#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · T-C2-2 obs 键覆盖闸（**双向有牙**，裁定 49.2 / 54；阻塞台账 B3）。

## 这把闸判什么

消费侧（`harness/queue_td_learner.py` 的 `_obs_vector`）在读一条 obs 快照时，
**存入键集合与消费键集合必须完全对上**：
* 快照里有键没人读 ⇒ `LearnerRefused` 且**点名**（不许静默丢图）；
* 契约声明为必需的键缺席 ⇒ 同样拒绝（观测通道缺失 = 契约不符）；
* 只有 `state` / `state`+`environment_state` 的 ACT 线旧快照 ⇒ **仍须绿**（不破坏 C 的 17/17）；
* `state_dim` 语义与宽度检查**不变**（废掉它等于把 ACT 线既有判据一起废掉）。

## 双向牙（裁定 27.1：恒真的闸等于没有闸）

* **正向**：`--mode baseline` 的 G1–G12 全绿才算 PASS。
* **反向（文件级变异，各自跑独立子进程 + 独立 harness 副本，不改仓库文件）**：
  - `M1_coverage_check_non_raising`：`check_coverage` → `evaluate_coverage`（不抛）
  - `M2_swallow_violation`：把 `raise LearnerRefused(...)` 换成 `pass`
  - `M3_hardcode_state_keys`：`contract.state_keys` → 写死 `("state","environment_state")`
  - `M4_tautological_covered`：`harness/obs_key_coverage.py` 里 `covered = not ... ` → `covered = True`
  每个变异体都有 `must_go_red` / `must_stay_green` 两张清单，**两边都要对上**才算这条变异有效。
* **输入级反向变异** `R1_optional_hides_missing`：把图像键从 `required` 降成 `optional`
  ⇒ G5（缺失通道必须红）必须失效。用来证明 G5 的牙来自"声明为必需"，不是白送的。

## 纪律
* 产物落 `runs/vla/c2_obs_key_whitelist_20260929/`；变异体的 harness 副本落**产物目录内**，
  **一个字节都不改仓库里的 `harness/`**（变异结束后副本原样保留以便复核）。
* 计数/不存在类主张带 (mtime, 行数, 命令)；数值主张带 loadavg + nr_throttled（分母 = 12 核配额）。
* 状态词只用 v4 五档；产物里不出现「跑通 / 学会 / 达标」。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))
GATE_ID = "c2_gate_obs_key_coverage"
TASK_ID = "T-C2-2"
REPR_VERSION = "c2-gate-pi05shape-v1"
CONTRACT_VERSION = "v4-appendix01-2.3"

STATE_DIM = 14
START_STATE_14D = (0.0, -0.96, 1.16, 0.0, -0.3, 0.0, 0.099848,
                   0.0, -0.96, 1.16, 0.0, -0.3, 0.0, 0.099848)
POLICY_IMAGE_KEYS = ("observation.images.base_0_rgb",
                     "observation.images.left_wrist_0_rgb",
                     "observation.images.right_wrist_0_rgb")
ENV_CAMERA_KEYS = ("top", "left_wrist", "right_wrist")
POLICY_IMAGE_SHAPE = (3, 224, 224)
ENV_IMAGE_SHAPE = (480, 640, 3)

MUTATIONS = [
    {"id": "M1_coverage_check_non_raising",
     "target": "harness/queue_td_learner.py",
     "find": "        okc.check_coverage(obs.keys(), contract, kind=kind)",
     "replace": "        okc.evaluate_coverage(obs.keys(), contract, kind=kind)",
     "why": "把抛异常的覆盖检查换成不抛的纯判定 —— 最像『顺手优化』的一种改法，静默丢弃随即复活",
     "must_go_red": ["G3", "G5", "G8", "G13"],
     "must_stay_green": ["G1", "G2", "G4", "G6", "G7", "G9", "G10"]},
    {"id": "M2_swallow_violation",
     "target": "harness/queue_td_learner.py",
     "find": "        raise LearnerRefused(str(exc)) from exc",
     "replace": "        pass",
     "why": "把违规吞掉（本仓已有一例：modeling_pi05.py:1046-1047 把异常吞成 print）",
     "must_go_red": ["G3", "G5", "G8", "G13"],
     "must_stay_green": ["G1", "G2", "G4", "G6", "G7", "G9", "G10"]},
    {"id": "M3_hardcode_state_keys",
     "target": "harness/queue_td_learner.py",
     "find": "             for key in contract.state_keys if key in obs]",
     "replace": "             for key in (\"state\", \"environment_state\") if key in obs]",
     "why": "把键名写死回字面量 ⇒ 违反裁定 49.2 要求 1（不许写死键名清单），契约失去效力",
     "must_go_red": ["G10"],
     "must_stay_green": ["G1", "G2", "G3", "G4", "G6", "G7", "G8", "G9", "G13"]},
    {"id": "M4_tautological_covered",
     "target": "harness/obs_key_coverage.py",
     "find": "    covered = not unconsumed and not missing",
     "replace": "    covered = True",
     "why": "把判定改成恒真（裁定 27.1：恒真的闸等于没有闸）—— 这条专门检验闸本身不是同义反复",
     "must_go_red": ["G3", "G5", "G8", "G13"],
     "must_stay_green": ["G1", "G2", "G4", "G6", "G7", "G9", "G10"]},
]


# ------------------------------------------------------------------ 工具
def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:12]


def array_sha12(arr) -> str:
    a = np.ascontiguousarray(np.asarray(arr))
    return sha12(a.tobytes() + f"|{a.dtype}|{a.shape}".encode())


def fingerprint(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    raw = p.read_bytes()
    st = p.stat()
    return {"path": str(p), "sha256_12": sha12(raw), "n_bytes": len(raw),
            "n_lines": raw.decode("utf-8", "replace").count("\n"),
            "mtime": datetime.fromtimestamp(st.st_mtime, CST).isoformat(timespec="seconds")}


def machine_block() -> dict:
    la = Path("/proc/loadavg").read_text().split()
    cs = {}
    p = Path("/sys/fs/cgroup/cpu/cpu.stat")
    if p.exists():
        for line in p.read_text().splitlines():
            k, _, v = line.partition(" ")
            cs[k] = int(v)
    return {"ts": now_iso(), "loadavg_1m": float(la[0]), "loadavg_5m": float(la[1]),
            "loadavg_15m": float(la[2]), "cpu_stat": cs,
            "parallelism_denominator": "12-core cgroup quota（不是 nproc）",
            "nproc_host_not_the_denominator": os.cpu_count()}


def import_harness(import_root: Path):
    sys.path.insert(0, str(import_root))
    for mod in [m for m in list(sys.modules) if m == "harness" or m.startswith("harness.")]:
        del sys.modules[mod]
    from harness import queue_td_learner as qtl           # noqa: E402
    from harness import obs_key_coverage as okc           # noqa: E402
    from harness.obs_store import ObsStore                # noqa: E402
    return qtl, okc, ObsStore


# ------------------------------------------------------------------ obs 构造
def make_state() -> np.ndarray:
    return np.asarray(START_STATE_14D, dtype=np.float32)


def policy_images(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    return {k: rng.random(POLICY_IMAGE_SHAPE, dtype=np.float32) for k in POLICY_IMAGE_KEYS}


def env_images(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    return {k: rng.integers(0, 256, size=ENV_IMAGE_SHAPE, dtype=np.uint8) for k in ENV_CAMERA_KEYS}


# ------------------------------------------------------------------ 检查
def run_checks(import_root: Path, store_root: Path) -> list[dict]:
    qtl, okc, ObsStore = import_harness(import_root)
    store = ObsStore(root=store_root, contract_version=CONTRACT_VERSION)
    clock = [1_710_000_000_000_000_000]
    checks: list[dict] = []

    def put(obs: dict, tag: str) -> str:
        clock[0] += 1
        return store.put(obs, sampled_at_ns=clock[0], representation_version=REPR_VERSION,
                         episode_id=f"c2-gate-{tag}", abs_frame=0,
                         contract_version=CONTRACT_VERSION).obs_ref

    def call(ref: str, cfg, kind: str):
        try:
            return {"outcome": "returned", "vec": qtl._obs_vector(store, ref, cfg, kind=kind)}
        except qtl.LearnerRefused as exc:
            return {"outcome": "refused", "message": str(exc)}
        except Exception as exc:                            # noqa: BLE001
            return {"outcome": "raised_other", "type": type(exc).__name__, "message": str(exc)}

    def add(cid, claim, expected, measured, evidence=None, ok=None):
        checks.append({"id": cid, "claim": claim, "expected": expected, "measured": measured,
                       "ok": (expected == measured) if ok is None else ok,
                       "evidence": evidence})

    cfg = qtl.LearnerConfig(state_dim=STATE_DIM, action_dim=14, n=2, gamma=0.99)

    # ---- G1 / G2：ACT 线旧快照仍须绿（裁定 49.2 要求 2 的反向牙）
    ref_state = put({"state": make_state()}, "legacy_state")
    r = call(ref_state, cfg, "G1")
    add("G1", "只有 state 的 ACT 线旧快照仍绿（不破坏 C 的 17/17 回归基线）",
        "returned", r["outcome"],
        {"vec_shape": list(r["vec"].shape) if r["outcome"] == "returned" else None,
         "vec_sha12": array_sha12(r["vec"]) if r["outcome"] == "returned" else None,
         "obs_ref_sha12": ref_state[:12], "message": r.get("message")})

    ref_both = put({"state": make_state(),
                    "environment_state": np.zeros((6,), dtype=np.float32)}, "legacy_both")
    cfg20 = qtl.LearnerConfig(state_dim=STATE_DIM + 6, action_dim=14, n=2, gamma=0.99)
    r = call(ref_both, cfg20, "G2")
    add("G2", "state + environment_state 的旧快照仍绿，且拼接宽度 = 两者之和",
        {"outcome": "returned", "width": STATE_DIM + 6},
        {"outcome": r["outcome"],
         "width": int(r["vec"].shape[0]) if r["outcome"] == "returned" else None},
        {"message": r.get("message"), "obs_ref_sha12": ref_both[:12]})

    # ---- G3：π₀.₅ 策略层形态 + 未声明契约 ⇒ 必须点名拒绝
    ref_p = put({"state": make_state(), **policy_images(20260929)}, "pi05_policy")
    r = call(ref_p, cfg, "G3")
    named = sorted(k for k in POLICY_IMAGE_KEYS if r["outcome"] == "refused" and k in r["message"])
    add("G3", "π₀.₅ 策略层形态（state + 3×[3,224,224] 图像）未声明契约 ⇒ 拒绝且点名三路图像键",
        {"outcome": "refused", "named": list(POLICY_IMAGE_KEYS)},
        {"outcome": r["outcome"], "named": named},
        {"message": (r.get("message") or "")[:400], "obs_ref_sha12": ref_p[:12]})

    # ---- G4：显式声明三路图像为必需 ⇒ 绿，且覆盖报告显示 4 键全消费
    contract = okc.declare_contract(required_keys=POLICY_IMAGE_KEYS,
                                    representation_version=REPR_VERSION,
                                    note="π₀.₅ 三路图像声明为必需（裁定 49.2 要求 1：键名由调用方给）")
    cfg_decl = qtl.LearnerConfig(state_dim=STATE_DIM, action_dim=14, n=2, gamma=0.99,
                                 obs_key_contract=contract)
    r = call(ref_p, cfg_decl, "G4")
    cov = okc.evaluate_coverage(store.get(ref_p).keys(), contract, kind="G4")
    add("G4", "显式声明三路图像为必需 ⇒ 绿，且消费键集合覆盖全部 4 个存入键",
        {"outcome": "returned", "n_consumed": 4, "covered": True},
        {"outcome": r["outcome"], "n_consumed": len(cov.keys_consumed), "covered": cov.covered},
        {"coverage": cov.as_dict(), "message": r.get("message")})

    # ---- G5：声明必需却缺席一路 ⇒ 必须拒绝并点名缺席键
    partial = {"state": make_state(), POLICY_IMAGE_KEYS[0]: policy_images(1)[POLICY_IMAGE_KEYS[0]]}
    ref_miss = put(partial, "pi05_missing_two")
    r = call(ref_miss, cfg_decl, "G5")
    missing = sorted(k for k in POLICY_IMAGE_KEYS[1:] if r["outcome"] == "refused" and k in r["message"])
    add("G5", "契约声明为必需、快照却缺席两路图像 ⇒ 拒绝且点名缺席键",
        {"outcome": "refused", "named": list(POLICY_IMAGE_KEYS[1:])},
        {"outcome": r["outcome"], "named": missing},
        {"message": (r.get("message") or "")[:400], "obs_ref_sha12": ref_miss[:12]})

    # ---- G6：宽度检查仍然活着（不能被新层废掉，裁定 49.2 要求 3）
    bad = qtl.LearnerConfig(state_dim=STATE_DIM - 1, action_dim=14, n=2, gamma=0.99)
    r = call(ref_state, bad, "G6")
    add("G6", "state_dim 配错仍触发 LearnerRefused（宽度检查未被新层废掉）",
        {"outcome": "refused", "mentions_width": True},
        {"outcome": r["outcome"],
         "mentions_width": r["outcome"] == "refused" and "观测维度" in r["message"]},
        {"message": (r.get("message") or "")[:200]})

    # ---- G7：state_dim 语义不变（旧快照出来的宽度仍等于配置值）
    r = call(ref_state, cfg, "G7")
    add("G7", "state_dim 语义不变：旧快照返回宽度 == cfg.state_dim == 14",
        STATE_DIM, int(r["vec"].shape[0]) if r["outcome"] == "returned" else None,
        {"outcome": r["outcome"]})

    # ---- G8：env 侧相机键名（S4 注入名）未声明 ⇒ 点名拒绝
    ref_e = put({"state": make_state(), **env_images(20260929)}, "pi05_envcam")
    r = call(ref_e, cfg, "G8")
    named = sorted(k for k in ENV_CAMERA_KEYS if r["outcome"] == "refused" and k in r["message"])
    add("G8", "env 侧相机键名 top/left_wrist/right_wrist（480×640×3 uint8）未声明 ⇒ 点名拒绝",
        {"outcome": "refused", "named": sorted(ENV_CAMERA_KEYS)},
        {"outcome": r["outcome"], "named": named},
        {"message": (r.get("message") or "")[:400], "obs_ref_sha12": ref_e[:12]})

    # ---- G9：gym-aloha 原生 agent_pos 命名 ⇒ 不许静默通过
    ref_a = put({"agent_pos": make_state(), "top": env_images(555003)["top"]}, "raw_agent_pos")
    r = call(ref_a, cfg, "G9")
    add("G9", "gym-aloha 原生键名（agent_pos 而非 state）⇒ 拒绝，不许静默产出零信息向量",
        "refused", r["outcome"],
        {"message": (r.get("message") or "")[:300], "obs_ref_sha12": ref_a[:12]})

    # ---- G10：键名不写死（裁定 49.2 要求 1）—— 换一个 state 键名，契约说了算
    alt = okc.declare_contract(state_keys=("proprio",))
    cfg_alt = qtl.LearnerConfig(state_dim=STATE_DIM, action_dim=14, n=2, gamma=0.99,
                                obs_key_contract=alt)
    ref_alt = put({"proprio": make_state()}, "alt_state_key")
    r = call(ref_alt, cfg_alt, "G10")
    add("G10", "键名不写死：契约声明 state_keys=('proprio',) 时，该键必须真被消费",
        {"outcome": "returned", "width": STATE_DIM},
        {"outcome": r["outcome"],
         "width": int(r["vec"].shape[0]) if r["outcome"] == "returned" else None},
        {"message": r.get("message"), "obs_ref_sha12": ref_alt[:12]})

    # ---- G13：混合命名（桥接层扁平化后**又留着**原始键）⇒ 覆盖检查是唯一的拦截点
    # 为什么单列：G9（只有 agent_pos）即使覆盖检查被拿掉也会被 `:137`「里没有 state」拦住，
    # 所以 G9 对"覆盖层是否生效"**没有判别力**（实测：M1/M2/M4 三个变异体下 G9 仍绿）。
    # G13 的快照里 `state` 在位 ⇒ 旧检查全过，只有覆盖层能发现 `agent_pos`/`top` 没人读。
    ref_mix = put({"state": make_state(), "agent_pos": make_state(),
                   "top": env_images(555004)["top"]}, "mixed_naming")
    r = call(ref_mix, cfg, "G13")
    named = sorted(k for k in ("agent_pos", "top") if r["outcome"] == "refused" and k in r["message"])
    add("G13", "混合命名（state 在位 + 原始 agent_pos/top 无人消费）⇒ 必须点名拒绝，不许静默产出 14 维向量",
        {"outcome": "refused", "named": ["agent_pos", "top"]},
        {"outcome": r["outcome"], "named": named},
        {"message": (r.get("message") or "")[:400], "obs_ref_sha12": ref_mix[:12],
         "why_discriminating": "state 在位 ⇒ 宽度检查与 `:137` 都过，只有覆盖层能拦"})

    # ---- G11：未声明契约时的来源必须显式（不许静默变成"什么都不检查"）
    derived = okc.derive_contract()
    add("G11", "cfg.obs_key_contract=None ⇒ 用 derive_contract()，且来源标 derived_from_consumer",
        {"source": "derived_from_consumer", "consumed": ["state", "environment_state"]},
        {"source": derived.source, "consumed": list(derived.consumed_keys)},
        {"default_cfg_field_is_none": cfg.obs_key_contract is None})

    # ---- G12：gym-aloha 原样嵌套 obs 无法内容寻址（跨 T-C2-3 / S4 的存储侧事实）
    try:
        clock[0] += 1
        store.put({"pixels": {"top": np.zeros((8, 8, 3), dtype=np.uint8)},
                   "agent_pos": make_state()}, sampled_at_ns=clock[0],
                  representation_version=REPR_VERSION, episode_id="c2-gate-nested",
                  abs_frame=0, contract_version=CONTRACT_VERSION)
        nested = {"raised": False}
    except TypeError as exc:
        nested = {"raised": True, "type": "TypeError", "message": str(exc)}
    except Exception as exc:                                # noqa: BLE001
        nested = {"raised": True, "type": type(exc).__name__, "message": str(exc)}
    add("G12", "gym-aloha `pixels_agent_pos` 的原样嵌套 obs 无法内容寻址 ⇒ S4 必须扁平化后再入库",
        {"raised": True, "type": "TypeError"},
        {"raised": nested.get("raised", False), "type": nested.get("type")},
        {"provenance": "gym_aloha/env.py:143-148；harness/obs_store.py:92 的 object 数组卫语句",
         "message": nested.get("message"),
         "note": "这是**存储侧**事实，不是消费侧缺陷；口径不同不可与 G3/G8 混算"})

    # ---- R1：输入级反向变异 —— required 降成 optional 会抹掉 G5 的牙
    loose = okc.declare_contract(optional_keys=POLICY_IMAGE_KEYS,
                                 representation_version=REPR_VERSION,
                                 note="反向变异：图像键降为 optional")
    cfg_loose = qtl.LearnerConfig(state_dim=STATE_DIM, action_dim=14, n=2, gamma=0.99,
                                  obs_key_contract=loose)
    r = call(ref_miss, cfg_loose, "R1")
    add("R1", "反向变异：图像键声明成 optional 后，缺席两路不再被发现 ⇒ 证明 G5 的牙来自 required",
        "returned", r["outcome"],
        {"message": r.get("message"),
         "interpretation": "本条**期望 G5 的牙失效**；若这里变成 refused，说明 optional 语义被写错"})

    return checks


# ------------------------------------------------------------------ 变异体
def build_mutant(mut: dict, dest_root: Path) -> dict:
    src = REPO_ROOT / "harness"
    dst = dest_root / "harness"
    if dst.exists():
        # 本仓禁删既有产物；但**包名必须恰好是 `harness`**（子进程靠 PYTHONPATH/`--import-root`
        # 解析 `import harness`），所以不能就地改名 —— 改名会让子进程 import 到**未变异的旧副本**，
        # 变异体静默失效（那正是"假绿"）。⇒ 要求调用方给一个全新的 dest_root。
        return {"ok": False,
                "why": f"{dst} 已存在：拒绝在旧副本上变异（会 import 到未变异的树）。"
                       f"请用全新的 dest_root（本仓禁删，旧副本原样保留）",
                "target": str(dst)}
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    target = dst / Path(mut["target"]).name
    text = target.read_text(encoding="utf-8")
    if text.count(mut["find"]) != 1:
        return {"ok": False, "why": f"锚点出现 {text.count(mut['find'])} 次（要求恰好 1 次）",
                "target": str(target)}
    target.write_text(text.replace(mut["find"], mut["replace"]), encoding="utf-8")
    fp = fingerprint(target)
    return {"ok": True, "mutant_root": str(dest_root), "target": fp,
            "find": mut["find"], "replace": mut["replace"]}


def run_baseline(import_root: Path, out_dir: Path, *, label: str) -> dict:
    store_root = out_dir / "obs_store"
    t0 = time.time()
    before = machine_block()
    checks = run_checks(import_root, store_root)
    after = machine_block()
    reds = [c["id"] for c in checks if not c["ok"]]
    report = {
        "gate_id": GATE_ID, "task_id": TASK_ID, "label": label, "generated_at": now_iso(),
        "import_root": str(import_root),
        "verdict": "PASS" if not reds else "RED",
        "n_checks": len(checks), "n_red": len(reds), "red_ids": reds,
        "checks": checks,
        "machine_before": before, "machine_after": after,
        "nr_throttled_delta": after["cpu_stat"].get("nr_throttled", 0)
        - before["cpu_stat"].get("nr_throttled", 0),
        "elapsed_s": round(time.time() - t0, 3),
        "gate_script": fingerprint(Path(__file__).resolve()),
        # 指纹必须指向**实际被 import 的那棵树**（变异体子进程里它不是仓库根），
        # 否则产物会把变异体标成仓库原文件 —— 那正是 T-C2-4 要抓的失真形态。
        "probed_files": [fingerprint(import_root / "harness" / "queue_td_learner.py"),
                         fingerprint(import_root / "harness" / "obs_key_coverage.py")],
        "probed_files_are_repo_originals": import_root == REPO_ROOT,
        "status_word_v4": "回放通过（离线快照回放层）；不含任何能力主张",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gate_verdict.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report


def run_mutations(out_root: Path) -> dict:
    results = []
    for mut in MUTATIONS:
        # 每次跑都用**全新**的 run 目录：既不删旧证据，也保证 `harness` 包名唯一对应本次变异
        mroot = out_root / "mutants" / mut["id"] / f"run_{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}"
        mroot.mkdir(parents=True, exist_ok=True)
        built = build_mutant(mut, mroot)
        if not built["ok"]:
            results.append({"id": mut["id"], "ok": False, "stage": "build", "why": built["why"]})
            continue
        cmd = [sys.executable, str(Path(__file__).resolve()), "--mode", "baseline",
               "--import-root", str(mroot), "--out", str(mroot / "gate_out"),
               "--label", f"mutant:{mut['id']}"]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
        vpath = mroot / "gate_out" / "gate_verdict.json"
        if not vpath.exists():
            results.append({"id": mut["id"], "ok": False, "stage": "run",
                            "rc": proc.returncode, "stderr": proc.stderr[-800:]})
            continue
        rep = json.loads(vpath.read_text(encoding="utf-8"))
        red = set(rep["red_ids"])
        must_red, must_green = set(mut["must_go_red"]), set(mut["must_stay_green"])
        ok = must_red <= red and not (must_green & red)
        results.append({
            "id": mut["id"], "ok": ok, "stage": "verdict", "why": mut["why"],
            "target": built["target"], "find": mut["find"], "replace": mut["replace"],
            "expected_must_go_red": sorted(must_red), "expected_must_stay_green": sorted(must_green),
            "observed_red_ids": sorted(red),
            "missed_red": sorted(must_red - red), "false_red": sorted(must_green & red),
            "mutant_gate_verdict_path": str(vpath),
            "subprocess_rc": proc.returncode,
        })
        print(f"  [{'ok ' if ok else 'FAIL'}] {mut['id']}: observed_red={sorted(red)} "
              f"missed={sorted(must_red - red)} false_red={sorted(must_green & red)}", flush=True)
    return {"generated_at": now_iso(), "n_mutations": len(MUTATIONS),
            "n_ok": sum(1 for r in results if r.get("ok")),
            "all_ok": all(r.get("ok") for r in results), "mutations": results}


def main() -> int:
    ap = argparse.ArgumentParser(description="C2 · T-C2-2 obs 键覆盖闸")
    ap.add_argument("--mode", default="full", choices=["baseline", "mutations", "full"])
    ap.add_argument("--import-root", default=str(REPO_ROOT),
                    help="从哪个根 import harness（变异体子进程用；默认 = 仓库根）")
    ap.add_argument("--out", default="runs/vla/c2_obs_key_whitelist_20260929/gate_20260929")
    ap.add_argument("--label", default="repo_baseline")
    args = ap.parse_args()

    out_root = Path(args.out) if Path(args.out).is_absolute() else (REPO_ROOT / args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    import_root = Path(args.import_root)

    rc = 0
    base = run_baseline(import_root, out_root, label=args.label)
    print(f"[{args.label}] verdict={base['verdict']} n_checks={base['n_checks']} "
          f"red={base['red_ids']} nr_throttled_delta={base['nr_throttled_delta']}", flush=True)
    for c in base["checks"]:
        print(f"  [{'PASS' if c['ok'] else 'RED '}] {c['id']}: {c['claim'][:78]}", flush=True)
    if base["verdict"] != "PASS":
        rc = 1

    if args.mode in ("mutations", "full") and import_root == REPO_ROOT:
        mut = run_mutations(out_root)
        (out_root / "mutation_verdict.json").write_text(
            json.dumps(mut, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[mutations] {mut['n_ok']}/{mut['n_mutations']} ok "
              f"all_ok={mut['all_ok']}", flush=True)
        if not mut["all_ok"]:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
