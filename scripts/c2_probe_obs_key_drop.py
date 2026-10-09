#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · T-C2-2 只读证伪探针：π₀.₅ 形态观测的图像键是否被参考 learner 静默丢弃。

任务出处
  * 裁定 49.2 要求 1「先出只读复现探针，用真 π₀.₅ 形态 obs 证明图像键确实被静默丢弃（先证伪再修）」
    —— `rl_harness_supervision/d_handoff_to_c2_20260929.md:178`–`:187`
  * 阻塞台账 B3（卡 S4 / S6）—— `rl_harness_supervision/d_simchain_e2emin_20260929.md:203`
  * 缺口原文「x_ref → 表征重算（现在只重算 flat 状态向量，没有任何视觉表征）」
    —— `docs/ledger_data_bridge_20260928.md:210`；该模块不在冻结面 —— 同文 `:213`、`:436`

被探对象（**只读**，本脚本不改任何仓库文件）
  * `harness/queue_td_learner.py` 的 `_obs_vector`（键过滤 + 宽度检查）
  * `harness/obs_store.py` 的 `ObsStore.put/get/canonical_bytes`

obs 形态出处（**不自行命名**，避免与 A2 分叉；裁定 46.4 / §5.3 口径搬运禁令）
  * `scripts/a2_pi05_contract_probe.py:91`–`:105`（cam_map、transpose、/255.0、get_qpos 14 维）
  * `runs/vla/a2_pi05_contract_20260929/contract.json` → `observation.camera_map.*`、
    `observation.image_shape.*`、`observation.image_dtype`、`observation.state_raw_14d`
  * `gym_aloha/env.py:143`–`:148`（`pixels_agent_pos` 的真实返回是 **嵌套** dict：
    `{"pixels": {"top": ...}, "agent_pos": qpos}`，且只含 `top` 一路相机）

判别方法（不靠读源码下结论，靠**逐键敏感度实测**）
  对每个已存键 k：构造「只有 k 的内容不同、其余逐字节相同」的另一条快照，
  比较 `_obs_vector` 输出的 sha256。输出不变 ⇒ k **未被消费**（静默丢弃）。
  这样"哪些键被丢"是测出来的，不是从 `:133` 的字面量推出来的。

自证（探针自己有牙，两条方向都要）
  * 正向对照：扰动 `state` **必须**改变输出（否则探针测不出"被消费"，判 PROBE_INVALID）。
  * 宽度检查活性对照：把 `state_dim` 配错 **必须** 触发 `LearnerRefused`
    （否则"图像被静默忽略"可能只是"所有检查都死了"，结论不成立）。
  * 只读对照：跑前跑后对被探文件做 sha256-12 对比，不一致 ⇒ PROBE_INVALID。
  * 变异臂 M1（进程内替换成"白名单+全覆盖断言"的参照实现）⇒ 判定必须翻面为
    DEFECT_NOT_REPRODUCED；M2（只额外消费 base_0_rgb）⇒ 必须为 DEFECT_PARTIAL。
    两臂都**不落任何仓库文件改动**，用来证明本探针不是恒真判据。

纪律
  * ObsStore 落在本探针自己的输出目录，**不写** C 的默认库 `runs/infra/c_obs_store/`。
  * 计数类主张同批带 (mtime, 行数/键数, 代码位置)（裁定 51.2）；"不存在"类主张先枚举全集（裁定 50.1）。
  * 数值主张同批带 loadavg + nr_throttled；并行度分母 = 12 核 cgroup 配额，不是 `nproc`。
  * 状态词只用 v4 五档（未实施 / 已实现未验证 / 回放通过 / 仿真通过 / 真机通过）；
    产物里不出现「跑通 / 学会 / 达标」。
  * 体积口径显式标注：本探针实测的是 `np.savez` **未压缩**载荷，与 C 线「147 KB/帧」
    的 **PNG 压缩推算**口径不同，**两者不可直接相减比较**（只各自记录，不混算）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness import queue_td_learner as qtl            # noqa: E402
from harness.obs_store import ObsStore                 # noqa: E402
from harness.queue_td_learner import LearnerConfig, LearnerRefused  # noqa: E402

CST = timezone(timedelta(hours=8))

PROBE_ID = "c2_probe_obs_key_drop"
TASK_ID = "T-C2-2"
REPR_VERSION = "c2-probe-pi05shape-v1"
CONTRACT_VERSION = "v4-appendix01-2.3"

STATE_DIM = 14
STATE_KEYS = ("state", "environment_state")

# A2 实测的 π₀.₅ 策略层键名（contract.json → observation.camera_map）
POLICY_IMAGE_KEYS = (
    "observation.images.base_0_rgb",
    "observation.images.left_wrist_0_rgb",
    "observation.images.right_wrist_0_rgb",
)
# S4 指派的相机键注入名（d_simchain_e2emin_20260929.md:143）
ENV_CAMERA_KEYS = ("top", "left_wrist", "right_wrist")

# A2 实测的起始位姿（contract.json → observation.state_raw_14d）：dim 2 / dim 9 = 1.16，
# 即「原始 2/14 维越界」的那两维。用真值，不用随机数，免得和 S2 的起态覆盖闸对不上。
START_STATE_14D = (
    0.0, -0.96, 1.16, 0.0, -0.3, 0.0, 0.099848,
    0.0, -0.96, 1.16, 0.0, -0.3, 0.0, 0.099848,
)

POLICY_IMAGE_SHAPE = (3, 224, 224)     # contract.json → observation.image_shape.*
ENV_IMAGE_SHAPE = (480, 640, 3)        # gym_aloha observation_height/width, uint8

VERDICTS = ("DEFECT_REPRODUCED", "DEFECT_PARTIAL", "DEFECT_NOT_REPRODUCED", "PROBE_INVALID")

# ---------------------------------------------------------------- 基础工具


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:12]


def array_sha12(arr: np.ndarray) -> str:
    a = np.ascontiguousarray(arr)
    return sha12(a.tobytes() + f"|{a.dtype}|{a.shape}".encode("utf-8"))


def fingerprint(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    raw = p.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    st = p.stat()
    return {
        "path": str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else str(p),
        "exists": True,
        "sha256_12": sha12(raw),
        "n_bytes": len(raw),
        "n_lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "mtime": datetime.fromtimestamp(st.st_mtime, CST).isoformat(timespec="seconds"),
    }


def locate_lines(path: Path, needle: str) -> list[int]:
    """在源码里定位字面量所在行号（1-based）。主张必须留 file:line ⇒ 运行时定位，不靠记忆。"""
    hits = []
    for idx, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            hits.append(idx)
    return hits


def read_loadavg() -> dict:
    parts = Path("/proc/loadavg").read_text().split()
    return {"loadavg_1m": float(parts[0]), "loadavg_5m": float(parts[1]),
            "loadavg_15m": float(parts[2]), "nr_running_nth": parts[3]}


def read_cpu_stat() -> dict:
    out = {}
    p = Path("/sys/fs/cgroup/cpu/cpu.stat")
    if p.exists():
        for line in p.read_text().splitlines():
            k, _, v = line.partition(" ")
            out[k] = int(v)
    return out


def machine_block() -> dict:
    quota = None
    q = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    per = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if q.exists() and per.exists():
        qv, pv = int(q.read_text().strip()), int(per.read_text().strip())
        quota = {"cfs_quota_us": qv, "cfs_period_us": pv,
                 "cores_quota": round(qv / pv, 3) if pv else None}
    return {"ts": now_iso(), "loadavg": read_loadavg(), "cpu_stat": read_cpu_stat(),
            "cgroup_quota": quota,
            "nproc_host_not_the_denominator": __import__("os").cpu_count(),
            "parallelism_denominator": "12-core cgroup quota (裁定 46.4 / §5.3)"}


# ---------------------------------------------------------------- obs 形态构造


def make_state(rng=None) -> np.ndarray:
    return np.asarray(START_STATE_14D, dtype=np.float32)


def make_policy_images(seed: int) -> dict[str, np.ndarray]:
    """按 A2 的口径造策略层三路图像：(3,224,224) float32 ∈ [0,1]。"""
    rng = np.random.default_rng(seed)
    return {k: rng.random(POLICY_IMAGE_SHAPE, dtype=np.float32) for k in POLICY_IMAGE_KEYS}


def make_env_images(seed: int) -> dict[str, np.ndarray]:
    """按 gym-aloha 的原始口径造三路相机：(480,640,3) uint8。"""
    rng = np.random.default_rng(seed)
    return {k: rng.integers(0, 256, size=ENV_IMAGE_SHAPE, dtype=np.uint8) for k in ENV_CAMERA_KEYS}


def perturb(key: str, arr: np.ndarray, seed: int) -> np.ndarray:
    """同 shape / 同 dtype、内容确定性地不同。整数用模加，浮点用整体替换。"""
    rng = np.random.default_rng(seed)
    if np.issubdtype(arr.dtype, np.integer):
        return ((arr.astype(np.int64) + 37) % 256).astype(arr.dtype)
    return rng.random(arr.shape).astype(arr.dtype)


def build_variants() -> dict[str, dict]:
    """返回 {变体名: {"obs": {...}, "role": str, "provenance": str, "carries_images": bool}}"""
    state = make_state()
    v = {}
    v["act_legacy_state_only"] = {
        "obs": {"state": state.copy()},
        "role": "反向对照：ACT 线旧快照形态（只有 state）——按裁定 49.2 要求 2，修复后**仍须绿**",
        "provenance": "harness/queue_td_learner.py:133-134 消费键集合；C 线表征 lift-state-proprio50+obj10-v1",
        "carries_images": False,
    }
    v["pi05_policy_layer"] = {
        "obs": {"state": state.copy(), **make_policy_images(20260929)},
        "role": "真 π₀.₅ 形态（策略层键名，3×[3,224,224] float32）",
        "provenance": "scripts/a2_pi05_contract_probe.py:91-105; contract.json → observation.image_shape/camera_map",
        "carries_images": True,
    }
    v["pi05_policy_layer_altimg"] = {
        "obs": {"state": state.copy(), **make_policy_images(777001)},
        "role": "与 pi05_policy_layer **state 逐字节相同、图像内容完全不同** ⇒ 用于测图像是否影响输出",
        "provenance": "同上；图像换成另一 seed",
        "carries_images": True,
    }
    v["pi05_env_camera_names"] = {
        "obs": {"state": state.copy(), **make_env_images(20260929)},
        "role": "真 π₀.₅ 三路相机但用 S4 指派的 env 侧键名（top/left_wrist/right_wrist, 480×640×3 uint8）",
        "provenance": "d_simchain_e2emin_20260929.md:143（相机键注入）; gym_aloha/env.py:69-75 分辨率与 dtype",
        "carries_images": True,
    }
    v["pi05_env_camera_names_altimg"] = {
        "obs": {"state": state.copy(), **make_env_images(777002)},
        "role": "与 pi05_env_camera_names state 相同、图像不同",
        "provenance": "同上；图像换成另一 seed",
        "carries_images": True,
    }
    v["raw_env_agent_pos_naming"] = {
        "obs": {"agent_pos": state.copy(), "top": make_env_images(555003)["top"]},
        "role": "gym-aloha 原生键名（agent_pos 而非 state）⇒ 检验失败模式是**静默**还是**响亮**",
        "provenance": "gym_aloha/env.py:143-148（pixels_agent_pos 的 agent_pos 键）",
        "carries_images": True,
    }
    return v


NESTED_VARIANT = {
    "name": "raw_env_nested_pixels_agent_pos",
    "obs": {"pixels": {"top": np.zeros((8, 8, 3), dtype=np.uint8)},
            "agent_pos": make_state()},
    "role": "gym-aloha `pixels_agent_pos` 的**原样返回**（嵌套 dict）⇒ 检验 ObsStore 能否内容寻址",
    "provenance": "gym_aloha/env.py:143-148 _format_raw_obs 原文",
}


# ---------------------------------------------------------------- 三种 obs_vector 实现


def obs_vector_repo(store, x_ref, cfg, *, kind):
    """主臂：仓库里那个**未被修改**的实现本体。"""
    return qtl._obs_vector(store, x_ref, cfg, kind=kind)


def obs_vector_fixed_whitelist(store, x_ref, cfg, *, kind):
    """变异臂 M1：白名单 + 全覆盖断言的最小参照实现（进程内替换，**不落仓库文件**）。

    若将来真按裁定 49.2 修好，本探针的判定必须翻面 ⇒ 这是探针的**判别力**证据。
    """
    try:
        obs = store.get(x_ref)
    except KeyError as exc:
        raise LearnerRefused(f"{kind}: x_ref={x_ref!r} 在 ObsStore 里找不到") from exc
    consumed = [k for k in STATE_KEYS if k in obs]
    dropped = sorted(set(obs) - set(consumed))
    if dropped:
        raise LearnerRefused(
            f"{kind}: 快照 {x_ref!r} 存入 {len(obs)} 个键、只消费 {len(consumed)} 个；"
            f"被静默丢弃的键={dropped}")
    parts = [np.asarray(obs[k], dtype=np.float32).reshape(-1) for k in consumed]
    if not parts:
        raise LearnerRefused(f"{kind}: 快照 {x_ref!r} 里没有 state / environment_state")
    vec = np.concatenate(parts)
    if vec.shape[0] != cfg.state_dim:
        raise LearnerRefused(f"{kind}: 观测维度 {vec.shape[0]} != 配置 state_dim {cfg.state_dim}")
    return vec


def obs_vector_consume_base0(store, x_ref, cfg, *, kind):
    """变异臂 M2：只额外消费 `observation.images.base_0_rgb`，其余图像键仍静默丢弃。

    用来证明逐键敏感度测试**不是写死的**：它必须只把 base_0_rgb 判成"被消费"。
    注意：M2 是**判别力桩**，不是修复方案（它故意绕过宽度检查）。
    """
    vec = qtl._obs_vector(store, x_ref, cfg, kind=kind)
    obs = store.get(x_ref)
    key = POLICY_IMAGE_KEYS[0]
    if key in obs:
        extra = np.asarray([float(np.asarray(obs[key], dtype=np.float64).mean())], dtype=np.float32)
        vec = np.concatenate([vec, extra])
    return vec


ARMS = {
    "main": {"fn": obs_vector_repo,
             "expected_verdict": "DEFECT_REPRODUCED",
             "modifies_repo_files": False,
             "note": "被探对象 = 仓库现有实现本体（只读）"},
    "mut_fixed_whitelist": {"fn": obs_vector_fixed_whitelist,
                            "expected_verdict": "DEFECT_NOT_REPRODUCED",
                            "modifies_repo_files": False,
                            "note": "M1：进程内替换为白名单+全覆盖断言 ⇒ 判定必须翻面"},
    "mut_consume_base0": {"fn": obs_vector_consume_base0,
                          "expected_verdict": "DEFECT_PARTIAL",
                          "modifies_repo_files": False,
                          "note": "M2：只额外消费 base_0_rgb ⇒ 必须报 PARTIAL（逐键测试非写死）"},
}


# ---------------------------------------------------------------- 探针主体


def classify_refusal(msg: str, keys_stored) -> dict:
    """分类拒绝原因，并**精确**取出被点名的键。

    不用"键名是否是消息子串"来判点名 —— 消息里也会列出**存入键集合**（含 `state`），
    子串匹配会让"点名了被丢弃的键"这条检查**意外为真**（这正是 T-C2-4 要抓的假绿形态）。
    改为解析 `被静默丢弃的键=[...]` / `缺席的键=[...]` 两个片段；解析不到才退回子串法并标注。
    """
    import re

    def _parse(label: str) -> list[str]:
        m = re.search(re.escape(label) + r"=\[(.*?)\]", msg)
        if not m:
            return []
        return [x.strip().strip("\'\"") for x in m.group(1).split(",") if x.strip()]

    dropped = _parse("被静默丢弃的键")
    missing = _parse("契约声明为必需但快照缺席的键")
    if dropped or missing:
        named, method = sorted(set(dropped) | set(missing)), "regex_on_named_segment"
    else:
        named, method = [k for k in keys_stored if k and k in msg], "substring_fallback"
    if "里没有 state" in msg:
        kind = "missing_state_key_loud"
    elif dropped:
        kind = "coverage_names_dropped_keys"
    elif missing:
        kind = "coverage_names_missing_keys"
    elif "观测维度" in msg:
        kind = "width_mismatch"
    else:
        kind = "other"
    return {"refusal_kind": kind, "keys_named_in_refusal": named,
            "keys_named_dropped": dropped, "keys_named_missing": missing,
            "naming_parse_method": method, "message": msg}


def probe_variant(store: ObsStore, name: str, spec: dict, cfg: LearnerConfig,
                  obs_vector_fn, clock: list[int], *, run_sensitivity: bool) -> dict:
    obs = spec["obs"]
    clock[0] += 1
    meta = store.put(obs, sampled_at_ns=clock[0], representation_version=REPR_VERSION,
                     episode_id=f"c2-probe-{name}", abs_frame=0,
                     contract_version=CONTRACT_VERSION)
    keys_stored = list(meta.keys)
    roundtrip = store.get(meta.obs_ref)
    out = {
        "variant": name,
        "role": spec["role"],
        "provenance": spec["provenance"],
        "carries_images": bool(spec.get("carries_images")),
        "obs_ref": meta.obs_ref,
        "obs_ref_sha12": meta.obs_ref[:12],
        "payload_nbytes": int(meta.nbytes),
        "payload_KB_uncompressed_npz": round(int(meta.nbytes) / 1024.0, 2),
        "keys_stored": keys_stored,
        "n_keys_stored": len(keys_stored),
        "keys_roundtrip_identical": sorted(roundtrip) == sorted(keys_stored),
        "shapes_stored": {k: list(np.asarray(v).shape) for k, v in obs.items()},
        "dtypes_stored": {k: str(np.asarray(v).dtype) for k, v in obs.items()},
        "n_values_stored": int(sum(int(np.prod(np.asarray(v).shape)) for v in obs.values())),
    }

    try:
        vec = obs_vector_fn(store, meta.obs_ref, cfg, kind=name)
        refused = None
    except LearnerRefused as exc:
        vec, refused = None, classify_refusal(str(exc), keys_stored)

    if refused is not None:
        out.update({
            "call_outcome": "LearnerRefused",
            "refusal": refused,
            "vec_shape": None,
            "n_values_consumed": 0,
            "keys_consumed": [],
            "keys_unconsumed_silently": keys_stored,
            "n_keys_unconsumed_silently": len(keys_stored),
            "sensitivity_run": False,
            "silent_drop": False,
            "loud_refusal": True,
        })
        return out

    base_sha = array_sha12(vec)
    consumed, unconsumed, per_key = [], [], {}
    if run_sensitivity:
        for key in keys_stored:
            # 扰动 seed 用 key 的稳定 sha，不用内置 hash()（PYTHONHASHSEED 会变 ⇒ 产物不可复现）
            stable_seed = 900000 + int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:6], 16) % 9999
            pobs = {k: (perturb(k, np.asarray(v), stable_seed)
                        if k == key else np.asarray(v).copy())
                    for k, v in obs.items()}
            clock[0] += 1
            pmeta = store.put(pobs, sampled_at_ns=clock[0], representation_version=REPR_VERSION,
                              episode_id=f"c2-probe-{name}-perturb-{key}", abs_frame=0,
                              contract_version=CONTRACT_VERSION)
            try:
                pvec = obs_vector_fn(store, pmeta.obs_ref, cfg, kind=f"{name}#perturb({key})")
                p_sha, p_refused = array_sha12(pvec), None
            except LearnerRefused as exc:
                p_sha, p_refused = None, str(exc)
            changed = (p_sha != base_sha) or (p_refused is not None)
            per_key[key] = {"perturbed_obs_ref_sha12": pmeta.obs_ref[:12],
                            "output_sha12_before": base_sha, "output_sha12_after": p_sha,
                            "output_changed": bool(changed),
                            "perturbation_refused": p_refused}
            (consumed if changed else unconsumed).append(key)
    else:
        consumed = [k for k in keys_stored if k in STATE_KEYS]
        unconsumed = [k for k in keys_stored if k not in STATE_KEYS]

    out.update({
        "call_outcome": "returned_vector",
        "vec_shape": list(vec.shape),
        "vec_sha12": base_sha,
        "n_values_consumed": int(vec.size),
        "keys_consumed": sorted(consumed),
        "n_keys_consumed": len(consumed),
        "keys_unconsumed_silently": sorted(unconsumed),
        "n_keys_unconsumed_silently": len(unconsumed),
        "per_key_sensitivity": per_key,
        "sensitivity_run": bool(run_sensitivity),
        "silent_drop": bool(len(unconsumed) > 0),
        "loud_refusal": False,
        "dropped_value_ratio": round(1.0 - int(vec.size) / max(1, out["n_values_stored"]), 8),
    })
    return out


def compute_verdict(results: dict[str, dict]) -> tuple[str, list[str]]:
    reasons = []
    img = {k: v for k, v in results.items() if v.get("carries_images")}
    if not img:
        return "PROBE_INVALID", ["没有任何带图像键的变体"]
    silent, loud_named, partial = [], [], []
    for name, r in img.items():
        if r["call_outcome"] == "returned_vector":
            dropped_imgs = [k for k in r["keys_unconsumed_silently"] if k not in STATE_KEYS]
            consumed_imgs = [k for k in r["keys_consumed"] if k not in STATE_KEYS]
            if dropped_imgs and consumed_imgs:
                partial.append(name)
            elif dropped_imgs:
                silent.append(name)
            else:
                reasons.append(f"{name}: 图像键全部被消费")
        else:
            if r["refusal"]["refusal_kind"] == "coverage_names_dropped_keys":
                loud_named.append(name)
            else:
                reasons.append(f"{name}: 响亮拒绝（{r['refusal']['refusal_kind']}），非静默丢弃")
    if silent and not loud_named and not partial:
        return "DEFECT_REPRODUCED", reasons + [f"静默丢弃图像的变体={sorted(silent)}"]
    if loud_named and not silent and not partial:
        return "DEFECT_NOT_REPRODUCED", reasons + [f"全部点名拒绝={sorted(loud_named)}"]
    return "DEFECT_PARTIAL", reasons + [
        f"静默={sorted(silent)}", f"点名拒绝={sorted(loud_named)}", f"部分消费={sorted(partial)}"]


def run_arm(arm: str, out_root: Path, *, run_sensitivity: bool, cfg_state_dim: int) -> dict:
    spec = ARMS[arm]
    fn = spec["fn"]
    store_root = out_root / f"obs_store_{arm}"
    store = ObsStore(root=store_root, contract_version=CONTRACT_VERSION)
    cfg = LearnerConfig(state_dim=cfg_state_dim, action_dim=14, n=2, gamma=0.99)
    clock = [1_700_000_000_000_000_000]

    before = machine_block()
    results = {}
    variants = build_variants()
    for name, vspec in variants.items():
        want_sens = run_sensitivity and name in ("act_legacy_state_only", "pi05_policy_layer",
                                                 "pi05_env_camera_names",
                                                 "raw_env_agent_pos_naming")
        results[name] = probe_variant(store, name, vspec, cfg, fn, clock,
                                      run_sensitivity=want_sens)

    # ---- 嵌套原样 obs：ObsStore 能否内容寻址（跨 T-C2-3 / S4 的发现）
    nested = {"name": NESTED_VARIANT["name"], "role": NESTED_VARIANT["role"],
              "provenance": NESTED_VARIANT["provenance"]}
    try:
        clock[0] += 1
        nm = store.put(NESTED_VARIANT["obs"], sampled_at_ns=clock[0],
                       representation_version=REPR_VERSION, episode_id="c2-probe-nested",
                       abs_frame=0, contract_version=CONTRACT_VERSION)
        nested.update({"outcome": "stored", "obs_ref_sha12": nm.obs_ref[:12],
                       "keys_stored": list(nm.keys)})
    except Exception as exc:                                   # noqa: BLE001 - 记录真实失败模式
        nested.update({"outcome": "raised", "exception_type": type(exc).__name__,
                       "message": str(exc)})
    after = machine_block()

    verdict, reasons = compute_verdict(results)

    # ---- 对照 1：正向对照（state 必须被测成"被消费"）
    # 不钉死在某个变体上：修复后带图像的变体会**先被拒绝**、跑不到逐键敏感度，
    # 此时正向对照必须从仍然返回向量的变体（如 ACT 线旧快照形态）取证据。
    sens_hits = []
    for vname, vres in results.items():
        hit = vres.get("per_key_sensitivity", {}).get("state")
        if hit:
            sens_hits.append({"variant": vname, "output_changed": bool(hit.get("output_changed")),
                              "evidence": hit})
    positive_control = {
        "claim": "扰动 state 必须改变 _obs_vector 输出（否则探针测不出'被消费'）",
        "state_key_detected_as_consumed": any(h["output_changed"] for h in sens_hits),
        "n_variants_with_state_sensitivity": len(sens_hits),
        "evidence": sens_hits,
    }
    # ---- 对照 2：宽度检查活性（配错 state_dim 必须响亮拒绝）
    bad_cfg = LearnerConfig(state_dim=cfg_state_dim - 1, action_dim=14, n=2, gamma=0.99)
    # 复用已存的 act_legacy_state_only 快照：ObsStore 是内容寻址的，
    # 再 put 一次同内容会触发 StaleObservation（这本身是 obs_store 的既有纪律，不是缺陷）。
    legacy_ref = results["act_legacy_state_only"]["obs_ref"]
    try:
        fn(store, legacy_ref, bad_cfg, kind="width_control")
        width_control = {"claim": "state_dim 配错必须触发 LearnerRefused",
                         "raised": False, "message": None, "obs_ref_sha12": legacy_ref[:12]}
    except LearnerRefused as exc:
        width_control = {"claim": "state_dim 配错必须触发 LearnerRefused",
                         "raised": True, "message": str(exc), "obs_ref_sha12": legacy_ref[:12]}

    controls_ok = True
    if run_sensitivity and not positive_control["state_key_detected_as_consumed"]:
        controls_ok = False
        verdict, reasons = "PROBE_INVALID", reasons + ["正向对照失败：state 未被测成消费键"]
    if not width_control["raised"]:
        controls_ok = False
        verdict, reasons = "PROBE_INVALID", reasons + ["宽度检查失活：配错 state_dim 未拒绝"]

    return {
        "probe_id": PROBE_ID, "task_id": TASK_ID, "arm": arm,
        "arm_spec": {k: v for k, v in spec.items() if k != "fn"},
        "generated_at": now_iso(),
        "verdict": verdict, "verdict_reasons": reasons,
        "expected_verdict_for_selftest": spec["expected_verdict"],
        "controls": {"positive_control_state_consumed": positive_control,
                     "width_check_liveness": width_control,
                     "all_controls_ok": controls_ok},
        "learner_config": {"state_dim": cfg.state_dim, "action_dim": cfg.action_dim,
                           "n": cfg.n, "gamma": cfg.gamma, "goals": list(cfg.goals)},
        "representation_version": REPR_VERSION,
        "obs_store_root": str(store_root.relative_to(REPO_ROOT)),
        "obs_store_isolated_from_c_default_root": True,
        "variants": results,
        "nested_raw_obs_result": nested,
        "machine_before": before, "machine_after": after,
        "nr_throttled_delta": (after["cpu_stat"].get("nr_throttled", 0)
                                - before["cpu_stat"].get("nr_throttled", 0)),
    }


def provenance_block() -> dict:
    qtl_path = REPO_ROOT / "harness" / "queue_td_learner.py"
    obs_path = REPO_ROOT / "harness" / "obs_store.py"
    return {
        "probe_script": fingerprint(Path(__file__).resolve()),   # 产物必须能追到探针自身的版本
        "probed_files": [fingerprint(qtl_path), fingerprint(obs_path)],
        "code_locations_runtime_located": {
            "key_filter_literal_('state', 'environment_state')":
                {"file": "harness/queue_td_learner.py",
                 "lines": locate_lines(qtl_path, '("state", "environment_state")')},
            "def _obs_vector": {"file": "harness/queue_td_learner.py",
                                "lines": locate_lines(qtl_path, "def _obs_vector")},
            "width_check_state_dim": {"file": "harness/queue_td_learner.py",
                                      "lines": locate_lines(qtl_path, "!= cfg.state_dim")},
            "no_state_key_refusal": {"file": "harness/queue_td_learner.py",
                                     "lines": locate_lines(qtl_path, "里没有 state")},
            "canonical_bytes_object_array_guard": {"file": "harness/obs_store.py",
                                                   "lines": locate_lines(obs_path, "object 数组")},
        },
        "spec_citations": [
            "rl_harness_supervision/d_handoff_to_c2_20260929.md:178-187（裁定 49.2 四条要求）",
            "rl_harness_supervision/d_simchain_e2emin_20260929.md:203（阻塞台账 B3）",
            "rl_harness_supervision/d_simchain_e2emin_20260929.md:143（S4 相机键注入 top/left_wrist/right_wrist）",
            "docs/ledger_data_bridge_20260928.md:210（视觉表征缺口原文）",
            "docs/ledger_data_bridge_20260928.md:213 / :436（queue_td_learner 不在冻结面）",
            "scripts/a2_pi05_contract_probe.py:91-105（obs 构造口径来源）",
            "runs/vla/a2_pi05_contract_20260929/contract.json → observation.camera_map / image_shape / state_raw_14d",
        ],
        "env": {"venv_python": sys.executable, "python": platform.python_version(),
                "numpy": np.__version__, "platform": platform.platform(),
                "torch": getattr(__import__("torch"), "__version__", None)},
        "size_caveat": ("payload_KB 是 np.savez **未压缩**载荷；C 线「147 KB/帧」是 PNG 压缩**推算**，"
                        "口径不同，两者不可直接比较（裁定 46.4 / §5.3 口径搬运禁令）"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="C2 · T-C2-2 只读证伪探针")
    ap.add_argument("--out", default="runs/vla/c2_obs_key_whitelist_20260929/probe_20260929")
    ap.add_argument("--arm", default="main", choices=sorted(ARMS) + ["all"])
    ap.add_argument("--state-dim", type=int, default=STATE_DIM)
    ap.add_argument("--no-sensitivity", action="store_true",
                    help="跳过逐键敏感度（只在需要省体积时用；会削弱证据）")
    ap.add_argument("--selftest", action="store_true",
                    help="跑三臂并断言各自 expected_verdict；不符 ⇒ exit 2（探针自己有牙）")
    ap.add_argument("--expect", action="append", default=[], metavar="ARM=VERDICT",
                    help="覆盖某臂的期望判定（修复后应写 --expect main=DEFECT_NOT_REPRODUCED）。"
                         "覆盖值会在产物里标 expectation_source=cli_override，不与默认值混同。")
    args = ap.parse_args()

    expectations = {arm: ARMS[arm]["expected_verdict"] for arm in ARMS}
    expect_source = {arm: "default_in_script" for arm in ARMS}
    for item in args.expect:
        arm, _, want = item.partition("=")
        if arm not in ARMS:
            ap.error(f"--expect 的臂名 {arm!r} 不存在，可选 {sorted(ARMS)}")
        if want not in VERDICTS:
            ap.error(f"--expect 的判定 {want!r} 不在词表 {list(VERDICTS)}")
        expectations[arm] = want
        expect_source[arm] = "cli_override"

    out_root = (REPO_ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    prov = provenance_block()
    fp_before = {f["path"]: f["sha256_12"] for f in prov["probed_files"]}

    arms = sorted(ARMS) if args.arm == "all" or args.selftest else [args.arm]
    # 主臂才跑全量逐键敏感度；变异臂只为判别力，控制体积
    reports = {}
    for arm in arms:
        sens = (not args.no_sensitivity) and (
            arm == "main" or (arm == "mut_consume_base0"))
        rep = run_arm(arm, out_root, run_sensitivity=sens, cfg_state_dim=args.state_dim)
        rep["provenance"] = prov
        rep["expected_verdict_for_selftest"] = expectations[arm]
        rep["expectation_source"] = expect_source[arm]
        path = out_root / f"probe_{arm}.json"
        path.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        reports[arm] = {"path": str(path.relative_to(REPO_ROOT)), "verdict": rep["verdict"],
                        "expected": expectations[arm], "expectation_source": expect_source[arm],
                        "controls_ok": rep["controls"]["all_controls_ok"],
                        "nr_throttled_delta": rep["nr_throttled_delta"]}
        print(f"[{arm}] verdict={rep['verdict']} expected={rep['expected_verdict_for_selftest']} "
              f"controls_ok={rep['controls']['all_controls_ok']} "
              f"nr_throttled_delta={rep['nr_throttled_delta']} -> {path.name}", flush=True)

    fp_after = {f["path"]: f["sha256_12"]
                for f in [fingerprint(REPO_ROOT / p) for p in
                          [f["path"] for f in prov["probed_files"]]]}
    readonly_ok = fp_before == fp_after
    if not readonly_ok:
        print(f"[FATAL] 只读纪律被破坏：{fp_before} != {fp_after}", flush=True)

    selftest = None
    if args.selftest:
        checks = [{"id": "readonly_preserved", "expected": True, "measured": readonly_ok}]
        for arm in arms:
            checks.append({"id": f"verdict[{arm}]", "expected": expectations[arm],
                           "measured": reports[arm]["verdict"],
                           "expectation_source": expect_source[arm]})
            checks.append({"id": f"controls_ok[{arm}]", "expected": True,
                           "measured": reports[arm]["controls_ok"]})
        m1 = json.loads((out_root / "probe_mut_fixed_whitelist.json").read_text(encoding="utf-8"))
        named = []
        for vname, v in m1["variants"].items():
            if v.get("carries_images") and v["call_outcome"] == "LearnerRefused":
                named.append({"variant": vname,
                              "keys_named": v["refusal"]["keys_named_in_refusal"],
                              "refusal_kind": v["refusal"]["refusal_kind"]})
        checks.append({"id": "M1_refusal_names_dropped_keys(裁定49.2-4)", "expected": True,
                       "measured": bool(named) and all(n["keys_named"] for n in named),
                       "detail": named})
        m2 = json.loads((out_root / "probe_mut_consume_base0.json").read_text(encoding="utf-8"))
        main_rep = json.loads((out_root / "probe_main.json").read_text(encoding="utf-8"))
        base0 = POLICY_IMAGE_KEYS[0]
        if main_rep["verdict"] == "DEFECT_REPRODUCED":
            # 修复前的世界：M2 桩必须只把 base_0_rgb 判成"被消费"（证明逐键测试非写死）
            sens2 = m2["variants"]["pi05_policy_layer"].get("per_key_sensitivity", {})
            checks.append({"id": "M2_base0_detected_consumed", "expected": True,
                           "measured": bool(sens2.get(base0, {}).get("output_changed"))})
            others = [sens2.get(k, {}).get("output_changed") for k in POLICY_IMAGE_KEYS[1:]]
            checks.append({"id": "M2_other_image_keys_still_dropped", "expected": [False, False],
                           "measured": others})
        else:
            # 修复后的世界：仓库实现已**先于** M2 桩拒绝带图像的快照 ⇒ M2 的判别力被取代。
            # 这仍是可检验的主张：所有带图像变体都必须是 LearnerRefused（不是静默返回）。
            checks.append({
                "id": "M2_sensitivity_superseded_by_repo_refusal",
                "expected": True,
                "measured": all(v["call_outcome"] == "LearnerRefused"
                                for v in m2["variants"].values() if v.get("carries_images")),
                "reason": ("主臂 verdict=" + main_rep["verdict"] +
                           " ≠ DEFECT_REPRODUCED ⇒ 逐键敏感度对带图像变体不再可得"),
            })
        ok = all(c["expected"] == c["measured"] for c in checks)
        selftest = {"ok": ok, "checks": checks, "ts": now_iso()}
        (out_root / "selftest.json").write_text(
            json.dumps(selftest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        for c in checks:
            flag = "PASS" if c["expected"] == c["measured"] else "FAIL"
            print(f"  [{flag}] {c['id']}: expected={c['expected']} measured={c['measured']}", flush=True)

    summary = {
        "probe_id": PROBE_ID, "task_id": TASK_ID, "generated_at": now_iso(),
        "arms": reports, "readonly_preserved": readonly_ok,
        "fingerprints_before": fp_before, "fingerprints_after": fp_after,
        "selftest": selftest,
        "expectations": expectations, "expectation_sources": expect_source,
        "machine": machine_block(),
        "status_word_v4": "已实现未验证（探针本体）；被测对象的判定见各臂 verdict",
    }
    (out_root / "probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if not readonly_ok:
        return 3
    if args.selftest and not selftest["ok"]:
        return 2
    for arm in arms:
        if reports[arm]["verdict"] == "PROBE_INVALID":
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
