# D 的权威重启入口（2026-09-30 10:4x 落盘 · 取代 `d_context_checkpoint_20260929_2130.md`）

**读到这一件就够了。** 上一份 checkpoint（**1207 ln `8013accb49d1`**，§1–§21.12）**仍在盘、仍是历史细节的权威源**，但**它的「当前状态」章节已过期**（写在裁定 92 之后、裁定 93 之前）。
本件 = 裁定 93 之后的**当前状态**。前像已落：`runs/vla/d_ruling_round_20260930_1010/d_context_checkpoint_20260929_2130.md.beforeref`。

---

## 0. 身份、仓库、模式

- 仓库：`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot`（NFS）。我是 **D（监管 / 口径裁定）**。
- 四条活线：**A2**（π₀.₅ 运行时 + 延迟 + BC 执行）· **B2**（数据 + **git 单写者** + `registry/`）· **C2**（契约层 / 归一化 / 闸审计）· **E**（GPU 渲染 / 冷启动 / **断点续跑保险**）。A/B/C 原线已冻结。
- 协调面：`rl_harness_supervision/`（D 的交接件）· `work/decisions/decisions_20260929.md`（裁定，append-only）· `daily_report.md`（append-only，**从当前 tail 读，不用缓存 offset**）· `work/project_parameters.json`（**D 单写者**）· `runs/vla/{a2,b2,c2,d}_*` · `runs/infra/{c2,e}_*`（线前缀隔离）。
- 北极星：**「尽快把仿真链 RL-VLA-harness 跑通，再考虑后续」**（用户原话）。用户已明示「**速度优先**」。
- 当前时刻 2026-09-30 10:4x（Asia/Shanghai）。

## 1. 一分钟接手：现在处于哪一步

- **裁定 93 已落**（decisions §93 · params **rev18**）：**E4 = 甲 + 补丁** ⇒ `Tb_scale_floor_effective` / `Tr3_near_constant_floor_material` 转 WARN，换上 `Tz_denom_strictly_positive` + `Tres_per_dim_resolution_floor` 两颗 D 定标硬红 ⇒ **`S3 BC` 前置清零**。
- **四份派工单已落** `rl_harness_supervision/d_handoff_to_{c2,a2,b2,e}_20260930.md`。
- **A2 的 S4b 与 C2 的 T-C2-8 并行**（S4b 的三个前置都已落地，不再串行等待）。
- **BC 还没跑** ⇒ **裁定 46 的能力声明禁令仍然生效**：任何「能搬运 / 学会了」的表述都无效。
- 环境 as_of 10:33:28：GPU `0 %` / `0 MiB`、`compute-apps` **0** 行、无活 python 训练进程、`loadavg [12.76, 8.06, 5.87]`（1m 含 D 自己的只读提取）。`HEAD = 0913535`，脏 6 项（**待 B2 代提交，P0**）。

## 2. 关键路径（照此推进，不要重排）

1. **[B2 · P0]** T-B2-17 两次代提交 + RR-B2-09（顶层 `ok` 把 WARN 算失败 ⇒ **不修则 C2 转 WARN 的牙会被二次判死**）。
2. **[C2 · P0]** T-C2-8：落 93.1/93.2/93.4-C2侧/93.6 + **四点单调性实测**（n=547/2196/10488/11035，同一 stats、同一 `--s1-frames`）+ 重跑全量闸与全部变异体 + 重生成 formal-40 stats 与 `mainline_status.json`。**预授权一次通过**；触发可证伪检查点（单调性不成立，或全量口径下任一非近常量维 `< 8`）⇒ **停手回报 D**，不得自行降阈值或升 P0。
3. **[A2 · P0]** T-A2-6 S4b（GPU 窗口申报；四类判定接 `ledger`、独立于 `reward==4`；**必须复用** `harness/env_gym_aloha.py` **579 ln `6c4d71eb732e`**，不得自造判定层；同批做运行时 `-1` prompt 牙 + `pad_vector` 记 `not_measured` + 落 `renderer_class` 给 E 搭车）。
4. **[B2 · P1]** T-B2-20 `registry/` 多门禁并存（D 已裁 T-C2-6：`GATE_MODULE_PATH` 改按 `gate_id` 索引，默认仍是 ACT 冻结基线，新增 `pi05_norm_contract`，**跨 gate 身份串不得互认**）—— **这是 A2 按 93.4 做 sha 对账的地基**。
5. **[A2 · P0]** T-A2-7 S3 BC 入口：必须 AND `gate_verdict_green` + **自己复算**闸产物 sha 对账，不一致 ⇒ `LearnerRefused`。**T-A2-8：BC 结果口径必须在开跑之前预登记**（三分开 / 双向独立 / 动态 BC 对照 / 失败面归因 / 裁定 46 解禁点）。
6. **[E · P1]** T-E-11 重启续跑就绪清单（**不许上卡**）+ T-E-9 裁定 92 三条欠账。
7. **BC 出结果之后**才进入 S5 双向评测 → B5 RL 可行性 → S6 一次更新（`params:1112` 的原链）。

## 3. 裁定 93 的八条（细节见 decisions §93 / params `model_and_learning.ruling93_e4_resolution_rev18`）

1. **93.1 甲**：两颗牙 `blocking → False`（机制 = `harness/norm_contract.py:848`，**断言文本一字不改**）；阈值状态 → `registered_measurement_not_a_judgment`；登记不许缩水（转 WARN 后字段数不得减少，配变异体）。
2. **93.2 补丁**：`Tz_denom_strictly_positive`（绝对硬红、无定标空间、咬 ACT 线 `(x-mean)/(std+1e-6)` 除零族；`Tr1` 保持 blocking 不降级）+ `Tres_per_dim_resolution_floor`（逐维、**全量口径**：非近常量维 ≥8 硬红；近常量维 ≥2 硬红 + `<8` WARN）。定标依据 = `runs/vla/d_ruling_round_20260930_1010/probe_resolution_calibration_inputs.json` **236 ln `55190798963c`**；余量 **2.75× / 1.5× / 2.5×**；采样计数假象实证 dim0 **3→23**、dim7 **4→22**。**两个可证伪检查点已预登记。**
3. **93.3 E1 分口径**：正确性族 = held-out、分辨率族 = 全量；**撤回** `params:688` 的 median 可推翻条件，统一到 `:778` 逐维口径；触发①记 `not_measured`（尚无 BC）、②不触发、③待实测；**不升 P0**（用户速度优先）。
4. **93.4 E2**：BC 准入必须 AND 闸 verdict（C2 加四字段 + 牙 `Tbcad_admission_requires_green_gate`；A2 入口不一致 ⇒ `LearnerRefused`）。
5. **93.5 E3**：`params` 里牙② 的字面 id 改 `Tcov_declared_interval_covered`（实测 `Te2` 0/8、`Tcov` 8/8）；`Te2` 的非法 bin 形式另由 G50 `heldout_below_lo` 证明 ⇒ 证据不丢。
6. **93.6 E5**：批 `Txr_crosscheck_freshness_is_registered`（WARN 级、非阻塞、复用 M18 形态；不升 P0）。
7. **93.7**：`params:768` 改 `Tiv_out_of_declared_interval_is_measured（harness/norm_contract.py:1072）`（**D `grep -n` 亲核**；旧名已撤回，记录在 `:637`/`:1086`）。
8. **93.8 新纪律（红线族）+ 缺陷类 ⑲**：`reference_auditor_must_prove_its_own_pattern_coverage` / `green_verdict_from_an_under_covered_audit_pattern`。审引用/审清单/审命名的闸必须自带**对照探针**，产物落 `pattern_coverage_probe: {injected_bad_form, detected: true}`，缺 ⇒ `not_measured`、**不得报绿**。

## 4. 待用户批（rev18 口径，**D 不代批**）

- **已批**：④ 裁定 90.4 **第 3 条 = P1**（依据「速度优先」）· **E4 = 甲 + 补丁**。
- **仍待批 5 项**：① `timeout_isolation_scope=td_only` · ② 丙案（EGL 采集 / osmesa 对照）· ③ 裁定 87.3 adopt ①（**按 rev16/rev18 口径批，不要按 rev15 原文**）· ⑤ `NVIDIA_DRIVER_CAPABILITIES=graphics` · ⑧ 裁定 92 四条（尤其 **92.1 不需要 v4**）。
- **D 判暂缓/不做**：⑥ bf16（会新建 `representation_version` 并作废裁定 84.7 的 realtime 口径）· ⑦ E 的 5 分钟稳态窗口。
- **新开的分叉（D 已自证 + 写可推翻条件）**：`Tres` 的分口径。**若用户认为 held-out 上那 6 个低 bin 维 `[0,3,5,7,10,12]` 必须先修再跑 BC ⇒ 93.2/93.3 整体回退到 held-out 口径、`per_dim_coverage` 升 P0**（代价 = 关键路径加一轮生成器重构）。

## 5. 硬约束（一条都没变）

不用 `rm`（走 `recycle_bin`）· 永不碰 `/workspace/mnt/sppro/yhzhang91/datasets` · `RL_Harness_v4_20260924/` **只读** · run 目录线前缀隔离 · 吞吐/延迟数字必须成对引 `loadavg`(3 点) + `nr_throttled`（cgroup **12 核**，`nproc=112` 是假象）· 外部事实标 `external_unverified`、不与实测同表 · `declared_only` 永不 blocking · 闸必须双向有牙 + `applies_when` + 绿见证 + 幅度下限 + 变异体自证（**恒真的闸等于没有闸**）· 每个探测器三值（正 / 负 / **NOT-MEASURED**，空集 → `null` + 非零退出）· 覆写自己的产物 ⇒ 前像 + `sha256[:12]` · 内容含反引号/`$()`/`$VAR` 时**必须**用 `<<'EOF'` 引用型 heredoc（红线）· 不写系统（含 `ldconfig`）· GPU 优先级 **A2 > B2 > C2 > E** + 三网占用判定 · **D 永不 `git commit`（单写者 B2）、永不写实现代码** · v4 五个状态词 · 所有 sha 引用带 `as_of` + 机器取值（**永不转写**）+ 可对账到已保存产物 · 单样本不许写成率 · **逐维失效模式必须由逐维统计守（永不 median/mean）** · 从上一版派生字段必须按 **rev 号**索引（不用 `[-1]`/`[-2]`）· **作废永不改名**（原件原字节原名 + `.INVALIDATED.json` 旁证 + 注册表登记）· **同名多件必须带路径消歧**（rev18 新）。

## 6. 用户偏好

中文 · 证据优先（`file:line` + 身份三元组 + `as_of`）· **战略分叉归用户，技术口径 D 自证自裁**（自证时必须写可推翻条件）· append-only 共享文书从当前 tail 读 · 每轮更新以「D 等 / 用户需」收尾 · **保护"下位纠正 D"的通道**（已用 **12** 次）· 服务器可能关闭 ⇒ checkpoint 必须保持最新 · 用户 10:0x 明示：**速度优先，D 判断无误可直接确认执行**。

## 7. D 的错误账（透明文化，重启后不许清零）

**D 同型错误 = 18**（#15 软边界当硬界 · #16 用 median 守逐维失效 · #17 用已作废的驳回理由 · #18 把未核实的文件系统断言写进权威重启入口）；**本轮 +0，一次未遂已登记**（93.7 的 `:1071` vs `:1072`）⇒ 新自查项 `d_must_grep_before_citing_a_line_number`。**下位纠正 D = 12**。**缺陷类 = 19**（⑱ `fabricated_justification_for_a_wrong_value` · ⑲ `green_verdict_from_an_under_covered_audit_pattern`）。

## 8. 本轮 D 落盘的全部件（身份见 `D_IDENTITY_TABLE_20260930_1045.json`）

`work/decisions/decisions_20260929.md`（追加 §93）· `work/project_parameters.json`（**rev18**）· `rl_harness_supervision/d_handoff_to_{c2,a2,b2,e}_20260930.md`（四份）· `daily_report.md`（追加 §D93）· 本件 · `runs/vla/d_ruling_round_20260930_1010/`（四份前像 + `d_probe_resolution_calibration.py` + `probe_resolution_calibration_inputs.json` + `write_params_rev18.py` + `d_write_identity_table.py` + `D_IDENTITY_TABLE_20260930_1045.json` + `env_snapshot.txt`）。
⚠ **`runs/` 被 `.gitignore:12` 排除 ⇒ 上面 run 目录里的全部证据只在 NFS，不入库**；文书五件（decisions / params / 四份交接件 / daily_report / 本件）**必须由 B2 代提交**（T-B2-17，P0）。

## 9. 接手后第一件事

`git log --oneline -3` · `git status --porcelain | wc -l` · `tail -120 daily_report.md`（从当前 tail 读）· `ls -dt runs/vla/c2_norm_contract_20260929/gate/run_* | head -3`（看 C2 是否已落 T-C2-8）· `ls -d runs/vla/a2_s4b* runs/vla/a2_s3_bc* 2>/dev/null`（看 A2 是否已开工）· GPU 三网 · 然后按 §2 的顺序派工，**不要重排、不要代任何线写实现代码**。

---

## ⚠ 取代指针（2026-09-30 12:1x 由 D 追加；**以上原字节保留、不改一字**）

**本件已过时，新读者一律从 `d_context_checkpoint_20260930_1205.md` 进。** 三处口径已被取代：
① **本件 §2 的关键路径（C2 formal-40 stats → A2 S4b → S3 BC）已被裁定 95.2 的「六步序列」取代**（用户 11:4x 的方向输入 = 最高权威，**不许重排**）。
② **本件的「BC 前置清零 / 速度优先」口径已被裁定 95.1 的「治理冻结令 + 检查三分类」取代**（Ⅰ 阻塞 / Ⅱ 登记不阻塞 / Ⅲ 冻结扩张）；**本件 §3 的裁定 93 八条中，93.6 `Txr` 已冻结**。
③ **本件 §4 的待批清单按 rev21 读**（口径类已清零，剩 3 项方向确认与资源）。
**本件不作废**（作废永不改名同族）：它是**裁定 93 时代**的权威入口，保留以便追溯"当时为什么那样派工"。
