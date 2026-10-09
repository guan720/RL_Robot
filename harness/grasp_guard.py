"""抓取监护（harness 级干预）：策略"到了能抓的位置却迟迟不合爪"时，由脚本原语接管一次。

为什么要有这一块（2026-09-24 的实测背景）：
    用户观察到的现象是"臂能移动到目标上方，但抓不起来"。同一现象我们此前用五种
    "加示范"的办法试过（加量 4×、lift 段过采样、堆时序 hist、纯 BC、BC+DAgger），
    结论是**加在示范侧的量与构成都救不了闭环分布偏移**：只有把示范加在"学习者自己
    会到达的状态"上才有信号（DAgger）。本模块把这件事做成 harness 的一个部件：
    监护器只在**策略实际卡住的那些状态**上出手，出手记录既能量化"救回多少"，
    也能直接当作干预示范喂回训练。

    这正是 HIL-SERL 里"人类干预"的位置，只是把干预者从人换成一段有特权的脚本原语。
    先例：HIL-SERL 的干预率随训练单调下降，是判断"策略真的在变好"的独立指标。

三条纪律（别破）：
    1. **成功判定只来自环境真值**（`env._env._check_success()`），监护器不自己宣布成功。
    2. **监护成绩与策略成绩分开报**：`evaluate_guarded` 用同一批 seed 跑"裸策略"和
       "带监护"两遍，输出 `policy_only` / `guarded` / `rescue_delta`。只报 guarded 会
       把脚本原语的功劳记到策略头上（这就是 RoboRSI 报告里"累计覆盖"掩盖退化的同类错误）。
    3. **干预率是要下降的指标**：`intervention_rate` 与 `rescue_delta` 一起看。
       干预率高 + 救回多 = 策略确实缺"合爪"这一环；干预率低 = 监护基本没出手，
       成绩是策略自己的。

监护器是**特权**监督者：它读 robosuite 原始 obs（物体真值位姿、末端位姿、夹爪 qpos），
这些信息不在策略的观测里也没关系——现实中的干预者（人或上层 harness）本来就看得到场景。
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Sequence

import numpy as np

# 物体真值位姿的键名随任务变（Lift = cube_pos 小写，PickPlaceCan = Can_pos），沿用脚本控制器口径
_OBJ_KEYS = ("cube_pos", "Cube_pos", "Can_pos", "can_pos")


def object_pos(raw: dict) -> np.ndarray:
    """从 robosuite 原始 obs 里取被操作物体的位置（3,）。"""
    for key in _OBJ_KEYS:
        if key in raw:
            return np.asarray(raw[key], dtype=np.float64)[:3]
    raise KeyError(f"obs 里找不到物体位姿键，现有键：{sorted(k for k in raw if k.endswith('_pos'))}")


def gripper_width(raw: dict) -> float:
    """夹爪开度：两指 qpos 反号，取绝对值最大者（与 demo_scripted_lift_rs.py 同口径）。

    经验刻度（Panda + robosuite 1.5，2026-09-23 实测）：
        ~0.04 全开；0.012–0.035 是"执行器过渡区"，读数会抖（这段别用来做判定）；
        <=0.012 空合（指间没东西）；夹住 Lift 的小方块时稳定在 0.02 附近。
    """
    return float(np.max(np.abs(np.asarray(raw["robot0_gripper_qpos"], dtype=np.float64))))


@dataclasses.dataclass
class GuardConfig:
    """监护器的几何与预算常数。默认值来自 demo_scripted_lift_rs.py 的实测（6/6 成功）。"""

    # --- 触发模式 ---
    # window：只认"已经到了抓取窗口却不合爪"（窄，只补合爪时机这一环）
    # stall ：放宽到"在物体附近停住不动、又不合爪"（宽，能覆盖 PickPlace 那种
    #          连窗口都进不去的失败；2026-09-24 漏斗实测 held 0/12、6 局 no_reach）
    mode: str = "window"

    # --- window 模式：什么叫"已经到了能抓的位置" ---
    xy_tol: float = 0.014          # 末端与物体的水平误差上限（脚本控制器用 0.008，这里放宽给学习策略）
    z_lo: float = 0.005            # 末端高出物体的下限：太低说明压在物体上
    z_hi: float = 0.045            # 末端高出物体的上限：太高还没到抓取高度
    close_cmd: float = 0.2         # 策略动作第 7 维 >= 该值才算"在 decisively 合爪"（+1 闭 / -1 开）
    lift_eps: float = 0.010        # 物体高出初始位置不足该值 => 认定"还没抓起来"
    dwell_steps: int = 8           # 在窗口内连续多少步不合爪才接管（=0.4s @20Hz）；防抢策略自己的合爪

    # --- stall 模式：捕获半径 + "真的停住了"的判据 ---
    stall_xy_tol: float = 0.060    # 水平捕获半径：再远就不是"够到了不会抓"，而是"根本没到"
    stall_z_lo: float = -0.010     # 末端相对物体的高度下界（允许略低于物体顶面）
    stall_z_hi: float = 0.120      # 上界：太高说明还在接近段，不该由监护替它飞过去
    stall_move_eps: float = 0.005  # 窗口内末端最大位移小于该值 => 判"停在原地"（不是路过）
    stall_steps: int = 20          # 停滞判定窗长（=1s @20Hz）；stall 模式下 dwell_steps 取该值
    held_dz: float = 0.020         # 物体被抬离初始高度超过该值 => 记 ever_held（真抓住了）

    # --- 接管预算 ---
    max_per_episode: int = 2       # 一局最多接管几次（防监护器把整局都跑完）
    cooldown_steps: int = 20       # 一次接管结束后的冷却步数，防"接管-松手-立刻再接管"死循环
    align_steps: int = 30          # 对齐到物体上方抓取位的步数上限
    grasp_steps: int = 25          # 合爪步数（与脚本控制器一致）
    lift_steps: int = 45           # 提升步数上限
    grasp_z: float = 0.020         # 抓取时末端高于物体的距离（脚本控制器实测值）
    lift_dz: float = 0.050         # 物体提到 z0 + lift_dz 就交还控制权（Lift 成功阈值约 0.04）
    step_scale: float = 0.05       # OSC_POSE：动作 ±1 对应每步 5cm 位移


class GraspGuard:
    """一个"只在抓取窗口内出手"的脚本原语：对齐 → 合爪 → 提起 → 交还控制权。

    用法：每个控制步先 `observe(raw, policy_action, succeeded)`，返回 None 表示不干预
    （照策略的动作走），返回 7 维数组表示本步由监护器接管。
    """

    def __init__(self, cfg: GuardConfig | None = None) -> None:
        self.cfg = cfg or GuardConfig()
        self.reset(obj_z0=0.0)

    def reset(self, obj_z0: float) -> None:
        self.obj_z0 = float(obj_z0)
        self.phase = "idle"          # idle / align / close / lift
        self.phase_step = 0
        self.dwell = 0
        self.cooldown = 0
        self.used = 0
        self.steps = 0
        self.log: list[str] = []
        self._eef_hist: list[np.ndarray] = []

    # ------------------------------------------------------------------ 判定
    def _in_window(self, raw: dict) -> bool:
        """窄窗口判据（window 模式的几何部分）；触发逻辑统一在 `_trigger` 里。"""
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        obj = object_pos(raw)
        dxy = max(abs(eef[0] - obj[0]), abs(eef[1] - obj[1]))
        dz = eef[2] - obj[2]
        return dxy <= self.cfg.xy_tol and self.cfg.z_lo <= dz <= self.cfg.z_hi

    def _not_grasped(self, raw: dict) -> bool:
        """物体还没被提起来 => 抓取尚未成功（用物体高度，不用夹爪读数：过渡区会抖）。"""
        return float(object_pos(raw)[2]) < self.obj_z0 + self.cfg.lift_eps

    def _stalled(self, eef: np.ndarray) -> bool:
        """末端在最近 stall_steps 步里是否"停在原地"（位移小于 stall_move_eps）。

        为什么要这一条：只按半径触发会把"正在路过物体上方"的步也抢下来，
        等于用脚本控制器替策略飞完接近段——那就不是在补抓取，而是在替换策略。
        """
        if len(self._eef_hist) < self.cfg.stall_steps:
            return False
        window = np.asarray(self._eef_hist[-self.cfg.stall_steps:])
        return float(np.max(np.abs(window - eef))) <= self.cfg.stall_move_eps

    def _trigger(self, raw: dict, act: np.ndarray) -> bool:
        """本步是否满足"该接管了"的几何条件（连续 dwell_steps 步满足才真接管）。"""
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        obj = object_pos(raw)
        dxy = max(abs(eef[0] - obj[0]), abs(eef[1] - obj[1]))
        dz = eef[2] - obj[2]
        self._eef_hist.append(eef.copy())
        self._eef_hist = self._eef_hist[-max(self.cfg.stall_steps, self.cfg.dwell_steps):]
        if act[6] >= self.cfg.close_cmd:          # 策略正在合爪：别抢
            return False
        if not self._not_grasped(raw):            # 已经抓起来了：没必要
            return False
        if self.cfg.mode == "stall":
            in_radius = dxy <= self.cfg.stall_xy_tol and self.cfg.stall_z_lo <= dz <= self.cfg.stall_z_hi
            return bool(in_radius and self._stalled(eef))
        return bool(dxy <= self.cfg.xy_tol and self.cfg.z_lo <= dz <= self.cfg.z_hi)

    # ------------------------------------------------------------------ 主接口
    def observe(self, raw: dict, policy_action: Sequence[float], succeeded: bool = False):
        """返回本步实际该执行的动作：None = 不干预（用策略动作），ndarray = 监护器接管。"""
        act = np.asarray(policy_action, dtype=np.float64).ravel()
        if self.phase != "idle":
            return self._run_phase(raw)
        if succeeded or self.used >= self.cfg.max_per_episode:
            self.dwell = 0
            return None
        if self.cooldown > 0:
            self.cooldown -= 1
            self.dwell = 0
            return None
        stalling = self._trigger(raw, act)
        self.dwell = self.dwell + 1 if stalling else 0
        need = self.cfg.stall_steps if self.cfg.mode == "stall" else self.cfg.dwell_steps
        if self.dwell < need:
            return None
        self.used += 1
        self.dwell = 0
        self._set("align")
        self.log.append(f"intervene@{self.used}")
        return self._run_phase(raw)

    # ------------------------------------------------------------------ 接管原语
    def _set(self, phase: str) -> None:
        self.phase = phase
        self.phase_step = 0
        self.log.append(phase)

    def _action(self, raw: dict, target: np.ndarray, grip: float) -> np.ndarray:
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        action = np.zeros(7, dtype=np.float64)
        action[:3] = np.clip((target - eef) / self.cfg.step_scale, -1.0, 1.0)
        action[6] = grip            # +1 闭合 / -1 张开（写反的症状见 demo_scripted_lift_rs.py）
        return action

    def _run_phase(self, raw: dict) -> np.ndarray:
        cfg = self.cfg
        self.phase_step += 1
        self.steps += 1
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        obj = object_pos(raw)

        if self.phase == "align":
            target = obj + np.array([0.0, 0.0, cfg.grasp_z])
            ok = (max(abs(eef[0] - obj[0]), abs(eef[1] - obj[1])) <= 0.008
                  and abs(eef[2] - obj[2] - cfg.grasp_z) <= 0.008)
            if ok or self.phase_step >= cfg.align_steps:
                self._set("close")
            return self._action(raw, target, -1.0)

        if self.phase == "close":
            target = obj + np.array([0.0, 0.0, cfg.grasp_z - 0.002])
            if self.phase_step >= cfg.grasp_steps:
                self._set("lift")
            return self._action(raw, target, 1.0)

        if self.phase == "lift":
            target = eef + np.array([0.0, 0.0, 0.3])
            if obj[2] > self.obj_z0 + cfg.lift_dz or self.phase_step >= cfg.lift_steps:
                self._set("idle")
                self.cooldown = cfg.cooldown_steps
            return self._action(raw, target, 1.0)

        self._set("idle")
        self.cooldown = cfg.cooldown_steps
        return self._action(raw, eef.copy(), 1.0)


class GuardedRollout:
    """在真环境上跑"策略 + 监护"的一局，记录干预账本与（可选）转移数据。

    刻意不写成 gym.Wrapper：本仓库的评测/采集都是自己持有 env 的循环，
    一个显式的 runner 比 wrapper 更容易读，也避免 gymnasium 版本的属性转发差异。
    """

    def __init__(self, env: Any, cfg: GuardConfig | None = None, record: bool = False,
                 pin: bool = True) -> None:
        self.env = env
        self.pin = bool(pin)
        self.cfg = cfg or GuardConfig()
        self.guard = GraspGuard(self.cfg)
        self.record = bool(record)
        self.transitions: list[dict] = []
        self.episodes: list[dict] = []

    def _raw(self) -> dict:
        return self.env._env._get_observations()

    def episode(self, policy_fn: Callable[[np.ndarray], np.ndarray], seed: int, horizon: int) -> dict:
        obs = reset_env(self.env, seed, pin=self.pin)
        raw = self._raw()
        z0 = float(object_pos(raw)[2])
        self.guard.reset(obj_z0=z0)
        succ, held, guard_steps, steps = False, False, 0, 0
        for t in range(horizon):
            policy_action = np.asarray(policy_fn(obs), dtype=np.float64).ravel()
            override = self.guard.observe(raw, policy_action, succeeded=bool(self.env._env._check_success()))
            action = policy_action if override is None else override
            is_guard = override is not None      # None = 监护没出手，本步是策略自己的动作
            next_obs, reward, terminated, truncated, info = self.env.step(action)
            if self.record:
                self.transitions.append({
                    "obs": np.asarray(obs, dtype=np.float32).ravel(),
                    "next_obs": np.asarray(next_obs, dtype=np.float32).ravel(),
                    "action": np.asarray(action, dtype=np.float32).ravel(),
                    "reward": np.float32(reward),
                    "done": np.float32(bool(terminated or truncated)),
                    "guard_step": bool(is_guard),
                    "info": info,
                })
            if is_guard:
                guard_steps += 1
            steps = t + 1
            succ = succ or bool(info["success"])
            obs = next_obs
            raw = self._raw()
            held = held or (float(object_pos(raw)[2]) - z0 > self.cfg.held_dz)
            if terminated or truncated:
                break
        ep = {"seed": int(seed), "success": bool(succ), "held": bool(held), "steps": steps,
              "tasks_done": int(getattr(self.env, "tasks_done", 0)),
              "interventions": int(self.guard.used), "guard_steps": int(guard_steps),
              "phases": list(self.guard.log)}
        self.episodes.append(ep)
        return ep

    # ------------------------------------------------------------------ 数据出口
    def guard_pairs(self) -> tuple[np.ndarray, np.ndarray]:
        """只取监护器出手的那些 (obs, action)：这就是"干预示范"。"""
        rows = [t for t in self.transitions if t["guard_step"]]
        if not rows:
            return (np.zeros((0, self.env.observation_space.shape[0]), dtype=np.float32),
                    np.zeros((0, 7), dtype=np.float32))
        return (np.asarray([r["obs"] for r in rows], dtype=np.float32),
                np.asarray([r["action"] for r in rows], dtype=np.float32))

    def summary(self, episodes: int | None = None) -> dict:
        eps = self.episodes[-episodes:] if episodes else self.episodes
        n = max(len(eps), 1)
        touched = sum(e["interventions"] > 0 for e in eps)
        rescued = sum(e["success"] and e["interventions"] > 0 for e in eps)
        return {"episodes": len(eps), "success": sum(e["success"] for e in eps),
                "success_rate": sum(e["success"] for e in eps) / n,
                "held": sum(e.get("held", False) for e in eps),
                "held_rate": sum(e.get("held", False) for e in eps) / n,
                "tasks_done": sum(e["tasks_done"] for e in eps),
                "interventions": sum(e["interventions"] for e in eps),
                "intervention_rate": touched / n,
                "guard_steps": sum(e["guard_steps"] for e in eps),
                "rescued_episodes": rescued}


def make_env(model, horizon: int):
    """按 ckpt 的 task/obs/hist 建环境，并**钉死构造期物体尺寸**。

    为什么必须钉（2026-09-24 实测踩到）：robosuite 在构造期用未播种 RNG 抽物体尺寸，
    所以"裸策略"与"带监护"两次建环境拿到的是**两个不同的 cube** —— 配对评测就失去
    意义（4 局冒烟里出现"监护没出手的那局结果却变了"，裸 50% vs 带监护 25%）。
    口径统一走 `harness/env_factory.pinned_object_rng`；出题走 `reset_contact`
    （按叶子 sampler 播种；PickPlace 上只播 composite.rng 是静默无效的）。
    代价：这里的绝对数字与历史"未钉死"的重评不可直接互比，**只有配对内的差值可比**。
    """
    from harness.env_factory import PINNED_OBJECT_SEED, pinned_object_rng
    from envs.robosuite_lift import RobosuiteLift
    from envs.robosuite_pickplace import RobosuitePickPlaceCan
    env_cls = RobosuiteLift if getattr(model, "task", "pickplace") == "lift" else RobosuitePickPlaceCan
    kwargs = dict(obs_mode=model.obs_mode, cams=model.cams, cam_size=model.cam_size,
                  horizon=horizon, reward_shaping=model.reward_shaping,
                  hist=getattr(model, "hist", 1))
    if not getattr(model, "pin_object", True):
        return env_cls(**kwargs)
    with pinned_object_rng(PINNED_OBJECT_SEED):
        return env_cls(**kwargs)


def reset_env(env, seed: int, pin: bool = True) -> np.ndarray:
    """可复现出题：物体出生点只由 seed 决定（Lift / PickPlace 通用）。

    `pin=False` 走旧口径（只播包装层 rng），仅为和 2026-09-24 之前的历史数字对账。
    """
    if not pin:
        obs, _ = env.reset(seed=seed)
        return np.asarray(obs)
    from harness.env_factory import reset_contact
    obs = reset_contact(env, seed)
    if getattr(env, "hist", 1) > 1:
        # reset_contact 内部会多喂一帧，堆叠缓冲得重建，否则第 1 帧混进上一次 reset 的观测
        env._hist_buf = []
        obs = env._obs(env._env._get_observations())
    return np.asarray(obs)


def evaluate_guarded(model, seed_base: int, episodes: int, horizon: int,
                     cfg: GuardConfig | None = None) -> dict:
    """配对评测：同一批 seed 先跑裸策略，再跑带监护，输出两者的差（rescue）。

    返回的 `rescue_delta` 才是"监护救回了多少"，`intervention_rate` 是"监护出手了多少"。
    """
    plain = _run(model, seed_base, episodes, horizon, cfg, guarded=False)
    guarded = _run(model, seed_base, episodes, horizon, cfg, guarded=True)
    out = {"episodes": episodes, "seed_base": seed_base,
           "policy_only": plain["summary"], "guarded": guarded["summary"],
           "rescue_delta": guarded["summary"]["success_rate"] - plain["summary"]["success_rate"],
           "held_delta": guarded["summary"]["held_rate"] - plain["summary"]["held_rate"],
           "per_episode": guarded["episodes"]}
    return out


def _run(model, seed_base: int, episodes: int, horizon: int,
         cfg: GuardConfig | None, guarded: bool) -> dict:
    pin = bool(getattr(model, "pin_object", True))
    env = make_env(model, horizon)
    roll = GuardedRollout(env, cfg, pin=pin)
    policy_fn = lambda obs: model.predict(obs, deterministic=True)[0]  # noqa: E731
    eps = []
    for e in range(episodes):
        if not guarded:
            obs = reset_env(env, seed_base + e, pin=pin)
            z0 = float(object_pos(env._env._get_observations())[2])
            held_dz = (cfg or GuardConfig()).held_dz
            succ, held, steps = False, False, 0
            for t in range(horizon):
                action, _ = model.predict(obs, deterministic=True)
                obs, _r, term, trunc, info = env.step(action)
                steps = t + 1
                succ = succ or bool(info["success"])
                held = held or (float(object_pos(env._env._get_observations())[2]) - z0 > held_dz)
                if term or trunc:
                    break
            eps.append({"seed": seed_base + e, "success": bool(succ), "held": bool(held),
                        "steps": steps, "tasks_done": int(env.tasks_done), "interventions": 0,
                        "guard_steps": 0, "phases": []})
        else:
            eps.append(roll.episode(policy_fn, seed=seed_base + e, horizon=horizon))
    env.close()
    n = max(len(eps), 1)
    touched = sum(e["interventions"] > 0 for e in eps)
    return {"episodes": eps,
            "summary": {"episodes": len(eps), "success": sum(e["success"] for e in eps),
                        "success_rate": sum(e["success"] for e in eps) / n,
                        "held": sum(e.get("held", False) for e in eps),
                        "held_rate": sum(e.get("held", False) for e in eps) / n,
                        "tasks_done": sum(e["tasks_done"] for e in eps),
                        "interventions": sum(e["interventions"] for e in eps),
                        "guard_steps": sum(e["guard_steps"] for e in eps),
                        "intervention_rate": touched / n,
                        "rescued_episodes": sum(e["success"] and e["interventions"] > 0 for e in eps)}}


def collect_interventions(model, task: str, cfg: GuardConfig | None = None, episodes: int = 6,
                          horizon: int = 300, seed_base: int = 9000, **env_kw) -> dict:
    """采集"干预示范"：让当前策略跑，监护器只在它卡住的状态上出手，出手记录留作训练数据。

    与 DAgger 的区别（这是本模块的关键）：DAgger 让脚本专家给**所有**访问到的状态打标签，
    等于把策略往"专家的全局轨迹"上拉；干预采集只保留**策略自己走不动的那一小段**，
    数据量小得多，也更贴近 HIL-SERL 的"人类只在必要时接管"。
    """
    env = make_env(model, horizon)
    roll = GuardedRollout(env, cfg, record=True, pin=bool(getattr(model, "pin_object", True)))
    policy_fn = lambda obs: model.predict(obs, deterministic=True)[0]  # noqa: E731
    for e in range(episodes):
        roll.episode(policy_fn, seed=seed_base + e, horizon=horizon)
    obs_arr, act_arr = roll.guard_pairs()
    env.close()
    return {"obs": obs_arr, "act": act_arr, "transitions": roll.transitions,
            "episodes": roll.episodes, "stats": roll.summary()}
