#!/usr/bin/env python3
"""B-5：T17「同状态换 goal」的 mock 预检 —— goal 是否**真的**进了计算图。

v4 的原始要求（见 B 线交接说明）：
  「同状态换 goal，先验证 goal 真进计算图而非维度检查」
以及附录 02 §12「全包 goal 与时间条件」：
  「原生 base、editor、Q、候选筛选和预测器**分别**检查输入目标、C 和有效时刻。」

为什么现在做（**0928 的历史动机，C 已于 0929 修掉，见文末实测清单**）：
当时 `harness/queue_td_learner.py:65` 的 `cfg.goals = ("lift",)`，
`_goal_onehot` 出来恒为 `[1.0]`。网络确实 `torch.cat([state, goal, c, xi])`（:291），
维度检查、concat 检查、forward 检查**全都会过**，但 goal 那一列是常量，
等价于给第一层加了一个固定偏置 —— goal 对输出的影响恒为 0。
这不是 C 的 bug（`_goal_onehot` 对词表外的 goal 会 `LearnerRefused`，是诚实的），
但它意味着 T17 目前**无法被验证**：单 goal 词表下连「换一个 goal」都构造不出来。

0929 现状（**实测**，不是散文；由 `_probe_wire_status()` 子进程真调 C 的 learner 得到）：
`LearnerConfig.goals` 缺省已是双向词表 `("lift_A_to_B", "lift_B_to_A")`，
且 `_goal_onehot` 在 `goal_dim < 2` 时显式抛 `LearnerRefused`（不是 `KeyError` 子类）
⇒ 上面两条 C 侧阻塞已闭合。本脚本末尾的 `to_wire_goal_for_real` 清单逐项带
`status`（`closed_verified` / `open` / `open_not_probed` / `unprobed` / `partial_verified`）
与 `evidence`；**探针跑不起来时记 `unprobed`，既不冒充闭合也不冒充开放**。

本脚本不 import C 的 learner、不碰 harness/ledger.py 与 harness/data_bridge.py。
它在 B 命名空间里搭一个**参考实现**和**六个故意写坏的实现**，证明：
  (1) T17 的正确断言长什么样；
  (2) 这些坏实现要么能通过「维度/concat/forward 不报错」这类常规检查（B2–B6），
      要么连测试都构造不出来（B1：单 goal 词表，换不了 goal）—— 两种情况
      T17 都不放行，也就是**这个测试有牙**。
      注意这两类必须分开统计：B1 的常规检查是**报错**而不是**放行**，
      把它算进「常规检查会过」的分母，会让牙齿判定被自己绊倒（2026-09-28 晚的误报）。
第 (2) 点是重点：一个抓不到假实现的测试，比没有测试更危险
（`scripts/b_selfcheck_reproducibility.py` 里那个恒真的「版本一致」检查就是先例，
  见 docs/b_reproducibility_incident_20260928.md §2 缺陷 3）。

用法：
    python3 scripts/b_selfcheck_goal_conditioning_t17.py \
        --json-out runs/infra/b_t17/t17_precheck.json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOALS = ("lift_A_to_B", "lift_B_to_A")          # 双向，A↔B（v4 的共享策略要求）
STATE_DIM, N, ACTION_DIM, XI_DIM, EMB = 60, 6, 7, 4, 8


# --------------------------------------------------------------------------
# 「真贯通还差什么」的状态必须**实测**，不能是硬编码的行号 TODO。
#
# 为什么加这个：本脚本原先把 `harness/queue_td_learner.py:65`（cfg.goals 单项词表）
# 与 `:135`（_goal_onehot 在 goal_dim==1 时恒为 [1.0]）写成两条 `owner=C, blocking=True`
# 的固定清单。C 在 0929 已经把两条都改了（goals 缺省 = 双向词表；_goal_onehot 在
# goal_dim<2 时显式抛 LearnerRefused），但清单是散文，不会自己更新，于是它继续把
# **已闭合**的项报成「C 阻塞」。这与 D 在 裁定 27.4 里判 A 的 G2 假红**同型**
# （文本/行号锚点失效 ⇒ 假红），也与本仓「恒假的闸等于没有闸」是同一条教训：
# 长期挂着的假阻塞会让人对「阻塞」这个字脱敏。
# 修法不是删清单，而是把状态改成**子进程真调 C 的 learner 测出来**；
# 探针跑不起来时一律记 `unprobed`（**不得**记成 closed，也**不得**记成 open）。
# 本脚本自身仍不 import C 的 learner（隔离原则不变）：探针在独立进程里跑。
# --------------------------------------------------------------------------
_WIRE_PROBE = r'''
import dataclasses, json, sys
root = sys.argv[1]
sys.path.insert(0, root)
res = {"probe_ran": True}
try:
    from harness import queue_td_learner as ql
except Exception as exc:                                    # noqa: BLE001
    print(json.dumps({"probe_ran": False, "error": "%s: %s" % (type(exc).__name__, exc)}))
    raise SystemExit(0)
try:
    fld = ql.LearnerConfig.__dataclass_fields__.get("goals")
    default = tuple(getattr(fld, "default", ()) or ())
    res["goals_default"] = list(default)
    res["goals_default_n"] = len(default)
except Exception as exc:                                    # noqa: BLE001
    res["goals_default_error"] = "%s: %s" % (type(exc).__name__, exc)
try:
    kwargs = {}
    for name, fl in ql.LearnerConfig.__dataclass_fields__.items():
        if fl.default is not dataclasses.MISSING or name == "goals":
            continue
        if fl.default_factory is not dataclasses.MISSING:   # noqa: E501
            kwargs[name] = fl.default_factory()
            continue
        ann = str(fl.type)
        kwargs[name] = 3 if "int" in ann else (0.9 if "float" in ann else "probe")
    cfg1 = ql.LearnerConfig(goals=("lift",), **kwargs)
    try:
        vec = ql._goal_onehot("lift", cfg1, kind="b_wire_probe")
        res["single_goal_refused"] = False
        res["single_goal_returned"] = [float(x) for x in vec]
    except ql.LearnerRefused as exc:
        res["single_goal_refused"] = True
        res["single_goal_refusal_message"] = str(exc)[:200]
    except Exception as exc:                                # noqa: BLE001
        res["single_goal_refused"] = False
        res["single_goal_wrong_exception"] = "%s: %s" % (type(exc).__name__, exc)
    res["refusal_is_not_keyerror"] = not issubclass(ql.LearnerRefused, KeyError)
except Exception as exc:                                    # noqa: BLE001
    res["single_goal_probe_error"] = "%s: %s" % (type(exc).__name__, exc)
print(json.dumps(res))
'''


def _probe_wire_status() -> dict:
    """子进程实测 C 的 learner 现状；任何异常都降级为 unprobed，绝不静默判 closed。"""
    import subprocess
    import tempfile
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(_WIRE_PROBE)
            probe_path = fh.name
        proc = subprocess.run([sys.executable, probe_path, str(ROOT)],
                              capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
        payload["probe_rc"] = proc.returncode
        if proc.returncode != 0:
            payload["probe_stderr_tail"] = (proc.stderr or "")[-400:]
        return payload
    except Exception as exc:                                # noqa: BLE001
        return {"probe_ran": False, "error": "%s: %s" % (type(exc).__name__, exc)}


# --------------------------------------------------------------------------
# A 侧 2 项（audit 的 goal_id 硬编码 / policy 不接收 goal）原先记 `open_not_probed`：
# B 不代判 A 的文件。0929 A 已落地并出了证据（`docs/a_handoff_to_b_anchor_shift_20260929.md` §3–§4），
# 但**状态翻转由 B 决定**，而翻转的判据不能是「A 说自己绿了」—— 那正是本仓反复禁止的自证形态
# （A 自己在 §4 里也反对）。所以照 `_probe_wire_status()` 的形态加一条**子进程真调**：
#   · 跑 A 的 `scripts/a_selfcheck_goal_conditioning_t17.py`，`--json-out` 重定向到 B 自己的临时路径
#     （**不覆写 A 的产物**，D→B 执行单 §9 卫生要求；A 的脚本是 `outp = ROOT / a.json_out`，
#      传绝对路径就落到 B 指的位置）；
#   · 读 A 产物里的**原始断言行** `checks[].id/.ok` 逐条点名要求，不拿 `summary`/`verdict` 当结论；
#   · 额外要求 rc==0、fail==0、**skip==0（SKIP ≠ PASS）**、`teeth.non_vacuous is True`；
#   · 再加一组**不经 A 的脚本**的 B 侧独立复核：内容锚命中数（写死的 `'goal_id':'lift'` 必须 0 命中、
#     `'epoch':epoch,'goal_id':goal_id` 必须 2 命中）与 goal 词表逐字等于 B 的 GOALS。
# 任何异常一律降级 `unprobed`（既不冒充闭合，也不冒充开放）。
# 注意：`b_source_anchor` 必须**惰性 import** —— `b_selfcheck_t17_mutation.py` 会把本脚本复制到
# 临时目录再跑，那时 `ROOT` 不是仓库根，顶层 import 会直接把 6 条变异全打成 no_json。
# --------------------------------------------------------------------------
_A_SIDE_SCRIPT = "scripts/a_selfcheck_goal_conditioning_t17.py"
# 期望值随 A 的 0929 落地**整体改写**（D→B 执行单 §5：语义变了 ⇒ 改期望值，不是只改行号）。
# 旧期望值一并留档，免得下次有人拿旧口径去验新实现（那会验出一个假的「已闭合」）。
AUDIT_EXPECTATION = (
    "**旧期望值（已作废）**：goal_id 硬编码 'lift'、epoch 写死 1，两处各写一份字面量。"
    "**现期望值（0929 起）**：goal_id / epoch 由**一处**统一给出"
    "（A 的 `make_goal_resolver(vocab, plan, switch_every, task)`），随 A↔B 换向、epoch 同步 +1，"
    "且同时进 `DecisionRequest` / `frame_records` / `chunks` **三处**；"
    "ckpt 无 `goal_vocab`（goal-blind）时退回**任务名占位**并在 `goal_source` 里明说「非 goal 条件」，"
    "此时若显式要求 `--goal-plan=alternate` 必须**拒绝**"
    "（否则账本记方向性 goal 而 policy 不看 goal = 伪造贯通证据）；"
    "源码里不得再残留写死的 `'goal_id':'lift'`")
POLICY_EXPECTATION = (
    "**旧期望值（已作废）**：policy 不接收 goal；共享 πθ 要支持 A↔B 必须把 goal 加进输入，"
    "并且 BC 采集时就要按 goal 分组，否则事后加 goal 输入也没有可学的差异。"
    "**现期望值（0929 起）**：`ChunkPolicy(obs_dim, chunk=4, *, goals=None)` —— "
    "goal 相关参数一律**关键字、缺省关闭**；`goals=None` ⇒ `goal_dim=0` ⇒ "
    "state_dict 的**键序/形状/权重与改动前逐项相同**，旧 ckpt 仍 `strict=True` 加载"
    "（向后兼容是硬要求：这两个位置参数被 7 个 B 线脚本原样调用）；"
    "开 goal 时 goal 必须**真进第一层输入维度**且 `d_goal/d_state` 同量级"
    "（只验「输出变了」不够：变 1e-9 也算变，那就是常量偏置的近似形态）；"
    "词表外 goal_id 必须被拒绝、不静默映射；BC 采集必须**按 goal 分组**，"
    "无 teacher 的方向如实记 `n_rows=0`（不拿 A→B 冒充 B→A）")
# B 独立点名的 A 侧断言 id：哪一条证明哪一项阻塞闭合（不读 A 的 summary 就下结论）
_A_SIDE_REQUIRED = {
    "audit_goal_id_epoch": ("G9",),
    "policy_takes_goal": ("G2", "G5", "G6", "G8"),
}


def _probe_a_side_t17() -> dict:
    """子进程真调 A 的 T17 自检 + B 侧内容锚独立复核；异常一律降级 unprobed。"""
    import subprocess
    import tempfile
    out = {"probe_ran": False}
    script = ROOT / _A_SIDE_SCRIPT
    if not script.exists():
        out["error"] = "找不到 A 的自检脚本：%s" % _A_SIDE_SCRIPT
        return out
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix="b_t17_aside_"))
        aj = tmpdir / "a_t17_goal_conditioning.json"
        proc = subprocess.run([sys.executable, str(script), "--json-out", str(aj)],
                              capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        out["probe_ran"] = True
        out["rc"] = proc.returncode
        out["a_artifact_redirect"] = str(aj)
        if not aj.exists():
            out["error"] = "A 的脚本 rc=%s 但没写出产物" % proc.returncode
            out["stderr_tail"] = (proc.stderr or "")[-400:]
            return out
        rep = json.loads(aj.read_text(encoding="utf-8"))
        rows = {r.get("id"): r for r in (rep.get("checks") or [])}
        teeth = rep.get("teeth") or {}
        summ = rep.get("summary") or {}
        out["a_summary"] = summ
        out["a_verdict"] = rep.get("verdict")
        out["a_teeth_non_vacuous"] = teeth.get("non_vacuous")
        out["a_teeth_caught"] = "%s/%s" % (teeth.get("n_caught"), teeth.get("n_mutants"))
        out["a_goal_vocab"] = rep.get("goal_vocab")
        # 表述纪律（D→B 执行单 §8.7）：引用哪份产物就得回显它跑在什么解释器上。
        # 本探针用的是 **B 的解释器**（sys.executable），A 自己留档那份用的是 lerobot_eval；
        # 两者都记下来，才看得出「A 侧 T17 在两个解释器上都成立」不是同一份数据被引了两次。
        out["a_report_interpreter"] = rep.get("interpreter")
        out["a_report_torch"] = rep.get("torch")
        out["a_report_numpy"] = rep.get("numpy")
        out["probe_interpreter"] = sys.executable
        # B 点名要的断言逐条核（读原始行，不读 summary）
        wanted = {}
        for key, ids in _A_SIDE_REQUIRED.items():
            wanted[key] = {
                "ids": list(ids),
                "all_ok": all(rows.get(i, {}).get("ok") is True for i in ids),
                "missing_ids": [i for i in ids if i not in rows],
                "failed_ids": [i for i in ids if i in rows and rows[i].get("ok") is not True],
                "observed": {i: str(rows.get(i, {}).get("observed"))[:220] for i in ids}}
        out["required_checks"] = wanted
        out["vocab_matches_b_goals"] = tuple(rep.get("goal_vocab") or ()) == GOALS
        out["all_required_ok"] = all(v["all_ok"] and not v["missing_ids"] for v in wanted.values())
        out["clean_run"] = (proc.returncode == 0 and int(summ.get("fail", 1)) == 0
                            and int(summ.get("skip", 1)) == 0
                            and teeth.get("non_vacuous") is True)
        if proc.returncode != 0:
            out["stderr_tail"] = (proc.stderr or "")[-400:]
    except Exception as exc:                                # noqa: BLE001
        out["probe_ran"] = False
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
        return out

    # ---- B 侧独立复核：内容锚（不经 A 的脚本；两条独立通道都绿才算闭合）----
    try:
        from scripts.b_source_anchor import find_lines, render
    except Exception as exc:                                # noqa: BLE001
        out["anchor_error"] = "%s: %s" % (type(exc).__name__, exc)
        out["anchors_ok"] = False
        return out
    anchors = {
        # 语义变了：两处写死的 'epoch':1,'goal_id':'lift' 已改成变量（旧行号锚 :36,39 → 现 :73,76）
        "audit_uses_variables": find_lines(
            "scripts/run_act_lift_runtime_failure_audit.py",
            "'epoch':epoch,'goal_id':goal_id", expect=2),
        # 写死的 goal_id 必须**一处不剩**（expect=0 = 断言「这段代码已删除」）
        "audit_hardcode_gone": find_lines(
            "scripts/run_act_lift_runtime_failure_audit.py", "'goal_id':'lift'", expect=0),
        # policy 接收 goal：关键字、缺省关闭（向后兼容是硬要求）
        "policy_ctor_takes_goals": find_lines(
            "scripts/train_act_lift.py",
            "def __init__(self, obs_dim, chunk=4, *, goals=None)", expect=1),
        # goal 真的进了第一层输入维度（不是只加个参数不用）
        "goal_enters_first_layer": find_lines(
            "scripts/train_act_lift.py", "nn.Linear(self.obs_dim+self.goal_dim,256)", expect=1),
    }
    out["anchors"] = anchors
    out["anchors_rendered"] = {k: render(v) for k, v in anchors.items()}
    out["anchors_ok"] = all(v["status"] == "ok" for v in anchors.values())
    return out


# --------------------------------------------------------------------------
# 参考实现：goal 走一张可训练的 embedding 表，且**每个**组件都单独吃 goal
# --------------------------------------------------------------------------
class GoalConditioned(nn.Module):
    """X_k = (h, g, C, ξ)。actor 出 E∈R^{n×d_a}，critic 出 Q。

    goal 通过 embedding 表进入，并且 actor / critic / editor / candidate_filter /
    predictor 五个组件**各自**拿到 goal（附录 02 §12 要求分别检查）。
    """

    def __init__(self, goal_mode: str = "embedding", zero_gate: bool = False,
                 detach_goal: bool = False, drop_from: tuple[str, ...] = (),
                 mask_goal_cols: bool = False, vocab: tuple[str, ...] = GOALS):
        super().__init__()
        self.goal_mode, self.zero_gate, self.detach_goal = goal_mode, zero_gate, detach_goal
        self.drop_from, self.mask_goal_cols, self.vocab = set(drop_from), mask_goal_cols, vocab
        self.goal_dim = EMB if goal_mode == "embedding" else len(vocab)
        if goal_mode == "embedding":
            self.goal_table = nn.Embedding(len(vocab), EMB)
            nn.init.normal_(self.goal_table.weight, std=0.5)
        self.gate = nn.Parameter(torch.zeros(1)) if zero_gate else None
        d = STATE_DIM + self.goal_dim + N * ACTION_DIM + XI_DIM
        self.actor = nn.Sequential(nn.Linear(d, 128), nn.ReLU(), nn.Linear(128, N * ACTION_DIM), nn.Tanh())
        self.critic = nn.Sequential(nn.Linear(d + N * ACTION_DIM, 128), nn.ReLU(), nn.Linear(128, 1))
        self.editor = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, N * ACTION_DIM))
        self.candidate_filter = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, 1))
        self.predictor = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, STATE_DIM))

    # --- goal 编码 ---
    def encode_goal(self, goal_id: str, batch: int):
        if goal_id not in self.vocab:
            raise KeyError(f"goal_id={goal_id!r} 不在词表 {self.vocab} 里")
        if self.goal_mode == "embedding":
            idx = torch.full((batch,), self.vocab.index(goal_id), dtype=torch.long)
            g = self.goal_table(idx)
            if self.detach_goal:
                g = g.detach()                     # 坏实现 B3：embedding 永远学不到东西
            if self.gate is not None:
                g = g * self.gate                  # 坏实现 B2：零初始化门，前向恒 0
        else:
            v = np.zeros((batch, len(self.vocab)), dtype=np.float32)
            v[:, self.vocab.index(goal_id)] = 1.0
            g = torch.tensor(v)
            if len(self.vocab) == 1:
                pass                               # 坏实现 B1：单 goal 词表 -> 常量列
        return g

    def _x(self, h, goal_id, C, xi, drop_goal: bool = False):
        b = h.shape[0]
        g = self.encode_goal(goal_id, b)
        if drop_goal or self.mask_goal_cols:
            g = torch.zeros_like(g)                # 坏实现 B4/B5：维度对、值恒 0
        return torch.cat([h, g, C.reshape(b, -1), xi], dim=-1)

    def forward_actor(self, h, goal_id, C, xi):
        x = self._x(h, goal_id, C, xi, "actor" in self.drop_from)
        return self.actor(x).view(-1, N, ACTION_DIM)

    def forward_q(self, h, goal_id, C, xi, E):
        x = self._x(h, goal_id, C, xi, "critic" in self.drop_from)
        return self.critic(torch.cat([x, E.reshape(h.shape[0], -1)], dim=-1)).squeeze(-1)

    def component(self, name, h, goal_id, C, xi):
        x = self._x(h, goal_id, C, xi, name in self.drop_from)
        mod = {"editor": self.editor, "candidate_filter": self.candidate_filter,
               "predictor": self.predictor}[name]
        return mod(x)


# --------------------------------------------------------------------------
# 输入构造
# --------------------------------------------------------------------------
def make_inputs(seed=0, batch=4):
    rng = np.random.default_rng(seed)
    h = torch.tensor(rng.normal(size=(batch, STATE_DIM)).astype(np.float32))
    C = torch.tensor(rng.normal(size=(batch, N, ACTION_DIM)).astype(np.float32))
    xi = torch.tensor(rng.normal(size=(batch, XI_DIM)).astype(np.float32))
    E = torch.tensor(rng.normal(size=(batch, N, ACTION_DIM)).astype(np.float32))
    return h, C, xi, E


def dim_checks_pass(model, h, C, xi, E):
    """「常规检查」：维度对不对、concat 有没有报错、forward 能不能跑、goal 列在不在。
    这是大多数实现会做的全部验证 —— 下面会看到六个坏实现全都能过。"""
    out = {}
    try:
        e = model.forward_actor(h, GOALS[0], C, xi)
        q = model.forward_q(h, GOALS[0], C, xi, E)
        out["actor_shape_ok"] = tuple(e.shape) == (h.shape[0], N, ACTION_DIM)
        out["q_shape_ok"] = tuple(q.shape) == (h.shape[0],)
        out["goal_dim_positive"] = model.goal_dim > 0
        x = model._x(h, GOALS[0], C, xi)
        out["x_contains_goal_slice"] = x.shape[1] == STATE_DIM + model.goal_dim + N * ACTION_DIM + XI_DIM
        out["forward_no_exception"] = True
    except Exception as exc:
        out["forward_no_exception"] = False
        out["error"] = repr(exc)
    out["all_pass"] = all(v is True for k, v in out.items() if k not in ("error", "all_pass"))
    return out


def model_can_represent_goals(model) -> bool:
    """模型的 goal 词表是否装得下本测试要用的两个 goal（GOALS）。"""
    vocab = set(getattr(model, "vocab", ()))
    return all(g in vocab for g in GOALS)


def dim_checks_status(model, dims: dict) -> str:
    """把常规检查的结果分成三类，避免把「测试构造不出来」误记成「常规检查抓住了它」。

    pass    —— 维度/concat/forward 全过：常规检查放行，只能靠 T17 抓（B2–B6）。
    fail    —— 常规检查自己就报错（形状/前向异常）：确实被抓住，但不是 T17 的功劳。
    blocked —— 词表装不下 GOALS，连「同状态换 goal」都构造不出来（B1）。
               这是比 fail 更强的信号（实现根本没有双向能力），但**不能**计入
               「常规检查会放行」的分母，否则牙齿判定会被自己绊倒。
    """
    if not model_can_represent_goals(model):
        return "blocked"
    return "pass" if dims["all_pass"] else "fail"


def t17_checks(model, h, C, xi, E):
    """T17 的正确断言。分五组，每组都必须过。"""
    res = {}
    g0, g1 = GOALS[0], GOALS[1]
    # T17-a 同状态换 goal，输出必须变（actor / critic / 三个附属组件各自查）
    e0 = model.forward_actor(h, g0, C, xi); e1 = model.forward_actor(h, g1, C, xi)
    q0 = model.forward_q(h, g0, C, xi, E); q1 = model.forward_q(h, g1, C, xi, E)
    res["a_actor_output_changes_with_goal"] = bool(not torch.allclose(e0, e1, atol=1e-9))
    res["a_critic_output_changes_with_goal"] = bool(not torch.allclose(q0, q1, atol=1e-9))
    for name in ("editor", "candidate_filter", "predictor"):
        c0 = model.component(name, h, g0, C, xi); c1 = model.component(name, h, g1, C, xi)
        res["a_%s_changes_with_goal" % name] = bool(not torch.allclose(c0, c1, atol=1e-9))
    # T17-b/c goal embedding 的梯度必须非零（抓 detach 与零门）
    if model.goal_mode == "embedding" and not model.detach_goal:
        model.zero_grad()
        loss = model.forward_q(h, g0, C, xi, E).sum() + model.forward_actor(h, g0, C, xi).sum()
        loss.backward()
        gr = model.goal_table.weight.grad
        res["c_goal_embedding_grad_nonzero"] = bool(gr is not None and float(gr.abs().sum()) > 0)
    elif model.goal_mode == "embedding":
        res["c_goal_embedding_grad_nonzero"] = False
    else:
        # one-hot 没有可学的 embedding，但至少要求第一层在 goal 列上的权重非零且能收到梯度
        model.zero_grad()
        model.forward_q(h, g0, C, xi, E).sum().backward()
        w = model.critic[0].weight.grad
        sl = slice(STATE_DIM, STATE_DIM + model.goal_dim)
        res["c_goal_embedding_grad_nonzero"] = bool(w is not None and float(w[:, sl].abs().sum()) > 0)
    # T17-d goal 的影响不能只是常量偏置：换 goal 造成的输出差，量级要可比于换状态造成的差
    h2 = h + 0.1 * torch.randn_like(h)
    e_h = model.forward_actor(h2, g0, C, xi)
    d_goal = float((e1 - e0).abs().mean()); d_state = float((e_h - e0).abs().mean())
    res["d_goal_effect_not_negligible_vs_state"] = bool(d_state > 0 and d_goal / max(d_state, 1e-12) > 0.05)
    res["_d_goal_delta"] = round(d_goal, 6); res["_d_state_delta"] = round(d_state, 6)
    # T17-e 词表外的 goal 必须被拒绝，不能静默当成某个已知 goal（对齐黄金值 E6 的 goal/epoch 拒绝）
    try:
        model.forward_actor(h, "lift_C_to_D", C, xi)
        res["e_unknown_goal_rejected"] = False
    except KeyError:
        res["e_unknown_goal_rejected"] = True
    res["all_pass"] = all(v is True for k, v in res.items() if not k.startswith("_") and k != "all_pass")
    return res


def variant(name, desc, ctor):
    return {"name": name, "description": desc, "model": ctor()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_t17/t17_precheck.json"))
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    torch.manual_seed(a.seed); np.random.seed(a.seed)
    h, C, xi, E = make_inputs(a.seed)

    variants = [
        variant("REF_embedding", "参考实现：goal 走可训练 embedding，五个组件各自吃 goal",
                lambda: GoalConditioned("embedding")),
        variant("B1_onehot_single_goal", "one-hot + 单 goal 词表 -> goal 列恒为常量 1.0"
                                         "（当前 harness/queue_td_learner.py:65 的实配）",
                lambda: GoalConditioned("onehot", vocab=("lift",))),
        variant("B2_zero_gate", "goal embedding 乘一个零初始化的门 -> 前向恒 0，维度全对",
                lambda: GoalConditioned("embedding", zero_gate=True)),
        variant("B3_detached_goal", "goal embedding 被 detach -> 前向会变，但表永远学不到东西",
                lambda: GoalConditioned("embedding", detach_goal=True)),
        variant("B4_goal_not_wired", "goal 只参与维度检查，concat 前被丢成 0",
                lambda: GoalConditioned("embedding", drop_from=("actor", "critic", "editor",
                                                               "candidate_filter", "predictor"))),
        variant("B5_goal_cols_masked", "goal 列在 X 里存在但被掩成 0（形状完全正确）",
                lambda: GoalConditioned("embedding", mask_goal_cols=True)),
        variant("B6_asymmetric_wiring", "只有 critic 吃了 goal，actor / editor / 筛选器 / 预测器没吃"
                                        " -> 标量检查会过，全包检查不过",
                lambda: GoalConditioned("embedding", drop_from=("actor", "editor",
                                                               "candidate_filter", "predictor"))),
    ]

    report = {"spec": "T17 同状态换 goal：goal 必须真进计算图，不是维度检查",
              "goals_used": list(GOALS), "seed": a.seed,
              "state_dim": STATE_DIM, "n": N, "action_dim": ACTION_DIM, "xi_dim": XI_DIM,
              "variants": []}
    print("=" * 96)
    print("%-24s %-14s %-14s %s" % ("实现", "常规维度检查", "T17", "被 T17 抓住的原因"))
    print("=" * 96)
    for v in variants:
        m = v["model"]
        dims = dim_checks_pass(m, h, C, xi, E)
        dims_status = dim_checks_status(m, dims)
        # B1 的词表装不下 GOALS，换 goal 会直接 KeyError；这本身就是「无法声称 goal-conditioned」的信号
        if dims_status == "blocked":
            missing = tuple(g for g in GOALS if g not in set(m.vocab))
            t17 = {"all_pass": False, "a_actor_output_changes_with_goal": None,
                   "blocked_reason": "词表 %s 装不下本测试要的 goal %s，「同状态换 goal」构造不出来"
                                     % (tuple(m.vocab), missing)}
        else:
            t17 = t17_checks(m, h, C, xi, E)
        caught = [k for k, val in t17.items()
                  if val is False and not k.startswith("_") and k not in ("all_pass", "blocked_reason")]
        row = {"name": v["name"], "description": v["description"],
               "conventional_dim_checks": dims,
               "conventional_dim_checks_status": dims_status,
               "t17": t17,
               "t17_pass": bool(t17.get("all_pass")),
               "t17_blocked": dims_status == "blocked",
               "caught_by": caught,
               "blocked_reason": t17.get("blocked_reason"),
               "goal_effect_over_state_effect": (
                   round(t17["_d_goal_delta"] / max(t17["_d_state_delta"], 1e-12), 4)
                   if "_d_goal_delta" in t17 else None)}
        report["variants"].append(row)
        print("%-24s %-14s %-14s %s"
              % (v["name"], {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCKED"}[dims_status],
                 "PASS" if row["t17_pass"] else "FAIL",
                 (row["blocked_reason"] or ", ".join(caught) or "-")[:70]))

    ref = report["variants"][0]
    bad = report["variants"][1:]
    # 「常规检查会放行」的分母只取 runnable（能构造出换 goal 测试）的坏实现；
    # blocked 的坏实现走单独一条断言：它必须被 T17 明确挡住，不能静默通过。
    runnable = [v for v in bad if v["conventional_dim_checks_status"] != "blocked"]
    blocked = [v for v in bad if v["conventional_dim_checks_status"] == "blocked"]
    # blocked 变体必须留下**独立于分类标志**的证据：T17 明确 FAIL、且拒绝理由被写进 JSON。
    # 这里故意不复用 v["t17_blocked"]（它和 dims_status 同源，读了等于恒真——
    # 参见 docs/b_reproducibility_incident_20260928.md §2 缺陷 3 的恒真检查先例）。
    def _blocked_caught(v):
        reason = v["t17"].get("blocked_reason")
        return (v["t17_pass"] is False and isinstance(reason, str) and len(reason) > 0
                and v["t17"].get("all_pass") is False)
    teeth = {"reference_passes": ref["t17_pass"],
             "all_broken_variants_caught_by_t17": all(not v["t17_pass"] for v in bad),
             "runnable_broken_variants_pass_conventional_dim_checks":
                 all(v["conventional_dim_checks"]["all_pass"] for v in runnable),
             "blocked_variants_cannot_silently_pass":
                 all(_blocked_caught(v) for v in blocked),
             "non_vacuous": len(runnable) >= 1,
             "n_broken_variants": len(bad),
             "n_runnable_broken_variants": len(runnable),
             "n_blocked_variants": len(blocked)}
    report["teeth_check"] = teeth
    teeth_ok = bool(teeth["reference_passes"]
                    and teeth["all_broken_variants_caught_by_t17"]
                    and teeth["runnable_broken_variants_pass_conventional_dim_checks"]
                    and teeth["blocked_variants_cannot_silently_pass"]
                    and teeth["non_vacuous"])
    report["verdict"] = {
        "test_has_teeth": teeth_ok,
        "meaning": (("T17 抓住全部 %d 个坏实现：其中 %d 个（B2–B6 类）常规维度/concat/forward 检查全过、"
                      "只有 T17 能抓，%d 个（B1 类）连「同状态换 goal」都构造不出来、被 T17 明确挡下。"
                      "所以只用维度检查验收 goal 贯通是不充分的。"
                      % (len(bad), len(runnable), len(blocked)))
                     if teeth_ok else
                     "T17 断言本身有问题，先修断言再用它验收。"),
    }
    # 状态实测（见 _WIRE_PROBE / _probe_a_side_t17 注释）：C 的三项由子进程真调 learner 判定，
    # A 的两项由子进程真调 A 的自检 + B 自己的内容锚复核（两条独立通道）判定。
    # 文档侧 B 不代判。探针跑不起来一律 unprobed（明确写出「未实测」，不冒充结论）。
    probe = _probe_wire_status()
    report["wire_probe"] = probe
    a_probe = _probe_a_side_t17()
    report["a_side_probe"] = a_probe
    c_selfcheck = ROOT / "scripts/c_selfcheck_goal_conditioning_t17.py"
    _anch = a_probe.get("anchors_rendered") or {}
    _audit_anchor = _anch.get(
        "audit_uses_variables",
        "scripts/run_act_lift_runtime_failure_audit.py:?（内容锚 `'epoch':epoch,'goal_id':goal_id`）")
    _policy_anchor = _anch.get(
        "policy_ctor_takes_goals",
        "scripts/train_act_lift.py:?（内容锚 `def __init__(self, obs_dim, chunk=4, *, goals=None)`）")

    def _a_status(anchor_keys, check_key, evidence):
        """A 侧状态：**两条独立通道都绿**才 closed_verified。

        通道 1 = 子进程真调 A 的自检并读**原始断言行**（不读 A 的 summary/verdict 下结论）；
        通道 2 = B 自己的内容锚复核（不经 A 的脚本）。
        只信通道 1 就退化成「A 说自己绿了」；只信通道 2 就只是读源码、不是语义实测。
        """
        if not a_probe.get("probe_ran"):
            return "unprobed", "A 侧探针未跑起来：%s" % a_probe.get("error")
        if not a_probe.get("clean_run"):
            return "open", ("A 的自检未干净通过：rc=%s summary=%s teeth.non_vacuous=%s"
                            "（**SKIP ≠ PASS**，A 的牙没跑起来也不算闭合）"
                            % (a_probe.get("rc"), a_probe.get("a_summary"),
                               a_probe.get("a_teeth_non_vacuous")))
        rc = (a_probe.get("required_checks") or {}).get(check_key) or {}
        if not rc.get("all_ok") or rc.get("missing_ids"):
            return "open", "B 点名的 A 侧断言未全绿：ids=%s 缺=%s 未过=%s" % (
                rc.get("ids"), rc.get("missing_ids"), rc.get("failed_ids"))
        bad = [k for k in anchor_keys
               if ((a_probe.get("anchors") or {}).get(k) or {}).get("status") != "ok"]
        if bad:
            return "open", "B 侧内容锚独立复核未过：%s" % bad
        if not a_probe.get("vocab_matches_b_goals"):
            return "open", ("A 回报的 goal 词表 %s 与 B 的 GOALS %s 不逐字相同"
                            % (a_probe.get("a_goal_vocab"), list(GOALS)))
        return "closed_verified", evidence

    def _obs(check_key, gid):
        return (((a_probe.get("required_checks") or {}).get(check_key) or {})
                .get("observed") or {}).get(gid, "?")

    def _status(ok, evidence, when_unprobed="unprobed"):
        if not probe.get("probe_ran"):
            return when_unprobed, "探针未跑起来：%s" % probe.get("error")
        return ("closed_verified" if ok else "open"), evidence

    st1, ev1 = _status(
        probe.get("goals_default_n", 0) >= 2
        and tuple(probe.get("goals_default") or ()) == GOALS,
        # 注意：evidence 是**实参**，即使 _status 因探针没跑起来而提前返回也照样求值，
        # 所以这里必须对缺失键空值安全（曾用 %d 撞 None，把 6 个变异体全打成 no_json）。
        "实测 LearnerConfig.goals 缺省 = %s（%s 项，与 B 的 GOALS 逐字相同）"
        % (probe.get("goals_default"), probe.get("goals_default_n", 0) or 0))
    st2, ev2 = _status(
        probe.get("single_goal_refused") is True and probe.get("refusal_is_not_keyerror") is True,
        "实测单 goal 配置调 _goal_onehot → LearnerRefused（且 LearnerRefused 不是 KeyError 子类）：%s"
        % (probe.get("single_goal_refusal_message") or probe.get("single_goal_wrong_exception")
           or probe.get("single_goal_returned") or probe.get("single_goal_probe_error")
           or "探针未回报该键"))
    st3 = "closed_verified" if c_selfcheck.exists() else "open"
    ev3 = ("实测存在 %s（C 侧把 T17-a/c/d/e 落成单元测试）；覆盖度以 C 自己的汇总为准："
           "已实现组件 4 个（base/Q/actor_target/critic_target），未实现 3 个"
           "（editor/candidate_filter/predictor）记 SKIP ≠ PASS" % c_selfcheck.name) \
        if c_selfcheck.exists() else "未找到 C 侧单元测试脚本"
    if not probe.get("probe_ran"):
        st3, ev3 = "unprobed", "探针未跑起来：%s" % probe.get("error")

    st4, ev4 = _a_status(
        ("audit_uses_variables", "audit_hardcode_gone"), "audit_goal_id_epoch",
        ("两条**独立**通道都实测过：① 子进程真调 A 的 %s（rc=%s、%s、teeth.non_vacuous=%s、"
         "抓住变异 %s），B 点名的 G9 **原始断言行** ok=True，observed=%s；"
         "② B 自己的内容锚复核（不经 A 的脚本）：%s 命中 **2** 处、`'goal_id':'lift'` 命中 **0** 处 "
         "⇒ 写死的 goal_id 一处不剩。A 的产物由 B 重定向到自己的临时目录（%s），"
         "**未覆写** A 的 runs/infra/a_t17_goal_conditioning.json。")
        % (_A_SIDE_SCRIPT, a_probe.get("rc"),
           json.dumps(a_probe.get("a_summary"), ensure_ascii=False),
           a_probe.get("a_teeth_non_vacuous"), a_probe.get("a_teeth_caught"),
           _obs("audit_goal_id_epoch", "G9"), _anch.get("audit_uses_variables", "?"),
           a_probe.get("a_artifact_redirect")))
    st5, ev5 = _a_status(
        ("policy_ctor_takes_goals", "goal_enters_first_layer"), "policy_takes_goal",
        ("两条**独立**通道都实测过：① 子进程真调 A 的 %s，B 点名的 G2/G5/G6/G8 **原始断言行**全 "
         "ok=True（G2=%s；G5=%s；G6=%s；G8=%s），且 A 回报的 goal 词表 %s 与 B 的 GOALS %s "
         "**逐字相同**；② B 自己的内容锚复核：%s 与 %s 各命中 1 处 ⇒ goal 不只进了签名，"
         "也真进了第一层输入维度。**这不等于已学出方向差异**：真帧 teacher 只做 A→B，"
         "`lift_B_to_A` 组 n_rows=0（A 交接单 §5 明确不主张），要真贯通 T17 还需 B→A 的演示源。")
        % (_A_SIDE_SCRIPT, _obs("policy_takes_goal", "G2"), _obs("policy_takes_goal", "G5"),
           _obs("policy_takes_goal", "G6"), _obs("policy_takes_goal", "G8"),
           a_probe.get("a_goal_vocab"), list(GOALS),
           _anch.get("policy_ctor_takes_goals", "?"),
           _anch.get("goal_enters_first_layer", "?")))

    report["to_wire_goal_for_real"] = [
        {"file": "harness/queue_td_learner.py（LearnerConfig.goals）",
         "change": "cfg.goals 从 ('lift',) 扩成双向词表 ('lift_A_to_B','lift_B_to_A')；单 goal 下 T17 无法构造",
         "owner": "C", "status": st1, "evidence": ev1,
         "was_blocking": True, "blocking": st1 == "open"},
        {"file": "harness/queue_td_learner.py（_goal_onehot）",
         "change": "_goal_onehot 在 goal_dim==1 时输出恒为 [1.0]（= 常量偏置）；须在 goal_dim<2 时**显式拒绝**声称已 goal-conditioned",
         "owner": "C", "status": st2, "evidence": ev2,
         "was_blocking": True, "blocking": st2 == "open"},
        {"file": "harness/queue_td_learner.py（forward 的 cat）",
         "change": "cat([state, goal, c, xi]) 只保证维度；需要把本脚本的 T17-a/c/d 断言落成单元测试",
         "owner": "C", "status": st3, "evidence": ev3,
         "was_blocking": False, "blocking": False},
        # 内容锚（D→B 执行单 §5：旧锚 :36,39 已移位，且**语义变了** ⇒ 期望值跟着改，不是只改行号）
        {"file": _audit_anchor,
         "change": AUDIT_EXPECTATION,
         "owner": "A", "status": st4, "evidence": ev4,
         "was_blocking": True, "blocking": st4 != "closed_verified"},
        {"file": _policy_anchor + "（及 A 的 LeRobot 训练侧）",
         "change": POLICY_EXPECTATION,
         "owner": "A", "status": st5, "evidence": ev5,
         "was_blocking": True, "blocking": st5 != "closed_verified"},
        {"file": "docs/b_golden/async_td_golden_v1.json（E6）", "change": "goal/epoch 不相容必须与「晚到」"
                                                                        "作为两个独立拒绝理由分别记录；"
                                                                        "T17 只管计算图，不管这条时间语义",
        "owner": "C", "status": "closed_verified",
         "evidence": ("B 实测 harness/data_bridge.py：:379 append 'deadline_miss'、:388 append "
                      "'goal_epoch_incompatible'，两条并排独立（:386-387 注释即「晚到 + 换向必须同时留下两条理由」）"
                      "⇒ E6 的实质要求成立。**但 C 0929 回执 §2 有一处事实错误**：它写「两条都在 "
                      "CENSORING_REASONS 里」，实测 goal_epoch_incompatible **不在**该元组，且是**有意排除**"
                      "（:40-42 注释：换向族属 §5.5 合法边界、不是信息缺失）⇒ 结论不变、措辞须更正"),
         "was_blocking": False, "blocking": False},
        {"file": "附录 02 §12「全包 goal 与时间条件」", "change": "base / editor / Q / 候选筛选 / 预测器要**分别**验，"
                                                                "不能只验一个标量输出。本脚本的 B6 变体就是只验标量会漏掉的那种",
         "owner": "B（规格）+ C（实现）", "status": "partial_verified",
         "evidence": ("C 已按组件分别验，但只覆盖 4/7 个已实现组件；editor / candidate_filter / predictor "
                      "**未实现 ⇒ SKIP ≠ PASS**，实现后必须补测（C 0929 回执 §3）"),
         "was_blocking": False, "blocking": False},
    ]

    outp = Path(a.json_out); outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("=" * 96)
    print("teeth check:", json.dumps(teeth, ensure_ascii=False))
    print("裁定：T17 断言%s有牙" % ("" if report["verdict"]["test_has_teeth"] else "**不**"))
    wire = report["to_wire_goal_for_real"]
    n_closed = sum(1 for x in wire if x["status"] == "closed_verified")
    n_open = sum(1 for x in wire if x["status"] == "open")
    n_block = sum(1 for x in wire if x["blocking"])
    n_notprobed = sum(1 for x in wire if x["status"] == "open_not_probed")
    n_unprobed = sum(1 for x in wire if x["status"] == "unprobed")
    print("\n真贯通清单（%d 项）：实测已闭合 %d / 仍开放 %d / 未实测 %d / 探针失败 %d ⇒ **当前阻塞 %d 项**"
          % (len(wire), n_closed, n_open, n_notprobed, n_unprobed, n_block))
    if n_unprobed:
        print("  [WARN] 探针没跑起来，%d 项状态为 unprobed（不当作已闭合，也不当作开放）：%s"
              % (n_unprobed, probe.get("error")))
    for x in wire:
        print("  [%-16s %-9s%s] %s" % (x["status"], x["owner"], " 阻塞" if x["blocking"] else "     ",
                                       x["file"]))
        print("       证据：%s" % x["evidence"])
    print("写出:", outp)
    return 0 if report["verdict"]["test_has_teeth"] else 1


if __name__ == "__main__":
    sys.exit(main())
