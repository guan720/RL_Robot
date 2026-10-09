#!/usr/bin/env python
"""档 9B 判定：搬运期「末端高度保持」（零训练干预）能不能把「侧躺才算送到」这条放宽退回去。

门槛出处：`runs/S9_PREREG.md` §3.3（**2026-10-07 13:46 落盘，早于本档任何读数**）；
干预实现与限位值出处：**增补 1**（14:2x，v1 → 「末端高度保持」、cap 改示范分位数、条件标签 off/hold/hold_lo）
与 **增补 3**（15:1x，v1 在 Z0b 上 0/12 判死 → v2「终点预测式节流」、Z0b 前置闸、Z4 补受控量）。
终态出处：**增补 4**（15:3x，v2 在 Z0b 上仍 0/12 ⇒ 增补 3 ④ 的 2 次重设计预算用尽 ⇒ **9B 在设计阶段关闭、不发车**，
合法终态 = `runs/s9b.SKIPPED`；Z1–Z6 = **NOT_RUN**，本文件只作**档案**）。
本工具**只读数、不选点、不降门**：缺产物 ⇒ 该门 `UNKNOWN`（绝不当 0 计，坑 40③）；
出身不过 ⇒ 判定打 🚫、`S9B_TRUST=NO`、退出码 3、**本判定不采信**。

退出码：0 = 判定完成且可采信；3 = 出身核对不过（不采信）；4 = 主门读数不齐（UNKNOWN）。

机器可读行（链脚本 grep 这几行）：
    S9B_Z0b= / S9B_Z0= / S9B_Z1= / S9B_Z2= / S9B_Z3= / S9B_Z4= / S9B_TRUST= / S9B_DECISION=
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2f import wilson  # noqa: E402

RUNS = MG_ROOT / "runs"

# ── 门槛（逐字照抄 runs/S9_PREREG.md §3.3；改这里等于改门 ⇒ 必须先改预注册并留增补）──
Z1_MIN_REL_DROP = 0.50        # 侧躺局数相对下降 ≥ 50%
Z1_MAX_P = 0.05               # Fisher 单侧
Z2_MIN_NET_STRICT = 8         # 严格成功净增 ≥ +8 局 / 160
Z3_MAX_DROP_RELAXED = 6       # 放宽成功掉幅 ≤ 6 局 / 160
Z4_LIFT_TOL_CM = 0.5          # cap 组 p95 ≤ cap + 0.5 cm（受控量 + `max_lift_cm` 两条都要过，增补 3 ⑥）
Z0B_TOL_CM = 1.0              # Z0b 门线 = cap + 1.0 cm（增补 1 ④，**逐字冻结**、v1 判死后未放松）
Z0B_NEED = 11                 # Z0b 门 = ≥ 11/12 局按得住（增补 1 ④）
Z0B_N = 12                    # Z0b 样本 = 「侧躺 ∧ 升程最高」的 12 局（挑最坏 ⇒ 保守）
Z0B_REDESIGN_BUDGET = 2       # 增补 3 ④：Z0b 台最多 2 次控制律重设计（v1、v2 已用尽）

EPS = 20
REPS = 4
K_EVAL = 10
VAL_SEED0 = 8000
TEST_SEED0 = 7000
CK_SUFFIX = "checkpoints/022000/pretrained_model"
DEMO_NPZ = "data/mix60f120r_rev_raw.npz"     # 与 8C/8D 关门读逐项同口径（增补 3 ⑥）
# 限位值：示范搬运升程的分位数（增补 1 ③；出处 data/mix60f120r_rev_raw.npz，120 集，事前）
CAP_MAIN = 12.15              # 示范 p90 = 主限位
CAP_DOSE = 11.73              # 示范 p75 = 剂量副读（不是门）
MODE = "ceilpred"             # v2 终点预测式节流（增补 3 ③）；v1 ceilhold 已被 Z0b 判死
SAFETY = 1.4702               # = max(上升保真比 1.138, 1/制动保真比 0.680)，公式定、不调参
B_CARRY = (0.4093, 0.6105, 0.1768, 0.1015)   # 脉冲响应（code/mg_s9b_gain.py，76230 搬运步）
K_EFF = 1.9085                # = Σb × safety
Z0B_JSON = RUNS / "_diag/s9_tax/z0b_feasibility.json"        # 主闸（TEST 最坏 12 局）
Z0B_VAL_JSON = RUNS / "_diag/s9_tax/z0b_feasibility_val.json"  # 确认台 Z0b′（val，不是门）

# 臂 → (评测目录前缀里的臂名, 训练 run 名)
ARMS = {
    "8c_seed2000": "pi05_mix60f120r_c1_s8c_seed2000",
    "8d_seed4000": "pi05_mix60f120r_c1_s8d_seed4000",
}
ARM_TEST = dict(ARMS, **{"8d_seed5000": "pi05_mix60f120r_c1_s8d_seed5000"})   # Z5 登记用（3 臂）
COND_CAP = {"off": 0.0, "hold": CAP_MAIN, "hold_lo": CAP_DOSE}   # 条件标签（增补 1 ⑤）
Z0_DIR = "s9b_z0_fidelity"


def val_dirs(arm: str, cond: str) -> list[str]:
    return [f"s9b_{arm}_{cond}_val_rand20_k10{r}" for r in ("", "_rep2", "_rep3", "_rep4")[:REPS]]


def test_dirs(arm: str, cond: str) -> list[str]:
    return [f"s9b_{arm}_{cond}_test_rand20_k10{r}" for r in ("", "_rep2", "_rep3", "_rep4")[:REPS]]


def fisher_lower_tail(a: int, n1: int, b: int, n2: int) -> float:
    """单侧 Fisher：P(X ≤ a)，X = 组1（n1）里的「事件」数，边际总数 a+b 固定（超几何）。

    为什么自己写而不用 `mg_verdict_s2.fisher_two_sided`：那条是双侧，本档 Z1 有**方向**
    （侧躺应当变少）。实现与 `mg_verdict_s8.sign_test_one_sided` 同一套「按定义直接求和」的写法，
    不给判定工具添 scipy 依赖。n<=0 ⇒ 返回 1.0（缺读数绝不当 0 让它假过）。
    """
    if n1 <= 0 or n2 <= 0:
        return 1.0
    tot = a + b
    lo, hi = max(0, tot - n2), min(n1, tot)
    xs = list(range(lo, hi + 1))
    w = [math.comb(n1, x) * math.comb(n2, tot - x) for x in xs]
    den = sum(w)
    if den == 0:
        return 1.0
    return min(1.0, sum(w[i] / den for i, x in enumerate(xs) if x <= a))


def fisher_upper_tail(a: int, n1: int, b: int, n2: int) -> float:
    """单侧 Fisher：P(X ≥ a)（用于「严格成功应当变多」的方向）。"""
    if n1 <= 0 or n2 <= 0:
        return 1.0
    tot = a + b
    lo, hi = max(0, tot - n2), min(n1, tot)
    xs = list(range(lo, hi + 1))
    w = [math.comb(n1, x) * math.comb(n2, tot - x) for x in xs]
    den = sum(w)
    if den == 0:
        return 1.0
    return min(1.0, sum(w[i] / den for i, x in enumerate(xs) if x >= a))


def quantile_lower(v: list[float], q: float) -> float:
    if not v:
        return float("nan")
    v = sorted(v)
    return float(v[min(len(v) - 1, int(math.floor(q * len(v))))])


def pct(k: int, n: int) -> str:
    return "—" if n <= 0 else "%.1f%%" % (100.0 * k / n)


def cm(v: float) -> str:
    return "—" if v != v else f"{v:.2f} cm"


def read_cond(dirs: list[str], cond: str, seed0: int, arm: str) -> dict:
    """读一个条件（4 读 × 20 局）。出身不过 ⇒ problems 里记；缺产物 ⇒ missing 里记（不当 0）。"""
    out = {"strict": 0, "relaxed": 0, "tipped": 0, "n": 0, "lifts": [], "rises": [], "reads": [],
           "missing": [], "problems": [], "clamped": 0, "max_dz": 0.0, "sidecar_missing": [],
           "cap_seen": set(), "per_seed": {}, "n_grasped": 0, "n_ep_snap": 0}
    want_cap = COND_CAP[cond]
    for d in dirs:
        p = RUNS / d / "eval_summary.json"
        if not p.exists():
            out["missing"].append(d)
            continue
        j = json.loads(p.read_text())
        if j.get("task_mode") != "reverse":
            out["problems"].append(f"{d}: task_mode={j.get('task_mode')}")
        if int(j.get("seed", -1)) != seed0:
            out["problems"].append(f"{d}: seed={j.get('seed')} != {seed0}")
        if int(j.get("n_action_steps", -1)) != K_EVAL:
            out["problems"].append(f"{d}: K={j.get('n_action_steps')} != {K_EVAL}")
        if int(j.get("episodes", -1)) != EPS:
            out["problems"].append(f"{d}: episodes={j.get('episodes')} != {EPS}")
        if not str(j.get("policy_ckpt", "")).endswith(CK_SUFFIX):
            out["problems"].append(f"{d}: ckpt 尾串 != {CK_SUFFIX}")
        if f"runs/{ARM_TEST[arm]}" not in str(j.get("policy_ckpt", "")):
            out["problems"].append(f"{d}: ckpt 不是 {arm} 的训练 run（{j.get('policy_ckpt')}）")
        if not str(j.get("demo_npz", "")).endswith(DEMO_NPZ):
            out["problems"].append(f"{d}: demo_npz={j.get('demo_npz')} != {DEMO_NPZ}（与关门读不同口径）")
        sc_p = RUNS / d / "zlim_sidecar.json"
        if not sc_p.exists():
            out["sidecar_missing"].append(d)
        else:
            s = json.loads(sc_p.read_text())
            out["cap_seen"].add(float(s.get("cap_cm", float("nan"))))
            out["clamped"] += int(s.get("n_clamped_total", 0))
            out["max_dz"] = max(out["max_dz"], float(s.get("max_abs_dz_delta", 0.0)))
            out["n_grasped"] += int(s.get("n_grasped_ep", 0))
            if abs(float(s.get("cap_cm", -1)) - want_cap) > 1e-6:
                out["problems"].append(f"{d}: sidecar cap_cm={s.get('cap_cm')} != 条件 {cond}({want_cap})")
            if int(s.get("n_ep", -1)) != EPS:
                out["problems"].append(f"{d}: sidecar n_ep={s.get('n_ep')} != {EPS}")
            # ── v2 控制律的出身（增补 3 ③⑥）：mode / safety / b / k_eff 必须与预注册逐字一致 ──
            if s.get("mode") != MODE:
                out["problems"].append(f"{d}: sidecar mode={s.get('mode')} != {MODE}（v1/zlim 的读不许进本档门）")
            if want_cap > 0.0:
                if abs(float(s.get("safety", -1)) - SAFETY) > 1e-3:
                    out["problems"].append(f"{d}: sidecar safety={s.get('safety')} != {SAFETY}")
                if abs(float(s.get("k_eff", -1)) - K_EFF) > 1e-2:
                    out["problems"].append(f"{d}: sidecar k_eff={s.get('k_eff')} != {K_EFF}")
                bb = [float(x) for x in (s.get("b_carry") or [])]
                if len(bb) != len(B_CARRY) or max(abs(x - y) for x, y in zip(bb, B_CARRY)) > 1e-3:
                    out["problems"].append(f"{d}: sidecar b_carry={bb} != {list(B_CARRY)}")
            # 受控量本身（Z4 要用）：逐局「搬运期末端最大升程」，来自 reset 时定格的快照
            for e in s.get("ep", []):
                snap = e.get("filter") or {}
                if snap.get("t_grasp", -1) is not None and int(snap.get("t_grasp", -1)) >= 0:
                    out["n_ep_snap"] += 1
                    if snap.get("max_rise_cm") is not None:
                        out["rises"].append(float(snap["max_rise_cm"]))
        for f in ("n_success", "n_success_relaxed", "n_delivered_tipped"):
            if f not in j:
                out["problems"].append(f"{d}: 缺字段 {f}（坑 40③：不当 0）")
        out["strict"] += int(j.get("n_success", 0))
        out["relaxed"] += int(j.get("n_success_relaxed", 0))
        out["tipped"] += int(j.get("n_delivered_tipped", 0))
        out["n"] += int(j.get("episodes", 0))
        for e in j.get("per_episode", []):
            if "max_lift_cm" in e and e["max_lift_cm"] is not None:
                out["lifts"].append(float(e["max_lift_cm"]))
            sd = int(e.get("seed", -1))
            rec = out["per_seed"].setdefault(sd, {"strict": 0, "relaxed": 0, "tipped": 0, "n": 0})
            rec["n"] += 1
            rec["strict"] += int(bool(e.get("success")))
            rec["relaxed"] += int(bool(e.get("success_relaxed")))
            rec["tipped"] += int(bool(e.get("delivered_tipped")))
        out["reads"].append(d)
    if out["cap_seen"] and len(out["cap_seen"]) != 1:
        out["problems"].append(f"{cond}: 混进了不同 cap 的读 {sorted(out['cap_seen'])}")
    out["cap_seen"] = sorted(out["cap_seen"])
    return out


def blocked_sign_test(cap: dict, off: dict) -> dict:
    """按初态 seed 分块的符号检验（佐证，不是门）：每个 seed 上比「侧躺局数」，cap 少 = 胜。"""
    b = c = tie = 0
    for sd in sorted(set(cap["per_seed"]) & set(off["per_seed"])):
        dc = cap["per_seed"][sd]["tipped"] - off["per_seed"][sd]["tipped"]
        if dc < 0:
            b += 1
        elif dc > 0:
            c += 1
        else:
            tie += 1
    n = b + c
    # 单侧方向 = 「cap 侧躺更少的 seed 至少有 b 个」⇒ P(X ≥ b)，n=0 时返回 1.0（没有不一致不能说有差）
    p = 1.0 if n <= 0 else sum(math.comb(n, k) for k in range(b, n + 1)) / (2.0 ** n)
    return {"win": b, "lose": c, "tie": tie, "p_lower": p}


def gate(name: str, ok, detail: str) -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def z0b_read(path: Path, tag: str) -> dict:
    """读一台 Z0b 重放结果（纯 CPU，`code/mg_zlim_replay.py` 的产物）。

    除门槛本身，还核**出身**（mode/cap/safety/need/tol 与预注册逐字一致）：出身不过 ⇒ 该台按 FAIL 处理，
    免得有人换了控制律或放松了门线之后拿旧门当过（坑 40）。缺产物 ⇒ pass=None（UNKNOWN，不当 0/不当过）。
    """
    if not path.exists():
        return {"exists": False, "pass": None, "tag": tag, "problems": [f"缺产物 {path.name}"],
                "detail": f"缺产物 `runs/_diag/s9_tax/{path.name}` ⇒ UNKNOWN（坑 40③：不当过也不当 0）"}
    j = json.loads(path.read_text())
    g = j.get("gate", {}) or {}
    probs: list[str] = []
    if j.get("mode") != MODE:
        probs.append(f"mode={j.get('mode')} != {MODE}")
    if abs(float(j.get("cap_cm", -1)) - CAP_MAIN) > 1e-6:
        probs.append(f"cap_cm={j.get('cap_cm')} != {CAP_MAIN}")
    if abs(float(j.get("safety", -1)) - SAFETY) > 1e-3:
        probs.append(f"safety={j.get('safety')} != {SAFETY}")
    if int(g.get("need", -1)) != Z0B_NEED or int(g.get("n", -1)) != Z0B_N or abs(float(g.get("tol", -1)) - Z0B_TOL_CM) > 1e-9:
        probs.append(f"门槛被改过：need/n/tol={g.get('need')}/{g.get('n')}/{g.get('tol')} != {Z0B_NEED}/{Z0B_N}/{Z0B_TOL_CM}")
    on = [float(r.get("rise_cm", float("nan"))) for r in (j.get("on") or [])]
    off = [float(r.get("rise_cm", float("nan"))) for r in (j.get("off") or [])]
    on = [v for v in on if v == v]
    off = [v for v in off if v == v]
    held, need = int(g.get("held", -1)), int(g.get("need", -1))
    detail = (f"{tag}（`--sample {j.get('sample')}`，n={g.get('n')}）：加限位后升程 "
              f"{min(on):.2f}~{max(on):.2f} cm（不加限位 {min(off):.2f}~{max(off):.2f}），门线 = cap+{Z0B_TOL_CM:.1f} = "
              f"{CAP_MAIN + Z0B_TOL_CM:.2f} cm ⇒ 按住 **{held}/{g.get('n')}**（门 ≥ {need}/{Z0B_N}）"
              + ("；⚠️ " + "；".join(probs) if probs else ""))
    return {"exists": True, "pass": (bool(g.get("pass")) and not probs), "raw_pass": bool(g.get("pass")),
            "tag": tag, "held": held, "need": need, "n": int(g.get("n", -1)), "problems": probs,
            "on_min": min(on) if on else float("nan"), "on_max": max(on) if on else float("nan"),
            "off_min": min(off) if off else float("nan"), "off_max": max(off) if off else float("nan"),
            "fid": j.get("fid_max_dev"), "detail": detail}


def report() -> int:
    print("# 档 9B 判定（**档案**：设计阶段关闭）：运输高度限位（零训练干预）能不能把侧躺退回去")
    print()
    print(f"* 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}（`code/mg_verdict_s9b.py`）")
    print(f"* 门槛出处：`runs/S9_PREREG.md` §3.3（2026-10-07 13:46 落盘，**早于本档任何读数**）+ 增补 1/3（干预实现、Z0b 前置闸）+ **增补 4**（终态）")
    print(f"* 终态：**9B 在设计阶段关闭、从未上 GPU**（`runs/s9b.SKIPPED`）⇒ Z1–Z6 = **NOT_RUN**，本文件只是档案；"
          f"所有 UNKNOWN **不许当 0、也不许当过**（坑 40③）")
    print(f"* 主口径 = **放宽 R**；`delivered_tipped` = 放宽算成功、严格不算（侧躺送达）")
    print(f"* 窗口 = **val {VAL_SEED0}..{VAL_SEED0+EPS-1}**（门）；TEST {TEST_SEED0}.. 只作 Z5 登记")
    print()

    # ── Z0b 前置闸（增补 3 ④）：干预在纯 CPU 重放台上按不按住天花板；按不住 ⇒ 不许上 GPU ──
    zb_test = z0b_read(Z0B_JSON, "Z0b 主闸")
    zb_val = z0b_read(Z0B_VAL_JSON, "Z0b′ 确认台（不是门）")
    z0b = gate("Z0b", zb_test["pass"], zb_test["detail"])
    for pr in zb_test["problems"] + zb_val["problems"]:
        pass   # 出身问题已写进 detail；这里只汇总到 problems 供 TRUST 用（见下）

    problems: list[str] = []
    problems += [f"[Z0b] {p}" for p in zb_test["problems"]]
    problems += [f"[Z0b′] {p}" for p in zb_val["problems"]]
    data: dict[tuple[str, str], dict] = {}
    for arm in ARMS:
        for cond in ("off", "hold"):
            data[(arm, cond)] = read_cond(val_dirs(arm, cond), cond, VAL_SEED0, arm)
            for pr in data[(arm, cond)]["problems"]:
                problems.append(f"[{arm}/{cond}] {pr}")
    dose = read_cond(val_dirs("8d_seed4000", "hold_lo"), "hold_lo", VAL_SEED0, "8d_seed4000")
    for pr in dose["problems"]:
        problems.append(f"[8d_seed4000/hold_lo] {pr}")

    # Z0 保真：专用保真读 + 全部 off 条件的 sidecar
    #   ⚠️ 坑 40③：产物**根本不存在**（本档在设计阶段关闭、从未上 GPU，增补 4 ③）⇒ Z0 = **NOT_RUN/UNKNOWN**，
    #      不是 FAIL；只有「产物在、断言不过」才是 FAIL（外壳脏 ⇒ 全部读数作废）。
    z0_probs: list[str] = []
    fp = RUNS / Z0_DIR / "zlim_sidecar.json"
    off_n = sum(data[(a, "off")]["n"] for a in ARMS)
    z0_notrun = (not fp.exists()) and off_n == 0
    if not fp.exists():
        if not z0_notrun:
            z0_probs.append(f"缺保真读产物 {Z0_DIR}/zlim_sidecar.json（但 off 条件已有 {off_n} 局读数 ⇒ 保真没自证）")
    else:
        s = json.loads(fp.read_text())
        if float(s.get("cap_cm", -1)) != 0.0:
            z0_probs.append(f"{Z0_DIR}: cap_cm={s.get('cap_cm')} != 0（保真读必须关闭限位）")
        if int(s.get("n_clamped_total", -1)) != 0:
            z0_probs.append(f"{Z0_DIR}: n_clamped_total={s.get('n_clamped_total')} != 0")
        if float(s.get("max_abs_dz_delta", -1)) != 0.0:
            z0_probs.append(f"{Z0_DIR}: max_abs_dz_delta={s.get('max_abs_dz_delta')} != 0.0")
    off_clamped = sum(data[(a, "off")]["clamped"] for a in ARMS)
    off_dz = max([data[(a, "off")]["max_dz"] for a in ARMS] or [0.0])
    if off_clamped != 0:
        z0_probs.append(f"off 条件累计 n_clamped={off_clamped} != 0")
    if off_dz != 0.0:
        z0_probs.append(f"off 条件 max|Δdz|={off_dz} != 0.0")
    if z0_notrun:
        z0 = gate("Z0", None, "NOT_RUN：本档在设计阶段关闭、**从未上 GPU**（增补 4 ③）⇒ 保真门未测（UNKNOWN；坑 40③ 不当过也不当 FAIL）")
    else:
        z0 = gate("Z0", not z0_probs, "；".join(z0_probs) if z0_probs else
                  f"保真读 + 全部 off 条件：n_clamped=0 ∧ max|Δdz|=0.0 ⇒ 外壳从未改动任何一维动作")

    # 池化
    def pool(cond: str) -> dict:
        agg = {"strict": 0, "relaxed": 0, "tipped": 0, "n": 0, "lifts": [], "rises": [], "clamped": 0, "missing": 0}
        for arm in ARMS:
            d = data[(arm, cond)]
            for k in ("strict", "relaxed", "tipped", "n", "clamped"):
                agg[k] += d[k]
            agg["lifts"] += d["lifts"]
            agg["rises"] += d["rises"]
            agg["missing"] += len(d["missing"])
        return agg

    cap_, off_ = pool("hold"), pool("off")
    n_expected = len(ARMS) * REPS * EPS
    unknown = cap_["n"] < n_expected or off_["n"] < n_expected

    if not unknown and off_["tipped"] > 0:
        rel_drop = 1.0 - cap_["tipped"] / off_["tipped"]
        p1 = fisher_lower_tail(cap_["tipped"], cap_["n"], off_["tipped"], off_["n"])
        z1 = gate("Z1", rel_drop >= Z1_MIN_REL_DROP and p1 <= Z1_MAX_P,
                  f"侧躺 {off_['tipped']}→{cap_['tipped']}（相对降 {100*rel_drop:.1f}%，门 ≥{100*Z1_MIN_REL_DROP:.0f}%）"
                  f"∧ Fisher 单侧 p={p1:.2e}（门 ≤{Z1_MAX_P}）")
    elif not unknown:
        z1 = gate("Z1", cap_["tipped"] == 0, f"off 组侧躺 = 0 ⇒ 没有可降的空间（基线无效）；cap 组 = {cap_['tipped']}")
        p1 = float("nan"); rel_drop = float("nan")
    else:
        z1 = gate("Z1", None, f"读数不齐（cap {cap_['n']}/{n_expected}、off {off_['n']}/{n_expected}）⇒ UNKNOWN（坑 40③：不当 0）")
        p1 = float("nan"); rel_drop = float("nan")

    if not unknown:
        net = cap_["strict"] - off_["strict"]
        p2 = fisher_upper_tail(cap_["strict"], cap_["n"], off_["strict"], off_["n"])
        z2 = gate("Z2", net >= Z2_MIN_NET_STRICT,
                  f"严格成功 {off_['strict']}→{cap_['strict']}（净增 {net:+d} 局/{n_expected}，门 ≥ +{Z2_MIN_NET_STRICT}）"
                  f"；Fisher 单侧 p={p2:.4f}（佐证）")
        drop = off_["relaxed"] - cap_["relaxed"]
        z3 = gate("Z3", drop <= Z3_MAX_DROP_RELAXED,
                  f"放宽成功 {off_['relaxed']}→{cap_['relaxed']}（掉幅 {drop:+d} 局/{n_expected}，门 ≤ {Z3_MAX_DROP_RELAXED}）")
        p95 = quantile_lower(cap_["lifts"], 0.95)
        p95r = quantile_lower(cap_["rises"], 0.95)
        z4 = gate("Z4", (p95 == p95 and p95 <= CAP_MAIN + Z4_LIFT_TOL_CM
                         and p95r == p95r and p95r <= CAP_MAIN + Z4_LIFT_TOL_CM
                         and cap_["clamped"] > 0),
                  f"cap 组 max_lift p95={cm(p95)} ∧ **受控量** filter.max_rise p95={cm(p95r)}"
                  f"（两条都要 ≤ {CAP_MAIN + Z4_LIFT_TOL_CM:.2f} cm，增补 3 ⑥）∧ n_clamped={cap_['clamped']}（门 >0）")
    else:
        z2 = gate("Z2", None, "读数不齐 ⇒ UNKNOWN"); z3 = gate("Z3", None, "读数不齐 ⇒ UNKNOWN")
        z4 = gate("Z4", None, "读数不齐 ⇒ UNKNOWN"); net = None; drop = None
        p95 = float("nan"); p95r = float("nan")

    def mark(g: dict) -> str:
        return "UNKNOWN" if g["pass"] is None else ("PASS" if g["pass"] else "FAIL")

    print("## 一、判据（Z0b = 前置闸；Z0–Z4 = 门；本档**从未上 GPU** ⇒ 除 Z0b 外全 UNKNOWN）")
    print()
    print("| 判据 | 结果 | 读数 |")
    print("|:--|:--|:--|")
    for g in (z0b, z0, z1, z2, z3, z4):
        print(f"| **{g['name']}** | {mark(g)} | {g['detail']} |")
    print(f"| **Z0b′** 确认台（**不是门**） | {mark(gate('Z0b′', zb_val['pass'], zb_val['detail']))} | {zb_val['detail']} |")
    print()

    print("## 二、逐臂逐条件读数（val，每条件 4×20 = 80 局）")
    print()
    print("| 臂 | 条件 | 局数 | 严格（立着送达） | 放宽 | 侧躺 | max_lift p95 | 受控量 rise p95 | n_clamped |")
    print("|:--|:--|---:|---:|---:|---:|---:|---:|---:|")
    for arm in ARMS:
        for cond in ("off", "hold"):
            d = data[(arm, cond)]
            print(f"| {arm} | {cond} | {d['n']} | {d['strict']} = {pct(d['strict'], d['n'])} "
                  f"| {d['relaxed']} = {pct(d['relaxed'], d['n'])} | {d['tipped']} = {pct(d['tipped'], d['n'])} "
                  f"| {cm(quantile_lower(d['lifts'], 0.95))} | {cm(quantile_lower(d['rises'], 0.95))} | {d['clamped']} |")
    print(f"| 8d_seed4000 | hold_lo（Z6 剂量副读，cap={CAP_DOSE}） | {dose['n']} | {dose['strict']} = {pct(dose['strict'], dose['n'])} "
          f"| {dose['relaxed']} = {pct(dose['relaxed'], dose['n'])} | {dose['tipped']} = {pct(dose['tipped'], dose['n'])} "
          f"| {cm(quantile_lower(dose['lifts'], 0.95))} | {cm(quantile_lower(dose['rises'], 0.95))} | {dose['clamped']} |")
    print()
    if unknown:
        print("* ⚠️ 上表局数为 0 = **缺产物**（本档从未上 GPU），不是「跑了 0 局成功」⇒ 一律 UNKNOWN（坑 40③）。")
        print()
    if not unknown:
        def pooled_seeds(cond: str) -> dict:
            agg: dict = {}
            for a in ARMS:
                for sd, rec in data[(a, cond)]["per_seed"].items():
                    agg.setdefault(sd, {"tipped": 0})["tipped"] += rec["tipped"]
            return {"per_seed": agg}

        bs = blocked_sign_test(pooled_seeds("hold"), pooled_seeds("off"))
        print(f"* 按初态 seed 分块的符号检验（**佐证、不是门**）：cap 侧躺更少的 seed {bs['win']} 个 / 更多 {bs['lose']} 个 / "
              f"持平 {bs['tie']} 个，单侧 p = {bs['p_lower']:.4f}")
        print()

    # Z5：TEST 登记（只有三门全过才有产物；没有就写「未跑」）
    print("## 三、Z5 · TEST 部署数字登记（**不是门**）")
    print()
    z5_rows = []
    for arm in ARM_TEST:
        d = read_cond(test_dirs(arm, "hold"), "hold", TEST_SEED0, arm)
        for pr in d["problems"]:
            problems.append(f"[Z5 {arm}] {pr}")
        z5_rows.append((arm, d))
    if all(d["n"] == 0 for _a, d in z5_rows):
        print("* 未跑（Z1∧Z2∧Z3 未全过 ⇒ 按预注册 §3.4 不烧卡；或链还没到这一段）。")
    else:
        print("| 臂 | 局数 | 严格 | 放宽 | 侧躺 | 出处 |")
        print("|:--|---:|---:|---:|---:|:--|")
        for arm, d in z5_rows:
            if d["n"] == 0:
                continue
            print(f"| {arm} +hold{CAP_MAIN} | {d['n']} | {d['strict']} = {pct(d['strict'], d['n'])} "
                  f"| {d['relaxed']} = {pct(d['relaxed'], d['n'])} | {d['tipped']} = {pct(d['tipped'], d['n'])} "
                  f"| {', '.join(d['reads'][:1])}… |")
        print()
        print("* ⚠️ 带限位的读数一律标 `+hold<cap>`，**不许**与不带限位的历史读数混列比高低（预注册 §4 诚实标注 3）。")
    print()

    trust = not problems and z0["pass"] is True and z0b["pass"] is True
    print("## 四、出身核对与不变量")
    print()
    if problems:
        for pr in problems:
            print(f"* 🚫 {pr}")
    else:
        print("* ✅ 已有产物的出身断言通过（Z0b 台的 mode/cap/safety/need/n/tol 与预注册逐字一致）")
    print(f"* Z0b 台出身：TEST {zb_test['problems'] or '✅ 全对'}；val {zb_val['problems'] or '✅ 全对'}")
    print("* `S9B_TRUST=NO` 的含义 = **本档没有可采信的 GPU 读数**（Z0 保真门未测、Z1–Z6 NOT_RUN）；"
          "**不是**「关闭结论不可信」——关闭结论的证据是零 GPU 的 Z0b 台，它的出身断言全对、重放台自证 5.95e-08（见上一行）。")
    print(f"* 重放台自证（不加限位 vs npz 的 `state[:,2]`）：TEST max|Δ| = {zb_test.get('fid', float('nan')):.2e}（容差 1e-05）")
    print()

    if z0b["pass"] is not True:
        dec = ("Z0b ❌ ⇒ **干预在设计阶段就被判死**：v1(ceilhold) 0/12、v2(ceilpred) 0/12（加限位后 "
               f"{zb_test['on_min']:.2f}~{zb_test['on_max']:.2f} cm，门线 {CAP_MAIN + Z0B_TOL_CM:.2f} cm）⇒ "
               f"增补 3 ④ 的 {Z0B_REDESIGN_BUDGET} 次重设计预算**用尽** ⇒ **9B 关闭、不发车**（终态 runs/s9b.SKIPPED），"
               "Z1–Z6 = NOT_RUN；根因 = 侧躺局的升程是**接触/动量弹射**（限位器饱和刹车时末端仍在涨）⇒ dz 级外壳按不住；"
               "9C（配方收口）无条件接续（增补 2/4）")
    elif z0["pass"] is False:
        dec = "Z0 ❌ ⇒ 外壳不干净 ⇒ **9B 全部读数作废**、停下等人（预注册 §3.4）"
    elif unknown:
        dec = "读数不齐 ⇒ UNKNOWN（不许当 0 计）"
    elif z1["pass"] and z2["pass"] and z3["pass"]:
        dec = "Z1∧Z2∧Z3 ✅ ⇒ 限位成立 ⇒ 跑 Z5（TEST 登记）⇒ 9C 主线 = 把限位器写进部署口径；下一靶 = B 类搬运失手"
    elif z1["pass"] and not z3["pass"]:
        dec = "Z1 ✅ ∧ Z3 ❌ ⇒ 抬了严格、掉了放宽 ⇒ 标「**不可作为部署配方**」，只登记（处方见预注册 §3.4）"
    elif z1["pass"] and not z2["pass"]:
        dec = "Z1 ✅ ∧ Z2 ❌ ⇒ 机理部分成立（侧躺降了但严格没涨）⇒ 按 Z1 ❌ 走分支乙，判定里标「机理部分成立」"
    else:
        dec = "Z1 ❌ ⇒ 举高是代理变量不是因 ⇒ 9C 转分支乙（配方收口 2×2：bs32/5500 + 纠正，3 seed）"
    print("## 五、决策（预注册 §3.4 的决策树 + 增补 3 ④ 的 Z0b 前置闸）")
    print()
    print(f"* {dec}")
    print("* 沉淀（写进 `runs/MISSION_VERDICT.md` 的已知极限 + README 坑 81）：「运输高度限位」这条**部署侧动作过滤**路线关闭；"
          "治侧躺只剩改教材几何 / 改释放时机 / 接受侧躺（现行放宽判据已把侧躺送达算成功并打 `delivered_tipped` 标）。")
    print()
    print("## 六、机器可读行（链脚本 grep 这几行）")
    print()
    print("```")
    print(f"S9B_STAGE={'DESIGN_CLOSED' if z0b['pass'] is not True else 'GPU_RUN'}")
    print(f"S9B_Z0b={mark(z0b)} held={zb_test.get('held', 'NA')}/{zb_test.get('n', 'NA')} "
          f"on_min={zb_test.get('on_min', float('nan')):.2f} on_max={zb_test.get('on_max', float('nan')):.2f} "
          f"line={CAP_MAIN + Z0B_TOL_CM:.2f}")
    print(f"S9B_Z0b_val={mark(gate('Z0b′', zb_val['pass'], zb_val['detail']))} held={zb_val.get('held', 'NA')}/{zb_val.get('n', 'NA')}")
    print(f"S9B_Z0={mark(z0)}")
    rd = "NA" if rel_drop != rel_drop else f"{rel_drop:.4f}"
    pv = "NA" if p1 != p1 else f"{p1:.6g}"
    print(f"S9B_Z1={mark(z1)} rel_drop={rd} p={pv}")
    print(f"S9B_Z2={mark(z2)} net={net if net is not None else 'NA'}")
    print(f"S9B_Z3={mark(z3)} drop={drop if drop is not None else 'NA'}")
    print(f"S9B_Z4={mark(z4)}")
    print(f"S9B_TRUST={'YES' if trust else 'NO'}")
    print(f"S9B_DECISION={dec.split('⇒')[0].strip()}")
    print("```")
    print()
    print("## 七、复现（本档**不发车**：终态 = `runs/s9b.SKIPPED`；下面是已跑过的零 GPU 台）")
    print()
    print("```bash")
    print("source code/env.sh")
    print("$MG_PY code/mg_eval_zlim.py --selftest       # 限位外壳钉子（含 v2 CarryPredict）")
    print("$MG_PY code/mg_zlim_replay.py --selftest     # 重放台钉子")
    print("$MG_PY code/mg_s9b_gain.py --selftest        # dz→升程 脉冲响应（k/safety 的出处）")
    print("$MG_PY code/mg_verdict_s9b.py --selftest     # 判定钉子")
    print("# Z0b 主闸（v1 判死 + v2 判死，纯 CPU）：")
    print(f"$MG_PY code/mg_zlim_replay.py --sample test --mode ceilhold  --cap-cm {CAP_MAIN} --kp 0.5")
    print(f"$MG_PY code/mg_zlim_replay.py --sample test --mode ceilpred  --cap-cm {CAP_MAIN}")
    print(f"$MG_PY code/mg_zlim_replay.py --sample val  --mode ceilpred  --cap-cm {CAP_MAIN}")
    print("$MG_PY code/mg_verdict_s9b.py > runs/S9B_VERDICT.md")
    print("# code/chain_s9b.sh 写的是旧 zlim/旧 cap 口径 ⇒ **不修、不发车**（增补 4 ③），留档。")
    print("```")
    if problems:
        return 3
    return 4 if unknown else 0


def selftest() -> int:
    fails: list[str] = []
    total = [0]
    import tempfile
    global RUNS

    def ck(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    # fisher_lower_tail：用超几何定义**独立**算参考值（坑 65）
    def ref_lower(a, n1, b, n2):
        tot = a + b
        xs = [x for x in range(max(0, tot - n2), min(n1, tot) + 1)]
        w = {x: math.comb(n1, x) * math.comb(n2, tot - x) for x in xs}
        den = sum(w.values())
        return sum(w[x] for x in xs if x <= a) / den

    ck("f1 下尾与独立参考值一致（24/160 vs 48/160）",
       abs(fisher_lower_tail(24, 160, 48, 160) - ref_lower(24, 160, 48, 160)) < 1e-12)
    ck("f2 侧躺 48→24（减半）⇒ p < 1e-3（-3.2σ 量级）", fisher_lower_tail(24, 160, 48, 160) < 1e-3)
    ck("f2b 减半的 p 与正态近似同量级", 1e-4 < fisher_lower_tail(24, 160, 48, 160) < 5e-3)
    ck("f3 一点没降 ⇒ p≈1", fisher_lower_tail(48, 160, 48, 160) > 0.5)
    ck("f4 a=0 ⇒ p = P(X=0) > 0", 0 < fisher_lower_tail(0, 160, 48, 160) < 0.05)
    ck("f5 n=0 ⇒ 返回 1.0（缺读数不假过）", fisher_lower_tail(0, 0, 5, 10) == 1.0)
    ck("f6 上尾与下尾互补（**边际总数必须相同**：a+b=140 ⇒ 下尾取 a=79,b=61）",
       abs(fisher_upper_tail(80, 160, 60, 160) + fisher_lower_tail(79, 160, 61, 160) - 1.0) < 1e-9)
    ck("f6b 边际总数写错就会露馅（这条是防呆钉子，不是恒等式）",
       fisher_upper_tail(80, 160, 60, 160) + fisher_lower_tail(79, 160, 60, 160) > 1.0)
    ck("f7 上尾：净增很大 ⇒ p 小", fisher_upper_tail(80, 160, 60, 160) < 0.05)
    ck("f8 上尾：一点没增 ⇒ p≈1", fisher_upper_tail(60, 160, 60, 160) > 0.5)

    ck("q1 下分位 p95(n=20)=第20小", quantile_lower([float(i) for i in range(1, 21)], 0.95) == 20.0)
    ck("q2 空列表 → nan", math.isnan(quantile_lower([], 0.5)))
    ck("q3 乱序输入自动排序", quantile_lower([3.0, 1.0, 2.0], 0.5) == 2.0)

    # 门槛常数必须与预注册逐字一致（防止有人偷偷改门）
    ck("g1 Z1 相对降门 = 50%", Z1_MIN_REL_DROP == 0.50)
    ck("g2 Z1 p 门 = 0.05", Z1_MAX_P == 0.05)
    ck("g3 Z2 净增门 = +8 局", Z2_MIN_NET_STRICT == 8)
    ck("g4 Z3 掉幅门 = 6 局", Z3_MAX_DROP_RELAXED == 6)
    ck("g5 Z4 容差 = 0.5 cm", Z4_LIFT_TOL_CM == 0.5)
    ck("g6 cap 主值 = 示范搬运升程 p90 = 12.15（增补 1 ③）", CAP_MAIN == 12.15)
    ck("g7 cap 副值 = 示范 p75 = 11.73（增补 1 ③）", CAP_DOSE == 11.73)
    ck("g8 使命窗口 = val 8000 / TEST 7000", VAL_SEED0 == 8000 and TEST_SEED0 == 7000)
    ck("g9 每条件 4×20 = 80 局/臂", REPS * EPS == 80)
    ck("g10 条件标签 = off/hold/hold_lo（增补 1 ⑤），cap 逐一对得上",
       COND_CAP == {"off": 0.0, "hold": CAP_MAIN, "hold_lo": CAP_DOSE})
    ck("g11 v2 控制律常数自洽：k=Σb、k_eff=k×safety、safety>1（公式定、不调参）",
       abs(sum(B_CARRY) - 1.2981) < 5e-4 and abs(K_EFF - sum(B_CARRY) * SAFETY) < 1e-3 and SAFETY > 1.0)
    ck("g12 Z0b 门槛逐字冻结：≥11/12 局 ≤ cap+1.0 cm（v1 判死后**没有**放松）",
       (Z0B_NEED, Z0B_N, Z0B_TOL_CM) == (11, 12, 1.0) and Z0B_REDESIGN_BUDGET == 2)
    ck("g13 demo_npz 口径 = 反向 raw npz（与 8C/8D 关门读逐项同）", DEMO_NPZ == "data/mix60f120r_rev_raw.npz")

    # z0b_read：门 + 出身（mode/cap/safety/need/n/tol）；缺产物 ⇒ UNKNOWN，不当 0/不当过
    def mk_z0b(p: Path, held: int, mode: str = MODE, cap: float = CAP_MAIN, need: int = Z0B_NEED,
               tol: float = Z0B_TOL_CM, raw: bool | None = None) -> dict:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "sample": "test", "mode": mode, "cap_cm": cap, "safety": SAFETY, "k_eff": K_EFF,
            "gate": {"n": Z0B_N, "held": held, "need": need, "tol": tol,
                     "pass": (held >= need) if raw is None else raw},
            "fid_max_dev": 5.9e-08,
            "on": [{"rise_cm": cap + 0.5} for _ in range(Z0B_N)],
            "off": [{"rise_cm": cap + 6.0} for _ in range(Z0B_N)]}))
        return json.loads(p.read_text())

    with tempfile.TemporaryDirectory() as td2:
        zp = Path(td2) / "_diag/s9_tax/z0b_x.json"
        mk_z0b(zp, 12)
        r = z0b_read(zp, "T")
        ck("z1 按住 12/12 且出身全对 ⇒ PASS", r["pass"] is True and not r["problems"])
        mk_z0b(zp, 0)
        r = z0b_read(zp, "T")
        ck("z2 按住 0/12 ⇒ FAIL（本档实测形状）", r["pass"] is False and r["held"] == 0)
        mk_z0b(zp, 12, mode="ceilhold")
        r = z0b_read(zp, "T")
        ck("z3 v1 的产物混进 v2 的门 ⇒ 记出身问题且判 FAIL（不许拿旧控制律当过）",
           r["pass"] is False and any("mode" in p for p in r["problems"]))
        mk_z0b(zp, 12, cap=12.87)
        ck("z4 cap 被改过 ⇒ 记出身问题", any("cap_cm" in p for p in z0b_read(zp, "T")["problems"]))
        mk_z0b(zp, 8, need=8)
        ck("z5 门槛被放松（need 11→8）⇒ 记出身问题、不采信",
           any("门槛被改过" in p for p in z0b_read(zp, "T")["problems"]))
        mk_z0b(zp, 12, raw=False)
        ck("z6 json 自己的 gate.pass=false ⇒ 照它判（不重算门）", z0b_read(zp, "T")["pass"] is False)
        ck("z7 缺产物 ⇒ pass=None（UNKNOWN，不当 0/不当过，坑 40③）",
           z0b_read(Path(td2) / "不存在.json", "T")["pass"] is None)

    # read_cond：缺产物必须单列，不当 0（坑 40③）
    saved = RUNS
    with tempfile.TemporaryDirectory() as td:
        RUNS = Path(td)
        d = read_cond(["nope_a", "nope_b"], "off", VAL_SEED0, "8d_seed4000")
        ck("r1 缺产物单列、n 保持 0 而不是假数", d["n"] == 0 and len(d["missing"]) == 2)
        # 假一读：出身错必须被记
        dd = RUNS / "s9b_8d_seed4000_off_val_rand20_k10"
        dd.mkdir(parents=True)
        (dd / "eval_summary.json").write_text(json.dumps({
            "task_mode": "forward", "seed": VAL_SEED0, "n_action_steps": K_EVAL, "episodes": EPS,
            "policy_ckpt": f"/x/runs/{ARM_TEST['8d_seed4000']}/checkpoints/022000/pretrained_model",
            "n_success": 10, "n_success_relaxed": 13, "n_delivered_tipped": 3,
            "per_episode": [{"seed": VAL_SEED0 + i, "success": True, "success_relaxed": True,
                             "delivered_tipped": False, "max_lift_cm": 11.0} for i in range(EPS)]}))
        d2 = read_cond(["s9b_8d_seed4000_off_val_rand20_k10"], "off", VAL_SEED0, "8d_seed4000")
        ck("r2 task_mode 错 ⇒ 记 problem（不静默通过）", any("task_mode" in p for p in d2["problems"]))
        ck("r3 缺 sidecar ⇒ 单列", len(d2["sidecar_missing"]) == 1)
        ck("r4 严格/放宽/侧躺照常入账", (d2["strict"], d2["relaxed"], d2["tipped"], d2["n"]) == (10, 13, 3, 20))
        # sidecar cap 不匹配条件 ⇒ 记 problem
        (dd / "zlim_sidecar.json").write_text(json.dumps({"cap_cm": 12.87, "n_clamped_total": 3,
                                                          "max_abs_dz_delta": 0.4, "n_ep": EPS}))
        d3 = read_cond(["s9b_8d_seed4000_off_val_rand20_k10"], "off", VAL_SEED0, "8d_seed4000")
        ck("r5 off 条件里混进 cap=12.87 的 sidecar ⇒ 记 problem",
           any("cap_cm" in p for p in d3["problems"]))
        # v2 出身 + 受控量（增补 3 ⑥）：hold 条件的 sidecar 必须带 mode/safety/k_eff/b_carry 与逐局 max_rise_cm
        dh = RUNS / "s9b_8d_seed4000_hold_val_rand20_k10"
        dh.mkdir(parents=True)
        (dh / "eval_summary.json").write_text(json.dumps({
            "task_mode": "reverse", "seed": VAL_SEED0, "n_action_steps": K_EVAL, "episodes": EPS,
            "policy_ckpt": f"/x/runs/{ARM_TEST['8d_seed4000']}/{CK_SUFFIX}", "demo_npz": f"/x/{DEMO_NPZ}",
            "n_success": 10, "n_success_relaxed": 13, "n_delivered_tipped": 3,
            "per_episode": [{"seed": VAL_SEED0 + i, "success": True, "success_relaxed": True,
                             "delivered_tipped": False, "max_lift_cm": 11.0} for i in range(EPS)]}))
        (dh / "zlim_sidecar.json").write_text(json.dumps({
            "cap_cm": CAP_MAIN, "n_clamped_total": 7, "max_abs_dz_delta": 0.9, "n_ep": EPS,
            "mode": MODE, "safety": SAFETY, "k_eff": K_EFF, "b_carry": list(B_CARRY), "n_grasped_ep": EPS,
            "ep": [{"filter": {"t_grasp": 100, "max_rise_cm": 11.5 + i * 0.01}} for i in range(EPS)]}))
        d4 = read_cond(["s9b_8d_seed4000_hold_val_rand20_k10"], "hold", VAL_SEED0, "8d_seed4000")
        ck("r6 v2 出身全对 ⇒ 无 problem", d4["problems"] == [])
        ck("r7 逐局受控量 filter.max_rise_cm 被收上来（Z4 的第二条门要用）", len(d4["rises"]) == EPS)
        sck = json.loads((dh / "zlim_sidecar.json").read_text()); sck["mode"] = "ceilhold"
        (dh / "zlim_sidecar.json").write_text(json.dumps(sck))
        ck("r8 sidecar mode=v1 ⇒ 记 problem（v1 的读不许进 v2 的门）",
           any("mode" in p for p in read_cond(["s9b_8d_seed4000_hold_val_rand20_k10"], "hold",
                                              VAL_SEED0, "8d_seed4000")["problems"]))
        sck["mode"] = MODE; sck["safety"] = 1.0
        (dh / "zlim_sidecar.json").write_text(json.dumps(sck))
        ck("r9 safety 与预注册不符（公式定的常数被改）⇒ 记 problem",
           any("safety" in p for p in read_cond(["s9b_8d_seed4000_hold_val_rand20_k10"], "hold",
                                                VAL_SEED0, "8d_seed4000")["problems"]))
    RUNS = saved

    ck("b1 符号检验：全胜 ⇒ p = 0.5^n", abs(blocked_sign_test(
        {"per_seed": {i: {"tipped": 0} for i in range(5)}},
        {"per_seed": {i: {"tipped": 2} for i in range(5)}})["p_lower"] - 0.5 ** 5) < 1e-12)
    ck("b2 符号检验：全负 ⇒ p = 1", blocked_sign_test(
        {"per_seed": {i: {"tipped": 3} for i in range(4)}},
        {"per_seed": {i: {"tipped": 1} for i in range(4)}})["p_lower"] == 1.0)
    ck("b3 符号检验：全持平 ⇒ p = 1（没有不一致不能说有差）", blocked_sign_test(
        {"per_seed": {i: {"tipped": 2} for i in range(4)}},
        {"per_seed": {i: {"tipped": 2} for i in range(4)}})["p_lower"] == 1.0)

    print(f"档 9B 判定钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  🚫", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
