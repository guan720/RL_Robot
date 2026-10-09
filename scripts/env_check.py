#!/usr/bin/env python
"""阶段 0 验收：确认环境装对了，并跑通最小 RL 接口。

做四件事：
  1. 打印关键依赖版本与 GPU 信息
  2. 测试 MuJoCo 离屏渲染（EGL / OSMesa）—— 这是后面录视频的前提
  3. 在自写的 Reach 环境里跑 100 步随机策略，打印 obs / action / reward
  4. 把结果写成 JSON 存到 runs/，方便以后对比

用法：
    python scripts/env_check.py
    python scripts/env_check.py --gl osmesa     # EGL 报错时的退路（纯 CPU 渲染）
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

# 忘了 activate venv 时给出人话提示，而不是甩一堆 traceback
ensure_venv("gymnasium", "numpy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gl", default=os.environ.get("MUJOCO_GL", "egl"), choices=["egl", "osmesa", "glfw"],
                        help="MuJoCo 离屏渲染后端：egl=GPU（首选），osmesa=CPU（退路）")
    return parser.parse_args()


def pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except Exception as exc:  # noqa: BLE001
        return f"NOT INSTALLED ({type(exc).__name__})"


def check_versions(report: dict) -> None:
    print("=" * 68)
    print("[1/4] 依赖版本")
    print("=" * 68)
    report["python"] = sys.version.split()[0]
    report["platform"] = platform.platform()
    report["packages"] = {
        name: pkg_version(dist)
        for name, dist in [
            ("torch", "torch"),
            ("numpy", "numpy"),
            ("mujoco", "mujoco"),
            ("robosuite", "robosuite"),
            ("gymnasium", "gymnasium"),
            ("stable-baselines3", "stable-baselines3"),
            ("py-trees", "py-trees"),
            ("imageio", "imageio"),
            ("imageio-ffmpeg", "imageio-ffmpeg"),
            ("pyyaml", "PyYAML"),
        ]
    }
    for name, version in report["packages"].items():
        print(f"  {name:<20} {version}")

    try:
        import torch

        report["torch_cuda_available"] = bool(torch.cuda.is_available())
        report["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            report["gpu"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
            print(f"  {'GPU':<20} {report['gpu']}")
        else:
            print("  GPU                  不可用（CPU 也能跑 Reach，但 robosuite 图像训练会很慢）")
    except Exception as exc:  # noqa: BLE001
        report["torch_error"] = repr(exc)
        print(f"  torch 导入失败：{exc!r}")


def check_mujoco_render(report: dict, gl: str) -> bool:
    print()
    print("=" * 68)
    print(f"[2/4] MuJoCo 离屏渲染（MUJOCO_GL={gl}）")
    print("=" * 68)
    os.environ["MUJOCO_GL"] = gl
    xml = (
        "<mujoco>"
        "<worldbody>"
        "<light pos='0 0 2' dir='0 0 -1'/>"
        "<body pos='0 0 0.3'><joint type='free'/><geom type='sphere' size='0.1' rgba='0.2 0.6 0.9 1'/></body>"
        "<geom type='plane' size='1 1 0.1'/>"
        "</worldbody>"
        "</mujoco>"
    )
    try:
        import mujoco

        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        renderer = mujoco.Renderer(model, height=64, width=64)
        renderer.update_scene(data)
        image = renderer.render()
        renderer.close()
        report["mujoco_render"] = {"ok": True, "gl": gl, "image_shape": list(image.shape),
                                   "mean_pixel": float(image.mean())}
        print(f"  PASS  渲染成功，图像 shape={image.shape}, 平均像素值={image.mean():.1f}")
        print("        （平均像素值不是 0 说明真的画出了东西，不是黑屏）")
        return True
    except Exception as exc:  # noqa: BLE001
        report["mujoco_render"] = {"ok": False, "gl": gl, "error": repr(exc)}
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        print("        退路：MUJOCO_GL=osmesa python scripts/env_check.py")
        return False


def check_reach_env(report: dict) -> bool:
    print()
    print("=" * 68)
    print("[3/4] 自写 Reach 环境跑 100 步随机策略")
    print("=" * 68)
    import numpy as np

    from envs.reach_env import make_reach_env

    env = make_reach_env()
    rng = np.random.default_rng(0)
    obs, info = env.reset(seed=0)
    print(f"  observation_space = {env.observation_space}   -> obs.shape={obs.shape}")
    print(f"  action_space      = {env.action_space}")
    print(f"  初始 obs = {np.round(obs, 3).tolist()}")
    print("           [ 前 3 维 = 末端位置(归一化) | 后 3 维 = 目标位置(归一化) ]")
    print(f"  初始距离 dist = {info['dist']:.4f} m")

    total_reward = 0.0
    steps = 0
    for _ in range(100):
        action = rng.uniform(-1.0, 1.0, size=env.action_space.shape).astype(np.float32)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        steps += 1
        if terminated or truncated:
            obs, info = env.reset()
    report["reach_random_walk"] = {
        "obs_shape": list(obs.shape),
        "action_shape": list(env.action_space.shape),
        "steps": steps,
        "total_reward": total_reward,
        "final_dist": info["dist"],
    }
    print(f"  100 步随机走：累计 reward={total_reward:.2f}，最后一步 dist={info['dist']:.4f} m")
    print("  说明：随机策略几乎不可能进入 3cm 成功圈，reward 是负的很正常。")
    print("        阶段 1b 训练之后再跑同样的评测，就应该看到成功率 > 0。")
    return True


def check_optional_imports(report: dict) -> None:
    print()
    print("=" * 68)
    print("[4/4] 可选依赖导入检查")
    print("=" * 68)
    print("  说明：每一项都在**独立子进程**里导入。")
    print("        原因是本机实测：同一进程内先用 MuJoCo 建了 EGL 渲染上下文，")
    print("        再导入 torch / tensorflow 会段错误（exit 139）。子进程隔离后互不影响。")
    report["imports"] = {}
    probes = {
        "robosuite": "import robosuite; print('envs=', len(getattr(robosuite, 'ALL_ENVIRONMENTS', [])))",
        "stable_baselines3": "import stable_baselines3 as s; print('version=', s.__version__)",
        "py_trees": "import py_trees, importlib.metadata as m; print('version=', m.version('py-trees'))",
        "gymnasium": "import gymnasium; print('version=', gymnasium.__version__)",
        "yaml": "import yaml; print('version=', yaml.__version__)",
        "imageio": "import imageio; print('version=', imageio.__version__)",
        "imageio_ffmpeg": "import imageio_ffmpeg; print('ffmpeg=', imageio_ffmpeg.get_ffmpeg_exe())",
        "torch_cuda": "import torch; print('cuda=', torch.cuda.is_available(), torch.cuda.get_device_name(0))",
    }
    env = dict(os.environ, MUJOCO_GL=os.environ.get("MUJOCO_GL", "egl"))
    for name, code in probes.items():
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=300)
        detail = (proc.stdout or proc.stderr).strip().splitlines()
        detail = detail[-1] if detail else ""
        if proc.returncode == 0:
            report["imports"][name] = {"ok": True, "detail": detail}
            print(f"  ok    {name:<20} {detail}")
        else:
            signal_note = f"（信号 {-proc.returncode}，通常是段错误）" if proc.returncode < 0 else ""
            report["imports"][name] = {"ok": False, "returncode": proc.returncode, "detail": detail}
            print(f"  FAIL  {name:<20} exit={proc.returncode} {signal_note} {detail[-160:]}")


def main() -> int:
    args = parse_args()
    started = time.time()
    report: dict = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "mujoco_gl_requested": args.gl}

    check_versions(report)
    render_ok = check_mujoco_render(report, args.gl)
    reach_ok = check_reach_env(report)
    check_optional_imports(report)

    report["elapsed_sec"] = round(time.time() - started, 2)
    out_dir = REPO_ROOT / "runs" / "env_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 68)
    print("结论")
    print("=" * 68)
    print(f"  渲染可用: {'是' if render_ok else '否（录视频会失败，先解决这个）'}")
    print(f"  RL 接口可用: {'是' if reach_ok else '否'}")
    print(f"  报告已写入: {out_path}")
    print()
    print("下一步：")
    print("  python scripts/smoke_random_policy.py --task Lift --episodes 1")
    print("  python scripts/train_reach.py --config configs/reach_sac.yaml")
    return 0 if (render_ok and reach_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
