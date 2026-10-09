#!/usr/bin/env python
"""阶段 1a：robosuite 冒烟测试 —— 随机策略跑一个抓取任务，并录成视频。

这个脚本不学习任何东西。它只有三个目的：
  1. 确认 robosuite + MuJoCo + 离屏渲染在这台机器上真的能跑；
  2. 让你亲眼看到 obs 里到底有什么（关节角 / 末端位姿 / 物体位置 / 图像）；
  3. 让你看到 action 的语义（robosuite 默认 OSC_POSE：末端位姿增量 + 夹爪开合）。

用法：
    python scripts/smoke_random_policy.py --task Lift --episodes 1
    python scripts/smoke_random_policy.py --task PickPlaceCan --episodes 2
    MUJOCO_GL=osmesa python scripts/smoke_random_policy.py --task Lift   # EGL 失败时

预期结果：随机策略的成功率基本是 0，这是正常的。重点看 obs 的结构和视频里的行为。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

# 忘了 activate venv 时给出人话提示，而不是甩一堆 traceback
ensure_venv("robosuite", "numpy", "imageio")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", default="Lift",
                        help="robosuite 任务名：Lift / PickPlaceCan / Stack / NutAssembly ...")
    parser.add_argument("--robot", default="Panda", help="机械臂型号，默认 Panda（先用它，教程最多）")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--horizon", type=int, default=0, help="0 表示用任务默认步数上限")
    parser.add_argument("--camera", default="frontview")
    parser.add_argument("--video-size", type=int, default=256)
    parser.add_argument("--no-video", action="store_true", help="不录视频，只跑数值（排障时更快）")
    parser.add_argument("--gl", default=os.environ.get("MUJOCO_GL", "egl"), choices=["egl", "osmesa", "glfw"])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="", help="输出目录，默认 runs/smoke/<时间戳>")
    return parser.parse_args()


def action_bounds(env):
    """robosuite 1.5 用 env.action_spec=(low, high)，1.4 用 env.action_space。两种都兼容。"""
    spec = getattr(env, "action_spec", None)
    if spec is not None:
        return spec[0], spec[1]
    space = env.action_space
    return space.low, space.high


def grab_frame(env, obs, args):
    """取一帧画面。

    robosuite 1.5 的 env.render() 只能开窗口（本机无显示器），所以离屏录视频走两条路：
      1. 首选 obs 里的相机图像 <camera>_image —— 这正是视觉策略（ACT/VLA）实际吃的输入；
      2. 退路 env.sim.render(...) —— 直接问 MuJoCo 要像素。
    """
    import numpy as np

    # MuJoCo 的像素是 bottom-up 的，必须上下翻转才是正常朝向。
    # robosuite 官方自己的 scripts/make_reset_video.py 也是 render(...)[::-1]。
    # 不翻的话视频是倒的（桌面在天上、机械臂吊在下面），很容易误判成「相机装反了」。
    key = f"{args.camera}_image"
    if isinstance(obs, dict) and key in obs:
        return np.asarray(obs[key], dtype=np.uint8)[::-1]
    return np.asarray(env.sim.render(camera_name=args.camera, height=args.video_size,
                                      width=args.video_size), dtype=np.uint8)[::-1]


def unpack_reset(out):
    """robosuite 1.5 是 gymnasium 风格 (obs, info)，1.4 是旧风格 obs。两种都兼容。"""
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], dict):
        return out[0], out[1]
    return out, {}


def unpack_step(out):
    """兼容 5 元组 (obs, r, terminated, truncated, info) 与 4 元组 (obs, r, done, info)。"""
    if len(out) == 5:
        obs, reward, terminated, truncated, info = out
        return obs, reward, bool(terminated), bool(truncated), info
    obs, reward, done, info = out
    return obs, reward, bool(done), False, info


def describe_obs(obs: dict) -> list[dict]:
    """把 obs 字典里每一项的形状打出来，这是理解环境接口的第一步。"""
    import numpy as np

    rows = []
    for key in sorted(obs.keys()):
        value = obs[key]
        if isinstance(value, np.ndarray):
            rows.append({"key": key, "shape": list(value.shape), "dtype": str(value.dtype)})
        else:
            rows.append({"key": key, "shape": None, "dtype": type(value).__name__})
    return rows


def main() -> int:
    args = parse_args()
    os.environ["MUJOCO_GL"] = args.gl

    out_dir = Path(args.out) if args.out else REPO_ROOT / "runs" / "smoke" / time.strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import robosuite as suite

    print("=" * 72)
    print(f"robosuite {suite.__version__} · task={args.task} · robot={args.robot} · MUJOCO_GL={args.gl}")
    print("=" * 72)

    make_kwargs = dict(
        env_name=args.task,
        robots=args.robot,
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
    if args.horizon > 0:
        make_kwargs["horizon"] = args.horizon

    env = suite.make(**make_kwargs)
    rng = np.random.default_rng(args.seed)

    print(f"  action_dim = {env.action_dim}   (前 {env.action_dim - 1} 维是末端位姿增量，最后 1 维是夹爪)")
    act_low, act_high = action_bounds(env)
    print(f"  action 范围 = [{float(act_low.min()):.1f}, {float(act_high.max()):.1f}]")
    print("  horizon = %d 步（每步 1/control_freq = %.3f 秒，共 %.1f 秒仿真时间）"
          % (env.horizon, 1.0 / env.control_freq, env.horizon / env.control_freq))
    print("  动作语义（OSC_POSE 控制器）：")
    print("    action[0:3] = 末端 xyz 位移增量（单位：米/步，相对世界系）")
    print("    action[3:6] = 末端姿态增量（axis-angle 表示）")
    print("    action[6]   = 夹爪，-1 张开 / +1 闭合")

    video_writer = None
    if not args.no_video:
        import imageio

        video_path = out_dir / f"{args.task}_random.mp4"
        video_writer = imageio.get_writer(str(video_path), fps=20)
    else:
        video_path = None

    summary = []
    for episode in range(args.episodes):
        obs, info = unpack_reset(env.reset())
        if episode == 0:
            print()
            print("  第一局 obs 的结构（这就是策略网络的输入）：")
            for row in describe_obs(obs):
                shape = row["shape"]
                print(f"    {row['key']:<34} shape={shape if shape else row['dtype']}")
            print("  重点看这几个（键名随任务变，Lift 里物体叫 cube）：")
            print("    robot0_eef_pos / robot0_eef_quat : 末端位置与姿态（世界系，单位米 / 四元数）")
            print("    cube_pos / cube_quat             : 被操作物体的位置与姿态")
            print("    gripper_to_cube_pos              : 夹爪到物体的相对位置（RL 最有用的一维特征）")
            print("    robot0_joint_pos                 : 七个关节角（弧度）")
            print("    robot0_proprio-state             : 上面机器人相关项拼接好的 50 维向量")
            print("    object-state                     : 物体相关项拼接好的 10 维向量")
            print("    frontview_image                  : 256x256x3 相机图像（use_camera_obs=True 时才有）")

        episode_reward = 0.0
        steps = 0
        success = False
        while True:
            action = rng.uniform(-1.0, 1.0, size=env.action_dim).astype(np.float32)
            obs, reward, terminated, truncated, info = unpack_step(env.step(action))
            episode_reward += float(reward)
            steps += 1
            if isinstance(info, dict) and info.get("success"):
                success = True
            if video_writer is not None:
                video_writer.append_data(grab_frame(env, obs, args))
            if terminated or truncated:
                break

        summary.append({"episode": episode, "steps": steps, "reward": round(episode_reward, 3),
                        "success": bool(success)})
        print()
        print(f"  episode {episode}: steps={steps}, reward={episode_reward:.3f}, success={success}")

    if video_writer is not None:
        video_writer.close()
        print(f"\n  视频已保存: {video_path}")

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": args.task,
        "robot": args.robot,
        "robosuite_version": suite.__version__,
        "mujoco_gl": args.gl,
        "seed": args.seed,
        "episodes": summary,
        "success_rate": round(sum(s["success"] for s in summary) / max(1, len(summary)), 3),
        "video": str(video_path) if video_path else None,
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  结果 JSON: {out_dir / 'result.json'}")
    print()
    print("=" * 72)
    print("怎么读这个结果")
    print("=" * 72)
    print(f"  成功率 = {result['success_rate']:.1%}（随机策略接近 0 是正常的，说明任务确实需要学习）")
    print("  reward 每步都在变 → 这就是 reward 函数的输出，后面 RL 就是最大化它的累计值")
    print("  下一步：python scripts/train_reach.py --config configs/reach_sac.yaml")
    print("         （先在自写的 Reach 环境里学会「参数怎么变」，再回来攻 robosuite 抓取）")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
