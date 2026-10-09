"""C 线：队列增广 TD 的**参考 learner**（首版确定性完整头，CPU 可跑）。

## 定位（先说清楚它不是什么）

不是能力主张，也不替代 RLinf / LeRobot。它存在的唯一目的是让「四个视图 + 导出分片」
有一个**真实调用方**：v4 附录 02 §3 的学习目标此前只有公式与合成自检，没有任何代码
真的按它读过数据、算过 target、更新过参数。本模块把那条路径接通：

    load_views(dir) → ShardBatch(张量) → td_targets()/train_steps() → 参数更新

跑出来的成功率没有任何意义（十几条 TD 样本 + 小 MLP），**只看接线与数值语义是否正确**。

## 三条硬约束（违反任何一条直接抛 `LearnerRefused`，不静默降级）

1. **只有 td / bc 两个视图能进梯度**。`isolated / pending / candidate` 一律计数后丢弃 ——
   把「不确定」当「失败」训正是附录 02 §7 禁止的那件事。
2. **Q 的动作梯度只经 E 段**。C 段进网络前就是分片里的常量（`requires_grad=False`），
   H>2n 的 D 段补零；分片里的 `q_action_gradient_mask` 与 `data_bridge.e_segment_mask(H,n)`
   不一致就拒绝启动，而不是"大致对得上就用"。
3. **不重写公式**。TD 目标逐行调 `data_bridge.td_target()`，`γ_slot` 用分片里的值
   （= γ^n，只乘一次，learner 侧不再自己乘），终局槽 `bootstrap_valid=False` ⇒ 无 bootstrap。

## 首版明确不做

- 不用 SAC 的 `log_pi` / 熵温度 / entropy backup（附录 01 T36：确定性完整头用本文 Q＋BC 目标，
  也不许填假概率去骗 worker 签名）。
- ξ 只有一位（决策时是否有承诺队列在生效）。分片里没导出延迟/执行进度，要加必须先扩导出列
  ——那属于冻结面变更（`docs/ledger_data_bridge_20260928.md` §9.2），不在 learner 侧偷偷补。
- BC 行的 C 无法从分片重建（BC 行没有前后槽链），首版按 `C=0, has_c=0` 处理并写进 `notes`；
  等 harness 纠正也走 request/commit 后可精确重建。这是**已知近似**，不是 bug；
  但「声明」不等于「可量化」⇒ 每个 batch 的 ξ 覆盖面由 `ShardBatch.xi_census` 逐行计数
  （`bc_rows_at_xi0 / bc_rows_total`、`td_rows_at_xi1 / td_rows_total`）。实测比例为
  **100%**（BC 行全部在 ξ=0，TD 侧 ξ=1 的行拿不到锚）⇒ 按 B→C 交接单 §4 的判据，
  这在部署区间是**实质缺口**而不只是已知近似，登记为 ADR-C-005，修法见该条。
- 不做优先级采样、多步回报、分布式 critic、自适应 BC 权重（调研报告 §9.3 首版不加入的复杂度）。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import torch

from . import data_bridge as db
from . import obs_key_coverage as okc
from .obs_store import ObsStore

XI_DIM = 1                 # ξ 首版只有一位
XI_HAS_C = 0               # 第 0 位：决策时是否有承诺队列正在生效
GRADIENT_VIEWS = ("td", "bc")
NEVER_GRADIENT_VIEWS = ("isolated", "pending", "candidate")


class LearnerRefused(RuntimeError):
    """分片与学习配置不一致 / 观测反查不到 / mask 不符 ⇒ 拒绝启动。"""


@dataclass(frozen=True)
class LearnerConfig:
    """学习配置。`n` 与 `gamma` 必须与分片 manifest 一致，否则拒绝（防止用错槽预算）。"""

    state_dim: int
    action_dim: int
    n: int
    gamma: float
    # v4 附录 02 §12 与交付包 AGENTS.md 的共享策略要求「同一目标条件学 A→B 与 B→A」。
    # 词表只有 1 项时 one-hot 恒为 [1.0]（= 给第一层加一个常量偏置），goal 对输出的影响恒为 0，
    # 而维度 / concat / forward 检查全都会过 ⇒ T17「同状态换 goal」连测试都构造不出来。
    # 所以缺省就是双向词表；单 goal 配置由 `_goal_onehot` 显式拒绝（B→C 交接单 C-1 / C-2）。
    goals: tuple[str, ...] = ("lift_A_to_B", "lift_B_to_A")
    hidden: int = 128
    xi_dim: int = XI_DIM
    lr_actor: float = 3e-4
    lr_critic: float = 3e-4
    lambda_bc: float = 1.0
    lambda_cont: float = 0.1
    tau: float = 0.005
    grad_clip: float = 1.0
    device: str = "cpu"          # 首版固定 CPU：不与 A/B 的 GPU 训练抢卡
    seed: int = 0
    chunk_len: int | None = None   # H，缺省 2n
    torch_threads: int = 2
    # C2 · T-C2-2（裁定 49.2）：消费侧 obs 键覆盖契约。
    # `None` ⇒ 用 `okc.derive_contract()`（只消费 state 类键）⇒ ACT 线的旧快照仍绿。
    # π₀.₅ 形态必须由调用方**显式声明**图像键；未声明而快照里带了图像 ⇒
    # `_obs_vector` 点名拒绝（`LearnerRefused`），不再静默丢图。
    obs_key_contract: okc.ObsKeyContract | None = None

    @property
    def H(self) -> int:
        return int(self.chunk_len or 2 * self.n)

    @property
    def goal_dim(self) -> int:
        return len(self.goals)

    def x_dim(self) -> int:
        """X=(h,g,C,ξ) 的宽度（不含动作块）。"""
        return self.state_dim + self.goal_dim + self.n * self.action_dim + self.xi_dim


@dataclass
class ShardBatch:
    """从分片装配出来的一批张量 + 出处审计信息。learner 只认这个，不再回读账本。"""

    view_dir: str
    manifest: dict[str, Any]
    used: dict[str, int] = field(default_factory=dict)
    excluded: dict[str, int] = field(default_factory=dict)
    td_rows: list[dict] = field(default_factory=list)
    bc_rows: list[dict] = field(default_factory=list)
    td: dict[str, Any] = field(default_factory=dict)
    bc: dict[str, Any] = field(default_factory=dict)
    xi_census: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    device: str = "cpu"

    @property
    def n_td(self) -> int:
        return int(self.used.get("td", 0))

    @property
    def n_bc(self) -> int:
        return int(self.used.get("bc", 0))


def _obs_vector(obs_store: ObsStore, x_ref: str | None, cfg: LearnerConfig, *, kind: str) -> np.ndarray:
    """`x_ref` → 状态向量。反查不到就拒绝：宁可停下，也不要拿零向量凑一个 batch。"""
    if not x_ref:
        raise LearnerRefused(f"{kind}: 分片行缺 x_ref，无法反查观测")
    try:
        obs = obs_store.get(x_ref)
    except KeyError as exc:
        raise LearnerRefused(
            f"{kind}: x_ref={x_ref!r} 在 ObsStore 里找不到（快照缺失或表征缓存已失效）") from exc
    # C2 · T-C2-2（裁定 49.2）：先判「存入键集合 vs 消费键集合」的覆盖，再拼状态向量。
    # 这一步原来不存在 ⇒ 图像键被静默丢弃、而宽度检查只看拼出来的向量所以恒过。
    # 实测证据（只读探针）：runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/probe_main.json
    #   4 个带图像变体的 vec_sha12 全部 = 4fd32aacc677，与 state-only 旧快照**逐字节相同**。
    # 宽度检查（下面 `!= cfg.state_dim`）语义**不动**：本层只补键覆盖，不改 state_dim。
    contract = cfg.obs_key_contract or okc.derive_contract()
    try:
        okc.check_coverage(obs.keys(), contract, kind=kind)
    except okc.ObsKeyCoverageViolation as exc:
        raise LearnerRefused(str(exc)) from exc
    parts = [np.asarray(obs[key], dtype=np.float32).reshape(-1)
             for key in contract.state_keys if key in obs]
    if not parts:
        raise LearnerRefused(f"{kind}: 快照 {x_ref!r} 里没有 state / environment_state")
    vec = np.concatenate(parts)
    if vec.shape[0] != cfg.state_dim:
        raise LearnerRefused(f"{kind}: 观测维度 {vec.shape[0]} != 配置 state_dim {cfg.state_dim}")
    return vec


def _goal_onehot(goal_id: str, cfg: LearnerConfig, *, kind: str) -> np.ndarray:
    if goal_id not in cfg.goals:
        raise LearnerRefused(f"{kind}: goal_id={goal_id!r} 不在配置词表 {cfg.goals} 里")
    if cfg.goal_dim < 2:
        # 单 goal 词表下 one-hot 恒为 [1.0]：形状全对、forward 不报错，但 goal 那一列是常量，
        # 等价于给第一层加固定偏置 ⇒ goal 对输出的影响恒为 0。这类缺陷**维度检查抓不到**
        # （B 的 6 个变异体里 B1 就是这种，只有 T17 能挡），所以在这里显式拒绝，
        # 把「无法验证」变成「拒绝启动」，而不是让一个恒真检查冒充 goal 贯通验收。
        raise LearnerRefused(
            f"{kind}: goals 词表只有 {cfg.goal_dim} 项 {tuple(cfg.goals)} ⇒ one-hot 恒为常量，"
            "不能声称已 goal-conditioned（T17「同状态换 goal」构造不出来）。"
            "要跑单 goal 的规格算例（如 B 黄金值 E1–E6），请直接构造 goal 张量，"
            "不要经 _goal_onehot —— 那条路径不主张 goal 条件，也就无需词表 ≥2。")
    vec = np.zeros(cfg.goal_dim, dtype=np.float32)
    vec[cfg.goals.index(goal_id)] = 1.0
    return vec


def _action_matrix(u: Any, cfg: LearnerConfig, *, kind: str, expect: int) -> np.ndarray:
    """分片里的 U（JSON 文本 → list）→ (expect, action_dim) 数组，逐维核对。"""
    if u is None:
        raise LearnerRefused(f"{kind}: 动作为空（u=None），不能当零动作训")
    arr = np.asarray(u, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[0] != expect or arr.shape[1] != cfg.action_dim:
        raise LearnerRefused(f"{kind}: 动作块形状 {arr.shape} != 期望 {(expect, cfg.action_dim)}")
    return arr


def load_shard_batch(view_dir: str | Path, obs_store: ObsStore, cfg: LearnerConfig) -> ShardBatch:
    """读一个导出目录 → 张量批。核内容身份、核 n/γ、核表征单一、核 mask，然后才装配。"""
    torch.set_num_threads(max(1, int(cfg.torch_threads)))
    rows, manifest = db.load_views(view_dir, verify=True)     # sha256 不符会抛 ViewExportTampered
    if int(manifest.get("n", -1)) != cfg.n:
        raise LearnerRefused(f"分片 n={manifest.get('n')} 与配置 n={cfg.n} 不一致（槽预算用错）")
    if abs(float(manifest.get("gamma", np.nan)) - cfg.gamma) > 1e-12:
        raise LearnerRefused(f"分片 gamma={manifest.get('gamma')} 与配置 {cfg.gamma} 不一致")
    versions = list(manifest.get("representation_versions") or [])
    if len(versions) > 1:
        raise LearnerRefused(f"分片混了多个表征版本 {versions}：一个训练批次只能有一个")

    excluded = {view: len(rows.get(view, [])) for view in NEVER_GRADIENT_VIEWS}
    notes: list[str] = [f"排除不进梯度的视图: {excluded}"]

    # ---------- td 视图 ----------
    td_rows = sorted(rows.get("td", []),
                     key=lambda r: (str(r["episode_id"]), str(r["goal_id"]), int(r["start_frame"])))
    expect_mask = list(db.e_segment_mask(cfg.H, cfg.n))
    state, goal, c_vec, xi, u_vec = [], [], [], [], []
    r_slot, gamma_slot, bootstrap = [], [], []
    n_state, n_goal, n_c, n_xi = [], [], [], []
    prev: dict | None = None
    for row in td_rows:
        mask = list(row.get("q_action_gradient_mask") or [])
        if mask != expect_mask:
            raise LearnerRefused(
                f"q_action_gradient_mask 与 e_segment_mask(H={cfg.H},n={cfg.n}) 不一致："
                f"{row['request_id']}")
        if row.get("r_slot") is None:
            raise LearnerRefused(f"td 行 {row['request_id']} 的 r_slot 为 None（不是 final）")
        state.append(_obs_vector(obs_store, row["x_ref"], cfg, kind=f"td/{row['request_id']}"))
        goal.append(_goal_onehot(str(row["goal_id"]), cfg, kind=f"td/{row['request_id']}"))
        u_mat = _action_matrix(row["u"], cfg, kind=f"td/{row['request_id']}", expect=cfg.n)
        # C_k = U_{k-1}（附录 02：X_{k+1}=(h_{t_k+n}, g, C_{k+1}=U_k, ξ)）。
        # 只有**紧邻的上一行**才能当 C：中间被隔离/换 goal/换 episode 就说明队列断过，
        # 这时按 has_c=0 处理，绝不能拿不相干的旧动作冒充承诺队列。
        contiguous = (prev is not None
                      and prev["episode_id"] == row["episode_id"]
                      and prev["goal_id"] == row["goal_id"]
                      and int(prev["start_frame"]) + cfg.n == int(row["start_frame"]))
        c_mat = (_action_matrix(prev["u"], cfg, kind="td/C", expect=cfg.n) if contiguous
                 else np.zeros((cfg.n, cfg.action_dim), dtype=np.float32))
        if not contiguous and prev is not None:
            notes.append(f"{row['request_id']}: 与上一 td 行不连续 ⇒ C=0, has_c=0")
        c_vec.append(c_mat.reshape(-1))
        xi.append(np.array([1.0 if contiguous else 0.0], dtype=np.float32))
        u_vec.append(u_mat.reshape(-1))
        r_slot.append(float(row["r_slot"]))
        gamma_slot.append(float(row["gamma_slot"]))
        bootstrap.append(1.0 if row["bootstrap_valid"] else 0.0)
        # 终局槽（L<=n）在导出里 `next_x_ref=None`：它压根没有下一帧。这种行
        # `bootstrap_valid=False`，目标退化成 R_{k,L}，Q̄ 项不进 y，所以零占位无害。
        # 但**声明要 bootstrap 却没有下一快照**是另一回事 —— 那说明下一状态不可确认，
        # 必须拒绝，绝不能拿零向量冒充 h_{t_k+n}（附录 02 §5：不能悄悄降级）。
        next_ref = row.get("next_x_ref")
        if next_ref:
            n_state.append(_obs_vector(obs_store, next_ref, cfg,
                                       kind=f"td-next/{row['request_id']}"))
        elif bool(row["bootstrap_valid"]):
            raise LearnerRefused(
                f"td 行 {row['request_id']} 声明 bootstrap 却缺 next_x_ref：下一快照不可确认")
        else:
            n_state.append(np.zeros(cfg.state_dim, dtype=np.float32))
            notes.append(f"{row['request_id']}: 终局槽无下一快照且不 bootstrap ⇒ next_state 零占位")
        n_goal.append(goal[-1])
        n_c.append(u_mat.reshape(-1))          # C_{k+1} = U_k
        n_xi.append(np.array([1.0], dtype=np.float32))   # 提交之后必然有队列在生效
        prev = row

    dev = cfg.device
    tensor = lambda arr, dtype=torch.float32: torch.as_tensor(np.asarray(arr), dtype=dtype, device=dev)
    td: dict[str, Any] = {}
    if td_rows:
        td = {
            "state": tensor(state), "goal": tensor(goal), "c": tensor(c_vec), "xi": tensor(xi),
            "u": tensor(u_vec), "r_slot": tensor(r_slot), "gamma_slot": tensor(gamma_slot),
            "bootstrap": tensor(bootstrap), "next_state": tensor(n_state), "next_goal": tensor(n_goal),
            "next_c": tensor(n_c), "next_xi": tensor(n_xi),
            "q_mask": tensor([expect_mask]),
            "request_ids": [str(r["request_id"]) for r in td_rows],
            "start_frames": [int(r["start_frame"]) for r in td_rows],
            "terminal_kinds": [str(r["terminal_kind"]) for r in td_rows],
        }
        # C 必须是常量：它是上一步决策的结果，本步不许对它求梯度（sg(C)）。
        assert td["c"].requires_grad is False, "C 必须不带梯度（sg(C)）"

    # ---------- bc 视图（纠正帧）----------
    bc_rows = sorted(rows.get("bc", []),
                     key=lambda r: (str(r["episode_id"]), int(r["start_frame"])))
    b_state, b_goal, b_c, b_xi, b_target, b_index, b_weight = [], [], [], [], [], [], []
    for row in bc_rows:
        mask = list(row.get("supervision_mask") or [])
        ones = [i for i, v in enumerate(mask) if v]
        if len(ones) != 1:
            raise LearnerRefused(f"bc 行 frame={row['start_frame']} 的 supervision_mask 应恰好一位，实得 {ones}")
        idx = ones[0]
        if not (cfg.n <= idx < 2 * cfg.n):
            raise LearnerRefused(f"bc 监督位 {idx} 不在 E 段 [n,2n)=[{cfg.n},{2 * cfg.n})")
        target = _action_matrix(row["u"], cfg, kind=f"bc/{row['start_frame']}", expect=1)[0]
        b_state.append(_obs_vector(obs_store, row["x_ref"], cfg, kind=f"bc/{row['start_frame']}"))
        b_goal.append(_goal_onehot(str(row["goal_id"]), cfg, kind=f"bc/{row['start_frame']}"))
        b_c.append(np.zeros(cfg.n * cfg.action_dim, dtype=np.float32))
        b_xi.append(np.zeros(XI_DIM, dtype=np.float32))
        b_target.append(target)
        b_index.append(idx - cfg.n)
        b_weight.append(float(row.get("supervision_weight") or 0.0))
    bc: dict[str, Any] = {}
    if bc_rows:
        bc = {"state": tensor(b_state), "goal": tensor(b_goal), "c": tensor(b_c), "xi": tensor(b_xi),
              "target": tensor(b_target), "e_index": tensor(b_index, dtype=torch.long),
              "weight": tensor(b_weight),
              "start_frames": [int(r["start_frame"]) for r in bc_rows],
              "action_fields": sorted({str(r.get("bc_action_field")) for r in bc_rows})}
        notes.append("BC 行的 C 无法从分片重建 ⇒ 首版按 C=0/has_c=0（已知近似）")

    # ---- ξ 覆盖面普查（B→C 交接单 §4：把「已知近似」从 notes 升级为每 batch 可量化）----
    # 为什么必须计数而不是只声明：v4 的 L_actor = −E[Q] + λ_BC·L_BC + λ_cont·L_continuity 里，
    # λ_BC 是「防 RL 破坏已有能力」的锚。BC 行按构造恒在 ξ=0（C 无法从分片重建），
    # 而 TD 行在队列连续时是 ξ=1、`next_xi` 恒为 1 —— 若锚只在 ξ=0 的输入半空间施力，
    # 那么「有 BC 锚保护」这个主张在部署区间（多数决策态 ξ=1）就**没有证据**。
    # 比例是 100% 还是 12% 决定这句话是「已知近似」还是「实质缺口」，只有计数能回答。
    def _xi1(vec: Any) -> bool:
        return float(np.asarray(vec, dtype=np.float64).reshape(-1)[XI_HAS_C]) == 1.0

    td_xi1 = sum(1 for vec in xi if _xi1(vec))
    bc_xi0 = sum(1 for vec in b_xi if not _xi1(vec))
    bc_anchor_covers_xi1 = bool(bc_rows) and bc_xi0 < len(bc_rows)
    xi_census: dict[str, Any] = {
        "xi_semantics": "ξ 第 0 位 = 决策时是否有承诺队列 C 正在生效（1 = 有）",
        "td_rows_total": len(td_rows),
        "td_rows_at_xi1": td_xi1,
        "td_rows_at_xi1_ratio": (td_xi1 / len(td_rows)) if td_rows else None,
        "bc_rows_total": len(bc_rows),
        "bc_rows_at_xi0": bc_xi0,
        "bc_rows_at_xi0_ratio": (bc_xi0 / len(bc_rows)) if bc_rows else None,
        "bc_c_forced_zero": bool(bc_rows),
        "bc_anchor_covers_xi1": bc_anchor_covers_xi1,
        "next_xi_always_one": bool(td_rows),
    }
    if bc_rows:
        notes.append(
            f"BC 锚的 ξ 覆盖面：{bc_xi0}/{len(bc_rows)} 行在 ξ=0 上计算"
            f"（TD 侧 ξ=1 的行 = {td_xi1}/{len(td_rows)}）⇒ "
            + ("BC 锚在 ξ=1 区间完全没有施力，「有 BC 锚保护」在部署区间暂无证据（实质缺口）"
               if not bc_anchor_covers_xi1 and td_xi1 > 0 else
               "BC 锚至少部分覆盖 ξ=1 区间"))

    return ShardBatch(view_dir=str(view_dir), manifest=manifest,
                      used={"td": len(td_rows), "bc": len(bc_rows)}, excluded=excluded,
                      td_rows=td_rows, bc_rows=bc_rows, td=td, bc=bc, xi_census=xi_census,
                      notes=notes, device=dev)


class DeterministicActor(torch.nn.Module):
    """π_θ(X) = E ∈ R^{n×d_a}，tanh 输出（首版动作域 [-1,1]）。

    只输出 E 段：结构上就没有 C/D 的头，所以「梯度只经 E」不靠 mask 兜底，而是无从违反。
    """

    def __init__(self, cfg: LearnerConfig):
        super().__init__()
        self.cfg = cfg
        self.net = torch.nn.Sequential(
            torch.nn.Linear(cfg.x_dim(), cfg.hidden), torch.nn.ReLU(),
            torch.nn.Linear(cfg.hidden, cfg.hidden), torch.nn.ReLU(),
            torch.nn.Linear(cfg.hidden, cfg.n * cfg.action_dim), torch.nn.Tanh())

    def forward(self, state, goal, c, xi):
        return self.net(torch.cat([state, goal, c, xi], dim=-1))


class QueueCritic(torch.nn.Module):
    """Q_φ(h, g, sg(C), chunk, ξ)：状态里带承诺队列 C，动作位是 H 长块（梯度只在 E 段）。"""

    def __init__(self, cfg: LearnerConfig):
        super().__init__()
        self.cfg = cfg
        in_dim = cfg.x_dim() + cfg.H * cfg.action_dim
        self.net = torch.nn.Sequential(
            torch.nn.Linear(in_dim, cfg.hidden), torch.nn.ReLU(),
            torch.nn.Linear(cfg.hidden, cfg.hidden), torch.nn.ReLU(),
            torch.nn.Linear(cfg.hidden, 1))

    def forward(self, state, goal, c, xi, chunk):
        return self.net(torch.cat([state, goal, c, xi, chunk], dim=-1)).squeeze(-1)


def build_nets(cfg: LearnerConfig) -> dict[str, Any]:
    """actor / critic + 各自 target（polyak）。首版确定性头，没有熵温度、没有 log_pi。"""
    torch.manual_seed(cfg.seed)
    actor = DeterministicActor(cfg).to(cfg.device)
    critic = QueueCritic(cfg).to(cfg.device)
    nets = {"actor": actor, "critic": critic,
            "actor_target": copy.deepcopy(actor), "critic_target": copy.deepcopy(critic),
            "opt_actor": torch.optim.Adam(actor.parameters(), lr=cfg.lr_actor),
            "opt_critic": torch.optim.Adam(critic.parameters(), lr=cfg.lr_critic),
            "cfg": cfg}
    for key in ("actor_target", "critic_target"):
        for param in nets[key].parameters():
            param.requires_grad_(False)
    return nets


def chunk_of(c_flat: torch.Tensor, e_flat: torch.Tensor, cfg: LearnerConfig) -> torch.Tensor:
    """拼 H 长动作块：`[sg(C) | E | D]`。D 段补零且不可训（首版 H=2n 时没有 D）。"""
    parts = [c_flat, e_flat]
    tail = cfg.H - 2 * cfg.n
    if tail > 0:
        parts.append(torch.zeros(c_flat.shape[0], tail * cfg.action_dim,
                                 dtype=e_flat.dtype, device=e_flat.device))
    elif tail < 0:
        raise LearnerRefused(f"H={cfg.H} < 2n={2 * cfg.n}：首版要求 H>=2n")
    return torch.cat(parts, dim=-1)


def td_targets(batch: ShardBatch, nets: dict, cfg: LearnerConfig) -> torch.Tensor:
    """`y_k = R_k + γ_slot·bootstrap·Q_φ̄(X_{k+1}, π_θ̄(X_{k+1}))`，逐行调 `db.td_target`。

    X_{k+1} 的 C 就是 U_k（分片里的 `next_c`，装配时已置为 u 的副本），
    终局槽 `bootstrap_valid=False` ⇒ 目标退化成 R_{k,L}，没有 bootstrap 项。
    """
    td = batch.td
    with torch.no_grad():
        e_next = nets["actor_target"](td["next_state"], td["next_goal"], td["next_c"], td["next_xi"])
        chunk_next = chunk_of(td["next_c"], e_next, cfg)
        q_next = nets["critic_target"](td["next_state"], td["next_goal"], td["next_c"],
                                       td["next_xi"], chunk_next)
    values = [db.td_target(float(r), float(gs), bool(bv), float(q))
              for r, gs, bv, q in zip(td["r_slot"].tolist(), td["gamma_slot"].tolist(),
                                      td["bootstrap"].tolist(), q_next.tolist())]
    return torch.tensor(values, dtype=torch.float32, device=cfg.device)


def bc_loss(batch: ShardBatch, nets: dict, cfg: LearnerConfig) -> torch.Tensor:
    """纠正帧的监督：只在 `supervision_mask` 指定的那一位上算加权 MSE。"""
    if not batch.bc:
        return torch.zeros((), device=cfg.device)
    bc = batch.bc
    e = nets["actor"](bc["state"], bc["goal"], bc["c"], bc["xi"]).view(-1, cfg.n, cfg.action_dim)
    pred = e[torch.arange(e.shape[0], device=cfg.device), bc["e_index"]]
    weight = bc["weight"]
    per_row = ((pred - bc["target"]) ** 2).sum(-1)
    return (weight * per_row).sum() / weight.sum().clamp(min=1e-9)


def continuity_loss(e_flat: torch.Tensor, c_flat: torch.Tensor, has_c: torch.Tensor,
                    cfg: LearnerConfig) -> torch.Tensor:
    """`L_continuity`：块内相邻动作不跳变 + 块边界接得上正在执行的 C 的最后一步。

    边界项只对 `has_c=1` 的行生效：prime/hold 槽没有前序队列，罚它等于凭空造约束。
    """
    e = e_flat.view(-1, cfg.n, cfg.action_dim)
    within = ((e[:, 1:] - e[:, :-1]) ** 2).sum(-1).mean() if cfg.n > 1 else torch.zeros((), device=e.device)
    last_c = c_flat.view(-1, cfg.n, cfg.action_dim)[:, -1]
    boundary = (((e[:, 0] - last_c) ** 2).sum(-1) * has_c.squeeze(-1)).sum() / has_c.sum().clamp(min=1.0)
    return within + boundary


def train_steps(batch: ShardBatch, nets: dict, cfg: LearnerConfig, steps: int = 1) -> list[dict]:
    """跑若干步真实更新，返回每步的分项损失（供人工核对，不只是看总 loss 下降）。"""
    if not batch.td:
        raise LearnerRefused("td 视图为空：没有合格样本可更新（不是失败，但也不该假装训了）")
    actor, critic = nets["actor"], nets["critic"]
    td = batch.td
    history = []
    for step in range(steps):
        y = td_targets(batch, nets, cfg)
        with torch.no_grad():
            e_detached = actor(td["state"], td["goal"], td["c"], td["xi"])
        q = critic(td["state"], td["goal"], td["c"], td["xi"],
                   chunk_of(td["c"], e_detached, cfg))
        critic_loss = torch.nn.functional.mse_loss(q, y)
        nets["opt_critic"].zero_grad(set_to_none=True)
        critic_loss.backward()
        torch.nn.utils.clip_grad_norm_(critic.parameters(), cfg.grad_clip)
        nets["opt_critic"].step()

        e = actor(td["state"], td["goal"], td["c"], td["xi"])
        q_actor = critic(td["state"], td["goal"], td["c"], td["xi"], chunk_of(td["c"], e, cfg))
        loss_q = -q_actor.mean()                       # L_Q^actor = -E[Q(h,g,sg(C),π(X),ξ)]
        loss_bc = bc_loss(batch, nets, cfg)
        loss_cont = continuity_loss(e, td["c"], td["xi"], cfg)
        actor_loss = loss_q + cfg.lambda_bc * loss_bc + cfg.lambda_cont * loss_cont
        nets["opt_actor"].zero_grad(set_to_none=True)
        actor_loss.backward()
        torch.nn.utils.clip_grad_norm_(actor.parameters(), cfg.grad_clip)
        nets["opt_actor"].step()

        with torch.no_grad():                            # polyak
            for key, target in (("actor", "actor_target"), ("critic", "critic_target")):
                for p_t, p_s in zip(nets[target].parameters(), nets[key].parameters()):
                    p_t.mul_(1.0 - cfg.tau).add_(p_s.detach(), alpha=cfg.tau)

        history.append({
            "step": step, "critic_loss": float(critic_loss), "actor_loss": float(actor_loss),
            "loss_q": float(loss_q), "loss_bc": float(loss_bc), "loss_cont": float(loss_cont),
            "q_mean": float(q.mean()), "y_mean": float(y.mean()),
            "y_min": float(y.min()), "y_max": float(y.max()),
            "finite": bool(torch.isfinite(critic_loss) and torch.isfinite(actor_loss)),
        })
    return history


def assemble_from_full_head(full: torch.Tensor, c_const: torch.Tensor, cfg: LearnerConfig,
                            *, wrong_c: bool = False, wrong_d: bool = False) -> torch.Tensor:
    """按 `chunk_of` 的同一规则，从「完整头的整块 H 长预测」拼出 critic 的动作输入。

    C 段取 `sg(C)` 常量、E 段取 `full[n·d_a : 2n·d_a]`、D 段取零常量。
    `wrong_c` / `wrong_d` 是**故意写错**的对照分支：把对应段换成策略自己的预测。
    没有这两个分支，「C/D 段梯度为 0」就无法证伪 —— 旧写法 `0.0*probe` 正是那种恒真断言
    （`grad_c` 与拼装规则无关地等于 0；`grad_d` 量到的是 Q 对 D *输入*的敏感度，本该非 0）。
    """
    n_da = cfg.n * cfg.action_dim
    parts = [full[..., :n_da] if wrong_c else c_const, full[..., n_da:2 * n_da]]
    if cfg.H > 2 * cfg.n:
        parts.append(full[..., 2 * n_da:] if wrong_d else torch.zeros_like(full[..., 2 * n_da:]))
    return torch.cat(parts, dim=-1)


def full_head_gradient_probe(critic: torch.nn.Module, state: torch.Tensor, goal: torch.Tensor,
                             c: torch.Tensor, xi: torch.Tensor, cfg: LearnerConfig) -> dict:
    """附录 02 §4.1／例2（= B 黄金值 E2 的 `gradients` 段）：∂(-Q)/∂(整块预测) 按 C/E/D 切片。

    契约要的是：**假如** actor 是完整头、对整块 H 都给预测，那么按上面的规则组装之后，
    C 段（已承诺状态）与 D 段（被后续推理替换）都拿不到这条 Q 动作梯度，只有 E 段（= U）能。
    判定按黄金值要求用 `== 0` / `!= 0` 严判，不设容差。

    同时返回两个 `wrong_*` 对照值：把拼装规则故意写错时对应段的梯度。它们必须非 0，
    否则上面那些 0 只是探针失灵（H=2n 时不存在 D 段，`wrong_d` 记 0 并由 `d_segment_width` 说明）。
    """
    n_da = cfg.n * cfg.action_dim
    full_dim = cfg.H * cfg.action_dim
    c_const = c.detach()                                  # sg(C)
    full = torch.zeros(state.shape[0], full_dim, device=c.device, dtype=c.dtype,
                       requires_grad=True)

    def seg_absmax(grad: torch.Tensor, lo: int, hi: int) -> float:
        block = grad[:, lo:hi]
        return float(block.abs().max()) if block.numel() else 0.0

    def grad_of(**wrong) -> torch.Tensor:
        chunk = assemble_from_full_head(full, c_const, cfg, **wrong)
        q = critic(state, goal, c, xi, chunk)
        return torch.autograd.grad(-q.sum(), full, allow_unused=True)[0]

    base = grad_of()
    bad_c = grad_of(wrong_c=True)
    bad_d = grad_of(wrong_d=True)
    return {
        "grad_c_absmax": seg_absmax(base, 0, n_da),
        "grad_e_absmax": seg_absmax(base, n_da, 2 * n_da),
        "grad_d_absmax": seg_absmax(base, 2 * n_da, full_dim),
        "wrong_c_grad_absmax": seg_absmax(bad_c, 0, n_da),
        "wrong_d_grad_absmax": seg_absmax(bad_d, 2 * n_da, full_dim),
        "d_segment_width": max(0, cfg.H - 2 * cfg.n) * cfg.action_dim,
        "c_requires_grad": bool(c.requires_grad),
        "segments": {"C": [0, cfg.n * cfg.action_dim],
                     "E": [n_da, 2 * n_da], "D": [2 * n_da, full_dim]},
    }


def perturbation_invariance_probe(critic: torch.nn.Module, state: torch.Tensor, goal: torch.Tensor,
                                  c: torch.Tensor, xi: torch.Tensor, cfg: LearnerConfig) -> dict:
    """B 黄金值 E2 的 `invariance` 段：P1/P2 下 `L_Q^actor` 数值不变，P3 下必须变。

    P0 基准；P1 改 C 段预测（X 里的真实 C 不变）；P2 改 D 段预测；P3 改 E 段预测。
    用**同一个** `full` 张量的不同取值算 loss，不是把探针乘 0 挂图（那种构造恒真）。
    取值用 `linspace` 而不是随机数，保证跨进程逐位可复现、不扰动全局 RNG。
    """
    n_da = cfg.n * cfg.action_dim
    full_dim = cfg.H * cfg.action_dim
    base = torch.linspace(-1.0, 1.0, full_dim, device=c.device, dtype=c.dtype)
    full = base.unsqueeze(0).expand(state.shape[0], full_dim).contiguous()

    def loss_of(f: torch.Tensor) -> float:
        q = critic(state, goal, c, xi, assemble_from_full_head(f, c.detach(), cfg))
        return float(-q.mean())

    p1, p2, p3 = full.clone(), full.clone(), full.clone()
    p1[:, :n_da] += 3.0                       # P1：任意改 C 段预测
    p2[:, 2 * n_da:] = p2[:, 2 * n_da:] * -2.0 + 1.0    # P2：任意改 D 段预测
    p3[:, n_da:2 * n_da] += 0.5               # P3：改 E 段预测
    return {"L_Q_P0": loss_of(full), "L_Q_P1": loss_of(p1),
            "L_Q_P2": loss_of(p2), "L_Q_P3": loss_of(p3)}


def gradient_isolation_report(batch: ShardBatch, nets: dict, cfg: LearnerConfig) -> dict:
    """在**真实分片数据**上复核附录 02 §4.1／例2：Q 的动作梯度只经 E 段。

    探针本体在 `full_head_gradient_probe`（与 B 黄金值 E2 共用同一实现，不各写一份）。
    这里额外核两件分片层面的事：learner 自己的 actor 只输出 E（结构上就没有 C/D 头），
    以及分片里的 `q_action_gradient_mask` 与 `e_segment_mask(H,n)` 逐位相同。
    """
    if not batch.td:
        return {"skipped": "td 视图为空"}
    td = batch.td
    actor, critic = nets["actor"], nets["critic"]
    row = {key: value[:1] for key, value in td.items() if torch.is_tensor(value)}
    n_da = cfg.n * cfg.action_dim

    e = actor(row["state"], row["goal"], row["c"], row["xi"])
    q = critic(row["state"], row["goal"], row["c"], row["xi"], chunk_of(row["c"], e, cfg))
    grad_e = torch.autograd.grad(-q.sum(), e, allow_unused=True)[0]
    probe = full_head_gradient_probe(critic, row["state"], row["goal"], row["c"], row["xi"], cfg)
    mask = list(db.e_segment_mask(cfg.H, cfg.n))
    return {
        "grad_e_absmax": float(grad_e.abs().max()) if grad_e is not None and grad_e.numel() else 0.0,
        "probe_grad_c_absmax": probe["grad_c_absmax"],
        "probe_grad_e_absmax": probe["grad_e_absmax"],
        "probe_grad_d_absmax": probe["grad_d_absmax"],
        "d_segment_width": probe["d_segment_width"],
        "probe_construction": ("对单个 full 张量求导后按段切片；C 段用 sg(C) 常量、D 段用零常量"
                               "拼装，不是 0.0*probe（那种构造恒为 0，证伪不了任何事）"),
        "falsifiable": ("把 c_const 换成 full[:, :n_da] 会让 probe_grad_c_absmax 变非 0；"
                        "把 D 段零常量换成 full[:, 2*n_da:] 会让 probe_grad_d_absmax 变非 0"),
        "c_requires_grad": bool(td["c"].requires_grad),
        "actor_out_width": int(e.shape[-1]),
        "expected_e_width": n_da,
        "shard_mask_equals_e_segment": [int(v) for v in td["q_mask"][0].tolist()] == mask,
        "e_segment_mask": mask,
        "H": cfg.H, "n": cfg.n,
    }


def gradient_isolation_falsification(batch: ShardBatch, nets: dict, cfg: LearnerConfig) -> dict:
    """把拼装规则**故意写错**，确认探针会亮；否则「C/D 梯度为 0」可能只是探针失灵。

    两种错法都是真实代码里最容易犯的：`wrong_c` 忘了 `sg(C)`、`wrong_d` 忘了补零。
    H=2n 时不存在 D 段，`wrong_d` 记 0 并由 `d_segment_width` 说明原因，不算失败。
    """
    if not batch.td:
        return {"skipped": "td 视图为空"}
    td = batch.td
    row = {key: value[:1] for key, value in td.items() if torch.is_tensor(value)}
    probe = full_head_gradient_probe(nets["critic"], row["state"], row["goal"],
                                     row["c"], row["xi"], cfg)
    return {"wrong_c_grad_absmax": probe["wrong_c_grad_absmax"],
            "wrong_d_grad_absmax": probe["wrong_d_grad_absmax"],
            "d_segment_width": probe["d_segment_width"],
            "note": "故意写错拼装规则后对应段梯度必须非 0；否则隔离断言的 0 是探针失灵"}


def target_audit(batch: ShardBatch, nets: dict, cfg: LearnerConfig) -> list[dict]:
    """逐行把 target 拆开给人核对：R_k、γ_slot、是否 bootstrap、Q̄、y。"""
    y = td_targets(batch, nets, cfg)
    td = batch.td
    with torch.no_grad():
        e_next = nets["actor_target"](td["next_state"], td["next_goal"], td["next_c"], td["next_xi"])
        q_next = nets["critic_target"](td["next_state"], td["next_goal"], td["next_c"],
                                       td["next_xi"], chunk_of(td["next_c"], e_next, cfg))
    out = []
    for i, rid in enumerate(td["request_ids"]):
        out.append({
            "request_id": rid, "start_frame": td["start_frames"][i],
            "terminal_kind": td["terminal_kinds"][i],
            "r_slot": float(td["r_slot"][i]), "gamma_slot": float(td["gamma_slot"][i]),
            "bootstrap_valid": bool(td["bootstrap"][i]), "q_next": float(q_next[i]),
            "y": float(y[i]),
            "y_handcheck": float(td["r_slot"][i]) + (float(td["gamma_slot"][i]) * float(q_next[i])
                                                     if bool(td["bootstrap"][i]) else 0.0),
        })
    return out


def param_snapshot(nets: dict) -> dict[str, float]:
    """参数指纹：更新前后对比，证明真的动了（而不是 loss 变了但参数没变）。"""
    out = {}
    for key in ("actor", "critic", "actor_target", "critic_target"):
        flat = torch.cat([p.detach().reshape(-1) for p in nets[key].parameters()])
        out[key] = float(flat.sum())
    return out
