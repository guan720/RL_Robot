#!/usr/bin/env python
"""阶段 3 自检：不训练、不联网，几秒钟把闭环的每一层单独验一遍。

为什么要这个？闭环有 6 个部件（技能 / 诊断 / 采样 / 训练 / 门禁 / 版本库），
任何一个静默出错，最后的对照实验结论都是废的，而且**看不出来**——
比如「诊断把救场成功算进主策略成功率」那个 bug，表现只是闭环不再触发训练，
日志上完全看不出异常。所以每一层都要有独立的、会明确失败的检查。

检查项：
    1  模块能导入
    2  诊断标签能区分「找不着路」和「差一点」（7 个用例）
    3  采样器：目标点必须在工作空间内、满足 min_goal_dist、按权重落在对应距离带
    4  门禁：拒绝无进步、拒绝掉点、接受有进步
    5  版本库 append-only：重复版本号必须报错
    6  环境工厂：切换后评测口径真的跟着变
    7  技能接口：三种来源（RL/规划/随机）都能被同一个 run_episode 跑通
    8  严酷探针只许更严不许更松（换环境后不能悄悄放宽）
    9  采样设计：labelcond/frontier/quantile 的分带不变量 + 干预强度门禁（gate v2）
    10 可观测性开关：默认关 / 维度稳 / 队列语义
    11 探针的观测布局解析必须和真实环境逐配置一致（踩过「猜切片」的坑）
    12 接触物理门禁：分辨率算术（MDE/所需局数）+ frontier_verdict 五条规则
    13 提前停止判据（冻结口径）+ 发布判定的分辨率审计 / McNemar 三态
    14 接触任务可复现性（物体尺寸钉死）+ 弹起式成功口径 + 配对两个守卫
    15 三态发布门禁（`registry.decide_paired`）：run7 的两个误判都必须变成 inconclusive
    16 接触探针迁移到 PickPlace：叶子播种 / 物体解析 / 放置段标签与漏斗 / 双口径门禁

用法：
    python scripts/selfcheck_stage3.py            # 全过 -> 退出码 0
    python scripts/selfcheck_stage3.py -v         # 打印每一项的细节
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("gymnasium", "numpy", "py_trees")

VERBOSE = False
FAILED: list[str] = []


def say(text: str) -> None:
    if VERBOSE:
        print(f"      {text}")


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  <- {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)
    return ok


def _rec(init: float, mn: float, fin: float, success: bool = False):
    from skills.base import EpisodeRecord

    return EpisodeRecord(direction="forward", role="primary", skill="t", seed=0, steps=50,
                         success=success, terminated=success, truncated=not success,
                         init_dist=init, final_dist=fin, min_dist=mn, goal=[0.1, 0.0, 0.0])


def check_imports() -> None:
    import importlib

    mods = ["skills.base", "skills.reach_skills", "harness.diagnose", "harness.sampling",
            "harness.env_factory", "harness.trainer", "harness.tree", "harness.loop",
            "registry.publish", "envs.reach_perturbed",
            # 参照控制器缺陷取证探针（§12.11-R.4.1）：它 import 探针的 build_env /
            # make_scripted_factory，签名一变就会在这里炸，而不是在交接给对方之后才炸
            "scripts.probe_scripted_defect_repro"]
    bad = []
    for name in mods:
        try:
            importlib.import_module(name)
        except Exception as exc:            # noqa: BLE001
            bad.append(f"{name}: {exc}")
    check("1 模块导入（11 个）", not bad, "; ".join(bad))


def check_diagnose() -> None:
    from harness.diagnose import label_episode

    cases = [
        ("成功", _rec(0.20, 0.005, 0.005, True), "success"),
        ("到过附近但停在圈外", _rec(0.20, 0.031, 0.031), "no_precision"),
        ("正好在 2×半径边界（闭区间）", _rec(0.20, 0.060, 0.065), "no_precision"),
        ("一直很远", _rec(0.20, 0.180, 0.190), "timeout_far"),
        ("中等距离超时", _rec(0.20, 0.070, 0.075), "timeout_mid"),
        ("越走越远", _rec(0.20, 0.200, 0.250), "diverged"),
        ("几乎没动", _rec(0.20, 0.199, 0.200), "never_moved"),
    ]
    bad = []
    for label, record, want in cases:
        got = label_episode(record, goal_radius=0.03)
        say(f"{label}: {got}")
        if got != want:
            bad.append(f"{label} 期望 {want} 实得 {got}")
    check(f"2 诊断标签（{len(cases)} 个用例）", not bad, "; ".join(bad))


def check_sampling() -> None:
    import numpy as np

    from harness.diagnose import SamplingPlan
    from harness.sampling import BandedGoalSampler, RegionGoalSampler, UniformGoalSampler

    env_kwargs = {"half_space": 0.15, "min_goal_dist": 0.10, "goal_radius": 0.02}
    problems = []
    for sampler in (UniformGoalSampler(seed=1, **{k: env_kwargs[k] for k in ("half_space", "min_goal_dist")}),
                    RegionGoalSampler(sign=+1, seed=2, half_space=0.15, min_goal_dist=0.10),
                    RegionGoalSampler(sign=-1, seed=3, half_space=0.15, min_goal_dist=0.10)):
        for _ in range(300):
            goal = sampler.draw()
            if np.any(np.abs(goal) > env_kwargs["half_space"] + 1e-9):
                problems.append(f"{type(sampler).__name__} 采出工作空间外的目标 {goal}")
                break
            if np.linalg.norm(goal) < env_kwargs["min_goal_dist"] - 1e-9:
                problems.append(f"{type(sampler).__name__} 目标离起点太近 {goal}")
                break
        say(f"{type(sampler).__name__}: 300 次采样全部合法，平均距离 "
            f"{np.mean([np.linalg.norm(g) for g in sampler.history]):.3f}")

    # 带权采样：权重集中在第 2 带，命中数就应该明显偏向第 2 带
    plan = SamplingPlan(bands=[(0.10, 0.14), (0.14, 0.18), (0.18, 0.22), (0.22, 0.2598)],
                        weights=[0.05, 0.80, 0.10, 0.05])
    banded = BandedGoalSampler(plan, half_space=0.15, min_goal_dist=0.10, seed=4, mix_uniform=0.0)
    for _ in range(400):
        banded.draw()
    hits = banded.band_hits
    say(f"BandedGoalSampler 命中分布 {hits}（权重 0.05/0.80/0.10/0.05, mix_uniform=0）")
    # 判据是「命中最多的带 == 权重最高的带」，不是「hits[1] 大于 max」
    # （hits[1] <= max(hits) 恒真，会把正确结果也判成失败——这个断言本身就错过一次）
    if max(range(len(hits)), key=lambda i: hits[i]) != 1:
        problems.append(f"带权采样没有偏向高权重带(期望第 2 带命中最多): {hits}")
    if sum(1 for h in hits if h == 0) > 1:
        problems.append(f"某些距离带完全采不到（floor 失效或该带无合法点）: {hits}")
    check("3 采样器合法性 + 带权命中分布", not problems, "; ".join(problems))


def check_gate() -> None:
    from registry.publish import decide

    incumbent = {"success_rate": 0.50, "harsh_success_rate": 0.30}
    cases = [
        ("无进步", {"success_rate": 0.50, "harsh_success_rate": 0.30}, False),
        ("旧任务掉点", {"success_rate": 0.40, "harsh_success_rate": 0.30}, False),
        ("严酷探针掉点", {"success_rate": 0.60, "harsh_success_rate": 0.20}, False),
        ("有进步", {"success_rate": 0.60, "harsh_success_rate": 0.35}, True),
    ]
    bad = []
    for label, candidate, want in cases:
        ok, reasons = decide(candidate, incumbent, min_gain=0.02)
        say(f"{label}: ok={ok} · {reasons[1] if len(reasons) > 1 else reasons[0]}")
        if ok != want:
            bad.append(f"{label} 期望 {'通过' if want else '拒绝'} 实得 {'通过' if ok else '拒绝'}")
    first_ok, _ = decide({"success_rate": 0.10, "harsh_success_rate": 0.0}, None)
    if not first_ok:
        bad.append("首次发布（无现任）被错误拒绝")

    # 规则 0：不同环境的分数不可比，必须被拦住（这条是踩了坑才加的，见 notes_stage3 §7）
    cross_ok, cross_reasons = decide(
        {"success_rate": 0.99, "harsh_success_rate": 0.99},
        {"success_rate": 0.10, "harsh_success_rate": 0.05},
        min_gain=0.02, candidate_env_hash="aaa", incumbent_env_hash="bbb")
    say(f"跨环境发布: ok={cross_ok} · {cross_reasons[0][:70]}")
    if cross_ok:
        bad.append("跨环境的版本被放进了同一条版本线（env_hash 不一致却通过了门禁）")
    same_ok, _ = decide(
        {"success_rate": 0.99, "harsh_success_rate": 0.99},
        {"success_rate": 0.10, "harsh_success_rate": 0.05},
        min_gain=0.02, candidate_env_hash="aaa", incumbent_env_hash="aaa")
    if not same_ok:
        bad.append("同一环境下的正常进步被误拦")
    check(f"4 发布门禁（{len(cases) + 3} 个用例，含跨环境拦截）", not bad, "; ".join(bad))


def check_registry_append_only() -> None:
    from registry import publish as registry
    from skills.base import SkillMeta

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meta = SkillMeta(name="t", version="v1", kind="random")
        registry.publish(skill_name="t", ckpt=None, meta=meta,
                         scores={"standard": {"success_rate": 0.5}, "harsh": None},
                         gate={"ok": True}, registry_root=root)
        dup = ""
        try:
            registry.publish(skill_name="t", ckpt=None,
                             meta=SkillMeta(name="t", version="v1", kind="random"),
                             scores={"standard": {"success_rate": 0.9}, "harsh": None},
                             gate={"ok": True}, registry_root=root)
        except FileExistsError as exc:
            dup = str(exc)
        say(f"重复发布 v1 -> {dup[:60]}")
        v2 = registry.next_version(root / "t")
        ok = bool(dup) and v2 == "v2" and registry.load_current("t", root)["version"] == "v1"
        check("5 版本库 append-only（拒绝覆盖 + 版本号自增）", ok,
              f"dup={bool(dup)} next={v2}")


def check_env_factory() -> None:
    from eval.reach_eval import evaluate_reach
    from harness.env_factory import install_env_factory
    from skills.reach_skills import ProportionalReachSkill

    env_kwargs = {"max_steps": 40, "action_scale": 0.05, "goal_radius": 0.02,
                  "min_goal_dist": 0.10, "half_space": 0.15}
    install_env_factory("reach")
    plain = evaluate_reach(ProportionalReachSkill(action_scale=0.05, gain=1.0),
                           env_kwargs, n_episodes=20, seed=999)["success_rate"]
    install_env_factory("perturbed")
    perturbed_kwargs = {**env_kwargs, "action_delay": 4, "gain_noise": 0.7, "drift": 0.008}
    pert = evaluate_reach(ProportionalReachSkill(action_scale=0.05, gain=1.0),
                          perturbed_kwargs, n_episodes=20, seed=999)["success_rate"]
    install_env_factory("reach")
    say(f"同一个比例控制技能：无扰动 {plain:.2f} -> 扰动 {pert:.2f}")
    check("6 环境工厂切换（同一技能在扰动环境下应显著变差）",
          plain > pert + 0.1, f"plain={plain} perturbed={pert}")


def check_obs_extensions() -> None:
    """第 10 项：run7 的两个可观测性开关必须「默认关、维度稳、队列语义对」。

    默认关保证历史数字可比；维度稳是 SB3 的前提（队列长度在 reset/step 间会跳，
    靠补零垫定长）；队列语义指「step t 之后观测里出现在途指令 = 第 t 步发出、
    下一步才生效的那条」，补零在前。
    """
    import numpy as np

    from envs.reach_perturbed import PerturbedReachEnv

    base_kw = {"max_steps": 20, "action_scale": 0.05, "goal_radius": 0.02,
               "min_goal_dist": 0.10, "half_space": 0.15, "action_delay": 2,
               "gain_noise": 0.5, "drift": 0.004}
    bad: list[str] = []
    plain = PerturbedReachEnv(**base_kw)
    if tuple(plain.observation_space.shape) != (6,):
        bad.append(f"默认关应仍是 6 维: {plain.observation_space.shape}")
    for kw, want in [({"expose_queue": True}, 12), ({"obs_stack": 3}, 18),
                     ({"expose_queue": True, "obs_stack": 3}, 24)]:
        env = PerturbedReachEnv(**base_kw, **kw)
        obs, _ = env.reset(seed=0)
        shapes = {tuple(obs.shape)}
        for _ in range(6):
            o, _, _, _, _ = env.step(env.action_space.sample())
            shapes.add(tuple(o.shape))
        if tuple(env.observation_space.shape) != (want,) or shapes != {(want,)}:
            bad.append(f"{kw} 维度不对或不稳: space={env.observation_space.shape} seen={shapes}")
    env = PerturbedReachEnv(**{**base_kw, "gain_noise": 0.0, "drift": 0.0,
                               "expose_queue": True})
    env.reset(seed=1)
    cmd = np.array([0.5, -0.25, 0.1])
    obs, *_ = env.step(cmd)
    if not np.allclose(obs[6:], np.concatenate([np.zeros(3), cmd]), atol=1e-6):
        bad.append(f"队列语义错: {obs[6:]}")
    check("10 可观测性开关（默认关 / 维度稳 / 队列语义）", not bad, "; ".join(bad))


def check_probe_obs_layout() -> None:
    """第 11 项：探针脚本里的观测切片必须和真实环境一致。

    踩过的坑（run7 期间真实发生）：`scripts/probe_fullstate_ceiling.py` 早先用
    `flat[-6:]` 猜「最新帧」。在 stack3+expose_queue(24 维) 上它取到的是**在途指令
    本身**，于是那个确定性对照退化成 cmd_t = 0.9 * cmd_{t-1}，几步之后恒为 0，
    表现为「y 方差为 0、R² 是 nan」。如果没查出来，就会被当成「确定性策略也恢复不了
    在途指令」写进结论 —— 而真实结论恰好相反（R²=1.0000）。

    所以这里对 4 种维度组合逐一校验：解析出的维度 == 实际维度；最新帧切片能还原
    真 ee/goal；在途指令切片能还原环境里真正 pending 的那条。
    """
    import numpy as np

    from envs.reach_perturbed import PerturbedReachEnv
    from scripts.probe_fullstate_ceiling import decode_ee_goal, obs_layout

    base_kw = {"max_steps": 20, "action_scale": 0.05, "goal_radius": 0.02,
               "min_goal_dist": 0.10, "half_space": 0.15, "action_delay": 2,
               "gain_noise": 0.5, "drift": 0.004}
    half = base_kw["half_space"]
    bad: list[str] = []
    combos = [{}, {"expose_queue": True}, {"obs_stack": 3},
              {"obs_stack": 3, "expose_queue": True}]
    for kw in combos:
        env_kw = {**base_kw, **kw}
        lay = obs_layout(env_kw)
        env = PerturbedReachEnv(**env_kw)
        obs, _ = env.reset(seed=7)
        if lay["dim"] != obs.shape[0]:
            bad.append(f"{kw or '默认'}: 解析维度 {lay['dim']} != 实际 {obs.shape[0]}")
        for step_i in range(5):
            ee, goal = decode_ee_goal(obs, half, lay)
            if not (np.allclose(ee, env.ee, atol=2e-3)
                    and np.allclose(goal, env.goal, atol=2e-3)):
                bad.append(f"{kw or '默认'} 第{step_i}步 最新帧切片错: "
                           f"ee={ee.round(4)} vs {env.ee.round(4)}")
                break
            if lay["in_flight_cmd"]:
                qa, qb = lay["in_flight_cmd"]
                want = np.asarray(env._pending[-1], dtype=np.float64).reshape(3)
                if not np.allclose(np.asarray(obs, dtype=np.float64).reshape(-1)[qa:qb],
                                   want, atol=2e-3):
                    bad.append(f"{kw or '默认'} 第{step_i}步 在途指令切片错: "
                               f"{obs[qa:qb]} vs {want}")
                    break
            obs, _, term, trunc, _ = env.step(env.action_space.sample())
            if term or trunc:
                break
    check("11 探针观测布局解析（4 种维度组合，切片对得上真实状态）", not bad, "; ".join(bad))


def check_skills() -> None:
    from envs.reach_env import make_reach_env
    from skills.base import run_episode
    from skills.reach_skills import ProportionalReachSkill, RandomSkill

    env = make_reach_env()
    bad = []
    for skill in (RandomSkill(seed=0), ProportionalReachSkill(gain=1.0)):
        record = run_episode(env, skill, seed=11)
        say(f"{skill.meta.short()}: steps={record.steps} success={record.success} "
            f"末距={record.final_dist:.4f}")
        if record.steps <= 0 or len(record.dist_trace) != record.steps + 1:
            bad.append(f"{skill.meta.name} 记录不完整")
    prop = ProportionalReachSkill(gain=1.0)
    if not run_episode(env, prop, seed=12).success:
        bad.append("比例控制在无扰动 Reach 上竟然失败（环境或技能实现有问题）")
    check("7 技能接口（三种来源同一 run_episode）", not bad, "; ".join(bad))


def check_harsh_probe() -> None:
    from registry.publish import HARSH_PROBE, harsh_probe_kwargs

    cases = [
        ("默认 Reach", {"max_steps": 100, "goal_radius": 0.03},
         HARSH_PROBE["max_steps"], HARSH_PROBE["goal_radius"]),
        ("reach_hard", {"max_steps": 50, "goal_radius": 0.02}, 25, 0.02),
        ("reach_perturbed", {"max_steps": 40, "goal_radius": 0.02}, 20, 0.02),
    ]
    bad = []
    for label, env_kwargs, want_steps, want_radius in cases:
        got = harsh_probe_kwargs(env_kwargs)
        say(f"{label}: {got}")
        if got["max_steps"] != want_steps or abs(got["goal_radius"] - want_radius) > 1e-9:
            bad.append(f"{label} 期望 steps={want_steps} radius={want_radius} 实得 {got}")
        if got["max_steps"] > env_kwargs["max_steps"] or got["goal_radius"] > env_kwargs["goal_radius"]:
            bad.append(f"{label} 探针比环境本身还松: {got}")
    check("8 严酷探针只许更严（默认环境口径不变，历史数字可比）", not bad, "; ".join(bad))


def check_sampling_design() -> None:
    """第 9 项：新分带设计的不变量。这些断言全部来自探针实测踩过的坑，
    任何一条被改坏，A/B 就会静默退化成「又跑了一次 uniform」。"""
    from harness.diagnose import SamplingPlan, build_sampling_plan, label_all
    from harness.sampling_design import (design_table, effective_tv, gate_verdict,
                                        gate_verdict_phased, realized_distance_profile,
                                        tv_ceiling)

    bad: list[str] = []
    radius, half = 0.03, 0.15

    # (1) labelcond：精度失败的目标距离 = 它卡住的半径（会被钳进带域），
    #     于是质量应该集中到最近的带，而不是像 range 那样喂给空带。
    precision = [_rec(0.20, 0.031, 0.031) for _ in range(6)] + [_rec(0.20, 0.18, 0.19)]
    label_all(precision, radius)
    plan = build_sampling_plan([r for r in precision if not r.success], radius, half,
                               n_bands=3, floor=0.0, band_mode="labelcond")
    if plan.reason.get("hist_variable") != "label_target_dist":
        bad.append("labelcond 的 hist_variable 记错")
    if not plan.weights[0] > plan.weights[-1]:
        bad.append(f"labelcond 没把质量集中到近带: {plan.weights}")

    # (2) frontier：目标距离 = min_dist，与初始距离无关。
    diverged = [_rec(0.20, 0.19, 0.25) for _ in range(4)]
    label_all(diverged, radius)
    plan_f = build_sampling_plan(diverged, radius, half, n_bands=3, floor=0.05,
                                 band_mode="frontier")
    if plan_f.reason.get("hist_variable") != "min_dist":
        bad.append("frontier 的 hist_variable 记错")

    # (3) quantile 构造上把失败均分到各带 -> 干预强度必然接近 0。
    #     这是探针实测结论的固化：谁再把 quantile 当「更强的干预」就该被这条拦住。
    spread = [_rec(0.10 + 0.02 * i, 0.05, 0.09) for i in range(8)]
    label_all(spread, radius)
    plan_q = build_sampling_plan(spread, radius, half, n_bands=4, floor=0.05,
                                 band_mode="quantile")
    if effective_tv(plan_q.weights, 0.25) >= 0.1:
        bad.append(f"quantile 分带的 TV 应该≈0，实得 {effective_tv(plan_q.weights, 0.25):.3f}")

    # (4) 两个保护：
    #     a) 没有失败时（全成功）不能返回全零权重（floor=0 时 TV 会变 nan），
    #        必须退化成均匀并在 reason 里记账；
    #     b) 子带域外的目标距离会被钳进带域（labelcond 的 min_dist 常常 < lo），
    #        所以「精度失败集中在最近带」是正确行为，不是 bug —— 这里断言它集中。
    plan_z = build_sampling_plan([], radius, half, n_bands=3, floor=0.0,
                                 band_mode="labelcond")
    if abs(sum(plan_z.weights) - 1.0) > 1e-9 or effective_tv(plan_z.weights, 0.25) != 0.0:
        bad.append(f"空失败保护失效: weights={plan_z.weights}")
    if not plan_z.reason.get("fell_back_to_uniform"):
        bad.append("退化到均匀时没在 reason 里记账")
    if effective_tv([0.0, 0.0, 0.0], 0.25) != 0.0:
        bad.append("effective_tv 对全零权重应返回 0（防 nan）")
    tiny = [_rec(0.20, 0.001, 0.001) for _ in range(3)]
    label_all(tiny, radius)
    plan_c = build_sampling_plan(tiny, radius, half, n_bands=3, floor=0.0,
                                 band_mode="labelcond")
    if not plan_c.weights[0] == 1.0:
        bad.append(f"带域外目标应被钳进最近带: weights={plan_c.weights}")

    # (5) gate v2 的三条规则：中后期过门槛 / 早期不退化 / 均值过门槛。
    def verdict(tv: float) -> dict:
        return {"ok": tv >= 0.4, "best": {"tv": tv, "starved_bands": []}, "reason": ""}

    if not gate_verdict_phased([verdict(0.34), verdict(0.5), verdict(0.5)],
                               tv_gate=0.4)["ok"]:
        bad.append("gate v2 误拒了 [0.34, 0.5, 0.5]")
    if gate_verdict_phased([verdict(0.10), verdict(0.5), verdict(0.5)],
                           tv_gate=0.4)["ok"]:
        bad.append("gate v2 放过了早期退化的 [0.10, 0.5, 0.5]")
    if gate_verdict_phased([verdict(0.34), verdict(0.30), verdict(0.5)],
                           tv_gate=0.4)["ok"]:
        bad.append("gate v2 放过了中后期不过门槛的 [0.34, 0.30, 0.5]")

    # (6) TV 天花板：门槛必须落在设计空间**可达**范围内，否则「拒绝」是构造性的、
    #     不是实测结论；反过来压满天花板 = one-hot 计划（floor 归零），过门禁 ≠ 好设计，
    #     必须带 warning，让 A/B 去看「旧任务掉点」。
    if abs(tv_ceiling(3, 0.25) - 0.5) > 1e-9 or abs(tv_ceiling(4, 0.25) - 0.5625) > 1e-9:
        bad.append(f"tv_ceiling 公式变了: 3带={tv_ceiling(3, 0.25)} 4带={tv_ceiling(4, 0.25)}")
    if abs(effective_tv([1.0, 0.0, 0.0], 0.25) - tv_ceiling(3, 0.25)) > 1e-9:
        bad.append("one-hot 计划应恰好取到天花板")
    if tv_ceiling(2, 0.25) >= 0.4:
        bad.append("2 带天花板应低于默认门槛 0.4（该设计族构造上过不了门禁）")
    tiny_failures = [r for r in tiny if not r.success]
    rows3 = design_table(tiny_failures, goal_radius=radius, half_space=half,
                         candidates=[{"band_mode": "labelcond", "floor": 0.0, "n_bands": 3}])
    if not rows3[0]["one_hot"] or rows3[0]["tv_frac"] < 0.99:
        bad.append(f"全钳进近带时应压满天花板: {rows3[0]}")
    verdict3 = gate_verdict(rows3, tv_gate=0.4)
    if not verdict3["ok"]:
        bad.append(f"TV=天花板 0.5 应过 0.4 门槛: {verdict3['reason']}")
    if not verdict3.get("warnings"):
        bad.append("压满天花板的推荐必须带 warning（过门禁 ≠ 好设计）")
    rows2 = design_table(tiny_failures, goal_radius=radius, half_space=half,
                         candidates=[{"band_mode": "range", "floor": 0.0, "n_bands": 2}])
    verdict2 = gate_verdict(rows2, tv_gate=0.4)
    if verdict2["ok"] or not any("构造上不可达" in w for w in verdict2.get("warnings") or []):
        bad.append(f"2 带应被拒且给出构造性不可达提示: {verdict2}")

    # (7) 实测口径（真跑采样器）：one-hot 计划在距离空间上必须显著偏离均匀，
    #     全幅单带必须≈无干预，且前者的距离覆盖必须更窄。
    #     这三条一起才说明「TV距离/覆盖」两列不是装饰品。
    hi = half * 3 ** 0.5
    onehot = SamplingPlan([(0.04, 0.1133), (0.1133, 0.1865), (0.1865, hi)], [1.0, 0.0, 0.0], {})
    full = SamplingPlan([(0.06, hi)], [1.0], {})
    prof_hot = realized_distance_profile(onehot, half_space=half, min_goal_dist=0.1, n_draws=1500)
    prof_full = realized_distance_profile(full, half_space=half, min_goal_dist=0.1, n_draws=1500)
    if prof_hot["tv_distance"] < 0.3:
        bad.append(f"one-hot 计划的 TV距离应远大于噪声地板，实得 {prof_hot}")
    if prof_hot["tv_distance"] <= prof_hot["tv_noise_floor"] * 3:
        bad.append(f"TV距离没跑赢噪声地板 3 倍: {prof_hot}")
    if prof_full["tv_distance"] > 0.15:
        bad.append(f"全幅单带应≈无干预，实得 {prof_full}")
    if prof_hot["support_frac"] >= prof_full["support_frac"]:
        bad.append(f"one-hot 的距离覆盖应窄于全幅单带: "
                   f"{prof_hot['support_frac']} vs {prof_full['support_frac']}")

    # (8) gate v3：两类「名义强、实际空转」的候选必须被拦住。数字直接取自
    #     runs/infra/20260923_142507_intervention_probe.json 的实测行。
    def row(**kw) -> dict:
        base = {"band_mode": "labelcond", "floor": 0.05, "n_bands": 4, "tv": 0.469,
                "tv_ceiling": 0.5625, "tv_frac": 0.83, "one_hot": False,
                "weights": [0.875, 0.0417, 0.0417, 0.0417], "starved_bands": [2, 3, 4],
                "tv_distance": 0.044, "tv_noise_floor": 0.028, "support_frac": 0.54,
                "uniform_support_frac": 0.53, "fallback_rate": 0.667}
        base.update(kw)
        return base

    voided = gate_verdict([row()], tv_gate=0.4)
    if voided["ok"] or voided.get("metric") != "tv_distance":
        bad.append(f"名义 0.469/实测 0.044 的候选应被 gate v3 拒（按实测口径）: {voided}")
    if not any("作废" in w for w in voided.get("warnings") or []):
        bad.append("fallback 超标的候选必须在 warnings 里被点名作废")
    narrow = gate_verdict([row(tv=0.5, tv_distance=0.65, fallback_rate=0.0, one_hot=True,
                               support_frac=0.10)], tv_gate=0.4)
    if narrow["ok"] or "覆盖" not in narrow["reason"]:
        bad.append(f"实测 TV 够但覆盖 0.10（均匀 0.53）应被拒: {narrow}")
    if narrow.get("coverage_ok") is not False:
        bad.append("覆盖率拒绝必须写 coverage_ok=False（分阶段门禁靠它）")
    good = gate_verdict([row(tv=0.5, tv_distance=0.65, fallback_rate=0.0, one_hot=True,
                             support_frac=0.38)], tv_gate=0.4)
    if not good["ok"]:
        bad.append(f"run3 用的 labelcond/f0/b3 实测口径应过门禁: {good['reason']}")
    if gate_verdict_phased([good, narrow], tv_gate=0.4)["ok"]:
        bad.append("任一阶段覆盖率不合格，总门禁必须不通过")

    # (9) objective：strength 选最强、coverage 在过门槛的里选覆盖最宽（run4 的选法）。
    strong = row(tv=0.5, tv_distance=0.65, fallback_rate=0.0, one_hot=True, support_frac=0.38,
                 band_mode="frontier", floor=0.0, n_bands=3)
    wide = row(tv=0.435, tv_distance=0.593, fallback_rate=0.0, one_hot=False, support_frac=0.46,
               band_mode="frontier", floor=0.05, n_bands=3,
               weights=[0.913, 0.0435, 0.0435], tv_frac=0.87)
    pick_s = gate_verdict([strong, wide], tv_gate=0.4, objective="strength")["best"]
    pick_c = gate_verdict([strong, wide], tv_gate=0.4, objective="coverage")["best"]
    if pick_s is not strong or pick_c is not wide:
        bad.append(f"objective 选错: strength→{pick_s['floor']} coverage→{pick_c['floor']}")
    if gate_verdict([wide], tv_gate=0.4, objective="coverage")["best"] is not wide:
        bad.append("唯一候选过门槛时 coverage 目标也应选它")
    try:
        gate_verdict([wide], tv_gate=0.4, objective="bogus")
        bad.append("objective 非法值没报错")
    except ValueError:
        pass

    check(f"9 采样设计不变量 + gate v2/v3（{9} 组断言）", not bad, "; ".join(bad))


def check_frontier_gate() -> None:
    """第 12 项：接触任务的 A/B 前置门禁。

    这些断言里最关键的是**分辨率算术**——它不是风格问题，是阶段 3 A/B 一直给出
    「看着有提升」却复现不出来的根因之一：run7 的门禁用 `eval_episodes=50`
    配 `min_gain=0.02`，而 50 局二项评测的 MDE ≈ 0.28，门禁在按噪声发布版本。
    数字取自本轮实测：`runs/infra/spawn_sweep_lift.json`（Lift 手写上限 ±0.03~±0.18 m
    全为 1.000，每局 ~4.8 s）与 `runs/ab_stage3/run7_fullstate/noearly_s0/journal.jsonl`
    （gate 以 +0.140 通过、下一轮 0.040 被撤回）。
    """
    from harness.sampling_design import (frontier_verdict, mcnemar, mde_worst_case,
                                        min_detectable_effect, paired_gate,
                                        required_episodes)

    bad: list[str] = []

    # (1) MDE：50 局 ≈ 0.28（α=0.05、power=0.8、p̄≈0.5 的标准两比例口径）；
    #     必须随 n 单调下降，且 n→大 时逼近 0。
    mde50 = min_detectable_effect(50)
    if not 0.24 <= mde50 <= 0.32:
        bad.append(f"MDE(50) 应在 0.24~0.32（实测 {mde50:.3f}），公式被改了？")
    if not min_detectable_effect(200) < mde50 < min_detectable_effect(10):
        bad.append("MDE 必须随局数单调下降")
    if not min_detectable_effect(0) == float("inf"):
        bad.append("n=0 时 MDE 应为 inf（不许静默当成可判定）")
    # (1b) `p_base=0.5` **不是**最保守口径：δ 会把 p̄ 推到 p_base+δ/2，
    #      p_base=0.35 时 p̄≈0.49 更靠近方差最大点。上界必须用闭式的 mde_worst_case。
    if not min_detectable_effect(50, 0.35) > min_detectable_effect(50, 0.5):
        bad.append("MDE(50,0.35) 应大于 MDE(50,0.5)（这条反直觉关系被改没了）")
    for pb in (0.0, 0.1, 0.35, 0.5, 0.7, 0.9, 1.0):
        for n in (20, 50, 200, 5000):
            if min_detectable_effect(n, pb) > mde_worst_case(n) + 1e-9:
                bad.append(f"mde_worst_case 不再是上界: n={n} p_base={pb}")
    if abs(mde_worst_case(50) - 2.799 * 0.1) > 0.01:
        bad.append(f"mde_worst_case(50) 应≈0.28，实得 {mde_worst_case(50):.4f}")

    # (2) 所需局数：要检出 2 个点的差，独立两臂口径需要上万局；配对能省一个量级，
    #     但前提是同 seed 真出同一道题（探针 verify_seeding 守的就是这条）。
    need = required_episodes(0.02, 0.5)
    if not 5000 <= need["unpaired_per_arm"] <= 15000:
        bad.append(f"检出 δ=0.02 每臂需 ~1 万局（2(z_α+z_β)²p̄(1-p̄)/δ²），"
                   f"实得 {need['unpaired_per_arm']}")
    # (2b) 配对**不是白省的**：方差从 2p(1-p)/n 变成 (d-δ²)/n，
    #      所以 d < 2p(1-p) 才省。两条方向都必须钉住，否则会被拿去合理化更小的评测预算。
    agree = required_episodes(0.02, 0.5, discordant=0.10)     # A/B 两条相似策略：绝大多数题同结论
    disagree = required_episodes(0.02, 0.5, discordant=0.90)  # 手写 vs SAC：几乎题题不同结论
    if not (agree["paired_pairs"] < need["unpaired_per_arm"] and agree["paired_cheaper"]):
        bad.append(f"d=0.10 时配对应省局数: {agree}")
    if not (disagree["paired_pairs"] > need["unpaired_per_arm"]
            and disagree["paired_cheaper"] is False):
        bad.append(f"d=0.90 时配对应更贵（这种配对只为诊断）: {disagree}")
    if required_episodes(0.02, 0.5, discordant=0.9)["paired_pairs"] is None:
        bad.append("d=0.9 >= δ² 时配对口径应有解")
    if required_episodes(0.0)["unpaired_per_arm"] is not None:
        bad.append("δ<=0 应返回 None 而不是编一个局数")

    # (2c) **硬约束 |δ| <= d**（本轮抓到的 bug）：δ=(c−b)/n、d=(b+c)/n、b,c>=0 ⇒ |c−b|<=b+c。
    #      旧守卫只查 d >= δ²（公式定义域），于是 (δ=0.20, d=0.10) 这种**不可达**组合被当成
    #      有解、报 18 对，§12.11-H 一度照抄成「省 4.4×」。真实下界是 d=|δ| ⇒ 37 对（省 2.1×）。
    imp = required_episodes(0.20, 0.17, discordant=0.10)
    if imp["paired_pairs"] is not None:
        bad.append(f"d=0.10 < |δ|=0.20 不可达，必须拒绝，实得 {imp['paired_pairs']} 对")
    if "|δ|" not in (imp.get("paired_reason") or ""):
        bad.append(f"拒绝理由必须点名硬约束 |δ|<=d: {imp.get('paired_reason')}")
    if imp.get("paired_floor_pairs") != 37:
        bad.append(f"δ=0.20 的配对下界应是 37 对，实得 {imp.get('paired_floor_pairs')}")
    floor = required_episodes(0.20, 0.17, discordant=0.20)
    if floor["paired_pairs"] != floor["paired_floor_pairs"] or not floor["paired_at_floor"]:
        bad.append(f"d=|δ| 时应正好落在下界: {floor}")
    if not 2.0 <= floor["unpaired_per_arm"] / floor["paired_floor_pairs"] <= 2.3:
        bad.append(f"δ=0.20/p=0.17 的配对最大节省应≈2.1×（79/37），实得 "
                   f"{floor['unpaired_per_arm']}/{floor['paired_floor_pairs']}")
    # 下界对所有合法 d 成立，且 n_pairs 随 d 单调上升（d 越大越没得省）
    prev = 0
    for d in (0.20, 0.25, 0.30, 0.40, 0.60, 0.90):
        got = required_episodes(0.20, 0.17, discordant=d)
        if got["paired_pairs"] < got["paired_floor_pairs"]:
            bad.append(f"d={d}: 配对局数低于数学下界 {got['paired_floor_pairs']}")
        if got["paired_pairs"] <= prev:
            bad.append(f"d={d}: n_pairs 必须随 d 单调上升（{prev} -> {got['paired_pairs']}）")
        prev = got["paired_pairs"]
    # reach 饱和退化实测（§12.11-L）：p̄=0.987、δ=0.026、d=0.026 ⇒ 正好在下界，配对**不省**
    # （300 对 vs 297 局/臂）。这条把「配对不省」从判据升级成「已经无可省」。
    sat = required_episodes(0.026, 0.987, discordant=0.026)
    if not (sat["paired_at_floor"] and sat["paired_pairs"] >= sat["unpaired_per_arm"]):
        bad.append(f"饱和工作点应落在下界且配对不省: {sat}")

    # (2d) 两个「谁更省」的口径在盈亏平衡点附近会打架，必须都被算出来并在 note 里点名
    split = required_episodes(0.20, 0.17, discordant=0.30)
    if split["paired_cheaper"] is not False or split["paired_cheaper_by_n"] is not True:
        bad.append(f"d=0.30 应出现方差判据/局数判据分歧: {split}")
    if "不一致" not in split["paired_note"]:
        bad.append(f"分歧必须在 paired_note 里点名: {split['paired_note']}")

    # (3) 五条规则逐条必须会拒。每条都用一个只违反它自己的档位。
    # CHEAP = 分辨率与成本都给得起的最小配置：MDE(200)=0.14 <= 0.30，
    # 2 臂 × (8 采集 + 200 评测) × 10 轮 × 5 s/局 = 5.8 h <= 8 h。
    # 有了它，下面每个用例才只违反**它自己**那一条规则。
    CHEAP = {"budget_sec": 8 * 3600, "arms": 2, "rounds": 10, "episodes_per_round": 8,
             "eval_episodes": 200, "min_gain": 0.30, "regression_tol": 0.30}
    good = {"half_range": 0.12, "scripted_success": 1.0, "sac_success": 0.35,
            "frontier_frac": 0.55, "too_hard_frac": 0.10, "sec_per_episode": 5.0,
            "seeding_ok": True, "ctrl_z0_mismatch": 0}

    def only(**kw) -> dict:
        rung = dict(good)
        rung.update(kw)
        return [rung]

    cases = [
        ("data", only(seeding_ok=False), "出题不可复现必须整档作废"),
        ("data", only(ctrl_z0_mismatch=3), "控制器 z0 与出生点不符 = 量到的是时序 bug"),
        ("ceiling", only(scripted_success=0.30), "手写上限 0.30 应先修控制器"),
        ("ceiling", only(scripted_success=0.70), "手写上限 0.70 参照不可信"),
        ("band", only(sac_success=0.02), "策略贴地：全局成功率无分辨力"),
        ("band", only(sac_success=0.99), "策略饱和：无可学空间"),
        ("band", only(sac_success=None), "没评策略不能开 A/B"),
        ("frontier", only(frontier_frac=0.02), "frontier 太小时针对性采样无处发力"),
        ("frontier", only(too_hard_frac=0.90), "「都不成」太多时采样也学不到"),
        ("cost", only(sec_per_episode=120.0), "120 s/局 × 8 × 10 × 6 臂必须超预算"),
        # 本轮新增的两条（§12.11-M/N）：物体尺寸没钉死 = 评的是另一个物体；
        # 成功率主要靠"弹一下" = 指标本身不是完成任务。
        ("data", only(object_pinned=False), "物体尺寸未钉死 ⇒ 每进程一个不同 cube，整档作废"),
        ("metric", only(flick_frac=0.80, success_rate_grasp_verified=0.03),
         "成功率 80% 靠弹起（真抓起来只有 3%）时不能开 A/B"),
    ]
    for rule, rung, note in cases:
        v = frontier_verdict(rung, **CHEAP)
        # 每个用例只许违反它自己那一条规则，否则「规则会拒」这个断言是被别的规则蒙对的
        if v["rungs"][0]["failed"] != [rule]:
            bad.append(f"{note}：应只被 {rule} 拒，实得 {v['rungs'][0]['failed']}")

    # (3b) `object_pinned=None`（旧产物没这个字段）**不追溯判废**，否则历史数据全部读不了；
    #      但必须在 warnings 里点名，不然会被当成"已验证可复现"。
    v_none = frontier_verdict([good], **CHEAP)
    if v_none["rungs"][0]["failed"]:
        bad.append(f"旧产物缺 object_pinned 不该判废: {v_none['rungs'][0]['failed']}")
    if not any("object_pinned" in w for w in v_none["warnings"]):
        bad.append(f"缺字段必须在 warnings 里点名: {v_none['warnings']}")
    v_pin = frontier_verdict([dict(good, object_pinned=True)], **CHEAP)
    if v_pin["rungs"][0]["failed"] or any("object_pinned" in w for w in v_pin["warnings"]):
        bad.append(f"已钉死就不该再报这条: {v_pin['rungs'][0]['failed']} {v_pin['warnings']}")

    # (3c) 弹起式成功分三档：0=安静、0<flick<0.5=警告并给 grasp-verified、>=0.5=拒。
    #      实测背景（§12.11-N）：最弱那档 SAC 的 success_rate=0.333 里真抓起来的是 0/6。
    v_flick = frontier_verdict([dict(good, flick_frac=0.20,
                                     success_rate_grasp_verified=0.20)], **CHEAP)
    if v_flick["rungs"][0]["failed"]:
        bad.append(f"flick 20% 只该警告不该判废: {v_flick['rungs'][0]['failed']}")
    if not any("弹起" in w for w in v_flick["warnings"]):
        bad.append(f"flick>0 必须警告: {v_flick['warnings']}")
    v_gap = frontier_verdict([dict(good, flick_frac=0.40, sac_success=0.35,
                                   success_rate_grasp_verified=0.20)], **CHEAP)
    if not any("grasp-verified" in w for w in v_gap["warnings"]):
        bad.append(f"两个成功口径差 >= 0.05 时必须点名: {v_gap['warnings']}")
    v_zero = frontier_verdict([dict(good, flick_frac=0.0,
                                    success_rate_grasp_verified=0.35)], **CHEAP)
    if any("弹起" in w for w in v_zero["warnings"]):
        bad.append(f"flick=0 不该有弹起相关警告: {v_zero['warnings']}")
    if "metric" not in v_none["policy"] or "钉死" not in v_none["policy"]:
        bad.append(f"policy 应升级到 frontier_v2 并列出新规则: {v_none['policy']}")

    # (4) 通过的档位要被推荐；多档时推荐 frontier 最大的那档（针对性采样最有对象）。
    v = frontier_verdict([good, dict(good, half_range=0.15, frontier_frac=0.70)], **CHEAP)
    if not v["ok"] or v["recommended"]["half_range"] != 0.15:
        bad.append(f"应推荐 frontier 最大的 0.15 档: {v['reason']} / {v['recommended']}")

    # (5) 分辨率是**全局**规则：档位全过、但评测局数配不上 min_gain ⇒ 总门禁不过。
    #     这正是 run7 的真实配置（eval_episodes=50, min_gain=0.02）。
    noisy = frontier_verdict([good], eval_episodes=50, min_gain=0.02)
    if noisy["ok"] or noisy["checks"]["resolution"]["ok"]:
        bad.append(f"50 局评测配 min_gain=0.02 必须被分辨率规则拒: {noisy['reason']}")
    # (5b) 掉点容忍度是**另一半**：零容忍 + 50 局 = 真值相同时约一半概率误拒。
    #      run7 决定性臂 round 3（0.08 vs incumbent 0.14，差 0.85σ）就是这么被拒的。
    res = noisy["checks"]["resolution"]
    if res["gain_ok"] is not False or res["tol_ok"] is not False:
        bad.append(f"min_gain 与 regression_tol 两维都必须被判不合格: {res}")
    tol_only = frontier_verdict([good], eval_episodes=50, min_gain=0.30, regression_tol=0.0)
    if tol_only["ok"] or tol_only["checks"]["resolution"]["tol_ok"] is not False:
        bad.append(f"min_gain 够但零容忍掉点，仍应被拒: {tol_only['reason']}")
    if "拒绝" not in tol_only["checks"]["resolution"]["reason"]:
        bad.append(f"零容忍必须在 reason 里点名是「按噪声拒绝」: "
                   f"{tol_only['checks']['resolution']['reason']}")
    if frontier_verdict([good], eval_episodes=50, min_gain=0.30,
                        regression_tol=0.30)["checks"]["resolution"]["ok"] is not True:
        bad.append("min_gain 与 tol 都 >= MDE(50)=0.27 时分辨率应判合格")
    # (5c) 工作点必须用**实测**成功率（没有实测才退回最保守的 0.5）：
    #      MDE 随 p_base 变化（p=0.5 最坏），拿 0.5 去算一个 p=0.17 的任务会把
    #      所需评测局数高估，进而把买得起的设计判成买不起。
    res_m = frontier_verdict([good], eval_episodes=50, min_gain=0.30,
                             regression_tol=0.30)["checks"]["resolution"]
    if abs(res_m["p_base"] - 0.35) > 1e-9 or "measured" not in res_m["p_base_source"]:
        bad.append(f"p_base 应取实测 sac_success 均值 0.35: {res_m['p_base_source']}")
    if not res_m["min_detectable_effect"] <= res_m["min_detectable_effect_worst_case"] + 1e-9:
        bad.append(f"实测工作点的 MDE 不该大于闭式上界: {res_m}")
    res_f = frontier_verdict([dict(good, sac_success=None)], eval_episodes=50, min_gain=0.30,
                             regression_tol=0.30)["checks"]["resolution"]
    if abs(res_f["p_base"] - 0.5) > 1e-9 or "fallback" not in res_f["p_base_source"]:
        bad.append(f"没有策略侧实测值时应退回 0.5 并记账: {res_f['p_base_source']}")
    if noisy["rungs"][0]["ok"] is not True:
        bad.append("分辨率是全局规则，不该把单档判成不合格（否则定位不到问题在哪一层）")
    if not any("抛硬币" in w or "噪声地板" in w for w in noisy["warnings"]):
        bad.append("分辨率不过时必须在 warnings 里点名")
    if frontier_verdict([good], **CHEAP)["ok"] is not True:
        bad.append(f"评测局数与容忍度都补足后应放行: {frontier_verdict([good], **CHEAP)['reason']}")

    # (6) 本轮 Lift 实测：手写上限 ±0.03~±0.18 全 1.000、每局 ~4.8 s，
    #     位置轴不是难度旋钮 ⇒ 只有上限数据的档位一律「还不能开 A/B」。
    sweep = [{"half_range": h, "scripted_success": 1.0, "sec_per_episode": 4.8}
             for h in (0.03, 0.06, 0.09, 0.12, 0.15, 0.18)]
    v = frontier_verdict(sweep, **CHEAP)      # 分辨率/成本都给够，好让 band 成为唯一拦路规则
    if v["ok"] or v["recommended"] is not None:
        bad.append(f"只有上限数据的 Lift 阶梯不该放行: {v['reason']}")
    if any(r["failed"] != ["band"] for r in v["rungs"]):
        bad.append(f"Lift 阶梯应只卡在 band（缺策略侧数据），实得 "
                   f"{[r['failed'] for r in v['rungs']]}")
    if any("ceiling" in r["failed"] for r in v["rungs"]):
        bad.append("手写上限 1.000 不该触发 ceiling 规则")

    # (7) 成本规则要用实测每局秒数，并给出预算内的最大臂数（阶段 3 想开 6 臂，
    #     接触任务这条算术通常直接砍到 1~2 臂）。
    pricey = frontier_verdict([dict(good, sec_per_episode=30.0)], budget_sec=8 * 3600,
                              arms=6, rounds=10, episodes_per_round=8,
                              eval_episodes=50, min_gain=0.30, regression_tol=0.30)
    arms_raw = pricey["rungs"][0]["affordable_arms_raw"]
    if arms_raw is None or arms_raw > 2:
        bad.append(f"30 s/局 × (8 采集 + 50 评测) × 10 轮时预算内只养得起 1 条臂，实得 {arms_raw}")
    if "cost" not in pricey["rungs"][0]["failed"]:
        bad.append(f"6 臂在该成本下必须被 cost 规则拒: {pricey['rungs'][0]['failed']}")
    # 评测计入成本后，「加评测局数换分辨率」会直接把预算吃光：这条对立关系必须被算出来
    pricey2 = frontier_verdict([dict(good, sec_per_episode=30.0)], budget_sec=8 * 3600,
                               arms=2, rounds=10, episodes_per_round=8,
                               eval_episodes=20000, min_gain=0.02, regression_tol=0.02)
    if "cost" not in pricey2["rungs"][0]["failed"]:
        bad.append("评测 2 万局 × 30 s 必须超预算（分辨率与成本在接触任务上直接对立）")
    if not any("臂" in w for w in pricey["warnings"]):
        bad.append(f"臂数被预算砍掉时必须写进 warnings: {pricey['warnings']}")

    # (8) McNemar 已知答案（手算 + 文献口径双对齐）：
    #     b=20,c=5 -> 精确二项 p=0.004077、χ²_cc=(|20-5|-1)²/25=7.84、p=0.00511
    mc = mcnemar(20, 5)
    if abs(mc["exact_p"] - 0.004077) > 1e-5 or abs(mc["chi2_cc"] - 7.84) > 1e-9 \
            or abs(mc["chi2_p"] - 0.00511) > 1e-4:
        bad.append(f"McNemar 已知答案对不上: {mc}")
    if mcnemar(10, 10)["exact_p"] != 1.0:
        bad.append("b=c 时精确 p 必须是 1.0（双侧对称）")
    if mcnemar(0, 0)["method"] != "no_discordant" or mcnemar(0, 0)["exact_p"] != 1.0:
        bad.append("零不一致对 = 差异为 0 的直接证据，不是缺数据")
    if mcnemar(100, 80)["chi2_p"] < 0.05:      # 净差 20 题、d=0.9 ⇒ 不该显著
        bad.append(f"b=100/c=80 应不显著（p={mcnemar(100, 80)['chi2_p']}）")

    # (9) paired_gate 三态：旧的二态门禁缺的就是 inconclusive 这一态
    #     （run7 round 6 用 +0.02/p=0.31 发布、round 3 用 -0.06/p=0.34 拒绝）。
    if paired_gate(200, 30, 10)["decision"] != "publish":
        bad.append("30 vs 10 翻转（p=0.0022）应发布")
    if paired_gate(200, 10, 30)["decision"] != "reject_regression":
        bad.append("10 vs 30 翻转应判掉点")
    for b, c in [(2, 0), (0, 3), (60, 40), (10, 10)]:
        got = paired_gate(200, b, c)["decision"]
        if got != "inconclusive":
            bad.append(f"翻转 {b}/{c} 不显著，应 inconclusive，实得 {got}")
    if paired_gate(5, 3, 0)["decision"] != "inconclusive":
        bad.append("配对题数太少必须 inconclusive，不许当成显著")
    # 净差 +0.10 但 d 很大时**不显著**：这条必须钉住，否则会把配对当成万能放大镜
    if paired_gate(200, 60, 40)["mcnemar"]["exact_p"] < 0.05:
        bad.append(f"60/40 的 p 应 >= 0.05（净差 +0.10 但 d=0.5，判不出来）: "
                   f"{paired_gate(200, 60, 40)['mcnemar']}")

    check("12 接触物理门禁：MDE/所需局数/掉点容忍/McNemar 三态 + frontier_verdict 五规则",
          not bad, "; ".join(bad))


def check_stopping_and_resolution() -> None:
    """第 13 项：提前停止判据（冻结口径）+ 发布判定的分辨率审计。

    两条都是 run7 实测暴露的 harness 缺陷（§7 第 14 条 / §12.11-G）：
      · 停止判据曾用 8 局**采集**成功率，而结论用 50 局**冻结**评测 ⇒ 22496/40000 步
        就截断在爬升段，预登记阈值既没证实也没证伪；
      · `min_gain=0.02` / `regression_tol=0` 都低于 50 局评测的噪声地板（MDE≈0.22~0.28）
        ⇒ 同一条臂上既用 +0.02（p=0.31）发布，也用「50 局里翻 1 局」判掉点拒绝。
    """
    from harness.loop import HarnessLoop, LoopConfig, frozen_stop_decision

    bad: list[str] = []

    # (1) 采集满分 / 冻结不达标 -> **不许停**（这就是 run7 s0 被截断的那一幕）
    d = frozen_stop_decision({"success_rate": 0.860}, 1.000, 0.90)
    if d["stop"] or d["converged_on"] is not None:
        bad.append(f"采集 1.000 / 冻结 0.860 / 目标 0.90 不该停: {d}")
    if d["collect_success_rate"] != 1.000 or d["frozen_success_rate"] != 0.860:
        bad.append(f"两个口径都要记账: {d}")
    # (2) 采集很差 / 冻结达标 -> 该停（判据只看冻结，采集再差也不影响）
    if not frozen_stop_decision({"success_rate": 0.95}, 0.50, 0.90)["stop"]:
        bad.append("冻结 0.95 >= 目标 0.90 应停止")
    # (3) target>1.0 = 关掉提前停止（run7 决定性臂的 --target-success 1.01）
    if frozen_stop_decision({"success_rate": 1.0}, 1.0, 1.01)["stop"]:
        bad.append("target=1.01 时即使冻结 1.000 也不该停")
    # (4) 没有现任指标时不许崩、也不许当成达标
    if frozen_stop_decision(None, 1.0, 0.9)["stop"]:
        bad.append("incumbent=None 时应视为 0.0，不停")

    # (5) 分辨率审计：run7 的真实配置必须被点名（两个方向都不合格）
    loop = object.__new__(HarnessLoop)                 # 不建环境、不训练，只打这个方法
    loop.cfg = LoopConfig(eval_episodes=50, min_gain=0.02, regression_tol=0.0)
    loop.incumbent_metrics = {"success_rate": 1.00}
    loop.incumbent_scores = {"standard": {"episodes": [
        {"seed": 999 + i, "success": True} for i in range(50)]}}
    cand_scores = {"standard": {"episodes": [
        {"seed": 999 + i, "success": (i != 7)} for i in range(50)]}}   # 只翻 1 局
    audit = loop.resolution_audit({"success_rate": 0.98}, cand_scores)
    if audit["min_gain_resolvable"] or audit["regression_tol_resolvable"]:
        bad.append(f"eval 50 局 + min_gain 0.02 + tol 0 必须两维都不合格: {audit}")
    if not audit["warning"]:
        bad.append("不合格时必须给出可读告警")
    # 噪声地板随**工作点**变化：这里 p̄=0.99（贴近饱和），MDE(50)=0.055 而不是
    # 最坏情况的 0.280 —— 但仍比 min_gain=0.02 大 2.75 倍，所以判定照样不合格。
    if not (0.02 < audit["mde"] <= audit["mde_worst_case"]):
        bad.append(f"MDE 应落在 (min_gain, 最坏上界] 内: {audit}")
    if audit["episodes_needed_for_min_gain"] <= audit["eval_episodes"]:
        bad.append(f"检出 min_gain 所需的局数必须多于现有评测局数: {audit}")
    # (6) 配对参考给出旧二态门禁缺的第三态：50 局里翻 1 局 = inconclusive，不是"掉点"
    if audit["paired"]["decision"] != "inconclusive":
        bad.append(f"翻 1 局（1:0）应 inconclusive: {audit['paired']}")
    if audit["paired"]["only_inc"] != 1 or audit["paired"]["only_new"] != 0:
        bad.append(f"方向弄反了（现任成/候选败应记 only_inc）: {audit['paired']}")
    # (7) 翻得够多时要能判显著（20:2 -> publish），证明它不是一律 inconclusive
    many = {"standard": {"episodes": [
        {"seed": 999 + i, "success": i >= 20} for i in range(50)]}}
    a2 = loop.resolution_audit({"success_rate": 1.0}, many)
    if a2["paired"]["decision"] != "reject_regression":
        bad.append(f"候选只在 30/50 题上成功、现任全成 => 应判显著掉点: {a2['paired']}")
    # (8) 缺逐局记录时必须显式说明，不能静默跳过
    loop.incumbent_scores = None
    if "reason" not in loop.resolution_audit({"success_rate": 0.5}, cand_scores)["paired"]:
        bad.append("现任缺逐局记录时应写明无法配对")

    check("13 提前停止（冻结口径）+ 发布判定的分辨率审计/配对三态", not bad, "; ".join(bad))


def check_contact_repro_and_flick() -> None:
    """第 14 项：接触任务的可复现性（物体尺寸钉死）+「弹起式成功」口径 + 配对两个守卫。

    三组断言各对应本轮一个实测发现（§7 第 22~24 条 / §12.11-M/N）：
      · robosuite 的 cube 尺寸是构造期用**未播种**的 `np.random.default_rng()` 抽的
        ⇒ 每个进程评的是不同物体，跨进程"冻结评测"根本不冻结；
      · Lift 的成功判据只看高度，可以被"弹一下"满足 ⇒ 成功率必须分 grasp-verified 口径；
      · 逐题配对（McNemar）成立需要两个前提：同 seed 同题、且仿真确定性成立，
        两个前提都要有会失败的守卫，不能只在文档里声明。
    全部用合成数据，不建仿真环境（建一次 robosuite 要几十秒，自检必须秒级）。
    """
    import numpy as np

    from harness.env_factory import PINNED_OBJECT_SEED, pinned_object_rng
    from scripts.probe_contact_ceiling import classify, truth_consistency
    from scripts.probe_paired_lift_eval import identity_check, spawn_audit

    bad: list[str] = []

    # (1) 钉死：无种子调用被钉住，**带种子的调用不受影响**（否则会顺手改掉别的随机性，
    #     包括包装层 `env.rng = default_rng(seed)` 那条我们依赖的路径）
    outside_unseeded = np.random.default_rng().random(4)
    outside_seeded = np.random.default_rng(7).random(4)
    with pinned_object_rng() as pin:
        inside_pinned = np.random.default_rng().random(4)
        inside_seeded = np.random.default_rng(7).random(4)
        inside_again = np.random.default_rng().random(4)
    expect = np.random.default_rng(PINNED_OBJECT_SEED).random(4)
    if pin != PINNED_OBJECT_SEED:
        bad.append(f"pinned_object_rng 应回显种子 {PINNED_OBJECT_SEED}，实得 {pin}")
    if not np.array_equal(inside_pinned, expect):
        bad.append("无种子调用没有被钉到 PINNED_OBJECT_SEED（物体尺寸仍会每进程不同）")
    if not np.array_equal(inside_pinned, inside_again):
        bad.append("同一次上下文里两次无种子调用应给出同一条流（否则钉了个寂寞）")
    if not np.array_equal(inside_seeded, outside_seeded):
        bad.append("**带种子的调用被改写了**：会顺手改掉 env.rng 等我们依赖的随机性")
    if np.array_equal(outside_unseeded, expect):
        bad.append("对照组异常：未打补丁时无种子调用不该正好等于钉死值")
    after = np.random.default_rng().random(4)
    if np.array_equal(after, expect):
        bad.append("退出上下文后没有还原 np.random.default_rng")
    # 异常路径也要还原（建环境失败时不能把全局补丁留在进程里）
    try:
        with pinned_object_rng(123):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    if np.array_equal(np.random.default_rng().random(4), np.random.default_rng(123).random(4)):
        bad.append("上下文内抛异常后没有还原补丁（会污染后续所有随机性）")
    # 换种子必须换物体，否则"钉死"退化成"写死一个常量"，审计字段也就没意义了
    with pinned_object_rng(1):
        s1 = np.random.default_rng().random(4)
    with pinned_object_rng(2):
        s2 = np.random.default_rng().random(4)
    if np.array_equal(s1, s2):
        bad.append("不同 pin 种子给出同一条流 ⇒ 尺寸审计字段无法区分不同 cube")

    # (2) 弹起式成功：成功但没有抓取真值 ⇒ 必须单独一档，不能和"真抓起来"混计
    cal = {"lift_ok": 0.0106, "near": 0.0066}

    def track(**kw) -> dict:
        base = {"success": False, "held": False, "max_rise": 0.0, "min_xy": 0.05,
                "close_cmd_frac": 0.0, "seed": 0}
        base.update(kw)
        return base

    if classify(track(success=True, held=True), cal) != "success":
        bad.append("成功 + 有抓取真值应是 success")
    if classify(track(success=True, held=False), cal) != "success_flick":
        bad.append("成功但无抓取真值应是 success_flick（实测：16 步把 cube 弹过阈值）")
    # 失败侧的六个标签不能被这次改动带偏（回归）
    fail_cases = [
        (track(max_rise=0.05), "dropped"),                    # >= lift_ok：起来过又掉了
        (track(held=True, max_rise=0.003), "grasp_no_lift"),  # < near：夹住了但没提起来
        (track(held=True, max_rise=0.008), "lifted_below"),   # near <= rise < lift_ok：差一点
        (track(min_xy=0.09), "no_reach"),
        (track(min_xy=0.01, close_cmd_frac=0.0), "reach_no_close"),
        (track(min_xy=0.01, close_cmd_frac=0.4), "reach_no_hold"),
    ]
    for row, want in fail_cases:
        got = classify(row, cal)
        if got != want:
            bad.append(f"失败标签回归：{row} 应为 {want}，实得 {got}")

    def rows_of(specs):
        return [{"seed": i, "success": s, "held": h, "held_source": "truth(_check_grasp)"}
                for i, (s, h) in enumerate(specs)]

    tc_ok = truth_consistency(rows_of([(True, True), (True, True), (False, False)]))
    if tc_ok["status"] != "ok" or tc_ok["flick_frac"] != 0.0:
        bad.append(f"全部成功都有抓取真值时应为 ok/flick_frac=0: {tc_ok}")
    if tc_ok["success_rate_grasp_verified"] != round(2 / 3, 4):
        bad.append(f"grasp-verified 成功率算错: {tc_ok['success_rate_grasp_verified']}")
    tc_warn = truth_consistency(rows_of([(True, True), (True, True), (True, False)]))
    if tc_warn["status"] != "warn" or tc_warn["consistent"] is not True:
        bad.append(f"1/3 弹起应是 warn 且失败标签仍可信: {tc_warn['status']}")
    tc_fail = truth_consistency(rows_of([(True, False), (True, False)]))
    if tc_fail["status"] != "fail" or tc_fail["consistent"] is not False:
        bad.append(f"2/2 弹起应判 fail（成功率不能当学习信号）: {tc_fail['status']}")
    if tc_fail["success_rate_grasp_verified"] != 0.0:
        bad.append("全弹起时 grasp-verified 成功率必须是 0（实测那档 SAC 就是 0/6）")
    tc_none = truth_consistency(rows_of([(False, False), (False, True)]))
    if tc_none["status"] != "ok" or tc_none["n_success"] != 0:
        bad.append(f"没有成功局时不该报警: {tc_none}")

    # (3) 配对守卫一：同 seed 必须同题（跨臂出生点逐位相同），差一点都要判无效
    good = {"a": [{"seed": 1, "success": True, "spawn_xy": [0.01, 0.02]}],
            "b": [{"seed": 1, "success": False, "spawn_xy": [0.01, 0.02]}]}
    aud = spawn_audit(good)
    if not aud["pairing_valid"] or aud["max_abs_diff"] != 0.0:
        bad.append(f"出生点逐位相同应判配对有效: {aud}")
    shifted = {"a": [{"seed": 1, "success": True, "spawn_xy": [0.01, 0.02]}],
               "b": [{"seed": 1, "success": False, "spawn_xy": [0.0101, 0.02]}]}
    aud2 = spawn_audit(shifted)
    if aud2["pairing_valid"] or not aud2["examples"]:
        bad.append(f"出生点差 1e-4 也必须判配对无效并留证: {aud2}")
    single = {"a": [{"seed": 1, "success": True, "spawn_xy": [0.01, 0.02]}]}
    if spawn_audit(single)["pairing_valid"]:
        bad.append("只有一条臂时无从配对，不该判有效")

    # (4) 配对守卫二：恒等式 d − |δ| = 2·min(b,c)/n（把 d 拆成净差与双向翻转）
    one_sided = {"n_pairs": 500, "only_a": 0, "only_b": 13, "delta": 0.026,
                 "discordant_rate": 0.026}
    idc = identity_check(one_sided)
    if not idc["identity_ok"] or idc["excess_over_floor"] != 0.0:
        bad.append(f"13:0 全同向应落在硬下界（excess=0）: {idc}")
    two_sided = {"n_pairs": 200, "only_a": 10, "only_b": 20, "delta": 0.05,
                 "discordant_rate": 0.15}
    idc2 = identity_check(two_sided)
    if not idc2["identity_ok"] or abs(idc2["excess_over_floor"] - 0.10) > 2e-3:
        bad.append(f"10:20 双向翻转的 excess 应是 2*10/200=0.10: {idc2}")
    broken = {"n_pairs": 100, "only_a": 10, "only_b": 10, "delta": 0.0,
              "discordant_rate": 0.50}
    if identity_check(broken)["identity_ok"]:
        bad.append("恒等式被破坏时必须报错，否则 d 的拆解不可信")

    check("14 接触任务可复现性（物体尺寸钉死）+ 弹起式成功口径 + 配对两个守卫",
          not bad, "; ".join(bad))


def check_three_state_gate() -> None:
    """第 15 项：三态发布门禁 `registry/publish.py::decide_paired`（K12）。

    每一项都对应一个**实际发生过**的误判，不是假想用例：
      · run7 决定性臂 round 6：0.98 → 1.00（50 局只翻 1 局，McNemar p=1.0）被 legacy 发布；
      · run7 决定性臂 rounds 2/3：0.14 → 0.08（差 3 局 ≈ 0.85σ）被 legacy 判「旧任务掉点」拒绝。
    两个方向都在量噪声，而日志上毫无异常（§12.11-G）。reach r5 vs r6 的配对复算
    （§12.11-L）证明差异本身是真的（n=500 时 13:0、p=0.0002），所以当时的正确输出是第三态
    「测不出来，去买局数」，而不是发布或掉点。

    还要守住一条容易读错的语义：「显著更好但不足 min_gain」记 `reject`（判定清楚了：
    不值得换版本），但 `direction` 必须是 `better` —— 否则自进化会把它当成"这个方向失败了"。
    """
    from harness.loop import LoopConfig
    from registry.publish import (GATE_STATS_LEGACY, GATE_STATS_PAIRED, decide, decide_paired)

    bad: list[str] = []

    def gate(cand, inc, paired=None, n=50, **kw):
        g = decide_paired(cand, inc, paired=paired, eval_episodes=n, **kw)
        if g["ok"] != (g["decision"] == "publish"):
            bad.append(f"ok 必须等价于 decision==publish: {g['decision']} / ok={g['ok']}")
        if g["decision"] not in ("publish", "reject", "inconclusive"):
            bad.append(f"decision 只能三态，收到 {g['decision']!r}")
        if not g["reasons"]:
            bad.append("任何判定都必须给出人类可读理由")
        return g

    def flips(only_new: int, only_inc: int, p: float, n: int = 50) -> dict:
        """按 `resolution_audit()['paired']` 的形状造一份配对记录。"""
        return {"n_pairs": n, "only_new": only_new, "only_inc": only_inc,
                "mcnemar": {"exact_p": p}, "decision": "whatever"}

    # (1) run7 round 6 那一幕：+0.02、50 局翻 1 局 ⇒ 三态必须 inconclusive，
    #     而 legacy 同输入是"发布"。两者不同，正是第三态存在的理由。
    cand, inc = {"success_rate": 1.00}, {"success_rate": 0.98}
    g = gate(cand, inc, paired=flips(1, 0, 1.0), min_gain=0.02, regression_tol=0.0)
    if g["decision"] != "inconclusive" or g["reason_code"] != "unresolvable":
        bad.append(f"翻 1 局（p=1.0）应 inconclusive/unresolvable: {g['decision']}/{g['reason_code']}")
    if decide(cand, inc, min_gain=0.02, regression_tol=0.0)[0] is not True:
        bad.append("前提变了：legacy 在这一幕本来是**发布**，用例要跟着改")

    # (2) run7 rounds 2/3 那一幕：掉 3 局、p=0.24 ⇒ 不许判掉点，只能 inconclusive
    g = gate({"success_rate": 0.08}, {"success_rate": 0.14}, paired=flips(0, 3, 0.241),
             min_gain=0.02, regression_tol=0.0)
    if g["decision"] != "inconclusive":
        bad.append(f"3 局之差（p=0.241）不该判掉点: {g['decision']}/{g['reason_code']}")
    if g["direction"] == "worse":
        bad.append(f"不显著时 direction 不能是 worse（会被读成'这个方向失败'）: {g}")
    if decide({"success_rate": 0.08}, {"success_rate": 0.14},
              min_gain=0.02, regression_tol=0.0)[0] is not False:
        bad.append("前提变了：legacy 在这一幕本来是**拒绝（掉点）**")

    # (3) 显著更好且幅度够 ⇒ publish（reach r5 vs r6 在 n=500 上的真实数字）
    g = gate({"success_rate": 1.000}, {"success_rate": 0.974},
             paired=flips(13, 0, 0.000244, n=500), n=500, min_gain=0.02)
    if g["decision"] != "publish" or g["direction"] != "better" or not g["ok"]:
        bad.append(f"13:0、p=0.0002、δ=+0.026>=min_gain 应 publish: {g}")

    # (4) 方向敏感性（变异测试）：同样显著，翻转方向反过来就必须变成掉点拒绝。
    #     角色接反是历史上真出过的错（`compare()` 的 docstring 里记着），这一条专门抓它。
    g_worse = gate({"success_rate": 0.30}, {"success_rate": 1.00},
                   paired=flips(0, 20, 0.0000034), min_gain=0.02, regression_tol=0.0)
    if g_worse["decision"] != "reject" or g_worse["reason_code"] != "regression" \
            or g_worse["direction"] != "worse":
        bad.append(f"20:0 反方向应 reject/regression/worse: {g_worse}")

    # (5) 显著更好但不足 min_gain ⇒ reject，且 direction 必须仍是 better
    g = gate({"success_rate": 0.240}, {"success_rate": 0.093},
             paired=flips(34, 12, 0.0016, n=150), n=150, min_gain=0.20, regression_tol=0.20)
    if g["decision"] != "reject" or g["reason_code"] != "real_gain_below_min_gain":
        bad.append(f"δ=+0.147 < min_gain=0.20 应 reject/real_gain_below_min_gain: {g}")
    if g["direction"] != "better":
        bad.append(f"这种情况 direction 必须是 better，否则会被读成'变差': {g['direction']}")
    # 同一组数据把 min_gain 放回 0.02 就必须发布 ⇒ 判的是幅度阈值，不是显著性
    if gate({"success_rate": 0.240}, {"success_rate": 0.093},
            paired=flips(34, 12, 0.0016, n=150), n=150,
            min_gain=0.02)["decision"] != "publish":
        bad.append("min_gain=0.02 时同一组数据应 publish")

    # (6) 硬失败：env_hash 不一致 ⇒ 即使配对显著更好也 reject（不可比 ≠ 测不准）
    g = gate({"success_rate": 0.9}, {"success_rate": 0.1}, paired=flips(80, 0, 1e-20, n=100),
             n=100, min_gain=0.02, candidate_env_hash="A", incumbent_env_hash="B")
    if g["decision"] != "reject" or g["reason_code"] != "env_mismatch" or not g.get("hard"):
        bad.append(f"环境不一致必须硬拒绝: {g}")

    # (7) 绝对下限
    g = gate({"success_rate": 0.05}, {"success_rate": 0.04}, paired=flips(3, 1, 0.01),
             min_success=0.10, min_gain=0.02)
    if g["decision"] != "reject" or g["reason_code"] != "below_min_success":
        bad.append(f"低于绝对下限应 reject/below_min_success: {g}")

    # (8) 没有逐局记录 ⇒ 回退到 MDE 口径，且同样能给出第三态
    g = gate({"success_rate": 0.20}, {"success_rate": 0.14}, paired=None, n=50, min_gain=0.02)
    if g["decision"] != "inconclusive" or (g.get("fallback") or {}).get("kind") != "mde_unpaired":
        bad.append(f"δ=+0.06 < MDE(50) 且无配对记录 ⇒ inconclusive + 回退口径: {g}")
    g = gate({"success_rate": 0.80}, {"success_rate": 0.20}, paired=None, n=50, min_gain=0.02)
    if g["decision"] != "publish":
        bad.append(f"回退路径下 δ=+0.60（远超 MDE）应 publish: {g}")
    if decide({"success_rate": 0.80}, {"success_rate": 0.20}, min_gain=0.02)[0] is not True:
        bad.append("回退路径在**可分辨**情形下必须与 legacy 同结论（否则历史 run 不可比）")

    # (9) 严酷探针：可分辨的掉点要拦；分辨不出的掉点不许当拒绝理由
    g = gate({"success_rate": 0.60, "harsh_success_rate": 0.20},
             {"success_rate": 0.30, "harsh_success_rate": 0.50},
             paired=flips(60, 15, 1e-9, n=150), n=150, min_gain=0.02)
    if g["decision"] != "reject" or g["reason_code"] != "harsh_regression":
        bad.append(f"严酷探针 0.50→0.20 应 reject/harsh_regression: {g}")
    g = gate({"success_rate": 0.60, "harsh_success_rate": 0.48},
             {"success_rate": 0.30, "harsh_success_rate": 0.50},
             paired=flips(60, 15, 1e-9, n=150), n=150, min_gain=0.02)
    if g["decision"] != "publish":
        bad.append(f"严酷探针只掉 0.02（< MDE）不该拦发布: {g['decision']}/{g['reason_code']}")
    if not any("分辨不出" in r for r in g["reasons"]):
        bad.append("分辨不出的严酷掉点必须在理由里说明，不能静默忽略")

    # (10) 首次发布（registry 里还没有现任）
    g = gate({"success_rate": 0.30}, None, min_success=0.10, min_gain=0.02)
    if g["decision"] != "publish" or g["reason_code"] != "first_publish":
        bad.append(f"无现任且过绝对下限应 publish/first_publish: {g}")

    # (11) 配对题数太少（`paired_gate` 会给 mcnemar=None）不许崩，且必须落到 inconclusive
    g = gate({"success_rate": 0.6}, {"success_rate": 0.4},
             paired={"n_pairs": 5, "only_new": 3, "only_inc": 1, "mcnemar": None},
             n=5, min_gain=0.02)
    if g["decision"] != "inconclusive":
        bad.append(f"5 对（< min_pairs）应 inconclusive: {g}")

    # (12) 开关默认值：历史可比性靠它。默认必须是 legacy，非法值必须被 validate 拦住。
    if LoopConfig().gate_stats != GATE_STATS_LEGACY:
        bad.append(f"gate_stats 默认必须是 legacy（否则历史 run 不可比）: {LoopConfig().gate_stats}")
    if GATE_STATS_PAIRED != "paired_v1":
        bad.append("paired_v1 是写进 journal 的口径名，改名会让旧产物读不出来")
    try:
        LoopConfig(gate_stats="nope").validate()
        bad.append("非法 gate_stats 必须被 validate 拒绝")
    except ValueError:
        pass

    # (13) 配对必须**真的有数据**。`score_skill` 曾把逐局记录整个剥掉，于是
    #      `resolution_audit` 的配对分支永远拿到 0 局、静默退化成「无法配对」，
    #      而三态门禁会跟着退回未配对口径 —— 这条断言就是防它再断一次（§7 第 26 条）。
    from harness.loop import HarnessLoop
    from registry.publish import score_skill
    from skills.reach_skills import RandomSkill

    env_kwargs = {"max_steps": 20, "goal_radius": 0.03}
    scores = score_skill(RandomSkill(seed=0), env_kwargs, n_episodes=6, seed=999, harsh=False)
    outs = (scores.get("standard") or {}).get("episode_outcomes") or []
    if len(outs) != 6 or not all({"seed", "success"} <= set(r) for r in outs):
        bad.append(f"score_skill 必须留下 6 条 (seed, success) 逐局记录，实得 {len(outs)}: {outs[:2]}")
    if len({r["seed"] for r in outs}) != len(outs):
        bad.append(f"逐局记录的 seed 必须唯一，否则配的是不同的题: {outs}")
    loop = object.__new__(HarnessLoop)                 # 不建环境、不训练，只打这个方法
    loop.cfg = LoopConfig(eval_episodes=6, min_gain=0.02, regression_tol=0.0)
    loop.incumbent_metrics = {"success_rate": 0.0}
    loop.incumbent_scores = scores
    paired = loop.resolution_audit({"success_rate": 0.0}, scores).get("paired") or {}
    if paired.get("n_pairs") != 6:
        bad.append(f"同一份逐局记录必须能配出 6 对，而不是走「无法配对」: {paired}")
    # 同一份记录自己比自己 ⇒ 零翻转，三态必须是 inconclusive（不能因为 p=1.0 就发布）
    g = gate({"success_rate": 0.0}, {"success_rate": 0.0}, paired=paired, n=6, min_gain=0.02)
    if g["decision"] != "inconclusive":
        bad.append(f"自比零翻转应 inconclusive: {g['decision']}/{g['reason_code']}")

    check("15 三态发布门禁（decide_paired）：run7 两个误判 ⇒ inconclusive，方向/幅度/硬失败分开",
          not bad, "; ".join(bad))


def check_contact_migration() -> None:
    """第 16 项：接触探针迁移到 PickPlace（K11 前置 + 放置段真值 + 双口径门禁）。

    每一项都对应本轮**实测到的一个静默错误**，不是假想用例：
      · PickPlace 的 `placement_initializer` 是 `SequentialCompositeSampler`，给它自己设
        `rng` / `x_range` 都**不报错也不生效**（`sample()` 只遍历子 sampler）。实测同 seed
        三次 reset 给出三个出生点；改播种 5 个子 sampler 后三次逐位相同
        （`runs/infra/smoke_probe_pickplace_2ep.json` 的 seeding_check vs seeding_legacy_check）。
      · robosuite 1.5 的 PickPlace **没有** `.can` 属性（物体在 `.objects[object_id]`），
        旧探针按 `getattr(inner,"can")` 取 ⇒ 几何审计全 None、`_check_grasp` 真值静默退回
        宽度启发式（就是「弹一下算成功」那个误判源头）。
      · 旧探针的 pickplace 手写控制器读 `inner.bin_poses` / `inner.target_bin`，两个都不存在
        ⇒ AttributeError（这条分支从没跑通过）。
      · 标定后重打标签的 `classify(row, cal)` 漏传 task ⇒ pickplace 的失败被贴成 Lift 标签
        （`lift_no_carry` 变成 `dropped`），据此选修法会全错。
      · `calibrate_rise` 的**标定量**同样必须随任务变：PickPlace 成功那一刻 can 坐在篮底，
        `rise_at_success` 实测最小 +0.0001 ⇒ `lift_ok=1e-4`，于是「真抓住但只离桌 5 mm」的局
        被贴成 `lift_no_carry`（搬运段），而真相是 `grasp_no_lift`（力/姿态段）—— 两个标签
        指向相反的修法。改按成功局 `max_rise` 标定（实测 min=0.0816 ⇒ lift_ok=0.0653）。
      · `PickPlaceCan._check_success()` 是**合取**：can 在篮筐象限内 **且** 末端已退开
        （`r_reach<0.6`）。只报 success 就分不清「没放进去」和「放进去了没退开」。

    全部用合成对象，不建仿真环境（口径与第 14/15 项一致：自检必须秒级）。
    真环境的证据在探针产物里：`verify_seeding`（3 次逐位相同）+ `verify_seeding_legacy`
    （旧写法不可复现）+ Lift 回归（seed 1000~1003 出生点与历史产物逐位一致）。
    """
    import collections

    import numpy as np

    from harness import env_factory as ef
    from registry.publish import (SUCCESS_RATE, SUCCESS_RATE_GRASP, contact_bundle_from_probe,
                                  decide_paired)
    from scripts.probe_contact_ceiling import (REACH_XY, calibrate_rise, classify,
                                              place_funnel)

    bad: list[str] = []
    cal = {"lift_ok": 0.04, "near": 0.02}

    # ---- 合成环境：Lift 风格（叶子即 initializer）与 PickPlace 风格（composite）--------
    class Leaf:
        def __init__(self, name, objs, x_range=(-0.03, 0.03)):
            self.name, self.mujoco_objects = name, list(objs)
            self.x_range, self.y_range, self.rng = list(x_range), list(x_range), None

    class Obj:
        def __init__(self, name):
            self.name, self.root_body = name, name
            self.size, self.bottom_offset = [0.02] * 3, [0.0, 0.0, -0.02]
            self.horizontal_radius, self.density = [0.03], 1000.0

    class Composite:
        def __init__(self, leaves):
            self.samplers = collections.OrderedDict((leaf.name, leaf) for leaf in leaves)
            self.rng = "SENTINEL"          # 若被改动，说明实现找错了对象

    class Inner:
        pass

    class Wrap:
        def __init__(self, inner):
            self._env = inner

    cube = Obj("cube")
    lift_inner = Inner()
    lift_inner.cube = cube
    lift_leaf = Leaf("UniformRandomSampler", [cube])
    lift_inner.placement_initializer = lift_leaf
    lift_env = Wrap(lift_inner)

    can = Obj("Can")
    others = [Obj(n) for n in ("Milk", "Bread", "Cereal")]
    pp_inner = Inner()
    pp_inner.objects = others + [can]      # object_id=3 -> Can（与 PickPlaceCan 一致）
    pp_inner.object_id = 3
    pp_inner.single_object_mode, pp_inner.obj_to_use = 2, "Can"
    collision = Leaf("CollisionObjectSampler", others + [can], (-0.145, 0.145))
    visuals = [Leaf(f"Visual{o.name}ObjectSampler", [o], (0.5, 0.5)) for o in others]
    pp_composite = Composite([collision] + visuals +
                             [Leaf("VisualCanObjectSampler", [Obj("VisualCan")], (0.5, 0.5))])
    pp_inner.placement_initializer = pp_composite
    pp_inner.bin_size, pp_inner.bin1_pos = [0.39, 0.49, 0.82], [0.1, -0.25, 0.8]
    pp_inner.bin2_pos = [0.1, 0.28, 0.8]
    pp_inner.target_bin_placements = np.zeros((4, 3))
    pp_inner.target_bin_placements[3] = [0.1975, 0.4025, 0.8]
    pp_env = Wrap(pp_inner)
    # 诱饵：故意挂一个**指向视觉物体**的 `.can`。真实 robosuite 1.5 没有这个属性，
    # 但只要有（或将来加上、或某个 fork 里有），`getattr(inner,"can")` 这种写法就会
    # 拿到错的对象且不报错 —— 几何审计与 `_check_grasp` 真值会静默指向视觉体。
    pp_inner.can = Obj("VisualCan")

    # ---- (1) 物体解析：`.can` 不存在这件事必须被兜住 ----------------------------------
    if ef.contact_object(lift_env, "lift") is not cube:
        bad.append("lift 应解析到 inner.cube")
    if ef.contact_object(pp_env, "pickplace") is not can:
        bad.append("pickplace 应解析到 objects[object_id]，不能被同名诱饵属性带偏"
                   "（拿到 VisualCan 就意味着几何/抓取真值全指向视觉体）")
    if ef.contact_object_geom(pp_env, "pickplace")["object"] != "Can":
        bad.append("几何审计必须记真实操作对象 Can，而不是 VisualCan")
    empty = Wrap(Inner())
    try:
        ef.contact_object(empty, "pickplace")
        bad.append("既无 cube 也无 objects 时必须报错，不能静默返回 None")
    except RuntimeError:
        pass
    geom_pp = ef.contact_object_geom(pp_env, "pickplace", 20260923)
    for key in ("object", "bin_size", "bin2_pos", "target_bin_center", "object_id"):
        if geom_pp.get(key) is None:
            bad.append(f"pickplace 几何审计缺 {key}（跨 run 比较前要先能核对是不是同一个物体/篮位）")
    if geom_pp.get("object") != "Can":
        bad.append(f"几何审计应记 Can，实得 {geom_pp.get('object')}")

    # ---- (2) 叶子播种：composite 的 rng 不许被动，叶子必须全播种 ----------------------
    n = ef.seed_placement(pp_env, 1000)
    if n != 5:
        bad.append(f"pickplace 应播种 5 个叶子 sampler，实得 {n}")
    if any(leaf.rng is None for leaf in [collision] + visuals):
        bad.append("有叶子没被播种 ⇒ 出生点仍不可复现")
    if pp_composite.rng != "SENTINEL":
        bad.append("实现去改了 composite.rng（那是静默无效的旧写法，说明找错对象了）")
    draws = {leaf.name: leaf.rng.random(3).tolist() for leaf in [collision] + visuals}
    ef.seed_placement(pp_env, 1000)
    draws2 = {leaf.name: leaf.rng.random(3).tolist() for leaf in [collision] + visuals}
    if draws != draws2:
        bad.append("同 seed 两次播种后抽样序列不同 ⇒ 出题不可复现")
    # Lift 单叶子必须与历史写法 `pi.rng = default_rng(seed)` **逐位一致**（否则历史产物作废）
    ef.seed_placement(lift_env, 7)
    legacy = np.random.default_rng(7).random(4).tolist()
    if lift_leaf.rng.random(4).tolist() != legacy:
        bad.append("lift 的单叶子播种与历史写法不逐位一致 ⇒ paired_lift 那批数字全部作废")
    # 变异：旧写法（只给 composite 设 rng）必须**不能**让叶子可复现
    pp_composite.rng = np.random.default_rng(1000)
    before = collision.rng.random(3).tolist()
    pp_composite.rng = np.random.default_rng(1000)
    if collision.rng.random(3).tolist() == before:
        bad.append("变异未被抓到：只播种 composite 竟然也能复现 ⇒ 用例失去意义")

    # ---- (3) 出生盒子只改拥有该物体的叶子 -------------------------------------------
    changed = ef.set_spawn_half_range(pp_env, 0.06, "pickplace")
    if changed != 1:
        bad.append(f"应只改 1 个叶子（拥有 Can 的碰撞 sampler），实得 {changed}")
    if collision.x_range != [-0.06, 0.06]:
        bad.append(f"碰撞 sampler 的 x_range 没被改: {collision.x_range}")
    if any(leaf.x_range != [0.5, 0.5] for leaf in visuals):
        bad.append("视觉物体的定点 sampler 被顺手改了（它们的范围是刻意的退化值）")
    if ef.set_spawn_half_range(pp_env, None, "pickplace") != 0:
        bad.append("half_range=None 应是 no-op")
    ef.set_spawn_half_range(lift_env, 0.05, "lift")
    if lift_leaf.x_range != [-0.05, 0.05]:
        bad.append(f"lift 的出生盒子没被改: {lift_leaf.x_range}")

    # ---- (4) 放置段标签阶梯 + Lift 口径回归 ------------------------------------------
    def track(**kw):
        base = {"success": False, "held": False, "max_rise": 0.0, "min_xy": 0.001,
                "close_cmd_frac": 0.5, "ever_in_bin": False, "ever_above_bin": False}
        base.update(kw)
        return base

    ladder = [
        (track(success=True, held=True), "success", "success"),
        (track(success=True, held=False), "success_flick", "success_flick"),
        (track(ever_in_bin=True, held=True, max_rise=0.09), "in_bin_no_success", "dropped"),
        (track(ever_above_bin=True, held=True, max_rise=0.09), "above_bin_no_drop", "dropped"),
        (track(held=True, max_rise=0.09), "lift_no_carry", "dropped"),
        (track(held=True, max_rise=0.03), "grasp_no_lift", "lifted_below"),
        # 未真抓住时，即使物体被弹得很高，pickplace 也只能落到接近段标签：
        # 「搬运段失败」的前提是**真抓住过**，否则会把「从没抓起来」误诊成「搬不过去」。
        (track(held=False, max_rise=0.09), "reach_no_hold", "dropped"),
        (track(min_xy=0.2), "no_reach", "no_reach"),
        (track(close_cmd_frac=0.0), "reach_no_close", "reach_no_close"),
        (track(), "reach_no_hold", "reach_no_hold"),
    ]
    for tr, want_pp, want_lift in ladder:
        got_pp = classify(dict(tr), cal, "pickplace")
        got_lift = classify(dict(tr), cal, "lift")
        if got_lift != want_lift:
            bad.append(f"Lift 口径回归被破坏: {tr} -> {got_lift}，应为 {want_lift}")
        if got_pp != want_pp:
            bad.append(f"pickplace 标签阶梯不对: {tr} -> {got_pp}，应为 {want_pp}")
        say(f"      pickplace {got_pp:18s} | lift {got_lift}")
    # 优先级：进过篮压倒一切（哪怕同时 held 且 rise 很大）
    if classify(track(ever_in_bin=True, ever_above_bin=True, held=True, max_rise=0.2),
                cal, "pickplace") != "in_bin_no_success":
        bad.append("ever_in_bin 必须是最高优先级的失败标签")
    # 变异：漏传 task（本轮真实踩到的 bug）必须让三个新标签全部消失
    for tr, want_pp, _ in ladder:
        if want_pp in ("in_bin_no_success", "above_bin_no_drop", "lift_no_carry"):
            if classify(dict(tr), cal) == want_pp:
                bad.append(f"变异未被抓到：不传 task 也能得到 {want_pp}（说明用例区分不了口径）")

    # ---- (5) 放置段漏斗的三种判定 ----------------------------------------------------
    rows_none = [dict(track(), seed=i) for i in range(4)]
    f = place_funnel(rows_none, "pickplace")
    if "能力问题" not in f["verdict"] or f["ever_in_bin"] != 0:
        bad.append(f"从没进篮必须判成能力问题: {f['verdict'][:40]}")
    rows_bin = [dict(track(ever_in_bin=True, ever_above_bin=True, held=True,
                           min_r_reach_in_bin=0.9, steps_in_bin=5, min_bin_dist=0.01),
                     seed=i) for i in range(4)]
    f = place_funnel(rows_bin, "pickplace")
    if "判据第二半" not in f["verdict"] or f["blocked_by_reach_seeds"] != [0, 1, 2, 3]:
        bad.append(f"进篮却 0 成功必须指向 r_reach 判据: {f['verdict'][:60]} / {f['blocked_by_reach_seeds']}")
    rows_mix = rows_bin[:1] + [dict(track(success=True, held=True, ever_in_bin=True,
                                         ever_above_bin=True, min_r_reach_in_bin=0.55,
                                         steps_in_bin=20, min_bin_dist=0.002), seed=9)]
    f = place_funnel(rows_mix, "pickplace")
    if f["success"] != 1 or f["ever_in_bin"] != 2 or "两个口径" not in f["verdict"]:
        bad.append(f"混合情形的漏斗/判定不对: {f}")
    if place_funnel(rows_none, "lift").get("applicable") is not False:
        bad.append("lift 上放置段漏斗应标 applicable=False（没有篮筐）")

    # ---- (6) 双口径 bundle：逐局记录必须跟着被判口径走 -------------------------------
    probe_rows = [{"seed": 1, "success": True, "held": True, "success_grasp": True,
                   "label": "success"},
                  {"seed": 2, "success": True, "held": False, "success_grasp": False,
                   "label": "success_flick"},
                  {"seed": 3, "success": False, "held": True, "success_grasp": False,
                   "label": "lift_no_carry"},
                  {"seed": 4, "success": False, "held": False, "success_grasp": False,
                   "label": "no_reach"}]
    b_raw = contact_bundle_from_probe(probe_rows)
    b_gv = contact_bundle_from_probe(probe_rows, success_key=SUCCESS_RATE_GRASP)
    if (b_raw["success_rate"], b_raw[SUCCESS_RATE_GRASP], b_raw["flick_frac"]) != (0.5, 0.25, 0.5):
        bad.append(f"bundle 两个口径算错: {b_raw['success_rate']}/{b_raw[SUCCESS_RATE_GRASP]}/"
                   f"{b_raw['flick_frac']}")
    if [o["success"] for o in b_raw["episode_outcomes"]] != [True, True, False, False]:
        bad.append("未校验口径的逐局真值不对（配对会跟着错）")
    if [o["success"] for o in b_gv["episode_outcomes"]] != [True, False, False, False]:
        bad.append("grasp-verified 口径下 seed2（弹一下）必须记为失败")
    if b_gv["episode_outcomes"][1]["success_raw"] is not True:
        bad.append("原始口径必须留档，否则事后无法审计 flick")

    # ---- (7) 门禁：flick 硬拦 / 缺口径硬拦 / legacy 回归 -----------------------------
    inc = {"success_rate": 0.0, SUCCESS_RATE_GRASP: 0.0}
    g = decide_paired(b_raw, inc, eval_episodes=4)
    if (g["decision"], g["reason_code"], g["direction"]) != \
            ("reject", "metric_flick_contaminated", "unknown"):
        bad.append(f"flick_frac=0.500（Lift 臂 a 的实测值）必须硬拦: {g['decision']}/{g['reason_code']}")
    if not g.get("hard"):
        bad.append("指标不可用属于「不能比」，必须走 hard 通道而不是 inconclusive")
    mild = dict(b_raw, flick_frac=0.2)
    if decide_paired(mild, inc, eval_episodes=4)["reason_code"] == "metric_flick_contaminated":
        bad.append("flick_frac=0.2 不该被硬拦（阈值是 0.5，别把 warn 档当 fail 档）")
    g = decide_paired({"success_rate": 0.5}, inc, eval_episodes=4,
                      require_grasp_verified=True)
    if g["reason_code"] != "missing_grasp_verified":
        bad.append(f"require_grasp_verified 缺口径应硬拒: {g['reason_code']}")
    g = decide_paired({"success_rate": 0.5}, inc, eval_episodes=4,
                      success_key=SUCCESS_RATE_GRASP)
    if g["reason_code"] != "missing_metric":
        bad.append(f"候选缺被判口径不许静默按 0.0 判: {g['reason_code']}")
    g = decide_paired(b_gv, {"success_rate": 0.0}, eval_episodes=4,
                      success_key=SUCCESS_RATE_GRASP)
    if g["reason_code"] != "missing_metric":
        bad.append(f"现任缺被判口径 = 两边口径不一致，不可比: {g['reason_code']}")
    # legacy 回归：不传新参数 == 显式传 success_rate（reach 历史行为逐字不变）
    cand = {"success_rate": 1.0, "episode_outcomes": [{"seed": i, "success": i < 10}
                                                      for i in range(10)]}
    inc2 = {"success_rate": 0.6, "episode_outcomes": [{"seed": i, "success": i < 6}
                                                      for i in range(10)]}
    paired = {"n_pairs": 10, "only_new": 4, "only_inc": 0,
              "mcnemar": {"exact_p": 0.0002}}
    a = decide_paired(cand, inc2, paired=paired, eval_episodes=10, min_gain=0.02)
    b = decide_paired(cand, inc2, paired=paired, eval_episodes=10, min_gain=0.02,
                      success_key=SUCCESS_RATE)
    if {k: a[k] for k in ("decision", "reason_code", "direction", "delta")} != \
       {k: b[k] for k in ("decision", "reason_code", "direction", "delta")}:
        bad.append(f"legacy 口径被改动: {a['decision']}/{a['reason_code']} vs "
                   f"{b['decision']}/{b['reason_code']}")
    if a["decision"] != "publish":
        bad.append(f"前提变了：4:0 翻转、p=0.0002、δ=+0.4 应发布，实得 {a['decision']}")
    if a.get("success_key") != SUCCESS_RATE:
        bad.append("判定产物必须写清用了哪个口径，否则事后无法复算")

    # ---- (8) LoopConfig 默认值必须是 legacy（历史 run 可比） -------------------------
    from harness.loop import LoopConfig

    cfg = LoopConfig(mode="diagnosed", budget_steps=8000, steps_per_round=4000)
    if cfg.success_metric != SUCCESS_RATE or cfg.require_grasp_verified is not False:
        bad.append(f"LoopConfig 默认口径变了: {cfg.success_metric}/{cfg.require_grasp_verified}")
    try:
        LoopConfig(mode="diagnosed", budget_steps=8000, steps_per_round=4000,
                   success_metric="tasks_done").validate()
        bad.append("非法 success_metric 必须被 validate 拦下")
    except ValueError:
        pass

    # ---- (9) 门禁输入链：规则写了、输入永远缺 = 规则从没触发过（§7 第 26 条同类断链）----
    # 本轮实测到两处：`report_contact_gate.rung_from` 与探针自己的 rung 都没把
    # object_pinned / object_geom / flick_frac / success_rate_grasp_verified 交出去，
    # 于是「未钉死 ⇒ 整档作废」「弹起式成功 ⇒ 指标不可用」两条规则形同虚设，
    # 反而一直报「产物没有 object_geom」这个**假**警告（真产物里明明有）。
    from harness.sampling_design import frontier_verdict
    from scripts.report_contact_gate import rung_from

    doc = {"spawn_range": None,
           "object_geom": {"pinned_object_seed": 20260923, "object": "Can",
                           "body_mass_kg": 0.016},
           "scripted": {"success_rate": 0.719, "flick_frac": 0.0, "episodes": []},
           "sac": {"success_rate": 0.0, "success_rate_grasp_verified": 0.0,
                   "flick_frac": 0.5, "episodes": [{"wall_sec": 4.7, "steps": 400}]},
           "paired": {"frontier_frac": 0.719, "too_hard_frac": 0.281},
           "seeding_verified": True}
    rung = rung_from(doc)
    for key in ("object_pinned", "object_geom", "flick_frac", "success_rate_grasp_verified"):
        if rung.get(key) is None:
            bad.append(f"rung_from 没把 {key} 交出门禁 ⇒ 对应规则永远不会触发")
    if rung.get("object_pinned") is not True:
        bad.append(f"已钉死物体的产物必须报 object_pinned=True，实得 {rung.get('object_pinned')}"
                   "（否则真产物会被误报成「不可比」）")
    if rung.get("flick_frac") != 0.5:
        bad.append("flick_frac 必须取自 SAC 臂（band/metric 规则针对策略侧成功率）")
    gate_kw = {"budget_sec": 8 * 3600, "arms": 2, "rounds": 5, "episodes_per_round": 8,
               "train_sec_per_round": 80, "eval_episodes": 120, "eval_every": 5,
               "min_gain": 0.2, "regression_tol": 0.2}
    v_ok = frontier_verdict([rung], **gate_kw)
    if any("object_pinned" in w for w in v_ok["warnings"]):
        bad.append("钉死物体的产物不该再收到「没有 object_geom」的假警告")
    v_unpin = frontier_verdict([dict(rung, object_pinned=False)], **gate_kw)
    if "data" not in (v_unpin["rungs"][0]["failed"] or []):
        bad.append(f"object_pinned=False 必须让整档判废(data): {v_unpin['rungs'][0]['failed']}")
    v_flick = frontier_verdict([dict(rung, sac_success=0.35, scripted_success=1.0)], **gate_kw)
    if "metric" not in (v_flick["rungs"][0]["failed"] or []):
        bad.append(f"flick_frac=0.5 必须让指标判废(metric): {v_flick['rungs'][0]['failed']}")
    v_gv = frontier_verdict([dict(rung, flick_frac=0.0, sac_success=0.35,
                                  success_rate_grasp_verified=0.10, scripted_success=1.0)],
                            **gate_kw)
    if not any("grasp-verified" in w for w in v_gv["rungs"][0].get("warnings", [])
               + v_gv.get("warnings", [])):
        bad.append("两个口径差 0.25 时必须点名（否则 band/分辨率都按被高估的那个数算）")

    # ---- (10) rise 标定口径随任务变（塌掉时**不报错**，只是把失败标签贴反）-------------
    # 数字取自本轮实测产物 runs/infra/diag_pickplace_sparse100k.json（手写臂 23 个成功局）：
    # rise_at_success 最小 +0.0001（篮底≈桌面高，与「提没提起来」无因果），max_rise 最小 0.0816。
    lift_rows = [{"success": True, "rise_at_success": v, "max_rise": 0.09}
                 for v in (0.0161, 0.0172, 0.0180)]
    pp_rows = [{"success": True, "rise_at_success": r, "max_rise": m}
               for r, m in ((0.0001, 0.0816), (0.0003, 0.0845), (0.0215, 0.0826))]
    cal_lift = calibrate_rise(lift_rows)                 # 不传 task 必须 == 显式 "lift"
    if cal_lift != calibrate_rise(lift_rows, "lift"):
        bad.append("lift 默认口径被改动 ⇒ probe_paired_lift_eval 与历史 Lift 产物不再可比")
    if cal_lift["lift_ok"] != 0.0129 or "calibration_basis" in cal_lift \
            or cal_lift.get("rise_at_success_min_max") != [0.0161, 0.018]:
        bad.append(f"lift 标定应逐字保持历史行为（成功局 rise_at_success ×0.8）: {cal_lift}")
    cal_pp = calibrate_rise(pp_rows, "pickplace")
    if cal_pp.get("calibration_basis") != "max_rise" or cal_pp["lift_ok"] != 0.0653:
        bad.append(f"pickplace 必须按成功局 max_rise 标定（0.8×0.0816=0.0653）: {cal_pp}")
    if "rise_at_success_min_max" in cal_pp or cal_pp.get("max_rise_min_max") != [0.0816, 0.0845]:
        bad.append(f"pickplace 产物必须写清标定量区间，且字段名不能沿用 rise_at_success: {cal_pp}")
    # 塌陷口径（迁移前的行为）必须给出**不同**标签，否则这条断言是空的
    collapsed = calibrate_rise(pp_rows, "lift")
    if collapsed["lift_ok"] != 0.0001:
        bad.append(f"变异前提变了：按 rise_at_success 标定应塌到 1e-4，实得 {collapsed}")
    weak = dict(track(held=True, max_rise=0.0055, min_xy=0.004), seed=1010)   # 实测 seed 1010
    if classify(dict(weak), cal_pp, "pickplace") != "grasp_no_lift":
        bad.append("真抓住但只离桌 5.5 mm 应判 grasp_no_lift（力/姿态段）")
    if classify(dict(weak), collapsed, "pickplace") != "lift_no_carry":
        bad.append("变异未被抓到：塌陷口径也判 grasp_no_lift（说明用例区分不了两种标定量）")
    # 标定只许用**成功**局：失败局的 max_rise 再高也不能抬高这条线
    noisy = pp_rows + [{"success": False, "rise_at_success": None, "max_rise": 0.30}]
    if calibrate_rise(noisy, "pickplace")["lift_ok"] != cal_pp["lift_ok"]:
        bad.append("失败局混进了标定样本 ⇒ 阈值会被最差臂的乱动抬高")
    for tname in ("lift", "pickplace"):
        fb = calibrate_rise([], tname)
        if fb["lift_ok"] != 0.04 or not fb["source"].startswith("fallback"):
            bad.append(f"{tname} 无成功样本时必须退回兜底并写明不可信: {fb}")
        if (tname == "pickplace") != ("calibration_basis" in fb):
            bad.append(f"{tname} 的兜底路径也要露出标定量口径: {fb}")
    say(f"      rise 标定: lift lift_ok={cal_lift['lift_ok']}（rise_at_success）· "
        f"pickplace lift_ok={cal_pp['lift_ok']}（max_rise）· 塌陷口径={collapsed['lift_ok']}")
    # 断链守卫：函数支持 task **不等于**调用方传了 task（§7 第 26 条同一模式，本轮第二例）。
    # 漏传不会报错，只会让 pickplace 静默退回 lift 口径 —— 正是上面那个 1e-4 塌陷。
    import inspect
    import re

    from scripts import probe_contact_ceiling as pcc
    insides = re.findall(r"calibrate_rise\(([^)]*)\)", inspect.getsource(pcc))
    real_calls = [c for c in insides if c.strip() and "rows: list" not in c]
    no_task = [c for c in real_calls if "task" not in c]
    if not real_calls:
        bad.append("守卫空转：没在探针源码里找到任何 calibrate_rise 调用（正则失配？）")
    if no_task:
        bad.append(f"探针里有 calibrate_rise 调用没传 task，pickplace 会静默退回 lift 口径: {no_task}")

    check("16 接触探针迁移（pickplace）：叶子播种/物体解析/放置段标签与漏斗/双口径门禁/门禁输入链",
          not bad, "; ".join(bad))


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    VERBOSE = parser.parse_args().verbose

    print("=" * 72)
    print("阶段 3 自检：技能 / 诊断 / 采样 / 门禁 / 版本库 / 环境工厂")
    print("=" * 72)
    check_imports()
    check_diagnose()
    check_sampling()
    check_gate()
    check_registry_append_only()
    check_env_factory()
    check_skills()
    check_harsh_probe()
    check_sampling_design()
    check_obs_extensions()
    check_probe_obs_layout()
    check_frontier_gate()
    check_stopping_and_resolution()
    check_contact_repro_and_flick()
    check_three_state_gate()
    check_contact_migration()

    print("-" * 72)
    if FAILED:
        print(f"  {len(FAILED)} 项未通过: {FAILED}")
        return 1
    print("  全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
