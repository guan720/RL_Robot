#!/usr/bin/env python
"""档 7A · batch / gradient-checkpointing 的**计时与显存**探针（只出常数，不出判定）。

为什么要这一档（坑 57 的处方第一步）：
  档 3r 三个训练 seed 用**同一份数据、同一套超参、等 epoch**，反向放宽口径 =
  41.2% / 68.8% / 80.0% ⇒ 极差 38.8 pp、sd≈20 pp。这个 run 间方差比任何一条已知杠杆
  的效应都大（数据量那条只有 +15 pp、Fisher p=0.0801）⇒ n=1 的配方比较在数学上不可能出结论。
  头号嫌疑 = **batch 8 太小**：π₀.₅ 是 flow-matching 目标，每个样本还要额外抽一次噪声水平 t
  和一次 ε，batch 8 时每步梯度的蒙特卡洛噪声极大；而 81 GB 的卡只用了一小部分。
  在决定「烧 3×(5~9) h 训大 batch」之前，必须先把**代价**量出来：s/step 与峰值显存。

本工具**不跑仿真、不评成功率、不下结论**。它只做三件事：
  1) 逐配置跑 `--steps N` 的真训练（真数据、真基座、真命令行），从 lerobot 的 INFO 行里
     取 `updt_s`（AverageMeter，见 lerobot/scripts/lerobot_train.py:379）；
  2) 后台 1 Hz 采 `nvidia-smi memory.used`，记峰值；
  3) 按**等 epoch**（3.79 ep）反推每个配置的总步数、save_freq（保证 `last` == steps，
     且 11 格的 epoch 网格与档 2e/3r 的 batch8 网格**逐格相同**），投影墙钟。

产物：`runs/s7_probe/timing.{json,md}` + 每配置一份 `bs<BS>_gc<0|1>/train.log`。

纪律：
  * 输出目录一律在 `runs/s7_probe/` 下，不碰任何历史 run（房规：产物新建文件夹）。
  * 每个配置跑完就 `rm -rf` 自己的输出目录（只删本工具建的、路径写死在 s7_probe 下），
    免得 lerobot 的「output_dir 已存在就拒绝」把第二次跑挡掉，也免得堆几十 GB 废权重。
  * 峰值显存来自**真进程**的 nvidia-smi 读数，不是估算（坑 52/55：机理常数不许来自桩件）。
  * 某配置 OOM 或退出码非 0 ⇒ 记 `status=FAILED` 并继续下一个，不 die（探针的目的是画可行域）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_batch.py --dry-run'
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_batch.py'          # 跑默认 5 个配置
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_batch.py --selftest'
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
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
sys.path.insert(0, str(HERE))

DATASET = "mix60f120r"
FRAMES = 46426                 # 出处 data/mix60f120r/meta/info.json: total_frames（下面 preflight 会复核）
TARGET_EPOCHS = 3.79           # 与档 2 / 2c / 2e / 3r 同一个 epoch 预算
N_CELLS = 11                   # 档 2e/3r 的 val 网格是 11 格；这里保证新 batch 也是 11 格且 epoch 逐格对齐
BASE_LR = "1e-4"
WARMUP = 200
DECAY_STEPS_DEFAULT = 30_000   # 出处 lerobot/policies/pi05/configuration_pi05.py:95
UPDT_RE = re.compile(r"step:(\S+)\s+smpl:\S+\s+ep:\d+\s+epch:\S+\s+loss:([-\d.eE+]+)\s+grdn:([-\d.eE+]+)\s+lr:(\S+)\s+updt_s:([-\d.eE+]+)\s+data_s:([-\d.eE+]+)")


# ─────────────────────────── 纯函数（全部有自测钉子）───────────────────────────
def parse_updt(log_text: str) -> list[dict]:
    """从 train.log 抓所有 INFO 行的 (step, loss, grdn, lr, updt_s, data_s)。

    tqdm 的进度条会把整行冲掉，但 INFO 行是独立写的；只认 INFO 行，避免把进度条里的
    `1.35s/step`（含首步 warmup 的累计平均）当成稳态速度。
    """
    out = []
    for line in log_text.splitlines():
        m = UPDT_RE.search(line)
        if not m:
            continue
        out.append({
            "step_raw": m.group(1),
            "loss": float(m.group(2)),
            "grdn": float(m.group(3)),
            "lr_s": m.group(4),
            "updt_s": float(m.group(5)),
            "data_s": float(m.group(6)),
        })
    return out


def steady_updt(rows: list[dict], drop: int = 2) -> dict:
    """丢掉前 `drop` 个记录点（cudnn autotune / 首批 dataloader 预热），取剩下的中位数。

    用中位数不用均值：档 3r 的日志里 updt_s 偶发 1.677（对比稳态 1.36），均值会被这种毛刺拖高。
    """
    vals = [r["updt_s"] for r in rows[drop:]] or [r["updt_s"] for r in rows]
    if not vals:
        return {"n": 0, "median": float("nan"), "min": float("nan"), "max": float("nan")}
    return {"n": len(vals), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals)}


def equal_epoch_plan(frames: int, bs: int, target_epochs: float, n_cells: int) -> dict:
    """等 epoch 的步数 + save_freq（要求：steps 是 save_freq 的整数倍 ⇒ lerobot 的 `last` == steps）。

    为什么要凑 n_cells 格：档 2e/3r 的 batch8 网格是 steps 2000..22000（11 格），
    每格 = 2000/5803.25 = 0.3447 epoch。新 batch 必须落在**同一组 epoch 点**上，
    否则 mg_epoch_curve.py 的对表要靠「最近邻」凑，读出来的差就混进了网格错位。
    做法：steps = round(spe*ep) 再取整到 save_freq；save_freq = steps/n_cells 取整到 50 的倍数。
    """
    spe = frames / bs
    if spe <= 0:
        return {"batch_size": bs, "steps_per_epoch": 0.0, "raw_steps": 0.0, "save_freq": 50,
                "steps": 0, "epochs": 0.0, "cell_epoch": 0.0, "n_cells": 0}
    raw = spe * target_epochs
    steps0 = int(round(raw))
    sf = max(50, int(round(steps0 / n_cells / 50.0)) * 50)
    steps = int(round(steps0 / sf)) * sf
    return {"batch_size": bs, "steps_per_epoch": round(spe, 4), "raw_steps": round(raw, 1),
            "save_freq": sf, "steps": steps, "epochs": round(steps / spe, 4),
            "cell_epoch": round(sf / spe, 4), "n_cells": steps // sf}


def lr_autoscale(steps: int, warmup: int = WARMUP, decay: int = DECAY_STEPS_DEFAULT) -> dict:
    """复现 lerobot `CosineDecayWithWarmupSchedulerConfig.build` 的自动缩放（optim/schedulers.py:99-104）。

    为什么要复现：**改 batch ⇒ 等 epoch 的 steps 变 ⇒ LR 调度形状变**，这是一个隐形混淆。
    复现之后可以对账「warmup 占全程的比例」在不同 steps 下是否守恒 —— 若守恒，
    则等 epoch 比较里 LR 调度不是混淆项，可以放心只把 batch 当唯一变量。
    实测对账锚：steps=22000 时 lerobot 日志打印 `Scaling warmup: 200 → 146`（真产物，非桩件）。
    """
    if steps < decay:
        scale = steps / decay
        aw = int(warmup * scale)
        ad = steps
    else:
        scale, aw, ad = 1.0, warmup, decay
    return {"steps": steps, "scale_factor": round(scale, 6), "actual_warmup": aw,
            "actual_decay": ad, "warmup_frac_pct": round(100.0 * aw / max(1, steps), 4)}


def project_wall(steps: int, updt_s: float) -> dict:
    """墙钟投影：只算 updt_s（data_s 实测 0.004 s，占 0.3%，可忽略但要写明）。"""
    sec = steps * updt_s
    return {"sec": round(sec, 1), "hhmm": f"{int(sec // 3600)}h{int((sec % 3600) // 60):02d}m"}


# ─────────────────────────── 真跑 ───────────────────────────
def gpu_mem_mib() -> int:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout.strip().splitlines()
        return int(out[0]) if out else -1
    except Exception:  # noqa: BLE001
        return -1


class MemPoller:
    def __init__(self, hz: float = 1.0):
        self.hz, self.peak, self.samples, self._stop = hz, -1, [], threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            m = gpu_mem_mib()
            if m >= 0:
                self.samples.append(m)
                self.peak = max(self.peak, m)
            self._stop.wait(1.0 / self.hz)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)
        return False


def build_cmd(bs: int, gcpt: bool, steps: int, log_freq: int, out_dir: Path, seed: int) -> list[str]:
    """与 code/mg_train.py 的 pi05 分支**逐项对齐**（DEFAULTS['pi05'] + 档 2e 的两个 --extra）。

    唯一差异：steps/log_freq/save_freq 是探针口径，save_checkpoint=false（探针不要权重）。
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
        f"--log_freq={log_freq}",
        "--eval_freq=-1",
        f"--output_dir={out_dir}",
        f"--job_name=s7probe_bs{bs}_gc{int(gcpt)}",
        "--wandb.enable=false",
        "--save_checkpoint=false",
        f"--policy.path={MG / 'weights' / 'pi05_base_lr044'}",
        "--policy.dtype=bfloat16",
        f"--policy.gradient_checkpointing={'true' if gcpt else 'false'}",
        "--policy.chunk_size=50",
        "--policy.n_action_steps=50",
        "--policy.device=cuda",
        "--policy.push_to_hub=false",
        f"--policy.scheduler_warmup_steps={WARMUP}",
        "--dataset.use_imagenet_stats=true",
        f"--policy.optimizer_lr={BASE_LR}",
    ]


def run_one(bs: int, gcpt: bool, steps: int, log_freq: int, root: Path, seed: int,
            dry: bool = False) -> dict:
    name = f"bs{bs}_gc{int(gcpt)}"
    out_dir = root / name
    cmd = build_cmd(bs, gcpt, steps, log_freq, out_dir, seed)
    rec: dict = {"config": name, "batch_size": bs, "grad_ckpt": gcpt, "steps": steps,
                 "cmd": cmd, "started_at": datetime.now().isoformat(timespec="seconds")}
    if dry:
        rec["status"] = "DRY"
        return rec
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    log_path = root / f"{name}.log"
    t0 = time.time()
    with MemPoller() as poll, open(log_path, "w") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                              env=dict(os.environ), cwd=str(MG))
    rec["wall_s"] = round(time.time() - t0, 1)
    rec["rc"] = proc.returncode
    rec["peak_mem_mib"] = poll.peak
    rec["mem_samples"] = len(poll.samples)
    rec["log"] = str(log_path)
    text = log_path.read_text(errors="ignore")
    rows = parse_updt(text)
    rec["n_info_rows"] = len(rows)
    rec["updt"] = steady_updt(rows, drop=2)
    rec["data_s_median"] = statistics.median([r["data_s"] for r in rows]) if rows else None
    rec["loss_first_last"] = [rows[0]["loss"], rows[-1]["loss"]] if rows else None
    oom = ("CUDA out of memory" in text) or ("OutOfMemoryError" in text)
    rec["oom"] = oom
    m = re.search(r"Auto-scaling LR scheduler: num_training_steps \((\d+)\).*?warmup: (\d+) → (\d+), decay: (\d+) → (\d+)", text)
    rec["lr_autoscale_log"] = ({"steps": int(m.group(1)), "warmup_from": int(m.group(2)),
                                "warmup_to": int(m.group(3)), "decay_from": int(m.group(4)),
                                "decay_to": int(m.group(5))} if m else None)
    rec["status"] = "OOM" if oom else ("OK" if proc.returncode == 0 and rows else "FAILED")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    return rec


def write_md(root: Path, recs: list[dict], plan: dict, meta: dict) -> Path:
    lines = [
        "# 档 7A · batch / gradient-checkpointing 计时与显存探针",
        "",
        f"生成时间：{datetime.now().strftime('%F %T')}（`code/mg_probe_batch.py`）",
        "",
        "> 这是**代价探针**，不是判定。它回答的是「把 batch 抬上去要花多少墙钟、多少显存」，",
        "> 以便档 7B 在发车前就能算出预算（坑 53/57 的房规：发车前先算足迹与方差）。",
        "> s/step 取 lerobot INFO 行的 `updt_s`（AverageMeter，出处 "
        "`lerobot/scripts/lerobot_train.py:379`），丢前 2 个记录点后取中位数；",
        "> 峰值显存是探针进程在跑时 1 Hz 采 `nvidia-smi memory.used` 的最大值（真读数，非估算）。",
        "",
        f"- 数据集：`data/{DATASET}`，total_frames = **{meta['frames']}**（探针启动时从 info.json 复核）",
        f"- 等 epoch 预算：**{TARGET_EPOCHS} ep**（照抄档 2e/3r）；基座 `weights/pi05_base_lr044`",
        f"- lr {BASE_LR} / warmup {WARMUP} / chunk_size 50 / bf16 / 探针 steps={meta['probe_steps']}",
        f"- 探针 seed = {meta['seed']}（所有配置同一个，只为计时，不做配方比较）",
        "",
        "## 一、实测",
        "",
        "| 配置 | batch | grad-ckpt | 状态 | updt_s 中位 | updt_s 区间 | n | data_s 中位 | 峰值显存 MiB | 探针墙钟 |",
        "|:--|---:|:--|:--|---:|:--|---:|---:|---:|---:|",
    ]
    for r in recs:
        u = r.get("updt") or {}
        med = f"{u.get('median'):.3f}" if isinstance(u.get("median"), float) and u.get("n") else "—"
        rng = (f"[{u['min']:.3f}, {u['max']:.3f}]" if u.get("n") else "—")
        ds = f"{r['data_s_median']:.4f}" if r.get("data_s_median") else "—"
        wall = f"{r.get('wall_s', float('nan')):.0f}s" if r.get("wall_s") else "—"
        lines.append(f"| `{r['config']}` | {r['batch_size']} | {'on' if r['grad_ckpt'] else 'off'} | "
                     f"{r.get('status')} | {med} | {rng} | {u.get('n', 0)} | {ds} | "
                     f"{r.get('peak_mem_mib', '—')} | {wall} |")
    lines += ["", "## 二、等 epoch 投影（3.79 ep，11 格 epoch 网格与 batch8 逐格相同）", "",
              "| batch | steps/epoch | 等 epoch 步数 | 实际 epoch | save_freq | 格数 | 每格 epoch | "
              "实测 updt_s | 投影墙钟 |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for bs, p in sorted(plan.items()):
        med = p.get("updt_median")
        if med:
            w = project_wall(p["steps"], med)
            lines.append(f"| {bs} | {p['steps_per_epoch']} | **{p['steps']}** | {p['epochs']} | "
                         f"{p['save_freq']} | {p['n_cells']} | {p['cell_epoch']} | {med:.3f} | "
                         f"**{w['hhmm']}** ({w['sec']:.0f}s) |")
        else:
            lines.append(f"| {bs} | {p['steps_per_epoch']} | **{p['steps']}** | {p['epochs']} | "
                         f"{p['save_freq']} | {p['n_cells']} | {p['cell_epoch']} | 无读数 | 无读数 |")
    lines += ["", "### 网格对齐自检",
              "",
              f"- batch8 历史网格：steps 2000..22000、每格 2000/5803.25 = **0.3446** epoch",
              f"- 本表各 batch 的每格 epoch：" +
              ", ".join(f"bs{bs}={p['cell_epoch']}" for bs, p in sorted(plan.items())),
              "  ⇒ 差 ≤0.001 epoch 才算对齐（`mg_epoch_curve.py --align` 用最近邻，差大了会串格）。",
              "", "## 三、LR 调度自动缩放对账（改 batch 会不会顺手改了 LR 形状）", "",
              "出处 `lerobot/optim/schedulers.py:99-104`：`steps < scheduler_decay_steps(30000)` 时",
              "`actual_warmup = int(warmup × steps/30000)`、`actual_decay = steps`。",
              "", "| steps | scale | actual_warmup | actual_decay | warmup 占全程 % | 探针日志实测 |",
              "|---:|---:|---:|---:|---:|:--|"]
    for bs, p in sorted(plan.items()):
        a = lr_autoscale(p["steps"])
        got = next((r.get("lr_autoscale_log") for r in recs
                    if r["batch_size"] == bs and r.get("lr_autoscale_log")), None)
        gs = f"warmup {got['warmup_from']}→{got['warmup_to']}, decay {got['decay_from']}→{got['decay_to']}" if got else "—"
        lines.append(f"| {p['steps']} | {a['scale_factor']} | {a['actual_warmup']} | "
                     f"{a['actual_decay']} | {a['warmup_frac_pct']} | {gs} |")
    hist = meta.get("history_lr_log")
    lines += ["", f"- 历史锚（真产物 `runs/pi05_mix60f120r_s3r_seed3000/train.log`）：`{hist}`",
              "- 结论口径：warmup 占全程的**百分比**在 steps 2750/5500/11000/22000 上近似守恒"
              "（都是 200/30000 = 0.667%），余弦衰减也都在最后一步落到 `decay_lr` ⇒",
              "  **等 epoch 换 batch 时 LR 调度不是混淆项**（这条推翻了「抬 steps 会 LR 重启」的顾虑，",
              "  但只对**新起 run** 成立；`--resume` 续训改 steps 仍会换调度总长，档 7 不用续训）。",
              "", "## 四、复现", "", "```bash",
              "bash -c 'source code/env.sh && $MG_PY code/mg_probe_batch.py --dry-run'",
              "bash -c 'source code/env.sh && $MG_PY code/mg_probe_batch.py'   # 5 配置，约 20 min GPU",
              "bash -c 'source code/env.sh && $MG_PY code/mg_probe_batch.py --selftest'", "```", ""]
    out = root / "timing.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ─────────────────────────── 自测 ───────────────────────────
def selftest() -> int:
    ok = bad = 0

    def chk(name, cond):
        nonlocal ok, bad
        if cond:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ {name}")

    # --- parse_updt：真日志格式 ---
    real = ("INFO 2026-10-03 05:14:06 ot_train.py:435 step:22K smpl:176K ep:682 epch:3.79 "
            "loss:0.027 grdn:0.152 lr:2.5e-06 updt_s:1.366 data_s:0.004")
    rows = parse_updt(real)
    chk("真日志行能解析出 1 条", len(rows) == 1)
    chk("updt_s=1.366", rows and abs(rows[0]["updt_s"] - 1.366) < 1e-9)
    chk("data_s=0.004", rows and abs(rows[0]["data_s"] - 0.004) < 1e-9)
    chk("loss=0.027", rows and abs(rows[0]["loss"] - 0.027) < 1e-9)
    chk("grdn=0.152", rows and abs(rows[0]["grdn"] - 0.152) < 1e-9)
    chk("lr 原样留字符串", rows and rows[0]["lr_s"] == "2.5e-06")
    chk("step_raw=22K", rows and rows[0]["step_raw"] == "22K")
    # 进度条不能被当成 INFO 行（坑：进度条里的 1.35s/step 含首步预热）
    bar = "Training: 100%|██████████| 21999/22000 [8:51:24<00:01,  1.35s/step]"
    chk("进度条不被解析", parse_updt(bar) == [])
    chk("混合文本只取 INFO", len(parse_updt(bar + "\n" + real)) == 1)
    chk("空文本给空表", parse_updt("") == [])
    chk("step:100（非 K 后缀）也能解析",
        len(parse_updt("INFO x step:100 smpl:800 ep:3 epch:0.02 loss:0.291 grdn:4.269 "
                       "lr:3.5e-05 updt_s:1.370 data_s:0.020")) == 1)

    # --- steady_updt：丢前 2 + 中位数 ---
    mk = lambda xs: [{"updt_s": x} for x in xs]  # noqa: E731
    s = steady_updt(mk([9.9, 9.8, 1.36, 1.37, 1.38]), drop=2)
    chk("丢前2后 n=3", s["n"] == 3)
    chk("中位数=1.37", abs(s["median"] - 1.37) < 1e-9)
    chk("min/max 只在保留段里取", abs(s["min"] - 1.36) < 1e-9 and abs(s["max"] - 1.38) < 1e-9)
    s2 = steady_updt(mk([1.5, 1.6]), drop=2)
    chk("记录点不够 drop 时退回全量", s2["n"] == 2 and abs(s2["median"] - 1.55) < 1e-9)
    chk("毛刺不拖中位数（1.677 vs 稳态 1.36）",
        abs(steady_updt(mk([1.36, 1.36, 1.677, 1.36, 1.36]), drop=0)["median"] - 1.36) < 1e-9)
    e = steady_updt([], drop=2)
    chk("空表 n=0", e["n"] == 0)

    # --- equal_epoch_plan：必须与历史 batch8 口径对账 ---
    p8 = equal_epoch_plan(46426, 8, 3.79, 11)
    chk("bs8 steps/epoch=5803.25", abs(p8["steps_per_epoch"] - 5803.25) < 1e-6)
    chk("bs8 steps=22000（历史真值）", p8["steps"] == 22000)
    chk("bs8 save_freq=2000（历史真值）", p8["save_freq"] == 2000)
    chk("bs8 格数=11", p8["n_cells"] == 11)
    chk("bs8 每格 epoch≈0.3446", abs(p8["cell_epoch"] - 0.3446) < 5e-4)
    chk("bs8 实际 epoch≈3.79", abs(p8["epochs"] - 3.79) < 0.005)
    p32 = equal_epoch_plan(46426, 32, 3.79, 11)
    chk("bs32 steps=5500", p32["steps"] == 5500)
    chk("bs32 save_freq=500", p32["save_freq"] == 500)
    chk("bs32 格数=11", p32["n_cells"] == 11)
    p16 = equal_epoch_plan(46426, 16, 3.79, 11)
    chk("bs16 steps=11000", p16["steps"] == 11000)
    chk("bs16 save_freq=1000", p16["save_freq"] == 1000)
    p64 = equal_epoch_plan(46426, 64, 3.79, 11)
    chk("bs64 steps=2750", p64["steps"] == 2750)
    chk("bs64 save_freq=250", p64["save_freq"] == 250)
    for p in (p8, p16, p32, p64):
        chk(f"bs{p['batch_size']} steps 是 save_freq 整数倍（否则 last≠steps，坑 33）",
            p["steps"] % p["save_freq"] == 0)
        chk(f"bs{p['batch_size']} 每格 epoch 与 bs8 差 ≤0.001",
            abs(p["cell_epoch"] - p8["cell_epoch"]) <= 0.001)
    chk("frames=0 时不崩（返回 steps=0）", equal_epoch_plan(0, 8, 3.79, 11)["steps"] == 0)

    # --- lr_autoscale：必须复现真日志里的 200→146 ---
    a22 = lr_autoscale(22000)
    chk("steps=22000 ⇒ actual_warmup=146（真日志锚）", a22["actual_warmup"] == 146)
    chk("steps=22000 ⇒ actual_decay=22000", a22["actual_decay"] == 22000)
    chk("steps=22000 ⇒ scale=0.7333", abs(a22["scale_factor"] - 22000 / 30000) < 1e-6)
    a55 = lr_autoscale(5500)
    chk("steps=5500 ⇒ actual_warmup=36", a55["actual_warmup"] == 36)
    chk("steps=5500 ⇒ actual_decay=5500", a55["actual_decay"] == 5500)
    a11 = lr_autoscale(11000)
    a27 = lr_autoscale(2750)
    fr = [a27["warmup_frac_pct"], a55["warmup_frac_pct"], a11["warmup_frac_pct"], a22["warmup_frac_pct"]]
    chk("warmup 占比在 2750..22000 上守恒（极差 <0.05 pp）", max(fr) - min(fr) < 0.05)
    chk("占比都≈0.667%（=200/30000）", all(abs(x - 100 * 200 / 30000) < 0.05 for x in fr))
    big = lr_autoscale(40000)
    chk("steps≥30000 时不缩放", big["actual_warmup"] == 200 and big["actual_decay"] == 30000)
    chk("steps=0 不崩", lr_autoscale(0)["actual_warmup"] == 0)

    # --- project_wall ---
    w = project_wall(22000, 1.366)
    chk("22000×1.366 = 30052 s", abs(w["sec"] - 30052.0) < 1.0)
    chk("墙钟格式 8h21m", w["hhmm"] == "8h20m" or w["hhmm"] == "8h21m")
    chk("0 步给 0h00m", project_wall(0, 1.4)["hhmm"] == "0h00m")

    # --- build_cmd：必须与 mg_train.py 的 pi05 口径逐项对齐 ---
    c = build_cmd(32, False, 5500, 10, Path("/tmp/x/bs32_gc0"), 2000)
    j = " ".join(c)
    chk("用 lerobot-train", c[0] == "lerobot-train")
    chk("基座走 pi05_base_lr044", "weights/pi05_base_lr044" in j)
    chk("bf16", "--policy.dtype=bfloat16" in j)
    chk("chunk_size=50", "--policy.chunk_size=50" in j)
    chk("n_action_steps=50", "--policy.n_action_steps=50" in j)
    chk("grad_ckpt=false 生效", "--policy.gradient_checkpointing=false" in j)
    chk("grad_ckpt=true 生效", "--policy.gradient_checkpointing=true" in " ".join(
        build_cmd(32, True, 5500, 10, Path("/tmp/x/bs32_gc1"), 2000)))
    chk("lr=1e-4", "--policy.optimizer_lr=1e-4" in j)
    chk("warmup=200（只出现一次，避免档 3r 那种重复 flag）",
        j.count("scheduler_warmup_steps") == 1)
    chk("eval_freq=-1（评测口径唯一，走 mg_eval）", "--eval_freq=-1" in j)
    chk("wandb 关", "--wandb.enable=false" in j)
    chk("探针不存权重", "--save_checkpoint=false" in j)
    chk("save_freq=-1", "--save_freq=-1" in j)
    chk("imagenet_stats 与历史一致", "--dataset.use_imagenet_stats=true" in j)
    chk("数据集绝对路径", str(MG / "data" / DATASET) in j)
    chk("seed 传下去", "--seed=2000" in j)
    chk("batch 传下去", "--batch_size=32" in j and "--steps=5500" in j)

    print(f"[selftest] {ok} passed, {bad} failed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", default="8:1,16:0,32:0,64:0,32:1",
                    help="'<batch>:<grad_ckpt 0|1>' 逗号分隔；默认先跑 batch8+ckpt 复现历史常数当锚")
    ap.add_argument("--probe-steps", type=int, default=50)
    ap.add_argument("--log-freq", type=int, default=10)
    ap.add_argument("--seed", type=int, default=2000)
    ap.add_argument("--out", default=str(MG / "runs" / "s7_probe"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    info = MG / "data" / DATASET / "meta" / "info.json"
    if not info.exists():
        print(f"[s7a] FATAL 数据集不在：{info}", file=sys.stderr)
        return 3
    frames = int(json.loads(info.read_text())["total_frames"])
    if frames != FRAMES:
        print(f"[s7a] 注意：info.json 的 total_frames={frames} 与模块常数 {FRAMES} 不一致 ⇒ 以 info.json 为准")

    hist_lr = "（未找到）"
    hl = MG / "runs" / "pi05_mix60f120r_s3r_seed3000" / "train.log"
    if hl.exists():
        m = re.search(r"Auto-scaling LR scheduler: .*", hl.read_text(errors="ignore"))
        if m:
            hist_lr = m.group(0).strip()

    cfgs = []
    for part in args.configs.split(","):
        part = part.strip()
        if not part:
            continue
        bs_s, gc_s = part.split(":")
        cfgs.append((int(bs_s), bool(int(gc_s))))

    plan = {bs: equal_epoch_plan(frames, bs, TARGET_EPOCHS, N_CELLS) for bs, _ in cfgs}
    meta = {"frames": frames, "probe_steps": args.probe_steps, "log_freq": args.log_freq,
            "seed": args.seed, "target_epochs": TARGET_EPOCHS, "history_lr_log": hist_lr,
            "started_at": datetime.now().isoformat(timespec="seconds")}
    print(f"[s7a] frames={frames}  配置={[f'{b}:{int(g)}' for b, g in cfgs]}  探针 steps={args.probe_steps}")
    for bs, p in sorted(plan.items()):
        print(f"[s7a]   bs{bs}: 等 epoch {p['steps']} 步（{p['epochs']} ep）、save_freq={p['save_freq']}、"
              f"{p['n_cells']} 格、每格 {p['cell_epoch']} ep")
    print(f"[s7a] 历史 LR 自动缩放锚：{hist_lr}")

    recs = []
    for bs, gcpt in cfgs:
        print(f"[s7a] === 跑 bs{bs} grad_ckpt={int(gcpt)} === {datetime.now():%T}", flush=True)
        r = run_one(bs, gcpt, args.probe_steps, args.log_freq, root, args.seed, dry=args.dry_run)
        u = r.get("updt") or {}
        print(f"[s7a]   status={r.get('status')} rc={r.get('rc')} updt_s={u.get('median')} "
              f"peak_mem={r.get('peak_mem_mib')}MiB wall={r.get('wall_s')}s", flush=True)
        if u.get("n"):
            plan[bs]["updt_median"] = u["median"]
            plan[bs]["projected"] = project_wall(plan[bs]["steps"], u["median"])
        recs.append(r)

    md = write_md(root, recs, plan, meta)
    (root / "timing.json").write_text(json.dumps(
        {"meta": meta, "records": recs, "plan": plan,
         "finished_at": datetime.now().isoformat(timespec="seconds")},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[s7a] 报告 -> {md}")
    print(f"[s7a] 原始 -> {root / 'timing.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
