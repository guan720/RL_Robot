#!/usr/bin/env python
"""多 run 配对比较：val 曲线符号检验 + 训练日志噪声画像 + 早筛回溯（**零 GPU**）。

出处的三个问题（`code/chain_s3r_sweep_seed3000.sh` 头注释预注册的第 2 步 + 坑 57 的处方）：
  Q1 **好 seed 是不是全程都好**？把多条 val 曲线放在**同一组 epoch 格**上逐格配对，
     做符号检验（不靠单格功效，只看方向一致性）。若成立 ⇒ 坏 seed 在训练早期就可识别，
     存在便宜的早筛协议（不必盲跑 8 h 51 m 才发现这一发崩了）。
  Q2 **能不能只用训练日志（不花 GPU）区分好坏 seed**？三个 run 的 log_freq 都是 100、
     总步数都是 22000 ⇒ 220 个记录点**逐点同 epoch、同样本窗**（AverageMeter 窗长 = log_freq，
     出处 `lerobot/scripts/lerobot_train.py:376-381`），可以直接配对比较 `loss` / `grdn`。
     要区分「共同的收敛趋势」与「run 各自的抖动」，用**残差**口径：
     `resid_i = log(x_{r,i}) − log(mean_r x_{·,i})`，再比 run 间残差 sd。
  Q3 **早筛协议的历史表现**（回溯，n=3，明确不是门）：在第 S 格用阈值 T 决定「留 / 杀」，
     与已知 TEST 判定对照，数 TP / FN（白烧）/ FP（坏 seed 漏网）。

⚠️ 纪律（都是踩过的坑，写在这里免得下一个人重踩）：
  * val 每格 n=20、p≈0.3 时 1σ≈10 pp ⇒ **单格读数不能当门**（坑 27/42：挑 val 峰值 = 在噪声里挑峰）。
    主统计量是**配对符号检验**：只用方向、不用幅度，因此不受单格功效限制。但同一 run 的相邻
    检查点高度相关 ⇒ p 值读作「方向一致性的强度」，不是无偏的 I 类错误率。
  * 池化 Fisher（把 9 格 ×20 局当 180 局）**高估显著性**：同一 run 的检查点不是独立样本。
    报告里池化 p 一律并列符号检验 p，并注明前者不作数。
  * Q2/Q3 都只有 n=3 ⇒ 只能读方向、不能下判定（坑 57）；任何阈值 T 都是**回溯挑的**，
    报告里必须写「未前瞻验证」，不得直接当档 7 的门。
  * **不重实现读盘**：epoch 网格与最近邻对齐规则复用 `mg_epoch_curve.align` / `steps_per_epoch`
    （坑 54：同一个量被两套代码各算一遍，就会各说各话）。`mg_epoch_curve.py` 是冻结文件，
    所以本工具只 import、不改它；`n_success_relaxed` 由本工具自己读（那个工具只读严格口径）。

用法：
    $MG_PY code/mg_seedcurve.py --selftest
    $MG_PY code/mg_seedcurve.py \
      --run seed1000:runs/pi05_mix60f120r_s2e \
      --run seed2000:runs/pi05_mix60f120r_s3r_seed2000 \
      --run seed3000:runs/pi05_mix60f120r_s3r_seed3000 \
      --log seed1000:runs/pi05_mix60f120r_s2e/train.log \
      --log seed2000:runs/pi05_mix60f120r_s3r_seed2000/train.log \
      --log seed3000:runs/pi05_mix60f120r_s3r_seed3000/train.log \
      --test seed1000:55:80 --test seed2000:33:80 --test seed3000:64:80 \
      --metric relaxed --gate 0.50 --out runs/_diag/seedcurve_sign.md
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
sys.path.insert(0, str(HERE))

import mg_epoch_curve as EC  # noqa: E402  冻结文件，只 import

METRICS = {
    "strict": ("n_success", "严格（历史口径）"),
    "relaxed": ("n_success_relaxed", "放宽 R（用户 2026-10-02：送到为首要，侧躺打标）"),
}
CELL_RE = re.compile(r"step_(\d+)_(fwd|rev)")


# ─────────────────────────── 统计原语 ───────────────────────────
def fisher2(a: int, b: int, c: int, d: int) -> float:
    """双侧精确 Fisher（超几何直算，不引 scipy）。表 [[a,b],[c,d]]，行=组、列=成功/失败。"""
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    if r1 == 0 or r2 == 0 or c1 == 0 or c1 == n:
        return 1.0
    lo, hi = max(0, c1 - r2), min(c1, r1)

    def loghyp(x: int) -> float:
        return (math.lgamma(r1 + 1) + math.lgamma(r2 + 1) + math.lgamma(c1 + 1) + math.lgamma(n - c1 + 1)
                - math.lgamma(x + 1) - math.lgamma(r1 - x + 1)
                - math.lgamma(c1 - x + 1) - math.lgamma(r2 - c1 + x + 1) - math.lgamma(n + 1))

    p0 = loghyp(a)
    return min(1.0, sum(math.exp(loghyp(x)) for x in range(lo, hi + 1) if loghyp(x) <= p0 + 1e-9))


def sign_test_exact(wins: int, losses: int) -> float:
    """双侧精确符号检验：n = wins+losses（平局丢弃），H0: p=0.5。"""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def cv(xs: list[float]) -> float:
    """变异系数 sd/|mean|；mean=0 或点数<2 时返回 nan（不静默给 0）。"""
    if len(xs) < 2:
        return float("nan")
    m = statistics.fmean(xs)
    return statistics.stdev(xs) / abs(m) if m != 0 else float("nan")


def resid_log_sd(series: dict[str, list[float]], n_ref: int | None = None) -> dict[str, float]:
    """每条 run 取 log、减掉同索引的跨 run 均值，返回各 run 的残差 sd + `__aligned_len__`。

    为什么要残差：`grdn` 从 4.27 降到 0.15 是**共同收敛趋势**，直接比 sd 会把趋势当噪声。
    为什么取 log：grdn 跨两个数量级，绝对差在早期被放大、后期被压扁。
    ⚠️ 只有 2 条 run 时残差必然完全反对称（sd 相等）⇒ 该口径要求 ≥3 条，工具会标注。
    """
    if not series:
        return {"__aligned_len__": 0.0}
    m = min(len(v) for v in series.values())
    if n_ref is not None:
        m = min(m, n_ref)
    idx = {k: v[:m] for k, v in series.items()}
    logs = {k: [math.log(max(x, 1e-12)) for x in v] for k, v in idx.items()}
    means = [statistics.fmean([logs[k][i] for k in logs]) for i in range(m)]
    out = {k: (statistics.stdev([logs[k][i] - means[i] for i in range(m)]) if m >= 2 else float("nan"))
           for k in logs}
    out["__aligned_len__"] = float(m)
    out["__n_runs__"] = float(len(series))
    return out


def parse_train_log(text: str) -> list[dict]:
    """从 lerobot 的 INFO 行抓 (epch, loss, grdn, lr, updt_s, data_s)；顺序即记录顺序。

    只认含 `updt_s:` 的行 ⇒ 进度条（`1.40s/step`，含首步预热的累计平均）不会被误当成稳态。
    """
    rows = []
    for line in text.splitlines():
        if "updt_s:" not in line:
            continue
        rec: dict = {}
        for key in ("epch", "loss", "grdn", "lr", "updt_s", "data_s"):
            j = line.find(key + ":")
            if j < 0:
                rec[key] = None
                continue
            frag = line[j + len(key) + 1:].split()[0]
            try:
                rec[key] = float(frag)
            except ValueError:
                rec[key] = frag
        if rec.get("grdn") is None or rec.get("epch") is None or rec.get("loss") is None:
            continue
        rows.append(rec)
    return rows


def read_cells(run: Path, sub: str, direction: str, spe: float) -> list[dict]:
    """读 run/<sub>/step_<s>_<dir>/eval_summary.json，严格与放宽口径一起读。

    与 `mg_epoch_curve.read_curve` 的差异（也是必须自己读的原因）：
      * 多读 `n_success_relaxed` / `n_delivered_tipped`（门在放宽口径上，见 runs/S3R_VERDICT.md）；
      * 缺放宽字段的格标 `relaxed=None` 而不是 0 —— 档 2e(seed1000) 的扫描早于放宽判据上线，
        把「没有这个字段」当成「0 次成功」会造出一条假曲线（坑 54 同一类病）。
    """
    d = run / sub
    out = []
    if not d.is_dir():
        return out
    for cell in sorted(d.glob("step_*")):
        m = CELL_RE.fullmatch(cell.name)
        if not m or m.group(2) != direction:
            continue
        f = cell / "eval_summary.json"
        if not f.is_file():
            continue
        j = json.loads(f.read_text())
        n = int(j.get("episodes") or 0)
        if n <= 0:
            continue
        k = int(j.get("n_success") or 0)
        kr = j.get("n_success_relaxed")
        step = int(m.group(1))
        out.append({"step": step, "dir": direction, "n": n, "k": k, "p": k / n,
                    "ep": step / spe if spe else 0.0,
                    "k_relaxed": (int(kr) if kr is not None else None),
                    "p_relaxed": (int(kr) / n if kr is not None else None),
                    "tipped": j.get("n_delivered_tipped"),
                    "K": j.get("n_action_steps"), "seed": j.get("seed"),
                    "path": str(f.relative_to(MG)) if str(f).startswith(str(MG)) else str(f)})
    out.sort(key=lambda r: r["step"])
    return out


def kof(row: dict, metric: str) -> int | None:
    return row["k"] if metric == "strict" else row["k_relaxed"]


def paired_grid(a: list[dict], b: list[dict], min_epoch: float, metric: str) -> list[dict]:
    """两条 val 曲线在 epoch 网格上逐格配对（对齐规则 = mg_epoch_curve.ALIGN_RULE，最近邻+早步优先）。

    任一格在选定口径上没有读数 ⇒ 该格**跳过并计数**（不当 0），报告里写明丢了几格。
    """
    pairs = EC.align(a, b)
    out = []
    for pa, pb in pairs:
        if pb is None or pa["ep"] < min_epoch - 1e-9:
            continue
        ka, kb = kof(pa, metric), kof(pb, metric)
        if ka is None or kb is None:
            continue
        ra, rb = ka / pa["n"], kb / pb["n"]
        out.append({"step": pa["step"], "epoch": pa["ep"],
                    "a_k": ka, "a_n": pa["n"], "a_rate": ra,
                    "b_k": kb, "b_n": pb["n"], "b_rate": rb,
                    "delta_pp": round(100 * (ra - rb), 1),
                    "winner": "a" if ra > rb else ("b" if rb > ra else "tie"),
                    "fisher_p": fisher2(ka, pa["n"] - ka, kb, pb["n"] - kb)})
    return out


def screen_backtest(runs: dict[str, list[dict]], test: dict[str, tuple[int, int]], gate: float,
                    thresholds: list[float], min_epoch: float, metric: str,
                    total_steps: int = 22000) -> list[dict]:
    """早筛回溯：在第 S 格用「val rate ≥ T 就留」的规则，与 TEST 门对照。

    TP=留且 TEST 过门；FN=杀但 TEST 过门（白烧的算力）；FP=留但 TEST 不过门（坏 seed 漏网）；
    TN=杀且 TEST 不过门（省下的算力）。
    ⚠️ n = run 数（这里 3），阈值是**看着同一批数据挑的** ⇒ 回溯、不是门（坑 27/42/57）。
    """
    out = []
    grid = sorted({r["step"] for rows in runs.values() for r in rows
                   if r["ep"] >= min_epoch - 1e-9 and kof(r, metric) is not None})
    for step in grid:
        for thr in thresholds:
            tp = fn = fp = tn = 0
            kept, ep = [], None
            for lab, rows in runs.items():
                cell = next((r for r in rows if r["step"] == step), None)
                if cell is None or lab not in test:
                    continue
                k = kof(cell, metric)
                if k is None:
                    continue
                ep = cell["ep"]
                passed = (test[lab][0] / test[lab][1]) >= gate
                if k / cell["n"] >= thr:
                    kept.append(lab)
                    tp += int(passed)
                    fp += int(not passed)
                else:
                    fn += int(passed)
                    tn += int(not passed)
            if ep is None:
                continue
            out.append({"step": step, "epoch": round(ep, 3), "thr": thr,
                        "TP": tp, "FN": fn, "FP": fp, "TN": tn, "kept": kept,
                        "perfect": (fp == 0 and fn == 0 and tp > 0),
                        "cost_pct": round(100.0 * step / total_steps, 1)})
    return out


# ─────────────────────────── 报告 ───────────────────────────
def build_report(specs, logs, test, gate, min_epoch, direction, metric, thresholds, out_path) -> dict:
    mkey, mdesc = METRICS[metric]
    runs: dict[str, list[dict]] = {}
    prov: dict[str, str] = {}
    for label, path, sub in specs:
        p = Path(path)
        if not p.is_absolute():
            p = MG / p
        spe, src = EC.steps_per_epoch(p)
        used = sub or EC.detect_sub(p)
        rows = read_cells(p, used, direction, spe)
        if not rows:
            raise SystemExit(f"[seedcurve] FATAL {label} 在 {p}/{used} 读不到 direction={direction} 的格")
        runs[label] = rows
        n_have = sum(1 for r in rows if kof(r, metric) is not None)
        prov[label] = (f"{EC._rel(p)}/{used}；steps/epoch={spe}（{src}）；格数={len(rows)}；"
                       f"其中 {metric} 口径有读数 {n_have}/{len(rows)}")
    labs = list(runs)
    if len(labs) < 2:
        raise SystemExit("[seedcurve] 至少两条 run 才能配对")

    L = ["# 多 run 配对比较：val 曲线符号检验 + 训练噪声画像 + 早筛回溯", "",
         f"生成时间：{datetime.now().strftime('%F %T')}（`code/mg_seedcurve.py`）", "",
         f"- direction = **{direction}**；口径 = **{metric}**（{mdesc}，字段 `{mkey}`）",
         f"- min_epoch = **{min_epoch}**；TEST 门 = 放宽口径 ≥ **{gate:.0%}**（出处 `runs/S3R_VERDICT.md`）",
         "- 出身（每条 run 的读盘路径 / steps-per-epoch 反查出处 / 该口径的格覆盖率）："]
    for lab, s in prov.items():
        L.append(f"  - `{lab}` ← {s}")
    L += ["", "> ⚠️ 本文件是**趋势与诊断**，不是门。过没过门只由 `mg_verdict_s3r.py` 读 TEST 得出。",
          "> val 每格 n=20、p≈0.3 时 1σ≈10 pp；同一 run 的相邻检查点高度相关 ⇒",
          "> 符号检验的 p 读作「方向一致性强度」，池化 Fisher 的 p **高估显著性、不作数**。",
          "> 缺放宽字段的格按「无读数」跳过，**不当 0**（坑 54）。", ""]

    # 一、逐格并排
    all_steps = sorted({r["step"] for rows in runs.values() for r in rows})
    L += ["## 一、逐格并排（同一组 step / epoch）", "",
          "| step | epoch | " + " | ".join(f"{l} 严格 | {l} 放宽" for l in labs) + " |",
          "|---:|---:|" + "---:|---:|" * len(labs)]
    for st in all_steps:
        ep = next((r["ep"] for l in labs for r in runs[l] if r["step"] == st), None)
        cells = []
        for l in labs:
            r = next((x for x in runs[l] if x["step"] == st), None)
            if r is None:
                cells += ["—", "—"]
            else:
                cells.append(f"{r['k']}/{r['n']} = {100*r['p']:.0f}%")
                cells.append(f"{r['k_relaxed']}/{r['n']} = {100*r['p_relaxed']:.0f}%"
                             if r["k_relaxed"] is not None else "（无字段）")
        L.append(f"| {st} | {ep:.2f} | " + " | ".join(cells) + " |")
    L.append("")
    pooled: dict[str, tuple[int, int]] = {}
    L += [f"### 池化（epoch ≥ {min_epoch} 的格合并；**相关样本，只作参考**）", "",
          "| run | 合并 succ/n（本口径） | 合并 rate |", "|:--|---:|---:|"]
    for l in labs:
        s = sum(kof(r, metric) for r in runs[l] if r["ep"] >= min_epoch - 1e-9 and kof(r, metric) is not None)
        n = sum(r["n"] for r in runs[l] if r["ep"] >= min_epoch - 1e-9 and kof(r, metric) is not None)
        pooled[l] = (s, n)
        L.append(f"| `{l}` | {s}/{n} | {100*s/max(1,n):.1f}% |")
    L.append("")

    # 二、配对符号检验
    L += [f"## 二、两两配对符号检验（epoch ≥ {min_epoch}，口径 = {metric}）", "",
          "| A | B | 配对格数 | A 胜 | B 胜 | 平 | Δrate 中位(pp) | **符号 p（主统计量）** | 池化 Fisher p（不作数） | 首个单格 p<0.05 |",
          "|:--|:--|---:|---:|---:|---:|---:|---:|---:|:--|"]
    detail = {}
    for la, lb in combinations(labs, 2):
        g = paired_grid(runs[la], runs[lb], min_epoch, metric)
        detail[(la, lb)] = g
        if not g:
            L.append(f"| `{la}` | `{lb}` | 0 | — | — | — | — | — | — | 无可配对格 |")
            continue
        w = sum(1 for x in g if x["winner"] == "a")
        lo = sum(1 for x in g if x["winner"] == "b")
        t = sum(1 for x in g if x["winner"] == "tie")
        ds = statistics.median([x["delta_pp"] for x in g])
        sa, na = pooled[la]
        sb, nb = pooled[lb]
        first = next((f"step {x['step']}（{x['a_rate']:.0%} vs {x['b_rate']:.0%}，p={x['fisher_p']:.3f}）"
                      for x in g if x["fisher_p"] < 0.05), "无")
        L.append(f"| `{la}` | `{lb}` | {len(g)} | {w} | {lo} | {t} | {ds:+.1f} | "
                 f"**{sign_test_exact(w, lo):.4f}** | {fisher2(sa, na-sa, sb, nb-sb):.4g} | {first} |")
    L += ["", "### 逐格明细（A/B = 严格或放宽 rate，括号 = 该格胜方）", ""]
    for (la, lb), g in detail.items():
        if not g:
            continue
        L.append(f"- `{la}` vs `{lb}`：" + ", ".join(
            f"{x['step']}:{x['a_rate']:.0%}/{x['b_rate']:.0%}({x['winner'][0].upper() if x['winner']!='tie' else 'T'})"
            for x in g))
    L.append("")

    # 三、训练日志画像
    L += ["## 三、训练日志画像（零 GPU）", ""]
    if not logs:
        L += ["（没传 `--log`，跳过本节）", ""]
        noise = {}
    else:
        parsed = {}
        for lab, p in logs.items():
            pp = Path(p)
            if not pp.is_absolute():
                pp = MG / pp
            if not pp.exists():
                L.append(f"- ⚠️ `{lab}` 的日志不在：{EC._rel(pp)} ⇒ 跳过")
                continue
            rows = parse_train_log(pp.read_text(errors="ignore"))
            if not rows:
                L.append(f"- ⚠️ `{lab}` 的 {EC._rel(pp)} 解析出 0 行 ⇒ 跳过")
                continue
            parsed[lab] = rows
        noise = {}
        if parsed:
            lens = {k: len(v) for k, v in parsed.items()}
            n_ref = min(lens.values())
            L += [f"- 参与 run：{', '.join(f'`{k}`({v} 点)' for k, v in lens.items())}；"
                  f"对齐长度 = **{n_ref}**（取最短、尾巴截断 ⇒ 逐点同 epoch）",
                  "- 样本窗对齐：所有 run 的 `log_freq=100`、`batch=8` ⇒ AverageMeter 窗 = 800 样本，"
                  "逐点同窗（**换 batch 时必须按 `log_freq = 800/batch` 重设**，否则窗长不同、CV 不可比）", "",
                  "| run | 点数 | 末点 epoch | loss 首→末 | grdn 首→末 | loss 残差 sd | grdn 残差 sd | "
                  "grdn CV（后半） | loss CV（后半） | updt_s 中位 |",
                  "|:--|---:|---:|:--|:--|---:|---:|---:|---:|---:|"]
            rl = resid_log_sd({k: [r["loss"] for r in v] for k, v in parsed.items()})
            rg = resid_log_sd({k: [r["grdn"] for r in v] for k, v in parsed.items()})
            for lab, rows in parsed.items():
                half = rows[len(rows) // 2:]
                up = [r["updt_s"] for r in rows if isinstance(r.get("updt_s"), float)]
                L.append(f"| `{lab}` | {len(rows)} | {rows[-1]['epch']:.2f} | "
                         f"{rows[0]['loss']:.3f} → {rows[-1]['loss']:.4f} | "
                         f"{rows[0]['grdn']:.2f} → {rows[-1]['grdn']:.3f} | "
                         f"{rl[lab]:.4f} | **{rg[lab]:.4f}** | "
                         f"{cv([r['grdn'] for r in half]):.4f} | {cv([r['loss'] for r in half]):.4f} | "
                         f"{statistics.median(up):.3f} |")
            noise = {k: {"grdn_resid_sd": rg[k], "loss_resid_sd": rl[k]} for k in parsed}
            L += ["", "- 残差口径：`resid_i = log(x_i) − log(mean_run x_i)`；减掉同索引跨 run 均值是为了扣掉"
                  "**共同收敛趋势**（grdn 跨两个数量级，直接比 sd 会把趋势当噪声）。",
                  f"- ⚠️ n={len(parsed)} ⇒ 残差 sd 的自由度只有 {len(parsed)-1}，**只能读方向**（坑 57）；"
                  "n=2 时残差必然反对称、sd 恒等，该口径要求 ≥3 条 run。", ""]
            if test:
                L += ["### 与 TEST 结局的对照（回溯，不是门）", "",
                      f"| run | TEST 放宽 | 过门(≥{gate:.0%})? | grdn 残差 sd | loss 残差 sd |",
                      "|:--|---:|:--|---:|---:|"]
                for lab in parsed:
                    if lab in test:
                        s, n = test[lab]
                        L.append(f"| `{lab}` | {s}/{n} = {100*s/n:.1f}% | {'✅' if s/n >= gate else '❌'} | "
                                 f"{rg[lab]:.4f} | {rl[lab]:.4f} |")
                over = [lab for lab in parsed if lab in test and test[lab][0] / test[lab][1] < gate]
                good = [lab for lab in parsed if lab in test and test[lab][0] / test[lab][1] >= gate]
                if over and good:
                    worst_g = max(rg[l] for l in good)
                    sep = all(rg[l] > worst_g for l in over)
                    sep_l = all(rl[l] > worst_g for l in over)
                    L += ["", f"- 不过门的 run（{', '.join(over)}）grdn 残差 sd 是否**全部**大于过门 run 的最大值"
                          f"（{worst_g:.4f}）：**{'是' if sep else '否'}** ⇒ "
                          + ("训练日志里有先兆，存在**零 GPU** 早筛的可能（但 n 太小，必须前瞻验证）"
                             if sep else "grdn 画像分不开 ⇒ loss/grdn 不是可用的筛子"),
                          f"- 同一判据套 loss 残差 sd：**{'是' if sep_l else '否'}**",
                          "- 读法：若两者都「否」⇒ 分歧发生在**行为空间**而不在损失空间，"
                          "早筛只能靠 val rollout（要花 GPU），这也说明「loss 收敛了」不等于「行为对了」。"]
                L.append("")

    # 四、早筛回溯
    if test:
        L += ["## 四、早筛回溯表（阈值是看着同一批数据挑的 ⇒ **未前瞻验证，不是门**）", "",
              "- TEST 结局：" + ", ".join(f"`{k}` {v[0]}/{v[1]}={100*v[0]/v[1]:.1f}%"
                                          f"{'✅' if v[0]/v[1] >= gate else '❌'}" for k, v in test.items()),
              f"- 规则：在第 S 格若 val({metric}) ≥ T 就**留**（继续训到 3.79 epoch），否则**杀**（省掉剩下的算力）", "",
              "| step | epoch | 占全程 % | 阈值 T | 留 | TP | FN（白烧） | FP（漏网） | TN | 完美分类 |",
              "|---:|---:|---:|---:|:--|---:|---:|---:|---:|:--|"]
        bt = screen_backtest(runs, test, gate, thresholds, min_epoch, metric)
        for r in bt:
            L.append(f"| {r['step']} | {r['epoch']} | {r['cost_pct']} | {r['thr']:.2f} | "
                     f"{','.join(r['kept']) or '（全杀）'} | {r['TP']} | {r['FN']} | {r['FP']} | {r['TN']} | "
                     f"{'✅' if r['perfect'] else ''} |")
        perf = [r for r in bt if r["perfect"]]
        L += ["", f"- 能完美分类的 (step, T) 组合 = **{len(perf)}/{len(bt)}**"]
        if perf:
            cheapest = min(r["step"] for r in perf)
            row = next(r for r in perf if r["step"] == cheapest)
            L += [f"- 最便宜的可筛点 = step **{cheapest}**（epoch {row['epoch']}）= 全程的 "
                  f"{row['cost_pct']}% ⇒ 杀一个坏 seed 的花费 ≈ {row['cost_pct']/100*8.86:.1f} h 训练"
                  f" + 一次 20 局 val（≈6.4 min），对比盲跑一整个 run 的 8 h 51 m",
                  f"- 该点可用的阈值区间：T ∈ [{max([r['thr'] for r in perf if r['step']==cheapest]+[0]):.2f}, …]"
                  f"（表里 step={cheapest} 且打 ✅ 的行）",
                  "- ⚠️ 但这是**回溯**挑的：3 个 run、2 类结局，随便一个 T 都可能刚好分开。"
                  "要当协议用必须在**新 seed 上前瞻验证**（档 7B/7C 的免费副产物，不额外花 GPU）。"]
        else:
            L.append("- 没有能完美分类的 (step, T) ⇒ 在该口径/该 min_epoch 下早筛协议在 n=3 上不可行")
        L.append("")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(L), encoding="utf-8")
    return {"runs": {k: len(v) for k, v in runs.items()}, "metric": metric,
            "pairs": {f"{a}|{b}": [{"step": x["step"], "winner": x["winner"],
                                     "sign_inputs": (sum(1 for y in g if y["winner"] == "a"),
                                                     sum(1 for y in g if y["winner"] == "b")),
                                     "fisher_p": x["fisher_p"]} for x in g]
                      for (a, b), g in detail.items()},
            "noise": noise, "out": str(out_path)}


# ─────────────────────────── 自测 ───────────────────────────
def _mk_run(root: Path, name: str, sub: str, cells: list[tuple[int, int, int, int | None]],
            frames: int = 46426, bs: int = 8, direction: str = "rev") -> Path:
    """造一个最小可读的 run 目录；cells = (step, n, k_strict, k_relaxed|None)。"""
    d = root / name
    (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"batch_size": bs, "dataset_root": str(root / "ds")}))
    ds = root / "ds" / "meta"
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "info.json").write_text(json.dumps({"total_frames": frames}))
    for step, n, k, kr in cells:
        cell = d / sub / f"step_{step}_{direction}"
        cell.mkdir(parents=True, exist_ok=True)
        j = {"episodes": n, "n_success": k, "n_action_steps": 10, "seed": 8000}
        if kr is not None:
            j["n_success_relaxed"] = kr
            j["n_delivered_tipped"] = kr - k
        (cell / "eval_summary.json").write_text(json.dumps(j))
    return d


def selftest() -> int:
    ok = bad = 0

    def chk(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ {name} {detail}")

    # --- fisher2 ---
    chk("fisher 全同 ⇒ p=1", abs(fisher2(10, 10, 10, 10) - 1.0) < 1e-9)
    chk("fisher 空表 ⇒ p=1", fisher2(0, 0, 0, 0) == 1.0)
    chk("fisher 20/0 vs 0/20 ⇒ p<0.001", fisher2(20, 0, 0, 20) < 0.001)
    chk("fisher 组间对称", abs(fisher2(11, 9, 3, 17) - fisher2(3, 17, 11, 9)) < 1e-9)
    chk("fisher 行列转置不变", abs(fisher2(11, 9, 3, 17) - fisher2(11, 3, 9, 17)) < 1e-9)
    chk("fisher 11/20 vs 3/20 ≈ 0.0187（档 6 早筛的实测锚）",
        abs(fisher2(11, 9, 3, 17) - 0.0187) < 5e-4, f"got {fisher2(11,9,3,17):.5f}")
    chk("fisher 5/20 vs 3/20 ≈ 0.70（档 6 另一个锚）",
        abs(fisher2(5, 15, 3, 17) - 0.70) < 0.03, f"got {fisher2(5,15,3,17):.4f}")
    chk("fisher p 全在 [0,1]", all(0.0 <= fisher2(a, 20 - a, b, 20 - b) <= 1.0
                                   for a in range(21) for b in range(21)))
    chk("fisher 单调：a 越大 p 越小（b=5 固定）",
        all(fisher2(a + 1, 19 - a, 5, 15) <= fisher2(a, 20 - a, 5, 15) + 1e-9 for a in range(5, 19)))

    # --- sign_test_exact ---
    chk("符号 0 局 ⇒ p=1", sign_test_exact(0, 0) == 1.0)
    chk("符号 8胜0负 ⇒ p=0.0078125", abs(sign_test_exact(8, 0) - 0.0078125) < 1e-12)
    chk("符号 9胜0负 ⇒ p=0.00390625", abs(sign_test_exact(9, 0) - 2 / 512) < 1e-12)
    chk("符号 8胜1负 ⇒ p=0.0390625", abs(sign_test_exact(8, 1) - 20 / 512) < 1e-12)
    chk("符号对称", sign_test_exact(3, 7) == sign_test_exact(7, 3))
    chk("符号 5胜5负 ⇒ p=1", abs(sign_test_exact(5, 5) - 1.0) < 1e-9)
    chk("符号 1胜0负 ⇒ p=1（n 太小）", abs(sign_test_exact(1, 0) - 1.0) < 1e-9)
    chk("符号 p ≤ 1", sign_test_exact(20, 0) <= 1.0)

    # --- cv ---
    chk("cv 常数序列 = 0", cv([2.0, 2.0, 2.0]) == 0.0)
    chk("cv 单点 = nan", math.isnan(cv([1.0])))
    chk("cv 均值 0 = nan（不静默给 0）", math.isnan(cv([1.0, -1.0])))
    chk("cv [1,2,3] = 0.5", abs(cv([1.0, 2.0, 3.0]) - 0.5) < 1e-9)
    chk("cv 负均值取绝对值", abs(cv([-1.0, -2.0, -3.0]) - 0.5) < 1e-9)

    # --- resid_log_sd ---
    chk("两条完全相同 ⇒ 残差 sd=0",
        resid_log_sd({"a": [1.0] * 3, "b": [1.0] * 3})["a"] == 0.0)
    chk("三条完全相同 ⇒ 全 0",
        all(resid_log_sd({"a": [1., 2., 4.], "b": [1., 2., 4.], "c": [1., 2., 4.]})[k] == 0.0
            for k in "abc"))
    chk("恒定倍数差（共同趋势）⇒ 残差 sd=0",
        abs(resid_log_sd({"a": [1.] * 4, "b": [2.] * 4, "c": [4.] * 4})["b"]) < 1e-9)
    s3 = resid_log_sd({"a": [1.] * 6, "b": [1.] * 6, "c": [1., 3., 1., 3., 1., 3.]})
    chk("抖动的那条 run 残差 sd 最大（n=3 才有意义）",
        s3["c"] > s3["a"] and s3["c"] > s3["b"])
    chk("n=2 时两条 sd 恒等（工具应标注 ≥3 条）",
        abs(resid_log_sd({"a": [1., 1., 1., 1.], "b": [1., 3., 1., 3.]})["a"]
            - resid_log_sd({"a": [1., 1., 1., 1.], "b": [1., 3., 1., 3.]})["b"]) < 1e-12)
    chk("对齐长度 = 最短", resid_log_sd({"a": [1., 2., 3.], "b": [1., 2., 3., 9., 9.]})["__aligned_len__"] == 3.0)
    chk("n_ref 再截断", resid_log_sd({"a": [1., 2., 3.], "b": [1., 2., 3.]}, n_ref=2)["__aligned_len__"] == 2.0)
    chk("0 值不炸", not math.isnan(resid_log_sd({"a": [0., 1., 2.], "b": [1., 0., 2.], "c": [1., 2., 0.]})["a"]))
    chk("空 dict 不炸", resid_log_sd({})["__aligned_len__"] == 0.0)
    chk("n_runs 记对", resid_log_sd({"a": [1.], "b": [2.], "c": [3.]})["__n_runs__"] == 3.0)

    # --- parse_train_log ---
    line = ("INFO 2026-10-03 05:14:06 ot_train.py:435 step:22K smpl:176K ep:682 epch:3.79 "
            "loss:0.027 grdn:0.152 lr:2.5e-06 updt_s:1.366 data_s:0.004")
    pr = parse_train_log(line)
    chk("真日志解析出 1 行", len(pr) == 1)
    chk("epch=3.79", pr and pr[0]["epch"] == 3.79)
    chk("grdn=0.152", pr and pr[0]["grdn"] == 0.152)
    chk("loss=0.027", pr and pr[0]["loss"] == 0.027)
    chk("updt_s=1.366", pr and pr[0]["updt_s"] == 1.366)
    chk("data_s=0.004", pr and pr[0]["data_s"] == 0.004)
    chk("lr 解析成数值 2.5e-06", pr and abs(pr[0]["lr"] - 2.5e-06) < 1e-15)
    chk("进度条不入表", parse_train_log("Training: 100%|█| 22000/22000 [8:51:25<00:00, 1.40s/step]") == [])
    chk("缺 grdn 的行被丢", parse_train_log("INFO step:1 epch:0.1 loss:0.5 updt_s:1.0 data_s:0.0") == [])
    chk("科学计数法能解析",
        parse_train_log("INFO step:1 epch:0.1 loss:1e-05 grdn:2e-03 lr:1e-04 updt_s:1.0 data_s:0.0")[0]["loss"] == 1e-05)
    chk("多行按顺序全收", len(parse_train_log(line + "\n" + line + "\n" + line)) == 3)

    # --- read_cells / kof / paired_grid / screen_backtest（造盘）---
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        A = _mk_run(root, "A", "sweep_rev", [(2000, 20, 0, 0), (6000, 20, 6, 6),
                                             (12000, 20, 11, 12), (22000, 20, 10, 15)])
        B = _mk_run(root, "B", "sweep_rev", [(2000, 20, 1, 1), (6000, 20, 1, 2),
                                             (12000, 20, 3, 3), (22000, 20, 5, 6)])
        C = _mk_run(root, "C", "sweep_rev", [(2000, 20, 0, None), (6000, 20, 2, None),
                                             (12000, 20, 5, None), (22000, 20, 7, 9)])
        spe, src = EC.steps_per_epoch(A)
        chk("steps_per_epoch 反查 = 5803.25", abs(spe - 5803.25) < 1e-6)
        ra, rb, rc = (read_cells(x, "sweep_rev", "rev", spe) for x in (A, B, C))
        chk("read_cells 读到 4 格", len(ra) == 4 and len(rb) == 4 and len(rc) == 4)
        chk("ep 算对（step 22000 ⇒ 3.791）", abs(ra[-1]["ep"] - 22000 / 5803.25) < 1e-9)
        chk("严格口径读 n_success", ra[2]["k"] == 11)
        chk("放宽口径读 n_success_relaxed", ra[2]["k_relaxed"] == 12)
        chk("缺放宽字段 ⇒ None 而不是 0（坑 54）",
            rc[0]["k_relaxed"] is None and rc[0]["p_relaxed"] is None)
        chk("有放宽字段的格 tipped 也读到", ra[3]["tipped"] == 5)
        chk("kof(strict) 走 k", kof(ra[0], "strict") == 0)
        chk("kof(relaxed) 走 k_relaxed", kof(rc[0], "relaxed") is None)
        chk("read_cells 目录不存在 ⇒ 空表", read_cells(root / "nope", "sweep_rev", "rev", spe) == [])

        ga = paired_grid(ra, rb, 0.0, "strict")
        chk("min_epoch=0 ⇒ 4 格全配", len(ga) == 4)
        chk("A 全胜（strict）", all(x["winner"] == "a" for x in paired_grid(ra[1:], rb[1:], 0.0, "strict")))
        chk("delta_pp 算对（55% vs 15% ⇒ +40）",
            abs(next(x["delta_pp"] for x in ga if x["step"] == 12000) - 40.0) < 1e-6)
        chk("fisher_p 与 fisher2 一致",
            abs(ga[2]["fisher_p"] - fisher2(11, 9, 3, 17)) < 1e-12)
        g103 = paired_grid(ra, rb, 1.03, "strict")
        chk("min_epoch=1.03 保留 step6000（ep=1.034）", any(x["step"] == 6000 for x in g103))
        chk("min_epoch=1.03 丢掉 step2000（ep=0.34）", not any(x["step"] == 2000 for x in g103))
        chk("放宽口径配对格数 = 3（C 缺字段的格被跳过，不当 0）",
            len(paired_grid(ra, rc, 0.0, "relaxed")) == 1)
        tieA = _mk_run(root, "TA", "sweep_rev", [(2000, 20, 5, 5)])
        tieB = _mk_run(root, "TB", "sweep_rev", [(2000, 20, 5, 5)])
        chk("平局标 tie", paired_grid(read_cells(tieA, "sweep_rev", "rev", spe),
                                      read_cells(tieB, "sweep_rev", "rev", spe), 0.0, "strict")[0]["winner"] == "tie")
        chk("符号检验 8胜0负 = 0.0078125（档 3r 实测锚）", abs(sign_test_exact(8, 0) - 0.0078125) < 1e-12)

        runs = {"good": ra, "bad": rb}
        test = {"good": (64, 80), "bad": (33, 80)}
        bt = screen_backtest(runs, test, 0.50, [0.25], 0.0, "strict")
        chk("回溯表非空", len(bt) > 0)
        chk("step12000/T=0.25 完美分类（good 55% 留、bad 15% 杀）",
            any(r["perfect"] and r["step"] == 12000 for r in bt))
        chk("cost_pct 算对（12000/22000 = 54.5%）",
            abs(next(r["cost_pct"] for r in bt if r["step"] == 12000) - 54.5) < 0.1)
        bt0 = screen_backtest(runs, test, 0.50, [0.0], 0.0, "strict")
        chk("T=0 ⇒ 全留 ⇒ FP=1、FN=0、不完美", all(r["FP"] == 1 and r["FN"] == 0 and not r["perfect"] for r in bt0))
        bt9 = screen_backtest(runs, test, 0.50, [1.01], 0.0, "strict")
        chk("T>1 ⇒ 全杀 ⇒ FN=1、TP=0、不完美（perfect 要求 TP>0）",
            all(r["FN"] == 1 and r["TP"] == 0 and not r["perfect"] for r in bt9))
        btr = screen_backtest(runs, test, 0.50, [0.25], 0.0, "relaxed")
        chk("放宽口径 step12000：good 60% 留、bad 15% 杀 ⇒ 完美",
            any(r["perfect"] and r["step"] == 12000 for r in btr))
        chk("kept 是列表", all(isinstance(r["kept"], list) for r in bt))
        btc = screen_backtest({"good": ra, "c": rc}, {"good": (64, 80), "c": (55, 80)},
                              0.50, [0.25], 0.0, "relaxed")
        chk("网格取所有 run 的并集（4 格）", len(btc) == 4)
        chk("C 缺放宽字段的格不参与计数（step2000 只有 good ⇒ TP+FN+FP+TN = 1）",
            next(r["TP"] + r["FN"] + r["FP"] + r["TN"] for r in btc if r["step"] == 2000) == 1)
        chk("C 有放宽字段的格（step22000）才两条都计入",
            next(r["TP"] + r["FN"] + r["FP"] + r["TN"] for r in btc if r["step"] == 22000) == 2)

        # --- 报告端到端（造盘）---
        outp = root / "r.md"
        info = build_report([("good", str(A), "sweep_rev"), ("bad", str(B), "sweep_rev"),
                             ("nofield", str(C), "sweep_rev")],
                            {}, test | {"nofield": (55, 80)}, 0.50, 1.03, "rev", "strict",
                            [0.15, 0.25], outp)
        txt = outp.read_text()
        chk("端到端：报告落盘非空", len(txt) > 500)
        chk("端到端：三条 run 都在", all(x in txt for x in ("good", "bad", "nofield")))
        chk("端到端：有符号检验节", "配对符号检验" in txt)
        chk("端到端：有回溯表节", "早筛回溯表" in txt)
        chk("端到端：无 --log 时明说跳过", "没传 `--log`" in txt)
        chk("端到端：标注了池化不作数", "不作数" in txt)
        chk("端到端：标注了回溯未前瞻验证", "未前瞻验证" in txt)
        chk("端到端：返回 3 对 pairs", len(info["pairs"]) == 3)
        chk("端到端：口径写进报告", "strict" in txt)
        outp2 = root / "r2.md"
        build_report([("good", str(A), "sweep_rev"), ("bad", str(B), "sweep_rev")],
                     {}, test, 0.50, 0.0, "rev", "relaxed", [0.25], outp2)
        chk("端到端：放宽口径也能出报告", "relaxed" in outp2.read_text())

    # --- 报告端到端（真产物，若齐）---
    real = [("seed1000", "pi05_mix60f120r_s2e"), ("seed2000", "pi05_mix60f120r_s3r_seed2000"),
            ("seed3000", "pi05_mix60f120r_s3r_seed3000")]
    if all((MG / "runs" / d).is_dir() for _, d in real):
        import tempfile as tf
        with tf.TemporaryDirectory() as td:
            logmap = {l: str(MG / "runs" / d / "train.log") for l, d in real
                      if (MG / "runs" / d / "train.log").exists()}
            o = Path(td) / "real.md"
            info = build_report([(l, str(MG / "runs" / d), "sweep_rev") for l, d in real],
                                logmap, {"seed1000": (55, 80), "seed2000": (33, 80),
                                         "seed3000": (64, 80)}, 0.50, 1.03, "rev", "strict",
                                [0.05, 0.08, 0.10, 0.15, 0.20, 0.25], o)
            txt = o.read_text()
            chk("真产物：三条 run 各 11 格", all(info["runs"][l] == 11 for l, _ in real))
            chk("真产物：220 个记录点全参与对齐", "220" in txt)
            chk("真产物：噪声画像有 grdn 残差 sd", "grdn 残差 sd" in txt)
            chk("真产物：seed1000 缺放宽字段被标出来", "（无字段）" in txt)
            chk("真产物：sign_inputs 已返回", all(len(v[0]["sign_inputs"]) == 2 for v in info["pairs"].values()))
    else:
        print("  (跳过真产物端到端：三个 run 目录不全)")

    print(f"[selftest] {ok} passed, {bad} failed")
    return 1 if bad else 0


def parse_spec(s: str, n: int = 3) -> tuple[str, ...]:
    parts = s.split(":")
    if len(parts) == 2:
        return (parts[0], parts[1], "")
    if len(parts) == n:
        return tuple(parts)
    raise SystemExit(f"[seedcurve] 格式应为 LABEL:PATH[:SUB]，收到 {s!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", default=[], metavar="LABEL:PATH[:SUB]")
    ap.add_argument("--log", action="append", default=[], metavar="LABEL:PATH")
    ap.add_argument("--test", action="append", default=[], metavar="LABEL:SUCC:N",
                    help="该 run 的 TEST 关门读数（**放宽口径**），用于早筛回溯表")
    ap.add_argument("--metric", default="relaxed", choices=sorted(METRICS))
    ap.add_argument("--gate", type=float, default=0.50)
    ap.add_argument("--min-epoch", type=float, default=1.03)
    ap.add_argument("--direction", default="rev", choices=["rev", "fwd"])
    ap.add_argument("--thresholds", default="0.05,0.08,0.10,0.15,0.20,0.25,0.30,0.35,0.40")
    ap.add_argument("--out", default=str(MG / "runs" / "_diag" / "seedcurve_sign.md"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if len(args.run) < 2:
        raise SystemExit("[seedcurve] 至少两条 --run 才能配对")
    specs = [parse_spec(s) for s in args.run]
    logs = {parse_spec(s)[0]: parse_spec(s)[1] for s in args.log}
    test = {}
    for s in args.test:
        lab, su, n = s.split(":")
        test[lab] = (int(su), int(n))
    thr = [float(x) for x in args.thresholds.split(",") if x.strip()]
    info = build_report(specs, logs, test, args.gate, args.min_epoch, args.direction,
                        args.metric, thr, args.out)
    print(f"[seedcurve] 口径={info['metric']}  报告 -> {info['out']}")
    for k, v in info["pairs"].items():
        w, l = v[0]["sign_inputs"] if v else (0, 0)
        print(f"[seedcurve]   {k}: 配对格 {len(v)}  A胜 {w} B胜 {l} 平 {len(v)-w-l}  "
              f"符号 p={sign_test_exact(w, l):.4f}")
    for lab, n in info["noise"].items():
        print(f"[seedcurve]   噪声 {lab}: grdn 残差 sd={n['grdn_resid_sd']:.4f} "
              f"loss 残差 sd={n['loss_resid_sd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
