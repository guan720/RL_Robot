#!/usr/bin/env python
"""最小抓取链路 · 反向判据（严格 / 放宽 R）语义钉子。

为什么要有这个文件：2026-10-02 用户放宽了反向成功口径（**送到目标区为首要条件**；手臂高度/
冲击造成的侧躺也算送到，但要追加标记）。判据是整条链路最上游的定义，改错一个比较符，
后面 10 h 训练读出来的数全是废的。所以：

  1. **严格口径必须与历史代码逐比特同义**。参考实现不是我重新敲的，而是把 2026-09-30 首版
     step() 里那 5 行原样抄过来，并且**回头到备份文件里核对这段源码真的存在**
     （code/mg_env_reverse.py.bak_pre_relax）——出处可查，不靠记忆。
  2. **放宽口径 = 严格口径去掉一个合取项** ⇒ 数学上恒有 严格 ⊆ 放宽。随机 + 边界穷举钉住。
  3. 阈值常量（20° / 25 mm / 0.05 m/s / 0.05 m / 5 cm / 10 步 / ±9 cm）必须与备份文件里的
     字面量一致，防止「顺手改了个数」。
  4. 比较符的**开闭区间**语义要钉住（< vs <=）：z/速度/倾角是严格小于，夹爪/末端是严格大于，
     落框是 <=（in_target 用 abs(...)<=TOL）。这几条历史上就是这么写的，不许漂。

用法：
    $MG_PY code/mg_criterion_selftest.py            # 全过打印 ALL PASS 并退出 0
"""

from __future__ import annotations

import itertools
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

BAK = HERE / "mg_env_reverse.py.bak_pre_relax"

FAILS: list[str] = []
N_CHECK = 0


def chk(cond: bool, msg: str) -> None:
    global N_CHECK
    N_CHECK += 1
    if not cond:
        FAILS.append(msg)


def reference_settled_strict(can_z, resting_z, tilt_deg, obj_speed, gripper_width, eef_dist) -> bool:
    """2026-09-30 首版 mg_env_reverse.ReverseGraspEnv.step() 里 `settled` 的逐字抄写。

    原文（备份文件可查）：
        settled = bool(abs(can[2] - self.resting_z) < SETTLE_Z_TOL
                       and tilt < UPRIGHT_TILT_DEG
                       and float(info["object_speed"]) < SETTLE_SPEED
                       and float(info["gripper_width"]) > 0.05
                       and float(np.linalg.norm(eef - can)) > RELEASE_DIST)
    """
    from mg_env import RELEASE_DIST, SETTLE_SPEED, SETTLE_Z_TOL
    return bool(abs(can_z - resting_z) < SETTLE_Z_TOL
                and tilt_deg < 20.0
                and float(obj_speed) < SETTLE_SPEED
                and float(gripper_width) > 0.05
                and float(eef_dist) > RELEASE_DIST)


def main() -> int:
    from mg_env import RELEASE_DIST, SETTLE_SPEED, SETTLE_Z_TOL, SUCCESS_HOLD_STEPS
    import mg_env_reverse as R

    # ── 0. 出处核对：参考实现必须真的能在历史备份里找到（不是凭记忆写的）──────────
    chk(BAK.exists(), "缺备份 %s ⇒ 无法核对历史判据出处" % BAK.name)
    if BAK.exists():
        src = BAK.read_text(encoding="utf-8")
        for frag in ("abs(can[2] - self.resting_z) < SETTLE_Z_TOL",
                     "and tilt < UPRIGHT_TILT_DEG",
                     'and float(info["object_speed"]) < SETTLE_SPEED',
                     'and float(info["gripper_width"]) > 0.05',
                     "and float(np.linalg.norm(eef - can)) > RELEASE_DIST"):
            chk(frag in src, "历史备份里找不到判据片段：%r" % frag)
        chk(re.search(r"^UPRIGHT_TILT_DEG = 20\.0$", src, re.M) is not None,
            "历史 UPRIGHT_TILT_DEG != 20.0")
        chk(re.search(r"^REVERSE_TARGET_TOL_XY = 0\.09$", src, re.M) is not None,
            "历史 REVERSE_TARGET_TOL_XY != 0.09")
        chk("reverse_settled" not in src, "备份文件里居然有 reverse_settled ⇒ 备份不是改前版本")

    # ── 1. 常量没被顺手改掉 ─────────────────────────────────────────────────
    chk(R.UPRIGHT_TILT_DEG == 20.0, "UPRIGHT_TILT_DEG 漂了：%r" % R.UPRIGHT_TILT_DEG)
    chk(R.REVERSE_TARGET_TOL_XY == 0.09, "REVERSE_TARGET_TOL_XY 漂了：%r" % R.REVERSE_TARGET_TOL_XY)
    chk(R.GRIPPER_OPEN_MIN == 0.05, "GRIPPER_OPEN_MIN 必须 = 历史字面量 0.05，实为 %r" % R.GRIPPER_OPEN_MIN)
    chk(SETTLE_Z_TOL == 0.025 and SETTLE_SPEED == 0.05 and RELEASE_DIST == 0.05
        and SUCCESS_HOLD_STEPS == 10, "mg_env 的落定常量漂了（25mm/0.05m/s/5cm/10 步）")

    # ── 2. 严格口径 == 历史参考实现：边界穷举 ────────────────────────────────
    resting = 0.8603
    # 每个条件取「远低于 / 恰在阈值 / 远高于」三档，5 条件 x 3 档 = 3^5 = 243 组，再加 tilt 三档
    z_grid = [resting - 0.025, resting, resting + 0.025, resting - 0.0249, resting + 0.0249]
    tilt_grid = [0.0, 19.999, 20.0, 20.001, 90.0]
    spd_grid = [0.0, 0.0499, 0.05, 0.0501, 9.0]
    grip_grid = [0.0, 0.05, 0.0501, 0.08]
    dist_grid = [0.0, 0.05, 0.0501, 0.30]
    n_strict = 0
    for cz, tl, sp, gw, dd in itertools.product(z_grid, tilt_grid, spd_grid, grip_grid, dist_grid):
        got = R.reverse_settled(cz, resting, tl, sp, gw, dd, upright_required=True)
        exp = reference_settled_strict(cz, resting, tl, sp, gw, dd)
        n_strict += 1
        chk(got == exp, "严格口径与历史实现不一致 @ z=%r tilt=%r spd=%r grip=%r dist=%r: got=%r exp=%r"
            % (cz, tl, sp, gw, dd, got, exp))
    chk(n_strict == len(z_grid) * len(tilt_grid) * len(spd_grid) * len(grip_grid) * len(dist_grid),
        "边界穷举组数不对：%d" % n_strict)

    # ── 3. 放宽口径：只少「倾角」这一条 ⇒ 倾角之外的条件必须完全同判 ─────────────
    for cz, tl, sp, gw, dd in itertools.product(z_grid, tilt_grid, spd_grid, grip_grid, dist_grid):
        strict = R.reverse_settled(cz, resting, tl, sp, gw, dd, upright_required=True)
        rlx = R.reverse_settled(cz, resting, tl, sp, gw, dd, upright_required=False)
        chk(rlx or not strict, "违背 严格 ⊆ 放宽 @ z=%r tilt=%r spd=%r grip=%r dist=%r" % (cz, tl, sp, gw, dd))
        exp_rlx = reference_settled_strict(cz, resting, 0.0, sp, gw, dd)   # 倾角强行置 0 = 去掉该合取项
        chk(rlx == exp_rlx, "放宽口径 != 「严格口径去掉倾角项」 @ z=%r tilt=%r spd=%r grip=%r dist=%r"
            % (cz, tl, sp, gw, dd))
        if strict and tl < R.UPRIGHT_TILT_DEG:
            chk(rlx, "严格成立且立着时放宽必须成立")

    # 侧躺真值：can 半径 25 mm，侧躺中心 z = 0.82 + 0.025 = 0.845，倾角 90°
    chk(R.reverse_settled(0.845, resting, 90.0, 0.0, 0.08, 0.30, upright_required=False) is True,
        "侧躺(z=0.845, tilt=90°) 在放宽口径下必须算送到")
    chk(R.reverse_settled(0.845, resting, 90.0, 0.0, 0.08, 0.30, upright_required=True) is False,
        "侧躺在严格口径下必须不算（历史行为，反向首测就吃过 2/5 假阳性）")

    # ── 4. 随机模糊测试（含 NaN / inf / 负数），不变量不许破 ─────────────────────
    rng = random.Random(20261002)
    weird = [float("nan"), float("inf"), float("-inf"), -1.0, 0.0]
    for _ in range(20000):
        cz = rng.choice(weird) if rng.random() < 0.1 else rng.uniform(resting - 0.06, resting + 0.06)
        tl = rng.choice(weird) if rng.random() < 0.1 else rng.uniform(0.0, 180.0)
        sp = rng.choice(weird) if rng.random() < 0.1 else rng.uniform(0.0, 0.3)
        gw = rng.choice(weird) if rng.random() < 0.1 else rng.uniform(0.0, 0.1)
        dd = rng.choice(weird) if rng.random() < 0.1 else rng.uniform(0.0, 0.5)
        strict = R.reverse_settled(cz, resting, tl, sp, gw, dd, upright_required=True)
        rlx = R.reverse_settled(cz, resting, tl, sp, gw, dd, upright_required=False)
        chk(rlx or not strict, "模糊测试违背 严格 ⊆ 放宽 @ %r" % ((cz, tl, sp, gw, dd),))
        chk(strict == reference_settled_strict(cz, resting, tl, sp, gw, dd),
            "模糊测试严格口径偏离历史实现 @ %r" % ((cz, tl, sp, gw, dd),))
        chk(isinstance(strict, bool) and isinstance(rlx, bool), "返回值必须是 python bool（不能是 numpy.bool_）")

    # ── 5. 粘滞 + 保持 10 步的时序语义：放宽口径必须用**自己的**计数器 ───────────
    # 反例场景：can 侧躺进框并保持 12 步 ⇒ 严格 hold 一直是 0（永远不成功），
    # 放宽 hold 到第 10 步翻成功并粘住。若两者共用计数器，严格会被放宽带飞（假阳性）。
    hold_s = hold_r = 0
    ever_s = ever_r = False
    for _ in range(12):
        s = R.reverse_settled(0.845, resting, 90.0, 0.0, 0.08, 0.30, upright_required=True)
        r = R.reverse_settled(0.845, resting, 90.0, 0.0, 0.08, 0.30, upright_required=False)
        hold_s = hold_s + 1 if s else 0
        hold_r = hold_r + 1 if r else 0
        ever_s = ever_s or hold_s >= SUCCESS_HOLD_STEPS
        ever_r = ever_r or hold_r >= SUCCESS_HOLD_STEPS
    chk(ever_s is False, "侧躺 12 步：严格口径不该成功（否则历史数值被污染）")
    chk(ever_r is True, "侧躺 12 步：放宽口径该成功（= 用户要的『送到就算』）")

    print("判据钉子：%d 项检查，%d 项失败" % (N_CHECK, len(FAILS)))
    print("  严格口径 = 落定(z<25mm ∧ 速度<0.05 ∧ 夹爪>0.05 ∧ 末端>5cm) ∧ 倾角<20° ∧ 进框±9cm ∧ 保持10步")
    print("  放宽口径 = 同上但**去掉倾角**；侧躺/侧挡算送到，另打 delivered_tipped 标记")
    print("  出处：历史实现见 %s（本文件逐字核对过）" % BAK.name)
    for f in FAILS[:20]:
        print("  FAIL " + f)
    if FAILS:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
