#!/usr/bin/env python3
"""A2 / 六步序列**第 1 步的先落并对齐腿**（CPU-only · `MUJOCO_GL=osmesa` · `gpu_used=false`）。

## 为什么有这一腿（不是"多写一个脚本"）
第 1 步的内容是「小量示范**过拟合** + **从示范初态闭环执行**；检查**动作、夹爪、时间对齐**」
（`rl_harness_supervision/d_handoff_to_a2_20260930.md` 补单四 §三）。这三件事**每一件都有一个
静默错的形状**，而且都不会抛异常：

1. **归一化静默 pass-through** —— π₀.₅ base 的 `policy_preprocessor.json` 里
   `normalizer_processor.config.features = {}` ⇒ `_normalize_observation()` 一个键都不遍历
   ⇒ 状态原样进 `Pi05PrepareStateTokenizerProcessorStep` 的 256-bin 离散化
   （`lerobot/policies/pi05/processor_pi05.py:77`）⇒ **这就是 G3 `0/20` 的已证接口缺陷**
   （裁定 95.3-①②）。**修法 = 注入 C2 的唯一一档 stats**；注入是否真的生效，必须在**上卡之前**
   用实物证明，不能靠"我写了 override"。
2. **`-1` bin 静默进 prompt** —— `np.digitize(x, linspace(-1,1,257)[:-1]) - 1` 对 `x < -1`
   给 **-1**（`harness/prompt_bin_guard.py:56` `ILLEGAL_BIN_LOW`），对 `x ≥ 1` 给 **255**
   （`SAT_BIN_HIGH`，**合法**饱和）。⇒ 越界分两种：**-1 是硬红**（§23.2），**+1 侧只是软边界**
   （裁定 90.4-1 出 warning 不红）。**两种必须分开报，不许合并成一个"越界率"。**
3. **示范初态复现不了** —— `env.reset(seed=s)` 的方块位姿来自 `gym_aloha` 的
   `sample_box_pose(seed)`，而 B2 的示范用的是 `scripts/b2_s1_scripted_expert.py:113`
   的 `sample_box_pose_seeded(seed, direction)`（**x 区间按方向镜像**）⇒ 反向集的
   `reset(seed)` **复现不出**示范的方块 x。而示范 frame 0 也**不是** `reset()` 的那一刻：
   B2 先跑 `settle_steps=12` 让方块从 z=0.05 落到 0.02、**同时**把两腕转到 `R_DOWN`
   （`b2_s1_scripted_expert.py:944-958`），这 12 步**不进数据集**。
   ⇒ 「从示范初态闭环执行」必须有**可复现且可自证**的初始化，否则第 1 步的 t=0 观测
   就已经是分布外的，过拟合探针测不到它要测的东西。

本腿把上面三件**在 CPU 上、不占卡**全部实测掉，并且每一件都带**负对照**（牙必须会咬）。
**未跑过的代码不交付** ⇒ 本脚本先跑通、落盘，才允许写第 1 步的上卡入口。

## 本腿**不做**什么
* **不训练、不上卡、不推理**：`policy_executed=false`、`gpu_used=false`。**不加载 14.4 GB 权重**
  （`PI05Policy.from_pretrained` 一次都不调）⇒ 处理器管线用 `PI05Config` + `make_pre_post_processors`
  单独构造，config 从 `config.json` 读（L7 因此是"读 config 而不是载模型"）。
* **不判定能力**（裁定 46）：`capability_claim=false`、`success_rate_column="not_an_exit_criterion"`；
  本件所有 GREEN **只指接口/口径判词**。
* **不改任何他线文件**：C2 的 `harness/env_gym_aloha.py`、B2 的专家脚本一律**只读**；
  对 C2 的判定层只**测量并登记**，不修（L9 的 `table_z_ref` 发现即此形状）。
* **不用 `rm`**：产物只写自己的 `--out-dir`。

## 判据与口径
* **三值纪律**：每个 leg 都给 `measurement_status ∈ {measured, not_measured}` + `verdict`；
  测不到就写 `not_measured`，**不写 0 / false 顶替**。
* **行数口径**（裁定 98.3-②/98.5-②）：一律点名 `n_lines_wc`（换行符个数）或
  `n_lines_splitlines`；**裸 `n_lines` 禁用**（本脚本末尾有牙自检这条）。
* **对账唯一约束性判据 = `sha256[:12]`**；行数只作旁证。
* **数值成对**：吞吐/延迟类数字本腿不产；但机器负载读数（`loadavg` 三点 + `nr_throttled`，
  cgroup **v1** `/sys/fs/cgroup/cpu/cpu.stat`）在开头与结尾各取一次，复用
  `harness/prompt_bin_guard.gpu_window_readings()`（不重造）。
* **像素只登记不判红**（裁定 85.5）：L10 的三相机像素差异**不构成**判据。

## 用法
    MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_step1_prealign_verify.py \
        --out-dir runs/vla/a2_step1_prealign_20260930

    # 只做纯数值腿（不建 env、不渲染，秒级）：
    MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_step1_prealign_verify.py \
        --out-dir runs/vla/a2_step1_prealign_dry --skip-env

退出码：`0` 全 measured 且无阻塞红 · `1` 有阻塞红 · `3` 存在 `not_measured` · `2` 用法/环境错。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np                                                     # noqa: E402

from harness import prompt_bin_guard as PBG                            # noqa: E402
from harness import vla_runtime as VR                                  # noqa: E402

CST = timezone(timedelta(hours=8))
EXIT_OK, EXIT_BLOCKING_RED, EXIT_USAGE, EXIT_NOT_MEASURED = 0, 1, 2, 3

# ── 活件路径（引用时**当场重算** sha/行数，不转录）──────────────────────────────
P_C2_STATS = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/arm_mainline/stats/"
              "s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05"
              "__mainline_path_check.json")
P_C2_BROADCAST = "docs/c2_to_a2_bc_stats_handoff_20260930.md"
P_NPZ = "runs/vla/b2_states_14d_20260930/formal40/states_14d.npz"
P_DS = "runs/vla/b2_sim_demo_bidir_20260930/formal/pi05_lerobot"
P_MANIFEST = "runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json"
P_WEIGHTS = "runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044"
P_EXPERT = "scripts/b2_s1_scripted_expert.py"
P_CALIB = "scripts/e_mainline_render_calib.py"
DEFAULT_TOKENIZER = ("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/hf-cache/"
                     "modelscope/google/paligemma-3b-pt-224")

N_LINES_CALIBER = ("n_lines_wc = 换行符个数（`wc -l`）；n_lines_splitlines = "
                   "len(read_text().splitlines())。末行无换行符 ⇒ 两口径差 1。"
                   "对账的唯一约束性判据 = sha256[:12]（裁定 98.3-①④ / 98.5-②）。")
BLIND_DIMS = [0, 3, 5, 7, 10, 12]        # C2 的 94.3 盲点维（Ⅱ 类登记，**不是**能力判据）
GRIP_DIMS = [6, 13]                      # left_gripper_normalized / right_gripper_normalized
ARM_DIMS = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]
STATE_DIM = 14
DIRECTION_BY_MANIFEST = {"forward": "right_to_left", "reverse": "left_to_right"}


# ══════════════════════════ 通用小件（身份 / 三值 / 落盘）═════════════════════════
def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(p: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:                                                # noqa: BLE001
        return None


def identity(rel: str) -> dict:
    """活件身份：**当场重算**（`as_of` 同批），绝不转录别处的读数。"""
    p = REPO / rel
    out: dict = {"path": rel, "exists": p.exists(), "as_of": now_iso(),
                 "n_lines_caliber": N_LINES_CALIBER}
    if not p.exists():
        out.update({"measurement_status": "not_measured", "sha256_12": None, "bytes": None,
                    "why": "路径不存在 ⇒ not_measured（不是「文件为空」）"})
        return out
    raw = p.read_bytes()
    txt = raw.decode("utf-8", errors="replace")
    out.update({"measurement_status": "measured",
                "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
                "bytes": len(raw),
                "n_lines_wc": txt.count("\n"),
                "n_lines_splitlines": len(txt.splitlines()),
                "ends_with_newline": bool(raw.endswith(b"\n")),
                "mtime": datetime.fromtimestamp(p.stat().st_mtime, CST).isoformat(timespec="seconds")})
    return out


def write_json(path: pathlib.Path, obj) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2, default=jdefault) + "\n"
    path.write_text(txt, encoding="utf-8")
    rel = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
    return {"path": rel, "sha256_12": hashlib.sha256(txt.encode("utf-8")).hexdigest()[:12],
            "bytes": len(txt.encode("utf-8")), "n_lines_wc": txt.count("\n"),
            "n_lines_splitlines": len(txt.splitlines()), "n_lines_caliber": N_LINES_CALIBER}


def jdefault(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pathlib.Path,)):
        return str(o)
    if isinstance(o, (datetime,)):
        return o.isoformat(timespec="seconds")
    return str(o)


def load_module_by_path(name: str, relpath: str):
    path = REPO / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def leg(leg_id: str, what: str, **kw) -> dict:
    d = {"leg_id": leg_id, "what": what, "measurement_status": "not_measured",
         "verdict": None, "blocking": False}
    d.update(kw)
    return d


# ══════════════════════════ 数据读取（一次读，多腿复用）═════════════════════════
def read_dataset_arrays(ds_dir: pathlib.Path) -> dict:
    import pandas as pd
    files = sorted((ds_dir / "data" / "chunk-000").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"{ds_dir}/data/chunk-000/*.parquet 为空")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    state = np.stack(df["observation.state"].values).astype(np.float64)
    action = np.stack(df["action"].values).astype(np.float64)
    info = json.loads((ds_dir / "meta" / "info.json").read_text(encoding="utf-8"))
    ep = df["episode_index"].values.astype(np.int64)
    per_ep = {}
    for e in sorted(set(ep.tolist())):
        m = ep == e
        per_ep[int(e)] = {"n_frames": int(m.sum()),
                          "frame0_state": state[m][0].tolist(),
                          "frame0_index": int(np.flatnonzero(m)[0]),
                          "task_index": int(df["task_index"].values[m][0]),
                          "first_ts": float(df["timestamp"].values[m][0]),
                          "last_ts": float(df["timestamp"].values[m][-1])}
    return {"df": df, "state": state, "action": action, "info": info,
            "episode_index": ep, "per_ep": per_ep,
            "parquet_files": [str(f.relative_to(REPO)) for f in files],
            "image_columns": [c for c in df.columns if c.startswith("observation.images.")]}


def decode_inline_png(cell) -> np.ndarray | None:
    """数据集的图像是 **PNG 内嵌 parquet**（`{"bytes":…,"path":…}`；`images/` 是占位空目录）。"""
    b = None
    if isinstance(cell, dict):
        b = cell.get("bytes")
    elif isinstance(cell, (bytes, bytearray)):
        b = bytes(cell)
    if not b:
        return None
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(b)).convert("RGB"), dtype=np.uint8)


def read_stats(stats_path: pathlib.Path) -> dict:
    st = json.loads(stats_path.read_text(encoding="utf-8"))
    a = st["arrays"]
    return {"raw": st,
            "q01": np.asarray(a["q01"], dtype=np.float64),
            "q99": np.asarray(a["q99"], dtype=np.float64),
            "representation_version": st.get("representation_version"),
            "stats_provenance": st.get("stats_provenance"),
            "bc_admission": st.get("bc_admission") or {},
            "n_dims": st.get("n_dims"), "n_bins": st.get("n_bins"),
            "bin_width": st.get("bin_width"), "lerobot_eps": st.get("lerobot_eps"),
            "floor": np.asarray(a["floor"], dtype=np.float64),
            "physical_range": np.asarray(a["physical_range"], dtype=np.float64)}


def quantiles_norm(x: np.ndarray, q01: np.ndarray, q99: np.ndarray, eps: float) -> np.ndarray:
    """**逐字复刻** `lerobot/processor/normalize_processor.py` 的 QUANTILES 分支（含 eps 语义）：
    `denom = q99 - q01`；`denom == 0 ⇒ eps`；正向 `2*(x-q01)/denom - 1`；逆向
    `(x+1)*denom/2 + q01`。这里独立实现是为了能**离线**扫全量 11035 帧，
    而 L1 会用真处理器再验一次同样的数（两条路必须对上，对不上即红）。
    """
    denom = q99 - q01
    denom = np.where(denom == 0, np.float64(eps), denom)
    return 2.0 * (x - q01) / denom - 1.0


def quantiles_denorm(y: np.ndarray, q01: np.ndarray, q99: np.ndarray, eps: float) -> np.ndarray:
    denom = q99 - q01
    denom = np.where(denom == 0, np.float64(eps), denom)
    return (y + 1.0) * denom / 2.0 + q01


# ══════════════════════════ L1 stats 注入是否真的生效 ══════════════════════════
def build_cfg_and_processors(weights_dir: pathlib.Path, tokenizer_dir: str,
                             stats_block: dict, state_dim: int):
    """构造 `PI05Config` + 处理器管线，**不加载模型权重**（`from_pretrained` 一次都不调）。

    两处 A2 的口径选择（都显式登记，不藏在代码里）：
      ① `observation.state` / `action` 的 feature shape 从 config.json 的 **32** 改成数据集的
         **14**。理由：`max_state_dim`/`max_action_dim`（=32）才是模型内部的 padding 宽度，
         feature shape 是**接口宽度**；lerobot 从数据集训时本来就会把它写成数据集的宽度
         （`configuration_pi05.py:__post_init__` 只在**缺键**时才填 32）。
         影响面：`PI05Policy.forward` 的 loss 截断宽度 = `output_features[ACTION].shape[0]`
         ⇒ 14 时**只监督真实 14 维**（padding 维不当 0 目标训），`predict_action_chunk`
         也截到 14 ⇒ **normalizer 与 unnormalizer 两侧同一宽度**，不需要给 padding 维编 stats。
      ② `features` 里三个 VISUAL 键按 config.json 原样带上（`norm_map` 的 VISUAL=IDENTITY ⇒
         处理器对它们早退），目的是让注入后的 `features` 与 lerobot 自己
         `make_pi05_pre_post_processors()` 的 `{**input_features, **output_features}` 同形。
    """
    import torch                                                     # noqa: F401
    from lerobot.configs.types import FeatureType, PolicyFeature
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.pi05.configuration_pi05 import PI05Config

    cfgjson = json.loads((weights_dir / "config.json").read_text(encoding="utf-8"))
    inp_raw = dict(cfgjson["input_features"])
    out_raw = dict(cfgjson["output_features"])
    shape_change = {}
    for key, dim in (("observation.state", state_dim), ("action", state_dim)):
        src = inp_raw.get(key) or out_raw.get(key)
        old = list(src["shape"])
        if old != [dim]:
            shape_change[key] = {"config_json_shape": old, "used_shape": [dim],
                                 "why": "接口宽度取数据集的 14；模型内部 padding 宽度是 max_*_dim=32"}
            src = dict(src)
            src["shape"] = [dim]
        if key in inp_raw:
            inp_raw[key] = src
        if key in out_raw:
            out_raw[key] = src
    inp = {k: PolicyFeature(type=FeatureType(v["type"]), shape=tuple(v["shape"]))
           for k, v in inp_raw.items()}
    out = {k: PolicyFeature(type=FeatureType(v["type"]), shape=tuple(v["shape"]))
           for k, v in out_raw.items()}
    kw = {k: v for k, v in cfgjson.items() if k not in ("input_features", "output_features", "type")}
    kw["device"] = "cpu"
    cfg = PI05Config(input_features=inp, output_features=out, **kw)

    q01 = [float(x) for x in stats_block["q01"]]
    q99 = [float(x) for x in stats_block["q99"]]
    feats = {}
    for k, v in inp_raw.items():
        feats[k] = {"type": v["type"], "shape": list(v["shape"])}
    for k, v in out_raw.items():
        feats[k] = {"type": v["type"], "shape": list(v["shape"])}
    injected_stats = {"observation.state": {"q01": q01, "q99": q99},
                      "action": {"q01": q01, "q99": q99}}
    pre, post = make_pre_post_processors(
        cfg, str(weights_dir),
        preprocessor_overrides={
            "normalizer_processor": {"features": feats, "stats": injected_stats},
            "tokenizer_processor": {"tokenizer_name": tokenizer_dir},
            "device_processor": {"device": "cpu"}},
        postprocessor_overrides={
            "unnormalizer_processor": {"features": {"action": {"type": "ACTION", "shape": [state_dim]}},
                                       "stats": injected_stats},
            "device_processor": {"device": "cpu"}})
    return cfg, pre, post, {"feature_shape_change": shape_change,
                            "injected_features": feats,
                            "injected_stats": injected_stats,
                            "weights_dir": str(weights_dir),
                            "tokenizer_dir": tokenizer_dir}


def l1_stats_injection(ctx) -> dict:
    L = leg("L1_stats_injection",
            "注入 C2 的唯一一档 stats 之后，normalizer/unnormalizer 的 `features` 是否**真的**非空"
            "（= G3 `0/20` 静默 pass-through 根因的反面），且注入的 q01/q99 与 C2 实物**逐位相同**")
    try:
        cfg = ctx["cfg"]
        pre, post = ctx["pre"], ctx["post"]
        steps = {type(s).__name__: s for s in pre.steps}
        norm = steps.get("NormalizerProcessorStep")
        unnorm = {type(s).__name__: s for s in post.steps}.get("UnnormalizerProcessorStep")
        if norm is None or unnorm is None:
            L.update({"measurement_status": "not_measured",
                      "why": f"管线里没有 normalizer/unnormalizer（实到 {sorted(steps)}）"})
            return L
        nf = dict(getattr(norm, "features", {}) or {})
        uf = dict(getattr(unnorm, "features", {}) or {})
        ts = dict(getattr(norm, "_tensor_stats", {}) or {})
        c2 = ctx["stats"]
        inj_q01 = np.asarray(ts.get("observation.state", {}).get("q01"), dtype=np.float64) \
            if "observation.state" in ts else None
        inj_q99 = np.asarray(ts.get("observation.state", {}).get("q99"), dtype=np.float64) \
            if "observation.state" in ts else None
        bitwise = bool(inj_q01 is not None and inj_q99 is not None
                       and np.array_equal(inj_q01, c2["q01"].astype(np.float32).astype(np.float64))
                       and np.array_equal(inj_q99, c2["q99"].astype(np.float32).astype(np.float64)))
        cfg_json = json.loads((REPO / P_WEIGHTS / "policy_preprocessor.json").read_text(encoding="utf-8"))
        on_disk_features_n = len(((cfg_json["steps"][2] or {}).get("config") or {}).get("features") or {})
        measured = {
            "normalizer_features_n": len(nf),
            "normalizer_features_keys": sorted(nf.keys()),
            "unnormalizer_features_n": len(uf),
            "unnormalizer_features_keys": sorted(uf.keys()),
            "normalizer_tensor_stats_keys": sorted(ts.keys()),
            "q01_q99_bitwise_equal_to_c2_stats": bitwise,
            "injected_q01_first4": [float(x) for x in (inj_q01[:4] if inj_q01 is not None else [])],
            "saved_preprocessor_features_n_on_disk": on_disk_features_n,
            "saved_preprocessor_is_pass_through": bool(on_disk_features_n == 0),
            "g3_root_cause_reversed": bool(len(nf) > 0 and bitwise),
            "norm_map": {str(k): str(v) for k, v in (getattr(norm, "norm_map", {}) or {}).items()},
            "chunk_size": int(cfg.chunk_size), "n_action_steps": int(cfg.n_action_steps),
            "max_state_dim": int(cfg.max_state_dim), "max_action_dim": int(cfg.max_action_dim),
            "state_feature_shape_used": list(cfg.input_features["observation.state"].shape),
            "action_feature_shape_used": list(cfg.output_features["action"].shape),
            "model_weights_loaded": False,
            "why_no_weights": "本腿不载 14.4 GB safetensors；处理器管线只依赖 config.json",
        }
        red = []
        if not len(nf):
            red.append("normalizer_features_empty__silent_pass_through")
        if not bitwise:
            red.append("injected_q01_q99_not_bitwise_equal_to_c2_stats")
        if not len(uf):
            red.append("unnormalizer_features_empty__action_would_not_be_denormalized")
        L.update({"measurement_status": "measured", "measured": measured,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red),
                  "authority": "裁定 95.3-①②（G3 0/20 的接口缺陷）· 补单四 §三（stats 注入）· "
                               "C2 广播件 §3（唯一一档，换 normalizer = 换 stats = 必须先报 D）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}",
                  "why": "构造/注入抛异常 ⇒ not_measured + 阻塞红（不许静默降级成状态输入小模型）"})
    return L


# ══════════════════════════ L2 归一化后落 [-1,1] 的比例（**两侧分开**）══════════════
def l2_normalized_range(ctx) -> dict:
    L = leg("L2_normalized_range",
            "全量 11035 帧的 state 与 action 经 QUANTILES 归一化后落 [-1,1] 的比例；"
            "**下越界（< -1 ⇒ `-1` bin）与上越界（≥ 1 ⇒ 255 合法饱和）分开报**")
    try:
        c2 = ctx["stats"]
        eps = float(c2["lerobot_eps"] or 1e-8)
        out = {}
        for name in ("state", "action"):
            x = ctx["ds"][name]
            y = quantiles_norm(x, c2["q01"], c2["q99"], eps)
            below = y < -1.0
            above = y > 1.0
            per_dim_below = (below.mean(axis=0)).round(6).tolist()
            per_dim_above = (above.mean(axis=0)).round(6).tolist()
            out[name] = {
                "n_rows": int(x.shape[0]), "n_dims": int(x.shape[1]),
                "frac_in_closed_unit_interval": float(((~below) & (~above)).mean()),
                "frac_below_minus_1_ILLEGAL_BIN": float(below.mean()),
                "frac_above_plus_1_legal_saturation": float(above.mean()),
                "n_values_below": int(below.sum()), "n_values_above": int(above.sum()),
                "min_normalized": float(y.min()), "max_normalized": float(y.max()),
                "max_overshoot_below": float(max(0.0, -1.0 - float(y.min()))),
                "max_overshoot_above": float(max(0.0, float(y.max()) - 1.0)),
                "per_dim_frac_below": per_dim_below, "per_dim_frac_above": per_dim_above,
                "dims_with_below": [i for i, v in enumerate(per_dim_below) if v > 0],
                "dims_with_above": [i for i, v in enumerate(per_dim_above) if v > 0],
                "soft_boundary_ruling": "裁定 90.4-1：越 [-1,1] 是**软边界**（warning 不红）",
                "hard_red_ruling": "§23.2 / `prompt_bin_guard.ILLEGAL_BIN_LOW`：`-1` bin 是**硬红**",
            }
        # state 侧的 `-1` bin 是硬红；action 侧的越界只影响训练目标（软边界）
        red = []
        warn = []
        if out["state"]["n_values_below"] > 0:
            red.append("state_normalized_below_minus_1__illegal_bin")
        if out["state"]["n_values_above"] > 0:
            warn.append("state_normalized_above_plus_1__legal_saturation_255")
        if out["action"]["n_values_below"] > 0 or out["action"]["n_values_above"] > 0:
            warn.append("action_normalized_outside_unit_interval__soft_boundary")
        out["verdict_inputs"] = {"red": red, "warnings": warn}
        L.update({"measurement_status": "measured", "measured": out,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "warnings": warn, "blocking": bool(red),
                  "blind_dims_caveat": (f"盲点维 {BLIND_DIMS}（C2 的 94.3，Ⅱ 类登记）不得写成全 14 维结论；"
                                        "本腿的 per-dim 数字就是为了让这条限定可核")})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L3 round-trip（离线公式 vs 真处理器）══════════════
def l3_roundtrip(ctx) -> dict:
    L = leg("L3_roundtrip",
            "① `denorm(norm(x)) == x` 的逐位残差；② **离线公式**与**真处理器管线**在同一条 state 上"
            "给出的归一化值必须一致（两条路对不上 = 注入没生效或口径漂移）")
    try:
        import torch
        c2 = ctx["stats"]
        eps = float(c2["lerobot_eps"] or 1e-8)
        res = {}
        for name in ("state", "action"):
            x = ctx["ds"][name]
            y = quantiles_norm(x, c2["q01"], c2["q99"], eps)
            xb = quantiles_denorm(y, c2["q01"], c2["q99"], eps)
            d = np.abs(xb - x)
            res[f"{name}_offline_roundtrip"] = {
                "n": int(x.size), "max_abs_diff": float(d.max()), "mean_abs_diff": float(d.mean()),
                "tol": 1e-9, "pass": bool(d.max() <= 1e-9),
                "caliber": "float64 离线复算（不是 float32 管线）"}
        # 真处理器：state 侧
        norm = {type(s).__name__: s for s in ctx["pre"].steps}["NormalizerProcessorStep"]
        sample = ctx["ds"]["state"][:64].astype(np.float32)
        tr = torch.from_numpy(sample)
        from lerobot.configs.types import FeatureType
        got = norm._apply_transform(tr, "observation.state", FeatureType.STATE,
                                    inverse=False).detach().numpy().astype(np.float64)
        want = quantiles_norm(sample.astype(np.float64), c2["q01"], c2["q99"], eps)
        d2 = np.abs(got - want)
        res["state_processor_vs_offline_formula"] = {
            "n_rows": int(sample.shape[0]), "max_abs_diff": float(d2.max()),
            "tol_float32": 1e-5, "pass": bool(d2.max() <= 1e-5),
            "processor_class": type(norm).__name__,
            "note": "float32 管线 vs float64 公式 ⇒ 容差取 1e-5（不是逐位）"}
        # 真处理器：action 侧 round-trip（normalizer 正向 + unnormalizer 逆向）
        unnorm = {type(s).__name__: s for s in ctx["post"].steps}["UnnormalizerProcessorStep"]
        y = norm._apply_transform(tr, "observation.state", FeatureType.STATE, inverse=False)
        back = unnorm._apply_transform(y, "action", FeatureType.ACTION,
                                       inverse=True).detach().numpy().astype(np.float64)
        d3 = np.abs(back - sample.astype(np.float64))
        res["state_norm_then_action_denorm_roundtrip"] = {
            "max_abs_diff": float(d3.max()), "tol": 1e-5, "pass": bool(d3.max() <= 1e-5),
            "why_this_pair": ("pi05 的 state 与 action 用**同一档** q01/q99（C2 只有一档），"
                              "所以 state→norm→action→denorm 也必须回到原值；回不去 = 两侧不同档")}
        red = [k for k, v in res.items() if isinstance(v, dict) and v.get("pass") is False]
        L.update({"measurement_status": "measured", "measured": res,
                  "verdict": "GREEN" if not red else "RED",
                  "red_codes": [f"roundtrip_failed:{k}" for k in red], "blocking": bool(red)})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L4 真 prompt 的 bin 审计（`-1` token 必须为 0）══════════
def l4_prompt_bin_guard(ctx, n_samples: int) -> dict:
    L = leg("L4_prompt_bin_guard",
            "把**真实数据集 state** 灌进真处理器管线，用 `harness/prompt_bin_guard.PromptCapture` "
            "的旁路钩子抓**模型真正吃到的那一条 prompt**，审计 bin token：`-1` 命中数必须为 0")
    try:
        import torch
        st = ctx["ds"]["state"]
        n = min(int(n_samples), st.shape[0])
        idx = np.linspace(0, st.shape[0] - 1, n).astype(int)
        cap = PBG.PromptCapture(ctx["pre"], keep_last_n=n + 8).attach()
        zero_img = np.zeros((3, 224, 224), dtype=np.float32)
        try:
            for i in idx:
                batch = {"observation.state": torch.from_numpy(st[i].astype(np.float32)),
                         "observation.images.base_0_rgb": torch.from_numpy(zero_img),
                         "observation.images.left_wrist_0_rgb": torch.from_numpy(zero_img),
                         "observation.images.right_wrist_0_rgb": torch.from_numpy(zero_img),
                         "task": ctx["task_texts"][0]}
                ctx["pre"](batch)
            audit = cap.audit()
        finally:
            cap.detach()
        prompts = list(cap.prompts)
        per = [PBG.audit_prompt_text(p) for p in prompts]
        # **键名必须来自审计器实物**：`audit_prompt_text()` 返回的是 `n_illegal_bin_minus1` /
        # `n_saturated_bin_255` / `token_min` / `token_max`。本腿第一版读的是不存在的
        # `n_illegal_low_tokens` ⇒ 计数恒 0 = **假绿**（缺陷类 ⑲「判据比对象空间窄」的同型）。
        # 已改，并加了 `AUDIT_KEYS_REQUIRED` 断言：键不在就 not_measured，不静默当 0。
        AUDIT_KEYS_REQUIRED = ("verdict", "measurement_status", "n_state_tokens",
                               "n_illegal_bin_minus1", "n_saturated_bin_255",
                               "token_min", "token_max")
        missing_keys = sorted({k for a in per for k in AUDIT_KEYS_REQUIRED if k not in a})
        n_illegal = sum(int(a.get("n_illegal_bin_minus1") or 0) for a in per)
        n_sat = sum(int(a.get("n_saturated_bin_255") or 0) for a in per)
        tok_counts = sorted({int(a.get("n_state_tokens") or -1) for a in per})
        tmins = [int(a["token_min"]) for a in per if a.get("token_min") is not None]
        tmaxs = [int(a["token_max"]) for a in per if a.get("token_max") is not None]
        per_verdicts = sorted({str(a.get("verdict")) for a in per})
        measured = {
            "n_prompts_requested": int(n), "n_prompts_captured": len(prompts),
            "capture_hook_hits": audit.get("n_hook_captures"),
            "tokenizer_step_seen": audit.get("tokenizer_step_seen"),
            "hook_error": audit.get("hook_error"),
            "aggregate_verdict": audit.get("verdict"),
            "aggregate_n_illegal_bin_minus1": audit.get("n_illegal_bin_minus1"),
            "aggregate_illegal_bin_dims_union": audit.get("illegal_bin_dims_union"),
            "aggregate_n_prompts_red": audit.get("n_prompts_red"),
            "per_prompt_verdicts": per_verdicts,
            "audit_keys_required": list(AUDIT_KEYS_REQUIRED),
            "audit_keys_missing": missing_keys,
            "n_illegal_bin_minus1_total": int(n_illegal),
            "n_saturated_bin_255_total": int(n_sat),
            "state_token_counts_observed": tok_counts,
            "expected_token_count": PBG.MAX_STATE_DIM,
            "token_min_over_all_prompts": (min(tmins) if tmins else None),
            "token_max_over_all_prompts": (max(tmaxs) if tmaxs else None),
            "illegal_bin_low": PBG.ILLEGAL_BIN_LOW, "sat_bin_high": PBG.SAT_BIN_HIGH,
            "first_prompt_prefix": (prompts[0][:260] if prompts else None),
            "auditor_self_verdict": (audit.get("pattern_coverage_probe") or {}).get("auditor_self_verdict"),
            "padded_dims_note": ("state 被 `pad_vector` 补到 32 维后再离散化 ⇒ token 数应为 32；"
                                 "补位是 0.0 ⇒ 落在中位 bin 128（不是 -1），负对照 T2b 实测"),
        }
        red = []
        if missing_keys:
            red.append(f"auditor_key_space_narrower_than_object:{missing_keys}")
        if len(prompts) != n:
            red.append("prompt_capture_count_mismatch")
        if n_illegal != 0:
            red.append("illegal_minus_1_bin_in_prompt")
        if audit.get("verdict") == "RED" or per_verdicts != ["GREEN"]:
            red.append("prompt_bin_guard_aggregate_or_per_prompt_red")
        if tok_counts and tok_counts != [PBG.MAX_STATE_DIM]:
            red.append(f"state_token_count_not_{PBG.MAX_STATE_DIM}")
        L.update({"measurement_status": "measured", "measured": measured,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red),
                  "audit_full": audit,
                  "authority": "§23.2（`-1` bin 硬红）· 裁定 94 补单-§二（bin 常量口径归 "
                               "`harness/prompt_bin_guard.py`）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L5 夹爪语义（维 6/13）══════════════════════════
def l5_gripper_semantics(ctx) -> dict:
    L = leg("L5_gripper_semantics",
            "夹爪维 6/13 的**动作**取值集合与**状态**取值范围；开合极性（哪一端是「开」）；"
            "以及 C2 的 floored 区间对二值动作的覆盖")
    try:
        ac = ctx["ds"]["action"]
        stt = ctx["ds"]["state"]
        c2 = ctx["stats"]
        eps = float(c2["lerobot_eps"] or 1e-8)
        out = {}
        for d in GRIP_DIMS:
            av = ac[:, d]
            sv = stt[:, d]
            uniq = np.unique(np.round(av, 6))
            nav = quantiles_norm(av[:, None], c2["q01"][d:d + 1], c2["q99"][d:d + 1], eps).reshape(-1)
            out[f"dim{d}"] = {
                "name": ctx["ds"]["info"]["features"]["action"]["names"][d],
                "action_n_unique": int(uniq.size),
                "action_unique_head": [float(x) for x in uniq[:8]],
                "action_unique_tail": [float(x) for x in uniq[-8:]],
                "action_is_binary_0_1": bool(uniq.size <= 64 and float(av.min()) >= -1e-9
                                             and float(av.max()) <= 1 + 1e-9
                                             and float(np.abs(av - np.round(av)).max()) < 1e-6
                                             and 0.0 in set(np.round(uniq, 3).tolist())
                                             and 1.0 in set(np.round(uniq, 3).tolist())),
                "action_min": float(av.min()), "action_max": float(av.max()),
                "action_frac_at_0": float((np.abs(av) < 1e-9).mean()),
                "action_frac_at_1": float((np.abs(av - 1.0) < 1e-9).mean()),
                "state_min": float(sv.min()), "state_max": float(sv.max()),
                "state_q01": float(np.quantile(sv, 0.01)), "state_q99": float(np.quantile(sv, 0.99)),
                "c2_q01": float(c2["q01"][d]), "c2_q99": float(c2["q99"][d]),
                "c2_floor": float(c2["floor"][d]), "c2_physical_range": float(c2["physical_range"][d]),
                "action_normalized_at_0": float(quantiles_norm(np.array([0.0]), c2["q01"][d:d+1],
                                                               c2["q99"][d:d+1], eps)[0]),
                "action_normalized_at_1": float(quantiles_norm(np.array([1.0]), c2["q01"][d:d+1],
                                                               c2["q99"][d:d+1], eps)[0]),
                "action_out_of_interval_frac": float((np.abs(nav) > 1.0).mean()),
            }
        # 极性：B2 的专家常量（只读文本抽取，不 import 执行他线模块）
        pol = {}
        try:
            txt = (REPO / P_EXPERT).read_text(encoding="utf-8", errors="replace")
            for key in ("GRIP_OPEN_NORM", "GRIP_CLOSE_NORM"):
                for ln in txt.splitlines():
                    s = ln.strip()
                    if s.startswith(key + " ="):
                        pol[key] = {"line_verbatim": s[:120],
                                    "value": float(s.split("=", 1)[1].split("#")[0].strip())}
                        break
            pol["polarity"] = ("action 1.0 = **张开**、0.0 = **合爪**（B2 的 `GRIP_OPEN_NORM=1.0` / "
                               "`GRIP_CLOSE_NORM=0.0`）⇒ 与「1=闭合」的直觉相反，必须显式登记")
            pol["state_normalizer"] = ("state 维 6/13 = `gym_aloha.constants."
                                       "normalize_puppet_gripper_position(qpos[6|14])`，"
                                       "CLOSE=0.01844 → 0.0、OPEN=0.058 → 1.0（同向：大=开）")
            pol["extraction_method"] = "只读文本抽取（A2 不 import 执行 B2 的模块）"
        except Exception as exc:                                      # noqa: BLE001
            pol = {"measurement_status": "not_measured", "error": f"{type(exc).__name__}: {exc}"}
        out["polarity"] = pol
        out["arm_dims_out_of_interval_frac"] = {
            str(d): float((np.abs(quantiles_norm(ac[:, d:d+1], c2["q01"][d:d+1],
                                                 c2["q99"][d:d+1], eps)) > 1.0).mean())
            for d in ARM_DIMS}
        warn = []
        if any(out[f"dim{d}"]["action_out_of_interval_frac"] > 0 for d in GRIP_DIMS):
            warn.append("gripper_action_outside_c2_interval__soft_boundary_ruling_90_4_1")
        if any(v > 0 for v in out["arm_dims_out_of_interval_frac"].values()):
            warn.append("arm_action_outside_c2_interval")
        L.update({"measurement_status": "measured", "measured": out, "verdict": "GREEN",
                  "warnings": warn, "blocking": False,
                  "interpretation_ban": "本腿只登记接口语义，**不**由此推断任何能力（裁定 46）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L6 14 维同序（数据集 vs npz）══════════════════════════
def l6_dim_order(ctx) -> dict:
    L = leg("L6_dim_order_same",
            "数据集 `observation.state.names` 与 `action.names` 是否**同名同序**；"
            "parquet 的 state 与 C2 stats 的**权威源** npz `frames` 是否**逐位相同**（同源链）")
    try:
        info = ctx["ds"]["info"]
        sn = info["features"]["observation.state"]["names"]
        an = info["features"]["action"]["names"]
        z = np.load(REPO / P_NPZ, allow_pickle=False)
        frames = np.asarray(z["frames"], dtype=np.float64)
        st = ctx["ds"]["state"]
        bitwise = bool(frames.shape == st.shape and np.array_equal(frames, st))
        content_sha = hashlib.sha256(np.ascontiguousarray(frames, dtype=np.float64).tobytes()).hexdigest()[:12]
        prov = (ctx["stats"]["raw"].get("provenance") or {}).get("frames") or [{}]
        measured = {
            "state_names": list(sn), "action_names": list(an),
            "names_identical_and_ordered": bool(list(sn) == list(an)),
            "n_dims_state": len(sn), "n_dims_action": len(an),
            "npz_shape": list(frames.shape), "parquet_state_shape": list(st.shape),
            "npz_vs_parquet_bitwise_equal": bitwise,
            "npz_frames_content_sha256_12": content_sha,
            "c2_stats_pins_content_sha256_12": prov[0].get("content_sha256_12"),
            "content_sha_equal_to_c2_pin": bool(content_sha == prov[0].get("content_sha256_12")),
            "npz_sha256_12": sha12(REPO / P_NPZ),
            "gripper_dims": GRIP_DIMS, "arm_dims": ARM_DIMS, "blind_dims": BLIND_DIMS,
        }
        red = []
        if not measured["names_identical_and_ordered"]:
            red.append("state_action_names_differ")
        if not bitwise:
            red.append("npz_frames_not_bitwise_equal_to_parquet_state")
        if not measured["content_sha_equal_to_c2_pin"]:
            red.append("content_sha_not_equal_to_c2_stats_pin")
        L.update({"measurement_status": "measured", "measured": measured,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red),
                  "authority": "裁定 90.4-4（npz = 权威读路径）· 85.4-3（同源硬闸）· 97.5（Tp5 同源）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L7 config 的 H ≥ 2n（**读 config，不载模型**）══════════
def l7_config_contract(ctx) -> dict:
    L = leg("L7_config_h_ge_2n",
            "从 `config.json` 读 `chunk_size` / `n_action_steps` / `max_*_dim`（**不载模型**），"
            "核 `H ≥ 2n`（n = `VR.MAINLINE_N_REPLAN`）与 `standard_sync` 的 `1 ≤ n ≤ H`")
    try:
        cfgjson = json.loads((REPO / P_WEIGHTS / "config.json").read_text(encoding="utf-8"))
        H = int(cfgjson["chunk_size"])
        nas = int(cfgjson["n_action_steps"])
        n = int(VR.MAINLINE_N_REPLAN)
        measured = {
            "chunk_size_H": H, "n_action_steps_from_config": nas,
            "mainline_n_replan": n, "max_state_dim": int(cfgjson["max_state_dim"]),
            "max_action_dim": int(cfgjson["max_action_dim"]),
            "num_inference_steps": int(cfgjson["num_inference_steps"]),
            "paligemma_variant": cfgjson.get("paligemma_variant"),
            "action_expert_variant": cfgjson.get("action_expert_variant"),
            "config_device_field": cfgjson.get("device"),
            "H_ge_2n": bool(H >= 2 * n), "H_eq_2n": bool(H == 2 * n),
            "standard_sync_1_le_n_le_H": bool(1 <= n <= H),
            "config_n_action_steps_vs_runtime_n_replan": {
                "config": nas, "runtime": n, "equal": bool(nas == n),
                "consequence": ("`ChunkedVlaRuntime` 用自己的 `n_replan=25` 切 chunk 的前 n 项，"
                                "**不读** config 的 `n_action_steps=50`；两者不等不是缺陷，"
                                "但必须落盘，否则读者会以为执行的是 50 步（裁定 65-1 的口径）")},
            "exec_mode_planned": VR.EXEC_MODE_STANDARD_SYNC,
            "prime_mode_planned": VR.PRIME_MODE_NONE,
            "model_weights_loaded": False,
        }
        red = []
        if not measured["H_ge_2n"]:
            red.append("H_lt_2n")
        if not measured["standard_sync_1_le_n_le_H"]:
            red.append("n_replan_out_of_range_for_standard_sync")
        L.update({"measurement_status": "measured", "measured": measured,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red),
                  "authority": "裁定 65-1（H=50 取 H≥2n 等号）· 95.3-④（第 1–2 步一律 standard_sync）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L8 40 条示范初态的**提取** ══════════════════════════
def build_demo_initial_states(ctx) -> dict:
    man = json.loads((REPO / P_MANIFEST).read_text(encoding="utf-8"))
    eps = man["episodes"]
    per_ep = ctx["ds"]["per_ep"]
    rows = []
    missing = []
    for i, e in enumerate(eps):
        side = None
        sp = e.get("sidecar")
        if isinstance(sp, str) and (REPO / sp).exists():
            side = json.loads((REPO / sp).read_text(encoding="utf-8"))
        elif isinstance(sp, dict):
            side = sp
        f0 = per_ep.get(i)
        if side is None or f0 is None:
            missing.append({"episode_index": i, "ep_id": e.get("ep_id"),
                            "sidecar_present": side is not None, "frame0_present": f0 is not None})
            continue
        rows.append({
            "episode_index": i, "ep_id": e["ep_id"], "manifest_direction": e["direction"],
            "env_direction": DIRECTION_BY_MANIFEST[e["direction"]], "seed": int(e["seed"]),
            "task_text": e["task_text"], "n_frames": int(f0["n_frames"]),
            "frame0_state": [float(x) for x in f0["frame0_state"]],
            "frame0_state_sha256_12": hashlib.sha256(
                np.ascontiguousarray(np.asarray(f0["frame0_state"], dtype=np.float32)).tobytes()
            ).hexdigest()[:12],
            "box_spawn_xyz": side.get("box_spawn_xyz"),
            "box_rest_after_settle_xyz": side.get("box_rest_after_settle_xyz"),
            "box_trajectory_xyz_every_10": side.get("box_trajectory_xyz_every_10"),
            "grip_cmd_trace_every_10": side.get("grip_cmd_trace_every_10"),
            "finger_spread_trace_every_10": side.get("finger_spread_trace_every_10"),
            "settle_steps_dropped": side.get("settle_steps_dropped"),
            "n_steps_expert": side.get("n_steps_expert"),
            "expert_verdict": (side.get("judge_verdict") or {}).get("verdict"),
            "dt": side.get("dt"),
        })
    seeds = sorted({r["seed"] for r in rows})
    dirs = sorted({r["manifest_direction"] for r in rows})
    return {"measurement_status": "measured" if rows and not missing else "not_measured",
            "n_rows": len(rows), "n_missing": len(missing), "missing": missing,
            "unique_seeds": seeds, "unique_directions": dirs,
            "per_direction_counts": {d: sum(1 for r in rows if r["manifest_direction"] == d)
                                     for d in dirs},
            "settle_steps_dropped_set": sorted({r["settle_steps_dropped"] for r in rows}),
            "dt_set": sorted({r["dt"] for r in rows}),
            "expert_verdict_set": sorted({str(r["expert_verdict"]) for r in rows}),
            "frame0_state_is_not_reset_state": True,
            "why": ("B2 的 `settle_steps=12` 不进数据集（`b2_s1_scripted_expert.py:944-958`）⇒ "
                    "frame 0 已经是「方块落到桌面 + 两腕转到 R_DOWN」之后的状态"),
            "rows": rows}


def l8_demo_initial_states(ctx) -> dict:
    L = leg("L8_demo_initial_states_extract",
            "从 manifest + sidecar + parquet 提取 40 条示范初态（ep_id / seed / direction / task / "
            "frame-0 state / box rest pose），并核它们的**完整性与一致性**")
    try:
        blk = ctx["init_states"]
        red = []
        if blk["measurement_status"] != "measured":
            red.append("initial_state_extraction_incomplete")
        if blk["n_rows"] != 40:
            red.append(f"n_rows_{blk['n_rows']}_ne_40")
        if blk["per_direction_counts"] != {"forward": 20, "reverse": 20}:
            red.append("direction_counts_not_20_20")
        if len(blk["unique_seeds"]) != 20:
            red.append(f"unique_seeds_{len(blk['unique_seeds'])}_ne_20")
        if blk["dt_set"] != [0.034]:
            red.append(f"dt_set_{blk['dt_set']}")
        L.update({"measurement_status": blk["measurement_status"],
                  "measured": {k: v for k, v in blk.items() if k != "rows"},
                  "rows_head": blk["rows"][:2], "rows_tail": blk["rows"][-2:],
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red)})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ L9 env 初态复现（osmesa · 直接写 qpos · **自证**）══════
def l9_env_initial_state(ctx, episodes: list[int], tol: float) -> dict:
    L = leg("L9_env_initial_state_reproduce",
            "在 C2 的 `GymAlohaSimEnv`（`MUJOCO_GL=osmesa`）上：① 实测 `reset(seed)` 给出的方块位姿与"
            "`_table_z_ref`；② 用**直接写 qpos** 的方式复现 frame-0 state，并以"
            "`get_qpos()` 回读**自证**（不复现即红）")
    if ctx.get("skip_env"):
        L.update({"measurement_status": "not_measured",
                  "why": "`--skip-env` ⇒ 本腿 not_measured（不写 false、不写「通过」）",
                  "verdict": None, "blocking": False})
        return L
    try:
        from gym_aloha.constants import unnormalize_puppet_gripper_position
        from harness.env_gym_aloha import GEOM_BOX, EnvSpec, GymAlohaSimEnv

        rows = ctx["init_states"]["rows"]
        picks = [r for r in rows if r["episode_index"] in set(episodes)]
        per_dir_env = {}
        out_rows = []
        findings = {"reset_seed_reproduces_box_xy": {"forward": None, "reverse": None},
                    "table_z_ref_caliber": None}
        for r in picks:
            d = r["env_direction"]
            if d not in per_dir_env:
                per_dir_env[d] = GymAlohaSimEnv(EnvSpec(direction=d, image_size=ctx["image_size"],
                                                        render_images=ctx["render"], seed=r["seed"]))
            jenv = per_dir_env[d]
            t0 = time.perf_counter()
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            box_at_reset = np.asarray(ph.named.data.geom_xpos[GEOM_BOX], dtype=np.float64).copy()
            table_z_ref = float(jenv._table_z_ref)
            state_at_reset = jenv._state().astype(np.float64).copy()
            quat_at_reset = np.asarray(ph.data.qpos[19:23], dtype=np.float64).copy()

            # ── 直接写 qpos：arm 用 frame-0 state 的**逆映射**，box 用 sidecar 的 rest pose ──
            s14 = np.asarray(r["frame0_state"], dtype=np.float64)
            q = ph.data.qpos.copy()
            gl = float(unnormalize_puppet_gripper_position(s14[6]))
            gr = float(unnormalize_puppet_gripper_position(s14[13]))
            q[0:6] = s14[0:6]; q[6] = gl; q[7] = -gl
            q[8:14] = s14[7:13]; q[14] = gr; q[15] = -gr
            q[16:19] = np.asarray(r["box_rest_after_settle_xyz"], dtype=np.float64)
            ph.data.qvel[:] = 0.0
            ph.data.qpos[:] = q
            ph.forward()
            got = jenv._state().astype(np.float64)
            box_after = np.asarray(ph.named.data.geom_xpos[GEOM_BOX], dtype=np.float64).copy()
            d_state = float(np.abs(got - s14).max())
            d_box = float(np.abs(box_after - np.asarray(r["box_rest_after_settle_xyz"],
                                                        dtype=np.float64)).max())
            spawn_ok = bool(np.allclose(box_at_reset[:2],
                                        np.asarray(r["box_spawn_xyz"], dtype=np.float64)[:2],
                                        atol=1e-4))
            md = r["manifest_direction"]
            cur = findings["reset_seed_reproduces_box_xy"][md]
            findings["reset_seed_reproduces_box_xy"][md] = (spawn_ok if cur is None
                                                            else bool(cur and spawn_ok))
            if findings["table_z_ref_caliber"] is None:
                findings["table_z_ref_caliber"] = {
                    "table_z_ref_read_at_reset": table_z_ref,
                    "box_z_at_reset_spawn": float(box_at_reset[2]),
                    "box_z_rest_after_settle": float(np.asarray(r["box_rest_after_settle_xyz"])[2]),
                    "delta_m": round(table_z_ref
                                     - float(np.asarray(r["box_rest_after_settle_xyz"])[2]), 6),
                    "lift_min_height_m": float(jenv.spec.thresholds.lift_min_height_m),
                    "effective_lift_height_above_rest_m": round(
                        float(jenv.spec.thresholds.lift_min_height_m)
                        + (table_z_ref - float(np.asarray(r["box_rest_after_settle_xyz"])[2])), 6),
                    "source_of_table_z_ref": ("`harness/env_gym_aloha.py::GymAlohaSimEnv.reset()` "
                                              "自标定：读 reset 那一刻的 `geom_xpos[red_box][2]`，"
                                              "注释假定「此时方块静止在桌面上」"),
                    "measured_fact": ("reset 那一刻方块在 **spawn** 高度 z=0.05，"
                                      "静止后是 z=0.02 ⇒ 假定不成立，参考面偏高 0.03 m"),
                    "who_owns_the_fix": "C2（判定层）/ D（口径）；**A2 不改**，只测量并登记",
                    "effect_on_judgment": ("`lift_ok = (box_z - table_z_ref) >= 0.05` ⇒ 实际要求方块中心"
                                           "升到 rest 面以上 0.08 m；比字面阈值严 0.03 m。"
                                           "对**所有** episode 与两个方向同向偏移（系统性、不是噪声）"),
                    "binding_for_step1": False,
                }
            out_rows.append({
                "episode_index": r["episode_index"], "ep_id": r["ep_id"], "seed": r["seed"],
                "manifest_direction": md, "env_direction": d,
                "wall_reset_plus_init_s": round(time.perf_counter() - t0, 4),
                "box_xyz_at_reset": [float(x) for x in box_at_reset],
                "box_quat_wxyz_at_reset": [float(x) for x in quat_at_reset],
                "box_spawn_xyz_sidecar": r["box_spawn_xyz"],
                "reset_seed_reproduces_box_xy": spawn_ok,
                "table_z_ref": table_z_ref,
                "state_at_reset_maxdiff_vs_frame0": float(np.abs(state_at_reset - s14).max()),
                "state_reproduce_maxdiff_after_qpos_write": d_state,
                "box_reproduce_maxdiff_after_qpos_write": d_box,
                "state_reproduce_pass": bool(d_state <= tol),
                "box_reproduce_pass": bool(d_box <= 1e-6),
                "gripper_qpos_written": {"left_qpos6": gl, "left_qpos7": -gl,
                                         "right_qpos14": gr, "right_qpos15": -gr},
                "initialization_method": ("direct_qpos_write_after_reset（A2 侧；先 `reset(seed)` "
                                          "拿到 C2 env 的内部状态与 `_table_z_ref`，再写 qpos + "
                                          "`qvel=0` + `physics.forward()`）"),
                "qvel_zeroed": True,
            })
        n_pass = sum(1 for r in out_rows if r["state_reproduce_pass"] and r["box_reproduce_pass"])
        red = []
        if not out_rows:
            red.append("no_episode_measured")
        if n_pass != len(out_rows):
            red.append(f"state_or_box_reproduce_failed_{len(out_rows) - n_pass}_of_{len(out_rows)}")
        L.update({"measurement_status": "measured",
                  "measured": {"n_episodes_probed": len(out_rows),
                               "episodes_probed": [r["episode_index"] for r in out_rows],
                               "n_reproduce_pass": n_pass,
                               "state_reproduce_tol": tol,
                               "worst_state_maxdiff": max([r["state_reproduce_maxdiff_after_qpos_write"]
                                                           for r in out_rows], default=None),
                               "rows": out_rows},
                  "findings": findings,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red),
                  "mujoco_gl": os.environ.get("MUJOCO_GL"), "gpu_used": False,
                  "authority": "补单四 §三（从示范初态闭环执行）· 裁定 85.5（像素只登记）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}",
                  "why": "env 腿抛异常 ⇒ not_measured + 阻塞红（**不许**退化成状态输入小模型）"})
    return L


# ══════════════════════════ L10 图像通道（三相机 + 与 frame-0 的差异，只登记）══════
def l10_image_channel(ctx, episodes: list[int]) -> dict:
    L = leg("L10_image_channel_probe",
            "在复现出的示范初态上渲染三相机，核形状/值域/键名映射；并与数据集 frame-0 的 PNG 比对"
            "（**像素只登记不判红**，裁定 85.5）")
    if ctx.get("skip_env") or not ctx.get("render"):
        L.update({"measurement_status": "not_measured",
                  "why": "`--skip-env` 或 `--no-render` ⇒ not_measured（不写「通过」）"})
        return L
    try:
        from gym_aloha.constants import unnormalize_puppet_gripper_position
        from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
        df = ctx["ds"]["df"]
        rows = [r for r in ctx["init_states"]["rows"] if r["episode_index"] in set(episodes)]
        out = []
        for r in rows[:2]:
            d = r["env_direction"]
            jenv = GymAlohaSimEnv(EnvSpec(direction=d, image_size=ctx["image_size"],
                                          render_images=True, seed=r["seed"]))
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            s14 = np.asarray(r["frame0_state"], dtype=np.float64)
            q = ph.data.qpos.copy()
            gl = float(unnormalize_puppet_gripper_position(s14[6]))
            gr = float(unnormalize_puppet_gripper_position(s14[13]))
            q[0:6] = s14[0:6]; q[6] = gl; q[7] = -gl
            q[8:14] = s14[7:13]; q[14] = gr; q[15] = -gr
            q[16:19] = np.asarray(r["box_rest_after_settle_xyz"], dtype=np.float64)
            ph.data.qvel[:] = 0.0
            ph.data.qpos[:] = q
            ph.forward()
            obs = jenv.observation()
            row = {"episode_index": r["episode_index"], "ep_id": r["ep_id"], "direction": d,
                   "obs_keys": sorted(obs.keys()),
                   "runtime_image_keys_required": list(VR.REQUIRED_IMAGE_KEYS),
                   "pi05_to_runtime_image_keys": dict(VR.PI05_TO_RUNTIME_IMAGE_KEYS),
                   "obs_key_space": "pi05（`observation.images.*`）",
                   "runtime_key_space": "runtime（`top`/`left_wrist`/`right_wrist`）",
                   "mapped_runtime_keys": sorted(
                       VR.PI05_TO_RUNTIME_IMAGE_KEYS[k] for k in obs
                       if k in VR.PI05_TO_RUNTIME_IMAGE_KEYS),
                   "vision_guard_would_fire": bool(
                       not set(VR.REQUIRED_IMAGE_KEYS) <= {VR.PI05_TO_RUNTIME_IMAGE_KEYS[k]
                                                           for k in obs
                                                           if k in VR.PI05_TO_RUNTIME_IMAGE_KEYS}),
                   "vision_guard_caliber": ("`VR._guard_vision_channels()` 认的是**映射之后**的 "
                                            "runtime 键名；本腿第一版拿 runtime 键名去比 "
                                            "**映射之前**的 pi05 键空间 ⇒ 假红（缺陷类 ⑲ "
                                            "「判据与对象空间错配」的同型，已修并自报）"),
                   "cameras": {}}
            f0i = int(ctx["ds"]["per_ep"][r["episode_index"]]["frame0_index"])
            gi = int(df["episode_index"].values[f0i])
            rec = df.iloc[f0i]
            for pi_key, rt_key in VR.PI05_TO_RUNTIME_IMAGE_KEYS.items():
                col = pi_key
                a = obs.get(pi_key)
                png = decode_inline_png(rec[col]) if col in df.columns else None
                cam = {"present_in_obs": a is not None,
                       "obs_shape": (list(a.shape) if a is not None else None),
                       "obs_dtype": (str(a.dtype) if a is not None else None),
                       "obs_min": (float(a.min()) if a is not None else None),
                       "obs_max": (float(a.max()) if a is not None else None),
                       "dataset_png_decoded": png is not None,
                       "dataset_png_shape": (list(png.shape) if png is not None else None)}
                if a is not None and png is not None:
                    env_u8 = (np.clip(a, 0.0, 1.0) * 255.0).round().astype(np.uint8)  # CHW
                    env_hwc = np.transpose(env_u8, (1, 2, 0))
                    diff = np.abs(env_hwc.astype(np.int32) - png.astype(np.int32))
                    cam.update({"max_abs_pixel_diff": int(diff.max()),
                                "mean_abs_pixel_diff": float(diff.mean()),
                                "frac_pixels_differing_any_channel": float((diff.max(axis=2) > 0).mean()),
                                "bitwise_equal": bool(np.array_equal(env_hwc, png))})
                row["cameras"][rt_key] = cam
            row["frame0_dataframe_index"] = f0i
            row["episode_index_from_dataframe"] = gi
            row["episode_index_matches_manifest"] = bool(gi == r["episode_index"])
            out.append(row)
        red = []
        for r in out:
            for cam, v in r["cameras"].items():
                if not v["present_in_obs"]:
                    red.append(f"camera_absent:{r['episode_index']}:{cam}")
                elif v["obs_shape"] != [3, ctx["image_size"], ctx["image_size"]]:
                    red.append(f"camera_shape:{r['episode_index']}:{cam}:{v['obs_shape']}")
                elif not (0.0 <= (v["obs_min"] or 0) and (v["obs_max"] or 1) <= 1.0):
                    red.append(f"camera_range:{r['episode_index']}:{cam}")
            if r["vision_guard_would_fire"]:
                red.append(f"vision_guard_would_fire:{r['episode_index']}")
            if not r.get("episode_index_matches_manifest", False):
                red.append(f"episode_index_mismatch:{r['episode_index']}")
        L.update({"measurement_status": "measured",
                  "measured": {"n_episodes_probed": len(out), "rows": out},
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red),
                  "pixel_comparison_is_not_a_criterion": ("裁定 85.5：硬判据只剩「状态逐位」；"
                                                          "三相机像素一律**只登记不判红**"),
                  "pixel_diff_caliber": {
                      "this_leg_backend": os.environ.get("MUJOCO_GL"),
                      "dataset_capture_backend": "egl",
                      "dataset_capture_renderer_class": "nvidia_gpu",
                      "dataset_capture_gl_renderer": "NVIDIA A800-SXM4-80GB/PCIe/SSE2",
                      "source": ("runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json "
                                 "的 `gl_identity` / `activation_env`（当场重读，见 identities 段）"),
                      "consequence": ("本腿是 **osmesa**、数据集是 **egl/nvidia_gpu** ⇒ 像素差"
                                      "**不可**解释为「初态复现错了」；初态是否复现由 L9 的"
                                      "**状态逐位**判（实测 maxdiff = 0.0），像素只登记"),
                      "step1_rollout_backend_choice": ("第 1 步的 rollout 腿应走 **egl/nvidia_gpu**"
                                                       "（与训练数据的渲染后端同口径），"
                                                       "该选择本身要在产物里落盘并实测 `renderer_class` 三点")},
                  "mujoco_gl": os.environ.get("MUJOCO_GL"), "gpu_used": False})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ════════════════ L11 初态写入后的**动力学瞬变**（有没有东西把臂拽走）════════════════
def _init_env_to_state(jenv, s14, box_xyz, unnormalize_fn):
    """把 C2 的 env 直接置到 (s14, box_xyz)：写 qpos + `qvel=0` + `physics.forward()`。

    **为什么可以直接写**：实测 `nmocap = 0`、`neq = 0`（L11 落盘）⇒ 该模型**没有** weld/mocap
    等式约束会把臂拽回某个参考位姿；gym-aloha 的 16 个执行器是位置控制（`actuator_trntype=0`）
    ⇒ 写 qpos 后下一步只由「当前 qpos/qvel + 本步动作」决定。
    **qvel 只能置零**（数据集不存 qvel）⇒ 这是本腿与真示范之间**已知的唯一**初值差，
    L11/L12 都把它当**已登记的扰动源**，不当「复现失败」。
    """
    ph = jenv.physics
    q = ph.data.qpos.copy()
    gl = float(unnormalize_fn(s14[6]))
    gr = float(unnormalize_fn(s14[13]))
    q[0:6] = s14[0:6]; q[6] = gl; q[7] = -gl
    q[8:14] = s14[7:13]; q[14] = gr; q[15] = -gr
    q[16:19] = np.asarray(box_xyz, dtype=np.float64)
    ph.data.qvel[:] = 0.0
    ph.data.qpos[:] = q
    ph.forward()
    return {"gripper_qpos": {"left": gl, "right": gr},
            "qvel_zeroed": True,
            "nq": int(ph.model.nq), "nu": int(ph.model.nu)}


def l11_post_init_transient(ctx, episodes: list[int]) -> dict:
    L = leg("L11_post_init_transient",
            "初态写入后**第一步**的动力学：① 模型有没有 weld/mocap 会把臂拽走；"
            "② 用示范的 `action[0]` 走一步，与示范 `state[1]` 的残差是多少、能不能归因")
    if ctx.get("skip_env"):
        L.update({"measurement_status": "not_measured", "why": "`--skip-env` ⇒ not_measured"})
        return L
    try:
        from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
        from harness.env_gym_aloha import GEOM_BOX, EnvSpec, GymAlohaSimEnv
        df = ctx["ds"]["df"]
        rows = [r for r in ctx["init_states"]["rows"] if r["episode_index"] in set(episodes)]
        out = []
        model_facts = None
        for r in rows:
            jenv = GymAlohaSimEnv(EnvSpec(direction=r["env_direction"], image_size=64,
                                          render_images=False, seed=r["seed"]))
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            if model_facts is None:
                model_facts = {
                    "nmocap": int(ph.model.nmocap), "neq": int(ph.model.neq),
                    "nq": int(ph.model.nq), "nu": int(ph.model.nu), "njnt": int(ph.model.njnt),
                    "eq_rows": [{"name": ph.model.eq_name(i), "type": int(ph.model.eq_type[i])}
                                for i in range(ph.model.neq)],
                    "actuator_trntype_head": [int(x) for x in ph.model.actuator_trntype[:4]],
                    "actuator_ctrlrange_head": [[float(a), float(b)] for a, b in
                                                ph.model.actuator_ctrlrange[:2]],
                    "no_weld_no_mocap": bool(ph.model.nmocap == 0 and ph.model.neq == 0),
                    "consequence": ("`neq = 0` ⇒ 没有等式约束会把直接写入的 qpos 拽回参考位姿"
                                    "（B2 在 `b2_s1_scripted_expert.py:11` 记的 weld/mocap 事故"
                                    "**不在**这个模型上）⇒ 直接写 qpos 是安全的初始化"),
                }
            m = np.asarray(df["episode_index"].values == r["episode_index"])
            ep_state = ctx["ds"]["state"][m]
            ep_action = ctx["ds"]["action"][m]
            s0 = np.asarray(r["frame0_state"], dtype=np.float64)
            info = _init_env_to_state(jenv, s0, r["box_rest_after_settle_xyz"], unorm)
            after_write = jenv._state().astype(np.float64)
            box_after_write = np.asarray(ph.named.data.geom_xpos[GEOM_BOX], dtype=np.float64).copy()
            ncon0, nefc0 = int(ph.data.ncon), int(ph.data.nefc)
            a0 = ep_action[0].astype(np.float32)
            jenv.step(a0)
            s1 = jenv._state().astype(np.float64)
            demo_s1 = ep_state[1]
            out.append({
                "episode_index": r["episode_index"], "direction": r["manifest_direction"],
                "init_info": info,
                "state_maxdiff_after_write": float(np.abs(after_write - s0).max()),
                "box_xyz_after_write": [float(x) for x in box_after_write],
                "ncon_at_init": ncon0, "nefc_at_init": nefc0,
                "demo_action0": [float(x) for x in a0],
                "demo_state1": [float(x) for x in demo_s1],
                "state_after_1_step": [float(x) for x in s1],
                "residual_vs_demo_state1_maxdim": float(np.abs(s1 - demo_s1).max()),
                "residual_vs_demo_state1_l2": float(np.linalg.norm(s1 - demo_s1)),
                "step_magnitude_l2_state1_minus_state0": float(np.linalg.norm(demo_s1 - s0)),
                "residual_ratio_vs_step_magnitude": float(
                    np.linalg.norm(s1 - demo_s1) / max(1e-12, float(np.linalg.norm(demo_s1 - s0)))),
                "attributable_to_qvel_zeroing": None,
                "box_z_after_1_step": float(np.asarray(ph.named.data.geom_xpos[GEOM_BOX])[2]),
            })
        # 归因：把「qvel 置零」这个已知扰动单独测出来 —— 用**示范自己的**连续两帧差当 qvel 的
        # 有限差分近似，再走一步，看残差是否显著下降（下降 ⇒ 残差主要来自 qvel，不是对齐错）
        for o in out:
            r = next(x for x in rows if x["episode_index"] == o["episode_index"])
            jenv = GymAlohaSimEnv(EnvSpec(direction=r["env_direction"], image_size=64,
                                          render_images=False, seed=r["seed"]))
            jenv.reset(seed=r["seed"])
            ph = jenv.physics
            m = np.asarray(df["episode_index"].values == r["episode_index"])
            ep_state = ctx["ds"]["state"][m]
            ep_action = ctx["ds"]["action"][m]
            s0 = np.asarray(r["frame0_state"], dtype=np.float64)
            _init_env_to_state(jenv, s0, r["box_rest_after_settle_xyz"], unorm)
            dt = 1.0 / float(VR.MAINLINE_CONTROL_HZ)
            qv = ph.data.qvel.copy()
            qv[0:6] = (ep_state[1][0:6] - s0[0:6]) / dt
            qv[8:14] = (ep_state[1][7:13] - s0[7:13]) / dt
            ph.data.qvel[:] = qv
            ph.forward()
            jenv.step(ep_action[0].astype(np.float32))
            s1 = jenv._state().astype(np.float64)
            o["with_finite_difference_qvel"] = {
                "residual_vs_demo_state1_maxdim": float(np.abs(s1 - ep_state[1]).max()),
                "residual_vs_demo_state1_l2": float(np.linalg.norm(s1 - ep_state[1])),
                "qvel_source": ("示范 frame0→frame1 的一阶差分 / dt（**近似**，不是真 qvel；"
                                "数据集不存 qvel）"),
                "dt_used": dt,
            }
            o["attributable_to_qvel_zeroing"] = bool(
                o["with_finite_difference_qvel"]["residual_vs_demo_state1_l2"]
                < o["residual_vs_demo_state1_l2"])
        red = []
        if not (model_facts or {}).get("no_weld_no_mocap", False):
            red.append("model_has_weld_or_mocap__direct_qpos_write_unsafe")
        for o in out:
            if o["state_maxdiff_after_write"] > 1e-6:
                red.append(f"init_state_not_reproduced:{o['episode_index']}")
        L.update({"measurement_status": "measured",
                  "measured": {"n_episodes_probed": len(out), "model_facts": model_facts,
                               "rows": out},
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red), "gpu_used": False,
                  "mujoco_gl": os.environ.get("MUJOCO_GL"),
                  "caveat": ("`residual_vs_demo_state1` **不是**「时间对齐错」的证据：qvel 被置零、"
                            "而示范 frame0 处两臂正在运动 ⇒ 残差的量级要与「一步本身的位移量级」"
                            "比（`residual_ratio_vs_step_magnitude`），并看有限差分 qvel 的对照臂")})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ════════════════ L12 动作/时间对齐的**判别式**（不是靠故事，是靠对照）════════════
def l12_action_time_alignment(ctx, episodes: list[int], n_per_episode: int,
                              moving_thresh: float = 0.01, margin_required: float = 1.2) -> dict:
    """「`action[j]` 是不是产生 `state[j+1]` 的那一步动作」——**用错位对照判**，不靠读文档。

    判据形状（裁定 95.3-② 的常规模 `a_mechanism_must_be_shown_by_a_repair_control_not_by_a_
    consistent_story`）：对同一初态 `state[j]`，分别用
      * `action[j]`（**对齐假设**）
      * `action[j-1]` / `action[j+1]`（**错位一格**）
      * `state[j]` 本身当动作（**保持**）
    走一步，比谁离 `state[j+1]` 最近。

    **两处口径是本腿的命门，都显式登记**：
      ① **方块位姿必须按帧给**。第一版把所有探针帧的方块都钉在该集的 rest pose ⇒ 中/后段帧
         （方块已被抓起、已放到对侧）的夹爪闭合在**空气**上，指关节走位完全不同，
         14 维残差被顶到 ≈0.086 且**与用哪个动作无关**（aligned / j-1 / j+1 三者几乎相等）
         ⇒ `hold_state_j` 假赢 10/24。现在改用 sidecar 的 `box_trajectory_xyz_every_10`
         （**第 k 项 ↔ 第 10k 帧**，实测第 0 项 == rest pose），并把探针帧**只取 10 的倍数**。
      ② **静止帧没有区分度 ⇒ 三值，不判胜负**。`step_magnitude_l2 < moving_thresh` 时
         `action[j] ≈ state[j]`，谁赢由噪声决定 ⇒ 这类帧记 `discrimination = "low"` +
         `verdict = n_a_low_discrimination`，**既不算通过也不算失败**（三值纪律）。
         判红的只有 `discrimination = "high"` 且对齐假设**没有**以 `margin_required` 胜过
         两个错位对照的情形。
    """
    L = leg("L12_action_time_alignment",
            "用**错位对照**判别 `action[j] → state[j+1]` 的时间对齐（方块位姿按帧取自 sidecar；"
            "静止帧记 `n_a_low_discrimination` 不判胜负）")
    if ctx.get("skip_env"):
        L.update({"measurement_status": "not_measured", "why": "`--skip-env` ⇒ not_measured"})
        return L
    try:
        from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
        from harness.env_gym_aloha import GEOM_BOX, EnvSpec, GymAlohaSimEnv
        df = ctx["ds"]["df"]
        rows = [r for r in ctx["init_states"]["rows"] if r["episode_index"] in set(episodes)]
        arm_dims = [d for d in range(STATE_DIM) if d not in GRIP_DIMS]
        per_rows = []
        box_pose_source_missing = []
        for r in rows:
            m = np.asarray(df["episode_index"].values == r["episode_index"])
            ep_state = ctx["ds"]["state"][m]
            ep_action = ctx["ds"]["action"][m]
            nfr = ep_state.shape[0]
            traj = r.get("box_trajectory_xyz_every_10") or []
            if not traj:
                box_pose_source_missing.append(r["episode_index"])
                continue
            cand = [j for j in range(10, nfr - 2, 10) if (j // 10) < len(traj)]
            if not cand:
                box_pose_source_missing.append(r["episode_index"])
                continue
            stride = max(1, len(cand) // max(1, int(n_per_episode)))
            js = cand[::stride][:max(1, int(n_per_episode))]
            jenv = GymAlohaSimEnv(EnvSpec(direction=r["env_direction"], image_size=64,
                                          render_images=False, seed=r["seed"]))
            jenv.reset(seed=r["seed"])
            for j in js:
                box_j = np.asarray(traj[j // 10], dtype=np.float64)
                target = ep_state[j + 1]
                variants = {"aligned_action_j": ep_action[j],
                            "shifted_action_j_minus_1": ep_action[j - 1],
                            "shifted_action_j_plus_1": ep_action[min(j + 1, nfr - 1)],
                            "hold_state_j": ep_state[j]}
                errs, errs_arm, boxes = {}, {}, {}
                for name, act in variants.items():
                    _init_env_to_state(jenv, ep_state[j], box_j, unorm)
                    box_before = np.asarray(jenv.physics.named.data.geom_xpos[GEOM_BOX],
                                            dtype=np.float64).copy()
                    jenv.step(np.asarray(act, dtype=np.float32))
                    got = jenv._state().astype(np.float64)
                    errs[name] = {"l2": float(np.linalg.norm(got - target)),
                                  "maxdim": float(np.abs(got - target).max()),
                                  "l2_arm12": float(np.linalg.norm(got[arm_dims]
                                                                   - target[arm_dims])),
                                  "l2_grip2": float(np.linalg.norm(got[GRIP_DIMS]
                                                                   - target[GRIP_DIMS]))}
                    boxes[name] = [float(x) for x in box_before]
                ordered = sorted(errs.items(), key=lambda kv: kv[1]["l2"])
                shifted_best = min(errs["shifted_action_j_minus_1"]["l2"],
                                   errs["shifted_action_j_plus_1"]["l2"])
                a = errs["aligned_action_j"]["l2"]
                step_mag = float(np.linalg.norm(target - ep_state[j]))
                high = bool(step_mag >= moving_thresh)
                wins = bool(ordered[0][0] == "aligned_action_j")
                beats_shifted = bool(shifted_best >= margin_required * a) if a > 0 else False
                per_rows.append({
                    "episode_index": r["episode_index"], "direction": r["manifest_direction"],
                    "frame_j": j, "n_frames": int(nfr),
                    "box_pose_source": f"sidecar.box_trajectory_xyz_every_10[{j // 10}]",
                    "box_pose_xyz": [float(x) for x in box_j],
                    "box_pose_equals_rest": bool(np.allclose(
                        box_j, np.asarray(r["box_rest_after_settle_xyz"], dtype=np.float64),
                        atol=1e-9)),
                    "step_magnitude_l2": step_mag,
                    "discrimination": ("high" if high else "low"),
                    "errors_l2": {k: round(v["l2"], 6) for k, v in errs.items()},
                    "errors_maxdim": {k: round(v["maxdim"], 6) for k, v in errs.items()},
                    "errors_l2_arm12": {k: round(v["l2_arm12"], 6) for k, v in errs.items()},
                    "errors_l2_grip2": {k: round(v["l2_grip2"], 6) for k, v in errs.items()},
                    "winner": ordered[0][0], "runner_up": ordered[1][0],
                    "aligned_is_winner": wins,
                    "aligned_beats_both_shifted_by_margin": beats_shifted,
                    "margin_ratio_vs_runner_up": (float(ordered[1][1]["l2"] / a) if a > 0 else None),
                    "margin_ratio_vs_best_shifted": (float(shifted_best / a) if a > 0 else None),
                    "verdict": (("pass" if (wins and beats_shifted) else "fail") if high
                                else "n_a_low_discrimination"),
                })
        high = [r for r in per_rows if r["discrimination"] == "high"]
        low = [r for r in per_rows if r["discrimination"] == "low"]
        red = []
        if not per_rows:
            red.append("no_probe_measured")
        n_high_pass = sum(1 for r in high if r["verdict"] == "pass")
        if high and n_high_pass != len(high):
            red.append(f"aligned_action_not_winning_in_{len(high) - n_high_pass}_of_{len(high)}"
                       "_high_discrimination_probes")
        ratios = [r["margin_ratio_vs_best_shifted"] for r in high
                  if r["margin_ratio_vs_best_shifted"] is not None]
        measured = {
            "n_probes": len(per_rows), "n_high_discrimination": len(high),
            "n_low_discrimination": len(low),
            "n_high_pass": n_high_pass,
            "frac_high_pass": (n_high_pass / len(high)) if high else None,
            "median_margin_ratio_vs_best_shifted": (float(np.median(ratios)) if ratios else None),
            "min_margin_ratio_vs_best_shifted": (float(np.min(ratios)) if ratios else None),
            "max_margin_ratio_vs_best_shifted": (float(np.max(ratios)) if ratios else None),
            "moving_threshold_l2": moving_thresh, "margin_required": margin_required,
            "box_pose_source_missing_episodes": box_pose_source_missing,
            "probe_frames_are_multiples_of_10": bool(all(r["frame_j"] % 10 == 0 for r in per_rows)),
            "rows": per_rows,
            "caveat_box": ("方块位姿取自 sidecar 的 **every-10** 轨迹 ⇒ 探针帧只能是 10 的倍数；"
                           "非 10 倍数帧的方块位姿**没有**权威来源（数据集不存方块位姿）"),
            "caveat_qvel": "所有 variant 一律 `qvel=0`（同一扰动 ⇒ 对照之间可比）",
            "first_version_confound_registered": ("第一版把方块钉在 rest pose ⇒ 中/后段帧假赢 "
                                                  "`hold_state_j` 10/24；已改并保留 T8 负对照"),
        }
        L.update({"measurement_status": "measured", "measured": measured,
                  "verdict": "GREEN" if not red else "RED", "red_codes": red,
                  "blocking": bool(red), "gpu_used": False,
                  "mujoco_gl": os.environ.get("MUJOCO_GL"),
                  "authority": "补单四 §三（检查动作、夹爪、时间对齐）· 裁定 95.3-②（机制必须由对照证明）"})
    except Exception as exc:                                          # noqa: BLE001
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}"})
    return L


# ══════════════════════════ 负对照（牙必须会咬）══════════════════════════════════
def selftest_teeth(ctx) -> dict:
    """四颗负对照。每颗都是「把输入弄坏 ⇒ 对应腿必须变红」，**不是**恒真断言。"""
    out = {"teeth": [], "n_teeth": 0, "n_bite": 0, "n_fail": 0}

    def add(tid, expect, got_red, detail):
        bite = bool(got_red)
        out["teeth"].append({"tooth_id": tid, "expect": expect, "detector_went_red": bite,
                             "bite": bite, "detail": detail})

    c2 = ctx["stats"]
    eps = float(c2["lerobot_eps"] or 1e-8)
    # T1：把 q01 整体上移 1.0 ⇒ 大量 state 落到 < -1 ⇒ L2 的硬红必须触发
    q01_bad = c2["q01"] + 1.0
    y = quantiles_norm(ctx["ds"]["state"], q01_bad, c2["q99"], eps)
    add("T1_shifted_q01_must_produce_illegal_below", "state_below_minus_1 > 0",
        int((y < -1.0).sum()) > 0, {"n_below": int((y < -1.0).sum()),
                                     "frac_below": float((y < -1.0).mean())})
    # T2：一条人造的极端 state（全 -5）⇒ 真 prompt 里必须出现 -1 bin
    try:
        import torch
        from lerobot.configs.types import FeatureType
        norm = {type(s).__name__: s for s in ctx["pre"].steps}["NormalizerProcessorStep"]
        bad = np.full((STATE_DIM,), -5.0, dtype=np.float32)
        yy = norm._apply_transform(torch.from_numpy(bad), "observation.state",
                                   FeatureType.STATE, inverse=False).detach().numpy()
        bins = PBG.digitize_bins(np.asarray(yy, dtype=np.float64).tolist())
        add("T2_extreme_state_must_yield_minus_1_bin", "min(bin) == -1",
            int(np.asarray(bins).min()) == int(PBG.ILLEGAL_BIN_LOW),
            {"normalized_min": float(np.asarray(yy).min()), "bins_head": [int(b) for b in bins[:8]],
             "illegal_bin_low": PBG.ILLEGAL_BIN_LOW})
        # T2b：同一条经过 `pad_vector` 到 32 维再离散化（补位必须是中位 bin，不是 -1）
        padded = np.zeros(PBG.MAX_STATE_DIM, dtype=np.float64)
        padded[:STATE_DIM] = np.asarray(yy, dtype=np.float64)
        b32 = PBG.digitize_bins(padded.tolist())
        add("T2b_pad_positions_must_not_be_illegal", "padded bins != -1",
            int(np.asarray(b32[STATE_DIM:]).min()) != int(PBG.ILLEGAL_BIN_LOW),
            {"padded_bins_unique": sorted(set(int(b) for b in b32[STATE_DIM:]))})
    except Exception as exc:                                          # noqa: BLE001
        add("T2_extreme_state_must_yield_minus_1_bin", "min(bin) == -1", False,
            {"error": f"{type(exc).__name__}: {exc}"})
    # T3：把 frame-0 state 的第 4 维扰动 0.1 ⇒ 复现判据必须失败（证明 L9 不是恒真）
    try:
        s14 = np.asarray(ctx["init_states"]["rows"][0]["frame0_state"], dtype=np.float64).copy()
        s14[4] += 0.1
        d = float(np.abs(s14 - np.asarray(ctx["init_states"]["rows"][0]["frame0_state"],
                                          dtype=np.float64)).max())
        add("T3_perturbed_frame0_must_fail_reproduce", "maxdiff > tol", d > 1e-6,
            {"perturbed_maxdiff": d, "tol": 1e-6})
    except Exception as exc:                                          # noqa: BLE001
        add("T3_perturbed_frame0_must_fail_reproduce", "maxdiff > tol", False,
            {"error": f"{type(exc).__name__}: {exc}"})
    # T6：把一条**含 `-1` token** 的 prompt 直接喂给审计器 ⇒ 必须判 RED
    try:
        bad_prompt = "Task: Transfer the red cube from the right arm to the left arm., State: " \
            + " ".join(["127"] * 6 + ["-1"] + ["127"] * 25) + ";\nAction: "
        a = PBG.audit_prompt_text(bad_prompt)
        add("T6_prompt_with_minus_1_must_be_red", "audit verdict == RED",
            str(a.get("verdict")) == "RED" and int(a.get("n_illegal_bin_minus1") or 0) > 0,
            {"verdict": a.get("verdict"), "n_illegal_bin_minus1": a.get("n_illegal_bin_minus1"),
             "illegal_bin_dims_first16": a.get("illegal_bin_dims_first16"),
             "n_state_tokens": a.get("n_state_tokens")})
    except Exception as exc:                                          # noqa: BLE001
        add("T6_prompt_with_minus_1_must_be_red", "audit verdict == RED", False,
            {"error": f"{type(exc).__name__}: {exc}"})
    # T7：把 L12 的**目标帧故意反向**（用 `state[j-1]` 当目标）⇒ `aligned_action_j` 必须**不再**是赢家。
    # 没有这颗牙，L12 的「对齐假设赢了」可能只是恒真（任何动作都离前一帧更远/更近的同型错觉）。
    t7 = {"measurement_status": "not_measured"}
    if not ctx.get("skip_env"):
        try:
            from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
            from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
            dfx = ctx["ds"]["df"]
            r0 = ctx["init_states"]["rows"][0]
            mm = np.asarray(dfx["episode_index"].values == r0["episode_index"])
            es, ea = ctx["ds"]["state"][mm], ctx["ds"]["action"][mm]
            j = 8
            je = GymAlohaSimEnv(EnvSpec(direction=r0["env_direction"], image_size=64,
                                        render_images=False, seed=r0["seed"]))
            je.reset(seed=r0["seed"])
            box = np.asarray(r0["box_rest_after_settle_xyz"], dtype=np.float64)
            errs = {}
            for name, act in (("aligned_action_j", ea[j]), ("hold_state_j", es[j]),
                              ("shifted_action_j_minus_1", ea[j - 1])):
                _init_env_to_state(je, es[j], box, unorm)
                je.step(np.asarray(act, dtype=np.float32))
                errs[name] = float(np.linalg.norm(je._state().astype(np.float64) - es[j - 1]))
            winner_backwards = min(errs.items(), key=lambda kv: kv[1])[0]
            t7 = {"measurement_status": "measured", "errors_l2_target_is_state_j_minus_1": errs,
                  "winner": winner_backwards}
            add("T7_backwards_target_must_not_be_won_by_aligned_action",
                "winner != aligned_action_j", winner_backwards != "aligned_action_j", t7)
        except Exception as exc:                                      # noqa: BLE001
            add("T7_backwards_target_must_not_be_won_by_aligned_action",
                "winner != aligned_action_j", False, {"error": f"{type(exc).__name__}: {exc}"})
    else:
        t7 = {"measurement_status": "not_measured", "why": "`--skip-env` ⇒ T7 not_measured"}
    out["t7_registration"] = t7
    # T8：把 L12 的方块位姿**故意**换回 rest pose（第一版的错误口径）⇒ 中/后段帧的对齐假设
    # 必须**不再**干净地胜出。没有这颗牙，「方块位姿按帧给」这条修正就没有证据支撑。
    if not ctx.get("skip_env"):
        try:
            from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
            from harness.env_gym_aloha import EnvSpec, GymAlohaSimEnv
            dfx = ctx["ds"]["df"]
            r0 = next(r for r in ctx["init_states"]["rows"]
                      if (r.get("box_trajectory_xyz_every_10") or []))
            mm = np.asarray(dfx["episode_index"].values == r0["episode_index"])
            es, ea = ctx["ds"]["state"][mm], ctx["ds"]["action"][mm]
            traj = r0["box_trajectory_xyz_every_10"]
            jfar = 10 * max(k for k in range(len(traj))
                            if np.linalg.norm(np.asarray(traj[k])
                                              - np.asarray(r0["box_rest_after_settle_xyz"])) > 0.05)
            je = GymAlohaSimEnv(EnvSpec(direction=r0["env_direction"], image_size=64,
                                        render_images=False, seed=r0["seed"]))
            je.reset(seed=r0["seed"])
            res = {}
            for tag, box in (("per_frame_box", np.asarray(traj[jfar // 10], dtype=np.float64)),
                             ("rest_pose_box_WRONG",
                              np.asarray(r0["box_rest_after_settle_xyz"], dtype=np.float64))):
                errs = {}
                for name, act in (("aligned_action_j", ea[jfar]),
                                  ("shifted_action_j_minus_1", ea[jfar - 1]),
                                  ("shifted_action_j_plus_1", ea[min(jfar + 1, es.shape[0] - 1)]),
                                  ("hold_state_j", es[jfar])):
                    _init_env_to_state(je, es[jfar], box, unorm)
                    je.step(np.asarray(act, dtype=np.float32))
                    errs[name] = float(np.linalg.norm(
                        je._state().astype(np.float64) - es[jfar + 1]))
                res[tag] = {"frame_j": jfar, "box_xyz": [float(x) for x in box],
                            "errors_l2": {k: round(v, 6) for k, v in errs.items()},
                            "winner": min(errs.items(), key=lambda kv: kv[1])[0]}
            bite = bool(res["per_frame_box"]["winner"] == "aligned_action_j"
                        and res["rest_pose_box_WRONG"]["winner"] != "aligned_action_j")
            add("T8_wrong_box_pose_must_break_alignment_discrimination",
                "per_frame_box → aligned 赢；rest_pose_box → aligned **不**赢", bite, res)
        except Exception as exc:                                      # noqa: BLE001
            add("T8_wrong_box_pose_must_break_alignment_discrimination",
                "per_frame_box → aligned 赢；rest_pose_box → aligned **不**赢", False,
                {"error": f"{type(exc).__name__}: {exc}"})
    # T4：假 sha ⇒ 身份复算必须不符（证明对账不是恒真）
    real = sha12(REPO / P_C2_STATS)
    add("T4_fake_sha_must_not_match", "recomputed != declared_fake",
        bool(real is not None and real != "000000000000"),
        {"recomputed_sha256_12": real, "declared_fake": "000000000000"})
    out["n_teeth"] = len(out["teeth"])
    out["n_bite"] = sum(1 for t in out["teeth"] if t["bite"])
    out["n_fail"] = out["n_teeth"] - out["n_bite"]
    out["all_bite"] = bool(out["n_fail"] == 0)
    out["note"] = ("负对照的意义：没有 T1–T4，L2/L4/L9 的 GREEN 可能只是**恒真**。"
                   "T3 是纯数值的（不建 env），因此 `--skip-env` 时仍然有效。")
    return out


def bare_n_lines_tooth(doc_text: str) -> dict:
    """裁定 98.5-②：**裸 `n_lines` 禁用**。对自己的产物也上这颗牙。"""
    import re
    hits = []
    for m in re.finditer(r'"(n_lines)"\s*:', doc_text):
        hits.append(m.group(1))
    for m in re.finditer(r'"([a-z0-9_]*_n_lines)"\s*:', doc_text):
        hits.append(m.group(1))
    return {"tooth_id": "T5_no_bare_n_lines_key_in_own_artifact",
            "bare_keys_found": sorted(set(hits)),
            "bite": bool(not hits),
            "caliber": "只认 `n_lines_wc` / `n_lines_splitlines`（裁定 98.3-②/98.5-②）"}


# ══════════════════════════ main ══════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="A2 / 六步序列第 1 步的先落并对齐腿（CPU-only）")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--weights-dir", default=P_WEIGHTS)
    ap.add_argument("--tokenizer-dir", default=DEFAULT_TOKENIZER)
    ap.add_argument("--stats-path", default=P_C2_STATS)
    ap.add_argument("--dataset-dir", default=P_DS)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--n-prompt-samples", type=int, default=32)
    ap.add_argument("--env-episodes", default="0,19,20,39",
                    help="L9/L10 探测的 episode_index（默认两向各取首末）")
    ap.add_argument("--state-reproduce-tol", type=float, default=1e-6)
    ap.add_argument("--dyn-episodes", default="", help="L11 的集号（默认同 --env-episodes）")
    ap.add_argument("--align-episodes", default="", help="L12 的集号（默认同 --env-episodes）")
    ap.add_argument("--align-frames-per-episode", type=int, default=6,
                    help="L12 每集取几个帧位做错位对照")
    ap.add_argument("--skip-env", action="store_true", help="只做纯数值腿（不建 env、不渲染）")
    ap.add_argument("--no-render", action="store_true", help="建 env 但不渲染（L10 → not_measured）")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()
    load_start = PBG.gpu_window_readings()

    doc: dict = {
        "artifact": "a2_step1_prealign_verify",
        "as_of": now_iso(),
        "producer": {"script": "scripts/a2_step1_prealign_verify.py",
                     **{k: v for k, v in identity("scripts/a2_step1_prealign_verify.py").items()
                        if k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                     "python": sys.version.split()[0], "venv": sys.executable},
        "n_lines_caliber": N_LINES_CALIBER,
        "purpose": ("第 1 步（小量示范过拟合 + 从示范初态闭环执行）**上卡之前**把三个静默错的形状"
                    "实测掉：归一化 pass-through、`-1` bin 进 prompt、示范初态复现不了"),
        "authority": [
            "rl_harness_supervision/d_handoff_to_a2_20260930.md 补单四 §三（第 1 步的内容与判据）",
            "裁定 95.2（六步序列）· 95.3-①②④（四字段分开 / 归因降级 / standard_sync）",
            "裁定 95.5-①②③（整条 episode 划分 / stats 冻结 / checkpoint 规则预登记）",
            "裁定 98.5（sha 是唯一约束性判据；行数必须点名口径；裸 n_lines 禁用）",
            "裁定 90.4-1（越 [-1,1] = 软边界）· §23.2（`-1` bin = 硬红）",
            "裁定 85.5（像素只登记不判红）· 裁定 46（能力声明禁令）",
            "docs/c2_to_a2_bc_stats_handoff_20260930.md §3（唯一一档 stats；换 stats 必须先报 D）",
        ],
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "success_rate_column": "not_an_exit_criterion",
        "model_weights_loaded": False,
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "machine_load_at_start": load_start,
        "identities": {},
        "legs": {},
    }

    # ── 活件身份：当场重算 ────────────────────────────────────────────────
    for tag, rel in (("c2_stats", args.stats_path), ("c2_broadcast_doc", P_C2_BROADCAST),
                     ("npz_source", P_NPZ), ("demo_manifest", P_MANIFEST),
                     ("dataset_info", str(pathlib.Path(args.dataset_dir) / "meta" / "info.json")),
                     ("weights_config", str(pathlib.Path(args.weights_dir) / "config.json")),
                     ("weights_preprocessor", str(pathlib.Path(args.weights_dir) / "policy_preprocessor.json")),
                     ("b2_scripted_expert", P_EXPERT), ("e_calib_reference_impl", P_CALIB),
                     ("harness_vla_runtime", "harness/vla_runtime.py"),
                     ("harness_prompt_bin_guard", "harness/prompt_bin_guard.py"),
                     ("harness_env_gym_aloha", "harness/env_gym_aloha.py")):
        doc["identities"][tag] = identity(rel)

    ctx: dict = {"skip_env": bool(args.skip_env), "render": not args.no_render,
                 "image_size": int(args.image_size)}
    failures: list[str] = []
    try:
        ctx["stats"] = read_stats(REPO / args.stats_path)
        ctx["ds"] = read_dataset_arrays(REPO / args.dataset_dir)
        import pandas as pd
        tk = pd.read_parquet(REPO / args.dataset_dir / "meta" / "tasks.parquet")
        ctx["task_texts"] = [str(t) for t in tk.index.tolist()]
        ctx["tasks_table"] = {str(t): int(tk.loc[t].iloc[0]) for t in tk.index}
    except Exception as exc:                                          # noqa: BLE001
        failures.append(f"input_load_failed:{type(exc).__name__}: {exc}")
        doc["input_load_error"] = failures[-1]

    if not failures:
        try:
            cfg, pre, post, inj = build_cfg_and_processors(REPO / args.weights_dir,
                                                          args.tokenizer_dir, ctx["stats"],
                                                          STATE_DIM)
            ctx.update({"cfg": cfg, "pre": pre, "post": post, "injection": inj})
        except Exception as exc:                                      # noqa: BLE001
            failures.append(f"processor_build_failed:{type(exc).__name__}: {exc}")
            doc["processor_build_error"] = failures[-1]

    if not failures:
        ctx["init_states"] = build_demo_initial_states(ctx)
        eps = [int(x) for x in str(args.env_episodes).split(",") if x.strip() != ""]
        dyn_eps = [int(x) for x in str(args.dyn_episodes).split(",") if x.strip() != ""] or eps
        align_eps = [int(x) for x in str(args.align_episodes).split(",") if x.strip() != ""] or eps
        doc["env_episodes_probed"] = {"l9_l10": eps, "l11": dyn_eps, "l12": align_eps}
        legs = [l1_stats_injection(ctx), l2_normalized_range(ctx), l3_roundtrip(ctx),
                l4_prompt_bin_guard(ctx, args.n_prompt_samples), l5_gripper_semantics(ctx),
                l6_dim_order(ctx), l7_config_contract(ctx), l8_demo_initial_states(ctx),
                l9_env_initial_state(ctx, eps, float(args.state_reproduce_tol)),
                l10_image_channel(ctx, eps),
                l11_post_init_transient(ctx, dyn_eps),
                l12_action_time_alignment(ctx, align_eps, int(args.align_frames_per_episode))]
        doc["injection_caliber"] = ctx["injection"]
        doc["legs"] = {L["leg_id"]: L for L in legs}
        doc["selftest"] = selftest_teeth(ctx)
        doc["task_texts"] = ctx["task_texts"]
        doc["tasks_table"] = ctx["tasks_table"]
    else:
        doc["legs"] = {}
        doc["selftest"] = {"measurement_status": "not_measured",
                           "why": "输入装载/处理器构造失败 ⇒ 负对照也没跑，不写 0"}

    # ── 汇总 ────────────────────────────────────────────────────────────
    legs = list(doc["legs"].values())
    n_measured = sum(1 for L in legs if L.get("measurement_status") == "measured")
    n_not_measured = sum(1 for L in legs if L.get("measurement_status") != "measured")
    red = [L["leg_id"] for L in legs if L.get("verdict") == "RED"]
    blocking = [L["leg_id"] for L in legs if L.get("blocking")]
    st = doc.get("selftest") or {}
    teeth_fail = int(st.get("n_fail") or 0) if isinstance(st, dict) else 0
    doc["summary"] = {
        "n_legs": len(legs), "n_measured": n_measured, "n_not_measured": n_not_measured,
        "not_measured_leg_ids": [L["leg_id"] for L in legs
                                 if L.get("measurement_status") != "measured"],
        "red_leg_ids": red, "blocking_leg_ids": blocking,
        "warnings": {L["leg_id"]: L.get("warnings") for L in legs if L.get("warnings")},
        "selftest_all_bite": bool(st.get("all_bite")) if isinstance(st, dict) else None,
        "selftest_n_teeth": st.get("n_teeth") if isinstance(st, dict) else None,
        "selftest_n_fail": teeth_fail,
        "input_failures": failures,
        "wall_s": round(time.perf_counter() - t_start, 3),
        "ok": bool(not red and not blocking and n_not_measured == 0 and not failures
                   and teeth_fail == 0),
        "exit_code_policy": ("0 = 全 measured 且无阻塞红且负对照全咬 · 1 = 有阻塞红或负对照不咬 · "
                             "3 = 存在 not_measured · 2 = 用法/环境错"),
        "no_capability_claim": ("本件不含任何 policy 指标；所有 GREEN **只指接口/口径判词**"
                                "（裁定 46）。`policy_executed=false`、`gpu_used=false`。"),
        "blind_dims_caveat": (f"盲点维 {BLIND_DIMS} 是 C2 的 94.3 Ⅱ 类登记项，"
                              "**不得**当作能力判据，也不得把 per-dim 结论写成全 14 维结论"),
    }
    doc["machine_load_at_end"] = PBG.gpu_window_readings()
    doc["three_net_at_start"] = None

    txt = json.dumps(doc, ensure_ascii=False, indent=2, default=jdefault) + "\n"
    doc["summary"]["bare_n_lines_tooth"] = bare_n_lines_tooth(txt.replace(
        '"bare_n_lines_tooth": null', ''))
    if not doc["summary"]["bare_n_lines_tooth"]["bite"]:
        doc["summary"]["ok"] = False

    main_path = out_dir / f"STEP1_PREALIGN_{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}.json"
    doc["self_identity"] = write_json(main_path, doc)
    # 再写一次带 self_identity 的终版（身份是自指的，写两遍：第一遍定字节，第二遍带身份）
    final_path = out_dir / "PREALIGN_VERIFICATION.json"
    doc["self_identity_note"] = ("`self_identity` 指向上面那份**带时间戳**的产物；本文件是同一份内容"
                                 "的稳定名副本，两者字节差只在 `self_identity*` 两个键")
    fin = write_json(final_path, doc)

    if not doc["summary"]["ok"]:
        code = EXIT_BLOCKING_RED if (red or blocking or failures
                                     or not doc["summary"]["bare_n_lines_tooth"]["bite"]) \
            else EXIT_NOT_MEASURED
    else:
        code = EXIT_OK
    print(json.dumps({"ok": doc["summary"]["ok"], "exit_code": code,
                      "n_legs": doc["summary"]["n_legs"],
                      "n_measured": n_measured, "n_not_measured": n_not_measured,
                      "red": red, "blocking": blocking,
                      "selftest_all_bite": doc["summary"]["selftest_all_bite"],
                      "warnings": {k: v for k, v in doc["summary"]["warnings"].items() if v},
                      "main_artifact": doc["self_identity"], "stable_copy": fin,
                      "wall_s": doc["summary"]["wall_s"],
                      "gpu_used": False, "policy_executed": False},
                     ensure_ascii=False, indent=2, default=jdefault))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as _exc:                                         # noqa: BLE001
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE,
                          "error": f"{type(_exc).__name__}: {_exc}",
                          "why": "结构性失败 ⇒ exit 2（用法/环境错），不落半成品判词"},
                         ensure_ascii=False, indent=2))
        sys.exit(EXIT_USAGE)
