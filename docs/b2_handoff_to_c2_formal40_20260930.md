# B2 → C2 交接：**formal 40 集已落地 = BC 的 stats 源，可以重算**（2026-09-30 03:2x）

**发件**：B2（数据与判据线）｜**收件**：C2｜**抄送**：D
**依据**：裁定 85.3 RR-B2-13（"formal 40 集 = BC 的 stats 源，落地后通知 C2 重算"）+ D §20.6-3（P0）
**本节身份**：本文件由 B2 新建；所有数字都是机器现算（`sha256sum | cut -c1-12` / `wc -l` / `stat`），
引用时刻写在每项后面。**B2 只读 C2 的代码**（`scripts/c2_build_norm_stats.py`），一个字节都没改。

---

## 1. 一句话

`runs/vla/b2_sim_demo_bidir_20260930/formal/` 已落地：**40 集 = 20 forward + 20 reverse**、
11035 帧、**19 道闸 `n_red=0` / `n_warn=0` / `n_unjudged=0` / `n_a=1` / `verdict=PASS` / `ok=true`**、
`contaminated_by_cotenant=false`（⇒ 墙钟数字是权威口径）、体积 0.2154 GiB。
**C2 可以重算主线 normalizer stats。**

## 2. 你的入口与命令（按裁定 85.4-2 的优先级）

```bash
/opt/conda/bin/python3 scripts/c2_build_norm_stats.py \
  --s1-lerobot runs/vla/b2_sim_demo_bidir_20260930/formal/pi05_lerobot \
  --s1-npz-crosscheck runs/vla/b2_states_14d_20260930/formal40/states_14d.npz
```

- **主线 = `--s1-lerobot`**（直读 parquet）。
- **`--s1-npz-crosscheck`** 用 B2 的 npz 做帧序/集号/方向码的逐位互核（`crosscheck_frames_vs_npz` /
  `crosscheck_episodes_vs_npz` / `crosscheck_direction_vs_npz`）。
- ⚠ **不要用 `--s1-frames`**：该入口已被**裁定 85.4-2-1 撤销**（`c2_build_norm_stats.py:738` 的
  docstring 自己写着"已被撤销，保留只为读回旧产物做互核"）。而且它对 formal npz 会**判红**：
  `auto_stats_provenance(man)` 只认 `is_pilot5` / `formal_collection_pending` 两个标志，
  B2 的 formal npz 两个都是 `false` ⇒ 落到 `unclassified_not_for_bc`（不在
  `nc.KNOWN_STATS_PROVENANCES` 里 ⇒ 你的牙 Tp4 必红）。**这是一条假红，别踩。**
  走 `--s1-lerobot` 时用的是 `auto_stats_provenance_lerobot()`，判据完全不同（见 §3）。

## 3. 你的硬闸 `auto_stats_provenance_lerobot` 需要的四项事实（B2 侧实测值）

判据在 `scripts/c2_build_norm_stats.py:622-655`（B2 只读）。要拿到 `formal40_bc_source`，需同时满足：

| 判据 | 需要 | formal 实测（03:2x 机器读 `demo_manifest.json`） |
|---|---|---|
| `man.stage` | `== "formal"` | **`formal`** |
| `lf.n_episodes` | `== n_generated_per_direction × len(directions)` | **40 == 20 × 2** |
| `man.directions` | 非空 | **`["forward","reverse"]`** |
| `man.n_generated_per_direction` | int | **20** |
| `dc.per_direction_episode_counts` | 每方向都 `== n_generated_per_direction` | 你自己从 parquet 数；B2 侧 `episodes[].direction` 机器计数 = **forward 20 / reverse 20**，seeds 两方向都是 `2000…2019` |

⇒ 预期你的 `stats_provenance = formal40_bc_source`（`nc.BC_ADMISSIBLE_PROVENANCES` 里唯一那个档名）。
**若你数出来不是 20/20，请立刻报 D 并停下** —— 那说明 B2 的 manifest 与 parquet 不一致，
是 B2 的缺陷，不是你的判据太严。

## 4. `demo_manifest.json` 的 sha 时间线（**三段，都是披露式追加写，只增不改**）

| 时点 | sha256[:12] | bytes | 谁改的 / 加了什么 |
|---|---|---|---|
| 02:57:21 | `0c057e22690f` | 3577346 | 生成器落地原字节（19 道闸的结果就在这里面） |
| 03:06:38 | `561ab330fea7` | 4466471 | **B2 导出器**按契约 §17-4 回写：加 `states_14d_npz`（npz 的 sha256-12 + `as_of`），before/after 全登记在 `states_14d_npz.demo_manifest_patch` |
| 03:21:03 | **`e319754dd030`** | 4473151 | **B2 追加写**（`scripts/b2_patch_manifest_addendum.py`，**234 ln `3550c1e13cb1`**）：加 `renderer_arm_compensating_control`（裁定 88.5-1 的三字段）+ `naming_note`（D §20.6-4） |

> **一处引用更正（B2 自报，裁定 78.11 `citation_sha_as_of_discipline`）**：本节首版把追加脚本写成
> `232 ln bd9c5f291f67` —— 那是**改前**的身份（写完初版后又把输出缩进从 `indent=1` 改成 `indent=2`
> 以匹配盘上形态，然后才真正执行追加）。**实际执行追加写的是 `234 ln 3550c1e13cb1`**，已按现值更正。
> 教训与 D 的裁定 78.11 同型：引用自己写入面内、仍在编辑的文件时，sha 必须在**落笔时刻重读**。

- **你现在读到的是 `e319754dd030`。** 若你的产物里要记 demo_manifest 的 sha，请记这个值 + `as_of 03:21:03`。
- **两次追加写都有机器断言**：写完后重新读盘、逐键深比对 ⇒ `preexisting_keys_changed=[]`、
  `preexisting_keys_dropped=[]`、`keys_added` 恰好等于声明的那几个；并且
  `pi05_lerobot / team_form / sidecar` 三个子树的 `(文件数, 字节总数)` 进出**完全一致**
  （`pi05_lerobot` 6 files / 209691674 B；`team_form` 161 / 19025092；`sidecar` 40 / 2589929）。
  before 影像留在 `formal/overwrite_guard/demo_manifest.json.before_addendum_20260930_032103`。
- **⇒ `stage` / `directions` / `n_generated_per_direction` / `gates.*` 一个字节都没动**，你的硬闸不受影响。
- 追加内容另有独立载体：`formal/manifest_addendum_ruling_88_5.json`（不接受就地追加时也能读到三字段）。

## 5. npz（`--s1-npz-crosscheck` 用）：**三跑 sha 逐字节一致**

| 跑 | 目录 | `states_14d.npz` sha256[:12] | bytes |
|---|---|---|---|
| run1（权威） | `runs/vla/b2_states_14d_20260930/formal40/` | **`a84a26079550`** | 1332184 |
| run2（双跑核验） | `…/formal40_dualrun_sha_check/` | `a84a26079550` | 1332184 |
| run3（追加写之后重导） | `…/formal40_postaddendum_sha_check/` | `a84a26079550` | 1332184 |

- 全 sha256 = `a84a260795505780ca9c403d85719dd4b75921d18799ee61024d14e3ef7cd187`。
- **run3 的意义**：在两次 manifest 追加写**之后**重导一次 ⇒ 证明追加写没有碰数据（sha 不变），
  且 run3 的 `manifest.json` 里 `source_dataset.demo_manifest.sha256_12_at_read` = **`e319754dd030`**（当前值）。
  **要读"npz ↔ 当前 demo_manifest"的对应关系，请引 run3 那份 `manifest.json`。**
- 机器判定：`runs/vla/b2_states_14d_20260930/formal40_dualrun_sha_verdict.json`
  （`raw_file_sha_equal=true`、9/9 数组 `bitwise_equal=true`；并排除了"两跑恰好同一秒"的假象 ——
  numpy 把 zip 条目时间写死成 `[1980,1,1,0,0,0]` ⇒ 逐字节可复现是结构性的）。
- 导出器 = `scripts/b2_export_states_14d.py`（986 ln `8708d4a84d7f`），强制 `MUJOCO_GL=disable`、
  `gpu_nonusage.n_foreign_compute_apps={before:0,after:0}` ⇒ **可事后证明没碰卡**；
  16 道自查 `verdict=PASS / n_red=0`；`c2_consumer_drycheck.ok=true`
  （只读 `importlib` 干跑你的 `load_frames`，`no_write_proof_verdict=PASS_not_written_by_this_process`）。

### 5.1 契约面（**键名逐字不变，别改**）

`frames=[11035,14] float64`、`start_poses=[40,14]`、`physical_range`、
`physical_range_declared_c2_caliber`、`physical_range_effective`、`observed_travel`、
`episode_index`、`episode_boundaries`、`direction_code`（共 9 个数组）。
你已实测过 `contract_conformant=true`（逐维 `max_rel_diff ≤ 1e-9`）⇒ 这一面 B2 不动。

## 6. 夹爪维口径（**裁定 87.6，D 已裁**）

- **契约文本不得硬编码任何夹爪数值**；各维取值范围 = **主线数据的同源实测值**
  （npz 的 `physical_range_effective`，与 `frames` 同源）。
- `scripts/c2_collect_env_states.py` 是**诊断专用源**，它的 `0.91001` **不得移植进主线**。
- 契约里出现的任何具体数字（含旧文本的 `1.0`）**一律是登记项、不是判据**。
- npz 里三个槽位并存（`physical_range` = D 契约字面 / `physical_range_declared_c2_caliber` = C2 现行口径 /
  `physical_range_effective` = 实测生效值），**你按裁定 87.3 的 `must_cover` 覆盖"声明物理区间"时，
  以 `physical_range_effective` 为分母出处**（`resolve_physical_range_lerobot` 的"规则可搬、实测值不可搬"，裁定 71）。
- **一处 B2 侧待改的陈旧状态**：导出器仍把 `contract_conflict.status` 写成 `OPEN_needs_d_ruling`，
  而 D 已在裁定 87.6 关闭 ⇒ B2 会把它改成"已由裁定 87.6 关闭"并重跑三跑核验（只改状态串，不改数组）。
  **在你看到它变更之前，请按"已关闭"读**；若你的闸把它当 open 判红，那是假红，请引本节。

## 7. 渲染臂（裁定 88.5-1 的补偿控制）与负载口径

- `renderer_class_at_start = nvidia_gpu`、`renderer_class_at_end = nvidia_gpu`、**`arm_stable = true`（4/4 判据）**、
  `environment_invalid = false` ⇒ **本批不是 `environment_invalid`，可以进 BC。**
- 两端 `GL_RENDERER` 逐字相同（`NVIDIA A800-SXM4-80GB/PCIe/SSE2`，`4.6.0 NVIDIA 590.48.01`），
  连探针场景的 `render_byte_mean` 都是同一个值 `12.9741`。
- **如实登记的缺口**：`renderer_class_at_end_in_run = null` —— 产出这批的生成器字节
  （`b6af48fc6d58`，影像 `tmp/b2_s1_generate_dataset.py.formal_b6af48fc6d58`）在运行内**没有**终点复测；
  `renderer_class_at_end` 是**运行结束后 1240.5 s** 的独立复测（同一函数 `gl_identity()`，同一把尺）。
  运行中途没换臂由两组机器算的间接证据承载：40 集墙钟 `max/median = 1.0478`、
  `n_exceeding(>2×median) = 0`（换臂会造成 ≈12.64× 阶跃 = 420.2 s/集），
  以及运行末段的连渲对 **40/40 集**都产出了逐槽测量（240 行，G4b/G4d 均 PASS）。
- 端点复测器 `scripts/b2_probe_render_arm.py`（389 ln `34da0a62c2b3`）**自带反向牙**：
  用 D §19.2-4 的形态（`MUJOCO_GL=egl` 但**不带**前缀）起子进程 ⇒ 实测 `mesa_cpu_software`
  （`GL_RENDERER = llvmpipe (LLVM 15.0.7, 256 bits)`）、`tooth_verified=true`
  ⇒ 它不是恒报 `nvidia_gpu` 的报告器。产物：`formal/renderer_arm_endpoint_probe.json`。
- `contaminated_by_cotenant = false`（`loadavg_1m` 摆幅 0.15 < 5.0）⇒ 墙钟/产能数字**不需要**降级为趋势参考。

## 8. 还没做完的（B2 自报，别把它当成"已验"）

1. ~~**团队 QC（validate → clean → qc）尚未对 formal 跑**~~ ⇒ **已跑完（03:37），结论见 §10：
   `RED=0`，不需要暂停重算。**
2. **`overwrite_guard` 从未真正触发过**（teeth 三跑 + formal 都是新目录 ⇒ 四次都是
   `N_A_no_preexisting_manifest`）⇒ B2 欠一颗 CPU-only 牙（合成"已有 manifest"的目录，
   证明 before 影像 + 回收站移动都发生）。**这条不影响本批数据的有效性**（本批没有覆写任何东西），
   但它是"从没咬过的守卫"，B2 不把它算成已验的保护层。
3. **加项 1（渲染臂硬 preflight 拒绝 + `exit != 0` 的牙）仍欠**，D 已裁为"下一次采集之前落地"，
   不阻塞本批（裁定 88.5-1 的一次性有条件豁免；豁免**没有**作废，因为两端都是 `nvidia_gpu`）。

## 10. 团队 QC（validate → clean → qc）对 formal-40 的结果：**`RED=0`**（03:37 实测）

- 判词：`runs/vla/b2_sim_demo_bidir_20260930/qc_team_formal40/qc_verdict.json`
  （177734 B `f4a0a1f18565` as_of 03:37:11）：**`verdict=WARN`、`PASS 8 / WARN 1 / RED 0 / UNJUDGED 0`**，
  闸构建 `f7eb9cc55dbb`（`scripts/b2_run_team_qc.py`，1201 ln）。**`ok=false` 只因 `ok == (verdict=="PASS")`；
  没有任何一条红**（裁定 78.2 的口径提醒：别把 `ok=false` 读成"数据有问题"）。
- **clean 集（= formal 的 40 集）：`episodes=40`、`status={'ok': 40}`、`badcase_by_rule={}`（0 badcase）**，
  三个 stage（validate/clean/qc）对 40 条都有 `episode_done`；`rc=0`、`run_status=completed`、用时 3.6 s。
- **"0 badcase" 不是空洞真**：负对照 22 条缺陷 episode **全部被抓**（`Q5 PASS`，27 种规则命中，
  每条缺陷的 primary 规则都在它自己的证据通道上触发）；35 条 enabled 规则 **invocations 全 > 0**
  （`never_invoked=[]`）。
- **团队仓只读已被机器核**：`Q1 PASS`，跑前跑后 193 个文件 **`n_changed=0 / n_added=0 / n_removed=0`**；
  `Q8 PASS`，pristine 数据集（`formal/team_form/data`）**逐字节不变**，被流水线就地改写的是
  `qc_input/` 里的**副本**（clean 40 个 `converted_metadata_normal.json`；neg 23 改 + 21 新增 `badcase.json`）。
- **唯一的 WARN（`Q4_rule_coverage_nonvacuous`）与 B2 的数据无关**：它是团队规则 **`C07`
  （`rules/clean/c07_range_post_check.py`，v1.1.0）的敏感性没有证据通道** —— C07 `depends_on=["C06"]`，
  且 `ctx.shared["rejected_indices"]` 为空时**直接早退**（源码第 27-29 行）⇒ 正常路径永不写 badcase，
  实测两集 `badcase_count` 都是 0。B2 把它**如实登记为"未证明"而不是"已验过"**（这正是 Q4 存在的理由），
  并已开 RR-B2-22 请 D 裁是否值得为 C07 专门造一条负对照（需要"上游先拒帧 + C06 重映射后 range 仍不连续"
  的复合缺陷）。**这条 WARN 不构成对 formal 数据的任何否定。**
- **首跑（03:27）曾判 `RED 2` ⇒ 是 B2 自己那把闸的假红，已根因修 + 装牙**：
  旧 `Q6` 用字面量 `B_to_A` 认反向（那是 0929 形态夹具的词表），旧 `Q7` 要求**任何**数据集都不得自称
  demonstration（那也只是夹具的口径）⇒ 20/20 均衡的真双向示范集被判成"没有反向 = 全项目最硬的数据缺口"。
  首跑产物留证不改写：`qc_verdict.run1_false_red_q6q7.json`（173450 B `ff02a81fd920`）。
  修法：判据抽成纯函数 `judge_directions()` / `judge_data_kind()`，**方向标签用数据集自己声明的
  `reverse_direction_label`**（formal 走 `manifest_declared_labels`；负对照走
  `legacy_fixture_vocabulary_fallback`，退回路线登记在产物里），均衡**机器复算**不采信交件自述；
  Q7 按角色分岔（夹具不得自称示范 / 示范集必须带齐 `not_a_capability_claim=true`、
  `capability_claim=false`、`policy_executed=false` 且不得自称 policy/teleop/human/learned/rollout）。
  **牙 9/9 全过**（`qc_q6q7_teeth.json`，14899 B `f2e37ca0533c`）：4 条正向必须红（反向为 0 / 20-19 不均衡 /
  自述与复算不符 / 示范集缺免责声明 / 自称 policy_rollout）+ 1 条必须**弃权**（认不出反向标签 ⇒ UNJUDGED，
  不猜）+ 4 条反向必须绿（含 **T1 = formal-40 的真实形态不许再假红**、T9 = 0929 夹具词表仍绿）。

## 9. B2 侧不许你改的面（避免漂移）

- `representation_version` = `b2-s1-sim-bidir-aloha14d-dt0.034-29.4118hz-grip14_to_qpos_pair(+v,-v)-team480x640+pi05x224-v1`
  （**`-v1` 冻结**，裁定 85.3：反向串是 D 批准的逐字串，改串才等于换版本）。
  **它与你的 stats `representation_version` 是两个不同的版本串**（裁定 87.x）：
  BC 的硬闸认 `stats_provenance == formal40_bc_source`，**不是**版本串相等。
  B2 侧未发现两者被当成同一个字段；**若你侧发现混用，请报 D**。
- 数据集本体三个子树（`pi05_lerobot / team_form / sidecar`）：**只读**。B2 之后也不会再动它们
  （任何追加写只碰 `demo_manifest.json`，并带只增不改断言）。

## 11. 【知会 · 2026-09-30 06:0x】裁定 87.6 的**状态串改判已落码**：你的 npz sha **一个字节都没变**

D 在 §D90.8 批准 B2 改 `contract_conflict.status`（`OPEN_needs_d_ruling` → 「已由裁定 87.6 关闭」）时
**加了一条**：「改完 sha **若变**，必须同时在 `daily_report` 知会 C2，因为 C2 的 BC 硬闸认的就是
这个 npz 的 sha；**在 C2 已经用旧 sha 建过 stats 的情况下改 npz，会造成 provenance 与实物失配**
⇒ 请与 C2 对一次时序（谁先谁后都行，但必须有一方等另一方）。」

**实测结论：sha 没变 ⇒ 时序问题不存在，你不需要等 B2、也不需要重算任何 stats。**

- **改的只是导出器的散文/状态字段**：`scripts/b2_export_states_14d.py`
  （**986 ln `8708d4a84d7f`** → **1040 ln `122a92af2131`**）。`contract_conflict` 下
  新增 `closure` 与 `status_history` 两块，`clause_a/clause_b/contradiction/relative_diff_pct`
  **全部保留为历史登记**（裁定 92.4：作废不删件、不改名）；`physical_range`（契约字面，夹爪 1.0）
  显式标为 **`registered_only_not_a_criterion`** —— 这与你在 §6 已经采的处置（只登记不使用）一致。
- **三跑逐字节核验**（`runs/vla/b2_states_14d_20260930/formal40_conflictclosure_sha_verdict.json`
  `85d10bb6f9cf`）：原始导出器 1 跑 + **改判后**导出器 2 跑 ⇒
  **raw file sha256 三跑全同 `a84a26079550…`**、**逐数组 bitwise 全同**、
  manifest **0 键删除 / 9 键新增（全在 `contract_conflict` 下）/ 30 键变更**
  （全部是状态串文本、provenance 时间戳与身份、或环境读数）。
- **对你的影响 = 0**：你已用 `a84a26079550` 建过 stats（`runs/vla/c2_norm_contract_20260929/stats/`
  下多份命中）⇒ **provenance 与实物没有失配**，`stats_provenance=formal40_bc_source` 照旧有效。
- **一处已知差值并解释**：`runs/vla/b2_states_14d_20260930/formal40/manifest.json` 被覆写
  （前像 `tmp/b2_before_images_formal40_conflictclosure/`），其 `as_of` 变成重跑时刻；
  而**数据集本体** `demo_manifest.json` 里登记的 npz `as_of` 仍是 `03:06:34`
  （本次重跑用 `--no-patch-demo-manifest`，**不二次改数据集本体**）。
  **两处 `as_of` 不同、sha 相同** = 同一份数据的两次导出时刻。
  ⇒ 你的硬闸若认 `as_of` 而不认 sha，请**以 sha 为准**并报 D；B2 侧未发现有人拿 `as_of` 当身份。
- **`formal40/states_14d.npz` 的 mtime 变了、字节没变**（重跑必然重写文件）。
  若有下游用 mtime 做缓存键 ⇒ 会白重算一次，但结果不变。
