#!/usr/bin/env python3
"""A2 / 六步序列**第 1 步**（裁定 95.2 · D→A2 补单四 §三）：小量示范过拟合 + 从示范初态闭环执行。

## 本件回答的那一个问题（裁定 95.2 第 1 行原文）
「**数据能否被当前模型学到？**」—— 硬判据（同一行，不重新解释）：
「过拟合臂 loss 必须显著下降且**动作逐维对得上示范**（含夹爪开合时刻）；**从示范初态**闭环执行的
推进度必须 > 随机基线」。

## 阶段化（`--stages`，逗号分隔；GPU 阶段 = probe/train/rollout）
| 阶段 | 上卡 | 产物 |
|---|---|---|
| `admission` | 否 | `BC_ADMISSION_STEP1_<ts>.json`（**复用** `harness/bc_admission_gate.consume_c2_broadcast`，不许自己 glob）+ A2 自己的牙：先落腿 `PREALIGN_VERIFICATION.json` 必须 `ok=true` |
| `prereg` | 否 | `PRE_REGISTRATION.json`（裁定 95.5-①②③：整条 episode 划分 / stats 冻结 / **checkpoint 选择规则开跑前预登记**） |
| `cache` | 否 | `cache/samples_{train,val}.npz` + `CACHE_MANIFEST.json`（把 PNG 解码这段**纯 CPU** 开销挪到 GPU 窗口之外，免得污染窗口的 loadavg 摆动判据） |
| `probe` | **是** | `PROBE1STEP.json`（实测显存峰值/单步墙钟 ⇒ 按**预登记的规则**定 batch/梯度检查点，不是拍脑袋） |
| `train` | **是** | `TRAIN_REPORT.json` + `checkpoints/step_NNNNNN/` + `CHECKPOINT_SELECTION.json` |
| `rollout` | **是** | `ROLLOUT_REPORT.json` + `episode_<arm>_<ep>.json` |
| `report` | 否 | `STEP1_RESULT.json` + `STEP1_SIX_QUESTIONS.json`（裁定 95.6 六问） |

## 上卡纪律（裁定 94.9-1② / 96.1-③ / 97.8-RR4 / 98.9-②；补单四 §三）
- **先申报后上卡**：`daily_report.md` 里必须有 A2 的 GPU 窗口申报行，且**行内写入口脚本名**
  （RR1(a)：E 收到后一行补 `GPU_INTENT_PATTERNS` 词表，不必再问 D）。用 `--declaration-line` 传行号，
  本件**读回原文**核对（复用 `a2_s4b_pi05_gpu_run.check_declaration`，不另造）。
- **起跑那一刻实测三网**并落 `GPU_WINDOW.json`；拒绝逻辑读 **E 的参考实现**
  `scripts/e_mainline_render_calib.py::card_busy()`（经 `a2_egl_latency_remeasure._load_e_calib_module()`），
  **不读 B2 的副本**。忙且未 `--allow-cotenant` ⇒ `exit 3` + `refused_gpu_busy_<ts>.json`。
- **停点的执行面是「实测读数」不是「我设了环境变量」**（`env -i` 会抹掉档位变量，E 已因此踩过一次）。
- 渲染走 **egl/nvidia_gpu**（与训练数据采集同口径，见先落腿结论 9），`renderer_class` 三点各自独立测。

## 复用（裁定 72 `self_artifact_reuse_discipline`：**不重造**，按路径 import）
- `scripts/a2_s4b_pi05_gpu_run.py`：`check_declaration` / `GpuWindow` / `Pi05ChunkPolicy` /
  `weights_identity` / `Findings` / `write_json` / `sha12` / `now_iso`。
- `scripts/a2_step1_prealign_verify.py`：`build_cfg_and_processors`（**L1 已逐位自证过的 stats 注入路径**）/
  `read_stats` / `read_dataset_arrays` / `build_demo_initial_states` / `_init_env_to_state`
  （L9 已自证 `state maxdiff = 0.0` 的那一条）/ `identity`。
- `harness/bc_admission_gate.py::consume_c2_broadcast`：唯一消费入口。
- `harness/vla_runtime.py`：`ChunkedVlaRuntime`（`standard_sync` + `prime_mode=none`，裁定 95.3-④）/
  `GymAlohaJudgedAdapter`（判定层归 C2，A2 只搬运）。
- `scripts/a2_pi05_zeroshot_eval.py::build_policy/adapt_action`（经 S4B 的 `load_reuse()`）。

## 与 S4B 的**唯一**两处差异（都显式登记，不藏在代码里）
1. `Step1ChunkPolicy(S4B.Pi05ChunkPolicy)`：构造与推理路径 100% 继承；只改**三个身份字段**
   （父类写 `pi05_base_zero_sft@…` / `stats_version=NONE`，那是 base 臂的正确身份；本臂载的是
   **带 C2 stats 注入的目录**，`stats_version` 必须是 C2 的 `representation_version`，否则 runtime 的
   `_guard_stats_version()` 会硬隔离 td/bc 资格）。
2. `run_episode_demo_init()`：以 `S4B.run_episode` 为模板，**只插入**「`rt.reset(seed)` 之后把物理
   直接置到示范初态」这一步（`DemoInitAdapter.reset` 里做，复用先落腿 `_init_env_to_state` + 回读自证）。
   其余（三网读数成对、prompt 审计、renderer 三点、四字段、ledger round-trip）逐项照搬。

## 纪律
- **能力声明禁令（裁定 46）**：产物里 `capability_claim=false`、
  `success_rate_column=SUCCESS_RATE_COLUMN`（**裁定 102.2-① 已改**：用户 Step 1 验收标准第 2 条
  「至少一条正向和一条反向轨迹能从示范初态闭环复现」= **出场判据**，不再是 `not_an_exit_criterion`；
  但它判的是**闸门**、不是能力 ⇒ `capability_claim` 仍恒 `false`、policy 能力指标仍 = 0）；
  第 1 步出结果前不得出现任何能力表述。
  `policy_executed` 按**事实**登记（rollout 真跑了策略 ⇒ `true`）。
- **四字段分开记（裁定 95.3-①）**：`measurement_reliable` / `interface_conformant` /
  `out_of_distribution`（**只标注不剔除**）/ `task_success`。
- **盲点维 `[0,3,5,7,10,12]` 不得写成全 14 维结论**（裁定 94.3/95.5-④；C2 广播件明写、D 追认）。
- **三值纪律**：`measurement_status ∈ {measured, not_measured, not_applicable}`；`not_measured ≠ 0`。
- **行数口径点名**：只认 `n_lines_wc` / `n_lines_splitlines`，裸 `n_lines` 禁用（裁定 98.3-②/98.5-②）。
- **sha256[:12] 是唯一约束性判据**，行数只作旁证（裁定 98.5）。
- 数值成对带 `loadavg` 三点 + `nr_throttled`（cgroup **v1**）。
- **不用 `rm`**（走回收站）；**不 `git commit`**（B2 是单写者，裁定 49.6/69.1/81.2）。

## 用法（三段，**每段各自过一次三网硬闸**）
    PY=/root/venvs/pi05_sim/bin/python
    # ① 纯 CPU：准入 + 预登记 + 数据缓存
    $PY scripts/a2_step1_bc_overfit.py --out-dir runs/vla/a2_s3_bc_overfit_20260930 \
        --stages admission,prereg,cache
    # ② 上卡：显存/时长探针（申报行号必填）
    eval "$(bash scripts/e_activate_gpu_render.sh --print)"
    $PY scripts/a2_step1_bc_overfit.py --out-dir runs/vla/a2_s3_bc_overfit_20260930 \
        --stages probe --declaration-line <N>
    # ③ 上卡：训练 + 闭环
    $PY scripts/a2_step1_bc_overfit.py --out-dir runs/vla/a2_s3_bc_overfit_20260930 \
        --stages train,rollout,report --declaration-line <N>

退出码：`0` 完成且无阻塞红 · `1` 结构性失败/阻塞红 · `2` 用法或未申报 · `3` **起跑前拒绝（GPU 忙）**
      · `4` **准入被拒（`LearnerRefused`）**。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import time
from datetime import datetime

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np                                                     # noqa: E402

from harness import bc_admission_gate as GATE                          # noqa: E402
from harness import prompt_bin_guard as PBG                            # noqa: E402
from harness import vla_runtime as VR                                  # noqa: E402
from harness.ledger import FactLedger                                  # noqa: E402


def _load_mod(name: str, relpath: str):
    """按**路径**加载（与 `a2_s4b_pi05_gpu_run.load_module_by_path` 同口径；本函数在 S4B 载入
    **之前**就要用，所以本地留一份三行实现，载入 S4B 之后一律改用 S4B 的那一份）。"""
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S4B = _load_mod("a2_s4b_pi05_gpu_run", "scripts/a2_s4b_pi05_gpu_run.py")
PRE = _load_mod("a2_step1_prealign_verify", "scripts/a2_step1_prealign_verify.py")

now_iso = S4B.now_iso
sha12 = S4B.sha12
write_json = S4B.write_json
jdefault = S4B.jdefault
identity = PRE.identity

EXIT_OK, EXIT_BLOCKING_RED, EXIT_USAGE, EXIT_REFUSED_GPU_BUSY, EXIT_REFUSED_ADMISSION = 0, 1, 2, 3, 4

# ══════════════════════════ 口径常量（都能被独立复核）══════════════════════════
SELF_REL = "scripts/a2_step1_bc_overfit.py"
GPU_STAGES = ("probe", "train", "rollout")
ALL_STAGES = ("admission", "prereg", "cache", "probe", "train", "rollout", "report")

STEP1_QUESTION_VERBATIM = "数据能否被当前模型学到？（裁定 95.2 六步序列表 第 1 行）"
STEP1_CRITERION_VERBATIM = ("过拟合臂 loss 必须显著下降且**动作逐维对得上示范**（含夹爪开合时刻）；"
                            "**从示范初态**闭环执行的推进度必须 > 随机基线；产物落 "
                            "`runs/vla/a2_s3_bc_overfit_*/`（裁定 95.2 第 1 行，不重新解释）")
CORE_QUESTION_VERBATIM = "一份经过验证的双向示范，能否训练出一个在标准执行方式下具有可重复能力的策略？"

# ── 裁定 101.2 的用户原文（**逐字采纳、不得增删**）：Step 1 = 唯一的在飞单 ──────────────
STEP1_FIXED_CONDITIONS_VERBATIM = (
    "formal-40 双向示范 · 先只取极小训练集（正向 1–2 集、反向 1–2 集）· 训练到训练误差接近零 · "
    "从对应示范初态开始闭环执行 · 不使用 Harness 后半段调度 · 不使用 LLM · 不使用恢复 · 不使用 RL · "
    "正向与反向分别记录")
STEP1_REQUIRED_OUTPUTS_VERBATIM = [
    "① 训练集动作误差（判断模型是否真的学到数据）",
    "② 示范初态闭环成功率（判断离线拟合能否转成在线控制）",
    "③ 正向/反向分别结果（防止一个方向掩盖另一个方向）",
    "④ 夹爪转变帧误差（验证 R2 是否影响抓取）",
    "⑤ 每步动作间隔（为后续实时性提供基线）",
    "⑥ 失败阶段（区分接近 / 抓取 / 抬升 / 放置 / 释放）",
]
STEP1_ACCEPTANCE_CRITERIA_VERBATIM = [
    "① 训练集动作误差明显下降",
    "② 至少一条正向和一条反向轨迹能从示范初态闭环复现",
    "③ 动作和夹爪时间对齐没有未解释的系统性偏移",
    "④ 失败时能定位到具体阶段",
]

# ── 裁定 102.2-①：**闭环复现是出场判据**（A2 的 v1 预登记说不是 ⇒ v2 已修正）──────────
SUCCESS_RATE_COLUMN = "exit_criterion_closed_loop_reproduction"
SUCCESS_RATE_COLUMN_NOTE = (
    "裁定 102.2-①：用户 Step 1 验收标准第 2 条原文「至少一条正向和一条反向轨迹能从示范初态闭环复现」"
    "**就是出场判据**。可核化 = `bc` 臂在**正向 train 集 ≥1 集** ∧ **反向 train 集 ≥1 集**，"
    "从该集示范初态闭环跑到 C2 判定层的 `geometric_success == True`（= A2 的 `max_stage == 4`，"
    "含 hold 反 flick）。`progress_gt_random` **降为诊断读数**、不再是唯一判据。"
    "**这不是能力声明**（裁定 46/101.3）：它判的是「离线拟合能否转成在线控制」这一条闸门，"
    "`capability_claim` 恒 `false`、policy 能力指标仍 = 0；本臂跑的是 `AlohaTransferCube-v0` 的"
    "左右臂交接（冒烟基准），**不得**写成「单臂区域抓放能力」（裁定 95.4-③/⑤）。"
    "这一条**不属** 裁定 101.1 冻结令禁的「新增非 Ⅰ 类门禁」—— 它就是 Step 1 闸门本身"
    "（Ⅰ 类：⑥ 标准同步控制是否正确执行 + ④ 数据能否被读取和重放）。")

# ── 两处口径差 / 两处延后项（都**只登记不阻塞**，裁定 101.1「先登记、不阻塞训练」）──────────
OPEN_STEP1_NEARZERO_GAP = {
    "id": "OPEN-STEP1-NEARZERO-GAP",
    "what": ("用户原文「训练到训练误差接近零」vs A2 v1 预登记的「末点 ≤ step0 的 50%」"
             "（`GATES['train_det_loss_final_over_step0_max']=0.5`）之间的差"),
    "disposition": ("裁定 102.2-②：**(a)** A2 预登记的四个数（0.5 / 0.05 / 0.9 / 5 帧）**原样有效、一个不改**；"
                    "**(b)** 不得在确定性训练损失仍在下降时提前停（见 `PLATEAU_RULE`）；"
                    "**(c)** 差本身由 **D 在里程碑审查按实测曲线裁**"),
    "a2_self_binding": "**A2 不得自行把「≤50%」宣称为「接近零」**；平台期停在高值 ⇒ Step 1 的答案是 RED",
    "blocking": False,
}
OPEN_STEP2_TIMING_PERCENTILES = {
    "id": "OPEN-STEP2-TIMING-PERCENTILES",
    "what": "产出⑤「每步动作间隔」的 **intra-episode** max / P95 / P99 百分位",
    "disposition": ("裁定 102.2-④：Step 1 以「**逐集** `wall_ms_per_ctrl_step` + **跨集**分布 + "
                    "`budget_fraction` / `overload_flag`」满足产出⑤；intra-episode 百分位此刻**还不是**"
                    "实时性判据（standard_sync 下推理本就在关键路径上、控制器必然被阻塞；真机判据另在 P4）"),
    "when": "**第 2 步前置，非阻塞**",
    "blocking": False,
}
OPEN_ITEMS_STEP1 = [OPEN_STEP1_NEARZERO_GAP, OPEN_STEP2_TIMING_PERCENTILES]

# ── A2 自报缺陷（本件自己的码；**不含**任何冻结面。裁定 93.8：审计器须自证、自报不遮丑）──────
SELF_DEFECTS_STEP1 = [
    {"id": "D1_A2T4_readback_wrong_attribute",
     "what": ("`build_training_stack` 的 A2T4 自证牙用 `step.config.get(\"stats\")` 回读注入进真处理器的 "
              "q01/q99，而 `NormalizerProcessorStep` **没有** `.config` 属性"),
     "symptom": ("第一次上卡的 `probe` 阶段 15.32 s 即 `exit 1`、`blocking_red=2`、"
                 "`build_error=\"AttributeError: 'NormalizerProcessorStep' object has no attribute 'config'\"`、"
                 "`probe.chosen` 全 `null`（`PROBE1STEP.json` = `9819c806c7a3`）"),
     "how_caught": ("**上卡即被自己的阻塞红拦住**（`probe_build_failed:gc=True` ⇒ `blocking=True`）⇒ "
                    "没有带着可疑的归一化器往下跑；这是牙生效、不是牙失效"),
     "root_cause": ("凭 `.config` 这个「看起来合理」的名字写回读，**没有**去核对冻结先落腿的同源实现"
                    "（`scripts/a2_step1_prealign_verify.py:469` 用的是 `_tensor_stats`）"),
     "fix": "改为读 `_tensor_stats`，并把「读的是哪个属性、哪个类」一起落盘（`inj.stats_readback_A2T4`）",
     "frozen_surfaces_touched": "**0 个**（`harness/vla_runtime.py` / `norm_contract.py` / stats / C2 判定层 / 先落腿件全部一个字节未动）",
     "class": "Ⅱ 类（自己的实现错，未产生任何对外判词；被自己的阻塞红当场拦住）"},
    {"id": "D2_A2T4_float64_vs_float32_false_red",
     "what": ("A2T4 把 C2 npz 里的 **float64** q01/q99 直接与 **float32** 管线里的值做 `array_equal` 逐位比对"),
     "symptom": "**尚未发作**（D1 先炸了）；若只修 D1 不修 D2 ⇒ A2T4 会**假红**、`build_training_stack` 抛 `RuntimeError` 而停",
     "how_caught": ("**A2 自查**：修 D1 时实测 `q01.astype(float32).astype(float64) == q01` ⇒ **False**"
                    "（14 维里存在末位差）；冻结先落腿 L1 的判据本来就写了这一步"
                    "（`a2_step1_prealign_verify.py:475-478`），A2 抄判据时把它漏了"),
     "root_cause": "同 D1：**没有逐字对齐**已被验证过的同源判据，凭记忆重写了一遍",
     "fix": ("参考值先经 `.astype(np.float32).astype(np.float64)` 再比；并把 "
             "`npz_q01_float64_equals_float32_roundtrip` 的实测值（= `false`）落盘，"
             "让「为什么必须走这一步」可被独立复核"),
     "frozen_surfaces_touched": "**0 个**",
     "class": "Ⅱ 类（潜在假红；未产生任何对外判词）"},
    {"id": "A2-SD-10_demo_init_box_quat_not_written",
     "what": ("示范初态**只写方块 xyz、不写方块四元数**：`PRE._init_env_to_state` 写 `qpos[0:16]`（双臂+双爪）"
              "与 `qpos[16:19]`（方块 xyz），**不写 `qpos[19:23]`**、`qvel` 置零 ⇒ Step-1 的闭环初态是"
              "「**沉降后** xyz + `reset(seed)` 的**沉降前**四元数」的拼接"),
     "who_found": "**D**（裁定 104.2，本机 as_of 19:0x 实测）—— **不是 A2 自报**；A2 先前的自报（D4）作用域窄了",
     "symptom": ("回读自证与阻塞牙 `demo_init_readback_failed` 都只比 **14 维机器人状态**"
                 "（`rb=jenv._state()[:STATE_DIM]` vs `frame0_state`）⇒ 方块位姿**不在覆盖里**，"
                 "而用户 Step-1 出场判据的字面就是「**从示范初态**」"),
     "class": "**Ⅰ 类**（直接落在出场判据的字面上；裁定 104.2-（a））",
     "status": "**OPEN / `not_measured`** —— 量级由 CPU-only 测量件 `DEMO_INIT_BOX_QUAT_SETTLE.json` 给（裁定 104.3）",
     "fix": ("按裁定 104.3 的两个**预登记**分支走：甲（差 ≤ 阈值）⇒ 键升 `measured_and_immaterial`、"
             "Step-1 **按现码起跑、一个字节不改**；乙（差 > 阈值）⇒ 只允许一处窄修"
             "（`_init_env_to_state` 增写 `q[19:23]`），改前落前像 + `criteria_identity`、"
             "**判据常量不得改**、以预登记 v3 增补的形式在起跑前落盘"),
     "frozen_surfaces_touched": "**0 个**（先落腿件 `_init_env_to_state` 本轮只读复用、一个字节未改）"},
    {"id": "A2-SD-11_step1_rollout_not_affected_overreach",
     "what": ("A2 在锚定探针的判词块里写过 `step1_rollout_not_affected`：「方块静止在桌面 ⇒ 四元数稳定，"
              "本缺陷不影响 Step 1 的初态复现（L9 已自证 `maxdiff=0.0`）」"),
     "why_it_is_a_defect": ("**证据作用域 ⊊ 结论作用域**：L9 与回读牙都是 14 维口径、不含方块位姿，"
                            "而结论是关于方块姿态的；且「方块静止」当时**未测**。红线 "
                            "`absence_of_measurement_is_not_measurement_of_absence`：**测出量级之前不得写「不影响」**"),
     "how_caught": "**D 亲核**（裁定 104.2：「A2 的 `step1_rollout_not_affected` 不予采信」）",
     "fix": ("键改写为 `step1_rollout_effect_not_measured`（裁定 104.2-（d））：旧键**原文保留 + "
             "`superseded_by`、不删**；新键的值**只读**测量件 `box_quat_defect_status()`，件不在盘 ⇒ "
             "`not_measured`（不写 false、不写「无影响」）"),
     "class": "**Ⅰ 类**（同族于 C2 报的元缺陷：审计器的识别模式比对象空间窄 ⇒ 报绿、漏掉真缺陷；裁定 104.2-（e））",
     "frozen_surfaces_touched": "**0 个**"},
]

SELF_DEFECT_ID_CROSSWALK = {
    "why_this_exists": ("**A2 的自报缺陷编号此前在两份件里各自从 `D1` 起编 ⇒ 裸 `D1`/`D2`/`D3` 有歧义**"
                        "（`R1R2_ALIGNMENT_VERDICT.json` 里的 `D1_dangling_else_wiped_legs` 与本件里的 "
                        "`D1_A2T4_readback_wrong_attribute` 是两件事）。裁定 104.6-F 要按编号归类 ⇒ "
                        "**新编号一律用全局唯一的 `A2-SD-nn_<slug>`**，旧编号原样保留（已发布的件不改字节），"
                        "对照关系就是本表。**这不是新门禁、不是新索引件**：它只是本件内的一个字段"),
    "caliber": "`A2-SD-nn` = A2 线自报/被裁缺陷的全局序号；旧 `Dn_<slug>` 保留原样并在此登记归属",
    "legacy_to_unique": {
        "D1_A2T4_readback_wrong_attribute": {"unique_id": "A2-SD-01", "artifact": "scripts/a2_step1_bc_overfit.py（本件）"},
        "D2_A2T4_float64_vs_float32_false_red": {"unique_id": "A2-SD-02", "artifact": "scripts/a2_step1_bc_overfit.py（本件）"},
        "D1_dangling_else_wiped_legs": {"unique_id": "A2-SD-03", "artifact": "runs/vla/a2_r1_r2_alignment_20260930_run2/R1R2_ALIGNMENT_VERDICT.json"},
        "D2_stable_copy_sha_stale": {"unique_id": "A2-SD-04", "artifact": "同上"},
        "D3_per_dim_attribution_wrong_key": {"unique_id": "A2-SD-05", "artifact": "同上"},
        "D4（锚定探针：探针层未受控初值）": {"unique_id": "A2-SD-06",
                                        "artifact": "runs/vla/a2_r1_r2_anchor_probe_20260930/ANCHOR_PROBE_BOX_QUAT.json",
                                        "note": "裁定 104.2-（c）：**作用域窄了** —— 同一函数也是 Step-1 的初态写入路径 ⇒ 对象侧另立 A2-SD-10"},
        "D3（仓库根误落 `false`/`null` 两个 0 字节文件）": {"unique_id": "A2-SD-07",
                                                       "artifact": "runs/vla/a2_s3_bc_overfit_20260930/stray_root_files/STRAY_ROOT_FILES_NOTE.json"},
        "D4（`PRE_REGISTRATION_v2.json` 的 `producer` 块继承自 v1）": {"unique_id": "A2-SD-08",
                                                                  "artifact": "runs/vla/a2_s3_bc_overfit_20260930/CRITERIA_IDENTITY.json"},
        "D5（判据脚本 `6b531a1a1a25`→`e75d2284fd6c` 改动无前像）": {"unique_id": "A2-SD-09",
                                                                "artifact": "同上；违反 Ⅰ 类口径 "
                                                                            "`judging_script_change_requires_before_image_and_criteria_identity`（§100.3-（d））"},
        "demo_init_box_quat_not_written（D 裁、非 A2 自报）": {"unique_id": "A2-SD-10", "artifact": "本件 + `DEMO_INIT_BOX_QUAT_SETTLE.json`"},
        "step1_rollout_not_affected 的断言超出证据作用域": {"unique_id": "A2-SD-11", "artifact": "本件"},
    },
}

AUTHORITY = [
    "rl_harness_supervision/d_handoff_to_a2_20260930.md 补单四 §三/§四/§五（第 1 步内容、判据、停点、下一步）",
    "rl_harness_supervision/d_handoff_to_a2_20260930.md **补单七**（全项目唯一在飞单）§二（判据四条）/"
    "§三（预登记 v2）/§四（窗口与执行顺序，写死）/§五（停点与汇报）",
    "**裁定 101.2**（用户三项输入：Step 1 = 唯一在飞单；固定条件/六项产出/四条验收标准逐字采纳；"
    "R1/R2 并入产出③④、不再是上卡前独立探针）· **裁定 101.4**（A2 自己 declare 窗口后起跑）· "
    "**裁定 101.3**（阶段判断的唯一权威措辞）",
    "**裁定 102.2-①②③④**（闭环复现=出场判据 / 不提前停+`plateau_reached` / 四臂必需 / "
    "产出⑤的逐集+跨集口径）· 裁定 102.1（admission/prereg/cache 三阶段追认合法）",
    "裁定 95.2（六步序列 = 权威，不许重排）· 95.3-①（四字段分开）· 95.3-④（第 1–2 步一律标准同步动作块）",
    "裁定 95.5-①②③（整条 episode 划分 / stats 与阈值开跑即冻结 / checkpoint 选择规则开跑前预登记）",
    "裁定 95.6（汇报格式 = 六问）· 裁定 46（能力声明禁令）· 裁定 94.3/95.5-④（盲点维不是能力判据）",
    "裁定 98.5（sha256[:12] 是唯一约束性判据；行数必须点名口径；裸 n_lines 禁用）",
    "裁定 98.10-四（A2 准入成立 + 停点追平）· 裁定 94.9-1② / 96.1-③ / 98.9-②（上卡纪律）",
    "docs/c2_to_a2_bc_stats_handoff_20260930.md §3（唯一一档 stats；换 stats 必须先报 D）",
]

STATE_DIM = PRE.STATE_DIM                       # 14
BLIND_DIMS = list(PRE.BLIND_DIMS)               # [0,3,5,7,10,12]（C2 94.3 Ⅱ 类登记，**不是**能力判据）
GRIP_DIMS = list(PRE.GRIP_DIMS)                 # [6,13]
OBSERVED_DIMS = [d for d in range(STATE_DIM) if d not in BLIND_DIMS]
DIRECTION_BY_MANIFEST = dict(PRE.DIRECTION_BY_MANIFEST)   # forward→right_to_left / reverse→left_to_right
MANIFEST_DIRECTION_BY_ENV = {v: k for k, v in DIRECTION_BY_MANIFEST.items()}

# ── 裁定 95.5-①：按**整条 episode** 划分（规则先写死，不看任何结果）──────────────
# formal-40 的排布（B2 manifest 实测）：episode_index 0–19 = forward(seed 2000–2019)、
# 20–39 = reverse(seed 2000–2019)。取「每向最小两个 seed」当过拟合臂、次小两个当验证臂，
# 其余 32 集**完全不碰**（留给第 2 步；裁定 95.5-② 的留出集升级排在第 2 步之后）。
TRAIN_EPISODES = [0, 1, 20, 21]
VAL_EPISODES = [2, 3, 22, 23]
UNTOUCHED_EPISODES = [i for i in range(40) if i not in TRAIN_EPISODES + VAL_EPISODES]
SPLIT_RULE = (
    "整条 episode 划分（裁定 95.5-①）：train = 每向 seed 最小的 2 集（forward ep0/ep1 + reverse ep20/ep21）；"
    "val = 每向次小的 2 集（forward ep2/ep3 + reverse ep22/ep23）；其余 32 集本轮**完全不读**"
    "（留给第 2 步）。规则在任何结果产生之前写死，**不依据 loss/成功率重选**。"
)

# ── 裁定 95.5-③：checkpoint 选择规则（**开跑前**预登记，不许按 rollout 成功率挑）──────
CHECKPOINT_SELECTION_RULE = (
    "在**已保存的** checkpoint 集合里取 `val_det_loss`（固定 noise/time 的确定性验证损失，见下）**最小**者；"
    "并列 ⇒ 取步数更少者。**严禁**用 rollout 成功率/推进度挑 checkpoint（裁定 95.5-③：那是 ACT 线吃过的亏，"
    "且实测 seed × checkpoint 共同决定）。验证集只用于选择，**最终测试用新的物体初始状态**排在第 2 步。"
)
VAL_LOSS_CALIBER = (
    "π₀.₅ 是 flow-matching：`PI05Pytorch.forward` 每步随机采 `noise` 与 `time` ⇒ 验证损失本身带抽样噪声，"
    "用它挑 checkpoint 会挑到噪声而不是模型。A2 的口径选择（**显式登记**）：验证/对照损失一律用"
    "**预先固定**的 (noise, time)（`np.random.default_rng(DET_RNG_SEED)` 生成一次、每次评估复用同一份），"
    "直接调 `policy.model.forward(..., noise=…, time=…)`，与 `policy.forward()` 走同一条 `prepare_action` /"
    "`_preprocess_images` 路径，只把随机源换成固定源 ⇒ 曲线可逐点相比。训练损失**保持随机**（那才是真目标）。"
)
DET_RNG_SEED = 20260930

# ── 推进度（裁定 95.2 第 1 行的「推进度必须 > 随机基线」需要一个**先写死**的定义）──────
PROGRESS_LADDER = {
    0: "起点：什么都没发生",
    1: "**源侧**夹爪接触到方块（`contact_box_finger[source]==True`）⇒ 抓取尝试到位",
    2: "stage1 ∧ 方块离桌（`contact_box_table==False`）⇒ 抬起",
    3: "stage2 ∧ 方块到**目标侧**指距离 ≤ `grasp_max_dist_m` ⇒ 交接侧到位",
    4: "C2 的 `geometric_success==True`（含 `hold_steps ≥ hold_min_steps` 的反 flick 持稳）",
}
PROGRESS_METRIC_DEFINITION = {
    "primary": "max_stage（0–4 的**序数**，逐帧按 `PROGRESS_LADDER` 算当帧最高档，再取全集最大）",
    "secondary": "net_approach_target = (d_init_target − min_dist_target) / d_init_target（连续量，1=贴到目标侧指）",
    "tiebreak_order": ["max_stage", "net_approach_target", "max_height_m", "max_hold_steps"],
    "source_of_truth": ("全部标量都由 **C2 的 `JudgmentFacts`** 逐帧算出（`harness/env_gym_aloha.read_facts`），"
                        "A2 **不重算任何判定**；方向相关的 source/target 侧由 C2 的 `target_side(direction)` 定，"
                        "不用 G3 那个把方向写死成右→左的 `SceneProbe.stage`"),
    "direction_aware": True,
    "why_not_env_reward": ("`gym_aloha/env.py:178-180` 的 `reward==4` 把方向写死成右→左（C2 已登记为 "
                          "`defect_direction_hardcoded`）⇒ 反向集上它是假成功源，不能当推进度"),
    "attribution_strength": "inferred（标量是实测的；「stage 越高=推进越多」这个序关系是 A2 的口径选择）",
}
RANDOM_BASELINE_DEFINITION = {
    "name": "random_uniform",
    "what": ("**裁定 95.2 第 1 行点名的那个随机基线**：每个控制帧在**合法物理动作空间**内均匀采样 —— "
             "臂维 `U[lo, hi]`（= `actuator_ctrlrange`，与 BC 臂 `adapt_action` 裁剪后的落点同一个空间）、"
             "夹爪维 `U[0, 1]`（B2 的 `GRIP_OPEN_NORM` 口径）。"),
    "rng": "np.random.default_rng(RANDOM_SEED0 + episode_index)，每集独立、可复现",
    "why_physical_space": ("随机基线必须与 BC 臂**同口径**才可比：BC 臂经 `adapt_action` 之后落的也是这个"
                           "物理空间；在归一化空间里随机会让比较多出一次非线性映射的差"),
    "extra_null": ("另配一条 `hold_init`（保持示范初态不动，= G3 那条 no-op 零假设，复用 "
                   "`a2_s4b_outcome_ledger_verify.HoldPolicy`）。理由：均匀随机会让臂剧烈抖动，"
                   "**有可能靠抖动碰上方块**；`hold_init` 才把「什么都没做也能到 stage k」这条底给钉住。"
                   "两条都报，判据用 `random_uniform`（裁定点名的那条）。"),
}

# ── 臂（问题②「相比哪个固定基线、只改了什么」需要能把变量**分开**）──────────────
ARMS = {
    "bc": ("**第 1 步的主体**：BC 微调后选中的 checkpoint（带 C2 stats 注入、feature shape=14）"),
    "injected_base": ("**同一注入路径、零微调**（= `checkpoints/step_000000`）：把「接口修复（stats 注入 + "
                      "shape 32→14）」与「BC 微调」这两个变量**分开**。G3 的 `0/20` 无法区分二者"),
    "base_zeroshot": ("**固定基线**：G3 那一臂的复刻（base compat 目录、feature shape=32、无 stats ⇒ "
                      "`stats_version=NONE` ⇒ runtime 硬隔离 td/bc 资格，这是**预期形态**）"),
    "random": RANDOM_BASELINE_DEFINITION["what"],
    "hold": RANDOM_BASELINE_DEFINITION["extra_null"],
}
# ── 裁定 102.2-③：**四臂必需**；`base_zeroshot` 降为**可选、排最后、且不得推迟报告** ─────────
REQUIRED_ARMS = ("bc", "injected_base", "random", "hold")
OPTIONAL_ARMS = ("base_zeroshot",)
DEFAULT_ARMS = "bc,injected_base,random,hold,base_zeroshot"
ARM_REQUIREMENT_RULE = {
    "required": list(REQUIRED_ARMS),
    "optional": list(OPTIONAL_ARMS),
    "order_rule": "**必需四臂先跑**；`base_zeroshot` 若跑则**排最后**（裁定 102.2-③）",
    "why_injected_base_required": (
        "用户 09-30 分析 §4-②「脚本 6/6 成功不能证明训练栈正确」的同族混淆：不把「接口修复"
        "（stats 注入 + shape 32→14）」与「BC 微调」分开，`max_stage==4` 就**无法归因**"),
    "why_hold_required": "钉住「什么都不做也能到 stage k」这条底（G3 的 no-op 零假设）",
    "why_random_required": "裁定 95.2 第 1 行点名的随机基线（`progress_gt_random` 的分母）",
    "why_base_zeroshot_optional": (
        "它复刻的 G3 `0/20` **已在案**，属确认而非新信息 ⇒ 降为可选、排最后、"
        "**但不得推迟报告**（裁定 102.2-③）"),
    "missing_required_arm_disposition": "**RED / blocking** ⇒ 缺任一必需臂不许出 Step 1 判词",
}
ARM_BASELINE_FOR_Q2 = "base_zeroshot"
ARM_BASELINE_FOR_Q2_FALLBACK = "injected_base"
ARM_BASELINE_FOR_Q2_RULE = (
    f"问题②的「固定基线」优先 = `{ARM_BASELINE_FOR_Q2}`（G3 那一臂的复刻）；"
    f"它是**可选臂**（裁定 102.2-③）⇒ 若本轮未跑，退到 `{ARM_BASELINE_FOR_Q2_FALLBACK}`"
    "（同一注入路径、零微调）并**显式登记退化事实**，不许静默把两跳压成一跳")
ARM_DELTA_TABLE = {
    "base_zeroshot → injected_base": "只改「接口」：注入 C2 的唯一一档 stats + feature shape 32→14；**权重一字节未动**",
    "injected_base → bc": "只改「权重」：在 train split（4 集）上做 BC 微调；接口/stats/运行时/判定层/初态全不动",
    "bc → random": "只改「动作来源」：同一初态、同一帧预算、同一运行时、同一判定层",
    "所有臂共同不变量": ("`exec_mode=standard_sync` + `prime_mode=none` + `n_replan=25` + `H=50`（裁定 95.3-④）· "
                     "C2 的 `judge_from_facts` 判定层 · 示范初态（先落腿 L9 已自证 `maxdiff=0.0`）· "
                     "`MUJOCO_GL=egl` · `morphology=aloha_bimanual_14d`"),
}

# ── 判据阈值（**预登记**；开跑后不改。改它必须先报 D）──────────────────────────
GATES = {
    "train_det_loss_final_over_step0_max": 0.5,
    "train_det_loss_final_over_step0_max_why": (
        "「loss 必须显著下降」的可核化：确定性训练损失（固定 noise/time）**末点 ≤ step0 的 50%**。"
        "用确定性口径而不是随机训练损失，是为了不把抽样噪声当成下降（见 VAL_LOSS_CALIBER）"),
    "per_dim_mae_rel_max_observed_dims": 0.05,
    "per_dim_mae_rel_max_observed_dims_why": (
        "「动作逐维对得上示范」的可核化：反归一化后的 chunk 逐维 MAE ÷ 该维行程 (q99−q01) ≤ 5%，"
        "**只对 8 个非盲点维设闸**；6 个盲点维 [0,3,5,7,10,12] **只报不判**（裁定 94.3/95.5-④）"),
    "per_dim_corr_min_observed_dims": 0.90,
    "gripper_transition_frames_max": 5,
    "gripper_transition_frames_max_why": (
        "「含夹爪开合时刻」的可核化：示范里夹爪跨 0.5 的那一帧 vs 预测里跨 0.5 的那一帧，"
        "误差中位数 ≤ 5 帧（= 0.17 s @ 29.41 Hz）。夹爪两维 6/13 **不在**盲点维里 ⇒ 可设闸"),
    "progress_gt_random": True,
    "progress_gt_random_why": (
        "裁定 95.2 第 1 行原文「从示范初态闭环执行的推进度必须 > 随机基线」。可核化：**逐集配对**比较，"
        "按 `tiebreak_order` 依次判；总判 = `sum(max_stage_bc) > sum(max_stage_random)`，"
        "若相等则退到 `sum(net_approach_target)`；两者都不占优 ⇒ RED"),
    "progress_gt_random_role": "diagnostic_not_exit_criterion",
    "progress_gt_random_role_why": (
        "**裁定 102.2-① 改了它的地位，没改它的值**：v1 预登记把它当**唯一阻塞牙**"
        "（`success_rate_column=\"not_an_exit_criterion\"`），与用户验收标准第 2 条冲突 ⇒ "
        "现降为**诊断读数**（`blocking=False`、照实报、不决定 Step 1 出场）。"
        "阈值 `progress_gt_random=True` 与 `tiebreak_order` **原样保留**（裁定 102.2-②(a)：预登记的数不改）"),
    # ── 裁定 102.2-①：**出场判据**（用户验收标准第 2 条的可核化）──
    "closed_loop_reproduction_arm": "bc",
    "closed_loop_reproduction_success_field": "geometric_success",
    "closed_loop_reproduction_min_forward_train_episodes": 1,
    "closed_loop_reproduction_min_reverse_train_episodes": 1,
    "closed_loop_reproduction_forward_direction": "right_to_left",
    "closed_loop_reproduction_reverse_direction": "left_to_right",
    "closed_loop_reproduction_split": "train",
    "closed_loop_reproduction_why": (
        "用户 Step 1 验收标准第 2 条**原文**：「至少一条正向和一条反向轨迹能从示范初态闭环复现」。"
        "可核化（裁定 102.2-①，逐字）：**`bc` 臂**在**正向 train 集 ≥1 集** ∧ **反向 train 集 ≥1 集**，"
        "从该集示范初态闭环跑到 **C2 判定层的 `geometric_success == True`**"
        "（= A2 自己的 `max_stage == 4`，含 hold 反 flick）。"
        "**三条防混淆锁**：① 只看 `bc` 臂的行 —— 若过的其实是 `injected_base`（接口修复而非 BC 微调）"
        "⇒ 必须 RED；② 正反向**分别**计数，只一向过 ⇒ 必须 RED（用户固定条件「正向与反向分别记录」）；"
        "③ 只认 `split=='train'` 的示范集本身（过拟合阶段允许用示范集，裁定 101.2 六类阻塞项之⑤），"
        "val 集的成功**不计入**本条 ⇒ 不得用评测集调参。"
        "判定层归 C2（`judge_from_facts` 经 `GymAlohaJudgedAdapter`），**A2 不重算任何判定**。"),
    "closed_loop_reproduction_tooth_id": "A2T6_closed_loop_reproduction_two_way",
    "closed_loop_reproduction_selftest_id": "A2T6S_closed_loop_reproduction_mutant_selftest",
}

# ── 裁定 102.2-②(b)：**不得在确定性训练损失仍在下降时提前停** ────────────────────────
PLATEAU_RULE = {
    "block_steps": 100,
    "min_block_drop_frac": 0.01,
    "continue_iff": ("**每 100 步一块**，块间降幅 >1%（`train_det_loss` 块均值，确定性口径）**且**窗口预算"
                     "未耗尽 ⇒ **继续**（裁定 102.2-②(b) 逐字）"),
    "stop_when": ("块间降幅 ≤1% ⇒ `plateau_reached=true` 停；或墙钟预算耗尽 / 触到硬上限 ⇒ "
                  "`plateau_reached=false` + `stopped_by` 照实写（**不许把预算耗尽写成平台期**）"),
    "wall_budget_s_default": 3600.0,
    "wall_budget_ruling": ("裁定 101.4：**Step 1 若 1 小时未收敛即停并报读数，不要烧满窗口**；"
                           "Step 1 **不占** 1×A800 / ≤24 h / ≥3 种子那份预算（那是 Step 2 的）"),
    "escalation_rule": "**若单种子需 >8 h ⇒ 立刻报 D，不得静默超预算**（v1 预登记的 `escalation_rule` 原样有效）",
    "required_products": ["plateau_reached(bool)", "train_det_loss_final_over_step0(实测值)",
                          "stopped_by", "plateau_blocks(逐块降幅表)"],
    "extension_is_preregistered": (
        "**扩展规则先写死、不看结果**：只在「块间降幅 >1% ∧ 预算未耗尽 ∧ 未触硬上限」三条**同时**成立时"
        "按 `block_steps` 的整数倍延长；扩展产生的 checkpoint 步 = `block_steps` 的整数倍。"
        "**严禁**按 loss/成功率反选步数（裁定 95.5-③）"),
    "gates_unchanged": ("裁定 102.2-②(a)：`train_det_loss_final_over_step0_max=0.5` / "
                        "`per_dim_mae_rel_max_observed_dims=0.05` / `per_dim_corr_min_observed_dims=0.9` / "
                        "`gripper_transition_frames_max=5` **四个数一个不改**"),
    "nearzero_gap": OPEN_STEP1_NEARZERO_GAP,
}

# ── 裁定 102.2-④：产出⑤「每步动作间隔」的口径（逐集 + 跨集分布 + 软约束标记）──────────────
TIMING_OUTPUT_RULE = {
    "per_episode_field": "`wall_ms_per_ctrl_step`（源 `harness/vla_runtime.py:1078`，**只读、不改载荷件**）",
    "cross_episode_distribution": "跨集分布：n / min / p25 / median / p75 / max / mean / std（**逐臂**给）",
    "must_be_listed_separately": (
        "裁定 75.5：`wall_ms_per_ctrl_step` 与 `amortized_inference_ms` **必须分列**，两个口径不得互搬"),
    "soft_constraint": ("裁定 75.4：仿真/离线里 34 ms/步是**软约束** ⇒ `budget_fraction > 1` **不判硬失败**，"
                        "只置 `overload_flag=true`"),
    "realtime_closed_loop_claim": False,
    "deferred": OPEN_STEP2_TIMING_PERCENTILES,
    "satisfies_required_output": "⑤ 每步动作间隔（裁定 101.2 的六项产出之一）",
}
GRIPPER_SEMANTICS = {
    "action_1.0": "张开（实测 8.41 cm，B2 `GRIP_OPEN_NORM=1.0`）",
    "action_0.0": "合爪（实测 1.83 cm）",
    "note": "**与直觉相反**，先落腿 L5 已实测登记；夹爪非严格二值（ramp 占 ~3.8%）⇒ 用「跨 0.5 的那一帧」定义开合时刻",
}

N_LINES_CALIBER = PRE.N_LINES_CALIBER
RULING_46 = S4B.RULING_46
CORRECTNESS_FAMILY_CAVEAT = dict(S4B.CORRECTNESS_FAMILY_CAVEAT)
BLIND_DIM_CAVEAT = (
    "盲点维 [0,3,5,7,10,12]（C2 的 94.3 Ⅱ 类登记）：本件对它们的任何数字都是**逐维登记**，"
    "**不得**汇总成「全 14 维」的结论；它们也**不是**能力判据（裁定 95.5-④：全量 bin 占用数只描述覆盖）"
)
MORPHOLOGY_SCOPE_CAVEAT = (
    "裁定 95.4-③：本件跑的是 `AlohaTransferCube-v0` 的**左右臂交接**（冒烟基准），"
    "任何数字**不得**写成「单臂区域抓放能力」；`same_action_dim_does_not_imply_same_morphology`（95.4-⑤）"
)
IMG_KEYS = ("observation.images.base_0_rgb", "observation.images.left_wrist_0_rgb",
            "observation.images.right_wrist_0_rgb")
OBS_LANGUAGE_TOKENS = "observation.language.tokens"
OBS_LANGUAGE_ATTENTION_MASK = "observation.language.attention_mask"
PREALIGN_JSON_DEFAULT = "runs/vla/a2_step1_prealign_20260930_run4/PREALIGN_VERIFICATION.json"
PREREG_NAME = "PRE_REGISTRATION.json"
PREREG_V2_NAME = "PRE_REGISTRATION_v2.json"


def prereg_path(out_dir: pathlib.Path) -> pathlib.Path:
    """**v2 在盘 ⇒ 消费 v2；否则 v1**（补单七 §三：v2 是**追加**、不覆写 v1）。"""
    p2 = pathlib.Path(out_dir) / PREREG_V2_NAME
    return p2 if p2.exists() else (pathlib.Path(out_dir) / PREREG_NAME)


PROBE_NAME = "PROBE1STEP.json"
SELECTION_NAME = "CHECKPOINT_SELECTION.json"


# ══════════════════════════ 小工具 ══════════════════════════
def base_doc(artifact: str, args, **extra) -> dict:
    d = {
        "artifact": artifact,
        "as_of": now_iso(),
        "producer": {"script": SELF_REL,
                     **{k: v for k, v in identity(SELF_REL).items()
                        if k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                     "python": sys.version.split()[0], "venv": sys.executable},
        "n_lines_caliber": N_LINES_CALIBER,
        "step": 1,
        "step_question_verbatim": STEP1_QUESTION_VERBATIM,
        "step_criterion_verbatim": STEP1_CRITERION_VERBATIM,
        "core_question_verbatim": CORE_QUESTION_VERBATIM,
        "authority": list(AUTHORITY),
        "capability_claim": False,
        "policy_executed": False,
        "gpu_used": False,
        "success_rate_column": SUCCESS_RATE_COLUMN,
        "success_rate_column_note": SUCCESS_RATE_COLUMN_NOTE,
        "success_rate_column_amended_by": "裁定 102.2-①（v1 预登记写的是 `not_an_exit_criterion` ⇒ v2 已修正）",
        "self_defects": SELF_DEFECTS_STEP1,
        "self_defects_note": ("**A2 自报**（裁定 93.8）：这两件都是本件自己的码错、**没有**碰任何冻结面，"
                              "且都在产生对外判词之前被拦住（D1 被自己的阻塞红当场拦、D2 是 A2 自查）"),
        "self_defect_id_crosswalk": SELF_DEFECT_ID_CROSSWALK,
        "ruling_46": RULING_46,
        "blind_dims": BLIND_DIMS,
        "blind_dim_caveat": BLIND_DIM_CAVEAT,
        "observed_dims": OBSERVED_DIMS,
        "morphology": S4B.MORPHOLOGY,
        "morphology_scope_caveat": MORPHOLOGY_SCOPE_CAVEAT,
        "correctness_family_caveat": CORRECTNESS_FAMILY_CAVEAT,
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
    }
    d.update(extra)
    return d


def load_json(path: pathlib.Path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


BOX_QUAT_MEASURE_JSON_DEFAULT = "runs/vla/a2_s3_bc_overfit_20260930/DEMO_INIT_BOX_QUAT_SETTLE.json"


def box_quat_defect_status(path: str = BOX_QUAT_MEASURE_JSON_DEFAULT) -> dict:
    """裁定 104.2 的 Ⅰ 类缺陷 `demo_init_box_quat_not_written` 的**实测状态**（只读、不猜）。

    为什么必须有这个函数：旧键 `step1_rollout_not_affected` 拿 L9 的 `maxdiff=0.0` 作证，而 L9 与
    回读牙 `demo_init_readback_failed` 都是 **14 维机器人状态**口径、**不含方块位姿** ⇒
    **证据作用域 ⊊ 结论作用域**（裁定 104.2）。红线
    `absence_of_measurement_is_not_measurement_of_absence`：**测出量级之前不得写「不影响」**
    ⇒ 量级只从 CPU-only 测量件读；件不在盘 ⇒ `not_measured`，**不写 false、不写「无影响」**。
    """
    p = REPO / path
    rel = path
    if not p.exists():
        return {"measurement_status": "not_measured", "artifact": rel, "exists": False,
                "sha256_12": None, "branch": None, "angle_diff_deg_max": None,
                "angle_diff_deg_median": None, "n_episodes_measured": None,
                "settle_steps_dropped_set": None, "negative_controls_all_bite": None,
                "why": ("测量件不在盘 ⇒ `not_measured`（**不是**「无影响」）；红线 "
                        "`absence_of_measurement_is_not_measurement_of_absence`")}
    try:
        d = load_json(p)
    except Exception as exc:                                          # noqa: BLE001
        return {"measurement_status": "not_measured", "artifact": rel, "exists": True,
                "sha256_12": sha12(p), "branch": None, "angle_diff_deg_max": None,
                "angle_diff_deg_median": None, "n_episodes_measured": None,
                "settle_steps_dropped_set": None, "negative_controls_all_bite": None,
                "why": f"测量件读不出来（{type(exc).__name__}: {exc}）⇒ `not_measured`"}
    br = d.get("branch_decision") or {}
    agg = d.get("aggregate") or {}
    return {"measurement_status": d.get("measurement_status"), "artifact": rel, "exists": True,
            "sha256_12": sha12(p), "branch": br.get("branch"), "branch_rule": br.get("rule"),
            "angle_diff_deg_max": agg.get("angle_diff_deg_max"),
            "angle_diff_deg_median": agg.get("angle_diff_deg_median"),
            "n_episodes_measured": agg.get("n_episodes"),
            "settle_steps_dropped_set": agg.get("settle_steps_dropped_set"),
            "negative_controls_all_bite": (d.get("negative_controls") or {}).get("all_bite"),
            "why": None}


def build_reuse() -> dict:
    """`S4B.load_reuse()` 原样复用（含 E 的三网探测器身份、zs 的 `build_policy`/`adapt_action`），
    再补上本件特有的两件（先落腿脚本 + 准入闸）的身份三元组（裁定 64：只有路径的引用不可核验）。"""
    r = S4B.load_reuse()
    r["S4B"] = S4B
    r["PRE"] = PRE
    r["GATE"] = GATE
    r["identity"].update({
        "step1_prealign_verify": identity("scripts/a2_step1_prealign_verify.py"),
        "bc_admission_gate": identity("harness/bc_admission_gate.py"),
        "s4b_pi05_gpu_run": identity("scripts/a2_s4b_pi05_gpu_run.py"),
        "this_script": identity(SELF_REL),
    })
    return r


# ══════════════════════════ ① admission（**复用**唯一消费入口）══════════════════════════
G14_CHECKED_BY_DEFAULT = ("F（裁定 97.3-4 的裁定值；A2 **只引不判**，语义归属的扫描旁证见 "
                          "`g14_provenance.json`）")
G14_CHECKED_WHEN_DEFAULT = "A2 第 1 步开跑前（裁定 97.3-4）"


def regenerate_g14_provenance(out_dir: pathlib.Path, gate_verdict_path: str, *,
                              checked_by: str, checked_when: str) -> dict:
    """**当场重跑** `scripts/a2_g14_provenance_scan.py`（不复用 14:19 那一份）。

    为什么必须重跑：那件的一半结论是「F 的写入面里**没有**独立判定 `G14` 翻转的件」——
    这是一条**否定存在性**结论，而 F 的写入面是活件（14:19 之后 F 可能已经落了新件）。
    转录旧读数 = 缺陷类 ㉒（把时点读数当常驻身份）。
    """
    import subprocess
    out_p = out_dir / "g14_provenance.json"
    cmd = [sys.executable, str(REPO / "scripts/a2_g14_provenance_scan.py"),
           "--gate-verdict-json", str(gate_verdict_path), "--out", str(out_p),
           "--checked-by", checked_by, "--checked-when", checked_when]
    rec: dict = {"cmd": cmd, "measurement_status": "not_measured"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(REPO))
        rec.update({"returncode": r.returncode, "stdout_tail": (r.stdout or "")[-1500:],
                    "stderr_tail": (r.stderr or "")[-1500:],
                    "measurement_status": "measured" if r.returncode == 0 else "measured_failed"})
    except Exception as exc:                                              # noqa: BLE001
        rec.update({"error": f"{type(exc).__name__}: {exc}", "measurement_status": "not_measured"})
    if out_p.exists():
        try:
            gj = json.loads(out_p.read_text(encoding="utf-8", errors="replace"))
            rec.update({"path": GATE._rel(out_p), "identity": GATE._stream_identity(out_p),
                        "conclusion": gj.get("conclusion"),
                        "f_independent_g14_verdict_artifact": gj.get("f_independent_g14_verdict_artifact"),
                        "variant_scan": gj.get("variant_scan"),
                        "positive_control": gj.get("positive_control"),
                        "note_for_consumer": gj.get("note_for_consumer")})
        except Exception as exc:                                          # noqa: BLE001
            rec.update({"parse_error": f"{type(exc).__name__}: {exc}"})
    return rec


def build_g14_precondition(args, out_dir: pathlib.Path, findings) -> dict:
    """裁定 97.3-4 的一次性前置。**声明的 sha 不由 A2 自己复算充当**（那样闸的
    「声明 vs 复算」对账就恒真、失去咬合力）：默认从 **C2 广播件解析**出 ② 的路径与声明 sha
    （用闸自己的 `parse_c2_broadcast`，无 glob、无 latest-run 推断），再让闸去复算对账。"""
    prov_rec: dict = {}
    if args.g14_evidence_path and args.g14_evidence_sha256_12:
        g14 = {"g14_flip_evidence_path": args.g14_evidence_path,
               "g14_flip_evidence_sha256_12": args.g14_evidence_sha256_12,
               "g14_flip_checked_by": args.g14_checked_by,
               "g14_flip_checked_when": args.g14_checked_when,
               "declaration_source": "CLI 显式给定"}
    else:
        try:
            parsed = GATE.parse_c2_broadcast(REPO / GATE.BROADCAST_DOC_DEFAULT)
            d0 = parsed.get("declaration") or {}
            g14 = {"g14_flip_evidence_path": d0.get("gate_verdict_path"),
                   "g14_flip_evidence_sha256_12": d0.get("gate_verdict_sha256_12"),
                   "g14_flip_checked_by": args.g14_checked_by,
                   "g14_flip_checked_when": args.g14_checked_when,
                   "declaration_source": ("**C2 的成对广播件**（`GATE.parse_c2_broadcast` 解析出来的 "
                                          "`gate_verdict_path` / `gate_verdict_sha256_12`，即广播里的 ②）；"
                                          "A2 不自拼路径、不自己复算 sha 充当声明（否则闸的声明 vs 复算"
                                          "对账恒真、失去咬合力）"),
                   "broadcast_doc_sha256_12": d0.get("broadcast_doc_sha256_12"),
                   "broadcast_as_of": d0.get("as_of")}
        except Exception as exc:                                          # noqa: BLE001
            g14 = {"g14_flip_evidence_path": None, "g14_flip_evidence_sha256_12": None,
                   "g14_flip_checked_by": args.g14_checked_by,
                   "g14_flip_checked_when": args.g14_checked_when,
                   "parse_error": f"{type(exc).__name__}: {exc}"}
    if g14.get("g14_flip_evidence_path"):
        prov_rec = regenerate_g14_provenance(
            out_dir, str(REPO / GATE._rel(g14["g14_flip_evidence_path"])),
            checked_by=str(g14.get("g14_flip_checked_by")), checked_when=str(g14.get("g14_flip_checked_when")))
        # 组装方式**照抄** `GATE.main()` 的那一段（同一实现口径，不另造）
        g14["provenance_evidence"] = {k: prov_rec.get(k) for k in
                                      ("path", "identity", "conclusion",
                                       "f_independent_g14_verdict_artifact", "variant_scan",
                                       "positive_control", "measurement_status", "returncode", "error")}
        g14["provenance_note"] = prov_rec.get("note_for_consumer")
        g14["provenance_regenerated_this_run"] = True
        g14["provenance_why_regenerated"] = (
            "旧件的半边结论是「F 的写入面里**没有**独立 G14 判定件」= 否定存在性，而 F 的写入面是活件 ⇒ "
            "转录旧读数 = 缺陷类 ㉒（把时点读数当常驻身份）")
        if prov_rec.get("returncode") not in (0, None):
            findings.add("g14_provenance_scan_failed", verdict="RED", blocking=False,
                         subject="g14_provenance", evidence=prov_rec, ruling="裁定 97.3-4",
                         why="旁证扫描非零退出 ⇒ 归属结论不可用（不阻塞准入本身：闸只核证据件的存在与 sha）")
    return g14


def prealign_tooth_selftest() -> dict:
    """**两向自检**（裁定 93.8：审计器须自证；只装一向不许报绿）。

    正向：真产物 ⇒ GREEN。负向：四个变异体（`ok=false` / `n_not_measured=1` / `all_bite=false` /
    `n_fail=1`）⇒ 必须各自 RED。**特别是 `n_not_measured=0` 与 `n_fail=0` 这两个「0 是好值」的情形**
    —— 写稿第一版把它们判红了（`int(x or -1)` 的 falsy-zero），这颗自检就是它的负对照。
    """
    import copy
    real = pathlib.Path(PREALIGN_JSON_DEFAULT)
    rows: list[dict] = []

    def judge(pj: dict | None, label: str, expect: str) -> dict:
        red = _prealign_red_codes(pj)
        got = "GREEN" if not red else "RED"
        return {"case": label, "expect": expect, "got": got, "red_codes": red,
                "bite": (got == expect)}

    if real.exists():
        base = json.loads(real.read_text(encoding="utf-8"))
        rows.append(judge(base, "positive_real_artifact", "GREEN"))
        for label, mut in (
            ("NEG1_summary_ok_false", lambda d: d["summary"].__setitem__("ok", False)),
            ("NEG2_n_not_measured_1", lambda d: d["summary"].__setitem__("n_not_measured", 1)),
            ("NEG3_selftest_all_bite_false", lambda d: d["selftest"].__setitem__("all_bite", False)),
            ("NEG4_selftest_n_fail_1", lambda d: d["selftest"].__setitem__("n_fail", 1)),
            ("NEG5_red_leg_ids_nonempty", lambda d: d["summary"].__setitem__("red_leg_ids", ["L9"])),
            ("NEG6_zero_vals_must_stay_green_control", None),
        ):
            d2 = copy.deepcopy(base)
            if mut is None:
                # **falsy-zero 的正向对照**：把 0 显式写回 0，仍必须 GREEN（第一版在这里判红）
                d2["summary"]["n_not_measured"] = 0
                d2["selftest"]["n_fail"] = 0
                rows.append(judge(d2, label, "GREEN"))
            else:
                mut(d2)
                rows.append(judge(d2, label, "RED"))
    else:
        rows.append({"case": "positive_real_artifact", "expect": "GREEN", "got": "not_measured",
                    "bite": None, "why": f"{real} 不在盘 ⇒ 正向对照不可测（不是「通过」）"})
    ok = [r for r in rows if r.get("bite") is True]
    return {"tooth_id": "A2T1_selftest_two_way", "n_rows": len(rows), "n_bite": len(ok),
            "all_bite": bool(rows) and len(ok) == len(rows),
            "measurement_status": "measured" if rows else "not_measured", "rows": rows}


def _prealign_red_codes(pj: dict | None) -> list[str]:
    """先落腿产物的判据（与 `stage_admission` 里那颗牙**同一份实现**，避免两处判据分叉）。"""
    if pj is None:
        return ["prealign_artifact_unreadable"]
    s = pj.get("summary") or {}
    st = pj.get("selftest") or {}
    red: list[str] = []
    if s.get("ok") is not True:
        red.append("prealign_summary_ok_not_true")
    n_nm = s.get("n_not_measured")
    if not isinstance(n_nm, int) or n_nm != 0:
        red.append(f"prealign_n_not_measured_{n_nm!r}")
    if s.get("red_leg_ids") or s.get("blocking_leg_ids"):
        red.append("prealign_has_red_or_blocking_legs")
    n_fail = st.get("n_fail")
    if st.get("all_bite") is not True or not isinstance(n_fail, int) or n_fail != 0:
        red.append(f"prealign_selftest_not_all_bite(all_bite={st.get('all_bite')!r}, n_fail={n_fail!r})")
    return red


def stage_admission(args, out_dir: pathlib.Path, findings) -> dict:
    """`consume_c2_broadcast()` 是**唯一**消费入口（补单四 §二：不许自己 glob）。
    A2 在这里**加一颗自己的牙**：先落腿 `PREALIGN_VERIFICATION.json` 必须存在且 `summary.ok=true`
    —— 理由：先落腿实测掉的三个静默错形状（归一化 pass-through / `-1` bin 进 prompt / 示范初态复现不了）
    任何一个回来，第 1 步都会**白跑一轮上卡**（补单四 §二 的 sha 口径差已经白跑过一半）。"""
    doc = base_doc("bc_admission_step1", args)
    t0 = time.perf_counter()
    pre_path = pathlib.Path(args.prealign_json)
    if not pre_path.is_absolute():
        pre_path = REPO / pre_path
    tooth: dict = {"tooth_id": "A2T1_prealign_verification_must_be_ok",
                   "path": str(pre_path), "exists": pre_path.exists(),
                   "measurement_status": "not_measured", "verdict": None, "bite": None}
    if pre_path.exists():
        try:
            pj = load_json(pre_path)
            s = pj.get("summary") or {}
            st = pj.get("selftest") or {}
            tooth.update({
                "measurement_status": "measured",
                "sha256_12": sha12(pre_path),
                "bytes": pre_path.stat().st_size,
                "n_lines_wc": int(pre_path.read_text(encoding="utf-8", errors="replace").count("\n")),
                "n_lines_splitlines": len(pre_path.read_text(encoding="utf-8", errors="replace").splitlines()),
                "as_of_in_artifact": pj.get("as_of"),
                "summary_ok": s.get("ok"), "n_legs": s.get("n_legs"), "n_measured": s.get("n_measured"),
                "n_not_measured": s.get("n_not_measured"),
                "red_leg_ids": s.get("red_leg_ids"), "blocking_leg_ids": s.get("blocking_leg_ids"),
                "warnings": s.get("warnings"),
                "selftest_all_bite": st.get("all_bite"), "selftest_n_teeth": st.get("n_teeth"),
                "selftest_n_fail": st.get("n_fail"),
                "prealign_gpu_used": pj.get("gpu_used"), "prealign_policy_executed": pj.get("policy_executed"),
            })
            # 判据**只有一份实现**（`_prealign_red_codes`），自检与实跑共用 ⇒ 不会两处判据分叉。
            # 内含 falsy-zero 纪律：`0` 是合法好值，写稿第一版用 `int(x or -1)` 把 0 变成 -1 ⇒ 好值判红
            # （缺陷类 ⑲ 同型：判据的极性与对象空间不一致），已修，并由 `prealign_tooth_selftest()`
            # 的 NEG6 正向对照钉住。
            red = _prealign_red_codes(pj)
            tooth.update({"verdict": "GREEN" if not red else "RED", "red_codes": red,
                          "selftest": prealign_tooth_selftest()})
            if tooth["selftest"]["all_bite"] is not True:
                red = red + ["prealign_tooth_selftest_not_all_bite"]
                tooth.update({"verdict": "RED", "red_codes": red})
        except Exception as exc:                                          # noqa: BLE001
            tooth.update({"measurement_status": "not_measured", "verdict": "RED",
                          "error": f"{type(exc).__name__}: {exc}"})
    else:
        tooth.update({"verdict": "RED", "red_codes": ["prealign_artifact_absent"],
                      "why": "先落腿产物不在盘 ⇒ 第 1 步的三个静默错形状没有被实测掉过 ⇒ 拒"})
    doc["a2_own_tooth"] = tooth

    g14 = build_g14_precondition(args, out_dir, findings)
    doc["g14_precondition_supplied"] = g14

    dec: dict = {}
    try:
        dec = GATE.consume_c2_broadcast(
            g14=(g14 or None),
            consumer="bc_step1_overfit",
            start_authority=("rl_harness_supervision/d_handoff_to_a2_20260930.md 补单四 §一/§五-②"
                             "（裁定 98 + 98.10-四：停点已解除，不得停在 ready）"),
            remaining_preconditions_before_card=("① 本件 `--declaration-line` 指到的 daily_report 申报行"
                                                 "（行内写入口脚本名，RR1(a)）；② 起跑那一刻实测三网并落 "
                                                 "`GPU_WINDOW.json`，拒绝逻辑读 E 的 `card_busy()`"),
            extra_context={"a2_own_tooth": tooth, "step": 1,
                           "note": "A2 的牙与 C2 的闸是 AND：任一不成立 ⇒ 拒"},
        )
    except Exception as exc:                                              # noqa: BLE001
        import traceback
        dec = {"admitted": False, "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()[-3000:]}
    doc["c2_broadcast_consumption"] = dec
    doc["admitted"] = bool(dec.get("admitted")) and tooth.get("verdict") == "GREEN"
    doc["admitted_and_rule"] = "C2 的 `consume_c2_broadcast().admitted` ∧ A2 自己的先落腿牙（AND，不是 OR）"
    doc["blocking_refusals"] = list(dec.get("blocking_refusals") or []) + \
        ([] if tooth.get("verdict") == "GREEN" else [{"code": tooth["tooth_id"],
                                                      "red_codes": tooth.get("red_codes")}])
    doc["not_measured_items"] = list(dec.get("not_measured_items") or [])
    doc["warnings"] = list(dec.get("warnings") or [])
    doc["n_lines_caliber_note"] = ("裁定 98.5：约束性判据 = `sha256[:12]`；行数必须点名口径。"
                                   "`*_n_lines_mismatch` 类 WARN（6728 vs 6729 = `wc -l` vs `splitlines`）"
                                   "**不得**当拒绝理由（98.10-四已记 A2 一功，本轮沿用同一处置）")
    doc["wall_s"] = round(time.perf_counter() - t0, 3)
    doc["measurement_status"] = "measured"
    if not doc["admitted"]:
        findings.add("admission_refused", verdict="RED", blocking=True, subject="bc_admission",
                     evidence={"blocking_refusals": doc["blocking_refusals"],
                               "not_measured_items": doc["not_measured_items"]},
                     ruling="补单四 §二 · 裁定 97.7（成对缺一 ⇒ LearnerRefused）",
                     why="准入不成立 ⇒ 第 1 步不许开跑")
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    p = out_dir / f"BC_ADMISSION_STEP1_{ts}.json"
    ident = write_json(p, doc)
    stable = out_dir / "BC_ADMISSION_STEP1.json"
    write_json(stable, doc)
    print(f"[admission] admitted={doc['admitted']} c2={dec.get('admitted')} "
          f"prealign_tooth={tooth.get('verdict')} artifact={ident['path']} {ident['sha256_12']}", flush=True)
    return doc


# ══════════════════════════ ② prereg（裁定 95.5-①②③）══════════════════════════
def stage_prereg(args, out_dir: pathlib.Path, findings) -> dict:
    p = out_dir / PREREG_NAME
    if p.exists() and not args.allow_prereg_overwrite:
        doc = load_json(p)
        doc["_note"] = ("`PRE_REGISTRATION.json` 已在盘 ⇒ **原字节保留、不追改**（预登记的意义就在于它先于结果；"
                        "重写它 = 事后编造）。要改必须先报 D 并显式 `--allow-prereg-overwrite`（会留前像）")
        print(f"[prereg] v1 已在盘，**不重写**：{p} {sha12(p)}", flush=True)
        return write_prereg_v2(args, out_dir, findings, doc)
    if p.exists() and args.allow_prereg_overwrite:
        before = out_dir / "before_images"
        before.mkdir(parents=True, exist_ok=True)
        bp = before / f"{PREREG_NAME}.before_{sha12(p)}"
        bp.write_bytes(p.read_bytes())
        print(f"[prereg] 覆盖前像已留：{bp}", flush=True)

    man = load_json(REPO / PRE.P_MANIFEST)
    eps = man["episodes"]

    def rows(idxs):
        return [{"episode_index": i, "ep_id": eps[i]["ep_id"], "seed": int(eps[i]["seed"]),
                 "manifest_direction": eps[i]["direction"],
                 "env_direction": DIRECTION_BY_MANIFEST[eps[i]["direction"]],
                 "task_text": eps[i]["task_text"],
                 "dataset_sha256_12": sha12(REPO / PRE.P_DS / "meta" / "info.json")} for i in idxs]

    doc = base_doc(
        "bc_step1_pre_registration", args,
        preregistered_before_any_result=True,
        why_this_file_exists=("裁定 95.5-③：`checkpoint 选择规则必须在开跑前预登记`（ACT 线吃过 "
                              "`checkpoints/last` 是未被验证的选择、且 seed × checkpoint 共同决定 的亏）；"
                              "裁定 95.5-①：整条 episode 划分；95.5-②：stats 与阈值开跑即冻结"),
        hypothesis_under_test=STEP1_QUESTION_VERBATIM,
        acceptance_criteria_verbatim=STEP1_CRITERION_VERBATIM,
        data_split={
            "rule": SPLIT_RULE, "by_whole_episode": True,
            "train_episodes": TRAIN_EPISODES, "val_episodes": VAL_EPISODES,
            "untouched_episodes_count": len(UNTOUCHED_EPISODES),
            "untouched_episodes_reserved_for": "第 2 步（裁定 95.5-② 的留出集升级排在第 2 步之后）",
            "overlap_train_val": sorted(set(TRAIN_EPISODES) & set(VAL_EPISODES)),
            "train_rows": rows(TRAIN_EPISODES), "val_rows": rows(VAL_EPISODES),
            "final_test_uses_new_object_initial_states": ("**排在第 2 步**（裁定 95.5-①）；第 1 步的闭环初态"
                                                          "**就是示范初态**，这是判据原文要求的，不是测试集"),
        },
        frozen_inputs={
            "stats_path": PRE.P_C2_STATS,
            "stats_sha256_12": sha12(REPO / PRE.P_C2_STATS),
            "npz_source": PRE.P_NPZ, "npz_sha256_12": sha12(REPO / PRE.P_NPZ),
            "dataset_dir": PRE.P_DS, "dataset_info_sha256_12": sha12(REPO / PRE.P_DS / "meta" / "info.json"),
            "base_weights_dir": args.weights_dir,
            "base_weights_config_sha256_12": sha12(pathlib.Path(args.weights_dir_resolved) / "config.json"),
            "freeze_rule": ("裁定 95.5-②：本轮 formal-40 的 stats 与 93.2 的阈值**一经第 1 步开跑即冻结**；"
                            "换 stats 必须先报 D（C2 广播件 §3）"),
        },
        checkpoint_selection_rule=CHECKPOINT_SELECTION_RULE,
        checkpoint_candidates_steps=resolve_ckpt_steps(args),
        val_loss_caliber=VAL_LOSS_CALIBER,
        det_rng_seed=DET_RNG_SEED,
        det_subset_size=int(args.det_subset_size),
        det_subset_rule=("从 train / val 各自的有效样本里用 `np.random.default_rng(DET_RNG_SEED)` "
                         "**不放回**抽 `det_subset_size` 个，抽一次、全程复用同一份索引与同一份 (noise,time)"),
        hyperparameters={
            "precision_primary": args.precision,
            "precision_fallback": "float32（**仅当** bf16 出现非有限 loss 时启用，且必须在产物里报 D）",
            "fp32_not_probed_reason": ("算术：3.617B 参数 × (4B 参数 + 4B 梯度 + 8B AdamW 一二阶矩) = "
                                       "**57.9 GB**，还没算激活 ⇒ 在 80 GB 卡上属「偏紧、OOM 风险高」；"
                                       "bf16 同项 = 28.9 GB ⇒ 预登记 bf16 为主、fp32 为后备，**不实测 fp32**"),
            "lr": float(args.lr), "lr_source": ("**预登记固定值**，不调参。取 ckpt 自带 `optimizer_lr=2.5e-5` 的 "
                                                f"{round(float(args.lr) / 2.5e-5, 1)}×（过拟合探针要在有限步数里"
                                                "打出可判的下降；第 2 步的正式 BC 另议）"),
            "betas": [0.9, 0.95], "eps": 1e-8, "weight_decay": 0.01,
            "grad_clip_norm": 1.0, "scheduler": "无（探针步数 < ckpt 的 warmup 1000 ⇒ 常数 lr）",
            "batch_size": ("由 `probe` 阶段按 `batch_selection_rule` **实测**决定（预登记的是规则，不是数字）"
                           if int(args.batch_size) <= 0 else int(args.batch_size)),
            "batch_selection_rule": (
                "在 probe 实测的 (gradient_checkpointing, batch_size) 组合里，取**满足 "
                "`peak_reserved_mib ≤ VRAM_CEILING_MIB` 的最大 batch_size**；同一 batch 下优先"
                "**不开**梯度检查点（更快）；都不满足 ⇒ 降 batch 到 1 并开梯度检查点；仍不满足 ⇒ 停下报 D"),
            "VRAM_CEILING_MIB": int(args.vram_ceiling_mib),
            "train_steps": int(args.train_steps),
            "grad_checkpointing_candidates": [True, False],
            "batch_size_candidates": [int(x) for x in str(args.batch_candidates).split(",") if x.strip()],
            "n_train_epochs_implied": ("train_steps × batch_size ÷ 有效训练样本数（开跑后在 TRAIN_REPORT 里"
                                       "**实测回填**，不是预登记的量）"),
        },
        gates=dict(GATES),
        progress_metric=PROGRESS_METRIC_DEFINITION,
        progress_ladder={str(k): v for k, v in PROGRESS_LADDER.items()},
        random_baseline=RANDOM_BASELINE_DEFINITION,
        rollout_plan={
            "arms": [a.strip() for a in str(args.rollout_arms).split(",") if a.strip()],
            "arm_definitions": {k: ARMS.get(k, k) for k in
                                [a.strip() for a in str(args.rollout_arms).split(",") if a.strip()]},
            "arm_delta_table": ARM_DELTA_TABLE,
            "initial_states": ("**示范初态**（判据原文要求）：`rt.reset(seed)` 之后直接写 qpos 到示范 frame-0 "
                               "state + sidecar 的 `box_rest_after_settle_xyz`，`qvel=0` + `physics.forward()`；"
                               "复用先落腿 `_init_env_to_state`（L9 已自证 4/4 集 `state maxdiff = 0.0`），"
                               "并**每局回读自证**（超 `--state-reproduce-tol` ⇒ 该局 RED，不当成功也不当失败）"),
            "splits": [s.strip() for s in str(args.rollout_splits).split(",") if s.strip()],
            "exec_mode": VR.EXEC_MODE_STANDARD_SYNC, "prime_mode": VR.PRIME_MODE_NONE,
            "n_replan": int(args.n_replan), "chunk_size_expected": 50,
            "exec_mode_ruling": "裁定 95.3-④：第 1–2 步一律用标准同步动作块执行（**不用**后半段调度）",
            "renderer": "egl / nvidia_gpu（与训练数据采集同口径；`renderer_class` 三点各自独立测）",
            "judgment_layer": "C2 的 `judge_from_facts`（经 `GymAlohaJudgedAdapter`），A2 **不重算任何判定**",
            "four_fields_ruling": "裁定 95.3-①：四字段分开记，`out_of_distribution` **只标注不剔除**",
        },
        budget={
            "step1_counts_toward_24h": False,
            "budget_ruling": ("补单四 §三（用户已批）：**第 1 步的过拟合探针不计入 24 h**；第 2 步 = 1×A800 · "
                              "总墙钟 ≤24 h · ≥3 种子 ⇒ 每种子 ≤8 h"),
            "escalation_rule": "**若第 1 步显示单种子需 >8 h ⇒ 立刻报 D，不得静默超预算**（超预算的数字 D 不认）",
            "single_seed_wall_s_over_8h": None,
        },
        reporting={
            "format": "裁定 95.6 六问 + **每种子单独报数**（不许只报均值、不许挑最高）",
            "per_seed": True,
            "blind_dim_restriction": ("盲点维 [0,3,5,7,10,12] 不得写成全 14 维结论"
                                      "（C2 广播件明写、D 追认；裁定 94.3/95.5-④）"),
            "capability_claim_ban": RULING_46,
        },
        stop_point=("**第 1 步出结果 ⇒ 按六问答完 ⇒ 停，等 D 的里程碑审查**（补单四 §四）。"
                    "**不要顺手开第 2 步**，即使卡空着"),
    )
    ident = write_json(p, doc)
    print(f"[prereg] 预登记落盘：{ident['path']} {ident['sha256_12']} "
          f"(train={TRAIN_EPISODES} val={VAL_EPISODES} steps={args.train_steps} lr={args.lr})", flush=True)
    return write_prereg_v2(args, out_dir, findings, doc)


def write_prereg_v2(args, out_dir: pathlib.Path, findings, v1_doc: dict) -> dict:
    """**预登记 v2**（补单七 §三）：**追加、不覆写**。

    三条硬要求：
    ① v1（`PRE_REGISTRATION.json`）**原字节**进 `before_images/`，一个字节不改；
    ② v2 写**新文件** `PRE_REGISTRATION_v2.json`，带 `amendment_reason` +
       `amended_before_any_train_or_rollout_result`（**由盘上事实证**，不是自述）；
    ③ 新牙（`A2T6` 出场判据 / `A2T7` 平台期规则）的**两向变异体自证必须在这里干跑一遍**
       （裁定 99.3：先干跑再上卡；裁定 93.8：只装一向不许报绿）。
    """
    if not bool(getattr(args, "prereg_v2", False)):
        return v1_doc
    p2 = out_dir / PREREG_V2_NAME
    if p2.exists():
        doc2 = load_json(p2)
        print(f"[prereg] v2 已在盘，**不重写**：{p2} {sha12(p2)}", flush=True)
        return doc2
    p1 = out_dir / PREREG_NAME
    before = out_dir / "before_images"
    before.mkdir(parents=True, exist_ok=True)
    v1_before_ident = None
    if p1.exists():
        bp = before / f"{PREREG_NAME}.before_{sha12(p1)}"
        if not bp.exists():
            bp.write_bytes(p1.read_bytes())
        v1_before_ident = identity(str(bp.relative_to(REPO)))
        print(f"[prereg] v1 原字节已进前像：{bp} {sha12(bp)}", flush=True)

    # ── ②「在任何 train/rollout 结果产生之前」由**盘上事实**证，不靠自述 ──
    result_files = {n: bool((out_dir / n).exists()) for n in
                    ("TRAIN_REPORT.json", "ROLLOUT_REPORT.json", "STEP1_RESULT.json",
                     "CHECKPOINT_SELECTION.json", PROBE_NAME)}
    ckpt_dirs = sorted(str(x.relative_to(out_dir)) for x in out_dir.glob("checkpoints/step_*"))
    ledger_hits = sorted(str(x.relative_to(out_dir)) for x in out_dir.glob("*ledger*"))
    amended_before = not (any(result_files.values()) or ckpt_dirs)

    # ── ③ 两颗新牙的干跑（纯 CPU、合成夹具，**不消费任何真读数**）──
    st6 = closed_loop_reproduction_selftest()
    st7 = plateau_rule_selftest()
    for st, fid in ((st6, "exit_criterion_tooth_selftest_not_bite_at_prereg"),
                    (st7, "plateau_rule_selftest_not_bite_at_prereg")):
        if not st["all_bite"]:
            findings.add(fid, verdict="RED", blocking=True, subject="preregistered_tooth_dry_run",
                         evidence={k: v for k, v in st.items() if k != "rows"},
                         ruling="裁定 93.8 / 99.3（只装一向不许报绿；预登记判据必须先干跑）",
                         why="新牙在干跑里没全咬 ⇒ 它没有分辨力 ⇒ 不许上卡用它出判词")
    if not amended_before:
        findings.add("prereg_v2_amended_after_results_exist", verdict="RED", blocking=True,
                     subject="pre_registration_v2",
                     evidence={"result_files_present": result_files, "checkpoint_dirs": ckpt_dirs,
                               "ledger_hits": ledger_hits},
                     ruling="补单七 §三（v2 **必须在任何 train/rollout 结果产生之前**落盘）· 裁定 95.5-③",
                     why="盘上已有 train/rollout 产物 ⇒ 现在改判据 = **事后改判据** ⇒ 无效")

    doc2 = dict(v1_doc)
    doc2.pop("_note", None)
    doc2.update({
        "artifact": "bc_step1_pre_registration_v2",
        "as_of": now_iso(),
        "prereg_version": 2,
        "append_not_overwrite": True,
        "supersedes": {"path": str(p1.relative_to(REPO)) if p1.exists() else None,
                       **(identity(str(p1.relative_to(REPO))) if p1.exists() else {}),
                       "disposition": "**原字节保留、一个字节不改**；v2 是**新文件**（补单七 §三）"},
        "v1_original_bytes_preserved_at": v1_before_ident,
        "amendment_reason": "裁定 102.2-①：用户 Step 1 验收标准第 2 条是出场判据",
        "amendment_reason_full": (
            "A2 的 v1 预登记写的是 `success_rate_column=\"not_an_exit_criterion\"`、唯一阻塞牙是 "
            "`progress_not_gt_random`；而用户 Step 1 验收标准第 2 条原文 = 「**至少一条正向和一条反向轨迹"
            "能从示范初态闭环复现**」⇒ 裁定 102.2-①：**第 2 条是出场判据**。同批落地裁定 102.2-②③④"
            "（不提前停 + `plateau_reached` / 四臂必需 / 产出⑤的逐集+跨集口径）与裁定 101.2"
            "（固定条件、六项产出、四条验收标准逐字采纳；R1/R2 并入产出③④）"),
        "amended_before_any_train_or_rollout_result": bool(amended_before),
        "amended_before_evidence": {
            "how_proved": "**由盘上事实证，不是自述**：v2 落盘这一刻扫描 out_dir",
            "result_files_present": result_files,
            "checkpoint_dirs_present": ckpt_dirs,
            "ledger_files_present": ledger_hits,
            "conclusion": ("盘上没有任何 train/rollout 产物 ⇒ 本 v2 **先于**一切结果"
                           if amended_before else
                           "**盘上已有产物 ⇒ 本 v2 无效**（已置阻塞红 `prereg_v2_amended_after_results_exist`）"),
        },
        "amendments": [
            {"id": "裁定 102.2-①", "topic": "**闭环复现 = 出场判据**",
             "v1": "`success_rate_column=\"not_an_exit_criterion\"`；唯一阻塞牙 = `progress_not_gt_random`",
             "v2": (f"`success_rate_column=\"{SUCCESS_RATE_COLUMN}\"`；新阻塞牙 = "
                    f"`{GATES['closed_loop_reproduction_tooth_id']}`（bc ∧ train split ∧ 正向 ≥"
                    f"{GATES['closed_loop_reproduction_min_forward_train_episodes']} ∧ 反向 ≥"
                    f"{GATES['closed_loop_reproduction_min_reverse_train_episodes']} ∧ "
                    "`geometric_success==True`）；`progress_not_gt_random` 降为 `blocking=false` 的诊断读数"),
             "preregistered_numbers_changed": "**0 个**（阈值 `progress_gt_random=True` 与 `tiebreak_order` 原样保留）"},
            {"id": "裁定 102.2-②", "topic": "**不提前停** + `plateau_reached` + `train_det_loss_final_over_step0`",
             "v1": "`train_steps` 固定跑完，无平台期规则、无 `plateau_reached` 字段",
             "v2": f"`plateau_rule` = {json.dumps(PLATEAU_RULE['continue_iff'], ensure_ascii=False)}；"
                   "产物落 `plateau_reached`(三值) + `train_det_loss_final_over_step0`(实测) + `stopped_by`",
             "preregistered_numbers_changed": (
                 "**0 个**：`train_det_loss_final_over_step0_max=0.5` / `per_dim_mae_rel_max_observed_dims=0.05` / "
                 "`per_dim_corr_min_observed_dims=0.9` / `gripper_transition_frames_max=5` **一个不改**"
                 "（裁定 102.2-②(a)）")},
            {"id": "裁定 102.2-③", "topic": "**四臂必需**",
             "v1": f"`DEFAULT_ARMS=\"bc,injected_base,base_zeroshot,random,hold\"`（五臂平列、无必需/可选之分）",
             "v2": (f"`REQUIRED_ARMS={list(REQUIRED_ARMS)}`（缺任一 ⇒ 阻塞红）；"
                    f"`OPTIONAL_ARMS={list(OPTIONAL_ARMS)}` 排最后、不得推迟报告；"
                    f"`DEFAULT_ARMS=\"{DEFAULT_ARMS}\"`"),
             "preregistered_numbers_changed": "0 个"},
            {"id": "裁定 102.2-④", "topic": "产出⑤「每步动作间隔」的口径",
             "v1": "只逐集落 `wall_ms_per_ctrl_step`（均值），无跨集分布",
             "v2": ("逐集 `wall_ms_per_ctrl_step` + **跨集分布**（n/min/p25/median/p75/max/mean/std）+ "
                    "`budget_fraction` / `overload_flag`；`wall_ms` 与 `amortized_inference_ms` **分列**"
                    "（裁定 75.5）；intra-episode 百分位 = `OPEN-STEP2-TIMING-PERCENTILES`（第 2 步前置、非阻塞）"),
             "preregistered_numbers_changed": "0 个"},
            {"id": "裁定 101.2", "topic": "用户原文逐字落地 + R1/R2 并入产出③④",
             "v1": "只引裁定 95.2 第 1 行的判据原文",
             "v2": ("`fixed_conditions_verbatim` / `required_outputs_verbatim` / "
                    "`acceptance_criteria_verbatim_user_four` 三份逐字落盘；**总判改由用户原文的四条验收标准出**；"
                    "R1 = 产出③ 的臂侧取证、R2 = 产出④ 的夹爪转变帧误差（**消费既有判词件，A2 不重算**）"),
             "preregistered_numbers_changed": "0 个"},
        ],
        "fixed_conditions_verbatim": STEP1_FIXED_CONDITIONS_VERBATIM,
        "required_outputs_verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM,
        "acceptance_criteria_verbatim_user_four": STEP1_ACCEPTANCE_CRITERIA_VERBATIM,
        "authoritative_verdict_rule": (
            "**四条全过 ⇒ PASS；任一不过 ⇒ RED；任一 `pass=null` ⇒ `null` + 非零退出**（三值纪律）。"
            "`not_applicable` 的条不计入 AND。v1 的「三半」口径**保留照报**、但不再是总判"),
        "criterion_3_rule": CRITERION_3_RULE,
        "r1r2_evidence_sources": {"r1r2_verdict_json": args.r1r2_verdict_json,
                                  "r1r2_anchor_probe_json": args.r1r2_anchor_probe_json,
                                  "recomputes_nothing": True,
                                  "why": "裁定 101.2：R1/R2 并入 Step 1 的产出③④ ⇒ 只消费判词件、不重算"},
        "gates_v2": dict(GATES),
        "plateau_rule": PLATEAU_RULE,
        "arm_requirement_rule": ARM_REQUIREMENT_RULE,
        "timing_output_rule": TIMING_OUTPUT_RULE,
        "success_rate_column": SUCCESS_RATE_COLUMN,
        "success_rate_column_note": SUCCESS_RATE_COLUMN_NOTE,
        "unchanged_preregistered_numbers": {
            "train_det_loss_final_over_step0_max": GATES["train_det_loss_final_over_step0_max"],
            "per_dim_mae_rel_max_observed_dims": GATES["per_dim_mae_rel_max_observed_dims"],
            "per_dim_corr_min_observed_dims": GATES["per_dim_corr_min_observed_dims"],
            "gripper_transition_frames_max": GATES["gripper_transition_frames_max"],
            "progress_gt_random": GATES["progress_gt_random"],
            "statement": "**裁定 102.2-②(a)：这四个数（+ `progress_gt_random` 的阈值）一个不改**",
        },
        "new_teeth_dry_run_before_gpu": {
            "ruling": ("裁定 99.3（`preregistered_criterion_must_be_dry_run_on_the_object` ⇒ **先干跑再上卡**）· "
                       "裁定 93.8（只装一向不许报绿）· 补单七 §三（新牙带两向变异体自证）"),
            "A2T6_closed_loop_reproduction_two_way": {k: v for k, v in st6.items() if k != "rows"},
            "A2T6_rows": st6["rows"],
            "A2T7_plateau_rule_two_way": {k: v for k, v in st7.items() if k != "rows"},
            "A2T7_rows": st7["rows"],
            "all_bite": bool(st6["all_bite"] and st7["all_bite"]),
            "gpu_used_for_dry_run": False,
            "consumed_real_readings": False,
        },
        "open_items": OPEN_ITEMS_STEP1,
        "authority_v2": list(AUTHORITY),
        "capability_claim": False,
        "capability_note": ("**预登记不是能力声明**（裁定 46/101.3）：`policy 指标 = 0`；"
                            "`max_stage==4` 不是能力声明；本臂作用域 = `AlohaTransferCube-v0` 的左右臂交接"
                            "（**冒烟基准**），不得写成「单臂区域抓放能力」"),
        "stage_judgment_authoritative_wording": (
            "主线已成功纠偏，实验基础正在收敛；已有对齐和接口诊断产出，但策略学习结果仍为零。"
            "下一里程碑不是更多审计，而是标准同步执行下的双向 BC 过拟合与闭环复现。（裁定 101.3：**对外只用这一句**）"),
    })
    ident2 = write_json(p2, doc2)
    print(f"[prereg] **v2 落盘（追加、不覆写）**：{ident2['path']} {ident2['sha256_12']} "
          f"amended_before_any_result={amended_before} A2T6={st6['n_bite']}/{st6['n_rows']} "
          f"A2T7={st7['n_bite']}/{st7['n_rows']}", flush=True)
    return doc2


def resolve_ckpt_steps(args) -> list[int]:
    steps = [0]
    steps += [int(x) for x in str(args.ckpt_steps).split(",") if x.strip()]
    if int(args.train_steps) not in steps:
        steps.append(int(args.train_steps))
    return sorted(set(s for s in steps if 0 <= s <= int(args.train_steps)))


# ══════════════════════════ ③ cache（纯 CPU：把 PNG 解码挪出 GPU 窗口）══════════════
def _per_episode_n_frames() -> dict:
    ds = PRE.read_dataset_arrays(REPO / PRE.P_DS)
    return {int(k): int(v["n_frames"]) for k, v in ds["per_ep"].items()}, ds


def stage_cache(args, out_dir: pathlib.Path, findings) -> dict:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    doc = base_doc("bc_step1_data_cache", args)
    t0 = time.perf_counter()
    load_before = PBG.gpu_window_readings(extra={"phase": "cache_before"})
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    per_ep, dsraw = _per_episode_n_frames()
    info = dsraw["info"]
    fps = float(info.get("fps") or 0)
    H = int(args.chunk_size)
    if abs(fps - GATE.MAINLINE_CONTROL_HZ) > 1e-9:
        findings.add("fps_mismatch", verdict="RED", blocking=True, subject="dataset_fps",
                     evidence={"dataset_fps": fps, "mainline_control_hz": GATE.MAINLINE_CONTROL_HZ},
                     ruling="裁定 62-③ / `params:119` 同频纪律",
                     why="数据集 fps 与主线控制频率不同频 ⇒ 时间契约不成立，第 1 步不许开跑")
    delta = [i / fps for i in range(H)]
    out: dict = {"fps": fps, "chunk_size": H, "delta_timestamps_s": delta, "splits": {}}
    teeth: list[dict] = []
    for split, episodes in (("train", TRAIN_EPISODES), ("val", VAL_EPISODES)):
        path = cache_dir / f"samples_{split}.npz"
        if path.exists() and not args.force_cache:
            man = load_json(cache_dir / f"samples_{split}.manifest.json")
            out["splits"][split] = {"path": str(path), "reused_existing": True, **man}
            print(f"[cache:{split}] 复用已存在的缓存 {path}（{man.get('n_samples')} 样本）", flush=True)
            continue
        t1 = time.perf_counter()
        ds = LeRobotDataset("local/pi05_lerobot", root=(REPO / PRE.P_DS).resolve(), episodes=list(episodes),
                            delta_timestamps={"action": delta})
        # 全局索引 = 按 episode 升序拼接（**实测自证**，不假设）
        offs, acc = {}, 0
        for e in sorted(episodes):
            offs[e] = acc
            acc += per_ep[e]
        assert acc == len(ds), f"拼接长度 {acc} != len(ds) {len(ds)}"
        off_teeth = []
        for e in sorted(episodes):
            s = ds[offs[e]]
            ok = (int(s["episode_index"]) == e and int(s["frame_index"]) == 0)
            off_teeth.append({"episode_index": e, "offset": offs[e], "probe_episode_index": int(s["episode_index"]),
                              "probe_frame_index": int(s["frame_index"]), "ok": bool(ok)})
            if not ok:
                findings.add(f"cache_offset_mismatch:{split}:{e}", verdict="RED", blocking=True,
                             subject="dataset_index_mapping", evidence=off_teeth[-1], ruling="—",
                             why="(episode, frame) → 全局索引 的映射假设被实测打脸 ⇒ 缓存不可信")
        valid = [(e, f) for e in sorted(episodes) for f in range(per_ep[e] - H + 1)]
        n = len(valid)
        imgs = np.zeros((n, 3, 3, args.image_size, args.image_size), dtype=np.uint8)
        act = np.zeros((n, H, STATE_DIM), dtype=np.float32)
        sta = np.zeros((n, STATE_DIM), dtype=np.float32)
        epi = np.zeros((n,), dtype=np.int32)
        fri = np.zeros((n,), dtype=np.int32)
        tasks: list[str] = []
        max_roundtrip_err = 0.0
        n_pad_hits = 0
        for k, (e, f) in enumerate(valid):
            s = ds[offs[e] + f]
            assert int(s["episode_index"]) == e and int(s["frame_index"]) == f, \
                f"样本定位错：想要 (ep{e}, f{f})，拿到 (ep{int(s['episode_index'])}, f{int(s['frame_index'])})"
            a = np.asarray(s["action"], dtype=np.float32)
            if a.shape != (H, STATE_DIM):
                raise RuntimeError(f"action chunk 形状 {a.shape} != {(H, STATE_DIM)}")
            if bool(np.asarray(s["action_is_pad"]).any()):
                n_pad_hits += 1
            for j, key in enumerate(IMG_KEYS):
                im = np.asarray(s[key], dtype=np.float32)
                u8 = np.rint(np.clip(im, 0.0, 1.0) * 255.0).astype(np.uint8)
                max_roundtrip_err = max(max_roundtrip_err, float(np.abs(u8.astype(np.float32) / 255.0 - im).max()))
                imgs[k, j] = u8
            act[k] = a
            sta[k] = np.asarray(s["observation.state"], dtype=np.float32)
            epi[k] = e
            fri[k] = f
            tasks.append(str(s["task"]))
            if (k + 1) % 200 == 0:
                print(f"[cache:{split}] {k + 1}/{n} 样本，已用 {round(time.perf_counter() - t1, 1)}s", flush=True)
        np.savez(path, images=imgs, action=act, state=sta, episode_index=epi, frame_index=fri)
        man = {"n_samples": n, "episodes": sorted(episodes), "task_by_row": tasks,
               "task_note": ("task 文本走 manifest JSON 而不是 npz 的 object 数组：`np.savez` 不接受 "
                             "`allow_pickle`，传进去只会被当成一个名为 `allow_pickle` 的**数组**存下来"
                             "（写稿时踩过，已修）⇒ 载入侧也不需要 `allow_pickle=True`"),
               "per_episode_n_frames": {str(e): per_ep[e] for e in episodes},
               "valid_frame_rule": f"frame_index + {H} <= n_frames（**排除**越界补零样本，免 mask）",
               "excluded_tail_frames_per_episode": H - 1,
               "n_pad_hits_must_be_0": n_pad_hits,
               "uint8_roundtrip_max_abs_err_must_be_0": max_roundtrip_err,
               "offset_selfproof": off_teeth,
               "images_dtype_stored": "uint8（喂模型前 `/255.0` 还原成 float32 [0,1]，见 `_preprocess_images` 的口径）",
               "action_dtype": "float32（物理单位，与数据集同）",
               "sha256_12": sha12(path), "bytes": path.stat().st_size,
               "decode_wall_s": round(time.perf_counter() - t1, 2)}
        write_json(cache_dir / f"samples_{split}.manifest.json", man)
        out["splits"][split] = {"path": str(path), "reused_existing": False, **man}
        teeth.append({"tooth_id": f"A2T2_cache_uint8_roundtrip_exact:{split}",
                      "expect": "max|uint8/255 − float32| == 0", "value": max_roundtrip_err,
                      "bite": max_roundtrip_err == 0.0})
        teeth.append({"tooth_id": f"A2T3_cache_no_pad_samples:{split}",
                      "expect": "action_is_pad 命中数 == 0", "value": n_pad_hits, "bite": n_pad_hits == 0})
        print(f"[cache:{split}] {n} 样本 → {path.name} {man['sha256_12']} "
              f"({man['decode_wall_s']}s, roundtrip_err={max_roundtrip_err}, pad={n_pad_hits})", flush=True)
    doc["cache"] = out
    doc["selftest_teeth"] = teeth
    doc["measurement_status"] = "measured"
    doc["load_pair"] = {"before": load_before, "after": PBG.gpu_window_readings(extra={"phase": "cache_after"})}
    doc["wall_s"] = round(time.perf_counter() - t0, 2)
    bad = [t for t in teeth if not t["bite"]]
    if bad:
        findings.add("cache_teeth_not_bite", verdict="RED", blocking=True, subject="data_cache",
                     evidence=bad, ruling="裁定 93.8（审计器须自证）", why="缓存的自证牙没咬 ⇒ 训练数据不可信")
    ident = write_json(out_dir / "CACHE_MANIFEST.json", doc)
    print(f"[cache] {ident['path']} {ident['sha256_12']}", flush=True)
    return doc


def load_cache(out_dir: pathlib.Path, split: str) -> dict:
    p = out_dir / "cache" / f"samples_{split}.npz"
    if not p.exists():
        raise FileNotFoundError(f"缺缓存 {p}（先跑 `--stages cache`；它是纯 CPU 阶段，故意排在 GPU 窗口之外）")
    z = np.load(p)
    man = load_json(p.parent / f"samples_{split}.manifest.json")
    tasks = [str(t) for t in (man.get("task_by_row") or [])]
    if len(tasks) != len(z["frame_index"]):
        raise RuntimeError(f"manifest 的 task 行数 {len(tasks)} != npz 的样本数 {len(z['frame_index'])} "
                           "⇒ 缓存与 manifest 不同源，停下（不许静默用空串顶替 prompt）")
    return {"images": z["images"], "action": z["action"], "state": z["state"],
            "episode_index": z["episode_index"], "frame_index": z["frame_index"],
            "task": tasks, "path": str(p), "sha256_12": sha12(p),
            "manifest_sha256_12": sha12(p.parent / f"samples_{split}.manifest.json")}


# ══════════════════════════ ④ 训练栈（stats 注入路径 = L1 已逐位自证过的那一条）══════
def build_training_stack(args, *, device: str, dtype: str, gradient_checkpointing: bool,
                         reuse: dict) -> tuple:
    """返回 `(policy, pre, post, cfg, inj_info)`。

    **不重造注入路径**：先调先落腿的 `PRE.build_cfg_and_processors()`（L1 已实测「注入后 q01/q99 与 C2
    实物**逐位相同**」），拿到它算好的 `injected_features` / `injected_stats`，再用同一份 overrides 重建
    一次处理器（只把 `device` 从 cpu 换成本臂的 device）。⇒ 训练臂的归一化器与先落腿验证过的**同一个**。
    """
    import torch
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.pi05.modeling_pi05 import PI05Policy

    wdir = pathlib.Path(args.weights_dir_resolved)
    stats = reuse["stats"]
    cfg0, _pre0, _post0, inj = PRE.build_cfg_and_processors(wdir, args.tokenizer_dir, stats, STATE_DIM)
    cfg0.device = device
    cfg0.dtype = dtype
    cfg0.gradient_checkpointing = bool(gradient_checkpointing)
    pre_over = {"normalizer_processor": {"features": inj["injected_features"], "stats": inj["injected_stats"]},
                "tokenizer_processor": {"tokenizer_name": args.tokenizer_dir},
                "device_processor": {"device": device}}
    post_over = {"unnormalizer_processor": {"features": {"action": {"type": "ACTION", "shape": [STATE_DIM]}},
                                            "stats": inj["injected_stats"]},
                 "device_processor": {"device": "cpu"}}
    pre, post = make_pre_post_processors(cfg0, str(wdir), preprocessor_overrides=pre_over,
                                         postprocessor_overrides=post_over)
    # ── 自证牙 A2T4：注入进真处理器的 q01/q99 与 C2 实物**逐位相同**（先落腿 L1 的同一判据）──
    npz_q01 = np.asarray(stats["q01"], dtype=np.float64)
    npz_q99 = np.asarray(stats["q99"], dtype=np.float64)
    # **口径与冻结的先落腿 L1 逐字对齐**（`scripts/a2_step1_prealign_verify.py:469`）：
    # ① 回读属性是 `NormalizerProcessorStep._tensor_stats`（**不是** `.config` —— 该实例没有这个属性，
    #    写错会让 A2T4 直接 `AttributeError`，见 `SELF_DEFECTS_STEP1` 的 D1）；
    # ② C2 的 npz 存的是 **float64**，而处理器管线是 **float32** ⇒ 比对前必须先
    #    `.astype(np.float32).astype(np.float64)`（**实测这一步不恒等**，不比就会假红，见 D2）。
    got: dict = {}
    norm_cls = None
    for step in pre.steps:
        if (type(step).__name__ == "NormalizerProcessorStep"
                or getattr(step.__class__, "_registry_name", "") == "normalizer_processor"):
            got = dict(getattr(step, "_tensor_stats", {}) or {})
            norm_cls = type(step).__name__
    ref_q01 = npz_q01.astype(np.float32).astype(np.float64)
    ref_q99 = npz_q99.astype(np.float32).astype(np.float64)
    bitwise = None
    if got and "observation.state" in got and "action" in got:
        a = np.asarray(got["observation.state"]["q01"], dtype=np.float64)
        b = np.asarray(got["observation.state"]["q99"], dtype=np.float64)
        c = np.asarray(got["action"]["q01"], dtype=np.float64)
        bitwise = bool(np.array_equal(a, ref_q01) and np.array_equal(b, ref_q99)
                       and np.array_equal(c, ref_q01))
    inj["stats_readback_A2T4"] = {
        "normalizer_step_class": norm_cls,
        "attribute_read": "_tensor_stats（**不是** `.config`；与冻结先落腿 `a2_step1_prealign_verify.py:469` 同源）",
        "features_present": sorted(got.keys()),
        "n_features": len(got),
        "comparison_caliber": ("C2 npz = float64、处理器管线 = float32 ⇒ 参考值先经 "
                               "`.astype(np.float32).astype(np.float64)`；**实测该 round-trip 不恒等**"
                               "（`q01` 14 维里存在末位差）⇒ 不做这一步就是**假红**"),
        "npz_q01_float64_equals_float32_roundtrip": bool(np.array_equal(npz_q01, ref_q01)),
        "bitwise_identical_to_c2": bitwise,
        "measurement_status": "measured" if bitwise is not None else "not_measured",
    }
    inj["stats_bitwise_identical_to_c2"] = bitwise
    inj["device"] = device
    inj["dtype"] = dtype
    inj["gradient_checkpointing"] = bool(gradient_checkpointing)
    if bitwise is not True:
        raise RuntimeError(f"stats 注入未逐位相符（bitwise={bitwise}）⇒ 停下，不许带着可疑的归一化器上卡")
    t0 = time.perf_counter()
    policy = PI05Policy.from_pretrained(str(wdir), config=cfg0)
    load_s = round(time.perf_counter() - t0, 2)
    policy = policy.to(device)
    inj["from_pretrained_load_s"] = load_s
    inj["n_parameters"] = int(sum(p.numel() for p in policy.parameters()))
    inj["n_trainable_parameters"] = int(sum(p.numel() for p in policy.parameters() if p.requires_grad))
    hist: dict = {}
    for p_ in policy.parameters():
        hist[str(p_.dtype)] = hist.get(str(p_.dtype), 0) + p_.numel()
    inj["param_dtype_hist"] = {k: int(v) for k, v in sorted(hist.items())}
    inj["feature_shape_14_rationale"] = (
        "`max_state_dim`/`max_action_dim`（=32）才是模型内部 padding 宽度，feature shape 是**接口宽度**；"
        "取 14 ⇒ `PI05Policy.forward` 的 loss 只截到真实 14 维（padding 维不当 0 目标训）、"
        "`predict_action_chunk` 也截到 14 ⇒ normalizer 与 unnormalizer 两侧同宽（先落腿结论 1）")
    inj["pi05_does_not_consume_state"] = {
        "finding": ("**实测的契约事实**：`PI05Pytorch.embed_prefix` 只吃 images + language tokens；"
                    "`PI05Policy.forward` 的注释原文 `Compute loss (no separate state needed for PI05)` ⇒ "
                    "`observation.state` **不进模型的条件**（它只经 `pi05_prepare_state_tokenizer_processor_step` "
                    "被离散成 bin 拼进 prompt 文本）"),
        "evidence": "lerobot 0.4.4 `policies/pi05/modeling_pi05.py`：`embed_prefix(images, img_masks, tokens, masks)`",
        "consequence": ("⇒ 状态通道的 6 个盲点维**不影响**本模型的动作预测条件（它们影响的是 prompt 里的 bin 文本）；"
                        "这条**收窄**了盲点维对本臂的作用面，但**不取消** 94.3/95.5-④ 的登记纪律"),
        "measurement_status": "measured_from_source",
    }
    return policy, pre, post, cfg0, inj


def make_batch(arrs: dict, idxs, *, image_size: int) -> dict:
    idxs = np.asarray(idxs, dtype=np.int64)
    b: dict = {}
    for j, key in enumerate(IMG_KEYS):
        b[key] = torch_from_numpy(arrs["images"][idxs, j].astype(np.float32) / 255.0)
    b["observation.state"] = torch_from_numpy(arrs["state"][idxs])
    b["action"] = torch_from_numpy(arrs["action"][idxs])
    b["task"] = [arrs["task"][int(i)] for i in idxs]
    return b


def torch_from_numpy(a):
    import torch
    return torch.from_numpy(np.ascontiguousarray(a))


def build_det_bank(arrs: dict, idxs, *, chunk_size: int, max_action_dim: int, seed: int) -> tuple:
    """固定 (noise, time) 银行：`noise ~ N(0,1)`（与 `PI05Pytorch.sample_noise` 同分布同 dtype=float32）、
    `time = Beta(alpha,beta)*scale + offset`（与 `sample_time` 同分布）。抽一次、全程复用。"""
    rng = np.random.default_rng(seed)
    n = len(idxs)
    noise = rng.standard_normal((n, chunk_size, max_action_dim)).astype(np.float32)
    beta = rng.beta(1.5, 1.0, size=n).astype(np.float32)
    time_v = (beta * 0.999 + 0.001).astype(np.float32)
    return noise, time_v


def det_loss(policy, pre, arrs: dict, idxs, noise_bank, time_bank, *, action_dim: int,
             image_size: int, bs: int) -> dict:
    """确定性损失：与 `policy.forward()` 同一条 `_preprocess_images`/`prepare_action` 路径，
    只把随机源换成固定源（见 `VAL_LOSS_CALIBER`）。"""
    import torch
    was_training = bool(policy.training)
    policy.eval()
    per_batch: list[float] = []
    per_dim_sum = np.zeros((action_dim,), dtype=np.float64)
    n_elem = 0
    t0 = time.perf_counter()
    with torch.no_grad():
        for s in range(0, len(idxs), bs):
            sel = list(range(s, min(s + bs, len(idxs))))
            batch = pre(make_batch(arrs, [idxs[i] for i in sel], image_size=image_size))
            images, img_masks = policy._preprocess_images(batch)
            tokens = batch[OBS_LANGUAGE_TOKENS]
            masks = batch[OBS_LANGUAGE_ATTENTION_MASK]
            actions = policy.prepare_action(batch)
            losses = policy.model.forward(images, img_masks, tokens, masks, actions,
                                          noise=torch_from_numpy(noise_bank[sel]).to(actions.device),
                                          time=torch_from_numpy(time_bank[sel]).to(actions.device))
            losses = losses[:, :, :action_dim]
            per_batch.append(float(losses.mean().item()))
            per_dim_sum += losses.sum(dim=(0, 1)).detach().double().cpu().numpy()
            n_elem += int(losses.shape[0] * losses.shape[1])
    if was_training:
        policy.train()
    mean = float(np.mean(per_batch)) if per_batch else float("nan")
    return {"loss": mean, "per_dim": (per_dim_sum / max(1, n_elem)).tolist(),
            "n_batches": len(per_batch), "n_samples": len(idxs),
            "wall_s": round(time.perf_counter() - t0, 2),
            "finite": bool(np.isfinite(mean)),
            "caliber": VAL_LOSS_CALIBER}


# ══════════════════════════ ⑤ probe（实测显存/时长 ⇒ 按预登记规则定档）══════════════
def stage_probe(args, out_dir: pathlib.Path, findings, reuse: dict, window) -> dict:
    import torch
    doc = base_doc("bc_step1_probe1step", args, gpu_used=True)
    t0 = time.perf_counter()
    load_before = PBG.gpu_window_readings(extra={"phase": "probe_before"})
    prereg = load_json(prereg_path(out_dir))
    hp = prereg["hyperparameters"]
    cands_bs = [int(x) for x in hp["batch_size_candidates"]]
    ceiling = int(hp["VRAM_CEILING_MIB"])
    tr = load_cache(out_dir, "train")
    n_train = len(tr["frame_index"])
    results: list[dict] = []
    policy = pre = post = cfg = inj = None
    for gc in [True, False]:
        try:
            policy, pre, post, cfg, inj = build_training_stack(
                args, device=args.device, dtype=args.precision, gradient_checkpointing=gc, reuse=reuse)
        except Exception as exc:                                          # noqa: BLE001
            import traceback
            findings.add(f"probe_build_failed:gc={gc}", verdict="RED", blocking=True,
                         subject="model_build", evidence={"error": f"{type(exc).__name__}: {exc}",
                                                           "traceback": traceback.format_exc()[-3000:]},
                         ruling="—", why="模型/处理器建不起来 ⇒ 第 1 步无法开跑")
            doc["build_error"] = f"{type(exc).__name__}: {exc}"
            break
        policy.train()
        opt = torch.optim.AdamW(policy.get_optim_params(), lr=float(hp["lr"]), betas=tuple(hp["betas"]),
                                eps=float(hp["eps"]), weight_decay=float(hp["weight_decay"]))
        for bs in cands_bs:
            idxs = [int(i) % n_train for i in range(bs)]
            rec: dict = {"gradient_checkpointing": bool(gc), "batch_size": int(bs), "dtype": args.precision,
                         "measurement_status": "not_measured"}
            try:
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                t1 = time.perf_counter()
                opt.zero_grad(set_to_none=True)
                batch = pre(make_batch(tr, idxs, image_size=args.image_size))
                loss, ld = policy(batch)
                loss.backward()
                gnorm = float(torch.nn.utils.clip_grad_norm_(policy.parameters(),
                                                             float(hp["grad_clip_norm"])).item())
                opt.step()
                torch.cuda.synchronize()
                wall = time.perf_counter() - t1
                rec.update({
                    "measurement_status": "measured", "ok": True,
                    "loss": float(ld.get("loss")), "loss_finite": bool(np.isfinite(float(ld.get("loss", np.nan)))),
                    "grad_norm_before_clip": gnorm,
                    "wall_s_per_step": round(wall, 3),
                    "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / (1 << 20), 1),
                    "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / (1 << 20), 1),
                    "n_parameters": inj["n_parameters"], "n_trainable_parameters": inj["n_trainable_parameters"],
                    "param_dtype_hist": inj["param_dtype_hist"],
                    "load_pair": {"before": PBG.gpu_window_readings(extra={"phase": f"probe_gc{int(gc)}_bs{bs}_before"}),
                                  "after": PBG.gpu_window_readings(extra={"phase": f"probe_gc{int(gc)}_bs{bs}_after"})},
                    "pairing_rule": "裁定 46.4/53.6/85.7：吞吐/显存数字成对带 loadavg(3 点)+nr_throttled",
                })
            except torch.cuda.OutOfMemoryError as exc:
                rec.update({"ok": False, "oom": True, "error": f"{type(exc).__name__}: {exc}",
                            "measurement_status": "measured",
                            "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / (1 << 20), 1)})
                torch.cuda.empty_cache()
            except Exception as exc:                                      # noqa: BLE001
                import traceback
                rec.update({"ok": False, "oom": False, "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc()[-2000:], "measurement_status": "measured"})
                torch.cuda.empty_cache()
            results.append(rec)
            print(f"[probe] gc={int(gc)} bs={bs} ok={rec.get('ok')} "
                  f"peak_reserved={rec.get('peak_reserved_mib')}MiB wall={rec.get('wall_s_per_step')}s "
                  f"loss={rec.get('loss')}", flush=True)
        del opt
        policy = policy.to("cpu")
        del policy, pre, post, cfg
        policy = pre = post = cfg = None
        torch.cuda.empty_cache()

    # ── 按**预登记的规则**定档（规则在 PRE_REGISTRATION 里，这里只执行）──
    ok = [r for r in results if r.get("ok") and r.get("peak_reserved_mib") is not None
          and float(r["peak_reserved_mib"]) <= ceiling and r.get("loss_finite") is not False]
    chosen: dict = {"measurement_status": "not_measured", "rule": hp["batch_selection_rule"],
                    "vram_ceiling_mib": ceiling, "n_candidates_measured": len(results),
                    "n_candidates_within_ceiling": len(ok)}
    if ok:
        max_bs = max(int(r["batch_size"]) for r in ok)
        same = [r for r in ok if int(r["batch_size"]) == max_bs]
        same.sort(key=lambda r: (bool(r["gradient_checkpointing"]), float(r["wall_s_per_step"])))
        pick = same[0]
        chosen.update({"measurement_status": "measured", "gradient_checkpointing": bool(pick["gradient_checkpointing"]),
                       "batch_size": int(pick["batch_size"]), "dtype": args.precision,
                       "peak_reserved_mib": pick["peak_reserved_mib"],
                       "wall_s_per_step": pick["wall_s_per_step"],
                       "estimated_train_wall_min": round(float(pick["wall_s_per_step"]) * int(args.train_steps) / 60.0, 1),
                       "selection_evidence": pick})
    else:
        findings.add("probe_no_candidate_within_ceiling", verdict="RED", blocking=True,
                     subject="vram_probe", evidence={"results": results, "ceiling_mib": ceiling},
                     ruling="补单四 §三（预算）+ 95.5", why="没有任何 (gc,bs) 组合落在显存上限内 ⇒ 停下报 D，不硬跑")
    doc["probe"] = {"results": results, "chosen": chosen, "injection_info": inj,
                    "n_train_samples": n_train, "train_cache_sha256_12": tr["sha256_12"]}
    doc["measurement_status"] = "measured"
    doc["load_pair"] = {"before": load_before, "after": PBG.gpu_window_readings(extra={"phase": "probe_after"})}
    doc["wall_s"] = round(time.perf_counter() - t0, 2)
    ident = write_json(out_dir / PROBE_NAME, doc)
    print(f"[probe] chosen={ {k: chosen.get(k) for k in ('gradient_checkpointing','batch_size','peak_reserved_mib','wall_s_per_step')} } "
          f"artifact={ident['path']} {ident['sha256_12']}", flush=True)
    return doc


# ══════════════════════════ ⑥ train（过拟合臂）══════════════════════════
def save_ckpt(out_dir: pathlib.Path, step: int, policy, pre, post) -> dict:
    ck = out_dir / "checkpoints" / f"step_{step:06d}"
    ck.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(ck)
    pre.save_pretrained(ck)
    post.save_pretrained(ck)
    st = ck / "model.safetensors"
    cfgj = load_json(ck / "config.json")
    prej = load_json(ck / "policy_preprocessor.json")
    nstats = 0
    for s in prej.get("steps") or []:
        if s.get("registry_name") == "normalizer_processor":
            nstats = len(((s.get("config") or {}).get("features") or {}))
    return {"step": int(step), "dir": str(ck), "rel_dir": str(ck.relative_to(REPO)),
            "model_safetensors_bytes": (st.stat().st_size if st.exists() else None),
            "model_safetensors_sha256_12": sha12(st) if st.exists() else None,
            "files": sorted(p.name for p in ck.iterdir()),
            "config_output_action_shape": (cfgj.get("output_features") or {}).get("action", {}).get("shape"),
            "config_input_state_shape": (cfgj.get("input_features") or {}).get("observation.state", {}).get("shape"),
            "config_dtype": cfgj.get("dtype"),
            "preprocessor_normalizer_n_features": nstats,
            "structural_selfproof": {
                "action_shape_must_be_14": (cfgj.get("output_features") or {}).get("action", {}).get("shape") == [STATE_DIM],
                "normalizer_features_must_be_nonempty": nstats > 0,
                "note": ("**结构**自证（形状 + 归一化器非空）；真正的**载回**自证发生在 rollout 阶段"
                         "（`zs.build_policy()` 从该目录 `from_pretrained` + `make_pre_post_processors`）"),
            }}


def prereg_consistency_tooth(prereg: dict, args, resolved: dict) -> dict:
    """**预登记一致性牙**：实跑用的超参必须落在 `PRE_REGISTRATION.json` 登记的（规则 ∨ 值）里。
    不一致 ⇒ RED（不是 warning）—— 预登记若事后可改，它就没有任何约束力（裁定 95.5-③）。"""
    hp = prereg["hyperparameters"]
    checks: list[dict] = []

    def chk(name, expected, actual, kind="value"):
        ok = (expected == actual)
        checks.append({"field": name, "kind": kind, "preregistered": expected, "actually_used": actual,
                       "consistent": bool(ok)})
        return ok

    bad = []
    if not chk("lr", float(hp["lr"]), float(args.lr)):
        bad.append("lr")
    if not chk("train_steps", int(hp["train_steps"]), int(args.train_steps)):
        bad.append("train_steps")
    if not chk("precision_primary", hp["precision_primary"], args.precision):
        bad.append("precision")
    if not chk("det_subset_size", int(prereg["det_subset_size"]), int(args.det_subset_size)):
        bad.append("det_subset_size")
    if not chk("det_rng_seed", int(prereg["det_rng_seed"]), DET_RNG_SEED):
        bad.append("det_rng_seed")
    if not chk("train_episodes", prereg["data_split"]["train_episodes"], TRAIN_EPISODES):
        bad.append("train_episodes")
    if not chk("val_episodes", prereg["data_split"]["val_episodes"], VAL_EPISODES):
        bad.append("val_episodes")
    if not chk("checkpoint_candidates_steps", prereg["checkpoint_candidates_steps"], resolved["ckpt_steps"]):
        bad.append("ckpt_steps")
    # 由**规则**解析出来的量：只核它落在预登记的候选集里
    if resolved.get("batch_size") is not None:
        cands = [int(x) for x in hp["batch_size_candidates"]]
        checks.append({"field": "batch_size", "kind": "rule_resolved",
                       "preregistered": {"candidates": cands, "rule": hp["batch_selection_rule"]},
                       "actually_used": int(resolved["batch_size"]),
                       "consistent": bool(int(resolved["batch_size"]) in cands)})
        if int(resolved["batch_size"]) not in cands:
            bad.append("batch_size")
    if resolved.get("gradient_checkpointing") is not None:
        cands = [bool(x) for x in hp["grad_checkpointing_candidates"]]
        checks.append({"field": "gradient_checkpointing", "kind": "rule_resolved",
                       "preregistered": {"candidates": cands, "rule": hp["batch_selection_rule"]},
                       "actually_used": bool(resolved["gradient_checkpointing"]),
                       "consistent": bool(bool(resolved["gradient_checkpointing"]) in cands)})
        if bool(resolved["gradient_checkpointing"]) not in cands:
            bad.append("gradient_checkpointing")
    return {"tooth_id": "A2T5_prereg_consistency", "checks": checks, "inconsistent_fields": bad,
            "verdict": "GREEN" if not bad else "RED", "bite": bool(bad),
            "measurement_status": "measured",
            "why_blocking": ("预登记事后被改 ⇒ 95.5-③ 的 checkpoint 选择规则/95.5-① 的划分都失去约束力；"
                             "这一颗牙让「改」在产物层过不去，而不是靠自觉")}


# ══════════════════ 出场判据牙 A2T6（裁定 102.2-①：闭环复现 = Step 1 的出场判据）══════════════
def _cl_train_rows(tables: dict, arm: str, split: str) -> list[dict]:
    per = ((tables.get(arm) or {}).get("per_seed")) or []
    return [r for r in per if str(r.get("split")) == str(split)]


def _cl_count(rows: list[dict], direction: str, field: str) -> int:
    return sum(1 for r in rows if str(r.get("direction")) == direction and r.get(field) is True)


def _cl_count_stage4(rows: list[dict], direction: str) -> int:
    """`max_stage == 4` 的交叉核对（裁定 102.2-①：`geometric_success==True` = A2 的 `max_stage==4`）。"""
    return sum(1 for r in rows
               if str(r.get("direction")) == direction and int(r.get("max_stage") or 0) == 4)


def closed_loop_reproduction_tooth(tables: dict, *, arms_run: list | None = None,
                                   gate: dict | None = None) -> dict:
    """**Step 1 的出场判据牙**（裁定 102.2-①，用户验收标准第 2 条逐字）。

    原文：**「至少一条正向和一条反向轨迹能从示范初态闭环复现」**。
    可核化：**`bc` 臂** ∧ **`split=='train'`** ∧ **正向 ≥1 集** ∧ **反向 ≥1 集** ∧
    C2 判定层的 **`geometric_success is True`**（= `max_stage == 4`，含 hold 反 flick）。

    **三条防混淆锁**（每条都有对应的负向变异体，见 `closed_loop_reproduction_selftest`）：
    ① 只读 `bc` 臂 ⇒ 「过的其实是 `injected_base`（接口修复而不是 BC 微调）」必须翻红；
    ② 正反向**分别**计数 ⇒ 只一向过必须翻红（用户固定条件「正向与反向分别记录」）；
    ③ 只认 `split=='train'` ⇒ 拿 val 集的成功顶替必须翻红（裁定 101.2 六类阻塞项之⑤：
       过拟合阶段允许用示范集本身，但**不得用评测集调参**）。

    判定层归 C2（`judge_from_facts`），**A2 不重算任何判定**：本牙只数 C2 已经写下的布尔值。
    """
    g = dict(GATES if gate is None else gate)
    arm = str(g["closed_loop_reproduction_arm"])
    field = str(g["closed_loop_reproduction_success_field"])
    split = str(g["closed_loop_reproduction_split"])
    fwd = str(g["closed_loop_reproduction_forward_direction"])
    rev = str(g["closed_loop_reproduction_reverse_direction"])
    min_fwd = int(g["closed_loop_reproduction_min_forward_train_episodes"])
    min_rev = int(g["closed_loop_reproduction_min_reverse_train_episodes"])
    arms_seen = list(arms_run if arms_run is not None else sorted(tables.keys()))

    red: list[str] = []
    bc_present = arm in tables
    rows = _cl_train_rows(tables, arm, split) if bc_present else []
    if not bc_present:
        red.append(f"{arm}_arm_absent")
    elif not rows:
        red.append(f"{arm}_no_{split}_rows")

    n_fwd = _cl_count(rows, fwd, field)
    n_rev = _cl_count(rows, rev, field)
    n_fwd_stage4 = _cl_count_stage4(rows, fwd)
    n_rev_stage4 = _cl_count_stage4(rows, rev)
    if bc_present and n_fwd < min_fwd:
        red.append(f"no_{fwd}_{split}_{field}")
    if bc_present and n_rev < min_rev:
        red.append(f"no_{rev}_{split}_{field}")

    passed = bool(bc_present and rows and n_fwd >= min_fwd and n_rev >= min_rev)
    # 其它臂的同口径计数：**只报不判**，用来让「过的其实是别的臂」这件事在产物里看得见
    other_arms = {}
    for a in arms_seen:
        if a == arm:
            continue
        ar = _cl_train_rows(tables, a, split)
        other_arms[a] = {"n_rows": len(ar),
                         f"n_{fwd}_{field}": _cl_count(ar, fwd, field),
                         f"n_{rev}_{field}": _cl_count(ar, rev, field),
                         "would_pass_if_it_were_bc": bool(
                             _cl_count(ar, fwd, field) >= min_fwd and _cl_count(ar, rev, field) >= min_rev)}
    return {
        "tooth_id": str(g["closed_loop_reproduction_tooth_id"]),
        "ruling": "裁定 102.2-①（用户 Step 1 验收标准第 2 条 = **出场判据**）· 裁定 101.2（逐字采纳）",
        "criterion_verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM[1],
        "nuclearization": g["closed_loop_reproduction_why"],
        "arm_judged": arm, "field_judged": field, "split_judged": split,
        "directions": {"forward": fwd, "reverse": rev},
        "min_required": {"forward": min_fwd, "reverse": min_rev},
        "arms_seen": arms_seen,
        "measurement_status": "measured" if (bc_present and rows) else "not_measured",
        "n_bc_train_rows": len(rows),
        "n_forward_geometric_success": n_fwd,
        "n_reverse_geometric_success": n_rev,
        "n_forward_max_stage_4": n_fwd_stage4,
        "n_reverse_max_stage_4": n_rev_stage4,
        "geometric_success_equals_max_stage_4": (
            None if not rows else bool(n_fwd == n_fwd_stage4 and n_rev == n_rev_stage4)),
        "forward_episodes_passed": [int(r["episode_index"]) for r in rows
                                    if str(r.get("direction")) == fwd and r.get(field) is True],
        "reverse_episodes_passed": [int(r["episode_index"]) for r in rows
                                    if str(r.get("direction")) == rev and r.get(field) is True],
        "other_arms_same_caliber_report_only": other_arms,
        "other_arms_note": ("**只报不判**：这几臂的同口径计数落盘，是为了让「过的其实是 `injected_base`」"
                            "这种混淆在产物层**看得见**；判词只由 `bc` 臂产生"),
        "red_codes": red,
        "pass": (None if not (bc_present and rows) else passed),
        "verdict": "GREEN" if passed else "RED",
        "bite": bool(red),
        "capability_claim": False,
        "capability_note": ("**GREEN ≠ 能力声明**（裁定 46/101.3）：它只回答「离线拟合能否转成在线控制」"
                            "这一条闸门，且作用域是 `AlohaTransferCube-v0` 的左右臂交接（冒烟基准）"),
        "why_blocking": ("这是 Step 1 的**出场判据**（裁定 102.2-①）⇒ 不过 ⇒ Step 1 = RED，"
                         "且按用户原文「如果这一步失败，继续加 RL、LLM 或 Harness 都没有意义」"),
        "three_valued_discipline": ("`bc` 臂缺席或该 split 无行 ⇒ `measurement_status='not_measured'` + "
                                    "`pass=null` + 非零退出，**不许写 `false`/`0` 顶替**（裁定 88.3-1）"),
    }


def _cl_fixture(rows_by_arm: dict) -> dict:
    """构造**合成**的 `per_arm_tables` 夹具：牙只读 `per_seed` 那一层，别的键一概不碰。"""
    out = {}
    for arm, rows in rows_by_arm.items():
        out[arm] = {"n_episodes": len(rows), "by_direction": {}, "per_seed": rows}
    return out


def _cl_row(ep: int, direction: str, split: str, geom: bool, max_stage: int | None = None) -> dict:
    return {"episode_index": ep, "seed": 2000 + ep, "direction": direction, "split": split,
            "geometric_success": geom,
            "max_stage": (4 if geom else (max_stage if max_stage is not None else 2)),
            "task_success": geom}


def closed_loop_reproduction_selftest() -> dict:
    """**A2T6 的两向变异体自证**（裁定 93.8：只装一向不许报绿；裁定 99.3：先干跑再上卡）。

    正向 = `bc` 有 ≥1 正向 **且** ≥1 反向 `geometric_success` ⇒ 必须 GREEN；
    负向 = 只正向过 / 只反向过 / 过的其实是 `injected_base` / `bc` 臂缺席 / 拿 val 集顶替 ⇒ **必须翻红**。
    不翻 ⇒ 牙没有分辨力 ⇒ `all_bite=false` ⇒ 阻塞红。
    """
    F = GATES["closed_loop_reproduction_forward_direction"]
    R = GATES["closed_loop_reproduction_reverse_direction"]
    cases = [
        {"case": "M0_positive_bc_both_dirs", "polarity": "positive", "expect_verdict": "GREEN",
         "expect_measurement_status": "measured",
         "tables": _cl_fixture({
             "bc": [_cl_row(0, F, "train", True), _cl_row(1, F, "train", False, 1),
                    _cl_row(20, R, "train", True), _cl_row(21, R, "train", False, 3)],
             "injected_base": [_cl_row(0, F, "train", False, 0), _cl_row(20, R, "train", False, 0)],
             "random": [_cl_row(0, F, "train", False, 0)], "hold": [_cl_row(0, F, "train", False, 0)]}),
         "what": "正例：bc 在正向 ep0 与反向 ep20 各复现一条 ⇒ 出场判据成立"},
        {"case": "M1_negative_forward_only", "polarity": "negative", "expect_verdict": "RED",
         "expect_measurement_status": "measured",
         "tables": _cl_fixture({
             "bc": [_cl_row(0, F, "train", True), _cl_row(20, R, "train", False, 2),
                    _cl_row(21, R, "train", False, 1)]}),
         "what": "负例：只正向过 ⇒ 必须翻红（用户固定条件「正向与反向分别记录」）"},
        {"case": "M2_negative_reverse_only", "polarity": "negative", "expect_verdict": "RED",
         "expect_measurement_status": "measured",
         "tables": _cl_fixture({
             "bc": [_cl_row(0, F, "train", False, 2), _cl_row(1, F, "train", False, 1),
                    _cl_row(20, R, "train", True)]}),
         "what": "负例：只反向过 ⇒ 必须翻红"},
        {"case": "M3_negative_passes_belong_to_injected_base", "polarity": "negative",
         "expect_verdict": "RED", "expect_measurement_status": "measured",
         "tables": _cl_fixture({
             "bc": [_cl_row(0, F, "train", False, 2), _cl_row(20, R, "train", False, 1)],
             "injected_base": [_cl_row(0, F, "train", True), _cl_row(20, R, "train", True)]}),
         "what": ("负例：**过的其实是 `injected_base`**（= 接口修复：stats 注入 + shape 32→14，"
                  "权重一字节未动）而不是 `bc` ⇒ 必须翻红（裁定 102.2-③ 的归因要求）")},
        {"case": "M4_negative_bc_arm_absent", "polarity": "negative", "expect_verdict": "RED",
         "expect_measurement_status": "not_measured",
         "tables": _cl_fixture({
             "injected_base": [_cl_row(0, F, "train", True), _cl_row(20, R, "train", True)]}),
         "what": "负例：`bc` 臂根本没跑 ⇒ 必须 `not_measured` + 红（三值纪律，不许写 0/false 顶替）"},
        {"case": "M5_negative_only_val_split_passes", "polarity": "negative", "expect_verdict": "RED",
         "expect_measurement_status": "measured",
         "tables": _cl_fixture({
             "bc": [_cl_row(0, F, "train", False, 2), _cl_row(20, R, "train", False, 1),
                    _cl_row(2, F, "val", True), _cl_row(22, R, "val", True)]}),
         "what": "负例：只有 **val** 集复现、train 集没有 ⇒ 必须翻红（不得用评测集调参）"},
        {"case": "M6_negative_geometric_success_is_none_not_false", "polarity": "negative",
         "expect_verdict": "RED", "expect_measurement_status": "measured",
         "tables": _cl_fixture({
             "bc": [{"episode_index": 0, "seed": 2000, "direction": F, "split": "train",
                     "geometric_success": None, "max_stage": None, "task_success": None},
                    {"episode_index": 20, "seed": 2020, "direction": R, "split": "train",
                     "geometric_success": None, "max_stage": None, "task_success": None}]}),
         "what": ("负例：C2 的判定是 `null`（没测到）⇒ **不许**当 `False` 也不许当 `True`，"
                  "必须红（falsy-None 与 falsy-False 分开处置）")},
    ]
    rows = []
    for c in cases:
        got = closed_loop_reproduction_tooth(c["tables"], arms_run=sorted(c["tables"].keys()))
        ok_v = got["verdict"] == c["expect_verdict"]
        ok_m = got["measurement_status"] == c["expect_measurement_status"]
        # 「咬」= 该红的红了、该绿的绿了，**且** `pass` 与 `verdict` 自洽
        consistent = (got["pass"] is True) if got["verdict"] == "GREEN" else (got["pass"] is not True)
        rows.append({"case": c["case"], "polarity": c["polarity"], "what": c["what"],
                     "expect": c["expect_verdict"], "got": got["verdict"],
                     "expect_measurement_status": c["expect_measurement_status"],
                     "got_measurement_status": got["measurement_status"],
                     "got_pass": got["pass"], "red_codes": got["red_codes"],
                     "n_forward": got["n_forward_geometric_success"],
                     "n_reverse": got["n_reverse_geometric_success"],
                     "verdict_matches": ok_v, "status_matches": ok_m,
                     "pass_verdict_self_consistent": bool(consistent),
                     "bite": bool(ok_v and ok_m and consistent)})
    n_bite = sum(1 for r in rows if r["bite"])
    return {
        "tooth_id": GATES["closed_loop_reproduction_selftest_id"],
        "target_tooth_id": GATES["closed_loop_reproduction_tooth_id"],
        "ruling": ("裁定 93.8（审计器须自证；只装一向不许报绿）· 裁定 99.3"
                   "（`preregistered_criterion_must_be_dry_run_on_the_object` ⇒ 新牙**先干跑再上卡**）· "
                   "补单七 §三（新牙带两向变异体自证）"),
        "n_rows": len(rows), "n_bite": n_bite, "all_bite": bool(n_bite == len(rows)),
        "two_way": {"positive_mutants": [r["case"] for r in rows if r["polarity"] == "positive"],
                    "negative_mutants": [r["case"] for r in rows if r["polarity"] == "negative"],
                    "n_positive": sum(1 for r in rows if r["polarity"] == "positive"),
                    "n_negative": sum(1 for r in rows if r["polarity"] == "negative")},
        "not_a_dry_run_on_real_data": ("这一层**全部是合成夹具**（`_cl_fixture`）⇒ 干跑不消费任何真 rollout 读数，"
                                       "也就不可能被真读数污染；真读数的判词在 `stage_rollout` 里另出一遍"),
        "rows": rows,
    }


def action_match_analysis(policy, pre, post, arrs: dict, idxs, *, stats: dict, image_size: int,
                          bs: int, fps: float, tag: str) -> dict:
    """「**动作逐维对得上示范**（含夹爪开合时刻）」的可核化。

    全部在**物理单位**里比（模型输出经 `post`（unnormalizer）反归一化后就是物理量，与数据集同量纲）。
    逐维报 MAE / RMSE / Pearson ρ，并按 `BLIND_DIMS` 分成「8 个非盲点维（设闸）」与
    「6 个盲点维（**只报不判**，裁定 94.3/95.5-④）」两组 —— 不许把两组混成「全 14 维」的结论。
    """
    import torch
    q01 = np.asarray(stats["q01"], dtype=np.float64)
    q99 = np.asarray(stats["q99"], dtype=np.float64)
    span = np.where((q99 - q01) == 0, np.nan, (q99 - q01))
    was_training = bool(policy.training)
    policy.eval()
    preds: list[np.ndarray] = []
    demos: list[np.ndarray] = []
    t0 = time.perf_counter()
    with torch.no_grad():
        for s in range(0, len(idxs), bs):
            sel = idxs[s:s + bs]
            batch = pre(make_batch(arrs, sel, image_size=image_size))
            raw = policy.predict_action_chunk(batch)
            raw = post(raw)
            c = np.asarray(raw.detach().to("cpu").numpy(), dtype=np.float64)
            if c.ndim != 3 or c.shape[0] != len(sel):
                raise RuntimeError(f"predict_action_chunk 输出形状 {c.shape} 与批 {(len(sel), 'H', STATE_DIM)} "
                                   "不符 ⇒ 停下（不许静默 squeeze，那正是 S4B 单样本臂才需要的操作）")
            preds.append(c)
            demos.append(np.asarray(arrs["action"][np.asarray(sel)], dtype=np.float64))
    if was_training:
        policy.train()
    P = np.concatenate(preds, axis=0)          # (N,H,14)
    D = np.concatenate(demos, axis=0)
    if P.shape != D.shape:
        return {"measurement_status": "not_measured", "verdict": "RED", "tag": tag,
                "error": f"预测 {P.shape} 与示范 {D.shape} 形状不一致 ⇒ 无法逐维比",
                "nonzero_exit_required": True}
    N, H = P.shape[0], P.shape[1]
    ae = np.abs(P - D)
    mae = ae.mean(axis=(0, 1))
    rmse = np.sqrt((ae ** 2).mean(axis=(0, 1)))
    mae_rel = mae / span
    corr = np.full((STATE_DIM,), np.nan)
    for d in range(STATE_DIM):
        p_, d_ = P[:, :, d].reshape(-1), D[:, :, d].reshape(-1)
        if p_.std() > 1e-12 and d_.std() > 1e-12:
            corr[d] = float(np.corrcoef(p_, d_)[0, 1])
    # ── 夹爪开合时刻（判据原文点名）──
    def first_events(seq: np.ndarray) -> dict:
        """`seq` = (H,) 夹爪动作。返回 {'close': 第一次跨到 <0.5 的帧, 'open': 那之后第一次跨回 ≥0.5 的帧}。"""
        out: dict = {"close": None, "open": None}
        above = seq >= 0.5
        for t in range(1, len(seq)):
            if above[t - 1] and not above[t]:
                out["close"] = t
                for u in range(t + 1, len(seq)):
                    if above[u]:
                        out["open"] = u
                        break
                break
        return out

    grip_rows: list[dict] = []
    for g in GRIP_DIMS:
        errs_close: list[int] = []
        errs_open: list[int] = []
        n_demo_no_event = 0
        n_pred_miss = 0
        for i in range(N):
            de = first_events(D[i, :, g])
            pe = first_events(P[i, :, g])
            if de["close"] is None:
                n_demo_no_event += 1
                continue
            if pe["close"] is None:
                n_pred_miss += 1
                continue
            errs_close.append(abs(int(pe["close"]) - int(de["close"])))
            if de["open"] is not None and pe["open"] is not None:
                errs_open.append(abs(int(pe["open"]) - int(de["open"])))
        grip_rows.append({
            "dim": g, "dim_name": ("left_gripper_normalized" if g == 6 else "right_gripper_normalized"),
            "semantics": GRIPPER_SEMANTICS,
            "n_samples": N, "n_demo_without_close_event": n_demo_no_event,
            "n_pred_missed_close_event": n_pred_miss,
            "close_event_frame_err": {"n": len(errs_close),
                                      "median": (float(np.median(errs_close)) if errs_close else None),
                                      "mean": (round(float(np.mean(errs_close)), 3) if errs_close else None),
                                      "max": (int(max(errs_close)) if errs_close else None),
                                      "all": [int(x) for x in errs_close]},
            "open_event_frame_err": {"n": len(errs_open),
                                     "median": (float(np.median(errs_open)) if errs_open else None),
                                     "mean": (round(float(np.mean(errs_open)), 3) if errs_open else None),
                                     "max": (int(max(errs_open)) if errs_open else None)},
            "frame_to_s": (None if not errs_close else
                           round(float(np.median(errs_close)) / fps, 4)),
            "measurement_status": "measured" if errs_close else "not_measured",
        })
    per_dim = []
    for d in range(STATE_DIM):
        per_dim.append({
            "dim": d, "blind_dim": d in BLIND_DIMS,
            "gated": d not in BLIND_DIMS,
            "mae_physical": round(float(mae[d]), 6),
            "rmse_physical": round(float(rmse[d]), 6),
            "mae_over_range_q99_minus_q01": (None if not np.isfinite(mae_rel[d]) else round(float(mae_rel[d]), 6)),
            "pearson_rho": (None if not np.isfinite(corr[d]) else round(float(corr[d]), 6)),
            "demo_absmedian": round(float(np.median(np.abs(D[:, :, d]))), 6),
            "pred_absmedian": round(float(np.median(np.abs(P[:, :, d]))), 6),
            "q01": round(float(q01[d]), 6), "q99": round(float(q99[d]), 6),
        })
    gated = [r for r in per_dim if r["gated"]]
    blind = [r for r in per_dim if r["blind_dim"]]

    def _gate(rows, key, thr, cmp):
        vals = [r[key] for r in rows if r[key] is not None]
        if not vals:
            return None, "not_measured"
        return bool(all(cmp(v, thr) for v in vals)), "measured"

    g_mae, s_mae = _gate(gated, "mae_over_range_q99_minus_q01", GATES["per_dim_mae_rel_max_observed_dims"],
                         lambda v, t: v <= t)
    g_rho, s_rho = _gate(gated, "pearson_rho", GATES["per_dim_corr_min_observed_dims"], lambda v, t: v >= t)
    grip_med = [r["close_event_frame_err"]["median"] for r in grip_rows
                if r["close_event_frame_err"]["median"] is not None]
    g_grip = (None if not grip_med else
              bool(max(grip_med) <= GATES["gripper_transition_frames_max"]))
    red = []
    if g_mae is not True:
        red.append("per_dim_mae_rel_over_threshold_on_observed_dims")
    if g_rho is not True:
        red.append("per_dim_corr_below_threshold_on_observed_dims")
    if g_grip is not True:
        red.append("gripper_transition_timing_over_threshold")
    return {
        "tag": tag, "measurement_status": "measured",
        "n_samples": int(N), "chunk_size": int(H), "units": "physical（`post` 反归一化之后，与数据集同量纲）",
        "fps": fps, "wall_s": round(time.perf_counter() - t0, 2),
        "per_dim": per_dim,
        "per_dim_split": {"observed_dims_gated": [r["dim"] for r in gated],
                          "blind_dims_report_only": [r["dim"] for r in blind],
                          "blind_dim_caveat": BLIND_DIM_CAVEAT},
        "summary_observed_dims": {
            "mae_rel_max": max([r["mae_over_range_q99_minus_q01"] for r in gated
                                if r["mae_over_range_q99_minus_q01"] is not None] or [None])
            if any(r["mae_over_range_q99_minus_q01"] is not None for r in gated) else None,
            "rho_min": min([r["pearson_rho"] for r in gated if r["pearson_rho"] is not None] or [None])
            if any(r["pearson_rho"] is not None for r in gated) else None,
            "gate_mae_rel": {"threshold": GATES["per_dim_mae_rel_max_observed_dims"], "pass": g_mae,
                             "measurement_status": s_mae, "why": GATES["per_dim_mae_rel_max_observed_dims_why"]},
            "gate_rho": {"threshold": GATES["per_dim_corr_min_observed_dims"], "pass": g_rho,
                         "measurement_status": s_rho},
        },
        "summary_blind_dims_report_only": {
            "mae_rel": {r["dim"]: r["mae_over_range_q99_minus_q01"] for r in blind},
            "rho": {r["dim"]: r["pearson_rho"] for r in blind},
            "not_a_gate": True, "ruling": "裁定 94.3 / 95.5-④：盲点维**只登记**，不当能力判据、不当闸",
        },
        "gripper_timing": {"rows": grip_rows,
                           "gate": {"threshold_frames": GATES["gripper_transition_frames_max"],
                                    "pass": g_grip, "measurement_status": ("measured" if grip_med else "not_measured"),
                                    "close_event_median_frames_per_dim": grip_med,
                                    "why": GATES["gripper_transition_frames_max_why"]}},
        "gates_all_pass": (None if (g_mae is None or g_rho is None or g_grip is None)
                           else bool(g_mae and g_rho and g_grip)),
        "red_codes": red,
    }


# ══════════ 平台期规则（裁定 102.2-②(b)：**不得在确定性训练损失仍在下降时提前停**）══════════
def plateau_blocks_from_curve(curve: list, block_steps: int) -> list:
    """把 `train_det_loss`（确定性口径）按 `block_steps` 分块求均值。

    **只用 curve 里已经落盘的读数，不新算一次前向** ⇒ 块表可被独立复核。
    非有限的点不进块（三值纪律：不把 NaN 当 0）。
    """
    blk: dict = {}
    for r in curve:
        s = int(r.get("step") or 0)
        if s <= 0 or not r.get("train_det_finite") or r.get("train_det_loss") is None:
            continue
        b = (s - 1) // int(block_steps) + 1
        blk.setdefault(b, []).append((s, float(r["train_det_loss"])))
    out = []
    for b, pts in sorted(blk.items()):
        vals = [v for _, v in pts]
        out.append({"block": int(b),
                    "step_range": [int((b - 1) * block_steps) + 1, int(b * block_steps)],
                    "steps_sampled": [int(s) for s, _ in pts],
                    "n_points": len(pts),
                    "mean_train_det_loss": float(np.mean(vals)),
                    "last_train_det_loss": float(vals[-1])})
    return out


def plateau_decision(curve: list, *, block_steps: int, min_drop_frac: float, elapsed_s: float,
                     wall_budget_s: float, target_steps: int, hard_cap_steps: int,
                     extend_enabled: bool) -> dict:
    """**规则先写死、不看结果**（裁定 102.2-②(b) 逐字）：每 `block_steps` 一块，
    块间降幅 > `min_drop_frac` **且** 窗口预算未耗尽 ⇒ 继续；否则停。

    三值纪律：块数 <2 ⇒ `plateau_reached=null` + `stopped_by='insufficient_blocks…'`（**不写 false 顶替**）。
    `plateau_reached=false` **只**用于「还在降但被预算/硬上限截断」⇒ 这两种停因必须在产物里分得开。
    """
    blocks = plateau_blocks_from_curve(curve, block_steps)
    base = {"block_steps": int(block_steps), "min_block_drop_frac": float(min_drop_frac),
            "elapsed_s": round(float(elapsed_s), 3), "wall_budget_s": float(wall_budget_s),
            "target_steps": int(target_steps), "hard_cap_steps": int(hard_cap_steps),
            "extend_enabled": bool(extend_enabled), "blocks": blocks,
            "rule": PLATEAU_RULE["continue_iff"], "stop_when": PLATEAU_RULE["stop_when"]}
    if len(blocks) < 2:
        base.update({"measurement_status": "not_measured", "block_drop_frac": None,
                     "still_descending": None, "budget_remaining": bool(elapsed_s < wall_budget_s),
                     "cap_remaining": bool(target_steps + block_steps <= hard_cap_steps),
                     "extend": False, "new_target_steps": int(target_steps),
                     "plateau_reached": None,
                     "stopped_by": "insufficient_blocks_for_plateau_rule",
                     "why": (f"只有 {len(blocks)} 个完整块 ⇒ 块间降幅无法计算 ⇒ **不许**把「算不出」写成"
                             "「到平台期」或「还在降」（三值纪律）")})
        return base
    prev, last = blocks[-2]["mean_train_det_loss"], blocks[-1]["mean_train_det_loss"]
    drop = (None if not prev else (prev - last) / prev)
    still = (None if drop is None else bool(drop > min_drop_frac))
    budget_left = bool(elapsed_s < wall_budget_s)
    cap_left = bool(target_steps + block_steps <= hard_cap_steps)
    extend = bool(extend_enabled and still and budget_left and cap_left)
    if extend:
        stopped_by, plateau = "still_descending_continue", None
    elif not extend_enabled:
        stopped_by, plateau = "extension_disabled", None
    elif still is not True and drop is not None:
        stopped_by, plateau = "plateau", True
    elif not budget_left:
        stopped_by, plateau = "wall_budget_exhausted", False
    elif not cap_left:
        stopped_by, plateau = "hard_cap_steps_reached", False
    else:
        stopped_by, plateau = "not_extended_reason_unresolved", None
    base.update({"measurement_status": "measured",
                 "prev_block_mean": (None if prev is None else round(float(prev), 9)),
                 "last_block_mean": (None if last is None else round(float(last), 9)),
                 "block_drop_frac": (None if drop is None else round(float(drop), 9)),
                 "still_descending": still, "budget_remaining": budget_left, "cap_remaining": cap_left,
                 "extend": extend,
                 "new_target_steps": int(target_steps + block_steps) if extend else int(target_steps),
                 "plateau_reached": plateau, "stopped_by": stopped_by,
                 "nearzero_gap": OPEN_STEP1_NEARZERO_GAP,
                 "a2_self_binding": OPEN_STEP1_NEARZERO_GAP["a2_self_binding"]})
    return base


def plateau_rule_selftest() -> dict:
    """`plateau_decision` 的两向自证（裁定 93.8）：**纯函数、零 GPU、可在上卡前干跑**（裁定 99.3）。"""
    def cv(pairs):
        return [{"step": s, "train_det_loss": v, "train_det_finite": bool(np.isfinite(v))} for s, v in pairs]

    kw = dict(block_steps=100, min_drop_frac=0.01, elapsed_s=100.0, wall_budget_s=3600.0,
              target_steps=200, hard_cap_steps=4000, extend_enabled=True)
    cases = [
        {"case": "P0_still_descending_must_extend", "expect_extend": True, "expect_plateau": None,
         "curve": cv([(100, 1.0), (200, 0.8)]), "kw": dict(kw),
         "what": "块间降 20% > 1% 且预算未耗尽 ⇒ **必须继续**（裁定 102.2-②(b)）"},
        {"case": "P1_plateau_must_stop", "expect_extend": False, "expect_plateau": True,
         "curve": cv([(100, 1.0), (200, 0.995)]), "kw": dict(kw),
         "what": "块间降 0.5% ≤ 1% ⇒ `plateau_reached=true` 停"},
        {"case": "P2_budget_exhausted_not_plateau", "expect_extend": False, "expect_plateau": False,
         "curve": cv([(100, 1.0), (200, 0.5)]), "kw": dict(kw, elapsed_s=3700.0),
         "what": "还在降但墙钟预算耗尽 ⇒ `plateau_reached=false` + `stopped_by=wall_budget_exhausted`"
                 "（**不许**把预算耗尽写成平台期）"},
        {"case": "P3_hard_cap_not_plateau", "expect_extend": False, "expect_plateau": False,
         "curve": cv([(100, 1.0), (200, 0.5)]), "kw": dict(kw, hard_cap_steps=250),
         "what": "还在降但触硬上限 ⇒ `plateau_reached=false` + `stopped_by=hard_cap_steps_reached`"},
        {"case": "P4_insufficient_blocks_three_valued", "expect_extend": False, "expect_plateau": None,
         "curve": cv([(100, 1.0)]), "kw": dict(kw),
         "what": "只有 1 块 ⇒ `plateau_reached=null` + `not_measured`（**不写 false 顶替**）"},
        {"case": "P5_nonfinite_points_excluded", "expect_extend": False, "expect_plateau": None,
         "curve": cv([(100, 1.0), (200, float("nan"))]), "kw": dict(kw),
         "what": "非有限损失不进块 ⇒ 只剩 1 块 ⇒ `not_measured`（NaN 不当 0）"},
        {"case": "P6_extension_disabled", "expect_extend": False, "expect_plateau": None,
         "curve": cv([(100, 1.0), (200, 0.5)]), "kw": dict(kw, extend_enabled=False),
         "what": "显式关掉扩展（只用于调试）⇒ `stopped_by=extension_disabled` 照实落盘"},
    ]
    rows = []
    for c in cases:
        got = plateau_decision(c["curve"], **c["kw"])
        ok = bool(got["extend"] == c["expect_extend"] and got["plateau_reached"] == c["expect_plateau"])
        rows.append({"case": c["case"], "what": c["what"], "expect_extend": c["expect_extend"],
                     "got_extend": got["extend"], "expect_plateau_reached": c["expect_plateau"],
                     "got_plateau_reached": got["plateau_reached"], "got_stopped_by": got["stopped_by"],
                     "got_measurement_status": got["measurement_status"],
                     "got_block_drop_frac": got.get("block_drop_frac"), "bite": ok})
    n_bite = sum(1 for r in rows if r["bite"])
    return {"tooth_id": "A2T7_plateau_rule_two_way", "target": "plateau_decision",
            "ruling": "裁定 102.2-②(b) · 裁定 93.8（只装一向不许报绿）· 裁定 99.3（先干跑再上卡）",
            "n_rows": len(rows), "n_bite": n_bite, "all_bite": bool(n_bite == len(rows)), "rows": rows}


def stage_train(args, out_dir: pathlib.Path, findings, reuse: dict, window) -> dict:
    import torch
    doc = base_doc("bc_step1_train_report", args, gpu_used=True)
    t0 = time.perf_counter()
    load_before = PBG.gpu_window_readings(extra={"phase": "train_before"})
    prereg = load_json(prereg_path(out_dir))
    probe = load_json(out_dir / PROBE_NAME)
    chosen = probe["probe"]["chosen"]
    if chosen.get("measurement_status") != "measured":
        findings.add("probe_chosen_not_measured", verdict="RED", blocking=True, subject="probe",
                     evidence=chosen, ruling="补单四 §三", why="probe 没定出档位 ⇒ 不许凭感觉开训")
        doc["measurement_status"] = "not_measured"
        write_json(out_dir / "TRAIN_REPORT.json", doc)
        return doc
    resolved = {"batch_size": int(chosen["batch_size"]),
                "gradient_checkpointing": bool(chosen["gradient_checkpointing"]),
                "ckpt_steps": resolve_ckpt_steps(args)}
    tooth = prereg_consistency_tooth(prereg, args, resolved)
    doc["prereg_consistency"] = tooth
    if tooth["verdict"] != "GREEN":
        findings.add("prereg_inconsistent", verdict="RED", blocking=True, subject="pre_registration",
                     evidence=tooth, ruling="裁定 95.5-③", why=tooth["why_blocking"])
        doc["measurement_status"] = "measured"
        write_json(out_dir / "TRAIN_REPORT.json", doc)
        return doc

    bs = resolved["batch_size"]
    gc = resolved["gradient_checkpointing"]
    tr = load_cache(out_dir, "train")
    va = load_cache(out_dir, "val")
    n_train = len(tr["frame_index"])
    n_val = len(va["frame_index"])
    policy, pre, post, cfg, inj = build_training_stack(
        args, device=args.device, dtype=args.precision, gradient_checkpointing=gc, reuse=reuse)
    H = int(cfg.chunk_size)
    mad = int(cfg.max_action_dim)
    policy.train()
    hp = prereg["hyperparameters"]
    opt = torch.optim.AdamW(policy.get_optim_params(), lr=float(hp["lr"]), betas=tuple(hp["betas"]),
                            eps=float(hp["eps"]), weight_decay=float(hp["weight_decay"]))
    # ── 确定性子集 + 固定 (noise,time) 银行（抽一次、全程复用）──
    rng_det = np.random.default_rng(DET_RNG_SEED)
    k_tr = min(int(args.det_subset_size), n_train)
    k_va = min(int(args.det_subset_size), n_val)
    det_tr = np.sort(rng_det.choice(n_train, size=k_tr, replace=False)).astype(np.int64).tolist()
    det_va = np.sort(rng_det.choice(n_val, size=k_va, replace=False)).astype(np.int64).tolist()
    noise_tr, time_tr = build_det_bank(tr, det_tr, chunk_size=H, max_action_dim=mad, seed=DET_RNG_SEED)
    noise_va, time_va = build_det_bank(va, det_va, chunk_size=H, max_action_dim=mad, seed=DET_RNG_SEED + 1)
    fps = float(load_json(out_dir / "CACHE_MANIFEST.json")["cache"]["fps"])

    curve: list[dict] = []
    ckpts: list[dict] = []

    def snap(step: int, extra: dict | None = None) -> dict:
        d_tr = det_loss(policy, pre, tr, det_tr, noise_tr, time_tr, action_dim=STATE_DIM,
                        image_size=args.image_size, bs=bs)
        d_va = det_loss(policy, pre, va, det_va, noise_va, time_va, action_dim=STATE_DIM,
                        image_size=args.image_size, bs=bs)
        rec = {"step": int(step), "train_det_loss": d_tr["loss"], "val_det_loss": d_va["loss"],
               "train_det_per_dim": d_tr["per_dim"], "val_det_per_dim": d_va["per_dim"],
               "train_det_finite": d_tr["finite"], "val_det_finite": d_va["finite"],
               "det_wall_s": round(d_tr["wall_s"] + d_va["wall_s"], 2),
               "det_subset": {"train_n": k_tr, "val_n": k_va, "rng_seed": DET_RNG_SEED},
               "loadavg_three_points": PBG.gpu_window_readings(extra={"phase": f"det_eval@{step}"})}
        if extra:
            rec.update(extra)
        curve.append(rec)
        return rec

    s0 = snap(0, {"note": "step0 = **未微调**、只带 stats 注入的起点（= rollout 的 `injected_base` 臂）"})
    if 0 in resolved["ckpt_steps"]:
        c0 = save_ckpt(out_dir, 0, policy, pre, post)
        c0["role"] = "injected_base（未微调起点；rollout 的 A1 臂直接从这个目录载）"
        ckpts.append(c0)
        print(f"[train] ckpt step0 已存 {c0['dir']} {c0['model_safetensors_sha256_12']}", flush=True)
    print(f"[train] step0 train_det_loss={s0['train_det_loss']:.6f} val_det_loss={s0['val_det_loss']:.6f}",
          flush=True)

    rng = np.random.default_rng(int(args.train_seed))
    planned_steps = int(args.train_steps)
    # ── 裁定 102.2-②(b)：**不得在确定性训练损失仍在下降时提前停**（规则先写死、不看结果）──
    block_steps = int(args.plateau_block_steps)
    ckpt_steps_live = set(int(x) for x in resolved["ckpt_steps"])
    ckpt_steps_extended: list[int] = []
    target_steps = planned_steps
    extension_log: list[dict] = []
    plateau_reached = None
    stopped_by = "planned_steps_no_extension_evaluated_yet"
    last_decision: dict = {}
    running: list[float] = []
    nonfinite = 0
    train_wall = 0.0
    t_train0 = time.perf_counter()
    step = 0
    while step < target_steps:
        step += 1
        idxs = rng.integers(0, n_train, size=bs).tolist()
        ts = time.perf_counter()
        opt.zero_grad(set_to_none=True)
        batch = pre(make_batch(tr, idxs, image_size=args.image_size))
        loss, ld = policy(batch)
        loss.backward()
        gnorm = float(torch.nn.utils.clip_grad_norm_(policy.parameters(), float(hp["grad_clip_norm"])).item())
        opt.step()
        torch.cuda.synchronize()
        w = time.perf_counter() - ts
        train_wall += w
        lv = float(ld.get("loss"))
        running.append(lv)
        if not np.isfinite(lv):
            nonfinite += 1
        if step % int(args.log_every) == 0 or step == target_steps:
            win = running[-int(args.log_every):]
            print(f"[train] step {step}/{target_steps} loss={np.mean(win):.6f} (last{len(win)}) gnorm={gnorm:.4f} "
                  f"{round(w, 3)}s/step peak_reserved={round(torch.cuda.max_memory_reserved() / (1 << 20), 1)}MiB",
                  flush=True)
        if step % int(args.eval_every) == 0 or step in ckpt_steps_live:
            snap(step)
        if step in ckpt_steps_live:
            c = save_ckpt(out_dir, step, policy, pre, post)
            ckpts.append(c)
            print(f"[train] ckpt step{step} 已存 {c['model_safetensors_sha256_12']}", flush=True)
        # ---- 到当前 target ⇒ 按**预登记的规则**决定「继续 or 停」（唯一决定点）----
        if step == target_steps:
            last_decision = plateau_decision(
                curve, block_steps=block_steps, min_drop_frac=float(args.plateau_min_block_drop_frac),
                elapsed_s=(time.perf_counter() - t_train0), wall_budget_s=float(args.train_wall_budget_s),
                target_steps=target_steps, hard_cap_steps=max(int(args.train_steps_max), planned_steps),
                extend_enabled=bool(args.plateau_extend))
            stopped_by = str(last_decision.get("stopped_by"))
            plateau_reached = last_decision.get("plateau_reached")
            extension_log.append(dict(last_decision, at_step=int(step)))
            if last_decision.get("extend"):
                new_t = int(last_decision["new_target_steps"])
                for b in range(target_steps + block_steps, new_t + 1, block_steps):
                    if b not in ckpt_steps_live:
                        ckpt_steps_live.add(b)
                        ckpt_steps_extended.append(b)
                print(f"[train] 平台期规则：块间降幅={last_decision.get('block_drop_frac')} > "
                      f"{args.plateau_min_block_drop_frac} ⇒ **不提前停**，target {target_steps} → {new_t}"
                      f"（elapsed={last_decision.get('elapsed_s')}s / budget={args.train_wall_budget_s}s）",
                      flush=True)
                target_steps = new_t
            else:
                print(f"[train] 停：stopped_by={stopped_by} plateau_reached={plateau_reached} "
                      f"block_drop_frac={last_decision.get('block_drop_frac')} steps={step}", flush=True)
    train_wall_total = round(time.perf_counter() - t_train0, 3)

    # ── checkpoint 选择（**预登记的规则**：val_det_loss 最小；并列取步数少）──
    by_step = {int(c["step"]): c for c in ckpts}
    cand = [r for r in curve if int(r["step"]) in by_step and r.get("val_det_loss") is not None
            and bool(r.get("val_det_finite"))]
    sel: dict = {"rule": CHECKPOINT_SELECTION_RULE, "n_candidates": len(cand),
                 "candidate_table": [{"step": int(r["step"]), "val_det_loss": r["val_det_loss"],
                                     "train_det_loss": r["train_det_loss"],
                                     "sha256_12": by_step[int(r["step"])].get("model_safetensors_sha256_12")}
                                    for r in sorted(cand, key=lambda r: int(r["step"]))],
                 "selected_by_rollout_success_rate": False,
                 "forbidden_selection_basis": "rollout 成功率/推进度（裁定 95.5-③）"}
    if cand:
        best = min(cand, key=lambda r: (float(r["val_det_loss"]), int(r["step"])))
        sel.update({"measurement_status": "measured", "selected_step": int(best["step"]),
                    "selected_val_det_loss": float(best["val_det_loss"]),
                    "selected_train_det_loss": float(best["train_det_loss"]),
                    "selected_dir": by_step[int(best["step"])]["dir"],
                    "selected_rel_dir": by_step[int(best["step"])]["rel_dir"],
                    "selected_sha256_12": by_step[int(best["step"])].get("model_safetensors_sha256_12")})
    else:
        sel.update({"measurement_status": "not_measured", "selected_step": None,
                    "nonzero_exit_required": True,
                    "why": "没有任何有限 val_det_loss 的候选 ⇒ 不许写 0、不许挑最后一个（裁定 88.3-1）"})
        findings.add("no_finite_val_loss_candidate", verdict="RED", blocking=True, subject="checkpoint_selection",
                     evidence=sel, ruling="裁定 95.5-③ / 88.3-1", why="选不出 checkpoint ⇒ 第 1 步无法交付")
    write_json(out_dir / SELECTION_NAME, sel)

    # ── loss 是否「显著下降」（判据原文的第一半）──
    fin = [r for r in curve if r.get("train_det_finite")]
    step0_loss = s0["train_det_loss"]
    final_loss = fin[-1]["train_det_loss"] if fin else None
    ratio = (None if (final_loss is None or not step0_loss) else float(final_loss) / float(step0_loss))
    loss_gate = {"threshold_max_ratio": GATES["train_det_loss_final_over_step0_max"],
                 "step0_train_det_loss": step0_loss, "final_train_det_loss": final_loss,
                 "ratio_final_over_step0": (None if ratio is None else round(ratio, 6)),
                 "pass": (None if ratio is None else bool(ratio <= GATES["train_det_loss_final_over_step0_max"])),
                 "measurement_status": "measured" if ratio is not None else "not_measured",
                 "why": GATES["train_det_loss_final_over_step0_max_why"],
                 "val_step0": s0["val_det_loss"],
                 "val_final": (fin[-1]["val_det_loss"] if fin else None),
                 "val_ratio": (None if (not fin or not s0["val_det_loss"]) else
                               round(float(fin[-1]["val_det_loss"]) / float(s0["val_det_loss"]), 6)),
                 "val_is_reported_not_gated": ("验证损失只**报**、不设为闸：闸设在过拟合臂（判据原文是"
                                               "「过拟合臂 loss 必须显著下降」），验证集只用于 checkpoint 选择")}
    # ── 裁定 102.2-②：**产物必须落 `plateau_reached`(bool) + `train_det_loss_final_over_step0` 实测值** ──
    loss_gate["train_det_loss_final_over_step0"] = (None if ratio is None else round(float(ratio), 9))
    loss_gate["train_det_loss_final_over_step0_caliber"] = (
        "**实测值**（确定性口径：固定 (noise,time) 的 `train_det_loss` 末点 ÷ step0 同口径值）。"
        "它就是 v1 预登记的 `ratio_final_over_step0`，**换名不换值**（裁定 102.2-②(a)：预登记的四个数一个不改）")
    loss_gate["plateau_reached"] = plateau_reached
    loss_gate["plateau_reached_caliber"] = (
        "**三值**：`true` = 块间降幅 ≤1% 后停（真到平台期）；`false` = **还在降**但被墙钟预算/硬上限截断"
        "（裁定 101.4：1 小时未收敛即停并报读数）；`null` = 块数 <2 或扩展被显式关掉 ⇒ **算不出**，"
        "不许写 `false` 顶替（裁定 88.3-1）")
    loss_gate["stopped_by"] = stopped_by
    loss_gate["no_early_stop_while_descending"] = {
        "rule": PLATEAU_RULE["continue_iff"],
        "planned_train_steps": planned_steps,
        "actually_run_steps": int(step),
        "extended_by_plateau_rule": bool(int(step) > planned_steps),
        "extension_log": extension_log,
        "ckpt_steps_preregistered": sorted(int(x) for x in resolved["ckpt_steps"]),
        "ckpt_steps_added_by_extension_rule": sorted(ckpt_steps_extended),
        "extension_rule_is_preregistered": PLATEAU_RULE["extension_is_preregistered"],
        "gates_unchanged": PLATEAU_RULE["gates_unchanged"],
    }
    loss_gate["nearzero_gap_open_item"] = OPEN_STEP1_NEARZERO_GAP
    loss_gate["nearzero_gap_self_binding"] = (
        "**A2 不宣称「接近零」**：本件只报 `train_det_loss_final_over_step0` 的实测值与预登记阈值 0.5 的关系；"
        "两处口径的差 = `OPEN-STEP1-NEARZERO-GAP`，由 **D 在里程碑审查按实测曲线裁**（裁定 102.2-②(c)）")
    loss_gate["plateau_high_value_disposition"] = (
        "裁定 102.2-②：**平台期停在高值 ⇒ Step 1 的答案是 RED（「数据学不到」）**，不是通过 —— "
        "按用户原文：这一步失败，则 RL / LLM / Harness 都没有意义")
    if loss_gate["pass"] is not True:
        findings.add("train_loss_not_significantly_down", verdict="RED", blocking=True,
                     subject="overfit_loss", evidence=loss_gate, ruling="裁定 95.2 第 1 行",
                     why="过拟合臂 loss 没有显著下降 ⇒ 判据的第一半不成立")
    if nonfinite:
        findings.add("nonfinite_train_loss", verdict="RED", blocking=True, subject="numerics",
                     evidence={"n_nonfinite_steps": nonfinite, "precision": args.precision},
                     ruling="—", why="出现非有限 loss ⇒ 该档数值不稳，必须报 D（预登记的 fp32 后备路径）")

    doc.update({
        "measurement_status": "measured",
        "injection_info": inj,
        "resolved_hyperparameters": {"batch_size": bs, "gradient_checkpointing": gc,
                                     "precision": args.precision, "lr": float(hp["lr"]),
                                     "train_steps_planned": planned_steps,
                                     "train_steps_actually_run": int(step),
                                     "train_steps_extension_rule": PLATEAU_RULE["extension_is_preregistered"],
                                     "plateau_block_steps": block_steps,
                                     "plateau_min_block_drop_frac": float(args.plateau_min_block_drop_frac),
                                     "train_wall_budget_s": float(args.train_wall_budget_s),
                                     "train_steps_max_hard_cap": max(int(args.train_steps_max), planned_steps),
                                     "grad_clip_norm": float(hp["grad_clip_norm"]),
                                     "optimizer": "AdamW", "optim_params_source": "policy.get_optim_params()",
                                     "scheduler": hp["scheduler"]},
        "data": {"train_cache": {"path": tr["path"], "sha256_12": tr["sha256_12"], "n_samples": n_train,
                                 "episodes": TRAIN_EPISODES},
                 "val_cache": {"path": va["path"], "sha256_12": va["sha256_12"], "n_samples": n_val,
                               "episodes": VAL_EPISODES},
                 "n_train_epochs_implied": round(int(step) * bs / max(1, n_train), 4)},
        "curve": curve,
        "checkpoints": ckpts,
        "selection": sel,
        "loss_gate": loss_gate,
        "n_nonfinite_steps": nonfinite,
        "timing": {"train_wall_s_total": train_wall_total,
                   "wall_s_per_step_mean": round(train_wall / max(1, int(step)), 4),
                   "n_steps": int(step), "total_wall_s": round(time.perf_counter() - t0, 2),
                   "load_pair": {"before": load_before,
                                 "after": PBG.gpu_window_readings(extra={"phase": "train_after"})},
                   "pairing_rule": "裁定 46.4/53.6/85.7：吞吐数字成对带 loadavg(3 点)+nr_throttled",
                   "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / (1 << 20), 1),
                   "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / (1 << 20), 1),
                   "single_seed_wall_s": round(time.perf_counter() - t0, 2),
                   "single_seed_over_8h": bool((time.perf_counter() - t0) > 8 * 3600),
                   "escalation_if_over_8h": "补单四 §三：立刻报 D，不得静默超预算"},
    })
    # ── 动作逐维对齐（判据原文的第二半）：step0 vs 选中 ckpt ──
    matches: dict = {}
    matches["selected"] = action_match_analysis(policy, pre, post, tr, det_tr, stats=reuse["stats"],
                                                image_size=args.image_size, bs=bs, fps=fps,
                                                tag=f"train_split@step{sel.get('selected_step')}")
    doc["action_match"] = matches
    if matches["selected"].get("gates_all_pass") is not True:
        findings.add("action_match_gate_not_passed", verdict="RED", blocking=True,
                     subject="per_dim_action_match",
                     evidence={"red_codes": matches["selected"].get("red_codes"),
                               "summary_observed_dims": matches["selected"].get("summary_observed_dims"),
                               "gripper_timing_gate": (matches["selected"].get("gripper_timing") or {}).get("gate")},
                     ruling="裁定 95.2 第 1 行（含夹爪开合时刻）",
                     why="动作逐维（8 个非盲点维）或夹爪开合时刻没对上示范 ⇒ 判据的第二半不成立")
    ident = write_json(out_dir / "TRAIN_REPORT.json", doc)
    print(f"[train] ratio={loss_gate['ratio_final_over_step0']} pass={loss_gate['pass']} "
          f"selected_step={sel.get('selected_step')} "
          f"action_match_gates={matches['selected'].get('gates_all_pass')} "
          f"artifact={ident['path']} {ident['sha256_12']}", flush=True)
    del policy
    torch.cuda.empty_cache()
    return doc


# ══════════════════════════ ⑦ 策略与适配器（复用 + 显式登记的最小差异）══════════════
class Step1ChunkPolicy(S4B.Pi05ChunkPolicy):
    """`S4B.Pi05ChunkPolicy` 的**最小**子类。

    继承不变的部分（**一个字节都不改**）：`zs.build_policy()` 从目录载权重、`PBG.PromptCapture`
    旁路抓「模型真正吃到的那一条 prompt」、`predict_action_chunk` → `post` → `zs.adapt_action`
    的 32/14→14 适配与 ctrlrange 裁剪统计、`H ≥ 2n` 的自检、推理墙钟计量。

    唯一差异 = **三个身份字段**。父类把它们写成 base 臂的正确身份（`pi05_base_zero_sft@…` /
    `stats_version=NONE`）；本臂载的是**带 C2 stats 注入的目录**（`step_000000` = 未微调，
    `step_NNNNNN` = BC 微调后）⇒ 身份必须跟着改，否则 runtime 的 `_guard_stats_version()` 会
    硬隔离 td/bc 资格（裁定 44.1/49.2 的反面），而那是**假红**。
    """

    def __init__(self, *, arm_label: str, ckpt_sha12: str | None, representation_version: str | None,
                 arm_note: str = "", **kw):
        super().__init__(**kw)
        self.arm_label = arm_label
        self.arm_note = arm_note
        self.policy_version = f"{arm_label}@{ckpt_sha12 or 'unverified'}"
        self.stats_version = representation_version or VR.STATS_VERSION_ABSENT

    def identity(self) -> dict:
        d = super().identity()
        d.update({
            "kind": self.arm_label,
            "parent_identity_kind_overridden_from": "pi05_base_zero_sft",
            "identity_override_reason": ("父类写死的是 **base 臂**的身份；本臂载的是带 C2 stats 注入的目录"
                                         "（未微调 or BC 微调后）⇒ `policy_version`/`stats_version` 必须跟着改，"
                                         "否则 `_guard_stats_version()` 会硬隔离 td/bc 资格（假红）"),
            "arm_note": self.arm_note,
            "stats_version_is_c2_representation_version": (self.stats_version != VR.STATS_VERSION_ABSENT),
            "loaded_from": str(self.weights_identity.get("dir") or ""),
        })
        return d


class RandomChunkPolicy:
    """**裁定 95.2 第 1 行点名的随机基线**：每帧在合法物理动作空间内均匀采样。

    与 BC 臂**同口径**：BC 臂经 `zs.adapt_action` 之后落的也是「臂维 ∈ `actuator_ctrlrange`、
    夹爪维 ∈ [0,1]」这个物理空间 ⇒ 在这里直接采，不多一次非线性映射。
    容器与 chunk 字段照 `S4B._Rows` / `HoldPolicy` 的同一形状（不另造）。
    """

    def __init__(self, adapter, *, n_replan: int, chunk_size: int, rng_seed: int, stats_version: str):
        self.adapter = adapter
        self.n_replan = int(n_replan)
        self.chunk_size = int(chunk_size)
        self.rng = np.random.default_rng(int(rng_seed))
        self.rng_seed = int(rng_seed)
        self.stats_version = stats_version
        self.policy_version = f"random_uniform_physical_action_space@seed{int(rng_seed)}"
        phys = adapter.jenv.physics
        lo = np.asarray(phys.model.actuator_ctrlrange[:, 0], dtype="float64")
        hi = np.asarray(phys.model.actuator_ctrlrange[:, 1], dtype="float64")
        self.act_idx = list(range(0, 6)) + list(range(8, 14))
        self.arm_dim = list(range(0, 6)) + list(range(7, 13))
        self.lo = np.asarray([lo[i] for i in self.act_idx], dtype="float64")
        self.hi = np.asarray([hi[i] for i in self.act_idx], dtype="float64")
        self.g = 0
        self.n_calls = 0
        self.clip_stats = {"n_values": 0, "n_clipped": 0, "max_clip_magnitude": 0.0,
                           "raw_absmax": float(max(abs(self.lo).max(), abs(self.hi).max())),
                           "note": ("构造性事实：本臂的动作**直接**在 ctrlrange 内采样 ⇒ 永不被裁剪。"
                                    "`raw_absmax` 记的是 ctrlrange 的绝对上界，用于「单位错配」探测器")
                           }

    def reset(self, seed: int) -> None:
        self.g = 0
        self.rng = np.random.default_rng(int(self.rng_seed))

    def _one(self):
        a = np.zeros((STATE_DIM,), dtype=np.float64)
        a[self.arm_dim] = self.rng.uniform(self.lo, self.hi)
        for gdim in GRIP_DIMS:
            a[gdim] = float(self.rng.uniform(0.0, 1.0))
        return a.astype("float32").tolist()

    def select_chunk(self, obs) -> VR.ActionChunk:
        self.g += 1
        self.n_calls += 1
        rows = [self._one() for _ in range(self.chunk_size)]
        n = self.n_replan
        return VR.ActionChunk(
            request_id="placeholder", chunk_index=-1, chunk_id=f"random-chunk-{self.g}", lease_generation=-1,
            epoch=0, actions=S4B._Rows(rows), created_at_frame=-1, planned_frames=(-1, -1),
            slot_c=tuple(range(0, n)), slot_e=tuple(range(n, 2 * n)), slot_d=tuple(range(2 * n, self.chunk_size)),
            dt_s=self.adapter.dt_s, control_hz=self.adapter.control_hz, n_replan=n,
            chunk_size=self.chunk_size, inference_wall_s=None, deadline_frame=-1, deadline_s=-1.0,
            policy_version=self.policy_version, stats_version=self.stats_version,
            shim_sha256_12=self.adapter.shim.shim_sha256_12(), representation_version="placeholder")

    def identity(self) -> dict:
        return {"kind": "random_uniform_baseline", "policy_version": self.policy_version,
                "stats_version": self.stats_version,
                "stats_version_note": ("随机基线**不是** BC 策略 ⇒ 没有 stats 版本可声明；"
                                       "写 `NONE` 会让 runtime 硬隔离 td/bc 资格，这是**预期形态**（它本来"
                                       "就不该进训练视图）"),
                "chunk_size": self.chunk_size, "n_replan": self.n_replan,
                "action_space": "臂维 U[ctrlrange_lo, ctrlrange_hi] · 夹爪维 U[0,1]（与 BC 臂同口径）",
                "rng": f"np.random.default_rng({self.rng_seed})",
                "definition": RANDOM_BASELINE_DEFINITION,
                "clip_stats": dict(self.clip_stats), "n_inference_calls": self.n_calls,
                "capability_claim": False}


class DemoInitAdapter(VR.GymAlohaJudgedAdapter):
    """`VR.GymAlohaJudgedAdapter` 的子类，**唯一**差异：`reset()` 之后把物理直接置到**示范初态**。

    为什么必须这样（先落腿结论 5/6，已实测）：B2 的 `settle_steps=12` **不进数据集** ⇒ 数据集的
    frame-0 已经是「方块从 z=0.05 落到 0.02 + 两腕转到 `R_DOWN`」之后的状态，而 `env.reset(seed)`
    给的是 spawn 状态；而且 `reset(seed)` 的方块复现只在 **forward** 方向成立（B2 用方向镜像的
    `sample_box_pose_seeded`，gym-aloha 用不镜像的 `sample_box_pose`）⇒ 反向集必须按 sidecar 写 box。
    做法 = 直接写 qpos（arm 用 `unnormalize_puppet_gripper_position` 逆映射、box 用 sidecar 的
    `box_rest_after_settle_xyz`）+ `qvel=0` + `physics.forward()`；实测 `nmocap=0`/`neq=0` ⇒
    **没有** weld/mocap 会把臂拽走。写入后**每局回读自证**（超容差 ⇒ 该局判 RED，不当成功也不当失败）。
    """

    def __init__(self, *, demo_init: dict, unorm_fn, tol: float, **kw):
        super().__init__(**kw)
        self.demo_init = demo_init
        self._unorm = unorm_fn
        self._tol = float(tol)
        self.demo_init_apply_record: dict | None = None

    def reset(self, seed: int):
        super().reset(seed)
        s14 = np.asarray(self.demo_init["frame0_state"], dtype=np.float64)
        rec = PRE._init_env_to_state(self.jenv, s14, self.demo_init["box_xyz"], self._unorm)
        st = np.asarray(self.jenv._state(), dtype=np.float64).reshape(-1)
        hold = [float(x) for x in st[:14]]
        for gi in GRIP_DIMS:
            if gi < len(hold):
                hold[gi] = min(max(hold[gi], 0.0), 1.0)
        self._hold = hold                      # hold 必须跟**示范初态**走，不能留 reset 的那一份
        self._frame = 0
        rb = np.asarray(self.jenv._state(), dtype=np.float64).reshape(-1)[:STATE_DIM]
        diff = float(np.abs(rb - s14).max())
        rec.update({
            "readback_maxdiff": diff, "readback_ok": bool(diff <= self._tol), "tol": self._tol,
            "demo_episode_index": self.demo_init.get("episode_index"),
            "demo_ep_id": self.demo_init.get("ep_id"),
            "demo_seed": self.demo_init.get("seed"),
            "box_xyz_written": [float(x) for x in np.asarray(self.demo_init["box_xyz"], dtype=np.float64)],
            "box_xyz_source": ("sidecar `box_rest_after_settle_xyz`（**不是** spawn 的 `box_spawn_xyz`；"
                               "先落腿结论 5/6）"),
            "qvel_zeroed_because": ("数据集不存 qvel ⇒ 只能置零。先落腿结论 10 曾把它写成「**唯一**已知"
                                    "初值差」—— 那个「唯一」现在是**错的**（裁定 104.2-⑤）：还有第二处，"
                                    "见下面的 `box_quat_not_written`"),
            "box_quat_not_written": ("`PRE._init_env_to_state` 只写方块自由关节的 **xyz**（`qpos[16:19]`），"
                                     "**不写四元数**（`qpos[19:23]`）⇒ Step-1 的闭环初态是「**沉降后** xyz"
                                     "（sidecar `box_rest_after_settle_xyz`）+ `reset(seed)` 留下的**沉降前**"
                                     "四元数」的拼接。登记为 Ⅰ 类缺陷 `demo_init_box_quat_not_written`"
                                     "（裁定 104.2，OPEN）；**量级由 CPU-only 测量件给**，本键不猜"),
            "box_quat_defect_status": box_quat_defect_status(),
            "reused_from": ("scripts/a2_step1_prealign_verify.py::_init_env_to_state"
                            "（L9 已自证 4/4 集 `state maxdiff = 0.0`）"),
            "readback_scope_caveat": ("`readback_maxdiff` / `readback_ok` 与阻塞牙 "
                                      "`demo_init_readback_failed` 都只覆盖 **14 维机器人状态**"
                                      "（`jenv._state()[:STATE_DIM]`），**不含方块位姿** ⇒ 它们**不能**"
                                      "用来证明「方块初值差不影响本局」（裁定 104.2：证据作用域 ⊊ 结论作用域）"),
            "measurement_status": "measured",
        })
        self.demo_init_apply_record = rec
        return self._obs(0)


# ══════════════════════════ ⑧ 推进度（方向感知，标量全部来自 C2 的 facts）══════════════
def progress_from_frames(frames: list[dict], *, direction: str, thresholds: dict,
                         geometric_success_any: bool, hold_steps_max: int) -> dict:
    tgt = "left" if direction == "right_to_left" else "right"
    src = "right" if tgt == "left" else "left"
    grasp_max = float(thresholds.get("grasp_max_dist_m") or 0.05)
    rows = []
    for f in frames:
        facts = f.get("facts") or {}
        bx = np.asarray(facts.get("box_xyz") or [np.nan] * 3, dtype=np.float64)
        ft = np.asarray((facts.get("finger_xyz") or {}).get(tgt) or [np.nan] * 3, dtype=np.float64)
        fs = np.asarray((facts.get("finger_xyz") or {}).get(src) or [np.nan] * 3, dtype=np.float64)
        if not np.isfinite(bx).all() or not np.isfinite(ft).all():
            rows.append({"abs_frame": f.get("abs_frame"), "stage": None,
                         "measurement_status": "not_measured",
                         "why": "方块或目标侧指 geom 位置读不到 ⇒ 该帧不判（不猜 0）"})
            continue
        d_tgt = float(np.linalg.norm(bx - ft))
        d_src = float(np.linalg.norm(bx - fs)) if np.isfinite(fs).all() else None
        height = float(bx[2] - float(facts.get("table_z_ref") or 0.0))
        c_src = bool((facts.get("contact_box_finger") or {}).get(src))
        c_tgt = bool((facts.get("contact_box_finger") or {}).get(tgt))
        off = not bool(facts.get("contact_box_table"))
        stage = 0
        if c_src:
            stage = 1
        if c_src and off:
            stage = 2
        if c_src and off and d_tgt <= grasp_max:
            stage = 3
        rows.append({"abs_frame": f.get("abs_frame"), "stage": stage, "dist_target": d_tgt,
                     "dist_source": d_src, "height_over_table_z_ref": height,
                     "contact_source": c_src, "contact_target": c_tgt, "off_table": off,
                     "box_xyz": [float(x) for x in bx],
                     "env_reward": facts.get("env_reward"), "measurement_status": "measured"})
    meas = [r for r in rows if r.get("measurement_status") == "measured"]
    if not meas:
        return {"measurement_status": "not_measured", "max_stage": None, "nonzero_exit_required": True,
                "why": "没有任何一帧读到方块/目标侧指位置 ⇒ 推进度不可测（**不是** 0）", "rows_head": rows[:3]}
    d_init = meas[0]["dist_target"]
    min_d = min(r["dist_target"] for r in meas)
    max_h = max(r["height_over_table_z_ref"] for r in meas)
    b0 = np.asarray(meas[0]["box_xyz"], dtype=np.float64)
    ft0 = None
    for f, r in zip(frames, rows):
        if r.get("measurement_status") == "measured":
            facts = f.get("facts") or {}
            ft0 = np.asarray((facts.get("finger_xyz") or {}).get(tgt), dtype=np.float64)
            break
    axis = (ft0 - b0)
    nrm = float(np.linalg.norm(axis))
    unit = axis / nrm if nrm > 1e-9 else np.zeros(3)
    disp = max(float(np.dot(np.asarray(r["box_xyz"], dtype=np.float64) - b0, unit)) for r in meas)
    stages = [int(r["stage"]) for r in meas]
    return {
        "measurement_status": "measured",
        "max_stage": max(stages),
        "stage_reached_at_abs_frame": (meas[stages.index(max(stages))]["abs_frame"] if meas else None),
        "stage_ladder_definition": PROGRESS_LADDER,
        "net_approach_target": (None if d_init <= 1e-9 else round((d_init - min_d) / d_init, 6)),
        "d_init_target_m": round(d_init, 6), "min_dist_target_m": round(min_d, 6),
        "max_height_over_table_z_ref_m": round(max_h, 6),
        "max_displacement_toward_target_m": round(disp, 6),
        "displacement_axis_definition": "unit(目标侧指在 frame0 的位置 − 方块在 frame0 的位置)（方向无关）",
        "max_hold_steps": int(hold_steps_max),
        "geometric_success_any_frame": bool(geometric_success_any),
        "target_side": tgt, "source_side": src, "grasp_max_dist_m": grasp_max,
        "n_frames_measured": len(meas), "n_frames_not_measured": len(rows) - len(meas),
        "table_z_ref_note": ("先落腿结论 7（Ⅰ/Ⅱ 类，已报 D、A2 不改）：C2 的 `_table_z_ref` 自标定读的是方块 "
                             "**spawn** 高度 z=0.05，而静止后是 z=0.02 ⇒ 参考面偏高 0.03 m。本件的 `max_height` "
                             "沿用 C2 的同一个 `table_z_ref`（**不自造第二个参考面**），因此它与 C2 的 `lift_ok` "
                             "同口径；跨件比较时这条偏差对**所有臂同向**，不改变臂间差值"),
        "rows_head": rows[:5], "rows_tail": rows[-5:],
    }


# ══════════════════════════ ⑨ 单局（模板 = `S4B.run_episode`；差异只有一处）══════════════
def run_episode_demo_init(*, arm: str, ep: dict, args, policy, ledger, window, reuse,
                          out_dir: pathlib.Path, unorm_fn) -> dict:
    """与 `S4B.run_episode` 的**差异清单**（逐项登记，别的不改）：
      ① 适配器换成 `DemoInitAdapter`（`reset()` 之后写示范初态 + 回读自证）；
      ② `exec_mode=standard_sync` + `prime_mode=none`（裁定 95.3-④；S4B 那臂是 harness_second_half）；
      ③ 逐帧收 `facts`/`qpos` 以算推进度与 OOD 信号（S4B 只收 outcome_class 跃变）；
      ④ 四字段（裁定 95.3-①）用 `VR.four_fields_from_episode` 实算，OOD 五个信号**逐个真测**。
    其余（三网读数成对、prompt 审计、renderer 三点、ledger round-trip、timing_report、env_manifest）
    逐项照搬 S4B 的同名字段。
    """
    zs = reuse["zs"]
    direction = ep["env_direction"]
    seed = int(ep["seed"])
    ep_index = int(ep["episode_index"])
    ad = DemoInitAdapter(demo_init=ep, unorm_fn=unorm_fn, tol=float(args.state_reproduce_tol),
                         direction=direction, image_size=args.image_size, render=True)
    if callable(policy):
        policy = policy(ad, direction)
    ep_id = f"step1-{arm}-{direction}-{ep_index:02d}"
    rt = VR.ChunkedVlaRuntime(
        policy, ad, episode_id=ep_id, goal_id=ad.goal_id, epoch=0, n_replan=args.n_replan,
        dt_s=ad.dt_s, late_policy=VR.MAINLINE_LATE_POLICY, prime_mode=VR.PRIME_MODE_NONE,
        exec_mode=VR.EXEC_MODE_STANDARD_SYNC, ledger=ledger,
        shim_sha256_12=ad.jenv.timing.get("shim_sha256_12", "unspecified"), async_overlap=False,
        max_episode_steps=ad.max_episode_steps)
    load_before = PBG.gpu_window_readings(extra={"phase": f"{arm}_ep{ep_index}_before"})
    prompt_lo = len(policy.capture.prompts) if getattr(policy, "capture", None) else 0
    n_calls_before = getattr(policy, "n_calls", None)
    t0 = time.perf_counter()
    rt.reset(seed=seed)
    demo_init_record = dict(ad.demo_init_apply_record or {})
    max_frames = min(int(args.max_frames or ad.max_episode_steps), int(ad.max_episode_steps))
    frames: list[dict] = []
    states: list[list[float]] = []
    transitions: list[dict] = []
    prev_oc = "__none__"
    stop_reason = "frame_budget_exhausted"
    n = 0
    hold_max = 0
    geom_any = False
    thr: dict = {}
    last_jud: dict = {}
    while n < max_frames:
        sr = rt.step()
        n += 1
        info = sr.info or {}
        jud = info.get("judgment") or {}
        if isinstance(jud, dict) and jud:
            last_jud = dict(jud)
        if not thr and isinstance(jud.get("thresholds"), dict):
            thr = dict(jud["thresholds"])
        frames.append({"abs_frame": sr.abs_frame, "facts": info.get("facts") or {},
                       "outcome_class": info.get("outcome_class"),
                       "geometric_success": info.get("geometric_success"),
                       "hold_steps": info.get("hold_steps")})
        if isinstance(info.get("qpos"), (list, tuple)):
            states.append([float(x) for x in info["qpos"]])
        hold_max = max(hold_max, int(info.get("hold_steps") or 0))
        geom_any = bool(geom_any or info.get("geometric_success"))
        oc = info.get("outcome_class")
        if oc != prev_oc:
            transitions.append({"abs_frame": sr.abs_frame, "outcome_class": oc,
                                "env_reward": info.get("env_reward"),
                                "geometric_success": info.get("geometric_success"),
                                "env_is_success": info.get("env_is_success"),
                                "hold_steps": info.get("hold_steps")})
            prev_oc = oc
        if sr.terminated or sr.truncated:
            stop_reason = ("env_terminated(is_success==reward==4)" if sr.terminated
                           else "env_truncated(TimeLimit)")
            break
        if oc == "success" and args.stop_on_geometric_success:
            stop_reason = "geometric_success__mirrors_c2_env_done_semantics"
            break
    wall_s = time.perf_counter() - t0
    renderer_at_end = ad.measure_renderer_at_end()
    out = rt.finalize_from_env_judgment(ad, ledger=ledger)
    roundtrip = VR.s4b_outcome_from_ledger(ledger, episode_id=ep_id)
    load_after = PBG.gpu_window_readings(extra={"phase": f"{arm}_ep{ep_index}_after"})
    nr0, nr1 = load_before.get("nr_throttled"), load_after.get("nr_throttled")
    prog = progress_from_frames(frames, direction=direction, thresholds=thr,
                                geometric_success_any=geom_any, hold_steps_max=hold_max)

    # ---- prompt 牙（与 S4B 同实现、同口径）----
    cap = getattr(policy, "capture", None)
    if cap is not None:
        sl = list(cap.prompts[prompt_lo:])
        pa = cap.audit(prompts=sl)
        pa["n_prompts_in_this_episode"] = len(sl)
        per = [PBG.audit_prompt_text(p) for p in sl]
        sat: set[int] = set()
        ill: set[int] = set()
        for a in per:
            sat.update(int(i) for i in (a.get("saturated_bin_255_dims") or []))
            ill.update(int(i) for i in (a.get("illegal_bin_minus1_dims") or []))
        pa.update({"saturated_bin_255_dims_union": sorted(sat), "illegal_bin_minus1_dims_union": sorted(ill),
                   "state_dim_after_pad_values": sorted({int(a["state_dim_after_pad"]) for a in per
                                                         if isinstance(a.get("state_dim_after_pad"), int)}),
                   "per_prompt_audit_reused": "harness/prompt_bin_guard.audit_prompt_text（同一实现，不另造）"})
    else:
        pa = {"measurement_status": "not_applicable", "verdict": None, "n_prompts_in_this_episode": 0,
              "why": ("本臂不是 π₀.₅ 推理臂（random / hold）⇒ 没有 prompt 可审。"
                      "`not_applicable` ≠「审过且 0 命中」（三值纪律）")}

    # ---- OOD 五信号（裁定 95.3-① 的 (b) 类：**只标注、不剔除**）----
    q01 = np.asarray(reuse["stats"]["q01"], dtype=np.float64)
    q99 = np.asarray(reuse["stats"]["q99"], dtype=np.float64)
    denom = np.where((q99 - q01) == 0, 1e-8, (q99 - q01))
    below = above = 0
    below_dims: set[int] = set()
    above_dims: set[int] = set()
    if states:
        S = np.asarray(states, dtype=np.float64)
        Z = 2.0 * (S - q01) / denom - 1.0
        below_dims = {int(d) for d in np.flatnonzero((Z < -1.0).any(axis=0))}
        above_dims = {int(d) for d in np.flatnonzero((Z >= 1.0).any(axis=0))}
        below = int((Z < -1.0).sum())
        above = int((Z >= 1.0).sum())
    cs = dict(getattr(policy, "clip_stats", {}) or {})
    raw_absmax = float(cs.get("raw_absmax") or 0.0)
    ctrl_absmax = float(max(np.abs(ad.jenv.physics.model.actuator_ctrlrange).max(), 1e-9))
    is_model_arm = bool(cs)
    ood = {
        "state_out_of_normalizer_range": (bool(below or above) if states else None),
        "state_out_of_normalizer_range_detail": {
            "n_values_below_minus1": below, "n_values_at_or_above_plus1": above,
            "dims_below_minus1": sorted(below_dims), "dims_saturated_plus1": sorted(above_dims),
            "polarity_note": ("先落腿结论 2：`x < −1` 是**硬红**（§23.2 的 `-1` bin），`x ≥ 1` 是**合法**优雅饱和"
                              "（bin 255）。这里两者都算「越出归一化器区间」⇒ 都进 OOD 标注；"
                              "硬红/合法的区分由 prompt 牙与 `dims_*` 分列承担"),
            "n_frames_with_state": len(states)},
        "action_clipped_at_ctrlrange": (bool(cs.get("n_clipped")) if is_model_arm else None),
        "action_clipped_at_ctrlrange_detail": cs or {"why_not_measured": "非模型臂没有 clip_stats"},
        "prompt_bins_saturated_255": ((int(pa.get("n_saturated_bin_255") or 0) > 0)
                                      if pa.get("measurement_status") == "measured" else None),
        "prompt_bins_illegal_minus1": ((int(pa.get("n_illegal_bin_minus1") or 0) > 0)
                                       if pa.get("measurement_status") == "measured" else None),
        "action_unit_mismatch_suspected": (
            (bool(raw_absmax > 3.0 * ctrl_absmax) if is_model_arm
             else False),
        ),
        "action_unit_mismatch_suspected_detail": {
            "detector": "`raw_absmax > 3 × max|actuator_ctrlrange|`（预登记的固定倍数，不调参）",
            "raw_absmax": raw_absmax, "ctrl_absmax": round(ctrl_absmax, 6),
            "non_model_arm_value": ("random/hold 臂的动作**构造上**就在合法物理空间内 ⇒ `False` 是构造性事实，"
                                    "不是「未测」"),
        },
    }
    ff = VR.four_fields_from_episode(
        outcome_class=(out.as_dict() or {}).get("outcome_class"),
        ledger_roundtrip_status=roundtrip.get("measurement_status"),
        timing_measured=(rt.timing_report().get("wall_ms_per_ctrl_step") is not None),
        isolation_reasons=rt.isolation_reasons, ood_signals=ood,
        seed=seed, direction=direction,
        autonomous_success=(True if (out.as_dict() or {}).get("outcome_class") == "success"
                            else (False if (out.as_dict() or {}).get("outcome_class") in ("failure", "timeout")
                                  else None)),
        intervention_count=0,
        evidence={"arm": arm, "exec_mode": VR.EXEC_MODE_STANDARD_SYNC, "prime_mode": VR.PRIME_MODE_NONE,
                  "n_replan": args.n_replan,
                  "intervention_count_note": ("第 1 步 = `standard_sync` + `prime_mode=none` ⇒ **没有**接管通路"
                                              "（裁定 95.3-④：第 1–2 步不用后半段调度）；`intervention_count=0` "
                                              "是**构造性事实**，同时 `queue_drain_events` / `late_records` / "
                                              "`sync_overload_records` 三个计数照实报，用来证明它不是掩盖"),
                  "note": "四字段分开记；`out_of_distribution` 只标注不剔除（裁定 95.3-①）"})
    timing = rt.timing_report()
    rec = {
        "artifact": "bc_step1_episode", "arm": arm, "arm_definition": ARMS.get(arm, arm),
        "episode_id": ep_id, "episode_index": ep_index, "ep_id_demo": ep.get("ep_id"),
        "direction": direction, "manifest_direction": MANIFEST_DIRECTION_BY_ENV.get(direction),
        "seed": seed, "goal_id": ad.goal_id, "task_text": ep.get("task_text"),
        "split": ep.get("split"),
        "initial_state": {"kind": "demo_frame0_state（判据原文：**从示范初态**闭环执行）",
                          "apply_record": demo_init_record,
                          "readback_ok": demo_init_record.get("readback_ok"),
                          "readback_maxdiff": demo_init_record.get("readback_maxdiff")},
        "n_control_frames": n, "max_frames_allowed": max_frames, "stop_reason": stop_reason,
        "wall_s": round(wall_s, 2),
        "outcome": out.as_dict(),
        "four_fields": ff.as_dict(),
        "ood_signals": ood,
        "progress": prog,
        "final_judgment": last_jud,
        "final_judgment_reasons": list(last_jud.get("reasons") or []),
        "final_judgment_source": ("C2 的 `judge_from_facts()`（判定层归 C2，A2 **不重算、不改写**；"
                                  "这里只是把最后一帧的判词原文抄进本局记录，供第 ④ 问定位用）"),
        "ledger_roundtrip": roundtrip,
        "renderer_class_three_points": ad.renderer_ledger.snapshot(),
        "n_renders_in_run": ad.n_renders_in_run,
        "isolation_reasons": list(rt.isolation_reasons),
        "td_eligible": out.training_view.td_eligible, "bc_eligible": out.training_view.bc_eligible,
        "timing_report": timing,
        "harness_takeover_counters": {
            "n_queue_drain_events": len(rt.queue_drain_events),
            "n_late_records": len(rt.late_records),
            "n_sync_overload_records": len(rt.sync_overload_records),
            "n_chunks_committed": timing.get("n_chunks_committed"),
            "late_policy": VR.MAINLINE_LATE_POLICY,
            "interpretation": ("裁定 95.6 第 ⑤ 问「Harness 接管了多少次」的实测答案：三个计数**全为 0** 才叫"
                               "「没接管」；`sync_overload_records` 非 0 **不是**接管（标准同步执行下推理阻塞"
                               "控制环、仿真时间不推进 ⇒ 没有过期的槽可作废，裁定 75.4 的软约束事实）"),
        },
        "load_pair": {"before": load_before, "after": load_after,
                      "nr_throttled_delta": (None if (nr0 is None or nr1 is None) else int(nr1) - int(nr0)),
                      "pairing_rule": "裁定 46.4/53.6/85.7：延迟/吞吐数字成对带 loadavg(3 点)+nr_throttled"},
        "prompt_audit": pa,
        "representation_version": rt.representation_version,
        "n_inference_calls_this_episode": (None if n_calls_before is None
                                           else (int(getattr(policy, "n_calls", 0)) - int(n_calls_before))),
        "outcome_transitions": transitions,
        "env_manifest": ad.manifest(),
        "policy_identity": S4B.policy_identity_of(policy),
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "gpu_stats": zs.gpu_stats(),
        "capability_claim": False,
        "success_rate_column": SUCCESS_RATE_COLUMN,
    }
    ad.close()
    return rec, ff


# ══════════════════════════ ⑩ rollout（从示范初态闭环 · standard_sync）══════════════
def _arm_policy_factory(arm: str, args, reuse: dict, ctx: dict):
    zs = reuse["zs"]
    if arm in ("bc", "injected_base"):
        key = "bc" if arm == "bc" else "injected_base"
        d = ctx["model_dirs"][key]
        cache: dict = {}

        def factory(ad, direction):
            p = cache.get("p")
            if p is None:
                p = Step1ChunkPolicy(
                    arm_label=ctx["arm_labels"][key], ckpt_sha12=d["sha256_12"],
                    representation_version=ctx["representation_version"], arm_note=ctx["arm_notes"][key],
                    adapter=ad, zs=zs, weights_dir=d["dir"], tokenizer_dir=args.tokenizer_dir,
                    device=args.device, task_text=args.task_by_direction[direction],
                    n_replan=args.n_replan, weights_identity={"dir": d["dir"], **d})
                cache["p"] = p
                print(f"[rollout:{arm}] loaded {d['dir']} in {p.load_info.get('load_s')}s "
                      f"H={p.chunk_size} policy_version={p.policy_version} "
                      f"stats_version={p.stats_version[:32]}…", flush=True)
            p.task_text = args.task_by_direction[direction]
            return p
        factory.cache = cache
        factory.free = lambda: (cache.clear(),)
        return factory
    if arm == "base_zeroshot":
        wident = ctx["base_weights_identity"]
        cache: dict = {}

        def factory(ad, direction):
            p = cache.get("p")
            if p is None:
                p = S4B.Pi05ChunkPolicy(adapter=ad, zs=zs, weights_dir=args.weights_dir_resolved,
                                        tokenizer_dir=args.tokenizer_dir, device=args.device,
                                        task_text=args.task_by_direction[direction],
                                        n_replan=args.n_replan, weights_identity=wident)
                cache["p"] = p
                print(f"[rollout:base_zeroshot] loaded in {p.load_info.get('load_s')}s "
                      f"H={p.chunk_size} policy_version={p.policy_version} "
                      f"stats_version={p.stats_version}", flush=True)
            p.task_text = args.task_by_direction[direction]
            return p
        factory.cache = cache
        factory.free = lambda: (cache.clear(),)
        return factory
    if arm == "random":
        def factory(ad, direction):
            return RandomChunkPolicy(ad, n_replan=args.n_replan, chunk_size=int(args.chunk_size),
                                     rng_seed=int(args.random_seed0) + int(ad.demo_init["episode_index"]),
                                     stats_version=VR.STATS_VERSION_ABSENT)
        factory.cache = {}
        factory.free = lambda: None
        return factory
    if arm == "hold":
        mod = S4B.load_module_by_path("a2_s4b_outcome_ledger_verify",
                                      "scripts/a2_s4b_outcome_ledger_verify.py")

        def factory(ad, direction):
            return mod.HoldPolicy(ad, n_replan=args.n_replan, stats_version=VR.STATS_VERSION_ABSENT)
        factory.cache = {}
        factory.free = lambda: None
        return factory
    raise ValueError(f"未知臂 {arm!r}，可选 {sorted(ARMS)}")


def _prog_key(p: dict, i: int) -> tuple:
    order = ("max_stage", "net_approach_target", "max_height_over_table_z_ref_m", "max_hold_steps")
    vals = []
    for k in order:
        v = p.get(k)
        vals.append(-1e18 if v is None else float(v))
    return tuple(vals) + (int(i),)


def paired_comparison(a_recs: list[dict], b_recs: list[dict], *, a_name: str, b_name: str) -> dict:
    """**逐集配对**（同一示范初态、同一帧预算、同一运行时）比较推进度。
    判据顺序 = 预登记的 `tiebreak_order`；总判用 `sum(max_stage)`，相等则退到 `sum(net_approach_target)`。"""
    idx = {(r["episode_index"], r["seed"]): r for r in b_recs}
    rows, wins, ties, losses, notmeas = [], 0, 0, 0, 0
    for r in a_recs:
        k = (r["episode_index"], r["seed"])
        o = idx.get(k)
        pa, pb = r.get("progress") or {}, (o or {}).get("progress") or {}
        if pa.get("measurement_status") != "measured" or pb.get("measurement_status") != "measured":
            notmeas += 1
            rows.append({"episode_index": k[0], "seed": k[1], "direction": r.get("direction"),
                         "measurement_status": "not_measured", "verdict": None,
                         "why": "至少一臂的推进度不可测 ⇒ 该配对不判（不猜）"})
            continue
        ka, kb = _prog_key(pa, k[0]), _prog_key(pb, k[0])
        v = "win" if ka > kb else ("loss" if ka < kb else "tie")
        wins += v == "win"
        ties += v == "tie"
        losses += v == "loss"
        rows.append({"episode_index": k[0], "seed": k[1], "direction": r.get("direction"),
                     "split": r.get("split"), "measurement_status": "measured", "verdict": v,
                     a_name: {kk: pa.get(kk) for kk in ("max_stage", "net_approach_target",
                                                         "max_height_over_table_z_ref_m", "max_hold_steps",
                                                         "min_dist_target_m", "d_init_target_m")},
                     b_name: {kk: pb.get(kk) for kk in ("max_stage", "net_approach_target",
                                                         "max_height_over_table_z_ref_m", "max_hold_steps",
                                                         "min_dist_target_m", "d_init_target_m")},
                     "tiebreak_order": PROGRESS_METRIC_DEFINITION["tiebreak_order"]})

    def ssum(recs, key):
        vs = [(r.get("progress") or {}).get(key) for r in recs]
        vs = [float(v) for v in vs if v is not None]
        return round(sum(vs), 6) if vs else None
    sa, sb = ssum(a_recs, "max_stage"), ssum(b_recs, "max_stage")
    na, nb = ssum(a_recs, "net_approach_target"), ssum(b_recs, "net_approach_target")
    primary = (None if (sa is None or sb is None) else ("gt" if sa > sb else ("eq" if sa == sb else "lt")))
    if primary == "eq":
        primary = (None if (na is None or nb is None) else
                   ("gt_by_tiebreak" if na > nb else ("eq" if na == nb else "lt_by_tiebreak")))
    return {
        "a": a_name, "b": b_name, "n_pairs": len(a_recs),
        "wins": wins, "ties": ties, "losses": losses, "not_measured_pairs": notmeas,
        "sum_max_stage": {a_name: sa, b_name: sb},
        "sum_net_approach_target": {a_name: na, b_name: nb},
        "primary_verdict": primary,
        "a_greater_than_b": (None if primary is None else bool(primary in ("gt", "gt_by_tiebreak"))),
        "measurement_status": "measured" if primary is not None else "not_measured",
        "rows": rows,
        "gate": {"threshold": GATES["progress_gt_random"], "why": GATES["progress_gt_random_why"],
                 "pass": (None if primary is None else bool(primary in ("gt", "gt_by_tiebreak")))},
    }


def _dist(vals: list) -> dict:
    """跨集分布（**只**在有限值上算；空集 ⇒ `null` + `measurement_status='not_measured'`，不写 0）。"""
    v = [float(x) for x in vals if x is not None and np.isfinite(float(x))]
    if not v:
        return {"measurement_status": "not_measured", "n": 0, "n_missing_or_nonfinite": len(vals) - len(v),
                "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None, "std": None,
                "why": "没有有限读数 ⇒ `null`（三值纪律，裁定 88.3-1：不许写 0 顶替）"}
    a = np.asarray(v, dtype=np.float64)
    return {"measurement_status": "measured", "n": len(v), "n_missing_or_nonfinite": len(vals) - len(v),
            "min": round(float(a.min()), 4), "p25": round(float(np.percentile(a, 25)), 4),
            "median": round(float(np.median(a)), 4), "p75": round(float(np.percentile(a, 75)), 4),
            "max": round(float(a.max()), 4), "mean": round(float(a.mean()), 4),
            "std": (round(float(a.std(ddof=1)), 4) if len(v) > 1 else None)}


def cross_episode_timing_distribution(all_recs: dict, arms: list) -> dict:
    """**产出⑤「每步动作间隔」**（裁定 101.2 六项产出之一）的可核化 = 裁定 102.2-④ 的口径：
    **逐集** `wall_ms_per_ctrl_step` + **跨集**分布 + `budget_fraction` / `overload_flag`。

    三条硬规定照旧：
    - 裁定 75.5：`wall_ms_per_ctrl_step` 与 `amortized_inference_ms_per_ctrl_step` **必须分列**，
      两个口径**不得互搬**；`realtime_closed_loop_claim` 恒 `false`。
    - 裁定 75.4：仿真/离线里 34 ms/步是**软约束** ⇒ `budget_fraction > 1` **不判硬失败**，只置 `overload_flag`。
    - 裁定 102.2-④：intra-episode 的 max/P95/P99 **不在此报** ⇒ 登记为 `OPEN-STEP2-TIMING-PERCENTILES`
      （第 2 步前置、非阻塞）；standard_sync 下推理本就在关键路径上、控制器必然被阻塞。
    """
    per_arm: dict = {}
    for a in arms:
        recs = all_recs.get(a) or []
        rows = []
        for r in recs:
            t = r.get("timing_report") or {}
            lp = r.get("load_pair") or {}
            rows.append({"episode_index": int(r.get("episode_index")), "split": r.get("split"),
                         "direction": r.get("direction"), "seed": r.get("seed"),
                         "n_control_frames": t.get("n_control_frames"),
                         "per_step_budget_ms": t.get("per_step_budget_ms"),
                         "wall_ms_per_ctrl_step": t.get("wall_ms_per_ctrl_step"),
                         "amortized_inference_ms_per_ctrl_step": t.get("amortized_inference_ms_per_ctrl_step"),
                         "env_step_ms_per_ctrl_step": t.get("env_step_ms_per_ctrl_step"),
                         "observe_render_ms_per_ctrl_step": t.get("observe_render_ms_per_ctrl_step"),
                         "unitemized_other_ms_per_ctrl_step": t.get("unitemized_other_ms_per_ctrl_step"),
                         "budget_fraction": t.get("budget_fraction"),
                         "overload_flag": t.get("overload_flag"),
                         "queue_never_drained": t.get("queue_never_drained"),
                         "exec_mode": t.get("exec_mode"),
                         "loadavg_at_after": (lp.get("after") or {}).get("loadavg"),
                         "nr_throttled_delta": (lp.get("after") or {}).get("nr_throttled_delta")})
        per_arm[a] = {
            "n_episodes": len(rows),
            "per_episode": rows,
            "wall_ms_per_ctrl_step_distribution": _dist([x["wall_ms_per_ctrl_step"] for x in rows]),
            "amortized_inference_ms_distribution": _dist(
                [x["amortized_inference_ms_per_ctrl_step"] for x in rows]),
            "budget_fraction_distribution": _dist([x["budget_fraction"] for x in rows]),
            "n_overload_flag_true": sum(1 for x in rows if x["overload_flag"] is True),
            "n_overload_flag_not_measured": sum(1 for x in rows if x["overload_flag"] is None),
            "per_step_budget_ms": sorted({x["per_step_budget_ms"] for x in rows
                                          if x["per_step_budget_ms"] is not None}),
            "measurement_status": "measured" if rows else "not_measured",
        }
    budgets = sorted({x["per_step_budget_ms"] for a in per_arm.values() for x in a["per_episode"]
                      if x["per_step_budget_ms"] is not None})
    return {
        "rule": TIMING_OUTPUT_RULE,
        "satisfies_required_output_5": TIMING_OUTPUT_RULE["satisfies_required_output"],
        "caliber": "synchronous_blocking_serial（推理在关键路径上、与队列消费**零重叠**）",
        "listed_separately": ["wall_ms_per_ctrl_step", "amortized_inference_ms_per_ctrl_step"],
        "realtime_closed_loop_claim": False,
        "per_step_budget_ms_observed": budgets,
        "soft_constraint_not_a_hard_failure": ("裁定 75.4：`budget_fraction > 1` **不判硬失败**，"
                                               "只置 `overload_flag=true`；本块**不产生** findings"),
        "per_arm": per_arm,
        "deferred_open_item": OPEN_STEP2_TIMING_PERCENTILES,
        "pairing_rule": "裁定 46.4/53.6/85.7：每个延迟数字都带同集的 `loadavg` + `nr_throttled_delta`",
    }


def stage_rollout(args, out_dir: pathlib.Path, findings, reuse: dict, window) -> dict:
    import torch
    doc = base_doc("bc_step1_rollout_report", args, gpu_used=True, policy_executed=True)
    t0 = time.perf_counter()
    load_before = PBG.gpu_window_readings(extra={"phase": "rollout_before"})
    prereg = load_json(prereg_path(out_dir))
    sel = load_json(out_dir / SELECTION_NAME)
    train_rep = load_json(out_dir / "TRAIN_REPORT.json")
    ck_by_step = {int(c["step"]): c for c in (train_rep.get("checkpoints") or [])}
    if sel.get("measurement_status") != "measured":
        findings.add("selection_not_measured", verdict="RED", blocking=True, subject="checkpoint_selection",
                     evidence=sel, ruling="裁定 95.5-③", why="没有选中的 checkpoint ⇒ rollout 无主体臂")
        doc["measurement_status"] = "not_measured"
        write_json(out_dir / "ROLLOUT_REPORT.json", doc)
        return doc

    dsraw = PRE.read_dataset_arrays(REPO / PRE.P_DS)
    init = PRE.build_demo_initial_states({"ds": dsraw})
    if init["measurement_status"] != "measured":
        findings.add("demo_initial_states_incomplete", verdict="RED", blocking=True,
                     subject="demo_initial_states", evidence={k: v for k, v in init.items() if k != "rows"},
                     ruling="裁定 95.2 第 1 行（**从示范初态**）", why="40 条示范初态没提全 ⇒ 闭环初态不可信")
    rows_by_ep = {int(r["episode_index"]): r for r in init["rows"]}
    splits = [s.strip() for s in str(args.rollout_splits).split(",") if s.strip()]
    eps: list[dict] = []
    for sp in splits:
        for e in (TRAIN_EPISODES if sp == "train" else VAL_EPISODES):
            r = dict(rows_by_ep[e])
            r["split"] = sp
            r["box_xyz"] = r.get("box_rest_after_settle_xyz")
            if r["box_xyz"] is None:
                findings.add(f"box_rest_missing:ep{e}", verdict="RED", blocking=True,
                             subject="demo_initial_state", evidence={"episode_index": e}, ruling="—",
                             why="sidecar 缺 `box_rest_after_settle_xyz` ⇒ 该局初态写不出来")
                continue
            eps.append(r)
    arms = [a.strip() for a in str(args.rollout_arms).split(",") if a.strip()]
    # ── 裁定 102.2-③：`bc`+`injected_base`+`random`+`hold` **四臂必需**；`base_zeroshot` 可选、排最后 ──
    missing_required = [a for a in REQUIRED_ARMS if a not in arms]
    unknown_arms = [a for a in arms if a not in ARMS]
    opt_present = [a for a in OPTIONAL_ARMS if a in arms]
    optional_not_last = bool(opt_present and arms[-len(opt_present):] != opt_present)
    doc["arm_requirement_check"] = {
        "rule": ARM_REQUIREMENT_RULE, "arms_requested": arms,
        "required": list(REQUIRED_ARMS), "optional": list(OPTIONAL_ARMS),
        "missing_required": missing_required, "unknown_arms": unknown_arms,
        "optional_arms_present": opt_present, "optional_not_last": optional_not_last,
        "order_rule_satisfied": bool(not optional_not_last),
        "verdict": "GREEN" if not (missing_required or unknown_arms or optional_not_last) else "RED",
    }
    if missing_required:
        findings.add("required_arm_missing", verdict="RED", blocking=True, subject="rollout_arms",
                     evidence={"missing_required": missing_required, "arms_requested": arms,
                               "rule": ARM_REQUIREMENT_RULE},
                     ruling="裁定 102.2-③（四臂必需）",
                     why=("缺任一必需臂 ⇒ `max_stage==4` 无法归因（`injected_base`）/ 随机底不成立（`random`）/ "
                          "no-op 底不成立（`hold`）⇒ 不许出 Step 1 判词"))
    if unknown_arms:
        findings.add("unknown_arm_requested", verdict="RED", blocking=True, subject="rollout_arms",
                     evidence={"unknown_arms": unknown_arms, "known": sorted(ARMS)},
                     ruling="—", why="请求了未定义的臂 ⇒ 它的定义/不变量都没有预登记")
    if optional_not_last:
        findings.add("optional_arm_not_last", verdict="RED", blocking=False, subject="rollout_arms",
                     evidence={"arms_requested": arms, "optional_arms_present": opt_present,
                               "order_rule": ARM_REQUIREMENT_RULE["order_rule"]},
                     ruling="裁定 102.2-③（`base_zeroshot` 降为可选、**排最后**、且不得推迟报告）",
                     why=("可选臂排在必需臂之前 ⇒ 必需四臂的读数被推迟；不阻塞本臂出数，但**必须自报**"
                          "（`base_zeroshot` 复刻的 G3 `0/20` 已在案，属确认而非新信息）"))
    ctx = {
        "model_dirs": {
            "bc": {"dir": sel["selected_dir"], "rel_dir": sel.get("selected_rel_dir"),
                   "sha256_12": sel.get("selected_sha256_12"), "step": sel.get("selected_step"),
                   "sha_source": ("`TRAIN_REPORT.json` 保存时算的 sha256[:12]（不重算 7.25 GB；"
                                  "裁定 98.5：sha 是唯一约束性判据）")},
            "injected_base": {"dir": ck_by_step[0]["dir"], "rel_dir": ck_by_step[0].get("rel_dir"),
                              "sha256_12": ck_by_step[0].get("model_safetensors_sha256_12"), "step": 0,
                              "role": "**未微调**、只带 C2 stats 注入 ⇒ 把「接口修复」与「BC 微调」两个变量分开"},
        },
        "arm_labels": {"bc": "pi05_bc_step1_overfit", "injected_base": "pi05_injected_base_zero_finetune"},
        "arm_notes": {"bc": ARMS["bc"], "injected_base": ARMS["injected_base"]},
        "representation_version": reuse["stats"]["representation_version"],
        "base_weights_identity": S4B.weights_identity(pathlib.Path(args.weights_dir_resolved),
                                                     REPO / args.weights_receipt,
                                                     skip_rehash=bool(args.skip_weights_rehash)),
    }
    doc["arm_context"] = ctx
    from gym_aloha.constants import unnormalize_puppet_gripper_position as unorm

    ledger_path = out_dir / "ledger_step1_rollout.sqlite"
    ledger = FactLedger(ledger_path)
    all_recs: dict[str, list[dict]] = {}
    all_ff: dict[str, list] = {}
    try:
        for arm in arms:
            recs: list[dict] = []
            ffs: list = []
            factory = _arm_policy_factory(arm, args, reuse, ctx)
            for ep in eps:
                try:
                    rec, ff = run_episode_demo_init(arm=arm, ep=ep, args=args, policy=factory,
                                                    ledger=ledger, window=window, reuse=reuse,
                                                    out_dir=out_dir, unorm_fn=unorm)
                except Exception as exc:                                  # noqa: BLE001
                    import traceback
                    findings.add(f"episode_crash:{arm}:ep{ep['episode_index']}", verdict="RED", blocking=True,
                                 subject="episode_crash",
                                 evidence={"error": f"{type(exc).__name__}: {exc}",
                                           "traceback": traceback.format_exc()[-3000:]},
                                 ruling="—", why="一局崩了 ⇒ 该臂不完整，不许当绿交付")
                    print(f"[rollout:{arm}] ep{ep['episode_index']} CRASH {type(exc).__name__}: {exc}",
                          flush=True)
                    continue
                recs.append(rec)
                ffs.append(ff)
                write_json(out_dir / f"episode_{arm}_{rec['direction']}_{rec['episode_index']:03d}.json", rec)
                if not rec["initial_state"]["readback_ok"]:
                    findings.add(f"demo_init_readback_failed:{arm}:ep{rec['episode_index']}", verdict="RED",
                                 blocking=True, subject="demo_initial_state_reproduce",
                                 evidence=rec["initial_state"], ruling="裁定 95.2 第 1 行",
                                 why=("示范初态没复现出来 ⇒ 该局既不算成功也不算失败，"
                                      "整臂的「从示范初态」前提不成立"))
                rend = rec["renderer_class_three_points"]["points"]
                bad_pts = [k for k, v in rend.items()
                           if args.renderer_must_contain and isinstance((v or {}).get("renderer_class"), str)
                           and args.renderer_must_contain.lower() not in str(v["renderer_class"]).lower()]
                nul = [k for k, v in rend.items() if (v or {}).get("renderer_class") is None]
                if bad_pts or nul:
                    findings.add(f"renderer_not_{args.renderer_must_contain}:{arm}:ep{rec['episode_index']}",
                                 verdict="RED", blocking=bool(args.renderer_strict),
                                 subject="renderer_backend",
                                 evidence={"points": rend, "must_contain": args.renderer_must_contain,
                                           "null_points": nul},
                                 ruling="补单四 §三 + 先落腿结论 9（rollout 应走 egl/nvidia_gpu 与训练数据同口径）",
                                 why=("渲染后端与训练数据采集口径不一致 ⇒ 视觉分布不同源，"
                                      "该局的数字不能与训练臂并列"))
                p = rec["progress"]
                o = rec["outcome"]
                print(f"[rollout:{arm}] ep{rec['episode_index']:02d} {rec['direction']} seed={rec['seed']} "
                      f"split={rec['split']} frames={rec['n_control_frames']} stop={rec['stop_reason']} "
                      f"max_stage={p.get('max_stage')} approach={p.get('net_approach_target')} "
                      f"outcome={o.get('outcome_class')} geom={o.get('geometric_success')} "
                      f"initdiff={rec['initial_state']['readback_maxdiff']} "
                      f"renderer_end={rec['renderer_class_three_points']['at_end']} "
                      f"wall={rec['wall_s']}s", flush=True)
            all_recs[arm] = recs
            all_ff[arm] = ffs
            try:
                factory.free()
            except Exception:                                             # noqa: BLE001
                pass
            if arm in ("bc", "injected_base", "base_zeroshot"):
                try:
                    torch.cuda.empty_cache()
                except Exception:                                         # noqa: BLE001
                    pass
    finally:
        try:
            ledger_stats = ledger.stats()
        except Exception as exc:                                          # noqa: BLE001
            ledger_stats = {"error": f"{type(exc).__name__}: {exc}"}
        ledger.close()

    # ---- 汇总：每种子单独报数（裁定 95.5 / 补单二-§七）+ 正反向分别报 ----
    def per_arm_table(recs):
        by_dir: dict = {}
        per_seed = []
        for r in recs:
            d = r["direction"]
            by_dir.setdefault(d, []).append(r)
            o, p, ff = r["outcome"], r["progress"], r["four_fields"]
            per_seed.append({
                "episode_index": r["episode_index"], "seed": r["seed"], "direction": d,
                "manifest_direction": r["manifest_direction"], "split": r["split"],
                "ep_id_demo": r["ep_id_demo"], "task_text": r["task_text"],
                "task_success": ff.get("task_success"),
                "geometric_success": o.get("geometric_success"),
                "outcome_class": o.get("outcome_class"),
                "max_stage": p.get("max_stage"),
                "net_approach_target": p.get("net_approach_target"),
                "max_height_over_table_z_ref_m": p.get("max_height_over_table_z_ref_m"),
                "max_hold_steps": p.get("max_hold_steps"),
                "measurement_reliable": ff.get("measurement_reliable"),
                "interface_conformant": ff.get("interface_conformant"),
                "out_of_distribution": ff.get("out_of_distribution"),
                "n_control_frames": r["n_control_frames"], "stop_reason": r["stop_reason"],
                "initial_state_readback_maxdiff": r["initial_state"]["readback_maxdiff"],
                "harness_takeover_counters": r["harness_takeover_counters"],
                "wall_ms_per_ctrl_step": (r["timing_report"] or {}).get("wall_ms_per_ctrl_step"),
                "loadavg_at_after": (r["load_pair"] or {}).get("after", {}).get("loadavg"),
                "nr_throttled_delta": (r["load_pair"] or {}).get("nr_throttled_delta"),
            })
        out_by_dir = {}
        for d, rs in by_dir.items():
            n = len(rs)
            out_by_dir[d] = {
                "n_episodes": n,
                "task_success_count": sum(1 for r in rs if r["four_fields"].get("task_success") is True),
                "task_success_not_measured": sum(1 for r in rs if r["four_fields"].get("task_success") is None),
                "geometric_success_count": sum(1 for r in rs if r["outcome"].get("geometric_success") is True),
                "max_stage_hist": {str(k): sum(1 for r in rs if (r["progress"].get("max_stage")) == k)
                                   for k in sorted(PROGRESS_LADDER)},
                "sum_max_stage": round(sum(float(r["progress"].get("max_stage") or 0) for r in rs), 4),
                "mean_net_approach_target": (
                    round(float(np.mean([r["progress"].get("net_approach_target") for r in rs
                                         if r["progress"].get("net_approach_target") is not None])), 6)
                    if any(r["progress"].get("net_approach_target") is not None for r in rs) else None),
                "ood_true_count": sum(1 for r in rs if r["four_fields"].get("out_of_distribution") is True),
                "ood_not_measured_count": sum(1 for r in rs if r["four_fields"].get("out_of_distribution") is None),
                "interface_conformant_false_count": sum(
                    1 for r in rs if r["four_fields"].get("interface_conformant") is False),
                "measurement_reliable_false_count": sum(
                    1 for r in rs if r["four_fields"].get("measurement_reliable") is False),
                "seeds": sorted({int(r["seed"]) for r in rs}),
                "capability_stats": VR.aggregate_capability_stats(
                    [r["four_fields"] for r in rs]),
            }
        return {"by_direction": out_by_dir, "per_seed": per_seed, "n_episodes": len(recs)}

    tables = {a: per_arm_table(all_recs.get(a, [])) for a in arms}
    # ── 裁定 102.2-①：**出场判据牙**。裁定 99.3：先在合成夹具上干跑（证明它有分辨力），再对真读数出判词 ──
    cl_selftest = closed_loop_reproduction_selftest()
    if not cl_selftest["all_bite"]:
        findings.add("closed_loop_reproduction_tooth_selftest_not_bite", verdict="RED", blocking=True,
                     subject="exit_criterion_tooth",
                     evidence={k: v for k, v in cl_selftest.items() if k != "rows"},
                     ruling="裁定 93.8 / 99.3（只装一向不许报绿；预登记判据必须先在对象上干跑）",
                     why="出场判据牙的两向变异体没全咬 ⇒ 它没有分辨力 ⇒ 不许拿它出 Step 1 判词")
    cl_tooth = closed_loop_reproduction_tooth(tables, arms_run=arms)
    if cl_tooth["verdict"] != "GREEN":
        findings.add("closed_loop_reproduction_not_met", verdict="RED", blocking=True,
                     subject="step1_exit_criterion",
                     evidence={k: v for k, v in cl_tooth.items()
                               if k not in ("nuclearization", "why_blocking", "capability_note")},
                     ruling="裁定 102.2-① · 裁定 101.2（用户 Step 1 验收标准第 2 条）",
                     why=cl_tooth["why_blocking"])
    timing_block = cross_episode_timing_distribution(all_recs, arms)
    comparisons: dict = {}
    if "bc" in all_recs and "random" in all_recs:
        comparisons["bc_vs_random"] = paired_comparison(all_recs["bc"], all_recs["random"],
                                                        a_name="bc", b_name="random")
        if comparisons["bc_vs_random"]["gate"]["pass"] is not True:
            findings.add("progress_not_gt_random", verdict="RED", blocking=False, subject="progress_vs_random",
                         evidence={**{k: v for k, v in comparisons["bc_vs_random"].items() if k != "rows"},
                                   "downgraded_by": "裁定 102.2-①",
                                   "former_blocking": True,
                                   "now_role": GATES["progress_gt_random_role"],
                                   "role_why": GATES["progress_gt_random_role_why"]},
                         ruling="裁定 95.2 第 1 行 · **裁定 102.2-① 降级**",
                         why=("从示范初态闭环执行的推进度没有 > 随机基线。**裁定 102.2-①：本条已从「唯一阻塞牙」"
                              "降为诊断读数**（`blocking=false`）—— 出场判据换成「至少一条正向和一条反向轨迹"
                              "能从示范初态闭环复现」（`A2T6`）。阈值与 `tiebreak_order` **原样保留**，"
                              "读数照实报，只是不再单独决定 Step 1 出场"))
    if "bc" in all_recs and "hold" in all_recs:
        comparisons["bc_vs_hold"] = paired_comparison(all_recs["bc"], all_recs["hold"],
                                                      a_name="bc", b_name="hold")
    if "bc" in all_recs and "injected_base" in all_recs:
        comparisons["bc_vs_injected_base"] = paired_comparison(all_recs["bc"], all_recs["injected_base"],
                                                               a_name="bc", b_name="injected_base")
    if "bc" in all_recs and "base_zeroshot" in all_recs:
        comparisons["bc_vs_base_zeroshot"] = paired_comparison(all_recs["bc"], all_recs["base_zeroshot"],
                                                               a_name="bc", b_name="base_zeroshot")
    takeover = {}
    for a, recs in all_recs.items():
        takeover[a] = {"n_episodes": len(recs),
                       "sum_queue_drain_events": sum(r["harness_takeover_counters"]["n_queue_drain_events"] for r in recs),
                       "sum_late_records": sum(r["harness_takeover_counters"]["n_late_records"] for r in recs),
                       "sum_sync_overload_records": sum(r["harness_takeover_counters"]["n_sync_overload_records"] for r in recs),
                       "sum_chunks_committed": sum(int(r["harness_takeover_counters"]["n_chunks_committed"] or 0) for r in recs),
                       "exec_mode": VR.EXEC_MODE_STANDARD_SYNC, "prime_mode": VR.PRIME_MODE_NONE,
                       "interpretation": ("第 1 步的运行时**没有**接管通路（standard_sync + prime_mode=none）；"
                                          "这里报的是三个计数器的实测和，用来证明「0 次接管」是**测出来的**"
                                          "而不是写死的（裁定 50.1/72）")}
    doc.update({
        "measurement_status": "measured" if any(all_recs.values()) else "not_measured",
        "episodes_planned": [{"episode_index": e["episode_index"], "seed": e["seed"], "split": e["split"],
                              "env_direction": e["env_direction"], "ep_id": e["ep_id"]} for e in eps],
        "arms": {a: {"definition": ARMS.get(a, a), "n_episodes": len(all_recs.get(a, []))} for a in arms},
        "arm_delta_table": ARM_DELTA_TABLE,
        "per_arm_tables": tables,
        "exit_criterion_closed_loop_reproduction": cl_tooth,
        "exit_criterion_tooth_selftest": cl_selftest,
        "exit_criterion_dry_run_before_real_reading": (
            "裁定 99.3：`A2T6` **先在合成夹具上干跑**（`exit_criterion_tooth_selftest`，7 例两向）"
            "证明它有分辨力，**再**对真读数出判词（`exit_criterion_closed_loop_reproduction`）；两次读数都落盘"),
        "capability_stats_overall": {a: VR.aggregate_capability_stats(all_ff.get(a, [])) for a in arms},
        "paired_comparisons": comparisons,
        "harness_takeover": takeover,
        "progress_metric": PROGRESS_METRIC_DEFINITION,
        "progress_gt_random_role": GATES["progress_gt_random_role"],
        "progress_gt_random_role_why": GATES["progress_gt_random_role_why"],
        "random_baseline": RANDOM_BASELINE_DEFINITION,
        "timing_per_ctrl_step": timing_block,
        "ledger": {"path": str(ledger_path), "sha256_12": sha12(ledger_path), "stats": ledger_stats},
        "timing": {"total_wall_s": round(time.perf_counter() - t0, 2),
                   "load_pair": {"before": load_before,
                                 "after": PBG.gpu_window_readings(extra={"phase": "rollout_after"})},
                   "pairing_rule": "裁定 46.4/53.6/85.7：延迟/吞吐数字成对带 loadavg(3 点)+nr_throttled"},
        "four_fields_ruling": "裁定 95.3-①：四字段分开记；`out_of_distribution` **只标注不剔除**",
        "open_items": OPEN_ITEMS_STEP1,
    })
    ident = write_json(out_dir / "ROLLOUT_REPORT.json", doc)
    print(f"[rollout] arms={arms} episodes/arm={[len(all_recs.get(a, [])) for a in arms]} "
          f"**exit_criterion**={cl_tooth['verdict']}(fwd={cl_tooth['n_forward_geometric_success']}/"
          f"rev={cl_tooth['n_reverse_geometric_success']}, status={cl_tooth['measurement_status']}) "
          f"tooth_selftest={cl_selftest['n_bite']}/{cl_selftest['n_rows']} "
          f"bc_vs_random(诊断)={comparisons.get('bc_vs_random', {}).get('primary_verdict')} "
          f"artifact={ident['path']} {ident['sha256_12']}", flush=True)
    return doc


# ══════════════════════════ ⑪ report（裁定 95.6 的**六问**）══════════════
# ══════ 验收标准 ③ 的取证块：消费 R1/R2 的**既有判词件**（裁定 101.2：R1/R2 并入 Step 1 的产出③④）══════
CRITERION_3_RULE = {
    "question_verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM[2],
    "key_words": ("判的是「有没有**未解释**的**系统性**偏移」，**不是**「有没有例外行」—— 这两个问题不同，"
                  "混起来就会把探针假象读成数据错位（裁定 95.3-②：机制必须由对照证明，不靠一致的故事）"),
    "pass_iff": [
        "R1（臂侧 12 维 off-by-one 排除）`verdict == GREEN`",
        "R2 的例外**不是系统性错位**：按 R2 **自己预登记**的 `systematic_gripper_offbyone_iff` 判 —— "
        "`n_exception_frames_with_persistent_shifted_argmin / n_unique_exception_frames < 0.5`",
        "R2 的聚合与逐事件排名仍然 `aligned` 第一（`n_events_aggregate_not_aligned_first == 0` "
        "∧ 全局聚合 `aligned_is_best == true`）",
        "R2 的植入 ±1 负对照全翻（⇒ 上面那条「aligned 第一」不是尺子坏了）",
    ],
    "does_not_whitewash": [
        "**R2 的行级 verdict = RED 照旧保留**（预登记判据不放宽；14/102 高判别行的 margin 例外就是例外）",
        "R2 的 `exception_attribution.classification` **照抄实测值**，A2 不改写、不升格",
        "R2 那条 RED 的**处置权在 D**（补单七 §三 / 裁定 102.2）",
    ],
    "three_valued": "任一件不在盘 / 字段缺失 ⇒ `not_measured` + `pass=null`，**不猜「应该绿」**（裁定 88.3-1）",
}


def _safe_get(d, path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def alignment_evidence_block(args) -> dict:
    """产出③（对齐取证 = R1）与产出④（夹爪转变帧误差 = R2）的证据块。**A2 不重算任何判据**：
    只读 R1/R2 已落盘的判词件与锚定探针件，按**预登记的规则**（`CRITERION_3_RULE`）归类。"""
    out: dict = {"rule": CRITERION_3_RULE, "recomputes_nothing": True,
                 "note": ("裁定 101.2：R1/R2 不再是上卡前的独立探针，**改为并入 Step 1 的产出列**"
                          "（R2 = ④ 夹爪转变帧误差；R1 = ③ 里「没有未解释的系统性偏移」这一条的取证）")}
    p_r1r2 = pathlib.Path(args.r1r2_verdict_json)
    if not p_r1r2.is_absolute():
        p_r1r2 = REPO / p_r1r2
    p_probe = pathlib.Path(args.r1r2_anchor_probe_json)
    if not p_probe.is_absolute():
        p_probe = REPO / p_probe
    out["r1r2_verdict_artifact"] = identity(str(p_r1r2.relative_to(REPO)) if str(p_r1r2).startswith(str(REPO))
                                            else str(p_r1r2))
    out["anchor_probe_artifact"] = identity(str(p_probe.relative_to(REPO)) if str(p_probe).startswith(str(REPO))
                                            else str(p_probe))
    if not p_r1r2.exists():
        out.update({"measurement_status": "not_measured", "pass": None,
                    "why": f"R1/R2 判词件不在盘：{p_r1r2} ⇒ 不猜、不代算"})
        return out
    d = load_json(p_r1r2)
    r1 = _safe_get(d, "legs.R1_arm12_offbyone_exclusion") or {}
    r2 = _safe_get(d, "legs.R2_grip2_transition_alignment") or {}
    att = _safe_get(r2, "measured.exception_attribution") or {}
    n_uniq = att.get("n_unique_exception_frames")
    n_persist = att.get("n_exception_frames_with_persistent_shifted_argmin")
    frac_persist = (None if not n_uniq else round(float(n_persist or 0) / float(n_uniq), 6))
    checks = {
        "c1_r1_green": (None if not r1 else bool(r1.get("verdict") == "GREEN")),
        "c2_not_systematic_by_r2_own_preregistered_rule": (
            None if frac_persist is None
            else bool(frac_persist < 0.5)),
        "c3_aggregate_and_event_rankings_aligned_first": (
            None if not r2 else bool(
                _safe_get(r2, "measured.n_events_aggregate_not_aligned_first") == 0
                and _safe_get(r2, "measured.global_aggregate_grip2_all_rows.aligned_is_best") is True
                and _safe_get(r2, "measured.global_aggregate_grip2_high_rows.aligned_is_best") is True)),
        "c4_planted_controls_still_flip": (
            None if not r2 else bool(
                _safe_get(r2, "measured.planted_control_grip2.flipped_everywhere") is True
                and _safe_get(r1, "measured.planted_control_arm12.flipped_everywhere") is True)),
    }
    all_measured = all(v is not None for v in checks.values())
    passed = (None if not all_measured else all(bool(v) for v in checks.values()))
    out.update({
        "measurement_status": "measured" if all_measured else "not_measured",
        "r1_arm12_offbyone_exclusion": {
            "verdict": r1.get("verdict"), "measurement_status": r1.get("measurement_status"),
            "red_codes": r1.get("red_codes"),
            "row_judgment": _safe_get(r1, "measured.arm12_row_judgment"),
            "planted_control": {k: v for k, v in (_safe_get(r1, "measured.planted_control_arm12") or {}).items()
                                if k != "offenders_head"},
            "two_box_pose_coverage": _safe_get(r1, "measured.two_box_pose_coverage"),
            "aggregate_high_rows": _safe_get(r1, "measured.aggregate_arm12_high_rows"),
            "role": "**产出③ 的臂侧取证**：臂 12 维的 off-by-one（H2）在该帧集上被排除",
        },
        "r2_grip2_transition_alignment": {
            "verdict": r2.get("verdict"), "measurement_status": r2.get("measurement_status"),
            "red_codes": r2.get("red_codes"),
            "row_judgment": {k: v for k, v in (_safe_get(r2, "measured.grip2_row_judgment") or {}).items()
                             if k != "exceptions_head"},
            "gripper_transition_frame_error": {
                "role": "**产出④「夹爪转变帧误差」**（裁定 101.2：R2 = 产出④）",
                "caliber": ("夹爪转变点 ±3 帧窗口内，`grip2`(dim6/dim13) 的 `aligned` vs `j±1` vs `hold` "
                            "四臂逐行 L2 误差 + 事件内聚合 + 全局聚合"),
                "aggregate_all_rows": _safe_get(r2, "measured.global_aggregate_grip2_all_rows"),
                "aggregate_high_rows": _safe_get(r2, "measured.global_aggregate_grip2_high_rows"),
                "n_events_aggregate_not_aligned_first": _safe_get(r2, "measured.n_events_aggregate_not_aligned_first"),
                "planted_control": {k: v for k, v in (_safe_get(r2, "measured.planted_control_grip2") or {}).items()
                                    if k != "offenders_head"},
                "warm_vs_cold": _safe_get(r2, "measured.warm_vs_cold"),
            },
            "exception_attribution_verbatim_from_run": {
                "classification": att.get("classification"),
                "n_unique_exception_frames": n_uniq,
                "n_exception_frames_pass_at_Kmax": att.get("n_exception_frames_pass_at_Kmax"),
                "frac_exception_frames_pass_at_Kmax": att.get("frac_exception_frames_pass_at_Kmax"),
                "median_aligned_err_decay_K0_over_Kmax": att.get("median_aligned_err_decay_K0_over_Kmax"),
                "n_exception_frames_with_persistent_shifted_argmin": n_persist,
                "frac_persistent_shifted_argmin": frac_persist,
                "conditions_for_probe_qvel_artifact": att.get("conditions_for_probe_qvel_artifact"),
                "conditions_for_systematic_offbyone": att.get("conditions_for_systematic_offbyone"),
                "anchor_tooth": att.get("anchor_tooth"),
                "verdict_untouched": att.get("verdict_untouched"),
                "a2_does_not_rewrite_this": ("**照抄**：run2 的归类实测值就是 `classification` 这一行，"
                                             "A2 不因后面那个探针把它升格成 `probe_qvel_artifact…`"
                                             "（那是**事后改判据**）"),
            },
        },
        "checks": checks,
        "pass": passed,
        "why_not_pass": (None if passed is not False else
                         [k for k, v in checks.items() if v is not True]),
        "anchor_probe_additional_evidence": (
            None if not p_probe.exists() else {
                "role": ("**run2 之后另取的对照证据**，只用于解释「锚定牙为什么在 ep0 f129 失锚」，"
                         "**不改** R2 的 verdict / red_codes / classification"),
                "identity": out["anchor_probe_artifact"],
                "all_V2_equiv_V3": _safe_get(load_json(p_probe), "summary.all_V2_equiv_V3"),
                "failing_anchor_gap_explained": _safe_get(load_json(p_probe), "summary.failing_anchor_gap_explained"),
                "failing_anchor_quat_spread": _safe_get(load_json(p_probe), "summary.failing_anchor_quat_spread"),
                "control_anchor_quat_spreads": _safe_get(load_json(p_probe), "summary.control_anchor_quat_spreads"),
                "mechanism": ("`PRE._init_env_to_state` 只写方块自由关节的 **xyz**（`qpos[16:19]`）、"
                              "**不写四元数**（`qpos[19:23]`）⇒ cold 模每臂重写一次初态时，方块姿态继承"
                              "上一臂 step 之后的值（**受控变量之外的 carry-over**）；warm K=0 只写一次、"
                              "之后 `restore_phys` 钉住整份 qpos ⇒ 两条路径分叉。方块静止时四元数不变"
                              "⇒ 6/7 锚点差 = 0.0；ep0 f129 是释放帧（`nearest_before` 位姿已 stale 4.65 cm、"
                              "方块在翻转）⇒ 四元数逐臂漂 7.6e-3、两路差 3.6e-3"),
                "single_variable_control": ("V2（钉住四元数的 cold）≡ V3（warm K=0）差 **0.000e+00**；"
                                            "V1（现行 cold）≢ V3 差 3.627e-03；两个静止帧对照四元数漂 0.0、"
                                            "三臂全等 ⇒ 机制由**对照**证明，不是故事"),
                "does_not_change_r2_verdict": True,
                "self_defect_registered": ("这是**探针层**的一个未受控初值（登记为 A2 自报缺陷 D4），"
                                           "**不是**动作/时间错位；修法属先落腿件 `_init_env_to_state` 的口径，"
                                           "该件本轮**只读复用、一个字节不改** ⇒ 修法与是否重跑由 D 裁"),
                "step1_rollout_not_affected": ("Step 1 的闭环初态写在**示范 frame-0**（方块静止在桌面、"
                                               "且用 sidecar 的 `box_rest_after_settle_xyz`）⇒ 四元数稳定，"
                                               "本缺陷不影响 Step 1 的初态复现（L9 已自证 `maxdiff=0.0`）"),
                "step1_rollout_not_affected_superseded_by": (
                    "`step1_rollout_effect_not_measured`（裁定 104.2-（d）：旧键**原文保留、不删**，"
                    "但**不再被引用为结论**）。作废理由：旧键的证据是 L9 的 `maxdiff=0.0`，而 L9 与回读牙"
                    "都是 **14 维**口径、不含方块位姿 ⇒ **证据作用域 ⊊ 结论作用域**；且「方块静止在桌面」"
                    "本身当时**未测**（红线 `absence_of_measurement_is_not_measurement_of_absence`）"),
                "step1_rollout_effect_not_measured": {
                    "measurement_status_source": "只读 CPU-only 测量件，不在本件里估",
                    "status": box_quat_defect_status(),
                    "defect_id": "A2-SD-11_step1_rollout_not_affected_overreach（Ⅰ 类 "
                                 "`demo_init_box_quat_not_written` 的对象侧，裁定 104.2-（c）（d））",
                    "ruling": "裁定 104.2 · 红线 `absence_of_measurement_is_not_measurement_of_absence`",
                },
            }),
        "disposition_authority": "D（R2 的 RED 与锚定牙失锚的处置权都不在 A2）",
    })
    return out


def stage_report(args, out_dir: pathlib.Path, findings, reuse: dict) -> dict:
    doc = base_doc("bc_step1_result", args)
    prereg = load_json(prereg_path(out_dir)) if prereg_path(out_dir).exists() else None
    adm_p = sorted(out_dir.glob("BC_ADMISSION_STEP1_*.json"))
    adm = load_json(adm_p[-1]) if adm_p else None
    train_rep = load_json(out_dir / "TRAIN_REPORT.json") if (out_dir / "TRAIN_REPORT.json").exists() else None
    roll = load_json(out_dir / "ROLLOUT_REPORT.json") if (out_dir / "ROLLOUT_REPORT.json").exists() else None
    sel = load_json(out_dir / SELECTION_NAME) if (out_dir / SELECTION_NAME).exists() else None
    probe = load_json(out_dir / PROBE_NAME) if (out_dir / PROBE_NAME).exists() else None

    doc["gpu_used"] = bool(train_rep or roll)
    doc["policy_executed"] = bool(roll and roll.get("measurement_status") == "measured")
    doc["inputs"] = {
        "admission": (None if adm is None else {"admitted": adm.get("admitted"),
                                                "path": str(adm_p[-1]), "sha256_12": sha12(adm_p[-1])}),
        "pre_registration": (None if prereg is None else {"path": str(prereg_path(out_dir)),
                                                          "sha256_12": sha12(prereg_path(out_dir)),
                                                          "version": (2 if prereg_path(out_dir).name == PREREG_V2_NAME else 1),
                                                          "append_not_overwrite": True}),
        "probe": (None if probe is None else {"chosen": (probe.get("probe") or {}).get("chosen"),
                                              "sha256_12": sha12(out_dir / PROBE_NAME)}),
        "train_report": (None if train_rep is None else {"sha256_12": sha12(out_dir / "TRAIN_REPORT.json")}),
        "checkpoint_selection": sel,
        "rollout_report": (None if roll is None else {"sha256_12": sha12(out_dir / "ROLLOUT_REPORT.json")}),
    }

    lg = (train_rep or {}).get("loss_gate") or {}
    am = ((train_rep or {}).get("action_match") or {}).get("selected") or {}
    cmp_rand = ((roll or {}).get("paired_comparisons") or {}).get("bc_vs_random") or {}
    cmp_ib = ((roll or {}).get("paired_comparisons") or {}).get("bc_vs_injected_base") or {}
    cmp_b0 = ((roll or {}).get("paired_comparisons") or {}).get("bc_vs_base_zeroshot") or {}
    tables = (roll or {}).get("per_arm_tables") or {}
    takeover = (roll or {}).get("harness_takeover") or {}

    def dirnum(arm: str, d: str, key: str):
        t = (tables.get(arm) or {}).get("by_direction", {}).get(d) or {}
        return t.get(key)

    # ── Q4：失败主要发生在哪一步（用**预登记的推进度阶梯**定位，不新造口径）──
    stall: dict = {"measurement_status": "not_measured"}
    if roll:
        per = ((tables.get("bc") or {}).get("per_seed")) or []
        fails = [r for r in per if r.get("task_success") is not True]
        hist: dict = {}
        for r in fails:
            k = r.get("max_stage")
            hist[str(k)] = hist.get(str(k), 0) + 1
        stall = {
            "measurement_status": "measured" if per else "not_measured",
            "n_bc_episodes": len(per), "n_bc_not_task_success": len(fails),
            "stall_stage_hist": hist,
            "stall_stage_hist_reading": {str(k): PROGRESS_LADDER.get(int(k), "?") for k in hist},
            "dominant_stall_stage": (max(hist, key=lambda k: hist[k]) if hist else None),
            "dominant_stall_stage_reading": (PROGRESS_LADDER.get(int(max(hist, key=lambda k: hist[k])))
                                             if hist else None),
            "ladder": PROGRESS_LADDER,
            "note": ("「哪一步」= 推进度阶梯上**停住的那一档**（0 未接触 / 1 源侧接触 / 2 离桌 / "
                     "3 交接侧到位 / 4 C2 几何成功）。逐局的 C2 `reasons` 原文见各 `episode_bc_*.json` 的 "
                     "`final_judgment_reasons`（判定层归 C2，A2 不重算、不改写）"),
        }

    six = {
        "artifact": "bc_step1_six_questions",
        "ruling": "裁定 95.6：每轮日报**优先只回答**这六问（取代散文式日报）",
        "as_of": now_iso(),
        "capability_claim": False,
        "success_rate_column": SUCCESS_RATE_COLUMN,
        "success_rate_column_note": SUCCESS_RATE_COLUMN_NOTE,
        "policy_executed": doc["policy_executed"],
        "questions": [
            {
                "n": 1, "q": "本轮验证了什么假设？",
                "answer": ("**第 1 步的假设（裁定 95.2 第 1 行原文）**：「数据能否被当前模型学到？」—— "
                           "即在 formal-40 的 4 集小量双向示范上做 BC **过拟合**，π₀.₅（lerobot 0.4.4 实现）"
                           "能否把这套数据的动作学下来，并在**从示范初态**闭环执行时表现出超过随机基线的推进度。"
                           "**它不是**「能力是否可重复」（那是第 2 步）、也**不是**「Harness 是否损害基础策略」"
                           "（第 3 步）。上层核心问题原文：" + CORE_QUESTION_VERBATIM),
                "measurement_status": "measured",
                "not_tested_here": ["能力可重复性（≥3 种子，第 2 步）", "新物体初始状态的泛化（第 2 步）",
                                    "标准执行 vs 后半段调度的配对比较（第 3 步）",
                                    "受限脚本恢复（第 4 步）", "纠正数据（第 5 步）", "BC vs BC+RL（第 6 步）"],
                "limits": [MORPHOLOGY_SCOPE_CAVEAT, BLIND_DIM_CAVEAT],
            },
            {
                "n": 2, "q": "相比哪个固定基线、只改了什么？",
                "answer": ("**固定基线 = `base_zeroshot`**（G3 那一臂的复刻：base compat 目录、feature shape=32、"
                           "无 normalizer stats ⇒ `stats_version=NONE` ⇒ runtime 硬隔离 td/bc 资格）。"
                           "从基线到主体臂**分两跳**，每跳只改一个变量（见 `arm_delta_table`）："
                           "① `base_zeroshot → injected_base`：只改接口（注入 C2 的唯一一档 stats + shape 32→14，"
                           "**权重一字节未动**）；② `injected_base → bc`：只改权重（在 train split 4 集上 BC 微调）。"
                           "另有两条无模型对照：`random`（裁定点名的随机基线）与 `hold`（G3 的 no-op 零假设）。"
                           "**所有臂共同不变量**：standard_sync + prime_mode=none + n_replan=25 + H=50、"
                           "C2 的判定层、示范初态、egl 渲染、morphology。"),
                "measurement_status": "measured" if roll else "not_measured",
                "evidence": {"arm_delta_table": ARM_DELTA_TABLE,
                             "arms": (roll or {}).get("arms"),
                             "bc_vs_base_zeroshot": {k: v for k, v in cmp_b0.items() if k != "rows"},
                             "bc_vs_injected_base": {k: v for k, v in cmp_ib.items() if k != "rows"},
                             "invariants": ARM_DELTA_TABLE.get("所有臂共同不变量")},
            },
            {
                "n": 3, "q": "正反向独立成功率分别多少？",
                "answer": (None if not roll else {
                    "caliber": ("`task_success` **只**取自 C2 的几何判定（`judge_from_facts` 的 "
                                "`outcome_class=='success'`），A2 不重算；**每种子单独报数**（不许只报均值、"
                                "不许挑最高），正反向**分别**报（裁定 95.2 第 2 行 / 95.5 / 补单二-§七）"),
                    "forward_right_to_left": {a: {"n": dirnum(a, "right_to_left", "n_episodes"),
                                                  "task_success_count": dirnum(a, "right_to_left", "task_success_count"),
                                                  "geometric_success_count": dirnum(a, "right_to_left", "geometric_success_count"),
                                                  "max_stage_hist": dirnum(a, "right_to_left", "max_stage_hist"),
                                                  "ood_true_count": dirnum(a, "right_to_left", "ood_true_count"),
                                                  "seeds": dirnum(a, "right_to_left", "seeds")}
                                              for a in tables},
                    "reverse_left_to_right": {a: {"n": dirnum(a, "left_to_right", "n_episodes"),
                                                  "task_success_count": dirnum(a, "left_to_right", "task_success_count"),
                                                  "geometric_success_count": dirnum(a, "left_to_right", "geometric_success_count"),
                                                  "max_stage_hist": dirnum(a, "left_to_right", "max_stage_hist"),
                                                  "ood_true_count": dirnum(a, "left_to_right", "ood_true_count"),
                                                  "seeds": dirnum(a, "left_to_right", "seeds")}
                                              for a in tables},
                    "per_seed_table": {a: (tables.get(a) or {}).get("per_seed") for a in tables},
                    "ood_ratio_reported_separately": {a: ((roll.get("capability_stats_overall") or {}).get(a) or {}).get("ood_ratio")
                                                      for a in tables},
                    "not_a_capability_claim": RULING_46,
                    "scope_limit": MORPHOLOGY_SCOPE_CAVEAT,
                }),
                "measurement_status": "measured" if roll else "not_measured",
            },
            {
                "n": 4, "q": "失败主要发生在哪一步？",
                "answer": stall,
                "measurement_status": stall.get("measurement_status", "not_measured"),
            },
            {
                "n": 5, "q": "Harness 接管了多少次？",
                "answer": {
                    "n_takeovers": {a: (t.get("sum_queue_drain_events", 0) + t.get("sum_late_records", 0))
                                    for a, t in takeover.items()},
                    "counters": takeover,
                    "why_zero_by_construction_and_still_measured": (
                        "裁定 95.3-④：第 1–2 步**一律用标准同步动作块执行**，运行时里根本没有接管通路"
                        "（`exec_mode=standard_sync` + `prime_mode=none`）⇒ 接管次数**构造上**为 0。"
                        "但本件仍然把三个计数器（`queue_drain_events` / `late_records` / "
                        "`sync_overload_records`）逐局实测并求和报出来，让「0」是**测出来的**而不是写死的"
                        "（裁定 50.1/72：写死的字符串一律无效）。`sync_overload_records` 非 0 **不是**接管"
                        "（同步阻塞下推理占墙钟、仿真时间不推进 ⇒ 没有过期的槽可作废，裁定 75.4 的软约束事实）"),
                    "harness_second_half_scheduling_not_used_in_step1": True,
                    "paired_comparison_is_step3": "裁定 95.2 第 3 步：同 ckpt、同初态、同 seed 序列的配对比较",
                },
                "measurement_status": "measured" if takeover else "not_measured",
            },
            {
                "n": 6, "q": "更新后关闭接管是否变好？",
                "answer": (None if not roll else {
                    "reading": ("第 1 步**所有臂都在「接管关闭」下跑**（standard_sync + prime_mode=none）⇒ "
                                "「更新后 vs 更新前」= `bc`（BC 微调后）vs `injected_base`（同一接口、零微调）"
                                "vs `base_zeroshot`（G3 的固定基线）。三者可直接比，因为运行时/初态/判定层全同"),
                    "bc_vs_injected_base": {k: v for k, v in cmp_ib.items() if k != "rows"},
                    "bc_vs_base_zeroshot": {k: v for k, v in cmp_b0.items() if k != "rows"},
                    "improved": cmp_ib.get("a_greater_than_b"),
                    "measurement_status": cmp_ib.get("measurement_status", "not_measured"),
                    "not_answered_here": ("「**关闭恢复**后对比更新前后」的完整形态是**第 5 步**"
                                          "（裁定 95.2 第 5 行：用纠正数据更新策略、关闭恢复重新测试），"
                                          "它的前置是纠正数据桥接通（`label_record`/`proposal_label`/"
                                          "`view_manifest` 当前 0 行）。第 1 步只给出「BC 微调 vs 零微调」"
                                          "这一个受控差值，**不得**读成第 5 步的结论"),
                }),
                "measurement_status": (cmp_ib.get("measurement_status", "not_measured") if roll else "not_measured"),
            },
        ],
    }
    # ── v1 预登记的三条硬判据（裁定 95.2 第 1 行）逐条给结论：**保留、照实报**，但不再是总判 ──
    doc["step1_acceptance"] = {
        "criterion_verbatim": STEP1_CRITERION_VERBATIM,
        "status": ("**v1 预登记口径，保留照报**（裁定 102.2-②(a)：预登记的四个数一个不改）。"
                   "**总判已改由用户原文的四条验收标准出**（裁定 101.2 / 102.2-①），"
                   "见 `step1_acceptance_user_four_criteria`"),
        "half_1_loss_significantly_down": {
            "pass": lg.get("pass"), "measurement_status": lg.get("measurement_status", "not_measured"),
            "ratio_final_over_step0": lg.get("ratio_final_over_step0"),
            "threshold_max_ratio": lg.get("threshold_max_ratio"),
            "step0_train_det_loss": lg.get("step0_train_det_loss"),
            "final_train_det_loss": lg.get("final_train_det_loss"),
            "val_reported_not_gated": {"val_step0": lg.get("val_step0"), "val_final": lg.get("val_final"),
                                       "val_ratio": lg.get("val_ratio")},
        },
        "half_2_per_dim_action_match_including_gripper_timing": {
            "pass": am.get("gates_all_pass"), "measurement_status": am.get("measurement_status", "not_measured"),
            "red_codes": am.get("red_codes"),
            "observed_dims_summary": am.get("summary_observed_dims"),
            "blind_dims_report_only": am.get("summary_blind_dims_report_only"),
            "gripper_timing_gate": (am.get("gripper_timing") or {}).get("gate"),
            "gripper_semantics": GRIPPER_SEMANTICS,
        },
        "half_3_progress_from_demo_init_gt_random": {
            "pass": (cmp_rand.get("gate") or {}).get("pass"),
            "measurement_status": cmp_rand.get("measurement_status", "not_measured"),
            "primary_verdict": cmp_rand.get("primary_verdict"),
            "wins_ties_losses": {k: cmp_rand.get(k) for k in ("wins", "ties", "losses", "not_measured_pairs")},
            "sum_max_stage": cmp_rand.get("sum_max_stage"),
            "sum_net_approach_target": cmp_rand.get("sum_net_approach_target"),
            "extra_null_hold": {k: v for k, v in ((roll or {}).get("paired_comparisons") or {}).get(
                "bc_vs_hold", {}).items() if k != "rows"},
        },
        "v1_preregistered_three_halves_verdict": None,
    }
    three = [doc["step1_acceptance"]["half_1_loss_significantly_down"]["pass"],
             doc["step1_acceptance"]["half_2_per_dim_action_match_including_gripper_timing"]["pass"],
             doc["step1_acceptance"]["half_3_progress_from_demo_init_gt_random"]["pass"]]
    doc["step1_acceptance"]["v1_preregistered_three_halves_verdict"] = (
        None if any(x is None for x in three) else ("PASS" if all(x is True for x in three) else "RED"))
    doc["step1_acceptance"]["half_3_role_amended"] = GATES["progress_gt_random_role_why"]

    # ── **裁定 101.2 / 102.2-①：用户原文的四条验收标准 = Step 1 的权威总判** ──
    cl_tooth = _safe_get(roll, "exit_criterion_closed_loop_reproduction") or {}
    align = alignment_evidence_block(args)
    per_bc = ((tables.get("bc") or {}).get("per_seed")) or []
    n_fail = stall.get("n_bc_not_task_success")
    c4_pass, c4_status, c4_why = None, "not_measured", "rollout 未跑 ⇒ 无从判"
    if roll and per_bc:
        if n_fail == 0:
            c4_status, c4_pass = "not_applicable", None
            c4_why = ("`bc` 臂**没有任何失败局** ⇒ 「失败时能定位到具体阶段」这一条**无从判**；"
                      "三值纪律：`not_applicable` + `pass=null`，**不许**写成「通过」")
        else:
            localized = [r for r in per_bc if r.get("task_success") is not True]
            all_have_stage = all(r.get("max_stage") is not None for r in localized)
            c4_pass = bool(all_have_stage and stall.get("dominant_stall_stage") is not None)
            c4_status = "measured"
            c4_why = ("每条失败局都带 C2 判定层给出的 `max_stage` ⇒ 能定位到阶梯上的具体档"
                      if c4_pass else "有失败局缺 `max_stage` 或定不出主导档 ⇒ 定位失败")
    c1_pass = (None if (lg.get("pass") is None or am.get("gates_all_pass") is None)
               else bool(lg.get("pass") and am.get("gates_all_pass")))
    four = {
        "criteria_verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM,
        "authority": "裁定 101.2（用户原文逐字采纳）· 裁定 102.2-①（第 2 条 = **出场判据**）",
        "is_the_authoritative_verdict": True,
        "criterion_1_train_action_error_clearly_down": {
            "verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM[0],
            "pass": c1_pass,
            "measurement_status": "measured" if c1_pass is not None else "not_measured",
            "nuclearization": ("**产出①「训练集动作误差」**= 两半都过：(a) 确定性训练损失末点 ≤ step0 的 0.5"
                               "（`train_det_loss_final_over_step0`）；(b) 反归一化后逐维 MAE ≤ 5% 行程 ∧ "
                               "逐维 corr ≥ 0.9（8 个非盲点维）∧ 夹爪开合时刻误差中位数 ≤ 5 帧"),
            "sub_readings": {"loss_gate_pass": lg.get("pass"),
                             "train_det_loss_final_over_step0": lg.get("train_det_loss_final_over_step0"),
                             "action_match_gates_all_pass": am.get("gates_all_pass"),
                             "per_dim_mae_rel_max_observed_dims": am.get("summary_observed_dims"),
                             "gripper_timing_gate": (am.get("gripper_timing") or {}).get("gate")},
            "plateau_reached": lg.get("plateau_reached"),
            "stopped_by": lg.get("stopped_by"),
            "no_early_stop_while_descending": lg.get("no_early_stop_while_descending"),
            "nearzero_gap": OPEN_STEP1_NEARZERO_GAP,
            "a2_self_binding": ("**A2 不宣称「接近零」**：只报实测比值与预登记阈值 0.5 的关系；"
                                "两处口径的差由 **D 在里程碑审查按实测曲线裁**（裁定 102.2-②(c)）"),
            "high_plateau_disposition": ("**平台期停在高值 ⇒ Step 1 = RED（「数据学不到」）**，不是通过"
                                         "（裁定 102.2-②）"),
        },
        "criterion_2_closed_loop_reproduction_forward_and_reverse": {
            "verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM[1],
            "is_exit_criterion": True,
            "pass": cl_tooth.get("pass"),
            "measurement_status": cl_tooth.get("measurement_status", "not_measured"),
            "nuclearization": cl_tooth.get("nuclearization") or GATES["closed_loop_reproduction_why"],
            "tooth_id": cl_tooth.get("tooth_id"),
            "red_codes": cl_tooth.get("red_codes"),
            "n_forward_geometric_success": cl_tooth.get("n_forward_geometric_success"),
            "n_reverse_geometric_success": cl_tooth.get("n_reverse_geometric_success"),
            "forward_episodes_passed": cl_tooth.get("forward_episodes_passed"),
            "reverse_episodes_passed": cl_tooth.get("reverse_episodes_passed"),
            "other_arms_same_caliber_report_only": cl_tooth.get("other_arms_same_caliber_report_only"),
            "tooth_selftest": {k: v for k, v in (_safe_get(roll, "exit_criterion_tooth_selftest") or {}).items()
                               if k != "rows"},
            "capability_note": cl_tooth.get("capability_note"),
        },
        "criterion_3_no_unexplained_systematic_offset": {
            "verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM[2],
            "pass": align.get("pass"),
            "measurement_status": align.get("measurement_status", "not_measured"),
            "rule": CRITERION_3_RULE,
            "checks": align.get("checks"),
            "why_not_pass": align.get("why_not_pass"),
            "r1_verdict": _safe_get(align, "r1_arm12_offbyone_exclusion.verdict"),
            "r2_verdict_unchanged": _safe_get(align, "r2_grip2_transition_alignment.verdict"),
            "r2_attribution_classification_verbatim": _safe_get(
                align, "r2_grip2_transition_alignment.exception_attribution_verbatim_from_run.classification"),
            "anchor_probe_additional_evidence": align.get("anchor_probe_additional_evidence"),
            "disposition_authority": align.get("disposition_authority"),
            "evidence_artifacts": {"r1r2_verdict": align.get("r1r2_verdict_artifact"),
                                   "anchor_probe": align.get("anchor_probe_artifact")},
        },
        "criterion_4_failure_localizable_to_stage": {
            "verbatim": STEP1_ACCEPTANCE_CRITERIA_VERBATIM[3],
            "pass": c4_pass, "measurement_status": c4_status, "why": c4_why,
            "nuclearization": ("**产出⑥「失败阶段」**= 用**预登记的推进度阶梯**（0 未接触 / 1 源侧接触 / "
                               "2 离桌 / 3 交接侧到位 / 4 C2 几何成功）给每条失败局定位；"
                               "阶梯与 C2 的 `reasons` 原文都不新造"),
            "stall_stage_hist": stall.get("stall_stage_hist"),
            "stall_stage_hist_reading": stall.get("stall_stage_hist_reading"),
            "dominant_stall_stage": stall.get("dominant_stall_stage"),
            "dominant_stall_stage_reading": stall.get("dominant_stall_stage_reading"),
            "n_bc_episodes": stall.get("n_bc_episodes"), "n_bc_not_task_success": n_fail,
        },
        "required_outputs_six": STEP1_REQUIRED_OUTPUTS_VERBATIM,
        "fixed_conditions_verbatim": STEP1_FIXED_CONDITIONS_VERBATIM,
        "open_items": OPEN_ITEMS_STEP1,
    }
    judged = [four["criterion_1_train_action_error_clearly_down"],
              four["criterion_2_closed_loop_reproduction_forward_and_reverse"],
              four["criterion_3_no_unexplained_systematic_offset"],
              four["criterion_4_failure_localizable_to_stage"]]
    counted = [c for c in judged if c["measurement_status"] != "not_applicable"]
    four["overall_step1_verdict"] = (
        None if any(c["pass"] is None for c in counted)
        else ("PASS" if all(c["pass"] is True for c in counted) else "RED"))
    four["overall_caliber"] = (
        "**四条全过 ⇒ PASS；任一不过 ⇒ RED；任一 `pass=null`（含 `not_measured`）⇒ `null` + 非零退出**"
        "（三值纪律，裁定 88.3-1：不许把「没测到」写成「通过」或「失败」）。"
        f"`not_applicable` 的条不计入 AND（本轮 = "
        f"{[c['verbatim'] for c in judged if c['measurement_status'] == 'not_applicable']}）")
    four["capability_claim"] = False
    four["capability_note"] = (
        "**PASS ≠ 能力声明**（裁定 46 / 101.3）：Step 1 是「数据能否被学到 + 离线拟合能否转成在线控制」"
        "的闸门；本臂作用域 = `AlohaTransferCube-v0` 的左右臂交接（**冒烟基准**），"
        "**不得**写成「单臂区域抓放能力」（裁定 95.4-③/⑤）；盲点维 [0,3,5,7,10,12] 只报不判")
    doc["step1_acceptance_user_four_criteria"] = four
    doc["overall_step1_verdict"] = four["overall_step1_verdict"]
    doc["alignment_evidence"] = align
    if four["overall_step1_verdict"] is None and (train_rep or roll):
        findings.add("step1_verdict_undetermined_three_valued", verdict="RED", blocking=True,
                     subject="step1_acceptance",
                     evidence={"per_criterion": [{"verbatim": c["verbatim"], "pass": c["pass"],
                                                  "measurement_status": c["measurement_status"]}
                                                 for c in judged]},
                     ruling="裁定 88.3-1（三值纪律）· 裁定 101.2（四条验收标准）",
                     why="四条验收标准里有 `pass=null` ⇒ Step 1 的总判**算不出** ⇒ 不许写 PASS 也不许写 RED")
    doc["six_questions"] = six
    doc["measurement_status"] = "measured" if (train_rep or roll) else "not_measured"
    # ── 裁定 101.2 的**六项产出**逐项落点（D 审查时按这张表核，不用翻散文）──
    doc["required_outputs_index"] = {
        "authority": "裁定 101.2（用户原文逐字采纳的六项必须产出）",
        "outputs": [
            {"n": "①", "verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM[0],
             "where": "STEP1_RESULT.json → `step1_acceptance_user_four_criteria.criterion_1_*`",
             "sources": ["TRAIN_REPORT.json → `loss_gate.train_det_loss_final_over_step0`",
                         "TRAIN_REPORT.json → `action_match.selected.summary_observed_dims`"],
             "measurement_status": four["criterion_1_train_action_error_clearly_down"]["measurement_status"]},
            {"n": "②", "verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM[1],
             "where": "ROLLOUT_REPORT.json → `exit_criterion_closed_loop_reproduction`（= 出场判据牙 A2T6）",
             "sources": ["ROLLOUT_REPORT.json → `per_arm_tables.bc.per_seed[*].geometric_success`"],
             "measurement_status": four["criterion_2_closed_loop_reproduction_forward_and_reverse"]["measurement_status"]},
            {"n": "③", "verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM[2],
             "where": "ROLLOUT_REPORT.json → `per_arm_tables.*.by_direction`（正/反**分别**）",
             "sources": ["ROLLOUT_REPORT.json → `paired_comparisons`", "STEP1_RESULT.json → 六问 Q3"],
             "measurement_status": "measured" if roll else "not_measured"},
            {"n": "④", "verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM[3],
             "where": ("TRAIN_REPORT.json → `action_match.selected.gripper_timing`（训练侧）+ "
                       "R2 判词件（探针侧，`alignment_evidence.r2_grip2_transition_alignment`）"),
             "sources": [args.r1r2_verdict_json],
             "measurement_status": four["criterion_3_no_unexplained_systematic_offset"]["measurement_status"]},
            {"n": "⑤", "verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM[4],
             "where": "ROLLOUT_REPORT.json → `timing_per_ctrl_step`（裁定 102.2-④ 的口径）",
             "sources": ["harness/vla_runtime.py:1078 `wall_ms_per_ctrl_step`（**只读，未改载荷件**）"],
             "measurement_status": ("measured" if roll else "not_measured"),
             "deferred": OPEN_STEP2_TIMING_PERCENTILES},
            {"n": "⑥", "verbatim": STEP1_REQUIRED_OUTPUTS_VERBATIM[5],
             "where": "STEP1_RESULT.json → `step1_acceptance_user_four_criteria.criterion_4_*` + 六问 Q4",
             "sources": ["ROLLOUT_REPORT.json → `per_arm_tables.bc.per_seed[*].max_stage`",
                         "`PROGRESS_LADDER`（预登记的阶梯，不新造口径）"],
             "measurement_status": four["criterion_4_failure_localizable_to_stage"]["measurement_status"]},
        ],
    }
    doc["stop_point"] = prereg.get("stop_point") if prereg else None
    doc["next_step_authorization"] = ("**停，等 D 的里程碑审查**（补单四 §四）。第 2 步的排程与预算核算是 D 在"
                                      "里程碑审查时发；**不要顺手开第 2 步**，即使卡空着")
    ident = write_json(out_dir / "STEP1_RESULT.json", doc)
    write_json(out_dir / "STEP1_SIX_QUESTIONS.json", six)
    print(f"[report] **overall_step1_verdict={four['overall_step1_verdict']}** "
          f"①误差={four['criterion_1_train_action_error_clearly_down']['pass']} "
          f"②闭环复现={four['criterion_2_closed_loop_reproduction_forward_and_reverse']['pass']} "
          f"③无系统性偏移={four['criterion_3_no_unexplained_systematic_offset']['pass']} "
          f"④可定位={four['criterion_4_failure_localizable_to_stage']['pass']}"
          f"（v1 三半旧口径={doc['step1_acceptance']['v1_preregistered_three_halves_verdict']}） "
          f"artifact={ident['path']} {ident['sha256_12']}", flush=True)
    return doc


# ══════════════════════════ ⑫ 总判与退出码 ══════════════════════════
def evaluate_findings_step1(summary: dict, findings, exit_code: int) -> int:
    fs = findings.summary() if hasattr(findings, "summary") else {}
    n_block = fs.get("n_blocking_red", 0)
    if n_block:
        return EXIT_BLOCKING_RED
    return exit_code


# ══════════════════════════ ⑬ CLI ══════════════════════════
def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="A2 / 六步序列第 1 步：小量示范过拟合 + 从示范初态闭环执行")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--stages", default="admission,prereg",
                    help=f"逗号分隔，可选 {','.join(ALL_STAGES)}；GPU 阶段 = {','.join(GPU_STAGES)}")
    ap.add_argument("--weights-dir", default=PRE.P_WEIGHTS)
    ap.add_argument("--tokenizer-dir", default=PRE.DEFAULT_TOKENIZER)
    ap.add_argument("--weights-receipt", default="runs/vla/a2_pi05_contract_20260929/ckpt_readonly_reverification.json")
    ap.add_argument("--skip-weights-rehash", action="store_true",
                    help="不复算 14.4 GB base safetensors 的 sha256（⇒ 该身份记 not_measured）")
    ap.add_argument("--stats-path", default=PRE.P_C2_STATS)
    ap.add_argument("--prealign-json", default=PREALIGN_JSON_DEFAULT,
                    help="先落腿 `PREALIGN_VERIFICATION.json`（A2 自己那颗准入牙的判据）")
    ap.add_argument("--g14-evidence-path", default=None,
                    help="裁定 97.3-4 的一次性前置证据件；**默认不给** ⇒ 从 C2 广播件解析（不 glob、不自算充当声明）")
    ap.add_argument("--g14-evidence-sha256-12", default=None,
                    help="上面那件的**声明** sha256[:12]（闸会自己复算对账；A2 自算充当声明会让对账恒真）")
    ap.add_argument("--g14-checked-by", default=G14_CHECKED_BY_DEFAULT)
    ap.add_argument("--g14-checked-when", default=G14_CHECKED_WHEN_DEFAULT)
    ap.add_argument("--selftest-only", action="store_true",
                    help="只跑 A2 自己那颗牙的两向自检（纯 CPU、不消费广播、不上卡）然后退出")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--mujoco-gl", default=None, help="默认沿用环境（EGL 前缀激活后应为 egl）")
    ap.add_argument("--declaration-line", type=int, default=None,
                    help="daily_report.md 里的 GPU 窗口申报行号（**GPU 阶段必填**，行内须写入口脚本名）")
    ap.add_argument("--allow-cotenant", action="store_true")
    ap.add_argument("--refusal-strictness", choices=["narrow", "strict"], default="narrow")
    ap.add_argument("--sampler-interval-s", type=float, default=2.0)
    ap.add_argument("--cotenant-interval-s", type=float, default=0.0,
                    help=">0 才把三网采样挂到 runtime 关键路径（会改变延迟口径，默认 0 与权威带同口径）")
    ap.add_argument("--skip-gpu-preflight", action="store_true",
                    help="**只**允许在不含 GPU 阶段时用（上卡阶段必须过起跑前拒绝逻辑）")
    # ---- 数据 / 训练 ----
    ap.add_argument("--chunk-size", type=int, default=50)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--force-cache", action="store_true")
    ap.add_argument("--precision", choices=["bfloat16", "float32"], default="bfloat16")
    ap.add_argument("--batch-size", type=int, default=0, help="0 = 由 probe 按预登记的规则实测决定")
    ap.add_argument("--batch-candidates", default="1,2,4")
    ap.add_argument("--vram-ceiling-mib", type=int, default=62000,
                    help="预登记的显存上限（80 GB 卡留 ~18 GB 余量给碎片/渲染上下文）")
    ap.add_argument("--lr", type=float, default=1.0e-4)
    ap.add_argument("--train-steps", type=int, default=1200)
    ap.add_argument("--train-seed", type=int, default=20260930)
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--ckpt-steps", default="300,600,900,1200")
    ap.add_argument("--log-every", type=int, default=20)
    ap.add_argument("--det-subset-size", type=int, default=64)
    ap.add_argument("--allow-prereg-overwrite", action="store_true",
                    help="重写预登记件（会留前像）。**默认拒绝**：预登记事后被改就没有约束力（95.5-③）")
    # ---- 裁定 102.2-②(b)：**不得在确定性训练损失仍在下降时提前停** ----
    ap.add_argument("--plateau-block-steps", type=int, default=int(PLATEAU_RULE["block_steps"]),
                    help="平台期判定的块长（裁定 102.2-②(b)：**每 100 步一块**）")
    ap.add_argument("--plateau-min-block-drop-frac", type=float,
                    default=float(PLATEAU_RULE["min_block_drop_frac"]),
                    help="块间降幅 >1%% 且预算未耗尽 ⇒ 继续（裁定 102.2-②(b) 逐字）")
    ap.add_argument("--train-steps-max", type=int, default=4000,
                    help="平台期扩展的**硬上限**（预登记的规则，不看结果）")
    ap.add_argument("--train-wall-budget-s", type=float, default=float(PLATEAU_RULE["wall_budget_s_default"]),
                    help="裁定 101.4：**1 小时未收敛即停并报读数，不要烧满窗口**")
    ap.add_argument("--no-plateau-extend", dest="plateau_extend", action="store_false", default=True,
                    help="关掉扩展（**只**用于调试；关掉时 `stopped_by='extension_disabled'` 照实落盘）")
    # ---- 预登记 v2（补单七 §三：**追加、不覆写**）----
    ap.add_argument("--no-prereg-v2", dest="prereg_v2", action="store_false", default=True,
                    help="不写 `PRE_REGISTRATION_v2.json`（默认写：v1 已在盘 ⇒ v2 追加、v1 原字节进 before_images/）")
    # ---- 裁定 101.2：R1/R2 并入产出③④（消费既有判词件，**不重算**）----
    ap.add_argument("--r1r2-verdict-json",
                    default="runs/vla/a2_r1_r2_alignment_20260930_run2/R1R2_ALIGNMENT_VERDICT.json",
                    help="产出③（对齐取证 = R1）/ 产出④（夹爪转变帧误差 = R2）的既有判词件")
    ap.add_argument("--r1r2-anchor-probe-json",
                    default="runs/vla/a2_r1_r2_anchor_probe_20260930/ANCHOR_PROBE_BOX_QUAT.json",
                    help="锚定牙失锚机制的对照探针件（**只引用、不改 R2 的预登记判词**）")
    # ---- rollout ----
    ap.add_argument("--n-replan", type=int, default=VR.MAINLINE_N_REPLAN)
    ap.add_argument("--max-frames", type=int, default=0, help="0 = 用 env 注册的 300（裁定 65-2）")
    ap.add_argument("--rollout-arms", default=DEFAULT_ARMS)
    ap.add_argument("--rollout-splits", default="train,val")
    ap.add_argument("--random-seed0", type=int, default=77000)
    ap.add_argument("--state-reproduce-tol", type=float, default=1e-6)
    ap.add_argument("--renderer-must-contain", default="NVIDIA")
    ap.add_argument("--renderer-strict", action="store_true", default=True)
    ap.add_argument("--no-renderer-strict", dest="renderer_strict", action="store_false")
    ap.add_argument("--stop-on-geometric-success", dest="stop_on_geometric_success",
                    action="store_true", default=True)
    ap.add_argument("--no-stop-on-geometric-success", dest="stop_on_geometric_success", action="store_false")
    ap.add_argument("--task-right-to-left", default=S4B.TASK_BY_DIRECTION["right_to_left"])
    ap.add_argument("--task-left-to-right", default=S4B.TASK_BY_DIRECTION["left_to_right"])
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    args.task_by_direction = {"right_to_left": args.task_right_to_left,
                              "left_to_right": args.task_left_to_right}
    stages = [s.strip() for s in str(args.stages).split(",") if s.strip()]
    bad = [s for s in stages if s not in ALL_STAGES]
    if bad:
        print(f"[usage] 未知 stage {bad}，可选 {list(ALL_STAGES)}", file=sys.stderr)
        return EXIT_USAGE
    if not stages:
        print("[usage] --stages 为空", file=sys.stderr)
        return EXIT_USAGE
    need_gpu = any(s in GPU_STAGES for s in stages)
    if need_gpu and args.skip_gpu_preflight:
        print("[usage] --skip-gpu-preflight 不能与 GPU 阶段同用（上卡必须过起跑前拒绝逻辑）", file=sys.stderr)
        return EXIT_USAGE
    if args.mujoco_gl:
        os.environ["MUJOCO_GL"] = args.mujoco_gl
    _w = pathlib.Path(args.weights_dir)
    args.weights_dir_resolved = str(_w if _w.is_absolute() else (REPO / _w))
    if not pathlib.Path(args.weights_dir_resolved).exists():
        print(f"[usage] 权重目录不存在：{args.weights_dir_resolved}", file=sys.stderr)
        return EXIT_USAGE
    if not pathlib.Path(args.tokenizer_dir).exists():
        print(f"[usage] tokenizer 目录不存在：{args.tokenizer_dir}", file=sys.stderr)
        return EXIT_USAGE

    out_dir = pathlib.Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")

    if args.selftest_only:
        st = prealign_tooth_selftest()
        st6 = closed_loop_reproduction_selftest()
        st7 = plateau_rule_selftest()
        all_bite = bool(st["all_bite"] and st6["all_bite"] and st7["all_bite"])
        ident = write_json(out_dir / f"A2_TOOTH_SELFTEST_{ts}.json",
                           base_doc("a2_step1_tooth_selftest", args, selftest=st,
                                    selftest_A2T6_exit_criterion=st6,
                                    selftest_A2T7_plateau_rule=st7,
                                    all_bite=all_bite,
                                    gpu_used=False, policy_executed=False,
                                    dry_run_before_gpu=True,
                                    consumed_real_readings=False,
                                    ruling=("裁定 93.8：审计器须自证；只装一向不许报绿 · "
                                            "裁定 99.3：预登记判据必须**先干跑再上卡** · "
                                            "补单七 §三：新牙带两向变异体自证")))
        print(f"[selftest] **all_bite={all_bite}** A2T1={st['n_bite']}/{st['n_rows']} "
              f"A2T6={st6['n_bite']}/{st6['n_rows']} A2T7={st7['n_bite']}/{st7['n_rows']} "
              f"artifact={ident['path']} {ident['sha256_12']}", flush=True)
        for r in st["rows"]:
            print(f"  [{'BITE' if r.get('bite') else 'FAIL'}] {r['case']} expect={r['expect']} "
                  f"got={r['got']} red={r.get('red_codes')}", flush=True)
        for r in st6["rows"] + st7["rows"]:
            print(f"  [{'BITE' if r.get('bite') else 'FAIL'}] {r['case']} "
                  f"expect={r.get('expect') or r.get('expect_extend')}/"
                  f"{r.get('expect_measurement_status') if 'expect_measurement_status' in r else r.get('expect_plateau_reached')} "
                  f"got={r.get('got') or r.get('got_extend')}/{r.get('got_measurement_status', r.get('got_plateau_reached'))}"
                  f" red={r.get('red_codes')}", flush=True)
        return EXIT_OK if all_bite else EXIT_BLOCKING_RED

    # ── 裁定 102.2-③：**四臂必需**在上卡之前就拦住（不烧窗口才发现缺臂）──
    _arms_req = [a.strip() for a in str(args.rollout_arms).split(",") if a.strip()]
    _missing = [a for a in REQUIRED_ARMS if a not in _arms_req]
    _unknown = [a for a in _arms_req if a not in ARMS]
    _opt = [a for a in OPTIONAL_ARMS if a in _arms_req]
    if ("rollout" in stages or need_gpu) and (_missing or _unknown):
        print(f"[usage] 裁定 102.2-③：四臂必需 {list(REQUIRED_ARMS)}；缺={_missing} 未定义={_unknown} "
              f"请求={_arms_req} ⇒ 不上卡（exit {EXIT_USAGE}）", file=sys.stderr)
        return EXIT_USAGE
    if _opt and _arms_req[-len(_opt):] != _opt:
        print(f"[usage] 提示（不阻塞）：可选臂 {_opt} 应**排最后**（裁定 102.2-③）；当前顺序={_arms_req}",
              file=sys.stderr)

    print(f"[step1] stages={stages} need_gpu={need_gpu} MUJOCO_GL={os.environ.get('MUJOCO_GL')} "
          f"out={out_dir}", flush=True)
    reuse = build_reuse()
    reuse["stats"] = PRE.read_stats(REPO / args.stats_path)
    print(f"[reuse] 三网探测器={reuse['identity']['three_net_detector']['sha256_12']} "
          f"policy 构造={reuse['identity']['policy_builder_and_action_adapter']['sha256_12']} "
          f"先落腿={reuse['identity']['step1_prealign_verify']['sha256_12']} "
          f"准入闸={reuse['identity']['bc_admission_gate']['sha256_12']} "
          f"stats={sha12(REPO / args.stats_path)} rep_version={str(reuse['stats']['representation_version'])[:40]}…",
          flush=True)

    findings = S4B.Findings()
    exit_code = EXIT_OK
    window = None
    decl: dict = {"measurement_status": "not_applicable", "why": "本次调用不含 GPU 阶段 ⇒ 不需要申报"}
    docs: dict = {}
    if need_gpu:
        # ---- ① 先申报后上卡（行内须写入口脚本名；读回原文核对，复用 S4B 的实现）----
        decl = S4B.check_declaration(args.declaration_line, required=True)
        if decl.get("verdict") != "GREEN":
            print(f"[refuse] 未核到 A2 的 GPU 窗口申报行（--declaration-line={args.declaration_line}）"
                  f"⇒ 不上卡（exit {EXIT_USAGE}）。核到的事实：{json.dumps(decl, ensure_ascii=False)[:500]}",
                  file=sys.stderr)
            write_json(out_dir / f"refused_no_declaration_{ts}.json", decl)
            return EXIT_USAGE
        if SELF_REL.split("/")[-1].replace(".py", "") not in str(decl.get("found_text") or ""):
            findings.add("declaration_line_lacks_entry_script_name", verdict="RED", blocking=False,
                         subject="gpu_window_declaration", evidence=decl,
                         ruling="RR1(a)（补单四 §三）：申报里必须写入口脚本名，E 收到后一行补词表",
                         why="申报行没写入口脚本名 ⇒ E 无法把它加进 `GPU_INTENT_PATTERNS`（不阻塞本臂，但必须自报）")
        # ---- ② 起跑前拒绝逻辑（读 E 的参考实现 `card_busy()`）+ 开窗 ----
        window = S4B.GpuWindow(out_dir, reuse=reuse, allow_cotenant=args.allow_cotenant,
                               refusal_strictness=args.refusal_strictness,
                               sampler_interval_s=args.sampler_interval_s,
                               arm_label=f"step1_bc_overfit:{'+'.join(stages)}", declaration=decl)
        try:
            pf = window.preflight()
        except S4B.GpuBusyRefusal as exc:
            print(f"[refuse] {exc}", file=sys.stderr)
            return EXIT_REFUSED_GPU_BUSY
        print(f"[preflight] n_foreign_gpu_processes={pf['n_foreign_gpu_processes']} "
              f"gate_ok={pf['yield_gate']['ok']} memory_used_mib="
              f"{(pf['three_net_raw'] or {}).get('memory_used_mib')}", flush=True)
        window.open()

    try:
        if "admission" in stages:
            docs["admission"] = stage_admission(args, out_dir, findings)
            if not docs["admission"].get("admitted"):
                print("[refuse] 准入不成立 ⇒ 第 1 步不许开跑（exit 4）", file=sys.stderr)
                exit_code = EXIT_REFUSED_ADMISSION
        if exit_code == EXIT_REFUSED_ADMISSION:
            return _finish(args, out_dir, findings, window, docs, decl, ts, exit_code, need_gpu, stages)
        if "prereg" in stages:
            docs["prereg"] = stage_prereg(args, out_dir, findings)
        if "cache" in stages:
            docs["cache"] = stage_cache(args, out_dir, findings)
        if "probe" in stages:
            docs["probe"] = stage_probe(args, out_dir, findings, reuse, window)
        if "train" in stages:
            docs["train"] = stage_train(args, out_dir, findings, reuse, window)
        if "rollout" in stages:
            docs["rollout"] = stage_rollout(args, out_dir, findings, reuse, window)
        if "report" in stages:
            docs["report"] = stage_report(args, out_dir, findings, reuse)
    except Exception as exc:                                              # noqa: BLE001
        import traceback
        findings.add("run_crash", verdict="RED", blocking=True, subject="run_crash",
                     evidence={"error": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc()[-4000:]},
                     ruling="—", why="整轮崩了 ⇒ 不许当绿交付")
        exit_code = EXIT_BLOCKING_RED
    return _finish(args, out_dir, findings, window, docs, decl, ts, exit_code, need_gpu, stages)


def _finish(args, out_dir, findings, window, docs, decl, ts, exit_code, need_gpu, stages) -> int:
    summary = {
        **base_doc("bc_step1_run_summary", args),
        "stages_requested": stages,
        "stage_measurement_status": {k: (v or {}).get("measurement_status") for k, v in docs.items()},
        "gpu_used": bool(need_gpu),
        "policy_executed": bool((docs.get("rollout") or {}).get("measurement_status") == "measured"),
        "declaration": decl,
        "findings": findings.items,
        "n_findings": len(findings.items),
        "n_blocking_red": sum(1 for f in findings.items if f.get("blocking") and f.get("verdict") == "RED"),
        "n_not_measured": sum(1 for f in findings.items if f.get("verdict") == "not_measured"),
        "self_identity": identity(SELF_REL),
        "identities": {"c2_stats": identity(PRE.P_C2_STATS), "npz_source": identity(PRE.P_NPZ),
                       "demo_manifest": identity(PRE.P_MANIFEST),
                       "dataset_info": identity(str(pathlib.Path(PRE.P_DS) / "meta" / "info.json")),
                       "base_weights_config": identity(str(pathlib.Path(args.weights_dir_resolved)
                                                            .relative_to(REPO) / "config.json")),
                       "prealign_verification": identity(args.prealign_json),
                       "e_calib_reference_impl": identity(PRE.P_CALIB)},
    }
    win = None
    if window is not None:
        renderer_end = None
        win = window.close(renderer_at_end=renderer_end,
                           extra={"stages": stages, "arm_label": window.arm_label,
                                  "note": ("窗口账本覆盖本次调用请求的全部阶段；`cache` 这类纯 CPU 阶段"
                                           "**故意**排在 GPU 调用之外，免得它的 loadavg 摆动污染窗口判据")})
        summary["gpu_window"] = win
    if exit_code == EXIT_OK:
        exit_code = evaluate_findings_step1(summary, findings, exit_code)
    summary["exit_code"] = exit_code
    summary["overall_verdict"] = "RED" if exit_code != EXIT_OK else "GREEN"
    ident = write_json(out_dir / f"STEP1_RUN_SUMMARY_{ts}.json", summary)
    write_json(out_dir / "STEP1_RUN_SUMMARY.json", summary)
    print(f"[done] stages={stages} overall={summary['overall_verdict']} exit={exit_code} "
          f"blocking_red={summary['n_blocking_red']} gpu_used={summary['gpu_used']} "
          f"policy_executed={summary['policy_executed']} artifact={ident['path']} {ident['sha256_12']}",
          flush=True)
    if win:
        c = win.get("contaminated") or {}
        print(f"[window] elapsed={win.get('elapsed_s')}s contaminated_overall={c.get('contaminated_overall')} "
              f"three_net={c.get('contaminated_three_net')} loadavg_swing={c.get('loadavg_1m_swing')} "
              f"nr_throttled_delta={(win.get('nr_throttled') or {}).get('delta')}", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
