#!/usr/bin/env python
"""最小抓取链路 · 示范采集（脚本专家 -> LeRobotDataset + 原始 npz）。

纪律（对应「先不要使用未经验证的本地数据」）：
  1. 数据只来自本目录的脚本专家（mg_expert.py），不读仓内任何既有数据集；
  2. **只收 success=True 的 episode**，成功判定只用 robosuite 真值 env._check_success()；
  3. 采集结束立刻回读数据集自证（帧数 / 统计 / 单帧形状），写进 MG_DATASET_CARD.json；
  4. 同时落一份原始 npz（state/action/长度），供 mg_probe.py --replay 验证
     「数据集里的动作重放回环境能否复现成功」——这是 action ↔ 环境执行器 的对齐牙。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_collect.py --episodes 50 --name fixed50'
    第 2 阶段（随机位姿）：--seed-mode random --seed-base 1000
    档 2（正反向混合，一个数据集两个 task 字符串）：
        --mode mixed --episodes 60 --reverse-episodes 60 --seed-mode random \
        --seed-base 1000 --reverse-seed-base 5000 --expert-noise 0.05 --name mix60f60r
    正向半边的复现性：noise_rng 固定为 default_rng(12345)、seed = seed_base + attempt，
    所以同样的参数重跑 = 逐比特相同的正向示范（--verify-forward-npz 可拿旧 npz 对账）。
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_env import (  # noqa: E402
    ACTION_DIM, ACTION_KEY, ACTION_NAMES, CAM_BASE, CONTROL_FREQ, IMG_KEY_BASE, IMG_KEY_WRIST, ROBOT,
    STATE_DIM, STATE_KEY, STATE_NAMES, SUITE_TASK, TASK, SingleArmGraspEnv,
)
from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv  # noqa: E402
from mg_expert import ScriptedExpert  # noqa: E402
from mg_expert_reverse import ReverseScriptedExpert  # noqa: E402

DATA = MG_ROOT / "data"


def build_features(img_size: int) -> dict:
    return {
        STATE_KEY: {"dtype": "float32", "shape": (STATE_DIM,), "names": list(STATE_NAMES)},
        ACTION_KEY: {"dtype": "float32", "shape": (ACTION_DIM,), "names": list(ACTION_NAMES)},
        IMG_KEY_BASE: {"dtype": "image", "shape": (img_size, img_size, 3),
                       "names": ["height", "width", "channel"]},
        IMG_KEY_WRIST: {"dtype": "image", "shape": (img_size, img_size, 3),
                        "names": ["height", "width", "channel"]},
    }


def run_one_episode(env: SingleArmGraspEnv, seed: int, want_frames: bool,
                    noise_sigma: float = 0.0, noise_rng: np.random.Generator | None = None,
                    task: str = TASK, expert_cls=ScriptedExpert) -> dict:
    """跑一条脚本专家 episode，返回帧列表与真值指标（不写盘）。

    task / expert_cls 是档 2 加的：反向局用 TASK_REVERSE + ReverseScriptedExpert，
    其余（动作语义、加噪方式、只留成功局）与正向完全一致。
    """
    obs = env.reset(seed=seed)
    expert = expert_cls(env).reset()
    frames: list[dict] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    succ_step, steps, first_success = -1, 0, False
    obj_z0 = float(env.object_pos[2])
    max_lift = 0.0
    while True:
        act = expert()
        if noise_sigma > 0.0:
            # 只给位置三维加噪声（姿态恒 0、夹爪保持 ±1 离散语义），制造围绕名义轨迹的分布；
            # 抓空/掉了会被专家的重试与重抓逻辑救回，最终仍只保留 success 的 episode。
            act = np.asarray(act, dtype=np.float32).copy()
            act[:3] = np.clip(act[:3] + noise_rng.normal(0.0, noise_sigma, size=3), -1.0, 1.0)
        if want_frames:
            frames.append({STATE_KEY: obs[STATE_KEY], ACTION_KEY: act.astype(np.float32),
                           IMG_KEY_BASE: obs[IMG_KEY_BASE], IMG_KEY_WRIST: obs[IMG_KEY_WRIST],
                           "task": task})
        states.append(obs[STATE_KEY].copy())
        actions.append(np.asarray(act, dtype=np.float32))
        obs, _r, terminated, truncated, info = env.step(act)
        steps += 1
        max_lift = max(max_lift, float(info["object_pos"][2]) - obj_z0)
        if info["success"] and succ_step < 0:
            succ_step = steps
        first_success = first_success or info["success"]
        if terminated or truncated:
            break
    return {"seed": seed, "steps": steps, "success": first_success, "success_step": succ_step,
            "max_lift_m": max_lift, "phases": expert.phase_seq, "regrasp": expert.regrasp,
            "frames": frames, "states": np.asarray(states, dtype=np.float32),
            "actions": np.asarray(actions, dtype=np.float32)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=10, help="要收多少条**成功**示范")
    ap.add_argument("--name", default="fixed50", help="数据集目录名（data/<name>）")
    ap.add_argument("--seed-mode", choices=("fixed", "random"), default="fixed",
                    help="fixed=每局同一初态（第 1 阶段）；random=每局换 seed（第 2 阶段）")
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--max-attempts-mult", type=float, default=3.0, help="最多尝试 episodes*mult 局")
    ap.add_argument("--video", action="store_true", help="存第一条成功 episode 的视频")
    ap.add_argument("--expert-noise", type=float, default=0.0,
                    help="给专家的位置动作加高斯噪声 sigma（0=纯净固定示范）；只保留仍成功的局")
    ap.add_argument("--overwrite", action="store_true", help="目标目录已存在时改名备份而不是报错")
    # ── 档 2：正反向混合 ──
    ap.add_argument("--mode", choices=("forward", "reverse", "mixed"), default="forward",
                    help="forward=只正向（档 0/1）；reverse=只反向；mixed=同一数据集里两个 task")
    ap.add_argument("--reverse-episodes", type=int, default=0,
                    help="mixed 模式下要收多少条**成功**的反向示范")
    ap.add_argument("--reverse-seed-base", type=int, default=5000,
                    help="反向 seed 起点；必须与正向区间不相交，否则同一 seed 两个 task 会混淆")
    ap.add_argument("--verify-forward-npz", type=str, default="",
                    help="给一个旧的 <name>_raw.npz，收完后逐比特对账正向半边是否复现")
    args = ap.parse_args()
    if args.mode == "mixed" and args.reverse_episodes <= 0:
        print("[err] --mode mixed 需要 --reverse-episodes > 0", file=sys.stderr)
        return 2

    noise_rng = np.random.default_rng(12345)
    root = DATA / args.name
    if root.exists():
        if not args.overwrite:
            print(f"[err] {root} 已存在（换 --name 或加 --overwrite）", file=sys.stderr)
            return 2
        backup = root.with_name(f"{args.name}.bak_{datetime.now():%Y%m%d_%H%M%S}")
        root.rename(backup)
        print(f"[warn] 旧数据集改名备份 -> {backup}")

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset.create(
        repo_id=args.name, fps=CONTROL_FREQ, features=build_features(args.img_size),
        robot_type=ROBOT.lower(), root=str(root), use_videos=False, image_writer_threads=4,
    )

    # 相位表：mixed = 先正向后反向，写进**同一个**数据集，靠每帧的 task 字符串区分。
    # 正向半边必须与 rand60 逐比特一致，所以正向的 seed / 噪声流 / 尝试顺序都原样保留
    # （noise_rng 单一实例、按相位顺序消费；正向在前 => 与只收正向时完全同序）。
    phases: list[tuple[str, int, int]] = []
    if args.mode in ("forward", "mixed"):
        phases.append(("forward", args.episodes, args.seed_base))
    if args.mode == "reverse":
        phases.append(("reverse", args.episodes, args.reverse_seed_base))
    elif args.mode == "mixed":
        phases.append(("reverse", args.reverse_episodes, args.reverse_seed_base))

    kept: list[dict] = []
    rejected: list[dict] = []
    all_states: list[np.ndarray] = []
    all_actions: list[np.ndarray] = []
    lengths: list[int] = []
    video_frames: list[np.ndarray] = []
    per_phase: dict[str, dict] = {}
    contracts: dict[str, dict] = {}
    t0 = time.perf_counter()

    for mode, want_n, seed_base in phases:
        if mode == "forward":
            env, expert_cls, task = SingleArmGraspEnv(img_size=args.img_size), ScriptedExpert, TASK
        else:
            env, expert_cls, task = (ReverseGraspEnv(img_size=args.img_size),
                                     ReverseScriptedExpert, TASK_REVERSE)
        contracts[mode] = env.contract()
        print(f"\n[phase:{mode}] {SUITE_TASK} / {ROBOT} / fps={env.fps} / horizon={env.horizon} "
              f"/ img={args.img_size} / 目标 {want_n} 条成功示范")
        print(f"[phase:{mode}] task = {task!r}")
        print(f"[phase:{mode}] 契约：{json.dumps(contracts[mode], ensure_ascii=False, indent=2)}")
        max_attempts = int(want_n * args.max_attempts_mult)
        n_before = len(kept)
        rej_before = len(rejected)

        for attempt in range(max_attempts):
            if len(kept) - n_before >= want_n:
                break
            seed = seed_base if args.seed_mode == "fixed" else seed_base + attempt
            want_video = args.video and not video_frames
            res = run_one_episode(env, seed, want_frames=True, noise_sigma=args.expert_noise,
                                  noise_rng=noise_rng, task=task, expert_cls=expert_cls)
            meta = {k: v for k, v in res.items() if k not in ("frames", "states", "actions")}
            meta["mode"] = mode
            if not res["success"]:
                rejected.append(meta)
                print(f"  [{mode}] attempt{attempt} seed={seed} 失败（steps={res['steps']} "
                      f"phases={'->'.join(res['phases'])}）-> 丢弃", flush=True)
                continue

            for fr in res["frames"]:
                ds.add_frame(dict(fr))
            ds.save_episode()
            kept.append(meta)
            all_states.append(res["states"])
            all_actions.append(res["actions"])
            lengths.append(res["steps"])
            if want_video:
                video_frames = [f[IMG_KEY_BASE] for f in res["frames"]]
            print(f"  [{mode}] ep{len(kept) - 1} seed={seed} steps={res['steps']} "
                  f"success_step={res['success_step']} max_lift={res['max_lift_m'] * 100:.1f} cm "
                  f"regrasp={res['regrasp']}", flush=True)

        env.close()
        n_got = len(kept) - n_before
        n_rej = len(rejected) - rej_before
        per_phase[mode] = {"wanted": want_n, "kept": n_got, "rejected": n_rej,
                           "attempts": n_got + n_rej, "seed_base": seed_base, "task": task,
                           "expert": expert_cls.__name__,
                           "yield": round(n_got / max(1, n_got + n_rej), 3)}
        print(f"[phase:{mode}] 收到 {n_got}/{want_n} 条成功示范，丢弃 {n_rej} 条"
              f"（专家产出率 {per_phase[mode]['yield'] * 100:.0f}%）", flush=True)

    ds.finalize()          # 必须调用：否则 parquet footer / episode 元数据不落盘，数据集读不回来
    secs = time.perf_counter() - t0
    contract = contracts.get("forward", contracts.get("reverse"))

    if not kept:
        print("[err] 一条成功示范都没有：先跑 mg_probe.py --expert 修专家，别急着训练", file=sys.stderr)
        return 1

    # ── 原始 npz（重放对齐验证用）：按相位分开存，重放时必须用对应的 env ──
    def _write_npz(suffix: str, idxs: list[int]):
        if not idxs:
            return None
        path = DATA / f"{args.name}{suffix}.npz"
        np.savez_compressed(
            path,
            state=np.concatenate([all_states[i] for i in idxs], axis=0),
            action=np.concatenate([all_actions[i] for i in idxs], axis=0),
            episode_lengths=np.asarray([lengths[i] for i in idxs], dtype=np.int32),
            seeds=np.asarray([kept[i]["seed"] for i in idxs], dtype=np.int64),
        )
        return path

    fwd_idx = [i for i, k in enumerate(kept) if k["mode"] == "forward"]
    rev_idx = [i for i, k in enumerate(kept) if k["mode"] == "reverse"]
    npz_fwd = _write_npz("_raw", fwd_idx)
    npz_rev = _write_npz("_rev_raw", rev_idx)
    npz_path = npz_fwd or npz_rev

    if args.verify_forward_npz and npz_fwd is not None:
        old = np.load(args.verify_forward_npz)
        new = np.load(npz_fwd)
        same = (np.array_equal(old["state"], new["state"]) and np.array_equal(old["action"], new["action"])
                and np.array_equal(old["episode_lengths"], new["episode_lengths"])
                and np.array_equal(old["seeds"], new["seeds"]))
        print(f"[对账] 正向半边 vs {args.verify_forward_npz}: 逐比特相同={same} "
              f"(state {old['state'].shape} vs {new['state'].shape}, "
              f"eps {len(old['episode_lengths'])} vs {len(new['episode_lengths'])})")
        if not same:
            print("[err] 正向半边没有复现旧数据：混合数据集的正向部分与档 1 不可比，先查噪声流/seed 顺序",
                  file=sys.stderr)
            return 3

    if video_frames:
        try:
            import imageio.v2 as imageio
            vdir = MG_ROOT / "runs" / "collect"
            vdir.mkdir(parents=True, exist_ok=True)
            imageio.mimwrite(str(vdir / f"{args.name}_ep0.mp4"), video_frames, fps=env.fps)
            print(f"[video] {vdir / (args.name + '_ep0.mp4')}")
        except Exception as exc:
            print(f"[warn] 视频写入失败：{exc}")

    # ── 回读自证 ──
    ds2 = LeRobotDataset(repo_id=args.name, root=str(root))
    item = ds2[0]
    states = np.concatenate(all_states, axis=0)
    actions = np.concatenate(all_actions, axis=0)
    card = {
        "name": args.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "本目录脚本专家 mg_expert.ScriptedExpert / mg_expert_reverse.ReverseScriptedExpert"
                  "（真值判定成功，失败局全丢）",
        "mode": args.mode,
        "phases": per_phase,
        "seed_mode": args.seed_mode,
        "expert_noise_sigma": args.expert_noise,
        "seed_base": args.seed_base,
        "reverse_seed_base": args.reverse_seed_base,
        "episodes_kept": len(kept),
        "episodes_kept_forward": len(fwd_idx),
        "episodes_kept_reverse": len(rev_idx),
        "episodes_rejected": len(rejected),
        "frames": int(sum(lengths)),
        "fps": env.fps,
        "episode_length_min_max": [int(min(lengths)), int(max(lengths))],
        "reread": {"len": len(ds2), "item_keys": sorted(item.keys()),
                   "state_shape": list(np.asarray(item[STATE_KEY]).shape),
                   "action_shape": list(np.asarray(item[ACTION_KEY]).shape),
                   "img_base_shape": list(np.asarray(item[IMG_KEY_BASE]).shape),
                   "img_wrist_shape": list(np.asarray(item[IMG_KEY_WRIST]).shape),
                   "img_base_dtype": str(np.asarray(item[IMG_KEY_BASE]).dtype),
                   "total_episodes_meta": ds2.meta.total_episodes,
                   "total_frames_meta": ds2.meta.total_frames},
        "state_stats": {n: {"min": float(states[:, i].min()), "max": float(states[:, i].max()),
                            "mean": float(states[:, i].mean()), "std": float(states[:, i].std())}
                        for i, n in enumerate(STATE_NAMES)},
        "action_stats": {n: {"min": float(actions[:, i].min()), "max": float(actions[:, i].max()),
                             "mean": float(actions[:, i].mean()), "std": float(actions[:, i].std()),
                             "frac_at_plus1": float((actions[:, i] > 0.999).mean()),
                             "frac_at_minus1": float((actions[:, i] < -0.999).mean())}
                         for i, n in enumerate(ACTION_NAMES)},
        "contract": contract,
        "contracts": contracts,
        "npz_forward": str(npz_fwd) if npz_fwd else None,
        "npz_reverse": str(npz_rev) if npz_rev else None,
        "per_episode": kept,
        "rejected": rejected,
        "seconds": round(secs, 1),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "npz": str(npz_path),
        "root": str(root),
    }
    try:
        import mujoco
        import robosuite
        import torch
        card["versions"].update({"robosuite": robosuite.__version__, "mujoco": mujoco.__version__,
                                 "torch": torch.__version__})
    except Exception:
        pass
    (root / "MG_DATASET_CARD.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))

    print(f"\n采集完成：{len(kept)} 条成功示范（正向 {len(fwd_idx)} / 反向 {len(rev_idx)}）/ "
          f"{len(kept) + len(rejected)} 次尝试 / {sum(lengths)} 帧 / {secs:.0f} s")
    for m, st in per_phase.items():
        print(f"  [{m}] task={st['task']!r} kept={st['kept']}/{st['wanted']} "
              f"rejected={st['rejected']} yield={st['yield'] * 100:.0f}% seeds>={st['seed_base']}")
    print(f"[dataset] {root}")
    print(f"[npz]     {npz_path}")
    print(f"[card]    {root / 'MG_DATASET_CARD.json'}")
    print("[回读自证] len={} frames(meta)={} state={} action={} img={} {}".format(
        len(ds2), ds2.meta.total_frames, card["reread"]["state_shape"], card["reread"]["action_shape"],
        card["reread"]["img_base_shape"], card["reread"]["img_base_dtype"]))
    print("[action 统计] gripper: mean={:.3f} +1 占比={:.2f} -1 占比={:.2f}".format(
        card["action_stats"]["gripper"]["mean"], card["action_stats"]["gripper"]["frac_at_plus1"],
        card["action_stats"]["gripper"]["frac_at_minus1"]))
    print("[下一步] bash -c 'source code/env.sh && $MG_PY code/mg_probe.py --replay {}'".format(npz_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
