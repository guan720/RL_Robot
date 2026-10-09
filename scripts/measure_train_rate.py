#!/usr/bin/env python
"""受控重测「Lift 训练墙钟」：同机、同窗口、串行、无并发，三个配置各测一次。

为什么必须重测（§12.11-P）：成本表里的 `train_sec_per_round=671` 是 **reach** 的实测值，
搬到接触任务上完全不对号。翻 `runs/*/result.json` 能拿到 Lift 60k 步的三个历史值 ——
42.3 / 8.9 / 5.6 步/秒，差 **7.6 倍**，足以把「6 臂 8 h」的判定从 4.4 h（买得起）
翻到 14.7 h（买不起）。但这三个值**不能归因于配置**：按 result.json 的时间戳排，
`demo5k`(16:48–18:40) 与 `demo5k_bc3k`(17:16–20:15) 的训练窗口重叠了 84 分钟，
两个慢值互相污染；只有纯 SAC 那次(16:23–16:46)是独跑的。
所以「加示范池会不会让训练慢 4.7 倍」这个问题，用现有产物回答不了，只能重测。

还有一条口径差异必须记着：历史 `train_seconds` 把**训练途中的内联评测**也算进去了
（`train_pickplace_sac.py` 的计时窗里每 eval_freq 步跑一次 evaluate），
60k 步 + eval_freq 10k + 5 局 = 30 局评测混在里面。本脚本把 `--eval-freq` 设成总步数、
`--eval-episodes 1`，让计时窗里只剩 1 局评测，得到的是接近纯训练的速率；
产物里两个口径都记，别混用。

守卫：启动前扫一遍进程，发现别的 RL 进程（train_*/probe_*/run_harness_*）在跑就**直接退出**
—— 并发正是本轮要排除的混淆项。确实要并发跑（比如故意量并发惩罚）才用 --force。

用法：
    /root/venvs/rlrobot/bin/python scripts/measure_train_rate.py
    /root/venvs/rlrobot/bin/python scripts/measure_train_rate.py --steps 20000 --configs pure demo5k
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VENV_PY = "/root/venvs/rlrobot/bin/python"
TRAINER = "scripts/train_pickplace_sac.py"

# 配置名 → 传给 trainer 的额外参数。三个配置只差示范/BC，步数与评测口径完全一致，
# 这样 sps 的差异才只能来自配置本身（或机器漂移，用 loadavg 记录）。
CONFIGS: dict[str, list[str]] = {
    "pure": ["--demo-steps", "0"],
    "demo5k": ["--demo-steps", "5000"],
    "demo5k_bc3k": ["--demo-steps", "5000", "--bc-steps", "3000"],
}
RL_PAT = ("train_pickplace_sac", "train_reach", "train_transport", "probe_", "run_harness_loop",
          "measure_train_rate")


def proc_counts() -> dict:
    """容器内 R/D 进程数。loadavg 是**宿主机**口径，只能当粗协变量（§12.11-O）。"""
    r = d = total = 0
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            state = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0]
        except (OSError, IndexError):
            continue
        total += 1
        r += state == "R"
        d += state == "D"
    return {"r": r, "d": d, "total": total}


def other_rl_procs() -> list[str]:
    """列出别的 RL 进程（排除自己）。并发会把速率测量污染掉，所以要挡。"""
    me = os.getpid()
    hits = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        if int(pid) == me:
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        parts = [c for c in cmd.split("\0") if c]
        if not parts or "python" not in parts[0]:
            continue
        line = " ".join(parts)
        if any(p in line for p in RL_PAT) and "measure_train_rate" not in line:
            hits.append(f"pid={pid} {line[:150]}")
    return hits


def machine() -> dict:
    return {"loadavg": [round(v, 1) for v in os.getloadavg()], "cpu_count": os.cpu_count(),
            "procs_r_d": proc_counts(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", type=int, default=12000,
                    help="每个配置的训练步数。测速率不需要 60k：12k 步已足够把 sps 定下来，"
                         "而 60k 在最慢配置下要 3 h")
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=list(CONFIGS))
    ap.add_argument("--task", default="lift", choices=["lift", "pickplace"])
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps-per-round", type=int, default=4000,
                    help="harness 的一轮训练步数，用来把 sps 换算成 train_sec_per_round")
    ap.add_argument("--force", action="store_true", help="有别的 RL 进程也照跑（量并发惩罚用）")
    ap.add_argument("--out", default="runs/infra/train_rate_controlled.json")
    args = ap.parse_args()

    others = other_rl_procs()
    if others and not args.force:
        print("[拒绝启动] 检测到别的 RL 进程在跑，速率测量会被污染：")
        for o in others:
            print("   ", o)
        print("  等它跑完，或用 --force（那测到的就是**并发下**的速率，要注明）")
        return 2

    print("=" * 78)
    print(f"受控训练速率测量 · task={args.task} steps={args.steps} 配置={args.configs}")
    print(f"  串行执行，同一时间窗；计时窗内只留 1 局内联评测（历史产物里是 30 局）")
    print("=" * 78, flush=True)

    rows = []
    for name in args.configs:
        run_name = f"infra_rateme_{args.task}_{name}"
        cmd = [VENV_PY, TRAINER, "--task", args.task, "--steps", str(args.steps),
               "--horizon", str(args.horizon), "--eval-freq", str(args.steps),
               "--eval-episodes", "1", "--reward-shaping", "1", "--device", args.device,
               "--seed", str(args.seed), "--run-name", run_name, *CONFIGS[name]]
        print(f"\n[{name}] {' '.join(cmd)}", flush=True)
        m0 = machine()
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        wall = time.perf_counter() - t0
        m1 = machine()
        run_dirs = sorted((REPO_ROOT / "runs").glob(f"*_{run_name}"))
        res = {}
        if run_dirs:
            rj = run_dirs[-1] / "result.json"
            if rj.exists():
                res = json.loads(rj.read_text(encoding="utf-8"))
        sps = res.get("steps_per_second") or (args.steps / wall if wall else None)
        row = {
            "config": name, "extra_args": CONFIGS[name], "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "run_dir": str(run_dirs[-1]) if run_dirs else None,
            "wall_sec_subprocess": round(wall, 1),
            "train_seconds": res.get("train_seconds"),
            "steps_per_second": round(sps, 2) if sps else None,
            "train_sec_per_round": (round(args.steps_per_round / sps, 1) if sps else None),
            "inline_eval_episodes_in_timed_window": 1,
            "machine_before": m0, "machine_after": m1,
            "stdout_tail": (proc.stdout or "")[-1200:], "stderr_tail": (proc.stderr or "")[-800:],
        }
        rows.append(row)
        print(f"  ⇒ wall={wall:.0f}s train_seconds={res.get('train_seconds')} "
              f"sps={row['steps_per_second']} → train_sec_per_round"
              f"({args.steps_per_round} 步)={row['train_sec_per_round']}", flush=True)
        if proc.returncode != 0:
            print("  [非零退出] stderr 尾部:", (proc.stderr or "")[-400:], flush=True)

    ok = [r for r in rows if r["steps_per_second"]]
    spread = (max(r["steps_per_second"] for r in ok) / min(r["steps_per_second"] for r in ok)
              if len(ok) > 1 else None)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "purpose": "受控重测 Lift 训练墙钟，替换成本表里从 reach 借来的 train_sec_per_round=671",
        "protocol": {"serial": True, "same_time_window": True, "steps": args.steps,
                     "inline_eval_episodes": 1, "steps_per_round_for_translation": args.steps_per_round,
                     "concurrency_guard": not args.force,
                     "other_rl_procs_at_start": others},
        "rows": rows,
        "sps_spread": round(spread, 2) if spread else None,
        "historical_reference": {
            "note": "来自 runs/*/result.json，**计时窗含 30 局内联评测**，且 demo5k 与 "
                    "demo5k_bc3k 的训练窗口重叠 84 min ⇒ 慢值互相污染，不能归因于配置",
            "162317_sac_lift_state_shaped": {"sps": 42.3, "window": "16:23-16:46", "solo": True},
            "164831_sac_lift_state_shaped_demo5k": {"sps": 8.9, "window": "16:48-18:40", "solo": False},
            "171636_sac_lift_state_shaped_demo5k_bc3k": {"sps": 5.6, "window": "17:16-20:15",
                                                          "solo": False},
        },
    }
    if spread:
        out["conclusion"] = (
            f"同一时间窗串行测量：sps 在 {min(r['steps_per_second'] for r in ok)}~"
            f"{max(r['steps_per_second'] for r in ok)} 之间，差 {spread:.2f}×。"
            + ("配置本身就值这个倍数（历史 7.6× 至少部分是真的）" if spread >= 2 else
               "配置差异远小于历史的 7.6× ⇒ 历史慢值主要是**并发**造成的，"
               "成本表应当用这里的独跑值"))
    path = Path(args.out)
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("\n" + "=" * 78)
    print(f"{'config':<16}{'wall_s':>9}{'train_s':>10}{'sps':>8}{'sec/round':>11}")
    for r in rows:
        print(f"{r['config']:<16}{r['wall_sec_subprocess']:>9.0f}"
              f"{str(r['train_seconds'] and round(r['train_seconds'])):>10}"
              f"{str(r['steps_per_second']):>8}{str(r['train_sec_per_round']):>11}")
    print(f"\nsps 极差 {out.get('sps_spread')}×")
    if out.get("conclusion"):
        print("结论:", out["conclusion"])
    print(f"已写出: {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
