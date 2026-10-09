#!/usr/bin/env python
"""档 7A-2 · **逐步**梯度噪声探针：把「batch 小 ⇒ 梯度噪声大」这句话变成两个可解的常数。

预注册出处：`runs/S7_PREREG.md` §3 格 7A-2（2026-10-03 13:55 落盘，早于本工具的任何读数）。

模型：设每步梯度 g_b（batch = b）满足
    E‖g_b‖² = G + C/b
其中 G = 真（全批量）梯度范数平方，C/b = 有限样本带来的噪声贡献（方差 ∝ 1/b 是标准结果）。
在两个（或更多）batch 上各测一次 `E‖g‖²`，最小二乘解出 G 与 C，就能算出
    η_b = (C/b) / (G + C/b)      # batch b 下「噪声占 E‖g‖² 的比例」
η 就是本档要的机理量：η₈ 大 ⇒ batch 8 的每步梯度确实被噪声主导 ⇒ 抬 batch 是对症的；
η₈ 小 ⇒ 「run 间 38.8 pp 方差来自梯度噪声」这条机理论证不成立，7B 该暂缓（省钱）。

为什么必须把 lr 压到 1e-6：
    grdn 是**当前参数点**的梯度范数。若两个 batch 各自用正常 lr 跑 100 步，参数早就走到
    不同地方去了，测出来的差里混着「位置不同」而不是「噪声不同」。把 lr 压到 1e-6
    （+ `scheduler_decay_lr=1e-8`，避免 cosine 里 `alpha = decay_lr/peak_lr` 变成 >1 的怪调度），
    100 步的总位移量级 ~1e-4，两个 batch 都在**基座那一个参数点**附近测 ⇒ 干净的对照。
    本工具还会报「前 10 步均值 vs 后 10 步均值」的漂移当哨兵（漂移 >20% ⇒ 该次测量作废）。

为什么必须 `--log_freq=1`：
    `grdn` 是 AverageMeter（出处 `lerobot/scripts/lerobot_train.py:377`），窗长 = log_freq。
    历史 run 用 log_freq=100、batch=8 ⇒ 日志里的 grdn 已经是 **800 样本的平均**，
    逐步噪声被抹掉了 ⇒ 用历史日志根本测不出 η（这正是 `runs/_diag/seedcurve_sign_strict.md`
    第三节只能给出「残差 sd」这种弱读数的原因）。窗长 1 步才拿得到逐步值。

⚠️ grdn 是 `clip_grad_norm_` 的返回值 = **裁剪前**的总范数
   （出处 `lerobot/scripts/lerobot_train.py:126-130`；max_norm=inf 时也返回真范数）
   ⇒ 可以直接当 ‖g‖ 用，不受裁剪阈值影响。

用法：
    $MG_PY code/mg_probe_gradnoise.py --selftest
    $MG_PY code/mg_probe_gradnoise.py --dry-run
    $MG_PY code/mg_probe_gradnoise.py            # bs 8 与 32 各 120 步，约 15 min GPU
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
sys.path.insert(0, str(HERE))

DATASET = "mix60f120r"
PROBE_LR = "1e-6"
PROBE_DECAY_LR = "1e-8"
GRDN_RE = re.compile(r"\bgrdn:([-+0-9.eE]+)")
UPDT_RE = re.compile(r"\bupdt_s:([-+0-9.eE]+)")


# ─────────────────────────── 纯函数（全部有自测钉子）───────────────────────────
def parse_grdn(text: str, drop: int = 0) -> list[float]:
    """按出现顺序抓所有 `grdn:` 值（log_freq=1 ⇒ 一行一步）。

    只认同时含 `updt_s:` 的行（= lerobot 的 INFO 行），进度条不入表。
    """
    out = []
    for line in text.splitlines():
        if "updt_s:" not in line:
            continue
        m = GRDN_RE.search(line)
        if not m:
            continue
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out[drop:] if drop else out


def fit_noise_model(pairs: list[tuple[int, float]]) -> dict:
    """最小二乘解 `m = G + C·(1/b)`；pairs = [(batch, mean(grdn²)), ...]。

    返回 G（真梯度范数²）、C（噪声系数）、以及每个 batch 的 η_b 与拟合残差。
    两点时是精确解；三点以上才有残差可看（模型是否真是 1/b）。
    ⚠️ G 解出负数 ⇒ 测量不自洽（噪声项不足以解释差值），标 `g_negative=True`，
       此时 η 无意义，**不得**用来做「机理成立/不成立」的判定。
    """
    if len(pairs) < 2:
        return {"ok": False, "reason": "至少需要 2 个 batch", "n_points": len(pairs)}
    xs = [1.0 / b for b, _ in pairs]
    ys = [m for _, m in pairs]
    n = len(xs)
    xb, yb = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - xb) ** 2 for x in xs)
    if den == 0:
        return {"ok": False, "reason": "所有 batch 相同", "n_points": n}
    C = sum((x - xb) * (y - yb) for x, y in zip(xs, ys)) / den
    G = yb - C * xb
    eta = {}
    for b, m in pairs:
        eta[b] = ((C / b) / m) if m > 0 else float("nan")
    pred = {b: G + C / b for b, _ in pairs}
    resid = {b: (m - pred[b]) / m if m else float("nan") for b, m in pairs}
    return {"ok": True, "n_points": n, "G": G, "C": C, "g_negative": G <= 0,
            "eta": eta, "pred": pred, "rel_resid": resid,
            "norm_excess": {b: ((m / G) ** 0.5 - 1.0) if G > 0 and m > 0 else float("nan")
                            for b, m in pairs}}


def eta_branch(eta8: float) -> tuple[str, str]:
    """按 `runs/S7_PREREG.md` §3 格 7A-2 的预注册判据分支（阈值写死在这里，跑前就定了）。"""
    if eta8 != eta8:  # nan
        return "NA", "η₈ 不是数 ⇒ 判据不适用，先看 fit 是否 ok"
    if eta8 >= 0.40:
        return "MECH_YES", "η₈ ≥ 0.40 ⇒ H7 机理成立，7B 照发（噪声是主导项）"
    if eta8 >= 0.15:
        return "MECH_PART", ("0.15 ≤ η₈ < 0.40 ⇒ 方向对但不主导，7B 照发；"
                             "判定里必须写明「即使 7B 成功，也不能把功劳全归给梯度噪声」")
    return "MECH_NO", "η₈ < 0.15 ⇒ H7 机理不成立 ⇒ **7B 暂缓**，转备择假设 A1/A3"


def drift_check(vals: list[float], head: int = 10, tail: int = 10) -> dict:
    """哨兵：lr=1e-6 下参数应该几乎不动 ⇒ 首尾窗口的 grdn 均值应接近。

    漂移 >20% ⇒ 参数走远了，两个 batch 测的不是同一个点 ⇒ 该次测量作废（`usable=False`）。
    """
    if len(vals) < head + tail:
        return {"usable": False, "reason": f"点数不足（{len(vals)} < {head + tail}）"}
    h = statistics.fmean(vals[:head])
    t = statistics.fmean(vals[-tail:])
    rel = abs(t - h) / h if h else float("nan")
    return {"head_mean": h, "tail_mean": t, "rel_drift": rel,
            "usable": (rel == rel and rel <= 0.20), "reason": ("漂移 ≤20%" if rel <= 0.20 else "漂移 >20%")}


def build_cmd(bs: int, steps: int, out_dir: Path, seed: int) -> list[str]:
    """与 `code/mg_probe_batch.build_cmd` 同构，差异只有三处（都是本探针的必需项）：
    `--log_freq=1`（拿逐步值）、`optimizer_lr=1e-6` + `scheduler_decay_lr=1e-8`（冻住参数点）。
    """
    return [
        "lerobot-train",
        f"--dataset.repo_id={DATASET}",
        f"--dataset.root={MG / 'data' / DATASET}",
        f"--batch_size={bs}",
        f"--steps={steps}",
        f"--num_workers={int(os.environ.get('MG_PROBE_WORKERS', 8))}",
        f"--seed={seed}",
        "--save_freq=-1",
        "--log_freq=1",
        "--eval_freq=-1",
        f"--output_dir={out_dir}",
        f"--job_name=s7a2_gradnoise_bs{bs}",
        "--wandb.enable=false",
        "--save_checkpoint=false",
        f"--policy.path={MG / 'weights' / 'pi05_base_lr044'}",
        "--policy.dtype=bfloat16",
        "--policy.gradient_checkpointing=true",
        "--policy.chunk_size=50",
        "--policy.n_action_steps=50",
        "--policy.device=cuda",
        "--policy.push_to_hub=false",
        "--policy.scheduler_warmup_steps=200",
        "--dataset.use_imagenet_stats=true",
        f"--policy.optimizer_lr={PROBE_LR}",
        f"--policy.scheduler_decay_lr={PROBE_DECAY_LR}",
    ]


def run_one(bs: int, steps: int, drop: int, root: Path, seed: int, dry: bool = False) -> dict:
    name = f"gradnoise_bs{bs}"
    out_dir = root / name
    cmd = build_cmd(bs, steps, out_dir, seed)
    rec: dict = {"config": name, "batch_size": bs, "steps": steps, "drop": drop, "cmd": cmd,
                 "started_at": datetime.now().isoformat(timespec="seconds")}
    if dry:
        rec["status"] = "DRY"
        return rec
    if out_dir.exists():
        shutil.rmtree(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / f"{name}.log"
    with open(log_path, "w") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=dict(os.environ), cwd=str(MG))
    text = log_path.read_text(errors="ignore")
    raw = parse_grdn(text)
    vals = raw[drop:]
    rec.update({"rc": proc.returncode, "log": str(log_path), "n_raw": len(raw), "n_used": len(vals),
                "oom": ("CUDA out of memory" in text) or ("OutOfMemoryError" in text)})
    if vals:
        rec["mean_grdn"] = statistics.fmean(vals)
        rec["mean_grdn_sq"] = statistics.fmean([v * v for v in vals])
        rec["sd_grdn"] = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        rec["cv_grdn"] = (rec["sd_grdn"] / rec["mean_grdn"]) if rec["mean_grdn"] else float("nan")
        rec["drift"] = drift_check(vals)
    rec["status"] = ("OOM" if rec["oom"] else
                     "OK" if proc.returncode == 0 and len(vals) >= 10 else "FAILED")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    return rec


def write_report(root: Path, recs: list[dict], fit: dict, meta: dict) -> Path:
    L = ["# 档 7A-2 · 逐步梯度噪声探针（`E‖g_b‖² = G + C/b`）", "",
         f"生成时间：{datetime.now().strftime('%F %T')}（`code/mg_probe_gradnoise.py`）", "",
         "> 预注册出处：`runs/S7_PREREG.md` §3 格 7A-2（判据阈值在跑之前就写死在那份文件里）。",
         "> 本文件只出**机理常数**，不出成功率判定。", "",
         f"- `--log_freq=1` ⇒ `grdn` 是 AverageMeter 窗长 1 步 = **逐步**值"
         f"（出处 `lerobot/scripts/lerobot_train.py:377`）",
         f"- `grdn` = `clip_grad_norm_` 的返回值 = **裁剪前**总范数"
         f"（出处 `lerobot/scripts/lerobot_train.py:126-130`）",
         f"- `optimizer_lr={PROBE_LR}` + `scheduler_decay_lr={PROBE_DECAY_LR}` ⇒ 参数几乎不动，"
         f"两个 batch 测的是**同一个参数点**（基座）附近的梯度",
         f"- 每配置 steps={meta['steps']}、丢前 {meta['drop']} 步、seed={meta['seed']}、"
         f"数据集 `data/{DATASET}`、基座 `weights/pi05_base_lr044`、grad-ckpt on、bf16", "",
         "## 一、逐配置读数", "",
         "| 配置 | batch | 状态 | 用到点数 | mean grdn | **mean grdn²** | sd | CV | 首10/末10 漂移 | 可用? |",
         "|:--|---:|:--|---:|---:|---:|---:|---:|:--|:--|"]
    for r in recs:
        d = r.get("drift") or {}
        L.append(f"| `{r['config']}` | {r['batch_size']} | {r.get('status')} | {r.get('n_used', 0)} | "
                 f"{r.get('mean_grdn', float('nan')):.4f} | **{r.get('mean_grdn_sq', float('nan')):.4f}** | "
                 f"{r.get('sd_grdn', float('nan')):.4f} | {r.get('cv_grdn', float('nan')):.4f} | "
                 f"{d.get('rel_drift', float('nan')):.2%}（{d.get('reason', '—')}） | "
                 f"{'✅' if d.get('usable') else '❌'} |")
    L += ["", "## 二、解 `E‖g_b‖² = G + C/b`", ""]
    if not fit.get("ok"):
        L += [f"- 拟合失败：{fit.get('reason')}"]
    else:
        L += [f"- 点数 = {fit['n_points']}（2 点是精确解，>2 点才有残差可看模型是否真是 1/b）",
              f"- **G = {fit['G']:.6f}**（真/全批量梯度范数² ⇒ ‖ḡ‖ ≈ {math.sqrt(max(fit['G'],0)):.4f}）",
              f"- **C = {fit['C']:.6f}**（噪声系数；每步噪声贡献 = C/b）",
              f"- G ≤ 0 ? **{fit['g_negative']}**（若 True ⇒ 测量不自洽，η 无意义、判据不适用）", "",
              "| batch | 实测 mean grdn² | 拟合值 | 相对残差 | C/b（噪声项） | **η_b（噪声占比）** | ‖g‖ 相对超出真值 |",
              "|---:|---:|---:|---:|---:|---:|---:|"]
        for b in sorted(fit["eta"]):
            m = next((r["mean_grdn_sq"] for r in recs if r["batch_size"] == b), float("nan"))
            L.append(f"| {b} | {m:.6f} | {fit['pred'][b]:.6f} | {fit['rel_resid'][b]:+.2%} | "
                     f"{fit['C']/b:.6f} | **{fit['eta'][b]:.2%}** | {fit['norm_excess'][b]:+.2%} |")
    L += ["", "## 三、预注册判据（阈值出自 `runs/S7_PREREG.md` §3）", ""]
    if fit.get("ok") and not fit["g_negative"] and 8 in fit["eta"]:
        br, msg = eta_branch(fit["eta"][8])
        L += [f"- η₈ = **{fit['eta'][8]:.2%}** ⇒ 分支 **`{br}`**", f"- {msg}", ""]
        if 32 in fit["eta"]:
            L += [f"- η₃₂ = **{fit['eta'][32]:.2%}**（抬到 32 之后噪声占比降到这个水平）",
                  f"- 预测：抬 batch 8→32 把每步梯度噪声贡献从 {fit['C']/8:.5f} 降到 {fit['C']/32:.5f}"
                  f"（÷4），‖g‖ 的相对超出从 {fit['norm_excess'][8]:+.1%} 降到 {fit['norm_excess'][32]:+.1%}"]
        L += ["", "- ⚠️ 这只是 **H7 的必要条件**：η₈ 大说明「batch 8 的每步梯度被噪声主导」，",
              "  但**不保证**「降噪声就能降 run 间成功率方差」——中间还隔着 §1.3 那个",
              "  「loss ≈ 0.028 的简并解族」。真正检验 H7 的是格 7B 的配对符号检验（M1）。"]
    else:
        L += ["- 拟合不可用（点数不足 / G ≤ 0）⇒ **判据不适用**，不得据本文件决定 7B 发不发。",
              "- 处置：检查 drift 哨兵与 OOM 状态；必要时加大 steps 或换 batch 组合重测。"]
    bad = [r["config"] for r in recs if not (r.get("drift") or {}).get("usable", False)]
    L += ["", f"- 漂移哨兵不通过的配置：{', '.join(bad) if bad else '无'}"
          + ("（⇒ 参数走远了，η 不可信）" if bad else "（⇒ lr=1e-6 确实冻住了参数点）"),
          "", "## 四、复现", "", "```bash",
          "$MG_PY code/mg_probe_gradnoise.py --selftest",
          "$MG_PY code/mg_probe_gradnoise.py --dry-run",
          "$MG_PY code/mg_probe_gradnoise.py      # bs 8 与 32 各 120 步，约 15 min GPU", "```", ""]
    out = root / "gradnoise.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return out


import math  # noqa: E402  （write_report 里用到；放这里避免顶部与 sys.path 设置交错）


# ─────────────────────────── 自测 ───────────────────────────
def selftest() -> int:
    ok = bad = 0

    def chk(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ {name} {detail}")

    # --- parse_grdn ---
    ln = ("INFO 2026-10-03 05:14:06 ot_train.py:435 step:22K smpl:176K ep:682 epch:3.79 "
          "loss:0.027 grdn:0.152 lr:2.5e-06 updt_s:1.366 data_s:0.004")
    chk("真日志行抓到 grdn", parse_grdn(ln) == [0.152])
    chk("进度条不入表", parse_grdn("Training: 100%|█| 120/120 [09:00<00:00, 4.50s/step]") == [])
    chk("多行按顺序", parse_grdn(ln + "\n" + ln.replace("grdn:0.152", "grdn:0.200")) == [0.152, 0.200])
    chk("drop 生效", parse_grdn(ln + "\n" + ln.replace("grdn:0.152", "grdn:0.2"), drop=1) == [0.2])
    chk("drop 超过长度 ⇒ 空", parse_grdn(ln, drop=5) == [])
    chk("科学计数法", parse_grdn(ln.replace("grdn:0.152", "grdn:1.5e-03")) == [1.5e-03])
    chk("缺 grdn 的行跳过", parse_grdn("INFO step:1 epch:0.1 loss:0.5 updt_s:1.0 data_s:0.0") == [])
    chk("非数值 grdn 跳过", parse_grdn("INFO grdn:nan-tag epch:1 loss:1 updt_s:1 data_s:0") == [])
    chk("空文本 ⇒ 空", parse_grdn("") == [])

    # --- fit_noise_model：人造真值反解 ---
    G0, C0 = 0.2, 1.6   # 刻意挑成 η₈=0.50 / η₃₂=0.20，便于手算对账
    mk = lambda b: G0 + C0 / b  # noqa: E731
    f = fit_noise_model([(8, mk(8)), (32, mk(32))])
    chk("两点精确解：ok", f["ok"] is True)
    chk("两点精确解：G 还原", abs(f["G"] - G0) < 1e-12, f"G={f['G']}")
    chk("两点精确解：C 还原", abs(f["C"] - C0) < 1e-12, f"C={f['C']}")
    chk("η₈ = (C/8)/m₈", abs(f["eta"][8] - (C0 / 8) / mk(8)) < 1e-12)
    chk("η₈ 数值 = 0.5", abs(f["eta"][8] - 0.5) < 1e-12, f"η₈={f['eta'][8]}")
    chk("η₃₂ = 0.2", abs(f["eta"][32] - 0.2) < 1e-12, f"η₃₂={f['eta'][32]}")
    chk("两点残差为 0", all(abs(v) < 1e-12 for v in f["rel_resid"].values()))
    chk("norm_excess = sqrt(m/G)-1", abs(f["norm_excess"][8] - (math.sqrt(mk(8) / G0) - 1)) < 1e-12)
    chk("g_negative=False", f["g_negative"] is False)
    f3 = fit_noise_model([(8, mk(8)), (16, mk(16)), (32, mk(32))])
    chk("三点且模型正确 ⇒ G/C 仍还原", abs(f3["G"] - G0) < 1e-12 and abs(f3["C"] - C0) < 1e-12)
    chk("三点残差 ≈ 0", max(abs(v) for v in f3["rel_resid"].values()) < 1e-12)
    chk("三点 n_points=3", f3["n_points"] == 3)
    fbad = fit_noise_model([(8, 0.10), (32, 0.12)])   # 大 batch 反而更大 ⇒ C<0 ⇒ G>m
    chk("C<0 时不崩", fbad["ok"] is True)
    chk("C<0 被记下来", fbad["C"] < 0)
    # G = (4·m₃₂ − m₈)/3 ⇒ G ≤ 0 ⟺ m₃₂ ≤ m₈/4（噪声极端主导时才会出现）
    fneg = fit_noise_model([(8, 0.40), (32, 0.05)])
    chk("G ≤ 0 ⇒ g_negative=True", fneg["g_negative"] is True)
    chk("G ≤ 0 的构造条件 m₃₂ ≤ m₈/4 已复核", abs(fneg["G"] - (4*0.05 - 0.40)/3) < 1e-12)
    fpos = fit_noise_model([(8, 0.40), (32, 0.11)])
    chk("m₃₂ 略大于 m₈/4 ⇒ G > 0（边界两侧都对）", fpos["g_negative"] is False)
    chk("单点 ⇒ ok=False", fit_noise_model([(8, 0.1)])["ok"] is False)
    chk("空 ⇒ ok=False", fit_noise_model([])["ok"] is False)
    chk("同 batch 两点 ⇒ ok=False", fit_noise_model([(8, 0.1), (8, 0.2)])["ok"] is False)
    chk("m=0 ⇒ η 是 nan 而不是崩",
        math.isnan(fit_noise_model([(8, 0.0), (32, 0.1)])["eta"][8]))

    # --- eta_branch：阈值必须与预注册一致 ---
    chk("η₈=0.50 ⇒ MECH_YES", eta_branch(0.50)[0] == "MECH_YES")
    chk("η₈=0.40 ⇒ MECH_YES（含边界）", eta_branch(0.40)[0] == "MECH_YES")
    chk("η₈=0.399 ⇒ MECH_PART", eta_branch(0.399)[0] == "MECH_PART")
    chk("η₈=0.15 ⇒ MECH_PART（含边界）", eta_branch(0.15)[0] == "MECH_PART")
    chk("η₈=0.149 ⇒ MECH_NO", eta_branch(0.149)[0] == "MECH_NO")
    chk("η₈=0 ⇒ MECH_NO", eta_branch(0.0)[0] == "MECH_NO")
    chk("η₈=1 ⇒ MECH_YES（全是噪声）", eta_branch(1.0)[0] == "MECH_YES")
    chk("nan ⇒ NA", eta_branch(float("nan"))[0] == "NA")
    chk("MECH_NO 的文案含「7B 暂缓」", "7B 暂缓" in eta_branch(0.01)[1])
    chk("MECH_PART 的文案含「不能把功劳全归给」", "不能把功劳全归给" in eta_branch(0.2)[1])

    # --- drift_check ---
    d = drift_check([1.0] * 20)
    chk("常数序列漂移 0 ⇒ usable", d["usable"] and d["rel_drift"] == 0.0)
    d2 = drift_check([1.0] * 10 + [1.5] * 10)
    chk("漂移 50% ⇒ 不可用", d2["usable"] is False and abs(d2["rel_drift"] - 0.5) < 1e-12)
    d3 = drift_check([1.0] * 10 + [1.1] * 10)
    chk("漂移 10% ⇒ 可用", d3["usable"] is True)
    d4 = drift_check([1.0] * 10 + [0.8] * 10)
    chk("下降 20% ⇒ 边界可用", d4["usable"] is True)
    d5 = drift_check([1.0] * 10 + [0.7] * 10)
    chk("下降 30% ⇒ 不可用", d5["usable"] is False)
    chk("点数不足 ⇒ 不可用且有 reason", drift_check([1.0, 2.0])["usable"] is False)
    chk("首窗均值为 0 ⇒ 不炸", "rel_drift" in drift_check([0.0] * 10 + [1.0] * 10))

    # --- build_cmd ---
    c = build_cmd(32, 120, Path("/tmp/x/gn_bs32"), 2000)
    j = " ".join(c)
    chk("log_freq=1（逐步值的关键）", "--log_freq=1" in j)
    chk("lr 压到 1e-6", f"--policy.optimizer_lr={PROBE_LR}" in j)
    chk("decay_lr 压到 1e-8（避免 alpha>1 的怪调度）", f"--policy.scheduler_decay_lr={PROBE_DECAY_LR}" in j)
    chk("grad-ckpt 开（7A 实测关掉必 OOM）", "--policy.gradient_checkpointing=true" in j)
    chk("不存权重", "--save_checkpoint=false" in j and "--save_freq=-1" in j)
    chk("基座走 pi05_base_lr044", "weights/pi05_base_lr044" in j)
    chk("chunk/n_action 50 与历史一致", "--policy.chunk_size=50" in j and "--policy.n_action_steps=50" in j)
    chk("bf16", "--policy.dtype=bfloat16" in j)
    chk("batch/steps/seed 传下去", "--batch_size=32" in j and "--steps=120" in j and "--seed=2000" in j)
    chk("数据集绝对路径", str(MG / "data" / DATASET) in j)
    chk("eval_freq=-1（评测口径唯一）", "--eval_freq=-1" in j)
    chk("warmup 只出现一次", j.count("scheduler_warmup_steps") == 1)
    chk("两个不同 batch 的命令只差 batch_size 与 job_name（单一变量，其余逐项相同）",
        [x for x in build_cmd(8, 120, Path("/tmp/x/a"), 2000)
         if x not in build_cmd(32, 120, Path("/tmp/x/a"), 2000)]
        == ["--batch_size=8", "--job_name=s7a2_gradnoise_bs8"])
    chk("反向差集同理", [x for x in build_cmd(32, 120, Path("/tmp/x/a"), 2000)
                        if x not in build_cmd(8, 120, Path("/tmp/x/a"), 2000)]
        == ["--batch_size=32", "--job_name=s7a2_gradnoise_bs32"])
    chk("命令条数相同（没有多塞 flag）",
        len(build_cmd(8, 120, Path("/tmp/x/a"), 2000)) == len(build_cmd(32, 120, Path("/tmp/x/a"), 2000)))

    # --- write_report 端到端（造数）---
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        recs = [{"config": "gradnoise_bs8", "batch_size": 8, "status": "OK", "n_used": 100,
                 "mean_grdn": math.sqrt(mk(8)), "mean_grdn_sq": mk(8), "sd_grdn": 0.05,
                 "cv_grdn": 0.2, "drift": drift_check([1.0] * 20)},
                {"config": "gradnoise_bs32", "batch_size": 32, "status": "OK", "n_used": 100,
                 "mean_grdn": math.sqrt(mk(32)), "mean_grdn_sq": mk(32), "sd_grdn": 0.02,
                 "cv_grdn": 0.1, "drift": drift_check([1.0] * 20)}]
        fit = fit_noise_model([(8, mk(8)), (32, mk(32))])
        p = write_report(Path(td), recs, fit, {"steps": 120, "drop": 20, "seed": 2000})
        txt = p.read_text()
        chk("报告落盘非空", len(txt) > 800)
        chk("报告含 G 与 C", "**G = " in txt and "**C = " in txt)
        chk("报告含预注册分支 MECH_YES", "MECH_YES" in txt)
        chk("报告含漂移哨兵结论", "漂移哨兵" in txt)
        chk("报告标明只是必要条件", "必要条件" in txt)
        fit2 = fit_noise_model([(8, 0.40), (32, 0.05)])   # G ≤ 0 的构造
        txt2 = write_report(Path(td), recs, fit2, {"steps": 1, "drop": 0, "seed": 1}).read_text()
        chk("G≤0 时报告写「判据不适用」", "判据不适用" in txt2)
        txt3 = write_report(Path(td), recs, {"ok": False, "reason": "点数不足"},
                            {"steps": 1, "drop": 0, "seed": 1}).read_text()
        chk("fit 失败时报告不崩且写明", "拟合失败" in txt3)

    print(f"[selftest] {ok} passed, {bad} failed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batches", default="8,32")
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--drop", type=int, default=20, help="丢掉前 N 步（首批 dataloader/autotune 预热）")
    ap.add_argument("--seed", type=int, default=2000)
    ap.add_argument("--out", default=str(MG / "runs" / "s7_probe"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    bss = [int(x) for x in args.batches.split(",") if x.strip()]
    meta = {"steps": args.steps, "drop": args.drop, "seed": args.seed, "batches": bss,
            "probe_lr": PROBE_LR, "probe_decay_lr": PROBE_DECAY_LR,
            "started_at": datetime.now().isoformat(timespec="seconds")}
    print(f"[s7a2] batches={bss} steps={args.steps} drop={args.drop} lr={PROBE_LR} -> {root}")

    recs = []
    for bs in bss:
        print(f"[s7a2] === 跑 bs{bs}（log_freq=1，逐步 grdn）=== {datetime.now():%T}", flush=True)
        r = run_one(bs, args.steps, args.drop, root, args.seed, dry=args.dry_run)
        print(f"[s7a2]   status={r.get('status')} rc={r.get('rc')} n_used={r.get('n_used')} "
              f"mean_grdn={r.get('mean_grdn')} mean_grdn_sq={r.get('mean_grdn_sq')} "
              f"drift={ (r.get('drift') or {}).get('rel_drift') }", flush=True)
        recs.append(r)

    pairs = [(r["batch_size"], r["mean_grdn_sq"]) for r in recs
             if r.get("status") == "OK" and r.get("mean_grdn_sq") is not None]
    fit = fit_noise_model(pairs)
    if fit.get("ok"):
        print(f"[s7a2] 拟合：G={fit['G']:.6f}  C={fit['C']:.6f}  g_negative={fit['g_negative']}")
        for b in sorted(fit["eta"]):
            print(f"[s7a2]   η_{b} = {fit['eta'][b]:.2%}")
        if not fit["g_negative"] and 8 in fit["eta"]:
            br, msg = eta_branch(fit["eta"][8])
            print(f"[s7a2] 预注册分支 = {br}：{msg}")
    else:
        print(f"[s7a2] 拟合不可用：{fit.get('reason')}")

    md = write_report(root, recs, fit, meta)
    (root / "gradnoise.json").write_text(json.dumps(
        {"meta": meta, "records": recs, "fit": fit,
         "branch": (eta_branch(fit["eta"][8])[0] if fit.get("ok") and not fit.get("g_negative")
                    and 8 in fit.get("eta", {}) else "NA"),
         "finished_at": datetime.now().isoformat(timespec="seconds")},
        indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[s7a2] 报告 -> {md}")
    print(f"[s7a2] 原始 -> {root / 'gradnoise.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
