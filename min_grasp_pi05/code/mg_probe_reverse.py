#!/usr/bin/env python
"""最小抓取链路 · 档 2 反向任务探针（在训练任何策略之前，先把反向链路的四层自证干净）。

四项检查（对应「先让脚本专家跑通反向 = 链路上界自证」）：
  --teleport    can 被写进 bin2 象限后：位置与请求值一致、60 步零动作不漂不炸、幽灵 can 已隐藏；
  --negative    400 步零动作**不许**判成功（防止成功判据被初态直接满足 = 假阳性）；
  --determinism 同 seed 两次 reset 逐位一致（含图像哈希）；不同 seed 的 can xy 要有跨度；
  --expert      ScriptedExpert 原封不动跑反向，报严格成功率 + 相位序列 + 倾角 + 视频（上界）；
  --feasible    网格扫描 can 在象限内的可行出生域（反向抖动范围的**实测依据**，别拍脑袋定）；
  --replay      把数据集里的**反向**动作序列喂回 ReverseGraspEnv：既要复现严格成功，
                又要逐帧 state 逐比特相同（= 数据集 action/state ↔ 环境执行器 三者对齐）。
                正向这一环在档 1 已验过（`mg_probe.py --replay`），反向是本档新加的，必须单独验。

纪律：本探针只 import 本目录模块；不 import 仓内其它线的任何代码。
用法：bash -c 'source code/env.sh && $MG_PY code/mg_probe_reverse.py --all'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_env import CAM_BASE, CAN_HALF_HEIGHT, STATE_KEY  # noqa: E402
from mg_env_reverse import (  # noqa: E402
    GHOST_GEOM_PREFIX, INIT_JITTER_X_HI, INIT_JITTER_X_LO, INIT_JITTER_Y, REVERSE_TARGET_TOL_XY,
    TASK_REVERSE, UPRIGHT_TILT_DEG, ReverseGraspEnv,
)
from mg_expert import ScriptedExpert  # noqa: E402
from mg_expert_reverse import ReverseScriptedExpert  # noqa: E402

OUT = MG_ROOT / "runs" / "probe_reverse"
RESULTS: list[dict] = []


def _record(name: str, passed: bool, detail: str, **extra) -> None:
    RESULTS.append({"probe": name, "pass": bool(passed), "detail": detail, **extra})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)


def _img_hash(img: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(img).tobytes()).hexdigest()[:16]


def _ghost_alpha(env) -> list[float]:
    sim = env.env.sim
    out = []
    for g in range(sim.model.ngeom):
        if (sim.model.geom_id2name(g) or "").startswith(GHOST_GEOM_PREFIX):
            out.append(float(np.asarray(sim.model.geom_rgba[g])[3]))
    return out


# ── 1. 摆放：can 真被写进象限、且物理稳定 ───────────────────────────────────────
def probe_teleport(img_size: int = 224, settle_steps: int = 60) -> None:
    env = ReverseGraspEnv(img_size=img_size)
    snap = None
    for seed in (1000, 1001):
        env.reset(seed=seed)
        snap = env.init_state_snapshot()
        req = np.asarray(snap["can_init_xy_requested"], dtype=np.float64)
        got = env.object_pos[:2]
        err_xy = float(np.linalg.norm(got - req))
        z_err = abs(float(env.object_pos[2]) - (float(env.env.bin2_pos[2]) + CAN_HALF_HEIGHT))
        q = env.source_xy
        inside = bool(INIT_JITTER_X_LO - 1e-6 <= got[0] - q[0] <= INIT_JITTER_X_HI + 1e-6
                      and abs(got[1] - q[1]) <= INIT_JITTER_Y + 1e-6)
        drift = 0.0
        max_speed = 0.0
        for _ in range(settle_steps):
            _o, _r, term, trunc, info = env.step(np.zeros(7, dtype=np.float32))
            drift = max(drift, float(np.linalg.norm(np.asarray(info["object_pos"])[:2] - got)))
            max_speed = max(max_speed, float(info["object_speed"]))
            if term or trunc:
                break
        alphas = _ghost_alpha(env)
        _record(
            f"teleport.seed{seed}",
            err_xy < 2e-3 and z_err < 2e-3 and inside and drift < 5e-3 and max_speed < 0.05
            and alphas and max(alphas) == 0.0,
            f"写入误差 xy={err_xy * 1e3:.2f} mm z={z_err * 1e3:.2f} mm 在象限内={inside}；"
            f"{settle_steps} 步零动作漂移={drift * 1e3:.2f} mm 最大速度={max_speed:.4f} m/s；"
            f"VisualCan alpha={alphas}（0 = 幽灵已隐藏）",
            snapshot=snap, drift_mm=round(drift * 1e3, 3), max_speed=round(max_speed, 5))
    env.close()


# ── 2. 反向成功判据不许被初态满足 ───────────────────────────────────────────────
def probe_negative(img_size: int = 224) -> None:
    env = ReverseGraspEnv(img_size=img_size)
    env.reset(seed=1000)
    fired_at, ever_raw = -1, False
    for i in range(env.horizon):
        _o, _r, term, trunc, info = env.step(np.zeros(7, dtype=np.float32))
        ever_raw = ever_raw or bool(info["success_forward_pred"])
        if info["success"] and fired_at < 0:
            fired_at = i + 1
        if term or trunc:
            break
    _record("negative.no_action_no_success", fired_at < 0,
            f"400 步零动作：严格成功触发步={fired_at}（必须为 -1）；"
            f"正向判据读数={ever_raw}。注意正向谓词认的是「can 在 bin2 象限 ∧ 末端离 can >4.2 cm」，"
            f"而反向初态恰好满足前者 —— 所以反向绝不能复用正向判据，必须自带落点区域判据。",
            fired_at=fired_at, forward_pred_ever=ever_raw)
    env.close()


# ── 3. 确定性：同 seed 逐位一致；异 seed 有跨度 ─────────────────────────────────
def probe_determinism(img_size: int = 128, seeds: int = 6) -> None:
    env = ReverseGraspEnv(img_size=img_size)
    imgs, detail = [], []
    for seed in (1000, 1000):
        obs = env.reset(seed=seed)
        detail.append({"seed": seed, "can": np.round(env.object_pos, 6).tolist(),
                       "can_quat_xyzw": np.round(np.asarray(env._raw["Can_quat"], dtype=float), 6).tolist(),
                       "eef": np.round(env.eef_pos, 6).tolist(),
                       "state_hash": _img_hash(obs["observation.state"]),
                       "img_hash": _img_hash(env.render(CAM_BASE))})
        imgs.append(env.render(CAM_BASE).astype(np.int16))
    # 与 mg_probe.probe_determinism 同口径：**状态必须逐位一致**；图像只要求 MuJoCo EGL 的
    # LSB 抖动级别（≤2 灰阶、占比 <1e-3）。逐位比图像哈希会把渲染抖动误判成初态不确定。
    same_state = detail[0]["can"] == detail[1]["can"] and detail[0]["eef"] == detail[1]["eef"] \
        and detail[0]["state_hash"] == detail[1]["state_hash"] \
        and detail[0]["can_quat_xyzw"] == detail[1]["can_quat_xyzw"]
    d = np.abs(imgs[0] - imgs[1])
    img_max, img_frac = int(d.max()), float((d > 0).mean())
    same = bool(same_state and img_max <= 2 and img_frac < 1e-3)
    xs, ys = [], []
    for s in range(1000, 1000 + seeds):
        env.reset(seed=s)
        xs.append(float(env.object_pos[0]))
        ys.append(float(env.object_pos[1]))
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    want_x = INIT_JITTER_X_HI - INIT_JITTER_X_LO
    want_y = 2 * INIT_JITTER_Y
    _record("determinism.same_seed", same,
            f"同 seed=1000 两次 reset：状态逐位一致={same_state}（can/quat/eef/state 哈希全同）；"
            f"图像最大差={img_max} 灰阶、占比 {img_frac:.1e}（MuJoCo EGL LSB 抖动，与正向 env 同级，非状态差异）",
            runs=detail, img_max_diff=img_max, img_frac_diff=img_frac)
    _record("determinism.seed_spread", span_x > 0.4 * want_x and span_y > 0.4 * want_y,
            f"{seeds} 个 seed 的 can 初态跨度 x={span_x * 1e3:.1f} mm y={span_y * 1e3:.1f} mm"
            f"（抖动窗口 x={want_x * 1e3:.0f} mm、y={want_y * 1e3:.0f} mm，"
            f"跨度太小说明随机源没生效）", xs=[round(v, 4) for v in xs], ys=[round(v, 4) for v in ys])
    env.close()


# ── 4. 脚本专家跑反向：链路上界 + 示范源可用性 ──────────────────────────────────
def probe_expert(episodes: int = 5, seed_base: int = 1000, img_size: int = 224,
                 noise_sigma: float = 0.0, video: bool = True) -> None:
    env = ReverseGraspEnv(img_size=img_size)
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(12345)
    per_ep, frames = [], []
    for ep in range(episodes):
        seed = seed_base + ep
        env.reset(seed=seed)
        expert = ReverseScriptedExpert(env).reset()
        succ_step, steps, last_info, ep_frames = -1, 0, {}, []
        min_dist = float("inf")
        while steps < env.horizon:
            act = np.asarray(expert(), dtype=np.float32)
            if noise_sigma > 0.0:
                act[:3] = np.clip(act[:3] + rng.normal(0.0, noise_sigma, size=3), -1.0, 1.0)
            _o, _r, term, trunc, info = env.step(act)
            steps += 1
            last_info = info
            min_dist = min(min_dist, float(info["dist_to_target_xy"]))
            if info["success"] and succ_step < 0:
                succ_step = steps
            if video and ep == 0:
                ep_frames.append(env.render(CAM_BASE))
            if term or trunc:
                break
        can = np.asarray(last_info.get("object_pos", [np.nan] * 3), dtype=np.float64)
        per_ep.append({"ep": ep, "seed": seed, "success": succ_step > 0, "success_step": succ_step,
                       "final_tilt_deg": round(float(last_info.get("can_tilt_deg", float("nan"))), 2),
                       "steps": steps, "phases": expert.phase_seq, "regrasp": expert.regrasp,
                       "slip": expert.slip, "final_can": np.round(can, 4).tolist(),
                       "final_can_z": round(float(can[2]), 4),
                       "reverse_resting_z": round(float(last_info.get("reverse_resting_z", np.nan)), 4),
                       "min_dist_to_target": round(min_dist, 4),
                       "hold": int(last_info.get("hold", -1))})
        if ep == 0:
            frames = ep_frames
        print(f"    ep{ep} seed={seed} success={succ_step > 0} step={succ_step} steps={steps} "
              f"can={np.round(can, 3).tolist()} (静置预期 z={last_info.get('reverse_resting_z', float('nan')):.4f}) "
              f"倾角={last_info.get('can_tilt_deg', float('nan')):.1f}°(门限 {UPRIGHT_TILT_DEG}°) "
              f"slip={expert.slip} regrasp={expert.regrasp} phases={'->'.join(expert.phase_seq)}", flush=True)
    n_ok = sum(e["success"] for e in per_ep)
    if video and frames:
        try:
            import imageio.v2 as imageio
            imageio.mimwrite(str(OUT / "expert_reverse.mp4"), frames, fps=env.fps)
            print(f"    [video] {OUT / 'expert_reverse.mp4'}", flush=True)
        except Exception as exc:
            print(f"    [warn] 视频写入失败：{exc}", flush=True)
    _record("expert.reverse_success_rate", n_ok == episodes and episodes > 0,
            f"反向严格成功 {n_ok}/{episodes} —— 脚本专家 = 反向链路上界；"
            f"不满贯就先修专家/几何，不要急着采数据",
            per_episode=per_ep, noise_sigma=noise_sigma)
    env.close()


# ── 5. 可行出生域网格扫描：反向抖动范围的实测依据 ───────────────────────────────
def probe_feasible(seeds: tuple[int, ...] = (1000, 1001), img_size: int = 64) -> None:
    """在象限内按网格摆 can，每格跑 len(seeds) 局脚本专家；严格成功（含立着落定）才算该格可行。

    为什么必须实测：象限净空看着有 18×23 cm，但 Panda 在 x/y 偏大那一角已经到可达极限，
    末端压不到 can 正上方、反而蹭 bin2 底板空转到超时（2026-09-30 实测）。
    """
    env = ReverseGraspEnv(img_size=img_size)
    dxs = (-0.08, -0.06, -0.04, -0.02, 0.0, 0.02, 0.04)
    dys = (-0.08, -0.04, 0.0, 0.04, 0.08)
    grid, feasible = [], []
    for dx in dxs:
        for dy in dys:
            oks, worst = [], []
            for sd in seeds:
                env.reset(seed=sd, init_xy_offset=[dx, dy], init_yaw=0.0)
                ex = ReverseScriptedExpert(env).reset()
                ok, steps, tilt_fin = False, 0, float("nan")
                for i in range(env.horizon):
                    _o, _r, term, trunc, info = env.step(ex())
                    steps = i + 1
                    tilt_fin = float(info.get("can_tilt_deg", float("nan")))
                    if info["success"]:
                        ok = True
                    if term or trunc:
                        break
                oks.append(ok)
                worst.append({"seed": sd, "success": ok, "steps": steps,
                              "can_z": round(float(env.object_pos[2]), 4),
                              "tilt_deg": round(tilt_fin, 1)})
            cell = {"dx": dx, "dy": dy, "n_ok": int(sum(oks)), "n": len(seeds), "runs": worst}
            grid.append(cell)
            if all(oks):
                feasible.append((dx, dy))
        print("    dx={:+.2f} -> ".format(dx) + " ".join(
            f"dy={d:+.2f}:{next(c['n_ok'] for c in grid if c['dx'] == dx and c['dy'] == d)}/{len(seeds)}"
            for d in dys), flush=True)
    fdx = [f[0] for f in feasible]
    fdy = [f[1] for f in feasible]
    inside = bool(fdx and fdy and INIT_JITTER_X_LO >= min(fdx) and INIT_JITTER_X_HI <= max(fdx)
                  and INIT_JITTER_Y <= max(fdy) and -INIT_JITTER_Y >= min(fdy))
    _record("feasible.jitter_box_inside_measured_region", inside,
            f"可行格点 {len(feasible)}/{len(grid)}；实测可行域 dx∈[{min(fdx) if fdx else float('nan'):+.2f},"
            f"{max(fdx) if fdx else float('nan'):+.2f}] dy∈[{min(fdy) if fdy else float('nan'):+.2f},"
            f"{max(fdy) if fdy else float('nan'):+.2f}]；"
            f"当前抖动框 x∈[{INIT_JITTER_X_LO:+.2f},{INIT_JITTER_X_HI:+.2f}] y∈[{-INIT_JITTER_Y:+.2f},"
            f"{INIT_JITTER_Y:+.2f}] 是否被它包住={inside}",
            grid=grid, feasible_dx=[min(fdx), max(fdx)] if fdx else None,
            feasible_dy=[min(fdy), max(fdy)] if fdy else None)
    env.close()


# ── 6. 重放对齐：数据集里的反向动作能否复现成功 + 复现逐帧 state ─────────────────
def probe_replay(npz_path: str, max_eps: int = 3, img_size: int = 224) -> None:
    """双重判据（只验「成功」是不够的，反向的成功判据本身比正向复杂）：

    1) **成功复现**：把 npz 里的动作按原顺序喂回 ReverseGraspEnv（回到该局自己的 seed），
       严格成功判据（立着 ∧ 落定 ∧ 保持 10 步）必须仍然为 True；
    2) **状态逐比特**：`mg_collect` 存的是「执行 action[t] **之前**的 obs」，所以重放时
       第 t 步的 obs 必须与 state[t] 逐比特相同。物理是确定性的，state 里又不含图像，
       只要对齐没错就该 100% 相同 —— 有任何一帧不同，说明 state 打包 / 执行器 / 初态
       三者之一有偏差，这比「成功与否」灵敏得多。
    """
    data = np.load(npz_path, allow_pickle=False)
    if "seeds" not in data:
        _record("replay.reverse", False, f"{npz_path} 没有 seeds 字段，无法回到该局初态（档 1 陷阱 16）")
        return
    acts, states = data["action"], data["state"]
    lengths = np.asarray(data["episode_lengths"], dtype=int)
    seeds = np.asarray(data["seeds"]).reshape(-1)
    env = ReverseGraspEnv(img_size=img_size)
    n_ok = n_bitexact = checked = 0
    worst = 0.0
    per_ep = []
    off = 0
    for ep in range(min(int(len(lengths)), max_eps)):
        L = int(lengths[ep])
        seed = int(seeds[ep])
        obs = env.reset(seed=seed)
        succ, n_exact, ep_worst, t_run = False, 0, 0.0, 0
        for t in range(L):
            rec = np.asarray(states[off + t], dtype=np.float32)
            cur = np.asarray(obs[STATE_KEY], dtype=np.float32)
            if np.array_equal(cur, rec):
                n_exact += 1
            else:
                ep_worst = max(ep_worst, float(np.abs(cur - rec).max()))
            obs, _r, terminated, truncated, info = env.step(acts[off + t])
            t_run += 1
            succ = succ or bool(info["success"])
            if terminated or truncated:
                break
        off += L
        checked += 1
        n_ok += int(succ)
        n_bitexact += int(n_exact == L)
        worst = max(worst, ep_worst)
        tilt = float(info.get("can_tilt_deg", float("nan")))
        per_ep.append({"ep": ep, "seed": seed, "L": L, "steps_run": t_run, "success": bool(succ),
                       "state_frames_bit_exact": n_exact, "max_abs_state_diff": round(ep_worst, 8),
                       "final_tilt_deg": round(tilt, 2)})
        print(f"    replay ep{ep}: seed={seed} L={L} success={succ} "
              f"state 逐比特帧={n_exact}/{L} 最大绝对差={ep_worst:.3g} 末态倾角={tilt:.2f}°", flush=True)
    _record("replay.reverse_success", checked > 0 and n_ok == checked,
            f"{n_ok}/{checked} 条**反向**示范的动作序列重放后仍然严格成功（源 {npz_path}）",
            per_episode=per_ep)
    _record("replay.reverse_state_bitexact", checked > 0 and n_bitexact == checked,
            f"{n_bitexact}/{checked} 局逐帧 state 与数据集**逐比特相同**（最差绝对差 {worst:.3g}）"
            f"——数据集 action/state ↔ ReverseGraspEnv 执行器三方对齐",
            worst_abs_state_diff=worst)
    env.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--teleport", action="store_true")
    ap.add_argument("--negative", action="store_true")
    ap.add_argument("--determinism", action="store_true")
    ap.add_argument("--expert", action="store_true")
    ap.add_argument("--feasible", action="store_true")
    ap.add_argument("--replay", type=str, default="", help="反向示范 npz（data/<name>_rev_raw.npz）")
    ap.add_argument("--replay-eps", type=int, default=3)
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed-base", type=int, default=1000)
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    t0 = time.perf_counter()
    if args.all or args.teleport:
        probe_teleport(args.img_size)
    if args.all or args.negative:
        probe_negative(args.img_size)
    if args.all or args.determinism:
        probe_determinism(args.img_size if not args.all else 128)
    if args.all or args.expert:
        probe_expert(args.episodes, args.seed_base, args.img_size, args.noise)
    if args.replay:            # 需要指定 npz，不进 --all
        probe_replay(args.replay, args.replay_eps, args.img_size)
    if args.feasible:          # 网格很贵，不进 --all；单独跑
        probe_feasible()

    n_fail = sum(1 for r in RESULTS if not r["pass"])
    mg_env_sha = hashlib.sha256((HERE / "mg_env.py").read_bytes()).hexdigest()[:16]
    summary = {"probe": "mg_probe_reverse", "task_reverse": TASK_REVERSE,
               "n_probe": len(RESULTS), "n_fail": n_fail,
               "seconds": round(time.perf_counter() - t0, 1),
               "mg_env_py_sha256_16": mg_env_sha,
               "note_isolation": "mg_env.py 未被修改（档 1 评测进程仍在 import 它）；反向逻辑全在 mg_env_reverse.py",
               "reverse_target_tol_xy": REVERSE_TARGET_TOL_XY,
               "results": RESULTS}
    out = Path(args.out) if args.out else OUT / "probe_reverse_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n反向探针 {len(RESULTS) - n_fail}/{len(RESULTS)} 通过，用时 {summary['seconds']} s")
    print(f"[saved] {out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
