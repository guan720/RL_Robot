"""§12.0 的「第 0 步」探针迁移到**真接触物理**（robosuite Lift / PickPlaceCan）。

为什么要迁移，以及为什么不是直接把 harness 接上去
------------------------------------------------
Reach 线的教训（§6.12）是：**先量可达上限和难度坐标，再烧预算**。搬到接触物理，
第一个要回答的不是「诊断有没有用」，而是「这个任务上有没有可判定的测量空间」。
现有实测把两头都堵住了：

    · `envs/robosuite_lift.py` 的文档记载：PickPlaceCan 在 100k 步下稀疏/shaped/
      shaped+示范三臂的冻结成功率**全是 0%** —— 完全没有爬升段，阈值梯无从谈起。
    · 降到 Lift 这一级之后：对方的示范采集是 **60 局 60 task**（`result.json` 的
      `demo.demo_tasks`），说明**手写状态机≈满分**；而 SAC 60k 步（shaped+demo5k）
      的 20 局固定复评只有 **0.10**（`reeval_fixed_success.json`），一条臂 6713 s GPU。
    · 几何抽象的 transport 线（`skills/transport_skill.py`）手写比例控制 **0.987** —— 饱和。

也就是说：**手写在上限（≈1.0），SAC 在地板（≈0.10），全局成功率这个统计量在可负担的
预算里没有分辨力**。所以本探针换一个统计量：

    不按「全局成功率是否越过 0.3/0.5」判定，而按**物体出生位置**分格，
    量「同一个出生点上，手写 vs SAC 各自成不成」——
      · 两者都成的格子 = 太简单，采样在这里是浪费；
      · 两者都不成的格子 = 太难，采样在这里也学不到东西；
      · **只有手写成、SAC 时成时不成的格子才是 frontier**，针对性采样唯一能发力的地方。

    这个口径的好处：即使全局成功率只有 0.10，**条件成功率**仍然有分辨力，
    而且它直接就是 §12.8 里说的「`SamplingPlan` 从距离带换成 (物体初位, 目标位)
    联合分布」要挂上去的那根坐标轴。

**一个必须先修的坑（2026-09-23 实测）**：包装层 `envs/robosuite_pickplace.py::reset(seed=N)`
只设了 `self._env.rng`，但真正决定物体摆放的是
`self._env.placement_initializer`（一个 `UniformRandomSampler`），它**自带一个独立的
`rng` 属性**，没有人给它播种。实测：同一进程里 `reset(seed=1000)` 连做 4 次，cube 出生点是
4 个不同位置。后果有两条，都很致命：
  · 「同 seed = 同一道题」不成立 ⇒ 手写 vs SAC 的**逐题配对是假的**（配的是噪声）；
  · 对方的「固定口径复评」（`reeval_fixed_success.json`，20 局 0.10）其实**没有固定题目**，
    它的方差里混着出题方差，跨 run 的数字不严格可比。
修法（一行，属于对方文件，**只上报不代改**）：`reset()` 里同时
`self._env.placement_initializer.rng = np.random.default_rng(seed)`。
本探针在自己这一侧用 `reset_controlled()` 绕过：先走包装层 reset（重置它的记账），
再给 `placement_initializer.rng` 播种并重新 `inner.reset()`，然后用 `--verify-seeding`
（默认开）实测两次同 seed 的出生点必须**逐位相同**，不相同就直接报错退出。

**难度旋钮也是从这里来的**：`placement_initializer.x_range / y_range` 默认只有
**±0.03 m**（6cm×6cm 的小盒子）—— 这解释了为什么手写状态机是 1.000：所有题目几乎一样。
把 range 加宽就是在制造「有的题会做、有的题不会」的 frontier，实测
range=[0.06,0.10] 时出生点确实落在 [0.066,0.100]。所以阶段 4 的采样轴不是"距离带"，
而是**出生盒子的位置/半径**，而且它是可控的 —— 这是 `SamplingPlan` 能挂上去的前提。

同时量三件必须量的事
    1. 可达上限：手写状态机的成功率（口径 = 环境真值 `_check_success()`）。
    2. 失败是否**结构化**：按环境真值分成 no_reach / reach_no_hold / grasp_no_lift /
       lifted_below / dropped / success，再叠上状态机停在哪个 phase。
       只有标签能区分「病因不同」，诊断层才有可作用的对象（§6.11 结论 4）。
    3. 成本：每局多少秒。这决定 6 臂 × 3 seed 的 A/B 到底可不可负担。

用法（state 观测，不需要渲染）：
    MUJOCO_GL=egl OMP_NUM_THREADS=1 /root/venvs/rlrobot/bin/python \
        scripts/probe_contact_ceiling.py --task lift --episodes 12 \
            --sac-ckpt runs/20260923_164831_sac_lift_state_shaped_demo5k/model_final.zip
    只想先看手写上限和成本：加 --skip-sac --episodes 3
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.env_factory import (PINNED_OBJECT_SEED, contact_object,  # noqa: E402
                                 contact_object_geom, make_contact_env,
                                 place_truth_fn, placement_leaves,
                                 reset_contact, seed_placement,
                                 set_spawn_half_range)

# rise 阈值（米）：**不能硬编码**。实测（2026-09-23，Lift，seed 1000~1011）手写状态机
# 在 `rise = +0.016 ~ +0.018` 时 `_check_success()` 就已经为真 —— 而 robosuite 文档口径
# 常被引成「高于桌面 0.04」。若照 0.04 硬编码，`lifted_below` 这一档会**永远为空**
# （成功在 0.016 就触发了），而 rise=0.03 的失败局会被误判成 `dropped`。
# 所以这里的两个常量只是**兜底**，正式口径由 `calibrate_rise()` 从成功局标定出来
# （和 `scripts/calibrate_perturbed.py` 同一条纪律：阈值要标定，不要猜）。
# 注意「标定量」本身随任务变：Lift 用 `rise_at_success`，PickPlace 用 `max_rise`
# （成功那一刻 can 坐在篮底，rise_at_success≈0，拿它标定会把阈值压成 1e-4）。
FALLBACK_RISE_SUCCESS = 0.04
FALLBACK_RISE_NEAR = 0.02
GRASP_WIDTH = 0.012      # 与 demo_scripted_lift_rs.py 实测口径一致：> 该值 = 指间有东西
REACH_XY = 0.03          # 末端与物体的水平距离小于此值算「够到了」


def placement(env):
    """拿到 `placement_initializer`。

    **注意它不一定是叶子 sampler**：Lift 是 `UniformRandomSampler`（叶子，`rng`/`x_range`
    直接生效），PickPlace 是 `SequentialCompositeSampler`（`sample()` 只遍历子 sampler，
    给它设 `rng`/`x_range` 都是**静默无效**）。要播种/改出生盒子请用
    `harness.env_factory.seed_placement` / `set_spawn_half_range`，它们按叶子操作。
    """
    pi = getattr(env._env, "placement_initializer", None)
    if pi is None or not hasattr(pi, "rng"):
        raise RuntimeError("环境没有可控的 placement_initializer.rng，无法保证出题可复现")
    return pi


def set_spawn_range(env, half_range: float | None, task: str = "lift") -> int:
    """设定物体出生盒子（正方形，半宽 half_range 米）。None = 用环境默认（±0.03）。

    返回实际改动的叶子数。以前这里直接写 `pi.x_range`，在 pickplace 上写的是 composite
    （没人读）⇒ `--spawn-range` / `--spawn-sweep` 空转、扫出来的"档位"全是默认盒子。
    """
    return set_spawn_half_range(env, half_range, task)


def reset_controlled(env, seed: int, flat_dim_ok: bool = True, task: str = "lift"):
    """可复现的 reset：物体出生位置**只**由 seed 决定（Lift / PickPlace 通用）。

    实现收在 `harness.env_factory.reset_contact`（唯一入口，K11 硬前置）：它先走包装层
    `reset(seed=...)` 重置记账并播种 `inner.rng`，再**按叶子**播种 placement sampler，
    然后重新 `inner.reset()`。Lift 的路径与历史产物逐位一致（单叶子 ⇒ `default_rng(seed)`）。
    """
    return reset_contact(env, seed)


def verify_seeding_legacy(env, seed: int = 12345, task: str = "lift") -> dict:
    """对照实验：**只**给 composite 播种（迁移前的做法）还能不能复现出题。

    留着它不是为了怀旧，而是为了证明修复是**承重的**：若哪天 robosuite 换了实现让
    旧写法也能复现，这一栏会变成 True，那时就该重新审视叶子播种是否还必要。
    Lift 上它本来就 True（initializer 即叶子），PickPlace 上实测 False。
    """
    from scripts.demo_scripted_lift_rs import _cube_pos

    spawns = []
    for _ in range(2):
        env.reset(seed=seed)
        placement(env).rng = np.random.default_rng(seed)   # 迁移前的写法
        env._env.reset()
        spawns.append(np.asarray(_cube_pos(env._env._get_observations()))[:2].copy())
    same = bool(np.array_equal(spawns[0], spawns[1]))
    return {"seed": seed, "task": task, "method": "composite_only(legacy)",
            "spawn_a": [round(float(v), 6) for v in spawns[0]],
            "spawn_b": [round(float(v), 6) for v in spawns[1]], "reproducible": same,
            "n_leaves": len(placement_leaves(env))}


def verify_seeding(env, seed: int = 12345, task: str = "lift", tries: int = 3) -> dict:
    """自校验：同 seed 两次受控 reset，出生点必须逐位相同。不同就直接失败。

    没有这一步，后面的逐题配对会安静地退化成配噪声（本次就是这么发现的）。
    `tries` 默认 3：两次相同可能是巧合（尤其出生盒子小的时候），三次逐位相同才算钉住。
    """
    from scripts.demo_scripted_lift_rs import _cube_pos
    spawns = []
    for _ in range(max(2, int(tries))):
        reset_controlled(env, seed, task=task)
        spawns.append(np.asarray(_cube_pos(env._env._get_observations()))[:2].copy())
    same = all(bool(np.array_equal(spawns[0], s)) for s in spawns[1:])
    return {"seed": seed, "task": task, "tries": len(spawns),
            "spawn_a": [round(float(v), 6) for v in spawns[0]],
            "spawn_b": [round(float(v), 6) for v in spawns[-1]],
            "spawns": [[round(float(v), 6) for v in s] for s in spawns],
            "n_leaves": len(placement_leaves(env)),
            "reproducible": same}


def make_env(task: str, horizon: int, reward_shaping: bool):
    return build_env(task, horizon, reward_shaping, PINNED_OBJECT_SEED)


def build_env(task: str, horizon: int, reward_shaping: bool, pin_object: int | None):
    """建环境。`pin_object` 非 None 时把 robosuite 构造期未播种的**物体尺寸随机化**钉死。

    不钉的后果（本轮实测，详见 `harness/env_factory.py::pinned_object_rng`）：每个进程建出的
    cube 尺寸都不同（半高 0.020175 vs 0.020347），初始 z 差 1.6 mm，接触动力学混沌放大 ⇒
    同一 ckpt + 同一 seed 在不同进程里给出 0/4、1/4、2/4 三种成绩。**跨进程的一切比较
    （包括"冻结评测"）在钉死之前都是无效的。**

    实现已收敛到 `harness.env_factory.make_contact_env`（K11：接触环境只有一个构造入口）。
    """
    return make_contact_env(task, horizon=horizon, reward_shaping=reward_shaping,
                            pin_seed=pin_object)


def object_geom_audit(env, task: str = "lift", pin_seed: int | None = None) -> dict:
    """记录**本进程实际在用的那个物体**的几何与质量。

    为什么必须有这一项：尺寸是构造期随机抽的（见 `build_env`），所以两个 run 的成功率
    能不能比，先要回答"是不是同一个 cube"。把几何写进产物，比较之前先比这一栏。

    实现收在 `harness.env_factory.contact_object_geom`：它按 `contact_object()` 取物体，
    pickplace 额外记篮筐真值（`bin_size` / `bin2_pos` / `target_bin_center`）。
    旧版按 `getattr(inner, "can")` 取 —— robosuite 1.5 的 PickPlace **没有** `.can`
    属性，于是这一栏在 pickplace 上全是 None（实测），跨 run 比较时无从核对。
    """
    return contact_object_geom(env, task, pin_seed)


def make_scripted(task: str, env, raw: dict):
    """构造对方的手写状态机（**只读 import，不修改他们的文件**）。"""
    if task == "lift":
        from scripts.demo_scripted_lift_rs import LiftStateMachine, _cube_pos
        return LiftStateMachine(cube_z0=float(_cube_pos(raw)[2])), _cube_pos
    from scripts.demo_scripted_pickplace import PickPlaceStateMachine
    inner = env._env
    # robosuite 1.5 的 PickPlace 只有 `bin1_pos` / `bin2_pos` / `bin_size`：
    # 既没有 `bin_poses`，也没有 `target_bin`（旧写法两个分支都会 AttributeError）。
    bin2 = np.asarray(inner.bin2_pos, dtype=np.float64)
    can_z0 = float(np.asarray(raw["Can_pos"], dtype=np.float64)[2])
    # 目标不是 bin2 的交点，而是 can 对应的**象限中心**（object_id=3）：直接放交点上
    # 会坐在篮墙上。用 robosuite 自己的真值表，与 demo_scripted_pickplace.py 保持一致。
    oid = int(getattr(inner, "object_id", 0))
    target_xy = np.asarray(inner.target_bin_placements, dtype=np.float64)[oid]

    def _obj_pos(obs: dict) -> np.ndarray:
        return np.asarray(obs["Can_pos"], dtype=np.float64)

    return PickPlaceStateMachine(bin2_pos=bin2, can_z0=can_z0, target_xy=target_xy), _obj_pos


def grasp_truth_fn(env, task: str):
    """用 robosuite **自己判成功用的那个 API** 问「真抓住了吗」，返回 callable 或 None。

    为什么要换掉宽度启发式：`robot0_gripper_qpos` 在**开局就是张开的**（|q|≈0.04），
    所以「width > 0.012 且离物体近」这个判据在策略根本没碰夹爪通道时**天然成立**。
    实测后果（runs/infra/probe_paired_lift.held_falsepositive.log）：SAC 10 局里 8 局
    `rise=0.000`（物体一动没动）却全被打成 `grasp_no_lift`（"夹住了但提不起来"）——
    标签把「从未尝试抓」说成「抓持力/姿态问题」，据此选采样轴或改奖励会全错。
    `_check_grasp` 要求左右两个 fingerpad 都与物体接触，是 lift.py 判 grasp 奖励的同一条真值。

    取物体走 `contact_object()`：pickplace 上 `getattr(inner, "can")` 是 None（robosuite 1.5
    没有这个属性），旧写法因此**静默退回宽度启发式** —— 也就是 §12.11-N 那个
    「弹一下算成功 / 从没抓也被打成 grasp_no_hold」的误判源头，在 pickplace 上会原样复现。
    """
    inner = env._env
    try:
        obj = contact_object(env, task)
    except RuntimeError:
        obj = None
    if obj is None or not hasattr(inner, "_check_grasp"):
        return None
    gripper = inner.robots[0].gripper

    def fn() -> bool | None:
        try:
            return bool(inner._check_grasp(gripper=gripper, object_geoms=obj))
        except Exception:                      # 真值不可用时宁可退回启发式，也不要抛
            return None

    return fn


class ScriptedAdapter:
    """把「只吃 raw obs 的状态机」适配成 `run_one` 的 `controller(raw, flat)`，并透出 `.phase/.log`。

    存在的唯一理由：状态机的 `cube_z0` 必须来自**本局**的出生点。之前 sweep 分支在
    `run_one`（内部会 `reset_controlled`）**之前**就用旧 obs 建了状态机，于是 z0 拿到的是
    上一局结束时（物体被举高）的高度 → `lift` 段的 `cube[2] > cube_z0 + LIFT_TARGET`
    永远不成立，扫描出来的"上限"是控制器时序 bug 而不是物理难度。
    """

    def __init__(self, sm) -> None:
        self.sm = sm

    def __call__(self, raw, flat):
        return self.sm(raw)

    @property
    def phase(self):
        return getattr(self.sm, "phase", None)

    @property
    def log(self) -> list:
        return list(getattr(self.sm, "log", []) or [])

    @property
    def z0(self):
        return getattr(self.sm, "cube_z0", getattr(self.sm, "can_z0", None))


def make_scripted_factory(task: str, env):
    """返回 `factory(raw) -> controller`：每局在受控 reset **之后**才新建状态机。"""

    def factory(raw: dict):
        sm, _ = make_scripted(task, env, raw)
        return ScriptedAdapter(sm)

    return factory


def calibrate_rise(rows: list[dict], task: str = "lift") -> dict:
    """从成功局标定「算不算真的把物体提起来了」这条线（`lift_ok` / `near`）。

    返回 `{"rise_ref", "lift_ok", "near", "n_success_used", "source", ...}`。
    `lift_ok` 取标定量最小值的 0.8 倍：只要某局的最高 rise 到过这条线，就说明它
    **真的把物体提起来了**，之后的失败属于「提起来又丢了/没搬到位」，而不是「没提起」。
    没有成功样本时退回兜底常量，并在 `source` 里写明 —— 兜底值不可信，必须在报告里露出来。

    **标定量随任务变**（pickplace 上曾静默塌掉，实测 2026-09-24）：

    - Lift 用 `rise_at_success`（成功那一刻物体的高度）。Lift 的成败**就是**高度，
      所以成功那一刻的 rise 天然给出「提多高才算成功」的下界，实测 +0.016~+0.018 m
      （远低于常被引用的 0.04，这也是 `FALLBACK_RISE_SUCCESS` 只能当兜底的原因）。
    - PickPlace **不能**用 `rise_at_success`：成功那一刻 can 正坐在篮底，而篮底与桌面
      几乎等高 ⇒ 实测 23 个成功局的 `rise_at_success` 有 19 个是 +0.0001~+0.0003 m
      （最小 +0.0001）。它和「有没有把 can 提起来」毫无因果。用它标定会得到
      `lift_ok = 1e-4`，于是"真抓住但只离桌 5 mm"的局被贴成 `lift_no_carry`
      （提起来了没搬过去），把**力/姿态问题**误报成**搬运段问题** —— 据此去改水平
      位移的奖励/采样，方向是反的。改用 `max_rise`（整局物体到过的最高点）的最小值
      ×0.8：语义变成「成功局里最省力的那次也至少把 can 提到过这么高」，实测
      `min(max_rise)=0.0816 ⇒ lift_ok=0.0653`，仍是数据标定、没有引入魔法数字。

    两种口径都写在产物里（`calibration_basis` + 对应的 min/max 区间），报告可复核。
    """
    pickplace = str(task).lower() == "pickplace"
    basis = "max_rise" if pickplace else "rise_at_success"
    ok = [r[basis] for r in rows if r.get("success") and r.get(basis) is not None]
    if not ok:
        out = {"rise_ref": None, "lift_ok": FALLBACK_RISE_SUCCESS, "near": FALLBACK_RISE_NEAR,
               "n_success_used": 0, "source": "fallback（没有成功样本，阈值不可信）"}
        if pickplace:
            out["calibration_basis"] = basis
        return out
    ref = float(min(ok))
    span_key = "max_rise_min_max" if pickplace else "rise_at_success_min_max"
    out = {"rise_ref": round(ref, 4), "lift_ok": round(0.8 * ref, 4), "near": round(0.5 * ref, 4),
           "n_success_used": len(ok),
           span_key: [round(float(min(ok)), 4), round(float(max(ok)), 4)],
           "source": "calibrated"}
    if pickplace:
        out["calibration_basis"] = basis
    return out


def classify(track: dict, cal: dict, task: str = "lift") -> str:
    """按环境真值给失败打结构化标签。顺序即优先级：先认成功，再认「曾经拿到又丢了」。

    标签 = 失败发生在**哪一段**，每段对应不同的修法，所以段与段之间不能混。

    Lift（`task="lift"`，历史口径，逐字未改）：
        no_reach        接近段：末端根本没到物体旁边      -> 位姿表征/探索范围问题
        reach_no_close  到了但**从没下发闭合指令**        -> 夹爪动作通道没被学会用
        reach_no_hold   下发了闭合却没夹住（真值 grasp=False）-> 时机/对准问题
        grasp_no_lift   真抓住了却提不起来                -> 力/姿态/提升段问题
        lifted_below    提起来了但没过成功判定线          -> 差一点，阈值敏感
        dropped         起来过又掉了                      -> 抓持保持问题

    PickPlace（`task="pickplace"`）：Lift 那套标签在放置段是**瞎的** —— 它最细只到
    「提起来了没有」，而 PickPlaceCan 的成败在**放置段**。所以这里按环境真值把梯子往下接三段：
        in_bin_no_success  can 真的进过篮（`not_in_bin==False`）却没判成功
                           -> 卡在成功判据的第二半（`r_reach<0.6`，即没松手退开）或进去又弹出来
        above_bin_no_drop  can 到过篮子上方象限但从未落进篮 -> 下降/释放时机
        lift_no_carry      真抓住且提起来了，但从没搬到篮上方 -> 搬运段（水平位移）
    再往下（grasp_no_lift / no_reach / reach_no_close / reach_no_hold）与 Lift 同义。
    `held` 只认 robosuite 的 `_check_grasp` 真值（见 `grasp_truth_fn`）；真值不可用时
    退回「必须先真的闭合过」的宽度启发式，并在 `held_source` 里写明用了哪个。
    """
    if track["success"]:
        # 「成功」只由高度阈值判定（robosuite `_check_success`），**不要求真抓住**。
        # 实测（2026-09-23，Lift，钉死物体尺寸后）：最弱那档 SAC（无示范）的两个成功局
        # 都是 **16 步**、末端离物体 2.6~2.8 cm、`_check_grasp` 全程为假 —— 开局就下发
        # 闭合指令，指间把 cube **弹起**越过高度阈值。所以成功必须再分一档，
        # 否则「成功率」会把"弹一下"和"真抓起来"算成同一件事（那一档的真实抓起率是 0/6）。
        return "success" if track.get("held") else "success_flick"
    if str(task).lower() == "pickplace":
        if track.get("ever_in_bin"):
            return "in_bin_no_success"       # 放进去了但没被判成功 —— 判据第二半/又弹出来
        if track.get("ever_above_bin"):
            return "above_bin_no_drop"       # 到过篮子上方但没落进去 —— 下降/释放段
        if track.get("held"):
            if track["max_rise"] >= cal["lift_ok"]:
                return "lift_no_carry"       # 提起来了但没搬过去 —— 搬运段
            return "grasp_no_lift"           # 夹住了但提不起来 —— 力/姿态问题
        if track["min_xy"] is None or track["min_xy"] > REACH_XY:
            return "no_reach"
        if float(track.get("close_cmd_frac") or 0.0) <= 0.0:
            return "reach_no_close"
        return "reach_no_hold"
    if track["max_rise"] >= cal["lift_ok"]:
        return "dropped"                 # 起来过又掉了 —— 抓持/搬运问题
    if track["held"]:
        if track["max_rise"] >= cal["near"]:
            return "lifted_below"        # 起来了但没过判定线 —— 差一点
        return "grasp_no_lift"           # 夹住了但提不起来 —— 力/姿态问题
    if track["min_xy"] is None or track["min_xy"] > REACH_XY:
        return "no_reach"                # 根本没到物体旁边 —— 接近段问题
    if float(track.get("close_cmd_frac") or 0.0) <= 0.0:
        return "reach_no_close"          # 到了但从没让夹爪闭合 —— 动作通道没学会
    return "reach_no_hold"               # 闭合了却没夹住 —— 时机/对准问题


def run_one(env, task: str, controller, seed: int, horizon: int,
            stop_on_success: bool = True, cal: dict | None = None,
            controller_factory=None) -> dict:
    """跑一局，逐步记录真值信号。controller(raw, flat) -> 7 维 action。

    `controller_factory(raw) -> controller`：给了它就在受控 reset **之后**用本局真值 obs
    现场建控制器（手写状态机必须走这条路，见 `ScriptedAdapter` 的说明）；此时 `controller`
    传 None 即可。SAC 那种无状态策略不需要，直接传 `controller`。

    `stop_on_success` 默认开：包装层的 `step()` 恒返回 `terminated=False`
    （`envs/robosuite_pickplace.py` 只在 `done` 时截断），所以成功后还会白跑满 horizon。
    Lift 一局只有一个 task，首次成功就已决定这一局的结局，继续跑纯粹是烧 MuJoCo 时间
    （实测 110 s/局里大部分是成功后的空转；对方的示范采集平均只用 83 步/局 = 同一个道理）。
    要做「一局多 task」的口径（transport 那种）时必须关掉它。
    """
    flat = reset_controlled(env, seed, task=task)
    raw = env._env._get_observations()
    if controller_factory is not None:
        controller = controller_factory(raw)
    from scripts.demo_scripted_lift_rs import _cube_pos
    obj_pos_fn = _cube_pos if task == "lift" else (lambda o: np.asarray(o["Can_pos"], dtype=np.float64))

    obj0 = obj_pos_fn(raw)
    z0 = float(obj0[2])
    grasp_fn = grasp_truth_fn(env, task)
    place_fn = place_truth_fn(env, task)     # Lift 返回 None；PickPlace 给篮筐真值
    width0 = float(np.max(np.abs(np.asarray(raw["robot0_gripper_qpos"], dtype=np.float64))))
    track = {"seed": seed, "spawn_xy": [round(float(obj0[0]), 4), round(float(obj0[1]), 4)],
             "spawn_z0": round(z0, 4),
             "success": False, "success_step": None, "rise_at_success": None,
             "min_xy": float("inf"), "max_rise": 0.0, "final_rise": 0.0,
             "held": False, "grasp_step": None, "steps": 0, "phases": [], "phase_at_end": "",
             "held_source": "truth(_check_grasp)" if grasp_fn else "fallback(width)",
             "width_open0": round(width0, 4), "min_width": round(width0, 4),
             "close_cmd_steps": 0, "open_cmd_steps": 0,
             # 放置段真值（只有 pickplace 会被填；见 place_truth_fn）：
             # 分开记「到过篮上方 / 真进过篮 / 进篮时末端离物体多远」，
             # 才能把「从没放进去」和「放进去了但没松手退开（判据第二半）」区分开。
             "ever_above_bin": False, "ever_in_bin": False, "steps_in_bin": 0,
             "min_bin_dist": None, "min_r_reach_in_bin": None, "open_cmd_above_bin": 0}
    t0 = time.time()
    for t in range(horizon):
        action = controller(raw, flat)
        flat, _r, term, trunc, info = env.step(action)
        raw = env._env._get_observations()
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        obj = obj_pos_fn(raw)
        dxy = float(np.linalg.norm(eef[:2] - obj[:2]))
        track["min_xy"] = min(track["min_xy"], dxy)
        rise = float(obj[2]) - z0
        track["max_rise"] = max(track["max_rise"], rise)
        track["final_rise"] = rise
        width = float(np.max(np.abs(np.asarray(raw["robot0_gripper_qpos"], dtype=np.float64))))
        track["min_width"] = round(min(track["min_width"], width), 4)
        grip_cmd = float(np.asarray(action, dtype=np.float64).reshape(-1)[-1])
        if grip_cmd > 0.0:
            track["close_cmd_steps"] += 1        # OSC_POSE 第 7 维：+1 闭合 / -1 张开
        else:
            track["open_cmd_steps"] += 1
        # `_check_grasp` 每步调用会把每局从 4.2 s 拖到 15.3 s（它要遍历 sim 全部接触对
        # 并做 geom 名字解析）。两个门控在物理上无损：真抓住时末端与物体的水平距离必然
        # 很小；一旦已经抓住过，后面只需知道「抓住过」，不必再问。
        if grasp_fn is not None:
            if not track["held"] and dxy < 0.06 and grasp_fn():
                track["held"] = True
                track["grasp_step"] = t + 1
        elif width > GRASP_WIDTH and width < track["width_open0"] - 0.005 and dxy < 0.06:
            track["held"] = True                 # 退回启发式：必须先真的闭合过
            track["grasp_step"] = track["grasp_step"] or t + 1
        if place_fn is not None:
            pt = place_fn()                      # 每步都问得起：它不扫接触对（不像 _check_grasp）
            if pt["above_bin"]:
                track["ever_above_bin"] = True
            if pt["in_bin"]:
                track["ever_in_bin"] = True
                track["steps_in_bin"] += 1
                if track["min_r_reach_in_bin"] is None or pt["r_reach"] < track["min_r_reach_in_bin"]:
                    track["min_r_reach_in_bin"] = pt["r_reach"]
            if track["min_bin_dist"] is None or pt["dist_target"] < track["min_bin_dist"]:
                track["min_bin_dist"] = pt["dist_target"]
            if grip_cmd < 0.0 and pt["above_bin"]:
                track["open_cmd_above_bin"] += 1   # 在篮上方下过张开指令 = 至少尝试了释放
        if info.get("success") and not track["success"]:
            track["success"] = True
            track["success_step"] = t + 1
            track["rise_at_success"] = round(rise, 4)   # Lift 的标定量（见 calibrate_rise）
        track["steps"] = t + 1
        if track["success"] and stop_on_success:
            break
        phase = getattr(controller, "phase", None) or getattr(controller, "_phase", None)
        if phase and (not track["phases"] or track["phases"][-1] != phase):
            track["phases"].append(phase)
        if term or trunc:
            break
    track["phase_at_end"] = track["phases"][-1] if track["phases"] else ""
    log = getattr(controller, "log", None)
    if log:                       # 状态机自己的相位日志才是权威（循环里记的会漏掉成功那一步）
        track["phases"] = list(log)
        track["phase_at_end"] = track["phases"][-1]
    z0_ctrl = getattr(controller, "z0", None)
    if z0_ctrl is not None:       # 审计用：控制器认定的初始高度必须等于本局出生高度
        track["ctrl_z0"] = round(float(z0_ctrl), 4)
        track["z0_matches_spawn"] = bool(abs(float(z0_ctrl) - z0) < 1e-3)
    track["close_cmd_frac"] = round(track["close_cmd_steps"] / max(1, track["steps"]), 3)
    track["success_grasp"] = bool(track["success"] and track["held"])
    track["success_kind"] = ("grasp" if track["success_grasp"]
                             else ("flick" if track["success"] else "fail"))
    track["min_xy"] = round(track["min_xy"], 4) if np.isfinite(track["min_xy"]) else None
    track["max_rise"] = round(track["max_rise"], 4)
    track["final_rise"] = round(track["final_rise"], 4)
    track["wall_sec"] = round(time.time() - t0, 2)
    track["label"] = classify(track, cal or {"lift_ok": FALLBACK_RISE_SUCCESS,
                                             "near": FALLBACK_RISE_NEAR}, task)
    return track


def grid_report(rows: list[dict], grid: int) -> list[dict]:
    """按物体出生位置 (x, y) 分格，给出每格的成功率 —— 这就是 SamplingPlan 要挂的坐标轴。"""
    if not rows:
        return []
    xs = np.array([r["spawn_xy"][0] for r in rows])
    ys = np.array([r["spawn_xy"][1] for r in rows])
    xe = np.linspace(xs.min(), xs.max() + 1e-9, grid + 1)
    ye = np.linspace(ys.min(), ys.max() + 1e-9, grid + 1)
    cells = []
    for i in range(grid):
        for j in range(grid):
            m = (xs >= xe[i]) & (xs < xe[i + 1]) & (ys >= ye[j]) & (ys < ye[j + 1])
            n = int(m.sum())
            if not n:
                continue
            sub = [r for r, keep in zip(rows, m) if keep]
            cells.append({
                "x_range": [round(float(xe[i]), 3), round(float(xe[i + 1]), 3)],
                "y_range": [round(float(ye[j]), 3), round(float(ye[j + 1]), 3)],
                "n": n,
                "success": round(sum(r["success"] for r in sub) / n, 3),
                "labels": {lab: sum(1 for r in sub if r["label"] == lab)
                           for lab in sorted({r["label"] for r in sub})},
            })
    return sorted(cells, key=lambda c: -c["n"])


def truth_consistency(rows: list[dict], fail_above: float = 0.5) -> dict:
    """自校验 +「弹起式成功」计量（**三态**，不再是"有就 FAIL"）。

    原判据是「成功 ⇒ 必然真抓住过」，这条前提已被实测推翻：robosuite Lift 的
    `_check_success` 只看 cube 高度、不看抓握，所以指间把 cube 弹过阈值也算成功
    （16 步、末端离物体 2.6 cm、`_check_grasp` 全程为假）。分三档：
      · flick_frac == 0        -> ok   成功都由真抓起完成；
      · 0 < flick_frac < 0.5   -> warn 存在弹起式成功 ⇒ **成功率被高估**，但失败标签仍
                                    可信（失败标签只依赖 held / min_xy / max_rise）；
      · flick_frac >= 0.5      -> fail 多数"成功"不是抓起来的 ⇒ 成功率不能当学习信号，
                                    必须改用 `success_rate_grasp_verified`；也可能是
                                    `_check_grasp` 口径接错（对象/geom 组不对）。
                                    两种都要先查清楚再往下走。
    """
    ok = [r for r in rows if r.get("success")]
    bad = [r["seed"] for r in ok if not r.get("held")]
    frac = (len(bad) / len(ok)) if ok else 0.0
    status = "fail" if (ok and frac >= fail_above) else ("warn" if bad else "ok")
    interp = {
        "ok": "所有成功局都有两指抓取真值 ⇒ 成功率可信",
        "warn": (f"{len(bad)}/{len(ok)} 个成功局没有抓取真值（弹起式成功）⇒ 成功率被高估，"
                 f"报数时要同时给 grasp-verified 口径；失败标签不受影响"),
        "fail": (f"{len(bad)}/{len(ok)} 个成功局没有抓取真值 ⇒ 成功率主要由"
                 f"「弹一下」贡献，不能当学习信号；先查 `_check_grasp` 口径或改用"
                 f"grasp-verified 成功率"),
    }[status]
    return {"n_success": len(ok), "success_without_grasp": bad,
            "flick_frac": round(frac, 4), "status": status,
            "consistent": status != "fail",       # 兼容旧调用点：fail 才算"不可信"
            "interpretation": interp,
            "n_rows": len(rows),
            "success_rate_grasp_verified": round(
                sum(1 for r in rows if r.get("success") and r.get("held")) / len(rows), 4
            ) if rows else None,
            "held_source": (rows[0].get("held_source") if rows else None)}


def place_funnel(rows: list[dict], task: str = "pickplace") -> dict:
    """PickPlace 的**放置段漏斗**：抓到 → 提到篮上方 → 真进篮 → 判成功，逐级掉多少。

    为什么必须逐级看：`PickPlaceCan._check_success()` 是两个条件的**合取**——
    ① `not_in_bin(pos, object_id) == False`（can 在篮筐象限内、z 在篮底以上 0.1 m 内）；
    ② `r_reach = 1 − tanh(10·dist(eef_site, can)) < 0.6`（末端已离 can **> 4.23 cm**，
       也就是松手并退开了）。
    只报 success 率时，「从没放进去」和「放进去了但没退开」长得一模一样，而修法完全相反：
    前者是能力问题（搬运/释放段没学会，该改奖励与采样），后者是**评测口径**在挡
    （真实能力被系统性低估，此时任何 A/B 都在比噪声）。对方 100k 步四个臂全 0% 成功、
    而 shaped 臂 mean_reward 能到 12 —— 这两种解释给出的下一步是相反的，必须先分开。
    """
    if str(task).lower() != "pickplace":
        return {"task": task, "n": len(rows), "applicable": False}
    if not rows:
        return {"task": task, "n": 0, "applicable": True, "verdict": "没有样本"}
    n = len(rows)
    held = [r for r in rows if r.get("held")]
    above = [r for r in rows if r.get("ever_above_bin")]
    in_bin = [r for r in rows if r.get("ever_in_bin")]
    succ = [r for r in rows if r.get("success")]
    in_bin_no_succ = [r for r in in_bin if not r.get("success")]
    # 判据第二半在挡的：进过篮，但**在篮期间**末端从没退开到 4.23 cm 以外
    blocked = [r for r in in_bin_no_succ if (r.get("min_r_reach_in_bin") or 1.0) >= 0.6]
    tried_release = [r for r in above if int(r.get("open_cmd_above_bin") or 0) > 0]
    dists = [r["min_bin_dist"] for r in rows if r.get("min_bin_dist") is not None]
    out = {
        "task": task, "n": n, "applicable": True,
        "held": len(held), "ever_above_bin": len(above), "ever_in_bin": len(in_bin),
        "success": len(succ), "success_grasp": sum(1 for r in succ if r.get("held")),
        "held_frac": round(len(held) / n, 3),
        "above_bin_frac": round(len(above) / n, 3),
        "in_bin_frac": round(len(in_bin) / n, 3),
        "success_frac": round(len(succ) / n, 3),
        "in_bin_no_success_seeds": [r["seed"] for r in in_bin_no_succ],
        "blocked_by_reach_seeds": [r["seed"] for r in blocked],
        "open_cmd_above_bin_episodes": len(tried_release),
        "min_bin_dist_median": round(float(np.median(dists)), 4) if dists else None,
        "min_bin_dist_min": round(float(np.min(dists)), 4) if dists else None,
        "steps_in_bin_total": int(sum(r.get("steps_in_bin") or 0 for r in rows)),
        "criterion": {"in_bin": "not_in_bin(pos, object_id) == False",
                      "retreat": "r_reach = 1 - tanh(10*dist(eef,can)) < 0.6  (dist > 0.0423 m)"},
    }
    if not in_bin:
        out["verdict"] = (
            f"判据第一半从没被触发：can 一次都没进过篮筐象限（到过上方的 {len(above)}/{n} 局、"
            f"真抓住过 {len(held)}/{n} 局，最近离篮心 "
            f"{out['min_bin_dist_min']} m）⇒ 0% 是**能力问题**（搬运/释放段没学会），"
            "不是评测口径问题。下一步该改学习信号（放置段奖励/示范/采样），别去动成功判据。")
    elif not succ:
        out["verdict"] = (
            f"can 进过篮 {len(in_bin)}/{n} 局却 0 成功 ⇒ **判据第二半在挡**："
            f"{len(blocked)} 局在篮期间 r_reach 始终 ≥ 0.6（末端没退开到 4.23 cm 外）"
            "⇒ 真实能力被系统性低估。先确认策略是否会松手退开，再决定是判据太严还是"
            "释放段确实没学会；在这种状态下开 A/B 比的是噪声。")
    else:
        out["verdict"] = (
            f"{len(succ)}/{n} 成功；进过篮的 {len(in_bin)} 局里 {len(in_bin_no_succ)} 局没被判成功"
            f"（其中 {len(blocked)} 局卡在 r_reach）⇒ 两段判据都在起作用，"
            "报数时 success 与 success_grasp 两个口径一起给。")
    return out


def place_brief(row: dict, task: str) -> str:
    """逐局一行的放置段摘要（只有 pickplace 有内容，Lift 返回空串不打扰历史日志格式）。"""
    if str(task).lower() != "pickplace":
        return ""
    return (f" above={int(bool(row.get('ever_above_bin')))}"
            f" in_bin={int(bool(row.get('ever_in_bin')))}/{row.get('steps_in_bin') or 0}步"
            f" min_bin_d={row.get('min_bin_dist')}"
            f" r_reach@bin={row.get('min_r_reach_in_bin')}"
            f" open@bin={row.get('open_cmd_above_bin') or 0}")


def paired_frontier(scr: list[dict], sac: list[dict], grid: int) -> dict:
    """逐 seed 配对（同 seed = 同一道题），统计四类格子/题目的分布。"""
    by_seed_s = {r["seed"]: r for r in scr}
    pairs = [(by_seed_s[r["seed"]], r) for r in sac if r["seed"] in by_seed_s]
    if not pairs:
        return {"n_pairs": 0}
    both_ok = sum(1 for a, b in pairs if a["success"] and b["success"])
    only_scr = sum(1 for a, b in pairs if a["success"] and not b["success"])
    only_sac = sum(1 for a, b in pairs if b["success"] and not a["success"])
    both_bad = sum(1 for a, b in pairs if not a["success"] and not b["success"])
    n = len(pairs)
    return {
        "n_pairs": n,
        "both_success": both_ok,
        "scripted_only": only_scr,       # <- 可学但还没学会：针对性采样的目标区
        "sac_only": only_sac,            # <- 反常，需要查（多半是评测噪声）
        "both_fail": both_bad,           # <- 太难，采样在这里也学不到
        "frontier_frac": round(only_scr / n, 3),
        "too_hard_frac": round(both_bad / n, 3),
        "too_easy_frac": round(both_ok / n, 3),
        "note": "frontier = 手写成、SAC 不成。只有这一部分题目对「采样往哪儿放」敏感。",
    }


def axis_diagnosis(sac_rows: list[dict], grid: int, *, sec_per_episode: float,
                    budget_sec: float, delta: float = 0.30,
                    alpha: float = 0.05, power: float = 0.8) -> dict:
    """哪条难度轴**用得起**：不是问「哪条轴看起来有差异」，而是问「预算内判不判得出来」。

    两条候选轴：
      · `spatial` 物体出生格（grid×grid 个桶）。接触任务里它常常没有信号：本轮实测
        手写上限在出生半宽 ±0.03~±0.18（默认的 6 倍）上恒为 1.000（48/48），
        SAC 的失败也与出生位置无关（min_xy 已经小到 0.001~0.03 仍抓不住）。
      · `segment` 失败发生在哪一段（no_reach / reach_no_close / reach_no_hold /
        grasp_no_lift / lifted_below / dropped）。每段对应**不同的修法**，
        而且一局就能归类，桶数少、每桶局数多 ⇒ 便宜。

    判据用分辨率算术（`harness/sampling_design.py::min_detectable_effect`）：
    桶数为 k 时，要在桶间检出 δ，每桶需要 `required_episodes(δ)` 局，总成本
    = k × 每桶局数 × 每局墙钟。空间轴 grid=3 ⇒ k=9，成本直接 ×9；
    段落轴 k≈5，而且**当前样本已经能看出主导段**（不需要先跑满才有信息）。
    这就是「先量上限再烧预算」在轴选择上的具体形态。
    """
    from harness.sampling_design import min_detectable_effect, required_episodes
    n = len(sac_rows)
    labels: dict[str, int] = {}
    for row in sac_rows:
        labels[row["label"]] = labels.get(row["label"], 0) + 1
    dominant = max(labels, key=lambda k: labels[k]) if labels else None
    cells = [c for c in grid_report(sac_rows, grid) if c["n"] > 0]
    n_cells = max(len(cells), 1)
    per_bucket_obs = n / n_cells
    need_per_bucket = required_episodes(delta, 0.5, alpha=alpha, power=power)["unpaired_per_arm"]
    seg_k = max(len([k for k in labels if k != "success"]), 1)

    def axis(k: int, observed_per_bucket: float) -> dict:
        total_eps = k * need_per_bucket
        hours = total_eps * sec_per_episode / 3600.0
        return {"buckets": k,
                "observed_n_per_bucket": round(observed_per_bucket, 2),
                "mde_at_observed_n": round(min_detectable_effect(max(int(observed_per_bucket), 0)), 3),
                "episodes_per_bucket_for_delta": need_per_bucket,
                "total_episodes": total_eps,
                "total_hours": round(hours, 2),
                "decidable_within_budget": bool(hours * 3600.0 <= budget_sec),
                "delta": delta}

    out = {"n_episodes": n, "sec_per_episode": sec_per_episode,
           "budget_hours": round(budget_sec / 3600.0, 2),
           "labels": labels, "dominant_segment": dominant,
           "dominant_frac": round(labels.get(dominant, 0) / n, 3) if n and dominant else None,
           "spatial": axis(n_cells, per_bucket_obs),
           "segment": axis(seg_k, n / seg_k),
           "spatial_cells": cells}
    sp, sg = out["spatial"], out["segment"]
    if n == 0:
        out["verdict"] = "没有策略侧样本，无法判轴"
    elif sp["decidable_within_budget"] and sg["decidable_within_budget"]:
        out["verdict"] = ("两条轴在预算内都可判：优先用**段落轴**（桶少、每桶局数多、"
                          "且直接对应修法），空间轴留作泛化对照")
    elif sg["decidable_within_budget"]:
        out["verdict"] = (f"只有段落轴判得起（{sg['total_hours']} h）；空间轴要 "
                          f"{sp['total_hours']} h（{sp['buckets']} 桶 × "
                          f"{sp['episodes_per_bucket_for_delta']} 局 × {sec_per_episode} s）"
                          f"超预算 {out['budget_hours']} h ⇒ 当前每格只有 "
                          f"{sp['observed_n_per_bucket']} 局，MDE={sp['mde_at_observed_n']}，"
                          "任何格间差异都不可判定，**别说成「空间轴没有信号」**")
    else:
        out["verdict"] = (f"两条轴都判不起（段落 {sg['total_hours']} h / 空间 "
                          f"{sp['total_hours']} h > 预算 {out['budget_hours']} h）："
                          "先砍 δ（接受更粗的效应）、砍桶数，或换更便宜的环境")
    if out["dominant_frac"] is not None and out["dominant_frac"] >= 0.6:
        out["verdict"] += (f"；主导失败段 {dominant} 占 {out['dominant_frac']:.0%}"
                           " ⇒ 修这一段比调采样分布更可能改变结果")
    return out


def run_frontier_gate(rungs: list[dict], args, machine: dict | None = None) -> dict:
    """把探针实测行喂给 `harness/sampling_design.py::frontier_verdict`（§12.11 的门禁）。

    放在探针里而不是另开脚本，是因为门禁的输入**必须**是实测值：每局墙钟、手写上限、
    逐题配对的 frontier 占比。手写一份"看起来差不多"的档位表喂给门禁，等于自己给自己发证。
    """
    from harness.sampling_design import frontier_verdict
    gate = frontier_verdict(
        rungs, budget_sec=args.budget_hours * 3600.0, arms=args.arms, rounds=args.rounds,
        episodes_per_round=args.episodes_per_round, train_sec_per_round=args.train_sec_per_round,
        eval_episodes=args.eval_episodes, min_gain=args.min_gain,
        regression_tol=args.regression_tol, eval_every=args.eval_every,
        eval_sec_per_episode=args.eval_sec_per_episode)
    print("=" * 78)
    print(f"frontier 门禁（预算 {args.budget_hours:g} h · {args.arms} 臂 × {args.rounds} 轮 × "
          f"{args.episodes_per_round} 局 · 评测 {args.eval_episodes} 局 / min_gain "
          f"{args.min_gain:g} / 掉点容忍 {args.regression_tol:g}）")
    print("=" * 78)
    for rung in gate["rungs"]:
        mark = "通过" if rung["ok"] else "拒绝[" + "/".join(rung["failed"]) + "]"
        print(f"  档 {rung['half_range']}: {mark}"
              + (f" · 成本 {rung['cost_hours']} h · 预算内最多 {rung['affordable_arms_raw']} 臂"
                 if rung.get("cost_hours") is not None else ""))
        for reason in rung["reasons"]:
            print(f"      - {reason}")
    res = gate["checks"]["resolution"]
    print(f"  分辨率（全局）: {'OK' if res['ok'] else 'FAIL'} · {res['reason']}")
    print(f"  推荐档位: {gate['recommended']['half_range'] if gate['recommended'] else '无'}")
    for warn in gate["warnings"]:
        print(f"  [WARN] {warn}")
    machine = machine or {}
    load = (machine.get("loadavg") or [0.0])[0]
    ncpu = machine.get("cpu_count") or 1
    if load > 2 * ncpu:
        print(f"  [WARN] 成本数字是在 load={load:.0f}（{ncpu} 核）下量的，空载会快得多；"
              f"跨机器/跨时间比较前先用 steps_per_sec 归一：{ {r['half_range']: r.get('steps_per_sec') for r in rungs} }")
    print(f"  => 总判定: {'允许开 A/B' if gate['ok'] else '不允许开 A/B'}")
    return gate


def verdict(scr_rate: float, sac_rate: float | None, paired: dict, cost_sec: float) -> list[str]:
    out = []
    if scr_rate < 0.5:
        out.append(f"手写上限只有 {scr_rate:.2f} < 0.5 -> **先修控制器/栈**，"
                   f"现在谈 A/B 没有意义（连「成功长什么样」都没有可靠参照）")
    elif scr_rate >= 0.98:
        out.append(f"手写上限 {scr_rate:.2f} ≈ 满分 -> 上限侧饱和；"
                   f"A/B 是否可判定取决于 SAC 侧有没有爬升段")
    else:
        out.append(f"手写上限 {scr_rate:.2f} 在中间 -> 存在可测的爬升空间")
    if sac_rate is not None:
        if sac_rate <= 0.02:
            out.append(f"SAC 只有 {sac_rate:.2f} -> 全局成功率**没有分辨力**（阈值梯会全部 no_resolution，"
                       f"和 PickPlaceCan 的 0% 同病）；必须改用**条件成功率**（按出生格）做统计量")
        elif sac_rate >= 0.98:
            out.append(f"SAC 已 {sac_rate:.2f} -> 饱和陷阱（run1 / Reach-fullstate 同病），A/B 不可判定")
        else:
            out.append(f"SAC {sac_rate:.2f} 在爬升段内 -> 全局阈值梯可能有分辨力")
        ff = paired.get("frontier_frac")
        if ff is not None:
            if ff <= 0.05:
                out.append(f"frontier 只占 {ff:.1%} -> 针对性采样几乎无处发力，"
                           f"先降难度或加课程，别急着开 A/B")
            else:
                out.append(f"frontier 占 {ff:.1%}（{paired.get('scripted_only')}/{paired.get('n_pairs')} 题）"
                           f"-> 这就是 SamplingPlan 应该加权采样的区域；"
                           f"太难区占 {paired.get('too_hard_frac'):.1%}，太易区占 {paired.get('too_easy_frac'):.1%}")
    if cost_sec > 0:
        arms = 6
        out.append(f"成本：{cost_sec:.1f} s/局。若一条 A/B 臂要 60k 环境步、每轮 8 局采集，"
                   f"光采集就约 {cost_sec * 8 * 10 * arms / 3600:.1f} h（{arms} 臂 × 10 轮 × 8 局），"
                   f"还不含训练 —— 这个数字必须先看得下去再设计实验")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", default="lift", choices=["lift", "pickplace"])
    ap.add_argument("--episodes", type=int, default=12)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--reward-shaping", action="store_true")
    ap.add_argument("--grid", type=int, default=3, help="出生位置分格数（每边）")
    ap.add_argument("--spawn-range", type=float, default=None,
                    help="物体出生盒子半宽（米）。默认用环境的 ±0.03；加宽它就是在制造 frontier")
    ap.add_argument("--spawn-sweep", default="",
                    help="逗号分隔的半宽阶梯，只跑手写控制器逐档量上限，例如 0.03,0.06,0.09,0.12")
    ap.add_argument("--no-verify-seeding", action="store_true",
                    help="跳过「同 seed 出生点必须可复现」的自校验（不建议）")
    ap.add_argument("--no-pin-object", action="store_true",
                    help="不钉死物体尺寸随机化（复现旧的跨进程不可比行为，仅用于演示该混淆）")
    ap.add_argument("--pin-seed", type=int, default=PINNED_OBJECT_SEED,
                    help=f"钉死物体尺寸用的种子（默认 {PINNED_OBJECT_SEED}）。改它=换 cube=与历史数字不可比")
    ap.add_argument("--sac-ckpt", default="", help="SB3 .zip；给了就同时评它并逐题配对")
    ap.add_argument("--skip-scripted", action="store_true")
    ap.add_argument("--skip-sac", action="store_true")
    ap.add_argument("--no-stop-on-success", action="store_true",
                    help="成功后继续跑满 horizon（做多 task 口径时用）；默认首次成功就收，省 MuJoCo 时间")
    ap.add_argument("--out", default="")
    # 门禁参数：默认值**故意**取 harness 现在用的那一套（6 臂 / 10 轮 / 每轮 8 局 /
    # 评测 50 局 / min_gain 0.02），这样探针会直接把「这套配置在接触任务上买不起、
    # 且 50 局评测检不出 0.02」两件事指出来，而不是等人自己去算。
    ap.add_argument("--budget-hours", type=float, default=8.0, help="一条 A/B 允许的墙钟预算")
    ap.add_argument("--arms", type=int, default=6)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--episodes-per-round", type=int, default=8)
    ap.add_argument("--train-sec-per-round", type=float, default=0.0,
                    help="每轮训练的墙钟秒数（journal 的 train_seconds；不填就只算采集）")
    ap.add_argument("--eval-episodes", type=int, default=50)
    ap.add_argument("--min-gain", type=float, default=0.02)
    ap.add_argument("--regression-tol", type=float, default=0.0,
                    help="门禁允许的掉点容忍度（harness 现用 0.0 = 零容忍）")
    ap.add_argument("--eval-every", type=int, default=1, help="每几轮做一次正式评测")
    ap.add_argument("--eval-sec-per-episode", type=float, default=None,
                    help="评测每局墙钟（默认与采集同价；确定性评测通常更快）")
    args = ap.parse_args()

    pin = None if args.no_pin_object else int(args.pin_seed)
    env = build_env(args.task, args.horizon, args.reward_shaping, pin)
    obj_geom = object_geom_audit(env, args.task, pin)
    print(f"物体几何审计（跨 run 比较前先看这一栏）: pin_seed={pin} "
          f"object={obj_geom.get('object')} "
          f"bottom_offset={obj_geom.get('bottom_offset')} "
          f"horizontal_radius={obj_geom.get('horizontal_radius')} "
          f"mass={obj_geom.get('body_mass_kg')} kg", flush=True)
    if args.task != "lift":
        print(f"篮筐真值: bin_size={obj_geom.get('bin_size')} bin2_pos={obj_geom.get('bin2_pos')} "
              f"target_bin_center={obj_geom.get('target_bin_center')} "
              f"object_id={obj_geom.get('object_id')} obj_to_use={obj_geom.get('obj_to_use')}",
              flush=True)
    if obj_geom.get("error") or (obj_geom.get("body_mass_kg") is None
                                 and not obj_geom.get("body_mass_error")):
        print(f"[WARN] 物体几何审计不完整：{obj_geom.get('error') or obj_geom.get('body_mass_error')}"
              " ⇒ 跨 run 的成功率无法核对是不是同一个物体", file=sys.stderr, flush=True)
    n_spawn_leaves = set_spawn_range(env, args.spawn_range, args.task)
    if args.spawn_range is not None:
        print(f"出生盒子半宽设为 ±{args.spawn_range} m（改动 {n_spawn_leaves} 个叶子 sampler）",
              flush=True)
    seeds = [args.seed0 + i for i in range(args.episodes)]

    vs = vs_legacy = None
    if not args.no_verify_seeding:
        vs = verify_seeding(env, task=args.task)
        print(f"出题可复现自校验: seed={vs['seed']} · {vs['tries']} 次 · 叶子 {vs['n_leaves']} 个 · "
              f"出生点 {vs['spawns']} -> {'一致 OK' if vs['reproducible'] else '不一致 FAIL'}",
              flush=True)
        if not vs["reproducible"]:
            print("[ERR] 出生点不可复现 => 逐题配对无意义，拒绝继续。"
                  "检查 placement_initializer 的**叶子** sampler 是否被播种"
                  "（PickPlace 是 composite，给它自己设 rng 无效）。", file=sys.stderr)
            return 3
        vs_legacy = verify_seeding_legacy(env, task=args.task)
        print(f"  对照（迁移前只播种 composite.rng）: {vs_legacy['spawn_a']} / {vs_legacy['spawn_b']} "
              f"-> {'一致' if vs_legacy['reproducible'] else '不一致（说明叶子播种是承重的）'}",
              flush=True)
    result: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "machine": {"loadavg": [round(v, 1) for v in os.getloadavg()],
                    "cpu_count": os.cpu_count(),
                    "note": "sec_per_episode 必须和 loadavg 一起读：本机被第三方 ffmpeg 作业"
                            "压到 load>1000 时，同一局的墙钟会差一个量级"},
        "task": args.task, "horizon": args.horizon, "episodes": args.episodes,
        "stop_on_success": not args.no_stop_on_success,
        "spawn_range": args.spawn_range,
        "spawn_range_leaves_changed": n_spawn_leaves,
        "placement_leaves": len(placement_leaves(env)),
        "seeding_verified": (not args.no_verify_seeding),
        "object_geom": obj_geom,
        "seeds": [seeds[0], seeds[-1]], "grid": args.grid,
        "thresholds": {"grasp_width": GRASP_WIDTH, "reach_xy": REACH_XY,
                       "rise_fallback": [FALLBACK_RISE_SUCCESS, FALLBACK_RISE_NEAR],
                       "rise_note": "正式 rise 阈值由 rise_calibration 从成功样本标定"},
    }
    if vs is not None:
        # 逐位出生点必须进产物：McNemar 的前提是「同一道题」，这一栏是它唯一的证据。
        result["seeding_check"] = vs
        result["seeding_legacy_check"] = vs_legacy

    scripted_factory = make_scripted_factory(args.task, env)

    if args.spawn_sweep:
        ladder = [float(x) for x in args.spawn_sweep.split(",") if x.strip()]
        print("=" * 78)
        print(f"出生范围扫描（只跑手写控制器）· 每档 {args.episodes} 局 · 阶梯 {ladder}")
        print("=" * 78, flush=True)
        sweep = []
        for half in ladder:
            set_spawn_range(env, half)
            rows = []
            for seed in seeds:
                rows.append(run_one(env, args.task, None, seed, args.horizon,
                                    stop_on_success=not args.no_stop_on_success,
                                    controller_factory=scripted_factory))
            cal = calibrate_rise(rows, args.task)
            for row in rows:
                row["label"] = classify(row, cal, args.task)
            rate = sum(r["success"] for r in rows) / max(1, len(rows))
            spawn_r = float(np.max(np.abs(np.array([r["spawn_xy"] for r in rows]))))
            z0_bad = sum(1 for r in rows if r.get("z0_matches_spawn") is False)
            entry = {"half_range": half, "success_rate": round(rate, 4),
                     "mean_steps": round(float(np.mean([r["steps"] for r in rows])), 1),
                     "mean_wall_sec": round(float(np.mean([r["wall_sec"] for r in rows])), 2),
                     "labels": {k: sum(1 for r in rows if r["label"] == k)
                                for k in sorted({r["label"] for r in rows})},
                     "observed_spawn_absmax": round(spawn_r, 4),
                     "ctrl_z0_mismatch": z0_bad,
                     "rise_calibration": cal, "episodes": rows}
            sweep.append(entry)
            print(f"  半宽 {half:.3f} m（实测出生 |xy| 最大 {spawn_r:.3f}）: 手写上限 {rate:.3f} · "
                  f"{entry['mean_steps']:.0f} 步 · {entry['mean_wall_sec']:.1f} s/局 · "
                  f"标签 {entry['labels']}"
                  + (f" · [WARN] {z0_bad} 局控制器 z0 与出生点不符" if z0_bad else ""), flush=True)
        result["spawn_sweep"] = sweep
        for e in sweep:
            e["steps_per_sec"] = round(e["mean_steps"] / max(e["mean_wall_sec"], 1e-9), 2)
        result["frontier_gate"] = run_frontier_gate(
            [{"half_range": e["half_range"], "scripted_success": e["success_rate"],
              "sec_per_episode": e["mean_wall_sec"], "seeding_ok": True,
              "steps_per_sec": e["steps_per_sec"],
              "ctrl_z0_mismatch": e.get("ctrl_z0_mismatch", 0)} for e in sweep],
            args, result["machine"])
        ok = [e["half_range"] for e in sweep if e["success_rate"] >= 0.98]
        bad = [e["half_range"] for e in sweep if e["success_rate"] < 0.5]
        mid = [e["half_range"] for e in sweep if 0.05 <= e["success_rate"] < 0.98]
        result["sweep_verdict"] = {
            "handwritten_saturated_up_to": max(ok) if ok else None,
            "handwritten_collapses_at": min(bad) if bad else None,
            "usable_middle_rungs": mid,
            "text": ("手写上限在 <= %.3f m 都满分 => 这一段没有可诊断的失败；"
                     "候选难度档是 %s" % (max(ok) if ok else float("nan"), mid or "无"))
                    if ok else "没有任何一档让手写满分，先修控制器",
        }
        print("-" * 78)
        print(f"  扫描判定: {result['sweep_verdict']['text']}", flush=True)
        out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
            f"{time.strftime('%Y%m%d_%H%M%S')}_contact_sweep_{args.task}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float),
                       encoding="utf-8")
        print(f"已写出: {out}")
        env.close()
        return 0

    scr_rows: list[dict] = []
    if not args.skip_scripted:
        print("=" * 78)
        print(f"手写状态机上限 · task={args.task} · {args.episodes} 局 · horizon={args.horizon}")
        print("=" * 78, flush=True)
        for seed in seeds:
            row = run_one(env, args.task, None, seed, args.horizon,   # 每局现场新建状态机
                          stop_on_success=not args.no_stop_on_success,
                          controller_factory=scripted_factory)
            scr_rows.append(row)
            print(f"  seed {seed} spawn={row['spawn_xy']} success={int(row['success'])} "
                  f"步={row['steps']:3d} rise={row['max_rise']:+.3f} min_xy={row['min_xy']} "
                  f"label={row['label']:14s} phase={row['phase_at_end']:12s} "
                  f"grasp={int(row['held'])}@{row['grasp_step']} close={row['close_cmd_frac']:.2f} "
                  f"w={row['min_width']:.3f}/{row['width_open0']:.3f} {row['wall_sec']}s"
                  f"{place_brief(row, args.task)}",
                  flush=True)
        # 必须带 task：pickplace 的成功局 rise_at_success≈0（can 坐在篮底），
        # 按 lift 口径标定会得到 lift_ok=1e-4，把「抓不住/提不起」误贴成「搬运段」。
        cal = calibrate_rise(scr_rows, args.task)
        for row in scr_rows:                 # 用标定后的阈值重打标签
            # 必须带 task：pickplace 的失败梯子在放置段（in_bin_no_success /
            # above_bin_no_drop / lift_no_carry），漏传就退回 Lift 口径、把
            # 「搬不到篮上方」说成「起来过又掉了」，据此选修法会全错。
            row["label"] = classify(row, cal, args.task)
        print(f"  rise 阈值标定: {json.dumps(cal, ensure_ascii=False)}", flush=True)
        tc = truth_consistency(scr_rows)
        result["grasp_truth_check"] = tc
        print(f"  抓取真值自校验[{tc['status'].upper()}]: {tc['held_source']} · "
              f"成功 {tc['n_success']} 局中 {len(tc['success_without_grasp'])} 局无抓取真值"
              f"（flick_frac={tc['flick_frac']}）\n      {tc['interpretation']}", flush=True)
        if tc["status"] != "ok":
            print(f"  [{tc['status'].upper()}] 弹起式成功 seed={tc['success_without_grasp']}："
                  f"grasp-verified 成功率={tc['success_rate_grasp_verified']}", flush=True)
        rate = sum(r["success"] for r in scr_rows) / max(1, len(scr_rows))
        result["rise_calibration"] = cal
        funnel_scr = place_funnel(scr_rows, args.task)
        if funnel_scr.get("applicable"):
            print(f"  放置段漏斗[手写]: 抓 {funnel_scr['held']}/{funnel_scr['n']} → "
                  f"到篮上方 {funnel_scr['ever_above_bin']} → 真进篮 {funnel_scr['ever_in_bin']} → "
                  f"判成功 {funnel_scr['success']}\n      {funnel_scr['verdict']}", flush=True)
        result["scripted"] = {
            "success_rate": round(rate, 4),
            "success_rate_grasp_verified": tc["success_rate_grasp_verified"],
            "flick_frac": tc["flick_frac"],
            "place_funnel": funnel_scr,
            "mean_steps": round(float(np.mean([r["steps"] for r in scr_rows])), 1),
            "mean_wall_sec": round(float(np.mean([r["wall_sec"] for r in scr_rows])), 2),
            "labels": {k: sum(1 for r in scr_rows if r["label"] == k)
                       for k in sorted({r["label"] for r in scr_rows})},
            "phases_at_end": {k: sum(1 for r in scr_rows if r["phase_at_end"] == k)
                              for k in sorted({r["phase_at_end"] for r in scr_rows})},
            "spawn_grid": grid_report(scr_rows, args.grid),
            "episodes": scr_rows,
        }
        print(f"  -> 手写上限 {rate:.3f} · 标签 {result['scripted']['labels']} · "
              f"{result['scripted']['mean_wall_sec']} s/局", flush=True)

    sac_rows: list[dict] = []
    if args.sac_ckpt and not args.skip_sac:
        ckpt = Path(args.sac_ckpt)
        ckpt = ckpt if ckpt.is_absolute() else REPO_ROOT / ckpt
        if not ckpt.exists():
            print(f"[ERR] 找不到 ckpt: {ckpt}", file=sys.stderr)
            return 2
        from scripts.eval_policy import load_any_policy
        model, algo = load_any_policy(str(ckpt))
        # 阈值口径必须和手写臂一致，否则两臂的失败标签不可比。
        cal_use = result.get("rise_calibration") or calibrate_rise([], args.task)
        if cal_use.get("source", "").startswith("fallback"):
            print("  [WARN] 没有手写臂的成功样本可标定，rise 阈值退回兜底值，"
                  "失败标签仅供参考", flush=True)
        print("=" * 78)
        print(f"冻结 SAC（{algo}）· 同一批 seed ⇒ 与手写逐题配对")
        print("=" * 78, flush=True)
        for seed in seeds:
            ctrl = lambda raw, flat, _m=model: np.asarray(_m.predict(flat, deterministic=True)[0],
                                                          dtype=np.float64).reshape(-1)
            row = run_one(env, args.task, ctrl, seed, args.horizon,
                          stop_on_success=not args.no_stop_on_success, cal=cal_use)
            sac_rows.append(row)
            print(f"  seed {seed} spawn={row['spawn_xy']} success={int(row['success'])} "
                  f"步={row['steps']:3d} rise={row['max_rise']:+.3f} min_xy={row['min_xy']} "
                  f"label={row['label']:14s} grasp={int(row['held'])}@{row['grasp_step']} "
                  f"close={row['close_cmd_frac']:.2f} {row['wall_sec']}s"
                  f"{place_brief(row, args.task)}", flush=True)
        rate = sum(r["success"] for r in sac_rows) / max(1, len(sac_rows))
        tc_sac = truth_consistency(sac_rows)
        result["sac_grasp_truth_check"] = tc_sac
        funnel_sac = place_funnel(sac_rows, args.task)
        if funnel_sac.get("applicable"):
            print(f"  放置段漏斗[SAC]: 抓 {funnel_sac['held']}/{funnel_sac['n']} → "
                  f"到篮上方 {funnel_sac['ever_above_bin']} → 真进篮 {funnel_sac['ever_in_bin']} → "
                  f"判成功 {funnel_sac['success']}\n      {funnel_sac['verdict']}", flush=True)
            result["place_funnel"] = funnel_sac
        print(f"  SAC 抓取真值自校验[{tc_sac['status'].upper()}]: 成功 {tc_sac['n_success']} 局中 "
              f"{len(tc_sac['success_without_grasp'])} 局无抓取真值"
              f"（flick_frac={tc_sac['flick_frac']}）\n      {tc_sac['interpretation']}",
              flush=True)
        result["sac"] = {
            "ckpt": str(ckpt), "algo": algo,
            "success_rate": round(rate, 4),
            "success_rate_grasp_verified": tc_sac["success_rate_grasp_verified"],
            "flick_frac": tc_sac["flick_frac"],
            "place_funnel": funnel_sac,
            "labels": {k: sum(1 for r in sac_rows if r["label"] == k)
                       for k in sorted({r["label"] for r in sac_rows})},
            "spawn_grid": grid_report(sac_rows, args.grid),
            "episodes": sac_rows,
        }
        print(f"  -> SAC {rate:.3f} · 标签 {result['sac']['labels']}", flush=True)

    if scr_rows and sac_rows:
        result["paired"] = paired_frontier(scr_rows, sac_rows, args.grid)
        print("-" * 78)
        print(f"  逐题配对（{result['paired']['n_pairs']} 题）: "
              f"两者都成 {result['paired']['both_success']} · "
              f"**只手写成 {result['paired']['scripted_only']}** · "
              f"只 SAC 成 {result['paired']['sac_only']} · "
              f"都不成 {result['paired']['both_fail']}", flush=True)

    paired = result.get("paired", {})
    if sac_rows:
        sec_sac = float(np.mean([r["wall_sec"] for r in sac_rows]))
        result["axis_diagnosis"] = axis_diagnosis(
            sac_rows, args.grid, sec_per_episode=sec_sac,
            budget_sec=args.budget_hours * 3600.0)
        ad = result["axis_diagnosis"]
        print("-" * 78)
        print(f"  难度轴诊断: 标签 {ad['labels']} · 主导段 {ad['dominant_segment']} "
              f"({ad['dominant_frac']})")
        print(f"  空间轴 {ad['spatial']['buckets']} 桶 → 每桶只有 "
              f"{ad['spatial']['observed_n_per_bucket']} 局（MDE {ad['spatial']['mde_at_observed_n']}），"
              f"判 δ={ad['spatial']['delta']} 需 {ad['spatial']['total_hours']} h")
        print(f"  段落轴 {ad['segment']['buckets']} 桶 → 判同一 δ 需 "
              f"{ad['segment']['total_hours']} h")
        print(f"  => {ad['verdict']}", flush=True)
    rung = {"half_range": (args.spawn_range if args.spawn_range is not None else 0.03),
            "scripted_success": result.get("scripted", {}).get("success_rate"),
            "sac_success": result.get("sac", {}).get("success_rate"),
            "frontier_frac": paired.get("frontier_frac"),
            "too_hard_frac": paired.get("too_hard_frac"),
            "seeding_ok": bool(result.get("seeding_verified")),
            "ctrl_z0_mismatch": sum(1 for r in scr_rows if r.get("z0_matches_spawn") is False)}
    # 门禁**支持**但以前没人填的三个字段（和 §7 第 26 条同一类断链：规则写了、输入永远缺，
    # 于是"物体未钉死 ⇒ 整档作废"和"弹起式成功 ⇒ 指标不可用"两条规则从没真正触发过，
    # 反而一直报"产物没有 object_geom"这个假警告）：
    rung["object_pinned"] = bool(pin is not None)
    rung["object_geom"] = obj_geom
    rung["flick_frac"] = result.get("sac", {}).get("flick_frac")
    rung["success_rate_grasp_verified"] = result.get("sac", {}).get("success_rate_grasp_verified")
    rung["scripted_flick_frac"] = result.get("scripted", {}).get("flick_frac")
    sec_all = [r["wall_sec"] for r in (sac_rows or scr_rows)]      # 成本按**贵的那一臂**算
    rung["sec_per_episode"] = round(float(np.mean(sec_all)), 2) if sec_all else 0.0
    step_all = [r["steps"] for r in (sac_rows or scr_rows)]
    rung["steps_per_sec"] = (round(float(np.sum(step_all) / max(np.sum(sec_all), 1e-9)), 2)
                             if sec_all else None)
    result["frontier_gate"] = run_frontier_gate([rung], args, result["machine"])

    cost = float(np.mean([r["wall_sec"] for r in (scr_rows or sac_rows)])) if (scr_rows or sac_rows) else 0.0
    scr_rate = result.get("scripted", {}).get("success_rate")
    sac_rate = result.get("sac", {}).get("success_rate")
    result["verdict"] = verdict(scr_rate if scr_rate is not None else 0.0, sac_rate,
                                result.get("paired", {}), cost)
    print("=" * 78)
    print("§12.0 第 0 步判定")
    print("=" * 78)
    for line in result["verdict"]:
        print(f"  · {line}", flush=True)

    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_contact_ceiling_{args.task}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("-" * 78)
    print(f"已写出: {out}")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
