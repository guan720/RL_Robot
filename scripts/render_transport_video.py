#!/usr/bin/env python
"""把阶段 2 的搬运过程画成视频：左边看动作，右边看覆盖率怎么长出来。

阶段 1 的 `render_reach_video.py` 回答的是「策略学到了什么」；
这个脚本回答的是阶段 2 的三个新问题，而且是**看得见**的版本：

    1. reset-free 交替到底长什么样？
       -> alternate 那一行里，物体会在 A/B 之间来回走，从不消失；
          fixed 那一行里，物体每完成一个 task 就「瞬移」回源区域（那就是一次人工复位）。
    2. 覆盖率是怎么积累的？
       -> 右侧热力图随步数一格一格点亮。你会看到目标格子（外生、均匀）点得很快，
          而起始格子（内生）在策略不可靠时只点亮一小片。
    3. 救场什么时候触发？
       -> 卡住 120 步时物体会被规则摆回源区域，HUD 上的 stall 计数 +1。

用法：
    # 用训练好的 SAC 策略，交替 vs 人工复位并排看
    python scripts/render_transport_video.py --run runs/xxx_sac_transport_alternate --steps 400
    # 看不可靠策略怎么塌缩（biased 脚本策略，舒适区 6cm）
    python scripts/render_transport_video.py --policy biased --easy-radius 0.06 --steps 600
    # 看完全不可靠时救场怎么兜底
    python scripts/render_transport_video.py --policy random --steps 600
    # 只渲染一种模式
    python scripts/render_transport_video.py --modes alternate --policy perfect

输出：<run 目录>/transport_<policy>.mp4（或 --out 指定的路径）
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

ensure_venv("numpy", "matplotlib", "yaml", "imageio")

import matplotlib  # noqa: E402

matplotlib.use("Agg")          # 本机无显示器，必须离屏
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

# 环境构造统一走 eval/transport_eval.make_env：这样 --env-factory perturbed 就能渲带扰动的版本，
# 而渲染代码本身一行都不用改（两套环境暴露的状态字段完全一样）。
from eval.transport_eval import ABSTRACT, make_env  # noqa: E402
from scripts.compare_reset_modes import (  # noqa: E402
    PDController,
    PController,
    RandomPolicy,
    region_center,
)

MODE_LABEL = {"alternate": "ALTERNATE (reset-free)", "fixed": "FIXED (human reset every task)"}
MODE_COLOR = {"alternate": "#2f7ed8", "fixed": "#e8a33d"}


def build_policy(kind: str, ckpt: str, easy_radius: float, kp: float = 1.0, kd: float = 0.5):
    if kind == "random":
        return RandomPolicy(0), "random"
    if kind == "perfect":
        return PController(0, easy_radius=None), "perfect (P-controller)"
    if kind == "pd":
        return PDController(0, easy_radius=None, kp=kp, kd=kd), f"PD controller (kp={kp:g}, kd={kd:g})"
    if kind == "biased":
        return PController(0, easy_radius=easy_radius, behavior="freeze"), f"biased (easy_r={easy_radius})"
    if kind == "ckpt":
        from scripts.eval_policy import load_any_policy

        model, algo = load_any_policy(ckpt)

        class _Wrap:
            def act(self, obs, info, prm):
                action, _ = model.predict(obs.astype(np.float32), deterministic=True)
                return np.asarray(action, dtype=np.float32).reshape(2)

        return _Wrap(), f"trained {algo} ({Path(ckpt).name})"
    raise SystemExit(f"未知 policy：{kind}")


def _snapshot(env) -> dict:
    """环境当前的三类格子集合（内部就是 (i, j) 元组键）。"""
    return {"pick": set(env.pick_cell_counts), "place": set(env.place_cell_counts),
            "start": set(env.start_cell_counts)}


def record_rollout(policy, mode: str, env_kwargs: dict, steps: int, seed: int,
                   env_factory: str = ABSTRACT) -> dict:
    """跑满 steps 步（跨多局），把每一步的状态和每个格子事件都记下来供逐帧重放。

    两个容易踩的点：
      1. 一局只有 max_steps=400 步，所以必须跨局续跑，否则 --steps 2000 只会渲出 401 帧；
      2. 环境的计数器在 reset() 时清零，事件检测的「上一帧快照」也必须跟着重置，
         否则跨局之后 diff 永远为空，热力图就不再点亮了。
    """
    from eval.transport_eval import merge_episode_reports, summarize

    env = make_env(dict(env_kwargs, reset_mode=mode), env_factory)
    # 有状态的控制器的钩子（PD 用上一帧位置估速度，跨局必须清掉）
    on_episode_start = getattr(policy, "on_episode_start", None)
    prm = {"half": env.half, "gap": env.gap, "action_scale": env.action_scale}
    grid_n = env.grid_n

    def cell_of(pos):
        u = np.clip((pos + env.half) / (2 * env.half), 0.0, 1.0 - 1e-9)
        idx = (u * grid_n).astype(int)
        return int(idx[0]), int(idx[1])

    frames: list[dict] = []
    events: list[tuple] = []        # (step, kind, cell)：kind ∈ start / pick / place
    reports: list[dict] = []

    obs, info = env.reset(seed=seed)
    if on_episode_start is not None:
        on_episode_start(obs, info)
    prev = _snapshot(env)
    events.append((0, "start", cell_of(env.obj)))
    episodes = 1
    t = 0

    def push_frame(step: int) -> None:
        frames.append({
            "t": step, "ee": env.ee.copy(), "obj": env.obj.copy(), "target": env.target.copy(),
            "held": bool(env.held), "direction": env.direction, "phase": info["phase"],
            "tasks": info["tasks_done"], "manual_resets": info["manual_resets"],
            "fixed_resets": info["fixed_resets"], "episode": episodes,
        })

    push_frame(t)
    while t < steps:
        action = policy.act(obs, info, prm)
        obs, _r, _term, truncated, info = env.step(action)
        t += 1
        # 事件检测：靠环境里的格子集合有没有变大来判定，不重写环境的判定逻辑
        snap = _snapshot(env)
        for cell in snap["pick"] - prev["pick"]:
            events.append((t, "pick", cell))
        for cell in snap["place"] - prev["place"]:
            events.append((t, "place", cell))
        for cell in snap["start"] - prev["start"]:
            events.append((t, "start", cell))
        prev = snap
        push_frame(t)
        if truncated:
            reports.append(env.coverage_report())
            obs, info = env.reset(seed=seed + t)
            if on_episode_start is not None:
                on_episode_start(obs, info)
            episodes += 1
            prev = _snapshot(env)
            for cell in prev["start"]:
                events.append((t, "start", cell))
    reports.append(env.coverage_report())

    merged = merge_episode_reports(reports)
    summary = summarize(merged, t, grid_n * grid_n, 30.0)
    return {"mode": mode, "frames": frames, "events": events, "summary": summary,
            "report": merged, "episodes": episodes, "steps": t,
            "grid_n": grid_n, "half": env.half, "gap": env.gap,
            "pick_radius": env.pick_radius, "place_radius": env.place_radius}


def events_to_grid(events: list, upto: int, kind: str, grid_n: int) -> np.ndarray:
    grid = np.zeros((grid_n, grid_n), dtype=np.float64)
    for step, event_kind, cell in events:
        if step <= upto and event_kind == kind:
            grid[cell[1], cell[0]] += 1.0
    return grid


def draw_frame(rollouts: list[dict], t: int, policy_label: str, fig_title: str) -> np.ndarray:
    n = len(rollouts)
    fig = plt.figure(figsize=(6.4 * 2, 4.5 * n + 0.6))
    for row, roll in enumerate(rollouts):
        frames, mode = roll["frames"], roll["mode"]
        idx = min(t, len(frames) - 1)
        frame = frames[idx]
        half, gap = roll["half"], roll["gap"]

        # ---- 左：桌面俯视图
        ax = fig.add_subplot(n, 2, row * 2 + 1)
        ax.add_patch(plt.Rectangle((-half, -half), half - gap, 2 * half, color="#eef3fb"))
        ax.add_patch(plt.Rectangle((gap, -half), half - gap, 2 * half, color="#fdf3e7"))
        for boundary in (-gap, gap):
            ax.axvline(boundary, color="#999999", linestyle=":", linewidth=1.0)
        trail = np.array([f["ee"] for f in frames[:idx + 1]])
        if len(trail) > 1:
            ax.plot(trail[:, 0], trail[:, 1], "-", color=MODE_COLOR[mode], linewidth=0.9, alpha=0.55)
        # 目标（绿星 + 放置圈）与物体（橙色方块 + 抓取圈）
        ax.plot(*frame["target"], marker="*", color="#2ecc71", markersize=15, markeredgecolor="#178a4c")
        ax.add_patch(plt.Circle(frame["target"], roll["place_radius"], fill=False,
                                color="#2ecc71", linestyle="--", linewidth=1.0))
        ax.plot(*frame["obj"], marker="s", color="#e8537d", markersize=10, markeredgecolor="black")
        ax.add_patch(plt.Circle(frame["obj"], roll["pick_radius"], fill=False,
                                color="#e8537d", linestyle="--", linewidth=1.0))
        ax.plot(*frame["ee"], marker="o", color=MODE_COLOR[mode], markersize=9,
                markeredgecolor="black", zorder=5)
        ax.annotate("A", (-half * 0.85, half * 0.85), fontsize=10, color="#7a8ca3")
        ax.annotate("B", (half * 0.78, half * 0.85), fontsize=10, color="#c39a6b")
        ax.set_xlim(-half, half)
        ax.set_ylim(-half, half)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        arrow = "A -> B" if frame["direction"] == "forward" else "B -> A"
        holding = "HOLDING" if frame["held"] else "empty"
        # info 里的 tasks_done / resets 每局清零，所以 HUD 用跨局累计的事件数
        done_total = sum(1 for st, kind, _c in roll["events"] if st <= idx and kind == "place")
        ax.set_title(f"{MODE_LABEL[mode]}   step {idx}  (episode {frame.get('episode', 1)})\n"
                     f"tasks done {done_total}  now: {arrow}  {frame['phase']}/{holding}  "
                     f"stall resets {frame['manual_resets']}  human resets {frame['fixed_resets']}",
                     fontsize=9)

        # ---- 右：覆盖率随时间积累（起始格子 vs 请求目标格子）
        ax2 = fig.add_subplot(n, 2, row * 2 + 2)
        start_grid = events_to_grid(roll["events"], idx, "start", roll["grid_n"])
        place_grid = events_to_grid(roll["events"], idx, "place", roll["grid_n"])
        peak = max(start_grid.max(), place_grid.max(), 1.0)
        ax2.imshow(start_grid, origin="lower", cmap="Blues", vmin=0, vmax=peak,
                   extent=[-half, half, -half, half])
        ax2.contour(np.arange(roll["grid_n"]), np.arange(roll["grid_n"]), place_grid.T,
                    levels=[0.5], colors="#2ecc71", linewidths=1.2,
                    extent=[0, roll["grid_n"] - 1, 0, roll["grid_n"] - 1])
        for boundary in (-gap, gap):
            ax2.axvline(boundary, color="#666666", linestyle=":", linewidth=1.0)
        n_start = int((start_grid > 0).sum())
        n_place = int((place_grid > 0).sum())
        total = roll["grid_n"] ** 2
        ax2.set_title(f"coverage so far: start {n_start}/{total} cells, place {n_place}/{total}\n"
                      f"blue = experienced starts, green outline = achieved placements",
                      fontsize=9)
        ax2.set_xticks([])
        ax2.set_yticks([])

    fig.suptitle(f"{fig_title}  ·  policy: {policy_label}", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.canvas.draw()
    image = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
    plt.close(fig)
    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="", help="train_transport.py 的 run 目录（取 model_final.zip）")
    parser.add_argument("--ckpt", default="", help="直接给模型 .zip；优先级高于 --run")
    parser.add_argument("--policy", default="",
                        choices=["", "ckpt", "random", "perfect", "biased", "pd"],
                        help="渲染哪个策略；给了 --run/--ckpt 就是 ckpt")
    parser.add_argument("--pd-kp", type=float, default=1.0, help="policy=pd 时的比例增益")
    parser.add_argument("--pd-kd", type=float, default=0.5, help="policy=pd 时的微分增益")
    parser.add_argument("--env-factory", default="", choices=["", "abstract", "perturbed"],
                        help="覆盖 config 顶层的 env_factory（perturbed = 带扰动的搬运环境）")
    parser.add_argument("--modes", default="alternate,fixed")
    parser.add_argument("--recovery-mode", default="resample", choices=["resample", "home"],
                        help="救场时把物体放哪：resample=均匀重采样 / home=固定 home 点。"
                             "想看覆盖塌缩最明显的版本用 home")
    parser.add_argument("--steps", type=int, default=400, help="渲染多少环境步（一局是 400 步）")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--easy-radius", type=float, default=0.06, help="policy=biased 时的舒适区半径")
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "transport_sac.yaml"))
    parser.add_argument("--out", default="", help="输出 mp4 路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = {}
    if Path(args.config).exists():
        cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    env_kwargs = dict(cfg.get("env", {}))
    env_kwargs.pop("reset_mode", None)
    env_kwargs["recovery_mode"] = args.recovery_mode
    env_factory = (args.env_factory or str(cfg.get("env_factory", ABSTRACT))).lower()

    ckpt = args.ckpt
    if not ckpt and args.run:
        run_dir = Path(args.run)
        if not run_dir.is_absolute():
            run_dir = REPO_ROOT / run_dir
        ckpt = str(run_dir / "model_final.zip")
    kind = args.policy or ("ckpt" if ckpt else "perfect")
    if kind == "ckpt" and not ckpt:
        raise SystemExit("--policy ckpt 需要 --run 或 --ckpt")
    policy, label = build_policy(kind, ckpt, args.easy_radius, args.pd_kp, args.pd_kd)
    if env_factory == "perturbed":
        label += " · perturbed env"

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    rollouts = []
    for mode in modes:
        roll = record_rollout(policy, mode, env_kwargs, args.steps, args.seed, env_factory)
        m = roll["summary"]
        print(f"  [{mode:<9}] {roll['steps']} 步 / {roll['episodes']} 局  "
              f"完成任务 {m['tasks_done']:>4}（正 {m['success_forward']} / 反 {m['success_backward']}）"
              f"  掉物 {m['slip_events']:>3}  撞飞 {m['push_events']:>3}"
              f"  成功率 {m['success_rate'] * 100:>5.1f}%"
              f"  救场 {m['manual_resets']:>3}  人工复位 {m['fixed_resets']:>4}"
              f"  起始格子 {m['start_cells']:>2}/{roll['grid_n'] ** 2}"
              f"  起始熵 {m['entropy_start']:.3f}"
              f"  放置格子 {m['place_cells']:>2}")
        rollouts.append(roll)

    out_path = Path(args.out) if args.out else None
    if out_path is None:
        base = Path(args.run) if args.run else REPO_ROOT / "runs" / "transport_video"
        if not base.is_absolute():
            base = REPO_ROOT / base
        base.mkdir(parents=True, exist_ok=True)
        suffix = f"_{args.recovery_mode}" if args.recovery_mode != "resample" else ""
        # 带扰动的视频另起文件名，别把阶段 2 的抽象环境版本覆盖掉
        suffix += "_perturbed" if env_factory == "perturbed" else ""
        out_path = base / f"transport_{kind}{suffix}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import imageio

    n_frames = min(args.steps + 1, max(len(r["frames"]) for r in rollouts))
    print(f"  渲染 {n_frames} 帧 @ {args.fps} fps -> {out_path}")
    title = "Stage 2 bidirectional transport"
    writer = imageio.get_writer(str(out_path), fps=args.fps, codec="libx264", quality=8)
    for t in range(n_frames):
        writer.append_data(draw_frame(rollouts, t, label, title))
    writer.close()

    print(f"  视频已保存: {out_path}")
    print()
    print("  怎么读：")
    print("    · ALTERNATE 行：物体一直在桌上，被来回搬（反向任务就是复位），human resets 恒为 0。")
    print("    · FIXED 行：每完成一个 task，物体就瞬移回源区域 —— 那是一次人工复位，计数 +1。")
    print("    · 右侧蓝格 = 策略**实际经历过**的起始位置，绿框 = 它**真正做到**的放置位置。")
    print("      请求的目标是均匀采样的，所以如果蓝格只点亮一小片，就是覆盖塌缩本身。")
    print("    · 卡住 120 步时物体会被规则摆回源区域，stall resets +1，这就是「两者都失败时谁复位」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
