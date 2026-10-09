#!/usr/bin/env python
"""在真实物理仿真里「看见成功」：手写控制器让 Panda 真的把方块抓起来。

为什么要这个脚本？前面 Reach 的成功只是一个点进入半径 30mm 的球，太抽象。
这个脚本用 **robosuite + MuJoCo 物理引擎**（有重力、接触、摩擦），
跑一个**不用学习**的手写状态机控制器，把方块真的拎离桌面，并录成视频。

它要回答你问的那个问题：**「成功」到底是怎么体现的？**

    1. 仿真器自己的判定：robosuite `Lift._check_success()` 只有一行
           cube_height > table_height + 0.04
       即方块中心的 z 坐标比桌面高 4cm。这是**物理事实**，不是模型说了算。
    2. 奖励：`reward()` 在成功的那一步给 +1，之前全是 0（稀疏奖励）。
    3. 画面：你能在 mp4 里看到方块离开桌面、悬在空中。

三条互相印证，这就是「成功」在仿真里的完整证据链。
后面接 RL / 接大模型时，判定**仍然**用第 1 条，永远不要让模型自己说「我成功了」。

控制器是一个 5 阶段状态机（完全不学习，纯规则）：

    approach  末端水平移到方块正上方 12cm 处
    descend   垂直下降到夹爪中心比方块中心高 1.5cm
    grasp     夹爪闭合 20 步（约 1 秒）
    lift      夹爪保持闭合，末端全速上升，直到方块离桌面 > 6cm
    hold      悬停 40 步，让你看清楚

动作语义（robosuite 默认 OSC_POSE）：
    action[0:3] 末端 xyz 位移增量，[-1,1] 对应每步最多 5cm
    action[3:6] 姿态增量，这里恒为 0（保持初始朝下的姿态）
    action[6]   夹爪，-1 开 / +1 合

用法：
    MUJOCO_GL=egl python scripts/demo_scripted_lift.py --episodes 3
    MUJOCO_GL=egl python scripts/demo_scripted_lift.py --episodes 1 --verbose   # 打印每步状态
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("robosuite", "numpy", "imageio")

import numpy as np  # noqa: E402

# OSC_POSE 每步最大位移 5cm，用它把「目标差」换算成 [-1,1] 的动作
STEP_SCALE = 0.05
PRE_HEIGHT = 0.12      # 预抓取高度：方块上方 12cm
GRASP_OFFSET = 0.015   # 抓取时夹爪中心比方块中心高 1.5cm
XY_TOL = 0.006         # 水平对准容差 6mm
Z_TOL = 0.006          # 垂直到位容差 6mm
GRASP_STEPS = 20       # 闭合夹爪的步数
LIFT_TARGET = 0.06     # 方块离桌面 6cm 算拎起来了（仿真判定线是 4cm）
HOLD_STEPS = 40


class LiftStateMachine:
    """5 阶段状态机。输入 obs，输出 7 维 action。"""

    def __init__(self, table_z: float) -> None:
        self.table_z = table_z
        self.phase = "approach"
        self.phase_step = 0
        self.log: list[str] = ["approach"]

    def _set(self, phase: str) -> None:
        self.phase = phase
        self.phase_step = 0
        self.log.append(phase)

    def __call__(self, obs: dict) -> np.ndarray:
        eef = obs["robot0_eef_pos"]
        cube = obs["cube_pos"]
        self.phase_step += 1

        if self.phase == "approach":
            target = cube + np.array([0.0, 0.0, PRE_HEIGHT])
            if (abs(eef[0] - cube[0]) < XY_TOL and abs(eef[1] - cube[1]) < XY_TOL
                    and eef[2] > cube[2] + PRE_HEIGHT - 0.02):
                self._set("descend")
        elif self.phase == "descend":
            target = cube + np.array([0.0, 0.0, GRASP_OFFSET])
            if (abs(eef[2] - cube[2] - GRASP_OFFSET) < Z_TOL
                    and abs(eef[0] - cube[0]) < XY_TOL and abs(eef[1] - cube[1]) < XY_TOL):
                self._set("grasp")
        elif self.phase == "grasp":
            target = cube + np.array([0.0, 0.0, GRASP_OFFSET])
            if self.phase_step >= GRASP_STEPS:
                self._set("lift")
        elif self.phase == "lift":
            target = eef + np.array([0.0, 0.0, 0.3])   # 全速上升
            if cube[2] > self.table_z + LIFT_TARGET:
                self._set("hold")
        else:  # hold
            target = eef.copy()

        delta = target - eef
        action = np.zeros(7, dtype=np.float32)
        action[:3] = np.clip(delta / STEP_SCALE, -1.0, 1.0)
        if self.phase in ("grasp", "lift", "hold"):
            action[6] = 1.0        # 闭合夹爪
        else:
            action[6] = -1.0       # 张开
        return action


def run_episode(env, seed: int, verbose: bool, video_writer, camera: str, size: int,
                annotate: bool = False) -> dict:
    obs = env.reset()
    if not isinstance(obs, dict):
        obs = obs[0] if isinstance(obs, tuple) else obs
    table_z = float(env.model.mujoco_arena.table_offset[2])
    ctrl = LiftStateMachine(table_z)
    success_step = -1
    total_reward = 0.0
    steps = 0
    cube_z_trace = []
    trace = {"step": [], "phase": [], "action": [], "eef": [], "cube_z": [],
             "reward": [], "lifted": [], "frame": []}

    while steps < env.horizon:
        action = ctrl(obs)
        out = env.step(action)
        if len(out) == 5:
            obs, reward, terminated, truncated, info = out
        else:
            obs, reward, terminated, info = out
            truncated = False
        total_reward += float(reward)
        steps += 1
        cube_z = float(obs["cube_pos"][2])
        cube_z_trace.append(cube_z)
        lifted = cube_z > table_z + 0.04
        trace["step"].append(steps)
        trace["phase"].append(ctrl.phase)
        trace["action"].append(np.asarray(action, dtype=np.float64).copy())
        trace["eef"].append(np.asarray(obs["robot0_eef_pos"], dtype=np.float64).copy())
        trace["cube_z"].append(cube_z)
        trace["reward"].append(float(reward))
        trace["lifted"].append(bool(lifted))
        if annotate:
            frame = np.asarray(obs.get(f"{camera}_image"), dtype=np.uint8)
            if frame is None:
                frame = np.asarray(env.sim.render(camera_name=camera, height=size, width=size),
                                  dtype=np.uint8)
            trace["frame"].append(frame[::-1].copy())   # bottom-up -> 正常朝向
        if lifted and success_step < 0:
            success_step = steps
        if info.get("success") and success_step < 0:
            success_step = steps

        if verbose and steps % 20 == 0:
            eef = obs["robot0_eef_pos"]
            print(f"    step {steps:4d} phase={ctrl.phase:<8} eef_z={eef[2]:.3f} "
                  f"cube_z={cube_z:.3f} lifted={lifted} reward={reward:.1f}")

        if video_writer is not None:
            frame = np.asarray(obs.get(f"{camera}_image"), dtype=np.uint8)
            if frame is None:
                frame = np.asarray(env.sim.render(camera_name=camera, height=size, width=size),
                                  dtype=np.uint8)
            # MuJoCo 像素是 bottom-up，必须上下翻转（robosuite 官方脚本同样这么干）
            video_writer.append_data(frame[::-1])

        if ctrl.phase == "hold" and ctrl.phase_step >= HOLD_STEPS:
            break
        if terminated or truncated:
            break

    return {
        "seed": seed,
        "steps": steps,
        "trace": trace,
        "reward": round(total_reward, 3),
        "success": bool(env._check_success()) if hasattr(env, "_check_success") else success_step >= 0,
        "success_step": success_step,
        "final_cube_z": round(cube_z_trace[-1], 4) if cube_z_trace else None,
        "table_z": round(table_z, 4),
        "success_threshold_z": round(table_z + 0.04, 4),
        "phases": ctrl.log,
    }


def plot_keyframe_sheet(trace: dict, table_z: float, out_path: Path, n: int = 9) -> None:
    """把「状态机每个阶段的代表性画面 + 当步指令」拼成一张联系表。

    为什么不用在 mp4 上烧字：视频编码器路径上叠字出现过伪影，而联系表走
    matplotlib.imshow，像素一对一、绝不翻转，适合放进文档和汇报。
    每格标题就是状态机在那一步的完整状态：相位 / 7 维指令 / 两个关键高度。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    frames = trace["frame"]
    if not frames:
        return
    idx = np.linspace(0, len(frames) - 1, min(n, len(frames))).astype(int)
    cols = 3
    rows = int(np.ceil(len(idx) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.1 * cols, 4.6 * rows))
    axes = np.atleast_1d(axes).reshape(-1)
    for ax, i in zip(axes, idx):
        ax.imshow(frames[i])
        a = trace["action"][i]
        ax.set_title(
            f"step {trace['step'][i]:3d}  [{trace['phase'][i]}]\n"
            f"cmd dx={a[0]:+.2f} dy={a[1]:+.2f} dz={a[2]:+.2f} grip={a[6]:+.0f}\n"
            f"eef_z={trace['eef'][i][2]:.3f}  cube_z={trace['cube_z'][i]:.3f} "
            f"(need >{table_z + 0.04:.2f})  lifted={trace['lifted'][i]}",
            fontsize=8, color=PHASE_COLORS.get(trace["phase"][i], "black"))
        ax.set_xticks([])
        ax.set_yticks([])
    for ax in axes[len(idx):]:
        ax.axis("off")
    fig.suptitle("State machine applied step by step — each panel is one control step (20 Hz)",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


PHASE_COLORS = {"approach": "#4c9be8", "descend": "#e8a33d", "grasp": "#cc4444",
                "lift": "#2ecc71", "hold": "#9b59b6"}


def plot_action_trace(trace: dict, table_z: float, out_path: Path) -> None:
    """把「状态机发出的指令」和「物理世界的响应」画在同一张时间轴上。

    这是理解「状态机怎么应用」的关键图：
      第 1 行：action[0:3]，状态机每步发给 OSC_POSE 控制器的位移指令（[-1,1]，每步最多 5cm）
      第 2 行：action[6]，夹爪指令（-1 开 / +1 合）
      第 3 行：eef_z 与 cube_z 的真实高度，加成功判定线 table_z+0.04
      第 4 行：相位色带（状态机当前处于哪个阶段）

    对着视频看：色带切换的瞬间，就是视频里机械臂行为改变的那一刻。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    steps = np.asarray(trace["step"])
    actions = np.asarray(trace["action"])
    eef = np.asarray(trace["eef"])
    cube_z = np.asarray(trace["cube_z"])
    phases = trace["phase"]

    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True,
                             gridspec_kw={"height_ratios": [1.1, 0.6, 1.1, 0.45]})

    axes[0].plot(steps, actions[:, 0], label="action[0] dx", lw=1.4)
    axes[0].plot(steps, actions[:, 1], label="action[1] dy", lw=1.4)
    axes[0].plot(steps, actions[:, 2], label="action[2] dz", lw=1.6)
    axes[0].axhline(0, color="black", lw=0.7, ls=":")
    axes[0].set_ylabel("translation cmd\n([-1,1] = +-5cm/step)")
    axes[0].set_ylim(-1.15, 1.15)
    axes[0].legend(ncol=3, fontsize=8, loc="upper right")
    axes[0].set_title("What the state machine commands vs what the physics does (one Lift episode)")
    axes[0].grid(alpha=0.25)

    axes[1].step(steps, actions[:, 6], where="post", color="#cc4444", lw=1.6)
    axes[1].set_ylabel("gripper cmd\n(-1 open / +1 close)")
    axes[1].set_ylim(-1.5, 1.5)
    axes[1].set_yticks([-1, 1])
    axes[1].grid(alpha=0.25)

    axes[2].plot(steps, eef[:, 2], label="eef_z (gripper center)", lw=1.5, color="#2f7ed8")
    axes[2].plot(steps, cube_z, label="cube_z (cube center)", lw=1.8, color="#e67e22")
    axes[2].axhline(table_z, color="gray", ls=":", lw=1.2, label=f"table top = {table_z:.2f}")
    axes[2].axhline(table_z + 0.04, color="#2ecc71", ls="--", lw=1.4,
                    label=f"success line = {table_z + 0.04:.2f}")
    axes[2].set_ylabel("height (m)")
    axes[2].legend(ncol=2, fontsize=8, loc="lower right")
    axes[2].grid(alpha=0.25)

    # 相位色带
    ax = axes[3]
    start = 0
    for i in range(1, len(phases) + 1):
        if i == len(phases) or phases[i] != phases[start]:
            ax.broken_barh([(steps[start], steps[i - 1] - steps[start] + 1)], (0, 1),
                           facecolors=PHASE_COLORS.get(phases[start], "#888888"), alpha=0.85)
            mid = (steps[start] + steps[i - 1]) / 2
            ax.text(mid, 0.5, phases[start], ha="center", va="center", fontsize=9, color="white")
            start = i
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("control step (20 Hz, so 20 steps = 1 second)")
    ax.grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--camera", default="frontview")
    parser.add_argument("--video-size", type=int, default=320)
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--annotate", action="store_true",
                        help="额外产出 keyframes_ep*.png：9 个关键帧 + 每步状态机指令的联系表")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    os.environ.setdefault("MUJOCO_GL", "egl")
    import robosuite as suite

    out_dir = Path(args.out) if args.out else REPO_ROOT / "runs" / "scripted_lift" / time.strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    env = suite.make(
        env_name="Lift", robots="Panda",
        has_renderer=False,
        has_offscreen_renderer=not args.no_video,
        use_camera_obs=not args.no_video,
        camera_names=args.camera if not args.no_video else None,
        camera_heights=args.video_size,
        camera_widths=args.video_size,
        reward_shaping=False,
        use_object_obs=True,
        control_freq=20,
    )

    writer = None
    video_path = None
    if not args.no_video:
        import imageio
        video_path = out_dir / "lift_scripted.mp4"
        writer = imageio.get_writer(str(video_path), fps=20, codec="libx264", quality=8)

    print("=" * 72)
    print("robosuite Lift + 手写状态机控制器（不学习，纯规则）")
    print(f"成功判定（仿真器给的）：cube_z > table_z + 0.04 = "
          f"{float(env.model.mujoco_arena.table_offset[2]) + 0.04:.3f} m")
    print("=" * 72)

    results = []
    for ep in range(args.episodes):
        if args.verbose:
            print(f"  episode {ep}:")
        r = run_episode(env, args.seed + ep, args.verbose, writer, args.camera, args.video_size,
                        annotate=args.annotate)
        trace = r.pop("trace")
        plot_action_trace(trace, r["table_z"], out_dir / f"action_trace_ep{ep}.png")
        if trace["frame"]:
            plot_keyframe_sheet(trace, r["table_z"], out_dir / f"keyframes_ep{ep}.png")
            trace["frame"] = []   # 不写进 result.json，省空间
        np.savez_compressed(out_dir / f"action_trace_ep{ep}.npz",
                            step=np.asarray(trace["step"]), action=np.asarray(trace["action"]),
                            eef=np.asarray(trace["eef"]), cube_z=np.asarray(trace["cube_z"]),
                            reward=np.asarray(trace["reward"]),
                            phase=np.asarray(trace["phase"]))
        results.append(r)
        print(f"  episode {ep}: steps={r['steps']:4d} reward={r['reward']:5.1f} "
              f"success={r['success']}  方块最终 z={r['final_cube_z']} m "
              f"(桌面 {r['table_z']} + 判定线 {r['success_threshold_z']})")
        print(f"             阶段链: {' -> '.join(r['phases'])}")

    if writer is not None:
        writer.close()

    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": "Lift", "robot": "Panda", "controller": "hand-written state machine (no learning)",
        "success_criterion": "cube_z > table_z + 0.04 (robosuite Lift._check_success)",
        "episodes": results,
        "success_rate": round(sum(r["success"] for r in results) / max(1, len(results)), 3),
        "video": str(video_path) if video_path else None,
    }
    (out_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 72)
    print("怎么读")
    print("=" * 72)
    print(f"  成功率 = {payload['success_rate']:.0%}（手写规则在 Lift 上通常 100%）")
    print(f"  视频  : {video_path}")
    print(f"  指令图: {out_dir / 'action_trace_ep0.png'}（状态机指令 vs 物理响应，同一时间轴）")
    print(f"  关键帧: {out_dir / 'keyframes_ep0.png'}（--annotate 时产出，每格标注当步指令与高度）")
    print(f"  结果  : {out_dir / 'result.json'}")
    print()
    print("  「成功」在这里有三重证据，缺一不可：")
    print("    1. 物理事实：方块中心 z 从 ~0.83 升到 >0.84（result.json 里有 final_cube_z）")
    print("    2. 仿真器判定：robosuite 的 _check_success() 返回 True，info['success']=True")
    print("    3. 奖励：成功那一步 reward 从 0 变成 1（稀疏奖励）")
    print("    4. 画面：mp4 里能看到方块悬空")
    print()
    print("  对比一下：随机策略跑 1000 步的成功率是 0%（见 smoke 实验）。")
    print("  这说明 Lift 的难点不在「判定」，而在「怎么把动作序列做对」——")
    print("  而这正是 RL / 模仿学习 / 大模型要解决的问题。")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
