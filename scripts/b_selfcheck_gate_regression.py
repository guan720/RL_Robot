#!/usr/bin/env python3
"""B 线：《受控成功判据》规格 §7「反例自检」表的可执行版本。

为什么需要这个脚本：规格 §7 那张表原本是**人肉重跑**的 —— 每次改判据都要求
「逐条重跑并核对期望值」。实测后果已经出现过一次：门禁从 v1.1 升到 v1.2
（拆出 `insufficient_lift`）之后，留档产物 `runs/infra/b_normclip2/gate_all.json`
仍是旧构建 `22a7d92bec0a` 判的，而三份文档里引用的构建指纹又各不相同
（`800e1d08a174` / `28290b9c1b25` / 无指纹），没人能一眼看出哪份裁定还算数。

本脚本把 §7 的五条已知答案变成断言，并强制三件事：
  1. 夹具缺失 = **FAIL**，不是 skip（吸取 L0-c 恒真断言的教训：
     永远绿的检查等于没有检查，见 docs/b_reproducibility_incident_20260928.md）；
  2. 输出里带上当轮 `gate_build` / `gate_spec_sha256`，使「这份回归记录是哪一版门禁跑的」可回答；
  3. 断言值与规格 §7 表格一一对应，改判据时必须**同时**改规格与这里，
     否则本脚本会红 —— 这正是想要的耦合。

只读：不修改任何评测器、checkpoint 或 A/C 的实现文件。

用法：
    python3 scripts/b_selfcheck_gate_regression.py
    python3 scripts/b_selfcheck_gate_regression.py --json-out runs/infra/b_gate_regression/selfcheck.json
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "b_gate_controlled_success.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("b_gate", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Args:
    """judge_file 只读这三个属性（与 b_gate_threshold_sensitivity.py 同一约定）。"""
    def __init__(self, rise_cap, final_rise, assist_off=False):
        self.rise_cap = rise_cap
        self.final_rise = final_rise
        self.assist_off = assist_off


def acct(row, key):
    """三套账里 policy_independent 的某个计数。"""
    return (row.get("accounts") or {}).get("policy_independent", {}).get(key)


# ---- 规格 §7 的五条回归（编号与表格一一对应）----
# 每条 = 夹具路径 + 一组 (取值函数, 期望值, 说明)。取值函数只吃 judge_file 的返回行。
FIXDIR = ROOT / "runs" / "infra" / "b_gate_regression" / "fixtures"


def _row(seed, **kw):
    base = {"seed": seed, "success_raw": True, "grasp_verified": True, "max_rise": 0.06,
            "final_rise": 0.055, "held_at_end": True, "phase_at_end": "hold",
            "phase_trace": ["approach", "descend", "grasp", "hold"],
            "terminal_kind": "terminated_success", "steps": 180,
            "guard_interventions": 0, "recovery_events": 0}
    base.update(kw)
    return base


def _doc(rows, **top):
    d = {"controller": "synthetic_fixture", "task": "lift", "horizon": 300, "seed0": 5000,
         "episodes": len(rows), "rows": rows,
         "fixture_note": "由 scripts/b_selfcheck_gate_regression.py::make_fixtures 确定性生成，勿手改"}
    d.update(top)
    return d


def make_fixtures(gate):
    """生成 v1.3 三类裁定的合成夹具，返回 {name: 仓库相对路径}。

    为什么必须用合成夹具：裁定 2 的 not_applicable 声明路径、裁定 3 的带外拒绝、
    以及「新产物缺 blown 指纹」这三种判定，在仓里**还没有真实样例**（它们正是 v1.3
    新引入的）。没有夹具 = 这三条裁定永远不会被回归覆盖 = 下次重构可以静默改掉它们。
    内容是确定性的，重复生成字节一致，因此可以放心放在不纳版控的 runs/ 下。
    """
    FIXDIR.mkdir(parents=True, exist_ok=True)
    impl = gate.KNOWN_BLOWN_IMPLS[0]
    out = {}

    def w(name, d):
        p = FIXDIR / name
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")
        out[name] = str(p.relative_to(ROOT))

    ic_ok = {"blown_metric_impl": impl, "blowup_threshold": 23.845039, "gate_tolerance": 0.05}

    def blown_rows(n=20, frac=0.0, absmax=3.0, **kw):
        return [_row(5000 + i, norm_input_blown_frames_frac=frac,
                     norm_input_absmax=absmax, **kw) for i in range(n)]

    # ---- 裁定 2：无归一化策略的 not_applicable 声明路径（四种牙）----
    na_rows = [_row(5000 + i, raw_obs_absmax=4.8) for i in range(20)]
    w("na_verified.json", _doc(na_rows, ckpt="synthetic://residual_raw_obs", input_contract={
        "not_applicable": {"reason": "SAC 直吃 raw 60 维 obs，训练与推理均无归一化（未用 VecNormalize）",
                           "obs_space": "raw_state", "train_time_obs_absmax": 5.0}}))
    w("na_no_reason.json", _doc(na_rows, ckpt="synthetic://residual_raw_obs", input_contract={
        "not_applicable": {"reason": "   ", "obs_space": "raw_state",
                           "train_time_obs_absmax": 5.0}}))
    w("na_no_closed_loop.json", _doc(
        [{k: v for k, v in r.items() if k != "raw_obs_absmax"} for r in na_rows],
        ckpt="synthetic://residual_raw_obs", input_contract={
            "not_applicable": {"reason": "无归一化", "train_time_obs_absmax": 5.0}}))
    w("na_out_of_range.json", _doc(
        [_row(5000 + i, raw_obs_absmax=9.0) for i in range(20)],
        ckpt="synthetic://residual_raw_obs", input_contract={
            "not_applicable": {"reason": "无归一化", "train_time_obs_absmax": 5.0}}))

    # ---- 监管 §12 分派：blown_metric_impl 指纹三态 ----
    w("impl_known.json", _doc(blown_rows(), ckpt="synthetic://a", input_contract=dict(ic_ok)))
    w("impl_missing_new.json", _doc(blown_rows(), ckpt="synthetic://a",
                                    input_contract={"blowup_threshold": 23.845039}))
    w("impl_unknown.json", _doc(blown_rows(), ckpt="synthetic://a",
                                input_contract={**ic_ok, "blown_metric_impl": "deadbeefcafe"}))

    # ---- 裁定 1：phase 词表矛盾三态 + 一致对照 ----
    rows_no_trace = []
    for i in range(20):
        r = _row(5000 + i, phase_at_end="done")
        r.pop("phase_trace")
        rows_no_trace.append(r)
    w("phase_mismatch_no_trace.json", _doc(rows_no_trace, ckpt="synthetic://a",
                                          input_contract=dict(ic_ok)))
    w("phase_mismatch_per_frame.json", _doc(
        blown_rows(phase_at_end="done", phase_trace=["approach", "grasp", "hold"]),
        ckpt="synthetic://a", input_contract=dict(ic_ok)))
    w("phase_ok_controller_log.json", _doc(
        blown_rows(phase_at_end="done",
                   phase_trace=["approach", "descend", "grasp", "lift", "hold", "done"]),
        ckpt="synthetic://a", input_contract=dict(ic_ok)))
    w("phase_ok_per_frame.json", _doc(
        blown_rows(phase_at_end="hold", phase_trace=["approach", "grasp", "hold"]),
        ckpt="synthetic://a", input_contract=dict(ic_ok)))

    # ---- 裁定 3：带外拒绝（文件名必须命中豁免册登记的臂名）----
    w("official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json", _doc(
        blown_rows(frac=0.5, absmax=99.0), ckpt="synthetic://stdfloor",
        input_contract={**ic_ok, "blowup_threshold": 12.469445}))

    # ---- B-3：insufficient_lift「差多少」诊断（数值可手算）----
    fr = [0.0200, 0.0300, 0.0350, 0.0360, 0.0372, 0.0380, 0.0395, 0.0500]
    rows_i = [_row(5000 + i, final_rise=v, norm_input_blown_frames_frac=0.0,
                   norm_input_absmax=3.0) for i, v in enumerate(fr)]
    rows_i += [_row(5060 + i, norm_input_blown_frames_frac=0.0, norm_input_absmax=3.0)
               for i in range(4)]
    w("insuff_diag.json", _doc(rows_i, ckpt="synthetic://a", input_contract=dict(ic_ok)))

    # ---- v1.4 裁定 14（DR-D09）：证据不足 ⇒ 失效模式标签必须弃权 ----
    # 三份夹具是**同一次物理评测**的三种字段可得性，对应 A 的最小复现
    # （docs/a_handoff_to_b_gate_vocabulary_20260928.md §2）：同一次 run，
    # 只差 held_at_end / final_rise / terminal_kind / phase_at_end 在不在，
    # v1.3 就会在 flick 与 insufficient_lift 之间翻。
    def _lbl_rows(**drop):
        rs = []
        for i in range(6):
            r = _row(5000 + i, final_rise=0.030, held_at_end=True, phase_at_end="grasp",
                     phase_trace=["approach", "descend", "grasp"],
                     terminal_kind="horizon_exhausted", steps=300,
                     norm_input_blown_frames_frac=0.0, norm_input_absmax=3.0)
            for k in drop:
                r.pop(k, None)
            rs.append(r)
        return rs

    w("label_abstain_partial.json", _doc(
        _lbl_rows(final_rise=1, held_at_end=1, phase_at_end=1, terminal_kind=1),
        ckpt="synthetic://a", input_contract=dict(ic_ok)))
    w("label_strict_reportable.json", _doc(_lbl_rows(), ckpt="synthetic://a",
                                           input_contract=dict(ic_ok)))
    w("label_terminal_kind_only.json", _doc(_lbl_rows(terminal_kind=1), ckpt="synthetic://a",
                                            input_contract=dict(ic_ok)))

    # ---- v1.5（裁定 10 / DR-008）：clip_at_train_absmax 通道的夹具与**候选豁免册** ----
    # 为什么必须合成：真实的目标臂只有一条（trimdone0_minmax_k2_lr1e-5_s20k_seed0），
    # 而这条通道有 14 种走向（1 种受理 + 13 种拒绝）。只测「受理成功」那一条等于没测 ——
    # 下次谁把牙拔了（例如把带内检查恢复成对所有 kind 生效、或把晋级闸放宽成
    # 「exonerated 即可升 violated」），自检照样全绿。
    # 候选豁免册同样写在 FIXDIR（不纳版控）：**绝不**把合成 sha256 写进 configs/。
    C_TRAIN = 12.469445
    ic_clip = {"blown_metric_impl": impl, "blowup_threshold": C_TRAIN, "gate_tolerance": 0.05}
    ARM_FILE = "official_act_truth20_synthetic_clip_arm.json"
    PROBE12 = "official_act_truth20_synthetic_clip_arm_clipC12p469445.json"
    PROBE5 = "official_act_truth20_synthetic_clip_arm_clipC5p0.json"
    PROBE_NC = "official_act_truth20_synthetic_clip_arm_noclip.json"
    BAND_FILE = "official_act_truth20_synthetic_band_violated.json"
    # 超阈（0.212 > 0.05）-> violated；20 局全受控成功 -> 免罪成立后 gate_pass 应为 True
    w(ARM_FILE, _doc(blown_rows(frac=0.212, absmax=40.0), ckpt="synthetic://k2_seed0",
                     input_contract=dict(ic_clip)))
    w(PROBE12, _doc(blown_rows(frac=0.212, absmax=40.0), ckpt="synthetic://k2_seed0",
                    input_contract=dict(ic_clip),
                    execution_constraints={"norm_input_clip": C_TRAIN}))
    w(PROBE5, _doc(blown_rows(frac=0.212, absmax=40.0), ckpt="synthetic://k2_seed0",
                   input_contract=dict(ic_clip),
                   execution_constraints={"norm_input_clip": 5.0}))
    w(PROBE_NC, _doc(blown_rows(frac=0.212, absmax=40.0), ckpt="synthetic://k2_seed0",
                     input_contract=dict(ic_clip)))
    # 带内但超阈（0.05 < 0.06 <= 0.08）-> violated：专门用来测「晋级闸按 kind 分路」
    w(BAND_FILE, _doc(blown_rows(frac=0.06, absmax=14.0), ckpt="synthetic://band",
                      input_contract=dict(ic_clip)))

    def sha_of(name):
        return hashlib.sha256((FIXDIR / name).read_bytes()).hexdigest()

    def clip_entry(**over):
        e = {"scope": "artifact", "probe_kind": gate.PROBE_KIND_CLIP_AT_TRAIN_ABSMAX,
             "arm": "synthetic_clip_arm", "artifact": out[PROBE12], "sha256": sha_of(PROBE12),
             "clip_C": C_TRAIN, "ruling_ref": "合成夹具（DR-008 回归用例，非真实豁免）",
             "ruling10_conditions": {k: True for k in gate.RULING10_CONDITION_KEYS},
             "cosign": {"by": "D", "fact_basis": True, "gate_build_at_cosign": "synthetic"},
             "reason": "合成回归夹具：只用于验证通道的牙，不构成对任何真实臂的豁免"}
        e.update(over)
        return e

    def wreg(name, entry, key):
        p = FIXDIR / name
        p.write_text(json.dumps({"entries": {key: entry}}, ensure_ascii=False, indent=1,
                                sort_keys=True) + "\n", encoding="utf-8")
        out[name] = str(p.relative_to(ROOT))

    tgt, band = sha_of(ARM_FILE), sha_of(BAND_FILE)
    conds_all = {k: True for k in gate.RULING10_CONDITION_KEYS}
    reblown_entry = {"scope": "artifact", "probe_kind": gate.PROBE_KIND_REBLOWN,
                     "artifact": out[PROBE12], "sha256": sha_of(PROBE12),
                     "ruling_ref": "合成夹具", "reason": "合成回归夹具"}
    wreg("exo_clip_ok.json", clip_entry(), tgt)
    wreg("exo_clip_scope_arm.json", clip_entry(scope="arm"), "synthetic_clip_arm")
    wreg("exo_clip_wrong_C.json", clip_entry(clip_C=5.0), tgt)
    wreg("exo_clip_no_clipC.json", clip_entry(clip_C=None), tgt)
    wreg("exo_clip_no_cosign.json", clip_entry(cosign={"by": "", "fact_basis": True}), tgt)
    wreg("exo_clip_cosign_nottrue.json", clip_entry(cosign={"by": "D", "fact_basis": "yes"}), tgt)
    wreg("exo_clip_cond_false.json",
         clip_entry(ruling10_conditions=dict(conds_all,
                                             cond2_verdicts_and_counts_identical=False)), tgt)
    wreg("exo_clip_cond_missing.json",
         clip_entry(ruling10_conditions={k: True for k in list(gate.RULING10_CONDITION_KEYS)[:-1]}),
         tgt)
    wreg("exo_clip_probe_wrongclip.json",
         clip_entry(artifact=out[PROBE5], sha256=sha_of(PROBE5)), tgt)
    wreg("exo_clip_probe_unstated.json",
         clip_entry(artifact=out[PROBE_NC], sha256=sha_of(PROBE_NC)), tgt)
    wreg("exo_clip_probe_sha_bad.json", clip_entry(sha256="0" * 64), tgt)
    wreg("exo_clip_evidence_missing.json",
         clip_entry(artifact="runs/infra/__no_such_probe__.json"), tgt)
    wreg("exo_reblown_outofband.json", dict(reblown_entry), tgt)
    wreg("exo_unknown_kind.json", clip_entry(probe_kind="brand_new_channel"), tgt)
    wreg("exo_reblown_inband_violated.json", dict(reblown_entry), band)
    return out


CASES = [
    {
        "id": 1,
        "fixture": "runs/infra/b_env_rebuild/base_truth20.json",
        "why": "防假阴性：scripted base（无学习策略）必须 20/20 受控成功；"
               "且输入契约判 not_applicable 而非 unverified —— 否则门禁会作废自己的 rise_cap 标定基准",
        "asserts": [
            ("gate_pass", True, "整体 PASS"),
            ("episodes_total", 20, "20 局全部可判"),
            (lambda r: acct(r, "controlled_success"), 20, "20/20 controlled_success"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "not_applicable",
             "无学习策略 -> 输入契约 not_applicable"),
            # v1.4 / DR-007 护栏：本产物缺 terminal_kind ⇒ field_class=partial，
            # 但三个失效模式标签都不读 terminal_kind，所以**不得**因裁定 14 被判 INVALID。
            ("labels_reportable", True, "只缺 terminal_kind -> 标签仍可报（DR-007 收窄）"),
            ("n_labels_abstained", 0, "标定基准不得被弃权掉"),
        ],
    },
    {
        "id": 2,
        "fixture": "runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20.json",
        "why": "防假阳性：residual 臂缺 final_rise/held_at_end，局末夹持无从证明，"
               "只能给 provisional_pass；且缺输入契约字段 -> INVALID（不是 PASS，也不是 FAIL）",
        "asserts": [
            (lambda r: acct(r, "controlled_success"), 0, "不得给 controlled_success"),
            ("n_provisional_pass", 20, "20 局 provisional_pass"),
            ("measurement_valid", False, "测量无效"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "unverified",
             "输入契约未验证"),
        ],
    },
    {
        "id": 3,
        "fixture": "runs/infra/b_normclip/noclip.json",
        "why": "防混淆：输入契约违例（94% 帧超训练分布）测的是数值事故，"
               "必须判 INVALID 而不是 FAIL —— FAIL 会被读成「策略能力不足」",
        "asserts": [
            ("measurement_valid", False, "测量无效"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated",
             "输入契约违例"),
            (lambda r: (r.get("input_contract") or {}).get("violated"), True, "violated 标志位"),
        ],
    },
    {
        "id": 4,
        "fixture": "runs/infra/b_normclip/clip3.json",
        "why": "防「把不同失效混成一类」：clip3 的四类裁定必须各自计数正确，"
               "over_lift（抬太高、方块全程在爪里）与 flick（真脱手）不得互相顶替",
        "asserts": [
            ("gate_pass", True, "有受控成功 -> PASS"),
            (lambda r: acct(r, "controlled_success"), 1, "1 局受控成功"),
            (lambda r: acct(r, "over_lift"), 12, "12 局 over_lift"),
            (lambda r: acct(r, "flick"), 1, "1 局 flick（v1.2 前误记为 2）"),
            (lambda r: acct(r, "insufficient_lift"), 1, "1 局 insufficient_lift（v1.2 新增类别）"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "verified_ok",
             "输入契约已验证"),
        ],
    },
    {
        "id": 5,
        "fixture": ("runs/infra/lerobot_act_env_20260928/"
                    "official_act_truth20_train24_lr1e-5_actionminmax_s20k_gatefields.json"),
        "why": "防误诊：A 的官方臂 raw 11 局**没有一局是弹射**，全部是抬起不足。"
               "这条决定了「唯一卡点是 dz 抬起高度」能否成立，也是 v1.2 拆类的直接动因",
        "asserts": [
            (lambda r: acct(r, "insufficient_lift"), 11, "11 局 insufficient_lift"),
            (lambda r: acct(r, "flick"), 0, "零弹射"),
            (lambda r: acct(r, "over_lift"), 0, "零 over_lift"),
            (lambda r: acct(r, "controlled_success"), 0, "零受控成功"),
        ],
    },
    {
        "id": 6,
        "fixture": "runs/infra/b_normclip/clip3.json",
        "why": "防不对称标注（v1.2.1 修的真实缺陷）：推理期对归一化输入截断也是执行侧介入，"
               "必须计入复合 policy。此前 9 个 clip 臂全被标成 composite_policy=false，"
               "「裁定对象是 policy+约束，不是底模」这条 warn 一次都没打印过",
        "asserts": [
            ("composite_policy", True, "输入截断 -> 复合 policy"),
            ("active_constraints", ["clip_norm_input"], "约束清单含 clip_norm_input"),
            (lambda r: (r.get("constraint_sides") or {}).get("clip_norm_input"), "input",
             "标注为输入侧（不是 exec 侧）"),
        ],
    },
    {
        "id": 7,
        "fixture": "runs/infra/b_normclip2/clip3_dzdb0.1.json",
        "why": "防漏计/重复计：同时开了输入截断与 dz 死区时，两侧约束都要在清单里，"
               "且各自标对来源（这是跨线比较能否成立的前提）",
        "asserts": [
            ("composite_policy", True, "复合 policy"),
            ("active_constraints", ["clip_norm_input", "dz_deadband"], "两侧约束都在"),
            (lambda r: (r.get("constraint_sides") or {}).get("dz_deadband"), "exec",
             "dz_deadband 标为执行侧"),
            (lambda r: (r.get("constraint_sides") or {}).get("clip_norm_input"), "input",
             "clip_norm_input 标为输入侧"),
        ],
    },
    {
        "id": 8,
        "fixture": "runs/infra/b_normclip/noclip.json",
        "why": "负对照：没开任何约束的臂**不得**被凭空标成复合 policy —— "
               "否则 composite 标志失去区分力，等于没标",
        "asserts": [
            ("composite_policy", False, "无约束 -> 非复合"),
            ("active_constraints", [], "约束清单为空"),
        ],
    },
    # ---- v1.3 新增：裁定 1（phase 词表矛盾 -> INVALID，不再静默判 flick）----
    {
        "id": 9,
        "fixture_from": "phase_mismatch_no_trace.json",
        "why": "裁定 1 主用例：phase_at_end='done'（状态机词表）却无 phase_trace。"
               "旧行为是静默走 per-frame strict 分支判 flick（把 20/20 的臂报成 20 局全脱手）；"
               "新行为必须移出分母 + 文件级 INVALID",
        "asserts": [
            ("n_phase_vocab_mismatch", 20, "20 局全部识别为词表矛盾"),
            ("n_unjudged", 20, "20 局移出分母（v4：unknown 既非成功也非失败）"),
            (lambda r: acct(r, "denominator"), 0, "policy_independent 分母归零"),
            (lambda r: acct(r, "flick"), 0, "**关键**：不再产生假 flick"),
            ("measurement_valid", False, "文件级判 INVALID"),
            ("gate_pass", False, "不得 PASS"),
            (lambda r: any(x.startswith("phase_vocab_mismatch")
                           for x in r["measurement_invalid_reasons"]), True, "失效理由必须点名裁定 1"),
        ],
    },
    {
        "id": 10,
        "fixture_from": "phase_mismatch_per_frame.json",
        "why": "裁定 1 的第二种矛盾：phase_at_end='done' 而 phase_trace 是逐帧分类"
               "（词表只有 approach/grasp/hold，永不产出 done）—— 两字段互相打脸",
        "asserts": [
            ("n_phase_vocab_mismatch", 20, "20 局识别为矛盾"),
            (lambda r: acct(r, "flick"), 0, "不产生假 flick"),
            ("measurement_valid", False, "INVALID"),
        ],
    },
    {
        "id": 11,
        "fixture_from": "phase_ok_controller_log.json",
        "why": "裁定 1 的正对照：同样是 phase_at_end='done'，但**带** 6 元素状态机 phase_trace "
               "-> 词表一致，必须照常判 20/20 受控成功（证明裁定 1 没有把合法状态机日志一起毙掉）",
        "asserts": [
            ("n_phase_vocab_mismatch", 0, "无矛盾"),
            (lambda r: acct(r, "controlled_success"), 20, "20/20 controlled_success"),
            ("measurement_valid", True, "测量有效"),
            ("gate_pass", True, "PASS"),
            ("phase_field_kinds", ["controller_log"], "词表判定为 controller_log"),
        ],
    },
    {
        "id": 12,
        "fixture_from": "phase_ok_per_frame.json",
        "why": "裁定 1 的第二个正对照：phase_at_end='hold' + 逐帧 trace（48 个官方臂就是这种）"
               "-> 必须零影响，否则 v1.3 会把全部官方臂打成 INVALID",
        "asserts": [
            ("n_phase_vocab_mismatch", 0, "无矛盾"),
            (lambda r: acct(r, "controlled_success"), 20, "20/20 controlled_success"),
            ("phase_field_kinds", ["per_frame"], "词表判定为 per_frame"),
            ("measurement_valid", True, "测量有效"),
        ],
    },
    # ---- v1.3 新增：裁定 2（not_applicable 声明路径，四种牙）----
    {
        "id": 13,
        "fixture_from": "na_verified.json",
        "why": "裁定 2 正用例：SAC 直吃 raw obs（无归一化）+ 显式声明 + 训练期与闭环原始 obs "
               "区间齐备且不越界 -> not_applicable_verified，测量有效（解开 residual 臂 "
               "raw 20/20 却 INVALID 的口径缺口，ADR-A-005 #2）",
        "asserts": [
            (lambda r: (r.get("input_contract") or {}).get("status"), "not_applicable_verified",
             "声明 + 区间证据齐备 -> verified"),
            (lambda r: (r.get("not_applicable_declaration") or {}).get("status"), "verified_in_range",
             "原始 obs 区间检查通过"),
            ("measurement_valid", True, "测量有效"),
            (lambda r: acct(r, "controlled_success"), 20, "20/20 controlled_success"),
            ("gate_pass", True, "PASS"),
        ],
    },
    {
        "id": 14,
        "fixture_from": "na_no_reason.json",
        "why": "裁定 2 牙 1：声明了但 reason 是空白 —— 声明不等于豁免",
        "asserts": [
            (lambda r: (r.get("input_contract") or {}).get("status"), "not_applicable_unverified",
             "无理由的声明 -> INVALID"),
            ("measurement_valid", False, "测量无效"),
            ("gate_pass", False, "不得 PASS"),
        ],
    },
    {
        "id": 15,
        "fixture_from": "na_no_closed_loop.json",
        "why": "裁定 2 牙 2：有训练期区间但**没有闭环原始 obs 区间**（既无块级字段也无逐局 "
               "raw_obs_absmax）-> 区间检查做不了，仍判 INVALID",
        "asserts": [
            (lambda r: (r.get("not_applicable_declaration") or {}).get("status"),
             "declared_no_closed_loop_range", "缺闭环区间"),
            ("measurement_valid", False, "测量无效"),
            (lambda r: acct(r, "controlled_success"), 20,
             "逐局判据仍然全过 —— 说明 INVALID 是**测量**问题，不是策略失败"),
        ],
    },
    {
        "id": 16,
        "fixture_from": "na_out_of_range.json",
        "why": "裁定 2 牙 3：闭环 raw obs absmax=9.0 远超训练期上界 5.0×1.05=5.25 "
               "-> violated_out_of_range，与归一化炸穿同性质",
        "asserts": [
            (lambda r: (r.get("not_applicable_declaration") or {}).get("status"),
             "violated_out_of_range", "区间检查未过"),
            (lambda r: (r.get("not_applicable_declaration") or {}).get("rows_out_of_range"), 20,
             "20 局全部越界"),
            ("measurement_valid", False, "测量无效"),
            (lambda r: any(x.startswith("raw_obs_out_of_range")
                           for x in r["measurement_invalid_reasons"]), True, "失效理由点名区间越界"),
        ],
    },
    # ---- v1.3 新增：监管 §12 分派（blown_metric_impl 指纹三态）----
    {
        "id": 17,
        "fixture_from": "impl_known.json",
        "why": "指纹正用例：带已知 impl 指纹 -> 指纹写进裁定 JSON 且放行",
        "asserts": [
            (lambda r: (r.get("blown_metric") or {}).get("status"), "known", "已知实现"),
            (lambda r: (r.get("input_contract") or {}).get("blown_metric_impl"),
             "52eae25ee2d7", "指纹写进裁定 JSON（§12 分派）"),
            ("measurement_valid", True, "测量有效"),
        ],
    },
    {
        "id": 18,
        "fixture_from": "impl_missing_new.json",
        "why": "指纹核心牙：记录了 blown 字段却**没有** impl 指纹，且不在存量豁免册里 "
               "-> 按新产物**拒判**（§12 实测同一轨迹两条路径给出 0.2120 vs 0.1180）",
        "asserts": [
            (lambda r: (r.get("blown_metric") or {}).get("status"), "missing_new_reject", "拒判"),
            (lambda r: (r.get("blown_metric") or {}).get("reject"), True, "reject 标志"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "missing_new_reject",
             "ic_status 被覆盖为拒判"),
            ("measurement_valid", False, "测量无效"),
            (lambda r: any(x.startswith("blown_impl_missing")
                           for x in r["measurement_invalid_reasons"]), True, "失效理由点名缺指纹"),
        ],
    },
    {
        "id": 19,
        "fixture_from": "impl_unknown.json",
        "why": "指纹第三态：有指纹但不在已知清单 -> **不**判 INVALID（D 的裁定是「缺指纹则拒判」，"
               "未知指纹不等于缺失），但必须记 unknown_impl 并禁止引用",
        "asserts": [
            (lambda r: (r.get("blown_metric") or {}).get("status"), "unknown_impl", "未知实现"),
            (lambda r: (r.get("blown_metric") or {}).get("reject"), False, "不拒判"),
            ("measurement_valid", True, "测量仍有效"),
        ],
    },
    # ---- v1.3 新增：裁定 3（探针豁免的带外拒绝）----
    {
        "id": 20,
        "fixture_from": "official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json",
        "why": "裁定 3 的牙：文件名命中豁免册登记的臂名，但 mean_blown=0.5 远超争议带上界 0.08 "
               "-> 豁免**不受理**，§12「带外 INVALID 维持」不能被豁免册翻案",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "out_of_band_refused",
             "带外拒绝"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持 violated"),
            ("measurement_valid", False, "测量无效"),
        ],
    },
    # ---- v1.3 新增：B-3 insufficient_lift「差多少」诊断（数值可手算）----
    {
        "id": 21,
        "fixture_from": "insuff_diag.json",
        "why": "B-3：insufficient_lift 是当前主失效模式（A 线 21 臂合计 219 局），只有计数无法"
               "回答「差一点点还是差很多」，也就无法判断该修策略还是该由 D 重定 C5。"
               "夹具数值手算：insuff 7 局 final_rise=[0.02,0.03,0.035,0.036,0.0372,0.038,0.0395]，"
               "中位 0.036 -> 中位差 0.004；≥0.035 的有 5 局",
        "asserts": [
            (lambda r: (r.get("insuff_diagnostic") or {}).get("n"), 7, "7 局 insufficient_lift"),
            (lambda r: (r.get("insuff_diagnostic") or {}).get("final_rise_median"), 0.036, "中位 0.036"),
            (lambda r: (r.get("insuff_diagnostic") or {}).get("gap_median"), 0.004, "中位差 0.004 m"),
            (lambda r: (r.get("insuff_diagnostic") or {}).get("gap_min_best"), 0.0005,
             "最好的一局只差 0.0005 m"),
            (lambda r: (r.get("insuff_diagnostic") or {}).get("n_within_0p005"), 5,
             "5 局在门槛下方 0.005 m 内（±0.005 敏感带一翻即变受控成功）"),
            (lambda r: (r.get("insuff_diagnostic") or {}).get("frac_within_0p005"), 0.714,
             "占比 0.714 —— 高占比说明主要卡在阈值上，须走 ADR-A-005 #3 由 D 裁定"),
            (lambda r: acct(r, "controlled_success"), 5, "同夹具里 5 局真受控成功（对照）"),
        ],
    },
    {
        "id": 22,
        "fixture_from": "label_abstain_partial.json",
        "why": "v1.4 裁定 14（DR-D09）：final_rise/held_at_end/phase_at_end 全缺时，C4 落到 "
               "HOLD_PHASES_STRICT={hold} 分支拒绝 end_phase=grasp -> c4=False -> 一路返回**最重的"
               "失效模式 flick**。A 的最小复现实测 5 臂 **16 局假 flick**（11+3+2），补测后全部翻成 "
               "insufficient_lift，使可引用 flick 只剩 2 局 / 920 局。证据不足必须弃权，不得猜成脱手弹射",
        "asserts": [
            ("field_class", "partial", "字段等级 partial"),
            ("labels_reportable", False, "标签不可报"),
            (lambda r: acct(r, "flick"), 0, "不得输出 flick"),
            (lambda r: acct(r, "insufficient_lift"), 0, "也不得改判成 insufficient_lift（同样是猜）"),
            ("n_labels_abstained", 6, "6 局标签弃权"),
            ("n_unjudged", 6, "全部移入 unjudged（v4：unknown 既不是成功也不是失败，移出分母）"),
            ("measurement_valid", False, "测量无效"),
            (lambda r: any("evidence_missing" in str(x)
                           for x in (r.get("measurement_invalid_reasons") or [])), True,
             "INVALID 理由点名 evidence_missing"),
            (lambda r: (r["per_episode"][0].get("evidence") or {}).get("label_before_abstain"),
             "flick", "原标签保留可追溯（不销毁证据，对齐 A 的 *_raw 做法）"),
        ],
    },
    {
        "id": 23,
        "fixture_from": "label_strict_reportable.json",
        "why": "裁定 14 的**反方向**护栏：同一次物理评测补齐 4 个字段后 field_class=strict，"
               "标签必须照常输出且答案是 insufficient_lift（不是 flick）。"
               "对应 A §4.2「strict 不得误伤」——改动只许让 partial 弃权，不许动 strict",
        "asserts": [
            ("field_class", "strict", "字段齐 -> strict"),
            ("labels_reportable", True, "标签可报"),
            (lambda r: acct(r, "insufficient_lift"), 6, "6 局 insufficient_lift（final_rise=0.030 < 0.04）"),
            (lambda r: acct(r, "flick"), 0, "不是 flick —— 这就是补测前后的差别"),
            ("n_labels_abstained", 0, "strict 不得弃权"),
            ("measurement_valid", True, "测量有效"),
        ],
    },
    {
        "id": 24,
        "fixture_from": "label_terminal_kind_only.json",
        "why": "**DR-007 收窄的护栏**：只缺 terminal_kind 的产物（base-only 标定件的真实形状，"
               "runs/infra/b_env_rebuild/base_truth20.json 就只缺这一项）。三个失效模式标签**不读** "
               "terminal_kind（它走终局分支那条独立弃权路径），所以标签仍可报。"
               "若按 DR-D09 字面实现（field_class != strict 即弃权 + measurement_valid=False），"
               "rise_cap=0.15 的标定基准会被判 INVALID —— 门禁作废自己的锚点"
               "（本文件 :741 注释早就警告过这种自伤）。本例防止该回退",
        "asserts": [
            ("field_class", "partial", "字段等级仍是 partial（只缺 terminal_kind）"),
            ("labels_reportable", True, "但标签可报"),
            ("n_labels_abstained", 0, "不得弃权"),
            (lambda r: acct(r, "insufficient_lift"), 6, "标签照常输出"),
            ("measurement_valid", True, "测量仍有效"),
            ("gate_pass", False, "但没有受控成功 -> 不 PASS（insuff 不是成功）"),
        ],
    },
    # ---- v1.5 新增（裁定 10 / DR-008）：clip_at_train_absmax 通道，1 受理 + 13 拒绝 ----
    # 每个用例都用**候选豁免册**（FIXDIR 下生成），跑完立即还原 gate.EXONERATION_DOC，
    # 不碰 configs/b_probe_exonerations.json。
    {
        "id": 25,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_ok.json",
        "why": "裁定 10 通道的**受理**路径（DR-008 决定 1/2/3/5）：blown=0.212 带外、"
               "scope=artifact、clip_C == 产物自报训练期 absmax、五条准入全 true、D 已会签、"
               "探针自报截断值 == clip_C ⇒ violated 升为 probe_exonerated，measurement_valid=True",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "exonerated", "豁免受理"),
            (lambda r: (r.get("probe_exoneration") or {}).get("band_checked"), False,
             "本通道不做争议带检查（带内检查留给 reblown 通道）"),
            (lambda r: (r.get("probe_exoneration") or {}).get("probe_clip_C"), 12.469445,
             "探针自报截断值已回显"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "probe_exonerated",
             "ic_status 由 violated 晋级"),
            ("measurement_valid", True, "测量有效（裁定 12 的唯一救济通道生效）"),
            ("gate_pass", True, "20 局全受控成功 -> PASS"),
            (lambda r: acct(r, "controlled_success"), 20, "三套账不受免罪影响（cond5）"),
        ],
    },
    {
        "id": 26,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_scope_arm.json",
        "why": "DR-008 决定 2 的牙：裁定 10 通道**只受理 scope=artifact**。臂级会让豁免随臂迁移"
               "（同臂重新评测后不必重做探针就被免罪）。注意本夹具 impl 指纹是 known，"
               "所以命中的是**新增**的 scope 牙，不是既有的 scope_requires_known_impl",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"),
             "clip_channel_requires_artifact_scope", "臂级登记被拒"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持原判"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 27,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_wrong_C.json",
        "why": "DR-008 决定 3 条件 ② 的牙：登记的 clip_C=5.0 ≠ 产物自报训练期 absmax=12.469445。"
               "A 的判别力反证已实测 C=5.0 时 seed 5007 verdict 翻转 ⇒「截得越紧越安全」是假的，"
               "C 必须钉死。没有这条牙，册子里写个任意 C 就能给任意臂免罪",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"),
             "clip_c_not_train_absmax", "C 不是 train-absmax -> 拒绝"),
            (lambda r: (r.get("probe_exoneration") or {}).get("artifact_train_absmax"), 12.469445,
             "产物自报值已回显（可复核）"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持原判"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 28,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_no_clipC.json",
        "why": "条目根本没写 clip_C ⇒ 无法核验条件 ①，必须拒绝而不是当成 0 或跳过",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "clip_c_undeclared",
             "缺 clip_C -> 拒绝"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持原判"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 29,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_no_cosign.json",
        "why": "裁定 16.4 的牙：条目「由 B 写、**D 会签**」。会签人为空 ⇒ B 不能自签",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "cosign_missing",
             "无会签 -> 拒绝"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持原判"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 30,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_cosign_nottrue.json",
        "why": "会签块存在但 fact_basis 不是布尔 true（写了字符串 \"yes\"）⇒ 同样拒绝。"
               "真值判断必须是 `is True`，否则任意非空值都能冒充会签",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "cosign_missing",
             "fact_basis 非 true -> 拒绝"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 31,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_cond_false.json",
        "why": "裁定 16.4 要求条目含五条准入的**逐条核对**；cond2（逐局 verdict 与计数相同）"
               "写成 false ⇒ 事实基础不成立，必须拒绝",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"),
             "entry_conditions_incomplete", "五条准入有 false -> 拒绝"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持原判"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 32,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_cond_missing.json",
        "why": "五条准入少登记一条（缺 cond5）⇒ 拒绝。「少写一条」和「写 false」必须同样对待，"
               "否则漏项会被读成通过",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"),
             "entry_conditions_incomplete", "缺条目 -> 拒绝"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 33,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_probe_wrongclip.json",
        "why": "DR-008 决定 3 条件 ⑤ 的牙：探针产物**自己**记录的截断值是 5.0，"
               "而册子登记 clip_C=12.469445 ⇒ 登记的证据不是这次探针。判 "
               "probe_exoneration_invalid（登记假证据比没登记更糟）",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "probe_clip_mismatch",
             "探针自报截断值 != 登记 C"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "probe_exoneration_invalid",
             "并入证据失效家族"),
            ("measurement_valid", False, "测量无效"),
        ],
    },
    {
        "id": 34,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_probe_unstated.json",
        "why": "探针产物根本没记录执行侧截断值 ⇒ 无法核验它真截在 C 上，同样判证据失效",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "probe_clip_unstated",
             "探针未记录截断值"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "probe_exoneration_invalid",
             "并入证据失效家族"),
            ("measurement_valid", False, "测量无效"),
        ],
    },
    {
        "id": 35,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_probe_sha_bad.json",
        "why": "既有的证据 sha 牙在新通道上同样生效：登记 sha 与实测不符 ⇒ 证据被改写/换了文件",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "evidence_sha_mismatch",
             "sha256 不匹配"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "probe_exoneration_invalid",
             "判 invalid 而非静默忽略"),
            ("measurement_valid", False, "测量无效"),
        ],
    },
    {
        "id": 36,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_clip_evidence_missing.json",
        "why": "既有的证据存在性牙在新通道上同样生效：探针文件不存在 ⇒ 判 invalid",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "evidence_missing",
             "证据产物不存在"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "probe_exoneration_invalid",
             "判 invalid"),
            ("measurement_valid", False, "测量无效"),
        ],
    },
    {
        "id": 37,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_reblown_outofband.json",
        "why": "**DR-008 决定 1 的保守性护栏**：同一个带外臂（0.212）改按 reblown_single_source "
               "登记，必须**仍然**被带外拒绝。分通道不是给旧通道开口子",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "out_of_band_refused",
             "带内通道带外拒绝（行为与 v1.4 逐字一致）"),
            (lambda r: (r.get("probe_exoneration") or {}).get("band_checked"), True,
             "本通道做了争议带检查"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated", "ic_status 维持原判"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 38,
        "fixture_from": "official_act_truth20_synthetic_clip_arm.json",
        "exoneration_registry_from": "exo_unknown_kind.json",
        "why": "白名单语义的牙：未知 probe_kind 一律按**带内**处理。新增通道必须显式进 "
               "BAND_EXEMPT_PROBE_KINDS 并配自己的牙，不能靠写个新 kind 名绕过争议带",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "out_of_band_refused",
             "未知 kind -> 带内 -> 带外拒绝"),
            (lambda r: (r.get("probe_exoneration") or {}).get("band_checked"), True, "按带内处理"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
    {
        "id": 39,
        "fixture_from": "official_act_truth20_synthetic_band_violated.json",
        "exoneration_registry_from": "exo_reblown_inband_violated.json",
        "why": "**DR-008 决定 5 的牙（晋级闸按 kind 分路）**：带内（0.06）但超阈 -> violated，"
               "reblown 通道证据齐全 -> 豁免状态是 exonerated，**但 ic_status 不得晋级**。"
               "若把晋级闸放宽成「exonerated 即可升 violated」，本例立刻变红 —— 那等于让"
               "「重测一次尺子」推翻一个真的超阈",
        "asserts": [
            (lambda r: (r.get("probe_exoneration") or {}).get("status"), "exonerated",
             "豁免本身受理（带内 + 证据齐）"),
            (lambda r: (r.get("input_contract") or {}).get("status"), "violated",
             "但 reblown 通道**不能**把 violated 晋级"),
            ("measurement_valid", False, "测量仍无效"),
        ],
    },
]


def eval_assert(row, spec):
    getter, expect, note = spec
    if callable(getter):
        got = getter(row)
        name = getattr(getter, "__name__", "lambda")
    else:
        got = row.get(getter)
        name = getter
    return {"field": name, "expect": expect, "got": got, "note": note, "ok": got == expect}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rise-cap", type=float, default=None, help="默认取门禁常量 RISE_CAP")
    ap.add_argument("--final-rise", type=float, default=None, help="默认取门禁常量 FINAL_RISE_MIN")
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_gate_regression/selfcheck.json"))
    a = ap.parse_args()

    gate = load_gate()
    rise_cap = gate.RISE_CAP if a.rise_cap is None else a.rise_cap
    final_rise = gate.FINAL_RISE_MIN if a.final_rise is None else a.final_rise
    args = Args(rise_cap, final_rise)
    # v1.3：先生成合成夹具再解析 fixture_from。夹具内容确定性，重复生成字节一致，
    # 因此放在不纳版控的 runs/ 下也不会让本自检变成「只在某台机器上能跑」。
    synth = make_fixtures(gate)
    for case in CASES:
        if case.get("fixture_from"):
            case["fixture"] = synth[case["fixture_from"]]
        if case.get("exoneration_registry_from"):
            case["exoneration_registry"] = synth[case["exoneration_registry_from"]]
    print("合成夹具：%d 个 -> %s" % (len(synth), FIXDIR.relative_to(ROOT)))

    print("=" * 100)
    print("受控成功判据 §7 反例自检（可执行版）")
    print("门禁构建：gate_version=%s gate_build=%s spec_sha256=%s"
          % (gate.GATE_VERSION, gate.GATE_BUILD, gate.GATE_SPEC_SHA))
    print("判据：rise_cap=%.3f m  final_rise_min=%.3f m" % (rise_cap, final_rise))
    print("=" * 100)

    results, all_ok = [], True
    for case in CASES:
        path = ROOT / case["fixture"]
        rec = {"id": case["id"], "fixture": case["fixture"], "why": case["why"],
               "asserts": [], "ok": False, "status": None}
        if not path.exists():
            # 夹具缺失必须 FAIL：skip 会让这张表在重构后静默失去覆盖。
            rec["status"] = "fixture_missing"
            rec["asserts"] = [{"field": "-", "expect": "夹具存在", "got": "缺失",
                               "note": "夹具缺失按 FAIL 处理，不得 skip", "ok": False}]
            print("\n[#%d] %-70s %s" % (case["id"], Path(case["fixture"]).name, "夹具缺失 -> FAIL"))
            print("      %s" % case["fixture"])
            all_ok = False
            results.append(rec)
            continue

        # v1.5（DR-008）：候选豁免册按用例临时替换，跑完立即还原。
        # 用真实 configs/b_probe_exonerations.json 测拒绝路径是不可行的 —— 那需要往受版控的
        # 册子里写合成 sha256，等于把夹具污染进生产配置。
        saved_exo_doc = gate.EXONERATION_DOC
        if case.get("exoneration_registry"):
            gate.EXONERATION_DOC = case["exoneration_registry"]
        try:
            row = gate.judge_file(path, args)
        finally:
            gate.EXONERATION_DOC = saved_exo_doc
        if case.get("exoneration_registry"):
            rec["exoneration_registry"] = case["exoneration_registry"]
        if "error" in row:
            rec["status"] = "judge_error"
            rec["asserts"] = [{"field": "-", "expect": "可判定", "got": row["error"],
                               "note": "judge_file 报错", "ok": False}]
            print("\n[#%d] %-70s judge_error -> FAIL: %s"
                  % (case["id"], Path(case["fixture"]).name, row["error"]))
            all_ok = False
            results.append(rec)
            continue

        for spec in case["asserts"]:
            r = eval_assert(row, spec)
            rec["asserts"].append(r)
        rec["status"] = "judged"
        rec["ok"] = all(x["ok"] for x in rec["asserts"])
        rec["verdict_summary"] = {
            "gate_pass": row.get("gate_pass"),
            "measurement_valid": row.get("measurement_valid"),
            "input_contract_status": (row.get("input_contract") or {}).get("status"),
            "episodes_total": row.get("episodes_total"),
            "accounts_policy_independent": acct(row, "controlled_success") is not None and
                {k: acct(row, k) for k in ("controlled_success", "provisional_pass",
                                           "over_lift", "flick", "insufficient_lift")},
        }
        all_ok &= rec["ok"]
        results.append(rec)

        print("\n[#%d] %-70s %s" % (case["id"], Path(case["fixture"]).name,
                                    "PASS" if rec["ok"] else "**FAIL**"))
        print("      用途：%s" % case["why"])
        for x in rec["asserts"]:
            print("      [%s] %-26s 期望=%-14s 实测=%-14s %s"
                  % ("PASS" if x["ok"] else "FAIL", x["field"], x["expect"], x["got"], x["note"]))

    n_assert = sum(len(r["asserts"]) for r in results)
    n_ok = sum(1 for r in results for x in r["asserts"] if x["ok"])
    # 零断言不得报绿：一条都没评上时「全部通过」是空话（L0-c 恒真断言的同类陷阱）。
    if n_assert == 0:
        all_ok = False
    print("\n" + "=" * 100)
    if n_assert == 0:
        print("结论：**一条断言都没评上**（用例 %d 个、断言 0 条）→ 本自检无效，"
              "不得据此宣称门禁与规格一致" % len(CASES))
    else:
        print("结论：%d/%d 条断言通过，%d/%d 个用例通过 → %s"
              % (n_ok, n_assert, sum(1 for r in results if r["ok"]), len(CASES),
                 "门禁与本规格 §7 一致" if all_ok
                 else "**门禁行为与规格 §7 不一致：先修门禁或同步改规格，不得让本表长期红**"))
    print("=" * 100)

    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({
        "ok": all_ok, "gate_version": gate.GATE_VERSION, "gate_build": gate.GATE_BUILD,
        "gate_spec_sha256": gate.GATE_SPEC_SHA, "gate_spec_doc": gate.GATE_SPEC_DOC,
        "rise_cap": rise_cap, "final_rise_min": final_rise,
        "n_cases": len(CASES), "n_asserts": n_assert, "n_asserts_ok": n_ok,
        "cases": results,
        "guard": {"zero_assert_fails": True,
                  "note": "n_asserts==0 时强制 ok=False；夹具缺失按 FAIL 而非 skip"},
    }, indent=2, ensure_ascii=False, default=str) + "\n")
    print("写出:", outp)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
