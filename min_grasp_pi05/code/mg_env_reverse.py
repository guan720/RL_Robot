#!/usr/bin/env python
"""最小抓取链路 · 档 2「反向任务」环境（can: bin2 目标象限 → bin1 源托盘）。

为什么是**子类 + 新文件**，而不是改 mg_env.py：
    档 1 的 sweep / gate 评测进程每 500 步新起一个，每次都重新 import mg_env。
    档 1 关门前动 mg_env.py = 让同一条验证曲线的前后段跑在不同代码上 = 自污染。
    所以反向任务全部落在本文件，mg_env.py 一行不改；档 1 关门后再决定是否合并 task_mode。

反向任务定义（与正向严格对称，同一套 action/state/相机/夹爪契约）：
    初态   can 放在 bin2 的 can 象限内（正向的目标点），xy 在象限内抖动、yaw 随机；
           机械臂初姿仍由 seed 决定（沿用 mg_env._seed_randomness）。
    目标   把 can 放回 bin1 托盘中心附近（正向的出生区）。
    成功   can 静止在 bin1 中心 ±REVERSE_TARGET_TOL_XY 的方框内 ∧ 物理落定 ∧ 连续保持 10 步。
           口径与正向逐条对齐（同样的 25 mm 高度容差 / 0.05 m/s 速度 / 夹爪张开 / 末端离 can >5 cm），
           只把「落在哪个象限」换成「落在源托盘的等大区域内」。

三个实测事实（2026-09-30 探针，见 code/mg_probe_reverse.py）：
  1. 正向的 can 出生区就是 bin1 托盘内部（placement sampler 以 bin1_pos 为参考、范围覆盖整个托盘），
     所以「从带 10 cm 矮墙的托盘里抓 can」正向专家本来就天天在做 —— 反向不存在新的几何难题。
  2. bin2 象限内部净空 x∈(0.11,0.29) y∈(0.29,0.52)，墙顶 z=0.90；can 半径 25 mm、
     静置中心 z=0.8603。夹爪中心抓到 0.875，掌部仍高于墙顶，横向余量 ≥5 cm → 可下探。
  3. **robosuite 在 can 的目标象限里常驻一个 VisualCan「幽灵」**（contype=0 不参与碰撞，
     永远摆在象限中心）。正向它是有用的目标视觉提示；反向 can 就出生在那里，若不隐藏，
     画面里 bin 内会**永远**有一个 can（抓走之后还在），视觉证据被彻底污染。
     所以反向模式把 VisualCan 的 geom alpha 置 0（只改渲染，不改任何物理）。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_env import (  # noqa: E402
    CAN_HALF_HEIGHT, RELEASE_DIST, SETTLE_SPEED, SETTLE_Z_TOL, SUCCESS_HOLD_STEPS,
    SingleArmGraspEnv,
)

TASK_REVERSE = "Take the can out of the bin and put it back into the tray."

CAN_JOINT = "Can_joint0"          # 实测：sim.model 里 can 的自由关节名
GHOST_GEOM_PREFIX = "VisualCan"   # 目标象限里的常驻幽灵 can（只渲染、不碰撞）

# can 出生抖动范围 —— **实测可行域**，不是按象限净空推的（mg_probe_reverse.py --feasible 可复现）：
# 象限净空 x∈(0.11,0.29) y∈(0.29,0.52) 看着很大，但 Panda 在 x 偏大 / y 偏大那一角已到
# **运动学可达极限**：末端压不到 can 正上方，反而一路蹭 bin2 底板（实测 geom_id=21 = bin2 底板
# 接触 1586 次、手指接触 can 0 次），400 步空转到超时。7×5 网格 × 2 seed 扫出的可行域是
# dx∈[-0.08,+0.02]、dy∈[-0.05,+0.05]；这里取它的内接保守框 —— 宁可初态多样性小一点，
# 也不要把「专家自己都做不到」的初态混进训练分布（采集端只留成功局，但白跑很贵）。
INIT_JITTER_X_LO = -0.06
INIT_JITTER_X_HI = 0.01
INIT_JITTER_Y = 0.04
# 落点必须**立着**：can 半径 25 mm、立置中心高 0.8603；侧躺时中心高 = 0.82+0.025 = 0.845，
# 与立置只差 15 mm —— 恰好落在正向沿用的 ±25 mm 高度容差里。不加这一条，「侧躺在托盘里」
# 会被判成功（2026-09-30 反向首测就吃到 2/5 这种假阳性）。倾角用仿真真值四元数算，不看模型输出。
UPRIGHT_TILT_DEG = 20.0
# 成功区域半宽：0.18 m 见方，与正向象限净空（0.18 × 0.23 m）同量级，避免反向「判定更松所以更容易」
REVERSE_TARGET_TOL_XY = 0.09

# 夹爪「张开」阈值。出处：2026-09-30 首版 step() 里写死的字面量 0.05（与正向 mg_env.py 同值），
# 2026-10-02 抽成常量只是为了让判据变成可单测的纯函数，**数值一个都没改**。
GRIPPER_OPEN_MIN = 0.05


def reverse_settled(can_z: float, resting_z: float, tilt_deg: float, obj_speed: float,
                    gripper_width: float, eef_dist: float, upright_required: bool = True) -> bool:
    """反向「物理落定」判据的纯函数版（无 self、无 RNG、可单测）。

    为什么抽出来：2026-10-02 用户放宽口径（**送到目标区为首要条件**；因手臂高度/冲击导致
    can 侧躺也算送到，但要**追加标记**）。原实现把 5 个条件写在 step() 里，改它 = 改档 2/2c/2e
    正在跑的判据。抽成纯函数后：
      * upright_required=True  -> **严格口径**，与 2026-09-30 首版逐条件同值（见 mg_criterion_selftest.py）；
      * upright_required=False -> **放宽口径 R**，只去掉「倾角 < 20°」这一条，其余四条一字不动。
    因为放宽口径是严格口径「少一个合取项」，所以数学上恒有 严格 ⊆ 放宽（selftest 随机枚举钉住）。
    条件顺序不影响布尔结果（全是 and），也不消耗任何随机数 ⇒ 同一次 rollout 两种口径共用一条轨迹。
    """
    if not (abs(float(can_z) - float(resting_z)) < SETTLE_Z_TOL):
        return False
    if not (float(obj_speed) < SETTLE_SPEED):
        return False
    if not (float(gripper_width) > GRIPPER_OPEN_MIN):
        return False
    if not (float(eef_dist) > RELEASE_DIST):
        return False
    if upright_required and not (float(tilt_deg) < UPRIGHT_TILT_DEG):
        return False
    return True


class ReverseGraspEnv(SingleArmGraspEnv):
    """正向包装层的反向子类：只重写「初态摆放 + 成功判定 + 目标点」，其余契约完全继承。"""

    def __init__(self, *args, task: str = TASK_REVERSE, hide_ghost: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task = task
        self.hide_ghost = bool(hide_ghost)
        self._rev_hold = 0
        self._rev_ever = False
        # 放宽口径 R 的独立计数器：与严格口径**并行**跑在同一条轨迹上，互不影响。
        self._rev_hold_rlx = 0
        self._rev_ever_rlx = False
        # 更松的诊断级「到过目标框」粘滞标记（只当阶梯最底一级，不是成功）。
        self._rev_ever_in_target = False
        self._init_xy = np.zeros(2)
        self._last_obs = None

    # ── 目标 / 参考几何（专家只读这些，因此 ScriptedExpert 不用改一行）──────────
    @property
    def dest_pos(self) -> np.ndarray:
        """反向的落点参考：bin1 托盘（正向的出生区）。"""
        return np.asarray(self.env.bin1_pos, dtype=np.float64)

    @property
    def source_xy(self) -> np.ndarray:
        """反向的取物点：bin2 里 can 的目标象限中心（= 正向的落点）。"""
        return np.asarray(super().target_xy, dtype=np.float64)

    @property
    def target_xy(self) -> np.ndarray:
        return self.dest_pos[:2].copy()

    @property
    def bin_pos(self) -> np.ndarray:
        """专家用它的 z 做搬运高度 / 下放高度参考；两个托盘底面同为 z=0.8，语义上这里是「落点托盘」。"""
        return self.dest_pos

    @property
    def resting_z(self) -> float:
        return float(self.dest_pos[2]) + CAN_HALF_HEIGHT

    # ── 初态：把 can 摆进 bin2 象限（反向任务的「固定/随机初态」）──────────────
    def _write_can_pose(self, pos: np.ndarray, yaw: float) -> None:
        sim = self.env.sim
        q0, q1 = sim.model.get_joint_qpos_addr(CAN_JOINT)
        v0, v1 = sim.model.get_joint_qvel_addr(CAN_JOINT)
        sim.data.qpos[q0:q1] = np.array(
            [pos[0], pos[1], pos[2], np.cos(yaw / 2.0), 0.0, 0.0, np.sin(yaw / 2.0)], dtype=np.float64)
        sim.data.qvel[v0:v1] = 0.0
        sim.forward()

    def _apply_ghost_visibility(self) -> None:
        sim = self.env.sim
        n = 0
        for g in range(sim.model.ngeom):
            name = sim.model.geom_id2name(g) or ""
            if name.startswith(GHOST_GEOM_PREFIX):
                rgba = np.asarray(sim.model.geom_rgba[g], dtype=np.float64)
                rgba[3] = 0.0 if self.hide_ghost else 1.0
                sim.model.geom_rgba[g] = rgba
                n += 1
        return n

    def reset(self, seed: int | None = None, init_xy_offset=None, init_yaw: float | None = None) -> dict:
        """init_xy_offset / init_yaw 只为「可行初态区域扫描」留的显式钩子；默认走 seed 随机。"""
        obs = super().reset(seed=seed)               # 钉住全部随机源 + robosuite reset + 打包
        rng = self.env.rng                           # 已被 _seed_randomness 设成本局 seed
        if init_xy_offset is None:
            jitter = np.array([rng.uniform(INIT_JITTER_X_LO, INIT_JITTER_X_HI),
                               rng.uniform(-INIT_JITTER_Y, INIT_JITTER_Y)], dtype=np.float64)
        else:
            jitter = np.asarray(init_xy_offset, dtype=np.float64).reshape(2)
        yaw = float(rng.uniform(0.0, 2.0 * np.pi)) if init_yaw is None else float(init_yaw)
        src = self.source_xy
        init_pos = np.array([src[0] + jitter[0], src[1] + jitter[1],
                             float(self.env.bin2_pos[2]) + CAN_HALF_HEIGHT], dtype=np.float64)
        self._init_xy = init_pos[:2].copy()
        self._write_can_pose(init_pos, yaw)
        self._apply_ghost_visibility()      # 按 hide_ghost 设 alpha（0 或 1），双向可切换、可自证
        # 位移之后必须重新取一次观测。**必须 force_update=True**：robosuite 的 observable 有
        # 采样缓存，同一 sim 时刻二次调用会原样返回 reset 时的旧值（can 还在 bin1），
        # 于是第一步 step 才刷新 -> 位置突跳 0.67 m -> 假「13 m/s 爆炸」。踩到过，别再踩。
        self._last_obs = self._pack(self.env._get_observations(force_update=True))
        self._prev_obj_pos = self.object_pos.copy()
        self._rev_hold = 0
        self._rev_ever = False
        self._rev_hold_rlx = 0
        self._rev_ever_rlx = False
        self._rev_ever_in_target = False
        self._rev_init_yaw = yaw
        return self._last_obs

    # ── 真值倾角（can 的 z 轴 vs 世界 z）────────────────────────────────────
    def can_tilt_deg(self) -> float:
        """0° = 立着，90° = 侧躺。Can_quat 实测是 **xyzw**（与 scipy 对照 body_xmat 逐元素核过）。"""
        q = np.asarray(self._raw["Can_quat"], dtype=np.float64).reshape(4)
        r22 = 1.0 - 2.0 * (q[0] ** 2 + q[1] ** 2)      # 旋转矩阵 [2][2] = can z 轴在世界 z 上的投影
        return float(np.degrees(np.arccos(np.clip(abs(r22), -1.0, 1.0))))

    # ── 成功判定：与正向逐条同口径，只换落点区域 + 补一条「必须立着」──────────────
    def step(self, action):
        packed, reward, fwd_success, truncated, info = super().step(action)
        can = np.asarray(info["object_pos"], dtype=np.float64)
        eef = np.asarray(info["eef_pos"], dtype=np.float64)
        tgt = self.target_xy
        in_target = bool(abs(can[0] - tgt[0]) <= REVERSE_TARGET_TOL_XY
                         and abs(can[1] - tgt[1]) <= REVERSE_TARGET_TOL_XY)
        tilt = self.can_tilt_deg()
        eef_dist = float(np.linalg.norm(eef - can))
        # 严格口径（= 历史口径，档 2/2c/2e 的 pc_success 一直是它）
        settled = reverse_settled(can[2], self.resting_z, tilt, float(info["object_speed"]),
                                  float(info["gripper_width"]), eef_dist, upright_required=True)
        # 放宽口径 R（用户 2026-10-02 授权）：只去掉「必须立着」，其余四条一字不动
        settled_rlx = reverse_settled(can[2], self.resting_z, tilt, float(info["object_speed"]),
                                     float(info["gripper_width"]), eef_dist, upright_required=False)
        self._rev_hold = self._rev_hold + 1 if (in_target and settled) else 0
        success = self._rev_ever or self._rev_hold >= SUCCESS_HOLD_STEPS
        self._rev_ever = success
        self._rev_hold_rlx = self._rev_hold_rlx + 1 if (in_target and settled_rlx) else 0
        success_rlx = self._rev_ever_rlx or self._rev_hold_rlx >= SUCCESS_HOLD_STEPS
        self._rev_ever_rlx = success_rlx
        self._rev_ever_in_target = self._rev_ever_in_target or in_target

        out = dict(info)
        out["success"] = bool(success)
        out["success_forward_pred"] = bool(fwd_success)   # 正向判据在反向局里的读数（只作对照，不参与结论）
        out["settled"] = settled
        out["hold"] = int(self._rev_hold)
        out["in_reverse_target"] = in_target
        out["can_tilt_deg"] = tilt
        # ── 放宽口径的读数（新增字段，老消费者按 key 取值，一个都不受影响）──────────
        out["settled_relaxed"] = bool(settled_rlx)
        out["hold_relaxed"] = int(self._rev_hold_rlx)
        out["success_relaxed"] = bool(success_rlx)
        out["ever_in_reverse_target"] = bool(self._rev_ever_in_target)
        # 标记：送到了但没立着（侧躺/侧挡）。用户要求「可以视为送到，但要追加标记」。
        out["delivered_tipped"] = bool(success_rlx and not success)
        out["target_xy"] = tgt.tolist()
        out["dist_to_target_xy"] = float(np.linalg.norm(can[:2] - tgt))
        out["reverse_resting_z"] = float(self.resting_z)
        return packed, reward, bool(success), truncated, out

    @property
    def success(self) -> bool:
        return self._rev_ever

    @property
    def success_relaxed(self) -> bool:
        """放宽口径 R：送到 bin1 ±9 cm 框内 ∧ 物理落定（不要求立着）∧ 保持 10 步。"""
        return self._rev_ever_rlx

    @property
    def success_raw(self) -> bool:
        """反向没有 robosuite 原生谓词（原生只认「can 在 bin2 象限」= 反向的**初态**）。
        严格成功 = 仿真真值（can 位姿/速度、夹爪开口、末端距离）+ 落定保持，与正向同一套物理量。"""
        return self._rev_ever

    def init_state_snapshot(self) -> dict:
        snap = super().init_state_snapshot()
        can_quat = np.asarray(self._raw.get("Can_quat", [np.nan] * 4), dtype=np.float64)
        snap.update({
            "task_mode": "reverse",
            "task": self.task,
            "ghost_can_hidden": self.hide_ghost,
            "can_init_xy_requested": np.round(self._init_xy, 6).tolist(),
            "can_init_yaw_requested": round(float(getattr(self, "_rev_init_yaw", np.nan)), 6),
            "can_quat_wxyz": np.round(can_quat, 6).tolist(),
            "source_quadrant_xy": np.round(self.source_xy, 6).tolist(),
            "bin_pos": np.round(self.dest_pos, 6).tolist(),
            "target_xy": np.round(self.target_xy, 6).tolist(),
            "reverse_target_tol_xy": REVERSE_TARGET_TOL_XY,
        })
        return snap

    def contract(self) -> dict:
        c = super().contract()
        c.update({
            "task_mode": "reverse",
            "task": self.task,
            "forward_task": super().contract()["task"],
            "success_criterion": (
                "can **立着**静止在 bin1 托盘中心 ±"
                f"{REVERSE_TARGET_TOL_XY} m 方框内（仿真真值）∧ 物理落定"
                f"(|can_z - {round(self.resting_z, 4)}| < {SETTLE_Z_TOL} m, 倾角 < {UPRIGHT_TILT_DEG}°, "
                f"速度 < {SETTLE_SPEED} m/s, 夹爪张开, 末端离 can > {RELEASE_DIST} m) "
                f"∧ 连续保持 {SUCCESS_HOLD_STEPS} 步"),
            "success_criterion_raw": "反向无 robosuite 原生谓词；原生 _check_success() 认的是「can 在 bin2 象限」，恰为反向初态",
            "success_criterion_relaxed": (
                "【放宽口径 R，用户 2026-10-02 授权】can 静止在 bin1 托盘中心 ±"
                f"{REVERSE_TARGET_TOL_XY} m 方框内 ∧ 物理落定"
                f"(|can_z - {round(self.resting_z, 4)}| < {SETTLE_Z_TOL} m, "
                f"速度 < {SETTLE_SPEED} m/s, 夹爪 > {GRIPPER_OPEN_MIN} m, 末端离 can > {RELEASE_DIST} m) "
                f"∧ 连续保持 {SUCCESS_HOLD_STEPS} 步；**不要求立着**（去掉倾角 < {UPRIGHT_TILT_DEG}° 这一条）。"
                "语义：送到目标区为首要条件，手臂高度/冲击造成的侧躺也算送到，另用 delivered_tipped 打标。"
                "数学关系：严格 ⊆ 放宽（少一个合取项），故 pc_success_relaxed ≥ pc_success 恒成立。"),
            "criterion_ladder": {
                "strict": "落定 ∧ 立着（历史口径 = pc_success，档 2/2c/2e 的预注册门用它）",
                "relaxed_R": "落定，不要求立着（= pc_success_relaxed）",
                "entered_box": "can 曾进入 ±%.2f m 框（= ever_in_reverse_target，最松，仅诊断，不算成功)"
                               % REVERSE_TARGET_TOL_XY},
            "criterion_relaxed_provenance": (
                "放宽依据：runs/_diag/tax_s2c_rev.md 的 80 局分类账 —— 档 2c 严格 37/80=46.2%（未过 50% 门），"
                "其中 10 局是「送到了但侧躺」(C 类)，按放宽口径 47/80=58.8% ≥ 门。"
                "两口径并报、历史严格数值不追改。"),
            "reverse_init": {
                "can_joint": CAN_JOINT,
                "source_quadrant_xy": np.round(self.source_xy, 6).tolist(),
                "jitter_xy": [[INIT_JITTER_X_LO, INIT_JITTER_X_HI], [-INIT_JITTER_Y, INIT_JITTER_Y]],
                "jitter_feasible_region_measured": {
                    "dx": [-0.08, 0.02], "dy": [-0.05, 0.05],
                    "method": "7x5 网格 x 2 seed，以脚本专家严格成功（立着落定）为准",
                    "failure_mode": "x/y 偏大处 Panda 达可达极限，末端蹭 bin2 底板(geom 21)而非抓到 can"},
                "upright_tilt_deg": UPRIGHT_TILT_DEG,
                "yaw": "uniform [0, 2pi)",
                "resting_z_in_bin": round(float(self.env.bin2_pos[2]) + CAN_HALF_HEIGHT, 6),
                "ghost_geom_prefix": GHOST_GEOM_PREFIX,
                "ghost_hidden": self.hide_ghost,
            },
            "dest_tray_pos": np.round(self.dest_pos, 6).tolist(),
        })
        return c
