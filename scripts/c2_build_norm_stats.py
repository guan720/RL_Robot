#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · T-C2-1 归一化 stats **生成器**（裁定 49.1 / 51① / 52 / 69）。

## D 裁定的口径（本脚本逐条落进产物，不静默选）
* **主线 stats 源 = B2 的 S1 仿真双向示范**（先导 5 集落地即算）；`env_derived` **只作诊断**、
  `yam_abc130k` **只作必红分支输入** ⇒ 两者一律 `not_for_mainline_normalizer=true`（裁定 52/61/69）。
* **`norm_map` 保留 QUANTILES，但每维必须有 scale 下限保护、近常量维必须显式标记**；
  **IDENTITY + 显式缩放**作对照分支保留 ⇒ **两案并列**报 D。
* **scale 下限系数给两个候选值 + 各自在真实数据上的效果，不许抄 ACT 旧阈值**（裁定 51①）：
  - `F1_physical_range_fraction`：`floor_d = coef × 物理行程_d`，coef 候选 **0.05 / 0.02**；
  - `F2_noise_scale_multiple`：`floor_d = coef × 逐步差分 MAD_d`，coef 候选 **4.0 / 2.0**。
* **下限烘进 q01/q99**：`normalize_processor.py:369` 只算 `q99-q01`，无法从外部注入下限
  ⇒ 这是唯一不改 site-packages 就能让下限生效的位置（见 `harness/norm_contract.py` 文档串）。
* **主线档没有数据就不产文件**：`--require-s1` 下 S1 帧缺席 ⇒ 写 `mainline_status.json`
  记 `waiting_for_s1_pilot_5`，**不拿 env/YAM 顶替、不伪造**。

## 产物
`runs/vla/c2_norm_contract_20260929/`
  `matrix.json`                     —— 两案 × 两族 × 两系数 的**并列**结果（D 要的就是这张表）
  `stats/<source>__<case>__<family>_<coef>.json` —— 每档的完整 stats（带 sha256-12、representation_version）
  `mainline_status.json`            —— 主线档状态（waiting / built），含触发条件与对 B2 的接口要求

## 纪律
数值主张带 loadavg + `nr_throttled`；外部/未实测量标 `declared_only`；不写「跑通/学会/达标」。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import norm_contract as nc      # noqa: E402

OUT_DEFAULT = ROOT / "runs/vla/c2_norm_contract_20260929"
A2_START_POSE_SRC = ROOT / "runs/vla/a2_pi05_zeroshot_20260929/approach_baseline.json"
YAM_STATS_DEFAULT = ROOT / "runs/vla/b2_abc130k_pairs_20260929/normalizer_stats.json"
# 头寸（bin 数）。**单一真值在契约层**（`nc.HEADROOM_BINS_DEFAULT`）：
# `nc.declared_interval_conformance()` 的"头寸消耗比"分母必须与 `nc.widen_to_cover()` 实际留的
# 头寸同源，否则"留了多少"与"吃掉几成"就是两个口径（与 NEAR_CONSTANT_REL_TOL 曾各写一份同族）。
HEADROOM_BINS = nc.HEADROOM_BINS_DEFAULT
assert HEADROOM_BINS == 1.0, "D 的文书按 1 bin 头寸引用本档读数；改这个值 = 换 representation_version"
BEFORE_IMAGE = {"path": "runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_e295544b5431",
                "sha256_12_of_patched_file": "e295544b5431",
                "n_lines_of_patched_file": 3102,
                "image_taken_at": ("2026-09-30T05:32:51+08:00（`cp -p` 保留了被改文件的原 mtime 05:32:51 "
                                   "⇒ 影像的 mtime 不等于留像时刻，这里显式记两个）"),
                "why": ("裁定 35.1：改自己的脚本前留 before 影像。**本条是补登记**：该影像 05:32:51 就已落盘，"
                        "但当时没写进本字典 ⇒ 修前本块最新一层停在 `e0f9ca34ffc1`/2789 ln，而盘上真实的最新一层是 "
                        "`e295544b5431`/3102 ln（名实不符；且**闸侧没有任何 check 审本块** ⇒ 属沉默缺口，"
                        "故在此就地登记并写明补登记理由，不留成暗账）。该轮改动（05:32→06:03，实测 38 行差异）= "
                        "① 红标签的权威口径改读结构化 `payload['red']`，只在卫语句提前抛、拿不到 payload 时才回落"
                        "按分隔符反解（牙文案里合法地含中文分号 ⇒ 反解会切出幻影红标签）；② `expected_red_teeth` "
                        "由一个从未存在过的 id 改成本行实测真红的两个 id；③ 行级补 `eval_scope` / "
                        "`eval_frames_are_held_out` 两键（修前缺失，读者只能从牙名猜）；④ 变异体副本里 "
                        "`resolve()` 改 `absolute()`（副本的 runs 是指向真 runs 的符号链接，canonicalize 会逃出副本 "
                        "ROOT ⇒ 下游 `relative_to(ROOT)` 抛 ValueError、连 matrix 都不产 ⇒ 翻转台账拿不到 mainline "
                        "侧实测翻转）；⑤ 显示用路径改走本文件已有的不抛版本 `rel()`（同一根因的第二道防线）"),
                "recovered_note": ("补登记时刻 = 2026-09-30T07:1x+08:00；核法 = 影像与实物做 `diff` 并**逐行读过**"
                                   "全部 38 行差异、确认都落在上述 5 项内，不是只比 sha；"
                                   "留像文件 = `before_images/c2_build_norm_stats.py.before_e295544b5431`"),
                "previous_before_image": {"path": "runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_e0f9ca34ffc1",
                "sha256_12_of_patched_file": "e0f9ca34ffc1",
                "n_lines_of_patched_file": 2789,
                "image_taken_at": ("2026-09-30T04:5x+08:00（本轮开工时留像；`cp -p` 保留了被改文件的原 mtime "
                                   "04:32 ⇒ 影像的 mtime 不等于留像时刻，这里显式记两个）"),
                "why": ("裁定 35.1：改自己的脚本前留 before 影像。本轮改动 = **裁定 90.4-3 触发判据的口径缺陷修复**："
                        "修前 `bins_occupied` 只在 held-out 评估帧（formal-40：n=547）上量，而 D 在裁定 90.2 #16 / "
                        "§18.6 引的是全量帧口径（n=11035）⇒ 同一条触发判据两口径**结论相反**"
                        "（held-out：8/8 行触发、dims_below=[0,3,5,7,10,12]；build/all：0/8 行触发、"
                        "dims_below=[3,10] 全是已分类近常量维）。现在三个口径都量、都落盘，`triggered` 拆成逐口径字段 "
                        "+ `governing_caliber=OPEN_question_to_d`；并把 `compose_mainline_finding` 里"
                        "「取 `main_rows[0]` 当整臂」改为**逐行聚合** + 落盘对照读数（裁定 92.6 自查项族）。"
                        "**C2 不选口径**（升 P0 = 改关键路径，属 D 裁量）；新代码 = `trigger_caliber_readings()` / "
                        "`probe_citation()` / `CALIBER_NAMES` / 行键 `summary_all`+`n_all_frames`+`summary_calibers` / "
                        "`run_source(all_frames=…)` / 返回键 `condition_b_resolution_first_row`→`condition_b_resolution`"),
                "corroborating_probe": {
                    "path": "runs/vla/c2_norm_contract_20260929/probe_trigger_caliber_20260930/verdict.json",
                    "sha256_12": "8da89e59caa9", "n_lines": 1534, "bytes": 40658,
                    "generator": "runs/vla/c2_norm_contract_20260929/probe_trigger_caliber_20260930/probe.py",
                    "role": ("只读旁证（用生成器自己的 `load_frames`/`split_heldout_by_episode` + "
                             "`nc.roundtrip_from_payload` 从**落盘 stats 文件**重算）；"
                             "划分自证 = 帧多重集相等（`multiset_build_plus_heldout_equals_all=true`）"),
                    "note": "生成器运行时由 `probe_citation()` **重读** sha（裁定 82.6：不沿用早先 run 的值）"},
                "previous_before_image": {"path": "runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_634e8e894087",
                "sha256_12_of_patched_file": "634e8e894087",
                "n_lines_of_patched_file": 2121,
                "image_taken_at": ("2026-09-30T03:57+08:00（本轮开工时留像；`cp -p` 保留了被改文件的原 "
                                   "mtime 03:41:02 ⇒ 影像的 mtime 不等于留像时刻，这里显式记两个）"),
                "why": ("裁定 35.1：改自己的脚本前留 before 影像。本轮改动 = 落地**裁定 90.4-1**"
                        "（`Tiv_no_state_outside_declared_interval` 的极性撤回 ⇒ 授权事实改 A/F/G、"
                        "旧升级项转 `ruled_escalations`）与**裁定 90.4-4**（权威接口 = npz + `--s1-frames`；"
                        "`--s1-lerobot` 降为交叉核对臂、标签改 `formal40_lerobot_crosscheck`；"
                        "`auto_stats_provenance` 按 8 项机器判据认 formal-40 npz）；"
                        "两臂的 finding 组合抽成 `compose_mainline_finding()`（同一份实现，避免散文漂移）；"
                        "新增 `resolve_physical_range_npz_mainline` / `crosscheck_npz_vs_lerobot` / "
                        "`sha12_bytes` / `iso_mtime` / `_count_per_direction`"),
                "previous_before_image": {"path": "runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_a8d8d6e2598e",
                "sha256_12_of_patched_file": "a8d8d6e2598e",
                "why": ("裁定 35.1：改自己的脚本前留 before 影像；本轮改动 = 落地裁定 87.3-1 的 ①"
                        "（`must_cover` → 声明物理区间）+ 条件 b/c 的实测登记 + "
                        "`allowed_red_teeth` 由测量派生（不再手写常量）"),
                "previous_before_image": {"path": "runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_b52b31245140",
                                          "sha256_12_of_patched_file": "b52b31245140",
                "why": ("裁定 35.1：改自己的脚本前留 before 影像；本轮改动 = ① 新增 `--s1-lerobot` 直读 "
                        "π₀.₅ LeRobot 出口的 parquet（裁定 85.4-2，B2 的 `states_14d.npz` 导出任务已撤销）；"
                        "② 溯源标签 `pre_pilot5_path_check` → `pilot10_path_check`（裁定 85.4-2-4 作废降级路径）；"
                        "③ 每行显式声明 `stats_provenance` + `consumer`，喂契约层新牙 Tp4/Tp5（裁定 85.4-3 同源硬闸）"),
                                          "previous_before_image": {"path": "runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_e921cd9c965d",
                                          "sha256_12_of_patched_file": "e921cd9c965d",
                                          "why": "IDENTITY 分支 center 可行区间界序反转（need>=span ⇒ 区间恒空 ⇒ np.clip 返回 a_max ⇒ Tc 恒红）"}}}}}}


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def sha12(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def load_pair() -> dict:
    la = " ".join(Path("/proc/loadavg").read_text().split()[:3]) if Path("/proc/loadavg").exists() else "unavailable"
    nt = None
    for cand in ("/sys/fs/cgroup/cpu,cpuacct/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        p = Path(cand)
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("nr_throttled"):
                    nt = int(line.split()[1])
            break
    return {"loadavg": la, "nr_throttled": nt, "cgroup_quota_cores": 12}


def load_frames(npz: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    d = np.load(npz, allow_pickle=False)
    frames = np.asarray(d["frames"], dtype=np.float64)
    start = np.asarray(d["start_poses"], dtype=np.float64)
    prange = np.asarray(d["physical_range"], dtype=np.float64)
    man = {}
    mp = npz.parent / "manifest.json"
    if mp.exists():
        man = json.loads(mp.read_text(encoding="utf-8"))
    return frames, start[0] if start.ndim == 2 else start, prange, man


def start_pose_from_a2() -> tuple[np.ndarray, dict]:
    """A2 实测的起始位姿（`hold_action_14d`）—— 牙 (c) 的输入，独立于本线采集。"""
    d = json.loads(A2_START_POSE_SRC.read_text(encoding="utf-8"))
    v = np.asarray(d["hold_action_14d"], dtype=np.float64)
    return v, {"source": str(A2_START_POSE_SRC.relative_to(ROOT)), "sha256_12": sha12(A2_START_POSE_SRC),
               "field": "hold_action_14d", "n_dims": int(v.size),
               "abs_max": float(np.abs(v).max()),
               "dims_exceeding_unit_interval": sorted(int(i) for i in np.nonzero(np.abs(v) > 1.0)[0]),
               "control_dt_in_that_run": d.get("control_dt"),
               "note": "该文件的 control_dt=0.02 是**当时**的口径；起态位姿与频率无关，可直接用（裁定 53 只改频率口径）"}


def yam_stats_arrays(path: Path, group: str = "direction:forward") -> tuple[dict[str, np.ndarray], dict]:
    """B2 的 ABC-130k（YAM 形态）stats ⇒ **只**用于必红分支（裁定 43.4/52/61/69）。"""
    d = json.loads(path.read_text(encoding="utf-8"))
    g = d["groups"][group]["state"]
    q = g["quantiles"]                      # 实测键名：quantiles.{p1,p50,p99}（不是顶层 p01/p99）
    arr = {"q01": np.asarray(q["p1"], dtype=np.float64), "q99": np.asarray(q["p99"], dtype=np.float64),
           "mean": np.asarray(g["mean"], dtype=np.float64), "std": np.asarray(g["std"], dtype=np.float64),
           "min": np.asarray(g["min"], dtype=np.float64), "max": np.asarray(g["max"], dtype=np.float64),
           "median": np.asarray(q["p50"], dtype=np.float64)}
    prov = {"source": str(path.relative_to(ROOT)), "sha256_12": sha12(path), "group": group,
            "morphology_proxy": d.get("morphology_proxy"),
            "morphology_proxy_basis": d.get("morphology_proxy_basis"),
            "vector_layout": d.get("vector_layout", {}).get("primary"),
            "n_frames_used": g.get("n_frames_used"),
            "quantile_policy": d.get("quantile_policy"),
            "quantile_keys_used": ["quantiles.p1", "quantiles.p99", "quantiles.p50"],
            "n_rows_subsampled": q.get("_n_rows_subsampled"), "stride": q.get("_stride"),
            "all_zero_dims": g.get("all_zero_dims"),
            "saturation_if_unnormalized_to_pm1": g.get("saturation_if_unnormalized_to_pm1"),
            "cross_morphology_evidence": ("YAM 的 p50 与 ViperX300 起态符号/零位不同"
                                          "（例 dim1：YAM p50=1.4479 vs A2 实测起态 -0.96）"
                                          "⇒ 搬 stats 等于把饱和问题换成错配问题（裁定 43.4/52）"),
            "allowed_use": "必红分支输入（YAM 形态、零位/符号不同；主线禁用）"}
    return arr, prov


def eval_verdict(**kw):
    """跑一次契约判定，统一返回 `(verdict, red, teeth, warnings)`（红时不丢逐牙明细）。"""
    try:
        res = nc.evaluate_contract(**kw)
    except nc.NormContractViolation as exc:
        pl = getattr(exc, "payload", None) or {}
        # 红标签的**权威**口径 = 结构化的 `payload["red"]`；**不再**从 `str(exc)` 反解。
        # WHY（本轮实测到的真缺陷）：牙的 `required`/`observed` 文案里合法地含中文分号
        # （`Tesc` 的 required 写了"…不是调参项；裁定 90.6-1 明令不得放宽"）⇒ 用 `"；"` 拼出的
        # 字符串再 `split("；")` 会切出**幻影红标签**（原型跑里主线 8 行各多一个 `裁定`），
        # 污染 `red_ids` 与 `unexplained_red_teeth`。详见 `nc.RED_MESSAGE_SEPARATOR` 的注释。
        rl = pl.get("red")
        if rl is None:                     # 提前抛的卫语句可能只给字符串 ⇒ 才回落（三态：不假装）
            rl = str(exc).split(nc.RED_MESSAGE_SEPARATOR)
        return ("RED", [str(x) for x in rl], pl.get("teeth"), pl.get("warnings", []), pl or None)
    # 没抛异常，但契约层自己算出了红 ⇒ **内部不一致**（典型形态：变异体把 `raise` 去掉，
    # 于是"恒绿的闸"）。不静默当绿，显式记一条一致性牙。
    if res.get("red") or res.get("verdict") != "PASS":
        return ("RED", [f"Tconsistency_raise_matches_verdict 契约层算出红但未抛异常: "
                        f"required=raise 或 verdict==PASS observed=verdict={res.get('verdict')} "
                        f"n_red={len(res.get('red') or [])}"],
                res.get("teeth"), res.get("warnings", []), res)
    return "PASS", [], res["teeth"], res.get("warnings", []), res


def roundtrip_from_file(fp: Path, *, case, frames, start_pose, source, features,
                        physical_range_fallback, mainline, eval_frames, force_blocking,
                        in_memory_verdict: str, physical_interval=None,
                        consumer: str | None = None,
                        coverage_target_expected: str | None = None,
                        all_frames=None, gate_verdict: str | None = None,
                        gate_run_dir: str | None = None,
                        gate_verdict_sha256_12: str | None = None,
                        gate_verdict_class1: str | None = None) -> dict:
    """**从落盘文件读回**再判一次：证明"闸判的就是交付的那一份"（附录 02:274 同族）。

    本轮实测到过反例：IDENTITY 档 `stats_payload()` 重算 center/gain ⇒ 文件里的值与被判的值
    不同（详见 `harness/norm_contract.py:stats_payload` 注释）。所以这一步不是装饰。
    """
    payload = json.loads(Path(fp).read_text(encoding="utf-8"))
    st2 = nc.roundtrip_from_payload(payload)
    # 溯源标签与消费方**从文件读回**（不是沿用内存里的那份）：硬闸要能在**交付物**上复算，
    # 否则下游拿文件走 BC 配置时，闸判的是别的东西（附录 02:274「缓存不得冒充新表示」同族）。
    adm = nc.admission_from_payload(payload)
    prov2 = adm["stats_provenance"]
    # 覆盖目标同样**从文件读回**：牙 `Tcov`/`Tiv` 的 `applies_when` 全靠它。若这里沿用内存值，
    # 而文件里写的是别的（或没有），复算就会与内存判定分叉 ⇒ `match=False` 却查不出原因。
    cov2 = nc.coverage_target_from_payload(payload)
    ct2 = cov2["coverage_target"]
    pr_from_file = "physical_range" in st2
    pr2 = np.asarray(st2["physical_range"] if pr_from_file else physical_range_fallback,
                     dtype=np.float64)
    v2, red2, teeth2, warn2, _ = eval_verdict(case=case, stats=st2, frames=frames,
                                              start_pose=start_pose, source=source,
                                              features=features, physical_range=pr2,
                                              mainline=mainline, eval_frames=eval_frames,
                                              force_blocking=force_blocking,
                                              physical_interval=physical_interval,
                                              stats_provenance=prov2, consumer=consumer,
                                              coverage_target=ct2,
                                              # 裁定 93.2/93.4：复算必须走**与内存判定同一份口径**，
                                              # 否则 `Tres`（全量口径）与 `Tbcad`（闸 verdict）会在
                                              # 两侧取到不同输入 ⇒ `match=False` 却查不出原因。
                                              all_frames=all_frames, gate_verdict=gate_verdict,
                                              gate_run_dir=gate_run_dir,
                                              gate_verdict_sha256_12=gate_verdict_sha256_12,
                                              gate_verdict_class1=gate_verdict_class1)
    match = (v2 == in_memory_verdict)
    # `bc_admission` 字段是**生成当时**那版契约层写的 ⇒ 用当前口径重判一次，不一致就报。
    adm_agree = adm["agree"]
    return {"stats_file": str(Path(fp).relative_to(ROOT)), "sha256_12": sha12(fp),
            "in_memory_verdict": in_memory_verdict, "verdict_from_file": v2, "match": match,
            "red_from_file": red2, "physical_range_from_file": pr_from_file,
            "arrays_keys": sorted(payload.get("arrays", {})),
            "n_teeth_from_file": (None if teeth2 is None else len(teeth2)),
            "n_warnings_from_file": len(warn2),
            "stats_provenance_from_file": prov2,
            "coverage_target_from_file": ct2,
            "coverage_target_known_from_file": cov2["known"],
            "coverage_target_agrees_with_build": (None if coverage_target_expected is None
                                                  else bool(ct2 == coverage_target_expected)),
            "coverage_block_present_in_file": cov2["coverage_block_present"],
            "consumer_used_for_roundtrip": consumer,
            "bc_admission_from_file": adm["file_says"],
            "bc_admission_recomputed": adm["recomputed"],
            "bc_admission_file_vs_recomputed_agree": adm_agree,
            "file_had_bc_admission": adm["file_had_bc_admission"],
            "tooth_id": "Trt_payload_roundtrip",
            "red_when": "落盘 arrays 复算的 verdict ≠ 内存判定的 verdict（= 闸判的不是交付物）",
            "note": ("round-trip 只覆盖 **stats 表示**（arrays）；评估帧与起态仍来自采集产物，"
                     "不是本文件的一部分")}


def resolve_physical_range(args, npz_prange, npz_path: Path, prefer: str = "errata"):
    """物理行程分母的**出处解析**（F1 下限族与近常量标记都用它 ⇒ 出处必须显式、可复算）。

    优先级：① 勘误件的 `physical_range_effective` = max(声明行程, 实测行程)；
            ② npz 自带的 `physical_range_effective`（修正后的采集器会写）；
            ③ npz 的 `physical_range`（**已知缺陷**：右臂 qpos 映射差一 ⇒ dim12 差 175×；
               夹爪行程按 1.0 假设 ⇒ 实测 0.91001）⇒ 只作对照，产物标 `superseded_defect=true`。
    为什么必须 ①：`jnt_range` 是**软**边界（live 实测 hold 60 步 `qpos[6]=0.07333 > jnt_hi=0.057`，
    +28.6%；random 档 8 个维越界）⇒ 拿声明行程当分母会低估该维能走多远，F1 下限跟着偏小。
    """
    jp = Path(args.physical_range_json)
    # `prefer="npz"`：**主线档专用**。勘误件的 `physical_range_effective` 里的"实测行程"是从 C2 的
    # env 诊断档（random/sweep/hold）量出来的；把它搬到 B2 的示范帧上就是裁定 71 禁止的**跨口径移植**。
    # 可以搬的是**规则**（max(声明行程, 同源实测行程)），不能搬的是**实测值**。
    # ⇒ 主线档只认 npz 自带的、与 frames 同源的那份（B2 的导出器已按此写 `physical_range_effective`）。
    if (not args.ignore_physical_range_json) and jp.exists() and prefer != "npz":
        d = json.loads(jp.read_text(encoding="utf-8"))
        arr = np.asarray(d["physical_range_effective"], dtype=np.float64)
        iv = (d.get("physical_interval") or {})
        interval = ([np.asarray(iv["lo"], dtype=np.float64), np.asarray(iv["hi"], dtype=np.float64)]
                    if ("lo" in iv and "hi" in iv) else None)
        return arr, interval, {"basis": "max(jnt_travel_through_upstream_normalizer, observed_travel)",
                     "ctrlrange_interval_basis": "声明 jnt_range（经 upstream 归一化换算）；覆盖率只作记录（裁定 51.1）",
                     "source": str(jp.relative_to(ROOT)), "sha256_12": sha12(jp),
                     "rule": d.get("physical_range_effective_rule"),
                     "declared_jnt_travel": d.get("physical_range"),
                     "superseded_defect": False,
                     "correction_ref": ("runs/vla/c2_norm_contract_20260929/"
                                        "physical_range_correction/correction.json"),
                     "defects_corrected": ["右臂 qpos 映射差一（dim7-12；dim12 = 0.036 vs 真值 6.28316）",
                                           "夹爪行程按 1.0 假设（实测 0.91001，差 9.0%）",
                                           "jnt_range 被当硬边界（实测是软边界，见 Tp4）"]}
    z = np.load(npz_path)
    if "physical_range_effective" in z.files:
        arr = np.asarray(z["physical_range_effective"], dtype=np.float64)
        return arr, None, {"basis": "npz.physical_range_effective（采集器已修正版）",
                           "source": str(npz_path.relative_to(ROOT)), "sha256_12": sha12(npz_path),
                           "superseded_defect": False,
                           "ctrlrange_interval": "未提供 ⇒ Tw_ctrlrange_coverage 出 N_A（不判红）"}
    arr = np.asarray(npz_prange, dtype=np.float64)
    return arr, None, {"basis": "npz.physical_range（**旧口径，已知缺陷**）",
                       "source": str(npz_path.relative_to(ROOT)), "sha256_12": sha12(npz_path),
                       "superseded_defect": True,
                       "defect_ref": ("runs/vla/c2_norm_contract_20260929/"
                                      "physical_range_correction/correction.json")}


def s1_npz_crosscheck(npz_path: Path, frames: np.ndarray, pr_used: np.ndarray) -> dict:
    """**不采信** B2 npz 里的数组：逐维复算，把"契约符合性"变成实测记录（裁定 82.6 的同源纪律）。

    复算三件事：① `observed_travel` 是否等于本 npz 的 frames 逐维 max-min；
    ② `physical_range_effective` 是否等于 max(声明行程, 同源实测行程)（= C2 §6.2 的规则）；
    ③ 本脚本**实际拿去用的**分母是否就是 ② 那一份（防止"登记一份、用另一份"）。
    任何一条不符 ⇒ `contract_conformant=False`，**报 D，不改 B2 的产物**（D §13-2②）。
    """
    z = np.load(npz_path, allow_pickle=False)
    have = {k: np.asarray(z[k], dtype=np.float64) for k in
            ("physical_range", "physical_range_effective", "physical_range_declared_c2_caliber",
             "observed_travel") if k in z.files}
    rec_obs = frames.max(axis=0) - frames.min(axis=0)
    out = {"npz_arrays_present": sorted(have), "n_frames": int(frames.shape[0]),
           "recomputed_observed_travel": rec_obs.tolist()}
    if not {"physical_range_effective", "physical_range_declared_c2_caliber", "observed_travel"} <= set(have):
        out["contract_conformant"] = False
        out["why"] = f"缺数组：需要 physical_range_effective/…_declared_c2_caliber/observed_travel，实到 {sorted(have)}"
        return out
    decl, eff, obs = (have["physical_range_declared_c2_caliber"], have["physical_range_effective"],
                      have["observed_travel"])
    d_obs = np.abs(obs - rec_obs)
    rel_obs = d_obs / np.maximum(np.abs(rec_obs), 1e-12)
    expect_eff = np.maximum(decl, obs)
    d_eff = np.abs(eff - expect_eff)
    rel_eff = d_eff / np.maximum(np.abs(expect_eff), 1e-12)
    d_used = np.abs(pr_used - eff)
    rel_used = d_used / np.maximum(np.abs(eff), 1e-12)
    out.update({
        "observed_travel_max_abs_diff": float(d_obs.max()),
        "observed_travel_max_rel_diff": float(rel_obs.max()),
        "observed_travel_worst_dim": int(rel_obs.argmax()),
        "effective_equals_max_declared_observed": bool(np.all(rel_eff <= 1e-9)),
        "effective_max_rel_diff": float(rel_eff.max()),
        "denominator_used_equals_npz_effective": bool(np.all(rel_used <= 1e-12)),
        "denominator_used_max_rel_diff": float(rel_used.max()),
        "contract_literal_gripper_dims": {int(i): float(have["physical_range"][i])
                                          for i in (6, 13) if "physical_range" in have},
        "declared_c2_caliber_gripper_dims": {int(i): float(decl[i]) for i in (6, 13)},
    })
    out["contract_conformant"] = bool(
        out["effective_equals_max_declared_observed"] and out["denominator_used_equals_npz_effective"]
        and rel_obs.max() <= 1e-9)
    out["dims_exceeding_unit_interval"] = sorted(int(i) for i in np.nonzero(np.abs(frames).max(axis=0) > 1.0)[0])
    return out


def split_heldout_by_episode(npz_path: Path, frames: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """主线档的 build / eval 划分：**按集切**，留出每个方向的最后一集。

    为什么必须按集：帧级随机切会让同一集内相邻帧（几乎相同的状态）同时出现在 build 与 eval 里
    ⇒ `Td2_clip_heldout` / `Te2_no_illegal_bin_heldout` 名义上"held-out"、实质上是 build 帧的重测
    （**01:5x 实测到过：`--s1-frames` 首跑 `eval_frames_are_held_out=False`、2746 build / 2746 eval**）。
    没有 `episode_index` ⇒ 返回 (frames, frames) 并把 `held_out=False` 显式登记，**不假装切过**。
    """
    z = np.load(npz_path, allow_pickle=False)
    if "episode_index" not in z.files:
        return frames, frames, {"held_out": False, "why": "npz 无 `episode_index` ⇒ 无法按集切；不假装切过"}
    ep = np.asarray(z["episode_index"])
    if ep.size != frames.shape[0]:
        return frames, frames, {"held_out": False,
                                "why": f"episode_index 长度 {ep.size} != frames {frames.shape[0]}"}
    uniq_eps = sorted(set(int(e) for e in ep.tolist()))
    # ⚠ `direction_code` 是**按集**给的（长度 = 集数），`episode_index` 是**按帧**给的（长度 = 帧数）
    # ⇒ 两者不可直接 zip。01:5x 实测踩过：直接 zip 只配上前 10 帧 ⇒ 分组全错 ⇒ 误报
    # "每个方向的集数 < 2"。修法：按 `episode_boundaries` 的顺序把集号映到方向码，且长度不符就**响亮拒绝**。
    if "direction_code" in z.files:
        dc = np.asarray(z["direction_code"])
        if dc.size != len(uniq_eps):
            return frames, frames, {"held_out": False,
                                    "why": (f"direction_code 长度 {dc.size} != 集数 {len(uniq_eps)} "
                                            f"⇒ 无法确定它是按集还是按帧给的，拒绝猜")}
        ep_dir = dict(zip(uniq_eps, (int(c) for c in dc.tolist())))
    else:
        ep_dir = {e: 0 for e in uniq_eps}
    hold_eps = []
    for code in sorted(set(ep_dir.values())):
        eps_in_dir = sorted(e for e, c in ep_dir.items() if c == code)
        if len(eps_in_dir) >= 2:
            hold_eps.append(eps_in_dir[-1])          # 每个方向留最后一整集
    if not hold_eps:
        return frames, frames, {"held_out": False, "why": "每个方向的集数 < 2 ⇒ 留不出整集"}
    mask = np.isin(ep, hold_eps)
    return (frames[~mask], frames[mask],
            {"held_out": True, "rule": "按集切：每个 direction_code 的最后一整集留出作 eval",
             "held_out_episodes": [int(e) for e in hold_eps],
             "n_episodes_total": len(uniq_eps),
             "episode_to_direction": {str(k): v for k, v in sorted(ep_dir.items())},
             "n_build_frames": int((~mask).sum()), "n_eval_frames": int(mask.sum()),
             "leakage_note": "同一集的帧不会跨 build/eval（相邻帧近似重复 ⇒ 帧级随机切等于没切）"})


# ─────────────────────────────────────────────────────────────────────────────────────────
# `--s1-lerobot`：直读 π₀.₅ LeRobot 出口的 parquet（裁定 85.4-2）
#
# 为什么必须有这条路径（不是"多一个入口"）：D 已**撤销** B2 的 `states_14d.npz` 导出任务
# （裁定 85.4-2-1：它复制 parquet 已有内容，而 B2 是负载最重的线）。formal-40 落地时
# **不会**再有 npz ⇒ 主线 stats 的唯一入口就是 lerobot 目录本身。
#
# 口径（裁定 85.4-2 逐条落地，不静默选）：
#   * 按 `episode_index` 分组、组内按 `frame_index` **升序**拼接；
#   * dtype：parquet 存 `float32` ⇒ 产物记 `state_dtype_source=float32_parquet_upcast_to_float64`，
#     并**实测**上转是否逐位无损（不是照抄"理论上无损"）；
#   * `start_poses` = 每集 `frame_index == 0`；
#   * `physical_range` = C2 自己的 `physical_range_effective` 规则（max(声明行程, **同源**实测行程)）；
#   * `stats_provenance` 写明数据集身份 + `demo_manifest.json` 的 sha256-12 + `generated_at`。
# ─────────────────────────────────────────────────────────────────────────────────────────
LEROBOT_STATE_COL = "observation.state"
LEROBOT_COLS = ("observation.state", "episode_index", "frame_index", "index", "task_index", "timestamp")
DTYPE_DECLARATION = {
    "state_dtype_source": "float32_parquet_upcast_to_float64",
    "parquet_storage_dtype": "float32（schema: fixed_size_list<element: float>[14]）",
    "compute_dtype": "float64",
    "note": ("q01/q99 等**分位统计量**对 float32→float64 上转不敏感（上转是精确的，float32 ⊂ float64）；"
             "但**逐位比较不可跨 dtype**：同一批状态在 float32 与 float64 下的 sha/逐位相等判定没有可比性，"
             "跨 dtype 的『逐位相同』主张一律无效（裁定 85.4-2）。本产物里的逐位主张都已注明比较双方的 dtype。"),
}


def resolve_lerobot_dirs(arg: Path) -> dict:
    """`--s1-lerobot` 接受两种写法，都解析成同一对绝对路径，并记录**用了哪种解释**（不猜）。

    ① 数据集目录：含 `pi05_lerobot/data/`（B2 的 `runs/vla/b2_sim_demo_bidir_*/pilot`）；
    ② lerobot 目录本身：含 `data/` + `meta/`。
    都不匹配 ⇒ **响亮拒绝**（不 fallback 到 rglob 全盘找 parquet：那会静默吃到别的数据集）。
    """
    p = Path(arg)
    # 用 absolute() 而不是 resolve()：resolve 会穿过变异体副本里的 `runs` 符号链接（见 rel() 的注释）
    p = p if p.is_absolute() else (ROOT / p).absolute()
    if (p / "pi05_lerobot" / "data").is_dir():
        ds, lr, interp = p, p / "pi05_lerobot", "dataset_dir（含 pi05_lerobot/）"
    elif (p / "data").is_dir() and (p / "meta").is_dir():
        ds, lr, interp = p.parent, p, "lerobot_dir（含 data/ + meta/）"
    else:
        raise SystemExit(
            f"[RED] --s1-lerobot 路径无法解释：{p}\n"
            f"  需要 `{p}/pi05_lerobot/data/` 或 `{p}/data/` + `{p}/meta/`；两者都不在。\n"
            f"  拒绝 rglob 全盘搜 parquet（会静默吃到别的数据集 = 裁定 52/69 的同源要求被绕过）")
    dm = ds / "demo_manifest.json"
    return {"dataset_dir": ds, "lerobot_dir": lr, "interpretation": interp,
            "dataset_dir_rel": rel(ds), "lerobot_dir_rel": rel(lr),
            "demo_manifest": dm,
            "demo_manifest_exists": dm.exists(),
            "demo_manifest_sha256_12": (sha12(dm) if dm.exists() else None),
            "demo_manifest_mtime": (mtime_iso(dm) if dm.exists() else None),
            "demo_manifest_bytes": (dm.stat().st_size if dm.exists() else None)}


def rel(p) -> str:
    """路径显示：在 ROOT 内就写相对路径，否则写绝对路径（**不抛**）。

    为什么不能一律 `relative_to(ROOT)`：变异体副本（`scripts/c2_gate_norm_contract.py` 建的
    `run_*/mutants/<mid>/`）里的 `runs` 是指向真 `runs/` 的**符号链接**；若先 `.resolve()`
    就会 canonicalize 到真仓路径 ⇒ 不在该副本的 ROOT 之内 ⇒ `relative_to` 抛 ValueError。
    """
    p = Path(p)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def mtime_iso(p: Path) -> str:
    return _dt.datetime.fromtimestamp(Path(p).stat().st_mtime).astimezone().replace(microsecond=0).isoformat()


def load_frames_lerobot(res: dict) -> dict:
    """从 lerobot 目录读 `observation.state` ⇒ `frames=[N,14] float64`（**按集分组 + 组内 frame_index 升序**）。

    三件"不采信、要实测"的事（本仓纪律：verify, don't trust）：
      ① **排序是否本来就已成立**：`raw_order_already_grouped_sorted`。若为 False，则重排是**实质性**的，
         必须留痕（否则下游无法判断我拼出来的帧序是不是我自己造的）；
      ② **上转是否逐位无损**：float32 → float64 再回 float32，按 uint32 位模式比（不是比值相等）；
      ③ **`frame_index` 是否逐集连续**：有缺口 ⇒ 说明上游丢过帧，必须记 `n_frame_index_gaps`，
         不假装"连续"。
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    lr = res["lerobot_dir"]
    files = sorted((lr / "data").glob("chunk-*/*.parquet"))
    stray = sorted(set((lr / "data").rglob("*.parquet")) - set(files))
    if not files:
        raise SystemExit(f"[RED] {lr}/data/chunk-*/*.parquet 一个都没有 ⇒ 拒绝产 stats（不拿别的数据顶替）")
    tbls = [pq.read_table(f, columns=[c for c in LEROBOT_COLS]) for f in files]
    t = pa.concat_tables(tbls)
    col = t.column(LEROBOT_STATE_COL).combine_chunks()
    list_size = int(col.type.list_size)
    storage_dtype = str(col.type.value_type)
    s32 = col.values.to_numpy(zero_copy_only=False).reshape(len(col), list_size).astype(np.float32, copy=False)
    # ② 上转无损：按位模式比（float32 ⊂ float64 ⇒ 理论上恒真，但**实测**才算证据）
    s64 = s32.astype(np.float64)
    upcast_ok = bool(np.all(s64.astype(np.float32).view(np.uint32) == s32.view(np.uint32)))

    d = t.to_pydict()
    ep = np.asarray(d["episode_index"], dtype=np.int64)
    fi = np.asarray(d["frame_index"], dtype=np.int64)
    gi = np.asarray(d["index"], dtype=np.int64)
    ti = np.asarray(d["task_index"], dtype=np.int64)
    uniq_eps = sorted(set(int(e) for e in ep.tolist()))

    # ① 分组 + 组内升序（裁定 85.4-2 的口径）。用稳定排序，并**记录原始顺序是否已经满足**。
    order = np.lexsort((fi, ep))                     # 主键 episode_index，次键 frame_index
    raw_order_ok = bool(np.array_equal(order, np.arange(order.size)))
    frames = s64[order]
    ep_sorted = ep[order]
    fi_sorted = fi[order]
    ti_sorted = ti[order]

    per_ep = {}
    gaps = []
    contiguous_all = True
    for e in uniq_eps:
        f_e = fi_sorted[ep_sorted == e]
        n = int(f_e.size)
        contig = bool(np.all(f_e == np.arange(n)))
        contiguous_all = contiguous_all and contig
        if not contig:
            gaps.append({"episode_index": e, "n_frames": n,
                         "frame_index_min": int(f_e.min()), "frame_index_max": int(f_e.max()),
                         "n_missing_in_range": int(f_e.max() - f_e.min() + 1 - n)})
        per_ep[e] = {"n_frames": n, "frame_index_min": int(f_e.min()), "frame_index_max": int(f_e.max()),
                     "frame_index_contiguous_from_0": contig,
                     "task_index_set": sorted(set(int(x) for x in ti_sorted[ep_sorted == e].tolist()))}
    start_mask = fi_sorted == 0
    start_poses = frames[start_mask]
    n_start_from_fi0 = int(start_mask.sum())
    # 每集必须恰好一个 frame_index==0（否则 start_poses 与集数不对应 ⇒ 响亮报，不静默取第一个）
    eps_with_fi0 = sorted(set(int(e) for e in ep_sorted[start_mask].tolist()))

    return {
        "frames": frames, "frames_f32_as_stored": s32[order], "start_poses": start_poses,
        "episode_index_sorted": ep_sorted, "frame_index_sorted": fi_sorted,
        "uniq_episodes": uniq_eps, "n_episodes": len(uniq_eps), "n_frames": int(frames.shape[0]),
        "state_dim": list_size, "parquet_storage_dtype": storage_dtype,
        "upcast_bitwise_lossless": upcast_ok,
        "raw_order_already_grouped_sorted": raw_order_ok,
        "reorder_was_material": (not raw_order_ok),
        "sort_key": "np.lexsort((frame_index, episode_index))  # 主键集号、次键集内帧号，稳定",
        "frame_index_contiguous_per_episode": contiguous_all,
        "n_frame_index_gaps": len(gaps), "frame_index_gaps": gaps,
        "per_episode": per_ep,
        "start_pose_extraction": {
            "rule": "每集 frame_index == 0（裁定 85.4-2）",
            "n_start_poses": n_start_from_fi0, "n_episodes": len(uniq_eps),
            "one_per_episode": bool(n_start_from_fi0 == len(uniq_eps)),
            "episodes_with_frame_index_0": eps_with_fi0,
            "start_poses_abs_max": (float(np.abs(start_poses).max()) if start_poses.size else None)},
        "index_column_is_global_arange": bool(np.all(gi == np.arange(gi.size))),
        "dtype_declaration": dict(DTYPE_DECLARATION),
        "parquet_files": [{"path": rel(f),
                           "sha256_12": sha12(f), "mtime": mtime_iso(f),
                           "n_rows": int(pq.read_metadata(f).num_rows), "bytes": f.stat().st_size}
                          for f in files],
        "stray_parquet_outside_chunk_glob": [str(x.relative_to(ROOT)) for x in stray],
        "columns_read": list(LEROBOT_COLS),
        "task_index_per_episode": {str(e): per_ep[e]["task_index_set"] for e in uniq_eps},
    }


def direction_from_two_sources(res: dict, lf: dict, man: dict) -> dict:
    """每集的方向码：**两条独立来源**互核（不采信单一来源）。

    来源 A = `demo_manifest.json` 的 `episodes[*].task_text` → `direction` 映射，
             经 `meta/tasks.parquet` 的 `task_index` → task_text 落到每集；
    来源 B = B2 npz 的 `direction_code`（**若存在**；D 已撤销该导出任务 ⇒ formal 期不会有）。
    两者不一致 ⇒ `agree=false`，**响亮报**，不静默取其一（裁定 82.6 的同源纪律）。
    为什么方向码要紧：主线档的 build/eval 划分是**按方向各留最后一整集**，方向错 ⇒ 划分错 ⇒
    held-out 牙（Td2/Te2）判的是错的东西。
    """
    lr = res["lerobot_dir"]
    out = {"sources": [], "agree": None, "ep_dir": {}, "n_episodes": lf["n_episodes"]}
    ep_dir_a = {}
    tasks_p = lr / "meta" / "tasks.parquet"
    if tasks_p.exists() and man.get("episodes"):
        import pyarrow.parquet as pq
        tt = pq.read_table(tasks_p).to_pydict()
        idx_key = "task_index" if "task_index" in tt else ("__index_level_0__" if "__index_level_0__" in tt else None)
        text_key = None
        for k in tt:
            if k != idx_key:
                text_key = k
                break
        if idx_key is not None and text_key is not None:
            idx2text = {int(i): str(x) for i, x in zip(tt[idx_key], tt[text_key])}
            text2dir = {}
            for e in man["episodes"]:
                if e.get("task_text") and e.get("direction"):
                    text2dir.setdefault(str(e["task_text"]), str(e["direction"]))
            amb = [t for t, ds in
                   {t: sorted({d for tt2, d in text2dir.items() if tt2 == t}) for t in text2dir}.items() if len(ds) > 1]
            for ep_i, tis in lf["task_index_per_episode"].items():
                dirs = sorted({text2dir.get(idx2text.get(int(x), ""), "<unknown>") for x in tis})
                ep_dir_a[int(ep_i)] = dirs[0] if len(dirs) == 1 else "<ambiguous>"
            out["sources"].append({
                "id": "A_demo_manifest_task_text_via_tasks_parquet",
                "tasks_parquet": rel(tasks_p), "tasks_parquet_sha256_12": sha12(tasks_p),
                "idx_key": idx_key, "text_key": text_key,
                "n_task_index_values": len(idx2text),
                "task_text_to_direction": text2dir,
                "directions_ambiguous_for_same_task_text": amb,
                "n_episodes_mapped": len(ep_dir_a),
                "n_episodes_unmapped": sum(1 for v in ep_dir_a.values() if v.startswith("<"))})
    # 方向名 → 方向码（稳定：按 manifest 的 `directions` 声明顺序，不按出现顺序）
    declared_dirs = list(man.get("directions") or [])
    dir_names = declared_dirs or sorted({v for v in ep_dir_a.values() if not v.startswith("<")})
    name2code = {n: i for i, n in enumerate(dir_names)}
    ep_dir = {e: name2code.get(v, -1) for e, v in ep_dir_a.items()}
    out["ep_dir"] = {str(k): v for k, v in sorted(ep_dir.items())}
    out["direction_names"] = dir_names
    out["direction_name_to_code"] = name2code
    out["n_episodes_with_unknown_direction"] = sum(1 for v in ep_dir.values() if v < 0)
    out["per_direction_episode_counts"] = {str(c): sum(1 for v in ep_dir.values() if v == c)
                                           for c in sorted(set(ep_dir.values()))}
    # 来源 B：B2 npz 的 direction_code（可选）
    out["cross_check_vs_b2_npz"] = None
    return out


def crosscheck_direction_vs_npz(dc_rec: dict, npz_path: Path | None) -> dict:
    """来源 B 的互核：B2 npz 的 `direction_code`（按集）vs 本脚本从 manifest+tasks.parquet 推的方向码。"""
    if npz_path is None or not Path(npz_path).exists():
        return {"present": False, "why": "B2 npz 不在（D 已撤销该导出任务，裁定 85.4-2-1）⇒ 只有来源 A"}
    z = np.load(npz_path, allow_pickle=False)
    if "direction_code" not in z.files:
        return {"present": False, "why": f"{npz_path.name} 无 direction_code 键", "npz_keys": sorted(z.files)}
    b = [int(x) for x in np.asarray(z["direction_code"]).tolist()]
    a = [dc_rec["ep_dir"][str(k)] for k in sorted(int(x) for x in dc_rec["ep_dir"])]
    return {"present": True, "npz": rel(npz_path), "npz_sha256_12": sha12(npz_path),
            "from_manifest_tasks_parquet": a, "from_b2_npz": b,
            "len_equal": len(a) == len(b),
            "agree": bool(len(a) == len(b) and all(x == y for x, y in zip(a, b))),
            "n_disagree": (sum(1 for x, y in zip(a, b) if x != y) if len(a) == len(b) else None)}


def crosscheck_frames_vs_npz(lf: dict, npz_path: Path | None) -> dict:
    """我的 parquet 读取器 vs B2 的 npz：**逐位**比（两边都是 float64，可比）。

    ⚠ 诚实声明：B2 的导出器（`scripts/b2_export_states_14d.py:23-24`）**也**是读同一份 parquet
    ⇒ 这**不是独立来源**的互核。它的价值是**另一件事**：证明我的
    「按 episode_index 分组 + 组内 frame_index 升序」拼接与 B2 的实现给出**同一个帧序**。
    帧序错 ⇒ 逐步差分 MAD（F2 下限族的输入）与 held-out 划分都会静默偏掉，
    而 stats 的 q01/q99 对顺序不敏感 ⇒ **只有逐位比帧序才看得见这类缺陷**。
    """
    if npz_path is None or not Path(npz_path).exists():
        return {"present": False, "why": "B2 npz 不在 ⇒ 无同序互核对象（formal 期就是这种情形）",
                "independence": "n_a"}
    z = np.load(npz_path, allow_pickle=False)
    if "frames" not in z.files:
        return {"present": False, "why": "npz 无 frames 键", "npz_keys": sorted(z.files)}
    b = np.asarray(z["frames"], dtype=np.float64)
    a = lf["frames"]
    same_shape = (a.shape == b.shape)
    bitwise = bool(same_shape and np.all(a.view(np.uint64) == b.view(np.uint64)))
    return {"present": True, "npz": rel(npz_path), "npz_sha256_12": sha12(npz_path),
            "independence": ("**非独立来源**：B2 的导出器也读同一份 parquet（b2_export_states_14d.py:23-24）"
                             "⇒ 本互核证明的是**帧序/分组一致**，不是数据正确性"),
            "what_it_does_prove": ("我的 lexsort 拼接与 B2 的实现给出同一帧序；帧序错会静默偏掉 "
                                   "F2 下限族的 noise_MAD 与按集 held-out 划分，而 q01/q99 对顺序不敏感"),
            "compare_dtype": "两边都是 float64（float32 上转而来）⇒ 逐位可比（裁定 85.4-2 的 dtype 口径）",
            "shape_mine": list(a.shape), "shape_npz": list(b.shape), "same_shape": same_shape,
            "bitwise_equal": bitwise,
            "max_abs_diff": (float(np.abs(a - b).max()) if same_shape else None),
            "n_diff_elements": (int(np.count_nonzero(a != b)) if same_shape else None),
            "episode_index_also_compared": None}


def crosscheck_episodes_vs_npz(lf: dict, npz_path: Path | None) -> dict:
    """`episode_index` 逐元素比（帧序一致的**另一半**证据：frames 相同但集号错也会毁掉按集划分）。"""
    if npz_path is None or not Path(npz_path).exists():
        return {"present": False, "why": "B2 npz 不在"}
    z = np.load(npz_path, allow_pickle=False)
    if "episode_index" not in z.files:
        return {"present": False, "why": "npz 无 episode_index 键"}
    b = np.asarray(z["episode_index"], dtype=np.int64)
    a = np.asarray(lf["episode_index_sorted"], dtype=np.int64)
    same = (a.shape == b.shape)
    return {"present": True, "same_shape": same,
            "identical": bool(same and np.array_equal(a, b)),
            "n_diff": (int(np.count_nonzero(a != b)) if same else None),
            "n_episodes_mine": lf["n_episodes"]}


def auto_stats_provenance_lerobot(res: dict, man: dict, lf: dict, dc: dict) -> tuple[str, str]:
    """数据集身份 → 溯源标签（**交叉核对臂**；裁定 90.4-4）。**分类不了就不给可用标签**（宁可红，不可假绿）。

    * `stage == "pilot"`  ⇒ `pilot10_path_check`（**不得进 BC**）；
    * `stage == "formal"` ⇒ **`formal40_lerobot_crosscheck`**（裁定 90.4-4：本读路径是**交叉核对臂**，
      结构上不得产 BC 档标签）；集数与每方向集数仍然**必须**核（`n_generated_per_direction ×
      len(directions)`），核不上 ⇒ 退回 `unclassified_not_for_bc`（= 红）—— 交叉核对臂也要能证明
      自己读的是同一批 formal-40，否则"逐位等价"这句话就没有对象；
    * 其它 ⇒ `unclassified_not_for_bc`（**故意不在** `nc.KNOWN_STATS_PROVENANCES` 里 ⇒ 牙 Tp4 必红）。

    ⚠ 修前本函数在 `stage == "formal"` 时返回 `nc.STATS_PROVENANCE_FORMAL40_BC`，与 npz 侧的
    `auto_stats_provenance` **产同一个标签** ⇒ 正是裁定 90.4-4 点名要挡的形态（「两个读取器产出
    同一个 provenance 标签 = 无法回答『BC 到底吃了哪一份』」）。BC 档标签现在**只**由 npz 侧产。
    """
    stage = man.get("stage")
    n_eps = lf["n_episodes"]
    dirs = list(man.get("directions") or [])
    per_dir = (man.get("n_generated_per_direction"))
    counts = dc.get("per_direction_episode_counts") or {}
    ident = (f"stage={stage} n_episodes={n_eps} directions={dirs} "
             f"n_generated_per_direction={per_dir} per_direction_counts={counts}")
    if stage == "pilot":
        return (nc.STATS_PROVENANCE_PILOT10_PATH_CHECK,
                f"demo_manifest.stage='pilot' ⇒ 通路验证档（裁定 85.4-3：用途限定三项，**不得进 BC**）。{ident}"
                f"｜标签字面按裁定 87.4：正典 = `pre_pilot5_path_check`，本值 `pilot10_path_check` 是其"
                f"**别名**（裁定 86.1 的字面被撤回为别名；D 原文『非 BC 标签的字面不承载判据，"
                f"不值得为此改产物』）⇒ 产物同时落 `stats_provenance_canonical` 把关系机器化")
    if stage == "formal":
        expect_total = None
        if isinstance(per_dir, int) and dirs:
            expect_total = per_dir * len(dirs)
        counts_ok = bool(counts) and all(v == per_dir for v in counts.values()) if isinstance(per_dir, int) else False
        if expect_total is not None and n_eps == expect_total and counts_ok:
            return (nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK,
                    f"demo_manifest.stage='formal' 且集数自洽（{n_eps} == {per_dir} × {len(dirs)}，"
                    f"每方向集数实测一致）⇒ 本读路径确为 formal-40 的**交叉核对臂**。"
                    f"标签 = `formal40_lerobot_crosscheck`（裁定 90.4-4：它在 "
                    f"`nc.KNOWN_STATS_PROVENANCES` 里但**不在** `nc.BC_ADMISSIBLE_PROVENANCES` 里 "
                    f"⇒ 牙 Tp4 绿、牙 Tp5 对 `consumer=bc` 必红 ⇒ BC 硬闸在**结构上**吃不到本臂）。"
                    f"权威接口 = npz + `--s1-frames`（裁定 86.0/86.1/90.4-4）。{ident}")
        return ("unclassified_not_for_bc",
                f"stage='formal' 但集数核不上（期望 {expect_total}，实到 {n_eps}；每方向一致={counts_ok}）"
                f"⇒ **拒绝**给可用标签（宁可红，不可假绿）；交叉核对臂也必须先证明自己读的是 formal-40。{ident}")
    return ("unclassified_not_for_bc",
            f"demo_manifest.stage={stage!r} 既不是 'pilot' 也不是 'formal' ⇒ 无法判定数据集身份，"
            f"拒绝给可用标签（该值**不在** nc.KNOWN_STATS_PROVENANCES 里 ⇒ 牙 Tp4 必红）。{ident}")


def resolve_physical_range_lerobot(args, frames: np.ndarray) -> tuple[np.ndarray, list, dict]:
    """主线（lerobot 直读）档的分母出处：**规则可搬、实测值不可搬**（裁定 71）。

    declared = 勘误件的 `physical_range`（= jnt_range 经 upstream 归一化换算的**声明行程**，
               模型属性 ⇒ 与数据集无关 ⇒ 可搬；夹爪维 = 0.91001 不是 1.0）；
    observed = **本数据集** frames 的逐维 max−min（同源实测）；
    effective = max(declared, observed)。
    ⚠ **不取**勘误件的 `physical_range_effective`：那一份的 observed 来自 C2 的 env 诊断档
      （random/sweep/hold）⇒ 搬到 B2 的示范帧上就是裁定 71 禁止的**跨口径移植**。
    ctrlrange 区间取勘误件的 `physical_interval`（同样是声明 jnt_range 换算 ⇒ 模型属性 ⇒ 可搬），
    供牙 `Tw_ctrlrange_coverage` **记录**覆盖率（裁定 51.1：不判红）。
    """
    jp = Path(args.physical_range_json)
    jp = jp if jp.is_absolute() else (ROOT / jp).absolute()
    if not jp.exists():
        raise SystemExit(f"[RED] 物理行程勘误件不在：{jp}（主线档拒绝用 npz 里的旧 physical_range 顶替）")
    d = json.loads(jp.read_text(encoding="utf-8"))
    declared = np.asarray(d["physical_range"], dtype=np.float64)
    iv = d.get("physical_interval") or {}
    interval = ([np.asarray(iv["lo"], dtype=np.float64), np.asarray(iv["hi"], dtype=np.float64)]
                if ("lo" in iv and "hi" in iv) else None)
    observed = frames.max(axis=0) - frames.min(axis=0)
    effective = np.maximum(declared, observed)
    prov = {
        "basis": "max(声明行程[模型属性，可搬], **同源**实测行程[本数据集])",
        "rule": d.get("physical_range_effective_rule"),
        "source_of_declared": rel(jp),
        "sha256_12_of_declared_source": sha12(jp),
        "declared_jnt_travel": declared.tolist(),
        "observed_travel_this_dataset": observed.tolist(),
        "effective": effective.tolist(),
        "effective_binding_side": {int(i): ("observed_travel" if observed[i] > declared[i] + 1e-12
                                            else "declared_jnt_range") for i in range(declared.size)},
        "dims_where_observed_exceeds_declared": [int(i) for i in np.nonzero(observed > declared + 1e-12)[0]],
        "superseded_defect": False,
        "caliber_rule": ("规则可搬、实测值不可搬（裁定 71 `caliber_transplant_ban_scope`）："
                         "声明行程是**模型属性**（jnt_range 经 upstream 归一化换算）⇒ 可搬；"
                         "勘误件里的 `physical_range_effective` 含 env 诊断档的实测行程 ⇒ **不搬**，"
                         "本档只用它的 `physical_range`（声明）与 `physical_interval`（声明区间）"),
        "not_used_from_errata": ["physical_range_effective（含 env 档实测行程 ⇒ 跨口径）"],
        "ctrlrange_interval_basis": ("声明 jnt_range 经 upstream 归一化换算（模型属性）；"
                                     "覆盖率只作**记录**（裁定 51.1：示范不会用满行程，判红 = 极性错）"),
        "gripper_dims_caliber": {int(i): float(declared[i]) for i in (6, 13)},
        "gripper_caliber_note": ("实测夹爪行程 0.91001 不是 1.0（手指滑动关节 jnt_range=[0.021,0.057] "
                                 "经 upstream normalize_puppet_gripper_position 换算）；契约字面 1.0 与 "
                                 "『同 c2_collect_env_states.py 口径』两个半句互相矛盾 ⇒ "
                                 "B2 已登记 contract_conflict=OPEN_needs_d_ruling，**C2 不代改契约文本**"),
    }
    return effective, interval, prov


def sha12_bytes(b: bytes) -> str:
    """**内容** sha（不是文件 sha）：用于两条读路径的逐位等价判定（裁定 90.4-4 的口径）。"""
    return hashlib.sha256(b).hexdigest()[:12]


def iso_mtime(p) -> str:
    """文件 mtime 的 ISO 串（引用纪律 `citation_sha_as_of_discipline`：sha 必须带 as_of）。"""
    pp = Path(p)
    if not pp.exists():
        return "unavailable"
    return _dt.datetime.fromtimestamp(pp.stat().st_mtime).astimezone().replace(microsecond=0).isoformat()


def _count_per_direction(ep_dir: dict | None) -> dict | None:
    """`{集号: 方向码}` → `{方向码: 集数}`（**从数据数**，不采信 manifest 的自报）。"""
    if not ep_dir:
        return None
    out: dict[str, int] = {}
    for code in sorted({int(v) for v in ep_dir.values()}):
        out[str(code)] = sum(1 for v in ep_dir.values() if int(v) == code)
    return out


def resolve_physical_range_npz_mainline(args, frames: np.ndarray,
                                       npz_path: Path) -> tuple[np.ndarray, list, dict]:
    """**权威接口**（npz + `--s1-frames`，裁定 90.4-4）的分母与声明区间出处。

    规则与 `resolve_physical_range_lerobot` **同一份实现**（直接调它）：裁定 71
    `caliber_transplant_ban_scope` / 裁定 87.7 `rule_transplantable_value_not_transplantable`
    —— declared = 勘误件的 `physical_range`（jnt_range 经 upstream 归一化换算，**模型属性**⇒ 可搬）、
    observed = **本 npz 的 frames** 逐维 max−min（同源实测）、effective = max(declared, observed)、
    interval = 勘误件的 `physical_interval`（① 的覆盖目标）。
    ⚠ **不取**勘误件的 `physical_range_effective`（其 observed 来自 C2 的 env 诊断档 ⇒ 跨口径移植）。

    多做一件 lerobot 侧做不到的事：B2 的导出器**自己也**按同一规则写了 `physical_range_effective`
    （`scripts/b2_export_states_14d.py:422` 的 rule 串）⇒ 这里把两份并排比。规则同源、数据同源
    ⇒ 应当**逐位**一致；不一致就是发现（要么 B2 的 rule 串与实现分叉，要么我的 observed 口径不同），
    必须落盘、**不静默取其一**（`s1_npz_crosscheck` 的 `denominator_used_equals_npz_effective` 也判这件事）。
    """
    effective, interval, prov = resolve_physical_range_lerobot(args, frames)
    z = np.load(npz_path, allow_pickle=False)
    b2_eff = (np.asarray(z["physical_range_effective"], dtype=np.float64)
              if "physical_range_effective" in z.files else None)
    if b2_eff is None:
        xchk = {"present": False,
                "why": "npz 无 `physical_range_effective` 键 ⇒ 无比对对象（三态：**没测**，不是『测到一致』）"}
    else:
        d = np.abs(b2_eff - effective)
        rel_d = d / np.maximum(np.abs(effective), 1e-12)
        xchk = {"present": True,
                "b2_effective": b2_eff.tolist(), "c2_effective": effective.tolist(),
                "abs_diff": d.tolist(), "max_rel_diff": float(rel_d.max()),
                "bitwise_equal": bool(np.array_equal(b2_eff, effective)),
                "agree_within_1e_9": bool(rel_d.max() <= 1e-9),
                "dims_disagree_over_1e_9": sorted(int(i) for i in np.nonzero(rel_d > 1e-9)[0]),
                "what_it_proves": ("两个**独立实现**（B2 的导出器 / C2 的生成器）用同一条规则在同一批帧上"
                                   "得到同一个分母 ⇒ 分母不是某一侧的私货"),
                "what_it_does_not_prove": ("规则本身对不对（那由裁定 71/87.6 的口径与勘误件承担），"
                                           "也不证明 frames 的数值正确（那在 B2 的 19 道闸里）")}
    prov = {**prov,
            "reader": "--s1-frames（npz = 权威接口，裁定 90.4-4）",
            "npz": rel(npz_path), "npz_sha256_12": sha12(npz_path),
            "b2_npz_effective_crosscheck": xchk}
    return effective, interval, prov


def crosscheck_npz_vs_lerobot(fr_npz, ep_npz, lr_frames, lr_ep_sorted,
                              npz_content_sha: str | None = None) -> dict:
    """裁定 90.4-4 的**读路径互核**：权威接口（npz）与交叉核对臂（parquet）是否同一批帧。

    三态：交叉核对臂没跑 ⇒ `comparison_status="not_compared_arm_absent"`（**不**读成"一致"）。
    比的是：形状、float64 位模式、**内容 sha**（与 D 在 90.4-4 里报的 `c9a72480fcb7` 同口径：
    `sha256(float64 C-contiguous bytes)[:12]`）、`episode_index` 逐元素。
    ⚠ 独立性限定（必须写进产物）：B2 的导出器也读同一份 parquet ⇒ 本互核证明的是
    **两条读路径拼出的帧序/集号一致**，不是数据本身的正确性。
    """
    if lr_frames is None:
        return {"comparison_status": "not_compared_arm_absent",
                "why": "本次运行没有跑 `--s1-lerobot`（交叉核对臂缺席）⇒ **没比**，不是『比过一致』",
                "npz_content_sha256_12": npz_content_sha}
    a = np.ascontiguousarray(np.atleast_2d(np.asarray(fr_npz, dtype=np.float64)))
    b = np.ascontiguousarray(np.atleast_2d(np.asarray(lr_frames, dtype=np.float64)))
    same_shape = (a.shape == b.shape)
    bitwise = bool(same_shape and np.all(a.view(np.uint64) == b.view(np.uint64)))
    sha_b = sha12_bytes(b.tobytes())
    ep_a = (np.asarray(ep_npz, dtype=np.int64) if ep_npz is not None else None)
    ep_b = (np.asarray(lr_ep_sorted, dtype=np.int64) if lr_ep_sorted is not None else None)
    ep_same = (bool(ep_a is not None and ep_b is not None and ep_a.shape == ep_b.shape
                    and np.array_equal(ep_a, ep_b)))
    return {"comparison_status": "compared",
            "shape_npz": list(a.shape), "shape_lerobot": list(b.shape), "same_shape": same_shape,
            "bitwise_equal": bitwise,
            "max_abs_diff": (float(np.abs(a - b).max()) if same_shape else None),
            "n_diff_elements": (int(np.count_nonzero(a != b)) if same_shape else None),
            "content_sha256_12_npz": npz_content_sha, "content_sha256_12_lerobot": sha_b,
            "content_sha_equal": bool(npz_content_sha is not None and npz_content_sha == sha_b),
            "episode_index_equal": ep_same,
            "episode_index_compared": bool(ep_a is not None and ep_b is not None),
            "authority": ("裁定 90.4-4：D 亲测 `np.array_equal=True`、`max_abs_diff=0.0`、双方 content sha "
                          "均 `c9a72480fcb7` ⇒ 本函数是 C2 侧的**独立复算**，不是引用 D 的结论"),
            "independence": ("**非独立来源**：B2 的导出器也读同一份 parquet（`b2_export_states_14d.py:23-24`）"
                             "⇒ 证明的是帧序/集号一致，不是数据正确性")}


def split_heldout_by_episode_arrays(frames: np.ndarray, ep: np.ndarray,
                                    ep_dir: dict | None) -> tuple[np.ndarray, np.ndarray, dict]:
    """按集切 build/eval：**每个方向留出最后一整集**。与 npz 版同一份实现（不各写一份）。"""
    ep = np.asarray(ep, dtype=np.int64)
    if ep.size != frames.shape[0]:
        return frames, frames, {"held_out": False,
                                "why": f"episode_index 长度 {ep.size} != frames {frames.shape[0]}"}
    uniq_eps = sorted(set(int(e) for e in ep.tolist()))
    if ep_dir is None:
        return frames, frames, {"held_out": False, "why": "无方向码 ⇒ 无法按方向各留一集；不假装切过"}
    if len(ep_dir) != len(uniq_eps):
        return frames, frames, {"held_out": False,
                                "why": f"方向码覆盖 {len(ep_dir)} 集 != 实测集数 {len(uniq_eps)} ⇒ 拒绝猜"}
    hold_eps = []
    for code in sorted(set(ep_dir.values())):
        eps_in_dir = sorted(e for e, c in ep_dir.items() if c == code)
        if len(eps_in_dir) >= 2:
            hold_eps.append(eps_in_dir[-1])
    if not hold_eps:
        return frames, frames, {"held_out": False, "why": "每个方向的集数 < 2 ⇒ 留不出整集"}
    mask = np.isin(ep, hold_eps)
    return (frames[~mask], frames[mask],
            {"held_out": True, "rule": "按集切：每个方向的最后一整集留出作 eval",
             "held_out_episodes": [int(e) for e in hold_eps],
             "n_episodes_total": len(uniq_eps),
             "episode_to_direction": {str(k): v for k, v in sorted(ep_dir.items())},
             "n_build_frames": int((~mask).sum()), "n_eval_frames": int(mask.sum()),
             "leakage_note": "同一集的帧不会跨 build/eval（相邻帧近似重复 ⇒ 帧级随机切等于没切）"})


def auto_stats_provenance(man: dict, z=None, frames: np.ndarray | None = None) -> tuple[str, str]:
    """**权威接口**（npz + `--s1-frames`，裁定 90.4-4）的溯源标签。

    裁定 90.4-4 原文：「权威接口 = npz + `--s1-frames`。裁定 **86.0** 撤回 85.4-2（`--s1-lerobot`）；
    **86.1 末条**明写『B2 …落地后**同时导出 formal 版 npz**…**C2 用它重算 `formal40_bc_source`**』」，
    且「`--s1-lerobot` 保留为交叉核对臂，但其产物 `stats_provenance` 必须是
    `formal40_lerobot_crosscheck`，**不得是** `formal40_bc_source`」。
    ⇒ **只有本函数（npz 侧）可以产 BC 档标签**；`auto_stats_provenance_lerobot` 结构上产不出来。

    修前本函数只认 `is_pilot5` / `formal_collection_pending` 两个标志 ⇒ B2 的 formal-40 npz
    两个都是 `false`，会落到 `unclassified_not_for_bc`（B2 在交接单 §2 里点名这是一条**假红**）。
    现在按 B2 导出器**实际写进 manifest 的字段**判级（每个判据都是机器读的，不采信散文）：
      ① `source_dataset.stage == "formal"`；② `is_pilot5 == false` 且 `formal_collection_pending == false`；
      ③ `not_for_mainline_normalizer == false`；④ 集数自洽：`source_dataset.n_episodes ==
      n_per_direction × len(directions)`；⑤ **每方向集数由 C2 自己从 npz 数组数**（`direction_code`
      按集、`episode_index` 按帧），不采信 manifest 的自报；⑥ B2 导出器自己声明的前置
      `source_dataset.gates_verdict == "PASS"` 且 `gates_n_red == 0`；⑦ `schema.frames.shape`
      与实际 `frames` 一致。任一不满足 ⇒ `unclassified_not_for_bc`（**故意**不在
      `nc.KNOWN_STATS_PROVENANCES` 里 ⇒ 牙 Tp4 必红；宁可红，不可假绿）。
    """
    sd = (man.get("source_dataset") or {})
    stage = sd.get("stage")
    n_eps_declared = sd.get("n_episodes")
    n_per_dir = sd.get("n_per_direction")
    dirs = list(sd.get("directions") or [])
    gates_verdict = sd.get("gates_verdict")
    gates_n_red = sd.get("gates_n_red")
    # ⑤ 每方向集数：**从数组数**（`direction_code` 长度 = 集数，`episode_index` 长度 = 帧数 ⇒ 不可 zip）
    per_dir_measured: dict[str, int] | None = None
    n_eps_measured = None
    shape_ok = None
    if z is not None:
        try:
            if "episode_index" in z.files:
                ep = np.asarray(z["episode_index"]).astype(np.int64)
                uniq = sorted(set(int(e) for e in ep.tolist()))
                n_eps_measured = len(uniq)
                if "direction_code" in z.files:
                    dc = np.asarray(z["direction_code"]).astype(np.int64)
                    if dc.size == len(uniq):
                        ep_dir = dict(zip(uniq, (int(c) for c in dc.tolist())))
                        per_dir_measured = {str(c): sum(1 for v in ep_dir.values() if v == c)
                                            for c in sorted(set(ep_dir.values()))}
                    else:
                        per_dir_measured = {"__mismatch__": {
                            "direction_code_len": int(dc.size), "n_episodes": len(uniq),
                            "why": "长度不符 ⇒ 无法确定 direction_code 是按集还是按帧给的，拒绝猜"}}
            if frames is not None and "frames" in z.files:
                shape_ok = bool(np.asarray(z["frames"]).shape == np.atleast_2d(frames).shape)
        except Exception as exc:                                   # noqa: BLE001
            per_dir_measured = {"__error__": repr(exc)[:200]}
    ident = (f"stage={stage} n_episodes(declared)={n_eps_declared} n_episodes(measured)={n_eps_measured} "
             f"n_per_direction={n_per_dir} directions={dirs} per_direction_measured={per_dir_measured} "
             f"gates_verdict={gates_verdict} gates_n_red={gates_n_red} "
             f"is_pilot5={man.get('is_pilot5')} formal_collection_pending={man.get('formal_collection_pending')} "
             f"not_for_mainline_normalizer={man.get('not_for_mainline_normalizer')} frames_shape_ok={shape_ok}")
    if man.get("formal_collection_pending") or man.get("is_pilot5"):
        return (nc.STATS_PROVENANCE_PILOT10_PATH_CHECK,
                f"manifest.is_pilot5={man.get('is_pilot5')} / formal_collection_pending="
                f"{man.get('formal_collection_pending')} ⇒ 通路验证档（裁定 85.4-3），不进 BC。"
                f"标签字面口径按裁定 87.4：正典 = `pre_pilot5_path_check`，本档写的 "
                f"`pilot10_path_check` 是它的**别名**（裁定 86.1 的字面被撤回为别名；"
                f"D 原文『非 BC 标签的字面不承载判据，不值得为此改产物』）⇒ 产物同时落 "
                f"`stats_provenance_canonical` 把关系机器化｜{ident}")
    checks = {
        "stage_is_formal": stage == "formal",
        "not_pilot_flags": (man.get("is_pilot5") is False and man.get("formal_collection_pending") is False),
        "not_marked_not_for_mainline": man.get("not_for_mainline_normalizer") is False,
        "episode_count_self_consistent": (isinstance(n_per_dir, int) and bool(dirs)
                                          and n_eps_declared == n_per_dir * len(dirs)),
        "per_direction_measured_consistent": (isinstance(per_dir_measured, dict)
                                              and bool(per_dir_measured)
                                              and all(v == n_per_dir for v in per_dir_measured.values())
                                              and len(per_dir_measured) == len(dirs)),
        "n_episodes_measured_matches_declared": (n_eps_measured is not None
                                                 and n_eps_measured == n_eps_declared),
        "b2_gates_pass": (gates_verdict == "PASS" and gates_n_red == 0),
        "frames_shape_matches_schema": (shape_ok is not False),
    }
    failed = sorted(k for k, v in checks.items() if not v)
    if not failed:
        return (nc.STATS_PROVENANCE_FORMAL40_BC,
                f"npz 权威接口（裁定 90.4-4）：8 项机器判据全过 ⇒ 可作 BC 同源 stats。判据={checks}｜{ident}")
    return ("unclassified_not_for_bc",
            f"npz 权威接口：判据未全过 ⇒ **拒绝**标 formal40_bc_source（宁可红，不可假绿）。"
            f"未过项={failed} 判据={checks}｜{ident}")


def build_case(*, frames, base_stats, prange, case, family, coef, source, rep_version, prov,
               must_cover=(), widen=True, stats_provenance=None, consumer=None,
               coverage_target=None, physical_interval=None, start_pose=None,
               interval_source_sha256_12=None) -> dict:
    """构造一档 stats。**覆盖集不由调用方拼**：给了 `coverage_target` 就走
    `nc.coverage_must_cover()`（裁定 87.3-1 的 ①／对照口径都在那一份实现里），
    没给才用 `must_cover`（历史调用面，产物里 `coverage_target=null` 会显式暴露这件事）。
    """
    fam = nc.floor_family(family, coef)
    noise = np.asarray(base_stats["noise_mad_step"], dtype=np.float64)
    floors = fam.floors(physical_range=prange, noise=noise)
    st = dict(base_stats)
    st["physical_range"] = prange
    cov_rec = None
    cover_cap = None
    if coverage_target is not None:
        cov_rec = nc.coverage_must_cover(target=coverage_target, frames=frames,
                                         start_pose=start_pose, physical_interval=physical_interval)
        must_cover = cov_rec["must_cover"]
        cover_cap = cov_rec["cover_cap"]
    # 顺序 = **先下限、后覆盖**（实测教训：反过来时 `apply_scale_floor` 围绕 median 对称展宽，
    # 会把刚覆盖进来的起态又甩到 [-1,1] 外 ⇒ 牙 Tc/Te 恒红，且红的原因是实现顺序而不是数据）。
    if case == nc.CASE_QUANTILES_FLOOR:
        baked = nc.apply_scale_floor(base_stats, floors)
        st["q01"] = baked["q01"]; st["q99"] = baked["q99"]
        st["denom_raw"] = baked["denom_raw"]; st["denom_effective"] = baked["denom_effective"]
        st["floor"] = floors
    elif case == nc.CASE_IDENTITY_EXPLICIT:
        denom = np.maximum(np.asarray(base_stats["span_q99_q01"], dtype=np.float64), floors)
        st["center"] = np.asarray(base_stats["median"], dtype=np.float64)
        st["gain"] = 2.0 / denom
        st["floor"] = floors
        st["denom_raw"] = np.asarray(base_stats["span_q99_q01"], dtype=np.float64)
        st["denom_effective"] = denom
    else:
        raise nc.NormContractViolation(f"未知 case {case}")
    widened = None
    if widen and must_cover:
        if case == nc.CASE_QUANTILES_FLOOR:
            widened = nc.widen_to_cover(st, must_cover, cover_cap=cover_cap)
            st["q01"] = widened["q01"]; st["q99"] = widened["q99"]
            st["span_q99_q01"] = st["q99"] - st["q01"]
            st["denom_effective"] = st["q99"] - st["q01"]
        else:   # IDENTITY 分支：显式缩放的 center/gain 也要覆盖住 must_cover
            cov = np.concatenate([np.atleast_2d(np.asarray(m, dtype=np.float64)) for m in must_cover], 0)
            lo, hi = cov.min(0), cov.max(0)
            # 头寸与 `nc.widen_to_cover` 同口径（1 bin）：不留头寸时起态极值维归一化后正好 = ±1.0，
            # 与越界值落进同一个边界 bin（`processor_pi05.py:77`）。
            span = np.maximum(hi - lo, 1e-12)
            delta = HEADROOM_BINS * nc.BIN_WIDTH * span / 2.0
            cover_lo, cover_hi = lo - delta, hi + delta
            need = np.maximum(cover_hi - cover_lo, np.asarray(st["denom_effective"], dtype=np.float64))
            st["gain"] = 2.0 / need
            # 覆盖约束 `center - need/2 <= cover_lo` 且 `center + need/2 >= cover_hi`
            # ⇒ **可行 center 区间 = [cover_hi - need/2, cover_lo + need/2]**（need >= span ⇒ 恒非空）。
            # 修前写成 [lo + need/2, hi - need/2]（界序反了）：因 need >= span，该区间恒为空，
            # `np.clip` 在 a_min > a_max 时返回 a_max = hi - need/2 ⇒ 覆盖窗滑到 [hi-need, hi]，
            # 低端起态被甩出 -1（实测 Tc 恒红、越界维=[9]）。**是实现缺陷，不是契约红。**
            c_lo, c_hi = cover_hi - need / 2.0, cover_lo + need / 2.0
            st["center"] = np.clip(np.asarray(st["center"], dtype=np.float64), c_lo, c_hi)
            st["denom_effective"] = need
            # IDENTITY 档的"上限"判据（裁定 87.3-2 条件 c）：判**覆盖集**（lo/hi）有没有超出声明区间，
            # 与 QUANTILES 档同一口径（`nc.widen_to_cover` 里写了为什么不能判最终窗口：
            # 下限是围绕 median 对称烘的，中位数靠近限位的维会把窗口顶过区间，那是另一件事）。
            if cover_cap is None:
                cap_ok, cap_viol, beyond = None, [], None
            else:
                _cl = np.asarray(cover_cap[0], dtype=np.float64)
                _ch = np.asarray(cover_cap[1], dtype=np.float64)
                _tol = 1e-12 + 1e-9 * np.maximum(_ch - _cl, 0.0)
                cap_viol = sorted(int(i) for i in np.nonzero(
                    (lo < _cl - _tol) | (hi > _ch + _tol))[0])
                cap_ok = bool(not cap_viol)
                _wlo, _whi = st["center"] - need / 2.0, st["center"] + need / 2.0
                beyond = {"dims_low": sorted(int(i) for i in np.nonzero(_wlo < _cl - _tol)[0]),
                          "dims_high": sorted(int(i) for i in np.nonzero(_whi > _ch + _tol)[0]),
                          "amount_low": np.maximum(_cl - _wlo, 0.0).tolist(),
                          "amount_high": np.maximum(_whi - _ch, 0.0).tolist(),
                          "cause": ("下限烘入（denom = max(span, floor)）与 1 bin 头寸；**不是**为覆盖"
                                    "越界数据而展宽（覆盖集越界由 `cover_cap_violation_dims` 单独判）"),
                          "effect_on_teeth": ("窗口越过声明区间会让 `Tsat`/`Td1` 对**小幅**越界状态失声 ⇒ "
                                              "由 `Tiv_out_of_declared_interval_is_measured`（测量）与 "
                                              "`Tesc_no_covered_window_escape` / "
                                              "`Tlo_no_downside_coverage_deficit`（判据）独立量数据兜住"
                                              "（裁定 90.4-1 撤回极性前的旧牙名是 "
                                              "`Tiv_no_state_outside_declared_interval`）")}
            widened = {"n_widened": int((need > np.asarray(st["denom_raw"], dtype=np.float64)).sum()),
                       "widened_dims_low": [], "widened_dims_high": [],
                       "cover_min": lo, "cover_max": hi,
                       "headroom_bins": HEADROOM_BINS, "headroom_delta": delta,
                       "cover_cap": (None if cover_cap is None else
                                     {"lo": np.asarray(cover_cap[0]).tolist(),
                                      "hi": np.asarray(cover_cap[1]).tolist()}),
                       "cover_cap_respected": cap_ok,
                       "cover_cap_violation_dims": cap_viol,
                       "window_beyond_declared_interval": beyond,
                       "center_feasible_lo": c_lo, "center_feasible_hi": c_hi,
                       "center_feasible_interval_nonempty": bool(np.all(c_lo <= c_hi)),
                       "note": "IDENTITY 分支的覆盖通过 center/gain 实现（含 1 bin 头寸）"}
    payload = nc.stats_payload(stats=st, case=case, source=source, floors=floors, family=fam,
                              representation_version=rep_version, provenance=prov,
                              stats_provenance=stats_provenance, consumer=consumer,
                              coverage_target=coverage_target,
                              coverage={
                                  "target": coverage_target,
                                  "authority": (None if cov_rec is None else cov_rec["authority"]),
                                  "includes_build_frames": (None if cov_rec is None
                                                            else cov_rec["includes_build_frames"]),
                                  "n_cover_rows": (None if cov_rec is None else cov_rec["n_cover_rows"]),
                                  "headroom_bins": (None if widened is None else widened["headroom_bins"]),
                                  "n_widened": (None if widened is None else widened["n_widened"]),
                                  "cover_cap_respected": (None if widened is None
                                                          else widened.get("cover_cap_respected")),
                                  "cover_cap_violation_dims": (None if widened is None
                                                               else widened.get("cover_cap_violation_dims")),
                                  "window_beyond_declared_interval": (None if widened is None
                                                                      else widened.get("window_beyond_declared_interval")),
                                  "interval_source_sha256_12": interval_source_sha256_12,
                                  "note": (None if cov_rec is None else cov_rec["note"])})
    payload["widen_to_cover"] = (None if widened is None else {
        "n_widened": widened["n_widened"], "widened_dims_low": widened["widened_dims_low"],
        "widened_dims_high": widened["widened_dims_high"],
        "headroom_bins": widened["headroom_bins"],
        "cover_cap": widened.get("cover_cap"),
        "cover_cap_respected": widened.get("cover_cap_respected"),
        "cover_cap_violation_dims": widened.get("cover_cap_violation_dims"),
        "cover_min": np.asarray(widened["cover_min"]).tolist(),
        "cover_max": np.asarray(widened["cover_max"]).tolist()})
    return {"payload": payload, "stats": st, "floors": floors, "family": fam, "widened": widened,
            "coverage": cov_rec}


def summarize(rep: dict) -> dict:
    pd = rep["per_dim"]
    bins = [p["n_bins_occupied"] for p in pd]
    clips = [p["clip_ratio"] for p in pd]
    return {"n_frames": rep["n_frames"], "n_dims": rep["n_dims"],
            "bins_occupied_min": min(bins), "bins_occupied_median": float(np.median(bins)),
            "bins_occupied_max": max(bins),
            # 逐维 bins 与"低于阈值维"必须落盘：裁定 87.3-2 **条件 b** 要的是分辨率代价的
            # **实测登记**（D 本轮故意不定阈值），而中位数会把 dim3/dim10 的塌陷平均掉
            # （本轮实测：① 之后 median=36.0 看着还行、per-dim 最小 = 3）⇒ 只登记中位数 = 半个事实。
            "bins_occupied_per_dim": [int(x) for x in bins],
            "min_bins_occupied_threshold": nc.ContractThresholds().min_bins_occupied,
            "min_bins_occupied_threshold_status": nc.ContractThresholds().provenance["min_bins_occupied"],
            "dims_below_min_bins": [int(p["dim"]) for p in pd
                                    if p["n_bins_occupied"] < nc.ContractThresholds().min_bins_occupied],
            "clip_dims_over_cap": [int(p["dim"]) for p in pd
                                   if p["clip_ratio"] > nc.ContractThresholds().clip_ratio_cap],
            "illegal_bin_dims": [int(p["dim"]) for p in pd if p["illegal_bin_-1_present"]],
            "clip_ratio_max": max(clips), "clip_ratio_mean": float(np.mean(clips)),
            "n_dims_floor_binding": sum(1 for p in pd if p["floor_binding"]),
            "dims_floor_binding": [p["dim"] for p in pd if p["floor_binding"]],
            "n_dims_with_illegal_bin": sum(1 for p in pd if p["illegal_bin_-1_present"]),
            "saturation": rep["saturation"]}


# --------- 裁定 90.4-3 触发判据的**逐口径**读数（单一实现：行级与臂级共用） ---------
# 为什么必须有这个函数（本轮实测到的缺陷，不是理论洁癖）：
# 修前触发判据只吃 `row["summary"]`，而 `summary` 是在 **held-out 评估帧**上算的
# （formal-40：n=547）；D 在裁定 90.2 #16 / §18.6 引的 formal-40 读数
# （median 47.5 / min 3 / max 117 / below8=[3,10]）是**全量帧**（n=11035）口径。
# C2 只读探针实测（`runs/vla/c2_norm_contract_20260929/probe_trigger_caliber_20260930/`）：
#   held-out(n=547)          ⇒ 8/8 行触发（dims_below=[0,3,5,7,10,12]，其中 [0,5,7,12] 非近常量维）
#   build(n=10488)/all(n=11035) ⇒ 0/8 行触发（dims_below=[3,10]，都是已分类近常量维）
# ⇒ **同一条判据在两个口径下结论相反**。哪个口径「算」是 D 的裁量（判据文字归 D、
# `min_bins_occupied` 的状态是 `proposed_pending_s1`）⇒ C2 三个口径都量、都落盘、**不选边**。
# 这与裁定 92.6 的自查项同族：「凡取上一个/取典型值的地方，都问一句我取的这个量是不是我真正要指的那个」
# —— held-out 子集当全量、`main_rows[0]` 当整臂，是同一族的两处（后者由逐行聚合修掉）。
CALIBER_NAMES = ("heldout", "build", "all")
CALIBER_MEANING = {
    "heldout": "按集留出的评估帧（**牙 `Tb` 本身的测量口径** ⇒ 授权事实用它）",
    "build": "建 stats 用的帧（`summary_build` 的口径）",
    "all": "全量帧（build ∪ held-out；**D 在 90.2 #16 / §18.6 引数所用口径**）",
}
PROBE_TRIGGER_CALIBER_REL = ("runs/vla/c2_norm_contract_20260929/"
                             "probe_trigger_caliber_20260930/verdict.json")
# D 在裁定 90.2 #16 / §18.6 引的那组 formal-40 读数。**只作引用交叉核对，不参与任何判定**
# （裁定 87.7 `rule_transplantable_value_not_transplantable`：别的口径量出的数值不得当本档阈值用）。
D_QUOTED_90_2_16_READING = {"bins_occupied_median": 47.5, "bins_occupied_min": 3,
                            "bins_occupied_max": 117, "dims_below_min_bins": [3, 10],
                            "role": "citation_crosscheck_not_a_threshold",
                            "authority": "裁定 90.2 #16 + `rl_harness_supervision/d_handoff_to_c2_20260929.md` §18.6"}


def probe_citation(rel_path: str | None) -> dict:
    """旁证探针的引用身份：**此刻**重读（裁定 82.6：不得沿用早先 run 里的值）。缺失 ⇒ 三态。"""
    if rel_path is None:
        return {"measurement_status": "not_applicable",
                "note": "本块是**对照读数**（同一函数只喂第 0 行），不是独立测量 ⇒ 不引旁证探针"}
    pp = ROOT / rel_path
    if not pp.exists():
        return {"path": rel_path, "measurement_status": "not_measured",
                "note": ("探针件不在盘上 ⇒ 不作旁证引用（红线 "
                         "`absence_of_measurement_is_not_measurement_of_absence`）")}
    return {"path": rel_path, "measurement_status": "measured",
            "sha256_12": sha12(pp), "bytes": pp.stat().st_size,
            "n_lines": len(pp.read_text(encoding="utf-8").splitlines()),
            "as_of_mtime": iso_mtime(pp),
            "role": ("corroborating_probe_read_only：本函数自己重算全部读数，"
                     "**不依赖**探针的数值（探针只是同口径的第二次独立实现）")}


def trigger_caliber_readings(*, per_dim_by_caliber, n_frames_by_caliber, nc_dims, threshold,
                             row_ids=None, threshold_status=None,
                             probe_path=PROBE_TRIGGER_CALIBER_REL) -> dict:
    """裁定 90.4-3 触发判据：**逐口径 × 逐行**读数（不聚合掉行、不聚合掉口径）。

    `per_dim_by_caliber[caliber]` = 每行一份「逐维 bins_occupied」列表，或 `None`（该口径没测）。
    三态纪律：没测 ⇒ `measurement_status="not_measured"`、`triggered=None`，
    **不得**读成「测到了、没触发」（红线 `absence_of_measurement_is_not_measurement_of_absence`）。
    """
    nc_set = sorted(set(int(d) for d in (nc_dims or [])))
    nc_lookup = set(nc_set)
    ids = list(row_ids or [])
    calibers: dict[str, Any] = {}
    for cname in CALIBER_NAMES:
        pats = per_dim_by_caliber.get(cname)
        nf = n_frames_by_caliber.get(cname)
        if not pats or any((not p) for p in pats):
            calibers[cname] = {
                "measurement_status": "not_measured", "meaning": CALIBER_MEANING[cname],
                "n_frames": nf, "triggered": None,
                "n_rows_measured": (0 if not pats else sum(1 for p in pats if p)),
                "note": ("该口径没量到 ⇒ **不得**读成『量到了、没触发』"
                         "（红线 `absence_of_measurement_is_not_measurement_of_absence`）")}
            continue
        if not ids or len(ids) != len(pats):
            ids = [f"row{i}" for i in range(len(pats))]
        below = [sorted(int(d) for d, b in enumerate(p) if b < threshold) for p in pats]
        trig = [bool(sorted(set(b) - nc_lookup)) for b in below]
        meds = [float(np.median(p)) for p in pats]
        uniq: dict[tuple, list] = {}
        for i, pat in enumerate(pats):
            uniq.setdefault(tuple(int(x) for x in pat), []).append(ids[i])
        ndim = len(pats[0])
        differ = sorted({d for d in range(ndim) if len({int(p[d]) for p in pats}) > 1})
        dmatch = [{"row_id": ids[i],
                   "reproduces_d_quoted_90_2_16": bool(
                       abs(meds[i] - D_QUOTED_90_2_16_READING["bins_occupied_median"]) < 1e-9
                       and min(pats[i]) == D_QUOTED_90_2_16_READING["bins_occupied_min"]
                       and max(pats[i]) == D_QUOTED_90_2_16_READING["bins_occupied_max"]
                       and below[i] == D_QUOTED_90_2_16_READING["dims_below_min_bins"])}
                  for i in range(len(pats))]
        calibers[cname] = {
            "measurement_status": "measured", "meaning": CALIBER_MEANING[cname], "n_frames": nf,
            "n_rows": len(pats), "row_ids": ids,
            "bins_occupied_per_dim_per_row": [[int(x) for x in p] for p in pats],
            "n_distinct_per_dim_patterns": len(uniq),
            "distinct_patterns": [{"bins_occupied_per_dim": list(k), "row_ids": v}
                                  for k, v in uniq.items()],
            "dims_differing_across_rows": differ,
            "bins_occupied_min_per_row": [int(min(p)) for p in pats],
            "bins_occupied_median_per_row": meds,
            "bins_occupied_max_per_row": [int(max(p)) for p in pats],
            "dims_below_min_bins_per_row": below,
            "dims_below_min_bins_union": sorted({d for b in below for d in b}),
            "dims_below_not_near_constant_union": sorted({d for b in below for d in b} - nc_lookup),
            "trigger": {"n_rows_trigger": sum(1 for t in trig if t),
                        "any_row_trigger": any(trig), "all_rows_trigger": all(trig),
                        "per_row": trig,
                        "triggering_row_ids": [ids[i] for i, t in enumerate(trig) if t]},
            "triggered": any(trig),
            "triggered_on_every_row": all(trig),
            "reading_median_would_trigger": any(m < threshold for m in meds),
            "reading_per_dim_would_trigger": any(bool(b) for b in below),
            "d_quoted_90_2_16_crosscheck": dmatch,
        }
    measured = [c for c in CALIBER_NAMES if calibers[c]["measurement_status"] == "measured"]
    trigs = {c: calibers[c]["triggered"] for c in measured}
    caliber_dependent = (None if len(trigs) < 2 else bool(len(set(trigs.values())) > 1))
    if caliber_dependent:
        disposition = ("**口径依赖**（各口径结论不一致）⇒ C2 **不据此把 P1 升 P0**；"
                       "两个读数都在 `calibers` 里，由 D 定哪个口径算")
    elif trigs and all(v is True for v in trigs.values()):
        disposition = "**各已测口径一致触发** ⇒ 按裁定 90.4-3，P1 逐维覆盖升 P0（D 已预分析完毕）"
    elif trigs and all(v is False for v in trigs.values()):
        disposition = "**各已测口径一致未触发** ⇒ 逐维覆盖留在 P1（C2 不自行重构生成器）"
    else:
        disposition = ("**有口径未测** ⇒ 三态：不得读成『未触发』"
                       "（红线 `absence_of_measurement_is_not_measurement_of_absence`）")
    return {
        "trigger_text": ("裁定 90.4-3：P1 逐维覆盖升 P0 的条件之一 = 『`bins_occupied_min < 8` 的维"
                         "**不再是**已分类近常量维』"),
        "threshold": threshold,
        "threshold_status": threshold_status or nc.ContractThresholds().provenance["min_bins_occupied"],
        "near_constant_dims": nc_set,
        "calibers": calibers,
        "calibers_measured": measured,
        "triggered_heldout_caliber": trigs.get("heldout"),
        "triggered_build_caliber": trigs.get("build"),
        "triggered_all_caliber": trigs.get("all"),
        "caliber_dependent": caliber_dependent,
        "governing_caliber": "OPEN_question_to_d",
        "disposition": disposition,
        "triggered": (None if caliber_dependent or not trigs else next(iter(trigs.values()))),
        "triggered_field_semantics": ("`triggered` 只在**各已测口径一致**时给布尔值；口径分叉或口径缺失时为 "
                                      "`null` ⇒ 读者必须去看 `calibers`，不能只看这一个字段"
                                      "（修前它是单口径布尔值，把 held-out 子集读数当成了全量结论）"),
        "c2_does_not_self_decide": ("触发 = 把 P1 升 P0 = 改关键路径；判据文字是 D 写的、阈值状态是 "
                                    "`proposed_pending_s1`（红线 `redline_provenance_discipline`："
                                    "只有声明值支撑的不得作 blocking）⇒ **口径归 D 裁**，C2 只把两读数并排落盘"),
        "ask_d": ("裁定 90.4-3 的触发判据应以哪个帧口径为准：held-out 评估帧（牙 `Tb` 与行 `summary` "
                  "的现口径）、全量帧（D 在 90.2 #16 / §18.6 引数所用口径）、还是**两者都满足**才触发？"),
        "corroborating_probe": probe_citation(probe_path),
        "d_quoted_reading": D_QUOTED_90_2_16_READING,
        "ruling_90_2_16": ("裁定 90.2 #16：用 `median` 守逐维失效是 D 自记的第 16 号同型错误 ⇒ 新规则 "
                           "`a_per_dim_failure_mode_must_be_gated_by_a_per_dim_statistic`。"
                           "本块两种读法都给（`reading_median_would_trigger` / "
                           "`reading_per_dim_would_trigger`），**触发**按逐维形式判"),
    }


# --------- 主线臂"允许红的牙"= **由同一次运行的测量派生**（不是写死的清单） ---------
# 为什么改（裁定 87.3-2 条件 b/c，与 87.2-1 缺陷 10 同族教训）：
# 修前是一份**手写常量** `ALLOWED_MAINLINE_RED`（held-out 家族 + F2 的 Tr3）。它在 pilot-10 上是对的，
# 但形式上是"先看到红、再把红的牙写进允许清单"⇒ 换一批数据（formal-40）就可能退化成**红洗白器**：
# 任何新红只要落在那三个 id 里就被解释掉。改成派生后，每把被允许红的牙都必须由**独立测量事实**授权，
# 且它点名的维必须落在授权事实的维集合**之内**（子集检查），否则算"无法解释的红"。
TOOTH_AUTHORIZED_BY_FACT = {
    # 事实 A = 数据超出声明物理区间（`nc.declared_interval_conformance`）。
    # ⚠ 裁定 90.4-1 之后 A **只是测量**：它不再授权任何"越界即红"的牙（那把牙已撤），
    # 但对 clip/饱和族的红它仍是**成因之一**（窗口被 `cover_cap` 钉在声明区间上 ⇒ 越界数据会被裁）。
    "Td1_clip_build_frames": ("A",),
    "Te1_no_illegal_bin_build": ("A",),
    # 事实 A ∪ B（B = held-out 帧落在 build **原始**分位窗之外的维 = 覆盖率缺口）
    "Td2_clip_heldout": ("A", "B"),
    "Te2_no_illegal_bin_heldout": ("A", "B"),
    "Tsat_saturation_dims_zero": ("A", "B"),
    # 事实 C = 逐维合法 bin 占用 < `min_bins_occupied`（条件 b 的分辨率代价）
    # ⚠ 裁定 **93.1-1** 之后这两把牙是 **非 blocking（WARN）**，结构上进不了 `red_ids` ⇒
    #   本表**故意不再登记**它们（修前登记的是 `"Tb_scale_floor_effective": ("C",)` 与
    #   `"Tr3_near_constant_floor_material": ("D",)`）。理由与下面 `Tiv`/`Tovr` 那条绊线同族：
    #   若哪天有人把 `blocking` 改回 True（= 撤回裁定 93.1 而未经 D 裁），它们的红会**立刻**
    #   落进 `unexplained_red_teeth` ⇒ 闸红，而不是被一张过期白名单静默解释掉。
    #   事实 C / D 仍然照量、照落盘（`facts` 块与 `summary*` 的逐维读数一个字段都没少，
    #   裁定 93.1-3「登记不许缩水」），只是不再用于**授权红**。
    # 事实 C = 逐维合法 bin 占用 < `min_bins_occupied`（条件 b 的分辨率代价；现为登记项）
    # 事实 D = F2 下限在真正不动的维上比 0.02×行程小若干数量级（Tr3 的设计目的；现为登记项）
    # 事实 F = **窗口逃逸**（`headroom_consumption_max ≥ 1.0`，裁定 90.4-1 的新硬红）
    "Tesc_no_covered_window_escape": ("F",),
    # 事实 G = **下侧覆盖不足**（digitize 层面实测到非法 bin -1 的维；裁定 90.4-1 的下侧硬红）。
    # 用 digitize 层面的实测去授权**窗口层**的牙 = 两个层面互为印证；若两者不一致（一个空一个非空），
    # 子集检查会把红判成"无法解释"⇒ 分叉不会被静默吞掉。
    "Tlo_no_downside_coverage_deficit": ("G",),
    # ⚠ **故意不登记**这两把：
    #   `Tiv_out_of_declared_interval_is_measured` —— 它红 = 测量块缺失/不完整 = **实现缺陷**，
    #     没有任何"数据事实"能授权它 ⇒ 必须落进 `unexplained_red_teeth`（不临时加白名单）；
    #   `Tovr_out_of_interval_overflow_is_warned` —— 非 blocking（只出 WARN）⇒ 结构上不可能进 red_ids；
    #     若哪天它进了 red_ids（= 有人把它升回 blocking，把裁定 90.4-1 撤回的极性装回去），
    #     本表没有它 ⇒ 立刻"无法解释"⇒ 闸红。这是一处**故意留下的绊线**。
    # 事实 E = 本臂**声明的消费方是 bc 而溯源标签不可进 BC**（裁定 85.4-3 的同源硬闸）。
    # 这是结构性事实、不是维级测量 ⇒ 它只授权"红不红"，不约束维集合。
    "Tp5_bc_admission_requires_formal40_bc_source": ("E",),
    # ⚠ 裁定 **93.2 / 93.4** 的三颗新硬红**同样故意不登记**：
    #   `Tz_denom_strictly_positive`（除零族，绝对硬红、无定标空间）、
    #   `Tres_per_dim_resolution_floor`（逐维分辨率下限，D 用 formal-40 全量口径定标）、
    #   `Tbcad_admission_requires_green_gate`（BC 准入必须 AND 闸 verdict）。
    #   它们红了 = **实现缺陷或数据缺陷**，没有任何"数据事实"能授权 ⇒ 必须落进
    #   `unexplained_red_teeth`（不临时加白名单，与 `Tiv` 的处置同理）。
    #   `Tresw_near_constant_low_resolution_is_warned` 是非 blocking（只出 WARN）⇒ 结构上
    #   进不了 red_ids；若哪天它进了，本表没有它 ⇒ 立刻"无法解释"⇒ 闸红（同 `Tovr` 的绊线）。
}


def derive_allowed_red_from_measurement(*, red_ids, rep_eval, rep_build, conformance, base_stats,
                                        eval_frames, family, near_constant,
                                        coverage_target, stats_provenance=None,
                                        consumer=None, rep_all=None) -> dict:
    """把"哪些牙允许红"变成**测量的函数**：返回授权表 + 四个事实 + 无法解释的红 + 升级项。

    四个事实都在**本次运行内**量出来，不引别处量出的数值（裁定 87.7
    `rule_transplantable_value_not_transplantable`：规则可搬、别的口径量出的数值不可搬）：
      A = 超出声明物理区间的维（三态：区间缺失 ⇒ `not_measured_*`，**不**当成"没有越界"）；
      B = held-out 帧落在 build **未展宽** q01/q99 之外的维（覆盖率缺口）；
      C = 逐维合法 bin 占用低于 `min_bins_occupied` 的维（分辨率代价）；
      D = 近常量维的下限实质性比 < 1（F2 族的已知形态，Tr3 的对象）。
    """
    th = nc.ContractThresholds()
    pd_e = rep_eval["per_dim"]
    pd_b = (rep_build or {}).get("per_dim", [])
    pd_a = (rep_all or {}).get("per_dim", [])
    a_status = conformance.get("measurement_status")
    A = sorted(conformance.get("dims_out") or []) if a_status == "measured" else None
    B = None
    if eval_frames is not None:
        q01 = np.asarray(base_stats["q01"], dtype=np.float64)
        q99 = np.asarray(base_stats["q99"], dtype=np.float64)
        ev = np.atleast_2d(np.asarray(eval_frames, dtype=np.float64))
        B = sorted(int(i) for i in np.nonzero((ev.min(axis=0) < q01) | (ev.max(axis=0) > q99))[0])
    C = sorted(int(p["dim"]) for p in pd_e if p["n_bins_occupied"] < th.min_bins_occupied)
    # 事实 C 的**口径拆分**：授权用的是 held-out 口径（牙 `Tb` 就是在 held-out 帧上量的，
    # 授权事实与被授权的红必须同口径，否则子集检查会把红判成"无法解释"）；
    # build / all 两个口径**只登记**，供裁定 90.4-3 的触发判据用。没测 ⇒ `None`（三态）。
    C_build = (sorted(int(p["dim"]) for p in pd_b if p["n_bins_occupied"] < th.min_bins_occupied)
               if pd_b else None)
    C_all = (sorted(int(p["dim"]) for p in pd_a if p["n_bins_occupied"] < th.min_bins_occupied)
             if pd_a else None)
    d_ratio = (near_constant or {}).get("materiality_ratio_min")
    D = bool(family == "F2_noise_scale_multiple" and d_ratio is not None and d_ratio < 1.0)
    adm = nc.bc_admission(stats_provenance)
    E = bool(consumer == nc.CONSUMER_BC and not adm["admissible_for_bc"])
    # 事实 F / G（裁定 90.4-1 新立）：F = 窗口逃逸（头寸消耗比 ≥ 1.0）；
    # G = 下侧覆盖不足（在 **digitize 层面**实测到非法 bin -1 的维，build ∪ eval）。
    # G 用 digitize 层面量、去授权**窗口层**的牙 `Tlo`，是故意的：两层若分叉（一层空、一层非空），
    # 子集检查会把红判成"无法解释" ⇒ 分叉不会被静默吞掉（`reference_digitize` 与 `normalize_with_case`
    # 是两条独立实现路径）。
    F = (bool(conformance.get("window_escape")) if a_status == "measured" else None)
    F_dims = (sorted(conformance.get("dims_window_escape") or []) if a_status == "measured" else None)
    G = sorted(set(int(p["dim"]) for p in pd_b if p["illegal_bin_-1_present"]) |
               set(int(p["dim"]) for p in pd_e if p["illegal_bin_-1_present"]))
    facts = {
        "A_out_of_declared_interval": {
            "measurement_status": a_status, "dims": A,
            "excess_above": conformance.get("excess_above"), "excess_below": conformance.get("excess_below"),
            "excess_above_pct_of_travel": conformance.get("excess_above_pct_of_travel"),
            "excess_below_pct_of_travel": conformance.get("excess_below_pct_of_travel"),
            "n_frames_out_per_dim": conformance.get("n_frames_out_per_dim"),
            "n_frames_above_per_dim": conformance.get("n_frames_above_per_dim"),
            "n_frames_below_per_dim": conformance.get("n_frames_below_per_dim"),
            "frac_frames_out_per_dim": conformance.get("frac_frames_out_per_dim"),
            "headroom_consumption_max": conformance.get("headroom_consumption_max"),
            "headroom_consumption_max_above": conformance.get("headroom_consumption_max_above"),
            "headroom_consumption_max_below": conformance.get("headroom_consumption_max_below"),
            "role_after_ruling_90_4_1": ("**只是测量**：越出声明区间本身物理合法（`jnt_range` 是软边界），"
                                         "**永不因越界本身出红**；它只作 clip/饱和族红的成因之一"),
            "authority": ("裁定 90.4-1（撤回裁定 87.3-2 条件 c 的极性；D 自记第 15 号同型错误"
                          "『把软边界当硬界』）；修前这里写的是『条件 c：超出 = 数据/契约缺陷，必须继续红』")},
        "B_heldout_coverage_gap": {
            "dims": B, "measured": B is not None,
            "rule": "held-out 帧的 min/max 落在 **build 的原始 q01/q99** 之外（未展宽口径）",
            "authority": "裁定 87.2-1 缺陷 10 的修法（held-out 必须真是 held-out）"},
        "C_resolution_below_threshold": {
            "dims": C, "threshold": th.min_bins_occupied,
            "threshold_status": th.provenance["min_bins_occupied"],
            "caliber": "heldout（**授权口径**：与被授权的牙 `Tb` 同口径）",
            "caliber_split": {
                "heldout": {"dims": C, "measurement_status": "measured",
                            "n_frames": int(rep_eval.get("n_frames"))},
                "build": {"dims": C_build,
                          "measurement_status": ("measured" if C_build is not None else "not_measured"),
                          "n_frames": (None if not pd_b else int(rep_build.get("n_frames")))},
                "all": {"dims": C_all,
                        "measurement_status": ("measured" if C_all is not None else "not_measured"),
                        "n_frames": (None if not pd_a else int(rep_all.get("n_frames")))},
                "why": ("三个口径的 `dims_below_min_bins` **实测不同**（held-out 是 5% 的子集）⇒ "
                        "只报一个口径 = 半个事实。哪个口径管裁定 90.4-3 的触发，见 "
                        "`escalations_to_d[resolution_floor_uncalibrated].ruling_90_4_3_trigger`"),
            },
            "authority": "裁定 87.3-2 条件 b（本轮**只登记不定标**；超限走升级路径报 D）"},
        "D_f2_floor_immaterial": {
            "applies": D, "family": family, "materiality_ratio_min": d_ratio,
            "authority": "Tr3 的设计目的（F2 下限 = coef × MAD，在真正不动的维上≈0）"},
        "E_bc_admission_must_red": {
            "applies": E, "consumer": consumer, "stats_provenance": adm["stats_provenance"],
            "admissible_for_bc": adm["admissible_for_bc"],
            "required_provenance_for_bc": adm.get("required_provenance_for_bc"),
            "authority": "裁定 85.4-3（同源硬闸：喂 pilot 的 stats 给 BC 配置 ⇒ 必须红）"},
        "F_window_escape": {
            "measured": F, "dims": F_dims,
            "threshold": nc.WINDOW_ESCAPE_RATIO,
            "headroom_consumption_max": conformance.get("headroom_consumption_max"),
            "authority": ("裁定 90.4-1（硬红移到有物理含义的量：`headroom_consumption_max ≥ 1.0` = "
                          "**窗口逃逸的定义**）；90.6-1 明令不得放宽 1.0，处置是升 `headroom_bins` "
                          "或启用逐维覆盖 + 新建 `representation_version`")},
        "G_downside_coverage_deficit": {
            "dims": G, "measured_at": "digitize 层面（`illegal_bin_-1_present`，build ∪ eval）",
            "authority": ("裁定 90.4-1 的下侧/上侧分治 + `processor_pi05.py:77` 的结构不对称"
                          "（裁定 90.3 实测：`x < -1` ⇒ bin -1 非法 token；`x ≥ 1` ⇒ 255 合法顶 bin）")},
    }
    # `ok` = 该事实是否**已测得且成立**（三态：`None` = 没测到，不当成"测到了没有"）；
    # `dims` = 该事实授权的维集合（`None` = 结构性事实，不约束维）。
    fact_state = {"A": {"ok": (A is not None and len(A) > 0), "dims": A},
                  "B": {"ok": (B is not None and len(B) > 0), "dims": B},
                  "C": {"ok": len(C) > 0, "dims": C},
                  "D": {"ok": D, "dims": None},
                  "E": {"ok": E, "dims": None},
                  "F": {"ok": (F is True), "dims": F_dims},
                  "G": {"ok": len(G) > 0, "dims": G}}
    sat = rep_eval.get("saturation") or {}
    sat_dims = sorted(set(int(x) for x in (sat.get("dims_with_high_sat") or [])) |
                      set(int(x) for x in (sat.get("dims_with_low_sat") or [])))
    observed_dims = {
        "Td1_clip_build_frames": sorted(int(p["dim"]) for p in pd_b if p["clip_ratio"] > th.clip_ratio_cap),
        "Te1_no_illegal_bin_build": sorted(int(p["dim"]) for p in pd_b if p["illegal_bin_-1_present"]),
        "Td2_clip_heldout": sorted(int(p["dim"]) for p in pd_e if p["clip_ratio"] > th.clip_ratio_cap),
        "Te2_no_illegal_bin_heldout": sorted(int(p["dim"]) for p in pd_e if p["illegal_bin_-1_present"]),
        "Tsat_saturation_dims_zero": sat_dims,
        "Tb_scale_floor_effective": C,
        "Tesc_no_covered_window_escape": (F_dims or []),
        "Tlo_no_downside_coverage_deficit": G,
        "Tr3_near_constant_floor_material": sorted((near_constant or {}).get("immaterial_dims") or []),
    }
    allowed, attribution, unexplained = {}, {}, []
    for tid in sorted(set(red_ids or [])):
        auth = TOOTH_AUTHORIZED_BY_FACT.get(tid)
        if auth is None:
            unexplained.append(tid)      # 不在授权表里的牙红了 ⇒ 一律算无法解释（不临时加白名单）
            continue
        present = [f for f in auth if (fact_state.get(f) or {}).get("ok")]
        missing = [f for f in auth if f not in present]
        dim_sets = [(fact_state[f]["dims"] or []) for f in present
                    if (fact_state.get(f) or {}).get("dims") is not None]
        constrains_dims = any((fact_state.get(f) or {}).get("dims") is not None for f in present)
        union = sorted(set().union(*dim_sets)) if dim_sets else []
        od = observed_dims.get(tid, [])
        subset_ok = (bool(set(od) <= set(union)) if (od and constrains_dims) else True)
        if missing or not present or not subset_ok:
            unexplained.append(tid)
            attribution[tid] = {"allowed": False, "authorized_by": list(auth),
                                "facts_missing_or_empty": missing, "facts_present": present,
                                "observed_dims": od, "authorizing_dims": union,
                                "dims_subset_of_authorizing": subset_ok}
            continue
        allowed[tid] = {"authorized_by": list(auth), "facts_present": present,
                        "observed_dims": od, "authorizing_dims": union,
                        "dims_subset_of_authorizing": subset_ok}
        attribution[tid] = {**allowed[tid], "allowed": True}
    escalations = []
    # ---- 裁定 93.1-3「登记不许缩水」+ 裁定 93.3：分辨率读数**无条件**照量照落 ----
    # 修前本块的发射条件是 `if "Tb_scale_floor_effective" in allowed:`（= 只有 `Tb` 红了才登记）。
    # 裁定 93.1-1 把 `Tb` 转成 WARN 之后它结构上不再进 `red_ids` ⇒ 该条件恒假 ⇒ 整块逐维读数
    # （三个口径 + 90.4-3 触发判据）会**静默消失**，而这正是 93.1-3 要挡的「转 WARN 之后登记缩水」。
    # ⇒ 条件去掉、读数无条件计算；本块已从 `escalations_to_d`（open ask）移进 `ruled_escalations`
    #   （D 在裁定 93.1/93.2/93.3 里已裁），**字段一个没少**，只把 `ask_d` 换成 `what_d_ruled`。
    # 裁定 90.4-3 的触发条件是**逐维**的（D 自记第 16 号错误：用 median 守逐维失效），
    # 所以两种读法都算出来，并按 90.4-3 的字面判「是否触发」。
    nc_dims = sorted(set((near_constant or {}).get("dims") or []))
    dims_below_not_nc = sorted(set(C) - set(nc_dims))
    # 触发判据的**逐口径**读数（单一实现 `trigger_caliber_readings`；行级只有一行 ⇒ 传单元素列表）。
    # 修前这里只有 held-out 一个口径，且把它当成全量结论报给 D（本轮实测两口径结论相反）。
    trigger_row = trigger_caliber_readings(
        per_dim_by_caliber={
            "heldout": ([[int(x["n_bins_occupied"]) for x in pd_e]] if pd_e else None),
            "build": ([[int(x["n_bins_occupied"]) for x in pd_b]] if pd_b else None),
            "all": ([[int(x["n_bins_occupied"]) for x in pd_a]] if pd_a else None)},
        n_frames_by_caliber={
            "heldout": int(rep_eval.get("n_frames")),
            "build": (None if not pd_b else int(rep_build.get("n_frames"))),
            "all": (None if not pd_a else int(rep_all.get("n_frames")))},
        nc_dims=nc_dims, threshold=th.min_bins_occupied,
        threshold_status=th.provenance["min_bins_occupied"],
        row_ids=[f"row|{family}"])
    resolution_reading = {
        "measured": {
            "caliber_of_this_block": "heldout（= 牙 `Tb` 的测量口径；全量口径见 `all_caliber`）",
            "dims_below_min_bins": C,
            "bins_occupied_per_dim": [int(x["n_bins_occupied"]) for x in pd_e],
            "bins_occupied_median": float(np.median([x["n_bins_occupied"] for x in pd_e])),
            "bins_occupied_min": int(min(x["n_bins_occupied"] for x in pd_e)),
            "threshold": th.min_bins_occupied,
            "threshold_status": th.provenance["min_bins_occupied"],
            "near_constant_dims": nc_dims,
            "dims_below_min_bins_not_near_constant": dims_below_not_nc},
        "all_caliber": {
            "measurement_status": ("measured" if C_all is not None else "not_measured"),
            "n_frames": (None if not pd_a else int(rep_all.get("n_frames"))),
            "dims_below_min_bins": C_all,
            "bins_occupied_per_dim": ([int(x["n_bins_occupied"]) for x in pd_a] if pd_a else None),
            "dims_below_min_bins_not_near_constant": (
                None if C_all is None else sorted(set(C_all) - set(nc_dims))),
            "build_caliber_dims_below_min_bins": C_build,
            "why_both": ("held-out 只有全量的 ~5%（formal-40：547/11035）⇒ 同一维在子集上"
                         "落进个位数 bin、在全量上不会。两个读数**都是真的**，只是口径不同；"
                         "裁定 93.3 已指定：分辨率族用**全量**、正确性族用 **held-out**")},
        "ruling_90_4_3_trigger": trigger_row}
    ruled = []
    ruled.append({
        "id": "resolution_floor_uncalibrated",
        "status": ("RULED_by_93_1_93_2_93_3（原为 C2 的升级项 `ask_d`，D 已裁 ⇒ 不再是 open ask）"),
        "tooth_before": ("Tb_scale_floor_effective（blocking=True，阈值状态 `proposed_pending_s1`）"),
        "teeth_after": [
            "Tb_scale_floor_effective（**blocking=False ⇒ WARN**，阈值状态 "
            "`registered_measurement_not_a_judgment`；断言文本/applies_when/red_when 一字未改）",
            "Tr3_near_constant_floor_material（同上，裁定 93.1-1）",
            "Tz_denom_strictly_positive（新增，绝对硬红、全臂、无定标空间；裁定 93.2 补丁①）",
            "Tres_per_dim_resolution_floor（新增，逐维硬红、**全量口径**、D 定标；裁定 93.2 补丁②）",
            "Tresw_near_constant_low_resolution_is_warned（新增，近常量维 < 8 ⇒ WARN 登记 = "
            "裁定 90.4-3 的 P1 债）"],
        "measured": resolution_reading["measured"],
        "all_caliber": resolution_reading["all_caliber"],
        "ruling_90_4_3_trigger": resolution_reading["ruling_90_4_3_trigger"],
        "what_d_ruled": (
            "裁定 93.1（甲）：`Tb`/`Tr3` 的 `blocking → False`（机制 = `tooth()` 的 status 分支），"
            "阈值状态串改判为 `registered_measurement_not_a_judgment`，登记不许缩水；"
            "裁定 93.2（补丁）：换上 `Tz`（除零族，绝对硬红）与 `Tres`（逐维分辨率下限，"
            "**全量口径**，D 用 formal-40 实测定标：非近常量维 ≥8、近常量维 ≥2 硬红 / <8 WARN，"
            "阈值状态 `d_calibrated_from_formal40_all_caliber`，余量 2.75× / 1.5× / 2.5×）；"
            "裁定 93.3（E1）：正确性族 = held-out、分辨率族 = 全量，`params:688` 的 median "
            "可推翻条件**已撤回**，统一到逐维口径；触发条件 ② 实测不触发（`dims_below_8=[3,10]` "
            "恰好是已分类近常量维），条件 ① 记 `not_measured`（尚无 BC）。"),
        "c2_does_not": (
            "不下调 `min_bins_occupied`、不把 `Tres` 的阈值改成能放行的值、不据 held-out 口径把 "
            "P1 升 P0。**可推翻条件仍在册**（裁定 93.2 预登记）：全量口径下任一非近常量维 < 8 ⇒ "
            "C2 停手回报 D，不得改阈值放行。"),
        "falsifiable_checkpoint_measured": (
            "四点单调性（n=547/2196/10488/11035，同一份 stats、同一 `--s1-frames` 读路径）已由 C2 "
            "实测：逐维单调不减成立、全量口径下非近常量维最小 22 ≥ 8 ⇒ 两个预登记检查点都 PASS，"
            "产物 `runs/vla/c2_norm_contract_20260929/probe_monotonicity_20260930/verdict.json`。"
            "**同时实测出 D 在 93.2 里写的成因不成立** ⇒ C2 停手回报、未自决；D 已裁（**94.1**）："
            "「采样计数假象」判 **REFUTED**、记 D 同型错误 #19 "
            "`consistent_with_is_not_established_by`，D 用 8 个同 n iid 子集独立复算确认"
            "（dim0 ∈ [20,22] vs 真 held-out 3、`arithmetic_bound_binding=false`）。"
            "**94.2**：口径改判到全量的理由换成三条独立实测（留出集形状说 / 无判据力说 / 极性说），"
            "**结论、口径、阈值 8 / 2 一律不变**，余量 2.75× / 1.5× / 2.5× 不变；**94.5**：不回退到 "
            "held-out 口径、`Tres` 分口径分叉关闭。"),
        "preregistered_conditions_consumer": {
            # 裁定 94.9-5（缺陷类 ⑳ `preregistered_condition_without_a_consumer`）：预登记的可推翻
            # 条件必须写明**谁在什么时刻核它**，否则等于没写。实证 = T-C2-7 的「再发生一次抢卡事故
            # ⇒ 立即升 P0」在 00:2x 触发后 11 小时无人执行，而且是外部分析而不是 D 自己发现的。
            "why": ("裁定 94.9-5：全线自查 rev19 之前所有 `trigger_to_promote_to_P0` / 可推翻条件字段，"
                    "补 `checked_by` + `checked_when`"),
            "conditions": [
                {"condition": "全量口径下任一非近常量维 bins_occupied_d < 8（裁定 93.2 预登记）",
                 "checked_by": ("C2 · `harness/norm_contract.py` 的 `Tres` 牙，逐次 "
                                "`evaluate_contract` 调用落 "
                                "`extra.preregistered_falsifiable_condition`"),
                 "checked_when": now_iso(),
                 "checked_when_field": "同名（每次调用都盖新时刻，不是写死的字符串）",
                 "result_this_run": ("见每行 Tres 的 `extra.preregistered_falsifiable_condition.result`"),
                 "action_if_true": "不得改阈值放行、不得自行升 P0，停手回报 D"},
                {"condition": "裁定 90.4-3 的分辨率触发判据（逐维、口径依赖）",
                 "checked_by": "C2 · `trigger_caliber_readings`（本块 `ruling_90_4_3_trigger`）",
                 "checked_when": now_iso(),
                 "checked_when_field": "matrix 顶层 `run_started_at` / `generated_at`",
                 "action_if_true": ("口径依赖 ⇒ 不据此升 P0；`governing_caliber` 交 D 裁"
                                    "（已由 93.3 裁为：分辨率族用全量）")},
                {"condition": "四点单调性 / 全量口径非近常量维 ≥ 8（裁定 93.2 的两个可证伪检查点）",
                 "checked_by": "C2 · `probe_monotonicity_20260930/probe.py`（一次性探针，已跑）",
                 "checked_when": "2026-09-30T11:12:23+08:00（verdict.json 的落盘时刻）",
                 "result_this_run": "两个检查点都 PASS；第三臂另证伪了 D 的成因（⇒ 裁定 94.1）",
                 "action_if_true": "口径作废、`Tres` 回 held-out、触发 P0 复议（未触发）"},
                {"condition": ("T-C2-3 的触发（formal > 2 GiB，或 S4b 真帧接入时出现 "
                               "`StaleObservation`）"),
                 "checked_by": None,
                 "checked_when": None,
                 "consumer_status": ("**无消费者 —— 如实登记**：裁定 95.1-4 把 T-C2-3 冻结在 P2"
                                     "（不进本轮任何批次）⇒ 冻结期内无人核它；恢复时由 D 指派"),
                 "action_if_true": "解冻 T-C2-3（obs 键白名单的图像侧）"}],
        },
        "p1_debt_registered": (
            "dim3/dim10 逐维覆盖重建（全量 3 / 5 bin → 目标 ~200 bin）；触发 = BC 首轮失败面指向"
            "这两维，**或** 93.2 的单调性检查点被证伪。用户已批「速度优先」⇒ 维持 P1、不进 P0。")})
    if a_status == "measured" and (A or []):
        ruled.append({
            "id": "states_outside_declared_interval",
            "status": "RULED_by_90_4-1（原为 C2 的升级项，D 已裁 ⇒ 不再是 open ask）",
            "tooth_before": "Tiv_no_state_outside_declared_interval（越界即红）",
            "teeth_after": ["Tiv_out_of_declared_interval_is_measured（测量必须存在）",
                            "Tesc_no_covered_window_escape（硬红：窗口逃逸）",
                            "Tlo_no_downside_coverage_deficit（硬红：下侧覆盖不足）",
                            "Tovr_out_of_interval_overflow_is_warned（warning + 量级）"],
            "measured": {"dims_out": A,
                         "excess_above": conformance.get("excess_above"),
                         "excess_below": conformance.get("excess_below"),
                         "excess_above_pct_of_travel": conformance.get("excess_above_pct_of_travel"),
                         "n_frames_out_per_dim": conformance.get("n_frames_out_per_dim"),
                         "n_frames_above_per_dim": conformance.get("n_frames_above_per_dim"),
                         "frac_frames_out_per_dim": conformance.get("frac_frames_out_per_dim"),
                         "headroom_consumption_ratio": conformance.get("headroom_consumption_ratio"),
                         "headroom_consumption_max": conformance.get("headroom_consumption_max"),
                         "window_escape": conformance.get("window_escape"),
                         "downside_deficit": conformance.get("downside_deficit")},
            "what_d_ruled": ("裁定 90.4-1：`jnt_range` 是**软边界** ⇒ 越出声明区间物理合法、"
                             "**永不因越界本身出红**；硬红移到 `headroom_consumption_max ≥ 1.0`；"
                             "下侧/上侧分治；`Te1`/`Te2` 的非法 bin 保持绝对硬红。"
                             "裁定 90.4-2：① 保留不回退。裁定 90.4-3：P0 只改极性，逐维覆盖留 P1"),
            "c2_proposal_now_void": ("C2 原提案『`interval_effective = [min(declared_lo, observed_min), "
                                     "max(declared_hi, observed_max)]` 作 ① 的覆盖目标』**未被采纳**："
                                     "D 采的是 P1 的逐维覆盖（下侧取 min(declared_lo, observed_min)、"
                                     "上侧只取 observed_max + regime margin），且**待触发**、不进 BC 前置"),
            "no_widening_applied": ("C2 **没有**用『再展宽』消掉越界事实（裁定 90.3 明令禁止：饱和平台"
                                    "再展宽只会把求解器抖动放大成假信号喂给 BC）；`cover_cap` 仍钉在声明区间上，"
                                    "`cover_cap_respected` 逐行落盘")})
    return {"coverage_target": coverage_target,
            "allowed_red_teeth": sorted(allowed),
            "allowed_red_authorization": allowed,
            "red_dim_attribution": attribution,
            "unexplained_red_teeth": sorted(unexplained),
            "all_red_explained": not unexplained,
            "facts": facts,
            "escalations_to_d": escalations,
            "ruled_escalations": ruled}


BASELINE_BUILD_ONLY_PILOT10 = {
    "what": ("裁定 87.3-2 **条件 a 臂 1**（`--coverage-target build_only`）在 **pilot-10** 上的读数"
             "（① 之前的世界）"),
    "clip_ratio_max": 0.0927273, "illegal_bin_dims": [7, 12], "saturation_dims": [5, 7, 12],
    "status": ("**reference_only_not_this_run**（裁定 87.7 `rule_transplantable_value_not_transplantable`："
               "数值不可搬 ⇒ 本字典是引用，不参与本次任何行的判定）"),
    "authority": "裁定 87.3-2 条件 a；逐位复现由闸侧 `coverage_condition_a.json` 承担",
}
MAINLINE_WATCHED_TEETH = ("Td2_clip_heldout", "Te2_no_illegal_bin_heldout", "Tsat_saturation_dims_zero",
                          "Tb_scale_floor_effective", "Tcov_declared_interval_covered",
                          "Tiv_out_of_declared_interval_is_measured", "Tesc_no_covered_window_escape",
                          "Tlo_no_downside_coverage_deficit", "Tovr_out_of_interval_overflow_is_warned",
                          "Tr3_near_constant_floor_material",
                          # 裁定 93.1/93.2/93.4 新增的四颗（转 WARN 的两颗**仍在册**：
                          # 「登记不许缩水」= 转 WARN 之后 observed 串照旧被聚合进 finding）
                          "Tz_denom_strictly_positive", "Tres_per_dim_resolution_floor",
                          "Tresw_near_constant_low_resolution_is_warned",
                          "Tbcad_admission_requires_green_gate")
HELDOUT_FAMILY_TEETH = ("Td2_clip_heldout", "Te2_no_illegal_bin_heldout", "Tsat_saturation_dims_zero")


def heldout_blindness_registration(main_rows: list) -> dict:
    """裁定 **94.3** 的臂级登记（按裁定 **95.1-1** 降级为 Ⅱ 类「登记不阻塞」）。

    WHY 只有登记、没有牙：94.3 原本要一颗 blocking 牙 + 双向变异体，但那属于用户分诊表的
    「Ⅱ 实验解释风险」⇒ 裁定 95.1-1 把它从 T-C2-8 的 P0 批次里拿出来，牙与变异体**推迟到 S5 前**，
    本轮只落 `heldout_bins_occupied_per_dim` + `correctness_blind_dims` 两个字段（逐维数据本来就有）。
    WHY 必须落：held-out（episodes [19,39]、n=547）逐维占用实测
    `[3,97,106,2,38,3,35,4,111,108,5,46,5,36]` ⇒ 正确性族在 6 个维上几乎无从触发，而它们**报了绿**
    = 缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`。不回退口径（94.5）⇒ 隐性盲点
    必须变成显性登记。
    纪律：**盲点维必须由逐维实测算出，不许硬编码 6**；**永不 median/mean**（中位数会把塌陷平均掉）。
    """
    per_row = [(i, r.get("heldout_bins_occupied_per_dim"), r.get("correctness_blind_dims"),
                r.get("correctness_blind_dims_status")) for i, r in enumerate(main_rows)]
    measured = [x for x in per_row if x[1] is not None]
    blind_union = sorted({int(d) for x in measured for d in (x[2] or [])})
    distinct = sorted({json.dumps(x[1]) for x in measured})
    th_nc = nc.ContractThresholds().min_bins_occupied_non_near_constant
    return {
        "measurement_status": ("measured" if measured else "not_measured"),
        "n_rows": len(main_rows), "n_rows_measured": len(measured),
        "n_dims": (len(measured[0][1]) if measured else None),
        "blind_dim_threshold": th_nc,
        "blind_dim_threshold_status": ("d_calibrated_from_formal40_all_caliber"
                                       "（复用 `Tres` 已定标的 8，不新造数）"),
        "n_distinct_heldout_patterns": len(distinct),
        "heldout_bins_occupied_per_dim_distinct": [json.loads(s) for s in distinct],
        "correctness_blind_dims_union": blind_union,
        "correctness_blind_dims_per_row": [
            {"row_index": i, "heldout_bins_occupied_per_dim": b,
             "correctness_blind_dims": c, "measurement_status": s} for i, b, c, s in per_row],
        "correctness_family_teeth_affected": sorted(set(HELDOUT_FAMILY_TEETH)
                                                    | {"Te1_no_illegal_bin_build",
                                                       "Tcov_declared_interval_covered",
                                                       "Tesc_no_covered_window_escape"}),
        "tooth_status": ("deferred_to_pre_S5（裁定 95.1-1：牙 "
                         "`Theldout_per_dim_blindness_is_registered` 与双向变异体推迟；"
                         "本轮**只落两个字段**，BC 不等它）"),
        "class_per_ruling_95_1": "Ⅱ_experiment_interpretation_risk（登记不阻塞）",
        "authority": ("裁定 94.3（held-out 逐维占用 ⇒ 正确性族在盲点维上几乎无从触发）+ 裁定 94.5"
                      "（不回退口径，代价写在脸上）+ 裁定 95.1-1（降为登记不阻塞）"),
        "debt_repayment": ("裁定 94.4 的选集升级（硬下限 k ≥ 8、目标 k = 12、按方向 × 相位分层选取）；"
                           "裁定 95.1-2 降 **P2**、排六步序列第 2 步之后 —— 它会换 stats ⇒ 换 "
                           "`representation_version` ⇒ 重跑全量闸，**不许与 T-C2-8 混批**"),
        "wording_constraint": ("偿清之前，任何『归一化器已通过正确性验证』的表述都必须带『盲点维 "
                               "`not_measured`』的限定（红线 "
                               "`absence_of_measurement_is_not_measurement_of_absence`）"),
    }


def compose_mainline_finding(*, main_rows, coverage_target, base_stats, build_frames, split_rec,
                             reader, reader_role, dataset_stage, stats_provenance,
                             baseline_build_only_reading=None) -> dict:
    """把一个 S1 臂的**结论串**从该臂自己的测量拼出来（不写死数字：裁定 84.5 / 87.7）。

    为什么必须是**一份函数**而不是两个臂各写一段：裁定 90.4-4 之后 S1 有**两个**读路径臂
    （npz = 权威接口、`--s1-lerobot` = 交叉核对臂），两者的 finding 结构必须同源，
    否则两段文本会各自漂移 —— 与本仓已多次实测到的"同族常量各写一份"（`NEAR_CONSTANT_REL_TOL`、
    `HEADROOM_BINS_DEFAULT`）同一缺陷形态。

    所有数字都取自 `main_rows`（= 本次运行产出的行），**唯一**例外是
    `baseline_build_only_reading`（显式标 `reference_only_not_this_run`）。
    """
    n_main_rows = len(main_rows)
    unexplained = sorted({t for r in main_rows for t in (r.get("unexplained_red_teeth") or [])})
    tr3_on_f1 = sorted(r["coef"] for r in main_rows
                       if r["family"] == "F1_physical_range_fraction"
                       and "Tr3_near_constant_floor_material" in r["red_ids"])
    worst: dict[str, list] = {}
    for r in main_rows:
        for t in (r.get("teeth") or []):
            if t["id"] in MAINLINE_WATCHED_TEETH:
                worst.setdefault(t["id"], []).append(t["observed"])
    red_tooth_counts: dict[str, int] = {}
    for r in main_rows:
        for t in (r.get("red_ids") or []):
            red_tooth_counts[t] = red_tooth_counts.get(t, 0) + 1
    warn_tooth_counts: dict[str, int] = {}
    green_tooth_counts: dict[str, int] = {}
    na_tooth_counts: dict[str, int] = {}
    for r in main_rows:
        for t in (r.get("teeth") or []):
            if t.get("status") == "PASS":
                green_tooth_counts[t["id"]] = green_tooth_counts.get(t["id"], 0) + 1
            elif t.get("status") == "WARN":
                warn_tooth_counts[t["id"]] = warn_tooth_counts.get(t["id"], 0) + 1
            elif t.get("status") == "N_A":
                na_tooth_counts[t["id"]] = na_tooth_counts.get(t["id"], 0) + 1
    agg_allowed = sorted({t for r in main_rows for t in (r.get("allowed_red_teeth") or [])})
    # 升级项按 id 去重（同一臂 8 行会各报一次；修前是 16 条重复项，读起来像 16 件事）
    esc_seen: dict[str, dict] = {}
    for r in main_rows:
        for e in (r.get("escalations_to_d") or []):
            k = e.get("id")
            if k not in esc_seen:
                esc_seen[k] = {**e, "n_rows_reporting": 0}
            esc_seen[k]["n_rows_reporting"] += 1
    agg_escalations = [esc_seen[k] for k in sorted(esc_seen)]
    # 已裁定的旧升级项（裁定 90.4-1 把 `states_outside_declared_interval` 从 open ask 变成 RULED）：
    # 与 open 的 `escalations_to_d` **分开存**，否则"还欠 D 什么"这件事读不出来。
    ruled_seen: dict[str, dict] = {}
    for r in main_rows:
        for e in (r.get("ruled_escalations") or []):
            k = e.get("id")
            if k not in ruled_seen:
                ruled_seen[k] = {**e, "n_rows_reporting": 0}
            ruled_seen[k]["n_rows_reporting"] += 1
    agg_ruled = [ruled_seen[k] for k in sorted(ruled_seen)]
    # ---- 「第 0 行能不能代表整臂」= **实测**，不是假设（裁定 92.6 自查项族）----
    # 修前本块只读 `main_rows[0]` 的 `summary`/`near_constant`，等于把「一行」当「整臂」、
    # 把「held-out 子集」当「全量」。两处都是"取一个看起来能用的间接量替代真正要指的那个"。
    row_ids = [f"{r.get('case')}|{r.get('family')}|{r.get('coef')}" for r in main_rows]
    confs = [json.dumps(r.get("declared_interval_conformance"), sort_keys=True, ensure_ascii=False)
             for r in main_rows]
    nc_sets = [sorted(set(int(d) for d in ((r.get("near_constant") or {}).get("dims") or [])))
               for r in main_rows]
    conf_identical = (len(set(confs)) <= 1)
    nc_identical = (len({tuple(x) for x in nc_sets}) <= 1)
    nc_dims = sorted({d for x in nc_sets for d in x})
    conf0 = ((main_rows[0].get("declared_interval_conformance") or {}) if main_rows else {})
    heldout_now_green = all(t not in red_tooth_counts for t in HELDOUT_FAMILY_TEETH)
    # ---- 条件 b（裁定 87.3-2）+ 裁定 90.4-3 的触发判据：**逐行 × 逐口径** ----
    SUMKEY = {"heldout": "summary", "build": "summary_build", "all": "summary_all"}
    per_dim_by_caliber: dict[str, Any] = {}
    n_frames_by_caliber: dict[str, Any] = {}
    rows_missing_caliber: dict[str, list] = {}
    for cname, skey in SUMKEY.items():
        vals = [((r.get(skey) or {}).get("bins_occupied_per_dim")) for r in main_rows]
        nfs = [((r.get(skey) or {}).get("n_frames")) for r in main_rows]
        if main_rows and all(vals):
            per_dim_by_caliber[cname] = [[int(x) for x in v] for v in vals]
            uniq_nf = sorted({int(x) for x in nfs if x is not None})
            n_frames_by_caliber[cname] = (uniq_nf[0] if len(uniq_nf) == 1 else uniq_nf)
            rows_missing_caliber[cname] = []
        else:
            # 缺任何一行 ⇒ 该口径记 `not_measured`（三态）：部分行的聚合会**看起来像**全臂读数
            per_dim_by_caliber[cname] = None
            n_frames_by_caliber[cname] = None
            rows_missing_caliber[cname] = [row_ids[i] for i, v in enumerate(vals) if not v]
    th0 = nc.ContractThresholds()
    trigger_arm = trigger_caliber_readings(
        per_dim_by_caliber=per_dim_by_caliber, n_frames_by_caliber=n_frames_by_caliber,
        nc_dims=nc_dims, threshold=th0.min_bins_occupied,
        threshold_status=th0.provenance["min_bins_occupied"], row_ids=row_ids)
    # 对照读数：同一函数**只喂第 0 行**（= 修前的行为）⇒ 「改成逐行聚合有没有改变结论」是实测的
    trigger_row0 = trigger_caliber_readings(
        per_dim_by_caliber={c: (v[:1] if v else None) for c, v in per_dim_by_caliber.items()},
        n_frames_by_caliber=n_frames_by_caliber, nc_dims=nc_dims,
        threshold=th0.min_bins_occupied, threshold_status=th0.provenance["min_bins_occupied"],
        row_ids=(row_ids[:1] or None), probe_path=None)
    row0_representativeness = {
        "what_changed": ("修前只读 `main_rows[0]`（「取一行当典型」）；现在**逐行聚合**"
                         "（dims_below 取并集、触发按逐行计数），并把「第 0 行能否代表整臂」变成实测"),
        "n_rows": len(main_rows), "row_ids": row_ids,
        "near_constant_dims_identical_across_rows": nc_identical,
        "near_constant_dims_per_row": nc_sets,
        "declared_interval_conformance_identical_across_rows": conf_identical,
        "conformance_from_row0_justified_by": (
            "measured_identical_across_rows（8 行的 conformance 块逐字相同 ⇒ 返回第 0 行那份不丢信息）"
            if conf_identical else
            "**NOT identical across rows** ⇒ `declared_interval_conformance` 只是第 0 行的读数，"
            "**不得**当整臂结论引用"),
        "trigger_row0_only_vs_all_rows": {
            c: {"row0_only_triggered": trigger_row0["calibers"][c].get("triggered"),
                "all_rows_any_triggered": trigger_arm["calibers"][c].get("triggered"),
                "all_rows_every_triggered": trigger_arm["calibers"][c].get("triggered_on_every_row"),
                "conclusion_differs": bool(trigger_row0["calibers"][c].get("triggered")
                                           != trigger_arm["calibers"][c].get("triggered"))}
            for c in CALIBER_NAMES},
        "per_dim_patterns_per_caliber": {c: trigger_arm["calibers"][c].get("n_distinct_per_dim_patterns")
                                         for c in CALIBER_NAMES},
        "dims_differing_across_rows_per_caliber": {
            c: trigger_arm["calibers"][c].get("dims_differing_across_rows") for c in CALIBER_NAMES},
        "ruling_92_6_selfcheck": ("裁定 92.6 自查项：「凡取上一个/取典型值的地方，都问一句我取的这个量"
                                  "是不是我真正要指的那个」⇒ 本线自查命中两处（held-out 子集当全量、"
                                  "第 0 行当整臂），均已改为**逐口径 / 逐行**并落盘对照读数"),
    }
    condition_b = {
        "aggregation": "per_row_then_union（**不再取 `main_rows[0]`**；对照读数见 `row0_representativeness`）",
        "row0_representativeness": row0_representativeness,
        "near_constant_dims": nc_dims,
        "min_bins_occupied_threshold": th0.min_bins_occupied,
        "threshold_status": th0.provenance["min_bins_occupied"],
        "rows_missing_per_caliber": rows_missing_caliber,
        "caliber_readings": trigger_arm["calibers"],
        "ruling_90_4_3_trigger": trigger_arm,
        "note": ("裁定 87.3-2 **条件 b**：只登记、**不自设阈值**。① 之前的同口径读数由条件 a 臂 1"
                 "（`--coverage-target build_only`）那一跑提供，两者由闸侧 `coverage_condition_b.json` "
                 "并排复算"),
    }
    # ---- Tr3 的家族分辨力：**从本次行算**（修前这里是一段写死的 pilot-10 数字散文）----
    tr3_by_family: dict[str, dict] = {}
    for r in main_rows:
        fam = r.get("family")
        t3 = next((t for t in (r.get("teeth") or [])
                   if t["id"] == "Tr3_near_constant_floor_material"), None)
        blk = tr3_by_family.setdefault(fam, {"statuses": [], "materiality_ratio_min": [],
                                             "near_constant_dims": []})
        blk["statuses"].append((t3 or {}).get("status"))
        blk["materiality_ratio_min"].append((r.get("near_constant") or {}).get("materiality_ratio_min"))
        blk["near_constant_dims"].append((r.get("near_constant") or {}).get("dims"))
    tr3_discrimination = {
        fam: {"n_rows": len(v["statuses"]),
              "n_red": sum(1 for s in v["statuses"] if s == "RED"),
              "n_pass": sum(1 for s in v["statuses"] if s == "PASS"),
              "n_n_a": sum(1 for s in v["statuses"] if s == "N_A"),
              "materiality_ratio_min": v["materiality_ratio_min"],
              "near_constant_dims": v["near_constant_dims"]}
        for fam, v in tr3_by_family.items()}
    f1 = tr3_discrimination.get("F1_physical_range_fraction") or {}
    f2 = tr3_discrimination.get("F2_noise_scale_multiple") or {}
    tr3_separates = bool(f1 and f2 and f1.get("n_red") == 0 and f2.get("n_red") == f2.get("n_rows"))
    # ---- 结构性下限（裁定 87.5 / §16.4）：**本次运行实测**，不搬别的口径的读数 ----
    q01b = np.asarray(base_stats["q01"], dtype=np.float64)
    q99b = np.asarray(base_stats["q99"], dtype=np.float64)
    bf = np.atleast_2d(np.asarray(build_frames, dtype=np.float64))
    out_win = ((bf < q01b[None, :]) | (bf > q99b[None, :]))
    clip_pd = out_win.mean(axis=0)
    clip_max_rows = (float(max(r["summary"]["clip_ratio_max"] for r in main_rows)) if main_rows else None)
    clip_ratio_structural_floor = {
        "definition": "未展宽的 build q01/q99 之外那部分 build 帧的比例（逐维）",
        "measured_on": f"build frames n={int(bf.shape[0])}（held-out 划分之后）",
        "clip_ratio_per_dim": [float(x) for x in clip_pd],
        "max": float(clip_pd.max()), "median": float(np.median(clip_pd)), "min": float(clip_pd.min()),
        "quantile_only_floor_after_1": clip_max_rows,
        "annotation_ruling_87_5": ("**该 floor 是『仅分位数覆盖』下的结构下限；采裁定 87.3-1 的 ① 后"
                                   f"应变为 ≈0**（本臂实测：`clip_ratio_max` = {clip_max_rows}）。"
                                   "⇒ 未来读者**不得**由『0.01 < 结构下限』推出『cap 不可达』然后抬高 cap："
                                   "cap 判的是 ① 生效之后的世界，结构下限判的是 ① 之前的世界，"
                                   "两者不是同一口径（裁定 86.6-3：不许放宽到 0.02 以上）"),
    }
    finding_text = (
        (f"采 ①（`coverage_target={coverage_target}`，裁定 87.3-1）后：held-out 家族 "
         f"({'/'.join(t.split('_')[0] for t in HELDOUT_FAMILY_TEETH)}) 在本臂**全绿** —— "
         "这正是裁定 87.13 预登记的可证伪检查点（`Td2 clip=0` / `Te2 dims=[]` / "
         "`Tsat n_dims_saturated=0`）。"
         if heldout_now_green else
         "held-out 家族 (Td2/Te2/Tsat) 仍有红：说明覆盖目标之外还有覆盖率缺口，"
         "读数见 `worst_observed_per_tooth` 与每行 `red_dim_attribution`。")
        + (f"｜裁定 90.4-1 改判后：越出声明区间**不再判红**（软边界），改由 `Tovr` 出 warning"
           f"（本臂 WARN 计数 {warn_tooth_counts}），硬红只落在 `Tesc`（窗口逃逸，实测 "
           f"headroom_consumption_max={conf0.get('headroom_consumption_max')}）与 `Tlo`"
           f"（下侧覆盖不足，实测 dims={conf0.get('dims_downside_deficit')}）上。"
           if coverage_target == nc.COVERAGE_TARGET_DECLARED_INTERVAL else
           f"｜本臂 coverage_target={coverage_target}（对照臂）⇒ 声明区间那组牙出 N_A。")
        + (f"｜裁定 90.4-3 触发判据**口径依赖**：held-out(n="
           f"{trigger_arm['calibers']['heldout'].get('n_frames')}) triggered="
           f"{trigger_arm['calibers']['heldout'].get('triggered')}，全量(n="
           f"{trigger_arm['calibers']['all'].get('n_frames')}) triggered="
           f"{trigger_arm['calibers']['all'].get('triggered')} ⇒ C2 **不据此把 P1 升 P0**，"
           f"`governing_caliber=OPEN_question_to_d`（读数见 `condition_b_resolution`）"
           if trigger_arm["caliber_dependent"] else
           f"｜裁定 90.4-3 触发判据各已测口径一致：triggered="
           f"{trigger_arm['triggered']}（`caliber_dependent=false`）")
        + f"｜当前仍在红的牙（行数/{n_main_rows}）：{red_tooth_counts}，逐条授权见每行 "
          f"`allowed_red_authorization`；升级项 {len(agg_escalations)} 条见 `escalations_to_d`。")
    return {
        "finding": finding_text,
        "reader": reader, "reader_role": reader_role,
         "dataset_stage": dataset_stage, "stats_provenance": stats_provenance,
         "bc_admission": nc.bc_admission(stats_provenance),
         # 裁定 94.3（Ⅱ 类登记不阻塞）：正确性族的逐维盲点。**这不是牙**，是登记。
         "heldout_per_dim_blindness_ruling_94_3": heldout_blindness_registration(main_rows),
         "n_mainline_rows": n_main_rows,
        "n_mainline_rows_red": sum(1 for r in main_rows if r["verdict"] == "RED"),
        "n_mainline_rows_pass": sum(1 for r in main_rows if r["verdict"] == "PASS"),
        "red_tooth_counts": red_tooth_counts,
        "warn_tooth_counts": warn_tooth_counts,
        "green_tooth_counts": green_tooth_counts,
        "n_a_tooth_counts": na_tooth_counts,
        "coverage_target": coverage_target,
        "coverage_target_authority": nc.COVERAGE_TARGET_AUTHORITY.get(coverage_target),
        "allowed_red_teeth_union": agg_allowed,
        "baseline_build_only_reading": (baseline_build_only_reading or BASELINE_BUILD_ONLY_PILOT10),
        "clip_ratio_structural_floor": clip_ratio_structural_floor,
        "allowed_red_derivation": "measured_this_run（`derive_allowed_red_from_measurement`；"
                                  "授权事实的读数在每行 `allowed_red_facts`）",
        "escalations_to_d": agg_escalations,
        "ruled_escalations": agg_ruled,
        "open_asks_to_d": [e.get("id") for e in agg_escalations],
        "declared_interval_conformance": conf0,
        "declared_interval_conformance_identical_across_rows": conf_identical,
        "condition_b_resolution": condition_b,
        "condition_b_resolution_renamed_from": (
            "condition_b_resolution_first_row（修前只含 `main_rows[0]` 的单口径读数；"
            "现名去掉 first_row 是因为它已逐行 × 逐口径聚合）"),
        "tr3_red_on_f1_rows_must_be_empty": tr3_on_f1,
        "tr3_family_discrimination": tr3_discrimination,
        "tr3_separates_f1_from_f2_this_run": tr3_separates,
        "tr3_family_discrimination_note": (
            "**本块由本次行算出**（修前是一段写死的 pilot-10 数字散文 ⇒ 换数据集就会与数据脱节，"
            "裁定 84.5 同族）。判据：F1 行 Tr3 全非 RED 且 F2 行 Tr3 全 RED ⇒ 分得开"
            if tr3_separates else
            "**本臂 Tr3 没有把 F1 与 F2 分开**（读数见 `tr3_family_discrimination`）⇒ "
            "不得再引用『Tr3 在主线数据上分得开』这句话"),
        "unexplained_red_teeth": unexplained,
        "all_red_explained": (not unexplained),
        "worst_observed_per_tooth": {k: v for k, v in worst.items()},
        "held_out_episodes": split_rec.get("held_out_episodes"),
        "n_build_frames": split_rec.get("n_build_frames"),
        "n_eval_frames": split_rec.get("n_eval_frames"),
        "episode_sets_disjoint": split_rec.get("episode_sets_disjoint"),
        "c2_does_not": ("不放宽 `clip_ratio_cap`、不把 held-out 牙降为 warning、不把这批行标成 "
                        "must_red_branch —— 三者都会把真实的数据缺口洗成绿（裁定 51① 的 "
                        "clip_cap_proposal 已明写不许放宽到 0.02 以上；裁定 87.5 维持 cap=0.01）"),
        "ruling_90_4_disposition": {
            "90.4-1": ("条件 c 的极性已撤回：`Tiv_no_state_outside_declared_interval`（越界即红）"
                       "被替换为 `Tiv_out_of_declared_interval_is_measured`（测量必须存在）+ "
                       "`Tesc_no_covered_window_escape`（硬红）+ `Tlo_no_downside_coverage_deficit`"
                       "（下侧硬红）+ `Tovr_out_of_interval_overflow_is_warned`（warning）"),
            "90.4-2": "① 保留、不回退（`must_cover` 未动）",
            "90.4-3": ("P0 只改极性；逐维覆盖留 P1。触发判据现在**逐行 × 三口径**落盘"
                       "（见 `condition_b_resolution.ruling_90_4_3_trigger`）；本轮实测两口径结论相反 "
                       "⇒ `governing_caliber = OPEN_question_to_d`，**C2 不据此升 P0**"),
            "90.4-4": (f"权威接口 = npz + `--s1-frames`（本臂 reader_role={reader_role}）；"
                       "`--s1-lerobot` 的标签必须是 `formal40_lerobot_crosscheck`"),
        },
    }


def resolve_gate_verdict(path: str | None) -> dict:
    """裁定 **93.4**：把"BC 准入要 AND 的那次闸跑"解析成一个**可复算**的引用块。

    三值纪律（红线 `absence_of_measurement_is_not_measurement_of_absence`）：
      · 给了路径且可读 ⇒ `measurement_status="measured"`，`gate_verdict` = 产物里的字面值；
      · 没给路径 ⇒ `"not_measured"` + `gate_verdict=None`（**不**写 `"RED"`、**不**写 `false`：
        那等于宣称"测过了、闸是红的"）；
      · 给了路径但文件不在/不可解析 ⇒ `"not_measured"` + `why` 点名原因（不静默降级）。

    `gate_verdict_sha256_12` **本机取值**（`sha12()`），永不转写：消费方（A2 的 S3 BC 入口，
    裁定 93.4 / T-A2-7）必须自己再算一次并对账，不一致 ⇒ `LearnerRefused`。

    裁定 **97.3-3**：本函数**另解析 `verdict_class1`**（BC 准入真正 AND 的那一个判词），并与顶层
    `verdict` **并排**落进引用块。三值纪律在这里有一条**专属**形态：**产物里没有
    `verdict_class1` 字面值（= 早于裁定 97.3 的闸产物）⇒ `gate_verdict_class1=None` +
    `measurement_status="not_measured"` + `why` 点名原因**，**绝不拿顶层 `verdict` 顶替**
    （顶替 = 把"这一项没测"谎报成"测了、且与顶层同值"，正是红线
    `absence_of_measurement_is_not_measurement_of_absence` 要挡的形态）。后果是可预期的：
    拿旧产物当闸证据 ⇒ `Tbcad` 在 BC 消费方那侧**红**，而不是静默放行。

    ⚠ 这里读的是**上一次已完成的**闸跑，不是本次正在跑的这一次（本次的 verdict 要等 matrix
    产完才算得出来 ⇒ 自引用在构造上做不到）。这个"引用上一轮权威跑"的语义已随产物落盘
    （`gate_verdict_reference.semantics`），不藏在散文里。
    """
    base = {"gate_verdict": None, "gate_verdict_green": None, "gate_run_dir": None,
            "gate_verdict_sha256_12": None, "measurement_status": "not_measured",
            "gate_verdict_class1": None, "gate_verdict_class1_green": None,
            "gate_verdict_class1_measurement_status": "not_measured",
            "gate_verdict_class1_why": "闸证据缺席 ⇒ class-1 判词同样缺席（不猜、不顶替）",
            "semantics": ("引用**上一次已完成**的权威闸跑（本次跑的 verdict 在 matrix 产完之前"
                          "不存在 ⇒ 自引用不可构造）；消费方须自己复算 sha256[:12] 对账")}
    if not path:
        return {**base, "why": "调用方未给 --gate-verdict-json ⇒ 闸证据缺席（not_measured）",
                "declared_path": None}
    fp = Path(path)
    if not fp.is_absolute():
        fp = (ROOT / fp)
    if not fp.is_file():
        return {**base, "why": f"声明的路径不是文件：{fp}", "declared_path": str(path)}
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
        gv = d.get("verdict")
        gvc1_raw = d.get("verdict_class1")
    except (OSError, ValueError) as exc:
        return {**base, "why": f"不可解析：{type(exc).__name__}: {exc}", "declared_path": str(path)}
    if not isinstance(gv, str) or not gv:
        return {**base, "why": "产物里没有 `verdict` 字面值 ⇒ 不猜", "declared_path": str(path),
                "resolved_path": str(fp)}
    try:
        rel = str(fp.resolve().relative_to(ROOT))
    except ValueError:
        rel = str(fp.resolve())
    gvc1 = (gvc1_raw.strip() or None) if isinstance(gvc1_raw, str) else None
    return {"gate_verdict": gv,
            "gate_verdict_green": bool(gv == nc.GATE_VERDICT_PASS),
            "gate_verdict_class1": gvc1,
            "gate_verdict_class1_green": (None if not gvc1
                                          else bool(gvc1 == nc.GATE_VERDICT_PASS)),
            "gate_verdict_class1_measurement_status": ("measured" if gvc1 else "not_measured"),
            "gate_verdict_class1_why": (None if gvc1 else
                                        "产物里没有 `verdict_class1` 字面值（该产物早于裁定 97.3）"
                                        "⇒ 不猜、不拿顶层 verdict 顶替"),
            "gate_run_dir": str(fp.resolve().parent),
            "gate_verdict_sha256_12": sha12(fp),
            "measurement_status": "measured",
            "declared_path": str(path), "resolved_path": rel,
            "gate_verdict_path": rel,
            "gate_generated_at": d.get("generated_at"),
            "gate_n_checks": d.get("n_checks"), "gate_n_red": d.get("n_red"),
            "gate_n_red_class1": d.get("n_red_class1"),
            "gate_triage_class_authority": d.get("triage_class_authority"),
            "gate_artifact": d.get("artifact"),
            "semantics": base["semantics"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    ap.add_argument("--env-frames", default=str(OUT_DEFAULT / "env_states_random/env_states.npz"))
    ap.add_argument("--env-frames-2", default=str(OUT_DEFAULT / "env_states_sweep/env_states.npz"),
                    help="第二份 env 采集（sweep 逐维激励）；当**held-out 评估帧**用，不参与建 stats")
    ap.add_argument("--env-frames-hold", default=str(OUT_DEFAULT / "env_states_hold/env_states.npz"),
                    help="hold 策略采集：真实的**近常量维**数据（对应 late_policy=hold 阶段，裁定 65-3）")
    ap.add_argument("--floor-coef-scale", type=float, default=1.0,
                    help="把所有下限系数乘这个数（0 = 关掉下限 ⇒ R1/Tb 必须变红；输入级变异体用）")
    ap.add_argument("--no-widen", action="store_true",
                    help="跳过 widen_to_cover（= 变异体：起态覆盖闸必须因此变红）")
    ap.add_argument("--coverage-target", default=nc.COVERAGE_TARGET_DECLARED_INTERVAL,
                    choices=nc.KNOWN_COVERAGE_TARGETS,
                    help=("**主线臂**的覆盖目标（裁定 87.3-1）。`declared_interval`（①，默认，强制）= "
                          "`must_cover` 为声明物理区间两端 ⇒ 任何物理合法状态都不产生非法 bin；"
                          "`build_only` = 修前口径（起态 + build 帧），**只**作裁定 87.3-2 条件 a 臂 1 的"
                          "对照，产物里逐行标 `coverage_target`，不得当交付档。"
                          "诊断/YAM 臂不吃这个开关（恒 build_only，理由见 matrix 的 "
                          "`coverage_ruling_87_3.scope_limitation`）"))
    ap.add_argument("--s1-frames", default=None,
                    help=("**已被裁定 85.4-2-1 撤销的入口**（B2 的 `states_14d.npz`）。保留只为读回旧产物做"
                          "逐位互核；主线请用 `--s1-lerobot`"))
    ap.add_argument("--s1-lerobot", default=None,
                    help=("主线入口（裁定 85.4-2）：B2 的 S1 数据集目录（含 `demo_manifest.json` + "
                          "`pi05_lerobot/`）或 lerobot 目录本身（含 `data/` + `meta/`）"))
    ap.add_argument("--s1-npz-crosscheck", default=None,
                    help=("只作互核的 npz（帧序/集号/方向码逐位比）。缺省 = 与 `--s1-frames` 同值；"
                          "两者都缺 ⇒ 产物如实记 `present=false`（formal 期就是这种情形）"))
    ap.add_argument("--consumer", default=None, choices=(None, *nc.KNOWN_CONSUMERS),
                    help=("这批 stats 的消费方。`bc` ⇒ 触发裁定 85.4-3 的同源硬闸（牙 Tp5）；"
                          "缺省 = 每档按自己的用途填（主线通路验证档 = path_check，诊断档 = diagnostic）"))
    ap.add_argument("--stats-provenance", default="auto",
                    choices=("auto", *nc.KNOWN_STATS_PROVENANCES, "unclassified_not_for_bc"),
                    help=("主线档 stats 的溯源标签（裁定 85.4-2/85.4-3）。`auto` = 从 "
                          "`demo_manifest.json` 的 `stage` + 集数自洽性判级（pilot ⇒ "
                          "`pilot10_path_check`；formal 且集数自洽 ⇒ `formal40_bc_source`；"
                          "判不了 ⇒ `unclassified_not_for_bc`，**故意**不在已知集合里 ⇒ 牙 Tp4 必红）。"
                          "显式指定需 D 的裁定支撑，C2 不自决。"
                          "**标签字面口径（裁定 87.4 更正）**：正典 = `pre_pilot5_path_check`，"
                          "`pilot10_path_check` = 别名（裁定 86.1 的字面被撤回为别名）。本档产物继续写"
                          "别名字面（D 原文『不值得为此改产物』），但**同时**落 "
                          "`stats_provenance_canonical` 把关系机器化 —— BC 硬闸只认 "
                          "`== formal40_bc_source`，任何别名都映射不到它 ⇒ 别名表不可能放宽准入。"
                          "已作废值：`mainline_s1_formal`（并入 `formal40_bc_source`）"))
    ap.add_argument("--yam-stats", default=str(YAM_STATS_DEFAULT))
    ap.add_argument("--start-pose", default="a2", choices=("a2", "collector"),
                    help="牙 (c) 的起态来源：a2 = A2 实测 hold_action_14d；collector = 本线采集的 reset 帧")
    ap.add_argument("--emit-yam", action="store_true", help="同时产 YAM 档（只用于必红分支验证）")
    ap.add_argument("--physical-range-json",
                    default=str(OUT_DEFAULT / "physical_range_correction/physical_range.json"),
                    help=("物理行程勘误件（`scripts/c2_fix_physical_range.py` 产）；存在则**优先于** "
                          "npz 里的 physical_range 字段（那个字段有两处已勘误的缺陷）"))
    ap.add_argument("--ignore-physical-range-json", action="store_true",
                    help="故意用 npz 里的旧 physical_range（只作对照/变异体；产物必须标注 superseded）")
    ap.add_argument("--gate-verdict-json", default=None,
                    help=("裁定 93.4：BC 准入要 AND 的**闸 verdict 产物**（某一次已完成跑的 "
                          "`gate_verdict.json`）。给了 ⇒ 逐行落 `gate_verdict` / "
                          "`gate_verdict_green` / `gate_run_dir` / `gate_verdict_sha256_12`；"
                          "没给 ⇒ 三值纪律记 `not_measured`（**不**写成 false，也**不**静默当绿），"
                          "此时 `consumer=bc` 的行会被牙 `Tbcad_admission_requires_green_gate` 判红"))
    args = ap.parse_args()

    out = Path(args.out_dir).resolve(); (out / "stats").mkdir(parents=True, exist_ok=True)
    rows, files = [], []
    # 本次 run 的起点时刻：裁定 93.6 的新鲜度牙 `Txr` 用它当参考窗口的左端
    # （右端 = matrix 的 `generated_at`，那是**写盘那一刻**盖的 ⇒ 见 `nc.crosscheck_freshness_tooth`
    # 文档串里登记的落点差异）。
    run_started_at = now_iso()
    gate_ref = resolve_gate_verdict(args.gate_verdict_json)

    # ---------- env 诊断档（两份采集合并） ----------
    env_frames_list, env_prov = [], []
    for p in (args.env_frames, args.env_frames_2):
        pp = Path(p)
        if pp.exists():
            fr, st0, pr, man = load_frames(pp)
            env_frames_list.append(fr)
            env_prov.append({"npz": str(pp.relative_to(ROOT)), "sha256_12": sha12(pp),
                             "n_frames": int(fr.shape[0]), "policy": man.get("policy"),
                             "five_tuple": man.get("five_tuple"), "shim": man.get("shim"),
                             "measured_control_hz": man.get("measured_control_hz"),
                             "not_for_mainline_normalizer": man.get("not_for_mainline_normalizer"),
                             "load_pair": man.get("load_pair")})
        else:
            env_prov.append({"npz": str(pp), "exists": False, "note": "declared_only：文件不存在，未参与"})
    if not env_frames_list:
        raise SystemExit("两份 env 采集都不存在 ⇒ 先跑 scripts/c2_collect_env_states.py")
    env_frames = np.concatenate(env_frames_list, axis=0)
    _pr_npz_path = (Path(args.env_frames) if Path(args.env_frames).exists()
                    else Path(args.env_frames_2))
    _, _, _prange_npz, man0 = load_frames(_pr_npz_path)
    prange, prange_interval, prange_prov = resolve_physical_range(args, _prange_npz, _pr_npz_path)

    if args.start_pose == "a2":
        start_pose, sp_prov = start_pose_from_a2()
    else:
        _, st0, _, _ = load_frames(Path(args.env_frames))
        start_pose, sp_prov = st0, {"source": "collector reset frame", "abs_max": float(np.abs(st0).max())}

    env_stats = nc.build_stats(env_frames)
    features = {"observation.state": {"type": "state", "shape": (int(env_frames.shape[1]),)}}

    ks = float(args.floor_coef_scale)
    combos = ([(nc.CASE_QUANTILES_FLOOR, "F1_physical_range_fraction", c * ks) for c in nc.F1_CANDIDATES] +
              [(nc.CASE_QUANTILES_FLOOR, "F2_noise_scale_multiple", c * ks) for c in nc.F2_CANDIDATES] +
              [(nc.CASE_IDENTITY_EXPLICIT, "F1_physical_range_fraction", c * ks) for c in nc.F1_CANDIDATES] +
              [(nc.CASE_IDENTITY_EXPLICIT, "F2_noise_scale_multiple", c * ks) for c in nc.F2_CANDIDATES])

    def run_source(source, frames, base_stats, pr, prov, rep_prefix, mainline, eval_frames=None,
                   widen=True, tag="", force_blocking=False, stats_provenance=None, consumer=None,
                   expected_verdict=None, is_must_red_branch=False, is_stress_branch=False,
                   file_suffix="", allowed_red_teeth=None, arm="", all_frames=None,
                   coverage_target=nc.COVERAGE_TARGET_BUILD_ONLY,
                   physical_interval_override=None, interval_source_sha256_12=None,
                   rep_ver_extra="", rep_ver_n=1, derive_allowed=False):
        # 覆盖区间：主线臂用**它自己那份**出处（勘误件的声明区间，与 frames 同一次解析），
        # 诊断臂沿用 env 侧解析出来的那份。两者数值同源（同一份勘误件），但**出处必须逐臂登记**，
        # 否则"用了哪一份声明区间"就变成读者要自己去猜的事（裁定 87.7 的附带义务）。
        iv_use = prange_interval if physical_interval_override is None else physical_interval_override
        for case, fam_name, coef in combos:
            # 版本串**值派生**（裁定 83§5 / A2 `vla_runtime` 范式）：覆盖目标与头寸由
            # `nc.coverage_version_token()` 从实际取值算出并拼进去，声明区间的哈希也在里面
            # ⇒ 换了区间而版本号不变这种事在构造上就做不到。
            cov_tok = nc.coverage_version_token(
                target=coverage_target, headroom_bins=HEADROOM_BINS,
                cover_cap=(iv_use if coverage_target == nc.COVERAGE_TARGET_DECLARED_INTERVAL else None),
                interval_source_sha256_12=interval_source_sha256_12)
            rep_version = (f"{rep_prefix}{tag}-{case}-{fam_name}-coef{coef}"
                           f"{rep_ver_extra}-{cov_tok}-v{rep_ver_n}").replace("_", "-")
            built = build_case(frames=frames, base_stats=base_stats, prange=pr, case=case,
                               family=fam_name, coef=coef, source=source,
                               rep_version=rep_version, prov=prov,
                               must_cover=(start_pose, frames), widen=widen,
                               stats_provenance=stats_provenance, consumer=consumer,
                               coverage_target=coverage_target, physical_interval=iv_use,
                               start_pose=start_pose,
                               interval_source_sha256_12=interval_source_sha256_12)
            name = f"{source}__{case}__{fam_name}_{coef}{file_suffix}.json"
            fp = out / "stats" / name
            fp.write_text(json.dumps(built["payload"], ensure_ascii=False, indent=2), encoding="utf-8")
            files.append({"path": str(fp.relative_to(ROOT)), "sha256_12": sha12(fp),
                          "bytes": fp.stat().st_size, "case": case, "family": fam_name, "coef": coef,
                          "source": source, "representation_version": rep_version})
            verdict, red, teeth, warn, _res = eval_verdict(
                case=case, stats=built["stats"], frames=frames, start_pose=start_pose,
                source=source, features=features, physical_range=pr, mainline=mainline,
                eval_frames=eval_frames, force_blocking=force_blocking,
                physical_interval=iv_use,
                stats_provenance=stats_provenance, consumer=consumer,
                coverage_target=coverage_target,
                # 裁定 93.2：`Tres_per_dim_resolution_floor` 的口径是**全量帧**（build ∪ held-out）
                # ⇒ 必须把 `all_frames` 显式喂进契约层，不能让它自己拼（拼出来的口径要能被发现）。
                # 裁定 93.4：BC 准入要 AND 的闸 verdict 由 `--gate-verdict-json` 解析而来。
                all_frames=all_frames,
                gate_verdict=gate_ref.get("gate_verdict"),
                gate_run_dir=gate_ref.get("gate_run_dir"),
                gate_verdict_sha256_12=gate_ref.get("gate_verdict_sha256_12"),
                gate_verdict_class1=gate_ref.get("gate_verdict_class1"))
            rt = roundtrip_from_file(fp, case=case, frames=frames, start_pose=start_pose,
                                     source=source, features=features, physical_range_fallback=pr,
                                     mainline=mainline, eval_frames=eval_frames,
                                     force_blocking=force_blocking, in_memory_verdict=verdict,
                                     physical_interval=iv_use, consumer=consumer,
                                     coverage_target_expected=coverage_target,
                                     all_frames=all_frames,
                                     gate_verdict=gate_ref.get("gate_verdict"),
                                     gate_run_dir=gate_ref.get("gate_run_dir"),
                                     gate_verdict_sha256_12=gate_ref.get("gate_verdict_sha256_12"),
                                     gate_verdict_class1=gate_ref.get("gate_verdict_class1"))
            if rt.get("bc_admission_file_vs_recomputed_agree") is False:
                red = list(red) + [f"Trt_bc_admission_stale 落盘 bc_admission 与当前契约层重判不一致: "
                                   f"required=agree observed=file={rt['bc_admission_from_file']} "
                                   f"recomputed={rt['bc_admission_recomputed']}"]
                verdict = "RED"
            if not rt["match"]:
                red = list(red) + [f"{rt['tooth_id']} 落盘文件复算与内存判定不一致: "
                                   f"required=verdict=={verdict} observed={rt['verdict_from_file']}"]
                verdict = "RED"
            rep = nc.dim_report(eval_frames if eval_frames is not None else frames,
                                built["stats"], case=case, physical_range=pr)
            # 全量口径（build ∪ held-out）的第三份报告：裁定 90.4-3 的触发判据在 held-out 子集上
            # 与在全量上**结论相反**（探针实测）⇒ 两个口径都必须落盘，由 D 定哪个管触发。
            rep_all = (None if all_frames is None else
                       nc.dim_report(all_frames, built["stats"], case=case, physical_range=pr))
            # 近常量维三计数（纯测量，不受 blocking/applies_when 影响）：
            # marked = 原始分位距 < 0.02×行程；unprotected = 其中 floor==0；
            # immaterial = 其中 floor < 0.02×行程（有下限但**实质上等于没有**）。
            # rel_tol **显式传**：不依赖函数默认值（本轮实测过默认值与阈值类分叉的缺陷）
            _ncd = nc.near_constant_dims({**built["stats"], "physical_range": pr},
                                         rel_tol=nc.NEAR_CONSTANT_REL_TOL)
            _fl = np.asarray(built["floors"], dtype=np.float64)
            _prs = np.where(np.asarray(pr, dtype=np.float64) > 0, np.asarray(pr, dtype=np.float64), 1.0)
            _th0 = nc.ContractThresholds()
            near_const = {"rel_tol": _th0.near_constant_rel_tol,
                          "rel_tol_matches_gate_threshold": bool(
                              _th0.near_constant_rel_tol == nc.NEAR_CONSTANT_REL_TOL),
                          "n_dims": len(_ncd), "dims": _ncd,
                          "n_unprotected": int(sum(1 for d in _ncd if _fl[d] <= 0)),
                          "unprotected_dims": [int(d) for d in _ncd if _fl[d] <= 0],
                          "n_immaterial": int(sum(1 for d in _ncd
                                                  if _fl[d] < _th0.floor_materiality_fraction * _prs[d])),
                          "immaterial_dims": [int(d) for d in _ncd
                                              if _fl[d] < _th0.floor_materiality_fraction * _prs[d]],
                          "floor_min_on_marked": (None if not _ncd else float(_fl[_ncd].min())),
                          "materiality_ratio_min": (None if not _ncd else
                                                    float((_fl[_ncd] / (_th0.floor_materiality_fraction * _prs[_ncd])).min()))}
            # ---- "允许红的牙"：主线臂**由测量派生**；其它臂沿用调用方给的静态清单 ----
            # 为什么主线臂不用静态清单：见 `derive_allowed_red_from_measurement` 的注释
            # （静态清单形式上是"先看到红再写白名单"，换数据集会退化成红洗白器）。
            derived = None
            rep_build = None
            if derive_allowed:
                conf_row = ((_res or {}).get("declared_interval_conformance")
                            or nc.declared_interval_conformance(frames, iv_use))
                rep_build = nc.dim_report(frames, built["stats"], case=case, physical_range=pr)
                derived = derive_allowed_red_from_measurement(
                    red_ids=sorted({x.split(" ")[0] for x in (red or [])}),
                    rep_eval=rep, rep_build=rep_build, conformance=conf_row,
                    base_stats=base_stats, eval_frames=eval_frames, family=fam_name,
                    near_constant=near_const, coverage_target=coverage_target,
                    stats_provenance=stats_provenance, consumer=consumer, rep_all=rep_all)
            if derived is not None:
                art = derived["allowed_red_teeth"]
                unexplained = derived["unexplained_red_teeth"]
            else:
                art = allowed_red_teeth
                if isinstance(art, dict):
                    art = art.get(fam_name, art.get("*"))
                unexplained = (sorted(set(x.split(" ")[0] for x in (red or [])) - set(art))
                               if art else None)
            rows.append({"source": source, "case": case, "family": fam_name, "coef": coef,
                         "tag": tag, "widen_to_cover": not args.no_widen,
                         "stats_provenance": nc.normalize_provenance(stats_provenance),
                         "stats_provenance_canonical": nc.canonical_provenance(stats_provenance),
                         "consumer": consumer,
                         "bc_admission": nc.bc_admission(stats_provenance),
                         "coverage_target": coverage_target,
                         "coverage_target_authority": nc.COVERAGE_TARGET_AUTHORITY.get(coverage_target),
                         "coverage_block": built["payload"].get("coverage"),
                         "declared_interval_conformance": (_res or {}).get("declared_interval_conformance"),
                         "expected_verdict": expected_verdict,
                         "allowed_red_teeth": (sorted(art) if art else None),
                         "allowed_red_authorization": (None if derived is None
                                                       else derived["allowed_red_authorization"]),
                         "red_dim_attribution": (None if derived is None else derived["red_dim_attribution"]),
                         "allowed_red_facts": (None if derived is None else derived["facts"]),
                         "escalations_to_d": (None if derived is None else derived["escalations_to_d"]),
                         "ruled_escalations": (None if derived is None
                                               else derived.get("ruled_escalations")),
                         "allowed_red_derivation": (None if derived is None else "measured_this_run"),
                         "unexplained_red_teeth": unexplained,
                         "is_must_red_branch": bool(is_must_red_branch),
                         "is_stress_branch": bool(is_stress_branch),
                         "n_build_frames": int(frames.shape[0]),
                         "n_eval_frames": int((eval_frames if eval_frames is not None else frames).shape[0]),
                         "eval_frames_are_held_out": eval_frames is not None,
                         # `*_heldout` 牙名在本行成不成立，必须**行级**也可读（与牙级 `eval_scope`
                         # 同源：都调 `nc.eval_scope_of`，两处不可能各说各话）。
                         "eval_scope": nc.eval_scope_of(eval_frames),
                         "coverage_target_roundtrip_agrees": rt.get("coverage_target_agrees_with_build"),
                         "mainline": mainline, "representation_version": rep_version,
                         "stats_file": name,
                         "stats_file_sha256_12": sha12(fp),
                         "arm": arm,
                         "verdict": verdict, "red": red,
                         "red_ids": sorted({x.split(" ")[0] for x in (red or [])}),
                         "teeth": teeth, "warnings": warn, "roundtrip": rt,
                         # ---- 裁定 93.2 / 93.4 的行级登记（**新增字段，不替换任何既有字段**）----
                         # 为什么行级也要落：`summary_all` 是给「三个口径并排读」的，而下面这两个字段回答的是
                         # 「本行的 `Tres` 到底在哪个口径上判的」与「本行的 BC 准入引的是哪一次闸跑」
                         # ⇒ 少了它们，读者无法从行本身复算这两颗牙（附录 02:274「缓存不得冒充表示」同族）。
                         "resolution_caliber": (_res or {}).get("resolution_caliber"),
                         "resolution_caliber_note": (_res or {}).get("resolution_caliber_note"),
                         "n_frames_resolution_caliber": (_res or {}).get(
                             "n_frames_resolution_caliber"),
                         "bins_occupied_per_dim_resolution_caliber": (_res or {}).get(
                             "bins_occupied_per_dim_resolution_caliber"),
                         # ---- 裁定 94.3 的两个登记字段（裁定 95.1-1：Ⅱ 类「登记不阻塞」）----
                         # WHY 行级也要落：正确性族（`HELDOUT_FAMILY_TEETH` 及 Te1/Tcov/Tesc）的对象是
                         # held-out 帧，读者要能从**本行**看出这些牙在哪几维上根本无从触发
                         # （缺陷类 ⑲：报了绿、而绿来自覆盖不全）。
                         # 三值纪律：本臂无 held-out 划分 ⇒ None + `not_measured`（不写 []、不写 0）。
                         "heldout_bins_occupied_per_dim": (_res or {}).get(
                             "heldout_bins_occupied_per_dim"),
                         "correctness_blind_dims": (_res or {}).get("correctness_blind_dims"),
                         "correctness_blind_dims_status": (_res or {}).get(
                             "correctness_blind_dims_status"),
                         "bc_admission_with_gate": (_res or {}).get("bc_admission_with_gate"),
                         "gate_verdict_reference": gate_ref,
                         "near_constant": near_const,
                         "summary": summarize(rep),
                         "summary_build": (None if rep_build is None else summarize(rep_build)),
                         "summary_all": (None if rep_all is None else summarize(rep_all)),
                         "n_all_frames": (None if all_frames is None else int(all_frames.shape[0])),
                         "summary_calibers": {
                             "summary": ("heldout（按集留出的评估帧）" if eval_frames is not None
                                         else "build（本臂无 held-out 划分 ⇒ 与 summary_build 同源）"),
                             "summary_build": "build（建 stats 用的帧）",
                             "summary_all": ("all（build ∪ held-out = 全量帧；裁定 90.4-3 触发判据的"
                                             "**另一口径**）" if rep_all is not None
                                             else "not_measured（调用方未给 all_frames）")},
                         "floor": np.asarray(built["floors"]).tolist(),
                         "not_for_mainline_normalizer": built["payload"]["not_for_mainline_normalizer"]})

    # 诊断档 A：random 的 **ep0 建 stats、ep1 当同分布 held-out 评估帧**（按集切，不按策略切）
    rnd = np.asarray(env_frames_list[0], dtype=np.float64)
    half = rnd.shape[0] // 2
    build_frames = rnd[:half]
    eval_frames = rnd[half:]
    build_stats = nc.build_stats(build_frames)
    diag_prov = {"build_frames": env_prov[:1], "eval_frames": env_prov[1:2],
                 "start_pose": sp_prov,
                 "physical_range_provenance": {**prange_prov,
                                               "npz_declared": man0.get("physical_range_provenance")},
                 "tier": "diagnostic_only（裁定 52：不得进主线部署包）"}
    run_source(nc.SOURCE_ENV_DERIVED, build_frames, build_stats, prange, diag_prov,
               "env-derived-diagnostic", mainline=False, eval_frames=eval_frames,
               widen=not args.no_widen, file_suffix="__randomphase", arm="env_randomphase",
               stats_provenance=nc.STATS_PROVENANCE_ENV_DIAGNOSTIC, consumer=nc.CONSUMER_DIAGNOSTIC)

    # 诊断档 A-stress：**跨策略**（random 建、sweep 评）⇒ 牙 Td 必须红（否则 Td 没牙）
    if len(env_frames_list) > 1:
        sweep = np.asarray(env_frames_list[1], dtype=np.float64)
        run_source(nc.SOURCE_ENV_DERIVED, build_frames, build_stats, prange,
                   {**diag_prov, "tier": "diagnostic_only · cross_policy_stress",
                    "expected": "Td 必须红：random 的 q01/q99 覆盖不住 sweep 的状态分布"},
                   "env-derived-crosspolicy", mainline=False, eval_frames=sweep,
                   tag="-stress", widen=not args.no_widen, force_blocking=True,
                   file_suffix="__crosspolicy_stress", arm="env_crosspolicy_stress",
                   stats_provenance=nc.STATS_PROVENANCE_ENV_DIAGNOSTIC, consumer=nc.CONSUMER_DIAGNOSTIC,
                   expected_verdict="RED", is_stress_branch=True)
        for r in rows[-len(combos):]:
            r["is_stress_branch"] = True
            r["expected_verdict"] = "RED"
            # ⚠ 修前这里写的是 `["Td_clip_ratio_cap"]` —— 一个**盘上从未存在过的牙 id**
            #   （本轮闸侧 `tooth_name_citation_audit` 实测抓到；同族的 3 处在
            #   `harness/norm_contract.py` 的散文里，已一并修）。它是"设计意图"字段，
            #   没有任何代码消费它 ⇒ 写错也不会报错，正好是缺陷类 ⑮（名实不符）的静默形态。
            #   修后由闸 `name_semantics_audit` 规则 6 机器核：这里写的每个 id 都必须
            #   ①真实存在于本行的牙集合、②在本行确实是红的（stress 臂的设计判据 = pred_G3 的
            #   `{Td2, Te2}`，不把 `Tsat` 写进来：Tsat 红是数据事实、不是本分支的设计要求）。
            r["expected_red_teeth"] = ["Td2_clip_heldout", "Te2_no_illegal_bin_heldout"]

    # 诊断档 B：**hold 策略**的真实近常量维（= late_policy=hold 阶段会遇到的分布，裁定 65-3）
    hp = Path(args.env_frames_hold)
    if hp.exists():
        hf, hstart, _hpr_npz, hman = load_frames(hp)
        hstats = nc.build_stats(hf)
        # hold 档与 env 档共用同一份**勘误后**的物理行程：分母不同源 ⇒ 跨档不可比
        hpr = prange
        run_source(nc.SOURCE_ENV_DERIVED, hf, hstats, hpr,
                   {"build_frames": [{"npz": str(hp.relative_to(ROOT)), "sha256_12": sha12(hp),
                                      "n_frames": int(hf.shape[0]), "policy": hman.get("policy"),
                                      "five_tuple": hman.get("five_tuple"),
                                      "measured_control_hz": hman.get("measured_control_hz")}],
                    "start_pose": sp_prov,
                    "physical_range_provenance": hman.get("physical_range_provenance"),
                    "tier": "diagnostic_only · near_constant_real_data",
                    "why": ("hold 策略下每一维都近常量 ⇒ 这是**真实测量**的近常量数据，"
                            "用来量下限有没有生效（floor_binding / bin 占用 / 是否饱和）。"
                            "对应裁定 65-3 的 late_policy=hold：机器人保持旧动作时状态几乎不动，"
                            "归一化若把这点噪声放大就会饱和。")},
                   "env-derived-holdphase", mainline=False, eval_frames=None, tag="-holdphase",
                   widen=not args.no_widen, file_suffix="__holdphase", arm="env_holdphase",
                   stats_provenance=nc.STATS_PROVENANCE_ENV_DIAGNOSTIC, consumer=nc.CONSUMER_DIAGNOSTIC)
    else:
        rows.append({"source": nc.SOURCE_ENV_DERIVED, "tag": "-holdphase", "verdict": "SKIPPED",
                     "reason": f"{hp} 不存在 ⇒ 不伪造近常量档", "red": []})
        # 三态（红线 88.3-1）：跳过 ≠ 通过。这里没有覆盖目标可言，显式写 null + 原因，
        # 不靠"字段不存在"让读者猜（`targets_by_arm` 会把它聚合成 `<skipped>`）。
        rows[-1]["coverage_target"] = None
        rows[-1]["coverage_target_why"] = "本行 SKIPPED（hold 采集不在）⇒ 没有构造覆盖集，未测得"

    if args.emit_yam:
        yp = Path(args.yam_stats)
        if not yp.exists():
            raise SystemExit(f"--emit-yam 但 YAM stats 不存在：{yp}")
        yarr, yprov = yam_stats_arrays(yp)
        ystats = dict(yarr)
        ystats["median"] = yarr.get("median", yarr["mean"])
        ystats["span_q99_q01"] = yarr["q99"] - yarr["q01"]
        ystats["noise_mad_step"] = np.full(14, np.nan)      # YAM 档没有逐步差分（不是同一形态）
        ystats["step_abs_median"] = np.full(14, np.nan)
        # YAM 档只用 env 的**起态**当必红分支输入：把 YAM stats 喂 ViperX300 必须红（裁定 49.1）
        for case, fam_name, coef in [(nc.CASE_QUANTILES_FLOOR, "F1_physical_range_fraction", nc.F1_CANDIDATES[0])]:
            fam = nc.floor_family(fam_name, coef)
            floors = np.zeros(14)          # YAM 档**故意不给下限**：R1 必须红
            st = dict(ystats); st["floor"] = floors
            st["denom_raw"] = ystats["span_q99_q01"]; st["denom_effective"] = ystats["span_q99_q01"]
            # ViperX300 的物理行程一并落盘：必红分支的前提就是"YAM 的 stats 喂 ViperX300"，
            # 判据里用到的行程必须能在文件里复算（round-trip 自洽）。
            st["physical_range"] = prange
            payload = nc.stats_payload(stats=st, case=case, source=nc.SOURCE_YAM_ABC130K, floors=floors,
                                       family=fam, representation_version="yam-abc130k-mustred-branch-v1",
                                       provenance=yprov,
                                       stats_provenance=nc.STATS_PROVENANCE_YAM_MUSTRED,
                                       consumer=nc.CONSUMER_DIAGNOSTIC)
            name = f"{nc.SOURCE_YAM_ABC130K}__{case}__{fam_name}_{coef}.json"
            fp = out / "stats" / name
            fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            files.append({"path": str(fp.relative_to(ROOT)), "sha256_12": sha12(fp),
                          "bytes": fp.stat().st_size, "case": case, "family": fam_name, "coef": coef,
                          "source": nc.SOURCE_YAM_ABC130K,
                          "representation_version": payload["representation_version"]})
            verdict, red, teeth, warn, _res = eval_verdict(
                case=case, stats=st, frames=env_frames, start_pose=start_pose,
                source=nc.SOURCE_YAM_ABC130K, features=features, physical_range=prange,
                mainline=True, physical_interval=prange_interval,
                stats_provenance=nc.STATS_PROVENANCE_YAM_MUSTRED, consumer=nc.CONSUMER_DIAGNOSTIC)
            rt = roundtrip_from_file(fp, case=case, frames=env_frames, start_pose=start_pose,
                                     source=nc.SOURCE_YAM_ABC130K, features=features,
                                     physical_range_fallback=prange, mainline=True,
                                     eval_frames=None, force_blocking=False,
                                     in_memory_verdict=verdict, physical_interval=prange_interval,
                                     consumer=nc.CONSUMER_DIAGNOSTIC)
            if not rt["match"]:
                red = list(red) + [f"{rt['tooth_id']} 落盘文件复算与内存判定不一致: "
                                   f"required=verdict=={verdict} observed={rt['verdict_from_file']}"]
                verdict = "RED"
            rows.append({"source": nc.SOURCE_YAM_ABC130K, "case": case, "family": fam_name, "coef": coef,
                         "mainline": True, "representation_version": "yam-abc130k-mustred-branch-v1",
                         "stats_provenance": nc.STATS_PROVENANCE_YAM_MUSTRED,
                         "consumer": nc.CONSUMER_DIAGNOSTIC,
                         "bc_admission": nc.bc_admission(nc.STATS_PROVENANCE_YAM_MUSTRED),
                         "allowed_red_teeth": None, "unexplained_red_teeth": None,
                         "red_ids": sorted({x.split(" ")[0] for x in (red or [])}),
                         "stats_file": name, "stats_file_sha256_12": sha12(fp),
                         "arm": "yam_mustred", "verdict": verdict, "red": red, "teeth": teeth,
                         "warnings": warn, "roundtrip": rt,
                         # 本臂**不传** eval_frames ⇒ 契约层 `eval_x = frames`（in-sample）。
                         # 修前这两个键在本行**缺失**（读者只能从牙名猜），现按契约层实测值补上。
                         "eval_frames_are_held_out": bool((_res or {}).get("eval_frames_are_held_out", False)),
                         "eval_scope": (_res or {}).get("eval_scope") or nc.EVAL_SCOPE_NO_SPLIT,
                         "expected_verdict": "RED", "is_must_red_branch": True,
                         "summary": None, "floor": floors.tolist(),
                         # YAM 必红臂**根本不做覆盖展宽**（YAM 的 q01/q99 原样喂 ViperX300，
                         # 且故意不给下限）⇒ 覆盖目标不适用。写 null 而不是 `build_only`：
                         # `build_only` 意味着"用起态+build 帧展宽过"，本臂没展宽，标错就是谎报口径。
                         "coverage_target": None,
                         "coverage_target_why": ("必红分支不做 widen_to_cover（`stats_payload` 直接落 YAM 的 "
                                                 "q01/q99）⇒ 覆盖目标不适用；牙 Tcov/Tiv 出 N_A 是正确极性"),
                         "not_for_mainline_normalizer": True})

    # ---------- 主线档（S1）：没数据就不产文件，只登记状态 ----------
    # 入口优先级（裁定 85.4-2）：`--s1-lerobot`（主线，直读 parquet）> `--s1-frames`（npz，**已撤销**的入口）。
    # 两者都给 ⇒ lerobot 为准、npz 只作逐位互核对象。路径口径：脚本内部多处做 `relative_to(ROOT)`
    # ⇒ 相对路径必须先经 ROOT absolutize（01:4x 实测到过 ValueError）。
    lr_res = resolve_lerobot_dirs(Path(args.s1_lerobot)) if args.s1_lerobot else None
    if args.s1_frames:
        s1 = Path(args.s1_frames)
        # 用 `absolute()` 而不是 `resolve()`（同 `resolve_lerobot_dirs` 的口径，见 :422 的注释）：
        # 变异体副本里的 `runs` 是指向真 `runs/` 的**符号链接**，`resolve()` 会 canonicalize 到真仓
        # 路径 ⇒ 逃出该副本的 ROOT ⇒ 下游 `relative_to(ROOT)` 抛 ValueError。
        # **本轮实测到的真缺陷**（不是假想）：主线臂改成 npz 权威接口（裁定 90.4-4）之后，
        # 所有 mainline 档文件级变异体（M10/M12/M13/M14/M15/M18/M21/…）都在 :2591 崩掉、
        # 连 matrix 都不产 ⇒ 翻转台账拿不到任何 mainline 侧的实测翻转（= 牙无法被证明）。
        s1 = s1 if s1.is_absolute() else (ROOT / s1).absolute()
    else:
        s1 = None
    xnpz = Path(args.s1_npz_crosscheck) if args.s1_npz_crosscheck else s1
    if xnpz is not None:
        xnpz = xnpz if xnpz.is_absolute() else (ROOT / xnpz).absolute()
        if not xnpz.exists():
            xnpz = None
    mainline_finding = None
    mainline_reader_evidence = None
    # 裁定 90.4-4 之后 S1 有**两个**读路径臂，两个都可能在同一次运行里跑 ⇒ 臂状态必须先初始化，
    # 否则"哪个臂跑了"这件事只能靠变量是否存在来猜（NameError 或静默读成 None，两者都坏）。
    mainline_status = None
    crosscheck_finding = None
    crosscheck_reader_evidence = None
    crosscheck_status = None
    lr_frames = None                 # 交叉核对臂的帧（给权威臂做读路径互核用）
    lr_ep_sorted = None
    bc_arm_built = False             # BC 准入必红臂只建一次（两个读路径都给时由交叉核对臂建，更贴题）
    npz_authority_ran = False

    if lr_res is not None:
        # ===== 主线入口：直读 π₀.₅ LeRobot 出口的 parquet（裁定 85.4-2）=====
        if not lr_res["demo_manifest_exists"]:
            raise SystemExit(f"[RED] demo_manifest.json 不在：{lr_res['demo_manifest']} ⇒ "
                             f"无法判定数据集身份（pilot/formal），拒绝产主线 stats（不拿别的档顶替）")
        man = json.loads(lr_res["demo_manifest"].read_text(encoding="utf-8"))
        lf = load_frames_lerobot(lr_res)
        fr = lf["frames"]
        if lf["state_dim"] != 14:
            raise SystemExit(f"[RED] observation.state 维度 = {lf['state_dim']}，不是 14 ⇒ 契约维度不符，拒绝")
        # 留给权威臂（npz）做**读路径互核**：裁定 90.4-4 的"两条读路径逐位等价"必须在本产物里
        # 也有一份 C2 自己的复算，不能只引 D 的结论（`crosscheck_npz_vs_lerobot`）。
        lr_frames = fr
        lr_ep_sorted = lf["episode_index_sorted"]
        pr, pr_interval_s1, pr_prov = resolve_physical_range_lerobot(args, fr)
        dc = direction_from_two_sources(lr_res, lf, man)
        dc_x = crosscheck_direction_vs_npz(dc, xnpz)
        fr_x = crosscheck_frames_vs_npz(lf, xnpz)
        ep_x = crosscheck_episodes_vs_npz(lf, xnpz)
        dc["cross_check_vs_b2_npz"] = dc_x
        if dc["n_episodes_with_unknown_direction"]:
            raise SystemExit(f"[RED] {dc['n_episodes_with_unknown_direction']} 集的方向码推不出来"
                             f"（来源 A = demo_manifest.task_text → meta/tasks.parquet）⇒ "
                             f"按方向各留一整集的 held-out 划分无法成立，拒绝产 stats（不假装切过）")
        ep_dir = {int(k): int(v) for k, v in dc["ep_dir"].items()}
        if args.stats_provenance == "auto":
            prov_label, prov_why = auto_stats_provenance_lerobot(lr_res, man, lf, dc)
        else:
            prov_label, prov_why = args.stats_provenance, "命令行显式指定（需 D 的裁定支撑）"
        cc = (man.get("contract_conflict") or {})
        # 契约字面（夹爪 1.0）与 C2 现行口径（0.91001）的冲突：**只登记不使用**，C2 不代改契约文本
        b2_npz_man = None
        if xnpz is not None and (xnpz.parent / "manifest.json").exists():
            b2_npz_man = json.loads((xnpz.parent / "manifest.json").read_text(encoding="utf-8"))
            cc = cc or (b2_npz_man.get("contract_conflict") or {})
        fr_build, fr_eval, split_rec = split_heldout_by_episode_arrays(
            fr, lf["episode_index_sorted"], ep_dir)
        # 划分自证：build 与 eval 的集号**不得相交**（这是"按集切"这句话唯一的可测形式）
        ep_b = sorted(set(int(e) for e in lf["episode_index_sorted"][
            ~np.isin(lf["episode_index_sorted"], split_rec.get("held_out_episodes") or [])].tolist()))
        ep_e = sorted(set(int(e) for e in (lf["episode_index_sorted"][
            np.isin(lf["episode_index_sorted"], split_rec.get("held_out_episodes") or [])].tolist())))
        split_rec["build_episodes"] = ep_b
        split_rec["eval_episodes"] = ep_e
        split_rec["episode_sets_disjoint"] = bool(not (set(ep_b) & set(ep_e)))
        split_rec["n_build_plus_eval_equals_total"] = bool(
            split_rec.get("n_build_frames", 0) + split_rec.get("n_eval_frames", 0) == lf["n_frames"])
        s1_stats = nc.build_stats(fr_build)
        consumer_main = args.consumer or nc.CONSUMER_PATH_CHECK
        sp_xcheck = None
        if lf["start_poses"].size:
            d_sp = np.abs(lf["start_poses"] - start_pose[None, :]).max(axis=1)
            sp_xcheck = {"n_start_poses": int(lf["start_poses"].shape[0]),
                         "max_abs_diff_vs_a2_start_pose": float(d_sp.max()),
                         "all_equal_to_a2_start_pose": bool(np.all(d_sp <= 1e-9)),
                         "per_episode_max_abs_diff": [float(x) for x in d_sp.tolist()],
                         "note": ("起态口径：本档仍用 A2 的 `hold_action_14d`（部署起态；D §14-5-4 认定"
                                  "起态位姿是几何量、不随控制频率变化）。这里只**交叉核验** lerobot 的"
                                  " 每集 frame_index==0 与它是否同一位姿，不静默换源")}
        lr_prov = {
            "frames": [{"reader": "--s1-lerobot（直读 parquet，裁定 85.4-2）",
                        "dataset_dir": lr_res["dataset_dir_rel"],
                        "lerobot_dir": lr_res["lerobot_dir_rel"],
                        "path_interpretation": lr_res["interpretation"],
                        "demo_manifest": rel(lr_res["demo_manifest"]),
                        "demo_manifest_sha256_12": lr_res["demo_manifest_sha256_12"],
                        "demo_manifest_mtime": lr_res["demo_manifest_mtime"],
                        "demo_manifest_generated_at": man.get("generated_at"),
                        "dataset_stage": man.get("stage"),
                        "dataset_gates": (man.get("gates") or {}).get("verdict"),
                        "dataset_gates_n_checks": (man.get("gates") or {}).get("n_checks"),
                        "dataset_gates_n_red": (man.get("gates") or {}).get("n_red"),
                        "representation_version_of_dataset": man.get("representation_version"),
                        "parquet_files": lf["parquet_files"],
                        "stray_parquet_outside_chunk_glob": lf["stray_parquet_outside_chunk_glob"],
                        "n_frames": lf["n_frames"], "n_episodes": lf["n_episodes"],
                        "per_episode": {str(k): v for k, v in lf["per_episode"].items()},
                        "grouping": {"sort_key": lf["sort_key"],
                                     "raw_order_already_grouped_sorted": lf["raw_order_already_grouped_sorted"],
                                     "reorder_was_material": lf["reorder_was_material"],
                                     "frame_index_contiguous_per_episode": lf["frame_index_contiguous_per_episode"],
                                     "n_frame_index_gaps": lf["n_frame_index_gaps"],
                                     "frame_index_gaps": lf["frame_index_gaps"]},
                        "index_column_is_global_arange": lf["index_column_is_global_arange"],
                        "crosscheck_vs_b2_npz_frames": fr_x,
                        "crosscheck_vs_b2_npz_episode_index": ep_x}],
            "start_pose": sp_prov,
            "start_pose_extraction": lf["start_pose_extraction"],
            "start_pose_crosscheck": sp_xcheck,
            "state_dtype_source": lf["dtype_declaration"]["state_dtype_source"],
            "dtype_declaration": lf["dtype_declaration"],
            "upcast_bitwise_lossless": lf["upcast_bitwise_lossless"],
            "parquet_storage_dtype": lf["parquet_storage_dtype"],
            "direction": dc,
            "tier": ("**主线 BC 同源档**（裁定 85.4-3：与 BC 训练数据同源）"
                     if prov_label == nc.STATS_PROVENANCE_FORMAL40_BC
                     else "**通路验证档**（裁定 85.4-3：用途限定三项 —— ① 端到端验证契约层吃真·主线形态数据；"
                          "② 实测每维 q01–q99 对 ctrlrange 的覆盖率与饱和维数；③ 验 Tr1 修复后的闸在真数据上有牙。"
                          "**不得进 BC**）"),
            "stats_provenance": prov_label,
            "stats_provenance_why": prov_why,
            "bc_admission": nc.bc_admission(prov_label),
            "physical_range": pr_prov,
            "physical_range_caliber_rule": pr_prov["caliber_rule"],
            "heldout_split": split_rec,
            "b2_contract_conflict": {
                "status_reported_by_b2": cc.get("status"),
                "status_after_ruling_87_6": "RULED_by_87_6（C2 侧不再登记为 OPEN；B2 的 registry 由 B2 自己闭合）",
                "contradiction": cc.get("contradiction"),
                "relative_diff_pct": cc.get("relative_diff_pct"),
                "d_ruling_87_6": {
                    "ruling": "契约文本**不得硬编码任何夹爪数值**（根因修法，不在 1.0 与 0.91001 之间选数）",
                    "new_contract_text": ("各维取值范围 = **主线数据的同源实测值**（B2 npz / parquet 的 "
                                          "`physical_range_effective`，与 `frames` 同源）。"
                                          "`scripts/c2_collect_env_states.py` 是**诊断专用源**，数值"
                                          "**不得移植进主线**。契约里出现的任何具体数字（含旧文本的 "
                                          "『夹爪维 = 1.0』）一律为**登记项、不是判据**"),
                    "why_not_pick_a_number": ("选任何一个都是把一个**口径相关的实测量**写进**口径无关的契约**，"
                                              "下次换采集器就会再冲突一次。根因是『契约里有实测量』，"
                                              "不是『哪个实测量对』"),
                    "accounting": "D 的第 14 号同型错误；由 B2 登记 OPEN + C2 拒绝自决 ⇒ 下属纠正 D 第 9 例",
                    "authority": "裁定 87.6 / §16.5（D 已改文本，C2 直接落）"},
                "c2_side_action": ("按裁定 87.6 落地：本次运行的分母 = `max(声明行程[模型属性，可搬], "
                                   "**同源**实测行程[本数据集])`（`resolve_physical_range_lerobot`），"
                                   "契约字面数字（含 1.0 与 0.91001）**只登记不使用**；"
                                   "`physical_range.gripper_dims_caliber` 保留为登记项"),
                "status_note": ("B2 侧 registry 里的那条 OPEN 由 B2 自己闭合（C2 不代改他人产物）；"
                                "C2 侧自本产物起引用裁定 87.6 的新文本")},
            "crosscheck_independence_note": (
                "所有 `crosscheck_vs_b2_npz_*` 都**不是独立来源**的互核（B2 的导出器也读同一份 parquet）；"
                "它们证明的是**帧序/集号/方向码的拼接一致**，不是数据本身的正确性。数据正确性的证据在 "
                "B2 的 demo_manifest.gates（16/16 PASS）与 expert_selfverify（80/80），C2 只引用不重证"),
        }
        # ⚠ 主线行的红一律是**发现**（数据的或契约的），不是实现缺陷 ⇒ 处置始终是「保留红 + 逐条解释」。
        # 本轮改口径（裁定 87.3-1 的 ① 落地）：修前这里是一份**手写常量** `ALLOWED_MAINLINE_RED`
        # （held-out 家族 + F2 的 Tr3），形式上等于"先看到红、再把红的牙写进白名单"⇒ 换一批数据
        # 就会退化成红洗白器。现在每行的 `allowed_red_teeth` 由
        # `derive_allowed_red_from_measurement()` 从**本次运行的四个测量事实**（A 超出声明区间 /
        # B held-out 覆盖率缺口 / C 分辨率低于阈值 / D F2 下限不实质 / E BC 准入必红）派生，
        # 且红牙点名的维必须落在授权事实的维集合**之内**，否则记入 `unexplained_red_teeth`。
        # 仍然**不**把这 8 行标成 must_red_branch（那会把真实缺口洗成"预期红"）。
        # ① 的实测后果（本轮）：held-out 家族（Td2/Te2/Tsat）**由红转绿** —— clip 0、非法 bin []、
        # 饱和维 []（= 裁定 87.13 预登记的可证伪检查点在 pilot-10 上就已满足）；红剩下的是
        # `Tb`（分辨率代价，条件 b 的升级项）与 `Tiv`（3 个维超出声明区间，条件 c 的数据/契约发现）。
        run_source(nc.SOURCE_S1_DEMO, fr_build, s1_stats, pr, lr_prov,
                   "s1-sim-demo-bidir", mainline=True,
                   eval_frames=(fr_eval if split_rec.get("held_out") else None),
                   stats_provenance=prov_label, consumer=consumer_main,
                   arm="s1_lerobot_crosscheck", file_suffix="__lerobot_crosscheck",
                   coverage_target=args.coverage_target,
                   physical_interval_override=pr_interval_s1,
                   interval_source_sha256_12=pr_prov.get("sha256_12_of_declared_source"),
                   rep_ver_extra="-ruling87-3-1", rep_ver_n=2,
                   derive_allowed=True, all_frames=fr)
        main_rows = rows[-len(combos):]
        # finding 的**组合逻辑已抽成 `compose_mainline_finding()`**：裁定 90.4-4 之后有两个读路径臂
        # （npz = 权威、lerobot = 交叉核对），结构必须同源，否则两段结论散文会各自漂移。
        crosscheck_finding = compose_mainline_finding(
            main_rows=main_rows, coverage_target=args.coverage_target, base_stats=s1_stats,
            build_frames=fr_build, split_rec=split_rec,
            reader="--s1-lerobot（直读 π₀.₅ LeRobot 出口的 parquet）",
            reader_role="crosscheck_arm（裁定 90.4-4：权威接口 = npz + `--s1-frames`）",
            dataset_stage=man.get("stage"), stats_provenance=prov_label)
        bc_arm_built = True
        # ===== BC 准入必红臂（裁定 85.4-3 点名的那条牙）=====
        # 同一份 stats（**标签不可进 BC**），只把消费方改成 `bc` ⇒ 牙 Tp5 必须红。
        # 裁定 90.4-4 之后本臂的判据更干净了：标签是 `formal40_lerobot_crosscheck`（formal 期）或
        # `pilot10_path_check`（先导期），两者都**不在** `nc.BC_ADMISSIBLE_PROVENANCES` 里 ⇒
        # 本臂证明的是"交叉核对臂/通路验证臂的 stats 结构上进不了 BC"，与数据批次无关。
        # 这不是"另造一批 stats"，而是**同一交付物**在另一个消费方下的判定 ⇒ 用 file_suffix 分开落盘，
        # 免得覆写通路验证档那份（覆写纪律）。
        run_source(nc.SOURCE_S1_DEMO, fr_build, s1_stats, pr,
                   {**lr_prov,
                    "tier": f"**BC 准入必红臂**：同一份 stats（标签 `{prov_label}`），消费方声明为 bc",
                    "why_this_arm_exists": ("裁定 85.4-3 的牙：『喂不可进 BC 的 stats 给 BC 配置 ⇒ 必须红』。"
                                            "红不了 = 同源硬闸是恒真的 = 没有闸。裁定 90.4-4 之后本臂吃的正是"
                                            "**交叉核对臂的标签**，即 D 点名要挡的形态（『两个读取器产出同一个"
                                            "标签 = 无法回答 BC 到底吃了哪一份』）")},
                   "s1-bc-admission-mustred", mainline=True,
                   eval_frames=(fr_eval if split_rec.get("held_out") else None),
                   stats_provenance=prov_label, consumer=nc.CONSUMER_BC,
                   tag="-bc-admission-mustred", file_suffix="__bc_admission_mustred",
                   arm="s1_bc_admission_mustred",
                   expected_verdict="RED", is_must_red_branch=True,
                   coverage_target=args.coverage_target,
                   physical_interval_override=pr_interval_s1,
                   interval_source_sha256_12=pr_prov.get("sha256_12_of_declared_source"),
                   rep_ver_extra="-ruling87-3-1", rep_ver_n=2,
                   derive_allowed=True, all_frames=fr)
        bc_rows = rows[-len(combos):]
        for r in bc_rows:
            r["bc_admission_tooth_id"] = "Tp5_bc_admission_requires_formal40_bc_source"
            r["bc_admission_tooth_fired"] = ("Tp5_bc_admission_requires_formal40_bc_source" in r["red_ids"])
        # 顶层证据块：闸（`scripts/c2_gate_norm_contract.py`）直接读它判 G29–G35，
        # 不必去挖每个 stats 文件的 `provenance`（一处事实一处存放，避免两份漂移）。
        crosscheck_reader_evidence = {
            "reader": "--s1-lerobot（直读 parquet，裁定 85.4-2）",
            "dataset_dir": lr_res["dataset_dir_rel"], "lerobot_dir": lr_res["lerobot_dir_rel"],
            "path_interpretation": lr_res["interpretation"],
            "demo_manifest_sha256_12": lr_res["demo_manifest_sha256_12"],
            "demo_manifest_mtime": lr_res["demo_manifest_mtime"],
            "demo_manifest_bytes": lr_res["demo_manifest_bytes"],
            "demo_manifest_generated_at": man.get("generated_at"),
            "demo_manifest_sha_recorded_by_b2_npz": ((b2_npz_man or {}).get("source_dataset") or {})
                .get("demo_manifest", {}).get("sha256_12_at_read") if b2_npz_man else None,
            "dataset_stage": man.get("stage"),
            "dataset_gates_verdict": (man.get("gates") or {}).get("verdict"),
            "dataset_gates_n_checks": (man.get("gates") or {}).get("n_checks"),
            "dataset_gates_n_red": (man.get("gates") or {}).get("n_red"),
            "dataset_representation_version": man.get("representation_version"),
            "parquet_files": lf["parquet_files"],
            "stray_parquet_outside_chunk_glob": lf["stray_parquet_outside_chunk_glob"],
            "n_frames": lf["n_frames"], "n_episodes": lf["n_episodes"], "state_dim": lf["state_dim"],
            "parquet_storage_dtype": lf["parquet_storage_dtype"],
            "dtype_declaration": lf["dtype_declaration"],
            "upcast_bitwise_lossless": lf["upcast_bitwise_lossless"],
            "grouping": {"sort_key": lf["sort_key"],
                         "raw_order_already_grouped_sorted": lf["raw_order_already_grouped_sorted"],
                         "reorder_was_material": lf["reorder_was_material"],
                         "frame_index_contiguous_per_episode": lf["frame_index_contiguous_per_episode"],
                         "n_frame_index_gaps": lf["n_frame_index_gaps"],
                         "frame_index_gaps": lf["frame_index_gaps"],
                         "index_column_is_global_arange": lf["index_column_is_global_arange"]},
            "start_pose_extraction": lf["start_pose_extraction"],
            "start_pose_crosscheck": sp_xcheck,
            "direction": dc,
            "crosscheck_vs_b2_npz": {"frames": fr_x, "episode_index": ep_x, "direction": dc_x},
            "heldout_split": split_rec,
            "physical_range": {"basis": pr_prov["basis"],
                               "declared_source": pr_prov["source_of_declared"],
                               "declared_source_sha256_12": pr_prov["sha256_12_of_declared_source"],
                               "dims_where_observed_exceeds_declared":
                                   pr_prov["dims_where_observed_exceeds_declared"],
                               "effective_binding_side": pr_prov["effective_binding_side"],
                               "not_used_from_errata": pr_prov["not_used_from_errata"],
                               "ctrlrange_interval_provided": bool(pr_interval_s1 is not None)},
            "stats_provenance": prov_label, "stats_provenance_why": prov_why,
            "bc_admission": nc.bc_admission(prov_label),
            "independence_note": lr_prov["crosscheck_independence_note"],
        }
        crosscheck_status = {
            "status": "built_from_lerobot_as_crosscheck_arm",
            "source": nc.SOURCE_S1_DEMO,
            "reader": "--s1-lerobot（直读 parquet）",
            "reader_role": ("**交叉核对臂**（裁定 90.4-4）。权威接口 = npz + `--s1-frames`；"
                            "本臂的产物 `stats_provenance` 结构上不可能等于 `formal40_bc_source`"),
            "dataset_dir": lr_res["dataset_dir_rel"],
            "checked_path": lr_res["lerobot_dir_rel"],
            "checked_at": now_iso(),
            "checked_path_sha256_12": [f["sha256_12"] for f in lf["parquet_files"]],
            "checked_path_mtime": [f["mtime"] for f in lf["parquet_files"]],
            "demo_manifest_sha256_12": lr_res["demo_manifest_sha256_12"],
            "demo_manifest_mtime": lr_res["demo_manifest_mtime"],
            "dataset_stage": man.get("stage"),
            "n_frames": lf["n_frames"], "n_episodes": lf["n_episodes"],
            "state_dtype_source": lf["dtype_declaration"]["state_dtype_source"],
            "upcast_bitwise_lossless": lf["upcast_bitwise_lossless"],
            "stats_provenance": prov_label, "stats_provenance_why": prov_why,
            "stats_provenance_canonical": nc.canonical_provenance(prov_label),
            "bc_admission": nc.bc_admission(prov_label),
            "not_for_bc": (prov_label not in nc.BC_ADMISSIBLE_PROVENANCES),
            # 裁定 86.1 的实质要求：provenance 必须**同时**引 `源 sha + n_episodes + n_frames`。
            # 三元组由构造满足（裁定 87.9 加项 2 的同一思路）：这里机器核一遍，缺任何一项就 `satisfied=false`，
            # 不靠散文声称。源已从 npz 换成 lerobot parquet（裁定 85.4-2-1）⇒ "npz sha" 读作
            # "**数据源** sha"，parquet 逐文件 sha + demo_manifest sha 都在里面，npz 只作互核源登记。
            "provenance_triple_ruling_86_1": {
                "source_kind": "pi05_lerobot_parquet（裁定 85.4-2：直读 π₀.₅ LeRobot 出口）",
                "source_sha256_12": [f["sha256_12"] for f in lf["parquet_files"]],
                "demo_manifest_sha256_12": lr_res["demo_manifest_sha256_12"],
                "n_episodes": lf["n_episodes"], "n_frames": lf["n_frames"],
                "crosscheck_npz_sha256_12": (fr_x.get("npz_sha256_12") if isinstance(fr_x, dict) else None),
                "crosscheck_npz_present": (fr_x.get("present") if isinstance(fr_x, dict) else None),
                # 走 `rel()`（本文件已有的**不抛**版本）而不是裸 `relative_to(ROOT)`：
                # 显示用路径不该有抛异常的能力（同一根因的第二道防线）。
                "crosscheck_npz_path": (rel(xnpz) if xnpz is not None else None),
                "satisfied": bool([f["sha256_12"] for f in lf["parquet_files"]]
                                  and isinstance(lf["n_episodes"], int) and lf["n_episodes"] > 0
                                  and isinstance(lf["n_frames"], int) and lf["n_frames"] > 0),
                "why_86_1_exists": ("D 原文：86.1 之所以立，正因为**目录名 `pilot5` 与内容（10 集）不符**，"
                                    "而 `pre_pilot5_path_check` 这个标签又沿用了目录名 ⇒ 集数必须与 sha 并列在册")},
            "coverage_target": args.coverage_target,
            "coverage_target_authority": nc.COVERAGE_TARGET_AUTHORITY.get(args.coverage_target),
            "declared_interval_conformance": (crosscheck_finding or {}).get("declared_interval_conformance"),
            "escalations_to_d": (crosscheck_finding or {}).get("escalations_to_d"),
            "heldout_split": split_rec,
            "direction_agree_with_b2_npz": dc_x.get("agree"),
            "frames_bitwise_equal_to_b2_npz": fr_x.get("bitwise_equal"),
            "physical_range_basis": pr_prov.get("basis"),
            "b2_contract_conflict_status": cc.get("status"),
            "b2_contract_conflict_ruling": "裁定 87.6（契约文本不得硬编码夹爪数值；C2 已按新文本落地）",
            "crosscheck_finding": crosscheck_finding,
            "supersedes": ("本键修前写的是『formal 落地后换 `--s1-lerobot` 指向 formal 目录重算 ⇒ 标签自动变 "
                           "`formal40_bc_source`』——该说法已被**裁定 90.4-4 作废**（lerobot 读路径不得产 BC 档标签）。"
                           "同时作废的历史件：`mainline_s1_pilot5/mainline_status.json`"
                           "（status=waiting_for_s1_pilot_5 / checked_path=null 已过期）"),
            "next_required_action": ("无（本臂是交叉核对臂）。主线 stats 的权威产出走 "
                                     "`--s1-frames <formal40 npz>`（裁定 90.4-4），见同批产物的 "
                                     "`mainline_status.json`"),
            "ruling_90_4_4_compliance": {
                "authority_interface": "npz + `--s1-frames`（裁定 86.0 撤回 85.4-2；86.1 末条；90.4-4）",
                "this_arm_label": prov_label,
                "label_is_bc_admissible": (prov_label in nc.BC_ADMISSIBLE_PROVENANCES),
                "must_be_false": True,
                "ok": (prov_label not in nc.BC_ADMISSIBLE_PROVENANCES),
                "why": ("D 原文：『两个读取器产出**同一个** provenance 标签 = 无法回答「BC 到底吃了哪一份」，"
                        "这正是要挡的形态』⇒ 本臂若拿到 BC 档标签，就是把这个缺陷装回去"),
                "data_equivalence_note": ("裁定 90.4-4 已亲测两条读路径**逐位等价**（`np.array_equal=True`、"
                                          "content sha 双 `c9a72480fcb7`）⇒ 分标签是**权威性**要求，"
                                          "不是正确性要求；C2 已有的 lerobot 侧工作不作废"),
            },
        }
    if s1 is not None and s1.exists():
        # ===== **权威接口**：npz + `--s1-frames`（裁定 90.4-4；86.0 撤回 85.4-2、86.1 末条要求用 formal npz 重算）=====
        # 修前本分支是 `elif`（lerobot 优先）、且被标成"已撤销的入口"、产物 status =
        # `built_from_npz_superseded_reader`。裁定 90.4-4 把**权威性反过来**了：npz 是权威、
        # `--s1-lerobot` 是交叉核对臂（其标签必须是 `formal40_lerobot_crosscheck`）。
        # 数据侧两条读路径经 D 亲测**逐位相同**（90.4-4：`np.array_equal=True`、content sha 双
        # `c9a72480fcb7`）⇒ 本轮换的是**权威性与标签**，不是数值；C2 已有的 lerobot 侧工作不作废。
        fr, st0, pr_literal, man = load_frames(s1)
        z_s1 = np.load(s1, allow_pickle=False)
        pr, pr_interval_s1, pr_prov = resolve_physical_range_npz_mainline(args, fr, s1)
        if pr_interval_s1 is None and args.coverage_target == nc.COVERAGE_TARGET_DECLARED_INTERVAL:
            raise SystemExit("[RED] 声明物理区间不可得，而 `--coverage-target=declared_interval`（裁定 87.3-1 的 ①）"
                             "⇒ 拒绝静默退回 `build_only`（红线 "
                             "`absence_of_measurement_is_not_measurement_of_absence`：没测到 ≠ 测到没有）")
        s1x = s1_npz_crosscheck(s1, fr, pr)
        if args.stats_provenance == "auto":
            prov_label, prov_why = auto_stats_provenance(man, z_s1, fr)
        else:
            prov_label, prov_why = args.stats_provenance, "命令行显式指定（需 D 的裁定支撑）"
        cc = (man.get("contract_conflict") or {})
        fr_build, fr_eval, split_rec = split_heldout_by_episode(s1, fr)
        s1_stats = nc.build_stats(fr_build)
        ep_npz = (np.asarray(z_s1["episode_index"]).astype(np.int64)
                  if "episode_index" in z_s1.files else None)
        n_eps_npz = (len(set(int(e) for e in ep_npz.tolist())) if ep_npz is not None else None)
        upcast_lossless = bool(np.array_equal(fr.astype(np.float32).astype(np.float64), fr))
        content_sha = sha12_bytes(np.ascontiguousarray(fr).tobytes())
        sp_all = np.asarray(z_s1["start_poses"], dtype=np.float64) if "start_poses" in z_s1.files else None
        sp_xcheck = None
        if sp_all is not None and sp_all.shape[0] > 0:
            d = np.abs(sp_all - start_pose[None, :]).max(axis=1)
            sp_xcheck = {"n_start_poses": int(sp_all.shape[0]),
                         "max_abs_diff_vs_a2_start_pose": float(d.max()),
                         "all_equal_to_a2_start_pose": bool(np.all(d <= 1e-9)),
                         "note": ("起态口径：本档仍用 A2 的 `hold_action_14d`（部署起态；D §14-5-4 认定"
                                  "起态位姿是几何量、不随控制频率变化）。这里只**交叉核验** B2 导出的"
                                  " start_poses 与它是否同一位姿，不静默换源")}
        npz_prov = {
            "frames": [{"reader": "--s1-frames（npz = **权威接口**，裁定 90.4-4）",
                        "npz": rel(s1), "sha256_12": sha12(s1), "bytes": s1.stat().st_size,
                        "mtime": iso_mtime(s1),
                        "manifest": (rel(s1.parent / "manifest.json")
                                     if (s1.parent / "manifest.json").exists() else None),
                        "manifest_sha256_12": (sha12(s1.parent / "manifest.json")
                                               if (s1.parent / "manifest.json").exists() else None),
                        "npz_arrays": sorted(z_s1.files),
                        "shape": list(fr.shape), "dtype": str(fr.dtype),
                        "content_sha256_12": content_sha,
                        "content_sha_definition": "sha256(float64 C-contiguous bytes of `frames`)[:12]",
                        "upcast_bitwise_lossless": upcast_lossless,
                        "n_episodes": n_eps_npz,
                        "per_direction_episode_counts": split_rec.get("episode_to_direction")
                        and _count_per_direction(split_rec.get("episode_to_direction")),
                        "crosscheck_vs_lerobot_reader": crosscheck_npz_vs_lerobot(
                            fr, ep_npz, lr_frames, lr_ep_sorted, content_sha)}],
            "start_pose": sp_prov,
            "start_pose_crosscheck": sp_xcheck,
            "tier": ("**主线 BC 同源档**（裁定 85.4-3 同源 + 90.4-4 权威接口）"
                     if prov_label in nc.BC_ADMISSIBLE_PROVENANCES
                     else f"**{prov_label}**：不可进 BC（裁定 85.4-3/90.4-4）"),
            "stats_provenance": prov_label,
            "stats_provenance_why": prov_why,
            "stats_provenance_canonical": nc.canonical_provenance(prov_label),
            "bc_admission": nc.bc_admission(prov_label),
            "physical_range": pr_prov,
            "physical_range_caliber_rule": pr_prov.get("caliber_rule"),
            "npz_contract_recompute": s1x,
            "heldout_split": split_rec,
            "b2_contract_conflict": {
                "status_reported_by_b2": cc.get("status"),
                "status_after_ruling_87_6": ("RULED_by_87_6（C2 侧不再登记为 OPEN；B2 的 registry 由 B2 自己闭合）"),
                "b2_side_stale_status_note": ("B2 在 `docs/b2_handoff_to_c2_formal40_20260930.md` §6 自报："
                                              "导出器仍把 `contract_conflict.status` 写成 `OPEN_needs_d_ruling`，"
                                              "而 D 已在裁定 87.6 关闭 ⇒ C2 按『已关闭』读，**不代改 B2 的产物**"),
                "authority": "裁定 87.6 / §16.5（契约文本不得硬编码夹爪数值；分母 = 同源实测 effective）"},
        }
        run_source(nc.SOURCE_S1_DEMO, fr_build, s1_stats, pr, npz_prov,
                   "s1-sim-demo-bidir", mainline=True,
                   eval_frames=(fr_eval if split_rec.get("held_out") else None),
                   stats_provenance=prov_label, consumer=(args.consumer or nc.CONSUMER_PATH_CHECK),
                   arm="s1_mainline_path_check", file_suffix="__mainline_path_check",
                   coverage_target=args.coverage_target,
                   physical_interval_override=pr_interval_s1,
                   interval_source_sha256_12=pr_prov.get("sha256_12_of_declared_source"),
                   rep_ver_extra="-ruling87-3-1", rep_ver_n=2,
                   derive_allowed=True, all_frames=fr)
        main_rows = rows[-len(combos):]
        mainline_finding = compose_mainline_finding(
            main_rows=main_rows, coverage_target=args.coverage_target, base_stats=s1_stats,
            build_frames=fr_build, split_rec=split_rec,
            reader="--s1-frames（B2 的 `states_14d.npz`）",
            reader_role="authority（裁定 90.4-4：BC 档标签只由本读路径产出）",
            dataset_stage=(man.get("source_dataset") or {}).get("stage"),
            stats_provenance=prov_label)
        # ===== BC 准入必红臂（裁定 85.4-3 点名的那条牙）=====
        # 只在**交叉核对臂没有跑**时由这里补（两个读路径都给时，本臂由 lerobot 分支产，
        # 那份更贴题：它的 frames 与标签**都**来自被禁止进 BC 的那条读路径）。
        if not bc_arm_built:
            run_source(nc.SOURCE_S1_DEMO, fr_build, s1_stats, pr,
                       {**npz_prov,
                        "tier": ("**BC 准入必红臂**：与权威臂**同一批帧**，只把标签换成结构上不可进 BC 的 "
                                 f"`{nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK}`"),
                        "why_this_arm_exists": ("裁定 85.4-3 的牙：『喂不可进 BC 的 stats 给 BC 配置 ⇒ 必须红』。"
                                                "红不了 = 同源硬闸是恒真的 = 没有闸。裁定 90.4-4 之后"
                                                "**标签**是判据（不是数据批次）：本臂的 frames 与权威臂逐位相同，"
                                                "差别只在标签 ⇒ 正好证明 Tp5 判的是标签而非数据"),
                        "stats_provenance": nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK,
                        "bc_admission": nc.bc_admission(nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK)},
                       "s1-bc-admission-mustred", mainline=True,
                       eval_frames=(fr_eval if split_rec.get("held_out") else None),
                       stats_provenance=nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK,
                       consumer=nc.CONSUMER_BC,
                       tag="-bc-admission-mustred", file_suffix="__bc_admission_mustred",
                       arm="s1_bc_admission_mustred",
                       expected_verdict="RED", is_must_red_branch=True,
                       coverage_target=args.coverage_target,
                       physical_interval_override=pr_interval_s1,
                       interval_source_sha256_12=pr_prov.get("sha256_12_of_declared_source"),
                       rep_ver_extra="-ruling87-3-1", rep_ver_n=2,
                       derive_allowed=True, all_frames=fr)
            bc_rows = rows[-len(combos):]
            for r in bc_rows:
                r["bc_admission_tooth_id"] = "Tp5_bc_admission_requires_formal40_bc_source"
                r["bc_admission_tooth_fired"] = (
                    "Tp5_bc_admission_requires_formal40_bc_source" in r["red_ids"])
            bc_arm_built = True
        mainline_reader_evidence = {
            "reader": "--s1-frames（npz = **权威接口**，裁定 90.4-4）",
            "reader_role": "authority",
            "npz": rel(s1), "npz_sha256_12": sha12(s1), "npz_bytes": s1.stat().st_size,
            "npz_mtime": iso_mtime(s1),
            "npz_manifest": (rel(s1.parent / "manifest.json")
                             if (s1.parent / "manifest.json").exists() else None),
            "npz_manifest_sha256_12": (sha12(s1.parent / "manifest.json")
                                       if (s1.parent / "manifest.json").exists() else None),
            "npz_arrays": sorted(z_s1.files),
            "frames_shape": list(fr.shape), "frames_dtype": str(fr.dtype),
            "frames_content_sha256_12": content_sha,
            "frames_content_sha_definition": "sha256(float64 C-contiguous bytes)[:12]",
            "upcast_bitwise_lossless": upcast_lossless,
            "n_frames": int(fr.shape[0]), "n_episodes": n_eps_npz,
            "per_direction_episode_counts": (split_rec.get("episode_to_direction")
                                             and _count_per_direction(split_rec.get("episode_to_direction"))),
            "heldout_split": split_rec,
            "source_dataset_block": man.get("source_dataset"),
            "b2_gates": {"verdict": (man.get("source_dataset") or {}).get("gates_verdict"),
                         "n_checks": (man.get("source_dataset") or {}).get("gates_n_checks"),
                         "n_red": (man.get("source_dataset") or {}).get("gates_n_red"),
                         "precondition": (man.get("source_dataset") or {}).get("gates_precondition")},
            "cotenant_evidence_at_collection": (man.get("source_dataset") or {}).get(
                "cotenant_evidence_at_collection"),
            "renderer_arm_compensating_control": man.get("renderer_arm_compensating_control"),
            "renderer_arm_citation_discipline": ("裁定 91.2-2：引用 `arm_stable` 必须写 "
                                                 "`post_run_independent_probe_same_caliber`，且必须同引 "
                                                 "`renderer_class_at_end_in_run = null`（运行内**未**连续监测）"),
            "physical_range": pr_prov,
            "npz_contract_recompute": s1x,
            "crosscheck_arm_present": bool(crosscheck_status is not None),
            "crosscheck_arm_frames_bitwise_equal": (
                (crosscheck_status or {}).get("frames_bitwise_equal_to_b2_npz")
                if crosscheck_status is not None else None),
            "independence_note": ("本臂与交叉核对臂**不是独立来源**（B2 的导出器也读同一份 parquet）；"
                                  "两臂逐位相同证明的是**两条读路径拼出的帧序/集号一致**，数据正确性的证据在 "
                                  "B2 的 `demo_manifest.gates`（19/19 PASS）与 `expert_selfverify`（80/80），"
                                  "C2 只引用不重证"),
        }
        mainline_status = {
            "status": "built_from_npz_authority_interface",
            "source": nc.SOURCE_S1_DEMO,
            "reader": "--s1-frames（B2 的 `states_14d.npz`）",
            "reader_role": "authority（裁定 90.4-4）",
            "ruling_90_4_4": {
                "authority_interface": "npz + `--s1-frames`",
                "crosscheck_arm": "--s1-lerobot（标签必须是 `formal40_lerobot_crosscheck`）",
                "what_changed_this_round": ("修前本 status 写『不再需要 `states_14d.npz`（裁定 85.4-2-1 已撤销"
                                            "该任务）』⇒ D 在 90.4-4 指出这与裁定 **86.0** 直接冲突，且 "
                                            "`85.4-2-1` 这个裁定号在 decisions 里**不存在**（实际是 85.4-1，"
                                            "且已被 86.0 撤回）⇒ 本轮按 86.0/86.1/90.4-4 重生成，"
                                            "引用号已核对存在性"),
                "data_equivalence": ("两条读路径逐位等价（D 亲测 + C2 本轮独立复算 content sha "
                                     f"`{content_sha}`，与 D 报的 `c9a72480fcb7` 逐字相符）⇒ 权威性冲突、"
                                     "不是正确性冲突"),
            },
            "frames_npz": rel(s1), "n_frames": int(fr.shape[0]), "n_episodes": n_eps_npz,
            "checked_path": rel(s1),
            "checked_at": now_iso(),
            "checked_path_sha256_12": sha12(s1),
            "checked_path_mtime": iso_mtime(s1),
            "npz_manifest_sha256_12": (sha12(s1.parent / "manifest.json")
                                       if (s1.parent / "manifest.json").exists() else None),
            "dataset_stage": (man.get("source_dataset") or {}).get("stage"),
            "stats_provenance": prov_label, "stats_provenance_why": prov_why,
            "stats_provenance_canonical": nc.canonical_provenance(prov_label),
            # 裁定 93.4：BC 准入的**闸证据**必须随产物落盘（消费方 = A2 的 S3 BC 入口，T-A2-7）。
            # `admissible_for_bc` 仍是标签派生（既有消费方 `pred_G40` 按它判，语义未改）；
            # 闸 verdict 走独立字段 ⇒ "标签错"与"闸红"两种失效可分辨。
            "bc_admission": nc.bc_admission(
                prov_label, gate_verdict=gate_ref.get("gate_verdict"),
                gate_run_dir=gate_ref.get("gate_run_dir"),
                gate_verdict_sha256_12=gate_ref.get("gate_verdict_sha256_12"),
                gate_verdict_class1=gate_ref.get("gate_verdict_class1")),
            "gate_verdict_reference": gate_ref,
            # 裁定 94.3（Ⅱ 类登记不阻塞，裁定 95.1-1）：**BC 消费口径**上也必须能一眼看见
            # 正确性族的逐维盲点。A2 读的是本档 ⇒ 少了它，"归一化器已通过正确性验证"这句话
            # 就会在盲点维上变成缺陷类 ⑲（报绿而绿来自覆盖不全）。与 `mainline_finding` 里那份
            # **同源同值**（同一个 `heldout_blindness_registration()`，不各写一份）。
            "heldout_per_dim_blindness_ruling_94_3": mainline_finding[
                "heldout_per_dim_blindness_ruling_94_3"],
            "not_for_bc": (prov_label not in nc.BC_ADMISSIBLE_PROVENANCES),
            "provenance_triple_ruling_86_1": {
                "source_kind": "b2_states_14d npz（裁定 86.1 末条：formal 版 npz = 权威接口）",
                "source_sha256_12": sha12(s1),
                "frames_content_sha256_12": content_sha,
                "npz_manifest_sha256_12": (sha12(s1.parent / "manifest.json")
                                           if (s1.parent / "manifest.json").exists() else None),
                "n_episodes": n_eps_npz, "n_frames": int(fr.shape[0]),
                "satisfied": bool(sha12(s1) and isinstance(n_eps_npz, int) and n_eps_npz > 0
                                  and int(fr.shape[0]) > 0),
                "why_86_1_exists": ("D 原文：86.1 之所以立，正因为**目录名 `pilot5` 与内容（10 集）不符**"
                                    "⇒ 集数必须与 sha 并列在册（裁定 87.9 加项 2 同思路：由构造满足 + 机器核）")},
            "coverage_target": args.coverage_target,
            "coverage_target_authority": nc.COVERAGE_TARGET_AUTHORITY.get(args.coverage_target),
            "declared_interval_source": pr_prov.get("source_of_declared"),
            "declared_interval_sha256_12": pr_prov.get("sha256_12_of_declared_source"),
            "declared_interval_conformance": (mainline_finding or {}).get("declared_interval_conformance"),
            "ruling_90_4_1_polarity": {
                "withdrawn": ("`Tiv_no_state_outside_declared_interval`（越出声明区间即红）—— 裁定 90.4-1 撤回："
                              "`jnt_range` 是**软边界**，越界本身物理合法且实测不产生非法 bin"),
                "now": ["Tiv_out_of_declared_interval_is_measured（测量必须存在且完整；永不因越界量判红）",
                        "Tesc_no_covered_window_escape（硬红：headroom_consumption_max ≥ 1.0 = 窗口逃逸的定义）",
                        "Tlo_no_downside_coverage_deficit（硬红：下侧覆盖不足 = 正确性缺陷）",
                        "Tovr_out_of_interval_overflow_is_warned（warning + 量级：上侧/任一侧越界事实）"],
                "unchanged": "Te1/Te2 的 `illegal_bin(-1)` 保持绝对硬红（裁定 90.4-1）",
                "probe": ("runs/vla/c2_norm_contract_20260929/probe_ruling90_4_polarity/verdict.json"
                          "（6 个构造 × 4 把牙的极性逐条对上裁定原文）"),
            },
            "escalations_to_d": (mainline_finding or {}).get("escalations_to_d"),
            "condition_b_resolution": (mainline_finding or {}).get("condition_b_resolution"),
            "condition_b_resolution_renamed_from": (
                "condition_b_resolution_first_row（修前的键名，只含 `main_rows[0]` 的单口径读数）。"
                "**改名必须同步这里**：本轮实测到改名后本键静默变 `null` 的形态"
                "（读者会把 null 读成『没有数据』而不是『键改名了』）⇒ 已修，并留下这条自曝记录"),
            "ruling_90_4_3_trigger_caliber": {
                "summary_for_readers": ("裁定 90.4-3 的 P1→P0 触发判据**口径依赖**：held-out(n=547) 触发、"
                                        "build(n=10488)/all(n=11035) 不触发。C2 **不据此把 P1 升 P0**，"
                                        "口径归 D 裁（详情见 `condition_b_resolution.ruling_90_4_3_trigger`）"),
                **{k: (((mainline_finding or {}).get("condition_b_resolution") or {})
                       .get("ruling_90_4_3_trigger") or {}).get(k)
                   for k in ("caliber_dependent", "triggered", "triggered_heldout_caliber",
                             "triggered_build_caliber", "triggered_all_caliber",
                             "governing_caliber", "disposition", "ask_d",
                             "c2_does_not_self_decide", "corroborating_probe")},
                "authority": ("裁定 90.4-3（触发条件原文）+ 90.2 #16（逐维不用 median）"
                              "+ 92.6 自查项（取典型值 ⇒ 问是不是真正要指的那个）"),
            },
            "heldout_split": split_rec,
            "npz_contract_recompute_conformant": s1x.get("contract_conformant"),
            "physical_range_basis": pr_prov.get("basis"),
            "b2_contract_conflict_status": cc.get("status"),
            "b2_contract_conflict_ruling": "裁定 87.6（契约文本不得硬编码夹爪数值；C2 已按新文本落地）",
            "mainline_finding": mainline_finding,
            "supersedes": ("同目录修前的 `mainline_status.json`。两层前像："
                           "① `before_images/toplevel_pre_ruling90_4_polarity/`（status=`built_from_lerobot`、"
                           "stats_provenance=`pilot10_path_check`、as_of 03:41:04）；"
                           "② `before_images/toplevel_pre_trigger_caliber_fix_eeb616db9486/`（status 已是 "
                           "`built_from_npz_authority_interface`，但 90.4-3 触发判据只有 held-out 单口径、"
                           "且误报 `triggered=true`；matrix.json 前像 `eeb616db9486`、"
                           "mainline_status.json 前像 `d0a039fae97d`）"),
            "next_required_action": ("闸侧（`scripts/c2_gate_norm_contract.py`）按裁定 90.4-1 的四把牙与"
                                     "90.4-4 的双读路径重跑 ⇒ 0 红后，本档 stats 才是 S3 BC 的输入"
                                     "（裁定 85.4-3 同源硬闸：BC 只认 `formal40_bc_source`）"),
        }
        npz_authority_ran = True
    if not npz_authority_ran:
        # 权威接口（npz）没跑 ⇒ **没有主线 stats**。交叉核对臂跑了也不算：裁定 90.4-4 明写
        # lerobot 读路径的标签必须是 `formal40_lerobot_crosscheck`、结构上进不了 BC ⇒
        # 拿它顶替权威臂就是"两个位置都以为自己管"的形态（D 在 §16 之后反复点名要挡的东西）。
        mainline_status = {
            "status": ("waiting_for_npz_authority_interface" if lr_res is not None
                       else "waiting_for_s1_formal_40"),
            "blocking_on": ("**权威接口缺席**：`--s1-frames <B2 的 states_14d.npz>` 没给或文件不在"
                            "（裁定 90.4-4：权威接口 = npz + `--s1-frames`；裁定 86.0 撤回 85.4-2、"
                            "86.1 末条要求用 formal 版 npz 重算 `formal40_bc_source`）"
                            if lr_res is not None else
                            "B2 的 S1 仿真双向示范 **formal 40 集**（20 集/方向）+ 同批 npz 导出"
                            "（裁定 85.4-3 同源、86.1 末条、90.4-4 权威接口）"),
            "crosscheck_arm_ran": bool(lr_res is not None),
            "crosscheck_arm_cannot_substitute": ("交叉核对臂的标签是 "
                                                 f"`{nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK}`，"
                                                 "不在 `nc.BC_ADMISSIBLE_PROVENANCES` 里 ⇒ 结构上进不了 BC"
                                                 "（裁定 90.4-4）" if lr_res is not None else None),
            "checked_path": (str(s1) if s1 is not None else
                             (str(lr_res["dataset_dir_rel"]) if lr_res else None)),
            "checked_at": now_iso(),
            "checked_path_exists": bool((s1 is not None and s1.exists()) or lr_res),
            "refused_to_substitute": ["env_derived_diagnostic", "yam_abc130k"],
            "interface_ask_to_b2": ("⚠ 本键修前写的是『**不再需要 `states_14d.npz`**（裁定 85.4-2-1 已撤销"
                                    "该任务）… 命令 = `--s1-lerobot <formal 目录>`，标签自动判为 "
                                    "`formal40_bc_source`』⇒ D 在裁定 90.4-4 指出它与裁定 **86.0** 直接冲突，"
                                    "且 `85.4-2-1` 这个裁定号在 decisions 里**不存在**（实际是 85.4-1，"
                                    "且已被 86.0 撤回）。**现行口径**：需要 `states_14d.npz`，它是权威接口；"
                                    "命令 = `--s1-frames <formal40 npz> [--s1-lerobot <formal 目录> 作交叉核对臂]`；"
                                    "BC 档标签只由 npz 侧的 `auto_stats_provenance()` 按 8 项机器判据产出"),
            "what_is_ready_now": ("生成器（含 --s1-lerobot 直读器）+ 契约层（含 Tp4/Tp5 溯源硬闸）"
                                  "+ 闸 + 变异体；pilot-10 通路验证档已产出（不进 BC）"),
        }

    # 下限族效果对照（只看 hold 相：那是**真实测量**的近常量数据；random/sweep 相一个维都标不出来）
    hold_rows = [r for r in rows if r.get("tag") == "-holdphase" and r.get("near_constant")]
    fam_effect = []
    for r in hold_rows:
        ncd, sm = r["near_constant"], (r.get("summary") or {})
        fam_effect.append({"case": r["case"], "family": r["family"], "coef": r["coef"],
                           "n_dims_near_constant": ncd["n_dims"],
                           "n_unprotected": ncd["n_unprotected"],
                           "n_floor_immaterial": ncd["n_immaterial"],
                           "floor_min_on_marked": ncd["floor_min_on_marked"],
                           "materiality_ratio_min": ncd["materiality_ratio_min"],
                           "n_dims_floor_binding": sm.get("n_dims_floor_binding"),
                           "bins_occupied_median": sm.get("bins_occupied_median"),
                           "clip_ratio_max": sm.get("clip_ratio_max"),
                           "abs_max_normalized": (sm.get("saturation") or {}).get("abs_max_normalized"),
                           "verdict": r["verdict"]})
    floor_finding = {
        "measurement_basis": "hold 相 300 帧（`env_states_hold/env_states.npz`，osmesa CPU 采集）",
        "near_constant_rel_tol": nc.ContractThresholds().near_constant_rel_tol,
        "rel_tol_history": ("原提议 1e-3 **实测标不出任何维**（hold 相 denom_raw/行程 最小 = 1.648e-3）"
                            "⇒ 恒真牙，已作废；现值 = min(F1_CANDIDATES) = 0.02，与下限公式同源"),
        "f1_verdict": ("F1（coef × 物理行程）：下限**实质有效**（materiality_ratio = coef/0.02 ≥ 1），"
                       "coef=0.05 绑定 10 维、coef=0.02 绑定 7 维；代价 = 分辨率（bins 中位数 12.0 / 13.5）"),
        "f2_verdict": ("F2（coef × 逐步差分 MAD）：hold 相 MAD 最小 = 1.881e-07 ⇒ coef=2.0 的下限 = 3.76e-07，"
                       "比 0.02×行程小约 **5 个数量级** ⇒ `floor>0` 成立（Tr1 绿）但**实质上没有保护**"
                       "（Tr3 的对象）；实测 floor_binding = 0 维、bins 中位数与关下限完全相同（13.5）"),
        "c2_recommendation": ("主线用 **F1**；若要同时防"
                              "「噪声放大」，取 `floor = max(F1(coef), F2(coef))` 而**不是**二选一 —— "
                              "F2 单独用在真正不动的维上退化为 0。coef 的最终值仍标 "
                              "`proposed_pending_s1`（等 B2 的 S1 先导 5 集定标）"),
        "clip_cap_proposal": ("`clip_ratio_cap` 维持 **0.01**（proposed_pending_s1）：结构事实是 q01/q99 "
                              "天然甩掉两端各 1%（本线实测 in-distribution clip_max = 0.0208 ≈ 2×1%），"
                              "所以 0.01 只有在 `widen_to_cover` 生效后才是可达的；**不许**把它放宽到 0.02 以上，"
                              "否则等于把「展宽没做」这件事合法化"),
        "status": "proposed_pending_s1（效果列已用真实帧算出，阈值本身待 S1 定标；D 裁）"}

    # ---- 裁定 93.6：run 级牙（不属于任何一行，所以不塞进 `rows[*].teeth`）----
    # `Txr_crosscheck_freshness_is_registered` 判的是 `crosscheck_status.checked_at` 的新鲜度。
    # 参考区间 = **本次 run 的窗口** `[run_started_at, generated_at]`：`generated_at` 是写盘那一刻
    # 盖的、`checked_at` 是 run 中途真去看路径时盖的 ⇒ 裁定 93.6 的字面（「`checked_at` 不早于
    # `generated_at`」）在构造上不可满足（实测差 −1 s，会让本牙结构性恒 WARN = 裁定 27.1 的恒红闸）。
    # C2 保留 D 的**意图**、把参考点换成可满足的窗口，并把两个 lag 逐秒落盘 ⇒ 落点差异已报 D（E7）。
    gen_at = now_iso()
    run_level_teeth = []
    if crosscheck_status is not None:
        run_level_teeth.append(nc.crosscheck_freshness_tooth(
            checked_at=crosscheck_status.get("checked_at"),
            run_started_at=run_started_at, generated_at=gen_at,
            scope="crosscheck_status"))
    run_level_warnings = [t["observed"] for t in run_level_teeth if t["status"] == "WARN"]

    matrix = {"artifact": "c2_norm_stats_matrix", "generated_at": gen_at,
              "run_started_at": run_started_at,
              "run_level_teeth": run_level_teeth,
              "run_level_warnings": run_level_warnings,
              "n_run_level_teeth": len(run_level_teeth),
              # 裁定 93.4：本次 matrix 的每一行 `bc_admission_with_gate` 引的都是这**同一次**闸跑
              # （`--gate-verdict-json`）；没给 ⇒ `measurement_status="not_measured"`（不写 false）。
              "gate_verdict_reference": gate_ref,
              "cli": [str(Path(sys.argv[0]).name), *[str(a) for a in sys.argv[1:]]],
              "generator": {"path": "scripts/c2_build_norm_stats.py",
                            "sha256_12": sha12(Path(__file__).resolve())},
              "generator_before_image": (BEFORE_IMAGE if BEFORE_IMAGE else None),
              "contract_module": {"path": "harness/norm_contract.py", "sha256_12": sha12(ROOT / "harness/norm_contract.py"),
                                  "lines": len((ROOT / "harness/norm_contract.py").read_text().splitlines())},
              "authority": ["裁定 49.1", "裁定 51①", "裁定 52", "裁定 61", "裁定 69（T-C2-1 P0）"],
              "two_cases_parallel": list(nc.KNOWN_CASES),
              "floor_candidates": {"F1_physical_range_fraction": list(nc.F1_CANDIDATES),
                                   "F2_noise_scale_multiple": list(nc.F2_CANDIDATES),
                                   "coef_status": "proposed_pending_s1（效果列已用 env 诊断档真实帧算出）"},
              "start_pose": sp_prov,
              "physical_range": {**prange_prov, "values": np.asarray(prange).tolist(),
                                 "n_dims": int(np.asarray(prange).size)},
              "env_frames_total": int(env_frames.shape[0]),
              "rows": rows, "files": files,
              "floor_effect_on_near_constant_holdphase": fam_effect,
              "floor_family_finding": floor_finding,
              "mainline_status": mainline_status,
              "mainline_finding": mainline_finding,
              "mainline_reader_evidence": mainline_reader_evidence,
              # 裁定 90.4-4：两条读路径**分开登记**（权威 vs 交叉核对），不共用一套键 ——
              # 共用就等于把"BC 到底吃了哪一份"这个问题重新变成不可回答。
              "crosscheck_status": crosscheck_status,
              "crosscheck_finding": crosscheck_finding,
              "crosscheck_reader_evidence": crosscheck_reader_evidence,
              "reader_authority_ruling_90_4_4": {
                  "authority_interface": "npz + `--s1-frames`",
                  "authority_ran_this_run": bool(npz_authority_ran),
                  "crosscheck_interface": "`--s1-lerobot`（直读 parquet）",
                  "crosscheck_ran_this_run": bool(crosscheck_status is not None),
                  "bc_label_only_from_authority": bool(
                      not (crosscheck_status or {}).get("ruling_90_4_4_compliance", {}).get(
                          "label_is_bc_admissible", False)),
                  "withdrawn": ("裁定 85.4-2（`--s1-lerobot` 为主线）被 **86.0** 撤回；"
                                "`85.4-2-1` 这个裁定号在 decisions 里不存在（D 在 90.4-4 指出）"),
                  "data_equivalence": ("两条读路径的数据经 D 亲测逐位相同（90.4-4）；本产物另有 C2 自己的"
                                        "复算，见 `mainline_reader_evidence` 里的 "
                                        "`crosscheck_vs_lerobot_reader`（含 content sha 比对）"),
              },
              # 裁定 87.3-1 的 ① 在**本产物里**的适用范围登记（逐行 `coverage_target` 是判据，
              # 这里只解释"为什么诊断臂不吃这个开关"⇒ 不让范围限定只活在散文里）。
              "coverage_ruling_87_3": {
                  "ruling": "裁定 87.3-1：`widen_to_cover` 的 `must_cover` 改为覆盖**声明物理区间**（①，强制）",
                  "cli_switch": "--coverage-target",
                  "this_run_target_for_mainline": args.coverage_target,
                  "targets_by_arm": {a: sorted({(r.get("coverage_target") or "<not_applicable>")
                                                for r in rows if (r.get("arm") or "<none>") == a})
                                     for a in sorted({(r.get("arm") or "<none>") for r in rows})},
                  "applied_to_arms": sorted({r.get("arm") for r in rows
                                             if r.get("coverage_target") == nc.COVERAGE_TARGET_DECLARED_INTERVAL}),
                  "not_applied_to_arms": sorted({(r.get("arm") or "<none>") for r in rows
                                                 if r.get("coverage_target") != nc.COVERAGE_TARGET_DECLARED_INTERVAL}),
                  "scope_limitation": {
                      "status": "OPEN_needs_d_ruling（C2 不自决扩围）",
                      "what_was_limited": ("① 只作用于**主线臂**（`s1_mainline_path_check` / "
                                           "`s1_bc_admission_mustred`）。env 诊断三臂与 YAM 必红臂保持 "
                                           "`build_only`"),
                      "why": ("① 诊断档 stats 全部 `not_for_mainline_normalizer=true`、不进部署表示，"
                              "① 要防的失效模式（非法 bin 进 π₀.₅ prompt）在它们身上不成立；"
                              "② 那 33 行的读数是裁定 83/84 文书引用的基线，改覆盖目标 = 跨档改口径，"
                              "无裁定支撑；③ stress 臂的红来自**源不匹配**（Tr2/Td2/Te2），"
                              "把窗口展到声明区间有可能削弱那组牙 ⇒ 在没有裁定之前不动它"),
                      "ask_d": "是否把 ① 推广到诊断/stress 臂（C2 判：不必，但请 D 明确记一句以免沉默缺口）"},
                  "condition_a": ("两臂变异体由**闸**跑（`scripts/c2_gate_norm_contract.py`）："
                                  "臂 1 = `--coverage-target build_only` 复现裁定 87.3 的红读数"
                                  "（clip 0.0927273 / 非法 bin [7,12] / 饱和 3 维 [5,7,12]，三个数逐位对齐）；"
                                  "臂 2 = 注入一个『声明区间内、build q01/q99 外』的状态 ⇒ ① 档必须不产生非法 bin、"
                                  "`build_only` 档必须产生。产物：闸 run 目录下 "
                                  "`coverage_condition_a.json` / `coverage_condition_b.json`"),
                  "condition_b": ("分辨率代价**只登记不定标**（裁定 87.3-2 条件 b）：逐维 `bins_occupied` 落在"
                                  "每行 `summary.bins_occupied_per_dim`，① 前后并排由闸侧复算；"
                                  "D 预登记的可推翻条件（主线维 bins_occupied_median < 8 ⇒ 改采逐维覆盖）"
                                  "由闸按**两种读法**分别判，不替 D 选读法"),
                  "condition_c": ("① 不是赦免令：覆盖集**不含 build 帧**（`nc.coverage_must_cover`），"
                                  "且 `widen_to_cover(cover_cap=...)` 机器核『展宽不得超出声明区间 ± 头寸』；"
                                  "⚠ 本条后半句已被**裁定 90.4-1 改写**：修前写的是『超出声明区间的状态由"
                                  "独立牙 `Tiv_no_state_outside_declared_interval` 判红』，而 D 在裁定 90.2 #15 "
                                  "承认『超出声明区间 = 缺陷』这个前提是它自己的错误（`jnt_range` 是**软边界**）。"
                                  "**保留的部分**（裁定 90.3 称之为条件 c 的『正确残余』）：覆盖集仍**不含 build 帧**、"
                                  "`cover_cap` 仍钉在声明区间上、**禁止**用『再展宽』消除饱和平台"
                                  "（那只会把求解器抖动放大成假信号喂给 BC）；"
                                  "**撤回的部分**：越界本身不再判红，改为 `Tiv_…is_measured`（测量）+ "
                                  "`Tesc`（窗口逃逸硬红）+ `Tlo`（下侧覆盖不足硬红）+ `Tovr`（warning + 量级）。"
                                  "『越界量小于 1 bin 头寸 ⇒ `Tsat` 绿 ⇒ 事实被静默吸收』这个**实测形态仍然成立**，"
                                  "所以测量必须独立落盘 —— 变的只是它是不是红"),
                  "ruling_90_4": {
                      "90.4-1": ("撤回条件 c 的极性；`Tiv_no_state_outside_declared_interval` 改判为四把牙"
                                 "（见 `condition_c`）。三颗双向牙由闸侧构造：① 推过 1.0 的变异体必须让 `Tesc` 红；"
                                 "② 把下侧覆盖缩回 build_only 的变异体必须让 `Te2` 红；③ 把测量牙改成恒真的"
                                 "变异体必须被元闸 `gate_name_must_match_gate_semantics` 抓到；"
                                 "牙台账报 missed/extra/all_caught（裁定 85.5 口径）"),
                      "90.4-2": "① 保留、不回退（`coverage_must_cover` 未动）",
                      "90.4-3": ("裁定 87.3 的可推翻条件以**逐维形式**触发；P0 只改极性、P1 = 逐维覆盖（待触发）。"
                                 "触发判据已机器化：见每行 `escalations_to_d[resolution_floor_uncalibrated]"
                                 ".ruling_90_4_3_trigger`"),
                      "90.4-4": ("权威接口 = npz + `--s1-frames`（标签 `formal40_bc_source`）；"
                                 "`--s1-lerobot` = 交叉核对臂（标签 `formal40_lerobot_crosscheck`，"
                                 "结构上进不了 BC）"),
                      "d_self_recorded_errors": ("#15 把软边界当硬界、#16 用中位数守逐维失效、"
                                                 "#17 以已被自己作废的理由否掉正确候选（裁定 90.5：14 → 17）"),
                      "c2_credit": ("裁定 90.5『记 C2 一功（下位纠正 D 第 10 次）』：C2 撞上与裁定直接冲突的实测时"
                                    "**没有自决改契约、也没有静默展宽**，而是把根因写进牙的 note 并报 D"),
                  },
                  "representation_version_change": ("① 改了表示 ⇒ 版本串换 `-v2` 并拼入 "
                                                    "`nc.coverage_version_token()`（含覆盖目标、头寸、"
                                                    "声明区间哈希、区间出处 sha）⇒ 值派生、不可手写；"
                                                    "先导档 stats 本就 `not_for_bc` ⇒ 无返工成本（裁定 87.3-3）"),
              },
              "load_pair": load_pair(),
              "verdict": ("RED" if (any(r["verdict"] == "RED" and not r.get("is_must_red_branch")
                                         and not r.get("is_stress_branch") for r in rows)
                                     or any(r["verdict"] != "RED" for r in rows
                                            if r.get("is_must_red_branch") or r.get("is_stress_branch")))
                          else "PASS"),
              "verdict_semantics": {
                  "rule": ("顶层 `verdict` = RED 当且仅当『存在一行既不是 must-red 也不是 stress、却红了』"
                           "或『存在一行本该红却没红』"),
                  # 这段**由本次运行的红牙计数拼出来**，不写死：修前它写的是"唯一来源是 held-out 家族"，
                  # 而 ① 落地后 held-out 家族已转绿、红的是 Tb/Tiv ⇒ 写死的语义说明会当场变成谎报
                  # （裁定 84.5 `top_level_aggregate_must_declare_semantics` 要求的是**当前**语义）。
                  "what_red_means_here": (
                      "**不等于**契约层或闸坏了。本产物里红的行与其牙（机器计数）："
                      f"主线臂红牙={ (mainline_finding or {}).get('red_tooth_counts') }；"
                      f"must-red/stress 臂是**设计成必须红**的（红不了 = 牙恒真）。"
                      "每行都带 `allowed_red_teeth`（由本次运行的测量事实派生）与 `unexplained_red_teeth`，"
                      "`all_red_explained=true` 即『红得逐条可解释』；解释不了的牙 ⇒ 闸必须报"),
                  "declared_per": "裁定 84.5 `top_level_aggregate_must_declare_semantics`（顶层聚合必须自报语义）",
                  "n_rows": len(rows),
                  "n_rows_red": sum(1 for r in rows if r["verdict"] == "RED"),
                  "n_rows_expected_red": sum(1 for r in rows if r.get("expected_verdict") == "RED"),
                  "n_rows_with_unexplained_red": sum(1 for r in rows if r.get("unexplained_red_teeth")),
                  "mainline_included": bool(mainline_finding is not None)},
              "polarity_rule": ("非 stress / 非 must-red 的行必须绿；stress 与 must-red 行**必须红**"
                                "（红不了 = 那把牙是恒真的，等于没有牙）。"
                                "**例外（显式登记而非静默）**：主线通路验证档的行会红 —— 那是**发现**"
                                "（本轮 ① 落地后：`Tb` = 分辨率代价，条件 b 的升级项；`Tiv` = 3 个维被示范"
                                "顶到软限位之外，条件 c 的数据/契约发现；F2 行另有 `Tr3` = 它的设计目的），"
                                "不是实现缺陷。处置 = 保留红 + 每行的 `allowed_red_teeth` **由测量派生**，"
                                "由闸断言『红得可解释』（任何解释不了的牙红 ⇒ 闸报）。**不**把这 8 行标成 "
                                "must_red_branch（那会把真实缺口洗成预期红），也**不**放宽阈值"),
              "must_red_branches_all_red": all(r["verdict"] == "RED" for r in rows
                                               if r.get("is_must_red_branch")) if any(
                  r.get("is_must_red_branch") for r in rows) else None}
    (out / "matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "mainline_status.json").write_text(json.dumps(
        {**mainline_status, "generated_at": now_iso(),
         "authority": "裁定 52/69：主线 stats 与 BC 训练数据同源；env/YAM 不得顶替"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": matrix["verdict"], "n_rows": len(rows),
                      "n_red_non_mustred": sum(1 for r in rows if r["verdict"] == "RED" and not r.get("is_must_red_branch")),
                      "must_red_all_red": matrix["must_red_branches_all_red"],
                      "mainline_status": mainline_status["status"],
                      "matrix": str((out / "matrix.json").relative_to(ROOT))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
