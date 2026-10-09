#!/usr/bin/env python
"""A2 · 裁定 104.3 的 CPU-only 测量件 —— Ⅰ 类缺陷 `demo_init_box_quat_not_written` 的**量级**

为什么必须有这一件（裁定 104.2 / 补单九 ②③）
--------------------------------------------
`PRE._init_env_to_state()`（`scripts/a2_step1_prealign_verify.py:1078`）把 C2 的 env 置到示范初态时，
写 `qpos[0:16]`（双臂+双爪）与 `qpos[16:19]`（方块 xyz，取 sidecar 的 `box_rest_after_settle_xyz`
= **沉降后**），**不写 `qpos[19:23]`（方块四元数）** ⇒ 四元数留在 `reset(seed)` 的值（**沉降前**）
⇒ Step-1 的闭环初态是「沉降后位置 + 沉降前姿态」的**拼接**（`scripts/a2_step1_bc_overfit.py:2619`）。
而回读自证 `readback_ok` 与阻塞牙 `demo_init_readback_failed` 都只比 **14 维机器人状态**
⇒ **证据作用域 ⊊ 结论作用域** ⇒ 旧键 `step1_rollout_not_affected` 不予采信（裁定 104.2-（d））。
红线 `absence_of_measurement_is_not_measurement_of_absence`：**量级只能测出来，不能推出来。**

这一件做什么（两阶段，CPU-only，不执行 policy，不动任何冻结面）
--------------------------------------------------------------
  `--stage prereg`   先落**预登记**：阈值 + **实测锚** + 两分支程序 + 负对照设计。
                     落盘时**尚无 40 集的任何结果**（阈值不由结果反推）。
  `--stage measure`  校验预登记（`sha256[:12]` + 阈值逐字 + 锚逐字）后才跑：
                     40 集全量（不抽样）+ 8 组对照 ⇒ `DEMO_INIT_BOX_QUAT_SETTLE.json`。
                     该件的键名与 `scripts/a2_step1_bc_overfit.py::box_quat_defect_status()`
                     的消费口逐字对齐（`branch_decision` / `aggregate` / `negative_controls`）。

纪律
----
* **三值**：`measured` / `not_measured`（⇒ 非零退出，**不用 false/0 顶替**）/ `refused`。
* **数值成对**：机器负载读数（`loadavg` 三点 + `nr_throttled`，cgroup **v1**，配额 12 核、
  `nproc=112` 是假象）在开头与结尾各取一次，复用 `PBG.gpu_window_readings()`（不重造）。
  三网读数里的**外来占用**（`min_grasp_pi05` = 用户隔离线）只是**排程事实**，
  与本线读数**不得互搬**（裁定 46.4 / 103.6-②）。
* **能力声明禁令**：`capability_claim=false`、`policy_executed=false`、`gpu_used=false`、
  `success_rate_column="not_an_exit_criterion"`。本件不产生任何 policy 指标。
* **行数口径**：`n_lines_wc` = 换行符个数；`n_lines_splitlines` = `len(text.splitlines())`。
  裸 `n_lines` 禁用（裁定 98.5）。
* **冻结面**：先落腿件 `scripts/a2_step1_prealign_verify.py` 只**读复用**（`read_dataset_arrays` /
  `build_demo_initial_states` / `_init_env_to_state`），一个字节不改；判定层与 stats 不碰。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import time

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
SELF_REL = "scripts/a2_demo_init_box_quat_measure.py"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_mod(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PRE = _load_mod("a2_pre_mod_for_quat_measure", "scripts/a2_step1_prealign_verify.py")

now_iso = PRE.now_iso
sha12 = PRE.sha12
identity = PRE.identity
write_json = PRE.write_json
jdefault = PRE.jdefault
N_LINES_CALIBER = PRE.N_LINES_CALIBER
GRIP_DIMS = PRE.GRIP_DIMS
STATE_DIM = PRE.STATE_DIM

EXIT_OK, EXIT_BLOCKING_RED, EXIT_USAGE, EXIT_NOT_MEASURED = 0, 1, 2, 3

# ══════════════════ 落点（与入口脚本的消费口逐字对齐，不许漂）══════════════════
OUT_DIR_DEFAULT = "runs/vla/a2_s3_bc_overfit_20260930"
PREREG_REL = f"{OUT_DIR_DEFAULT}/DEMO_INIT_BOX_QUAT_PREREG.json"
MEASURE_REL = f"{OUT_DIR_DEFAULT}/DEMO_INIT_BOX_QUAT_SETTLE.json"
CONSUMER_FUNC = "scripts/a2_step1_bc_overfit.py::box_quat_defect_status"
CONSUMER_DEFAULT_CONST = "scripts/a2_step1_bc_overfit.py:572 BOX_QUAT_MEASURE_JSON_DEFAULT"

# ══════════════════ A2 自设的判据（裁定 104.3-①：D 不代设数字）══════════════════
SETTLE_STEPS = 12                       # = B2 的 `cfg.settle_steps`（`b2_s1_scripted_expert.py:807`）
N_EPISODES_REQUIRED = 40                # 裁定 104.3-④：全量、不抽样（少于 40 ⇒ not_measured）
ANGLE_DIFF_DEG_MAX_THRESHOLD = 1.0      # C1/C2：沉降前 vs 沉降后四元数的测地角差
SPLICE_REST_DRIFT_XYZ_M_MAX = 1.0e-4    # C3：拼接初态 12 hold 步后方块 xyz 的漂移
SPLICE_REST_ANGLE_DEG_MAX = 1.0         # C4：拼接初态 12 hold 步后方块姿态的漂移
REST_XYZ_MATCH_TOL_M = 1.0e-5           # C6：正向对照（我的沉降 == B2 记录的 rest）
NC_INJECT_DEG = 15.0                    # 负对照注入角（补单九 ③-②：人为改四元数 ⇒ 判据必须翻）
NC_INJECT_TOL_DEG = 0.1                 # 注入角的估计器回读容差
THRESHOLD_INSENSITIVITY_DEGS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
PIXEL_ANCHOR_DEGS = (0.5, 1.0, 2.0, 5.0, 15.0, 90.0)
PIXEL_ANCHOR_AXES = (( "z", (0.0, 0.0, 1.0)), ("x", (1.0, 0.0, 0.0)), ("y", (0.0, 1.0, 0.0)))
PIXEL_ANCHOR_IMAGE_SIZE = 224           # = Step-1 的 `--image-size` 默认值（`:4072`），锚必须在同分辨率上取
BOX_GEOM_EXPECTED_HALF_SIZE = (0.02, 0.02, 0.02)

AUTHORITY = [
    "rl_harness_supervision/d_handoff_to_a2_20260930.md 补单九 ③（裁定 104.3：CPU-only 测量的五项要求）",
    "裁定 104.2（Ⅰ 类缺陷 `demo_init_box_quat_not_written` 的事实链与 (a)–(e) 处置）",
    "裁定 104.3（两分支都预登记、跑完不裁量；甲 ⇒ 按现码起跑一字节不改；乙 ⇒ 只许一处窄修）",
    "红线 absence_of_measurement_is_not_measurement_of_absence（测出量级之前不得写「不影响」）",
    "裁定 46（能力声明禁令）· 裁定 98.5（sha 是唯一约束性判据；裸 n_lines 禁用）",
    "裁定 46.4 / 53.6 / 85.7（数值成对带 loadavg 三点 + nr_throttled）· 裁定 103.6-②（隔离线读数不互搬）",
]


# ══════════════════════════ 四元数工具（wxyz，SO(3) 测地角）══════════════════════════
def quat_from_axis_angle(axis, deg: float) -> np.ndarray:
    a = np.asarray(axis, dtype=np.float64)
    n = float(np.linalg.norm(a))
    if n <= 0.0:
        raise ValueError(f"零轴不能定旋转：{axis!r}")
    a = a / n
    t = np.deg2rad(float(deg)) / 2.0
    return np.array([np.cos(t), *(a * np.sin(t))], dtype=np.float64)


def quat_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = (float(v) for v in a)
    w2, x2, y2, z2 = (float(v) for v in b)
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], dtype=np.float64)


def quat_angle_deg(q1, q2) -> float:
    """SO(3) 上的测地角差（度）。**双覆盖**：`q` 与 `-q` 是同一旋转 ⇒ 取 `|dot|`。"""
    a = np.asarray(q1, dtype=np.float64).reshape(-1)
    b = np.asarray(q2, dtype=np.float64).reshape(-1)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 0.0 or nb <= 0.0:
        raise ValueError("四元数模长为 0，不是合法旋转")
    d = abs(float(np.dot(a, b))) / (na * nb)
    return float(np.rad2deg(2.0 * np.arccos(min(1.0, d))))


def quat_bitwise_identical(q1, q2) -> bool:
    """**逐位**相同（含符号零 / 次正规数）。与 `quat_angle_deg == 0.0` 是**两件不同的事**：
    ep0 探针实测沉降后虚部是 `-3.17e-18 / -2.59e-17 / -2.64e-34`（负零与次正规）⇒
    角差恰为 0.0，但逐位**不同**。正式件必须把两者分开报，不许合并成一个布尔。"""
    a = np.ascontiguousarray(np.asarray(q1, dtype=np.float64).reshape(-1))
    b = np.ascontiguousarray(np.asarray(q2, dtype=np.float64).reshape(-1))
    return bool(np.array_equal(a.view(np.uint64), b.view(np.uint64)))


def quat_normalize_sign(q) -> np.ndarray:
    """把双覆盖规范化（`w<0` 或 `w==0 且首个非零分量为负` ⇒ 取反），用于**逐位**比较的可读形态。"""
    a = np.asarray(q, dtype=np.float64).reshape(-1).copy()
    if a[0] < 0.0 or (a[0] == 0.0 and next((v for v in a if v != 0.0), 0.0) < 0.0):
        a = -a
    return a


# ══════════════════════════ 模型侧口径（**派生**，不硬编下标）══════════════════════════
def box_qpos_layout(ph) -> dict:
    """方块自由关节的 qpos 切片：**从模型派生**（geom → body → joint → qposadr），
    并断言它确实是 7 维自由关节且落在 `[16:19]`/`[19:23]`。模型换了 ⇒ **抛**，不静默测错切片。"""
    import mujoco
    from harness.env_gym_aloha import GEOM_BOX
    m = ph.model
    gnames = [mujoco.mj_id2name(m.ptr, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(m.ngeom)]
    if GEOM_BOX not in gnames:
        raise RuntimeError(f"模型里没有方块 geom {GEOM_BOX!r} ⇒ 拒绝测量（不许假设下标）")
    gid = gnames.index(GEOM_BOX)
    bodyid = int(m.geom_bodyid[gid])
    jntadr = int(m.body_jntadr[bodyid])
    njnt_body = int(m.body_jntnum[bodyid])
    if njnt_body != 1:
        raise RuntimeError(f"方块所在 body 有 {njnt_body} 个关节（≠1）⇒ 切片不可派生，拒绝测量")
    if int(m.jnt_type[jntadr]) != int(mujoco.mjtJoint.mjJNT_FREE):
        raise RuntimeError("方块关节不是 mjJNT_FREE ⇒ qpos 不是 3+4 布局，拒绝测量")
    adr = int(m.jnt_qposadr[jntadr])
    jname = mujoco.mj_id2name(m.ptr, mujoco.mjtObj.mjOBJ_JOINT, jntadr)
    out = {"box_geom_id": gid, "box_geom_name": GEOM_BOX, "box_body_id": bodyid,
           "box_joint_id": jntadr, "box_joint_name": jname, "box_qposadr": adr,
           "xyz_slice": [adr, adr + 3], "quat_slice": [adr + 3, adr + 7],
           "joint_type_is_free": True,
           "matches_hardcoded_16_19_23": bool(adr == 16),
           "box_geom_half_size": [float(x) for x in m.geom_size[gid]],
           "box_geom_type": int(m.geom_type[gid]),
           "nq": int(m.nq), "nv": int(m.nv), "nu": int(m.nu),
           "nmocap": int(m.nmocap), "neq": int(m.neq),
           "timestep": float(m.opt.timestep)}
    if not out["matches_hardcoded_16_19_23"]:
        raise RuntimeError(f"派生出的 qposadr={adr} ≠ 16 ⇒ 与先落腿件的 `q[16:19]` 口径不符，"
                           "拒绝测量（先落腿件与判定层必须先对齐，A2 不擅改）")
    if tuple(round(x, 6) for x in out["box_geom_half_size"]) != BOX_GEOM_EXPECTED_HALF_SIZE:
        out["geom_size_changed_vs_anchor"] = True
    return out


def hold_action(jenv) -> np.ndarray:
    """hold 动作 = 当前 `_state()` 的前 14 维，夹爪维裁到 [0,1]。
    **逐字复刻** `scripts/a2_step1_bc_overfit.py::DemoInitAdapter.reset` 里 `self._hold` 的构造
    （`:2620`–`:2626`），不自创口径。"""
    st = np.asarray(jenv._state(), dtype=np.float64).reshape(-1)
    hold = [float(x) for x in st[:STATE_DIM]]
    for gi in GRIP_DIMS:
        if gi < len(hold):
            hold[gi] = min(max(hold[gi], 0.0), 1.0)
    return np.asarray(hold, dtype=np.float32)


def box_contacts(ph) -> set:
    """本步与方块接触的 geom 名集合（用判定层同一口径 `model.id2name(.., "geom")`，不重造）。"""
    from harness.env_gym_aloha import GEOM_BOX
    out = set()
    for i in range(int(ph.data.ncon)):
        c = ph.data.contact[i]
        g1 = ph.model.id2name(int(c.geom1), "geom")
        g2 = ph.model.id2name(int(c.geom2), "geom")
        if g1 == GEOM_BOX:
            out.add(g2)
        elif g2 == GEOM_BOX:
            out.add(g1)
    return out


def sidecar_decimal_places(vals) -> int | None:
    """sidecar 里 xyz 的**小数位数**（实测表示地板；ep0 探针实测 = 5 位 ⇒ 地板 5e-6 m）。"""
    if not isinstance(vals, (list, tuple)) or not vals:
        return None
    ds = []
    for v in vals:
        s = repr(float(v))
        ds.append(len(s.split(".")[1]) if "." in s else 0)
    return int(max(ds))


def settle_run(jenv, ph, x0, x1, q0, q1, *, write_spawn=None) -> dict:
    """一条 12 步 hold 的沉降腿。`write_spawn` 给了就先把方块 xyz 写成它（`qvel=0` + `forward()`）。

    为什么要**两条**沉降腿（A0/A1）：
    * **A0**（不写）= 纯 `reset(seed)` 的 spawn（`gym_aloha/utils.py::sample_box_pose`，x∈[0,0.2]，
      **不镜像**）⇒ 它是「现码留在初态里的那个四元数」的**真实来源**；
    * **A1**（写 sidecar 的 `box_spawn_xyz`）= **B2 的真实初条件**（reverse 的 x 区间是 [-0.2,0]，
      `b2_s1_scripted_expert.py:113` `sample_box_pose_seeded`）⇒ sidecar 记录的
      `box_rest_after_settle_xyz` 就是从这条腿出来的。
    正向对照（NC-G）必须用 **A1**：用 A0 去比 sidecar 的绝对位置，在 reverse 集上量到的是
    **已登记的方向差 0.2 m**，不是沉降腿的对错（本件第一版就错在这里，见 `prereg_revision_history`）。
    """
    if write_spawn is not None:
        q = ph.data.qpos.copy()
        q[x0:x1] = np.asarray(write_spawn, dtype=np.float64)
        ph.data.qvel[:] = 0.0
        ph.data.qpos[:] = q
        ph.forward()
    xyz_pre = np.asarray(ph.data.qpos[x0:x1], dtype=np.float64).copy()
    quat_pre = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
    contacts: set = set()
    traj = []
    for _ in range(SETTLE_STEPS):
        jenv.step(hold_action(jenv))
        contacts |= box_contacts(ph)
        traj.append([float(x) for x in ph.data.qpos[x0:x1]]
                    + [float(x) for x in ph.data.qpos[q0:q1]])
    return {"spawn_written": (None if write_spawn is None
                              else [float(x) for x in np.asarray(write_spawn, dtype=np.float64)]),
            "n_hold_steps": SETTLE_STEPS,
            "xyz_pre": xyz_pre, "quat_pre": quat_pre,
            "xyz_post": np.asarray(ph.data.qpos[x0:x1], dtype=np.float64).copy(),
            "quat_post": np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy(),
            "contacts": contacts,
            "traj_first_last": ([traj[0], traj[-1]] if traj else []),
            "z_drop_m": float(xyz_pre[2] - np.asarray(ph.data.qpos[x0:x1], dtype=np.float64)[2])}


def anchor_spawn_quat_source() -> dict:
    """**源码级佐证**（当场重读文件字节，不转抄、不凭记忆）：两个 spawn 采样器都把方块四元数
    硬编成 identity。这与「40 集实测角差 = 0.0°」互为**独立**佐证 —— 一条是读码，一条是跑物理。

    注意作用域：源码只说明**初态**是 identity；「沉降 12 步之后仍是 identity」是**物理**结论，
    只能由 A0/A1 两条腿测出来，源码不能替代（否则又是一次证据作用域 ⊊ 结论作用域）。
    """
    out: dict = {"measurement_status": "not_measured", "sources": []}
    try:
        import gym_aloha.utils as GU
        targets = [("gym_aloha/utils.py::sample_box_pose", GU.__file__, ("cube_quat",)),
                   ("scripts/b2_s1_scripted_expert.py::sample_box_pose_seeded",
                    str(REPO / PRE.P_EXPERT), ("1.0, 0.0, 0.0, 0.0",)),
                   ("scripts/b2_s1_scripted_expert.py::SPAWN_RANGE",
                    str(REPO / PRE.P_EXPERT), ("SPAWN_RANGE",))]
        for label, path, needles in targets:
            pp = pathlib.Path(path)
            if not pp.exists():
                out["sources"].append({"label": label, "path": path, "exists": False,
                                       "measurement_status": "not_measured"})
                continue
            txt = pp.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = []
            for i, ln in enumerate(txt, start=1):
                if any(nd in ln for nd in needles):
                    hits.append({"line_1based": i, "text": ln.strip()[:200]})
            rel = (str(pp.relative_to(REPO)) if pp.is_relative_to(REPO) else str(pp))
            out["sources"].append({
                "label": label, "path": rel, "exists": True, "sha256_12": sha12(pp),
                "measurement_status": "measured" if hits else "not_measured",
                "n_hits": len(hits), "hits": hits[:8]})
        out["measurement_status"] = ("measured" if out["sources"]
                                     and all(s.get("measurement_status") == "measured"
                                             for s in out["sources"]) else "not_measured")
        out["finding"] = ("两个 spawn 采样器都把方块四元数写成 `[1,0,0,0]`（identity）：上游 "
                          "`gym_aloha/utils.py`（`reset(seed)` 走的就是它）与 B2 的 "
                          "`sample_box_pose_seeded`（数据集/sidecar 的 spawn 走的是它）⇒ "
                          "**沉降前**四元数与 B2 记录时的**沉降前**四元数是同一个常量，与 seed 无关")
        out["scope_caveat"] = ("只覆盖「**沉降前**是 identity」。「**沉降后**仍是 identity」是物理结论，"
                               "由 A0/A1 的 12 hold 步实测给；源码不能替代")
    except Exception as exc:                                          # noqa: BLE001
        out.update({"measurement_status": "not_measured",
                    "error": f"{type(exc).__name__}: {exc}"})
    return out


# ══════════════════════════ 阶段一：预登记（**尚无 40 集结果**）══════════════════════════
def measure_anchors(rows: list[dict], *, image_size: int, do_pixel: bool) -> dict:
    """阈值要用到的**实测锚**：模型/判据侧的几何事实 + sidecar 表示地板 + 像素可表征性。

    这些是**冻结 harness 的属性**，不是「沉降前后差多少」的结果 ⇒ 可以在预登记之前测。
    唯一例外：像素锚需要构造 Step-1 真正看到的那一帧 ⇒ 必然读到 ep0 的**沉降前**四元数，
    这一点在 `contamination_disclosure` 里**明写**，不装作盲。
    """
    from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
    r0 = rows[0]
    a: dict = {"as_of": now_iso(), "anchor_episode": {
        "episode_index": r0["episode_index"], "ep_id": r0["ep_id"], "seed": r0["seed"],
        "manifest_direction": r0["manifest_direction"], "env_direction": r0["env_direction"]}}

    jenv = GymAlohaSimEnv(EnvSpec(direction=r0["env_direction"], image_size=64,
                                  render_images=False, seed=r0["seed"]))
    jenv.reset(seed=r0["seed"])
    ph = jenv.physics
    a["model_facts"] = box_qpos_layout(ph)
    a["judge_thresholds"] = jenv.spec.thresholds.as_dict()
    a["judge_has_orientation_term"] = {
        "value": False,
        "evidence": ("`harness/env_gym_aloha.py:232`–`:256`：判据变量只有 "
                     "`dist=|box_xyz - finger_geom_xpos|`、`height=box_xyz[2]-table_z_ref`、"
                     "`box_speed_mps`、`contact_box_table`、`hold_steps`；"
                     "`JudgeThresholds` 的 6 个字段里**没有任何姿态/四元数项**（当场重读，见上）"),
        "consequence": ("方块**绕自身中心**的旋转对判据的直接输入（中心 xyz / 速度）**恒等不变**；"
                        "姿态只能通过 ①接触几何（`contact_box_*`）②policy 的像素输入 两条间接通道起作用"),
        "who_owns": "C2（判定层）/ D（口径）；**A2 不改**，只测量并登记",
    }
    a["sidecar_representation_floor"] = {
        "spawn_xyz": r0["box_spawn_xyz"], "rest_xyz": r0["box_rest_after_settle_xyz"],
        "decimal_places_spawn": sidecar_decimal_places(r0["box_spawn_xyz"]),
        "decimal_places_rest": sidecar_decimal_places(r0["box_rest_after_settle_xyz"]),
        "floor_m": (None if sidecar_decimal_places(r0["box_rest_after_settle_xyz"]) is None
                    else 0.5 * 10.0 ** -int(sidecar_decimal_places(r0["box_rest_after_settle_xyz"]))),
        "consequence": ("sidecar 的 xyz 是**舍入后**存的 ⇒ `REST_XYZ_MATCH_TOL_M` 不能比这个地板更紧，"
                        "否则量的是 B2 的舍入而不是物理"),
    }
    a["sidecar_has_any_quaternion_key"] = {
        "value": not any("quat" in k.lower() for k in r0.keys()),
        "keys": sorted(r0.keys()),
        "consequence": ("数据集与 sidecar **都不存方块四元数** ⇒ 乙分支的「记录的 frame-0 四元数」"
                        "**没有**数据侧来源，只能用本件复现值替代（需 D 认可该替代来源）"),
    }
    a["spawn_quat_source"] = anchor_spawn_quat_source()
    a["pixel_sensitivity"] = (pixel_sensitivity(jenv, r0, image_size=image_size)
                              if do_pixel else {"measurement_status": "not_measured",
                                                "why": "`--no-pixel-anchor` ⇒ 不测（不写 0）"})
    a["machine_load_at_anchor"] = PRE.PBG.gpu_window_readings(extra={"phase": "quat_prereg_anchor"})
    return a


def pixel_sensitivity(jenv, r: dict, *, image_size: int) -> dict:
    """在 Step-1 rollout **真正看到的那一帧**上，把方块四元数人为转 θ，数三相机各变几个像素。

    为什么要这个锚：1.0° 这个阈值不能靠「大概是亚像素吧」来撑。实测下来它**不是**亚像素
    （base 相机 15–60 px 变），所以阈值的正当性只能来自**判据无姿态项 + 分支对阈值不敏感**
    （`threshold_insensitivity_report`），而不是「看不见」。这条锚把话说死，免得事后被当成
    「A2 用一个松阈值给自己放行」。
    """
    from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
    from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
    out: dict = {"image_size": int(image_size), "render_backend": os.environ.get("MUJOCO_GL"),
                 "gpu_used": False, "rows": []}
    try:
        j2 = GymAlohaSimEnv(EnvSpec(direction=r["env_direction"], image_size=int(image_size),
                                    render_images=True, seed=r["seed"]))
        j2.reset(seed=r["seed"])
        ph2 = j2.physics
        lay = box_qpos_layout(ph2)
        q0, q1 = lay["quat_slice"]
        s14 = np.asarray(r["frame0_state"], dtype=np.float64)
        PRE._init_env_to_state(j2, s14, r["box_rest_after_settle_xyz"], unorm)
        base = np.asarray(ph2.data.qpos[q0:q1], dtype=np.float64).copy()

        def render_u8() -> dict:
            obs = j2.observation()
            return {k: (np.clip(np.asarray(v), 0.0, 1.0) * 255.0).round().astype(np.uint8)
                    for k, v in obs.items() if k.startswith("observation.images.")}

        ref = render_u8()
        out["ref_shapes"] = {k: list(v.shape) for k, v in ref.items()}
        out["base_quat_at_spliced_frame"] = [float(x) for x in base]
        for ax_name, ax in PIXEL_ANCHOR_AXES:
            for deg in PIXEL_ANCHOR_DEGS:
                ph2.data.qpos[q0:q1] = quat_mul(quat_from_axis_angle(ax, deg), base)
                ph2.data.qvel[:] = 0.0
                ph2.forward()
                cur = render_u8()
                row = {"axis": ax_name, "injected_deg": float(deg),
                       "estimator_readback_deg": quat_angle_deg(base, ph2.data.qpos[q0:q1]),
                       "cams": {}}
                for k in sorted(ref):
                    diff = np.abs(cur[k].astype(np.int32) - ref[k].astype(np.int32)).max(axis=0)
                    row["cams"][k] = {"n_px_changed": int((diff > 0).sum()),
                                      "n_px_total": int(diff.size),
                                      "frac_px_changed": float((diff > 0).mean())}
                out["rows"].append(row)
        ph2.data.qpos[q0:q1] = base
        ph2.forward()
        out["measurement_status"] = "measured"
        out["self_consistency"] = {
            "cube_90deg_maps_to_itself": {
                "expected": "绕 x/y/z 转 90° 后立方体与自身重合 ⇒ 变像素应≈0",
                "observed_n_px": {row["axis"]: row["cams"].get(
                    "observation.images.base_0_rgb", {}).get("n_px_changed")
                    for row in out["rows"] if row["injected_deg"] == 90.0},
            },
            "wrist_cams_see_box_at_frame0": {
                "expected": None,
                "observed_all_zero": bool(all(
                    row["cams"].get("observation.images.left_wrist_0_rgb", {}).get("n_px_changed") == 0
                    and row["cams"].get("observation.images.right_wrist_0_rgb", {}).get("n_px_changed") == 0
                    for row in out["rows"])),
                "consequence": ("若为 true ⇒ frame-0 时两个腕相机**看不见**方块 ⇒ 姿态差只可能进 "
                                "base 相机这一路 policy 输入（3 路里的 1 路）"),
            },
        }
    except Exception as exc:                                          # noqa: BLE001
        out.update({"measurement_status": "not_measured",
                    "error": f"{type(exc).__name__}: {exc}",
                    "why": "锚腿抛异常 ⇒ not_measured（不写 0、不写「无影响」）"})
    return out


def build_prereg(args, rows: list[dict], init_block: dict) -> dict:
    out_dir = pathlib.Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    anchors = measure_anchors(rows, image_size=int(args.pixel_image_size),
                              do_pixel=not args.no_pixel_anchor)
    px = anchors.get("pixel_sensitivity") or {}
    px_rows = px.get("rows") or []
    base_px_at_1deg = [r["cams"].get("observation.images.base_0_rgb", {}).get("n_px_changed")
                       for r in px_rows if r["injected_deg"] == 1.0]
    n_px_total = next((r["cams"].get("observation.images.base_0_rgb", {}).get("n_px_total")
                       for r in px_rows if r["cams"].get("observation.images.base_0_rgb")), None)
    half = float(np.asarray(anchors["model_facts"]["box_geom_half_size"], dtype=np.float64)[0])
    side = 2.0 * half
    d_w_1deg = side * (abs(np.cos(np.deg2rad(1.0))) + abs(np.sin(np.deg2rad(1.0))) - 1.0)
    jt = anchors["judge_thresholds"]
    floor = anchors["sidecar_representation_floor"]
    doc = {
        "artifact": "a2_demo_init_box_quat_prereg",
        "as_of": now_iso(),
        "producer": {"script": SELF_REL,
                     **{k: v for k, v in identity(SELF_REL).items()
                        if k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                     "python": sys.version.split()[0], "venv": sys.executable},
        "n_lines_caliber": N_LINES_CALIBER,
        "stage": "prereg",
        "purpose": ("裁定 104.3-①：断言与阈值由 A2 **预登记**（D 不代设数字）。本件落盘时"
                    "**尚无 40 集的任何结果** ⇒ 阈值不由结果反推；`--stage measure` 必须先校验本件"
                    "（sha + 阈值逐字 + 锚逐字）才允许跑。"),
        "authority": AUTHORITY,
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "success_rate_column": "not_an_exit_criterion",
        "model_weights_loaded": False,
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "defect_under_measurement": {
            "id": "A2-SD-10_demo_init_box_quat_not_written",
            "d_ruling_id": "demo_init_box_quat_not_written（裁定 104.2，Ⅰ 类，OPEN）",
            "mechanism": ("`PRE._init_env_to_state` 写 `qpos[16:19]`=沉降后 xyz，**不写** "
                          "`qpos[19:23]`=四元数 ⇒ 初态 = 沉降后位置 + `reset(seed)` 的沉降前姿态"),
            "write_site": "scripts/a2_step1_prealign_verify.py:1078（`_init_env_to_state`）",
            "consumer_site": "scripts/a2_step1_bc_overfit.py:2619（`DemoInitAdapter.reset`）",
            "readback_scope": ("`readback_ok` / 阻塞牙 `demo_init_readback_failed` 只比 "
                               "`jenv._state()[:14]` ⇒ **不含方块位姿** ⇒ 不能用来证明「不影响」"),
        },
        "what_is_measured": {
            "primary": ("每一集：`reset(seed)` 那一刻的方块四元数（**沉降前**，= 现码留在初态里的值）"
                        "vs 沉降 12 步之后的方块四元数（**沉降后**，= 写进去的 xyz 所属的那个姿态），"
                        "取 SO(3) 测地角差（度）"),
            "secondary": ("每一集：把现码的**拼接初态**真的构造出来（`_init_env_to_state`），"
                          "再走 12 个 hold 步，量方块 xyz / 姿态漂了多少 ⇒ 这是「拼接是否静止」的直接测量"),
            "n_episodes": len(rows), "sampling": "**全量、不抽样**（裁定 104.3-④）",
            "settle_steps": SETTLE_STEPS,
            "settle_steps_source": ("B2 `scripts/b2_s1_scripted_expert.py:807` `settle_steps=12`；"
                                    "sidecar `settle_steps_dropped` 当场重读，见 `dataset_side`"),
        },
        "reference_legs_design": {
            "A0_pure_reset_settle": ("`reset(seed)` → 12 hold 步。**不写**方块 xyz ⇒ 位置是上游 "
                                     "`gym_aloha/utils.py::sample_box_pose(seed)` 的 spawn（x∈[0,0.2]，"
                                     "**不镜像**）。它是「现码留在初态里的那个四元数」的**来源腿**"),
            "A1_sidecar_spawn_settle": ("`reset(seed)` → 写 sidecar 的 `box_spawn_xyz` → 12 hold 步。"
                                        "= **B2 的真实初条件**（reverse 的 x∈[-0.2,0]），sidecar 的 "
                                        "`box_rest_after_settle_xyz` 就是从这条腿出来的 ⇒ **正向对照用它**"),
            "B_splice_as_coded": ("`reset(seed)` → `PRE._init_env_to_state(frame0_state, "
                                  "box_rest_after_settle_xyz)`（**现码原样**：写 xyz、不写四元数、"
                                  "`qvel=0`）→ 12 hold 步 ⇒ 直接量「拼接初态自己会不会动」"),
            "primary_quantity": ("`angle_diff_deg` = **max**(A0, A1 各自与沉降前四元数的测地角差)。"
                                 "取较大者 = 保守口径；**不许**挑好看的那条腿报"),
            "why_three_legs": ("A0 给「现码四元数从哪来」，A1 给「B2 的 rest 是怎么来的」（正向对照），"
                               "B 给「拼接初态的实际后果」。少任何一条，结论的作用域都会比证据宽"),
        },
        "criteria": {
            "C1_angle_diff_deg_max": {"op": "<=", "value": ANGLE_DIFF_DEG_MAX_THRESHOLD,
                                      "unit": "deg", "branch_role": "decides 甲/乙"},
            "C2_angle_diff_deg_median": {"op": "<=", "value": ANGLE_DIFF_DEG_MAX_THRESHOLD,
                                         "unit": "deg", "branch_role": "decides 甲/乙"},
            "C3_splice_rest_drift_xyz_m_max": {"op": "<=", "value": SPLICE_REST_DRIFT_XYZ_M_MAX,
                                               "unit": "m", "branch_role": "decides 甲/乙"},
            "C4_splice_rest_angle_deg_max": {"op": "<=", "value": SPLICE_REST_ANGLE_DEG_MAX,
                                             "unit": "deg", "branch_role": "decides 甲/乙"},
            "C5_settle_steps_dropped_set": {"op": "==", "value": [SETTLE_STEPS],
                                            "branch_role": "**有效性**控制（不符 ⇒ not_measured，不是乙）"},
            "C6_positive_control_rest_xyz_match_m": {
                "op": "<=", "value": REST_XYZ_MATCH_TOL_M, "unit": "m",
                "leg": "**A1**（写 sidecar 的 `box_spawn_xyz` 再沉降 12 步 = B2 产出 rest 的那条腿）",
                "branch_role": ("**有效性**控制（我的沉降必须复现 B2 记录的 rest；不符 ⇒ not_measured）"),
                "why_A1_not_A0": ("A0（纯 `reset(seed)`）在 reverse 集上与 sidecar 差一个**已登记的常量 "
                                  "x 偏移**（上游 `sample_box_pose` 的 x∈[0,0.2] vs B2 "
                                  "`sample_box_pose_seeded` 的 x∈[-0.2,0]）⇒ 拿 A0 比 sidecar 的**绝对**"
                                  "位置会把方向差误判成沉降腿的错。A0 的绝对残差**仍逐集落盘**，不删"),
                "revised_after_first_attempt": True,
                "revision_is_not_a_relaxation": ("修订只改**对照的作用域**（A0→A1），"
                                                 "**C1–C4 这四条决定甲/乙的阈值一个数字都没动**"
                                                 "（由 `verify_prereg.lineage_...` 机器核，见 "
                                                 "`prereg_revision_history`）")},
            "C7_negative_controls_all_bite": {"op": "==", "value": True,
                                              "branch_role": "**有效性**控制（对照不咬 ⇒ 判据是空的 ⇒ not_measured）"},
            "C8_no_arm_box_contact_during_settle": {"op": "==", "value": True,
                                                    "branch_role": ("**有效性**控制（沉降期臂若碰到方块，"
                                                                    "则「我用 hold 臂复刻 B2 的 R_DOWN 臂」"
                                                                    "对方块不等价 ⇒ not_measured）")},
            "C9_full_coverage_40_episodes": {"op": "==", "value": N_EPISODES_REQUIRED,
                                             "branch_role": ("**有效性**控制（裁定 104.3-④：40 集全量、"
                                                             "不抽样；`--episodes` 只用于冒烟，"
                                                             "覆盖不足 ⇒ not_measured，不是甲也不是乙）")},
        },
        "threshold_anchors": {
            "ANGLE_DIFF_DEG_MAX_THRESHOLD": {
                "value_deg": ANGLE_DIFF_DEG_MAX_THRESHOLD,
                "anchor_1_judge_has_no_orientation_term": {
                    "measured": anchors["judge_has_orientation_term"],
                    "why_it_anchors": ("判据不读姿态 ⇒ 姿态差要变成 verdict 差，必须先经过接触几何或像素；"
                                       "绕竖直轴的纯旋转对中心 xyz 恒等不变"),
                },
                "anchor_2_pixel_representability": {
                    "measured_backend": px.get("render_backend"),
                    "image_size": px.get("image_size"),
                    "n_px_total_base_cam": n_px_total,
                    "n_px_changed_at_1deg_base_cam": base_px_at_1deg,
                    "frac_at_1deg": (None if (not base_px_at_1deg or not n_px_total)
                                     else [round(v / float(n_px_total), 6) for v in base_px_at_1deg]),
                    "honest_reading": ("1.0° **不是**亚像素（base 相机确有像素变）⇒ 本阈值**不能**用"
                                       "「policy 看不见」来正当化；正当性只来自 anchor_1 + anchor_4"),
                    "self_consistency": px.get("self_consistency"),
                },
                "anchor_3_grasp_extent_geometry": {
                    "box_half_size_m_measured": [float(x) for x in
                                                 anchors["model_facts"]["box_geom_half_size"]],
                    "box_side_m": side,
                    "grasp_axis_extent_change_at_1deg_m": float(d_w_1deg),
                    "judge_grasp_max_dist_m": jt.get("grasp_max_dist_m"),
                    "ratio_to_grasp_tolerance": (None if not jt.get("grasp_max_dist_m")
                                                 else round(float(d_w_1deg)
                                                            / float(jt["grasp_max_dist_m"]), 6)),
                    "why_it_anchors": ("方块横截面是正方形 ⇒ 绕竖直轴转 1° 后沿固定抓取轴的外形宽度只增 "
                                       f"{float(d_w_1deg) * 1e3:.3f} mm，是 `grasp_max_dist_m` 的 "
                                       f"{(100.0 * float(d_w_1deg) / float(jt['grasp_max_dist_m'])):.2f}%"),
                },
                "anchor_4_branch_insensitivity_is_preregistered": (
                    "measure 阶段必须落 `threshold_insensitivity_report`：把 0.1/0.25/0.5/1/2/5° 六个阈值"
                    "各自会选出哪个分支都报出来 ⇒ 分支决定不是刀口上的裁量"),
            },
            "REST_XYZ_MATCH_TOL_M": {
                "value_m": REST_XYZ_MATCH_TOL_M,
                "anchor": floor,
                "why_it_anchors": ("sidecar 的 xyz 是 5 位小数舍入存的 ⇒ 表示地板 "
                                   f"{floor.get('floor_m')} m；容差取地板的 "
                                   f"{round(REST_XYZ_MATCH_TOL_M / float(floor.get('floor_m') or 1), 2)}× "
                                   "⇒ 比地板紧的容差量到的是 B2 的舍入，不是物理"),
            },
            "SPLICE_REST_DRIFT_XYZ_M_MAX": {
                "value_m": SPLICE_REST_DRIFT_XYZ_M_MAX,
                "anchor_1": ("= `REST_XYZ_MATCH_TOL_M` 的 10×，即「比 sidecar 表示地板松两个量级」，"
                             "避免把舍入当成漂移"),
                "anchor_2_judge_scale": {
                    "lift_min_height_m": jt.get("lift_min_height_m"),
                    "grasp_max_dist_m": jt.get("grasp_max_dist_m"),
                    "ratio_to_lift": (None if not jt.get("lift_min_height_m")
                                      else round(SPLICE_REST_DRIFT_XYZ_M_MAX
                                                 / float(jt["lift_min_height_m"]), 6)),
                    "ratio_to_grasp": (None if not jt.get("grasp_max_dist_m")
                                       else round(SPLICE_REST_DRIFT_XYZ_M_MAX
                                                  / float(jt["grasp_max_dist_m"]), 6)),
                },
            },
            "SPLICE_REST_ANGLE_DEG_MAX": {
                "value_deg": SPLICE_REST_ANGLE_DEG_MAX,
                "anchor": "与 C1 同锚（同一套 anchor_1..4），量的是拼接初态**自己**会不会转起来",
            },
        },
        "prereg_revision_history": {
            "lineage": prereg_lineage(out_dir),
            "note": ("逐版都由 `prereg_lineage()` **当场从盘上重读**（含 `before_images/` 里的历史件），"
                     "不靠记忆。**本件（正在写的这一版）不会出现在下面的列表里** —— 调用发生在本件落盘"
                     "之前，那时 current 路径上躺着的还是上一版；版本数看 `n_distinct_sha`，"
                     "不是 `n_files`"),
            "v1_481768aae5c3": ("首版预登记（脚本 `cfbf8cf6a4d8`）。作废原因：脚本自己的校验牙里"
                                "`sorted(['甲','乙','not_measured'])` 按码点序排，与字面顺序不符 ⇒ "
                                "咬出一把**假牙**（预登记本身没问题）。**没有阈值被移动**"),
            "v2_f9bb681527d7": ("第二版（脚本 `99be80c2e223`）。它下面跑的第一次 measure 返回 "
                                "`not_measured`（40/40 集）：末行 `c5_set.add(r[...])` 用了输出行的键名去索引"
                                "**数据集行** ⇒ KeyError；三值纪律让 40 行全部判 not_measured 而不是"
                                "静默通过。同时 NC-G 的**绝对位置**形态在 20 个 reverse 集上残差 "
                                "2.0e-1 m ⇒ 暴露出对照的作用域错（把已登记的方向差当成沉降腿错）"),
            "v3_this": ("修 KeyError + 拆 A0/A1 双沉降腿 + C6 重新定标到 A1 + 新增血缘牙与源码级佐证锚。"
                        "**C1–C4 四条决定甲/乙的阈值一个数字都没动**（1.0° / 1.0° / 1.0e-4 m / 1.0°），"
                        "由 `verify_prereg` 的 `lineage_branch_deciding_thresholds_never_moved` 机器核"),
        },
        "threshold_provenance": {
            "set_by": "A2（裁定 104.3-①：D 明示不代设数字）",
            "blind": False,
            "contamination_disclosure": {
                "what_was_seen_before_fixing_thresholds": [
                    {"item": "ep0 单集草稿探针（**非正式件**）",
                     "script": "tmp/a2_quat_anchor_probe.py",
                     "sha256_12": sha12(REPO / "tmp/a2_quat_anchor_probe.py"),
                     "artifact": "tmp/A2_QUAT_ANCHOR_PROBE.json",
                     "artifact_sha256_12": sha12(REPO / "tmp/A2_QUAT_ANCHOR_PROBE.json"),
                     "observed": "ep0 的 angle_diff_deg = 0.0（沉降前 [1,0,0,0] vs 沉降后 [1,-3.17e-18,-2.59e-17,-2.64e-34]）",
                     "consequence": "**阈值对 ep0 不盲**；本件不假装盲测"},
                    {"item": "像素锚需要构造 Step-1 那一帧 ⇒ 必然读到 ep0 的沉降前四元数",
                     "observed": "见 `anchors.pixel_sensitivity.base_quat_at_spliced_frame`"},
                    {"item": "**v2 预登记下面那次 measure 的 40 集读数**（件 `25288da9f7d1`，"
                             "已存为前像，未删）",
                     "observed": ("40/40 集 `angle_diff_deg = 0.0`、拼接漂移 3.5e-8 m、沉降期方块只接触 "
                                  "`table`；同时暴露 reverse 集 0.2 m 的方向差与那个 KeyError"),
                     "consequence": ("**A2 在成功跑之前已经看过 40 集的主量读数** ⇒ 本件**不是**盲测，"
                                     "不装作盲。防线不是「没看过」，而是：① C1–C4 阈值跨三版**逐字未动**"
                                     "（机器核）；② 分支决定是预登记规则的**纯函数**（`decide_branch` 里"
                                     "没有任何裁量分支）；③ `threshold_insensitivity_report` 报六个阈值各自"
                                     "会选出哪个分支 ⇒ 刀口不刀口一目了然；④ 两次 measure 的件都在盘上，"
                                     "可逐字节对账")},
                    {"item": "源码级佐证锚（`anchors.spawn_quat_source`）会读到两个 spawn 采样器"
                             "都把四元数硬编成 identity",
                     "observed": "见该锚；它与 40 集实测**互为独立**（一条读码、一条跑物理）",
                     "consequence": ("这条锚只能证明「**沉降前**是 identity」；「**沉降后**仍是 identity」"
                                     "是物理结论，源码不能替代 ⇒ 锚里带 `scope_caveat`")},
                ],
                "what_was_NOT_seen": ("v1/v2 预登记落盘的那一刻，40 集的 max/median 尚不存在于任何产物；"
                                      "**阈值是在看到任何一集结果之前定下的**，此后未动"),
                "mitigation": ("① 分支决定不靠阈值裁量：measure 阶段必须报 "
                               "`threshold_insensitivity_report`（六个阈值 × 各自分支）；"
                               "② 两分支的**处置程序**在本件里写死（见 `branch_procedures`），"
                               "跑完不再裁量（裁定 104.3）；③ 负对照必须先咬，否则整件 not_measured"),
            },
        },
        "branch_procedures": {
            "甲": {
                "trigger": "C1∧C2∧C3∧C4 全部成立（且 C5–C8 有效性控制全部成立）",
                "defect_key_status": "measured_and_immaterial",
                "action": ("Step-1 **按现码起跑、一个字节不改**（裁定 104.3）。"
                           "`demo_init_box_quat_not_written` 仍作为**已登记混淆项**随报告出，"
                           "不因为「量出来是 0」就销账（缺陷是码的形状，不是这一次的数值）"),
                "forbidden": "**不得**据此把 R2 的 RED 改判（裁定 104.1 记功那条纪律照旧）",
            },
            "乙": {
                "trigger": "C1∨C2∨C3∨C4 任一不成立（C5–C8 仍须成立，否则是 not_measured 不是乙）",
                "defect_key_status": "measured_and_material",
                "action": ("只允许**一处窄修**：`_init_env_to_state` 增写 `q[19:23]`（**只此一项**）。"
                           "改前落前像 + `criteria_identity`；判据常量一律不改"
                           "（R1R2 `7b2d6803a396`、Step-1 预登记 v2 的阈值/margin）；"
                           "以**预登记 v3 增补**的形式在**起跑之前**落盘（补单九 ③）"),
                "substitute_source_caveat": {
                    "problem": ("乙分支要写的是「**记录的** frame-0 四元数」，但实测："
                                "数据集与 sidecar **都不存任何四元数键**"),
                    "measured_evidence": anchors["sidecar_has_any_quaternion_key"],
                    "only_available_source": ("本件 `per_episode[].quat_post_settle_after_settle`"
                                              "（= 用 B2 的 12 步沉降在 CPU 上复现出来的姿态）"),
                    "requires": "**D 认可该替代来源**之后才允许窄修；未认可 ⇒ A2 不动先落腿件",
                    "why_not_silent": ("拿复现值当「记录值」是**换来源**，不是修 bug；"
                                       "静默换来源 = 又一处「件内声明的身份与盘上字节不符」"),
                },
            },
            "not_measured": {
                "trigger": "C5∨C6∨C7∨C8 任一不成立，或任何一集测不出来",
                "action": ("`measurement_status=not_measured` + `branch=null` + **非零退出**；"
                           "**不用 false/0 顶替**（三值纪律）。此时 Step-1 若已被守望器起跑，"
                           "按裁定 104.3 的竞态兜底：那一跑仍有效、不作废，但缺陷必须作为"
                           "已登记混淆项随报告出"),
            },
        },
        "negative_control_design": {
            "NC-A_estimator_known_pairs": ("合成已知角差的四元数对（0/0.5/1/15/90/180°，绕 x/y/z），"
                                           "断言估计器回读 |误差| ≤ 1e-6°"),
            "NC-B_signed_zero_not_conflated": ("`[1,0,0,0]` vs `[1,-0.0,-0.0,-0.0]`：断言角差 = 0.0 "
                                               "**且** 逐位不同 ⇒ 证明两个字段各携带信息、没被合并"),
            "NC-C_inject_15deg_about_z_must_flip": ("在指定集上把沉降后四元数人为转 15°，断言回读 "
                                                    "∈ 15°±0.1° **且** C1 翻（> 阈值）"),
            "NC-D_inject_15deg_tip_about_x_must_flip": "同上但绕 x（倾倒方向），断言 C1 翻",
            "NC-E_zero_injection_must_NOT_flip": ("注入 0°，断言角差与未注入值**逐位相同**且 C1 不翻 "
                                                  "⇒ 防「判据永远红」这种假对照"),
            "NC-F_splice_drift_detector_must_bite": ("在拼接初态上写入 15° 倾倒再走 12 hold 步，"
                                                     "断言 C3/C4 至少一条翻 ⇒ 证明漂移判据不是空的"),
            "NC-G_positive_control_settle_reproduces_sidecar": ("40 集全量：用 **A1** 腿（写 sidecar 的 "
                                                                "`box_spawn_xyz` 再沉降 12 步）复现出的 "
                                                                "**绝对** rest xyz 与 sidecar 的差 ≤ "
                                                                f"{REST_XYZ_MATCH_TOL_M} m ⇒ 证明参考腿"
                                                                "就是 B2 那条腿。另附**镜像不变**的位移对照"
                                                                "（沉降位移 vs `rest − spawn`）作为旁证"),
            "NC-H_no_arm_box_contact_during_settle": ("40 集全量：沉降 12 步里与方块接触的 geom 集合 "
                                                      "⊆ {table} ⇒ 证明「我用 hold 臂」与「B2 用 R_DOWN 臂」"
                                                      "**对方块等价**（B2 自己在 `:944`–`:947` 也这么论证，"
                                                      "这里改成实测）"),
            "all_bite_rule": "NC-A..NC-F 全部按预登记表现 **且** NC-G/NC-H 全过 ⇒ `all_bite=true`",
        },
        "dataset_side": {
            "npz_or_parquet_source": PRE.P_DS,
            "manifest": PRE.P_MANIFEST,
            "n_rows": init_block["n_rows"], "n_missing": init_block["n_missing"],
            "measurement_status": init_block["measurement_status"],
            "unique_seeds": init_block["unique_seeds"],
            "per_direction_counts": init_block["per_direction_counts"],
            "settle_steps_dropped_set": init_block["settle_steps_dropped_set"],
            "dt_set": init_block["dt_set"],
            "identities": {"dataset_info": identity(str(pathlib.Path(PRE.P_DS) / "meta" / "info.json")),
                           "demo_manifest": identity(PRE.P_MANIFEST),
                           "harness_env_gym_aloha": identity("harness/env_gym_aloha.py"),
                           "step1_prealign_verify": identity("scripts/a2_step1_prealign_verify.py"),
                           "step1_bc_overfit": identity("scripts/a2_step1_bc_overfit.py")},
        },
        "anchors": anchors,
        "consumed_by": {"function": CONSUMER_FUNC, "default_const": CONSUMER_DEFAULT_CONST,
                        "expected_artifact_path": MEASURE_REL,
                        "expected_keys": ["measurement_status", "branch_decision.branch",
                                          "branch_decision.rule", "aggregate.angle_diff_deg_max",
                                          "aggregate.angle_diff_deg_median", "aggregate.n_episodes",
                                          "aggregate.settle_steps_dropped_set",
                                          "negative_controls.all_bite"]},
        "exit_code_policy": ("0 = measured ∧ 分支 = **甲**（按现码起跑）· 1 = measured ∧ 分支 = **乙**"
                             "（= 主线阻塞红：窄修 + 预登记 v3 落盘之前不得起跑）· "
                             "2 = 用法错或**预登记校验不过**（脚本 sha 漂了 / 阈值被改 / 锚变了 ⇒ "
                             "不落半成品判词）· 3 = **not_measured**（有效性控制 C5–C8 有任一不成立，"
                             "或任何一集测不出来 ⇒ 分支 null，不用「乙」顶替「不知道」）"),
    }
    return doc


# ══════════════════════════ 阶段二：40 集全量测量 ══════════════════════════
def run_measure(args, rows: list[dict], init_block: dict, prereg: dict, prereg_id: dict) -> dict:
    from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
    from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv, GEOM_TABLE

    per_ep: list[dict] = []
    per_dir_env: dict = {}
    contact_geoms_seen: set = set()
    arm_box_contact_eps: list[int] = []
    nc_g_fail: list[dict] = []
    c5_set: set = set()
    t0 = time.perf_counter()

    for r in rows:
        d = r["env_direction"]
        if d not in per_dir_env:
            per_dir_env[d] = GymAlohaSimEnv(EnvSpec(direction=d, image_size=64,
                                                    render_images=False, seed=r["seed"]))
        jenv = per_dir_env[d]
        row: dict = {"episode_index": r["episode_index"], "ep_id": r["ep_id"], "seed": r["seed"],
                     "manifest_direction": r["manifest_direction"], "env_direction": d,
                     "settle_steps_dropped_sidecar": r["settle_steps_dropped"],
                     "box_spawn_xyz_sidecar": r["box_spawn_xyz"],
                     "box_rest_after_settle_xyz_sidecar": r["box_rest_after_settle_xyz"],
                     "measurement_status": "not_measured"}
        try:
            t_ep = time.perf_counter()
            # ── env A0：纯 `reset(seed)` → 12 hold 步（现码四元数的**真实来源**）──────
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            lay = box_qpos_layout(ph)
            x0, x1 = lay["xyz_slice"]
            q0, q1 = lay["quat_slice"]
            quat_pre = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
            xyz_at_reset = np.asarray(ph.data.qpos[x0:x1], dtype=np.float64).copy()
            a0 = settle_run(jenv, ph, x0, x1, q0, q1)
            # ── env A1：写 sidecar 的 `box_spawn_xyz` 再 12 hold 步（= B2 的真实初条件）──
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            a1 = settle_run(jenv, ph, x0, x1, q0, q1, write_spawn=r["box_spawn_xyz"])
            rest = np.asarray(r["box_rest_after_settle_xyz"], dtype=np.float64)
            spawn_side = np.asarray(r["box_spawn_xyz"], dtype=np.float64)
            disp_side = rest - spawn_side
            ang_a0 = quat_angle_deg(quat_pre, a0["quat_post"])
            ang_a1 = quat_angle_deg(quat_pre, a1["quat_post"])
            # 预登记口径：主量取**两条腿的较大者**（保守；不许挑好看的那条报）
            ang = max(ang_a0, ang_a1)
            contacts = set(a0["contacts"]) | set(a1["contacts"])
            resid = {"a0_abs": float(np.abs(a0["xyz_post"] - rest).max()),
                     "a1_abs": float(np.abs(a1["xyz_post"] - rest).max()),
                     "a0_disp": float(np.abs((a0["xyz_post"] - a0["xyz_pre"]) - disp_side).max()),
                     "a1_disp": float(np.abs((a1["xyz_post"] - a1["xyz_pre"]) - disp_side).max())}

            # ── env B：拼接腿（现码真正的初态）→ 12 hold 步 ────────────────────
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            init_info = PRE._init_env_to_state(jenv, np.asarray(r["frame0_state"], dtype=np.float64),
                                               r["box_rest_after_settle_xyz"], unorm)
            quat_splice = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
            xyz_splice = np.asarray(ph.data.qpos[x0:x1], dtype=np.float64).copy()
            readback = np.asarray(jenv._state(), dtype=np.float64).reshape(-1)[:STATE_DIM]
            rb_diff = float(np.abs(readback - np.asarray(r["frame0_state"], dtype=np.float64)).max())
            splice_contacts: set = set()
            for _ in range(SETTLE_STEPS):
                jenv.step(hold_action(jenv))
                splice_contacts |= box_contacts(ph)
            quat_splice_end = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
            xyz_splice_end = np.asarray(ph.data.qpos[x0:x1], dtype=np.float64).copy()

            allc = contacts | splice_contacts
            contact_geoms_seen |= allc
            arm_contact = bool(any(g is not None and g.startswith("vx300s") for g in allc))
            if arm_contact:
                arm_box_contact_eps.append(r["episode_index"])

            row.update({
                "measurement_status": "measured",
                "box_qpos_layout": {"xyz_slice": lay["xyz_slice"], "quat_slice": lay["quat_slice"],
                                    "joint_name": lay["box_joint_name"]},
                "quat_pre_settle_at_reset": [float(x) for x in quat_pre],
                "quat_pre_bit_pattern": [x.hex() for x in np.float64(quat_pre)],
                "env_A0_pure_reset_settle": {
                    "caliber": ("纯 `reset(seed)` 的 spawn（上游 `sample_box_pose`，x∈[0,0.2]，**不镜像**）"
                                "→ 12 hold 步。这一条是「现码留在初态里的四元数」的来源腿"),
                    "spawn_written": a0["spawn_written"],
                    "xyz_pre": [float(x) for x in a0["xyz_pre"]],
                    "quat_pre": [float(x) for x in a0["quat_pre"]],
                    "xyz_post": [float(x) for x in a0["xyz_post"]],
                    "quat_post": [float(x) for x in a0["quat_post"]],
                    "quat_post_bit_pattern": [x.hex() for x in np.float64(a0["quat_post"])],
                    "angle_diff_deg_vs_pre_settle": ang_a0,
                    "angle_diff_is_exact_zero": bool(ang_a0 == 0.0),
                    "quat_bitwise_identical": quat_bitwise_identical(quat_pre, a0["quat_post"]),
                    "quat_bitwise_identical_after_sign_norm": quat_bitwise_identical(
                        quat_normalize_sign(quat_pre), quat_normalize_sign(a0["quat_post"])),
                    "z_drop_m": a0["z_drop_m"],
                    "rest_xyz_residual_abs_m": resid["a0_abs"],
                    "rest_xyz_residual_displacement_m": resid["a0_disp"],
                    "contacts_during_settle": sorted(g for g in a0["contacts"] if g is not None),
                    "traj_first_last": a0["traj_first_last"],
                },
                "env_A1_sidecar_spawn_settle": {
                    "caliber": ("写 sidecar 的 `box_spawn_xyz`（reverse 的 x∈[-0.2,0]，B2 "
                               "`sample_box_pose_seeded`）→ 12 hold 步 = **B2 产出 "
                               "`box_rest_after_settle_xyz` 的那条腿** ⇒ 正向对照（NC-G）用它"),
                    "spawn_written": a1["spawn_written"],
                    "xyz_pre": [float(x) for x in a1["xyz_pre"]],
                    "quat_pre": [float(x) for x in a1["quat_pre"]],
                    "xyz_post": [float(x) for x in a1["xyz_post"]],
                    "quat_post": [float(x) for x in a1["quat_post"]],
                    "quat_post_bit_pattern": [x.hex() for x in np.float64(a1["quat_post"])],
                    "angle_diff_deg_vs_pre_settle": ang_a1,
                    "angle_diff_is_exact_zero": bool(ang_a1 == 0.0),
                    "quat_bitwise_identical": quat_bitwise_identical(quat_pre, a1["quat_post"]),
                    "z_drop_m": a1["z_drop_m"],
                    "rest_xyz_residual_abs_m": resid["a1_abs"],
                    "rest_xyz_residual_displacement_m": resid["a1_disp"],
                    "positive_control_rest_xyz_match": bool(resid["a1_abs"] <= REST_XYZ_MATCH_TOL_M),
                    "contacts_during_settle": sorted(g for g in a1["contacts"] if g is not None),
                    "traj_first_last": a1["traj_first_last"],
                },
                "angle_diff_deg": ang,
                "angle_diff_caliber": "**max(A0, A1)**（保守口径，预登记写死；不许挑好看的那条报）",
                "spawn_direction_offset": {
                    "sim_reset_xyz": [float(x) for x in xyz_at_reset],
                    "sidecar_spawn_xyz": [float(x) for x in spawn_side],
                    "offset_sidecar_minus_sim": [float(x) for x in (spawn_side - xyz_at_reset)],
                    "reset_reproduces_sidecar_spawn": bool(
                        np.abs(xyz_at_reset - spawn_side).max() <= REST_XYZ_MATCH_TOL_M),
                    "why_it_matters": ("reverse 集上 `reset(seed)` 的方块 x 与 sidecar 差一个**常量**偏移"
                                       "（同 rng、x 区间从 [0,0.2] 平移到 [-0.2,0]）⇒ 用 A0 去比 sidecar 的"
                                       "**绝对**位置会把这条已登记的方向差当成沉降腿的错。Step-1 自己"
                                       "**按 sidecar 写 box xyz**（`DemoInitAdapter` docstring），"
                                       "所以这条差不进 Step-1 的初态；本件只把它测出来、登记，不改判"),
                },
                "env_B_splice_as_coded": {
                    "init_info": init_info,
                    "quat_at_splice": [float(x) for x in quat_splice],
                    "xyz_at_splice": [float(x) for x in xyz_splice],
                    "quat_at_splice_bitwise_equals_pre_settle": quat_bitwise_identical(
                        quat_splice, quat_pre),
                    "xyz_at_splice_bitwise_equals_sidecar_rest": bool(np.array_equal(xyz_splice, rest)),
                    "readback_maxdiff_14d": rb_diff,
                    "readback_scope": "**只有 14 维机器人状态**（裁定 104.2：不含方块位姿）",
                    "quat_after_12_hold": [float(x) for x in quat_splice_end],
                    "xyz_after_12_hold": [float(x) for x in xyz_splice_end],
                    "splice_rest_drift_xyz_m": float(np.abs(xyz_splice_end - rest).max()),
                    "splice_rest_drift_xyz_vs_splice_m": float(
                        np.abs(xyz_splice_end - xyz_splice).max()),
                    "splice_rest_angle_deg": quat_angle_deg(quat_splice, quat_splice_end),
                    "contacts_during_splice_hold": sorted(g for g in splice_contacts if g is not None),
                },
                "arm_box_contact_during_settle": arm_contact,
                "wall_s": round(time.perf_counter() - t_ep, 3),
            })
            if not row["env_A1_sidecar_spawn_settle"]["positive_control_rest_xyz_match"]:
                nc_g_fail.append({"episode_index": r["episode_index"],
                                  "residual_m": resid["a1_abs"], "tol_m": REST_XYZ_MATCH_TOL_M})
            c5_set.add(r["settle_steps_dropped"])
        except Exception as exc:                                      # noqa: BLE001
            row.update({"measurement_status": "not_measured",
                        "error": f"{type(exc).__name__}: {exc}",
                        "why": "该集测不出来 ⇒ not_measured（不写 0、不跳过当通过）"})
        per_ep.append(row)

    meas = [r for r in per_ep if r["measurement_status"] == "measured"]
    n_measured = len(meas)

    def col(getter, seq=None):
        vals = [getter(r) for r in (seq if seq is not None else meas)]
        return vals

    ang_all = col(lambda r: r["angle_diff_deg"])
    ang_a0 = col(lambda r: r["env_A0_pure_reset_settle"]["angle_diff_deg_vs_pre_settle"])
    ang_a1 = col(lambda r: r["env_A1_sidecar_spawn_settle"]["angle_diff_deg_vs_pre_settle"])
    drift_xyz = col(lambda r: r["env_B_splice_as_coded"]["splice_rest_drift_xyz_m"])
    drift_ang = col(lambda r: r["env_B_splice_as_coded"]["splice_rest_angle_deg"])
    resid_a1_abs = col(lambda r: r["env_A1_sidecar_spawn_settle"]["rest_xyz_residual_abs_m"])
    resid_a0_abs = col(lambda r: r["env_A0_pure_reset_settle"]["rest_xyz_residual_abs_m"])
    disp_resid = col(lambda r: max(r["env_A0_pure_reset_settle"]["rest_xyz_residual_displacement_m"],
                                   r["env_A1_sidecar_spawn_settle"]["rest_xyz_residual_displacement_m"]))
    z_drop = col(lambda r: r["env_A1_sidecar_spawn_settle"]["z_drop_m"])

    def by_dir(key_fn):
        out = {}
        for r in meas:
            out.setdefault(r["manifest_direction"], []).append(key_fn(r))
        return {k: {"n": len(v), "max": max(v), "min": min(v)} for k, v in sorted(out.items())}

    mirror = by_dir(lambda r: r["spawn_direction_offset"]["offset_sidecar_minus_sim"][0])
    reset_repro = by_dir(lambda r: float(
        np.abs(np.asarray(r["spawn_direction_offset"]["sim_reset_xyz"], dtype=np.float64)
               - np.asarray(r["spawn_direction_offset"]["sidecar_spawn_xyz"], dtype=np.float64)).max()))
    nc = run_negative_controls(args, rows, per_ep, ang_all)
    aggregate = {
        "measurement_status": "measured" if (n_measured == len(rows) and rows) else "not_measured",
        "n_episodes": len(rows),
        "n_episodes_measured": n_measured,
        "n_episodes_not_measured": len(rows) - n_measured,
        "sampling": "全量、不抽样（裁定 104.3-④）",
        "angle_diff_deg_max": (max(ang_all) if ang_all else None),
        "angle_diff_deg_median": (float(np.median(ang_all)) if ang_all else None),
        "angle_diff_deg_min": (min(ang_all) if ang_all else None),
        "angle_diff_deg_distinct_values": sorted({float(x) for x in ang_all}),
        "angle_diff_caliber": "**max(A0, A1)**（保守；A0 = 纯 reset 沉降，A1 = 写 sidecar spawn 沉降）",
        "angle_diff_deg_max_A0": (max(ang_a0) if ang_a0 else None),
        "angle_diff_deg_max_A1": (max(ang_a1) if ang_a1 else None),
        "n_angle_diff_exact_zero": sum(1 for x in ang_all if x == 0.0),
        "n_quat_bitwise_identical_A0": sum(
            1 for r in meas if r["env_A0_pure_reset_settle"]["quat_bitwise_identical"]),
        "n_quat_bitwise_identical_after_sign_norm_A0": sum(
            1 for r in meas if r["env_A0_pure_reset_settle"]["quat_bitwise_identical_after_sign_norm"]),
        "bitwise_vs_numeric_gap_explained": (
            "两个计数不同不是矛盾：沉降后的虚部是 -0.0 / 次正规数 ⇒ **角差恰为 0.0** 但**逐位不同**。"
            "正式件把两者分开报，不合并成一个布尔（合并 = 又一次证据作用域窄于结论作用域）"),
        "settle_steps_dropped_set": sorted(x for x in c5_set if x is not None),
        "splice_rest_drift_xyz_m_max": (max(drift_xyz) if drift_xyz else None),
        "splice_rest_drift_xyz_m_median": (float(np.median(drift_xyz)) if drift_xyz else None),
        "splice_rest_angle_deg_max": (max(drift_ang) if drift_ang else None),
        "splice_rest_angle_deg_median": (float(np.median(drift_ang)) if drift_ang else None),
        "positive_control_rest_xyz_residual_m_max": (max(resid_a1_abs) if resid_a1_abs else None),
        "positive_control_caliber": ("**A1** 腿（写 sidecar spawn 再沉降 = B2 的真实初条件）的"
                                     "**绝对** rest xyz 残差；A0 的绝对残差另见 "
                                     "`spawn_direction_offset_by_direction`（reverse 上是已登记的方向差，"
                                     "**不是**沉降腿的错）"),
        "A0_absolute_residual_m_max": (max(resid_a0_abs) if resid_a0_abs else None),
        "settle_displacement_residual_m_max": (max(disp_resid) if disp_resid else None),
        "settle_displacement_residual_caliber": ("**镜像不变**的对照：沉降位移(sim) vs "
                                                 "`sidecar_rest − sidecar_spawn`；这条在 40 集上"
                                                 "都成立，与方向无关"),
        "spawn_direction_offset_by_direction": {
            "value_x_offset_sidecar_minus_sim": mirror,
            "reset_reproduces_sidecar_spawn_abs_residual_m": reset_repro,
            "finding": ("forward：`reset(seed)` 的 spawn 与 sidecar 一致（残差 = sidecar 的 5 位小数"
                        "表示地板量级）；reverse：差一个**常量 x 偏移**（同 rng、x 区间从 [0,0.2] "
                        "平移到 [-0.2,0]，B2 `sample_box_pose_seeded` + `SPAWN_RANGE`）"),
            "already_registered_where": ("`scripts/a2_step1_bc_overfit.py::DemoInitAdapter` docstring"
                                         "（「`reset(seed)` 的方块复现只在 forward 方向成立」）+ "
                                         "先落腿 L9 的 `reset_seed_reproduces_box_xy`"),
            "does_it_enter_step1_initial_state": ("**不进**：Step-1 按 sidecar 写 box xyz，"
                                                  "不用 `reset(seed)` 的位置 ⇒ 本件只登记、不改判"),
        },
        "box_z_drop_m_min_max": ([min(z_drop), max(z_drop)] if z_drop else None),
        "contact_geoms_seen_with_box": sorted(g for g in contact_geoms_seen if g is not None),
        "table_geom_name": GEOM_TABLE,
        "arm_box_contact_episodes": arm_box_contact_eps,
        "wall_s_total": round(time.perf_counter() - t0, 2),
        "wall_s_per_episode_max": (max(col(lambda r: r["wall_s"])) if meas else None),
    }
    return {"per_episode": per_ep, "aggregate": aggregate, "negative_controls": nc,
            "arm_box_contact_episodes": arm_box_contact_eps,
            "positive_control_failures": nc_g_fail}


def run_negative_controls(args, rows: list[dict], per_ep: list[dict], ang_all: list[float]) -> dict:
    """8 组对照。NC-A/B 是纯数值，NC-C/D/E/F 要 env（CPU、osmesa），NC-G/H 直接从 40 集读数汇总。"""
    from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
    from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
    out: dict = {"as_of": now_iso(), "controls": {}, "all_bite": None,
                 "measurement_status": "not_measured"}
    thr = ANGLE_DIFF_DEG_MAX_THRESHOLD
    try:
        # ── NC-A：估计器已知角差 ────────────────────────────────────────────
        iz = np.array([1.0, 0.0, 0.0, 0.0])
        known = []
        for ax_name, ax in PIXEL_ANCHOR_AXES:
            for deg in (0.0, 0.5, 1.0, 15.0, 90.0, 180.0):
                got = quat_angle_deg(iz, quat_from_axis_angle(ax, deg))
                known.append({"axis": ax_name, "expected_deg": deg, "readback_deg": got,
                              "abs_err_deg": abs(got - deg), "pass": bool(abs(got - deg) <= 1e-6)})
        dbl = quat_angle_deg(iz, -iz)
        out["controls"]["NC-A_estimator_known_pairs"] = {
            "rows": known, "n_pass": sum(1 for k in known if k["pass"]), "n": len(known),
            "double_cover_q_vs_minus_q_deg": dbl,
            "double_cover_pass": bool(dbl == 0.0),
            "bites": bool(all(k["pass"] for k in known) and dbl == 0.0)}

        # ── NC-B：符号零 / 次正规数不与数值相等混为一谈 ───────────────────────
        qa = np.array([1.0, 0.0, 0.0, 0.0])
        qb = np.array([1.0, -0.0, -0.0, -0.0])
        out["controls"]["NC-B_signed_zero_not_conflated"] = {
            "q_a": [float(x) for x in qa], "q_b": [float(x) for x in qb],
            "angle_deg": quat_angle_deg(qa, qb),
            "np_array_equal": bool(np.array_equal(qa, qb)),
            "bitwise_identical": quat_bitwise_identical(qa, qb),
            "expected": {"angle_deg": 0.0, "np_array_equal": True, "bitwise_identical": False},
            "bites": bool(quat_angle_deg(qa, qb) == 0.0 and np.array_equal(qa, qb)
                          and not quat_bitwise_identical(qa, qb)),
            "why": ("ep0 探针实测沉降后虚部是负零/次正规 ⇒ 若只报一个布尔就会把"
                    "「数值相等」和「逐位相同」混成一件事，正是裁定 104.2 批评的那种作用域错配")}

        # ── NC-C/D/E/F：需要 env ────────────────────────────────────────────
        r0 = rows[0]
        jenv = GymAlohaSimEnv(EnvSpec(direction=r0["env_direction"], image_size=64,
                                      render_images=False, seed=r0["seed"]))
        jenv.reset(seed=r0["seed"])
        ph = jenv.physics
        lay = box_qpos_layout(ph)
        x0, x1 = lay["xyz_slice"]
        q0, q1 = lay["quat_slice"]
        quat_pre = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
        for _ in range(SETTLE_STEPS):
            jenv.step(hold_action(jenv))
        quat_post = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
        base_ang = quat_angle_deg(quat_pre, quat_post)

        inj_rows = []
        for tag, ax, deg, expect_flip in (
                ("NC-C_inject_15deg_about_z", (0.0, 0.0, 1.0), NC_INJECT_DEG, True),
                ("NC-D_inject_15deg_tip_about_x", (1.0, 0.0, 0.0), NC_INJECT_DEG, True),
                ("NC-E_zero_injection", (0.0, 0.0, 1.0), 0.0, False)):
            q_inj = quat_mul(quat_from_axis_angle(ax, deg), quat_post)
            got = quat_angle_deg(quat_pre, q_inj)
            flipped = bool(got > thr)
            inj_rows.append({
                "control": tag, "axis": list(ax), "injected_deg": float(deg),
                "readback_angle_deg": got,
                "readback_within_tol": bool(abs(got - deg) <= NC_INJECT_TOL_DEG) if deg > 0 else
                                         bool(got == base_ang),
                "criterion_c1_value": got, "threshold_deg": thr,
                "c1_fails_after_injection": flipped, "expected_to_flip": expect_flip,
                "flip_observed_as_expected": bool(flipped == expect_flip),
                "bitwise_identical_to_uninjected": quat_bitwise_identical(q_inj, quat_post)})
        by = {r["control"]: r for r in inj_rows}
        out["controls"]["NC-CDE_injection"] = {
            "episode_index": r0["episode_index"], "seed": r0["seed"],
            "uninjected_angle_diff_deg": base_ang, "rows": inj_rows,
            "NC-C_bites": bool(by["NC-C_inject_15deg_about_z"]["flip_observed_as_expected"]
                               and by["NC-C_inject_15deg_about_z"]["readback_within_tol"]),
            "NC-D_bites": bool(by["NC-D_inject_15deg_tip_about_x"]["flip_observed_as_expected"]
                               and by["NC-D_inject_15deg_tip_about_x"]["readback_within_tol"]),
            "NC-E_bites": bool(by["NC-E_zero_injection"]["flip_observed_as_expected"]
                               and by["NC-E_zero_injection"]["readback_within_tol"]
                               and by["NC-E_zero_injection"]["bitwise_identical_to_uninjected"]),
            "bites": bool(by["NC-C_inject_15deg_about_z"]["flip_observed_as_expected"]
                          and by["NC-D_inject_15deg_tip_about_x"]["flip_observed_as_expected"]
                          and by["NC-E_zero_injection"]["flip_observed_as_expected"]
                          and all(r["readback_within_tol"] for r in inj_rows))}

        # NC-F：拼接初态上写 15° 倾倒 ⇒ 漂移判据必须翻
        jenv.reset(seed=r0["seed"])
        ph = jenv.physics
        PRE._init_env_to_state(jenv, np.asarray(r0["frame0_state"], dtype=np.float64),
                               r0["box_rest_after_settle_xyz"], unorm)
        rest = np.asarray(r0["box_rest_after_settle_xyz"], dtype=np.float64)
        q_base = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
        ph.data.qpos[q0:q1] = quat_mul(quat_from_axis_angle((1.0, 0.0, 0.0), NC_INJECT_DEG), q_base)
        ph.data.qvel[:] = 0.0
        ph.forward()
        q_tip = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
        z_at_tip = float(ph.data.qpos[x0:x1][2])
        for _ in range(SETTLE_STEPS):
            jenv.step(hold_action(jenv))
        q_end = np.asarray(ph.data.qpos[q0:q1], dtype=np.float64).copy()
        xyz_end = np.asarray(ph.data.qpos[x0:x1], dtype=np.float64).copy()
        d_xyz = float(np.abs(xyz_end - rest).max())
        d_ang = quat_angle_deg(q_tip, q_end)
        c3_flip = bool(d_xyz > SPLICE_REST_DRIFT_XYZ_M_MAX)
        c4_flip = bool(d_ang > SPLICE_REST_ANGLE_DEG_MAX)
        out["controls"]["NC-F_splice_drift_detector"] = {
            "episode_index": r0["episode_index"], "injected_tip_deg": NC_INJECT_DEG,
            "injected_axis": [1.0, 0.0, 0.0],
            "readback_injected_angle_vs_base_deg": quat_angle_deg(q_base, q_tip),
            "box_z_at_tip_m": z_at_tip,
            "drift_xyz_m_after_12_hold": d_xyz, "threshold_m": SPLICE_REST_DRIFT_XYZ_M_MAX,
            "c3_flips": c3_flip,
            "drift_angle_deg_after_12_hold": d_ang, "threshold_deg": SPLICE_REST_ANGLE_DEG_MAX,
            "c4_flips": c4_flip,
            "xyz_end": [float(x) for x in xyz_end],
            "bites": bool(c3_flip or c4_flip),
            "why": ("若两条都不翻 ⇒ C3/C4 是空判据（永远绿），那么「甲」就没有证据力；"
                    "这一条就是防这个的")}

        # NC-G / NC-H：从 40 集读数汇总
        meas = [r for r in per_ep if r["measurement_status"] == "measured"]
        g_fail = [r["episode_index"] for r in meas
                  if not r["env_A1_sidecar_spawn_settle"]["positive_control_rest_xyz_match"]]
        h_fail = [r["episode_index"] for r in meas if r["arm_box_contact_during_settle"]]
        out["controls"]["NC-G_positive_control_settle_reproduces_sidecar"] = {
            "n_episodes": len(meas), "tol_m": REST_XYZ_MATCH_TOL_M,
            "n_fail": len(g_fail), "fail_episodes": g_fail,
            "max_residual_m": (max(r["env_A1_sidecar_spawn_settle"]["rest_xyz_residual_abs_m"]
                                   for r in meas) if meas else None),
            "bites": bool(meas and not g_fail),
            "caliber": ("用 **A1** 腿（写 sidecar 的 `box_spawn_xyz` 再沉降 12 步）比 sidecar 的"
                        "**绝对** rest xyz；这是 B2 产出该字段的同一条腿。"
                        "**不用 A0**：A0 在 reverse 集上差一个已登记的常量 x 偏移（0.2 m 量级），"
                        "拿它当正向对照会把方向差误判成沉降腿的错（本件第一版就错在这里）"),
            "semantics": "**正向**对照：不成立 ⇒ 参考腿不是 B2 那条腿 ⇒ 整件 not_measured"}
        out["controls"]["NC-H_no_arm_box_contact_during_settle"] = {
            "n_episodes": len(meas), "n_fail": len(h_fail), "fail_episodes": h_fail,
            "bites": bool(meas and not h_fail),
            "semantics": ("**等价性**对照：成立 ⇒ 沉降期方块只与桌面接触 ⇒「我用 hold 臂」与"
                          "「B2 用 R_DOWN 臂」对**方块姿态**等价（B2 在 `:944`–`:947` 是几何论证，"
                          "这里改成实测）；不成立 ⇒ 等价性没了 ⇒ 整件 not_measured")}

        keys = ["NC-A_estimator_known_pairs", "NC-B_signed_zero_not_conflated", "NC-CDE_injection",
                "NC-F_splice_drift_detector", "NC-G_positive_control_settle_reproduces_sidecar",
                "NC-H_no_arm_box_contact_during_settle"]
        bites = {k: bool(out["controls"][k].get("bites")) for k in keys}
        out["bites_per_control"] = bites
        out["all_bite"] = bool(all(bites.values())) and bool(meas)
        out["measurement_status"] = "measured"
    except Exception as exc:                                          # noqa: BLE001
        out.update({"measurement_status": "not_measured", "all_bite": None,
                    "error": f"{type(exc).__name__}: {exc}",
                    "why": "对照腿抛异常 ⇒ not_measured（**不许**当成「对照通过」）"})
    return out


def decide_branch(aggregate: dict, nc: dict, per_ep: list[dict], arm_eps: list[int]) -> dict:
    """分支决定 = **纯函数**，规则逐字来自预登记；跑完不裁量（裁定 104.3）。"""
    C = aggregate["criteria"] = {}
    thr = ANGLE_DIFF_DEG_MAX_THRESHOLD
    ok = aggregate["measurement_status"] == "measured"
    C["C1_angle_diff_deg_max"] = {"value": aggregate["angle_diff_deg_max"], "op": "<=",
                                  "threshold": thr,
                                  "pass": (None if aggregate["angle_diff_deg_max"] is None
                                           else bool(aggregate["angle_diff_deg_max"] <= thr))}
    C["C2_angle_diff_deg_median"] = {"value": aggregate["angle_diff_deg_median"], "op": "<=",
                                     "threshold": thr,
                                     "pass": (None if aggregate["angle_diff_deg_median"] is None
                                              else bool(aggregate["angle_diff_deg_median"] <= thr))}
    C["C3_splice_rest_drift_xyz_m_max"] = {
        "value": aggregate["splice_rest_drift_xyz_m_max"], "op": "<=",
        "threshold": SPLICE_REST_DRIFT_XYZ_M_MAX,
        "pass": (None if aggregate["splice_rest_drift_xyz_m_max"] is None
                 else bool(aggregate["splice_rest_drift_xyz_m_max"] <= SPLICE_REST_DRIFT_XYZ_M_MAX))}
    C["C4_splice_rest_angle_deg_max"] = {
        "value": aggregate["splice_rest_angle_deg_max"], "op": "<=",
        "threshold": SPLICE_REST_ANGLE_DEG_MAX,
        "pass": (None if aggregate["splice_rest_angle_deg_max"] is None
                 else bool(aggregate["splice_rest_angle_deg_max"] <= SPLICE_REST_ANGLE_DEG_MAX))}
    C["C5_settle_steps_dropped_set"] = {
        "value": aggregate["settle_steps_dropped_set"], "op": "==", "threshold": [SETTLE_STEPS],
        "pass": (None if not ok else bool(aggregate["settle_steps_dropped_set"] == [SETTLE_STEPS]))}
    C["C6_positive_control_rest_xyz_match_m"] = {
        "value": aggregate["positive_control_rest_xyz_residual_m_max"], "op": "<=",
        "threshold": REST_XYZ_MATCH_TOL_M,
        "pass": (nc.get("controls", {}).get("NC-G_positive_control_settle_reproduces_sidecar", {})
                 .get("bites"))}
    C["C7_negative_controls_all_bite"] = {"value": nc.get("all_bite"), "op": "==",
                                          "threshold": True, "pass": nc.get("all_bite")}
    C["C8_no_arm_box_contact_during_settle"] = {
        "value": arm_eps, "op": "==", "threshold": [],
        "pass": (nc.get("controls", {}).get("NC-H_no_arm_box_contact_during_settle", {})
                 .get("bites"))}
    C["C9_full_coverage_40_episodes"] = {
        "value": aggregate["n_episodes_measured"], "op": "==", "threshold": N_EPISODES_REQUIRED,
        "pass": (None if not ok else bool(aggregate["n_episodes_measured"] == N_EPISODES_REQUIRED
                                          and aggregate["n_episodes"] == N_EPISODES_REQUIRED))}

    validity = ["C5_settle_steps_dropped_set", "C6_positive_control_rest_xyz_match_m",
                "C7_negative_controls_all_bite", "C8_no_arm_box_contact_during_settle",
                "C9_full_coverage_40_episodes"]
    deciding = ["C1_angle_diff_deg_max", "C2_angle_diff_deg_median",
                "C3_splice_rest_drift_xyz_m_max", "C4_splice_rest_angle_deg_max"]
    v_vals = [C[k]["pass"] for k in validity]
    d_vals = [C[k]["pass"] for k in deciding]
    if not ok or any(v is not True for v in v_vals) or any(v is None for v in d_vals):
        branch, status = None, "not_measured"
        rule = ("有效性控制（C5–C8）有任一不成立，或有集测不出来 ⇒ **not_measured**，"
                "分支为 null（三值纪律：不用「乙」顶替「不知道」）")
    elif all(v is True for v in d_vals):
        branch, status = "甲", "measured"
        rule = (f"C1–C4 全部成立（max={aggregate['angle_diff_deg_max']}° ≤ {thr}°，"
                f"median={aggregate['angle_diff_deg_median']}°；拼接漂移 "
                f"xyz={aggregate['splice_rest_drift_xyz_m_max']} m ≤ {SPLICE_REST_DRIFT_XYZ_M_MAX}，"
                f"angle={aggregate['splice_rest_angle_deg_max']}° ≤ {SPLICE_REST_ANGLE_DEG_MAX}°）"
                "⇒ **甲**：`measured_and_immaterial`，Step-1 按现码起跑、一个字节不改；"
                "缺陷仍作为已登记混淆项随报告出，**不销账**")
    else:
        branch, status = "乙", "measured"
        rule = (f"C1–C4 有 {[k for k in deciding if C[k]['pass'] is not True]} 不成立 ⇒ **乙**："
                "`measured_and_material`，只允许一处窄修（`_init_env_to_state` 增写 `q[19:23]`），"
                "改前落前像 + `criteria_identity`，判据常量一律不改，以预登记 v3 增补在起跑前落盘；"
                "**且替代来源须先经 D 认可**（数据集/sidecar 不存四元数）")

    insens = []
    for t in THRESHOLD_INSENSITIVITY_DEGS:
        if aggregate["angle_diff_deg_max"] is None or aggregate["angle_diff_deg_median"] is None:
            insens.append({"threshold_deg": t, "branch": None})
            continue
        would = ("甲" if (aggregate["angle_diff_deg_max"] <= t
                          and aggregate["angle_diff_deg_median"] <= t
                          and C["C3_splice_rest_drift_xyz_m_max"]["pass"] is True
                          and C["C4_splice_rest_angle_deg_max"]["pass"] is True) else "乙")
        insens.append({"threshold_deg": t, "branch": would,
                       "same_as_preregistered": bool(would == branch)})
    return {"branch": branch, "rule": rule, "measurement_status": status,
            "criteria": C, "validity_controls": validity, "branch_deciding_criteria": deciding,
            "threshold_insensitivity_report": insens,
            "threshold_insensitivity_note": ("预登记要求（`anchor_4`）：把六个阈值各自会选出的分支都报出来，"
                                             "证明分支决定不是刀口上的裁量"),
            "defect_key_status": ({"甲": "measured_and_immaterial",
                                   "乙": "measured_and_material"}.get(branch) if branch else
                                  "not_measured"),
            "does_not_change_r2_verdict": True,
            "r2_note": ("裁定 104.1 记功那条纪律照旧：本件**不**因为量出 0.0 就去动 R2 的 RED 或"
                        "14 个 `grip2` 例外（那是事后改判据）")}


PREREG_NAME = "DEMO_INIT_BOX_QUAT_PREREG.json"
THRESHOLD_KEYS = ("C1_angle_diff_deg_max", "C2_angle_diff_deg_median",
                  "C3_splice_rest_drift_xyz_m_max", "C4_splice_rest_angle_deg_max",
                  "C5_settle_steps_dropped_set", "C6_positive_control_rest_xyz_match_m",
                  "C9_full_coverage_40_episodes")


def prereg_lineage(out_dir: pathlib.Path) -> dict:
    """把**所有版本**的预登记件（当前件 + `before_images/` 里的历史件）按时间排开，逐版取
    `producer.sha256_12` 与判据阈值。两个用途：
      ① 写进新预登记的 `prereg_revision_history`（修订史可核，不靠记忆）；
      ② 给 `verify_prereg` 一把牙：**分支决定用的阈值（C1–C4）从未被移动**。
         这条主张必须是机器核出来的，不能是 A2 自己写一句「我没改」。
    """
    files: list[pathlib.Path] = []
    cur = out_dir / PREREG_NAME
    if cur.exists():
        files.append(cur)
    bi = out_dir / "before_images"
    if bi.is_dir():
        files.extend(sorted(bi.glob(f"{PREREG_NAME}.before_*")))
    versions = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            crit = d.get("criteria") or {}
            versions.append({
                "path": (str(f.relative_to(REPO)) if f.is_relative_to(REPO) else str(f)),
                "sha256_12": sha12(f), "as_of": d.get("as_of"),
                "mtime": f.stat().st_mtime,
                "producer_script_sha256_12": (d.get("producer") or {}).get("sha256_12"),
                "thresholds": {k: (crit.get(k) or {}).get("value") for k in THRESHOLD_KEYS},
                # `is_at_current_path` **不是**「这是最新一版」：在 `--stage prereg` 里调用本函数时，
                # current 路径上躺着的还是**上一版**（新版此刻尚未落盘）⇒ 字段名必须说清它指的是路径，
                # 不是版本序。把「路径」当「版本」报 = A2-SD-08（身份字段误导）的同型，不许再犯。
                "is_at_current_path": bool(f == cur),
                "role": ("predecessor_still_at_current_path" if f == cur else "before_image")})
        except Exception as exc:                                      # noqa: BLE001
            versions.append({"path": str(f), "sha256_12": sha12(f), "parse_error":
                             f"{type(exc).__name__}: {exc}", "is_current": bool(f == cur)})
    versions.sort(key=lambda v: (v.get("mtime") or 0.0))
    branch_deciding = ("C1_angle_diff_deg_max", "C2_angle_diff_deg_median",
                       "C3_splice_rest_drift_xyz_m_max", "C4_splice_rest_angle_deg_max")
    distinct = {k: sorted({json.dumps(v["thresholds"].get(k), sort_keys=True, default=str)
                           for v in versions if "thresholds" in v}) for k in branch_deciding}
    constant = bool(versions) and all(len(v) == 1 for v in distinct.values())
    shas = [v.get("sha256_12") for v in versions if v.get("sha256_12")]
    return {"measurement_status": "measured" if versions else "not_measured",
            "n_files": len(versions),
            "n_distinct_sha": len(set(shas)),
            "n_files_caliber": ("**文件数**，不是版本数：同一份字节可能同时躺在 current 路径与它的"
                                "前像里（`--stage prereg` 会先把上一版存成前像，再写新版）⇒ "
                                "版本数一律看 `n_distinct_sha`，别把文件数当版本数读"),
            "versions": versions,
            "branch_deciding_threshold_keys": list(branch_deciding),
            "distinct_values_per_key": distinct,
            "branch_deciding_thresholds_never_moved": constant,
            "caliber": ("**只**核 C1–C4（决定甲/乙的那四条）。C6 是**有效性**控制的容差，"
                        "它在修订史里被**重新定标**过（A0 绝对位置 → A1 绝对位置），"
                        "那是修对照的作用域，不是放松分支判据；两者分开核，不混为一谈")}


# ══════════════════════════ 预登记校验（**跑之前**，漂了就拒绝）══════════════════════════
def verify_prereg(prereg: dict, *, script_sha: str, rows_n: int,
                  out_dir_for_lineage: pathlib.Path | None = None) -> dict:
    """裁定 104.3「两分支都预登记、跑完不裁量」的**牙**：measure 阶段必须证明
    ① 预登记是**本脚本这个字节版本**落的（否则阈值可能被事后移动 = A2-SD-08 的同型）；
    ② 预登记里的阈值与本件的模块常量**逐字相同**；
    ③ 阈值所依赖的**实测锚**（模型几何 / 判据阈值 / sidecar 表示地板）**当场重测仍成立**。
    任一不过 ⇒ `refused`，exit 2，**不落半成品判词**。
    """
    checks: list[dict] = []
    out_dir_for_lineage = out_dir_for_lineage or (REPO / OUT_DIR_DEFAULT)

    def chk(name: str, expected, got, *, fatal: bool = True):
        same = bool(expected == got)
        checks.append({"check": name, "expected": expected, "got": got, "pass": same,
                       "fatal": fatal})
        return same

    prod = (prereg.get("producer") or {})
    chk("prereg_produced_by_this_script_bytes", script_sha, prod.get("sha256_12"))
    crit = (prereg.get("criteria") or {})
    chk("C1_threshold_deg", ANGLE_DIFF_DEG_MAX_THRESHOLD,
        (crit.get("C1_angle_diff_deg_max") or {}).get("value"))
    chk("C2_threshold_deg", ANGLE_DIFF_DEG_MAX_THRESHOLD,
        (crit.get("C2_angle_diff_deg_median") or {}).get("value"))
    chk("C3_threshold_m", SPLICE_REST_DRIFT_XYZ_M_MAX,
        (crit.get("C3_splice_rest_drift_xyz_m_max") or {}).get("value"))
    chk("C4_threshold_deg", SPLICE_REST_ANGLE_DEG_MAX,
        (crit.get("C4_splice_rest_angle_deg_max") or {}).get("value"))
    chk("C5_settle_steps", [SETTLE_STEPS], (crit.get("C5_settle_steps_dropped_set") or {}).get("value"))
    chk("C6_tol_m", REST_XYZ_MATCH_TOL_M,
        (crit.get("C6_positive_control_rest_xyz_match_m") or {}).get("value"))
    chk("C9_n_episodes", N_EPISODES_REQUIRED,
        (crit.get("C9_full_coverage_40_episodes") or {}).get("value"))
    chk("prereg_n_episodes", N_EPISODES_REQUIRED,
        (prereg.get("what_is_measured") or {}).get("n_episodes"))
    chk("rows_available_now", N_EPISODES_REQUIRED, rows_n)
    bp = prereg.get("branch_procedures") or {}
    # 集合比较，不用 `sorted()`：中/日文字与 ascii 混排时 `sorted` 按码点序，与字面顺序无关，
    # 拿它当判据会造出一把**假牙**（本件第一版就咬在这里：预登记没问题，是校验自己写错了）。
    chk("branch_procedures_preregistered", ["not_measured", "乙", "甲"],
        sorted(bp.keys(), key=lambda s: (not s.isascii(), s)))
    for b in ("甲", "乙", "not_measured"):
        chk(f"branch_{b}_has_action", True, bool((bp.get(b) or {}).get("action")))
    chk("negative_control_design_preregistered", 8,
        len([k for k in (prereg.get("negative_control_design") or {}) if k.startswith("NC-")]))
    chk("threshold_insensitivity_preregistered", True,
        "anchor_4_branch_insensitivity_is_preregistered"
        in ((prereg.get("threshold_anchors") or {}).get("ANGLE_DIFF_DEG_MAX_THRESHOLD") or {}))

    # ── 锚当场重测（模型/判据变了 ⇒ 阈值的正当性没了）────────────────────────
    try:
        from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
        jenv = GymAlohaSimEnv(EnvSpec(direction="right_to_left", image_size=64,
                                      render_images=False, seed=0))
        jenv.reset(seed=0)
        live = box_qpos_layout(jenv.physics)
        live_jt = jenv.spec.thresholds.as_dict()
        pre_mf = ((prereg.get("anchors") or {}).get("model_facts") or {})
        for k in ("nq", "nv", "nu", "nmocap", "neq", "box_qposadr", "box_joint_name",
                  "box_geom_half_size", "box_geom_type", "timestep", "xyz_slice", "quat_slice"):
            chk(f"anchor_model_facts.{k}", pre_mf.get(k), live.get(k))
        chk("anchor_judge_thresholds", (prereg.get("anchors") or {}).get("judge_thresholds"), live_jt)
        chk("anchor_judge_has_no_orientation_term", False,
            ((prereg.get("anchors") or {}).get("judge_has_orientation_term") or {}).get("value"))
        floor = ((prereg.get("anchors") or {}).get("sidecar_representation_floor") or {})
        chk("anchor_sidecar_floor_m_less_eq_tol", True,
            bool(floor.get("floor_m") is not None and float(floor["floor_m"]) <= REST_XYZ_MATCH_TOL_M))
        chk("anchor_sidecar_has_no_quaternion_key", True,
            ((prereg.get("anchors") or {}).get("sidecar_has_any_quaternion_key") or {}).get("value"))
        anchor_recheck = "measured"
    except Exception as exc:                                          # noqa: BLE001
        checks.append({"check": "anchor_recheck_ran", "expected": True, "got": False,
                       "pass": False, "fatal": True,
                       "error": f"{type(exc).__name__}: {exc}"})
        anchor_recheck = "not_measured"

    lin = prereg_lineage(out_dir_for_lineage)
    chk("lineage_branch_deciding_thresholds_never_moved", True,
        lin.get("branch_deciding_thresholds_never_moved"))

    n_fail = sum(1 for c in checks if not c["pass"])
    return {"measurement_status": "measured" if anchor_recheck == "measured" else "not_measured",
            "n_checks": len(checks), "n_pass": len(checks) - n_fail, "n_fail": n_fail,
            "verified": bool(n_fail == 0), "checks": checks,
            "prereg_lineage": prereg_lineage(out_dir_for_lineage),
            "anchor_recheck_status": anchor_recheck,
            "refusal_policy": ("任一 fatal 不过 ⇒ `refused` + exit 2，**不落半成品判词**；"
                               "脚本字节漂了必须**重新预登记**，不许拿旧预登记给新码背书"),
            "why_this_tooth_exists": ("A2-SD-08（`PRE_REGISTRATION_v2` 的 `producer` 块逐字段继承 v1、"
                                      "身份字段与实际产码版本不符）的同型防线：预登记的价值全在"
                                      "「它是在结果之前、由这个字节版本落的」这两件事上")}


# ══════════════════════════ main ══════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(
        description="A2 / 裁定 104.3 的 CPU-only 测量件：`demo_init_box_quat_not_written` 的量级")
    ap.add_argument("--stage", choices=("prereg", "measure"), required=True)
    ap.add_argument("--out-dir", default=OUT_DIR_DEFAULT)
    ap.add_argument("--prereg-path", default=None,
                    help=f"预登记件路径（默认 <out-dir>/{pathlib.Path(PREREG_REL).name}）")
    ap.add_argument("--pixel-image-size", type=int, default=PIXEL_ANCHOR_IMAGE_SIZE,
                    help="像素锚的渲染分辨率（默认 224 = Step-1 的 `--image-size` 默认值）")
    ap.add_argument("--no-pixel-anchor", action="store_true",
                    help="跳过像素锚（⇒ 该锚 not_measured；阈值正当性只剩 anchor_1/3/4）")
    ap.add_argument("--episodes", default="",
                    help="**只用于冒烟**；正式件必须留空 = 40 集全量（裁定 104.3-④，C9 会拦）")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prereg_rel = args.prereg_path or str(out_dir / pathlib.Path(PREREG_REL).name)
    prereg_path = pathlib.Path(prereg_rel)
    if not prereg_path.is_absolute():
        prereg_path = REPO / prereg_path
    measure_path = out_dir / pathlib.Path(MEASURE_REL).name

    if os.environ.get("MUJOCO_GL") != "osmesa":
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "measurement_status": "refused",
                          "why": (f"`MUJOCO_GL={os.environ.get('MUJOCO_GL')!r}` ≠ 'osmesa' ⇒ 本件是 "
                                  "**CPU-only** 测量，不许上卡（裁定 104.3）；用 "
                                  "`MUJOCO_GL=osmesa OMP_NUM_THREADS=1` 跑")}, ensure_ascii=False))
        return EXIT_USAGE

    script_sha = sha12(REPO / SELF_REL)
    load_before = PRE.PBG.gpu_window_readings(extra={"phase": f"quat_{args.stage}_before"})
    t_start = time.perf_counter()

    # ── 输入：与 Step-1 **同源**（复用先落腿件，不另造读取路径）──────────────
    ctx: dict = {"skip_env": False, "render": False, "image_size": 64}
    try:
        ctx["ds"] = PRE.read_dataset_arrays(REPO / PRE.P_DS)
        init_block = PRE.build_demo_initial_states(ctx)
    except Exception as exc:                                          # noqa: BLE001
        print(json.dumps({"ok": False, "exit_code": EXIT_NOT_MEASURED,
                          "measurement_status": "not_measured",
                          "error": f"{type(exc).__name__}: {exc}",
                          "why": "输入装载失败 ⇒ not_measured（不写 0、不写「无影响」）"},
                         ensure_ascii=False))
        return EXIT_NOT_MEASURED
    rows = list(init_block["rows"])
    if args.episodes.strip():
        want = {int(x) for x in args.episodes.split(",") if x.strip()}
        rows = [r for r in rows if r["episode_index"] in want]

    # ══════════════ 阶段一：预登记 ══════════════
    if args.stage == "prereg":
        if prereg_path.exists():
            bi_dir = out_dir / "before_images"
            bi_dir.mkdir(parents=True, exist_ok=True)
            old_sha = sha12(prereg_path)
            bi = bi_dir / f"{PREREG_NAME}.before_{old_sha}"
            if not bi.exists():
                bi.write_bytes(prereg_path.read_bytes())
            print(f"[before-image] {bi.relative_to(REPO)} {old_sha}", flush=True)
        doc = build_prereg(args, rows, init_block)
        doc["stage_note"] = ("本件落盘时**尚无 40 集的任何结果**（`--stage measure` 才产结果）；"
                             "`threshold_provenance.contamination_disclosure` 里明写了"
                             "哪些东西在定阈值之前已经被看到，不装作盲测")
        if rows and len(rows) != N_EPISODES_REQUIRED:
            doc["warning"] = (f"`--episodes` 只给了 {len(rows)} 集 ⇒ 这是**冒烟**用预登记，"
                              "正式件必须用全量 40 集重新预登记（C9 会拦）")
        info = write_json(prereg_path, doc)
        load_after = PRE.PBG.gpu_window_readings(extra={"phase": "quat_prereg_after"})
        doc_load = {"before": load_before, "after": load_after}
        print(json.dumps({"ok": True, "stage": "prereg", "exit_code": EXIT_OK,
                          "measurement_status": "measured",
                          "prereg": info, "script_sha256_12": script_sha,
                          "anchors_measurement_status": (doc["anchors"].get("pixel_sensitivity") or {})
                          .get("measurement_status"),
                          "thresholds": {"angle_diff_deg_max": ANGLE_DIFF_DEG_MAX_THRESHOLD,
                                         "splice_rest_drift_xyz_m_max": SPLICE_REST_DRIFT_XYZ_M_MAX,
                                         "splice_rest_angle_deg_max": SPLICE_REST_ANGLE_DEG_MAX,
                                         "rest_xyz_match_tol_m": REST_XYZ_MATCH_TOL_M},
                          "loadavg_before": load_before.get("loadavg"),
                          "loadavg_after": load_after.get("loadavg"),
                          "wall_s": round(time.perf_counter() - t_start, 2)}, ensure_ascii=False))
        return EXIT_OK

    # ══════════════ 阶段二：测量 ══════════════
    if not prereg_path.exists():
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "measurement_status": "refused",
                          "why": (f"预登记件不在盘（{prereg_rel}）⇒ 拒绝测量："
                                  "**先预登记再测**是这一件的全部价值所在（裁定 104.3-①）")},
                         ensure_ascii=False))
        return EXIT_USAGE
    try:
        prereg_raw = prereg_path.read_bytes()
        prereg = json.loads(prereg_raw.decode("utf-8"))
    except Exception as exc:                                          # noqa: BLE001
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "measurement_status": "refused",
                          "error": f"{type(exc).__name__}: {exc}",
                          "why": "预登记件读不出来 ⇒ 拒绝测量"}, ensure_ascii=False))
        return EXIT_USAGE
    prereg_txt = prereg_raw.decode("utf-8")
    prereg_id = {"path": prereg_rel,
                 "sha256_12": sha12(prereg_path), "bytes": len(prereg_raw),
                 "n_lines_wc": prereg_txt.count("\n"),
                 "n_lines_splitlines": len(prereg_txt.splitlines()),
                 "n_lines_caliber": N_LINES_CALIBER,
                 "mtime": prereg_path.stat().st_mtime}
    ver = verify_prereg(prereg, script_sha=script_sha, rows_n=len(rows),
                        out_dir_for_lineage=out_dir)
    if not ver["verified"]:
        fails = [c for c in ver["checks"] if not c["pass"]]
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "measurement_status": "refused",
                          "prereg": prereg_id, "n_fail": len(fails), "failed_checks": fails,
                          "why": ("预登记校验不过 ⇒ 拒绝测量、**不落半成品判词**"
                                  "（脚本字节漂了必须重新预登记）")}, ensure_ascii=False))
        return EXIT_USAGE

    if measure_path.exists():
        bi_dir = out_dir / "before_images"
        bi_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        bi = bi_dir / f"{measure_path.name}.before_{ts}"
        bi.write_bytes(measure_path.read_bytes())
        print(f"[before-image] {bi.relative_to(REPO)} {sha12(bi)}", flush=True)

    res = run_measure(args, rows, init_block, prereg, prereg_id)
    aggregate = res["aggregate"]
    nc = res["negative_controls"]
    branch = decide_branch(aggregate, nc, res["per_episode"], res["arm_box_contact_episodes"])
    load_after = PRE.PBG.gpu_window_readings(extra={"phase": "quat_measure_after"})

    status = branch["measurement_status"]
    doc = {
        "artifact": "a2_demo_init_box_quat_settle",
        "as_of": now_iso(),
        "producer": {"script": SELF_REL,
                     **{k: v for k, v in identity(SELF_REL).items()
                        if k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                     "python": sys.version.split()[0], "venv": sys.executable},
        "n_lines_caliber": N_LINES_CALIBER,
        "stage": "measure",
        "measurement_status": status,
        "purpose": ("裁定 104.3：把「沉降前姿态 vs 沉降后姿态」的差**测出来**，"
                    "并按**预登记**的两分支程序决定 Step-1 是否按现码起跑。"
                    "红线 `absence_of_measurement_is_not_measurement_of_absence`："
                    "本件在盘之前，任何「不影响」的写法都不成立"),
        "authority": AUTHORITY,
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "model_weights_loaded": False,
        "success_rate_column": "not_an_exit_criterion",
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "render_backend": os.environ.get("MUJOCO_GL"),
        "prereg": {"identity": prereg_id, "verification": ver,
                   "thresholds_as_preregistered": {
                       "angle_diff_deg_max": ANGLE_DIFF_DEG_MAX_THRESHOLD,
                       "splice_rest_drift_xyz_m_max": SPLICE_REST_DRIFT_XYZ_M_MAX,
                       "splice_rest_angle_deg_max": SPLICE_REST_ANGLE_DEG_MAX,
                       "rest_xyz_match_tol_m": REST_XYZ_MATCH_TOL_M,
                       "settle_steps": SETTLE_STEPS, "n_episodes_required": N_EPISODES_REQUIRED},
                   "moved_after_prereg": False},
        "identities": {
            "this_script": identity(SELF_REL),
            "step1_prealign_verify_readonly_reuse": identity("scripts/a2_step1_prealign_verify.py"),
            "step1_bc_overfit_consumer": identity("scripts/a2_step1_bc_overfit.py"),
            "harness_env_gym_aloha": identity("harness/env_gym_aloha.py"),
            "demo_manifest": identity(PRE.P_MANIFEST),
            "dataset_info": identity(str(pathlib.Path(PRE.P_DS) / "meta" / "info.json")),
            "b2_scripted_expert": identity(PRE.P_EXPERT),
            "anchor_probe_nonformal": identity("tmp/a2_quat_anchor_probe.py"),
        },
        "frozen_surfaces_touched": {
            "count": 0,
            "detail": ("先落腿件 `scripts/a2_step1_prealign_verify.py`（含 `_init_env_to_state`）"
                       "**只读复用、一个字节未改**；判定层 `harness/env_gym_aloha.py`、stats、"
                       "`harness/vla_runtime.py`、`PRE_REGISTRATION_v2.json` 全部未碰；"
                       "本件是**新增**脚本，不改任何判据常量"),
        },
        "machine_load": {
            "before": load_before, "after": load_after,
            "nr_throttled_delta": (None if (load_before.get("nr_throttled") is None
                                            or load_after.get("nr_throttled") is None)
                                   else int(load_after["nr_throttled"])
                                   - int(load_before["nr_throttled"])),
            "pairing_rule": "裁定 46.4/53.6/85.7：数值成对带 loadavg(3 点)+nr_throttled",
            "cgroup_caliber": "cgroup v1 配额 12 核；`nproc=112` 是假象，分母用配额",
            "cotenant_caliber": ("三网读数里若出现外来占用（`min_grasp_pi05` = 用户隔离线），"
                                 "那只是**排程事实**，与本线读数**不得互搬**（裁定 46.4 / 103.6-②）；"
                                 "本件 CPU-only、不上卡、不申报窗口"),
        },
        "aggregate": aggregate,
        "branch_decision": branch,
        "negative_controls": nc,
        "per_episode": res["per_episode"],
        "positive_control_failures": res["positive_control_failures"],
        "arm_box_contact_episodes": res["arm_box_contact_episodes"],
        "confounder_registration": {
            "defect_id": "A2-SD-10_demo_init_box_quat_not_written",
            "d_ruling_id": "demo_init_box_quat_not_written（裁定 104.2，Ⅰ 类）",
            "status_after_this_measurement": branch["defect_key_status"],
            "stays_registered_even_if_branch_is_甲": True,
            "why": ("缺陷是**码的形状**（`_init_env_to_state` 不写 `qpos[19:23]`、回读自证只覆盖 14 维），"
                    "不是这一次的数值；量出 0.0° 只说明**这一批示范初态**上它不material，"
                    "不说明这条路径安全 ⇒ 必须作为**已登记混淆项**随 Step-1 报告出（补单九 ④）"),
            "must_appear_in_step1_report": True,
        },
        "readback_scope_caveat": ("Step-1 的 `readback_ok` / 阻塞牙 `demo_init_readback_failed` 仍只覆盖 "
                                  "**14 维机器人状态**；本件是把作用域补到**方块位姿**的那一件，"
                                  "两者不可互相替代"),
        "does_not_change_r2_verdict": True,
        "exit_code_policy": (prereg.get("exit_code_policy")),
        "wall_s": round(time.perf_counter() - t_start, 2),
    }
    if status == "measured" and branch["branch"] == "乙":
        doc["blocking_for_step1_start"] = True
        doc["blocking_reason"] = ("分支 = 乙 ⇒ 按预登记必须先做那一处窄修 + 预登记 v3 增补，"
                                  "且**替代来源须先经 D 认可**；在此之前不得起跑")
    elif status == "measured":
        doc["blocking_for_step1_start"] = False
        doc["non_blocking_reason"] = ("分支 = 甲 ⇒ Step-1 **按现码起跑、一个字节不改**（裁定 104.3）；"
                                      "缺陷作为已登记混淆项随报告出")
    else:
        doc["blocking_for_step1_start"] = None
        doc["blocking_reason"] = ("not_measured ⇒ 分支未知；按裁定 104.3 的竞态兜底，"
                                  "守望器若已起跑，那一跑仍有效、不作废，但缺陷必须随报告出")

    doc["exit_code"] = (EXIT_OK if (status == "measured" and branch["branch"] == "甲")
                        else EXIT_BLOCKING_RED if status == "measured"
                        else EXIT_NOT_MEASURED)
    info = write_json(measure_path, doc)
    print(json.dumps({
        "ok": doc["exit_code"] == EXIT_OK, "stage": "measure", "exit_code": doc["exit_code"],
        "measurement_status": status, "branch": branch["branch"],
        "defect_key_status": branch["defect_key_status"],
        "artifact": info, "prereg_sha256_12": prereg_id["sha256_12"],
        "angle_diff_deg_max": aggregate["angle_diff_deg_max"],
        "angle_diff_deg_median": aggregate["angle_diff_deg_median"],
        "angle_diff_exact_zero_count": f'{aggregate["n_angle_diff_exact_zero"]}/{aggregate["n_episodes_measured"]}',
        "quat_bitwise_identical_count": aggregate["n_quat_bitwise_identical"],
        "splice_rest_drift_xyz_m_max": aggregate["splice_rest_drift_xyz_m_max"],
        "splice_rest_angle_deg_max": aggregate["splice_rest_angle_deg_max"],
        "settle_steps_dropped_set": aggregate["settle_steps_dropped_set"],
        "negative_controls_all_bite": nc.get("all_bite"),
        "bites_per_control": nc.get("bites_per_control"),
        "criteria_pass": {k: v["pass"] for k, v in branch["criteria"].items()},
        "threshold_insensitivity": branch["threshold_insensitivity_report"],
        "loadavg_before": load_before.get("loadavg"), "loadavg_after": load_after.get("loadavg"),
        "nr_throttled_delta": doc["machine_load"]["nr_throttled_delta"],
        "wall_s": doc["wall_s"],
    }, ensure_ascii=False, indent=1, default=jdefault))
    return int(doc["exit_code"])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as _exc:                                         # noqa: BLE001
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "measurement_status": "refused",
                          "error": f"{type(_exc).__name__}: {_exc}",
                          "why": "结构性失败 ⇒ exit 2，不落半成品判词"}, ensure_ascii=False))
        sys.exit(EXIT_USAGE)
