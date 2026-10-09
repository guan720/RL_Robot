#!/usr/bin/env python3
"""官方 LeRobot ACT checkpoint 的闭环真值评测（Lift，20 局，pinned seeds 5000-5019）。

口径与 `scripts/eval_act_lift_truth.py`（自研 MLP ACT 用的那个）逐项对齐，方便三列并排：
scripted teacher 20/20、自研 MLP ACT 0/20、官方 LeRobot ACT = 本脚本的结果。

评测协议（与 `runs/infra/lerobot_act_runtime_readiness_audit.md` 的必检项一致）：
  - 环境：`harness.env_factory.make_contact_env('lift', ...)`，构造期钉死物体几何
    （`PINNED_OBJECT_SEED=20260923`），出题走 `reset_contact(env, seed)`；
  - 观测：60 维 state = `robot0_proprio-state`(50) + `object-state`(10)，按官方 key 拆成
    `observation.state` / `observation.environment_state` 喂给 policy；
  - 动作：官方 `predict_action_chunk` 出一个 [K,7] chunk，逐帧送 `env.step`，
    一个 request 对应 R 个真实 20 Hz tick；R = replan 周期，默认取 checkpoint 的
    `n_action_steps`（本项目所有既有臂都是 K = R = 4），可用 `--replan-every R` 覆盖，
    只执行 chunk 的前 R 步、丢弃其余，然后重新推理。改 R 就是改控制器口径，
    结果必须按 R 分开报告，不能与默认口径的臂直接互比；
  - 归一化：preprocessor/postprocessor 从 checkpoint 目录加载，normalizer stats 来自
    训练时保存的 safetensors，不重新统计；
  - 裁剪：policy 输出先反归一化，再 clip 到 [-1,1] 送环境，clip 次数单独记账；
  - 真值：`success_raw` 取 env info，`grasp_verified` 取 `grasp_truth_fn`（robosuite
    `_check_grasp`），`success_rise` 用 `max_rise >= 0.04 m`；不启用 guard/recovery，
    harness 不出手，救场数为 0。
  - 门禁字段：每局额外输出 `final_rise / held_at_end / phase_at_end / terminal_kind`，
    供 `scripts/b_gate_controlled_success.py`（受控成功判据 v1）直接判定「受控抬起 vs 弹射」，
    不再退化成只看 `phase_trace` 的宽松判据。`terminal_kind` 取值
    `horizon_exhausted`（跑满 horizon，含 env 自身的 trunc 超时）/ `environment_done`（env term 真终止）/
    `preempted`（`--limit-requests` 冒烟截断，门禁按 v4 不变量移出分母）。
  - 逐帧动作日志：默认**关闭**。`--log-actions` 打开后每局多写两个字段
    `actions`（真正送进 `env.step` 的 clip 后 7 维动作，逐帧）与 `rise_trace`（逐帧方块相对
    初始高度的位移），用于分辨「闭环里根本没下抬起命令」与「下了命令但臂没抬起来」——
    开环审计（`scripts/audit_lerobot_act_lift_frames.py`）只能证明前者在 teacher 状态上成立。
    关掉时输出与历史产物逐字节同构（不新增任何 key），因此既有臂的对照不受影响。
  - 推理侧归一化输入截断：默认**关闭**。`--clip-norm-input C` 打开后，在 `pre()` 归一化之后、
    送进 `predict_action_chunk` 之前，把两个 obs 特征的归一化值逐维截到 ±C。
    **这是因果探针，不是修复、更不是交付能力**（`docs/b_normalization_incident_20260928.md` §6.4、
    监管备忘 2026-09-28 增补二 §1：「截断永久只作因果探针，不得作修复或交付能力」）。
    它回答的唯一问题是「L1 数值炸穿对这个 checkpoint 的闭环行为有没有因果作用」。
    打开时产物会写 `execution_constraints.norm_input_clip`，门禁据此判 `composite_policy=true`；
    同时**额外**记录截断前的越界比例（`norm_input_preclip_blown_frames_frac`），
    以免「截断后 0% 越界」把违例本身藏掉。关闭时输出与既有产物逐字节同构。

用法：
    /root/venvs/lerobot_eval/bin/python scripts/eval_lerobot_act_runtime.py \
        --ckpt runs/infra/lerobot_act_lift_v30/train24_lr1e-4_s20k \
        --episodes 20 --seed0 5000 --horizon 300 \
        --out runs/infra/lerobot_act_env_20260928/official_act_truth20.json
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.env_factory import (  # noqa: E402
    PINNED_OBJECT_SEED,
    contact_object_geom,
    make_contact_env,
    reset_contact,
)
from scripts.probe_contact_ceiling import grasp_truth_fn  # noqa: E402

STATE_DIM = 50
ENV_DIM = 10
ACTION_DIM = 7
RISE_THRESHOLD = 0.04

from scripts._lerobot_act import load_official_act, resolve_pretrained_dir, sha256_file  # noqa: E402


NORM_FEATURES = (("observation.state", STATE_DIM), ("observation.environment_state", ENV_DIM))


def load_norm_input_contract(pm_dir: Path, cfg) -> dict:
    """从 checkpoint 的 normalizer stats 反推「训练期归一化输入范围」，用于输入契约检查。

    为什么需要它（监管备忘 2026-09-28 增补二 §3、`docs/b_normalization_incident_20260928.md`）：
    MEAN_STD 归一化是 `(x - mean) / (std + eps)`，对**近常量维没有下限保护**。Lift 的 state obs 里
    `joint_vel` / `joint_acc` 系的 std 低至 1e-2 量级（未裁剪数据上 `joint_pos_cos` 系甚至 9.7e-05），
    闭环一旦偏离 teacher 轨迹，这些维会被放大到 10^1~10^4 喂进网络，第一层激活炸穿、输出饱和成 ±1。
    **开环指标完全看不到这件事**，所以必须把「有多少帧的归一化输入超出训练期见过的范围」写进产物。

    口径与 B 线 `scripts/b_eval_act_lift_v1.py --record-input-blowup` 对齐：
       blown 帧 = 该帧归一化输入的 `max_dim |x|` 超过**全局阈值**
      全局阈值 = 所有维里训练期归一化后 |x| 的最大值（B 在未裁剪导出上实测 23.7，
                 本函数按每个 checkpoint 自己的 stats 现算，不写死）
    另附一个更严的 per-dim 口径（任一维超出**它自己**的训练范围）作为诊断，不参与门禁。
    """
    from safetensors.torch import load_file

    cand = sorted(Path(pm_dir).glob("policy_preprocessor_step_*_normalizer_processor.safetensors"))
    if not cand:
        raise SystemExit(f"[错误] {pm_dir} 下找不到 normalizer stats，无法做输入契约检查")
    stats = load_file(cand[-1])

    modes = {}
    for key, val in dict(cfg.normalization_mapping).items():
        modes[str(key).split(".")[-1].upper()] = str(val).split(".")[-1].upper()
    feat_mode = {"observation.state": modes.get("STATE", "MEAN_STD"),
                 "observation.environment_state": modes.get("ENV", "MEAN_STD")}

    per_dim, stds, detail = [], [], []
    for name, dim in NORM_FEATURES:
        mean = stats[f"{name}.mean"].numpy().astype(np.float64)
        std = stats[f"{name}.std"].numpy().astype(np.float64)
        lo_raw = stats[f"{name}.min"].numpy().astype(np.float64)
        hi_raw = stats[f"{name}.max"].numpy().astype(np.float64)
        mode = feat_mode[name]
        if mode == "MIN_MAX":
            span = np.where((hi_raw - lo_raw) == 0, 1.0, hi_raw - lo_raw)
            lo, hi = -1.0 * np.ones(dim), 1.0 * np.ones(dim)
            _ = span
        elif mode == "MEAN_STD":
            denom = np.maximum(std, 1e-12)
            lo, hi = (lo_raw - mean) / denom, (hi_raw - mean) / denom
        else:  # IDENTITY / BINARY：不归一化，范围就是原始范围
            lo, hi = lo_raw, hi_raw
        absmax = np.maximum(np.abs(lo), np.abs(hi))
        per_dim.append(absmax)
        stds.append(std)
        for j in np.argsort(-absmax)[:5]:
            detail.append({"feature": name, "dim_in_feature": int(j),
                           "global_dim": int(j) + (0 if name == "observation.state" else STATE_DIM),
                           "std": float(std[j]), "norm_absmax": float(absmax[j]), "mode": mode})
    per_dim_absmax = np.concatenate(per_dim)
    std_all = np.concatenate(stds)
    return {
        "per_dim_absmax": per_dim_absmax,
        "std": std_all,
        "blowup_threshold": float(per_dim_absmax.max()),
        "feature_modes": feat_mode,
        "top_dims": detail,
        "stats_file": str(cand[-1].name),
        "min_std_dim": int(np.argmin(std_all)),
        "min_std": float(std_all.min()),
    }


def normalized_input_vector(batch, contract) -> np.ndarray | None:
    """从 preprocessor 输出里取出真正喂给 policy 的归一化输入，拼成 60 维（state 前 50 + env 后 10）。"""
    parts = []
    for name, dim in NORM_FEATURES:
        if name not in batch:
            return None
        arr = batch[name]
        arr = arr.detach().cpu().numpy() if hasattr(arr, "detach") else np.asarray(arr)
        arr = np.asarray(arr, dtype=np.float64).reshape(-1)
        if arr.size != dim:
            return None
        parts.append(arr)
    return np.concatenate(parts) if parts else None


def blown_frame_stats(vec, contract) -> dict:
    """**单一来源**的 blown 帧判定：plain 路径与 clip 探针路径共用本函数（监管 增补三 §12 分派）。

    为什么必须有这个函数：D 线在核验截断探针时发现，同一 checkpoint / 同一题集下
    未截断产物的 `norm_input_blown_frames_frac`（0.2120）与探针产物的
    `norm_input_preclip_blown_frames_frac`（0.1180）不相等，怀疑「分母或参与维不一致」。
    实测结论是**两者不是同一条闭环轨迹**（20 局里 6 局 `phase_trace` 从第 48–138 帧起分岔，
    见 `runs/infra/lerobot_act_env_20260928/blown_metric_reconcile.json`），
    计算本身已经同源；但为了让这件事**可自证**，判定逻辑收敛到这一个函数，
    并把它的源码指纹写进产物（`input_contract.blown_metric_impl`），
    使任何一份裁定都能回答「这个 blown 数字是哪套实现、在哪条轨迹上算出来的」。

    口径（与 `load_norm_input_contract` 的 threshold_semantics 一致，不得在此另立判据）：
      blown 帧 = 该帧归一化输入的 `max_dim |x|` 超过**全局阈值**（该 ckpt 训练期归一化 |x| 最大值）
      oor   帧 = 任一维超出**它自己**的训练范围（诊断字段，按监管 增补三 §5 不进判据）
    """
    av = np.abs(np.asarray(vec, dtype=np.float64).reshape(-1))
    frame_max = float(av.max())
    return {
        "frame_max": frame_max,
        "blown": frame_max > contract["blowup_threshold"],
        "top_dim": int(av.argmax()),
        "oor": bool(np.any(av > contract["per_dim_absmax"] + 1e-9)),
    }


def _src_sha12(*funcs) -> str:
    import hashlib
    import inspect
    src = "".join(inspect.getsource(f) for f in funcs)
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]


# blown 指标的实现指纹：改动 blown_frame_stats / normalized_input_vector 任一行，这个值就变，
# 于是「同一数字出自不同实现」不可能再悄悄发生（B 侧按 增补三 §12 把它写进裁定 JSON）。
BLOWN_METRIC_IMPL = _src_sha12(normalized_input_vector, blown_frame_stats)


def phase(raw, z0: float, step: int) -> str:
    """与 eval_act_lift_truth.py 完全一致的相位标签。"""
    z = float(raw["cube_pos"][2])
    e = np.asarray(raw["robot0_eef_pos"])
    c = np.asarray(raw["cube_pos"])
    w = float(np.max(np.abs(raw["robot0_gripper_qpos"])))
    if z > z0 + RISE_THRESHOLD:
        return "hold"
    if w > 0.012:
        return "grasp"
    if abs(e[2] - c[2]) < 0.035:
        return "descend"
    return "approach"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="run 目录 / checkpoint 目录 / pretrained_model 目录")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    ap.add_argument("--limit-requests", type=int, default=None, help="冒烟用：每局最多几次 request")
    ap.add_argument("--replan-every", type=int, default=None, metavar="R",
                    help="闭环每 R 步重新推理一次并只执行 chunk 的前 R 步（默认 = checkpoint 的 "
                         "n_action_steps）。改这个值就是改控制器口径，结果必须按 R 分别报告；"
                         "口径先例见 scripts/eval_act_replan_frequency.py --replan-every 1,2,4")
    ap.add_argument("--log-actions", action="store_true",
                    help="每局额外记录逐帧 clip 后动作 actions 与 rise_trace（默认关闭；"
                         "关闭时输出与既有产物同构，不加任何 key）")
    ap.add_argument("--clip-norm-input", type=float, default=None, metavar="C",
                    help="因果探针：把归一化后的策略输入逐维截到 ±C（默认关闭 = 不截断）。"
                         "打开即构成复合 policy，产物写 execution_constraints.norm_input_clip，"
                         "结果只能用于「L1 是否因果咬合」的判定，不得作为能力数字对外引用。"
                         "口径对齐 B 线 scripts/b_eval_act_lift_v1.py --clip-norm-input。")
    ap.add_argument("--no-record-input-blowup", dest="record_input_blowup", action="store_false",
                    help="关闭策略输入契约记录（默认开启）。开启时每局写 "
                         "norm_input_blown_frames_frac / norm_input_absmax / norm_input_top_dim / "
                         "norm_input_out_of_range_frames_frac；门禁 "
                         "scripts/b_gate_controlled_success.py 用 INPUT_BLOWUP_TOL=0.05 判 "
                         "measurement_invalid（测量无效 ≠ 策略失败）。监管备忘 2026-09-28 增补二 §3 "
                         "要求任何闭环产物都带这个字段，缺字段同样判 INVALID。")
    ap.set_defaults(record_input_blowup=True)
    args = ap.parse_args()

    pm_dir = resolve_pretrained_dir(args.ckpt)
    torch, cfg, policy, pre, post, pm_dir = load_official_act(pm_dir, device=args.device)

    import lerobot

    k = int(cfg.n_action_steps)
    replan = k if args.replan_every is None else int(args.replan_every)
    if not 1 <= replan <= int(cfg.chunk_size):
        raise SystemExit(f"[错误] --replan-every={replan} 必须在 [1, chunk_size={cfg.chunk_size}] 内")
    contract = load_norm_input_contract(pm_dir, cfg) if args.record_input_blowup else None
    clip_c = args.clip_norm_input
    if clip_c is not None and clip_c <= 0:
        raise SystemExit(f"[错误] --clip-norm-input 必须是正数，收到 {clip_c}")
    print(f"checkpoint : {pm_dir}")
    print(f"lerobot {lerobot.__version__}  torch {torch.__version__}  device {cfg.device}")
    print(f"chunk_size={cfg.chunk_size} n_action_steps={k} temporal_ensemble={cfg.temporal_ensemble_coeff}")
    if contract is not None:
        print(f"输入契约: 阈值={contract['blowup_threshold']:.3f}（该 ckpt 训练期归一化 |x| 最大值）"
              f" 最小 std={contract['min_std']:.3e}@dim{contract['min_std_dim']}"
              f" modes={contract['feature_modes']}")
    if clip_c is not None:
        thr = contract["blowup_threshold"] if contract is not None else None
        print(f"[因果探针] 归一化输入逐维截断 ±{clip_c}"
              + (f"（该 ckpt 训练期上界 {thr:.3f}）" if thr is not None else "")
              + " —— 复合 policy，结果不得作为能力数字")

    env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    rows = []
    try:
        for i in range(args.episodes):
            seed = args.seed0 + i
            obs = reset_contact(env, seed)
            raw = env._env._get_observations()
            z0 = float(raw["cube_pos"][2])
            truth = grasp_truth_fn(env, "lift")
            policy.reset()

            raw_success = held = False
            max_rise = 0.0
            final_rise = 0.0
            held_at_end = False
            limit_break = False
            frames = 0
            requests = 0
            chunks = []
            phases = []
            acts: list = []
            rises: list = []
            n_meas = 0
            n_blown = 0
            n_oor = 0
            input_absmax = 0.0
            blown_dims: dict = {}
            events = {"partial": 0, "cancel": 0, "deadline": 0, "clip": 0}
            max_preclip_abs = 0.0
            preclip_n = 0
            preclip_blown = 0
            preclip_absmax = 0.0
            n_clamped_frames = 0
            first_clamped_frame = None
            started = time.perf_counter()
            term = trunc = False

            while frames < args.horizon:
                state = np.asarray(obs, dtype=np.float32).reshape(-1)
                if state.size != STATE_DIM + ENV_DIM:
                    raise SystemExit(f"[错误] 环境观测 {state.size} 维，与 50+10 切分不符")
                batch = pre(
                    {
                        "observation.state": torch.from_numpy(state[:STATE_DIM]),
                        "observation.environment_state": torch.from_numpy(state[STATE_DIM:]),
                    }
                )
                if clip_c is not None:
                    # 先按未截断的归一化值记账（否则「截断后 0% 越界」会把违例藏掉），再逐维截断。
                    # 截断发生在 pre() 之后、predict_action_chunk 之前：已实测 pre() 的输出就是
                    # 真正喂给网络的归一化输入（与手算 (x-mean)/(std+1e-8) 差 4.7e-05 = float32 舍入），
                    # 且 predict_action_chunk 不会再改写 batch，所以在这里截断等价于 B 线的
                    # --clip-norm-input，无需改动 lerobot 内部。
                    if contract is not None:
                        pvec = normalized_input_vector(batch, contract)
                        if pvec is not None:
                            preclip_n += 1
                            pst = blown_frame_stats(pvec, contract)
                            preclip_absmax = max(preclip_absmax, pst["frame_max"])
                            if pst["blown"]:
                                preclip_blown += 1
                            if pst["frame_max"] > clip_c:
                                n_clamped_frames += 1
                                if first_clamped_frame is None:
                                    first_clamped_frame = preclip_n - 1
                    for key in ("observation.state", "observation.environment_state"):
                        if torch.is_tensor(batch.get(key)):
                            batch[key] = torch.clamp(batch[key], -clip_c, clip_c)
                with torch.no_grad():
                    pred = post(policy.predict_action_chunk(batch))
                if contract is not None:
                    vec = normalized_input_vector(batch, contract)
                    if vec is not None:
                        n_meas += 1
                        st = blown_frame_stats(vec, contract)
                        frame_max = st["frame_max"]
                        input_absmax = max(input_absmax, frame_max)
                        if st["blown"]:
                            n_blown += 1
                            blown_dims[st["top_dim"]] = blown_dims.get(st["top_dim"], 0) + 1
                        if st["oor"]:
                            n_oor += 1
                pred = np.asarray(pred.detach().cpu().numpy(), dtype=np.float32).reshape(-1, ACTION_DIM)

                # 只执行前 n_action_steps 步（官方 ACT 用法）：chunk_size > n_action_steps 时
                # 丢弃本 chunk 剩余动作、下一 tick 重新请求，使闭环重规划频率恒等于
                # n_action_steps。既有全部臂都是 chunk_size == n_action_steps == 4，
                # 因此本行对它们是恒等变换（已用重评逐局比对验证）。
                n_plan = min(replan, len(pred))
                n = min(n_plan, args.horizon - frames)
                if args.limit_requests is not None and requests >= args.limit_requests:
                    limit_break = True
                    break
                mask = []
                for j in range(n):
                    a_raw = pred[j]
                    max_preclip_abs = max(max_preclip_abs, float(np.max(np.abs(a_raw))))
                    a = np.clip(a_raw, -1.0, 1.0).astype(np.float32)
                    if not np.array_equal(a, a_raw):
                        events["clip"] += 1
                    obs, _, term, trunc, info = env.step(a)
                    raw = env._env._get_observations()
                    frames += 1
                    mask.append(True)
                    raw_success = raw_success or bool(info.get("success", False))
                    held_now = bool(truth())
                    held = held or held_now
                    held_at_end = held_now
                    rise = float(raw["cube_pos"][2]) - z0
                    max_rise = max(max_rise, rise)
                    final_rise = rise
                    phases.append(phase(raw, z0, frames))
                    if args.log_actions:
                        acts.append([round(float(x), 5) for x in a])
                        rises.append(round(rise, 6))
                    if term or trunc:
                        events["cancel"] += 1
                        break
                if n < n_plan:
                    events["partial"] += 1
                chunks.append(
                    {
                        "request_id": requests,
                        "frame": int(frames - len(mask)),
                        "chunk_length": int(n),
                        "planned_chunk_length": int(len(pred)),
                        "executed_of_chunk": int(n),
                        "actual_activation_mask": mask,
                        "phase": phases[-1] if phases else "",
                        "td_eligible": False,
                        "bc_eligible": False,
                    }
                )
                requests += 1
                if term or trunc:
                    break

            rows.append(
                {
                    "seed": seed,
                    "success_raw": raw_success,
                    "grasp_verified": held,
                    "success_grasp_verified": bool(raw_success and held),
                    "success_rise": bool(max_rise >= RISE_THRESHOLD),
                    "max_rise": round(max_rise, 8),
                    # ---- 受控成功门禁字段（契约见 scripts/b_gate_controlled_success.py，
                    #      语义对齐 scripts/probe_contact_ceiling.py::run_one）----
                    "final_rise": round(final_rise, 8),
                    "held_at_end": held_at_end,
                    "phase_at_end": phases[-1] if phases else "",
                    "terminal_kind": ("preempted" if limit_break else
                                      "environment_done" if term else "horizon_exhausted"),
                    "failure_phase": "" if raw_success else (phases[-1] if phases else "unknown"),
                    "steps": frames,
                    "chunk_count": requests,
                    "actual_activation_frames": sum(len(c["actual_activation_mask"]) for c in chunks),
                    "partial_events": events["partial"],
                    "cancel_events": events["cancel"],
                    "deadline_events": events["deadline"],
                    "clip_events": events["clip"],
                    "max_preclip_abs_action": round(max_preclip_abs, 6),
                    "elapsed_sec": round(time.perf_counter() - started, 3),
                    "guard_interventions": 0,
                    "recovery_events": 0,
                    "phase_trace": phases,
                    "chunks": chunks,
                }
            )
            if args.log_actions:
                rows[-1]["actions"] = acts
                rows[-1]["rise_trace"] = rises
            if contract is not None:
                # 输入契约字段。名称与 B 线 scripts/b_eval_act_lift_v1.py 完全一致，
                # 门禁 scripts/b_gate_controlled_success.py 直接按这个名字读。
                rows[-1]["norm_input_frames_measured"] = n_meas
                rows[-1]["norm_input_blown_frames_frac"] = (round(n_blown / n_meas, 6) if n_meas else None)
                rows[-1]["norm_input_out_of_range_frames_frac"] = (round(n_oor / n_meas, 6) if n_meas else None)
                rows[-1]["norm_input_absmax"] = round(input_absmax, 4)
                rows[-1]["norm_input_top_dim"] = (max(blown_dims, key=blown_dims.get) if blown_dims else None)
                rows[-1]["norm_input_blown_dims"] = {str(kk): vv for kk, vv in
                                                     sorted(blown_dims.items(), key=lambda x: -x[1])[:8]}
                if clip_c is not None:
                    rows[-1]["norm_input_preclip_blown_frames_frac"] = (
                        round(preclip_blown / preclip_n, 6) if preclip_n else None)
                    rows[-1]["norm_input_preclip_absmax"] = round(preclip_absmax, 4)
                    rows[-1]["norm_input_clamped_frames"] = n_clamped_frames
                    rows[-1]["norm_input_first_clamped_frame"] = first_clamped_frame
            print(
                f"  seed {seed}: raw={int(raw_success)} grasp={int(held)} "
                f"rise={max_rise:.4f} final_rise={final_rise:.4f} "
                f"held_end={int(held_at_end)} term={rows[-1]['terminal_kind']} "
                f"fail={rows[-1]['failure_phase'] or '-'} "
                f"req={requests} frames={frames} clip={events['clip']}"
            )
        geom = contact_object_geom(env, "lift", PINNED_OBJECT_SEED)
    finally:
        env.close()

    n = len(rows)
    result = {
        "controller": "official_lerobot_act",
        "claim": "closed_loop_sim_truth",
        "not_a_claim": ["不是真机结果", "不含 guard/recovery，救场数为 0"],
        "task": "lift",
        "episodes": n,
        "seed0": args.seed0,
        "horizon": args.horizon,
        "chunk_size": int(cfg.chunk_size),
        "n_action_steps": k,
        "replan_every": replan,
        "replan_every_note": ("等于 checkpoint 的 n_action_steps（默认口径）" if args.replan_every is None
                              else f"由 --replan-every 覆盖为 {replan}，与默认口径的臂不可直接互比"),
        "log_actions": bool(args.log_actions),
        "temporal_ensemble_coeff": cfg.temporal_ensemble_coeff,
        "input_contract": (None if contract is None else {
            "recorded": True,
            # 实现指纹（监管 增补三 §12 分派）：blown 判定的**单一来源**是
            # blown_frame_stats() + normalized_input_vector()，两者的源码哈希落在这里。
            # 这是本评测器唯一在「开/关截断」两种模式下都写的新增键（schema 追加，
            # 不改任何既有字段的语义与数值），B 的门禁可据此把 blown_metric_impl 写进裁定 JSON。
            "blown_metric_impl": BLOWN_METRIC_IMPL,
            "blown_metric_source": "scripts/eval_lerobot_act_runtime.py::blown_frame_stats + ::normalized_input_vector",
            "blowup_threshold": round(contract["blowup_threshold"], 6),
            "threshold_semantics": ("该 checkpoint 训练期归一化输入 |x| 的最大值（按 ckpt 自己的 "
                                    "normalizer stats 现算）；某帧 max_dim|x| 超过它即记为 blown 帧。"
                                    "与 B 线 scripts/b_eval_act_lift_v1.py --record-input-blowup 同口径。"),
            "gate_tolerance": 0.05,
            "gate_rule": "mean(norm_input_blown_frames_frac) > 0.05 -> measurement_invalid（测量无效，不是策略失败）",
            "feature_modes": contract["feature_modes"],
            "stats_file": contract["stats_file"],
            "min_std": contract["min_std"],
            "min_std_dim": contract["min_std_dim"],
            "top_training_range_dims": contract["top_dims"],
            "mean_blown_frames_frac": (round(float(np.mean([r["norm_input_blown_frames_frac"] for r in rows
                                                            if r.get("norm_input_blown_frames_frac") is not None])), 6)
                                       if rows else None),
            "max_input_absmax": round(max([r["norm_input_absmax"] for r in rows]), 4) if rows else None,
            "mean_out_of_range_frames_frac": (round(float(np.mean([r["norm_input_out_of_range_frames_frac"] for r in rows
                                                                  if r.get("norm_input_out_of_range_frames_frac") is not None])), 6)
                                              if rows else None),
        }),
        "pinned_object_seed": PINNED_OBJECT_SEED,
        "object_geom": geom,
        "observation_key_map": {
            "env_state_vector[0:50]": "observation.state (robot0_proprio-state)",
            "env_state_vector[50:60]": "observation.environment_state (object-state)",
        },
        "normalizer_source": "checkpoint policy_preprocessor_step_*_normalizer_processor.safetensors",
        "versions": {
            "lerobot": lerobot.__version__,
            "torch": torch.__version__,
            "python": platform.python_version(),
            "device": str(cfg.device),
        },
        "checkpoint": {
            "pretrained_model_dir": str(pm_dir.resolve()),
            "model_safetensors_sha256": sha256_file(pm_dir / "model.safetensors"),
        },
        "policy_config": {
            "type": cfg.type,
            "chunk_size": int(cfg.chunk_size),
            "n_action_steps": k,
            "temporal_ensemble_coeff": cfg.temporal_ensemble_coeff,
            "use_vae": bool(cfg.use_vae),
            "kl_weight": float(cfg.kl_weight),
            "dim_model": int(cfg.dim_model),
            "normalization_mapping": {str(kk): str(vv) for kk, vv in cfg.normalization_mapping.items()},
            "input_features": {kk: {"type": str(vv.type), "shape": list(vv.shape)} for kk, vv in cfg.input_features.items()},
            "output_features": {kk: {"type": str(vv.type), "shape": list(vv.shape)} for kk, vv in cfg.output_features.items()},
            "optimizer_lr": float(cfg.optimizer_lr),
        },
        "success_raw": sum(r["success_raw"] for r in rows),
        "grasp_verified": sum(r["grasp_verified"] for r in rows),
        "success_grasp_verified": sum(r["success_grasp_verified"] for r in rows),
        "success_rise": sum(r["success_rise"] for r in rows),
        "mean_max_rise": float(np.mean([r["max_rise"] for r in rows])) if rows else 0.0,
        "mean_final_rise": float(np.mean([r["final_rise"] for r in rows])) if rows else 0.0,
        "held_at_end_count": sum(bool(r["held_at_end"]) for r in rows),
        "terminal_kind_counts": {
            t: sum(1 for r in rows if r["terminal_kind"] == t)
            for t in sorted({r["terminal_kind"] for r in rows})
        },
        "total_clip_events": sum(r["clip_events"] for r in rows),
        "failure_phase_counts": {
            p: sum(1 for r in rows if r["failure_phase"] == p)
            for p in sorted({r["failure_phase"] for r in rows if r["failure_phase"]})
        },
        "total_partial_events": sum(r["partial_events"] for r in rows),
        "total_cancel_events": sum(r["cancel_events"] for r in rows),
        "rows": rows,
    }
    if clip_c is not None:
        # 门禁 scripts/b_gate_controlled_success.py:234 读 execution_constraints 决定 composite_policy
        # （非 None 的值 -> active_constraints 非空 -> composite_policy=true）。
        # 关闭截断时**不新增任何 clip 相关 key**（execution_constraints 与 input_contract.clip_probe
        # 都不写），保证默认路径的产物与既有臂同构；唯一例外是 `input_contract.blown_metric_impl`
        # 实现指纹（增补三 §12），它是 schema 追加、不改任何既有字段，回归比对时按「新增键」放行。
        result["execution_constraints"] = {"norm_input_clip": clip_c}
        if result.get("input_contract") is not None:
            result["input_contract"]["clip_probe"] = {
                "enabled": True,
                "C": clip_c,
                "applied_to": ["observation.state", "observation.environment_state"],
                "stage": "pre() 归一化之后、predict_action_chunk 之前（推理侧，未改 lerobot 内部）",
                "is_a_fix": False,
                "note": ("因果探针，不是修复也不是交付能力（b_normalization_incident_20260928.md §6.4、"
                         "监管备忘 增补二 §1）。用于判定 L1 数值炸穿对该 checkpoint 的闭环行为"
                         "是否有因果作用。截断后的 blown_frames_frac 按构造为 0，"
                         "真实违例程度看 mean_preclip_blown_frames_frac。"),
                "mean_preclip_blown_frames_frac": (
                    round(float(np.mean([r["norm_input_preclip_blown_frames_frac"] for r in rows
                                         if r.get("norm_input_preclip_blown_frames_frac") is not None])), 6)
                    if rows else None),
                "max_preclip_input_absmax": (round(max([r["norm_input_preclip_absmax"] for r in rows]), 4)
                                             if rows else None),
                # 轨迹归属声明（增补三 §12 的直接产物）：preclip 系列字段算的是**本次这条被截断的
                # 闭环轨迹**，与未截断臂的同名字段**不是同一条轨迹**，不得逐局对齐相减。
                # 实测 k2 seed0 @C=12.469445：20 局里 6 局 phase_trace 自第 48–138 帧起分岔，
                # 14 局 |x| 从未超过 C（截断为恒等变换）→ 两局集合的 blown 计数天然不等。
                "trajectory_note": ("preclip/blown 字段属于本次（被截断的）闭环轨迹；与未截断产物"
                                    "的同名字段不是同一轨迹，不可逐局对齐。分岔证据见 "
                                    "runs/infra/lerobot_act_env_20260928/blown_metric_reconcile.json"),
                "n_episodes_input_clamped": sum(1 for r in rows if (r.get("norm_input_clamped_frames") or 0) > 0),
                "total_clamped_frames": sum(int(r.get("norm_input_clamped_frames") or 0) for r in rows),
                "first_clamped_frames": [r.get("norm_input_first_clamped_frame") for r in rows],
            }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {kk: result[kk] for kk in
             ("episodes", "success_raw", "grasp_verified", "success_grasp_verified",
              "success_rise", "mean_max_rise", "failure_phase_counts", "total_clip_events")},
            ensure_ascii=False, indent=2,
        )
    )
    print(f"写出: {out}")


if __name__ == "__main__":
    main()
