#!/usr/bin/env python3
"""A 线自检：T17「同状态换 goal」落到 **A 的真帧训练/审计侧**（B 交接单 §8 的 2 项 A 侧待办）。

分工（不要重复别人的活）
----------------------
- B 的 `scripts/b_selfcheck_goal_conditioning_t17.py`：证明 T17 断言本身**有牙**（6 个变异体全被抓）。
- C 的 `scripts/c_selfcheck_goal_conditioning_t17.py`：把断言落到 C 的参考 learner
  （`harness/queue_td_learner.py`，base/Q/两个 target）。
- **本脚本**：把断言落到 A 侧那两处 B 标 `open_not_probed` 的地方 ——
  ① `scripts/train_act_lift.py`（policy 接收 goal + BC 采集按 goal 分组）；
  ② `scripts/run_act_lift_runtime_failure_audit.py`（`goal_id` 不再写死 `'lift'`，换向与 epoch 一起进账本）。
  B 不代判 A 的文件，所以这两项的状态**只能由 A 自己出证据**，再由 D 核。

向后兼容是硬要求，不是风格偏好
----------------------------
`ChunkPolicy(obs_dim, chunk)` 这两个位置参数被 7 个 B 线脚本与 A 自己的 4 个脚本原样调用，
既有 ckpt（`runs/infra/act_lift_k4_state_seed0/model_final.pt`，0924）的 `net.0.weight` 是
`(256, 60)`。所以 G5/G6 不是「我觉得没破坏」，而是**把 git HEAD（改动前）的实现动态载入做对照**：
键集、形状、同一 seed 下的 forward 输出必须逐项相同，且既有 ckpt 仍能 `strict=True` 加载。
HEAD 取不到 ⇒ 记 **SKIP（≠ PASS）**，不静默降级成绿。

只依赖 torch + numpy（**不起任何 env、不用 GPU**）：T17 验的是计算图与账本口径，不是真机能力。
`import scripts.train_act_lift` 会连带 import robosuite（模块级），但只 import、不 make env。

用法（必须用带 torch+robosuite 的解释器；不要用系统 python3）：
    /root/venvs/lerobot_eval/bin/python scripts/a_selfcheck_goal_conditioning_t17.py
    /root/venvs/lerobot_eval/bin/python scripts/a_selfcheck_goal_conditioning_t17.py --no-teeth

产物：`runs/infra/a_t17_goal_conditioning.json`（**只写 A 自己的目录**，不碰 harness/ configs/ 与他人产物）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.queue_td_learner import LearnerConfig, LearnerRefused  # noqa: E402
import scripts.train_act_lift as TAL  # noqa: E402
import scripts.run_act_lift_runtime_failure_audit as AUD  # noqa: E402

CKPT = ROOT / "runs/infra/act_lift_k4_state_seed0/model_final.pt"
OBS_DIM, CHUNK = 60, 4
# B/C 用的同一条判据：goal 方向的灵敏度必须与 state 方向同量级。
# 只验「换 goal 输出变了」不够 —— 变了 1e-9 也算变，那就是常量偏置的近似形态。
DGOAL_OVER_DSTATE_MIN = 0.05


class Checker:
    def __init__(self):
        self.rows = []

    def add(self, cid, name, ok, observed="", required="", note=""):
        self.rows.append({"id": cid, "name": name,
                          "ok": None if ok is None else bool(ok),
                          "observed": observed, "required": required, "note": note})
        tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        print("[%s] %-5s %s" % (tag, cid, name))
        if ok is not True and note:
            print("           note     = %s" % note)
        if ok is False:
            print("           observed = %s" % (observed,))
            print("           required = %s" % (required,))

    @property
    def n_pass(self):
        return sum(1 for r in self.rows if r["ok"] is True)

    @property
    def n_fail(self):
        return sum(1 for r in self.rows if r["ok"] is False)

    @property
    def n_skip(self):
        return sum(1 for r in self.rows if r["ok"] is None)


def load_head_version():
    """把 git HEAD（= T17 改动前）的 `train_act_lift.py` 动态载入，作为兼容性对照的事实源。

    为什么不抄一份「旧实现」进本脚本：抄的那份会与真旧实现各自漂移，
    最后测的是「我抄对了我自己」——那正是恒真断言的形态。
    """
    try:
        src = subprocess.run(["git", "show", "HEAD:scripts/train_act_lift.py"],
                             cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return None, "git show 失败：%r" % (exc,)
    if src.returncode != 0 or "class ChunkPolicy" not in src.stdout:
        return None, "git show HEAD:scripts/train_act_lift.py 不可用（rc=%s）" % src.returncode
    if "goals=None" in src.stdout:
        return None, "HEAD 已含 goal 改动 ⇒ 对照系不再是「改动前」，请改用 T17 之前的 commit"
    tmp = Path(tempfile.mkdtemp(prefix="a_t17_head_", dir=str(ROOT / "tmp")))
    f = tmp / "train_act_lift_head.py"
    f.write_text(src.stdout)
    spec = importlib.util.spec_from_file_location("train_act_lift_head", str(f))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        return None, "HEAD 版本 import 失败：%r" % (exc,)
    return mod, "git HEAD:scripts/train_act_lift.py（%d 行，%s）" % (len(src.stdout.splitlines()), f.name)


def rel_grad_sensitivity(policy, obs_dim, seed=4242):
    """d_goal/d_state：goal 列与 state 列对输出的**逐坐标**灵敏度之比（Jacobian 的 Frobenius 范数）。

    为什么不用「扰动全部 state 维」的有限差分：那样 state 侧一次动 60 个坐标、goal 侧只动 2 个，
    比值被坐标数主导，量不到「goal 这一列到底进没进计算图」。
    为什么绕开 `forward` 直接走 `.net`：`forward` 收的是 goal **id**，one-hot 不可导；
    把 goal 当连续输入向量才求得了导。goal 列若只是常量偏置（B 的 B2–B6 那类），比值恒为 0。
    """
    torch.manual_seed(seed)
    x = torch.randn(1, obs_dim, requires_grad=True)   # 全零点会让 ReLU 停在边界上，梯度可能整片为 0
    # g 必须带 batch 维（与 x 同形状族），否则 torch.cat 会报 "same number of dimensions"
    g = torch.zeros(1, policy.goal_dim, requires_grad=True)
    out = policy.net(torch.cat([x, g], dim=-1))
    out.backward(torch.ones_like(out))                # 一次反传同时拿两组梯度（不累加、不重复建图）
    d_state = float(x.grad.norm())
    d_goal = float(g.grad.norm())
    return d_goal, d_state, (d_goal / d_state if d_state > 0 else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default="runs/infra/a_t17_goal_conditioning.json")
    ap.add_argument("--no-teeth", action="store_true", help="跳过变异自检（只在赶时间时用；跳过后 teeth 记 SKIP）")
    a = ap.parse_args()

    t0 = time.time()
    ck = Checker()
    vocab_default = tuple(LearnerConfig.__dataclass_fields__["goals"].default)

    # ---- G1：词表单一事实源 = learner 的缺省（A 只读不抄）---------------------------------
    resolved = TAL._resolve_goal_vocab("default")
    ck.add("G1", "A 的 goal 词表读的是 LearnerConfig.goals 缺省（不抄字面量）",
           resolved == vocab_default and len(resolved) >= 2,
           "A 解析出 %r（%d 项）" % (resolved, len(resolved)),
           "== LearnerConfig.goals 缺省 %r 且 >= 2 项" % (vocab_default,),
           "抄一份字面量就会在缺省变更时对着一个不存在的词表绿着（ADR-C-005 同一条纪律）。")

    # ---- G2：同状态换 goal 必须改变输出，且灵敏度与 state 同量级 ---------------------------
    torch.manual_seed(0)
    pol = TAL.ChunkPolicy(OBS_DIM, CHUNK, goals="default")
    st = torch.randn(1, OBS_DIM)
    g0, g1 = vocab_default[0], vocab_default[1]
    with torch.no_grad():
        o0 = pol(st, goal=g0)
        o1 = pol(st, goal=g1)
    delta = float((o0 - o1).abs().max())
    d_goal, d_state, ratio = rel_grad_sensitivity(pol, OBS_DIM)
    ck.add("G2", "同一 state 换 goal 改变输出，且 d_goal/d_state > %.2f（不是常量偏置）" % DGOAL_OVER_DSTATE_MIN,
           delta > 0 and ratio > DGOAL_OVER_DSTATE_MIN,
           "max|Δoutput|=%.6g，d_goal=%.6g / d_state=%.6g ⇒ 比值 %.4g" % (delta, d_goal, d_state, ratio),
           "max|Δoutput| > 0 且比值 > %.2f" % DGOAL_OVER_DSTATE_MIN,
           "只验「变了」不够：变 1e-9 也算变。比值才区分「goal 进了计算图」与「goal 是常量偏置」。")

    # ---- G3：词表外 goal 拒绝，且拒绝类型跨线一致（不是 KeyError）--------------------------
    try:
        pol.goal_onehot("lift")          # 旧脚本写死的那个值：现在必须被拒绝
        refused, msg, is_key = False, "未拒绝（返回了值）", None
    except LearnerRefused as exc:
        refused, msg, is_key = True, str(exc), issubclass(LearnerRefused, KeyError)
    except Exception as exc:  # noqa: BLE001
        refused, msg, is_key = False, "抛了别的异常 %r" % (exc,), None
    ck.add("G3", "词表外 goal_id（含旧写死的 'lift'）被 LearnerRefused 拒绝，且不静默映射",
           refused and is_key is False,
           "refused=%s，LearnerRefused 是 KeyError 子类=%s，msg=%s" % (refused, is_key, msg[:150]),
           "refused=True 且 LearnerRefused 不是 KeyError 子类",
           "C 抛的是 LearnerRefused(RuntimeError)。B 参考实现里 `except KeyError` 的写法照抄过来会假失败。")

    # ---- G4：单 goal 词表显式拒绝（否则 T17 连测试都构造不出来）---------------------------
    try:
        TAL.ChunkPolicy(OBS_DIM, CHUNK, goals=("lift_A_to_B",))
        single_refused, single_msg = False, "未拒绝"
    except LearnerRefused as exc:
        single_refused, single_msg = True, str(exc)
    except Exception as exc:  # noqa: BLE001
        single_refused, single_msg = False, "抛了别的异常 %r" % (exc,)
    ck.add("G4", "单 goal 词表被显式拒绝（one-hot 退化成常量 [1.0] 时不得声称已 goal 条件化）",
           single_refused, "refused=%s，msg=%s" % (single_refused, single_msg[:150]),
           "refused=True（LearnerRefused）", "对齐 C 的 `goal_dim < 2` 那一条。")

    # ---- G5：缺省路径与 git HEAD（改动前）逐项相同 ----------------------------------------
    head, head_src = load_head_version()
    if head is None:
        ck.add("G5", "缺省路径 state_dict 键集/形状与改动前相同", None,
               "对照系不可用：%s" % head_src, "git HEAD 版本可载入",
               "**SKIP ≠ PASS**：这条没被验证，不得读成兼容。")
        ck.add("G6", "既有 0924 ckpt 仍 strict=True 加载且输出与改动前逐元素相同", None,
               "对照系不可用：%s" % head_src, "git HEAD 版本可载入", "**SKIP ≠ PASS**")
    else:
        torch.manual_seed(1234)
        new_p = TAL.ChunkPolicy(OBS_DIM, CHUNK)
        torch.manual_seed(1234)
        old_p = head.ChunkPolicy(OBS_DIM, CHUNK)
        new_sd, old_sd = new_p.state_dict(), old_p.state_dict()
        same_keys = list(new_sd.keys()) == list(old_sd.keys())
        same_shapes = same_keys and all(new_sd[k].shape == old_sd[k].shape for k in old_sd)
        same_vals = same_keys and all(bool(torch.equal(new_sd[k], old_sd[k])) for k in old_sd)
        with torch.no_grad():
            xo = torch.randn(3, OBS_DIM)
            same_out = bool(torch.equal(new_p(xo), old_p(xo)))
        ck.add("G5", "缺省路径（不传 goals）state_dict 键序/形状/权重与 git HEAD 逐项相同，forward 输出相同",
               same_keys and same_shapes and same_vals and same_out,
               "键序相同=%s 形状相同=%s 同 seed 权重逐元素相同=%s forward 相同=%s；键=%s"
               % (same_keys, same_shapes, same_vals, same_out, list(new_sd.keys())),
               "四项全 True；net.0.weight 形状 == (256, %d)" % OBS_DIM,
               "对照系 = %s" % head_src)

        # ---- G6：既有 ckpt 仍能被新代码 strict=True 加载，且预测不变 -----------------------
        if not CKPT.exists():
            ck.add("G6", "既有 0924 ckpt 仍 strict=True 加载且输出与改动前逐元素相同", None,
                   "找不到 %s" % CKPT, "ckpt 在位", "**SKIP ≠ PASS**")
        else:
            try:
                ckpt = torch.load(str(CKPT), map_location="cpu")
                m_new = TAL.policy_from_checkpoint(ckpt, CHUNK)
                m_new.load_state_dict(ckpt["model"])          # strict=True（默认）
                m_old = head.ChunkPolicy(int(ckpt["obs_dim"]), CHUNK)
                m_old.load_state_dict(ckpt["model"])
                m_new.eval(); m_old.eval()
                mean = np.asarray(ckpt["obs_mean"], np.float32)
                std = np.asarray(ckpt["obs_std"], np.float32)
                xck = torch.tensor(((np.random.RandomState(0).randn(2, OBS_DIM).astype(np.float32) - mean) / std))
                with torch.no_grad():
                    same_pred = bool(torch.equal(m_new(xck), m_old(xck)))
                w0 = tuple(ckpt["model"]["net.0.weight"].shape)
                ck.add("G6", "既有 0924 ckpt 仍 strict=True 加载，且预测与改动前逐元素相同",
                       same_pred and w0 == (256, OBS_DIM) and not ckpt.get("goal_vocab"),
                       "net.0.weight=%s，预测相同=%s，ckpt 带 goal_vocab=%s（应无：缺省路径不写这两个键）"
                       % (w0, same_pred, bool(ckpt.get("goal_vocab"))),
                       "net.0.weight == (256, %d)；预测逐元素相同；ckpt 无 goal_vocab 键" % OBS_DIM,
                       "torch.load 走的是与 audit 脚本同一条代码路径（torch %s）" % torch.__version__)
            except Exception as exc:  # noqa: BLE001
                ck.add("G6", "既有 0924 ckpt 仍 strict=True 加载，且预测与改动前逐元素相同",
                       False, "加载/比对抛异常 %r" % (exc,), "strict=True 加载成功且预测相同",
                       "torch 2.6 起 torch.load 默认 weights_only=True：若因它失败，是**环境重建带来的真差异**，必须报 D")

    # ---- G7：逐样本 goal 长度不齐必须拒绝（不得广播成单 goal）-----------------------------
    try:
        pol(torch.randn(4, OBS_DIM), goal=[g0, g1])
        len_refused, len_msg = False, "未拒绝"
    except LearnerRefused as exc:
        len_refused, len_msg = True, str(exc)
    except Exception as exc:  # noqa: BLE001
        len_refused, len_msg = False, "抛了别的异常 %r" % (exc,)
    with torch.no_grad():
        ok_pair = pol(torch.randn(2, OBS_DIM), goal=[g0, g1]).shape == (2, CHUNK, 7)
    ck.add("G7", "逐样本 goal 长度与 batch 不齐时拒绝；齐时输出形状 (B, chunk, 7)",
           len_refused and ok_pair, "不齐 refused=%s（%s）；齐时形状正确=%s" % (len_refused, len_msg[:110], ok_pair),
           "不齐 refused=True；齐时 shape == (2, %d, 7)" % CHUNK,
           "不齐还广播 = 把「按 goal 分组」静默退回单 goal。")

    # ---- G8：BC 采集按 goal 分组；无 teacher 的方向如实记 0 行 ----------------------------
    # 用 stub 替掉 collect（不碰 robosuite）：这里验的是**分组与如实计数**的逻辑，不是采集本身。
    fake_calls = []
    real_collect = TAL.collect

    def fake_collect(env, seeds, horizon, chunk, history=1):
        fake_calls.append(tuple(seeds))
        return [(np.zeros(OBS_DIM, np.float32), np.zeros((chunk, 7), np.float32)) for _ in seeds]

    TAL.collect = fake_collect
    try:
        groups = TAL.collect_by_goal(None, vocab_default, [1, 2, 3], 10, CHUNK)
        honest_zero = (groups[g0]["n_rows"] == 3 and groups[g0]["teacher_available"] is True
                       and groups[g1]["n_rows"] == 0 and groups[g1]["teacher_available"] is False
                       and groups[g1]["rows"] == [])
        only_teacher_collected = fake_calls == [(1, 2, 3)]   # list of calls；只对 teacher 方向调过一次
        try:
            TAL.collect_by_goal(None, ("some_other_goal", "yet_another"), [1], 10, CHUNK)
            vocab_refused, vocab_msg = False, "未拒绝"
        except LearnerRefused as exc:
            vocab_refused, vocab_msg = True, str(exc)
    finally:
        TAL.collect = real_collect
    ck.add("G8", "BC 按 goal 分组：teacher 方向有行、无 teacher 的方向如实记 n_rows=0（不伪造 0/0、不拿 A→B 冒充）",
           honest_zero and only_teacher_collected and vocab_refused,
           "分组=%s；只对 teacher 方向调了一次 collect=%s（实调 %d 次）；teacher 不在词表时 refused=%s（%s）"
           % ({g: groups[g]["n_rows"] for g in vocab_default}, only_teacher_collected,
              len(fake_calls), vocab_refused, vocab_msg[:90]),
           "%s 有 3 行 / %s 记 0 行且 teacher_available=False；teacher 不在词表 ⇒ 拒绝" % (g0, g1),
           "「计算图已 goal 条件化」≠「真帧能学出方向差异」：main() 会把这条区别写进 config.json 的 goal_conditioning_status。")

    # ---- G9：audit 侧 goal_id/epoch 由 resolver 统一给出，随 A↔B 换向一起进账本 -----------
    res_alt, plan_alt, src_alt = AUD.make_goal_resolver(vocab_default, "auto", 4, "lift")
    seq = [res_alt(ci) for ci in range(10)]
    alternates = [g for g, _ in seq[:8]] == [vocab_default[0]] * 4 + [vocab_default[1]] * 4
    epoch_moves = [e for _, e in seq[:8]] == [1, 1, 1, 1, 2, 2, 2, 2]
    res_fix, plan_fix, src_fix = AUD.make_goal_resolver((), "auto", 4, "lift")
    legacy = [res_fix(ci) for ci in range(3)]
    legacy_ok = legacy == [("lift", 1)] * 3 and plan_fix == "fixed" and "非 goal 条件" in src_fix
    try:
        AUD.make_goal_resolver((), "alternate", 4, "lift")
        blind_refused, blind_msg = False, "未拒绝"
    except LearnerRefused as exc:
        blind_refused, blind_msg = True, str(exc)
    try:
        AUD.make_goal_resolver(vocab_default, "alternate", 0, "lift")
        zero_refused = False
    except LearnerRefused:
        zero_refused = True
    hardcoded_left = "'goal_id':'lift'" in (ROOT / "scripts/run_act_lift_runtime_failure_audit.py").read_text()
    ck.add("G9", "audit 侧：goal_id 随 A↔B 换向且 epoch 同步 +1；goal-blind ckpt 不得记方向性 goal（拒绝）；源码里不再有写死的 goal_id",
           alternates and epoch_moves and legacy_ok and blind_refused and zero_refused and not hardcoded_left,
           "换向序列=%s；epoch 序列=%s；legacy 退回=%s(plan=%s, source=%s)；"
           "goal-blind + --goal-plan=alternate refused=%s（%s）；switch_every=0 refused=%s；源码残留写死 goal_id=%s"
           % ([g for g, _ in seq[:8]], [e for _, e in seq[:8]], legacy[:1], plan_fix, src_fix,
              blind_refused, blind_msg[:80], zero_refused, hardcoded_left),
           "词表内轮换 + epoch 同步 +1；legacy 记 ('lift',1) 且 goal_source 明说非 goal 条件；"
           "goal-blind 要求换向 ⇒ 拒绝；源码无 'goal_id':'lift'",
           "E6 要的是 goal/epoch 不相容与「晚到」作为**两个独立**拒绝理由（data_bridge.py:379/:388）。")

    # ---- 变异自检：证明上面这些断言不是恒真 ----------------------------------------------
    teeth = {"ran": False}
    if not a.no_teeth:
        bad = []

        # M1：forward 收到 goal 但**丢掉不用**（B 的 B2 类）——G2 的 Δoutput 必须为 0 ⇒ 被抓。
        # 注意它的 `.net` 里 goal 列权重是**真的**，所以梯度比值仍 > 阈值：
        # 这正是 G2 必须同时判「Δoutput > 0」与「比值 > 阈值」两条的原因，少一条就漏这个变异体。
        class MIgnoreGoal(TAL.ChunkPolicy):
            def forward(self, x, goal=None):
                z = torch.zeros(x.shape[0], self.goal_dim, dtype=x.dtype, device=x.device)
                return self.net(torch.cat([x, z], dim=-1)).view(-1, self.chunk, 7)

        torch.manual_seed(0)
        m1 = MIgnoreGoal(OBS_DIM, CHUNK, goals="default")
        with torch.no_grad():
            xs1 = torch.randn(1, OBS_DIM)
            d1 = float((m1(xs1, goal=g0) - m1(xs1, goal=g1)).abs().max())
        _, _, r1 = rel_grad_sensitivity(m1, OBS_DIM)
        bad.append({"mutant": "M1 forward 丢掉 goal（Δoutput 恒 0，但 net 里 goal 权重是真的）",
                    "caught_by": "G2", "caught": d1 == 0.0 or r1 <= DGOAL_OVER_DSTATE_MIN,
                    "delta_out": d1, "ratio": r1})

        # M2：goal 列全零接线（维度对、concat 对、forward 不报错）——G2 必须红
        class MZero(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.goal_dim = len(vocab_default)
                self.chunk = CHUNK
                torch.manual_seed(0)
                inner = TAL.ChunkPolicy(OBS_DIM, CHUNK, goals="default")
                self.net = inner.net
                with torch.no_grad():     # 把 goal 那两列权重清零 ⇒ 输出对 goal 完全不敏感
                    self.net[0].weight[:, OBS_DIM:] = 0.0

            def forward(self, x, goal=None):
                g = torch.zeros(x.shape[0], self.goal_dim)
                return self.net(torch.cat([x, g], -1)).view(-1, self.chunk, 7)

        m2 = MZero()
        with torch.no_grad():
            xs2 = torch.randn(1, OBS_DIM)
            d2 = float((m2(xs2, goal=g0) - m2(xs2, goal=g1)).abs().max())
        _, _, r2 = rel_grad_sensitivity(m2, OBS_DIM)
        bad.append({"mutant": "M2 goal 列权重清零（维度/concat/forward 全对）", "caught_by": "G2",
                    "caught": d2 == 0.0 or r2 <= DGOAL_OVER_DSTATE_MIN,
                    "delta_out": d2, "ratio": r2})

        # M3：词表外 goal 静默映射到第 0 项——G3 必须红
        class MSilent(TAL.ChunkPolicy):
            def goal_onehot(self, goal_id):
                vec = np.zeros(self.goal_dim, dtype=np.float32)
                vec[self.goals.index(goal_id) if goal_id in self.goals else 0] = 1.0
                return torch.from_numpy(vec)

        torch.manual_seed(0)
        m3 = MSilent(OBS_DIM, CHUNK, goals="default")
        try:
            m3.goal_onehot("lift")
            m3_refused = False          # 静默给了个值 ⇒ G3 的「必须拒绝」判红 ⇒ 变异体被抓
        except LearnerRefused:
            m3_refused = True           # 竟然还拒绝 ⇒ 这个变异体没改变行为，抓不到东西（= 变异体写废了）
        bad.append({"mutant": "M3 词表外 goal 静默映射到 vocab[0]", "caught_by": "G3",
                    "caught": not m3_refused, "mutant_still_refused": m3_refused})

        # M4：resolver 把 goal_id 写死、epoch 恒 1（= 改动前的形态）——G9 必须红
        def resolver_hardcoded(vocab, plan, switch_every, task):
            return (lambda ci: ("lift", 1)), "fixed", "hardcoded"

        real_resolver = AUD.make_goal_resolver
        AUD.make_goal_resolver = resolver_hardcoded
        try:
            r_alt, _, _ = AUD.make_goal_resolver(vocab_default, "auto", 4, "lift")
            s = [r_alt(ci) for ci in range(8)]
            c4 = not ([g for g, _ in s] == [vocab_default[0]] * 4 + [vocab_default[1]] * 4
                      and [e for _, e in s] == [1] * 4 + [2] * 4)
        finally:
            AUD.make_goal_resolver = real_resolver
        bad.append({"mutant": "M4 resolver 写死 ('lift',1)（改动前形态）", "caught_by": "G9", "caught": c4})

        # M5：无 teacher 的方向拿 A→B 的行冒充（伪造 0/0 的反面）——G8 必须红
        def fake_collect_lies(env, seeds, horizon, chunk, history=1):
            return [(np.zeros(OBS_DIM, np.float32), np.zeros((chunk, 7), np.float32)) for _ in seeds]

        real_cbg = TAL.collect_by_goal

        def lying_collect_by_goal(env, vocab, seeds, horizon, chunk, history=1):
            rows = fake_collect_lies(env, seeds, horizon, chunk, history)
            return {g: {"rows": rows, "n_rows": len(rows), "teacher_available": True,
                        "seeds": list(seeds), "note": "lie"} for g in vocab}

        TAL.collect_by_goal = lying_collect_by_goal
        try:
            lg = TAL.collect_by_goal(None, vocab_default, [1, 2, 3], 10, CHUNK)
            c5 = not (lg[vocab_default[1]]["n_rows"] == 0 and lg[vocab_default[1]]["teacher_available"] is False)
        finally:
            TAL.collect_by_goal = real_cbg
        bad.append({"mutant": "M5 无 teacher 的方向拿 A→B 的行冒充", "caught_by": "G8", "caught": c5})

        caught = sum(1 for b in bad if b["caught"])
        teeth = {"ran": True, "n_mutants": len(bad), "n_caught": caught,
                 "non_vacuous": caught == len(bad), "mutants": bad,
                 "meaning": ("G2/G3/G8/G9 抓住全部 %d 个变异体 ⇒ 这些断言不是恒真判据。" % len(bad))
                            if caught == len(bad) else
                            ("**有 %d 个变异体没被抓** ⇒ 对应断言是恒真的，先修断言再用它验收。"
                             % (len(bad) - caught))}
        print("\nteeth check:", json.dumps({k: v for k, v in teeth.items() if k != "mutants"}, ensure_ascii=False))
        for b in bad:
            print("  [%s] %s（由 %s 抓）" % ("caught " if b["caught"] else "MISSED", b["mutant"], b["caught_by"]))
    else:
        teeth = {"ran": False, "non_vacuous": None,
                 "meaning": "--no-teeth：变异自检未跑，**不得**据此声称断言有牙"}

    report = {
        "who": "A（官方 LeRobot ACT 训练与真值评测线）",
        "what": "T17 真贯通的 A 侧 2 项（B 交接单 §8 / D 执行单 §7.4）",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 2),
        "interpreter": sys.executable,
        "torch": torch.__version__,
        "numpy": np.__version__,
        "goal_vocab_source": "harness/queue_td_learner.py::LearnerConfig.goals（A 只读不抄）",
        "goal_vocab": list(vocab_default),
        "checks": ck.rows,
        "teeth": teeth,
        "coverage_note": ("本脚本验**计算图与账本口径**，不验学习成效：真帧 teacher 只做 A→B，"
                          "B→A 无演示 ⇒ 即便 G1–G9 全绿，也只能声称「goal 已接进 policy 输入与账本」，"
                          "**不得**声称「已学出方向差异」。后者需要 B→A 的演示源。"),
        "not_a_claim": ["不是训练/评测复现主张（就绪闸 E6 未解封）", "不覆盖 C 的 learner 与 B 的参考实现"],
        "summary": {"pass": ck.n_pass, "fail": ck.n_fail, "skip": ck.n_skip, "total": len(ck.rows)},
        "verdict": {
            "a_side_t17_wired": ck.n_fail == 0 and ck.n_skip == 0,
            "assertions_have_teeth": teeth.get("non_vacuous") is True,
            "skip_is_not_pass": ck.n_skip > 0,
        },
    }
    outp = ROOT / a.json_out
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")

    print("\n" + "=" * 96)
    print("A 侧 T17：%d PASS / %d FAIL / %d SKIP（共 %d）" % (ck.n_pass, ck.n_fail, ck.n_skip, len(ck.rows)))
    print("裁定：A 侧 goal 贯通%s；断言%s有牙"
          % ("成立" if report["verdict"]["a_side_t17_wired"] else "**不成立**",
             "" if report["verdict"]["assertions_have_teeth"] else "**不**"))
    if ck.n_skip:
        print("  [WARN] %d 项 SKIP —— **SKIP ≠ PASS**，这几条本轮未被验证。" % ck.n_skip)
    print("产物：%s" % outp)
    return 0 if (ck.n_fail == 0 and report["verdict"]["assertions_have_teeth"]) else 1


if __name__ == "__main__":
    sys.exit(main())
