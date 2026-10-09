"""run7 的零训练配套探针：可达上限 + 「堆叠观测到底缺什么信息」的定量回答。

背景（为什么要这个脚本）
    run7 原本要跑 6 条 SAC 臂（fullstate×3 + stack3×3），机器负载 1300+ 时一条臂
    要 1.5~2 h，总共 ~11 h。其中 stack3 那三臂按 `configs/reach_stack3.yaml` 的
    注释是「预期失败的理论对照」。本脚本用**不训练**的方式把两个问题一次问清，
    于是 stack3 的三臂可以砍掉（结论用数学 + 实测支持度替代，见 docs/notes_stage3.md §6.12）：

    问题 A（可达上限）  reach_perturbed 上 SAC 60k 只到 0.68、手写 P 控制 0.94，
                        这个残差是「6 维观测信息不够」还是「SAC 没优化到位」？
                        -> 在 6 维 / 12 维(fullstate) 两种观测上分别跑三种手写控制器，
                           看成功率**和平均步数**。若 g=0.5 的朴素 P 控制在 6 维上就
                           已经 1.00，则「可达性」根本不是瓶颈，残差属于可学习性。

    问题 B（信息缺口）  朴素堆叠为什么修不好延迟？
                        -> 关键不是「位置历史不够长」，而是**在途指令是策略自己上一步
                           随机采样出来的动作**，它还没产生任何位移，所以任何位置历史
                           里都不含它。用「从 18 维堆叠观测回归在途指令」的 R² 直接量出来：
                           随机策略下 R²≈0（信息真的不在），确定性 P 策略下 R²≈1
                           （因为 a_{t-1}=π(o_{t-1})，而 o_{t-1} 就在堆叠里）。
                           这两个数一起说明：stack3 能不能修好延迟，取决于策略是否
                           确定性 —— SAC 是随机的，所以修不好。

用法：
    /root/venvs/rlrobot/bin/python scripts/probe_fullstate_ceiling.py
    （只吃 CPU 几秒钟，不训练、不写 registry、不改任何已有文件）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.env_factory import install_env_factory          # noqa: E402
from harness.trainer import load_train_config                # noqa: E402
from registry.publish import score_skill                     # noqa: E402
from skills.base import Skill, SkillMeta, compute_config_hash  # noqa: E402


# --------------------------------------------------------------------------
# 观测布局解析（必须显式算，不能靠维度猜）
#
# `envs/reach_perturbed.py::_obs()` 的拼法是：
#     [frame_{t-k+1} ... frame_t]  (6*obs_stack 维，最新帧在最后)
#     [zero_pad(3*(delay-1)), in_flight_cmd(3)]   (仅 expose_queue 时追加)
# 所以「最新帧」和「在途指令」的切片都由 obs_stack / action_delay 决定。
# 早先这里用 `flat[-6:]` 猜最新帧，在 stack3+queue(24 维) 上取到的是队列本身，
# 策略退化成 cmd_t = 0.9*cmd_{t-1} -> 几步后恒为 0，实测 y 方差为 0。已修。
# --------------------------------------------------------------------------
def obs_layout(env_kwargs: dict) -> dict:
    obs_stack = max(1, int(env_kwargs.get("obs_stack", 1)))
    delay = max(0, int(env_kwargs.get("action_delay", 2)))
    expose = bool(env_kwargs.get("expose_queue", False))
    frame_block = 6 * obs_stack
    start = frame_block - 6
    maxlen = max(1, delay)
    return {
        "obs_stack": obs_stack,
        "expose_queue": expose,
        "ee_goal": (start, start + 6),
        "in_flight_cmd": (frame_block + 3 * (maxlen - 1), frame_block + 3 * maxlen) if expose else None,
        "dim": frame_block + (3 * maxlen if expose else 0),
    }


def decode_ee_goal(obs: np.ndarray, half_space: float, lay: dict):
    flat = np.asarray(obs, dtype=np.float64).reshape(-1)
    a, b = lay["ee_goal"]
    base = flat[a:b]
    return base[:3] * half_space, base[3:6] * half_space


# --------------------------------------------------------------------------
# 问题 A：三种手写控制器
# --------------------------------------------------------------------------
class Proportional6D(Skill):
    """朴素比例控制（只看当前帧的 [ee, goal]）。6/12/18 维观测都能用。"""

    def __init__(self, half_space: float = 0.15, action_scale: float = 0.05,
                 gain: float = 1.0, layout: dict | None = None, version: str = "v1") -> None:
        self.half_space, self.action_scale, self.gain = half_space, action_scale, gain
        self.layout = layout or obs_layout({})
        self.meta = SkillMeta(
            name="probe_prop6d", version=version, kind="planner",
            source="scripts/probe_fullstate_ceiling.py::Proportional6D",
            trained_on="无需训练（人写公式）",
            config_hash=compute_config_hash({"gain": gain, "kind": "prop6d",
                                             "ee_goal": list(self.layout["ee_goal"])}),
            notes=f"朴素 P 控制 g={gain}，只用最新帧 {self.layout['ee_goal']}",
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        ee, goal = decode_ee_goal(obs, self.half_space, self.layout)
        return np.clip(self.gain * (goal - ee) / self.action_scale, -1.0, 1.0).astype(np.float32)


class QueueCompensated(Skill):
    """fullstate(12 维) 上的比例控制：先扣掉**在途指令**的预计位移，再算新指令。

    观测布局（`envs/reach_perturbed.py::_obs`，delay=2 => 队列 maxlen=2，零垫到定长）：
        flat[0:3]   ee / half_space
        flat[3:6]   goal / half_space
        flat[6:9]   零垫（reset 时队列满、step 后队列只剩 1 条，所以垫到定长）
        flat[9:12]  在途指令 q —— 下一步真正会被执行的那条
    一步预测：ee_next = ee + action_scale * (q * E[gain]) + drift * [-ee_y, ee_x, 0]
    （`E[gain]=1.0`，因为 gain ~ U[1-g, 1+g]；drift 项照抄环境里的折算方式。）
    """

    def __init__(self, half_space: float = 0.15, action_scale: float = 0.05,
                 gain: float = 1.0, drift: float = 0.004, mean_act_gain: float = 1.0,
                 layout: dict | None = None, version: str = "v1") -> None:
        self.half_space, self.action_scale = half_space, action_scale
        self.gain, self.drift, self.mean_act_gain = gain, drift, mean_act_gain
        self.layout = layout or obs_layout({"expose_queue": True, "action_delay": 2})
        if not self.layout["in_flight_cmd"]:
            raise ValueError("QueueCompensated 需要 expose_queue=True 的观测")
        self.meta = SkillMeta(
            name="probe_queue_compensated", version=version, kind="planner",
            source="scripts/probe_fullstate_ceiling.py::QueueCompensated",
            trained_on="无需训练（人写公式 + 已知在途指令）",
            config_hash=compute_config_hash({"gain": gain, "drift": drift,
                                             "mean_act_gain": mean_act_gain,
                                             "kind": "queue_compensated",
                                             "in_flight_cmd": list(self.layout["in_flight_cmd"])}),
            notes="用 fullstate 暴露的在途指令做一步预测补偿",
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        flat = np.asarray(obs, dtype=np.float64).reshape(-1)
        ee, goal = decode_ee_goal(obs, self.half_space, self.layout)
        qa, qb = self.layout["in_flight_cmd"]
        q = flat[qa:qb]
        drift_disp = self.drift * np.array([-ee[1], ee[0], 0.0])
        predicted = ee + self.action_scale * (q * self.mean_act_gain) + drift_disp
        return np.clip(self.gain * (goal - predicted) / self.action_scale,
                       -1.0, 1.0).astype(np.float32)


def run_achievability(configs: dict[str, Path], episodes: int, seed: int) -> list[dict]:
    rows: list[dict] = []
    for cfg_name, cfg_path in configs.items():
        cfg = load_train_config(cfg_path)
        install_env_factory(str(cfg.get("env_factory", "reach")))
        env_kwargs = dict(cfg.get("env") or {})
        half = float(env_kwargs.get("half_space", 0.15))
        scale = float(env_kwargs.get("action_scale", 0.05))
        drift = float(env_kwargs.get("drift", 0.0))
        lay = obs_layout(env_kwargs)
        skills: list[tuple[str, Skill]] = [
            ("朴素P g=1.0", Proportional6D(half, scale, gain=1.0, layout=lay)),
            ("朴素P g=0.5", Proportional6D(half, scale, gain=0.5, layout=lay)),
        ]
        if lay["in_flight_cmd"]:
            skills.append(("在途补偿P g=1.0",
                           QueueCompensated(half, scale, gain=1.0, drift=drift, layout=lay)))
            skills.append(("在途补偿P g=0.7",
                           QueueCompensated(half, scale, gain=0.7, drift=drift, layout=lay)))
        print(f"  [{cfg_name}] 观测 {lay['dim']} 维 · 最新帧 {lay['ee_goal']} · "
              f"在途指令 {lay['in_flight_cmd']}", flush=True)
        for skill_label, skill in skills:
            scores = score_skill(skill, env_kwargs, n_episodes=episodes, seed=seed, harsh=True)
            std, harsh = scores["standard"], scores["harsh"] or {}
            rows.append({
                "config": cfg_name,
                "obs_dim": lay["dim"],
                "obs_layout": {k: (list(v) if isinstance(v, tuple) else v)
                               for k, v in lay.items()},
                "controller": skill_label,
                "std_success": std["success_rate"],
                "std_mean_steps": std["mean_steps"],
                "std_final_dist": std["mean_final_dist"],
                "harsh_success": harsh.get("success_rate"),
                "harsh_mean_steps": harsh.get("mean_steps"),
                "harsh_probe": harsh.get("probe"),
            })
            print(f"  [{cfg_name:16s}] {skill_label:18s} "
                  f"标准 {std['success_rate']:.3f} / {std['mean_steps']:5.2f} 步 · "
                  f"严酷 {harsh.get('success_rate'):.3f} / {harsh.get('mean_steps'):5.2f} 步 · "
                  f"末距 {std['mean_final_dist']:.4f} m", flush=True)
    return rows


# --------------------------------------------------------------------------
# 问题 B：在途指令到底在不在堆叠观测里
# --------------------------------------------------------------------------
DET_GAIN = 0.3   # 确定性对照用的增益：故意不饱和。
                 # g=1.0 时 min_goal_dist=0.10 / action_scale=0.05 => 动作长期贴在 ±1，
                 # 在途指令 y 几乎没有方差，R² 分母为 0（实测就是 nan），对照失效。


def _collect(base_cfg: Path, policy_kind: str, episodes: int, max_steps: int,
             seed: int) -> tuple[np.ndarray, np.ndarray, dict]:
    """在 obs_stack=3 且 expose_queue=True 的环境上采数据。

    X = 前 18 维（SAC 在 stack3 档真正看到的观测）
    y = flat[21:24]（真值：下一步会被执行的在途指令）
    跳过每局前 2 步：那时堆叠还在用首帧零垫，不是真实的三帧历史。
    """
    cfg = load_train_config(base_cfg)
    install_env_factory(str(cfg.get("env_factory", "reach")))
    env_kwargs = dict(cfg.get("env") or {})
    env_kwargs["obs_stack"] = 3
    env_kwargs["expose_queue"] = True
    from envs.reach_perturbed import PerturbedReachEnv
    env = PerturbedReachEnv(**env_kwargs)
    lay = obs_layout(env_kwargs)
    assert lay["dim"] == 24 and lay["in_flight_cmd"] == (21, 24), f"布局异常: {lay}"
    half = float(env_kwargs.get("half_space", 0.15))
    scale = float(env_kwargs.get("action_scale", 0.05))
    rng = np.random.default_rng(seed)
    naive = Proportional6D(half, scale, gain=DET_GAIN, layout=lay)

    xs, ys, acts = [], [], []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed + ep)
        for t in range(max_steps):
            if policy_kind == "random":
                action = rng.uniform(-1.0, 1.0, size=3).astype(np.float32)
            else:
                action = naive.act(obs)
            flat = np.asarray(obs, dtype=np.float64).reshape(-1)
            if t >= 2:
                xs.append(flat[:18])                       # stack3 档 SAC 真正看到的
                ys.append(flat[lay["in_flight_cmd"][0]:lay["in_flight_cmd"][1]])
            acts.append(np.asarray(action, dtype=np.float64).reshape(3))
            obs, _r, term, trunc, _info = env.step(action)
            if term or trunc:
                break
    y = np.asarray(ys)
    a = np.asarray(acts)
    diag = {
        "y_std_per_axis": [round(float(v), 4) for v in y.std(axis=0)],
        "saturated_action_frac": round(float((np.abs(a) >= 0.999).mean()), 4),
    }
    return np.asarray(xs), y, diag


def _heldout_r2(x: np.ndarray, y: np.ndarray, ridge: float = 1e-6) -> dict:
    """带常数列的最小二乘 + 前后对半 train/test，返回诚实的 held-out R²。"""
    n = len(x)
    aug = np.concatenate([x, np.ones((n, 1))], axis=1)
    half = n // 2
    def fit(a, b):
        g = a.T @ a + ridge * np.eye(a.shape[1])
        return np.linalg.solve(g, a.T @ b)
    w = fit(aug[:half], y[:half])
    pred = aug[half:] @ w
    ss_res = float(((y[half:] - pred) ** 2).sum())
    ss_tot = float(((y[half:] - y[:half].mean(axis=0)) ** 2).sum())
    per_axis = []
    for j in range(y.shape[1]):
        r = float(((y[half:, j] - pred[:, j]) ** 2).sum())
        tt = float(((y[half:, j] - y[:half, j].mean()) ** 2).sum())
        per_axis.append(round(1.0 - r / tt, 4) if tt > 1e-12 else None)
    out = {"n_samples": n,
           "r2_overall": round(1.0 - ss_res / ss_tot, 4) if ss_tot > 1e-12 else None,
           "r2_per_axis": per_axis,
           "residual_rms_action_units": round(float(np.sqrt(((y[half:] - pred) ** 2).mean())), 4)}
    if out["r2_overall"] is None:
        out["note"] = "y 无方差（动作饱和），R² 不可定义 —— 该对照作废，见 DET_GAIN 注释"
    return out


def run_identifiability(base_cfg: Path, episodes: int, max_steps: int, seed: int,
                        action_scale: float, goal_radius: float) -> dict:
    out: dict = {"action_scale": action_scale, "goal_radius": goal_radius}
    print(f"  （每条策略采 {episodes} 局 × ≤{max_steps} 步，回归 18 维堆叠观测 -> 在途指令）", flush=True)
    for kind, label in (("random", "随机策略（模拟 SAC 的随机采样）"),
                        ("deterministic", f"确定性 P 策略 g={DET_GAIN}（a=π(o)，无采样噪声）")):
        x, y, diag = _collect(base_cfg, kind, episodes, max_steps, seed)
        r2 = {**_heldout_r2(x, y), **diag}
        resid_m = r2["residual_rms_action_units"] * action_scale
        r2["residual_rms_meters"] = round(resid_m, 5)
        r2["residual_vs_goal_radius"] = round(resid_m / goal_radius, 3) if goal_radius else None
        out[kind] = r2
        r2s = "  n/a" if r2["r2_overall"] is None else f"{r2['r2_overall']:+.4f}"
        print(f"  [{label}] R²={r2s} 逐轴={r2['r2_per_axis']} · "
              f"残差 {resid_m * 1000:.2f} mm = {r2['residual_vs_goal_radius']}× 成功圈 · "
              f"y标准差={r2['y_std_per_axis']} 动作饱和率={r2['saturated_action_frac']:.2f}", flush=True)
        if r2.get("note"):
            print(f"      ! {r2['note']}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", default="reach_perturbed,reach_fullstate")
    ap.add_argument("--episodes", type=int, default=50, help="可达上限评测局数（对齐 registry 门禁）")
    ap.add_argument("--seed", type=int, default=999, help="对齐 INDEP_EVAL_SEED")
    ap.add_argument("--ident-episodes", type=int, default=40)
    ap.add_argument("--ident-max-steps", type=int, default=50)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    names = [n.strip() for n in args.configs.split(",") if n.strip()]
    configs = {n: REPO_ROOT / "configs" / f"{n}.yaml" for n in names}
    missing = [str(p) for p in configs.values() if not p.exists()]
    if missing:
        print(f"[ERR] 配置不存在: {missing}", file=sys.stderr)
        return 2

    t0 = time.time()
    print("=" * 78)
    print("问题 A · 可达上限（零训练，评测口径 = registry 门禁：seed 999 / 50 局 / 标准+严酷）")
    print("=" * 78)
    ach = run_achievability(configs, args.episodes, args.seed)

    print("=" * 78)
    print("问题 B · 在途指令在不在堆叠观测里（18 维 -> 3 维回归的 held-out R²）")
    print("=" * 78)
    base_cfg = REPO_ROOT / "configs" / "reach_stack3.yaml"
    if not base_cfg.exists():
        base_cfg = REPO_ROOT / "configs" / "reach_perturbed.yaml"
    env_kwargs = dict(load_train_config(base_cfg).get("env") or {})
    ident = run_identifiability(base_cfg, args.ident_episodes, args.ident_max_steps, args.seed,
                                float(env_kwargs.get("action_scale", 0.05)),
                                float(env_kwargs.get("goal_radius", 0.02)))

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_sec": round(time.time() - t0, 2),
        "eval_protocol": {"n_episodes": args.episodes, "seed": args.seed, "harsh": True},
        "achievability": ach,
        "identifiability": ident,
    }
    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_fullstate_ceiling.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("-" * 78)
    print(f"已写出: {out}  ({result['elapsed_sec']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
