#!/usr/bin/env python
"""档 4x · K≥25 塌陷的机理对照（正向同任务、同 seed 窗口，唯一变量 = 模型）判定汇编。

预注册全文见 `runs/S4X_PREREG.md`（**写死时间 2026-10-02 11:58，在跑之前**）。
本脚本只做三件事，全部可审计：
  1. **逐读核出身**：`task_mode == forward`、`seed == 2000`、`seed_mode == random`、
     `n_action_steps == 声称的 K`、`policy_ckpt` 的格号 == 该臂声称的检查点（记 `last` 就现场
     `readlink` 核对，复用 `mg_select_ckpt.classify`，与坑 42 的修复同一套语义）。
     对不上 ⇒ **该读作废并逐条报出**，绝不静默使用。
  2. 把两臂 × 三个 K 的成功率与 **A/B/C 分类**（尺子 = `mg_tax_fail.klass`）并到一张表上；
  3. 按预注册规则判 **H1 / H0 / 部分支持**，并报功效与「本档不改工作点」。

历史读数**原样并入、不重跑、不追改**（坑 40①）：臂 A 的 K=10/25/50 与臂 B 的 K=10 都是
本档之前落盘的产物；本档只新跑 4 读。

用法：
    $MG_PY code/mg_verdict_s4x.py            # -> 打到 stdout（链里重定向到 runs/S4X_VERDICT.md）
    $MG_PY code/mg_verdict_s4x.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_select_ckpt import classify, last_target          # noqa: E402
from mg_tax_fail import LIFT_OK_CM, NEAR_CM, klass        # noqa: E402
from mg_verdict_s2 import fisher_two_sided                # noqa: E402
from mg_verdict_s2f import ci, pct                        # noqa: E402

RUNS = HERE.parent / "runs"

SEED_BASE = 2000            # 预注册：TEST seed 窗口 2000..2019
# 预注册判定阈值（H1 / H0），跑前写死
H1_A_RATE_MAX = 0.25        # A 率(B@K50) ≤ 25%
H1_SUCC_MIN = 0.45          # 成功率(B@K50) ≥ 45%
H0_A_RATE_MIN = 0.40        # A 率(B@K50) ≥ 40%
H0_SUCC_MAX = 0.35          # 成功率(B@K50) ≤ 35%
GATE_K = 50                 # 判定只看 K=50 那一格（悬崖最深）

ARMS = {
    "A": {
        "label": "臂A 档1 007200（rand60：60 条正向 / 7200 步）",
        "run": "pi05_rand60_s1", "step": 7200,
        "reads": {
            10: [("s1_gate_test_rand20_k10", "历史")],
            25: [("s1_k25_test_rand20", "历史")],
            50: [("s1_gate_test_rand20", "历史"), ("s4x_fwdA007200_k50_rep2", "本档新跑")],
        },
    },
    "B": {
        "label": "臂B 档2e 022000（mix60f120r：同样那 60 条正向 + 120 条反向 / 22000 步）",
        "run": "pi05_mix60f120r_s2e", "step": 22000,
        "reads": {
            10: [("s2e_fwd_test_rand20_k10", "历史"), ("s2e_fwd_test_rand20_k10_rep2", "历史")],
            25: [("s4x_fwdB022000_k25", "本档新跑")],
            50: [("s4x_fwdB022000_k50", "本档新跑"), ("s4x_fwdB022000_k50_rep2", "本档新跑")],
        },
    },
}


def check_provenance(j: dict, arm: dict, k: int, dname: str) -> list[str]:
    """逐条核对一读的出身。返回**违规列表**（空 = 干净）。"""
    bad: list[str] = []
    if j.get("task_mode") != "forward":
        bad.append("task_mode=%r ≠ forward" % j.get("task_mode"))
    if int(j.get("seed", -1)) != SEED_BASE:
        bad.append("seed=%r ≠ %d" % (j.get("seed"), SEED_BASE))
    if j.get("seed_mode") != "random":
        bad.append("seed_mode=%r ≠ random" % j.get("seed_mode"))
    if int(j.get("n_action_steps", -1)) != k:
        bad.append("n_action_steps=%r ≠ %d" % (j.get("n_action_steps"), k))
    status, why = classify(j.get("policy_ckpt"), arm["step"], last_target(RUNS / arm["run"]))
    if status != "ok":
        bad.append("出身核对 %s：%s" % (status, why))
    # 正向判据没有倾角项 ⇒ 两口径必然相等（档 2f 阶段 B 冒烟已验）。不等 = 判据写坏了。
    if "success_relaxed" in j:
        for e in j.get("per_episode", []):
            if "success_relaxed" in e and bool(e["success_relaxed"]) != bool(e["success"]):
                bad.append("正向两口径不一致（seed %s）⇒ 判据不变量破了" % e.get("seed"))
                break
    return bad


def collect(arm: dict, k: int):
    """把一臂一个 K 的所有合格读并起来。返回 dict（含逐读明细与作废清单）。"""
    eps: list[dict] = []
    reads, rejected, missing = [], [], []
    for dname, origin in arm["reads"].get(k, []):
        f = RUNS / dname / "eval_summary.json"
        if not f.is_file():
            missing.append("%s（%s）" % (dname, origin))
            continue
        try:
            j = json.loads(f.read_text())
        except Exception as exc:                                   # noqa: BLE001
            rejected.append((dname, "解析失败：%r" % exc))
            continue
        bad = check_provenance(j, arm, k, dname)
        if bad:
            rejected.append((dname, "；".join(bad)))
            continue
        pe = j.get("per_episode", [])
        reads.append({"dir": dname, "origin": origin, "n": len(pe),
                      "n_success": sum(1 for e in pe if e.get("success")),
                      "policy_ckpt": j.get("policy_ckpt")})
        for e in pe:
            e = dict(e)
            e["src"] = dname
            if "min_dist_to_target_xy" in e:
                e["min_dist_cm"] = float(e["min_dist_to_target_xy"]) * 100.0
            elif "min_dist_to_target_cm" in e:
                e["min_dist_cm"] = float(e["min_dist_to_target_cm"])
            else:
                e["min_dist_cm"] = float("nan")
            e["lift_cm"] = float(e.get("max_lift_cm", float("nan")))
            eps.append(e)
    n = len(eps)
    nA = sum(1 for e in eps if klass(e, "strict") == "A")
    nB = sum(1 for e in eps if klass(e, "strict") == "B")
    nC = sum(1 for e in eps if klass(e, "strict") == "C")
    nOK = sum(1 for e in eps if klass(e, "strict") == "OK")
    return {"n": n, "ok": nOK, "A": nA, "B": nB, "C": nC,
            "a_rate": (nA / n) if n else float("nan"),
            "succ": (nOK / n) if n else float("nan"),
            "reads": reads, "rejected": rejected, "missing": missing}


def verdict_string(cellB: dict, cellA: dict) -> tuple[str, list[str]]:
    """按预注册规则判 H1 / H0 / 部分支持。返回 (标签, 依据行列表)。"""
    reasons = []
    if not cellB["n"]:
        return "悬空", ["臂 B 在 K=%d 没有合格读数 ⇒ 本档判不了" % GATE_K]
    ar, su = cellB["a_rate"], cellB["succ"]
    reasons.append("A 率(B@K%d) = %d/%d = %.1f%%（H1 阈 ≤%.0f%%，H0 阈 ≥%.0f%%）"
                   % (GATE_K, cellB["A"], cellB["n"], 100 * ar, 100 * H1_A_RATE_MAX, 100 * H0_A_RATE_MIN))
    reasons.append("成功率(B@K%d) = %d/%d = %.1f%%（H1 阈 ≥%.0f%%，H0 阈 ≤%.0f%%）"
                   % (GATE_K, cellB["ok"], cellB["n"], 100 * su, 100 * H1_SUCC_MIN, 100 * H0_SUCC_MAX))
    if cellA["n"]:
        reasons.append("对照 A 率(A@K%d) = %d/%d = %.1f%%，成功率 = %d/%d = %.1f%%"
                       % (GATE_K, cellA["A"], cellA["n"], 100 * cellA["a_rate"],
                          cellA["ok"], cellA["n"], 100 * cellA["succ"]))
    h1 = (ar <= H1_A_RATE_MAX) and (su >= H1_SUCC_MIN)
    h0 = (su <= H0_SUCC_MAX) and (ar >= H0_A_RATE_MIN)
    if h1 and not h0:
        return "H1 机理成立", reasons
    if h0 and not h1:
        return "H0 塌陷是内禀的", reasons
    if h1 and h0:
        return "规则自相矛盾（阈值写重了）", reasons
    return "部分支持（落在预注册的中间地带）", reasons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    print("# 档 4x 判定：K≥25 塌陷的机理对照（正向同任务、同 seed 窗口，唯一变量 = 模型）")
    print("# 产物根目录：%s" % RUNS)
    print("# 预注册全文：runs/S4X_PREREG.md（写死时间 2026-10-02 11:58，**在跑之前**）")
    print()
    print("* 任务 = **forward**；TEST seed = **%d..%d**（`--seed-mode random`）；初态由 `env.reset(seed)` 钉死，" % (SEED_BASE, SEED_BASE + 19))
    print("  与 `--demo-npz` 无关（`mg_eval.py:267-275` 只用它做动作分布对照）⇒ 两臂**逐 seed 初态相同**。")
    print("* 分类尺子 = `code/mg_tax_fail.py`：A `max_lift < %.1f cm`、B `≥%.1f ∧ min_dist > %.1f cm`、"
          % (LIFT_OK_CM, LIFT_OK_CM, NEAR_CM))
    print("  C `≥%.1f ∧ min_dist ≤ %.1f cm`。正向判据无倾角项 ⇒ 严格 == 放宽（脚本里逐局核过）。"
          % (LIFT_OK_CM, NEAR_CM))
    print()

    cells = {}
    for arm_key, arm in ARMS.items():
        for k in sorted(arm["reads"]):
            cells[(arm_key, k)] = collect(arm, k)

    print("## 一、2 臂 × 3 个 K")
    print()
    print("| 臂 | K | 局数 | 成功 | A 没抓起 | B 没送到 | C 没落定 | **A 率** | Wilson 95%（成功） |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for arm_key, arm in ARMS.items():
        for k in sorted(arm["reads"]):
            c = cells[(arm_key, k)]
            if not c["n"]:
                print("| %s | %d | 0 | — | — | — | — | — | — |" % (arm_key, k))
                continue
            print("| %s | %d | %d | %d = %s | %d | %d | %d | **%.1f%%** | %s |"
                  % (arm_key, k, c["n"], c["ok"], pct(c["ok"], c["n"]), c["A"], c["B"], c["C"],
                     100 * c["a_rate"], ci(c["ok"], c["n"])))
    print()
    for arm_key, arm in ARMS.items():
        print("* %s" % arm["label"])
        for k in sorted(arm["reads"]):
            c = cells[(arm_key, k)]
            for r in c["reads"]:
                print("  * K=%d %s（%s）：%d/%d 成功，`policy_ckpt` 出身已核"
                      % (k, r["dir"], r["origin"], r["n_success"], r["n"]))
            for d, why in c["rejected"]:
                print("  * 🚫 K=%d `%s` **作废**：%s" % (k, d, why))
            if c["missing"]:
                print("  * ⚠️ K=%d 缺产物 %d 读：%s（**不当 0 计入**）" % (k, len(c["missing"]), ", ".join(c["missing"])))
    print()

    print("## 二、平衡性检查（K=10：两臂本来就打平吗）")
    print()
    a10, b10 = cells[("A", 10)], cells[("B", 10)]
    if a10["n"] and b10["n"]:
        p = fisher_two_sided(b10["ok"], b10["n"], a10["ok"], a10["n"])
        print("* A@K10 = %s（n=%d）vs B@K10 = %s（n=%d）：Fisher 双侧 p=%.4f ⇒ %s"
              % (pct(a10["ok"], a10["n"]), a10["n"], pct(b10["ok"], b10["n"]), b10["n"], p,
                 "两臂基线打平，K=50 的差可以直接读" if p >= 0.05
                 else "**两臂基线就不打平** ⇒ K=50 的差要打折读（差里混着基线差）"))
        pa = fisher_two_sided(b10["A"], b10["n"], a10["A"], a10["n"])
        print("* A 率同格对比：%.1f%%（A）vs %.1f%%（B），Fisher p=%.4f"
              % (100 * a10["a_rate"], 100 * b10["a_rate"], pa))
    else:
        print("* 🚫 有一臂在 K=10 没有合格读数 ⇒ 平衡性检查悬空")
    print()

    print("## 三、判定格（K=%d，预注册规则见 runs/S4X_PREREG.md 第三节）" % GATE_K)
    print()
    a50, b50 = cells[("A", GATE_K)], cells[("B", GATE_K)]
    if a50["n"] and b50["n"]:
        ps = fisher_two_sided(b50["ok"], b50["n"], a50["ok"], a50["n"])
        pa = fisher_two_sided(b50["A"], b50["n"], a50["A"], a50["n"])
        print("* 成功率：A %s vs B %s，Δ=%+.1f pp，Fisher 双侧 **p=%.4f**%s"
              % (pct(a50["ok"], a50["n"]), pct(b50["ok"], b50["n"]),
                 100 * (b50["succ"] - a50["succ"]), ps, "（显著）" if ps < 0.05 else "（不显著）"))
        print("* **A 类率**：A %.1f%% vs B %.1f%%，Δ=%+.1f pp，Fisher 双侧 **p=%.4f**%s"
              % (100 * a50["a_rate"], 100 * b50["a_rate"], 100 * (b50["a_rate"] - a50["a_rate"]), pa,
                 "（显著）" if pa < 0.05 else "（不显著）"))
        print("  ⇒ 这一行是本档的**主指标**：机理假说说的是「K≥25 塌陷 = A 类塌陷」。")
    label, reasons = verdict_string(b50, a50)
    print()
    print("### 判定：%s" % label)
    for r in reasons:
        print("* %s" % r)
    print()

    print("## 四、并列：K=25（n=20/臂，1σ≈11 pp，**只作方向性**）")
    print()
    a25, b25 = cells[("A", 25)], cells[("B", 25)]
    if a25["n"] and b25["n"]:
        print("* 成功率：A %s vs B %s；A 类率：%.1f%% vs %.1f%%；Fisher p（成功）=%.4f、p（A 率）=%.4f"
              % (pct(a25["ok"], a25["n"]), pct(b25["ok"], b25["n"]),
                 100 * a25["a_rate"], 100 * b25["a_rate"],
                 fisher_two_sided(b25["ok"], b25["n"], a25["ok"], a25["n"]),
                 fisher_two_sided(b25["A"], b25["n"], a25["A"], a25["n"])))
    else:
        print("* 🚫 有一臂在 K=25 没有合格读数 ⇒ 本格悬空")
    print()

    print("## 五、纪律与功效（预注册写死的部分，不许事后改）")
    print()
    print("* 🚫 **本档不改工作点**：K=10 仍是档 5 的设计点。即使 B@K50 打平 B@K10，挪部署点也需要"
          "另立一档做**非劣性检验**（每格 n≥60 + 预设非劣边界），否则就是看完数再挑口径。")
    print("* 功效：K=50 每臂 n=%d/%d；K=25 每臂 n=%d/%d。坑 39：评测不可复现（π₀.₅ flow-matching 的"
          % (a50["n"], b50["n"], a25["n"], b25["n"]))
    print("  torch 噪声没钉种子），同权重两读 = **独立抽样**，合并合法但不能当复现。")
    print("* 「不显著」读作**没测出差别**，不是「证明了没差别」。")
    print()
    print("## 六、复现")
    print()
    print("```bash")
    print("source code/env.sh")
    print("bash code/chain_s4x_k50fwd.sh     # 4 读（A@K50 第2读、B@K50 ×2、B@K25），逐读核出身")
    print("$MG_PY code/mg_verdict_s4x.py --selftest")
    print("$MG_PY code/mg_verdict_s4x.py     # 本文件")
    print("```")
    return 0


def selftest() -> int:
    import tempfile

    fails: list[str] = []
    n = 0

    def chk(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            fails.append(msg)

    # --- klass 的边界（与 mg_tax_fail 同一把尺子，这里再钉一遍防上游漂）-----
    def ep(success, lift, dist, **kw):
        d = {"success": success, "max_lift_cm": lift, "min_dist_to_target_xy": dist / 100.0,
             "steps": 400, "seed": kw.pop("seed", 2000)}
        d.update(kw)
        d["lift_cm"] = lift
        d["min_dist_cm"] = dist
        return d
    chk(klass(ep(False, 4.9, 60.0), "strict") == "A", "lift 4.9 ⇒ A")
    chk(klass(ep(False, 5.0, 60.0), "strict") == "B", "lift 5.0 恰好够 ∧ 远 ⇒ B")
    chk(klass(ep(False, 12.0, 25.0), "strict") == "C", "dist 25.0 恰好 ⇒ C")
    chk(klass(ep(True, 0.1, 99.0), "strict") == "OK", "成功局一律 OK")

    # --- check_provenance：五种违规各钉一条 --------------------------------
    arm = {"run": "pi05_rand60_s1", "step": 7200}
    good = {"task_mode": "forward", "seed": 2000, "seed_mode": "random", "n_action_steps": 50,
            "policy_ckpt": "/x/runs/pi05_rand60_s1/checkpoints/007200/pretrained_model",
            "per_episode": []}
    with tempfile.TemporaryDirectory() as td:
        import mg_verdict_s4x as M
        old = M.RUNS
        M.RUNS = Path(td)
        (Path(td) / "pi05_rand60_s1" / "checkpoints").mkdir(parents=True)
        (Path(td) / "pi05_rand60_s1" / "checkpoints" / "007200").mkdir()
        (Path(td) / "pi05_rand60_s1" / "checkpoints" / "last").symlink_to(
            Path(td) / "pi05_rand60_s1" / "checkpoints" / "007200")
        try:
            chk(M.check_provenance(good, arm, 50, "d") == [], "干净的一读不该报违规：%r"
                % M.check_provenance(good, arm, 50, "d"))
            for key, val, frag in (("task_mode", "reverse", "task_mode"),
                                   ("seed", 7000, "seed="),
                                   ("seed_mode", "fixed", "seed_mode"),
                                   ("n_action_steps", 10, "n_action_steps")):
                j = dict(good); j[key] = val
                bad = M.check_provenance(j, arm, 50, "d")
                chk(len(bad) == 1 and frag in bad[0], "%s 违规要被抓到，实得 %r" % (key, bad))
            j = dict(good); j["policy_ckpt"] = "/x/checkpoints/022000/pretrained_model"
            bad = M.check_provenance(j, arm, 50, "d")
            chk(len(bad) == 1 and "mismatch" in bad[0], "格号不符要判 mismatch，实得 %r" % bad)
            # 记 last 且 last 确实指向 007200 ⇒ 合格
            j = dict(good); j["policy_ckpt"] = "/x/checkpoints/last/pretrained_model"
            chk(M.check_provenance(j, arm, 50, "d") == [], "last 指向本格时应判合格")
            # 正向两口径不一致 ⇒ 判据不变量破了
            j = dict(good); j["success_relaxed"] = 1
            j["per_episode"] = [{"seed": 2000, "success": True, "success_relaxed": False}]
            bad = M.check_provenance(j, arm, 50, "d")
            chk(any("不变量" in b for b in bad), "正向严格≠放宽要报不变量破，实得 %r" % bad)
            # 正向两口径一致 ⇒ 干净
            j["per_episode"] = [{"seed": 2000, "success": True, "success_relaxed": True}]
            chk(M.check_provenance(j, arm, 50, "d") == [], "正向两口径一致应判干净")

            # --- collect：作废读不进分母、缺产物不当 0 ----------------------
            d1 = Path(td) / "r1"; d1.mkdir()
            (d1 / "eval_summary.json").write_text(json.dumps(dict(
                good, per_episode=[ep(True, 12, 1), ep(False, 0.3, 70), ep(False, 12, 60)])))
            d2 = Path(td) / "r2"; d2.mkdir()
            (d2 / "eval_summary.json").write_text(json.dumps(dict(
                good, seed=7000, per_episode=[ep(False, 0.3, 70)])))      # seed 不符 ⇒ 作废
            armT = {"run": "pi05_rand60_s1", "step": 7200,
                    "reads": {50: [("r1", "历史"), ("r2", "本档新跑"), ("gone", "历史")]}}
            c = M.collect(armT, 50)
            chk(c["n"] == 3, "只有 r1 合格 ⇒ n 应为 3，实得 %d" % c["n"])
            chk(c["ok"] == 1 and c["A"] == 1 and c["B"] == 1, "分类应为 OK/A/B 各 1，实得 %r" % c)
            chk(len(c["rejected"]) == 1 and "seed=" in c["rejected"][0][1], "r2 要以 seed 违规作废")
            chk(c["missing"] == ["gone（历史）"], "缺产物要进 missing，实得 %r" % c["missing"])
            chk(abs(c["a_rate"] - 1 / 3) < 1e-12, "A 率应是 1/3")

            # --- verdict_string：预注册阈值的四个角 -------------------------
            def cell(succ_n, n, A):
                return {"n": n, "ok": succ_n, "A": A, "B": 0, "C": 0,
                        "a_rate": A / n if n else float("nan"),
                        "succ": succ_n / n if n else float("nan")}
            lab, _ = M.verdict_string(cell(18, 40, 4), cell(12, 40, 20))
            chk(lab == "H1 机理成立", "A率10%% ∧ 成功45%% ⇒ 应判 H1，实得 %r" % lab)
            lab, _ = M.verdict_string(cell(12, 40, 20), cell(12, 40, 20))
            chk(lab == "H0 塌陷是内禀的", "A率50%% ∧ 成功30%% ⇒ 应判 H0，实得 %r" % lab)
            lab, _ = M.verdict_string(cell(16, 40, 12), cell(12, 40, 20))
            chk(lab.startswith("部分支持"), "A率30%% ∧ 成功40%% ⇒ 中间地带，实得 %r" % lab)
            lab, rs = M.verdict_string(cell(0, 0, 0), cell(12, 40, 20))
            chk(lab == "悬空" and rs, "B 无读数 ⇒ 悬空")
            # 边界：恰好 25% / 45% 应算 H1（阈值是 ≤ / ≥）
            lab, _ = M.verdict_string(cell(18, 40, 10), cell(12, 40, 20))
            chk(lab == "H1 机理成立", "A率恰好 25%% ∧ 成功恰好 45%% ⇒ 应判 H1（含等号），实得 %r" % lab)
        finally:
            M.RUNS = old

    # --- 复用语义钉子的参考值（防上游改了签名这边静默算错）----------------
    chk(abs(fisher_two_sided(6, 20, 2, 20) - 0.23511623511623514) < 1e-12, "fisher 参考值漂了")
    chk(pct(6, 20) == "30.0%", "pct(6,20) 应为 30.0%%，实得 %r" % pct(6, 20))
    chk(pct(0, 0) == "—", "pct 零分母要给破折号")
    chk(H1_A_RATE_MAX < H0_A_RATE_MIN and H1_SUCC_MIN > H0_SUCC_MAX,
        "H1/H0 阈值不许重叠（重叠会出现自相矛盾的判定）")
    chk(GATE_K in (25, 50), "判定格必须是悬崖那两格之一")

    print("档4x 判定工具钉子：%d 项检查，%d 项失败" % (n, len(fails)))
    for f in fails[:20]:
        print("  FAIL " + f)
    if fails:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
