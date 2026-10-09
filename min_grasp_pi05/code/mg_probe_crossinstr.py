#!/usr/bin/env python
"""最小抓取链路 · 档 2b 交叉指令探针：策略到底跟着**语言**走，还是跟着**视觉场景**走？

为什么必须有这一测：档 2 把正/反两个任务塞进同一个数据集，唯一的区分线索就是每帧的
task 字符串（`Pick up the can and place it into the bin.` vs
`Take the can out of the bin and put it back into the tray.`）。
如果策略其实吃的是「can 在哪 / 幽灵 can 在不在」这种视觉捷径，那么它对语言是**假条件化**——
换一句指令行为不变。这直接决定档 5 之后 Harness 能不能用语言接管。

2×2 设计（两个假设在交叉格里给出**相反**预测，所以结果可判）：

| 场景 | 正向指令 | 反向指令 |
| --- | --- | --- |
| 正向场景（can 在 bin1 托盘、幽灵 can 在 bin2 象限可见） | 基线：can→bin2 象限 | 交叉：照字符串=「已在托盘里，无处可放」→ 不搬运；照场景=can→bin2 象限 |
| 反向场景（can 在 bin2 象限、幽灵 can 隐藏） | 交叉：照字符串=「已在 bin 里」→ 不搬运；照场景=can→bin1 托盘 | 基线：can→bin1 托盘 |

行为指纹（与成功判据解耦，只看 can 最终去了哪）：
  fwd_like      末态 can 落在 bin2 象限中心 6 cm 内，且初态离象限 > 15 cm（= 真的搬进去了）
  rev_like      末态 can 落在 bin1 托盘中心 9 cm 内，且初态离托盘 > 15 cm
  no_transport  两者都不是，且 can 基本没动（末态离初态 < 5 cm）
  other         动了但两个目标都没到

隔离纪律：本文件只 **import** mg_eval 的 `load_policy` / `to_tensor_obs`（不改它一行），
所以档 1/档 2 正在跑的评测进程完全不受影响。

用法（档 2 训练出检查点后）：
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_crossinstr.py \
        --ckpt runs/pi05_mix60f60r_s2/checkpoints/last/pretrained_model \
        --episodes 10 --n-action-steps 10 --out runs/s2_crossinstr'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from mg_env import CAM_BASE, TASK, SingleArmGraspEnv  # noqa: E402
from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv  # noqa: E402
from mg_eval import load_policy, to_tensor_obs  # noqa: E402

NEAR_QUAD = 0.06      # 「落在 bin2 象限中心附近」
NEAR_TRAY = 0.09      # 「落在 bin1 托盘中心附近」（= REVERSE_TARGET_TOL_XY）
FAR_INIT = 0.15       # 初态离该目标足够远，才谈得上「搬过去了」
NO_MOVE = 0.05        # can 末态离初态这么近 = 没搬运


def anchors(env, scene: str) -> tuple[np.ndarray, np.ndarray]:
    """两个场景共用的两个参照点：bin1 托盘中心、bin2 的 can 象限中心。"""
    tray = np.asarray(env.env.bin1_pos, dtype=np.float64)[:2]
    quad = (np.asarray(env.source_xy, dtype=np.float64) if scene == "reverse"
            else np.asarray(env.target_xy, dtype=np.float64))
    return tray, quad


def fingerprint(can0: np.ndarray, can1: np.ndarray, tray: np.ndarray, quad: np.ndarray) -> str:
    d_quad_0 = float(np.linalg.norm(can0[:2] - quad))
    d_quad_1 = float(np.linalg.norm(can1[:2] - quad))
    d_tray_0 = float(np.linalg.norm(can0[:2] - tray))
    d_tray_1 = float(np.linalg.norm(can1[:2] - tray))
    moved = float(np.linalg.norm(can1[:2] - can0[:2]))
    if d_quad_1 < NEAR_QUAD and d_quad_0 > FAR_INIT:
        return "fwd_like"
    if d_tray_1 < NEAR_TRAY and d_tray_0 > FAR_INIT:
        return "rev_like"
    if moved < NO_MOVE:
        return "no_transport"
    return "other"


def run_cell(policy, pre, post, device, scene: str, instr: str, task_str: str, seed_base: int,
             episodes: int, n_action_steps_req: int, img_size: int, video: bool, max_videos: int,
             out_dir: Path, tag: str) -> dict:
    """一格 = 固定（场景, 指令字符串）跑 episodes 局。scene/instr ∈ {"forward","reverse"}。"""
    env = (ReverseGraspEnv(img_size=img_size) if scene == "reverse"
           else SingleArmGraspEnv(img_size=img_size))
    tray, quad = anchors(env, scene)
    n_action_steps = min(int(n_action_steps_req), int(getattr(policy.config, "chunk_size", 50) or 50))
    policy.config.n_action_steps = n_action_steps
    per_ep = []
    t0 = time.perf_counter()
    for ep in range(episodes):
        seed = seed_base + ep
        obs = env.reset(seed=seed)
        policy.reset()
        can0 = np.asarray(env.object_pos, dtype=np.float64).copy()
        z0 = float(can0[2])
        frames = []
        want_video = video and ep < max_videos
        steps, max_lift, ever_success = 0, 0.0, False
        while True:
            t_obs = to_tensor_obs(obs, device, task=task_str)
            with torch.inference_mode():
                action = post(policy.select_action(pre(t_obs)))
            act = action.squeeze(0).detach().to("cpu").numpy().astype(np.float32)
            obs, _r, terminated, truncated, info = env.step(act)
            steps += 1
            ever_success = ever_success or bool(info["success"])
            max_lift = max(max_lift, float(info["object_pos"][2]) - z0)
            if want_video:
                frames.append(env.render(CAM_BASE))
            if terminated or truncated:
                break
        can1 = np.asarray(info["object_pos"], dtype=np.float64)
        fp = fingerprint(can0, can1, tray, quad)
        per_ep.append({"ep": ep, "seed": seed, "steps": steps, "scene_success": bool(ever_success),
                       "behavior": fp, "max_lift_cm": round(max_lift * 100, 2),
                       "can_init": np.round(can0, 4).tolist(), "can_final": np.round(can1, 4).tolist(),
                       "final_tilt_deg": (round(float(info.get("can_tilt_deg", float("nan"))), 2)
                                          if scene == "reverse" else None),
                       "d_tray_final_cm": round(float(np.linalg.norm(can1[:2] - tray)) * 100, 2),
                       "d_quad_final_cm": round(float(np.linalg.norm(can1[:2] - quad)) * 100, 2)})
        if frames:
            try:
                import imageio.v2 as imageio
                imageio.mimwrite(str(out_dir / f"{tag}_ep{ep}_{'succ' if ever_success else 'fail'}.mp4"),
                                 frames, fps=env.fps)
            except Exception as exc:
                print(f"    [warn] 视频失败：{exc}", flush=True)
        print(f"  [{tag}] ep{ep} seed={seed} 行为={fp:<12} 场景判据成功={ever_success} "
              f"steps={steps} lift={max_lift * 100:.1f}cm "
              f"末态离托盘={per_ep[-1]['d_tray_final_cm']}cm 离象限={per_ep[-1]['d_quad_final_cm']}cm",
              flush=True)
    env.close()
    counts: dict[str, int] = {}
    for e in per_ep:
        counts[e["behavior"]] = counts.get(e["behavior"], 0) + 1
    cell = {"tag": tag, "scene": scene, "instr": instr, "task": task_str, "episodes": episodes,
            "seed_base": seed_base, "seeds_used": [e["seed"] for e in per_ep],
            "n_action_steps": n_action_steps, "cross": bool(scene[0] != instr),
            "scene_success_rate": float(np.mean([e["scene_success"] for e in per_ep])),
            "behavior_counts": counts,
            "dominant_behavior": max(counts, key=counts.get) if counts else None,
            "seconds": round(time.perf_counter() - t0, 1), "per_episode": per_ep}
    print(f"  [{tag}] 小结：场景判据成功率={cell['scene_success_rate'] * 100:.0f}%  行为分布={counts}",
          flush=True)
    return cell


FROZEN_LIFT_CM = 1.0   # can 抬不过 1 cm = 手臂根本没碰它 -> 行为冻结，不是「听懂了所以不搬」
FROZEN_FRAC = 0.8      # 一个格子里冻结局占比超过这个数，本格判「不可判」


def split_no_transport(cell: dict) -> tuple[int, int]:
    """把 `no_transport` 拆成两种机理完全不同的情况（原实现把它们混为一谈）：

      moved  碰过 can 但没搬走（max_lift >= 1 cm）—— 与「指令说它已经在目标位、所以不该搬」
             一致，可以当语言条件化的**弱**证据；
      frozen can 纹丝不动（max_lift < 1 cm）—— 手臂根本没去碰它，是**行为退化/停摆**。

    为什么必须拆：两者的末态指纹（can 还在起点附近）**一模一样**，
    原来的 `follow_string = behavior_counts['no_transport']` 会把「冻结」算成「照字符串走」，
    于是一次策略停摆就能被读成「π₀.₅ 真的在做语言条件化」。2026-10-01 档 2b 实测：
    两个交叉格 40 局 max_lift 全 < 0.3 cm，全部属于 frozen。
    """
    moved = frozen = 0
    for e in cell.get("per_episode", []):
        if e.get("behavior") != "no_transport":
            continue
        if float(e.get("max_lift_cm") or 0.0) >= FROZEN_LIFT_CM:
            moved += 1
        else:
            frozen += 1
    return moved, frozen


def build_verdict(cells: list[dict]) -> tuple[list[dict], bool, str]:
    """从已落盘的 cells 重算判定。返回 (verdict, conclusive, frozen_note)。

    单独成函数是为了让 `--rescore` 也能用它：判定口径改过之后，
    不必为了一个解释重跑 40 局（每局 400 步仿真 + 视频）。
    """
    base = {c["tag"]: c for c in cells}
    verdict = []
    for scene, cross_tag, scene_beh in (("f", "scenef_taskr", "fwd_like"),
                                        ("r", "scener_taskf", "rev_like")):
        c = base.get(cross_tag)
        if not c:
            continue
        cc = c.get("behavior_counts", {})
        ne = int(c.get("episodes", 0))
        follow_scene = cc.get(scene_beh, 0)      # 照场景走 = 仍执行本场景的搬运
        moved, frozen = split_no_transport(c)
        ambiguous = ne - follow_scene - moved - frozen
        item = {"cell": cross_tag, "follow_scene": follow_scene, "follow_string": moved,
                "frozen": frozen, "ambiguous": ambiguous, "episodes": ne}
        if ne and frozen >= FROZEN_FRAC * ne:
            item["read"] = (
                f"**不可判（行为冻结）**：{frozen}/{ne} 局 can 抬不过 {FROZEN_LIFT_CM:.0f} cm，"
                "手臂根本没去碰 can。指令与场景不匹配时策略直接停摆 —— 这**不能**算「照字符串走」"
                "的证据：冻结和「听懂了所以不搬」在末态指纹上完全一样。"
                "要区分得再看手臂有没有朝本场景的目标运动（eef 是否去过 bin/托盘上方）。")
        elif follow_scene > moved + frozen + ambiguous:
            item["read"] = (f"照**场景**走（{follow_scene}/{ne} 仍执行本场景搬运）"
                            "=> 视觉捷径，假语言条件化")
        elif moved > follow_scene + frozen + ambiguous:
            item["read"] = (f"照**指令字符串**走（{moved}/{ne} 碰过 can 但没搬走，另有 {frozen} 局冻结）"
                            "=> 与真语言条件化一致；仍须结合基线格成功率 + conclusion_valid 一起判")
        else:
            item["read"] = (f"不可判：照场景 {follow_scene} / 照字符串 {moved} / 冻结 {frozen} / "
                            f"混杂 {ambiguous}（n={ne} 太小或行为本身混杂，加大 --episodes 再测）")
        verdict.append(item)
    frozen_cells = [v["cell"] for v in verdict
                    if v["episodes"] and v["frozen"] >= FROZEN_FRAC * v["episodes"]]
    conclusive = not frozen_cells and bool(verdict)
    note = ""
    if frozen_cells:
        note = ("交叉格 " + ", ".join(frozen_cells) + f" 里 ≥{FROZEN_FRAC*100:.0f}% 的局是**行为冻结**"
                f"（can 抬不过 {FROZEN_LIFT_CM:.0f} cm），本探针**不能**用来判语言条件化；"
                "它只能证明「指令与场景不匹配时策略会停摆」。")
    return verdict, conclusive, note


def provenance(ckpt: Path) -> tuple[str, bool, str]:
    """查出这个检查点是拿哪个数据集训的，并据此判「语言条件化的结论成不成立」。

    返回 (dataset_root, conclusion_valid, warning)。

    ⚠️ 踩过的坑：lerobot 把 `train_config.json` 写在检查点目录**里面**
    （`checkpoints/0XXXXX/pretrained_model/train_config.json`），不在它的父目录。
    第一版用 `ckpt.parent / "train_config.json"` 去找，恒为空串 ⇒ conclusion_valid=False，
    于是一次**跑对了**的档 2b 探针（40 局行为数据全在）被判成「不可用」白扔掉。
    标志位算错比数据算错更难发现——它只会安静地把结论降级，不会报错。
    """
    train_cfg = ckpt / "train_config.json"
    if not train_cfg.exists():
        train_cfg = ckpt.parent / "train_config.json"
    ds_root = ""
    if train_cfg.exists():
        try:
            ds_root = str(json.loads(train_cfg.read_text()).get("dataset", {}).get("root", ""))
        except Exception:
            ds_root = ""
    valid = bool(ds_root and "mix" in Path(ds_root).name)
    warn = "" if valid else (
        f"这个检查点的数据集是 {ds_root or '未知'}，**不是正反向混合集**："
        "只学过一个 task 字符串的策略在交叉格里必然照场景走（它没有别的可走），"
        "因此本结果只能当**阴性对照/管路自证**，不能当语言条件化的结论。")
    return ds_root, valid, warn


def rescore(summary_dir: Path) -> int:
    """只重算 provenance 三个字段并重写 summary，不重跑任何一局。"""
    f = summary_dir / "crossinstr_summary.json"
    if not f.is_absolute():
        f = MG_ROOT / summary_dir / "crossinstr_summary.json"
    if not f.exists():
        print(f"[err] 找不到 {f}", file=sys.stderr)
        return 2
    summary = json.loads(f.read_text())
    ckpt = Path(summary.get("ckpt", ""))
    if not ckpt.exists():
        print(f"[err] summary 里记的检查点已不存在：{ckpt}", file=sys.stderr)
        return 2
    ds_root, valid, warn = provenance(ckpt)
    old = {"dataset_of_ckpt": summary.get("dataset_of_ckpt"),
           "conclusion_valid": summary.get("conclusion_valid"),
           "probe_conclusive": summary.get("probe_conclusive")}
    summary["dataset_of_ckpt"] = ds_root
    summary["conclusion_valid"] = valid
    verdict, conclusive, frozen_note = build_verdict(summary.get("cells", []))
    summary["verdict"] = verdict
    summary["probe_conclusive"] = bool(valid and conclusive)
    if warn:
        summary["conclusion_warning"] = warn
    else:
        summary.pop("conclusion_warning", None)
    if frozen_note:
        summary["frozen_note"] = frozen_note
    else:
        summary.pop("frozen_note", None)
    summary["rescored_at"] = datetime.now().isoformat(timespec="seconds")
    summary["rescore_note"] = ("只重算了 provenance（--rescore）；cells / per_episode / verdict "
                               "都是原始跑出来的，未经改动。")
    f.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[rescore] {old}\n       -> dataset_of_ckpt={ds_root!r} conclusion_valid={valid} "
          f"probe_conclusive={summary['probe_conclusive']}")
    for v in verdict:
        print(f"  [{v['cell']}] {v['read']}")
    print(f"[rescore] 重写 -> {f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", default="", help="检查点目录（含 config.json + model.safetensors）")
    ap.add_argument("--rescore", default="",
                    help="**不重跑**，只拿已有的 crossinstr_summary.json 重算「数据出处/结论是否可用」"
                         "三个字段并重写。用途：出处判定本身写错过（见 provenance() 注释），"
                         "40 局行为数据是好的，没必要为了一个标志位再烧 20 分钟 GPU。")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0,
                    help="强制所有格子用同一个 seed 起点；0（默认）= 每格用自己场景的 test 区间")
    ap.add_argument("--fwd-seed", type=int, default=2000, help="正向场景格子的 seed 起点（test 区间）")
    ap.add_argument("--rev-seed", type=int, default=7000, help="反向场景格子的 seed 起点（test 区间）")
    ap.add_argument("--n-action-steps", type=int, default=10)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--max-videos", type=int, default=1)
    ap.add_argument("--cells", default="ff,fr,rr,rf",
                    help="要跑哪几格：f/r=场景，第二位 f/r=指令。默认 2 基线 + 2 交叉")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.rescore:
        return rescore(Path(args.rescore))
    if not args.ckpt:
        print("[err] 需要 --ckpt（或 --rescore 只重算已有产物）", file=sys.stderr)
        return 2

    ckpt = Path(args.ckpt)
    if not ckpt.exists():
        print(f"[err] 检查点不存在：{ckpt}", file=sys.stderr)
        return 2
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    policy, pre, post = load_policy(ckpt, device, False)
    out_dir = Path(args.out) if args.out else MG_ROOT / "runs" / "crossinstr"
    out_dir.mkdir(parents=True, exist_ok=True)

    task_of = {"f": TASK, "r": TASK_REVERSE}
    long_of = {"f": "forward", "r": "reverse"}
    cells = []
    for spec in [c.strip() for c in args.cells.split(",") if c.strip()]:
        if len(spec) != 2 or spec[0] not in task_of or spec[1] not in task_of:
            print(f"[err] --cells 的每一项必须是两字母（场景+指令，f/r），收到 {spec!r}", file=sys.stderr)
            return 2
        sc, ins = long_of[spec[0]], spec[1]
        base = args.seed if args.seed else (args.rev_seed if sc == "reverse" else args.fwd_seed)
        tag = f"scene{spec[0]}_task{ins}"
        print(f"\n=== [{tag}] {'交叉' if spec[0] != ins else '基线'}：场景={sc} 指令={ins} "
              f"seeds={base}..{base + args.episodes - 1} eps={args.episodes} "
              f"K={args.n_action_steps} ===", flush=True)
        print(f"    task = {task_of[ins]!r}", flush=True)
        cells.append(run_cell(policy, pre, post, device, sc, ins, task_of[ins], base, args.episodes,
                              args.n_action_steps, args.img_size, args.video, args.max_videos,
                              out_dir, tag))

    summary = {"probe": "crossinstr", "ckpt": str(ckpt), "task_forward": TASK,
               "task_reverse": TASK_REVERSE, "cells": cells,
               "anchors_note": "行为指纹只看 can 末态落在 bin1 托盘 / bin2 象限哪个中心附近，与成功判据解耦"}
    verdict, conclusive, frozen_note = build_verdict(cells)
    summary["verdict"] = verdict
    # 护栏：只有**同时学过两个 task 字符串**的策略才谈得上语言条件化
    ds_root, valid, warn = provenance(ckpt)
    summary["dataset_of_ckpt"] = ds_root
    summary["conclusion_valid"] = valid          # 出处：是不是混合数据集训出来的
    summary["probe_conclusive"] = bool(valid and conclusive)   # 行为：交叉格有没有冻结
    if warn:
        summary["conclusion_warning"] = warn
    else:
        summary.pop("conclusion_warning", None)
    if frozen_note:
        summary["frozen_note"] = frozen_note
    else:
        summary.pop("frozen_note", None)
    (out_dir / "crossinstr_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n=== 2×2 汇总 ===")
    print("| 格子 | 类型 | 场景判据成功率 | 行为分布 |")
    print("| --- | --- | --- | --- |")
    for c in cells:
        print(f"| {c['tag']} | {'交叉' if c['cross'] else '基线'} | {c['scene_success_rate'] * 100:.0f}% "
              f"| {c['behavior_counts']} |")
    for v in verdict:
        print(f"  [{v['cell']}] 照场景={v['follow_scene']} 照字符串={v['follow_string']} "
              f"混杂={v['ambiguous']} => {v['read']}")
    if not summary.get("conclusion_valid", True):
        print(f"\n[警告] {summary['conclusion_warning']}")
    print(f"[saved] {out_dir / 'crossinstr_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
