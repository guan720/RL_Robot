# 证据快照入库摘要（2026-09-30 · T-E-12 · 裁定 94.9-6）

> 生成器 `scripts/e_evidence_snapshot.py`（557 ln `d91c566258f3`）· 生成时刻 **2026-09-30T13:09:54 CST** · 快照本体 `runs/infra/e_evidence_snapshot_20260930/EVIDENCE_SNAPSHOT_v2.json`（**只在 NFS，不入库**）
> **本文件是那份快照的入库摘要**：`runs/` 被 `.gitignore:12` 排除 ⇒ 快照本体进不了 git，所以把**身份与判词**摘到这里让它随 commit 走。**字节本身仍只在 NFS**（异地副本需用户给 remote，§94.10 用户需 ①）。

## 0.0 本版取代了谁（裁定 92.2 的形状：另出一份、原字节保留）

- 取代 **`runs/infra/e_evidence_snapshot_20260930/EVIDENCE_SNAPSHOT.json`**（5597 ln `e9fe197352d2`，190035 B）；上一版**原字节保留未动**。
- 为什么出这一版：裁定 96.3 批准 F 的白名单建议（PROGRESS_LEDGER.json / TRIGGER_REGISTRY.json）⇒ 交 E 落地；E 另自决补两件自己的 Ⅰ 类新证据（CARD_BUSY_FIX_VERDICT.json = 裁定 96.1-③ 的修法判词 · *.SIDECAR.json = T-E-11 v1 的旁证更正件）。v1 原字节保留、不改一个字节。总读量仍受 ≤4 GiB 硬约束。

## 0. 一句话

白名单 **34** 条 spec ⇒ 命中 **226** 件，其中 **226** 件已 hash（读量 **543.89 MiB**，= 4 GiB 预算的 **13.2786%**）；超 200 MiB 的 **0** 件按 `not_hashed_oversize` 登记；预算耗尽 **0** 件。裁定 93.8 的对照探针 `detected = true`。**判词：`PASS`**（exit 0）。

## 1. 已 hash 的关键证据（`sha256[:12]` + 字节 + 判词 + `as_of`）

| 线 | 路径 | `n_bytes` | `sha256[:12]` | `verdict` | `verdict` 取自 | `as_of`(mtime) |
|---|---|---|---|---|---|---|
| A2 | `runs/vla/a2_egl_latency_20260929/latency_mainline_egl_gpu.json` | 11970 | `748e371be374` | `null`（not_present_in_artifact） | `None` | 2026-09-29T22:16:58 CST |
| A2 | `runs/vla/a2_egl_latency_20260929/latency_mainline_egl_gpu_pi05.json` | 31133 | `34b94b33b6a5` | `null`（not_present_in_artifact） | `None` | 2026-09-29T22:38:17 CST |
| A2 | `runs/vla/a2_egl_latency_20260929/selftest.json` | 18208 | `c829921adc4a` | `null`（not_present_in_artifact） | `None` | 2026-09-30T10:58:59 CST |
| B2 | `runs/vla/b2_env_admission_20260930/B2_IDENTITY_TABLE_20260930_0603.json` | 27582 | `22c93092e149` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:17:49 CST |
| B2 | `runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json` | 4473151 | `e319754dd030` | `null`（not_present_in_artifact） | `None` | 2026-09-30T03:21:03 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40/manifest.json` | 59176 | `e251dc6e07c7` | `PASS` | `verdict` | 2026-09-30T05:52:58 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` | 1332184 | `a84a26079550` | `null`（not_a_json_artifact） | `None` | 2026-09-30T05:52:57 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40_conflictclosure_sha_check/manifest.json` | 59138 | `8eb0efaa5486` | `PASS` | `verdict` | 2026-09-30T05:52:13 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40_conflictclosure_sha_check/states_14d.npz` | 1332184 | `a84a26079550` | `null`（not_a_json_artifact） | `None` | 2026-09-30T05:52:10 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40_dualrun_sha_check/manifest.json` | 56237 | `ffc1137d01e2` | `PASS` | `verdict` | 2026-09-30T03:07:36 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40_dualrun_sha_check/states_14d.npz` | 1332184 | `a84a26079550` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:07:34 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40_postaddendum_sha_check/manifest.json` | 56311 | `49508306cc32` | `PASS` | `verdict` | 2026-09-30T03:23:48 CST |
| B2 | `runs/vla/b2_states_14d_20260930/formal40_postaddendum_sha_check/states_14d.npz` | 1332184 | `a84a26079550` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:23:45 CST |
| B2 | `runs/vla/b2_states_14d_20260930/pilot5/manifest.json` | 53865 | `7d2dc2adf53c` | `PASS` | `verdict` | 2026-09-30T03:21:24 CST |
| B2 | `runs/vla/b2_states_14d_20260930/pilot5/manifest_addendum_ruling_88_5.json` | 1335 | `db6b1235a731` | `null`（not_present_in_artifact） | `None` | 2026-09-30T03:21:24 CST |
| B2 | `runs/vla/b2_states_14d_20260930/pilot5/states_14d.npz` | 333664 | `5c4710426db2` | `null`（not_a_json_artifact） | `None` | 2026-09-30T01:08:09 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_003054/gate_verdict.json` | 36850 | `12a964314803` | `RED` | `verdict` | 2026-09-30T00:30:58 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_003158/gate_verdict.json` | 37235 | `0926a1cbdee2` | `RED` | `verdict` | 2026-09-30T00:32:02 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_003324/gate_verdict.json` | 37235 | `c4d1479c832e` | `RED` | `verdict` | 2026-09-30T00:33:29 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_003414/gate_verdict.json` | 38420 | `4b7b535e634f` | `PASS` | `verdict` | 2026-09-30T00:34:19 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_003745/gate_verdict.json` | 38420 | `40c08b9bed4c` | `PASS` | `verdict` | 2026-09-30T00:37:53 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_004116/gate_verdict.json` | 50900 | `9a55f95dd191` | `RED` | `verdict` | 2026-09-30T00:41:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_010545/gate_verdict.json` | 79552 | `b37b62178a8d` | `RED` | `verdict` | 2026-09-30T01:05:52 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_010948/gate_verdict.json` | 85051 | `4443e4aea7b8` | `PASS` | `verdict` | 2026-09-30T01:09:57 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_024113/gate_verdict.json` | 41561 | `0dc648825872` | `RED` | `verdict` | 2026-09-30T02:41:19 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_024246/gate_verdict.json` | 41558 | `446cb1d891f2` | `RED` | `verdict` | 2026-09-30T02:42:50 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_024312/gate_verdict.json` | 10287134 | `6686e785283c` | `RED` | `verdict` | 2026-09-30T02:43:34 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_025846/gate_verdict.json` | 40467 | `def3ea7d6fec` | `RED` | `verdict` | 2026-09-30T02:58:52 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_064005/gate_verdict.json` | 62006 | `ba87643be991` | `RED` | `verdict` | 2026-09-30T06:40:15 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_064428/gate_verdict.json` | 63414 | `c0bf55787e64` | `RED` | `verdict` | 2026-09-30T06:44:34 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_065527/gate_verdict.json` | 69385764 | `38ab89207b30` | `RED` | `verdict` | 2026-09-30T06:56:52 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_065915/gate_verdict.json` | 69386190 | `6efec0589bf6` | `PASS` | `verdict` | 2026-09-30T07:00:36 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_070355/gate_verdict.json` | 69389080 | `879ba22ec9e2` | `PASS` | `verdict` | 2026-09-30T07:05:16 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_071824/gate_verdict.json` | 69440525 | `f521b77a58fe` | `PASS` | `verdict` | 2026-09-30T07:19:54 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_073852/gate_verdict.json` | 69440530 | `ae4e16c33743` | `PASS` | `verdict` | 2026-09-30T07:40:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_113655/gate_verdict.json` | 63727 | `746b4114ac38` | `RED` | `verdict` | 2026-09-30T11:37:14 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_124834/gate_verdict.json` | 76915 | `bb308def93fe` | `RED` | `verdict` | 2026-09-30T12:48:54 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_125204/gate_verdict.json` | 76853 | `dd188842a98c` | `RED` | `verdict` | 2026-09-30T12:52:24 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_125352/gate_verdict.json` | 94847366 | `24da8c3bb86e` | `RED` | `verdict` | 2026-09-30T12:55:43 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_125721/gate_verdict.json` | 94852438 | `fbf80622259f` | `PASS` | `verdict` | 2026-09-30T13:04:47 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/mainline_status.json` | 198907 | `fc3f049753bf` | `built_from_npz_authority_interface` | `status` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/matrix.json` | 3295794 | `c3f3260e5cf1` | `RED` | `verdict` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/mutation_no_widen_post_identity_center_fix/mainline_status.json` | 936 | `0734c33c6b14` | `waiting_for_s1_pilot_5` | `status` | 2026-09-29T23:42:54 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/mutation_no_widen_post_identity_center_fix/matrix.json` | 86687 | `f11240bfca1c` | `RED` | `verdict` | 2026-09-29T23:42:54 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/probe_monotonicity_20260930/ADDENDUM_ruling_94_6_1_wording_correction.json` | 7118 | `39b8ed7889cc` | `null`（not_present_in_artifact） | `None` | 2026-09-30T12:55:07 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/probe_monotonicity_20260930/verdict.json` | 53305 | `388f6c4edb16` | `PASS_preregistered_checkpoints` | `overall.verdict` | 2026-09-30T11:12:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.02__crosspolicy_stress.json` | 20225 | `75b4ccbcb6b7` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.02__holdphase.json` | 16790 | `19ca3a5a5e58` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.02__randomphase.json` | 20148 | `94d880e3f0c4` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.05__crosspolicy_stress.json` | 20246 | `b7151bed5d2a` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.05__holdphase.json` | 16807 | `dc7ab8240407` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.05__randomphase.json` | 20169 | `a8f5ccd081e6` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F2_noise_scale_multiple_2.0__crosspolicy_stress.json` | 20298 | `53a53e9f039e` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F2_noise_scale_multiple_2.0__holdphase.json` | 16915 | `b60de4d32e5d` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F2_noise_scale_multiple_2.0__randomphase.json` | 20221 | `940d2e4d2671` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F2_noise_scale_multiple_4.0__crosspolicy_stress.json` | 20296 | `1361c2fbb132` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F2_noise_scale_multiple_4.0__holdphase.json` | 16917 | `5dfc616c726b` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__identity_with_explicit_scale__F2_noise_scale_multiple_4.0__randomphase.json` | 20219 | `82e6ceb4a377` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.02__crosspolicy_stress.json` | 19701 | `1c4496b3aafd` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.02__holdphase.json` | 16195 | `c36969880183` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.02__randomphase.json` | 19624 | `7226e14f0572` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__crosspolicy_stress.json` | 19722 | `dbfb7df2bbb5` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__holdphase.json` | 16171 | `9bbf43eb6166` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__randomphase.json` | 19645 | `3ec957943b04` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F2_noise_scale_multiple_2.0__crosspolicy_stress.json` | 19774 | `14c84e9c8099` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F2_noise_scale_multiple_2.0__holdphase.json` | 16386 | `76d95ed2194c` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F2_noise_scale_multiple_2.0__randomphase.json` | 19697 | `d28b0aa8148f` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F2_noise_scale_multiple_4.0__crosspolicy_stress.json` | 19762 | `758ee3ae84aa` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F2_noise_scale_multiple_4.0__holdphase.json` | 16388 | `8017e43bd89f` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/env_derived_diagnostic__quantiles_with_scale_floor__F2_noise_scale_multiple_4.0__randomphase.json` | 19685 | `8c1829a6a2e8` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F1_physical_range_fraction_0.02__bc_admission_mustred.json` | 41166 | `8ff97cdc7c82` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F1_physical_range_fraction_0.02__lerobot_crosscheck.json` | 40952 | `22a740694efe` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F1_physical_range_fraction_0.02__mainline_path_check.json` | 24937 | `44e1096a921b` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F1_physical_range_fraction_0.05__bc_admission_mustred.json` | 41196 | `8372716972ac` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F1_physical_range_fraction_0.05__lerobot_crosscheck.json` | 40982 | `8d93ae03b9fa` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:21 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F1_physical_range_fraction_0.05__mainline_path_check.json` | 24967 | `dcdfd6d02237` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F2_noise_scale_multiple_2.0__bc_admission_mustred.json` | 41287 | `c351ab749fd0` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F2_noise_scale_multiple_2.0__lerobot_crosscheck.json` | 41073 | `b6eea4fff61f` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F2_noise_scale_multiple_2.0__mainline_path_check.json` | 25058 | `bf95585cee58` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F2_noise_scale_multiple_4.0__bc_admission_mustred.json` | 41282 | `1e6abbca6231` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F2_noise_scale_multiple_4.0__lerobot_crosscheck.json` | 41068 | `e5f04e6488af` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__identity_with_explicit_scale__F2_noise_scale_multiple_4.0__mainline_path_check.json` | 25053 | `b5a1a4fa6c94` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.02__bc_admission_mustred.json` | 40759 | `acdecc922c00` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.02__lerobot_crosscheck.json` | 40545 | `be73e6142e4f` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:21 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.02__mainline_path_check.json` | 24530 | `dc78f7f246b7` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__bc_admission_mustred.json` | 40787 | `06bb0dafb479` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__lerobot_crosscheck.json` | 40573 | `e8c2ba6178c2` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:21 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__mainline_path_check.json` | 24558 | `b8d825dfaa6b` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F2_noise_scale_multiple_2.0__bc_admission_mustred.json` | 40890 | `8523bbbd7933` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F2_noise_scale_multiple_2.0__lerobot_crosscheck.json` | 40676 | `1651d926aacf` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:21 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F2_noise_scale_multiple_2.0__mainline_path_check.json` | 24661 | `eac8f3f588c0` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F2_noise_scale_multiple_4.0__bc_admission_mustred.json` | 40885 | `897dca4f48a9` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:22 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F2_noise_scale_multiple_4.0__lerobot_crosscheck.json` | 40671 | `bf312c8f3841` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:21 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F2_noise_scale_multiple_4.0__mainline_path_check.json` | 24656 | `bff413580814` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:23 CST |
| C2 | `runs/vla/c2_norm_contract_20260929/stats/yam_abc130k__quantiles_with_scale_floor__F1_physical_range_fraction_0.05.json` | 9283 | `b8276b797d55` | `null`（not_present_in_artifact） | `None` | 2026-09-30T06:04:20 CST |
| D | `rl_harness_supervision/README.md` | 419 | `d196d5a19b3e` | `null`（not_a_json_artifact） | `None` | 2026-09-24T14:27:58 CST |
| D | `rl_harness_supervision/d_context_checkpoint_20260929_2130.md` | 227613 | `8013accb49d1` | `null`（not_a_json_artifact） | `None` | 2026-09-30T04:12:01 CST |
| D | `rl_harness_supervision/d_context_checkpoint_20260930_1010.md` | 11863 | `3993ce966d46` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:24:08 CST |
| D | `rl_harness_supervision/d_context_checkpoint_20260930_1205.md` | 12746 | `0a2d0ace85d4` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:24:08 CST |
| D | `rl_harness_supervision/d_freeze_abc_20260929.md` | 11514 | `0304adb1bdb4` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:58:09 CST |
| D | `rl_harness_supervision/d_handoff_to_a2_20260929.md` | 134743 | `8e5197bb0b77` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:53:38 CST |
| D | `rl_harness_supervision/d_handoff_to_a2_20260930.md` | 17373 | `8b08e087763a` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:18:42 CST |
| D | `rl_harness_supervision/d_handoff_to_a_20260929.md` | 33154 | `c9e4fb46ce7d` | `null`（not_a_json_artifact） | `None` | 2026-09-29T15:37:43 CST |
| D | `rl_harness_supervision/d_handoff_to_b2_20260929.md` | 121731 | `b5a82c6085c8` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:52:46 CST |
| D | `rl_harness_supervision/d_handoff_to_b2_20260930.md` | 17777 | `411afbed81c3` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:20:26 CST |
| D | `rl_harness_supervision/d_handoff_to_b_20260929.md` | 26097 | `034a2098d134` | `null`（not_a_json_artifact） | `None` | 2026-09-29T15:20:46 CST |
| D | `rl_harness_supervision/d_handoff_to_c2_20260929.md` | 132622 | `da9730cfa15c` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:51:42 CST |
| D | `rl_harness_supervision/d_handoff_to_c2_20260930.md` | 20469 | `4fb9e964d4e8` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:18:42 CST |
| D | `rl_harness_supervision/d_handoff_to_c_20260929.md` | 37161 | `e1f5f22a8bbe` | `null`（not_a_json_artifact） | `None` | 2026-09-29T15:37:04 CST |
| D | `rl_harness_supervision/d_handoff_to_e_20260929.md` | 108843 | `a3de25d90ca5` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:54:36 CST |
| D | `rl_harness_supervision/d_handoff_to_e_20260930.md` | 15341 | `4599436de7d5` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:20:26 CST |
| D | `rl_harness_supervision/d_handoff_to_f_20260930.md` | 9504 | `b0e5d2c8cc15` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:22:01 CST |
| D | `rl_harness_supervision/d_simchain_e2emin_20260929.md` | 53140 | `87de84c1bd16` | `null`（not_a_json_artifact） | `None` | 2026-09-29T22:07:26 CST |
| D | `rl_harness_supervision/supervisor_handoff_20260924.md` | 2613 | `5dd173314183` | `null`（not_a_json_artifact） | `None` | 2026-09-24T15:07:52 CST |
| D | `rl_harness_supervision/supervisor_memo_20260928.md` | 75000 | `c4a7b5234dd1` | `null`（not_a_json_artifact） | `None` | 2026-09-29T10:53:10 CST |
| D | `rl_harness_supervision/supervisor_memo_20260929.md` | 305821 | `84f38fde4813` | `null`（not_a_json_artifact） | `None` | 2026-09-29T23:24:19 CST |
| D | `rl_harness_supervision/supervisor_review_20260924.md` | 5687 | `7000eb5aada5` | `null`（not_a_json_artifact） | `None` | 2026-09-24T14:27:14 CST |
| D | `rl_harness_supervision/supervisor_review_initial_20260924.md` | 4078 | `19e7bc9436c7` | `null`（not_a_json_artifact） | `None` | 2026-09-24T14:19:05 CST |
| D | `runs/vla/d_ruling_round_20260930_1010/D_IDENTITY_TABLE_20260930_1045.json` | 10256 | `f3abc05b1c30` | `null`（not_present_in_artifact） | `None` | 2026-09-30T10:53:25 CST |
| D | `work/decisions/decisions_20260928.md` | 14094 | `32851c0d4565` | `null`（not_a_json_artifact） | `None` | 2026-09-28T21:25:34 CST |
| D | `work/decisions/decisions_20260928_A.md` | 14992 | `c72fa0798131` | `null`（not_a_json_artifact） | `None` | 2026-09-28T23:00:36 CST |
| D | `work/decisions/decisions_20260928_B.md` | 112526 | `c779e205e4b3` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:35:30 CST |
| D | `work/decisions/decisions_20260928_C.md` | 12902 | `dc9792bb0e64` | `null`（not_a_json_artifact） | `None` | 2026-09-28T21:47:42 CST |
| D | `work/decisions/decisions_20260929.md` | 647920 | `fb62c9df695c` | `null`（not_a_json_artifact） | `None` | 2026-09-30T13:01:15 CST |
| D | `work/decisions/decisions_20260929_A.md` | 55802 | `5d1594710954` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:42:09 CST |
| D | `work/decisions/decisions_20260929_C.md` | 78531 | `2b0a0bc637b8` | `null`（not_a_json_artifact） | `None` | 2026-09-29T17:49:25 CST |
| D | `work/project_parameters.json` | 529156 | `63bb46f2f303` | `null`（not_present_in_artifact） | `None` | 2026-09-30T12:14:27 CST |
| E | `runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json` | 57776 | `c7457467514f` | `PASS` | `verdict` | 2026-09-30T12:51:09 CST |
| E | `runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.ANNOTATIONS.json` | 18094 | `9a48b11db93e` | `PASS` | `verdict` | 2026-09-30T11:49:57 CST |
| E | `runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json` | 24219 | `56b81f389712` | `COLDSTART_VERIFIED` | `delivery_status` | 2026-09-30T03:02:38 CST |
| E | `runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v4.json` | 45885 | `4011ae621f61` | `null`（not_present_in_artifact） | `None` | 2026-09-30T11:21:56 CST |
| E | `runs/infra/e_mainline_calib_20260929/E_IDENTITY_TABLE_20260930_0330.json` | 18191 | `b63da7c16d3c` | `null`（not_present_in_artifact） | `None` | 2026-09-30T03:55:37 CST |
| E | `runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_REPS5.json` | 44662 | `767a2d984a5b` | `null`（not_present_in_artifact） | `None` | 2026-09-30T00:49:50 CST |
| E | `runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json` | 27548 | `6a67e3796695` | `measured` | `measurement_status` | 2026-09-30T03:02:54 CST |
| E | `runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM_TEAM480x640_OSMESA_REPS5.json` | 25843 | `9e0e1469ecb6` | `null`（not_present_in_artifact） | `None` | 2026-09-30T02:12:13 CST |
| E | `runs/infra/e_mainline_calib_20260929/summary_20260929_220400.json` | 76849 | `92968f4d94af` | `null`（not_present_in_artifact） | `None` | 2026-09-29T22:09:41 CST |
| E | `runs/infra/e_mainline_calib_20260929/summary_20260929_221443.json` | 79013 | `bf2b82329566` | `null`（not_present_in_artifact） | `None` | 2026-09-29T22:20:19 CST |
| E | `runs/infra/e_mainline_calib_20260929/summary_20260929_222019.json` | 23988 | `2861993f89fd` | `null`（not_present_in_artifact） | `None` | 2026-09-29T22:21:24 CST |
| E | `runs/infra/e_mainline_calib_20260929/summary_20260929_234814.json` | 84197 | `32d15f0da3b3` | `null`（not_present_in_artifact） | `None` | 2026-09-29T23:54:08 CST |
| E | `runs/infra/e_mainline_calib_20260929/summary_20260929_235835.json` | 14313 | `1fdf82ef5c4e` | `null`（not_present_in_artifact） | `None` | 2026-09-29T23:59:55 CST |
| E | `runs/infra/e_restart_readiness_20260930/LINK_AUDIT_SELFCHECK_prefixstate_after.json` | 16370 | `d2b92aab58a4` | `PASS` | `verdict` | 2026-09-30T11:22:35 CST |
| E | `runs/infra/e_restart_readiness_20260930/LINK_AUDIT_SELFCHECK_prefixstate_before.json` | 16382 | `f8550111f830` | `PASS` | `verdict` | 2026-09-30T11:17:50 CST |
| E | `runs/infra/e_restart_readiness_20260930/RESTART_READINESS.CARD_BUSY_FIX_96_1_3.SIDECAR.json` | 6041 | `d7b99b6d0498` | `CORRECTION_LANDED` | `verdict` | 2026-09-30T12:56:28 CST |
| E | `runs/infra/e_restart_readiness_20260930/RESTART_READINESS.json` | 73860 | `4587672f186f` | `READY_WITH_NOT_MEASURED` | `verdict` | 2026-09-30T11:49:05 CST |
| E | `runs/infra/e_restart_readiness_20260930/V3_TO_V4_DELTA.json` | 3728 | `c8e2b1cc0878` | `PASS` | `verdict` | 2026-09-30T11:24:24 CST |
| F | `runs/vla/f_oversight_20260930/PROGRESS_LEDGER.json` | 14965 | `3cd0b860a784` | `ok` | `verdict` | 2026-09-30T12:26:04 CST |
| F | `runs/vla/f_oversight_20260930/TRIGGER_REGISTRY.json` | 28474 | `46a25c0ecc10` | `measured` | `measurement_status` | 2026-09-30T12:26:04 CST |
| 多写者 | `daily_report.md` | 1161863 | `3a4b53f88429` | `null`（not_a_json_artifact） | `None` | 2026-09-30T13:02:34 CST |
| 多写者 | `docs/ROADMAP.md` | 20146 | `9ebd2df1c419` | `null`（not_a_json_artifact） | `None` | 2026-09-23T14:36:04 CST |
| 多写者 | `docs/a2_pi05_sim_readiness_20260929.md` | 154821 | `e090cfc5858e` | `null`（not_a_json_artifact） | `None` | 2026-09-30T01:55:10 CST |
| 多写者 | `docs/a2_s4_vla_runtime_interface_20260929.md` | 81081 | `490411105046` | `null`（not_a_json_artifact） | `None` | 2026-09-30T01:08:18 CST |
| 多写者 | `docs/a_bimodal_divergence_preregistration_20260928.md` | 50179 | `71c2b9454049` | `null`（not_a_json_artifact） | `None` | 2026-09-29T12:36:59 CST |
| 多写者 | `docs/a_env_rebuild_acceptance_20260929.md` | 52334 | `51d999381995` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:43:37 CST |
| 多写者 | `docs/a_handoff_to_b_anchor_shift_20260929.md` | 9863 | `c9a29f6af78c` | `null`（not_a_json_artifact） | `None` | 2026-09-29T15:10:56 CST |
| 多写者 | `docs/a_handoff_to_b_gate_vocabulary_20260928.md` | 10601 | `fa95f97bcb81` | `null`（not_a_json_artifact） | `None` | 2026-09-28T22:07:36 CST |
| 多写者 | `docs/a_handoff_to_b_pending_bucket_tristate_20260929.md` | 7530 | `dd6cf44a2c30` | `null`（not_a_json_artifact） | `None` | 2026-09-29T14:44:51 CST |
| 多写者 | `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md` | 10352 | `0b23be25aadc` | `null`（not_a_json_artifact） | `None` | 2026-09-28T22:56:52 CST |
| 多写者 | `docs/a_handoff_to_b_t17_train_side_verified_20260929.md` | 10086 | `aca4275a8e0d` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:30:03 CST |
| 多写者 | `docs/a_handoff_to_d_20260929.md` | 22510 | `6e3e44da6e72` | `null`（not_a_json_artifact） | `None` | 2026-09-29T15:53:35 CST |
| 多写者 | `docs/act_chunk_replay_report_20260924.md` | 2108 | `ff61e8631f0b` | `null`（not_a_json_artifact） | `None` | 2026-09-24T16:18:12 CST |
| 多写者 | `docs/act_imitation_history_ablation_20260924.md` | 2394 | `614630a2faf1` | `null`（not_a_json_artifact） | `None` | 2026-09-24T16:59:25 CST |
| 多写者 | `docs/act_imitation_report_20260924.md` | 1999 | `40aa5c42aeff` | `null`（not_a_json_artifact） | `None` | 2026-09-24T16:37:27 CST |
| 多写者 | `docs/agent_a_handoff_20260924.md` | 3047 | `7cb40e4f56d4` | `null`（not_a_json_artifact） | `None` | 2026-09-24T15:11:03 CST |
| 多写者 | `docs/b2_bidirectional_demo_and_gates_20260929.md` | 45231 | `622a072d01e9` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:40:25 CST |
| 多写者 | `docs/b2_gpu_window_incident_and_rr_20260930.md` | 14437 | `1501958afccc` | `null`（not_a_json_artifact） | `None` | 2026-09-30T00:37:46 CST |
| 多写者 | `docs/b2_handoff_to_c2_formal40_20260930.md` | 18030 | `59a9633e408f` | `null`（not_a_json_artifact） | `None` | 2026-09-30T06:06:13 CST |
| 多写者 | `docs/b_agent_review_20260928.md` | 71902 | `6d37c2c131e8` | `null`（not_a_json_artifact） | `None` | 2026-09-28T22:44:09 CST |
| 多写者 | `docs/b_controlled_success_v1_20260928.md` | 72960 | `c7fadabe8e3c` | `null`（not_a_json_artifact） | `None` | 2026-09-29T11:42:20 CST |
| 多写者 | `docs/b_gate_threshold_sensitivity_20260928.md` | 12312 | `2024452ddcc6` | `null`（not_a_json_artifact） | `None` | 2026-09-28T19:07:24 CST |
| 多写者 | `docs/b_handoff_to_a_20260928.md` | 33039 | `33bff799364d` | `null`（not_a_json_artifact） | `None` | 2026-09-28T22:45:42 CST |
| 多写者 | `docs/b_handoff_to_a_20260929.md` | 24513 | `2384d6701597` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:38:39 CST |
| 多写者 | `docs/b_handoff_to_c_20260928.md` | 8346 | `ff237b4f623b` | `null`（not_a_json_artifact） | `None` | 2026-09-28T22:10:33 CST |
| 多写者 | `docs/b_handoff_to_c_20260929.md` | 23450 | `d6b1c9895817` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:36:36 CST |
| 多写者 | `docs/b_handoff_to_d_20260929.md` | 32303 | `ca411dcd5dd8` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:37:47 CST |
| 多写者 | `docs/b_normalization_incident_20260928.md` | 11399 | `f74a2ebed455` | `null`（not_a_json_artifact） | `None` | 2026-09-28T17:42:07 CST |
| 多写者 | `docs/b_official_arms_reclassification_20260928.md` | 12278 | `a2146e24d156` | `null`（not_a_json_artifact） | `None` | 2026-09-28T19:36:34 CST |
| 多写者 | `docs/b_reproducibility_incident_20260928.md` | 8117 | `f1e5d4023e94` | `null`（not_a_json_artifact） | `None` | 2026-09-28T17:10:15 CST |
| 多写者 | `docs/b_teacher_desaturation_prereg_20260928.md` | 19473 | `d46804081983` | `null`（not_a_json_artifact） | `None` | 2026-09-28T22:37:35 CST |
| 多写者 | `docs/b_truncation_probe_official_20260928.md` | 13934 | `11024fd75371` | `null`（not_a_json_artifact） | `None` | 2026-09-28T19:29:37 CST |
| 多写者 | `docs/baseline_gap_analysis_20260924.md` | 8345 | `3462412b05a8` | `null`（not_a_json_artifact） | `None` | 2026-09-24T14:36:18 CST |
| 多写者 | `docs/c2_gate_polarity_audit_20260929.md` | 28642 | `768d49409d76` | `null`（not_a_json_artifact） | `None` | 2026-09-29T23:37:30 CST |
| 多写者 | `docs/c2_handoff_to_d_20260929.md` | 81994 | `0c9b2563a89e` | `null`（not_a_json_artifact） | `None` | 2026-09-30T07:45:41 CST |
| 多写者 | `docs/c2_task_selfintake_20260929.md` | 26375 | `e1c99b50d45a` | `null`（not_a_json_artifact） | `None` | 2026-09-29T20:33:44 CST |
| 多写者 | `docs/c_env_manifest_and_pending_impl_20260929.md` | 60566 | `9a2edcc6b1f2` | `null`（not_a_json_artifact） | `None` | 2026-09-29T18:05:12 CST |
| 多写者 | `docs/c_golden_conformance_20260928.md` | 26875 | `f16f33bd8e8c` | `null`（not_a_json_artifact） | `None` | 2026-09-28T21:36:01 CST |
| 多写者 | `docs/c_handoff_to_b2_registry_20260929.md` | 17164 | `ed55c4c3c512` | `null`（not_a_json_artifact） | `None` | 2026-09-29T17:59:40 CST |
| 多写者 | `docs/c_handoff_to_b_t17_landed_20260929.md` | 9393 | `6b3cb6ceaeea` | `null`（not_a_json_artifact） | `None` | 2026-09-29T11:10:45 CST |
| 多写者 | `docs/c_handoff_to_d_p1_landed_20260929.md` | 8937 | `9ca242de7fbb` | `null`（not_a_json_artifact） | `None` | 2026-09-29T17:08:09 CST |
| 多写者 | `docs/c_reuse_manifest_for_a2_b2_20260929.md` | 44656 | `decb358bd8b1` | `null`（not_a_json_artifact） | `None` | 2026-09-29T18:05:56 CST |
| 多写者 | `docs/c_t17_goal_conditioning_20260929.md` | 21180 | `3894dd0d7973` | `null`（not_a_json_artifact） | `None` | 2026-09-29T11:07:32 CST |
| 多写者 | `docs/c_verdict_identity_20260928.md` | 19571 | `32e2d00b2ba4` | `null`（not_a_json_artifact） | `None` | 2026-09-28T21:45:02 CST |
| 多写者 | `docs/e_egl_feasibility_20260929.md` | 54405 | `a79b068a39cc` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:29:23 CST |
| 多写者 | `docs/e_handoff_to_d_20260929.md` | 77594 | `6e9d943091c9` | `null`（not_a_json_artifact） | `None` | 2026-09-30T03:48:53 CST |
| 多写者 | `docs/e_platform_request_graphics_capability.md` | 10277 | `0d1d2d1c2d28` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:06:38 CST |
| 多写者 | `docs/f_handoff_to_d_20260930.md` | 11070 | `ea3ca5bc430b` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:01:58 CST |
| 多写者 | `docs/f_stop_point_20260930.md` | 11982 | `35abc0c1679a` | `null`（not_a_json_artifact） | `None` | 2026-09-30T12:29:32 CST |
| 多写者 | `docs/f_task_selfintake_20260930.md` | 8033 | `650a4b3a7b32` | `null`（not_a_json_artifact） | `None` | 2026-09-30T11:59:52 CST |
| 多写者 | `docs/from_scratch_sac_handoff_20260924.md` | 1309 | `304bfdcb013b` | `null`（not_a_json_artifact） | `None` | 2026-09-24T15:59:11 CST |
| 多写者 | `docs/handoff_scripted_pickplace_defects.md` | 11035 | `fec3b09ef097` | `null`（not_a_json_artifact） | `None` | 2026-09-24T10:09:58 CST |
| 多写者 | `docs/harness_actrl_interface.md` | 2301 | `ccf771706e20` | `null`（not_a_json_artifact） | `None` | 2026-09-24T14:17:38 CST |
| 多写者 | `docs/infra-gpu-render.md` | 49788 | `ed5d4aad866e` | `null`（not_a_json_artifact） | `None` | 2026-09-30T13:08:05 CST |
| 多写者 | `docs/lead_report_and_asks_20260929.md` | 17829 | `d222e450f758` | `null`（not_a_json_artifact） | `None` | 2026-09-29T20:23:57 CST |
| 多写者 | `docs/ledger_data_bridge_20260928.md` | 52897 | `452fc82894ff` | `null`（not_a_json_artifact） | `None` | 2026-09-28T21:03:17 CST |
| 多写者 | `docs/lerobot_act_env_setup_20260928.md` | 232169 | `5dd918b9080f` | `null`（not_a_json_artifact） | `None` | 2026-09-29T14:49:18 CST |
| 多写者 | `docs/lerobot_act_migration_20260924.md` | 2734 | `5b5763c9773b` | `null`（not_a_json_artifact） | `None` | 2026-09-24T17:31:19 CST |
| 多写者 | `docs/lerobot_env_reinstall_pin_20260929.md` | 27670 | `7bd863eddc0f` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:14:10 CST |
| 多写者 | `docs/lerobot_official_act_lock_20260924.md` | 2609 | `6c3e49fa5ff8` | `null`（not_a_json_artifact） | `None` | 2026-09-24T17:43:25 CST |
| 多写者 | `docs/lerobot_official_env_manifest_20260924.md` | 2123 | `f42fdfdf1e43` | `null`（not_a_json_artifact） | `None` | 2026-09-24T18:24:31 CST |
| 多写者 | `docs/lerobot_official_overfit_blocker_20260924.md` | 2696 | `c0dee5a9213b` | `null`（not_a_json_artifact） | `None` | 2026-09-24T18:03:59 CST |
| 多写者 | `docs/notes_env.md` | 10652 | `d9ba103dc945` | `null`（not_a_json_artifact） | `None` | 2026-09-29T16:07:28 CST |
| 多写者 | `docs/notes_residual_architecture.md` | 1107 | `02aaebb642c0` | `null`（not_a_json_artifact） | `None` | 2026-09-24T14:09:41 CST |
| 多写者 | `docs/notes_roborsi.md` | 17807 | `04324738458b` | `null`（not_a_json_artifact） | `None` | 2026-09-23T14:46:43 CST |
| 多写者 | `docs/notes_stage0.md` | 8083 | `de338b89e3c9` | `null`（not_a_json_artifact） | `None` | 2026-09-22T18:48:26 CST |
| 多写者 | `docs/notes_stage1.md` | 18603 | `a72abb23ea32` | `null`（not_a_json_artifact） | `None` | 2026-09-22T19:07:35 CST |
| 多写者 | `docs/notes_stage1_internals.md` | 12714 | `b84bb0d59883` | `null`（not_a_json_artifact） | `None` | 2026-09-22T20:11:31 CST |
| 多写者 | `docs/notes_stage1_visual.md` | 9791 | `0d6cf3fdab56` | `null`（not_a_json_artifact） | `None` | 2026-09-22T20:11:31 CST |
| 多写者 | `docs/notes_stage2.md` | 48973 | `c876b9a9a429` | `null`（not_a_json_artifact） | `None` | 2026-09-23T13:43:40 CST |
| 多写者 | `docs/notes_stage3.md` | 197325 | `069efef155ca` | `null`（not_a_json_artifact） | `None` | 2026-09-24T10:08:29 CST |
| 多写者 | `docs/notes_vision.md` | 21606 | `e3d0c19c9dfd` | `null`（not_a_json_artifact） | `None` | 2026-09-24T11:35:53 CST |
| 多写者 | `docs/plan_alignment_2026-09-23.md` | 11373 | `c64aadf8b579` | `null`（not_a_json_artifact） | `None` | 2026-09-23T17:17:00 CST |
| 多写者 | `docs/research-survey-2026-09-23.md` | 32181 | `9114da796902` | `null`（not_a_json_artifact） | `None` | 2026-09-24T09:18:32 CST |
| 多写者 | `docs/residual_audit_report_20260924.md` | 3137 | `96eead5b031a` | `null`（not_a_json_artifact） | `None` | 2026-09-24T15:26:47 CST |
| 多写者 | `docs/residual_audit_status_20260924.md` | 1413 | `723c3ee852b2` | `null`（not_a_json_artifact） | `None` | 2026-09-24T15:00:57 CST |
| 多写者 | `docs/residual_three_arm_audit_20260924.md` | 4435 | `e05237102654` | `null`（not_a_json_artifact） | `None` | 2026-09-24T16:03:19 CST |
| 多写者 | `docs/roborsi-callchain.md` | 13572 | `6a81de9a2d4d` | `null`（not_a_json_artifact） | `None` | 2026-09-22T15:57:25 CST |
| 多写者 | `docs/roborsi-trial-log.md` | 14010 | `ccbf9e89255b` | `null`（not_a_json_artifact） | `None` | 2026-09-22T18:23:47 CST |

**`verdict` 覆盖率**：45 / 226 件取到判词；181 件为 `null`（**`null` 不是「绿」也不是「空判词」**，而是「这件产物里没有那批键」，`verdict_status` 区分 `not_a_json_artifact` / `not_present_in_artifact`）。

## 2. 白名单里**没命中**的 spec（如实登记，不静默丢）

| spec | 线 | 扫描范围 | 状态 |
|---|---|---|---|
| `glob:runs/vla/d_ruling_round_20260930_1100/*IDENTITY_TABLE*.json` | D | `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/runs/vla/d_ruling_round_20260930_1100` × `*IDENTITY_TABLE*.json`（as_of 2026-09-30T13:08:35 CST） | `not_found` |

## 3. 关键但**不可能 hash** 的（显式登记，不许假装覆盖）

| 路径 | 是什么 | 状态 |
|---|---|---|
| `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/hf-cache` | 权重/模型缓存（14 GiB） | `not_hashed_by_budget_or_scope`（exists=True） |
| `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01` | EGL 库前缀（339,337,693 B / 34 条目） | `not_hashed_by_budget_or_scope`（exists=True） |
| `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/runs` | 全部证据档（39.53 GiB） | `not_hashed_by_budget_or_scope`（exists=True） |
| `/workspace/mnt/sppro/yhzhang91/datasets` | 数据集（**E 永不写、永不遍历**） | `not_hashed_by_budget_or_scope`（exists=True） |

## 4. 裁定 93.8 的对照探针（审清单的闸必须自证模式覆盖）

- **注入的坏形态**：B1 = 一个存在于被扫目录、但**不匹配任何白名单模式**的文件（`README_not_whitelisted.txt`）；B2 = 一个**超 200 MiB** 的体积形状
- **`detected` = `true`**
- 绿见证 G1（符合模式的文件必须被列出，证明不是「一律判清单外」的平凡真）：`listed` （ok=True）
- B1（清单外文件）检出：`['in_whitelist/README_not_whitelisted.txt']` （ok=True）
- B2（体积闸形状）：`{"over": "not_hashed_oversize", "under": "will_hash"}` （ok=True）
- 沙箱：`runs/infra/e_evidence_snapshot_20260930/probe_sandbox_v2`（**E 自己的产物目录，不写他线 run 目录**）

## 5. 「清单外」的真实测量（不是探针）

- 扫描范围：12 个目录前缀（`cap=4000`，capped=True）
- 扫到 4000 件，其中**清单外 3898 件**
- **这是预期的**：本快照是「**最小**」快照，只收白名单。本字段的作用是让「漏了什么」可见、可核，而不是假装全覆盖（裁定 94.9-4：否定性存在主张必须带扫描范围）。

## 6. 硬约束遵守情况

- 单文件 ≤ 200 MiB：**遵守**（超限 0 件按 `not_hashed_oversize` 登记，未 hash）
- 总读量 ≤ 4 GiB：**遵守**（实读 543.89 MiB = 13.2786%）
- **没有全量 hash 39.53 GiB**、**没有 `find /`**、**没有递归 `runs/` 全树**（裁定 94.9-2）
- **本轮未上卡**（`gpu_window_used = false`）
- 三值纪律：`verdict` 取不到写 `null`，白名单空集 ⇒ exit 4

## 7. 这份摘要**不能**做什么

- **不能**用它恢复字节 —— 它只有 sha，没有内容。字节在 NFS。
- **不能**把 `verdict=null` 读成「绿」或「通过」。
- **不能**跨线搬判词：表里的 `verdict` 是**从那件产物里取出来的原值**，E 不重判、不解释、不平均（裁定 71 `caliber_transplant_ban`）。
- **不能**当作能力声明：裁定 46 的禁令不变（BC 出结果前，任何「能搬运/学会了」的表述无效）。
