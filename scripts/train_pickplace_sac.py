#!/usr/bin/env python
"""在 robosuite PickPlaceCan 上训 SAC：state / pixels 两种观测共用一个入口。

这是「视觉观测」路线的 V0/V1 共用脚本：
    V0 --obs state    不渲染，先验证「接触物理 + OSC 控制 + 稀疏成功」下 RL 能不能学会；
                      本机 state-only 约 94 步/秒（探针实测），100k 步约 25 分钟。
    V1 --obs pixels   观测换成 agentview 64x64x3 uint8，CNN 策略；
                      渲染是本机瓶颈（单相机 64² 约 117 ms/步 ≈ 8.5 fps），
                      所以像素档只跑短预算或配合示范预填，别一上来就 1M 步。

评测口径（和阶段 2 同一纪律）：
    训练中每 eval_freq 步做 n_eval_episodes 局**确定性**评测，报告
    episode 成功率（一局里 info["success"] 曾为 True）与 tasks_done；
    成功永远来自 robosuite 的真值判定，不用奖励代替。

用法：
    OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_pickplace_sac.py --obs state --steps 100000 \
        > /tmp/train_pp_state.log 2>&1 < /dev/null & disown
    python scripts/train_pickplace_sac.py --obs pixels --steps 5000 --eval-episodes 2   # 像素档冒烟
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")   # 本机实际是 Mesa llvmpipe 软渲染（docs/infra-gpu-render.md）

# 本机红线：TensorFlow 的用户态库与 MuJoCo 离屏渲染（llvmpipe）在同一进程里会 segfault
# （实测：import SB3 后再建离屏环境、或先建环境再 import SB3，两种顺序都崩）。
# TF 是被 SB3 -> torch.utils.tensorboard 拉进来的，而 SB3 对它的 import 有 try/except 保护，
# 所以在这里把该模块屏蔽掉：SB3 退化为 SummaryWriter=None，本脚本本来就用 json/npz 记账，不用 TB。
sys.modules.setdefault("torch.utils.tensorboard", None)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("stable_baselines3", "numpy", "torch")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from stable_baselines3 import SAC  # noqa: E402
from stable_baselines3.common.callbacks import BaseCallback  # noqa: E402

from envs.robosuite_lift import RobosuiteLift  # noqa: E402
from envs.robosuite_pickplace import RobosuitePickPlaceCan  # noqa: E402
from harness.env_factory import (PINNED_OBJECT_SEED, contact_object_geom,  # noqa: E402
                                 pinned_object_rng, reset_contact)


def _make_env(task: str, obs_mode: str, cams, cam_size: int, horizon: int,
              reward_shaping: bool, hist: int, pin: bool = True):
    """建接触环境的**唯一**入口（口径见 harness/README.md：接触任务都走 env_factory）。

    pin=True 钉死 robosuite 构造期的物体尺寸随机化。为什么这件事不能再拖
    （2026-09-24 实测）：`runs/20260923_171636_*`（20 局重评 15%）与
    `runs/20260924_095928_*`（同一配方、同一 seed，20 局重评 90%）config 逐项相同，
    差别只在"进程构造时抽到的那个 cube 不一样"。也就是说，此前每条臂其实是在
    **不同的物体**上训练、又在**另一个不同的物体**上评测，跨臂数字不可比。
    """
    env_cls = RobosuiteLift if task == "lift" else RobosuitePickPlaceCan
    kwargs = dict(obs_mode=obs_mode, cams=cams, cam_size=cam_size, horizon=horizon,
                  reward_shaping=reward_shaping, hist=hist)
    if not pin:
        return env_cls(**kwargs)
    with pinned_object_rng(PINNED_OBJECT_SEED):
        return env_cls(**kwargs)


def _reset(env, seed: int, pin: bool = True) -> np.ndarray:
    """评测出题：pin=True 时按**叶子** sampler 播种，同 seed = 同一道题（跨进程逐位相同）。

    包装层的 `reset(seed=...)` 只播了 `_env.rng`（机器人关节噪声那条路），
    PickPlace 的 `placement_initializer` 是 composite，只给它 `.rng` 赋值是**静默无效**的
    （harness/env_factory.py 里有实测对照）。所以评测必须走 `reset_contact`。
    """
    if not pin:
        obs, _ = env.reset(seed=seed)
        return np.asarray(obs)
    obs = reset_contact(env, seed)
    if getattr(env, "hist", 1) > 1:
        # reset_contact 内部会多喂一帧，堆叠缓冲重建一次，别让上一次 reset 的观测混进第 1 帧
        env._hist_buf = []
        obs = env._obs(env._env._get_observations())
    return np.asarray(obs)


def _state_obs(env):
    """控制器需要 robosuite 原始 obs（Can_pos / robot0_eef_pos / robot0_gripper_qpos）。

    包装层的 state 观测是压平的 proprio+object 向量，控制器读不了；直接问内层环境要
    原始 OrderedDict。像素档训练时控制器同样用这份真值状态当「接管者」的观测
    （示范数据里的 obs 仍然是像素，两者不混）。
    """
    return env._env._get_observations()


def _new_controller(env, task: str = "pickplace"):
    if task == "lift":
        from scripts.demo_scripted_lift_rs import LiftStateMachine
        return LiftStateMachine(cube_z0=float(_state_obs(env)["cube_pos"][2]))
    from scripts.demo_scripted_pickplace import PickPlaceStateMachine
    return PickPlaceStateMachine(
        env._env.bin2_pos,
        can_z0=float(_state_obs(env)["Can_pos"][2]),
        target_xy=env._env.target_bin_placements[env._env.object_to_id["can"]])


def fill_demo_buffer(model, demo_steps: int, obs_mode: str, cams, cam_size: int,
                     horizon: int, reward_shaping: bool, seed: int = 0,
                     task: str = "pickplace", lift_focus: bool = False, hist: int = 1,
                     pin: bool = True) -> dict:
    # hist>1 时示范 obs 与策略 obs 同口径（堆叠帧），BC 才不是学错维度
    """用脚本式 pick-place 控制器跑 demo_steps 步，把转移塞进 SAC 回放池再开在线 RL。

    与阶段 2 的 fill_demo_buffer 同一套路（SERL/RLPD 式最小闭环）：shaped 臂 100k 步
    只学到 lift/hover（重评 mean_reward 12.3、成功率 0%），按方案对齐文档的决策点
    「shaped 仍 <10% 就上示范预填」执行。示范源 = scripts/demo_scripted_pickplace.py
    的七段状态机（5/6 成功，含掉落重抓恢复），不需要人、可复现。
    """
    env = _make_env(task, obs_mode, cams, cam_size, horizon, reward_shaping, hist, pin=pin)
    ctrl = _new_controller(env, task)
    obs = _reset(env, seed, pin=pin)
    ctrl = _new_controller(env, task)
    added = episodes = tasks = 0
    prev_succ = False
    obs_list: list[np.ndarray] = []
    act_list: list[np.ndarray] = []
    snapshots: list[tuple[np.ndarray, np.ndarray]] = []
    normal_cap = demo_steps // 2 if lift_focus else demo_steps
    while added < normal_cap:
        prev_phase = ctrl.phase
        action = ctrl(_state_obs(env))
        next_obs, reward, terminated, truncated, info = env.step(action)
        # 「夹住并提起」是整条链上最稀疏的事件：在 grasp->lift 交接瞬间给仿真状态拍快照，
        # 主循环结束后从快照重放 lift 段做过采样（用户假设的可检验版本：加量 vs 加构成）。
        if lift_focus and prev_phase == "grasp" and ctrl.phase == "lift" and len(snapshots) < 16:
            snapshots.append((env._env.sim.data.qpos.copy(), env._env.sim.data.qvel.copy()))
        # SB3 2.x 的 add 要 batch 维：obs (1,)+space.shape，infos 是长度 1 的 list[dict]
        model.replay_buffer.add(obs[None], next_obs[None], np.asarray(action, dtype=np.float32)[None],
                                np.array([reward], dtype=np.float32),
                                np.array([terminated or truncated], dtype=np.float32),
                                [info])
        added += 1
        obs_list.append(np.asarray(obs, dtype=np.float32).ravel())
        act_list.append(np.asarray(action, dtype=np.float32).ravel())
        if info["success"] and not prev_succ:
            tasks += 1
        prev_succ = bool(info["success"])
        obs = next_obs
        if terminated or truncated or ctrl.phase == "done":
            episodes += 1
            prev_succ = False
            obs, _ = env.reset(seed=seed + episodes)
            ctrl = _new_controller(env, task)
    while lift_focus and snapshots and added < demo_steps:
        qpos, qvel = snapshots[added % len(snapshots)]
        sim = env._env.sim
        # 先 reset 清掉 robosuite 内部的 done/cur_step 记账（set_state 只恢复物理不恢复记账，
        # 否则累计超 horizon 后 step 会抛 "executing action in terminated episode"），再覆写物理状态。
        env._env.reset()
        sim.data.qpos[:] = qpos
        sim.data.qvel[:] = qvel
        sim.forward()
        ctrl = _new_controller(env, task)
        ctrl._set("lift")
        env._succ_held = False
        prev_succ = False
        obs = env._obs(env._env._get_observations())
        for _ in range(150):
            action = ctrl(_state_obs(env))
            next_obs, reward, terminated, truncated, info = env.step(action)
            model.replay_buffer.add(obs[None], next_obs[None], np.asarray(action, dtype=np.float32)[None],
                                    np.array([reward], dtype=np.float32),
                                    np.array([terminated or truncated], dtype=np.float32),
                                    [info])
            added += 1
            obs_list.append(np.asarray(obs, dtype=np.float32).ravel())
            act_list.append(np.asarray(action, dtype=np.float32).ravel())
            if info["success"] and not prev_succ:
                tasks += 1
            prev_succ = bool(info["success"])
            obs = next_obs
            if added >= demo_steps or ctrl.phase == "done" or terminated or truncated:
                break
    env.close()
    info = {"demo_steps": added, "demo_episodes": episodes, "demo_tasks": tasks,
            "buffer_pos": int(model.replay_buffer.pos), "snapshots": len(snapshots)}
    return info, np.asarray(obs_list, dtype=np.float32), np.asarray(act_list, dtype=np.float32)


def bc_warmstart_actor(model, obs_arr: np.ndarray, act_arr: np.ndarray, bc_steps: int,
                       lr: float = 1e-3, batch: int = 256, seed: int = 0) -> dict:
    """BC 热启动：拿示范 (obs, action) 直接预训练 SAC actor 的均值头，再开在线 RL。

    为什么回归目标用 atanh(action)：actor 的输出要过 tanh 才是动作，直接对 action 做 MSE
    会让均值头学到「tanh 之前」的错目标。clip 到 ±0.999 防止 atanh 在夹爪 ±1 上爆炸。
    只动 actor（critic 留给 RL 自己学），这是 SERL/RLPD 一脉「示范热启动」的最小版本。
    """
    target = np.arctanh(np.clip(act_arr, -0.999, 0.999)).astype(np.float32)
    obs_t = torch.as_tensor(obs_arr, device=model.device)
    tgt_t = torch.as_tensor(target, device=model.device)
    opt = torch.optim.Adam(model.policy.actor.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    n = len(obs_arr)
    first = last = float("nan")
    for i in range(bc_steps):
        idx = rng.integers(0, n, batch)
        # SB3 2.x 的 Actor.forward 返回采样动作；要拿「tanh 之前的均值」得走 get_action_dist_params
        mu, _log_std, _kwargs = model.policy.actor.get_action_dist_params(obs_t[idx])
        loss = ((mu - tgt_t[idx]) ** 2).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        first = first if i else float(loss)
        last = float(loss)
    return {"bc_steps": bc_steps, "bc_loss_first": first, "bc_loss_last": last}


def dagger_collect(model, env_cls, task: str, rounds: int, episodes: int, horizon: int,
                   seed_base: int = 7000, pin: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """DAgger 式补示范：让**当前策略** rollout，在它实际到达的状态上问脚本专家要动作。

    为什么这是「加示范」的正确姿势（2026-09-24 四条否证之后的结论）：纯 BC 的墙是闭环
    分布偏移（策略小错 -> 进示范里没有的状态 -> 更大错），加量/加构成/加时序都救不了；
    只有把示范加在「学习者会去的状态」上才对准这个墙。专家 = 状态机控制器：它的相位转移
    全是 obs 条件，丢进任意状态都能给出合理动作（掉落重抓就是这么来的）。
    """
    obs_list: list[np.ndarray] = []
    act_list: list[np.ndarray] = []
    # env_cls 参数保留只为兼容旧调用；构造统一走 _make_env（否则物体尺寸没钉死）
    env = _make_env(task, model.obs_mode, model.cams, model.cam_size, horizon,
                    model.reward_shaping, getattr(model, "hist", 1), pin=pin)
    for r in range(rounds):
        for e in range(episodes):
            obs = _reset(env, seed_base + r * episodes + e, pin=pin)
            ctrl = _new_controller(env, task)
            for _ in range(horizon):
                action_pol, _ = model.predict(obs, deterministic=True)
                act_list.append(np.asarray(ctrl(_state_obs(env)), dtype=np.float32).ravel())
                obs_list.append(np.asarray(obs, dtype=np.float32).ravel())
                obs, _rw, term, trunc, _info = env.step(action_pol)
                if term or trunc:
                    break
    env.close()
    return np.asarray(obs_list, dtype=np.float32), np.asarray(act_list, dtype=np.float32)


def evaluate(model, seed_base: int, episodes: int, horizon: int, pin: bool = True) -> dict:
    task = getattr(model, "task", "pickplace")
    env = _make_env(task, model.obs_mode, model.cams, model.cam_size, horizon,
                    model.reward_shaping, getattr(model, "hist", 1), pin=pin)
    succ, tasks, rewards = 0, 0, []
    for e in range(episodes):
        obs = _reset(env, seed_base + e, pin=pin)
        done, ep_r, ep_succ = False, 0.0, False
        for _ in range(horizon):
            action, _ = model.predict(obs, deterministic=True)
            obs, r, terminated, truncated, info = env.step(action)
            ep_r += r
            ep_succ = ep_succ or bool(info["success"])
            if terminated or truncated:
                break
        succ += int(ep_succ)
        tasks += env.tasks_done
        rewards.append(ep_r)
    env.close()
    return {"episodes": episodes, "episode_success": succ / episodes,
            "tasks_done": tasks, "mean_reward": float(np.mean(rewards))}


class BCAnchorCallback(BaseCallback):
    """在线 RL 期间每隔若干 env 步插一步 BC 梯度：把 actor 锚在示范上，防热启动被冲掉。

    不复制 SB3 的 SAC.train()（版本耦合太脆），而是用独立 optimizer 与 RL 的 actor
    optimizer 交替更新同一组参数——效果等价于 actor loss 里加 λ·MSE(mu, atanh(a_demo))。
    失败模式依据：bc-only 与从零 RL 都 5%，要看「热启动 + 锚定 + RL」能否把两者优点叠起来。
    """

    def __init__(self, obs_arr: np.ndarray, act_arr: np.ndarray, lr: float = 3e-4,
                 every: int = 1, batch: int = 256, seed: int = 0, verbose: int = 0):
        super().__init__(verbose)
        target = np.arctanh(np.clip(act_arr, -0.999, 0.999)).astype(np.float32)
        self._obs = torch.as_tensor(obs_arr)
        self._tgt = torch.as_tensor(target)
        self.lr, self.every, self.batch = lr, every, batch
        self.rng = np.random.default_rng(seed)
        self.opt: "torch.optim.Optimizer | None" = None
        self.losses: list[float] = []

    def _on_training_start(self) -> None:
        self._obs = self._obs.to(self.model.device)
        self._tgt = self._tgt.to(self.model.device)
        self.opt = torch.optim.Adam(self.model.policy.actor.parameters(), lr=self.lr)

    def _on_step(self) -> bool:
        if self.n_calls % self.every:
            return True
        idx = self.rng.integers(0, len(self._obs), self.batch)
        mu, _log_std, _kw = self.model.policy.actor.get_action_dist_params(self._obs[idx])
        loss = ((mu - self._tgt[idx]) ** 2).mean()
        assert self.opt is not None
        self.opt.zero_grad()
        loss.backward()
        self.opt.step()
        self.losses.append(float(loss))
        return True


def _run_dagger(model, env_cls, args, demo_obs, demo_act) -> list[dict]:
    """DAgger 轮循环（BC-only 与 RL 档共用）：每轮策略 rollout + 专家补示范 + 聚合重训 BC。"""
    dagger_info: list[dict] = []
    agg_obs, agg_act = demo_obs, demo_act
    for r in range(args.dagger_rounds):
        new_obs, new_act = dagger_collect(model, env_cls, args.task, 1, args.dagger_episodes,
                                          args.horizon, seed_base=7000 + r * args.dagger_episodes,
                                          pin=bool(args.pin_object))
        agg_obs = np.concatenate([agg_obs, new_obs])
        agg_act = np.concatenate([agg_act, new_act])
        info = bc_warmstart_actor(model, agg_obs, agg_act, args.bc_steps, seed=args.seed + r + 1)
        ev = evaluate(model, seed_base=2000, episodes=max(args.eval_episodes, 10), horizon=args.horizon,
                      pin=bool(args.pin_object))
        dagger_info.append({"round": r + 1, "agg_steps": int(len(agg_obs)),
                            "bc_loss_last": info["bc_loss_last"],
                            "success": ev["episode_success"], "tasks": ev["tasks_done"],
                            "mean_reward": ev["mean_reward"]})
        print(f"  [DAgger 轮 {r+1}] 聚合 {len(agg_obs)} 步  loss {info['bc_loss_last']:.4f}  "
              f"成功 {ev['episode_success']*100:.1f}%  tasks {ev['tasks_done']}  "
              f"reward {ev['mean_reward']:.2f}", flush=True)
    return dagger_info


def _run_guard(model, args, demo_obs, demo_act) -> list[dict]:
    """监护式干预学习：把 harness 的抓取监护当"干预者"，只在策略卡住的状态上补数据。

    与 `--dagger-rounds` 的区别（这一档存在的理由）：DAgger 让脚本专家给策略访问到的
    **所有**状态打标签；监护只保留"策略已经到了能抓的位置、却连续 N 步不合爪"那一小段的
    出手记录。前者是把策略往专家的全局轨迹上拉（2026-09-24 实测 BC+DAgger 0%/65.4），
    后者只补真正缺的那一环，数据量小一到两个量级，也正是 HIL-SERL 干预学习的口径
    （干预率随训练下降 = 策略真的在变好的独立指标）。

    `--guard-inject` 会把干预转移一并塞进 SAC 回放池：BC 只改 actor 均值头，容易被在线 RL
    冲掉（bc-anchor 那档的塌缩就是这个毛病）；进回放池后 critic 也见到"合爪 -> 提起"的
    因果，梯度层面才留得住。
    """
    from harness.grasp_guard import GuardConfig, collect_interventions

    gcfg = GuardConfig(max_per_episode=args.guard_max, dwell_steps=args.guard_dwell)
    bc_steps = args.guard_bc_steps or max(args.bc_steps, 1500)
    agg_obs, agg_act = demo_obs, demo_act
    info_list: list[dict] = []
    for r in range(args.guard_rounds):
        data = collect_interventions(model, args.task, cfg=gcfg, episodes=args.guard_episodes,
                                     horizon=args.horizon, seed_base=9000 + r * args.guard_episodes)
        st = data["stats"]
        if len(data["obs"]):
            agg_obs = np.concatenate([agg_obs, data["obs"]])
            agg_act = np.concatenate([agg_act, data["act"]])
        injected = 0
        if args.guard_inject:
            for tr in data["transitions"]:
                if not tr["guard_step"]:
                    continue
                model.replay_buffer.add(tr["obs"][None], tr["next_obs"][None], tr["action"][None],
                                        np.array([float(tr["reward"])], dtype=np.float32),
                                        np.array([bool(tr["done"])], dtype=np.float32), [tr["info"]])
                injected += 1
        bc = bc_warmstart_actor(model, agg_obs, agg_act, bc_steps, seed=args.seed + 100 + r)
        ev = evaluate(model, seed_base=2000, episodes=max(args.eval_episodes, 10), horizon=args.horizon,
                      pin=bool(args.pin_object))
        rec = {"round": r + 1, "guard_episodes": int(args.guard_episodes),
               "interventions": int(st["interventions"]), "guard_steps": int(st["guard_steps"]),
               "intervention_rate": float(st["intervention_rate"]),
               "collect_success": float(st["success_rate"]),
               "agg_steps": int(len(agg_obs)), "injected": int(injected),
               "bc_loss_last": bc["bc_loss_last"],
               "success": ev["episode_success"], "tasks": ev["tasks_done"],
               "mean_reward": ev["mean_reward"]}
        info_list.append(rec)
        print(f"  [监护轮 {r+1}] 干预 {rec['interventions']} 次/{rec['guard_steps']} 步"
              f"（干预局 {rec['intervention_rate']*100:.0f}%）  聚合 {rec['agg_steps']} 步  "
              f"注入回放池 {injected}  loss {rec['bc_loss_last']:.4f}  "
              f"成功 {rec['success']*100:.1f}%  tasks {rec['tasks']}  reward {rec['mean_reward']:.2f}",
              flush=True)
    return info_list


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs", default="state", choices=["state", "pixels"])
    ap.add_argument("--task", default="pickplace", choices=["pickplace", "lift"],
                    help="lift = 课程阶梯低一级（移动-抓-提起，无放置段），见 envs/robosuite_lift.py")
    ap.add_argument("--cams", default="agentview")
    ap.add_argument("--cam-size", type=int, default=64)
    ap.add_argument("--steps", type=int, default=100000)
    ap.add_argument("--horizon", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval-freq", type=int, default=10000)
    ap.add_argument("--eval-episodes", type=int, default=5)
    ap.add_argument("--buffer-size", type=int, default=100000)
    ap.add_argument("--net", default="256,256")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--run-name", default="")
    ap.add_argument("--reward-shaping", type=int, default=1,
                        help="1=robosuite 分段稠密奖励（reach/grasp/lift/hover），0=纯稀疏（成功+1）")
    ap.add_argument("--demo-steps", type=int, default=0, help=">0 时先用脚本控制器预填回放池再训练")
    ap.add_argument("--bc-steps", type=int, default=0,
                    help=">0 时用示范 (obs,action) 预训练 SAC actor 均值头再开 RL（需同时给 --demo-steps）")
    ap.add_argument("--bc-only", action="store_true",
                    help="只做 示范预填+BC 热启动，然后冻结评测并保存，不开在线 RL（归因用：纯模仿能到哪）")
    ap.add_argument("--bc-anchor-lr", type=float, default=0.0,
                    help=">0 时在线 RL 期间每步插一步 BC 梯度锚定 actor（需 --demo-steps > 0）")
    ap.add_argument("--demo-lift-focus", action="store_true",
                    help="lift 专用：示范一半正常采集、一半从 grasp->lift 快照重放 lift 段（稀疏事件过采样）")
    ap.add_argument("--hist", type=int, default=1,
                    help="状态观测堆叠帧数（>1 给策略时序信息消相位歧义；示范与策略同口径）")
    ap.add_argument("--dagger-rounds", type=int, default=0,
                    help="BC-only 档：每轮让当前策略 rollout 并在其状态上问脚本专家补示范，聚合重训")
    ap.add_argument("--dagger-episodes", type=int, default=10, help="DAgger 每轮 rollout 局数")
    ap.add_argument("--guard-rounds", type=int, default=0,
                    help=">0 时启用 harness 抓取监护的干预学习（harness/grasp_guard.py）：每轮"
                         "让当前策略跑、监护只在它卡住的状态上出手，出手记录当干预示范重训 actor")
    ap.add_argument("--guard-episodes", type=int, default=6, help="每轮监护采集的局数")
    ap.add_argument("--guard-dwell", type=int, default=8,
                    help="在抓取窗口内连续多少步不合爪才算'卡住'并接管（=0.4s @20Hz）")
    ap.add_argument("--guard-max", type=int, default=2, help="监护每局最多接管几次")
    ap.add_argument("--guard-bc-steps", type=int, default=0,
                    help="监护轮的 BC 步数（0 = 沿用 --bc-steps，且不低于 1500）")
    ap.add_argument("--guard-inject", action="store_true",
                    help="把干预转移一并塞进 SAC 回放池（让 critic 也见到'合爪->提起'的因果）")
    ap.add_argument("--pin-object", type=int, default=1,
                    help="1（默认）= 钉死构造期物体尺寸 + 评测按叶子 sampler 出题（跨进程可比）；"
                         "0 = 复现 2026-09-24 之前'每个进程一个随机物体'的旧口径，只为对账用")
    args = ap.parse_args()

    cams = tuple(c for c in args.cams.split(",") if c)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = args.run_name or f"sac_{args.task}_{args.obs}"
    run_dir = REPO_ROOT / "runs" / f"{ts}_{name}"
    run_dir.mkdir(parents=True, exist_ok=True)

    env_cls = RobosuiteLift if args.task == "lift" else RobosuitePickPlaceCan
    pin = bool(args.pin_object)
    env = _make_env(args.task, args.obs, cams, args.cam_size, args.horizon,
                    bool(args.reward_shaping), args.hist, pin=pin)
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    if args.obs == "pixels":
        policy, policy_kwargs = "CnnPolicy", {}
    else:
        policy = "MlpPolicy"
        policy_kwargs = {"net_arch": [int(x) for x in args.net.split(",")]}

    model = SAC(policy, env, learning_rate=3e-4, buffer_size=args.buffer_size,
                learning_starts=1000, batch_size=256, tau=0.005, gamma=0.99,
                train_freq=1, gradient_steps=1, policy_kwargs=policy_kwargs,
                seed=args.seed, device=device, verbose=0)
    model.obs_mode, model.cams, model.cam_size = args.obs, cams, args.cam_size  # evaluate 要用
    model.reward_shaping = bool(args.reward_shaping)
    model.task = args.task
    model.hist = args.hist
    model.pin_object = pin

    demo_info = {}
    bc_info = {}
    # 没有 --demo-steps 时也要给一对空数组：_run_dagger / _run_guard 拿它们当聚合起点
    # （此前只在 demo_steps>0 分支里赋值，纯 RL 档走到 _run_dagger 调用处会 NameError）。
    demo_obs = np.zeros((0, int(np.prod(env.observation_space.shape))), dtype=np.float32)
    demo_act = np.zeros((0, int(np.prod(env.action_space.shape))), dtype=np.float32)
    if args.demo_steps > 0:
        demo_info, demo_obs, demo_act = fill_demo_buffer(model, args.demo_steps, args.obs, cams, args.cam_size,
                                                         args.horizon, bool(args.reward_shaping), seed=args.seed,
                                                         task=args.task, lift_focus=args.demo_lift_focus,
                                                         hist=args.hist, pin=pin)
        print(f"  [示范预填] 脚本控制器 {demo_info['demo_steps']} 步 / {demo_info['demo_episodes']} 局 "
              f"-> 回放池 {demo_info['buffer_pos']}", flush=True)
        if args.bc_steps > 0:
            if args.obs == "pixels":
                raise SystemExit("BC 热启动当前只支持 state 观测（像素档要先定 CNN 结构再谈）")
            bc_info = bc_warmstart_actor(model, demo_obs, demo_act, args.bc_steps, seed=args.seed)
            print(f"  [BC 热启动] {bc_info['bc_steps']} 步梯度  loss {bc_info['bc_loss_first']:.4f} "
                  f"-> {bc_info['bc_loss_last']:.4f}", flush=True)
    elif args.bc_steps > 0:
        raise SystemExit("--bc-steps 需要示范数据：请同时给 --demo-steps > 0")
    if args.bc_only and args.bc_steps <= 0:
        raise SystemExit("--bc-only 需要 --bc-steps > 0（且 --demo-steps > 0）")
    if args.dagger_rounds > 0 and args.demo_steps <= 0:
        raise SystemExit("--dagger-rounds 需要示范数据：请同时给 --demo-steps > 0")
    if args.guard_rounds > 0 and args.obs == "pixels":
        raise SystemExit("--guard-rounds 的 BC 环节当前只支持 state 观测（像素档要先定 CNN 结构）")

    cfg = {"task": args.task, "obs": args.obs, "cams": list(cams), "cam_size": args.cam_size, "steps": args.steps,
           "reward_shaping": bool(args.reward_shaping),
           "demo_steps": int(demo_info.get("demo_steps", 0)),
          "demo_episodes": int(demo_info.get("demo_episodes", 0)),
           "bc_steps": int(bc_info.get("bc_steps", 0)),
           "demo_lift_focus": bool(args.demo_lift_focus),
           "hist": int(args.hist),
          "dagger_rounds": int(args.dagger_rounds),
          "guard_rounds": int(args.guard_rounds),
          "guard_episodes": int(args.guard_episodes),
          "guard_dwell": int(args.guard_dwell),
          "guard_max": int(args.guard_max),
          "guard_inject": bool(args.guard_inject),
          "bc_anchor_lr": float(args.bc_anchor_lr),
          "pin_object": pin,
          "horizon": args.horizon, "seed": args.seed, "device": device, "policy": policy,
          "policy_kwargs": policy_kwargs, "timestamp": ts}
    # 物体几何进产物：比较两条臂的成功率之前，先能回答"是不是同一个 cube / 同一个 can"
    try:
        cfg["object_geom"] = contact_object_geom(env, args.task, PINNED_OBJECT_SEED if pin else None)
    except Exception as exc:      # 审计失败不该挡住训练，但必须留痕
        cfg["object_geom"] = {"error": f"{type(exc).__name__}: {exc}"}
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

    print(f"[SAC] {args.task} · obs={args.obs} · steps={args.steps} · device={device}")
    print(f"      run 目录: {run_dir}")
    dagger_info = _run_dagger(model, env_cls, args, demo_obs, demo_act)
    guard_info = _run_guard(model, args, demo_obs, demo_act)
    if args.bc_only:
        final = evaluate(model, seed_base=2000, episodes=max(args.eval_episodes, 20),
                         horizon=args.horizon, pin=pin)
        model.save(str(run_dir / "model_final.zip"))
        result = {**cfg, "demo": demo_info, "bc": bc_info, "bc_only": True,
                  "dagger": dagger_info,
                  "guard": guard_info,
                  "train_seconds": 0.0, "steps_per_second": 0.0, "curve": [], "eval_final": final}
        (run_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"  [BC-only 冻结评测] episode 成功率 {final['episode_success']*100:.1f}%  "
              f"tasks {final['tasks_done']}  mean_reward {final['mean_reward']:.2f}")
        print(f"[已保存] {run_dir / 'result.json'}")
        env.close()
        return 0
    curve = []
    t0 = time.perf_counter()
    best_key, best_saved = (-1, -1.0), False
    callbacks = []
    if args.bc_anchor_lr > 0:
        if args.demo_steps <= 0:
            raise SystemExit("--bc-anchor-lr 需要示范数据：请同时给 --demo-steps > 0")
        callbacks.append(BCAnchorCallback(demo_obs, demo_act, lr=args.bc_anchor_lr, seed=args.seed))
    for chunk in range(0, args.steps, args.eval_freq):
        model.learn(total_timesteps=args.eval_freq, reset_num_timesteps=False, progress_bar=False,
                    callback=callbacks or None)
        ev = evaluate(model, seed_base=1000, episodes=args.eval_episodes, horizon=args.horizon, pin=pin)
        done_steps = chunk + args.eval_freq
        curve.append({"step": done_steps, **ev})
        key = (ev["tasks_done"], ev["episode_success"])
        if key > best_key:
            best_key = key
            model.save(str(run_dir / "model_best.zip"))
            best_saved = True
        anchor = f"  anchor_loss {callbacks[0].losses[-1]:.4f}" if callbacks and callbacks[0].losses else ""
        print(f"  [eval @ {done_steps:7d} 步] episode 成功率 {ev['episode_success']*100:5.1f}%  "
              f"tasks {ev['tasks_done']}  mean_reward {ev['mean_reward']:.2f}{anchor}", flush=True)
        (run_dir / "eval_curve.json").write_text(json.dumps(curve, indent=1))
    secs = time.perf_counter() - t0
    model.save(str(run_dir / "model_final.zip"))
    final = evaluate(model, seed_base=2000, episodes=max(args.eval_episodes, 5),
                     horizon=args.horizon, pin=pin)
    result = {**cfg, "demo": demo_info, "train_seconds": secs, "steps_per_second": args.steps / secs,
              "bc": bc_info, "curve": curve, "eval_final": final,
              "dagger": dagger_info,
              "guard": guard_info,
              "eval_best": {"key_tasks": best_key[0], "key_success": best_key[1],
                            "ckpt": "model_best.zip" if best_saved else None}}
    (run_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"  训练耗时 {secs:.0f} 秒（{args.steps/secs:.1f} 步/秒）")
    print(f"  [冻结评测] episode 成功率 {final['episode_success']*100:.1f}%  tasks {final['tasks_done']}")
    print(f"[已保存] {run_dir / 'result.json'}")
    env.close()


if __name__ == "__main__":
    main()
