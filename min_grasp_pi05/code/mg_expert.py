#!/usr/bin/env python
"""最小抓取链路 · 脚本专家（示范源）。

十段状态机，完全不学习，只用几何规则 + 环境真值（物体位姿 / 末端位姿 / 夹爪宽度）。
两个职责：
  1. **示范源**：产出的 (obs, action) 对就是训练数据；mg_collect.py 只收严格成功的 episode。
  2. **链路上界**：专家在同一套包装层里稳定成功 -> 环境执行器 / 动作语义 / 成功判定这三层是通的，
     之后 BC 学不出来就只剩数据格式、归一化、模型三类原因（把故障域收窄）。

动作语义（与 mg_env 的 CONTRACT 一致）：
    action[0:3] = clip((目标末端位置 - 当前末端位置) / STEP_SCALE, -1, 1) * SPEED[phase]
    action[3:6] = 0                     # 不做姿态控制
    action[6]   = +1 闭合 / -1 张开      # mg_probe --gripper 实测语义

为什么每个相位有不同的 SPEED（2026-09-30 实测教训）：
    控制器 output_max=0.05 m 但 ramp_ratio=0.2 + kp=150 阻抗控制，饱和动作的有效位移只有
    ≈11 mm/控制步。全速搬运时 can 会从指间滑出（实测第 141 步滑脱），滑脱后 can 恰好穿过
    篮子上方的 z 窗口 -> robosuite 的 _check_success() 判**假阳性**成功。所以搬运/下放限速，
    并且用「末端-物体距离」做滑脱检测，滑脱就重新抓。

几何常数：夹爪中心比 can 中心高 15 mm 抓得最牢（25 mm 会滑）；can 半高 60.3 mm（实测：
静置桌面时 can 中心 z=0.8603，桌面 z=0.8）。任何改动都要重跑 mg_probe.py --expert 自证。
"""

from __future__ import annotations

import numpy as np

STEP_SCALE = 0.05        # 命令 -> 动作 的换算基数（控制器 output_max）；有效位移见 SPEED 注释
PRE_HEIGHT = 0.12        # can 正上方悬停高度
GRASP_OFFSET_Z = 0.015   # 抓取时夹爪中心高于 can 中心 15 mm
CAN_HALF_HEIGHT = 0.0603 # can 半高（实测）
XY_TOL = 0.008           # 水平对准容差 8 mm
Z_TOL = 0.010            # 垂直对准容差 10 mm
GRASP_STEPS = 25         # 闭爪步数
GRASP_HELD_WIDTH = 0.020 # sum(|gripper_qpos|) 大于它 = 夹到东西（空合 0.001，夹 can ≈0.05）
# GRASP_HELD_WIDTH 只是**下界**：它写于 grasp 相位内部（那时爪子刚刚合完，张开态不会出现），
# 但档 5 的 resume() 要在**任意时刻**判「现在是不是夹着」，此时爪子可能正大张着（0.078）。
# 所以需要上界 HOLD_WIDTH_MAX。出处（180 条示范的搬运段实测，code/mg_expert_resume_selftest.py 钉住）：
#   反向搬运段 n=21815：p1=0.0466 中位=0.0498 p99=0.0609 **max=0.0720**
#   正向搬运段 n=11167：p1=0.0493 中位=0.0497 p99=0.0611 max=0.0681
#   张开模态（抓取前）  ：中位 0.078~0.079，max=0.0801
# ⇒ 取 0.072：搬运段一步不误判，张开模态一步不误判。判错两个方向都能自愈
#   （误判「夹着」⇒ carry 的 _held 距离检查立刻把它打回 approach；误判「没夹」⇒ 重新接近重抓）。
HOLD_WIDTH_MAX = 0.072   # 夹持宽度上界（只被 resume() 用；reset()/__call__() 一行都没碰）
LIFT_TARGET = 0.05       # can 离桌面 5 cm 才算抓起来
SETTLE_STEPS = 10        # 提起后静止消摆
CARRY_HEIGHT = 0.18      # 搬运高度（篮子 z + 18 cm）
PLACE_CAN_Z = 0.068      # can 中心降到 篮子 z + 68 mm（离篮底 ~8 mm）就松手
RELEASE_STEPS = 15       # 张爪步数
RETREAT_STEPS = 20       # 松手后抬爪步数
MAX_GRASP_TRIES = 3      # 抓空重试次数
HOLD_DIST_MAX = 0.055    # 末端与 can 的距离超过它 = 滑脱（正常吊挂约 0.03）
# ── descend 相位的超时退路（档 5.1 第 2 步；修 README 坑 46「相位退出逻辑不对称 = 静默死循环」）──
# 为什么必须加：`descend → grasp` 判据（xy_ok ±8 mm ∧ |z_err| < 10 mm）在**接管**场景下会长期不成立，
# 而 grasp 有 MAX_GRASP_TRIES 的阶梯、descend 一条退路都没有 ⇒ 专家以 0.7 倍速在 can 上方原地打转到
# horizon。档 5 实测 23 次接管里 **11 次**如此（162~305 步、爪子全程 0.0798 = 完全张开、ms/step 还更快，
# 光看门指标看不出在空转）。物理机理见 runs/S5_SUPPLEMENT.md 第三节 + runs/s5_diag_resume/：
# 末端偏 5~8 mm 时指头（单侧指隙 ≈ (0.0805−0.066)/2 ≈ 7 mm）顶住 can 上缘/bin 壁 ⇒
# 命令下降 25~33 mm/步、实测只有 0.03 mm/步（99% 的下降步实测 <20% 命令）。
#
# 三个常数的出处 = code/mg_probe_stall_calib.py 的两侧标定（**不是**拍脑袋）：
#   干净专家跑（reverse/20 局/seed7000/noise0.05/rng12345，与 G1 同配置）
#     runs/s5_1_stall_calib_clean_rev：T=0.1 mm 时最长连续停滞游程 **9** 步 ⇒ W=25 触发 **0/20** 段
#     （T=0.5 mm 就会误触发 1/20 ⇒ 阈值不能放宽；余量 9 vs 25 = 2.8×）
#   接管跑（runs/s5_diag_resume 的 trace，6 段 descend 游程）
#     runs/s5_1_stall_calib_trace：卡死局 seed7014=**79** 步、seed7015=**152** 步 ⇒ W=25 稳稳触发；
#     而 3 段「走到 grasp」的游程最长只有 **14** 步（seed7003，它磨了 96 步但一直在缓慢推进）⇒ 不误伤
# ⇒ 取 T=0.1 mm/步、W=25 步：卡死局最迟在第 25 步就被打断（省 130~190 步），成功局一步不改。
DESCEND_STALL_DZ = 0.0001    # 每步实测下降 < 0.1 mm = 「没有实质下降」
DESCEND_STALL_MAX = 25       # 连续这么多步停滞 ⇒ 退回 approach 重新对准（restage）
DESCEND_MAX_RESTAGES = 2     # restage 上限；仍失败 ⇒ unrecoverable=True + give_up（交还上层）
GIVE_UP_PHASE = "give_up"    # 落进 __call__ 末尾的 else 分支 = 原地保持 + 开爪（显式认输，不再空转）

GRIP_CLOSE = 1.0         # 实测语义（robosuite 1.5.2 SimpleGripController）：+1 = 闭合
GRIP_OPEN = -1.0         # -1 = 张开

CLOSED_PHASES = ("grasp", "lift", "settle", "carry", "place_descend")

# 每个相位的速度系数（1.0 = 饱和 ≈11 mm/步）。搬运与下放限速是为了不让 can 滑出指间。
SPEED = {
    "approach": 1.0,
    "descend": 0.7,
    "grasp": 0.2,
    "lift": 0.7,
    "settle": 0.0,
    "carry": 0.55,
    "place_descend": 0.35,
    "release": 0.0,
    "retreat": 0.6,
    "done": 0.0,
}


class ScriptedExpert:
    """输入环境真值，输出 7 维 OSC_POSE 动作。用法：env.reset() 后 reset()，每步 __call__()。"""

    # 搬运阶段「高度保持」的两种写法。False（默认）= 现行行为：每步把目标 z 设成**当前** eef z；
    # True = 锁到绝对高度 bin_pos[2] + CARRY_HEIGHT + CARRY_Z_LOCK_MARGIN。
    # 为什么需要 True（2026-09-30 档 2 反向任务实测，code/mg_probe_reverse.py --expert 可复现）：
    # 「跟随当前 z」本质是个**积分器** —— 长距离横移时每步的稳态误差会累加。反向搬运
    # （bin2 -> bin1，朝机器人方向收臂）实测 eef z 漂 +0.155 m（0.95 -> 1.105），臂越抬越高、
    # 夹持越来越虚，can 在指间一路转到 75°、松手后侧躺（z=0.845 = can 半径）。
    # 正向同一段代码只漂 -0.005~+0.017 m、can 全程 0°，所以默认 False = 正向行为逐比特不变。
    CARRY_Z_LOCK = False
    # 锁定目标 = bin_pos[2] + CARRY_HEIGHT + MARGIN。实测锁定后 eef z 稳态误差 ≈ 0（目标 1.00 -> 实测 1.000），
    # 所以 MARGIN 取 0：搬运高度就是 0.98 m，与正向实测的 0.96~0.97 m 同量级，
    # 免得正/反两条示范的 eef_z 分布被人为拉开（联合训练时那会变成一个额外变量）。
    CARRY_Z_LOCK_MARGIN = 0.0

    def __init__(self, env) -> None:
        self.env = env
        self.phase = "init"
        self.phase_step = 0
        self.grasp_try = 0
        self.regrasp = 0
        self.slip = 0
        self.log: list[str] = []
        self.can_z0 = 0.0
        self.target_xy = np.zeros(2)
        self.bin_pos = np.zeros(3)
        # 档 5.1：descend 停滞计数与认输标记（纯增量；不参与任何既有判据）
        self.restages = 0
        self.unrecoverable = False
        self._prev_eef_z: float | None = None
        self._descend_stall = 0

    def reset(self) -> "ScriptedExpert":
        """必须在 env.reset() 之后调用（要读初帧真值）。"""
        self.phase = "approach"
        self.phase_step = 0
        self.grasp_try = 0
        self.regrasp = 0
        self.slip = 0
        self.log = ["approach"]
        self.can_z0 = float(self.env.object_pos[2])     # 桌面参考线
        self.target_xy = self.env.target_xy.copy()      # robosuite 真值表给的目标象限中心
        self.bin_pos = self.env.bin_pos.copy()
        self.restages = 0
        self.unrecoverable = False
        self._prev_eef_z = None
        self._descend_stall = 0
        return self

    def resume(self, can_z0: float | None = None) -> "ScriptedExpert":
        """档 5 Harness 接管入口：从**当前**环境状态推断相位，然后接着跑。

        为什么「续跑」是可能的（2026-10-02 读代码确认）：本状态机是**全反应式**的 ——
        `__call__` 每步都用 env 真值（eef_pos / object_pos / gripper_width / target_xy / bin_pos）
        现算目标点，相位只是「现在该干什么」的标签，**没有任何隐藏的积分状态**。
        所以只要把 (phase, phase_step) 和三个参考量 (can_z0, target_xy, bin_pos) 摆对，
        之后的动作流与从 reset() 一路跑下来完全一致。

        ⚠️ 纯增量约束（档 5 的 G1 护栏就是查这条）：本方法只**写** self 的相位与参考量，
        不改 reset() / __call__() / 任何类常数。改完必须重跑 mg_ceiling.py（噪声流钉死
        default_rng(12345)）逐局复现 runs/s2f_ceiling_rev_test20_n05，否则档 5 全部作废。

        can_z0 = **本局开始时** can 的静止 z（反向实测 0.8603），必须由调用方在 env.reset()
        之后记下来传进来。缺省时退回 env.resting_z（几何静止高度，反向 = bin 底 + can 半高）。
        两者都拿不到就**报错**，绝不用当前的 env.object_pos[2] 兜底：lift 相位的判据是
        `can[2] > can_z0 + LIFT_TARGET`，接管时 can 可能正被夹在半空（z≈1.0），拿它当参考线
        ⇒ 判据永远成立不了 ⇒ 专家会卡在 lift 相位一直往上顶（静默失败，比崩掉更难查）。
        """
        if can_z0 is None:
            can_z0 = getattr(self.env, "resting_z", None)
            if can_z0 is None:
                raise ValueError(
                    "resume() 需要本局起始的 can 静止 z：请在 env.reset() 后记录 object_pos[2] 并显式传入"
                    "（用接管瞬间的 object_pos[2] 会让 lift 判据失效）")
        self.can_z0 = float(can_z0)
        self.target_xy = self.env.target_xy.copy()
        self.bin_pos = self.env.bin_pos.copy()

        eef = self.env.eef_pos
        can = self.env.object_pos
        # 「还夹着」= 夹爪宽度落在夹持区间 (GRASP_HELD_WIDTH, HOLD_WIDTH_MAX) ∧ 末端-can 距离在吊挂范围内。
        # 两个条件都要：只看宽度会把「夹着空气但恰好停在 0.05」误判成夹持，只看距离会把
        # 「can 掉在末端正下方 5 cm」误判成夹持。
        # 上界不可省：张开的爪子是 0.078，它也 > GRASP_HELD_WIDTH，只看下界会把「张着爪子悬在 can 上方」
        # 误判成夹持 ⇒ 专家跑去 carry 高度却发现手里没东西（HOLD_WIDTH_MAX 的注释里有实测出处）。
        width = float(self.env.gripper_width)
        holding = GRASP_HELD_WIDTH < width < HOLD_WIDTH_MAX and self._held(eef, can)
        if holding:
            # 已经离地 => 直接搬运；还没离地 => 先提起（lift 的判据用的就是上面那个 can_z0）
            phase = "carry" if can[2] > self.can_z0 + LIFT_TARGET else "lift"
        elif abs(eef[0] - can[0]) < XY_TOL and abs(eef[1] - can[1]) < XY_TOL:
            # 末端已在 can 正上方：高度也对上了就直接闭爪，否则先下降
            phase = "grasp" if abs(eef[2] - can[2] - GRASP_OFFSET_Z) < Z_TOL else "descend"
        else:
            phase = "approach"
        self.phase = phase
        self.phase_step = 0
        self.grasp_try = 0
        self.log.append(f"resume:{phase}")
        self.restages = 0
        self.unrecoverable = False
        self._prev_eef_z = None      # 接管后的第一步没有「上一步 eef z」⇒ 不算停滞（保守）
        self._descend_stall = 0
        return self

    def _set(self, phase: str) -> None:
        self.phase = phase
        self.phase_step = 0
        self.log.append(phase)
        self._descend_stall = 0      # 换相位就清停滞计数（游程必须是**连续**的）

    def _held(self, eef: np.ndarray, can: np.ndarray) -> bool:
        """滑脱检测：末端与 can 的水平/垂直距离都在吊挂范围内才算还夹着。"""
        return float(np.linalg.norm(eef - can)) < HOLD_DIST_MAX

    def __call__(self) -> np.ndarray:
        self.phase_step += 1
        eef = self.env.eef_pos
        can = self.env.object_pos
        # 实测 z 位移（上一步动作的结果）。只用于 descend 的停滞判据，不进任何既有判据。
        dz = None if self._prev_eef_z is None else float(eef[2]) - self._prev_eef_z
        self._prev_eef_z = float(eef[2])
        xy_ok = abs(eef[0] - can[0]) < XY_TOL and abs(eef[1] - can[1]) < XY_TOL

        if self.phase == "approach":
            target = can + np.array([0.0, 0.0, PRE_HEIGHT])
            if xy_ok and eef[2] > can[2] + PRE_HEIGHT - 0.02:
                self._set("descend")

        elif self.phase == "descend":
            target = can + np.array([0.0, 0.0, GRASP_OFFSET_Z])
            z_err = eef[2] - can[2] - GRASP_OFFSET_Z      # 与上一行同一个表达式，逐比特不变
            if xy_ok and abs(z_err) < Z_TOL:
                self._set("grasp")
            else:
                # 停滞 = 还在抓取带上方（z_err > Z_TOL）∧ 这一步几乎没下降。连续 W 步 ⇒ 退一级重来。
                stalled = z_err > Z_TOL and dz is not None and abs(dz) < DESCEND_STALL_DZ
                self._descend_stall = self._descend_stall + 1 if stalled else 0
                if self._descend_stall >= DESCEND_STALL_MAX:
                    if self.restages < DESCEND_MAX_RESTAGES:
                        # 退回 approach：升到 PRE_HEIGHT（指头高于 can 上缘）重新对准 xy，再下一次。
                        # 这一步的动作按 approach 的目标算（_set 已把相位换成 approach）。
                        self.restages += 1
                        self.log.append(f"descend_restage{self.restages}")
                        self._set("approach")
                        target = can + np.array([0.0, 0.0, PRE_HEIGHT])
                    else:
                        # 认输：显式打标 + 落到 else 分支（原地保持 + 开爪），让上层（harness）能把
                        # 剩余步数交还给策略，而不是把整局烧在一个死循环里（坑 46 的房规①）。
                        self.unrecoverable = True
                        self.log.append("descend_unrecoverable")
                        self._set(GIVE_UP_PHASE)
                        target = eef.copy()

        elif self.phase == "grasp":
            target = can + np.array([0.0, 0.0, GRASP_OFFSET_Z - 0.004 * self.grasp_try])
            if self.phase_step >= GRASP_STEPS:
                if self.env.gripper_width > GRASP_HELD_WIDTH:   # 没合到底 = 夹到东西了
                    self.grasp_try = 0
                    self._set("lift")
                elif self.grasp_try < MAX_GRASP_TRIES:          # 抓空：再降 4 mm 重夹
                    self.grasp_try += 1
                    self.phase_step = 0
                    self.log.append(f"grasp_retry{self.grasp_try}")
                else:                                           # 彻底抓空：重新接近
                    self.grasp_try = 0
                    self._set("approach")

        elif self.phase == "lift":
            target = eef + np.array([0.0, 0.0, 0.3])
            if can[2] > self.can_z0 + LIFT_TARGET:
                self._set("settle")

        elif self.phase == "settle":
            target = eef.copy()                                 # 停 SETTLE_STEPS 步消摆
            if not self._held(eef, can):
                self.slip += 1
                self.log.append(f"slip_settle{self.slip}")
                self._set("approach")
            elif self.phase_step >= SETTLE_STEPS:
                self._set("carry")

        elif self.phase == "carry":
            if not self._held(eef, can):                        # 搬运途中滑脱 -> 回去重抓
                self.slip += 1
                self.regrasp += 1
                self.log.append(f"slip_carry{self.slip}")
                self._set("approach")
                target = eef.copy()
            elif eef[2] < self.bin_pos[2] + CARRY_HEIGHT - 0.02:
                target = eef + np.array([0.0, 0.0, 0.3])        # 先垂直升到搬运高度
            else:
                # 用 can 的实际 xy 闭环（can 吊在夹爪下会偏），把 can 搬到目标象限正上方
                z_hold = (self.bin_pos[2] + CARRY_HEIGHT + self.CARRY_Z_LOCK_MARGIN
                          if self.CARRY_Z_LOCK else eef[2])
                target = np.array([eef[0] + (self.target_xy[0] - can[0]),
                                   eef[1] + (self.target_xy[1] - can[1]), z_hold])
            if (self.phase == "carry" and abs(can[0] - self.target_xy[0]) < XY_TOL
                    and abs(can[1] - self.target_xy[1]) < XY_TOL
                    and eef[2] >= self.bin_pos[2] + CARRY_HEIGHT - 0.02):
                self._set("place_descend")

        elif self.phase == "place_descend":
            if not self._held(eef, can):
                self.slip += 1
                self.log.append(f"slip_place{self.slip}")
                self._set("approach")
                target = eef.copy()
            elif abs(can[0] - self.target_xy[0]) > XY_TOL or abs(can[1] - self.target_xy[1]) > XY_TOL:
                target = np.array([eef[0] + (self.target_xy[0] - can[0]),
                                   eef[1] + (self.target_xy[1] - can[1]), eef[2]])
            else:
                # 下降的目标用「can 中心到 PLACE_CAN_Z」换算：夹爪中心比 can 中心高 GRASP_OFFSET_Z
                target = np.array([eef[0], eef[1],
                                   self.bin_pos[2] + PLACE_CAN_Z + GRASP_OFFSET_Z])
            if can[2] < self.bin_pos[2] + PLACE_CAN_Z + 0.015:
                self._set("release")

        elif self.phase == "release":
            target = eef.copy()
            if self.phase_step >= RELEASE_STEPS:
                self._set("retreat")

        elif self.phase == "retreat":
            target = eef + np.array([0.0, 0.0, 0.10])
            if self.phase_step >= RETREAT_STEPS:
                self._set("done")

        else:  # done：本局不再动
            target = eef.copy()

        delta = target - eef
        speed = SPEED.get(self.phase, 1.0)
        action = np.zeros(7, dtype=np.float32)
        action[:3] = np.clip(delta / STEP_SCALE, -1.0, 1.0) * speed
        action[6] = GRIP_CLOSE if self.phase in CLOSED_PHASES else GRIP_OPEN
        return action

    @property
    def phase_seq(self) -> list[str]:
        """去重后的相位序列（写进 summary，用来判断专家是否走了正常路径）。"""
        return list(dict.fromkeys(self.log))
