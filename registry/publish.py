"""发布门禁 + 只增不覆盖的版本库。

这是 `registry/README.md` 里那条「最小 CI」的实现：

    train.py -> eval.py(独立 seed + 严酷探针) -> 旧任务不掉点 -> 才写入这里

为什么门禁必须是**独立**的一步、而不是训练脚本自己报分？因为训练脚本看到的是
它自己采样出来的题；发布判定必须换成一批没参与训练的 seed，并且额外跑一次
「严酷探针」（收紧成功圈、砍掉步数上限）。默认 Reach 条件下随机策略就有 ~16%
成功率，只看「涨了」根本说明不了学到东西（见 `docs/notes_stage1.md`）。

两种指标都留：
    standard   默认条件下的成功率 —— 回答「这个版本能用吗」
    harsh      收紧条件下的成功率 —— 回答「它是真学会了还是刚好卡线」
只报 standard 会让「刚好压线的策略」蒙混过关；只报 harsh 会看不出整体可用性。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from skills.base import SkillMeta, ensure_dir, timestamp, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "registry"

# 严酷探针的**上限口径**：与 README/ROADMAP 里用的一致，改动它会让历史版本不可比。
HARSH_PROBE = {"max_steps": 50, "goal_radius": 0.02}
INDEP_EVAL_SEED = 999        # 刻意不同于训练 seed(0) 和评测 seed(12345)

# 接触任务的成功率有**两个口径**（§12.11-N，K11 硬前置之一）：
#   success_rate                  环境 `_check_success()`。它**不要求真抓住**：Lift 只看 cube
#                                 高度、PickPlace 只看 can 在篮内 + 末端退开。
#   success_rate_grasp_verified   再要求 `_check_grasp` 真值（两指 fingerpad 都接触到物体）。
# 实测（2026-09-23，Lift，钉死物体尺寸后）最弱那档 SAC 的两个"成功"局都是 16 步、
# 末端离物体 2.6 cm、全程没有抓取真值 —— 指间把 cube **弹起**越过阈值。那一档
# flick_frac = 0.500，用第一个口径当门禁指标，"弹一下"就能过门禁。
SUCCESS_RATE = "success_rate"
SUCCESS_RATE_GRASP = "success_rate_grasp_verified"
SUCCESS_KEYS = (SUCCESS_RATE, SUCCESS_RATE_GRASP)
# `flick_frac` 达到这个值就不许再拿未校验口径当门禁指标（与
# `scripts/probe_contact_ceiling.py::truth_consistency` 的 fail 档同一个阈值）。
FLICK_REJECT_ABOVE = 0.5

def harsh_probe_kwargs(env_kwargs: dict) -> dict:
    """根据当前环境算出实际探针口径：只许更严，不许更松。

    为什么不能直接用 HARSH_PROBE 覆盖？因为它是一组**绝对值**，是按默认 Reach
    （max_steps=100, goal_radius=0.03）标定出来的。换成 `configs/reach_perturbed.yaml`
    （max_steps=40）之后，`max_steps: 50` 反而把步数上限**放宽**了 —— 所谓「严酷探针」
    变成了更简单的题，两个口径的分数就完全不可比了。

    取 min(绝对上限, 当前环境的一半) 就同时满足两件事：
      · 默认 Reach 上结果与 HARSH_PROBE 完全一致（min(50, 50)=50, min(0.02, 0.03)=0.02），
        所以 `registry/reach_sac/v1` 那次的历史数字仍然有效；
      · 本来就更难的环境上，探针只会更严。
    """
    env_steps = int(env_kwargs.get("max_steps", 100))
    env_radius = float(env_kwargs.get("goal_radius", 0.03))
    return {
        "max_steps": max(5, min(int(HARSH_PROBE["max_steps"]), env_steps // 2 or env_steps)),
        "goal_radius": round(min(float(HARSH_PROBE["goal_radius"]), env_radius), 6),
    }


def score_skill(skill: Any, env_kwargs: dict, *, n_episodes: int = 50,
                seed: int = INDEP_EVAL_SEED, harsh: bool = True) -> dict:
    """给一个技能打分：标准条件 + 严酷探针。返回可直接进 result.json 的 dict。

    这里复用 `eval/reach_eval.evaluate_reach`（另一个模块，训练/评测解耦的那一份），
    不重新实现评测逻辑 —— 两处评测口径不一致是排障噩梦的开端。
    """
    from eval.reach_eval import evaluate_reach

    standard = evaluate_reach(skill, env_kwargs, n_episodes=n_episodes, seed=seed)
    # 逐局结果**必须留着**：发布判定的逐题配对（McNemar）只能从「同一批 seed 上两臂各自
    # 成没成」算出来。这里以前把 `episodes` 整个剥掉，于是 `loop.py::resolution_audit`
    # 的配对分支永远拿到 0 局、静默退化成「无法配对」—— 跑了这么多轮没人发现，
    # 因为配对当时只是 advisory 字段、不进日志也不影响判定（§7 第 26 条）。
    # 只留 seed/success 两个字段：够配对，又不会把 journal 撑大。
    def _outcomes(metrics: dict) -> list[dict]:
        return [{"seed": int(r["seed"]), "success": bool(r["success"])}
                for r in (metrics.get("episodes") or [])]

    std = {k: v for k, v in standard.items() if k != "episodes"}
    std["episode_outcomes"] = _outcomes(standard)
    out = {"n_episodes": n_episodes, "seed": seed, "standard": std, "harsh": None}
    if harsh:
        probe = harsh_probe_kwargs(env_kwargs)
        probe_kwargs = dict(env_kwargs)
        probe_kwargs.update(probe)
        metrics = evaluate_reach(skill, probe_kwargs, n_episodes=n_episodes, seed=seed)
        harsh_block = {k: v for k, v in metrics.items() if k != "episodes"}
        harsh_block["episode_outcomes"] = _outcomes(metrics)
        out["harsh"] = {**harsh_block, "probe": probe}
    return out


def summarize_scores(scores: dict) -> dict:
    """从完整打分里挑出门禁要看的那几个数，方便打印和比较。"""
    std = scores.get("standard") or {}
    harsh = scores.get("harsh") or {}
    return {
        "success_rate": std.get("success_rate"),
        "mean_steps": std.get("mean_steps"),
        "mean_final_dist": std.get("mean_final_dist"),
        "harsh_success_rate": harsh.get("success_rate"),
        "harsh_mean_final_dist": harsh.get("mean_final_dist"),
        # 接触任务的第二口径（reach 上没有，值为 None）：门禁可以按它判，
        # 配对也会跟着用它（见 contact_bundle_from_probe）。
        "success_rate_grasp_verified": std.get("success_rate_grasp_verified"),
        "harsh_success_rate_grasp_verified": harsh.get("success_rate_grasp_verified"),
        "flick_frac": std.get("flick_frac"),
    }


def contact_bundle_from_probe(rows: list[dict], *, success_key: str = SUCCESS_RATE,
                              label: str = "", harsh_rows: list[dict] | None = None) -> dict:
    """把接触探针的逐局记录打成 `decide` / `decide_paired` 能直接吃的 bundle。

    为什么需要它：接触任务的评测产物来自 `scripts/probe_contact_ceiling.py::run_one`
    （逐局真值：success / held / success_grasp / label），而门禁吃的是
    `{"success_rate":…, "episode_outcomes":[…]}` 这一套。中间这层转换必须**一次写对**，
    否则会出现「门禁判的是 A 口径、配对算的是 B 口径」——两者不一致时，
    三态门禁会给出看起来合理但完全错的方向。

    所以这里的关键约定是：`episode_outcomes[i]["success"]` **就是被判定口径的逐局真值**
    （`success_key=success_rate_grasp_verified` 时它取 `success_grasp`），
    这样 `loop.py::resolution_audit` 的 McNemar 配对自动与门禁同口径；
    两个口径的原始值都另外留着（`success_raw` / `success_grasp`）供事后审计。
    """
    if success_key not in SUCCESS_KEYS:
        raise ValueError(f"未知 success_key: {success_key!r}，可选 {SUCCESS_KEYS}")
    rows = list(rows or [])
    n = len(rows)
    if not n:
        return {"success_rate": None, SUCCESS_RATE_GRASP: None, "flick_frac": None,
                "n_episodes": 0, "episode_outcomes": [], "label": label,
                "success_key": success_key}
    n_raw = sum(1 for r in rows if r.get("success"))
    n_grasp = sum(1 for r in rows if r.get("success") and r.get("held"))
    flick = round((n_raw - n_grasp) / n_raw, 4) if n_raw else 0.0
    # 被判口径的逐局真值。`success_grasp` 是 run_one 自己算好的
    # （`success and held`），这里只兜底旧产物（缺该字段时现算）。
    def _grasp(r: dict) -> bool:
        return bool(r["success_grasp"]) if "success_grasp" in r \
            else bool(r.get("success") and r.get("held"))

    per_ep = _grasp if success_key == SUCCESS_RATE_GRASP else (lambda r: bool(r.get("success")))
    outcomes = [{"seed": int(r["seed"]), "success": per_ep(r),
                 "success_raw": bool(r.get("success")), "success_grasp": _grasp(r),
                 "held": bool(r.get("held")), "label": r.get("label")}
                for r in rows]
    out = {
        "success_rate": round(n_raw / n, 4),
        SUCCESS_RATE_GRASP: round(n_grasp / n, 4),
        "flick_frac": flick,
        "n_episodes": n,
        "success_key": success_key,
        "episode_outcomes": outcomes,
        "labels": {k: sum(1 for r in rows if r.get("label") == k)
                   for k in sorted({str(r.get("label")) for r in rows})},
        "label": label,
    }
    if harsh_rows:
        harsh = contact_bundle_from_probe(harsh_rows, success_key=success_key,
                                          label=f"{label}|harsh")
        out["harsh_success_rate"] = harsh["success_rate"]
        out["harsh_success_rate_grasp_verified"] = harsh[SUCCESS_RATE_GRASP]
        out["harsh_flick_frac"] = harsh["flick_frac"]
        out["harsh_episode_outcomes"] = harsh["episode_outcomes"]
    return out


def decide(
    candidate: dict,
    incumbent: dict | None,
    *,
    min_gain: float = 0.02,
    regression_tol: float = 0.0,
    min_success: float = 0.0,
    require_harsh_not_worse: bool = True,
    candidate_env_hash: str = "",
    incumbent_env_hash: str = "",
) -> tuple[bool, list[str]]:
    """门禁判定：返回 (是否发布, 人类可读的理由列表)。

    四条规则，缺一不可：
      0. 环境一致：候选与现任的 `env_hash` 必须相同。**不同环境下的分数根本不可比**，
         把它们放进同一条版本线，「不掉点」这条保证就完全失去意义
         （实测踩过：默认 Reach 的 1.0 和扰动 Reach 的 0.02 混进了同一个技能名）。
      1. 绝对下限：标准条件成功率 >= min_success（默认 0，即不设限）
      2. 不掉点：candidate >= incumbent - regression_tol（默认 tol=0，一点都不能掉）
      3. 有进步：candidate >= incumbent + min_gain，否则「换版本」没有意义，
         只会让 registry 里堆满统计噪声上下的版本

    第 3 条很容易被忽略，但它是防止「随机波动被当成进化」的关键：
    50 局评测的标准误约 ±7%，min_gain=0.02 只是下限，正式结论要多 seed 复评。
    """
    reasons: list[str] = []
    ok = True

    if candidate_env_hash and incumbent_env_hash and candidate_env_hash != incumbent_env_hash:
        return False, [
            f"环境不一致，分数不可比：候选 env_hash={candidate_env_hash} "
            f"!= 现任 env_hash={incumbent_env_hash}。"
            "换一个技能名，或确认是不是拿错环境的版本在比。",
        ]

    cand_rate = float(candidate.get("success_rate") or 0.0)
    cand_harsh = candidate.get("harsh_success_rate")

    if cand_rate < min_success:
        ok = False
        reasons.append(f"未达绝对下限: {cand_rate:.3f} < {min_success:.3f}")
    else:
        reasons.append(f"标准条件成功率 {cand_rate:.3f} >= 下限 {min_success:.3f}")

    if incumbent:
        inc_rate = float(incumbent.get("success_rate") or 0.0)
        if cand_rate < inc_rate - regression_tol:
            ok = False
            reasons.append(f"旧任务掉点: {cand_rate:.3f} < {inc_rate:.3f} - {regression_tol:.3f}")
        elif cand_rate < inc_rate + min_gain:
            ok = False
            reasons.append(
                f"进步不足: {cand_rate:.3f} < {inc_rate:.3f} + {min_gain:.3f}（可能是评测噪声，不发布）")
        else:
            reasons.append(f"比现任高 {cand_rate - inc_rate:+.3f}（>= min_gain {min_gain:.3f}）")

        if require_harsh_not_worse and cand_harsh is not None and incumbent.get("harsh_success_rate") is not None:
            inc_harsh = float(incumbent.get("harsh_success_rate") or 0.0)
            if float(cand_harsh) < inc_harsh - regression_tol:
                ok = False
                reasons.append(f"严酷探针掉点: {float(cand_harsh):.3f} < {inc_harsh:.3f}")
            else:
                reasons.append(f"严酷探针 {float(cand_harsh):.3f} >= 现任 {inc_harsh:.3f}")
    else:
        reasons.append("registry 里还没有现任版本，首次发布只需过绝对下限")

    return ok, reasons


# --------------------------------------------------------------------------------------
# 三态门禁（K12）。`decide()` 保持不变：历史 run 的数字是二态口径产出的，改它等于让
# registry 里已发布的版本线不可比。新口径走 `decide_paired()`，由 `harness/loop.py`
# 的 `gate_stats` 开关选择（默认 legacy）。
# --------------------------------------------------------------------------------------

GATE_STATS_LEGACY = "legacy"       # 二态：未配对比率 + min_gain / regression_tol
GATE_STATS_PAIRED = "paired_v1"    # 三态：配对显著性 + 幅度 + 分辨不出时 inconclusive
GATE_STATS_CHOICES = (GATE_STATS_LEGACY, GATE_STATS_PAIRED)
THREE_STATE_POLICY = ("three_state_v1: 显著且够大才 publish；显著掉点超容忍才 reject；"
                      "分辨不出一律 inconclusive（保留现任，且**不**判该方向失败）")


def decide_paired(
    candidate: dict,
    incumbent: dict | None,
    *,
    paired: dict | None = None,
    eval_episodes: int | None = None,
    min_gain: float = 0.02,
    regression_tol: float = 0.0,
    min_success: float = 0.0,
    require_harsh_not_worse: bool = True,
    candidate_env_hash: str = "",
    incumbent_env_hash: str = "",
    alpha: float = 0.05,
    success_key: str = SUCCESS_RATE,
    require_grasp_verified: bool = False,
) -> dict:
    """三态发布门禁：返回 `publish` / `reject` / `inconclusive` + 机器可读的方向与理由码。

    为什么要第三态（§12.11-G/L 实证）：二态门禁在 50 局评测（噪声地板 MDE≈0.22~0.28）上
    用 `min_gain=0.02` / `regression_tol=0` 判定，同一条臂上既出现过「+0.02、p=0.31 ⇒ 发布」，
    也出现过「0.98 vs 1.00、50 局只翻 1 局 ⇒ 判掉点拒绝」。两个方向都在量噪声，而日志上
    毫无异常。reach r5 vs r6 的配对复算把这件事钉死了：n=50 时 p=1.0（**分辨不出**），
    n=500 时 13:0、p=0.0002（差异是真的）—— 所以当时的正确输出不是"发布"也不是"掉点"，
    而是"测不出来，去买局数"。

    三态的**动作含义**必须分清，否则自进化会拿噪声当学习信号：
      · `publish`      换现任版本；
      · `reject`       能判定、且不发布（含硬失败 / 显著掉点超容忍 / 提升真实但不足 min_gain）；
      · `inconclusive` **测量分辨不出** ⇒ 下一步是加局数或改配对，不是判这个技能方向失败。
    所以「显著更好但只高 0.005」归 `reject`（`reason_code=real_gain_below_min_gain`、
    `direction=better`）而不是 `inconclusive`：那条不是测不准，是判定清楚了「不值得换版本」。
    `direction` 字段单独给出，避免把这种 reject 误读成「变差了」。

    显著性优先用**逐题配对**（McNemar 精确检验，`paired` 直接吃
    `loop.py::resolution_audit()` 里那份）；拿不到逐局记录时回退到未配对口径，
    并用 MDE 判「这个差分辨不分辨得出」—— 回退路径同样能产出 inconclusive，
    这正是二态门禁缺的那一态。

    接触任务的指标口径（K11 硬前置之二，§12.11-N）
    ----------------------------------------------
    `success_key` 决定**判哪个口径**，默认 `success_rate`（reach 历史行为逐字不变）。
    接触任务应当传 `success_rate_grasp_verified`；`require_grasp_verified=True` 时，
    bundle 里没有这个口径就**硬拒**（`missing_grasp_verified`），不许静默按 0.0 判。
    另外一条守卫：即使按未校验口径判，只要 `flick_frac >= FLICK_REJECT_ABOVE`
    （多数"成功"不是真抓起来的）也硬拒（`metric_flick_contaminated`）——
    这不是判技能好坏，是判**指标本身不可用**，所以走 hard 通道、direction=unknown。
    """
    from harness.sampling_design import min_detectable_effect

    if success_key not in SUCCESS_KEYS:
        raise ValueError(f"未知 success_key: {success_key!r}，可选 {SUCCESS_KEYS}")
    reasons: list[str] = []

    def out(decision: str, code: str, direction: str, significant: bool | None, **extra) -> dict:
        return {"decision": decision, "ok": decision == "publish", "reasons": reasons,
                "reason_code": code, "direction": direction, "significant": significant,
                "gate_stats": GATE_STATS_PAIRED, "policy": THREE_STATE_POLICY,
                "success_key": success_key, **extra}

    # 规则 0：环境不一致 ⇒ 分数根本不可比。这是"不能比"，不是"测不准"，所以硬 reject。
    if candidate_env_hash and incumbent_env_hash and candidate_env_hash != incumbent_env_hash:
        reasons.append(f"环境不一致，分数不可比：候选 env_hash={candidate_env_hash} "
                       f"!= 现任 env_hash={incumbent_env_hash}")
        return out("reject", "env_mismatch", "unknown", None, hard=True)

    # 规则 0b：指标口径本身不可用 ⇒ 后面所有比较都无意义，同样走 hard 通道。
    if require_grasp_verified and candidate.get(SUCCESS_RATE_GRASP) is None:
        reasons.append(f"require_grasp_verified=True 但候选 bundle 没有 {SUCCESS_RATE_GRASP}"
                       "（接触任务必须由 `contact_bundle_from_probe` / 探针的"
                       " `truth_consistency` 提供这一口径）")
        return out("reject", "missing_grasp_verified", "unknown", None, hard=True)
    if success_key != SUCCESS_RATE and candidate.get(success_key) is None:
        reasons.append(f"候选 bundle 缺 {success_key} ⇒ 不按 0.0 静默判，先补齐口径")
        return out("reject", "missing_metric", "unknown", None, hard=True)
    flick = candidate.get("flick_frac")
    if success_key == SUCCESS_RATE and flick is not None and float(flick) >= FLICK_REJECT_ABOVE:
        reasons.append(f"指标被「弹一下」污染：flick_frac={float(flick):.3f} >= "
                       f"{FLICK_REJECT_ABOVE:g} ⇒ 未校验成功率里多数不是真抓起来的，"
                       f"不能当门禁指标。改用 success_key={SUCCESS_RATE_GRASP}")
        return out("reject", "metric_flick_contaminated", "unknown", None, hard=True,
                   flick_frac=round(float(flick), 4))

    cand_rate = float(candidate.get(success_key) or 0.0)
    if cand_rate < min_success:
        reasons.append(f"未达绝对下限: {cand_rate:.3f} < {min_success:.3f}"
                       f"（口径 {success_key}）")
        return out("reject", "below_min_success", "unknown", None, hard=True)
    if min_success > 0:
        reasons.append(f"标准条件成功率 {cand_rate:.3f} >= 下限 {min_success:.3f}"
                       f"（口径 {success_key}）")

    if not incumbent:
        reasons.append("registry 里还没有现任版本，首次发布只需过绝对下限")
        return out("publish", "first_publish", "unknown", None, delta=None)

    if success_key != SUCCESS_RATE and incumbent.get(success_key) is None:
        reasons.append(f"现任 bundle 缺 {success_key} ⇒ 两边口径不一致，不可比")
        return out("reject", "missing_metric", "unknown", None, hard=True)
    inc_rate = float(incumbent.get(success_key) or 0.0)
    delta = round(cand_rate - inc_rate, 6)
    p_base = (cand_rate + inc_rate) / 2.0

    # ---- 显著性与方向：优先配对，缺逐局记录则按 MDE 回退 ------------------------------
    mc = (paired or {}).get("mcnemar") or {}
    n_pairs = (paired or {}).get("n_pairs")
    p_value = mc.get("exact_p")
    only_new = (paired or {}).get("only_new")
    only_inc = (paired or {}).get("only_inc")
    fallback = None
    mde = round(min_detectable_effect(int(eval_episodes), p_base, alpha=alpha), 4) \
        if eval_episodes else None
    if p_value is not None and n_pairs and only_new is not None and only_inc is not None:
        # 方向只看翻转题谁多，**不要**用 mcnemar 里的 only_a/only_b 字段名：
        # `paired_gate` 调 `mcnemar(only_new, only_inc)`，那两个名字在那边是反的。
        significant = bool(p_value < alpha and only_new != only_inc)
        direction = ("flat" if not significant else
                     ("better" if only_new > only_inc else "worse"))
        basis = (f"配对 McNemar（n={n_pairs} 对，翻转 只候选成 {only_new} : 只现任成 {only_inc}，"
                 f"精确 p={p_value:.4f}，α={alpha:g}）")
    elif mde is not None:
        resolvable = bool(abs(delta) >= mde)
        significant = resolvable
        direction = ("better" if delta > 0 else "worse") if resolvable else "flat"
        basis = (f"未配对回退（缺逐局记录）：|δ|={abs(delta):.3f} "
                 + (f">= MDE({eval_episodes} 局, p̄={p_base:.3f})={mde:.3f} ⇒ 分辨得出"
                    if resolvable else
                    f"< MDE({eval_episodes} 局, p̄={p_base:.3f})={mde:.3f} ⇒ 分辨不出"))
        fallback = {"kind": "mde_unpaired", "eval_episodes": int(eval_episodes),
                    "p_base": round(p_base, 4), "mde": mde, "resolvable": resolvable}
    else:
        significant, direction = None, "unknown"
        basis = "既没有逐局配对记录、也没有 eval_episodes ⇒ 无从判定显著性"
        fallback = {"kind": "none", "reason": basis}
    reasons.append(f"δ = 候选 {cand_rate:.3f} − 现任 {inc_rate:.3f} = {delta:+.3f}；{basis}")

    # ---- 严酷探针：通常没有逐局记录，所以用 MDE 判"这个掉点分辨得出吗" ------------------
    harsh_reject = False
    harsh_unresolvable_drop = False
    if require_harsh_not_worse and candidate.get("harsh_success_rate") is not None \
            and incumbent.get("harsh_success_rate") is not None:
        ch = float(candidate.get("harsh_success_rate") or 0.0)
        ih = float(incumbent.get("harsh_success_rate") or 0.0)
        hd = round(ch - ih, 6)
        mde_h = round(min_detectable_effect(int(eval_episodes), (ch + ih) / 2.0, alpha=alpha), 4) \
            if eval_episodes else None
        beyond_tol = hd < -regression_tol
        resolvable_h = (abs(hd) >= mde_h) if mde_h is not None else True
        if beyond_tol and resolvable_h:
            harsh_reject = True
            reasons.append(f"严酷探针**可分辨地**掉点: {ch:.3f} < {ih:.3f} − {regression_tol:g}"
                           + (f"（|Δ|={abs(hd):.3f} >= MDE={mde_h:.3f}）" if mde_h else ""))
        elif beyond_tol:
            harsh_unresolvable_drop = True
            reasons.append(f"严酷探针掉了 {hd:+.3f} 但小于噪声地板 MDE={mde_h} ⇒ 分辨不出，"
                           "不作为拒绝理由（二态门禁会在这里误判掉点）")
        else:
            reasons.append(f"严酷探针 {ch:.3f} >= 现任 {ih:.3f} − 容忍 {regression_tol:g}")
    if harsh_reject:
        return out("reject", "harsh_regression", direction, significant,
                   delta=delta, paired=paired, fallback=fallback, mde=mde)

    # ---- 三态判定 --------------------------------------------------------------------
    if significant and direction == "better":
        if delta < min_gain:
            reasons.append(f"提升是真的，但 δ={delta:+.3f} < min_gain={min_gain:g} ⇒ 不值得换版本。"
                           "**注意 direction=better：这不是判它变差**，是判它不够大")
            return out("reject", "real_gain_below_min_gain", "better", True,
                       delta=delta, paired=paired, fallback=fallback, mde=mde)
        reasons.append(f"显著更好且 δ={delta:+.3f} >= min_gain={min_gain:g} ⇒ 发布")
        return out("publish", "significant_gain", "better", True,
                   delta=delta, paired=paired, fallback=fallback, mde=mde)

    if significant and direction == "worse":
        if -delta > regression_tol:
            reasons.append(f"显著掉点且超出容忍: δ={delta:+.3f}，regression_tol={regression_tol:g}")
            return out("reject", "regression", "worse", True,
                       delta=delta, paired=paired, fallback=fallback, mde=mde)
        reasons.append(f"显著掉点但在容忍度内（δ={delta:+.3f} >= −{regression_tol:g}）⇒ 不发布；"
                       "方向记 worse，但没有超出可接受范围")
        return out("reject", "no_gain_within_tol", "worse", True,
                   delta=delta, paired=paired, fallback=fallback, mde=mde)

    # 分辨不出（含 direction=flat / unknown）：第三态。
    reasons.append("差异分辨不出 ⇒ **既不发布也不判掉点**，保留现任；"
                   "下一步是加评测局数或改逐题配对，不是改技能"
                   + ("（严酷探针也有一个分辨不出的下落，别把它当掉点）"
                      if harsh_unresolvable_drop else ""))
    need = None
    if min_gain > 0 and mde is not None and eval_episodes:
        from harness.sampling_design import required_episodes
        need = required_episodes(min_gain, p_base, alpha=alpha).get("unpaired_per_arm")
    return out("inconclusive", "unresolvable", direction or "flat", significant,
               delta=delta, paired=paired, fallback=fallback, mde=mde,
               episodes_needed_for_min_gain=need,
               hint=(f"要判 min_gain={min_gain:g} 约需 {need} 局/臂（未配对口径）"
                     if need else None))


def next_version(skill_dir: Path) -> str:
    """扫已有目录给出下一个版本号。append-only，绝不复用已存在的号。"""
    ensure_dir(skill_dir)
    existing = [p.name for p in skill_dir.iterdir() if p.is_dir() and p.name.startswith("v")]
    nums = []
    for name in existing:
        digits = "".join(ch for ch in name[1:].split("-")[0] if ch.isdigit())
        if digits:
            nums.append(int(digits))
    return f"v{(max(nums) + 1) if nums else 1}"


def publish(
    *,
    skill_name: str,
    ckpt: str | Path | None,
    meta: SkillMeta,
    scores: dict,
    gate: dict,
    registry_root: str | Path = DEFAULT_REGISTRY,
    extra: dict | None = None,
) -> Path:
    """把一个通过门禁的版本写进 registry。已存在的版本号会直接报错，不覆盖。"""
    skill_dir = Path(registry_root) / skill_name
    version = meta.version or next_version(skill_dir)
    target = skill_dir / version
    if target.exists():
        raise FileExistsError(
            f"{target} 已存在。registry 是 append-only：请换版本号，"
            f"不要覆盖历史（否则事后无法复现当时的评测结论）。")
    ensure_dir(target)

    if ckpt:
        src = Path(ckpt)
        if not src.exists():
            raise FileNotFoundError(f"要发布的权重不存在: {src}")
        shutil.copy2(src, target / "model.zip")

    meta.version = version
    meta.eval_score = summarize_scores(scores)
    meta.created_at = meta.created_at or timestamp()
    write_json(target / "meta.json", meta.to_dict())
    write_json(target / "result.json", {"scores": scores, "gate": gate,
                                        "extra": extra or {}, "published_at": timestamp()})
    write_json(skill_dir / "current.json", {
        "skill": skill_name,
        "version": version,
        "published_at": timestamp(),
        "eval_score": meta.eval_score,
        # 存下来是为了让下一次 decide() 能做「环境一致性」检查
        "env_hash": meta.env_hash,
    })
    return target


def list_versions(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> list[dict]:
    skill_dir = Path(registry_root) / skill_name
    if not skill_dir.exists():
        return []
    out = []
    for path in sorted(p for p in skill_dir.iterdir() if p.is_dir()):
        meta_path = path / "meta.json"
        if meta_path.exists():
            out.append(json.loads(meta_path.read_text(encoding="utf-8")) | {"path": str(path)})
    return out


def load_current(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> dict | None:
    pointer = Path(registry_root) / skill_name / "current.json"
    if not pointer.exists():
        return None
    return json.loads(pointer.read_text(encoding="utf-8"))


def current_metrics(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> dict | None:
    """现任版本的门禁指标（用于「不掉点」比较）。"""
    current = load_current(skill_name, registry_root)
    if not current:
        return None
    return current.get("eval_score")


def current_env_hash(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> str:
    """现任版本是在哪个环境下评出来的。空字符串表示老版本没记（不做拦截）。"""
    current = load_current(skill_name, registry_root)
    if not current:
        return ""
    return str(current.get("env_hash") or "")
