#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 / **R1 + R2** —— L12 的两条残差腿（裁定 99.2 的 H1/H2/H3 → 裁定 100.1 点名的 R1/R2）。

CPU-only · `MUJOCO_GL=osmesa` · `gpu_used=false` · `policy_executed=false` · **不加载权重**
（`PI05Policy.from_pretrained` 一次都不调）。派工出处：
`rl_harness_supervision/d_handoff_to_a2_20260930.md` **补单六 §二（R1）/ §三（R2）/ §四（判据可核性）**
＝ `work/decisions/decisions_20260929.md` **§99.2 / §100.1 / §100.3 / §100.8-A2-①②③**。

## 一、为什么还要这一腿（`run4` 不是已经绿了吗）
`run4` 把 L12 的阻塞红解释掉了（根因 = 探针把方块钉在 rest pose，H3 成立；D 亲核 + 独立复算，
`decisions` §100.1）。但 D 点名**两条残差腿**，都不是 `run4` 能覆盖的：

* **R1（H2 尚未排除）**：`run3` 唯一输给 `shifted_action_j_plus_1` 的那一帧是整套探针里
  **全 14 维运动量最大**的一帧（ep20 reverse f56、`step_magnitude_l2 = 0.08199`、差 **3.48×**）；
  而 `run4` 的帧**只能是 10 的倍数**（sidecar 的方块轨迹是 every-10，已登成 `caveat_box`）⇒
  `(ep, frame)` 与 `run3` 的交集 = **空集**，`run4` 的最大运动量只有 **0.04401**。
  **⇒ 不是"已排除"，是"没测到"。**
* **R2（夹爪维时序尚未成立）**：`grip2` 逐行 argmin，aligned 只有 **7/24**（`j-1` 9 · `j+1` 6 · `hold` 2），
  但**聚合**口径 aligned 最好（求和 aligned 0.03863 < `j+1` 0.07263 < `j-1` 0.08118 < `hold` 0.10412）。
  ⇒ 精确表述是**「聚合上对齐、逐帧转变点上不明确」**，材料性分歧集中在 **f50–f130**。
  这是**第 2 步**的真前置：若 dim6/dim13 的监督在抓/放那一刻差一帧，BC 会学出"晚一帧合爪"，
  而它**看起来像策略失败**（用户 09-30 方向分析点名的正是这个混淆）。

## 二、本腿开工前先用纯数值测出来的一件事（它决定 R1 的分层量，必须写在判据前面）
`run3`/`run4` 排序用的 `step_magnitude_l2` 是**全 14 维**的 L2。本腿实测 ep20 reverse f56：

    mag14 = 0.08199 · 其中 grip2 = 0.08187（**占 99.9%**）· arm12 = 0.00439

⇒ **那一帧在臂侧 12 维上其实是低运动量帧**；`run3` 在 f56 上的 `j+1` 胜出**只可能**由夹爪维承载。
所以：
1. **R1 的分层量改为 `arm12` 运动量**（同时把 `mag14` 一并落盘，供与 `run3`/`run4` 对读）——
   判 arm12 的对齐就必须用 arm12 的运动量分层，否则"高运动量档"里装的其实是夹爪事件帧；
2. **f56 的 `j+1` 现象交给 R2 用 `grip2` 口径重测**；R1 对它只出**逐维归属**读数（14 维各自的贡献
   + 点名承载维，补单五 §三 要求的形状），**不**硬判 arm12 胜负（arm12 运动量 0.00439 < 阈值 ⇒ 三值 `n_a`）；
3. R1 **另外**按 arm12 取真·高运动量帧（`f100–f108` 一类，`run3`/`run4` 都没覆盖到）单独判 ⇒
   H2 是被**真·臂侧高运动量帧**排除的，不是被"把极值帧重新归类"排除的。

**这不是放宽判据**：arm12 的行内判据（strict argmin 含 `hold` 竞争 + `margin ≥ 1.2`）比 `run4` 的
行内判据（把 `hold` 排除在竞争外）**更严**；严判据下的例外数单独落盘。

## 三、判据（**全部预登记**；常量 sha 进 `criteria_identity`，改常量即改身份）
| 常量 | 值 | 出处 / 理由（**不是本轮调出来的**） |
|---|---|---|
| `margin_required` | `1.2` | 沿用 L12 冻结常量（`scripts/a2_step1_prealign_verify.py` `ad77b2611475`）|
| `moving_threshold_l2`（arm12） | `0.01` | 同上 |
| `grip2_moving_threshold_l2` | `0.01` | 同上（**同一个常量**，不为夹爪维另立尺子）|
| `warm_drift_arm12_max` | `0.01` | 与判别阈值同量级：warm 滚出的初态若已漂移超过一个判别单位，分叉比的就不是对齐了 |
| strict argmin 的竞争者集合 | 含 `hold_state_j` | `decisions` §100.1-① D 亲核用的就是这把更严的尺子 |

**行内判据**：`moving ≥ threshold` 的行才判；`aligned` 必须是 **strict argmin**（4 臂都参与）**且**
`min(两个 shifted) / aligned ≥ margin_required`。**低运动量行 = `n_a_low_discrimination`**（三值纪律，
既不算过也不算不过）。`aligned == 0.0` 时按**完美预测**判过（比率记 `null`）——这是缺陷类 ⑲
（falsy-zero）的显式正向对照，牙 `T4` 钉住；同时落 `n_rows_aligned_err_is_zero` 证明该分支本轮命中几次。

**R1 断言**（补单六 §二 原文）：对极值帧集，**两个方块位姿下 aligned 都是 arm12 的 argmin，
且对两个 shifted 的 margin ≥ 1.2** ⇒ H2 排除。**负对照必带**：植入 `+1` 错位，arm12 判据必须翻。
**R2 断言**（本腿预登记）：① 行内——每个高判别 `grip2` 行 aligned 都是 strict argmin 且 margin ≥ 1.2；
② 事件内聚合——每个转变事件 ±3 帧的 `grip2` 误差求和，aligned 排第一；③ 全局聚合同向；
④ **warm 模**（把 `qvel=0` 这个已登记扰动源移开）与 cold 模同向。**负对照**：植入 `±1` 都必须翻。

## 四、两种探针模（都测，成对落盘）
* **cold**（= L12 的冻结口径）：`_init_env_to_state(state[j], box, qvel=0)` → 一步。
  方块位姿**两个都给**：`nearest_before = traj[j//10]`、`nearest_after = traj[ceil(j/10)]`
  （D 的指定设计）。两位姿之差 `box_pose_delta_l2` **落盘**——若它 ≈0，则"两位姿都过"这句话
  **不带额外信息**，本腿显式登记 `two_poses_degenerate=true`，不拿它当强度。
* **warm**（本腿新增，**只为移开 `qvel=0` 这一个扰动源**）：从 `state[j-K]` 写初态后用**真动作**滚 K 步，
  到 `j` 再分叉比各 variant；每帧记 `drift`（滚出来的 state vs 数据集 state）。
  漂移超 `warm_drift_arm12_max` 的帧记 `n_a_warm_drift`（**不判**）。方块位姿在 warm 模里
  **只在 w0 写一次**，之后由物理演化（`box_pose_mode="physical_evolution"`）。

## 五、本腿**不做**什么
* **不改 L12 判据、不新增第 13 条腿**（补单五 §五 的治理冻结）——本件是**独立脚本**，
  对 `scripts/a2_step1_prealign_verify.py` **只 import 复用**（`_init_env_to_state` / `read_dataset_arrays` /
  `build_demo_initial_states` / `identity` / `write_json` / `bare_n_lines_tooth`），一个字节都不改。
* **不训练、不上卡、不推理、不判能力**（裁定 46）：`capability_claim=false`、
  `success_rate_column="not_an_exit_criterion"`；本件所有 GREEN **只指接口/口径判词**，policy 指标仍 = 0。
* **不改 C2 的归一化器输入**（裁定 100.8-C2-②：R1/R2 是在既有 npz `a84a26079550` 上做时序探针）。
* **不用 `rm`**：产物只写自己的 `--out-dir`；改判据脚本前必须先留前像（Ⅰ 类口径
  `judging_script_change_requires_before_image_and_criteria_identity`，`decisions` §100.3-（d））。

## 六、用法
    # 1) 预登记 + 判据干跑（**必须先在对象上干跑**，裁定 99.3 的 Ⅰ 类口径）
    MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_r1_r2_alignment_residual.py \
        --out-dir runs/vla/a2_r1_r2_alignment_20260930 --stages prereg

    # 2) 真测（纯 CPU / osmesa，分钟级）
    MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_r1_r2_alignment_residual.py \
        --out-dir runs/vla/a2_r1_r2_alignment_20260930 --stages r1,r2,report

退出码：`0` 全 measured 且无阻塞红且牙全咬 · `1` 有阻塞红或牙不咬 · `3` 存在 `not_measured` ·
`2` 用法/环境错。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
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

# ── 复用先落腿件（**只读 import，不改一个字节**；治理冻结见补单五 §五）─────────────
SELF_REL = "scripts/a2_r1_r2_alignment_residual.py"
PRE_REL = "scripts/a2_step1_prealign_verify.py"


def _load_pre():
    import importlib.util
    spec = importlib.util.spec_from_file_location("a2_step1_prealign_verify_reused", REPO / PRE_REL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["a2_step1_prealign_verify_reused"] = mod
    spec.loader.exec_module(mod)
    return mod


PRE = _load_pre()

now_iso, sha12, identity, write_json, leg = PRE.now_iso, PRE.sha12, PRE.identity, PRE.write_json, PRE.leg
jdefault, bare_n_lines_tooth = PRE.jdefault, PRE.bare_n_lines_tooth
N_LINES_CALIBER = PRE.N_LINES_CALIBER
ARM_DIMS, GRIP_DIMS, STATE_DIM = PRE.ARM_DIMS, PRE.GRIP_DIMS, PRE.STATE_DIM
BLIND_DIMS = PRE.BLIND_DIMS
CST = PRE.CST
EXIT_OK, EXIT_BLOCKING_RED, EXIT_USAGE, EXIT_NOT_MEASURED = 0, 1, 2, 3

# ══════════════════ 判据常量（预登记；sha 进 `criteria_identity`）══════════════════
CRITERIA = {
    "margin_required": 1.2,
    "moving_threshold_l2_arm12": 0.01,
    "grip2_moving_threshold_l2": 0.01,
    "warm_drift_arm12_max": 0.01,
    "warm_drift_grip2_max": 0.01,
    "strict_argmin_competitors": ["aligned_action_j", "shifted_action_j_minus_1",
                                  "shifted_action_j_plus_1", "hold_state_j"],
    "nonstrict_argmin_competitors": ["aligned_action_j", "shifted_action_j_minus_1",
                                     "shifted_action_j_plus_1"],
    "discrimination_rule": ("moving(维集) = ‖state[j+1][维集] − state[j][维集]‖₂；"
                            "moving ≥ threshold ⇒ discrimination=high（判）；否则 low ⇒ "
                            "verdict=n_a_low_discrimination（三值，既不算过也不算不过）"),
    "row_pass_rule": ("high 行：aligned 必须是 strict argmin（4 臂含 hold_state_j 都参与）"
                      "**且** min(两个 shifted)/aligned ≥ margin_required；"
                      "aligned == 0.0 视为完美预测 ⇒ 判过、比率记 null（缺陷类 ⑲ falsy-zero 的显式处置）"),
    "r1_assertion": ("极值帧集在**两个方块位姿**下，所有 arm12 高判别行都 pass ⇒ H2（臂侧 off-by-one）排除"),
    "r2_assertion": ("① 行内：所有 grip2 高判别行 pass；② 事件内聚合：每事件 ±3 帧的 grip2 误差求和 "
                     "aligned 排第一；③ 全局聚合同向；④ warm 模与 cold 模同向"),
    "negative_control_rule": ("植入 +1 / −1 错位后，**在真判据 pass 的每一行上都必须不再 pass**；"
                              "有任何一行植入后仍 pass ⇒ 判据没有分辨力 ⇒ 牙不咬 ⇒ 该腿 RED"),
    "attribution_rule": {
        "what": ("**只用于归类例外的成因，不改任何判据、不改任何 verdict**（判据仍是 row_pass_rule）；"
                 "归类必须由对照证明，不由故事证明（裁定 95.3-②）"),
        "k_ladder": "预热步数 K ∈ {0,1,2,4,8}；**K=0 就是 cold 模**（同初态、同方块位姿、同步一步）",
        "k_ladder_single_variable": ("阶梯上只有 K 一个变量在变：初态帧 j、方块位姿（一律取 j 的 "
                                     "nearest_before）、动作臂集合、目标 state[j+1] 全部不动"),
        "anchor_tolerance": 1e-06,
        "probe_qvel_artifact_not_misalignment_iff": [
            "≥80% 的唯一例外帧在 K≥4 时 verdict == pass",
            "aligned 误差从 K=0 到 K=max 至少降 10×（中位数口径）",
            "K=0 档必须复现 cold 读数（差 ≤ anchor_tolerance）⇒ 阶梯锚得住",
            "聚合与逐事件的排名仍然 aligned 第一",
            "植入 ±1 负对照仍然全翻（判据有分辨力）"],
        "systematic_gripper_offbyone_iff": [
            "≥50% 的唯一例外帧在**所有** K 上都是同一个 shifted 臂当 argmin（错位在 K 增大后不消失）"],
        "otherwise": "mixed / not_explained（照实报，不硬归因）",
    },
    "constants_source": ("margin_required / moving_threshold 沿用 L12 的冻结常量"
                         "（`scripts/a2_step1_prealign_verify.py`），**不是本轮调出来的**；"
                         "grip2 与 warm_drift 复用同一个 0.01，不另立尺子"),
}
ARMS_TRUE = {"aligned_action_j": "a_j", "shifted_action_j_minus_1": "a_jm1",
             "shifted_action_j_plus_1": "a_jp1", "hold_state_j": "hold"}
ARMS_PLANT_P1 = {"aligned_action_j": "a_jp1", "shifted_action_j_minus_1": "a_j",
                 "shifted_action_j_plus_1": "a_jp2", "hold_state_j": "hold"}
ARMS_PLANT_M1 = {"aligned_action_j": "a_jm1", "shifted_action_j_minus_1": "a_jm2",
                 "shifted_action_j_plus_1": "a_j", "hold_state_j": "hold"}
VIEWS = {"true": ARMS_TRUE, "plant_plus_1": ARMS_PLANT_P1, "plant_minus_1": ARMS_PLANT_M1}
DIMSETS = {"arm12": ARM_DIMS, "grip2": GRIP_DIMS, "all14": list(range(STATE_DIM))}


def criteria_constants_sha() -> str:
    canon = json.dumps(CRITERIA, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def criteria_identity(prereg: dict | None = None) -> dict:
    """`decisions` §100.3-（c）/（d）要求的 `criteria_identity` 块（补单六 §四-②）。

    三件：**判据脚本 sha256[:12] + `n_lines_wc`** · **判据常量的 sha** · **冻结来源件的身份**。
    身份一律**当场重算**，不转录。
    """
    me = identity(SELF_REL)
    frozen = identity(PRE_REL)
    return {
        "required_by": "decisions §100.3-（c）（d）· 补单六 §四-② · Ⅰ 类口径 "
                       "judging_script_change_requires_before_image_and_criteria_identity",
        "judging_script": {k: me.get(k) for k in
                           ("path", "exists", "sha256_12", "bytes", "n_lines_wc",
                            "n_lines_splitlines", "mtime", "measurement_status")},
        "criteria_constants_sha256_12": criteria_constants_sha(),
        "criteria_constants": CRITERIA,
        "frozen_criteria_reused_from": {
            "path": frozen.get("path"), "sha256_12": frozen.get("sha256_12"),
            "bytes": frozen.get("bytes"), "n_lines_wc": frozen.get("n_lines_wc"),
            "n_lines_splitlines": frozen.get("n_lines_splitlines"),
            "measurement_status": frozen.get("measurement_status"),
            "reused_functions": ["_init_env_to_state", "read_dataset_arrays",
                                 "build_demo_initial_states", "identity", "write_json",
                                 "bare_n_lines_tooth", "ARM_DIMS", "GRIP_DIMS"],
            "modified": False,
            "note": "L12 判据未改、未新增第 13 条腿（补单五 §五 治理冻结）；本件是独立脚本，只 import 复用",
        },
        "preregistration_constants_sha256_12": (prereg or {}).get("criteria_constants_sha256_12"),
        "preregistration_constants_match": (
            None if not prereg else
            bool(prereg.get("criteria_constants_sha256_12") == criteria_constants_sha())),
        "n_lines_caliber": N_LINES_CALIBER,
    }


# ══════════════════ 判据本体（**纯函数**，可被干跑牙逐形状钉住）══════════════════
def judge_arms(errs: dict, moving: float | None, threshold: float,
               margin_required: float = CRITERIA["margin_required"]) -> dict:
    """对一个维集下的 4 臂误差判行内胜负。**纯函数**：不碰 env、不碰盘，因此可被干跑。

    `errs` 的键必须是 `CRITERIA["strict_argmin_competitors"]`。
    返回：strict/nonstrict argmin、两个 margin 比率、`discrimination`、`verdict ∈
    {pass, fail, n_a_low_discrimination, not_measured}`。
    """
    missing = [k for k in CRITERIA["strict_argmin_competitors"] if k not in errs]
    if missing:
        return {"measurement_status": "not_measured", "verdict": "not_measured",
                "why": f"缺臂 {missing} ⇒ not_measured（不写 0 顶替）", "missing_arms": missing}
    if moving is None:
        return {"measurement_status": "not_measured", "verdict": "not_measured",
                "why": "moving 量取不到 ⇒ not_measured", "errors": dict(errs)}
    a = float(errs["aligned_action_j"])
    best_shifted = min(float(errs["shifted_action_j_minus_1"]), float(errs["shifted_action_j_plus_1"]))
    ordered = sorted(((k, float(v)) for k, v in errs.items()), key=lambda kv: kv[1])
    nonstrict = sorted(((k, float(v)) for k, v in errs.items() if k != "hold_state_j"),
                       key=lambda kv: kv[1])
    high = bool(float(moving) >= float(threshold))
    out = {
        "measurement_status": "measured",
        "errors": {k: round(float(v), 9) for k, v in errs.items()},
        "moving_magnitude": round(float(moving), 9),
        "threshold": float(threshold),
        "discrimination": "high" if high else "low",
        "argmin_strict": ordered[0][0],
        "argmin_excluding_hold": nonstrict[0][0],
        "aligned_is_argmin_strict": bool(ordered[0][0] == "aligned_action_j"),
        "aligned_is_argmin_excluding_hold": bool(nonstrict[0][0] == "aligned_action_j"),
        "margin_ratio_vs_best_shifted": (None if a == 0.0 else round(best_shifted / a, 6)),
        "margin_ratio_vs_runner_up": (None if a == 0.0 else round(ordered[1][1] / a, 6)),
        "aligned_err_is_zero": bool(a == 0.0),
        "margin_ok": bool(best_shifted >= margin_required * a) if a != 0.0 else True,
        "margin_required": float(margin_required),
    }
    if not high:
        out["verdict"] = "n_a_low_discrimination"
        return out
    out["verdict"] = "pass" if (out["aligned_is_argmin_strict"] and out["margin_ok"]) else "fail"
    return out


def judge_view(errs_by_action: dict, dimset_key: str, view: str, moving: float | None,
               threshold: float) -> dict:
    """把「按动作索引存的误差表」翻成「按判据臂名存的误差」，再调 `judge_arms`。

    三种 view（`true` / `plant_plus_1` / `plant_minus_1`）**共用同一张误差表** ⇒
    植入错位负对照与真判据是**同一次仿真**的两种读法，不可能因为重跑而不可比。
    """
    mapping = VIEWS[view]
    dims = DIMSETS[dimset_key]
    errs, miss = {}, []
    for arm, akey in mapping.items():
        pack = errs_by_action.get(akey)
        if pack is None:
            miss.append(akey)
            continue
        errs[arm] = float(np.linalg.norm(np.asarray(pack["per_dim_abs"], dtype=np.float64)[dims]))
    if miss:
        return {"measurement_status": "not_measured", "verdict": "not_measured",
                "why": f"动作越界，缺 {miss}（帧太靠边）⇒ not_measured", "view": view,
                "dimset": dimset_key}
    out = judge_arms(errs, moving, threshold)
    out.update({"view": view, "dimset": dimset_key})
    return out


# ══════════════════ 干跑牙：判据**先在对象上干跑**（裁定 99.3 的 Ⅰ 类口径）══════════
def dry_teeth() -> dict:
    """把 `judge_arms` / `judge_view` 按**形状**逐个钉住：会过的必须过、该翻的必须翻、
    退化的必须**不**恒真、`0.0` 必须走对分支、低判别必须走三值。

    `preregistered_criterion_must_be_dry_run_on_the_object`（裁定 99.3）：
    **先证明判据有分辨力，再拿它去量真对象**；顺序反了就是"先看数再定尺"。
    """
    teeth = []

    def add(tid, expect, bite, detail):
        teeth.append({"tooth_id": tid, "expect": expect, "bite": bool(bite),
                      "measurement_status": "measured", "detail": detail})

    th, mr = CRITERIA["moving_threshold_l2_arm12"], CRITERIA["margin_required"]
    # T1：aligned 明显最好 ⇒ 必须 pass
    e1 = {"aligned_action_j": 0.001, "shifted_action_j_minus_1": 0.030,
          "shifted_action_j_plus_1": 0.040, "hold_state_j": 0.035}
    r1 = judge_arms(e1, 0.05, th, mr)
    add("T1_clean_aligned_must_pass", "verdict == pass", r1["verdict"] == "pass", r1)
    # T2：shifted 更好 ⇒ 必须 fail（判据不是恒真）
    e2 = {"aligned_action_j": 0.020, "shifted_action_j_minus_1": 0.004,
          "shifted_action_j_plus_1": 0.030, "hold_state_j": 0.035}
    r2 = judge_arms(e2, 0.05, th, mr)
    add("T2_shifted_better_must_fail", "verdict == fail", r2["verdict"] == "fail", r2)
    # T3：四臂几乎相等（低运动量的形状）⇒ 高判别档必须**不**判过（margin 卡住）
    e3 = {"aligned_action_j": 0.0857, "shifted_action_j_minus_1": 0.0858,
          "shifted_action_j_plus_1": 0.0856, "hold_state_j": 0.0007}
    r3 = judge_arms(e3, 0.05, th, mr)
    add("T3_tie_must_not_pass", "verdict == fail（margin < 1.2 或 aligned 非 argmin）",
        r3["verdict"] == "fail", r3)
    # T4：falsy-zero 正向对照 —— aligned 误差**恰好 0.0** 时必须判过，不得被判成"缺失/失败"
    e4 = {"aligned_action_j": 0.0, "shifted_action_j_minus_1": 0.01,
          "shifted_action_j_plus_1": 0.02, "hold_state_j": 0.03}
    r4 = judge_arms(e4, 0.05, th, mr)
    add("T4_aligned_exactly_zero_must_pass_not_be_falsy", "verdict == pass ∧ ratio is None",
        r4["verdict"] == "pass" and r4["margin_ratio_vs_best_shifted"] is None
        and r4["aligned_err_is_zero"] is True, r4)
    # T5：低运动量 ⇒ 三值 n_a，既不算过也不算不过
    r5 = judge_arms(e1, 0.002, th, mr)
    add("T5_low_discrimination_must_be_three_valued",
        "verdict == n_a_low_discrimination", r5["verdict"] == "n_a_low_discrimination", r5)
    # T6：moving 取不到 ⇒ not_measured（红线 absence_of_measurement_is_not_measurement）
    r6 = judge_arms(e1, None, th, mr)
    add("T6_missing_moving_must_be_not_measured", "verdict == not_measured",
        r6["verdict"] == "not_measured" and r6["measurement_status"] == "not_measured", r6)
    # T7：缺臂 ⇒ not_measured，不许静默降级成 3 臂判据
    r7 = judge_arms({"aligned_action_j": 0.001, "shifted_action_j_plus_1": 0.03}, 0.05, th, mr)
    add("T7_missing_arm_must_be_not_measured", "verdict == not_measured",
        r7["verdict"] == "not_measured" and sorted(r7["missing_arms"]) ==
        ["hold_state_j", "shifted_action_j_minus_1"], r7)
    # T8：strict argmin 必须比 nonstrict **更严**（hold 参与竞争时可能翻）
    e8 = {"aligned_action_j": 0.010, "shifted_action_j_minus_1": 0.030,
          "shifted_action_j_plus_1": 0.040, "hold_state_j": 0.005}
    r8 = judge_arms(e8, 0.05, th, mr)
    add("T8_strict_argmin_is_stricter_than_nonstrict",
        "nonstrict 判 aligned 赢、strict 判 aligned 不是 argmin ⇒ verdict == fail",
        r8["aligned_is_argmin_excluding_hold"] is True
        and r8["aligned_is_argmin_strict"] is False and r8["verdict"] == "fail", r8)
    # T9：`judge_view` 的三种 view 必须**真的换臂**（否则负对照是空转）
    pack = {k: {"per_dim_abs": [0.0] * STATE_DIM} for k in ("a_jm2", "a_jm1", "a_j", "a_jp1", "a_jp2", "hold")}
    for k, v in (("a_jm2", 0.9), ("a_jm1", 0.5), ("a_j", 0.01), ("a_jp1", 0.3), ("a_jp2", 0.7), ("hold", 0.4)):
        pack[k]["per_dim_abs"][ARM_DIMS[0]] = v
    vt = judge_view(pack, "arm12", "true", 0.05, th)
    vp = judge_view(pack, "arm12", "plant_plus_1", 0.05, th)
    vm = judge_view(pack, "arm12", "plant_minus_1", 0.05, th)
    add("T9_view_rotation_must_change_the_judged_arm",
        "true pass ∧ plant_plus_1 fail ∧ plant_minus_1 fail",
        vt["verdict"] == "pass" and vp["verdict"] == "fail" and vm["verdict"] == "fail",
        {"true": vt, "plant_plus_1": vp, "plant_minus_1": vm})
    # T10：维集必须真的分离 —— grip 维上一个巨大的误差不得进 arm12 判据
    pg = {k: {"per_dim_abs": [0.0] * STATE_DIM} for k in pack}
    for k in pack:
        pg[k]["per_dim_abs"][ARM_DIMS[0]] = 0.01 if k == "a_j" else 0.30
        pg[k]["per_dim_abs"][GRIP_DIMS[0]] = 9.0 if k == "a_j" else 0.0
    va = judge_view(pg, "arm12", "true", 0.05, th)
    vg = judge_view(pg, "grip2", "true", 0.05, CRITERIA["grip2_moving_threshold_l2"])
    add("T10_dimset_separation_must_be_real",
        "arm12 判 aligned pass，同一次仿真 grip2 判 aligned fail",
        va["verdict"] == "pass" and vg["verdict"] == "fail", {"arm12": va, "grip2": vg})
    # T11：`criteria_constants_sha` 必须对常量敏感（改一个数就变），否则身份块是装饰
    base = criteria_constants_sha()
    saved = CRITERIA["margin_required"]
    try:
        CRITERIA["margin_required"] = saved + 0.001
        bumped = criteria_constants_sha()
    finally:
        CRITERIA["margin_required"] = saved
    add("T11_criteria_sha_must_be_constant_sensitive",
        "改动 margin_required 后 sha 变；改回后 sha 复原",
        bumped != base and criteria_constants_sha() == base,
        {"sha_base": base, "sha_bumped": bumped, "sha_restored": criteria_constants_sha()})
    out = {"teeth": teeth, "n_teeth": len(teeth), "n_bite": sum(1 for t in teeth if t["bite"]),
           "measurement_status": "measured",
           "dry_run_on_object": ("判据是**纯函数**（不碰 env、不碰盘）⇒ 干跑用的对象就是判据真会吃的那类对象；"
                                 "真对象上的植入错位负对照另有 R1/R2 腿内的 `plant_*` 读数"),
           "authority": "裁定 99.3（preregistered_criterion_must_be_dry_run_on_the_object）· "
                        "裁定 95.3-②（机制必须由对照证明，不靠一致的故事）"}
    out["n_fail"] = out["n_teeth"] - out["n_bite"]
    out["all_bite"] = bool(out["n_fail"] == 0)
    return out


# ══════════════════ 帧集 / 事件集构造（**纯数值，先落盘再测**）══════════════════════
def _box_pose_pair(row, j):
    """返回 (nearest_before, nearest_after, 元信息)。两位姿之差一并给出（判"两位姿"有没有信息量）。"""
    traj = row.get("box_trajectory_xyz_every_10") or []
    if not traj:
        return None, None, {"measurement_status": "not_measured", "why": "sidecar 无 box_trajectory_xyz_every_10"}
    n = len(traj)
    ib = min(j // 10, n - 1)
    ia = min(-(-j // 10), n - 1)                       # ceil(j/10)，且不越尾
    b = np.asarray(traj[ib], dtype=np.float64)
    a = np.asarray(traj[ia], dtype=np.float64)
    rest = np.asarray(row.get("box_rest_after_settle_xyz"), dtype=np.float64)
    return b, a, {
        "measurement_status": "measured",
        "nearest_before": {"traj_index": int(ib), "frame": int(ib * 10), "xyz": [float(x) for x in b]},
        "nearest_after": {"traj_index": int(ia), "frame": int(ia * 10), "xyz": [float(x) for x in a]},
        "box_pose_delta_l2": float(np.linalg.norm(a - b)),
        "two_poses_degenerate": bool(np.allclose(a, b, atol=1e-9)),
        "degenerate_note": ("两位姿数值相同 ⇒ 「两个位姿下都过」**不带额外信息**，"
                            "本腿不拿它当强度（三值纪律：不把退化对照说成双重验证）"),
        "before_equals_rest": bool(np.allclose(b, rest, atol=1e-9)),
        "after_equals_rest": bool(np.allclose(a, rest, atol=1e-9)),
        "caveat_box": "方块位姿只有 every-10 的权威来源（sidecar）⇒ 非 10 倍数帧用前后夹逼，真值在两者之间",
    }


def build_r1_frame_sets(ds, rows_by_ep, tier_episodes, n_per_tier, b_episodes):
    """R1 的三个帧集（**全部预登记**，测前落盘）：

    * `A_d_specified_extremes`：补单六 §二 点名的 ep20 reverse f46/f56/f66 + `run3` 的前三大
      `step_magnitude_l2`(14 维) 帧（实测 = ep20 f56 / ep0 f4 / ep20 f4，f56 与点名集重合）。
    * `B_arm12_top_motion`：按 **arm12** 运动量取的真·高运动量帧（每集 top-2，`j ∈ [10, nfr-3]`）——
      `run3`/`run4` 都没覆盖到这一类（它们的极值帧其实都是夹爪事件帧）。
    * `C_magnitude_tiers`：低/中/高三档各 `n_per_tier` 帧（补单五 §三-（c）→ 补单六 §二 并入 R1），
      候选只取 **10 的倍数**（方块位姿有权威来源），档界 = 候选池 arm12 运动量的三分位。
    """
    state, action, ep_idx = ds["state"], ds["action"], ds["episode_index"]

    def mag(e, j, dims):
        m = ep_idx == e
        s = state[m]
        return float(np.linalg.norm(s[j + 1][dims] - s[j][dims]))

    setA = []
    for (e, j) in [(20, 46), (20, 56), (20, 66), (0, 4), (20, 4)]:
        if e in rows_by_ep:
            setA.append({"episode_index": e, "frame_j": j, "why": "补单六 §二 点名 / run3 前三大 mag14"})
    setB = []
    for e in sorted(set(int(x) for x in b_episodes) & set(rows_by_ep)):
        nfr = rows_by_ep[e]["n_frames"]
        cand = list(range(10, nfr - 2))
        if not cand:
            continue
        mags = [(mag(e, j, ARM_DIMS), j) for j in cand]
        mags.sort(key=lambda t: (-t[0], t[1]))
        for v, j in mags[:2]:
            setB.append({"episode_index": e, "frame_j": int(j), "arm12_mag_prereg": round(v, 6),
                         "why": ("arm12 运动量 top-2（真·臂侧高运动量帧）；集号限定在 "
                                 "`run3`/`run4` 探过的 4 集，保证与既有判词可逐行对读")})
    pool = []
    for e in tier_episodes:
        if e not in rows_by_ep:
            continue
        nfr = rows_by_ep[e]["n_frames"]
        traj = rows_by_ep[e].get("box_trajectory_xyz_every_10") or []
        for j in range(10, nfr - 2, 10):
            if (j // 10) >= len(traj):
                continue
            pool.append({"episode_index": e, "frame_j": j,
                         "arm12_mag": mag(e, j, ARM_DIMS), "mag14": mag(e, j, list(range(STATE_DIM)))})
    tiers = {"low": [], "mid": [], "high": []}
    tier_bounds = None
    if pool:
        arr = np.asarray([p["arm12_mag"] for p in pool], dtype=np.float64)
        t1, t2 = float(np.quantile(arr, 1.0 / 3.0)), float(np.quantile(arr, 2.0 / 3.0))
        tier_bounds = {"q33_arm12": round(t1, 6), "q67_arm12": round(t2, 6), "n_pool": len(pool)}
        for p in pool:
            k = "low" if p["arm12_mag"] < t1 else ("mid" if p["arm12_mag"] < t2 else "high")
            tiers[k].append(p)
    setC = {}
    for k, items in tiers.items():
        items = sorted(items, key=lambda p: (p["episode_index"], p["frame_j"]))
        stride = max(1, len(items) // max(1, int(n_per_tier)))
        pick = items[::stride][:max(1, int(n_per_tier))]
        setC[k] = [dict(p, tier=k, why=f"arm12 运动量三分位 {k} 档，等距抽 {n_per_tier} 帧") for p in pick]
    return {"A_d_specified_extremes": setA, "B_arm12_top_motion": setB, "C_magnitude_tiers": setC,
            "tier_bounds": tier_bounds,
            "b_episodes": sorted(set(int(x) for x in b_episodes) & set(rows_by_ep)),
            "magnitude_caliber": ("arm12 = ‖state[j+1][ARM_DIMS] − state[j][ARM_DIMS]‖₂；"
                                  "mag14 = 全 14 维同式。分层一律用 arm12（理由见模块 docstring §二）"),
            "n_preregistered_frames": (len(setA) + len(setB) + sum(len(v) for v in setC.values()))}


def build_r2_events(ds, rows_by_ep, episodes_by_dir, n_events_per_dir, half_window):
    """R2 的转变事件集：夹爪**动作值**发生变化的帧，按「极大连续段」聚成事件。

    实测（本腿开工前用纯数值扫全量 11035 帧得到，**先登记后测**）：
    **120 个事件、每个恰好 8 帧、每事件只动一个维（dim6 或 dim13）**；
    按 `direction × sign` = forward/dec 40 · forward/inc 20 · reverse/dec 40 · reverse/inc 20。
    极性（L5 已登记）：**action 1.0 = 张开、0.0 = 合爪** ⇒ `dec` = **合爪**、`inc` = **张开**。

    「正反两向」D 没写死是哪一维，本腿**两种读法都满足**并分别计数：
    ① 集方向 forward/reverse 各 ≥5 个事件；② 变化方向 合爪/张开 各 ≥5 个事件。
    """
    state, action, ep_idx = ds["state"], ds["action"], ds["episode_index"]
    events = []
    for e in sorted(set(ep_idx.tolist())):
        if e not in rows_by_ep:
            continue
        m = ep_idx == e
        a, s = action[m], state[m]
        g = a[:, GRIP_DIMS]
        ch = np.abs(np.diff(g, axis=0)).max(axis=1) > 1e-9
        idx = np.flatnonzero(ch)
        runs = []
        for k in idx:
            if runs and k == runs[-1][-1] + 1:
                runs[-1].append(k)
            else:
                runs.append([k])
        for r in runs:
            p0, p1 = int(r[0]), int(r[-1]) + 1
            dims = [d for d in GRIP_DIMS if np.abs(np.diff(a[:, d])[r]).max() > 1e-9]
            delta = float(g[p1].sum() - g[p0].sum())
            events.append({
                "episode_index": int(e), "direction": rows_by_ep[e]["manifest_direction"],
                "start_frame": p0, "end_frame": p1, "n_ramp_frames": len(r),
                "sign": "inc" if delta > 0 else "dec",
                "gripper_semantics": "开爪" if delta > 0 else "合爪",
                "action_delta": round(delta, 4), "changed_dims": dims,
                "n_frames_episode": int(s.shape[0]),
            })
    picked = []
    for d, eps in episodes_by_dir.items():
        cand = [ev for ev in events if ev["direction"] == d and ev["episode_index"] in eps]
        by_ep = {}
        for ev in cand:
            by_ep.setdefault(ev["episode_index"], []).append(ev)
        take = []
        for e in sorted(by_ep):
            for ev in sorted(by_ep[e], key=lambda x: x["start_frame"]):
                if len(take) >= int(n_events_per_dir):
                    break
                take.append(ev)
            if len(take) >= int(n_events_per_dir):
                break
        picked.extend(take)
    for ev in picked:
        nfr = ev["n_frames_episode"]
        ev["probe_frames"] = [j for j in range(ev["start_frame"] - half_window,
                                               ev["start_frame"] + half_window + 1)
                              if 2 <= j < nfr - 2]
        ev["half_window"] = int(half_window)
    counts = {}
    for ev in picked:
        counts[f"{ev['direction']}/{ev['sign']}"] = counts.get(f"{ev['direction']}/{ev['sign']}", 0) + 1
    return {"all_events_in_dataset": len(events),
            "events_by_dir_sign_all": {f"{k}": v for k, v in
                                       sorted(((f"{e['direction']}/{e['sign']}",
                                                sum(1 for x in events
                                                    if x['direction'] == e['direction']
                                                    and x['sign'] == e['sign']))
                                              for e in events), key=lambda kv: kv[0])},
            "picked": picked, "picked_counts_by_dir_sign": counts,
            "n_picked": len(picked),
            "reading_of_正反两向": ("① 集方向 forward/reverse；② 变化方向 合爪(dec)/张开(inc)。"
                                    "两种读法都计数，缺任一种 ≥5 即 not_measured 并报 D"),
            "gripper_polarity_source": "L5（run4）：GRIP_OPEN_NORM=1.0 / GRIP_CLOSE_NORM=0.0"}


# ══════════════════ env 会话（**步数预算 + 截断守卫**：静默污染的防线）══════════════
class EnvSession:
    """一个 episode 的探针会话。

    **为什么必须有守卫**：`EnvSpec.horizon_steps() = 300`（裁定 58.3），底层 gym 的 TimeLimit 一旦
    触发，**下一次** `step()` 的初态就不再是我写进去的那个 ⇒ 静默污染。`run4` 每个 env 只走 24 步
    所以碰不到；本腿每集要走几百步 ⇒ 必须显式记账：`steps_since_fresh` 超预算就**主动换新 env**，
    并且**每次 step 后检查 `env_truncated`**，命中即记数 + 立刻换新。两个计数都落盘。
    """

    def __init__(self, row, budget: int = 200):
        from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm
        from harness.env_gym_aloha import GEOM_BOX, EnvSpec, GymAlohaSimEnv
        self._unorm, self._EnvSpec, self._Env = unorm, EnvSpec, GymAlohaSimEnv
        self._GEOM_BOX = GEOM_BOX
        self.row, self.budget = row, int(budget)
        self.n_created = self.n_truncated = self.steps_since_fresh = self.n_steps = 0
        self.jenv = None
        self.fresh()

    def fresh(self):
        r = self.row
        self.jenv = self._Env(self._EnvSpec(direction=r["env_direction"], image_size=64,
                                           render_images=False, seed=int(r["seed"])))
        self.jenv.reset(seed=int(r["seed"]))
        self.n_created += 1
        self.steps_since_fresh = 0

    def set_state(self, s14, box_xyz):
        return PRE._init_env_to_state(self.jenv, s14, box_xyz, self._unorm)

    def step_and_read(self, action):
        """走一步并**立刻**读 state；读完再处理截断（截断只污染下一步，不污染本步的读数）。"""
        if self.steps_since_fresh + 1 > self.budget:
            self.fresh()
        _, info = self.jenv.step(np.asarray(action, dtype=np.float32))
        self.steps_since_fresh += 1
        self.n_steps += 1
        got = self.jenv._state().astype(np.float64)
        trunc = bool(info.get("env_truncated"))
        if trunc:
            self.n_truncated += 1
            self.fresh()
        return got, {"env_truncated": trunc, "step_index": int(info.get("step_index") or -1)}

    def box_xyz(self):
        return np.asarray(self.jenv.physics.named.data.geom_xpos[self._GEOM_BOX],
                          dtype=np.float64).copy()

    def save_phys(self):
        return (self.jenv.physics.data.qpos.copy(), self.jenv.physics.data.qvel.copy())

    def restore_phys(self, sv):
        self.jenv.physics.data.qpos[:] = sv[0]
        self.jenv.physics.data.qvel[:] = sv[1]
        self.jenv.physics.forward()

    def facts(self):
        return {"n_env_created": self.n_created, "n_steps_total": self.n_steps,
                "n_truncation_events": self.n_truncated, "step_budget_per_env": self.budget,
                "horizon_steps": int(self.jenv.horizon) if self.jenv is not None else None,
                "guard": ("步数超预算或 `env_truncated` 命中 ⇒ 立刻换新 env（两个计数都落盘）；"
                          "这是「静默污染」的防线，不是可选装饰")}


def err_pack(got, target) -> dict:
    d = np.abs(np.asarray(got, dtype=np.float64) - np.asarray(target, dtype=np.float64))
    return {"per_dim_abs": [float(x) for x in d],
            "l2": float(np.linalg.norm(d)),
            "l2_arm12": float(np.linalg.norm(d[ARM_DIMS])),
            "l2_grip2": float(np.linalg.norm(d[GRIP_DIMS])),
            "maxdim": float(d.max()), "argmax_dim": int(np.argmax(d))}


def round_pack(p: dict, nd: int = 9) -> dict:
    return {"per_dim_abs": [round(float(x), nd) for x in p["per_dim_abs"]],
            "l2": round(float(p["l2"]), nd), "l2_arm12": round(float(p["l2_arm12"]), nd),
            "l2_grip2": round(float(p["l2_grip2"]), nd), "maxdim": round(float(p["maxdim"]), nd),
            "argmax_dim": int(p["argmax_dim"])}


def action_bundle(ep_action, ep_state, j, nfr):
    """一次仿真出 6 个动作臂的误差表 ⇒ 真判据与植入 ±1 负对照**共用同一次仿真**。"""
    acts, clipped = {}, []

    def pick(k, idx, fallback):
        if 0 <= idx < nfr:
            acts[k] = np.asarray(fallback(idx), dtype=np.float64)
        else:
            clipped.append({"arm": k, "requested_index": int(idx)})
    pick("a_jm2", j - 2, lambda i: ep_action[i])
    pick("a_jm1", j - 1, lambda i: ep_action[i])
    pick("a_j", j, lambda i: ep_action[i])
    pick("a_jp1", j + 1, lambda i: ep_action[i])
    pick("a_jp2", j + 2, lambda i: ep_action[i])
    if 0 <= j < nfr:
        acts["hold"] = np.asarray(ep_state[j], dtype=np.float64)
    else:
        clipped.append({"arm": "hold", "requested_index": int(j)})
    return acts, clipped




def cold_probe(sess, state_j, box, acts, target):
    """**cold 模** = L12 的冻结口径：写 `(state[j], box, qvel=0)` → 一步 → 读 state。"""
    out = {}
    for name, a in acts.items():
        sess.set_state(state_j, box)
        got, meta = sess.step_and_read(a)
        pack = err_pack(got, target)
        pack["_meta"] = meta
        out[name] = pack
    return out


def warm_probe_chain(sess, ep_state, ep_action, w0, frames, box_w0, acts_fn, target_fn):
    """**warm 模**：从 `state[w0]` 写初态（唯一一次 `qvel=0`），用**真动作**滚到待测帧再分叉。

    目的只有一个：**把 `qvel=0` 这个已登记的扰动源从被测的那一步移开**（数据集不存 qvel，
    cold 模每一步都把它清零；夹爪是位置执行器，一帧内的位移对初速度敏感 ⇒ 这是 R2 最可能的
    假红来源）。代价是漂移会累积 ⇒ **每帧都记 `drift`**，超 `warm_drift_arm12_max` 的帧
    记 `n_a_warm_drift`（三值，不判）。方块位姿只在 `w0` 写一次，之后由物理演化。
    """
    sess.set_state(ep_state[w0], box_w0)
    out, cursor = {}, w0
    for j in sorted(frames):
        while cursor < j:
            sess.step_and_read(ep_action[cursor])
            cursor += 1
        pre = sess.jenv._state().astype(np.float64)
        saved = sess.save_phys()
        per_arm = {}
        for name, a in acts_fn(j).items():
            sess.restore_phys(saved)
            got, meta = sess.step_and_read(a)
            pack = err_pack(got, target_fn(j))
            pack["_meta"] = meta
            per_arm[name] = pack
        out[str(j)] = {"frame_j": int(j), "drift": err_pack(pre, ep_state[j]),
                       "box_xyz_at_fork": [float(x) for x in sess.box_xyz()],
                       "n_warmup_steps_from_w0": int(j - w0), "arms": per_arm}
        sess.restore_phys(saved)
        sess.step_and_read(ep_action[j])
        cursor = j + 1
    return out


def aggregate_by_arm(rows, dimset, view, only_high):
    """D 在 §99.2/§100.1 用的那把聚合尺子：按臂求和（可限定在高判别行上）。"""
    sums, n = {}, 0
    for r in rows:
        jd = ((r.get("judge") or {}).get(dimset) or {}).get(view)
        if not jd or jd.get("measurement_status") != "measured":
            continue
        if only_high and jd.get("discrimination") != "high":
            continue
        n += 1
        for arm, v in (jd.get("errors") or {}).items():
            sums[arm] = round(sums.get(arm, 0.0) + float(v), 9)
    ordered = sorted(sums.items(), key=lambda kv: kv[1])
    return {"dimset": dimset, "view": view, "only_high_discrimination": bool(only_high),
            "n_rows": n, "sum_by_arm": dict(ordered),
            "best_arm": (ordered[0][0] if ordered else None),
            "aligned_is_best": bool(ordered and ordered[0][0] == "aligned_action_j")}


def strict_no_gating_disclosure(rows, dimset, view):
    """**不设判别门**地把所有行都判一遍（= D 在 §100.1 亲核用的口径），单独落盘。

    为什么必须有这一块：本腿的行内判据带 `moving ≥ threshold` 的三值门，若只报门内的数，
    读者无法判断「是不是靠门把不利行挡掉了」。这里把**门外的行也判**，例外数一并给出 ⇒
    判据有没有被收窄，可以逐行复核。
    """
    n_all = n_argmin = n_pass = 0
    exceptions = []
    for r in rows:
        jd = ((r.get("judge") or {}).get(dimset) or {}).get(view)
        if not jd or jd.get("measurement_status") != "measured":
            continue
        n_all += 1
        if jd.get("aligned_is_argmin_strict"):
            n_argmin += 1
        ok = bool(jd.get("aligned_is_argmin_strict") and jd.get("margin_ok"))
        if ok:
            n_pass += 1
        else:
            exceptions.append({"episode_index": r["episode_index"], "frame_j": r["frame_j"],
                               "set": r.get("set"), "box_pose_tag": r.get("box_pose_tag"),
                               "mode": r.get("mode"), "tier": r.get("tier"),
                               "discrimination": jd.get("discrimination"),
                               "moving": jd.get("moving_magnitude"), "errors": jd.get("errors"),
                               "argmin_strict": jd.get("argmin_strict"),
                               "margin_ratio_vs_best_shifted": jd.get("margin_ratio_vs_best_shifted")})
    return {"dimset": dimset, "view": view, "gating": "none（低判别行也判）",
            "n_rows": n_all, "n_aligned_is_argmin_strict": n_argmin,
            "frac_aligned_is_argmin_strict": (round(n_argmin / n_all, 6) if n_all else None),
            "n_pass_strict_and_margin": n_pass, "n_exceptions": len(exceptions),
            "exceptions_head": exceptions[:12], "n_exceptions_listed": min(12, len(exceptions))}


def planted_control_report(rows, dimset):
    """植入 ±1 错位的负对照：**在真判据 pass 的每一行上都必须不再 pass**。"""
    n_true_pass = n_p1 = n_m1 = 0
    offenders = []
    for r in rows:
        js = ((r.get("judge") or {}).get(dimset) or {})
        t, p, m = js.get("true"), js.get("plant_plus_1"), js.get("plant_minus_1")
        if not t or t.get("verdict") != "pass":
            continue
        n_true_pass += 1
        for tag, jd in (("plant_plus_1", p), ("plant_minus_1", m)):
            if jd and jd.get("verdict") == "pass":
                n_p1 += (tag == "plant_plus_1")
                n_m1 += (tag == "plant_minus_1")
                offenders.append({"episode_index": r["episode_index"], "frame_j": r["frame_j"],
                                  "set": r.get("set"), "mode": r.get("mode"), "tag": tag,
                                  "errors": jd.get("errors")})
    return {"dimset": dimset, "n_rows_true_pass": n_true_pass,
            "n_plant_plus_1_still_pass": n_p1, "n_plant_minus_1_still_pass": n_m1,
            "flipped_everywhere": bool(n_true_pass > 0 and n_p1 == 0 and n_m1 == 0),
            "offenders_head": offenders[:10], "rule": CRITERIA["negative_control_rule"]}


def per_dim_attribution(errs_by_action, target, state_j, aligned_key: str = "a_j"):
    """补单五 §三 要求的形状：**14 维各自对残差的贡献 + 点名承载维**（不只给总残差）。"""
    dims = list(range(STATE_DIM))
    out = {}
    for name, pack in errs_by_action.items():
        d = np.asarray(pack["per_dim_abs"], dtype=np.float64)
        tot = float(d.sum())
        carry = int(np.argmax(d))
        out[name] = {"abs_err_per_dim": {str(i): round(float(d[i]), 9) for i in dims},
                     "sum_abs": round(tot, 9), "l2": round(float(pack["l2"]), 9),
                     "carry_dim": carry,
                     "carry_dim_share_of_sum_abs": (round(float(d[carry]) / tot, 6) if tot > 0 else None),
                     "share_by_dim": {str(i): (round(float(d[i]) / tot, 6) if tot > 0 else None)
                                      for i in dims},
                     "is_blind_dim": bool(carry in BLIND_DIMS)}
    aligned = out.get(aligned_key) or {}
    mv = float(np.linalg.norm(np.asarray(target, dtype=np.float64) - np.asarray(state_j, dtype=np.float64)))
    return {"per_action_arm": out,
            "action_key_map": {v: k for k, v in ARMS_TRUE.items()},
            "aligned_action_key": aligned_key,
            "carry_dim_of_aligned": aligned.get("carry_dim"),
            "carry_dim_is_gripper": bool(aligned.get("carry_dim") in GRIP_DIMS),
            "moving_magnitude_all14": round(mv, 9),
            "note": (f"承载维 = aligned 臂逐维绝对误差最大的那一维；盲点维 {BLIND_DIMS} 是 C2 的 "
                     "94.3 Ⅱ 类登记项，**不得**当能力判据，也不得把 per-dim 结论写成全 14 维结论")}


def k_ladder_attribution(rows_by_ep, ep_arrays_fn, exception_frames, control_frames, dimset,
                         ks=(0, 1, 2, 4, 8)):
    """**只改一个变量（warm 预热步数 K）**的阶梯对照：把例外的成因从「故事」变成「对照」。

    `K=0` 就是 cold 模（同初态帧、同方块位姿、同步一步）⇒ 阶梯的第一档必须**复现** cold 的读数，
    否则阶梯锚不住（牙 `TK_k_ladder_anchor_must_reproduce_cold` 钉住）。方块位姿在**所有 K** 上都
    写帧 j 的 `nearest_before` 值（写一次，之后物理演化）⇒ 阶梯上动的只有 K。
    """
    threshold = THRESH[dimset]
    frames_out, sessions = [], {}
    for role, flist in (("exception", exception_frames), ("control", control_frames)):
        for (e, j) in flist:
            rec = {"episode_index": int(e), "frame_j": int(j), "role": role, "dimset": dimset}
            if e not in rows_by_ep:
                rec.update({"measurement_status": "not_measured", "why": "该集无 sidecar/初态行"})
                frames_out.append(rec)
                continue
            es, ea = ep_arrays_fn(e)
            nfr = int(es.shape[0])
            if not (2 <= j < nfr - 2):
                rec.update({"measurement_status": "not_measured", "n_frames": nfr,
                            "why": f"帧越界（需 2 ≤ j < {nfr - 2}）"})
                frames_out.append(rec)
                continue
            if e not in sessions:
                sessions[e] = EnvSession(rows_by_ep[e], budget=STEP_BUDGET)
            sess = sessions[e]
            box_j, _, bmeta = _box_pose_pair(rows_by_ep[e], j)
            acts, _clipped = action_bundle(ea, es, j, nfr)
            target = es[j + 1]
            moving = moving_mags(es[j], target)
            ladder = []
            for K in ks:
                w0 = max(2, int(j) - int(K))
                res = warm_probe_chain(sess, es, ea, w0, [int(j)], box_j,
                                       (lambda _a: (lambda jj: acts))(acts),
                                       (lambda _t: (lambda jj: target))(target))
                blk = res[str(j)]
                jd = judge_view(blk["arms"], dimset, "true", moving[dimset], threshold)
                ladder.append({
                    "K": int(K), "w0": int(w0), "verdict": jd.get("verdict"),
                    "argmin_strict": jd.get("argmin_strict"),
                    "errors": jd.get("errors"),
                    "margin_ratio_vs_best_shifted": jd.get("margin_ratio_vs_best_shifted"),
                    "drift_arm12": round(float(blk["drift"]["l2_arm12"]), 9),
                    "drift_grip2": round(float(blk["drift"]["l2_grip2"]), 9),
                    "box_pose_written_at_w0": [float(x) for x in box_j],
                    "box_xyz_at_fork": [float(x) for x in blk["box_xyz_at_fork"]],
                    "box_moved_during_warmup_l2": round(float(np.linalg.norm(
                        np.asarray(blk["box_xyz_at_fork"], dtype=np.float64)
                        - np.asarray(box_j, dtype=np.float64))), 9)})
            rec.update({"measurement_status": "measured", "moving": moving,
                        "box_pose_meta": bmeta, "ladder": ladder})
            frames_out.append(rec)
    return {"frames": frames_out, "ks": [int(k) for k in ks], "dimset": dimset,
            "single_variable": CRITERIA["attribution_rule"]["k_ladder_single_variable"],
            "session_facts": {str(k): v.facts() for k, v in sorted(sessions.items())}}


def attribution_analysis(ladder_block, cold_err_by_frame, dimset, agg_aligned_best,
                         planted_flipped, event_agg_all_aligned_first):
    """按**预登记的归类规则**（`CRITERIA["attribution_rule"]`）判例外的成因，并出锚定牙。

    **它不改任何 verdict**：R2 的行内判据与红码照旧；这里只回答「例外是谁造成的」。
    """
    ar = CRITERIA["attribution_rule"]
    ks_max = max(ladder_block["ks"]) if ladder_block["ks"] else None
    anchors, decay, exc_pass_at_kmax, persistent_shifted = [], [], 0, 0
    exc = [f for f in ladder_block["frames"]
           if f["role"] == "exception" and f.get("measurement_status") == "measured"]
    for f in exc:
        k0 = next((x for x in f["ladder"] if x["K"] == 0), None)
        kmax = next((x for x in f["ladder"] if x["K"] == ks_max), None)
        cold = cold_err_by_frame.get((f["episode_index"], f["frame_j"]))
        if k0 and cold:
            diff = max(abs(float(k0["errors"][arm]) - float(cold[arm])) for arm in k0["errors"]
                       if arm in cold)
            anchors.append({"episode_index": f["episode_index"], "frame_j": f["frame_j"],
                            "max_abs_diff_K0_vs_cold": round(diff, 12),
                            "within_tolerance": bool(diff <= float(ar["anchor_tolerance"]))})
        else:
            anchors.append({"episode_index": f["episode_index"], "frame_j": f["frame_j"],
                            "measurement_status": "not_measured",
                            "why": "K=0 档或 cold 行缺失 ⇒ 锚不上，不写 0 顶替"})
        if kmax and kmax.get("verdict") == "pass":
            exc_pass_at_kmax += 1
        e0 = ((k0 or {}).get("errors") or {}).get("aligned_action_j")
        em = ((kmax or {}).get("errors") or {}).get("aligned_action_j")
        if e0 is not None and em not in (None, 0):
            decay.append(float(e0) / float(em))
        winners = [x.get("argmin_strict") for x in f["ladder"]]
        shifted = [w for w in winners if w in ("shifted_action_j_minus_1", "shifted_action_j_plus_1")]
        if shifted and len(shifted) == len(winners) and len(set(shifted)) == 1:
            persistent_shifted += 1
    n_exc = len(exc)
    frac_pass_kmax = (exc_pass_at_kmax / n_exc) if n_exc else None
    median_decay = float(np.median(decay)) if decay else None
    frac_persistent = (persistent_shifted / n_exc) if n_exc else None
    anchor_ok = bool(anchors) and all(a.get("within_tolerance") for a in anchors)
    cond_qvel = {
        "frac_exception_frames_pass_at_Kmax_ge_0.8": (None if frac_pass_kmax is None
                                                      else bool(frac_pass_kmax >= 0.8)),
        "median_aligned_err_decay_K0_over_Kmax_ge_10x": (None if median_decay is None
                                                         else bool(median_decay >= 10.0)),
        "anchor_K0_reproduces_cold": anchor_ok,
        "aggregate_and_event_rankings_still_aligned_first": bool(agg_aligned_best
                                                                 and event_agg_all_aligned_first),
        "planted_controls_still_flip": bool(planted_flipped),
    }
    cond_shift = {"frac_exception_frames_with_same_shifted_argmin_at_all_K_ge_0.5":
                  (None if frac_persistent is None else bool(frac_persistent >= 0.5))}
    if n_exc == 0:
        cls = "no_exception_to_attribute"
    elif all(v is True for v in cond_qvel.values()):
        cls = "probe_qvel_artifact_not_misalignment"
    elif list(cond_shift.values())[0] is True:
        cls = "systematic_gripper_offbyone"
    else:
        cls = "mixed_or_not_explained"
    tooth = {"tooth_id": "TK_k_ladder_anchor_must_reproduce_cold",
             "expect": (f"阶梯 K=0 档必须复现 cold 读数（差 ≤ {ar['anchor_tolerance']}）⇒ "
                        "阶梯上只有 K 一个变量在动"),
             "measurement_status": "measured" if anchors else "not_measured",
             "bite": anchor_ok, "detail": {"n_anchors": len(anchors), "anchors": anchors}}
    return {"classification": cls,
            "classification_rule": ar,
            "n_unique_exception_frames": n_exc,
            "n_exception_frames_pass_at_Kmax": exc_pass_at_kmax,
            "frac_exception_frames_pass_at_Kmax": (round(frac_pass_kmax, 6)
                                                   if frac_pass_kmax is not None else None),
            "median_aligned_err_decay_K0_over_Kmax": (round(median_decay, 3)
                                                      if median_decay is not None else None),
            "n_exception_frames_with_persistent_shifted_argmin": persistent_shifted,
            "conditions_for_probe_qvel_artifact": cond_qvel,
            "conditions_for_systematic_offbyone": cond_shift,
            "anchor_tooth": tooth,
            "ladder": ladder_block,
            "verdict_untouched": ("本块**不改** R2 的 verdict / red_codes：判据是预登记的，"
                                  "例外就是例外；这里只回答「例外是谁造成的」，处置权在 D")}


def tier_report(rows, dimset):
    out = {}
    for t in ("low", "mid", "high"):
        sub = [r for r in rows if r.get("tier") == t]
        js = [((r.get("judge") or {}).get(dimset) or {}).get("true") for r in sub]
        js = [j for j in js if j and j.get("measurement_status") == "measured"]
        hi = [j for j in js if j.get("discrimination") == "high"]
        out[t] = {"n_rows": len(sub), "n_judged": len(js), "n_high_discrimination": len(hi),
                  "frac_aligned_is_argmin_strict": (
                      round(sum(1 for j in js if j.get("aligned_is_argmin_strict")) / len(js), 6)
                      if js else None),
                  "n_high_pass": sum(1 for j in hi if j.get("verdict") == "pass"),
                  "n_high_fail": sum(1 for j in hi if j.get("verdict") == "fail"),
                  "sum_by_arm": aggregate_by_arm(sub, dimset, "true", only_high=False)["sum_by_arm"],
                  "moving_median": (round(float(np.median([j["moving_magnitude"] for j in js])), 6)
                                    if js else None)}
    return out


# ══════════════════════════ R1：臂侧 12 维的 off-by-one 排除 ══════════════════════
THRESH = {"arm12": CRITERIA["moving_threshold_l2_arm12"],
          "grip2": CRITERIA["grip2_moving_threshold_l2"],
          "all14": CRITERIA["moving_threshold_l2_arm12"]}
STEP_BUDGET = 200


def moving_mags(state_j, target) -> dict:
    d = np.asarray(target, dtype=np.float64) - np.asarray(state_j, dtype=np.float64)
    return {"arm12": float(np.linalg.norm(d[ARM_DIMS])),
            "grip2": float(np.linalg.norm(d[GRIP_DIMS])),
            "all14": float(np.linalg.norm(d))}


def mk_judge(errs_by_action, moving, dimsets, views=("true", "plant_plus_1", "plant_minus_1")):
    return {dk: {v: judge_view(errs_by_action, dk, v, moving[dk], THRESH[dk]) for v in views}
            for dk in dimsets}


def compact_errs(errs_by_action, keep_dims, nd=9):
    out = {}
    for k, p in errs_by_action.items():
        d = np.asarray(p["per_dim_abs"], dtype=np.float64)
        out[k] = {"l2": round(float(p["l2"]), nd), "l2_arm12": round(float(p["l2_arm12"]), nd),
                  "l2_grip2": round(float(p["l2_grip2"]), nd),
                  "maxdim": round(float(p["maxdim"]), nd), "argmax_dim": int(p["argmax_dim"]),
                  "abs_err_dims": {str(i): round(float(d[i]), nd) for i in keep_dims},
                  "env_truncated_after_step": bool((p.get("_meta") or {}).get("env_truncated"))}
    return out


def _warm_gate(drift_pack):
    """warm 模的漂移门（预登记）：超阈 ⇒ 该行**不判**（`n_a_warm_drift`），不是判过也不是判不过。"""
    a = float(drift_pack["l2_arm12"])
    g = float(drift_pack["l2_grip2"])
    ok = bool(a <= CRITERIA["warm_drift_arm12_max"] and g <= CRITERIA["warm_drift_grip2_max"])
    return ok, {"drift_arm12": round(a, 9), "drift_grip2": round(g, 9),
                "gate": {"arm12_max": CRITERIA["warm_drift_arm12_max"],
                         "grip2_max": CRITERIA["warm_drift_grip2_max"],
                         "note": "同一冻结常量 0.01；对 grip2 也设门是**加严**，不是放宽"},
                "within_gate": ok}


def r1_leg(ctx, fs, warm_k):
    L = leg("R1_arm12_offbyone_exclusion",
            "**只比臂侧 12 维**，在两个方块位姿下判 `aligned` 是否 argmin 且 margin ≥ 1.2；"
            "帧集 = 补单六 §二 点名的极值帧 + arm12 真·高运动量帧 + 运动量三档各 N 帧；"
            "植入 +1/−1 错位做负对照")
    try:
        ds, rows_by_ep = ctx["ds"], ctx["rows_by_ep"]
        state, action, ep_idx = ds["state"], ds["action"], ds["episode_index"]
        ep_cache, sessions = {}, {}

        def ep_arrays(e):
            if e not in ep_cache:
                m = ep_idx == e
                ep_cache[e] = (state[m], action[m])
            return ep_cache[e]

        def sess_for(e):
            if e not in sessions:
                sessions[e] = EnvSession(rows_by_ep[e], budget=STEP_BUDGET)
            return sessions[e]

        rows, skipped = [], []

        def one_frame(e, j, set_label, tier=None, want_warm=False, want_perdim=False):
            es, ea = ep_arrays(e)
            nfr = int(es.shape[0])
            rec = {"episode_index": int(e), "frame_j": int(j), "set": set_label, "tier": tier,
                   "direction": rows_by_ep[e]["manifest_direction"] if e in rows_by_ep else None}
            if e not in rows_by_ep:
                rec.update({"measurement_status": "not_measured", "why": "该集无 sidecar/初态行"})
                skipped.append(rec)
                return
            if not (2 <= j < nfr - 2):
                rec.update({"measurement_status": "not_measured", "n_frames": nfr,
                            "why": f"帧越界（需 2 ≤ j < nfr−2 = {nfr - 2}）"})
                skipped.append(rec)
                return
            bb, ba, bmeta = _box_pose_pair(rows_by_ep[e], j)
            if bb is None:
                rec.update({"measurement_status": "not_measured", "box_pose_meta": bmeta,
                            "why": bmeta.get("why")})
                skipped.append(rec)
                return
            sess = sess_for(e)
            acts, clipped = action_bundle(ea, es, j, nfr)
            target = es[j + 1]
            moving = moving_mags(es[j], target)
            poses = [("nearest_before", bb)]
            if not bmeta.get("two_poses_degenerate"):
                poses.append(("nearest_after", ba))
            for tag, box in poses:
                errs = cold_probe(sess, es[j], box, acts, target)
                row = dict(rec, mode="cold", box_pose_tag=tag, measurement_status="measured",
                           n_frames=nfr, box_pose_xyz=[float(x) for x in box],
                           box_pose_meta=bmeta, moving=moving,
                           grip_share_of_all14_moving=(
                               round(moving["grip2"] / moving["all14"], 6)
                               if moving["all14"] > 0 else None),
                           actions_clipped=clipped,
                           errors_by_action=compact_errs(errs, list(range(STATE_DIM))),
                           judge=mk_judge(errs, moving, ("arm12", "grip2", "all14")))
                if want_perdim:
                    row["per_dim_attribution"] = per_dim_attribution(errs, target, es[j])
                rows.append(row)
            if want_warm:
                w0 = max(2, j - int(warm_k))
                bw0, _, _ = _box_pose_pair(rows_by_ep[e], w0)
                res = warm_probe_chain(sess, es, ea, w0, [j], bw0,
                                       lambda jj: action_bundle(ea, es, jj, nfr)[0],
                                       lambda jj: es[jj + 1])
                blk = res[str(j)]
                within, gate = _warm_gate(blk["drift"])
                jd = mk_judge(blk["arms"], moving, ("arm12", "grip2"))
                if not within:
                    for dk in jd:
                        for v in jd[dk]:
                            if jd[dk][v].get("measurement_status") == "measured":
                                jd[dk][v]["verdict"] = "n_a_warm_drift"
                                jd[dk][v]["why_na"] = "warm 滚出的初态漂移超门 ⇒ 不判（三值）"
                rows.append(dict(rec, mode="warm", box_pose_tag="physical_evolution",
                                 measurement_status="measured", n_frames=nfr,
                                 box_pose_xyz=[float(x) for x in blk["box_xyz_at_fork"]],
                                 warm={"w0": int(w0), "warm_k": int(warm_k),
                                       "n_warmup_steps": blk["n_warmup_steps_from_w0"],
                                       "drift": round_pack(blk["drift"], 9), "gate": gate},
                                 moving=moving, errors_by_action=compact_errs(
                                     blk["arms"], list(range(STATE_DIM))), judge=jd))

        for f in fs["A_d_specified_extremes"]:
            one_frame(f["episode_index"], f["frame_j"], "A_d_specified_extremes",
                      want_warm=True, want_perdim=True)
        for f in fs["B_arm12_top_motion"]:
            one_frame(f["episode_index"], f["frame_j"], "B_arm12_top_motion",
                      want_warm=True, want_perdim=True)
        for t, items in fs["C_magnitude_tiers"].items():
            for f in items:
                one_frame(f["episode_index"], f["frame_j"], "C_magnitude_tiers", tier=t)

        cold = [r for r in rows if r.get("mode") == "cold"]
        warm = [r for r in rows if r.get("mode") == "warm"]
        a12 = [((r.get("judge") or {}).get("arm12") or {}).get("true") for r in rows]
        a12 = [j for j in a12 if j and j.get("measurement_status") == "measured"]
        hi = [j for j in a12 if j.get("discrimination") == "high"]
        fails = []
        for r in rows:
            jd = ((r.get("judge") or {}).get("arm12") or {}).get("true") or {}
            if jd.get("verdict") == "fail":
                fails.append({"episode_index": r["episode_index"], "frame_j": r["frame_j"],
                              "set": r.get("set"), "tier": r.get("tier"), "mode": r.get("mode"),
                              "box_pose_tag": r.get("box_pose_tag"), "errors": jd.get("errors"),
                              "moving": jd.get("moving_magnitude"),
                              "argmin_strict": jd.get("argmin_strict"),
                              "margin_ratio_vs_best_shifted": jd.get("margin_ratio_vs_best_shifted")})
        # 两位姿覆盖：非退化两位姿的帧，必须两个位姿下都 pass
        by_frame = {}
        for r in cold:
            jd = ((r.get("judge") or {}).get("arm12") or {}).get("true") or {}
            by_frame.setdefault((r["episode_index"], r["frame_j"]), []).append(
                {"box_pose_tag": r.get("box_pose_tag"), "verdict": jd.get("verdict"),
                 "degenerate": bool((r.get("box_pose_meta") or {}).get("two_poses_degenerate")),
                 "box_pose_delta_l2": (r.get("box_pose_meta") or {}).get("box_pose_delta_l2")})
        two_pose_frames = {k: v for k, v in by_frame.items() if len(v) >= 2}
        both_pass = {k: v for k, v in two_pose_frames.items()
                     if all(x["verdict"] in ("pass", "n_a_low_discrimination") for x in v)}
        # f56 的逐维归属（补单五 §三：点名承载维）
        f56 = [r for r in rows if r["episode_index"] == 20 and r["frame_j"] == 56
               and r.get("mode") == "cold" and r.get("box_pose_tag") == "nearest_before"]
        attribution = None
        if f56:
            r = f56[0]
            g2 = ((r.get("judge") or {}).get("grip2") or {}).get("true") or {}
            a1 = ((r.get("judge") or {}).get("arm12") or {}).get("true") or {}
            carry = ((r.get("per_dim_attribution") or {}).get("carry_dim_of_aligned"))
            attribution = {
                "episode_index": 20, "frame_j": 56, "direction": r.get("direction"),
                "moving": r.get("moving"), "grip_share_of_all14_moving": r.get("grip_share_of_all14_moving"),
                "arm12_discrimination": a1.get("discrimination"), "arm12_verdict": a1.get("verdict"),
                "arm12_errors": a1.get("errors"),
                "grip2_discrimination": g2.get("discrimination"), "grip2_verdict": g2.get("verdict"),
                "grip2_argmin_strict": g2.get("argmin_strict"), "grip2_errors": g2.get("errors"),
                "carry_dim_of_aligned": carry,
                "carry_dim_is_gripper": ((r.get("per_dim_attribution") or {}).get("carry_dim_is_gripper")),
                "run3_reading_being_explained": {
                    "source": "runs/vla/a2_step1_prealign_20260930_run3/PREALIGN_VERIFICATION.json",
                    "winner": "shifted_action_j_plus_1", "margin_ratio": 3.4817982271312493,
                    "errors_l2": {"aligned_action_j": 0.015521, "shifted_action_j_minus_1": 0.035306,
                                 "shifted_action_j_plus_1": 0.004458, "hold_state_j": 0.08208},
                    "caliber": "run3 用的是**全 14 维** errors_l2 + 方块钉在 rest pose"},
                "conclusion_class": None, "conclusion": None,
            }
            if a1.get("discrimination") == "low" and g2.get("measurement_status") == "measured":
                attribution["conclusion_class"] = "explained_by_gripper_dim"
                attribution["conclusion"] = (
                    "run3 在 f56 的例外：全 14 维运动量 0.082 里 **99.9% 由夹爪维承载**，"
                    "臂侧 12 维在该帧的运动量低于判别阈 ⇒ **臂侧在这一帧上没有判别力**，"
                    "该例外不构成 H2（臂侧 off-by-one）的证据；它属于 R2 的对象")
            elif a1.get("verdict") == "fail":
                attribution["conclusion_class"] = "arm_offbyone_not_excluded"
                attribution["conclusion"] = "臂侧 12 维在该帧判据不过 ⇒ H2 **没有**被排除"
            else:
                attribution["conclusion_class"] = "arm12_passes_at_f56"
                attribution["conclusion"] = "臂侧 12 维在该帧判据通过 ⇒ H2 在该帧上不成立"

        measured = {
            "frames_preregistered": {"n_A": len(fs["A_d_specified_extremes"]),
                                     "n_B": len(fs["B_arm12_top_motion"]),
                                     "n_C": {k: len(v) for k, v in fs["C_magnitude_tiers"].items()},
                                     "tier_bounds": fs.get("tier_bounds")},
            "n_rows_cold": len(cold), "n_rows_warm": len(warm), "n_rows_skipped": len(skipped),
            "skipped": skipped,
            "arm12_row_judgment": {
                "n_rows_judged": len(a12), "n_high_discrimination": len(hi),
                "n_high_pass": sum(1 for j in hi if j.get("verdict") == "pass"),
                "n_high_fail": sum(1 for j in hi if j.get("verdict") == "fail"),
                "n_low_discrimination": sum(1 for j in a12 if j.get("discrimination") == "low"),
                "n_aligned_err_is_zero": sum(1 for j in a12 if j.get("aligned_err_is_zero")),
                "exceptions_head": fails[:12], "n_exceptions": len(fails),
                "frac_high_pass": (round(sum(1 for j in hi if j.get("verdict") == "pass") / len(hi), 6)
                                   if hi else None)},
            "two_box_pose_coverage": {
                "n_frames_with_two_distinct_poses": len(two_pose_frames),
                "n_frames_pass_or_na_under_both": len(both_pass),
                "frames": [{"episode_index": k[0], "frame_j": k[1], "poses": v}
                           for k, v in sorted(two_pose_frames.items())][:20]},
            "aggregate_arm12_all_rows": aggregate_by_arm(rows, "arm12", "true", only_high=False),
            "aggregate_arm12_high_rows": aggregate_by_arm(rows, "arm12", "true", only_high=True),
            "aggregate_all14_all_rows": aggregate_by_arm(rows, "all14", "true", only_high=False),
            "strict_no_gating_disclosure_arm12": strict_no_gating_disclosure(rows, "arm12", "true"),
            "strict_no_gating_disclosure_all14": strict_no_gating_disclosure(rows, "all14", "true"),
            "planted_control_arm12": planted_control_report(rows, "arm12"),
            "tier_report_arm12": tier_report(rows, "arm12"),
            "run3_f56_anomaly_attribution": attribution,
            "warm_mode": {"n_rows": len(warm),
                          "n_rows_gated_out_by_drift": sum(
                              1 for r in warm
                              if not ((r.get("warm") or {}).get("gate") or {}).get("within_gate")),
                          "drift_arm12_max": (max([float(((r.get("warm") or {}).get("drift") or {})
                                                          .get("l2_arm12", 0.0)) for r in warm])
                                              if warm else None),
                          "why": "把 `qvel=0` 这个已登记扰动源移开后的同口径复测"},
            "session_facts": {str(k): v.facts() for k, v in sorted(sessions.items())},
            "caveat_box": ("非 10 倍数帧的方块位姿只有 sidecar every-10 的前后夹逼；"
                           "两位姿之差 `box_pose_delta_l2` 已逐行落盘，退化（≈0）时不算双重验证"),
            "caveat_qvel": "cold 模每步 `qvel=0`（与 L12 冻结口径同）；warm 模另测，成对落盘",
        }
        red = []
        if not hi:
            red.append("no_arm12_high_discrimination_row_measured")
        if measured["arm12_row_judgment"]["n_high_fail"]:
            red.append(f"arm12_high_discrimination_exceptions_"
                       f"{measured['arm12_row_judgment']['n_high_fail']}")
        pc = measured["planted_control_arm12"]
        if pc["n_rows_true_pass"] == 0:
            red.append("planted_control_has_no_true_pass_row_to_flip")
        elif not pc["flipped_everywhere"]:
            red.append("planted_offbyone_control_did_not_flip")
        if two_pose_frames and len(both_pass) != len(two_pose_frames):
            red.append("two_box_pose_coverage_not_both_pass")
        L.update({"measurement_status": "measured" if (hi or skipped) else "not_measured",
                  "measured": measured, "verdict": "RED" if red else "GREEN", "red_codes": red,
                  "blocking": bool(red), "blocking_for_step1": False, "blocking_for_step2": bool(red),
                  "gpu_used": False, "policy_executed": False, "model_weights_loaded": False,
                  "mujoco_gl": os.environ.get("MUJOCO_GL"), "criteria_identity": criteria_identity(),
                  "authority": "补单六 §二（R1 指定设计）· decisions §99.2 / §100.1 · "
                               "裁定 95.3-②（机制必须由对照证明）"})
    except Exception as exc:                                          # noqa: BLE001
        import traceback
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-3000:]})
    return L


# ══════════════════════════ R2：夹爪维在**转变点**上的时序 ══════════════════════════
def r2_leg(ctx, ev_block, warm_k, limit_events=None):
    L = leg("R2_grip2_transition_alignment",
            "**只比 `grip2`（dim6/dim13）**，在夹爪动作值发生变化的转变点上逐点判 `aligned` vs `j±1`；"
            "cold（两个方块位姿）+ warm（移开 `qvel=0`）两模成对；植入 ±1 错位做负对照")
    try:
        ds, rows_by_ep = ctx["ds"], ctx["rows_by_ep"]
        state, action, ep_idx = ds["state"], ds["action"], ds["episode_index"]
        ep_cache, sessions = {}, {}

        def ep_arrays(e):
            if e not in ep_cache:
                m = ep_idx == e
                ep_cache[e] = (state[m], action[m])
            return ep_cache[e]

        def sess_for(e):
            if e not in sessions:
                sessions[e] = EnvSession(rows_by_ep[e], budget=STEP_BUDGET)
            return sessions[e]

        events = list(ev_block["picked"])
        if limit_events:
            events = events[:int(limit_events)]
        rows, skipped = [], []
        for ev in events:
            e, frames = ev["episode_index"], ev["probe_frames"]
            ekey = f"ep{e}_{ev['start_frame']}_{ev['sign']}"
            if e not in rows_by_ep:
                skipped.append(dict(ev, measurement_status="not_measured", why="该集无 sidecar/初态行"))
                continue
            es, ea = ep_arrays(e)
            nfr = int(es.shape[0])
            sess = sess_for(e)
            cold_rows = []
            for j in frames:
                if not (2 <= j < nfr - 2):
                    skipped.append(dict(ev, frame_j=j, measurement_status="not_measured",
                                        why=f"帧越界（需 2 ≤ j < {nfr - 2}）"))
                    continue
                bb, ba, bmeta = _box_pose_pair(rows_by_ep[e], j)
                if bb is None:
                    skipped.append(dict(ev, frame_j=j, measurement_status="not_measured",
                                        box_pose_meta=bmeta, why=bmeta.get("why")))
                    continue
                acts, clipped = action_bundle(ea, es, j, nfr)
                target = es[j + 1]
                moving = moving_mags(es[j], target)
                poses = [("nearest_before", bb)]
                if not bmeta.get("two_poses_degenerate"):
                    poses.append(("nearest_after", ba))
                for tag, box in poses:
                    errs = cold_probe(sess, es[j], box, acts, target)
                    row = {"event_key": ekey, "episode_index": int(e), "frame_j": int(j),
                           "direction": ev["direction"], "sign": ev["sign"],
                           "gripper_semantics": ev["gripper_semantics"],
                           "changed_dims": ev["changed_dims"], "event_start_frame": ev["start_frame"],
                           "offset_from_event_start": int(j - ev["start_frame"]),
                           "mode": "cold", "box_pose_tag": tag, "measurement_status": "measured",
                           "box_pose_xyz": [float(x) for x in box],
                           "box_pose_delta_l2": bmeta.get("box_pose_delta_l2"),
                           "two_poses_degenerate": bool(bmeta.get("two_poses_degenerate")),
                           "moving": moving, "actions_clipped": clipped,
                           "errors_by_action": compact_errs(errs, GRIP_DIMS),
                           "judge": mk_judge(errs, moving, ("grip2", "arm12"))}
                    rows.append(row)
                    cold_rows.append(row)
            # warm 链：一次滚过整个事件的 ±half_window 帧
            if frames:
                w0 = max(2, min(frames) - int(warm_k))
                bw0, _, _ = _box_pose_pair(rows_by_ep[e], w0)
                wf = [j for j in frames if 2 <= j < nfr - 2]
                res = warm_probe_chain(sess, es, ea, w0, wf, bw0,
                                       lambda jj: action_bundle(ea, es, jj, nfr)[0],
                                       lambda jj: es[jj + 1])
                for j in wf:
                    blk = res[str(j)]
                    moving = moving_mags(es[j], es[j + 1])
                    within, gate = _warm_gate(blk["drift"])
                    jd = mk_judge(blk["arms"], moving, ("grip2", "arm12"))
                    if not within:
                        for dk in jd:
                            for v in jd[dk]:
                                if jd[dk][v].get("measurement_status") == "measured":
                                    jd[dk][v]["verdict"] = "n_a_warm_drift"
                                    jd[dk][v]["why_na"] = "warm 漂移超门 ⇒ 不判（三值）"
                    rows.append({"event_key": ekey, "episode_index": int(e), "frame_j": int(j),
                                 "direction": ev["direction"], "sign": ev["sign"],
                                 "gripper_semantics": ev["gripper_semantics"],
                                 "changed_dims": ev["changed_dims"],
                                 "event_start_frame": ev["start_frame"],
                                 "offset_from_event_start": int(j - ev["start_frame"]),
                                 "mode": "warm", "box_pose_tag": "physical_evolution",
                                 "measurement_status": "measured",
                                 "box_pose_xyz": [float(x) for x in blk["box_xyz_at_fork"]],
                                 "warm": {"w0": int(w0), "warm_k": int(warm_k),
                                          "n_warmup_steps": blk["n_warmup_steps_from_w0"],
                                          "drift": round_pack(blk["drift"], 9), "gate": gate},
                                 "moving": moving,
                                 "errors_by_action": compact_errs(blk["arms"], GRIP_DIMS),
                                 "judge": jd})

        cold = [r for r in rows if r.get("mode") == "cold"]
        warm = [r for r in rows if r.get("mode") == "warm"]
        g2 = [((r.get("judge") or {}).get("grip2") or {}).get("true") for r in rows]
        g2 = [j for j in g2 if j and j.get("measurement_status") == "measured"]
        hi = [j for j in g2 if j.get("discrimination") == "high"]
        fails = []
        for r in rows:
            jd = ((r.get("judge") or {}).get("grip2") or {}).get("true") or {}
            if jd.get("verdict") == "fail":
                fails.append({"event_key": r.get("event_key"), "episode_index": r["episode_index"],
                              "frame_j": r["frame_j"], "mode": r.get("mode"),
                              "box_pose_tag": r.get("box_pose_tag"),
                              "offset_from_event_start": r.get("offset_from_event_start"),
                              "moving": jd.get("moving_magnitude"), "errors": jd.get("errors"),
                              "argmin_strict": jd.get("argmin_strict"),
                              "margin_ratio_vs_best_shifted": jd.get("margin_ratio_vs_best_shifted")})
        # 事件内聚合（补单六 §三：逐转变点报）
        per_event, ev_bad = [], []
        for ekey in sorted({r["event_key"] for r in rows}):
            sub = [r for r in rows if r["event_key"] == ekey]
            subc = [r for r in sub if r["mode"] == "cold"]
            agg_all = aggregate_by_arm(subc, "grip2", "true", only_high=False)
            agg_hi = aggregate_by_arm(subc, "grip2", "true", only_high=True)
            head = sub[0]
            rec = {"event_key": ekey, "episode_index": head["episode_index"],
                   "direction": head["direction"], "sign": head["sign"],
                   "gripper_semantics": head["gripper_semantics"],
                   "event_start_frame": head["event_start_frame"], "changed_dims": head["changed_dims"],
                   "n_rows_cold": len(subc), "n_rows_warm": len(sub) - len(subc),
                   "n_high_discrimination_cold": agg_hi["n_rows"],
                   "aggregate_grip2_all_rows": agg_all["sum_by_arm"],
                   "aligned_is_best_all_rows": agg_all["aligned_is_best"],
                   "aggregate_grip2_high_rows": agg_hi["sum_by_arm"],
                   "aligned_is_best_high_rows": (agg_hi["aligned_is_best"]
                                                 if agg_hi["n_rows"] else None),
                   "per_frame_grip2_errors": [
                       {"frame_j": r["frame_j"], "box_pose_tag": r.get("box_pose_tag"),
                        "moving_grip2": round(r["moving"]["grip2"], 9),
                        "errors": ((r.get("judge") or {}).get("grip2") or {}).get("true", {}).get("errors"),
                        "verdict": ((r.get("judge") or {}).get("grip2") or {}).get("true", {}).get("verdict")}
                       for r in sorted(subc, key=lambda x: (x["frame_j"], str(x.get("box_pose_tag"))))]}
            per_event.append(rec)
            if agg_hi["n_rows"] and not agg_hi["aligned_is_best"]:
                ev_bad.append({"event_key": ekey, "aggregate_grip2_high_rows": agg_hi["sum_by_arm"],
                               "best_arm": agg_hi["best_arm"]})
        # warm vs cold 是否同向
        cold_idx = {(r["episode_index"], r["frame_j"]): r for r in cold}
        disagree = []
        n_compared = 0
        for r in warm:
            c = cold_idx.get((r["episode_index"], r["frame_j"]))
            if not c:
                continue
            jw = ((r.get("judge") or {}).get("grip2") or {}).get("true") or {}
            jc = ((c.get("judge") or {}).get("grip2") or {}).get("true") or {}
            if jw.get("verdict") in ("pass", "fail") and jc.get("verdict") in ("pass", "fail"):
                n_compared += 1
                if jw["verdict"] != jc["verdict"]:
                    disagree.append({"episode_index": r["episode_index"], "frame_j": r["frame_j"],
                                     "cold": jc.get("verdict"), "warm": jw.get("verdict"),
                                     "cold_errors": jc.get("errors"), "warm_errors": jw.get("errors"),
                                     "warm_drift": (r.get("warm") or {}).get("drift")})
        # ── 例外归因：**只改 K 一个变量**的阶梯对照（预登记规则；**不改判据、不改 verdict**）──
        agg_all = aggregate_by_arm(cold, "grip2", "true", only_high=False)
        agg_high = aggregate_by_arm(rows, "grip2", "true", only_high=True)
        paired_arm12 = aggregate_by_arm(rows, "arm12", "true", only_high=False)
        strict_disc = strict_no_gating_disclosure(rows, "grip2", "true")
        planted = planted_control_report(rows, "grip2")
        cold_err_by_frame = {}
        for r in cold:
            jd = ((r.get("judge") or {}).get("grip2") or {}).get("true") or {}
            if jd.get("errors"):
                cold_err_by_frame.setdefault((r["episode_index"], r["frame_j"]), jd["errors"])
        exc_frames, seen_exc = [], set()
        for e in fails:
            if e.get("mode") != "cold":
                continue
            k = (e["episode_index"], e["frame_j"])
            if k in seen_exc:
                continue
            seen_exc.add(k)
            exc_frames.append(k)
            if len(exc_frames) >= 8:
                break
        ctrl_frames, seen_ctrl = [], set()
        for r in cold:
            jd = ((r.get("judge") or {}).get("grip2") or {}).get("true") or {}
            if jd.get("verdict") != "pass" or jd.get("discrimination") != "high":
                continue
            k = (r["episode_index"], r["frame_j"])
            if k in seen_ctrl or k in seen_exc:
                continue
            seen_ctrl.add(k)
            ctrl_frames.append(k)
            if len(ctrl_frames) >= 4:
                break
        if exc_frames or ctrl_frames:
            ladder_block = k_ladder_attribution(rows_by_ep, ep_arrays, exc_frames, ctrl_frames,
                                                "grip2")
        else:
            ladder_block = {"frames": [], "ks": [0, 1, 2, 4, 8], "dimset": "grip2",
                            "measurement_status": "not_measured",
                            "why": "既无例外行也无高判别 pass 行 ⇒ 阶梯不跑（不写 0 顶替）"}
        attribution = attribution_analysis(
            ladder_block, cold_err_by_frame, "grip2",
            agg_aligned_best=bool(agg_all["aligned_is_best"] and agg_high["aligned_is_best"]),
            planted_flipped=bool(planted["flipped_everywhere"]),
            event_agg_all_aligned_first=bool(not ev_bad))

        by_dir, by_sign = {}, {}
        for ev in events:
            by_dir[ev["direction"]] = by_dir.get(ev["direction"], 0) + 1
            by_sign[ev["sign"]] = by_sign.get(ev["sign"], 0) + 1
        measured = {
            "transition_points_in_dataset": ev_block["all_events_in_dataset"],
            "events_by_dir_sign_all": ev_block["events_by_dir_sign_all"],
            "n_events_probed": len(events), "n_events_by_direction": by_dir,
            "n_events_by_sign": by_sign,
            "gripper_polarity": ev_block["gripper_polarity_source"],
            "n_rows_cold": len(cold), "n_rows_warm": len(warm), "n_skipped": len(skipped),
            "skipped_head": skipped[:8],
            "grip2_row_judgment": {
                "n_rows_judged": len(g2), "n_high_discrimination": len(hi),
                "n_high_pass": sum(1 for j in hi if j.get("verdict") == "pass"),
                "n_high_fail": sum(1 for j in hi if j.get("verdict") == "fail"),
                "n_low_discrimination": sum(1 for j in g2 if j.get("discrimination") == "low"),
                "n_warm_drift_na": sum(1 for j in g2 if j.get("verdict") == "n_a_warm_drift"),
                "n_aligned_err_is_zero": sum(1 for j in g2 if j.get("aligned_err_is_zero")),
                "frac_high_pass": (round(sum(1 for j in hi if j.get("verdict") == "pass") / len(hi), 6)
                                   if hi else None),
                "exceptions_head": fails[:16], "n_exceptions": len(fails)},
            "per_event": per_event,
            "n_events_aggregate_not_aligned_first": len(ev_bad),
            "events_aggregate_not_aligned_first": ev_bad[:10],
            "global_aggregate_grip2_all_rows": agg_all,
            "global_aggregate_grip2_high_rows": agg_high,
            "paired_arm12_reading_on_same_frames": paired_arm12,
            "strict_no_gating_disclosure_grip2": strict_disc,
            "planted_control_grip2": planted,
            "exception_attribution": attribution,
            "warm_vs_cold": {"n_rows_compared": n_compared, "n_disagreements": len(disagree),
                             "disagreements_head": disagree[:10],
                             "n_warm_gated_out_by_drift": sum(
                                 1 for r in warm
                                 if not ((r.get("warm") or {}).get("gate") or {}).get("within_gate")),
                             "why": "cold 模每步 `qvel=0`；warm 模把它移开 ⇒ 两模同向才叫稳"},
            "session_facts": {str(k): v.facts() for k, v in sorted(sessions.items())},
            "material_divergence_window_registered": (
                "D 在 §99.2/§100.1 实测的材料性分歧集中在 f50–f130（ep0 f90 / ep19 f50 / ep20 f90）；"
                "本腿的转变点探针覆盖各事件的 start−3 … start+3，落盘 `offset_from_event_start` 供对读"),
            "caveat_gripper_normalizer": (
                "L5（run4）已登记：夹爪维**动作**分布（2.71% 低于 −1，集中在 dim6 19.12% / dim13 18.79%）"
                "没被 C2 归一化器的 q01/q99 覆盖 ⇒ 那是**归一化器覆盖面**问题（H1 的另一半），"
                "**不是**本腿要判的时序问题；本腿只在既有 npz `a84a26079550` 上做时序探针，"
                "不重生成 stats（裁定 100.8-C2-②）"),
        }
        red = []
        if not hi:
            red.append("no_grip2_high_discrimination_row_measured")
        if measured["grip2_row_judgment"]["n_high_fail"]:
            red.append(f"grip2_high_discrimination_exceptions_"
                       f"{measured['grip2_row_judgment']['n_high_fail']}")
        if ev_bad:
            red.append(f"event_aggregate_not_aligned_first_in_{len(ev_bad)}_events")
        ga = measured["global_aggregate_grip2_all_rows"]
        if ga["n_rows"] and not ga["aligned_is_best"]:
            red.append("global_aggregate_grip2_not_aligned_first")
        pc = measured["planted_control_grip2"]
        if pc["n_rows_true_pass"] == 0:
            red.append("planted_control_has_no_true_pass_row_to_flip")
        elif not pc["flipped_everywhere"]:
            red.append("planted_offbyone_control_did_not_flip")
        if n_compared and disagree:
            red.append(f"warm_disagrees_with_cold_in_{len(disagree)}_rows")
        for tag, cnt in (("direction", by_dir), ("sign", by_sign)):
            for k, v in cnt.items():
                if v < 5:
                    red.append(f"insufficient_transition_points_by_{tag}_{k}_{v}_lt_5")
        L.update({"measurement_status": "measured" if (hi or skipped) else "not_measured",
                  "measured": measured, "verdict": "RED" if red else "GREEN", "red_codes": red,
                  "blocking": bool(red), "blocking_for_step1": False, "blocking_for_step2": bool(red),
                  "gpu_used": False, "policy_executed": False, "model_weights_loaded": False,
                  "mujoco_gl": os.environ.get("MUJOCO_GL"), "criteria_identity": criteria_identity(),
                  "authority": "补单六 §三（R2 指定设计）· decisions §99.2 / §100.1 / §100.8-A2-②"})
    except Exception as exc:                                          # noqa: BLE001
        import traceback
        L.update({"measurement_status": "not_measured", "verdict": "RED", "blocking": True,
                  "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-3000:]})
    return L


# ══════════════════ 判据可核性（补单六 §四 / decisions §100.3-（c）（d））══════════════════
PRE_REG_NAME = "PRE_REGISTRATION_R1R2.json"
VERDICT_NAME = "R1R2_ALIGNMENT_VERDICT.json"
JUDGED_SCRIPTS = (SELF_REL, PRE_REL)


def snapshot_judging_scripts(out_dir: pathlib.Path, tag: str) -> list:
    """把**判据路径上的每一个脚本**的当前字节拷进本 run 目录。

    对症的缺陷 = `OPEN-L12-CRITERIA-DRIFT`（decisions §100.3）：`run3 → run4` 之间判据脚本
    改了 103 行却没留前像 ⇒ 改前字节不可复得。Ⅰ 类口径
    `judging_script_change_requires_before_image_and_criteria_identity` 要求「改动即须在同一个
    run 目录留改前字节 + 写 `criteria_identity`」。本件的做法比要求更靠前一步：
    **每一跑都把判据字节与判词同批落盘**，于是任何后续改动的前像必然在盘。
    """
    dst_dir = out_dir / "judging_script_snapshots"
    dst_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for rel in JUDGED_SCRIPTS:
        src = REPO / rel
        sha = sha12(src)
        name = pathlib.Path(rel).name
        dst = dst_dir / f"{name}.{tag}.{sha}"
        prior = sorted(q for q in dst_dir.glob(f"{name}.*") if q.is_file())
        prior_other = [q for q in prior if sha12(q) != sha]
        elsewhere = sorted(
            q for q in (REPO / "runs" / "vla").glob(f"*/judging_script_snapshots/{name}.*")
            if q.is_file() and sha12(q) != sha and q.resolve() != dst.resolve())
        if not dst.exists():
            shutil.copy2(src, dst)
        ide = identity(rel)
        out.append({
            "path": rel, "sha256_12": sha, "bytes": ide.get("bytes"),
            "n_lines_wc": ide.get("n_lines_wc"), "n_lines_splitlines": ide.get("n_lines_splitlines"),
            "n_lines_caliber": N_LINES_CALIBER, "measurement_status": ide.get("measurement_status"),
            "snapshot_path": str(dst.relative_to(REPO)), "snapshot_sha256_12": sha12(dst),
            "snapshot_bytes_match_source": bool(sha12(dst) == sha),
            "before_image_status": ("captured_in_this_run_dir" if prior_other
                                    else ("captured_in_sibling_run_dir" if elsewhere
                                          else "n_a_first_snapshot_of_these_bytes")),
            "before_image_paths": [str(p.relative_to(REPO)) for p in prior_other],
            "before_image_paths_elsewhere": [str(q.relative_to(REPO)) for q in elsewhere][:8],
            "before_image_scan_scope": ("`runs/vla/*/judging_script_snapshots/<name>.*`"
                                        "（glob，有界；**不做 `find /`**，见 decisions §100.6）"),
            "modified_by_this_leg": bool(rel == SELF_REL),
            "note": ("`a2_step1_prealign_verify.py` **只 import 复用、一个字节都没改**"
                     "（补单五 §五 治理冻结：不得新增第 13 条腿、不得再改 L12 判据）"
                     if rel == PRE_REL else "本件是 R1/R2 的判据脚本（新件）"),
        })
    return out


def load_or_write_prereg(out_dir: pathlib.Path, builder, allow_rewrite: bool, reason: str):
    """预登记：**默认拒绝重写**；要重写必须先留前像 + 给理由（改写理由落盘）。"""
    p = out_dir / PRE_REG_NAME
    if p.exists():
        cur = sha12(p)
        if not allow_rewrite:
            doc = json.loads(p.read_text(encoding="utf-8"))
            return doc, {"path": str(p.relative_to(REPO)), "status": "reused_existing_refused_rewrite",
                         "sha256_12": cur, "bytes": p.stat().st_size,
                         "why": "预登记默认不可重写（先登记后测量；改登记＝改判据）",
                         "flag_used": False}
        bi_dir = out_dir / "before_images"
        bi_dir.mkdir(parents=True, exist_ok=True)
        bi = bi_dir / f"{PRE_REG_NAME}.before_{cur}"
        if not bi.exists():
            shutil.copy2(p, bi)
        doc = builder()
        info = write_json(p, doc)
        return doc, {"path": info["path"], "status": "rewritten_with_before_image",
                     "before_image": str(bi.relative_to(REPO)), "before_image_sha256_12": cur,
                     "rewrite_reason": reason, "flag_used": True, **{
                         k: info[k] for k in ("sha256_12", "bytes", "n_lines_wc",
                                              "n_lines_splitlines")}}
    doc = builder()
    info = write_json(p, doc)
    return doc, {"path": info["path"], "status": "written_first_time",
                 **{k: info[k] for k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                 "n_lines_caliber": N_LINES_CALIBER}


LEG_DIMSET = (("R1_arm12_offbyone_exclusion", "arm12"), ("R2_grip2_transition_alignment", "grip2"))


def planted_teeth(legs: dict, requested: list) -> tuple:
    """把两条腿里的植入错位负对照**提升为牙**（牙不咬 ⇒ 整件不 ok）。

    **三值**：该腿这一跑没被请求 ⇒ **不生牙**（另记 `skipped`），不生一颗注定 `bite=false`
    的牙去污染 `all_bite`；跑了却读不到 ⇒ 才算不咬。
    """
    teeth, skipped = [], []
    for leg_id, dimset in LEG_DIMSET:
        tid = f"TP_{leg_id.split('_')[0]}_planted_offbyone_must_flip_{dimset}"
        if leg_id not in legs:
            skipped.append({"tooth_id": tid, "measurement_status": "not_measured",
                            "why": f"本跑未请求该腿（stages={requested}）⇒ 不生牙，也不写 0 顶替"})
            continue
        m = (legs.get(leg_id) or {}).get("measured")
        pc = (m or {}).get(f"planted_control_{dimset}")
        if not pc:
            teeth.append({"tooth_id": tid, "measurement_status": "not_measured", "bite": False,
                          "expect": "植入 ±1 错位后判据必须翻",
                          "why": f"{leg_id} 没有 planted_control 读数（腿未跑或结构性失败）"})
            continue
        teeth.append({"tooth_id": tid, "measurement_status": "measured",
                      "expect": ("真判据 pass 的每一行，植入 +1 与 −1 后都**不再** pass"
                                 "（否则判据没有分辨力）"),
                      "bite": bool(pc.get("flipped_everywhere")),
                      "detail": {k: v for k, v in pc.items() if k != "offenders_head"},
                      "offenders_head": pc.get("offenders_head", [])[:4]})
    return teeth, skipped


def write_pending_commit_request(out_dir: pathlib.Path, snaps: list, doc_identity: dict) -> dict:
    """补单六 §四-① 的处置：A2 **不** `git commit`（B2 是 git 单写者，裁定 49.6/69.1/81.2），
    改为落一份**机器可读的入库请求**，等下次经授权的提交带走。"""
    paths = [{"path": s["path"], "sha256_12": s["sha256_12"], "bytes": s["bytes"],
              "n_lines_wc": s["n_lines_wc"], "n_lines_splitlines": s["n_lines_splitlines"],
              "git_status_expected": "?? （从未入库）", "why": (
                  "判据脚本必须入库，否则 `criteria_drift` 无法逐字段比对（decisions §100.3-（c）-i）"
                  if s["path"] == PRE_REL else
                  "R1/R2 的判据脚本（本件），同批入库以免重犯 `OPEN-L12-CRITERIA-DRIFT`")}
             for s in snaps]
    req = {"artifact": "a2_pending_commit_request", "as_of": now_iso(),
           "requested_by": "A2", "git_single_writer": "B2（A2 不 git commit）",
           "authority": "补单六 §四-①（让当前版本入库，下次经授权的提交带走）· decisions §100.3-（c）",
           "paths": paths, "verdict_artifact": doc_identity,
           "note": ("这份请求**不**授权任何提交；它只是把「哪些字节必须被下一次授权提交带走」"
                    "写成机器可读的一件，免得再出现『改前字节不可复得』")}
    return write_json(out_dir / "PENDING_COMMIT_REQUEST.json", req)


# ══════════════════════════════════ main ══════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="A2 / R1+R2 —— L12 的两条残差腿（CPU-only）")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--stages", default="prereg,r1,r2,report")
    ap.add_argument("--dataset-dir", default=PRE.P_DS)
    ap.add_argument("--tier-episodes", default="0,10,19,20,30,39",
                    help="R1 三档抽样的候选集（10 的倍数帧才有权威方块位姿）")
    ap.add_argument("--n-per-tier", type=int, default=8, help="补单五 §三-（c）：每档 8 帧")
    ap.add_argument("--b-episodes", default="0,19,20,39",
                    help="R1 Set B（arm12 真·高运动量帧）的集号；默认 = `run3`/`run4` 的 L12 探测集")
    ap.add_argument("--r2-episodes-forward", default="0,10,19")
    ap.add_argument("--r2-episodes-reverse", default="20,30,39")
    ap.add_argument("--n-events-per-dir", type=int, default=9,
                    help="每个集方向取几个转变事件（≥5 是补单六 §三 的下限）")
    ap.add_argument("--half-window", type=int, default=3, help="每个转变点 ±3 帧（补单六 §三）")
    ap.add_argument("--warm-k", type=int, default=4, help="warm 模的预热步数")
    ap.add_argument("--limit-events", type=int, default=0, help=">0 时只跑前 N 个事件（计时/调试用）")
    ap.add_argument("--skip-warm", action="store_true")
    ap.add_argument("--allow-prereg-rewrite", action="store_true")
    ap.add_argument("--prereg-rewrite-reason", default="")
    args = ap.parse_args()

    stages = [s.strip() for s in str(args.stages).split(",") if s.strip()]
    known = {"prereg", "r1", "r2", "report"}
    bad = [s for s in stages if s not in known]
    if bad or not stages:
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "error": f"未知 stage {bad}",
                          "known": sorted(known)}, ensure_ascii=False))
        return EXIT_USAGE
    if args.allow_prereg_rewrite and not args.prereg_rewrite_reason.strip():
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE,
                          "error": "重写预登记必须给 --prereg-rewrite-reason（理由要落盘）"},
                         ensure_ascii=False))
        return EXIT_USAGE

    out_dir = pathlib.Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()
    load_start = PBG.gpu_window_readings()
    snaps = snapshot_judging_scripts(out_dir, datetime.now(CST).strftime("%Y%m%d_%H%M%S"))

    doc: dict = {
        "artifact": "a2_r1_r2_alignment_residual",
        "as_of": now_iso(),
        "producer": {"script": SELF_REL,
                     **{k: v for k, v in identity(SELF_REL).items()
                        if k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                     "python": sys.version.split()[0], "venv": sys.executable},
        "n_lines_caliber": N_LINES_CALIBER,
        "stages_requested": stages,
        "purpose": ("裁定 100.1 点名的两条残差腿：**R1** 排除 H2（高运动量帧的臂侧 off-by-one，"
                    "`run4` 的帧集与 `run3` 的极值帧交集为空 ⇒ 没测到）；**R2** 判夹爪维 dim6/dim13 "
                    "在**转变点**上的时间对齐（第 2 步的真前置）"),
        "authority": [
            "rl_harness_supervision/d_handoff_to_a2_20260930.md 补单六 §二（R1）/§三（R2）/§四（判据可核性）/§五（顺序与停点）",
            "work/decisions/decisions_20260929.md §99.2（H1/H2/H3 + 三个对照臂）· §100.1（run4 亲核 + R1/R2 指定设计）",
            "§100.3（OPEN-L12-CRITERIA-DRIFT：判据脚本入库 + criteria_identity 块）· §100.8-A2-①②③④",
            "裁定 99.3（preregistered_criterion_must_be_dry_run_on_the_object）",
            "裁定 95.3-②（机制必须由对照证明，不靠一致的故事）· 裁定 46（能力声明禁令）",
            "裁定 98.5（sha 是唯一约束性判据；行数必须点名口径；裸 n_lines 禁用）",
        ],
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "model_weights_loaded": False, "success_rate_column": "not_an_exit_criterion",
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "machine_load_at_start": load_start,
        "criteria_identity": criteria_identity(),
        "judging_script_snapshots": snaps,
        "stop_rule_on_red": ("R1 或 R2 任一 RED ⇒ **不申报 GPU 窗口、不开 BC**，报 D 等裁"
                            "（补单六 §五 的执行顺序写死：R1+R2 → 补 §四 两件 → 登记窗口 → 跑第 1 步）"),
        "stop_rule_superseded_by": {
            "ruling": "裁定 101.2 / 补单七 §一-1（2026-09-30 17:2x）",
            "effect": ("**R1/R2 的上卡前置地位已被 D 撤销**：R2 并入 Step 1 的产出④（夹爪转变帧误差）、"
                       "R1 并入产出③（「没有未解释的系统性偏移」的取证）⇒ 本件的 RED **不再**自动挡住窗口，"
                       "处置权在 D；上面那条 `stop_rule_on_red` 是**旧单（补单六）**的口径，保留原文以便对账"),
        },
        "self_defects_found_and_fixed_in_this_script": [
            {"id": "D1_dangling_else_wiped_legs",
             "what": ("一个悬空 `else: doc[\"legs\"] = {}` 把已跑完的两条腿从判词件里擦掉，"
                      "而 `summary.ok` 仍是 `true`（`n_legs=0` 却 `all_bite=true`）"),
             "how_caught": "**A2 自查**：`runs/vla/a2_r1_r2_alignment_20260930_dbg2` 打印出 `legs={}` "
                           "与 `n_teeth=13` 自相矛盾 ⇒ 当场追查",
             "fix": "改成显式分支 + 新增结构守卫牙 `TS_requested_leg_must_be_present_*`（腿不在 ⇒ 牙不咬 ⇒ 整件不 ok）",
             "class": "Ⅲ 类自纠（未产生任何对外判词；dbg2 的判词件已留在盘上供核）"},
            {"id": "D2_stable_copy_sha_stale",
             "what": ("稳定名副本写完后又追加 `pending_commit_request` 再写一遍 ⇒ 件内声明的 "
                      "`verdict_artifact.sha256_12` 与盘上字节不符（run1：件内 `f13dac4be060` vs "
                      "盘上 `f3f8cc8e0516`）"),
             "how_caught": "**A2 自查**：把工具报的 sha 与 `sha256sum` 并排比对",
             "fix": "调整写入顺序（先算 `pending_commit_request`，再写稳定名副本，**不再二次重写**）",
             "class": ("Ⅰ 类同源（身份对账）——裁定 98.5：`sha256[:12]` 是唯一约束性判据 ⇒ "
                       "件内 sha 与盘上字节不符就是硬缺陷，即使内容没错")},
            {"id": "D3_per_dim_attribution_wrong_key",
             "what": ("`per_dim_attribution` 用判据臂名 `aligned_action_j` 去索引**按动作键**存的误差表 "
                      "⇒ `carry_dim_of_aligned` 恒为 `null`（run1 的 f56 归因里「承载维」是空的，"
                      "而补单五 §三 恰恰要求点名承载维）"),
             "how_caught": "**A2 自查**：读 run1 的 `run3_f56_anomaly_attribution` 时发现 `carry_dim=null`",
             "fix": "显式传 `aligned_key=\"a_j\"` + 落 `action_key_map` 让读者能自己映射",
             "class": "Ⅲ 类自纠（结论未受影响：`grip_share=0.9986` 那条独立读数已足以支撑归因）"},
        ],
        "identities": {},
        "legs": {},
    }
    for tag, rel in (("c2_stats", PRE.P_C2_STATS), ("npz_source", PRE.P_NPZ),
                     ("demo_manifest", PRE.P_MANIFEST),
                     ("dataset_info", str(pathlib.Path(args.dataset_dir) / "meta" / "info.json")),
                     ("run3_prealign_verdict",
                      "runs/vla/a2_step1_prealign_20260930_run3/PREALIGN_VERIFICATION.json"),
                     ("run4_prealign_verdict",
                      "runs/vla/a2_step1_prealign_20260930_run4/PREALIGN_VERIFICATION.json"),
                     ("b2_scripted_expert", PRE.P_EXPERT),
                     ("harness_env_gym_aloha", "harness/env_gym_aloha.py")):
        doc["identities"][tag] = identity(rel)

    failures: list[str] = []
    ctx: dict = {}
    try:
        ctx["ds"] = PRE.read_dataset_arrays(REPO / args.dataset_dir)
        ctx["init_states"] = PRE.build_demo_initial_states(ctx)
        ctx["rows_by_ep"] = {int(r["episode_index"]): r for r in ctx["init_states"]["rows"]}
    except Exception as exc:                                          # noqa: BLE001
        failures.append(f"input_load_failed:{type(exc).__name__}: {exc}")
        doc["input_load_error"] = failures[-1]

    tier_eps = [int(x) for x in str(args.tier_episodes).split(",") if x.strip() != ""]
    b_eps = [int(x) for x in str(args.b_episodes).split(",") if x.strip() != ""]
    fwd_eps = [int(x) for x in str(args.r2_episodes_forward).split(",") if x.strip() != ""]
    rev_eps = [int(x) for x in str(args.r2_episodes_reverse).split(",") if x.strip() != ""]

    def build_prereg():
        dry = dry_teeth()
        return {
            "artifact": "a2_r1_r2_pre_registration", "as_of": now_iso(),
            "registered_by": "A2", "registered_before_measurement": True,
            "criteria_constants_sha256_12": criteria_constants_sha(),
            "criteria_constants": CRITERIA,
            "criteria_identity": criteria_identity(),
            "dry_run_of_criterion_on_objects": dry,
            "r1_frame_sets": build_r1_frame_sets(ctx["ds"], ctx["rows_by_ep"], tier_eps,
                                                 args.n_per_tier, b_eps),
            "r2_transition_events": build_r2_events(ctx["ds"], ctx["rows_by_ep"],
                                                    {"forward": fwd_eps, "reverse": rev_eps},
                                                    args.n_events_per_dir, args.half_window),
            "probe_design": {
                "modes": {"cold": "L12 冻结口径：写 (state[j], box, qvel=0) → 一步",
                          "warm": f"从 state[j−{args.warm_k}] 用真动作滚到 j 再分叉（移开 qvel=0）"},
                "box_poses": ["nearest_before = traj[j//10]", "nearest_after = traj[ceil(j/10)]"],
                "box_pose_degeneracy_is_recorded": True,
                "arms_per_probe": ["a_jm2", "a_jm1", "a_j", "a_jp1", "a_jp2", "hold"],
                "views_share_one_simulation": True,
                "env_step_budget": STEP_BUDGET,
                "env_truncation_guard": "每次 step 后查 `env_truncated`，命中即换新 env 并记数",
                "warm_k": int(args.warm_k), "half_window": int(args.half_window),
                "skip_warm": bool(args.skip_warm), "limit_events": int(args.limit_events)},
            "assertions_verbatim": {
                "R1": CRITERIA["r1_assertion"], "R2": CRITERIA["r2_assertion"],
                "negative_control": CRITERIA["negative_control_rule"],
                "source": "补单六 §二（R1 断言原文：两个位姿下 aligned 都是 arm12 的 argmin，"
                          "且对两个 shifted 的 margin ≥ 1.2）· §三（R2：断言与 margin 必须预登记，"
                          "并且先在对象上干跑；负对照 = 植入 ±1 错位必须翻）"},
            "stop_rule_on_red": doc["stop_rule_on_red"],
            "not_a_capability_claim": "本登记不含任何 policy 指标（裁定 46）",
        }

    prereg, prereg_info = ({}, {"status": "not_requested"})
    if not failures and ("prereg" in stages or any(s in stages for s in ("r1", "r2"))):
        try:
            prereg, prereg_info = load_or_write_prereg(out_dir, build_prereg,
                                                       bool(args.allow_prereg_rewrite),
                                                       args.prereg_rewrite_reason)
        except Exception as exc:                                      # noqa: BLE001
            failures.append(f"prereg_failed:{type(exc).__name__}: {exc}")
            prereg_info = {"status": "failed", "error": failures[-1]}
    doc["preregistration"] = prereg_info

    mismatch = None
    if prereg:
        declared = prereg.get("criteria_constants_sha256_12")
        mismatch = bool(declared != criteria_constants_sha())
        doc["criteria_identity"]["preregistration_constants_sha256_12"] = declared
        doc["criteria_identity"]["preregistration_constants_match"] = (not mismatch)
        if mismatch:
            failures.append(f"prereg_constants_sha_mismatch:declared={declared}:"
                            f"now={criteria_constants_sha()}")
    if any(s in stages for s in ("r1", "r2")) and not prereg:
        failures.append("preregistration_missing_cannot_measure")
    if failures:
        doc["input_failures"] = failures

    fs_used = (prereg or {}).get("r1_frame_sets") or {}
    ev_used = (prereg or {}).get("r2_transition_events") or {}
    dry_now = dry_teeth()
    dry_prereg = (prereg or {}).get("dry_run_of_criterion_on_objects") or {}
    dry_reproducible = bool(dry_now["all_bite"]) and bool(
        dry_now["n_bite"] == dry_prereg.get("n_bite") or not dry_prereg)
    doc["selftest"] = {
        "dry_teeth": dry_now,
        "dry_teeth_reproduce_preregistered_run": {
            "prereg_n_teeth": dry_prereg.get("n_teeth"), "prereg_n_bite": dry_prereg.get("n_bite"),
            "now_n_teeth": dry_now["n_teeth"], "now_n_bite": dry_now["n_bite"],
            "reproducible": dry_reproducible,
            "why": "判据是纯函数 ⇒ 干跑必须可复现；不可复现说明常量或实现被动过"},
        "planted_teeth": [],
    }

    if not failures:
        if "r1" in stages:
            doc["legs"]["R1_arm12_offbyone_exclusion"] = r1_leg(ctx, fs_used, int(args.warm_k))
        if "r2" in stages:
            doc["legs"]["R2_grip2_transition_alignment"] = r2_leg(
                ctx, ev_used, int(args.warm_k),
                (int(args.limit_events) if args.limit_events else None))
    else:
        doc["legs"] = {}
    pt, ps = planted_teeth(doc["legs"], [s for s in stages if s in ("r1", "r2")])
    doc["selftest"]["planted_teeth"] = pt
    doc["selftest"]["planted_teeth_skipped"] = ps
    attr_teeth = []
    r2_measured = ((doc["legs"].get("R2_grip2_transition_alignment") or {}).get("measured") or {})
    anchor = (r2_measured.get("exception_attribution") or {}).get("anchor_tooth")
    if anchor:
        attr_teeth.append(anchor)
    elif "r2" in stages and not failures:
        attr_teeth.append({"tooth_id": "TK_k_ladder_anchor_must_reproduce_cold",
                           "measurement_status": "not_measured", "bite": False,
                           "why": "R2 跑了却读不到 `anchor_tooth` ⇒ 不写 0 顶替"})
    doc["selftest"]["attribution_teeth"] = attr_teeth
    doc["selftest"]["attribution_teeth_skipped"] = (
        [] if attr_teeth else
        [{"tooth_id": "TK_k_ladder_anchor_must_reproduce_cold", "measurement_status": "not_measured",
          "why": f"本跑未请求 R2（stages={stages}）⇒ 不生牙"}])

    # ── 结构守卫牙：**请求了的腿必须在判词件里**。这一颗钉住的是本件自己刚出过的一个静默错：
    #    一个悬空 `else: doc["legs"] = {}` 把两条腿擦空，而 `summary.ok` 仍然是 `true`
    #    （`a2_r1_r2_alignment_20260930_dbg2` 亲见：`n_legs=0` 却 `all_bite=true`）。
    #    修法是把它变成显式守卫：腿不在 ⇒ 牙不咬 ⇒ 整件不 ok。
    expected_legs = {"r1": "R1_arm12_offbyone_exclusion", "r2": "R2_grip2_transition_alignment"}
    structural = []
    for stage_key, leg_id in expected_legs.items():
        if stage_key not in stages:
            continue
        got = doc["legs"].get(leg_id)
        structural.append({
            "tooth_id": f"TS_requested_leg_must_be_present_{stage_key}",
            "expect": f"{leg_id} 在判词件里，且 measurement_status=measured（除非输入装载失败）",
            "measurement_status": "measured",
            "bite": bool(failures or (got is not None
                                      and got.get("measurement_status") == "measured")),
            "detail": {"leg_id": leg_id, "present": got is not None,
                       "measurement_status": (got or {}).get("measurement_status"),
                       "verdict": (got or {}).get("verdict"),
                       "input_failures": failures}})
    doc["selftest"]["structural_teeth"] = structural

    teeth = (list(doc["selftest"]["dry_teeth"]["teeth"])
             + list(doc["selftest"]["planted_teeth"])
             + list(doc["selftest"]["structural_teeth"])
             + list(doc["selftest"]["attribution_teeth"]))
    n_teeth = len(teeth)
    n_bite = sum(1 for t in teeth if t.get("bite"))
    n_not_measured_teeth = sum(1 for t in teeth if t.get("measurement_status") == "not_measured")
    legs = list(doc["legs"].values())
    red = [L["leg_id"] for L in legs if L.get("verdict") == "RED"]
    blocking = [L["leg_id"] for L in legs if L.get("blocking")]
    nm = [L["leg_id"] for L in legs if L.get("measurement_status") != "measured"]
    doc["summary"] = {
        "n_legs": len(legs), "n_measured_legs": len(legs) - len(nm),
        "not_measured_leg_ids": nm, "red_leg_ids": red, "blocking_leg_ids": blocking,
        "red_codes": {L["leg_id"]: L.get("red_codes") for L in legs if L.get("red_codes")},
        "selftest_n_teeth": n_teeth, "selftest_n_bite": n_bite, "selftest_n_fail": n_teeth - n_bite,
        "selftest_n_not_measured_teeth": n_not_measured_teeth,
        "selftest_all_bite": bool(n_teeth > 0 and n_bite == n_teeth),
        "dry_teeth_reproducible": dry_reproducible,
        "criteria_constants_sha256_12": criteria_constants_sha(),
        "preregistration_constants_match": (not mismatch) if prereg else None,
        "input_failures": failures,
        "wall_s": round(time.perf_counter() - t_start, 3),
        "ok": bool(not red and not blocking and not nm and not failures
                   and n_teeth > 0 and n_bite == n_teeth and dry_reproducible and not mismatch),
        "exit_code_policy": ("0 = 全 measured 且无阻塞红且牙全咬 · 1 = 有阻塞红或牙不咬 · "
                             "3 = 存在 not_measured · 2 = 用法/环境错"),
        "no_capability_claim": ("本件不含任何 policy 指标；所有 GREEN **只指接口/口径判词**"
                                "（裁定 46）。`policy_executed=false`、`gpu_used=false`、"
                                "`model_weights_loaded=false`。"),
        "blind_dims_caveat": (f"盲点维 {BLIND_DIMS} 是 C2 的 94.3 Ⅱ 类登记项，**不得**当能力判据，"
                              "也不得把 per-dim 结论写成全 14 维结论"),
        "stop_rule_on_red": doc["stop_rule_on_red"],
    }
    doc["machine_load_at_end"] = PBG.gpu_window_readings()
    doc["three_net_at_start"] = None

    txt = json.dumps(doc, ensure_ascii=False, indent=2, default=jdefault) + "\n"
    doc["summary"]["bare_n_lines_tooth"] = bare_n_lines_tooth(txt.replace(
        '"bare_n_lines_tooth": null', ''))
    if not doc["summary"]["bare_n_lines_tooth"]["bite"]:
        doc["summary"]["ok"] = False

    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    main_path = out_dir / f"R1R2_ALIGNMENT_{ts}.json"
    doc["self_identity"] = write_json(main_path, doc)
    doc["pending_commit_request"] = write_pending_commit_request(out_dir, snaps, doc["self_identity"])
    doc["self_identity_note"] = (
        "`self_identity` 指上面那份**带时间戳**的产物；本件（稳定名副本）与它的字节差只在 "
        "`pending_commit_request` / `self_identity*` 三个键。**稳定名副本只写一次**（写完不再追加），"
        "所以下面 `stable_copy_identity` 报的 sha 就是盘上字节 —— 修的是自报缺陷 D2")
    fin = write_json(out_dir / VERDICT_NAME, doc)
    doc["stable_copy_identity"] = fin

    if doc["summary"]["ok"]:
        code = EXIT_OK
    elif red or blocking or failures or n_teeth == 0 or n_bite != n_teeth or mismatch:
        code = EXIT_BLOCKING_RED
    else:
        code = EXIT_NOT_MEASURED
    print(json.dumps({
        "ok": doc["summary"]["ok"], "exit_code": code, "stages": stages,
        "legs": {L["leg_id"]: {"verdict": L.get("verdict"),
                               "measurement_status": L.get("measurement_status"),
                               "red_codes": L.get("red_codes")} for L in legs},
        "selftest": {"n_teeth": n_teeth, "n_bite": n_bite, "all_bite": doc["summary"]["selftest_all_bite"]},
        "criteria_constants_sha256_12": criteria_constants_sha(),
        "preregistration": prereg_info,
        "verdict_artifact": fin, "timestamped_artifact": doc["self_identity"],
        "wall_s": doc["summary"]["wall_s"],
        "gpu_used": False, "policy_executed": False, "capability_claim": False,
    }, ensure_ascii=False, indent=2, default=jdefault))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as _exc:                                         # noqa: BLE001
        import traceback
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE,
                          "error": f"{type(_exc).__name__}: {_exc}",
                          "traceback_tail": traceback.format_exc()[-2000:],
                          "why": "结构性失败 ⇒ exit 2（用法/环境错），不落半成品判词"},
                         ensure_ascii=False, indent=2))
        sys.exit(EXIT_USAGE)
