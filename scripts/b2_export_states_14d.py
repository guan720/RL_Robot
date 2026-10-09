#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B2 · `states_14d.npz` 导出器 —— D 执行单 §17-4 的**关键路径唯一卡点**（裁定 82②）。

## 它解决什么
C2 的主线 stats（`harness/norm_contract.py` 的 `SOURCE_S1_DEMO`）卡在
`c2_build_norm_stats.py --s1-frames <npz>` 的输入上；C2 三次写
`mainline_status.json = waiting_for_s1_pilot_5` 并三次拒绝用 env 诊断档 / YAM ABC-130k 顶替。
本脚本把**已落地且已过 16 道闸**的 S1 仿真双向示范数据集导出成 C2 的 `--s1-frames` 契约件。

## 契约（D 执行单 §17-4 原文 = C2 的 `interface_ask_to_b2`，逐字对齐）
* `frames=[N,14] float64`（按集拼接、集序号升序）
* `start_poses=[E,14]`
* `physical_range=[14]`（臂关节读 `jnt_range`、夹爪维 = 1.0）
* `manifest.json`（五元标注 + `control_hz=29.4118` + `episode_horizon_s=10.2`）
* 导出**不得改变 LeRobot 数据集本体**（两条出口并存）
* 在 `demo_manifest.json` 里记 npz 的 sha256-12 + `as_of` mtime

## 三条自查纪律（本脚本自己守，也自己留证）
1. **不占卡**：强制 `MUJOCO_GL=disable`（只读模型 XML，不起 GL 上下文），并在导出前后各拍一次
   `nvidia-smi` 计算进程清单落进产物 ⇒ 可事后证明本脚本没碰 GPU（裁定 73 的优先级 A2>C2>E>B2、
   §17-7「现在不要上卡」）。
2. **数据源是已落地的产物，不是重跑**：`frames` 直接读 `pi05_lerobot` 的 parquet
   （`observation.state`，parquet 里是 `fixed_size_list<float>[14]` = float32 存储），
   加宽到 float64 并**逐位自证无损**；`start_poses` 读 sidecar 的
   `reset_state_vs_a2_contract.reset_value_full_precision`（全精度，且 sidecar 已自证
   `vs_upstream_bitwise_equal`）。⇒ 与 BC 训练数据**同源**（裁定 52/69），且不引入第二次仿真。
3. **口径冲突不静默裁决**：D 的契约文本写「夹爪维 = 1.0，同 `scripts/c2_collect_env_states.py` 口径」，
   但该脚本**现行版**（本脚本只读 import 它的 `physical_range()`）实测夹爪维行程 = **0.91001**
   （手指滑动关节 `jnt_range=[0.021,0.057]` 经 upstream `normalize_puppet_gripper_position` 换算），
   且其 docstring 明写「旧版本这里写的是『夹爪维行程 = 1.0』」= 已勘误的缺陷口径。
   ⇒ 本脚本**两个都写**：`physical_range`（= D 契约字面，夹爪 1.0；也正是 C2
   `resolve_physical_range()` 标注为「旧口径，已知缺陷」的那个槽位）+
   `physical_range_declared_c2_caliber` / `physical_range_effective`（= C2 现行口径），
   并把冲突连同双侧文件 sha256-12 / mtime / 命令原文写进 `contract_conflict`，**交 D 裁**。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

# **必须在 import mujoco / gym_aloha 之前**定死：本脚本不起 GL 上下文（不占卡）。
_FORCED_GL = "disable"
_GL_BEFORE_IMPORT = os.environ.get("MUJOCO_GL")
os.environ["MUJOCO_GL"] = _FORCED_GL

import numpy as np                                                  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_DIM = 14
GRIPPER_STATE_DIMS = (6, 13)
GRIPPER_RANGE_CONTRACT_LITERAL = 1.0     # D 执行单 §17-4 的字面值（见模块 docstring 的冲突说明）
CONTROL_HZ_CONTRACT = 29.4118            # D 契约要求的标注值
EPISODE_HORIZON_S_CONTRACT = 10.2        # 裁定 65-2：300 步 × 0.034 s
STATE_LAYOUT = ["left_arm_joint_%d" % i for i in range(6)] + ["left_gripper_normalized"] + \
               ["right_arm_joint_%d" % i for i in range(6)] + ["right_gripper_normalized"]


# ---------------------------------------------------------------- 取证小工具
def sha12(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def mtime_iso(p: Path) -> Optional[str]:
    p = Path(p)
    if not p.exists():
        return None
    return _dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().replace(microsecond=0).isoformat()


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def load_pair() -> dict:
    """数值主张必须带负载对（分母 = cgroup 配额 12 核），与 C2 同口径。"""
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


def nvidia_smi_snapshot(tag: str) -> dict:
    """拍一次 GPU 计算进程 + 利用率。**只为证明本脚本没上卡**，不作任何吞吐主张。"""
    out: dict[str, Any] = {"tag": tag, "ts": now_iso()}
    for key, q in (("compute_apps", "--query-compute-apps=pid,process_name,used_memory"),
                   ("gpu_util", "--query-gpu=utilization.gpu,utilization.memory,memory.used")):
        cmd = ["nvidia-smi", q, "--format=csv"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out[key] = {"ok": r.returncode == 0, "rc": r.returncode,
                        "stdout": (r.stdout or "").strip(), "stderr": (r.stderr or "").strip()[:300],
                        "command_verbatim": " ".join(cmd)}
        except Exception as exc:                                     # noqa: BLE001
            out[key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                        "command_verbatim": " ".join(cmd)}
    apps = out.get("compute_apps", {})
    lines = [ln for ln in (apps.get("stdout") or "").splitlines()[1:] if ln.strip()]
    out["n_foreign_compute_apps"] = len(lines)
    out["compute_app_lines"] = lines
    return out


def count_files(root: Path) -> dict:
    """穷举计数（红线 `absence_claim_requires_exhaustive_enumeration`：说"没写文件"必须穷举）。"""
    root = Path(root)
    if not root.exists():
        return {"root": str(root), "exists": False, "n_files": 0}
    files = [p for p in root.rglob("*") if p.is_file()]
    return {"root": str(root), "exists": True, "n_files": len(files),
            "bytes_total": int(sum(p.stat().st_size for p in files))}


def inventory(root: Path) -> dict[str, tuple[int, float]]:
    """路径级清单 {relpath: (size, mtime)}。计数不够：**别的智能体可能同时在写自己的目录**，
    只比总数会把"它写的"算成"我写的"（本线 01:05:46 实测就撞上了 C2 的 `gate/run_20260930_010545`）。"""
    root = Path(root)
    if not root.exists():
        return {}
    out = {}
    for f in root.rglob("*"):
        if f.is_file():
            st = f.stat()
            out[str(f.relative_to(root))] = (int(st.st_size), float(st.st_mtime))
    return out


def inventory_diff(before: dict, after: dict) -> dict:
    added = sorted(k for k in after if k not in before)
    removed = sorted(k for k in before if k not in after)
    changed = sorted(k for k in after if k in before and after[k] != before[k])
    return {"n_added": len(added), "n_removed": len(removed), "n_changed": len(changed),
            "added_head": added[:10], "removed_head": removed[:10], "changed_head": changed[:10],
            "added_newest_mtime": (max((after[k][1] for k in added), default=None)),
            "empty": not (added or removed or changed)}


def self_io() -> dict:
    """/proc/self/io 的写入计数。**这是"本进程有没有写"的决定性证据**：
    目录清单会被并发写者污染，但 `wchar` 只统计本进程发出的写系统调用字节数。"""
    p = Path("/proc/self/io")
    if not p.exists():
        return {"available": False}
    d = {}
    for line in p.read_text().splitlines():
        k, _, v = line.partition(":")
        d[k.strip()] = int(v.strip())
    return {"available": True, "wchar": d.get("wchar"), "write_bytes": d.get("write_bytes"),
            "syscw": d.get("syscw")}


# ---------------------------------------------------------------- 读已落地的数据集
def read_demo_manifest(dataset_dir: Path) -> dict:
    p = dataset_dir / "demo_manifest.json"
    if not p.exists():
        raise SystemExit(f"[RED] 找不到 {p}（--dataset-dir 指错？）")
    return json.loads(p.read_text(encoding="utf-8"))


def read_lerobot_frames(dataset_dir: Path, demo: dict) -> tuple[np.ndarray, dict]:
    """读 π₀.₅ LeRobot 出口的 `observation.state` ⇒ `frames=[N,14] float64`。

    为什么读这一侧：它是 BC 训练直接消费的那一份（裁定 52/69「主线 stats 必须与 BC 训练数据同源」）。
    """
    lr = dataset_dir / "pi05_lerobot"
    info_p = lr / "meta" / "info.json"
    info = json.loads(info_p.read_text(encoding="utf-8"))
    import pyarrow.parquet as pq

    data_files = sorted((lr / "data").rglob("*.parquet"))
    cols = ["observation.state", "episode_index", "frame_index", "index", "timestamp"]
    tables = [pq.read_table(f, columns=cols) for f in data_files]
    if not tables:
        raise SystemExit(f"[RED] {lr}/data 下没有 parquet")
    d: dict[str, list] = {c: [] for c in cols}
    for t in tables:
        td = t.to_pydict()
        for c in cols:
            d[c].extend(td[c])
    st = np.asarray(d["observation.state"], dtype=np.float64)
    ep = np.asarray(d["episode_index"], dtype=np.int64)
    fi = np.asarray(d["frame_index"], dtype=np.int64)
    gi = np.asarray(d["index"], dtype=np.int64)
    ts = np.asarray(d["timestamp"], dtype=np.float64)

    # ---- 排序：契约要求「按集拼接、集序号升序」；同时校验集内 frame_index 升序
    order = np.lexsort((fi, ep))
    already_sorted = bool((order == np.arange(len(order))).all())
    st, ep, fi, gi, ts = st[order], ep[order], fi[order], gi[order], ts[order]

    n = int(st.shape[0])
    ep_ids = sorted(set(ep.tolist()))
    per_ep = [int((ep == k).sum()) for k in ep_ids]
    bounds = [0]
    for c in per_ep:
        bounds.append(bounds[-1] + c)

    checks: list[dict] = []

    def chk(cid: str, ok: Optional[bool], required: str, observed: Any, note: str = "") -> None:
        checks.append({"id": cid, "verdict": ("PASS" if ok else ("RED" if ok is False else "N/A")),
                       "required": required, "observed": observed, "note": note})

    chk("X1_shape", st.shape == (n, STATE_DIM) and n > 0,
        f"frames 是 [N,{STATE_DIM}] 且 N>0", {"shape": list(st.shape)},
        "契约 §17-4：frames=[N,14] float64")
    chk("X2_finite", bool(np.isfinite(st).all()), "无 NaN/Inf",
        {"n_nonfinite": int((~np.isfinite(st)).sum())})
    chk("X3_float32_widen_lossless", bool((st.astype(np.float32).astype(np.float64) == st).all()),
        "parquet 的 float32 存储加宽到 float64 **逐位无损**",
        {"max_abs_diff_after_requant": float(np.abs(st.astype(np.float32).astype(np.float64) - st).max())},
        "parquet schema = fixed_size_list<element: float>[14]；info.json 声明 dtype=float32")
    chk("X4_index_is_global_position", bool((gi == np.arange(n)).all()),
        "lerobot `index` == 全局行号（G12 同源判据）",
        {"n_mismatch": int((gi != np.arange(n)).sum())})
    chk("X5_frame_index_contiguous_per_ep",
        all(bool((fi[ep == k] == np.arange(int((ep == k).sum()))).all()) for k in ep_ids),
        "每集 `frame_index` 从 0 连续（集内序号，不是全局）",
        {"per_ep_counts": per_ep})
    chk("X6_sorted_by_episode_asc", already_sorted,
        "文件里本来就是集序号升序（若不是，本脚本已 lexsort 重排并在此登记）",
        {"needed_resort": (not already_sorted)})

    # ---- 与 demo_manifest 的每集帧数对账（**这是"同源"的硬证据**）
    demo_eps = demo.get("episodes") or []
    demo_counts = [int(((e.get("metrics") or {}).get("n_frames")) or -1) for e in demo_eps]
    chk("X7_per_ep_counts_match_demo_manifest", demo_counts == per_ep,
        "parquet 每集帧数 == demo_manifest.episodes[*].metrics.n_frames（同序）",
        {"parquet": per_ep, "demo_manifest": demo_counts, "n_episodes_parquet": len(ep_ids),
         "n_episodes_demo_manifest": len(demo_eps)})

    # ---- 与 info.json 对账
    chk("X8_total_frames_match_info", int(info.get("total_frames", -1)) == n,
        "N == meta/info.json.total_frames", {"info": info.get("total_frames"), "measured": n})
    chk("X9_total_episodes_match_info", int(info.get("total_episodes", -1)) == len(ep_ids),
        "E == meta/info.json.total_episodes",
        {"info": info.get("total_episodes"), "measured": len(ep_ids)})

    # ---- 时间基：timestamp == frame_index × dt（每集从 0 起算）
    dt = float(((demo.get("frequency") or {}).get("DT")) or 0.034)
    ts_expect = fi.astype(np.float64) * dt
    dts = float(np.abs(ts - ts_expect).max()) if n else 0.0
    chk("X10_timestamp_timebase", dts <= 1e-6,
        f"`timestamp` == frame_index × DT（DT={dt}），每集从 0 起算",
        {"max_abs_dev_s": dts, "timestamp_dtype_in_parquet": "float(float32)"},
        "float32 存储 ⇒ 偏差量级 1e-6 属表示误差，不是时间基错位")

    # ---- fps 精确性（D §17-3 的口径问题：容器里是不是取整 fps）
    fps_info = float(info.get("fps", -1.0))
    fps_rational = (demo.get("frequency") or {}).get("fps_rational_in_video_container")
    chk("X11_fps_not_rounded", abs(fps_info - 500.0 / 17.0) < 1e-12,
        "info.json 的 fps == 500/17 的精确值（不是取整 30）",
        {"fps_info_json": repr(fps_info), "exact_500_over_17": repr(500.0 / 17.0),
         "abs_diff": abs(fps_info - 500.0 / 17.0), "fps_rational_in_container": fps_rational})

    meta = {
        "source": "pi05_lerobot/data/**.parquet → observation.state",
        "data_files": [{"path": str(f.relative_to(ROOT)), "sha256_12": sha12(f),
                        "mtime": mtime_iso(f), "n_rows": int(pq.read_metadata(f).num_rows)}
                       for f in data_files],
        "info_json": {"path": str(info_p.relative_to(ROOT)), "sha256_12": sha12(info_p),
                      "mtime": mtime_iso(info_p), "fps": fps_info,
                      "total_episodes": info.get("total_episodes"),
                      "total_frames": info.get("total_frames"),
                      "codebase_version": info.get("codebase_version"),
                      "robot_type": info.get("robot_type")},
        "parquet_state_storage": "fixed_size_list<element: float>[14]（float32）",
        "npz_frames_dtype": "float64（float32 值无损加宽；见 X3）",
        "n_frames": n, "n_episodes": len(ep_ids), "per_episode_counts": per_ep,
        "episode_boundaries": bounds, "episode_index_values": ep_ids,
        "order_rule": "集序号升序、集内 frame_index 升序（契约 §17-4「按集拼接、集序号升序」）",
        "dt": dt, "checks": checks,
    }
    return st, meta


def read_start_poses(dataset_dir: Path, demo: dict, frames: np.ndarray,
                     ep_counts: list[int]) -> tuple[np.ndarray, dict]:
    """`start_poses=[E,14]` = 每集 **reset 后、第一步之前**的全精度状态（C2「collector reset frame」口径）。

    ⚠ 与 `frames` 的第 0 帧**不是同一个量**：数据集第 0 帧是丢掉 12 步沉降之后的 pre-step 状态。
    两者都写进产物并给出实测差，避免下游把 start_pose 当 frame0 用。
    """
    eps = demo.get("episodes") or []
    rows, checks = [], []
    per_ep = []
    for i, e in enumerate(eps):
        sp = Path(e.get("sidecar") or "")
        if not sp.exists():
            raise SystemExit(f"[RED] 第 {i} 集的 sidecar 不存在：{sp}")
        sc = json.loads(sp.read_text(encoding="utf-8"))
        rs = ((sc.get("metrics") or {}).get("reset_state_vs_a2_contract") or {})
        v = rs.get("reset_value_full_precision")
        if v is None or len(v) != STATE_DIM:
            raise SystemExit(f"[RED] {sp.name} 缺 reset_value_full_precision（G14 的证据字段）")
        rows.append(np.asarray(v, dtype=np.float64))
        per_ep.append({
            "episode_index": i, "ep_id": e.get("ep_id"), "direction": e.get("direction"),
            "seed": e.get("seed"),
            "sidecar": {"path": str(sp.relative_to(ROOT)), "sha256_12": sha12(sp), "mtime": mtime_iso(sp)},
            "reset_value_full_precision": [float(x) for x in v],
            "vs_upstream_bitwise_equal": rs.get("vs_upstream_bitwise_equal"),
            "vs_upstream_max_abs_diff": rs.get("vs_upstream_max_abs_diff"),
            "vs_contract_max_abs_diff": rs.get("vs_contract_max_abs_diff"),
            "contract_rounding_decimals": rs.get("contract_rounding_decimals"),
            "frame0_of_this_episode": [float(x) for x in frames[sum(ep_counts[:i])].tolist()],
            "start_pose_vs_frame0_max_abs_diff": float(np.max(np.abs(
                np.asarray(v, dtype=np.float64) - frames[sum(ep_counts[:i])]))),
        })
    start = np.asarray(rows, dtype=np.float64).reshape(len(rows), STATE_DIM)

    uniq = np.unique(start, axis=0)
    checks.append({"id": "X12_start_pose_shape", "verdict": "PASS" if start.shape == (len(eps), STATE_DIM) else "RED",
                   "required": f"start_poses=[E,{STATE_DIM}]，E == demo_manifest.episodes 数",
                   "observed": {"shape": list(start.shape), "n_episodes": len(eps)}})
    checks.append({"id": "X13_start_pose_finite",
                   "verdict": "PASS" if bool(np.isfinite(start).all()) else "RED",
                   "required": "无 NaN/Inf", "observed": {"n_nonfinite": int((~np.isfinite(start)).sum())}})
    checks.append({"id": "X14_start_pose_all_equal_upstream_reset",
                   "verdict": "PASS" if len(uniq) == 1 else "WARN",
                   "required": "gym_aloha 的 reset 是常量起姿 ⇒ E 行应逐位相同（若不同必须能解释）",
                   "observed": {"n_unique_rows": int(len(uniq)),
                                "row0": [float(x) for x in uniq[0].tolist()],
                                "abs_max": float(np.abs(start).max())},
                   "note": "上游常量重构见 sidecar 的 upstream_reconstruction；A2 契约 state_raw_14d 是 6 位小数存的"})
    checks.append({"id": "X15_start_pose_is_not_frame0",
                   "verdict": "PASS" if float(np.abs(start[0] - frames[0]).max()) > 0.0 else "RED",
                   "required": "start_pose（reset 态）≠ frames[0]（沉降后 pre-step 态）——两者必须分清",
                   "observed": {"max_abs_diff_ep0": float(np.abs(start[0] - frames[0]).max()),
                                "per_episode_max_abs_diff": [r["start_pose_vs_frame0_max_abs_diff"] for r in per_ep]},
                   "note": "12 步沉降（settle_steps_dropped）里腕被 plan_align 对齐 ⇒ 起姿与第 0 帧本就不同"})
    meta = {"source": "sidecar/*.json → metrics.reset_state_vs_a2_contract.reset_value_full_precision",
            "caliber": "reset 后、第一步之前（= C2 `--start-pose collector` 的「collector reset frame」口径）",
            "n_episodes": int(start.shape[0]), "per_episode": per_ep, "checks": checks}
    return start, meta


# ---------------------------------------------------------------- 物理行程（只读复用 C2 的口径函数）
def import_c2_collector() -> tuple[Any, dict]:
    """**只读** import `scripts/c2_collect_env_states.py`，用它的 `physical_range()`，不复制公式。

    为什么必须 import 而不是自己写一遍：D 的契约要求「同 `scripts/c2_collect_env_states.py` 口径」。
    自己重写一套就会有两套真相（这正是该文件 docstring 记录的历史缺陷：内联第二套 qpos 映射 ⇒ 差 175×）。
    """
    p = ROOT / "scripts" / "c2_collect_env_states.py"
    ident = {"path": str(p.relative_to(ROOT)), "sha256_12": sha12(p), "mtime": mtime_iso(p),
             "n_lines": len(p.read_text(encoding='utf-8').splitlines()),
             "import_mode": "importlib（只读；本脚本不写 C2 的任何文件）"}
    spec = importlib.util.spec_from_file_location("b2_ro_c2_collect_env_states", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                     # type: ignore[union-attr]
    return mod, ident


def physical_ranges(c2mod: Any, frames: np.ndarray) -> tuple[dict, list[dict]]:
    import mujoco
    import gym_aloha
    xml = Path(gym_aloha.__file__).resolve().parent / "assets" / "bimanual_viperx_transfer_cube.xml"

    class _Phys:                                                     # 只用到 .model
        def __init__(self, model):
            self.model = model

    model = mujoco.MjModel.from_xml_path(str(xml))
    declared_c2, prov_c2 = c2mod.physical_range(_Phys(model))
    declared_c2 = np.asarray(declared_c2, dtype=np.float64)

    contract_literal = declared_c2.copy()
    for d in GRIPPER_STATE_DIMS:
        contract_literal[d] = GRIPPER_RANGE_CONTRACT_LITERAL

    observed = frames.max(axis=0) - frames.min(axis=0)
    effective = np.maximum(declared_c2, observed)

    prov = []
    for i in range(STATE_DIM):
        c2p = next((x for x in prov_c2 if x.get("dim") == i), {})
        prov.append({
            "dim": i, "name": STATE_LAYOUT[i], "joint": c2p.get("joint"),
            "qpos_idx": c2p.get("qpos_idx"), "jnt_range": c2p.get("jnt_range"),
            "state_interval_c2_caliber": c2p.get("state_interval"),
            "declared_c2_caliber": float(declared_c2[i]),
            "contract_literal": float(contract_literal[i]),
            "observed_travel_this_dataset": float(observed[i]),
            "effective": float(effective[i]),
            "effective_binding_side": ("observed_travel" if observed[i] > declared_c2[i] + 1e-12
                                       else "declared_jnt_range"),
            "bound_kind": c2p.get("bound_kind"),
            "provenance_c2": c2p.get("provenance"),
        })
    out = {
        "physical_range_contract_literal": contract_literal,
        "physical_range_declared_c2_caliber": declared_c2,
        "physical_range_effective": effective,
        "observed_travel": observed,
        "provenance": prov,
        "model_xml": {"path": str(xml), "exists": bool(xml.exists()), "sha256_12": sha12(xml),
                      "mtime": mtime_iso(xml), "njnt": int(model.njnt), "nq": int(model.nq),
                      "mujoco_version": getattr(mujoco, "__version__", "unknown"),
                      "loaded_with": "mujoco.MjModel.from_xml_path（只读模型，不起 GL、不占卡）"},
        "dims_where_observed_exceeds_declared": [int(i) for i in range(STATE_DIM)
                                                 if observed[i] > declared_c2[i] + 1e-12],
        "gripper_dims": list(GRIPPER_STATE_DIMS),
        "rule": "effective = max(jnt_range 声明行程, 本数据集实测行程)；jnt_range 是软边界（C2 实测可被推出 +28.6%）",
    }
    return out, prov


# ---------------------------------------------------------------- 五元标注
def build_five_tuple(demo: dict, dataset_dir: Path) -> dict:
    """五元 = (venv, MUJOCO_GL 后端, mujoco 版本, 模型, 相机数与分辨率) + 负载对。

    ⚠ 关键口径纪律：**五元描述的是"采集那一次"**（egl + NVIDIA，见 demo_manifest.gl_identity），
    不是本导出进程（MUJOCO_GL=disable、不渲染）。所以这里调 `harness.env_gym_aloha.five_tuple_annotation()`
    拿到**规范键形**，再把进程相关字段用已落地证据覆盖，并逐字段登记覆盖来源。
    """
    from harness import env_gym_aloha as geg
    a2_contract = ROOT / "runs" / "vla" / "a2_pi05_contract_20260929" / "contract.json"
    cam_map, image_size, cam_src = {}, 224, None
    if a2_contract.exists():
        c = json.loads(a2_contract.read_text(encoding="utf-8"))
        cam_map = {k: v for k, v in (c.get("camera_map") or {}).items()} or \
                  {"base_0_rgb": "angle", "left_wrist_0_rgb": "left_wrist", "right_wrist_0_rgb": "right_wrist"}
        image_size = int(c.get("image_size") or 224)
        cam_src = {"path": str(a2_contract.relative_to(ROOT)), "sha256_12": sha12(a2_contract),
                   "mtime": mtime_iso(a2_contract), "fields_used": ["camera_map", "image_size"]}
    else:
        cam_map = {"base_0_rgb": "angle", "left_wrist_0_rgb": "left_wrist", "right_wrist_0_rgb": "right_wrist"}
        cam_src = {"path": None, "note": "A2 契约件不在，退到 demo_manifest 里记录的映射",
                   "fallback": True}

    class _Spec:                                                     # 只提供 five_tuple_annotation 用到的字段
        env_id = "gym_aloha/AlohaTransferCube-v0"
        render_images = True

    _Spec.cam_map = cam_map
    _Spec.image_size = image_size
    freq = demo.get("frequency") or {}
    timing = {"control_timestep_s": freq.get("DT"), "physics_timestep_s": freq.get("model_timestep_s"),
              "n_sub_steps": freq.get("n_sub_steps"), "control_hz": freq.get("control_hz_measured")}
    ft_export_process = geg.five_tuple_annotation(_Spec(), timing)

    act = demo.get("activation_env") or {}
    gli = demo.get("gl_identity") or {}
    ver = demo.get("versions") or {}
    overrides = {
        "venv": {"value": ver.get("venv_python") or demo.get("venv"),
                 "source": "demo_manifest.versions.venv_python（采集那一次的解释器）"},
        "interpreter": {"value": ver.get("venv_python") or demo.get("venv"),
                        "source": "demo_manifest.versions.venv_python"},
        "mujoco_gl_backend": {"value": act.get("MUJOCO_GL"),
                              "source": "demo_manifest.activation_env.MUJOCO_GL（采集时 = egl）"},
        "egl_vendor_filenames": {"value": act.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
                                 "source": "demo_manifest.activation_env.__EGL_VENDOR_LIBRARY_FILENAMES"},
        "ld_library_path_prefix_only": {"value": act.get("LD_LIBRARY_PATH"),
                                        "source": "demo_manifest.activation_env.LD_LIBRARY_PATH"},
        "mujoco_version": {"value": gli.get("mujoco_version") or ver.get("mujoco"),
                           "source": "demo_manifest.gl_identity.mujoco_version"},
    }
    ft = json.loads(json.dumps(ft_export_process))                   # deep copy（可 JSON 化）
    for k, v in overrides.items():
        ft[k] = v["value"]
    ft["model"] = {"env_id": _Spec.env_id, **timing,
                   "episode_horizon_steps_registered": freq.get("episode_horizon_steps_registered"),
                   "episode_horizon_s": freq.get("episode_horizon_s")}
    ft["five_tuple_fields"] = ["venv", "mujoco_gl_backend", "mujoco_version", "model", "cameras+resolution"]
    ft["overrides_applied"] = overrides
    ft["export_process_values_before_override"] = ft_export_process
    ft["override_reason"] = ("五元必须描述**采集那一次**（裁定 46.4/59：跨后端数字不得互搬）。"
                             "本导出进程 MUJOCO_GL=disable、不渲染，若直接落它的进程字段就等于把"
                             "『导出进程的后端』冒充成『采集后端』。")
    ft["gl_identity_landed"] = gli
    ft["camera_map_source"] = cam_src
    return ft


def near_constant_analysis(frames: np.ndarray, pr: dict, ep_bounds: list[int],
                           dir_codes: list[int]) -> dict:
    """把「哪些维在示范里几乎不动」量化，并给**实测**的物理解释（不是推断）。

    为什么这条对 C2 要紧：`norm_contract.near_constant_dims()` 会拿 `physical_range` 当分母，
    近常量维决定 F1 下限族（`floor_d = coef × 物理行程_d`）咬不咬得住；而这两个维恰好是
    双臂 `forearm_roll`——**因为右臂基座绕 z 转了 180°**，同一个"工具朝下"姿态在左臂要 roll≈0、
    在右臂要 roll≈π。基座朝向是从模型里实测的（`body_quat`），不是从 XML 读注释猜的。
    """
    import mujoco
    import gym_aloha
    xml = Path(gym_aloha.__file__).resolve().parent / "assets" / "bimanual_viperx_transfer_cube.xml"
    M = mujoco.MjModel.from_xml_path(str(xml))
    bases = {}
    for nm in ("vx300s_left", "vx300s_right"):
        i = M.body(nm).id
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, M.body_quat[i])
        bases[nm] = {"body_id": int(i),
                     "body_pos": [float(x) for x in M.body_pos[i]],
                     "body_quat_wxyz": [float(x) for x in M.body_quat[i]],
                     "yaw_deg_about_z": float(np.degrees(np.arctan2(R[3], R[0]))),
                     "measurement": "mujoco.MjModel.body_quat + mju_quat2Mat（实测读模型）"}
    travel = frames.max(axis=0) - frames.min(axis=0)
    declared = pr["physical_range_declared_c2_caliber"]
    ratio = travel / np.where(declared > 0, declared, np.nan)
    per_dim = []
    for i in range(STATE_DIM):
        per_dim.append({"dim": i, "name": STATE_LAYOUT[i],
                        "joint": pr["provenance"][i]["joint"],
                        "observed_travel": float(travel[i]),
                        "declared_c2_caliber": float(declared[i]),
                        "travel_over_declared": (float(ratio[i]) if np.isfinite(ratio[i]) else None),
                        "value_interval": [float(frames[:, i].min()), float(frames[:, i].max())],
                        "n_unique_float32_values": int(len(np.unique(frames[:, i]))),
                        "per_direction_travel": {"forward": None, "reverse": None}})
    for code, name in ((0, "forward"), (1, "reverse")):
        sel = np.concatenate([np.arange(ep_bounds[k], ep_bounds[k + 1])
                              for k in range(len(dir_codes)) if dir_codes[k] == code]).astype(int)
        for i in range(STATE_DIM):
            per_dim[i]["per_direction_travel"][name] = (
                float(frames[sel, i].max() - frames[sel, i].min()) if len(sel) else None)
        for i in range(STATE_DIM):
            per_dim[i]["n_frames_" + name] = int(len(sel))
    flagged = [d["dim"] for d in per_dim if d["travel_over_declared"] is not None
               and d["travel_over_declared"] < 0.05]
    return {
        "rule_used_here": "travel_over_declared < 0.05（本脚本的展示口径；**判定权在 C2 的 `near_constant_dims()`**，见 cross_check）",
        "dims_flagged_by_this_rule": flagged,
        "per_dim": per_dim,
        "arm_base_orientation_measured": bases,
        "explanation": {
            "claim": "两个近常量维都是 `forearm_roll`（dim3 左 / dim10 右）：左臂全程 ≈0（区间见 per_dim），右臂全程 ≈π。",
            "cause_measured": ("右臂基座 `vx300s_right` 的 body_quat = [0,0,0,1]（绕 z 转 180°，实测 yaw = "
                               + str(round(bases["vx300s_right"]["yaw_deg_about_z"], 4)) +
                               "°），左臂 = 单位四元数（yaw 0°）⇒ 专家用同一个『工具朝下』姿态（R_DOWN）时，"
                               "左臂 roll 解在 0 附近、右臂 roll 解在 π 附近。"),
            "status": "measured（基座朝向读模型；roll 区间读落盘 frames）",
            "consequence_for_c2": ("这两维的实测行程（≈0.039 / ≈0.093 rad）远小于声明行程 6.28316 ⇒ "
                                   "F1 下限族若拿声明行程当分母，floor 会远大于此维的真实动态范围，"
                                   "该维必被标近常量；这正是 C2 建 F1 族要处理的情形（不是数据缺陷）。"),
            "consequence_for_bc": ("BC 训练时这两维几乎不携带信息（示范里就是常量姿态）⇒ "
                                   "不能把『该维 loss 低』当成学到了 roll 控制；评测口径要显式排除或单列。"),
        },
    }


# ---------------------------------------------------------------- C2 消费端只读干跑
def c2_consumer_drycheck(npz_path: Path) -> dict:
    """用 **C2 自己的加载函数**（只读）证明契约件可被 `--s1-frames` 直接吃，不需要 C2 改代码。

    绝不写 C2 的产物目录：进出各拍一次文件穷举计数（红线
    `absence_claim_requires_exhaustive_enumeration` / `regression_driver_output_enumeration`）。
    """
    out: dict[str, Any] = {"mode": "read_only_import", "ran_at": now_iso()}
    c2_out = ROOT / "runs" / "vla" / "c2_norm_contract_20260929"
    before = count_files(c2_out)
    inv_before = inventory(c2_out)
    # 不让 import 落 __pycache__：否则"本进程写了 0 字节"这条证据就不干净了。
    _dwb = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    io_before = self_io()
    t_start = time.time()
    p = ROOT / "scripts" / "c2_build_norm_stats.py"
    out["c2_generator"] = {"path": str(p.relative_to(ROOT)), "sha256_12": sha12(p), "mtime": mtime_iso(p)}
    try:
        spec = importlib.util.spec_from_file_location("b2_ro_c2_build_norm_stats", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                                 # type: ignore[union-attr]
        frames, start0, prange, man = mod.load_frames(npz_path)
        out["load_frames"] = {
            "ok": True,
            "frames_shape": list(frames.shape), "frames_dtype": str(frames.dtype),
            "start_pose_shape": list(np.asarray(start0).shape),
            "physical_range_shape": list(prange.shape),
            "manifest_keys_found": sorted(man.keys())[:40],
            "manifest_read_from": str((npz_path.parent / "manifest.json").relative_to(ROOT)),
        }
        from harness import norm_contract as nc
        st = nc.build_stats(frames)
        out["build_stats"] = {
            "ok": True, "keys": sorted(st.keys()),
            "mean_round6": [round(float(x), 6) for x in np.asarray(st["mean"]).tolist()],
            "q01_round6": [round(float(x), 6) for x in np.asarray(st["q01"]).tolist()],
            "q99_round6": [round(float(x), 6) for x in np.asarray(st["q99"]).tolist()],
            "min_round6": [round(float(x), 6) for x in np.asarray(st["min"]).tolist()],
            "max_round6": [round(float(x), 6) for x in np.asarray(st["max"]).tolist()],
        }
        if hasattr(nc, "near_constant_dims"):
            try:
                ncd = nc.near_constant_dims({**st, "physical_range": prange})
                out["near_constant_dims"] = {"ok": True, "value": json.loads(json.dumps(ncd, default=str))}
            except Exception as exc:                                # noqa: BLE001
                out["near_constant_dims"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        rp = mod.resolve_physical_range(
            argparse.Namespace(physical_range_json=str(c2_out / "physical_range_correction" / "physical_range.json"),
                               ignore_physical_range_json=False), None, npz_path)
        out["resolve_physical_range"] = {"ok": True,
                                         "value_round6": [round(float(x), 6) for x in np.asarray(rp[0]).tolist()],
                                         "provenance": rp[2]}
    except Exception as exc:                                         # noqa: BLE001
        out["ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"
        import traceback
        out["traceback_tail"] = traceback.format_exc().splitlines()[-6:]
    t_end = time.time()
    io_after = self_io()
    sys.dont_write_bytecode = _dwb
    after = count_files(c2_out)
    diff = inventory_diff(inv_before, inventory(c2_out))
    wchar_delta = (io_after.get("wchar") - io_before.get("wchar")
                   if (io_before.get("available") and io_after.get("available")) else None)
    out["c2_out_dir_file_count"] = {"before": before, "after": after,
                                    "wrote_nothing": (before.get("n_files") == after.get("n_files")
                                                      and before.get("bytes_total") == after.get("bytes_total"))}
    out["no_write_proof"] = {
        "why_two_proofs": ("**计数不够**：C2 是并发写者，它自己的 `gate/run_*` 会在本干跑的同一秒里落文件"
                           "（实测 01:05:46 撞上 `run_20260930_010545`）⇒ 只用目录计数会把"
                           "『C2 写的』误判成『B2 写的』（同型错误本线已在 GPU 污染上犯过一次）。"),
        "proof_1_path_level_inventory_diff": diff,
        "proof_2_this_process_wchar_delta_bytes": wchar_delta,
        "proc_self_io": {"before": io_before, "after": io_after},
        "bytecode_writing_disabled_during_drycheck": True,
        "window_s": round(t_end - t_start, 3),
        "attribution": (
            "this_process_wrote_nothing_to_c2_dir" if (wchar_delta == 0 and diff["empty"]) else
            ("dir_changed_but_not_by_this_process（wchar_delta=0 ⇒ 本进程一个写系统调用都没发；"
             "变化归并发写者 C2）" if wchar_delta == 0 else
             "AMBIGUOUS_or_this_process_wrote（wchar_delta>0，必须逐条解释）")),
        "verdict": ("PASS" if (wchar_delta == 0 and diff["empty"]) else
                    ("PASS_not_written_by_this_process" if wchar_delta == 0 else "RED")),
    }
    out.setdefault("ok", out.get("load_frames", {}).get("ok", False) is True and "error" not in out)
    return out


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset-dir", default="runs/vla/b2_sim_demo_bidir_20260930/pilot",
                    help="已落地的 S1 数据集目录（含 demo_manifest.json / pi05_lerobot / sidecar）")
    ap.add_argument("--out-dir", default="runs/vla/b2_states_14d_20260930/pilot5",
                    help="导出目录（写 states_14d.npz + manifest.json；**不写进数据集本体**）")
    ap.add_argument("--provenance", default="s1_pilot_dataset_10ep_5perdir",
                    help="provenance 标签")
    ap.add_argument("--is-pilot5", default="true", choices=("true", "false"))
    ap.add_argument("--formal-collection-pending", default="true", choices=("true", "false"))
    ap.add_argument("--no-patch-demo-manifest", action="store_true",
                    help="不回写 demo_manifest.json（契约 §17-4 要求回写 npz 的 sha256-12 + as_of）")
    ap.add_argument("--skip-c2-drycheck", action="store_true")
    ap.add_argument("--command-verbatim", default=None)
    args = ap.parse_args()

    t0 = time.time()
    dataset_dir = (ROOT / args.dataset_dir) if not Path(args.dataset_dir).is_absolute() else Path(args.dataset_dir)
    out_dir = (ROOT / args.out_dir) if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / "states_14d.npz"
    man_path = out_dir / "manifest.json"

    gpu_before = nvidia_smi_snapshot("before_export")
    demo = read_demo_manifest(dataset_dir)
    frames, fmeta = read_lerobot_frames(dataset_dir, demo)
    start, smeta = read_start_poses(dataset_dir, demo, frames, fmeta["per_episode_counts"])
    c2mod, c2ident = import_c2_collector()
    pr, pr_prov = physical_ranges(c2mod, frames)
    five_tuple = build_five_tuple(demo, dataset_dir)

    # ---- 契约冲突（不静默裁决；交 D）
    errata_p = ROOT / "runs/vla/c2_norm_contract_20260929/physical_range_correction/physical_range.json"
    errata = json.loads(errata_p.read_text(encoding="utf-8")) if errata_p.exists() else None
    conflict = {
        # ---- 裁定 87.6（D 自证轮，2026-09-30 02:1x）：**已关闭**，采根因修法而不是选数 ----
        # D 的原话要点：不在 1.0 与 0.91001 之间选一个 —— 选任何一个都是把「口径相关的实测量」
        # 写进「口径无关的契约」，下一次换采集器就会再冲突一次；**根因是"契约里有实测量"，
        # 不是"哪个实测量对"**。新口径：契约文本不得硬编码任何夹爪数值；各维取值范围 =
        # **主线数据的同源实测值**（本 npz 的 `physical_range_effective`，与 `frames` 同源）；
        # `scripts/c2_collect_env_states.py` 是**诊断专用源**，其数值不得移植进主线
        # （裁定 87.7 常规则 `rule_transplantable_value_not_transplantable`：规则可搬、数值不可搬）。
        # ⇒ 契约里出现的任何具体数字（含旧文本的 "1.0"）**一律为登记项、不是判据**。
        # 下面 clause_a / clause_b / contradiction / relative_diff_pct **全部保留为历史登记**
        # （它们是 D 第 14 号同型错误 + 下属纠正 D 第 9 例的证据链；裁定 92.4：作废不删件、
        # 不改名）⇒ 只是不再作为**待裁项**。
        "status": "CLOSED_by_ruling_87_6",
        "closure": {
            "closed_by": "裁定 87.6（`work/decisions/decisions_20260929.md:2532`）",
            "closed_at_registration": now_iso(),
            "resolution": "root_cause_fix_not_number_picking（改契约文本，不在两个数里挑一个）",
            "new_caliber_text": ("夹爪维（及其它各维）的取值范围 = **主线数据的同源实测值**"
                                 "（B2 npz 的 `physical_range_effective`，与 `frames` 同源）。"
                                 "`scripts/c2_collect_env_states.py` 是**诊断专用源**，其数值"
                                 "**不得移植进主线**（§87.7）。契约里出现的任何具体数字"
                                 "（含旧文本的「1.0」）**一律为登记项、不是判据**。"),
            "effect_on_mainline": ("**0**（D 的原话：主线分母已经走 npz 的 `physical_range_effective`，"
                                   "§87.7 ⇒ 冲突对主线是惰性的）。改的只是**文本**，防止未来有人"
                                   "「照契约」把 1.0 应用上去（那会产生 9.889% 的分母错误）"),
            "what_stays_registered_not_criterion": [
                "npz 的 `physical_range` 数组（契约字面，夹爪 = 1.0）—— 保留，但**只登记不判**",
                "clause_a_d_contract_text 里的旧文本（含「夹爪维 = 1.0」）—— 历史证据",
                "relative_diff_pct（9.889%）—— 量化差值，供追溯，不是判据",
            ],
            "superseded_ruling_chain": ("裁定 82.2（契约文本，含互斥两半句）→ 裁定 87.6（改文本）"
                                        "→ 裁定 87.7（`prefer=\"npz\"`：规则可搬、数值不可搬）"),
            "accounts": ("D 的第 14 号同型错误（issued 了一份含两个互斥半句的契约文本）；"
                         "由下属发现（B2 登记 OPEN + C2 拒绝自决）⇒ 同时计入下属纠正 D 第 9 例"),
        },
        "status_history": [
            {"status": "OPEN_needs_d_ruling",
             "as_of": "裁定 87.6 之前（B2 登记、C2 不代改；两线的处置都被 D 判为正确）",
             "registered_by": "B2（本导出器 `contract_conflict.status`）",
             "also_surfaced_in": "mainline_status.json.b2_contract_conflict_status"},
            {"status": "CLOSED_by_ruling_87_6", "as_of": now_iso(),
             "changed_by": "B2（按 D→B2 §19.6-2【P1】：只改状态串与其说明，不动任何数组）"},
        ],
        "clause_a_d_contract_text": {
            "text": "`physical_range=[14]`（**臂关节读 `jnt_range`、夹爪维 = 1.0**，同 `scripts/c2_collect_env_states.py` 口径）",
            "source": "rl_harness_supervision/d_handoff_to_b2_20260929.md §17-4（裁定 82.2，C2 提、D 采纳为绑定契约）",
            "same_text_also_in": "scripts/c2_build_norm_stats.py 的 mainline_status.interface_ask_to_b2",
        },
        "clause_b_c2_collector_current": {
            "text": "夹爪维 = 手指滑动关节 jnt_range=[0.021,0.057] 经 upstream normalize_puppet_gripper_position 换算 ⇒ 行程 0.91001；docstring 明写「⚠ 旧版本这里写的是『夹爪维行程 = 1.0』」= 已勘误缺陷",
            "measured_gripper_travel": float(pr["physical_range_declared_c2_caliber"][GRIPPER_STATE_DIMS[0]]),
            "file": c2ident,
            "errata_file": ({"path": str(errata_p.relative_to(ROOT)), "sha256_12": sha12(errata_p),
                             "mtime": mtime_iso(errata_p),
                             "declared_gripper": (errata or {}).get("physical_range", [None] * 14)[6],
                             "effective_gripper": (errata or {}).get("physical_range_effective", [None] * 14)[6],
                             "supersedes": (errata or {}).get("supersedes")} if errata else None),
        },
        "contradiction": ("契约的两个半句现在互相矛盾：『夹爪维 = 1.0』与『同 c2_collect_env_states.py 口径』"
                          "不可能同时成立（该文件现行口径实测 0.91001，差 9.0%）。"),
        "relative_diff_pct": round(abs(1.0 - float(pr["physical_range_declared_c2_caliber"][6]))
                                   / float(pr["physical_range_declared_c2_caliber"][6]) * 100.0, 3),
        "what_this_exporter_did": ("**两个都写、不挑**：`physical_range` = 契约字面（夹爪 1.0，= C2 "
                                   "`resolve_physical_range()` 标注为「旧口径，已知缺陷」的那个槽位）；"
                                   "`physical_range_declared_c2_caliber` / `physical_range_effective` = C2 现行口径。"),
        "what_c2_will_actually_use": ("**裁定 87.7 之后**：C2 的 `resolve_physical_range()` 已加 "
                                      "`prefer=\"npz\"` ⇒ 主线分母走**本 npz 的 "
                                      "`physical_range_effective`**（与 `frames` 同源），"
                                      "并在产物里记 `physical_range_basis`（值由哪个源供给）。"
                                      "勘误件 `physical_range_correction/physical_range.json` 里的"
                                      "「实测行程」是 C2 从 **env 诊断档**（random/sweep/hold）量出来的，"
                                      "把它当主线帧的分母 = 裁定 71 禁止的**跨口径移植** ⇒ 不再优先。"
                                      "（本段在裁定 87.6/87.7 之前写的是「① 勘误件优先」，"
                                      "那是当时的口径，**已被 C2 自己改判**、D 追认为常规则）"),
        "why_not_silently_pick": ("B2 是判据线：口径分歧必须响亮登记（红线 caliber_transplant_ban / 裁定 71），"
                                  "静默挑一个等于把 9.0% 的行程差藏进 F1 下限族的分母。"
                                  "**这条纪律的结果是好的**：正因为 B2 登记了 OPEN、C2 拒绝自决，"
                                  "D 才发现是自己的契约文本自相矛盾（裁定 87.6 记为 D 第 14 号同型错误）。"),
    }

    # ---- 落 npz
    ep_dir_codes = np.asarray([0 if (e.get("direction") == "forward") else 1 for e in (demo.get("episodes") or [])],
                              dtype=np.int64)
    np.savez(npz_path,
             frames=np.asarray(frames, dtype=np.float64),
             start_poses=np.asarray(start, dtype=np.float64),
             physical_range=np.asarray(pr["physical_range_contract_literal"], dtype=np.float64),
             physical_range_effective=np.asarray(pr["physical_range_effective"], dtype=np.float64),
             physical_range_declared_c2_caliber=np.asarray(pr["physical_range_declared_c2_caliber"], dtype=np.float64),
             observed_travel=np.asarray(pr["observed_travel"], dtype=np.float64),
             episode_index=np.asarray(np.repeat(np.arange(len(fmeta["per_episode_counts"])),
                                                fmeta["per_episode_counts"]), dtype=np.int64),
             episode_boundaries=np.asarray(fmeta["episode_boundaries"], dtype=np.int64),
             direction_code=ep_dir_codes)

    gates = demo.get("gates") or {}
    manifest = {
        "artifact": "b2_s1_states_14d_export",
        "generated_at": now_iso(),
        "purpose": ["C2 主线 stats 的 `--s1-frames` 输入（裁定 52/69：主线 stats 与 BC 训练数据同源）"],
        "contract_source": "rl_harness_supervision/d_handoff_to_b2_20260929.md §17-4（裁定 82.2）",
        "contract_fields": {"frames": "[N,14] float64（按集拼接、集序号升序）",
                            "start_poses": "[E,14]",
                            "physical_range": ("[14]（臂关节读 jnt_range、夹爪维 = 1.0）—— "
                                               "**登记项、不是判据**（裁定 87.6：契约文本不得硬编码"
                                               "任何夹爪数值；主线分母走 `physical_range_effective`）"
                                               "；见 contract_conflict"),
                            "manifest": "五元标注 + control_hz=29.4118 + episode_horizon_s=10.2"},
        "not_for_mainline_normalizer": False,
        "tier": "mainline_candidate（数据源 = 已过 16 道闸的 S1 先导数据集本体）",
        "provenance": args.provenance,
        "is_pilot5": (args.is_pilot5 == "true"),
        "formal_collection_pending": (args.formal_collection_pending == "true"),
        "provenance_note": ("**不是** §17-5 的降阶方案（那条要求用 expert_selfverify_40x2_postpatch.json 当数据源，"
                            "但该文件实测只有标量诊断行、**没有 14 维状态轨迹** ⇒ 字面不可执行；见 "
                            "downgrade_plan_feasibility）。本件的数据源是**已落地的先导数据集本体**"
                            "（pi05_lerobot 的 observation.state），比降阶方案更强：与 BC 训练数据同源、"
                            "且已随数据集一起过了 16/16 道闸。"),
        "downgrade_plan_feasibility": {
            "ruling": "§17-5 字面不可执行",
            "evidence_file": "runs/vla/b2_sim_demo_bidir_20260930/probe/expert_selfverify_40x2_postpatch2.json",
            "evidence_sha256_12": sha12(ROOT / "runs/vla/b2_sim_demo_bidir_20260930/probe/expert_selfverify_40x2_postpatch2.json"),
            "row_keys_measured": ["direction", "seed", "verdict", "ok", "failure_class", "n_steps", "wall_s", "hz",
                                  "max_held", "box_final", "env_reward4", "max_box_speed", "max_box_speed_phase",
                                  "picker_held", "displacement_m", "on_goal_side_diag", "box_spawn",
                                  "budget_exceeded", "n_plan_nonconverged", "timeouts", "why"],
            "n_rows": 80,
            "why": "rows[*] 只有标量判据字段，没有 states/actions 序列 ⇒ 无法从它导出 frames=[N,14]",
            "what_was_done_instead": "改从已落地的先导数据集 parquet 导出（同源、更强）",
        },
        "source_dataset": {
            "dir": str(dataset_dir.relative_to(ROOT)),
            "demo_manifest": {"path": "demo_manifest.json", "sha256_12_at_read": sha12(dataset_dir / "demo_manifest.json"),
                              "mtime": mtime_iso(dataset_dir / "demo_manifest.json")},
            "stage": demo.get("stage"), "seed0": demo.get("seed0"),
            "n_episodes": len(demo.get("episodes") or []),
            "n_per_direction": demo.get("n_generated_per_direction"),
            "directions": demo.get("directions"),
            "generator": demo.get("generator"), "generator_sha256_12": demo.get("generator_sha256_12"),
            "expert_module": demo.get("expert_module"), "expert_module_sha256_12": demo.get("expert_module_sha256_12"),
            "gates_verdict": gates.get("verdict"), "gates_n_checks": gates.get("n_checks"),
            "gates_n_red": gates.get("n_red"), "gates_red_ids": gates.get("red_ids"),
            "gates_n_warn": gates.get("n_warn"), "gates_n_a": gates.get("n_a"),
            "gates_precondition": "只有 gates.verdict == PASS 且 n_red == 0 才允许把该数据集的状态导成主线 stats 输入",
            "cotenant_evidence_at_collection": (demo.get("cotenant_evidence") or {}).get("contaminated_by_cotenant"),
            "cotenant_reasons": (demo.get("cotenant_evidence") or {}).get("reasons"),
            "cotenant_scope_note": ("采集窗的 contaminated 标记**只由 loadavg_1m 摆幅驱动**（实测 "
                                    "foreign_gpu_compute_apps=[]、foreign_active_gpu_line_procs=[]）⇒ "
                                    "它约束的是**吞吐/墙钟数字**，不改变状态与图像的**内容**判据；"
                                    "详见 demo_manifest.cotenant_evidence 与本线报告。"),
        },
        "schema": {
            "frames": {"shape": list(frames.shape), "dtype": "float64",
                       "value_provenance": fmeta["source"],
                       "storage_in_source": fmeta["parquet_state_storage"],
                       "widen_lossless": True,
                       "order_rule": fmeta["order_rule"],
                       "per_episode_counts": fmeta["per_episode_counts"],
                       "episode_boundaries": fmeta["episode_boundaries"]},
            "start_poses": {"shape": list(start.shape), "dtype": "float64",
                            "value_provenance": smeta["source"], "caliber": smeta["caliber"]},
            "physical_range": {"shape": [STATE_DIM], "dtype": "float64",
                               "caliber": ("契约字面（臂 = jnt_range 宽度、夹爪 = 1.0）；"
                                           "**registered_only_not_a_criterion**（裁定 87.6）；"
                                           "见 contract_conflict")},
            "physical_range_declared_c2_caliber": {"shape": [STATE_DIM], "dtype": "float64",
                                                   "caliber": "C2 现行口径（夹爪经 upstream 归一化 = 0.91001）"},
            "physical_range_effective": {"shape": [STATE_DIM], "dtype": "float64", "caliber": pr["rule"]},
            "observed_travel": {"shape": [STATE_DIM], "dtype": "float64"},
            "extra_arrays_not_in_contract": ["episode_index", "episode_boundaries", "direction_code"],
            "extra_arrays_note": "C2 的 load_frames() 只取 frames/start_poses/physical_range ⇒ 多出的键被忽略，不影响消费",
            "state_layout": STATE_LAYOUT,
        },
        "control_hz": CONTROL_HZ_CONTRACT,
        "control_hz_exact": 500.0 / 17.0,
        "control_hz_rational": "500/17",
        "control_hz_note": ("契约要求标 29.4118；精确值是 1/0.034 = 500/17 = 29.41176470588235。"
                            "视频容器里实测写的就是 500/17（ffprobe r_frame_rate=avg_frame_rate=500/17）"
                            "⇒ team_form 与 pi05_lerobot **时间基一致**，回答 D §17-3。"),
        "episode_horizon_s": EPISODE_HORIZON_S_CONTRACT,
        "episode_horizon_steps_registered": (demo.get("frequency") or {}).get("episode_horizon_steps_registered"),
        "dt": fmeta["dt"],
        "five_tuple": five_tuple,
        "load_pair": load_pair(),
        "physical_range_provenance": pr_prov,
        "physical_range_model_xml": pr["model_xml"],
        "dims_where_observed_exceeds_declared": pr["dims_where_observed_exceeds_declared"],
        "contract_conflict": conflict,
        "frames_diagnostics": {
            "abs_max_per_dim": [round(float(x), 6) for x in np.abs(frames).max(axis=0).tolist()],
            "min_per_dim": [round(float(x), 6) for x in frames.min(axis=0).tolist()],
            "max_per_dim": [round(float(x), 6) for x in frames.max(axis=0).tolist()],
            "n_dims_exceeding_unit_interval": int((np.abs(frames).max(axis=0) > 1.0).sum()),
            "dims_exceeding_unit_interval": [int(i) for i in range(STATE_DIM)
                                             if np.abs(frames[:, i]).max() > 1.0],
            "note": ("3 个维（left_arm_j4 / right_arm_j2 / right_arm_j3）实测越出 [-1,1] ⇒ "
                     "这就是 C2 诊断档要解释的『零样本饱和』的同型现象，现在在**主线同源数据**上也测到了。"),
        },
        "near_constant_dims_analysis": near_constant_analysis(
            frames, pr, fmeta["episode_boundaries"], ep_dir_codes.tolist()),
        "video_container_fps_check": {
            "question": "D §17-3：team_form 的 mp4 容器里写的是精确 fps 还是取整 fps？",
            "answer": "精确 500/17 = 29.411764705882351（**不是**取整 30）",
            "method": "ffprobe -select_streams v:0 -show_entries stream=r_frame_rate,avg_frame_rate,nb_frames,duration",
            "measured": {"r_frame_rate": "500/17", "avg_frame_rate": "500/17",
                         "duration_s": 9.35, "nb_frames": 275,
                         "sample_file": "runs/vla/b2_sim_demo_bidir_20260930/pilot/team_form/data/train/"
                                        "transfer_cube_right_to_left/episode_a735a0d5-0e05-55b2-a01e-34ea45815cf4/top-camera.mp4"},
            "cross_check_generator_sidecar": {
                "field": "metrics.team_rule_inputs.video_container_fps",
                "n_episodes_checked": 10, "n_cameras_checked": 3,
                "all_values": 29.41176470588235,
                "note": "10 集 × 3 相机全部是精确值（B2 独立 ffprobe 与生成器记录一致）"},
            "verdict": "PASS_no_timebase_inconsistency",
            "consequence": "乙被否的原因是『mp4 + **取整** fps』；team_form 的 mp4 写的是精确有理数 ⇒ 与乙不是一回事、可保留",
        },
        "checks": (fmeta["checks"] + smeta["checks"]),
        "gpu_nonusage": {
            "claim": "本导出**没有使用 GPU**（§17-7『现在不要上卡』；优先级 A2>C2>E>B2）",
            "mujoco_gl_forced_to": _FORCED_GL,
            "mujoco_gl_before_import": _GL_BEFORE_IMPORT,
            "model_loaded_with": "mujoco.MjModel.from_xml_path（无 GL 上下文、无 Renderer）",
            "before": gpu_before, "after": None,
        },
        "exporter": {"path": "scripts/b2_export_states_14d.py",
                     "sha256_12": sha12(Path(__file__).resolve()),
                     "n_lines": len(Path(__file__).read_text(encoding="utf-8").splitlines())},
        "c2_collector_reused_readonly": c2ident,
        "command_verbatim": args.command_verbatim or " ".join(sys.argv),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "interpreter_this_process": sys.executable,
        "wall_seconds": None,
    }

    gpu_after = nvidia_smi_snapshot("after_export")
    manifest["gpu_nonusage"]["after"] = gpu_after
    manifest["gpu_nonusage"]["n_foreign_compute_apps"] = {"before": gpu_before["n_foreign_compute_apps"],
                                                          "after": gpu_after["n_foreign_compute_apps"]}
    manifest["wall_seconds"] = round(time.time() - t0, 3)

    n_red = sum(1 for c in manifest["checks"] if c["verdict"] == "RED")
    manifest["verdict"] = "PASS" if n_red == 0 else "RED"
    manifest["n_checks"] = len(manifest["checks"])
    manifest["n_red"] = n_red
    manifest["red_ids"] = [c["id"] for c in manifest["checks"] if c["verdict"] == "RED"]

    # 先落 v1（**必须**：C2 的 load_frames() 会读 npz 同目录的 manifest.json；
    # 干跑若在落盘前执行，就会拿到 man={} ⇒ 干跑证明的不是 C2 真正会看到的组合）。
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    npz_sha = sha12(npz_path)

    if not args.skip_c2_drycheck:
        manifest["c2_consumer_drycheck"] = c2_consumer_drycheck(npz_path)
        dchk = manifest["c2_consumer_drycheck"]
        nwp = dchk.get("no_write_proof") or {}
        ok = (bool(dchk.get("ok"))
              and bool((dchk.get("load_frames") or {}).get("manifest_keys_found"))
              and nwp.get("verdict") in ("PASS", "PASS_not_written_by_this_process")
              and bool((dchk.get("build_stats") or {}).get("ok")))
        manifest["checks"].append({
            "id": "X16_c2_consumer_drycheck",
            "verdict": "PASS" if ok else "RED",
            "required": ("C2 的 `load_frames()` 能直接吃本件（frames/start_poses/physical_range 三键齐、"
                         "**且同目录 manifest.json 被读到**），并且进出 C2 产物目录的文件穷举计数不变"),
            "observed": {"ok": dchk.get("ok"),
                         "manifest_keys_found_n": len((dchk.get("load_frames") or {}).get("manifest_keys_found") or []),
                         "no_write_proof_verdict": nwp.get("verdict"),
                         "this_process_wchar_delta_bytes": nwp.get("proof_2_this_process_wchar_delta_bytes"),
                         "c2_dir_inventory_diff": nwp.get("proof_1_path_level_inventory_diff"),
                         "error": dchk.get("error")},
            "note": "只读干跑：importlib 加载 C2 的模块、只调它的纯函数，不写它的任何产物"})
        manifest["n_checks"] = len(manifest["checks"])
        manifest["n_red"] = sum(1 for c in manifest["checks"] if c["verdict"] == "RED")
        manifest["red_ids"] = [c["id"] for c in manifest["checks"] if c["verdict"] == "RED"]
        manifest["verdict"] = "PASS" if manifest["n_red"] == 0 else "RED"
    manifest["npz"] = {"path": str(npz_path.relative_to(ROOT)), "sha256_12": npz_sha,
                       "bytes": int(npz_path.stat().st_size), "as_of": mtime_iso(npz_path),
                       "arrays": sorted(np.load(npz_path, allow_pickle=False).files)}
    manifest["manifest_json"] = {"path": str(man_path.relative_to(ROOT)), "as_of": mtime_iso(man_path)}
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    patch = None
    if not args.no_patch_demo_manifest:
        patch = patch_demo_manifest(dataset_dir, npz_path, man_path, manifest)

    print(json.dumps({
        "verdict": manifest["verdict"], "n_checks": manifest["n_checks"], "n_red": manifest["n_red"],
        "red_ids": manifest["red_ids"],
        "npz": manifest["npz"], "n_frames": int(frames.shape[0]), "n_episodes": int(start.shape[0]),
        "physical_range_contract_literal": [round(float(x), 6) for x in pr["physical_range_contract_literal"]],
        "physical_range_declared_c2": [round(float(x), 6) for x in pr["physical_range_declared_c2_caliber"]],
        "contract_conflict": conflict["status"],
        "c2_drycheck_ok": (manifest.get("c2_consumer_drycheck") or {}).get("ok"),
        "gpu_foreign_apps": manifest["gpu_nonusage"]["n_foreign_compute_apps"],
        "demo_manifest_patch": patch,
        "wall_s": manifest["wall_seconds"],
    }, ensure_ascii=False, indent=2))
    return 0 if manifest["verdict"] == "PASS" else 1


def patch_demo_manifest(dataset_dir: Path, npz_path: Path, man_path: Path, manifest: dict) -> dict:
    """契约 §17-4：在 `demo_manifest.json` 里记 npz 的 sha256-12 + `as_of` mtime。

    这是**对已落地产物的追加写**，所以进出都留证：前/后 sha256-12、前/后 mtime、加了哪些键、
    以及"数据集本体（pi05_lerobot / team_form / sidecar）一个字节都没动"的穷举计数。
    """
    p = dataset_dir / "demo_manifest.json"
    before_sha, before_mtime, before_bytes = sha12(p), mtime_iso(p), p.stat().st_size
    body_roots = ["pi05_lerobot", "team_form", "sidecar"]
    before_counts = {r: count_files(dataset_dir / r) for r in body_roots}
    d = json.loads(p.read_text(encoding="utf-8"))
    key = "states_14d_npz"
    keys_added = [] if key in d else [key]
    d[key] = {
        "npz_path": str(npz_path),
        "npz_relative": str(npz_path.relative_to(ROOT)),
        "sha256_12": manifest["npz"]["sha256_12"],
        "bytes": manifest["npz"]["bytes"],
        "as_of": manifest["npz"]["as_of"],
        "manifest_path": str(man_path.relative_to(ROOT)),
        "n_frames": int(manifest["schema"]["frames"]["shape"][0]),
        "n_episodes": int(manifest["schema"]["start_poses"]["shape"][0]),
        "arrays": manifest["npz"]["arrays"],
        "exported_by": manifest["exporter"],
        "exported_at": manifest["generated_at"],
        "provenance": manifest["provenance"],
        "is_pilot5": manifest["is_pilot5"],
        "formal_collection_pending": manifest["formal_collection_pending"],
        "contract_conflict_status": manifest["contract_conflict"]["status"],
        "c2_consumer": "scripts/c2_build_norm_stats.py --s1-frames <npz>（不需改 C2 代码；已只读干跑验证）",
        "command_verbatim": manifest["command_verbatim"],
        "dataset_body_untouched": {"checked_roots": body_roots, "before": before_counts, "after": None},
        "demo_manifest_patch": {"before_sha256_12": before_sha, "before_mtime": before_mtime,
                                "before_bytes": before_bytes, "keys_added": keys_added,
                                "after_sha256_12": None, "after_mtime": None},
    }
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    after_counts = {r: count_files(dataset_dir / r) for r in body_roots}
    d[key]["dataset_body_untouched"]["after"] = after_counts
    d[key]["dataset_body_untouched"]["unchanged"] = all(
        before_counts[r].get("n_files") == after_counts[r].get("n_files") and
        before_counts[r].get("bytes_total") == after_counts[r].get("bytes_total") for r in body_roots)
    d[key]["demo_manifest_patch"]["after_sha256_12"] = sha12(p)
    d[key]["demo_manifest_patch"]["after_mtime"] = mtime_iso(p)
    d[key]["demo_manifest_patch"]["after_bytes"] = p.stat().st_size
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    res = d[key]["demo_manifest_patch"]
    res["dataset_body_unchanged"] = d[key]["dataset_body_untouched"]["unchanged"]
    res["final_sha256_12"] = sha12(p)
    res["final_mtime"] = mtime_iso(p)
    return res


if __name__ == "__main__":
    sys.exit(main())
