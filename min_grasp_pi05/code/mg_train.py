#!/usr/bin/env python
"""最小抓取链路 · 训练启动器（同步 BC，不用 RL、不用异步调度）。

两条臂，同一份数据集，同一个评测口径：
  act   —— 从零训练的 ACT（ResNet18 + CVAE + transformer），几十分钟出第一个 policy 指标；
  pi05  —— 在 π₀.₅ 基座（weights/pi05_base，本地已校验）上小数据微调。

它只做三件事：拼 lerobot-train 的命令行、把命令原文与日志落到 run 目录、起进程。
超参不写死在这里——全部通过 --extra 'policy.xxx=yyy' 传下去。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_train.py --policy act  --dataset fixed10 --steps 20000'
    bash -c 'source code/env.sh && $MG_PY code/mg_train.py --policy pi05 --dataset fixed10 --steps 4000 --batch-size 2'
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from mg_env import ACTION_DIM, STATE_DIM, TASK  # noqa: E402

DATA = MG_ROOT / "data"
RUNS = MG_ROOT / "runs"
WEIGHTS = MG_ROOT / "weights"

# 每种策略的默认超参（都是 lerobot 0.4.4 的 --policy.* / --dataset.* 键）
DEFAULTS = {
    "act": {
        "policy.chunk_size": "100",
        "policy.n_action_steps": "100",
        "policy.pretrained_backbone_weights": "ResNet18_Weights.IMAGENET1K_V1",
        "policy.device": "cuda",
        "policy.push_to_hub": "false",
        "dataset.use_imagenet_stats": "true",
    },
    "pi05": {
        "policy.dtype": "bfloat16",
        "policy.gradient_checkpointing": "true",
        "policy.chunk_size": "50",
        "policy.n_action_steps": "50",
        "policy.device": "cuda",
        "policy.push_to_hub": "false",
        "policy.scheduler_warmup_steps": "100",
        "dataset.use_imagenet_stats": "true",
    },
}


def parse_ep_subset(spec: str) -> list[int]:
    """'60-119' / '0,2,4-6' -> [0, 2, 4, 5, 6, 60, 61, ...]（去重 + 升序）。"""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            if lo > hi:
                raise ValueError(f"episode 区间反了：{part}")
            out.extend(range(lo, hi + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def subset_preflight(ds_root: Path, subset: list[int]) -> dict:
    """发车前把子集的家底盘清楚：帧数、epoch 步数、task 字符串集合。

    为什么必须做：`--dataset.episodes` 是个**静默**开关 —— 写错区间不会报错，
    只会安静地训了另一批数据（甚至空集）。档 2c 的整个结论都建立在
    「只有反向 60 条被喂进去」这一句上，所以这句必须由产物证明，不能由命令行证明。
    """
    import pandas as pd

    files = sorted(ds_root.glob("meta/episodes/**/*.parquet"))
    if not files:
        raise FileNotFoundError(f"{ds_root} 下没有 meta/episodes/*.parquet")
    df = pd.concat([pd.read_parquet(f) for f in files])
    total_ep = int(df["episode_index"].max()) + 1
    bad = [e for e in subset if e < 0 or e >= total_ep]
    if bad:
        raise ValueError(f"episode 越界（数据集只有 {total_ep} 集）：{bad[:8]}")
    sub = df[df["episode_index"].isin(subset)]
    if len(sub) != len(subset):
        raise ValueError(f"子集里有 {len(subset) - len(sub)} 个 episode 在 meta 里找不到")
    tasks = sorted({t for ts in sub["tasks"] for t in list(ts)})
    frames = int(sub["length"].sum())
    return {"n_episodes": int(len(sub)), "n_frames": frames, "tasks": tasks,
            "episodes": subset, "dataset_total_episodes": total_ep,
            "dataset_total_frames": int(df["length"].sum())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", choices=("act", "pi05"), required=True)
    ap.add_argument("--dataset", required=True, help="data/<dataset> 目录名（= repo_id）")
    ap.add_argument("--episodes-subset", default="",
                    help="只用数据集里的这些 episode 训练，如 '60-119' 或 '0,2,4-6'。"
                         "映射到 lerobot-train 的 --dataset.episodes=[...]。"
                         "用途：**同一份数据、同一份归一化统计**下做「数据配比」消融"
                         "（档 2c：只喂反向 60 条，看反向是不是被正向挤掉的）。"
                         "注意 lerobot 的 DatasetConfig.episodes 会真的过滤 hf_dataset，"
                         "但 meta.stats（= policy normalizer 的来源）**不会**按子集重算 —— "
                         "这正好是我们想要的：消融时归一化器保持不变，唯一变量是采样到哪些帧。")
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--save-freq", type=int, default=2000)
    ap.add_argument("--log-freq", type=int, default=100)
    ap.add_argument("--pretrained", default="", help="π₀.₅ 基座目录（默认 weights/pi05_base）")
    ap.add_argument("--out", default="")
    ap.add_argument("--job-name", default="")
    ap.add_argument("--extra", action="append", default=[], help="额外的 lerobot-train 覆盖项，如 'policy.optimizer_lr=1e-4'")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ds_root = DATA / args.dataset
    if not ds_root.exists():
        print(f"[err] 数据集不存在：{ds_root}（先跑 mg_collect.py）", file=sys.stderr)
        return 2

    ep_subset = parse_ep_subset(args.episodes_subset) if args.episodes_subset else None
    sub_info = None
    if ep_subset:
        try:
            sub_info = subset_preflight(ds_root, ep_subset)
        except Exception as exc:  # noqa: BLE001
            print(f"[err] episode 子集预检失败：{exc}", file=sys.stderr)
            return 2
        print(f"[subset] {sub_info['n_episodes']}/{sub_info['dataset_total_episodes']} 集，"
              f"{sub_info['n_frames']}/{sub_info['dataset_total_frames']} 帧，"
              f"tasks={sub_info['tasks']}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    job = args.job_name or f"{args.policy}_{args.dataset}"
    out_dir = Path(args.out) if args.out else RUNS / f"{ts}_{job}"
    # lerobot-train 会拒绝已存在的 output_dir（防止覆盖），所以元信息先写到 <out>_meta/，
    # 训练进程自己建好 out_dir 之后再搬进去。
    meta_dir = out_dir.parent / f"{out_dir.name}_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "lerobot-train",
        f"--dataset.repo_id={args.dataset}",
        f"--dataset.root={ds_root}",
        f"--batch_size={args.batch_size}",
        f"--steps={args.steps}",
        f"--num_workers={args.num_workers}",
        f"--seed={args.seed}",
        f"--save_freq={args.save_freq}",
        f"--log_freq={args.log_freq}",
        "--eval_freq=-1",             # 评测不走 lerobot 的 gym 通道，统一用 mg_eval.py（口径唯一）
        f"--output_dir={out_dir}",
        f"--job_name={job}",
        "--wandb.enable=false",
        "--save_checkpoint=true",
    ]
    pretrained = args.pretrained or (str(WEIGHTS / "pi05_base_lr044") if args.policy == "pi05" else "")
    if pretrained:
        if not Path(pretrained).exists():
            print(f"[err] 基座不存在：{pretrained}", file=sys.stderr)
            return 2
        cmd.append(f"--policy.path={pretrained}")
    else:
        cmd.append(f"--policy.type={args.policy}")

    for key, val in DEFAULTS[args.policy].items():
        cmd.append(f"--{key}={val}")
    if ep_subset:
        cmd.append("--dataset.episodes=[" + ",".join(str(e) for e in ep_subset) + "]")
    for item in args.extra:
        item = item.strip()
        cmd.append(item if item.startswith("--") else f"--{item}")

    log_path = meta_dir / "train.log"
    (meta_dir / "command.sh").write_text("#!/usr/bin/env bash\nsource code/env.sh\n" +
                                        " ".join(shlex.quote(c) for c in cmd) + "\n")
    (meta_dir / "meta.json").write_text(json.dumps({
        "policy": args.policy, "dataset": args.dataset, "dataset_root": str(ds_root),
        "steps": args.steps, "batch_size": args.batch_size, "seed": args.seed,
        "pretrained": pretrained or None, "task": TASK,
        "action_dim": ACTION_DIM, "state_dim": STATE_DIM, "cmd": cmd,
        "episodes_subset": sub_info,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2, ensure_ascii=False))

    print("[cmd] " + " ".join(shlex.quote(c) for c in cmd))
    print(f"[log] {log_path}")
    if args.dry_run:
        return 0

    env_path = Path("/root/mg_venvs/min_grasp/bin")
    import os
    environ = dict(os.environ)
    environ["PATH"] = f"{env_path}:{environ.get('PATH', '')}"
    with open(log_path, "w") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=environ, cwd=str(MG_ROOT))
    for name in ("command.sh", "meta.json", "train.log"):
        src = meta_dir / name
        if src.exists() and out_dir.is_dir():
            src.replace(out_dir / name)
    if out_dir.is_dir() and not any(meta_dir.iterdir()):
        meta_dir.rmdir()
    tail = log_path.read_text(errors="ignore").splitlines()[-25:] if log_path.exists() else []
    print("\n".join(tail))
    print(f"\n[exit] {proc.returncode}   run 目录：{out_dir}")
    print(f"[next] bash -c 'source code/env.sh && $MG_PY code/mg_eval.py "
          f"--ckpt {out_dir}/checkpoints/last/pretrained_model --episodes 10 --video "
          f"--demo-npz data/{args.dataset}_raw.npz'")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
