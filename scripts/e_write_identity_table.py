#!/usr/bin/env python3
"""机器生成「散文可核身份表」—— D 的裁定 89.7 新规则
`prose_identity_must_be_verifiable_against_a_saved_artifact` 的落地工具。

规则原文：**散文里引用的每个身份串，必须存在一个机器保存的产物其 sha 与散文值相等；
若不存在这样的产物，散文就只引产物路径、不引 sha。**

E 在 `daily_report.md` §E12.6 恰好犯过这个错（散文写了 sha1[:12]，而本仓口径是 sha256[:12]），
D 靠 before 影像一条命令判定。⇒ 本脚本的做法照 C2（**落笔时刻由脚本生成身份表**，本仓最稳）：

- **两种算法都给**（`sha256_12` = 本仓引用口径；`sha1_12` = 只为让「算法错配」这类错误一眼可见），
  并显式写 `citation_algo: "sha256[:12]"`，引用方不得取另一个。
- **行数用 `wc -l` 口径**（= 换行符个数），与 D/A2/B2/C2 散文里的「N ln」一致；
  同时给 `n_lines_splitlines`，两者不同就说明文件不以换行结尾（也是一个可核事实）。
- **拒绝覆写**：目标已存在 ⇒ exit 3（本仓 `overwrite_own_artifact` 纪律）；
  `--force` 才允许，且**先把旧件移进 `before_images/`**（裁定 83.5 / `OVERWRITE_EVENT_20260929_2345.md`）。
- **空清单 ⇒ exit 4**（裁定 88.3-2：空集上不许给出「通过」形状的产物）。
- **缺失文件不静默跳过**：逐个记 `missing: true` 并使 exit=5 —— 表里缺一行比多一行更危险。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# (相对仓库根的路径, 为什么它重要, 可以被引用成什么)
TARGETS: list[tuple[str, str, str]] = [
    # ---- 本轮改动的脚本 ----
    ("scripts/e_egl_coldstart.py",
     "P0 一条命令恢复的驱动器；本轮加了顶层 delivery_status/stages_executed/stages_skipped/"
     "c4_gl_renderer_measured/failed_teeth、all_teeth_proven 的 PARTIAL 档、--manifest-name 拒绝覆写闸、"
     "mutant 牙强化到 4 条腿（空集腿如实标注）；**03:4x 把 tooth_relink 的断言从 exit_zero 改为 "
     "exit_partial_5（精确等值、非放宽），实测 tooth_proven=true**",
     "冷启动交付的生成器（裁定 85.9-3 / 87.1-4 / 89.5-1）"),
    ("runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_relinktooth_exit5.json",
     "**exit 5 修法的验证件**（只跑 relink 一阶段、纯 CPU、未触卡）：tooth_relink 三条断言全 ok、exit_code=5、"
     "boundary_clean_no_system_write=true、c4_gl_renderer_measured=false（如实标未测）；顶层 delivery_status=PARTIAL "
     "⇒ 裁定 87.1-2 的正确行为。**不取代 v3**",
     "牙证明（**不得**当冷启动交付引用）"),
    ("scripts/e_gpu_egl_verify.py",
     "**采样窗竞态的根因修在这里**：run_child 从子进程起跑就轮询 fd（20 ms 级、覆盖整个生命期），"
     "并把「没采到」与「采到但为空」拆成 gpu_sampling.{fds,smi}_measured_not_assumed 两个字段；"
     "fd 轮询对 cpu 臂也生效 ⇒ N5 不再平凡真。**签名向后兼容**",
     "自证件的生成器；A2/B2/C2 若复用其采样函数需知本轮已改"),
    ("scripts/e_activate_selfcheck.py",
     "GPU 臂观测窗 0.6s/400帧 → 1.2s/8000帧（可 env 覆盖 E_PROBE_BENCH_SECONDS/E_PROBE_FRAMES；cpu 臂未动）；"
     "新增 invalid_measurement 判定 + **exit 2**（≠ fail/exit 1）",
     "L1–L6 判据的实现处；exit 2 的语义定义处"),
    ("scripts/e_coldstart_gpu_render.sh",
     "**运维真正会敲的那一条命令**；本轮把 C4 的 exit 1/2/3 分成三条不同文案（仍全部 ≠0，无任何放宽）；"
     "**03:4x 又修掉一个退出码层面的假绿**：E_SKIP_GPU=1（只跑 C1–C3、GPU 未测）原本 exit 0 ⇒ 改为 **exit 5**"
     "（与 e_egl_coldstart.py 顶层 PARTIAL 同号同义）⇒ 退出码全集 = **0 / 1 / 5**，0 是唯一可读作「可用」的码",
     "docs/infra-gpu-render.md §0 的那一条命令"),
    ("scripts/e_render_determinism.py",
     "T-E-DET-480 的生成器；本轮加了 --cams/--resolution（默认臂字节等价已自证）与**第四道闸**："
     "空 rep 集 ⇒ measurement_status=not_measured_*、all_bitwise_deterministic=null、verdict.not_a_pass、**exit 4**",
     "确定性登记带的生成器（裁定 86.3 / 88.3-2）"),
    ("scripts/e_selfcheck_gate_mutation.py",
     "**本轮新增**：两侧牙的独立证明器（M1–M5），crosscheck GREEN、5 个变异体全部生效、**全程不触卡**",
     "「闸有牙」的证明（不是测量件）"),
    ("scripts/e_invalidate_runs.py",
     "本轮加 MANUAL_INVALIDATIONS + --append-manual-only + 拒绝覆写闸（exit 3，已装牙）",
     "INVALIDATED_RUNS.json 的写入器（裁定 88.5-1）"),
    ("scripts/e_mainline_render_calib.py",
     "**本轮（12:3x–12:4x）按裁定 96.1-③ 改了网③ cmdline 的判据**：裸关键字 ⇒ **真实执行形态 ∧ 关键字 ∧ 非闲置**"
     "（新增 `classify_cmdline()` / `_argv()` / `_proc_cpu()` / `EXEC_FORM_RE`（逐字复用 F 的探针）/ `IDLE_CPU_TICKS`；"
     "`card_busy()` 新增 `cmdline_hits_text_mention_only` 与 `cmdline_net_caliber` 两键，8 个旧键与签名不变）。"
     "**网①（compute-apps）/ 网②（fd）/ 窄档词表 / 宽档正则 / `_cmdline()` / `_own_tree()` 逐字未改**"
     "（ast 逐对象机器比对 7/7，证据见 `CARD_BUSY_FIX_VERDICT.json` 的 `legs.N`）。"
     "修的是 F 实测的两起文本误触发 ⇒ **行为确实变了，这正是修法的目的**；早先那句「逐字未动 / A2·C2 复用行为不受影响」"
     "只对 03:1x 那一轮成立，已在 `--manifest-only` 的 notes 里就地加了 `later_change_96_1_3` 更正条（缺陷类 ㉒）",
     "三网探测器 card_busy() 的所在处（A2/B2/C2 共用口径）"),
    ("scripts/e_coldstart_manifest.py",
     "**本轮新增**：冷启动产物目录的逐文件 MANIFEST 生成器。不复用 write_manifest() 的理由 = 后者表头字段是标定轮专用"
     "（裁定 71 caliber_transplant_ban）。内建：os.walk(followlinks=False)（不跟随符号链接）、"
     "原地重写前自动留前像、有 (未登记) 洞 ⇒ exit 3、空目录 ⇒ exit 4",
     "冷启动目录清单的生成器"),
    ("scripts/e_write_identity_table.py",
     "本脚本：裁定 89.7 新规则的落地工具（散文可核身份表）",
     "身份表的生成器"),
    # ---- 本轮产物 ----
    ("runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json",
     "**冷启动权威件**：delivery_status=COLDSTART_VERIFIED、all_teeth_proven=true、stages_skipped=[]、"
     "c4_gl_renderer_measured=true、failed_teeth=[]、exit 0；C4 实测 GL_RENDERER=NVIDIA A800-SXM4-80GB/PCIe/SSE2",
     "P0 的交付证据（**唯一可引用的那一版**）"),
    ("runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v3.json",
     "**持久化权威清单**：NFS 前缀 34 条的逐文件 sha + rebuild_class 三分层（nfs/overlay_image_baked/overlay_runtime_upper）",
     "「重启后什么会活下来」的机器可读答案"),
    ("runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v2.json",
     "**历史件**：baseline 臂是采样窗竞态造成的**假红**（tooth_proven=false）；原字节保留",
     "禁止当权威；替代件 = _v3"),
    ("runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE.json",
     "**v1 历史件**：fs_of() 未区分镜像只读层/运行期可写层；原字节保留",
     "禁止当权威；替代件 = _v3"),
    ("runs/infra/e_egl_coldstart_20260930/MANIFEST.json",
     "冷启动目录的逐文件清单（**首次生成**）：182 行 = 44 真文件（含清单自身）+ 135 符号链接"
     "（其中 3 条指向目录、登记为 symlink_to_dir）+ 3 空目录、n_unlisted=0；"
     "本轮新留的那份前像按设计不自我引用 ⇒ `find -type f` 会比清单多 1（已对账）",
     "索引（self_sha_caveat：它自己那一行恒为上一版）"),
    ("runs/infra/e_egl_coldstart_20260930/gate_mutation/GATE_MUTATION_SELFTEST_20260930_023715.json",
     "两侧牙自证：verdict_set_crosscheck=GREEN、two_sided_proof_present=true、5 个变异体全部生效、**未触卡**",
     "「闸有牙」的证据"),
    ("runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json",
     "**480×640 egl 侧权威件**：measurement_status=measured、5/5 无跳过、unmeasured_backends=[]、exit 0；"
     "实测三槽都不逐位、量级 1 LSB（max_abs_diff 全 = 1；frac 最差 right_wrist 2.25e-04）",
     "T-E-DET-480 的交付证据 + B2 的 G4d 登记带基础（**仅登记**）"),
    ("runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_OSMESA_REPS5.json",
     "480×640 osmesa 对照臂：三槽 5/5 全逐位、max_abs_diff=0、**未触卡**",
     "逐位对照后端的证据"),
    ("runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json",
     "**已作废**（vacuous_all_reps_skipped_no_measurement）：5 rep 全被让位闸跳过却写 all_bitwise_deterministic=true"
     "（空集上的平凡真）。原字节按 append-only 保留 —— 它是让位闸在真实抢卡场景下生效的唯一实证",
     "**禁止引用**；替代件 = 同名 _r2"),
    ("runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.INVALIDATED.json",
     "机器可读的作废旁证件（含让位闸判对的证据：fd 网 PID 388252、compute-apps 盲、当时 12 MiB）",
     "口径更正（引用作废件时必须同引）"),
    ("runs/infra/e_mainline_calib_20260929/INVALIDATED_RUNS.json",
     "**裁定 88.5-1「先于一切」的那件**：追加 invalidated_manual + invalidated_index，"
     "grep vacuous_all_reps_skipped / TEAM480x640_EGL 双双命中（D 02:2x 实测为 0 命中）；前 800 行字节未动（diff 验过）",
     "作废登记簿（任何线采纳权威值前必须 grep 它）"),
    ("runs/infra/e_mainline_calib_20260929/MANIFEST.json",
     "标定轮产物目录的清单（本轮重生成，129 文件、n_unlisted=0）；本轮只加 _r2 与 round4/round5 前像的描述",
     "索引"),
    ("runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_REPS5.json",
     "224² 的 reps=5 权威件（裁定 83.3 可推翻条件③ 在此被触发）；本轮**未改动**，列出只为 480×640 的对比口径",
     "224² 侧权威件（**本轮不重判它**）"),
    # ---- 本轮改动的文书 ----
    ("docs/infra-gpu-render.md",
     "本轮**追加 §8**（裁定 96.1-③ 的占卡判定新口径：三档判据表 / 六腿证据 / GPU 边界实测 / 四条残留风险），"
     "身份串由工具在落笔时刻现取。此前 11:5x 追加的 **§0.4 权威恢复块**（T-E-9-3）与 03:1x 的 **§0.3** 都在；"
     "§0.3 点名 checkpoint §19.0 的临时版已被取代、§19.0-3 的临时判据按其自身可推翻条件退役 ⇒ **exit code 恢复为权威**；"
     "首 7 行原字节保留（append-only）",
     "三线共用的事实基线（重启恢复指引的权威处）"),
    ("docs/e_handoff_to_d_20260929.md",
     "**新增 §6.4（最终文件身份表，sha 一律指向机器表）+ §6.5（前缀悬空链接的跨线发现）**",
     "E → D 的交付文书"),
    ("docs/e_egl_feasibility_20260929.md",
     "**§6.0 追加结案行**：D 已采甲案（权威 136.99）+ 丙案（egl 采集 / osmesa 对照）⇒ 本节不再悬空；首 7 行原字节保留",
     "可行性权威文书"),
    # ---- 共享文书（E 只追加，不覆写）----
    ("daily_report.md",
     "多写者、append-only。E 本轮追加 §E12.6（窗口 #2 申报）+ §E12.7（销账 + 两项结果）+ §E12.8（更正框 + 交付正文）。"
     "**表内这一行的身份是「生成本表那一刻」的值**；§E12.8 落盘后它会变，引用方须重算",
     "全线共享日志（引用时以追加时刻的机器读数为准）"),
    ("work/decisions/decisions_20260929.md",
     "D 的裁定原本（**E 只读**）。本轮 E 依据的是裁定 87 / 88 / **89**（89 = 双验收轮，P0/P1 均 ACCEPTED 并关闭）",
     "裁定权威源（E 无写入权）"),
    # ---- 2026-09-30 11:0x–12:0x 那一轮（T-E-9 / T-E-11 / T-E-12）----
    ("scripts/e_restart_readiness.py",
     "**本轮新增**：T-E-11 的生成器。28 行 × 5 项全实测；两个轴严格分开（readiness_axis 决定 exit code，"
     "post_restart_verification_axis 恒 not_measured 直到有人真重启）；项 5 自带全绿基线 + G0/M1/M2/M3 四臂变异探针",
     "重启就绪清单的生成器（T-E-11）"),
    ("runs/infra/e_restart_readiness_20260930/RESTART_READINESS.json",
     "**T-E-11 的交付件**：5 项 / 28 行 / 20 条重启后探针 / 5 条可推翻条件（全带 `checked_by`+`checked_when`，裁定 94.9-5）。"
     "verdict=`READY_WITH_NOT_MEASURED`、**exit 2**（唯一一条 not_measured = 「镜像换 python 小版本」那一行，"
     "本轮无从测 ⇒ 如实记，不写 restored）",
     "断点续跑保险线的权威件（D 执行单 §一）"),
    ("scripts/e_evidence_snapshot.py",
     "**11:4x 新增 · 12:5x 改**：T-E-12（裁定 94.9-6）的生成器。白名单 **34** 条 spec（12:5x 按裁定 96.3 加入 F 的 "
     "`PROGRESS_LEDGER.json` / `TRIGGER_REGISTRY.json`，E 另自决补自己的 Ⅰ 类两件：`CARD_BUSY_FIX_VERDICT.json` 与 "
     "`*.SIDECAR.json`）、200 MiB 单文件闸、4 GiB 总读量闸、`verdict` 三值提取（取不到 ⇒ null，绝不填绿）、"
     "93.8 对照探针（注入清单外文件必须被检出）。新增 `--supersedes` / `--why-regenerated`（v1→v2 另出一份、原字节保留，"
     "与 `PERSIST_MANIFEST_v3→v4` 同形状）。**根因修一处**：相对 `--out` 会在哈希全部跑完之后才炸"
     "（实测白跑 6 m 28 s）⇒ 入口处一次性归一为绝对路径",
     "最小证据快照的生成器（T-E-12）"),
    ("runs/infra/e_evidence_snapshot_20260930/EVIDENCE_SNAPSHOT.json",
     "**T-E-12 的 v1 交付件（11:5x）**：211 件已 hash、读量 362.47 MiB（= 4 GiB 预算的 0.0885%）、探针 detected=true、"
     "1 条 spec 未命中（如实登记 + 带 scan_scope）。**原字节保留、不改一个字节**，已被 v2 取代（见下一条）",
     "v1（**已被 v2 取代**，但字节仍是 11:5x 那一刻的权威读数）"),
    ("runs/infra/e_evidence_snapshot_20260930/EVIDENCE_SNAPSHOT_v2.json",
     "**T-E-12 的当前权威件（12:5x–13:0x）**：v1 的 30 条 spec + 裁定 96.3 点名的 F 两件 + E 自决的 Ⅰ 类两件；"
     "`supersedes` 里钉着 v1 的身份（原字节保留）。**读量仍受 ≤4 GiB 硬约束**（v1+v2 累计读量写进产物与日报）",
     "服务器关掉之后唯一还能证明「证据曾经存在、判词是什么」的件（**当前版**）"),
    ("docs/evidence_snapshot_manifest_20260930.md",
     "**T-E-12 的入库摘要**（B2 代提交 ⇒ 进 git）。由工具生成，身份串人不碰（裁定 92.3(i)）",
     "证据快照的 git 侧副本"),
    ("scripts/e_authority_annotations.py",
     "**本轮新增**：裁定 92.1(a)(b) 两个机器可读标注的生成器。三个 scope 严格分开"
     "（A=v3 的 tooth_relink.exit_code 历史值 · B=480×640 团队三槽 · C=224² 采集臂），"
     "**不选一个、不平均**（D 的 T-E-9.1 把 B 的相机名与 C 的 0.052% 写在了一句里）",
     "旁证件的生成器（不改 v3 一个字节）"),
    ("runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.ANNOTATIONS.json",
     "**裁定 92.1(a)(b) 的旁证件**：`tooth_relink.exit_code` 的 0 是历史值 / 当前期望 5（`e_coldstart_gpu_render.sh:106`）；"
     "`reproduction_caliber_gap` 按 A/B/C 三个 scope 分开登记。8 条自检全过、v3 原字节与前像逐位相同",
     "T-E-9-1 的交付件（**旁证**，v3 仍是唯一权威）"),
    ("runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v4.json",
     "**当前权威持久化清单**（裁定 92.2）：34 条目 / 339,337,693 B（与 v3 逐位相同）+ 新的 "
     "`prefix.link_audit`（verdict=measured、n_links_audited=11、**n_dangling=0**）+ 逐条 `link_target_exists`/`dangling`。"
     "`supersedes=v3`、`superseded_by=null`、`coldstart_evidence_authority_still=COLDSTART_EVIDENCE_v3.json`",
     "「重启后什么会活下来」的机器可读答案（**权威**；替代 v3）"),
    ("runs/infra/e_egl_coldstart_20260930/MANIFEST_ONLY_RUN_for_PERSIST_v4.json",
     "生成 v4 清单那一轮的伴随 evidence 件（只跑 `manifest` 一阶段、纯 CPU、未触卡）："
     "`delivery_status=PARTIAL`、`stages_skipped=[chain,relink,mutant,baseline]`、`c4_gl_renderer_measured=false`、**exit 5**",
     "**不得**当冷启动交付引用（裁定 87.1-2）；冷启动权威件仍是 v3"),
    ("runs/infra/e_restart_readiness_20260930/V3_TO_V4_DELTA.json",
     "v3→v4 的逐条对账：**23 个真文件的 sha256 与字节数逐条一致**、`total_bytes` 逐位不变、"
     "唯一差异 = 1 条符号链接的目标字符串 ⇒ **v3 的 34 条 sha 记录没有一条过期**（D 在 §E12.8.8 时担心的正是这一点）",
     "前缀改动无害的**不变量证明**"),
    ("scripts/e_link_audit_selfcheck.py",
     "**本轮新增**：`link_audit()` 的两侧牙 + 93.8 模式覆盖探针。注入 5 形态，"
     "命门是 **P3 相对路径悬空**（按「绝对路径」判悬空的审计器会漏它）与 **P4 绝对但存在**（证明不是「绝对即坏」的平凡真）",
     "悬空链接审计器的自证件（不触卡）"),
    ("runs/infra/e_restart_readiness_20260930/LINK_AUDIT_SELFCHECK_prefixstate_before.json",
     "**fix ① 之前**的臂：真前缀实测 `n_dangling=1`（`libnvidia-vksc-core.so.1`）、沙箱 2 条注入悬空全被抓、"
     "两条空集臂都是 `not_measured`+null、`pattern_coverage_probe.detected=true`、exit 0",
     "牙证明（正向：能抓到真缺陷）"),
    ("runs/infra/e_restart_readiness_20260930/LINK_AUDIT_SELFCHECK_prefixstate_after.json",
     "**fix ① 之后**的臂：真前缀 `n_dangling=0`，而沙箱仍是 2 条被抓 ⇒ **检测器没有变成「一律绿」**（反向牙仍在）",
     "牙证明（两侧：修好了 + 牙没钝）"),
    ("runs/infra/e_restart_readiness_20260930/PREFIX_HOLDER_SCAN_pretouch.json",
     "动前缀**之前**的「无活进程持有」实测（比照三网做法，对象换成前缀目录）："
     "五张网（cwd/exe/root/fd/*/maps）、`n_proc_entries_scanned=57`、**`n_holders=0`**。"
     "本机没有 `lsof` ⇒ 用 `/proc` 直扫（如实记方法）",
     "裁定 92.2「核无活进程持有该前缀」的证据"),
    ("scripts/e_install_nvidia_gl_590.sh",
     "**本轮改**（裁定 92.2-②）：新增 `relativize_abs_symlink()`（`:121`），在 `install_one()` 的 `cp -a` 之后（`:160`）"
     "与 dry-run 分支（`:164`）各调一次 ⇒ 驱动包自带的**绝对**符号链接不再原样落地成悬空。"
     "**注意**：裁定 92.2 原文写的是 `scripts/e_persist_egl_590.sh:131`，**该文件名在本仓不存在**；"
     "实际含 `install_one()` 且 `cp -a` 在 **:131** 的是本文件 ⇒ 行号对得上、文件名对不上",
     "系统安装/回滚工具（安装模式已被代码闸挡死，须 `E_ALLOW_SYSTEM_INSTALL=<D 的批准文书路径>`）"),
    ("scripts/e_egl_coldstart.py",
     "**本轮改**（裁定 92.2-③）：新增模块级 `link_audit()`（单一真源，裁定 46.4）+ `build_manifest()` 逐条给 "
     "`target_is_absolute`/`target_resolved`/`link_target_exists`/`dangling`（**实测**，判据是 `Path.exists()` 的真实 stat，"
     "不是字符串形状）+ 空集 ⇒ `verdict=not_measured`+null；新增 `--manifest-extra-json`（编务字段可合并，"
     "**实测字段一律拒绝被外部值覆盖** ⇒ 清单不会变成自我背书）",
     "冷启动取证件 + 持久化清单的生成器"),
    ("rl_harness_supervision/d_handoff_to_e_20260930.md",
     "D 的派工单原件 + **11:3x 的补单**（裁定 94：确认 E 的下位纠正成立、新开 T-E-12、⑤ 降 P2、两条新纪律适用于 E）",
     "E 本轮的任务来源（E 无写入权）"),
    # ---- 2026-09-30 12:3x–13:0x 那一轮（裁定 95 冻结令 + 裁定 96：96.1-③ 的 P0.5 修法）----
    ("scripts/e_card_busy_probe.py",
     "**本轮新增**：裁定 96.1-③ 修法的验证探针（**纯 CPU、不上卡、不需窗口**）。六腿 = 重放（喂真实记录过的 argv）· "
     "活体（诱饵进程自证不碰 GPU）· **新旧差分**（文本腿必须「旧判忙 ∧ 新不判忙」⇒ 断言不是恒真）· "
     "网①②字节未改（ast 逐对象）· 接口未破 · 现场读数；93.8 对照探针**两向都装**（缺陷类 ⑲）；"
     "闲置阈值带**定标实测**（不是拍脑袋常数）；4 条残留风险全带 `checked_by`+`checked_when`（裁定 94.9-5）",
     "P0.5 修法的判词生成器（A2 第一次真上卡的前置之一）"),
    ("runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json",
     "**96.1-③ 的交付件**：verdict=`PASS`、exit 0、六腿全绿（R 12/12 · L/D 4/4 且两向都在 · N 7/7 · I 未破 · "
     "S 11 条自洽判据 · 闲置定标 26 tick vs 0 tick）；GPU 起止 util 0→0 / mem 0→0 MiB / `compute_procs=[]`"
     "（网① `measurement_status=measured`，即「测到的空」不是「没测」）、`nr_throttled` 增量 0",
     "A2 / B2 起跑前该读的那一件（占卡判定现在的口径、证据与作用域边界）"),
    ("runs/infra/e_card_busy_fix_20260930/before_images/e_mainline_render_calib.py.before_96_1_3",
     "**改动前的前像**（`cp -p` 直存）：1279 ln `fd582e261e87`。它同时是差分腿里被 `SourceFileLoader` 加载的"
     "「旧版模块」⇒ 「旧版判忙 ∧ 新版不判忙」这条断言的**旧版就是这一份字节**，不是 E 转述的旧逻辑",
     "散文里「改前 1279 ln `fd582e261e87`」这句话的可核产物（裁定 89.7）"),
    ("runs/infra/e_card_busy_fix_20260930/decoy_self_report_L1.json",
     "**活体正腿诱饵的自证件**：它自己报告 `nvidia_fds=[]` / `nvidia_maps=[]` / `imports=[]` / "
     "`gpu_context_created=false` + 实测 `cpu_ticks`（闲置阈值的定标就取自这里）⇒ 「本轮一条都没上卡」"
     "是**机器自证**的，不是散文声明（裁定 50.1/72：声明必须与产物字段一致）",
     "GPU 边界与闲置定标的原始读数"),
    ("runs/infra/e_restart_readiness_20260930/RESTART_READINESS.CARD_BUSY_FIX_96_1_3.SIDECAR.json",
     "**T-E-11 v1 的旁证更正件**（裁定 96.2 批准的形状）：v1（1757 ln `4587672f186f`）**原字节保留**，"
     "更正 `$.items[3].rows[0].measured.card_busy_byte_identical_claim` 那句已过期（「逐字未动」不再成立）；"
     "并把 v1 未落 `exit_code` 字段这件事**如实记为 null + 登记为 v1 的登记缺口**（不编数，裁定 89.7）",
     "旁证更正（不为一个字段重生成 1757 行 ⇒ Ⅲ 类不扩张，裁定 95.1 冻结令 + 缺陷类 ㉑）"),
    ("runs/infra/e_restart_readiness_20260930/make_card_busy_sidecar.py",
     "上件的生成器（放在 run 目录里、不占 `scripts/` 面；每个身份串在写盘那一刻现读，裁定 92.3(i)；拒绝覆写 exit 3）",
     "旁证更正件的生成器"),
    ("docs/e_platform_request_graphics_capability.md",
     "**⑤ 的平台申请文本（P2 · 裁定 94.7-1⑤ / 96.5）**：本机**不改** `NVIDIA_DRIVER_CAPABILITIES`（维持 "
     "`compute,utility`），只向平台申请加 `graphics`；**已按裁定 77.4 删掉 `/dev/dri` 那一条**（本机 `drm_device_file=null`，"
     "该条已被证伪）；理由 = 渲染腿已由自有前缀 + `__EGL_VENDOR_LIBRARY_FILENAMES` 实测打通，而 `graphics` 必须容器重启才生效",
     "给平台的申请文本（**不是**本机改动；E 的边界：不写系统目录、不 `ldconfig`）"),
]


def sha_of(path: Path, algo: str) -> str | None:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


# ── 裁定 93.8：清单件生成器必须**自证识别模式覆盖**（红线族
#    `reference_auditor_must_prove_its_own_pattern_coverage` / 缺陷类 ⑲）──────────────
def unlisted_in_scope(scope_dirs: list[Path], listed: set[str], cap: int = 5000) -> dict:
    """在**显式声明的范围**里找出「存在、但没被列进清单」的文件。

    **为什么 scope 必须显式声明**：本脚本是**引用清单**（列出被散文引用的那些件），
    不是**完整性清单**（那是 `MANIFEST.json` 的活，它自带 `n_unlisted` + exit 3 的牙）。
    把「完整性」口径硬套到引用清单上 = 裁定 71 `caliber_transplant_ban`。
    ⇒ 没声明 scope 时，本项**不判**，如实记 `not_applicable_this_artifact`（**不是** `n_unlisted=0`）。
    """
    if not scope_dirs:
        return {"scope_declared": False, "verdict": "not_applicable_this_artifact",
                "n_unlisted": None, "unlisted": None,
                "why": ("本件是**引用清单**，不是完整性清单；未声明 `--scope` ⇒ 「清单外文件」这一维不适用。"
                        "**不写成 `n_unlisted=0`**（那会把「没审」冒充成「审过且干净」，红线 88.3-1）。"
                        "完整性由 `MANIFEST.json` 守（`e_coldstart_manifest.py` / `write_manifest()`，有洞 ⇒ exit 3）")}
    unlisted, scanned = [], 0
    for d in scope_dirs:
        d = Path(d).resolve()
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if scanned >= cap:
                return {"scope_declared": True, "verdict": "capped", "cap": cap,
                        "n_unlisted": len(unlisted), "unlisted": unlisted[:60], "n_scanned": scanned,
                        "note": f"达到 cap={cap} ⇒ 计数是**下界**，如实标 capped"}
            if not p.is_file():
                continue
            scanned += 1
            rel = str(p.relative_to(REPO)) if str(p).startswith(str(REPO) + "/") else str(p)
            if rel not in listed:
                unlisted.append(rel)
    return {"scope_declared": True, "verdict": "measured", "cap": cap, "n_scanned": scanned,
            "n_unlisted": len(unlisted), "unlisted": unlisted[:200],
            "scope_dirs": [str(d.relative_to(REPO)) if str(d).startswith(str(REPO) + "/") else str(d)
                           for d in scope_dirs]}


def run_pattern_coverage_probe(out: Path, self_path: Path) -> dict:
    """裁定 93.8 要求的**对照探针**：注入已知形态的坏对象，抓不到 ⇒ 审计器自己红。

    三条臂（缺一即 `detected=false`）：
      B1「清单外」  —— 造一个**真实存在**、但故意不放进清单的文件 ⇒ `unlisted_in_scope` 必须检出它。
      G1 绿见证    —— 已列进清单的文件必须**不**被报为清单外（否则检测器是「一律报」的平凡真）。
      B2 exit 5    —— 用**子进程真跑一次自己**、`--extra-target` 指一个不存在的路径 ⇒
                      必须 `missing: true` **且 exit code == 5**（D 的 §四 点名要「补一个探针产物证明它真的会 exit 5」）。
    """
    out = Path(out).resolve()
    sandbox = out.parent / "identity_table_probe_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    listed_file = sandbox / "listed_artifact.json"
    unlisted_file = sandbox / "INJECTED_not_in_targets.json"
    listed_file.write_text('{"probe": "listed"}\n', encoding="utf-8")
    unlisted_file.write_text('{"probe": "injected_on_purpose_not_in_targets"}\n', encoding="utf-8")

    listed_rel = {str(listed_file.relative_to(REPO))}
    audit = unlisted_in_scope([sandbox], listed_rel)
    b1 = (audit.get("verdict") == "measured"
          and any("INJECTED_not_in_targets.json" in u for u in (audit.get("unlisted") or [])))
    g1 = not any(str(listed_file.relative_to(REPO)) == u for u in (audit.get("unlisted") or []))

    # B2：真跑一次自己（子进程），逼出一条 missing ⇒ 断言 exit 5
    probe_out = sandbox / "PROBE_TABLE_exit5.json"
    bogus = "runs/infra/__definitely_does_not_exist__/nope.json"
    r = subprocess.run([sys.executable, str(self_path), "--out", str(probe_out),
                        "--extra-target", bogus, "--no-probe"],
                       cwd=str(REPO), capture_output=True, text=True, timeout=300)
    b2_detail = {"argv": [sys.executable, str(self_path), "--out", str(probe_out),
                          "--extra-target", bogus, "--no-probe"],
                 "exit_code": r.returncode, "expected_exit_code": 5,
                 "stdout_tail": r.stdout.strip()[-500:], "stderr_tail": r.stderr.strip()[-300:]}
    missing_flagged = False
    if probe_out.is_file():
        try:
            t = json.loads(probe_out.read_text())
            row = (t.get("files") or {}).get(bogus) or {}
            missing_flagged = (row.get("missing") is True and bogus in (t.get("missing") or []))
            b2_detail["table_n_missing"] = t.get("n_missing")
            b2_detail["table_missing_list"] = t.get("missing")
            b2_detail["row_missing_flag"] = row.get("missing")
        except json.JSONDecodeError as exc:
            b2_detail["parse_error"] = f"{type(exc).__name__}: {exc}"
    b2 = (r.returncode == 5 and missing_flagged)

    detected = bool(b1 and g1 and b2)
    res = {"artifact": str(out.relative_to(REPO)) if str(out).startswith(str(REPO) + "/") else str(out),
           "sandbox": str(sandbox.relative_to(REPO)) if str(sandbox).startswith(str(REPO) + "/") else str(sandbox),
           "injected_bad_form": ("B1 = 一个**真实存在**、但故意不放进 `TARGETS` 的文件"
                                 "（`INJECTED_not_in_targets.json`）⇒ 必须被检出为「清单外文件」；"
                                 "B2 = 一条**不存在**的 `--extra-target` ⇒ 必须 `missing: true` **且 exit 5**"),
           "detected": detected,
           "B1_unlisted_file_detected": {"ok": b1, "audit": audit},
           "G1_green_witness_listed_not_flagged": {
               "ok": g1, "why": "已列进清单的文件若也被报清单外 ⇒ 检测器是「一律报」的平凡真，等于没有牙"},
           "B2_missing_gives_exit_5": {"ok": b2, **b2_detail},
           "why_it_matters": ("裁定 93.8：审清单的闸必须先证明**自己的识别模式覆盖对象空间的全部形态**。"
                             "抓不到注入的坏形态 ⇒ 本审计器按 `not_measured` 登记、**不得报绿**"
                             "（缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`）"),
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
           "loadavg": list(os.getloadavg())}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "runs/infra/e_mainline_calib_20260929"
                                         "/E_IDENTITY_TABLE_20260930_0330.json"))
    ap.add_argument("--force", action="store_true", help="目标已存在时允许重写，但**先把旧件移进 before_images/**")
    ap.add_argument("--extra-target", action="append", default=[],
                    help="临时追加一条目标（相对仓库根）。**只给对照探针用**（B2 臂要逼出一条 missing）")
    ap.add_argument("--scope", action="append", default=[],
                    help="显式声明「完整性范围」目录；声明后本表会报「存在但未列入」的文件。"
                         "**不声明 ⇒ 该维记 `not_applicable_this_artifact`，不写 0**（裁定 71 / 88.3-1）")
    ap.add_argument("--probe-out", default=None,
                    help="跑裁定 93.8 的对照探针并把产物落到这个路径（`pattern_coverage_probe`）")
    ap.add_argument("--no-probe", action="store_true", help="跳过对照探针（**只**给探针的子进程臂用，防递归）")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        if not args.force:
            print(json.dumps({"ok": False, "exit": 3,
                              "error": f"拒绝覆写已存在的身份表：{out}（换一个 --out 名字，或 --force 且自动留前像）"},
                             ensure_ascii=False))
            return 3
        bdir = out.parent / "before_images"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, bdir / f"{out.name}.before{time.strftime('%Y%m%d_%H%M%S')}")

    targets = list(TARGETS) + [(x, "**由 `--extra-target` 临时追加**（对照探针的 B2 臂用它逼出一条 missing）",
                                "probe_only（不得在散文里引用）") for x in args.extra_target]
    rows, missing = {}, []
    for rel, why, citable in targets:
        p = REPO / rel
        if not p.is_file():
            missing.append(rel)
            rows[rel] = {"missing": True, "why_it_matters": why, "citable_as": citable}
            continue
        b = p.read_bytes()
        st = p.stat()
        rows[rel] = {
            "missing": False,
            "bytes": len(b),
            "n_lines": b.count(b"\n"),                       # wc -l 口径
            "n_lines_splitlines": len(b.splitlines()),
            "ends_with_newline": b.endswith(b"\n"),
            "sha256_12": sha_of(p, "sha256"),
            "sha1_12": sha_of(p, "sha1"),
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S %Z", time.localtime(st.st_mtime)),
            "why_it_matters": why,
            "citable_as": citable,
        }

    table = {
        "artifact": str(out),
        "agent": "E",
        "purpose": ("散文可核身份表：D 的裁定 89.7 新规则 "
                    "`prose_identity_must_be_verifiable_against_a_saved_artifact` 的落地件。"
                    "**散文里引用的 sha 必须与本表相等**；本表没有的路径，散文只引路径、不引 sha"),
        "citation_algo": "sha256[:12]",
        "citation_algo_why": ("本仓口径 = `hashlib.sha256(...).hexdigest()[:12]`"
                              "（`scripts/e_mainline_render_calib.py:116/139/168` 与 D 的 §D88 抬头同口径）。"
                              "`sha1_12` 一并给出，**只为让「算法错配」一眼可见**，不得被引用"),
        "line_count_convention": "n_lines = 换行符个数（= `wc -l`），与散文里的「N ln」一致",
        "stale_by_construction": (
            "**三条必然过期的行，引用方必须重算，不得采信本表**："
            "① 本表自己（`rows` 在写盘前采集，与 MANIFEST 的 `self_sha_caveat` 同理）；"
            "② 两个 `MANIFEST.json`（它们是**可重生成件**，本表生成之后还会再重生成一次以登记本表）；"
            "③ `daily_report.md`（多写者、append-only，**身份串保质期是分钟级** —— 裁定 88.6）。"
            "**其余各行是终值**：本表在所有脚本/文书改动落盘之后才生成"),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator": {"file": "scripts/e_write_identity_table.py",
                      "sha256_12": sha_of(Path(__file__).resolve(), "sha256")},
        "loadavg": list(os.getloadavg()),
        "n_targets": len(targets),
        "n_present": len(targets) - len(missing),
        "n_missing": len(missing),
        "missing": missing,
        "unlisted_audit": unlisted_in_scope([REPO / s for s in args.scope], set(rows.keys())),
        "files": rows,
    }
    if args.probe_out and not args.no_probe:
        table["pattern_coverage_probe"] = run_pattern_coverage_probe(
            Path(args.probe_out), Path(__file__).resolve())
    elif not args.no_probe:
        # 裁定 93.8：缺探针 ⇒ 该闸按 not_measured 登记、**不得报绿**
        table["pattern_coverage_probe"] = {
            "injected_bad_form": None, "detected": None, "verdict": "not_measured",
            "why": "本次运行未给 `--probe-out` ⇒ 对照探针**没跑**。按裁定 93.8 记 `not_measured`，不得报绿"}
    if not rows:
        print(json.dumps({"ok": False, "exit": 4, "error": "空清单 ⇒ 不生成（裁定 88.3-2）"}, ensure_ascii=False))
        return 4
    out.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    rc = 5 if missing else 0
    print(json.dumps({"ok": not missing, "exit": rc, "artifact": str(out),
                      "n_targets": len(targets), "n_present": len(targets) - len(missing),
                      "n_missing": len(missing), "missing": missing,
                      "unlisted_audit_verdict": table["unlisted_audit"].get("verdict"),
                      "n_unlisted": table["unlisted_audit"].get("n_unlisted"),
                      "pattern_coverage_probe_detected": (table.get("pattern_coverage_probe") or {}).get("detected"),
                      "sha256_12": sha_of(out, "sha256"),
                      "n_lines": out.read_bytes().count(b"\n")}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
