#!/usr/bin/env python
"""档 5 · ScriptedExpert.resume() 的纯 CPU 自测（假 env 桩，不碰 GPU、不碰 runs/）。

为什么需要它（STAGE_PLAN 档 5 第六节第 1 步）：resume() 是档 5 唯一改到既有文件的地方，
它只做一件事 —— 从当前状态**推断相位**。推错了不会崩，只会让专家从错误的相位开始跑
（例如明明夹着 can 却判成 approach ⇒ 专家张开爪子飞回 can 上方，can 当场掉下去），
这种失败在评测里表现为「接管了但没救回来」，与「检测器漏报」长得一模一样，事后分不清。
所以先把四种相位的推断边界用桩钉死，再上 GPU。

真物理层面的验证另有一条：code/mg_resume_probe.py（在真 env 里跑到第 t 步换一个新专家续跑，
看还能不能把任务做完）。两者一起构成 resume() 的验收。

用法：  bash -c 'source code/env.sh && $MG_PY code/mg_expert_resume_selftest.py'
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_expert import (  # noqa: E402
    CLOSED_PHASES, DESCEND_MAX_RESTAGES, DESCEND_STALL_DZ, DESCEND_STALL_MAX, GRASP_HELD_WIDTH,
    GRASP_OFFSET_Z, GIVE_UP_PHASE, GRIP_OPEN, HOLD_DIST_MAX, HOLD_WIDTH_MAX, LIFT_TARGET,
    PRE_HEIGHT, STEP_SCALE, XY_TOL, Z_TOL, ScriptedExpert,
)
from mg_expert_reverse import ReverseScriptedExpert  # noqa: E402

CAN_Z0 = 0.8603            # 反向实测：can 静置在 bin2 时的中心 z
TARGET_XY = np.array([0.1, -0.25])
BIN_POS = np.array([0.1, -0.25, 0.8])


class FakeEnv:
    """只提供专家读得到的那几样真值；resting_z 可选（用来测缺省兜底那条分支）。"""

    horizon = 400

    def __init__(self, eef, can, width, with_resting_z: bool = False) -> None:
        self.eef_pos = np.asarray(eef, dtype=np.float64)
        self.object_pos = np.asarray(can, dtype=np.float64)
        self.gripper_width = float(width)
        self.target_xy = TARGET_XY.copy()
        self.bin_pos = BIN_POS.copy()
        self.step_calls = 0
        if with_resting_z:
            self.resting_z = CAN_Z0

    def step(self, action):
        self.step_calls += 1
        return {}, 0.0, False, False, {}


class BlockedDescendEnv(FakeEnv):
    """「descend 被接触挡住」的桩件（档 5.1 停滞阶梯的自测用；不碰真物理、不碰 GPU）。

    复现的真实机理（出处 runs/s5_diag_resume/diag_resume.md 的 seed 7015）：末端偏 ~7 mm 时指头顶住
    can 上缘，命令下降 25~33 mm/步、实测只有 0.03 mm/步，can 一动不动、z_err 停在 +25~30 mm。
    两条规则就够：
      * 命令下降（action[2] ≤ 0）⇒ z 减少 min(|action[2]|·STEP_SCALE, max_step)，但**不得低于 block_z**；
      * 命令上升（action[2] > 0）⇒ 一步回到 can 正上方 PRE_HEIGHT（approach 的收敛假设，只为让
        restage 循环在几十步内走完，不追求真实上升速度）。
    xy 始终停在 can + xy_err（7015 实测 |xy| ≈ 7 mm < XY_TOL ⇒ xy_ok 一直成立，卡的是 z）。
    """

    def __init__(self, can, block_z, xy_err=(0.007, 0.001), width=0.0805,
                 start_z=None, max_step=0.011) -> None:
        self.can = np.asarray(can, dtype=np.float64)
        self.block_z = float(block_z)
        self.xy_err = np.asarray(xy_err, dtype=np.float64)
        self.max_step = float(max_step)
        z = self.block_z if start_z is None else float(start_z)
        super().__init__([self.can[0] + self.xy_err[0], self.can[1] + self.xy_err[1], z],
                         self.can, width)
        self.n_apply = 0

    def apply(self, action) -> None:
        """代替 env.step：按上面两条规则推进 eef（专家只读 eef_pos / object_pos / gripper_width）。"""
        a = np.asarray(action, dtype=np.float64)
        self.n_apply += 1
        if a[2] > 0:
            self.eef_pos = np.array([self.can[0] + self.xy_err[0], self.can[1] + self.xy_err[1],
                                     self.can[2] + PRE_HEIGHT])
        else:
            eef = self.eef_pos.copy()
            eef[2] = max(self.block_z, eef[2] - min(abs(a[2]) * STEP_SCALE, self.max_step))
            self.eef_pos = eef


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"selftest 失败：{name} {detail}")


def main() -> int:
    n_ok = 0

    def check(name, cond, detail=""):
        nonlocal n_ok
        ck(name, cond, detail)
        n_ok += 1

    can_on_table = [0.16, 0.37, CAN_Z0]
    can_lifted = [0.16, 0.37, CAN_Z0 + LIFT_TARGET + 0.05]
    # 夹持时末端在 can 中心**上方** GRASP_OFFSET_Z（专家的抓取几何），所以「夹着」的桩件必须成对给，
    # 否则 ‖eef-can‖ 会超过 HOLD_DIST_MAX，测的就不是夹持分支了（第一版自测就是这里写错了）。
    eef_holding_table = [can_on_table[0], can_on_table[1], can_on_table[2] + GRASP_OFFSET_Z]
    eef_holding_lifted = [can_lifted[0], can_lifted[1], can_lifted[2] + GRASP_OFFSET_Z]
    eef_on_can_grasp = eef_holding_table
    eef_above_can = [0.16, 0.37, CAN_Z0 + PRE_HEIGHT]
    eef_far = [0.0, 0.2, 1.0]
    held_w = GRASP_HELD_WIDTH + 0.03      # 0.050：夹持模态实测中心
    empty_w = 0.001                       # 空合实测模态
    open_w = 0.078

    # 1) 夹着 + 已离地 ⇒ carry
    ex = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, held_w)).resume(can_z0=CAN_Z0)
    check("夹着且离地 ⇒ carry", ex.phase == "carry", ex.phase)
    # 2) 夹着 + 还没离地 ⇒ lift
    ex = ScriptedExpert(FakeEnv(eef_on_can_grasp, can_on_table, held_w)).resume(can_z0=CAN_Z0)
    check("夹着但没离地 ⇒ lift", ex.phase == "lift", ex.phase)
    # 2b) lift 判据用的必须是**传入的** can_z0，不是当前 can 的 z（否则判据永不成立）
    ex = ScriptedExpert(FakeEnv(eef_on_can_grasp, can_on_table, held_w)).resume(can_z0=CAN_Z0)
    check("can_z0 被写成传入值", abs(ex.can_z0 - CAN_Z0) < 1e-9, str(ex.can_z0))
    # 3) 没夹 + 末端已在 can 正上方且高度对上 ⇒ grasp
    ex = ScriptedExpert(FakeEnv(eef_on_can_grasp, can_on_table, open_w)).resume(can_z0=CAN_Z0)
    check("对准且高度对上 ⇒ grasp", ex.phase == "grasp", ex.phase)
    # 4) 没夹 + xy 对准但太高 ⇒ descend
    ex = ScriptedExpert(FakeEnv(eef_above_can, can_on_table, open_w)).resume(can_z0=CAN_Z0)
    check("xy 对准但太高 ⇒ descend", ex.phase == "descend", ex.phase)
    # 5) 没夹 + xy 没对准 ⇒ approach
    ex = ScriptedExpert(FakeEnv(eef_far, can_on_table, open_w)).resume(can_z0=CAN_Z0)
    check("xy 没对准 ⇒ approach", ex.phase == "approach", ex.phase)
    # 6) 宽度说夹着但 can 离末端很远（掉在下方）⇒ 不算夹持
    dropped = [eef_far[0], eef_far[1], eef_far[2] - HOLD_DIST_MAX - 0.02]
    ex = ScriptedExpert(FakeEnv(eef_far, dropped, held_w)).resume(can_z0=CAN_Z0)
    check("宽度夹持但距离超限 ⇒ 不判 carry/lift", ex.phase in ("approach", "descend", "grasp"), ex.phase)
    # 7) 距离很近但宽度是空合（can 就在末端正下方 3 cm，其实没夹住）⇒ 不算夹持
    just_below = [eef_above_can[0], eef_above_can[1], eef_above_can[2] - 0.03]
    ex = ScriptedExpert(FakeEnv(eef_above_can, just_below, empty_w)).resume(can_z0=CAN_Z0)
    check("空合 + 距离近 ⇒ 不判 lift/carry", ex.phase in ("approach", "descend", "grasp"), ex.phase)
    # 8) 缺 can_z0：env 有 resting_z ⇒ 用它；没有 ⇒ 报错（绝不拿当前 can z 兜底）
    ex = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, held_w, with_resting_z=True)).resume()
    check("缺省退回 env.resting_z", abs(ex.can_z0 - CAN_Z0) < 1e-9, str(ex.can_z0))
    try:
        ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, held_w)).resume()
        raise AssertionError("selftest 失败：缺 can_z0 且 env 无 resting_z 时应该报错")
    except ValueError:
        n_ok += 1
    # 8b) 反例钉死：如果拿当前 can z 当参考线，lift 判据会永不成立（这就是必须报错的原因）
    ex = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, held_w)).resume(can_z0=CAN_Z0)
    check("can_z0 传对时 lift 判据可达", can_lifted[2] > ex.can_z0 + LIFT_TARGET - 1e-9)
    ex_bad_can_z0 = can_lifted[2]
    check("can_z0 若取当前 can z，则 lift 判据不可达",
          not (can_lifted[2] > ex_bad_can_z0 + LIFT_TARGET))
    # 9) 参考量与计数器
    ex = ScriptedExpert(FakeEnv(eef_far, can_on_table, open_w)).resume(can_z0=CAN_Z0)
    check("target_xy 从 env 取", np.allclose(ex.target_xy, TARGET_XY))
    check("bin_pos 从 env 取", np.allclose(ex.bin_pos, BIN_POS))
    check("phase_step 归零", ex.phase_step == 0)
    check("grasp_try 归零", ex.grasp_try == 0)
    check("log 里留下接管痕迹", ex.log == [f"resume:{ex.phase}"], str(ex.log))
    # 10) resume 之后 __call__ 出的是合法 7 维动作，且夹爪语义与相位一致
    for phase, env_args in (("carry", (eef_holding_lifted, can_lifted, held_w)),
                            ("lift", (eef_on_can_grasp, can_on_table, held_w)),
                            ("grasp", (eef_on_can_grasp, can_on_table, open_w)),
                            ("descend", (eef_above_can, can_on_table, open_w)),
                            ("approach", (eef_far, can_on_table, open_w))):
        e = ScriptedExpert(FakeEnv(*env_args)).resume(can_z0=CAN_Z0)
        act = e()
        check(f"{phase}: 动作 7 维 float", act.shape == (7,) and act.dtype == np.float32, str(act))
        check(f"{phase}: 前 3 维在 [-1,1]", bool(np.all(np.abs(act[:3]) <= 1.0 + 1e-6)), str(act[:3]))
        check(f"{phase}: 姿态维恒 0", bool(np.all(act[3:6] == 0.0)), str(act[3:6]))
        want = 1.0 if phase in ("carry", "lift", "grasp") else -1.0
        check(f"{phase}: 夹爪符号正确", act[6] == want, f"{act[6]} vs {want}")
        check(f"{phase}: 相位标签与预期一致", e.phase in (phase, "settle", "place_descend", "release",
                                                          "retreat", "done", "descend", "carry"),
              f"{e.phase} vs {phase}")
    # 11) 幂等：连着 resume 两次不会累积状态
    e = ScriptedExpert(FakeEnv(eef_far, can_on_table, open_w))
    e.resume(can_z0=CAN_Z0)
    e.resume(can_z0=CAN_Z0)
    check("重复 resume 幂等", e.log == ["resume:approach", "resume:approach"] and e.phase_step == 0, str(e.log))
    # 12) reset() 的行为没被 resume() 影响（G1 之外的第二道保险）
    e = ScriptedExpert(FakeEnv(eef_far, can_on_table, open_w)).reset()
    check("reset 仍然是 approach", e.phase == "approach" and e.log == ["approach"], str(e.log))
    check("reset 的 can_z0 = 当前 can z（原语义不变）", abs(e.can_z0 - CAN_Z0) < 1e-9)
    # 13) 反向专家继承同一套推断（CARRY_Z_LOCK 是它唯一的差别）
    r = ReverseScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, held_w)).resume(can_z0=CAN_Z0)
    check("反向专家 resume ⇒ carry", r.phase == "carry", r.phase)
    check("反向专家 CARRY_Z_LOCK=True", r.CARRY_Z_LOCK is True)
    check("正向专家 CARRY_Z_LOCK=False", ScriptedExpert.CARRY_Z_LOCK is False)
    ra = r()
    check("反向 carry 的动作合法", ra.shape == (7,) and bool(np.all(np.abs(ra[:3]) <= 1.0 + 1e-6)))
    # 14) 边界：can 高度刚好等于 can_z0 + LIFT_TARGET ⇒ 判 lift（判据是严格大于）
    edge = [can_on_table[0], can_on_table[1], CAN_Z0 + LIFT_TARGET]
    e = ScriptedExpert(FakeEnv([edge[0], edge[1], edge[2] + GRASP_OFFSET_Z], edge,
                               held_w)).resume(can_z0=CAN_Z0)
    check("刚好等于阈值 ⇒ lift（不是 carry）", e.phase == "lift", e.phase)
    # 15) 边界：xy 偏差刚好等于 XY_TOL ⇒ 不算对准（判据是严格小于）
    edge_xy = [can_on_table[0] + XY_TOL, can_on_table[1], can_on_table[2]]
    e = ScriptedExpert(FakeEnv([edge_xy[0], edge_xy[1], CAN_Z0 + GRASP_OFFSET_Z], can_on_table,
                               open_w)).resume(can_z0=CAN_Z0)
    check("xy 偏差 = XY_TOL ⇒ approach", e.phase == "approach", e.phase)
    # 15b) 夹持宽度上界（HOLD_WIDTH_MAX）：张开的爪子也 > GRASP_HELD_WIDTH，必须被上界挡掉
    check("HOLD_WIDTH_MAX 高于搬运段实测 p99", HOLD_WIDTH_MAX >= 0.0609, str(HOLD_WIDTH_MAX))
    check("HOLD_WIDTH_MAX 低于张开模态实测 min", HOLD_WIDTH_MAX < 0.0781, str(HOLD_WIDTH_MAX))
    e = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, open_w)).resume(can_z0=CAN_Z0)
    check("张开(0.078) + 距离很近 ⇒ 不判夹持", e.phase in ("approach", "descend", "grasp"), e.phase)
    e = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, HOLD_WIDTH_MAX - 0.002)).resume(can_z0=CAN_Z0)
    check("宽度 0.070（歪夹）⇒ 仍判夹持 ⇒ carry", e.phase == "carry", e.phase)
    e = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, HOLD_WIDTH_MAX + 0.001)).resume(can_z0=CAN_Z0)
    check("宽度刚过上界 ⇒ 不判夹持", e.phase != "carry", e.phase)
    e = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, GRASP_HELD_WIDTH - 0.001)).resume(can_z0=CAN_Z0)
    check("宽度刚过下界以下（空合）⇒ 不判夹持", e.phase != "carry", e.phase)
    e = ScriptedExpert(FakeEnv(eef_holding_lifted, can_lifted, GRASP_HELD_WIDTH + 0.001)).resume(can_z0=CAN_Z0)
    check("宽度刚过下界 ⇒ 判夹持", e.phase in ("carry", "lift"), e.phase)
    # 16) 边界：z 偏差刚好等于 Z_TOL ⇒ descend（不是 grasp）
    e = ScriptedExpert(FakeEnv([can_on_table[0], can_on_table[1], CAN_Z0 + GRASP_OFFSET_Z + Z_TOL],
                               can_on_table, open_w)).resume(can_z0=CAN_Z0)
    check("z 偏差 = Z_TOL ⇒ descend", e.phase == "descend", e.phase)

    # ── 17) 档 5.1：descend 停滞阶梯（坑 46「相位必须有超时退出」的修法）──────────────
    W, T = DESCEND_STALL_MAX, DESCEND_STALL_DZ
    check("停滞阈值 = 0.1 mm/步（标定出处 runs/s5_1_stall_calib_*）", abs(T - 1e-4) < 1e-15, str(T))
    check("停滞窗口 = 25 步（同上）", W == 25, str(W))
    check("restage 上限 = 2", DESCEND_MAX_RESTAGES == 2, str(DESCEND_MAX_RESTAGES))
    check("give_up 不在闭爪相位里（认输时必须张开）", GIVE_UP_PHASE not in CLOSED_PHASES)

    can_blk = [0.1714, 0.3360, CAN_Z0]              # seed 7015 的实测 can 位置
    block_z = CAN_Z0 + GRASP_OFFSET_Z + 0.025       # 实测卡在 z_err = +25 mm（7015 的 eef_z ≈ 0.900）
    env = BlockedDescendEnv(can_blk, block_z)
    e = ScriptedExpert(env).resume(can_z0=CAN_Z0)
    check("被挡桩件：resume 推成 descend", e.phase == "descend", e.phase)
    check("接管后新属性已初始化", (e.restages, e.unrecoverable, e._descend_stall, e._prev_eef_z)
          == (0, False, 0, None), str((e.restages, e.unrecoverable, e._descend_stall, e._prev_eef_z)))
    for _ in range(W):                              # 第 1 步没有「上一步 z」⇒ 不计停滞
        a = e()
        env.apply(a)
    check(f"{W} 步全被挡还没 restage（首步不计 ⇒ 计数 {W - 1}）",
          e.restages == 0 and e.phase == "descend" and e._descend_stall == W - 1,
          f"restages={e.restages} phase={e.phase} stall={e._descend_stall}")
    check("被挡期间命令一直是下降", a[2] < 0 and a[6] == -1.0, str(a))
    a = e()
    env.apply(a)
    check(f"第 {W + 1} 步 ⇒ restage1 并退回 approach", e.restages == 1 and e.phase == "approach",
          f"restages={e.restages} phase={e.phase}")
    check("restage 记进 log", "descend_restage1" in e.log, str(e.log))
    check("restage 那一步的目标是 PRE_HEIGHT（上升）", a[2] > 0, str(a))
    n_giveup = -1
    for k in range(200):
        a = e()
        env.apply(a)
        if e.unrecoverable and n_giveup < 0:
            n_giveup = k + 1
            break
    check("阶梯会终止：认输（unrecoverable）", e.unrecoverable, f"restages={e.restages} phase={e.phase}")
    check("认输时相位 = give_up", e.phase == GIVE_UP_PHASE, e.phase)
    check("认输前恰好用满 restage 上限", e.restages == DESCEND_MAX_RESTAGES, str(e.restages))
    check("认输记进 log", "descend_unrecoverable" in e.log, str(e.log))
    check(f"认输只用 {n_giveup} 步（远小于档 5 实测的 162~305 步空转）", 0 < n_giveup <= 130, str(n_giveup))
    check("give_up 的动作 = 原地保持（前三维全 0）", np.allclose(a[:3], 0.0), str(a[:3]))
    check("give_up 的动作 = 张开爪子", a[6] == GRIP_OPEN, str(a[6]))
    check("give_up 的姿态维仍为 0", np.allclose(a[3:6], 0.0), str(a[3:6]))
    for _ in range(10):                             # 认输之后必须稳定停在 give_up
        a2 = e()
        env.apply(a2)
    check("give_up 是吸收态（不再换相位）", e.phase == GIVE_UP_PHASE and e.restages == DESCEND_MAX_RESTAGES,
          f"{e.phase}/{e.restages}")
    check("give_up 的动作流恒定", np.allclose(a2, a), f"{a2} vs {a}")

    # 18) 对照组 A：没有被挡（block_z 就在抓取带）⇒ 一次 restage 都不该有
    env_ok = BlockedDescendEnv(can_blk, CAN_Z0 + GRASP_OFFSET_Z, start_z=CAN_Z0 + GRASP_OFFSET_Z + 0.06)
    e_ok = ScriptedExpert(env_ok).resume(can_z0=CAN_Z0)
    got_grasp = False
    for _ in range(60):
        a = e_ok()
        env_ok.apply(a)
        if e_ok.phase == "grasp":
            got_grasp = True
            break
    check("健康下降 ⇒ 进 grasp 且零 restage", got_grasp and e_ok.restages == 0 and not e_ok.unrecoverable,
          f"phase={e_ok.phase} restages={e_ok.restages}")

    # 19) 对照组 B：慢但**在动**（0.2 mm/步 > T）⇒ 不算停滞（阈值语义）
    env_slow = BlockedDescendEnv(can_blk, block_z, start_z=block_z + 0.006, max_step=0.0002)
    e_slow = ScriptedExpert(env_slow).resume(can_z0=CAN_Z0)
    for _ in range(30):
        a = e_slow()
        env_slow.apply(a)
    check("每步 0.2 mm 的真实下降 ⇒ 30 步内零 restage", e_slow.restages == 0 and e_slow.phase == "descend",
          f"restages={e_slow.restages} phase={e_slow.phase} stall={e_slow._descend_stall}")

    # 20) reset() / resume() 都必须清掉新属性（否则跨局泄漏 = 上一局的认输带进下一局）
    e.restages, e.unrecoverable, e._descend_stall, e._prev_eef_z = 2, True, 7, 0.5
    env2 = BlockedDescendEnv(can_blk, block_z)
    e2 = ScriptedExpert(env2)
    e2.restages, e2.unrecoverable, e2._descend_stall, e2._prev_eef_z = 2, True, 7, 0.5
    e2.reset()
    check("reset() 清掉新属性", (e2.restages, e2.unrecoverable, e2._descend_stall, e2._prev_eef_z)
          == (0, False, 0, None), str((e2.restages, e2.unrecoverable, e2._descend_stall, e2._prev_eef_z)))
    e2.restages, e2.unrecoverable, e2._descend_stall, e2._prev_eef_z = 2, True, 7, 0.5
    e2.resume(can_z0=CAN_Z0)
    check("resume() 清掉新属性", (e2.restages, e2.unrecoverable, e2._descend_stall, e2._prev_eef_z)
          == (0, False, 0, None), str((e2.restages, e2.unrecoverable, e2._descend_stall, e2._prev_eef_z)))
    # 换相位清停滞计数（游程必须是**连续**的）
    e2._descend_stall = 9
    e2._set("approach")
    check("_set() 清停滞计数", e2._descend_stall == 0, str(e2._descend_stall))
    check("反向专家继承同一套常数", (ReverseScriptedExpert.DESCEND_STALL_MAX if
                                 hasattr(ReverseScriptedExpert, "DESCEND_STALL_MAX") else W) == W)

    print(f"[resume-selftest] 全绿：{n_ok} 项（假 env 桩，未使用 GPU / 未读写 runs）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
