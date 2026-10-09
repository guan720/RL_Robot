"""按配置切换环境实现（reach / perturbed），且**不修改** `envs/` 与 `eval/` 里已有的代码。

为什么用这种看起来有点脏的 monkeypatch？
    `eval/reach_eval.py::evaluate_reach` 和 `harness/trainer.py` 都是在**函数内部**
    `from envs.reach_env import make_reach_env`，也就是每次调用时才去模块上取这个属性。
    所以只要替换 `envs.reach_env.make_reach_env` 这一个属性，训练、采集、独立评测、
    严酷探针就会**同时**换到同一个环境实现上，口径天然一致。

    另一条路是给 `evaluate_reach()` 加一个 `env_factory` 参数——那更干净，但要改
    `eval/reach_eval.py`。那个文件属于另一条并行工作线，本阶段刻意不动它，
    所以把 shim 收在这一个文件里，并注明它是临时手段：等两条线合并后，
    应当把 `env_factory` 变成 `evaluate_reach` 的正式参数，然后删掉这里。

用法：在 yaml 顶层写 `env_factory: perturbed`，其余照旧。

本文件还收着**接触任务的另一个 shim**：`pinned_object_rng()`。它和上面的 monkeypatch
是同一个理由（不改 `envs/` 与第三方库），但解决的是另一个问题——robosuite 在**构造期**
用未播种的 `np.random.default_rng()` 抽物体尺寸，导致「每个进程评的是不同的物体」。
详见该函数的 docstring 与 `docs/notes_stage3.md` §7 第 22 条。
"""

from __future__ import annotations

import contextlib

REACH = "reach"
PERTURBED = "perturbed"
KNOWN = (REACH, PERTURBED)

# 钉死物体尺寸随机化用的种子。**改动它 = 换了一个 cube = 与历史数字不可比**，
# 所以它必须写进产物（`object_geom` 审计字段），不能只留在代码里。
PINNED_OBJECT_SEED = 20260923

_installed = REACH


def get_factory(name: str):
    if name == PERTURBED:
        from envs.reach_perturbed import make_perturbed_reach_env

        return make_perturbed_reach_env
    from envs.reach_env import make_reach_env

    return make_reach_env


def install_env_factory(name: str) -> str:
    """把 `envs.reach_env.make_reach_env` 指向指定实现。进程内全局生效。"""
    global _installed
    name = (name or REACH).lower()
    if name not in KNOWN:
        raise ValueError(f"未知 env_factory: {name!r}，可选 {KNOWN}")
    import envs.reach_env as reach_env_mod

    reach_env_mod.make_reach_env = get_factory(name)
    _installed = name
    return name


def current() -> str:
    return _installed


def from_config(cfg: dict) -> str:
    """从 `load_train_config()` 的结果里读出并安装环境工厂。"""
    return install_env_factory(str(cfg.get("env_factory", REACH)))


@contextlib.contextmanager
def pinned_object_rng(seed: int = PINNED_OBJECT_SEED):
    """把 robosuite **构造期未播种**的对象尺寸随机化钉死，让接触任务跨进程可复现。

    根因（2026-09-23 逐层实测定位）：
        `robosuite/environments/manipulation/lift.py:311` 用
        `BoxObject(size_min=[0.020]*3, size_max=[0.022]*3)` 建 cube；尺寸由
        `utils/mjcf_utils.py::generate_random_size(..., rng=None)` 抽出，而 `rng is None`
        时它执行 **`np.random.default_rng()`（不带种子 ⇒ 每次进程都从 OS 熵重新播种）**。
        `Robot.reset()` 的关节噪声走的是 `env.rng`（包装层按 seed 播种过，可复现），
        但物体尺寸这条路**没有人播种**。

    实测后果（同一个 ckpt、同一批 seed、出生点已验证逐位相同）：
        · 两个进程建出的 cube `bottom_offset` = 0.020175 vs 0.020347、
          `horizontal_radius` = 0.030446 vs 0.030795 —— **是两个不同的物体**
          （质量最多差 (0.022/0.020)^3 ≈ 1.33 倍，抓取难度也不同）；
        · 物体初始 z = `z_offset + reference_z − bottom_offset` 因此差 ~1.6 mm；
        · 接触动力学对 1e-3 量级的初值差是**混沌**的：4 局里成功数分别是 0/4、1/4、2/4，
          `held@step` 从 @28 到 @208 都有；
        · 换成 CPU 推理**并不能**修好（实测 CPU 两个进程同样 2/4 vs 0/4）⇒ 不是 GPU 浮点，
          是物体本身不同。
        · 进程内则完全确定：同一 ckpt 重跑，`min_xy` 等逐位相同 ⇒ **同进程配对有效**。

    所以：接触任务的「冻结评测」跨进程根本不冻结；逐 seed 对照历史产物必然失败；
    跨 run 的成功率差里混着「换了个 cube」这一项。修法就是在建环境时把这条 RNG 钉死。

    只钉**未显式传种子**的调用（`seed is None`），因此 `env.rng = default_rng(seed)`
    这类调用者自带种子的路径不受影响，不会顺手改变别的随机性。
    """
    import numpy as np

    original = np.random.default_rng

    def pinned(seed_arg=None):
        return original(int(seed) if seed_arg is None else seed_arg)

    np.random.default_rng = pinned
    try:
        yield int(seed)
    finally:
        np.random.default_rng = original


# ---------------------------------------------------------------------------
# 接触任务（Lift / PickPlaceCan）的**唯一**构造与出题入口
#
# 为什么要有这一节（K11 硬前置，§12.11-M/N + 2026-09-24 的 pickplace 迁移实测）：
#   接触任务有两条「谁都没播种」的随机性，任何一条没钉死，跨进程/跨臂的比较就都是假的：
#     1. 构造期的**物体尺寸**（`pinned_object_rng`，上面那节）；
#     2. 每次 reset 的**物体出生点**（`placement_initializer` 的 rng）。
#   第 2 条在 Lift 上「碰巧」能修（它的 initializer 就是叶子 sampler 本身，
#   `pi.rng = default_rng(seed)` 直接生效），在 PickPlace 上**修不动**：
#   那里 `placement_initializer` 是 `SequentialCompositeSampler`，它的 `sample()`
#   只遍历 `self.samplers.values()`，composite 自己的 `.rng` 属性根本不参与采样 ——
#   而 `ObjectPositionSampler` 基类又确实**有**这个属性，所以 `hasattr(pi,"rng")` 通过、
#   赋值成功、然后静默无效。实测（同 seed 连开三次）：
#       只播种 composite.rng : [-0.010,-0.290] / [0.162,-0.085] / [0.134,-0.304]  三个出生点
#       播种 5 个子 sampler  : [0.187,-0.146] × 3                                  逐位相同
#   所以「出题可复现」必须按**叶子**播种，这件事只能收在一个地方，否则每个探针各写一份、
#   各错一份。下面这些函数就是那一个地方；探针与 harness 都必须从这里取。
# ---------------------------------------------------------------------------

CONTACT_TASKS = ("lift", "pickplace")
DEFAULT_HORIZON = {"lift": 300, "pickplace": 400}


def contact_inner(env):
    """拿到 robosuite 原生 env（我们的包装层把它挂在 `_env` 上）。"""
    return getattr(env, "_env", env)


def make_contact_env(task: str, *, horizon: int | None = None, reward_shaping: bool = False,
                     obs_mode: str = "state", pin_seed: int | None = PINNED_OBJECT_SEED):
    """建接触环境。**必须**走这里：构造期物体尺寸随机化被 `pinned_object_rng` 钉死。

    `pin_seed=None` 只用于「复现旧的跨进程不可比行为」这种演示场景，正常路径不要传。
    """
    task = str(task or "").lower()
    if task not in CONTACT_TASKS:
        raise ValueError(f"未知接触任务: {task!r}，可选 {CONTACT_TASKS}")
    kwargs = {"obs_mode": obs_mode, "reward_shaping": bool(reward_shaping)}
    if horizon is not None:
        kwargs["horizon"] = int(horizon)

    def _construct():
        if task == "lift":
            from envs.robosuite_lift import RobosuiteLift

            return RobosuiteLift(**kwargs)
        from envs.robosuite_pickplace import RobosuitePickPlaceCan

        return RobosuitePickPlaceCan(**kwargs)

    if pin_seed is None:
        return _construct()
    with pinned_object_rng(int(pin_seed)):
        return _construct()


def contact_env_bundle(task: str, **kwargs) -> tuple:
    """`(env, object_geom)`：建环境的同时把**本进程实际在用的那个物体**的几何带出来。

    为什么必须成对返回：`pin_seed` 只写在代码里是不够的 —— 比较两个 run 的成功率之前，
    得先能回答「是不是同一个 cube / 同一个 can / 同一个篮位」。几何进产物，比较先看这一栏。
    """
    env = make_contact_env(task, **kwargs)
    return env, contact_object_geom(env, task, kwargs.get("pin_seed", PINNED_OBJECT_SEED))


def contact_object(env, task: str = "lift"):
    """返回当前任务**真正被操作的那个物体**对象。

    robosuite 的命名不统一，这是踩过的坑：Lift 有 `inner.cube`，PickPlace **没有**
    `inner.can`（物体在 `inner.objects` 里，`inner.object_id` 指哪个是当前任务对象；
    `PickPlaceCan` ⇒ `single_object_mode=2, object_type="can" ⇒ object_id=3`）。
    旧探针按 `getattr(inner, "can", None)` 取，静默拿到 None ⇒ 几何审计全空、
    `_check_grasp` 真值退回宽度启发式（就是 §12.11-N 里那个「弹一下算成功」的误判源头）。
    """
    inner = contact_inner(env)
    obj = getattr(inner, "cube", None) if str(task).lower() == "lift" else None
    if obj is None:
        objects = list(getattr(inner, "objects", []) or [])
        oid = getattr(inner, "object_id", None)
        if objects and isinstance(oid, int) and 0 <= oid < len(objects):
            obj = objects[oid]
        elif objects:
            obj = objects[0]
    if obj is None:
        raise RuntimeError(f"环境里找不到 task={task!r} 的操作对象（既没有 cube 也没有 objects）")
    return obj


def contact_object_geom(env, task: str = "lift", pin_seed: int | None = None) -> dict:
    """记录本进程实际在用的物体几何/质量；pickplace 连**篮筐真值**一起记。"""
    import numpy as np

    inner = contact_inner(env)
    task = str(task).lower()
    try:
        obj = contact_object(env, task)
    except RuntimeError as exc:
        return {"task": task, "pinned_object_seed": pin_seed, "error": str(exc)}
    out: dict = {"task": task, "pinned_object_seed": pin_seed,
                 "object": getattr(obj, "name", None)}
    for key in ("size", "bottom_offset", "top_offset", "horizontal_radius",
                "density", "friction", "solref", "solimp"):
        val = getattr(obj, key, None)
        if val is None:
            continue
        try:
            out[key] = [round(float(v), 10) for v in np.asarray(val, dtype=float).ravel()]
        except Exception:                       # 非标量属性（如 rgba）原样存字符串
            out[key] = str(val)
    try:                                        # 尺寸随机化最终落到质量上，质量最直观
        sim = inner.sim
        name = getattr(obj, "root_body", None) or getattr(obj, "name", None)
        bid = sim.model.body_name2id(name)
        out["body_mass_kg"] = round(float(sim.model.body_mass[bid]), 8)
        out["body_inertia"] = [round(float(v), 10) for v in sim.model.body_inertia[bid]]
    except Exception as exc:                    # 读不到就明确写出来，不要静默留空
        out["body_mass_error"] = f"{type(exc).__name__}: {exc}"
    if task != "lift":
        # 篮筐几何决定「放置段」的难度与成功判据的落点，换它 = 换任务，必须一起进产物。
        for key in ("bin_size", "bin1_pos", "bin2_pos"):
            val = getattr(inner, key, None)
            if val is None:
                continue
            try:
                out[key] = [round(float(v), 6) for v in np.asarray(val, dtype=float).ravel()]
            except Exception:
                out[key] = str(val)
        oid = getattr(inner, "object_id", None)
        tbp = getattr(inner, "target_bin_placements", None)
        if tbp is not None and isinstance(oid, int):
            try:
                out["target_bin_center"] = [round(float(v), 6) for v in np.asarray(tbp)[oid]]
            except Exception:
                pass
        out["object_id"] = oid
        out["single_object_mode"] = getattr(inner, "single_object_mode", None)
        out["obj_to_use"] = getattr(inner, "obj_to_use", None)
    return out


def placement_leaves(env) -> list:
    """返回真正持有 `rng` / `x_range` 的**叶子 sampler**。

    Lift：`placement_initializer` 本身就是 `UniformRandomSampler` ⇒ 叶子就是它。
    PickPlace：`SequentialCompositeSampler`，叶子是 5 个子 sampler
    （1 个 `CollisionObjectSampler` 管 can 的出生点 + 4 个视觉物体的定点 sampler）。
    """
    inner = contact_inner(env)
    pi = getattr(inner, "placement_initializer", None)
    if pi is None:
        raise RuntimeError("环境没有 placement_initializer，无法保证出题可复现")
    subs = getattr(pi, "samplers", None)
    if subs:
        leaves = list(subs.values()) if isinstance(subs, dict) else list(subs)
        leaves = [leaf for leaf in leaves if leaf is not None]
        if leaves:
            return leaves
    return [pi]


def seed_placement(env, seed: int) -> int:
    """把决定物体出生点的 rng 播种到**叶子**，返回被播种的叶子数。

    只有一个叶子时用 `default_rng(seed)` —— 与历史 Lift 产物**逐位一致**（这一条是硬约束，
    否则 `paired_lift_d_workpoint.json` 那批数字全部作废）；多叶子时用
    `default_rng([seed, i])` 派生，避免 5 个子 sampler 抽到同一条序列。
    """
    import numpy as np

    leaves = placement_leaves(env)
    for i, leaf in enumerate(leaves):
        leaf.rng = (np.random.default_rng(int(seed)) if len(leaves) == 1
                    else np.random.default_rng([int(seed), int(i)]))
    return len(leaves)


def set_spawn_half_range(env, half_range: float | None, task: str = "lift") -> int:
    """设定物体出生盒子（正方形半宽，米），返回改动了几个叶子。None = 用环境默认。

    只改**拥有当前操作对象**的那个叶子：给 composite 设 `x_range` 和给它设 `rng` 一样，
    是静默无效（属性写进去了，采样时没人读）。旧探针就是这么让 `--spawn-range` /
    `--spawn-sweep` 在 pickplace 上空转的。
    """
    if half_range is None:
        return 0
    leaves = placement_leaves(env)
    try:
        target = getattr(contact_object(env, task), "name", None)
    except RuntimeError:
        target = None
    owners = []
    for leaf in leaves:
        objs = list(getattr(leaf, "mujoco_objects", []) or [])
        if target is not None and any(getattr(o, "name", None) == target for o in objs):
            owners.append(leaf)
    if not owners:                  # 兜底：取「出生盒子非退化」的叶子（视觉物体的是定点，范围相等）
        owners = [leaf for leaf in leaves
                  if hasattr(leaf, "x_range") and len(set(map(float, leaf.x_range))) > 1]
    for leaf in owners or leaves[:1]:
        leaf.x_range = [-float(half_range), float(half_range)]
        leaf.y_range = [-float(half_range), float(half_range)]
    return len(owners or leaves[:1])


def reset_contact(env, seed: int):
    """可复现 reset：物体出生点**只**由 seed 决定（Lift / PickPlace 通用）。

    顺序很关键：先走包装层 `reset(seed=...)` 让它重置自己的记账（`_succ_held` /
    `tasks_done`）并播种 `inner.rng`（机器人关节噪声那条路），**再**播种叶子 sampler
    并重新 `inner.reset()` —— 只有第二次 reset 的摆放才用到我们播种的 rng。
    代价是每局多一次 reset（实测 <1 s）。
    """
    env.reset(seed=seed)
    seed_placement(env, seed)
    inner = contact_inner(env)
    raw = inner.reset()
    return env._obs(raw) if hasattr(env, "_obs") else raw


def place_truth_fn(env, task: str = "pickplace"):
    """返回 `callable -> dict`，用 **robosuite 自己的判据**报告放置段真值；Lift 返回 None。

    为什么必须有它：`PickPlaceCan._check_success()` 是**两个条件同时成立**——
      ① `not_in_bin(pos, object_id) == False`：can 落在篮筐**象限**内
         （x∈[bin2_x, bin2_x+bin_size/2]、y 同理）且 z∈(bin2_z, bin2_z+0.1)；
      ② `r_reach = 1 − tanh(10·dist(eef_site, can)) < 0.6`，即末端已离 can **> 4.23 cm**
         （松手并退开）。
    只报 success 就分不清「从没放进去」和「放进去了但没退开」，而这两者的修法完全不同
    （前者是搬运/释放段没学会，后者是判据的第二半在挡 ⇒ 成功率会系统性低估）。
    所以逐局要把 `ever_in_bin` 与 `min_r_reach_in_bin` 分开记。
    """
    import numpy as np

    inner = contact_inner(env)
    if str(task).lower() == "lift" or not hasattr(inner, "not_in_bin"):
        return None
    obj = contact_object(env, task)
    oid = int(getattr(inner, "object_id", 0))
    bid = inner.obj_body_id[obj.name]
    tgt = np.asarray(inner.target_bin_placements, dtype=float)[oid]
    half = np.asarray(inner.bin_size, dtype=float).ravel()[:2] / 4.0
    robot = inner.robots[0]
    site_ids = [robot.eef_site_id[arm] for arm in robot.arms]

    def fn() -> dict:
        pos = np.asarray(inner.sim.data.body_xpos[bid], dtype=float)
        dist = min(float(np.linalg.norm(np.asarray(inner.sim.data.site_xpos[s], dtype=float) - pos))
                   for s in site_ids)
        return {"in_bin": not bool(inner.not_in_bin(pos, oid)),
                "above_bin": bool(abs(pos[0] - tgt[0]) < half[0] and abs(pos[1] - tgt[1]) < half[1]),
                "obj_z": round(float(pos[2]), 5),
                "dist_target": round(float(np.linalg.norm(pos[:2] - tgt[:2])), 5),
                "dist_eef_obj": round(dist, 5),
                "r_reach": round(float(1.0 - np.tanh(10.0 * dist)), 5)}

    return fn
