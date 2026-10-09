#!/usr/bin/env python
"""A/B 对照：相同交互预算下，「失败诊断 + 针对性采样」是否比固定均匀采样学得更快？

这是本项目第一个**可验证的小研究问题**（见 `harness/loop.py` 顶部说明）。
它比同时上 VLA、世界模型、大模型评分要容易验证得多，因为它只有一个变量。

两臂用**子进程**分别跑，理由有两个：
    1. 进程隔离，避免上一臂残留的 torch/采样器状态影响下一臂；
    2. 参数由本脚本统一生成，杜绝手抖把两臂的预算或 seed 写得不一致。

用法：
    python scripts/compare_harness_ab.py --budget-steps 1200 --steps-per-round 600 \
        --episodes 10 --rounds 2                      # 冒烟，几分钟
    python scripts/compare_harness_ab.py --budget-steps 12000 --steps-per-round 4000
    python scripts/compare_harness_ab.py --seeds 0 1 2   # 多 seed 复现（正式结论要这个）

结果看两个地方：
    runs/<tag>_ab/compare.json     机器可读
    终端表格                        每轮的「累计预算 vs 独立评测成功率」
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
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("yaml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget-steps", type=int, default=12000)
    parser.add_argument("--steps-per-round", type=int, default=4000)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0],
                        help="多 seed 复现：每个 seed 跑一对 (uniform, diagnosed)")
    parser.add_argument("--init", default="random")
    parser.add_argument("--target-success", type=float, default=0.95,
                        help="采集成功率达到就提前停。想做「用满预算比整条曲线」就设成 1.01")
    parser.add_argument("--deploy", default="latest", choices=["latest", "published"])
    parser.add_argument("--eval-episodes", type=int, default=50)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "reach_sac.yaml"))
    parser.add_argument("--out", default="")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--aggregate-only", action="store_true",
                        help="不重跑，只把 --out 目录里已有的 loop_result.json 重新汇总一遍")
    parser.add_argument("--band-mode", default="range",
                        choices=["range", "quantile", "labelcond", "frontier"],
                        help="diagnosed 臂的分带方式；uniform 臂不受影响（对照干净）")
    parser.add_argument("--plan-floor", type=float, default=0.15)
    parser.add_argument("--plan-bands", type=int, default=4)
    return parser.parse_args()


def run_arm(mode: str, seed: int, out_dir: Path, args: argparse.Namespace) -> dict:
    cmd = [
        sys.executable, str(REPO_ROOT / "scripts" / "run_harness_loop.py"),
        "--mode", mode, "--seed", str(seed),
        "--budget-steps", str(args.budget_steps),
        "--steps-per-round", str(args.steps_per_round),
        "--episodes", str(args.episodes),
        "--rounds", str(args.rounds),
        "--target-success", str(args.target_success),
        "--init", args.init,
        "--deploy", args.deploy,
        "--eval-episodes", str(args.eval_episodes),
        "--config", args.config,
        "--device", args.device,
        "--threads", str(args.threads),
        "--band-mode", args.band_mode,
        "--plan-floor", str(args.plan_floor),
        "--plan-bands", str(args.plan_bands),
        # 技能名带上 config 标识：不同环境的版本绝不能混进同一条版本线
        # 技能名带上采样设计标识：不同设计的版本绝不能混进同一条版本线，
        # 否则「不掉点」门禁会在两种干预之间做无意义的比较（range 是历史默认，不加后缀）
        "--skill-name", (f"harness_{Path(args.config).stem}_{mode}_s{seed}"
                         if args.band_mode == "range" else
                         f"harness_{Path(args.config).stem}_{args.band_mode}_{mode}_s{seed}"),
        "--out", str(out_dir),
    ]
    log_path = out_dir.parent / f"{out_dir.name}.log"
    print(f"\n### 跑 {mode} (seed={seed})\n    命令: {' '.join(cmd)}\n    日志: {log_path}", flush=True)
    started = time.time()
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO_ROOT))
    print(f"    退出码 {proc.returncode} · 用时 {time.time() - started:.1f}s", flush=True)

    result_path = out_dir / "loop_result.json"
    if not result_path.exists():
        return {"mode": mode, "seed": seed, "error": f"没有产出 {result_path}",
                "returncode": proc.returncode}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["returncode"] = proc.returncode
    # loop_result.json 顶层没有 mode/seed（它们在 config 里），而汇总时是按
    # (seed, mode) 配对的。不在这里补齐，配对结果会全是空 dict，表格清一色 None。
    result.setdefault("mode", mode)
    result.setdefault("seed", seed)
    return result


def load_arm(mode: str, seed: int, out_dir: Path) -> dict:
    """不重跑，只读已有产物（--aggregate-only 用）。"""
    result_path = out_dir / "loop_result.json"
    if not result_path.exists():
        return {"mode": mode, "seed": seed, "error": f"没有产出 {result_path}"}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.setdefault("mode", mode)
    result.setdefault("seed", seed)
    return result


def curve_of(result: dict) -> list[tuple[int, float, float]]:
    """把 learning_curve 拉成 (累计预算, 标准成功率, 严酷成功率)。"""
    out = []
    for point in result.get("learning_curve", []):
        out.append((int(point.get("consumed_steps", 0)),
                    float(point.get("success_rate") or 0.0),
                    float(point.get("harsh_success_rate") or 0.0)))
    return out


def _reconcile_args_from_arms(args, arms: list[dict]) -> None:
    """`--aggregate-only` 时，以各臂 `loop_result.json` 为准覆盖命令行默认值。

    为什么必须做这件事：`--aggregate-only` 只想重算汇总，但 `vars(args)` 会被原样写进
    `compare.json` 的 `args` 字段，而 `scripts/plot_stage3.py` 的报告头（预算 / 每轮步数 /
    采集局数 / 轮数 / 环境 config）就是从这里读的。实测踩过：对 run6（真实 40000 步 /
    8 局 / 10 轮 / `reach_nodelay.yaml`）只传 `--seeds` 和 `--out` 重算，compare.json 里
    记成了默认的 12000 步 / 20 局 / 8 轮 / `reach_sac.yaml` —— 表头和图全是错的，
    而且**从输出上完全看不出来**。所以这里逐项校正并打印改了什么。

    yaml 路径没有被 `run_harness_loop.py` 记进 `loop_result.json`（该文件正被运行中的
    作业 import，按 §12.9 规则 1 冻结，待解冻后补记），所以只能标成未知 + env_factory。
    """
    src = next((a.get("config") for a in arms if a.get("config")), None)
    if not src:
        return
    mapping = {                      # loop_result.config 的键 -> argparse 的键
        "budget_steps": "budget_steps",
        "steps_per_round": "steps_per_round",
        "episodes_per_round": "episodes",
        "max_rounds": "rounds",
        "target_success": "target_success",
        "eval_episodes": "eval_episodes",
        "init": "init",
    }
    changed = []
    for src_key, dst_key in mapping.items():
        if src_key in src and getattr(args, dst_key, None) != src[src_key]:
            changed.append(f"{dst_key}: {getattr(args, dst_key, None)} -> {src[src_key]}")
            setattr(args, dst_key, src[src_key])
    env_factory = next((a.get("env_factory") for a in arms if a.get("env_factory")), None)
    default_cfg = str(REPO_ROOT / "configs" / "reach_sac.yaml")
    if str(args.config) == default_cfg and env_factory:
        args.config = f"<yaml 路径未记录 · env_factory={env_factory}>"
        changed.append(f"config: {default_cfg} -> {args.config}")
    if changed:
        print("  [aggregate-only 校正] 以各臂 loop_result.json 为准覆盖了这些参数：")
        for line in changed:
            print(f"      {line}")


def main() -> int:
    args = parse_args()
    tag = time.strftime("%Y%m%d_%H%M%S")
    root = Path(args.out) if args.out else REPO_ROOT / "runs" / f"{tag}_ab"
    if args.aggregate_only:
        if not root.exists():
            raise SystemExit(f"--aggregate-only 需要已存在的目录: {root}")
    else:
        root.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("A/B 对照：diagnosed（诊断+针对性采样） vs uniform（固定均匀采样）"
          + ("  [仅重算已有产物]" if args.aggregate_only else ""))
    print(f"输出: {root}")

    arms: list[dict] = []
    for seed in args.seeds:
        for mode in ("uniform", "diagnosed"):
            out_dir = root / f"{mode}_s{seed}"
            if args.aggregate_only:
                arms.append(load_arm(mode, seed, out_dir))
            else:
                arms.append(run_arm(mode, seed, out_dir, args))

    if args.aggregate_only:
        _reconcile_args_from_arms(args, arms)

    # 参数行放在校正**之后**打印：否则 aggregate-only 时会先印一遍命令行默认值、
    # 再印一遍"已校正成别的值"，同一份输出自相矛盾（读日志的人只会看到第一行）。
    print(f"预算 {args.budget_steps} 步/臂 · 每轮 {args.steps_per_round} 步训练 + "
          f"{args.episodes} 局采集 · 最多 {args.rounds} 轮 · seeds={args.seeds}")
    print(f"环境 {args.config} · target_success={args.target_success} · "
          f"独立评测 {args.eval_episodes} 局")
    print("=" * 76)

    # ---- 汇总 -----------------------------------------------------------
    print()
    print("=" * 76)
    print("对照表（同一预算下，独立评测的成功率；数字越早达到高分 = 学得越快）")
    print("曲线用的是**每轮候选策略**的独立评测分，不是只算过了门禁的版本 ——")
    print("学习速度这个问题要看学到哪儿了，发布门禁是另一件事（见 harness/loop.py）")
    print("=" * 76)
    rows = []
    for seed in args.seeds:
        pair = {a["mode"]: a for a in arms if a.get("seed") == seed}
        for mode in ("uniform", "diagnosed"):
            result = pair.get(mode, {})
            curve = curve_of(result)
            final = result.get("learner_metrics") or {}
            rows.append({
                "seed": seed, "mode": mode,
                "consumed_steps": result.get("consumed_steps"),
                "stop_reason": result.get("stop_reason"),
                "rounds": len(result.get("history", [])) - 1,
                "final_success": final.get("success_rate"),
                "final_harsh": final.get("harsh_success_rate"),
                "n_published": result.get("n_published"),
                "published_metrics": result.get("published_metrics"),
                "curve": curve,
                "error": result.get("error", ""),
            })
            curve_txt = " ".join(f"{s}->{r:.2f}" for s, r, _ in curve)
            print(f"  seed={seed} {mode:<10} 消耗={str(rows[-1]['consumed_steps']):>7} "
                  f"轮数={rows[-1]['rounds']} 最终标准={final.get('success_rate')} "
                  f"严酷={final.get('harsh_success_rate')} 过线版本数={rows[-1]['n_published']}")
            print(f"      曲线(累计步数->成功率): {curve_txt or '无'}")
            if rows[-1]["error"]:
                print(f"      错误: {rows[-1]['error']}")

    # 「谁更快」的单一数字：达到某个成功率所需的累计交互步数
    for threshold in (0.5, 0.8, 0.95):
        line = []
        for seed in args.seeds:
            for mode in ("uniform", "diagnosed"):
                row = next((r for r in rows if r["seed"] == seed and r["mode"] == mode), None)
                if not row:
                    continue
                reached = next((s for s, r, _ in row["curve"] if r >= threshold), None)
                line.append(f"{mode}/s{seed}={reached if reached is not None else '未达'}")
        print(f"  达到 {threshold:.0%} 成功率所需累计步数: " + "  ".join(line))

    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "args": vars(args),
        "rows": rows,
        "note": "两臂唯一差别是 mode（采样分布）；预算/seed/超参/评测口径完全相同。"
                "单 seed 的差异可能只是噪声，正式结论要跑 --seeds 0 1 2。",
    }
    out_path = root / "compare.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
    print(f"\n  汇总已存: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
