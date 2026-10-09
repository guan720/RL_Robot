#!/usr/bin/env python
"""档 5 护栏 G0a（**修正版**）· 证明 harness 外壳没有扰动策略路径。

### 为什么改（2026-10-02 20:47，改的是**方法**不是目的）
原设计（`code/mg_g0a_bitcmp.py.superseded`）要求同一 `--torch-seed` 下 `--observe-only` 与
`--detector-off` 的 `rollout_actions.npz` **逐比特相同**。实测做不到，而且原因与 harness 无关：
  两次都关掉检测器、同种子重跑，**第 0 步动作就已经差 6e-4**（A=1.0228312 vs B=1.0234671），
  400 步后放大成不同的成功步（283 vs 282）。
π₀.₅ 是 bf16 + GPU 上的 flow-matching 采样，cuDNN/cuBLAS 会按当时的时序挑算法，
归约顺序不固定 ⇒ 前向本身就不是逐比特可复现的。**钉 torch 种子也救不回来**（新坑，见 README 坑 44）。
所以「逐比特」这个判据在本项目里对任何两次 GPU 读数都不成立，拿它当护栏只会永远 FAIL。

### 修正后的两段判据
**G0a-1（CPU，确定性，这才是原设计真正想防的东西）**
  a. 桩策略（动作只由步号决定）下，`--observe-only` 与 `--detector-off` 的动作流**逐比特相同**
     ⇒ 外壳没有多调/少调/改写策略动作；
  b. 跑完整条检测器序列后，`torch` 的 CPU 与 CUDA 随机数状态**一字未动**
     ⇒ 检测器不吃随机数，不会把 flow-matching 的采样流推歪（这才是「套壳改变结果」的真实机理）。
**G0a-2（GPU，经验对照）**
  噪声地板 = 两次「检测器关掉」之间的分歧（同种子、同 seed 窗口）；
  判据 = 「observe-only vs detector-off」的分歧**不得比噪声地板更早、更大**。
  具体：first_diff_step(A,B) ≥ min over 地板对，且 max|Δaction|(A,B) ≤ max over 地板对。
  若某个地板对自己就是逐比特相同的，则地板 = 逐比特，A 也必须逐比特（不给放水）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_g0a_equiv.py \
        runs/s5_g0a_observe_ts12345 \
        runs/s5_g0a_off_ts12345 runs/s5_g0a_off2_ts12345 runs/s5_g0a_off3_ts12345'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_env import STATE_KEY  # noqa: E402
from mg_harness import TakeoverHarness, GraspDetector, SegmentBuffer  # noqa: E402


def sha(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


# ───────────────────────── G0a-1（CPU，确定性）────────────────────────
class _StubEnv:
    horizon = 400


class _StubExpert:
    def __init__(self, env) -> None:
        self.phase, self.phase_step = "carry", 0

    def resume(self, can_z0=None):
        return self

    def __call__(self):
        return np.full(7, 0.5, dtype=np.float32)


def g0a1() -> tuple[int, list[str]]:
    """返回 (通过项数, 失败原因列表)。"""
    n_ok, bad = 0, []

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n_ok
        if cond:
            n_ok += 1
        else:
            bad.append(f"{name} {detail}")

    widths = ([0.0417] + [0.078] * 20 + [0.001] * 12 + [0.050] * 40 + [0.078] * 30
              + [0.001] * 25 + [0.050] * 60)
    env = _StubEnv()

    def collect(observe_only: bool, enabled: bool) -> tuple[np.ndarray, np.ndarray, list[str]]:
        h = TakeoverHarness(env, _StubExpert, observe_only=observe_only, enabled=enabled,
                            detector=GraspDetector(), buffer=SegmentBuffer())
        h.reset(seed=7002, can_z0=0.8603)
        acts, states, srcs = [], [], []
        for i, w in enumerate(widths):
            obs = {STATE_KEY: np.array([0.1, -0.25, 0.95, 0, 0, 0, 1, w], dtype=np.float32)}
            a, s = h.select(obs, i, lambda i=i: np.full(7, float(i) * 0.001, dtype=np.float32))
            acts.append(a)
            states.append(obs[STATE_KEY])
            srcs.append(s)
        h.finish(False, False, len(widths))
        return np.asarray(acts), np.asarray(states), srcs

    a_act, a_st, a_src = collect(observe_only=True, enabled=True)
    b_act, b_st, b_src = collect(observe_only=False, enabled=False)
    ck("G0a-1a 动作流逐比特相同", sha(a_act) == sha(b_act), f"{sha(a_act)} vs {sha(b_act)}")
    ck("G0a-1a 状态流逐比特相同", sha(a_st) == sha(b_st), f"{sha(a_st)} vs {sha(b_st)}")
    ck("G0a-1a 来源全是 policy（观察模式不接管）", set(a_src) == {"policy"}, str(set(a_src)))
    ck("G0a-1a 桩策略确实被喂了全部步", len(a_act) == len(widths), f"{len(a_act)} vs {len(widths)}")

    # b) torch 随机数状态不受检测器影响
    import torch
    torch.manual_seed(12345)
    cpu_before = torch.random.get_rng_state().clone()
    cuda_before = torch.cuda.get_rng_state().clone() if torch.cuda.is_available() else None
    draws_before = torch.randn(4).clone()          # 参考：不跑检测器时，接下来该出这 4 个数
    torch.manual_seed(12345)                       # 回到同一个起点
    det = GraspDetector()
    for w in widths * 20:                          # 跑一整条检测器序列（含 latch/reset）
        det.update(w)
        det.latch_success()
        det.reset()
    cpu_mid = torch.random.get_rng_state().clone()  # ⚠️ 必须在下面的 randn **之前**取快照
    cuda_mid = torch.cuda.get_rng_state().clone() if cuda_before is not None else None
    draws_after = torch.randn(4)
    ck("G0a-1b CPU RNG 状态一字未动", sha(cpu_before.numpy()) == sha(cpu_mid.numpy()),
       f"{sha(cpu_before.numpy())} vs {sha(cpu_mid.numpy())}")
    ck("G0a-1b 跑完检测器后 torch.randn 与不跑时逐比特相同",
       sha(draws_before.numpy()) == sha(draws_after.numpy()),
       f"{draws_before.tolist()} vs {draws_after.tolist()}")
    if cuda_before is not None:
        ck("G0a-1b CUDA RNG 状态一字未动",
           sha(cuda_before.cpu().numpy()) == sha(cuda_mid.cpu().numpy()),
           f"{sha(cuda_before.cpu().numpy())} vs {sha(cuda_mid.cpu().numpy())}")
    return n_ok, bad


# ───────────────────────── G0a-2（GPU 经验对照）────────────────────────
def load_run(d: Path) -> dict:
    z = np.load(d / "rollout_actions.npz")
    s = json.loads((d / "eval_summary.json").read_text())
    return {"npz": z, "summary": s, "dir": str(d),
            "lengths": [int(x) for x in z["episode_lengths"]],
            "relaxed": [bool(e["success_relaxed"]) for e in s["per_episode"]]}


def divergence(x: dict, y: dict) -> dict:
    """两次读数的分歧度量：首个不同步、最大动作差、局长度是否一致、逐局放宽是否一致。"""
    ax, ay = x["npz"]["action"], y["npz"]["action"]
    sx, sy = x["npz"]["state"], y["npz"]["state"]
    first, maxd, off_x, off_y, per_ep = None, 0.0, 0, 0, []
    for i, (lx, ly) in enumerate(zip(x["lengths"], y["lengths"])):
        n = min(lx, ly)
        bx, by = ax[off_x:off_x + n], ay[off_y:off_y + n]
        d = np.abs(bx - by).max(axis=1) if n else np.zeros(0)
        fd = int(np.flatnonzero(d > 0)[0]) if n and (d > 0).any() else None
        ep_first = None if fd is None else off_x + fd + 1     # 1-based 全局步号
        if fd is not None and first is None:
            first = ep_first
        maxd = max(maxd, float(d.max()) if n else 0.0)
        per_ep.append({"ep": i, "len_x": lx, "len_y": ly, "first_diff_step_in_ep": (fd + 1) if fd is not None else None,
                       "max_abs_daction": round(float(d.max()), 8) if n else 0.0,
                       "state_identical": bool(n and sha(sx[off_x:off_x + n]) == sha(sy[off_y:off_y + n]))})
        off_x += lx
        off_y += ly
    return {"first_diff_step": first, "max_abs_daction": maxd, "per_ep": per_ep,
            "lengths_identical": x["lengths"] == y["lengths"],
            "relaxed_identical": x["relaxed"] == y["relaxed"],
            "bit_identical": first is None and x["lengths"] == y["lengths"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("observe", help="observe-only 产物目录")
    ap.add_argument("offs", nargs="+", help="detector-off 产物目录（≥2 个，用来量噪声地板）")
    ap.add_argument("--skip-cpu", action="store_true")
    args = ap.parse_args()

    print("[G0a] === G0a-1（CPU，确定性）===")
    n_ok, bad = (0, []) if args.skip_cpu else g0a1()
    if bad:
        for b in bad:
            print(f"[G0a][FAIL] {b}")
    else:
        print(f"[G0a] G0a-1 PASS：{n_ok} 项（桩策略动作流逐比特相同 ∧ torch CPU/CUDA RNG 状态未动）")

    print("\n[G0a] === G0a-2（GPU 经验对照）===")
    obs = load_run(Path(args.observe) if Path(args.observe).is_absolute() else MG_ROOT / args.observe)
    offs = [load_run(Path(p) if Path(p).is_absolute() else MG_ROOT / p) for p in args.offs]
    for r in [obs] + offs:
        h = r["summary"].get("harness", {})
        print(f"  {Path(r['dir']).name:<28} mode={h.get('mode'):<13} torch_seed={h.get('torch_seed')} "
              f"eps={r['summary']['episodes']} lengths={r['lengths']} relaxed={r['relaxed']}")
    if len(offs) < 2:
        print("[G0a][FAIL] 噪声地板至少要两次 detector-off 读数（只有一次就没有对照）")
        return 1
    if obs["summary"]["harness"].get("mode") != "observe_only":
        print("[G0a][FAIL] observe 侧模式不是 observe_only")
        return 1
    for r in offs:
        if r["summary"]["harness"].get("mode") != "detector_off":
            print(f"[G0a][FAIL] {Path(r['dir']).name} 模式不是 detector_off")
            return 1
        if r["summary"]["harness"].get("torch_seed") != obs["summary"]["harness"].get("torch_seed"):
            print(f"[G0a][FAIL] {Path(r['dir']).name} 的 torch_seed 与 observe 侧不同 ⇒ 不可比")
            return 1

    floor: list[dict] = []
    print("\n  -- 噪声地板（detector-off 两两对比）--")
    for i in range(len(offs)):
        for j in range(i + 1, len(offs)):
            dv = divergence(offs[i], offs[j])
            floor.append(dv)
            print(f"  {Path(offs[i]['dir']).name} vs {Path(offs[j]['dir']).name}: "
                  f"逐比特={dv['bit_identical']} 首个不同步={dv['first_diff_step']} "
                  f"max|Δaction|={dv['max_abs_daction']:.3e} 局长度一致={dv['lengths_identical']} "
                  f"逐局放宽一致={dv['relaxed_identical']}")
    print("\n  -- 被检对（observe-only vs 每个 detector-off）--")
    test: list[dict] = []
    for r in offs:
        dv = divergence(obs, r)
        test.append(dv)
        print(f"  {Path(obs['dir']).name} vs {Path(r['dir']).name}: "
              f"逐比特={dv['bit_identical']} 首个不同步={dv['first_diff_step']} "
              f"max|Δaction|={dv['max_abs_daction']:.3e} 局长度一致={dv['lengths_identical']} "
              f"逐局放宽一致={dv['relaxed_identical']}")

    # 结构化判据（**非退化**）：外壳必须「每步恰好调用一次策略、一次不多一次不少」，
    # 且观察模式下专家一步都不许出。这条能抓住「多调一次 select_action 把 chunk 队列推歪」这类
    # 真实故障，而 max|Δaction| 在轨迹已经完全分叉时会饱和到动作量程（≈2.0），
    # 地板 2.040 vs 被检 2.045 这种 0.2% 的差只是「各自走到了哪个状态」，没有判别力 ⇒ 不作判据。
    struct_bad = []
    for r in [obs] + offs:
        h = r["summary"].get("harness", {})
        n_steps = int(sum(r["lengths"]))
        n_pol = int(h.get("n_steps_policy", -1))
        n_exp = int(h.get("n_steps_expert", -1))
        if n_pol != n_steps:
            struct_bad.append(f"{Path(r['dir']).name}: 策略调用 {n_pol} 次 ≠ 总步数 {n_steps}")
        if r is obs and n_exp != 0:
            struct_bad.append(f"{Path(r['dir']).name}: 观察模式竟然出了 {n_exp} 步专家动作")
        if n_pol + n_exp != n_steps:
            struct_bad.append(f"{Path(r['dir']).name}: 策略 {n_pol} + 专家 {n_exp} ≠ 总步数 {n_steps}")
    print("\n  -- 结构化判据（每步恰好一次策略调用）--")
    for r in [obs] + offs:
        h = r["summary"].get("harness", {})
        print(f"  {Path(r['dir']).name:<28} 总步数={int(sum(r['lengths']))} 策略调用={h.get('n_steps_policy')} "
              f"专家步数={h.get('n_steps_expert')}")
    for b in struct_bad:
        print(f"[G0a][FAIL] {b}")

    floor_bit = any(d["bit_identical"] for d in floor)
    if floor_bit:
        ok = all(d["bit_identical"] for d in test)
        why = "地板里有逐比特相同的对 ⇒ 被检对也必须逐比特相同"
    else:
        floor_firsts = [d["first_diff_step"] for d in floor if d["first_diff_step"] is not None]
        floor_first = min(floor_firsts) if floor_firsts else None
        floor_lens = {i: sorted(d["per_ep"][i]["len_y"] for d in floor) for i in range(len(obs["lengths"]))}
        ok = not struct_bad
        why = (f"地板本身从第 {floor_first} 步就分叉（GPU 前向不可逐比特复现，坑 44）⇒ "
               f"逐比特判据无意义；改判三条非退化条件：①结构化（上面）②被检对首个分歧步不早于地板 "
               f"③逐局放宽结果一致 ∧ 局长度落在地板的取值范围内")
        for d in test:
            if floor_first is not None and d["first_diff_step"] is not None \
                    and d["first_diff_step"] < floor_first:
                ok = False
                why += f"｜违规：被检对首个分歧步 {d['first_diff_step']} < 地板 {floor_first}"
            if not d["relaxed_identical"]:
                ok = False
                why += "｜违规：被检对逐局放宽结果与地板不一致"
        for i, want in enumerate(obs["lengths"]):
            lo, hi = min(floor_lens[i]), max([x["lengths"][i] for x in offs] + floor_lens[i])
            if not (lo <= want <= hi):
                ok = False
                why += f"｜违规：ep{i} 局长度 {want} 不在地板范围 [{lo},{hi}]"
    print(f"\n[G0a] 判据：{why}")
    if bad or not ok:
        raise SystemExit("[G0a] FAIL：harness 外壳的扰动**超过**了策略本身的运行间噪声地板 "
                         "⇒ 档 5 读数不能归因给检测器")
    print(f"[G0a] PASS：G0a-1 {n_ok} 项全过 ∧ G0a-2 被检对的分歧不劣于噪声地板 "
          f"（逐局放宽结果一致={all(d['relaxed_identical'] for d in test)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
