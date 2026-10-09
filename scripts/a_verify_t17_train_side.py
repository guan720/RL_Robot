#!/usr/bin/env python3
"""A 线：T17 **训练侧**验证闸（B 交接单 §8 两项 / 裁定 37.1 解封后第一次真跑）。

与 `a_selfcheck_goal_conditioning_t17.py` 的分工（不要互相替代）
--------------------------------------------------------------
单元自检（G1–G9 + 5 个变异体）证的是**代码层**：计算图 goal 条件化、词表拒绝语义、
缺省路径逐字节向后兼容 —— 但它跑在**玩具规模**（1 局 / 60 帧 / 2 epoch）上，回答不了四件事：
  ① 真跑规模下 BC 是否**真的按 goal 分组**（B §8-2：「采集时就要分组，事后加 goal 输入没有可学差异」）；
  ② **训练之后**的 policy 是否仍对 goal 敏感（初始化时敏感 ≠ 训练后没被压成常量）；
  ③ 换向账本在**真跑 ckpt** 上是否随 A↔B 与 epoch 一起进账（B §8-1，黄金值 E6 的两个独立拒绝理由）；
  ④ 解封后**第一次真跑**是否真带了溯源旁挂件（裁定 37.1：`env_provenance.json` 由 P1 接线升为**必须有**，
     且新 lock 的 sha256 必须与重建目录两份**逐字相同**、并回显 0928 两份旧 lock）。
本闸判这四件事（V1–V8），全程只读他人文件，产物只写 A 自己的目录。

**本闸不得被用来声称「已学出方向差异」**：真帧 teacher（`LiftStateMachine`）只会 A→B，
`lift_B_to_A` 的演示源为 0 行 ⇒ `goal_conditioning_status.learnable_from_real_frames` **必须是 false**，
V3 就是按「必须如实为 false」判的（若它为 true 而 coverage 仍只覆盖 1 个方向，那是产物在撒谎 ⇒ 判红）。
V2 判的是**wiring 在训练后仍然活着**，不是「学出了方向」。

模式
----
  默认          读两路真跑产物（goal / default）+ 现场跑三次 audit，判 V1–V8，写 JSON 留档。
  --skip-audit  只读已有的 audit JSON（复跑判据、不重跑 env）。
  --selftest    变异自检：证明每道判据**有牙**（fixture 全在内存里，不写任何文件、不碰真产物）。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT = "scripts/run_act_lift_runtime_failure_audit.py"
NEW_LOCKS = ROOT / "runs/infra/a_lerobot_env_rebuild_20260929"
OLD_LOCKS = ROOT / "runs/infra/lerobot_act_env_20260928"
LOCK_FILES = ("requirements.lock.txt", "requirements.eval.lock.txt")
SIDECAR = "env_provenance.json"
# 与单元自检 G2 **同一个阈值**（不自创第二套：两套阈值就等于没有阈值）
# —— 但**阈值不能跨 regime 搬**（ADR-A-018，裁定 36.4 同族）：G2 的 0.05 是在「**未训练**的随机初始化
# 网络」上立的，那时 goal 两列都是活的随机权重；真跑训练后，若真帧只覆盖 1 个方向，goal one-hot 在数据里
# 是**常量** ⇒ 未覆盖方向的列拿**零梯度**、停在初始化尺度，输出比必然很小。所以：
#   · **权重空间**的比值阈值照用 0.05（它判「goal 通路没被压成 0」，与训练状态无关）；
#   · **输出空间**的比值阈值**只在数据真的能学出方向差异时生效**（`learnable_from_real_frames=true`）。
GOAL_SENS_RATIO_MIN = 0.05
N_SENS_STATES = 8


def _sha256(path: Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def vocab_single_source() -> tuple:
    """词表的**单一事实源** = `LearnerConfig.goals` 的缺省值（ADR-A-015 教训②：断言字面量从实现取，不抄）。"""
    from harness.queue_td_learner import LearnerConfig
    return tuple(LearnerConfig.__dataclass_fields__["goals"].default)


def teacher_goal() -> str:
    from scripts.train_act_lift import TEACHER_GOAL
    return TEACHER_GOAL


def goal_sensitivity(ck: dict, vocab: tuple, n_states: int = N_SENS_STATES, seed: int = 0) -> dict:
    """训练**之后**的 policy 对 goal 是否仍敏感。相对口径（Δgoal / Δstate），与 G2 同型。"""
    from scripts.train_act_lift import ChunkPolicy
    rng = np.random.default_rng(seed)
    obs_dim = int(ck["obs_dim"])
    model = ChunkPolicy(obs_dim, int(ck["chunk_length"]), goals=tuple(vocab))
    model.load_state_dict(ck["model"])
    model.eval()
    mean = np.asarray(ck["obs_mean"], dtype=np.float32)
    std = np.asarray(ck["obs_std"], dtype=np.float32)
    d_goal, d_state = [], []
    with torch.no_grad():
        for _ in range(n_states):
            x = rng.normal(size=(obs_dim,)).astype(np.float32)
            xn = torch.from_numpy((x - mean) / std).unsqueeze(0)
            a = model(xn, goal=vocab[0])
            b = model(xn, goal=vocab[1])
            d_goal.append(float((a - b).abs().max()))
            x2 = x + rng.normal(scale=0.1, size=(obs_dim,)).astype(np.float32)
            c = model(torch.from_numpy((x2 - mean) / std).unsqueeze(0), goal=vocab[0])
            d_state.append(float((a - c).abs().max()))
    w = model.net[0].weight.detach().numpy()
    mg, ms = float(np.mean(d_goal)), float(np.mean(d_state))
    return {"max_abs_delta_goal": max(d_goal), "mean_abs_delta_goal": mg,
            "mean_abs_delta_state": ms, "ratio_goal_over_state": mg / (ms + 1e-12),
            "delta_std_across_states": float(np.std(d_goal)),
            "goal_col_absmax": float(np.abs(w[:, obs_dim:]).max()) if w.shape[1] > obs_dim else 0.0,
            "state_col_absmax": float(np.abs(w[:, :obs_dim]).max()), "n_states": n_states,
            "measured_on": "训练后的 ckpt（不是初始化）"}


def ckpt_facts(path: Path) -> dict:
    ck = torch.load(str(path), map_location="cpu")
    return {"exists": True, "keys": sorted(ck.keys()),
            "has_goal_keys": any(str(k).startswith("goal") for k in ck),
            "goal_vocab": list(ck.get("goal_vocab") or []), "goal_dim": ck.get("goal_dim"),
            "obs_dim": int(ck["obs_dim"]), "chunk_length": int(ck["chunk_length"]),
            "net0_in": int(ck["model"]["net.0.weight"].shape[1]),
            "state_dict_keys": sorted(ck["model"].keys()), "_raw": ck}


def run_audit(py: str, ckpt: Path, out: Path, log: Path, extra: list[str], args) -> dict:
    cmd = [py, str(ROOT / AUDIT), "--ckpt", str(ckpt), "--episodes", str(args.audit_episodes),
           "--seed0", str(args.audit_seed0), "--horizon", str(args.audit_horizon),
           "--chunk-length", "4", "--out", str(out)] + extra
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    log.write_text((r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""))
    doc = None
    if out.is_file():
        try:
            doc = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = None
    slim = None
    if doc:
        slim = {"goal_plan": doc.get("goal_plan"), "goal_source": doc.get("goal_source"),
                "goal_vocab": doc.get("goal_vocab"),
                "policy_goal_conditioned": doc.get("policy_goal_conditioned"),
                "goal_ledger": doc.get("goal_ledger"), "episodes": doc.get("episodes"),
                "task": doc.get("task"), "switch_every": doc.get("switch_every")}
    rec = {"rc": r.returncode, "out_exists": out.is_file(), "doc": slim,
           "refused": "LearnerRefused" in ((r.stderr or "") + (r.stdout or "")),
           "elapsed_s": round(time.time() - t0, 1), "cmd": " ".join(cmd[len(py) + 1:])}
    # rc / refused 是**进程级**证据，audit 的 JSON 产物里没有（拒绝时压根不写产物）⇒ 单独落一份 meta，
    # 否则 --skip-audit 复跑判据时 V7 只能拿到 None 而**假红**（本轮实测撞到的第 2 个判据缺陷）。
    try:
        out.with_suffix(out.suffix + ".meta.json").write_text(
            json.dumps({k: v for k, v in rec.items() if k != "doc"}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        pass
    return rec


def _slim_doc(doc):
    if not doc:
        return None
    return {"goal_plan": doc.get("goal_plan"), "goal_source": doc.get("goal_source"),
            "goal_vocab": doc.get("goal_vocab"),
            "policy_goal_conditioned": doc.get("policy_goal_conditioned"),
            "goal_ledger": doc.get("goal_ledger"), "episodes": doc.get("episodes"),
            "task": doc.get("task"), "switch_every": doc.get("switch_every")}


def collect(args) -> dict:
    d = Path(args.dir)
    vocab = vocab_single_source()
    tgoal = teacher_goal()
    facts = {"dir": str(d), "vocab_single_source": list(vocab), "teacher_goal": tgoal,
             "goal": {}, "default": {}, "audits": {}}
    for tag in ("goal", "default"):
        sub = d / f"{tag}_path"
        ck_p, cfg_p, prov_p = sub / "model_final.pt", sub / "config.json", sub / SIDECAR
        rec = {"ckpt_path": str(ck_p), "exists": ck_p.is_file()}
        if rec["exists"]:
            cf = ckpt_facts(ck_p)
            raw = cf.pop("_raw")
            rec.update(cf)
            rec["goal_sensitivity"] = (goal_sensitivity(raw, vocab) if cf["goal_dim"] else None)
        try:
            rec["config"] = json.loads(cfg_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rec["config"] = None
        try:
            rec["provenance"] = json.loads(prov_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rec["provenance"] = None
        facts[tag] = rec
    if not args.skip_audit:
        py = sys.executable
        facts["audits"]["alternate"] = run_audit(
            py, d / "goal_path/model_final.pt", d / "audit_alternate_trained.json",
            d / "audit_alternate_trained.log",
            ["--goal-plan", "alternate", "--switch-every", str(args.switch_every)], args)
        facts["audits"]["refuse"] = run_audit(
            py, d / "default_path/model_final.pt", d / "audit_refuse_should_not_exist.json",
            d / "audit_refuse.log", ["--goal-plan", "alternate", "--switch-every", str(args.switch_every)], args)
        facts["audits"]["legacy"] = run_audit(
            py, d / "default_path/model_final.pt", d / "audit_legacy_trained.json",
            d / "audit_legacy_trained.log", [], args)
    else:
        # 复用已有 audit 产物 + 它们的 *.meta.json（进程级证据）；缺 meta 就如实记 None，**不猜**
        for name, fn in (("alternate", "audit_alternate_trained.json"),
                         ("refuse", "audit_refuse_should_not_exist.json"),
                         ("legacy", "audit_legacy_trained.json")):
            p, mp = d / fn, d / (fn + ".meta.json")
            try:
                doc = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
            except json.JSONDecodeError:
                doc = None
            try:
                meta = json.loads(mp.read_text(encoding="utf-8")) if mp.is_file() else {}
            except json.JSONDecodeError:
                meta = {}
            facts["audits"][name] = {"rc": meta.get("rc"), "out_exists": p.is_file(),
                                     "doc": _slim_doc(doc), "refused": meta.get("refused"),
                                     "elapsed_s": meta.get("elapsed_s"),
                                     "reused_existing": True, "meta_present": bool(meta),
                                     "note": None if meta else "缺 *.meta.json ⇒ 进程级证据不可复用（重跑才有）"}
    facts["locks"] = {"new": {f: _sha256(NEW_LOCKS / f) for f in LOCK_FILES},
                      "old": {f: _sha256(OLD_LOCKS / f) for f in LOCK_FILES}}
    return facts


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, cid, name, ok, observed, required, *, blocking=True, note=""):
        self.rows.append({"id": cid, "name": name, "pass": bool(ok), "blocking": blocking,
                          "observed": observed, "required": required, "note": note})
        return bool(ok)

    @property
    def open(self) -> bool:
        return all(r["pass"] for r in self.rows if r["blocking"])

    def n_fail_blocking(self) -> int:
        return sum(1 for r in self.rows if r["blocking"] and not r["pass"])

    def n_warn(self) -> int:
        return sum(1 for r in self.rows if not r["blocking"] and not r["pass"])


def run_checks(f: dict) -> Checks:
    ck = Checks()
    vocab = list(f.get("vocab_single_source") or [])
    tgoal = f.get("teacher_goal")
    g, dfl = f.get("goal") or {}, f.get("default") or {}
    other = [x for x in vocab if x != tgoal]

    # ---- V1：真跑 ckpt 带词表，且 goal 真的进了第一层 ----
    v1 = {"goal_ckpt_exists": bool(g.get("exists")),
          "goal_vocab_matches_single_source": list(g.get("goal_vocab") or []) == vocab,
          "goal_dim_equals_len_vocab": g.get("goal_dim") == len(vocab) and g.get("goal_dim") is not None,
          "net0_in_equals_obs_plus_goal": g.get("net0_in") == (g.get("obs_dim") or -1) + (g.get("goal_dim") or 0),
          "no_extra_state_dict_keys": sorted(g.get("state_dict_keys") or []) == sorted(dfl.get("state_dict_keys") or [])}
    ck.add("V1", "真跑 goal ckpt：词表来自单一事实源 + goal 进第一层（B §8-2）",
           all(v1.values()), {"terms": v1, "goal_vocab": g.get("goal_vocab"),
                              "goal_dim": g.get("goal_dim"), "net0_in": g.get("net0_in"),
                              "obs_dim": g.get("obs_dim")},
           {"terms": {k: True for k in v1}, "goal_vocab": vocab},
           note="词表**不抄字面量**：从 `LearnerConfig.goals` 缺省取（ADR-A-015 教训②）。"
                "「不新增任何键」是向后兼容的硬要求（旧 ckpt 必须仍能 strict=True 加载）。")

    # ---- V2：训练**之后** policy 仍对 goal 敏感（wiring 没被压成常量）----
    sens = g.get("goal_sensitivity") or {}
    status = ((g.get("config") or {}).get("goal_conditioning_status")) or {}
    learnable = status.get("learnable_from_real_frames") is True
    w_ratio = ((sens.get("goal_col_absmax") or 0.0) /
               ((sens.get("state_col_absmax") or 0.0) + 1e-12))
    o_ratio = sens.get("ratio_goal_over_state") or 0.0
    v2 = {"measured": bool(sens),
          "delta_goal_nonzero": (sens.get("mean_abs_delta_goal") or 0.0) > 1e-6,
          "delta_varies_across_states": (sens.get("delta_std_across_states") or 0.0) > 0.0,
          "goal_col_weights_nonzero": (sens.get("goal_col_absmax") or 0.0) > 0.0,
          # 权重空间：goal 列没被训练压成 0（与 regime 无关，阈值照用 G2 的 0.05）
          "goal_col_weight_ratio_above_G2_threshold": w_ratio > GOAL_SENS_RATIO_MIN,
          # 输出空间：**只在数据能支撑方向差异时**才要求过阈值；单方向覆盖时判 not_applicable
          "output_ratio_ok_or_not_applicable": (o_ratio > GOAL_SENS_RATIO_MIN) if learnable else True}
    ck.add("V2", "**训练后**的 policy 仍对 goal 敏感（不是初始化时的假象）",
           all(v2.values()), {"terms": v2, "sensitivity": sens,
                              "goal_col_weight_ratio": w_ratio, "output_ratio": o_ratio,
                              "output_ratio_regime": ("learnable_from_real_frames=true ⇒ 阈值 %s 生效"
                                                      % GOAL_SENS_RATIO_MIN) if learnable else
                                                      ("not_applicable：真帧只覆盖 %s/%s 个方向 ⇒ goal one-hot 在数据里是常量，"
                                                       "未覆盖方向的列拿零梯度、停在初始化尺度，输出比必然小；"
                                                       "这**正是** V3 要求的 learnable_from_real_frames=false 的必然后果"
                                                       % (status.get("directions_with_real_frames"),
                                                          status.get("directions_total"))),
                              "threshold": GOAL_SENS_RATIO_MIN},
           {"terms": {k: True for k in v2}},
           note="阈值 %s 沿用单元自检 **G2**，但**分空间**用：权重空间无条件判（goal 通路没被压成 0），"
                "输出空间只在 `learnable_from_real_frames=true` 时判（否则数据根本不支持方向差异，"
                "要求输出比过阈值 = 要求产物撒谎）。**本条只证 wiring 在训练后仍活着**，"
                "不证「学出了方向差异」——那要先有第二个方向的演示源（见 V3）。"
                "首版把 G2 的输出阈值无条件搬到训练后 regime，是**跨口径搬阈值**（ADR-A-018）。" % GOAL_SENS_RATIO_MIN)

    # ---- V3：BC 在真跑规模下**确实按 goal 分组**，且缺方向如实记 0 ----
    cfg = g.get("config") or {}
    cov = cfg.get("goal_coverage") or {}
    status = cfg.get("goal_conditioning_status") or {}
    t_rows = ((cov.get(tgoal) or {}).get("train_rows"))
    o_rows = [((cov.get(x) or {}).get("train_rows")) for x in other]
    v3 = {"coverage_present": bool(cov),
          "teacher_direction_has_rows": isinstance(t_rows, int) and t_rows > 0,
          "teacher_rows_match_train_samples": isinstance(t_rows, int) and t_rows == cfg.get("train_samples"),
          "missing_directions_all_zero": all(r == 0 for r in o_rows) and len(o_rows) == len(other),
          "missing_direction_teacher_unavailable": all(
              (cov.get(x) or {}).get("teacher_available") is False for x in other),
          "learnable_from_real_frames_is_false": status.get("learnable_from_real_frames") is False,
          "directions_with_real_frames_is_1": status.get("directions_with_real_frames") == 1}
    ck.add("V3", "BC **按 goal 分组**采集（真跑规模），缺方向如实记 0 行、不冒充",
           all(v3.values()),
           {"terms": v3, "goal_coverage": cov, "goal_conditioning_status": status,
            "train_samples": cfg.get("train_samples"), "train_episodes": len(cfg.get("train_seeds") or []),
            "horizon": cfg.get("horizon")},
           {"terms": {k: True for k in v3}},
           note="`learnable_from_real_frames` **必须是 false**：真帧 teacher 只做 A→B，"
                "one-hot 在数据上是常量 ⇒ 单靠真帧 BC 学不出方向差异。**不得**把 V1/V2 读成「已学成 goal 条件」。")

    # ---- V4：缺省路径（goal-blind）向后兼容，真跑规模下仍无 goal 键 ----
    v4 = {"default_ckpt_exists": bool(dfl.get("exists")),
          "default_has_no_goal_keys": dfl.get("has_goal_keys") is False,
          "default_net0_in_equals_obs": dfl.get("net0_in") == dfl.get("obs_dim"),
          "default_config_has_no_goal_keys": not any(
              str(k).startswith("goal") or k == "teacher_goal" for k in (dfl.get("config") or {})),
          "default_goal_dim_absent": dfl.get("goal_dim") is None}
    ck.add("V4", "缺省路径真跑产物**无 goal 键**（0924 基线仍可原样复算）",
           all(v4.values()), {"terms": v4, "default_ckpt_keys": dfl.get("keys"),
                              "default_config_keys": sorted((dfl.get("config") or {}).keys())},
           {"terms": {k: True for k in v4}},
           note="向后兼容是**硬要求不是风格**：`ChunkPolicy(obs_dim, chunk)` 被 7 个 B 线脚本与 A 的 4 个入口原样调用。")

    # ---- V5：解封后第一次真跑的**溯源旁挂件**（裁定 37.1）----
    locks = f.get("locks") or {}
    v5_terms, v5_detail = {}, {}
    for tag in ("goal", "default"):
        prov = (f.get(tag) or {}).get("provenance") or {}
        lk = prov.get("lock") or {}
        new_sha = {k: (v or {}).get("sha256") for k, v in (lk.get("new_env_20260929") or {}).items()}
        old_sha = {k: (v or {}).get("sha256") for k, v in (lk.get("original_0928_untouched") or {}).items()}
        img = prov.get("imageio") or {}
        t = {"sidecar_present": bool(prov),
             "gate_allowed": ((prov.get("readiness_gate") or {}).get("verdict")) == "ALLOWED",
             "new_lock_sha_matches_files": new_sha == locks.get("new") and all(locks.get("new", {}).values()),
             "old_lock_sha_matches_files": old_sha == locks.get("old") and all(locks.get("old", {}).values()),
             "imageio_matches_new_lock": img.get("matches_new_lock") is True,
             "run_kind_is_train": prov.get("run_kind") == "train_act_lift"}
        v5_terms[tag] = t
        v5_detail[tag] = {"new_lock_sha12": {k: (v or "")[:12] for k, v in new_sha.items()},
                          "old_lock_sha12": {k: (v or "")[:12] for k, v in old_sha.items()},
                          "gate": (prov.get("readiness_gate") or {}).get("verdict"),
                          "imageio_effective": img.get("effective_version"),
                          "venv_realpath": ((prov.get("interpreter") or {}).get("venv_realpath"))}
    ok5 = all(all(t.values()) for t in v5_terms.values())
    ck.add("V5", "两路真跑都带 `env_provenance.json`，且新旧 lock sha256 **逐字相同**（裁定 37.1）",
           ok5, {"terms": v5_terms, "detail": v5_detail,
                 "lock_files_on_disk": {"new": {k: (v or "")[:12] for k, v in (locks.get("new") or {}).items()},
                                        "old": {k: (v or "")[:12] for k, v in (locks.get("old") or {}).items()}}},
           {"terms": {tag: {k: True for k in v5_terms[tag]} for tag in v5_terms}},
           note="D §9.6-5 的三个验收点：① 产物目录里真有旁挂件 ② 新 lock sha256 与重建目录两份逐字相同 "
                "③ 回显 0928 两份旧 lock（证明新旧并存、没覆盖）。另按裁定 37.3 回显 imageio 生效版本。")

    # ---- V6：真跑 ckpt 上的换向账本（B §8-1）----
    alt = (f.get("audits") or {}).get("alternate") or {}
    adoc = alt.get("doc") or {}
    ledger = adoc.get("goal_ledger") or []
    ids = [e.get("goal_id") for e in ledger]
    eps = [e.get("epoch") for e in ledger]
    v6 = {"audit_exit0": alt.get("rc") == 0,
          "both_directions_in_ledger": set(ids) == set(vocab),
          "epochs_strictly_increasing": all(b > a for a, b in zip(eps, eps[1:])) and len(eps) >= 2,
          "policy_goal_conditioned_true": adoc.get("policy_goal_conditioned") is True,
          "goal_source_not_fallback": bool(adoc.get("goal_source")) and "fallback" not in str(adoc.get("goal_source")),
          "goal_plan_alternate": adoc.get("goal_plan") == "alternate",
          "vocab_echoed": list(adoc.get("goal_vocab") or []) == vocab}
    ck.add("V6", "真跑 ckpt + `--goal-plan alternate`：换向与 epoch **一起**进账本（B §8-1）",
           all(v6.values()), {"terms": v6, "goal_ids": ids, "epochs": eps,
                              "goal_source": adoc.get("goal_source"), "n_ledger": len(ledger),
                              "audit": {k: alt.get(k) for k in ("rc", "elapsed_s", "out_exists")}},
           {"terms": {k: True for k in v6}},
           note="黄金值 E6 的**两个独立拒绝理由**：goal_id 必须来自任务定义并随 A↔B 变；换向必须与 epoch 一起入账。")

    # ---- V7：真跑的 goal-blind ckpt 要求换向 ⇒ 必须**拒绝**且不产文件 ----
    ref = (f.get("audits") or {}).get("refuse") or {}
    v7 = {"nonzero_exit": bool(ref.get("rc")),
          "learner_refused": ref.get("refused") is True,
          "no_artifact_written": ref.get("out_exists") is False}
    ck.add("V7", "真跑 goal-blind ckpt 要求 alternate ⇒ **拒绝**且不伪造产物",
           all(v7.values()), {"terms": v7, "rc": ref.get("rc"), "out_exists": ref.get("out_exists"),
                              "reused_existing": ref.get("reused_existing")},
           {"terms": {k: True for k in v7}},
           note="拒绝语义与 C 的 `LearnerRefused` 同一套（A 不另造第二种异常类型）。"
                "写了产物就等于伪造 goal 贯通证据。",
           )

    # ---- V8：真跑缺省路径 ⇒ 退回任务名占位并**标注来源** ----
    leg = (f.get("audits") or {}).get("legacy") or {}
    ldoc = leg.get("doc") or {}
    lids = [e.get("goal_id") for e in (ldoc.get("goal_ledger") or [])]
    v8 = {"audit_exit0": leg.get("rc") == 0,
          "goal_id_is_task_name": lids == ["lift"] * len(lids) and len(lids) >= 1,
          "goal_source_marked_fallback": "task_name_fallback" in str(ldoc.get("goal_source")),
          "policy_goal_conditioned_false": ldoc.get("policy_goal_conditioned") is False,
          "vocab_empty": list(ldoc.get("goal_vocab") or []) == []}
    ck.add("V8", "真跑缺省路径：退回任务名占位并**标注来源**（不冒充方向性 goal）",
           all(v8.values()), {"terms": v8, "goal_ids": lids, "goal_source": ldoc.get("goal_source")},
           {"terms": {k: True for k in v8}},
           note="占位是**允许的**，但必须自报来源；把占位写成方向性 goal 才是伪造。")
    return ck


def report(ck: Checks, gate_open: bool) -> None:
    for r in ck.rows:
        tag = "PASS" if r["pass"] else ("FAIL" if r["blocking"] else "WARN")
        print(f"[{tag}] {r['id']:<4} {r['name']}")
        if not r["pass"]:
            print(f"           observed = {json.dumps(r['observed'], ensure_ascii=False)[:900]}")
            print(f"           required = {json.dumps(r['required'], ensure_ascii=False)[:300]}")
        if r.get("note"):
            print(f"           note     = {r['note']}")
    print()
    print(f"T17_TRAIN_SIDE_VERIFY={'OPEN' if gate_open else 'CLOSED'}  "
          f"blocking_fail={ck.n_fail_blocking()}  warn={ck.n_warn()}  total_checks={len(ck.rows)}")


def _mutate(f: dict, fn) -> dict:
    out = copy.deepcopy(f)
    fn(out)
    return out


def selftest(f0: dict) -> int:
    base = run_checks(f0)
    vocab = list(f0.get("vocab_single_source") or [])
    tgoal = f0.get("teacher_goal")
    other = [x for x in vocab if x != tgoal]
    cases = [("T1 真实现场（两路真跑产物 + 三次 audit）-> OPEN", f0, (), True)]

    def m1(s):
        sens = s["goal"]["goal_sensitivity"]
        sens.update({"mean_abs_delta_goal": 0.0, "max_abs_delta_goal": 0.0,
                     "ratio_goal_over_state": 0.0, "delta_std_across_states": 0.0,
                     "goal_col_absmax": 0.0})
    cases.append(("M1 训练把 goal 通路压成 0（forward 丢 goal）-> CLOSED(V2)",
                  _mutate(f0, m1), ("V2",), False))

    def m1b(s):
        st = s["goal"]["config"]["goal_conditioning_status"]
        st["learnable_from_real_frames"] = True
        st["directions_with_real_frames"] = len(vocab)
    cases.append(("M1b 产物谎称真帧覆盖两个方向（⇒ 输出阈值必须生效）-> CLOSED(V2,V3)",
                  _mutate(f0, m1b), ("V2", "V3"), False))

    def m2(s):
        cov = s["goal"]["config"]["goal_coverage"]
        for x in other:
            cov[x] = {"train_rows": 999, "val_rows": 999, "teacher_available": True,
                      "note": "拿 A→B 的帧冒充"}
        s["goal"]["config"]["goal_conditioning_status"]["learnable_from_real_frames"] = True
        s["goal"]["config"]["goal_conditioning_status"]["directions_with_real_frames"] = len(vocab)
    cases.append(("M2 无 teacher 的方向拿 A→B 的行冒充 -> CLOSED(V3)",
                  _mutate(f0, m2), ("V3",), False))

    def m3(s):
        s["goal"]["provenance"] = None
    cases.append(("M3 真跑没写溯源旁挂件 -> CLOSED(V5)", _mutate(f0, m3), ("V5",), False))

    def m3b(s):
        lk = s["goal"]["provenance"]["lock"]["new_env_20260929"]
        for k in lk:
            lk[k]["sha256"] = "0" * 64
    cases.append(("M3b 旁挂件回显的新 lock sha256 与盘上不符 -> CLOSED(V5)",
                  _mutate(f0, m3b), ("V5",), False))

    def m4(s):
        led = s["audits"]["alternate"]["doc"]["goal_ledger"]
        s["audits"]["alternate"]["doc"]["goal_ledger"] = [led[0]] * len(led)
    cases.append(("M4 账本 goal_id 写死不换向（改动前形态）-> CLOSED(V6)",
                  _mutate(f0, m4), ("V6",), False))

    def m5(s):
        s["audits"]["refuse"].update({"rc": 0, "refused": False, "out_exists": True})
    cases.append(("M5 goal-blind 也放行 alternate 并写出产物 -> CLOSED(V7)",
                  _mutate(f0, m5), ("V7",), False))

    def m6(s):
        s["default"]["has_goal_keys"] = True
        s["default"]["goal_dim"] = len(vocab)
    cases.append(("M6 缺省路径漏出 goal 键（破坏向后兼容）-> CLOSED(V4,V1)",
                  _mutate(f0, m6), ("V4",), False))

    n_pass = 0
    print(f"{'变异自检':<56}{'期望':<22}结果")
    print("-" * 100)
    for name, st, expect_closed, expect_open in cases:
        c = run_checks(st)
        got = tuple(r["id"] for r in c.rows if not r["pass"] and r["blocking"])
        if expect_open:
            ok = c.open and not got
            want = "OPEN"
        else:
            ok = (not c.open) and all(x in got for x in expect_closed)
            want = "CLOSED(" + ",".join(expect_closed) + ")"
        print(f"    {name:<52}{want:<22}-> {'pass' if ok else 'FAIL'}   gate="
              f"{'OPEN' if c.open else 'CLOSED(' + ','.join(got) + ')'}")
        n_pass += 1 if ok else 0
    if not base.open:
        print("    [FAIL] 真实现场不是 OPEN —— 判据自检无意义，先修现场")
        return 1
    print(f"\n  T17 训练侧验证闸自检：{n_pass}/{len(cases)} 通过")
    return 0 if n_pass == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="runs/infra/a_t17_train_verify_20260929")
    ap.add_argument("--audit-episodes", type=int, default=2)
    ap.add_argument("--audit-horizon", type=int, default=300)
    ap.add_argument("--audit-seed0", type=int, default=5000)
    ap.add_argument("--switch-every", type=int, default=8)
    ap.add_argument("--skip-audit", action="store_true", help="只读已有 audit JSON，不重跑 env")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    facts = collect(args)
    if args.selftest:
        return selftest(facts)
    ck = run_checks(facts)
    report(ck, ck.open)
    sens = (facts.get("goal") or {}).get("goal_sensitivity") or {}
    print(f"  词表（单一事实源 LearnerConfig.goals）：{facts.get('vocab_single_source')}；"
          f"teacher 方向：{facts.get('teacher_goal')}")
    if sens:
        print(f"  训练后 goal 敏感度：Δgoal/Δstate = {sens.get('ratio_goal_over_state'):.4f}"
              f"（阈值 {GOAL_SENS_RATIO_MIN}），goal 列权重 absmax = {sens.get('goal_col_absmax'):.4g}")
    cov = ((facts.get("goal") or {}).get("config") or {}).get("goal_coverage") or {}
    print("  BC 分组行数：" + json.dumps({k: v.get("train_rows") for k, v in cov.items()}, ensure_ascii=False))
    print("  **不得**据此声称「已学出方向差异」：真帧只覆盖 1/2 个方向（V3 的 note）")
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        slim = copy.deepcopy(facts)
        for tag in ("goal", "default"):
            (slim.get(tag) or {}).pop("_raw", None)
        out.write_text(json.dumps({
            "check": "a_verify_t17_train_side",
            "ruling": "B 交接单 §8 两项 / 裁定 37.1（解封后第一次真跑）",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "authoritative_citation": {"gate_version": "v1.5", "gate_build": "f19f61341cbe",
                                       "spec_axis": "observation_only（裁定 29.1：不带 spec 值）"},
            "claim_boundary": ["goal 贯通（计算图 + 账本 + 真跑规模）成立",
                               "**不含**「已学出方向差异」（真帧 teacher 只覆盖 lift_A_to_B）",
                               "**不含** 48 臂权威表跨断点复用（那是另一件事，需真重跑）"],
            "verdict": "OPEN" if ck.open else "CLOSED",
            "blocking_fail": [r["id"] for r in ck.rows if r["blocking"] and not r["pass"]],
            "n_checks": len(ck.rows),
            "rows": ck.rows,
            "facts": slim,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  留档 -> {args.json_out}")
    return 0 if ck.open else 1


if __name__ == "__main__":
    sys.exit(main())
