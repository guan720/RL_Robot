#!/usr/bin/env python
"""最小抓取链路 · 契约探针（不训练、不联网，几十秒跑完）。

为什么先跑它：BC 学不出来时，故障可能在 action/state 对齐、归一化、夹爪语义、动作处理器、
环境执行器、终止判定这六层里的任意一层。把「环境这一侧的物理语义」先用探针钉死，
训练侧出问题就只剩数据格式与模型两类原因。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_probe.py --all'
    ... --determinism --axes --gripper --images --timing --expert --replay data/xxx.npz
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_env import (  # noqa: E402
    ACTION_DIM, ACTION_KEY, CAM_BASE, CAM_WRIST, FIXED_SEED, IMG_KEY_BASE, IMG_KEY_WRIST,
    SingleArmGraspEnv, STATE_DIM, STATE_KEY, STATE_NAMES, TASK,
)
from mg_expert import GRIP_CLOSE, GRIP_OPEN, STEP_SCALE, ScriptedExpert  # noqa: E402

OUT = MG_ROOT / "runs" / "probe"
RESULTS: list[dict] = []


def _record(name: str, passed: bool, detail: str, **extra) -> None:
    RESULTS.append({"probe": name, "pass": bool(passed), "detail": detail, **extra})
    flag = "PASS" if passed else "FAIL"
    print(f"[{flag}] {name}: {detail}", flush=True)


def _img_hash(img: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(img).tobytes()).hexdigest()[:16]


def _open_env(img_size: int = 224) -> SingleArmGraspEnv:
    return SingleArmGraspEnv(img_size=img_size)


# ── 1. 固定初态：同 seed 必须逐位相同（含图像哈希）─────────────────────────────
def probe_determinism(img_size: int = 64) -> None:
    env = _open_env(img_size)
    snaps, imgs = [], []
    for _ in range(2):
        obs = env.reset(seed=FIXED_SEED)
        snaps.append({"snapshot": env.init_state_snapshot(), "state": obs[STATE_KEY].copy()})
        imgs.append((obs[IMG_KEY_BASE].astype(np.int16), obs[IMG_KEY_WRIST].astype(np.int16)))
    same_pose = snaps[0]["snapshot"] == snaps[1]["snapshot"]
    same_state = bool(np.array_equal(snaps[0]["state"], snaps[1]["state"]))
    # 图像不做逐位比较：MuJoCo EGL 离屏渲染有 LSB 抖动（实测最大 1 灰阶、占比 ~2e-5 像素），
    # 等价于传感器噪声，对 BC 无害；状态/物体位姿/qpos 必须逐位一致才算「固定初态」成立。
    diffs = [np.abs(imgs[0][k] - imgs[1][k]) for k in (0, 1)]
    img_max = int(max(d.max() for d in diffs))
    img_frac = float(max((d > 0).mean() for d in diffs))
    img_ok = img_max <= 2 and img_frac < 1e-3
    _record("determinism.fixed_seed", same_pose and same_state and img_ok,
            f"同 seed 两次 reset：初态快照逐位一致={same_pose} 状态向量一致={same_state} "
            f"图像最大差={img_max} 灰阶（占比 {img_frac:.1e}，渲染 LSB 抖动，非状态差异）；"
            f"初态={json.dumps(snaps[0]['snapshot'], ensure_ascii=False)}",
            init_state=snaps[0]["snapshot"], img_max_diff=img_max, img_frac_diff=img_frac)

    env.reset(seed=FIXED_SEED + 777)
    other = env.init_state_snapshot()
    differs = other["object_pos"] != snaps[0]["snapshot"]["object_pos"]
    _record("determinism.seed_changes_scene", differs,
            f"换 seed 后物体位姿变化={differs}（第 2 阶段「随机位姿」的开关就是 seed）："
            f"{np.round(np.asarray(other['object_pos']), 4).tolist()}")
    env.close()


# ── 2. 动作 -> 运动 的轴向、符号、有效增益 ─────────────────────────────────────
def probe_axes(steps: int = 10) -> None:
    """契约里 action=1.0 的**有效**每步位移是实测值，不是控制器 output_max。

    robosuite 1.5.2 default_panda.json：OSC_POSE output_max=0.05 m，但 ramp_ratio=0.2 且
    kp=150 阻抗控制 -> 饱和动作一个控制步只走约 11 mm（实测）。这一层搞错，BC 学到的动作
    量级就会和环境执行器差 4~5 倍（典型的「动作处理器」故障）。
    """
    env = _open_env(64)
    gains = {}
    for axis in range(3):
        env.reset(seed=FIXED_SEED)
        p0 = env.eef_pos.copy()
        act = np.zeros(ACTION_DIM, dtype=np.float32)
        act[axis] = 1.0
        act[6] = GRIP_OPEN
        for _ in range(steps):
            env.step(act)
        disp = env.eef_pos - p0
        dominant = int(np.argmax(np.abs(disp)))
        per_step = float(abs(disp[axis]) / steps)
        gains[axis] = per_step
        ok = dominant == axis and disp[axis] > 0 and 0.005 < per_step < 0.02
        _record(f"axes.action[{axis}]=+1", ok,
                f"位移={np.round(disp, 4).tolist()} 主轴={dominant} 有效增益={per_step * 1000:.2f} mm/步"
                f"（控制器 output_max=50 mm × ramp_ratio=0.2 ≈ 11 mm，实测吻合）",
                displacement=disp.tolist(), measured_step_gain_m=per_step)

    # 线性度：action=0.5 的位移应约为 action=1.0 的一半（说明是比例控制，不是纯 bang-bang）
    env.reset(seed=FIXED_SEED)
    p0 = env.eef_pos.copy()
    act = np.zeros(ACTION_DIM, dtype=np.float32)
    act[0] = 0.5
    act[6] = GRIP_OPEN
    for _ in range(steps):
        env.step(act)
    half = float(abs(env.eef_pos[0] - p0[0]) / steps)
    ratio = half / gains[0]
    _record("axes.proportional", 0.3 < ratio < 0.7, f"action=0.5 的增益是 action=1.0 的 {ratio:.2f} 倍")

    # 姿态三维给 0 时不应有明显姿态漂移
    env.reset(seed=FIXED_SEED)
    q0 = env._last_obs[STATE_KEY][3:7].copy()
    act = np.zeros(ACTION_DIM, dtype=np.float32)
    act[0] = 1.0
    act[6] = GRIP_OPEN
    for _ in range(steps):
        env.step(act)
    drift = float(np.abs(env._last_obs[STATE_KEY][3:7] - q0).max())
    _record("axes.rotation_zeroed", drift < 0.05, f"姿态分量恒 0 时四元数最大漂移={drift:.4f}")
    env.close()


# ── 3. 夹爪语义（最容易反的一层）───────────────────────────────────────────────
def probe_gripper(steps: int = 30) -> None:
    env = _open_env(64)
    env.reset(seed=FIXED_SEED)
    w_open0 = env.gripper_width
    act = np.zeros(ACTION_DIM, dtype=np.float32)
    act[6] = GRIP_CLOSE
    for _ in range(steps):
        env.step(act)
    w_close = env.gripper_width
    act[6] = GRIP_OPEN
    for _ in range(steps):
        env.step(act)
    w_open = env.gripper_width
    ok = w_close < w_open0 - 0.02 and w_open > w_open0 - 0.01 and w_close < w_open
    _record("gripper.semantics", ok,
            f"初始宽度={w_open0:.4f} → +1({GRIP_CLOSE}) {steps} 步后={w_close:.4f} → -1({GRIP_OPEN}) {steps} 步后={w_open:.4f}"
            f"；结论：{'GRIP_CLOSE=+1 为闭合（与 mg_expert 一致）' if ok else '语义与契约相反，必须修 mg_env/mg_expert'}",
            width_initial=w_open0, width_after_close=w_close, width_after_open=w_open)
    env.close()


# ── 4. 图像：形状 / 取值 / 朝向 / 两路相机不同帧 ────────────────────────────────
def probe_images(img_size: int = 224) -> None:
    env = _open_env(img_size)
    obs = env.reset(seed=FIXED_SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    base = obs[IMG_KEY_BASE]
    wrist = obs[IMG_KEY_WRIST]
    shape_ok = base.shape == (img_size, img_size, 3) and wrist.shape == base.shape
    dtype_ok = base.dtype == np.uint8 and wrist.dtype == np.uint8
    distinct = not np.array_equal(base, wrist)
    try:
        from PIL import Image
        Image.fromarray(base).save(OUT / "probe_base.png")
        Image.fromarray(wrist).save(OUT / "probe_wrist.png")
        saved = str(OUT / "probe_base.png")
    except Exception as exc:  # pragma: no cover
        saved = f"保存失败 {exc}"
    # 朝向自检：倒置图像的上半部分应该是背景/远处（更亮或更暗都可，但翻转前后必须不同）
    flipped_diff = float(np.abs(base.astype(np.int32) - base[::-1].astype(np.int32)).mean())
    _record("images.shape_dtype", shape_ok and dtype_ok,
            f"base={base.shape}/{base.dtype} wrist={wrist.shape}/{wrist.dtype}（已按契约上下翻转）")
    _record("images.two_cameras_distinct", distinct, "两路相机不是同一帧")
    _record("images.not_vertically_symmetric", flipped_diff > 1.0,
            f"翻转前后平均像素差={flipped_diff:.2f}（≈0 说明图像本身对称，朝向探针无效）")
    _record("images.saved", Path(str(saved)).exists() if saved.endswith("png") else False,
            f"样帧已存 {saved}；base 均值={base.reshape(-1, 3).mean(0).round(1).tolist()} "
            f"std={base.reshape(-1, 3).std(0).round(1).tolist()}")
    env.close()


# ── 5. 计时：一步多贵（决定采集/评测预算）──────────────────────────────────────
def probe_timing(steps: int = 50, img_size: int = 224) -> None:
    env = _open_env(img_size)
    env.reset(seed=FIXED_SEED)
    act = np.zeros(ACTION_DIM, dtype=np.float32)
    act[6] = GRIP_OPEN
    t0 = time.perf_counter()
    for _ in range(steps):
        env.step(act)
    dt = (time.perf_counter() - t0) / steps
    t0 = time.perf_counter()
    for _ in range(3):
        env.reset(seed=FIXED_SEED)
    dt_reset = (time.perf_counter() - t0) / 3
    _record("timing.step", dt < 0.2, f"单步（含 2 路 {img_size}² 相机）={dt * 1000:.1f} ms，reset={dt_reset * 1000:.0f} ms")
    env.close()


# ── 6. 脚本专家：链路上界 + 示范源可用性 ────────────────────────────────────────
def probe_expert(episodes: int = 3, img_size: int = 224, video: bool = True) -> None:
    env = _open_env(img_size)
    OUT.mkdir(parents=True, exist_ok=True)
    frames: list[np.ndarray] = []
    per_ep = []
    for ep in range(episodes):
        obs = env.reset(seed=FIXED_SEED)      # 第 1 阶段：每局都用同一个固定初态
        expert = ScriptedExpert(env).reset()
        frames_ep = []
        succ_step, raw_step, steps = -1, -1, 0
        last_info: dict = {}
        while steps < env.horizon:
            act = expert()
            obs, _r, terminated, truncated, info = env.step(act)
            steps += 1
            last_info = info
            if info["success_raw"] and raw_step < 0:
                raw_step = steps
            if info["success"] and succ_step < 0:
                succ_step = steps
            if video and ep == 0:
                frames_ep.append(env.render(CAM_BASE))
            if terminated:
                break
        can_z = float(last_info.get("object_pos", [0, 0, float("nan")])[2])
        per_ep.append({"ep": ep, "success": succ_step > 0, "success_step": succ_step,
                       "success_raw_step": raw_step, "steps": steps, "phases": expert.phase_seq,
                       "regrasp": expert.regrasp, "slip": expert.slip,
                       "final_can_z": round(can_z, 4),
                       "resting_z_expected": round(float(last_info.get("resting_z", float("nan"))), 4),
                       "final_success_raw": bool(last_info.get("success_raw"))})
        if ep == 0:
            frames = frames_ep
        print(f"    ep{ep} strict_success={succ_step > 0} step={succ_step} raw_step={raw_step} steps={steps} "
              f"can_z={can_z:.4f}(静止预期 {last_info.get('resting_z', float('nan')):.4f}) "
              f"slip={expert.slip} phases={'->'.join(expert.phase_seq)}", flush=True)
    n_ok = sum(e["success"] for e in per_ep)
    if video and frames:
        try:
            import imageio.v2 as imageio
            imageio.mimwrite(str(OUT / "expert_success.mp4"), frames, fps=20)
        except Exception as exc:
            print(f"    [warn] 视频写入失败：{exc}", flush=True)
    n_raw = sum(e["success_raw_step"] > 0 for e in per_ep)
    _record("expert.success_rate", n_ok == episodes,
            f"严格成功 {n_ok}/{episodes}（宽口径 robosuite 真值 {n_raw}/{episodes}）——脚本专家 = 链路上界；"
            f"两者不一致就说明有「掉进去」的假阳性",
            per_episode=per_ep)
    env.close()


# ── 7. 重放：数据集里的动作能否在同初态复现成功（对齐验证的关键一环）───────────────
def probe_replay(npz_path: str, max_eps: int = 2) -> None:
    data = np.load(npz_path, allow_pickle=False)
    n_eps = int(data["episode_lengths"].shape[0]) if "episode_lengths" in data else 1
    env = _open_env(224)
    acts = data["action"]
    lengths = data["episode_lengths"] if "episode_lengths" in data else np.array([acts.shape[0]])
    # 档 1 起示范带随机初姿：重放必须回到**该局自己的 seed**，否则动作对着另一个物体位置执行，
    # 必然失败（2026-09-30 在 rand60 上踩到：0/2 假 FAIL）。没有 seeds 字段才退回固定 seed。
    seeds = data["seeds"] if "seeds" in data else None
    ok_count, checked = 0, 0
    off = 0
    for ep in range(min(n_eps, max_eps)):
        L = int(lengths[ep])
        ep_acts = acts[off:off + L]
        off += L
        use_seed = int(seeds[ep]) if seeds is not None else FIXED_SEED
        env.reset(seed=use_seed)
        succ = False
        for a in ep_acts:
            _o, _r, terminated, _tr, info = env.step(a)
            succ = succ or info["success"]
            if terminated:
                break
        checked += 1
        ok_count += int(succ)
        print(f"    replay ep{ep}: seed={use_seed} L={L} success={succ}", flush=True)
    _record("replay.actions_reproduce_success", checked > 0 and ok_count == checked,
            f"{ok_count}/{checked} 条示范的动作序列重放后仍然成功"
            f"（证明 数据集 action ↔ 环境执行器 对齐；源 {npz_path}）")
    env.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--determinism", action="store_true")
    ap.add_argument("--axes", action="store_true")
    ap.add_argument("--gripper", action="store_true")
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--expert", action="store_true")
    ap.add_argument("--replay", type=str, default="")
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    t0 = time.perf_counter()
    if args.all or args.determinism:
        probe_determinism()
    if args.all or args.axes:
        probe_axes()
    if args.all or args.gripper:
        probe_gripper()
    if args.all or args.images:
        probe_images(args.img_size)
    if args.all or args.timing:
        probe_timing(img_size=args.img_size)
    if args.all or args.expert:
        probe_expert(args.episodes, args.img_size)
    if args.replay:
        probe_replay(args.replay)

    n_fail = sum(1 for r in RESULTS if not r["pass"])
    summary = {"probe": "mg_probe", "n_probe": len(RESULTS), "n_fail": n_fail,
               "seconds": round(time.perf_counter() - t0, 1),
               "env_contract": SingleArmGraspEnv.__init__.__doc__ and None or None,
               "task": TASK, "results": RESULTS}
    summary.pop("env_contract")
    out = Path(args.out) if args.out else OUT / "probe_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n探针 {len(RESULTS) - n_fail}/{len(RESULTS)} 通过，用时 {summary['seconds']} s")
    print(f"[saved] {out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
