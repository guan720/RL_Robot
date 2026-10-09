#!/usr/bin/env python
"""把 robosuite PickPlaceCan 各训练臂画到一张图上对比（阶段 2.5 的结果视图）。

终端里一行行 `[eval @ 10000 步] 成功率 0.0%` 看不出趋势，也看不出「哪一臂先起步」。
这个脚本回答三个问题：

    1. 各臂的 episode 成功率随步数怎么变？      -> fig_pickplace_curves.png（左）
    2. 成功率还是 0% 时，奖励在涨吗？           -> fig_pickplace_curves.png（右）
    3. 冻结评测口径下各臂最终差多少？           -> fig_pickplace_arms.png

第 2 个问题最容易被忽略：PickPlaceCan 的 shaped 臂成功率长期 0%，但 mean_reward 从 1.09
涨到 9.19，说明它学会了 reach/grasp/lift/hover，卡在最后的 place。**只看成功率会把它误判成
「什么都没学到」**，只看奖励又会把「没完成任务」误判成「快成功了」——两个必须并排看。

数据来源（都是本项目自己写的，不依赖 tensorboard）：
    runs/<ts>_<name>/eval_curve.json          训练中每 eval_freq 步的确定性冻结评测
    runs/<ts>_<name>/config.json + result.json 观测档 / 奖励档 / 示范步数 / 耗时
    runs/<ts>_<name>/reeval_fixed_success.json 用修复后的成功口径重评（可选）

注意：本机没有中文字体，**图里的标签一律用英文**，中文解释放在终端输出和 docs 里。

用法：
    python scripts/plot_pickplace.py --latest              # 自动挑所有 pickplace 臂
    python scripts/plot_pickplace.py --run runs/xxx --run runs/yyy   # 只画指定几臂
    python scripts/plot_pickplace.py --latest --no-smoke   # 排除冒烟短跑（默认就排除）
    python scripts/plot_pickplace.py --latest --ascii      # 终端里也画一张 ASCII 曲线
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "matplotlib")

import matplotlib  # noqa: E402

matplotlib.use("Agg")          # 本机无显示器，必须用离屏后端
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT_DIR = REPO_ROOT / "runs" / "infra" / "pickplace_figures"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def label_of(run_dir: Path, cfg: dict, result: dict) -> str:
    """从配置生成一个短标签，图例里能一眼看出这一臂换了哪个变量。

    刻意只暴露「我们主动改的那几层」：观测档、奖励档、示范步数。
    其它（seed、net_arch）不放进标签，避免图例爆掉。
    """
    obs = cfg.get("obs", "?")
    shaped = "shaped" if cfg.get("reward_shaping") else "sparse"
    demo = int(cfg.get("demo_steps") or (result or {}).get("demo", {}).get("demo_steps") or 0)
    task = cfg.get("task", "pickplace")
    tag = f"{obs}/{shaped}" if task == "pickplace" else f"{task}/{obs}/{shaped}"
    if demo:
        tag += f"+demo{demo // 1000}k" if demo >= 1000 else f"+demo{demo}"
    bc = int(cfg.get("bc_steps") or 0)
    if bc:
        tag += f"+bc{bc // 1000}k" if bc >= 1000 else f"+bc{bc}"
    if (result or {}).get("bc_only"):
        tag += "(BC-only)"
    if obs == "pixels":
        tag += f"@{cfg.get('cam_size', 64)}"
    return tag


def collect(run_dirs) -> list[dict]:
    arms = []
    for run_dir in run_dirs:
        run_dir = Path(run_dir)
        curve = _load_json(run_dir / "eval_curve.json")
        cfg = _load_json(run_dir / "config.json") or {}
        result = _load_json(run_dir / "result.json") or {}
        if not cfg or cfg.get("task") not in ("pickplace", "lift"):
            continue
        curve = curve or []
        arms.append({
            "dir": run_dir,
            "label": label_of(run_dir, cfg, result),
            "curve": curve,
            "steps": [c["step"] for c in curve],
            "success": [100.0 * c["episode_success"] for c in curve],
            "reward": [c["mean_reward"] for c in curve],
            "tasks": [c.get("tasks_done", 0) for c in curve],
            "total_steps": cfg.get("steps", 0),
            "train_seconds": result.get("train_seconds"),
            "sps": result.get("steps_per_second"),
            "final": result.get("eval_final") or {},
            "reeval": _load_json(run_dir / "reeval_fixed_success.json"),
            "demo_steps": int(cfg.get("demo_steps") or (result.get("demo") or {}).get("demo_steps") or 0),
            "result": result,
        })
    return arms


def find_pickplace_runs(include_smoke: bool) -> list[Path]:
    """挑出 config.json 带 task 字段（pickplace/lift）的 run；曲线可为空（bc-only 臂）。"""
    runs = []
    for run_dir in sorted((REPO_ROOT / "runs").glob("*_*")):
        if not include_smoke and "smoke" in run_dir.name:
            continue
        cfg = _load_json(run_dir / "config.json")
        if not cfg or cfg.get("task") not in ("pickplace", "lift"):
            continue
        runs.append(run_dir)
    return runs


def plot_curves(arms: list[dict], out_png: Path) -> None:
    fig, (ax_s, ax_r) = plt.subplots(1, 2, figsize=(12, 4.2))
    for arm in arms:
        if not arm["steps"]:
            continue
        ax_s.plot(arm["steps"], arm["success"], marker="o", ms=3, lw=1.4, label=arm["label"])
        ax_r.plot(arm["steps"], arm["reward"], marker="o", ms=3, lw=1.4, label=arm["label"])
    ax_s.set_title("Frozen-eval episode success (%)")
    ax_s.set_xlabel("training steps")
    ax_s.set_ylabel("success %")
    ax_s.grid(alpha=0.3)
    ax_r.set_title("Frozen-eval mean episode reward")
    ax_r.set_xlabel("training steps")
    ax_r.set_ylabel("mean reward")
    ax_r.grid(alpha=0.3)
    for ax in (ax_s, ax_r):
        ax.legend(fontsize=8, loc="best")
    fig.suptitle("PickPlaceCan: reward curve vs success curve (read both, never one alone)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def plot_arms(arms: list[dict], out_png: Path) -> None:
    labels = [a["label"] for a in arms]
    finals = [100.0 * (a["final"].get("episode_success", 0.0)) for a in arms]
    rewards = [a["final"].get("mean_reward", 0.0) for a in arms]
    reevals = [100.0 * a["reeval"]["episode_success"] if a["reeval"] else np.nan for a in arms]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.0))
    x = np.arange(len(labels))
    ax1.bar(x - 0.18, finals, width=0.36, label="train-time frozen eval")
    ax1.bar(x + 0.18, reevals, width=0.36, label="re-eval (fixed success metric)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
    ax1.set_ylabel("episode success %")
    ax1.set_title("Final success by arm")
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", alpha=0.3)

    ax2.bar(x, rewards, width=0.5, color="#c46a2b")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
    ax2.set_ylabel("mean episode reward")
    ax2.set_title("Final mean reward (shaped arms only comparable)")
    ax2.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def print_table(arms: list[dict]) -> None:
    head = f"{'臂(label)':<32}{'总步数':>9}{'示范':>8}{'耗时':>9}{'步/秒':>8}{'冻结成功':>10}{'重评成功':>10}{'重评奖励':>10}"
    print()
    print(head)
    print("-" * len(head.expandtabs()))
    for a in arms:
        secs = f"{a['train_seconds']/60:.0f}min" if a["train_seconds"] else "-"
        sps = f"{a['sps']:.1f}" if a["sps"] else "-"
        total = "-" if (a.get("result") or {}).get("bc_only") else a["total_steps"]
        fin = f"{100*a['final'].get('episode_success', 0.0):.1f}%" if a["final"] else "-"
        rr = a["reeval"] or {}
        rs = f"{100*rr['episode_success']:.1f}%" if rr else "-"
        rw = f"{rr['mean_reward']:.2f}" if rr else "-"
        demo = f"{a['demo_steps']//1000}k" if a["demo_steps"] else "0"
        print(f"{a['label']:<32}{str(total):>9}{demo:>8}{secs:>9}{sps:>8}{fin:>10}{rs:>10}{rw:>10}")
    print()
    print("目录：")
    for a in arms:
        print(f"  {a['label']:<32} {a['dir'].relative_to(REPO_ROOT)}")


def print_ascii(arm: dict) -> None:
    from scripts.show_curve import ascii_curve

    print()
    print(f"[{arm['label']}] 训练中 mean_reward 曲线（{arm['dir'].name}）")
    print(ascii_curve(np.asarray(arm["steps"], dtype=float), np.asarray(arm["reward"], dtype=float)))
    print()
    print(f"[{arm['label']}] 训练中 episode 成功率曲线")
    print(ascii_curve(np.asarray(arm["steps"], dtype=float), np.asarray(arm["success"], dtype=float)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", default=[], help="run 目录，可重复；不给则自动挑")
    ap.add_argument("--latest", action="store_true", help="自动挑 runs/ 下所有非冒烟 pickplace 臂")
    ap.add_argument("--with-smoke", action="store_true", help="自动挑时把冒烟短跑也算进来")
    ap.add_argument("--ascii", action="store_true", help="终端里额外打印 ASCII 曲线")
    args = ap.parse_args()

    run_dirs = args.run or []
    if not run_dirs or args.latest:
        run_dirs = list(run_dirs) + find_pickplace_runs(args.with_smoke)
    if not run_dirs:
        raise SystemExit("runs/ 下还没有带 eval_curve.json 的 pickplace 臂，先跑 scripts/train_pickplace_sac.py")

    arms = collect(run_dirs)
    if not arms:
        raise SystemExit("挑到的目录里没有可用的 eval_curve.json + config.json")
    arms.sort(key=lambda a: a["total_steps"])

    # 标签撞名（例如两个 state/sparse 冒烟臂）会让图例分不清谁是谁，补上时间后缀
    seen: dict[str, int] = {}
    for arm in arms:
        seen[arm["label"]] = seen.get(arm["label"], 0) + 1
    if any(n > 1 for n in seen.values()):
        for arm in arms:
            if seen[arm["label"]] > 1:
                stamp = arm["dir"].name.split("_")
                arm["label"] = f"{arm['label']}@{stamp[1] if len(stamp) > 1 else arm['dir'].name[-4:]}"

    print_table(arms)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    curves_png = OUT_DIR / "fig_pickplace_curves.png"
    arms_png = OUT_DIR / "fig_pickplace_arms.png"
    plot_curves(arms, curves_png)
    plot_arms(arms, arms_png)
    print(f"\n[已保存] {curves_png}")
    print(f"[已保存] {arms_png}")

    if args.ascii:
        print_ascii(arms[-1])

    print()
    print("怎么读：")
    print("  - 左图（成功率）为 0% 而右图（奖励）在涨 = 学会了子步骤但没完成任务，别急着调算法；")
    print("  - 两图都平 = 探索信号问题（稀疏奖励臂就是这样），解法是示范/课程，不是超参；")
    print("  - 「冻结成功」与「重评成功」不一致时以重评为准：早期成功口径有 bug（info 为空 dict）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
