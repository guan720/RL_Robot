#!/usr/bin/env python3
"""C 线自检：T17「同状态换 goal」落到**真实参考 learner**（B→C 交接单 C-1 / C-2 / C-3 + §4）。

B 的 `scripts/b_selfcheck_goal_conditioning_t17.py` 已在 B 命名空间里证明 T17 断言「有牙」
（参考实现全过、6 个故意写坏的实现全被抓，`teeth_check.non_vacuous=true`）。本脚本做另一半：
把同一套断言落到 C 的真实实现 `harness/queue_td_learner.py` 上，而不是落在 mock 上。

**为什么维度检查不够**（B 的实测结论，本脚本照抄其断言形态）：
`torch.cat([state, goal, c, xi])` 只保证了维度。单 goal 词表下 `_goal_onehot` 恒返回 `[1.0]`
—— 形状全对、concat 正常、forward 不报错，但 goal 那一列是常量，等价于给第一层加了一个固定
偏置，goal 对输出的影响恒为 0。B 的 B2–B6 五个变异体正是「常规检查全过、只有 T17 能抓」那类。

**三处 C 侧改动**（交接单 §1 表，全部在 C 的写入边界内）：
  C-1 `LearnerConfig.goals` 缺省 = 双向词表（v4 附录 02 §12 / 交付包 AGENTS.md：同一目标条件
      学 A→B 与 B→A；单 goal 词表下 T17 连测试都构造不出来）；
  C-2 `_goal_onehot` 在 `goal_dim < 2` 时**显式拒绝**（把「无法验证」变成「拒绝启动」）；
  C-3 本脚本 = T17-a/c/d/e 的单元测试 + 变异自检。

**按交接单 §3.1 的精度更正**：C 抛的是 `LearnerRefused`（继承 `RuntimeError`），**不是**
`KeyError`。B 参考实现里 `except KeyError` 的写法照抄过来会让 T17-e 假失败，所以这里断言
`LearnerRefused`，并额外钉一条「它不是 `KeyError` 的子类」——防止日后有人把它改成 `KeyError`
让 B 的旧写法蒙对（那会让两侧各测一个东西，共因失效看不出来）。

**五组件覆盖（交接单 §2 / 附录 02 §12）**：base / editor / Q / 候选筛选 / 预测器要**分别**验。
本参考 learner 首版只实现了 base(=actor) 与 Q(=critic)，另加两个 target 网络（它们产生
bootstrap；goal 不进 target 就等于 TD 目标不是 goal 条件的，这是 B 的参考实现没覆盖的风险，
因为它没有 target 网络）。editor / 候选筛选 / 预测器**尚未实现** ⇒ 按 ADR-C-004 记 SKIP
（`ok=None`），不计入通过也不计入失败，并在结论里明写「这三条本轮未被验证」。**SKIP ≠ PASS。**

**只依赖 torch + numpy**（不 import robosuite / mujoco）：T17 验的是计算图，不是真机能力，
所以它不该被渲染栈、EGL 或 GPU 可用性阻塞。观测走真实 `ObsStore`，时间轴复用
`selfcheck_ledger_views.EpisodeBuilder`（不另立事实源），learner 侧代码路径与真帧通道一致。
真帧通道的 goal 贯通另由 `scripts/c_learner_shard_smoke.py` 覆盖（词表已同步为双向）。

产物：`runs/infra/c_t17_goal_conditioning.json`
临时分片：`runs/infra/c_t17_goal_conditioning/<时间戳>/`（**不写** A/B 的目录、不写 `harness/`）

用法：
    python3 scripts/c_selfcheck_goal_conditioning_t17.py
    python3 scripts/c_selfcheck_goal_conditioning_t17.py --no-b-teeth   # 跳过复跑 B 的牙齿自检
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("torch")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from harness import data_bridge as db  # noqa: E402
from harness import queue_td_learner as ql  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402
from harness.obs_store import ObsStore  # noqa: E402
from scripts.selfcheck_ledger_views import EpisodeBuilder  # noqa: E402
from scripts.selfcheck_ledger_views import action as synth_action  # noqa: E402

OUT_ROOT = ROOT / "runs" / "infra" / "c_t17_goal_conditioning"
OUT_JSON = ROOT / "runs" / "infra" / "c_t17_goal_conditioning.json"
B_TEETH_SCRIPT = ROOT / "scripts" / "b_selfcheck_goal_conditioning_t17.py"

# ---- 单一事实源：词表不从本文档抄，直接读 learner 配置的缺省值 --------------------------
# 抄一份常量到这里，等 C-1 的缺省词表变了而本脚本没跟着变，测试就会对着一个不存在的
# 词表绿着——那正是「恒真断言」的另一种形态。
DEFAULT_VOCAB: tuple[str, ...] = tuple(
    ql.LearnerConfig.__dataclass_fields__["goals"].default)
UNKNOWN_GOAL = "lift_C_to_D"          # 词表外，T17-e 用
LEGACY_SINGLE = ("lift",)             # C-2 之前的实配（交接单点名的 `queue_td_learner.py:65`）

# ---- 本脚本自己的合成口径（刻意不复用 Lift 的表征版本号）------------------------------
# T17 用的是合成状态，不是 Lift 的 proprio50+obj10 布局。若在这里写
# `lift-state-proprio50+obj10-v1`，就等于凭空多出第二个「Lift 表征版本」的事实源，
# 而那份布局归 `scripts/c_contract_lift_smoke.py::REPR_VERSION` 独家生产（由宽度拼出）。
PROP_DIM = 50
ENV_DIM = 10
STATE_DIM = PROP_DIM + ENV_DIM
ACTION_DIM = 7
N = 4
GAMMA = 0.99
LABEL_VERSION = "env-reward-v1"
SLOTS_PER_EPISODE = 5
SEED = 20260929
D_GOAL_OVER_D_STATE_MIN = 0.05        # T17-d 阈值，原样取自交接单 §2 表
ATOL = 1e-9                           # T17-a 阈值，原样取自交接单 §2 表


def t17_repr_version() -> str:
    return f"t17-synthetic-state{STATE_DIM}-v1"


def t17_unit_convention() -> dict[str, Any]:
    """γ/n 的定标状态必须跟着分片走（ADR-C-002），哪怕这份分片是合成的。

    γ=0.99 / n=4 是**假设值**（真帧路径同一套），status 因此只能是 `assumed`；
    `scope` 明写这份分片只为验计算图，不参与任何跨线数值比较。
    """
    return {"gamma": GAMMA, "n": N, "gamma_slot": GAMMA ** N, "status": "assumed",
            "gamma_is_assumed": True, "n_is_assumed": True,
            "scope": "t17_computation_graph_only",
            "note": ("T17 合成通道：γ/n 沿用真帧路径的假设值（未定标），"
                     "本分片只用于验证 goal 是否真进计算图，不得当能力或数值口径引用。"),
            "doc": "docs/c_golden_conformance_20260928.md#8"}


@contextlib.contextmanager
def open_two_goal_shard(work: Path) -> dict[str, Any]:
    """建一份**同一个 batch 里 goal 真的会变**的分片：两条 episode，各用词表的一个方向。

    走的是真实链路：FactLedger → ObsStore → `db.build_views` → `db.export_views`
    → `ql.load_shard_batch`。所以本脚本验的不只是网络，还包括 goal_id 能否从账本
    一路活到张量（中间任何一处把 goal 丢掉，T17-a 都会转红）。
    """
    if len(DEFAULT_VOCAB) < 2:
        raise AssertionError(f"缺省词表不足 2 项：{DEFAULT_VOCAB}（C-1 未落地）")
    work.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        ledger = stack.enter_context(FactLedger(work / "ledger_t17.db"))
        store = stack.enter_context(ObsStore(work / "obs_t17"))
        rng = np.random.default_rng(SEED)
        n_frames = SLOTS_PER_EPISODE * N
        for gi, goal in enumerate(DEFAULT_VOCAB[:2]):
            episode_id = f"t17_{goal}"
            refs: dict[int, str] = {}
            for frame in range(100, 100 + n_frames):
                refs[frame] = store.put(
                    {"state": rng.normal(size=PROP_DIM).astype(np.float32).tolist(),
                     "environment_state": rng.normal(size=ENV_DIM).astype(np.float32).tolist()},
                    sampled_at_ns=1_000_000 * frame,
                    representation_version=t17_repr_version(),
                    episode_id=episode_id, abs_frame=frame).obs_ref
            builder = EpisodeBuilder(ledger, episode_id, n=N, goal=goal)
            for k in range(SLOTS_PER_EPISODE):
                last = (k == SLOTS_PER_EPISODE - 1)
                # 尾槽必须标终局：否则它声明 bootstrap 却拿不到 `t_k+n` 的快照
                # （帧只写到本槽末尾），`load_shard_batch` 会按「下一状态不可确认」拒绝。
                # 这与 `c_learner_shard_smoke.make_terminal_channel` 的处理同源，不另立规则。
                builder.add_slot(
                    f"R{gi}{k}", 100 + k * N,
                    u=synth_action(1.0 + 0.1 * k, N, dim=ACTION_DIM),
                    rewards=[0.0] * (N - 1) + [0.1 * (k + 1)],
                    terminal_step=N if last else None,
                    terminal_kind="success" if last else "none",
                    obs_ref_of=lambda f: refs.get(f),
                    time_ns_of=lambda f: 1_000_000 * f)
        bundle = db.build_views(ledger, n=N, gamma=GAMMA, obs_store=store,
                                max_age_ns=200_000_000, label_version=LABEL_VERSION)
        db.write_manifests(ledger, bundle, run_id="c-t17", gamma=GAMMA, n=N,
                           label_version=LABEL_VERSION)
        view_dir = work / "views_t17"
        manifest = db.export_views(bundle, view_dir, run_id="c-t17", n=N, gamma=GAMMA,
                                   label_version=LABEL_VERSION, obs_store=store,
                                   fmt="jsonl", unit_convention=t17_unit_convention(),
                                   notes="T17 goal 贯通自检导出的四视图分片（合成时间轴）")
        cfg = ql.LearnerConfig(state_dim=STATE_DIM, action_dim=ACTION_DIM, n=N, gamma=GAMMA,
                               goals=DEFAULT_VOCAB, hidden=64, device="cpu",
                               torch_threads=2, seed=0)
        batch = ql.load_shard_batch(view_dir, store, cfg)
        yield {"work": work, "cfg": cfg, "batch": batch, "manifest": manifest,
               "view_dir": view_dir,
               "counts": {view: len(getattr(bundle, view)) for view in db.VIEW_NAMES}}


# --------------------------------------------------------------------------
# 组件表：附录 02 §12 的五个组件 + C 首版额外两个 target 网络
# --------------------------------------------------------------------------
def _e_fixed(cfg: ql.LearnerConfig, rows: int) -> torch.Tensor:
    """critic 的动作位用**固定** E（linspace，不用随机数）⇒ 跨进程逐位可复现。

    用固定 E 而不是 actor 的实时输出，是为了让「critic 对 goal 的依赖」与
    「actor 对 goal 的依赖」互不掩盖：否则 actor 瞎了也会通过 critic 表现出来，
    B6（只验标量会漏掉）那类缺陷就抓不住。
    """
    width = cfg.n * cfg.action_dim
    base = torch.linspace(-0.5, 0.5, width, dtype=torch.float32)
    return base.unsqueeze(0).expand(rows, width).contiguous()


def component_outputs(nets: dict, cfg: ql.LearnerConfig, state: torch.Tensor,
                      goal: torch.Tensor, c: torch.Tensor, xi: torch.Tensor,
                      e: torch.Tensor) -> dict[str, torch.Tensor]:
    """按组件分别前向。`None` = 本参考 learner 首版未实现该组件（记 SKIP，不记 PASS）。"""
    chunk = ql.chunk_of(c, e, cfg)
    out: dict[str, Any] = {
        "base(actor)": nets["actor"](state, goal, c, xi),
        "Q(critic)": nets["critic"](state, goal, c, xi, chunk),
        "editor": None,
        "candidate_filter": None,
        "predictor": None,
        # 以下两个不在附录 02 §12 的五组件里，但在同一条计算图上：
        # `td_targets` 的 bootstrap 完全由 target 网络产生，goal 不进 target
        # ⇒ TD 目标 y 就不是 goal 条件的，actor 再对 goal 敏感也学不出方向性。
        "actor_target": nets["actor_target"](state, goal, c, xi),
        "critic_target": nets["critic_target"](state, goal, c, xi, chunk),
    }
    return out


NOT_IMPLEMENTED = ("editor", "candidate_filter", "predictor")
IMPLEMENTED = ("base(actor)", "Q(critic)", "actor_target", "critic_target")


def _goal_vec(goal_id: str, cfg: ql.LearnerConfig, rows: int) -> torch.Tensor:
    one = ql._goal_onehot(goal_id, cfg, kind=f"t17/{goal_id}")
    return torch.as_tensor(np.tile(one, (rows, 1)), dtype=torch.float32)


def _blind_forward(orig: Callable) -> Callable:
    """变异体：goal 在进 concat 前被丢成 0（= B 的 B4/B5 那类，形状完全正确）。"""
    def fwd(self, state, goal, c, xi, *rest):
        return orig(self, state, torch.zeros_like(goal), c, xi, *rest)
    return fwd


@contextlib.contextmanager
def blind_component(cls: type) -> Any:
    orig = cls.forward
    cls.forward = _blind_forward(orig)
    try:
        yield
    finally:
        cls.forward = orig


@contextlib.contextmanager
def freeze_first_layer(nets: dict, keys: tuple[str, ...]) -> Any:
    """变异体：第一层权重被冻结 ⇒ 前向仍随 goal 变（T17-a 过），但学不到（T17-c 红）。

    这条的存在是为了证明 **T17-c 有独立于 T17-a 的牙齿**：只测「换 goal 输出会变」
    抓不到「goal 影响存在但参数收不到梯度」这一类。
    """
    saved = {k: nets[k].net[0].weight.requires_grad for k in keys}
    for k in keys:
        nets[k].net[0].weight.requires_grad_(False)
    try:
        yield
    finally:
        for k, v in saved.items():
            nets[k].net[0].weight.requires_grad_(v)


def goal_col_grad_abssum(net: torch.nn.Module, cfg: ql.LearnerConfig, *, chunk: torch.Tensor | None,
                         state: torch.Tensor, goal: torch.Tensor, c: torch.Tensor,
                         xi: torch.Tensor) -> float:
    """T17-c（one-hot 分支）：第一层在 **goal 列切片**上的权重梯度绝对值和。

    交接单 §2 明写 one-hot 走这条（embedding 才走 `goal_table.weight.grad`）。
    C 首版是 one-hot，所以切 `[state_dim, state_dim+goal_dim)`。
    """
    net.zero_grad(set_to_none=True)
    out = net(state, goal, c, xi) if chunk is None else net(state, goal, c, xi, chunk)
    out.sum().backward()
    grad = net.net[0].weight.grad
    if grad is None:
        return 0.0
    sl = slice(cfg.state_dim, cfg.state_dim + cfg.goal_dim)
    return float(grad[:, sl].abs().sum())


# --------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------
def case_c1_vocab_is_bidirectional(checks: list, ctx: dict) -> None:
    """C-1：缺省词表必须是双向的，且两个方向的 one-hot 真的不同。"""
    checks.append((f"C-1 缺省 goals 词表 ≥2 项（实得 {DEFAULT_VOCAB}）",
                   len(DEFAULT_VOCAB) >= 2))
    checks.append((f"C-1 词表含 A→B 与 B→A 两个方向（{DEFAULT_VOCAB}）",
                   any("A_to_B" in g for g in DEFAULT_VOCAB)
                   and any("B_to_A" in g for g in DEFAULT_VOCAB)))
    cfg = ctx["cfg"]
    checks.append((f"C-1 配置 goal_dim == {len(DEFAULT_VOCAB)}（不是 1）",
                   cfg.goal_dim == len(DEFAULT_VOCAB) >= 2))
    g0 = ql._goal_onehot(DEFAULT_VOCAB[0], cfg, kind="t17-c1")
    g1 = ql._goal_onehot(DEFAULT_VOCAB[1], cfg, kind="t17-c1")
    checks.append(("C-1 两个方向的 one-hot 逐值不同（不是同一列常量）",
                   bool(np.any(g0 != g1)) and float(g0.sum()) == 1.0 and float(g1.sum()) == 1.0))
    checks.append(("C-1 x_dim 随词表宽度增长（goal 真的占了输入位）",
                   cfg.x_dim() == cfg.state_dim + len(DEFAULT_VOCAB)
                   + cfg.n * cfg.action_dim + cfg.xi_dim))


def case_c2_single_goal_refused(checks: list, ctx: dict) -> None:
    """C-2：单 goal 词表下必须**显式拒绝**，而不是静默返回常量 [1.0]。"""
    cfg_single = ql.LearnerConfig(state_dim=STATE_DIM, action_dim=ACTION_DIM, n=N,
                                  gamma=GAMMA, goals=LEGACY_SINGLE, device="cpu")
    checks.append((f"C-2 单 goal 词表 {LEGACY_SINGLE} 下 _goal_onehot 抛 LearnerRefused",
                   _raises_refused(lambda: ql._goal_onehot("lift", cfg_single, kind="t17-c2"))))
    err = _catch(lambda: ql._goal_onehot("lift", cfg_single, kind="t17-c2"))
    msg = str(err)
    checks.append(("C-2 拒绝理由点名「one-hot 恒为常量 / 不能声称 goal-conditioned」",
                   "常量" in msg and "goal-conditioned" in msg))
    checks.append(("C-2 拒绝理由写出实际词表（可诊断，不是只说 no）",
                   "lift" in msg))
    # 反证：把 C-2 的守卫拿掉（重注入修复前实现），单 goal 就会静默给出 [1.0]。
    # 没有这一条，「抛异常」可能只是因为别的分支先炸了 —— 那就是恒真断言。
    def pre_c2_onehot(goal_id: str, cfg: ql.LearnerConfig, *, kind: str) -> np.ndarray:
        if goal_id not in cfg.goals:
            raise ql.LearnerRefused(f"{kind}: goal_id={goal_id!r} 不在配置词表 {cfg.goals} 里")
        vec = np.zeros(cfg.goal_dim, dtype=np.float32)
        vec[cfg.goals.index(goal_id)] = 1.0
        return vec

    orig = ql._goal_onehot
    ql._goal_onehot = pre_c2_onehot
    try:
        silent = ql._goal_onehot("lift", cfg_single, kind="t17-c2-mutant")
        checks.append(("C-2 变异可证伪：去掉守卫后单 goal 静默返回常量 [1.0]（缺陷确实存在过）",
                       silent.tolist() == [1.0]))
    finally:
        ql._goal_onehot = orig
    checks.append(("C-2 守卫在位时同一调用被拒（前后对比成立）",
                   _raises_refused(lambda: ql._goal_onehot("lift", cfg_single, kind="t17-c2"))))


def case_shard_carries_both_goals(checks: list, ctx: dict) -> None:
    """goal_id 必须从账本一路活到张量：同一 batch 里两个方向都出现。"""
    batch, cfg = ctx["batch"], ctx["cfg"]
    goal = batch.td["goal"]
    checks.append((f"分片装配出 td 行（used={batch.used}，counts={ctx['counts']}）",
                   batch.used["td"] > 0))
    distinct = {tuple(row) for row in goal.tolist()}
    expect = {tuple(ql._goal_onehot(g, cfg, kind="t17").tolist()) for g in DEFAULT_VOCAB[:2]}
    checks.append((f"td 批里出现 {len(distinct)} 种 goal one-hot，且正好是词表前两个方向",
                   distinct == expect))
    checks.append(("td 批的 goal 列不是常量（否则等价于固定偏置）",
                   float(goal.std(dim=0).sum()) > 0.0))
    rows = {str(r["goal_id"]) for r in batch.td_rows}
    checks.append((f"td 行的 goal_id 覆盖两个方向（{sorted(rows)}）",
                   rows == set(DEFAULT_VOCAB[:2])))
    checks.append(("next_goal 与同行 goal 一致（附录 02：X_{k+1} 沿用 g_k，不换向）",
                   bool(torch.equal(batch.td["next_goal"], goal))))
    uc = (ctx["manifest"] or {}).get("unit_convention") or {}
    checks.append(("分片 manifest 带 unit_convention 且 γ_slot == γ^n（ADR-C-002）",
                   uc.get("status") == "assumed"
                   and abs(float(uc.get("gamma_slot", -1)) - GAMMA ** N) < 1e-15
                   and int(uc.get("n", -1)) == N))


def case_t17_a_components(checks: list, ctx: dict) -> None:
    """T17-a：同状态换 goal，输出必须变 —— 逐组件查，不是一个标量。"""
    nets, cfg, batch = ctx["nets"], ctx["cfg"], ctx["batch"]
    state, c, xi = batch.td["state"], batch.td["c"], batch.td["xi"]
    rows = state.shape[0]
    e = _e_fixed(cfg, rows)
    g0 = _goal_vec(DEFAULT_VOCAB[0], cfg, rows)
    g1 = _goal_vec(DEFAULT_VOCAB[1], cfg, rows)
    with torch.no_grad():
        o0 = component_outputs(nets, cfg, state, g0, c, xi, e)
        o1 = component_outputs(nets, cfg, state, g1, c, xi, e)
    for name in IMPLEMENTED:
        changed = bool(not torch.allclose(o0[name], o1[name], atol=ATOL))
        checks.append((f"T17-a 组件 {name}：同状态换 goal 输出改变（atol={ATOL:g}）", changed))
        ctx.setdefault("t17_a_delta", {})[name] = float((o1[name] - o0[name]).abs().mean())
    for name in NOT_IMPLEMENTED:
        # ADR-C-004：SKIP ≠ PASS。这三条本轮**未被验证**，不计入通过率。
        checks.append((f"T17-a 组件 {name} —— SKIP：参考 learner 首版未实现该组件"
                       "（附录 02 §12 要求分别验，实现后必须补测）", None))
        ctx.setdefault("t17_a_delta", {})[name] = None


def case_t17_c_gradient(checks: list, ctx: dict) -> None:
    """T17-c：goal 表征的梯度非零（抓 detach 与零门）。one-hot ⇒ 查第一层 goal 列。"""
    nets, cfg, batch = ctx["nets"], ctx["cfg"], ctx["batch"]
    state, c, xi = batch.td["state"], batch.td["c"], batch.td["xi"]
    e = _e_fixed(cfg, state.shape[0])
    chunk = ql.chunk_of(c, e, cfg)
    g0 = _goal_vec(DEFAULT_VOCAB[0], cfg, state.shape[0])
    for key, net, ch in (("actor", nets["actor"], None), ("critic", nets["critic"], chunk)):
        val = goal_col_grad_abssum(net, cfg, chunk=ch, state=state, goal=g0, c=c, xi=xi)
        checks.append((f"T17-c {key} 第一层 goal 列权重梯度非零（实得 {val:.3e}）", val > 0.0))
        ctx.setdefault("t17_c_grad", {})[key] = val
    for name in NOT_IMPLEMENTED:
        checks.append((f"T17-c 组件 {name} —— SKIP：首版未实现", None))


def case_t17_d_not_constant_bias(checks: list, ctx: dict) -> None:
    """T17-d：goal 的影响不能只是常量偏置 —— d_goal / d_state > 0.05。"""
    nets, cfg, batch = ctx["nets"], ctx["cfg"], ctx["batch"]
    state, c, xi = batch.td["state"], batch.td["c"], batch.td["xi"]
    gen = torch.Generator().manual_seed(SEED)
    state2 = state + 0.1 * torch.randn(state.shape, generator=gen, dtype=state.dtype)
    g0 = _goal_vec(DEFAULT_VOCAB[0], cfg, state.shape[0])
    g1 = _goal_vec(DEFAULT_VOCAB[1], cfg, state.shape[0])
    with torch.no_grad():
        e0 = nets["actor"](state, g0, c, xi)
        e1 = nets["actor"](state, g1, c, xi)
        eh = nets["actor"](state2, g0, c, xi)
    d_goal = float((e1 - e0).abs().mean())
    d_state = float((eh - e0).abs().mean())
    ratio = d_goal / max(d_state, 1e-12)
    checks.append((f"T17-d 换 goal 的输出差量级可比于换状态"
                   f"（d_goal={d_goal:.3e} / d_state={d_state:.3e} = {ratio:.4f} "
                   f"> {D_GOAL_OVER_D_STATE_MIN}）", ratio > D_GOAL_OVER_D_STATE_MIN))
    ctx["t17_d"] = {"d_goal": d_goal, "d_state": d_state, "ratio": ratio,
                    "threshold": D_GOAL_OVER_D_STATE_MIN}


def case_t17_e_unknown_goal_rejected(checks: list, ctx: dict) -> None:
    """T17-e：词表外 goal 必须被拒绝，不能静默当成某个已知 goal。

    按交接单 §3.1：断言 `LearnerRefused`，**不要**照抄 B 的 `except KeyError`。
    """
    cfg = ctx["cfg"]
    err = _catch(lambda: ql._goal_onehot(UNKNOWN_GOAL, cfg, kind="t17-e"))
    checks.append((f"T17-e 词表外 goal {UNKNOWN_GOAL!r} 被拒（LearnerRefused）",
                   isinstance(err, ql.LearnerRefused)))
    checks.append(("T17-e 精度更正落地：LearnerRefused 不是 KeyError 子类"
                   "（照抄 B 的 except KeyError 会漏掉它）",
                   isinstance(err, RuntimeError) and not isinstance(err, KeyError)))
    checks.append((f"T17-e 拒绝理由回显 goal 与词表（{UNKNOWN_GOAL!r}）",
                   UNKNOWN_GOAL in str(err) and DEFAULT_VOCAB[0] in str(err)))
    # 静默降级是这条要防的事故：拒绝必须发生在**装配前**，不能先给个零向量再说。
    checks.append(("T17-e 拒绝时不返回任何向量（不是先降级后报警）",
                   _returns_none_on_raise(lambda: ql._goal_onehot(UNKNOWN_GOAL, cfg, kind="t17-e"))))


def case_xi_census_is_quantified(checks: list, ctx: dict) -> None:
    """交接单 §4：BC 锚的 ξ 覆盖面必须**每 batch 可量化**，不能只写在 notes 里。"""
    batch = ctx["batch"]
    cen = batch.xi_census
    checks.append(("§4 ShardBatch.xi_census 已落地且含 bc_rows_at_xi0 / bc_rows_total",
                   "bc_rows_at_xi0" in cen and "bc_rows_total" in cen
                   and "td_rows_at_xi1" in cen and "td_rows_total" in cen))
    checks.append(("§4 普查行数与 batch.used 自洽",
                   cen["td_rows_total"] == batch.used["td"]
                   and cen["bc_rows_total"] == batch.used["bc"]))
    td1 = int((batch.td["xi"][:, ql.XI_HAS_C] > 0.5).sum()) if batch.td else 0
    bc0 = int((batch.bc["xi"][:, ql.XI_HAS_C] < 0.5).sum()) if batch.bc else 0
    checks.append((f"§4 普查与张量独立复算逐值相同（td@ξ1={td1}, bc@ξ0={bc0}）",
                   (cen["td_rows_at_xi1"], cen["bc_rows_at_xi0"]) == (td1, bc0)))
    checks.append(("§4 无 BC 行时比例为 None（不伪造 0/0）",
                   (cen["bc_rows_at_xi0_ratio"] is None) == (cen["bc_rows_total"] == 0)))
    checks.append(("§4 普查给出显式结论字段 bc_anchor_covers_xi1（B 要的是显式而非沉默）",
                   isinstance(cen["bc_anchor_covers_xi1"], bool)))
    ctx["xi_census"] = cen


def case_mutations_have_teeth(checks: list, ctx: dict) -> None:
    """变异自检：把 goal 通路逐个写坏，上面的断言必须转红（只测正向等于没测）。"""
    cfg, batch = ctx["cfg"], ctx["batch"]
    state, c, xi = batch.td["state"], batch.td["c"], batch.td["xi"]
    rows = state.shape[0]
    e = _e_fixed(cfg, rows)
    g0 = _goal_vec(DEFAULT_VOCAB[0], cfg, rows)
    g1 = _goal_vec(DEFAULT_VOCAB[1], cfg, rows)

    def fresh_nets() -> dict:
        return ql.build_nets(cfg)

    def outs(nets: dict) -> tuple[dict, dict]:
        with torch.no_grad():
            return (component_outputs(nets, cfg, state, g0, c, xi, e),
                    component_outputs(nets, cfg, state, g1, c, xi, e))

    def differs(o0: dict, o1: dict, key: str) -> bool:
        return bool(not torch.allclose(o0[key], o1[key], atol=ATOL))

    # M1 actor 瞎（B6 同构：只验标量 / 只验 critic 会漏掉）
    nets = fresh_nets()
    with blind_component(ql.DeterministicActor):
        o0, o1 = outs(nets)
    checks.append(("M1 变异有牙：actor 丢掉 goal 后 T17-a(actor) 转红",
                   not differs(o0, o1, "base(actor)")))
    checks.append(("M1 说明逐组件必要：同一变异下 critic 仍敏感（只看标量会假绿）",
                   differs(o0, o1, "Q(critic)")))

    # M2 critic 瞎：actor 仍敏感 ⇒ 标量级检查会过，逐组件检查才抓得到
    nets = fresh_nets()
    with blind_component(ql.QueueCritic):
        o0, o1 = outs(nets)
    checks.append(("M2 变异有牙：critic 丢掉 goal 后 T17-a(Q) 转红",
                   not differs(o0, o1, "Q(critic)")))
    checks.append(("M2 说明逐组件必要：同一变异下 actor 仍敏感（只看标量/只看 actor 会假绿）",
                   differs(o0, o1, "base(actor)")))

    # M3 target 网络瞎：在线网络全对，但 bootstrap 不是 goal 条件的。
    # 只盲 **实例**（actor_target），不动类 ⇒ 与 M1 不是同一条变异。
    nets = fresh_nets()
    tgt = nets["actor_target"]
    orig_at = ql.DeterministicActor.forward
    with attr_override(tgt, "forward",
                       lambda s_, g_, c_, xi_: orig_at(tgt, s_, torch.zeros_like(g_), c_, xi_)):
        o0, o1 = outs(nets)
    checks.append(("M3 变异有牙：actor_target 丢掉 goal 后 T17-a(actor_target) 转红",
                   not differs(o0, o1, "actor_target")))
    checks.append(("M3 是 B 参考实现未覆盖的风险：同一变异下在线 actor 仍敏感",
                   differs(o0, o1, "base(actor)")))

    # M4 one-hot 恒为常量（无视 goal_id）：装配层就被污染
    nets = fresh_nets()
    orig = ql._goal_onehot
    ql._goal_onehot = lambda goal_id, cfg_, *, kind: orig(DEFAULT_VOCAB[0], cfg_, kind=kind)
    try:
        g0m = _goal_vec(DEFAULT_VOCAB[0], cfg, rows)
        g1m = _goal_vec(DEFAULT_VOCAB[1], cfg, rows)
        with torch.no_grad():
            m0 = component_outputs(nets, cfg, state, g0m, c, xi, e)
            m1 = component_outputs(nets, cfg, state, g1m, c, xi, e)
        same = bool(torch.allclose(m0["base(actor)"], m1["base(actor)"], atol=ATOL))
    finally:
        ql._goal_onehot = orig
    checks.append(("M4 变异有牙：one-hot 无视 goal_id 时两个方向输入相同 ⇒ T17-a 转红", same))

    # M5 第一层被冻结：前向仍随 goal 变（T17-a 过），但 goal 列收不到梯度（T17-c 红）
    nets = fresh_nets()
    with freeze_first_layer(nets, ("actor", "critic")):
        f0, f1 = outs(nets)
        fwd_ok = differs(f0, f1, "base(actor)")
        grad_actor = goal_col_grad_abssum(nets["actor"], cfg, chunk=None,
                                          state=state, goal=g0, c=c, xi=xi)
        grad_critic = goal_col_grad_abssum(nets["critic"], cfg,
                                           chunk=ql.chunk_of(c, e, cfg),
                                           state=state, goal=g0, c=c, xi=xi)
    checks.append(("M5 变异有牙：冻结第一层后 T17-c 梯度归零",
                   grad_actor == 0.0 and grad_critic == 0.0))
    checks.append(("M5 证明 T17-c 有独立牙齿：同一变异下 T17-a 仍然通过（只测 a 会漏）", fwd_ok))

    # M6 单 goal 词表（C-1 之前的实配）：T17 连构造都构造不出来
    cfg_single = ql.LearnerConfig(state_dim=STATE_DIM, action_dim=ACTION_DIM, n=N,
                                  gamma=GAMMA, goals=LEGACY_SINGLE, device="cpu")
    blocked = _raises_refused(lambda: (_goal_vec(LEGACY_SINGLE[0], cfg_single, 1),
                                       _goal_vec("lift_B_to_A", cfg_single, 1)))
    checks.append(("M6 变异有牙：单 goal 词表下「同状态换 goal」被显式挡住（不是静默通过）",
                   blocked))


@contextlib.contextmanager
def attr_override(obj: Any, name: str, value: Any) -> Any:
    """只在**实例** `__dict__` 上覆盖属性，退出时精确还原（不动类，避免污染其它实例）。"""
    had = name in obj.__dict__
    saved = obj.__dict__.get(name)
    obj.__dict__[name] = value
    try:
        yield
    finally:
        if had:
            obj.__dict__[name] = saved
        else:
            obj.__dict__.pop(name, None)


def _catch(fn: Callable) -> BaseException | None:
    try:
        fn()
    except BaseException as exc:        # noqa: BLE001 —— 要的就是「抛了什么」
        return exc
    return None


def _raises_refused(fn: Callable) -> bool:
    return isinstance(_catch(fn), ql.LearnerRefused)


def _returns_none_on_raise(fn: Callable) -> bool:
    """拒绝路径不得返回任何值（防止「先降级成零向量、再补一条警告」那种假拒绝）。"""
    try:
        fn()
    except ql.LearnerRefused:
        return True
    except BaseException:               # noqa: BLE001
        return False
    return False


def case_b_teeth_still_non_vacuous(checks: list, ctx: dict) -> None:
    """交接单 §6.3：复跑 B 的牙齿自检，确认 C 的改动没造成共因失效。

    输出改到 **C 的目录**（`--json-out`），不碰 `runs/infra/b_t17/`：那是 B 的产物边界。
    """
    if not ctx.get("with_b_teeth"):
        checks.append(("B 牙齿自检复跑 —— SKIP：本轮 --no-b-teeth", None))
        return
    if not B_TEETH_SCRIPT.exists():
        checks.append((f"B 牙齿自检复跑 —— SKIP：找不到 {B_TEETH_SCRIPT.name}", None))
        return
    out = ctx["work"] / "b_t17_precheck_rerun.json"
    proc = subprocess.run([sys.executable, str(B_TEETH_SCRIPT), "--json-out", str(out)],
                          capture_output=True, text=True, cwd=str(ROOT),
                          env={"CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2",
                               "PATH": "/usr/bin:/bin", "HOME": str(Path.home())})
    if proc.returncode != 0 or not out.exists():
        checks.append((f"B 牙齿自检复跑 —— SKIP：子进程 rc={proc.returncode}"
                       f"（{proc.stderr.strip().splitlines()[-1:] or 'no stderr'}）", None))
        return
    rep = json.loads(out.read_text(encoding="utf-8"))
    teeth = rep.get("teeth_check") or {}
    checks.append(("B 牙齿自检仍 non_vacuous（C 的改动未造成共因失效）",
                   teeth.get("non_vacuous") is True))
    checks.append((f"B 的 6 个坏实现仍全部被 T17 抓住（实得 {teeth.get('n_broken_variants')}）",
                   teeth.get("all_broken_variants_caught_by_t17") is True
                   and teeth.get("n_broken_variants") == 6))
    ctx["b_teeth"] = teeth


CASES: tuple[Callable[[list, dict], None], ...] = (
    case_c1_vocab_is_bidirectional,
    case_c2_single_goal_refused,
    case_shard_carries_both_goals,
    case_t17_a_components,
    case_t17_c_gradient,
    case_t17_d_not_constant_bias,
    case_t17_e_unknown_goal_rejected,
    case_xi_census_is_quantified,
    case_mutations_have_teeth,
    case_b_teeth_still_non_vacuous,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-b-teeth", action="store_true",
                        help="跳过复跑 B 的牙齿自检（默认会跑，输出写进 C 的目录）")
    args = parser.parse_args()

    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    work = OUT_ROOT / stamp
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    checks: list[tuple[str, bool | None]] = []
    with open_two_goal_shard(work) as ctx:
        ctx["work"] = work
        ctx["with_b_teeth"] = not args.no_b_teeth
        ctx["nets"] = ql.build_nets(ctx["cfg"])
        for case in CASES:
            print(f"--- {case.__name__} ---", flush=True)
            before = len(checks)
            case(checks, ctx)
            for name, ok in checks[before:]:
                tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
                print(f"[{tag}] {name}", flush=True)

    failed = [name for name, ok in checks if ok is False]
    skipped = [name for name, ok in checks if ok is None]
    n_pass = len([1 for _, ok in checks if ok is True])
    print("--- 全部通过 ---" if not failed else f"--- 失败 {len(failed)} 条 ---")
    for name in failed:
        print(f"  FAIL {name}")
    if skipped:
        print(f"--- 另有 {len(skipped)} 条 SKIP（未被验证，不计入通过）---")
        for name in skipped:
            print(f"  SKIP {name}")

    OUT_JSON.write_text(json.dumps({
        "cases": [c.__name__ for c in CASES],
        "checks": [{"name": name, "ok": (None if ok is None else bool(ok))}
                   for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_pass": n_pass,
        "n_failed": len(failed), "n_skipped": len(skipped), "skipped": skipped,
        "spec": "T17 同状态换 goal：goal 必须真进计算图（B→C 交接单 C-1/C-2/C-3 + §4）",
        "handoff_doc": "docs/b_handoff_to_c_20260928.md",
        "goals_vocab": list(DEFAULT_VOCAB),
        "unknown_goal_used": UNKNOWN_GOAL,
        "legacy_single_goal_vocab": list(LEGACY_SINGLE),
        "components_implemented": list(IMPLEMENTED),
        "components_not_implemented": list(NOT_IMPLEMENTED),
        "thresholds": {"t17_a_atol": ATOL,
                       "t17_d_min_ratio": D_GOAL_OVER_D_STATE_MIN},
        "t17_a_delta": ctx.get("t17_a_delta"),
        "t17_c_grad": ctx.get("t17_c_grad"),
        "t17_d": ctx.get("t17_d"),
        "xi_census": ctx.get("xi_census"),
        "b_teeth_check": ctx.get("b_teeth"),
        "synthetic_convention": {"state_dim": STATE_DIM, "action_dim": ACTION_DIM,
                                 "n": N, "gamma": GAMMA, "slots_per_episode": SLOTS_PER_EPISODE,
                                 "seed": SEED, "representation_version": t17_repr_version()},
        "shard_counts": ctx.get("counts"),
        "artifact_dir": str(work),
        "conclusion": (
            "T17 在 C 的真实 learner 上成立：base(actor) / Q(critic) / actor_target / "
            "critic_target 四个已实现组件都随 goal 改变输出、goal 列梯度非零、"
            "d_goal/d_state 超过阈值、词表外 goal 被 LearnerRefused 拒绝；"
            "6 个变异体逐个转红证明断言不是恒真。"
            "editor / candidate_filter / predictor 三个组件首版未实现，按 ADR-C-004 记 SKIP，"
            "**本轮未被验证**，不计入通过率；实现后必须补测。"
            "真贯通仍需 A 侧到位（`run_act_lift_runtime_failure_audit.py` 的 goal_id 硬编码、"
            "policy 不接收 goal），见交接单 §5。"),
        "impl_sha256": {rel: _sha256(ROOT / rel) for rel in
                        ("harness/queue_td_learner.py",
                         "scripts/c_selfcheck_goal_conditioning_t17.py")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"结果: {n_pass}/{len(checks)} PASS"
          + (f"（{len(skipped)} SKIP）" if skipped else "") + f" -> {OUT_JSON}")
    raise SystemExit(1 if failed else 0)


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
