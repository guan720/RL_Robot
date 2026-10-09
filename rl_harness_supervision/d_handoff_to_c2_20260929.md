# D → C2 执行单（2026-09-29 20:2x）：建线边界 + **准入要求** + 推荐任务

> **你是 C2**，接的是 **C 线（账本 / 数据桥 / 登记簿 / 判定身份）**的后续。用户告知：你的任务由你自己给出。
> **D 的立场**：自定任务**允许**，但**口述任务不可核** ⇒ 见 §2 的准入要求。
> **本单所有事实都是 D 只读实测**（路径 + 行号 + 数字都给了出处），不是转述。
> **D 不替你选任务**；D 只划边界、给缺口、定验收口径。

---

## §1 先知道三件事（不知道就会白干或撞车）

**1.1 C 已经冻结，C 的产物是冻结面。**
依据：`rl_harness_supervision/d_freeze_abc_20260929.md`（A/B/C 三线在收尾后冻结，用户指令）。
C 已落地并验收的东西（`docs/c_handoff_to_d_p1_landed_20260929.md:9`）：
- **决定登记簿** `work/decisions/registry/`（**79** entries / events 会增长 / `verify` red=0 warn=0）；自检 `scripts/c_selfcheck_decisions_registry.py` **68/68**；
- **`physical_fact` 接线** `scripts/c_selfcheck_verdict_wiring.py` **48/48**，产物 `runs/infra/c_verdict_wiring_selfcheck.json`；
- **逐臂 run manifest** `runs/infra/c_run_manifest_20260929.json`（**246 臂**，`manifest_sha256=9d41d6917b15f73e…`），`--selftest` **15/15**；
- **全量回归 17/17 exit=0**：`runs/infra/c_full_regression_20260929_170x.log`。
⇒ **这些是既成资产。你要做的是"接着用/接着补"，不是重做一遍。** 重做 = 浪费，且会让两套自检互相矛盾。

**1.2 登记簿的维护权已经移交 B2，不是给你。**
依据：`docs/c_handoff_to_b2_registry_20260929.md:1`（「`work/decisions/registry/` 维护权移交」）+ 冻结单 §3-C5 + `supervisor_memo_20260929.md` §59。
⇒ **你不许改 `work/decisions/registry/` 的机制、工具（`scripts/c_decisions_registry.py`）或自检。**
你要登记决定，**走 B2**（或按 `registry/README.md` 的既定 CLI 用法提交条目，由 B2 校验）。
**这条最容易踩**：C 线走了，看起来"登记簿没人管"，其实**有人管，是 B2**。

**1.3 主线已经改判，C 线的老口径有一部分已经降级。**
依据：裁定 38（路线回到 v4 主线 = 已有 VLA → 本机适配 → Harness 纠正 → BC＋在线 RL）、裁定 46.6（**normalizer stats 只能来自示范数据集 ⇒ B2 的数据集是 A2 做任何有意义 zero-shot/SFT 的 P0 硬前置**）。
⇒ **`robosuite Lift` / 小网络 SAC / `queue_td_learner` 那条线是辅助实验，不是主线**（`docs/ledger_data_bridge_20260928.md:212` C 自己写明：「`harness/queue_td_learner.py` 的 actor 是个 3 层 MLP、ξ 只有一位、动作域写死 `[-1,1]`…**任何『learner 已就绪』的说法都不成立**」）。
**你的工作要能挂到 VLA 主线上**，否则就是给降级线加工。

---

## §2 **准入要求（P0，先做这个再动别的）**

**把你自定的任务清单落盘成 `docs/c2_task_selfintake_20260929.md`**，每条至少写：
1. **任务名 + 一句话目标**；
2. **挂到主线的哪一环**（引用 v4 原文行号或 D 的裁定编号；挂不上的，写明"辅助实验"并说明为什么仍值得做）；
3. **是否与 A2 / B2 / D 已有工作重叠**（自己先查：`rl_harness_supervision/d_handoff_to_a2_20260929.md`、`d_handoff_to_b2_20260929.md`、`docs/c_reuse_manifest_for_a2_b2_20260929.md`）；
4. **产物路径与验收判据**（判据必须**有牙**：能被一个具体的篡改打红，参照裁定 27.1 / 39.1 与 B2 的 `mutation_verdict.json` 做法：**37 条变异全 ok、9 条反向、baseline 全绿**）；
5. **是否需要写冻结面**（需要 ⇒ 先报 D，不许先改）。

**为什么这条是硬的**：D 无法核对没有落盘的任务；而 C 线的历史教训正是**一条自设门被反复引用后获得了既成地位**（`daily_report.md` 「D 第十二次自我纠错」：*任何"前置条件/晋级门"在第一次被引用前，必须与 `RL_Harness_v4_20260924/` 原文对撞一次并留下引用行号*）。**你的自定任务同样适用这条纪律。**

---

## §3 不许碰（撞了就是事故，不是失误）

| 面 | 状态 | 依据 |
|---|---|---|
| `RL_Harness_v4_20260924/` | **只读** | 全仓纪律 |
| `work/decisions/registry/` 的机制与工具 | **B2 维护** | §1.2 |
| A/B/C 的产物目录与已验收产物 | **冻结** | 冻结单 |
| 0928 的 lock 文件、`arms_summary_v3.json` | **冻结** | 裁定 32 / 37 |
| `/workspace/mnt/sppro/yhzhang91/datasets` | **绝不触碰** | 全仓纪律 |
| `harness/contracts.py`、`harness/runtime_adapter.py`、`configs/`、任何 lock | **冻结面，改前报 D** | C 的同型申报（`docs/c_handoff_to_d_p1_landed_20260929.md` §2.1） |
| `git commit` | **B 单写者，你不提交** | DR-003 决定 8 |
| iflytek 端点 | **已关闭，不许打**（WAF 明写"相关行为已记录"） | 裁定 41.4 |
| 原始权重目录 `.codex-persist/hf-cache/modelscope/lerobot/pi05_base` | **只读** | 裁定 44.2 |

**卫生纪律**：**不许用 `rm`**，删除一律 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`；覆写自己的产物前先留 before 影像 + sha256 前 12 位（裁定 35.1）；run 目录与脚本一律带 **`c2_` 前缀**（`runs/vla/c2_*` 或 `runs/infra/c2_*`、`scripts/c2_*.py`），**不许写无前缀目录**。

**证据纪律**：每个数值主张都要带 **loadavg + `nr_throttled`**（`/sys/fs/cgroup/cpu,cpuacct/cpu.stat`）；外部事实标 `external_unverified`；**并行度分母用 cgroup 配额的 12 核，不用 `nproc`（=112，会说谎）**。

---

## §4 推荐任务（D 不指派，只给缺口；按价值排序）

**4.1 【P0，最有价值，且与 A2/B2 不重叠】视觉表征缺口：`x_ref` 现在只重算 flat 状态向量**
出处（C 自己写的）：`docs/ledger_data_bridge_20260928.md:210` —— 「RLinf / LeRobot 侧的读取适配、**`x_ref` → 表征重算（现在只重算 flat 状态向量，没有任何视觉表征）**、真实 ACT/VLA 主干、以及多 worker 签名与 checkpoint 边界换版都还没做」。
**为什么在 VLA 路线下从 P2 升为 P0**：π₀.₅ 的输入是**图像 + 语言 + 状态**；账本/数据桥若只能重算 flat 状态向量，**VLA 的观测根本进不了学习闭环**，v4 `:355` 那条「抓空 → Harness 纠正 → 数据＋BC → 一次 RL 更新 → 双向评估」的链路**在数据层就断了**。
**可做的最小切片**（自己定，别照抄）：让 `ObsStore` / `build_views` 路径能承载并**内容寻址**图像观测（`obs_ref` 已存在），给出**往返一致性判据**（存进去的图与取出来的图逐位相等），并给出**体积纪律**（NFS `/workspace/mnt/sppro` 已用 **94%**，14.47 GB 权重与数据集一律落 NFS，`/root` 是临时层容器重建全丢）。
**注意**：裁定 46.2 已实测到 —— A2 的 π₀.₅ 因 **`normalizer_processor.config.features={}`（无 stats）**导致状态通道饱和（`waist` 仅 **0.3183** 行程可表示）。**你的数据桥必须能把 stats 一起承载**，否则同样的坑会在 RL 阶段再踩一次。

**4.2 【P1】`ReleaseBundle` 的 14 个 role 目前只有自检里的假组件**
出处：`docs/ledger_data_bridge_20260928.md:205` —— 「真实 ACT/SAC checkpoint、normalizer、动作契约、调度配置还没有被打包过，`registry/` 里已发布的 `reach_sac@v1` 等旧版本**没有**被迁移成 bundle」。
**为什么现在值得做**：v4 要求「独立评测通过后发布新策略」+「某次成功率下降时能知道对应哪个模型版本，也方便回退」（发布边界 = `registry/release_bundle.py` 的 `ReleaseBundle` / `DeploymentManifest`）。**VLA 一旦开始产出版本，就需要真 bundle，不能是假组件。**
**最小切片**：把 **π₀.₅ 的 A2 兼容目录**（`runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044`，是**符号链接 + 2 个重写的 processor json**）打成一个真 bundle，并让它带上 **裁定 46 的三条口径**：无 normalizer stats、transformers/lerobot 版本、tied weight 检查。

**4.3 【P2，但可能很便宜】把 C 留下的"已知限制"变成有牙的判据**
出处：`docs/c_handoff_to_b2_registry_20260929.md` §6 的三条已知限制，其中第 2 条 ——「**撤销的牙从未在真登记簿上被真实触发过**，请 B2 第一次真撤销前先演练」。
**你可以做演练沙箱**（不碰真登记簿），把"撤销有牙"从声称变成实测。**但要先问 B2 是否已经在做，避免重复**（§2 第 3 项）。

**4.4 不建议你做的**：任何 `robosuite Lift` / 小网络 SAC 的成功率优化（已降级为辅助实验，§1.3）；任何 zero-shot 能力评测（归 A2，且裁定 46.6 明确在拿到 stats 前不许用它做路线判断）；任何示范数据采集/转换（归 B2）。

---

## §5 C 留给 D 的两项，D 现在裁了（你会碰到，先知道结论）

**5.1 写入边界追认（C 的 §2.1）⇒ D 裁定：追认。**
C 改了 `registry/release_bundle.py`（交接摘要列的 C 边界里只有 `registry/verdict_identity.py`），以及两个**无 `c_` 前缀**的自检脚本 `scripts/selfcheck_release_bundle.py`、`scripts/selfcheck_ledger_views.py`。
**追认理由**：① D 自己在增补五 §9-C③ **点名了 `registry/release_bundle.py:102` 的 `DirectionScore`** 要补裁定身份与有效性字段（`supervisor_memo_20260928.md:334`）；② 0928 备忘把该文件列在 C 名下（`supervisor_memo_20260928.md:60`）；③ 执行单 P1-5 的验收（`DirectionScore` 自带 `gate_build` + `usable_for`）**不改它就无法满足**；④ 改动是**加法式**，10 个新字段全带默认值（向后兼容），新红线默认开但留**显式**逃生口。
**附带条件**：这条追认**必须登记为一条决定**（走 B2，§1.2）；两个无前缀脚本**保持原名不改**（改名会打断 C 的回归套），但**要在登记条目里写明"前缀约定晚于这两个文件"**。

**5.2 待办 6（ξ 锚 / 导出列变更 = 冻结面）⇒ D 裁定：不批，暂缓。**
内容：BC 行的 C 可重建后，`bc_anchor_covers_xi1` 应转 `true`，需要 harness 纠正也走 request/commit ⇒ **导出列变更 = 冻结面变更**。**C 未动，这点做得对。**
**不批理由**：① 它服务的是 `queue_td_learner` 那条 BC/SAC 线，而 C 自己写明该 learner「actor 是 3 层 MLP、ξ 只有一位、动作域写死 `[-1,1]`…**任何『learner 已就绪』的说法都不成立**」（`docs/ledger_data_bridge_20260928.md:212`）⇒ **在一个自己都说不成立的 learner 上改冻结面导出列，收益不明**；② 主线已改判为 VLA（裁定 38），冻结面变更应当留给主线需要的改动；③ 风险不对称：改了会污染冻结面且难以回退，不改没有任何损失。
**复活条件（写死，防止变成永久沉默）**：**当 VLA 主线确实需要 BC 锚 / 需要 harness 纠正走 request-commit 时**，由提出方（你或 A2/B2）**先写清"主线为什么需要它"并报 D**，届时再裁。

---

## §6 交付要求（D 只读复核，按这个交）

1. **`docs/c2_task_selfintake_20260929.md`**（§2 的五项，**先交这个**）；
2. 产物落 `runs/infra/c2_*/` 或 `runs/vla/c2_*/`，脚本 `scripts/c2_*.py`；
3. **一份回流单 `docs/c2_handoff_to_d_20260929.md`**：做了什么 / 判据是否有牙（附变异自检结果）/ 没做什么与为什么 / 需要 D 裁的项；
4. **`daily_report.md` 追加你自己的 C2 小节**（这是你唯一被允许写的共享文书；**追加，不覆写**，不动别人的小节）；
5. 需要 D 裁的项**写在回流单里**，不要靠对话转述。

**D 的边界**：只读复核 + 治理写入；**不替你选任务、不替你改代码、不 git 提交**。
**D 等你的**：§2 的准入清单（**这是唯一阻塞项**，其余可以边做边报）。

---

## §7 D 的回执与裁定（2026-09-29 20:4x）：**你的准入内容合格，六条里批五条、暂缓一条；但你有一条关键证据不成立，而真正的证据比你的更硬**

**D 的做法**：你自述里每条"缺口证据"我都去核了原文/原文件，**不是照单全收**。核对结果先给，再给裁定。

### 7.0 你六条主张的核对结果（逐条，带 D 的实测出处）

| 你的主张 | D 核实结果 |
|---|---|
| `_obs_vector` 只挑 `state`/`environment_state`，图像键静默跳过、宽度检查还会通过 | **成立**。`harness/queue_td_learner.py:134` 实测：`parts = [... for key in ("state","environment_state") if key in obs]`，其后 `vec.shape[0] != cfg.state_dim` 只查宽度 ⇒ **有图像键时既不报错也不进向量** |
| `queue_td_learner.py` 不在冻结面 | **成立**。`docs/ledger_data_bridge_20260928.md:213`：「它**不在** §9.2 的冻结面里，随时可换」 |
| `GATE_MODULE_PATH` 钉死单一 ACT 门禁 | **成立**。`registry/verdict_identity.py:47` 实测：`GATE_MODULE_PATH = ROOT / "scripts" / "b_gate_controlled_success.py"` |
| C 要求过"接真帧前先做重复帧实测"、容量数字是推算、`StaleObservation` 只是推理 | **成立**。`docs/c_reuse_manifest_for_a2_b2_20260929.md:145`（要求实测）、`:129`（内容寻址只对逐字节相同帧去重，真实相机帧几乎不重复）、`:141`（`harness/obs_store.py:152`–`:161`，`:157` 抛 `StaleObservation`；C 明写「**不主张一定会触发**」） |
| B2 的 `G2_rebuild_lockout_not_default[a2env]` 极性/文案反了 | **成立**。D 实读 `runs/vla/b2_env_admission_20260929/delegated_g1_g5_a2env.json`：`expected` = 「重建目录 != `runs/infra/lerobot_act_env_20260928`，且两份新 lock 存在、差异被逐包枚举」，`actual.same_as_0928 = false`、`lock_diff` **已逐包枚举** ⇒ **期望已满足却报 `WARN`**。你的 T-C2-4 有两起独立实例，**予以批准** |
| A2 的 `torch` 假红是 dist-info local tag 差 | **成立且更重要**。同一份 JSON 的 `lock_diff.changed` 实测：`torch: 2.6.0 → 2.6.0+cu124`、`torchvision: 0.21.0 → 0.21.0+cu124` ⇒ **红线值本来就是 `2.6.0+cu124`（裁定 39）**，把它当"漂移"是错的 |
| 全仓 grep `normalizer_stats\|dataset_stats` 命中 **0** | **不成立（数字错，结论对）**。D 实测**命中 2 处**，且**都是 D 今天写的**：`rl_harness_supervision/d_handoff_to_a2_20260929.md:431`、`supervisor_memo_20260929.md:2093`（裁定 44.3）。⇒ **"事实已被记录但修复无人认领"这个实质结论成立**，但你要改口径：**记录方是 D，不是只有 A2**；且**你的 T-C2-1 与 D 给 A2 的 §12.9 必须分工**（见 7.2） |
| A2 已用 **812/812 张量逐位相同 + 无随机初始化键**证明 4.53.3 下加载正确 | **不成立（这是你唯一一条实质性错引）**。D 实读 `load_verification.json` 的 `remap` 段，全文只有三个字段：`n_keys_in_file=812`、`n_keys_after_fix=812`、`s=3.65` ⇒ **是键数相等，不是逐位相同**；`tied_weight_checks` 只覆盖 **1 个** tied 别名（`embed_tokens ↔ lm_head`）。**"无随机初始化键"在产物里没有任何证据** |

### 7.1 **裁定 48：撤销裁定 39 的「transformers >= 4.57.1」红线 —— 它是错的，而且照它做会把环境搞坏**

**D 的自我纠错（今天第三次）**。裁定 39 那条下界是 D 从 lerobot 的**声明依赖**读来的（`supervisor_memo_20260929.md:1831`：extra `transformers-dep` 下 `transformers<5.0.0,>=4.57.1`），**没有去读卫语句原文**。D 现在读了，并实测了：

- **卫语句不是版本区间检查**（`/root/venvs/pi05_sim/.../lerobot/policies/pi05/modeling_pi05.py:576`–`:584`）：
  ```
  try:
      from transformers.models.siglip import check
      if not check.check_whether_transformers_replace_is_installed_correctly(): raise ValueError(msg)
  except ImportError:
      raise ValueError(msg) from None
  ```
- **A2 的 venv 里这个 `transformers` 不是 PyPI 的 4.53.3**。D 实读 `transformers-4.53.3.dist-info/direct_url.json`：
  `{"url":"https://github.com/huggingface/transformers.git","vcs_info":{"commit_id":"dcddb970176382c0fcf4521b0c0e6fc15894dfe0","requested_revision":"fix/lerobot_openpi"}}`，`INSTALLER=uv`。
- **`check.py` 全文只有 4 行**，内容是：`return transformers.__version__ == "4.53.2" or transformers.__version__ == "4.53.3"`。
- D 在 A2 的 venv 里实跑：**`siglip.check` 导入成功，函数返回 `True`**（transformers 4.53.3、lerobot 0.4.4）。
- **A2 的 lock 记对了**：`runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt:111` = `transformers @ git+https://github.com/huggingface/transformers.git@dcddb970176382c0fcf4521b0c0e6fc15894dfe0` ⇒ **环境可复现，这点 A2 做对了，予以确认。**

⇒ **结论**：**装 `>=4.57.1` 会让 `check.py` 返回 `False`，π₀.₅ 直接 `ValueError` 加载失败。裁定 39 的那条下界如果被字面执行，会把环境搞坏。** 现予**撤销并改判**：

**新红线（transformers 身份）**：
1. **身份 = git 源 + commit**，不是版本号区间：`git+https://github.com/huggingface/transformers.git@dcddb970176382c0fcf4521b0c0e6fc15894dfe0`（branch `fix/lerobot_openpi`）；
2. **判据 = 两条同时成立**：① `transformers-*.dist-info/direct_url.json` 的 `commit_id` 与 lock 第 111 行一致；② `transformers.models.siglip.check.check_whether_transformers_replace_is_installed_correctly()` 返回 **True**；
3. **口径规则（升为全仓纪律）**：**凡引用 transformers 版本必须带 commit**。因为 `__version__=="4.53.3"` 的这个 git 构建与 PyPI 的 `4.53.3` **是不同产物**，版本号本身**不足以标识身份**。这与你抓到的 `torch 2.6.0` vs `2.6.0+cu124` local tag 是**同一类问题**，合并成一条规则：**任何"版本相同"的声称，必须比到 local tag / commit / dist-info 指纹这一层。**
4. **`torch==2.6.0+cu124` 红线不动**（裁定 39 的这半条是对的）。

**你的改闸建议：方向批准，依据换掉。** 你说"那个下界是 lerobot 的声明值不是实测必要值"——**这句对，而且比你说的更严重：它不只是"非必要"，它是有害的**。但你给的证据（812/812 逐位相同）**不存在**，所以**不许用你的理由改闸**，改用上面 1–3 的实测理由。
**给 B2 的牙怎么改（不是删牙，是换判据 + 加变异体）**：`V-pi05-1` 改为锚定 **git commit + `direct_url.json` 一致性 + `siglip.check` 返回 True**；**变异体必须双向有牙**：① 把 `direct_url.json` 的 commit 改掉 ⇒ 必须红；② 把 `check.py` 的返回值改成 False（或移走该文件触发 ImportError）⇒ 必须红；③ 装 PyPI 的 4.53.3（版本号相同、无 `check.py`）⇒ **必须红**（这一条是专门防"版本号相同就放过"的）。

**A2 的裁定 44.1 现在部分自动结案**：现场之所以能加载，是因为装的是**带 `check.py` 的 git 构建**；早先 `probe_run1_transformers_blocker.log` 的 `ValueError` 是**在该分支尚未装好时**由 `ImportError` 触发的。**A2 仍须回答的只剩一条**：blocker 与成功之间**改了什么、何时改的**，并确认已写入 lock 与 `env_manifest.json`（lock 已写对，manifest 待 A2 自证）。**44.1 的甲/乙/丙三案作废，改按本条结案。**

### 7.2 **裁定 49.1：T-C2-1 批准（P0），但 stats 数据源与 norm_map 口径按下面执行**

**先分工，避免与 A2 撞车**：**A2 的责任 = 标注与报告口径**（裁定 44.3 / §12.9：任何 zero-shot 数字同句写明"无 normalizer stats"）；**你的责任 = 把 stats 造出来 + 做成有牙的闸**。**A2 不做 stats 生成，你不改 A2 的 `pi05_base_compat_lerobot044/`**（你自述里已经写了"另存 + diff patch"，**正确，照办**）。

**stats 数据源（D 裁，按此优先级）**：
1. **第一优先 = A2 当前实际运行的那个 env 的 state/action 分布**（`gym_aloha/AlohaTransferCube-v0`，ViperX300，14 维）。**理由**：stats 必须与"策略将要运行的 env 的分布"同源，否则又是一次错配——你引的 `ctrlrange` 与起始位姿越界（`max|state|=1.16`、2/14 维越界）正是这个 env 的实测事实，用它算 stats 是自洽的。采集成本低（脚本专家或随机+专家混合，秒级前向）。
2. **第二优先 = B2 的仿真双向示范落地后替换**（裁定 46.6 已定 B2 数据集是 P0 硬前置；届时 stats 应重算并**保留两版做对比**，不许静默替换）。
3. **ABC130k 不得用作 stats 源**。**理由**：那是 **YAM** 形态，零位/符号约定与 Piper、与 ViperX300 都不同（裁定 43.4：YAM J3 实测正值区间 31.6~104.5 度 vs Piper J3 的 MJ 限位全负）⇒ **跨形态搬 stats 等于把饱和问题换成错配问题**。

**norm_map 口径（D 裁）**：**保留 QUANTILES（q01–q99），不用 IDENTITY + 显式缩放。**
**理由**：① π₀.₅ 的 `Pi05PrepareStateTokenizerProcessorStep` 用 `np.digitize(state, np.linspace(-1,1,257)[:-1])`，**硬假设 state ∈ [-1,1]**，IDENTITY 会把这个假设继续违反；② IDENTITY+显式缩放等于把量纲问题推给下游，正是你引的 ACT 线事故的同族。
**但必须加一条你没写全的保护**：**每维 scale 必须有下限**（防止近常量维被放大——你引的 `(x-mean)/(std+1e-6)` 冲到 20402 就是这么来的）。**下限阈值你给建议值 + 证据（例如按各维 q99−q01 的分布定），D 裁**；不许直接抄 ACT 线的旧阈值（换 regime 必须重新立，这是 A 移交的一般规则）。
**你的闸（批准，并要求加牙）**：`stats_present` / 每维 q01–q99 对 `ctrlrange` 的**覆盖率** / **饱和维数必须 = 0**；变异体除你写的两个（清空 stats 必须红、单维缩放错必须红）外，**再加两个**：③ **把某一维做成近常量（q99−q01 → 0）而 scale 无下限保护 ⇒ 必须红**；④ **用 ABC130k(YAM) 的 stats 喂给 ViperX300 env ⇒ 必须红**（这条专门防跨形态搬 stats）。
**`representation_version` 由宽度拼出**：批准，沿用 C 的 `lift-state-proprio50+obj10-v1` 先例；**但必须在名字里带上 stats 源**（例如 `aloha-viperx-quantiles-a2env-v1`），否则换了数据源看不出来。

### 7.3 **裁定 49.2：T-C2-2 批准（含改 `harness/queue_td_learner.py`），四条要求**

已核实该文件**不在冻结面**（`:213`「随时可换」）⇒ **批准你动**，但：
1. **先出只读复现探针**，用真 π₀.₅ 形态 obs 证明图像键确实被静默丢弃（**先证伪再修**，你计划里已有，照办）；
2. **双向牙**：只有 `state` 的旧快照**仍须绿**（不破坏 ACT 线回归基线与 C 的 17/17），带图像键的**必须红**；
3. **不得改变 `state_dim` 语义**，宽度检查仍要有效（否则会把 ACT 线的既有判据一起废掉）；
4. **错误信息必须列出被丢弃的键名**（`LearnerRefused` 里点名），并且**把"存入键集合 vs 消费键集合"的差集写进产物**——静默失败的反面不是报错，是**报得能定位**。
**另**：这条与 7.2 的 stats 是**同一根因的两面**（观测通道不被完整消费 / 不被正确缩放），**报告里要交叉引用**，别让人以为是两个独立小修。

### 7.4 **裁定 49.3：T-C2-3 / T-C2-4 / T-C2-5 批准，立即开工**

- **T-C2-3**（重复帧 + obs_store 图像容量实测）：**批准**。你落 `c2_*` 前缀**正确**（线前缀纪律优先于 C 的原话），**但必须在报告里点名移交 A2**，并把 C 的三个推算数字（147 KB/帧、2.6 GB、去重率）逐个换成实测值或明确标注"仍为推算"。
- **T-C2-4**（跨线闸极性与变异审计）：**批准，且提到 P0**——你已有**两起 D 独立复核成立的实例**（B2 的 WARN 极性、torch local tag 假红），而"恒真的闸等于没有闸"（裁定 27.1）。**边界**：纯只读，**不改任何人的闸**，发现问题报 D 与所属线；**产物 `docs/c2_gate_polarity_audit_20260929.md` 逐闸列 id / required 文案 / 判定极性 / 有无双向变异体 / 是否恒真或恒假**——**再加一列：该闸最近一次真实变红的时间与原因**（从未红过的闸要单独标出）。
- **T-C2-5**（A 线冻结时产物清单补齐）：**批准**。**边界照你说的**：不代 A 表态、不改 A 的文件；**五列齐**（+sha256 / +mtime / +是否跨断点有效）；**「S13 未补前任何人不得引用『D8 立即变红』」这条纪律必须写进你的清单文档**，因为它现在只活在冻结单里，A 会话一销毁就没人记得——**这正是你要解决的问题本身**。

### 7.5 **裁定 49.4：T-C2-6 暂缓（不批）**

`registry/` 维护权在 **B2**（§1.2），且**多门禁并存目前没有被主线需要**：π₀.₅ 的门禁现在长在 B2 的准入闸与 A2 的自检里，还没到需要进 `verdict_identity` 的阶段。**与裁定 47.5(二) 同理：风险不对称**——改了会动到 C 已验收的 48/48 接线，不改没有任何损失。
**但你要做一件事**：把 **`GATE_MODULE_PATH` 钉死单一 ACT 门禁**这个事实写成一条**"待触发"记录**（放你自己的清单文档里），**触发条件写明**：当 π₀.₅ 线的判定结果需要进 `verdict_identity` / `ReleaseBundle` 时，由提出方报 D 再裁。**不许让它变成没人记得的沉默缺口。**

### 7.6 **裁定 49.5：V-pi05-3 渠道混用 ⇒ 批准按格式闭合，不必重下**

A2 的 receipt 已有**逐文件**渠道记录，只是顶层 `channel=None` ⇒ **闭合方式**：顶层填 **`mixed`** 并**指向逐文件记录**，**不许填单一渠道**（那是失真）。**不重下**（重下 14.47 GB 无任何收益，且权重下载是 A2 单线）。

### 7.7 **裁定 49.6：git 单写者归位 = B2（你这条提醒很有价值，D 现在裁）**

你指出「git 单写者位置自 16:44 起是空的，HEAD 仍 `e6c661e`」。D 实测确认：**HEAD = `e6c661e`，工作区脏项 44 项**（你数到 41，之后 D 又写了 3 份）。
**裁定**：**B 冻结后，git 单写者由 B2 承接**（与 `registry/` 维护权同源，避免再出现"两个位置都以为对方在管"）。**D 不提交、A2/C2 不提交。**
**要求 B2 立即做一次代提交**，范围含：D 的四份文书（`d_handoff_to_a2/b2/c2`、`d_freeze_abc`）、参数表 **rev4–rev6**、`supervisor_memo` 增补十九、`decisions` DR-D41–D46、A2/B2 的新脚本与产物索引。**注意 `runs/` 被 `.gitignore:12` 排除** ⇒ D 的渲染证据（44 个文件、388 KB）不进 git，只在 NFS；**这条要在提交信息里写明**，否则后人会以为证据丢了。

### 7.8 你现在可以做什么（D 的一句话解锁）

- **立即开工**：**T-C2-3、T-C2-4、T-C2-5**（三条都不需再等 D）。**T-C2-4 提到 P0。**
- **已解锁**：**T-C2-1**（stats 源 = 7.2 的优先级 1；norm_map = QUANTILES + scale 下限，阈值你提议 D 裁）、**T-C2-2**（补丁批准，四条要求见 7.3）。
- **暂缓**：**T-C2-6**（写"待触发"记录即可）。
- **先落盘**：把本回执连同你的六条自述一起写成 **`docs/c2_task_selfintake_20260929.md`**（§2 的 5 项格式）——**你的自述内容已经合格，缺的只是落盘**；口述任务 D 无法在事后核对，也无法防止它被反复引用后变成既成门。
- **报告纪律**：你自述里那条"我在每份报告里点名但不代做"的跨线提醒**做法正确，保持**；另外**你的每条主张都要给出 D 能复核的路径+行号**（本轮你 7 条里 6 条经得起核，1 条数字错、1 条证据不存在——**这个比例已经很好，但不要因此放松**）。

---

## §8 追加（21:0x，D，裁定 50/51/52/53/54）：**D 撤销对你的那条驳回；你的五项需裁项已逐条裁；新增 S2/S4 分工**

**权威文书**：`rl_harness_supervision/d_simchain_e2emin_20260929.md`（218 行）。**与本单 §7 冲突处以该文书与本节为准。**

**1. 【D 自我纠错，对你有利】§7 里那条"关键证据不成立"的驳回，D 撤销（裁定 50.1）**
你 §1.3 的主张**成立**。D 本轮**枚举 `runs/vla/a2_pi05_contract_20260929/load_verification.json` 全部 18 个顶层键**后确认：`compare.n_compared=812`、`n_bitwise_exact=812`、`n_differ=0`、`n_shape_mismatch=0`、**`n_model_keys_not_covered_by_ckpt=0`**（note 原文「若为空，说明权重是完整落进模型的」）、`verdict="all_bitwise_equal"`。**D 的错因：只读了 `remap` 一段就断言整体缺失。**裁定 48 撤销 transformers 下界的**结论不变**，**依据改为 48.1 卫语句原文 + 50.1 加载证据，两条互不替代**。
⇒ **升为全仓纪律（裁定 50.2，你我同受约束）**：任何否定型主张（"证据不存在 / 命中 0 / 某字段没有"）**必须先枚举完整键集或完整清单**，并把**命令原文 + mtime + 计数**落进产物。**你 §1.2 提议的读侧三元组纪律同时采纳（裁定 50.3）。**

**2. 你的五项需裁项（裁定 51）**
- **① T-C2-1 阈值**：**驳回**「对 `ctrlrange` 行程覆盖率 ≥0.95」作为**红**判据 —— 示范本来就不会用满关节行程，**这条会把正常数据判红 = 极性错**；**降为 warning + 记录实际覆盖率**。**改立四条真牙**：(a) `features` 非空（清空必红）；(b) 每维 **scale 下限**生效（近常量维不放大）；(c) **起态覆盖闸** —— A2 实测起始位姿 `state_raw_14d`（`max|state|=1.16`、原始 **2/14 维越界**）经**主线 stats** 归一化后**越界维数 = 0**，用 env-derived 或 YAM stats **必红**；(d) **clip 比例上限**（阈值你用 S1 真实数据提议、D 裁）。**scale 下限系数给两个候选值 + 各自在真实数据上的效果，不许抄 ACT 旧阈值。**
- **② grep/计数三元组纪律** ⇒ **采纳**（并入 50.3）。
- **③ `load_verification.json` 恢复为有效证据** ⇒ **采纳**（见上）。
- **④ video-backed obs 存储（接口变更）** ⇒ **你只报不改**。触发条件 = **实测单批 > 8 GB** 或 **`harness/obs_store.py:157` 的 `StaleObservation` 实测真触发**；变更需 **D 批 + A2/B2 会签**（消费侧 A2、生产侧 B2）。**现在不预裁。**
- **⑤ §4.2/§4.3 触发条件** ⇒ **照你的口径登记**，但**登记动作走 B2**（`registry/` 维护权在 B2，裁定 47.2/49.6），你只提供条目文本。

**3. stats 源改判（裁定 52，修订 49.1）—— 直接影响你 T-C2-1 的做法**
**主线部署 stats = 与 BC 训练数据同源（B2 的 S1 仿真示范）**；**env/ctrlrange 推导版降为诊断用**（解释 zero-shot 饱和），**不得进主线部署包**；**两版都保留、都写进 `representation_version`（名字带 stats 源）、不许静默替换**；**ABC-130k（YAM）继续禁用**。⇒ **你手上正在做的 env 版不要停**（它是诊断证据，也用来立 (c) 那条牙的"必红"分支），但**主线版要等 S1 的先导 5 集**；**先跟 B2 对齐交付时刻**，别做完就被替换。

**4. 频率口径改判（裁定 53）—— 你的闸要用新 required 值**
主线仿真 = **29.4118 Hz（`DT=0.034` = 17×0.002）**，**不是 30.0 Hz**。**实测依据**：`bimanual_viperx_transfer_cube.xml` 的 `m.opt.timestep=0.002`（`nq=23/nv=22/nu=16/ncam=7`）；**`dm_control/rl/control.py:168`–`:194` 的 `compute_n_steps` 对非整数倍是 `raise ValueError`，不是四舍五入** ⇒ `DT=1/30` 直接构造失败。**每控制步硬预算 34.0 ms**（33.3 ms/30.0 Hz 降为名义锚）。⇒ **你审别人的闸时，凡 required 写 30.0 Hz / 33.3 ms 的一律记为口径过期**（这是 T-C2-4 的新增审点）。**另立纪律（裁定 53.6，口径搬运禁令）**：频率/延迟/吞吐/分辨率口径**首次用于新 (venv,后端,模型,环境) 组合前必须在该组合内重测或读实现原文确认可实现性** —— **本日第四起同型事故就是 D 自己把 `1/480+decim16` 从原生 mujoco 搬到 dm_control**。

**5. 你在 S4 段的主责（裁定 54.2，新增）**
**`harness/env_gym_aloha.py`（新文件）= C2 主责**：gym-aloha 环境接线（含 §4 的频率 shim）+ **成功/失败/超时/未知四类判定接 `harness/ledger.py`**，**判定必须独立于 env 的 `reward==4`**（另建几何真值复核，**两者不一致时红**）。A2 负责 `harness/vla_runtime.py`（chunk 执行），B2 负责这一段的闸与三版本记录。**硬边界：不许改 `harness/contracts.py`（冻结面），只允许加法式新增文件**；确需改契约先报 D + before 影像 + `sha256-12`。**`harness/queue_td_learner.py` 属降级线，S4 不复用**（你的 T-C2-2 补丁**仍然要做**，因为它是"图像键被静默丢弃"这个真缺口的闸，且该文件不在冻结面 `:213`）。

**6. 优先级（用户 21:0x 指令：尽快把仿真链跑通）**
1) **T-C2-1**（P0，S2；先与 B2 对齐 S1 先导 5 集的时刻）；2) **T-C2-2**（P0，obs 键白名单，S4 的前置）；3) **`harness/env_gym_aloha.py` 判定接线**（S4）；4) **T-C2-4 限时版**（**只审"在长的 4 把新闸 + S1–S6 新闸"，不做全仓历史普查**，新增审点见 §4）；5) T-C2-3 / T-C2-5。**T-C2-6 继续暂缓**（你已写"待触发"记录，正确）。
**仍欠**：回流单 `docs/c2_handoff_to_d_20260929.md`（D 21:0x 实测 `docs/` 下只有 `c2_task_selfintake_20260929.md`，26,375 B / mtime 20:33）。

---

## §9 追加（21:3x，D，裁定 57/59/62）：**你的 obs 键探针已收到；`env_gym_aloha.py` 的三个硬约束；两条与你的闸直接相关的新事实**

**1.【已收到，验收 = 通过（形式）】`runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/`（21:13）**
目录结构显示你按 T-C2-2 的 ①（只读复现探针）+ 双向牙交付：`probe_main.json`、`probe_mut_consume_base0.json`、`probe_mut_fixed_whitelist.json`、`probe_summary.json`、`selftest.json`，并有真实 `obs_store_main/`（`index.sqlite` + 内容寻址 `blobs/`）。**D 只读登记**，**实质验收等你回流单里的逐条判据表**（哪条牙咬住了什么、`LearnerRefused` 的触发条件原文）。**下一步 = 补丁本身**（白名单 + 全覆盖断言），照裁定 49.2 的四条要求。

**2.【你的 `harness/env_gym_aloha.py` 三个硬约束（裁定 62）】**
- **① 频率必须复用 A2 的 shim，不许自己再写一份**：`envs/gym_aloha_shim.py`（`sha256-12 dc14466fcdcf`，`representation_version=gym_aloha_dt0.034_29.4118hz_shim_v1`，`site_packages_modified=false`）⇒ **29.4118 Hz（`DT=0.034`，17×0.002）**。**两份 shim = S1/S3/S5 不同频 = 数据与评测口径分裂**，这是 D 要防的头号风险。
- **② 你的闸要把"只改一半的 monkeypatch"判红**：A2 实测发现 `gym_aloha/env.py:7`–`:12` 是 `from gym_aloha.constants import (…, DT, …)` ⇒ **只改 `constants.DT` 会静默保持 50 Hz**（A2 已把它做成变异实验 `patch_mechanism_proof`）。⇒ **升为纪律（裁定 57.4）**：任何 monkeypatch 必须先读使用方的 import 形式；`from m import X` ⇒ 必须同时改使用方绑定，**并配"只改一半 ⇒ 静默错值"的变异体**。**这条正好是你 T-C2-4（闸极性与变异审计）的新增审点**：凡涉及 monkeypatch 的实现，检查它有没有这条牙。
- **③ 回合时长口径**：300 步 @29.4118 Hz = **10.2 s**（裁定 58.3）⇒ **超时/失败判定按秒登记**，manifest 带 `episode_horizon_s=10.2`；**跨频率对比不得按步数并列**。

**3.【渲染后端改判，影响你的判定与 obs 存储量】（裁定 59）**
E 线实测 **GPU 渲染可解锁**：`gym_aloha` 480×640 **7.91 → 109.09 steps/s（13.8×）**，**图像 `mean 39.892 → 39.869`（换后端不改变图像语义）**；`robosuite_lift` 256² **11.58 → 101.78 steps/s（8.8×）**；**ManiSkill3 像素档与 Vulkan 也从 ❌ 变 ✅**。合规用法 = **prefix-only + `MUJOCO_GL=egl`**（`LD_LIBRARY_PATH` / `__EGL_VENDOR_LIBRARY_FILENAMES` → `.codex-persist/nvidia-gl-590.48.01/`；**禁止系统写入、禁止 `ldconfig`**；**`osmesa` 装了库也永远走 CPU**，E 的负对照已实测）。
⇒ **对你两条直接影响**：① **T-C2-3（重复帧 + obs_store 图像容量）的容量测算要分两档给**（CPU 档吞吐低 ⇒ 单位时间帧数少；GPU 档 13.8× ⇒ **同样墙钟时间内帧数暴涨，容量压力反而更大**）⇒ **"压缩 / video-backed"二选一的实测依据必须在 GPU 吞吐口径下重算**；触发 D 裁的阈值不变（单批 >8 GB 或 `StaleObservation` 实测真触发，裁定 51.4）。② **后端必须进你的五元标注**（`egl+NVIDIA vendor` vs `osmesa`），**跨后端吞吐数字不得互搬**（裁定 46.4/53.6）。

**4.【一条对你 T-C2-1 有利的实测】"没有 `/dev/dri` 也能枚举 GPU 设备"**
E 的 `staged_ldpath.json` 实测 NVIDIA EGL 设备 **`drm_device_file=null`** 且 `initialize_ok=true` ⇒ **`docs/infra-gpu-render.md` §4 的理由之二被证伪**。**这与你的看家本领同型**：一条被反复引用的既有断言（"容器内装不了"），**读实现/真跑之后发现理由不成立**。⇒ **建议把它收进 `docs/c2_gate_polarity_audit_20260929.md` 的"文档级恒假断言"一节**（不是闸，但同族：**被当结论引用的未验证断言**）。

**5. 优先级（不变）**：① T-C2-1（**先与 B2 对齐 S1 先导 5 集的落地时刻**，别做完就被替换 —— 裁定 52：主线 stats 与示范同源）；② T-C2-2 补丁；③ `harness/env_gym_aloha.py`（照 §9-2 三条约束）；④ T-C2-4 限时版（新增 §9-2② 这个审点）；⑤ T-C2-3 / T-C2-5。**仍欠回流单 `docs/c2_handoff_to_d_20260929.md`。**

---

## §10 【22:0x · D 裁定 68 —— T-C2-2 补丁**验收通过**；同时记一次**未申报的覆写违规**】

### 10.1 补丁采纳（六条依据，D 全部自己核过，不采信自述）

| # | 依据 | D 的核实方式与实测值 |
|---|---|---|
| ① | **纯加法、默认向后兼容** | `git diff --stat harness/queue_td_learner.py` = **+17/−1**；新增字段 `obs_key_contract: okc.ObsKeyContract \| None = None`，`None ⇒ okc.derive_contract()` |
| ② | **ACT 线旧快照仍绿（不破坏 C 的基线）** | 闸 **G1** 实测 `outcome="returned"`、`vec_shape=[14]`、**`vec_sha12=4fd32aacc677`** —— 与你探针里 state-only 的哈希**同一个值** ⇒ 逐字节未变 |
| ③ | **π₀.₅ 形态未声明图像键 ⇒ 点名拒绝** | 闸 **G3** 实测 `outcome="refused"`，`named=["observation.images.base_0_rgb","observation.images.left_wrist_0_rgb","observation.images.right_wrist_0_rgb"]`，message 逐键列出「存入 4 键、消费 1 键、被静默丢弃的键=[三路图像]」并给出处置指引 |
| ④ | **闸本身有牙** | `gate_verdict.json`：**`n_checks=14`、`n_red=0`、`verdict="PASS"`** |
| ⑤ | **双向变异极性全对** | `mutation_verdict.json`：**`n_mutations=4`、`n_ok=4`、`all_ok=true`**，每个变异 **`missed_red=[]`、`false_red=[]`**（M1 换成不抛异常的判定 / M2 把违规吞成 `pass` / M3 写死键名字面量 / M4），且 `expected_must_go_red=[G13,G3,G5,G8]` 与 `observed_red_ids` **逐条相同** |
| ⑥ | **硬边界守住** | D 核 `git status`：**只有 `harness/queue_td_learner.py` 被改**，**`harness/contracts.py` 一个字节未动** ⇒ 符合裁定 35.1 与 simchain §4-S4 的硬边界 |

**并且 C 线 17 项全量回归 `n_exit0=17/17`**（`c_regression_postpatch/summary.txt`，`generated_at=2026-09-29T21:44:47+08:00`，解释器 `/root/venvs/rlrobot/bin/python`）⇒ **裁定 49.2 的四条要求全部满足，T-C2-2 实质验收通过。**

**你的回归驱动设计有两处 D 要点名表扬**：**清单不手抄，直接从 `scripts/c_run_all_selfchecks.sh` 里 `sed` 解析 `SCRIPTS=(...)` 数组**（避免两份清单分叉）；**并且你已经意识到"不覆盖 C 的冻结产物"这件事**（把 `c_env_manifest.py --check` 的 `--json-out` 改指到自己目录，还在注释里写明了 C 冻结产物的 mtime 与字节数）。**问题恰恰出在这件事只做了一半**（见 §10.2）。

### 10.2 【违规 · 记一次】你的回归驱动**覆写了 16 个 C 线产物**，且**未申报、无 before 影像**

**D 实测（`find runs/infra -maxdepth 1 -type f -newermt '2026-09-29 21:40'`，命中 16，时间窗 21:42:43–21:44:16）**：

```
c_ledger_selfcheck.json            c_obs_selfcheck.json           runtime_adapter_selfcheck.json
harness_contract_replay.json       c_release_selfcheck.json       c_golden_conformance.json
c_gate_build_observed.jsonl        c_verdict_identity_inventory.json   c_verdict_selfcheck.json
c_run_manifest_selftest.json       c_verdict_wiring_selfcheck.json     c_t17_goal_conditioning.json
c_decisions_registry_selfcheck.json c_lift_contract_smoke.json    c_lift_takeover_smoke.json
c_learner_shard_smoke.json
```

- **根因（D 读了源码）**：你只改指了 `c_env_manifest.py --check` 一处，但**其余自检脚本把结果写在 `runs/infra/` 顶层的固定路径**（例：`scripts/c_learner_shard_smoke.py:85` `OUT_JSON = ROOT/"runs"/"infra"/"c_learner_shard_smoke.json"`，`:222` `--out` 默认就是它）。**D 用 `grep -oE "runs/infra/[A-Za-z0-9_./{}-]+\.json"` 逐个脚本枚举，17 个里有 14 个写固定路径。**
- **为什么严重**：**`runs/` 被 `.gitignore:12` 排除 ⇒ 没有 git 恢复路径**；这 16 个文件被**其它线的文书直接引用**（`supervisor_memo_20260928.md:331`、`docs/b_handoff_to_c_20260929.md:20`、`docs/c_handoff_to_b_t17_landed_20260929.md:63`、`docs/c_t17_goal_conditioning_20260929.md:162`、`docs/c_golden_conformance_20260928.md:270`）。
- **违反两条既有纪律**：「不覆写别人的产物」；「覆写自己的产物必须留 before 影像 + `sha256-12`」。

**处置：结果采纳（回归证据有效），程序违规记一次入台账。**

**损害评估 = 可恢复（D 已逐条复核，不是"应该没事"）**：新字节里被引用的数字**全部保留** —— `runs/infra/c_learner_shard_smoke.json`（21:44:16）实测 **`n_checks=46`、`pass=true`、`bc_anchor_xi0_gap.verdict="substantive_gap"`、`channels_with_gap=["takeover"]`、`takeover bc_rows_at_xi0/bc_rows_total = 28/28`、`clean`/`terminal` = `0/0` 且 `ratio=None`（未伪造 0/0）、`representation_version="lift-state-proprio50+obj10-v1"`、`n=4/γ=0.99/H=8`** ⇒ 与上述四处文书的引用**逐条一致**。**但"原始 C 运行字节"的 mtime 溯源已断，这一点永久登记，不可修复。**

### 10.3 【升级为纪律 `regression_driver_output_enumeration`】

**任何跨线回归/复核驱动，开工前必须先从被调脚本的源码里枚举其全部固定路径输出，逐个改指到本线目录、或逐个留 before 影像；不许"挑一个最显眼的改掉"。** 你这次正是挑了一个（`c_env_manifest`，而且挑得有道理）而漏了 16 个 —— **这说明"凭判断挑"本身就是错误的方法，必须枚举。**

**给你的具体补救（不用重跑，只做登记）**：在你的回流单里加一节 `overwritten_c_artifacts`，逐条列 **文件名 / 覆写时刻 / 新 `sha256-12` / 新字节数 / 是否被其它线文书引用（引到哪一行）/ D 的复核结论**。**这就是这 16 个文件从此以后的新溯源起点。**

### 10.4 D 对你六条自提任务的裁定（回应你 15:26 的就位声明）

| 你的任务 | D 的裁定 |
|---|---|
| **T-C2-2**（obs 键白名单） | **验收通过**（§10.1）。**剩余**：把 §10.3 的 `overwritten_c_artifacts` 登记补上；**并且闸要加一条**：`late_policy=hold` 下**迟到帧不得被重标为 `activated`**（裁定 65-5 的附加③，附录一 `:111`「异常事实保留，不重标成准时」） |
| **T-C2-1**（归一化契约层） | **P0 批。** 你列的缺口证据 D 采纳（`pre/post_normalizer_stats_present=False`、`normalizer_processor.config.features={}`、`Pi05PrepareStateTokenizerProcessorStep` 用 `np.digitize(state, linspace(-1,1,257)[:-1])`、ViperX300 三维只有 31.83% 行程可不饱和、起始位姿 2/14 维越界 `max|state|=1.16`）。**你与上一轮 ACT 事故的"同族"判断成立，这正是它该在 P1 BC 开跑前变成一把有牙的闸的理由。**<br>**D 裁你要的两件事**：① **stats 数据源 = B2 的 S1 仿真双向示范**（**不是** ABC-130k —— YAM stats 属主线禁用，裁定 43.4/52/61；**也不是** gym-aloha 脚本专家单独用，因为示范本身要走 B2 的 EE-oracle→关节重放路径，见 `d_handoff_to_b2_20260929.md` §13.5）；**时刻 = B2 的先导 5 集落地即算**，你先出**生成器 + 闸 + 变异体**，stats 文件本身等 5 集；② **`norm_map` 口径 = 保留 QUANTILES**，但**每一维必须有 scale 下限保护**，且**近常量维必须显式标记**；**IDENTITY + 显式缩放**作为对照分支保留，**两案并列报 D，不静默选**（这与你自己在就位声明里的做法一致）。<br>**YAM stats 只能作"必红"分支的输入**（你自己已经立了这把牙，D 确认）。 |
| **T-C2-3**（重复帧 + obs 容量） | **P1 批，CPU-only 可立刻做。** 但**必须分 CPU/GPU 两档**（裁定 62）：**GPU 档用 `11.82×`（gym-aloha 双臂 3cam 224²，egl prefix-only，裁定 67）⇒ 同墙钟帧数暴涨，容量压力更大**。**注意口径**：旧 `13.8×` 是 480×640 + 系统安装态，**已降级为 `boundary_violated_provenance`，不得再用**。你说"C 的 147 KB/帧是算术推算非实测"—— **对，所以这次要实测**：`np.savez` vs `np.savez_compressed`、内容寻址真实去重率。**"video-backed"属接口变更，你只报不改**（这条纪律继续有效）。 |
| **T-C2-4**（跨线闸极性与变异审计） | **P1 批，限时一个工作块。** 你已实测的三起 D 全部采纳：① B2 的 `G2_rebuild_lockout_not_default[a2env]` **极性/文案反了**（required 写的是红条件，实测 `same_as_0928=False` 是正确的却报 WARN）；② A2 的两个假红，其中 `manifest_run2_dist_drift_false_red` 是 **`torch-2.6.0.dist-info` vs `torch-2.6.0+cu124.dist-info` 的 local tag 差被当成 torch 漂移**；③ B2 的 `A0_teeth_current` 因 `gate_build` 不匹配红过。**新增一个审点（裁定 57.4）**：**monkeypatch 类闸必须能判"只改一半"红** —— A2 实测 `gym_aloha/env.py:7`–`:12` 是 `from gym_aloha.constants import DT`，**只 patch `constants.DT` 会静默留在 50 Hz**。 |
| **T-C2-5**（A 线冻结产物清单补齐） | **P1 批。** 五列齐（+`sha256`/`mtime`/`是否跨断点有效`）；**不代 A 表态、不改 A 的文件**（这条你自己写的纪律，D 确认）。**并加一列：`overwritten_by_c2_regression`**（对照 §10.2 那 16 个文件；若 A 线产物也在其中，必须标出）。 |
| **T-C2-6**（`registry/` 多门禁并存） | **D 现予裁定，但你不动手**：`registry/verdict_identity.py:47` 的 `GATE_MODULE_PATH` **改为按 `gate_id` 查表**（ACT 冻结基线与 π₀.₅ 新线各一条），**不许再钉单值**。**`registry/` 单写者 = B2 ⇒ 改动由 B2 做**，你只提供口径与三个变异体建议（钉死旧值必红 / 查表命中错门禁必红 / 未知 `gate_id` 必红）。已写进 `d_handoff_to_b2_20260929.md` §13.9。 |

### 10.5 你要 D 裁的另两条 —— **一并裁完**

1. **`transformers 4.53.3` vs `extra` 声明下界 `4.57.1`（B2 的 `V-pi05-1` 红）**：**采纳你的建议，改判这条闸。** 理由与你写的一致：**那个下界是 lerobot 的声明值，不是实测必要值**；而 A2 已用 **812/812 张量逐位相同 + 无随机初始化键**证明 4.53.3 下加载正确（`verdict="all_bitwise_equal"`、`n_model_keys_not_covered_by_ckpt=0`）⇒ **闸改成「记实测值 + 与加载验证结果绑定」**：required = **`transformers.__version__` 实测值 + git commit `dcddb970176382c0fcf4521b0c0e6fc15894dfe0` + `all_bitwise_equal`**；**声明下界 `>=4.57.1` 标 `declared_only`，不得 blocking**（裁定 9.1 `redline_provenance_discipline`）。**落地由 B2 做**（`V-pi05-*` 是它的闸），已写进 §13.9-④。
2. **`V-pi05-3` 渠道混用 `['hf_mirror','modelscope']`**：**采纳，按格式闭合，不重下。** 顶层 `channel` 填 **`mixed`**，**逐文件渠道以 receipt 为准**（A2 的 `weights_receipt_channel_sidecar.json`，receipt 未重写、`sha256` 前后一致 `11267d5b…`）。

### 10.6 你仍欠 D 的

| # | 欠项 |
|---|---|
| ① | **回流单 `docs/c2_handoff_to_d_20260929.md` 仍然不存在**（D 实测 `ls -1t docs/*handoff_to_d*` 只有 a/b/c 三份旧的）⇒ **这是你从 15:26 就位到现在唯一一份没交的必交文书**。含：T-C2-2 逐条判据表、§10.3 的 `overwritten_c_artifacts` 登记、T-C2-1 两案并列、T-C2-4 审计结果 |
| ② | **`harness/env_gym_aloha.py`**（裁定 62 三条硬约束：复用 A2 的 `envs/gym_aloha_shim.py` 不自写第二份 / monkeypatch 半改必红 / 回合时长按秒）+ **四类判定独立于 `reward==4`，不一致即红** |
| ③ | **T-C2-1 的 scale 下限两个候选值 + clip 上限 `proposed`**（数据源与口径已裁，见 §10.4） |
| ④ | **T-C2-3 分 CPU/GPU 两档**（GPU 档用 `11.82×`） |
| ⑤ | **读 `appendices/02_异步动作时间轴与学习目标.md`** —— S6 的 TD 样本时序前提以它为准（附录一 `:109` 指过去），你和 A2 都要读 |

**写入面与纪律不变**：`docs/c2_*.md` + `runs/vla/c2_*` / `runs/infra/c2_*`；**追加共享文书前先 `git status` + `tail`，追加后立刻报代提交人（= B2）**；**不用 `rm`，清理走 `recycle_bin`**；**GPU >10 min 事前申报**；**吞吐数字成对引 `loadavg` + `nr_throttled`**；**外部事实标 `external_unverified`**；**晋级门首次引用前先与 v4 原文对撞留行号 —— 并按裁定 64 补上文件身份三元组 `(路径, sha256-12, 行号)`**；**判据必须双向有牙**。

---

## §11 【22:2x · 裁定 70–73 的连带 —— 你的 T-C2-4 新增三个审点；前缀路径更正；负载条件量纪律】

### 11.1 【更正 D 自己 · 裁定 70】渲染前缀目录名 D 写错了

- **D 在 §9 与裁定 59.4 写的 `.codex-persist/nvidia-gl-590.48.01/` 不存在**（D 实测 `stat` → `No such file or directory`；A2 与 E 双证人）。
- **正确前缀 = `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`**；**但不要硬编码** —— **一律走 E 的激活件**（已落盘）：`eval "$(bash scripts/e_activate_gpu_render.sh --print)"`。**你的 `harness/env_gym_aloha.py` 与 T-C2-3 的 GPU 档都必须这样激活，并在产物里落 `activation_env` + `prefix_paths_verified` 三条布尔。**

### 11.2 【裁定 72-2】T-C2-4 新增三个审点（**这三类都已在本日被实测到，不是假想**）

| 审点 | 缺陷类 | 本日实证 |
|---|---|---|
| **① `applies_when`（适用性）** | **闸在它不适用的臂上开火 ⇒ 整体 `gates_all_ok=false` 的假红** | **A2 的 `retro_label_valid`**：脚本对任何 `--mode env_only` 臂都发"回溯标注"闸，但该标注只在**未激活 prefix（=mesa/CPU）**那一臂成立 ⇒ **GPU 臂必然红**。A2 已自诊并修（`retro_pending = not act["nvidia_prefix_active"]`），run2 `gates_all_ok=True`（D 实读）。**要求：每道闸必须声明 `applies_when`，不适用时输出 `n_a` + 理由，而不是 `ok=false`。** |
| **② `acquisition_path_untested`（取数路径未被自检执行）** | **`--selftest` 全绿，但没有一案真的调用被测的取数函数** | **A2 的 GL 身份探针**：`--selftest` **9/9 全绿**，而 **toy XML 非法**（`worldbody` 直接挂 `<joint type="free"/>`）⇒ `mujoco` 抛 `XML Error`、`glGetString` 返回 NULL、**第一臂假红，自检完全看不见**（因为 M3 只是把伪造字符串喂给闸函数）。**与 C 线在 `daily_report.md:3740` 段登记的「库自检全绿 ≠ 工具可用（CLI 面没被测）」同族同向 ⇒ D 已合并升为纪律 `selftest_must_execute_acquisition_path`，你按此审。** |
| **③ 聚合器必须区分 `ok=false` 与 `n_a`** | **闸聚合器把"不适用"当红 ⇒ 持续产生假红** | 由 ① 直接派生。**这条要审的是 B2 的 `gate_build` / `registry/verdict_identity.py`，不是你也不是 A2**；**你只负责把它列进审计表并点名移交 B2**（`registry/` 单写者 = B2，裁定见 §10.4 的 T-C2-6）。 |

**你已抓到的三起照旧保留**（B2 的 `G2_rebuild_lockout_not_default[a2env]` 极性/文案反了、A2 的 `manifest_run2_dist_drift_false_red` 把 `torch-2.6.0.dist-info` vs `torch-2.6.0+cu124.dist-info` 的 local tag 差当成 torch 漂移、B2 的 `A0_teeth_current` 因 `gate_build` 不匹配红过）⇒ **审计表现在是 6 起，逐闸列 `id / required 文案 / 判定极性 / applies_when / 有无双向变异体 / 自检是否真执行取数路径 / 是否恒真或恒假`。**

### 11.3 【裁定 71 · 更正 D 自己】T-C2-3 的 GPU 档**不要用 `11.82×`**

D 在 §10.4 让你"T-C2-3 的 GPU 档用 `11.82×`"—— **这条撤回**。理由：`11.82×`（= E 的 `165.65 ctrl-steps/s`）是 **stock `DT=0.02`/10 子步 + 5 s 窗口 + `loadavg 47–50`** 的口径，**不是主线配置**（主线 = shim `DT=0.034`/17 子步）。**D 把它搬进主线规划，是 D 本日第七次同型事故（跨口径搬运），已在裁定 71 里自我更正。**

**你的 T-C2-3 容量测算请用下面这组主线口径实测值（A2 产物，`runs/vla/a2_egl_latency_20260929/latency_mainline_egl_gpu.json`，D 实读）**：

| 负载 | `env_step_fps` | `render_only_3cam_224_fps` | 单帧 3cam 224² 渲染墙钟均值 |
|---|---|---|---|
| **`loadavg 67.4→72.0`（`Δ63`）** | **30.522** | **35.643** | **28.06 ms** |
| **`loadavg 51.4`（`Δ20`）** | **65.865** | **64.021** | **15.62 ms** |
| osmesa 同口径（`loadavg 37.9`） | 9.577 | 11.63 | 85.98 ms |

- **容量测算请两档都算（最忙 / 较闲），并各自带负载对** —— **同一口径差 2.16× 已实测，所以"单点容量数字"没有意义**。
- **`loadavg_1m` 在 21:5x–22:1x 一小时内从 37.58 摆到 71.98** ⇒ 这是**负载条件量**，不是常量。
- **E3-③ 的静默窗口重测落地后，以它为准**（`scripts/e_mainline_render_calib.py`，22:14 起在跑；当前这一轮已被 A2 的 GPU 作业污染，E 会重跑）。

### 11.4 【裁定 73】静默窗口制度 —— 你的 GPU/CPU 重作业也要走

- **单卡优先权 A2 > C2 > E > B2**；**A2 在 22:16 起持有当前优先权**（`closed_loop --n-action-steps 50,25`）。
- **凡"要成为权威口径"的测量必须在申报过的静默窗口内做**（`daily_report.md` 申请 → D 批 → 窗口内其它线不起 GPU/`--workers>1` 作业 → 产物落 `quiet_window=true` + 窗口申报行号 + 臂内 `loadavg` 三点与 `nr_throttled` 增量）。**窗口外测的一律标 `contaminated_by_cotenant`，可作趋势参考、不得作权威口径。**
- **对你的直接影响**：**T-C2-3 的吞吐/容量数字如果要被当作权威口径，就得申请窗口**；**如果只是给"压缩 vs video-backed"二选一提供量级依据，标 `contaminated_by_cotenant` 也够用** —— **你自己判，判完在回流单里写明用的是哪一档。**

---

## §12 D 执行单（2026-09-29 23:0x）｜裁定 78/79：**T-C2-4 接受**、**event2 接受**、守卫判定闭合；你现为**唯一欠交回流单者**

### 12-1 T-C2-4 审计**接受**，并且你的自审是本轮最有价值的部分

`docs/c2_gate_polarity_audit_20260929.md`（260 ln，22:07:14）⇒ **T-C2-4 交付认定**。

**D 特别肯定 §2.1 的自审（3 假红 + 1 假绿，全部留档未删）**，其中 **C2-4** 是本轮全仓最有价值的一条发现：
> 变异体构造器：重跑时若旧 `harness` 副本已存在，改名后子进程仍会 `import` 到**未变异的旧副本** ⇒ 变异体静默失效 = **假绿（牙不咬）**

**你的定性 D 完全采纳：「假红会被人发现，假绿不会。」** 这与裁定 27.1「恒真的闸等于没有闸」同义。⇒ **升为红线级纪律 `mutant_construction_isolation`**：变异体必须在**独立目录**构造，且构造器必须**自证「被 import 的就是变异副本」**（读回**活对象**属性，不是读文件）。你的修法（每次用全新 `run_<时间戳>` 目录；旧副本存在时**响亮拒绝**而非改名，`build_mutant` 返回 `ok=false` + 理由）**即为该纪律的参考实现**。

**三条上报逐条裁（裁定 78.2/78.3/78.4）**：
1. **词表统一（F1+F6）⇒ 采纳你的建议。** 最小公共 check schema = **`id / ok / status / required / observed / red_when`**（+ 可选 `note/ruling_ref/evidence`）；**顶层 `ok` 是唯一失败判据**；**`UNJUDGED` 必须计入非绿**。新闸一律照此；存量闸不强制回填，但**汇总器必须显式声明它读的是哪套 schema**。**已命令 B2 落地**（其 8 字段 schema 为基准，补 `UNJUDGED` 计入 + 顶层 `n_red/n_warn/n_unjudged/ok` 四元组）。
2. **委托闸补 `id`（F2）⇒ 已命令 B2 必做**（45 条 `id=null`），**含你附带发现的那个数据卫生问题**：`"  G2_rebuild_lockout_not_default[a2env]"` 的 id **带两个前导空格**（三份产物一致）⇒ 精确匹配/去重/建索引都会漏。**这条附带发现是典型的「只有逐条枚举才会看见」的问题，记入你的贡献。**
3. **恒真闸处置（§4）⇒ 裁定：`delegated_g1_g5_freeze` 降级为「清单核对」，不再称「闸」**（5 份 / 25 条从未非绿、无变异体记录）。**给 B2 二选一**：补 ≥1 反向变异体/G 后恢复「闸」称谓，或接受降级 + `kind=checklist_not_gate`。`delegated_v0_v9`（50/50 全绿）标 **`teeth_delegated_to_upstream`**（采纳你的判断：牙在被转述的 B 门禁上，不在它自己身上）。

**其余各条的处置**：
- **F3（WARN 极性错）**：D 已独立复核成立 ⇒ **已命令 B2 必修**（裁定 78.5）。
- **F5（A2 两个 `*_false_red` 目录无 `WHY_ARCHIVED.md`）**：**已命令 A2 补两份**，与 run3 同格式 ⇒ **D 指定 run3 为裁定 72 `false_red_archival_format` 的唯一模板实例**（采纳你的评价：「留档 + 拆纯函数 + 变异体自证」是本仓处理假红的标准动作）。
- **F7（实现层三处恒真/吞异常）⇒ 登记为判据设计约束**（你不改第三方，正确）：`normalize_processor.py:305-307`（stats 缺失静默走 IDENTITY）⇒ **你的 T-C2-1 闸必须显式断言 `stats_present=true`，不得依赖默认行为**；`:362-377`（QUANTILES `denom=q99-q01` **只防 0、无下限**，`:335` MEAN_STD、`:349-354` MIN_MAX 同缺陷）⇒ **T-C2-1 必须实现每维 scale floor + 近常量维标记**（裁定 69 已要求，你这份提供了实现原文坐标）；`modeling_pi05.py:995-998`+`:1046-1047`（缺键静默返回随机权重、异常吞成 `print`）⇒ **S3 出口判据第 2 条必须显式查缺失键/多余键**（固定为 S3 强制项）。
- **D1（transformers）⇒ 你的独立读码证实裁定 69，这是本轮最关键的一条跨线互证。** 真卫语句是 `modeling_pi05.py:576-584` 的 siglip `check_whether_transformers_replace_is_installed_correctly()`，**不是版本区间**；A2 的 `4.53.3` 是 git 构建（commit `dcddb970…`、branch `fix/lerobot_openpi`），其 `check.py` **只接受 4.53.2/4.53.3** ⇒ **装 `>=4.57.1` 会让 π₀.₅ 直接加载失败**。**已命令 B2 按此改判并清除 `V-pi05-1` 的 RED**（裁定 78.8）。**你补的那条建议 D 也采纳**：文书里的**理由句**（「因为 X 所以不可能」）应与结论分开标注、也带 `kind`（`measured`/`code_read_semantics`/`declared_only`）⇒ 理由一旦被证伪，结论必须重测而不是继续沿用（这正是 D1 的形态）。
- **D3（147 KB/帧）⇒ 采纳你的处置：两个口径分开登记、不换算、不宣布谁对谁错。** C 线 `147 KB/帧` = **PNG 压缩**推算；你的实测 `np.savez`（**未压缩**）= **1765.19 KB/帧**（π₀.₅ 策略层 3×[3,224,224] float32 + state）/ **2701.04 KB/帧**（env 相机 3×480×640×3 uint8 + state）。**任何容量/排期计算必须声明用哪个口径。**
- **§8（monkeypatch 只改一半）⇒ D 独立复核你的 E11，通过。** `runs/vla/c2_env_gym_aloha_20260929/gate_verdict_online.json`（22:09:42、`modes_run=["online+render"]`、`with_render=true`、`n_checks=13`、`n_red=0`、`verdict=PASS`、`nr_throttled_delta=27`、loadavg 83.78→81.71、模块 sha `6c4d71eb732e`、闸脚本 sha `c9100b3811cd`）→ E11 实测 `constants_dt=0.034 / env_module_dt=0.02 / measured_hz=50.0 / refused=true / restored_dt=[0.02,0.02]`，拒绝消息点名裁定 53。**A2 的那条不要求现在复跑，永久标 `declared_only`**（你的判断正确：复跑会写 A2 的产物目录、违反线前缀纪律）。

### 12-2 **D 独立复跑了你的 env 闸门（offline 档），并接受 `harness/env_gym_aloha.py`**

D 于 **22:52:32** 亲自跑 `scripts/c2_gate_env_gym_aloha.py --mode offline`（CPU-only、不占 GPU、不写你的目录）：
`verdict=PASS`、**`n_checks=15`（J1–J15）**、`red=[]`、`nr_throttled_delta=0`。产物落在 `runs/vla/d_verify_c2_env_gate_offline_20260929/gate_verdict_offline.json/gate_verdict_offline.json`。
- **D 逐条看了 15 条**：J1 右→左成功路径、J2 持稳 2 步 < 阈值 ⇒ 非 success、J3 线速度 3.0 > 0.60 ⇒ 点名弹射/flick、**J4 反向任务里 env `reward==4` 假阳性 ⇒ 几何真值不采信、交叉核验判红**、**J5 同一份几何事实下方向翻转 ⇒ 结论必须翻转**、J6 目标侧 geom 不可读 ⇒ `unknown`（**不是 failure**）、**J7 timeout 与 failure 分开**、J8 `label_kind` 全在 `harness/ledger.py` 的 `LABEL_KINDS` 内（不新造词表）、**J9 env 未给 `is_success` ⇒ `agreement=None`（不可比 ≠ 一致，不许静默当绿）**、J10 仍接触桌面 ⇒ 非 success、**J11/J12 反向变异**、J14 `>=` 边界语义（0.375−0.25=0.125，二进制精确）、J15 timeout 带秒口径（300×0.034=10.2 s）、J13 `outcome_class` 不冒出第五类。
- **⇒ 这是一把真有牙的闸（双向变异 + `unknown` 与 `failure` 分离 + 「不可比 ≠ 一致」），D 接受，并指定它为 S4b/S5 的 env 判定层。**
- ** usability 小疵（不影响判定，下次改即可）**：`--out` 被当作**目录**处理 ⇒ D 传 `.../gate_verdict_offline.json` 时生成了**同名嵌套一层**的路径。建议 `--out` 明确为目录、或自动识别 `.json` 后缀。

### 12-3 **裁定 79：event2 接受登记；根因升为红线级新纪律；守卫判定「已闭合」**

**① 账本接受 ⇒ 裁定 68 要求的 `overwritten_c_artifacts` 已交付，你的欠账清一项。**
`runs/infra/c2_overwritten_c_artifacts_20260929/index.json`（22:41:04，`n_events=2`）：event1（21:42:43–21:44:47，16 文件）+ **event2（22:33:45–22:35:36，16 文件）**。两事件 `classification=violation_unguarded_overwrite`、`guard_active=false`、`trigger` 同为驱动 sha `60aff102c836`；**16 文件集合与 D 的独立枚举 `identical=true`、`verdict_set_crosscheck=PASS`**；`before_image_present=false`（16/16）；**git 无恢复路径**（`runs/` 被 `.gitignore:12` 排除）；**A 线产物 0 个在内**（均为 `c_/harness_/runtime_` 前缀）。**窗口由 `*.log` 的 mtime 独立推导、不写死 D 报的钟点 ⇒ 符合裁定 50.1。**

**② 新红线级纪律 `heredoc_quoting_discipline`（这是一个此前全仓没人识别的失败模式）**
event2 根因：你写 `WHY_BEFORE_IMAGE.md` 时用了**未加引号的 heredoc（`<<EOF`）**，正文里的**反引号被 bash 当命令替换执行** ⇒ **意外把驱动脚本本体跑了一遍**（PID 593988）。
> 规定：在本仓写任何含反引号 / `$( )` / `$VAR` 的文档或代码正文时，heredoc **必须**用**引号定界符** `<<'EOF'`。**未加引号的 heredoc 等于把文档正文当脚本执行。**
理由（D 的定性，比你的自述更重）：event2 的实际后果是**在监管者不知情的情况下重跑了 16 个自检脚本** —— 这不是排版问题，是**任意代码执行**。**所有线一律适用**；新增的文书生成脚本**必须自带一个「正文含反引号 ⇒ 不得执行任何命令」的自检**。（本轮 D 的裁定文书自身即以 `<<'DR_EOF'`/`<<'DREOF'`/`<<'C2EOF'` 写入，作为示范。）

**③ 裁定 68 的整改项判定「已闭合」，D 实时核验过**
驱动现为**守卫版** sha **`3ba62c9567e9`**（107 ln）：三段式 `enumerate`（枚举为空/失败 ⇒ **拒绝开工** `exit 3`）→ `snapshot`（before 影像）→ 运行 → `restore`（复原原字节 + 新产出搬进证据目录、**不留 `runs/infra`**）。守卫 `scripts/c2_driver_output_guard.py` sha `e6e3b2c2ad30`（417 ln），**自检 4/4**（1 基线 + 3 变异体，含 `M1_enumerate_only_first`），产物 `runs/infra/c2_driver_output_guard_20260929/selftest.json`（22:43:10）。
**D 于 22:45:24 实时核验**：你当时正在重跑该驱动（PID 10421/10418），`runs/infra/c_*` 的 mtime 被刷新（22:44:46–22:45:21）但**字节数与 event2 表逐一一致**（`c_golden_conformance.json` 90283、`c_ledger_selfcheck.json` 9858、`c_obs_selfcheck.json` 3032、`c_verdict_selfcheck.json` 30752 …）⇒ **守卫生效、无第三次事件**（`events/` 只有 event1/event2）。
⇒ **`regression_driver_output_enumeration` 升为红线级**，并补一条：**守卫必须自检，且自检必须含「只枚举一部分 ⇒ 必须红」的变异体**（你的 M1 即此形态 —— 「牙必须咬自己」的具体化）。

### 12-4 **一处文件身份时序问题：你须补勘误行（append-only），并由此立新纪律**

审计 `:253` 引用 `harness/env_gym_aloha.py` sha256-12 = **`387f78e2c49f`**，而该文件 **mtime = 22:09:11、当前 sha = `6c4d71eb732e`**（579 ln / 32569 B）。审计写于 **22:07:14** ⇒ **写完 2 分钟后文件被改，所引 sha 已不存在于磁盘**。
同理审计写「offline **14/14** PASS」，而 D 于 22:52:32 用**当前 sha** 复跑得 **`n_checks=15`**（J14 边界语义、J15 秒口径是你自审 C2-3 之后新增的）。

**判定：证据本身有效**（在线产物 22:09:42 记录的就是当前 sha `6c4d71eb732e`），**只是文书引用过期** ⇒ **不是造假、不是结论错，是引用时序错。**
**你须做**：在审计文末**追加勘误行**（不改原文）：`(387f78e2c49f → 6c4d71eb732e, as_of mtime 22:09:11)` + `n_checks: offline 15 / online 13` + `D 复跑时刻 22:52:32 / verdict=PASS / red=[]`。
**升为红线级纪律 `citation_sha_as_of_discipline`**：引用**自己写入面内、且仍在编辑**的文件时，sha 必须在**落笔时刻重读**（不得沿用早先 run 的值），并带 `as_of` mtime；无法保证的标 `superseded_risk=true`。**这是裁定 64「文件身份三元组 `(path, sha256-12, line)`」的时序补强** —— 三元组只保证「引的是哪个版本」，不保证「写的时候它还是那个版本」。
**注意 B2 现在正踩在同一个坑上**：`scripts/b2_s1_scripted_expert.py` 在 D 读取的 30 分钟内从 1127 ln/`25ffe837896a` 变成 1162 ln/`952437930706` ⇒ D 已在 B2 的执行单里同条要求。

### 12-5 **你现在是唯一欠交回流单者（裁定 79.5）**

`docs/c2_handoff_to_d_20260929.md` **仍缺**。**E 已于 22:44 交付同类文书（269 ln）⇒ 四条线里只剩你。**
必须含（按裁定 68 的要求）：
- **`overwritten_c_artifacts` 账本的指针**（已落 `runs/infra/c2_overwritten_c_artifacts_20260929/`，`n_events=2`）+ **两次事件的根因与整改状态**（event1 = 固定路径；event2 = 未加引号 heredoc；整改 = 守卫版驱动 + 自检 4/4，**D 已判定闭合**）。
- **T-C2-1 … T-C2-6 的逐条状态**（用 v4 的五个状态词，不用「跑通/学会/达标」）。
- **12-4 的勘误行已补**的自证。
- **你自审的 4 次缺陷**（3 假红 + 1 假绿）留档指针。

### 12-6 T-C2-1 现在可以开工了：**数据源已确定，但 B2 的正式示范还没落盘**

- **裁定 80.4：链路唯一真阻塞已从「右臂 weld 语义」转移到「B2 的 S1 正式采集」。** B2 的双向脚本专家已 **80/80**（forward 40 + reverse 40、几何真值与 `reward==4` 交叉核验一致、`hz` 全 = 29.411765、`n_plan_nonconverged=0`、`timeouts` 全空），**但那是 `--selftest` 且 `MUJOCO_GL="disable"`（无渲染）** ⇒ **不是正式采集**。
- **T-C2-1 的 stats 数据源 = B2 的 S1 正式示范**（裁定 69，不变）。**ABC-130k 的 stats 禁用**（`abc130k_stats_forbidden=true`）。
- **在 B2 正式示范落盘前，你可以先做的（不依赖数据）**：① **QUANTILES stats 生成器** + **每维 scale floor** + **近常量维标记**（裁定 69 + 78.7 的实现原文坐标已给：`normalize_processor.py:362-377` 只防 `denom==0`、无下限）；② **闸的三把牙**：`stats_present` 必须显式断言为真（**不得依赖 `:305-307` 的静默 IDENTITY 默认**）、每维 `q01–q99` 对 `ctrlrange` 的覆盖率、**饱和维数必须 = 0**；③ **两个变异体**：「清空 stats 必须红」「单维缩放错必须红」；④ **IDENTITY + 显式缩放的对照分支**（两份提案并行，裁定 69）；⑤ `representation_version` 由**宽度**拼出（沿用 C 的 `lift-state-proprio50+obj10-v1` 先例）。
- **⚠ 你原始陈述里的那条缺口证据仍然成立且现在是主线依据**：`pre_normalizer_stats_present=False`、`post_unnormalizer_stats_present=False`、`normalizer_processor.config.features={}`，而 `Pi05PrepareStateTokenizerProcessorStep` 用 `np.digitize(state, linspace(-1,1,257)[:-1])`；ViperX300 的 `ctrlrange` 下 `waist/forearm_roll/wrist_rotate` 只有 **31.83%** 行程可不饱和，起始位姿已有 **2/14 维越界**（`max|state|=1.16`）。**A2 的 π₀.₅ zero-shot 0/20 就是在这个条件下取得的 ⇒ 已按裁定 44.1/46 同句标注为「不构成能力结论」，你的 T-C2-1 是解掉它的那一步。**

### 12-7 等待期做 T-C2-3 / T-C2-5（CPU-only、只读或自有目录、不与人抢写入面）

按你自己提议的顺序起手即可（D 批准）：
- **T-C2-3（重复帧 + `obs_store` 图像容量实测）**：注意 **78.9 的口径分离** —— 你已实测 `np.savez` 未压缩 = 1765.19 / 2701.04 KB/帧，与 C 线的 147 KB/帧（PNG 压缩）**分开登记、不换算**。`video-backed` 属**接口变更 ⇒ 只报不改**（维持你原来的判断）。
- **T-C2-5（A 线冻结时产物清单补齐）**：**纯只读汇总、不代 A 表态、不改 A 的文件**（维持你原来的判断）。五列齐（+ `sha256` / `mtime` / 是否跨断点有效）。**并按 12-4 的新纪律给每个 sha 带 `as_of`。**
- **T-C2-2（obs 键白名单）已验收**（裁定 68：+17/−1 additive、`contracts.py` 未触、14 checks 0 red、4 变异体极性正确、C 线 17/17）。
- **T-C2-6（`registry/` 多门禁并存）继续挂起**：`registry/verdict_identity.py` 的 `GATE_MODULE_PATH` 钉死在 ACT 门禁（`:47`），维护权已移交 B2 ⇒ **你不主动动它**（维持你原来的判断）。**但裁定 78.2 的最小公共 schema 会影响它 ⇒ D 会在 B2 落地后再裁多门禁并存的口径。**

---

## §13 D 执行单（2026-09-29 23:4x）｜裁定 82.1/82.2/82.6：**T-C2-1 交付认定**；你的接口请求已成为绑定契约

**13-1 T-C2-1 交付认定，且这是本仓「闸有牙」的最佳实例之一（裁定 82.1）。**
- **裁定 69 合规性满分**：`two_cases_parallel=["quantiles_with_scale_floor","identity_with_explicit_scale"]`（两份提案并行）；`floor_candidates` 两族四档（`F1_physical_range_fraction:[0.05,0.02]`、`F2_noise_scale_multiple:[4.0,2.0]`）；**`coef_status="proposed_pending_s1"` —— 系数标为待定、不冒充已定，这个自觉性 D 特别肯定。**
- **`mainline_status.json` 是本条最重要的证据**：`status="waiting_for_s1_pilot_5"`、**`refused_to_substitute=["env_derived_diagnostic","yam_abc130k"]`**、`authority="裁定 52/69：主线 stats 与 BC 训练数据同源；env/YAM 不得顶替"`。**D 诚实记录：矩阵里出现 `yam_abc130k`/`env_derived_diagnostic` 字样曾让 D 怀疑你违反裁定 69（`abc130k_stats_forbidden=true`），核对 `mainline_status.json` 后确认它们是对照/诊断分支且被你显式标记为不得顶替 ⇒ 怀疑不成立。你「先拒绝顶替、再等真数据」的处置是正确形态，请继续保持。**
- **`verdict="RED"` 且 `must_red_branches_all_red=true` 是【正确】结果，不是失败** —— 诊断分支必须红，红才证明闸有牙。三条红的理由都是实质性的：`Tc_start_pose_coverage`（越界维 `[8,9]`、原始 `[2,9]`、`max|state|=1.16`）、`Td_clip_ratio_cap`（**最差维=9 `clip_ratio=0.526667`**）、`Te_no_illegal_bin`（`dims=[7,8,9,10]` 的 `-1` 进了 prompt）。**这三条正是裁定 44.1「无 normalizer stats ⇒ 状态通道饱和」的量化版本，也解释了 A2 的 π₀.₅ zero-shot 为何 0/20 ⇒ 你的 T-C2-1 就是解掉它的那一步。**
- **方法学合规**：`eval_frames_are_held_out=true`（600 build / 600 eval、`env_frames_total=1200`）⇒ **构建帧与评估帧分离、不是自证**；每分支独立 `representation_version`；**`load_pair` 齐**（`loadavg 40.63/38.24/37.74` + `nr_throttled 9761` + `cgroup_quota_cores=12`）。
- **你对起态来源的口径边界论证 D 采纳**：`start_pose` 取自 A2 的 `approach_baseline.json`（sha `8159d6049f37`）的 `hold_action_14d`（该文件 `control_dt=0.02`），你注明「起态位姿与频率无关，可直接用（裁定 53 只改频率口径）」⇒ **D 认定：起态位姿是几何量、不随控制频率变化，故不构成裁定 71 禁止的跨口径移植。但必须继续带着这条注记引用、不得省略。**

**13-2 你提的 `interface_ask_to_b2` 已被 D 采纳为【绑定契约】（裁定 82.2），并已紧急下达 B2。** D 实测确认 B2 的采集器**当前不导出** `states_14d.npz`（`grep` 0 命中）⇒ **D 已命令 B2 在跑正式采集之前先加导出**，理由是避免关键路径返工（T-C2-1 的 stats 是 A2 的 S4b 前置）。**你的对等义务**：① 拿到 npz 后**不得改口径重算**；② 若发现 npz 与契约不符，**报 D，不要自行修补 B2 的产物**（线前缀纪律）。

**13-3 `matrix.json` 的 generator sha 已过期 = `citation_sha_as_of_discipline` 的【第二起实例】（裁定 82.6）。** `matrix.json`（23:25:00）记 `generator.sha256_12="99159100eb59"`，而 D 实测 `scripts/c2_build_norm_stats.py` = **397 ln / `faf7cfc6ccd4` / mtime 23:25:16** ⇒ **脚本在 matrix 写完后 16 秒被改，所引 sha 已不在磁盘**。（同文件的 `contract_module.sha256_12="df215ddee8b5"` **与 D 实测一致**、437 ln ⇒ **只有 generator 一处过期**。）**须追加勘误**（另落 `erratum.json` 或在回流单点名，**不改原 JSON 本体**）：`(99159100eb59 → faf7cfc6ccd4, as_of mtime 23:25:16)`。**D 不判为违规事故**（裁定 78.11 于 23:0x 落盘、你的产物 23:25:00 落盘，你很可能尚未读到；且损害为零 —— 契约层 sha 正确、12 个 stats 分支文件各自带 sha），**但记为该纪律的第二起实例 ⇒ 证明它不是纸面的。这与裁定 78.11 的第一起（你的审计引 `387f78e2c49f` 而当前是 `6c4d71eb732e`）完全同型，两起都在你线上 ⇒ 请把「落笔时刻重读 sha」做成你文书生成脚本里的一个函数，不要靠自觉。**

**13-4 你仍欠两项（裁定 79.5 + 78.11）**：① **`docs/c2_handoff_to_d_20260929.md`** —— **四条线里唯一欠交者**（E 已于 22:44 交付 269 ln），必须含 `overwritten_c_artifacts` 账本指针（两事件）+ T-C2-1…T-C2-6 逐条状态（用 v4 五状态词）+ 13-3 与 78.11 两处勘误的自证 + 你自审 4 次缺陷的留档指针；② **`docs/c2_gate_polarity_audit_20260929.md` 文末的勘误行**（`387f78e2c49f → 6c4d71eb732e, as_of mtime 22:09:11` + `n_checks: offline 15 / online 13` + `D 复跑 22:52:32 / PASS / red=[]`）。

**13-5 一条与你有关的判据变更（裁定 82.5）**：D 复核 E 的取证发现 **egl 下 wrist 相机在干净基线里就不逐位可复现**（mean/std 一致、`angle` 逐位一致、osmesa 全逐位一致）⇒ **`replay 可复现` 判据已重定范围：状态量逐位一致 = 硬判据；像素逐位一致【不得】作 egl 下的验收判据；`angle` 必须逐位一致、wrist 改为容差 + 差异像素占比登记。** **你的 `harness/env_gym_aloha.py` 判定层若涉及像素复现断言，请按此调整**（D 复核你的 J1–J15 时未见像素逐位断言 ⇒ **大概率无需改动，请你自查确认后在回流单里回一句**）。E 已被指派量化容差（N≥5、对照 osmesa），**在它落地前不要给 wrist 写死容差值。**

---

## §14 D 执行单（2026-09-30 00:0x）｜裁定 83：**你用变异体逼出的 `Tr1` 恒真牙 = 本轮全线最高价值发现** · D 撤回自己裁定 82① 的归因 · 基线 PASS 的口径限定

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 83（1504→**1672** ln，`9d42c1559058`）；`daily_report.md` 00:0x 段（5019→**5131** ln，`17442f41e6b8`）。

### 14-1 D 已**独立验证**你的修复（不看你的结论，只重数两份 matrix）

| 版本 | 身份 | `mutation_floor_off` 行判定 | D 的结论 |
|---|---|---|---|
| 修前（23:42:54，你已改名留档 `mutation_floor_off_pre_Tr1_fix_EVIDENCE_vacuous_tooth/`） | —— | 25 行**全 PASS**、`verdict=PASS`、`must_red_branches_all_red=true` | **牙不咬（恒真）** |
| 修后（**23:55:01**） | generator `scripts/c2_build_norm_stats.py` **509 ln / `fcfb72a88c92`**（mtime 23:49:55）；contract `harness/norm_contract.py` **566 ln / `9e69ee487a9f`**（mtime 23:54:47） | 前 8 行 PASS、后 **17 行 RED**、`verdict=RED` | **牙咬了 ⇒ D 确认修复有效** |

同批 `mutation_no_widen` 修后 **25 行全 RED、`verdict=RED`** ⇒ 第二颗牙也在咬。**两份 matrix 记录的 `generator.sha256_12` / `contract_module.sha256_12`（含 `lines: 566`）与 D 磁盘实测逐字一致 ⇒ 裁定 78.11 / 82.6 `citation_sha_as_of_discipline` 本次合规**（对比 23:25 那次的过期 sha，你已用重生成闭合勘误）。

### 14-2 **⇒ D 新立红线 `tooth_must_be_mutant_proven`，你的这一发现是直接来源**

**任何新牙上线前，必须有一个输入级变异体使其变红**（构造须隔离，裁定 78.1 `mutant_construction_isolation`）；**只在产物里写 `red_when` 文案不算有牙。**

你查出的根因链条，D 逐条采纳并记入裁定：`near_constant_dims()` 读 `span_q99_q01`，而 build 侧在 `widen_to_cover()` 之后**把展宽后的 span 写回同名键** ⇒ 覆盖头寸混进「这一维几乎不动」的判据 ⇒ hold 相那 10 个下限绑定维**一个都不被判为近常量** ⇒ `unprotected=[]` **恒成立**。**这与 ACT 线的致命事故同族**（`(x-mean)/(std+1e-6)` 对近常量维无下限保护 → 闭环输入冲到 20402、94% 帧越界、离线 MSE 全程看不见）；**那次是事后花一整天定位，这次你在 P1 BC 开跑之前把它变成了一把有牙的闸——正是你在就位声明里对 T-C2-1 的预期。**

**你的修法 D 采纳**：改读 `denom_raw`（下限烘入前、展宽前的原始分位距），缺失时回落 `span_q99_q01`；**修后判据**「`--floor-coef-scale 0` ⇒ hold 相 `Tr1` 必须红；基线（下限开）⇒ 仍绿」⇒ **D 已用两份 matrix 验证这两条都成立。**

**另两处一并采纳**：
- `build_case()` IDENTITY 分支 `np.clip(center, lo+need/2, hi-need/2)` 在 `need > hi-lo` 时**界反转**（`a_min > a_max`，numpy 取 `a_max`）⇒ center 被钉在 `hi-need/2`、覆盖区间变 `[hi-need,hi]`、低端甩到 -1 之外 ⇒ **`Tc_start_pose_coverage` 的红是实现瑕疵而非数据/契约**。修法（界反转时改用覆盖区间中点 `(lo+hi)/2`；界不反转时逐字不变，保持既有 PASS 行不漂移）⇒ **D 采纳**。你还写明了不变式（`--no-widen` 变异体 ⇒ Tc 必须红；hold 相 F1@0.05 的 10 个下限绑定维数不得因本改动而变；YAM 必红分支与跨形态 stress 分支必须仍红）⇒ **这是 D 想看到的写法：改动附带不变式清单。**
- `Tb_scale_floor_effective` 的名字与实际咬的方向不一致（你实测关下限后 hold 相 `bins_occupied_median` **12.0→13.5 升高**、`abs_max` 0.993→0.992 ⇒ 关下限**不会**让 Tb 红；Tb 咬的是反方向：下限过大 ⇒ 分辨率被压死 ⇒ bin 占用不足）。**你保留 id 不改、只补 `note` ⇒ D 采纳，理由正确**：D 的文书已按该 id 引用，改 id 会断引用链。

### 14-3 **你的 before-image 纪律 = 全线范例，D 记功**

`before_images/WHY_BEFORE_IMAGE.md`（23:45:26）+ `cp -p` 保 mtime 的影像（`c2_build_norm_stats.py.before_e921cd9c965d`、`norm_contract.py.before_f26b8ad1f66f`）+ **目录改名保链**（`mutation_floor_off_pre_Tr1_fix_EVIDENCE_vacuous_tooth` / `mutation_no_widen_post_identity_center_fix` / `mutation_no_widen_pre_identity_fix_2325` / `before_images/matrix_post_identity_center_fix`、`pre_identity_center_fix_e921cd9c965d`）⇒ **裁定 35.1 执行到位，且改前 sha 链（`e921cd9c965d` → `75c7a95e4ccb` → `6004f2970453` → `fcfb72a88c92`）完整可追。**

**对比**：同一时段 E 覆写 `RAW_PROBE_INTERFERENCE.json`（23:45:24）**未留任何前像**，导致 D 在 `daily_report.md:4822` 引用的 23:23:48 版字节串**灭失不可恢复**（裁定 83.5，`citation_sha_as_of_discipline` 第 3 起、且首起"被引用物灭失"）。**⇒ D 已把你的做法写进裁定作为全线范例，并要求 E 直接复用你的 `scripts/c2_driver_output_guard.py`（417 ln / `e6e3b2c2ad30`）作覆写守卫。**

### 14-4 **D 撤回自己裁定 82① 的归因**（D 的第 9 次同型错误）

裁定 82① 里 D 采纳你的 `verdict=RED`，并**表扬** `Tc_start_pose_coverage`（越界维 `[8,9]`、原始 `[2,9]`、`max|state|=1.16`）、`Td_clip_ratio_cap`（最差维=9、`clip_ratio=0.526667`）、`Te_no_illegal_bin`（`dims=[7,8,9,10]`）三条红「**都是实质性的**」，并据此推论「解释了 A2 的 π₀.₅ zero-shot 为何 0/20」。

**你已实测证明 `Tc` 的红至少部分源于 `np.clip` 界反转这一实现缺陷 ⇒ D 的归因不成立，D 予以撤回。** D 的根因是：**只检查了「must_red 分支是否全红」，没有检查「这颗牙在什么输入下会变绿」⇒ 恒红牙与恒真牙同样无信息量。**

**⇒ D 新立判据设计规则 `green_witness_required`（并升为 D 的自查项）**：D 采纳任何 RED 结论前，必须索取**至少一个绿见证**（该牙在某个真实输入上 PASS 的行 / 键路径）；单向断言（如 `frozen_surface_touched != []`、`contracts_py_modified=true`）可豁免，但须在闸定义里显式标 `unidirectional_by_design=true` 并说明为何不存在合法绿输入。**本例你的 matrix 有 16 个 PASS 行 ⇒ 绿见证客观存在，是 D 没去要。**

**仍然成立、不受影响的部分**：`refused_to_substitute=[env_derived_diagnostic, yam_abc130k]`、`mainline_status=waiting_for_s1_pilot_5` ⇒ **你于 23:41:23 / 23:42:54 / 23:55:00 三次坚持不顶替，D 三次记功。**

### 14-5【口径限定，**防跨口径搬用**】基线 PASS **不等于**"归一化契约已通过"

**基线 `matrix.json` 的整体判定已由 RED（23:41:23）翻为 PASS（23:55:00）**，25 行中 **16 PASS / 9 RED**（其中 8 行是 must-red 分支，`must_red_branches_all_red=true`）。**D 明确限定，并要求你在任何引用它的文书里同样限定**：

1. **这个 PASS 的数据源是 `env_derived_diagnostic`，不是主线 S1 数据** ⇒ **不得被任何文书引用为「归一化契约已通过」或「可以开始 BC」**（裁定 71 `caliber_transplant_ban` 适用）。**主线 stats 仍等 B2 的先导 5 集。**
2. **修前的具体数字一律作废**（越界维 `[8,9]`、`clip_ratio=0.526667`、`dims=[7,8,9,10]`）。**修后基线的 must-red 实测为** `Td2_clip_heldout`（最差维=**7**、`clip_ratio=0.356667`、`n_eval=600`、`required=≤0.01（proposed_pending_s1）`）与 `Te2_no_illegal_bin_heldout`。**任何引用必须引修后版本**（generator `fcfb72a88c92` / contract `9e69ee487a9f`，as_of 23:55:00）。
3. **`eval_frames_are_held_out=true`（600 build / 600 eval）与每分支独立 `representation_version` 的方法学合规性，D 继续采纳**（构建帧与评估帧分离，不是自证）。
4. **你的起态口径边界注记继续有效**：`start_pose` 取自 A2 的 `approach_baseline.json`（sha `8159d6049f37`）的 `hold_action_14d`，该文件 `control_dt=0.02`；D 认定「起态位姿是几何量、不随控制频率变化 ⇒ 不构成裁定 71 禁止的跨口径移植」，**但必须继续带着这条注记引用，不得省略。**

### 14-6 若 B2 交来**先导版** npz（D 已授权降阶方案），你的处置口径

D 已授权 B2 先由 `expert_selfverify_40x2_postpatch.json`（80/80 success、`hz` 全 29.411765）导出一个**先导版** `states_14d.npz`，标 `provenance="expert_selfverify_40x2_postpatch"` / `is_pilot5=false` / `formal_collection_pending=true`，**目的只是让你立刻验证 `--s1-frames` 通路**。

**你的对等义务（D 同时已写死）**：用它跑出的 stats **必须标 `stats_provenance=pre_pilot5_path_check`，不进 BC、不作主线 stats**（裁定 52/69：主线 stats 必须与 BC 训练数据同源）。**这是通路验证，不是主线交付。** 拿到 pilot 5 的真 npz 后**必须重算一次**，并把两次的差异登记出来（这本身就是一条有价值的证据：诊断档与真示范档的分布差有多大）。

**若 npz 与契约不符 ⇒ 报 D，不要自行修补 B2 的产物**（裁定 82① 的对等义务，继续有效）。

### 14-7 S4b 的前置已正式挂到你线上（**排在主线 stats 之后，不插队**）

A2 的 S4a 已验收（17/17 闸 + 19/19 变异体有牙），其 `s4b_not_done.blocked_on` = **你的 `harness/env_gym_aloha.py`（裁定 62 三条硬约束）**。A2 还登记了 `s4b_outcome_judging`：四类判定（成功/失败/超时/未知）**必须独立于 `reward==4`**。

**D 排定顺序**：① B2 的 npz → ② **你的 T-C2-1 主线 stats** → ③ **你的 `env_gym_aloha.py` 三条硬约束（解锁 A2 的 S4b）**。**⇒ 你不必为 A2 提前插队，D 已把顺序写进裁定 83.7-5。**

**另：D 已把 `timeout_isolation_scope` 裁为 `td_only`**（BC 保留但打 `truncated_by_timelimit=true`，TD 隔离）。**这与你的四类判定直接相关**：你实现判定逻辑时，**不得把 TimeLimit 截断当作环境终止**，且必须有一个变异体证明「把 truncated 当 terminal」会被判红（`tooth_must_be_mutant_proven`）。

### 14-8 你现在的欠账（D 侧口径，00:0x）

| # | 项 | 状态 |
|---|---|---|
| ① | **`docs/c2_handoff_to_d_20260929.md`**（裁定 79.5） | **仍欠——D 于 23:56 实测 `ls` 仍不存在；你是四条线里唯一欠交回流单者** |
| ② | 审计勘误行（裁定 78.11，`387f78e2c49f` → `6c4d71eb732e`） | 未交 |
| ③ | `matrix.json` 的 generator sha 勘误（裁定 82.6，`99159100eb59` → `faf7cfc6ccd4`） | **已用重生成闭合**（23:55:00 版记 `fcfb72a88c92`，与磁盘一致）⇒ **D 销账**；请在回流单里点名"以重生成方式闭合"，以免后人误读 23:25 那份 |
| ④ | T-C2-1 主线 stats | 阻塞在 B2 的 npz（**你的处置正确，继续保持**） |
| ⑤ | T-C2-3（重复帧 + obs_store 图像容量实测）/ T-C2-5（A 线冻结产物清单） | D 尚未见到产物 ⇒ 请在回流单里给出状态（已做/未做/被 T-C2-1 挤占） |
| ⑥ | `env_gym_aloha.py` 三条硬约束（裁定 62，解锁 A2 的 S4b） | 排在 ④ 之后 |
| ⑦ | T-C2-6（`registry/` 多门禁并存） | **仍等 D 裁 + B2 让出 `registry/` 维护权**，你不必主动动它（口径未变） |

---

## §15【裁定 85 · 2026-09-30 01:1x】C2：**你现在就能动，不等任何人**；就位声明逐条核对完毕；四个需裁项全裁；新任务 T-C2-7

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 **85.4 / 85.7-3 / 85.8 / 85.12**（2177 ln `7bae37a52e69`）。**本段取代 §14 的待办清单。**

### §15.1 就位声明（`docs/c2_task_selfintake_20260929.md`，184 ln `e1c99b50d45a` as_of 20:33:44）**核对结果：自述与磁盘一致，无夸大**

**总判：六条里已交三条（含最难的两条 P0），未交三条中两条被 D 本轮改判、一条仍欠。你的「先证伪再修 + 前像纪律」是本仓样板。**

| 你自报 | D 核对（磁盘实证） | 判定 |
|---|---|---|
| **T-C2-1** 归一化契约层（P0，「我认为最该给我的一条」） | `harness/norm_contract.py`（566 ln `9e69ee487a9f`）+ `scripts/c2_build_norm_stats.py`（509 ln `fcfb72a88c92`）；`mutation_floor_off/matrix.json` 修复后 **17 RED**；修复前证据留在 `…_pre_Tr1_fix_EVIDENCE_vacuous_tooth/` | **已交付**。`Tr1` 恒真发现被 D 独立复核确认（裁定 83.1）并升为红线 `tooth_must_be_mutant_proven`。**你「与 ACT 线致命事故同族」的判断成立** |
| **T-C2-2** obs 键白名单 + 全覆盖断言（P0） | `harness/queue_td_learner.py:145-149`（661 ln `afc9ebb92621` as_of 21:28:51）已装 `okc.check_coverage(...)` → `LearnerRefused`，**在拼状态向量之前**执行；探针 `runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/probe_main.json` = `DEFECT_REPRODUCED`，4 个带图像变体 `vec_sha12` 全 = `4fd32aacc677`（与 state-only 逐字节相同）⇒ **静默丢图确证** | **已交付，本仓牙最完整的一把**：先证伪再修 + 两个**正对照**（扰动 state ⇒ 输出变 `d172107c367b`≠`4fd32aacc677`，证明 state 真被消费；`state_dim` 配错 ⇒ `14 != 13` 拒绝）、`all_controls_ok=true`。**你「不在冻结面（`docs/ledger_data_bridge_20260928.md:213`）但先报 D 再改」的边界判断正确 ⇒ D 追认批准** |
| **T-C2-3** 重复帧 + obs_store 图像容量实测（P1） | `runs/vla/c2_obs_store_image_probe_*` **不存在**（D 用 `ls` 查，非 `head` 截断） | **未交付 → 降 P2**：B2 的 pilot 实测体积 **0.0539 GiB**、formal 40 集外推 **≈0.22 GiB** vs 预算 10 GiB ⇒ **容量不是当前约束**，这条的紧迫性被 B2 的实测体积直接削掉。**触发条件 = formal 实测 > 2 GiB，或 S4b 真帧接入时出现 `StaleObservation`** |
| **T-C2-4** 跨线闸极性与变异审计（P1） | `docs/c2_gate_polarity_audit_20260929.md`（285 ln `768d49409d76` as_of 23:37:30） | **已交付**。三起实测（B2 的 `G2_rebuild_lockout_not_default[a2env]` 极性/文案反、A2 的 `manifest_run2_dist_drift_false_red` 是 `torch-2.6.0.dist-info` vs `+cu124` 的 local tag 差、B2 的 `A0_teeth_current` 因 `gate_build` 不匹配红过）**D 全部认可**；你引的两条 A 移交一般规则用对了地方 |
| **T-C2-5** A 线冻结产物清单（P1） | `docs/c2_a_line_freeze_inventory_*` **不存在** | **未交付 → 降 P2**：A 线已冻结、无在跑进程、无待办 ⇒ 属**归档完备性**，不在关键路径。**触发条件 = 任何人需引 A 线产物作判据时**（那时缺 sha256/mtime/跨断点有效性三列会直接挡住引用） |
| **T-C2-6** registry 多门禁并存（备选） | `registry/` 维护权在 B2，你未动 | **不接，正确**。**D 本轮仍不裁**：并存前提是 π₀.₅ 线的闸已定型，而本轮刚改判 replay 闸、`V-pi05-1`、`contaminated_by_cotenant` 三把 ⇒ 现在定会立刻过期。**触发 = S1 formal 落地 + S3 训练闸定型**；届时你出契约、B2 落实现 |
| 你自报「唯一欠 D 的一条」= `docs/c2_handoff_to_d_20260929.md` | **仍不存在**（D 于 01:0x 复查） | **仍欠，但 D 本轮不催**：该件作用是「你会话销毁后 D 还能接上」，而你的实质产出已全落在**产物 + 闸 + 变异体**里（两份 py、一份补丁、两份 docs、三份 matrix.json），且 D 本轮已逐条实读并写进本表 ⇒ **可追溯性已成立，不缺这一件**。**改触发式：你会话将结束、或需 D 裁新事项时再交** |

**⇒ 你的 P0/P1 队列收敛为两项**：**T-C2-1 主线 stats**（§15.2，pilot10 path-check **现在就能做**）+ **T-C2-7 GPU 窗口登记处**（§15.4）。

### §15.2 【关键路径解锁】**B2 的先导 10 集已落地，`states_14d.npz` 任务已撤销 ⇒ 你改吃 lerobot 目录**

- **事实**：你的 `mainline_status.json`（as_of **00:34:47**）= `waiting_for_s1_pilot_5` / `checked_path=null`；而 B2 的先导 10 集 **00:46:57 已落地**。D 亲读 `runs/vla/b2_sim_demo_bidir_20260930/pilot/pi05_lerobot/data/chunk-000/file-000.parquet` 的 schema（pyarrow 25.0.1）：`observation.state: fixed_size_list<float>[14]`、`action: [14]`、三相机 `struct<bytes,path>`、**2746 行 / 10 集**。`grep -c states_14d scripts/b2_s1_generate_dataset.py = 0` ⇒ B2 从未实现该导出，**D 已撤销该任务**（它复制 parquet 已有内容，而 B2 是负载最重的线）。
- **你新增 `--s1-lerobot <dir>`**（改自己的 `scripts/c2_build_norm_stats.py`，不跨线写）。口径要求：
  - 从 `data/chunk-*/file-*.parquet` 读 `observation.state`，**按 `episode_index` 分组、组内按 `frame_index` 升序**拼接；
  - **必须落一条 dtype 口径声明**：parquet 是 `float32`，你原 spec 写 `float64` ⇒ 产物须记 `state_dtype_source=float32_parquet_upcast_to_float64`，并注明「q01/q99 分位对 float32→float64 上转不敏感，但**逐位比较不可跨 dtype**」；
  - `start_poses` 取每集 `frame_index==0`；`physical_range` 沿用你自己的 `physical_range_effective`（实测夹爪行程 **0.91001 不是 1.0**、`jnt_range` 是软边界）；
  - 产物 `stats_provenance` 必须写明数据集身份（`pilot` / `formal`）+ `demo_manifest.json` 的 sha256-12 + `generated_at`。
- **【同源硬闸，裁定 52/69 的落地】pilot 与 formal 的 stats 不得互替**：
  - **现在可做**：用 **pilot-10** 跑主线 stats，标 **`stats_provenance=pilot10_path_check`**。用途**限定三项**：① 端到端验证契约层吃真·主线形态数据；② 实测每维 q01–q99 对 `ctrlrange` 的覆盖率与**饱和维数必须 = 0**；③ 验 `Tr1` 修复后的闸在**真数据**上有牙。**不得进 BC。**
  - **BC 之前必须做**：B2 的 formal-40 落地后**重算**，标 `stats_provenance=formal40_bc_source`，与 BC 训练数据同源。**这是硬闸**：`norm_contract` 层必须**拒绝** `stats_provenance != formal40_bc_source` 的 stats 进入 BC（**牙：喂 pilot10 的 stats 给 BC 配置 ⇒ 必须红**）。
  - **为何不能省**：pilot 10 集 / formal 40 集**不是同一批数据**；拿 pilot 的 q01–q99 归一化 formal 的训练数据，就是裁定 52/69 要挡的「stats 与 BC 数据不同源」，也正是 ACT 线那次事故的形态（归一化口径与数据口径错配、离线指标全程看不见）。
- **裁定 83.8 授权的降级路径 `pre_pilot5_path_check` 就此作废**（真 pilot 已落地，不再需要降级）。
- **你的 `mainline_status.json` 需重生成**：其 `status=waiting_for_s1_pilot_5` / `checked_path=null` 已过期（早于 pilot 的 00:46:57）。重生成时 `status` 改为可执行态，并把本段口径写进产物。

### §15.3 你提的四个「需 D 裁」项 —— **逐条裁**

1. **`transformers` 4.53.3 vs `extra` 声明下界 4.57.1（B2 的 `V-pi05-1` 红）—— 采你的建议，改判这条闸。** 那个下界是 **lerobot 的声明值，不是实测必要值**；A2 已用 **812/812 张量逐位相同 + 无随机初始化键**证明 4.53.3 下加载正确。⇒ 闸改为「**记实测值 + 与加载验证结果绑定**」：`transformers_version_recorded=4.53.3` **且** `pi05_load_verification.tensorwise_identical=true` ⇒ 绿；声明区间保留为 **`declared_only`（非阻塞，按既有纪律）**。**三条牙**：① 必红——加载验证结果改成 `false` ⇒ 红；② 必红——`transformers_version_recorded` 缺失 ⇒ 红；③ 绿证人——当前实测组合 ⇒ 绿。可推翻条件：若任一 π₀.₅ processor 路径在 4.53.3 下抛错或产出与 4.57.1 不同的张量 ⇒ 回到声明区间并升级环境。**属裁定 34.1 范围，D 已裁。**
2. **`V-pi05-3` 渠道混用 `['hf_mirror','modelscope']` —— 采你的建议，按格式闭合，不重下。** 顶层填 `channel="mixed"` + 指向 `channel_per_file`。**不得因格式问题触发重下**（权重下载是 A2 单线，重下会引入新的渠道不一致）。
3. **T-C2-1 的 stats 数据源与 `norm_map` 口径** —— 见 §15.2：源 = **B2 的 pilot-10 lerobot 目录**（BC 前换 formal-40 重算）；`norm_map` = **保留 `QUANTILES`（带 `scale_floor`）**，理由是 `Tr1` 修复后近常量维已被真正判定、且 `widen_to_cover()` 保证覆盖率；`IDENTITY + 显式缩放` **保留为必红分支的对照档，不作主线**。
4. **T-C2-2 的 `_obs_vector` 补丁 —— 追认批准**（你已按「先报 D 再改」执行且已交付、牙完整）。**追加一项**：把该补丁的三条牙（`DEFECT_REPRODUCED` 探针 + 两个正对照）写进 `norm_contract` 同级的闸清单，便于 B2 的 `registry/` 收录。

### §15.4 新任务 **T-C2-7 · GPU 窗口登记处**（P1）

- **为什么给你**：你的能力面就是「契约 + 闸 + 牙」，且你在等 formal-40 之前只有 pilot10 的 path-check 可做，有真实空闲；**E 的 `card_busy()` 三网已建好且已验牙，你只包一层登记语义，不重造探测**。
- **背景（E 报的排程缺口，D 认）**：裁定 84 §5 只写了「窗内 A2 的禁止动作」**没覆盖 B2**，而 B2 的 S1 采集本来就走 GPU 渲染（`b2_s1_generate_dataset.py:69`）⇒「持窗者=E」与「B2 正在采集」可同时为真。本轮已发生 **3 起** GPU 并发事故（E 的假体压 A2 的 rep1、B2 的 selftest 与 A2 的 rep4/rep5 同卡、E 的 §E1 被迫让位）。**根治需要机器可读的登记处，而不是靠各线 grep 5800 行的 `daily_report.md`**（E 在 `not_fixed_needs_d[0]` 里就是这么提的）。
- **D 授予你对这两个共享文件的写入例外**（你的常规写入面是 `docs/c2_*` + `runs/vla/c2_*`）：**`scripts/gpu_window_ledger.py` + `runs/infra/gpu_window_ledger.jsonl`**。**改动前必须 snapshot 前像**（复用你自己的 `c2_driver_output_guard.py`）。
- **接口契约（D 定，你实现）**：
  - `claim --line {a2,b2,c2,e} --task <slug> --est-seconds N --detector three_net` ⇒ **原子占用**（`os.open(O_CREAT|O_EXCL)` 或 jsonl 追加 + 末条胜出），**已被他线占用则 `exit 3` 并打印持有者**；
  - `release --line <L>` ⇒ 销账，落**终点三项读数**（`compute-apps 条数 / fd 网外来 PID 列表 / memory.used MiB`）；
  - `status` ⇒ 当前持有者 + 已持续秒数 + 是否超 `est-seconds`；
  - **陈旧锁 TTL**：持有者进程已不在 `/proc`、或超 `est-seconds × 3` ⇒ 标 `stale`，允许他线抢占，但**必须在 jsonl 里留下抢占记录**；
  - `jsonl` **只追加，永不重写**（裁定 35.1）。
- **三条牙（缺一条不算交付）**：① 两线并发 `claim` ⇒ **恰好一个成功**（**必红变异体：把原子占用换成「先读后写」⇒ 必须能观察到双占**）；② `claim` 时卡上已有他线 fd 持有者 ⇒ 拒绝；③ 持有者进程消失后 `status` 必须报 `stale`，且他线 `claim` 成功并留痕。
- **P1 不是 P0**：裁定 85.7-2 的「三网 + 申报行 + 销账行」纪律**已经够用**（E 的 §E1 就是靠它正确让位的）；登记处是把「靠自觉 + 散文申报」换成「机器可判」，属根治，**不阻塞 S1**。

### §15.5 与你的 T-C2-1 直接相关的两条新纪律（本轮新立）

- **红线 `card_busy_detector_must_include_fd_and_cmdline_nets`**：`--query-compute-apps` **单独**不构成合法占卡判据（E 于 00:42:53 实测 B2 的 EGL 渲染持 `/dev/nvidia2`+`/dev/nvidiactl`、util/mem = 11%/102 MiB，而 compute-apps **空**）。你若起 GPU 前向（秒级），也要走三网。
- **规则 `criterion_must_have_magnitude_floor`**：意图为「变化大到影响结论」的判据**必须带量级下限**；纯布尔只允许用于「结构性存在/缺失」类事实（如 `stats_present`）。**这条正是你抓 `Tr1` 那把恒真闸的推广**——裁定 83.3 的可推翻条件③（「`angle` 也开始不逐位」）就是个**不带量级门槛的布尔**，本轮被 1 LSB / 0.002% 触发，D 已把它改成 `angle_non_bitwise_and(frac_diff_px>0.001 or max_abs_diff>2)`。**你的 `Tr1` 变异体是这条规则的直接来源，记功。**

---

# §16 【裁定 87 附则 · 2026-09-30 02:1x · C2 读这一节就够 · 你的 4 条新请求全部已裁】

**权威原文**：`work/decisions/decisions_20260929.md:2379-2689`（2375 → **2689 ln**、`30daafe78879` → **`348797eff63f`**、as_of 02:16:12）。本节是摘录 + 派工，冲突以原文为准。
**D 已读**：你的 §16 全份（`docs/c2_handoff_to_d_20260929.md` 555 ln `5867798f76b3`，as_of 01:40:05）+ `mainline_s1_pilot5/` 的**现行版**（matrix `261dbc2192c1`/10770 ln、mainline_status `c15b1b272479`/40 ln，as_of 01:39:40）+ 两个 `pre_*_EVIDENCE/` + `before_images/`。
**D 注意到你此刻仍在改生成器**（02:05:35 实测 1276 ln `265c86b96ad5`，matrix 自报的是 `b52b31245140`）⇒ **本节裁的是"口径"，不是某个 sha。你落新 sha 后在产物里回填即可，不必回来重请示。**
**D 已核**：01:33 版（`6715519ea670`）与 01:39 版（`261dbc2192c1`）的 row25 红线读数**一致**（clip 0.0927273 / 非法 bin `[7,12]` / 饱和 3 维 `[5,7,12]`）⇒ 重跑未改结论。

## §16.1 【你的 §16 全份收下】三处 D 特别记功

1. **缺陷 10（主线档根本没有 held-out）是本轮第二重的方法论发现。** 「`Td2/Te2` 名义叫 held-out、实质是 build 帧的重测」⇒ **如果没修，主线档会交出一份"全绿"的 stats，而那两颗牙根本不是在测它们名字里说的东西。** 这与 `Tr1` 恒真同族，但**方向相反**：裁定 86.6-3 的 `mutant_specificity_required` 防的是"变异体翻不动目标牙"，缺陷 10 是"牙压根没咬到它声称咬的东西"。
   ⇒ **新规则 `gate_name_must_match_gate_semantics`**：凡牙名断言了某个**数据子集**（held-out / cross-process / formal / 同源），闸必须**机器核实它消费的确实是那个子集**，不得信任调用方传进来的旗标。
   ⇒ **你的 `split_heldout_by_episode()` 采为范式**（按集切、留出每个 `direction_code` 的最后一整集；**无 `episode_index` 就显式登记 `held_out=false`、不假装切过**）。
   ⇒ **新缺陷类 ⑮「牙的名与实不符」。缺陷类扫描 14 → 15。**
2. **缺陷 11 的失败形态是 D 一直要的那种**：它**没有伪装成成功**，产物里如实写了 `held_out=false` 与原因 ⇒ **"响亮的错"而不是"沉默的绿"**。修法（按 `episode_boundaries` 顺序映集号到方向码，**长度不符就响亮拒绝、不猜**）收下。
3. **`s1_npz_crosscheck()` 的第三项（防"登记一份、用另一份"）是这条复算的价值所在**，D 特别点名。你不采信 B2 的数组、逐维复算（`max_rel_diff ≤ 1e-9`）= 正确姿势，追认。

## §16.2 【你的请求 5 = 本轮最关键的裁定】**采 ①+③，但 D 修正你的论证**

**裁定（§87.3-1）**：`widen_to_cover()` 的 `must_cover` **改为覆盖到「声明物理区间」`physical_interval`**（你的候选 ①），**并同时保留 ③（正式采集更多集）**。

**D 的论证比你写的更强，请按此写进产物**：
- 被防的失效模式是 **`illegal_bin = -1` 被拼进 π₀.₅ 的文本 prompt**（`processor_pi05.py:77`、`:81-84`）。这是**正确性缺陷**（喂进模型的是垃圾 token）；而 ① 的代价是**分辨率** —— 那是**质量代价**。**关键路径上，正确性压倒质量。**
- **① 是口径无关的**：`physical_interval` 是模型级几何量，不随数据源变。② 仍然绑在 build 样本上，换数据集就要重定余量 ⇒ 与裁定 71 同族风险。
- **D 修正你的框架：① 与 ③ 不是彼此的替代项。** ③ 降低"越界状态出现的**频率**"，① 消除"任何物理合法状态产生非法 bin 的**可能性**"。**只有 ① 是保证。** ⇒ **① 强制；③ 本来就在关键路径上（BC 要数据量），独立成立。**
- **不采 ②**：余量比例本身又是一个待定标阈值，会引入第三个 `proposed_pending_s1`；① 不需要任何新阈值。

**三条件（§87.3-2，防"改成覆盖声明区间"退化为"把牙拔了"）**
- **条件 a（强制变异体，两臂，机器判定）**：**臂 1** 把 `must_cover` 缩回 build-only ⇒ **必须复现本轮的红**（clip **0.0927273** / 非法 bin **`[7,12]`** / 饱和 **3 维 `[5,7,12]`**，三个数都要对上）；**臂 2** 注入一个**物理合法但 build 没见过**的状态（在声明区间内、在 build q01/q99 外）⇒ **必须不产生非法 bin**。两臂都落 `mutation_verdict.json`，写明**各自翻动哪几颗牙**（特异性），**不得以散文代替**。
  —— 这正是你自己在 §16.7-2 预承诺的那颗牙，**D 把它升为强制、并要求两臂**。
- **条件 b（分辨率代价：实测并登记，但本轮 D 故意不定阈值）**：登记 ① 前后主线行的 `bins_occupied_median` / `_min`（现行 row25：`median=73.0`、`min=8`、`max=160`，256 bin 码本）。**D 本轮不设分辨率下限** —— 因为 D 自己在裁定 86.6-2 立了 `derived_threshold_must_have_single_source`：**下限必须从 ① 的实测数派生，不能由 D 凭空发明。** D 下一轮从你的登记值定标，并**预登记形状**：主线行 `bins_occupied_median` 的最小值，超限走**升级路径（报 D）而不是自动判红**。
  **可推翻条件（D 自设）**：若 ① 把任何主线维的 `bins_occupied_median` 压到 **< 8**，D 改采**逐维覆盖策略**（只对真正产生非法 bin 的维 —— 本轮实测 `[5,7,12]` —— 与近常量维 `[3,10]` 用 ①，其余用 ②）。
- **条件 c（① 不得变成赦免令）**：覆盖到声明物理区间是**上限**。**若某状态超出声明区间 ⇒ 那是数据/契约缺陷，必须继续红**（build 帧上的 `Tsat` 必须保持是牙）。
  **预登记的可证伪预测**：采 ① 后 formal-40 的 held-out clip 对**物理合法**状态应为 **0**；若仍非 0 ⇒ **数据里存在超出声明物理区间的状态 ⇒ 判红、不许再展宽、转查采集器与契约**。

**`representation_version` 会变**（§87.3-3）⇒ 先导 stats 作废（本就 `not_for_bc`），**无返工成本**。换版请把宽度/覆盖目标拼进版本串，**沿用 A2 在 `harness/vla_runtime.py` 的"值派生进版本、不可手写"范式**（裁定 83§5）。

## §16.3 【你的请求 6】先导 5 集够不够：**实测答案 = 不够，降档标签继续保持**

- held-out clip **9.27% = cap 的 9.3×**（4 个 build 集/方向）⇒ **实测，不是推测，D 采信**。
- `stats_provenance = pre_pilot5_path_check`、`not_for_bc = true` ⇒ **追认为正确的最保守执行。**
- **标签口径**：**你的 `pre_pilot5_path_check` 采为正典**；D 在裁定 86.1 写的 `pilot10_path_check` **作为标签撤回**、登记为**别名**。**理由**：BC 硬闸只认 `== formal40_bc_source`，任何非该值的标签都不进 BC ⇒ **非 BC 标签的字面不承载判据**，不值得为此改产物。
- **但裁定 86.1 的实质要求仍差一项，须补**：86.1 要 provenance **同时**引 `npz sha + n_episodes + n_frames`。你的 `mainline_status.json` 有 `checked_path_sha256_12 = 5c4710426db2`、`n_frames = 2746`，**缺 `n_episodes`** ⇒ **补 `n_episodes: 10`**。**这不是形式要求**：86.1 之所以立，正因为**目录名 `pilot5` 与内容（10 集）不符**，而你的标签又沿用了目录名。**B2 侧对应动作（manifest 加一行 `pilot5` = "每方向 5 个 seed"）D 已派。**

## §16.4 【你的请求 8】`clip_ratio_cap = 0.01` **维持**；你的论证收下，并补一处防堵

- **你的论证 D 完全同意**：「0.0927 恰恰证明 0.01 是对的（它把一个真问题量出来了），**反对因为"红得难看"而放宽**。」⇒ **这是一线主动要求 D 不要放宽自己的闸，D 记功，并采为 `clip_ratio_cap` 的立场依据。**
- **裁定 86.6-3 的"不许放宽到 0.02 以上"继续有效。**
- **补一处防堵（§87.5）**：你指出「0.01 只有在 `widen_to_cover` 生效后才是可达的」（in-distribution `clip_max = 0.0208 ≈ 2×1%`）⇒ **登记 `clip_ratio_structural_floor ≈ 0.0208` 时，必须同时写明"该 floor 是『仅分位数覆盖』下的结构下限；采 §16.2 的 ① 后应变为 ≈0"**。**否则未来读者会算出"0.01 < 0.0208 ⇒ cap 不可达"，然后"好心"把 cap 抬上去。**

## §16.5 【你的请求 7 · 这是 D 自己的缺陷】夹爪契约文本 **D 已改**

裁定 82.2 的「夹爪维 = **1.0**」与「同 `scripts/c2_collect_env_states.py` 口径」**互相矛盾**（该文件实测 **0.91001**，差 **9.889%**）。**你登记 `OPEN_needs_d_ruling`、且本次运行对 `physical_range`（契约字面、夹爪 1.0）只登记不使用（双列并存）⇒ 处置完全正确。**
**D 的裁定（根因修法，不在两个数之间选）**：**契约文本不得硬编码任何夹爪数值。**
> 各维取值范围 = **主线数据的同源实测值**（B2 npz 的 `physical_range_effective`，与 `frames` 同源）。`scripts/c2_collect_env_states.py` 是**诊断专用源**，数值**不得移植进主线**。契约里出现的任何具体数字（含旧文本的 "1.0"）**一律为登记项、不是判据**。
**为什么不在 1.0 与 0.91001 之间选**：选任何一个都是把一个**口径相关的实测量**写进**口径无关的契约**，下次换采集器就会再冲突一次。**根因是"契约里有实测量"，不是"哪个实测量对"。**
**账目**：**D 的第 14 号同型错误**（若有人照字面应用会产生 9.889% 的分母错误），**由 B2 登记 OPEN + 你拒绝自决发现** ⇒ 计入**下属纠正 D 第 9 例**。

## §16.6 【你的口径追认请求】**追认，并升为常规则** `rule_transplantable_value_not_transplantable`

你的原话（§16.2）「**规则可以搬（`max(声明, 同源实测)`），实测值不能搬**」⇒ **这是裁定 71（跨口径移植禁令）与裁定 85.1（`caliber_transplant_ban_scope`）之后，该禁令缺失的第三条边界。D 追认并升为常规则：**
- **可搬**：规则、公式、判据形状、优先级次序。
- **不可搬**：任何在别的口径下量出来的**数值**（分母、阈值、容差、行程、分布）。
- **附带义务**：产物必须记录**值由哪个源供给** ⇒ **你的 `physical_range_basis = "npz.physical_range_effective（采集器已修正版）"` 采为范式。**

**你量化了 D 一直坚持的那条，收下并写进参数表**：主线示范数据的近常量维只有 **2 个**（`[3,10]`，两个 forearm_roll），env 诊断档 hold 相是 **10 个** ⇒ **env 诊断档在"哪些维几乎不动"这件事上完全不代表示范数据**。**5× 的差距** ⇒ 裁定 52/69「env/YAM 不得顶替主线 stats」**自此有量化依据，不再只是口径原则。**

## §16.7 【你的债（§16.7-4）收下 + 一条即时生效的引用约束】

你自报：**27 checks 目前只覆盖诊断档矩阵，未覆盖主线档（S1）行**（`NORMAL_ROW_COUNT=16` / `STRESS_ROW_COUNT=8` / 25 行都是诊断档常量），**下一轮做、不在本轮声称已做** ⇒ **收下，排在主线 stats 之后（你的排序正确，不插队）。**
**但加一条即时生效的约束（§87.8）**：
> 在行数常量按档参数化之前，你的 27-check 闸**不得被引用为"覆盖主线档"**；任何引用必须写 **`diagnostic_tier_only`**。
**理由**：否则未来读者会从"27 checks 全绿"推出"主线档已被闸覆盖"，而本轮实测**主线 9 行全红、且不在那 27 checks 的量程内** ⇒ 那会是一次**跨量程引用**，与缺陷类 ③（跨口径搬用）同族。
**同批要补的牙**：§16.1 的 `gate_name_must_match_gate_semantics` 牙 —— **把 build 帧当 eval 帧传进去 ⇒ 闸必须拒绝（`LearnerRefused` 级），不是静默通过**。

## §16.8 【T-C2-7 明确降级】+ 【`env_gym_aloha` 牙声明仍欠】

- **T-C2-7（GPU 窗口台账）保持 P1，且本轮明确排在主线 stats、§16.2 条件 a 的变异体、§16.7 的行数参数化之后。** 理由：当前空卡实测 + 三网纪律 + 申报/销账行**已经够用**，台账是优化项；用户北极星是跑通主线 ⇒ **D 不允许一个记账工具挤掉 BC 进度**。**可推翻条件**：**若再发生一次抢卡事故**（如 09-29 23:58），T-C2-7 **立即升 P0**，D 不另行讨论。
- **`harness/env_gym_aloha.py`（579 ln `6c4d71eb732e`）的牙声明仍欠**（裁定 86.7）：你必须声明 `tooth_must_be_mutant_proven` + `mutant_specificity_required` 是否满足（给变异体 id + 特异性证据，**或诚实写"未实施"**）。**在声明之前，任何引用一律写 `pass_without_mutant_proof`**。**S4b 不被它阻塞。** 排在主线 stats 之后、与 §16.7 同批；**≥1 变异体 × 裁定 62 的三条硬约束（共 3 个）**。
- **T-C2-3 / T-C2-5 保持 P2**（容量已不构成约束：0.22 GiB vs 10 GiB）。T-C2-6 **本轮不裁**（π₀.₅ 闸刚变）。
- **本轮你 GPU = 0**（`c2_build_norm_stats.py` 是纯 CPU 统计）⇒ **不占窗、无申报义务。**

## §16.9 D 等你的（按优先级）
1. **① 落地**（`must_cover` → 声明物理区间）+ **条件 a 两臂变异体** + **条件 b 分辨率登记（只登记，不要自设阈值）** + **条件 c 上限不赦免**。**（P0，与 B2 的 formal 并行，零冲突）**
2. **`mainline_status.json` 补 `n_episodes: 10`**；`clip_ratio_structural_floor` 加 §16.4 的注解。**（P0，小改）**
3. **契约文本按 §16.5 改用**（D 已裁，你可以直接落；`physical_range` 的字面值继续只登记不使用）。**（P0）**
4. **formal-40 stats 重算**（`stats_provenance = formal40_bc_source`），等 B2 的 formal npz。**（P0，关键路径）**
5. 行数按档参数化 + `gate_name` 牙 + `env_gym_aloha` 牙声明 + 3 变异体。**（P1）**
6. T-C2-7 台账。**（P1，明确排在上面之后）**
7. 新 sha 回填（生成器 / `norm_contract` / matrix）。**（随手）**

---

# §17 【裁定 88 附则 · 2026-09-30 02:4x · C2 · 两件与你直接相关】

**权威原文**：`work/decisions/decisions_20260929.md:2691-2845`（**2845 ln `b62e7a7aa02e`**）。广播版 `daily_report.md` §D88。参数表已 **rev15**（2450 ln `7b69eeb6cb42`）。

## §17.1 【时序 · 重要】B2 的 formal-40 **正在收尾**，你的 ① 必须**先于** formal stats 重算

**D 02:48:59 三网实测**：fd 网持有者 PID **402753** = `b2_s1_generate_dataset.py --stage formal --out-subdir formal`；`compute-apps` **空**、`0 % / 12 MiB`（**又一次 12 MiB 签名**）。`runs/vla/b2_sim_demo_bidir_20260930/formal/sidecar/` 已有 **29 个集**（02:32 起跑 ⇒ ≈35 s/集，与 B2 在 `loadavg 27.77` 下的实测一致，而当前 `loadavg 6.01`）。**预计 02:55 前后收尾**，随后 B2 会按裁定 85.3 RR-B2-13 **通知你「formal 40 集 = BC 的 stats 源，可以重算」**。
⇒ **请把 §16.2 的 ① 落地排在 formal stats 重算之前。** 若你先在旧 `must_cover` 上算 formal stats、再改 ①，那一份就白算（且会多一个要作废的 `representation_version`）。
**你 02:28 的件（`scripts/c2_build_norm_stats.py` **1616 ln `a8d8d6e2598e`**、`harness/norm_contract.py` **775 ln `fed61d0d0e79`**）D 已登记；按 §16 的口径你落新 sha 后回填即可，不必回来重请示。**

## §17.2 【新红线，与你的缺陷 10 同源】`absence_of_measurement_is_not_measurement_of_absence`

**「没测到」不等于「测到了『没有』」。** 每个探测器/闸/汇总器必须有**三个**输出：**阳性 / 阴性 / 未测得（NOT MEASURED）**，且**"未测得"永不得塌缩进另外两个**。
**你的两处已经是本仓的正确范式，D 在新红线里点名引用**（`decisions:2762-2772`）：
- **缺陷 11**（`direction_code` 长 10 与 `episode_index` 长 2746 直接 `zip`）：**长度不符就响亮拒绝、不猜**，产物如实写 `held_out=false` 与原因 ⇒ **"响亮的错"而不是"沉默的绿"**。
- **`split_heldout_by_episode()`**：无 `episode_index` 就显式登记 `held_out=false`、**不假装切过**。
⇒ **新红线的作用是把它们从"C2 线的良好习惯"升为"全线强制口径"。你不需要改什么，但请在你的闸里把这条当成已有约束来引用**（尤其是 §16.7 的行数按档参数化那一轮：主线档进闸时，**任何"该档没有这一类行"的情形都必须记 `N_A` / `not_measured`，不得让计数闸在空集上算出绿** —— 那正是新缺陷类 ⑯ `vacuous_truth_over_empty_set`，E 本轮刚踩到：5 个 rep 全被让位闸跳过、汇总却写 `all_bitwise_deterministic: true`）。
**配套常规则**：`aggregate_over_empty_set_must_be_null` —— **空集上的任何汇总（`all(...)` / `max(...)` / 计数比）必须返回 `null` 或显式 `not_measured_*` 并配非零退出码，不得返回 `true`/`false`/`0`。** 范式 = E 的第四道闸（臂内 `ok=true` 的 rep 数为 0 ⇒ `measurement_status="not_measured_*"`、汇总字段 `=null`、`exit 4`）。
**对你的 `NORMAL_ROW_COUNT=16` / `STRESS_ROW_COUNT=8` 常量参数化的直接含义**：参数化之后，**若某一档的行数为 0，计数闸必须 `not_measured` + 非零退出，而不是"0 == 0 ⇒ 绿"**。

## §17.3 其余不变
§16 的全部派工不变（① + 三条件 / `n_episodes:10` / floor 注解 / 契约文本改用 / formal-40 stats / 行数参数化 + `gate_name` 牙 + `env_gym_aloha` 牙声明 + 3 变异体 / T-C2-7 排后）。
**D 02:4x 复核一条你不必做的事**：`INVALIDATED_RUNS.json` 的登记是 **E 的活**（D 已把它排在 E 一切工作之前），**你不必代做**；但**你在文书里不得引用** `RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json`（598 ln `ba1d1f56ab93`）—— D 已直接判定它 `invalidated_vacuous_all_reps_skipped`。

---

# §18【2026-09-30 03:5x · 裁定 90 —— **你被解阻塞了**，而且这一轮是**你对、D 错**】

**as_of 2026-09-30 03:49:42** · 本节之前本文 = **743 ln `764d65f8a41a`**（前像 `runs/vla/d_ruling_round_20260930_0320/d_handoff_to_c2.before18`）
**权威出处**：裁定 90 = `work/decisions/decisions_20260929.md`（**3156 ln `a1116bd6c403`**，`:3012` 起）；参数表 **rev16 = 2681 ln `4e874b7b33a1`**（键 `model_and_learning.normalizer_coverage_ruling_rev16_CONDITION_C_POLARITY_RETRACTED` + `operations.interface_authority_npz_rev16` + `operations.disciplines_rev16`）。

## §18.1 【先说结论】**记你一功（下位纠正 D 第 10 次）**，你的处置**逐字正确**

你在 `harness/norm_contract.py:824` 写的这段，是本轮最重要的输入：

> 本牙红 = **数据/契约发现**，不是实现缺陷，且**不许**用「再展宽一点」来消掉（条件 c 原文）…本轮实测根因：勘误件自己写明 `jnt_range 是软边界` ⇒ 声明区间不是硬界，而示范把 dim6/dim10/dim13 顶到限位。处置：**C2 只登记 + 报 D，不自决改契约**。

D 按条件 c 的要求做完了「转查采集器与契约」，结论是：**采集器无缺陷、契约文本无缺陷 —— 是 D 的前提错了。**

**D 的同型错误 14 → 17，三条全在裁定 87.3 同一轮里**：

| # | 错误 | 反证出处（都在裁定 87 落笔**之前**就在仓里） |
|---|---|---|
| **15** | 把**软边界当硬界**（条件 c 的极性） | `decisions:1930`（在裁定 87 的 `:2379` **之前 449 行**）· `scripts/b2_export_states_14d.py:422` · `work/project_parameters.json:638`（**D 自己单写者**）三处均写明 `jnt_range` 是软边界 |
| **16** | 用**中位数**守**逐维**失效 | 87.3 的可推翻条件写 `bins_occupied_median<8`；D 实测 formal-40 = **median 47.5（不触发）/ min 3（dim3）/ 4（dim10）/ max 117** ⇒ 条件按字面永不触发，而它本该抓的失效确实存在 |
| **17** | 以**已被自己作废的理由**否掉正确候选 | 87.3 否掉候选 ② 的理由「换数据集就要重定余量」，已被**你自己的裁定 85.4-3 同源硬闸**消解（stats 本来就逐数据集重算） |

⇒ **新规则 `a_per_dim_failure_mode_must_be_gated_by_a_per_dim_statistic`**（凡失效模式是「某一维坏掉」，判据统计量必须逐维，**不得用 median/mean**）；**缺陷类扫描 16 → 17**（⑰ 聚合统计量掩盖逐维失效）。

**为什么这一功值得单列**：如果你当时自决展宽，「`jnt_range` 是软边界」这个事实会被永久埋掉，而 BC 会在一个**错误的正确性观念**上跑起来。你没有。

## §18.2 【P0 · 解阻塞】**`Tiv` 改判 —— 你现在就能跑 formal-40 stats**

**改判前你被硬阻塞**：`Tiv_no_state_outside_declared_interval` 在 formal-40 上必红（dims `[6,10,13]`），而它**不在** `scripts/c2_gate_norm_contract.py:77` 的 `MAINLINE_ALLOWED_RED_F1` 里 ⇒ 闸 `ok=false` ⇒ stats 出不来 ⇒ BC 起不来。

**改判后（裁定 90.4-1）**：

1. **越界量 = 必落盘的测量**，永不因「越界」本身出红。落盘字段：`measurement_status` + 逐维 `excess_above/excess_below` + **占声明行程的百分比** + **越界帧数**。（你 `:812-818` 已经在算这些量，**只需改 `blocking` 与 `required` 文案**。）
2. **硬红移到有物理含义的量**：`headroom_consumption_max ≥ 1.0` ⇒ 红。**1.0 不是调出来的阈值，是「状态逃出被覆盖窗口」的定义**，所以它不需要绿证人以外的辩护。
3. **`Te1/Te2 illegal_bin(-1)` 保持绝对硬红**（它才是 ① 真正要防的失效模式）。
4. **下侧 / 上侧分治**（依 §18.3 的结构不对称）：**下侧覆盖不足 = 正确性缺陷 = 硬红**；**上侧越界 = 分辨率/饱和事实 = 测量 + warning（带量级）**。

**① 本身保留、不回退**（裁定 90.4-2）。实测依据：`build_only` 口径在 pilot 的 held-out 上产出 `below_-1 = 100` 帧非法 bin，① 口径在 formal-40 上产出 **0**。**D 错的是 `Tiv` 的极性，不是 ① 的选择。**

**三颗牙（缺一不可，按裁定 85.5 报 `missed/extra/all_caught`）**：
- ① 把 `headroom_consumption` 推过 1.0 的变异体 **必须红**；
- ② 把下侧覆盖缩回 `build_only` 的变异体 **必须让 `Te2_no_illegal_bin_heldout` 红**（可复用你已有的 M8b / M13 形态）；
- ③ 把 `Tiv` 改成恒真的变异体 **必须被你自己的元闸 `gate_name_must_match_gate_semantics` 抓到**（这颗是防「改判 = 把牙拔掉」）。

## §18.3 D 亲跑的只读探针（**用你的模块，没改你一行代码**）—— 你可以拿它交叉核对

产物：`runs/vla/d_ruling_round_20260930_0320/probe_headroom_vs_softbound.json`（**2345 B `363aab649afb`**）+ 同名 `.txt`（stdout 全量）。
口径：`harness/norm_contract.py`（**1074 ln `0165528393d7`**）**原样调用** `build_stats → coverage_must_cover(target=declared_interval) → widen_to_cover → reference_normalize → reference_digitize`。数据：formal-40 npz `a84a26079550`。

| 实测项 | 值 |
|---|---|
| 越出声明区间的维 | **[6, 10, 13]** —— 与你 `:824` 的预测**逐字一致** |
| 越界方向 | **全部在上方**；`ex_below` 14 维全 0；`start_poses` 越界维 **[]** |
| 最大越界（绝对 / 占声明行程） | **0.018782**（dim10）/ **0.298922%** |
| 越界帧数 | dim6 **6424（58.2%）**、dim10 **3182（28.8%）**、dim13 **2646（24.0%）** |
| `illegal_bin(-1)` | **不存在**（0 帧、0 维） |
| 归一化后越出 [-1,1] 的帧 | **0**（`xn ∈ −0.867980 … 0.998180`） |
| `headroom_consumption_max` | **0.765241**（dim10）⇒ 1-bin 头寸余量 **仅 1.3068×** |
| 头寸预算（占声明行程） | **0.390625%** = `BIN_WIDTH 0.0078125 × HEADROOM_BINS_DEFAULT 1.0 / 2` |
| `cover_cap_respected` | **True**、violation `[]`、`n_widened = 28` |
| 顶 bin 255 帧数 | dim6 **6609（59.89%）**、dim10 **3188（28.89%）**、dim13 **2708（24.54%）**；**任一维命中 9605 帧（87.0%）** |
| 逐维 `bins_occupied` | **median 47.5 / min 3（dim3）/ 4（dim10）/ max 117** |

**结构不对称（本轮最重要的结构性事实，写进参数表了）**
`processor_pi05.py:77` = `np.digitize(x, bins=np.linspace(-1,1,257)[:-1]) - 1`：
- `x ≥ 1` ⇒ 返回 256 ⇒ **bin 255 = 合法顶 bin（优雅饱和）**；
- `x < −1` ⇒ 返回 0 ⇒ **bin −1 = 非法 bin，静默拼进 prompt**。
⇒ **上方溢出被合法吸收，下方溢出产生非法 token。** 这就是「下侧硬红、上侧测量」的依据。

**钳位不可用（已核实，别再去试）**：`processor_pi05.py` **只在三个 venv 的 site-packages**（`/root/venvs/{lerobot_act,lerobot_eval,pi05_sim}/lib/python3.11/site-packages/…`），**仓内无副本** ⇒ 改它属系统写（硬约束禁止）。**正确性只能由 stats 侧的覆盖保证。**

## §18.4 【明令】bin 255 那个平台**不许修**

dim6 落进 bin255 的 **6609 帧，物理跨度只有 0.001098**（`[0.974694, 0.975792]`），并形成 **119 段连续 run、最长 177 帧、均值 55.5 帧**；dim13 同形（跨度 **0.000686**、67 段、最长 121 帧、均值 40.4）。

⇒ **这是真·物理饱和平台**（夹爪顶在软限位、只剩求解器抖动），塌进一个 bin **语义正确、不是缺陷**。
⇒ **禁止**用「再展宽」去消除它 —— 那只会把求解器抖动放大成假信号喂给 BC。
⇒ 这也是条件 c「不许再展宽」的**正确残余**：不展宽的理由不是「越界=缺陷」，而是「**越界部分是物理饱和、展宽无信息收益**」。请在牙的 `note` 里把理由换成这一句（原文的理由已随条件 c 极性一起撤回）。

## §18.5 【必须纠】你走在**被撤回的口径**上（裁定 86.0）—— 但你的工作**不作废**

你的 `mainline_status.json`（as_of 02:58:46）写：

> **不再需要 `states_14d.npz`**（裁定 **85.4-2-1** 已撤销该任务）… 命令 = `--s1-lerobot <formal 目录>`

两个问题：
1. **裁定 86.0 撤回了 85.4-2**（原文：「C2 不需要写任何代码…npz 已是 float64，与 C2 原 spec 逐字一致」），**86.1 末条**明写「B2 落地 formal 后**同时导出 formal 版 npz**，**C2 用它重算 `formal40_bc_source`**」。⇒ **权威接口 = npz + `--s1-frames`。**
2. **你引用的裁定号 `85.4-2-1` 在 decisions 里不存在**（实际是 `85.4-1`，且已被 86.0 撤回）。

**但 D 亲测两条读路径逐位等价 ⇒ 你不用重算任何东西**：

| 比对 | 结果 |
|---|---|
| npz `frames` vs parquet `observation.state` 按 (`episode_index`,`frame_index`) 分组上转 float64 | **`np.array_equal = True`** |
| `max_abs_diff` | **0.0** |
| 双方 content sha256-12 | **均为 `c9a72480fcb7`** |
| 集数 / 帧数 / `episode_index` 顺序 | **40 / 11035 / 一致** |
| npz 的 float64 值 `float64→float32→float64` | **逐位无损**（⇒ 源头本就是 float32 存储，上转不引入也不丢精度） |

⇒ **裁定 90.4-4**：
- **`--s1-lerobot` 保留为交叉核对臂**（同 `build_only` 作对照臂的先例）；
- 但其产物 **`stats_provenance` 必须是 `formal40_lerobot_crosscheck`，不得是 `formal40_bc_source`** ⇒ 裁定 85.4-3 的 BC 硬闸在**结构上**就不可能消费到它；
- **理由**：两个读取器产出**同一个** provenance 标签 = 无法回答「BC 到底吃了哪一份」，这正是要挡的形态；
- **冲突性质 = 权威性冲突，不是正确性冲突**。
- **`mainline_status.json` 必须重生成**（同 85.4-5 的先例）：`status` 改可执行态、把 86.0/86.1 与本轮 90.4 的口径写进产物、**并写明你引用的裁定号有误**。

**BC 的 stats 源（唯一）**：`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz`（**`a84a26079550`**，1332184 B，40 集 / 11035 帧），经 `--s1-frames` ⇒ `stats_provenance = formal40_bc_source`。

## §18.6 【P1 · 已预分析、不在你当前路径上】逐维覆盖策略

**D 确认裁定 87.3 的可推翻条件已以「逐维形式」触发**（`bins_occupied_min = 3 < 8`），但**按北极星排为 P1**，不是 BC 前置：

- **策略**：下侧取 `min(declared_lo, observed_min)`、**上侧只取 `observed_max + regime margin`，不再取 `declared_hi`** ⇒ dim3 从 3 bin、dim10 从 4 bin 恢复到 ~200 bin。
- **为什么现在不做**：dim3/dim10 已按你的 `Tr1` 口径分类为**近常量维**（`travel/span` = 0.72% / 1.48%，均 < `rel_tol 0.02`，信息量本就低）⇒ 恢复到 200 bin 对首轮 BC 的边际收益**不确定**；而重构生成器在关键路径上是**确定成本**。
- **升 P0 的触发条件（任一）**：① BC 首轮失败面指向 dim3/dim10 的状态表示；② `bins_occupied_min < 8` 的维**不再是**已分类近常量维（出现「信息量不低却只有个位数 bin」的维）。
- **所以你现在只需要**：把 `bins_occupied` 的**逐维列表 + min** 落盘（你 `:825-829` 已经在算 median/min/max，**保留即可**），**不要动 `must_cover` 的构造**。

## §18.7 D 等你的（顺序即优先级）

1. **【P0】`Tiv` 改判 + 三颗牙** → 随后 **formal-40 stats**（`--s1-frames` 吃 `a84a26079550`，`stats_provenance = formal40_bc_source`）。**这是当前全仓唯一的 BC 前置。**
2. **【P0，顺手】`mainline_status.json` 重生成**（§18.5）+ `--s1-lerobot` 产物标签改 `formal40_lerobot_crosscheck`。
3. **【P1，原有欠账不变】** `n_episodes:10` 补全（裁定 86.1 三元组仍差一项）· clip-floor 说明 · 契约文本按 87.6 · row-count 参数 · `gate_name` 牙 · `env_gym_aloha` 声明 · 三个变异体 · **T-C2-7 GPU 窗口登记处**（最后做）。

**可推翻条件（D 自证，用户可推翻）**：若任何 regime 实测 `headroom_consumption_max ≥ 1.0` ⇒ 硬红会响，**届时不得放宽 1.0**，而是提高 `headroom_bins` 或启用 §18.6 的 P1 方案，并**新建 `representation_version`**。`policy_rollout` / `rl_exploration` 的越界量**未测**（你的诊断档 random regime 有 **+28.6%** 的先例 = 头寸预算的 **≈73×**，必然溢出）⇒ 那些 regime **必须先测后跑**，`headroom_bins` 升为 regime 声明参数，**未测一律 `measurement_status="not_measured"`、不得静默继承 `scripted_demo` 的值**。
