#!/usr/bin/env python
"""档 9 预备 · CPU-only「重放接管台」（零 GPU 推理、零改动既有文件）

一句话：把**已经录在盘上的** (state, action) 逐帧重放进真 env，用 `mg_harness` 的**原样**检测器/接管
语义把脚本专家接上去，于是在**不做一次策略推理**的前提下，量到格 8A 那晚才会产生的三样东西：
  ① `can_at_takeover` 的**无偏**真值（重放时 env 里的 can 位姿，不是按初态重建 —— 修坑 71）；
  ② A2（接管后放宽成功率）与 A1（过三条过滤的可用帧数）的**实测**读数；
  ③ 「未到 grasp」的分层与 `descend_diag` 盲区占比。

为什么重放是合法的（本工具的地基，必须自证、不能假设）：
  `env.reset(seed)` 钉住全部随机源（`mg_env._seed_randomness`），物理与渲染尺寸无关 ⇒
  把录下来的 action 原样喂回去，轨迹**逐比特**复现。实测（2026-10-04，档 7F F4 占卡时）：
    runs/s3r_seed2000_rev_test_rand20_k10 的 ep0/1/2 ⇒ `max|Δeef| = 0.000e+00`、`max|Δwidth| = 0.000e+00`
    且语料是 img_size=224 录的、重放用 img_size=8 ⇒ 顺带证明**渲染尺寸不扰动物理**。
  本工具把这条自证变成每局的读数（`fid_max_dxyz`），并设 `FID_TOL`：超差的局**剔出**并计数，
  绝不静默混进分母（坑 71 的教训：只核对初值 = 只证明起点找对了）。

⚠️ 三条诚实标注（写进每一份产物，不许摘）
  1. **删失**：语料是 horizon=400 的评测产物，采集口径是 `COLLECT_HORIZON=800`。
     ⇒ 只能看到「前 400 步内触发」的接管；400..800 步才触发的局**看不见**（`censored_no_trigger`）。
     接管率与 A2 的分母因此是**删失子集**，不是 8A 的分母。每个读数都要和这个标注一起看。
  2. **seed 窗口纪律**：本工具默认只吃 **val 窗口 8000..8019** 的语料。
     D1 的 TEST 窗口是 **7000..7019**（`code/chain_s8c.sh:32` 的 `REV_SEED0`）⇒
     **用它调专家 = 拿 TEST 调参**（坑 33 家族）。`--runs` 指到 TEST 窗口时本工具**拒绝**跑，
     除非显式给 `--allow-test-window`（给了就在产物里打 `TEST_WINDOW_CONTAMINATION` 标）。
  3. **出身**：语料的策略 ckpt 必须与 8A 的接管源同一条（`s3r_seed2000` 的 022000）才是同分布；
     池化多个检查点只用于**定方向**，不用于报效应量（坑 57）。产物逐格记 ckpt 尾串。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_s9_rescue.py --selftest'          # 零 GPU / 不碰 runs
    # 单格（一个 rollout_actions.npz）
    $MG_PY code/mg_s9_rescue.py --mode fidelity --runs runs/<cell> --out runs/_diag/s9_rescue
    $MG_PY code/mg_s9_rescue.py --mode rescue   --runs runs/<cell> --out runs/_diag/s9_rescue
    # 汇总（把若干格的 json 池化成一份 md）
    $MG_PY code/mg_s9_rescue.py --mode report --indir runs/_diag/s9_rescue --out-md runs/_diag/s9_rescue/REPORT.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# 常数一律 import，不重打字面量（坑 67）
from mg_collect_corr import (  # noqa: E402
    COLLECT_HORIZON, EVAL_WINDOWS, GATE_A1_EPISODES, GATE_A1_FRAMES, GATE_A2_RATE, GATE_A3_MEDIAN,
    MAX_RE_DESCEND, MAX_SEG_LEN, accept_segment, descend_diag, wilson,
)
from mg_env import ACTION_DIM, HORIZON, STATE_DIM, STATE_KEY  # noqa: E402
from mg_expert import GRASP_OFFSET_Z, XY_TOL, Z_TOL  # noqa: E402
from mg_env_reverse import REVERSE_TARGET_TOL_XY  # noqa: E402
from mg_harness import WIDTH_IDX, GraspDetector, SegmentBuffer, TakeoverHarness  # noqa: E402

FID_TOL = 1e-6          # 重放保真容差（m）。实测逐比特相等 ⇒ 这个容差只是给浮点打印留余地
TEST_WINDOW = (7000, 7019)     # D1 的 TEST 窗口（chain_s8c.sh 的 REV_SEED0）⇒ 不许用来调专家
CAN_MOVED_XY = 0.010    # 「can 在接管前被策略推动过」的判据：水平位移 > 10 mm（> XY_TOL，留 2 mm 余量）
CAN_TILTED_DEG = 10.0   # 「can 在接管前被策略撞倒」的判据：倾角 > 10°（干净初态实测 0.06~0.08°）


# ─────────────────────── 纯函数（全部有自测；期望值按定义独立算，坑 65）───────────────────────
def in_window(seed: int, win: tuple[int, int]) -> bool:
    return int(win[0]) <= int(seed) <= int(win[1])


def touches_eval_window(seed_lo: int, seed_hi: int) -> list[tuple[int, int]]:
    """本工具的 seed 窗口与哪些**评测**窗口相交（用来判「是不是在用 TEST 调参」）。"""
    return [w for w in EVAL_WINDOWS if not (seed_hi < w[0] or seed_lo > w[1])]


def can_displacement(can_now, can0) -> dict:
    """接管瞬间 can 相对**本局初态**的位移（重放台里 can_now 是真值，不是重建）。"""
    a = np.asarray(can_now, dtype=np.float64).reshape(3)
    b = np.asarray(can0, dtype=np.float64).reshape(3)
    d = a - b
    return {"dxy": float(np.hypot(d[0], d[1])), "dz": float(d[2]),
            "dnorm": float(np.linalg.norm(d)),
            "moved_xy": bool(np.hypot(d[0], d[1]) > CAN_MOVED_XY)}


def classify_takeover_state(*, dxy: float, tilt_deg: float) -> str:
    """接管瞬间的状态类别（互斥、按严重度排序）。

    TILT   = can 已倒/斜（≥10°）⇒ 专家的抓取几何（can 中心 + GRASP_OFFSET_Z）不再成立
    MOVED  = can 立着但被推动过（水平 >10 mm）⇒ 专家要追一个新位置
    CLEAN  = can 基本没动 ⇒ 与「干净初态」同类，专家本该能救
    """
    if tilt_deg > CAN_TILTED_DEG:
        return "TILT"
    if dxy > CAN_MOVED_XY:
        return "MOVED"
    return "CLEAN"


def rate_summary(k: int, n: int) -> dict:
    lo, hi = wilson(k, n) if n else (float("nan"), float("nan"))
    return {"k": int(k), "n": int(n), "rate": (float(k) / float(n)) if n else float("nan"),
            "wilson_lo": lo, "wilson_hi": hi,
            "low_power": bool(n < 5)}


def fidelity_verdict(fid_max: float, tol: float = FID_TOL) -> bool:
    """逐比特复现 ⇒ True。超差 ⇒ 该局剔出（不静默混进分母）。"""
    return bool(np.isfinite(fid_max) and fid_max <= tol)


def descend_pooled_from_recs(recs: list[dict]) -> dict:
    """把逐局的 `diag_descend` 计数池化。只读 per_episode ⇒ 可从盘上 json 无损重算。"""
    tk = [r for r in recs if r.get("takeover") and r.get("fid_ok")]
    ds = [(r.get("diag_descend") or {}) for r in tk]
    n_desc = int(sum(int(d.get("n_descend_steps", 0)) for d in ds))
    n_blind = int(sum(int(d.get("n_blind", 0)) for d in ds))
    n_zok = int(sum(int(d.get("n_descend_z_ok", 0)) for d in ds))
    n_below = int(sum(int(d.get("n_descend_z_below", 0)) for d in ds))
    n_exp = int(sum(int(d.get("n_expert_steps", 0)) for d in ds))
    return {"n_takeover_episodes": len(tk), "n_expert_steps": n_exp,
            "n_descend_steps": n_desc, "n_blind": n_blind,
            "n_descend_z_ok": n_zok, "n_descend_z_below": n_below,
            "frac_blind_of_descend": (n_blind / n_desc) if n_desc else float("nan"),
            "frac_blind_of_z_ok": (n_blind / n_zok) if n_zok else float("nan")}


def seg_len_median_tk_succ(recs: list[dict]) -> float:
    """A3 的**判据口径**（与 `mg_collect_corr.summarize` 同义）：只取「放宽成功的接管片段」总体。
    失败的接管在 horizon=800 下必然跑满 ⇒ 算进去会让门随 horizon 变长而必挂（口径走样，
    留档 runs/S8_PREREG.md §9 增补 1）。
    """
    xs = [int(r["seg_len_raw"]) for r in recs if r.get("takeover") and r.get("success_relaxed")]
    return median_or_nan(xs)


def frames_by_state_class(recs: list[dict]) -> dict:
    """**收下的**纠正帧按接管瞬间的状态类拆分（预测 8B 那份数据到底教的是什么）。

    只算 `accept_segment=True` 的局；帧数用 `seg_len_raw`（本台 `trim=True` 且在放宽成功那一步就收工
    ⇒ 截断不删帧，raw == 采集器截断后的 `seg_len`；这条等价关系在自测里钉住）。
    """
    out: dict[str, int] = {}
    for r in recs:
        if r.get("accept_segment") and r.get("fid_ok"):
            k = r.get("state_class") or "NA"
            out[k] = out.get(k, 0) + int(r.get("seg_len_raw", 0))
    return dict(sorted(out.items()))


def pool_descend(rows_per_ep: list[list[tuple[float, float, str]]]) -> dict:
    """把逐局的 `descend_diag` 池化。直接复用采集器的同一个函数（口径逐字相同）。"""
    flat = [r for rows in rows_per_ep for r in rows]
    d = descend_diag(flat)
    d["n_episodes_with_expert_steps"] = int(sum(1 for r in rows_per_ep if r))
    return d


def median_or_nan(xs) -> float:
    xs = [float(x) for x in xs if x is not None and np.isfinite(float(x))]
    return float(np.median(xs)) if xs else float("nan")


def cell_name(run_dir: str) -> str:
    """runs/a/b/c -> a__b__c（文件名安全）。"""
    p = Path(run_dir).resolve()
    try:
        rel = p.relative_to(MG_ROOT / "runs")
    except ValueError:
        rel = Path(p.name)
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", str(rel)).strip("_")


def expert_cls_for(name: str):
    """专家注册表。v1 = 冻结的 `mg_expert_reverse.ReverseScriptedExpert`（只 import，不改）。

    档 9 的候选修法是**新增**类（v2*），一行都不碰 v1：180 条示范的出身必须保持 v1 逐比特。
    """
    if name == "v1":
        from mg_expert_reverse import ReverseScriptedExpert
        return ReverseScriptedExpert
    try:
        import mg_expert_v2
    except ImportError as exc:
        raise SystemExit(f"[s9] 未知专家 {name!r}（且 code/mg_expert_v2.py 不在：{exc}）")
    cls = mg_expert_v2.registry().get(name)
    if cls is None:
        raise SystemExit(f"[s9] mg_expert_v2.registry() 里没有 {name!r}；有：{sorted(mg_expert_v2.registry())}")
    return cls


# ─────────────────────── 语料装载 ──────────────────────────────────────────────────────────
def load_corpus(run_dir: str) -> dict:
    rd = Path(run_dir)
    if not rd.is_absolute():
        rd = MG_ROOT / rd
    npz_p = rd / "rollout_actions.npz"
    sum_p = rd / "eval_summary.json"
    if not npz_p.exists():
        raise SystemExit(f"[s9] 没有 {npz_p}（本工具只吃带 rollout_actions.npz 的评测产物）")
    d = np.load(npz_p)
    for k in ("state", "action", "episode_lengths"):
        if k not in d.files:
            raise SystemExit(f"[s9] {npz_p} 缺 {k}；有 {d.files}")
    s = json.load(open(sum_p)) if sum_p.exists() else {}
    per_ep = s.get("per_episode") or []
    lengths = [int(x) for x in d["episode_lengths"]]
    seeds = []
    base = s.get("seed")
    for i, n in enumerate(lengths):
        sd = per_ep[i].get("seed") if i < len(per_ep) and isinstance(per_ep[i], dict) else None
        seeds.append(int(sd) if sd is not None else (int(base) + i if base is not None else -1))
    if any(x < 0 for x in seeds):
        raise SystemExit(f"[s9] {rd} 的 seed 推不出来（summary 无 seed / per_episode 无 seed）")
    st, ac = d["state"], d["action"]
    if st.shape[1] != STATE_DIM or ac.shape[1] != ACTION_DIM:
        raise SystemExit(f"[s9] 维度不符：state {st.shape} / action {ac.shape}（契约 {STATE_DIM}/{ACTION_DIM}）")
    if int(st.shape[0]) != sum(lengths):
        raise SystemExit(f"[s9] state 行数 {st.shape[0]} ≠ sum(episode_lengths) {sum(lengths)}")
    return {"dir": str(rd), "state": st, "action": ac, "lengths": lengths, "seeds": seeds,
            "summary": s, "ckpt": s.get("policy_ckpt", ""), "task_mode": s.get("task_mode", ""),
            "k": s.get("n_action_steps"), "recorded_horizon": int(max(lengths)) if lengths else 0}


# ─────────────────────── 重放一局 ──────────────────────────────────────────────────────────
def replay_one(env, corpus: dict, ep: int, *, harness, horizon: int, trim: bool,
               expert_enabled: bool) -> dict:
    """把语料第 ep 局重放进 env；`expert_enabled=False` 时检测器关掉 ⇒ 纯保真核对。

    语义与 `code/mg_collect_corr.py` 的采集循环**逐条对齐**（同一份 harness、同一份 can_z0 口径、
    同一份「观测在动作之前」的帧口径、同一份 trim/latch/截断规则），只有两处不同：
      * 策略动作来自**录像**而不是 GPU 推理（`policy_fn` 返回 `action[steps]`）；
      * 录像用完（steps ≥ n）就收工，并打 `censored_no_trigger`（见模块头的诚实标注 1）。
    """
    st, ac = corpus["state"], corpus["action"]
    n = int(corpus["lengths"][ep])
    seed = int(corpus["seeds"][ep])
    off = int(sum(corpus["lengths"][:ep]))
    s_rec = st[off:off + n]
    a_rec = ac[off:off + n]

    obs = env.reset(seed=seed)
    can_z0 = float(env.object_pos[2])
    can0 = np.asarray(env.object_pos, dtype=np.float64).copy()
    tilt0 = float(env.can_tilt_deg())
    harness.reset(seed=seed, can_z0=can_z0)

    diag_rows: list[tuple[float, float, str]] = []
    fid: list[float] = []
    can_at_takeover: list[float] = []
    can_tilt_at_takeover = float("nan")
    steps, succ_step, succ_step_rlx = 0, -1, -1
    censored = False
    in_target_at_takeover = False
    t0 = time.perf_counter()

    while True:
        # 只在**策略段**核对保真：接管一旦生效，专家的动作与录像不同 ⇒ 轨迹本该分叉，
        # 拿接管后的步去比只会得到一个大数、把整局误剔（2026-10-04 冒烟实测踩过：
        # ep0 接管@264 却报 fid=7.6e-02）。判定必须在 select() **之前**取，这样「触发那一步」的
        # 观测仍在策略轨迹上、可以合法参与核对。
        was_policy_segment = harness.expert is None
        if steps < n and was_policy_segment:
            rec = np.asarray(s_rec[steps], dtype=np.float64)
            got = np.asarray(obs[STATE_KEY], dtype=np.float64)
            fid.append(float(np.abs(got[:3] - rec[:3]).max()))
            fid.append(float(abs(got[WIDTH_IDX] - rec[WIDTH_IDX])))

        def policy_fn():   # noqa: E306 —— 闭包读当前 steps；harness 当步立即调用
            if steps < n:
                return np.asarray(a_rec[steps], dtype=np.float32)
            return np.zeros(ACTION_DIM, dtype=np.float32)

        act, source = harness.select(obs, steps, policy_fn)
        if source == "expert":
            can_now = np.asarray(env.object_pos, dtype=np.float64)
            eef_now = np.asarray(env.eef_pos, dtype=np.float64)
            if not can_at_takeover:
                can_at_takeover = [round(float(v), 6) for v in can_now]
                can_tilt_at_takeover = float(env.can_tilt_deg())
                # 坑 72：检测器只看 gripper_width ⇒ 会在「can 已进框、正等那 10 步落定」的**已赢局**上触发。
                # 这里用与 mg_env_reverse.step 逐字相同的判据把它数出来（容差 import，不重打）。
                tgt = np.asarray(env.target_xy, dtype=np.float64)
                in_target_at_takeover = bool(
                    abs(can_now[0] - tgt[0]) <= REVERSE_TARGET_TOL_XY
                    and abs(can_now[1] - tgt[1]) <= REVERSE_TARGET_TOL_XY)
            diag_rows.append((float(max(abs(eef_now[0] - can_now[0]), abs(eef_now[1] - can_now[1]))),
                              float(eef_now[2] - can_now[2] - GRASP_OFFSET_Z),
                              str(getattr(harness.expert, "phase", ""))))
        obs, _r, terminated, truncated, info = env.step(act)
        steps += 1
        if info["success"] and succ_step < 0:
            succ_step = steps
        s_rlx = bool(info.get("success_relaxed", info["success"]))
        if s_rlx and succ_step_rlx < 0:
            succ_step_rlx = steps
        harness.note_success(s_rlx)
        if terminated or truncated or (trim and succ_step_rlx > 0):
            break
        if steps >= n and harness.expert is None:
            censored = True       # 录像用完且还没接管 ⇒ 400..horizon 的接管看不见（删失）
            break

    hrec = harness.finish(success=bool(succ_step > 0), success_relaxed=bool(succ_step_rlx > 0),
                          steps=steps)
    seg = harness.buffer.episodes[-1] if harness.buffer.episodes else None
    phases = list(dict.fromkeys(seg["phase"])) if seg is not None else []
    seg_len_raw = int(hrec["seg_len"])
    re_desc = 0
    if phases:
        from mg_collect_corr import re_descend
        re_desc = int(re_descend(phases))
    acc, why = accept_segment(seg_len=seg_len_raw, success_relaxed=bool(succ_step_rlx > 0),
                              handback_at=(int(seg["handback_at"]) if seg is not None else -1),
                              n_re_descend=re_desc, max_seg_len=MAX_SEG_LEN,
                              max_re_descend=MAX_RE_DESCEND)
    rec = {
        "ep": int(ep), "seed": int(seed), "n_recorded": int(n), "steps": int(steps),
        "fid_max": (float(np.max(fid)) if fid else float("nan")),
        "fid_n_compared": int(len(fid)),
        "fid_ok": fidelity_verdict(float(np.max(fid)) if fid else float("nan")),
        "can_z0": round(can_z0, 6), "tilt0_deg": round(tilt0, 3),
        "success": bool(succ_step > 0), "success_step": int(succ_step),
        "success_relaxed": bool(succ_step_rlx > 0), "success_step_relaxed": int(succ_step_rlx),
        "delivered_tipped": bool(succ_step_rlx > 0 and succ_step < 0),
        "takeover": bool(hrec["takeover"]), "trigger": hrec["trigger"],
        "takeover_step": int(hrec["takeover_step"]), "seg_len_raw": seg_len_raw,
        "phases": phases, "re_descend": re_desc, "reached_grasp": bool("grasp" in phases),
        "n_restages": int(hrec["n_restages"]), "unrecoverable": bool(hrec["unrecoverable"]),
        "handback": bool(hrec["handback"]),
        "accept_segment": bool(acc), "reject_why": list(why),
        "censored_no_trigger": bool(censored),
        "diag_descend": descend_diag(diag_rows),
        "n_expert_steps": len(diag_rows),
        "can_at_takeover": can_at_takeover,
        "can_tilt_at_takeover": can_tilt_at_takeover,
        "takeover_after_delivery": bool(in_target_at_takeover),
        "target_tol_xy": float(REVERSE_TARGET_TOL_XY),
        "seconds": round(time.perf_counter() - t0, 2),
    }
    if can_at_takeover:
        dsp = can_displacement(can_at_takeover, can0)
        rec["can_disp"] = dsp
        rec["state_class"] = classify_takeover_state(dxy=dsp["dxy"], tilt_deg=can_tilt_at_takeover)
    else:
        rec["can_disp"] = None
        rec["state_class"] = None
    rec["_diag_rows"] = diag_rows      # 只在进程内用；写盘前剔掉
    return rec


def run_cell(corpus: dict, *, horizon: int, img_size: int, expert: str, max_eps: int | None,
             trim: bool, expert_enabled: bool, verbose: bool = True) -> dict:
    from mg_env_reverse import ReverseGraspEnv
    env = ReverseGraspEnv(img_size=int(img_size), horizon=int(horizon))
    detector = GraspDetector()
    harness = TakeoverHarness(env, expert_cls_for(expert), observe_only=False, min_remain=0,
                              enabled=bool(expert_enabled), detector=detector,
                              buffer=SegmentBuffer(), hand_back=False)
    E = len(corpus["lengths"])
    if max_eps is not None:
        E = min(E, int(max_eps))
    recs = []
    for ep in range(E):
        r = replay_one(env, corpus, ep, harness=harness, horizon=horizon, trim=trim,
                       expert_enabled=expert_enabled)
        rows = r.pop("_diag_rows")
        r["_rows"] = rows
        recs.append(r)
        if verbose:
            print(f"  ep{r['ep']:>2} seed={r['seed']} fid={r['fid_max']:.1e} "
                  f"takeover={str(r['takeover']):>5} step={r['takeover_step']:>4} "
                  f"grasp={str(r['reached_grasp']):>5} rlx={str(r['success_relaxed']):>5} "
                  f"cls={r['state_class']} acc={r['accept_segment']} {r['seconds']}s", flush=True)
    rows_all = [r.pop("_rows") for r in recs]
    return {"recs": recs, "rows_all": rows_all, "env_horizon": int(env.horizon)}


# ─────────────────────── 汇总 ────────────────────────────────────────────────────────────
def aggregate(res: dict, corpus: dict, *, expert: str, mode: str) -> dict:
    recs = res["recs"]
    n_ep = len(recs)
    fid_bad = [r["seed"] for r in recs if not r["fid_ok"]]
    ok = [r for r in recs if r["fid_ok"]]              # 保真不过的局**剔出**分母
    cens = [r for r in ok if r["censored_no_trigger"]]
    tk = [r for r in ok if r["takeover"]]
    tk_rlx = [r for r in tk if r["success_relaxed"]]
    acc = [r for r in tk if r["accept_segment"]]
    frames = int(sum(r["seg_len_raw"] for r in acc))
    per_ep_frames = frames / len(ok) if ok else float("nan")
    gr = [r for r in tk if r["reached_grasp"]]
    ng = [r for r in tk if not r["reached_grasp"]]
    cls_counts = {}
    for r in tk:
        cls_counts[r["state_class"] or "NA"] = cls_counts.get(r["state_class"] or "NA", 0) + 1

    def strat(sub):
        return rate_summary(sum(1 for r in sub if r["success_relaxed"]), len(sub))

    return {
        "tool": "code/mg_s9_rescue.py", "mode": mode, "expert": expert,
        "generated": datetime.now().strftime("%F %T"),
        "corpus_dir": corpus["dir"], "ckpt": corpus["ckpt"],
        "ckpt_tail": (Path(corpus["ckpt"]).parent.name if corpus["ckpt"] else ""),
        "task_mode": corpus["task_mode"], "k": corpus["k"],
        "seeds": [int(recs[0]["seed"]), int(recs[-1]["seed"])] if recs else [],
        "seed_windows_touched": [list(w) for w in touches_eval_window(
            int(recs[0]["seed"]), int(recs[-1]["seed"]))] if recs else [],
        "test_window_contamination": bool(recs and touches_eval_window(
            int(recs[0]["seed"]), int(recs[-1]["seed"])) and
            in_window(int(recs[0]["seed"]), TEST_WINDOW)),
        "env_horizon": res["env_horizon"], "recorded_horizon": corpus["recorded_horizon"],
        "n_episodes": n_ep,
        "fidelity": {"tol": FID_TOL, "n_bad": len(fid_bad), "bad_seeds": fid_bad,
                     "max_over_all": float(np.nanmax([r["fid_max"] for r in recs])) if recs else float("nan"),
                     "n_included": len(ok)},
        "censoring": {"n_censored_no_trigger": len(cens),
                      "note": ("语料 horizon=%d < 采集 horizon=%d ⇒ 只覆盖前 %d 步内触发的接管；"
                               "删失局 %d 个（录像用完仍未触发）"
                               % (corpus["recorded_horizon"], res["env_horizon"],
                                  corpus["recorded_horizon"], len(cens)))},
        "takeover": rate_summary(len(tk), len(ok)),
        "A2_relaxed_success_of_takeover": rate_summary(len(tk_rlx), len(tk)),
        "A2_gate": GATE_A2_RATE,
        "A1_frames": {"usable_frames": frames, "n_accepted": len(acc),
                      "frames_per_episode": per_ep_frames,
                      "scaled_to_%d_episodes" % GATE_A1_EPISODES:
                          (per_ep_frames * GATE_A1_EPISODES if np.isfinite(per_ep_frames) else float("nan")),
                      "gate_frames_per_%d_episodes" % GATE_A1_EPISODES: GATE_A1_FRAMES},
        "A3_seg_len_median_tk_succ": seg_len_median_tk_succ(ok),
        "A3_seg_len_median_accepted": median_or_nan([r["seg_len_raw"] for r in acc]),
        "A3_seg_len_median_all_takeover": median_or_nan([r["seg_len_raw"] for r in tk]),
        "A3_gate_median": GATE_A3_MEDIAN,
        "n_takeover_reached_grasp": int(sum(1 for r in tk if r["reached_grasp"])),
        "n_delivered_tipped": int(sum(1 for r in ok if r["delivered_tipped"])),
        "n_takeover_after_delivery": int(sum(1 for r in tk if r.get("takeover_after_delivery"))),
        "frames_by_state_class": frames_by_state_class(ok),
        "strat_reached_grasp": {"grasp": strat(gr), "nograsp": strat(ng)},
        "strat_state_class": {k: strat([r for r in tk if (r["state_class"] or "NA") == k])
                              for k in sorted(cls_counts)},
        "state_class_counts": cls_counts,
        "reject_reasons": {w: sum(1 for r in tk for x in r["reject_why"] if x == w)
                           for w in sorted({x for r in tk for x in r["reject_why"]})},
        "n_unrecoverable": sum(1 for r in tk if r["unrecoverable"]),
        "n_restages_total": sum(1 for r in tk if r["n_restages"]),
        "pooled_descend_counts": descend_pooled_from_recs(ok),
        "n_nograsp_blind_dominant": sum(1 for r in ng if r["diag_descend"]["blind_dominant"]),
        "per_episode": recs,
    }


def pool_cells(cells: list[dict]) -> dict:
    """把若干格的 agg 池化（同一 expert / 同一 horizon 才池；否则拒绝，免得混口径）。"""
    if not cells:
        raise SystemExit("[s9] 没有可池化的格")
    ex = {c["expert"] for c in cells}
    hz = {c["env_horizon"] for c in cells}
    if len(ex) != 1 or len(hz) != 1:
        raise SystemExit(f"[s9] 拒绝池化：expert={sorted(ex)} horizon={sorted(hz)}（口径必须一致，坑 57）")
    recs = [r for c in cells for r in c["per_episode"]]
    tk = [r for r in recs if r["takeover"] and r["fid_ok"]]
    ok = [r for r in recs if r["fid_ok"]]
    acc = [r for r in tk if r["accept_segment"]]
    frames = int(sum(r["seg_len_raw"] for r in acc))
    per_ep_frames = frames / len(ok) if ok else float("nan")

    def strat(sub):
        return rate_summary(sum(1 for r in sub if r["success_relaxed"]), len(sub))

    gr = [r for r in tk if r["reached_grasp"]]
    ng = [r for r in tk if not r["reached_grasp"]]
    cls = {}
    for r in tk:
        cls[r["state_class"] or "NA"] = cls.get(r["state_class"] or "NA", 0) + 1
    return {
        "tool": "code/mg_s9_rescue.py", "mode": "pooled", "expert": ex.pop(),
        "generated": datetime.now().strftime("%F %T"),
        "n_cells": len(cells), "cells": [c["corpus_dir"] for c in cells],
        "ckpts": sorted({c["ckpt_tail"] for c in cells}),
        "env_horizon": hz.pop(),
        "test_window_contamination": any(c["test_window_contamination"] for c in cells),
        "n_episodes": len(recs),
        "fidelity": {"tol": FID_TOL, "n_bad": len(recs) - len(ok), "n_included": len(ok),
                     "max_over_all": float(np.nanmax([r["fid_max"] for r in recs])) if recs else float("nan")},
        "censoring": {"n_censored_no_trigger": sum(1 for r in ok if r["censored_no_trigger"])},
        "takeover": rate_summary(len(tk), len(ok)),
        "A2_relaxed_success_of_takeover": rate_summary(
            sum(1 for r in tk if r["success_relaxed"]), len(tk)),
        "A2_gate": GATE_A2_RATE,
        "A1_frames": {"usable_frames": frames, "n_accepted": len(acc),
                      "frames_per_episode": per_ep_frames,
                      "scaled_to_%d_episodes" % GATE_A1_EPISODES: per_ep_frames * GATE_A1_EPISODES,
                      "gate_frames_per_%d_episodes" % GATE_A1_EPISODES: GATE_A1_FRAMES},
        "A3_seg_len_median_tk_succ": seg_len_median_tk_succ(recs),
        "A3_seg_len_median_accepted": median_or_nan([r["seg_len_raw"] for r in acc]),
        "A3_seg_len_median_all_takeover": median_or_nan([r["seg_len_raw"] for r in tk]),
        "A3_gate_median": GATE_A3_MEDIAN,
        "n_takeover_reached_grasp": int(sum(1 for r in tk if r["reached_grasp"])),
        "n_delivered_tipped": int(sum(1 for r in ok if r["delivered_tipped"])),
        "n_takeover_after_delivery": int(sum(1 for r in tk if r.get("takeover_after_delivery"))),
        "frames_by_state_class": frames_by_state_class(ok),
        "strat_reached_grasp": {"grasp": strat(gr), "nograsp": strat(ng)},
        "strat_state_class": {k: strat([r for r in tk if (r["state_class"] or "NA") == k])
                              for k in sorted(cls)},
        "state_class_counts": cls,
        "n_nograsp_blind_dominant": sum(1 for r in ng if r["diag_descend"]["blind_dominant"]),
        "pooled_descend_counts": descend_pooled_from_recs(recs),
        "n_unrecoverable": sum(1 for r in tk if r["unrecoverable"]),
        "per_episode": recs,
    }


def fmt_rate(d: dict) -> str:
    if not d or not d.get("n"):
        return f"{d.get('k', 0)}/{d.get('n', 0)} = NA"
    lp = " ⚠️`LOW_POWER`" if d.get("low_power") else ""
    return (f"{d['k']}/{d['n']} = {100 * d['rate']:.1f}% "
            f"[{100 * d['wilson_lo']:.1f}, {100 * d['wilson_hi']:.1f}]{lp}")


def to_md(agg: dict) -> str:
    L: list[str] = []
    pooled = agg.get("mode") == "pooled"
    L.append("# 档 9 预备 · CPU-only 重放接管台" + ("（池化）" if pooled else ""))
    L.append("")
    L.append(f"* 生成时间：{agg['generated']}（`code/mg_s9_rescue.py`，零 GPU 推理）")
    L.append(f"* 专家：`{agg['expert']}`   env horizon：{agg['env_horizon']}（采集口径 "
             f"`COLLECT_HORIZON={COLLECT_HORIZON}`；评测恒 {HORIZON}）")
    if pooled:
        L.append(f"* 池化 {agg['n_cells']} 格；检查点尾串：{agg['ckpts']}")
        for c in agg["cells"]:
            L.append(f"  * `{c}`")
    else:
        L.append(f"* 语料：`{agg['corpus_dir']}`")
        L.append(f"* 策略 ckpt：`{agg['ckpt']}`   task_mode={agg['task_mode']}  K={agg['k']}")
    L.append(f"* seed 窗口：{agg.get('seeds')}；碰到的评测窗口：{agg.get('seed_windows_touched')}")
    if agg.get("test_window_contamination"):
        L.append("* 🚨 `TEST_WINDOW_CONTAMINATION`：本产物用了 D1 的 TEST 窗口 7000..7019 ⇒ "
                 "**不许**据此定专家的修法（坑 33 家族）")
    L.append("")
    L.append("## ⚠️ 三条诚实标注（不许摘）")
    L.append(f"1. **删失**：{agg['censoring']['note'] if not pooled else agg['censoring']}")
    L.append(f"2. **保真**：容差 {agg['fidelity']['tol']}；实测全语料 `max|Δ| = "
             f"{agg['fidelity']['max_over_all']:.3e}`；剔出 {agg['fidelity']['n_bad']} 局、"
             f"纳入 {agg['fidelity']['n_included']} 局。")
    L.append("3. **出身**：这是**重放**语料，不是 8A 的新采集（8A 用 seed 9000..9079）。"
             "⇒ 只能读成「机理与方向」，不能读成 8A 的产出率本身。")
    L.append("")
    L.append("## 一、三条门的事前实测（同一份 harness 语义、同一批常数）")
    L.append("")
    L.append("| 门 | 判据 | 本台实测 | 判 |")
    L.append("|:--|:--|:--|:--|")
    a1 = agg["A1_frames"]
    a1v = a1["scaled_to_%d_episodes" % GATE_A1_EPISODES]
    L.append(f"| **A1** | ≥{GATE_A1_FRAMES} 可用帧/{GATE_A1_EPISODES} 局 | "
             f"{a1['usable_frames']} 帧/{agg['n_episodes']} 局 ⇒ 每局 {a1['frames_per_episode']:.1f} 帧 "
             f"⇒ 折算 {a1v:.0f} 帧 | {'✅' if a1v >= GATE_A1_FRAMES else '❌'} |")
    a2 = agg["A2_relaxed_success_of_takeover"]
    L.append(f"| **A2** | ≥{100 * GATE_A2_RATE:.0f}% | {fmt_rate(a2)} | "
             f"{'✅' if (a2['n'] and a2['rate'] >= GATE_A2_RATE) else '❌'} |")
    a3 = agg["A3_seg_len_median_tk_succ"]
    L.append(f"| **A3** | 段长中位 ≤{GATE_A3_MEDIAN}（放宽成功总体） | {a3:.1f} | "
             f"{'✅' if (np.isfinite(a3) and a3 <= GATE_A3_MEDIAN) else '❌'} |")
    L.append("")
    L.append(f"* 接管率：{fmt_rate(agg['takeover'])}")
    L.append(f"* 专家显式认输（unrecoverable）：{agg['n_unrecoverable']} 次")
    nad = agg.get("n_takeover_after_delivery", 0)
    ntk0 = max(1, a2["n"])
    L.append(f"* 🚨 坑 72 的直接测量：接管时 can **已在目标框内**（`±{REVERSE_TARGET_TOL_XY}`）"
             f"= **{nad}/{a2['n']}** 接管（{100 * nad / ntk0:.1f}%）⇒ 这些局是「已经赢下、只差落定那 10 步」，"
             "却贡献了 A2 的分子（量级小则有界，见 README 坑 72）")
    fbc = agg.get("frames_by_state_class") or {}
    tot_f = sum(fbc.values()) or 1
    L.append("* 可用纠正帧按接管状态类拆分（预测 8B 那份数据**教的是什么**）："
             + "、".join(f"`{k}` {v} 帧（{100 * v / tot_f:.1f}%）" for k, v in sorted(fbc.items())))
    if not pooled:
        L.append(f"* 三条过滤的拒收理由分布：{agg['reject_reasons']}")
    L.append("")
    L.append("## 二、接管瞬间的 can 真值（**无偏**；修坑 71 的那条读数）")
    L.append("")
    L.append("| 类别 | 判据 | 接管数 | 占接管 | 该类放宽成功 |")
    L.append("|:--|:--|--:|--:|:--|")
    ntk = max(1, a2["n"])
    for k in ("CLEAN", "MOVED", "TILT", "NA"):
        if k not in agg["state_class_counts"]:
            continue
        cnt = agg["state_class_counts"][k]
        sr = agg["strat_state_class"].get(k, {})
        L.append(f"| `{k}` | {({'CLEAN': '水平位移 ≤10 mm ∧ 倾角 ≤10°', 'MOVED': '水平位移 >10 mm（立着）', 'TILT': '倾角 >10°（被撞倒/斜）', 'NA': '无接管'})[k]} "
                 f"| {cnt} | {100 * cnt / ntk:.1f}% | {fmt_rate(sr)} |")
    L.append("")
    L.append("## 三、到不到 `grasp` 的分层（与 `mg_forecast_s8a.py` 同一把尺，但这里是无偏的）")
    L.append("")
    L.append("| 层 | n | 放宽成功 |")
    L.append("|:--|--:|:--|")
    for k in ("grasp", "nograsp"):
        L.append(f"| `{k}` | {agg['strat_reached_grasp'][k]['n']} | "
                 f"{fmt_rate(agg['strat_reached_grasp'][k])} |")
    L.append("")
    L.append(f"* 「未到 grasp」里 `blind_dominant`（≥50% 的 descend 步在盲区）的局数："
             f"**{agg['n_nograsp_blind_dominant']}**")
    pd = agg.get("pooled_descend_counts") or {}
    L.append(f"* 池化 descend 读数：{json.dumps({k: v for k, v in pd.items() if not isinstance(v, (list, dict))}, ensure_ascii=False)}")
    L.append("")
    L.append("## 四、复现")
    L.append("")
    L.append("```bash")
    L.append("bash -c 'source code/env.sh && $MG_PY code/mg_s9_rescue.py --selftest'")
    L.append("```")
    return "\n".join(L) + "\n"


# ─────────────────────── 自测（纯 CPU、假数据、不读写 runs/）───────────────────────────────
def _wilson_ref(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson 区间的**独立**实现（只为自测对账；坑 65：期望值不共用被测代码）。"""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def _fake_rec(**kw):
    base = {"ep": 0, "seed": 8000, "n_recorded": 400, "steps": 400, "fid_max": 0.0,
            "fid_n_compared": 800, "fid_ok": True, "can_z0": 0.8603, "tilt0_deg": 0.07,
            "success": False, "success_step": -1, "success_relaxed": False,
            "success_step_relaxed": -1, "delivered_tipped": False, "takeover": False,
            "trigger": None, "takeover_step": -1, "seg_len_raw": 0, "phases": [],
            "re_descend": 0, "reached_grasp": False, "n_restages": 0, "unrecoverable": False,
            "handback": False, "accept_segment": False, "reject_why": ["未接管"],
            "censored_no_trigger": True,
            "diag_descend": {"n_expert_steps": 0, "n_descend_steps": 0, "n_descend_z_ok": 0,
                             "n_descend_z_below": 0, "n_blind": 0,
                             "frac_blind_of_descend": float("nan"),
                             "frac_blind_of_z_ok": float("nan"), "blind_dominant": False},
            "n_expert_steps": 0, "can_at_takeover": [], "can_tilt_at_takeover": float("nan"),
            "can_disp": None, "state_class": None, "seconds": 0.0,
            "takeover_after_delivery": False, "target_tol_xy": 0.09}
    base.update(kw)
    return base


def selftest() -> int:
    n_ok = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n_ok
        if not cond:
            raise AssertionError(f"selftest 失败：{name} {detail}")
        n_ok += 1

    # ── 窗口纪律（本工具最重要的一条护栏）──────────────────────────────────
    ck("in_window 左闭", in_window(7000, TEST_WINDOW))
    ck("in_window 右闭", in_window(7019, TEST_WINDOW))
    ck("in_window 左外", not in_window(6999, TEST_WINDOW))
    ck("in_window 右外", not in_window(7020, TEST_WINDOW))
    ck("val 窗口只碰 (8000,8019)", touches_eval_window(8000, 8019) == [(8000, 8019)])
    ck("采集窗口 9000..9079 谁都不碰", touches_eval_window(9000, 9079) == [])
    ck("TEST 窗口被认出来", (7000, 7019) in touches_eval_window(7000, 7019))
    ck("TEST_WINDOW 与 chain_s8c 的 REV_SEED0 一致", TEST_WINDOW == (7000, 7019))
    ck("采集 horizon 是 import 来的 800", COLLECT_HORIZON == 800)
    ck("评测 horizon 是冻结的 400", HORIZON == 400)

    # ── can 位移 / 状态分类（期望值按定义手算）────────────────────────────
    d0 = can_displacement([0.10, -0.25, 0.8603], [0.10, -0.25, 0.8603])
    ck("位移 0", abs(d0["dxy"]) < 1e-12 and d0["dz"] == 0.0 and not d0["moved_xy"])
    d1 = can_displacement([0.112, -0.25, 0.8603], [0.100, -0.25, 0.8603])
    ck("dx=12mm > 10mm ⇒ moved", abs(d1["dxy"] - 0.012) < 1e-12 and d1["moved_xy"])
    d2 = can_displacement([0.106, -0.258, 0.8603], [0.100, -0.250, 0.8603])
    ck("3-4-5 直角 ⇒ dxy=10mm 不超门", abs(d2["dxy"] - 0.010) < 1e-12 and not d2["moved_xy"])
    ck("CLEAN", classify_takeover_state(dxy=0.005, tilt_deg=0.1) == "CLEAN")
    ck("MOVED", classify_takeover_state(dxy=0.020, tilt_deg=0.1) == "MOVED")
    ck("TILT", classify_takeover_state(dxy=0.005, tilt_deg=89.9) == "TILT")
    ck("TILT 优先于 MOVED（严重度排序）",
       classify_takeover_state(dxy=0.050, tilt_deg=45.0) == "TILT")
    ck("边界：dxy 恰 =10mm 不算 MOVED（严格大于）",
       classify_takeover_state(dxy=CAN_MOVED_XY, tilt_deg=0.0) == "CLEAN")
    ck("边界：tilt 恰 =10° 不算 TILT（严格大于）",
       classify_takeover_state(dxy=0.0, tilt_deg=CAN_TILTED_DEG) == "CLEAN")

    # ── 保真判定 ─────────────────────────────────────────────────────────
    ck("逐比特 ⇒ 保真过", fidelity_verdict(0.0))
    ck("1e-7 ⇒ 过", fidelity_verdict(1e-7))
    ck("1e-5 ⇒ 不过（要剔出）", not fidelity_verdict(1e-5))
    ck("nan ⇒ 不过（不许静默放行）", not fidelity_verdict(float("nan")))

    # ── Wilson 对账（独立实现）──────────────────────────────────────────
    for k, n in ((0, 5), (4, 10), (8, 35), (35, 80)):
        got = wilson(k, n)
        ref = _wilson_ref(k, n)
        ck(f"wilson({k},{n}) 与独立实现对账", abs(got[0] - ref[0]) < 1e-12 and abs(got[1] - ref[1]) < 1e-12,
           f"got={got} ref={ref}")
    r = rate_summary(4, 10)
    ck("rate_summary 点估计", abs(r["rate"] - 0.4) < 1e-12 and not r["low_power"])
    ck("rate_summary n<5 打 LOW_POWER", rate_summary(1, 3)["low_power"])
    ck("rate_summary n=0 不给假数", np.isnan(rate_summary(0, 0)["rate"]))

    # ── 中位数 / 命名 ────────────────────────────────────────────────────
    ck("median 偶数个取均值", median_or_nan([1, 2, 3, 4]) == 2.5)
    ck("median 空 ⇒ nan", np.isnan(median_or_nan([])))
    ck("median 忽略 None/nan", median_or_nan([1, None, 3, float("nan")]) == 2.0)
    ck("cell_name 相对 runs/", cell_name("runs/a/b") == "a__b")
    ck("cell_name 去掉路径分隔符", "/" not in cell_name("runs/a/b/c"))

    # ── pool_descend 与采集器同口径（手算期望）────────────────────────────
    rows = [("descend", 0.001, 0.005), ("descend", 0.020, 0.005), ("descend", 0.020, -0.030),
            ("approach", 0.020, 0.005)]
    got = pool_descend([[ (xy, z, ph) for ph, xy, z in rows ]])
    # descend 步 3 个：①xy 对准且带内 ②带内但 xy 偏（盲区）③低于带（盲区，另计 z_below）
    ck("pool_descend n_descend_steps=3", got["n_descend_steps"] == 3, str(got))
    ck("pool_descend n_blind=1（带内 ∧ xy 偏）", got["n_blind"] == 1, str(got))
    ck("pool_descend n_descend_z_ok=2", got["n_descend_z_ok"] == 2, str(got))
    ck("pool_descend n_descend_z_below=1", got["n_descend_z_below"] == 1, str(got))
    ck("pool_descend frac_blind_of_descend=1/3", abs(got["frac_blind_of_descend"] - 1 / 3) < 1e-12)
    ck("pool_descend blind_dominant=False（1*2 < 3）", got["blind_dominant"] is False)
    ck("pool_descend 局计数", got["n_episodes_with_expert_steps"] == 1)

    # ── 专家注册表：v1 必须是**冻结的那个类**（不许悄悄换掉出身）───────────
    from mg_expert_reverse import ReverseScriptedExpert
    ck("expert_cls_for('v1') 就是冻结的 ReverseScriptedExpert",
       expert_cls_for("v1") is ReverseScriptedExpert)
    ck("v1 有 harness 要的三个接口",
       all(hasattr(ReverseScriptedExpert, a) for a in ("resume", "__call__")))
    try:
        expert_cls_for("__no_such_expert__")
        raise AssertionError("selftest 失败：未知专家名应该报错")
    except SystemExit:
        n_ok += 1

    # ── aggregate 的算术（合成 5 局；期望值全部手算，且刻意让 A3 的三个口径互相不同）──
    def _dg(ns, nd, nz, nb, nbl, dom):
        return {"n_expert_steps": ns, "n_descend_steps": nd, "n_descend_z_ok": nz,
                "n_descend_z_below": nb, "n_blind": nbl, "blind_dominant": dom}
    recs = [
        _fake_rec(ep=0, seed=8000, takeover=True, trigger="T1", takeover_step=120,
                  seg_len_raw=200, accept_segment=True, reject_why=[], reached_grasp=True,
                  success_relaxed=True, success_step_relaxed=300, censored_no_trigger=False,
                  state_class="CLEAN", takeover_after_delivery=True,
                  diag_descend=_dg(200, 100, 40, 5, 10, False)),
        _fake_rec(ep=1, seed=8001, takeover=True, trigger="T3", takeover_step=250,
                  seg_len_raw=400, accept_segment=False, reject_why=["段长超上限"],
                  reached_grasp=False, success_relaxed=False, censored_no_trigger=False,
                  state_class="TILT", diag_descend=_dg(400, 300, 100, 60, 200, True)),
        _fake_rec(ep=2, seed=8002, takeover=True, trigger="T1", takeover_step=90,
                  seg_len_raw=100, accept_segment=False, reject_why=["放宽成功=否"],
                  reached_grasp=False, success_relaxed=False, censored_no_trigger=False,
                  state_class="MOVED", diag_descend=_dg(100, 50, 10, 0, 8, False)),
        _fake_rec(ep=3, seed=8003, fid_ok=False, fid_max=1e-3),      # 保真不过 ⇒ 必须被剔出
        _fake_rec(ep=4, seed=8004, takeover=True, trigger="T1", takeover_step=60,
                  seg_len_raw=500, accept_segment=False, reject_why=["段长超上限"],
                  reached_grasp=True, success_relaxed=True, success_step_relaxed=540,
                  censored_no_trigger=False, state_class="CLEAN",
                  diag_descend=_dg(500, 150, 60, 10, 20, False)),
    ]
    corpus = {"dir": "/fake", "ckpt": "/x/checkpoints/022000/pretrained_model",
              "task_mode": "reverse", "k": 10, "recorded_horizon": 400,
              "state": None, "action": None, "lengths": [], "seeds": [], "summary": {}}
    agg = aggregate({"recs": recs, "rows_all": [], "env_horizon": 800}, corpus,
                    expert="v1", mode="rescue")
    ck("保真不过的局被剔出分母", agg["fidelity"]["n_included"] == 4 and agg["fidelity"]["n_bad"] == 1)
    ck("ckpt 尾串抽得对", agg["ckpt_tail"] == "022000", agg["ckpt_tail"])
    ck("接管 = 4/4", agg["takeover"]["k"] == 4 and agg["takeover"]["n"] == 4)
    ck("A2 = 2/4（ep0 + ep4）", agg["A2_relaxed_success_of_takeover"]["k"] == 2
       and agg["A2_relaxed_success_of_takeover"]["n"] == 4)
    # A1：只有 ep0 被收下（ep4 段长 500 > MAX_SEG_LEN=300 被过滤 3 拒）⇒ 200 帧 / 4 局 = 50 帧每局
    ck("A1 可用帧 = 200（只 ep0）", agg["A1_frames"]["usable_frames"] == 200)
    ck("A1 收下 1 段", agg["A1_frames"]["n_accepted"] == 1)
    ck("A1 每局帧 = 200/4 = 50", abs(agg["A1_frames"]["frames_per_episode"] - 50.0) < 1e-12)
    ck("A1 折算到 80 局 = 4000", abs(agg["A1_frames"]["scaled_to_%d_episodes" % GATE_A1_EPISODES]
                                     - 4000.0) < 1e-9)
    # A3 三个口径必须互相可分：判据口径 = 放宽成功总体 median(200,500)=350；
    #   只算收下的 = 200；全部接管 = median(100,200,400,500)=300
    ck("A3 判据口径 = median(200,500) = 350", abs(agg["A3_seg_len_median_tk_succ"] - 350.0) < 1e-12)
    ck("A3 只算收下的 = 200（≠ 判据口径 ⇒ 两者确实不同）",
       abs(agg["A3_seg_len_median_accepted"] - 200.0) < 1e-12)
    ck("A3 全部接管 = median(100,200,400,500) = 300（只透明）",
       abs(agg["A3_seg_len_median_all_takeover"] - 300.0) < 1e-12)
    ck("A3 判据口径 != 只算收下的", agg["A3_seg_len_median_tk_succ"] != agg["A3_seg_len_median_accepted"])
    ck("分层 grasp = 2/2", agg["strat_reached_grasp"]["grasp"]["k"] == 2
       and agg["strat_reached_grasp"]["grasp"]["n"] == 2)
    ck("分层 nograsp = 0/2", agg["strat_reached_grasp"]["nograsp"]["k"] == 0
       and agg["strat_reached_grasp"]["nograsp"]["n"] == 2)
    ck("到 grasp 的接管数 = 2", agg["n_takeover_reached_grasp"] == 2)
    ck("nograsp 里 blind_dominant = 1 局", agg["n_nograsp_blind_dominant"] == 1)
    ck("状态类计数", agg["state_class_counts"] == {"CLEAN": 2, "MOVED": 1, "TILT": 1})
    ck("拒收理由计数", agg["reject_reasons"] == {"段长超上限": 2, "放宽成功=否": 1})
    ck("val 语料不打 TEST 污染标", agg["test_window_contamination"] is False)
    ck("坑72 计数 = 1（只有 ep0 打了标）", agg["n_takeover_after_delivery"] == 1)
    ck("帧按类拆 = {CLEAN: 200}", agg["frames_by_state_class"] == {"CLEAN": 200},
       str(agg["frames_by_state_class"]))
    ck("frames_by_state_class 只算收下的（ep1/ep2/ep4 被拒 ⇒ 不进）",
       sum(agg["frames_by_state_class"].values()) == agg["A1_frames"]["usable_frames"])
    ck("frames_by_state_class 剔掉保真不过的局",
       frames_by_state_class([_fake_rec(takeover=True, accept_segment=True, seg_len_raw=99,
                                        fid_ok=False, state_class="CLEAN")]) == {})
    # 池化 descend：只算「保真过 ∧ 接管」的局 = ep0+ep1+ep2+ep4
    pd = agg["pooled_descend_counts"]
    ck("池化 n_descend_steps = 100+300+50+150 = 600", pd["n_descend_steps"] == 600, str(pd))
    ck("池化 n_blind = 10+200+8+20 = 238", pd["n_blind"] == 238, str(pd))
    ck("池化 n_descend_z_ok = 40+100+10+60 = 210", pd["n_descend_z_ok"] == 210)
    ck("池化 frac_blind_of_descend = 238/600", abs(pd["frac_blind_of_descend"] - 238 / 600) < 1e-12)
    ck("池化 frac_blind_of_z_ok = 238/210 > 1（合法：盲区含低于带面的步）",
       pd["frac_blind_of_z_ok"] > 1.0)
    ck("池化局计数 = 4", pd["n_takeover_episodes"] == 4)

    recs_t = [_fake_rec(ep=0, seed=7000, takeover=True)]
    agg_t = aggregate({"recs": recs_t, "rows_all": [], "env_horizon": 800}, corpus,
                      expert="v1", mode="rescue")
    ck("TEST 窗口语料**必须**打污染标", agg_t["test_window_contamination"] is True)

    # ── pool_cells：口径不一致要拒绝（坑 57）──────────────────────────────
    a1 = dict(agg); a2 = dict(agg)
    a2["expert"] = "v2align"
    try:
        pool_cells([a1, a2])
        raise AssertionError("selftest 失败：不同 expert 不该池化")
    except SystemExit:
        n_ok += 1
    a3 = dict(agg); a3["env_horizon"] = 400
    try:
        pool_cells([a1, a3])
        raise AssertionError("selftest 失败：不同 horizon 不该池化")
    except SystemExit:
        n_ok += 1
    ja = json.loads(json.dumps(agg, default=str))
    pl = pool_cells([ja, json.loads(json.dumps(ja))])
    ck("同口径池化 ⇒ 局数翻倍（含保真不过的局）", pl["n_episodes"] == 10, str(pl["n_episodes"]))
    ck("池化保真：剔出 2 / 纳入 8", pl["fidelity"]["n_bad"] == 2
       and pl["fidelity"]["n_included"] == 8)
    ck("池化接管 = 8", pl["takeover"]["n"] == 8 and pl["takeover"]["k"] == 8)
    ck("池化 A2 = 4/8", pl["A2_relaxed_success_of_takeover"]["k"] == 4)
    ck("池化 A3 判据口径 = 350（与单格同，因为两格一样）",
       abs(pl["A3_seg_len_median_tk_succ"] - 350.0) < 1e-12)
    ck("池化坑72 计数 = 2（两格各 1）", pl["n_takeover_after_delivery"] == 2)
    ck("池化帧按类拆 = {CLEAN: 400}", pl["frames_by_state_class"] == {"CLEAN": 400},
       str(pl["frames_by_state_class"]))
    ck("池化 descend 计数是两格之和", pl["pooled_descend_counts"]["n_descend_steps"] == 1200)
    ck("池化 frac_blind_of_descend 不变（比值）= 238/600",
       abs(pl["pooled_descend_counts"]["frac_blind_of_descend"] - 238 / 600) < 1e-12)

    # ── to_md 冒烟（不写盘，只看它不炸且关键表头在）────────────────────────
    md = to_md(agg)
    for needle in ("三条门的事前实测", "**A1**", "**A2**", "**A3**", "无偏", "诚实标注",
                   "`CLEAN`", "`nograsp`"):
        ck(f"md 含 {needle!r}", needle in md)
    md2 = to_md(pl)
    ck("池化 md 也能渲染", "池化" in md2 and "**A2**" in md2)

    print(f"[s9-rescue] 全绿：{n_ok} 项（假数据，未使用 GPU / 未读写 runs）")
    return 0


# ─────────────────────── main ───────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("fidelity", "rescue", "report", "recompute"),
                    default="rescue")
    ap.add_argument("--runs", nargs="*", default=[], help="带 rollout_actions.npz 的评测产物目录")
    ap.add_argument("--expert", default="v1", help="v1（冻结）或 mg_expert_v2.registry() 里的名字")
    ap.add_argument("--horizon", type=int, default=COLLECT_HORIZON,
                    help=f"重放时的 env horizon（默认 = 采集口径 {COLLECT_HORIZON}）")
    ap.add_argument("--img-size", type=int, default=8,
                    help="渲染尺寸。物理与它无关（本工具已逐比特自证）⇒ 取小只为快")
    ap.add_argument("--max-eps", type=int, default=0, help="每格最多跑几局（0 = 全部）")
    ap.add_argument("--no-trim", action="store_true", help="关掉「放宽成功即收工」（采集器默认开）")
    ap.add_argument("--allow-test-window", action="store_true",
                    help="⚠️ 允许吃 D1 的 TEST 窗口 7000..7019 的语料（会给产物打污染标）")
    ap.add_argument("--out", default="", help="单格模式：产物目录")
    ap.add_argument("--indir", default="", help="report 模式：单格 json 所在目录")
    ap.add_argument("--out-md", default="", help="report 模式：汇总 md 路径")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if a.mode == "recompute":
        # 改了汇总口径时用：只读 per_episode 重算读数，不重跑仿真（保真/接管/A2 的原始逐局卡片不动）
        indir = Path(a.indir or (MG_ROOT / "runs/_diag/s9_rescue"))
        if not indir.is_absolute():
            indir = MG_ROOT / indir
        n = 0
        for pj in sorted(p for p in indir.glob("*.json") if not p.name.startswith("_")):
            old = json.load(open(pj))
            if old.get("mode") not in ("fidelity", "rescue"):
                continue
            corpus = {"dir": old["corpus_dir"], "ckpt": old["ckpt"],
                      "task_mode": old["task_mode"], "k": old["k"],
                      "recorded_horizon": old["recorded_horizon"], "state": None,
                      "action": None, "lengths": [], "seeds": [], "summary": {}}
            new_agg = aggregate({"recs": old["per_episode"], "rows_all": [],
                                 "env_horizon": old["env_horizon"]}, corpus,
                                expert=old["expert"], mode=old["mode"])
            pj.write_text(json.dumps(new_agg, ensure_ascii=False, indent=1, default=str))
            pj.with_suffix(".md").write_text(to_md(new_agg))
            n += 1
            print(f"[s9] 重算 {pj.name}: A2 {new_agg['A2_relaxed_success_of_takeover']['k']}/"
                  f"{new_agg['A2_relaxed_success_of_takeover']['n']}  A3判据口径 "
                  f"{new_agg['A3_seg_len_median_tk_succ']}")
        print(f"[s9] 重算完成：{n} 格（{indir}）")
        return 0

    if a.mode == "report":
        indir = Path(a.indir or (MG_ROOT / "runs/_diag/s9_rescue"))
        if not indir.is_absolute():
            indir = MG_ROOT / indir
        files = sorted(p for p in indir.glob("*.json") if not p.name.startswith("_"))
        cells = [json.load(open(p)) for p in files]
        cells = [c for c in cells if c.get("mode") in ("fidelity", "rescue")]
        if not cells:
            raise SystemExit(f"[s9] {indir} 里没有单格产物（*.json，mode=fidelity|rescue）")
        groups: dict[tuple, list[dict]] = {}
        for c in cells:
            groups.setdefault((c["expert"], c["env_horizon"], c["mode"]), []).append(c)
        out_md = Path(a.out_md or (indir / "REPORT.md"))
        if not out_md.is_absolute():
            out_md = MG_ROOT / out_md
        parts, pooled_all = [], []
        for (ex, hz, md_), grp in sorted(groups.items()):
            pl = pool_cells(grp)
            pooled_all.append(pl)
            parts.append(f"\n\n---\n\n# 组：expert=`{ex}` horizon={hz} mode={md_}（{len(grp)} 格）\n\n"
                         + to_md(pl))
            (indir / f"_pooled_{ex}_{hz}_{md_}.json").write_text(
                json.dumps(pl, ensure_ascii=False, indent=1, default=str))
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("".join(parts))
        print(f"[s9] 汇总 -> {out_md}（{len(pooled_all)} 组）")
        return 0

    if not a.runs:
        raise SystemExit("[s9] --mode fidelity|rescue 需要 --runs <目录>...")
    out = Path(a.out or (MG_ROOT / "runs/_diag/s9_rescue"))
    if not out.is_absolute():
        out = MG_ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    expert_enabled = (a.mode == "rescue")
    for rd in a.runs:
        corpus = load_corpus(rd)
        lo, hi = int(corpus["seeds"][0]), int(corpus["seeds"][-1])
        hit = touches_eval_window(lo, hi)
        print(f"[s9] === {corpus['dir']} seed {lo}..{hi} 碰到评测窗口 {hit} "
              f"ckpt={Path(corpus['ckpt']).parent.name} "
              f"K={corpus['k']} ===", flush=True)
        if in_window(lo, TEST_WINDOW) or in_window(hi, TEST_WINDOW):
            if not a.allow_test_window:
                raise SystemExit(
                    f"[s9] 拒绝：seed {lo}..{hi} 落在 D1 的 TEST 窗口 {TEST_WINDOW} 里 ⇒ "
                    "用它定专家的修法 = 拿 TEST 调参（坑 33 家族）。"
                    "改用 val 窗口语料（seed 8000..8019），或显式加 --allow-test-window 并接受污染标。")
            print("[s9] 🚨 --allow-test-window：产物会打 TEST_WINDOW_CONTAMINATION 标", flush=True)
        res = run_cell(corpus, horizon=int(a.horizon), img_size=int(a.img_size), expert=a.expert,
                       max_eps=(int(a.max_eps) or None), trim=not a.no_trim,
                       expert_enabled=expert_enabled)
        agg = aggregate(res, corpus, expert=a.expert, mode=a.mode)
        name = cell_name(corpus["dir"])
        (out / f"{name}.json").write_text(json.dumps(agg, ensure_ascii=False, indent=1, default=str))
        (out / f"{name}.md").write_text(to_md(agg))
        f = agg["fidelity"]
        print(f"[s9] {name}: 保真 max|Δ|={f['max_over_all']:.3e} 剔出 {f['n_bad']}/{agg['n_episodes']} | "
              f"接管 {agg['takeover']['k']}/{agg['takeover']['n']} | "
              f"A2 {agg['A2_relaxed_success_of_takeover']['k']}/{agg['A2_relaxed_success_of_takeover']['n']}"
              f" = {100 * agg['A2_relaxed_success_of_takeover']['rate']:.1f}% | "
              f"可用帧 {agg['A1_frames']['usable_frames']} | "
              f"状态类 {agg['state_class_counts']} -> {out / name}.md", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
