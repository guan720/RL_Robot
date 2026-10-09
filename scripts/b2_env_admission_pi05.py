#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 线：π₀.₅ 新环境的**可复现性准入闸**（D→B2 执行单 §1 + 增补十六 裁定 39.1）。

为什么需要它（D 的原文实质）
----------------------------
A2 会交来 `runs/vla/a2_env_pi05_sim_20260929/{requirements.lock.txt, env_manifest.json,
weights_receipt.json, resolve_dryrun.txt}`。D 的验收口径是：**这批产物必须过 B2 的闸，D 才认这套环境**。
本闸**不重写** B 已验收的判据，而是：
  ① 以子进程**委派** `scripts/b_env_provenance_guard.py`（G1–G5，`--selftest` 12/12 已被 D 验收）；
  ② 以子进程**委派** `scripts/b_env_migration_invariance_check.py`（V0–V9，本轮 B2 独立复跑 10/10）；
  ③ 只**新增** π₀.₅ 专属的八条牙（V-pi05-1…8），那是本仓从未验过的面。

八条 π₀.₅ 牙（每条都写明**可红条件**，遵守 裁定 27.1「恒真/恒假的闸等于没有闸」）
----------------------------------------------------------------------------------
V-pi05-1 version_anchor       `lerobot` 的实际装成版本必须与**两套已验收 venv**（lerobot_act /
                              lerobot_eval）逐字相同（现值 `0.4.4`）；`transformers` 必须**已装**、
                              必须落在 lerobot 0.4.4 extra `transformers-dep` 的硬区间
                              `>=4.57.1,<5.0.0` 内、且其**实际装成版本必须写进产物**
                              （裁定 34.1：钉实际装成的值、不回退）。
                              **红**：lerobot 版本与已验收值不同（必须**点名包与版本**，
                              不得写成「差异可忽略」）；transformers 缺失；版本低于 4.57.1 或
                              >= 5.0.0；transformers 实测已装但产物里查不到该版本；
                              venv 的 realpath 落在 `maniskill_probe`（其实测 transformers 4.30.0
                              低于硬下界 ⇒ 会出现「import 成功但加载权重报错」，裁定 39.1 明令禁用）。
V-pi05-2 weights_identity     `weights_receipt.json` 里每个文件的 **sha256 必须可复算且相同**、
                              字节数必须相同；`config.json` / `policy_preprocessor.json` /
                              `policy_postprocessor.json` **三件必须在盘上且非空**
                              （缺后两件 ⇒ lerobot `from_pretrained` **静默走默认归一化**，
                              这是最坏的一类假绿）；文件份数必须与 receipt 声明一致且 >= 7
                              （环境调研线实测：`snapshot_download` 被 429 时会**静默返回半成品并
                              exit 0**，719/895 ⇒ 数文件核 size，不信返回码）。
                              **「相同」的判法**：盘上复算值必须**命中 receipt 声明的至少一个通道**
                              （LFS sha256 / HF git blob sha1 / 字节数），且与 receipt 的自述值不冲突；
                              一个可比对的声明值都读不到 ⇒ **判红**（不得记成通过）。
                              **红**：任一 sha256/字节数不命中任一通道；盘上值与自述值不符（交件后被动过）；
                              三件小文件任一缺失或空；份数不足；receipt 缺 license 字段
                              （Gemma Terms 必须进证据链）。
                              **弃权**：只有 receipt 自述值、没有远端期望值 ⇒「没被动过」成立但
                              「下对了东西」未证 ⇒ UNJUDGED（不降级成 PASS）。
V-pi05-3 channel_provenance   走的是 ModelScope 还是 hf-mirror **必须留痕**（channel + host/url 证据）；
                              **外部来源事实**（license、他人显存报告、上游 lastModified）必须标
                              `external_unverified`，且**不得与本机实测并列在同一块**（裁定 36.4）。
                              **留痕的三种形态都认**（A2 的真实 receipt 没有顶层 channel 键，
                              但有 `remote_hf`/`remote_modelscope` 远端块 + 逐文件 `sha256_verdict`
                              + `download.note`）；解析出的渠道必须**全部** ∈ 允许集。
                              **外部标记的词表**：`external_unverified` 块 / `remote_*`·`upstream_*` 块名 /
                              同层 `kind|source|provenance` 点名远端（A2 用 `kind: remote_api_read`）
                              ——语义等价即算标记（M31 反向钉住，防恒红）；但外部声明值**躺在实测块里**
                              且无标记仍判红（M32 钉住；词表口径已开 RR-B2-05 报 D）。
                              **红**：三种形态都给不出留痕；渠道不在允许集；无 host/url 佐证；
                              外部事实未标记就混在实测块里；**反向**也红——把本机实测值
                              （bytes/sha256/速率）塞进 `external_unverified` 块（那是把实测降级成传闻）。
V-pi05-4 torch_stack_frozen   **裁定 39.1 的红线**：新 venv 的 `torch.__version__` 必须逐字等于
                              `2.6.0+cu124`（`torch.version.cuda == 12.4`）；`resolve_dryrun.txt`
                              里**不得**出现 torch / torchvision / torchcodec 的 install/upgrade/downgrade。
                              **必须双向有牙**（D 原文）：造 `2.6.0+cu124 → 2.9.0+cu128` 的清单必须红；
                              只新增 `transformers 4.57.1` 的清单必须绿。
                              **红**：live `torch.__version__` != 锚值；cuda != 12.4；
                              dryrun 触及 torch 栈；dryrun 缺失（缺失不等于「没动」⇒ 弃权，见下）。
V-pi05-5 transformers_pi05_ready  **2026-09-29 18:4x 现场逼出来的第 5 条牙**（B2 只读实测）。
                              lerobot 的 π₀.₅ 对 transformers 有一条**硬校验**
                              （`policies/pi05/modeling_pi05.py:576-585`）：import
                              `transformers.models.siglip.check` 并调
                              `check_whether_transformers_replace_is_installed_correctly()`，
                              不通过就 raise `ValueError: An incorrect transformer version is used`。
                              ⇒「能不能跑 π₀.₅」的事实源是**这个函数**，不是版本区间：
                              PyPI 的 4.57.6（满足 §8.1 区间）被它拒绝（A2 已实测到 traceback），
                              git 分支 `fix/lerobot_openpi`@`dcddb970…`（版本字符串 4.53.3，
                              **低于**下界）才通过，且模型真的加载成功（params=3.617B）。
                              **判据**：① 功能校验必须 True（活体探针，秒级、CPU-only）；
                              ② git 安装时**装成记录**（lock / env_manifest）里必须有 commit_id
                              —— git 装的包只写 `4.53.3` 认不出是哪一次 build（裁定 34.1），
                              只在 dryrun 里出现不算（计划书 ≠ 装成记录，与 V-pi05-1 的 M4 同口径）；
                              ③ lock 记的值必须 == 活体实测值。
                              **红**：功能校验 False/ImportError；git 安装但装成记录无 commit；
                              lock 与实测不符（当前真实现场即此项：lock 记 4.57.6 / 实测 4.53.3）。
                              **本条不以版本区间为判据**——区间锚由 V-pi05-1 判，两者的冲突
                              已开 **RR-B2-06** 报 D（B2 不自行改 D 的锚，M26 立的规矩）。
V-pi05-6 manifest_selfconsistency  **2026-09-29 19:11 现场逼出来的第 6 条牙**（B2 只读实测）。
                              A2 的 `env_manifest.json` 不只交版本，还交一句**可用性结论**：
                              `env_usable = all(assertions) and not frozen_stack_drift`
                              （`a2_env_manifest.py:313`），并在 `verdict.blocked_if` 里自述
                              「drift 非空 ⇒ 断点变更，需 D 登记 + 重过 B2 闸」。
                              19:11 交件：assertions 9/9 全 true，但 drift=["torch","torchvision"]
                              ⇒ `env_usable=false`。B2 独立探针查实**不是漂移**：三个 venv 的
                              runtime `torch.__version__` 全是 `2.6.0+cu124`、`torch.version.cuda`
                              全是 `12.4`，只有 dist-info 目录名一个是 `torch-2.6.0+cu124.dist-info`、
                              两个基线是 `torch-2.6.0.dist-info`。
                              **判据**：① 交件必须自洽（env_usable == A2 自己的公式）；
                              ② env_usable 必须为 true；③ drift 点名的每个包由 B2 独立复核，
                              成因必须落到 real_runtime_drift / metadata_only / unexplained /
                              unverifiable 之一。
                              **红**：交件自相矛盾；`env_usable is False`（**无论成因**——真漂移
                              与"比对口径造成的假红"都红，判词点名是哪一种，修法归 A2、裁定归 D）。
                              **弃权**：manifest 缺失/不可解析，或三个可用性键缺一。
                              **键位置多通道**（20:0x 用 A2 真交件回放实测到）：`frozen_stack_drift`
                              在真 manifest 里**只**出现在 `verdict.*` 与 `baseline_comparison.*`，
                              顶层没有 ⇒ 只读顶层会对真交件弃权、对合成世界全绿（V-pi05-2 读 receipt
                              键名的同型缺陷）。现在按候选路径全找一遍，**多处命中值必须一致**，
                              不一致 ⇒ 红（M42），B2 不替 A2 挑一个采信。
                              ⇒ 已开 **RR-B2-07** 报 D。

四条本闸自己发现的**口径陷阱**（写进产物，防止后来者踩）
------------------------------------------------------
① **lock 对 CUDA 构建是盲的**（见下）。
② **receipt 的键名不是稳定契约**：A2 的真实 receipt 用 `expected_sha256_modelscope` /
   `expected_sha256_hf_lfs` / `expected_git_blob_sha1_hf` / `actual_size`，而本闸第一版只读
   `sha256` / `bytes` ⇒ 读不到就落进 `else: n_ok += 1`，**把「无从比对」记成「比对通过」**
   ——恒真牙，而且它坏的样子是"全绿"不是报错。现在：盘上值必须**命中至少一个**声明通道
   （sha256 / git blob sha1 / 字节数各按通道核），一个通道都读不到 ⇒ 判红；
   只有 receipt 自述值、没有远端期望值 ⇒ **UNJUDGED**（「没被动过」成立、「下对了东西」未证）。
   `.gitattributes` 就是靠 git blob sha1 才能定案的真实案例（HF 不给它的 LFS sha256）。
③ **版本号认不出 git 安装**（V-pi05-5）：`4.53.3` 可以是 `fix/lerobot_openpi` 分支的任何一次
   build，只有 `dist-info/direct_url.json` 里的 commit_id 能认出来。
④ **dist-info 元数据版本 ≠ runtime 版本**（V-pi05-6）：同一台机上两套已验收 venv 的
   `importlib.metadata.version('torch')` 是 `2.6.0`，而 `torch.__version__` 是 `2.6.0+cu124`
   （PyPI 轮子的 METADATA 不带 local version 段，download.pytorch.org 的带）。
   ⇒ 用 dist-info 串做「冻结栈是否漂移」的比对，会在**同一构建**上判出漂移（现场实测：
   A2 的 manifest 因此自述 `env_usable=false`）。判漂移的事实源必须是 runtime `__version__`
   （torch 再加 `torch.version.cuda`）；两个口径在判词里**分开记**，不混算（裁定 36.4）。
两套已验收 lock 的 pin 是 `torch==2.6.0`（**不带** `+cu124`；
`runs/infra/lerobot_act_env_20260928/requirements.lock.txt:93`），而 `torch.__version__` 才是
`2.6.0+cu124`，`importlib.metadata.version('torch')` 也只有 `2.6.0`。
⇒ **lock 文件与 dist 元数据对 CUDA 构建是盲的**：cu124 与 cu126/cu128 会写出**逐字节相同**的 pin 行。
所以 V-pi05-4 的事实源必须是**活体探针的 `torch.__version__`**，不是 lock；
拿 lock pin 去判「torch 栈没动」= 恒真（正是 B 的 G3 在 rlrobot 世系上能用 `+cu124` 判、
在 lerobot 世系上不能照搬的原因；照搬会造成本仓第 8 起同型的**假红**）。

三值纪律（A→B 移交单 `docs/a_handoff_to_b_pending_bucket_tristate_20260929.md` + 裁定 14）
----------------------------------------------------------------------------------------
每条 check 的 `ok` 是**三值**：`true`=通过、`false`=**实测到违例**、`null`=**证据不足/不适用**。
判据一律写成「`is False` 才算违例」，**不得**写成「`is not True`」（那会把「不适用」误判成「违规」）。
证据缺失 ⇒ `status="UNJUDGED"` + `ok=null`，**绝不**降级成 PASS；
顶层 `ok`（**唯一失败判据**，实现 = `ok_of()`）只有在 **0 RED 且 0 UNJUDGED** 时才为 true
（`admission_granted=true`）；`admission` 是**四值标签**：0 RED 且 0 UNJUDGED 但有 WARN ⇒
标签 `WARN` 而 `ok=true`（RR-B2-09 已裁：**WARN 不计失败但必须登记**，裁定 93 / D→B2 §四-1）。
⇒ **A2 还没交件时本闸必须输出 UNJUDGED，不是绿**。这是本闸最重要的一颗牙：
   准入闸对空目录放行 = 全项目最贵的假绿。

用法
----
    # ① 先证明牙在（写 mutation_verdict.json；A0 要求它与当前 gate_build 同构建）
    /root/venvs/rlrobot/bin/python scripts/b2_env_admission_pi05.py --selftest
    # ② 再判现场（A2 交件后）
    /root/venvs/rlrobot/bin/python scripts/b2_env_admission_pi05.py
    # 只跑 π₀.₅ 八条牙、不委派 B 的两个闸（省时间，但 admission 会因缺委派而 UNJUDGED）
    /root/venvs/rlrobot/bin/python scripts/b2_env_admission_pi05.py --no-delegate

AGENTS.md / 冻结纪律：本脚本**不删除任何文件**（禁 `rm`），自检临时目录用完一律
`shutil.move` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`；**只读** A2 的产物与两套已验收 venv；
写入面只有 `runs/vla/b2_env_admission_20260929/`（B2 自己的目录，带线前缀，裁定 38.3）。
不装环境、不下权重、不占 GPU（裁定 39.2：权重下载单线负责 = A2）。
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
RECYCLE_BIN = Path("/workspace/mnt/sppro/yhzhang91/recycle_bin")

# ---------------------------------------------------------------------------
# 锚值（事实源 = 本机实测 + D 的裁定；改这里等于改判据，须先报 D）
# ---------------------------------------------------------------------------
A2_DIR_DEFAULT = "runs/vla/a2_env_pi05_sim_20260929"
OUT_DIR_DEFAULT = "runs/vla/b2_env_admission_20260929"
PI05_VENV_DEFAULT = "/root/venvs/pi05_sim"
ACCEPTED_VENVS = ["/root/venvs/lerobot_act", "/root/venvs/lerobot_eval"]
LOCKS_0928_DIR = "runs/infra/lerobot_act_env_20260928"

LEROBOT_ANCHOR = "0.4.4"                 # 两套已验收 venv 实测（B2 本轮 17:1x 复核）
TORCH_ANCHOR = "2.6.0+cu124"             # 裁定 39.1 红线：逐字等于
TORCH_CUDA_ANCHOR = "12.4"
TORCH_STACK = ("torch", "torchvision", "torchcodec")
# 三个包各自的锚值。事实源：两套已验收 venv 的**活体探针**（B2 本轮 17:1x 实测
# lerobot_act / lerobot_eval 均为 torch 2.6.0+cu124 / torchvision 0.21.0+cu124 / torchcodec 0.10.0）
# + `runs/infra/lerobot_act_env_20260928/requirements.lock.txt:93-95` 的 pin（2.6.0 / 0.21.0 / 0.10.0）。
# 运行时还会拿已验收 venv 的活体值**回校**这张表：不符 ⇒ 判红并要求报 D 更新锚，不得就地放宽。
TORCH_STACK_ANCHORS = {"torch": "2.6.0+cu124", "torchvision": "0.21.0+cu124",
                       "torchcodec": "0.10.0"}
# lerobot 0.4.4 的 extra `transformers-dep`：transformers<5.0.0,>=4.57.1（裁定 39.1 实测 requires）
# **裁定 78.8 / 69：这个区间自 2026-09-30 02:5x 起是 `declared_only`，不是 blocking 判据。**
# 它来自 `importlib.metadata.requires('lerobot')` 的 extra，是**上游声明**；而 lerobot 的 π₀.₅
# 代码另有一条硬校验（`policies/pi05/modeling_pi05.py:576-584`，C2 独立读码带 file:line），
# 只接受 git 定制分支 `fix/lerobot_openpi`。两重实测把「以区间判红 = 对合规环境判红」钉死：
#   · A2 `runs/vla/a2_pi05_contract_20260929/probe_run1_transformers_blocker.log`：
#     PyPI **4.57.6**（满足区间）⇒ `ValueError: An incorrect transformer version is used`；
#   · A2 `runs/vla/a2_pi05_contract_20260929/load_verification.json`：git@`dcddb970` 的 **4.53.3**
#     ⇒ 模型真加载成功（params=3.617B）且 812/812 张量逐位相等。
# ⇒ 常量保留（回显上游声明、并用于登记「实测值落在区间外」这一事实），但**不得据此判红**。
TRANSFORMERS_FLOOR = "4.57.1"
TRANSFORMERS_CEIL = "5.0.0"
# ---- 裁定 78.8 的**实测锚**（V-pi05-1 的四条 blocking 判据用它，不用上面那个声明区间）----
# 事实源：A2 活体探针（`runs/vla/b2_env_admission_20260929/live_probe.json`）
#       + `runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt:111`（direct-url 带 commit）
#       + `runs/vla/a2_pi05_contract_20260929/load_verification.json`（verdict/compare/versions）
TRANSFORMERS_MEASURED_ANCHOR = "4.53.3"
TRANSFORMERS_GIT_COMMIT_ANCHOR = "dcddb970176382c0fcf4521b0c0e6fc15894dfe0"
TRANSFORMERS_GIT_BRANCH_ANCHOR = "fix/lerobot_openpi"
# 权重逐位核验件（π₀.₅ 真加载 + ckpt 812 张量逐位落进模型）
A2_LOAD_VERIFICATION = "runs/vla/a2_pi05_contract_20260929/load_verification.json"
LOAD_VERIFY_VERDICT_ANCHOR = "all_bitwise_equal"
LOAD_VERIFY_N_TENSORS_ANCHOR = 812
# 四条 blocking 判据的**成因键**（变异体用 must_contain 钉特异性，避免"红了但不知红在哪条"）
TF_CAUSE_VERSION = "tf_version_off_measured_anchor"
TF_CAUSE_COMMIT = "tf_git_commit_off_anchor"
TF_CAUSE_GUARD = "pi05_guard_check_failed"
TF_CAUSE_LOADVER = "load_verification_not_all_bitwise"
# 裁定 49.5 / 69.3 / 78（D→B2 §15-5 item 2 + §14.4-⑦）：渠道混用的**格式闭合载体**。
# A2 写、B2 只读引用（D 的原话：「你只需在闸里引用这份 sidecar，不必自己再填」）。
# 引用 ≠ 采信：sidecar 自述的四件事（receipt 未被改写 / 顶层是 mixed / C1–C5 / 逐文件覆盖）
# 一律由本闸**自己复算**，变异体 M64/M65 钉住"自称与事实不符必须红"。
A2_CHANNEL_SIDECAR = "runs/vla/a2_env_pi05_sim_20260929/weights_receipt_channel_sidecar.json"
# 裁定 96.2（RR-B2-05 的解铃载体，D 已点头）：**B2 自己写入面内**的一份新 JSON，与被 sha256
# 钉死的 receipt **同目录**，只装「哪些字段是外部未核实事实 + 指向 receipt 的 `sha256[:12]` + `as_of`」。
# 三条硬约束（D 的原文）：≤40 行（实测 39 行）· **不新增牙** · **不改 receipt 一个字节**。
# 引用 ≠ 采信：本闸按 receipt 的 sha256 **自己复算**决定采不采信 ⇒ 变异世界里的合成 receipt
# sha 不同 ⇒ sidecar 自动失效 ⇒ M32（正是这个形态的变异体）仍然红，牙不会被 sidecar 蒙住。
A2_EXTERNAL_SIDECAR = "runs/vla/a2_env_pi05_sim_20260929/receipt_sidecar_external_unverified.json"
CHANNEL_TOP_LEVEL_MIXED = "mixed"
FORBIDDEN_VENV_SUBSTR = ("maniskill_probe",)   # 裁定 39.1：实测 transformers 4.30.0，π₀.₅ 卫语句拒绝
WEIGHTS_SMALL_REQUIRED = ("config.json", "policy_preprocessor.json", "policy_postprocessor.json")
WEIGHTS_MIN_FILES = 7                     # hf-mirror API 实测 lerobot/pi05_base = 7 文件
CHANNELS_ALLOWED = ("modelscope", "hf_mirror", "huggingface", "local", "other")
# 外部来源事实的键名（裁定 36.4：必须标 external_unverified，不得与本机实测并列）
EXTERNAL_KEY_RE = re.compile(
    r"(license|last_?modified|vram|community|upstream|paper|docs_url|reported|external)", re.I)
# 「已标记为外部来源」的判法。第一版只认字面 token `external_unverified`，
# 结果对 A2 的真实 receipt 造了 3 条**假红**（`$.license` 明明写了
# `kind: "remote_api_read"` + `source: "HF API cardData.license / tags（https://hf-mirror.com）"`，
# `$.remote_hf.*` 明明待在一个**块名就声明了远端**的子树里）。
# 但**没有**因此放宽实质要求：外部声明值若躺在**实测块**里且无任何标记
# （真实案例 = `$.download.reported_size` 与 `measured_rate_MBps` 同一个 dict、
#   `$.verdict.license_ok` 与本地判定同一个 dict）⇒ **仍然红**，那才是裁定 36.4 要禁的并列。
# M31（全绿反向）/ M32（这两条必须红）双向钉住这个边界。
EXTERNAL_MARK_RE = re.compile(
    r"(external_unverified|external|remote_api|remote_read|remote_manifest|remote|"
    r"upstream|hf[-_ ]?api|modelscope|huggingface|hf-mirror|community_report|vendor|"
    r"third_party|外部|远端|上游|传闻)", re.I)
REMOTE_BLOCK_RE = re.compile(r"^(remote|upstream|external|vendor|manifest)_", re.I)
# 本机实测的键名（反向：这些**不得**出现在 external_unverified 块里）
MEASURED_KEY_RE = re.compile(r"(sha256|bytes|byte_size|size_bytes|elapsed|rate|mb_per_s|duration)", re.I)
# 「裸」实测键：在本 receipt 口径里它们**只**可能是本机实测值。带声明限定词的
# （upstream_published_sha256 / reported_vram_bytes / community_*）是**外部声明**，
# 合法地属于 external 块 ⇒ 不算违例（否则会造成本仓第 8 起同型的假红）。
MEASURED_BARE_KEYS = {"sha256", "bytes", "total_bytes", "size_bytes", "n_bytes",
                      "elapsed", "elapsed_sec", "duration_sec", "mb_per_s", "rate", "n_files"}
CLAIM_QUAL_RE = re.compile(
    r"(reported|community|upstream|claimed|alleged|external|published|third_party|rumou?r)", re.I)


def _is_bare_measured(key) -> bool:
    k = str(key).lower()
    if CLAIM_QUAL_RE.search(k):
        return False
    if k in MEASURED_BARE_KEYS:
        return True
    return "sha256" in k

PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)")
# `pip install`/resolver 输出里「触及某个包」的行形态（dryrun 解析）
RESOLVE_TOUCH_RE = re.compile(
    r"^\s*(?:Would\s+install|Installing|Collecting|Attempting\s+uninstall|Successfully\s+installed|"
    r"Uninstalling|Would\s+uninstall|Upgrading|Downgrading)\b(.*)$", re.I)
RESOLVE_ARROW_RE = re.compile(r"([A-Za-z0-9_.\-]+)\s+([0-9][^\s;,)]*)\s*->\s*([0-9][^\s;,)]*)")

STATUS_PASS, STATUS_WARN, STATUS_RED, STATUS_UNJUDGED = "PASS", "WARN", "RED", "UNJUDGED"
# `ok` 由 `status` **反推**（裁定 78.3：两者必须同源，否则汇总会造假红/恒真）。
# WARN 与 UNJUDGED 都映射到 `ok=None`（既不是"通过"也不是"违例"），差别只在
# `counts_as_non_green`：UNJUDGED 计入非绿（裁定 78.2 F1），WARN 不计入失败但要人看。
OK_FROM_STATUS = {STATUS_PASS: True, STATUS_RED: False,
                  STATUS_WARN: None, STATUS_UNJUDGED: None}
# 裁定 78.2：顶层四元组（`n_red / n_warn / n_unjudged / ok`）+ **`ok` 的判据必须写成散文可核的一句话**。
# ---- RR-B2-09 已由 D 裁定（裁定 93 + D→B2 执行单 20260930 §四-1）：这里发生过一次改判 ----
# 改判前（B2 自采的非字面读法，已作废但**不删记录**）：`ok == (n_red==0 且 n_unjudged==0 且
# n_warn==0)`，即连 WARN 也算不绿；当时还专门写了一段"逐条 `counts_as_non_green` 与顶层 `ok`
# 的口径**故意不同**（差一个 WARN）"来解释这个分裂。
# 改判后（现行）：D 的字面口径 = 「`ok` 是**唯一失败判据**、`UNJUDGED` 计入非绿、**WARN 不计失败
# 但必须登记**」。这不是放宽，理由有三条，全部落在产物里可核：
#   ① 判据的**严格性**没有变：RED 与 UNJUDGED 一样让 `ok=false`（O2/O3 两颗牙钉住）；
#   ② WARN 的**登记义务**没有变：`admission` 四值标签仍会给 `WARN`、`non_green[]` 仍逐条列、
#      新增的 `warn_registered_not_blocking` 块逐条给 why/owner/fix（O1 钉住"标签仍为 WARN"）；
#   ③ 被改掉的只有"WARN 是否等于失败"这一层 —— 而这一层的旧读法有**真实代价**：裁定 93.1 把
#      C2 的两颗牙从 RED 转成 WARN 之后，旧口径会让 C2 的主线臂被本闸的顶层 `ok` **二次判死**
#      （D 原话），即一个非违例的登记项被下游读成不合格（正是 F1 事故的反向形态）。
# 改判后逐条 `counts_as_non_green`（只覆盖 RED+UNJUDGED）与顶层 `ok` **同源**了，
# 上面那段"故意不同"的解释随之作废（判据与散文同源，裁定 27 / 35.3 / 37.4 / 78.3）。
OK_CALIBER_MARKER = "warn_registered_not_blocking"
OK_CRITERION = (
    "顶层 `ok` == (n_red == 0 且 n_unjudged == 0)；**WARN 不计失败但必须登记**"
    "（口径标记 `%s`）。裁定 78.2：`ok` 是唯一失败判据、**UNJUDGED 计入非绿**（RED=0 不得被"
    "下游读成干净）；裁定 93 / D→B2 执行单 20260930 §四-1（RR-B2-09 已裁）：WARN 不参与判失败，"
    "但 `admission` 四值标签仍是 `WARN`、`non_green[]` 仍逐条列、`warn_registered_not_blocking` "
    "块逐条给 why/owner/fix、退出码为 0。"
    "`admission` 是**标签**（PASS/WARN/UNJUDGED_evidence_missing/RED，登记义务），"
    "`admission_granted` == `ok`（放行决定）⇒ 标签为 WARN 时两者**故意不同**，差别写在 "
    "`warn_registered_not_blocking.why_label_and_decision_differ` 里。"
    "逐条 `counts_as_non_green` 只覆盖 RED+UNJUDGED，与本口径**同源**（RR-B2-09 改判后不再有"
    "「差一个 WARN」的分裂）。上一版把 WARN 也算进 `ok=false` 的读法已作废（历史见 RR-B2-09）。"
    % OK_CALIBER_MARKER)


def ok_of(n_red, n_unjudged, n_warn):
    """顶层 `ok` 的**唯一**实现（裁定 78.2 + 裁定 93 / D→B2 §四-1，RR-B2-09 已裁）。

    口径标记 `warn_registered_not_blocking`：WARN 被**看见**（收进签名、参与非负校验、
    必须登记），但**不参与判失败**。把 `n_warn` 留在签名里是故意的 —— 任何"顺手把 WARN 也
    AND 进去"的回退都会让自检 O1 判失败，而不是悄悄改判据（裁定 27.1：恒真/恒假的闸等于没有闸）。
    两处 `ok`（本闸顶层 `build_verdict` 与 `_normalize_guard_doc` 的归一副本）**必须调这一个函数**：
    裁定 78.2 的最小公共 check schema 是 B2 自己定的，两处各写一份就是"判据与散文不同源"。
    计数为 `None` ⇒ 抛错，**不许拿 None 顶替 0**（三值纪律：证据缺失不是"零违例"）。
    """
    for name, val in (("n_red", n_red), ("n_unjudged", n_unjudged), ("n_warn", n_warn)):
        if val is None or int(val) < 0:
            raise ValueError("%s 必须是非负整数计数，收到 %r（不许拿 None/负数顶替 0）"
                             % (name, val))
    return int(n_red) == 0 and int(n_unjudged) == 0


# 裁定 93.8 `reference_auditor_must_prove_its_own_pattern_coverage`（红线族；缺陷类 ⑲
# `green_verdict_from_an_under_covered_audit_pattern`）：自检 O5 是一个**源码模式审计器**
# （它断言「旧口径的写法已从代码里消失」）。这类审计器的失效形态不是"判错某一条"，而是
# 「**模式太窄 ⇒ 报绿，而绿是模式窄造成的**」—— 它带着"已审计"的形状，比没测更危险。
# ⇒ 做法：把已知坏形态注入一份**合成源码**（绝不动真件），逐条要求被抓到；抓不到 ⇒ O5 自己红。
# 同时带**好形态负对照**（不得误报）：否则"把模式放宽到什么都抓"也能过探针，那是恒红，同样是坏牙。
# 模式故意按"语义形态"写（引号种类、括号有无都可变），不按某一版的逐字节字面写。
LEGACY_OK_CALIBER_PATTERNS = (
    re.compile(r'"ok"\s*:\s*\(?\s*adm\s*==\s*[\'"]PASS[\'"]'),
    re.compile(r'"admission_granted"\s*:\s*\(?\s*adm\s*==\s*[\'"]PASS[\'"]'),
)
LEGACY_OK_CALIBER_WHY = ("RR-B2-09 改判前的写法：顶层 `ok` / `admission_granted` 由四值标签反推"
                         "（`adm == 'PASS'`）⇒ WARN 也被算成失败。改判后两者都必须调 `ok_of()`"
                         "（裁定 93 / D→B2 §四-1）。")


def _legacy_ok_caliber_hits(src_text):
    """返回 `src_text` 里命中的旧口径模式（空列表 = 没命中）。O5 与它的对照探针共用这一个实现。"""
    return [p.pattern for p in LEGACY_OK_CALIBER_PATTERNS if p.search(src_text or "")]

# 裁定 78.3：委托闸产物（B 的 G1–G5）的归一副本。原件是**证据**，一字节不动。
GUARD_DOC_GLOB = "delegated_g1_g5_*.json"
# 这个 glob **会误吞 B2 自己的一份产物**：`delegated_g1_g5_upstream_teeth.json`（裁定 78.4 的
# 甲层证据）名字前缀相同、但它不是 B 的 guard 判词、没有 `checks[]` 数组。本轮实测它被吞进去
# 归出了一份 0 条 check 的空副本 ⇒ 台账的 `n_source_docs` 虚高 1、`n_checks_total` 与 D 数的
# 45 条对不上账。排除名单显式写死（不留给"看着像就收"的模糊判断）。
GUARD_DOC_EXCLUDE_NAMES = ("delegated_g1_g5_upstream_teeth.json",)
# D 在裁定 78.3 里点名那 45 条 `id=null` 的**作用域**（9 份产物全在这个目录树下）。
# 写成常量是为了让「B2 扫到的」与「D 数的」能机器对账，而不是两段散文各说各话。
D_FINDING_SCOPE_DIR = "b2_env_admission_20260929"
D_FINDING_N_DOCS = 9
D_FINDING_N_CHECKS = 45
# 归一副本的布局版本。v1 = `normalized/<rel>`（只扫当前 out_dir）；
# v2 = `normalized/<源 out_dir 名>/<rel>`（跨轮扫全部 B2 准入目录，因为 D 数的 45 条
# 分散在 20260929 的 9 份历史产物里，只扫当天等于只修 10/45）。
# 换布局时旧副本**移进** `normalized/_superseded_layout1_<stamp>/`（不删、不改名原件，
# 裁定 92.4 `invalidation_never_renames_the_original` 的同族做法）。
NORMALIZED_LAYOUT_VERSION = 2
GUARD_G_EXPECTED = ("G1", "G2", "G3", "G4", "G5")
# B 的 `--selftest` 表格行：`M1   G1=RED     G1=RED     说明 ⇒ 抓住`
GUARD_SELFTEST_ROW_RE = re.compile(
    r"^(M\d+)\s+(G\d)=(\w+)\s+(G\d)=(\w+)\s+(.*?)\s*⇒\s*(.+?)\s*$")
GUARD_SELFTEST_SUM_RE = re.compile(r"变异测试：(\d+)/(\d+)\s*条判定符合预期")
# 上游 `--selftest` 的 **baseline 行**：`-    GREEN  GREEN  baseline_all_green（…）`
# 它没有 `M\d+` id、也没有 G 目标 ⇒ 上面的 ROW_RE 匹配不到它。但上游自己的
# `n_results`（"12/12"）是**把它算进去的** ⇒ 只解析变异行会得到 11，与 12 差 1。
# 那个差值必须能被解释（裁定 92.3-ii），所以这一行也要解析、也要落盘。
GUARD_SELFTEST_BASELINE_RE = re.compile(r"^-\s+(\w+)\s+(\w+)\s+(.*)$")


# git blob sha1 只在**小文件**上复算：HF 对非 LFS 文件（如 `.gitattributes`）只公布
# git blob sha1，不公布 LFS sha256 ⇒ 少了这条通道，那类文件在本闸里就是"无从比对"。
# 大文件不需要它（LFS 文件都有 sha256），而且再读一遍 14 GB 只为算 sha1 不值 ⇒ 设上限。
GIT_BLOB_MAX_BYTES = 64 << 20


def _git_blob_sha1(path: Path, bufsize: int = 1 << 22):
    """复算 git 的 blob 对象 sha1：`sha1("blob <len>\\0" + 内容)`。超过上限返回 None（附原因）。"""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > GIT_BLOB_MAX_BYTES:
        return None
    h = hashlib.sha1(b"blob %d\0" % size)
    with path.open("rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sha256_file(path: Path, bufsize: int = 1 << 22):
    """复算 sha256（小文件附带 git blob sha1）。返回 dict；文件不存在返回 None。

    返回键：`sha256` / `bytes` / `elapsed_sec` / `mb_per_s` / `git_blob_sha1`
    （`git_blob_sha1` 为 None 时表示**没算**——文件超过 GIT_BLOB_MAX_BYTES——不是"算出来是空"）。
    """
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    n = 0
    t0 = time.time()
    with path.open("rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
            n += len(b)
    el = time.time() - t0
    return {"sha256": h.hexdigest(), "bytes": n, "elapsed_sec": round(el, 3),
            "mb_per_s": round(n / (1 << 20) / el, 2) if el > 0 else None,
            "git_blob_sha1": _git_blob_sha1(path, bufsize)}


def _sha12(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception:
        return "0" * 12


def parse_pins(path: Path) -> dict:
    """`pip freeze` 格式 -> {名字: 版本}（跳过注释/空行/无 `==` 的行）。"""
    out = {}
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return out
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = PIN_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def norm_name(name: str) -> str:
    """PEP 503 规范化：小写 + `-`/`_`/`.` 折叠成 `-`（本仓已因大小写/下划线踩过假红）。"""
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def norm_channel_name(v) -> str:
    """把渠道表述归一到 `CHANNELS_ALLOWED` 的词表（认不出的原样返回，交给 unknown 判红）。

    与 `check_v_pi05_3` 里的 `_chan_tokens` 同一口径，但那一个是**拆词**（用于 receipt 的
    `sha256_verdict` 这类 `hf_lfs+modelscope` 复合串），这一个是**整名归一**（用于 sidecar 的
    `hf_mirror_snapshot` / `modelscope_curl_single_stream` 这类整名）。整名不拆词的理由与
    `remote_*` 块名相同：拆 `manifest_cross_check` 会得到 "cross"/"check" 这种伪渠道名（自造假红）。
    """
    t = str(v).strip().lower()
    if "modelscope" in t:
        return "modelscope"
    if "hf_mirror" in t or "hf-mirror" in t:
        return "hf_mirror"
    if "huggingface" in t:
        return "huggingface"
    return t


def _vtuple(v: str):
    """把版本串拆成 (数字元组, local 段)。'2.6.0+cu124' -> ((2,6,0),'cu124')；解析不出返回 (None, v)。"""
    if not isinstance(v, str):
        return None, v
    s = v.strip()
    local = ""
    if "+" in s:
        s, local = s.split("+", 1)
    nums = []
    for part in re.split(r"[.\-]", s):
        m = re.match(r"^(\d+)", part)
        if not m:
            break
        nums.append(int(m.group(1)))
    return (tuple(nums) if nums else None), local


def vge(a: str, b: str):
    """a >= b（只比数字段；解析失败返回 None ⇒ 调用方必须弃权，不许当 True）。"""
    ta, _ = _vtuple(a)
    tb, _ = _vtuple(b)
    if ta is None or tb is None:
        return None
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    return ta >= tb


class Report:
    """三值 check 容器。schema 与 B 的 `invariance_verdict.json` 同构（id/ok/observed/required/note），
    另加 `status`（PASS/WARN/RED/UNJUDGED）与 `red_when` / `ruling_ref` 两个纪律字段。"""

    def __init__(self):
        self.checks = []

    def add(self, cid, ok, observed, required, note="", status=None, ruling_ref="", red_when=""):
        """**`ok` 与 `status` 必须同源**（裁定 78.3）。

        旧版：调用方可以给 `ok` 又给 `status`，两者各写各的 ⇒ 转录 B 的 guard 时出现
        「`status="WARN"` 而 `ok=None`」这种组合，于是任何 `if c["ok"] is True` 的汇总把
        WARN 读成不合格（**假红**），任何 `if c["status"]=="RED"` 又对那两把闸**永远为假**（恒真）。
        现在：**`status` 是唯一事实源**，`ok` 由它反推；调用方传的 `ok` 只用于交叉校验，
        不一致就登记 `ok_status_disagreement`（不静默改写、也不静默丢弃 —— 三值纪律）。
        """
        if status is None:
            status = {True: STATUS_PASS, False: STATUS_RED, None: STATUS_UNJUDGED}[ok]
        ok_derived = OK_FROM_STATUS.get(status)
        disagree = (ok is not None and ok_derived is not None and bool(ok) != bool(ok_derived))
        self.checks.append({
            "id": cid, "ok": ok_derived, "observed": observed, "required": required, "note": note,
            "status": status, "ruling_ref": ruling_ref, "red_when": red_when,
            "counts_as_non_green": status in (STATUS_RED, STATUS_UNJUDGED),
            "ok_status_same_source": True,
            "ok_from_status": status,
            "ok_as_passed_by_caller": ok,
            "ok_status_disagreement": (("%r（调用方）vs %r（由 status 反推）⇒ 以 status 为准"
                                        % (ok, ok_derived)) if disagree else None),
        })
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


# ---------------------------------------------------------------------------
# 活体探针（裁定 31.2：`import` 成功不算过，要**版本号 + 安装来源**）
# ---------------------------------------------------------------------------
PROBE_CODE = """
import sys, json, importlib.metadata as md
out = {'exe': sys.executable, 'prefix': sys.prefix,
       'py': '.'.join(str(i) for i in sys.version_info[:3]),
       'pkgs': {}, 'dist': {}}
for m in __PACKAGES__:
    try:
        mod = __import__(m)
        out['pkgs'][m] = getattr(mod, '__version__', None)
    except Exception as e:
        out['pkgs'][m] = None
        out['import_error'] = out.get('import_error', {})
        out['import_error'][m] = type(e).__name__ + ': ' + str(e)[:200]
    try:
        out['dist'][m] = str(md.distribution(m)._path)
    except Exception as e:
        out['dist'][m] = None
        out['dist_error'] = out.get('dist_error', {})
        out['dist_error'][m] = type(e).__name__
try:
    import torch
    out['torch_version'] = torch.__version__
    out['torch_cuda'] = torch.version.cuda
except Exception as e:
    out['torch_version'] = None
    out['torch_cuda'] = None
    out['torch_error'] = type(e).__name__ + ': ' + str(e)[:200]
# 每个包的**安装来源**：git 装的包，版本字符串（4.53.3）根本认不出是哪个 commit，
# 只有 dist-info/direct_url.json 里有确切 URL+commit ⇒ 它才是 git 安装的溯源锚。
out['direct_url'] = {}
for m in __PACKAGES__:
    try:
        d = md.distribution(m)
        txt = d.read_text('direct_url.json')
        out['direct_url'][m] = json.loads(txt) if txt else None
    except Exception as e:
        out['direct_url'][m] = None
# lerobot 的 π₀.₅ 对 transformers 有一条**硬校验**（实测
# `lerobot/policies/pi05/modeling_pi05.py:576-585`）：它 import
# `transformers.models.siglip.check` 并调 `check_whether_transformers_replace_is_installed_correctly()`，
# 不通过就 raise ValueError("An incorrect transformer version is used")。
# ⇒ **能不能跑 π₀.₅ 的事实源是这个函数**，不是版本号区间（A2 实测：PyPI 的 4.57.6 被判不合格，
#   git@dcddb970 的 4.53.3 才通过）。B2 只读实测它，不猜。
out['pi05_transformers_check'] = {'ran': False}
try:
    from transformers.models.siglip import check as _sig
    out['pi05_transformers_check'] = {
        'ran': True, 'module': getattr(_sig, '__file__', None),
        'ok': bool(_sig.check_whether_transformers_replace_is_installed_correctly()),
    }
except Exception as e:
    out['pi05_transformers_check'] = {'ran': True, 'ok': False,
                                      'error': type(e).__name__ + ': ' + str(e)[:300]}
print(json.dumps(out))
"""


def probe_venv(venv: str | Path, packages=("lerobot", "torch", "torchvision", "transformers"),
               timeout=300):
    """实测某个 venv 的解释器 / 包版本 / dist-info 位置 / torch 的 CUDA 构建。

    不用 `%` 格式化拼代码：本仓已两次踩过「实参里的 `%d` 撞占位符」导致探针静默返回空
    （B 的 `b_env_provenance_guard.py:_probe_python` 注释、DR-011 的 T17 evidence 事故）。
    """
    venv = Path(venv)
    py = venv / "bin" / "python"
    rec = {"venv": str(venv), "is_symlink": venv.is_symlink(),
           "link_target": os.readlink(str(venv)) if venv.is_symlink() else None,
           "resolved": str(venv.resolve()) if venv.exists() else None,
           "python_exists": py.exists()}
    if not py.exists():
        rec["probe_error"] = "解释器不存在：%s" % py
        return rec
    # 不用 % 格式化：被探测代码里本身含 %d/%r
    code = PROBE_CODE.replace("__PACKAGES__", repr(list(packages)))
    try:
        r = subprocess.run([str(py), "-c", code], capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        rec["probe_error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    rec["probe_rc"] = r.returncode
    if r.returncode == 0 and (r.stdout or "").strip():
        try:
            rec.update(json.loads(r.stdout.strip().splitlines()[-1]))
        except Exception as e:
            rec["probe_error"] = "解析探针输出失败 %r；stderr=%s" % (e, (r.stderr or "")[-400:])
    else:
        rec["probe_error"] = "rc=%s stderr=%s" % (r.returncode, (r.stderr or "")[-600:])
    return rec


def read_pyvenv_cfg(venv: str | Path) -> dict:
    p = Path(venv)
    if p.is_symlink():
        p = p.resolve()
    cfg = p / "pyvenv.cfg"
    out = {"path": str(cfg), "exists": cfg.exists()}
    if not cfg.exists():
        return out
    for line in cfg.read_text(errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------
# 证据采集：把「文件层」与「探针层」收进一个 dict；缺失就是缺失，不补默认值
# ---------------------------------------------------------------------------
# receipt 里「期望值」的键名**不是**稳定契约。A2 的真实 receipt（2026-09-29 17:50:53 交件，
# `runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json`，只读实测）用的是
#   `expected_sha256_modelscope` / `expected_sha256_hf_lfs` / `actual_sha256` /
#   `expected_size_hf` / `expected_size_modelscope` / `actual_size`
# 而本闸第一版只读 `sha256` / `bytes` ⇒ 读不到就落进 `else: n_ok += 1`，
# **把「无从比对」记成「比对通过」**：那是恒真牙（裁定 27.1 的头号禁令），而且它红的样子
# 不是报错、是"全绿"。修法分两条：
#   ① 把**所有**声明通道都收进来，盘上值必须**命中至少一个**通道才算同一性成立；
#   ② 一个通道都读不到 ⇒ 该文件记 `uncomparable` 并判 RED（不是 PASS，也不是静默跳过）。
# 另：`actual_*` 是 receipt 的**自述**（A2 自己算的值），归到 `_claim`，与 `expected_*`
# （远端清单值，属外部来源）分开报 —— 前者只能证明「交件后盘上没被动过」，
# 后者才能证明「下对了东西」；两者都缺 ⇒ 连"没被动过"都证不了。
SHA256_EXPECT_KEYS = ("sha256", "expected_sha256", "expected_sha256_hf_lfs",
                      "expected_sha256_modelscope", "expected_sha256_hf",
                      "sha256_expected", "lfs_sha256", "checksum")
BYTES_EXPECT_KEYS = ("bytes", "size", "size_bytes", "expected_bytes", "expected_size",
                     "expected_size_hf", "expected_size_modelscope", "nbytes")
SHA256_CLAIM_KEYS = ("actual_sha256", "sha256_actual", "computed_sha256", "local_sha256")
BYTES_CLAIM_KEYS = ("actual_size", "actual_bytes", "size_actual", "local_size")
# HF 对**非 LFS 小文件**只公布 git blob sha1（A2 的真实 receipt 里 `.gitattributes` 就是这种：
# `expected_sha256_hf_lfs: null` + `expected_git_blob_sha1_hf: 427ddad0…`，实测 2026-09-29 17:50）。
# 不认这条通道 ⇒ 该文件在本闸里"无从比对"，而它其实是**能**比的。
GIT_BLOB_EXPECT_KEYS = ("expected_git_blob_sha1_hf", "expected_git_blob_sha1", "git_blob_sha1",
                        "blob_sha1", "expected_blob_sha1")
GIT_BLOB_CLAIM_KEYS = ("actual_git_blob_sha1", "git_blob_sha1_actual")


def _receipt_expectations(f: dict):
    """抽出条目里的**全部**期望通道：({键名: {"sha256":…, "bytes":…}}, claim)。

    通道名保留 receipt 的**原键名**，这样产物里能逐条追溯"盘上值命中的是哪个来源"，
    不用回头猜。`claim` = receipt 对自己算出来的值的自述。
    """
    chans = {}
    for k in SHA256_EXPECT_KEYS:
        v = f.get(k)
        if isinstance(v, str) and v:
            chans.setdefault(k, {})["sha256"] = v
    for k in BYTES_EXPECT_KEYS:
        v = f.get(k)
        if v is None or isinstance(v, bool):
            continue
        try:
            chans.setdefault(k, {})["bytes"] = int(v)
        except (TypeError, ValueError):
            continue
    for k in GIT_BLOB_EXPECT_KEYS:
        v = f.get(k)
        if isinstance(v, str) and v:
            chans.setdefault(k, {})["git_blob_sha1"] = v
    claim = {}
    for k in SHA256_CLAIM_KEYS:
        if isinstance(f.get(k), str) and f[k]:
            claim["sha256"], claim["sha256_key"] = f[k], k
            break
    for k in BYTES_CLAIM_KEYS:
        if f.get(k) is not None and not isinstance(f.get(k), bool):
            try:
                claim["bytes"], claim["bytes_key"] = int(f[k]), k
            except (TypeError, ValueError):
                pass
            break
    for k in GIT_BLOB_CLAIM_KEYS:
        if isinstance(f.get(k), str) and f[k]:
            claim["git_blob_sha1"], claim["git_blob_sha1_key"] = f[k], k
            break
    return chans, claim


def collect(root: Path, a2_dir: Path, venv: str, out_dir: Path, live=True,
            verify_sha256=True,
            packages=("lerobot", "torch", "torchvision", "torchcodec", "transformers"),
            ctrl_hz_doc=None, compat_report=None):
    ev = {
        "root": str(root), "a2_dir": str(a2_dir), "a2_dir_exists": a2_dir.exists(),
        "venv": str(venv), "live": bool(live), "verify_sha256": bool(verify_sha256),
        "files": {}, "lock_pins": None, "manifest": None, "receipt": None,
        "resolve_dryrun": None, "venv_probe": None, "accepted_venv_probe": None,
        "pyvenv_cfg": None, "sha256_recompute": None, "missing": [],
        "lock_text": None, "snapshot_taken_at": datetime.now().astimezone().isoformat(
            timespec="seconds"),
        # 裁定 78.8：π₀.₅ 真加载 + 权重逐位的核验件（V-pi05-1 的第 4 条 blocking 判据）
        "load_verification": None, "load_verification_path": None,
        # 裁定 49.5/69.3/78-2：渠道混用的格式闭合载体（V-pi05-3 只读引用 + 自己复算）
        "channel_sidecar": None, "channel_sidecar_path": None,
    }
    names = ["requirements.lock.txt", "env_manifest.json", "weights_receipt.json",
             "resolve_dryrun.txt"]
    for n in names:
        p = a2_dir / n
        st = p.stat() if p.exists() else None
        ev["files"][n] = {"path": str(p), "exists": p.exists(),
                          "sha256": _sha256_file(p)["sha256"] if p.exists() else None,
                          "bytes": st.st_size if st else None,
                          "mtime_ns": st.st_mtime_ns if st else None,
                          "mtime_iso": (datetime.fromtimestamp(st.st_mtime).astimezone()
                                        .isoformat(timespec="seconds")) if st else None}
        if not p.exists():
            ev["missing"].append(n)

    lp = a2_dir / "requirements.lock.txt"
    if lp.exists():
        ev["lock_pins"] = parse_pins(lp)
        ev["lock_pins_norm"] = {norm_name(k): v for k, v in ev["lock_pins"].items()}
        # **原文也在 collect 时点快照**：判定期间不重读文件。
        # 19:05 实测到过这个 race —— A2 在 19:04:54 重写了 lock，本闸的 lock_pins 是 19:03:5x 读的、
        # 而 V-pi05-5 在 19:05:0x 又重读了一次原文 ⇒ 同一份判词里同时出现
        # 「lock 记 4.57.6」与「lock 里有 dcddb970 commit」两句互相矛盾的话。
        try:
            ev["lock_text"] = lp.read_text(errors="replace")
        except Exception:
            ev["lock_text"] = ""
    mf = a2_dir / "env_manifest.json"
    if mf.exists():
        try:
            ev["manifest"] = json.loads(mf.read_text(errors="replace"))
        except Exception as e:
            ev["manifest"] = None
            ev["missing"].append("env_manifest.json(parse_error:%s)" % type(e).__name__)
    rc = a2_dir / "weights_receipt.json"
    if rc.exists():
        try:
            ev["receipt"] = json.loads(rc.read_text(errors="replace"))
        except Exception as e:
            ev["receipt"] = None
            ev["missing"].append("weights_receipt.json(parse_error:%s)" % type(e).__name__)
    dr = a2_dir / "resolve_dryrun.txt"
    if dr.exists():
        ev["resolve_dryrun"] = dr.read_text(errors="replace").splitlines()

    # 裁定 78.8 的第 4 条 blocking 判据的事实源：A2 的 `load_verification.json`
    # （`scripts/a2_verify_pi05_load.py` 产出：π₀.₅ 真 `from_pretrained` + 与 ckpt 逐张量比对）。
    # 它**不在** A2 的环境交件目录里（在 contract 目录），所以按 root 相对路径找，并同样
    # 在 collect() 时点一次性快照（sha256 + mtime）⇒ `check_inputs_stable` 也覆盖它。
    lv_p = root / A2_LOAD_VERIFICATION
    ev["load_verification_path"] = str(lv_p)
    lv_st = lv_p.stat() if lv_p.exists() else None
    ev["files"]["load_verification.json"] = {
        "path": str(lv_p), "exists": lv_p.exists(),
        "sha256": _sha256_file(lv_p)["sha256"] if lv_p.exists() else None,
        "sha12": _sha12(lv_p) if lv_p.exists() else None,
        "bytes": lv_st.st_size if lv_st else None,
        "mtime_ns": lv_st.st_mtime_ns if lv_st else None,
        "mtime_iso": (datetime.fromtimestamp(lv_st.st_mtime).astimezone()
                      .isoformat(timespec="seconds")) if lv_st else None,
        "note": "不在 a2_dir 的四份交件里（在 contract 目录）；裁定 78.8 新增的第 5 份证据"}
    if lv_p.exists():
        try:
            ev["load_verification"] = json.loads(lv_p.read_text(errors="replace"))
        except Exception as e:
            ev["load_verification"] = None
            ev["load_verification_parse_error"] = "%s: %s" % (type(e).__name__, e)

    # 裁定 49.5 / 69.3 / 78（§15-5 item 2）：A2 的渠道 sidecar。同样在 collect() 时点
    # **一次性快照**（sha256 + mtime）⇒ `check_inputs_stable` 也覆盖它，判定期间不重读。
    sc_p = root / A2_CHANNEL_SIDECAR
    ev["channel_sidecar_path"] = str(sc_p)
    sc_st = sc_p.stat() if sc_p.exists() else None
    ev["files"]["weights_receipt_channel_sidecar.json"] = {
        "path": str(sc_p), "exists": sc_p.exists(),
        "sha256": _sha256_file(sc_p)["sha256"] if sc_p.exists() else None,
        "sha12": _sha12(sc_p) if sc_p.exists() else None,
        "bytes": sc_st.st_size if sc_st else None,
        "mtime_ns": sc_st.st_mtime_ns if sc_st else None,
        "mtime_iso": (datetime.fromtimestamp(sc_st.st_mtime).astimezone()
                      .isoformat(timespec="seconds")) if sc_st else None,
        "note": "A2 写、B2 只读引用（裁定 49.5：顶层 `mixed` + 逐文件渠道）；不在 a2_dir 的四份交件里"}
    if sc_p.exists():
        try:
            ev["channel_sidecar"] = json.loads(sc_p.read_text(errors="replace"))
        except Exception as e:
            ev["channel_sidecar"] = None
            ev["channel_sidecar_parse_error"] = "%s: %s" % (type(e).__name__, e)

    # 裁定 96.2：external-unverified sidecar（B2 写入面）。同样在 collect() 时点**一次性快照**
    # （sha256 + mtime）⇒ `check_inputs_stable` 一并覆盖它，判定期间不重读。
    xs_p = root / A2_EXTERNAL_SIDECAR
    ev["external_sidecar_path"] = str(xs_p)
    xs_st = xs_p.stat() if xs_p.exists() else None
    ev["files"]["receipt_sidecar_external_unverified.json"] = {
        "path": str(xs_p), "exists": xs_p.exists(),
        "sha256": _sha256_file(xs_p)["sha256"] if xs_p.exists() else None,
        "sha12": _sha12(xs_p) if xs_p.exists() else None,
        "bytes": xs_st.st_size if xs_st else None,
        "mtime_ns": xs_st.st_mtime_ns if xs_st else None,
        "mtime_iso": (datetime.fromtimestamp(xs_st.st_mtime).astimezone()
                      .isoformat(timespec="seconds")) if xs_st else None,
        "note": ("B2 写（裁定 96.2 授权的载体）；只标注 receipt 里哪些字段是外部未核实事实，"
                 "不改 receipt、不新增牙")}
    if xs_p.exists():
        try:
            ev["external_sidecar"] = json.loads(xs_p.read_text(errors="replace"))
        except Exception as e:
            ev["external_sidecar"] = None
            ev["external_sidecar_parse_error"] = "%s: %s" % (type(e).__name__, e)
    else:
        ev["external_sidecar"] = None

    if live:
        ev["venv_probe"] = probe_venv(venv, packages)
        ev["pyvenv_cfg"] = read_pyvenv_cfg(venv)
        # V-pi05-6 的复核前提：A2 的 `env_manifest.json` 会自述一个 `baseline_venv`
        # （现场实测 = `/root/venvs/lerobot_act`），并用**dist-info 元数据版本**跟它比对来判
        # `frozen_stack_drift`。B2 要判「那句自述对不对」，就必须能对**同一个**基线 venv 做
        # 独立探针；所以这里把它并进来（若它已在 ACCEPTED_VENVS 里就不重复探）。
        acc_venvs = list(ACCEPTED_VENVS)
        man0 = ev.get("manifest")
        decl_base = ((man0.get("baseline_comparison") or {}).get("baseline_venv")
                     if isinstance(man0, dict) else None)
        if decl_base and decl_base not in acc_venvs:
            acc_venvs.append(decl_base)
        acc = {}
        for v in acc_venvs:
            acc[v] = probe_venv(v, ("lerobot", "torch", "torchvision", "torchcodec"))
        ev["accepted_venv_probe"] = acc
        ev["accepted_venvs_probed"] = acc_venvs
        ev["declared_baseline_venv"] = decl_base
        # 探针证据落盘（可复核；D 的口径是「不采信自述」）
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "live_probe.json").write_text(
                json.dumps({"venv_probe": ev["venv_probe"], "accepted_venv_probe": acc,
                            "pyvenv_cfg": ev["pyvenv_cfg"],
                            "accepted_venvs_probed": acc_venvs,
                            "declared_baseline_venv": decl_base}, indent=2, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # V-pi05-7 / V-pi05-8 的证据（裁定 45.5 / 44.2）。两条牙都**不采信交件自述**：
    # 频率牙自己按 1/(timestep×decimation) 复算，兼容目录牙自己读两侧 JSON 比步骤。
    ev["ctrl_hz_override"] = ctrl_hz_doc
    ev["ctrl_hz_docs"] = _load_json_docs(root, CTRL_HZ_CANDIDATES, ctrl_hz_doc)
    ev["compat"] = _collect_compat(root, venv, compat_report,
                                   receipt_recompute=ev.get("sha256_recompute"))

    # 权重 sha256 复算（14.47 GB 级；D 的 V-pi05-2 要求「必须可复算」）
    if ev["receipt"] and verify_sha256:
        wdir, files = _receipt_weights_dir(root, ev["receipt"])
        ev["weights_dir"] = str(wdir) if wdir else None
        rec = {}
        for f in files:
            rel = f.get("path") or f.get("name") or f.get("file")
            if not rel:
                continue
            p = (wdir / rel) if wdir else None
            got = _sha256_file(p) if (p and p.exists()) else None
            chans, claim = _receipt_expectations(f)
            rec[rel] = {
                # 全部声明通道（原键名 ⇒ 可追溯"命中的是哪个来源"）
                "expected_channels": chans,
                # receipt 的自述值（只能证"交件后没被动过"，不能证"下对了东西"）
                "receipt_claim": claim,
                # 兼容读法：产物里给一个"代表值"便于人读，判据**不用**它（用 expected_channels）
                "expected_sha256": next((c["sha256"] for c in chans.values()
                                         if c.get("sha256")), None),
                "expected_bytes": next((c["bytes"] for c in chans.values()
                                        if c.get("bytes") is not None), None),
                "on_disk": got, "exists": bool(p and p.exists()),
                "receipt_self_verdict": {k: f.get(k) for k in
                                         ("present", "size_ok", "sha256_match_modelscope",
                                          "sha256_match_hf_lfs", "sha256_verdict",
                                          "critical_silent_default", "required")
                                         if k in f},
            }
        ev["sha256_recompute"] = rec
        # 盘上实际有哪些文件（用来抓「receipt 少报」与「半成品快照」两个方向）
        if wdir and wdir.exists():
            ev["weights_on_disk"] = sorted(
                str(q.relative_to(wdir)) for q in wdir.rglob("*") if q.is_file())
    return ev


def _receipt_weights_dir(root: Path, receipt: dict):
    """从 receipt 里定位权重目录与文件清单。容忍多种键名（A2 的 receipt 形态未定稿）。"""
    if not isinstance(receipt, dict):
        return None, []
    cand = None
    for k in ("local_path", "weights_dir", "dir", "path", "snapshot_dir", "local_dir",
              "download_dir", "target_dir"):
        v = receipt.get(k)
        if isinstance(v, str) and v:
            cand = v
            break
    for k in ("files", "file_list", "entries", "items"):
        v = receipt.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            for kk in ("dir", "parent", "root"):
                if isinstance(v[0].get(kk), str):
                    cand = cand or v[0][kk]
    wdir = None
    if cand:
        p = Path(cand)
        wdir = p if p.is_absolute() else (root / p)
    files = []
    for k in ("files", "file_list", "entries", "items"):
        v = receipt.get(k)
        if isinstance(v, list):
            files = [x for x in v if isinstance(x, dict)]
            break
    # 清单也可能是 {name: {sha256:..}} 的字典形态
    if not files:
        for k in ("files", "sha256", "checksums"):
            v = receipt.get(k)
            if isinstance(v, dict) and v:
                files = [{"path": name, **(meta if isinstance(meta, dict) else {"sha256": meta})}
                         for name, meta in v.items()]
                break
    return wdir, files


# ---------------------------------------------------------------------------
# A0 —— 牙必须**当下**是证明过的（防止「改完判据不重跑自检」＝ V9 的同型纪律）
# ---------------------------------------------------------------------------
def check_a0_teeth(ev, rep, out_dir: Path):
    gate_build = _sha12(Path(__file__))
    p = out_dir / "mutation_verdict.json"
    req = ("mutation_verdict.json 存在、all_ok=true、且其 gate_build == 当前脚本构建 %s" % gate_build)
    red = "自检 all_ok=false（有变异没被抓住）；或 gate_build != 当前构建（改了判据没重跑自检）"
    if not p.exists():
        rep.add("A0_teeth_current", None, "mutation_verdict.json 不存在（%s）" % p, req,
                note="**先跑 `--selftest`**：准入闸在未证明牙在之前不得给 PASS（裁定 27.1）。"
                     "证据缺失按三值纪律记 UNJUDGED，不记 PASS 也不记 RED。",
                ruling_ref="裁定 27.1 / 裁定 39.1（必须双向有牙）", red_when=red)
        return
    try:
        doc = json.loads(p.read_text(errors="replace"))
    except Exception as e:
        rep.add("A0_teeth_current", False, "mutation_verdict.json 解析失败（%s）" % type(e).__name__,
                req, note="坏掉的自检产物等于没有自检", ruling_ref="裁定 27.1", red_when=red)
        return
    bad = []
    if doc.get("all_ok") is not True:
        bad.append("all_ok=%r（n_ok=%s/%s）" % (doc.get("all_ok"), doc.get("n_ok"),
                                               doc.get("n_mutations")))
    if doc.get("gate_build") != gate_build:
        bad.append("gate_build=%s != 当前 %s" % (doc.get("gate_build"), gate_build))
    missed = [m.get("id") for m in (doc.get("mutations") or []) if m.get("ok") is not True]
    if missed:
        bad.append("未达预期的变异：%s" % ",".join(str(x) for x in missed))
    obs = {"all_ok": doc.get("all_ok"), "n_ok": doc.get("n_ok"),
           "n_mutations": doc.get("n_mutations"), "gate_build": doc.get("gate_build"),
           "baseline_all_green": doc.get("baseline_all_green"), "violations": bad}
    rep.add("A0_teeth_current", not bad, obs, req,
            note="双向牙：%s 条变异（含 %s 条反向 NOT_RED）"
                 % (doc.get("n_mutations"), doc.get("n_reverse")),
            ruling_ref="裁定 27.1 / 裁定 39.1", red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-1 —— 版本锚
# ---------------------------------------------------------------------------
def check_v_pi05_1(ev, rep):
    ref = ("**裁定 78.8 + 裁定 69**（transformers 改判：§8.1 的声明区间降 `declared_only`、"
           "改钉实测锚 + git commit + 功能校验 + 权重逐位）/ 裁定 39.1（依赖红线）/ "
           "裁定 34.1（钉实际装成的值、不回退；引用差异必须点名包与版本）/ "
           "C2 独立读码 `lerobot/policies/pi05/modeling_pi05.py:576-584`（第二重证据，带 file:line）")
    req = ("lerobot 实际装成版本 == 两套已验收 venv（现值 %s）；transformers 满足**四条 blocking**："
           "① 活体实测版本 == 实测锚 `%s`；② 装成记录（requirements.lock.txt / 活体 direct_url）里"
           "有 git commit `%s`（分支 `%s`）；③ lerobot 的 π₀.₅ 硬校验 `%s` **真跑通过**；"
           "④ `%s` 的 `verdict == %s` 且 `n_compared == n_bitwise_exact == %d`、`n_differ == 0`、"
           "`n_model_keys_not_covered_by_ckpt == 0`；外加「实际装成版本写进产物」（裁定 34.1）；"
           "venv 不是 maniskill_probe。**§8.1 的声明区间 `>=%s,<%s` 只登记（declared_only）、不判红。**"
           % (LEROBOT_ANCHOR, TRANSFORMERS_MEASURED_ANCHOR, TRANSFORMERS_GIT_COMMIT_ANCHOR[:12],
              TRANSFORMERS_GIT_BRANCH_ANCHOR, PI05_TF_CHECK_PATH, A2_LOAD_VERIFICATION,
              LOAD_VERIFY_VERDICT_ANCHOR, LOAD_VERIFY_N_TENSORS_ANCHOR,
              TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL))
    red = ("lerobot 版本与已验收值不同（点名包与版本）；transformers 缺失；"
           "[%s] 实测版本 != `%s`；[%s] 装成记录里没有 commit `%s`（或活体 commit 与之不符）；"
           "[%s] π₀.₅ 硬校验不是 True；[%s] load_verification 的 verdict != `%s` 或 "
           "812/812/0/0 四个计数任一不符；实测已装但产物里查不到该版本；"
           "venv realpath 落在 maniskill_probe。**注意：低于声明下界 %s 本身不是红**"
           "（裁定 78.8：满足区间的 PyPI 4.57.6 被 lerobot 硬校验拒绝，A2 已实测）"
           % (TF_CAUSE_VERSION, TRANSFORMERS_MEASURED_ANCHOR, TF_CAUSE_COMMIT,
              TRANSFORMERS_GIT_COMMIT_ANCHOR[:12], TF_CAUSE_GUARD, TF_CAUSE_LOADVER,
              LOAD_VERIFY_VERDICT_ANCHOR, TRANSFORMERS_FLOOR))
    vp = ev.get("venv_probe")
    if not ev.get("live") or not vp or vp.get("probe_error") or "pkgs" not in vp:
        rep.add("V-pi05-1_version_anchor", None,
                "活体探针不可得（live=%s，probe_error=%s）" % (ev.get("live"), (vp or {}).get("probe_error")),
                req, note="证据不足 ⇒ 弃权，不当作通过（裁定 14 的同型纪律：不得把「查不到」读成「没问题」）",
                ruling_ref=ref, red_when=red)
        return
    pkgs = vp.get("pkgs") or {}
    bad, obs, unjudged = [], {}, []

    # (1) 禁止复用 maniskill_probe（裁定 39.1 明令）。
    #     **成因口径已随裁定 78.8 改写**：不再说「低于硬下界 4.57.1」——那个下界现在是
    #     `declared_only`，拿它当红的理由就是本闸自己刚被 D 判掉的那条假红。
    #     改写时踩过一个坑，记在这里：**第一版新文案写成「四条 blocking 逐条不中：① 实测
    #     transformers 偏锚…」，那是一句关于「本世界探针读数」的断言**，而本条判据的成立
    #     **只依赖 venv 路径**、不依赖本世界的 transformers 读数（隔离变异体 M66 就是路径违规
    #     而 transformers 合规的世界）⇒ 那句话在 M66 上会是**假话**（裁定 92.5 缺陷类 ⑱
    #     「为自圆其说而虚构依据」的同族：值错了，还配一个站不住的解释）。
    #     所以现在的写法把两件事分开：① 本条判据的**成立条件**只写路径；② 禁用它的**实测理由**
    #     显式标明出处是裁定 39.1（那是关于**那个 venv** 的既成实测，不是关于本世界的断言）。
    resolved = str(vp.get("resolved") or "")
    obs["venv_resolved"] = resolved
    for sub in FORBIDDEN_VENV_SUBSTR:
        if sub in resolved:
            bad.append("venv realpath 落在 `%s` ⇒ 裁定 39.1 **明令**不得用它跑 π₀.₅。"
                       "本条判据的成立**只依赖路径**，与 transformers 的四条 blocking **相互独立**："
                       "那四条在同一条 check 里单独判、单独给成因键（%s/%s/%s/%s），"
                       "不因本条命中而省略、也不被本条代替。禁用它的**实测理由**（出处＝裁定 39.1，"
                       "是关于那个 venv 的既成实测，不是对本世界探针的断言）：其 transformers 实测 "
                       "4.30.0 既偏实测锚 `%s`、又没有定制分支 `%s` 自带的 `check.py`"
                       "（π₀.₅ 硬卫语句必为 False）⇒ 形态就是裁定 39.1 说的「import 成功但加载权重"
                       "报错」。**也不是**因为低于声明下界 %s（该下界 `declared_only`，裁定 78.8）"
                       % (sub, TF_CAUSE_VERSION, TF_CAUSE_COMMIT, TF_CAUSE_GUARD, TF_CAUSE_LOADVER,
                          TRANSFORMERS_MEASURED_ANCHOR, TRANSFORMERS_GIT_BRANCH_ANCHOR,
                          TRANSFORMERS_FLOOR))

    # (2) lerobot 版本锚：与**两套已验收 venv 的实测值**比，不与常量比（常量只作兜底并回显来源）
    new_lr = pkgs.get("lerobot")
    acc = ev.get("accepted_venv_probe") or {}
    acc_vals, acc_unprobed = {}, []
    for v, pr in acc.items():
        if pr.get("pkgs") and pr["pkgs"].get("lerobot"):
            acc_vals[v] = pr["pkgs"]["lerobot"]
        else:
            acc_unprobed.append(v)
    obs["lerobot_new"] = new_lr
    obs["lerobot_accepted"] = acc_vals
    obs["lerobot_accepted_unprobed"] = acc_unprobed
    obs["lerobot_anchor_constant"] = LEROBOT_ANCHOR
    if acc_unprobed:
        bad.append("已验收 venv %s 探不到 lerobot 版本 ⇒ 版本锚**无法比对**（不是「相同」）"
                   % ",".join(acc_unprobed))
    if not new_lr:
        bad.append("新环境探不到 lerobot 版本（pkgs.lerobot=%r；dist=%r）"
                   % (new_lr, (vp.get("dist") or {}).get("lerobot")))
    else:
        for v, want in acc_vals.items():
            if new_lr != want:
                bad.append("**lerobot**：新环境 `%s` != 已验收 %s `%s`（裁定 34.1：差异必须点名包与版本，"
                           "不得写成「差异可忽略」；lerobot 版本变更 = 断点变更，须 D 登记）"
                           % (new_lr, v, want))
        if acc_vals and set(acc_vals.values()) != {LEROBOT_ANCHOR}:
            bad.append("已验收 venv 自身与锚常量 %s 不一致：%s ⇒ 锚常量需报 D 更新，不得就地放宽"
                       % (LEROBOT_ANCHOR, acc_vals))

    # (3) transformers：**裁定 78.8 改判**——四条 blocking 判据全是实测，声明区间只登记。
    #     ① 实测版本 == 4.53.3（实测锚）        ② 装成记录里有 git commit dcddb970…
    #     ③ lerobot 的 π₀.₅ 硬校验真跑通过      ④ load_verification = all_bitwise_equal（812/812/0/0）
    #     为什么不再以区间判红（两重证据，不得再以声明下界判红）：
    #       · D 裁定 78.8：`extra` 声明的 `>=4.57.1` 属 `declared_only`；
    #       · C2 独立读码 `modeling_pi05.py:576-584`：真卫语句是 siglip 的
    #         `check_whether_transformers_replace_is_installed_correctly()`，**不是版本区间**，
    #         而该分支的 `check.py` 只接受 4.53.2 / 4.53.3 ⇒ **装 >=4.57.1 会让 π₀.₅ 直接加载失败**
    #         （A2 用 PyPI 4.57.6 实测到 `ValueError: An incorrect transformer version is used`）。
    tf = pkgs.get("transformers")
    obs["transformers_new"] = tf
    obs["transformers_measured_anchor"] = TRANSFORMERS_MEASURED_ANCHOR
    obs["transformers_git_commit_anchor"] = TRANSFORMERS_GIT_COMMIT_ANCHOR
    # ---- 声明区间：`declared_only`（登记事实，**不进 bad**）----
    ge = vge(tf, TRANSFORMERS_FLOOR) if tf else None
    lt = (vge(TRANSFORMERS_CEIL, tf) and tf != TRANSFORMERS_CEIL) if tf else None
    obs["transformers_declared_interval"] = {
        "bound": ">=%s,<%s" % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL),
        "source": "`importlib.metadata.requires('lerobot')` 的 extra `transformers-dep`（**上游声明**）",
        "status": "declared_only_not_blocking",
        "ruling_ref": "裁定 78.8 / 裁定 69（D→B2 §15-5 item 1）",
        "measured": tf,
        "measured_falls_inside_declared_interval": (bool(ge and lt) if tf else None),
        "why_not_blocking":
            "满足该区间的 PyPI 4.57.6 被 lerobot 的 π₀.₅ 硬校验**拒绝**"
            "（`ValueError: An incorrect transformer version is used`，A2 实测）；"
            "通过校验的是 git 分支 `%s`@`%s`，版本串 `%s` **低于**下界，且 812/812 张量逐位相等 "
            "⇒ 以声明下界判红 = 对**合规**环境判红（假红）。故区间只登记、不判红。"
            % (TRANSFORMERS_GIT_BRANCH_ANCHOR, TRANSFORMERS_GIT_COMMIT_ANCHOR[:12],
               TRANSFORMERS_MEASURED_ANCHOR),
        "evidence": [
            "runs/vla/a2_pi05_contract_20260929/probe_run1_transformers_blocker.log（PyPI 4.57.6 ⇒ ValueError）",
            "runs/vla/a2_pi05_contract_20260929/load_verification.json（git@dcddb970 的 4.53.3 ⇒ 加载成功、812/812 逐位）",
            "runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt:111（direct-url 装成记录带 commit）",
            "lerobot/policies/pi05/modeling_pi05.py:576-584（C2 独立读码：真卫语句是 siglip check，不是区间）"],
    }
    obs["transformers_bound"] = ">=%s,<%s（lerobot %s extra `transformers-dep`；**declared_only**）" % (
        TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL, LEROBOT_ANCHOR)
    if not tf:
        bad.append("**transformers**：未安装（%r）⇒ π₀.₅ `from_pretrained` 必失败；"
                   "注意它不在 lerobot 核心依赖里，正确装法是 `lerobot[transformers-dep]==%s`"
                   % (pkgs.get("transformers"), LEROBOT_ANCHOR))
    else:
        # ① 实测锚（逐字相等；git 构建的版本串认不出 commit，所以还要 ②）
        if tf != TRANSFORMERS_MEASURED_ANCHOR:
            bad.append("[%s] **transformers**：活体实测 `%s` != 实测锚 `%s`"
                       "（裁定 78.8：锚是 A2 那套**已验证能加载 π₀.₅** 的 git 构建；"
                       "换版本 = 换断点，须 D 登记后更新锚，不得就地放宽）"
                       % (TF_CAUSE_VERSION, tf, TRANSFORMERS_MEASURED_ANCHOR))
        # ② git commit 溯源：活体 direct_url **与** 装成记录（lock 原文）都要有锚 commit
        du = (vp.get("direct_url") or {}).get("transformers") if vp.get("direct_url") else None
        vcs = (du or {}).get("vcs_info") or {}
        commit_live = vcs.get("commit_id")
        lock_text = ev.get("lock_text") or ""
        commit_in_lock = TRANSFORMERS_GIT_COMMIT_ANCHOR in lock_text
        obs["transformers_git"] = {
            "live_commit": commit_live, "live_branch": vcs.get("requested_revision"),
            "install_url": (du or {}).get("url"),
            "anchor_commit": TRANSFORMERS_GIT_COMMIT_ANCHOR,
            "anchor_commit_in_lock_text": commit_in_lock,
            "lock_evidence": "runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt:111",
            "lock_text_present": bool(lock_text),
        }
        if commit_live and commit_live != TRANSFORMERS_GIT_COMMIT_ANCHOR:
            bad.append("[%s] **transformers**：活体 direct_url 的 commit `%s` != 锚 `%s`"
                       "（git 构建的版本串 `%s` 可以是该分支任何一次 build ⇒ 只有 commit 能认出来；"
                       "裁定 34.1 钉实际装成的值）"
                       % (TF_CAUSE_COMMIT, commit_live, TRANSFORMERS_GIT_COMMIT_ANCHOR[:12], tf))
        if not commit_in_lock:
            if lock_text:
                bad.append("[%s] **transformers**：装成记录 `requirements.lock.txt` 里查不到锚 commit "
                           "`%s`（原文 %d 字节已快照）⇒ 无法证明装的是那一次 build"
                           % (TF_CAUSE_COMMIT, TRANSFORMERS_GIT_COMMIT_ANCHOR[:12], len(lock_text)))
            else:
                unjudged.append("`requirements.lock.txt` 不可读/不存在 ⇒ 「装成记录里有锚 commit」"
                                "这一条**无法判**（三值纪律：记 UNJUDGED，不当作通过也不当作违例）")
        # 「实际装成版本必须写进产物」：lock 或 manifest 里必须能查到这个**逐字**版本
        where = []
        lp = (ev.get("lock_pins_norm") or {}).get("transformers")
        if lp == tf:
            where.append("requirements.lock.txt")
        elif lp:
            bad.append("**transformers**：产物 `requirements.lock.txt` 记 `%s`，与实测 `%s` 不符"
                       "（裁定 34.1：钉**实际装成**的值）" % (lp, tf))
        try:
            mtxt = json.dumps(ev.get("manifest"), ensure_ascii=False) if ev.get("manifest") else ""
        except Exception:
            mtxt = ""
        if tf in mtxt:
            where.append("env_manifest.json")
        obs["transformers_recorded_in"] = where
        # 三值细化（裁定 14 的同型纪律）：**产物本身不存在** ⇒ 这条无法判，记弃权；
        # 产物存在却没记 ⇒ 才是违例。第一版把两者都判 RED，会把「A2 还在施工、lock 未落盘」
        # 误读成「A2 交付了不可复现的产物」——那是假红，而且是最容易激化跨线误会的那一种。
        arts = ev.get("files") or {}
        art_present = [n for n in ("requirements.lock.txt", "env_manifest.json")
                       if (arts.get(n) or {}).get("exists")]
        obs["recording_artifacts_present"] = art_present
        if not art_present:
            unjudged.append("`requirements.lock.txt` 与 `env_manifest.json` 都不存在 ⇒ "
                            "「实际装成版本已写进产物」这一条**无法判**（A2 的 G0 产物尚未落盘）；"
                            "按三值纪律记 UNJUDGED，不记 RED（那不是违例，是还没交件）")
        elif not where:
            bad.append("**transformers**：实测已装 `%s`，但已落盘的产物（%s）里都查不到该版本 "
                       "⇒ 产物不可复现（裁定 34.1：必须钉**实际装成**的值）"
                       % (tf, ",".join(art_present)))

    # ③ 卫语句**真跑通过**（裁定 78.8：能不能跑 π₀.₅ 的事实源是这个函数，不是版本区间）
    chk = vp.get("pi05_transformers_check") or {}
    obs["pi05_guard_check"] = {
        "path": PI05_TF_CHECK_PATH, "ran": chk.get("ran"), "ok": chk.get("ok"),
        "error": chk.get("error"),
        "why_blocking": "lerobot `policies/pi05/modeling_pi05.py:576-584` 在 `from_pretrained` 路径上"
                        "直接 `raise ValueError` ⇒ 这条不过，π₀.₅ 一步都跑不了",
        "cross_ref": "V-pi05-5_transformers_pi05_ready（同一事实源，那条另判 git 溯源与 lock 一致性）",
    }
    if not chk.get("ran"):
        unjudged.append("活体探针没跑到 `%s`（探针版本旧了？）⇒ 卫语句这一条**无法判**"
                        "（三值纪律：弃权，不当作通过）" % PI05_TF_CHECK_PATH)
    elif chk.get("ok") is not True:
        bad.append("[%s] **lerobot 的 π₀.₅ 硬校验不通过**（`%s` 实测 %r，error=%s）⇒ "
                   "`PI05Policy.from_pretrained` 会抛 `ValueError: An incorrect transformer "
                   "version is used`（A2 已实测到该 traceback）"
                   % (TF_CAUSE_GUARD, PI05_TF_CHECK_PATH, chk.get("ok"), chk.get("error")))

    # ④ 权重逐位核验件：π₀.₅ 真加载过、且 ckpt 的 812 张量逐位落进模型
    lv = ev.get("load_verification")
    lv_meta = (ev.get("files") or {}).get("load_verification.json") or {}
    lv_obs = {"path": ev.get("load_verification_path"), "exists": lv_meta.get("exists"),
              "sha12": lv_meta.get("sha12"), "bytes": lv_meta.get("bytes"),
              "mtime_iso": lv_meta.get("mtime_iso"),
              "required_verdict": LOAD_VERIFY_VERDICT_ANCHOR,
              "required_counts": {"n_compared": LOAD_VERIFY_N_TENSORS_ANCHOR,
                                  "n_bitwise_exact": LOAD_VERIFY_N_TENSORS_ANCHOR,
                                  "n_differ": 0, "n_model_keys_not_covered_by_ckpt": 0}}
    if not isinstance(lv, dict):
        lv_obs["parse_error"] = ev.get("load_verification_parse_error")
        unjudged.append("`%s` 不存在或不可解析（exists=%r，parse_error=%r）⇒ 「π₀.₅ 真加载 + 权重逐位」"
                        "这一条**无法判**（三值纪律：不是违例，是还没交件/交件坏了；不得读成通过）"
                        % (A2_LOAD_VERIFICATION, lv_meta.get("exists"),
                           ev.get("load_verification_parse_error")))
    else:
        cmp_ = lv.get("compare") or {}
        n_c, n_b = cmp_.get("n_compared"), cmp_.get("n_bitwise_exact")
        n_d, n_unc = cmp_.get("n_differ"), cmp_.get("n_model_keys_not_covered_by_ckpt")
        verdict = lv.get("verdict")
        lv_obs.update({"verdict": verdict, "n_compared": n_c, "n_bitwise_exact": n_b,
                       "n_differ": n_d, "n_model_keys_not_covered_by_ckpt": n_unc,
                       "n_shape_mismatch": cmp_.get("n_shape_mismatch"),
                       "n_ckpt_keys_not_in_model": cmp_.get("n_ckpt_keys_not_in_model"),
                       "safetensors_n_tensors_in_file": (lv.get("safetensors") or {}).get(
                           "n_tensors_in_file"),
                       "versions": lv.get("versions"),
                       "n_parameters": lv.get("n_parameters"),
                       "generated_at": lv.get("generated_at")})
        if verdict is None or None in (n_c, n_b, n_d, n_unc):
            unjudged.append("`%s` 存在但缺 `verdict` / `compare` 的四个计数（实测 verdict=%r，"
                            "n_compared=%r，n_bitwise_exact=%r，n_differ=%r，"
                            "n_model_keys_not_covered_by_ckpt=%r）⇒ 无法判，弃权"
                            % (A2_LOAD_VERIFICATION, verdict, n_c, n_b, n_d, n_unc))
        else:
            if verdict != LOAD_VERIFY_VERDICT_ANCHOR:
                bad.append("[%s] **load_verification 的 verdict = `%s` != `%s`**"
                           "（裁定 78.8 的第 4 条 blocking：π₀.₅ 必须真加载且权重逐位相等）"
                           % (TF_CAUSE_LOADVER, verdict, LOAD_VERIFY_VERDICT_ANCHOR))
            if not (n_c == n_b == LOAD_VERIFY_N_TENSORS_ANCHOR):
                bad.append("[%s] **load_verification 的比对口径偏锚**：n_compared=%r / "
                           "n_bitwise_exact=%r，锚是 %d/%d（ckpt `model.safetensors` 的张量数）"
                           "⇒ 换 ckpt = 换断点，须 D 登记后更新锚"
                           % (TF_CAUSE_LOADVER, n_c, n_b,
                              LOAD_VERIFY_N_TENSORS_ANCHOR, LOAD_VERIFY_N_TENSORS_ANCHOR))
            if n_d != 0:
                bad.append("[%s] **load_verification 有 %r 个张量不逐位相等**（n_differ 必须 == 0）"
                           % (TF_CAUSE_LOADVER, n_d))
            if n_unc != 0:
                bad.append("[%s] **load_verification 有 %r 个模型键没被 ckpt 覆盖**"
                           "（n_model_keys_not_covered_by_ckpt 必须 == 0；非空 ⇒ 那些键保持随机初始化）"
                           % (TF_CAUSE_LOADVER, n_unc))
            lv_tf = (lv.get("versions") or {}).get("transformers")
            lv_obs["cross_check_transformers"] = {"load_verification": lv_tf, "live_probe": tf,
                                                  "agree": (lv_tf == tf) if (lv_tf and tf) else None}
            if lv_tf and tf and lv_tf != tf:
                bad.append("**跨源不一致**：`load_verification.json` 记 transformers `%s`，"
                           "而活体探针实测 `%s` ⇒ 这份逐位核验**不是在被审的这套环境里做的**"
                           "（裁定 34.1：钉实际装成的值；ADR-C-014 同型：被测对象与使用对象必须同一个）"
                           % (lv_tf, tf))
    obs["load_verification"] = lv_obs

    obs["violations"] = bad
    obs["unjudged_reasons"] = unjudged
    if bad:
        rep.add("V-pi05-1_version_anchor", False, obs, req,
                note="事实源 = 活体探针的 module `__version__` + dist-info/direct_url + "
                     "lerobot 的 π₀.₅ 硬校验 + A2 的 load_verification.json（裁定 31.2 / 78.8）",
                ruling_ref=ref, red_when=red)
    elif unjudged:
        rep.add("V-pi05-1_version_anchor", None, obs, req,
                note="；".join(unjudged) + " ⇒ 证据不足，弃权（不当作通过，也不当作违例）",
                ruling_ref=ref + " / 裁定 14", red_when=red)
    else:
        rep.add("V-pi05-1_version_anchor", True, obs, req,
                note="事实源 = 活体探针的 module `__version__` + dist-info/direct_url + "
                     "π₀.₅ 硬卫语句真跑通过 + 812/812 张量逐位（裁定 31.2：import 成功不算过；"
                     "裁定 78.8：声明区间只登记）",
                ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-2 —— 权重同一性
# ---------------------------------------------------------------------------
def check_v_pi05_2(ev, rep, root: Path):
    ref = "D→B2 执行单 §1.2 V-pi05-2 / D→A2 §3（G1 验收）/ 裁定 38.2（snapshot_download 静默半成品）"
    req = ("receipt 里每个文件的 sha256 **可复算且相同**、字节数相同；%s 三件在盘上且非空；"
           "文件份数 >= %d 且与 receipt 声明一致；license 字段在证据链里。"
           "「相同」的判法：盘上复算值必须**命中 receipt 声明的至少一个通道**"
           "（`%s` 任一），且与 receipt 的自述值（`%s` 任一）不冲突"
           % ("/".join(WEIGHTS_SMALL_REQUIRED), WEIGHTS_MIN_FILES,
              "|".join(SHA256_EXPECT_KEYS), "|".join(SHA256_CLAIM_KEYS)))
    red = ("任一 sha256 / 字节数不命中 receipt 声明的任一通道；盘上值与 receipt 自述值不符"
           "（交件后被动过）；**一个可比对的声明值都读不到**（键名不匹配 ⇒ 不得记成通过）；"
           "三件小文件任一缺失或为空（缺后两件 ⇒ lerobot 静默走默认归一化）；"
           "份数不足（半成品快照）；receipt 缺 license")
    rcp = ev.get("receipt")
    if rcp is None:
        rep.add("V-pi05-2_weights_identity", None,
                "weights_receipt.json 不存在或不可解析（missing=%s）" % ev.get("missing"), req,
                note="A2 的 G1 尚未交件 ⇒ 弃权（**不是**通过）。这条闸的存在理由就是不让空目录过关。",
                ruling_ref=ref, red_when=red)
        return
    wdir, files = _receipt_weights_dir(root, rcp)
    bad = []
    obs = {"receipt_keys": sorted(rcp.keys()) if isinstance(rcp, dict) else None,
           "weights_dir": str(wdir) if wdir else None,
           "weights_dir_exists": bool(wdir and wdir.exists()),
           "n_files_declared": len(files)}

    if not files:
        bad.append("receipt 里读不到文件清单（试过 files/file_list/entries/items/sha256/checksums）"
                   "⇒ sha256 无从复算")
    if len(files) < WEIGHTS_MIN_FILES:
        bad.append("声明文件份数 %d < %d（hf-mirror API 实测 lerobot/pi05_base = 7 文件）"
                   "⇒ 半成品快照：`snapshot_download` 被 429 时会**静默返回半成品并 exit 0**，不能信返回码"
                   % (len(files), WEIGHTS_MIN_FILES))

    rec = ev.get("sha256_recompute")
    unjudged = []
    if rec is None:
        obs["sha256_verified"] = False
        unjudged.append("sha256 未复算（--no-verify-sha256 或权重目录不可得）⇒ 同一性未被证明"
                        "（弃权，**不是**通过）")
    else:
        mism, absent, uncomparable, claim_only = [], [], [], []
        n_ok, total_bytes, total_sec = 0, 0, 0.0
        matched = {}
        for rel, item in rec.items():
            got = item.get("on_disk")
            chans = item.get("expected_channels") or {}
            claim = item.get("receipt_claim") or {}
            if not item.get("exists") or not got:
                absent.append(rel)
                continue
            sha_ch = {k: v["sha256"] for k, v in chans.items() if v.get("sha256")}
            blob_ch = {k: v["git_blob_sha1"] for k, v in chans.items() if v.get("git_blob_sha1")}
            byte_ch = {k: v["bytes"] for k, v in chans.items() if v.get("bytes") is not None}
            # (i) 一个可比对的声明值都读不到 ⇒ **无从比对**。第一版在这里落进 else 记 n_ok，
            #     等于把"键名不认识"洗成"哈希一致"（恒真牙）。现在单列并判红。
            if not sha_ch and not blob_ch and not claim.get("sha256"):
                uncomparable.append("%s（receipt 条目里试过 %s / %s / %s，都没有值）"
                                    % (rel, "|".join(SHA256_EXPECT_KEYS),
                                       "|".join(GIT_BLOB_EXPECT_KEYS),
                                       "|".join(SHA256_CLAIM_KEYS)))
                continue
            # (ii) 盘上值必须命中**至少一个**声明通道。两类通道：
            #      · sha256（LFS 文件）  · git blob sha1（HF 对非 LFS 小文件只公布这个）
            #      真实案例：`.gitattributes` 的 `expected_sha256_hf_lfs` 是 null，只有
            #      `expected_git_blob_sha1_hf`；不认第二类通道 ⇒ 它会被误判成"不命中任一通道"。
            hit = sorted(k for k, v in sha_ch.items() if v == got["sha256"])
            hit_blob = sorted(k for k, v in blob_ch.items()
                              if got.get("git_blob_sha1") and v == got["git_blob_sha1"])
            if (sha_ch or blob_ch) and not hit and not hit_blob:
                mism.append("%s: 盘上 sha256 %s… / git-blob-sha1 %s 不命中 receipt 声明的任一通道（%s）"
                            % (rel, got["sha256"][:16],
                               (got.get("git_blob_sha1") or "(未复算:>%dMiB)"
                                % (GIT_BLOB_MAX_BYTES >> 20))[:16],
                               "; ".join("%s=%s…" % (k, v[:16]) for k, v in
                                         sorted(list(sha_ch.items()) + list(blob_ch.items())))))
                continue
            # (iii) receipt 的自述值也要对得上：不符 ⇒ 交件之后盘上被动过
            if claim.get("git_blob_sha1") and got.get("git_blob_sha1") \
                    and claim["git_blob_sha1"] != got["git_blob_sha1"]:
                mism.append("%s: 盘上 git-blob-sha1 %s != receipt 自述 %s=%s ⇒ 交件后盘上被动过"
                            % (rel, got["git_blob_sha1"][:16], claim.get("git_blob_sha1_key"),
                               claim["git_blob_sha1"][:16]))
                continue
            if claim.get("sha256") and claim["sha256"] != got["sha256"]:
                mism.append("%s: 盘上 sha256 %s… != receipt 自述 %s=%s… ⇒ 交件后盘上被动过"
                            % (rel, got["sha256"][:16], claim.get("sha256_key"),
                               claim["sha256"][:16]))
                continue
            # (iv) 字节数：与命中通道（或任一声明通道 / 自述）一致
            bhit = sorted(k for k, v in byte_ch.items() if v == got["bytes"])
            if (byte_ch or claim.get("bytes") is not None) and not bhit \
                    and claim.get("bytes") != got["bytes"]:
                mism.append("%s: 盘上 %d bytes 不命中任一声明字节数（%s%s）"
                            % (rel, got["bytes"],
                               "; ".join("%s=%d" % (k, v) for k, v in sorted(byte_ch.items())),
                               ("; %s=%d" % (claim.get("bytes_key"), claim["bytes"])
                                if claim.get("bytes") is not None else "")))
                continue
            if not sha_ch and not blob_ch:
                # 只有自述、没有远端清单值 ⇒ "没被动过"成立，"下对了东西"未证
                claim_only.append(rel)
            n_ok += 1
            matched[rel] = {"sha256_channels": hit, "git_blob_sha1_channels": hit_blob,
                            "identity_channel": (hit + hit_blob) or ["(claim_only)"],
                            "bytes_channels": bhit,
                            "on_disk_sha256": got["sha256"], "on_disk_bytes": got["bytes"]}
            total_bytes += got["bytes"]
            total_sec += got["elapsed_sec"] or 0.0
        obs.update({"sha256_verified": True, "n_sha_ok": n_ok, "n_sha_mismatch": len(mism),
                    "n_absent": len(absent), "absent": absent[:12],
                    "n_uncomparable": len(uncomparable), "uncomparable": uncomparable[:12],
                    "n_claim_only": len(claim_only), "claim_only": claim_only[:12],
                    "matched_channels": matched,
                    "recomputed_gib": round(total_bytes / (1 << 30), 3),
                    "recompute_elapsed_sec": round(total_sec, 2)})
        if mism:
            bad.extend(["sha256/字节数不符：" + m for m in mism])
        if absent:
            bad.append("receipt 声明但盘上没有：%s（%d 个）" % (",".join(absent[:8]), len(absent)))
        if uncomparable:
            bad.append("**%d 个文件无从比对**：%s ⇒ receipt 的键名与本闸读法不匹配。"
                       "这**不得**记成通过（恒真牙）：要么 A2 在 receipt 里给出可比的声明值，"
                       "要么本闸扩键名后重跑自检（改判据必须重跑 --selftest，A0 会抓 gate_build 不符）"
                       % (len(uncomparable), "; ".join(uncomparable[:4])))
        if claim_only:
            unjudged.append("%d 个文件只有 receipt 的**自述**哈希（%s），没有远端清单的期望值 "
                            "⇒「交件后盘上没被动过」成立，但「下对了东西」**未证**，弃权"
                            % (len(claim_only), ",".join(claim_only[:6])))

    # 三件小文件（缺后两件 = 静默走默认归一化，本闸要抓的最坏假绿）
    small = {}
    for n in WEIGHTS_SMALL_REQUIRED:
        p = (wdir / n) if wdir else None
        # 有些快照把它放在子目录，退一步用 rglob 找一次（找不到才算缺）
        if (not p or not p.exists()) and wdir and wdir.exists():
            hits = sorted(wdir.rglob(n))
            p = hits[0] if hits else p
        ok = bool(p and p.exists() and p.stat().st_size > 0)
        small[n] = {"present": bool(p and p.exists()), "path": str(p) if p else None,
                    "bytes": (p.stat().st_size if (p and p.exists()) else None)}
        if not ok:
            bad.append("**%s 缺失或为空** ⇒ lerobot `from_pretrained` 会**静默走默认归一化/反归一化**，"
                       "这是最难查的一类假绿（D→A2 §3.2）" % n)
    obs["small_required"] = small

    # license 必须进证据链（Gemma Terms of Use 是有约束的许可证）
    lic = None
    for k in ("license", "license_id", "licence"):
        if isinstance(rcp, dict) and rcp.get(k) is not None:
            lic = rcp.get(k)
            break
    if lic is None and isinstance(rcp, dict):
        ext = rcp.get("external_unverified")
        if isinstance(ext, dict):
            lic = ext.get("license")
    obs["license"] = lic if not isinstance(lic, (dict, list)) else json.dumps(lic, ensure_ascii=False)[:120]
    if lic is None:
        bad.append("receipt 缺 license 字段（`lerobot/pi05_base` 标 `license:gemma`；"
                   "Gemma Terms 必须出现在证据链里 —— 注意它属**外部来源事实**，"
                   "须按裁定 36.4 标 external_unverified，见 V-pi05-3）")

    # 盘上多出来的文件（receipt 少报）——只 WARN：可能是缓存/软链，不是同一性失效
    on_disk = ev.get("weights_on_disk") or []
    declared = {(f.get("path") or f.get("name") or f.get("file")) for f in files}
    extra = [x for x in on_disk if x not in declared]
    obs["n_on_disk"] = len(on_disk)
    obs["n_extra_on_disk"] = len(extra)
    obs["extra_sample"] = extra[:8]

    obs["violations"] = bad
    base_note = ("sha256 由本闸**当场复算**，不采信 receipt 的自述判定"
                 "（`present/size_ok/sha256_match_*` 只作观测转录，见 observed.matched_channels）")
    if bad:
        rep.add("V-pi05-2_weights_identity", False, obs, req,
                note=(base_note + ("；另有弃权项：" + "；".join(unjudged) if unjudged else "")),
                ruling_ref=ref, red_when=red)
    elif unjudged:
        rep.add("V-pi05-2_weights_identity", None, obs, req,
                note="；".join(unjudged) + " ⇒ 证据不足，弃权（裁定 14 同型：不降级成 PASS）",
                ruling_ref=ref, red_when=red)
    else:
        rep.add("V-pi05-2_weights_identity", True, obs, req,
                note=base_note + "；双向牙见 mutation M8/M9/M10/M20/M28（红）与 M29（绿）",
                ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-3 —— 通道留痕 + 外部事实不得与本机实测并列
# ---------------------------------------------------------------------------
def _walk_provenance(obj, path="$", in_external=False, marked_outer=False, out=None):
    """递归扫 receipt：分别记下「外部事实键」与「本机实测键」各自所在的位置与是否被标记。

    **两个标志必须分开**（M31 抓出来的假红，留档）：
      · `in_external` = 此刻在一个**名为** `external_unverified`/`external_facts`/`*unverified*`
        的块里。只有这种块才适用**反向**判据（裸实测值不得出现在外部块里，M13）。
      · `marked_outer` = 此刻所在的子树**已经把外部来源标出来了**（块名 `remote_*`/`upstream_*`，
        或某个 `kind|source|provenance` 值点名了远端）。它只豁免"未标记"这条正向判据。
    第一版把两者合并成一个参数，结果 `remote_hf.n_files` / `remote_modelscope.n_files`
    这类**远端报来的数字**被判成"本机实测值被塞进外部块"——那是把远端事实误当本地事实，
    方向恰好相反，属于本闸自己造的假红。
    """
    if out is None:
        out = {"external": [], "measured_in_external": [], "external_unmarked": []}
    if isinstance(obj, dict):
        marked = bool(marked_outer or in_external)
        for mk in ("provenance", "source", "kind", "class", "origin"):
            v = obj.get(mk)
            if isinstance(v, str) and (EXTERNAL_MARK_RE.search(v) or v.startswith("local_file:")
                                       or v.startswith("measured")):
                marked = True
        for k, v in obj.items():
            kp = "%s.%s" % (path, k)
            is_ext_block = bool(re.search(r"external_unverified|external_facts|unverified", str(k), re.I))
            # 块名本身就声明了远端来源（`remote_hf` / `remote_modelscope` / `upstream_*`）
            # ⇒ 该子树里的外部事实不算"与本机实测并列"，但**不**触发反向判据（见 docstring）
            is_remote_block = bool(REMOTE_BLOCK_RE.match(str(k)))
            if is_ext_block:
                _walk_provenance(v, kp, True, True, out)
                continue
            if EXTERNAL_KEY_RE.search(str(k)):
                # 标记可以写在**值**上（`{"license": {"kind": "remote_api_read"}}`），
                # 不只写在父块上；否则会把已正确标注的事实误判成「未标记」= 本仓第 8 起同型的假红。
                self_marked = False
                if isinstance(v, dict):
                    for mk in ("provenance", "source", "kind", "class", "origin"):
                        mv = v.get(mk)
                        if isinstance(mv, str) and EXTERNAL_MARK_RE.search(mv):
                            self_marked = True
                elif isinstance(v, str) and EXTERNAL_MARK_RE.search(v):
                    self_marked = True
                rec = {"key": kp,
                       "marked": bool(marked or is_remote_block or self_marked),
                       "mark_evidence": ("parent_block" if (marked or is_remote_block)
                                         else ("self_marked" if self_marked else None)),
                       "value": (v if isinstance(v, (str, int, float, bool)) or v is None
                                 else json.dumps(v, ensure_ascii=False)[:160])}
                out["external"].append(rec)
                if not rec["marked"]:
                    out["external_unmarked"].append(rec)
            # 反向违例：**裸实测键**出现在 `external_unverified` 块里 ⇒ 红。这里**不看** `marked`：
            # 块自带的 `provenance: external_unverified` 只能豁免外部事实，豁免不了
            # 「把本机实测降级成传闻」（M13 第一版就是被 `marked` 豁免掉的 ⇒ 牙失效）。
            if in_external and _is_bare_measured(k):
                out["measured_in_external"].append({"key": kp, "value": v if isinstance(
                    v, (str, int, float, bool)) else str(v)[:80]})
            _walk_provenance(v, kp, in_external or is_ext_block,
                             marked or is_remote_block, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_provenance(v, "%s[%d]" % (path, i), in_external, marked_outer, out)
    return out


def check_v_pi05_3(ev, rep):
    ref = ("D→B2 执行单 §1.2 V-pi05-3 / 裁定 36.4（跨口径不得并列）/ 裁定 38.2（通道实测坑）/ "
           "**裁定 49.5 + 69.3 + 78（§15-5 item 2、§14.4-⑦）：渠道混用按格式闭合、顶层填 `mixed`、"
           "不重下；载体 = A2 的 `weights_receipt_channel_sidecar.json`，B2 只读引用 + 自己复算**")
    req = ("下载通道必须留痕（顶层 channel 键 / 逐文件 `sha256_verdict` / `remote_*` 远端块 三者之一，"
           "且解析出的渠道全部 ∈ %s、有 host/url 佐证）；**渠道混用（≥2 个渠道）时**，A2 的 sidecar "
           "顶层必须写 `%s` 并指向 `per_file_channel`（裁定 49.5：填单一渠道 = 失真），且 sidecar 自述的"
           "四件事经 B2 复算成立（receipt 未被改写 / 顶层 mixed 诚实 / C1–C5 与变异自检全绿 / "
           "逐文件覆盖无缺口），**不得**因格式问题要求重下；外部来源事实（license、他人显存报告、"
           "上游 lastModified、远端 reported_size）必须**带可识别的外部标记**"
           "（`external_unverified` 块 / `kind|source|provenance` 指向远端 / 待在 `remote_*` 子树里），"
           "且**本机实测值不得被塞进外部块**"
           % (list(CHANNELS_ALLOWED), CHANNEL_TOP_LEVEL_MIXED))
    red = ("三种形态都给不出通道留痕；解析出的渠道不在允许集；无 host 佐证；"
           "sidecar 顶层填单一渠道（实测 ≥2 个渠道）、或自称 `%s` 而实测只有 1 个渠道；"
           "sidecar 记的 receipt sha256 与 B2 复算值不符（或自述 `rewritten_by_this_script=true`）；"
           "sidecar 的 C1–C5 有非 true、或变异自检 caught != expected；"
           "receipt 里有文件在 sidecar 的 `per_file_channel` 里没有渠道记录；"
           "外部声明值**躺在实测块里**且无任何标记（真实案例：`download.reported_size` 与 "
           "`measured_rate_MBps` 同一个 dict）；**反向也红**——把 bytes/sha256/速率这类实测值"
           "写进 `external_unverified` 块（那是把实测降级成传闻）" % CHANNEL_TOP_LEVEL_MIXED)
    rcp = ev.get("receipt")
    if rcp is None:
        rep.add("V-pi05-3_channel_provenance", None,
                "weights_receipt.json 不存在或不可解析", req,
                note="证据不足 ⇒ 弃权（A2 的 G1 未交件）", ruling_ref=ref, red_when=red)
        return
    bad = []
    text = ""
    try:
        text = json.dumps(rcp, ensure_ascii=False)
    except Exception:
        text = str(rcp)

    # (1) 通道留痕。第一版只认**顶层标量键**（channel/via/route/…），A2 的真实 receipt 没有它，
    #     但它的留痕其实**更细**：`remote_hf` / `remote_modelscope` 两个远端块 + 逐文件
    #     `sha256_verdict`（`modelscope` / `hf_lfs+modelscope` / `hf_git_blob_sha1`）
    #     + `download.note` 点名"哪个文件走哪个渠道、用什么工具、实测速率"。
    #     ⇒ 判据改成认这三种形态，而且**更强**：逐文件的渠道归属必须**全部**落在允许集里
    #       （不再是一个顶层字符串说了算）；一个形态都没有才算无留痕（M11 仍然红）。
    chan = None
    for k in ("channel", "download_channel", "source_channel", "via", "route", "mirror"):
        if isinstance(rcp, dict) and isinstance(rcp.get(k), str) and rcp.get(k):
            chan = rcp[k].strip().lower()
            break
    hosts = {h: (h in text) for h in ("modelscope.cn", "hf-mirror.com", "huggingface.co")}
    url_keys = [k for k in ("url", "endpoint", "api_url", "host", "base_url", "repo_url")
                if isinstance(rcp, dict) and (k in rcp or k in text)]
    files_list = (rcp.get("files") if isinstance(rcp, dict) else None) or []
    per_file_chan = {}
    for f in files_list:
        if not isinstance(f, dict):
            continue
        v = f.get("sha256_verdict") or f.get("channel") or f.get("source") or f.get("via")
        if isinstance(v, str) and v:
            per_file_chan[str(f.get("path") or f.get("name") or "?")] = v
    remote_blocks = sorted(str(k) for k in (rcp if isinstance(rcp, dict) else {})
                           if REMOTE_BLOCK_RE.match(str(k)))
    hf_host = hosts.get("hf-mirror.com")
    tokens, raw_tokens = set(), []

    def _chan_tokens(v):
        """把一个渠道表述拆成规范渠道名。认不出的词**原样保留**，交给 unknown_chan 判红。"""
        out = []
        for t in re.split(r"[+/,;\s_]+", str(v).lower()):
            if not t or t in ("lfs", "git", "blob", "sha1", "sha256", "remote", "upstream",
                              "manifest", "external", "vendor", "channel", "via"):
                continue          # 构词成分，不是渠道名
            if "modelscope" in t:
                out.append("modelscope")
            elif "hf" in t or "huggingface" in t:
                # hf-mirror 与 huggingface.co 是**两个**不同出口，按 receipt 里出现的 host 定
                out.append("hf_mirror" if hf_host else "huggingface")
            else:
                out.append(t)
        return out

    for v in ([chan] if chan else []) + list(per_file_chan.values()):
        raw_tokens.append(str(v))
        tokens.update(_chan_tokens(v))
    # `remote_*` 块名只按**整名**映射（不拆词）：`manifest_cross_check` 拆开会得到
    # "cross"/"check" 这种伪渠道名 ⇒ 那是本闸自己造的假红，不是 A2 的问题。
    for b in remote_blocks:
        raw_tokens.append(b)
        low = b.lower()
        if "modelscope" in low:
            tokens.add("modelscope")
        elif "hf" in low or "huggingface" in low:
            tokens.add("hf_mirror" if hf_host else "huggingface")
    channels_used = sorted(tokens)
    unknown_chan = [c for c in channels_used if c not in CHANNELS_ALLOWED]
    obs = {"channel": chan, "hosts_found": {k: v for k, v in hosts.items() if v},
           "url_evidence_keys": url_keys, "channels_allowed": list(CHANNELS_ALLOWED),
           "channels_used": channels_used, "channel_evidence": {
               "top_level_channel_key": chan,
               "remote_blocks": remote_blocks,
               "n_per_file_channel": len(per_file_chan),
               "per_file_channel": per_file_chan,
               "raw_tokens": sorted(set(raw_tokens))[:12]},
           "channels_unknown": unknown_chan}
    if not chan and not per_file_chan and not remote_blocks:
        bad.append("receipt 里没有任何通道留痕（试过：顶层 channel/download_channel/source_channel/"
                   "via/route/mirror；逐文件 sha256_verdict/channel/source；remote_*/upstream_* 远端块）"
                   "⇒ 「走的是 ModelScope 还是 hf-mirror」无留痕")
    if unknown_chan:
        bad.append("通道 `%s` 不在允许集 %s（新通道必须先报 D 登记，不得就地扩表）"
                   % (",".join(unknown_chan), list(CHANNELS_ALLOWED)))
    if not any(hosts.values()) and not url_keys:
        bad.append("通道无 host/url 佐证（modelscope.cn / hf-mirror.com / huggingface.co 都没出现，"
                   "也没有 url/endpoint/host 字段）⇒ 留痕不可核")

    # ---- (1b) 裁定 49.5 / 69.3 / 78（D→B2 §15-5 item 2 + §14.4-⑦）：渠道混用 = `mixed`，
    #      **按格式闭合、不重下**。D 的处置不是"忽略混用"，而是"A2 用 sidecar 把顶层渠道写成
    #      `mixed` 并指向逐文件记录，B2 只在闸里引用这份 sidecar"。
    #      **引用 ≠ 采信**：sidecar 自述的四件事全部由本闸自己复算 ——
    #        ① receipt 未被 sidecar 改写（它自述的 sha256 == B2 快照时点复算的 sha256）；
    #        ② 顶层确实是 `mixed` 且**真的** ≥2 个渠道（裁定 49.5：填单一渠道 = 失真；
    #           反向也成立 —— 只有 1 个渠道却自称 mixed 同样 = 失真）；
    #        ③ sidecar 自己的 C1–C5 与 3/3 变异自检全绿（它有牙才可信）；
    #        ④ receipt 里每个文件都有渠道记录（不采信 C4 的自述，自己算差集）。
    #      牙：M64（自称 mixed 但只有 1 个渠道）/ M65（自称 receipt 未改写但 sha 对不上）必须红。
    sc = ev.get("channel_sidecar")
    sc_meta = (ev.get("files") or {}).get("weights_receipt_channel_sidecar.json") or {}
    rc_meta = (ev.get("files") or {}).get("weights_receipt.json") or {}
    chan_bad = []
    closure = {
        "ruling": "裁定 49.5（顶层必须填 mixed、不许填单一渠道）/ 裁定 69.3 / 裁定 78 §15-5 item 2",
        "sidecar_path": ev.get("channel_sidecar_path"),
        "sidecar_exists": sc_meta.get("exists"), "sidecar_sha12": sc_meta.get("sha12"),
        "sidecar_bytes": sc_meta.get("bytes"), "sidecar_mtime_iso": sc_meta.get("mtime_iso"),
        "sidecar_parse_error": ev.get("channel_sidecar_parse_error"),
        "channel_topology": ("mixed" if len(channels_used) > 1 else
                             ("single" if len(channels_used) == 1 else "none")),
        "channels_used_from_receipt": channels_used,
        "redownload_required": False,
        "no_redownload_ruling": ("裁定 49.5/69.3：重下 14.47 GB 无收益、下载是 A2 单线，"
                                 "且重下会引入新的渠道不一致 ⇒ **不得**因格式问题触发重下"),
    }
    if isinstance(sc, dict):
        ref_blk = sc.get("receipt_reference") or {}
        chk_blk = sc.get("checks") or {}
        mut = sc.get("mutation_selftest") or {}
        per_file = [f for f in (sc.get("per_file_channel") or []) if isinstance(f, dict)]
        rc_live = rc_meta.get("sha256")
        sc_chans = sorted({str(f.get("channel")) for f in per_file if f.get("channel")})
        sc_norm = sorted({norm_channel_name(c) for c in sc_chans})
        pf_names = {str(f.get("path")) for f in per_file if f.get("path")}
        rc_names = {str(f.get("path") or f.get("name") or f.get("file")) for f in files_list
                    if isinstance(f, dict) and (f.get("path") or f.get("name") or f.get("file"))}
        closure.update({
            "channel_top_level": sc.get("channel_top_level"),
            "distinct_channels_declared": sc.get("distinct_channels"),
            "distinct_channels_recomputed": sc_chans,
            "n_distinct_channels_recomputed": len(sc_chans),
            "normalized_into_allowed_set": sc_norm,
            "receipt_sha256_recomputed_by_b2": rc_live,
            "receipt_sha256_claimed_before": ref_blk.get("sha256_before_sidecar"),
            "receipt_sha256_claimed_after": ref_blk.get("sha256_after_sidecar"),
            "receipt_sha256_claim_identical": ref_blk.get("sha256_identical"),
            "receipt_rewritten_by_sidecar": ref_blk.get("rewritten_by_this_script"),
            "sidecar_checks": chk_blk,
            "sidecar_selftest": {"expected": mut.get("mutations_expected_to_be_caught"),
                                 "caught": mut.get("mutations_caught"),
                                 "all_cases_verdict_ok": mut.get("all_cases_verdict_ok")},
            "n_per_file_records": len(per_file),
            "receipt_files_without_channel_record": sorted(rc_names - pf_names),
        })
        # ① receipt 未被改写：sidecar 自述的 sha 必须与 B2 复算值逐字相同
        claimed = ref_blk.get("sha256_after_sidecar") or ref_blk.get("sha256_before_sidecar")
        if rc_live and claimed and claimed != rc_live:
            chan_bad.append("渠道 sidecar 自称「receipt 未被改写」，但它记的 sha256 `%s…` 与 B2 "
                            "复算的 `%s…` **不符** ⇒ 要么 receipt 在 sidecar 之后被改过（那份闭合"
                            "已失效、需重出 sidecar），要么 sidecar 记的不是这份 receipt"
                            "（ADR-C-014 同型：被引用对象与被使用对象不是同一个）"
                            % (str(claimed)[:12], str(rc_live)[:12]))
        if ref_blk.get("rewritten_by_this_script") is True:
            chan_bad.append("渠道 sidecar 自述 `rewritten_by_this_script=true` ⇒ receipt 被就地改写，"
                            "B2 快照引用的 sha256 已失效（裁定 49.5 的闭合方式是**另存 + 指回**，"
                            "不是重写）")
        # ② 顶层必须是 `mixed`，且"mixed"必须诚实（双向）
        top = sc.get("channel_top_level")
        if len(sc_chans) > 1 and top != CHANNEL_TOP_LEVEL_MIXED:
            chan_bad.append("实测有 %d 个渠道 %s，但 sidecar 顶层写 `%s` ⇒ 裁定 49.5：**不许填单一渠道**"
                            "（填单一渠道 = 失真）；顶层必须是 `%s` 并指向 `per_file_channel`"
                            % (len(sc_chans), sc_chans, top, CHANNEL_TOP_LEVEL_MIXED))
        if 0 < len(sc_chans) < 2 and top == CHANNEL_TOP_LEVEL_MIXED:
            chan_bad.append("sidecar 顶层自称 `%s`，但逐文件记录里只有 %d 个渠道 %s ⇒ "
                            "**mixed 不诚实**（裁定 49.5 的反向：只有一个渠道时必须写那个渠道，"
                            "sidecar 自己的 C1 就该抓住这件事）"
                            % (CHANNEL_TOP_LEVEL_MIXED, len(sc_chans), sc_chans))
        off = [c for c in sc_norm if c not in CHANNELS_ALLOWED]
        if off:
            chan_bad.append("sidecar 的逐文件渠道归一后 `%s` 不在允许集 %s（新渠道必须先报 D 登记，"
                            "不得就地扩表）" % (",".join(off), list(CHANNELS_ALLOWED)))
        # ③ sidecar 自己的判据与牙（不采信它的 `verdict.PASS`）
        if chk_blk:
            not_true = sorted(str(k) for k, v in chk_blk.items() if v is not True)
            if not_true:
                chan_bad.append("sidecar 的自检项 %s 不是 true（B2 不采信它的 `verdict.PASS`，"
                                "逐条读 `checks`）" % ",".join(not_true))
        if mut:
            if mut.get("all_cases_verdict_ok") is not True or (
                    mut.get("mutations_caught") != mut.get("mutations_expected_to_be_caught")):
                chan_bad.append("sidecar 的变异自检不成立（caught=%r / expected=%r、"
                                "all_cases_verdict_ok=%r）⇒ 它自称的闭合没有牙支撑"
                                % (mut.get("mutations_caught"),
                                   mut.get("mutations_expected_to_be_caught"),
                                   mut.get("all_cases_verdict_ok")))
        # ④ 逐文件覆盖：自己算差集，不采信 C4 的自述
        if rc_names and (rc_names - pf_names):
            chan_bad.append("receipt 里有 %d 个文件在 sidecar 的 `per_file_channel` 里**没有**渠道记录：%s"
                            "（C4 自称已覆盖，B2 复算不同意）⇒ 逐文件留痕不完整"
                            % (len(rc_names - pf_names), sorted(rc_names - pf_names)[:8]))
        closure["status"] = ("closed_by_ruling_49_5_via_a2_sidecar" if not chan_bad
                             else "sidecar_present_but_recomputed_claims_fail")
    else:
        closure["status"] = ("sidecar_unparseable" if sc_meta.get("exists")
                             else "sidecar_absent_judged_from_receipt_alone")
        closure["note"] = ("sidecar 不在场 ⇒ 本闸只按 receipt 自己的留痕判（判据不变、不放宽）；"
                           "顶层 `mixed` 的格式闭合**未被证明**，但也**不因此判红**"
                           "（裁定 49.5 的载体是 A2 的 sidecar，缺载体是"
                           "「闭合未证明」，不是「渠道违规」）")
    obs["channel_provenance_closure"] = closure
    bad.extend(chan_bad)

    # (2) 外部事实 vs 本机实测：两个方向都查（裁定 36.4）
    prov = _walk_provenance(rcp)
    # ---- 裁定 96.2：RR-B2-05 的解铃载体（B2 写入面内的 sidecar）。**引用 ≠ 采信**：
    # 采信条件全部由本闸自己复算 —— ① 有 `as_of`（无时点的引用不采信，裁定 96.1-①）；
    # ② 自述没改写 receipt（载体越权即拒）；③ 它指向的 receipt `sha256[:12]` 与本闸复算值
    # **逐字相同**；④ 路径是同一件。四条有一条不成立 ⇒ 不采信、并把它自己列成违例。
    # ③ 就是牙不被蒙住的原因：变异世界里的合成 receipt 内容不同 ⇒ sha 不同 ⇒ sidecar 失效
    # ⇒ M32（`download.reported_size` + `verdict.license_ok` 裸露的那个变异体）仍然红。
    xs = ev.get("external_sidecar")
    xs_meta = (ev.get("files") or {}).get("receipt_sidecar_external_unverified.json") or {}
    xs_bad = []
    marked_by_sidecar = {}
    xs_obs = {"path": ev.get("external_sidecar_path"), "exists": xs_meta.get("exists"),
              "sha12": xs_meta.get("sha12"), "bytes": xs_meta.get("bytes"),
              "mtime_iso": xs_meta.get("mtime_iso"),
              "as_of": (xs.get("as_of") if isinstance(xs, dict) else None),
              "parse_error": ev.get("external_sidecar_parse_error"),
              "honored_fields": [], "refusal_reasons": []}
    if isinstance(xs, dict):
        xs_rcp = (xs.get("receipt") or {})
        claimed12 = xs_rcp.get("sha256_12")
        # receipt 那一份快照只有全量 `sha256`（四份 A2 交件的 schema 里没有 `sha12` 键）
        # ⇒ 前 12 位由本闸**自己截**，不假设上游快照带这个键（假设错了就会拿 `None` 去比，
        # 首跑实测就是这么红的：判词写成「与本闸复算的 `None` 不符」——结论对、理由不诚实）。
        live_full = rc_meta.get("sha256")
        live12 = (str(live_full)[:12] if live_full else None)
        claimed_path = xs_rcp.get("path")
        live_path = str(rc_meta.get("path") or "")
        if not live12:
            xs_bad.append("本闸**没有**复算出 receipt 的 sha256（快照里 `sha256` 缺失）⇒ sidecar 无从核对，"
                          "不采信（三值纪律：记 not_measured，不猜、也不因此判 sidecar 说谎）")
        elif not xs.get("as_of"):
            xs_bad.append("external sidecar 没有 `as_of` ⇒ 引用无时点，不采信（裁定 96.1-①）")
        elif xs_rcp.get("rewritten_by_this_sidecar") is not False:
            xs_bad.append("external sidecar 未声明「没改写 receipt」（或自述改写过）⇒ 载体越权，"
                          "不采信（裁定 96.2：不改 receipt 一个字节）")
        elif not claimed12 or not live12 or str(claimed12) != str(live12):
            xs_bad.append("external sidecar 指向的 receipt sha256[:12]=`%s`，与本闸复算的 `%s` "
                          "**不符** ⇒ 它对这一份 receipt 无效（不猜、不放宽；receipt 变过就得重出 sidecar）"
                          % (claimed12, live12))
        elif claimed_path and not live_path.endswith(str(claimed_path)):
            xs_bad.append("external sidecar 指向的 receipt 路径 `%s`，与本闸读的 `%s` 不是同一件"
                          % (claimed_path, live_path))
        else:
            for row in (xs.get("external_unverified_fields") or []):
                if isinstance(row, dict) and isinstance(row.get("json_path"), str) \
                        and row.get("provenance") == "external_unverified":
                    marked_by_sidecar[row["json_path"]] = row
            xs_obs["honored_fields"] = sorted(marked_by_sidecar)
    elif xs_meta.get("exists"):
        xs_bad.append("external sidecar 在场但解析不出（%s）⇒ 不采信"
                      % (ev.get("external_sidecar_parse_error") or "parse_error"))
    xs_obs["refusal_reasons"] = xs_bad
    obs["external_sidecar_96_2"] = xs_obs
    bad.extend(xs_bad)
    obs["n_external_keys"] = len(prov["external"])
    obs["external_keys"] = [e["key"] for e in prov["external"]][:20]
    obs["external_unmarked"] = [e["key"] for e in prov["external_unmarked"]][:20]
    obs["measured_inside_external"] = [m["key"] for m in prov["measured_in_external"]][:20]
    for e in prov["external_unmarked"]:
        srow = marked_by_sidecar.get(e["key"])
        if srow is not None:
            # 裁定 96.2 的载体生效：这条外部事实**已被显式标注**（不是被忽略、也不是放宽标记词表：
            # `EXTERNAL_MARK_RE` 一字未改）⇒ 登记在案、不判红。
            obs.setdefault("marked_via_sidecar_96_2", []).append(
                {"key": e["key"], "value": e["value"], "kind": srow.get("kind"),
                 "why_external": srow.get("why_external"),
                 "sidecar_sha12": xs_meta.get("sha12"), "sidecar_as_of": xs_obs["as_of"],
                 "receipt_sha12": (str(rc_meta.get("sha256"))[:12] if rc_meta.get("sha256") else None),
                 "ruling_ref": "裁定 96.2（载体）+ 裁定 36.4（跨口径不得并列）"})
            continue
        bad.append("外部来源事实 `%s`（值=%r）未标 `external_unverified`，与本机实测并列在同一块 "
                   "⇒ 裁定 36.4：跨口径不得并列。修法：挪进 `external_unverified:{...}` 子块，"
                   "或给它加 `provenance`/`source` 标记" % (e["key"], e["value"]))
    for m in prov["measured_in_external"]:
        bad.append("**反向违例**：本机实测值 `%s` 被写进 `external_unverified` 块 "
                   "⇒ 把实测降级成传闻，同样违反裁定 36.4（两个口径都不许混）" % m["key"])

    obs["violations"] = bad
    # 裁定 96.2 的**分诊**（D 的原话：这条比载体更重要）：本条属 Ⅱ 类「登记不阻塞」。
    obs["triage_ruling_96_2"] = {
        "class": "II_experimental_interpretation_risk_registered_not_blocking",
        "blocking": False, "ruling_ref": "裁定 96.2（+ 95.1 的三分类）",
        "why": ("本条管的是「外部事实的口径标注」，不是控制 / 数据正确性；BC 的硬闸是 `Tp5` 同源 "
                "+ `bc_admission()` AND 闸 verdict（C2 已落码），不是这一条"),
        "does_not_block": "六步序列第 1–3 步",
        "must_not_be_read_as": ("本条若再红，顶层 `ok=false` **不得**被任何线读成「BC 被禁」"
                                "（读成禁 = 把 Ⅱ 类升成 Ⅰ 类 = D 同型错误 #20 的同型复发；"
                                "下位发现可直接引裁定 96.2 驳）")}
    rep.add("V-pi05-3_channel_provenance", not bad, obs, req,
            note="本闸自己的产物也遵守这条：`admission_verdict.json` 里外部事实一律带 "
                 "`external_unverified` 前缀键，不与实测同表",
            ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-4 —— torch 栈冻结（裁定 39.1 的红线，必须双向有牙）
# ---------------------------------------------------------------------------
SECTION_RE = re.compile(r"^\s*={3,}\s*(.*?)\s*={3,}\s*$")
PLUS_PIN_RE = re.compile(r"^\s*([+\-])\s*([A-Za-z0-9_.\-]+)==([^\s;#]+)")
WHEEL_RE = re.compile(r"([A-Za-z0-9_.\-]+?)-(\d[\w.!+]*?)(?:-cp\d+|-py\d+|[\s.]|$)")
DOWNLOAD_RE = re.compile(r"^\s*Downloading\s+([A-Za-z0-9_.\-]+)\s*[\(\[]", re.I)
COLLECT_RE = re.compile(r"^\s*Collecting\s+([A-Za-z0-9_.\-]+)\s*([<>=!~].*)?$", re.I)


def _dryrun_torch_hits(lines):
    """**分段 + 认版本**地扫 resolver 清单，抓「触及 torch 栈」的行。

    为什么必须认版本（这是本闸第一版判错的地方，留档）
    ------------------------------------------------
    A2 的 `resolve_dryrun.txt` 是**分段**的：第一段是对**空 venv** 的一次性解析
    （`Would install 123 packages`，里面必然含 `+ torch==2.6.0+cu124`），
    第二段起是 STAGE 1 先把 torch 栈钉死、STAGE 2 再解析其余依赖 —— 于是**后段的清单里
    torch 根本不出现**，那才是 裁定 39.1 想要的「真信号」（A2 自己在文件里写明了这个设计）。
    ⇒ 只按「包名出现」判红，会把**按锚值全新安装**误判成**挪动 torch 栈**（假红）；
      只按「包名不出现」判绿，又会放过**升级到别的版本**（假绿）。
    所以判据落在**版本**上：装成值 != 锚值 ⇒ 红；== 锚值 ⇒ 留痕但不红；
    无版本号的行（`Downloading torch (732.9MiB)`）⇒ 单独归类，由活体探针定案。

    返回 (hits, sections, transformers_seen)。
    hit = {line_no, section, line, pkg, action, version, klass}，
    klass ∈ {off_anchor, uninstall, at_anchor, unversioned}。
    """
    hits, sections, tf_seen = [], [], False
    section = "(preamble)"
    for i, raw in enumerate(lines or []):
        line = raw.rstrip()
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1)[:80]
            sections.append({"line_no": i + 1, "title": section})
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "transformers" in line.lower():
            tf_seen = True
        pkg = action = ver = None
        m = PLUS_PIN_RE.match(line)
        if m:
            action = "install" if m.group(1) == "+" else "uninstall"
            pkg, ver = m.group(2), m.group(3)
        else:
            m = RESOLVE_ARROW_RE.search(line)
            if m and norm_name(m.group(1)) in TORCH_STACK:
                pkg, action = m.group(1), "replace"
                ver = m.group(3)
                if m.group(2) != m.group(3):
                    hits.append({"line_no": i + 1, "section": section, "line": line.strip()[:200],
                                 "pkg": pkg, "action": "replace", "version": m.group(3),
                                 "from_version": m.group(2), "klass": "off_anchor"})
                    continue
            if not pkg:
                m = DOWNLOAD_RE.match(line)
                if m:
                    pkg, action, ver = m.group(1), "download", None
            if not pkg:
                m = COLLECT_RE.match(line)
                if m:
                    pkg, action = m.group(1), "collect"
                    spec = m.group(2) or ""
                    mv = re.search(r"==\s*([^\s,;]+)", spec)
                    ver = mv.group(1) if mv else None
            if not pkg and RESOLVE_TOUCH_RE.match(line):
                body = RESOLVE_TOUCH_RE.match(line).group(1)
                for wpkg, wver in WHEEL_RE.findall(body):
                    if norm_name(wpkg) in TORCH_STACK:
                        pkg, action, ver = wpkg, "install", wver
                        break
        if not pkg or norm_name(pkg) not in TORCH_STACK:
            continue
        anchor = TORCH_STACK_ANCHORS.get(norm_name(pkg))
        if action in ("uninstall", "replace"):
            klass = "uninstall"
        elif ver is None:
            klass = "unversioned"
        elif ver == anchor:
            klass = "at_anchor"
        else:
            klass = "off_anchor"
        hits.append({"line_no": i + 1, "section": section, "line": line.strip()[:200],
                     "pkg": norm_name(pkg), "action": action, "version": ver,
                     "anchor": anchor, "klass": klass})
    return hits, sections, tf_seen


def check_v_pi05_4(ev, rep):
    ref = "裁定 39.1（依赖红线：torch.__version__ 必须逐字等于 2.6.0+cu124；解析器不得动 torch 栈）"
    req = ("新 venv 活体 `torch.__version__ == %s` 且 `torch.version.cuda == %s`；"
           "`resolve_dryrun.txt` 里不出现 torch/torchvision/torchcodec 的 install/upgrade/uninstall；"
           "lock 的 torch pin 与活体值的**基版号**一致"
           % (TORCH_ANCHOR, TORCH_CUDA_ANCHOR))
    red = ("活体 torch 版本 != 锚值（例：2.9.0+cu128）；cuda != %s；dryrun 触及 torch 栈；"
           "lock pin 与活体值描述的**不是同一个 torch**（口径互斥）" % TORCH_CUDA_ANCHOR)
    bad, obs = [], {}
    unjudged = []

    # (a) 活体锚（事实源）——lock 对 CUDA 构建是盲的，见模块 docstring
    vp = ev.get("venv_probe")
    if not ev.get("live") or not vp or "torch_version" not in vp:
        unjudged.append("活体 torch 探针不可得（live=%s）" % ev.get("live"))
    else:
        tv, tc = vp.get("torch_version"), vp.get("torch_cuda")
        obs["torch_version_live"] = tv
        obs["torch_cuda_live"] = tc
        obs["torch_anchor"] = TORCH_ANCHOR
        if tv is None:
            bad.append("活体探不到 `torch.__version__`（torch_error=%r）⇒ torch 栈是否被动**无法判定**"
                       % vp.get("torch_error"))
        elif tv != TORCH_ANCHOR:
            bad.append("**torch 栈已变**：活体 `torch.__version__ == %s`，锚值是 `%s`（逐字比较）。"
                       "裁定 39.1：不等于 = **断点变更**，须 D 登记 + 重过本闸，不是「顺手升级」；"
                       "跨 torch 版本会让 V0–V9 基线与 `t17_train_side_verify_v2.json` 失去可比性"
                       % (tv, TORCH_ANCHOR))
        if tc is not None and str(tc) != TORCH_CUDA_ANCHOR:
            bad.append("CUDA 构建不符：`torch.version.cuda == %s`，锚值 `%s`" % (tc, TORCH_CUDA_ANCHOR))

    # (b) lock 口径：pin 对 `+cuXXX` 是盲的 ⇒ 只做**基版号一致性**，不照搬 G3 的 `+cu124` 规则
    lp = (ev.get("lock_pins_norm") or {}).get("torch")
    obs["torch_lock_pin"] = lp
    obs["lock_blind_to_cuda_build"] = True
    obs["lock_blind_note"] = ("已验收两套 0928 lock 的 pin 就是 `torch==2.6.0`（不带 +cu124，"
                              "`%s/requirements.lock.txt:93`），而活体 `torch.__version__` 才是 `%s`，"
                              "`importlib.metadata.version('torch')` 也只有 2.6.0 ⇒ **lock 与 dist 元数据"
                              "对 CUDA 构建是盲的**，cu124 与 cu126/cu128 会写出逐字节相同的 pin 行。"
                              "所以本条牙的事实源是活体探针，不是 lock；照搬 B 的 G3「pin 必须带 +cu124」"
                              "到 lerobot 世系会造成本仓第 8 起同型的**假红**。"
                              % (LOCKS_0928_DIR, TORCH_ANCHOR))
    if lp is None:
        unjudged.append("lock 里读不到 torch pin")
    elif vp and vp.get("torch_version"):
        base_live = _vtuple(vp["torch_version"])[0]
        base_pin = _vtuple(lp)[0]
        if base_live and base_pin and base_live != base_pin:
            bad.append("口径互斥：lock 记 `torch==%s`，活体是 `%s` ⇒ 二者描述的不是同一个 torch "
                       "（lock 不是这个 venv 的 freeze 产物，或 venv 装完后又被动过）" % (lp, vp["torch_version"]))

    # (c) resolve_dryrun：清单里出现 torch 栈的 install/upgrade ⇒ 红（裁定 39.1 的执行方式）
    lines = ev.get("resolve_dryrun")
    if lines is None:
        unjudged.append("`resolve_dryrun.txt` 不存在（裁定 39.1 要求**实装前**先落盘；"
                        "缺失不等于「没动 torch 栈」⇒ 弃权，不判绿）")
        obs["dryrun_hits"] = None
    else:
        hits, sections, tf_seen = _dryrun_torch_hits(lines)
        off = [h for h in hits if h["klass"] in ("off_anchor", "uninstall")]
        at = [h for h in hits if h["klass"] == "at_anchor"]
        unv = [h for h in hits if h["klass"] == "unversioned"]
        obs["dryrun_lines"] = len(lines)
        obs["dryrun_sections"] = sections[:8]
        obs["dryrun_transformers_seen"] = tf_seen
        obs["n_dryrun_torch_lines"] = len(hits)
        obs["dryrun_off_anchor"] = off[:12]
        obs["dryrun_at_anchor"] = at[:12]
        obs["dryrun_unversioned"] = unv[:12]
        for h in off:
            bad.append("dryrun 第 %d 行（段：%s）**挪动了 torch 栈**：%s 装成 `%s`，锚值 `%s`（%s）"
                       "｜ 原文：%s" % (h["line_no"], h["section"], h["pkg"], h.get("version"),
                                        h.get("anchor"), h["klass"], h["line"]))
        if at:
            obs["at_anchor_note"] = (
                "清单里出现 %d 行**按锚值**安装 torch 栈（%s）⇒ 不构成违例：那是空 venv 的一次性解析，"
                "不是「挪动」。但 裁定 39.1 的字面表述是「出现 install 或 upgrade ⇒ 停下报 D」，"
                "本闸采**认版本**的读法（装成值 == 锚值即未挪动），并已把该口径差异写进 "
                "`ruling_requests` 报 D 确认 —— 不静默放宽。"
                % (len(at), "; ".join("%s==%s@L%d" % (h["pkg"], h["version"], h["line_no"])
                                      for h in at[:6])))
        if unv:
            settled = (obs.get("torch_version_live") == TORCH_ANCHOR)
            obs["unversioned_note"] = (
                "%d 行只有包名没有版本（如 `Downloading torch (732.9MiB)`）⇒ 由活体探针定案：%s"
                % (len(unv), ("活体 torch.__version__ == 锚值 %s，判为按锚值安装" % TORCH_ANCHOR)
                   if settled else "**活体值不是锚值或探不到 ⇒ 无法定案**"))
            if not settled:
                bad.append("dryrun 有 %d 行无版本号地触及 torch 栈，且活体探针无法把它定案为锚值 "
                           "⇒ torch 栈是否被动**不可判**" % len(unv))
        if not tf_seen:
            obs["dryrun_warn"] = ("这份 dryrun 里没出现 `transformers` ⇒ 它可能不是 π₀.₅ 依赖解析的产物"
                                  "（口径可疑，但不构成 torch 栈违例）")

    # (d) 锚值回校：锚常量必须与**两套已验收 venv 的活体实测**一致，否则锚本身已漂
    acc = ev.get("accepted_venv_probe") or {}
    acc_torch, acc_unprobed = {}, []
    for v, pr in acc.items():
        tv = (pr.get("pkgs") or {}).get("torch") or pr.get("torch_version")
        if tv:
            acc_torch[v] = tv
        else:
            acc_unprobed.append(v)
    obs["torch_anchor_accepted_live"] = acc_torch
    if acc_unprobed:
        unjudged.append("已验收 venv %s 探不到 torch 版本 ⇒ 锚值无法回校"
                        % ",".join(acc_unprobed))
    for v, tv in acc_torch.items():
        if tv != TORCH_STACK_ANCHORS["torch"]:
            bad.append("锚常量与事实源不符：已验收 %s 的活体 `torch.__version__ == %s`，"
                       "而本闸锚值是 `%s` ⇒ 必须报 D 更新锚，不得就地放宽判据"
                       % (v, tv, TORCH_STACK_ANCHORS["torch"]))

    if bad:
        rep.add("V-pi05-4_torch_stack_frozen", False, obs, req,
                note="；".join(unjudged) or "双向牙：见 mutation M5/M6（红）与 M7（绿）",
                ruling_ref=ref, red_when=red)
    elif unjudged:
        rep.add("V-pi05-4_torch_stack_frozen", None, obs, req,
                note="；".join(unjudged) + " ⇒ 证据不足，弃权（不当作通过）",
                ruling_ref=ref, red_when=red)
    else:
        rep.add("V-pi05-4_torch_stack_frozen", True, obs, req,
                note="双向牙：M5/M6（2.6.0+cu124→2.9.0+cu128、dryrun 升级 torch）必须红；"
                     "M7（只新增 transformers 4.57.1）必须绿 —— 见 mutation_verdict.json",
                ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-5 —— transformers 对 π₀.₅ 是否**真的可用**（功能锚 + git 溯源）
# ---------------------------------------------------------------------------
# 为什么必须有这条（2026-09-29 18:2x–18:4x 的真实现场，B2 只读实测）
# ------------------------------------------------------------------
# D→B2 §8.1 给的锚是「`transformers >=4.57.1,<5.0.0`」，来源是
# `importlib.metadata.requires('lerobot')` 的 extra `transformers-dep`。但 lerobot 的 π₀.₅
# 代码里另有一条**硬校验**（`lerobot/policies/pi05/modeling_pi05.py:576-585`，B2 只读读过原文）：
#     from transformers.models.siglip import check
#     if not check.check_whether_transformers_replace_is_installed_correctly(): raise ValueError(msg)
# ⇒ 「能不能跑 π₀.₅」的事实源是**这个函数**，不是版本区间。两个实测把它钉死：
#   · A2 `runs/vla/a2_pi05_contract_20260929/probe_run1_transformers_blocker.log`：
#     PyPI 的 **4.57.6**（满足 §8.1 区间）⇒ `ValueError: An incorrect transformer version is used`；
#   · B2 活体探针（`CUDA_VISIBLE_DEVICES=""`，秒级、不占卡）：git 分支
#     `fix/lerobot_openpi`@`dcddb970176382c0fcf4521b0c0e6fc15894dfe0`（版本字符串 **4.53.3**，
#     **低于** §8.1 的下界）⇒ 该校验 **True**，且 A2 的 probe.log 显示模型真的加载成功
#     （params=3.617B）。A2 在 `resolve_dryrun.txt` STAGE 3 也独立得到同一结论，并引
#     lerobot `pyproject.toml:444` 的 `pi uses custom branch which conflicts with transformers-dep`
#     ⇒ **这是上游设计里的覆盖，不是版本退化**。
# 所以本闸**不自行改** §8.1 的区间（那是 D 的锚，改它等于就地放宽判据）：区间那条仍由
# V-pi05-1 判、判红就判红，并同时开 RR-B2-06 请 D 更新锚。本条只判**两件可实测的事**：
#   ① 功能锚：lerobot 的 π₀.₅ 硬校验必须真的通过（False/ImportError ⇒ from_pretrained 必抛）；
#   ② git 溯源：git 装的包，**版本字符串认不出 commit**（`4.53.3` 可以是该分支任何一次 build），
#      所以装成记录（lock / env_manifest）里必须同时有 **commit**；只在 dryrun 里出现不算
#      （dryrun 是计划书不是装成记录，与 V-pi05-1 的 M4 同一口径）。
PI05_TF_CHECK_PATH = "transformers.models.siglip.check.check_whether_transformers_replace_is_installed_correctly()"


def check_v_pi05_5(ev, rep):
    ref = ("lerobot `policies/pi05/modeling_pi05.py:576-585` 的硬校验（B2 只读实测）/ "
           "A2 `probe_run1_transformers_blocker.log` + `resolve_dryrun.txt` STAGE 3 / "
           "裁定 34.1（钉实际装成的值）/ D→B2 §8.1（版本区间锚，见 RR-B2-06）")
    req = ("① 活体探针 `%s` == True；② 若 transformers 是 git 安装，装成记录"
           "（requirements.lock.txt / env_manifest.json）里必须同时出现**版本号与 commit_id**；"
           "③ lock 里记的 transformers 值必须 == 活体实测值" % PI05_TF_CHECK_PATH)
    red = ("功能校验 False / ImportError（⇒ `PI05Policy.from_pretrained` 必抛 "
           "`ValueError: An incorrect transformer version is used`，A2 已实测）；"
           "git 安装但装成记录里没有 commit（只有 dryrun 里出现也不算）；"
           "lock 记的值与活体实测不符（产物不可复现）")
    vp = ev.get("venv_probe") or {}
    chk = vp.get("pi05_transformers_check") or {}
    tf_live = (vp.get("pkgs") or {}).get("transformers")
    du = (vp.get("direct_url") or {}).get("transformers") if vp.get("direct_url") else None
    vcs = (du or {}).get("vcs_info") or {}
    commit = vcs.get("commit_id")
    unjudged, bad = [], []
    obs = {"functional_check_path": PI05_TF_CHECK_PATH,
           "functional_check": chk, "tf_live_version": tf_live,
           "install_source": du, "git_commit": commit,
           "git_branch": vcs.get("requested_revision"),
           "lerobot_hard_check_evidence": [
               "runs/vla/a2_pi05_contract_20260929/probe_run1_transformers_blocker.log"
               "（PyPI 4.57.6 ⇒ ValueError: An incorrect transformer version is used）",
               "runs/vla/a2_pi05_contract_20260929/probe.log"
               "（git@dcddb970 的 4.53.3 ⇒ 模型加载成功，params=3.617B）",
               "runs/vla/a2_env_pi05_sim_20260929/resolve_dryrun.txt STAGE 3"
               "（A2 独立得到同一结论，并引 lerobot pyproject.toml:444 的 custom branch 覆盖）"]}

    if not ev.get("live"):
        rep.add("V-pi05-5_transformers_pi05_ready", None,
                "活体探针未运行（--no-live）⇒ 功能锚无从实测", req,
                note="证据不足 ⇒ 弃权（不当作通过）", ruling_ref=ref, red_when=red)
        return
    if tf_live is None:
        bad.append("transformers 未装/探不到 ⇒ π₀.₅ 连 import 都过不了")
    # ① 功能锚
    if not chk.get("ran"):
        unjudged.append("探针没跑到 `%s`（探针版本旧了？）⇒ 功能锚不可判" % PI05_TF_CHECK_PATH)
    elif chk.get("ok") is not True:
        bad.append("**lerobot 的 π₀.₅ 硬校验不通过**（`%s` 实测 %r，error=%s）⇒ "
                   "`PI05Policy.from_pretrained` 会抛 `ValueError: An incorrect transformer "
                   "version is used`（A2 18:2x 已实测到这个 traceback）"
                   % (PI05_TF_CHECK_PATH, chk.get("ok"), chk.get("error")))
    # ② / ③ 装成记录
    # 用 collect() 时点的**快照原文**，不在判定期间重读（否则与 A2 的并发写会撕成自相矛盾的判词）
    lock_text = ev.get("lock_text") or ""
    man = ev.get("manifest")
    man_text = json.dumps(man, ensure_ascii=False) if isinstance(man, dict) else ""
    dryrun_text = "\n".join(ev.get("resolve_dryrun") or [])
    surfaces = {}
    for tag, txt in (("requirements.lock.txt", lock_text), ("env_manifest.json", man_text),
                     ("resolve_dryrun.txt(计划书，不算装成记录)", dryrun_text)):
        surfaces[tag] = {"present": bool(txt),
                         "has_version": bool(tf_live and tf_live in txt),
                         "has_git_url": "transformers.git" in txt,
                         "has_commit": bool(commit and commit in txt)}
    obs["provenance_recorded_in"] = surfaces
    install_records = {k: v for k, v in surfaces.items()
                       if not k.startswith("resolve_dryrun") and v["present"]}
    if tf_live is not None:
        if commit:
            ok_prov = any(v["has_commit"] for v in install_records.values())
            if not ok_prov:
                where = ([k for k, v in surfaces.items() if v["has_commit"]] or ["(哪儿都没有)"])
                bad.append("transformers 是 **git 安装**（%s@%s，分支 %s），但装成记录里没有 commit_id"
                           "（只在 %s 出现）⇒ 版本字符串 `%s` 认不出是哪一次 build，"
                           "产物不可复现（裁定 34.1）。修法：重新 freeze，让 lock 里出现 "
                           "`transformers @ git+https://github.com/huggingface/transformers.git@%s`"
                           % (du.get("url"), commit[:12], vcs.get("requested_revision"),
                              ",".join(where), tf_live, commit[:12]))
        else:
            if not any(v["has_version"] for v in install_records.values()):
                bad.append("transformers 实测已装 `%s`，但 lock / env_manifest 里都查不到该版本 "
                           "⇒ 产物不可复现（裁定 34.1，与 V-pi05-1 的 M4 同一口径）" % tf_live)
        # ③ lock 与实测必须一致（当前真实现场就是这里红的：lock 4.57.6 / 实测 4.53.3）
        lock_pin = (ev.get("lock_pins_norm") or {}).get("transformers")
        man_pin = None
        if isinstance(man, dict):
            for v in (man.get("venvs") or {}).values():
                if isinstance(v, dict) and isinstance(v.get("pkgs"), dict):
                    man_pin = man_pin or v["pkgs"].get("transformers")
            man_pin = man_pin or (man.get("pin") or {}).get("transformers")
        obs["lock_pin_transformers"] = lock_pin
        obs["manifest_pin_transformers"] = man_pin
        if lock_pin and lock_pin != tf_live:
            bad.append("lock 记 `transformers==%s`，活体实测是 `%s`%s ⇒ 两者不是同一个东西"
                       "（lock 已过期，或环境在 freeze 之后被改过）。修法：重新 freeze 后再交件"
                       % (lock_pin, tf_live,
                          ("（git 安装，commit %s）" % commit[:12]) if commit else ""))
        elif man_pin and man_pin != tf_live:
            bad.append("env_manifest 记 `%s`，活体实测是 `%s` ⇒ 产物与实测不符" % (man_pin, tf_live))

    obs["violations"] = bad
    if bad:
        rep.add("V-pi05-5_transformers_pi05_ready", False, obs, req,
                note=("；".join(unjudged) + "；" if unjudged else "")
                     + "本条**不**以版本区间为判据：区间锚（§8.1）由 V-pi05-1 判，"
                       "两者的冲突已开 RR-B2-06 报 D（B2 不自行改 D 的锚）",
                ruling_ref=ref, red_when=red)
    elif unjudged:
        rep.add("V-pi05-5_transformers_pi05_ready", None, obs, req,
                note="；".join(unjudged) + " ⇒ 证据不足，弃权（不当作通过）",
                ruling_ref=ref, red_when=red)
    else:
        rep.add("V-pi05-5_transformers_pi05_ready", True, obs, req,
                note=("功能锚 + git 溯源双向有牙：M33（校验 False）/ M35（git 装但无 commit）必须红，"
                      "M34（git 装且 commit 进了 lock）必须绿 —— 见 mutation_verdict.json"),
                ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-6 —— A2 交件的**自述可用性**必须自洽，且能被 B2 的独立运行时探针复核（第 6 条牙）
# ---------------------------------------------------------------------------
# 为什么必须有这条（2026-09-29 19:11 的真实现场，B2 只读实测）
# ------------------------------------------------------------------
# A2 的 `env_manifest.json` 不只是版本清单，它还自带一句**可用性结论**：
#   `env_usable = all(assertions.values()) and not frozen_stack_drift`
#   （`scripts/a2_env_manifest.py:313`，B2 只读读过原文），并在 `verdict.blocked_if` 里写明
#   「frozen_stack_drift 非空 ⇒ 断点变更，需 D 登记 + **重过 B2 闸**」。
# 19:11 的交件：`assertions` 9/9 全 true，但 `frozen_stack_drift=["torch","torchvision"]`
# ⇒ `env_usable=false`。B2 独立探针查实这个 drift **不是漂移**：
#   · pi05_sim           runtime `torch.__version__=2.6.0+cu124`、`torch.version.cuda=12.4`、
#                        dist-info 目录 `torch-2.6.0+cu124.dist-info`
#   · lerobot_act/eval   runtime 同为 `2.6.0+cu124` / `12.4`，dist-info 目录却是 `torch-2.6.0.dist-info`
#   （torchvision 同型：两侧 runtime 都 `0.21.0+cu124`，dist-info 一个带 local 段一个不带）
# ⇒ 差异只在 **dist-info 元数据的 local version 段**（安装源写法不同），运行时构建逐字相同。
# 而本闸此前**根本没读** manifest 的这三个键 ⇒ 判词里会出现「B2：V-pi05-4 PASS」与
# 「A2 交件：env_usable=false」两句并列却不解释的话（裁定 36.4 的同型毛病：跨口径不得并列），
# 更糟的是准入可能给绿，而下游（任务 2/3/4 的数据采集与评测）读到的是"环境不可用"。
# 所以补这条牙，判两件**都可实测**的事：
#   ① 自洽：`env_usable` 必须等于 A2 自己写下的那个公式（assertions 全 true 且 drift 为空）；
#   ② 可复核：drift 点名的每个包，B2 用自己的运行时探针再比一遍（torch 另比 `torch.version.cuda`），
#      把成因分成 real_runtime_drift / metadata_only / unexplained / unverifiable 四类写进判词。
# 判红的两种情形**都红**，但判词点名不同：
#   · 成因 = real_runtime_drift ⇒ 冻结栈真被动了（V-pi05-4 通常同时红）；
#   · 成因 = metadata_only ⇒ **A2 的比对口径造假红**，交件必须改口径重出（比 runtime 版本，
#     或先把 local version 段归一化再比）。此时 B2 **不**就地替 A2 宣布"其实可用"：
#     准入不得建立在一份自称不可用的交件上，而用散文推翻交件正是本仓「解释逐渐获得既成地位」
#     的老毛病（裁定 27 / 35.3 / 37.4）。修法归 A2，裁定归 D（RR-B2-07）。
MANIFEST_USABILITY_KEYS = ("assertions", "env_usable", "frozen_stack_drift")

# 交件里这三个键**不止出现在顶层**（2026-09-29 20:0x 用 A2 的真实 manifest 回放实测到）：
#   `env_usable`          顶层 + `verdict.env_usable`
#   `frozen_stack_drift`  **只在** `verdict.*` 与 `baseline_comparison.*`（顶层没有！）
#   `assertions`          顶层
# 第一版只读顶层 ⇒ 对 A2 的**真交件**判 UNJUDGED，而在合成世界里全绿（因为合成世界是
# 按我自己想象的顶层结构写的）。缺陷类与 V-pi05-2 读 receipt 键名那次完全同型：
# 「被测对象与使用对象不是同一个」——合成世界的结构不能代替真交件的结构。
# 修法同 V-pi05-2：多通道读取，**所有命中位置的值必须一致**，不一致就是交件自相矛盾（红）。
MANIFEST_KEY_PATHS = {
    "assertions": ["assertions"],
    "env_usable": ["env_usable", "verdict.env_usable"],
    "frozen_stack_drift": ["frozen_stack_drift", "verdict.frozen_stack_drift",
                           "baseline_comparison.frozen_stack_drift"],
}


def _man_lookup(man, key):
    """按候选路径在交件里找一个键。返回 `(值列表, 命中路径列表, 缺失路径列表)`。

    值列表按路径顺序去重前**全部**返回：调用方要判「多处命中但值不同」这种自相矛盾。
    路径语法只支持 `a.b`（点号下钻 dict），不支持数组下标 —— 交件里这三个键都不在数组里。
    """
    vals, hits, miss = [], [], []
    for path in MANIFEST_KEY_PATHS.get(key, [key]):
        cur = man
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            vals.append(cur)
            hits.append(path)
        else:
            miss.append(path)
    return vals, hits, miss

def _dist_ver_from_path(p):
    """从 dist-info 目录名解析**元数据**版本（`torch-2.6.0+cu124.dist-info` → `2.6.0+cu124`）。

    单列成函数是因为它与 runtime `__version__` 是**两个口径**，判词里必须分开写（裁定 36.4）：
    现场实测同一个 venv 里这两者可以不同（基线 `2.6.0` vs runtime `2.6.0+cu124`）。
    """
    if not p:
        return None
    base = str(p).rstrip("/").rsplit("/", 1)[-1]
    for suf in (".dist-info", ".egg-info"):
        if base.endswith(suf):
            base = base[: -len(suf)]
    if "-" not in base:
        return None
    return base.rsplit("-", 1)[-1]


def _probe_usable(pr):
    """探针记录本身是否可用（解释器在、没报错）。不可用 ⇒ 无从复核，只能弃权。"""
    if not isinstance(pr, dict):
        return False, "探针记录缺失"
    if pr.get("python_exists") is False:
        return False, "解释器不存在"
    if pr.get("probe_error"):
        return False, "probe_error=%s" % str(pr["probe_error"])[:120]
    if pr.get("probe_rc") not in (0, None):
        return False, "probe_rc=%s" % pr.get("probe_rc")
    return True, ""


def _runtime_ver(pr, pkg):
    """取某 venv 里某包的 **runtime** 版本；区分「没探」与「探了但 import 失败」。

    这个区分是牙的一部分：`pkgs` 里**没有这个键**说明 B2 的探针没覆盖它（⇒ 无从复核，弃权），
    而键在、值是 `null` 说明探了且 import 失败（⇒ 那是真实差异，一侧连冻结包都装不上）。
    把两者混为一谈会造出两种错：假红（没探当成不同）与假绿（import 失败当成没探）。
    """
    if not isinstance(pr, dict):
        return None, "no_probe_record"
    if pkg == "torch" and pr.get("torch_version"):
        return pr.get("torch_version"), "ok"
    pk = pr.get("pkgs")
    if not isinstance(pk, dict) or pkg not in pk:
        return None, "not_probed"
    return pk[pkg], ("ok" if pk[pkg] else "import_failed")


def check_v_pi05_6(ev, rep):
    cid = "V-pi05-6_manifest_selfconsistency"
    ref = ("A2 `env_manifest.json` 的 `verdict.blocked_if` 自述口径 + `scripts/a2_env_manifest.py:313`"
           "（B2 只读实测）/ 裁定 36.4（跨口径不得并列）/ 裁定 27.1（恒真闸=没闸）")
    req = ("① 交件自洽：`env_usable` 必须 == A2 自己写的公式 `all(assertions.values()) and not "
           "frozen_stack_drift`；② `env_usable` 必须为 true 准入才可能在环境轴放行；"
           "③ `frozen_stack_drift` 点名的每个包，B2 用独立运行时探针复核"
           "（torch 另比 `torch.version.cuda`），成因必须落到 real_runtime_drift / metadata_only / "
           "unexplained / unverifiable 之一并写进判词")
    red = ("交件自相矛盾（env_usable 与 assertions/frozen_stack_drift 不符，或 assertions 有 False "
           "却写 env_usable=true）；`env_usable is False`（**无论成因**：真漂移 ⇒ 冻结栈被动；"
           "只有 dist-info local version 段不同 ⇒ A2 比对口径假红，交件必须改口径重出）")
    man = ev.get("manifest")
    if not isinstance(man, dict):
        rep.add(cid, None,
                {"manifest_present": man is not None,
                 "missing": [m for m in (ev.get("missing") or []) if "env_manifest" in m]},
                req, note="`env_manifest.json` 缺失或不可解析 ⇒ 自述可用性无从判，弃权（不当作通过）",
                ruling_ref=ref, red_when=red)
        return
    a_vals, a_hits, _ = _man_lookup(man, "assertions")
    u_vals, u_hits, _ = _man_lookup(man, "env_usable")
    d_vals, d_hits, _ = _man_lookup(man, "frozen_stack_drift")
    keymap = {"assertions": (a_vals, a_hits), "env_usable": (u_vals, u_hits),
              "frozen_stack_drift": (d_vals, d_hits)}
    absent = [k for k in MANIFEST_USABILITY_KEYS if not keymap[k][0]]
    # 同一键在多处命中但**值不同** ⇒ 交件自相矛盾。不"随便挑一个"：挑哪一个都是
    # B2 在替 A2 决定它自己说了什么（那正是「解释逐渐获得既成地位」的起点）。
    disagree = []
    for k in MANIFEST_USABILITY_KEYS:
        vals, hits = keymap[k]
        distinct = []
        for v in vals:
            if v not in distinct:
                distinct.append(v)
        if len(distinct) > 1:
            disagree.append({"key": k, "paths": hits, "values": vals})
    assertions = a_vals[0] if a_vals else None
    env_usable = u_vals[0] if u_vals else None
    drift = d_vals[0] if d_vals else None
    if absent or not isinstance(assertions, dict) or not isinstance(drift, list) \
            or not isinstance(env_usable, bool):
        rep.add(cid, None,
                {"keys_not_found": absent, "looked_in": MANIFEST_KEY_PATHS,
                 "found_at": {k: keymap[k][1] for k in MANIFEST_USABILITY_KEYS},
                 "assertions_type": type(assertions).__name__,
                 "env_usable_type": type(env_usable).__name__,
                 "frozen_stack_drift_type": type(drift).__name__},
                req,
                note=("交件里按 %s 这些位置都找不到 %s（或类型不对）⇒ 自述可用性无从判，弃权。"
                      "**不得**因为「没看到红」就记成 PASS（三值纪律）"
                      % (list(MANIFEST_KEY_PATHS.values()), absent or "类型不符的键")),
                ruling_ref=ref, red_when=red)
        return

    n_true = sum(1 for v in assertions.values() if v is True)
    false_assertions = sorted(k for k, v in assertions.items() if v is not True)
    self_formula = bool(all(v is True for v in assertions.values()) and not drift)
    contradictions = []
    for dd in disagree:
        contradictions.append(
            "交件自相矛盾：`%s` 在 %s 这几处的值不一致（%s）⇒ B2 不替 A2 挑一个采信，"
            "必须由 A2 修成交件内部一致" % (dd["key"], dd["paths"],
                                            json.dumps(dd["values"], ensure_ascii=False)[:200]))
    if bool(env_usable) != self_formula:
        contradictions.append(
            "交件自相矛盾：`env_usable=%s`，但按 A2 自己写在 `a2_env_manifest.py:313` 的公式"
            "（assertions 全 true 且 frozen_stack_drift 为空）算出来是 `%s`"
            "（assertions %d/%d true，drift=%s）"
            % (env_usable, self_formula, n_true, len(assertions), drift))
    if env_usable is True and false_assertions:
        contradictions.append("交件自称可用，但 assertions 里有 %d 条非 true：%s"
                              % (len(false_assertions), false_assertions))

    # ---- 独立复核：drift 点名的包，B2 自己再比一遍（不采信交件的比对结果）----
    probes = ev.get("accepted_venv_probe") or {}
    new_pr = ev.get("venv_probe") or {}
    decl_base = ev.get("declared_baseline_venv") or \
        ((man.get("baseline_comparison") or {}).get("baseline_venv"))
    base_pr = probes.get(decl_base) if decl_base else None
    if base_pr is None:
        for v in ACCEPTED_VENVS:
            if isinstance(probes.get(v), dict):
                decl_base, base_pr = v, probes[v]
                break
    unverifiable = []
    recon = []
    ok_n, why_n = _probe_usable(new_pr)
    ok_b, why_b = _probe_usable(base_pr)
    # 只有**交件点了 drift**才需要探针去归因：drift 为空时没有待复核的主张，
    # 版本锚本身由 V-pi05-1 / V-pi05-4 判（它们在无探针时各自弃权/判红），本条不重复设障。
    if drift:
        if not ev.get("live"):
            unverifiable.append("本次是 --no-live（无探针）⇒ 交件点名的 drift 无从独立复核")
        else:
            if not ok_n:
                unverifiable.append("π₀.₅ venv 探针不可用：%s" % why_n)
            if not ok_b:
                unverifiable.append("基线 venv（%s）探针不可用：%s" % (decl_base, why_b))
    if ok_n and ok_b and ev.get("live"):
        for pkg in drift:
            rt_n, st_n = _runtime_ver(new_pr, pkg)
            rt_b, st_b = _runtime_ver(base_pr, pkg)
            dt_n = _dist_ver_from_path((new_pr.get("dist") or {}).get(pkg))
            dt_b = _dist_ver_from_path((base_pr.get("dist") or {}).get(pkg))
            cuda = ({"pi05_sim": new_pr.get("torch_cuda"), "baseline": base_pr.get("torch_cuda")}
                    if pkg == "torch" else None)
            if "not_probed" in (st_n, st_b):
                cls, note = "unverifiable", ("B2 的探针没覆盖 %s（pi05_sim=%s / baseline=%s）⇒ 无从复核"
                                             % (pkg, st_n, st_b))
            elif rt_n is None and rt_b is None:
                cls = "metadata_same" if dt_n == dt_b else "metadata_only"
                note = ("两侧 runtime 都取不到（import 失败，如 torchcodec 缺 FFmpeg 的已知缺口）⇒ "
                        "只能比 dist-info 元数据：%s vs %s" % (dt_n, dt_b))
            elif rt_n is None or rt_b is None:
                cls, note = "real_runtime_drift", (
                    "一侧连冻结包都 import 不了（pi05_sim=%r / baseline=%r）⇒ 真实差异，不是写法问题"
                    % (rt_n, rt_b))
            elif str(rt_n) != str(rt_b):
                cls, note = "real_runtime_drift", "runtime 版本不同：%r vs %r" % (rt_n, rt_b)
            elif pkg == "torch" and str((cuda or {}).get("pi05_sim")) != str((cuda or {}).get("baseline")):
                cls, note = "real_runtime_drift", ("runtime 版本相同但 CUDA 构建不同：%s vs %s"
                                                   % ((cuda or {}).get("pi05_sim"),
                                                      (cuda or {}).get("baseline")))
            elif dt_n != dt_b:
                cls, note = "metadata_only", (
                    "**runtime 逐字相同**（%s；torch.version.cuda %s vs %s），只有 dist-info 元数据的 "
                    "local version 段不同（%s vs %s）⇒ 安装源写法差异，不是环境漂移"
                    % (rt_n, (cuda or {}).get("pi05_sim"), (cuda or {}).get("baseline"), dt_n, dt_b))
            else:
                cls, note = "unexplained", ("runtime 与 dist-info 元数据都相同（%s / %s），交件却报了 drift "
                                            "⇒ 成因不明，必须 A2 解释" % (rt_n, dt_n))
            recon.append({"package": pkg, "class": cls, "note": note,
                          "runtime": {"pi05_sim": rt_n, "baseline": rt_b,
                                      "probe_state": {"pi05_sim": st_n, "baseline": st_b}},
                          "dist_info_metadata": {"pi05_sim": dt_n, "baseline": dt_b},
                          "torch_cuda": cuda})
            if cls == "unverifiable":
                unverifiable.append("drift 点名的 %s 无从独立复核（%s）" % (pkg, note))

    causes = sorted({r["class"] for r in recon})
    obs = {
        # 裁定 36.4：交件自述与 B2 实测**分块**放，不并进同一张表
        "a2_declared": {
            "env_usable": env_usable, "assertions_pass": man.get("assertions_pass"),
            "key_locations": {k: keymap[k][1] for k in MANIFEST_USABILITY_KEYS},
            "key_value_disagreements": disagree,
            "n_assertions_true": "%d/%d" % (n_true, len(assertions)),
            "false_assertions": false_assertions, "frozen_stack_drift": drift,
            "baseline_venv": decl_base,
            "blocked_if": (man.get("verdict") or {}).get("blocked_if"),
            "differing_packages": {k: v for k, v in
                                   ((man.get("baseline_comparison") or {}).get("differing_packages") or {}).items()
                                   if k in (drift or ())},
            "frozen_stack_versions": {k: v for k, v in (man.get("frozen_stack_versions") or {}).items()
                                      if k in (drift or ())},
        },
        "b2_independent_runtime_probe": {
            "pi05_sim": {"venv": new_pr.get("venv"), "torch_version": new_pr.get("torch_version"),
                         "torch_cuda": new_pr.get("torch_cuda"),
                         "pkgs": {k: (new_pr.get("pkgs") or {}).get(k) for k in TORCH_STACK
                                  if k in (new_pr.get("pkgs") or {})},
                         "dist_info": {k: _dist_ver_from_path((new_pr.get("dist") or {}).get(k))
                                       for k in TORCH_STACK if k in (new_pr.get("dist") or {})},
                         "lerobot": (new_pr.get("pkgs") or {}).get("lerobot")},
            "baseline": {"venv": decl_base, "torch_version": (base_pr or {}).get("torch_version"),
                         "torch_cuda": (base_pr or {}).get("torch_cuda"),
                         "pkgs": {k: ((base_pr or {}).get("pkgs") or {}).get(k) for k in TORCH_STACK
                                  if k in ((base_pr or {}).get("pkgs") or {})},
                         "dist_info": {k: _dist_ver_from_path(((base_pr or {}).get("dist") or {}).get(k))
                                       for k in TORCH_STACK
                                       if k in ((base_pr or {}).get("dist") or {})},
                         "lerobot": ((base_pr or {}).get("pkgs") or {}).get("lerobot"),
                         "read_only": True},
        },
        "reconciliation": {"per_package": recon, "causes": causes,
                           "unverifiable": unverifiable,
                           "self_formula_recomputed": self_formula,
                           "contradictions": contradictions},
        "violations": list(contradictions),
    }

    if env_usable is False:
        if "real_runtime_drift" in causes:
            obs["violations"].append(
                "A2 交件自述 `env_usable=false`，且 B2 的独立运行时探针**证实**冻结栈真漂移"
                "（%s）⇒ 断点变更，需 D 登记 + 重过闸（A2 自己写的 blocked_if）"
                % "; ".join("%s: %s" % (r["package"], r["note"]) for r in recon
                            if r["class"] == "real_runtime_drift"))
        elif unverifiable and not causes:
            obs["violations"].append(
                "A2 交件自述 `env_usable=false`，但 B2 无法独立复核成因（%s）⇒ 准入不得放行；"
                "成因待 A2/D 定" % "; ".join(unverifiable))
        else:
            obs["violations"].append(
                "A2 交件自述 `env_usable=false`（assertions %d/%d 全 true、drift=%s），但 B2 的独立运行时"
                "探针显示两侧 runtime 逐字相同（成因=%s：%s）⇒ 这是**交件比对口径造成的假红**："
                "A2 比的是 dist-info 元数据版本（基线写 `2.6.0`、π₀.₅ 侧写 `2.6.0+cu124`），"
                "不是运行时构建。准入不得建立在一份自称不可用的交件上；B2 也**不**用散文就地宣布"
                "「其实可用」。修法：`frozen` 的比对改用 runtime `__version__`（或先归一化 local "
                "version 段），重出 manifest；裁定归 D（RR-B2-07）"
                % (n_true, len(assertions), drift, ",".join(causes) or "无 drift 可比",
                   "; ".join(r["note"] for r in recon) or "drift 为空但 env_usable=false，成因不在 drift"))

    if obs["violations"]:
        rep.add(cid, False, obs, req,
                note=("双向有牙：M36（只有 dist-info 写法差异 ⇒ 必须红，且判词必须点名"
                      "「metadata_only 假红」）/ M38（runtime 真不同 ⇒ 必须红且点名 real_runtime_drift）"
                      "/ M40（assertions 有 False 却自称可用 ⇒ 必须红）/ M37（干净交件 ⇒ 必须绿）"
                      "/ M39（交件缺键 ⇒ 必须弃权，不得 PASS）—— 见 mutation_verdict.json"),
                ruling_ref=ref, red_when=red)
    elif unverifiable:
        rep.add(cid, None, obs, req,
                note="；".join(unverifiable) + " ⇒ 交件的自述可用性无从独立复核，弃权（不当作通过）",
                ruling_ref=ref, red_when=red)
    else:
        rep.add(cid, True, obs, req,
                note=("交件自洽（env_usable=true 与 A2 自己的公式一致）且 B2 的独立运行时探针未发现"
                      "冻结栈差异。复核口径：runtime `__version__` + `torch.version.cuda`；"
                      "dist-info 元数据版本单独记在 `b2_independent_runtime_probe.*.dist_info`，"
                      "**不与 runtime 混算**（裁定 36.4）"),
                ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# 委派：G1–G5（B 的溯源闸）与 V0–V9（B 的迁移不变性闸）—— 不重写，只调用并转录
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# V-pi05-7 —— 控制频率三元组（裁定 45.5 的牙：缺项判黄、折算与声明不符判红）
# ---------------------------------------------------------------------------
# 为什么这条牙必须存在（裁定 45.3 原文的机制）：仿真控制频率与示范频率不一致 ⇒
# action chunk 的**时间尺度**与训练数据不一致（同一 chunk 覆盖不同真实时长），
# SFT 后动作整体偏快/偏慢，而**这种偏差不会在任何单点检查里报错**，
# 只表现为「能接近但抓不准」⇒ 排查成本极高。所以它必须是闸上的一条牙，不是文档里的一句话。
CTRL_HZ_CANDIDATES = [
    "runs/vla/a2_pi05_zeroshot_20260929/ctrl_hz_alignment_a2.json",
]
COMPAT_REPORT_CANDIDATES = [
    "runs/vla/a2_pi05_contract_20260929/compat_dir_report.json",
]
QC_FPS_BAND = (29.0, 31.0)          # 团队 QC 规则 J/V04 的合格区间（D→B2 §11.1 实测）
DEMO_HZ_ANCHOR = 30.0               # 裁定 45.1：控制频率锚定 30.0 Hz
FORBIDDEN_CONTRACT_HZ = (31.25,)    # 裁定 45.1：D 为凑整数 decimation 取的 convenient 值，**明令不得当契约值**
HZ_TOL = 0.01                       # 折算 Hz 与声明 Hz 的容差（比 QC 带宽小三个量级）

HZ_KEYS = ("control_hz", "ctrl_hz", "resulting_control_hz", "control_frequency_hz", "hz", "fps")
TS_KEYS = ("physics_timestep_s", "timestep_s", "timestep", "sim_timestep_s", "physics_dt_s")
CTS_KEYS = ("control_timestep_s", "control_dt_s", "control_period_s")
DEC_KEYS = ("decimation_n_substeps", "decimation", "n_substeps", "decim", "sim_decimation",
            "decimation_if_rounded")
# 「描述现状」的段名 vs 「声明要用」的段名：只有后者才受「必须落在 QC 合格区间」约束。
# 这条区分是**防假红**的关键：A2 的 `as_is.control_hz = 50.0` 是诚实的现状陈述
# （并且自己标了 `in_qc_band_29_31: false`），把它当契约值判红就是造假红。
DESCRIPTIVE_SEG = ("as_is", "asis", "current", "naive_pitfall", "pitfall", "baseline",
                   "measured", "observed", "before")
OPERATIVE_SEG = ("target", "anchor", "contract", "operative", "final", "chosen",
                 "adopted", "selected", "after")
RELATION_KEYS = ("chunk_timescale_options", "chunk_timescale", "resampling", "resample",
                 "resampling_plan", "relation_to_demo_hz", "demo_hz", "anchor_hz",
                 "in_qc_band_29_31", "qc_band")


def _lk(key) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _first_key(d: dict, names) -> tuple:
    for k, v in d.items():
        if _lk(k) in names:
            return k, v
    return None, None


def _hz_groups(obj, path="$", out=None):
    """递归找出所有「(timestep|control_timestep|decimation) + hz」同时出现的 dict ⇒ 一个可核三元组。"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        hz_k, hz_v = _first_key(obj, HZ_KEYS)
        ts_k, ts_v = _first_key(obj, TS_KEYS)
        cts_k, cts_v = _first_key(obj, CTS_KEYS)
        dec_k, dec_v = _first_key(obj, DEC_KEYS)
        if hz_k is not None and isinstance(hz_v, (int, float)) and not isinstance(hz_v, bool):
            out.append({"path": path, "hz_key": hz_k, "hz": float(hz_v),
                        "ts_key": ts_k, "ts": ts_v, "cts_key": cts_k, "cts": cts_v,
                        "dec_key": dec_k, "dec": dec_v,
                        "has_ts": isinstance(ts_v, (int, float)) and not isinstance(ts_v, bool),
                        "has_cts": isinstance(cts_v, (int, float)) and not isinstance(cts_v, bool),
                        "has_dec": isinstance(dec_v, (int, float)) and not isinstance(dec_v, bool)})
        for k, v in obj.items():
            _hz_groups(v, "%s.%s" % (path, k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _hz_groups(v, "%s[%d]" % (path, i), out)
    return out


def _group_role(path: str) -> str:
    segs = [_lk(x) for x in re.split(r"[.\[\]]", path) if x]
    if any(any(o in sg for o in OPERATIVE_SEG) for sg in segs):
        return "operative"
    if any(any(d in sg for d in DESCRIPTIVE_SEG) for sg in segs):
        return "descriptive"
    return "unclassified"


def _has_relation_declaration(doc) -> list:
    """(c) 与示范 30 Hz 的关系：重采样方案 / 锚点声明 / chunk 时间尺度讨论，任一即算声明了。"""
    hits = []

    def walk(o, path="$"):
        if isinstance(o, dict):
            for k, v in o.items():
                if _lk(k) in RELATION_KEYS:
                    hits.append("%s.%s" % (path, k))
                walk(v, "%s.%s" % (path, k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, "%s[%d]" % (path, i))
    walk(doc)
    return hits


def _load_json_docs(root: Path, candidates, override=None) -> list:
    """按候选表读 JSON 交件（**找到的全读**：多于一份时判据要能发现互相矛盾，不是随便挑一份）。"""
    paths = []
    if override:
        paths.append(Path(override) if Path(override).is_absolute() else root / override)
    for c in candidates:
        q = Path(c) if Path(c).is_absolute() else root / c
        if q not in paths:
            paths.append(q)
    docs = []
    for q in paths:
        ent = {"path": str(q), "exists": q.exists(), "parsed": None, "parse_error": None,
               "sha256_12": None, "mtime_iso": None, "bytes": None}
        if q.exists():
            st = q.stat()
            ent["bytes"] = st.st_size
            ent["mtime_iso"] = datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(
                timespec="seconds")
            ent["sha256_12"] = (_sha256_file(q)["sha256"] or "")[:12]
            try:
                ent["parsed"] = json.loads(q.read_text(errors="replace"))
            except Exception as e:                                    # noqa: BLE001
                ent["parse_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        docs.append(ent)
    return docs


def check_v_pi05_7(ev, rep):
    cid = "V-pi05-7_control_hz_triple"
    ref = ("裁定 45.5（`supervisor_memo_20260929.md:2114`）/ 裁定 45.1（30.0 Hz 锚定，"
           "31.25 Hz 不得当契约值）/ 裁定 45.4（原生频率非 30 Hz ⇒ 必须显式声明重采样方案，"
           "不许静默选）/ D→B2 §11.1")
    req = ("产物里出现「控制频率」时，必须同时给出 (a) `timestep` 与 decimation、(b) 折算后的 Hz、"
           "(c) 与示范数据 30 Hz 的关系（相等 / 重采样方案）。缺任一项判**黄**；"
           "折算值与声明值不符判**红**；把 31.25 Hz 当契约值判**红**（裁定 45.1）；"
           "声明为「要用」的频率落在 QC 合格区间 [%.1f,%.1f] 之外且**无**重采样方案 ⇒ 红"
           % QC_FPS_BAND)
    red = ("三元组不自洽（1/(timestep×decimation) 或 1/control_timestep 与声明 Hz 差 > %.2f Hz）；"
           "或 operative 段的 Hz == 31.25（裁定 45.1 明令不得当契约值）；"
           "或 operative 段的 Hz 在 [%.1f,%.1f] 之外且整份产物没有任何重采样/关系声明"
           % (HZ_TOL, QC_FPS_BAND[0], QC_FPS_BAND[1]))
    docs = [d for d in (ev.get("ctrl_hz_docs") or []) if d.get("exists")]
    if not docs:
        rep.add(cid, None,
                {"candidates": [d["path"] for d in (ev.get("ctrl_hz_docs") or [])],
                 "override": ev.get("ctrl_hz_override")},
                req, note=("找不到任何控制频率交件 ⇒ 三元组无从核，弃权（ok=null）。"
                           "**不得**因为「没看到红」记成 PASS（三值纪律）。"
                           "候选路径见 observed；A2 若把它落在别处，用 `--ctrl-hz-doc` 指过来"),
                ruling_ref=ref, red_when=red)
        return
    parsed = [d for d in docs if d.get("parsed") is not None]
    if not parsed:
        rep.add(cid, None, {"docs": [{k: d[k] for k in ("path", "exists", "parse_error")}
                                     for d in docs]},
                req, note="交件存在但不可解析 ⇒ 弃权（不当作通过）", ruling_ref=ref, red_when=red)
        return

    violations, warns, all_groups, groups, relation_hits = [], [], [], [], []
    for d in parsed:
        doc = d["parsed"]
        gs = _hz_groups(doc)
        rel = _has_relation_declaration(doc)
        relation_hits += ["%s:%s" % (Path(d["path"]).name, h) for h in rel]
        for g in gs:
            g["role"] = _group_role(g["path"])
            all_groups.append({k: g[k] for k in ("path", "role", "hz_key", "hz", "ts_key",
                                                 "ts", "cts_key", "cts", "dec_key", "dec",
                                                 "has_ts", "has_cts", "has_dec")})
            if not (g["has_ts"] or g["has_cts"]) or not g["has_dec"]:
                warns.append("缺 (a)：`%s` 只有 %s=%s，timestep=%s / control_timestep=%s / "
                             "decimation=%s ⇒ 三元组不完整（裁定 45.5：缺任一项判黄）"
                             % (g["path"], g["hz_key"], g["hz"], g["ts"], g["cts"], g["dec"]))
            # 折算口径（**防假红**的关键，2026-09-29 20:5x 现场逼出来的）：
            # 一个组里可能同时给 `physics_timestep × decimation` 与 `control_timestep` 两种折算，
            # 而 A2 的 `naive_pitfall` 组**故意**让两者不一致（它演示的就是"只改 DT 不改 timestep
            # ⇒ decimation 只能取整 17 ⇒ 29.41 Hz"这个坑）。若逐条要求全部相符，就会把
            # **对坑的诚实陈述**判成红（本仓第 N 起假红）。所以口径是：
            #   声明的 Hz 必须与**至少一种**折算相符；一种都不符才是"折算值与声明值不符"。
            #   只对上了其中一种（另一种不符）⇒ 记进 observed 的 partial_match，不判红也不判黄。
            implied = []
            if g["has_ts"] and g["has_dec"] and float(g["ts"]) > 0 and int(g["dec"]) > 0:
                implied.append(("1/(timestep×decimation)", 1.0 / (float(g["ts"]) * int(g["dec"]))))
            if g["has_cts"] and float(g["cts"]) > 0:
                implied.append(("1/control_timestep", 1.0 / float(g["cts"])))
            matched = [(lb, v) for lb, v in implied if abs(v - g["hz"]) <= HZ_TOL]
            unmatched = [(lb, v) for lb, v in implied if abs(v - g["hz"]) > HZ_TOL]
            if implied and not matched:
                msg = ("折算值与声明值不符：`%s` 声明 `%s=%s`，但 %s ⇒ 裁定 45.5 判红。"
                       "修法：把三元组改成同一套数（timestep=%s, decimation=%s, "
                       "control_timestep=%s）"
                       % (g["path"], g["hz_key"], g["hz"],
                          "; ".join("%s=%.4f Hz（差 %.4f > 容差 %.2f）"
                                    % (lb, v, abs(v - g["hz"]), HZ_TOL) for lb, v in unmatched),
                          g["ts"], g["dec"], g["cts"]))
                if g["role"] == "operative":
                    violations.append(msg)
                else:
                    warns.append(msg + "［注：该组是 `%s`（描述现状/演示坑），故判黄不判红——"
                                       "但**要用的**那一组必须自洽］" % g["role"])
            elif unmatched:
                g["partial_match"] = {"matched": [lb for lb, _ in matched],
                                      "unmatched": [{"label": lb, "hz": round(v, 6)}
                                                    for lb, v in unmatched]}
            if g["has_ts"] and g["has_dec"] and g["has_cts"]:
                prod = float(g["ts"]) * int(g["dec"])
                if abs(prod - float(g["cts"])) > max(1e-9, 1e-6 * float(g["cts"])):
                    msg = ("三元组内部不自洽：`%s` 的 timestep×decimation = %.9f s，"
                           "但 control_timestep 声明 %.9f s" % (g["path"], prod, float(g["cts"])))
                    if g["role"] == "operative":
                        violations.append(msg)
                    else:
                        g.setdefault("internal_ambiguity", msg)
            if g["role"] == "operative" and any(
                    abs(g["hz"] - f) < 1e-9 for f in FORBIDDEN_CONTRACT_HZ):
                violations.append(
                    "`%s` 把 **31.25 Hz** 当作要用的控制频率 ⇒ 裁定 45.1 明令禁止："
                    "31.25 Hz 是 D 为凑整数 decimation（500 Hz ÷ 16）取的 convenient 值，"
                    "**不是契约值**；锚定值是 30.0 Hz（物理 1/480 + decimation 16）" % g["path"])
            if g["role"] == "operative" and not (
                    QC_FPS_BAND[0] <= g["hz"] <= QC_FPS_BAND[1]) and not rel:
                violations.append(
                    "`%s` 声明要用的控制频率 %s Hz 落在团队 QC 合格区间 [%.1f,%.1f] 之外，"
                    "而整份产物**没有**重采样方案 / 与示范 30 Hz 的关系声明 ⇒ 裁定 45.4："
                    "原生频率非 30 Hz 必须显式声明方案并报 D 裁，不许静默选"
                    % (g["path"], g["hz"], QC_FPS_BAND[0], QC_FPS_BAND[1]))
        if not gs:
            warns.append("交件 `%s` 里找不到任何 (timestep|decimation)+Hz 的三元组" % d["path"])
        groups.append({"doc": d["path"], "n_groups": len(gs),
                       "roles": sorted({g["role"] for g in gs}),
                       "operative_hz": sorted({g["hz"] for g in gs if g["role"] == "operative"})})
    if not relation_hits:
        warns.append("缺 (c)：整份产物没有出现与示范 30 Hz 的关系声明"
                     "（重采样方案 / chunk 时间尺度 / 锚点 Hz / QC 区间自述，任一即可）")
    anchor_seen = any(abs(g["hz"] - DEMO_HZ_ANCHOR) < 1e-6 for g in all_groups)
    if not anchor_seen:
        warns.append("产物里没有任何一组折算到 **30.0 Hz**（裁定 45.1 的锚定值）⇒ "
                     "无法核对「仿真控制频率是否锚定 30 Hz」")

    obs = {"docs": [{k: d[k] for k in ("path", "exists", "bytes", "mtime_iso", "sha256_12",
                                       "parse_error")} for d in docs],
           "docs_summary": groups, "triple_groups_found": all_groups,
           "hz_consistency_rule": ("声明 Hz 必须与**至少一种**折算（1/(timestep×decimation) 或 "
                                   "1/control_timestep）相符；一种都不符 ⇒ operative 组判红、"
                                   "descriptive 组判黄。只对上一部分 ⇒ 记 partial_match，不判红"
                                   "（否则 A2 的 `naive_pitfall` 那种「故意演示不自洽」的组会造假红）"),
           "relation_declaration_hits": relation_hits[:20],
           "n_relation_declaration_hits": len(relation_hits),
           "anchor_30hz_present": anchor_seen,
           "qc_band": list(QC_FPS_BAND), "tolerance_hz": HZ_TOL,
           "forbidden_contract_hz": list(FORBIDDEN_CONTRACT_HZ),
           "violations": violations, "warn_items": sorted(set(warns))}
    if violations:
        rep.add(cid, False, obs, req, note="；".join(violations[:4]), ruling_ref=ref, red_when=red)
    elif warns:
        rep.add(cid, True, obs, req, status=STATUS_WARN,
                note="；".join(sorted(set(warns))[:4]), ruling_ref=ref, red_when=red)
    else:
        rep.add(cid, True, obs, req,
                note=("三元组齐全且自洽（%d 组），operative 段落在 QC 合格区间内，"
                      "与示范 30 Hz 的关系已声明（%d 处命中）。**注意**：本条牙只判"
                      "「有没有把三元组和关系写清楚、写的数自不自洽」，"
                      "**不**替 D 选定重采样方案（甲/乙/丙 仍是 RR-B2-08）"
                      % (len(all_groups), len(relation_hits))),
                ruling_ref=ref, red_when=red)


# ---------------------------------------------------------------------------
# V-pi05-8 —— 兼容目录「删步骤」的等价性（裁定 44.2 的牙）
# ---------------------------------------------------------------------------
PROCESSOR_FILES = ("policy_preprocessor.json", "policy_postprocessor.json")
IDENTITY_PATTERN = re.compile(r"if\s+not\s+self\.enabled\s*:\s*\n\s*return\s+transition")
REF_PATH_RE = re.compile(r"([A-Za-z0-9_./\-]+\.py)")
BLOB_SHA_RE = re.compile(r"\b([0-9a-f]{40})\b")
LINE_REF_RE = re.compile(r":(\d{1,5})\b")
DROPPED_CLASS_RE = re.compile(
    r"class\s+(RelativeActionsProcessorStep|AbsoluteActionsProcessorStep)\b")
BIG_FILE_BYTES = 512 << 20            # 超过这个就当"大权重"，必须软链不许复制（NFS 已用 94%）


def _steps_of(doc):
    if not isinstance(doc, dict):
        return None
    for k in ("steps", "processors", "pipeline", "chain"):
        v = doc.get(k)
        if isinstance(v, list):
            return v
    return None


def _step_name(st) -> str:
    if isinstance(st, dict):
        for k in ("registry_name", "name", "step", "id"):
            if isinstance(st.get(k), str):
                return st[k]
    return "<unnamed:%s>" % type(st).__name__


def _step_config(st):
    return st.get("config") if isinstance(st, dict) else None


def _installed_lerobot_scan(venv: str):
    """只读扫 venv 里 lerobot 的 processor 注册名与被删步骤的类是否存在（**不 import**）。

    为什么要 B2 自己扫：A2 的 `root_cause` 说「0.4.4 的 processor registry 没有这两步」，
    这是删步骤的**前提**；前提若不成立（其实有，只是名字不同），删步骤就不再是恒等变换。
    不采信自述（裁定 31.2 同族），但也不做重活：只读文件、只匹配注册装饰器与类名。
    """
    out = {"venv": str(venv), "scanned": False, "n_py_scanned": 0,
           "registry_names": [], "dropped_classes_found": [], "lerobot_present": None}
    v = Path(venv)
    lr_dirs = sorted(v.glob("lib/python3*/site-packages/lerobot"))
    if not lr_dirs:
        return out
    lr = lr_dirs[0]
    out["lerobot_present"] = str(lr)
    names, classes, n = set(), [], 0
    reg_re = re.compile(r'ProcessorStepRegistry\.register\(\s*name="([^"]+)"')
    try:
        files = [q for q in lr.rglob("*.py")][:6000]
    except OSError:
        return out
    for q in files:
        try:
            txt = q.read_text(errors="replace")
        except OSError:
            continue
        n += 1
        names.update(reg_re.findall(txt))
        for m in DROPPED_CLASS_RE.finditer(txt):
            classes.append({"class": m.group(1), "file": str(q)})
    out.update({"scanned": True, "n_py_scanned": n, "registry_names": sorted(names),
                "dropped_classes_found": classes})
    return out


def _collect_compat(root: Path, venv: str, override=None, receipt_recompute=None) -> dict:
    cz = {"report_docs": _load_json_docs(root, COMPAT_REPORT_CANDIDATES, override),
          "override": override, "lerobot_scan": _installed_lerobot_scan(venv),
          "receipt_recompute_available": bool(receipt_recompute)}
    rep_doc = next((d["parsed"] for d in cz["report_docs"]
                    if d.get("exists") and d.get("parsed") is not None), None)
    cz["report_present"] = rep_doc is not None
    cz["report"] = rep_doc if isinstance(rep_doc, dict) else None
    src = compat = None
    if isinstance(rep_doc, dict):
        for k in ("src_weights_dir", "source_dir", "src_dir", "orig_dir"):
            if isinstance(rep_doc.get(k), str) and rep_doc[k]:
                src = Path(rep_doc[k]); break
        for k in ("compat_dir", "compat_weights_dir", "out_dir", "dir"):
            if isinstance(rep_doc.get(k), str) and rep_doc[k]:
                compat = Path(rep_doc[k]); break
    cz["src_weights_dir"] = str(src) if src else None
    cz["compat_dir"] = str(compat) if compat else None
    cz["src_exists"] = bool(src and src.exists())
    cz["compat_exists"] = bool(compat and compat.exists())
    # 两侧的 processor JSON：B2 **自己读、自己比**（不采信 report 里的 kept/dropped 清单）
    sides = {}
    for fn in PROCESSOR_FILES:
        ent = {}
        for tag, base in (("src", src), ("compat", compat)):
            p = (base / fn) if base else None
            ent[tag] = {"path": str(p) if p else None, "exists": bool(p and p.exists()),
                        "is_symlink": bool(p and p.is_symlink()), "parsed": None,
                        "parse_error": None, "sha256_12": None, "bytes": None,
                        "mtime_iso": None, "steps": None}
            if p and p.exists():
                st = p.stat()
                ent[tag]["bytes"] = st.st_size
                ent[tag]["mtime_iso"] = datetime.fromtimestamp(
                    st.st_mtime).astimezone().isoformat(timespec="seconds")
                ent[tag]["sha256_12"] = (_sha256_file(p)["sha256"] or "")[:12]
                doc, err = None, None
                try:
                    doc = json.loads(p.read_text(errors="replace"))
                except Exception as e:                                # noqa: BLE001
                    err = "%s: %s" % (type(e).__name__, str(e)[:160])
                ent[tag]["parsed"] = doc
                ent[tag]["parse_error"] = err
                st_list = _steps_of(doc)
                ent[tag]["steps"] = ([{"registry_name": _step_name(x),
                                       "config": _step_config(x)} for x in st_list]
                                     if isinstance(st_list, list) else None)
        sides[fn] = ent
    cz["processor_files"] = sides
    entries = []
    if compat and compat.exists():
        for q in sorted(compat.iterdir()):
            tgt = None
            if q.is_symlink():
                try:
                    tgt = str(Path(os.readlink(q)))
                except OSError:
                    tgt = "<unreadable>"
            st = q.stat() if q.exists() else None
            entries.append({"name": q.name, "is_symlink": q.is_symlink(), "symlink_to": tgt,
                            "is_dir": q.is_dir(),
                            "bytes": (st.st_size if (st and not q.is_dir()) else None)})
    cz["compat_entries"] = entries
    src_entries = []
    if src and src.exists():
        for q in sorted(src.iterdir()):
            st = q.stat() if q.exists() else None
            src_entries.append({"name": q.name, "is_dir": q.is_dir(),
                                "bytes": (st.st_size if (st and not q.is_dir()) else None),
                                "mtime_iso": (datetime.fromtimestamp(st.st_mtime).astimezone()
                                              .isoformat(timespec="seconds")) if st else None})
    cz["src_entries"] = src_entries
    eq = (cz["report"] or {}).get("equivalence_evidence")
    prose = (cz["report"] or {}).get("equivalence_argument")
    cz["equivalence_structured"] = eq if isinstance(eq, dict) else None
    cz["equivalence_prose"] = prose if isinstance(prose, str) else None
    ref_path = blob_claim = None
    line_claims = []
    if isinstance(eq, dict):
        ref_path = eq.get("reference_file") or eq.get("path")
        blob_claim = eq.get("blob_sha1") or eq.get("git_blob_sha1")
        line_claims = eq.get("identity_lines") or []
    if not ref_path and isinstance(prose, str):
        cands = [c for c in REF_PATH_RE.findall(prose) if "processor" in c.lower() or "/" in c]
        ref_path = cands[0] if cands else None
        m = BLOB_SHA_RE.search(prose)
        blob_claim = m.group(1) if m else None
        line_claims = [int(x) for x in LINE_REF_RE.findall(prose)]
    cz["equivalence_ref_claim"] = {"reference_file": ref_path, "blob_sha1": blob_claim,
                                   "identity_lines": line_claims}
    refinfo = {"claimed_path": ref_path, "resolved_path": None, "exists": None,
               "blob_sha1_recomputed": None, "blob_sha1_matches_claim": None,
               "identity_pattern_hits": None, "claimed_lines_verified": None,
               "sha256_12": None, "bytes": None}
    if ref_path:
        rp = Path(ref_path)
        if not rp.is_absolute():
            rp = root / ref_path
        refinfo["resolved_path"] = str(rp)
        refinfo["exists"] = rp.exists()
        if rp.exists():
            refinfo["bytes"] = rp.stat().st_size
            refinfo["sha256_12"] = (_sha256_file(rp)["sha256"] or "")[:12]
            refinfo["blob_sha1_recomputed"] = _git_blob_sha1(rp)
            if blob_claim:
                refinfo["blob_sha1_matches_claim"] = (
                    refinfo["blob_sha1_recomputed"] == blob_claim)
            try:
                txt = rp.read_text(errors="replace")
            except OSError:
                txt = ""
            lines = txt.splitlines()
            hits = []
            for m in IDENTITY_PATTERN.finditer(txt):
                hits.append(txt[:m.start()].count("\n") + 2)   # `return transition` 那一行
            refinfo["identity_pattern_hits"] = hits
            ver = []
            for ln in [int(x) for x in (line_claims or []) if str(x).isdigit()]:
                body = lines[ln - 1].strip() if 0 < ln <= len(lines) else None
                ver.append({"claimed_line": ln, "text": body,
                            "is_identity_guard": bool(
                                body and re.search(r"if\s+not\s+self\.enabled\s*:", body))})
            refinfo["claimed_lines_verified"] = ver or None
    cz["equivalence_ref_verification"] = refinfo
    return cz


def check_v_pi05_8(ev, rep):
    cid = "V-pi05-8_compat_dir_step_deletion"
    ref = ("裁定 44.2（`supervisor_memo_20260929.md:2084` 起：兼容目录删步骤**需自证等价**、"
           "原始权重目录只读）/ D→B2 §11.6-①（闸应当能识别「删步骤」这类改动）/ "
           "裁定 27.1（恒真闸=没闸）")
    req = ("① 兼容目录与源 ckpt 的 processor 步骤差异必须由 B2 **自己算出来并逐条点名**"
           "（删除/新增/改配置/改顺序），不采信交件的 kept/dropped 清单；"
           "② 被删步骤在源里必须 `config.enabled is False`（显式 false；缺失或 true 都不算）；"
           "③ 每条删除必须有**代码级**恒等证据（裁定 44.2）：被点名的参考文件存在、"
           "其 git blob sha1 与声明逐字相同、被点名的行确实是 `if not self.enabled: return transition`；"
           "④ 只许删，不许新增步骤、改保留步骤的 config 或换顺序；"
           "⑤ 大权重必须**软链**回源目录（不得复制 14.47 GB；NFS 已用 94%）且软链落在源目录内；"
           "⑥ 被删步骤的名字必须确实不在**本机安装的** lerobot registry 里（B2 只读扫 site-packages 复核）")
    red = ("删掉了 `enabled` 不为 false 的步骤（= 改变数据流，不是恒等）；或删除无代码级等价证据 / "
           "证据里的 blob sha1 与参考文件不符 / 点名的行不是恒等守卫；或兼容目录**新增**了步骤、"
           "改了保留步骤的 config、换了顺序；或大权重是复制而不是软链、软链指向源目录之外；"
           "或被删步骤其实存在于本机 lerobot registry（删除前提不成立 ⇒ 删它不等价）")
    cz = ev.get("compat") or {}
    if not cz.get("report_present") and not cz.get("compat_exists"):
        rep.add(cid, None,
                {"report_candidates": [d["path"] for d in (cz.get("report_docs") or [])],
                 "compat_dir": cz.get("compat_dir"), "override": cz.get("override")},
                req, note=("既没有兼容目录报告、也没有兼容目录本身 ⇒ 无从判，弃权（ok=null）。"
                           "**不得**因为「没看到红」记成 PASS（三值纪律）；"
                           "A2 若把它落在别处，用 `--compat-report` 指过来"),
                ruling_ref=ref, red_when=red)
        return

    sides = cz.get("processor_files") or {}
    violations, warns, diffs, dropped_all = [], [], [], []
    for fn, ent in sides.items():
        src_e, cmp_e = ent.get("src") or {}, ent.get("compat") or {}
        if not src_e.get("exists") or not cmp_e.get("exists"):
            warns.append("%s：源侧存在=%s / 兼容侧存在=%s ⇒ 这一件无法比对"
                         % (fn, src_e.get("exists"), cmp_e.get("exists")))
            continue
        s_steps, c_steps = src_e.get("steps"), cmp_e.get("steps")
        if not isinstance(s_steps, list) or not isinstance(c_steps, list):
            warns.append("%s：步骤序列读不出来（解析错误 源=%s / 兼容=%s）"
                         % (fn, src_e.get("parse_error"), cmp_e.get("parse_error")))
            continue
        s_names = [x["registry_name"] for x in s_steps]
        c_names = [x["registry_name"] for x in c_steps]
        deleted = [n for n in s_names if n not in c_names]
        added = [n for n in c_names if n not in s_names]
        kept_order_src = [n for n in s_names if n in c_names]
        reordered = (kept_order_src != c_names)
        changed_cfg = []
        for i, n in enumerate(c_names):
            if n in s_names:
                s_cfg = s_steps[s_names.index(n)].get("config")
                c_cfg = c_steps[i].get("config")
                if json.dumps(s_cfg, sort_keys=True, ensure_ascii=False) != \
                        json.dumps(c_cfg, sort_keys=True, ensure_ascii=False):
                    changed_cfg.append({"step": n, "src_config": s_cfg, "compat_config": c_cfg})
        for n in deleted:
            cfg = s_steps[s_names.index(n)].get("config")
            enabled = cfg.get("enabled") if isinstance(cfg, dict) else None
            dropped_all.append({"file": fn, "step": n, "src_config": cfg,
                                "enabled_in_src": enabled,
                                "enabled_is_explicit_false": (enabled is False)})
            if enabled is not False:
                violations.append(
                    "%s：删掉的步骤 `%s` 在源 ckpt 里 `config.enabled = %r`（**不是**显式 false）"
                    "⇒ 删它会改变数据流，不是恒等变换。裁定 44.2 只允许删「registry 缺失**且** "
                    "enabled 明确 false」的步骤" % (fn, n, enabled))
        if added:
            violations.append("%s：兼容目录**新增**了源 ckpt 没有的步骤 %s ⇒ 未声明的改动"
                              "（本条牙只允许「删 enabled=false 的步骤」这一种改动）" % (fn, added))
        if reordered:
            violations.append("%s：保留步骤的顺序变了（源顺序 %s ⇒ 兼容顺序 %s）⇒ "
                              "processor 管线是**有序**的，换序不是恒等" % (fn, kept_order_src, c_names))
        for cc in changed_cfg:
            violations.append("%s：保留步骤 `%s` 的 config 被改了（源=%s ⇒ 兼容=%s）⇒ 未声明的改动"
                              % (fn, cc["step"],
                                 json.dumps(cc["src_config"], ensure_ascii=False)[:160],
                                 json.dumps(cc["compat_config"], ensure_ascii=False)[:160]))
        diffs.append({"file": fn, "n_steps_src": len(s_names), "n_steps_compat": len(c_names),
                      "deleted": deleted, "added": added, "reordered": reordered,
                      "config_changed": [c["step"] for c in changed_cfg],
                      "src_sha256_12": src_e.get("sha256_12"),
                      "compat_sha256_12": cmp_e.get("sha256_12")})

    refv = cz.get("equivalence_ref_verification") or {}
    claim = cz.get("equivalence_ref_claim") or {}
    ev_ok, ev_why = None, []
    if not (cz.get("equivalence_structured") or cz.get("equivalence_prose")):
        ev_ok = False
        ev_why.append("交件里既没有结构化的 `equivalence_evidence`、也没有 `equivalence_argument` "
                      "散文 ⇒ 删步骤**无自证**（裁定 44.2 要代码级证据，不是读 config 就下结论）")
    elif not claim.get("reference_file"):
        ev_ok = False
        ev_why.append("等价性说明里点不出任何参考实现文件（`.py`）⇒ 无法做代码级复核")
    elif not refv.get("exists"):
        ev_ok = False
        ev_why.append("点名的参考文件不存在：%s（resolved=%s）"
                      % (claim.get("reference_file"), refv.get("resolved_path")))
    else:
        if claim.get("blob_sha1") and refv.get("blob_sha1_matches_claim") is False:
            ev_ok = False
            ev_why.append("参考文件的 git blob sha1 与声明不符：声明 %s、B2 复算 %s "
                          "⇒ 证据不是被点名的那个版本"
                          % (claim.get("blob_sha1"), refv.get("blob_sha1_recomputed")))
        if not (refv.get("identity_pattern_hits") or []):
            ev_ok = False
            ev_why.append("参考文件里找不到 `if not self.enabled: return transition` 形态的恒等返回 "
                          "⇒ 「enabled=false 即恒等」这个前提**没有被代码证明**")
        bad_lines = [v for v in (refv.get("claimed_lines_verified") or [])
                     if not v.get("is_identity_guard")]
        if bad_lines:
            ev_ok = False
            ev_why.append("点名的行号不是恒等守卫：%s"
                          % json.dumps(bad_lines, ensure_ascii=False)[:200])
        if ev_ok is None:
            ev_ok = True
    if dropped_all and ev_ok is False:
        for w in ev_why:
            violations.append("删步骤自证不成立：%s" % w)
    elif dropped_all and ev_ok is True:
        n_hits = len(refv.get("identity_pattern_hits") or [])
        if n_hits < len(dropped_all):
            warns.append("恒等返回只找到 %d 处，但删了 %d 步 ⇒ 无法逐步对上（不判红，"
                         "但请 A2 在证据里逐步点名）" % (n_hits, len(dropped_all)))

    big_threshold = ev.get("big_file_bytes") or BIG_FILE_BYTES
    for e in (cz.get("compat_entries") or []):
        if (e.get("bytes") or 0) > big_threshold:
            if not e.get("is_symlink"):
                violations.append("兼容目录里 `%s` 是**实体文件**（%s 字节）而不是软链 ⇒ 复制了大权重。"
                                  "NFS 已用 94%%，且复制体会让「原始权重目录只读」无法证明（裁定 44.2）"
                                  % (e["name"], e["bytes"]))
            else:
                tgt = e.get("symlink_to") or ""
                srcd = (cz.get("src_weights_dir") or "").rstrip("/")
                if srcd and not tgt.startswith(srcd):
                    violations.append("兼容目录里 `%s` 软链到 `%s`，**不在**源权重目录 `%s` 下 ⇒ "
                                      "指向不明的权重（同一性无从核）" % (e["name"], tgt, srcd))
    if cz.get("compat_exists") and not [e for e in (cz.get("compat_entries") or [])
                                        if e.get("is_symlink")]:
        warns.append("兼容目录里没有任何软链条目 ⇒ 权重是复制体或压根不在（见 compat_entries）")

    scan = cz.get("lerobot_scan") or {}
    if dropped_all:
        if not scan.get("scanned"):
            warns.append("无法只读扫描 lerobot 安装树（venv=%s，lerobot_present=%s）⇒ "
                         "「registry 里没有这两步」这个删除前提**未独立复核**"
                         % (scan.get("venv"), scan.get("lerobot_present")))
        else:
            reg = set(scan.get("registry_names") or [])
            present = sorted({d["step"] for d in dropped_all} & reg)
            if present:
                violations.append("被删步骤 %s **确实存在于**本机 lerobot 的 processor registry"
                                  "（扫了 %d 个 .py）⇒ 「registry 缺失」这个删除前提不成立，"
                                  "删它就不是恒等变换" % (present, scan.get("n_py_scanned")))
            if scan.get("dropped_classes_found"):
                warns.append("本机 lerobot 里找到了被删步骤的**类**：%s ⇒ 可能只是没注册进 registry"
                             "（可用别的接法），删之前应先确认"
                             % json.dumps(scan["dropped_classes_found"], ensure_ascii=False)[:200])

    obs = {"report_docs": [{k: d[k] for k in ("path", "exists", "bytes", "mtime_iso",
                                              "sha256_12", "parse_error")}
                           for d in (cz.get("report_docs") or [])],
           "src_weights_dir": cz.get("src_weights_dir"), "src_exists": cz.get("src_exists"),
           "compat_dir": cz.get("compat_dir"), "compat_exists": cz.get("compat_exists"),
           "diffs_computed_by_b2": diffs,
           "dropped_steps_verified": dropped_all,
           "report_claimed_dropped": (cz.get("report") or {}).get("dropped_steps"),
           "report_claimed_kept": (cz.get("report") or {}).get("kept_steps"),
           "compat_entries": cz.get("compat_entries"),
           "src_entries": cz.get("src_entries"),
           "equivalence_claim": claim,
           "equivalence_ref_verification": refv,
           "equivalence_structured_present": bool(cz.get("equivalence_structured")),
           "equivalence_prose_present": bool(cz.get("equivalence_prose")),
           "lerobot_registry_scan": {"scanned": scan.get("scanned"),
                                     "lerobot_present": scan.get("lerobot_present"),
                                     "n_py_scanned": scan.get("n_py_scanned"),
                                     "n_registry_names": len(scan.get("registry_names") or []),
                                     "dropped_classes_found": scan.get("dropped_classes_found"),
                                     "dropped_names_present_in_registry": sorted(
                                         {d["step"] for d in dropped_all}
                                         & set(scan.get("registry_names") or []))},
           "big_file_threshold_bytes": big_threshold,
           "violations": violations, "warn_items": sorted(set(warns))}
    note_extra = ("参考文件的**上游来源**（是否真是 lerobot `main`）B2 无法本机核验："
                  "本机没有 lerobot main 的 checkout，只能证明「交件里那份文件的 blob sha1 与声明一致、"
                  "且它内部确有恒等返回」⇒ 上游出处记 external_unverified（裁定 36.4，不与本机实测混算）。")
    if violations:
        rep.add(cid, False, obs, req, note=("；".join(violations[:4]) + "。" + note_extra),
                ruling_ref=ref, red_when=red)
    elif warns:
        rep.add(cid, True, obs, req, status=STATUS_WARN,
                note=("；".join(sorted(set(warns))[:4]) + "。" + note_extra),
                ruling_ref=ref, red_when=red)
    else:
        rep.add(cid, True, obs, req,
                note=("B2 自己算出的差异 = 删 %d 步（%s），全部 `enabled is False`；"
                      "无新增、无改配置、无换序；大权重是软链回源目录；被删步骤确实不在本机 "
                      "lerobot registry（扫了 %s 个 .py）。%s"
                      % (len(dropped_all),
                         ", ".join("%s:%s" % (d["file"].replace("policy_", "").replace(".json", ""),
                                              d["step"]) for d in dropped_all),
                         scan.get("n_py_scanned"), note_extra)),
                ruling_ref=ref, red_when=red)


def _run(cmd, timeout=3600):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"rc": r.returncode, "stdout": r.stdout or "", "stderr": r.stderr or "",
                "cmd": [str(x) for x in cmd]}
    except Exception as e:
        return {"rc": None, "stdout": "", "stderr": "%s: %s" % (type(e).__name__, e),
                "cmd": [str(x) for x in cmd]}


def _guard_once(root: Path, py: str, out_json: Path, extra=()):
    cmd = [py, str(root / "scripts/b_env_provenance_guard.py"), "--root", str(root),
           "--json-out", str(out_json), "--quiet"] + list(extra)
    r = _run(cmd)
    log = out_json.with_suffix(".log")
    log.write_text("CMD: %s\nRC: %s\n--- stdout ---\n%s\n--- stderr ---\n%s\n"
                   % (" ".join(r["cmd"]), r["rc"], r["stdout"], r["stderr"]))
    doc = None
    if out_json.exists():
        try:
            doc = json.loads(out_json.read_text(errors="replace"))
        except Exception:
            doc = None
    return doc, r


def _transcribe_guard(rep, doc, tag, ref, req, red):
    s = (doc or {}).get("summary") or {}
    checks_in = [c for c in ((doc or {}).get("checks") or []) if isinstance(c, dict)]
    # ---- 逐条先归一（三值集外的 status ⇒ UNJUDGED；id 去空白、缺失不留 null），再**自己**汇总 ----
    # 为什么不只读上游的 `summary`：那会漏掉一种**假绿** —— 上游把某条写成 `N_A`/null 时，
    # 它的 `n_red` 仍是 0，于是聚合判 PASS，而那条其实"没判"（裁定 78.2：UNJUDGED 必须计入非绿）。
    # T9 是这条的牙。上游的 summary 仍然**逐字保留**在 `upstream_summary_verbatim` 里，
    # 两个口径并排给出并显式登记是否一致（裁定 36.4：跨口径不得并列**而不标注**）。
    norm = []
    for idx, c in enumerate(checks_in):
        st_raw = c.get("status")
        outside = st_raw not in (STATUS_PASS, STATUS_WARN, STATUS_RED)
        cid_raw = c.get("check_id")
        if cid_raw is None:
            cid_raw = c.get("id")
        cid_base = str(cid_raw).strip() if cid_raw is not None else ""
        null_id = (cid_raw is None or not cid_base)
        if null_id:
            cid_base = "G_index%d" % idx           # 裁定 78.3：**不留 null**
        norm.append({"c": c, "idx": idx, "st_raw": st_raw, "outside": outside,
                     "st": (STATUS_UNJUDGED if outside else st_raw),
                     "cid_raw": cid_raw, "cid_base": cid_base, "null_id": null_id,
                     "ws_stripped": (cid_raw is not None and cid_base != str(cid_raw))})
    rc = {st: sum(1 for x in norm if x["st"] == st)
          for st in (STATUS_PASS, STATUS_WARN, STATUS_RED, STATUS_UNJUDGED)}
    no_checks = (not norm)
    if rc[STATUS_RED]:
        status = STATUS_RED
    elif rc[STATUS_UNJUDGED] or no_checks:
        status = STATUS_UNJUDGED
    elif rc[STATUS_WARN]:
        status = STATUS_WARN
    else:
        status = STATUS_PASS
    ok = OK_FROM_STATUS.get(status)
    recomputed = {"n_checks": len(norm), "n_pass": rc[STATUS_PASS], "n_warn": rc[STATUS_WARN],
                  "n_red": rc[STATUS_RED], "n_unjudged": rc[STATUS_UNJUDGED],
                  "verdict": ("RED" if rc[STATUS_RED] else
                              ("UNJUDGED_evidence_missing" if (rc[STATUS_UNJUDGED] or no_checks)
                               else ("WARN" if rc[STATUS_WARN] else "PASS")))}
    agrees = (s.get("n_checks") == len(norm) and s.get("n_pass") == rc[STATUS_PASS]
              and s.get("n_warn") == rc[STATUS_WARN] and s.get("n_red") == rc[STATUS_RED])
    obs = {"guard_build": (doc or {}).get("guard_build"),
           "guard_kind": (doc or {}).get("guard_kind"),
           "n_checks": recomputed["n_checks"], "n_pass": recomputed["n_pass"],
           "n_warn": recomputed["n_warn"], "n_red": recomputed["n_red"],
           "n_unjudged": recomputed["n_unjudged"], "verdict": recomputed["verdict"],
           "counts_recomputed_by_b2": True,
           "upstream_summary_verbatim": s,
           "upstream_summary_agrees_with_recompute": agrees,
           "summary_disagreement": (None if agrees else
                                    "上游 summary %r 与 B2 逐条复算 %r 不一致 ⇒ 以**逐条**为准"
                                    "（裁定 78.2：顶层布尔/汇总不得掩盖逐条事实）"
                                    % ({k: s.get(k) for k in ("n_checks", "n_pass", "n_warn", "n_red")},
                                       {k: recomputed[k] for k in
                                        ("n_checks", "n_pass", "n_warn", "n_red")}))
           ,
           "n_id_null_filled": sum(1 for x in norm if x["null_id"]),
           "n_id_whitespace_stripped": sum(1 for x in norm if x["ws_stripped"]),
           "n_status_outside_three_value_set": sum(1 for x in norm if x["outside"]),
           "per_check": {("%s[%s]" % (x["cid_base"], tag)): x["st"] for x in norm},
           "per_check_source_verbatim": {str(x["idx"]): {"check_id": x["cid_raw"],
                                                         "status": x["st_raw"]} for x in norm},
           "violations": [v for c in checks_in if isinstance(c.get("actual"), dict)
                          for v in (c["actual"].get("violations") or [])],
           "warnings": [w for c in checks_in if isinstance(c.get("actual"), dict)
                        for w in (c["actual"].get("warnings") or [])]}
    if no_checks:
        obs["violations"] = list(obs["violations"]) + [
            "上游产物里没有可转录的 checks[] ⇒ 无从判（不得读成 PASS）"]
    obs["transcription_polarity_fix"] = (
        "**裁定 78.5（极性修正）**：旧版把 guard 的 `red_when` 塞进了 `required` 槽 ⇒ 逐条读起来"
        "像「期望 = 重建目录**等于** 0928」，而实际期望恰恰相反，于是「期望已被满足"
        "（`same_as_0928=false`、`lock_diff` 已逐包枚举）」却报 WARN，看着像自相矛盾。"
        "现在 `required` = guard 的 `expected`（绿条件）、`red_when` = guard 的 `red_when`，"
        "各归各位；**guard 的 status 一个字都没改**（B2 只转录不重写，D→B2 §1.1）。")
    obs["id_normalization"] = (
        "**裁定 78.3**：逐条 id 去掉两个前导空格（旧版 `\"  G2_…[a2env]\"` 会让精确匹配/去重/"
        "建索引全漏；本轮实测：21:13 那份判词里 **10 条**转录 id 全带两个前导空格，"
        "现已 `.strip()` 并由 T7 钉住），且 `check_id` 缺失时**不留 null**"
        "（退化成 `G_index<i>[<tag>]` 并登记原值，由 T8 钉住）。"
        "同 tag 的多份历史产物另见 `normalized/NORMALIZATION_LEDGER.json`（id 带 `@scope` 全局唯一）。")
    rep.add("G1-G5_%s" % tag, ok, obs, req,
            note="逐条 G 见同目录 JSON；本闸只**转录**不重写（D→B2 §1.1）",
            status=status, ruling_ref=ref, red_when=red)
    for x in norm:
        c, st, st_raw = x["c"], x["st"], x["st_raw"]
        cid = "%s[%s]" % (x["cid_base"], tag)
        note_c = c.get("note") or ""
        if st == STATUS_WARN:
            note_c = ((note_c + " ｜ " if note_c else "") +
                      "**这条 WARN 的真实成因见 `observed.actual.warnings`**：它是 guard 对"
                      "「某个事实缺失」的登记（本轮 = A2 的重建目录只有 `requirements.lock.txt`、"
                      "**没有** `requirements.eval.lock.txt`，实测 `ls runs/vla/a2_env_pi05_sim_20260929/*.txt`），"
                      "**不是**对「重建目录 != 0928 / lock_diff 未枚举」的否定 —— 那两项 `actual` 里"
                      "都是满足的（`same_as_0928=false`、`lock_diff` 逐包在案）。裁定 78.5。")
        if x["outside"]:
            note_c = ((note_c + " ｜ " if note_c else "") +
                      "**上游把这条写成 %r（不在 PASS/WARN/RED 三值集内）⇒ B2 记 UNJUDGED**，"
                      "不猜它是通过还是违例（裁定 78.2：UNJUDGED 计入非绿）。" % (st_raw,))
        rep.add(cid, OK_FROM_STATUS.get(st),
                {"expected": c.get("expected"), "actual": c.get("actual"),
                 "transcribed_from_check_id": x["cid_raw"],
                 "id_had_surrounding_whitespace": x["ws_stripped"],
                 "id_was_null": x["null_id"],
                 "source_status_verbatim": st_raw,
                 "status_was_not_in_three_value_set": x["outside"]},
                c.get("expected") or "", note=note_c, status=st,
                ruling_ref=c.get("ruling_ref") or ref, red_when=c.get("red_when") or "")
    return obs

# ---------------------------------------------------------------------------
# 裁定 78.3：委托闸产物的**归一副本**（原件逐字节不动，另存 + 台账 + 机器断言）
# ---------------------------------------------------------------------------
def _guard_tag_of(path: Path) -> str:
    """`delegated_g1_g5_freeze.json` -> `freeze`（认不出的按文件名中段取，取不到给 `unknown`）。"""
    n = path.name
    if n.startswith("delegated_g1_g5_") and n.endswith(".json"):
        mid = n[len("delegated_g1_g5_"):-len(".json")]
        if mid:
            return mid
    return "unknown"


def _normalize_guard_doc(doc, tag: str, scope: str = "") -> dict:
    """把 B 的 guard 产物归一成裁定 78.2 的最小公共 check schema（`id/ok/status/required/observed/red_when`）。

    为什么要有这一层（裁定 78.3，D 点名"必做"）：B 的产物用 `check_id`、**没有** `id`
    ⇒ D 的执行单里那 45 条（a2env 4 份 ×5、freeze 5 份 ×5）全是 `id=null`，无法精确引用到条；
    而且 `"  G2_rebuild_lockout_not_default[a2env]"` 还带**两个前导空格**（三份产物一致）
    ⇒ 精确匹配 / 去重 / 建索引都会漏。B2 无权改 B 的脚本（只读复用，D→B2 §1.1），
    也**不得**就地改写 B 的产物（那是证据；改了就成了"引用失效"，本仓已栽过：裁定 78.11 / 89.7）
    ⇒ 只另存归一副本，并把「原件逐字节未动」做成机器断言（`normalize_all_guard_docs` 里
    写前写后各复算一次 sha256）。

    `scope` 用于区分同一 `tag` 的多份产物（当前轮 / `history/runX` / `replay_run2`）：
    不带 scope 时 id 形如 `G1_locks_0928_not_overwritten[freeze]`，
    带 scope 时形如 `G1_locks_0928_not_overwritten[freeze@history/run2_…]`
    ⇒ 9 份产物 ×5 条 = 45 个 id **全局唯一**，D 可以精确点到条。
    """
    checks_in = (doc or {}).get("checks") or []
    out_checks = []
    hist = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_RED: 0, STATUS_UNJUDGED: 0}
    n_null = n_stripped = n_bad_status = 0
    for idx, c in enumerate(checks_in):
        if not isinstance(c, dict):
            continue
        raw = c.get("check_id")
        if raw is None:
            raw = c.get("id")
        cid_base = str(raw).strip() if raw is not None else ""
        if raw is None or not cid_base:
            n_null += 1
            cid_base = "G_index%d" % idx          # **不留 null**（裁定 78.3）
        elif cid_base != str(raw):
            n_stripped += 1                        # 前导/尾随空格已去掉
        st_raw = c.get("status")
        in_set = st_raw in (STATUS_PASS, STATUS_WARN, STATUS_RED)
        st = st_raw if in_set else STATUS_UNJUDGED
        if not in_set:
            n_bad_status += 1
        hist[st] += 1
        out_checks.append({
            "id": ("%s[%s]" % (cid_base, tag)) if not scope else
                  ("%s[%s@%s]" % (cid_base, tag, scope)),
            "id_base": cid_base, "tag": tag, "scope": scope or None,
            "ok": OK_FROM_STATUS.get(st), "status": st,
            "ok_status_same_source": True, "ok_from_status": st,
            "counts_as_non_green": st in (STATUS_RED, STATUS_UNJUDGED),
            "required": c.get("expected"), "observed": c.get("actual"),
            "red_when": c.get("red_when") or "", "note": c.get("note") or "",
            "ruling_ref": c.get("ruling_ref") or "",
            "source_verbatim": {"check_id": c.get("check_id"), "status": st_raw},
            "id_was_null": (raw is None or not str(raw).strip()),
            "id_had_surrounding_whitespace": (raw is not None and cid_base != str(raw)),
            "status_was_not_in_three_value_set": (not in_set),
        })
    n_red, n_warn = hist[STATUS_RED], hist[STATUS_WARN]
    n_unj, n_pass = hist[STATUS_UNJUDGED], hist[STATUS_PASS]
    s_up = (doc or {}).get("summary") or {}
    verdict = ("RED" if n_red else
               ("UNJUDGED_evidence_missing" if n_unj else
                ("WARN" if n_warn else "PASS")))
    return {
        "artifact": "b2_normalized_delegated_guard_doc",
        "normalization_ruling": ("裁定 78.3（补 `id`、`id` 与 `ok` 同源、去前导空格、"
                                 "`check_id` 缺失不留 null）/ 裁定 78.2（最小公共 check schema + "
                                 "顶层四元组 + UNJUDGED 计入非绿）"),
        "generated_by": "scripts/b2_env_admission_pi05.py:_normalize_guard_doc（B2 数据与判据线）",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tag": tag, "scope": scope or None,
        "upstream": {"guard_kind": (doc or {}).get("guard_kind"),
                     "guard_build": (doc or {}).get("guard_build"),
                     "generated_at": (doc or {}).get("generated_at"),
                     "generated_by": (doc or {}).get("generated_by"),
                     "rebuild_dir": (doc or {}).get("rebuild_dir"),
                     "venv": (doc or {}).get("venv")},
        "checks": out_checks,
        "n_checks": len(out_checks), "n_pass": n_pass, "n_warn": n_warn,
        "n_red": n_red, "n_unjudged": n_unj,
        # RR-B2-09 改判（裁定 93 / D→B2 §四-1）：与顶层 `ok` **调同一个 `ok_of()`**。
        # 裁定 78.2 的最小公共 check schema 是 B2 自己定的口径 ⇒ 归一副本与本闸顶层两处 `ok`
        # 若各写一份，就是"判据与散文不同源"（裁定 27 / 35.3 / 37.4）。WARN 仍登记在
        # `n_warn` 与下面的 `verdict` 四值标签里（登记义务不因改判而消失）。
        "ok": ok_of(n_red, n_unj, n_warn),
        "ok_criterion": OK_CRITERION,
        "verdict": verdict,
        "summary_recomputed_by_b2": True,
        "upstream_summary_verbatim": s_up,
        "upstream_summary_agrees": (s_up.get("n_checks") == len(out_checks)
                                    and s_up.get("n_pass") == n_pass
                                    and s_up.get("n_warn") == n_warn
                                    and s_up.get("n_red") == n_red),
        "id_fixes": {"n_id_null_filled": n_null, "n_id_whitespace_stripped": n_stripped,
                     "n_status_outside_three_value_set": n_bad_status},
        "ids": [c["id"] for c in out_checks],
        "original_modified_by_normalization": False,
    }


def _find_p_type_f(root: Path, name_glob: str, exclude_path_glob: str = "",
                   exclude_names=(), include_path_glob: str = "", maxdepth: int = 0) -> dict:
    """裁定 92.3-ii 的**对账基数**：不跟随符号链接的 `find -P -type f -name <glob> | wc -l`。

    为什么不用 `Path.rglob`（本函数上面的 `srcs` 就是用它扫的）：E 本轮的真实缺陷之一正是
    **`rglob` 跟随符号链接 ⇒ 清单越界**（裁定 92.5，代码缺陷 +3 的一条）。D 因此补了一句：
    「(ii) 的对账基数必须用不跟随符号链接的 `find -type f`，否则对账本身会被同一类问题骗过」。
    ⇒ 这里刻意用**另一套实现**（外部 `find -P`）去核对 `rglob` 的结果：两套独立实现对同一
    命题给同一个数，才叫对账；用同一个函数自己核自己等于没核（ADR-C-014 同型）。
    返回 `{"command":…, "n":…, "rc":…, "error":…}`；`n = -1` 表示**没测到**（不得当 0 用）。
    """
    cmd = ["find", "-P", str(root), "-type", "f", "-name", name_glob]
    if maxdepth:
        # `-maxdepth` 必须紧跟起点（GNU find 会警告它出现在其它测试之后的情形）
        cmd = ["find", "-P", str(root), "-maxdepth", str(maxdepth), "-type", "f",
               "-name", name_glob]
    if exclude_path_glob:
        cmd += ["-not", "-path", exclude_path_glob]
    if include_path_glob:
        cmd += ["-path", include_path_glob]
    for xn in exclude_names:
        cmd += ["-not", "-name", xn]
    out = {"command": " ".join(cmd) + " | wc -l", "n": -1, "rc": None, "error": None}
    if not root.exists():
        out["error"] = "root 不存在：%s（⇒ 没测到，不是 0）" % root
        return out
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:                                    # noqa: BLE001
        out["error"] = "%s: %s" % (type(e).__name__, e)
        return out
    out["rc"] = p.returncode
    if p.returncode != 0:
        out["error"] = "find rc=%s stderr=%s" % (p.returncode, (p.stderr or "")[:200])
        return out
    out["n"] = len([ln for ln in p.stdout.splitlines() if ln.strip()])
    return out


def normalize_all_guard_docs(out_dir: Path, rep, extra_roots=None):
    """对**全部 B2 准入 out_dir**（当轮 + 历史轮，含各自的 `history/`、`replay_run2/` 子目录）下的
    `delegated_g1_g5_*.json` 落归一副本 + 一份台账，并把「原件逐字节未动」做成机器断言（裁定 78.3）。

    **为什么必须跨轮扫（本轮正式判定实测逼出来的）**：D 数的是 **45 条 `id=null`
    （a2env 4 份 ×5、freeze 5 份 ×5）**，而那 9 份**全在 `runs/vla/b2_env_admission_20260929/` 下**。
    第一版只扫当天 out_dir ⇒ 20260930 那轮实测只归到 **3 份 / 10 条**，其中 1 份还是被 glob
    **误吞**的 B2 自己的 `delegated_g1_g5_upstream_teeth.json`（它名字前缀相同、但没有 `checks[]`）
    ⇒ 台账里写着"扫到 3 份 / 10 条"，与 D 的 45 条**对不上账**。
    那不是"D 数错了"，是**扫描作用域错了**（同族：裁定 90.5 #16「用一个看起来能用的间接量，
    替代那个真正要指的东西」—— 这里是用「当天目录」替代「D 点名的那 9 份」）。
    ⇒ 现在 `extra_roots` 由 `main()` 自动发现（`runs/vla/b2_env_admission_*` 的全部兄弟目录），
    副本按 `normalized/<源 out_dir 名>/<rel>` 落（布局版本见常量
    `NORMALIZED_LAYOUT_VERSION`，现值 2），原件**一字节不动**。
    """
    req = ("**全部** B2 准入 out_dir（当轮 + 历史轮）下的 `delegated_g1_g5_*.json` 都有归一副本"
           "（`id` 非空且全局唯一、`ok` 与 `status` 同源、前导空格已去）；且**原件逐字节未动**"
           "（写前/写后各复算一次 sha256）；且台账与不跟随符号链接的 `find -P -type f | wc -l` "
           "对账成立（裁定 92.3-ii）")
    red = ("任一原件的 sha256 在归一前后不同（= B2 改写了 B 的证据）；或归一副本里出现 "
           "`id` 为空 / id 重复；或某份产物解析失败；或清单对账的差值解释不了")
    ref = "裁定 78.3（委托闸补 id）/ 裁定 78.2（最小公共 schema）/ 裁定 89.7（before 影像纪律）"
    norm_root = out_dir / "normalized"
    roots = [out_dir] + [Path(r) for r in (extra_roots or []) if Path(r) != out_dir]
    srcs = []                                     # [(源 root, 原件 path)]
    for r in roots:
        if not r.exists():
            continue
        for p in sorted(r.rglob(GUARD_DOC_GLOB)):
            if not p.is_file() or p.name in GUARD_DOC_EXCLUDE_NAMES:
                continue                          # 排除 B2 自己的 teeth 产物（见常量注释）
            rel = p.relative_to(r)
            if rel.parts and rel.parts[0] == "normalized":
                continue                          # 不归一自己的副本（否则每跑一次翻一倍）
            if any(pt.startswith("_superseded_layout") for pt in rel.parts):
                continue                          # 也不归一上一版布局留下的旧副本
            srcs.append((r, p))
    # ---- 布局 v1 → v2：旧副本**移进**旁证目录（不删、不改名，裁定 92.4 的同族做法）----
    superseded = []
    if norm_root.exists():
        old = sorted(norm_root.glob("*.normalized.json"))
        if old:
            d = norm_root / ("_superseded_layout1_%d" % int(time.time()))
            d.mkdir(parents=True, exist_ok=True)
            for p in old:
                shutil.move(str(p), str(d / p.name))
                superseded.append(str((d / p.name).relative_to(out_dir)))
    if not srcs:
        rep.add("A3_delegated_docs_normalized", None,
                "扫过的 %d 个 out_dir（%s）下没有任何 `%s`（--no-delegate？或委派失败）"
                % (len(roots), [r.name for r in roots], GUARD_DOC_GLOB),
                req, note="没有可归一的产物 ⇒ 弃权（**不是**「没有 id=null 问题」）",
                ruling_ref=ref, red_when=red)
        return {"n_source_docs": 0, "source_roots": [str(r) for r in roots]}
    ledger, bad, all_ids = [], [], []
    for src_root, p in srcs:
        rel = p.relative_to(src_root)
        # scope 里**带上源 out_dir 名**：跨轮扫描后，同一个 `history/run2_…` 相对路径可能出现在
        # 两个不同的轮次目录里 ⇒ 不带轮次名的话 id 会撞（`ids_globally_unique` 会假报重复）。
        scope_parts = [src_root.name]
        if str(rel.parent) != ".":
            scope_parts.append(str(rel.parent))
        scope = "/".join(scope_parts)
        tag = _guard_tag_of(p)
        before = _sha256_file(p)
        st = p.stat()
        try:
            doc = json.loads(p.read_text(errors="replace"))
        except Exception as e:
            bad.append("`%s` 解析失败（%s: %s）⇒ 这份产物的 check 无从归一"
                       % (rel, type(e).__name__, e))
            ledger.append({"source": str(rel), "source_root": src_root.name,
                           "source_path": str(p), "parsed": False,
                           "sha256_12_before": (before or {}).get("sha256", "")[:12]})
            continue
        nd = _normalize_guard_doc(doc, tag, scope)
        nd["source"] = {"path": str(p), "rel": str(rel), "source_root": src_root.name,
                        "sha256": before["sha256"], "sha256_12": before["sha256"][:12],
                        "bytes": before["bytes"],
                        "mtime_iso": datetime.fromtimestamp(st.st_mtime).astimezone()
                        .isoformat(timespec="seconds")}
        dst = norm_root / src_root.name / rel.parent / (rel.stem + ".normalized.json")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(nd, indent=1, ensure_ascii=False) + "\n")
        after = _sha256_file(p)
        untouched = bool(after and before and after["sha256"] == before["sha256"]
                         and after["bytes"] == before["bytes"])
        if not untouched:
            bad.append("**原件被改动**：`%s`（before %s / after %s）⇒ B2 改写了 B 的证据，"
                       "归一副本随之失效" % (rel, (before or {}).get("sha256", "")[:12],
                                             (after or {}).get("sha256", "")[:12]))
        dup = [i for i in nd["ids"] if i in all_ids]
        if dup:
            bad.append("归一 id 重复：%s（`%s`）⇒ D 仍无法精确点到条" % (dup[:3], rel))
        empty = [c["id_base"] for c in nd["checks"] if not c["id_base"]]
        if empty:
            bad.append("归一后仍有空 id：%s（`%s`）" % (empty[:3], rel))
        all_ids.extend(nd["ids"])
        ledger.append({
            "source": str(rel), "source_root": src_root.name, "source_path": str(p),
            "parsed": True, "tag": tag, "scope": scope or None,
            "normalized": str(dst.relative_to(out_dir)),
            "sha256_12_before": before["sha256"][:12], "sha256_12_after": after["sha256"][:12],
            "bytes_before": before["bytes"], "bytes_after": after["bytes"],
            "original_untouched": untouched,
            "n_checks": nd["n_checks"], "n_pass": nd["n_pass"], "n_warn": nd["n_warn"],
            "n_red": nd["n_red"], "n_unjudged": nd["n_unjudged"],
            "upstream_summary_agrees": nd["upstream_summary_agrees"],
            "id_fixes": nd["id_fixes"], "ids": nd["ids"],
        })

    # ---- 裁定 92.3-ii：本台账是一件**清单/索引件** ⇒ 必须与不跟随符号链接的
    #      `find -P -type f | wc -l` 对一次行数，且差值必须能被解释。
    #      三个数各自独立：① 全目录命中（含归一副本）② 排除 `normalized/` 的源件
    #      ③ 归一副本本身。恒等式必须是 ①-② == ③ == 台账登记的成功归一份数，
    #      且 ② == `rglob` 扫到的 `len(srcs)`（两套实现互核，见 `_find_p_type_f` 的注释）。
    n_norm_expected = sum(1 for x in ledger if x.get("parsed"))
    fc_reasons = []
    # 逐个源 out_dir 各对一次账（跨轮扫描后，"一个总数"会把某一轮的漏扫藏进另一轮的富余里）。
    fc_per_root, fc_src_total = [], 0
    for r in roots:
        if not r.exists():
            continue
        f = _find_p_type_f(r, GUARD_DOC_GLOB, "*/normalized/*", GUARD_DOC_EXCLUDE_NAMES)
        n_rglob = sum(1 for (rr, _) in srcs if rr == r)
        agrees = (f["n"] == n_rglob)
        fc_per_root.append({"root_name": r.name, "root": str(r), "find": f,
                            "n_by_rglob": n_rglob, "agrees": agrees})
        if f["n"] < 0:
            fc_reasons.append("`find -P` 在 `%s` 上**没测到**（error=%s）⇒ 不得当 0 读，"
                              "这一轮的对账弃权" % (r, f["error"]))
        else:
            fc_src_total += f["n"]
            if not agrees:
                fc_reasons.append("`%s`：`find -P`（排除 `normalized/` 与 B2 自己的 teeth 产物）= %d "
                                  "与 `rglob` = %d 不符 ⇒ 两套独立实现对同一命题给了不同的数"
                                  "（符号链接 / 权限 / 竞态三者之一，必须查清，不得取其一）"
                                  % (r.name, f["n"], n_rglob))
    fc_norm = _find_p_type_f(norm_root, "*.normalized.json", "*/_superseded_layout*/*")
    fc_norm_all = _find_p_type_f(norm_root, "*.normalized.json")
    fc_sup = _find_p_type_f(norm_root, "*.normalized.json", "", (),
                            include_path_glob="*/_superseded_layout*/*")
    fc_top = _find_p_type_f(norm_root, "*.normalized.json", "", (), maxdepth=1)
    n_moved = len(superseded)
    if fc_norm["n"] < 0:
        fc_reasons.append("`find -P` 在 `normalized/` 上**没测到**（error=%s）⇒ 不得当 0 读"
                          % fc_norm["error"])
    else:
        if fc_norm["n"] != n_norm_expected:
            fc_reasons.append("归一副本实测 %d 份与台账登记 %d 份不符 ⇒ 台账漏登或多登"
                              "（E 的近失同型：清单漏登产物本体）"
                              % (fc_norm["n"], n_norm_expected))
        # ---- 旧副本（布局 v1）的差值必须**被解释**，不是被"本轮移入数"对上 ----
        # 第一版这里写的是 `全部副本 - 有效副本 == 本轮移入数`，**口径错了**：
        # `_superseded_layout1_<epoch>/` 会**跨轮累积**（每一轮布局变更各留一个目录），
        # 而"本轮移入数"只是当轮的量 ⇒ 第二轮必然对不上（本轮正式判定实测差 3、移入 0 ⇒ 假红）。
        # 这与 D 的第 16 号同型错误同根：拿一个"看起来能用"的量（本轮移入数）去替代
        # 真正要指的那个量（盘上现存的旧副本数）。现在换成三条**可核**的不变式：
        n_sup_on_disk = (fc_sup["n"] if fc_sup["n"] >= 0 else None)
        if n_sup_on_disk is None:
            fc_reasons.append("`find -P`（只数 `_superseded_layout*/` 下的副本）**没测到**"
                              "（error=%s）⇒ 差值无从解释，不得当 0 读" % fc_sup["error"])
        else:
            # (ii-a) 布局 v2 的硬不变式：`normalized/` **顶层**不许再有任何副本
            #        （v2 一律落在 `<源 out_dir 名>/…` 下）。这一条是真的会失败的：
            #        只要移动步骤漏了一个文件，它就非 0。
            if fc_top["n"] != 0:
                fc_reasons.append("布局 v%d 的硬不变式被破坏：`normalized/` **顶层**还有 %d 份副本"
                                  "（v2 一律落在 `<源 out_dir 名>/…` 下）⇒ 移动步骤漏了文件"
                                  % (NORMALIZED_LAYOUT_VERSION, fc_top["n"]))
            # (ii-b) 分区恒等式：全部 = 有效 + 旧副本（作为**解释**登记，不作为唯一证明；
            #        真正的证明是 (i) 台账对磁盘 与 (ii-a) 顶层为空）
            if fc_norm_all["n"] >= 0 and fc_norm_all["n"] != fc_norm["n"] + n_sup_on_disk:
                fc_reasons.append("分区不成立：全部副本 %d != 有效 %d + 旧副本 %d ⇒ `normalized/` 里"
                                  "有既不在有效集、也不在 `_superseded_layout*/` 下的命中件，必须点名"
                                  % (fc_norm_all["n"], fc_norm["n"], n_sup_on_disk))
            # (ii-c) 本轮移入的必须都在盘上、且不超过现存旧副本总数
            if n_moved > n_sup_on_disk:
                fc_reasons.append("本轮声称移入 %d 份，但盘上只有 %d 份旧副本 ⇒ 移入记录与磁盘不符"
                                  % (n_moved, n_sup_on_disk))
            missing_moved = [s for s in superseded if not (out_dir / s).is_file()]
            if missing_moved:
                fc_reasons.append("本轮登记移入的副本在盘上找不到：%s" % missing_moved[:3])
    fc_reconciled = (not fc_reasons)
    if not fc_reconciled:
        bad.extend(["**清单对账不成立**（裁定 92.3-ii）：%s" % r for r in fc_reasons])
    crosscheck = {
        "ruling": "裁定 92.3-ii（清单/索引件必须与不跟随符号链接的 `find -type f | wc -l` 对行数，"
                  "差值必须可解释；D 补：对账基数**不得**用会跟随符号链接的 `rglob`）",
        "n_source_docs_by_rglob": len(srcs),
        "n_source_docs_by_find_total": fc_src_total,
        "source_roots": [{"root_name": r.name, "root": str(r), "exists": r.exists()}
                         for r in roots],
        "per_root": fc_per_root,
        "n_normalized_by_ledger": n_norm_expected,
        "find_normalized_copies_excluding_superseded": fc_norm,
        "find_normalized_copies_including_superseded": fc_norm_all,
        "find_normalized_copies_only_superseded": fc_sup,
        "find_normalized_copies_at_top_level": fc_top,
        "n_superseded_on_disk": (fc_sup["n"] if fc_sup["n"] >= 0 else None),
        "n_superseded_moved_this_round": n_moved,
        "superseded_layout1_moved_to": superseded,
        "invariants": [
            "(i) 逐轮：find(源件, 排除 normalized/ 与 B2 自己的 teeth 产物) == rglob 的份数",
            "(ii) find(归一副本, 排除 _superseded_layout*/) == 台账登记的成功归一份数",
            "(iii) `normalized/` **顶层**的副本数 == 0（布局 v2 的硬不变式；v1 的旧副本必须已被移走）",
            "(iv) find(全部副本) == find(有效副本) + find(旧副本)（分区，作为差值的**解释**登记）",
            "(v) 本轮移入数 <= 盘上现存旧副本数，且每个移入路径都在盘上",
        ],
        "caliber_note": ("`_superseded_layout1_<epoch>/` **跨轮累积** ⇒ 「盘上现存旧副本数」与"
                         "「本轮移入数」是两个不同的量，不得互相对账（本闸第一版就写错了这一对，"
                         "在第二轮正式判定里造出一条假红）"),
        "identity_holds": fc_reconciled,
        "unexplained_differences": fc_reasons,
        "why_it_matters": "台账是 D 用来核「45 条 id=null 都修到了没有」的索引件；索引件自己漏登/"
                          "越界的话，下游会把「没扫到」读成「没有问题」（三值纪律的反面）。",
    }
    # ---- 与 D 的计数**对账**（不是只把自己的数写上去就完事）----
    # 第一版就是栽在这里：台账写着"扫到 3 份 / 10 条"，而 D 数的是 9 份 / 45 条，
    # 两个数并排放着却没有人对它们做差 ⇒ 读者要么以为 D 数错、要么以为 B2 修完了。
    # 裁定 92.3-ii 的实质就是这一句：**差值必须能被解释**。
    n_docs_d_scope = sum(1 for x in ledger if x.get("source_root") == D_FINDING_SCOPE_DIR)
    n_checks_d_scope = sum(x.get("n_checks") or 0 for x in ledger
                           if x.get("source_root") == D_FINDING_SCOPE_DIR)
    # **三值**：D 点名的作用域**没被扫**（例如 `--no-normalize-siblings`、或合成世界）时，
    # 对账的正确状态是**无从判**，不是"不成立"。第一版把它写成 `matches_d_count=False ⇒ 判红`，
    # 那会在任何不含 20260929 目录的 out_dir 上造假红（本仓第 8 起同型的镜像：把"没测到"
    # 读成"不合格"）。⇒ `matches_d_count` 取 True / False / None 三值，None 不进 violations。
    d_scope_scanned = any(r.name == D_FINDING_SCOPE_DIR for r in roots if r.exists())
    matches = (None if not d_scope_scanned else
               (n_docs_d_scope == D_FINDING_N_DOCS and n_checks_d_scope == D_FINDING_N_CHECKS))
    d_recon = {
        "d_counted": {"n_docs": D_FINDING_N_DOCS, "n_checks": D_FINDING_N_CHECKS,
                      "breakdown": "a2env 4 份 ×5 + freeze 5 份 ×5",
                      "scope": "runs/vla/%s/（含 history/ 与 replay_run2/）" % D_FINDING_SCOPE_DIR,
                      "source": "裁定 78.3 / D→B2 §15-5 item 3"},
        "d_scope_scanned_this_round": d_scope_scanned,
        "b2_scanned_from_that_scope": {"n_docs": n_docs_d_scope, "n_checks": n_checks_d_scope},
        "b2_scanned_all_roots": {"n_docs": len(srcs),
                                 "n_checks": sum(x.get("n_checks") or 0 for x in ledger)},
        "matches_d_count": matches,
        "matches_d_count_caliber": ("True/False = 作用域被扫过、计数可对；"
                                    "**None = 本轮没有扫 D 点名的作用域 ⇒ 无从对账**"
                                    "（三值纪律：不得把「没测到」读成「不合格」，也不得读成「合格」）"),
        "difference_explanation": (
            ("无差值：D 数的 %d 份 / %d 条已全部扫到并归一（另外还多扫了当轮新产的产物）"
             % (D_FINDING_N_DOCS, D_FINDING_N_CHECKS)) if matches is True else
            ("**本轮没有扫 `%s`**（扫过的是 %s）⇒ 与 D 的 45 条**无从对账**，按三值纪律记 None，"
             "**不判成立也不判不成立**。若要对账，去掉 `--no-normalize-siblings` 重跑"
             % (D_FINDING_SCOPE_DIR, [r.name for r in roots])) if matches is None else
            ("**有差值且解释不了**：D 数 %d 份 / %d 条，B2 在 `%s` 下只扫到 %d 份 / %d 条 "
             "⇒ 要么 D 的作用域与 B2 的不同（必须点名差在哪几份），要么 B2 漏扫。"
             "**不得**把这个差值悄悄留着"
             % (D_FINDING_N_DOCS, D_FINDING_N_CHECKS, D_FINDING_SCOPE_DIR,
                n_docs_d_scope, n_checks_d_scope))),
    }
    if d_recon["matches_d_count"] is False:
        bad.append("与 D 的计数对不上账（裁定 78.3 / 92.3-ii）：%s"
                   % d_recon["difference_explanation"])
    tally = {
        "artifact": "b2_delegated_guard_doc_normalization_ledger",
        "ruling": "裁定 78.3 / 78.2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "scripts/b2_env_admission_pi05.py:normalize_all_guard_docs",
        "out_dir": str(out_dir),
        "n_source_docs": len(srcs), "n_normalized": sum(1 for x in ledger if x.get("parsed")),
        "n_parse_failed": sum(1 for x in ledger if not x.get("parsed")),
        "n_checks_total": sum(x.get("n_checks") or 0 for x in ledger),
        "n_id_null_filled": sum((x.get("id_fixes") or {}).get("n_id_null_filled") or 0
                                for x in ledger),
        "n_id_whitespace_stripped": sum(
            (x.get("id_fixes") or {}).get("n_id_whitespace_stripped") or 0 for x in ledger),
        "n_ids": len(all_ids), "n_unique_ids": len(set(all_ids)),
        "ids_globally_unique": len(all_ids) == len(set(all_ids)),
        "originals_all_untouched": all(x.get("original_untouched")
                                       for x in ledger if x.get("parsed")),
        "layout_version": NORMALIZED_LAYOUT_VERSION,
        "source_roots": [{"root_name": r.name, "root": str(r), "exists": r.exists(),
                          "n_docs": sum(1 for (rr, _) in srcs if rr == r)} for r in roots],
        "d_finding_addressed": ("D 在裁定 78.3 点名的「45 条 check `id=null`（a2env 4 份 ×5、"
                                "freeze 5 份 ×5）」：本轮实际扫到 %d 份 / %d 条，逐份见 `docs[]`"
                                % (len(srcs), sum(x.get("n_checks") or 0 for x in ledger))),
        "d_finding_reconciliation": d_recon,
        "docs": ledger,
        "crosscheck_find_type_f": crosscheck,
    }
    norm_root.mkdir(parents=True, exist_ok=True)
    (norm_root / "NORMALIZATION_LEDGER.json").write_text(
        json.dumps(tally, indent=1, ensure_ascii=False) + "\n")
    obs = {"violations": bad, "n_source_docs": len(srcs),
           "n_checks_total": tally["n_checks_total"],
           "source_roots": tally["source_roots"],
           "d_finding_reconciliation": d_recon,
           "n_id_null_filled": tally["n_id_null_filled"],
           "n_id_whitespace_stripped": tally["n_id_whitespace_stripped"],
           "n_ids": tally["n_ids"], "ids_globally_unique": tally["ids_globally_unique"],
           "originals_all_untouched": tally["originals_all_untouched"],
            "ledger": str(norm_root / "NORMALIZATION_LEDGER.json"),
            "normalized_dir": str(norm_root),
            "sources": [{"source_root": r.name, "rel": str(p.relative_to(r)), "path": str(p)}
                        for r, p in srcs],
            "crosscheck_find_type_f": {k: crosscheck[k] for k in
                                       ("identity_holds", "unexplained_differences",
                                        "n_source_docs_by_rglob", "n_normalized_by_ledger")},
            "crosscheck_commands": ([x["find"]["command"] for x in fc_per_root]
                                    + [fc_norm["command"], fc_norm_all["command"]])}
    rep.add("A3_delegated_docs_normalized", not bad, obs, req,
            note=("原件逐字节不动、副本另存（布局 v%d）；id 全局唯一 ⇒ D 的执行单可以精确点到条"
                  "（裁定 78.3）。**跨轮扫** %d 个 out_dir（%s）；与 D 在裁定 78.3 点的计数对账："
                  "%s（`matches_d_count` 三值：%s）"
                  % (NORMALIZED_LAYOUT_VERSION, len(roots), [r.name for r in roots],
                     d_recon["difference_explanation"], d_recon["matches_d_count"])),
            ruling_ref=ref, red_when=red)
    return tally


# ---------------------------------------------------------------------------
# 裁定 78.4 的①：委托闸（freeze 模式）补牙 —— **亲自复跑**上游变异自检，不转述散文
# ---------------------------------------------------------------------------
def _parse_guard_selftest_stdout(text: str) -> dict:
    """解析 B 的 `--selftest` 表格输出，算出**每个 G 有没有「能红」的变异体**。

    为什么要解析而不是采信 rc：rc=0 只说明"上游自己认为全过"，而裁定 78.4 要的是
    「≥1 个反向变异体/G（证明能红）」—— 那是**逐 G 的覆盖**问题，rc 里没有这个维度。
    解析器本身有牙：`--selftest` 的 T10/T11 分别喂"全抓住"与"G4 漏抓"的合成 stdout，
    要求 `every_g_has_a_caught_red_mutant` 一个 True 一个 False（防恒真）。
    """
    rows = []
    baseline_rows = []
    per_g = {g: {"n_mutants": 0, "red_expected": 0, "red_caught": 0,
                 "reverse_expected": 0, "reverse_ok": 0, "ids": []}
             for g in GUARD_G_EXPECTED}
    for line in (text or "").splitlines():
        stripped = line.strip()
        m = GUARD_SELFTEST_ROW_RE.match(stripped)
        if not m:
            mb = GUARD_SELFTEST_BASELINE_RE.match(stripped)
            if mb and "baseline_all_green" in stripped:
                baseline_rows.append({"want": mb.group(1), "got": mb.group(2),
                                      "desc": mb.group(3),
                                      "all_green": (mb.group(1) == mb.group(2) == "GREEN")})
            continue
        mid, g_want, s_want, g_got, s_got, desc, verdict = m.groups()
        rows.append({"id": mid, "target_g": g_want, "want": s_want, "got_g": g_got,
                     "got": s_got, "desc": desc, "verdict": verdict,
                     "caught": (s_got == s_want) if s_want == "RED" else (s_got != "RED")})
        d = per_g.get(g_want)
        if d is None:
            d = per_g.setdefault(g_want, {"n_mutants": 0, "red_expected": 0, "red_caught": 0,
                                          "reverse_expected": 0, "reverse_ok": 0, "ids": []})
        d["n_mutants"] += 1
        d["ids"].append(mid)
        if s_want == "RED":
            d["red_expected"] += 1
            if s_got == "RED":
                d["red_caught"] += 1
        else:
            d["reverse_expected"] += 1
            if s_got != "RED":
                d["reverse_ok"] += 1
    msum = GUARD_SELFTEST_SUM_RE.search(text or "")
    n_ok = int(msum.group(1)) if msum else None
    n_res = int(msum.group(2)) if msum else None
    # ---- 裁定 92.3-ii：`n_results`（上游自己的 12）与 B2 解析出的**变异行**数（11）
    #      差 1 ⇒ 差值必须能被解释，不许留给读者去猜「是不是漏解析了一行」。
    n_base = len(baseline_rows)
    diff_explained = (n_res is None) or (n_res == len(rows) + n_base)
    caliber = {
        "n_results_from_upstream_summary": n_res,
        "n_mutation_rows_parsed_by_b2": len(rows),
        "n_baseline_rows_parsed_by_b2": n_base,
        "identity": "上游 n_results == B2 解析的变异行数 + baseline 行数",
        "difference_explained": diff_explained,
        "note": ("上游的 `n_results` 把它的 **baseline 行**（`-  GREEN  GREEN  "
                 "baseline_all_green（…）`）也计入，而那一行没有 `M\\d+` id、也没有 G 目标 "
                 "⇒ B2 的**变异行**解析数比它少 1，差值就是那一行，**不是漏解析**。"
                 "本块把两侧计数与恒等式一起落盘（裁定 92.3-ii：清单/计数件的对账差值必须可解释）"),
        "unexplained_difference": (None if diff_explained else
                                   "上游自称 %r 条，B2 只解析出 %d 条变异行 + %d 条 baseline 行"
                                   "（合计 %d）⇒ 差 %r 条无从归因，**不得**当成「解析口径不同」放过"
                                   % (n_res, len(rows), n_base, len(rows) + n_base,
                                      (n_res or 0) - len(rows) - n_base)),
    }
    return {"n_rows_parsed": len(rows), "rows": rows, "per_g": per_g,
            "g_covered": sorted(g for g in per_g if per_g[g]["n_mutants"]),
            "n_ok": n_ok, "n_results": n_res,
            "n_rows_parsed_caliber": caliber,
            "upstream_baseline_rows": baseline_rows,
            "upstream_baseline_all_green": (baseline_rows[0]["all_green"] if baseline_rows
                                            else None),
            "upstream_all_caught": (n_ok is not None and n_ok == n_res),
            "every_g_has_a_caught_red_mutant": all(
                per_g.get(g, {}).get("red_caught", 0) >= 1 for g in GUARD_G_EXPECTED),
            "per_g_caught_red_mutants": {g: per_g.get(g, {}).get("red_caught", 0)
                                         for g in GUARD_G_EXPECTED}}


def _upstream_guard_teeth(root: Path, py: str, out_dir: Path) -> dict:
    """**亲自跑**上游 `scripts/b_env_provenance_guard.py --selftest`（只读复用，不改它一行），
    把它的 12 条变异（含 2 条反向）逐条变成 B2 的机器证据（裁定 78.4 的①）。

    与 `delegated_v0_v9` 的 `teeth_delegated_to_upstream` 的差别：那一处 B2 只**转述** B 的
    台账（`V3: n_mutations=15 / n_caught=15`）⇒ D 判定"不得当独立闸引用"；这一处 B2
    **本轮真跑**了上游自检、逐行解析、逐 G 统计覆盖 ⇒ 证据是 B2 自己产的
    （rc + 解析结果 + stdout 全文落盘），不是转述。
    """
    script = root / "scripts/b_env_provenance_guard.py"
    out = {"script": str(script), "exists": script.exists(),
           "read_only_reuse": True, "modified_by_b2": False}
    if not script.exists():
        out.update({"ran": False, "why_not_ran": "上游脚本不存在 ⇒ 无从复跑"})
        return out
    out["script_sha256_12"] = _sha12(script)
    try:
        out["script_lines"] = sum(1 for _ in script.open(errors="replace"))
    except Exception:
        out["script_lines"] = None
    r = _run([py, str(script), "--selftest"], timeout=1800)
    log = out_dir / "delegated_g1_g5_upstream_teeth.log"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        log.write_text("CMD: %s\nRC: %s\n--- stdout ---\n%s\n--- stderr ---\n%s\n"
                       % (" ".join(r["cmd"]), r["rc"], r["stdout"], r["stderr"]))
    except Exception:
        log = None
    parsed = _parse_guard_selftest_stdout(r["stdout"])
    out.update({"ran": True, "rc": r["rc"], "log": str(log) if log else None,
                "stderr_tail": (r["stderr"] or "")[-400:],
                "all_caught": bool(parsed["upstream_all_caught"] and r["rc"] == 0),
                "teeth_artifact": str(out_dir / "delegated_g1_g5_upstream_teeth.json")})
    out.update(parsed)
    try:
        (out_dir / "delegated_g1_g5_upstream_teeth.json").write_text(
            json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return out


def delegate_g1_g5(ev, rep, root: Path, a2_dir: Path, venv: str, out_dir: Path, py: str,
                   run_it=True):
    """委派 B 的 G1–G5，**分两个模式**（这是本闸的一处设计裁定，理由写在 obs 里）：

    模式 `freeze`：B 的默认调用（`--venv /root/venvs/rlrobot`、`--rebuild-dir` A 的 0929 重建目录）。
        它判的是**冻结面此刻是否完好**（0928 两份 lock 未被覆写、persistent pin 合规、
        base python 断言、numpy 遮蔽生效）—— 与 A2 交不交件**无关**，所以**总是可判**。
    模式 `a2env`：`--rebuild-dir <A2 目录> --venv <π₀.₅ venv> --expect-numpy <A2 lock 的 numpy pin>`。
        它判的是 A2 那套新环境，并顺带让 G2 **枚举**新旧 lock 的逐包差异（裁定 32.4：
        解释义务在 A2，B2 只保证差异不被吞掉）。
        **仅当 A2 交件齐且 venv 存在时才调用**：对不存在的 venv，G4/G5 会判 RED/WARN，
        那是把「还没建」误读成「建坏了」—— 本仓第 8 起同型的**假红**，必须避开。
        证据不足 ⇒ 弃权（UNJUDGED），而**不是** RED、更不是 PASS。
    """
    ref = "D→B2 §1.1（直接复用 B 已验收的闸，不要另写一套）/ 裁定 32.3 前提 1/2 / 裁定 32.4"
    req = ("freeze 模式：G1–G5 全过（冻结面完好）；a2env 模式：G1–G5 全过，且 G5 的生效 numpy "
           "期望值按 **A2 自己那份 lock** 推导（不用项目口径常量）")
    red = "任一 G 判 RED；或委派进程跑不起来（rc != 0 且无 JSON 产物）"
    if not run_it:
        rep.add("G1-G5_freeze", None, "--no-delegate：未调用 B 的溯源闸", req,
                note="缺委派 ⇒ 准入不得给 PASS", ruling_ref=ref, red_when=red)
        rep.add("G1-G5_a2env", None, "--no-delegate：未调用 B 的溯源闸", req,
                note="缺委派 ⇒ 准入不得给 PASS", ruling_ref=ref, red_when=red)
        return None

    doc_f, _ = _guard_once(root, py, out_dir / "delegated_g1_g5_freeze.json")
    if doc_f is None:
        rep.add("G1-G5_freeze", False, "委派失败：%s 不可解析" % "delegated_g1_g5_freeze.json",
                req, note="判据装置自己跑不起来时，不得读成「没有违例」",
                ruling_ref=ref, red_when=red)
    else:
        obs_f = _transcribe_guard(rep, doc_f, "freeze", ref, req, red)
        # ---- 裁定 78.4：`delegated_g1_g5_freeze` 二选一 ⇒ B2 采**①补牙**，不采②降级 ----
        # D 的发现：5 份 freeze 产物 / 25 条 check **从未非绿**、且**无变异体记录**
        # ⇒ 按裁定 27.1「恒真的闸等于没有闸」。补牙分两层，两层都是 B2 本轮**自己产的证据**：
        #   甲（判据层）：亲自复跑上游 `--selftest`（12 条变异、含 2 条反向），逐 G 统计
        #       「有没有一条期望 RED 且实际 RED 的变异体」⇒ 覆盖 G1–G5（下面这条新 check 判它）。
        #   乙（转录层）：`--selftest` 的 T1–T11 —— 喂合成的 guard 产物（每个 G 各一条 RED）
        #       证明**B2 这一层**会跟着红、且 id 能精确点到那个 G（不碰 B 的脚本）。
        teeth = _upstream_guard_teeth(root, py, out_dir)
        ref78_4 = ("裁定 78.4（freeze 二选一：①补 ≥1 反向变异体/G 后恢复「闸」称谓；"
                   "②降级 checklist_not_gate）/ 裁定 27.1（恒真的闸等于没有闸）/ "
                   "D→B2 §15-5 item 5")
        t_req = ("上游 `scripts/b_env_provenance_guard.py --selftest` 本轮**由 B2 亲自复跑**："
                 "rc == 0、全部变异达预期（n_ok == n_results）、且 **G1–G5 每个 G 都至少有 1 条"
                 "「期望 RED 且实际 RED」的变异体**（裁定 78.4 的①：≥1 个反向变异体/G）")
        t_red = ("rc != 0；或 n_ok != n_results；或某个 G 的 `red_caught == 0`"
                 "（那个 G 在判据层无从证明能红 ⇒ 本层必须退回②降级为 checklist_not_gate）")
        if not teeth.get("ran"):
            rep.add("G1-G5_freeze_teeth", None,
                    teeth.get("why_not_ran") or "上游自检未跑成", t_req,
                    note="没有牙的证据 ⇒ 弃权（三值纪律）。**此时 `delegated_g1_g5_freeze` 不得"
                         "被当独立闸引用**（裁定 78.4 的②自动生效）",
                    ruling_ref=ref78_4, red_when=t_red)
        else:
            t_bad = []
            if teeth.get("rc") != 0:
                t_bad.append("上游自检 rc=%r（!= 0）⇒ 它自己的变异体没全咬住" % teeth.get("rc"))
            if not teeth.get("upstream_all_caught"):
                t_bad.append("上游自检 n_ok=%r / n_results=%r ⇒ 有变异未达预期"
                             % (teeth.get("n_ok"), teeth.get("n_results")))
            per_g_red = teeth.get("per_g_caught_red_mutants") or {}
            if not teeth.get("every_g_has_a_caught_red_mutant"):
                t_bad.append("**G 覆盖不全**：%s 没有「期望 RED 且实际 RED」的变异体"
                             "（逐 G 实测 %s）⇒ 那些 G 在判据层无从证明能红"
                             % ([g for g in GUARD_G_EXPECTED if per_g_red.get(g, 0) < 1], per_g_red))
            cal = teeth.get("n_rows_parsed_caliber") or {}
            if cal.get("difference_explained") is False:
                t_bad.append("**计数差值无从解释**：%s（裁定 92.3-ii：对账差值必须能被解释；"
                             "解释不了就不许用「口径不同」含糊过去）"
                             % cal.get("unexplained_difference"))
            if teeth.get("upstream_baseline_all_green") is False:
                t_bad.append("上游自检的 **baseline 行**不是全绿（%s）⇒ 它的合成世界本身有问题，"
                             "后面 11 条「抓住」都失去意义" % teeth.get("upstream_baseline_rows"))
            rep.add("G1-G5_freeze_teeth", not t_bad, {
                "violations": t_bad, "upstream_script": teeth.get("script"),
                "upstream_script_sha256_12": teeth.get("script_sha256_12"),
                "upstream_script_lines": teeth.get("script_lines"),
                "read_only_reuse": True, "modified_by_b2": False,
                "rc": teeth.get("rc"), "n_ok": teeth.get("n_ok"),
                "n_results": teeth.get("n_results"),
                "n_rows_parsed": teeth.get("n_rows_parsed"),
                "n_rows_parsed_caliber": cal,
                "upstream_baseline_all_green": teeth.get("upstream_baseline_all_green"),
                "upstream_baseline_rows": teeth.get("upstream_baseline_rows"),
                "g_covered": teeth.get("g_covered"),
                "per_g_caught_red_mutants": per_g_red,
                "per_g_reverse_mutants": {g: (teeth.get("per_g") or {}).get(g, {}).get("reverse_ok")
                                          for g in GUARD_G_EXPECTED},
                "every_g_has_a_caught_red_mutant": teeth.get("every_g_has_a_caught_red_mutant"),
                "stdout_log": teeth.get("log"), "teeth_artifact": teeth.get("teeth_artifact"),
                "b2_transcription_layer_teeth": {
                    "location": "本脚本 `--selftest` 的 T1–T11（转录层，喂合成 guard 产物）",
                    "artifact": str(out_dir / "mutation_verdict.json"),
                    "what_they_prove": ("若上游把某个 G 判 RED，B2 的聚合与逐条转录**必须**跟着红，"
                                        "且归一 id 能精确点到那个 G（T1–T5 各打一个 G）；"
                                        "T6 反向（全绿产物不得误报）；T7 前导空格必须被去掉；"
                                        "T8 `check_id` 缺失不得留 null；T9 三值集外的 status 必须弃权；"
                                        "T10/T11 钉住上面这个覆盖统计的解析器本身不恒真")},
            }, t_req,
                note="两层牙都是 B2 本轮自产的证据（不是转述上游散文）⇒ 采裁定 78.4 的①，"
                     "`delegated_g1_g5_freeze` 保留「闸」称谓，但引用规则见该条的 "
                     "`teeth_ruling_78_4.downstream_citation_rule`",
                ruling_ref=ref78_4, red_when=t_red)
        obs_f["teeth_ruling_78_4"] = {
            "ruling": ref78_4,
            "d_finding": ("5 份 freeze 产物 / 25 条 check 从未非绿、无变异体记录 "
                          "⇒ 裁定 27.1「恒真的闸等于没有闸」"),
            "option_chosen": "①（补牙，不降级为 checklist_not_gate）",
            "option_2_would_have_been": ("产物 `kind` 改标 `checklist_not_gate`、下游不得当保护层引用"
                                         "（若下面任一层牙缺失，就自动退回这一档）"),
            "teeth_layer_1_criteria": {
                "where": "上游 `scripts/b_env_provenance_guard.py --selftest`（B2 只读、本轮亲自复跑）",
                "rc": teeth.get("rc"), "n_ok": teeth.get("n_ok"),
                "n_results": teeth.get("n_results"),
                "per_g_caught_red_mutants": teeth.get("per_g_caught_red_mutants"),
                "every_g_covered": teeth.get("every_g_has_a_caught_red_mutant"),
                "evidence": [teeth.get("log"), teeth.get("teeth_artifact")],
                "not_transcribed_from_prose": True},
            "teeth_layer_2_transcription": {
                "where": "本脚本 `--selftest` 的 T1–T11",
                "artifact": str(out_dir / "mutation_verdict.json")},
            "still_delegated": ("G1–G5 的**判据本身**是 B 的（B2 只转录、不重写，D→B2 §1.1）"
                                "⇒ 引用本条时必须写「判据在上游、B2 转录 + 本轮复跑上游牙」"),
            "downstream_citation_rule": ("可以当闸引用（裁定 78.4 的①已满足），但**必须同引** "
                                         "`G1-G5_freeze_teeth` 的实测（rc / 逐 G 覆盖）与 T 系列；"
                                         "**不得**写成「B2 独立验证了 G1–G5 的判据」"
                                         "（那是把转录说成自证，裁定 88.3-1 的同型）"),
        }
        obs_f["gate_designation"] = ("gate_with_upstream_teeth_machine_rerun"
                                     if teeth.get("ran") and teeth.get("all_caught")
                                     and teeth.get("every_g_has_a_caught_red_mutant")
                                     else "checklist_not_gate_see_G1-G5_freeze_teeth")

    venv_ok = Path(venv).exists() and (Path(venv) / "bin" / "python").exists()
    have_lock = bool(ev.get("lock_pins_norm"))
    if not (venv_ok and have_lock):
        miss = []
        if not venv_ok:
            miss.append("venv 不存在或无解释器：%s" % venv)
        if not have_lock:
            miss.append("A2 的 requirements.lock.txt 不可读（missing=%s）" % ev.get("missing"))
        rep.add("G1-G5_a2env", None, "；".join(miss), req,
                note="**故意不委派**：对不存在的 venv，G4/G5 会输出 RED/WARN，那是把「还没建」"
                     "误读成「建坏了」（假红）。A2 交件后本行自动变成实判。",
                ruling_ref=ref + " / 裁定 14（证据不足不得输出最重失效标签）", red_when=red)
        return doc_f

    expect_numpy = (ev.get("lock_pins_norm") or {}).get("numpy")
    extra = ["--rebuild-dir", str(a2_dir), "--venv", str(venv)]
    if expect_numpy:
        extra += ["--expect-numpy", expect_numpy]
    doc_a, _ = _guard_once(root, py, out_dir / "delegated_g1_g5_a2env.json", extra)
    if doc_a is None:
        rep.add("G1-G5_a2env", False, "委派失败：delegated_g1_g5_a2env.json 不可解析", req,
                note="判据装置跑不起来 ≠ 环境合规", ruling_ref=ref, red_when=red)
        return doc_f
    obs = _transcribe_guard(rep, doc_a, "a2env", ref, req, red)
    obs["expect_numpy"] = expect_numpy
    obs["expect_numpy_source"] = ("A2 的 requirements.lock.txt 的 numpy pin（事实源）"
                                  if expect_numpy else
                                  "**未推导**（A2 的 lock 里没有 numpy pin）⇒ 闸内会响亮回显退回常量")
    obs["lock_diff_note"] = ("G2 已枚举 π₀.₅ 环境相对 0928 ACT lock 的逐包差异（见 JSON 的 lock_diff）；"
                             "裁定 34.1：引用差异必须**点名包与版本**，不得写成「差异可忽略」")
    return doc_a


def delegate_v0_v9(ev, rep, root: Path, out_dir: Path, py: str, run_it=True):
    ref = "D→B2 §1.1（V0–V9 不变性口径，当前 10/10 全过）/ 裁定 36.2"
    req = "V0–V9 全过（10/10）：用**当下没漂的判据装置**去判 A2 的新环境，否则准入本身不可信"
    red = "任一 V 判 FAIL；或委派进程跑不起来"
    jout = out_dir / "delegated_v0_v9.json"
    if not run_it:
        rep.add("V0-V9_delegated", None, "--no-delegate：未调用 B 的迁移不变性闸", req,
                note="缺委派 ⇒ 准入不得给 PASS", ruling_ref=ref, red_when=red)
        return None
    cmd = [py, str(root / "scripts/b_env_migration_invariance_check.py"), "--json-out", str(jout)]
    r = _run(cmd)
    (out_dir / "delegated_v0_v9.log").write_text(
        "CMD: %s\nRC: %s\n--- stdout ---\n%s\n--- stderr ---\n%s\n"
        % (" ".join(r["cmd"]), r["rc"], r["stdout"], r["stderr"]))
    doc = None
    if jout.exists():
        try:
            doc = json.loads(jout.read_text(errors="replace"))
        except Exception:
            doc = None
    if doc is None:
        rep.add("V0-V9_delegated", False,
                "委派失败：rc=%s，%s 不可解析" % (r["rc"], jout.name), req,
                note="判据装置跑不起来 ≠ 不变性成立", ruling_ref=ref, red_when=red)
        return None
    s = doc.get("summary") or {}
    obs = {"n_pass": s.get("pass"), "n_fail": s.get("fail"), "total": s.get("total"),
           "ok": doc.get("ok"), "gate_build_expected": doc.get("gate_build_expected"),
           "per_check": {c["id"]: ("PASS" if c.get("ok") else "FAIL") for c in (doc.get("checks") or [])}}
    ok = bool(doc.get("ok")) and s.get("fail") == 0 and s.get("total") == 10
    rep.add("V0-V9_delegated", bool(ok), obs, req,
            note=("逐条 V 的 observed/required 见 `delegated_v0_v9.json`；B2 本轮已独立复跑 10/10。"
                  "**裁定 78.4：本条标 `teeth_delegated_to_upstream`** —— 它的牙不在 B2 这一层，"
                  "而在被转述的 B 门禁上（`V3: n_mutations=15 / n_caught=15`）；"
                  "**下游不得把本条当独立闸引用**（B2 只转录，没有自己的反向变异体）。"),
            ruling_ref=ref, red_when=red)
    obs["teeth_delegated_to_upstream"] = True
    obs["teeth_location"] = ("B 的 `scripts/b_env_migration_invariance_check.py` 自带的变异体台账"
                             "（V3: n_mutations=15 / n_caught=15）；B2 这一层**没有**独立牙")
    obs["downstream_must_not_cite_as_independent_gate"] = True
    for vi, c in enumerate(doc.get("checks") or []):
        # 裁定 78.3：**去掉两个前导空格**（旧版 `"  V3_…"` 让精确匹配/去重/建索引全漏），
        # 且 `id` 缺失时不留 null。`ok` 不再直接采信上游的布尔，而是与 status 同源。
        vid = c.get("id") or c.get("check_id") or ("V_index%d" % vi)
        st_v = STATUS_PASS if c.get("ok") is True else (
            STATUS_RED if c.get("ok") is False else STATUS_UNJUDGED)
        rep.add(str(vid), OK_FROM_STATUS.get(st_v), c.get("observed"), c.get("required"),
                note=c.get("note") or "", ruling_ref=ref, status=st_v,
                red_when="该 V 条判 FAIL（详见 delegated_v0_v9.json 的 red_conditions）")
    return doc


CHECKS_PI05 = ["V-pi05-1_version_anchor", "V-pi05-2_weights_identity",
               "V-pi05-3_channel_provenance", "V-pi05-4_torch_stack_frozen",
               "V-pi05-5_transformers_pi05_ready", "V-pi05-6_manifest_selfconsistency",
               "V-pi05-7_control_hz_triple", "V-pi05-8_compat_dir_step_deletion"]


def run_pi05_version_checks(ev, rep, root: Path):
    """八条 π₀.₅ 牙的**唯一**执行序列（`--selftest` 与现场判定都走这里）。

    为什么必须只有一处（ADR-C-014 的同型教训，本闸 19:0x 刚踩过一次）：第一版
    `--selftest` 走 `run_pi05_checks`，而 `main()` 把 check 一条条**另外**列出来 ⇒
    新加的第 5 条牙在自检里 36/36 全绿、在**真实现场**里根本没被调用（total 仍是 28）。
    缺陷类是「被测对象与用户使用的对象不是同一个」：自检绿 ≠ 现场在跑。
    现在两条路径共用这一个函数，另外 `check_a1_all_teeth_ran` 在出判词前兜底。
    """
    check_v_pi05_1(ev, rep)
    check_v_pi05_2(ev, rep, root)
    check_v_pi05_3(ev, rep)
    check_v_pi05_4(ev, rep)
    check_v_pi05_5(ev, rep)
    check_v_pi05_6(ev, rep)
    check_v_pi05_7(ev, rep)
    check_v_pi05_8(ev, rep)


def run_pi05_checks(ev, rep, root: Path, out_dir: Path):
    check_a0_teeth(ev, rep, out_dir)
    run_pi05_version_checks(ev, rep, root)


def check_inputs_stable(ev, rep):
    """判定跑完之后回看：输入文件在**判定期间**有没有被别的会话改写（裁定 39.2 的四会话并发）。

    可红/可黄条件不是理论上的：2026-09-29 19:04:54 A2 就在本闸跑的过程中重写了
    `requirements.lock.txt`。这种情况**必须显式出现在判词里**，否则读判词的人会以为
    它描述的是同一个时间点的世界（而其实是两个时点的拼接）。
    """
    moved = []
    for n, meta in (ev.get("files") or {}).items():
        if not meta.get("exists"):
            continue
        p = Path(meta["path"])
        try:
            st = p.stat()
        except OSError:
            moved.append({"file": n, "change": "判定期间消失了"})
            continue
        if st.st_mtime_ns != meta.get("mtime_ns"):
            now_sha = _sha256_file(p)["sha256"]
            moved.append({"file": n, "change": "mtime 变了",
                          "snapshot_mtime_iso": meta.get("mtime_iso"),
                          "now_mtime_iso": datetime.fromtimestamp(st.st_mtime).astimezone()
                          .isoformat(timespec="seconds"),
                          "snapshot_sha256": (meta.get("sha256") or "")[:16],
                          "now_sha256": (now_sha or "")[:16],
                          "bytes_changed": st.st_size != meta.get("bytes")})
    if moved:
        rep.add("A2_inputs_stable_during_run", False,
                {"n_moved": len(moved), "moved": moved,
                 "snapshot_taken_at": ev.get("snapshot_taken_at"),
                 "checked_at": datetime.now().astimezone().isoformat(timespec="seconds")},
                "判定期间（collect 快照 → build_verdict）A2 的四份交件必须逐字节不动",
                note=("**这不是环境不合格，是判词的时间边界被破坏了**：本次判词描述的是 "
                      "`snapshot_taken_at` 那个时点的世界，被改动的文件需重跑本闸才能定案。"
                      "修法：A2 改完环境/产物后**再**叫 B2 跑闸（或 B2 重跑一次）。"),
                status=STATUS_WARN,
                ruling_ref="裁定 39.2（四会话并发）/ 裁定 34.1（钉实际值，不钉半路的值）",
                red_when="任一交件在判定期间 mtime/字节变了（⇒ 判词自相矛盾的风险）")
    return moved


def check_a1_all_teeth_ran(rep):
    """兜底牙：判词里必须**真的**出现全部八条 π₀.₅ 牙，少一条 ⇒ RED。

    可红条件不是理论上的：19:0x 的现场判定就少跑了 V-pi05-5（见 `run_pi05_version_checks`
    的注释）。没有这条兜底，"漏跑一条牙"的样子是**总数少一行**，不是报错 —— 与
    "恒真牙"同族（失效是静默的）。变异见自检的 `A1_missing_tooth` 案。
    """
    ran = {c["id"] for c in rep.checks}
    missing = [cid for cid in CHECKS_PI05 if cid not in ran]
    if missing:
        rep.add("A1_all_teeth_ran", False,
                {"n_checks_in_verdict": len(rep.checks), "ran": sorted(ran),
                 "expected": list(CHECKS_PI05), "missing": missing},
                "判词里必须出现全部 %d 条 π₀.₅ 牙：%s" % (len(CHECKS_PI05), CHECKS_PI05),
                note="漏跑的牙不会报错，只会让 total 少一行 ⇒ 必须由这条兜底判红",
                ruling_ref="ADR-C-014 同型（被测对象与使用对象不是同一个）/ 裁定 27.1",
                red_when="CHECKS_PI05 里任一 id 没出现在 checks[] 中")
    return missing


def admission_of(rep):
    """四值**标签**（PASS / WARN / UNJUDGED_evidence_missing / RED），**不是**失败判据。

    RR-B2-09 改判后（裁定 93 / D→B2 §四-1）：失败判据只有顶层 `ok`（= `ok_of()`）；
    本函数的职责是**登记世界状态**。其中 `WARN` 一档必须保留 —— 它承载"WARN 不计失败
    但必须登记"里的"必须登记"那一半（自检 O1 钉住：只加 WARN ⇒ 标签仍是 `WARN`
    而 `ok_of()` 仍为 True）。把这一档删掉或并进 PASS，登记义务就等于被改判取消了。
    """
    if rep.n_red:
        return "RED"
    if rep.n_unjudged:
        return "UNJUDGED_evidence_missing"
    if rep.n_warn:
        return "WARN"
    return "PASS"


def collect_ruling_requests(rep, ev):
    """把「本闸遇到但**无权自裁**」的口径问题结构化上呈 D（不静默放宽、也不静默判红）。

    本仓的教训（裁定 27 / 35.3 / 37.4 / 环境调研线自纠第 1 起）：判据与散文不同源、
    或某个前置门从未与原文对撞，会让一条**解释**逐渐获得既成地位。所以凡本闸对 D 的原文
    采了非字面读法，必须在这里点名、给证据、给立场、给「若判错的影响」。
    """
    rr = []
    for c in rep.checks:
        o = c.get("observed")
        if not isinstance(o, dict):
            continue
        if o.get("at_anchor_note"):
            rr.append({
                "id": "RR-B2-01",
                "check": c["id"],
                "topic": "裁定 39.1「清单里出现 torch 的 install/upgrade ⇒ 停下报 D」的字面读法 vs 认版本读法",
                "observed": {"n_at_anchor_lines": len(o.get("dryrun_at_anchor") or []),
                             "at_anchor_lines": [h["line"] for h in (o.get("dryrun_at_anchor") or [])][:6],
                             "n_off_anchor_lines": len(o.get("dryrun_off_anchor") or []),
                             "torch_version_live": o.get("torch_version_live"),
                             "torch_anchor": TORCH_ANCHOR},
                "question": ("A2 的 dryrun 是**空 venv 一次性解析 + STAGE 1 先钉 torch 栈**的分段形态，"
                             "前段必然出现 `+ torch==2.6.0+cu124`。字面读法会判「停下报 D」；"
                             "认版本读法认为「装成值 == 锚值 ⇒ torch 栈未被挪动」，不构成违例。请 D 裁定采哪一种。"),
                "b2_position": ("采**认版本**读法：红线的实质是「torch 栈不得被动」（跨 torch 版本会让 V0–V9 基线"
                                "与 t17_train_side_verify_v2.json 失去可比性），而按锚值全新安装不产生这种不可比。"
                                "本闸同时保留 off_anchor / uninstall / unversioned 三类红与锚值回校（M23/M25/M26/M27），"
                                "所以放宽的只是「字面命中」这一层，牙没有变钝。"),
                "impact_if_wrong": ("若 D 采字面读法，A2 每次重建 venv 都会被判红，等于要求「先有 torch 再建环境」，"
                                    "与 裁定 39.1「新环境一律另建 + --link」冲突；"
                                    "若 B2 的读法过宽，则「装成 2.6.0+cu124 但 dryrun 未留痕」这类情形会漏网"
                                    "—— 已由 live 探针 + unversioned 定案规则兜住。"),
                "evidence_paths": ["runs/vla/a2_env_pi05_sim_20260929/resolve_dryrun.txt",
                                   "runs/vla/b2_env_admission_20260929/mutation_verdict.json"],
            })
    # lock 的 freeze 工具口径：pip freeze 写 `torch==2.6.0`，uv 可能写 `torch==2.6.0+cu124`
    lp = (ev.get("lock_pins_norm") or {}).get("torch")
    if lp and lp != "2.6.0":
        rr.append({
            "id": "RR-B2-02",
            "check": "V-pi05-4_torch_stack_frozen",
            "topic": "lock 的 torch pin **字面形态**取决于 freeze 工具（pip 写 2.6.0，uv 可能写 2.6.0+cu124）",
            "observed": {"a2_lock_torch_pin": lp, "locks_0928_torch_pin": "2.6.0",
                         "note": "两者都对 CUDA 构建**不可判**或**可判**，取决于工具而非环境"},
            "question": ("A2 的 lock 里 torch pin 是 `%s`，而两套已验收 0928 lock 是 `2.6.0`。"
                         "委派给 B 的 G2 会把这报成「changed: torch 2.6.0 -> %s」，"
                         "但那是 **freeze 工具的写法差异**，不是环境差异。请 D 裁定：是否要求 π₀.₅ 线的 lock "
                         "一律带 `+cu124`（这样 lock 自身就可判 CUDA 构建），以及这条差异是否按 裁定 34.1 "
                         "「按包按链路」豁免。" % (lp, lp)),
            "b2_position": ("建议要求带 `+cu124`：本闸已证明 lock 的 `torch==2.6.0` 对 CUDA 构建是盲的"
                            "（cu121/cu124/cu128 会写出逐字节相同的 pin 行），带上本地段能让 lock 自身成为可判证据，"
                            "而不是每次都要活体探针。但**不改** 0928 那两份（冻结面），只对新线生效。"),
            "impact_if_wrong": ("若不裁，G2 的逐包差异表里会长期挂着一条「假差异」，"
                                "后来者要么误读成环境漂移，要么习惯性忽略差异表（那等于废掉 G2）。"),
            "evidence_paths": ["runs/infra/lerobot_act_env_20260928/requirements.lock.txt",
                               "runs/vla/b2_env_admission_20260929/delegated_g1_g5_a2env.json"],
        })
    # ---- RR-B2-05：裁定 36.4 的「标 external_unverified」要不要字面 token ----
    for c in rep.checks:
        if not c["id"].startswith("V-pi05-3"):
            continue
        o = c.get("observed")
        if not isinstance(o, dict):
            continue
        unmarked = o.get("external_unmarked") or []
        if unmarked:
            rr.append({
                "id": "RR-B2-05",
                "check": c["id"],
                "topic": "裁定 36.4「外部事实必须标 external_unverified」的**标记词表**：字面 token 还是语义等价标记",
                "observed": {"external_unmarked": unmarked,
                             "n_external_keys_seen": o.get("n_external_keys"),
                             "marked_but_not_flagged": [e["key"] for e in (o.get("external") or [])
                                                        if e.get("marked")][:12],
                             "mark_vocabulary_accepted_by_gate": [
                                 "块名 `external_unverified` / `external_facts` / `*unverified*`",
                                 "块名 `remote_*` / `upstream_*` / `vendor_*` / `manifest_*`",
                                 "同层 `kind|source|provenance|class|origin` 的值点名远端"
                                 "（如 A2 的 `kind: remote_api_read`、`source: HF API …`）"]},
                "question": ("A2 的真实 receipt 用 `kind: \"remote_api_read\"` + `source: \"HF API …\"` "
                             "与 `remote_hf` / `remote_modelscope` 两个远端块来标注外部来源，"
                             "但**没有**用字面 token `external_unverified`。请 D 裁定：语义等价的标记算不算"
                             "满足裁定 36.4，还是必须字面出现该 token。"),
                "b2_position": ("本闸已承认语义等价标记（M31 反向变异钉住：A2 完整结构必须全绿，防恒红），"
                                "但**没有**放宽实质要求——外部声明值若躺在**实测块**里且无任何标记仍判红"
                                "（M32 钉住；真实现场命中的两条是 `$.download.reported_size`（远端报的字节数，"
                                "与本机实测 `measured_rate_MBps` 同 dict）与 `$.verdict.license_ok`"
                                "（外部事实的派生判定，与本地判定同 dict））。B2 认为这两条是真违例，"
                                "修法各一行：把它们改成带 `kind`/`source` 的小 dict，或挪进 `remote_*` 块。"),
                "impact_if_wrong": ("若 D 要求字面 token，A2 的 receipt 需在 4 处补 `provenance` 字段"
                                    "（成本极低，B2 不改判据、只等 D 一句话）；若 D 认为 B2 放宽过头，"
                                    "则 `$.remote_hf.license` / `$.remote_hf.last_modified` / `$.license` "
                                    "三条要恢复判红 —— 那会让任何**已经正确标注来源**的 receipt 也红，"
                                    "红点失去指向性（本仓第 8 起同型假红的教训）。"),
                "evidence_paths": ["runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json",
                                   "runs/vla/b2_env_admission_20260929/mutation_verdict.json"],
            })
    # ---- RR-B2-06：§8.1 的 transformers 区间锚被现场证伪 ----
    for c in rep.checks:
        if not c["id"].startswith("V-pi05-5"):
            continue
        o = c.get("observed")
        if not isinstance(o, dict):
            continue
        fc = o.get("functional_check") or {}
        tf_live = o.get("tf_live_version")
        commit = o.get("git_commit")
        if not (tf_live and commit and fc.get("ok") is True):
            continue
        rr.append({
            "id": "RR-B2-06",
            "check": "V-pi05-1_version_anchor × V-pi05-5_transformers_pi05_ready",
            "topic": "D→B2 §8.1 的 transformers 区间锚（>=%s,<%s）被现场**证伪**："
                     "lerobot 的 π₀.₅ 要求的是 git 定制分支，不是版本区间"
                     % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL),
            "observed": {
                "tf_live_version": tf_live, "git_commit": commit,
                "git_branch": o.get("git_branch"), "git_url": (o.get("install_source") or {}).get("url"),
                "lerobot_hard_check": "%s == %r" % (PI05_TF_CHECK_PATH, fc.get("ok")),
                "section_8_1_bound": ">=%s,<%s" % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL),
                "below_floor": tf_live < TRANSFORMERS_FLOOR,
                "a2_probe_pypi_4576": "ValueError: An incorrect transformer version is used"
                                      "（modeling_pi05.py:584）",
                "a2_probe_git_4533": "模型加载成功 params=3.617B（GPU allocated 13812.5 MiB）"},
            "question": ("**区间锚与 git 安装互斥**：满足 §8.1 区间的 PyPI 4.57.6 被 lerobot 的硬校验拒绝；"
                         "通过硬校验的是 git 分支 `fix/lerobot_openpi`@`%s`，其版本字符串 `%s` **低于**下界，"
                         "而且 freeze 出来是 `transformers @ git+…@<commit>` 形态（**不含版本字符串**）"
                         "⇒ V-pi05-1 那条区间判据对**合规**环境也必然判红。请 D 裁定："
                         "①§8.1 表格的 transformers 行是否改为「git commit + 功能校验」；"
                         "② V-pi05-1 的区间判据是否停用/降级为观测。" % (commit[:12], tf_live)),
            "b2_position": ("采「**功能锚 + git commit 溯源**」：能不能跑 π₀.₅ 的事实源是 lerobot 自己的硬校验 "
                            "`%s`（B2 活体探针实测 == True，秒级、CPU-only、不占卡），"
                            "而 git 装的包只有 `dist-info/direct_url.json` 里的 commit 能认出来"
                            "（版本字符串 `4.53.3` 可以是该分支任何一次 build）。"
                            "已实现为**第 5 条牙 V-pi05-5**（M33 校验 False 必须红 / M34 git+commit 进 lock 必须绿 / "
                            "M35 只有版本没 commit 必须红）。**B2 不自行修改 V-pi05-1 的区间判据**"
                            "（M26 立的规矩：锚与事实源不符 ⇒ 报 D 更新锚，不得就地放宽）"
                            "⇒ 在 D 裁定之前，V-pi05-1 会继续对合规环境判红，这是刻意的。"
                            % PI05_TF_CHECK_PATH),
            "impact_if_wrong": ("若不裁：A2 每次交件都挂着一条**无法用任何合规操作消除**的红点 ⇒ 后来者会习惯性"
                                "忽略红点（等于废掉 V-pi05-1）；若 B2 自行改锚：违反 M26 纪律，且失去"
                                "「D 的锚被现场证伪」这条记录（A2 在 resolve_dryrun.txt STAGE 3 已独立写下"
                                "「推翻 D §9.1 的一条前提」，两侧证据互不相识就会各说各话）。"),
            "evidence_paths": [
                "runs/vla/a2_pi05_contract_20260929/probe_run1_transformers_blocker.log",
                "runs/vla/a2_pi05_contract_20260929/probe.log",
                "runs/vla/a2_env_pi05_sim_20260929/resolve_dryrun.txt",
                "runs/vla/a2_env_pi05_sim_20260929/stage3_install.log",
                "runs/vla/b2_env_admission_20260929/live_probe.json",
                "runs/vla/b2_env_admission_20260929/mutation_verdict.json"],
        })

    # ---- RR-B2-07：「冻结栈是否漂移」的事实源 —— dist-info 元数据版本 vs runtime 版本 ----
    # 与 RR-B2-02 同源（都是 local version 段 `+cu124` 的口径问题），但后果不同：
    # RR-B2-02 只让 G2 的差异表挂一条假差异；这一条直接让 A2 的交件自述 `env_usable=false`，
    # 而 A2 自己在 `verdict.blocked_if` 里写了「drift 非空 ⇒ 需 D 登记 + 重过 B2 闸」
    # ⇒ 下游（B2 的任务 2/3/4：数据采集、T17、评测器）读到的结论是"环境不可用"。
    for c in rep.checks:
        if c["id"] != "V-pi05-6_manifest_selfconsistency":
            continue
        o = c.get("observed")
        if not isinstance(o, dict):
            continue
        recon = ((o.get("reconciliation") or {}).get("per_package")) or []
        decl = o.get("a2_declared") or {}
        b2p = o.get("b2_independent_runtime_probe") or {}
        if not recon:
            continue
        rr.append({
            "id": "RR-B2-07",
            "check": "V-pi05-6_manifest_selfconsistency",
            "topic": "「冻结栈是否漂移」的事实源：A2 用 **dist-info 元数据版本**比基线，"
                     "B2 用 **runtime `__version__`**（torch 另比 `torch.version.cuda`）",
            "observed": {
                "a2_env_usable": decl.get("env_usable"),
                "a2_assertions_pass": decl.get("n_assertions_true"),
                "a2_frozen_stack_drift": decl.get("frozen_stack_drift"),
                "a2_differing_packages": decl.get("differing_packages"),
                "b2_runtime_pi05_sim": (b2p.get("pi05_sim") or {}),
                "b2_runtime_baseline": (b2p.get("baseline") or {}),
                "b2_cause_classes": [(r["package"], r["class"]) for r in recon],
            },
            "question": ("A2 的 `env_manifest.json` 用 dist-info 元数据串比基线 venv，而 PyPI 轮子的 "
                         "METADATA 不带 local version 段（基线 `torch-2.6.0.dist-info`）、"
                         "download.pytorch.org 的带（π₀.₅ 侧 `torch-2.6.0+cu124.dist-info`）"
                         "⇒ **同一个 CUDA 12.4 构建**被判成 drift，进而 `env_usable=false`。"
                         "请 D 裁定：① 冻结栈漂移的判定口径是否统一为 runtime `__version__`"
                         "（torch 再加 `torch.version.cuda`）；② 新线的 lock / manifest 是否一律要求带 "
                         "local version 段（与 RR-B2-02 同一决定）；③ A2 现交的这份 `env_usable=false` "
                         "是否登记为「口径假红」并要求重出 manifest（B2 无权改 A2 的实现，"
                         "也无权用散文推翻交件）。"),
            "b2_position": ("采 runtime 口径，且两个口径在产物里**分开记不混算**（裁定 36.4）。"
                            "V-pi05-6 对 `env_usable=false` **一律判红**，不因「成因是假红」就放行："
                            "准入不得建立在一份自称不可用的交件上，而由 B2 就地宣布「其实可用」"
                            "正是本仓「解释逐渐获得既成地位」的老毛病（裁定 27 / 35.3 / 37.4）。"
                            "已实现为**第 6 条牙 V-pi05-6**：M36（只有元数据差异）必须红且点名 "
                            "`metadata_only`；M38（runtime 真不同）必须红且点名 `real_runtime_drift`；"
                            "M40（assertions 有 False 却自称可用）必须红；M41（drift 无从复核）必须红；"
                            "M37（差异都在冻结栈外）必须绿；M39（交件缺可用性三键）必须弃权。"),
            "impact_if_wrong": ("若不裁：A2 的交件会长期自述 `env_usable=false`，下游读到的是"
                                "「环境不可用」⇒ 要么任务 2/3/4 停摆，要么后来者习惯性忽略这句结论"
                                "（那等于废掉 manifest 的可用性字段）；若 B2 自行放行：真漂移发生时"
                                "同一条牙也会被人当作假红忽略（本仓第 8 起同型假红的镜像风险）。"),
            "evidence_paths": [
                "runs/vla/a2_env_pi05_sim_20260929/env_manifest.json",
                "scripts/a2_env_manifest.py:281-313（frozen 的计算与 env_usable 公式，B2 只读）",
                "runs/vla/b2_env_admission_20260929/live_probe.json",
                "runs/vla/b2_env_admission_20260929/mutation_verdict.json"],
        })

    # ---- RR-B2-09（**已关闭**：裁定 93 / D→B2 执行单 20260930 §四-1）----
    # 议题原文：顶层 `ok` 该不该把 **WARN** 也算作失败（本闸曾采比 D 字面更严的读法）。
    # 为什么当初必须开这一条：D→B2 §15-5 item 6（裁定 78.2）的字面只说了两件事 ——
    # 「顶层 `ok` 是唯一失败判据」与「`UNJUDGED` 必须计入非绿」，**没有**说 WARN 让 ok=false；
    # 而本闸当时的 `OK_CRITERION` 写的是 `n_red == 0 且 n_unjudged == 0 且 n_warn == 0`
    # ⇒ 那是一处**非字面读法**，按本仓纪律（裁定 27 / 35.3 / 37.4：不许让一个解释悄悄获得
    # 既成地位）必须点名报 D，不能自己定了就当定论。**D 已裁：那一层加严不保留。**
    # 为什么关闭了还整条留着：裁定 92.4「作废不删件、不改名」+ 本仓既有写法（RR-B2-06 同样以
    # CLOSED 形态留在产物里）。历史价值两点：① 记录了 B2 曾自采更严读法并**点名上报**
    # （没有静默改判据）；② 记录了那种加严的**现实代价** —— 裁定 93.1 把两颗牙从 RED 转成
    # WARN 之后，旧口径会把 C2 的主线臂二次判死（D 的原话）⇒ 后来者若又想「顺手加严一层」，
    # 先读这一条，再读 O1–O5 那五颗牙。
    if rep.n_warn:
        warn_ids = [c["id"] for c in rep.checks if c["status"] == STATUS_WARN]
        rr.append({
            "id": "RR-B2-09",
            "check": "__verdict__（顶层 `ok` / `admission_granted` / 退出码的判据）",
            "topic": "裁定 78.2 只明写「UNJUDGED 计入非绿」；本闸曾**另外**让 WARN 也使 "
                     "`ok=false`（更严）⇒ 请 D 裁定这一层严格性要不要保留。"
                     "**D 已裁：不保留**（WARN 不计失败但必须登记）。",
            "ruling": {
                "closed_by": ("裁定 93 + D→B2 执行单 20260930 §四-1（原文：「与裁定 78.2 的四元组"
                              "口径对齐：`ok` 是唯一失败判据、`UNJUDGED` 计入非绿、**WARN 不计失败"
                              "但必须登记**」；D 并点名「裁定 93.1 会把两颗牙从 RED 转成 WARN ⇒ "
                              "这条不修，C2 的主线臂会被你的顶层 `ok` 二次判死」，"
                              "优先级因此由 P1 提到 **P0.5**）"),
                "caliber_now": ("`ok` == `ok_of(n_red, n_unjudged, n_warn)` == "
                                "(n_red==0 且 n_unjudged==0)；口径标记 `%s`" % OK_CALIBER_MARKER),
                "what_changed_in_code": [
                    "OK_CRITERION 改写（含改判前口径的作废说明）+ 新增常量 OK_CALIBER_MARKER",
                    "新增唯一实现 `ok_of()`；`build_verdict` 的 `ok` 与 `admission_granted` 都调它",
                    "`_normalize_guard_doc` 归一副本的 `ok` 改调同一个 `ok_of()`（两处同源）",
                    "`EXIT['WARN']` 2 → 0（按 rc!=0 判失败的下游不得被非违例登记项二次判死）",
                    "新增顶层 `warn_registered_not_blocking` / `admission_granted_criterion` / "
                    "`exit_code_caliber` 三块（把「不计失败」与「必须登记」两半都摆到顶层）",
                    "自检新增 `verdict_caliber` 层 O1–O5（`N_VERDICT_CALIBER_TEETH`）",
                ],
                "what_did_not_change": [
                    "`admission_of()` 一字未改：`admission` 仍是四值**标签**，WARN 一档保留"
                    "（登记义务的那一半就落在这个标签上）",
                    "`non_green[]` 仍逐条列 WARN，带 why/owner/fix/owner_rule",
                    "RED 与 UNJUDGED 的严格性一点没松：UNJUDGED 仍计入非绿（O2 钉住）",
                    "逐条 `counts_as_non_green` 仍只覆盖 RED+UNJUDGED ⇒ 改判后与顶层 `ok` 同源",
                    "`--expect pass|red|unjudged` 语义不变（比的是标签，不是 `ok`）",
                ],
                "teeth": ("自检 `verdict_caliber` 层 O1–O5：O1 只加 WARN ⇒ 标签 WARN 且 ok=true；"
                          "O2 只加 UNJUDGED ⇒ 标签 UNJUDGED 且 ok=false（防放宽过头）；"
                          "O3 有 RED ⇒ ok=false；O4 全 PASS ⇒ ok=true（防恒假）；"
                          "O5 同源牙（`inspect.getsource` 里必须真有 `ok_of(`、散文必须带口径标记、"
                          "`EXIT['WARN']` 必须为 0）⇒ 见 mutation_verdict.json 的 "
                          "`layers.verdict_caliber`"),
            },
            "observed": {"n_red": rep.n_red, "n_unjudged": rep.n_unjudged,
                         "n_warn": rep.n_warn, "warn_ids": warn_ids,
                         "ok_criterion_in_effect": OK_CRITERION,
                         "ok_now": ok_of(rep.n_red, rep.n_unjudged, rep.n_warn),
                         "ok_under_the_superseded_caliber": (rep.n_red == 0
                                                             and rep.n_unjudged == 0
                                                             and rep.n_warn == 0),
                         "caliber_delta_this_round": (
                             "本轮 n_red=%d ⇒ 两种口径都给 `ok=false`，**改判在本轮不改变结论**"
                             "（诚实披露：可见的变化只有 WARN 的登记块、退出码与散文）。"
                             "改判真正生效是在那条 RED（V-pi05-3）被 A2 消掉之后：届时旧口径仍会"
                             "因 2 条 WARN 判 `ok=false`（= D 说的二次判死），新口径给 `ok=true` "
                             "且 `admission=WARN` 照旧登记。" % rep.n_red),
                         "admission_mapping": "admission_of(): n_red→RED；n_unjudged→"
                                              "UNJUDGED_evidence_missing；n_warn→WARN；否则 PASS",
                         "what_the_warn_actually_is": (
                             "本轮的 WARN 逐条都是**事实缺失的登记**，不是违例：上游 G2 登记的是 "
                             "「A2 的重建目录只有 `requirements.lock.txt`、没有 "
                             "`requirements.eval.lock.txt`」。裁定 78.5 说的「极性/文案反了」，"
                             "B2 复核后的结论是：期望项（`same_as_0928=false`、`lock_diff` 逐包枚举）"
                             "**确实已满足**，这条 WARN 登记的是**另一件事**（缺一份文件），"
                             "根因是上游 id 的语义与它实际登记的事实不同名 —— 而 B2 无权改 B 的脚本")},
            "question": ("顶层 `ok` 是否应当把 WARN 计入失败？① 计入（本闸现行）⇒ 本轮 "
                         "`admission=RED`（因为还有 1 条 RED）、`ok=false`，且**即使那 1 条 RED "
                         "被 A2 消掉，`ok` 仍是 false**，直到 A2 补出 `requirements.eval.lock.txt`；"
                         "② 不计入 ⇒ 那条 RED 一消，本闸就能给 `admission=PASS`，"
                         "尽管环境里少一份 lock。请 D 裁定采哪一种。"),
            "b2_position_at_the_time_SUPERSEDED": (
                            "**【已被裁定 93 推翻，保留作历史，不得当现行判据引用】**当时采"
                            "**①计入**（更严），三条理由：(a) 本轮那条 WARN 的实质是"
                            "「一份该有的 lock 不在场」⇒ 放行就等于把「没测到」当「没问题」"
                            "（红线 `absence_of_measurement_is_not_measurement_of_absence`）；"
                            "(b) `admission_of()` 从第一版起就把 WARN 映射成非 PASS，"
                            "改成「WARN 不阻塞」要同时改 `admission` 的语义，那是改判据不是改文案；"
                            "(c) 若 D 认为这条 WARN 不该阻塞准入，**正确的修法是把那个事实消掉**"
                            "（A2 补一份 `requirements.eval.lock.txt`，成本 = 一次 pip freeze），"
                            "而不是放宽 `ok` 的判据 —— 放宽一次，下一次真的缺文件时同一条判据"
                            "就已经是软的了。**B2 不自行放宽，也不静默判红**：判据与散文同源"
                            "（`OK_CRITERION` 已把三者的差别写死在产物里）。"),
            "how_d_ruled_and_what_survives_of_b2s_position": (
                "D 采**②不计入**，但把 B2 立场里正确的两半**保留成了义务**：(b) 说的"
                "「`admission` 的语义不能顺手改」⇒ `admission_of()` 一字未动、WARN 标签保留；"
                "(c) 说的「正确修法是把事实消掉」⇒ 写进 `warn_registered_not_blocking."
                "why_still_registered`，且 `non_green[]` 仍带 owner=A2 / fix=补一份 "
                "`requirements.eval.lock.txt`。被推翻的只有 (a) 那一层：把「登记一项事实缺失」"
                "等同于「失败」，会让上游一次合法的 RED→WARN 改判（裁定 93.1）在本闸这里变成"
                "二次判死 —— 即**判据的严格性用错了对象**（严格性该对着违例，不该对着登记）。"),
            "impact_if_wrong": ("若 D 采②而 B2 继续按①：准入会长期挂在一条「A2 补一个文件就能消」的 "
                                "WARN 上，下游（C2 的 stats / A2 的 S4b / S3 BC）会被一条非违例挡住"
                                "⇒ 那是真实的进度损失，D 有权推翻；若 B2 自行采②：环境里少一份 lock "
                                "也能拿到 `admission=PASS`，而「少一份 lock」正是 G2 存在的理由"),
            "evidence_paths": [
                "runs/vla/b2_env_admission_20260930/admission_verdict.json（顶层四元组 + "
                "`warn_registered_not_blocking` + non_green[]）",
                "runs/vla/b2_env_admission_20260930/mutation_verdict.json（`layers.verdict_caliber` "
                "+ O1–O5 逐条）",
                "runs/vla/b2_env_admission_20260930/delegated_g1_g5_a2env.json（上游原件，只读）",
                "runs/vla/b2_env_admission_20260930/normalized/（归一副本 + 台账）",
                "rl_harness_supervision/d_handoff_to_b2_20260929.md:594（§15-5 item 6 的字面）",
                "rl_harness_supervision/d_handoff_to_b2_20260930.md:56（§四-1 的改判原文）",
                "work/decisions/decisions_20260929.md（§93 / 93.1：两颗牙 RED→WARN）"],
        })

    # ---- 逐条盖 `status`（表见 `RR_STATUS`；表里没有的 ⇒ 默认 OPEN，不猜它已被哪条裁定关闭）----
    for r in rr:
        st = RR_STATUS.get(r["id"])
        if st is None:
            r["status"] = "OPEN_no_d_ruling_yet"
            r["status_note"] = ("`RR_STATUS` 表里没有这个 id ⇒ 按纪律默认未决"
                                "（不得凭空写成已关闭）")
        else:
            r.update(st)
    return rr


# ---------------------------------------------------------------------------
# 裁定 78.2：顶层四元组 + `non_green[]`（ok=false 时的**解铃清单**）
# ---------------------------------------------------------------------------
# 为什么必须有 `non_green[]` 而不能只给 `ok`：D 在 §15-5 item 6 里点的 F1 事故就是
# 「`status` 直方图 {'PASS':18,'UNJUDGED':5}、RED=0，而 ok=false」⇒ 任何按 `RED` grep
# 的下游会把这次失败读成**干净**。所以非绿必须逐条落盘，且每条带三件事：
#   ① 它为什么不绿（`why`，取自 `observed.violations` 原文，不重写、不概括）；
#   ② 归谁修（`owner`）—— 本闸**无权**改 A2 的实现、也无权改 D 的锚，所以 owner 必须点名；
#   ③ 怎么修（`fix`）—— 写成可执行的一句话，不是「请检查」。
# owner/fix 用**显式表**而不是从判词里猜：猜出来的 owner 会把责任推给不在场的人
# （裁定 92.5 缺陷类 ⑱「为自圆其说而虚构依据」的同族）。表里没有的 id ⇒ owner 写
# `unmapped_see_check_note`，**不留空、不猜**。
NON_GREEN_OWNER_FIX = {
    "V-pi05-1_version_anchor": {
        "owner": "A2（环境装成侧）；若成因是**锚本身过期** ⇒ D（B2 不得自行改锚，M26 立的规矩）",
        "fix": ("按四条 blocking 逐条对：① 活体 `transformers.__version__` == 实测锚 `%s`；"
                "② lock 或活体 `direct_url.json` 里有定制分支 commit `%s`（分支 `%s`）；"
                "③ lerobot 的 π₀.₅ 硬校验真跑通过（返回 True）；④ `%s` 的 verdict == "
                "`%s` 且四个计数 = 812/812/0/0。**不要**去动 §8.1 的声明区间"
                "（`>=%s,<%s` 是 `declared_only`，裁定 78.8：以它判红就是本闸刚被裁掉的假红）"
                % (TRANSFORMERS_MEASURED_ANCHOR, TRANSFORMERS_GIT_COMMIT_ANCHOR[:12],
                   TRANSFORMERS_GIT_BRANCH_ANCHOR, A2_LOAD_VERIFICATION,
                   LOAD_VERIFY_VERDICT_ANCHOR, TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL))},
    "V-pi05-2_weights_identity": {
        "owner": "A2（权重下载与 receipt 的唯一责任线，裁定 39.2）",
        "fix": ("逐文件复算 sha256 与字节数并与 receipt 对齐；三件小文件必须在场且非空；"
                "份数 >= %d。若 receipt 只有 git blob sha1（HF 对非 LFS 文件的形态），"
                "本闸会在 <= %d MiB 的文件上复算 blob sha1 兜住，不需要 A2 补 sha256"
                % (WEIGHTS_MIN_FILES, GIT_BLOB_MAX_BYTES >> 20))},
    "V-pi05-3_channel_provenance": {
        "owner": "A2（receipt 的外部事实标记）；**载体需 D 点头** —— receipt 已被 sha256 钉死、不可重写",
        "fix": ("唯一解铃路径 = 另出一份 sidecar，把 receipt 里的外部来源事实（本轮实测为 "
                "`$.download.reported_size` 与 `$.verdict.license_ok`）显式标 "
                "`external_unverified`（裁定 36.4）。B2 **不静默放宽**标记词表、也**不静默判红** "
                "⇒ 词表口径已开 RR-B2-05 报 D；渠道混用本身**已按裁定 69/78.8 关闭**，"
                "不必重下（sidecar 复算成立即绿）")},
    "V-pi05-4_torch_stack_frozen": {
        "owner": "A2（装成侧）；口径归 D（lock 是否一律要求带 `+cu124`，RR-B2-02）",
        "fix": ("活体 `torch.__version__` 必须逐字 == `%s`、`torch.version.cuda` == `%s`；"
                "`resolve_dryrun.txt` 里不得出现 torch/torchvision/torchcodec 的 "
                "install/upgrade/uninstall（按锚值全新安装的那几行属认版本读法，见 RR-B2-01）。"
                "注意 lock 的 `torch==2.6.0` 对 CUDA 构建是**盲的**，事实源必须是活体探针"
                % (TORCH_ANCHOR, TORCH_CUDA_ANCHOR))},
    "V-pi05-5_transformers_pi05_ready": {
        "owner": "A2（装成侧）",
        "fix": ("lerobot 的 π₀.₅ 硬卫语句 `%s` 必须**真跑通过**（不是版本区间合规）；"
                "且装成记录必须能认出是**哪一次 build**（git commit 进 lock 的 direct-url 行，"
                "dryrun 是计划书、不算装成记录，裁定 34.1 / M35）" % PI05_TF_CHECK_PATH)},
    "V-pi05-6_manifest_selfconsistency": {
        "owner": "A2（manifest 的比对口径）；口径归 D（RR-B2-07）",
        "fix": ("交件自述 `env_usable=false` ⇒ 一律红（准入不得建立在自称不可用的交件上），"
                "但**成因必须分开写**：`metadata_only`（只有 dist-info 的 local version 段不同 "
                "⇒ 改 manifest 比对口径即可）vs `real_runtime_drift`（runtime 真不同 ⇒ 须 D 登记"
                "断点变更）。A2 重出 manifest 时把冻结栈比对口径统一到 runtime `__version__`"
                "（torch 另比 `torch.version.cuda`），两种口径分开记不混算（裁定 36.4）")},
    "V-pi05-7_control_hz_triple": {
        "owner": "A2（控制频率交件）；重采样方案的选择权归 D（RR-B2-08）",
        "fix": ("三元组必须自洽：`1/(timestep×decimation)` 与 `1/control_timestep` 与声明 Hz "
                "逐条对上；不得把 31.25 Hz 当契约值（裁定 45.1）；operative Hz 出 QC 区间 "
                "[29,31] 必须附**已被 D 选定**的重采样方案（B2 不替 D 选甲/乙/丙）")},
    "V-pi05-8_compat_dir_step_deletion": {
        "owner": "A2（兼容目录的构造）",
        "fix": ("只准删 `enabled` 为 false 的步骤，且要给可复核的代码级恒等证据；blob sha1 必须与"
                "参考文件相符；不得新增步骤 / 改保留步骤 config / 换序；大权重必须是**软链**回源"
                "目录而不是复制体（NFS 已用 94%，复制 14.47 GB 不可接受，且复制体会让「原始权重"
                "目录只读」无法证明，裁定 44.2）；被删步骤必须确实**不在**本机 lerobot registry")},
    "A0_teeth_current": {
        "owner": "B2（本闸自己）",
        "fix": ("改了判据就必须重跑 `--selftest`：`mutation_verdict.json` 的 `gate_build` 必须"
                "逐字等于当前脚本构建，且 `all_ok=true`。缺失 ⇒ UNJUDGED（不是 PASS）")},
    "A1_all_teeth_ran": {
        "owner": "B2（本闸自己）",
        "fix": "CHECKS_PI05 的八条牙必须全部出现在 `checks[]` 里（自检与现场共用同一条执行序列）"},
    "A2_inputs_stable_during_run": {
        "owner": "改写交件的那条线（本轮实测为 A2 在闸跑的过程中重写 lock）",
        "fix": "判定期间不得改写四份交件；确需改写 ⇒ 等闸跑完再改，然后**重跑**本闸（快照口径已写进产物）"},
    "A3_delegated_docs_normalized": {
        "owner": "B2（本闸自己）；原件属 B，**一字节不得动**",
        "fix": ("全部 `delegated_g1_g5_*.json` 都要有归一副本（id 非空且全局唯一、`ok` 与 `status` "
                "同源、前导空格已去），且原件 sha256 前后一致；台账还必须与不跟随符号链接的 "
                "`find -P -type f | wc -l` 对账成立（裁定 92.3-ii）")},
    "G1-G5_freeze": {
        "owner": "B（上游溯源闸 `scripts/b_env_provenance_guard.py`，B2 只读复用）",
        "fix": "冻结面此刻被破坏 ⇒ 按上游逐条 `violations` 修；B2 这一层只做**归一转录**，不代上游改判"},
    "G1-G5_a2env": {
        "owner": "A2（新环境的重建目录）；转录层归 B2",
        "fix": ("按上游逐条 `violations` 修。本轮已知的一条 WARN 成因 = A2 的重建目录缺 "
                "`requirements.eval.lock.txt`（**事实缺失的登记，不是违例**）⇒ A2 补件即消")},
    "G1-G5_freeze_teeth": {
        "owner": "B2（补牙的执行者）；牙本体在上游 B 的 `--selftest`",
        "fix": ("裁定 78.4 采①（补牙不降级）：B2 必须**亲自子进程复跑**上游 `--selftest` 并逐 G "
                "统计 `red_caught`；rc != 0 或五个 G 里任一个没有「能红」的变异体 ⇒ 红；"
                "没跑 ⇒ 弃权（不得记 PASS）")},
    "V0-V9_delegated": {
        "owner": "B（上游迁移不变量门禁，B2 只读复用）",
        "fix": ("牙在被转述的上游门禁上（`teeth_delegated_to_upstream`）⇒ **不得当独立闸引用**"
                "（裁定 78.4 末条）；非绿时按上游逐条修")},
}


# 转录层会把上游 guard 的**逐条** G 也作为独立 check 落进判词（形如
# `G2_rebuild_lockout_not_default[a2env]`）。那些 id 是**运行时生成**的（G×scope 的笛卡尔积，
# 本轮实测 10 条），不可能在上面的显式表里逐个枚举 ⇒ 用一条**声明出来的规则**解析，
# 而不是留 `unmapped`（本轮第一跑就有 1 条落了 unmapped：那是本闸自己的表不全，不是"无从归因"）。
# 规则本身写进产物（`non_green[].owner_rule`），让 D 能核这条规则对不对 —— 规则若不声明，
# 就等于"猜出来的 owner"（裁定 92.5 缺陷类 ⑱ 的同族）。
TRANSCRIBED_G_ID_RE = re.compile(r"^(G\d)_(?P<name>.+?)\[(?P<scope>[A-Za-z0-9_]+)\]$")
TRANSCRIBED_G_OWNER_BY_SCOPE = {
    "freeze": {
        "owner": "事实侧＝破坏冻结面的那条线（0928 两份 lock / persistent pin / base python / "
                 "numpy 遮蔽，逐条见 `observed.actual.violations`）；判据侧＝B（上游 guard，B2 只读复用）",
        "fix": ("按上游 `observed.actual.violations` 逐条修。B2 这一层**只转录不改判**"
                "（D→B2 §1.1）：即使认为上游判错了，也不就地翻案，而是开 RR 报 D"),
    },
    "a2env": {
        "owner": "事实侧＝A2（新环境的重建目录与 venv）；判据侧＝B（上游 guard 的文案）；"
                 "转录层＝B2",
        "fix": ("按上游 `observed.actual.violations` / `.warnings` 逐条修。本轮已知的一条 WARN "
                "成因＝A2 的重建目录只有 `requirements.lock.txt`、**没有** "
                "`requirements.eval.lock.txt`（属**事实缺失的登记**，不是违例）⇒ A2 补件即消。"
                "另一件已报 D 的事：这条 WARN 挂在 id 叫 `rebuild_lockout_not_default` 的检查下，"
                "而它真正登记的是「缺一份文件」⇒ **上游 id 的语义与它实际登记的事实不同名**"
                "（裁定 78.5 说的「极性/文案反了」，根因在上游文案，B2 无权改 B 的脚本）"),
    },
}


def _owner_fix_for(cid):
    """返回 `(owner, fix, rule_or_None)`。先查显式表，再走**声明过的**规则，都不中 ⇒ `unmapped`。"""
    hit = NON_GREEN_OWNER_FIX.get(cid)
    if hit:
        return hit.get("owner"), hit.get("fix"), None
    m = TRANSCRIBED_G_ID_RE.match(cid or "")
    if m:
        by_scope = TRANSCRIBED_G_OWNER_BY_SCOPE.get(m.group("scope"))
        if by_scope:
            rule = ("规则 `TRANSCRIBED_G_ID_RE`（`^(G\\d)_(.+?)\\[(scope)]$`）+ "
                    "`TRANSCRIBED_G_OWNER_BY_SCOPE[%s]`；匹配到 G=%s name=%s scope=%s"
                    % (m.group("scope"), m.group(1), m.group("name"), m.group("scope")))
            return by_scope["owner"], by_scope["fix"], rule
    return ("unmapped_see_check_note",
            "unmapped_see_check_note（`NON_GREEN_OWNER_FIX` 表与 `TRANSCRIBED_G_*` 规则都没命中"
            "这个 id ⇒ 按纪律不猜，读该条的 note/red_when，并把缺的 owner 补进表）",
            None)


# 请示单（RR）也要盖 `status`：三值纪律的同一逻辑 —— 一张「开着还是关着看不出来」的请示单，
# 会让后来者要么重复请示、要么把已被 D 裁掉的问题当未决问题继续判红。表里没有的 id ⇒
# 默认 `OPEN_no_d_ruling_yet`（**不猜**它已被哪条裁定关闭）。
RR_STATUS = {
    "RR-B2-01": {"status": "OPEN_no_d_ruling_yet",
                 "why_still_open": "D 尚未就「§39.1 的字面读法 vs 认版本读法」单独出裁定；"
                                   "本闸按认版本读法执行并**在产物里点名**（不静默）"},
    "RR-B2-02": {"status": "OPEN_no_d_ruling_yet",
                 "why_still_open": "lock 是否一律要求带 `+cu124` 属**口径决定**，归 D；与 RR-B2-07 同一决定"},
    "RR-B2-05": {
        "status": "CLOSED_by_ruling_96_2",
        "ruling": ("裁定 96.2（2026-09-30 12:0x）：**载体准** —— sidecar = B2 自己写入面内的一份新 JSON，"
                   "与被钉死的 receipt **同目录**、命名 `receipt_sidecar_external_unverified.json`，"
                   "内容只装「哪些字段是外部未核实事实 + 指向 receipt 的 `sha256[:12]` + `as_of`」，"
                   "**≤40 行、不新增牙、不改 receipt 一个字节**；**同时把 `V-pi05-3_channel_provenance` "
                   "这条 RED 降为 Ⅱ 类「登记不阻塞」**（它管的是外部事实的口径标注，不是控制 / 数据正确性）"),
        "how_closed": ("已落 `runs/vla/a2_env_pi05_sim_20260929/receipt_sidecar_external_unverified.json`"
                       "（实测 39 行，≤40 的上限；身份串不写在这里 —— 由本闸在 collect() 时点复算并落"
                       "`obs.external_sidecar_96_2.sha12`，避免代码里的散文身份过期，裁定 89.7）。"
                       "采信条件四条全部由本闸自己复算（`as_of` 在场 / 未改写 receipt / receipt sha 逐字相同 / "
                       "路径同一件）⇒ **引用 ≠ 采信**。`EXTERNAL_MARK_RE` 与两条判据的断言文本**一字未改**："),
        "what_did_not_change": ("标记词表没有放宽、反向违例（实测值塞进 external 块）照旧红、"
                                "渠道混用的四条复算照旧。**牙没有被蒙住**：sidecar 只对「sha 与本次复算值"
                                "逐字相同」的那一份 receipt 生效，而 M32 的世界里 receipt 是合成的、sha 不同 "
                                "⇒ M32 仍然 RED（这条正是同一个形态的变异体）"),
        "caliber_delta_this_round": ("落地前：V-pi05-3 = RED ⇒ `n_red=1` ⇒ 顶层 `ok=false`、退出码 1；"
                                     "落地后：那两条外部事实**已被显式标注** ⇒ 本条 PASS ⇒ `n_red=0` ⇒ "
                                     "`ok=true`、`admission` 标签仍是 **WARN**（两条 G1–G5 登记项照旧登记）、"
                                     "退出码 0。这是 RR-B2-09 改判（裁定 93）之后**第一次**顶层 `ok` 翻 true"),
        "reading_prohibition": ("裁定 96.2 的读法禁令：sidecar 落地**之前**的 `ok=false` 不得被任何线读成"
                                "「BC 被禁」（读成禁 = 又一次把 Ⅱ 类升成 Ⅰ 类，即 D 同型错误 #20 的同型复发；"
                                "**下位发现可直接引裁定 96.2 驳**）。BC 的硬闸是 `Tp5` 同源 + `bc_admission()` "
                                "AND 闸 verdict（C2 已落码），不是这一条"),
        "credit_note": "D 记功一次（裁定 96.2 原文）：维持判红、不自行放宽词表、照 90.2 的形状报上来",
        "b2_position_at_the_time_SUPERSEDED": (
            "裁定 36.4 的**标记词表**口径归 D。本轮实测：真实 receipt 的 "
            "`$.download.reported_size` 与 `$.verdict.license_ok` 两条外部事实"
            "在两种词表读法下都无标记 ⇒ V-pi05-3 判 RED（M32 钉住）。"
            "**B2 不静默放宽词表、也不静默判红**：修法归 A2（各一行），"
            "但**载体需 D 点头** —— receipt 已被 sha256 钉死不可重写，"
            "唯一解铃路径 = 另出一份 sidecar 显式标 `external_unverified`"),
        "superseded_note": ("上面这段是**请示当时的立场**，按「作废不删件」原字节保留（裁定 92.4）。"
                            "D 裁的结果与 B2 的请求一致（载体 = sidecar），差别只在**由谁写**："
                            "原立场写「修法归 A2（各一行）」，裁定 96.2 把写入面判给 **B2**"
                            "（因为 receipt 不可重写，而 sidecar 属 B2 的写入面）"),
    },
    "RR-B2-06": {
        "status": "CLOSED_by_ruling",
        "closed_by": "裁定 78.8（= D→B2 §15-5 item 1，附 C2 独立读码 "
                     "`lerobot/policies/pi05/modeling_pi05.py:576-584` 作第二重证据）+ 裁定 69.3",
        "what_changed": ("§8.1 的声明区间 `>=%s,<%s` 降为 `declared_only`（只登记、不判红）；"
                         "`required` 改为**四条 blocking**：① 实测版本 == 锚 `%s`；② 装成记录里有 "
                         "git commit `%s`（分支 `%s`）；③ lerobot 的 π₀.₅ 硬校验真跑通过；"
                         "④ `%s` = `%s` 且 812/812/0/0"
                         % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL, TRANSFORMERS_MEASURED_ANCHOR,
                            TRANSFORMERS_GIT_COMMIT_ANCHOR[:12], TRANSFORMERS_GIT_BRANCH_ANCHOR,
                            A2_LOAD_VERIFICATION, LOAD_VERIFY_VERDICT_ANCHOR)),
        "teeth_not_removed_proof": ("改判**没有**把牙拔掉：M59（PyPI 4.57.6 满足声明区间但卫语句拒绝）"
                                    "必须红、M60（同版本号、另一次 build）必须红、M61（自称 "
                                    "all_bitwise_equal 但 n_differ=3）必须红、M63（PyPI 的 4.53.3 "
                                    "版本号与锚逐字相同但无 check.py）必须红、M62（合规但核验件缺失）"
                                    "必须弃权；M34（与 A2 现场同形）必须绿 ⇒ 见 `mutation_verdict.json`"),
        "kept_in_verdict_because": ("这条 RR 留在产物里是为了钉住「**换判据不删记录**」：D 的锚被现场"
                                    "证伪这件事本身是一条证据，关闭它不等于抹掉它"),
    },
    "RR-B2-07": {"status": "OPEN_no_d_ruling_yet",
                 "why_still_open": ("「冻结栈漂移」的事实源（dist-info 元数据 vs runtime `__version__`）"
                                    "属口径决定，归 D。B2 已把它做成第 6 条牙 V-pi05-6，"
                                    "对 `env_usable=false` **一律判红**（不因成因是假红就放行），"
                                    "并要求判词点名成因类别（M36 `metadata_only` / M38 "
                                    "`real_runtime_drift`）⇒ 判据不依赖裁定结果，裁定只影响修法归属")},
    "RR-B2-09": {
        "status": "CLOSED_by_ruling_93",
        "closed_by": ("裁定 93 + D→B2 执行单 20260930 §四-1（原文：「与裁定 78.2 的四元组口径对齐："
                      "`ok` 是唯一失败判据、`UNJUDGED` 计入非绿、**WARN 不计失败但必须登记**」；"
                      "D 并点名「裁定 93.1 会把两颗牙从 RED 转成 WARN ⇒ 这条不修，C2 的主线臂会被"
                      "你的顶层 `ok` 二次判死」⇒ 优先级由 P1 提到 **P0.5**，与 T-B2-17 同批做掉）"),
        "what_changed": ("`ok` 收敛到唯一实现 `ok_of(n_red, n_unjudged, n_warn)` = "
                         "(n_red==0 且 n_unjudged==0)，口径标记 `%s`；`admission_granted` == `ok`；"
                         "`_normalize_guard_doc` 的归一副本 `ok` 改调同一个函数（两处同源）；"
                         "`EXIT['WARN']` 2 → **0**；顶层新增 `warn_registered_not_blocking` / "
                         "`admission_granted_criterion` / `exit_code_caliber` 三块"
                         % OK_CALIBER_MARKER),
        "what_did_not_change": ("`admission_of()` 一字未改（`admission` 仍是四值标签、WARN 一档保留 "
                                "⇒「必须登记」那一半落在标签 + `non_green[]` + 新登记块上）；"
                                "RED/UNJUDGED 的严格性一点没松；`--expect` 语义不变"),
        "teeth_not_removed_proof": ("改判自带一层牙：自检 `verdict_caliber` 的 O1–O5"
                                    "（O1 只加 WARN ⇒ 标签 WARN **且** ok=true；O2 只加 UNJUDGED ⇒ "
                                    "ok=false，防放宽过头；O3 有 RED ⇒ ok=false；O4 全 PASS ⇒ ok=true，"
                                    "防恒假；O5 同源牙：源码里必须真有 `ok_of(`、散文必须带口径标记、"
                                    "`EXIT['WARN']` 必须为 0）⇒ 见 mutation_verdict.json"),
        "superseded_position_kept_because": ("当时的 B2 立场（采①「计入更严」及其三条理由）保留在 "
                                             "`ruling_requests[]` 的 "
                                             "`b2_position_at_the_time_SUPERSEDED` 字段里，"
                                             "**不得当现行判据引用**；其中 (b)(c) 两条被 D 采纳为义务"
                                             "（标签不动 + 修法是消掉事实），只有 (a) 被推翻"),
        "kept_in_verdict_because": ("裁定 92.4：作废不删件、不改名。留着是为了钉住两件事 —— "
                                    "① B2 曾自采一个比 D 字面更严的**非字面读法**并点名上报"
                                    "（没有静默改判据）；② 那种加严的现实代价（上游一次合法的 "
                                    "RED→WARN 改判会被二次判死）⇒ 后来者若又想「顺手加严一层」，"
                                    "先读这一条与 O1–O5"),
    },
}


def _non_green_entries(rep):
    """把 `status != PASS` 的 check 逐条展开成 D 可一眼看清的解铃清单（裁定 78.2）。

    三条纪律：① `why` 取 `observed.violations` **原文**（不重写、不概括 —— 概括就是
    「用一个看起来能用的间接量替代真正要指的那个」，裁定 90.5 #16 同族）；② `owner`/`fix`
    只从**显式表**或**声明过的规则**取（转录层的逐条 G 是运行时生成的笛卡尔积，枚举不完
    ⇒ 用 `TRANSCRIBED_G_ID_RE` + `TRANSCRIBED_G_OWNER_BY_SCOPE` 解析，并把命中的规则原文
    写进 `owner_rule` 供 D 核）；两者都不中 ⇒ 写 `unmapped_see_check_note`（不猜、不留空）；③ 顺序按
    RED → UNJUDGED → WARN（严重度降序），同级按 id 字典序 ⇒ 输出稳定可对账。
    """
    order = {STATUS_RED: 0, STATUS_UNJUDGED: 1, STATUS_WARN: 2}
    out = []
    for c in sorted((x for x in rep.checks if x["status"] != STATUS_PASS),
                    key=lambda x: (order.get(x["status"], 9), x["id"])):
        o = c.get("observed")
        why = None
        if isinstance(o, dict):
            why = o.get("violations") or o.get("warning") or o.get("note")
        if why is None:
            why = o if isinstance(o, str) else c.get("note")
        owner, fix, owner_rule = _owner_fix_for(c["id"])
        out.append({
            "id": c["id"],
            "status": c["status"],
            "ok": c["ok"],
            "counts_as_non_green": c["counts_as_non_green"],
            "severity_rank": order.get(c["status"], 9),
            "why": why,
            "owner": owner,
            "fix": fix,
            # owner 是怎么定出来的：显式表命中 ⇒ None（表本身在脚本里可核）；
            # 规则命中 ⇒ 把规则原文写出来（不声明规则 = 猜 owner，裁定 92.5 缺陷类 ⑱ 同族）。
            "owner_rule": owner_rule,
            "red_when": c.get("red_when"),
            "ruling_ref": c.get("ruling_ref"),
            "required": c.get("required"),
        })
    return out


def _artifact_identity(p: Path) -> dict:
    """**落笔时刻重算**一份产物的身份（裁定 78.11 `citation_sha_as_of_discipline` +
    裁定 92.3「身份串必须由工具在落笔时刻生成，人不碰」）。不接任何缓存值、不手工转录。
    `n_lines` 用 `wc -l` 口径（换行符个数），与散文里的「N ln」一致；同时给
    `n_lines_splitlines` 与 `ends_with_newline`，两者不同就说明文件不以换行结尾（裁定 92.3）。
    """
    out = {"path": str(p), "exists": p.is_file()}
    if not p.is_file():
        out["note"] = "不存在 ⇒ 身份无从算（**不得**沿用早先 run 的值，也不得记成 0 字节）"
        return out
    raw = p.read_bytes()
    st = p.stat()
    out.update({
        "bytes": len(raw),
        "n_lines": raw.count(b"\n"),
        "n_lines_splitlines": len(raw.splitlines()),
        "ends_with_newline": raw.endswith(b"\n"),
        "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
        "sha1_12": hashlib.sha1(raw).hexdigest()[:12],
        "citation_algo": "sha256[:12]",
        "sha1_12_why": "只为让「算法错配」一眼可见，**不得被引用**（裁定 92.3）",
        "as_of_mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
        "read_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    return out


def _delegation_norm_block(delegated, out_dir: Path) -> dict:
    """裁定 78.3 的落盘证据：归一台账 + 副本目录的身份（**不重算归一，只登记产物**）。

    为什么不在这里重算：归一已经在 `normalize_all_guard_docs()` 里做过、并落了
    `A3_delegated_docs_normalized` 这条 check。这里只做一件事 —— 把**台账文件本身**的身份
    固定下来，好让 D 的文书能引到「哪一份台账、哪个 sha」。重算一遍会制造两个事实源
    （ADR-C-014 同型：被测对象与使用对象不是同一个）。
    """
    tally = delegated.get("norm") or {}
    ledger_p = out_dir / "normalized" / "NORMALIZATION_LEDGER.json"
    fc = (tally.get("crosscheck_find_type_f") or {})
    return {
        "ruling": "裁定 78.3（委托闸补 id + 去前导空格）/ 78.2（最小公共 schema）/ 92.3-ii（清单对账）",
        "originals_modified_by_b2": False,
        "originals_untouched_assertion": "台账里逐份记 sha256 before/after 并机器断言相等（不是散文声称）",
        "ledger_artifact": _artifact_identity(ledger_p),
        "normalized_dir": str(out_dir / "normalized"),
        "n_source_docs": tally.get("n_source_docs"),
        "n_normalized": tally.get("n_normalized"),
        "n_parse_failed": tally.get("n_parse_failed"),
        "n_checks_total": tally.get("n_checks_total"),
        "n_ids": tally.get("n_ids"),
        "ids_globally_unique": tally.get("ids_globally_unique"),
        "n_id_null_filled": tally.get("n_id_null_filled"),
        "n_id_whitespace_stripped": tally.get("n_id_whitespace_stripped"),
        "originals_all_untouched": tally.get("originals_all_untouched"),
        "layout_version": tally.get("layout_version"),
        "source_roots": tally.get("source_roots"),
        "d_finding_reconciliation": tally.get("d_finding_reconciliation"),
        "crosscheck_find_type_f": {k: fc.get(k) for k in
                                   ("identity_holds", "unexplained_differences",
                                    "n_source_docs_by_rglob", "n_source_docs_by_find_total",
                                    "n_normalized_by_ledger", "n_superseded_on_disk",
                                    "n_superseded_moved_this_round", "invariants",
                                    "caliber_note")},
        "d_finding_addressed": tally.get("d_finding_addressed"),
        "note": ("`n_*` 为 None 表示本轮没有可归一的产物（`--no-delegate` 或委派失败）⇒ "
                 "`A3_delegated_docs_normalized` 相应弃权（UNJUDGED），**不得**读成"
                 "「没有 id=null 问题」"),
    }


def _delegation_teeth_block(rep, out_dir: Path) -> dict:
    """裁定 78.4 的①（补牙不降级）：两层的**产物身份**与关键实测数，都从已落盘的证据取。

    甲层（判据层）= 本轮**亲自子进程复跑**上游 `scripts/b_env_provenance_guard.py --selftest`，
    逐 G 统计「有没有一条期望 RED 且实际 RED 的变异体」⇒ 产物
    `delegated_g1_g5_upstream_teeth.{json,log}`，判据是 check `G1-G5_freeze_teeth`。
    乙层（转录层）= 本闸 `--selftest` 的 T1–T11（喂合成 guard 产物给 `_transcribe_guard`）。
    两层都不碰 B 的脚本（只读复用，D→B2 §1.1），也不改写 B 的任何产物。
    """
    obs = {}
    for c in rep.checks:
        if c["id"] == "G1-G5_freeze_teeth":
            obs = c.get("observed") if isinstance(c.get("observed"), dict) else {}
    return {
        "ruling": "裁定 78.4（freeze 二选一 ⇒ B2 采①补牙，不采②降级）/ 裁定 27.1 / 86.6-3",
        "choice_taken": "①补牙（保留「闸」称谓）",
        "layers": {
            "criteria_layer_upstream_rerun": {
                "what": "B2 亲自子进程复跑上游 `--selftest`，逐行解析、逐 G 统计 red_caught",
                "check_id": "G1-G5_freeze_teeth",
                "artifacts": [_artifact_identity(out_dir / "delegated_g1_g5_upstream_teeth.json"),
                              _artifact_identity(out_dir / "delegated_g1_g5_upstream_teeth.log")],
                "upstream_script": obs.get("upstream_script"),
                "upstream_script_sha256_12": obs.get("upstream_script_sha256_12"),
                "upstream_script_lines": obs.get("upstream_script_lines"),
                "read_only_reuse": obs.get("read_only_reuse"),
                "modified_by_b2": obs.get("modified_by_b2"),
                "rc": obs.get("rc"), "n_ok": obs.get("n_ok"), "n_results": obs.get("n_results"),
                "n_rows_parsed": obs.get("n_rows_parsed"),
                "g_covered": obs.get("g_covered"),
                "per_g_caught_red_mutants": obs.get("per_g_caught_red_mutants"),
                "per_g_reverse_mutants": obs.get("per_g_reverse_mutants"),
                "every_g_has_a_caught_red_mutant":
                    obs.get("every_g_has_a_caught_red_mutant"),
                "why_not_ran": obs.get("why_not_ran"),
            },
            "transcription_layer_selftest": {
                "what": ("喂**合成的 guard 产物**给 `_transcribe_guard`：T1–T5 每个 G 各打一条 RED"
                         "（聚合必须红 + id 精确点到条）、T6 反向（全绿不得误报）、T7 前导空格、"
                         "T8 `check_id` 缺失不留 null、T9 三值集外必须弃权（只看上游 summary 会假绿）、"
                         "T10/T11 钉住上游自检 stdout 的覆盖解析器"),
                "where": "本闸 `--selftest` ⇒ `mutation_verdict.json` 的 `layers.transcription`",
                "n": 11,
            },
        },
        "freeze_gate_kind": ("gate_teeth_proven_this_round"
                             if obs.get("every_g_has_a_caught_red_mutant")
                             else "checklist_not_gate_see_G1-G5_freeze_teeth"),
        "note": ("`obs` 里的字段为 None 表示 `G1-G5_freeze_teeth` 弃权或没跑 ⇒ 此时 "
                 "`delegated_g1_g5_freeze` **不得**被当独立闸引用（裁定 78.4 的②自动生效）"),
    }


def _warn_registration(rep):
    """RR-B2-09 改判（裁定 93 / D→B2 §四-1）要求的**登记块**：WARN 不判失败，但必须登记。

    为什么单独成块、不只留在 `non_green[]` 里：改判后 `ok` 会是 true，而下游（C2 的闸、
    A2 的 BC 入口、D 的复核）在 `ok=true` 时**默认不再读** `non_green[]` ⇒ 若不把 WARN 连同
    "为什么不阻塞 / 谁来消 / 怎么消"一起摆在顶层，登记义务就等于被这次改判悄悄取消了
    （红线 `absence_of_measurement_is_not_measurement_of_absence` 的反向形态：
    「登记了但没人看得见」= 没登记）。这块同时是自检 O1 的取证面。
    """
    per = []
    for e in _non_green_entries(rep):
        if e["status"] != STATUS_WARN:
            continue
        per.append({"id": e["id"], "why": e["why"], "owner": e["owner"], "fix": e["fix"],
                    "owner_rule": e["owner_rule"], "required": e["required"],
                    "counts_as_non_green": e["counts_as_non_green"],
                    "counts_as_failure": False})
    return {
        "marker": OK_CALIBER_MARKER,
        "applies": bool(rep.n_warn),
        "n_warn": rep.n_warn,
        "warn_ids": [c["id"] for c in rep.checks if c["status"] == STATUS_WARN],
        "per_warn": per,
        "counts_as_failure": False,
        "why_not_blocking": (
            "裁定 78.2 的字面只规定两件事：「顶层 `ok` 是唯一失败判据」与「`UNJUDGED` 必须计入"
            "非绿」；**WARN 不在失败判据里**。B2 上一版把 WARN 也 AND 进 `ok=false`（RR-B2-09 的"
            "①，比 D 字面更严的非字面读法），已被 D 退回：裁定 93.1 会把两颗牙从 RED 转成 WARN，"
            "旧口径下 C2 的主线臂会被本闸的顶层 `ok` **二次判死**（D→B2 §四-1 原话）—— "
            "即一个非违例的登记项被下游读成不合格，正是 F1 事故的反向形态。"),
        "why_still_registered": (
            "「不计失败」≠「不用管」：`admission` 标签仍给 `WARN`、`non_green[]` 仍逐条列、"
            "本块逐条给 why/owner/fix、退出码为 0 但 stdout 仍打印 WARN 计数。"
            "消掉 WARN 的正确修法**始终是把那个事实消掉**（本轮 = A2 补一份 "
            "`requirements.eval.lock.txt`，成本 = 一次 pip freeze），不是把它从判据里挪走。"),
        "why_label_and_decision_differ": (
            "`admission` 是**标签**（登记世界状态，四值），`admission_granted` == `ok` 是**决定**"
            "（是否放行）。标签为 `WARN` 时两者故意不同：标签说「有一项事实缺失已登记」，"
            "决定说「这一项不构成失败」。两者并排落盘，谁都不许被当成对方读"
            "（裁定 78.3：`ok` 与 `status` 必须同源 —— 同源指的是**同一个函数算出来**，"
            "不是「两个字段必须相等」）。"),
        "exit_code_effect": (
            "EXIT['WARN'] = 0（改判前是 2）：WARN 不是失败 ⇒ 任何按 `rc != 0` 判失败的下游"
            "（含 CI 式包装、`&&` 串联的跑批）不得被一条非违例登记项二次判死。"
            "`--expect pass|red|unjudged` 的语义**不变**（它们比的是 `admission` 标签，不是 `ok`）。"),
        "ruling_ref": ("裁定 78.2（顶层四元组 + `ok` 唯一失败判据 + UNJUDGED 计入非绿）"
                       "+ 裁定 93 / D→B2 执行单 20260930 §四-1（RR-B2-09 改判：WARN 不计失败"
                       "但必须登记）"),
        "history_of_this_caliber": (
            "改判前的口径与其三条理由（B2 立场①「计入更严」）保留在 `ruling_requests[]` 的 "
            "RR-B2-09 条目里，`status=CLOSED_by_ruling_93`；作废不删件（裁定 92.4）。"),
    }


def build_verdict(ev, rep, root: Path, a2_dir: Path, out_dir: Path, venv: str, delegated):
    check_a1_all_teeth_ran(rep)          # 兜底：八条牙必须都真的跑过（见该函数注释）
    check_inputs_stable(ev, rep)         # 兜底：判定期间输入被并发改写 ⇒ 显式标出来
    adm = admission_of(rep)
    ext = {}
    rcp = ev.get("receipt") or {}
    if isinstance(rcp, dict):
        blk = rcp.get("external_unverified")
        if isinstance(blk, dict):
            ext = blk
        for k in ("license", "last_modified", "lastModified"):
            if isinstance(rcp.get(k), (str, int, float)) and k not in ext:
                ext.setdefault(k + "_UNMARKED_see_V-pi05-3", rcp[k])
    doc = {
        "spec": "π₀.₅ 新环境的可复现性准入闸（D→B2 执行单 §1 + 增补十六 裁定 39.1）",
        "verdict_kind": "b2_env_admission_pi05",
        "gate_build": _sha12(Path(__file__)),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "scripts/b2_env_admission_pi05.py（B2 数据与判据线）",
        "out_dir": str(out_dir),
        "input_snapshot_taken_at": ev.get("snapshot_taken_at"),
        "input_snapshot_note": ("四份交件在 collect() 时点**一次性快照**（sha256 + mtime 见 inputs.files），"
                                "判定期间不重读文件；若期间被并发改写，`A2_inputs_stable_during_run` "
                                "会显式判黄（19:04:54 实测到过 A2 在闸跑的过程中重写 lock）"),
        "inputs": {
            "root": str(root), "a2_dir": str(a2_dir), "a2_dir_exists": ev.get("a2_dir_exists"),
            "venv": str(venv), "live": ev.get("live"), "verify_sha256": ev.get("verify_sha256"),
            "files": ev.get("files"), "missing": ev.get("missing"),
            "accepted_venvs": ACCEPTED_VENVS,
        },
        "delegation": {
            "g1_g5": {"script": "scripts/b_env_provenance_guard.py",
                      "modes": {"freeze": "判冻结面此刻是否完好（与 A2 交件无关，总是可判）",
                                "a2env": "判 A2 的新环境（仅当交件齐 + venv 存在才委派，否则弃权）"},
                      "artifacts": ["delegated_g1_g5_freeze.json", "delegated_g1_g5_a2env.json"],
                      "ran": bool(delegated.get("g")),
                      "verdict": ((delegated.get("g") or {}).get("summary") or {}).get("verdict")},
            "v0_v9": {"script": "scripts/b_env_migration_invariance_check.py",
                      "artifact": "delegated_v0_v9.json",
                      "ran": bool(delegated.get("v")),
                      "verdict": ("PASS" if (delegated.get("v") or {}).get("ok") else "FAIL")
                                 if delegated.get("v") else None},
            # ---- 裁定 78.3：归一副本 + 台账（原件一字节不动）----
            "g1_g5_normalization": _delegation_norm_block(delegated, out_dir),
            # ---- 裁定 78.4 的①：补牙（不降级）——两层，产物都在本 out_dir----
            "g1_g5_teeth": _delegation_teeth_block(rep, out_dir),
            "v0_v9_teeth_status": ("teeth_delegated_to_upstream（牙在被转述的 B 门禁 "
                                   "`V3: n_mutations=15 n_caught=15` 上）⇒ **不得当独立闸引用**"
                                   "（裁定 78.4 末条 / D→B2 §15-5 item 5）"),
        },
        # ---- 裁定 78.2 的顶层四元组 + RR-B2-09 改判后的 `ok`（裁定 93 / D→B2 §四-1）----
        # D 的原话：「**顶层 `ok` 是唯一失败判据**；`UNJUDGED` 必须计入非绿；**WARN 不计失败
        # 但必须登记**」，并要求「产物顶层写 `n_red / n_warn / n_unjudged / ok` 四元组」。
        # F1 事故（RED=0 却 ok=false，被按 `RED` grep 的下游读成干净）就是只给布尔造成的 ⇒
        # 三个计数必须与 `ok` 并排落盘，且 `ok` 的判据写成散文可核的一句（`ok_criterion`），
        # 并与代码**同源**（`ok_of()` 是唯一实现，本闸顶层与归一副本都调它）。
        "ok": ok_of(rep.n_red, rep.n_unjudged, rep.n_warn),
        "n_red": rep.n_red,
        "n_warn": rep.n_warn,
        "n_unjudged": rep.n_unjudged,
        "n_pass": rep.n_pass,
        "ok_criterion": OK_CRITERION,
        # RR-B2-09 改判要求的那一半：「WARN 不计失败**但必须登记**」的登记载体（见该函数注释）。
        "warn_registered_not_blocking": _warn_registration(rep),
        "non_green": _non_green_entries(rep),
        "non_green_note": ("`ok=false` 时**必须**读这块（逐条带 why/owner/fix），不得只看 `ok` "
                           "一个布尔，也不得只按 `RED` grep（UNJUDGED 同样让 ok=false，"
                           "裁定 78.2 F1）。RR-B2-09 改判后（裁定 93 / D→B2 §四-1）"
                           "**WARN 不再让 `ok=false`** ⇒ 本块里的 WARN 条目属「已登记、不构成失败、"
                           "但要人消掉」那一类，读法见顶层 `warn_registered_not_blocking`；"
                           "`ok=true` 时本块**仍可能非空**（就是那些 WARN），不是矛盾。"
                           "`counts_as_non_green` 是**逐条**字段、只覆盖 RED+UNJUDGED，"
                           "与顶层 `ok` 改判后**同源**（不再有「差一个 WARN」的分裂）。"),
        "admission": adm,
        "admission_granted": ok_of(rep.n_red, rep.n_unjudged, rep.n_warn),
        "admission_granted_criterion": (
            "`admission_granted` == 顶层 `ok` == `ok_of(n_red, n_unjudged, n_warn)`（放行**决定**）；"
            "`admission` 是四值**标签**（登记世界状态）。两者在标签为 `WARN` 时**故意不同**，"
            "差别见 `warn_registered_not_blocking.why_label_and_decision_differ`。"
            "改判前这里写的是 `admission == 'PASS'`（即 WARN 也挡放行）⇒ 已作废，"
            "历史与理由见 `ruling_requests[]` 的 RR-B2-09（`CLOSED_by_ruling_93`，作废不删件）。"),
        # 退出码也是判据的一部分（下游常只看 rc）⇒ 与 `ok` 同源落盘，不留给读者去猜。
        "exit_code_caliber": {
            "map": dict(EXIT),
            "of_this_run": EXIT.get(adm, 1),
            "warn_is_zero_because": ("RR-B2-09 改判（裁定 93 / D→B2 §四-1）：WARN 不是失败 ⇒ "
                                     "任何按 `rc != 0` 判失败的下游（`&&` 串联、CI 式包装、"
                                     "`check_returncode`）都不得被一条非违例的登记项二次判死。"
                                     "改判前 `EXIT['WARN']` 是 2。"),
            "registration_is_not_lost_because": ("`admission` 标签仍是 `WARN`、"
                                                 "`warn_registered_not_blocking` 逐条落盘、"
                                                 "stdout 仍打印 WARN 计数与逐条 id"),
            "expect_flags_unchanged": ("`--expect pass|red|unjudged` 比的是 `admission` **标签**"
                                       "（不是 `ok`）⇒ 显式要求标签必须是 PASS 的调用方在 WARN 世界"
                                       "仍拿到 rc=1，那是调用方自己加严，与本条口径无关"),
        },
        "summary": {"total": len(rep.checks), "pass": rep.n_pass, "warn": rep.n_warn,
                    "red": rep.n_red, "unjudged": rep.n_unjudged, "verdict": adm,
                    "ok": ok_of(rep.n_red, rep.n_unjudged, rep.n_warn),
                    "ok_caliber_marker": OK_CALIBER_MARKER},
        "checks": rep.checks,
        "baseline_constants": {
            "lerobot_anchor": LEROBOT_ANCHOR, "torch_anchor": TORCH_ANCHOR,
            "torch_cuda_anchor": TORCH_CUDA_ANCHOR,
            "transformers_bound": ">=%s,<%s" % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL),
            # 裁定 78.8：上面那个 `transformers_bound` 是**上游 extra 的声明**，
            # 属 `declared_only`、**不进 blocking**。真正判红的是下面这一组实测锚。
            # 两个都留在产物里（不删声明值），并显式写清谁是判据、谁只是登记 —— 否则
            # 后来者会把「声明区间」当硬界用（D 的第 15 号同型错误：把软边界当硬界）。
            "transformers_bound_declared_only": {
                "bound": ">=%s,<%s" % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL),
                "source": "`importlib.metadata.requires('lerobot')` 的 extra `transformers-dep`",
                "status": "declared_only_not_blocking",
                "ruling_ref": "裁定 78.8 / 裁定 69（D→B2 §15-5 item 1）",
                "why_not_blocking": ("满足该区间的 PyPI 4.57.6 被 lerobot 的 π₀.₅ 硬校验**拒绝**"
                                     "（A2 实测 `ValueError: An incorrect transformer version is "
                                     "used`）⇒ 以声明下界判红 = 对合规环境判红（假红）"),
            },
            "transformers_measured_anchor": TRANSFORMERS_MEASURED_ANCHOR,
            "transformers_git_commit_anchor": TRANSFORMERS_GIT_COMMIT_ANCHOR,
            "transformers_git_branch_anchor": TRANSFORMERS_GIT_BRANCH_ANCHOR,
            "pi05_tf_check_path": PI05_TF_CHECK_PATH,
            "load_verification": {"path": A2_LOAD_VERIFICATION,
                                  "verdict_anchor": LOAD_VERIFY_VERDICT_ANCHOR,
                                  "n_tensors_anchor": LOAD_VERIFY_N_TENSORS_ANCHOR,
                                  "required_counts": "n_compared == n_bitwise_exact == %d、"
                                                     "n_differ == 0、"
                                                     "n_model_keys_not_covered_by_ckpt == 0"
                                                     % LOAD_VERIFY_N_TENSORS_ANCHOR},
            "channel_sidecar": {"path": A2_CHANNEL_SIDECAR,
                                "top_level_expected": CHANNEL_TOP_LEVEL_MIXED,
                                "policy": "引用 ≠ 采信：sidecar 自述的四件事由本闸自己复算（M64/M65 钉住）"},
            "tf_blocking_cause_keys": [TF_CAUSE_VERSION, TF_CAUSE_COMMIT, TF_CAUSE_GUARD,
                                       TF_CAUSE_LOADVER],
            "torch_stack": list(TORCH_STACK), "weights_min_files": WEIGHTS_MIN_FILES,
            "weights_small_required": list(WEIGHTS_SMALL_REQUIRED),
            "channels_allowed": list(CHANNELS_ALLOWED),
            "forbidden_venv_substr": list(FORBIDDEN_VENV_SUBSTR),
        },
        "ruling_requests": collect_ruling_requests(rep, ev),
        # 裁定 36.4：外部来源事实单独成块，**不与本机实测同表**
        "external_unverified": ext or None,
        "external_unverified_note": ("本块内全部是外部来源事实（上游 license / lastModified / 他人显存报告），"
                                     "**不得**与本文件 `checks[].observed` 里的本机实测值并列引用或混算"
                                     "（裁定 36.4）。本机实测只在 `checks[]` 与 `inputs.files` 里。"),
        "teeth": {
            "mutation_artifact": str(out_dir / "mutation_verdict.json"),
            "requirement": "每条 check 都必须能被一个**具体变异**打红；变异结果一并落盘（D→B2 §1.3）",
            "n_mutations_required": len(MUTATIONS),
            "layers": {
                "world": {"n": len(MUTATIONS),
                          "what": "合成 A2 交付世界（`_mk_world`）+ 八条 π₀.₅ 牙 + A0/A3 等装配判据",
                          "ids": "M1…M%d（见 mutation_verdict.json 的 mutations[]）" % len(MUTATIONS)},
                "transcription": {"n": N_TRANSCRIPTION_TEETH,
                                  "ids": ["T%d" % i for i in range(1, N_TRANSCRIPTION_TEETH + 1)],
                                  "what": "喂合成 guard 产物给 `_transcribe_guard`（裁定 78.4 的①·乙层）"},
                "meta_specificity": {"n": N_META_SPECIFICITY_TEETH,
                                     "ids": list(META_SPECIFICITY_IDS),
                                     "what": ("`_specificity_of` **自己**的牙（裁定 86.6-3 要求「证明"
                                              "本身必须由机器元判据看守」⇒ 元判据也必须被证明会判 "
                                              "False）：T12 未声明附带翻动⇒False、T13 已声明⇒True"
                                              "（防恒假）、T14 翻不动目标牙⇒False、T15 全局作用域必须"
                                              "回 None 而不是 True（防假绿）")},
                "assembly": {"n": 1, "ids": ["A1_missing_tooth"],
                             "what": "判词装配层：漏跑一条牙必须红、八条齐全时必须不出现（防恒红）"},
                "baseline": {"n": 1, "ids": ["baseline"],
                             "what": "干净合成世界里八条牙必须全绿（否则后面的「变红」没有意义）"},
                "normalization": {"n": N_NORMALIZATION_TEETH,
                                  "ids": list(NORMALIZATION_TEETH_IDS),
                                  "target": "A3_delegated_docs_normalized",
                                  "what": ("归一台账层：`A3`（清单件必须与不跟随符号链接的 "
                                           "`find -P -type f | wc -l` 对账，裁定 92.3-ii）**自己**的牙。"
                                           "N1 = `normalized/` 里多摆一份游离的有效副本（放在布局 v2 "
                                           "的位置，v1→v2 的顶层移动步骤抓不到）⇒ 不变式 (ii)「台账 vs "
                                           "磁盘」必须红、判词点名「台账漏登或多登」；N2 = **反向**"
                                           "（干净世界 + 没有 D 点名的作用域 ⇒ `matches_d_count` 记 "
                                           "`None`、A3 必须 PASS：「没测到」不得被读成「不合格」）；"
                                           "N3 = 造一个恰名 `%s` 的作用域但只放 2 份 ⇒ 与 D 的 %d 份 / "
                                           "%d 条**对不上账**、A3 必须红，且 `identity_holds` 仍为 True"
                                           "（红只来自对账，不是顺带咬了 find 不变式）"
                                           % (D_FINDING_SCOPE_DIR, D_FINDING_N_DOCS,
                                              D_FINDING_N_CHECKS)),
                                  "isolation": ("三条牙各**恰好 1 条违例**（牙内部的作用面，同 M66 的 "
                                                "`exact_viol`，裁定 86.6-3 的第三维）；不用 `_mk_world`"
                                                "（A3 的证据面就是 out_dir/`normalized/` 本身）"),
                                  "why_added_now": ("此前 `A3` 一颗变异牙都没有 ⇒ 按红线 "
                                                    "`tooth_must_be_mutant_proven`（裁定 27.1）它等于"
                                                    "没有闸；本轮它的第一版口径真的写错了（拿「本轮移入数」"
                                                    "去对**跨轮累积**的旧副本数 ⇒ 第二轮必假红），自检里"
                                                    "没有任何一颗牙挡得住，假红一路写进正式产物")},
                "verdict_caliber": {"n": N_VERDICT_CALIBER_TEETH,
                                    "ids": list(VERDICT_CALIBER_TEETH_IDS),
                                    "target": "ok_of / admission_of / EXIT（顶层判据本身）",
                                    "caliber_marker": OK_CALIBER_MARKER,
                                    "ruling": ("裁定 78.2（`ok` 是唯一失败判据 + UNJUDGED 计入非绿）"
                                               "+ 裁定 93 / D→B2 执行单 20260930 §四-1"
                                               "（RR-B2-09 改判：**WARN 不计失败但必须登记**）"),
                                    "what": ("顶层口径层 O1–O5：O1 只加 WARN ⇒ `admission` 标签仍是 "
                                             "`WARN` 而 `ok=true`（改判的正向钉；旧口径在这里给 "
                                             "false ⇒ 裁定 93.1 的 RED→WARN 会被本闸二次判死）；"
                                             "O2 只加 UNJUDGED ⇒ `ok=false`（**防放宽过头**）；"
                                             "O3 WARN+RED ⇒ 标签 `RED`、`ok=false`（WARN 不得稀释 "
                                             "RED）；O4 全 PASS ⇒ `ok=true`（**防恒假**）；"
                                             "O5 **同源牙**：`inspect.getsource` 证明 `build_verdict` "
                                             "与 `_normalize_guard_doc` 都真的调 `ok_of(`、旧的 "
                                             "`adm == \"PASS\"` 两处写法已消失、`OK_CRITERION` 与 "
                                             "`ok_of.__doc__` 都带口径标记、`EXIT['WARN']==0` 而 "
                                             "RED/UNJUDGED 非 0、`admission_of` 仍有 WARN 一档、"
                                             "判词仍带 `warn_registered_not_blocking` 登记块"),
                                    "isolation": ("不用 `_mk_world`（被测对象是判据函数本身，用合成 "
                                                  "`Report` 造计数组合）⇒ 不与世界层/归一层互相污染；"
                                                  "O5 的源码探针只读，不改任何文件"),
                                    "why_added_now": ("RR-B2-09 改判（裁定 93 / D→B2 §四-1）之前，"
                                                      "顶层 `ok` 的口径**一颗牙都没有**：它从第一版起"
                                                      "就是一个写在 `build_verdict` 里的字面表达式，"
                                                      "改判它不需要任何证明 ⇒ 按红线 "
                                                      "`tooth_must_be_mutant_proven`（裁定 27.1）"
                                                      "「改判本身也是判据」，无牙的改判等于一次"
                                                      "无人看守的口径变更（下一版可以悄悄改回去，"
                                                      "而悄悄加严与悄悄放宽都会以『已验证』的形状"
                                                      "活下来，裁定 86.6-3 同族）")},
                "criteria_layer_upstream_rerun": {
                    "n": "上游自己的 12 条（G1×3/G2×1/G3×3/G4×1/G5×3，含 2 条反向）",
                    "where": "正式判定里的 check `G1-G5_freeze_teeth`，不在本闸自检里跑",
                    "artifacts": ["delegated_g1_g5_upstream_teeth.json",
                                  "delegated_g1_g5_upstream_teeth.log"]},
            },
            # ↑ 上面 `layers` 里还有一层 `verdict_caliber`（O1–O5），写在 `normalization` 之后：
            #   它是 RR-B2-09 改判（裁定 93 / D→B2 §四-1）自带的牙，测的是**顶层判据本身**
            #   （`ok_of` / `admission_of` / `EXIT`），不是世界状态、不是转录、也不是台账。
            "layers_why_split": ("裁定 78.4 / 27.1 / 86.6-3：各层的**证明对象不同**，含糊成一个总数"
                                 "就等于把「哪一层证明了什么」抹掉。世界层证明八条 π₀.₅ 牙在合成世界上"
                                 "能红也能不红；转录层证明「上游把某个 G 判红时 B2 这一层会跟着红、且 id "
                                 "精确点到条」；装配层证明「漏跑一条牙会被兜底判红」（19:0x 的真实事故）。"
                                 "特异性元判据层证明「上面那些变异体是**精确**翻动目标牙的，不是碰巧红了」。"
                                 "归一台账层证明「看守台账-磁盘对账的那条 check 自己会红」——它是唯一"
                                 "一层**不测世界状态、只测本闸产物**的牙（裁定 92.3-ii）。"
                                 "口径层（O1–O5）证明「顶层 `ok` / `admission` 标签 / 退出码三者的口径"
                                 "就是散文里写的那一个，且四处调用点同源」——它是唯一一层**不测世界、"
                                 "也不测产物，只测判据函数本身**的牙（RR-B2-09 改判后新装，"
                                 "裁定 93 / D→B2 §四-1）。"
                                 "甲层（判据层：亲自复跑上游 `--selftest`）**不在自检里**（要真起子进程），"
                                 "它在正式判定里跑并落 `delegated_g1_g5_upstream_teeth.{json,log}`，"
                                 "其 stdout 解析器由转录层的 T10/T11 钉住（否则那颗牙自己是恒真闸）。"),
            "n_rows_expected_in_mutation_verdict": (1 + 1 + N_TRANSCRIPTION_TEETH
                                                    + N_META_SPECIFICITY_TEETH
                                                    + N_NORMALIZATION_TEETH
                                                    + N_VERDICT_CALIBER_TEETH + len(MUTATIONS)),
            "n_rows_expected_breakdown": ("1 条 baseline + 1 条 A1 装配层 + %d 条转录层 T + %d 条"
                                          "特异性元判据 T + %d 条归一台账层 N + %d 条口径层 O + "
                                          "%d 条世界层 M（改判前是 86 条，本轮 +5 = %d 条）"
                                          % (N_TRANSCRIPTION_TEETH, N_META_SPECIFICITY_TEETH,
                                             N_NORMALIZATION_TEETH, N_VERDICT_CALIBER_TEETH,
                                             len(MUTATIONS),
                                             1 + 1 + N_TRANSCRIPTION_TEETH
                                             + N_META_SPECIFICITY_TEETH + N_NORMALIZATION_TEETH
                                             + N_VERDICT_CALIBER_TEETH + len(MUTATIONS))),
            "counts_are_declarations_not_measurements": (
                "本块的计数是**声明**（由常量与 `len(MUTATIONS)` 算出）；实测计数在 "
                "`mutation_verdict.json` 的 `layers` 与 `n_mutations` 里。两者**已经不止靠 "
                "`A0_teeth_current` 的 gate_build 间接对上**：自检产物自己带一块 "
                "`layer_counts_declared_vs_measured`（逐层 declared vs measured + `mismatch`），"
                "且**不一致就让 `all_ok=false`** ⇒ `A0_teeth_current` 会判红（裁定 92.3-ii 的同族"
                "纪律用在自检产物自己身上：数字并排放着、差值没人解释 = 没对账）。此外 "
                "`gate_build` 必须逐字等于当前脚本构建、`all_ok` 必须为 true，否则判红/弃权"
                "（M18 钉住「改了判据没重跑自检」）。"),
            "specificity": {
                "ruling": ("裁定 86.6-3 `mutant_specificity_required`（挂在红线 "
                           "`tooth_must_be_mutant_proven` 之下）"),
                "requirement": ("登记的变异体**不是**证明：每个变异体必须被实测证明「精确翻动目标牙、"
                                "且只翻动目标牙」；未声明的附带翻动 ⇒ `all_ok=false`。而这个元判据"
                                "**本身必须有牙**（%s 四条，裁定 27.1：从没咬过的守卫等于没有守卫）："
                                "T12 喂「未声明的附带翻动」要求判 False、T13 喂「已声明的」要求判 True"
                                "（防恒假）、T14 喂「翻不动目标牙」要求判 False、T15 要求全局作用域目标"
                                "回 `None`（显式声明不适用）而**不是** `True`（防假绿）"
                                % "/".join(META_SPECIFICITY_IDS)),
                "two_halves": ("`must_contain` 钉的是**成因键**（红在哪一条 blocking 上），本判据钉的是"
                               "**作用面**（只红了那一条）。两者是特异性的两半：只有前者时，"
                               "「已验证」仍能以文书形态活下来（裁定 86.6-3 的原话）"),
                "declared_collateral_table": MUTATION_COLLATERAL,
                "declared_collateral_discipline": (
                    "一条附带翻动必须有**物理成因**（同一个世界改动同时违反了另一条判据）并写进 "
                    "`MUTATION_COLLATERAL` 的 `why`；写不出成因的不许声明，去改变异体构造让它隔离"
                    "（裁定 78.1 `mutant_construction_isolation`）"),
                "global_targets_declared_not_applicable": list(SPECIFICITY_GLOBAL_TARGETS),
                "where": "mutation_verdict.json 的 `specificity` 块与 `mutations[].specificity`",
            },
        },
        "red_conditions": [
            "任一 V-pi05-1…8 或委派的 G/V 判 RED",
            "lerobot 实际装成版本 != 两套已验收 venv 的实测值（点名包与版本）",
            # 裁定 78.8：这一行原来写的是「< 声明下界 ⇒ 红」，**已被 D 改判**。
            # 现在逐条写四条 blocking（与 `check_v_pi05_1` 的判据同源，不另立口径）。
            "transformers 缺失；或**四条 blocking** 任一不中：① [%s] 活体实测版本 != 实测锚 `%s`"
            "（M59：装了满足声明区间的 PyPI 4.57.6 也红）；② [%s] 装成记录里没有 git commit `%s`"
            "（分支 `%s`）或活体 commit 与之不符（M60：同版本号、另一次 build ⇒ 红）；"
            "③ [%s] lerobot 的 π₀.₅ 硬校验不是 True（M63：PyPI 的 4.53.3 版本号与锚逐字相同，"
            "但没有定制分支的 check.py ⇒ 红）；④ [%s] `%s` 的 verdict != `%s` 或四个计数"
            "（%d/%d/0/0）任一不符（M61：**自称** all_bitwise_equal 但 n_differ=3 ⇒ 红，"
            "判据读的是计数不是那句自述）；外加「实测已装但产物里查不到该版本」（裁定 34.1）"
            % (TF_CAUSE_VERSION, TRANSFORMERS_MEASURED_ANCHOR, TF_CAUSE_COMMIT,
               TRANSFORMERS_GIT_COMMIT_ANCHOR[:12], TRANSFORMERS_GIT_BRANCH_ANCHOR,
               TF_CAUSE_GUARD, TF_CAUSE_LOADVER, A2_LOAD_VERIFICATION,
               LOAD_VERIFY_VERDICT_ANCHOR, LOAD_VERIFY_N_TENSORS_ANCHOR,
               LOAD_VERIFY_N_TENSORS_ANCHOR),
            "渠道 sidecar 的**复算**不成立（裁定 78.8 item 2 的闭合块）：① receipt 的 sha256 与 sidecar "
            "记的不符（= 那份闭合指的不是这份 receipt，ADR-C-014 同型，M65）；② sidecar 顶层自称 "
            "`%s` 但逐文件记录里只有 1 个渠道、或双向查失真（M64：mixed 不诚实）；③ sidecar 自己的 "
            "C1–C5 有非 true、或 3/3 自检不成立；④ 逐文件覆盖有差集（存在既不在 receipt 也不在 "
            "sidecar 的文件）" % CHANNEL_TOP_LEVEL_MIXED,
            "活体 torch.__version__ != %s 或 torch.version.cuda != %s" % (TORCH_ANCHOR, TORCH_CUDA_ANCHOR),
            "resolve_dryrun.txt 里出现 torch/torchvision/torchcodec 的 install/upgrade/uninstall",
            "任一权重文件 sha256 或字节数与 receipt 不符；三件小文件任一缺失或为空；份数 < %d" % WEIGHTS_MIN_FILES,
            "下载通道无留痕；外部事实未标 external_unverified；或实测值被塞进 external_unverified 块",
            "mutation_verdict.json 缺失（⇒ UNJUDGED）/ all_ok=false / gate_build 与当前构建不符（⇒ RED）",
            "A2 的 env_manifest.json 自相矛盾（env_usable 与 assertions/frozen_stack_drift 不符），"
            "或自述 `env_usable=false`（**无论成因**：真漂移 / 只有 dist-info 元数据的 local version "
            "段不同 / 成因无从复核）",
            "控制频率三元组不自洽（1/(timestep×decimation) 或 1/control_timestep 与声明 Hz 不符）、"
            "或把 31.25 Hz 当契约值（裁定 45.1）、或 operative Hz 出 QC 区间 [29,31] 且无重采样方案",
            "兼容目录删掉了 `enabled` 非 false 的步骤 / 删除无代码级等价证据 / blob sha1 与参考文件不符 / "
            "新增步骤或改保留步骤 config 或换序 / 大权重是复制而非软链 / 被删步骤其实存在于本机 lerobot registry",
        ],
        "not_red_conditions": [
            "resolve_dryrun 只新增 transformers（区间内）而不动 torch 栈 ⇒ 必须绿（M7，防恒红）",
            "lock 的 `torch==2.6.0` 不带 `+cu124` ⇒ **不是**违例：lock 口径对 CUDA 构建是盲的，"
            "事实源是活体探针（照搬 G3 的 +cu124 规则到 lerobot 世系会造假红）",
            "盘上多出 receipt 未声明的缓存/软链文件 ⇒ 只 WARN，不红",
            "`summary` 之外的非判据字段（generated_at / gate_build / 路径）不同 ⇒ 不红",
            "A2 的 env_manifest.json 里 `differing_packages` 非空但都不在冻结栈"
            "（transformers / mujoco / scipy 等 A2 有意引入的）且 `frozen_stack_drift` 为空、"
            "`env_usable=true` ⇒ 必须绿（M37）：本条牙判的是**冻结栈**与**自洽性**，不是「有无差异」",
            "控制频率交件里 `as_is.control_hz = 50.0`（**描述现状**、且自述 `in_qc_band_29_31=false`）"
            "⇒ 不红：只有被声明为「要用」的 operative 值才受 QC 区间约束（M46 反向钉住）",
            "兼容目录只删了 `enabled=false` 的步骤、且给出了可复核的代码级恒等证据 ⇒ 必须绿（M51）；"
            "压根没有兼容目录 ⇒ UNJUDGED 而不是绿（M52）",
            # ---- 裁定 78.8 之后必须**显式**写进「不红条件」的两条（否则改判会被读成放宽）----
            "transformers 实测 `%s` **低于** §8.1 的声明下界 `%s`，但四条 blocking 全中"
            "（版本 == 实测锚 / lock 里有锚 commit / π₀.₅ 卫语句 True / 812-812-0-0）⇒ **必须绿**"
            "（M34，与 A2 现场同形；声明区间是 `declared_only`，拿它判红就是 D 已裁掉的假红）。"
            "反过来，满足声明区间的 PyPI 4.57.6 **必须红**（M59）⇒ 改判没有把牙拔掉"
            % (TRANSFORMERS_MEASURED_ANCHOR, TRANSFORMERS_FLOOR),
            "渠道混用（顶层 `%s`）且 sidecar 的四件复算全部成立 ⇒ **必须绿、且不必重下**"
            "（裁定 69 / 78.8 item 2 / D→B2 §15-5 item 2：A2 的 receipt 已有逐文件渠道记录，"
            "只是顶层 `channel=None`；M31 是这条的反向变异，用 A2 真实 receipt 的完整结构证明"
            "「判红」不是因为 receipt 结构不合本闸的想象）" % CHANNEL_TOP_LEVEL_MIXED,
        ],
        "abstain_discipline": ("证据缺失一律 UNJUDGED（ok=null），**不得**降级成 PASS，也不得升级成最重失效标签"
                              "（裁定 14 的同型纪律 + A→B 三值移交单：判据写 `is False`，不写 `is not True`）。"
                              "⇒ A2 未交件时本闸输出 UNJUDGED_evidence_missing，`admission_granted=false`。"),
    }
    return doc


def print_verdict(doc, quiet=False):
    if quiet:
        return
    s = doc["summary"]
    print("=" * 100)
    print("B2 线：π₀.₅ 新环境可复现性准入闸  gate_build=%s" % doc["gate_build"])
    print("=" * 100)
    for c in doc["checks"]:
        print("  [%-8s] %-34s %s" % (c["status"], c["id"], c["ruling_ref"][:60]))
        obs = c["observed"]
        if isinstance(obs, dict):
            for v in (obs.get("violations") or [])[:6]:
                print("             ** 违例：%s" % v)
            if obs.get("dryrun_warn"):
                print("             警告：%s" % obs["dryrun_warn"])
            for v in (obs.get("warnings") or [])[:4]:
                print("             警告：%s" % v)
        if c["status"] == STATUS_UNJUDGED and c.get("note"):
            print("             弃权理由：%s" % c["note"][:200])
    print("-" * 100)
    print("准入：%s ⇒ total=%d PASS=%d WARN=%d RED=%d UNJUDGED=%d ⇒ admission_granted=%s"
          % (s["verdict"], s["total"], s["pass"], s["warn"], s["red"], s["unjudged"],
             doc["admission_granted"]))
    # RR-B2-09 改判（裁定 93 / D→B2 §四-1）：`ok` 与 `admission` 标签在 WARN 世界会不同 ⇒
    # 两个都打，并把"已登记的 WARN 是哪些"打在 stdout 上（登记义务不因改判而变成看不见）。
    print("顶层 ok（唯一失败判据）=%s ⇒ 口径 %s：n_red=%d 且 n_unjudged=%d；"
          "WARN=%d 不计失败但已登记"
          % (doc["ok"], OK_CALIBER_MARKER, doc["n_red"], doc["n_unjudged"], doc["n_warn"]))
    wr = doc.get("warn_registered_not_blocking") or {}
    if wr.get("n_warn"):
        print("  已登记的 WARN（不阻塞放行；消掉那个事实才是修法，见 non_green[] 的 owner/fix）：%s"
              % ", ".join(str(x) for x in (wr.get("warn_ids") or [])))
    print("=" * 100)


# ---------------------------------------------------------------------------
# 自检：合成世界 + 变异，证明八条牙都咬得动、且**双向**有牙（裁定 27.1 / 裁定 39.1）
# ---------------------------------------------------------------------------
FAKE_WEIGHT_FILES = ["model.safetensors", "config.json", "policy_preprocessor.json",
                     "policy_postprocessor.json", "chat_template.json", "tokenizer.json",
                     "README.md"]


def _mk_world(base: Path, tamper: str):
    """造一个合成的 A2 交付世界：lock + manifest + receipt + dryrun + 7 份假权重。

    权重是**小假文件**（合成世界只验同一性逻辑，不验 14.47 GB 的真实字节）；
    sha256 是当场真算的，所以「复算相同 / 复算不同」两个方向都是真判据。
    """
    root = base
    a2 = root / A2_DIR_DEFAULT
    wdir = root / "weights" / "pi05_base"
    a2.mkdir(parents=True, exist_ok=True)
    wdir.mkdir(parents=True, exist_ok=True)

    # ---- 权重盘（M9 通过「不创建」来模拟缺失，绝不用 rm）----
    skip = set()
    if tamper == "M9_postprocessor_missing":
        skip = {"policy_postprocessor.json"}
    for i, n in enumerate(FAKE_WEIGHT_FILES):
        if n in skip:
            continue
        body = ("fake-pi05-weight-%s-%d\n" % (n, i)).encode()
        if tamper == "M8_sha_mismatch" and n == "model.safetensors":
            body = b"CORRUPTED-BYTES"          # 盘上字节变了，receipt 的 sha 仍是旧值
        (wdir / n).write_bytes(body)

    files_meta = []
    for n in FAKE_WEIGHT_FILES:
        p = wdir / n
        if not p.exists():
            continue
        h = hashlib.sha256(("fake-pi05-weight-%s-%d\n"
                            % (n, FAKE_WEIGHT_FILES.index(n))).encode()).hexdigest()
        files_meta.append({"path": n, "sha256": h, "bytes": p.stat().st_size})
    if tamper == "M10_files_short":
        files_meta = files_meta[:6]            # 半成品快照（719/895 的同型，缩小版）

    n_declared = 6 if tamper == "M10_files_short" else len(FAKE_WEIGHT_FILES)
    receipt = {
        "repo_id": "lerobot/pi05_base",
        "channel": "modelscope",
        "url": "https://www.modelscope.cn/api/v1/models/lerobot/pi05_base/repo/files",
        "local_path": str(wdir),
        "n_files": n_declared,
        "total_bytes": sum(f["bytes"] for f in files_meta),
        "elapsed_sec": 1234.5,
        "mb_per_s": 12.0,
        "files": files_meta,
        "external_unverified": {
            "license": "gemma",
            "last_modified": "2026-07-29",
            "community_vram_reports": "48GB 不够 vs ≈40GB 可用（互相矛盾）",
            "provenance": "external_unverified",
        },
    }
    # ---- 第三批变异：钉住「receipt 键名不匹配」这颗牙（第一版在这里把无从比对记成通过）----
    if tamper == "M28_receipt_key_blind":
        # 键名换成任何读法都不认识的名字 ⇒ 必须判「无从比对」= RED。
        # 第一版的行为是落进 `else: n_ok += 1`，即**把"读不懂"洗成"哈希一致"**（恒真牙）；
        # 这条变异就是它的回归测试：日后有人再简化 `_receipt_expectations`，这里会立刻红。
        receipt["files"] = [{"path": f["path"], "integrity_b64": f["sha256"],
                             "extent_v2": f["bytes"]} for f in files_meta]
    elif tamper == "M29_receipt_a2_shape":
        # A2 真实 receipt 的形态（`runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json`，
        # 2026-09-29 17:50:53，只读实测）：多渠道期望值 + 自述值。
        # 并**故意让一个文件的 modelscope 通道对不上** —— 真实案例是 `.gitattributes`：
        # ModelScope 仓由 SDK 重新打包 ⇒ 内容与 hf 不同（2130B vs 1519B），A2 用 git blob sha1 定案。
        # 盘上值命中 hf_lfs 通道 ⇒ **必须绿**：多渠道下"命中任一通道即同一"不是放宽判据，
        # 而是判对了对象（否则会对 A2 的真实交件造假红，同 M21/M22 的教训）。
        receipt["files"] = [{
            "path": f["path"], "required": True,
            "critical_silent_default": f["path"] in ("policy_preprocessor.json",
                                                     "policy_postprocessor.json"),
            "expected_size_hf": f["bytes"],
            "expected_size_modelscope": (f["bytes"] + 611) if f["path"] == "README.md" else f["bytes"],
            "expected_sha256_hf_lfs": f["sha256"],
            "expected_sha256_modelscope": ("f" * 64) if f["path"] == "README.md" else f["sha256"],
            "present": True, "actual_size": f["bytes"], "actual_sha256": f["sha256"],
            "sha256_match_modelscope": f["path"] != "README.md", "sha256_match_hf_lfs": True,
            "sha256_verdict": ("hf_git_blob_sha1" if f["path"] == "README.md"
                               else "hf_lfs+modelscope"),
        } for f in files_meta]
    elif tamper == "M30_receipt_claim_only":
        # 只有 receipt 的**自述**哈希、没有任何远端期望值 ⇒「交件后没被动过」成立，
        # 但「下对了东西」未证 ⇒ **UNJUDGED**（裁定 14 同型：既不降级成 PASS，也不升级成 RED）
        receipt["files"] = [{"path": f["path"], "actual_sha256": f["sha256"],
                             "actual_size": f["bytes"]} for f in files_meta]

    elif tamper in ("M31_receipt_a2_full", "M32_receipt_a2_unmarked_external"):
        # 复刻 A2 真实 receipt（`runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json`，
        # 2026-09-29 17:50:53）的**结构**：没有顶层 channel/url 键、有 remote_hf/remote_modelscope
        # 两个远端块、逐文件 sha256_verdict 标渠道、license 是带 kind/source 的 dict、
        # download 里有 note/log_path/measured_rate_MBps。权重仍是合成小文件
        #（数字**无物理意义**，ADR-C-007 口径），但 sha256 与 git blob sha1 都是当场真算的。
        # 一个文件（README.md）故意做成 `.gitattributes` 的真实形态：
        # `expected_sha256_hf_lfs = null`、modelscope 的 sha256/size 都对不上、
        # **只有 git blob sha1 能定案** ⇒ M31 同时是"blob 通道"这颗牙的正向证明。
        new_files = []
        for f in files_meta:
            fp = wdir / f["path"]
            body = fp.read_bytes() if fp.exists() else b""
            b1 = hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()
            diverge = (f["path"] == "README.md")
            new_files.append({
                "path": f["path"], "required": True,
                "critical_silent_default": f["path"] in ("policy_preprocessor.json",
                                                         "policy_postprocessor.json"),
                "expected_size_hf": f["bytes"],
                "expected_size_modelscope": (f["bytes"] + 611) if diverge else f["bytes"],
                "expected_sha256_hf_lfs": (None if diverge else f["sha256"]),
                "expected_sha256_modelscope": ("35bde0a2" + "0" * 56) if diverge else f["sha256"],
                "expected_git_blob_sha1_hf": (b1 if diverge else None),
                "present": True, "actual_size": f["bytes"], "actual_sha256": f["sha256"],
                "actual_git_blob_sha1": b1, "size_ok": True,
                "sha256_match_modelscope": (not diverge),
                "sha256_match_hf_lfs": (None if diverge else True),
                "git_blob_sha1_match_hf": True,
                "sha256_verdict": ("hf_git_blob_sha1" if diverge else "hf_lfs+modelscope"),
            })
        receipt["files"] = new_files
        receipt.pop("channel", None)
        receipt.pop("url", None)
        receipt.pop("external_unverified", None)
        receipt["remote_hf"] = {"commit_sha": "b211f3d4" + "0" * 32,
                                "last_modified": "2026-07-29T10:25:19.000Z",
                                "license": "gemma", "used_storage": receipt["total_bytes"],
                                "siblings_count": len(new_files), "gated": False,
                                "n_files": len(new_files)}
        receipt["remote_modelscope"] = {"n_files": len(new_files) + 1, "code": 200, "success": True}
        receipt["manifest_cross_check"] = {
            "hf_only": [], "modelscope_only": ["configuration.json"],
            "size_disagree": ["README.md"], "sha256_disagree": [],
            "note": "渠道差异（ModelScope 仓由 SDK 重新打包），不是损坏"}
        receipt["license"] = {"value": "gemma", "expected": "gemma", "match": True,
                              "source": "HF API cardData.license / tags（https://hf-mirror.com）",
                              "terms": "Gemma Terms of Use —— 有约束的许可证，引用前须复核",
                              "kind": "remote_api_read"}
        receipt["commit"] = {"hf_sha": "b211f3d4" + "0" * 32,
                             "expected": "b211f3d4" + "0" * 32, "match": True}
        receipt["download"] = {
            "note": "大文件走 ModelScope 单流 curl；其余小文件走 hf-mirror + hf_mirror_snapshot.py",
            "log_path": str(a2 / "g1_modelscope_download.log"), "curl_rc": 0,
            "wall_s": 553.0, "measured_rate_MBps": 26.16,
            "first_ts": "2026-09-29T17:17:57+08:00", "last_ts": "2026-09-29T17:27:10+08:00"}
        receipt["verdict"] = {"complete_7_of_7": True, "all_sizes_ok": True,
                              "all_hashes_ok": True, "no_halfbaked": True, "PASS": True}
        receipt["failures"] = []
        receipt["exit_code"] = 0
        if tamper == "M32_receipt_a2_unmarked_external":
            # 这两条正是**真实 receipt 上实测到的**并列形态：远端报的 size 与本机实测速率同块、
            # 关于外部事实的派生判定与本地判定同块，且都没有标记 ⇒ 放宽标记词表之后牙必须仍在
            receipt["download"]["reported_size"] = receipt["total_bytes"]
            receipt["verdict"]["license_ok"] = True
        else:
            receipt["download"]["remote_reported_size"] = {
                "value": receipt["total_bytes"], "kind": "remote_api_read",
                "source": "ModelScope API / HF API used_storage"}
            receipt["verdict"]["license_ok"] = {
                "value": True, "kind": "derived_from_remote_api_read",
                "source": "HF API cardData.license（https://hf-mirror.com）"}

    if tamper == "M11_channel_absent":
        receipt.pop("channel")
        receipt.pop("url")
    elif tamper == "M12_external_unmarked":
        receipt["license"] = receipt["external_unverified"].pop("license")
        receipt["community_vram_reports"] = receipt["external_unverified"].pop("community_vram_reports")
    elif tamper == "M13_measured_in_external":
        receipt["external_unverified"]["sha256_of_model"] = files_meta[0]["sha256"]
        receipt["external_unverified"]["total_bytes"] = receipt["total_bytes"]
    elif tamper == "M14_license_missing":
        receipt["external_unverified"].pop("license")

    # ---- 裁定 78.8 之后：合成世界的**基线 = A2 现场那套合规形态** ----
    # 旧基线（PyPI `4.57.1` + `transformers==4.57.1` 的 lock 行）在改判后的四条 blocking 判据下
    # **必然红**（① 版本偏实测锚 ② lock 里查不到锚 commit ③ 卫语句不过 ④ 没有 load_verification）
    # ⇒ 基线不绿，后面所有"变红"的变异体都失去参照（`baseline_all_green` 既是 mutation_verdict
    # 的判据之一，也是 M19 的内容；基线红 = 全部反向变异失去意义）。
    # 新基线照抄现场真值：git 分支 `fix/lerobot_openpi`@`dcddb970…`、版本串 `4.53.3`
    # （**低于** §8.1 的声明下界 `4.57.1` —— 这正是裁定 78.8 的现场）、卫语句 True、
    # lock 用 direct-url 行（**不含版本串**，所以版本串的唯一载体是 env_manifest）、
    # 外加一份合成的 `load_verification.json`（812/812/0/0，形态照 A2 的真件）。
    tf_live = TRANSFORMERS_MEASURED_ANCHOR
    tf_lock = TRANSFORMERS_MEASURED_ANCHOR
    tf_git_commit = TRANSFORMERS_GIT_COMMIT_ANCHOR
    tf_lock_style = "direct_url"     # "direct_url" = git 安装的真实 freeze 形态；"version" = `==` 行
    tf_in_manifest = True
    tf_pi05_ok = True                # lerobot π₀.₅ 的硬卫语句（功能锚）
    lr_live = LEROBOT_ANCHOR
    torch_live, torch_cuda, torch_lock = TORCH_ANCHOR, TORCH_CUDA_ANCHOR, "2.6.0"
    resolved = str(root / ".codex-persist" / "envs" / "pi05_sim")
    if tamper == "M1_lerobot_drift":
        lr_live = "0.4.5"
    elif tamper == "M2_transformers_absent":
        tf_live, tf_lock, tf_git_commit, tf_pi05_ok = None, None, None, False
    elif tamper == "M3_transformers_below_floor":
        # maniskill_probe 的实测值：版本偏锚 **且** 卫语句不过（其 `check.py` 只接受 4.53.2/4.53.3）
        tf_live, tf_lock = "4.30.0", "4.30.0"
        tf_git_commit, tf_lock_style, tf_pi05_ok = None, "version", False
    elif tamper == "M4_transformers_unrecorded":
        # 只留「实测已装但产物里查不到版本」这**一条**成因：git 安装的 lock 行是 direct-url 形态、
        # **不含版本串**（现场实测：A2 的 lock 里 grep 不到 "4.53.3"），所以版本串唯一的载体是
        # env_manifest ⇒ 把它抹掉即精确命中该成因（旧版靠 `tf_lock=None` 命中，改判后那条路径
        # 会先被 ①②④ 三条判据盖过，牙就不专一了）。
        # 注意 `resolve_dryrun.txt` 里仍会出现该版本 —— 那是**计划书**不是**装成记录**，
        # 不算「写进产物」（否则这颗牙会被一份 dryrun 糊过去）。
        tf_in_manifest = False
    elif tamper == "M5_torch_cu128":
        torch_live, torch_cuda, torch_lock = "2.9.0+cu128", "12.8", "2.9.0"
    elif tamper == "M14_forbidden_venv":
        resolved = str(root / ".codex-persist" / "envs" / "maniskill_probe")
        tf_live, tf_lock = "4.30.0", "4.30.0"
        tf_git_commit, tf_lock_style, tf_pi05_ok = None, "version", False
    elif tamper == "M66_forbidden_venv_tf_compliant":
        # 与 M14 的**唯一**差别：transformers 保持基线合规形态（版本 == 实测锚、commit 在 lock、
        # 卫语句 True、812/812 逐位核验件在场）⇒ 这个世界上只剩「venv realpath 落在
        # maniskill_probe」**一个**缺陷。
        # 为什么必须有这一条（裁定 86.6-3 `mutant_specificity_required`）：M14 复现的是
        # maniskill_probe 的**真实**形态，它同时违反 V-pi05-1 的禁用 venv 规则与 V-pi05-5 的
        # 卫语句判据 ⇒ 两颗牙一起红，**分不出**是「禁用 venv」这条规则红的还是「卫语句」红的。
        # 一个翻不动**目标**规则的变异体，与一个恒真的牙同样危险。M66 提供隔离证明：
        # 只有禁用 venv 这一个缺陷时，V-pi05-1 仍必须红、而 V-pi05-5 必须**不**红。
        resolved = str(root / ".codex-persist" / "envs" / "maniskill_probe")
    elif tamper == "M15_lock_cuda_blind":
        torch_live, torch_cuda = "2.6.0+cu121", "12.1"   # lock 仍写 2.6.0 ⇒ 只有活体探针能抓
    elif tamper == "M38_manifest_real_drift":
        # π₀.₅ 侧的 runtime torch **真的**换了构建（2.7.0+cu126），基线仍是 2.6.0+cu124
        # ⇒ V-pi05-6 必须红且点名 `real_runtime_drift`（V-pi05-4 同时红是应该的，不是重复计数：
        #   两条牙的事实源不同 —— 一条比锚常量，一条复核交件自述）
        torch_live, torch_cuda = "2.7.0+cu126", "12.6"

    # ---- 功能锚（lerobot π₀.₅ 的硬卫语句）与 git 溯源的变异 ----
    # 与上面同一条纪律：**必须在 lock_lines / manifest / dryrun / load_verification 构造之前**
    # 改 tf_*，否则产物里记的还是旧值，变异世界自相矛盾（第一版就踩了：M34 因 manifest 记
    # 4.57.1 而假红）。这一批（M33/M34/M35/M59/M60/M63）全部落在裁定 78.8 的四条 blocking 上。
    if tamper == "M33_pi05_tf_check_false":
        tf_pi05_ok = False                     # 版本看着合规，但硬校验不过 ⇒ 只有功能锚能抓
    elif tamper == "M34_pi05_tf_git_ok":
        pass          # 与基线**同形**（幂等）：裁定 78.8 之后基线就是 git@锚 + 4.53.3 + 卫语句 True
    elif tamper == "M35_pi05_tf_git_no_commit":
        # 活体仍是 git 安装（direct_url 带 commit），但 freeze 出来的 lock 只有版本串
        tf_lock_style = "version"
    elif tamper == "M59_tf_version_off_anchor":
        # 装了**满足 §8.1 声明区间**的 PyPI 4.57.6 ⇒ 卫语句拒绝（A2 实测 ValueError）、
        # 也就没有 load_verification。声明区间合规 ≠ 能跑 π₀.₅ —— 这条钉住裁定 78.8 的实质。
        tf_live, tf_lock = "4.57.6", "4.57.6"
        tf_git_commit, tf_lock_style, tf_pi05_ok = None, "version", False
    elif tamper == "M60_tf_commit_off_anchor":
        # 版本串对、卫语句也过，但装的是**另一次 build**（commit 偏锚）⇒ 只有 commit 能认出来
        tf_git_commit = "deadbeef" * 5
    elif tamper == "M63_tf_pypi_same_version_no_guard":
        # PyPI 的 4.53.3：**版本号与锚逐字相同**，但没有定制分支的 `check.py` ⇒ 卫语句 False、
        # 无 commit、也就没有 load_verification。专门防"版本号相同就放过"（D 点名的第 ③ 条变异）
        tf_git_commit, tf_lock_style, tf_pi05_ok = None, "version", False

    lock_lines = ["lerobot==%s" % LEROBOT_ANCHOR, "torch==%s" % torch_lock,
                  "torchvision==0.21.0", "torchcodec==0.10.0", "numpy==2.2.6",
                  "accelerate==1.15.0"]
    if tf_lock:
        if tf_lock_style == "direct_url" and tf_git_commit:
            # git 安装的真实 freeze 形态：**行里没有版本串**（现场 `requirements.lock.txt:111`）
            lock_lines.append("transformers @ git+https://github.com/huggingface/transformers.git@%s"
                              % tf_git_commit)
        else:
            lock_lines.append("transformers==%s" % tf_lock)
    # ---- V-pi05-6 用：A2 真实 manifest 的**可用性三元组**（assertions / env_usable /
    # frozen_stack_drift）+ 两个版本口径。合成世界默认给"干净交件"（assertions 全 true、
    # drift 空、env_usable=true），只有点名的变异才改它。
    # `*_meta`（dist-info 元数据）与 `*_rt`（runtime `__version__`）**故意不同**：
    # 基线元数据裸写 `2.6.0`、runtime 是 `2.6.0+cu124` —— 这是 19:11 现场实测的真实形态
    # （三个 venv 的 runtime 全是 `2.6.0+cu124`/cuda 12.4，只有 dist-info 目录名带不带 local
    # 段的差别）。不照抄这个形态，M36 那条"比对口径造成的假红"就无从复现。
    man_assertions = {k: True for k in (
        "V1_venv_is_symlink_to_NFS_persist", "V2_include_system_site_packages_false",
        "V3_torch_version_redline_2_6_0_cu124", "V4_torchvision_torchcodec_match_baseline",
        "V5_transformers_has_siglip_check_for_pi05", "V6_paligemma_and_pi05policy_importable",
        "V7_gym_aloha_spec_registrable", "V8_lerobot_pinned_0_4_4",
        "V9_lock_present_and_covers_probed_packages")}
    base_venv = ACCEPTED_VENVS[0]
    base_rt = {"torch": TORCH_ANCHOR, "torchvision": "0.21.0+cu124"}
    base_meta = {"torch": TORCH_ANCHOR.split("+")[0], "torchvision": "0.21.0",
                 "torchcodec": "0.10.0", "lerobot": LEROBOT_ANCHOR}
    new_rt = {"torch": torch_live, "torchvision": "0.21.0+cu124"}
    new_meta = {"torch": torch_live, "torchvision": "0.21.0+cu124",
                "torchcodec": "0.10.0", "lerobot": lr_live}
    man_drift, man_diff = [], {}
    if tamper == "M36_manifest_metadata_only":
        # A2 现场的真实形态：只比 dist-info 元数据串 ⇒ 同一构建被判成漂移
        man_drift = ["torch", "torchvision"]
        man_diff = {p: {"pi05_sim": new_meta[p], "lerobot_act_baseline": base_meta[p]}
                    for p in man_drift}
    elif tamper in ("M38_manifest_real_drift", "M41_manifest_drift_unprobeable"):
        man_drift = ["torch"]
        man_diff = {"torch": {"pi05_sim": new_rt["torch"], "lerobot_act_baseline": base_rt["torch"]}}
    elif tamper == "M40_manifest_selfcontradict":
        man_assertions["V5_transformers_has_siglip_check_for_pi05"] = False
    elif tamper == "M37_manifest_clean_benign_diff":
        # 交件里**有**包差异，但都不在冻结栈（transformers / mujoco 是 A2 有意引入的，
        # A2 自己在 baseline_comparison.note 里就这么写）⇒ drift 必须为空、env_usable=true，
        # 本条牙必须绿。这条反向变异防的是「一看到 differing_packages 非空就红」的恒红。
        man_diff = {"transformers": {"pi05_sim": tf_live, "lerobot_act_baseline": None},
                    "mujoco": {"pi05_sim": "3.8.1", "lerobot_act_baseline": None},
                    "scipy": {"pi05_sim": "1.17.1", "lerobot_act_baseline": None}}
    man_usable = bool(all(v is True for v in man_assertions.values()) and not man_drift)
    if tamper == "M40_manifest_selfcontradict":
        man_usable = True        # 交件自称可用，但 assertions 里有一条 False ⇒ 自相矛盾
    manifest = {
        "manifest_kind": "a2_pi05_env_manifest",
        "generated_by": "A2 / scripts/a_env_manifest.py（合成世界）",
        "pin": {"lerobot": LEROBOT_ANCHOR, "torch": torch_lock},
        "venvs": {"pi05_sim": {
            "link": "/root/venvs/pi05_sim", "is_symlink": True, "resolved": resolved,
            "exists": True, "python_exists": True, "probe_rc": 0, "py": "3.11.9",
            "pkgs": {"lerobot": lr_live, "torch": torch_live,
                     "torchvision": "0.21.0+cu124",
                     "transformers": (tf_live if tf_in_manifest else None)},
            "dist": {"lerobot": resolved + "/lib/python3.11/site-packages/lerobot-%s.dist-info" % lr_live},
            "torch_version": torch_live, "cuda": True,
        }},
        # ↓ 结构照抄 A2 的**真交件**（2026-09-29 19:11:47 那份，B2 只读实测）：
        #   `env_usable` 在顶层**和** `verdict.*`；`frozen_stack_drift` **只在** `verdict.*` 与
        #   `baseline_comparison.*`（顶层没有）。第一版合成世界把它写在顶层，结果对真交件
        #   判 UNJUDGED、对合成世界全绿 —— 「被测对象与使用对象不是同一个」的又一例。
        "assertions": man_assertions,
        "assertions_pass": "%d/%d" % (sum(1 for v in man_assertions.values() if v is True),
                                      len(man_assertions)),
        "env_usable": man_usable,
        "baseline_comparison": {"baseline_venv": base_venv, "baseline_read_only": True,
                                "differing_packages": man_diff,
                                "frozen_stack_drift": man_drift},
        "frozen_stack_versions": {k: {"pi05_sim_runtime": new_rt.get(k) or new_meta.get(k),
                                      "baseline_runtime": base_rt.get(k) or base_meta.get(k),
                                      "pi05_sim_dist": new_meta.get(k),
                                      "baseline_dist": base_meta.get(k)}
                                  for k in ("torch", "torchvision", "torchcodec", "lerobot")},
        "verdict": {"env_usable": man_usable, "frozen_stack_drift": man_drift,
                    "claim_scope": "env_usable=true 只支持「环境可用」，不支持任何能力主张",
                    "blocked_if": ("V5 红 ⇒ π₀.₅ 无法 from_pretrained；V3/V4 红或 frozen_stack_drift "
                                   "非空 ⇒ 断点变更，需 D 登记 + 重过 B2 闸")},
    }
    if tamper == "M39_manifest_no_usability_keys":
        # 旧式交件：只有版本清单，没有可用性三元组 ⇒ 本条牙必须**弃权**，不得记成 PASS。
        # 三个键在**所有**候选位置都要抹掉，否则多通道读取会从嵌套位置把它捞回来。
        for k in MANIFEST_USABILITY_KEYS:
            manifest.pop(k, None)
        for blk in ("verdict", "baseline_comparison"):
            for k in MANIFEST_USABILITY_KEYS:
                (manifest.get(blk) or {}).pop(k, None)
    if tamper == "M42_manifest_nested_disagree":
        # 同一个键在两处**说的不一样**：`verdict.frozen_stack_drift=[]`（配 env_usable=true，
        # 自洽）但 `baseline_comparison.frozen_stack_drift=["torch"]`。
        # ⇒ 必须红，且判词必须点名"交件内部不一致"，**不得**由 B2 挑一个采信。
        manifest["baseline_comparison"]["frozen_stack_drift"] = ["torch"]
        manifest["frozen_stack_versions"]["torch"]["baseline_dist"] = "2.6.0"
    # 计划书（dryrun）的形态照 A2 的真件：解析器**先**按 lerobot extra 的声明区间选中 PyPI 4.57.6，
    # STAGE 3 再用 π₀.₅ 的定制分支覆盖它。声明区间只出现在这里（`declared_only`，裁定 78.8）。
    dryrun = [
        "Collecting transformers<5.0.0,>=4.57.1",
        "  Downloading transformers-4.57.6-py3-none-any.whl (10.4 MB)",
        "Collecting tokenizers<0.22,>=0.21",
    ]
    if tf_git_commit:
        dryrun += [
            "=========== STAGE 3：π₀.₅ 定制分支覆盖（lerobot pyproject.toml:444）===========",
            "Updating https://github.com/huggingface/transformers.git (%s)"
            % TRANSFORMERS_GIT_BRANCH_ANCHOR,
            " Updated https://github.com/huggingface/transformers.git (%s)" % tf_git_commit,
            " + transformers @ git+https://github.com/huggingface/transformers.git@%s"
            % tf_git_commit]
    dryrun.append("Would install huggingface-hub-0.34.0 tokenizers-0.21.4 transformers-%s"
                  % (tf_lock or "4.57.6"))
    if tamper == "M6_dryrun_touches_torch":
        dryrun = [
            "Collecting torch<2.11.0,>=2.2.1",
            "  Downloading torch-2.9.0+cu128-cp311-linux_x86_64.whl (899.3 MB)",
            "Attempting uninstall: torch",
            "    Found existing installation: torch 2.6.0 -> 2.9.0",
            "Would install torch-2.9.0+cu128 torchcodec-0.11.0 torchvision-0.24.0 transformers-4.57.1",
        ]
    # ---- 第二批变异：钉住「认版本 + 认分段 + 锚值回校」这三处判据（第一版在这里判错过）----
    if tamper == "M21_dryrun_at_anchor_fresh":
        # 空 venv 的一次性解析：torch 栈**按锚值**出现在安装清单里 ⇒ 不是「挪动」，必须绿
        dryrun = ["Using Python 3.11.9 environment at: /root/venvs/pi05_sim",
                  "Would install 123 packages",
                  " + torch==2.6.0+cu124", " + torchcodec==0.10.0",
                  " + torchvision==0.21.0+cu124", " + transformers==4.57.1"]
    elif tamper == "M22_dryrun_multisection":
        # A2 的真实形态：STAGE 1 先钉 torch（前段含锚值安装行），STAGE 2 的清单里 torch 不出现
        dryrun = ["==================== uv pip install --dry-run ====================",
                  "Would install 123 packages",
                  " + torch==2.6.0+cu124", " + torchvision==0.21.0+cu124",
                  " + torchcodec==0.10.0", " + transformers==4.57.1",
                  "==================== STAGE 1：torch 栈 ====================",
                  "Downloading torch (732.9MiB)", "Installed 27 packages",
                  "==================== STAGE 2：lerobot + transformers ====================",
                  "Would install 96 packages", " + accelerate==1.15.0",
                  " + transformers==4.57.1", " + tokenizers==0.22.2"]
    elif tamper == "M23_dryrun_off_anchor_install":
        dryrun = ["Would install 12 packages", " + torch==2.9.0+cu128",
                  " + torchvision==0.24.0+cu128", " + transformers==4.57.1"]
    elif tamper == "M24_dryrun_unversioned_live_ok":
        dryrun = ["Downloading torch (732.9MiB)", "Downloading torchvision (6.9MiB)",
                  "Installed 27 packages", " + transformers==4.57.1"]
    elif tamper == "M25_dryrun_unversioned_live_bad":
        dryrun = ["Downloading torch (732.9MiB)", " + transformers==4.57.1"]
        torch_live, torch_cuda = "2.6.0+cu121", "12.1"
    elif tamper == "M27_dryrun_uninstall_torch":
        dryrun = ["Would uninstall 1 package", " - torch==2.6.0+cu124",
                  " + transformers==4.57.1"]

    # 注：M34（git 装成、commit 进 lock）与 M35（git 装成、commit 只在 dryrun）的世界构造
    # 已上移到 tf_* 基线段（`tf_lock_style` / `tf_git_commit`），因为裁定 78.8 之后
    # **基线本身就是 git 形态**，在这里再改 lock_lines 会造成同一行被追加两次（幂等性缺口）。
    # dryrun 的 STAGE 3 行也随基线一起构造（仅当 `tf_git_commit` 非空时出现）。
    out_dir = root / OUT_DIR_DEFAULT
    out_dir.mkdir(parents=True, exist_ok=True)
    if tamper == "M18_teeth_stale":
        (out_dir / "mutation_verdict.json").write_text(json.dumps(
            {"all_ok": True, "n_ok": 18, "n_mutations": 18, "n_reverse": 3,
             "baseline_all_green": True, "gate_build": "deadbeef0000",
             "mutations": []}, indent=1))

    if tamper == "M16_evidence_missing":
        # A2 目录存在但**空**（最常见的真实形态：还没交件）
        for n in ("requirements.lock.txt", "env_manifest.json", "weights_receipt.json",
                  "resolve_dryrun.txt"):
            p = a2 / n
            if p.exists():
                shutil.move(str(p), str(out_dir / ("moved_" + n)))
        return root, a2, out_dir, None

    (a2 / "requirements.lock.txt").write_text("\n".join(lock_lines) + "\n")
    (a2 / "env_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (a2 / "weights_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    (a2 / "resolve_dryrun.txt").write_text("\n".join(dryrun) + "\n")

    # ---- 裁定 78.8 的第 ④ 条 blocking 判据的事实源：合成的 `load_verification.json` ----
    # 写不写由**这个世界自身说不说得通**决定：只有「版本 == 实测锚 且 卫语句通过」的世界才可能
    # 存在这份件（卫语句不过 ⇒ `PI05Policy.from_pretrained` 直接抛 ValueError ⇒ 不会有核验件；
    # 版本偏锚 ⇒ A2 压根没做成那次核验）。不照这个因果写，M59/M63 就会出现"环境不合规却有
    # 逐位核验件"的自相矛盾世界。
    # 形态照 A2 的真件（`runs/vla/a2_pi05_contract_20260929/load_verification.json`，
    # sha12 `18d9149a4636`、3246 B）：`verdict` + `compare` 的四个计数 + `versions` + `safetensors`。
    lv_world = (tf_live == TRANSFORMERS_MEASURED_ANCHOR and tf_pi05_ok)
    if tamper == "M62_loadver_absent":
        lv_world = False        # 环境合规但核验件缺失 ⇒ V-pi05-1 必须 UNJUDGED（不得读成通过）
    if lv_world:
        n_differ = 3 if tamper == "M61_loadver_n_differ" else 0
        big = wdir / "model.safetensors"
        lv_doc = {
            "probe": "synthetic_a2_verify_pi05_load（B2 自检世界；**不代表** A2 的真实核验）",
            "generated_at": "2026-09-29T18:56:03+08:00",
            "generator": "scripts/a2_verify_pi05_load.py（合成）",
            "morphology": "aloha_bimanual_14d",
            "safetensors": {"path": str(big), "bytes": big.stat().st_size if big.exists() else None,
                            "n_tensors_in_file": LOAD_VERIFY_N_TENSORS_ANCHOR},
            "versions": {"torch": torch_live, "transformers": tf_live, "lerobot": lr_live},
            "n_parameters": 3616757520,
            "compare": {
                "n_compared": LOAD_VERIFY_N_TENSORS_ANCHOR,
                "n_bitwise_exact": LOAD_VERIFY_N_TENSORS_ANCHOR - n_differ,
                "n_differ": n_differ, "n_shape_mismatch": 0,
                "n_ckpt_keys_not_in_model": 0, "n_model_keys_not_covered_by_ckpt": 0,
                "differ_sample": ["synthetic.differ.%d.weight" % i for i in range(n_differ)],
                "ckpt_keys_not_in_model_sample": [], "shape_mismatch_sample": [],
                "model_keys_not_covered_sample": []},
            # M61 故意让 `verdict` 自称 all_bitwise_equal 而**计数不同意** ⇒ 钉住
            # 「只读 verdict 不读计数」的漏洞（与「只读 summary 不读逐条」同族）
            "verdict": LOAD_VERIFY_VERDICT_ANCHOR,
        }
        lv_p = root / A2_LOAD_VERIFICATION
        lv_p.parent.mkdir(parents=True, exist_ok=True)
        lv_p.write_text(json.dumps(lv_doc, indent=1, ensure_ascii=False) + "\n")

    # ---- 裁定 49.5 的闭合载体：合成的渠道 sidecar（形态照 A2 的真件，字段名逐字相同）----
    # 只在需要它的世界里写（基线 / M31 的 A2 完整结构 / M64 / M65）：其余世界的 receipt 本来就
    # 没有混用形态，硬塞一份 sidecar 只会造出"receipt 说一个渠道、sidecar 说两个"的自相矛盾世界。
    # **M11（receipt 无留痕）故意不写 sidecar** —— 否则那颗牙会被 sidecar 顶掉（牙被拔掉）。
    if tamper in ("none", "M31_receipt_a2_full",
                  "M64_sidecar_mixed_dishonest", "M65_sidecar_sha_claim_false"):
        rc_sha = _sha256_file(a2 / "weights_receipt.json")["sha256"]
        per_file = [{"path": f["path"],
                     "channel": ("modelscope_curl_single_stream"
                                 if f["path"] == "model.safetensors" else "hf_mirror_snapshot"),
                     "required": True, "actual_size": f["bytes"], "actual_sha256": f["sha256"]}
                    for f in files_meta]
        distinct = sorted({f["channel"] for f in per_file})
        claimed_sha = rc_sha
        if tamper == "M64_sidecar_mixed_dishonest":
            # 自称 `mixed`，但逐文件记录里只有 1 个渠道 ⇒ mixed 不诚实（sidecar 自己的 C1 就该红）
            for f in per_file:
                f["channel"] = "hf_mirror_snapshot"
            distinct = ["hf_mirror_snapshot"]
        if tamper == "M65_sidecar_sha_claim_false":
            claimed_sha = "0" * 64      # 自称 receipt 未改写，但记的 sha 与 B2 复算值不符
        sc_doc = {
            "artifact": "synthetic_pi05_base_weights_receipt_channel_sidecar（B2 自检世界）",
            "ruling": "裁定 49.5（V-pi05-3 渠道混用）",
            "generated_at": "2026-09-29T20:59:37+08:00",
            "generator": "scripts/a2_weights_channel_sidecar.py（合成）",
            "channel_top_level": CHANNEL_TOP_LEVEL_MIXED,
            "distinct_channels": distinct,
            "per_file_channel": per_file,
            "receipt_reference": {
                "path": str(a2 / "weights_receipt.json"),
                "sha256_before_sidecar": claimed_sha, "sha256_after_sidecar": claimed_sha,
                "sha256_identical": True, "rewritten_by_this_script": False,
                "verdict_PASS_in_receipt": True},
            "checks": {
                "C1_at_least_two_distinct_channels_so_mixed_is_honest": len(distinct) > 1,
                "C2_receipt_sha256_unchanged": (claimed_sha == rc_sha),
                "C3_model_safetensors_cross_channel_sha256_identical": True,
                "C4_every_required_file_has_channel_record_no_unknown": True,
                "C5_tokenizer_repo_channel_recorded_and_pass": True},
            "mutation_selftest": {"mutations_expected_to_be_caught": 3, "mutations_caught": 3,
                                  "all_cases_verdict_ok": True},
            "no_redownload": {"verdict": True, "reason": "裁定 49.5：重下 14.47 GB 无收益"},
            "verdict": {"channel_top_level": CHANNEL_TOP_LEVEL_MIXED, "all_checks_pass": True,
                        "selftest_caught": "3/3", "PASS": True},
        }
        sc_p = root / A2_CHANNEL_SIDECAR
        sc_p.parent.mkdir(parents=True, exist_ok=True)
        sc_p.write_text(json.dumps(sc_doc, indent=1, ensure_ascii=False) + "\n")

    probe = {"venv": "/root/venvs/pi05_sim", "is_symlink": True, "resolved": resolved,
             "python_exists": True, "probe_rc": 0, "py": "3.11.9",
             "pkgs": {"lerobot": lr_live, "torch": torch_live, "torchvision": "0.21.0+cu124",
                      "torchcodec": None, "transformers": tf_live},
             "dist": {"lerobot": "/fake/lerobot-%s.dist-info" % lr_live,
                      "torch": "/fake/torch-%s.dist-info" % new_meta["torch"],
                      "torchvision": "/fake/torchvision-%s.dist-info" % new_meta["torchvision"],
                      "torchcodec": "/fake/torchcodec-%s.dist-info" % new_meta["torchcodec"],
                      "transformers": ("/fake/transformers-%s.dist-info" % tf_live) if tf_live else None},
             "direct_url": {
                 "transformers": ({"url": "https://github.com/huggingface/transformers.git",
                                   "vcs_info": {"vcs": "git", "commit_id": tf_git_commit,
                                                "requested_revision": "fix/lerobot_openpi"}}
                                  if tf_git_commit else None),
                 "lerobot": None},
             "pi05_transformers_check": (
                 {"ran": True, "ok": bool(tf_pi05_ok)} if tf_live else
                 {"ran": True, "ok": False, "error": "ModuleNotFoundError: No module named 'transformers'"}),
             "torch_version": torch_live, "torch_cuda": torch_cuda}
    # 基线 venv 的探针：**runtime 与 dist-info 元数据分开给**（照抄现场实测形态 ——
    # runtime `2.6.0+cu124`、元数据 `2.6.0`），否则 V-pi05-6 的 metadata_only 分类无从复现。
    accepted = {v: {"venv": v, "python_exists": True, "probe_rc": 0,
                    "pkgs": {"lerobot": LEROBOT_ANCHOR, "torch": base_rt["torch"],
                             "torchvision": base_rt["torchvision"], "torchcodec": None},
                    "dist": {"lerobot": "/fake/lerobot-%s.dist-info" % base_meta["lerobot"],
                             "torch": "/fake/torch-%s.dist-info" % base_meta["torch"],
                             "torchvision": "/fake/torchvision-%s.dist-info" % base_meta["torchvision"],
                             "torchcodec": "/fake/torchcodec-%s.dist-info" % base_meta["torchcodec"]},
                    "torch_version": base_rt["torch"], "torch_cuda": TORCH_CUDA_ANCHOR}
                for v in ACCEPTED_VENVS}
    if tamper == "M17_accepted_unprobed":
        accepted[ACCEPTED_VENVS[0]] = {"venv": ACCEPTED_VENVS[0], "python_exists": False,
                                       "probe_error": "解释器不存在"}
    if tamper == "M41_manifest_drift_unprobeable":
        # 交件点了 drift，但基线 venv 探不到 ⇒ 成因无从归因；此时仍必须红（交件自称不可用），
        # 判词要写"无法独立复核成因"，**不得**悄悄改成 PASS 或 UNJUDGED
        accepted[ACCEPTED_VENVS[0]] = {"venv": ACCEPTED_VENVS[0], "python_exists": False,
                                       "probe_error": "解释器不存在"}
    if tamper == "M26_anchor_drift":
        # 已验收 venv 的活体 torch 与锚常量不符 ⇒ 锚本身已漂，必须红并要求报 D 更新锚
        for v in accepted:
            accepted[v] = dict(accepted[v], torch_version="2.7.0+cu126",
                               pkgs=dict(accepted[v]["pkgs"], torch="2.7.0+cu126"))
    measured = {"venv_probe": probe, "accepted_venv_probe": accepted,
                "pyvenv_cfg": {"exists": True, "version": "3.11.9",
                               "include-system-site-packages": "false"}}

    # ======================================================================
    # V-pi05-7 用：控制频率交件（形态照 A2 的真实产物 `ctrl_hz_alignment_a2.json`）
    # 路径用**候选表的相对路径**，这样合成世界与真现场走同一条发现逻辑
    # （教训：合成世界的结构不能代替真交件的结构 —— receipt 键名、manifest 键位置各踩过一次）
    # ======================================================================
    hz_path = root / CTRL_HZ_CANDIDATES[0]
    hz_path.parent.mkdir(parents=True, exist_ok=True)
    hz_doc = {
        "probe": "synthetic_ctrl_hz_alignment",
        "env_id": "gym_aloha/AlohaTransferCube-v0",
        "as_is": {"physics_timestep_s": 0.002, "control_timestep_s": 0.02,
                  "decimation_n_substeps": 10, "control_hz": 50.0,
                  "source_constants": "gym_aloha/constants.py DT=0.02",
                  "in_qc_band_29_31": False},
        "target_30hz": {"physics_timestep_s": 1.0 / 480.0, "control_timestep_s": 1.0 / 30.0,
                        "decimation_n_substeps": 16, "control_hz": 30.0,
                        "integer_decimation": True},
        # 这一组**故意**让 1/(ts×dec) 与 1/cts 不一致：它演示的就是"只改 DT 不改 timestep
        # ⇒ decimation 只能取整 17 ⇒ 29.41 Hz"这个坑。判据必须能容忍这种诚实陈述（否则假红）。
        "naive_pitfall": {"physics_timestep_s": 0.002, "control_timestep_s": 1.0 / 30.0,
                          "decimation_if_rounded": 17, "resulting_control_hz": 29.4118,
                          "why_it_matters": "只改 DT 不改 timestep ⇒ 拿不到 30.0 Hz"},
        "chunk_timescale_options": {
            "invariant": "chunk 覆盖的真实时长 = chunk 步数 × 控制周期",
            "pi05_chunk_steps": 50,
            "options": [{"id": "甲", "scheme": "示范 30 → 50 Hz 重采样", "chunk_duration_s": 1.0},
                        {"id": "乙", "scheme": "chunk 时长按 30/50 缩放",
                         "chunk_duration_s": 1.6667}]},
    }
    if tamper == "M43_hz_triple_inconsistent":
        hz_doc["target_30hz"]["control_hz"] = 30.5          # 与 1/(ts×dec)=30.0 不符
        hz_doc["target_30hz"]["control_timestep_s"] = 1.0 / 30.5
    elif tamper == "M44_hz_missing_decimation":
        hz_doc["target_30hz"].pop("decimation_n_substeps")
        hz_doc["target_30hz"].pop("physics_timestep_s")
    elif tamper == "M45_hz_contract_3125":
        hz_doc["contract_stack"] = {"physics_timestep_s": 0.002, "control_timestep_s": 0.032,
                                    "decimation_n_substeps": 16, "control_hz": 31.25}
    elif tamper == "M47_hz_no_relation":
        hz_doc.pop("chunk_timescale_options")
        hz_doc["as_is"].pop("in_qc_band_29_31")
    elif tamper == "M48_hz_operative_out_of_band_no_plan":
        hz_doc.pop("chunk_timescale_options")
        hz_doc["as_is"].pop("in_qc_band_29_31")
        hz_doc["target_30hz"] = {"physics_timestep_s": 0.002, "control_timestep_s": 0.02,
                                 "decimation_n_substeps": 10, "control_hz": 50.0}
    if tamper != "M58_hz_doc_absent":
        hz_path.write_text(json.dumps(hz_doc, indent=1, ensure_ascii=False) + "\n")

    # ======================================================================
    # V-pi05-8 用：源 ckpt + 兼容目录 + 参考实现 + 报告（形态照 A2 的真实交件）
    # ======================================================================
    ck = root / "weights" / "pi05_base_ckptsrc"
    cp = root / "weights" / "pi05_base_compat_lerobot044"
    ck.mkdir(parents=True, exist_ok=True)
    pre_src = {"name": "policy_preprocessor", "steps": [
        {"registry_name": "rename_observations_processor", "config": {"rename_map": {}}},
        {"registry_name": "to_batch_processor", "config": {}},
        {"registry_name": "relative_actions_processor",
         "config": {"enabled": False, "exclude_joints": ["gripper"], "action_names": None}},
        {"registry_name": "normalizer_processor", "config": {"eps": 1e-08, "features": {}}},
        {"registry_name": "tokenizer_processor", "config": {"max_length": 200}},
        {"registry_name": "device_processor", "config": {"device": "cpu", "float_dtype": None}}]}
    post_src = {"name": "policy_postprocessor", "steps": [
        {"registry_name": "unnormalizer_processor", "config": {"eps": 1e-08, "features": {}}},
        {"registry_name": "absolute_actions_processor", "config": {"enabled": False}},
        {"registry_name": "device_processor", "config": {"device": "cpu", "float_dtype": None}}]}
    if tamper == "M49_compat_deleted_enabled_step":
        # 把 normalizer 也变成"生效中"（enabled=true）并一起删掉 ⇒ 删它就不是恒等
        for st in pre_src["steps"]:
            if st["registry_name"] == "normalizer_processor":
                st["config"]["enabled"] = True
    drop_pre = ["relative_actions_processor"]
    drop_post = ["absolute_actions_processor"]
    if tamper == "M49_compat_deleted_enabled_step":
        drop_pre = ["relative_actions_processor", "normalizer_processor"]
    # **深拷贝**：第一版用列表推导直接引用了 pre_src 里的 step dict，于是 M52
    # （改兼容侧 device_processor 的 config）连源侧一起改了 ⇒ 两侧相同、牙咬不住。
    # 缺陷类是"被测对象与被比对象不是两个对象"，与 ADR-C-014 同族。
    pre_cmp = {"name": "policy_preprocessor",
               "steps": [json.loads(json.dumps(st)) for st in pre_src["steps"]
                         if st["registry_name"] not in drop_pre]}
    post_cmp = {"name": "policy_postprocessor",
                "steps": [json.loads(json.dumps(st)) for st in post_src["steps"]
                          if st["registry_name"] not in drop_post]}
    if tamper == "M54_compat_no_deletion":
        pre_cmp = json.loads(json.dumps(pre_src))
        post_cmp = json.loads(json.dumps(post_src))
        drop_pre, drop_post = [], []
    if tamper == "M52_compat_undeclared_config_change":
        for st in pre_cmp["steps"]:
            if st["registry_name"] == "device_processor":
                st["config"] = {"device": "cuda", "float_dtype": "bfloat16"}
    if tamper == "M53_compat_reordered":
        pre_cmp["steps"] = list(reversed(pre_cmp["steps"]))
    # 参考实现（合成）：两处 `if not self.enabled: return transition`
    ref_dir = root / "tmp" / "b2_synthetic_lerobot_main_ref"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_path = ref_dir / "relative_action_processor.py"
    ref_lines_body = [
        '"""synthetic reference: lerobot main 的 relative/absolute actions processor"""',
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass",
        "class RelativeActionsProcessorStep:",
        "    enabled: bool = False",
        "",
        "    def __call__(self, transition):",
        "        if not self.enabled:",
        "            return transition",
        "        return transition.copy()",
        "",
        "",
        "@dataclass",
        "class AbsoluteActionsProcessorStep:",
        "    enabled: bool = False",
        "",
        "    def __call__(self, transition):",
        "        if not self.enabled:",
        "            return transition",
        '        raise RuntimeError("needs paired relative_step")',
    ]
    ref_body = "\n".join(ref_lines_body) + "\n"
    ref_path.write_text(ref_body)
    ref_guard_lines = [k + 1 for k, ln in enumerate(ref_lines_body)
                       if ln.strip().startswith("if not self.enabled:")]
    ref_blob = _git_blob_sha1(ref_path)
    # 合成世界用 **64 KiB** 代表 14.47 GB 的大权重，阈值（32 KiB）经 `ev["big_file_bytes"]` 注入：
    # 判据逻辑（超过阈值 ⇒ 必须软链、且软链必须落在源目录内）与真现场逐字相同，
    # 只是阈值不同。这么做是因为自检世界最后会 mv 到 NFS 回收站（NFS 已用 94%），
    # 不能为了一个变异真造 14 GB 文件。
    measured["big_file_bytes"] = 32 << 10
    if tamper == "M57_compat_step_in_registry":
        # 造一个"本机 lerobot 里其实**有**这两步"的假 venv ⇒ 删除前提不成立，必须红
        fv = (root / "fake_venv" / "lib" / "python3.11" / "site-packages"
              / "lerobot" / "processor")
        fv.mkdir(parents=True, exist_ok=True)
        (fv / "relative_action_processor.py").write_text(
            "from lerobot.processor.core import ProcessorStepRegistry\n\n\n"
            '@ProcessorStepRegistry.register(name="relative_actions_processor")\n'
            "class RelativeActionsProcessorStep:\n    pass\n\n\n"
            '@ProcessorStepRegistry.register(name="absolute_actions_processor")\n'
            "class AbsoluteActionsProcessorStep:\n    pass\n")
        measured["venv_override"] = str(root / "fake_venv")
    blob_claim = ref_blob
    if tamper == "M51_compat_blob_sha_mismatch":
        blob_claim = "0" * 40
    prose = ("被删的两步在 ckpt 里都是 enabled=false；lerobot main 的实现在 enabled=false 时"
             "`return transition`（恒等），见 %s blob sha %s 的 :%d 与 :%d。"
             "⇒ 过滤后的管线与原管线**数据流等价**。"
             % (str(ref_path.relative_to(root)), blob_claim,
                ref_guard_lines[0], ref_guard_lines[1]))
    compat_report = {
        "tool": "synthetic_a2_make_pi05_compat_dir.py",
        "morphology": "aloha_bimanual_14d",
        "src_weights_dir": str(ck), "compat_dir": str(cp),
        "installed_lerobot_registry_steps": ["device_processor", "normalizer_processor",
                                             "rename_observations_processor",
                                             "to_batch_processor", "tokenizer_processor",
                                             "unnormalizer_processor"],
        "kept_steps": ([{"file": "policy_preprocessor.json",
                         "registry_name": st["registry_name"]} for st in pre_cmp["steps"]]
                       + [{"file": "policy_postprocessor.json",
                           "registry_name": st["registry_name"]} for st in post_cmp["steps"]]),
        "dropped_steps": (
            [{"file": "policy_preprocessor.json", "registry_name": n,
              "config": {"enabled": False},
              "reason": "registry 里不存在，且 config.enabled 明确为 false"} for n in drop_pre]
            + [{"file": "policy_postprocessor.json", "registry_name": n,
                "config": {"enabled": False},
                "reason": "registry 里不存在，且 config.enabled 明确为 false"} for n in drop_post]),
        "refused_steps": [],
        "root_cause": ("ckpt 的 README 要求 lerobot git main；0.4.4 的 processor registry "
                       "没有这两步"),
    }
    if tamper != "M50_compat_no_equivalence_proof":
        compat_report["equivalence_argument"] = prose
    else:
        compat_report["equivalence_argument_note"] = ("（这一版把等价性说明拿掉了："
                                                      "模拟「删了但没自证」）")
    if tamper != "M55_compat_absent":
        (ck / "policy_preprocessor.json").write_text(
            json.dumps(pre_src, indent=2, ensure_ascii=False) + "\n")
        (ck / "policy_postprocessor.json").write_text(
            json.dumps(post_src, indent=2, ensure_ascii=False) + "\n")
        (ck / "config.json").write_text('{"model_type": "pi05"}\n')
        (ck / "README.md").write_text("synthetic pi05_base ckpt (B2 selftest)\n")
        big = ck / "model.safetensors"
        if not big.exists():
            big.write_bytes(b"\0" * (64 << 10))      # 64 KiB 代表 14.47 GB（阈值 32 KiB）
        cp.mkdir(parents=True, exist_ok=True)
        (cp / "policy_preprocessor.json").write_text(
            json.dumps(pre_cmp, indent=2, ensure_ascii=False) + "\n")
        (cp / "policy_postprocessor.json").write_text(
            json.dumps(post_cmp, indent=2, ensure_ascii=False) + "\n")
        for n in ("config.json", "README.md", "model.safetensors"):
            link = cp / n
            if not link.exists():
                if tamper == "M56_compat_weights_copied" and n == "model.safetensors":
                    link.write_bytes((ck / n).read_bytes())   # 复制体（不是软链）⇒ 必须红
                else:
                    link.symlink_to(ck / n)
        rep_path = root / COMPAT_REPORT_CANDIDATES[0]
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        rep_path.write_text(json.dumps(compat_report, indent=1, ensure_ascii=False) + "\n")

    return root, a2, out_dir, measured


MUTATIONS = [
    # (id, tamper, 目标 check, 期望, 说明)；NOT_RED/PASS 是**反向**变异，防恒红
    ("M1", "M1_lerobot_drift", "V-pi05-1", "RED",
     "新环境 lerobot 0.4.5 而已验收两套是 0.4.4 ⇒ 断点变更必须被点名（裁定 34.1/39.1）"),
    ("M2", "M2_transformers_absent", "V-pi05-1", "RED",
     "transformers 未装（`pip install lerobot==0.4.4` 的真实后果）⇒ π₀.₅ 加载必失败"),
    ("M3", "M3_transformers_below_floor", "V-pi05-1", "RED",
     "transformers 4.30.0（maniskill_probe 的实测值）⇒ 版本偏实测锚 `%s` **且** π₀.₅ 硬卫语句不过"
     "（其 `check.py` 只接受 4.53.2/4.53.3）⇒「import 成功但加载报错」。"
     "**判据已按裁定 78.8 改**：红的成因是偏锚 + 卫语句，**不是**低于声明下界 4.57.1"
     % TRANSFORMERS_MEASURED_ANCHOR, TF_CAUSE_VERSION),
    ("M4", "M4_transformers_unrecorded", "V-pi05-1", "RED",
     "实测已装 `%s`（git 形态，lock 行是 direct-url、**不含版本串**）但 env_manifest 里也查不到"
     " ⇒ 裁定 34.1「实际装成版本必须写进产物」。改判后这条变异**只改 manifest 一处**，"
     "好让红的成因唯一（旧版靠抹掉 lock pin 命中，改判后那条路径会先被偏锚/无 commit 盖过）"
     % TRANSFORMERS_MEASURED_ANCHOR),
    ("M5", "M5_torch_cu128", "V-pi05-4", "RED",
     "**D 点名的变异**：torch 2.6.0+cu124 → 2.9.0+cu128 ⇒ 必须红"),
    ("M6", "M6_dryrun_touches_torch", "V-pi05-4", "RED",
     "resolve_dryrun 里出现 torch 的 Collecting/Downloading/uninstall/2.6.0->2.9.0 ⇒ 必须红"),
    ("M7", "none", "V-pi05-4", "NOT_RED",
     "**D 点名的反向变异**：dryrun 只新增 transformers 4.57.1、不动 torch 栈 ⇒ 必须绿（否则恒红）"),
    ("M8", "M8_sha_mismatch", "V-pi05-2", "RED",
     "盘上 model.safetensors 字节被改而 receipt 的 sha256 未变 ⇒ 复算必须抓到"),
    ("M9", "M9_postprocessor_missing", "V-pi05-2", "RED",
     "policy_postprocessor.json 不在盘上 ⇒ lerobot 静默走默认归一化（最坏的一类假绿）"),
    ("M10", "M10_files_short", "V-pi05-2", "RED",
     "receipt 只声明 6/7 份（半成品快照，snapshot_download 被 429 时 exit 0 的同型）"),
    ("M11", "M11_channel_absent", "V-pi05-3", "RED",
     "receipt 无 channel 也无 host/url ⇒ 「走 ModelScope 还是 hf-mirror」无留痕"),
    ("M12", "M12_external_unmarked", "V-pi05-3", "RED",
     "license 与他人显存报告裸露在实测块里 ⇒ 裁定 36.4 跨口径并列"),
    ("M13", "M13_measured_in_external", "V-pi05-3", "RED",
     "**反向混算**：把 sha256/total_bytes 塞进 external_unverified 块 ⇒ 把实测降级成传闻，同样红"),
    ("M14", "M14_forbidden_venv", "V-pi05-1", "RED",
     "venv realpath 落在 maniskill_probe ⇒ 裁定 39.1 明令不得用它跑 π₀.₅。**本条复现的是那个 venv "
     "的真实形态**（transformers 4.30.0、无定制分支 check.py）⇒ 它会**同时**打红 V-pi05-1 与 "
     "V-pi05-5，这个附带翻动已在 `MUTATION_COLLATERAL['M14']` 里带成因声明；"
     "「禁用 venv」这条规则**自己**能不能红，由 M66 的隔离世界证明", "maniskill_probe"),
    ("M66", "M66_forbidden_venv_tf_compliant", "V-pi05-1", "RED",
     "**隔离证明（裁定 86.6-3 `mutant_specificity_required`）**：与 M14 的唯一差别是 transformers "
     "保持基线合规 ⇒ 世界上只剩「venv 路径违规」一个缺陷，要求 V-pi05-1 红、且**只产生 1 条违例**、"
     "且 V-pi05-5 保持 PASS。为什么这三件事合起来就构成证明：V-pi05-5 PASS ⟹ 四条 blocking 的 "
     "①②③（版本==锚 / commit 在 lock / 卫语句 True）都成立，逐位核验件也在场 ⟹ ④ 成立；"
     "lerobot 锚未动 ⟹ 版本锚那一段成立；⇒ V-pi05-1 里**唯一还能红的**就是禁用 venv 这条规则。"
     "没有 M66 时，M14 的红点分不出是路径规则还是卫语句规则红的 —— 一个翻不动**目标**规则的"
     "变异体，与一个恒真的牙同样危险。**注意这是一个现实中不可能存在的世界**（真的 "
     "maniskill_probe 里 transformers 就是 4.30.0），合成世界允许它，因为它只用来隔离一条判据"
     "（裁定 78.1 `mutant_construction_isolation`）", "裁定 39.1 **明令**不得用它跑", 1),
    ("M15", "M15_lock_cuda_blind", "V-pi05-4", "RED",
     "lock 仍写 torch==2.6.0，但活体是 2.6.0+cu121 ⇒ 证明「事实源必须是活体探针」这颗牙真的在"),
    ("M16", "M16_evidence_missing", "__verdict__", "NOT_PASS",
     "**A2 未交件（目录空）⇒ 准入必须是 UNJUDGED_evidence_missing，绝不能是 PASS**（裁定 14 同型）"),
    ("M17", "M17_accepted_unprobed", "V-pi05-1", "RED",
     "已验收 venv 探不到 ⇒ 版本锚**无法比对**，必须红而不是「默认相同」（空洞真）"),
    ("M18", "M18_teeth_stale", "A0", "RED",
     "mutation_verdict.json 的 gate_build 与当前脚本构建不符（改了判据没重跑自检）⇒ 红"),
    ("M19", "none", "__all_pi05__", "PASS",
     "**反向基线**：干净的合成世界里八条牙必须全绿（证明它们不是恒红）"),
    ("M20", "M14_license_missing", "V-pi05-2", "RED",
     "receipt 缺 license ⇒ Gemma Terms 没进证据链（D→A2 §3.4）"),
    ("M21", "M21_dryrun_at_anchor_fresh", "V-pi05-4", "NOT_RED",
     "**反向（钉住第一版的假红）**：空 venv 一次性解析里 `+ torch==2.6.0+cu124` 是**按锚值安装**，"
     "不是挪动 ⇒ 必须绿"),
    ("M22", "M22_dryrun_multisection", "V-pi05-4", "NOT_RED",
     "**反向（A2 的真实 dryrun 形态）**：STAGE 1 含锚值安装行、STAGE 2 不含 torch ⇒ 分段解析必须绿"),
    ("M23", "M23_dryrun_off_anchor_install", "V-pi05-4", "RED",
     "dryrun 里 `+ torch==2.9.0+cu128` / `+ torchvision==0.24.0+cu128` ⇒ 装成值离锚，必须红"),
    ("M24", "M24_dryrun_unversioned_live_ok", "V-pi05-4", "NOT_RED",
     "**反向**：只有 `Downloading torch (732.9MiB)`（无版本号）但活体值 == 锚值 ⇒ 由探针定案，绿"),
    ("M25", "M25_dryrun_unversioned_live_bad", "V-pi05-4", "RED",
     "同样无版本号，但活体是 2.6.0+cu121 ⇒ 探针定不了案，必须红（不许拿「无版本号」当通过）"),
    ("M26", "M26_anchor_drift", "V-pi05-4", "RED",
     "已验收 venv 的活体 torch 变成 2.7.0+cu126 ⇒ 锚常量与事实源不符，必须红并报 D 更新锚"),
    ("M27", "M27_dryrun_uninstall_torch", "V-pi05-4", "RED",
     "dryrun 里 ` - torch==2.6.0+cu124`（卸载 torch 栈）⇒ 必须红"),
    # ---- 第三批：receipt 键名口径（第一版把「无从比对」记成「比对通过」，这是恒真牙）----
    ("M28", "M28_receipt_key_blind", "V-pi05-2", "RED",
     "receipt 用本闸读不到的键名（integrity_b64/extent_v2）⇒ 无从比对必须**红**，"
     "不得落进 else 记成「哈希一致」（A2 真实 receipt 的键名就是 expected_sha256_modelscope/actual_size）"),
    ("M29", "M29_receipt_a2_shape", "V-pi05-2", "NOT_RED",
     "**反向（A2 真实 receipt 形态）**：多渠道期望值 + 自述值，且有一个文件 modelscope 通道"
     "对不上但 hf_lfs 通道对得上（真实案例 = `.gitattributes`）⇒ 必须绿，不得造假红"),
    ("M30", "M30_receipt_claim_only", "V-pi05-2", "UNJUDGED",
     "只有 receipt 自述哈希、无远端期望值 ⇒「没被动过」成立但「下对了东西」未证 ⇒ 弃权，"
     "**不得**记成 PASS（三值纪律：证据缺失 ⇒ ok=null）"),
    ("M31", "M31_receipt_a2_full", "__all_pi05__", "PASS",
     "**反向（A2 真实 receipt 的完整结构）**：无顶层 channel 键、remote_hf/remote_modelscope 远端块、"
     "逐文件 sha256_verdict、license 带 kind/source、一个文件只有 git blob sha1 能定案 ⇒ 全绿。"
     "这条变异证明「判红」不是因为 receipt 结构不合本闸的想象（防恒红，同 M21/M22 的教训）"),
    # ---- 第四批：transformers 的**功能锚**与 git 溯源（版本区间锚被现场证伪，见 RR-B2-06）----
    ("M33", "M33_pi05_tf_check_false", "V-pi05-5", "RED",
     "lerobot π₀.₅ 的硬校验 `check_whether_transformers_replace_is_installed_correctly()` 返回 False "
     "⇒ `PI05Policy.from_pretrained` 必抛 ValueError（A2 用 PyPI 4.57.6 实测到过）。"
     "版本区间看着合规也拦不住它 ⇒ 必须有一条以**功能**为判据的牙"),
    ("M34", "M34_pi05_tf_git_ok", "V-pi05-5", "PASS",
     "**反向（A2 现场的真实形态）**：transformers 来自 git 分支 fix/lerobot_openpi@dcddb970、"
     "版本字符串 4.53.3（低于 §8.1 下界）、功能校验 True、lock 里是 direct-url 形态且带 commit "
     "⇒ V-pi05-5 必须绿。**裁定 78.8 之后本条与基线同形（幂等）**：同一世界上 V-pi05-1 "
     "现在也**必须绿**（四条 blocking 全中：版本 == 锚 / lock 有锚 commit / 卫语句 True / "
     "812-812-0-0），RR-B2-06 已由裁定 78.8 + 69.3 关闭。保留本条是为了钉住"
     "「换判据不删牙」——它仍是 V-pi05-5 的反向变异，且世界构造改一次就会立刻被它抓到"),
    ("M35", "M35_pi05_tf_git_no_commit", "V-pi05-5", "RED",
     "同样是 git 安装、功能校验也过，但 lock 只写 `transformers==4.53.3`、commit 只出现在 dryrun "
     "⇒ 版本字符串认不出是哪一次 build，产物不可复现（裁定 34.1；dryrun 是计划书不算装成记录，同 M4）"),
    ("M32", "M32_receipt_a2_unmarked_external", "V-pi05-3", "RED",
     "同样是 A2 结构，但 `download.reported_size`（远端报的字节数）与 `measured_rate_MBps`（本机实测）"
     "同块无标记、`verdict.license_ok`（外部事实的派生判定）与本地判定同块无标记 ⇒ 必须红。"
     "这条钉住「放宽标记词表」没有把裁定 36.4 的实质要求放掉"),
    # ---- 第三批变异：钉住 V-pi05-6（交件自述可用性 vs 独立运行时复核）----
    # 这六条的关键不是"能不能红"，而是**红的时候判词有没有点名成因**：
    # M36 与 M38 都是 RED，但一个是"交件比对口径造假红"、一个是"冻结栈真漂移"，
    # 修法完全不同（前者 A2 改 manifest 口径，后者 D 登记断点变更）。只判状态不判成因，
    # 就等于把两种世界混成一个红点 —— 所以这两条带 `must_contain`。
    ("M36", "M36_manifest_metadata_only", "V-pi05-6", "RED",
     "**A2 现场 19:11 的真实形态**：assertions 9/9 全 true，但 `frozen_stack_drift=[torch,torchvision]` "
     "⇒ 交件自述 `env_usable=false`。B2 独立探针显示两侧 runtime 逐字相同（都是 2.6.0+cu124 / cuda 12.4），"
     "只有 dist-info 元数据串不同（`2.6.0` vs `2.6.0+cu124`）⇒ 必须红，且判词必须点名成因是"
     "「交件比对口径造成的假红」，不得写成「冻结栈漂移」", "metadata_only"),
    ("M37", "M37_manifest_clean_benign_diff", "V-pi05-6", "PASS",
     "**反向（防恒红）**：交件的 `differing_packages` 非空（transformers/mujoco/scipy，A2 有意引入），"
     "但 `frozen_stack_drift` 为空、`env_usable=true` 且与 A2 自己的公式一致 ⇒ 必须绿。"
     "这条钉住「看到差异就红」不是本条牙的判据"),
    ("M38", "M38_manifest_real_drift", "V-pi05-6", "RED",
     "π₀.₅ 侧 runtime torch 真的换成 2.7.0+cu126（cuda 12.6），基线仍 2.6.0+cu124，交件也报了 drift "
     "⇒ 必须红且点名 `real_runtime_drift`（与 M36 的成因**不同**：这一种要 D 登记断点变更，"
     "不是改 manifest 口径就能了的）", "real_runtime_drift"),
    ("M39", "M39_manifest_no_usability_keys", "V-pi05-6", "UNJUDGED",
     "旧式交件：只有版本清单，没有 assertions / env_usable / frozen_stack_drift ⇒ 自述可用性"
     "**无从判**，必须弃权（ok=null），绝不得因为「没看到红」记成 PASS（三值纪律）"),
    ("M40", "M40_manifest_selfcontradict", "V-pi05-6", "RED",
     "交件自相矛盾：assertions 里 V5=False，却写 `env_usable=true`（与 A2 自己在 "
     "`a2_env_manifest.py:313` 写下的公式不符）⇒ 必须红。这条牙的另一半：不光防假红，也防**假绿**",
     "自相矛盾"),
    ("M41", "M41_manifest_drift_unprobeable", "V-pi05-6", "RED",
     "交件点了 drift 且自称 env_usable=false，但基线 venv 探不到（解释器不存在）⇒ 成因无从归因。"
     "仍必须红（准入不得建立在自称不可用的交件上），判词要写「无法独立复核成因」，"
     "**不得**降级成 PASS，也不得因为归因不了就弃权", "无法独立复核"),
    ("M42", "M42_manifest_nested_disagree", "V-pi05-6", "RED",
     "**真交件结构**逼出来的第 7 条变异：A2 的 manifest 把 `frozen_stack_drift` 写在 "
     "`verdict.*` 与 `baseline_comparison.*` **两处**（顶层没有）。两处值不一致时"
     "（verdict 说空、baseline_comparison 说 torch）必须红，且判词点名「交件内部不一致」"
     "—— B2 **不得**挑一个采信，挑哪个都是替 A2 决定它说了什么", "自相矛盾"),
    # ---- 第四批变异：钉住 V-pi05-7（控制频率三元组，裁定 45.5）----
    # 这批的关键是**双向**：既要有"折算与声明不符必须红"，也要有"A2 的真实形态必须绿"——
    # A2 的 `naive_pitfall` 组是**故意**不自洽的（它在演示"只改 DT 拿不到 30 Hz"这个坑），
    # 逐条要求全部相符就会把诚实陈述判成红（本仓第 N 起假红）。M46 就是钉这个边界的。
    ("M43", "M43_hz_triple_inconsistent", "V-pi05-7", "RED",
     "operative 组（target）声明 control_hz=30.5，但 1/(timestep×decimation)=30.0、"
     "1/control_timestep=30.5 只对上一半且声明值与折算值不符 ⇒ 裁定 45.5「折算值与声明值不符判红」",
     "折算值与声明值不符"),
    ("M44", "M44_hz_missing_decimation", "V-pi05-7", "WARN",
     "operative 组只给 control_timestep 与 Hz，**没有** timestep 与 decimation ⇒ 缺 (a)，判黄不判红"),
    ("M45", "M45_hz_contract_3125", "V-pi05-7", "RED",
     "新增 `contract_stack` 组：timestep=1/500、decimation=16、control_hz=**31.25**（三元组自洽！）"
     "⇒ 仍必须红：裁定 45.1 明令 31.25 Hz 是 D 为凑整数 decimation 取的 convenient 值，"
     "**不得当契约值**（自洽不等于合规，这条钉住「只查算术不查口径」的漏洞）", "31.25"),
    ("M46", "none", "V-pi05-7", "PASS",
     "**反向（防假红）**：A2 的真实形态 —— `as_is` 50 Hz（描述现状、自述不在 QC 区间）、"
     "`target_30hz` 三元组自洽、`naive_pitfall` **故意**让 1/(ts×dec) 与 1/cts 不一致、"
     "外加 chunk 时间尺度三方案 ⇒ 必须绿。这条钉住「descriptive 组的诚实不自洽不判红」"),
    ("M47", "M47_hz_no_relation", "V-pi05-7", "WARN",
     "把 chunk_timescale_options 与 in_qc_band_29_31 都拿掉 ⇒ 缺 (c)「与示范 30 Hz 的关系」，判黄"),
    ("M48", "M48_hz_operative_out_of_band_no_plan", "V-pi05-7", "RED",
     "operative 组声明 50 Hz（QC 合格区间 [29,31] 之外）且整份产物**没有**任何重采样方案 ⇒ "
     "裁定 45.4：原生频率非 30 Hz 必须显式声明方案并报 D 裁，不许静默选"),
    ("M58", "M58_hz_doc_absent", "V-pi05-7", "UNJUDGED",
     "控制频率交件压根不存在 ⇒ 三元组无从核，必须弃权（ok=null）。"
     "**不得**因为「没看到红」记成 PASS（三值纪律）"),
    # ---- 第五批变异：钉住 V-pi05-8（兼容目录删步骤，裁定 44.2）----
    ("M49", "M49_compat_deleted_enabled_step", "V-pi05-8", "RED",
     "把 `normalizer_processor` 的 config.enabled 改成 **true** 再一起删掉 ⇒ 删的不是恒等步骤，"
     "数据流被改了。裁定 44.2 只允许删「registry 缺失**且** enabled 明确 false」的步骤", "enabled"),
    ("M50", "M50_compat_no_equivalence_proof", "V-pi05-8", "RED",
     "删了步骤但交件里**没有**任何等价性说明（既无结构化 evidence 也无散文）⇒ "
     "裁定 44.2 要求代码级自证，不是读 config 就下结论", "无自证"),
    ("M51", "M51_compat_blob_sha_mismatch", "V-pi05-8", "RED",
     "等价性说明里点名的参考文件存在，但声明的 git blob sha1 与 B2 复算值不符（全 0 假 sha）"
     "⇒ 证据不是被点名的那个版本，必须红", "blob sha1"),
    ("M52", "M52_compat_undeclared_config_change", "V-pi05-8", "RED",
     "兼容目录除了删两步，还**改了**保留步骤 `device_processor` 的 config（cpu→cuda、"
     "float_dtype→bfloat16）⇒ 未声明的改动（裁定 44.4：改 bf16 必须单独报，不许与 fp32 混表）"),
    ("M53", "M53_compat_reordered", "V-pi05-8", "RED",
     "保留步骤的顺序被整体反转 ⇒ processor 管线是**有序**的，换序不是恒等变换"),
    ("M54", "M54_compat_no_deletion", "V-pi05-8", "PASS",
     "**反向（防恒红）**：兼容目录与源 ckpt 逐字相同（一步都没删）⇒ 必须绿。"
     "这条钉住本牙判的是「删得对不对」，不是「有没有兼容目录」"),
    ("M55", "M55_compat_absent", "V-pi05-8", "UNJUDGED",
     "既没有兼容目录也没有报告 ⇒ 无从判，必须弃权（ok=null），**不得**记成 PASS（三值纪律）"),
    ("M56", "M56_compat_weights_copied", "V-pi05-8", "RED",
     "兼容目录里的 `model.safetensors` 是**复制体**而不是软链回源目录 ⇒ ①NFS 已用 94%，"
     "复制 14.47 GB 不可接受；②复制体会让「原始权重目录只读」无法证明（裁定 44.2）。"
     "合成世界用 64 KiB 代表大权重、阈值经 ev 注入，判据逻辑与真现场逐字相同", "实体文件"),
    ("M57", "M57_compat_step_in_registry", "V-pi05-8", "RED",
     "造一个「本机 lerobot 里其实**有**这两步」的假 venv（注册名逐字相同）⇒ "
     "「registry 缺失」这个删除前提不成立，删它就不是恒等变换。"
     "这条钉住 B2 **自己扫 site-packages** 复核前提，而不是采信 A2 的 root_cause", "确实存在于"),
    # ---- 第六批：裁定 78.8 的四条 blocking 判据（V-pi05-1 改判之后**必须有专属牙**）----
    # 改判最容易出的事故是「删掉旧判据、新判据没有牙」⇒ 那等于把 V-pi05-1 变成恒真闸
    # （裁定 27.1）。故四条 blocking 各配一条变异体，且**用 must_contain 钉住成因键**：
    # 四种世界都是 RED，只判状态分不开（与 M36/M38 同理），而成因不同 ⇒ 修法完全不同。
    ("M59", "M59_tf_version_off_anchor", "V-pi05-1", "RED",
     "装了**满足 §8.1 声明区间** `>=%s,<%s` 的 PyPI 4.57.6 ⇒ 仍必须红：lerobot 的 π₀.₅ 硬卫语句"
     "拒绝它（A2 实测 `ValueError: An incorrect transformer version is used`），也就没有逐位核验件。"
     "这条钉住裁定 78.8 的实质 ——「声明区间合规 ≠ 能跑 π₀.₅」，同时证明改判**没有**把牙拔掉"
     % (TRANSFORMERS_FLOOR, TRANSFORMERS_CEIL), TF_CAUSE_VERSION),
    ("M60", "M60_tf_commit_off_anchor", "V-pi05-1", "RED",
     "版本串对（`%s`）、卫语句也过，但装的是**另一次 build**（commit 偏锚）⇒ 必须红且点名 commit："
     "git 构建的版本串认不出是哪一次提交，只有 `direct_url.json` 的 commit 与 lock 的 direct-url 行能认"
     "（裁定 34.1）。这条是 D 点名的第 ① 条变异（改 commit ⇒ 红）"
     % TRANSFORMERS_MEASURED_ANCHOR, TF_CAUSE_COMMIT),
    ("M61", "M61_loadver_n_differ", "V-pi05-1", "RED",
     "`load_verification.json` **自称** `verdict=%s`，但它自己的计数不同意"
     "（`n_differ=3`、`n_bitwise_exact=809/812`）⇒ 必须红：判据读的是**四个计数**，不是那句自述"
     "（与「只读 summary 不读逐条」同族缺陷）。这条钉住裁定 78.8 的第 ④ 条 blocking"
     % LOAD_VERIFY_VERDICT_ANCHOR, TF_CAUSE_LOADVER),
    ("M62", "M62_loadver_absent", "V-pi05-1", "UNJUDGED",
     "环境本身合规（版本 == 锚、commit 在 lock、卫语句 True），但 `load_verification.json` **不存在**"
     " ⇒「π₀.₅ 真加载过 + 812 张量逐位」这一条**无法判** ⇒ 必须弃权（ok=null），"
     "**不得**读成通过（三值纪律；裁定 78.2：UNJUDGED 计入非绿，顶层 `ok` 因此仍为 false）"),
    ("M63", "M63_tf_pypi_same_version_no_guard", "V-pi05-1", "RED",
     "PyPI 的 **4.53.3**：版本号与实测锚**逐字相同**，但没有定制分支的 `check.py` ⇒ 卫语句 False、"
     "无 commit、无逐位核验件 ⇒ 必须红。这条是 D 点名的第 ③ 条变异，专门防"
     "「版本号相同就放过」（只比版本串的闸在这个世界上会假绿）", TF_CAUSE_GUARD),
    # ---- 第七批：裁定 49.5 的闭合载体（渠道 sidecar）——「引用 ≠ 采信」必须有牙 ----
    # D 让 B2「只在闸里引用这份 sidecar」。若引用等于采信，那 V-pi05-3 的渠道段就变成
    # **恒真闸**（sidecar 说 PASS 就 PASS，裁定 27.1）。所以本闸复算它自述的四件事，
    # 并用这两条变异证明复算真的会红。
    ("M64", "M64_sidecar_mixed_dishonest", "V-pi05-3", "RED",
     "sidecar 顶层自称 `%s`，但逐文件记录里只有 1 个渠道 ⇒ **mixed 不诚实**（裁定 49.5 的反向："
     "只有一个渠道时必须写那个渠道）。同时它自己的 C1 也非 true ⇒ 证明本闸读的是逐条 `checks`、"
     "不是那句 `verdict.PASS`" % CHANNEL_TOP_LEVEL_MIXED, "不诚实"),
    ("M65", "M65_sidecar_sha_claim_false", "V-pi05-3", "RED",
     "sidecar 自称「receipt 未被改写」，但它记的 sha256 与 B2 **复算**的值不符 ⇒ 那份闭合已失效"
     "（或指的不是这份 receipt，ADR-C-014 同型）。这条钉住「B2 复算 receipt 的 sha、不采信自述」",
     "未被改写"),
]


def _status_of(rep, want_check):
    if want_check == "__verdict__":
        return None
    if want_check == "__all_pi05__":
        sts = [c["status"] for c in rep.checks if c["id"] in CHECKS_PI05]
        return ",".join(sts) if sts else "ABSENT"
    tgt = [c for c in rep.checks if c["id"].startswith(want_check)]
    return tgt[0]["status"] if tgt else "ABSENT"


# ---------------------------------------------------------------------------
# 裁定 86.6-3 `mutant_specificity_required`（挂在红线 `tooth_must_be_mutant_proven` 之下）
# ---------------------------------------------------------------------------
# D 的原话：「**登记的变异体不是证明。变异体必须被实测证明『精确翻动目标牙、且只翻动目标牙』**
# （specificity），而这个证明本身必须由机器元判据看守，不得以文书登记形态存在。
# 一个翻不动目标牙的变异体，与一个恒真的牙同样危险 —— 它让『已验证』以文书形态活下来。」
# ⇒ 本闸此前只有 `must_contain`（钉**成因键**，即"红在哪一条"），没有钉**作用面**
#   （即"只红了那一条"）。两者是特异性的两半，缺一半就还能"以文书形态活下来"。
N_TRANSCRIPTION_TEETH = 11          # T1–T11：`_transcribe_guard` 的转录层（裁定 78.4 的①·乙层）
N_META_SPECIFICITY_TEETH = 4        # T12–T15：`_specificity_of` **自己**（元判据必须有牙，裁定 27.1）
# id 只在这一处派生（自检产物与判词 `teeth` 块共用同一份），避免两处各算一份而漂移
# （裁定 92.6 的同族观察：凡是「取上一个/取典型值」的地方，都要问一句「我取的这个量，
# 是不是我真正要指的那个」）。
META_SPECIFICITY_IDS = ["T%d" % i for i in
                        range(N_TRANSCRIPTION_TEETH + 1,
                              N_TRANSCRIPTION_TEETH + N_META_SPECIFICITY_TEETH + 1)]

# 归一台账层（N 系列）：`A3_delegated_docs_normalized` **自己**的牙。
# 为什么单列一层：A3 不是"世界状态"的判据（八条 π₀.₅ 牙那一层），也不是"转录上游"的判据
# （T 系列那一层），它是**清单/索引件与磁盘对账**的判据（裁定 92.3-ii）⇒ 它的变异体必须
# 摆的是 `normalized/` 的目录树，而不是 `_mk_world` 的 A2 交件。三层各证一件事，合并计数
# 就等于把"哪一层证明了什么"抹掉（与 `layers_why_split` 同一条纪律）。
N_NORMALIZATION_TEETH = 3           # N1–N3：台账 vs 磁盘（ii）、三值 None 不判红（反向）、对 D 对账
NORMALIZATION_TEETH_IDS = ["N%d" % i for i in range(1, N_NORMALIZATION_TEETH + 1)]

# 顶层口径层（O 系列）：`ok_of` / `admission_of` / `EXIT` 三件**判据本身**的牙。
# 为什么单列一层：它既不测世界状态（M 层）、也不测转录（T 层）、也不测台账-磁盘对账（N 层），
# 它测的是「判据函数在四种计数组合下各给什么」+「判据与散文/退出码是否同源」。
# 起因 = RR-B2-09 改判（裁定 93 / D→B2 §四-1：`ok` 是唯一失败判据、UNJUDGED 计入非绿、
# **WARN 不计失败但必须登记**）。一次改判若无牙，下一版可以悄悄改回去；而**往严改也一样危险**
# —— 旧口径（连 WARN 也算 `ok=false`）会把上游一次合法的 RED→WARN 改判（裁定 93.1）
# 变成本闸的二次判死。⇒ O1 钉改判的正向、O2 钉"不许放宽过头"、O3/O4 钉两个恒值方向、
# O5 钉同源（代码与散文、`ok` 与退出码）。
N_VERDICT_CALIBER_TEETH = 5         # O1–O5
VERDICT_CALIBER_TEETH_IDS = ["O%d" % i for i in range(1, N_VERDICT_CALIBER_TEETH + 1)]

# 全局作用域的目标：这两类变异动的**就是整个世界**（M16 = A2 未交件、M19/M31 = 干净世界），
# 「只翻动目标牙」对它们在语义上不适用 ⇒ **显式声明不适用**（同裁定 91.2 的
# `authority_scope.does_not_apply_to` 写法），不静默放过：产物里写 `why_not_enforced`。
SPECIFICITY_GLOBAL_TARGETS = ("__verdict__", "__all_pi05__")

# 每个变异体**允许**附带翻动的牙（已声明的 collateral）。纪律两条：
#   ① 一条附带翻动必须有一个**物理成因**（同一个世界改动同时违反了另一条判据），
#      并把这个成因写在 `why` 里 —— 写不出成因的不许声明，去改变异体构造
#      （裁定 78.1 `mutant_construction_isolation`：变异体构造须隔离）；
#   ② 表里没有的 id 出现附带翻动 ⇒ `all_ok=false`，进而让正式判定里的 `A0_teeth_current`
#      判红 ⇒ 特异性不成立**不会**只停在自检里，它会挡住准入。
# 本轮实测（`--selftest`，65+1 条世界层变异）：**10 条**有附带翻动，逐条查过成因后分成三族。
# 三族里**只有一族是构造缺陷**（族 C 的 M14），已用 M66 的隔离世界补上证明；另两族是
# **判据本身的设计后果**，改构造也改不掉 —— 除非把 D 的判据拆开，而 B2 无权这么做。
# 每条都必须写出物理成因；写不出成因的按纪律不许声明（去改构造）。
MUTATION_COLLATERAL = {
    # ---- 族 A：V-pi05-1 与 V-pi05-5 **共享 transformers 的事实源**（裁定 78.8 的设计后果）----
    # 裁定 78.8 把「③ lerobot 的 π₀.₅ 硬卫语句真跑通过」写进了 V-pi05-1 的四条 blocking，
    # 而 V-pi05-5 本来就是那条卫语句的专属牙 ⇒ 两颗牙读**同一个事实**。任何破坏卫语句/版本/
    # commit 的世界必然同时打红两者。这不是构造缺陷：要隔离就得把 D 定的 blocking ③ 从
    # V-pi05-1 里拿掉，那是改判据（B2 无权，M26 立的规矩）。
    "M2": {"ids": ["V-pi05-5_transformers_pi05_ready"],
           "why": "transformers **未装** ⇒ V-pi05-5 要 import 的 "
                  "`transformers.models.siglip.check` 根本不存在，卫语句无从为 True ⇒ 必然同红",
           "family": "A_shared_transformers_fact_source"},
    "M3": {"ids": ["V-pi05-5_transformers_pi05_ready"],
           "why": "transformers 4.30.0 没有定制分支自带的 `check.py` ⇒ 卫语句 False，"
                  "而那正是 V-pi05-5 的判据本体 ⇒ 必然同红",
           "family": "A_shared_transformers_fact_source"},
    "M59": {"ids": ["V-pi05-5_transformers_pi05_ready"],
            "why": "PyPI 4.57.6 被 lerobot 的 π₀.₅ 硬卫语句**拒绝**（A2 实测 "
                   "`ValueError: An incorrect transformer version is used`）⇒ V-pi05-5 同红。"
                   "**这个同红恰恰是裁定 78.8 的实质**：声明区间合规 ≠ 能跑 π₀.₅",
            "family": "A_shared_transformers_fact_source"},
    "M63": {"ids": ["V-pi05-5_transformers_pi05_ready"],
            "why": "PyPI 的 4.53.3 版本号与实测锚逐字相同、但没有定制分支的 `check.py` ⇒ "
                   "卫语句 False ⇒ V-pi05-5 同红（与 M59 同一机制，差别在版本号是否偏锚）",
            "family": "A_shared_transformers_fact_source"},
    # ---- 族 A'：反方向（目标牙是 V-pi05-5，附带翻动 V-pi05-1）----
    "M33": {"ids": ["V-pi05-1_version_anchor"],
            "why": "卫语句 False ⇒ V-pi05-1 的 blocking ③（裁定 78.8 明写的那一条）也不中 ⇒ "
                   "同红。**设计上的共享**，不是构造缺陷",
            "family": "A_shared_transformers_fact_source"},
    "M35": {"ids": ["V-pi05-1_version_anchor"],
            "why": "lock 里没有 git commit ⇒ V-pi05-1 的 blocking ②（装成记录里必须有 commit）"
                   "也不中 ⇒ 同红。同上，设计上的共享",
            "family": "A_shared_transformers_fact_source"},
    # ---- 族 B：三颗牙**共享同一个比对基线**（两套已验收 venv 的活体实测值）----
    # V-pi05-1 的 lerobot 版本锚、V-pi05-4 的冻结栈锚、V-pi05-6 的漂移归因，都要拿已验收 venv
    # 当基线。基线探不到 ⇒ 三颗牙同时失去比对对象。这也是设计后果：把基线换成常量就等于
    # 承认「默认相同」（M17 本来要抓的就是这个空洞真）。
    "M17": {"ids": ["V-pi05-4_torch_stack_frozen"],
            "why": "已验收 venv 探不到 ⇒ V-pi05-4 的冻结栈比对也失去基线（它同样以两套已验收 "
                   "venv 的实测值为锚，不以常量为锚）⇒ 同红",
            "family": "B_shared_accepted_venv_baseline"},
    "M41": {"ids": ["V-pi05-1_version_anchor", "V-pi05-4_torch_stack_frozen"],
            "why": "与 M17 同一机制（基线 venv 的解释器不存在）⇒ 两颗以已验收 venv 为基线的牙"
                   "同时无法比对。V-pi05-6 是本条的目标牙（要求「无法独立复核成因」仍判红）",
            "family": "B_shared_accepted_venv_baseline"},
    # ---- 族 C：世界上**真的有**那个缺陷（不是判据重叠，是两个独立缺陷同时存在）----
    "M38": {"ids": ["V-pi05-4_torch_stack_frozen"],
            "why": "这个变异把 π₀.₅ 侧 runtime torch 真的换成 2.7.0+cu126 ⇒ V-pi05-4 的活体锚"
                   "（`%s` / cuda `%s`）也**真的**被违反了。这是想要的形态：两条互相独立的牙"
                   "抓住同一个真漂移（V-pi05-6 从交件自述侧抓、V-pi05-4 从活体探针侧抓）"
                   % (TORCH_ANCHOR, TORCH_CUDA_ANCHOR),
            "family": "C_world_really_has_two_defects"},
    "M14": {"ids": ["V-pi05-5_transformers_pi05_ready"],
            "why": "M14 复现的是 maniskill_probe 的**真实**形态（transformers 4.30.0、无定制分支 "
                   "`check.py`）⇒ 卫语句 False，V-pi05-5 同红。**这一条是本表里唯一带构造缺陷"
                   "性质的**：M14 的红点分不出是「禁用 venv」还是「卫语句」红的 ⇒ 已另加 **M66**"
                   "（路径违规但 transformers 合规的隔离世界，要求 V-pi05-1 恰好 1 条违例、"
                   "V-pi05-5 保持 PASS）来单独证明「禁用 venv」这条规则自己会红",
            "family": "C_world_really_has_two_defects"},
}


def _specificity_of(base_status, cur_status, target, want, declared=()):
    """实测一个变异体的**作用面**：它翻动了哪些牙、有没有翻动目标牙、有没有越界。

    纯函数（不吃 `rep`、不读盘）⇒ 可以被 T12–T14 直接喂合成输入来证明它自己会判 False
    （裁定 27.1：从没咬过的守卫等于没有守卫；裁定 86.6-3：元判据必须由机器看守）。
    `base_status` / `cur_status` 都是 `{check_id: status}`；只在一侧出现的 id 用
    `"ABSENT"` 兜（牙本身出现/消失也是一种翻动，不能漏）。
    """
    tgt = str(target)
    decl = set(declared or ())
    ids = sorted(set(base_status) | set(cur_status))
    flipped = [i for i in ids if base_status.get(i, "ABSENT") != cur_status.get(i, "ABSENT")]
    out = {"target": tgt, "want": want, "scope": None, "flipped": flipped,
           "n_flipped": len(flipped), "declared_collateral": sorted(decl),
           "target_ids_flipped": [], "target_flipped": None,
           "undeclared_collateral": [], "declared_but_not_flipped": [],
           "specificity_ok": None,
           "why_not_enforced": None, "reasons": []}
    if tgt in SPECIFICITY_GLOBAL_TARGETS:
        out["scope"] = "global_declared_not_applicable"
        out["why_not_enforced"] = (
            "目标 `%s` 是**全局作用域**（这个变异动的就是整个世界，不是某一颗牙）⇒ "
            "「只翻动目标牙」在语义上不适用。**显式声明不适用**，不静默放过：它的期望由 "
            "`want` 那一列判（M16 要求 admission != PASS；M19/M31 要求八条牙全绿），"
            "翻动清单仍逐条落盘在 `flipped` 里供人核。" % tgt)
        out["specificity_ok"] = None
        return out
    out["scope"] = "tooth_targeted"
    out["target_ids_flipped"] = [i for i in flipped if i.startswith(tgt)]
    out["target_flipped"] = bool(out["target_ids_flipped"])
    out["undeclared_collateral"] = [i for i in flipped
                                    if not i.startswith(tgt) and i not in decl]
    # 声明也会腐烂：声明了一条**并没有**翻动的牙，说明这条声明是抄来的/过期的，
    # 而它会让"特异性成立"这句话失去意义（登记表变成文书 ⇒ 正是裁定 86.6-3 要挡的形态）。
    out["declared_but_not_flipped"] = sorted(i for i in decl if i not in set(flipped))
    if want == "RED" and not out["target_flipped"]:
        out["reasons"].append(
            "**翻不动目标牙**：期望 `%s` 变 RED，但它的状态没变（实测翻动=%s）⇒ 裁定 86.6-3 "
            "的前半条不成立：这个变异体证明不了那颗牙能红，「已验证」只是文书形态" % (tgt, flipped))
    if out["undeclared_collateral"]:
        out["reasons"].append(
            "**未声明的附带翻动**：%s（目标 `%s` 之外、且不在 `MUTATION_COLLATERAL[%s]` 里）"
            "⇒ 裁定 86.6-3 的后半条「只翻动目标牙」不成立。要么给这个附带翻动写一个物理成因并"
            "声明进表，要么改变异体构造让它隔离（裁定 78.1）"
            % (out["undeclared_collateral"], tgt, repr(list(decl))))
    if out["declared_but_not_flipped"]:
        out["reasons"].append(
            "**声明已过期**：`MUTATION_COLLATERAL` 里为这个变异体声明了 %s，但它们本轮**没有**翻动"
            "（实测翻动=%s）⇒ 声明必须与实际作用面一致，不许留一条用不上的声明壮胆"
            % (out["declared_but_not_flipped"], flipped))
    out["specificity_ok"] = not out["reasons"]
    return out


def selftest(out_root: Path | None = None):
    stamp = int(time.time())
    base = out_root or Path("/tmp/b2_env_admission_selftest_%d_%d" % (stamp, os.getpid()))
    base.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("变异自检：证明八条 π₀.₅ 牙都咬得动（裁定 27.1「恒真/恒假的闸等于没有闸」）")
    print("含反向变异（M7/M19/M46/M54 期望不红，M16 期望**不是 PASS**，"
          "M44/M47 期望黄，M16/M39/M55/M58 期望弃权）：防恒红、防空目录放行")
    print("=" * 100)
    print("%-4s %-22s %-10s %-14s %s" % ("变异", "目标", "期望", "实际", "说明"))
    print("-" * 100)
    results, rows, spec_rows = [], [], []

    # baseline：干净合成世界里八条牙必须全绿（否则后面的「变红」没有意义）
    root, a2, odir, measured = _mk_world(base / "baseline", "none")
    ev = collect(Path(root), Path(a2), "/root/venvs/pi05_sim", Path(odir), live=False,
                 verify_sha256=True)
    ev.update({k: v for k, v in (measured or {}).items()})
    ev["live"] = True
    rep0 = Report()
    run_pi05_checks(ev, rep0, Path(root), Path(odir))
    base_green = all(c["status"] == STATUS_PASS for c in rep0.checks
                     if c["id"] in CHECKS_PI05)
    # 裁定 86.6-3 的比对基线：baseline 世界的**逐条状态图**（不是"全绿"这个布尔）。
    # 特异性 = 变异世界的状态图与它的**差集**，所以必须留住逐条状态，不能只留 base_green。
    base_status = {c["id"]: c["status"] for c in rep0.checks}
    print("%-4s %-22s %-10s %-14s %s" % ("-", "八条牙", "ALL PASS",
                                          "ALL PASS" if base_green else "有非 PASS",
                                          "baseline_all_green（合成世界本身必须全绿）"))
    results.append(base_green)
    rows.append({"id": "baseline", "target": "__all_pi05__", "want": "PASS",
                 "got": ",".join(c["status"] for c in rep0.checks if c["id"] in CHECKS_PI05),
                 "ok": base_green})
    if not base_green:
        for c in rep0.checks:
            if c["id"] in CHECKS_PI05 and c["status"] != STATUS_PASS:
                print("      baseline 非绿：%s -> %s" % (c["id"], c["observed"]))

    # ---- A1 兜底牙的自检（**不走** _mk_world 的变异表：它测的是"判词装配"，不是"世界状态"）----
    # 19:0x 的真实事故：第 5 条牙在自检里全绿、在现场判定里没被调用（main 与 selftest 各列一份）。
    # 所以这条案要**双向**：漏一条 ⇒ A1 必须红；八条都在 ⇒ A1 必须不出现（防恒红）。
    root_a1, a2_a1, odir_a1, meas_a1 = _mk_world(base / "A1", "none")
    ev_a1 = collect(Path(root_a1), Path(a2_a1), "/root/venvs/pi05_sim", Path(odir_a1),
                    live=False, verify_sha256=True)
    ev_a1.update({k: v for k, v in (meas_a1 or {}).items()})
    ev_a1["live"] = True
    rep_short = Report()
    check_v_pi05_1(ev_a1, rep_short)
    check_v_pi05_2(ev_a1, rep_short, Path(root_a1))
    check_v_pi05_3(ev_a1, rep_short)
    check_v_pi05_4(ev_a1, rep_short)
    check_v_pi05_5(ev_a1, rep_short)          # **故意漏掉最后三条（V-pi05-6/7/8）**
    missing = check_a1_all_teeth_ran(rep_short)
    a1_red = (missing == CHECKS_PI05[5:] and any(
        c["id"] == "A1_all_teeth_ran" and c["status"] == STATUS_RED for c in rep_short.checks))
    rep_full = Report()
    run_pi05_checks(ev_a1, rep_full, Path(root_a1), Path(odir_a1))
    missing_full = check_a1_all_teeth_ran(rep_full)
    a1_silent = (not missing_full) and not any(
        c["id"] == "A1_all_teeth_ran" for c in rep_full.checks)
    a1_ok = bool(a1_red and a1_silent)
    print("%-4s %-22s %-10s %-14s %s ⇒ %s" % (
        "A1", "A1_all_teeth_ran", "RED+静默", ("OK" if a1_ok else "失效"),
        "漏跑一条牙必须判红、八条齐全时必须不出现（防恒红）",
        "抓住" if a1_ok else "**没抓住（兜底牙失效）**"))
    results.append(a1_ok)
    rows.append({"id": "A1_missing_tooth", "tamper": "(装配层，不用 _mk_world)",
                 "target": "A1_all_teeth_ran", "want": "RED_and_silent_when_full",
                 "got": ("missing=%s red=%s silent_when_full=%s"
                         % (missing, a1_red, a1_silent)), "ok": a1_ok,
                 "desc": "第 5 条牙曾只在自检里跑、现场没跑（ADR-C-014 同型）⇒ 兜底牙必须能红"})

    # ---- 裁定 78.4 的①·乙层：**转录层**变异体（T 系列）----
    # D 的发现：`delegated_g1_g5_freeze` 的 5 份产物 / 25 条 check **从未非绿**、且**无变异体记录**
    # ⇒ 按裁定 27.1 那等于没有闸。B2 采①（补牙）而不是②（降级）。补牙分两层：
    #   甲（判据层）= 亲自复跑上游 `--selftest`、逐 G 统计覆盖 ⇒ 现场判定里的
    #       `G1-G5_freeze_teeth`（不在自检里跑，因为它要真调子进程；其解析器由 T10/T11 钉住）；
    #   乙（转录层）= 下面这 11 条：喂**合成的 guard 产物**给 `_transcribe_guard`，
    #       证明"上游把某个 G 判红时，B2 这一层会跟着红、且 id 能精确点到那个 G"。
    # **不碰 B 的脚本**（只读复用，D→B2 §1.1），也不改写 B 的任何产物。
    G_IDS = ["G1_locks_0928_not_overwritten", "G2_rebuild_lockout_not_default",
             "G3_persistent_pin_conformance", "G4_base_python_assertion", "G5_numpy_shadowing"]

    def _synth_guard_doc(red_g=None, lead_space=False, drop_id_g=None, outside_status_g=None):
        checks = []
        for cid in G_IDS:
            st, viol, warns = "PASS", [], []
            if red_g and cid.startswith(red_g):
                st = "RED"
                viol = ["合成违例：%s 被打红（B2 转录层变异体）" % red_g]
            if outside_status_g and cid.startswith(outside_status_g):
                st = "N_A"                      # 三值集外 ⇒ 转录层必须弃权，不得读成 PASS
            c = {"check_id": (("  " + cid) if lead_space else cid),
                 "ruling_ref": "合成（B2 转录层牙）", "status": st,
                 "expected": "合成期望（%s）" % cid, "red_when": "合成红条件",
                 "note": "", "actual": {"violations": viol, "warnings": warns}}
            if drop_id_g and cid.startswith(drop_id_g):
                c.pop("check_id")               # 裁定 78.3：id 缺失不得留 null
            checks.append(c)
        n_red = sum(1 for c in checks if c["status"] == "RED")
        n_out = sum(1 for c in checks if c["status"] not in ("PASS", "WARN", "RED"))
        return {"guard_kind": "synthetic_for_b2_transcription_teeth", "guard_build": "0" * 12,
                "checks": checks,
                # 上游 summary **故意**只按它自己的两值口径数（没有 `n_unjudged` 这一维，
                # 三值集外的那条被它算进 `n_pass`）⇒ T9 靠这一点证明：只看 summary 会判 PASS
                # （假绿），必须逐条复算。这不是把上游写坏，而是复现"上游没有 UNJUDGED 概念"
                # 这个**真实形态**（裁定 78.2 的 F1 就是这么发生的）。
                "summary": {"n_checks": len(checks), "n_pass": len(checks) - n_red,
                            "n_warn": 0, "n_red": n_red,
                            "all_green": (n_red == 0),
                            "verdict": "RED" if n_red else "PASS"}}

    def _t_record(tid, target, want, got, ok, desc, layer="transcription"):
        lname = {"transcription": "转录层", "meta_specificity": "特异性元判据"}[layer]
        print("%-4s %-22s %-10s %-14s %s ⇒ %s" % (
            tid, target, want, str(got)[:14], desc,
            ("抓住" if ok else "**没抓住（%s牙失效）**" % lname) if str(want).startswith("RED")
            else ("成立" if ok else "**不成立（%s牙失效）**" % lname)))
        results.append(bool(ok))
        rows.append({"id": tid,
                     "tamper": ("(转录层：合成 guard 产物，不用 _mk_world)" if
                                layer == "transcription" else
                                "(元判据层：合成 base/cur 状态图，不用 _mk_world)"),
                     "target": target, "want": want, "got": got, "ok": bool(ok), "desc": desc,
                     "must_contain": None, "must_contain_matched": None,
                     "layer": layer, "checks": []})

    def _transcribe_synth(doc, tag="freeze"):
        r = Report()
        _transcribe_guard(r, doc, tag, "合成 ref", "合成 req", "合成 red_when")
        agg = [c for c in r.checks if c["id"] == "G1-G5_%s" % tag]
        per = [c for c in r.checks if c["id"] != "G1-G5_%s" % tag]
        return r, (agg[0] if agg else None), per

    for gi, g in enumerate(("G1", "G2", "G3", "G4", "G5")):
        want_id = "%s[freeze]" % G_IDS[gi]
        _, agg, per = _transcribe_synth(_synth_guard_doc(red_g=g))
        reds = [c for c in per if c["status"] == STATUS_RED]
        ok_t = (agg is not None and agg["status"] == STATUS_RED and agg["ok"] is False
                and len(reds) == 1 and reds[0]["id"] == want_id and reds[0]["ok"] is False)
        _t_record("T%d" % (gi + 1), "G1-G5_freeze×%s" % g, "RED_and_id_exact",
                  "agg=%s red_ids=%s" % (agg and agg["status"], [c["id"] for c in reds]), ok_t,
                  "上游把 **%s** 判 RED ⇒ 聚合必须红、且逐条里**只有** `%s` 红（id 精确点到条，"
                  "裁定 78.3 补 id 就是为了这个）" % (g, want_id))

    _, agg6, per6 = _transcribe_synth(_synth_guard_doc())
    ok6 = (agg6 is not None and agg6["status"] == STATUS_PASS and len(per6) == 5
           and all(c["status"] == STATUS_PASS and c["ok"] is True for c in per6))
    _t_record("T6", "G1-G5_freeze", "PASS_all_green",
              "agg=%s n_per=%d" % (agg6 and agg6["status"], len(per6)), ok6,
              "**反向（防恒红）**：上游全绿的产物 ⇒ 聚合必须 PASS、5 条逐条全 PASS")

    _, agg7, per7 = _transcribe_synth(_synth_guard_doc(red_g="G2", lead_space=True))
    ids7 = [c["id"] for c in ([agg7] if agg7 else []) + per7]
    reds7 = [c for c in per7 if c["status"] == STATUS_RED]
    ok7 = (len(reds7) == 1 and reds7[0]["id"] == "G2_rebuild_lockout_not_default[freeze]"
           and all(i == i.strip() for i in ids7)
           and all(c["observed"].get("id_had_surrounding_whitespace") is True for c in per7))
    _t_record("T7", "id_whitespace", "stripped",
              "red_id=%r any_padded=%s" % (reds7 and reds7[0]["id"],
                                           any(i != i.strip() for i in ids7)), ok7,
              "上游 `check_id` 带**两个前导空格**（21:13 那份判词里 10 条转录 id 全带）⇒ "
              "转录后必须已 `.strip()`，否则精确匹配/去重/建索引全漏（裁定 78.3 附带必修）")

    _, agg8, per8 = _transcribe_synth(_synth_guard_doc(drop_id_g="G3"))
    ids8 = [c["id"] for c in ([agg8] if agg8 else []) + per8]
    g3 = [c for c in per8 if c["id"].startswith("G_index")]
    ok8 = (len(g3) == 1 and g3[0]["id"] == "G_index2[freeze]"
           and all(i and str(i).strip() and i != "None[freeze]" for i in ids8)
           and g3[0]["observed"].get("id_was_null") is True)
    _t_record("T8", "id_null", "filled_not_null",
              "fallback_id=%s n_null_id=%s" % (g3 and g3[0]["id"],
                                               sum(1 for i in ids8 if not i)), ok8,
              "上游 `check_id` 缺失 ⇒ id **不得留 null**（D 数的 45 条 `id=null` 就是这个形态），"
              "退化成 `G_index<i>[<tag>]` 并把原值登记在 `transcribed_from_check_id`")

    _, agg9, per9 = _transcribe_synth(_synth_guard_doc(outside_status_g="G4"))
    g4 = [c for c in per9 if c["id"].startswith("G4")]
    up9 = ((agg9 or {}).get("observed") or {}).get("upstream_summary_verbatim") or {}
    ok9 = (len(g4) == 1 and g4[0]["status"] == STATUS_UNJUDGED and g4[0]["ok"] is None
           and g4[0]["observed"].get("status_was_not_in_three_value_set") is True
           and agg9 is not None and agg9["status"] != STATUS_PASS
           and agg9["status"] == STATUS_UNJUDGED
           and up9.get("verdict") == "PASS"
           and agg9["observed"].get("upstream_summary_agrees_with_recompute") is False)
    _t_record("T9", "status_outside_three_value_set", "UNJUDGED_not_PASS",
              "g4=%s agg=%s upstream_summary=%r" % (
                  g4 and g4[0]["status"], agg9 and agg9["status"],
                  (agg9 or {}).get("observed", {}).get("upstream_summary_verbatim", {}).get("verdict")),
              ok9,
              "上游把某条写成 `N_A`（三值集外）而它的 summary 仍说 `verdict=PASS` ⇒ "
              "**只看 summary 就是假绿**；转录层必须逐条复算、把聚合降为 UNJUDGED"
              "（裁定 78.2：UNJUDGED 计入非绿）")

    synth_stdout_ok = "\n".join([
        "M1   G1=RED     G1=RED     合成 ⇒ 抓住",
        "M2   G2=RED     G2=RED     合成 ⇒ 抓住",
        "M3   G3=RED     G3=RED     合成 ⇒ 抓住",
        "M4   G4=RED     G4=RED     合成 ⇒ 抓住",
        "M5   G5=RED     G5=RED     合成 ⇒ 抓住",
        "M6   G3=NOT_RED G3=PASS    合成反向 ⇒ 未误报（假红已修）",
        "变异测试：7/7 条判定符合预期（含 baseline 全绿）"])
    p10 = _parse_guard_selftest_stdout(synth_stdout_ok)
    ok10 = (p10["n_rows_parsed"] == 6 and p10["upstream_all_caught"] is True
            and p10["every_g_has_a_caught_red_mutant"] is True
            and p10["per_g_caught_red_mutants"] == {"G1": 1, "G2": 1, "G3": 1, "G4": 1, "G5": 1})
    _t_record("T10", "teeth_parser_all_caught", "coverage_true",
              "rows=%s per_g=%s" % (p10["n_rows_parsed"], p10["per_g_caught_red_mutants"]), ok10,
              "上游自检**全抓住**的 stdout ⇒ 解析器必须算出「G1–G5 每个 G 都有能红的变异体」"
              "（裁定 78.4 的①靠这个统计成立，不能只看 rc）")
    synth_stdout_miss = synth_stdout_ok.replace(
        "M4   G4=RED     G4=RED     合成 ⇒ 抓住",
        "M4   G4=RED     G4=PASS    合成 ⇒ **没抓住（判据恒假）**").replace(
        "变异测试：7/7", "变异测试：6/7")
    p11 = _parse_guard_selftest_stdout(synth_stdout_miss)
    ok11 = (p11["upstream_all_caught"] is False
            and p11["every_g_has_a_caught_red_mutant"] is False
            and p11["per_g_caught_red_mutants"]["G4"] == 0)
    _t_record("T11", "teeth_parser_g4_missed", "coverage_false",
              "per_g=%s all_caught=%s" % (p11["per_g_caught_red_mutants"],
                                           p11["upstream_all_caught"]), ok11,
              "**反向钉住解析器本身**：G4 的那条变异漏抓 ⇒ 覆盖统计必须变 False"
              "（否则 `G1-G5_freeze_teeth` 就是恒真闸，裁定 27.1）")

    # ---- 裁定 86.6-3：**特异性元判据自己**的三颗牙（T12–T14）----
    # 为什么必须给元判据配牙：`_specificity_of` 如果恒返回 True，那"78 条变异体特异性全成立"
    # 就是一句文书 —— 正是 86.6-3 要挡的形态（"让『已验证』以文书形态活下来"）。
    # 所以这里喂**合成的 base/cur 状态图**，要求它对三种情形分别给出 False/True/False。
    _b = {"V-pi05-1_version_anchor": STATUS_PASS, "V-pi05-5_transformers_pi05_ready": STATUS_PASS}
    s12 = _specificity_of(_b, {"V-pi05-1_version_anchor": STATUS_RED,
                               "V-pi05-5_transformers_pi05_ready": STATUS_RED},
                          "V-pi05-1", "RED", ())
    ok12 = (s12["specificity_ok"] is False
            and s12["undeclared_collateral"] == ["V-pi05-5_transformers_pi05_ready"]
            and s12["target_flipped"] is True)
    _t_record("T12", "_specificity_of", "undeclared_collateral_false",
              "ok=%s undecl=%s" % (s12["specificity_ok"], s12["undeclared_collateral"]), ok12,
              "合成：目标牙翻了 RED，但**另一颗牙也翻了且未声明** ⇒ 特异性必须判 False"
              "（裁定 86.6-3 的后半条「只翻动目标牙」）", layer="meta_specificity")
    s13 = _specificity_of(_b, {"V-pi05-1_version_anchor": STATUS_RED,
                               "V-pi05-5_transformers_pi05_ready": STATUS_RED},
                          "V-pi05-1", "RED", ("V-pi05-5_transformers_pi05_ready",))
    ok13 = (s13["specificity_ok"] is True and s13["undeclared_collateral"] == []
            and s13["declared_collateral"] == ["V-pi05-5_transformers_pi05_ready"])
    _t_record("T13", "_specificity_of", "declared_collateral_true",
              "ok=%s decl=%s" % (s13["specificity_ok"], s13["declared_collateral"]), ok13,
              "**反向（防恒假）**：同一张状态图，但附带翻动**已声明** ⇒ 必须判 True"
              "（否则这条元判据会变成一把恒假的闸，把所有变异体一律判成特异性不成立）",
              layer="meta_specificity")
    s14 = _specificity_of(_b, {"V-pi05-1_version_anchor": STATUS_PASS,
                               "V-pi05-5_transformers_pi05_ready": STATUS_RED},
                          "V-pi05-1", "RED", ())
    ok14 = (s14["specificity_ok"] is False and s14["target_flipped"] is False
            and any("翻不动目标牙" in r for r in s14["reasons"]))
    _t_record("T14", "_specificity_of", "target_not_flipped_false",
              "ok=%s target_flipped=%s" % (s14["specificity_ok"], s14["target_flipped"]), ok14,
              "合成：期望 RED 但**目标牙一动没动**（红的是别的牙）⇒ 必须判 False"
              "（裁定 86.6-3 的前半条：一个翻不动目标牙的变异体，与一个恒真的牙同样危险）",
              layer="meta_specificity")
    s15 = _specificity_of(_b, {"V-pi05-1_version_anchor": STATUS_UNJUDGED},
                          "__all_pi05__", "PASS", ())
    ok15 = (s15["scope"] == "global_declared_not_applicable"
            and s15["specificity_ok"] is None and s15["why_not_enforced"])
    _t_record("T15", "_specificity_of", "global_scope_not_vacuous",
              "scope=%s ok=%s" % (s15["scope"], s15["specificity_ok"]), ok15,
              "全局作用域目标（`__all_pi05__`/`__verdict__`）必须回 `specificity_ok=None` + "
              "`why_not_enforced`，**不得**回 True（回 True 就是把「不适用」记成「通过」，"
              "三值纪律的反面）⇒ 显式声明不适用这条路径自己也有牙",
             layer="meta_specificity")

    # ---- 归一台账层（N 系列）：`A3_delegated_docs_normalized` **自己**的牙 ----
    # 为什么现在才补：A3 是「清单/索引件必须与不跟随符号链接的 `find -P -type f | wc -l`
    # 对账、且差值必须可解释」（裁定 92.3-ii）的看守者，而**看守者自己此前一颗变异牙都没有**
    # ⇒ 按红线 `tooth_must_be_mutant_proven`（裁定 27.1「从没咬过的守卫等于没有守卫」）
    # 它等于没有闸。本轮已经为这笔欠账付过学费：正式判定的**第一版**把不变式 (v) 写成
    # 「全部副本 - 有效副本 == 本轮移入数」，而 `_superseded_layout1_*` 是**跨轮累积**的
    # ⇒ 第二轮必然对不上（实测差 3、移入 0）⇒ 假红一路写进正式产物才被人工发现。
    # 自检里没有任何一颗牙挡得住它，这就是"看守者没被看守"的代价。
    # 与 D 的第 16 号同型（裁定 90.5 #16：拿一个"看起来能用"的量，替代那个真正要指的量）。
    #
    # 三条牙都只动 `normalized/` 的**台账-磁盘一致性**，不动八条 π₀.₅ 牙 ⇒ **不用** `_mk_world`
    # （A3 的证据面就是 out_dir 本身）。隔离要求（裁定 78.1 `mutant_construction_isolation`）：
    # 每条牙**恰好 1 条违例**（= 牙内部的作用面，同 M66 的 `exact_viol`，裁定 86.6-3 的第三维），
    # 且用 `identity_holds` 把「红来自哪一组不变式」钉死：
    #   N1（游离副本）⇒ identity_holds **False**（find 不变式 (ii) 失败）；
    #   N3（D 作用域只 2 份）⇒ identity_holds **True**（find 五条全成立，红只来自"与 D 对不上账"）。
    def _n_world(name, n_docs=1, stray_valid=False, d_scope_docs=None):
        """摆一个只含委派产物 + `normalized/` 的最小世界（不合成 A2 交件），返回 `(out_dir, extra_roots)`。

        `d_scope_docs` 会造一个**恰名** `D_FINDING_SCOPE_DIR`（`b2_env_admission_20260929`）的
        兄弟目录并放进 `extra_roots` ⇒ `d_scope_scanned=True`；不造则 `matches_d_count` 按
        三值纪律记 `None`（本轮没有扫 D 点名的作用域 ⇒ 无从对账，既不判成立也不判不成立）。
        """
        root_n = base / name
        out_n = root_n / "out"
        src_n = out_n / "src"
        src_n.mkdir(parents=True, exist_ok=True)
        for i in range(n_docs):
            (src_n / ("delegated_g1_g5_synth%d.json" % i)).write_text(
                json.dumps(_synth_guard_doc(), indent=1, ensure_ascii=False) + "\n")
        extra = []
        if d_scope_docs:
            ddir = root_n / D_FINDING_SCOPE_DIR
            (ddir / "history").mkdir(parents=True, exist_ok=True)
            for i in range(d_scope_docs):
                (ddir / "history" / ("delegated_g1_g5_d%d.json" % i)).write_text(
                    json.dumps(_synth_guard_doc(), indent=1, ensure_ascii=False) + "\n")
            extra.append(ddir)
        if stray_valid:
            # 一份**游离的有效副本**，落在布局 v2 的位置（`normalized/<源 out_dir 名>/…`）下：
            # v1→v2 的顶层移动步骤只 `glob("*.normalized.json")`（**顶层**）⇒ 抓不到它；
            # 而 `find -P -name '*.normalized.json'`（排除 `_superseded_layout*/`）**数得到**
            # ⇒ 只对不变式 (ii)「台账 vs 磁盘」施压，(iii)(iv)(v) 全部保持成立（隔离）。
            sdir = out_n / "normalized" / "src"
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "stray.normalized.json").write_text(
                json.dumps(_synth_guard_doc(), indent=1, ensure_ascii=False) + "\n")
        return out_n, extra

    _N_SKIP = object()               # 「这一维不检」的哨兵（不能用 None：None 本身是要检的值）

    def _n_record(nid, out_n, extra, want, must_contain=None, desc="",
                  want_matches=_N_SKIP, want_identity=_N_SKIP):
        rep_n = Report()
        tally_n = normalize_all_guard_docs(Path(out_n), rep_n, extra_roots=extra)
        cn = [c for c in rep_n.checks if c["id"] == "A3_delegated_docs_normalized"]
        got_n = cn[0]["status"] if cn else "ABSENT"
        viol_n = ((cn[0].get("observed") or {}).get("violations") or []) if cn else []
        recon_n = (tally_n.get("d_finding_reconciliation") or {})
        cc_n = (tally_n.get("crosscheck_find_type_f") or {})
        matches_n = recon_n.get("matches_d_count", "MISSING")
        identity_n = cc_n.get("identity_holds", "MISSING")
        n_reasons_n = len(cc_n.get("unexplained_differences") or [])
        ok_n = (got_n == want)
        matched_n = None
        if must_contain is not None and ok_n:
            matched_n = (must_contain in json.dumps(viol_n, ensure_ascii=False, default=str))
            ok_n = bool(matched_n)
        # 牙内部的作用面：判红时必须**恰好 1 条**违例（多了就说明这颗牙顺带咬了别的不变式，
        # 那它就证明不了"是这一条不变式在起作用"）。
        exact_n = (len(viol_n) == 1) if want == STATUS_RED else True
        if not exact_n:
            ok_n = False
        cond = []
        if want_matches is not _N_SKIP and matches_n is not want_matches:
            cond.append("matches_d_count=%r（要求 %r）" % (matches_n, want_matches))
        if want_identity is not _N_SKIP and identity_n is not want_identity:
            cond.append("identity_holds=%r（要求 %r）" % (identity_n, want_identity))
        if cond:
            ok_n = False
        got_s = ("status=%s n_viol=%d n_find_reasons=%d matches_d_count=%r identity_holds=%r"
                 % (got_n, len(viol_n), n_reasons_n, matches_n, identity_n))
        lname = "归一台账层"
        print("%-4s %-22s %-10s %-14s %s%s%s ⇒ %s" % (
            nid, "A3_delegated_docs_normalized", want,
            ("%s/%d条" % (got_n, len(viol_n)))[:14], desc,
            ("" if matched_n is None else ("［判词含 %r］" % must_contain if matched_n
                                          else "［**判词缺 %r**］" % must_contain)),
            ("" if exact_n else "［**违例 %d 条，要求恰好 1 条**］" % len(viol_n))
            + ("" if not cond else "［**%s**］" % "；".join(cond)),
            ("抓住" if ok_n else "**没抓住（%s牙失效）**" % lname) if want == STATUS_RED
            else ("未误报" if ok_n else "**误报（假红/恒红，%s牙失效）**" % lname)))
        if not ok_n:
            for v in viol_n[:3]:
                print("        A3 违例：%s" % str(v)[:220])
        results.append(bool(ok_n))
        rows.append({"id": nid,
                     "tamper": "(归一台账层：只摆 out_dir/normalized/ 的目录树，不用 _mk_world)",
                     "target": "A3_delegated_docs_normalized", "want": want,
                     "got": got_s, "ok": bool(ok_n), "desc": desc,
                     "must_contain": must_contain, "must_contain_matched": matched_n,
                     "exact_violations_expected": (1 if want == STATUS_RED else None),
                     "exact_violations_actual": (len(viol_n) if want == STATUS_RED else None),
                     "layer": "normalization",
                     "matches_d_count": matches_n, "identity_holds": identity_n,
                     "n_find_invariant_reasons": n_reasons_n,
                     "violations": [str(v)[:300] for v in viol_n[:3]],
                     "checks": [{"id": c["id"], "status": c["status"]} for c in rep_n.checks]})

    _n1_out, _n1_extra = _n_world("N1", n_docs=1, stray_valid=True)
    _n_record("N1", _n1_out, _n1_extra, STATUS_RED, must_contain="台账漏登或多登",
              want_identity=False,
              desc="不变式 (ii)：`normalized/` 里多摆一份**游离的有效副本**（放在布局 v2 的位置，"
                   "顶层移动步骤抓不到）⇒ 实测份数 > 台账登记份数，A3 必须红、判词必须点名"
                   "「台账漏登或多登」、且**恰好 1 条**违例（(iii)(iv)(v) 都还成立 ⇒ 红只来自 (ii)）")
    _n2_out, _n2_extra = _n_world("N2", n_docs=1)
    _n_record("N2", _n2_out, _n2_extra, STATUS_PASS, want_matches=None, want_identity=True,
              desc="**反向（防恒红/防假红）**：干净世界 + **没有** D 点名的作用域 ⇒ "
                   "`matches_d_count` 必须记 `None`（三值：无从对账）而 A3 必须 **PASS**。"
                   "第一版把 None 这一档写成 `False ⇒ 判红`，那会在任何不含 20260929 目录的 "
                   "out_dir 上造假红（本仓第 8 起的镜像：把「没测到」读成「不合格」）⇒ 这条牙钉住它")
    _n3_out, _n3_extra = _n_world("N3", n_docs=1, d_scope_docs=2)
    _n_record("N3", _n3_out, _n3_extra, STATUS_RED, must_contain="对不上账",
              want_matches=False, want_identity=True,
              desc="与 D 的计数**对账**：造一个恰名 `%s` 的作用域但只放 2 份（D 数的是 %d 份 / "
                   "%d 条）⇒ `matches_d_count=False`、A3 必须红且判词点名「对不上账」；同时 "
                   "`identity_holds` 必须仍为 True（find 五条不变式全成立 ⇒ 红只来自对账，"
                   "不是顺带咬了别的）" % (D_FINDING_SCOPE_DIR, D_FINDING_N_DOCS,
                                          D_FINDING_N_CHECKS))

    # ---- 顶层口径层（O1–O5）：RR-B2-09 改判（裁定 93 / D→B2 §四-1）的牙 ----
    # 这一层**不摆世界**（不用 `_mk_world`）：被测对象就是判据件本身（`ok_of` / `admission_of` /
    # `EXIT`），所以用合成 `Report` 造出四种计数组合。O5 是**同源牙**：用 `inspect.getsource`
    # 证明「改了判据也真的改了散文与调用点」，否则会出现两种活下来的假象 ——
    # ① helper 定义了却没接上（`build_verdict` 仍在算 `adm == "PASS"`）；② 代码改了、散文还写着
    # 旧口径（本仓栽过 9 次的「判据与散文不同源」，裁定 27 / 35.3 / 37.4 / 78.3）。
    _O_OK_FOR_STATUS = {STATUS_PASS: True, STATUS_RED: False,
                        STATUS_WARN: None, STATUS_UNJUDGED: None}

    def _o_world(*statuses):
        rep_o = Report()
        for i, st in enumerate(statuses):
            rep_o.add("SYNTH_CALIBER_%d" % i, _O_OK_FOR_STATUS[st], {"synthetic_status": st},
                      "合成判据：只为造出 n_red / n_unjudged / n_warn 的一种组合，"
                      "**不指任何真实事实**（口径层的被测对象是判据函数，不是世界）",
                      status=st, note="verdict_caliber 层的合成 check（O1–O5）")
        return rep_o

    def _o_record(oid, rep_o, want_adm, want_ok, desc, src_probe=None, coverage=None):
        got_adm = admission_of(rep_o)
        got_ok = ok_of(rep_o.n_red, rep_o.n_unjudged, rep_o.n_warn)
        counts = {"n_red": rep_o.n_red, "n_unjudged": rep_o.n_unjudged,
                  "n_warn": rep_o.n_warn, "n_pass": rep_o.n_pass}
        probe_failed = ({k: v for k, v in (src_probe or {}).items() if v is not True})
        ok_o = (got_adm == want_adm and got_ok is want_ok and not probe_failed)
        got_s = "admission=%s ok=%s red/unj/warn=%d/%d/%d" % (
            got_adm, got_ok, rep_o.n_red, rep_o.n_unjudged, rep_o.n_warn)
        if src_probe is not None:
            got_s += (" 同源探针 %d/%d 成立" % (sum(1 for v in src_probe.values() if v is True),
                                               len(src_probe)))
            if probe_failed:
                got_s += "［**未成立：%s**］" % sorted(probe_failed)
        lname = "口径层"
        print("%-4s %-22s %-10s %-14s %s ⇒ %s" % (
            oid, "ok_of/admission_of/EXIT",
            ("adm=%s,ok=%s" % (want_adm[:9], want_ok))[:10],
            ("adm=%s,ok=%s" % (got_adm[:9], got_ok))[:14], desc[:60],
            ("抓住" if ok_o else "**没抓住（%s牙失效）**" % lname) if want_ok is False
            else ("成立" if ok_o else "**不成立（%s牙失效）**" % lname)))
        results.append(bool(ok_o))
        rows.append({"id": oid,
                     "tamper": "(口径层：合成 Report 的计数组合 + 源码同源探针，不摆世界)",
                     "target": "ok_of/admission_of/EXIT",
                     "want": "admission=%s ok=%s" % (want_adm, want_ok),
                     "got": got_s, "ok": bool(ok_o), "desc": desc,
                     "must_contain": None, "must_contain_matched": None,
                     "exact_violations_expected": None, "exact_violations_actual": None,
                     "layer": "verdict_caliber",
                     "counts": counts, "admission_got": got_adm, "ok_got": got_ok,
                     "source_probe": src_probe, "source_probe_failed": sorted(probe_failed),
                     # 裁定 93.8：模式审计器必须自带对照探针（缺 ⇒ `not_measured`、不得报绿）
                     "pattern_coverage_probe": coverage,
                     "caliber_marker": OK_CALIBER_MARKER,
                     "checks": [{"id": c["id"], "status": c["status"]} for c in rep_o.checks]})

    _o_record("O1", _o_world(STATUS_PASS, STATUS_WARN), "WARN", True,
              "**改判的正向钉**（裁定 93 / D→B2 §四-1）：世界里只有 WARN ⇒ `admission` 标签必须"
              "仍是 `WARN`（「必须登记」那一半），而顶层 `ok` 必须为 **True**（「不计失败」那一半）。"
              "旧口径（`n_warn` 也 AND 进去）在这里给 ok=false ⇒ 上游一次合法的 RED→WARN 改判"
              "（裁定 93.1）会被本闸二次判死，正是 D 点名要修的那件事。"
              "反向价值：它同时防「把 WARN 一档从 `admission_of` 里删掉」——标签必须还是 WARN。")
    _o_record("O2", _o_world(STATUS_PASS, STATUS_UNJUDGED), "UNJUDGED_evidence_missing", False,
              "**防放宽过头**：改判只动 WARN 一档 ⇒ UNJUDGED 必须**仍计入非绿**（裁定 78.2 的 F1："
              "RED=0 不得被下游读成干净）。若有人把 `ok_of` 顺手写成「只有 RED 才算失败」，"
              "这条会抓住（证据缺失 = 没测到，不是没问题）。")
    _o_record("O3", _o_world(STATUS_WARN, STATUS_RED), "RED", False,
              "**RED 仍失败，且 WARN 在场不得稀释它**：同一世界里既有 WARN 又有 RED ⇒ 标签必须"
              "`RED`、`ok` 必须 False。钉住「WARN 不计失败」没有被误实现成「有 WARN 就整体不判失败」。")
    _o_record("O4", _o_world(STATUS_PASS, STATUS_PASS), "PASS", True,
              "**防恒假**：全绿世界必须 `ok=true`、标签 `PASS`。一个恒假的 `ok_of` 与一个恒真的"
              "同样等于没有闸（裁定 27.1），也会让 `admission_granted` 永远拿不到 true。")
    _src_bv = inspect.getsource(build_verdict)
    _src_nd = inspect.getsource(_normalize_guard_doc)
    _src_ao = inspect.getsource(admission_of)
    # ---- 裁定 93.8 的对照探针：先证明 O5 的**模式**覆盖得住旧口径的各种写法 ----
    # 注入面是**合成源码串**（不动真件、不写盘）：每一条坏形态都是同一个缺陷的不同字面
    # （引号种类 / 括号有无 / 键名），若模式只认其中一种，其余形态就会以"已审计"的形状溜过去。
    _O5_BAD_FORMS = [
        ('        "ok": adm == "PASS",\n', "改判前原样（双引号）"),
        ("        \"ok\": adm == 'PASS',\n", "同一缺陷、单引号形态"),
        ('        "ok": (adm == "PASS"),\n', "同一缺陷、多一对括号"),
        ('        "ok" : adm=="PASS",\n', "同一缺陷、冒号/等号两侧空格不同"),
        ('        "admission_granted": adm == "PASS",\n', "放行决定的旧写法"),
        ('        "admission_granted": (adm == "PASS"),\n', "放行决定的旧写法、带括号"),
    ]
    _O5_GOOD_FORMS = [
        ('        "ok": ok_of(rep.n_red, rep.n_unjudged, rep.n_warn),\n', "改判后的现行写法"),
        ('        "admission_granted": ok_of(rep.n_red, rep.n_unjudged, rep.n_warn),\n',
         "改判后的现行写法（放行决定）"),
        ('        "ok_criterion": OK_CRITERION,\n', "散文键：不是判据实现，不得被误报"),
        ('        "admission_granted_criterion": ("`admission_granted` == 顶层 `ok`"),\n',
         "键名以 `admission_granted` 开头但不是它 ⇒ 模式不得因为前缀相同就误报"),
    ]

    def _synth_bv(body):
        return ("def build_verdict(ev, rep, root, a2_dir, out_dir, venv, delegated):\n"
                "    adm = admission_of(rep)\n"
                "    doc = {\n" + body + '        "admission": adm,\n    }\n    return doc\n')

    _cov_bad, _cov_good = [], []
    for _bf, _why in _O5_BAD_FORMS:
        _hits = _legacy_ok_caliber_hits(_synth_bv(_bf))
        _cov_bad.append({"injected_bad_form": _bf.strip(), "why_it_is_bad": _why,
                         "defect": LEGACY_OK_CALIBER_WHY,
                         "detected": bool(_hits), "detected_by": _hits})
    for _gf, _why in _O5_GOOD_FORMS:
        _hits = _legacy_ok_caliber_hits(_synth_bv(_gf))
        _cov_good.append({"injected_good_form": _gf.strip(), "why_it_must_not_be_flagged": _why,
                          "false_positive": bool(_hits), "hit_by": _hits})
    _cov_all_detected = all(x["detected"] for x in _cov_bad)
    _cov_no_false_positive = not any(x["false_positive"] for x in _cov_good)
    _o5_coverage = {
        "ruling": ("裁定 93.8 `reference_auditor_must_prove_its_own_pattern_coverage`"
                   "（红线族；缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`）"),
        "auditor_under_test": ("O5 的 `no_legacy_ok_caliber_in_build_verdict` 探针"
                               "（模式表 = `LEGACY_OK_CALIBER_PATTERNS`）"),
        "injection_surface": "合成源码串（`_synth_bv`），**不动真件、不写盘**",
        "n_bad_forms_injected": len(_cov_bad),
        "bad_forms": _cov_bad,
        "n_good_form_controls": len(_cov_good),
        "good_form_controls": _cov_good,
        "detected": _cov_all_detected,
        "all_bad_forms_detected": _cov_all_detected,
        "no_false_positive_on_good_forms": _cov_no_false_positive,
        "measurement_status": ("measured" if (_cov_all_detected and _cov_no_false_positive)
                               else "not_measured"),
        "if_not_detected_then": ("O5 自己红（`src_probe` 里两条 coverage 断言会不成立）⇒ "
                                 "`all_ok=false` ⇒ 正式判定的 `A0_teeth_current` 判红："
                                 "模式覆盖不住的审计器不许报绿"),
    }
    _o5_probe = {
        "build_verdict_calls_ok_of": ("ok_of(" in _src_bv),
        "normalize_guard_doc_calls_ok_of": ("ok_of(" in _src_nd),
        # 改判前的写法必须已消失（模式见 `LEGACY_OK_CALIBER_PATTERNS`，覆盖引号/括号/空格变体）
        "no_legacy_ok_caliber_in_build_verdict": (not _legacy_ok_caliber_hits(_src_bv)),
        # ↑ 那条探针**自己**的覆盖证明（裁定 93.8）：注入的坏形态必须全被抓到、好形态必须不误报
        "pattern_coverage_all_bad_forms_detected": _cov_all_detected,
        "pattern_coverage_no_false_positive": _cov_no_false_positive,
        "ok_criterion_carries_marker": (OK_CALIBER_MARKER in OK_CRITERION),
        "ok_of_docstring_carries_marker": (OK_CALIBER_MARKER in (ok_of.__doc__ or "")),
        "warn_exit_code_is_zero": (EXIT.get("WARN") == 0),
        "red_and_unjudged_exit_codes_nonzero": (EXIT.get("RED") not in (0, None)
                                                and EXIT.get("UNJUDGED_evidence_missing") not in (0, None)),
        "admission_of_still_has_warn_branch": ('return "WARN"' in _src_ao),
        "verdict_carries_registration_block": ("warn_registered_not_blocking" in _src_bv),
    }
    _o_record("O5", _o_world(STATUS_PASS), "PASS", True,
              "**同源牙**（防「定义了 helper 却没接上」与「改了代码没改散文」）：`build_verdict` 与 "
              "`_normalize_guard_doc` 的源码里必须真的出现 `ok_of(`、且旧的 `adm == \"PASS\"` 两处"
              "写法必须已消失；`OK_CRITERION` 与 `ok_of.__doc__` 都必须带口径标记 `%s`；"
              "`EXIT['WARN']` 必须为 0 而 RED/UNJUDGED 必须非 0；`admission_of` 必须仍有 WARN 一档；"
              "判词必须仍带 `warn_registered_not_blocking` 登记块。计数组合本身用全绿世界（O4 已钉），"
              "这颗牙的载荷全在源码探针上。" % OK_CALIBER_MARKER,
              src_probe=_o5_probe, coverage=_o5_coverage)

    for entry in MUTATIONS:
        mid, tamper, want_check, want, desc = entry[:5]
        # 可选第 6 项：判词里**必须出现**的成因串。状态相同但成因不同的两种世界
        # （M36 交件口径假红 / M38 冻结栈真漂移，都是 RED）只判状态是分不开的，
        # 而它们的修法完全不同 ⇒ 这类变异额外钉住判词内容。
        must_contain = entry[5] if len(entry) > 5 else None
        # 可选第 7 项：目标牙里**违例条数必须恰好等于**这个数。用于「隔离变异体」
        # （M66）：`must_contain` 只能断言"某条成因**在**"，断言不了"别的成因**不在**"，
        # 而裁定 86.6-3 要的是「只翻动目标牙」——在同一条 check 内部，那就等价于
        # 「只产生那一条违例」。所以这一项是特异性的**第三个维度**（作用面 → 牙之间；
        # 违例条数 → 牙内部；成因键 → 红在哪一条判据上）。
        exact_viol = entry[6] if len(entry) > 6 else None
        wroot, wa2, wodir, wmeas = _mk_world(base / mid, tamper)
        ev = collect(Path(wroot), Path(wa2), "/root/venvs/pi05_sim", Path(wodir), live=False,
                     verify_sha256=True)
        if wmeas:
            ev.update(wmeas)
            ev["live"] = True
            # M57 用的是**合成 venv**（里面故意注册了被删的两步）⇒ 兼容目录证据必须按它重采，
            # 否则这条变异测的还是真 venv，等于没测（"被测对象与使用对象不是同一个"，ADR-C-014 同型）
            if wmeas.get("venv_override"):
                ev["venv"] = wmeas["venv_override"]
                ev["compat"] = _collect_compat(Path(wroot), wmeas["venv_override"], None, None)
        rep = Report()
        run_pi05_checks(ev, rep, Path(wroot), Path(wodir))
        got = _status_of(rep, want_check)
        if want_check == "__verdict__":
            adm = admission_of(rep)
            got = adm
            ok = (adm != "PASS") if want == "NOT_PASS" else (adm == want)
        elif want == "RED":
            ok = (got == STATUS_RED)
        elif want == "NOT_RED":
            ok = (got != STATUS_RED and got != "ABSENT")
        elif want == "PASS":
            ok = all(s == STATUS_PASS for s in str(got).split(",")) and got != "ABSENT"
        elif want == "UNJUDGED":
            ok = (got == STATUS_UNJUDGED)
        else:
            ok = (got == want)
        matched = None
        n_viol = None
        if must_contain is not None and ok and not str(want_check).startswith("__"):
            blob = json.dumps([c for c in rep.checks if c["id"].startswith(want_check)],
                              ensure_ascii=False, default=str)
            matched = (must_contain in blob)
            ok = bool(matched)
        if exact_viol is not None and not str(want_check).startswith("__"):
            n_viol = sum(len((c.get("observed") or {}).get("violations") or [])
                         for c in rep.checks
                         if c["id"].startswith(want_check) and isinstance(c.get("observed"), dict))
            if n_viol != exact_viol:
                ok = False
        # ---- 裁定 86.6-3：作用面（specificity）与成因键（must_contain）是特异性的两半 ----
        cur_status = {c["id"]: c["status"] for c in rep.checks}
        spec = _specificity_of(base_status, cur_status, want_check, want,
                               (MUTATION_COLLATERAL.get(mid) or {}).get("ids"))
        spec["declared_why"] = (MUTATION_COLLATERAL.get(mid) or {}).get("why")
        spec["declared_family"] = (MUTATION_COLLATERAL.get(mid) or {}).get("family")
        spec_rows.append({"id": mid, "specificity_ok": spec["specificity_ok"],
                          "scope": spec["scope"], "flipped": spec["flipped"],
                          "target_flipped": spec["target_flipped"],
                          "undeclared_collateral": spec["undeclared_collateral"],
                          "declared_collateral": spec["declared_collateral"],
                          "declared_but_not_flipped": spec["declared_but_not_flipped"],
                          "declared_why": spec.get("declared_why"),
                          "declared_family": spec.get("declared_family"),
                          "reasons": spec["reasons"]})
        if spec["specificity_ok"] is False:
            for rs in spec["reasons"]:
                print("        特异性不成立：%s" % rs)
        tag = {True: "抓住", False: "**没抓住（牙失效）**"}[ok] if want in ("RED",) else \
              {True: "未误报", False: "**误报（假红/恒红）**"}[ok]
        print("%-4s %-22s %-10s %-14s %s%s ⇒ %s" % (
            mid, want_check, want, got, desc,
            ("" if matched is None else ("［判词含 %r］" % must_contain if matched
                                         else "［**判词缺 %r**］" % must_contain))
            + ("" if n_viol is None else
               ("［违例 %d/%d 条］" % (n_viol, exact_viol) if n_viol == exact_viol
                else "［**违例 %d 条，要求恰好 %d 条**］" % (n_viol, exact_viol))), tag))
        if not ok:
            for c in rep.checks:
                if c["id"].startswith(want_check) or want_check.startswith("__"):
                    o = c["observed"]
                    if isinstance(o, dict) and o.get("violations"):
                        print("        %s: %s" % (c["id"], o["violations"][:2]))
        results.append(ok)
        rows.append({"id": mid, "tamper": tamper, "target": want_check, "want": want,
                     "got": got, "ok": ok, "desc": desc,
                     "must_contain": must_contain, "must_contain_matched": matched,
                     "exact_violations_expected": exact_viol, "exact_violations_actual": n_viol,
                     "layer": "world", "specificity": spec,
                     "checks": [{"id": c["id"], "status": c["status"]} for c in rep.checks]})

    n_ok = sum(1 for r in results if r)
    n_rev = sum(1 for m in MUTATIONS if m[3] in ("NOT_RED", "PASS", "NOT_PASS", "WARN",
                                                 "UNJUDGED"))
    n_t = sum(1 for r in rows if r.get("layer") == "transcription")
    n_t_rev = sum(1 for r in rows if r.get("layer") == "transcription"
                  and str(r.get("id")) in ("T6", "T11"))
    n_s = sum(1 for r in rows if r.get("layer") == "meta_specificity")
    n_s_rev = sum(1 for r in rows if r.get("layer") == "meta_specificity"
                  and str(r.get("id")) in ("T13", "T15"))
    n_n = sum(1 for r in rows if r.get("layer") == "normalization")
    n_n_rev = sum(1 for r in rows if r.get("layer") == "normalization"
                  and str(r.get("id")) in ("N2",))
    n_vc = sum(1 for r in rows if r.get("layer") == "verdict_caliber")
    # 口径层的"反向"= 要求 `ok=true` 的那两条（O1/O4）：世界层/T 层的反向防的是**恒红**，
    # 这一层对应的病是**恒假**（`ok_of` 永远给 false ⇒ `admission_granted` 永远拿不到 true）。
    n_vc_rev = sum(1 for r in rows if r.get("layer") == "verdict_caliber"
                   and str(r.get("id")) in ("O1", "O4"))
    n_w = sum(1 for r in rows if r.get("layer") == "world")
    # ---- 声明的层计数 vs 实测的层行数（裁定 92.3-ii 的同族纪律，用在自检产物自己身上）----
    # `teeth.layers` 里的 `n` 是**声明**（由常量算出），`rows` 里的 `layer` 是**实测**。
    # 两处各写一份而没有人对它们做差，就是本轮正式判定里 A3 第一版犯的那个错的自检版：
    # 数字并排放着，差值没人解释。⇒ 这里做差，且**不一致就让 `all_ok=false`**（收紧，不是放宽）。
    counts_declared = {"world": len(MUTATIONS), "transcription": N_TRANSCRIPTION_TEETH,
                       "meta_specificity": N_META_SPECIFICITY_TEETH,
                       "normalization": N_NORMALIZATION_TEETH,
                       "verdict_caliber": N_VERDICT_CALIBER_TEETH,
                       "assembly": 1, "baseline": 1}
    counts_measured = {"world": n_w, "transcription": n_t, "meta_specificity": n_s,
                       "normalization": n_n,
                       "verdict_caliber": n_vc,
                       "assembly": sum(1 for r in rows if r.get("id") == "A1_missing_tooth"),
                       "baseline": sum(1 for r in rows if r.get("id") == "baseline")}
    counts_mismatch = {k: {"declared": counts_declared[k], "measured": counts_measured[k]}
                       for k in counts_declared if counts_declared[k] != counts_measured[k]}
    counts_agree = (not counts_mismatch) and (len(spec_rows) == n_w)
    if not counts_agree:
        print("**层计数声明 vs 实测不一致**：%s（`len(spec_rows)`=%d vs 世界层 %d）"
              % (counts_mismatch, len(spec_rows), n_w))
    # ---- 裁定 86.6-3：特异性的机器汇总（不是文书登记）----
    n_spec_true = sum(1 for s in spec_rows if s["specificity_ok"] is True)
    n_spec_false = sum(1 for s in spec_rows if s["specificity_ok"] is False)
    n_spec_na = sum(1 for s in spec_rows if s["specificity_ok"] is None)
    all_specific = (n_spec_false == 0)
    spec_offenders = [{"id": s["id"], "flipped": s["flipped"],
                       "undeclared_collateral": s["undeclared_collateral"],
                       "declared_but_not_flipped": s["declared_but_not_flipped"],
                       "target_flipped": s["target_flipped"], "reasons": s["reasons"]}
                      for s in spec_rows if s["specificity_ok"] is False]
    # 附带翻动的**成因族**汇总：让 D 一眼看清"这 10 条不是 10 个各自独立的借口"，
    # 而是三个族（两个是判据设计后果、一个是世界真有两个缺陷）。
    spec_families = {}
    for s in spec_rows:
        if s["declared_collateral"]:
            spec_families.setdefault(s.get("declared_family") or "undeclared_family", []).append(s["id"])
    print("-" * 100)
    print("变异测试：%d/%d 条判定符合预期（= 1 条 baseline + 1 条 A1 装配层 + %d 条转录层 T + "
          "%d 条特异性元判据 T + %d 条归一台账层 N + %d 条口径层 O + %d 条世界层 M；"
          "反向 %d 条 = 世界层 %d + 转录层 %d + 元判据 %d + 归一台账 %d + 口径层 %d）"
          % (n_ok, len(results), n_t, n_s, n_n, n_vc, len(MUTATIONS),
             n_rev + n_t_rev + n_s_rev + n_n_rev + n_vc_rev,
             n_rev, n_t_rev, n_s_rev, n_n_rev, n_vc_rev))
    print("特异性（裁定 86.6-3 `mutant_specificity_required`）：世界层 %d 条 ⇒ 成立 %d / "
          "**不成立 %d** / 显式声明不适用 %d（全局作用域目标 %s）；已声明的附带翻动涉及 %d 条变异"
          % (len(spec_rows), n_spec_true, n_spec_false, n_spec_na,
             list(SPECIFICITY_GLOBAL_TARGETS),
             sum(1 for s in spec_rows if s["declared_collateral"])))
    if not all_specific:
        print("**特异性不成立的变异体（逐条）**：")
        for s in spec_offenders:
            print("   %-5s flipped=%s undeclared=%s target_flipped=%s"
                  % (s["id"], s["flipped"], s["undeclared_collateral"], s["target_flipped"]))
    print("自检总判：%s（判定 %d/%d、特异性不成立 %d 条、层计数声明==实测 %s）"
          % ("ALL OK" if (n_ok == len(results) and all_specific and counts_agree)
             else "**NOT OK**", n_ok, len(results), n_spec_false, counts_agree))
    doc = {"spec": "π₀.₅ 准入闸的变异自检（证明判据有牙，裁定 27.1 / 裁定 39.1 双向有牙）",
           "gate_build": _sha12(Path(__file__)),
           "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "generated_by": "scripts/b2_env_admission_pi05.py --selftest",
           "all_ok": bool(n_ok == len(results) and all_specific and counts_agree),
           "all_ok_criterion": ("(判定符合预期的条数 == 总条数) **且** (特异性不成立条数 == 0) "
                                "**且** (每一层的**声明**计数 == **实测**行数，且 "
                                "`len(specificity.per_mutant)` == 世界层条数)。裁定 86.6-3：特异性"
                                "不成立会让 `all_ok=false`；第三个合取项是裁定 92.3-ii 的同族纪律"
                                "用在自检产物自己身上（数字并排放着、差值没人解释 = 没对账）。"
                                "两者都会让正式判定里的 `A0_teeth_current` 判红 ⇒ 不会只停在自检里"),
           "n_ok": n_ok, "n_mutations": len(results),
           "n_reverse": n_rev, "baseline_all_green": base_green,
           "n_reverse_all_layers": (n_rev + n_t_rev + n_s_rev + n_n_rev),
           "n_reverse_all_layers_incl_caliber": (n_rev + n_t_rev + n_s_rev + n_n_rev + n_vc_rev),
           # 裁定 93.8：产物**顶层**必须落 `pattern_coverage_probe`（缺 ⇒ `not_measured`、不得报绿）。
           # 这里落的是 O5 那条源码模式审计器的对照探针（注入 6 条已知坏形态 + 4 条好形态负对照）。
           "pattern_coverage_probe": _o5_coverage,
           "layer_counts_declared_vs_measured": {
               "declared": counts_declared, "measured": counts_measured,
               "agree": counts_agree, "mismatch": counts_mismatch,
               "declared_source": ("`len(MUTATIONS)` 与常量 `N_TRANSCRIPTION_TEETH` / "
                                   "`N_META_SPECIFICITY_TEETH` / `N_NORMALIZATION_TEETH` / "
                                   "`N_VERDICT_CALIBER_TEETH`"),
               "measured_source": "`mutations[].layer` 的实测行数",
               "why_it_matters": ("声明与实测各写一份而不对差值，就是本轮 A3 第一版那个错的"
                                  "自检版（跨轮累积量 vs 本轮量被当成同一个量对账）")},
           "specificity": {
               "ruling": "裁定 86.6-3 `mutant_specificity_required`（挂在红线 "
                         "`tooth_must_be_mutant_proven` 之下）",
               "baseline_status_map": base_status,
               "n_world_mutants": len(spec_rows),
               "n_specificity_ok": n_spec_true,
               "n_specificity_failed": n_spec_false,
               "n_declared_not_applicable": n_spec_na,
               "all_specific": all_specific,
               "global_targets_declared_not_applicable": list(SPECIFICITY_GLOBAL_TARGETS),
               "why_not_applicable": ("这两类目标动的是**整个世界**（M16 = A2 未交件、"
                                      "M19/M31 = 干净世界），「只翻动目标牙」在语义上不适用；"
                                      "**显式声明不适用**（`specificity_ok=None`，不是 True）"
                                      "⇒ T15 钉住这条路径不得退化成假绿"),
               "offenders": spec_offenders,
               "declared_collateral_table": MUTATION_COLLATERAL,
               "declared_collateral_families": spec_families,
               "declared_collateral_discipline": (
                   "一条附带翻动必须有**物理成因**（写进 `MUTATION_COLLATERAL[<id>]['why']`）才许声明；"
                   "写不出成因的不许声明，去改变异体构造让它隔离（裁定 78.1）。声明本身也会被核："
                   "声明了却**没有**翻动 ⇒ `declared_but_not_flipped` ⇒ 特异性不成立"
                   "（登记表不许以文书形态活下来，裁定 86.6-3）。本轮 10 条声明分成 3 个成因族，"
                   "其中只有 M14 带构造缺陷性质 ⇒ 已另加 M66 的隔离世界补上证明"),
               "meta_teeth": {"ids": ["T%d" % i for i in
                                      range(N_TRANSCRIPTION_TEETH + 1,
                                            N_TRANSCRIPTION_TEETH + N_META_SPECIFICITY_TEETH + 1)],
                              "what": ("元判据 `_specificity_of` **自己**的四颗牙：T12 未声明附带翻动"
                                       "⇒False、T13 已声明⇒True（防恒假）、T14 翻不动目标牙⇒False、"
                                       "T15 全局作用域必须回 None 而不是 True（防假绿）"),
                              "why": "裁定 27.1：从没咬过的守卫等于没有守卫；86.6-3：元判据必须由机器看守"},
               "per_mutant": spec_rows,
           },
           # 裁定 78.4 的①：委托闸（freeze）的牙分两层，两层都在本自检里可数
           "layers": {
               "world": {"n": len(MUTATIONS), "n_reverse": n_rev,
                         "what": "合成 A2 交付世界（`_mk_world`）+ 八条 π₀.₅ 牙"},
               "transcription": {
                   "n": n_t, "n_reverse": n_t_rev, "ids": [r["id"] for r in rows
                                                            if r.get("layer") == "transcription"],
                   "what": ("喂**合成的 guard 产物**给 `_transcribe_guard`：T1–T5 每个 G 各打一条 RED"
                            "（聚合必须红 + id 精确点到条）、T6 反向（全绿不得误报）、"
                            "T7 前导空格、T8 `check_id` 缺失不留 null、T9 三值集外必须弃权"
                            "（只看上游 summary 会假绿）、T10/T11 钉住上游自检 stdout 的覆盖解析器")},
               "assembly": {"n": 1, "ids": ["A1_missing_tooth"],
                            "what": "判词装配层（漏跑一条牙必须红）"},
               "meta_specificity": {
                   "n": n_s, "n_reverse": n_s_rev,
                   "ids": [r["id"] for r in rows if r.get("layer") == "meta_specificity"],
                   "what": ("`_specificity_of` 自己的牙（裁定 86.6-3 要求「证明本身必须由机器元判据"
                            "看守」⇒ 元判据也必须被证明会判 False）")},
               "normalization": {
                   "n": n_n, "n_reverse": n_n_rev,
                   "ids": [r["id"] for r in rows if r.get("layer") == "normalization"],
                   "target": "A3_delegated_docs_normalized",
                   "what": ("归一台账层：`A3` **自己**的牙（此前欠账 ⇒ 看守者没被看守）。"
                            "N1 = `normalized/` 里多摆一份游离的有效副本（放在布局 v2 的位置，"
                            "顶层移动步骤抓不到）⇒ 不变式 (ii)「台账 vs 磁盘」必须红且判词点名"
                            "「台账漏登或多登」；N2 = **反向**（干净世界 + 没有 D 点名的作用域 ⇒ "
                            "`matches_d_count` 记 `None`、A3 必须 PASS，钉住"
                            "「没测到」不得被读成「不合格」）；N3 = 造一个恰名 `%s` 的作用域但只放 "
                            "2 份 ⇒ 与 D 的 %d 份 / %d 条对不上账、A3 必须红，且 `identity_holds` "
                            "仍为 True（红只来自对账，不是顺带咬了 find 不变式）"
                            % (D_FINDING_SCOPE_DIR, D_FINDING_N_DOCS, D_FINDING_N_CHECKS)),
                   "why": ("红线 `tooth_must_be_mutant_proven`（裁定 27.1）：本轮 A3 第一版把"
                           "「全部副本 - 有效副本」去对「本轮移入数」，而旧副本目录是**跨轮累积**的"
                           "⇒ 第二轮必假红，自检里没有一颗牙挡得住（与 D 的第 16 号同型，"
                           "裁定 90.5 #16）。三条牙各自**恰好 1 条违例**（牙内部的作用面，"
                           "同 M66 的 `exact_viol`，裁定 86.6-3 的第三维）"),
                   "isolation": ("不用 `_mk_world`：A3 的证据面就是 out_dir/`normalized/` 本身，"
                                 "不动八条 π₀.₅ 牙 ⇒ 不与世界层变异体互相污染")},
               "verdict_caliber": {
                   "n": n_vc, "n_reverse": n_vc_rev,
                   "ids": [r["id"] for r in rows if r.get("layer") == "verdict_caliber"],
                   "target": "ok_of / admission_of / EXIT（顶层判据本身）",
                   "caliber_marker": OK_CALIBER_MARKER,
                   "ruling": ("裁定 78.2（`ok` 是唯一失败判据 + UNJUDGED 计入非绿）+ 裁定 93 / "
                              "D→B2 执行单 20260930 §四-1（RR-B2-09 改判：**WARN 不计失败"
                              "但必须登记**）"),
                   "what": ("顶层口径层 O1–O5：O1 只加 WARN ⇒ `admission` 标签仍是 `WARN` 而 "
                            "`ok=true`（改判的正向钉；旧口径在这里给 false ⇒ 裁定 93.1 的 "
                            "RED→WARN 会被本闸二次判死）；O2 只加 UNJUDGED ⇒ `ok=false`"
                            "（**防放宽过头**：改判只动 WARN 一档，UNJUDGED 仍计入非绿）；"
                            "O3 WARN+RED ⇒ 标签 `RED`、`ok=false`（WARN 不得稀释 RED）；"
                            "O4 全 PASS ⇒ `ok=true`（**防恒假**）；O5 **同源牙**：用 "
                            "`inspect.getsource` 证明 `build_verdict` 与 `_normalize_guard_doc` "
                            "都真的调 `ok_of(`、旧的 `adm == \"PASS\"` 两处写法已消失、"
                            "`OK_CRITERION` 与 `ok_of.__doc__` 都带口径标记、`EXIT['WARN']==0` "
                            "而 RED/UNJUDGED 非 0、`admission_of` 仍有 WARN 一档、判词仍带 "
                            "`warn_registered_not_blocking` 登记块"),
                   "why": ("红线 `tooth_must_be_mutant_proven`（裁定 27.1）：**改判本身也是判据**，"
                           "没有牙的改判等于一次无人看守的口径变更 —— 下一版可以悄悄改回去，"
                           "而「悄悄加严」与「悄悄放宽」都会以『已验证』的形状活下来"
                           "（裁定 86.6-3 同族）。O2/O3 防「借着改判把 UNJUDGED/RED 一起放掉」，"
                           "O1/O4 防「把 `ok` 改成恒假或恒真」，O5 防「helper 定义了没接上」与"
                           "「代码改了、散文没改」（判据与散文不同源，裁定 27 / 35.3 / 37.4 / 78.3）"),
                   "isolation": ("不用 `_mk_world`：被测对象是判据函数本身，用合成 `Report` 造"
                                 "计数组合 ⇒ 不与世界层/归一层的变异体互相污染；O5 的源码探针是"
                                 "**只读**的（`inspect.getsource`），不改任何文件")},
               "upstream_criteria_teeth": {
                   "where": "现场判定里的 `G1-G5_freeze_teeth`（本轮亲自复跑上游 `--selftest`）",
                   "why_not_in_selftest": ("它要真起子进程跑 B 的脚本；自检里只钉它的**解析器**"
                                           "（T10/T11），复跑本身在正式判定里做并落 "
                                           "`delegated_g1_g5_upstream_teeth.{json,log}`）")}},
           "world": str(base), "mutations": rows}
    print("=" * 100)
    return doc, (0 if doc["all_ok"] else 1)


# RR-B2-09 改判（裁定 93 / D→B2 §四-1）：**WARN → 0**（改判前是 2）。
# 理由：WARN 不是失败 ⇒ 任何按 `rc != 0` 判失败的下游（`&&` 串联的跑批、CI 式包装、
# `subprocess` 后 `check_returncode`）都不该被一条非违例的登记项**二次判死**（D 的原话）。
# 「WARN 发生了」这件事并没有因此丢失：`admission` 标签仍是 `WARN`（登记义务在标签里）、
# 产物里有 `warn_registered_not_blocking` 块、stdout 仍打印 WARN 计数与逐条 id。
# `--expect pass|red|unjudged` 的语义**不变**（它们比的是 `admission` 标签，不是 `ok`）：
# 显式要求「标签必须是 PASS」的调用方在 WARN 世界仍拿到 rc=1，那是调用方自己加严，与本条无关。
EXIT = {"PASS": 0, "RED": 1, "WARN": 0, "UNJUDGED_evidence_missing": 3}


def main():
    ap = argparse.ArgumentParser(
        description="B2 线：π₀.₅ 新环境的可复现性准入闸（复用 G1–G5 + V0–V9，另加 V-pi05-1…8）")
    ap.add_argument("--root", default=str(ROOT_DEFAULT))
    ap.add_argument("--a2-dir", default=A2_DIR_DEFAULT,
                    help="A2 的交付目录（含 requirements.lock.txt / env_manifest.json / "
                         "weights_receipt.json / resolve_dryrun.txt）")
    ap.add_argument("--venv", default=PI05_VENV_DEFAULT, help="A2 新建的 π₀.₅ venv（软链路径）")
    ap.add_argument("--out-dir", default=None, help="缺省 runs/vla/b2_env_admission_<今天>")
    ap.add_argument("--no-live", action="store_true",
                    help="不探真实解释器（只判文件层）⇒ 依赖活体探针的判据一律 UNJUDGED，不判绿")
    ap.add_argument("--no-verify-sha256", action="store_true",
                    help="不复算权重 sha256（14.47 GB 级读取）⇒ V-pi05-2 记 UNJUDGED")
    ap.add_argument("--ctrl-hz-doc", default=None,
                    help="A2 的控制频率交件（裁定 45.4/45.5 的三元组）。缺省按候选表自动发现")
    ap.add_argument("--compat-report", default=None,
                    help="A2 的兼容目录报告 `compat_dir_report.json`（裁定 44.2）。缺省自动发现")
    ap.add_argument("--no-delegate", action="store_true",
                    help="不调用 B 的 G1–G5 / V0–V9（缺委派 ⇒ 准入不得给 PASS）")
    ap.add_argument("--no-normalize-siblings", action="store_true",
                    help="只归一当轮 out_dir 下的委派产物，不跨轮扫 `runs/vla/b2_env_admission_*`"
                         "的兄弟目录（缺省会跨轮扫 —— 因为 D 在裁定 78.3 点名的 9 份 / 45 条"
                         "全在 20260929 那一轮下；只扫当天会与 D 的计数对不上账）")
    ap.add_argument("--selftest", action="store_true", help="变异自检：证明八条牙都咬得动")
    ap.add_argument("--expect", choices=["auto", "pass", "red", "unjudged"], default="auto")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    today = datetime.now().astimezone().strftime("%Y%m%d")
    out_dir = Path(a.out_dir) if a.out_dir else (root / ("runs/vla/b2_env_admission_%s" % today))
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if a.selftest:
        doc, rc = selftest()
        # 自检产物落**正式产物目录**，A0 才核得到它与当前构建同源（裁定 27.1 + V9 的同型纪律）
        p = out_dir / "mutation_verdict.json"
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print("变异自检产物：%s（all_ok=%s，gate_build=%s）" % (p, doc["all_ok"], doc["gate_build"]))
        # AGENTS.md：不 rm；/tmp 在 overlay、回收站在 NFS ⇒ 必须 shutil.move（rename 会 EXDEV）
        world = Path(doc["world"])
        if world.exists() and str(world).startswith("/tmp"):
            try:
                RECYCLE_BIN.mkdir(parents=True, exist_ok=True)
                dst = RECYCLE_BIN / ("%d_b2_env_admission_selftest" % int(time.time()))
                shutil.move(str(world), str(dst))
                print("临时世界已 mv 到回收站：%s" % dst)
            except Exception as e:
                print("临时世界 mv 失败（%s: %s），留在 %s" % (type(e).__name__, e, world))
        sys.exit(rc)

    a2_dir = Path(a.a2_dir)
    if not a2_dir.is_absolute():
        a2_dir = root / a2_dir
    py = sys.executable
    ev = collect(root, a2_dir, a.venv, out_dir, live=not a.no_live,
                 verify_sha256=not a.no_verify_sha256,
                 ctrl_hz_doc=a.ctrl_hz_doc, compat_report=a.compat_report)
    rep = Report()
    check_a0_teeth(ev, rep, out_dir)
    delegated = {}
    delegated["g"] = delegate_g1_g5(ev, rep, root, a2_dir, a.venv, out_dir, py,
                                    run_it=not a.no_delegate)
    delegated["v"] = delegate_v0_v9(ev, rep, root, out_dir, py, run_it=not a.no_delegate)
    # 裁定 78.3：委派产物（含 history/ 与 replay_run2/ 下的历史份）全部落归一副本 + 台账。
    # 放在委派之后、判词装配之前 ⇒ 本轮新产的 2 份也一起归一（D 数的是 45 条，不是 10 条）。
    # **跨轮扫**：D 数的 9 份 / 45 条全在 `runs/vla/b2_env_admission_20260929/` 下，只扫当天
    # out_dir 会漏掉它们（本轮正式判定的第一跑就实测漏了：只归到 3 份 / 10 条）。
    # 兄弟目录只取 B2 自己写入面里的 `b2_env_admission_*`（裁定 38.3 的线前缀），
    # 且**只读**：归一副本一律落在当轮 out_dir 下，历史目录里一个字节都不写。
    sibling_roots = []
    if not a.no_normalize_siblings:
        vla = root / "runs/vla"
        if vla.is_dir():
            sibling_roots = sorted(p for p in vla.glob("b2_env_admission_*")
                                   if p.is_dir() and p.resolve() != out_dir.resolve())
    delegated["norm"] = normalize_all_guard_docs(out_dir, rep, extra_roots=sibling_roots)
    run_pi05_version_checks(ev, rep, root)

    doc = build_verdict(ev, rep, root, a2_dir, out_dir, a.venv, delegated)
    print_verdict(doc, a.quiet)
    jp = Path(a.json_out) if a.json_out else (out_dir / "admission_verdict.json")
    if not jp.is_absolute():
        jp = root / jp
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n")
    if not a.quiet:
        print("写出:", jp)
    adm = doc["admission"]
    if a.expect == "pass":
        sys.exit(0 if adm == "PASS" else 1)
    if a.expect == "red":
        sys.exit(0 if adm == "RED" else 1)
    if a.expect == "unjudged":
        sys.exit(0 if adm.startswith("UNJUDGED") else 1)
    sys.exit(EXIT.get(adm, 1))


if __name__ == "__main__":
    main()
