#!/usr/bin/env python3
"""把 interchange 导出转成官方 LeRobotDataset（codebase v3.0），供 lerobot 官方 ACT 训练入口直接读取。

为什么需要这一步：`runs/infra/lerobot_act_lift_state_overfit/` 只是「LeRobot-compatible
interchange」（逐 episode NPZ + 自写 meta/info.json，codebase_version 标的是
"RL_Robot local export"），官方 `lerobot.scripts.lerobot_train` 读不了。这里改用官方 API
（`LeRobotDataset.create` / `add_frame` / `save_episode`）重建真正的 v3.0 数据集，
统计量、parquet 分片、episodes/tasks 元数据全部由官方代码生成，不手写。

特征映射（关键适配，写进 manifest）：
    项目侧 observation_state[60] = robot0_proprio-state(50) + object-state(10)
        -> observation.state             float32[50]   本体感知
        -> observation.environment_state float32[10]   物体状态
    项目侧 action[7] = OSC_POSE xyz/rpy delta + gripper（+1 close / -1 open）
        -> action                        float32[7]

拆成两个 key 不是可选项：官方 `ACTConfig.validate_features()` 要求输入里至少有一个
image 或 `observation.environment_state`，只给 `observation.state` 会直接 ValueError。
50/10 的切分依据是 `docs/notes_stage1.md` 记录的 robosuite 观测构成。

action chunk 不在这里物化：官方 ACT 通过 `delta_timestamps` 在 `__getitem__` 里取
`chunk_size` 个未来动作，等价于 interchange 里的 `action_chunk` 字段；本脚本会把两者
逐元素对齐结果写进 manifest，作为「语义等价」的证据。

帧裁剪（`--trim-done N`）：源导出每局都跑满 horizon=300，任务成功后 teacher 进入 `done`
相位并输出常值动作 `[0,0,0,0,0,0,+1]`，全量 train split 里 `done` 占 72.5%、真正的 `lift`
帧只占 2.3%（见 `docs/lerobot_act_env_setup_20260928.md`）。损失被「什么都不做」主导，
抬起幅度学不出来。`--trim-done N` 只裁掉**每局末尾连续的 `done` 帧**、保留到 `N` 帧为止，
`hold`（夹持抬高中）一帧不动——B 线已验证丢掉 `hold` 会让模型抬起后主动开爪扔方块。
裁剪后末尾 `CHUNK-1` 个 chunk 会跨过新的 episode 边界（官方补帧），与源 `action_chunk`
不再可比，verify 会跳过它们并计数，不当作 mismatch。

用法（必须用装了 lerobot 的解释器）：
    /root/venvs/lerobot_act/bin/python scripts/build_lerobot_act_dataset.py \
        --split train --out runs/infra/lerobot_act_lift_v30/train
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np

STATE_DIM = 50
ENV_DIM = 10
ACTION_DIM = 7
FPS = 20
CHUNK = 4
DONE_PHASE = "done"
TASK_DEFAULT = "Lift the cube and hold it above the threshold height"


def _phase_array(z) -> np.ndarray:
    raw = np.asarray(z["phase"])
    return np.array([p.decode() if isinstance(p, bytes) else str(p) for p in raw])


def _trim_cut(phases: np.ndarray, trim_done: int) -> int:
    """返回保留帧数：末尾连续 done 段最多留 trim_done 帧；没有 done 段则全留。"""
    i = len(phases) - 1
    while i >= 0 and phases[i] == DONE_PHASE:
        i -= 1
    first_done = i + 1
    if first_done >= len(phases):
        return len(phases)
    return max(1, min(len(phases), first_done + trim_done))


def _sha256(path: Path, limit: int = 1 << 20) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        h.update(fh.read(limit))
    return h.hexdigest()


def load_source(src: Path) -> tuple[dict, list[dict]]:
    info = json.loads((src / "meta" / "info.json").read_text())
    rows = [json.loads(x) for x in (src / "meta" / "episodes.jsonl").read_text().splitlines() if x.strip()]
    for row in rows:
        row["path"] = src / "data" / f"episode_{int(row['episode_index']):04d}.npz"
        if not row["path"].exists():
            raise FileNotFoundError(row["path"])
    return info, rows


def select(rows: list[dict], split: str, limit: int | None) -> list[dict]:
    picked = rows if split == "all" else [r for r in rows if r["split"] == split]
    if not picked:
        raise SystemExit(f"[错误] split={split} 没有 episode；可选 train/validation/test/all")
    picked = sorted(picked, key=lambda r: int(r["episode_index"]))
    if limit is not None:
        picked = picked[:limit]
    return picked


def build(src: Path, out: Path, repo_id: str, split: str, limit: int | None, task: str,
          trim_done: int | None = None) -> dict:
    from lerobot import __version__ as lerobot_version
    from lerobot.datasets.lerobot_dataset import CODEBASE_VERSION, LeRobotDataset

    info, rows = load_source(src)
    picked = select(rows, split, limit)

    probe = np.load(picked[0]["path"], allow_pickle=False)
    obs_dim = int(probe["observation_state"].shape[1])
    if obs_dim != STATE_DIM + ENV_DIM:
        raise SystemExit(f"[错误] 源观测是 {obs_dim} 维，与 50+10 的切分假设不符，先核对 STATE_KEYS")

    if out.exists():
        raise SystemExit(f"[错误] 输出目录已存在：{out}\n  换一个 --out，或先把它 mv 到回收站（本项目禁止 rm）")

    features = {
        "observation.state": {"dtype": "float32", "shape": (STATE_DIM,)},
        "observation.environment_state": {"dtype": "float32", "shape": (ENV_DIM,)},
        "action": {"dtype": "float32", "shape": (ACTION_DIM,)},
    }
    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=FPS,
        features=features,
        robot_type=info.get("robot_type", "robosuite_panda_lift"),
        root=out,
        use_videos=False,
    )

    written = []
    ts_max_error = 0.0
    hist_source = collections.Counter()
    hist_written = collections.Counter()
    dropped_total = 0
    for row in picked:
        z = np.load(row["path"], allow_pickle=False)
        obs = np.asarray(z["observation_state"], dtype=np.float32)
        act = np.asarray(z["action"], dtype=np.float32)
        ts = np.asarray(z["timestamp"], dtype=np.float32)
        if len(obs) != len(act) or len(ts) != len(act):
            raise SystemExit(f"[错误] episode {row['episode_index']} 帧数不一致")
        phases = _phase_array(z) if "phase" in z else None
        if phases is not None and len(phases) != len(act):
            raise SystemExit(f"[错误] episode {row['episode_index']} phase 与 action 帧数不一致")
        frames_source = len(act)
        if phases is not None:
            hist_source.update(phases.tolist())
        cut = frames_source
        if phases is not None and trim_done is not None:
            cut = _trim_cut(phases, trim_done)
        obs, act, ts = obs[:cut], act[:cut], ts[:cut]
        if phases is not None:
            phases = phases[:cut]
            hist_written.update(phases.tolist())
        dropped_total += frames_source - cut
        # 官方 add_frame 不接受 timestamp 字段，它自己按 frame_index/fps 生成。
        # 源数据的 timestamp 就是 i/20.0，所以两者逐帧一致，这里量出误差记进 manifest。
        expect = np.arange(len(act), dtype=np.float64) / FPS
        ts_max_error = max(ts_max_error, float(np.max(np.abs(ts.astype(np.float64) - expect))))
        for i in range(len(act)):
            dataset.add_frame(
                {
                    "observation.state": obs[i, :STATE_DIM],
                    "observation.environment_state": obs[i, STATE_DIM:],
                    "action": act[i],
                    "task": task,
                }
            )
        dataset.save_episode()
        written.append(
            {
                "episode_index": len(written),
                "source_episode_index": int(row["episode_index"]),
                "seed": int(row["seed"]),
                "split": str(row["split"]),
                "frames": int(len(act)),
                "frames_source": int(frames_source),
                "done_frames_dropped": int(frames_source - len(act)),
                "source_sha256_1mb": _sha256(row["path"]),
            }
        )
        print(f"  写入 episode {written[-1]['episode_index']:>3d} <- src {row['episode_index']:04d} "
              f"seed={row['seed']} frames={len(act)}/{frames_source}"
              + (f" (裁掉末尾 done {frames_source - len(act)} 帧)" if cut < frames_source else ""))

    return {
        "lerobot_version": lerobot_version,
        "codebase_version": CODEBASE_VERSION,
        "episodes": written,
        "timestamp_source_vs_frame_index_over_fps_max_error": ts_max_error,
        "trim_done": trim_done,
        "frames_source_total": int(sum(w["frames_source"] for w in written)),
        "frames_written_total": int(sum(w["frames"] for w in written)),
        "done_frames_dropped_total": int(dropped_total),
        "phase_hist_source": dict(sorted(hist_source.items())),
        "phase_hist_written": dict(sorted(hist_written.items())),
    }


def verify(out: Path, repo_id: str, src: Path, split: str, task: str,
           written: list[dict] | None = None, trim_done: int | None = None) -> dict:
    """只读回检：官方 Dataset 能否加载、chunk 语义是否与 interchange 等价、统计量来源。"""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    plain = LeRobotDataset(repo_id=repo_id, root=out)
    chunked = LeRobotDataset(
        repo_id=repo_id,
        root=out,
        delta_timestamps={"action": [i / FPS for i in range(CHUNK)]},
    )

    info, rows = load_source(src)
    picked = select(rows, split, None)
    mismatches = []
    checked = 0
    skipped_tail_chunks = 0
    base = 0
    for local_ep in range(min(len(picked), plain.num_episodes)):
        z = np.load(picked[local_ep]["path"], allow_pickle=False)
        ref_chunks = np.asarray(z["action_chunk"], dtype=np.float32)
        # 逐局真实长度累加偏移：裁剪后各局长度不再相同，不能再用 local_ep * 300。
        n_local = int(written[local_ep]["frames"]) if written else int(picked[local_ep]["frames"])
        # 裁剪后末尾 CHUNK-1 个 chunk 跨过新的 episode 边界（官方按 episode 末尾补帧），
        # 与源 action_chunk（在完整 300 帧上算的）不再可比 —— 跳过并计数，不算 mismatch。
        comparable = n_local if trim_done is None else max(0, n_local - (CHUNK - 1))
        comparable = min(len(ref_chunks), comparable)
        skipped_tail_chunks += max(0, min(len(ref_chunks), n_local) - comparable)
        for c in range(comparable):
            got = np.asarray(chunked[base + c]["action"], dtype=np.float32)
            checked += 1
            if got.shape != ref_chunks[c].shape or not np.allclose(got, ref_chunks[c], atol=1e-6):
                mismatches.append({"episode": local_ep, "frame": c})
                if len(mismatches) > 5:
                    break
        base += n_local

    frame0 = plain[0]
    stats = {}
    for key in ("observation.state", "observation.environment_state", "action"):
        entry = plain.meta.stats.get(key) if plain.meta.stats else None
        if entry is None:
            continue
        stats[key] = {
            "mean_head": np.asarray(entry["mean"], dtype=np.float64).ravel()[:3].tolist(),
            "std_head": np.asarray(entry["std"], dtype=np.float64).ravel()[:3].tolist(),
        }

    return {
        "num_episodes": int(plain.num_episodes),
        "num_frames": int(plain.num_frames),
        "fps": int(plain.fps),
        "features": {k: {"dtype": v["dtype"], "shape": list(v["shape"])} for k, v in plain.features.items()},
        "task": task,
        "first_frame_keys": sorted(k for k in frame0 if not k.startswith("_")),
        "chunk_shape": list(np.asarray(frame0["action"]).shape) if "action" in frame0 else None,
        "chunk_equivalence": {
            "chunks_compared": checked,
            "skipped_tail_chunks_after_trim": skipped_tail_chunks,
            "trim_done": trim_done,
            "mismatches": mismatches,
            "all_match": not mismatches,
        },
        "stats_from_official_pipeline": stats,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="runs/infra/lerobot_act_lift_state_overfit")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo-id", default="rl-robot/lift-state-act")
    ap.add_argument("--split", default="train", choices=["train", "validation", "test", "all"])
    ap.add_argument("--episodes", type=int, default=None, help="只取前 N 局（单局 overfit 用 --episodes 1）")
    ap.add_argument("--task", default=TASK_DEFAULT)
    ap.add_argument("--trim-done", type=int, default=None, metavar="N",
                    help="每局末尾连续 done 帧最多保留 N 帧（0=全裁掉）；hold 帧不动。默认不裁剪")
    ap.add_argument("--manifest", default=None, help="默认写到 <out>/build_manifest.json")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] 源 interchange: {src}  split={args.split}  episodes={args.episodes or '全部'}"
          f"  trim_done={args.trim_done}")
    built = build(src, out, args.repo_id, args.split, args.episodes, args.task, args.trim_done)
    print(f"[2/3] 官方 v3.0 数据集写入完成: {out}（{len(built['episodes'])} 局，"
          f"{built['frames_written_total']}/{built['frames_source_total']} 帧）")
    print(f"       相位分布（写入后）: {json.dumps(built['phase_hist_written'], ensure_ascii=False)}")

    verification = None
    if not args.skip_verify:
        print("[3/3] 只读回检：加载 / chunk 语义 / 统计量")
        verification = verify(out, args.repo_id, src, args.split, args.task,
                             built["episodes"], args.trim_done)
        print(json.dumps({k: verification[k] for k in
                          ("num_episodes", "num_frames", "fps", "chunk_shape")}, ensure_ascii=False, indent=2))
        print("chunk 等价性:", json.dumps(verification["chunk_equivalence"], ensure_ascii=False))

    manifest = {
        "generator": "scripts/build_lerobot_act_dataset.py",
        "source": str(src.resolve()),
        "source_meta_codebase_version": json.loads((src / "meta" / "info.json").read_text()).get("codebase_version"),
        "output_root": str(out.resolve()),
        "repo_id": args.repo_id,
        "split": args.split,
        "episode_limit": args.episodes,
        "task": args.task,
        "fps": FPS,
        "feature_map": {
            "observation_state[0:50]": "observation.state (robot0_proprio-state)",
            "observation_state[50:60]": "observation.environment_state (object-state)",
            "action[0:7]": "action (OSC_POSE xyz/rpy delta + gripper, +1 close / -1 open)",
        },
        "feature_map_reason": "ACTConfig.validate_features() 要求 image 或 observation.environment_state 至少其一",
        "chunk_policy": f"不在数据集里物化；官方 delta_timestamps 取未来 {CHUNK} 帧，等价于源 action_chunk",
        "trim_done": args.trim_done,
        "trim_done_reason": (
            "源导出每局跑满 horizon=300，任务成功后 teacher 进 done 相位输出常值动作 "
            "[0,0,0,0,0,0,+1]；train split 里 done 占 72.5%、lift 只占 2.3%，损失被「什么都不做」"
            "主导。只裁末尾连续 done 帧、保留 hold 帧（丢 hold 会让模型抬起后开爪扔方块）。"
            if args.trim_done is not None else None
        ),
        "frames_source_total": built["frames_source_total"],
        "frames_written_total": built["frames_written_total"],
        "done_frames_dropped_total": built["done_frames_dropped_total"],
        "phase_hist_source": built["phase_hist_source"],
        "phase_hist_written": built["phase_hist_written"],
        "pinned_object_seed": json.loads((src / "meta" / "info.json").read_text()).get("pinned_object_seed"),
        "built": built,
        "verification": verification,
    }
    manifest_path = Path(args.manifest) if args.manifest else out / "build_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
