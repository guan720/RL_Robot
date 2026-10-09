#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 线：**只读**调用团队 `vla_pipeline` 跑 validate → clean → qc，并把结果判成可红可绿的判词。

D→B2 执行单 §0.2 的硬约束：`/workspace/mnt/sppro/yhzhang91/scripts/yhzhang91/vla_pipeline`
是团队资产、在本仓范围外，**只读使用 + 只在自己的输出目录写**。本脚本把这句话做成**判据**：

  Q1 team_repo_readonly   跑前跑后对团队仓做全量 sha256+mtime 快照，**逐文件**比对。
                          **红**：任一文件字节变了 / 新增了文件 / 文件消失了。
                          （`PYTHONDONTWRITEBYTECODE=1` 防止 Python 往它们的 `__pycache__` 写 .pyc；
                            快照里也**显式排除** `__pycache__`，但排除项会在产物里逐条列出，不静默。）
  Q2 pipeline_completed   CLI rc==0、run 状态 completed、处理条数 == 输入条数。
                          **红**：rc!=0 / 状态非 completed / 条数不符（半跑不算过）。
  Q3 clean_set_zero_badcase  干净数据集必须 **0 badcase**。**红**：出现任一 badcase。
  Q4 rule_coverage_nonvacuous 每条 enabled 的规则**真的被调用过**（events 里 invocations>0）。
                          **红**：有规则 0 调用 ⇒ 那么「0 badcase」是**空洞真**，必须单独红
                          （同 B 的 V6「空比对的 0 处变化单独红」的纪律）。
  Q5 negative_control_caught 负对照数据集里，每条 episode 的**已知缺陷**必须被点名的规则抓住。
                          **红**：任一期望键没触发 ⇒ QC 管路对我们这批数据不敏感，
                          「全绿」不可采信。
  Q6 directions_balanced  两个方向条数相等、且每条都带 direction/goal 标签
                          （D→B2 §2.2：两个方向的条数必须相当；反向为 0 是全项目最硬的数据缺口）。
  Q7 data_kind_stamped    每条 episode 的 metadata 与 dataset_manifest 都盖了 `data_kind` 戳，
                          且形态夹具**不得**自称 demonstration（D→B2 §5：不得把「数据造出来了」
                          写成「双向能力有了」）。

用法
----
    /opt/conda/bin/python3 scripts/b2_run_team_qc.py \\
        --clean-input runs/vla/b2_bidir_demo_form_20260929/data \\
        --neg-input   runs/vla/b2_bidir_demo_form_20260929/data_neg

写入面：只写 `--out-dir`（默认 `runs/vla/b2_bidir_demo_form_20260929/qc_b2/`）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
TEAM_PIPELINE = Path("/workspace/mnt/sppro/yhzhang91/scripts/yhzhang91/vla_pipeline")
# 团队流水线**不是只读的**：2026-09-29 18:07 实测（/tmp/b2_formtest/data 的干净集跑完 qc 后，
# `converted_metadata_normal.json` 的 mtime/字节数都变了，每条缺陷 episode 里多出 `badcase.json`，
# 文件模式还被改成 0600）⇒ clean 段的 C05/C06/C08 与 qc 段的 BadcaseStore 都**就地写回输入目录**。
# 于是"只读使用团队资产"这句话必须落到**输入面**上：输入目录只允许落在 B2 自己的写入面里，
# 团队的 ABC130k 语料（`workplace/`）、原始 XDOF 数据（`yfw_input/`）、全局 `datasets/`
# 一律**禁止**当输入（跑一次就会就地改写别人的数据，且 NFS 已用 94%）。
FORBIDDEN_INPUT_SUBSTR = ("/workplace/", "/yfw_input/", "/datasets", "/vla_pipeline",
                          "/RL_Harness_v4_20260924/")
# 团队流水线会写回的文件（白名单）：超出这个集合的改动 ⇒ Q8 判红
PIPELINE_WRITABLE_NAMES = {"badcase.json", "converted_metadata_normal.json"}
CONFIG_DEFAULT = "runs/vla/b2_bidir_demo_form_20260929/config/b2_form_check.yaml"
METADATA_NAME = "converted_metadata_normal.json"
SNAPSHOT_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
STATUS_PASS, STATUS_WARN, STATUS_RED, STATUS_UNJUDGED = "PASS", "WARN", "RED", "UNJUDGED"


def _sha256(path: Path):
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()
    except Exception:
        return None


def _loads_or_none(txt):
    try:
        return json.loads(txt) if txt else None
    except Exception:
        return None


def snapshot_tree(root: Path):
    """全量快照：{相对路径: (sha256, size, mtime_ns)}。只读。"""
    out = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if any(part in SNAPSHOT_EXCLUDE_DIRS for part in p.parts):
            continue
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (_sha256(p), st.st_size, st.st_mtime_ns)
    return out


def diff_snapshot(before, after):
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    return {"n_changed": len(changed), "changed": changed[:40],
            "n_added": len(added), "added": added[:40],
            "n_removed": len(removed), "removed": removed[:40]}


class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, ok, observed, required, note="", status=None, ruling_ref="", red_when=""):
        if status is None:
            status = {True: STATUS_PASS, False: STATUS_RED, None: STATUS_UNJUDGED}[ok]
        self.checks.append({"id": cid, "ok": ok, "observed": observed, "required": required,
                            "note": note, "status": status, "ruling_ref": ruling_ref,
                            "red_when": red_when})
        return status

    def _n(self, st):
        return sum(1 for c in self.checks if c["status"] == st)

    @property
    def n_pass(self):
        return self._n(STATUS_PASS)

    @property
    def n_warn(self):
        return self._n(STATUS_WARN)

    @property
    def n_red(self):
        return self._n(STATUS_RED)

    @property
    def n_unjudged(self):
        return self._n(STATUS_UNJUDGED)


def count_episodes(input_dir: Path):
    return sorted(str(p.parent) for p in input_dir.rglob(METADATA_NAME))


def run_pipeline(cfg: Path, input_dir: Path, output_root: Path, run_id: str, batch_id: str,
                 py: str, max_workers: int, log_dir: Path):
    cmd = [py, "cli/main.py", "run", "--batch-id", batch_id, "--run-id", run_id,
           "--config", str(cfg), "--input", str(input_dir), "--output", str(output_root),
           "--max-workers", str(max_workers), "--no-spark"]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"     # 不许往团队仓写 .pyc
    env["PYTHONHASHSEED"] = "0"
    t0 = time.time()
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / ("%s.stdout.log" % run_id)).open("wb") as fo, \
            (log_dir / ("%s.stderr.log" % run_id)).open("wb") as fe:
        fo.write(("CMD(cwd=%s): %s\n" % (TEAM_PIPELINE, " ".join(cmd))).encode())
        fo.flush()
        p = subprocess.run(cmd, cwd=str(TEAM_PIPELINE), stdout=fo, stderr=fe, env=env)
    (log_dir / ("%s.cmd.json" % run_id)).write_text(json.dumps(
        {"cmd": cmd, "cwd": str(TEAM_PIPELINE), "rc": p.returncode,
         "elapsed_sec": round(time.time() - t0, 2),
         "env": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}}, indent=2) + "\n")
    return p.returncode, round(time.time() - t0, 2)


def read_db(run_dir: Path):
    db = run_dir / "pipeline.db"
    if not db.exists():
        return None
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    cur = con.cursor()

    def q(sql, args=()):
        try:
            return cur.execute(sql, args).fetchall()
        except Exception:
            return []
    out = {
        "db_path": str(db), "db_bytes": db.stat().st_size,
        "runs": q("select run_id,batch_id,status,episodes_total,input_dir,output_dir from runs"),
        "episode_status": {r[0]: r[1] for r in q("select status,count(*) from episodes group by status")},
        "n_episodes": (q("select count(*) from episodes") or [(0,)])[0][0],
        "n_events": (q("select count(*) from events") or [(0,)])[0][0],
        "badcase_by_rule": {r[0]: r[1] for r in q(
            "select rule,count(*) from events where event='badcase' and rule is not null "
            "group by rule order by 2 desc")},
        "stage_episode_done": {r[0]: r[1] for r in q(
            "select stage,count(*) from events where event='episode_done' group by stage")},
        "stage_done": {r[0]: r[1] for r in q(
            "select stage,count(*) from events where event='stage_done' group by stage")},
        "badcase_rules_by_episode": {r[0]: sorted(set((r[1] or "").split(","))) for r in q(
            "select episode_id,group_concat(distinct rule) from events "
            "where event='badcase' group by episode_id")},
        "invocations_by_rule": {r[0]: r[1] for r in q(
            "select rule,count(*) from events where rule is not null group by rule")},
        "badcase_messages": [{"rule": r[0], "episode": r[1], "message": (r[2] or "")[:220]}
                             for r in q("select rule,episode_id,message from events "
                                        "where event='badcase' limit 40")],
        "episode_badcase": {r[0]: r[1] for r in q(
            "select folder,badcase_json from episodes where badcase_json is not null "
            "and badcase_json not in ('','{}','null')")},
        # ---- 两张**比 events 更强**的表（B2 第二轮只读实测发现，第一版漏了）----
        # `rule_stats` 逐规则记 invocations / badcase_count / rule_version ⇒「规则被调用过」
        #   这件事**是**可直接读到的（第一版 Q4 的注释写"不能从 events 读到"，那句只对 events 成立）。
        # `events.detail_json` 在 clean 段的 episode_done 上带 `rejected_count` ⇒ 变更型算子
        #   （C01/C02/C03 只贡献 rejected_indices，正常路径**不写 badcase**）的敏感性有独立证据通道。
        "rule_stats": {r[0]: {"stage": r[1], "invocations": r[2], "badcase_count": r[3],
                              "avg_duration_ms": r[4], "rule_version": r[5]} for r in q(
            "select rule_id,stage,invocations,badcase_count,avg_duration_ms,rule_version "
            "from rule_stats")},
        "clean_rejected_by_episode": {r[0]: r[1] for r in q(
            "select episode_id, detail_json from events "
            "where event='episode_done' and stage='clean'")},
        # clean 段**不写** per-rule 的 badcase 事件（实测 `stages/clean.py:172-188`：
        # 它把 badcase 写进 episode 目录的 badcase.json，只在 episode_done 的 detail 里留
        # `badcase_keys`，并且 C03 的 warning 用的键是字面 `"0"`、C07 用 `"1"` ⇒ 键名不可读，
        # 归因只能靠 `rule_stats.badcase_count`）。这两个通道都要读，少读一个就会把
        # "clean 段的规则没有敏感性" 当成事实（第一版就是这么误判的）。
        "clean_episode_done_detail": {r[0]: _loads_or_none(r[1]) for r in q(
            "select episode_id, detail_json from events "
            "where event='episode_done' and stage='clean'")},
        "nonbadcase_events_by_rule": {r[0]: r[1] for r in q(
            "select rule,count(*) from events where rule is not null and event!='badcase' "
            "group by rule")},
    }
    # clean 段**逐条规则**的非 badcase 事件（实测 2026-09-29 19:5x 的 neg 集：
    # `C02:quaternion_problems` ×1、`C04:reencode_error` ×1）。这是 C02 唯一的敏感性通道
    # ——它是 AnnotationRule（「只标,不写盘」），既不写 badcase 也不贡献 rejected_indices，
    # 光看 badcase_by_rule 或 rejected_count 都会把它误判成"空转"。
    clean_ev = {}
    for eid, rule, name, dj in q("select episode_id,rule,event,detail_json from events "
                                 "where stage='clean' and rule is not null"):
        clean_ev.setdefault(eid, {}).setdefault(rule, []).append(
            {"event": name, "detail": _loads_or_none(dj)})
    out["clean_rule_events_by_episode"] = clean_ev
    con.close()
    return out


# 变更型（clean 段）算子的两类副作用通道（事实源：`rules/clean/c01_static_frames.py` 等文件的
# 类文档字符串——「MutationRule: 贡献 rejected_indices；读取失败时可产生 badcase」，
# 以及 `stages/clean.py:114-142`：rejected_indices 聚合进 ctx.shared、C03 的 warning 才升 badcase）
CLEAN_REJECTED_RULES = {"C01", "C02", "C03"}     # 贡献 rejected_indices
CLEAN_EFFECT_RULES = {"C05", "C06"}              # 消费 rejected_indices：切 JSON 帧 / 重映射 subtask


def meta_shape(path: Path):
    """读一条 episode 的 metadata，抽出**会被 clean 段改写**的几个量（用来判"流水线真的动了数据"）。

    只取形状不取内容：帧数、subtask 段数与 range、以及各时间序列的长度是否一致。
    读不出来就返回 None（不猜、不补默认值）。
    """
    try:
        d = json.loads(Path(path).read_text())
    except Exception:
        return None
    if not isinstance(d, dict):
        return None

    def _n(key_path):
        cur = d
        for part in key_path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return len(cur) if isinstance(cur, list) else None

    sub = d.get("subtask")
    ranges = None
    if isinstance(sub, list):
        ranges = [[(x.get("range") or [None, None])[0], (x.get("range") or [None, None])[-1]]
                  if isinstance(x, dict) else None for x in sub]
    return {"bytes": Path(path).stat().st_size,
            "n_is_move": _n("is_move"),
            "n_action_left_joint": _n("action.left_arm.joint"),
            "n_state_left_joint": _n("state.left_arm.joint"),
            "n_subtask": (len(sub) if isinstance(sub, list) else None),
            "subtask_ranges": ranges,
            "frame_validity_is_valid_sum": (
                sum(1 for x in (d.get("frame_validity") or {}).get("is_valid", []) if x)
                if isinstance(d.get("frame_validity"), dict) else None)}


def enabled_rules(cfg_path: Path):
    import yaml
    c = yaml.safe_load(Path(cfg_path).read_text())
    out = {}
    for stage, rules in (c.get("rules") or {}).items():
        out[stage] = sorted(k for k, v in (rules or {}).items() if (v or {}).get("enabled"))
    return out


# ---------------------------------------------------------------------------
# Q6 / Q7 的判据（抽成**纯函数**：闸与牙调用同一份 ⇒ 被测对象与使用对象是同一个，
# ADR-C-014 同型的坑不再踩。牙见 `--selftest-q6q7`。）
# ---------------------------------------------------------------------------
# **为什么在 2026-09-30 03:2x 改（formal-40 首跑团队 QC 当场暴露两条假红）**：
# 旧 Q6 用 `any("B_to_A" in k for k in n_per_direction)` 认反向 —— 那是 **0929 形态夹具**
# 的词表（`A_to_B` / `B_to_A`）。formal 的团队形态用的是 A2 契约的任务名，而且 manifest
# **自己声明了** `forward_direction_label="right_to_left"` / `reverse_direction_label="left_to_right"`，
# `n_per_direction = {right_to_left: 20, left_to_right: 20}`、`directions_balanced=true`
# ⇒ 一个 20/20 的真双向集被判成「没有反向（B_to_A）条数 —— 全项目最硬的数据缺口」。
# 这是**假红里最坏的一种**：文案恰好是全项目最敏感的那句话，足以让人反过来怀疑数据本身。
# 根因不在数据，在判据把**一份夹具的词表**当成了通用口径。
# 旧 Q7 要求任何 episode 的 `data_kind` 都含 `not_demonstration` / `negative_control`
# ⇒ 等于**禁止任何数据集自称示范**。对 0929 夹具这是对的（它必须声明自己不是示范），
# 但 formal **就是**示范数据（用途 = BC 的 stats 源，裁定 85.3 RR-B2-13）；它的诚实义务是
# 另一条：**不得声称能力**（D→B2 §5 / 裁定 46：没跑过 policy 就不许声称能力）。
# ⇒ 判据按**数据集角色**分岔：夹具走「不得自称示范」，示范集走「必须带能力免责声明三件，
#    且 data_kind 不得自称 policy/teleop/human/learned/rollout」。**两条都仍然可红**（牙 9 条）。
REVERSE_LABEL_FALLBACKS = ("B_to_A", "reverse")
CAPABILITY_DISCLAIMER_REQUIRED = {"not_a_capability_claim": True, "capability_claim": False,
                                  "policy_executed": False}
CAPABILITY_SELFCLAIM_TOKENS = ("policy", "teleop", "human", "learned", "rollout")
FIXTURE_TOKENS = ("not_demonstration", "form_fixture", "fixture", "synthesized_analytic",
                  "negative_control")


def _status_from(bad, unjudged):
    if bad:
        return STATUS_RED
    if unjudged:
        return STATUS_UNJUDGED
    return STATUS_PASS


def _direction_labels(man: dict) -> dict:
    """认「哪个标签是反向」：**优先用数据集自己的声明**，认不出才退回夹具词表（退回必须登记）。"""
    per = man.get("n_per_direction") or {}
    fwd, rev = man.get("forward_direction_label"), man.get("reverse_direction_label")
    if rev:
        return {"route": "manifest_declared_labels", "forward": fwd, "reverse": rev,
                "reverse_present_in_counts": rev in per,
                "note": "用数据集自己声明的方向标签（不硬编码任何一份夹具的词表）"}
    for tok in REVERSE_LABEL_FALLBACKS:
        hit = next((k for k in per if tok.lower() in str(k).lower()), None)
        if hit:
            return {"route": "legacy_fixture_vocabulary_fallback", "matched_token": tok,
                    "forward": None, "reverse": hit, "reverse_present_in_counts": True,
                    "note": "manifest 没有 `reverse_direction_label` ⇒ 退回 0929 夹具词表 "
                            "`%s`；**退回路线已登记，不静默**" % tok}
    return {"route": "unrecognized", "forward": fwd, "reverse": None,
            "reverse_present_in_counts": False,
            "note": "两条路线都认不出反向标签 ⇒ 弃权（不猜）"}


def judge_directions(man: dict) -> dict:
    """Q6：两方向条数相等、反向不得为 0。**均衡由机器复算，不采信交件的 `directions_balanced`。**"""
    per = man.get("n_per_direction") or {}
    claimed = man.get("directions_balanced")
    lab = _direction_labels(man)
    vals = [v for v in per.values() if isinstance(v, int)]
    recomputed = (None if not per else
                  (len(per) >= 2 and len(vals) == len(per) and min(vals) == max(vals)
                   and min(vals) > 0))
    n_rev = per.get(lab["reverse"]) if lab["reverse"] else None
    bad, unj = [], []
    if not per:
        unj.append("`n_per_direction` 缺失/为空 ⇒ 均衡无从复算（三值纪律：弃权，不当作通过）")
    elif lab["route"] == "unrecognized":
        unj.append("认不出哪个标签是反向（manifest 没有 `reverse_direction_label`，退回词表 %s "
                   "也都没命中；实到标签 = %s）⇒「反向是否为 0」**无法判**，弃权。**不猜**："
                   "猜错会把真双向集判成缺口，也会把真缺口判成合规"
                   % (list(REVERSE_LABEL_FALLBACKS), sorted(str(k) for k in per)))
    else:
        if not n_rev:
            bad.append("**反向（`%s`）条数 = %r** —— 那是全项目最硬的数据缺口"
                       "（反向为 0 时任何「双向」声明都不成立）" % (lab["reverse"], n_rev))
        if recomputed is False:
            bad.append("两方向条数不相当：`n_per_direction` 实测 %s（**机器复算**，不采信交件自述）"
                       % per)
        if claimed is not None and bool(claimed) != bool(recomputed):
            bad.append("交件自述 `directions_balanced=%r` 与按 `n_per_direction=%s` 的机器复算 `%r` "
                       "**不符** ⇒ 自述与事实不一致（不采信自述；裁定 34.1 同型）"
                       % (claimed, per, recomputed))
    return {"violations": bad, "unjudged": unj, "status": _status_from(bad, unj),
            "observed": {"n_per_direction": per, "direction_labels": lab,
                         "directions_balanced_claimed": claimed,
                         "directions_balanced_recomputed": recomputed, "n_reverse": n_rev,
                         "recomputed_not_trusting_self_claim": True}}


def judge_data_kind(man: dict) -> dict:
    """Q7：按**数据集角色**分岔的诚实义务（夹具不得自称示范；示范集不得自称能力）。"""
    dk, mdk = man.get("dataset_kind"), man.get("data_kind")
    eps = man.get("episodes") or []
    kinds = sorted({str(e.get("data_kind")) for e in eps})
    blob = " ".join([str(dk), str(mdk or "")] + kinds).lower()
    is_fixture = any(t in blob for t in FIXTURE_TOKENS)
    bad, unj = [], []
    if not eps:
        unj.append("manifest 里没有 `episodes[]` ⇒ 逐条 `data_kind` 无从核（弃权，不当作通过）")
    else:
        missing = [i for i, e in enumerate(eps) if not e.get("data_kind")]
        if missing:
            bad.append("%d 条 episode 缺 `data_kind`（索引 %s…）⇒ 数据身份没盖戳"
                       % (len(missing), missing[:5]))
    if is_fixture:
        role = "form_fixture_must_not_claim_demonstration"
        if "demonstration" in blob and "not_demonstration" not in blob:
            bad.append("**形态夹具自称 demonstration**（`dataset_kind=%r` / `data_kind=%s`）⇒ "
                       "D→B2 §5：不得把「数据造出来了」写成「示范有了」" % (dk, kinds))
    else:
        role = "demonstration_must_not_claim_capability"
        for k, want in CAPABILITY_DISCLAIMER_REQUIRED.items():
            got = man.get(k, "__absent__")
            if got == "__absent__":
                bad.append("manifest 缺能力免责声明 `%s`（裁定 46：没跑过 policy 就不许声称能力；"
                           "缺字段 ⇒ 无从判断它声称了什么，不当作通过）" % k)
            elif bool(got) != want:
                bad.append("能力免责声明 `%s=%r`，要求 `%r`（裁定 46 / D→B2 §5）" % (k, got, want))
        if man.get("policy_executed") is False:
            where = " ".join([str(dk or ""), str(mdk or "")] + kinds).lower()
            hits = [t for t in CAPABILITY_SELFCLAIM_TOKENS if t in where]
            if hits:
                bad.append("`policy_executed=false` 但 `dataset_kind`/`data_kind` 里出现能力自称词 "
                           "%s（`%r` / %s）⇒ **自称与事实不符**（D→B2 §5）" % (hits, dk, kinds))
    return {"violations": bad, "unjudged": unj, "status": _status_from(bad, unj),
            "observed": {"dataset_kind": dk, "manifest_data_kind": mdk,
                         "episode_data_kinds": kinds, "role": role, "is_fixture": is_fixture,
                         "capability_disclaimer": {k: man.get(k, "__absent__")
                                                   for k in CAPABILITY_DISCLAIMER_REQUIRED}}}


Q6Q7_TEETH = [
    # (id, manifest, 期望 Q6 status, 期望 Q7 status, 说明)
    ("T1_formal_shape_must_not_be_false_red",
     {"dataset_kind": "sim_demonstration_bidirectional",
      "data_kind": "sim_demonstration_scripted_expert",
      "n_per_direction": {"right_to_left": 20, "left_to_right": 20},
      "forward_direction_label": "right_to_left", "reverse_direction_label": "left_to_right",
      "directions_balanced": True, "not_a_capability_claim": True,
      "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "sim_demonstration_scripted_expert"} for _ in range(40)]},
     "PASS", "PASS",
     "**反向牙（不许假红）**：formal-40 的真实形态 —— 自带方向标签声明、20/20 均衡、"
     "是真示范集且带齐三件能力免责声明 ⇒ Q6/Q7 都必须绿。旧判据在这里判了两条假红"),
    ("T2_reverse_zero_must_red",
     {"dataset_kind": "sim_demonstration_bidirectional",
      "data_kind": "sim_demonstration_scripted_expert",
      "n_per_direction": {"right_to_left": 40, "left_to_right": 0},
      "reverse_direction_label": "left_to_right", "directions_balanced": False,
      "not_a_capability_claim": True, "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "sim_demonstration_scripted_expert"}]},
     "RED", "PASS", "**正向牙**：反向为 0（全项目最硬的数据缺口）⇒ Q6 必须红"),
    ("T3_unbalanced_20_19_must_red",
     {"dataset_kind": "sim_demonstration_bidirectional",
      "data_kind": "sim_demonstration_scripted_expert",
      "n_per_direction": {"right_to_left": 20, "left_to_right": 19},
      "reverse_direction_label": "left_to_right", "directions_balanced": False,
      "not_a_capability_claim": True, "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "sim_demonstration_scripted_expert"}]},
     "RED", "PASS", "**正向牙**：20/19 不相当 ⇒ Q6 必须红"),
    ("T4_unrecognized_reverse_label_must_unjudged",
     {"dataset_kind": "sim_demonstration_bidirectional",
      "data_kind": "sim_demonstration_scripted_expert",
      "n_per_direction": {"pick": 20, "place": 20}, "directions_balanced": True,
      "not_a_capability_claim": True, "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "sim_demonstration_scripted_expert"}]},
     "UNJUDGED", "PASS",
     "**三值牙**：标签既不是声明的反向、也不含退回词表 ⇒ **弃权**（不猜成红、也不猜成绿）"),
    ("T5_self_claim_disagrees_must_red",
     {"dataset_kind": "sim_demonstration_bidirectional",
      "data_kind": "sim_demonstration_scripted_expert",
      "n_per_direction": {"right_to_left": 20, "left_to_right": 19},
      "reverse_direction_label": "left_to_right", "directions_balanced": True,
      "not_a_capability_claim": True, "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "sim_demonstration_scripted_expert"}]},
     "RED", "PASS",
     "**正向牙**：交件自称 `directions_balanced=true` 而实测 20/19 ⇒ 必须红且点名「自述与事实不一致」"),
    ("T6_demo_missing_disclaimer_must_red",
     {"dataset_kind": "sim_demonstration_bidirectional",
      "data_kind": "sim_demonstration_scripted_expert",
      "n_per_direction": {"right_to_left": 20, "left_to_right": 20},
      "reverse_direction_label": "left_to_right", "directions_balanced": True,
      "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "sim_demonstration_scripted_expert"}]},
     "PASS", "RED", "**正向牙**：示范集缺 `not_a_capability_claim` ⇒ Q7 必须红（裁定 46）"),
    ("T7_demo_claims_policy_must_red",
     {"dataset_kind": "sim_policy_rollout", "data_kind": "policy_rollout_demonstration",
      "n_per_direction": {"right_to_left": 20, "left_to_right": 20},
      "reverse_direction_label": "left_to_right", "directions_balanced": True,
      "not_a_capability_claim": True, "capability_claim": False, "policy_executed": False,
      "episodes": [{"data_kind": "policy_rollout_demonstration"}]},
     "PASS", "RED",
     "**正向牙**：`policy_executed=false` 却自称 `policy_rollout` ⇒ Q7 必须红"
     "（D→B2 §5：不得把「数据造出来了」写成「能力有了」）"),
    ("T8_fixture_claims_demonstration_must_red",
     {"dataset_kind": "form_fixture_demonstration",
      "n_per_direction": {"A_to_B": 4, "B_to_A": 4}, "directions_balanced": True,
      "episodes": [{"data_kind": "form_fixture_demonstration"}]},
     "PASS", "RED",
     "**旧判据保留牙**：形态夹具自称 demonstration ⇒ Q7 仍必须红（改判没有把这条放掉）"),
    ("T9_legacy_fixture_vocab_must_stay_green",
     {"dataset_kind": "form_fixture_not_demonstration",
      "n_per_direction": {"A_to_B": 4, "B_to_A": 4}, "directions_balanced": True,
      "episodes": [{"data_kind": "form_fixture_not_demonstration"}]},
     "PASS", "PASS",
     "**反向牙**：0929 夹具/负对照那套词表（`A_to_B`/`B_to_A`、`not_demonstration`）"
     "走退回路线仍必须绿 ⇒ 改判没有把旧世界的合规件判成红"),
]


def selftest_q6q7(out_dir: Path) -> tuple[dict, int]:
    """Q6/Q7 改判的牙（9 条：4 正向红 + 1 三值弃权 + 4 反向绿）。CPU-only、不调团队流水线。"""
    rows, n_ok = [], 0
    for tid, man, want6, want7, desc in Q6Q7_TEETH:
        j6, j7 = judge_directions(man), judge_data_kind(man)
        ok = (j6["status"] == want6 and j7["status"] == want7)
        n_ok += int(ok)
        rows.append({"id": tid, "desc": desc, "want": {"Q6": want6, "Q7": want7},
                     "got": {"Q6": j6["status"], "Q7": j7["status"]},
                     "Q6_violations": j6["violations"], "Q6_unjudged": j6["unjudged"],
                     "Q7_violations": j7["violations"], "Q7_unjudged": j7["unjudged"],
                     "Q6_observed": j6["observed"], "Q7_observed": j7["observed"], "ok": ok})
        print("%-42s Q6 %-9s(期望 %-9s) Q7 %-9s(期望 %-9s) ⇒ %s"
              % (tid, j6["status"], want6, j7["status"], want7,
                 "抓住" if ok else "**没抓住（牙失效/假红）**"))
    doc = {"spec": "Q6/Q7 改判的牙（旧判据把 0929 夹具的词表当通用口径 ⇒ formal-40 上两条假红）",
           "verdict_kind": "b2_qc_q6q7_teeth",
           "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "generated_by": "scripts/b2_run_team_qc.py --selftest-q6q7",
           "gate_build": (_sha256(Path(__file__)) or "")[:12],
           "root_cause": {"Q6": 'any("B_to_A" in k for k in n_per_direction) —— 硬编码 0929 夹具词表',
                          "Q7": '要求任何 data_kind 都含 not_demonstration/negative_control '
                                '—— 等于禁止任何数据集自称示范'},
           "false_reds_caught_on": "runs/vla/b2_sim_demo_bidir_20260930/qc_team_formal40/qc_verdict.json"
                                   "（首跑：Q6/Q7 各一条假红，n_per_direction 实为 20/20）",
           "n_teeth": len(rows), "n_ok": n_ok, "all_ok": n_ok == len(rows),
           "teeth": rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "qc_q6q7_teeth.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("-" * 96)
    print("Q6/Q7 牙：%d/%d 条符合预期 → %s" % (n_ok, len(rows), p))
    return doc, (0 if n_ok == len(rows) else 3)


def main():
    ap = argparse.ArgumentParser(description="B2：只读调用团队 vla_pipeline 并判成可红可绿的判词")
    ap.add_argument("--root", default=str(ROOT_DEFAULT))
    ap.add_argument("--config", default=None)
    ap.add_argument("--clean-input", default=None, help="干净数据集（期望 0 badcase）")
    ap.add_argument("--neg-input", default=None, help="负对照数据集（期望被抓）")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--batch-id", default="b2_form_fixture_001")
    ap.add_argument("--py", default="/opt/conda/bin/python3",
                    help="团队流水线的运行时（实测 base python3 有 av 17.1.0 + click 8.4.2）")
    ap.add_argument("--max-workers", type=int, default=4,
                    help="CPU 配额只有 12 核（cgroup cpu.max），不要按 nproc=112 开")
    ap.add_argument("--team-repo", default=str(TEAM_PIPELINE))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest-q6q7", action="store_true",
                    help="只跑 Q6/Q7 改判的 9 条牙（CPU-only、不调团队流水线）；"
                         "牙没咬 / 该绿的没绿 ⇒ rc=3")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    if a.selftest_q6q7:
        od = Path(a.out_dir) if a.out_dir else (
            root / "runs/vla/b2_sim_demo_bidir_20260930/qc_team_formal40")
        if not od.is_absolute():
            od = root / od
        return selftest_q6q7(od)[1]
    cfg = Path(a.config) if a.config else (root / CONFIG_DEFAULT)
    if not cfg.is_absolute():
        cfg = root / cfg
    base_out = Path(a.out_dir) if a.out_dir else (
        root / "runs/vla/b2_bidir_demo_form_20260929/qc_b2")
    if not base_out.is_absolute():
        base_out = root / base_out
    base_out.mkdir(parents=True, exist_ok=True)
    team = Path(a.team_repo)

    rep = Report()
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    results = {}

    # ---- 团队仓只读快照（跑前）----
    before = snapshot_tree(team)
    (base_out / "team_repo_snapshot_before.json").write_text(json.dumps(
        {"n_files": len(before), "excluded_dirs": sorted(SNAPSHOT_EXCLUDE_DIRS),
         "files": {k: {"sha256": v[0], "bytes": v[1], "mtime_ns": v[2]}
                   for k, v in before.items()}}, indent=1) + "\n")

    # ---- Q0 写入面守卫（在**跑之前**判，因为跑一次就已经写坏了）----
    guard_bad, guard_rows = [], []
    staged_inputs = {}
    for tag, inp in (("clean", a.clean_input), ("neg", a.neg_input)):
        if not inp:
            continue
        d = Path(inp)
        d = d if d.is_absolute() else (root / d)
        sd = str(d)
        forbidden = [w for w in FORBIDDEN_INPUT_SUBSTR if w in sd]
        allowed = (sd.startswith(str(root / "runs/vla/b2_")) or sd.startswith("/tmp/b2_"))
        guard_rows.append({"set": tag, "input_dir": sd, "exists": d.exists(),
                           "forbidden_substr_hit": forbidden, "in_b2_write_area": allowed})
        if forbidden:
            guard_bad.append("%s：输入目录 %s 命中禁止子串 %s ⇒ 团队流水线会**就地改写输入**，"
                             "跑一次就动了别人的数据（D→B2 §0.2/§0.3）" % (tag, sd, forbidden))
        elif not allowed:
            guard_bad.append("%s：输入目录 %s 不在 B2 写入面（runs/vla/b2_* 或 /tmp/b2_*）内 "
                             "⇒ 拒绝把它交给会写盘的团队流水线" % (tag, sd))
        elif not d.exists():
            guard_bad.append("%s：输入目录不存在 %s" % (tag, sd))
    rep.add("Q0_input_write_area_guard", (not guard_bad and bool(guard_rows)),
            {"per_set": guard_rows, "forbidden_substr": list(FORBIDDEN_INPUT_SUBSTR),
             "allowed_prefixes": [str(root / "runs/vla/b2_"), "/tmp/b2_"],
             "violations": guard_bad},
            "两份输入都必须存在、落在 B2 自己的写入面内、且不命中任何禁止子串",
            note=("事实源：2026-09-29 18:07 实测——团队流水线的 clean/qc 段会**就地写回输入目录**"
                  "（重写 converted_metadata_normal.json、写 badcase.json、改文件模式为 0600）。"
                  "所以「只读使用团队资产」必须落到输入面上：绝不可拿 workplace/ABC130k 或 "
                  "yfw_input 当输入。本脚本另外把输入**复制一份**到 qc_input/ 再跑，"
                  "pristine 生成集由 Q8 逐字节核。"),
            ruling_ref="D→B2 §0.2（只读使用 + 只在自己输出目录写）/ §0.3（不碰 datasets）",
            red_when="输入命中禁止子串 / 不在 B2 写入面 / 目录不存在")
    if guard_bad:
        guard_rows = None

    for tag, inp in (("clean", a.clean_input), ("neg", a.neg_input)):
        if not inp or guard_rows is None:
            continue
        pristine = Path(inp)
        if not pristine.is_absolute():
            pristine = root / pristine
        # 复制一份再跑：pristine 生成集必须逐字节不变（Q8 核），被流水线改写的是这份副本
        input_dir = base_out / "qc_input" / ("%s_%s" % (tag, stamp))
        shutil.copytree(pristine, input_dir)
        run_id = "b2_%s_%s" % (tag, stamp)
        output_root = base_out / tag
        staged_inputs[tag] = {"pristine": str(pristine), "staged": str(input_dir),
                              "pristine_before": snapshot_tree(pristine),
                              "staged_before": snapshot_tree(input_dir)}
        # clean 段会**就地改写** metadata ⇒ 必须在跑之前把形状读下来，事后就没得读了
        staged_inputs[tag]["meta_before"] = {
            str(p.relative_to(input_dir)): meta_shape(p)
            for p in sorted(input_dir.rglob(METADATA_NAME))}
        rc, elapsed = run_pipeline(cfg, input_dir, output_root, run_id, a.batch_id, a.py,
                                   a.max_workers, base_out / "logs")
        db = read_db(output_root / run_id)
        eps = count_episodes(input_dir)
        staged_inputs[tag]["pristine_after"] = snapshot_tree(pristine)
        staged_inputs[tag]["staged_after"] = snapshot_tree(input_dir)
        staged_inputs[tag]["meta_after"] = {
            str(p.relative_to(input_dir)): meta_shape(p)
            for p in sorted(input_dir.rglob(METADATA_NAME))}
        results[tag] = {"input_dir": str(input_dir), "pristine_dir": str(pristine),
                        "run_id": run_id, "rc": rc,
                        "elapsed_sec": elapsed, "n_input_episodes": len(eps),
                        "run_dir": str(output_root / run_id), "db": db,
                        "report_md": str(output_root / run_id / "report.md")}
        if not a.quiet:
            print("[%s] rc=%s 用时 %.1fs 输入条数=%d" % (tag, rc, elapsed, len(eps)))
            if db:
                print("      episodes=%s status=%s badcase_by_rule=%s"
                      % (db["n_episodes"], db["episode_status"], db["badcase_by_rule"]))

    # ---- 团队仓只读快照（跑后）----
    after = snapshot_tree(team)
    d = diff_snapshot(before, after)
    (base_out / "team_repo_snapshot_after.json").write_text(json.dumps(
        {"n_files": len(after), "diff": d}, indent=1) + "\n")
    ok1 = (d["n_changed"] == 0 and d["n_added"] == 0 and d["n_removed"] == 0)
    rep.add("Q1_team_repo_readonly", bool(ok1),
            {"n_files_before": len(before), "n_files_after": len(after),
             "excluded_dirs": sorted(SNAPSHOT_EXCLUDE_DIRS), **d},
            "团队仓 %s 全量 sha256+mtime 快照跑前跑后**逐文件相同**（0 改 / 0 增 / 0 删）" % team,
            note="PYTHONDONTWRITEBYTECODE=1；`__pycache__`/`.pytest_cache`/`.git` 已显式排除并在此列出",
            ruling_ref="D→B2 §0.2（只读使用 + 只在自己的输出目录写）",
            red_when="任一文件字节变了 / 新增 / 消失")

    rules = enabled_rules(cfg)
    all_enabled = sorted({k for v in rules.values() for k in v})

    # ---- Q2 跑完 ----
    bad2 = []
    for tag, r in results.items():
        db = r["db"] or {}
        runs = db.get("runs") or []
        st = runs[0][2] if runs else None
        if r["rc"] != 0:
            bad2.append("%s：CLI rc=%s" % (tag, r["rc"]))
        if st not in ("completed", "done", "finished", None) and st != "completed":
            if st is not None and st != "completed":
                bad2.append("%s：run 状态=%r（不是 completed）" % (tag, st))
        if db and db.get("n_episodes") != r["n_input_episodes"]:
            bad2.append("%s：处理条数 %s != 输入条数 %d（半跑不算过）"
                        % (tag, db.get("n_episodes"), r["n_input_episodes"]))
    if not results:
        rep.add("Q2_pipeline_completed", None, "没有给任何 --*-input", "至少跑一份数据集",
                note="证据不足 ⇒ 弃权", ruling_ref="D→B2 §2.2-2", red_when="rc!=0 / 状态非 completed / 条数不符")
    else:
        rep.add("Q2_pipeline_completed", not bad2,
                {"violations": bad2, "per_set": {t: {"rc": r["rc"], "elapsed_sec": r["elapsed_sec"],
                                                     "n_input_episodes": r["n_input_episodes"],
                                                     "n_db_episodes": (r["db"] or {}).get("n_episodes"),
                                                     "run_status": ((r["db"] or {}).get("runs") or [[None]])[0][2]}
                                                  for t, r in results.items()}},
                "每份数据集：rc==0、run 状态 completed、处理条数 == 输入条数",
                ruling_ref="D→B2 §2.2-2（validate → clean → qc 跑一遍）",
                red_when="rc!=0 / 状态非 completed / 条数不符")

    # ---- Q3 干净集 0 badcase ----
    if "clean" in results:
        db = results["clean"]["db"] or {}
        bc = db.get("badcase_by_rule") or {}
        n_bc = sum(bc.values())
        rep.add("Q3_clean_set_zero_badcase", n_bc == 0,
                {"n_badcase_events": n_bc, "badcase_by_rule": bc,
                 "episode_status": db.get("episode_status"),
                 "sample_messages": (db.get("badcase_messages") or [])[:8]},
                "干净数据集在**不放宽任何阈值**的前提下 0 badcase",
                note="阈值全部逐字沿用团队 default.yaml（放宽阈值换来的绿不算绿）",
                ruling_ref="D→B2 §2.2-2 + §5（不得把 QC 全过当成数据语义正确）",
                red_when="出现任一 badcase")
    else:
        rep.add("Q3_clean_set_zero_badcase", None, "未提供 --clean-input", "干净集必须跑",
                ruling_ref="D→B2 §2.2-2", red_when="出现任一 badcase")

    # ---- Q4 非空洞（**两轴**：调用覆盖 / 敏感性覆盖）----
    # 第一版把两件事混成一个 `coverage_proven`，还用 badcase 事件当"规则被调用过"的证据，
    # 结论是 13 条规则永远"未证明" ⇒ **恒 WARN**；而恒定出现的 WARN 等于没有 WARN（裁定 27.1 同型）。
    # 只读实测团队 pipeline.db 之后找到两处**更强的事实源**（第一版漏读）：
    #   · `rule_stats` 表：逐规则 invocations / badcase_count / rule_version
    #     ⇒「算子真的被调用过」是可直接读到的硬证据，不必靠 badcase 反推；
    #   · clean 段 `episode_done` 的 `detail_json.rejected_count`
    #     ⇒ C01/C02/C03 是**变更型**算子（只贡献 rejected_indices，正常路径**不写 badcase**），
    #       它们的敏感性有独立通道。
    # 于是拆两轴，各自有牙：
    #   Q4a 调用覆盖：任一 enabled 规则 invocations==0（或 rule_stats 里没有它）⇒ **RED**
    #       （此时"0 badcase"是空洞真；B 的 V6 纪律：空比对的 0 处变化要单独红）。
    #       invocations < 输入条数是**允许的**（上游 badcase 会短路下游算子），但逐条点名不静默。
    #   Q4b 敏感性覆盖：逐规则给"它在本批数据上**能不能**判红"的证据通道；拿不到 ⇒ WARN 并逐条列出，
    #       **不得**读成"已验过"。变更型算子的归因靠"单缺陷 episode"的构造成立（db 里的
    #       rejected_count 是聚合值，不区分是哪条 C 规则贡献的 —— 这一点在产物里写明，不假装更精确）。
    stages_required = sorted(rules.keys())
    bad4, warn4 = [], []
    stage_cov, inv_cov = {}, {}
    fired_badcase, rejected_eps, clean_effect = set(), {}, {}
    rule_event_only = set()
    for tag, r in results.items():
        db = r["db"] or {}
        sed = db.get("stage_episode_done") or {}
        stage_cov[tag] = {"required_stages": stages_required, "episode_done_by_stage": sed,
                          "n_input_episodes": r["n_input_episodes"]}
        for st in stages_required:
            if sed.get(st, 0) != r["n_input_episodes"]:
                bad4.append("%s：stage `%s` 的 episode_done=%s != 输入条数 %d（该段没对每条跑）"
                            % (tag, st, sed.get(st, 0), r["n_input_episodes"]))
        for rule, rs in (db.get("rule_stats") or {}).items():
            slot = inv_cov.setdefault(rule, {"stage": rs.get("stage"),
                                             "rule_version": rs.get("rule_version"),
                                             "per_set": {}})
            slot["per_set"][tag] = {"invocations": rs.get("invocations"),
                                    "badcase_count": rs.get("badcase_count"),
                                    "n_input_episodes": r["n_input_episodes"]}
            if rs.get("badcase_count"):
                # `rule_stats.badcase_count` 是**唯一**能归因到 clean 段单条规则的通道
                fired_badcase.add(rule)
        for rule in (db.get("nonbadcase_events_by_rule") or {}):
            rule_event_only.add(rule)
        # clean 段的 rejected_count（逐 episode）⇒ 变更型算子的敏感性通道
        rj = {}
        for ep, dj in (db.get("clean_rejected_by_episode") or {}).items():
            try:
                rj[ep] = (json.loads(dj) or {}).get("rejected_count")
            except Exception:
                rj[ep] = None
        rejected_eps[tag] = rj
        # clean 段对输入的**实际改写**（Q8 的快照差）⇒ C05/C06 的敏感性通道
        si = staged_inputs.get(tag) or {}
        mb_all, ma_all = si.get("meta_before") or {}, si.get("meta_after") or {}
        eff = []
        for rel in sorted(set(mb_all) & set(ma_all)):
            mb, ma = mb_all[rel], ma_all[rel]
            if mb and ma and mb != ma:
                diff = {k: {"before": mb.get(k), "after": ma.get(k)}
                        for k in sorted(set(mb) | set(ma)) if mb.get(k) != ma.get(k)}
                eff.append({"episode_file": rel, "changed_fields": diff})
        clean_effect[tag] = eff

    enabled = set(all_enabled)
    # ---- Q4a 调用覆盖 ----
    never_invoked = sorted(k for k in enabled
                           if not any((v.get("invocations") or 0) > 0
                                      for v in (inv_cov.get(k) or {}).get("per_set", {}).values()))
    partial = []
    for k in sorted(enabled & set(inv_cov)):
        for tag, v in inv_cov[k]["per_set"].items():
            n_inv, n_in = (v.get("invocations") or 0), v.get("n_input_episodes")
            if 0 < n_inv < (n_in or 0):
                partial.append("%s/%s: invocations=%s < 输入 %s（上游 badcase 短路了下游算子）"
                               % (tag, k, n_inv, n_in))
    unexpected_rows = sorted(set(inv_cov) - enabled)
    if never_invoked:
        bad4.append("**%d 条 enabled 规则 invocations==0**（或 rule_stats 里没有它）：%s ⇒ "
                    "此时的「0 badcase」是空洞真，不得采信"
                    % (len(never_invoked), ",".join(never_invoked)))
    if unexpected_rows:
        warn4.append("rule_stats 里有 %d 条规则不在 B2 config 的 enabled 集里：%s（只报观测，"
                     "可能是团队 CLI 的默认注入）" % (len(unexpected_rows), ",".join(unexpected_rows)))
    # ---- Q4b 敏感性覆盖 ----
    n_rejected_eps = sum(1 for rj in rejected_eps.values() for n in rj.values() if (n or 0) > 0)
    n_clean_effect = sum(len(v) for v in clean_effect.values())
    sens = {}
    for k in sorted(enabled):
        ch = []
        if k in fired_badcase:
            ch.append("rule_stats.badcase_count>0")
        if not ch and k in rule_event_only:
            ch.append("events 表里有 rule=%s 的非 badcase 事件（如 C02 的 quaternion_problems、"
                      "C04 的 reencode_error）" % k)
        if not ch and k in CLEAN_REJECTED_RULES and n_rejected_eps:
            ch.append("clean 段 rejected_count>0（%d 条 episode；归因靠单缺陷构造）" % n_rejected_eps)
        if not ch and k in CLEAN_EFFECT_RULES and n_clean_effect:
            ch.append("clean 段确实改写了输入的 metadata（%d 处；C05 切片 / C06 subtask 重映射）"
                      % n_clean_effect)
        sens[k] = ch
    sens_proven = sorted(k for k, v in sens.items() if v)
    sens_unproven = sorted(k for k, v in sens.items() if not v)
    if sens_unproven:
        warn4.append("%d 条 enabled 规则的**敏感性未被证明**（本批数据里没有能让它们判红的证据通道）：%s"
                     " ⇒ 不得读成「已验过」。结构性原因：%s"
                     % (len(sens_unproven), ",".join(sens_unproven),
                        "它们是变更型算子的下游消费者，正常路径不写 badcase，而 db 里的 "
                        "rejected_count 是聚合值、无法归因到单条规则"))
    if not sens_proven:
        bad4.append("所有数据集里**没有任何一条** enabled 规则被证明有敏感性 ⇒ 无法排除「算子整体空转」")

    obs4 = {"stage_coverage": stage_cov, "n_enabled_rules": len(enabled),
            "invocation_coverage": {"n_invoked": len(enabled) - len(never_invoked),
                                    "n_enabled": len(enabled),
                                    "never_invoked": never_invoked,
                                    "partial_invocation": partial,
                                    "rule_stats_rows_not_enabled": unexpected_rows,
                                    "per_rule": inv_cov},
            "sensitivity_coverage": {"n_proven": len(sens_proven), "proven": sens_proven,
                                     "n_unproven": len(sens_unproven), "unproven": sens_unproven,
                                     "channels": sens,
                                     "n_episodes_with_rejected": n_rejected_eps,
                                     "n_metadata_rewritten": n_clean_effect,
                                     "clean_effect_sample": {t: v[:3] for t, v in clean_effect.items()},
                                     "attribution_caveat": (
                                         "clean 段的 rejected_count 是 C01/C02/C03 的**聚合**值，"
                                         "db 不区分是哪条贡献的 ⇒ 归因靠「一条 episode 只注入一个缺陷」"
                                         "的构造成立，不是从 db 读出来的。这一点不假装更精确。")},
            "violations": bad4}
    st4 = STATUS_RED if bad4 else (STATUS_WARN if warn4 else STATUS_PASS)
    rep.add("Q4_rule_coverage_nonvacuous", not bad4, obs4,
            ("Q4a：三个 stage 对每条 episode 都有 `episode_done`，且**每条** enabled 规则在 "
             "`rule_stats` 里 invocations>0；Q4b：每条 enabled 规则都有一条可指名的**敏感性证据通道**"
             "（badcase_count>0 / rejected_count>0 / metadata 被改写）"),
            note=("；".join(warn4) if warn4 else
                  "调用覆盖 %d/%d、敏感性覆盖 %d/%d 全部有证据通道"
                  % (len(enabled) - len(never_invoked), len(enabled),
                     len(sens_proven), len(enabled))),
            status=st4,
            ruling_ref="裁定 27.1（恒真/恒假的闸等于没有闸）/ B 的 V6「空洞真单列一条红」纪律",
            red_when=("任一 stage 的 episode_done != 输入条数；任一 enabled 规则 invocations==0；"
                      "或没有任何规则被证明有敏感性"))

    # ---- Q5 负对照被抓 ----
    if "neg" in results:
        db = results["neg"]["db"] or {}
        bc = db.get("badcase_by_rule") or {}
        by_ep = db.get("badcase_rules_by_episode") or {}
        man = {}
        mp = Path(results["neg"]["input_dir"]) / "dataset_manifest.json"
        if mp.exists():
            try:
                man = json.loads(mp.read_text())
            except Exception:
                man = {}
        # ---- 两个路径口径必须接起来（19:5x 实测踩到的坑）----
        # db 的 `episode_id` 是**暂存副本**的绝对路径（`.../qc_input/neg_<ts>/train/<task>/episode_<uuid>`），
        # 而 dataset_manifest.json 里记的是 **pristine 生成集**的路径。第一版直接拿 manifest 的
        # path 去查 db ⇒ 22 条**一条都查不到** ⇒ Q5 恒红（22/22 primary "未触发"），
        # 而实际上 primary 全都触发了。恒红的判据比没有判据更糟：它会训练读判词的人忽略红点。
        pristine_dir = Path(results["neg"].get("pristine_dir") or results["neg"]["input_dir"])
        staged_dir = Path(results["neg"]["input_dir"])
        clean_det = db.get("clean_episode_done_detail") or {}
        clean_ev = db.get("clean_rule_events_by_episode") or {}
        rstats = db.get("rule_stats") or {}

        def _lookup(mapping, epath):
            p = Path(epath or "")
            cands = [str(p)]
            try:
                cands.append(str(staged_dir / p.relative_to(pristine_dir)))
            except (ValueError, OSError):
                pass
            for c in cands:
                if c in mapping:
                    return mapping[c], c, "path"
            for k, v in mapping.items():            # basename 兜底（uuid 在本集内唯一）
                if Path(k).name == p.name:
                    return v, k, "basename"
            return None, None, "not_found"

        per_eps, missed, unexplained = [], [], []
        for e in (man.get("episodes") or []):
            nc = e.get("negative_control") or {}
            kind = nc.get("kind")
            spec = nc.get("expected_badcase_keys") or {}
            if isinstance(spec, list):            # 兼容旧形态（纯列表）
                spec = {"primary": spec, "also_observed": []}
            primary = spec.get("primary") or []
            also = spec.get("also_observed") or []
            notobs = spec.get("expected_but_not_observed") or []
            chan = spec.get("primary_channel") or "badcase"
            det_key = spec.get("primary_detail_key")
            fired_raw, fired_key, how = _lookup(by_ep, e.get("path"))
            fired_ep = fired_raw or []
            det_raw, det_key_ep, how_det = _lookup(clean_det, e.get("path"))
            ev_raw, ev_key, how_ev = _lookup(clean_ev, e.get("path"))
            det_raw = det_raw if isinstance(det_raw, dict) else (_loads_or_none(det_raw) or {})
            bck = det_raw.get("badcase_keys")
            evidence = {
                "channel": chan,
                # 匹配方式**按所用通道**记，不能用 badcase 表的匹配结果代表全部：
                # clean 通道的缺陷（pose_jump / quat_denorm）本来就 0 条 badcase，
                # 在 badcase 表里查不到是**正常**的，把它记成 not_found 会让 Q5 恒红
                # （第一版就是这么红的：22 条里 21 条其实都命中了）。
                "db_key_matched_by": {"badcase": how, "clean_episode_done": how_det,
                                      "clean_rule_event": how_ev}[
                    "badcase" if chan == "badcase" else
                    ("clean_episode_done" if chan == "clean_rejected" else "clean_rule_event")],
                "db_key_matched_by_all": {"badcase": how, "clean_episode_done": how_det,
                                          "clean_rule_event": how_ev},
                "db_episode_key": fired_key or det_key_ep or ev_key,
                "badcase_rules_fired": fired_ep,
                "clean_rejected_count": det_raw.get("rejected_count"),
                "clean_badcase_keys": (sorted(bck) if isinstance(bck, dict) else bck),
                "clean_rule_events": {r: [{"event": x.get("event"), "detail": x.get("detail")}
                                          for x in v] for r, v in (ev_raw or {}).items()},
                "rule_stats_badcase_count": {r: (rstats.get(r) or {}).get("badcase_count")
                                             for r in primary},
            }
            if chan == "badcase":
                hit = [k for k in primary if k in fired_ep]
                miss = [k for k in primary if k not in fired_ep]
            elif chan == "clean_rejected":
                # C01/C03 是 MutationRule：只贡献 rejected_indices，**正常路径不写 badcase**
                # （事实源：两个规则文件的类文档字符串）。它们的敏感性只能从 clean 段
                # episode_done 的 `rejected_count` 读到 —— 而那是**聚合值**，db 不记是哪条 C 规则
                # 贡献的 ⇒ 归因靠「单缺陷 episode」的构造成立（这条 episode 只注入一个缺陷）。
                n_rej = det_raw.get("rejected_count") or 0
                ok = (n_rej > 0)
                hit = list(primary) if ok else []
                miss = [] if ok else list(primary)
                evidence["channel_note"] = (
                    "rejected_count=%s（聚合值，不归因到单条规则）；归因依据=本 episode 只注入了 "
                    "%s 一个缺陷；旁证=rule_stats 的 badcase_count=%s"
                    % (n_rej, kind, evidence["rule_stats_badcase_count"]))
            elif chan == "clean_rule_event":
                # C02 是 AnnotationRule（「只标,不写盘」）：既不写 badcase 也不贡献 rejected_indices，
                # 唯一的通道是它自己那条 clean 事件。实测（19:5x）该事件的形态是
                # `rule='C02', event='quaternion_problems', detail_json={"count": 6}`
                # ⇒ **事件名**才是规则点名的地方，detail 里只有一个计数（不是问题清单本身）。
                # 所以核法 = 事件名命中 + detail 的计数键非零；两件事都要写进判词。
                want_event = spec.get("primary_event_name")
                got = set()
                for r in primary:
                    for item in ((ev_raw or {}).get(r) or []):
                        det = item.get("detail") or {}
                        if want_event and item.get("event") != want_event:
                            continue
                        if not det_key or det.get(det_key):
                            got.add(r)
                hit = sorted(got)
                miss = [k for k in primary if k not in got]
                evidence["channel_note"] = (
                    "按 clean 段 rule=%s 且 event=%r 的事件核，detail[%r] 必须非空/非零；"
                    "实测 detail 形态=%s（AnnotationRule 只写计数，不写问题清单）"
                    % (primary, want_event, det_key,
                       json.dumps(evidence["clean_rule_events"], ensure_ascii=False)[:200]))
            else:
                hit, miss = [], list(primary)
                evidence["channel_note"] = "未知 primary_channel=%r ⇒ 无从核，按未触发计" % chan
            extra = [k for k in fired_ep if k not in primary and k not in also and k not in notobs]
            per_eps.append({"episode_id": e.get("episode_id"), "defect": kind,
                            "expected_primary": primary, "expected_also": also,
                            "fired": fired_ep, "primary_hit": hit, "primary_missed": miss,
                            "fired_but_unexpected": extra, "evidence": evidence})
            missed.extend(["%s(%s)" % (k, kind) for k in miss])
            unexplained.extend(["%s(%s)" % (k, kind) for k in extra])
        bad5 = list(missed)
        chan_cov = {}
        for p in per_eps:
            ch = (p.get("evidence") or {}).get("channel") or "badcase"
            chan_cov.setdefault(ch, {"n_episodes": 0, "defects": []})
            chan_cov[ch]["n_episodes"] += 1
            chan_cov[ch]["defects"].append(p["defect"])
        unmatched = [p["defect"] for p in per_eps
                     if (p.get("evidence") or {}).get("db_key_matched_by") == "not_found"]
        obs5 = {"badcase_by_rule": bc, "n_defective_episodes": len(per_eps),
                "n_defect_kinds": len({p["defect"] for p in per_eps}),
                "per_episode": per_eps, "primary_missed": sorted(set(missed)),
                "fired_but_unexpected": sorted(set(unexplained)),
                "channel_coverage": {k: {"n_episodes": v["n_episodes"],
                                         "defects": sorted(set(v["defects"]))}
                                     for k, v in chan_cov.items()},
                "episodes_not_found_in_db": sorted(set(unmatched)),
                "path_kou_jing_note": (
                    "db 的 episode_id = **暂存副本**路径，manifest 记的是 pristine 路径；"
                    "本判据按同一相对路径把两个口径接起来（basename 兜底），并在每条 episode 的 "
                    "`evidence.db_key_matched_by` 里写明是哪种匹配命中的。匹配不上会单列在 "
                    "`episodes_not_found_in_db` 里 —— 第一版就是在这里静默查空，把 Q5 变成恒红。"),
                "violations": bad5}
        note5 = ("每种缺陷的 primary 都在**它自己的证据通道**上触发（badcase %d 条 / "
                 "clean_rejected %d 条 / clean_rule_event %d 条）⇒ 「0 badcase」不是空洞真。"
                 % (chan_cov.get("badcase", {}).get("n_episodes", 0),
                    chan_cov.get("clean_rejected", {}).get("n_episodes", 0),
                    chan_cov.get("clean_rule_event", {}).get("n_episodes", 0))
                 if not bad5 else
                 "有 primary 未触发 ⇒ QC 对我们这批数据不敏感，全绿不可采信。")
        if unmatched:
            note5 += (" 另有 %d 条 episode 在 db 里**找不到对应键**（%s）⇒ 那是路径口径没接上，"
                      "不是数据问题，必须先修判据再读结果。" % (len(set(unmatched)),
                                                              ",".join(sorted(set(unmatched))[:5])))
        if unexplained:
            note5 += (" 另有 %d 处「触发了但期望表里没有」的规则（%s）⇒ 期望表需按实测更新，"
                      "不静默扩大解释。" % (len(set(unexplained)), ",".join(sorted(set(unexplained))[:8])))
        rep.add("Q5_negative_control_caught", (not bad5 and bool(per_eps) and not unmatched), obs5,
                "负对照里**每条** episode 的已知缺陷都被点名的 primary 规则抓住；"
                "primary 的证据通道按算子类型分三种（badcase / clean_rejected / clean_rule_event），"
                "变更型与标注型算子**不得**因为「不写 badcase」就被记成未触发",
                note=note5,
                ruling_ref="裁定 27.1 / A2 §5「随机基线对照，证明判据不是恒真」的同型纪律",
                red_when=("任一 primary 在它自己的通道上未触发 / 负对照集为空 / "
                          "任一 episode 在 db 里找不到对应键（路径口径没接上）"))
    else:
        rep.add("Q5_negative_control_caught", None, "未提供 --neg-input",
                "必须有负对照，否则 Q3 的 0 badcase 无法排除空洞真",
                note="证据不足 ⇒ 弃权（不当作通过）",
                ruling_ref="裁定 27.1", red_when="任一 primary 规则未触发")

    # ---- Q6 双向均衡 + Q7 data_kind 戳 ----
    # 判据本体在 `judge_directions()` / `judge_data_kind()` 两个**纯函数**里，
    # 与 `--selftest-q6q7` 的 9 条牙共用同一份代码（被测对象与使用对象必须同一个）。
    # **2026-09-30 03:2x 改判**：旧判据把 0929 形态夹具的词表（`B_to_A` / `not_demonstration`）
    # 当成了通用口径 ⇒ 在 formal-40（`right_to_left` 20 / `left_to_right` 20、真示范集）上
    # 造出两条**假红**，其中一条的文案还是"全项目最硬的数据缺口"。详见两个函数的注释。
    q67_required = {
        "bal": "两个方向条数相等且**反向条数 > 0**；均衡由机器复算 `n_per_direction`，"
               "**不采信**交件自述的 `directions_balanced`（不符即红）。反向标签优先用数据集"
               "自己声明的 `reverse_direction_label`；认不出才退回 0929 夹具词表"
               "（`B_to_A`/`reverse`，退回路线登记在 `direction_labels.route`）；"
               "两条路线都认不出 ⇒ **弃权**（UNJUDGED），不猜。",
        "kind": "每条 episode 与 manifest 都盖 `data_kind` 戳；**按数据集角色分岔**："
                "① 形态夹具（`form_fixture` / `not_demonstration` / `synthesized_analytic` / "
                "`negative_control`）**不得自称 demonstration**；② 真示范集**可以**自称示范，"
                "但必须带齐三件能力免责声明（`not_a_capability_claim=true` / "
                "`capability_claim=false` / `policy_executed=false`），且 `data_kind`/`dataset_kind` "
                "不得出现 policy/teleop/human/learned/rollout 这类能力自称词。",
    }
    q67_red_when = {
        "bal": "反向条数为 0 / 两方向条数不相当 / 交件自述 `directions_balanced` 与机器复算不符",
        "kind": "episode 缺 data_kind；夹具自称 demonstration；示范集缺能力免责声明或其值不符；"
                "`policy_executed=false` 却自称 policy/teleop/human/learned/rollout",
    }
    q67_note = ("**改判记录（2026-09-30 03:2x）**：本条曾对 formal-40 判假红"
                "（首跑产物 `runs/vla/b2_sim_demo_bidir_20260930/qc_team_formal40/"
                "qc_verdict.run1_false_red_q6q7.json` 留证），根因是判据硬编码了 0929 夹具的词表；"
                "现已改为「用数据集自己声明的方向标签 + 按角色分岔的诚实义务」，"
                "并由 9 条牙钉住（`qc_q6q7_teeth.json`：4 条正向必须红、1 条必须弃权、"
                "4 条反向必须绿，含 T1 = formal-40 的真实形态不许再假红）。")
    for cid, key in (("Q6_directions_balanced", "bal"), ("Q7_data_kind_stamped", "kind")):
        rows, bad, unj = [], [], []
        for tag, r in results.items():
            mp = Path(r["input_dir"]) / "dataset_manifest.json"
            if not mp.exists():
                bad.append("%s：缺 dataset_manifest.json" % tag)
                continue
            man = json.loads(mp.read_text())
            j = judge_directions(man) if key == "bal" else judge_data_kind(man)
            row = {"set": tag}
            row.update(j["observed"])
            row["violations"] = j["violations"]
            row["unjudged_reasons"] = j["unjudged"]
            row["manifest_path"] = str(mp)
            rows.append(row)
            bad += ["%s：%s" % (tag, v) for v in j["violations"]]
            unj += ["%s：%s" % (tag, u) for u in j["unjudged"]]
        if not rows:
            rep.add(cid, None, "没有可读的 dataset_manifest.json", "每份数据集都要有 manifest",
                    ruling_ref="D→B2 §2.2 / §5", red_when="见 check 名")
        else:
            st = STATUS_RED if bad else (STATUS_UNJUDGED if unj else STATUS_PASS)
            rep.add(cid, {STATUS_PASS: True, STATUS_RED: False, STATUS_UNJUDGED: None}[st],
                    {"per_set": rows, "violations": bad, "unjudged_reasons": unj},
                    q67_required[key], note=q67_note, status=st,
                    ruling_ref=("D→B2 §2.2-1（两方向条数必须相当）/ §5（不得声称）/ 裁定 46 / "
                                "裁定 85.3 RR-B2-13 / 2026-09-30 03:2x 改判（假红根因修）"),
                    red_when=q67_red_when[key])

    # ---- Q8 输入面改写审计（团队流水线**不是只读的**，这条是它的护栏）----
    # 2026-09-29 18:07 实测：干净集跑完 validate→clean→qc 之后，**输入目录里**的
    # `converted_metadata_normal.json` 字节数与 mtime 都变了（clean 段 C05/C06/C08 就地改写），
    # 每条缺陷 episode 里多出 `badcase.json`，文件模式还被改成 0600。
    # ⇒ 两件事必须判：
    #   ① pristine 生成集必须**逐字节不变**（本脚本把流水线的输入换成 `qc_input/` 里的副本）；
    #   ② 副本上被改写/新增/删除的文件必须只落在白名单里（badcase.json /
    #      converted_metadata_normal.json / 三路 mp4）；出现别的 ⇒ RED。
    # 这条牙的存在理由：一旦有人拿 `workplace/ABC130k` 或 `yfw_input/` 当输入跑一次，
    # 团队语料就被**就地改写**了，而且不会报错（Q0 在跑之前拦，Q8 在跑之后核）。
    q8_rows, bad8 = [], []
    for tag, si in staged_inputs.items():
        pd = diff_snapshot(si.get("pristine_before") or {}, si.get("pristine_after") or {})
        sd = diff_snapshot(si.get("staged_before") or {}, si.get("staged_after") or {})
        off_whitelist = [x for x in (sd["changed"] + sd["added"] + sd["removed"])
                         if Path(x).name not in PIPELINE_WRITABLE_NAMES
                         and Path(x).suffix != ".mp4"]
        removed_any = sd["removed"]
        if pd["n_changed"] or pd["n_added"] or pd["n_removed"]:
            bad8.append("%s：pristine 生成集被动过（改 %d / 增 %d / 删 %d）⇒ 流水线的输入必须是副本，"
                        "原始生成集要保持可复现" % (tag, pd["n_changed"], pd["n_added"], pd["n_removed"]))
        if off_whitelist:
            bad8.append("%s：副本上有 %d 处改动落在白名单外（%s）⇒ 团队流水线动了它不该动的东西"
                        % (tag, len(off_whitelist), ",".join(off_whitelist[:6])))
        if removed_any:
            bad8.append("%s：副本上有文件被**删除**（%s）⇒ 只读纪律下不允许"
                        % (tag, ",".join(removed_any[:6])))
        mb, ma = si.get("meta_before") or {}, si.get("meta_after") or {}
        rewritten = sorted(k for k in (set(mb) & set(ma)) if mb[k] != ma[k])
        q8_rows.append({"set": tag, "pristine_dir": si.get("pristine"), "staged_dir": si.get("staged"),
                        "pristine_diff": pd, "staged_diff": sd,
                        "n_metadata_rewritten": len(rewritten),
                        "metadata_rewritten_sample": [
                            {"file": k, "changed_fields": {
                                f: {"before": (mb[k] or {}).get(f), "after": (ma[k] or {}).get(f)}
                                for f in sorted(set(mb[k] or {}) | set(ma[k] or {}))
                                if (mb[k] or {}).get(f) != (ma[k] or {}).get(f)}}
                            for k in rewritten[:3]],
                        "off_whitelist": off_whitelist,
                        "whitelist": sorted(PIPELINE_WRITABLE_NAMES) + ["*.mp4"]})
    if not q8_rows:
        rep.add("Q8_input_mutation_audit", None, "没有跑任何数据集（Q0 拦下了？）",
                "每份数据集都要做跑前跑后的输入面快照",
                note="证据不足 ⇒ 弃权", ruling_ref="D→B2 §0.2 / §0.3", red_when="见 check 名")
    else:
        rep.add("Q8_input_mutation_audit", not bad8,
                {"per_set": q8_rows, "violations": bad8,
                 "finding": ("团队流水线**会就地改写输入目录**（实测：metadata 被 clean 段重写、"
                             "缺陷 episode 里写出 badcase.json、文件模式变 0600）⇒ 绝不可拿"
                             " workplace/ABC130k 或 yfw_input 当输入；B2 一律先复制到 qc_input/ 再跑，"
                             "pristine 生成集逐字节核不变。")},
                "pristine 生成集逐字节不变；副本上的改动只落在白名单（badcase.json / "
                "converted_metadata_normal.json / *.mp4）内，且**没有任何文件被删除**",
                note=("这条判据同时给 Q4b 提供证据：metadata 被改写 = C05/C06 真的动了数据"
                      "（变更型算子正常路径不写 badcase，光看 badcase 会误判成「空转」）"),
                ruling_ref="D→B2 §0.2（只读使用团队资产）/ §0.3（不碰 datasets）/ 裁定 27.1",
                red_when="pristine 被动过 / 改动落在白名单外 / 有文件被删除")

    verdict = "RED" if rep.n_red else ("UNJUDGED" if rep.n_unjudged else
                                       ("WARN" if rep.n_warn else "PASS"))
    doc = {
        "spec": "B2 只读调用团队 vla_pipeline 的 validate→clean→qc，并判成可红可绿的判词",
        "verdict_kind": "b2_team_qc_run",
        "gate_build": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "scripts/b2_run_team_qc.py（B2 数据与判据线）",
        "config": {"path": str(cfg), "sha256": _sha256(cfg),
                   "thresholds_relaxed": False,
                   "note": "qc.* / process.* 全部逐字沿用团队 default.yaml；差异只有 paths 与 V13 开关，"
                           "逐条写在配置文件头部注释里"},
        "team_repo": str(team),
        "python": a.py,
        "ok": verdict == "PASS",
        "verdict": verdict,
        "summary": {"total": len(rep.checks), "pass": rep.n_pass, "warn": rep.n_warn,
                    "red": rep.n_red, "unjudged": rep.n_unjudged, "verdict": verdict},
        "checks": rep.checks,
        "runs": {t: {k: v for k, v in r.items() if k != "db"} for t, r in results.items()},
        "db_evidence": {t: r["db"] for t, r in results.items()},
        "not_a_capability_claim": ("本判词只证明「B2 造的 episode **形态**能过团队 QC」。"
                                   "**不**证明数据语义正确（QC 查文件/帧数/FPS/对齐，不查动作是否物理可行），"
                                   "**不**证明双向能力已具备（D→B2 §5）。"),
    }
    (base_out / "qc_verdict.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False,
                                                         default=str) + "\n")
    if not a.quiet:
        print("=" * 96)
        for c in rep.checks:
            print("  [%-8s] %s" % (c["status"], c["id"]))
            o = c["observed"]
            if isinstance(o, dict):
                for v in (o.get("violations") or o.get("vacuous") or o.get("missed_expected_keys") or [])[:5]:
                    print("             ** %s" % v)
        print("-" * 96)
        print("QC 判词：%s（PASS %d / WARN %d / RED %d / UNJUDGED %d）"
              % (verdict, rep.n_pass, rep.n_warn, rep.n_red, rep.n_unjudged))
        print("写出:", base_out / "qc_verdict.json")
        print("=" * 96)
    sys.exit(0 if verdict == "PASS" else (1 if verdict == "RED" else 3))


if __name__ == "__main__":
    main()
