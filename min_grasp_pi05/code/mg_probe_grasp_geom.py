#!/usr/bin/env python
"""最小抓取链路 · 档 6B（改用途）：**从真环境**测抓取几何常数，钉死仓里互相矛盾的两个数。

为什么要有这个探针（2026-10-03 12:58 实测发现的矛盾）：
  仓里同一个「单侧指隙」被写成两个差一倍的数，而且**都被当依据用过**：
    * `code/mg_expert.py:59`：「单侧指隙 ≈ (0.0805−0.066)/2 ≈ 7 mm」⇒ 由此推出「指隙 7 mm < `XY_TOL` 8 mm
      = 几何矛盾」，档 5.1 的 descend 停滞机理、以及「收紧专家对准判据 + 重采 180 条示范 + 重训 ~10 h」
      这个方案都建立在它上面；
    * `code/mg_diag_trace.py:14` / `code/mg_diag_miss.py:46`：「can 直径 0.050、`CAN_RADIUS=0.025`」
      ⇒ 按它算单侧指隙是 (0.0805−0.050)/2 ≈ **15.3 mm**，比 `XY_TOL` 8 mm **宽一倍** ⇒ 根本没有矛盾。
  本探针实测：**can 直径 = 50.04 mm**（geom AABB 2×0.02502），全开 80.5 mm ⇒ 单侧指隙 **15.24 mm**。
  而 `mg_expert.py` 里的 0.066 实际是**手掌碰撞盒的 x 向尺寸**（`gripper0_right_hand_collision`
  size[0]=0.03164 ⇒ 2×0.03164 = 63.3 mm ≈ 0.066），**不是 can 的直径** ⇒ 那个 7 mm 是把「手掌宽」
  当成了「can 粗」，几何矛盾的前提不成立。
  按坑 52（机理门常数只来自真环境，不来自桩件/注释），这一节必须实测落盘，不能再靠注释传抄。

顺带钉掉第二个传抄错：`code/mg_diag_miss.py:CAN_TOP_Z = 0.9206`（= 0.8603 + 0.0603）用的是
`mg_env.py:CAN_HALF_HEIGHT=0.0603`，但实测**支撑面 z=0.82**、can 半高 = **0.0407**（geom AABB）
⇒ 真 can 顶面 = 0.8603 + 0.0407 = **0.9010**，比 0.9206 低 **2 cm**。
（两个参数化都给出 0.8603 = 0.82+0.0403 = 0.80+0.0603，所以静置高度看不出矛盾；只有顶面会露馅。）
`CAN_TOP_Z` 只被 `min_dxy_below_can_top_cm` 这个诊断字段用（不参与分桶、不参与任何门），
所以本档不改它 —— 只把真值落盘，避免下一个档又被 0.9206 带跑。

本探针**不跑策略、不扫 D_CRIT**：格 6A 已经测出 A 类失败里「高度对、横向 ≤1.5 cm」的 F 桶 = **0/41**，
即策略从来没在指隙量级（≤1.5 cm）的偏差下合过爪 ⇒ D_CRIT 无论测出多少都改不了任何决策
（跑了也不能改变行动 = 不该跑）。所以 6B 缩成「测常数」这一件小事。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_grasp_geom.py --out runs/s6_grasp_geom'
    $MG_PY code/mg_probe_grasp_geom.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_expert import XY_TOL, Z_TOL, GRASP_OFFSET_Z  # noqa: E402  专家的对准容差（被检验对象）

GEOM_MESH = 7
GEOM_BOX = 6


def finger_gap(open_width: float, obj_diam: float) -> float:
    """单侧指隙 = (全开内间距 − 物体直径) / 2。全部单位米。

    `open_width` 的语义（实测钉住）：robosuite 的 `gripper_width` = **两指垫内侧面间距**，
    证据 = 空合到底时 width→0.001（≈0）、夹住 can 时 width=0.0417~0.050（≈can 直径 0.050）。
    """
    return (float(open_width) - float(obj_diam)) / 2.0


def no_contradiction(open_width: float, obj_diam: float, xy_tol: float) -> dict:
    """「指隙 < 对准容差 ⇒ 几何矛盾」这个论断成不成立。

    矛盾成立的条件：单侧指隙 < xy_tol（此时专家即使对准达标，合爪也会顶到物体）。
    实测：指隙 15.24 mm vs xy_tol 8 mm ⇒ 指隙**宽 1.9 倍** ⇒ 不成立。
    """
    gap = finger_gap(open_width, obj_diam)
    return {"finger_gap_m": round(gap, 6), "finger_gap_mm": round(gap * 1000.0, 2),
            "xy_tol_mm": round(float(xy_tol) * 1000.0, 2),
            "gap_over_tol": round(gap / float(xy_tol), 3) if xy_tol else None,
            "contradiction": bool(gap < float(xy_tol))}


def measure(env, seed: int = 7000) -> dict:
    """从**真环境**读几何常数。返回全部以米为单位，另附 mm 便于对照注释里的传抄值。"""
    obs = env.reset(seed=seed)
    sim = env.env.sim
    model = sim.model

    def geoms(pred):
        out = []
        for g in range(model.ngeom):
            nm = model.geom_id2name(g) or ""
            if pred(nm):
                out.append({"name": nm, "type": int(model.geom_type[g]),
                            "size": [round(float(v), 6) for v in model.geom_size[g]],
                            "pos": [round(float(v), 6) for v in model.geom_pos[g]]})
        return out

    can = geoms(lambda n: n in ("Can_g0", "Can_g0_visual", "VisualCan_g0"))
    hand = geoms(lambda n: n.startswith("gripper0_right_hand"))
    fingers = geoms(lambda n: "finger" in n)

    # can 直径 = 碰撞 geom 的 AABB 在 x/y 上的直径（取 max，can 是回转体，x≈y）
    can_col = [c for c in can if c["name"] == "Can_g0"] or can
    aabb = np.asarray(can_col[0]["size"], dtype=np.float64)
    can_radius = float(max(aabb[0], aabb[1]))
    can_half_h = float(aabb[2])

    rest_z = float(env.object_pos[2])
    eef_z = float(env.eef_pos[2])

    # 支撑面 z：静置中心高 − can 半高（两个参数化都成立，实测取这条）
    support_z = rest_z - can_half_h

    # 夹爪三种模态的 width（真环境实测，不是注释传抄）
    width_at_reset = float(env.gripper_width)
    w_open = width_drive(env, -1.0, 40)
    w_close = width_drive(env, +1.0, 40)

    return {
        "seed": seed,
        "can": {"radius_m": round(can_radius, 6), "diameter_m": round(2 * can_radius, 6),
                "diameter_mm": round(2 * can_radius * 1000.0, 2),
                "half_height_m": round(can_half_h, 6), "geoms": can},
        "gripper": {"width_at_reset": round(width_at_reset, 6),
                    "width_fully_open": round(w_open, 6), "width_empty_close": round(w_close, 6),
                    "width_fully_open_mm": round(w_open * 1000.0, 2),
                    "hand_geoms": hand, "finger_geoms": fingers,
                    "hand_x_extent_m": round(2 * float(hand[0]["size"][0]), 6) if hand else None,
                    "hand_x_extent_mm": round(2 * float(hand[0]["size"][0]) * 1000.0, 2) if hand else None},
        "heights": {"can_rest_center_z": round(rest_z, 6), "can_top_z_true": round(rest_z + can_half_h, 6),
                    "support_surface_z": round(support_z, 6), "eef_z_at_reset": round(eef_z, 6),
                    "grasp_z_expected": round(rest_z + GRASP_OFFSET_Z, 6)},
        "bins": {"bin2_pos": [round(float(v), 6) for v in env.env.bin2_pos],
                 "reverse_target_xy": [round(float(v), 6) for v in env.target_xy]},
        "expert_tolerances": {"XY_TOL_m": XY_TOL, "Z_TOL_m": Z_TOL, "GRASP_OFFSET_Z_m": GRASP_OFFSET_Z},
        "obs_keys": sorted(list(obs.keys())) if isinstance(obs, dict) else None,
        "measured_at": datetime.now().isoformat(timespec="seconds"),
    }


def width_drive(env, grip_action: float, steps: int) -> float:
    """把夹爪命令打到底（-1 张开 / +1 闭合），返回稳定后的 `gripper_width`。

    为什么要真驱动而不是读常量：`GRIP_OPEN_WIDTH=0.0788` / `GRIP_EMPTY_CLOSE=0.0010` 是
    `mg_env.py` 里的传抄值，实测在 0.0795~0.0805 之间抖 ⇒ 指隙算出来会差 1 mm 量级，
    而「7 mm vs 15 mm」的裁定正好卡在这个量级上，必须实测。
    """
    zero = np.zeros(7, dtype=np.float64)
    w = float(env.gripper_width)
    for _ in range(steps):
        a = zero.copy()
        a[6] = grip_action
        env.step(a)
        w = float(env.gripper_width)
    return w


def build_report(m: dict, chk: dict) -> str:
    L: list[str] = []
    P = L.append
    P("# 档 6B · 抓取几何常数（**真环境实测**，不是注释传抄）")
    P("")
    P(f"* 生成时间：{m['measured_at']}；工具 `code/mg_probe_grasp_geom.py`；初态 seed={m['seed']}")
    P("* 出处纪律：坑 52 —— 机理门常数只来自真环境。本文件里每个数都能用 `--out` 重跑复现。")
    P("")
    P("## 一、can")
    P("")
    P(f"* 半径 = **{m['can']['radius_m']*1000:.2f} mm**（geom `Can_g0` 的 AABB，取 size[0]/size[1] 的较大者）")
    P(f"* 直径 = **{m['can']['diameter_mm']:.2f} mm** ⇒ 与 `mg_diag_trace.py:14`「can 直径 0.050」一致，")
    P(f"  与 `mg_expert.py:59` 用来算指隙的 **0.066 不一致**（那个数其实是手掌宽，见下）")
    P(f"* 半高 = **{m['can']['half_height_m']*1000:.2f} mm**（AABB size[2]）")
    P("")
    P("## 二、夹爪（三种模态的 `gripper_width`，真驱动 40 步后读稳定值）")
    P("")
    P(f"* reset 后 = {m['gripper']['width_at_reset']:.5f} m（「半合」，不能当张开用）")
    P(f"* 命令 -1 张开到底 = **{m['gripper']['width_fully_open']:.5f} m = {m['gripper']['width_fully_open_mm']:.2f} mm**")
    P(f"* 命令 +1 空合到底 = {m['gripper']['width_empty_close']:.5f} m（≈0 ⇒ 证实 width 的语义就是**两指垫内侧面间距**）")
    if m["gripper"]["hand_x_extent_mm"]:
        P(f"* 手掌碰撞盒 x 向全宽 = **{m['gripper']['hand_x_extent_mm']:.2f} mm**"
          f"（`gripper0_right_hand_collision` size[0]={m['gripper']['hand_geoms'][0]['size'][0]}）"
          " ⇒ **这就是 `mg_expert.py:59` 里那个 0.066 的真实身份**：手掌宽，不是 can 直径。")
    P("")
    P("## 三、单侧指隙 vs 专家对准容差（**本探针要裁定的那个矛盾**）")
    P("")
    P(f"* 单侧指隙 = (全开 {m['gripper']['width_fully_open_mm']:.2f} − can 直径 {m['can']['diameter_mm']:.2f}) / 2 "
      f"= **{chk['finger_gap_mm']:.2f} mm**")
    P(f"* 专家对准容差 `XY_TOL` = **{chk['xy_tol_mm']:.2f} mm**")
    P(f"* 指隙 / 容差 = **{chk['gap_over_tol']:.2f}×**")
    P("")
    if chk["contradiction"]:
        P("* ⇒ 🚫 **几何矛盾成立**：指隙 < 容差 ⇒ 专家对准达标也可能顶到 can，"
          "「收紧 `XY_TOL` + 重采示范 + 重训」这个 10 h 方案有物理依据，值得预注册。")
    else:
        P("* ⇒ ✅ **几何矛盾不成立**：指隙比容差宽 "
          f"{chk['gap_over_tol']:.2f}×，专家即使按 8 mm 容差对准，合爪时两侧还各有 "
          f"{chk['finger_gap_mm'] - chk['xy_tol_mm']:.2f} mm 余量。")
        hx = m["gripper"]["hand_x_extent_mm"]
        P(f"* ⇒ **`mg_expert.py:59` 的「(0.0805−0.066)/2 ≈ 7 mm」是把「手掌宽 {hx:.1f} mm」"
          f"当成了「can 粗 {m['can']['diameter_mm']:.1f} mm」**，")
        P("  由它推出的「指隙 < 容差」不成立。据此：**「收紧专家 `XY_TOL` → 重采 180 条示范 → 重训 ~10 h」")
        P("  这个方案失去物理依据，**不预注册、不执行**（省下 ~10 h GPU）。")
        P("* 与格 6A 的独立证据一致：A 类失败里「高度对、横向 ≤1.5 cm」的 **F 桶 = 0/41**"
          "（`runs/S6_GEOM_A.md` 第二节）⇒ 策略从来没在指隙量级的偏差下合过爪，"
          "它的横向偏差是 1.7~4.4 cm，比指隙大一个量级。")
    P("")
    P("## 四、高度基准（顺带钉掉 `CAN_TOP_Z` 的传抄错）")
    P("")
    P(f"* can 静置中心 z = {m['heights']['can_rest_center_z']:.4f}")
    P(f"* 支撑面 z = 中心 − 半高 = **{m['heights']['support_surface_z']:.4f}**（不是 `mg_env.py:72` 注释里的 0.80）")
    P(f"* **真 can 顶面 z = {m['heights']['can_top_z_true']:.4f}**；"
      f"`mg_diag_miss.py:CAN_TOP_Z = 0.9206` ⇒ 偏高 "
      f"{(0.9206 - m['heights']['can_top_z_true'])*1000:.1f} mm")
    P("  （两个参数化都给出静置中心 0.8603 = 0.82+0.0403 = 0.80+0.0603，所以静置高度看不出矛盾，只有顶面露馅）")
    P(f"* 专家合爪目标高度 = can 中心 + GRASP_OFFSET_Z({GRASP_OFFSET_Z}) = {m['heights']['grasp_z_expected']:.4f}"
      "；反向示范同口径实测中位 0.8784（`runs/S6_GEOM_A.md` 第一节）⇒ 差 "
      f"{(0.8784 - m['heights']['grasp_z_expected'])*1000:.1f} mm，一致。")
    P("")
    P("## 五、bin / 目标")
    P("")
    P(f"* bin2_pos = {m['bins']['bin2_pos']}；反向目标 target_xy = {m['bins']['reverse_target_xy']}")
    P("")
    P("## 六、复现")
    P("")
    P("```bash")
    P("source code/env.sh")
    P("$MG_PY code/mg_probe_grasp_geom.py --selftest")
    P("$MG_PY code/mg_probe_grasp_geom.py --out runs/s6_grasp_geom")
    P("```")
    return "\n".join(L) + "\n"


def selftest() -> int:
    fails: list[str] = []
    n = 0

    def chk(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            fails.append(msg)

    # 指隙算术
    chk(abs(finger_gap(0.0805, 0.0500) - 0.01525) < 1e-9, "全开 80.5、can 50.0 ⇒ 指隙 15.25 mm")
    chk(abs(finger_gap(0.0805, 0.0660) - 0.00725) < 1e-9,
        "用**手掌宽** 66 当 can 粗 ⇒ 指隙 7.25 mm（这就是那个错算的来路）")
    chk(abs(finger_gap(0.0500, 0.0500)) < 1e-12, "全开=物径 ⇒ 指隙 0")
    chk(finger_gap(0.0400, 0.0500) < 0, "全开小于物径 ⇒ 负指隙（张不开到能套住）")

    # 矛盾判定
    c_ok = no_contradiction(0.0805, 0.0500, 0.008)
    chk(c_ok["contradiction"] is False, "指隙 15.25 > 容差 8 ⇒ 矛盾**不**成立")
    chk(abs(c_ok["gap_over_tol"] - 1.906) < 1e-3, f"比值应≈1.906，实得 {c_ok['gap_over_tol']}")
    chk(c_ok["finger_gap_mm"] == 15.25 and c_ok["xy_tol_mm"] == 8.0, "mm 换算")
    c_bad = no_contradiction(0.0805, 0.0660, 0.008)
    chk(c_bad["contradiction"] is True, "若 can 真是 66 mm ⇒ 指隙 7.25 < 8 ⇒ 矛盾成立（复现那个错论断）")
    c_edge = no_contradiction(0.0660, 0.0500, 0.008)
    chk(c_edge["contradiction"] is False, "指隙恰好=容差 ⇒ 不算矛盾（判据是严格小于）")
    c_zero = no_contradiction(0.0805, 0.0500, 0.0)
    chk(c_zero["gap_over_tol"] is None, "容差 0 ⇒ 比值 None，不除零")

    # 单位：全部走米，mm 只在展示层换算
    chk(abs(no_contradiction(80.5, 50.0, 8.0)["finger_gap_m"] - 15.25) < 1e-9,
        "输入若已是 mm，finger_gap_m 字段名就不该被当成米用 —— 这条钉子提醒调用方只喂米")

    print(f"档 6B 几何探针钉子：{n} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  FAIL:", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7000, help="测 reset 后几何时用的初态 seed（不影响 geom 尺寸）")
    ap.add_argument("--out", default="runs/s6_grasp_geom", help="产物目录（写 geometry.md + geometry.json）")
    ap.add_argument("--img-size", type=int, default=64)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    from mg_env_reverse import ReverseGraspEnv
    env = ReverseGraspEnv(img_size=args.img_size)
    try:
        m = measure(env, seed=args.seed)
    finally:
        env.close()

    chk = no_contradiction(m["gripper"]["width_fully_open"], m["can"]["diameter_m"], XY_TOL)
    m["derived"] = chk

    out = Path(args.out)
    out = out if out.is_absolute() else MG_ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    txt = build_report(m, chk)
    (out / "geometry.md").write_text(txt)
    (out / "geometry.json").write_text(json.dumps(m, indent=2, ensure_ascii=False))
    print(txt)
    print(f"[geom6b] 落盘 -> {out/'geometry.md'} 与 {out/'geometry.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
