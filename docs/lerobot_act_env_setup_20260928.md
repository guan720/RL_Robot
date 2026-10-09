# 官方 LeRobot ACT 环境搭建与跑通记录（2026-09-28，智能体 A）

本轮目标只有一个：把 09-24 卡住的「没有可复现的官方 LeRobot ACT 训练环境」解掉，并用官方
入口真的训出 ACT 权重。**没有接 residual SAC、没有接 guard/recovery、没有动视觉、没有碰
`RL_Harness_v4_20260924/`、没有修改 `/root/venvs/rlrobot`（另一会话正在重建它）。**

## ⚠ 09-29 附记：环境已被重建（**读本文的复现命令前必看**）

0929 早间服务器检修把 overlay 上的 `/root/venvs/lerobot_act` 与 `lerobot_eval` 一并抹掉，
A 已按裁定 32 / D 执行单在 **14:11** 重建完毕。**本文以下所有命令照原样可用**（版本逐项 == 原 pin），
但有 5 条新事实必须知道：

1. **venv 现在物理位于 NFS**：`…/.codex-persist/envs/lerobot_{act,eval}`，
   `/root/venvs/lerobot_{act,eval}` 是**软链**（仓里 73 个文件硬编码该路径，不改路径）。
   软链在 overlay ⇒ **每个新容器要重建一次**：
   ```bash
   P=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs
   mkdir -p /root/venvs
   ln -sfn "$P/lerobot_act"  /root/venvs/lerobot_act
   ln -sfn "$P/lerobot_eval" /root/venvs/lerobot_eval
   ```
   venv 的 shebang 是**指向 NFS 真实路径的绝对路径**（在那儿建的）⇒ 经软链调用仍然正确（已实测）。
2. **`--dataset.root` 必须是有效的本地路径**（本文「复现命令」#2 的 `$R/…`）。
   路径写错时 lerobot **不会**报「路径不存在」，而是**回落去 `huggingface.co` 查 refs**，
   撞上本机代理（`https_proxy=10.2.162.180:3128`）的 **503** ⇒ 报错长得像网络故障，极易误判成「环境坏了」。
   实测：**root 正确时全程离线可训**（`runs/infra/a_smoke_env_rebuild_20260929/probe_train.log`，2 步 `PROBE_EXIT=0`）。
   A 的第一轮 smoke 就栽在这里（脚本把已绝对的路径又拼了一次 `$PWD`）。
3. **版本锁分成新旧两份，并存不覆盖**：0928 那两份原件（本文「环境规格」的依据）**一字节未动**
   （mtime 仍是 `09-28 14:56:45` / `15:24:06`，sha256 `68a38731c5b5` / `b6db07e2e31c`）；
   新装环境的 lock 在 `runs/infra/a_lerobot_env_rebuild_20260929/`。
   两者有 **3 处差异**（`ImageIO` 2.37.4→2.38.0 两份、`uv` 0.12.19→0.12.17 仅 act），
   **都不是 pin 项、都不在本文任何一条链路上**（官方 ACT 三件套不 import imageio；全仓无 `import uv`）。
   逐条解释与「为什么变」见 `docs/a_env_rebuild_acceptance_20260929.md` §3.2。
4. **断点 `BP-20260929-lerobot-env-rebuild`**（`occurred_at 2026-09-29T10:45:56+08:00`，`ready_at 14:11:23`）：
   本文产出的任何产物若 mtime **早于**该时刻而被引用为「可复现」，一律要在重建后的环境上**重跑**。
   该断点**单列**，不与 C 的 `BP-20260929-venv-rebuild` 合并（`invalidates` 范围不同）。
5. **smoke 已过（3/3），但复现主张仍被阻**：`scripts/a_env_readiness_gate.py` 现值
   `BLOCKED`，`blocking_fail` 从早上的 **6（E1–E6）** 降到 **1（只剩 E6）**。
   E6 判的是「**C 的** manifest 已把 lerobot 探通」⇒ **解除动作在 C 手里**（A 不改 C 的文件）。
   在就绪闸 `ALLOWED` 之前，本文的任何训练/评测结果**不得**被引用为「跨断点复现」。

机器可核承载：`runs/infra/a_env_manifest_20260929.json`（生成器 `scripts/a_env_manifest.py`，可复跑）。

## 结论

- 官方 LeRobot ACT 环境已建成并验证，两条门槛命令都过。
- interchange 导出已用官方 API 重建成真正的 `LeRobotDataset`（codebase v3.0），chunk 语义与
  源数据逐元素等价（297 / 7128 / 2376 个 chunk 全对）。
- 官方 ACT 已完成**单 episode learned overfit**（两条 lr 臂，20k 步，正式 safetensors checkpoint）
  与**全量 train24 训练**（两条 lr 臂，20k 步）。
- 单局 overfit 的开环动作对齐：逐帧 mean|err| = 0.0066（lr 1e-5），旋转三维完全为 0，
  gripper 符号一致率 100%；这是**learned policy**，不是 teacher replay。
- 09-24 审计清单里的「Official LeRobot ACT single-episode learned overfit: not run」这一项，
  状态改为**已运行、已有 checkpoint、已有独立审计**。
- 闭环 20 局真值评测（seeds 5000–5019、无 guard/recovery）：MEAN_STD 归一化下 lr1e-5 只有
  2/20、lr1e-4 **塌缩**（0/20、grasp 0/20、每帧输出常数）；把 ACTION 换成 **MIN_MAX**
  归一化后同一配方升到 **11/20**（`grasp_verified` 20/20、`flick_frac` 0）——
  learned 官方 ACT 第一次拿到非零、非弹射的抓取成功，且原因定位到单个可复现变量。
- 但 11/20 的成功局 `max_rise` 只有 0.0094–0.0379 m，`success_rise = 0/20`，
  `mean_max_rise` 仅为 scripted base-only（0.0764 m）的 17.5% → **是「过真值线」不是「学会抬起」**，
  且只有 1 个训练 seed，晋级条件第 1 条只算部分满足。
- **（15:50 更正，见下节）MIN_MAX 的 11/20 不跨训练 seed 复现**：同配方 seed0/1/2 =
  **11/20、0/20、4/20**（mean 5.0/20 = 25%，极差 0–55%）。所以「学到稳定能力」这个说法不成立，
  只能说「MIN_MAX 把成功率的期望从 ~0 抬到 25%，但种子方差极大」。
- **晋级条件第 1 条现在判为不满足**：给评测器补上 `final_rise` 后，按受控成功判据 v1 的
  C5（`final_rise >= 0.04 m`）——因为 `final_rise <= max_rise` 恒成立，而三臂所有成功局的
  `max_rise` 除 seed2 的一局（0.0418）外全部 < 0.04 m → **受控成功数为 0**，
  先前 `flick_frac = 0` 是字段缺失下的偏松判定，已作废。
- 根因指向数据：train split 里 `done` 相位占 **72.7%**（teacher 输出常值 `[0,0,0,0,0,0,+1]`）、
  真正的 `lift` 帧只占 **2.3%**，dz 在 82.5% 的帧上恒为 0 → L1 损失的最优解就是「dz 输出 0」，
  抬起幅度学不出来。已给 builder 加 `--trim-done N` 并建了两个裁剪版数据集做对照（见下节）。

### 17:15 更新：本轮全部单变量跑完后的当前口径（§12–§16 是证据）

- **已扫完 7 个单变量**：ACTION 归一化、lr、训练步数、`--trim-done` 强度、重规划频率 R、
  `kl_weight`/`use_vae`、示范量（24 → 120 局）、`chunk_size` K ∈ {2,4,8}。
  **只有「裁掉 done 帧」+「K=2」这一组把抬起高度拉到 base 量级的一半**
  （`mean_max_rise` 0.0376 m = base-only 0.0764 的 49%，此前所有臂 ≤35%）。
- **否证清单**：VAE/KL 模态平均（§12，`kl_weight` 10→1 与 `use_vae=false` 都还是 2/20）、
  欠训练（§10b，40k 步比 20k 差）、示范量不足（§13，120 局在固定 20k 步下 raw 15/20→4/20、
  受控 2→1，R=1 也救不回来）。
- **最好的单臂是 `trimdone0 + K=2 + seed0`：受控成功 9/20**，且是**唯一**在门槛
  0.030–0.050 全域不变的臂（§14）；但**种子复现没通过**：同配方 seed0/1/2 = 9/20、2/20、0/20
  （均值 3.7/20 = 18%，极差 0–45%，§15）。
- **晋级条件第 1 条**：强口径（可重复的非零受控成功）**仍不满足**；弱口径（≥2 个训练 seed
  取得非零受控成功）**首次达到**（3 seed 中 2 个非零；此前所有配方 ≤1/3）。6-seed 补测在跑。
- **机制已定位到可测量的一步**（§16）：闭环里 teacher 式的 dz≥0.5 饱和爆发几乎从不发生
  （每局 0–0.25 帧），**全部抬升来自 0.005≤dz<0.5 的持续小正命令积分**；
  成功局与失败局的差别就是抓取后 `dz_tail` 是 +0.0247 还是 +0.0013。
  开环 `done_dz`（teacher 抬起后那段帧上的预测 dz）与闭环受控成功 Pearson **+0.866**（n=11），
  明显优于爆发幅度 `lift_dz`（+0.441）→ **种子方差不住在「会不会抬」，住在「抬起之后 dz 是否保持正值」**。
- **因此当前不建议对外声称任何能力结论**，只声称：官方 LeRobot ACT 的训练/评测闭环已跑通、
  可跨进程复现（同 ckpt 同题集逐局 `max_rise` 完全一致），且失败机制已定位到单个可测量。
- 下一步唯一优先级：`trimdone0 + K=2` 补到 6 个训练 seed 定级；「相位重加权采样」需要改
  lerobot 内部（官方 ACT 入口无此开关），**越出官方入口纪律，须先与监管确认**。

### 18:00 更新：输入契约落地后的当前口径（§17 是证据；**修正 17:15 的两条**）

- **17:15 说的「最好的单臂是 `trimdone0 + K=2 + seed0`：受控 9/20」作废**。补上
  `norm_input_blown_frames_frac` 后该臂 blown = **0.2120** > `INPUT_BLOWUP_TOL=0.05`、
  闭环 |x| 峰 93.4（阈值 12.47），门禁判 **`measurement_invalid`**（§17.2）。
  它是「测量无效」，不是「策略失败」，两者不得混写；9/20 不再作为率证据，
  §14 里「唯一在门槛 0.030–0.050 全域不变」的表述也随之失去载体。
- **17:15 说的「6-seed 补测在跑」已完成**：K=2 trimdone0 六个训练 seed 里 seed0 INVALID，
  **5 个测量有效** = 2 / 0 / 17 / 19 / 1，均值 **7.8/20 = 39%**、极差 **0–95%**，
  且**双峰**（三个 seed ≤2/20、两个 seed ≥17/20，中间无点，§17.9）。
  高分 seed 的 `mean_max_rise` 0.0685 / 0.0719 = base-only 0.0764 的 **89% / 94%**，
  flick = 0；低分 seed 的 raw 里 75–80% 是弹射。
- **晋级条件第 1 条**：弱口径（≥2 个训练 seed 取得非零受控成功）**已稳固满足**
  （5 个有效 seed 里 4 个非零，其中 2 个 ≥17/20）；强口径（**可重复**）**仍不满足**——
  同一配方在不同训练 seed 上给出 0/20 与 19/20，这是当前最主要的未解问题，
  比任何新杠杆都更值得投算力。
- **§15 的「K=1 突破（20/20、mean_max_rise 0.0800 超 base）」撤销候选资格**：
  seed1 = **0/20**，两个 seed 都测量有效，是真实种子方差不是数值事故（§17.8）。
- **L1（归一化炸穿）在官方线上是测量有效性问题，不是能力瓶颈**：16 个已测臂里只有 1 个超阈；
  blown_frac 与受控成功无关联（seed4 blown 0.0000 → 19/20，seed1 blown 0.0000 → 2/20）。
  能力瓶颈仍是 §16 的 **L2**（抬起后 dz 无停止条件、靠小正 dz 积分漂上去）。
- **肇事维与 B 定位的不同**：官方臂炸的是 `observation.environment_state[3]/[4]`
  （cube_quat 前两个分量，teacher 示范里方块从不倾斜 → 全域幅度仅 ±0.037，
  闭环 raw 偏差可达其 19 倍），**不是** B 在自研 60 维线上定位的 `state[7]/[9]/[11]`
  （`joint_pos_cos` 系，在 A 的 12 臂闭环里一帧都没炸过，§17.3）。
- **B §6.1 的 std 相对下限在官方臂上不咬合肇事维，四 seed 修复臂已否证它**：`floor(env[3]) = 3.34e-4`
  比 `std 7.72e-3` 小 23 倍，不抬；它只抬 `state[7/9/11/12/38]`。`trimdone0_stdfloor_minmax_k2_...seed{0,1,2,4}`
  实测：3 个共同有效 seed 上受控 2/0/19 → 1/0/14（**对照组 seed4 从 19/20 退到 14/20**）；
  seed0 的 blown 0.2120 → 0.0400 只是边缘通过、闭环 |x| 峰 93.4 → 94.7 没降（§17.12）。
- **截断因果探针：L1 在官方臂上的咬合强度 ≈ 0**。seed0 / seed2 / seed4 在 C=12.469（及 seed0 在 C=5.0）
  下受控 9/0/19 → **9/0/19**、`mean_max_rise` 四位小数不变、失败相位不变；seed4 一帧都没被截到
  （阴性对照，证明探针装置本身不改变结果）。因此增补二 §2 的重分类**是形式而非实质**：
  40 个门禁产物里 38 个未截断即测量有效，2 个 INVALID 在截断下数字不变（§17.13）。
  与 B 自研线的差异是量级差异：94% 帧越界 / |x| 峰 20403 / 多维 → 21% 帧 / 93.4 / 仅 2 维。
- **L1 在官方入口内已无可用修复**，剩下两条都要监管批准：(a) obs 契约变更（去掉或重定义
  `env[3]/env[4]`）= baseline 重置；(b) 自定义 processor 做训练+推理一致截断 = 越出官方入口。
  获批前 A 线不再自行开 L1 修复臂（§17.12 末）。
- **官方入口内做不到「训练/推理一致截断」**：`lerobot 0.4.4` 的 `normalize_processor.py`
  全文无 `clip/clamp`，MEAN_STD 纯线性、MIN_MAX 不外 clip（§17.5）。要做必须自定义 processor，
  **越出官方入口纪律，须监管批准**；`STATE=MIN_MAX` 不是修复（分母 `max−min = 0.056` 不为 0）。
- **待 B/D 裁定的口径问题**：per-dim 超界比例在 16 臂上是 **0.196–0.593，全部 > 0.05**，
  而全局阈值口径只有 1 臂超阈，相差 16 倍——因为全局阈值被 `state[34]` 单维（gain 12.47）主导。
  A 线两个口径都已写进产物，**未自行改动 B 的判据**（§17.7）。
- 下一步优先级：① 21 个缺字段历史臂的输入契约回填**已完成**（40/40 带字段，0 缺失）。
  增补一 §1 引用的 R4/R2/R1 三臂实测 blown 全为 0.0000 → **M2 的因果证据成立**；
  但 `k2 seed0` 的 R=2 与 R=1 **双双 INVALID**（blown 0.2120 / 0.1692）→ 增补一 §5.A① 的
  2×2 解耦矩阵 seed0 那一列整体作废，只剩 seed1 列（R2 2/20、R1 1/20）有效。
  ② 种子双峰的机制归因（actlog 逐帧 dz，15 臂在跑，把 §16 的 `done_dz` 预测器从 n=11
  扩到覆盖 0/20 与 19/20 两端）。③ 升级给监管裁定 L1 的 (a) obs 契约 / (b) 自定义 processor
  两条路径（§17.12 末）。K / replan / 数据量杠杆按增补二 §5.A② **继续暂停**。

### 19:35 更新：闭环归因扩围 + 全量重判到门禁 v1.2.1（§18–§20 是证据）

- **`dz_tail` 是受控成功的近单调预测器**：归因扩到 **17 臂 / 340 局**（闭合校验 0 违规），
  16 个测量有效臂上 `dz_tail` vs 受控成功 **Pearson +0.874 / Spearman +0.946**
  （§16 的开环 `done_dz` 只有 +0.866 / **+0.327**）。高分 5 臂 `dz_tail` 0.0248–0.0336，
  低分 11 臂 −0.0009–0.0184，**受控 4–9 的有效臂一个都没有** → §17.9 的双峰在动作侧有清晰对应量。
  §16 边界第 1 条改判：Spearman 低是**样本无变异**所致，不是机制不稳。
- **§16 结论 1 修正一处**：burst（dz≥0.5）不是绝对为零——17 臂平均抬升←burst 0.0027 m、
  ←bias 0.0327 m（占 8%），高分组占 13%（最高的 `k1 seed0` 有 0.0175 m 来自 burst）。
  准确写法是「抬起主体（≈87–100%）来自持续小正 dz 积分，teacher 式饱和爆发最多贡献 1/8」。
- **全量重判到单一门禁构建**：44 个官方臂 + 4 个 clipprobe 臂重判到
  `gate_version=v1.2.1 / gate_build=e4f5ec887788`（此前 41 份留档裁定停在 **6 个不同构建**）。
  **受控成功合计 132 → 132，逐臂 0 处变化，`gate_pass`/`measurement_valid` 0 臂变化**
  → 门禁升级不动任何能力数字。
- **失效模式整体改判（重要）**：`flick` 185 → **23**、`insufficient_lift` 30 → **208**、
  `over_lift` 恒 0。364 局 raw 成功 = 132 受控 + 208「夹住了但没抬够」+ 23 真脱手 + 1 provisional
  → **非受控 raw 成功里 94.5% 是抬起高度不够，不是脱手**；37 个测量有效臂、740 局里真 flick 只剩 **2 局**。
  本文档 §17 及之前所有「flick N」都是 v1.1 口径（含 insufficient_lift），归因方向据此更正。
- **门槛敏感性刷新**（39 strict / 37 有效 / 780 局）：合计 199/167/**132**/111/95；
  ±0.005 带内 **4 robust / 21 sensitive / 12 always_zero**。robust 臂 = `k2 seed3`（**全域恒 17/20**）、
  `k2 seed4`（19/19/19/19/18）、`k2 seed5`、`k8 seed0`。与 B 的 12 臂表重叠 11 臂，
  `final_rise=0.040` 上 **11/11 数字完全相同**（两线各自 import 同一 `judge_file`，属独立复算）。
- **INVALID 共 7 臂**：5 个早段盲产物（缺输入契约字段，v1.2 §2.6 新增）+ 2 个 blown 超阈的 `k2 seed0`。
- **交接单 2（residual 臂）执行结果：B 的「补 2 个字段即可恢复裁定」只成立一半**。补字段重跑后
  逐局 `max_rise` 与 09-24 留档完全相同（跨版本可复现）；第一次重判出现**门禁假阴性**——
  20 局全被判 `flick`，唯一失败的 check 是 `end_phase`，因为该产物只写 `phases` 不写 `phase_trace`，
  `classify_phase_field` 退回 per-frame 规则、状态机的 `'done'` 不在 `{hold, grasp}` 里。
  按参考实现 `audit_lift_base_truth.py:66` 补写 `phase_trace` 后 → **`controlled_success` 20/20、
  flick 0**；但仍判 `measurement_invalid`，因为 SAC 无归一化、`norm_input_blown_frames_frac`
  没有对应量（**口径缺口，已上报 B/D**，A 不自行绕过）。这条臂本质是
  `clip(a_base + 0.25·a_residual, −1, 1)` 的**复合 policy**，已显式声明 `execution_constraints`，
  门禁自动标 `composite_policy=true` → 20/20 不得当作 learned-from-scratch 能力引用（§20.1）。
- **B 线 14 条关键结论逐条核对完毕（§20 表）**：8 条符合、3 条「机制成立但量级/影响面不成立」、
  2 条不符合（肇事维、std 下限在官方线咬合）、1 条需修正（交接单 2）。
  最重要的分歧是 #6：B 线的 L2 后果是 **over_lift 过冲**（clip3 12/20），A 官方线是
  **insufficient_lift 不足**（over_lift 0/44 臂）——同一个 dz 条件均值偏置，落在 0.04 门槛哪一侧的两个表现。
- **优先级申请（§20.3，待监管裁定）**：P0 种子双峰归因（只做归因不做修复）、
  P1 L2 修复方案设计（三条杠杆都属 baseline 重置，需批准；预登记判据 = `dz_tail` 进入 0.024–0.034 带）、
  P2 与 B 共担 `final_rise` 直方图报告；lr1e-4 塌缩臂与 K/replan/数据量杠杆降级或继续暂停。

### 20:40 更新：blown 口径单一来源化结案 + K=1 六 seed 全谱 + 盲臂补测（§21 是证据）

- **评测器补丁验收通过（只追加键，不改既有口径）**：blown / oor 判定收敛到单一函数
  `blown_frame_stats()`，源码指纹 `blown_metric_impl = 52eae25ee2d7` 写进产物
  `input_contract`。恒等回归（新工具 `scripts/a_eval_idempotence_check.py`）**全键递归比对 PASS**：
  同 ckpt（`k2 seed3`）重跑 20 局 vs 留档，只有 `rows[].elapsed_sec` 20 处不同 + 2 个新增键，
  逐局 `max_rise / final_rise / phase_trace / held_at_end / norm_input_*` 与全部顶层汇总键**逐位相同**。
- **监管 §12 的诊断需要改判：不是「分母或参与维不一致」，是「轨迹分岔」。**
  H1 分母 —— 逐局 `norm_input_frames_measured` 全等，**否证**；
  H2 参与维/阈值 —— 在「截断从未生效」的 **52 局**上 `absmax` 与 `blown_frac` **逐位相等**，**否证**；
  H3 轨迹分岔 —— **成立**，且因果干净（没有任何一局在截断未生效时分岔）。
  0.2120 与 0.1180 那 **0.0940 的差 100% 来自 6 局分岔**，未分岔的 14 局贡献恰好 0.0000。
- **D 的「20 局 `max_rise` 逐位相同」独立复算成立**，但「轨迹完全一致」只在 `max_rise` 这个**投影**上成立：
  那 6 局的 `max_rise` 全为 0.0（方块从未抬起），而 `phase_trace` 从第 48/53/56/75/114/138 帧分岔、
  `final_rise` 有 4 局不同（5012/5014/5016/5018）。**只比 `max_rise` 结构上看不见这种分岔。**
- **[0.03,0.08] 带臂重测完成**（全仓唯一 1 臂 = `trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`）：
  重测产物与留档全键递归比对 PASS，`mean_blown_frames_frac` 仍 **0.0400**、受控仍 **16/20**、
  v1.2.1 重判 `gate_pass=True` → §12「暂不可采信」的技术前提（口径未单一来源）已消除，提请 D 解除该保留。
- **5 个盲臂补测完成，INVALID 7 → 2**。它们的缺陷比 §3 记的更大：不只缺 `input_contract`，
  还缺 **10 个逐局门禁字段 + 7 个顶层键**（旧评测器产物）。补测后 **5/5 在共有字段上逐位相同**
  （各新增 19 个字段），全部转 `strict` + `verified_ok` + `measurement_valid=True`、blown 全 **0.0000**；
  其中 `train24_lr1e-5_actionminmax_s20k_seed2` **新出 1/20 受控**（此前因 INVALID 不得引用）。
  剩下 2 个 INVALID 是真超阈的 `k2 seed0`（0.2120）与 `k2 seed0_replan1`（0.1692），维持。
- **跨线阈值实测同源、但规则不同**：A 按 ckpt 现算的 train24 族阈值 = **23.8450**（= B 的常量 23.85），
  闭环 absmax **16.13**（= B 的 16.1）、per-dim oor **0.217~0.980**（= B 的 0.217~0.980）。
  但 trimdone0 族的 per-ckpt 阈值是 **12.469445** → 两套规则只在**同族数据**上恰好一致，
  跨族引用 blown 数字必须写明阈值取自哪个 ckpt，否则 0.05 这条容差不是同一把尺子。
- **K=1 六 seed 全谱（§9.A④ 交付）**：受控 **20 / 0 / 0 / 2 / 0 / 0**，均值 **3.67/20**、极差 **0~20**、
  非零 2/6、≥半数 1/6；6 臂全部 `measurement_valid`、blown ≤ 0.0012（**L1 完全不涉及**）。
  **§8 收窄条件第 1 条不满足**；K=2 族同样不满足（只有 seed3=17、seed4=19 两个 seed ≥半数）
  → **两族都不得上调，晋级条件第 1 条维持「部分满足」**。
- **K=1 与 K=2 的失败形态不同类**：K=1 的 4 个 0/20 臂是 `raw=0 / insuff=0 / flick=0`、
  `mean_max_rise` ≈ 1e-4 m 的**整体塌缩**（连 env 级成功都没有）；K=2 的失败主要是
  `raw>0` 但 `insufficient_lift`（夹住了、抬到 3.5–4.5 cm 就停）。把两族的 0 分当同一种失败读会误判修复方向。
- **§9.A⑤ 结案**：K=1 四个 0/20 臂的 `dz_mean_tail` **全为负**（−0.0009 / −0.0017 / −0.0138 / −0.0030），
  `dz_pos_frac_tail` 只有 **0.074–0.243**（对照 seed0 = 0.99925、seed3 = 0.94650）
  → 「0/20 是负偏置积分」成立；`dz_pos_frac_tail` 比 `dz_tail` 更干净地把 6 个 seed 一分为二（0.95+ vs 0.24−）。
- **归因扩到 21 臂 / 420 局**：闭合违规 0；`dz_mean_tail` vs 受控成功 **Pearson +0.773 / Spearman +0.944**
  （20 个有效臂）；**受控 4–9 的臂仍为 0 个**（双峰没被填平，只是两端各多了点）。
  burst 占比最高仍是 `k2 seed3` 的 **23.2%**，21 臂合计 **7.2%**，**无一臂 >50%**
  → §8 上调条件第 4 条在现有数据上**不可达**，维持 ADR-A-005 的提请。
- **与 B 线 19:36 两份文档交叉核验，无冲突**：B 的 44 臂重判与 A 的 `regate_current/` **逐格 0 差异**
  （两条独立实现路径 import 同一 `judge_file`）；B 的强臂截断探针 `L1_no_bite`（`k2 seed4`，C=3.0）
  与 A 核对该臂「截断从未生效、0 局分岔」一致。**但 A 的六 seed 数据改变了 B §4 的一个族均值**：
  `k1` 族从 10/20（n=2）降到 **3.67/20（n=6）**，按 B 自己的表述纪律（§4「任何单臂引用都属于挑 seed」），
  B §7 引为强结果的 `k1 seed0 = 20/20` 只能以「族均值 3.67/20 + 摆幅 0~20 + n=6」的形式出现。
- **A 线登记落地**：`work/decisions/decisions_20260928_A.md`（ADR-A-001 口径追加 / ADR-A-002 盲臂作废范围与补测 /
  ADR-A-003 两条 L1 路径只登记不动手 / ADR-A-004 §9.A 六条 ack / ADR-A-005 三项提请裁定）。

### 22:15 更新：唯一权威表落盘 + 双峰分岔定位（§21.10 改判重写、§22 是证据）

- **A-1 唯一权威表已落盘**（`arms_summary.json`，`schema_version=2`，唯一生产者
  `scripts/summarize_lerobot_act_arms.py`）：每行带 `validity_class` / `superseded_by` /
  `blowup_threshold_source` / `probe_exoneration`（裁定 10 的 5 条准入**在代码里断言**）/
  `labels_reportable`（裁定 8 推广 = 裁定 14）/ `gate_source_kind`；`meta` 里给**五套显式分母**
  与**四个带 scope 标签的合计**。与监管增补五 §3 的权威表**逐格对账一致**：
  48 臂 / 960 局 / raw 377 / 受控 **135** / `insufficient_lift` **235** / `flick` **7** / `over_lift` 0 /
  `provisional_pass` 0，有效 46 / 无效 2，免罪后 **47 / 1**、三分类 **24/22/2 → 25/22/1**。
- **`134 / 219 / 23` 正式作废**（blindfix 前口径）：本文档、`daily_report.md` 与 A 的收尾报告里
  这三个数一律标注为「blindfix 前口径」，不得再当现值引用。可引用的 `flick` 只剩 **2 局 / 920**。
- **裁定 16 构建纪律已写进表里**：本表是 **v1.2.1 / `e4f5ec887788` / spec `494d5f5babf9`** 口径；
  B 的 v1.3（工作树 build `4f20b3ec9130`）落地并全量重判后**重跑一条命令**即可刷新，届时本表降级为历史口径。
  两个登记册（`b_blown_impl_grandfathered` / `b_probe_exonerations`）填好前不得用 v1.3 全量重判。
- **A-2 双峰分岔定位跑完**（预登记 21:14:53 冻结 → 首批 4 臂 × 2 ckpt → 扩围 8 臂 × `010000`，共 320 局）：
  - **R5 先行门槛 PASS**（4/4 臂 `020000` 重跑与留档**逐局**一致）⇒ 不是评测器/环境漂移；
  - **K=1 族 → R2**：分岔**发生在 10k–20k 之间**（`010000` 两臂同判 `NONPOS`，`020000` 分开）；
    三切点稳定、无 R7 敏感格 ⇒ 可独立陈述；
  - **K=2 族 → R1**：分岔**不晚于 10k**，且**必须带「级别归属对阈值敏感」标注**
    （`k2 seed2@020000` 的 `dz_pos_frac_tail=0.86700` 落在 `[0.85,0.95]`）；但 R1 在 0.85/0.90/0.95
    三种切法下**都成立**（分离由 `010000` 的 1.00000 对 0.74575 提供）⇒ D 预警的「R1 是切点造成的」未被证实；
  - **R6：两族不一致 ⇒ 不合并跨口径主张**，并触发扩围（§7 条件 2）。
- **本节最重要的改判**：`k2 seed2` 在 **10k 是 15/20**（`HIGH`、`mean_max_rise` 0.06412 m），到 **20k 变 0/20**；
  `k2 seed4` 反过来（10k 5/20 → 20k 19/20）。扩围后 **`HIGH@10k` 与 `HIGH@20k` 的臂集合重叠 = 0**
  （K=2：`{seed2,seed5}` → `{seed3,seed4}`）、「受控 ≥ 半数」集合也**零重叠**
  ⇒ 「seed 单独决定成败」改判为「**seed × checkpoint 共同决定**」，`checkpoints/last`（=020000）
  作为唯一交付点是**未被验证的选择**。
- **晋级条件① 在两个时间点都不满足**（增补四 §8：同族 ≥3 seed 受控 ≥ 半数）：
  10k 上 K=1 **0/6**、K=2 **2/5**；20k 上 K=1 1/6、K=2 2/6 ⇒ **换 checkpoint 也满足不了条件①**，
  「部分满足」维持，且现在有两个时间点的证据。
- **R4 首次触发**：`k1 seed1@010000` blown **0.0532 > 0.05**（阈值 **12.469445**，取自该 ckpt 自己的
  normalizer stats）⇒ **该时间点测量无效、能力未知**，其 `6/20` 不得引用；`k1 seed3@010000` blown 0.0473
  （容差的 94.6%）登记为**近阈**。**不得**写成「炸穿导致失败」（裁定 12）。早期 ckpt 更容易 OOD 的预期被证实。
- **判据的样本外表现（阈值一字未改）**：`dz_pos_frac_tail ≥ 0.9` 在 10k 上仍把受控成功均值分开
  （**11.0/20** 对 **1.167/20**，约 9.5 倍）且无假阳性；但 `dz_mean_tail ∈ [0.024,0.034]` 的**带上界低估能力**
  —— `stdfloor k2 seed0@10k`（0.03787、实测 **18/20**）被判 `POS_BIAS` 而非 `HIGH`。要改阈值必须**新写预登记**。
- **A-3 已移交 B**（`docs/a_handoff_to_b_gate_vocabulary_20260928.md` + `v13probe/` 12 份算例，A 不改门禁）：
  在 B 的 v1.3 工作树上实测 —— **裁定 8 已修**（residual 缺 `phase_trace` → `unjudged=20`，不再 `flick=20`）；
  **裁定 14 未修**（5 个 `partial` 产物仍输出 `flick 11 / 3 / 2`、`unjudged=0`，而 v1.3 自己已算出
  `phase_vocab_status="absent_field"` 与 `field_class="partial"`，只是没用来弃权）；
  `strict` 侧 **无误伤**（11/3/2 个 `insufficient_lift` + `seed2` ep5001 升级 `controlled_success`、`gate_pass=true`）。
- **A-4 维持暂缓**（用户指令 + 增补五 §8 D 认可）：teacher 去饱和与 L1 路径 (a)/(b) 不动。
  A-2 的结果**加强**了暂缓理由 —— 换 checkpoint 都满足不了条件①，说明卡点不在「baseline 选得不好」，
  此时重置 `RISE_CAP` / `FINAL_RISE_MIN` 只会连做两次重置并废掉 48 臂比较集。顺序仍是 **A-2 → 再议**。
- **A-5 已落地（不花 GPU、不重跑 09-24）**：`scripts/train_residual_lift.py` 前瞻落盘 `obs_stats.json`
  ——`normalization="none"`、训练期 raw obs **60 维逐维 absmax**、闭环越界比例与 `bound_satisfied`、
  threshold 来源（裁定 9 的 ②③④，「只有声明不算」）。200 步冒烟实测：train 211 obs、
  闭环越界 1369/25200 = **0.054325 > 0.05** ⇒ `bound_satisfied=false`（机制生效）。
  09-24 的 residual 臂没有这份证据 ⇒ **维持 INVALID / `not_applicable_unnormalized`**。
- **表述纪律自查（增补四 §11-A②）**：全文档清查「炸穿导致…」型因果句 —— **0 处违规**
  （现存的 4 处都是「**不得**反推炸穿导致失败」的禁令句本身）；「轨迹完全一致」只以**被否证**的形态出现
  （§20:40 更新与 §21.4：只在 `max_rise` 投影上成立）；「blown 口径不一致」已被 §21.3 逐局否证并留档为证据。

### 22:40 更新：A-2 的 gate_build 漂移已处置（§22.9 / 预登记 §13 是证据）

- **问题**：`ckptseq/` 的 16 份 gate 横跨 **7 个 `gate_build`**（B 在 A-2 跑动期间实时升级门禁，
  `GATE_BUILD` = 脚本内容哈希），而预登记 §6 与 §21.10 的 48 臂权威表都锚在 **v1.2.1**。
  处置前，§22 的跨臂 / 跨时间点（10k vs 20k）比较**缺单一构建这个前提**。
- **处置**：`git archive 0137b33` 建钉扎快照 `runs/infra/lerobot_act_env_20260928/gate_v121_pinned/`
  （复刻 `scripts/`+`docs/` 布局，自报 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`）→ 旧 16 份 gate
  `mv` 进 `ckptseq/gate_build_drift_backup/`（禁 `rm`）→ **只重判、不重跑评测**（16 份 actlog 一字节未动）。
- **结果**：单一构建断言 **PASS**（16/16，原 7 个指纹 → 1 个）；**实体裁定 16/16 完全一致**，
  含 `per_episode` **逐局** verdict（320 局）；14 份仅指纹变化，10 份只有表述/溯源差异。
  **权威视图 `divergence_verdict_all.json` 只有 29 处字段变化 = 14 `gate_build` + 14 `gate_version` + 1 时间戳**
  ⇒ **§22.8 的 6 条结论、§21.10 的权威表口径全部维持原文**。
- **可以不重跑评测的理由是机制性的**：blown 阈值由评测器写进 actlog 每行，门禁只比 `INPUT_BLOWUP_TOL=0.05`；
  v1.2.1 不读 `configs/` ⇒ 探针免罪/登记册的有无都不影响本批（实测 16 份里 `probe_exonerated` **0 份为真**）。
- **新增 caveat**：`k1 seed3@010000` blown **0.0473**，距 0.05 容差仅 **0.0027**、落在 v1.3 的
  `DISPUTED_BLOWN_BAND (0.03,0.08)` 内 ⇒ 依赖该时间点的任何主张必须带此标注
  （它在 §22 只作 `NONPOS` 出现，不参与分离主张）。`k1 seed1@010000`（0.0532）两构建都判 INVALID，**R4 成立**。
- **新增产物**：`scripts/a_gate_build_drift_check.py`（可复现的漂移检查 + 逐臂逐局 diff）、
  `ckptseq_batch1_pinned/`（全 symlink 影子目录，给出**未污染**的预登记首批视图）、
  `ckptseq/build_drift_remediation_record.json`、`ckptseq/build_drift_remediate_diff.json`。
- **48 臂权威表回归**：重跑 `summarize_lerobot_act_arms.py` 与留档 `arms_summary.json`
  **逐字节相同（除 `generated_at`）** ⇒ A-1 未被扰动。

## 环境规格

两个 venv，都在本机 overlay 上（`/root` 不持久，容器重建后用 `scripts/install_lerobot_act_env.sh`
一键重建；版本锁已存到仓库里）。

| 用途 | 路径 | 关键版本 |
|---|---|---|
| 训练 / 离线审计 | `/root/venvs/lerobot_act` | python 3.11.9, torch 2.6.0+cu124, torchvision 0.21.0+cu124, lerobot 0.4.4, numpy 2.2.6, gymnasium 1.3.0, CUDA 12.4 |
| 闭环真值评测 | `/root/venvs/lerobot_eval` | 同上 + numpy 2.4.6, gymnasium 1.2.3, mujoco 3.9.0, robosuite 1.5.2, py_trees 2.6.0 |

版本锁：`runs/infra/lerobot_act_env_20260928/requirements.lock.txt`、
`requirements.eval.lock.txt`。GPU：NVIDIA A800-SXM4-80GB，driver 590.48.01。

分开建的原因：评测必须在**同一个解释器**里同时能 import lerobot（加载官方 checkpoint）和
robosuite（跑真值环境），否则权重要跨环境搬；但训练环境要保持干净，不让 robosuite 那条
依赖链（mink/numpy pin）污染已验证的组合。

## 门槛验证（09-24 审计要求的两条命令）

```bash
/root/venvs/lerobot_act/bin/python -m lerobot.scripts.lerobot_train --help   # OK，2414 行 draccus 帮助
/root/venvs/lerobot_act/bin/python -c "from lerobot.policies.act.configuration_act import ACTConfig; \
from lerobot.policies.act.modeling_act import ACTPolicy; print('OK')"        # OK
```

`--help` 全文留档：`runs/infra/lerobot_act_env_20260928/train_help.txt`。

## 09-24 那串 ImportError 的真正根因

不是 transformers 装坏了，也不是缺 diffusers。`runs/infra/lerobot_official_env/` 是用
`--system-site-packages` 建的，于是 `/opt/conda` 的 TensorFlow + jax 被拖进 import 链：
jax 在 `np.dtypes.StringDType` 上抛 AttributeError（numpy 版本不匹配），transformers 的惰性
导入把这个错误包装成 `cannot import name 'PreTrainedModel' from 'transformers'`，看起来就像
transformers 本身有问题。补装 `AutoProcessor` / `diffusers` 只会让报错名字换一个。

另外 `lerobot==0.4.4` 的核心依赖里**根本没有 transformers**（只有 groot / pi0 这类 VLA 才要），
ACT 路线不需要它。所以 09-24 那条「补 transformers」的路是岔路。

修法：干净 venv（`include-system-site-packages = false`）+ 满足官方 pin 的 torchvision。

## 本轮踩到的坑（都已在安装脚本里绕过）

1. **系统包污染** —— 见上，必须不带 `--system-site-packages`。
2. **torchvision pin** —— lerobot 0.4.4 要 `torchvision>=0.21.0,<0.26.0`，系统只有 0.19.1。
   装 torch 2.6.0 + torchvision 0.21.0（cu124）即满足，且 torch 声明范围 `>=2.2.1,<2.11.0` 也过。
3. **pip 走代理下大 wheel 只有 ~0.7 MB/s**，同一条 URL 用 curl / uv 是 6.6–39.8 MB/s
   （实测：664MB cudnn 用 curl 16 秒下完；pip 同文件 20 分钟没下完）。所以统一用 `uv pip install`。
4. **`pip.conf` 的 `find-links = mirrors.aliyun.com/pytorch-wheels/cu124/`** 会把 torch 解析成
   `+cu124` 本地版本并从那个慢源拉；**`index-url = mirrors.ustc.edu.cn`** 的文件下载会 302 到
   `mirrors.tuna.tsinghua.edu.cn`，对本机返回 403。uv 不读 pip.conf，显式指定 aliyun PyPI 索引即可。
5. **`--policy.push_to_hub` 默认是 True**（lerobot 0.4.4），不给 `--policy.repo_id` 就直接
   `ValueError: 'policy.repo_id' argument missing`。必须显式 `--policy.push_to_hub=false`。
6. **`--eval_freq` 是「gym 环境 rollout」，不是数据集验证**：`lerobot_train.py` 里
   `if cfg.eval_freq > 0 and cfg.env is not None`。没有 env 配置时必须 `--eval_freq=-1`，
   验证走项目自己的独立评测。
7. **`--policy.normalization_mapping.ENV=MEAN_STD` 这种点号写法 draccus 不认**
   （`unrecognized arguments`），要传整个 JSON 字符串。
8. **`ACTConfig` 默认的 normalization_mapping 只有 VISUAL/STATE/ACTION，没有 ENV**，
   而 `NormalizerProcessorStep` 是 `norm_map.get(feature_type, IDENTITY)` —— 缺 ENV 时
   **静默不归一化**。必须显式补 `"ENV":"MEAN_STD"`，否则物体状态那 10 维是裸值进网络。
9. **官方 `from_pretrained` 加载自己存的 checkpoint 会失败**：`PreTrainedConfig.from_pretrained`
   在 `config.pop("type")` **之前**就先 `draccus.parse(cls, config_file)`，于是抛
   `DecodingError: The fields `type` are not valid for ACTConfig`。绕过方式见
   `scripts/_lerobot_act.py`（复刻它 pop 之后的逻辑，再把 config 显式传给
   `ACTPolicy.from_pretrained(..., config=cfg)`）。
10. **`robosuite 1.5.2 -> mink 0.0.5 -> numpy<2.0.0`** 与项目口径 numpy 2.4.6 冲突，正常解析直接
    判 unsatisfiable。mink 的 pin 是陈旧的（继承环境里 numpy 2.4.6 实测能跑），用
    `uv pip install --override` 强制 numpy；只在评测环境这么做。
11. **`add_frame` 不接受 `timestamp` 字段**（`ValueError: Extra features: {'timestamp'}`），
    它自己按 `frame_index / fps` 生成。源数据的 timestamp 就是 `i/20.0`，两者逐帧一致，
    最大误差已量出并写进各数据集的 `build_manifest.json`。

## 关键适配：60 维观测拆成两个官方 key

官方 `ACTConfig.validate_features()` 要求输入里**至少有一个 image 或 `observation.environment_state`**，
只给 `observation.state` 会直接 ValueError。而项目侧的 60 维 state 观测按
`docs/notes_stage1.md:14` 的记录正好是 `robot0_proprio-state`(50) + `object-state`(10)，于是：

| 项目侧 | 官方 key | 维度 | FeatureType |
|---|---|---|---|
| `observation_state[0:50]` | `observation.state` | 50 | STATE |
| `observation_state[50:60]` | `observation.environment_state` | 10 | ENV |
| `action[0:7]` | `action` | 7 | ACTION |

这不是改名糊弄：50/10 的切分有 robosuite 观测构成依据，语义上 proprio 与物体状态本来就该分开。
训练后 `train_config.json` 里记录的是
`input_features = {observation.state: STATE[50], observation.environment_state: ENV[10]}`、
`output_features = {action: ACTION[7]}`。闭环评测时用同一张映射表把环境观测切开后喂进去
（`scripts/eval_lerobot_act_runtime.py` 的 `observation_key_map` 字段会写进结果 JSON）。

action chunk **不在数据集里物化**：官方用 `delta_timestamps` 在 `__getitem__` 里取未来
`chunk_size` 帧，等价于 interchange 的 `action_chunk`。等价性已逐元素验证（见下）。

## 数据集重建（interchange -> 官方 v3.0）

脚本：`scripts/build_lerobot_act_dataset.py`（用官方 `LeRobotDataset.create/add_frame/save_episode`，
统计量、parquet 分片、episodes/tasks 元数据全部由官方代码生成，不手写）。

| 输出 | split | 局数 | 帧数 | chunk 等价性 |
|---|---|---|---|---|
| `runs/infra/lerobot_act_lift_v30/overfit_ep0` | train（仅第 1 局，seed 1000） | 1 | 300 | 297/297 全对 |
| `runs/infra/lerobot_act_lift_v30/train24` | train `1000-1023` | 24 | 7200 | 7128/7128 全对 |
| `runs/infra/lerobot_act_lift_v30/val8` | validation `2000-2007` | 8 | 2400 | 2376/2376 全对 |

每个目录都有 `build_manifest.json`，记录源文件 sha256、feature 映射及理由、fps、
`codebase_version=v3.0`、lerobot 版本、timestamp 一致性误差。
test split（`5000-5019`）**没有**转成数据集 —— 它只在闭环评测里由 `reset_contact(env, seed)`
现场出题，不进训练、不进 normalization 统计，避免泄漏。

## 官方 ACT 训练

统一配置（两条 lr 臂只差 `--policy.optimizer_lr`）：

```text
policy.type=act  chunk_size=4  n_action_steps=4  temporal_ensemble_coeff=None
use_vae=True  kl_weight=10.0  dim_model=512  dropout=0.1（全部官方默认）
normalization_mapping={STATE,VISUAL,ENV,ACTION}=MEAN_STD（第 5 条臂只把 ACTION 改成 MIN_MAX）
push_to_hub=false  device=cuda  batch_size=8  steps=20000  seed=0
eval_freq=-1（无 gym env）  save_freq=10000  num_workers=4  wandb 关闭
```

`num_learnable_params = 40,170,695`（40M），A800 上 ~33–38 step/s，单臂 20k 步约 9–10 分钟。

| 臂 | 数据集 | ACTION 归一化 | lr | 末 loss | checkpoint |
|---|---|---|---|---|---|
| `overfit_ep0_lr1e-5_s20k` | 单局（seed 1000） | MEAN_STD | 1e-5（官方 preset） | 0.103 | `checkpoints/last/pretrained_model` |
| `overfit_ep0_lr1e-4_s20k` | 单局（seed 1000） | MEAN_STD | 1e-4 | 0.088 | 同上 |
| `train24_lr1e-5_s20k` | train 24 局 | MEAN_STD | 1e-5 | 不可归属（见下注） | 同上 |
| `train24_lr1e-4_s20k` | train 24 局 | MEAN_STD | 1e-4 | 不可归属（见下注） | 同上 |
| `train24_lr1e-5_actionminmax_s20k` | train 24 局 | **MIN_MAX** | 1e-5 | **0.019** | `checkpoints/020000/pretrained_model` |

注：两条 MEAN_STD 的 train24 臂并行跑、stdout 混写进同一个 `/tmp/lr_train24.log`，
行内没有臂标识，因此末段 loss（最后两条是 0.118 / 0.095）**无法按臂归属**，本文不做归属声明。
MIN_MAX 臂是单独一条日志（`/tmp/lr_train24_minmax.log`），末 loss 0.019 可信。

checkpoint 内容是**正式产物**，不是自研 `.pt`：`model.safetensors`、`config.json`、
`train_config.json`、`policy_preprocessor.json` + normalizer safetensors（**stats 已烘进
checkpoint**）、`policy_postprocessor.json` + unnormalizer safetensors，外加
`training_state/`（optimizer / rng / step）。09-24 审计里「未发现正式 LeRobot ACT checkpoint」
这一条就此关闭。

## 单局 overfit 的开环动作对齐审计

脚本：`scripts/audit_lerobot_act_overfit.py`（只读；推理链路照官方 `lerobot_eval.py`：
`preprocessor(obs) -> policy.select_action/predict_action_chunk -> postprocessor`）。

| 指标（vs teacher，同一局 seed 1000） | lr 1e-5 | lr 1e-4 |
|---|---|---|
| 逐帧 mean abs err（7 维平均） | **0.006577** | 0.031438 |
| 逐帧 max abs err | 1.0004 | 2.0002 |
| chunk 首动作 mean abs err | 0.038544 | 0.162899 |
| gripper 符号一致率 | **1.000** | 0.940 |
| droll / dpitch / dyaw max err | 0.0000 / 0.0000 / 0.0000 | 0.0000 / 0.0000 / 0.0000 |
| dx / dy / dz mean err | 0.0038 / 0.0014 / 0.0321 | 0.0261 / 0.0035 / 0.0703 |
| request 数 / 激活帧 | 75 / 300（无 partial、无 deadline） | 75 / 300 |

读法：

- max err ≈ 1.0 不是全面失准，而是集中在 request 11–12（frame 44–48，approach→descend 转折）
  的 dz 那一维；其余 300 帧的平均误差是 0.0066。lr 1e-4 那条在**第 0 个 request** 就把
  gripper 符号学反了（err 2.0 = 从 -1 翻到 +1），所以 overfit 不是「lr 越大越好」。
- 因此结论口径是：**官方 ACT 已能在单局上复现 teacher 轨迹的主体（旋转维精确、gripper 符号
  全对、平均误差 6.6e-3），但没有做到逐帧精确复现**，`teacher_action_reproduced_at_1e-2 = false`。
- 这是**离线开环对齐**，不是闭环成功。它证明「数据 -> 官方模型 -> 动作」这条链是通的、
  学到东西了；能不能真抓起来要看下面的闭环真值评测。

结果 JSON：`runs/infra/lerobot_act_env_20260928/overfit_alignment_overfit_ep0_lr1e-{5,4}_s20k.json`
（含 checkpoint sha256、逐 request 记录、execution_mask、partial/deadline/takeover 标记、
`td_eligible=false / bc_eligible=false` 隔离标记）。

## 闭环真值评测（20 局，pinned seeds 5000-5019）

脚本：`scripts/eval_lerobot_act_runtime.py`，口径与 `scripts/eval_act_lift_truth.py`（自研 MLP ACT
用的那个）逐项对齐，环境走 `harness/env_factory`（构造期钉死物体几何
`PINNED_OBJECT_SEED=20260923`，出题走 `reset_contact`），抓取真值走 `grasp_truth_fn`
（robosuite `_check_grasp`），horizon 300，K=4 一个 request 对应 4 个真实 20 Hz tick，
不启用 guard/recovery（救场数记 0）。

三条 learned 臂同口径各 20 局（seeds 5000–5019、`PINNED_OBJECT_SEED=20260923`、horizon 300、
K=4、无 guard/recovery），外加一条 scripted base-only 作参考上界（B 线复现，同口径）：

| 臂 | ACTION 归一化 | success_raw | grasp_verified | success_grasp_verified | success_rise | mean_max_rise (m) | 失败相位 | clip 帧 | max_preclip_abs 中位 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| `train24_lr1e-4_s20k` | MEAN_STD | 0/20 | 0/20 | 0 | 0 | 0.0000 | approach×20 | 6000/6000 | 1.0002（常数输出） |
| `train24_lr1e-5_s20k` | MEAN_STD | 2/20 | 20/20 | 2 | 0 | 0.0021 | grasp×18 | 2417/6000 | 1.1550 |
| `train24_lr1e-5_actionminmax_s20k` | **MIN_MAX** | **11/20** | **20/20** | **11** | **0** | **0.0134** | grasp×9 | 5986/6000 | 1.1659 |
| 参考：scripted base-only（非 learned） | — | 20/20 | 20/20 | 20 | — | 0.0764 | 无 | — | — |

flick 门禁（`scripts/b_flick_check.py`，`--rise-cap 0.15 --hold-phases hold,done,grasp`）：三臂
`flick = 0`，MIN_MAX 臂 11 局成功全部判为 controlled_success，`flick_frac = 0%`。
证据：`runs/infra/lerobot_act_env_20260928/flick_gate_three_arms.json`。
已知盲区：本评测器不输出 `final_rise`，门禁第三条判据退化成只看 `phase_trace`（脚本自己报
`NO-blind`），所以「不是 flick」这一条是**弱判据下成立**，不是完整判据下成立。

读法（按强度递减）：

1. **ACTION 归一化是本轮最大的单变量收益。** 同数据、同 lr、同步数、同 seed、同评测口径，
   只把 ACTION 的 `MEAN_STD` 换成 `MIN_MAX`：`success_raw` 2/20 → 11/20（5.5×），
   `grasp_verified` 保持 20/20，失败相位 18×grasp → 9×grasp，末 loss 降到 0.019。
   这与训练前的诊断一致——teacher 动作在 ±1 饱和（如 `[1.0,-0.22,-1.0,0,0,0,-1.0]`），
   MEAN_STD 下「恒输出均值」是退化解，lr 一大就塌缩（lr1e-4 臂每帧输出常数、
   `max_preclip_abs` 恒 1.0002、grasp 0/20）；MIN_MAX 把数据 min/max 映到 ±1，
   饱和的 teacher 动作变成可表达的边界值。
2. **11/20 只说明过了 robosuite 真值线，不等于「学会抬起」。** 11 局成功的 `max_rise`
   是 0.0094–0.0379 m（中位 0.0255），**全部低于 `success_rise` 的 0.04 m 阈值 → `success_rise = 0/20`**；
   全臂 `mean_max_rise = 0.0134 m`，只有 scripted base-only（0.0764 m）的 17.5%；
   相位上从未进入 `hold`（需 rise > 0.04），11 局局末相位都是 `grasp`。
3. **高 clip 率必须与 `max_preclip_abs` 一起读。** MIN_MAX 臂 5986/6000 帧被 clip，
   但 `max_preclip_abs` 中位 1.166（区间 1.14–1.23）是「贴边界饱和」；塌缩臂同样是
   6000/6000 clip，`max_preclip_abs` 却恒为 1.0002（常数输出）。同一个 clip 计数在两种
   情况下含义相反，单看 clip 会误判。

因此本节能声称的是：**闭环仿真真值下，learned 官方 ACT 首次拿到非零、非弹射的抓取成功
（11/20，grasp 20/20），且已定位到「ACTION 归一化」这个可复现的单变量原因。**
不能声称的是：学会抬起（`success_rise 0/20`、rise 仅 base 的 1/6）、可重复（只有 1 个训练 seed）、
以及任何真机结论。

## 训练 seed 复现、数据失衡诊断与裁剪对照（15:50 起）

### 1. MIN_MAX 配方的三 seed 复现：不成立

同数据（train24）、同归一化（ACTION=MIN_MAX）、同 lr 1e-5、同 20k 步、同冻结测试集
（seeds 5000–5019），只换训练 seed：

| 训练 seed | success_raw | grasp_verified | success_rise | mean_max_rise (m) | 成功局 max_rise 区间 | 失败相位 |
|---:|---:|---:|---:|---:|---|---|
| 0 | 11/20 | 20/20 | 0 | 0.0134 | 0.0094 – 0.0379 | grasp×9 |
| 1 | **0/20** | 20/20 | 0 | 0.0003 | — | grasp×20 |
| 2 | 4/20 | 20/20 | 1 | 0.0059 | ≤ 0.0418 | grasp×16 |
| 合计 | **15/60（25%）** | 60/60 | 1/60 | — | — | — |

证据：`runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k{,_seed1,_seed2}.json`、
`flick_gate_minmax_seedrep.json`。

读法：`grasp_verified` 三个 seed 都是 20/20（**夹爪这一维学得很稳**，MIN_MAX 下 grip 恒 ±1、
二值、占满量程），但 `success_raw` 在 0–55% 之间摆动，`mean_max_rise` 在 0.0003–0.0134 m 之间摆动。
所以不稳定的不是「抓不抓得住」，而是「抬不抬得起来」。这与 09-24 那次
「同配方 seed0 90% / seed1 0%」是同一类现象，结论口径必须按监管要求写成
「≥2 seed × 20 局，报均值 + 极差」。

### 2. 为什么抬不起来：训练帧里 lift 信号只占 2.3%

源导出（`runs/infra/lerobot_act_lift_state_overfit/`，52 局 × 300 帧 = 15600 帧）无论任务是否
完成都跑满 horizon，任务成功后 teacher 进 `done` 相位并输出常值动作。实测相位与动作分布：

```text
相位（全 52 局）  done 11307 (72.5%) | hold 1560 (10.0%) | grasp 1300 (8.3%)
                  approach 592 (3.8%) | descend 477 (3.1%) | lift 364 (2.3%)
相位（train split 24 局 / 7200 帧）
                  done 5231 (72.7%) | hold 720 | grasp 600 | approach 262 | descend 219 | lift 168 (2.3%)
动作逐维          dx 84.8% 为 0 | dy 84.8% 为 0 | dz 82.5% 为 0 | droll/dpitch/dyaw 100% 为 0
                  grip 100% 落在 ±1（min -1 / max +1 / mean 0.87）
done 帧上的动作    恒为 [0,0,0,0,0,0,+1]（100% 相同）
lift 帧上的动作    dz 恒为 +1.0（100% 饱和），grip +1
```

机制：L1 损失下，dz 有 82.5% 的帧目标是 0、只有 2.3% 的帧目标是 +1，最优常数解就是 dz≈0；
而 grip 是 100% 饱和的二值信号、信噪比极高，所以夹爪先学会、抬起学不会。
这正好对上观测到的现象：`grasp_verified` 稳定 20/20，`max_rise` 只有 scripted base 的 0.4%–17.5%。

### 3. 处置：只裁末尾 done 帧，保留 hold

给 `scripts/build_lerobot_act_dataset.py` 加了 `--trim-done N`（每局末尾连续 `done` 帧最多留 N 帧），
**`hold` 帧一帧不动**——B 线已验证丢掉 hold 会让模型在抬起后预测开爪、主动扔方块。
两个裁剪版数据集都用官方 API 重建并通过 chunk 等价回检：

| 数据集 | 帧数 | lift 占比 | done 占比 | chunk 回检 |
|---|---:|---:|---:|---|
| `train24`（原始） | 7200 | 2.3% | 72.7% | 7128 比对，全对 |
| `train24_trimdone60` | 3409 | 4.9% | 42.2% | 3337 比对，全对，跳过边界 72 |
| `train24_trimdone0` | 1969 | 8.5% | 0% | 1897 比对，全对，跳过边界 72 |

「跳过边界 72」= 裁剪后每局末尾 `CHUNK-1 = 3` 个 chunk 会跨过新的 episode 边界（官方按 episode
末尾补帧），与源 `action_chunk`（在完整 300 帧上算的）不再可比，verify 显式跳过并计数，
不当作 mismatch。默认路径（不裁剪）已做回归：单局重建仍是 300 帧 / 297 chunk 全对，与原 manifest 一致。

### 4. 评测器补齐门禁字段

`scripts/eval_lerobot_act_runtime.py` 现在每局额外输出
`final_rise / held_at_end / phase_at_end / terminal_kind`（语义对齐参考实现
`scripts/probe_contact_ceiling.py::run_one`，契约见 `scripts/b_gate_controlled_success.py`），
并聚合 `mean_final_rise / held_at_end_count / terminal_kind_counts`。
`terminal_kind ∈ {horizon_exhausted, environment_done, preempted}`，其中 `preempted`
只在 `--limit-requests` 冒烟截断时出现，按 v4 不变量被门禁移出分母。

这带来一个必须记录的更正：门禁 C5 要求 `final_rise >= 0.04 m`，而 `final_rise <= max_rise` 恒成立，
所以上表里除 seed2 的一局（`max_rise = 0.0418`，待重评确认 `final_rise`）之外，
**所有 success_raw 局都必然过不了 C5** → 受控成功 = 0，先前 `flick_frac = 0 / controlled_success = 11`
是字段缺失下的偏松判定（门禁自己标了 `NO-blind`），现予作废。
旧臂的重评结果写到 `*_gatefields.json`，原文件保留为当时上报口径的快照。

### 5. 在跑的对照臂（本节数字待回填）

| 臂 | 数据 | 步数 | 目的 |
|---|---|---:|---|
| `trimdone0_minmax_lr1e-5_s20k_seed0/1` | 1969 帧 | 20k | 裁掉 done 后能否把 rise 拉起来（同步数预算，与已有臂直接可比） |
| `trimdone0_minmax_lr1e-5_s6k_seed0` | 1969 帧 | 5.9k | epoch 对齐（≈22 epoch），检验同步数裁剪臂是否只是过拟合 |
| `trimdone60_minmax_lr1e-5_s20k_seed0` | 3409 帧 | 20k | 温和裁剪对照，避免用单点下结论 |
| `train24_lr1e-4_actionminmax_s20k` | 7200 帧 | 20k | MIN_MAX 是否消除了大 lr 塌缩（机制臂，非能力声明） |
| `train24_lr1e-5_actionminmax_s40k` | 7200 帧 | 40k | 是否只是欠训练（20k 时 loss 0.019 仍在降） |

日志：`/tmp/a_trim_arms.log`、`/tmp/a_arms_e1e2.log`、`/tmp/a_gate_reeval.log`。

### 6. 严格门禁下的三 seed 裁定（补字段后重评）

重评先做了一致性核对：同一 ckpt sha256、同一测试集，新旧两份 JSON 的 `success_raw`、
`mean_max_rise` 与**逐局** `success_raw / max_rise` 全部一致 → 新增字段是纯附加，
且闭环评测**跨进程可复现**（监管 P0 要求的「跨进程重评一致」在这一层成立）。

`scripts/b_gate_controlled_success.py`（受控成功判据 v1，严格 C5）结果：

| 训练 seed | success_raw | 受控成功 | 判为 flick | 门禁 | 失败判据 | held_at_end |
|---:|---:|---:|---:|---|---|---:|
| 0 | 11/20 | **0** | 11 | FAIL | 全部 `final_rise` 0.0094–0.0379 < 0.04 | 20/20 |
| 1 | 0/20 | 0 | 0 | FAIL | — | 20/20 |
| 2 | 4/20 | **1** | 3 | PASS | 3 局 `final_rise` 0.0088–0.0261 < 0.04 | 20/20 |
| 合计 | 15/60 | **1/60** | 14 | — | — | 60/60 |

证据：`runs/infra/lerobot_act_env_20260928/gate_strict_minmax_3seed.json`、
`official_act_truth20_*_gatefields.json`。

三个要点：

1. **本线第一例受控成功出现了，但只有 1 局**（seed2 臂、test seed 5001，`max_rise 0.042`、
   `final_rise 0.0418`、局末相位 `hold`）。所以晋级条件第 1 条从「非零受控成功 = 0」变成
   「= 1/60 局」，仍然**远不满足「可重复」**。
2. **`held_at_end` 三臂都是 20/20**，即无论成败，局末夹爪都还夹着方块 → 卡点不是「抓不住」
   也不是「中途掉落」，**唯一卡点是抬起高度**（C5）。这把问题收窄成一个变量：dz。
3. **门禁的 `flick` 标签在这里是误名的**：这 14 局不是「把方块弹射出去」（`max_rise` 全都
   ≤ 0.042 m，远低于 `rise_cap 0.15`），而是「抬得不够高」。判据本身没错（C5 该失败），
   但把 `raw_success ∧ ¬C5` 一律标成 `flick` 会让「弹射」和「抬起不足」在汇总行里混为一谈，
   只有看 `failed_checks` 才能区分。已作为口径问题提给 B 线（`scripts/b_gate_controlled_success.py`
   属 B 的写入范围，A 不改），建议增加 `insufficient_lift` 这一类 verdict。

### 7. 机制臂结论：MIN_MAX 不能救大 lr

`train24_lr1e-4_actionminmax_s20k`（MIN_MAX + lr1e-4）：`success_raw 0/20`、`grasp_verified 0/20`、
失败相位 descend×17 / approach×3，且 **20 局的 `final_rise` 全部等于同一个 −0.0101** →
策略输出与观测无关，是常数动作，即塌缩。

所以「塌缩」是 **lr 现象**（大 lr 掉进退化解吸引子），不是归一化独有的问题；
MIN_MAX 的作用是在 lr1e-5 下把饱和动作变成可表达的边界值，**不是**放宽可用 lr 范围。
这条臂按降级定位只作机制确认，不当能力臂使用。

### 8. 裁剪 done 帧的第一批结果：受控成功从 0 变 2

`trimdone0_minmax_lr1e-5_s20k_seed0`（1969 帧、lift 占 8.5%、20k 步、81 epoch、末 loss 0.026）
对同 seed 的全量数据臂：

| 指标 | 全量 train24（7200 帧） | trimdone0（1969 帧） | 变化 |
|---|---:|---:|---|
| success_raw | 11/20 | **15/20** | +4 |
| grasp_verified | 20/20 | 20/20 | 持平 |
| success_rise（max_rise ≥ 0.04） | 0/20 | **2/20** | +2 |
| mean_max_rise (m) | 0.0134 | **0.0228** | +70% |
| mean_final_rise (m) | 0.0105 | **0.0219** | +109% |
| 受控成功（严格 C5） | 0 | **2** | 0 → 非零 |
| 门禁 gate_pass | FAIL | **PASS** | — |
| 失败相位 | grasp×9 | grasp×5 | −4 |

两例受控成功是 test seed 5001（`max_rise = final_rise = 0.0466`，局末 `hold`）与
5015（`0.0415 / 0.0415`，局末 `hold`）。注意**所有成功局都满足 `final_rise == max_rise`**，
即方块举到最高点后一直保持在局末，没有回落 → 这些不是弹射，是「举得不够高」。
证据：`runs/infra/lerobot_act_env_20260928/gate_strict_trimdone0_seed0.json`
（`field_blindness = null`，即非盲判定）。

结论（单 seed，待 seed1 复现确认）：**裁掉末尾 done 帧、保留 hold，是当前唯一被证实能把
抬起高度推上去的处置**，方向与 §2 的数据失衡诊断一致。但 `mean_max_rise 0.0228 m` 仍只有
scripted base-only（0.0764 m）的 30%，`success_rise` 只有 2/20 → 远未达标，
晋级条件第 1 条的「可重复」仍缺（只有 1 个训练 seed 的裁剪臂结果）。

裁剪臂补上 seed1 后的两 seed 对照（同 1969 帧数据、同 20k 步、同冻结测试集）：

| 数据 | 训练 seed | success_raw | success_rise | mean_max_rise (m) | 受控成功 | 门禁 |
|---|---:|---:|---:|---:|---:|---|
| 全量 train24（7200 帧） | 0 | 11/20 | 0 | 0.0134 | 0 | FAIL |
| 全量 train24（7200 帧） | 1 | 0/20 | 0 | 0.0003 | 0 | FAIL |
| 全量 train24（7200 帧） | 2 | 4/20 | 1 | 0.0059 | 1 | PASS |
| **全量小计** | — | **15/60（25%）** | 1/60 | — | **1/60（1.7%）** | — |
| trimdone0（1969 帧） | 0 | **15/20** | **2** | **0.0228** | **2** | PASS |
| trimdone0（1969 帧） | 1 | 5/20 | 0 | 0.0086 | 0 | FAIL |
| **裁剪小计** | — | **20/40（50%）** | 2/40 | — | **2/40（5%）** | — |

即：裁掉末尾 done 帧把 `success_raw` 的期望从 25% 抬到 50%、受控成功从 1.7% 抬到 5%，
方向确认；但**种子方差仍然主导**（裁剪臂两 seed 是 15/20 与 5/20），
且 `mean_max_rise` 最好也只有 scripted base-only（0.0764 m）的 30%。

### 9. 机制诊断：卡点不是 dz 幅度，是抬起命令延迟约 4 帧

新探针 `scripts/audit_lerobot_act_lift_frames.py`（只读、开环）把预测误差按 teacher 相位分解，
并对 dz 报**带符号**偏差。在 train ep0（in-sample，300 帧，其中 teacher `lift` 帧只有 7 个、
dz 恒 +1.0）上跑三条臂：

| 臂 | lift 帧 pred dz 均值 | lift 帧 dz 带符号偏差 | descend 帧 dz（teacher −0.683） | gripper 符号一致率 | task_relevant mean\|err\| |
|---|---:|---:|---:|---:|---:|
| MEAN_STD lr1e-5 | 0.468 | −0.532 | −0.717 | 1.000 | 0.0150 |
| MIN_MAX 全量 | 0.489 | −0.511 | −0.683 | 1.000 | 0.0207 |
| MIN_MAX trimdone0 | 0.486 | −0.514 | −0.751 | 1.000 | 0.0173 |

但均值会骗人。7 个 lift 帧上的**逐帧** pred dz 是：

```text
MEAN_STD 全量     [0.019, 0.020, 0.020, 0.020, 1.073, 1.071, 1.056]
MIN_MAX 全量      [0.023, 0.023, 0.024, 0.024, 1.110, 1.110, 1.110]
MIN_MAX trimdone0 [0.024, 0.025, 0.027, 0.027, 1.085, 1.120, 1.094]
```

三条臂的形状完全一样：**前 4 帧几乎不抬（dz≈0.02），后 3 帧才给出 dz≈1.07–1.12（超过 +1，
这正是闭环里 `max_preclip_abs≈1.1`、几乎每帧被 clip 的来源）**。所以：

1. 不是「dz 幅度被压成一半」，而是**抬起命令整体延迟了约 4 帧**——恰好等于
   `chunk_size = n_action_steps = 4` 的开环执行窗口。teacher 的 lift 相位一共只有 7 帧，
   错过前 4 帧就等于丢掉 57% 的抬起指令窗口，闭环 rise 掉到 base 的 30% 与此量级吻合。
2. 裁剪 done 帧**没有**改变开环 dz 的时序（0.489 → 0.486，逐帧形状一致），
   它改善闭环成功率是通过别的途径（approach/descend/gripper 时序更准、失败相位从 9×grasp 降到 5×grasp），
   不是通过修好抬起延迟。这一点必须写清楚，否则会把「裁剪有效」误读成「裁剪修好了 dz」。
3. 因此下一个单变量应当是**重规划频率**（`replan_every`），而不是继续动数据配比或 VAE。
   项目里已有这个口径的先例：`scripts/eval_act_replan_frequency.py --replan-every 1,2,4`
   （自研 ChunkPolicy 版），`runs/infra/act_lift_replan_frequency_k4.json`。

探针的局限（不能过度解读）：只有 1 个 teacher episode、7 个 lift 帧、且是 in-sample；
它是**机制线索**，不是能力结论。能力结论只认闭环 20 局 + 严格门禁。

### 10. 三个后续单变量的结果：都只有边际收益

评测器新增 `--replan-every R`（默认 = checkpoint 的 `n_action_steps`，即既有口径 R=4；
口径先例 `scripts/eval_act_replan_frequency.py --replan-every 1,2,4`）。改 R 就是改控制器口径，
R 不同的臂不可直接互比。全部数字来自同一冻结测试集（seeds 5000–5019、horizon 300、无 guard）。

**(a) 闭环重规划频率 R**（同一 checkpoint `trimdone0_minmax_lr1e-5_s20k_seed0`，只改 R）：

| R | success_raw | success_rise | mean_max_rise (m) | 受控成功 | 门禁 |
|---:|---:|---:|---:|---:|---|
| 4（既有口径） | 15/20 | 2 | 0.0228 | 2/20 | PASS |
| 2 | 15/20 | 2 | 0.0244 | 2/20 | PASS |
| **1** | **16/20** | **4** | **0.0267** | **4/20** | PASS |

方向与 §9 的延迟诊断一致（R 越小、错过抬起指令窗口越少），但**换一条臂就不成立**：

| checkpoint | R=4 | R=1 |
|---|---|---|
| 全量数据 seed0 | raw 11/20、gv 20/20、受控 0 | raw **8/20**、gv **15/20**、受控 1 |
| trimdone0 seed1 | raw 5/20、受控 0 | raw 5/20、受控 **0** |

全量数据臂在 R=1 下 `grasp_verified` 从 20/20 掉到 15/20 —— 每步重推理破坏了 chunk 内部的
动作连贯性（模型是按 4 步 chunk 训练的，只执行第 1 步等于丢掉学到的时序结构）。
所以 R 不是一个稳健旋钮，**不能作为提升手段写进结论**，只能按臂分别报告。

**(b) 训练预算**：欠训练假设**否证**。

| 数据 | 步数 | epoch | success_raw | success_rise | 受控成功 |
|---|---:|---:|---:|---:|---:|
| 全量 train24 | 20k | 22 | 11/20 | 0 | 0 |
| 全量 train24 | **40k** | 44 | **6/20** | 0 | 0 |
| trimdone0 | 5.9k | 22（epoch 对齐） | 9/20 | **3** | **3/20** |
| trimdone0 | 20k | 81 | 15/20 | 2 | 2/20 |

40k 步比 20k 更差 → 不是训不够。epoch 对齐的 5.9k 臂受控成功 3/20，与 81 epoch 的 20k 臂
（2/20）同量级 → **裁剪带来的收益不是「同步数下多跑 epoch 导致过拟合」的伪影**，
两个预算下都成立（这一条正好补上 B 线在自研 MLP 上留下的疑问）。

**(c) 裁剪强度**：裁得越干净越好，与 §2 的失衡诊断一致。

| 数据集 | 帧数 | done 占比 | success_raw | success_rise | mean_max_rise (m) | 受控成功 |
|---|---:|---:|---:|---:|---:|---:|
| `train24`（不裁） | 7200 | 72.7% | 11/20（seed0） | 0 | 0.0134 | 0 |
| `train24_trimdone60` | 3409 | 42.2% | 12/20 | 0 | 0.0129 | 0 |
| `train24_trimdone0` | 1969 | 0% | **15/20** | **2** | **0.0228** | **2/20** |

**当前最好的单臂**是 `trimdone0 + seed0 + R=1`：raw 16/20、受控 4/20（20%）。
但 `mean_max_rise` 最好也只有 0.0267 m = scripted base-only（0.0764 m）的 **35%**，
且 trimdone0 两个 seed 是「受控 2/20」与「受控 0/20」——**种子方差仍然主导**。
三个单变量（归一化、裁剪、重规划频率）各自都只带来边际改善，没有一个把抬起高度拉到 base 量级。

全臂对照表用 `scripts/summarize_lerobot_act_arms.py` 生成（只读；从 checkpoint 的
`train_config.json` 反查数据/步数/seed/归一化，从门禁 JSON 反查受控成功裁定，
并自动折叠缺 `final_rise` 的旧产物），机器可读版：
`runs/infra/lerobot_act_env_20260928/arms_summary.json`。

### 11. 数据量对照臂（120 局示范）：设计与前置校验

§10 的三个单变量都只有边际收益，剩下最可疑的变量是**示范量**：trimdone0 只有 1969 帧、
其中 teacher `lift` 帧仅 168 个（24 局 × 7 帧）。抬起这一维的监督信号总量太小。

前置校验（做扩量之前先证明数据管线可复现）：用 `scripts/export_lift_to_lerobot.py`
以 `--train-seeds 1000-1001` 重新生成，与 09-24 那份 `runs/infra/lerobot_act_lift_state_overfit/
data/episode_0000.npz` 逐元素比对——`observation_state`(300,60)、`action`(300,7)、
`action_chunk`(297,4,7)、`timestamp`(300,)、`phase` 序列**全部 bit-exact 相同（max|diff| = 0）**。
即 scripted teacher + `harness/env_factory`（pinned object seed 20260923）+ `reset_contact(seed)`
这条链是确定性的，扩量不会引入不可复现的数据。

扩量臂设计（配方与 trimdone0 臂逐项一致，只改示范量）：

```text
示范：train seeds 1000-1119（120 局，含原 24 局）/ val 2000-2015 / test 5000-5019
      -> runs/infra/lerobot_act_lift_state_big120/（新目录，09-24 那份原样保留）
数据集：--split train --trim-done 0 -> runs/infra/lerobot_act_lift_v30/train120_trimdone0
训练：ACTION=MIN_MAX, lr 1e-5, chunk 4 / n_action_steps 4, batch 8, 20k 步, seed 0 与 1
评测：同一冻结测试集 seeds 5000-5019、horizon 300、无 guard，R=4 与 R=1 各一次（分开报）
```

**泄漏检查**：测试 seeds 5000–5019 只出现在 `--test-seeds`，数据集构建走 `--split train`
（只取 split == train 的行，即 seeds 1000–1119），val/test 的 teacher 轨迹从未进过训练集。
原有 52 局 interchange 里也含 test split 的 teacher 轨迹，同样从未被 `--split train` 取用过。

### 12. VAE / KL 权重：模态平均假设**否证**

§9 发现「抬起命令延迟约 4 帧、dz 均值只有 teacher 的一半」后，最自然的解释是
ACT 的 VAE：KL 项把 decoder 输出拉向先验/多模态均值，于是 dz 被平均掉。
两条单变量臂直接检验它（其余配方与 `trimdone0_minmax_lr1e-5_s20k_seed0` 逐项相同，
均 K=R=4、trimdone0、seed0、20k 步、同一冻结测试集）：

| 臂 | `kl_weight` | `use_vae` | success_raw | success_rise | mean_max_rise (m) | mean_final_rise (m) | 受控成功 | lift 帧 pred dz 均值 | 首个 dz≥0.5 的帧序号 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| trimdone0 基线 | 10 | true | 15/20 | 2 | 0.0228 | 0.0219 | 2/20 | 0.486 | 4 |
| `kl1` | **1** | true | 14/20 | 2 | 0.0220 | 0.0208 | 2/20 | 0.477 | 4 |
| `novae` | 10 | **false** | 11/20 | 2 | 0.0180 | 0.0159 | 2/20 | 0.497 | 4 |

三条臂的受控成功都是 **2/20**，开环 7 个 teacher lift 帧上的 dz 形状也完全一样
（`[0.02, 0.02, 0.02, 0.02, 1.07, 1.11, 1.07]` 量级，第 4 帧才发命令）。把 KL 权重降 10 倍
几乎不动数字，**直接关掉 VAE 反而略差**（raw 15→11）。

结论：**「dz 被 VAE 模态平均压掉」这个假设否证**。延迟来自 chunk 的开环执行窗口，
不来自潜变量正则。证据：`runs/infra/lerobot_act_env_20260928/official_act_truth20_trimdone0_minmax_{kl1,novae}_s20k_seed0.json`、
`lift_frames_dz_trimdone0_minmax_{kl1,novae}_s20k_seed0.json`。

### 13. 数据量 ×5（120 局示范）：固定步数下是**负结果**

§11 设计的扩量臂已跑完 seed0（seed1 在跑）。数据集 `train120_trimdone0` = 120 局 / **9965 帧**
（trimdone0 的 5.06 倍），teacher lift 帧同步 ×5；测试集仍是 held-out 的 seeds 5000–5019。

| 臂 | 示范量 | 帧数 | epoch@20k步 | R | success_raw | success_rise | mean_max_rise (m) | 受控成功 | 门禁 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trimdone0 seed0 | 24 局 | 1969 | 81 | 4 | **15/20** | 2 | **0.0228** | **2/20** | PASS |
| train120 seed0 | 120 局 | 9965 | 16 | 4 | 4/20 | 1 | 0.0074 | 1/20 | PASS |
| train120 seed0 | 120 局 | 9965 | 16 | **1** | 4/20 | 0 | 0.0062 | 0/20 | FAIL |

同步数预算下把示范量 ×5，`success_raw` 15→4、`mean_max_rise` 0.0228→0.0074（掉到 base 的 9.7%），
而且 R=1 也救不回来（24 局臂上 R=1 是 2→4，这里 1→0）。

结论：**「抬起监督信号总量太小」这个假设，在固定 20k 步下否证**。
必须写清的边界：本臂**没有做 epoch 对齐**（81 epoch → 16 epoch），所以严格讲它只否证了
「同步数下加数据有益」，没有否证「加数据 + 按比例加步数」。但 §10(b) 已证明在 24 局上
把步数 20k→40k 会更差，所以「加数据 + 加步数」这条不作为优先方向；真正该叠的是 §15 的 chunk_size。
证据：`official_act_truth20_train120_trimdone0_minmax_lr1e-5_s20k_seed0{,_replan1}.json`。

### 14. 门禁 `final_rise` 阈值 ±0.005 敏感性（回应监管备忘 §二.A.3）

监管指出：本线受控成功局的 `final_rise` 落在 0.0415–0.0466 m，紧贴判据 v1.1 的 C5 门槛
`FINAL_RISE_MIN = 0.04`。新增 `scripts/a_gate_threshold_sensitivity.py`（只读）扫
`{0.030, 0.035, 0.040, 0.045, 0.050}`。口径纪律：**不重新实现判据**，脚本 import
`scripts/b_gate_controlled_success.py::judge_file`，只改 `final_rise` 一个入参，
`RISE_CAP`、`HOLD_PHASES_*`、unjudged 移出分母、三套账全部沿用 B 的实现，因此每一格与门禁同源。

26 份评测产物里有 **21 份字段等级为 strict**（缺 `final_rise` 的 5 份 09-28 上午旧产物已排除，
不参与本节统计）。21 臂 × 20 局 = 420 局，受控成功数随门槛变化：

| 门槛 | 0.030 | 0.035 | **0.040（现行）** | 0.045 | 0.050 |
|---|---:|---:|---:|---:|---:|
| 受控成功合计 | 72/420 | 50/420 | **28/420** | 18/420 | 17/420 |
| 非零臂数 | 15/21 | 14/21 | **11/21** | 8/21 | 7/21 |

15 个「至少在一个门槛下非零」的臂，逐格列出（受控成功局数，门槛 0.030 → 0.050）：

| 臂 | 0.030 | 0.035 | 0.040 | 0.045 | 0.050 | 稳健？ |
|---|---:|---:|---:|---:|---:|---|
| **trimdone0 K=2 seed0（R=2）** | **9** | **9** | **9** | **9** | **9** | **全域不变**（†17:50 起判 `measurement_invalid`，见 §17.2；全域不变臂已易主为 K=2 seed3，见 §17.11） |
| trimdone0 kl1（K=4） | 9 | 5 | 2 | 1 | 1 | 强衰减 |
| trimdone0 K=4 seed0 R=1 | 9 | 6 | 4 | 2 | 2 | 强衰减 |
| trimdone0 K=4 seed0 R=2 | 8 | 6 | 2 | 1 | 1 | 强衰减 |
| trimdone0 K=4 seed0 R=4 | 8 | 6 | 2 | 1 | 0 | 归零 |
| trimdone0 s6k（epoch 对齐） | 6 | 5 | 3 | 2 | 2 | 强衰减 |
| trimdone0 novae（K=4） | 6 | 4 | 2 | 1 | 1 | 强衰减 |
| train24 MIN_MAX seed0 R=4 | 4 | 2 | 0 | 0 | 0 | 现行门槛已归零 |
| train24 MIN_MAX seed0 R=1 | 3 | 1 | 1 | 0 | 0 | 贴门槛 |
| train120 seed0 R=4 | 2 | 1 | 1 | 0 | 0 | 贴门槛 |
| train120 seed0 R=1 | 2 | 1 | 0 | 0 | 0 | 贴门槛 |
| trimdone0 K=8 seed0（R=8） | 2 | 1 | 1 | 1 | 1 | 弱但小幅 |
| trimdone60 seed0 | 2 | 2 | 0 | 0 | 0 | 现行门槛已归零 |
| train24 MIN_MAX seed2 | 1 | 1 | 1 | 0 | 0 | 贴门槛 |
| train24 MIN_MAX 40k 步 | 1 | 0 | 0 | 0 | 0 | 现行门槛已归零 |

其余 6 个 strict 臂（两条 lr1e-4 塌缩臂、train24 MEAN_STD、MIN_MAX seed1、trimdone0 seed1
的 R=4 与 R=1）在**全部门槛下都是 0**，与门槛取值无关。

判读（这条直接改写法）：

1. **§8/§10 里「受控成功 2/20」「4/20」都是贴门槛数字**：门槛抬 0.005 到 0.045，
   trimdone0 K=4 的三个口径（R=4/2/1）分别掉到 1/1/2，抬到 0.050 时 R=4 口径归零；
   合计从 28/420 掉到 18/420（−36%）。所以这些数字**不能当作能力证据**，
   只能记为「在现行门槛 0.040 下非零、但对门槛取值不稳健」。
2. **唯一对门槛完全不敏感的是 K=2 臂（9/9/9/9/9）**：它有 10 局 `max_rise ≥ 0.04`，
   其中 8 局落在 0.060–0.121 m 区间（base-only 均值 0.0764），离门槛有实质距离，
   且这些局 `final_rise == max_rise`（举到最高点后保持到局末，非弹射）。这是本线第一个
   「非零 + 非弹射 + 不靠门槛取值」的受控成功。
   **† 18:10 追加**：该臂补 `norm_input_blown_frames_frac` 后 blown = 0.2120 > 0.05，
   判 `measurement_invalid`（§17.2），本条的载体作废。门槛敏感性已在 37 个 strict 臂上重跑，
   **新的门槛稳健臂是 K=2 seed3（恒 17/20）与 seed4（19/19/19/19/18）**，两者都测量有效、
   flick = 0、`mean_max_rise` 达 base 的 89% / 94%（§17.11）。
3. 全表单调性检查通过（门槛越高受控成功越少，21/21 臂无非单调），说明扫描实现无误。
4. 晋级条件第 1 条的证据从这一节起**只能挂在 K=2 臂上**，且必须先补 ≥2 训练 seed（§15）。
5. 与 B 共担的一条：门槛本身（0.04）是判据 v1.1 的常量，本表不主张改它，
   只主张**引用受控成功数字时必须同时报门槛敏感性**。

机器可读版：`runs/infra/lerobot_act_env_20260928/gate_threshold_sensitivity_A.json`
（含每臂每门槛的 seeds 列表与相对现行门槛的 gained/lost）。

### 15. chunk_size：本轮最大的单变量，但**种子复现没通过**（改判）

§9 的诊断说「抬起命令延迟约 4 帧 = 开环执行窗口 K」，于是把 `chunk_size = n_action_steps`
当单变量扫 K ∈ {2, 4, 8}（数据 trimdone0、MIN_MAX、lr 1e-5、20k 步、seed0，闭环 R = K 默认口径）：

| K | R | success_raw | grasp_verified | success_rise | mean_max_rise (m) | mean_final_rise (m) | 受控成功 | 开环 lift 帧 dz 均值 | 首个 dz≥0.5 的帧 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **2** | 2 | 11/20 | 15/20 | **10** | **0.0376** | **0.0314** | **9/20** | 0.815 | **2** |
| 4 | 4 | 15/20 | 20/20 | 2 | 0.0228 | 0.0219 | 2/20 | 0.486 | 4 |
| 8 | 8 | 10/20 | 20/20 | 1 | 0.0129 | 0.0114 | 1/20 | 0.476 | 4 |

**评测器口径核查（一次性卫生项，已完成）**：`scripts/eval_lerobot_act_runtime.py` 的
`chunk_size` / `n_action_steps` / `replan_every` 全部从 checkpoint 的 config 读取，不写死；
`replan` 默认 = ckpt 的 `n_action_steps`，并强制校验 `1 <= R <= chunk_size`（越界直接退出）；
每局只执行 chunk 的前 R 步、丢弃其余，产物里逐臂记录 `chunk_size / n_action_steps / replan_every`
三个字段。K=2 与 K=8 两臂的产物分别写的是 `chunk_size=2, replan_every=2` 与
`chunk_size=8, replan_every=8` → 非 4 的取值确实按 ckpt 生效，既有 K=R=4 臂的口径未被改变。

三件事同时成立：K=2 把 `success_rise` 从 2 抬到 10、`mean_max_rise` 从 0.0228 抬到 0.0376
（= base-only 0.0764 的 **49%**，此前所有臂都 ≤35%）、受控成功从 2 抬到 **9**；代价是
`grasp_verified` 从 20/20 掉到 15/20（重规划更频繁，抓取连贯性变差）。

**K 与 R 是两个变量，必须分开**：K=4 的 checkpoint 在 R=2 下受控成功是 2/20（§10a），
而 K=2 在同样 R=2 下是 9/20 → 差异来自**训练期的预测时域 K**，不是闭环重规划频率。
反过来，把 K=2 的 checkpoint 按 R=1 评：raw 4/20、`grasp_verified` 掉到 **5/20**、受控 0/20
→ 再次印证 §10a 的结论「R 不是稳健旋钮」，R=1 会破坏按 chunk 训练出来的动作连贯性。

**2×2 对照（数据裁剪 × chunk_size，R=K；括号为 seed0 / seed1 / seed2 的受控成功）**：

| | K=4 | K=2 |
|---|---|---|
| `train24`（未裁剪，7200 帧） | raw 11、0、4/20；m_rise 0.0134/0.0003/0.0059；**受控 0、0、1** | raw 11、16/20；m_rise 0.0152/0.0244；**受控 1、3** |
| `train24_trimdone0`（1969 帧） | raw 15、5/20；m_rise 0.0228/0.0056；**受控 2、0** | raw 11、10、2/20；m_rise 0.0376/0.0134/0.0020；**受控 9、2、0** |

**匹配对照的聚合（只比数据/步数/归一化/lr 全同、仅 K 不同的臂）**：

| 配置 | K=4 受控均值 | K=2 受控均值 | K=4 非零 seed | K=2 非零 seed |
|---|---:|---:|---:|---:|
| trimdone0（20k, MIN_MAX, lr1e-5） | 1.0/20 | **3.7/20** | 1/2 | **2/3** |
| train24 未裁剪（同上） | 0.33/20 | **2.0/20** | 1/3 | **2/2** |

两组匹配对照上 K=2 都优于 K=4（均值 3.7 vs 1.0、2.0 vs 0.33；非零 seed 占比也更高）。
这是本轮**唯一在两个数据集上都同向的杠杆**，但量级仍小：最好均值 3.7/20 = 18%，
且没有任何一格达到「≥2 seed 且每 seed 都非零、幅度接近 base」。
两个杠杆都不单独充分：未裁剪 + K=2 只到 1–3/20，裁剪 + K=4 只到 0–2/20。
这与 §13（加数据无用）、§12（VAE/KL 无关）一致——起作用的是
「裁掉 done 帧」+「缩短开环窗口」这一组，而不是任何单一超参。

同一 K=2 checkpoint 换 R=1 评（口径不同，分开报）：seed0 raw 4/20、`grasp_verified` **5/20**、
受控 0/20；seed1 raw 10/20、gv 20/20、受控 1/20（R=2 下是 2/20）。R=1 在 seed0 上把抓取打崩，
在 seed1 上只是略降 → 再次说明 R 不是稳健旋钮（§10a）。

**种子复现（监管要求 ≥2 seed）：没通过。** 同一配方补到 3 个训练 seed：

| 训练 seed | success_raw | grasp_verified | success_rise | mean_max_rise (m) | 受控成功 | 开环 lift dz | 首个 dz≥0.5 帧 | 开环 `done_dz` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 11/20 | 15/20 | 10 | 0.0376 | **9/20** | 0.815 | 2 | **+0.0213** |
| 1 | 10/20 | 20/20 | 2 | 0.0134 | **2/20** | 0.812 | 2 | **+0.0024** |
| 2 | 2/20 | 20/20 | 0 | 0.0020 | **0/20** | 0.777 | 2 | **+0.0012** |

未裁剪 `train24` + K=2 的两个 seed 给出同向证据（`done_dz` 越大、受控成功越多）：
seed0 `done_dz` +0.0076 → 受控 1/20；seed1 `done_dz` +0.0143 → 受控 3/20（raw 16/20）。

均值 3.7/20（18%）、极差 0–45%。**改判**：

1. §14 里「K=2 是唯一门槛稳健的臂」仍然成立（那是 seed0 单臂的属性），但
   **「K=2 解决了抬起」不成立**——9/20 是 seed0 的偶发，和之前 MIN_MAX 的 11/20 同类。
2. 不过它比此前所有配方都强一点：这是**第一个在 3 个训练 seed 中有 2 个取得非零受控成功**
   的配方（此前 MIN_MAX K=4 是 1/3、train120 是 1/2、trimdone0 K=4 是 1/2）。
   晋级条件第 1 条按强口径（可重复）**仍判不满足**；按弱口径（≥2 seed 非零）**首次达到**。
3. 三个 seed 的**开环 lift 爆发几乎完全相同**（dz 0.777–0.815、首个命令都在第 2 帧、
   `dz_pred_lift_cmd_rate` 都是 0.714），差别全在抬起之后的 `hold/done` 相位 dz 偏置
   （+0.0199/+0.0019/+0.0000）。**种子方差不住在「会不会抬」，住在「抬起之后 dz 是否保持正值」**
   ——这条直接指向 §16 的归因。

已排 `trimdone0 + K=2` 的 seed 3/4/5（`/tmp/a_k2_seedsweep.sh`），把 3 点扩到 6 seed 的
均值+极差，再对晋级条件第 1 条定级。

### 16. 闭环抬起到底从哪来：逐帧动作归因（新工具 + 机制结论）

§15 的第 3 点需要一个能看闭环逐帧动作的工具。两处改动，都在 A 的写入范围：

- `scripts/eval_lerobot_act_runtime.py` 新增 `--log-actions`（**默认关闭**）：打开后每局多写
  `actions`（真正送进 `env.step` 的 clip 后 7 维动作）与 `rise_trace`（逐帧方块相对初始高度位移）。
  关闭时输出与历史产物**同构**（不新增任何 key）。等价性已验证：同一 ckpt 同一题集，
  加 `--log-actions` 重跑 20 局的 `(max_rise, final_rise, success_raw)` 与既有产物**逐局完全相同**
  （seed 5000 `max_rise = 0.12061307` 两边一致）→ 顺带独立确认了评测器的**跨进程确定性**
  （robosuite 1.5.2 + `harness/env_factory` 物体 pin 的前提下）。
- `scripts/a_closed_loop_dz_diag.py`（只读）：把每 0.001 m 的抬升按该帧 dz 归因到三档——
  `burst`（dz ≥ 0.5，teacher 的抬法）/ `bias`（0.005 ≤ dz < 0.5）/ `other`（dz < 0.005）。
  归因做了闭合校验（三档之和 = `final_rise`，残差 > 1e-4 报警；当前 80/80 局残差为 0）。

产物在 `runs/infra/lerobot_act_env_20260928/actlog/`（子目录，避免被汇总表的 glob 当成新臂）。

**结论 1：teacher 式的饱和爆发在闭环里几乎从不发生。**

| 臂 | K/R | high/low 局数 | `burst` 帧均值 | `dz_tail`(第100帧后均值) | 抬升←burst (m) | 抬升←bias (m) |
|---|---|---|---:|---:|---:|---:|
| trimdone0 K=2 seed0 | 2/2 | 10/10 | 0.25 | +0.0130 | +0.0024 | **+0.0399** |
| trimdone0 K=2 seed1 | 2/2 | 2/18 | 0.05 | +0.0155 | +0.0000 | +0.0216 |
| trimdone0 K=4 seed0 | 4/4 | 2/18 | 0.00 | +0.0181 | +0.0000 | +0.0321 |
| trimdone0 K=4 seed1 | 4/4 | 0/20 | 0.00 | +0.0110 | +0.0000 | +0.0113 |

每局 dz ≥ 0.5 的帧数平均只有 **0–0.25 帧**（teacher 是连续 7 帧），来自 burst 的抬升 ≤ 0.005 m。
**闭环抬起 100% 来自 0.005 ≤ dz < 0.5 的持续小正命令的积分。**

**结论 2：成功局与失败局的唯一差别是抓取后 dz 是否保持小正值。**
K=2 seed0 的 high 组（`max_rise ≥ 0.04`）`dz_tail = +0.0247`、抬升←bias = +0.0739 m；
low 组 `dz_tail = +0.0013`、抬升←bias = +0.0059 m。

**结论 3：量纲能对上。** teacher 用 7 帧 dz=+1.0 抬出 base-only 的 0.0764 m
→ ≈ **0.011 m /(dz·帧)**。K=2 seed0 high 组 `dz_tail +0.0247 × ~200 帧 × 0.011 ≈ 0.054 m`，
与实测抬升←bias 0.0739 m 同量级。所以「抬起高度 ≈ 0.011 × ∫dz」这个近似在本项目口径下可用。

**结论 4：开环 `done_dz` 是闭环受控成功的廉价预测器。** 把 §9 探针在 teacher `done` 相位
（抬起之后那段）上的预测 dz 均值拿来对闭环结果做相关（只取默认口径 R=K、且有开环审计的 11 个臂）：

| 开环量 | Pearson(mean_max_rise) | Pearson(受控成功) | Spearman(受控成功) |
|---|---:|---:|---:|
| `done_dz` | **+0.757** | **+0.866** | +0.327 |
| `lift_dz`（爆发幅度） | +0.197 | +0.441 | +0.273 |
| `hold_dz` | +0.330 | +0.174 | −0.191 |

`done_dz` 明显优于「爆发幅度」`lift_dz`。最干净的证据是 §15 的同配方三 seed：
`done_dz` +0.0213 / +0.0024 / +0.0012 对 受控成功 9 / 2 / 0，单调且量级对得上结论 3。
这也顺带解释了 §8 的裁剪为什么有效：未裁剪数据里 `done` 帧占 73%、把抬起后区域的 dz
教成 0（该臂 `hold_dz` 高达 +0.0368 但 `done_dz` 只有 +0.0002 → 受控 0）；裁掉 done 帧后，
抬起后区域继承了 hold 的正偏置（`done_dz` +0.0213）。

**必须写清的边界**：
1. Spearman 只有 +0.327，因为 11 个臂里 8 个的受控成功挤在 0–2，秩相关被并列值和一个
   9/20 的离群点主导；本表只主张「`done_dz` 与闭环抬起正相关、且优于爆发幅度」，不主张因果。
2. 开环探针只有 1 个 teacher episode、7 个 lift 帧、in-sample，是**机制线索与筛选器**，
   不能替代闭环 20 局 + 严格门禁做能力结论。
3. 「靠持续小正 dz 慢慢漂上去」与 teacher「7 帧爆发抬到位」是两种不同的行为。
   当前所有受控成功局都属于前者，因此**不得**把它们描述为「学会了 teacher 的抬起动作」。
   按监管对外标注纪律，这类素材只能标「抓取成功、抬起不足/抬起方式与示范不同」。

**由此得到的下一步排序**（都在 P1 门禁内：Lift、state、无视觉、无 PickPlace）：
1. `trimdone0 + K=2` 补到 6 个训练 seed（在跑），对晋级条件第 1 条定级；
2. 既然瓶颈是「抬起后 dz 保持正值」，而 ACT 官方入口**没有**相位重加权采样器
   （已核 `ACTConfig` 的 34 个字段：只有 `chunk_size / n_action_steps / normalization_mapping /
   use_vae / temporal_ensemble_coeff / dropout / kl_weight / optimizer_lr / optimizer_weight_decay /
   pre_norm / n_vae_encoder_layers`；`balance_*` 与 `time_sampling_*` 属于别的 policy），
   要做相位重加权就得改 lerobot 内部，**越出「官方入口」纪律**，需先与监管确认是否允许；
3. `temporal_ensemble_coeff`（ACT 原生的时序集成，官方要求配 `n_action_steps=1`）目前**不能直接评**：
   `eval_lerobot_act_runtime.py` 走 `predict_action_chunk` 取前 R 步，而时序集成实现在
   `select_action` 里 → 评测会静默绕过它，训练意图与评测口径不一致。要做这条必须先给评测器
   加一条「按 `select_action` 走」的显式口径（并单独命名产物），否则不出这条臂。

### 17. 输入契约实测：L1 在官方臂上只咬合 1/12，且肇事维与 B 定位的不同

交付监管备忘 增补二 §5.A①（评测器补 `--record-input-blowup` 并重跑），并顺带把 §15 的
「K=1 突破」改判、把 K=2 补到六个训练 seed。所有数字来自
`runs/infra/lerobot_act_env_20260928/gate_strict_*.json` 的 `input_contract` 块。

#### 17.1 评测器补字段 + 12 臂重评：既有数字逐项不变

`scripts/eval_lerobot_act_runtime.py` 新增 `--record-input-blowup`（**默认开**）：从 checkpoint 的
`policy_preprocessor_step_*_normalizer_processor.safetensors` 读 mean/std/min/max，按该 ckpt 自己的
`normalization_mapping` 逐特征算出**训练期归一化后 |x| 的上界**，全局阈值取所有维上界的最大值
（trimdone0 系 = 12.469、train120_trimdone0 = 18.038、未裁剪 train24 = 23.845）。行字段与 B 线
`scripts/b_eval_act_lift_v1.py --record-input-blowup` 同名，门禁可以直接吃。

完整性核验：重评前把 12 份原产物 `cp` 到 `pre_input_contract/`（只复制、不移动、不删除），
同参重跑后比对**顶层 8 个统计量 + 每局 12 个字段**——12/12 臂 `IDENTICAL`。
加字段不扰动行为，与此前已验证的跨进程逐位确定性一致。

**顺带把确定性口径钉死**（18:30 追加，改评测器加 `--clip-norm-input` 时做的全字段回归）：
拿 `trimdone0_minmax_k2_...seed3` 同参重跑，对**整份 JSON 做全键递归比对**，
唯一不同的字段是 **`rows[].elapsed_sec`**（每局墙钟耗时，旧 3.508/3.157/3.194 → 新 3.033/2.778/2.815）。
也就是说：本线闭环产物里**只有墙钟耗时不可复现**，其余所有字段（`max_rise` / `final_rise` /
`phase_trace` / `chunk_count` / `clip_events` / 全部 `norm_input_*`）跨进程逐位一致。
任何「重跑数字变了」的报告，先查是不是在看 `elapsed_sec`。

回填链（`scripts/a_backfill_input_contract.py`，不手抄命令、从产物自带的
`checkpoint.pretrained_model_dir` 与 `replan_every` 反推同参命令）随后把剩下 20 份也补齐：
**40/40 门禁产物全部带输入契约字段，0 份缺失**；31 份有留档的比对全部 `IDENTICAL`。

#### 17.2 裁定：15/16 测量有效，1/16 `measurement_invalid`

下表是**全部 16 个已带字段的臂**（其中 12 个是 17.1 的同参重评，另 4 个由并行的 seed 扫描链首次产出）：

| 臂 | 受控 | blown_frac | oor_frac | 闭环 \|x\| 峰 | 阈值 | 门禁 |
|---|---:|---:|---:|---:|---:|---|
| `trimdone0_minmax_k2_...seed0` | 9/20 | **0.2120** | 0.565 | **93.4** | 12.47 | **INVALID** |
| `trimdone0_minmax_k2_...seed1` | 2/20 | 0.0000 | 0.362 | 10.0 | 12.47 | pass |
| `trimdone0_minmax_k2_...seed2` | 0/20 | 0.0033 | 0.499 | 13.1 | 12.47 | pass |
| `trimdone0_minmax_k2_...seed3` | 17/20 | 0.0000 | 0.438 | 10.6 | 12.47 | pass |
| `trimdone0_minmax_k2_...seed4` | 19/20 | 0.0000 | 0.372 | 9.3 | 12.47 | pass |
| `trimdone0_minmax_k2_...seed5` | 1/20 | 0.0173 | 0.381 | 41.4 | 12.47 | pass |
| `trimdone0_minmax_k1_...seed0` | 20/20 | 0.0002 | 0.461 | 13.3 | 12.47 | pass |
| `trimdone0_minmax_k1_...seed1` | 0/20 | 0.0012 | 0.307 | 13.4 | 12.47 | pass |
| `trimdone0_minmax_lr1e-5_...seed0`（K=4） | 2/20 | 0.0000 | 0.246 | 8.6 | 12.47 | pass |
| `trimdone0_minmax_lr1e-5_...seed1`（K=4） | 0/20 | 0.0000 | 0.341 | 8.6 | 12.47 | pass |
| `trimdone0_minmax_k8_...seed0` | 1/20 | 0.0026 | 0.330 | 19.8 | 12.47 | pass |
| `train24_minmax_k2_...seed0` | 1/20 | 0.0000 | 0.593 | 16.1 | 23.85 | pass |
| `train24_minmax_k2_...seed1` | 3/20 | 0.0000 | 0.381 | 22.4 | 23.85 | pass |
| `train24_lr1e-5_actionminmax_s20k` | 0/20 | 0.0000 | 0.217 | 16.1 | 23.85 | pass |
| `train120_trimdone0_minmax_...seed0`（K=4） | 1/20 | 0.0000 | 0.196 | 8.8 | 18.04 | pass |
| `train120_trimdone0_minmax_k2_...seed0` | 9/20 | 0.0000 | 0.381 | 9.4 | 18.04 | pass |

**唯一 INVALID = `trimdone0_minmax_k2_lr1e-5_s20k_seed0`**（blown 0.2120 > `INPUT_BLOWUP_TOL=0.05`）。
因此增补一 §1 登记的「K=2 seed0 受控 9/20」按增补二 §2 正式降为**测量无效**，
不得再作为率证据引用；改判 1 的证据基里这一项移除。

#### 17.3 肇事维是 `env[3]/env[4]`（cube_quat 近常量维），不是 B 定位的 `state[7/9/11]`

`norm_input_blown_dims` 计数（只统计超过全局阈值的帧）：

| 臂 | 炸穿维:帧数 | 有炸帧的局数 | \|x\| 峰 @ test seed |
|---|---|---:|---|
| `trimdone0_minmax_k2_...seed0` | **env[4]:322, env[3]:314** | 7/20 | 93.4 @5011（env[4]） |
| `trimdone0_minmax_k2_...seed2` | env[4]:10 | 1/20 | 13.1 @5018 |
| `trimdone0_minmax_k8_...seed0` | env[3]:2 | 1/20 | 19.8 @5013 |
| `trimdone0_minmax_k1_...seed0` | state[34]:1 | 1/20 | 13.3 @5005 |
| 其余 8 臂 | 无 | 0/20 | ≤22.4 |

`observation.environment_state` 的实测布局（`train24_trimdone0/meta/stats.json`）：
`env[0:3]` = cube_pos（env[2] mean 0.8556 = 桌面高度 + 半边长），`env[3:7]` = cube_quat，
`env[7:10]` = gripper_to_cube_pos。肇事的 env[3]/env[4] 是 cube_quat 的前两个分量：

| dim | mean | std | min | max | 训练期归一化 \|x\| 上界 |
|---:|---:|---:|---:|---:|---:|
| env[3] | 0.00250 | 7.72e-03 | −0.02237 | +0.03344 | 4.01 |
| env[4] | 0.00014 | 7.57e-03 | −0.03736 | +0.02278 | 4.96 |

**teacher 示范里方块从不倾斜**，所以这两维的全域幅度只有 ±0.037。闭环里方块一被夹起就转，
raw 偏差可达 0.707（= 93.4 × 7.57e-3），是训练全域的 **19 倍** → 归一化后 93.4。
它们的训练期归一化上界只有 4.01/4.96，**看起来完全健康**：开环审计、训练 stats、
离线 val loss 全都不会报警。这与 B 说的「开环不可见」是同一类陷阱，只是换了一组维。

B 定位的 `state[7]/[9]/[11]`（`joint_pos_cos` 系）在 A 的 12 臂闭环里**一帧都没炸过**；
唯一炸过的 state 维是 `state[34]`（`joint_acc[6]`，1 帧）。差异来源：B 的事故在自研
`scripts/train_act_lift.py` 的 60 维拼接 obs 上，官方臂按 `ACTConfig.validate_features()`
要求拆成 state(50) + env(10)，两组数据的近常量维不是同一批。

#### 17.4 推论：B §6.1 的 std 相对下限在官方臂上**不咬合肇事维**

下限公式 `floor_j = rel_floor × max(absmax_j, abs_floor)`（rel 1e-2）：

| dim | std | absmax | floor | 是否抬升 |
|---:|---:|---:|---:|---|
| env[3] | 7.72e-03 | 0.0334 | 3.34e-04 | **否**（floor 比 std 小 23 倍） |
| env[4] | 7.57e-03 | 0.0374 | 3.74e-04 | **否** |
| state[7] | 7.45e-04 | 0.9998 | 1.00e-02 | 是，增益压缩 13.4x |
| state[9] | 5.07e-04 | 0.9999 | 1.00e-02 | 是，增益压缩 19.7x |
| state[11] | 1.10e-03 | 0.9994 | 1.00e-02 | 是，增益压缩 9.1x |
| state[38] | 1.67e-03 | 0.9999 | 1.00e-02 | 是，增益压缩 6.0x |
| state[12] | 9.01e-03 | 1.00e+00 | 1.00e-02 | 是，1.1x（顺带，无害） |

机制解释：相对下限按「该维自己的数据幅度」缩放，能治的是 **absmax 大但 std 极小**
（`joint_pos_cos`：cos θ ≈ 1 − θ²/2 在 0 附近二阶平坦，absmax≈1 而 std≈5e-4）；
治不了 **absmax 与 std 同量级、但闭环偏差远超训练全域**（cube_quat x/y）。
不是 B 的修复错了——在自研 60 维线上它正对着肇事维；而是**同一份修复搬到官方拆分 obs 上，
肇事维换人了**。这一点必须写进重分类结论，否则「加了 std 下限」会被误当成官方线已修好。

#### 17.5 官方入口内做不到「训练/推理一致截断」

实测 `lerobot 0.4.4` 的 `processor/normalize_processor.py` 全文 grep `clip|clamp` **0 命中**：
MEAN_STD 分支是纯 `(x − mean)/(std + 1e-8)`（:335），MIN_MAX 分支是 `2(x − min)/(max − min) − 1`
且**不外 clip**（:350-359，超范围就映射到 [−1,1] 之外）。所以：

- B §6.1 后半句「训练时也截断、与推理同一 C」在官方入口内**无法实现**，要做必须自定义
  processor，**越出「官方入口」纪律**，需监管批准后另开 baseline 族；
- `STATE=MIN_MAX` 不是修复（增补二 §0 已把「MIN_MAX 免疫 L1」的口头表述作废）：
  MIN_MAX 只在 `denom == 0` 时把分母换成 eps，env[3]/env[4] 的 `max − min = 0.056/0.060` 不为 0，
  照样被放大 1/0.056 ≈ 18 倍。

#### 17.6 L1 不解释种子方差

blown_frac 与受控成功**无关联**：seed4 blown 0.0000 → 19/20；seed1 blown 0.0000 → 2/20；
seed2 0.0033 → 0/20；seed5 0.0173 → 1/20；seed0 0.2120 → 9/20（且已 INVALID）。

所以在官方线上，L1 是**测量有效性**问题（12 臂里 1 臂），不是能力瓶颈；能力瓶颈仍是 §16 的
L2（抬起后 dz 无停止条件、靠小正 dz 积分漂上去）。这与增补二 §1 的三层因果栈不冲突，
只是权重要改：自研线上 L1 咬合 94% 帧，官方线上 11/12 臂 blown ≈ 0。
增补二 §5.B② 要的「判定 L1 是否在 A 臂上实际咬合」，本节的答复是：**咬合，但只在 1/12 臂、
且肇事维不同，咬合强度不足以解释官方线的失败**。

#### 17.7 口径建议（提交 B/D 裁定，A 线不自行改判据）

按 per-dim 口径（`norm_input_out_of_range_frames_frac`，任一维超出**它自己**的训练范围），
16 臂是 **0.196–0.593**，**全部 > 0.05**；按全局阈值口径只有 1 臂超阈。两者相差 12 倍，
原因是全局阈值被单维主导（trimdone0 的 12.47 全部来自 `state[34]`，gain 12.47），
对 env[3]/env[4]（自身上界只有 4.0/5.0）不敏感——一个帧只要没有哪一维超过 12.47 就不算 blown，
哪怕它在 env[4] 上已经是自己训练范围的 19 倍。

建议（**不改动现有 `INPUT_BLOWUP_TOL` 判据**，只加诊断）：把逐维超界比例或
「最差维超界倍数」`max_j(closed_loop_absmax_j / train_absmax_j)` 作为附加字段进门禁报告。
A 线已把两个口径都写进产物，B/D 可以直接复算。

#### 17.8 改判：§15 的「K=1 突破」撤销候选资格

| 训练 seed | 受控 | raw | success_rise | mean_max_rise | blown_frac | 测量 |
|---|---:|---:|---:|---:|---:|---|
| seed0 | **20/20** | 20/20 | 20/20 | **0.0800** | 0.0002 | 有效 |
| seed1 | **0/20** | 0/20 | 0/20 | 0.0000 | 0.0012 | 有效 |

两个 seed 都测量有效，所以这**不是 L1 事故，是真实的种子方差**。seed0 的 0.0800 m 甚至超过
base-only 参考 0.0764 m（且 `final_rise == max_rise`、20/20 局末仍夹持、flick 0、over_lift 0），
但按纪律单 seed 不得进结论——**K=1 只有 1 个 seed 非零，撤销晋级证据资格**。
seed1 的签名是「20/20 局末夹持但 rise 恒 0」：爪闭合、方块根本没离桌，与 seed0 是两个行为族。

已停掉 K=1 的 seed2/seed3 与 K=1 × 未裁剪 train24 的 2×2 对照（都属「K 杠杆」，
按增补二 §5.A② 让位给 L1 修复臂）。已产出的 seed0/seed1 结果保留。

#### 17.9 K=2 trimdone0 六个训练 seed：双峰分布

| 训练 seed | 受控 | raw | flick | mean_max_rise | blown_frac | 测量 |
|---|---:|---:|---:|---:|---:|---|
| seed0 | (9/20) | 11 | 2 | 0.0376 | 0.2120 | **INVALID** |
| seed1 | 2/20 | 10 | 8 | 0.0134 | 0.0000 | 有效 |
| seed2 | 0/20 | 2 | 2 | 0.0020 | 0.0033 | 有效 |
| seed3 | 17/20 | 17 | 0 | 0.0685 | 0.0000 | 有效 |
| seed4 | **19/20** | 19 | 0 | **0.0719** | 0.0000 | 有效 |
| seed5 | 1/20 | 4 | 3 | 0.0060 | 0.0173 | 有效 |

剔除 INVALID 的 seed0 后，**5 个测量有效的 seed**：受控 2 / 0 / 17 / 19 / 1
→ 均值 **7.8/20 = 39%**，极差 **0–19**。`mean_max_rise` 同样双峰：0.0020 / 0.0060 / 0.0134
对 0.0685 / 0.0719（= base 0.0764 的 89% / 94%），**中间没有点**。

flick 数与受控成功严格反相关（高分 seed 的 flick = 0，低分 seed 的 flick 占 raw 的 75–80%），
说明低分 seed 不是「抬得不够高」而是「靠弹射过 raw 门槛」，与 §16 结论 2 一致。

- **允许写**：「trimdone0 + K=2 在 5 个测量有效的训练 seed 上受控成功均值 7.8/20、极差 0–19，
  分布双峰（≤2 三个 seed、≥17 两个 seed），未达可重复」。
- **禁止写**：「K=2 达到 19/20」「K=2 解决了抬起」「K=2 稳定可复现」。
- 增补一 §5.A③ 要求的「≥2 训练 seed 才进结论节」：本节满足（5 个有效 seed），
  但结论是**否证可重复性**，不是确认能力。

#### 17.10 已落地的 L1 修复臂（在跑）与提前写下的预期

`scripts/a_patch_dataset_std_floor.py`：从 `train24_trimdone0` 派生
`train24_trimdone0_stdfloor`（**源目录一字节未改**，整树复制；本项目数据集约 1 MB），
只 patch `meta/stats.json` 里走 MEAN_STD 的两个 obs 特征的 std。
训练读路径已核实是 `LeRobotDatasetMetadata.__init__ → load_stats(root)`
（`lerobot/datasets/lerobot_dataset.py:169` → `datasets/utils.py:319` 读 `meta/stats.json`），
`meta/episodes/*.parquet` 的逐 episode stats 不参与训练期归一化，保留原值作为「源未被篡改」的证据。

- 效果：`observation.state` 的 min_std 5.07e-04 → 4.12e-03，5 维被抬升；
  `observation.environment_state` **0 维被抬升**（见 17.4）。
- 校验：`--check-ckpt` 读烘进 checkpoint 的 normalizer，与 manifest 逐维相符
  （`CKPT_STD_FLOOR_OK`，最大偏差 2.4e-08 = float32 舍入）→ 训练与推理用的是同一份 floored stats，
  不存在 B 警告的 train/inference 不一致。
- 臂：`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed{0,1,2,4}`，配方与六 seed 扫描**完全一致**，
  单变量 = std 下限。seed 选择对齐已有对照：seed0（无下限 INVALID）、seed1（2/20）、
  seed2（0/20）、seed4（19/20，对照组，验「修复是否伤害已好的 seed」）。

**预期（在看到结果前写下，避免事后合理化）**：由 17.4，下限不咬合 env[3]/env[4]，
而这两维才是官方臂的肇事维，因此 **blown_frac 与受控成功都应基本不变**。
若真如此，本臂的价值是**否证**「std 相对下限能修官方线的 L1」，把修复方向明确推到
「obs 契约变更」或「自定义 processor + 训练推理一致截断」这两条需要监管批准的路上；
若结果反而变好，则说明 state[7/9/11/38] 的过放大虽未越过全局阈值、仍在实质上损害策略，
那 17.6 的「L1 不解释种子方差」需要重议。两种结果都有信息量，故本臂值得跑。

#### 17.11 门槛敏感性重跑：全域不变臂易主（§14 的载体已 INVALID）

`scripts/a_gate_threshold_sensitivity.py` 在 **37 个 strict 臂**（§14 时是 21 个）上重跑，
分母 740 局，`rise_cap=0.15` 不变，仍 import B 的 `judge_file`、不改判据：

| `final_rise` 门槛 | 0.030 | 0.035 | **0.040（现行）** | 0.045 | 0.050 |
|---|---:|---:|---:|---:|---:|
| 受控成功合计 | 182/740 | 151/740 | **118/740** | 99/740 | 86/740 |
| 非零臂数 | 26/37 | 25/37 | **22/37** | 18/37 | 13/37 |

**门槛全域不变且非零的 strict 臂现在只有两个**（§14 时是一个）：

| 臂 | 0.030 | 0.035 | 0.040 | 0.045 | 0.050 | blown_frac | 测量 |
|---|---:|---:|---:|---:|---:|---:|---|
| `trimdone0_minmax_k2_...seed3` | **17** | **17** | **17** | **17** | **17** | 0.0000 | **有效** |
| `trimdone0_minmax_k2_...seed0` | 9 | 9 | 9 | 9 | 9 | 0.2120 | **INVALID** |

近全域不变的还有 `trimdone0_minmax_k2_...seed4` = 19/19/19/19/**18**（blown 0.0000，有效，flick 0）。

三点读法：

1. **§14 第 2 条的载体作废，但结论方向反而变强**：新的门槛稳健臂 seed3 是 17 局而不是 9 局，
   seed4 是 19 局，两者都 `measurement_valid`、flick = 0、`mean_max_rise` 0.0685 / 0.0719
   = base-only 0.0764 的 89% / 94%。「非零 + 非弹射 + 不靠门槛取值 + 输入契约有效」
   这四个条件第一次同时挂在**两个**训练 seed 上。
2. **std-floor 修复臂的高分是贴门槛的**：`trimdone0_stdfloor_minmax_k2_...seed0`
   = 18/18/**16**/15/12，从 0.030 到 0.050 衰减 33%；而 seed3 完全平坦、seed4 只掉 1 局。
   所以 17.10 里那个 16/20 **在门槛稳健性上劣于 seed3 的 17/20**，不能因为它来自「修复臂」就优先引用。
3. **`trimdone0_minmax_k1_...seed0` = 20/20/20/19/18 是全场最高**，但 K=1 已被 seed1（0/20）
   证伪（§17.8），不得作为晋级证据；列在这里只为记录门槛稳健性与种子稳健性是**两件独立的事**——
   一个臂可以门槛极稳健而种子极不稳健。

#### 17.12 std-floor 修复臂四 seed 结果：**否证**（17.10 的预登记预期兑现）

同配方、同训练 seed、单变量 = `observation.state` / `observation.environment_state` 的 std 相对下限：

| 训练 seed | 无下限 受控 | 无下限 blown | 无下限门禁 | 有下限 受控 | 有下限 blown | 有下限门禁 | `mean_max_rise` 无→有 |
|---|---:|---:|---|---:|---:|---|---|
| seed0 | (9/20) | **0.2120** | **INVALID** | **16/20** | **0.0400** | pass（边缘） | 0.0376 → 0.0541 |
| seed1 | 2/20 | 0.0000 | pass | 1/20 | 0.0000 | pass | 0.0134 → 0.0172 |
| seed2 | 0/20 | 0.0033 | pass | 0/20 | 0.0000 | pass | 0.0020 → 0.0024 |
| seed4（对照） | **19/20** | 0.0000 | pass | **14/20** | 0.0000 | pass | **0.0719 → 0.0428** |

**结论：std 相对下限不是官方 LeRobot 线上的 L1 修复。** 三条独立理由：

1. **不咬合肇事维**（§17.4）：`floor(env[3]) = 3.34e-4`、`floor(env[4]) = 3.74e-4`，都比它们的
   std（7.72e-3 / 7.57e-3）小一个量级以上 → 这两维的 std **一个字节都没改**。
2. **唯一违约臂只压到边缘通过、根因未除**：seed0 的 blown 0.2120 → 0.0400，离 `INPUT_BLOWUP_TOL=0.05`
   只差 0.01；闭环 |x| 峰值 **93.4 → 94.7（没降）**，env[4] 仍炸 120 帧。
3. **对最好的臂有害**：对照组 seed4 从 19/20 退到 14/20，`mean_max_rise` 从 base 的 94% 掉到 56%。
   在 3 个「无下限时也测量有效」的共同 seed {1,2,4} 上：无下限 2/0/19（均值 7.0）→
   有下限 1/0/14（均值 **5.0**），方向是变差。

**与 17.10 预登记预期的对照**（预期在看到结果前写下）：第一分支「blown_frac 与受控成功都应基本不变」
在 3 个共同有效 seed 上**成立**（2→1、0→0、19→14，均在种子噪声内）。seed0 确实变了
（blown 降 5.3 倍、受控 9→16），但这是**间接效应而非直接钳制**：下限改的是
`state[7/9/11/12/38]` 的归一化尺度 → 网络学到的是另一个函数 → 闭环轨迹不同 → 方块被夹起后转得少。
证据就是 |x| 峰值几乎没动（93.4 → 94.7）：env[4] 的 **raw 偏差量级没变**，变的只是超阈帧的**计数**。

**统计功效声明（避免过度解读）**：4 个 seed、母体分布本身是 0–19 的双峰（§17.9），
±5 局的差异在种子噪声内。因此本线**不主张「std 下限有害」**，只主张
**「std 下限没有带来可重复的改善，且不消除根因」**——这已足以否证它作为 L1 修复方案。

**L1 在官方入口内已无可用修复**，剩下两条都要监管批准：
- (a) **obs 契约变更**：去掉或重定义 `env[3]/env[4]`（cube_quat 近常量维）。它们与
  `env[7:10]`（gripper_to_cube_pos）在 teacher 分布内高度冗余，但属于 baseline 重置
  （增补二 §4：历史臂失去对照意义，且须同步核对 C 线 `harness/data_bridge.py` / `ledger.py`
  的 60 维维度假设）。
- (b) **自定义 processor 做训练+推理一致截断**：官方 `normalize_processor.py` 无 clip/clamp
  （§17.5），要做必须越出官方入口纪律。
→ **升级给监管裁定**：在 (a)/(b) 获批之前，A 线不再自行开 L1 修复臂；
L1 在官方线上的地位由 §17.6 定死为「测量有效性问题（2/40 臂），不是能力瓶颈」。

#### 17.13 截断因果探针：**L1 在官方臂上的咬合强度 ≈ 0**（回应增补二 §5.B② 与 §6 回流点）

给 `scripts/eval_lerobot_act_runtime.py` 加 `--clip-norm-input C`（**默认关**）：在 `pre()` 归一化之后、
`predict_action_chunk` 之前把两个 obs 特征的归一化值逐维截到 ±C。实现前已实测两件事，
确保这等价于 B 线的 `--clip-norm-input` 而不需要改 lerobot 内部：
① `pre()` 的输出就是真正喂给网络的归一化输入（与手算 `(x−mean)/(std+1e-8)` 最大差 4.7e-05
= float32 舍入）；② `predict_action_chunk` 不会再改写 `batch`（最大差 0.0）。

**回归门禁**：改完先用 `trimdone0_minmax_k2_...seed3` 同参重跑 20 局，对整份 JSON 做全键递归比对，
唯一差异是 `rows[].elapsed_sec`（墙钟）→ `IDENTICAL_MODULO_WALLCLOCK=True` 才继续跑探针。
关闭时**不新增任何 key**（`execution_constraints` 与 `input_contract.clip_probe` 都不写），
既有臂的对照不受影响。

产物单独放 `runs/infra/lerobot_act_env_20260928/clipprobe/`，**不进 `arms_summary.json`、
不当能力数字**；门禁据 `execution_constraints.norm_input_clip` 判 `composite_policy=true`。
同时额外记录**截断前**的越界比例（`mean_preclip_blown_frames_frac`），避免「截断后 0% 越界」把违例藏掉。

| checkpoint（K=2 trimdone0） | C | 受控 | raw | flick | `mean_max_rise` | 截断前 blown | 截断后 blown | 失败相位 | 门禁 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| seed0 | 无截断 | (9/20) | 11 | 2 | 0.0376 | 0.2120 | — | approach×9 | **INVALID** |
| seed0 | 12.469（=自身训练上界） | **9/20** | 11 | 1 | **0.0376** | 0.1180 | 0.0000 | approach×9 | pass（composite） |
| seed0 | 5.0（更紧一档） | **9/20** | 10 | 1 | **0.0374** | 0.0403 | 0.0000 | approach×9, grasp×1 | pass（composite） |
| seed2 | 无截断 | 0/20 | 2 | 2 | 0.0020 | 0.0033 | — | grasp×18 | pass |
| seed2 | 12.469 | **0/20** | 2 | 0 | **0.0020** | 0.0033 | 0.0000 | grasp×18 | pass（composite） |
| seed4（对照） | 无截断 | 19/20 | 19 | 0 | 0.0719 | 0.0000 | — | grasp×1 | pass |
| seed4（对照） | 12.469 | **19/20** | 19 | 0 | **0.0719** | 0.0000 | 0.0000 | grasp×1 | pass（composite） |

**四个可以直接读出的结论：**

1. **截断在官方线上几乎是恒等变换。** 三个 checkpoint 的受控成功 9/0/19 → 9/0/19，
   `mean_max_rise` **到小数点后四位都不变**（0.0376 / 0.0020 / 0.0719），失败相位分布不变。
   唯一变化是 flick 计数（seed0 2→1、seed2 2→0）：截断抹掉了两局的「弹射」外观，
   但那两局的 rise 仍不够 0.04，所以受控成功一格没动。
2. **seed4 是干净的阴性对照**：它闭环 |x| 峰 9.31 < 阈值 12.47，**一帧都没被截到**
   （截断前 blown = 0.0000），所有字段与未截断逐位相同 → 证明探针装置本身不改变任何结果，
   第 1 条不是「探针失灵」造成的假阴性。
3. **C 在 12.469 → 5.0 之间也不敏感**（9/20 → 9/20，raw 11 → 10，m_rise 0.0376 → 0.0374）。
   与 B 在自研线上看到的「C 非单调、1.5→4 局 / 3→1 局」形成对比：官方线上根本没有可被
   截断激活的机制。
4. **`measurement_invalid` 的那 2 个臂可以在复合 policy 标注下重新作为率证据引用**：
   seed0 未截断 9/20（INVALID）与截断后 9/20（valid、composite）**是同一个数字**。
   按 v4「复合 policy ≠ 底模变强」的纪律，写法是
   「seed0 受控 9/20；该数字在推理侧截断（C=12.469）与未截断下相同，
   因此能力主张不依赖截断，但两次测量都属复合 policy 口径」。

**因此对增补二 §2 重分类清单的实证回答是：重分类是形式而非实质。**
- 40 个门禁产物里 **38 个未截断即测量有效**；
- 2 个 INVALID（`k2 seed0` 的 R=2 与 R=1）在截断下数字不变；
- 「A 全部官方臂的闭环成功率在输入契约验证前一律标 L1 暴露、候选」这条，
  在字段补齐 + 探针跑完后可以解除，**但解除的依据是实测咬合强度 ≈ 0，不是字段补齐本身**。

**与 B 自研线结果的差异及机制解释**（这是两条线最重要的分歧点）：

| | B 自研线（`b_act_lift_mb_hist1_pinned_seed0`） | A 官方线（`trimdone0_minmax_k2_seed0`） |
|---|---|---|
| 超训练输入范围的帧 | **94%** | 21.2%（blown）/ 56.5%（per-dim oor） |
| 闭环 \|x\| 峰值 | **20403** | 93.4 |
| 炸穿的维数 | state dim 7/9/11 等多维（`joint_pos_cos`，std 低至 9.67e-05 → 增益 10⁴） | **只有 2 维**（env[3]/env[4]，cube_quat，增益 4.0/5.0） |
| 截断后的变化 | raw 3/20 → 8~15/20，**失效模式整体换类**（漏抓+弹射 → over_lift 全程夹持） | 受控 9/20 → 9/20，**m_rise 四位小数不变**，失效模式不变 |

差异不是「谁测错了」，而是**炸穿的量级与维数差了两个数量级**：B 的线上 60 维输入被多维、
10⁴ 量级地污染，网络首层激活彻底炸穿、输出饱和成 ±1；A 的线上 60 维里只有 2 维被污染到
10² 量级，ACT 的 transformer（40M 参数）显然能把这 2 维当噪声忽略掉。
**同一个 L1 机制，在两条线上的咬合强度完全不同**，所以 B §9 作废清单里对 A 臂的外推
（§7「LeRobot 线不会自动修掉这个缺陷」）在**机制上成立**（官方 MEAN_STD 同样无下限，已核源码），
但在**影响面上不成立**（官方线没有因此失去能力测量）。

**顺带修正 §17.7 的口径建议**：截断到 C=12.469 后 per-dim `oor` 仍是 **0.565**（几乎没降），
而行为完全不变 → 说明 per-dim 越界虽然普遍（16 臂 0.196–0.593），但**行为上无关**。
所以 A 线**撤回**「建议门禁增设 per-dim 判据」的提法，改为：per-dim `oor` 保留为诊断字段，
**不进判据**；现行全局阈值口径是行为上有意义的那一个。要彻底证否还需要一个
「逐维截到各自训练区间」的更强探针（`oor` 按构造降到 0），已列为待办。

### 18. 闭环抬起归因扩到 17 臂：`dz_tail` 与受控成功几乎一一对应（L2 是绑定约束）

§16 的归因工具当时只覆盖 4 个臂。现在把 `--log-actions` 重评扩到 **17 个臂 × 20 局 = 340 局**
（`runs/infra/lerobot_act_env_20260928/actlog/`，归因产物 `closed_loop_dz_diag_A.json`），
并与**当前门禁构建**（v1.2.1，见 §19）的受控成功逐臂对接。闭合校验：340 局残差全 0，
`attribution_closure_violations` 合计 **0**。

| 臂 | K/R | 受控 | 测量 | `dz_tail` | 抬升←bias (m) | 抬升←burst (m) | `mean_max_rise` | high/low 局 |
|---|---|---:|---|---:|---:|---:|---:|---|
| `trimdone0_minmax_k1_...seed0` | 1/1 | **20** | 有效 | **+0.0311** | +0.0718 | +0.0175 | 0.0800 | 20/0 |
| `trimdone0_minmax_k2_...seed4` | 2/2 | **19** | 有效 | **+0.0280** | +0.0764 | +0.0054 | 0.0719 | 19/1 |
| `trimdone0_minmax_k2_...seed3` | 2/2 | **17** | 有效 | **+0.0336** | +0.0595 | +0.0180 | 0.0685 | 17/3 |
| `trimdone0_stdfloor_minmax_k2_...seed0` | 2/2 | **16** | 有效 | **+0.0250** | +0.0639 | 0.0000 | 0.0542 | 16/4 |
| `trimdone0_stdfloor_minmax_k2_...seed4` | 2/2 | **14** | 有效 | **+0.0248** | +0.0525 | 0.0000 | 0.0428 | 14/6 |
| `trimdone0_minmax_k2_...seed0` | 2/2 | (9) | **INVALID** | +0.0130 | +0.0399 | +0.0024 | 0.0376 | 10/10 |
| `train24_minmax_k2_...seed1` | 2/2 | 3 | 有效 | +0.0184 | +0.0330 | 0.0000 | 0.0244 | 3/17 |
| `trimdone0_minmax_k2_...seed1` | 2/2 | 2 | 有效 | +0.0155 | +0.0216 | 0.0000 | 0.0134 | 2/18 |
| `trimdone0_minmax_lr1e-5_s20k_seed0` | 4/4 | 2 | 有效 | +0.0181 | +0.0321 | 0.0000 | 0.0228 | 2/18 |
| `train24_minmax_k2_...seed0` | 2/2 | 1 | 有效 | +0.0170 | +0.0240 | 0.0000 | 0.0152 | 1/19 |
| `trimdone0_minmax_k2_...seed5` | 2/2 | 1 | 有效 | +0.0088 | +0.0100 | 0.0000 | 0.0060 | 1/19 |
| `trimdone0_minmax_k8_...seed0` | 8/8 | 1 | 有效 | +0.0126 | +0.0205 | +0.0019 | 0.0129 | 1/19 |
| `trimdone0_stdfloor_minmax_k2_...seed1` | 2/2 | 1 | 有效 | +0.0176 | +0.0265 | 0.0000 | 0.0172 | 1/19 |
| `trimdone0_minmax_k1_...seed1` | 1/1 | 0 | 有效 | **−0.0009** | +0.0008 | 0.0000 | 0.0000 | 0/20 |
| `trimdone0_minmax_k2_...seed2` | 2/2 | 0 | 有效 | +0.0082 | +0.0062 | 0.0000 | 0.0020 | 0/20 |
| `trimdone0_minmax_lr1e-5_s20k_seed1` | 4/4 | 0 | 有效 | +0.0110 | +0.0113 | 0.0000 | 0.0056 | 0/20 |
| `trimdone0_stdfloor_minmax_k2_...seed2` | 2/2 | 0 | 有效 | +0.0078 | +0.0059 | 0.0000 | 0.0024 | 0/20 |

**结论 1：`dz_tail`（第 100 帧后的 dz 均值）与受控成功几乎一一对应。**

| 相关量（n=16 个测量有效臂） | Pearson | Spearman |
|---|---:|---:|
| `dz_tail` vs 受控成功 | **+0.874** | **+0.946** |
| `rise_from_bias` vs 受控成功 | +0.954 | +0.949 |
| `rise_from_burst` vs 受控成功 | +0.699 | +0.596 |
| `mean_max_rise` vs 受控成功 | +0.975 | +0.967 |

把 INVALID 的 k2 seed0 也算进来（n=17）：Pearson +0.854、Spearman +0.913，结论不变。
`mean_max_rise` 的相关更高，但它与判据 C5 共用同一个量（**定义上耦合**），不能当独立预测器；
`dz_tail` 是**动作侧**的量，与判据无共享变量，才是有信息量的那一个。

**结论 2：分布是双峰的，中间是空的。** 受控 ≥10 的 5 个臂 `dz_tail` 落在 **0.0248–0.0336**
（均值 0.0285）；受控 ≤3 的 11 个臂落在 **−0.0009–0.0184**（均值 0.0122）；
**受控 4–9 的测量有效臂一个都没有**（唯一的 9/20 是 INVALID 那个）。两组之间存在
0.0184 → 0.0248 的**空档**，所以「抬起够不够」不是连续退化的，而是**过不过一道坎**。

**结论 3：§16 结论 1 需要修正一处——burst 不是完全为零，但仍是小头。**
17 臂平均：抬升←burst **0.0027 m**、抬升←bias **0.0327 m**（burst 占 bias 的 8%）；
每局 dz ≥ 0.5 的帧数平均 **0.35 帧**（teacher 是连续 7 帧）。高分组（5 臂）里 burst 均值
0.0082 m、bias 均值 0.0648 m（占 13%）——最高的 `k1 seed0` 有 0.0175 m 来自 burst。
所以准确写法是「**闭环抬起的主体（≈87–100%）来自持续小正 dz 的积分，teacher 式饱和爆发最多贡献 1/8**」，
而不是 §16 当时写的「100%」。

**结论 4：量纲仍然对得上。** 高分组 `dz_tail` 0.0285 × ~200 帧 × 0.011 m/(dz·帧) ≈ **0.063 m**，
与高分组实测 `mean_max_rise` 0.0428–0.0800（base-only 参考上界 0.0764）同量级。

**这条结论改变了什么**

1. **L2 是当前的绑定约束，L1 不是**：§17.6 已证 blown_frac 与受控成功无关联；本节正面给出
   与受控成功几乎单调的那个量是 `dz_tail`。监管 增补二 §1 的三层因果栈在官方线上的权重要改成
   「L1 = 测量有效性问题（2/44 臂）、L2 = 能力瓶颈、L3 = 可通过 trim 缓解的数据配比」。
2. **给任何 L2 修复臂一个可预登记的判据**：修复若有效，`dz_tail` 必须从 0.012 量级进入
   **0.024–0.034** 这个带；`dz_tail` 不动而受控成功变好，说明改的是别的东西（要重新归因）。
3. **解释了 §17.9 的双峰**：6 个 K=2 训练 seed 的受控成功 2/0/17/19/1（+INVALID 的 9）
   对应 `dz_tail` 0.0155/0.0082/0.0336/0.0280/0.0088 —— 种子方差**不是**评测噪声，
   是训练收敛到的 dz 偏置本身在双峰之间跳。这也说明「多跑几个 seed 取平均」不会解决问题，
   要么把 dz 偏置推过坎，要么找到让它过坎的训练条件。

**必须写清的边界**

1. `dz_tail` 是**闭环内测量**的中介量，不是可独立设置的外生变量：这条相关**不构成因果**，
   也不构成「把 dz_tail 调大就能成功」的可执行修复。它的合法用途是归因与预登记判据。
2. 相关建立在 16 个臂上，其中 5 个高分臂有 3 个来自 K=2、2 个来自 std-floor 派生数据集，
   臂之间不是独立同分布抽样（同配方不同 seed 的臂高度相关）。
3. 与 §16 结论 4 的开环 `done_dz`（11 臂，Pearson +0.866 / **Spearman 仅 +0.327**）相比，
   秩相关从 +0.327 升到 +0.946 的主要原因是**受控成功终于有了 0–20 的真实分布**
   （§16 时 8/11 个臂挤在 0–2，秩相关被并列值主导）。所以 §16 边界第 1 条（Spearman 低）
   应改判为「样本无变异所致，不是机制不稳」；开环探针仍是**筛选器**，闭环 `dz_tail` 才是判据级证据。

### 19. 全量重判到当前门禁构建（v1.2.1）：能力数字一格未动，失效模式整体改判

**为什么要做**：B 的门禁在 09-28 一天内从 v1.1 升到 v1.2.1，而 A 目录里 41 份留档裁定停在
**6 个不同的 `gate_build`** 上（`800e1d08a174` / `369595c86a07` / `6bf27fa39e83` /
`22a7d92bec0a` / `28290b9c1b25` / 无指纹），clipprobe 4 份又是第 7 个（`cd96d1cd94c0`）。
这正是 `docs/b_handoff_to_a_20260928.md` §4 点名的产物漂移。

**做法**：新脚本 `scripts/a_regate_gate_current.py`（只读后处理，**import** B 的 `judge_file`、
不复制判据），把 44 个官方臂 + 4 个 clipprobe 臂重判到当前构建
（`gate_version=v1.2.1`、`gate_build=e4f5ec887788`、`spec_sha256=494d5f5babf9`），
产物写 `regate_current/` 子目录，**旧裁定一字节未改**（改判前后可逐臂核对）。

**结果 1：受控成功一格未动。**

| 量（44 臂合计） | 旧构建（v1.1/v1.2 混合） | 当前构建 v1.2.1 |
|---|---:|---:|
| `controlled_success` | **132** | **132** |
| `flick` | **185** | **23** |
| `insufficient_lift` | 30 | **208** |
| `over_lift` | 0 | 0 |
| `provisional_pass` | 0 | 1 |
| 逐臂 `controlled_success` 有变 | — | **0 臂** |
| 逐臂 `gate_pass` / `measurement_valid` 有变 | — | **0 臂** |

**结果 2：失效模式整体改判——A 线的失败几乎全是「夹住了但没抬够」，不是「脱手」。**
v1.2 把 `insufficient_lift` 从 `flick` 里分出来之后：364 局 raw 成功 = 132 受控 + **208 insufficient_lift**
+ 23 flick + 1 provisional。即**非受控的 raw 成功里 94.5% 是抬起高度不够**；
`flick`（真脱手）在 37 个测量有效臂、740 局里只剩 **2 局**（0.27%），
且 44 个臂里 **37 个 flick = 0**、**44 个臂 over_lift 全为 0**。

这条直接改写本文档 §17 之前所有用「flick」描述失败的地方：**那些计数是 v1.1 口径，
含 `insufficient_lift`**。能力数字（受控成功）不受影响，但**归因方向受影响**——
A 线不存在「抬起后开爪扔方块」的问题，存在的是「夹住了、抬到 3.5 cm 就停」。
与 §18 的 `dz_tail` 结论、§6 要点 2 的「`held_at_end` 三臂都 20/20」完全一致。

**结果 3：INVALID 共 7 臂**（其中 5 臂是 v1.2「缺输入契约字段 = INVALID」新增的）：

| 类型 | 臂 | 原因 |
|---|---|---|
| 缺字段 | `train24_lr1e-4_s20k`、`train24_lr1e-5_s20k`、`train24_lr1e-5_actionminmax_s20k`（+`_seed1`/`_seed2`） | 09-28 早段产物，无 `norm_input_blown_frames_frac`（已被同名 `_gatefields` 重评取代，汇总表里折叠） |
| 输入契约违例 | `trimdone0_minmax_k2_...seed0`（blown 0.2120）、`..._seed0_replan1`（0.1692） | §17.2，截断探针下数字不变（§17.13） |

**结果 4：门槛敏感性刷新（39 strict / 37 测量有效，780 局）。**

| `final_rise` 门槛 | 0.030 | 0.035 | **0.040（现行）** | 0.045 | 0.050 |
|---|---:|---:|---:|---:|---:|
| 受控成功合计 | 199/780 | 167/780 | **132/780** | 111/780 | 95/780 |
| 非零臂数 | 27/39 | 26/39 | **23/39** | 19/39 | 14/39 |

±0.005 敏感带（0.035/0.040/0.045，仅测量有效臂）：**threshold_robust 4 臂、
threshold_sensitive 21 臂、always_zero 12 臂**。4 个稳健臂是

| 臂 | 0.035 | 0.040 | 0.045 | 全域（0.030–0.050） |
|---|---:|---:|---:|---|
| `trimdone0_minmax_k2_...seed3` | 17 | **17** | 17 | 17/17/17/17/17（**全域不变**） |
| `trimdone0_minmax_k2_...seed4` | 19 | **19** | 19 | 19/19/19/19/18 |
| `trimdone0_minmax_k2_...seed5` | 1 | 1 | 1 | 2/1/1/1/0 |
| `trimdone0_minmax_k8_...seed0` | 1 | 1 | 1 | 2/1/1/1/1 |

§17.11 的合计（118/740 @0.040，37 臂）与「全域不变臂只有 seed3 + 已 INVALID 的 seed0」
按本次刷新**取代**：合计现在是 132/780 @0.040，全域不变且测量有效的仍只有 **seed3（恒 17/20）**，
seed4 在 0.050 掉 1 局。改判 1 引用的 `trimdone0_minmax_lr1e-5_s20k_seed0`（2/20）
在带内是 **6/2/1**，属 threshold_sensitive——引用必须带敏感带（B 的报告 §3 给了同一写法）。

**结果 5：与 B 的独立实现逐项吻合。** B 的
`docs/b_gate_threshold_sensitivity_20260928.md` §2 覆盖 12 个官方臂，与 A 的 44 臂表重叠 **11 臂**；
在 `final_rise=0.040` 上 **11/11 数字完全相同**（含 `trimdone0_..._seed0` = 2、
`..._seed0_replan1` = 4、`train24_lr1e-5_actionminmax_s20k_gatefields` = 0），
带内极值也一致（seed0：A 的 [6,2,1] 对 B 的 min 1 / max 6）。
两线各自 import 同一个 `judge_file`、各自扫网格，属**独立复算**而非互相引用。

**产物卫生（本次一起做的）**

- `scripts/summarize_lerobot_act_arms.py`：裁定索引新增第三优先级 `regate_current/`（当前构建覆盖旧构建），
  新增 `insuf` / `flick` 两列，`measurement_valid=false` 显示 **INVALID** 而不是 FAIL，
  页脚打印本表所用 `gate_version` / `gate_build`；盲区判定新增 v1.2 的 `field_class` 口径
  （否则旧产物会被当成严格判定、折叠逻辑失效——本次已踩到并修）。
- `scripts/a_gate_threshold_sensitivity.py`：输出新增 `gate_version` / `gate_build` / `gate_spec_sha256`、
  每臂 `measurement_valid` / `ic_status` / `band_class`（robust / sensitive / always_zero）、
  `insufficient_lift` / `over_lift`；表头新增 verdict 与 band 两列。
- 两份汇总产物（`arms_summary.json`、`gate_threshold_sensitivity_A.json`）已按上述重生成，
  全部数字出自**单一构建** `e4f5ec887788`。

### 20. B 线关键结论与官方线的符合性逐条核对

依据：`docs/b_normalization_incident_20260928.md`、`docs/b_handoff_to_a_20260928.md`（18:41）、
`docs/b_controlled_success_v1_20260928.md`（v1.2.1，18:50）、
`docs/b_gate_threshold_sensitivity_20260928.md`（18:42）、`docs/b_agent_review_20260928.md` §7.6，
以及监管 `rl_harness_supervision/supervisor_memo_20260928.md` 增补一/增补二。

| # | B 的关键结论 | A 官方线实测 | 是否符合 |
|---|---|---|---|
| 1 | L1：MEAN_STD 无下限 → 近常量维被放大、闭环炸穿、**开环不可见** | 官方 `normalize_processor.py:335` 同 `denom=std+1e-8`、无 clip（§17.5）；但闭环 \|x\| 峰 **93.4**（B 线 20403），44 臂里只有 **2 臂** blown>0.05；截断探针下 9/0/19 → **9/0/19**、`mean_max_rise` 四位小数不变（§17.13） | **机制成立，量级与影响面不成立** |
| 2 | 肇事维 = `state[7/9/11]`（`joint_pos_cos`，std 低至 9.7e-05） | 官方臂炸的是 **`env[3]/env[4]`**（cube_quat，训练全域 ±0.037、闭环偏差 19 倍）；`state[7/9/11]` 在 A 的闭环里**一帧未炸**，唯一炸过的 state 维是 `state[34]`（1 帧）（§17.3） | **不符合**（obs 拆分不同：官方按 `ACTConfig.validate_features()` 拆 state(50)+env(10)） |
| 3 | 修复 = std **相对**下限 + 训练/推理同一 C 截断 | 下限公式对 `env[3]/env[4]` 算出 3.34e-4 / 3.74e-4 < 它们自己的 std（7.7e-3）→ **一字节未改**（§17.4）；4 seed 修复臂**否证**（共同有效 seed 2/0/19 → 1/0/14，对照 seed4 19→14，\|x\| 峰 93.4→94.7）（§17.12）；官方入口无 clip → 一致截断**做不到**（§17.5） | **部分不符合**；但与 B 自己 §1.1bis 的机制②（真发散不是归一化问题、下限治不了）**一致** |
| 4 | 门禁：blown>0.05 → `INVALID`（测量无效 ≠ 策略失败） | 已落地执行，2 臂 INVALID；A 的评测器 `--record-input-blowup` 默认开 | **符合** |
| 5 | v1.2 §2.6：缺输入契约字段 = INVALID | 已执行：5 个早段盲产物现判 INVALID（汇总表折叠） | **符合** |
| 6 | L2：teacher dz 饱和 → 歧义区回归条件均值 → dz 正偏、无停止条件、**积分过冲 +0.14 m** | §16+§18 独立证实「抬起全靠小正 dz 积分」、`dz_tail` 与受控成功 Spearman **+0.946**；但后果**方向相反**：A 的 44 臂 `over_lift` = **0**、`insufficient_lift` = **208**（§19） | **机制符合，符号相反**（B 线过冲、A 线不足） |
| 7 | §7/§1.3：迁移到官方 LeRobot **不会**自动修好 | 源码核对成立（同一无下限 MEAN_STD）；但官方线并没有因此失去能力测量（37/44 臂测量有效） | **机制成立，影响面不成立** |
| 8 | MIN_MAX **不是**真修复（增补二 §0 已作废「MIN_MAX 免疫 L1」） | 确认：全部官方臂 `STATE=MEAN_STD / ENV=MEAN_STD / 仅 ACTION=MIN_MAX`；MIN_MAX 只在 `denom==0` 时换 eps，`env[3]/env[4]` 的 max−min=0.056/0.060 ≠ 0 | **符合** |
| 9 | 不能用 `success_raw` 选臂；raw 最优 ≠ ctrl 最优 | A 全线以 ctrl 为主指标。补充 A 侧同类证据：`k1 seed0` raw 20/20 且 ctrl 20/20，但同配方 `seed1` raw **0/20** → 选臂还必须带**训练 seed 数**（§17.8） | **符合，且 A 侧加一条** |
| 10 | clip 值不得当超参固化（raw 对 C 非单调）；截断只作探针、必须标复合 policy | 符合：clipprobe 产物单独目录、不进 `arms_summary`、门禁标 `composite_policy=true`。差异：官方线上 C 在 5.0–12.469 之间**完全不敏感**（§17.13 结论 3） | **符合**（纪律一致，现象不同） |
| 11 | 门禁阈值 ±0.005 敏感性：12 臂 0 robust / 5 sensitive；「N/20 不能单独引用」 | 重叠 11 臂 base 数字 **11/11 相同**；A 扩到 39 臂 → 4 robust / 21 sensitive / 12 always_zero；robust 臂是 **k2 seed3（恒 17）与 seed4（19）**，不是改判 1 引用的 2/20 那个臂（§19） | **符合，并已扩围** |
| 12 | v1.2.1 §2.8：输入侧约束也要计入 `composite_policy` | A 的评测器把截断写进 `execution_constraints.norm_input_clip`，正好是被正确识别的那一侧；clipprobe 4 臂重判后 `composite_policy=true`、`constraint_sides={norm_input_clip: exec}` | **符合** |
| 13 | §1.2：不要只补示范条数或加训练步数（已排除欠拟合） | 官方线独立同向：数据 ×5（`train120`，K=4）ctrl 1/20 vs `train24` 2/20；步数 ×2（`s40k`）0/20 vs `s20k` 0/20；步数 ↓（`s6k` 5.9k）3/20 **>** `s20k` 2/20 | **方向符合**（单 seed，证据弱，只作旁证） |
| 14 | 交接单 2：residual 臂「补 2 个字段即可恢复裁定」 | 见 §20.1：**部分成立**——实质判据恢复到 20/20 受控，但仍判 INVALID；过程中还抓到一个**门禁假阴性**通路 | **需修正** |

#### 20.1 residual 臂重判（交接单 2 执行结果）+ 门禁的第一个假阴性实例

`scripts/audit_residual_lift.py` 已按 B 的 §4 补齐 5 个字段（`final_rise / held_at_end /
phase_at_end / rise_at_success / terminal_kind`，只追加、原有键与算法一字节未改），
并在当前 pin 环境（robosuite 1.5.2 + `harness/env_factory`）重跑 20 局，
产物写**新文件** `runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20_gatefields.json`
（09-24 留档 `audit_truth20.json` 未改）。

1. **可复现性**：逐局 `max_rise` 与 09-24 留档**完全相同**，`mean_max_rise` 都是 0.10013615、
   `success_raw` 20/20 → 该臂在 1.5.2 + 物体 pin 下跨版本、跨进程可复现。
2. **第一次重判 = 门禁假阴性**：20 局全被判 `flick`，唯一失败的 check 是 `end_phase`。
   根因：residual audit 只写 `phases`（6 元素状态机日志 `['approach','descend','grasp','lift','hold','done']`），
   **不写 `phase_trace`**，而 `classify_phase_field`（`b_gate_controlled_success.py:96`）只认 `phase_trace`
   → 词表拿不到 → 退回 per-frame 规则 → 状态机的 `'done'` 不在 `{hold, grasp}` 里 → C4 判失败。
   而四条实质判据全过：`held_at_end=True` 20/20、`final_rise` 0.0563–0.1007（全 ≥0.04）、
   `max_rise` ≤0.111（<0.15）、`success_raw` 20/20。留档证据：
   `gate_v121_phase_misclassified_evidence.json` + `audit_truth20_gatefields_pre_phase_trace.json`。
3. **修法在 A 侧**：对齐参考实现 `scripts/audit_lift_base_truth.py:66`（同时写 `phases` 与 `phase_trace`）。
   改完重判 → `phase_field_kinds=['controller_log']`、C4 依据 `controller_log_reached_done`、
   **`controlled_success` 20/20、flick 0、insufficient_lift 0**。
4. **给 B 的建议（不改 B 的文件）**：门禁应加一条自检——`phase_at_end ∈ CONTROLLER_LOG_VOCAB`
   而 `phase_trace` 缺失/为空时，报「phase 词表与字段不匹配」并按 controller_log 处理或降为
   `provisional_pass`，而不是静默按 per-frame 判 `flick`。这是继 v1.1 修掉假阳性之后的
   **第一个假阴性实例**，且它会把一个 20/20 的臂报成「20 局全脱手」。
5. **仍未恢复裁定的原因 = 口径缺口**：SAC 直接吃 raw 60 维 obs（`train_residual_lift.py` 未用
   VecNormalize / `normalize_obs`），**不存在「归一化输入」**，增补二 §3 的
   `norm_input_blown_frames_frac` 没有对应量；训练期 obs 范围也没落盘，事后无法重建等效上界。
   门禁按 v1.2.1 §2.6 判 `measurement_invalid`（`ic_status=unverified`、`learned_policy=true`）→
   `gate_pass=false`。**A 线不自行绕过**（不删 `ckpt` 字段、不伪造 0.0），把裁定权交给 B/D：
   (i) 为无归一化策略定义输入契约（如 \|obs\| ≤ 训练期 absmax，需在训练时落盘 stats），或
   (ii) 给门禁一条显式 `not_applicable` 声明路径（类似 scripted base-only 的豁免）。
6. **这条臂即使恢复也只能算复合 policy**：能力来自 `a = clip(a_base + 0.25·a_residual, −1, 1)`，
   产物已显式写 `execution_constraints`（`scripted_base_controller` / `residual_scale` /
   `residual_phases` / `action_clip`），门禁自动标 `composite_policy=true`、
   `active_constraints` 4 项。**20/20 不得作为 learned-from-scratch 能力引用**，
   也不能用来满足 P1 晋级条件第 1 条对「learned policy」的要求。

#### 20.2 A 欠 B / B 欠 A（截至本节）

| 方向 | 项 | 状态 |
|---|---|---|
| A→B | 交接单 2：residual audit + `eval_act_lift_truth.py` 补门禁字段 | **代码已完成**；residual 臂已重跑重判（§20.1），`eval_act_lift_truth.py` 已补字段但**尚未重跑**（自研线用 B 的 `b_eval_act_lift_v1.py` 更合适，避免两套评测器并行） |
| A→B | 交接单 2 附带的输入契约字段（自研线 / SAC 线） | **阻塞**：无归一化策略的契约口径未定义，已上报（§20.1 第 5 条） |
| A→B | 交接单 1（a/b/c 三项重训） | **未做**：(a) 在官方线已否证（§17.12）、在自研线属 B 的口径；(b) teacher 去饱和 = **baseline 重置**，按增补二 §4 需监管批准，A 不单方面动；(c) `export_lift_to_lerobot.py` 的 std 下限同 (a) |
| A→B | 交接单 3（T17 goal 贯通 2 项） | **未做**，属 v4 P3 的 goal-conditioning 前置，与当前 Lift 门禁不冲突，建议排在 L2 之后 |
| A→B | v1.2.1 规格 §4 的 5 字段中 `rise_at_success` | 官方线评测器**未加**（门禁不消费该字段）；下次改评测器时一并补，避免为单字段重跑 12 臂回归 |
| B→A | 门禁 phase 词表自检（§20.1 第 4 条） | 建议项，A 不改 B 的文件 |
| B→A | 增补二 §5.B② 截断探针移植到官方 ckpt | **A 已代做**（§17.13），结论咬合强度 ≈ 0；建议 B 直接引用而不必重跑 |

#### 20.3 A 线的优先级建议（提交监管裁定）

按 §18/§19 的证据，A 线申请把重心从 L1 转到 **L2 与种子双峰**：

1. **P0：种子双峰归因**（§17.9 + §18 结论 2）。同一配方 6 个训练 seed 落在
   `dz_tail` ≈ 0.008–0.016（受控 0–3）或 ≈ 0.025–0.034（受控 14–19）两簇，中间是空的。
   这是当前最大的未解问题，也是「可重复性」这一晋级条件的直接障碍。
   **只做归因、不做修复**（任何 L2 修复都属 baseline 重置，需先裁定）。
2. **P1：L2 修复方案设计（待批）**。可选杠杆都超出官方入口：teacher 去饱和（增补二 §4 登记）、
   obs 加 `cube_z − z0`（同上，且须核对 C 线 60 维假设）、相位重加权采样（需改 lerobot 内部）。
   预登记判据已备好：修复有效 ⇒ `dz_tail` 进入 0.024–0.034 带（§18）。
3. **P2：`insufficient_lift` 的细分布**（§19 结果 2）。208 局的 `final_rise` 落在 0.035–0.045，
   与门槛高度纠缠；建议与 B 共担一份「按 `final_rise` 直方图」的报告，说明
   「抬到一半就不够」是普遍形态而非个别臂的运气。
4. **降级**：lr1e-4 塌缩臂（机制已由 `max_preclip_abs` 恒 1.0002 解释）、
   K / replan / 数据量杠杆（增补二 §5.A② 已暂停）、评测器 chunk/`n_action_steps` 核查
   （一次性卫生，随下次改评测器一起做）。

### 21. blown 口径单一来源化结案、盲臂补测与 K=1 六 seed 全谱（20:40）

对应监管备忘 增补三 §3 修正 / §9.A②③④⑤ / §12，以及 `work/decisions/decisions_20260928_A.md`
的 ADR-A-001/002/003/004/005。全部产物在 `runs/infra/lerobot_act_env_20260928/`，
门禁一律 `v1.2.1 / e4f5ec887788 / spec 494d5f5babf9`。

#### 21.1 四个新工具（都只读，都不改 B/C/D 的文件）

| 脚本 | 作用 | 产物 |
|---|---|---|
| `scripts/a_eval_idempotence_check.py` | 评测器改动后的**恒等回归**：两份产物全键递归比对，允许差异只有 `rows[].elapsed_sec` + 本次新增键 | `evaluator_patch_regression_k2_seed3.json`、`reblown/reblown_vs_archived_stdfloor_seed0.json` |
| `scripts/a_blown_metric_reconcile.py` | plain vs clip_probe **逐局对账**，把「blown 数字为什么不等」拆成 H1/H2/H3 三个互斥假设 | `blown_metric_reconcile.json` |
| `scripts/a_clamp_bound_no_divergence_case.py` | 单局取证：截断生效但闭环真值逐位不变的局，能否用**时序**解释 | `clampnochange/k2_seed0_ep5011_explained.json` |
| `scripts/a_blindfix_compare.py` | 盲臂补测 vs 留档的**交集字段**比对（旧产物键少，比不了全键） | `blindfix/blindfix_vs_archived.json` |

`a_eval_idempotence_check.py` 是把 A 线纪律「改评测器必须回归」变成**可执行断言**：它不接受
「汇总数字一样」当通过条件，因为本节 §21.3 恰好证明了汇总量（`max_rise`）可以掩盖逐局分岔。

#### 21.2 评测器补丁的验收（ADR-A-001）

同一 ckpt（`trimdone0_minmax_k2_lr1e-5_s20k_seed3`）、同题集重跑 20 局，与留档产物全键递归比对：

| 比对项 | 结果 |
|---|---|
| 值差异 | **20 处，全部是 `$.rows[].elapsed_sec`**（墙钟） |
| 违规（不在允许清单内的值差异） | **0** |
| 新增键 | `$.input_contract.blown_metric_impl`、`$.input_contract.blown_metric_source` |
| 丢失键 | **0** |
| 顶层汇总键（27 个，含 `success_raw/success_rise/mean_max_rise/checkpoint/policy_config/versions`） | 全部相同 |
| 逐局 18 个关键字段（`max_rise/final_rise/phase_trace/phase_at_end/held_at_end/terminal_kind/norm_input_*` 等） | **全部逐位相同** |
| verdict | **PASS** |

clip 探针模式另新增（只在 `--clip-norm-input` 打开时出现，关闭时产物与既有臂同构）：
逐局 `norm_input_clamped_frames` / `norm_input_first_clamped_frame`；块级
`clip_probe.trajectory_note` / `n_episodes_input_clamped` / `total_clamped_frames` / `first_clamped_frames`。

指纹定义：`BLOWN_METRIC_IMPL = sha256(getsource(normalized_input_vector) + getsource(blown_frame_stats))[:12]`
= `52eae25ee2d7`。改这两个函数任一行指纹就变，于是「同一个数字出自不同实现」不可能再悄悄发生。
`a_blown_metric_reconcile.py` 用 AST 从源码文本**独立复算**同一指纹并与产物里的值交叉校验
（当前 `from_source = 52eae25ee2d7`；留档产物早于该字段故 `recorded_in_products` 为空，重测产物已带）。

#### 21.3 对监管 §12 的诊断修正：0.0940 的差 **100% 来自轨迹分岔**

§12 指名对 = `k2 seed0` 的 plain 产物 vs `clipprobe/..._clipC12p469445.json`（同 ckpt、同题集、同帧数口径 150/局）。
三个互斥假设的判定：

| 假设 | 判据 | 结果 |
|---|---|---|
| H1 分母不同 | 逐局 `norm_input_frames_measured` 是否全等 | **否证**（20/20 局全等，两侧都是 150） |
| H2 参与维/阈值不同源 | 在**截断从未生效**的局上比 `absmax` 与 `blown_frac` | **否证**（4 对里 52 个可测局**逐位相等**） |
| H3 不是同一条闭环轨迹 | `phase_trace` 首个分岔帧 + 连续量（`max_rise/final_rise`） | **成立**（23/80 局分岔，且**因果干净**：没有一局在截断未生效时分岔） |

指名对的 6 局分岔明细（`max_rise` 两侧都是 0.0，所以只看 `max_rise` 会判成「轨迹完全一致」）：

| seed | `phase_trace` 首个分岔帧 | `max_rise`（两侧） | blown plain | blown preclip | absmax plain | absmax preclip |
|---|---|---|---|---|---|---|
| 5002 | 56 | 0.0 | 0.0533 | 0.0533 | 20.5209 | 20.9104 |
| 5012 | 48 | 0.0 | **0.8667** | **0.1267** | 27.5916 | 23.8081 |
| 5013 | 75 | 0.0 | **0.6000** | **0.1400** | 24.9029 | 22.3905 |
| 5014 | 138 | 0.0 | 0.7800 | 0.7133 | 20.4657 | 18.1865 |
| 5016 | 53 | 0.0 | **0.8600** | **0.1600** | 25.3965 | **26.5581** |
| 5018 | 114 | 0.0 | 0.6000 | **0.6867** | 26.7190 | **27.7959** |

- 未分岔的 **14 局**：`absmax` 与 `blown_frac` **逐位相等**，对 0.0940 的贡献 = **0.0000**。
- 差值方向**双向**（5012/5013/5016 是 plain 高，5018 是 preclip 高）→ 不存在系统性分母/参与维偏移。
- `final_rise` 有 4 局不同（5012/5014/5016/5018），`success_raw` 与 `held_at_end` 0 局不同。
- D 的「20 局 `max_rise` 逐位相同」**独立复算成立**；需要改判的只是由它推出的「轨迹完全一致」与
  「分母或参与维不一致」这两句。

剂量–反应（同 ckpt、同题集，只换截断电平 C）——这是「差异来自截断改变了行为」的最直接证据：

| C | 截断生效局 | 分岔局 | preclip blown 均值 | plain blown 均值 |
|---|---|---|---|---|
| 12.469445（= 全局阈值） | 7/20 | 6/20 | 0.1180 | 0.2120 |
| 5.0 | **20/20** | **16/20** | **0.0403** | 0.2120 |

对照臂（截断几乎不生效时，两条路径自然重合）：

| 臂 | C | 截断生效 | 分岔 | 可测局 | 可测局 absmax 全等 | plain / preclip blown |
|---|---|---|---|---|---|---|
| `k2 seed2` | 12.469445 | 1/20 | 1/20 | 19 | 是 | 0.0033 / 0.0033 |
| `k2 seed4` | 12.469445 | **0/20** | **0/20** | 20 | 是 | 0.0 / 0.0 |

**方法学要点（为什么 H2 的判据必须是「截断从未生效」而不是「`phase_trace` 相同」）**：
C=5.0 那一对 20/20 局截断都生效，若用 `phase_trace`（离散标签）或 `max_rise`（8 位小数）当同一性判据，
会剩下 4 局「看起来同一但 `absmax` 不等」的**假矛盾**。只有「两侧的 `max|x|` 都 ≤ C」能在**数学上**
保证两次运行是同一个计算（截断退化为恒等映射），所以 H2 只在这类局上判。

#### 21.4 「截断生效但真值逐位不变」的局：时序解释（不是探针失效）

`k2 seed0 ep5011`（C=5.0）看起来自相矛盾：`preclip_absmax = 93.3937`、**72 帧被截**、
`clip_events` 从 300 掉到 **158**、**144 帧动作不同**（逐维最大差：dim2 0.418、gripper 0.632），
但 `max_rise / final_rise / rise_trace / phase_trace` 与未截断产物**逐位相同**。
`scripts/a_clamp_bound_no_divergence_case.py` 的三条判据全部成立：

1. 首个动作不同的 tick = **156** = `norm_input_first_clamped_frame`(78) × `replan_every`(2) → 截断是唯一扰动源；
2. `rise_trace` 峰值 tick = **154** < 156 → 决定成败的那一下发生在扰动**之前**；
3. tick 156 之后两条 `rise_trace` **逐位相同** → 扰动没有再影响方块。

⇒ 这一局「截断生效但真值不变」是**时序**造成的，不是探针失效、也不是产物复制。
该局的 `plain` 动作里 gripper 维恒为 ±1（饱和）、dim3/4/5 恒为 0，截断把 gripper 从 ±1 拉回
0.37~0.90（`clip_events` 300→158 即此），但此时方块已落回桌面静止。

**推论（重要，写进 §21.10 边界）**：`mean_blown_frames_frac` 度量的是**输入越界程度**，不是**行为后果**。
对已经输出饱和/塌缩的 ckpt，48% 帧越界 + 把输入从 93.4 截到 5.0，闭环真值也可能逐位不变。
所以 blown 比例只能当「测量是否可信」的门禁量，**不能反推「炸穿导致了失败」**；
后者必须靠截断探针在**逐臂**层面上的行为差异来证——B 的 PROBE-2（`k2 seed4`，C=3.0，`L1_no_bite`）
正是这种正确用法，A 的核对里该臂「截断从未生效、0 局分岔」与之独立一致。

#### 21.5 [0.03,0.08] 带臂重测（§12 裁定 1）

用 v1.2.1 重判裁定**扫**出来的（不是人工挑的），全仓落在该带的臂只有 1 个：
`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`，`mean_blown = 0.0400`、容差 0.05、**余量仅 0.010**。

| 项 | 留档 | 重测 | 判定 |
|---|---|---|---|
| `mean_blown_frames_frac` | 0.0400 | **0.0400** | 不变 |
| 受控成功 | 16/20 | **16/20** | 不变 |
| `flick` / `insufficient_lift` | 1 / 3 | **1 / 3** | 不变 |
| `success_raw` / `success_rise` | 20 / 16 | **20 / 16** | 不变 |
| `gate_pass` / `measurement_valid` | True / True | **True / True** | 不变 |
| 全键递归比对 | — | 仅 `elapsed_sec` 20 处 + 2 新增键 | **PASS** |
| `blown_metric_impl` | （无该字段） | **52eae25ee2d7** | 已落盘 |

结论：「边缘通过」这个数字**稳定且可复现**，§12 的保留是**程序性**的（口径未单一来源），前提已消除，
提请 D 解除。但 A 不自行宣布解除，且必须同时说明：余量只有 0.010，该臂在 ±0.005 门槛带内属
**sensitive** 而非 robust，引用时仍须带敏感带。

#### 21.6 5 个盲臂补测（§9.A②）：INVALID **7 → 2**

缺陷比 §3 记录的更大：这 5 份出自**旧评测器**，不只缺 `input_contract`，还缺
**10 个逐局门禁字段**（`final_rise / held_at_end / phase_at_end / terminal_kind / norm_input_frames_measured /
norm_input_blown_frames_frac / norm_input_out_of_range_frames_frac / norm_input_absmax / norm_input_top_dim /
norm_input_blown_dims`）与 **7 个顶层键**（`replan_every / replan_every_note / log_actions / input_contract /
mean_final_rise / held_at_end_count / terminal_kind_counts`）→ 门禁只能判 `field_class=partial`。

补测（同协议：20 局 / seeds 5000-5019 / horizon 300 / K=R=4；产物写 `blindfix/`，留档一字节不动）：

| 臂 | 留档 raw / rise / mean_max | 补测 raw / rise / mean_max | 交集比对 | 补测后 field_class / mv / blown | 受控 |
|---|---|---|---|---|---|
| `train24_lr1e-4_s20k` | 0 / 0 / 0.0000 | **同** | IDENTICAL | strict / True / 0.0000 | 0 |
| `train24_lr1e-5_actionminmax_s20k` | 11 / 0 / 0.0134 | **同** | IDENTICAL | strict / True / 0.0000 | 0（insuff 11） |
| `train24_lr1e-5_actionminmax_s20k_seed1` | 0 / 0 / 0.0003 | **同** | IDENTICAL | strict / True / 0.0000 | 0 |
| `train24_lr1e-5_actionminmax_s20k_seed2` | 4 / 1 / 0.0059 | **同** | IDENTICAL | strict / True / 0.0000 | **1**（insuff 3） |
| `train24_lr1e-5_s20k` | 2 / 0 / 0.0021 | **同** | IDENTICAL | strict / True / 0.0000 | 0 |

- **5/5 在共有字段上逐位相同**，各新增 **19** 个字段 → 补测只是把缺失的门禁字段补齐，
  **没有改变任何留档结论**，可以安全 superseded（ADR-A-002 界定的作废范围仅限「门禁可判资格」）。
- `actionminmax_s20k_seed2` **新出 1/20 受控**（此前 INVALID，任何率都不得引用）→ 这是本轮唯一新增的正率臂。
- 剩下 **2 个 INVALID** 是真超阈的 `k2 seed0`（0.2120）与 `k2 seed0_replan1`（0.1692），**维持**。
- 跨线一致性（顺带核掉一个疑点）：A 按 ckpt 现算的 train24 族阈值 = **23.8450** = B 的常量 23.85；
  闭环 absmax **16.13** = B 的 16.1；per-dim oor **0.217~0.980** = B 的 0.217~0.980。
  但 trimdone0 族的 per-ckpt 阈值是 **12.469445** → 两套规则只在**同族数据**上恰好一致，
  跨族引用 blown 必须写明阈值取自哪个 ckpt（已提请 B 在门禁里显式记录 threshold 来源）。

#### 21.7 K=1 六 seed 全谱与 §8 收窄条件判定（§9.A④）

`trimdone0_minmax_k1_lr1e-5_s20k`（口径 1/1/1，`chunk_size=n_action_steps=replan_every=1`，
数据集 `train24_trimdone0`，20k 步，lr 1e-5，ACTION=MIN_MAX），门禁 v1.2.1：

| seed | raw | rise | **受控** | flick | insuff | `mean_max_rise` | `mean_final_rise` | blown | `closed_loop_absmax` | mv | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 20 | **20** | 0 | 0 | 0.0800 | **+0.0800** | 0.0002 | 13.3 | True | True |
| 1 | 0 | 0 | **0** | 0 | 0 | 0.0000 | −0.0087 | 0.0012 | 13.4 | True | False |
| 2 | 0 | 0 | **0** | 0 | 0 | 0.0001 | −0.0094 | 0.0000 | 11.5 | True | False |
| 3 | 12 | 2 | **2** | 0 | 10 | 0.0174 | +0.0147 | 0.0002 | 13.9 | True | True |
| 4 | 0 | 0 | **0** | 0 | 0 | 0.0000 | −0.0102 | 0.0002 | 13.4 | True | False |
| 5 | 1 | 0 | **0** | 0 | 1 | 0.0013 | −0.0076 | 0.0000 | 11.1 | True | False |

n=6、均值 **3.67/20**、极差 **0~20**、非零 **2/6**、受控 ≥ 半数 **1/6**、`measurement_valid` **6/6**、
blown ≤ **0.0012**（**L1 在这个族上完全不涉及**）。

K=2 对照（口径 2/2/2，同数据集同步数）：seed0 9/20（**INVALID**，blown 0.2120）、
seed1 2、seed2 0、seed3 **17**、seed4 **19**、seed5 1 → 有效 n=5、均值 **7.80/20**、极差 0~19、≥半数 **2/5**。

§8 收窄条件逐条判定：

| 条件 | K=1 | K=2 | 判定 |
|---|---|---|---|
| ① ≥3 个训练 seed 受控 ≥ 半数 | **1/6** | **2/5** | **不满足** |
| ② 全部 `measurement_valid` | 6/6 ✓ | 5/6（seed0 violated） | K=2 不满足 |
| ③ 全部在 v1.2.1 上重判 | ✓（`regate_current/` 48 份） | ✓ | 满足 |
| ④ burst 贡献可复现 > 50% | 最高 19.6%（seed0） | 最高 23.2%（seed3） | **21 臂无一达标 → 不可达** |

⇒ **不上调**。晋级条件第 1 条维持「部分满足」；强口径（**可重复**）现在在**两个族**上都被否证
（K=2 给出 0 与 19，K=1 给出 0 与 20），这是比 §17.9 单族双峰更强的证据。

**K=1 与 K=2 的失败形态不同类，不能混读**：K=1 的 4 个 0/20 臂是 `raw=0 / insuff=0 / flick=0`、
`mean_max_rise ≈ 1e-4 m` 的**整体塌缩**（连 env 级成功都没有，方块根本没被抬离桌面）；
K=2 的失败主要是 `raw>0` 但 `insufficient_lift`（夹住了、抬到 3.5–4.5 cm 就停）。
把两族的「0」当同一种失败会导致修错旋钮：前者要修**是否学到任何抬起命令**，后者要修**抬起幅度**。

算力不可比（与 B §5 一致）：`(1,1,1)` 每帧重新推理，推理次数是 `(4,4,4)` 的 **4 倍**，
所以 k1 的 3.67/20 与 k2 的 7.80/20 **不是同等算力下的比较**，本节不做跨口径排序。

#### 21.8 归因扩到 21 臂 / 420 局：`dz_pos_frac_tail` 比 `dz_tail` 更干净（§9.A⑤ 结案）

K=1 六 seed 的闭环 dz 归因（`a_closed_loop_dz_diag.py`，tail 窗口从第 100 帧起，闭合违规 0）：

| seed | 受控 | `dz_mean_tail` | **`dz_pos_frac_tail`** | `rise←burst` | `rise←bias` | `rise←other` | burst 帧/局 |
|---|---|---|---|---|---|---|---|
| 0 | **20** | **+0.03114** | **0.99925** | 0.01751 | 0.07182 | −0.00934 | 1.90 |
| 3 | 2 | +0.01719 | 0.94650 | 0.00000 | 0.02491 | −0.01024 | 0.20 |
| 1 | 0 | −0.00087 | 0.24300 | 0.00000 | 0.00082 | −0.00953 | 0.50 |
| 5 | 0 | −0.00299 | 0.20775 | 0.00000 | 0.00237 | −0.01002 | 0.20 |
| 2 | 0 | −0.00165 | 0.18850 | 0.00000 | 0.00074 | −0.01011 | 0.65 |
| 4 | 0 | **−0.01384** | **0.07375** | 0.00000 | −0.00000 | −0.01017 | 0.25 |

- **§9.A⑤ 结案**：四个 0/20 臂的 `dz_mean_tail` **全为负**，`dz_pos_frac_tail` 只有 **0.074–0.243**
  → 「0/20 是负偏置积分」成立（尾段绝大多数帧下的是**负** dz 命令，方块被压住而不是抬起）。
  `k1 seed1` 的 actlog 此前已存在（§18 表里 `dz_tail = −0.0009`），本轮把 seed2/4/5 补齐，四点同向。
- `dz_pos_frac_tail` 把 6 个 seed **一刀两断**（0.9465+ vs 0.2430−，中间空 0.7），
  比 `dz_mean_tail`（+0.0172 vs −0.0009，量级差小）更适合作预登记判别量。
  建议 L2 修复臂的预登记判据从「`dz_tail` 进入 0.024–0.034 带」**扩写为**
  「`dz_tail` 进入 0.024–0.034 带**且** `dz_pos_frac_tail ≥ 0.9`」（§18 判据不变，只加一条更稳的）。
- 全域相关（20 个有效臂）：`dz_mean_tail` vs 受控成功 **Pearson +0.773 / Spearman +0.944**
  （17 臂时是 +0.874 / +0.946）。Pearson 下降是因为新增的 `k1 seed4`（−0.0138、受控 0）是横轴最左离群点，
  它**符合排序**（Spearman 几乎没动）但拉大线性残差 → §18 的关系是**单调**而非严格线性，引用时以 Spearman 为主。
- **双峰未填平**：高分 5 臂（受控 ≥14）`dz_mean_tail` 0.0248–0.0336，其余 15 臂（受控 ≤3）−0.0138–0.0184，
  **受控 4–9 的臂仍是 0 个**。新增的 `k1 seed0`（0.0311、20/20）落在预登记的 0.024–0.034 带内 → §18 判据继续成立。
- burst 占比：最高 `k2 seed3` **23.2%**、次高 `k1 seed0` **19.6%**，21 臂合计 **7.2%**（burst 0.04525 / bias 0.58390）
  → **无一臂 >50%**，§8 第 4 条不可达（ADR-A-005 第 3 项提请的依据）。

#### 21.9 与 B 线 19:36 两份文档的交叉核验

| 项 | B（`b_official_arms_reclassification_20260928.md` / `b_truncation_probe_official_20260928.md`） | A（本节） | 结论 |
|---|---|---|---|
| 44 臂重判到 v1.2.1 | `runs/infra/b_official_arms/reclassification.json` | `regate_current/` + `regate_diff_current.json` | **逐格 0 差异**（B §3.1 已独立核验）→ 同一判据、同一构建、两条实现路径完全一致 |
| 强臂截断探针 | `k2 seed4`，C=3.0，`L1_no_bite`（raw/受控/四类计数零变化） | 同臂 C=12.469445：截断**从未生效**、0 局分岔、absmax 逐位相等 | **一致**（B 的 C 更紧，是更强的测试；A 的是可测局一致性证据） |
| 基线可复现性 | PROBE 护栏 2：`actionminmax_s20k` 新进程 **20/20 局逐位复现** | 补测 5/5 臂共有字段逐位相同（含该臂） | **一致**，两条独立路径 |
| 全局阈值 | 常量 **23.85** | 按 ckpt 现算：train24 族 **23.8450**、trimdone0 族 **12.469445** | 同族**数值一致**、**规则不同** → 提请 B 在门禁里记录 threshold 来源 |
| k1 族均值 | **10/20**（n=2：seed0 20、seed1 0） | **3.67/20**（n=6：20/0/0/2/0/0） | **需 B 更新**：B §7 引为强结果的 `k1 seed0 = 20/20`，按 B 自己的 §4 纪律（「任何单臂引用都属于挑 seed」）只能以「族均值 3.67/20 + 摆幅 0~20 + n=6」出现 |
| INVALID 计数 | 7（5 缺字段 + 2 超阈） | 补测后实质 **2**（5 缺字段已转 strict + verified_ok） | **需 B 更新** §3 三分类：22 可引用 → **23**、15 有效零成功 → **19**、7 无效 → **2**；§7 回流点条件「blowup 字段补齐」由 37/44 → **42/44**（含 4 个新 K=1 臂则 46/48）。**分母标注（21:55 补）：这行的 23/19/2 是 44 臂口径；48 臂产物级口径的权威值是 24/22/2、裁定 10 免罪后 25/22/1，见 §21.10(1)。两套都对，差值 = 4 个新增 K=1 臂，引用时必须写分母** |

#### 21.10 现行权威汇总（48 臂产物级 / 单一构建 v1.2.1）与分母纪律 —— **21:55 改判重写**

> 本节由 A-1 于 21:55 重写，**取代** 20:37 版。旧版给的「受控 134 / `insufficient_lift` 219 / `flick` 23」
> 是 **blindfix 合并前口径，已作废、不得引用**（其中 16 局 `flick` 是门禁在缺字段时走弱证据分支的产物，
> 见监管增补五 §1 裁定 14）。
> 唯一生产者 = `scripts/summarize_lerobot_act_arms.py`（`schema_version=2`，输出 `{"meta":…, "arms":[…]}`），
> 产物 = `runs/infra/lerobot_act_env_20260928/arms_summary.json`。不要再写第二个汇总脚本。
> 与监管增补五 §3 的权威表**逐格对账一致**（对账 scope 见下表第 1 行）。

**（1）分母：五套口径并列，引用数字必须写明用哪一套**

| 口径 | 计数单位 | 可引用 | 有效零成功 | 无效 | 恒等式 | 状态 |
|---|---|---|---|---|---|---|
| **产物级 48 臂（免罪前）** | 主目录一份 `official_act_truth20_*.json` = 一行 | 24 | 22 | 2 | `48 = 24+22+2` | **权威** |
| **产物级 48 臂（裁定 10 免罪后）** | 同上 | **25** | **22** | **1** | `48 = 25+22+1` | **权威（现值）** |
| **互异实验 dedup（43 行）** | 去掉 5 份 blind 重测产物 | 24 | 18 | 1 | `43 = 24+18+1` | **权威**；跨臂合计优先用这套 |
| 主目录留档口径 | 5 盲臂按「留档缺字段」记 INVALID | 23 | 18 | 7 | `48 = 23+18+7` | **superseded**（旧「41/48 有效」「46/48 含 blindfix」出自这里） |
| 44 臂口径 | `48 = 44 留档 + 4 个新增 K=1 seed2–5` | 23 | 19 | 2 | `44 = 23+19+2` | **superseded**（§21.9 的旧口径；不是错，是分母不同） |

- 48 → 43 的差 = **5 个盲臂各有 3 份产物**（留档 blind / 主目录 `*_gatefields` 重测 / `blindfix/` 补测）。
  本表按**产物级**计数，blind 行与 `_gatefields` 行各占一行 ⇒ 这 5 个实验被计了两次；
  要按互异训练 run 说话就用 dedup 那行。**两套都写出来，不许只报一个数**。
- 44 → 48 的差 = 新增的 K=1 `seed2/3/4/5`（`seed3` 可引用 2/20，`seed2/4/5` 有效零成功）⇒ 23/19/2 → 24/22/2。
- blind 行的**权威数字取 `blindfix/`**（行内 `superseded_by` 指过去），共有字段已证 5/5 逐位相同（§21.6）；
  留档原件一字节未动。

**（2）`validity_class`：三取值，`VALID_probe_exonerated` 不得简写成 `valid`**

| 取值 | 判据 | 臂数（现值） | 引用规则 |
|---|---|---|---|
| `valid` | 门禁 `measurement_valid=true` 且 `field_class=strict` | 46 | 数字可直接引用 |
| `VALID_probe_exonerated` | 原判 `measurement_invalid`（blown 超阈），但同 ckpt 的 clip 探针满足裁定 10 的 **5 条准入**（在 `probe_exoneration()` 里逐条代码断言，不靠约定） | 1 | 引用必须带 **C + 探针路径 + 探针 `gate_build`**；只改 `measurement_valid`，三套账与 `composite_policy` 不动 |
| `invalid` | blown 超阈且无合格探针，或缺逐局门禁字段 | 1 | **测量无效、能力未知**；不得写成「策略失败」（裁定 12） |

免罪臂（唯一一条）的**固定引用格式**：

> `trimdone0_minmax_k2_lr1e-5_s20k_seed0`：**9/20 @ `final_rise ≥ 0.040`**，
> `VALID_probe_exonerated`（C = **12.469445** = 该 ckpt 训练期归一化 `|x|` 上界，
> 探针 `clipprobe/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0_clipC12p469445.json`，
> 探针裁定 `clipprobe/regate_current/gate_..._clipC12p469445.json`，`v1.2.1 / e4f5ec887788`；
> 逐局 verdict 全同、`accounts.policy_independent` 五项计数全同，47 处残余逐局字段差异**全部 verdict 相同**）。

**同臂 C=5.0 的探针不满足准入 1**（`seed 5007` 的 verdict 翻转、`insufficient_lift` 1→0）⇒
「截得越紧越安全」是**错的**：紧到改变行为，它就不是免罪探针而是另一个策略。
维持 INVALID 的一条：`trimdone0_minmax_k2_lr1e-5_s20k_seed0_replan1`（blown **0.1692**，`clipprobe/` 里**无该臂探针**
→ `probe_exoneration.reason = no_probe_product`）。

**（3）合计：四个 scope，每个都带标签（裁定 8 推广 / 裁定 12 / 裁定 14）**

| scope | 臂 | 局 | raw | 受控 | `insufficient_lift` | `flick` | `over_lift` | `provisional_pass` | 用途 |
|---|---|---|---|---|---|---|---|---|---|
| `all_48_products_supervisor_reconcile` | 48 | 960 | 377 | **135** | **235** | **7** | 0 | 0 | 与监管增补五 §3 权威表逐格对账（**含** 2 个 INVALID 臂的标签） |
| `strict_and_valid_pre_exoneration` | 46 | 920 | 362 | 126 | 234 | **2** | 0 | 0 | 「可引用」范围的合计（免罪前） |
| `strict_and_valid_post_exoneration` | 47 | 940 | 373 | 135 | 235 | 3 | 0 | 0 | 现值合计（免罪后） |
| `dedup_post_exoneration` | 42 | 840 | 356 | 134 | 219 | 3 | 0 | 0 | 互异实验口径；跨臂比较用这个 |

- **可引用的 `flick` 只有 2 局 / 920**（0.2%）：7 局里有 5 局落在 2 个 INVALID 臂上
  （`k2 seed0_replan1` 4 局、`k2 seed0` 1 局）。这为 B-7「连续性 / slew-limit 停车」提供依据（增补五 §7）。
- 失效模式标签**只在 `field_class=strict` 且非 `invalid` 的行输出**；其余行表里写 `-`，
  原始值留在 JSON 的 `*_raw` 字段备查（裁定 8 推广 = 裁定 14，A 侧在汇总层执行，**不改门禁**，ADR-A-003）。
- **禁止引用**：`134 / 219 / 23` 这三个数不带 scope 标签出现。它们分别是「blindfix 前的受控 / insuff / flick」，
  分子里混了 5 个 partial 臂与 2 个 INVALID 臂。上表第 4 行的 `134 / 219` 是**另一个口径**（dedup 互异实验），
  数字撞巧但含义不同 ⇒ 引用时必须写 scope 名。

**（4）`blowup_threshold_source`：阈值按族分开，跨族不混尺（裁定 11）**

| 数据族 | `blowup_threshold` | 臂数 | 来源 |
|---|---|---|---|
| `train24` | **23.845039** | 15 | 该 ckpt 自己的 `policy_preprocessor_step_3_normalizer_processor.safetensors` 现算（= B 的常量 23.85） |
| `train24_trimdone0` | **12.469445** | 23 | 同上 |
| `train24_trimdone0_stdfloor` | **12.469445** | 4 | 同上（std 下限修复不改阈值） |
| `train120_trimdone0` | **18.037877** | 5 | 同上 |
| `train24_trimdone60` | **16.407488** | 1 | 同上 |

每行 JSON 都带 `blowup_threshold` / `threshold_semantics` / `stats_file` / `source_ckpt` / `dataset_family` /
`blown_metric_impl` + 门禁侧的 `gate_ic_status` / `gate_ic_tolerance` / `gate_ic_mean_blown_frames_frac` /
`gate_ic_closed_loop_norm_absmax`。留档产物里 39 份的 `blown_metric_impl` 是 `null`（早于 blown 口径单一来源化补丁），
本表如实记 `null` 并附 `blown_metric_impl_note`；**不回填、不伪造指纹**（裁定 15 的落地在 B 侧门禁 v1.3）。

**（5）构建纪律（裁定 16）：本表是 v1.2.1 口径，v1.3 全量重判后必须重出**

- 本表全部裁定出自单一构建 **`v1.2.1` / `gate_build=e4f5ec887788` / `spec 494d5f5babf9`**（`meta.gate_*` 记录）。
- `GATE_BUILD` 是门禁脚本内容哈希，B 在途的 **v1.3 已 ≠ `e4f5ec887788`** ⇒ 改判 7 触发：
  v1.3 落地并全量重判后，**重跑本脚本一次**即可刷新（结构性字段不变，数字列换 build），
  届时本节降级为**历史口径**（不作废，但不得再当现值引用）。
- 两个登记册（`configs/b_blown_impl_grandfathered.json`、`configs/b_probe_exonerations.json`）填好之前
  **不得**用 v1.3 做全量重判（否则 39 份无指纹产物会被判 `missing_new_reject`，整表不可裁定）；
  v1.3 的局部结果**不得**与 v1.2.1 混在同一张表。
- 按监管的 A-1 顺序修正：本轮先交付**结构性**部分（`superseded_by` / `validity_class` /
  `blowup_threshold_source` / 显式分母 / 作废数字标注），数字列在 v1.2.1 上给全并注明 build。

**（5bis）22:55 状态更新：v1.3 / v1.4 已落地，但本表暂不迁移（有一个可核的 blocker）**

- **事实**：B 已提交 v1.3（22:22，commit `8bb554c`）与 **v1.4**（22:44，`3c66215`，落地裁定 14），
  当前工作树门禁 = **`v1.4` / `b9379fdb1089` / spec `132fceb89f68`**；两个登记册
  （`configs/b_blown_impl_grandfathered.json` 21:27、`configs/b_probe_exonerations.json` 21:29）已存在
  ⇒ 裁定 16 第 1 条的前置**已解除**。B 的全量重分类 `runs/infra/b_official_arms/reclassification.json`
  顶层指纹已是 v1.4。
- **计数层：A 独立复核 B §8.4「v1.4 零附带损伤」成立**（逐臂重算，不是引用 B 的结论）：
  48 臂 / 960 局，`raw_success` 377、受控 **135**、`insufficient_lift` **235**、`flick` **7**、
  `over_lift` 0、`provisional_pass` 0、受控 >0 的臂数 25 —— **A(v1.2.1) 与 B(v1.4) 逐格相同**。
- **分类层：差 1 臂，本表暂不迁移**。B 的 v1.4 表给三分类 **24 / 22 / 2**（`NOT_CITABLE_measurement_invalid=2`），
  而增补五 §3 / §7 要求**免罪后 25 / 22 / 1**（`measurement_valid` **47 / 1**）。根因：
  `configs/b_probe_exonerations.json` **只有 1 条**（`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0` 的
  争议带豁免，blown 0.04），**缺 裁定 16 第 4 条明文要求的 `trimdone0_minmax_k2_lr1e-5_s20k_seed0` 条目**
  （blown 0.212、受控 9/20、C=12.469445）；且该册 `_doc` 的「带外（>0.08）一律不受理」把
  **裁定 10 的 clip-at-train-absmax 通道**一起挡掉了（那条规则只对 `probe_kind=reblown_single_source` 成立）。
  ⇒ **迁移会把本表从 25/22/1 拉回 24/22/2，与监管权威表直接冲突**，所以 A 不迁。
  证据与最小修复面见 **`docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`**（A 不改 B 的册子与门禁）。
- **迁移触发条件（A 自己设的闸，写死在这里）**：B 补齐条目 + D 会签后，A 重跑
  `scripts/a_regate_gate_current.py` + `scripts/summarize_lerobot_act_arms.py` 即可迁移；
  **迁移前必须核**新表 `NOT_CITABLE_measurement_invalid == 1` 且三分类 `== 25/22/1`，否则不迁并报回 D。
- **过渡期引用纪律（两个构建并存，计数可互换、分类不可互换）**：
  - 引 A 的 `arms_summary.json` → 带 **`v1.2.1 / e4f5ec887788`** + 三分类 **25/22/1（免罪后）**；
  - 引 B 的 `reclassification.json` → 带 **`v1.4 / b9379fdb1089`** + 三分类 **24/22/2（免罪前）**；
  - **不得**把 B 的 24/22/2 当「免罪后」现值引用，也不得把两张表的分类数字混在同一行。
- **本表回归**：A-2 的 gate_build 处置（§22.9）之后重跑本脚本，与留档 `arms_summary.json`
  **逐字节相同（除 `generated_at`）** ⇒ A-1 未被扰动（生产者只扫父目录，不扫 `ckptseq/`）。

**（6）阈值敏感性产物的口径（`gate_threshold_sensitivity_A.json`，未改）**

该产物按**主目录留档口径**统计：48 臂 / **41 有效** / 5 robust（含 1 个 INVALID → **4 个有效 robust**）/
22 sensitive / 21 always_zero；`gate_build=e4f5ec887788`。有效 robust 臂 =
`k2 seed3`（全域恒 17/20）、`k2 seed4`（19/19/19/19/18）、`k2 seed5`、`k8 seed0`。
换成合并 blindfix 的口径是 **46/48 有效**、免罪后 **47/48**。引用「有效臂数」必须写明用哪一份；
v1.3 全量重判后此产物需与新表一起重出（登记为待办，不在本轮改）。

#### 21.11 评测器 chunk / `n_action_steps` 核查（一次性卫生，§20.3 降级项，随本次改评测器一起做掉）

对 **58 份产物**（主目录 48 + `blindfix/` 5 + `reblown/` 1 + `clipprobe/` 4）逐臂核三条：

| 核查项 | 结果 |
|---|---|
| `chunk_size` / `n_action_steps` 是否逐臂等于该 ckpt 的 `policy_config` | **全部一致**（0 处不符） |
| `replan_every` 默认口径 | 默认 = `n_action_steps`；只有臂名显式带 `replan1` / `replan2` 的 **8 臂**是刻意覆盖（R≠N），且**都已在臂名里标出** |
| `chunk_count == ceil(steps / replan_every)` | **逐臂成立** |

实测 `(K, N, R)` 分布：`(1,1,1)`×6、`(2,2,2)`×13、`(2,2,1)`×2、`(4,4,4)`×15、`(4,4,2)`×1、`(4,4,1)`×5、
`(4,4,None)`×5（5 个盲臂的旧产物无该键，`blindfix/` 补测后为 `(4,4,4)`）、`(8,8,8)`×1。
⇒ 评测器**没有**把 K 与 R 混用，也**没有**在 K=1/K=2 臂上 silently 退回默认 K=4；
§21.7 的 K=1 六 seed 与 §15 的 K 对照都建立在正确的控制器口径上。
这条是纯只读核查，不改评测器、不产生新评测。

### 22. 训练侧种子双峰「分岔何时可观测」（A-2，预登记 21:14:53 / 结果 22:03）

预登记：`docs/a_bimodal_divergence_preregistration_20260928.md`（判据、臂清单、判定规则 R1–R6
**在跑之前**冻结；§10 扩围追加 21:42:35、§11 更正与 R7 追加 21:49、§12 扩围结果 22:03，
三节都是**追加**，§2–§6 原文与阈值一字未改）。
判定器：`scripts/a_ckptseq_verdict.py`（只读，不训练不评测）。
产物：`runs/infra/lerobot_act_env_20260928/ckptseq/`（`actlog_*__step*.json` **16** 份、`gate_*__step*.json` **16** 份、
`dz_diag_ckptseq_batch1.json`、`dz_diag_ckptseq_all.json`、`divergence_verdict.json`、
**权威视图 `divergence_verdict_all.json`**、`build_drift_remediate_diff.json`、`build_drift_remediation_record.json`）。
16 份 gate 现全部判在**单一构建 v1.2.1 / `e4f5ec887788` / spec `494d5f5babf9`** 上（见 §22.9 与预登记 §13）。
**刻意不进主目录 glob**：中间 checkpoint 不是交付臂，混进去会污染 §21.10 的 48 臂权威表（预登记 §8）。

#### 22.1 分辨率上限（结论强度的硬约束）

`checkpoints/last -> 020000` 是**符号链接**、`save_freq=10000` ⇒ 每臂只有 **2 个互异 checkpoint**
（`010000` / `020000`，4 臂的 `checkpoints/` 目录已实测确认）。所以本节能给出的**最强**结论只有：
「分岔**不晚于 10k**」或「分岔**发生在 10k–20k 之间**」或「本分辨率下**未能定位**」。
**禁止**写「分岔发生在第 X 步」——要更细必须重训并加密 `save_freq`（新臂、新预登记、新算力申请）。

#### 22.2 R5 先行门槛：PASS（4/4 IDENTICAL）

`020000` 是**已知答案**的时间点，先拿它对账：4 臂重跑的逐局 `max_rise` / `final_rise`、
`dz_pos_frac_tail` / `dz_mean_tail`（对 `closed_loop_dz_diag_A.json`）、四个聚合量
（`success_raw` / `success_rise` / `mean_max_rise` / `mean_final_rise`）**全部逐位一致**。
⇒ 下面的分岔结论不是评测器或环境漂移造成的。（R5 不过关就整批作废，不解释分岔。）

#### 22.3 首批极端对（4 臂 × 2 ckpt = 8 次评测 / 160 局）

| 族 | `010000`：高分臂 / 低分臂 | `020000`：高分臂 / 低分臂 | 判定 | 允许措辞 |
|---|---|---|---|---|
| K=1（1/1/1） | `NONPOS`（ctrl 0/20，`dz_pos` 0.00000）/ `NONPOS`（1/20，0.15800）⇒ **同级** | `HIGH`（20/20，0.99925）/ `NONPOS`（0/20，0.07375）⇒ 分开 | **R2** | 分岔**发生在 10k–20k 之间** |
| K=2（2/2/2） | `NONPOS`（5/20，0.74575）/ **`HIGH`**（**15/20**，1.00000）⇒ **已分开** | `HIGH`（19/20，1.00000）/ `NONPOS`（0/20，0.86700）⇒ 分开 | **R1** | 分岔**不晚于 10k** |

- **R4 未触发**（首批 8 个时间点全 `verified_ok`，blown 最大 0.0082 < 0.05）⇒ 判定不依赖任何被排除的时间点。
- **R7（增补五 §5 的报告义务）**：`k2 seed2@020000` 的 `dz_pos_frac_tail=0.86700` 落在敏感带 `[0.85,0.95]`
  （`0.85` 切法判 `POS_BIAS`、`0.90/0.95` 切法判 `NONPOS`）⇒ **K=2 族结论必须带「级别归属对阈值敏感」标注**。
  但 **R1 这个判定在三种切法下都成立**（`verdict_by_cut = {0.85:R1, 0.90:R1, 0.95:R1}`），
  因为分离由 `010000` 提供（1.00000 对 0.74575，两侧都远离切点）。
  K=1 族**无敏感格**、三切法都是 R2 ⇒ 可独立陈述。
- **R6：两族结论不一致（R2 对 R1）⇒ 只报族内结论，不得合并成跨口径主张**，并触发预登记 §7 条件 2 的扩围。

#### 22.4 扩围（8 臂 × `010000` × 20 局 = 160 局）：12 臂 10k vs 20k 全表

| 臂 | 族 | 10k `dz_pos_frac_tail` | 10k `dz_mean_tail` | 10k 级别 | 10k 受控 | 20k `dz_pos_frac_tail` | 20k `dz_mean_tail` | 20k 级别 | 20k 受控 |
|---|---|---|---|---|---|---|---|---|---|
| `k1 seed0` | K=1 | 0.00000 | −0.02750 | `NONPOS` | 0/20 | 0.99925 | +0.03114 | `HIGH` | **20/20** |
| `k1 seed1` | K=1 | 0.62950 | +0.01554 | `NONPOS` | ~~6/20~~ **测量无效** | 0.24300 | −0.00087 | `NONPOS` | 0/20 |
| `k1 seed2` | K=1 | 0.08550 | −0.00752 | `NONPOS` | 1/20 | 0.18850 | −0.00165 | `NONPOS` | 0/20 |
| `k1 seed3` | K=1 | 0.04800 | −0.00980 | `NONPOS` | 0/20 | 0.94650 | +0.01719 | `POS_BIAS` | 2/20 |
| `k1 seed4` | K=1 | 0.15800 | −0.00830 | `NONPOS` | 1/20 | 0.07375 | −0.01384 | `NONPOS` | 0/20 |
| `k1 seed5` | K=1 | 0.94125 ⚠ | +0.03517 | `POS_BIAS` | 2/20 | 0.20775 | −0.00299 | `NONPOS` | 0/20 |
| `k2 seed1` | K=2 | 0.20825 | +0.00027 | `NONPOS` | 0/20 | 0.94175 | +0.01549 | `POS_BIAS` | 2/20 |
| `k2 seed2` | K=2 | 1.00000 | +0.02887 | **`HIGH`** | **15/20** | 0.86700 ⚠ | +0.00823 | `NONPOS` | 0/20 |
| `k2 seed3` | K=2 | 1.00000 | +0.04372 | `POS_BIAS` | 5/20 | 0.94925 | +0.03358 | `HIGH` | **17/20** |
| `k2 seed4` | K=2 | 0.74575 | +0.01504 | `NONPOS` | 5/20 | 1.00000 | +0.02803 | `HIGH` | **19/20** |
| `k2 seed5` | K=2 | 0.94875 ⚠ | +0.02686 | **`HIGH`** | **15/20** | 0.66900 | +0.00882 | `NONPOS` | 1/20 |
| `stdfloor k2 seed0` | 另一配方 | 1.00000 | +0.03787 | `POS_BIAS` | **18/20** | 0.95250 | +0.02496 | `HIGH` | 16/20 |

⚠ = R7 敏感格（`[0.85,0.95]`，级别随切点变）。20k 侧**不重跑**：留档 actlog + `closed_loop_dz_diag_A.json`
就是 `020000` 的权威产物（R5 已证 4 臂重跑逐局一致）。`k2 seed0` 按预登记 §4 排除
（`VALID_probe_exonerated` 臂不进判据样本）；stdfloor 是**另一个数据配方**，单列、不并入 K=2 族计数。

#### 22.5 两个预登记问题的答案

**Q1：晋级条件①（同族 ≥3 个 seed 受控 ≥ 半数）在 `010000` 上成立吗？→ 不成立，两个时间点都不成立。**

| 族 | n | 10k 级别分布 | 10k ≥半数 | 20k ≥半数 | 条件① @10k | @20k |
|---|---|---|---|---|---|---|
| K=1（1/1/1） | 6 | `NONPOS`×5、`POS_BIAS`×1 | **0**（`seed1` 时间点 INVALID 不计） | 1（`seed0`） | 不满足 | 不满足 |
| K=2（2/2/2） | 5 | `NONPOS`×2、`POS_BIAS`×1、`HIGH`×2 | **2**（`seed2`、`seed5`） | 2（`seed3`、`seed4`） | 不满足 | 不满足 |
| stdfloor | 1 | `POS_BIAS`×1 | 1（18/20） | 1（16/20） | n=1 无法判 | n=1 无法判 |

⇒ **换 checkpoint 满足不了晋级条件①**：10k 与 20k 上都只有 ≤2 个 seed 过线。§21.7 的「部分满足」维持，
且现在有**两个时间点**的证据，不再只是 20k 快照。

**Q2：`HIGH@10k` 与 `HIGH@20k` 的臂集合重叠多少？→ 0，两族都是空交集。**

| 族 | `HIGH@10k` | `HIGH@20k` | 重叠 | 「≥半数」集合 10k vs 20k | 重叠 |
|---|---|---|---|---|---|
| K=1 | ∅ | `{seed0}` | **0** | ∅ vs `{seed0}` | **0** |
| K=2 | `{seed2, seed5}` | `{seed3, seed4}` | **0** | `{seed2, seed5}` vs `{seed3, seed4}` | **0** |
| stdfloor | ∅（`POS_BIAS`） | `{seed0}` | **0** | `{seed0}` vs `{seed0}` | 1 |

⇒ **「哪些 seed 是好 seed」在 10k 与 20k 上是两个不相交的集合**（K=2：`{2,5}` → `{3,4}`；
`k2 seed2` 在 10k 是 15/20、到 20k 变 0/20，`k2 seed4` 反过来从 5/20 涨到 19/20）。
这是对 §21.7 / §15「seed 单独决定成败」的**直接改判**：好坏不是 seed 的稳定属性，而是
**seed × checkpoint** 的属性；`checkpoints/last`（=020000）作为唯一交付点是一个**未被验证的选择**。

#### 22.6 R4 首次触发：一个时间点测量无效（裁定 12 的措辞纪律）

| (臂, ckpt) | blown | 容差 | 阈值来源 | `status` | 处置 |
|---|---|---|---|---|---|
| `k1 seed1 @ 010000` | **0.0532** | 0.05 | **12.469445**（该 ckpt 自己的 normalizer stats） | `violated` | **该时间点测量无效、能力未知**；`6/20` **不得引用**、不进 Q1 计数 |
| `k1 seed3 @ 010000` | 0.0473 | 0.05 | 12.469445 | `verified_ok` | 未超阈但达容差 **94.6%** → 登记为**近阈**，引用须带 blown 值 |

其余 10 个 (臂, ckpt) 全 `verified_ok`、blown ≤ 0.0210。
**不得**写成「炸穿导致 `k1 seed1@10k` 失败」（裁定 12）：blown 度量的是输入越界程度，不是行为后果。
早期 checkpoint 更容易 OOD 这条预期（预登记 §6）**得到证实**：12 个 10k 时间点里 blown 最大的三个
（0.0532 / 0.0473 / 0.0210）全在 K=1 族的 10k 上，同臂 20k 只有 0.0002–0.0033。

#### 22.7 样本外表现（增补四 §11-A④ 的报告义务，**阈值未改**）

只用第一判据 `dz_pos_frac_tail ≥ 0.9` 切两半（描述统计，不是新判据；INVALID 时间点不参与）：

| 时间点 | `≥0.9` 半区 | `<0.9` 半区 |
|---|---|---|
| `010000`（**样本外**） | n=5、受控均值 **11.0/20**、区间 [2, 18] | n=6、受控均值 **1.167/20**、区间 [0, 5] |
| `020000`（留档，阈值的样本内来源） | n=6、受控均值 **12.667/20**、区间 [2, 20] | n=6、受控均值 **0.167/20**、区间 [0, 1] |

- **成立**：判据在样本外仍把两半的受控成功均值分开（11.0 对 1.167，约 **9.5 倍**），
  且**没有假阳性**（`HIGH@10k` 的两臂实测 15/20 与 15/20）。
- **不成立（必须一起报）**：`dz_mean_tail ∈ [0.024, 0.034]` 的**带上界在样本外低估能力** ——
  `stdfloor k2 seed0@10k`（0.03787、实测 **18/20**）与 `k2 seed3@10k`（0.04372、5/20）都因超出上界
  被判 `POS_BIAS` 而非 `HIGH`。⇒ 带内判据是样本内拟合的产物；`dz_pos_frac_tail` 比 `dz_mean_tail` 带更稳。
- **处置**：不改阈值（21:14:53 冻结）。要改必须**新写一份预登记**，且只对下一批新臂生效，不得回填本批。

#### 22.8 本节允许写的结论（措辞白名单）

1. **K=1 族**（可独立陈述、三切点稳定、无 R7 敏感格）：分岔**发生在 10k–20k 之间**（R2）。
2. **K=2 族**：分岔**不晚于 10k**（R1）+ **级别归属对阈值敏感**（R7 标注，见 §22.3）。
3. **R6**：两族不一致 ⇒ 不做跨口径合并主张（且 K=1 推理次数是 K=4 的 4 倍，本就不可排序）。
4. **Q1/Q2**：晋级条件① 在 10k 与 20k **都不满足**；`HIGH` 与「≥半数」集合在两个时间点**完全不重叠**
   ⇒ 「seed 单独决定成败」改判为「**seed × checkpoint 共同决定**」。
5. **R5 PASS**（4/4 逐局一致）⇒ 以上不是评测器/环境漂移。
6. **`k1 seed1@010000` 测量无效**（blown 0.0532 > 0.05）：能力未知，不得当 0 分用。

**本节不回答**：什么训练动力学**导致**分岔（需加密 `save_freq` + 训练侧探针，属新预登记）；
分岔发生在第几步（分辨率只有 2 个互异 ckpt）；哪个 checkpoint「更好」（需要新的选择准则与新的比较集，
且会牵动 §21.10 的 48 臂比较集 —— 与 A-4 暂缓的理由同源，先议后动）。

#### 22.9 gate_build 漂移的处置（22:40）：16 份 gate 统一到 v1.2.1，**裁定零变化**

预登记 §6 要求「在 v1.2.1 单一构建上判」，但落盘的 16 份 gate 实测横跨 **7 个 `gate_build`**
（`GATE_BUILD` = 门禁脚本内容哈希，B 在 21:16–21:52 期间实时升级 v1.2.1 → v1.3）：
v1.2.1 `e4f5ec887788`×2、v1.3 `4f20b3ec9130`×8、`5d20e5a2dffe`×2、`6999e8ac8526`/`85e63f7c7b0f`/
`934d456e6cd6`/`7d5b62d243a2` 各 1。**处置前 §22 的所有跨臂、跨时间点（10k vs 20k）比较都缺这个前提。**

- **钉扎快照** `runs/infra/lerobot_act_env_20260928/gate_v121_pinned/`：`git archive 0137b33`（基线提交）取出
  门禁脚本 + spec 文档，**刻意复刻 `<root>/scripts` + `<root>/docs` 相对布局**（门禁用
  `_ROOT=Path(__file__).resolve().parents[1]` 定位 `GATE_SPEC_DOC`，布局不同则 spec 哈希会变）。
  自报身份 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`，与 §21.10 的 48 臂权威表指纹逐项相符。
- **只重判、不重跑评测**：16 份 actlog **一字节未动**。可以不重跑的理由是机制性的 ——
  blown 阈值由**评测器**按 ckpt 自己的 normalizer stats 现算并写进 actlog 每行的
  `norm_input_blown_frames_frac`，门禁只比 `INPUT_BLOWUP_TOL = 0.05`；v1.2.1 也**不读** `configs/`
  （grep 确认只读 `_ROOT/GATE_SPEC_DOC` 与命令行传入的 actlog）⇒ 在快照目录内运行与在仓库根运行等价，R4 不翻案。
- **旧 16 份 gate 一律 `mv` 进 `ckptseq/gate_build_drift_backup/`**（工作区禁 `rm`），完整保留可核。
- **结果（`scripts/a_gate_build_drift_check.py` 机器判，不手填）**：
  - 单一构建断言 **PASS**：16/16 = `v1.2.1 / e4f5ec887788 / 494d5f5babf9`，1 个不同指纹（原 7 个）；
  - **实体裁定 16/16 完全一致**（`ALL_VERDICTS_IDENTICAL=PASS`）：比的是三套账五计数 + 三个 denominator、
    `measurement_valid`、`gate_pass`、`field_class`、`n_unjudged`、`raw_success`、`input_contract` 的 9 个裁定键、
    `gate_reason` **语义类别**，以及 **`per_episode` 逐局 verdict（20 局 × 16 臂 = 320 局）**；
  - 14 份「仅指纹变化」，2 份（`k1 seed0` 的 10k/20k）本来就是 v1.2.1、指纹也没变；
  - **10 份只有表述/溯源差异，不计入裁定差异**：`gate_reason` 文案（v1.2.1 短句 vs v1.3 附数值长句，
    类别同为 `measurement_invalid`；唯一一例 = `k1 seed1@010000`）+ v1.3 独有溯源键
    （`threshold_provenance`/`blown_metric_impl`/`blown_metric_impl_status`/`artifact_gate_tolerance`/
    `gate_tolerance_matches`/`in_disputed_band`/`probe_exonerated`）+ `train_time_norm_absmax`
    （v1.2.1 从 actlog 的 `input_constraints` 取，本项目 actlog 放在顶层 `input_contract.blowup_threshold`，故报 null）。
    **溯源没丢**：`a_ckptseq_verdict.py::collect` 读的正是 actlog 顶层那份。
- **权威视图 `ckptseq/divergence_verdict_all.json` 只有 29 处字段变化 = 14 `gate_build` + 14 `gate_version` + 1 `generated_at`，
  实体零变化** ⇒ **§22.8 的 6 条允许结论逐条维持原文**，不新增、不改写、不放宽。
  首批 8 个 tag 的记录：非指纹变化 **0**。
- **免罪与争议带（换构建的两个真实风险点）**：16 份里 `probe_exonerated` **0 份为真** ⇒ 不产生
  `VALID_probe_exonerated` 类别差异；v1.3 的 `DISPUTED_BLOWN_BAND = (0.03, 0.08)` 在本批命中 2 个时间点 ——
  `k1 seed1@010000`（blown **0.0532**，两构建都判 INVALID，**R4 成立**）与
  `k1 seed3@010000`（blown **0.0473**，v1.2.1 下 `measurement_valid=True`，但距容差仅 **0.0027**）。
  **新增 caveat**：任何依赖 `k1 seed3@010000` 的主张必须带「blown 0.0473 距 0.05 容差 0.0027、落在 v1.3 争议带内」标注；
  该时间点在 §22 只作为 `NONPOS`（`dz_pos_frac_tail` 0.048）出现、不参与任何分离主张，故结论不受影响。
- **干净的首批视图**：`ckptseq_batch1_pinned/` 是**全 symlink 影子目录**（判定器逻辑零改动），只含预登记 §4 的
  8 个 tag ⇒ 产物 `ckptseq_batch1_pinned/ckptseq/divergence_verdict_batch1_pinned.json`：
  K1=**R2** / K2=**R1** / R5 **PASS**（4/4，`row_diffs`/`dz_diffs`/`aggregate_diffs` 全 0）/ R6 不一致 ——
  与权威视图完全一致。之所以要它：重判后的 batch-1 视图枚举范围从 11 tag 变 16 tag，
  5 个扩围 tag 在 `dz_diag_ckptseq.json` 里没有 dz（该文件早于它们落盘）⇒ `level=UNKNOWN`，
  会污染 Q1/Q2/样本外分离度的**描述统计**（族判定与 R5 不受影响）。
- **48 臂权威表回归**：重跑 `summarize_lerobot_act_arms.py` 与留档 `arms_summary.json`
  **逐字节相同（除 `generated_at`）**，48 臂 / `v1.2.1` 口径不变 ⇒ **A-1 未被本次处置扰动**
  （生产者只扫父目录的 `official_act_truth20_*.json` 与 `gate_*.json`，不扫 `ckptseq/`）。
- 明细：预登记 `docs/a_bimodal_divergence_preregistration_20260928.md` **§13**（§2–§6 前 131 行与提交版逐字节相同）、
  `ckptseq/build_drift_remediation_record.json`、`ckptseq/build_drift_remediate_diff.json`。

#### 22.10 v1.4 交叉核验（22:55）：分岔结论是**构建不变**的；检查器默认指纹改为跟随权威表

B 在 22:44 落地 **v1.4**（`b9379fdb1089` / spec `132fceb89f68`，实现裁定 14），并在
`docs/b_handoff_to_a_20260928.md` **§8.3bis** 指出 `scripts/a_gate_build_drift_check.py` 硬编码的
v1.2.1 默认指纹已过期、建议改成从权威表读。**A 采纳其选项 2**：

- **检查器改造**：期望指纹默认从 `--authoritative-table`（`runs/infra/b_official_arms/reclassification.json` 顶层
  `gate_version/gate_build/gate_spec_sha256`）读 ⇒ **默认值自动跟随当前权威构建，不会过期**；
  `--pin-a2-prereg` 显式钉到预登记 §6 的 v1.2.1 历史锚点；`--expect-*` 仍可单独覆盖。
  同时修掉报错文案里的硬编码，并按 B 的口径把 diff 分成 `label_migration`（裁定 14 的预期效果，允许）与
  **`stop_signal`**（`controlled_success` / `provisional_pass` 一变就必须停下查）。
- **v1.4 交叉核验（不是迁移）**：用工作树 v1.4 门禁重判同样 16 份 actlog，写**独立子目录**
  `ckptseq/v14_crosscheck/`，再与 v1.2.1 的 16 份逐臂逐局比对 ——
  `SINGLE_BUILD=PASS`、`MATCHES_EXPECTED_v1.4=PASS`、**`ALL_VERDICTS_IDENTICAL=PASS`**、
  **`STOP_SIGNAL=0`**、**`LABEL_MIGRATION_ONLY=0`**（16 份全 `field_class=strict` ⇒ 裁定 14 的弃权路径不触发）。
  ⇒ **§22.8 的 6 条结论在 v1.2.1 / v1.3 / v1.4 三个构建上同结论**，「分岔」不是判据构建的产物。
- **A-2 仍钉在 v1.2.1**：预登记 §6 冻结的锚点不因门禁前进而改；v1.4 结果只作交叉核验留档，
  **不与 v1.2.1 混表**（裁定 16 第 2 条）。产物 `ckptseq/v14_crosscheck/crosscheck_diff.json`。
- **顺带核出 §21.10 的迁移 blocker**：B 的 v1.4 权威表计数层与本表逐格相同，但三分类停在 **24/22/2**
  （免罪前），因为豁免册缺 裁定 16.4 明文要求的 `k2 seed0` 条目 ⇒ 见 §21.10（5bis）与
  `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`。

## 复现命令

```bash
# 0) 重建两个环境（容器重启后必跑；约 3-5 分钟，uv 走缓存）
bash scripts/install_lerobot_act_env.sh

# 1) interchange -> 官方 v3.0 数据集
P=/root/venvs/lerobot_act/bin/python
B=runs/infra/lerobot_act_lift_v30
$P scripts/build_lerobot_act_dataset.py --split train --episodes 1 --out $B/overfit_ep0 --repo-id rl-robot/lift-act-overfit-ep0
$P scripts/build_lerobot_act_dataset.py --split train      --out $B/train24 --repo-id rl-robot/lift-act-train24
$P scripts/build_lerobot_act_dataset.py --split validation --out $B/val8   --repo-id rl-robot/lift-act-val8

# 2) 官方 ACT 训练（单局 overfit；把 overfit_ep0 换成 train24 即全量臂）
R=$PWD/$B
$P -m lerobot.scripts.lerobot_train \
  --dataset.repo_id=rl-robot/lift-act-overfit-ep0 --dataset.root=$R/overfit_ep0 \
  --policy.type=act --policy.chunk_size=4 --policy.n_action_steps=4 \
  --policy.device=cuda --policy.push_to_hub=false --policy.optimizer_lr=1e-5 \
  --policy.normalization_mapping='{"STATE":"MEAN_STD","VISUAL":"MEAN_STD","ENV":"MEAN_STD","ACTION":"MEAN_STD"}' \
  --output_dir=$R/overfit_ep0_lr1e-5_s20k --job_name=overfit_ep0_lr1e-5_s20k \
  --batch_size=8 --steps=20000 --log_freq=100 --eval_freq=-1 --save_freq=10000 \
  --num_workers=4 --seed=0 --wandb.enable=false

# 3) 离线动作对齐审计（只读）
/root/venvs/lerobot_eval/bin/python scripts/audit_lerobot_act_overfit.py \
  --ckpt $B/overfit_ep0_lr1e-5_s20k \
  --src-episode runs/infra/lerobot_act_lift_state_overfit/data/episode_0000.npz \
  --out runs/infra/lerobot_act_env_20260928/overfit_alignment_overfit_ep0_lr1e-5_s20k.json

# 4) 闭环 20 局真值评测
/root/venvs/lerobot_eval/bin/python scripts/eval_lerobot_act_runtime.py \
  --ckpt $B/train24_lr1e-4_s20k --episodes 20 --seed0 5000 --horizon 300 \
  --out runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-4_s20k.json

# 4b) 当前最好的一臂：ACTION 用 MIN_MAX 归一化（其余参数与 #2 完全相同）
$P -m lerobot.scripts.lerobot_train \
  --dataset.repo_id=rl-robot/lift-act-train24 --dataset.root=$R/train24 \
  --policy.type=act --policy.chunk_size=4 --policy.n_action_steps=4 \
  --policy.device=cuda --policy.push_to_hub=false --policy.optimizer_lr=1e-5 \
  --policy.normalization_mapping='{"STATE":"MEAN_STD","VISUAL":"MEAN_STD","ENV":"MEAN_STD","ACTION":"MIN_MAX"}' \
  --output_dir=$R/train24_lr1e-5_actionminmax_s20k --job_name=train24_lr1e-5_actionminmax_s20k \
  --batch_size=8 --steps=20000 --log_freq=100 --eval_freq=-1 --save_freq=10000 \
  --num_workers=4 --seed=0 --wandb.enable=false
/root/venvs/lerobot_eval/bin/python scripts/eval_lerobot_act_runtime.py \
  --ckpt $B/train24_lr1e-5_actionminmax_s20k --episodes 20 --seed0 5000 --horizon 300 \
  --out runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k.json

# 5) flick 门禁（受控成功 vs 弹射），三臂一起过
/root/venvs/lerobot_eval/bin/python scripts/b_flick_check.py \
  runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_s20k.json \
  runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-4_s20k.json \
  runs/infra/lerobot_act_env_20260928/official_act_truth20_train24_lr1e-5_actionminmax_s20k.json \
  --json-out runs/infra/lerobot_act_env_20260928/flick_gate_three_arms.json

# 6) chunk_size 单变量（§15）：把 K=4 换成 K=2 即可，其余与 #4b 完全相同
$P -m lerobot.scripts.lerobot_train \
  --dataset.repo_id=rl-robot/lift-act-train24-trimdone0 --dataset.root=$R/train24_trimdone0 \
  --policy.type=act --policy.chunk_size=2 --policy.n_action_steps=2 \
  --policy.device=cuda --policy.push_to_hub=false --policy.optimizer_lr=1e-5 \
  --policy.normalization_mapping='{"STATE":"MEAN_STD","VISUAL":"MEAN_STD","ENV":"MEAN_STD","ACTION":"MIN_MAX"}' \
  --output_dir=$R/trimdone0_minmax_k2_lr1e-5_s20k_seed0 --job_name=trimdone0_minmax_k2_lr1e-5_s20k_seed0 \
  --batch_size=8 --steps=20000 --log_freq=100 --eval_freq=-1 --save_freq=10000 \
  --num_workers=4 --seed=0 --wandb.enable=false

# 7) 全臂汇总表（只读；自动折叠缺 final_rise 的旧产物）
python3 scripts/summarize_lerobot_act_arms.py \
  --json-out runs/infra/lerobot_act_env_20260928/arms_summary.json

# 8) 门禁 final_rise 阈值敏感性（§14；import B 的 judge_file，不改判据）
python3 scripts/a_gate_threshold_sensitivity.py \
  --json-out runs/infra/lerobot_act_env_20260928/gate_threshold_sensitivity_A.json

# 9) 闭环逐帧动作归因（§16）：先带 --log-actions 重评到子目录，再归因
E=/root/venvs/lerobot_eval/bin/python
mkdir -p runs/infra/lerobot_act_env_20260928/actlog
$E scripts/eval_lerobot_act_runtime.py \
  --ckpt $B/trimdone0_minmax_k2_lr1e-5_s20k_seed0 \
  --episodes 20 --seed0 5000 --horizon 300 --log-actions \
  --out runs/infra/lerobot_act_env_20260928/actlog/actlog_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json
python3 scripts/a_closed_loop_dz_diag.py --per-episode \
  --json-out runs/infra/lerobot_act_env_20260928/actlog/closed_loop_dz_diag_A.json

# 10) 输入契约字段（§17.1）：--record-input-blowup 默认开，重评只加字段、数字逐项不变
#     重评前先把原产物 cp 到 pre_input_contract/ 留档（只复制、不移动、不删除）
O=runs/infra/lerobot_act_env_20260928
mkdir -p $O/pre_input_contract
cp -n $O/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json $O/pre_input_contract/
$E scripts/eval_lerobot_act_runtime.py --ckpt $B/trimdone0_minmax_k2_lr1e-5_s20k_seed0 \
  --episodes 20 --seed0 5000 --horizon 300 \
  --out $O/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json
$E scripts/b_gate_controlled_success.py $O/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json \
  --json-out $O/gate_strict_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json

# 11) 给缺字段的历史臂批量回填（§17.2 表里未列的 21 个门禁产物）
#     不手抄命令：从产物自带的 checkpoint.pretrained_model_dir / replan_every 反推同参命令
python3 scripts/a_backfill_input_contract.py --dry-run          # 先看将要执行什么
python3 scripts/a_backfill_input_contract.py --emit /tmp/a_backfill_ic.sh
setsid nohup bash /tmp/a_backfill_ic.sh > /tmp/a_backfill_ic.log 2>&1 & disown

# 12) L1 修复臂（§17.4 / §17.10）：派生带 std 相对下限的数据集，再按同配方训练
P=/root/venvs/lerobot_act/bin/python
$P scripts/a_patch_dataset_std_floor.py \
  --src $B/train24_trimdone0 --out $B/train24_trimdone0_stdfloor
$P -m lerobot.scripts.lerobot_train \
  --dataset.repo_id=rl-robot/lift-act-train24-trimdone0-stdfloor \
  --dataset.root=$PWD/$B/train24_trimdone0_stdfloor \
  --policy.type=act --policy.chunk_size=2 --policy.n_action_steps=2 \
  --policy.device=cuda --policy.push_to_hub=false \
  --policy.normalization_mapping='{"STATE":"MEAN_STD","VISUAL":"MEAN_STD","ENV":"MEAN_STD","ACTION":"MIN_MAX"}' \
  --policy.optimizer_lr=1e-5 --output_dir=$B/trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0 \
  --job_name=trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0 \
  --batch_size=8 --steps=20000 --log_freq=100 --eval_freq=-1 --save_freq=10000 \
  --num_workers=4 --seed=0 --wandb.enable=false
# 核对下限确实烘进了 checkpoint 的 normalizer（训练/推理同一份 stats）
$P scripts/a_patch_dataset_std_floor.py \
  --check-ckpt $B/trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0 \
  --expect-manifest $B/train24_trimdone0_stdfloor/std_floor_manifest.json

# 13) 截断因果探针（§17.13）：默认关；产物单独放 clipprobe/，不进 arms_summary、不当能力数字
#     C=12.469445 是 trimdone0 系 checkpoint 自己的训练期归一化 |x| 上界
CP=$O/clipprobe; mkdir -p $CP
for SPEC in "seed0:12.469445" "seed0:5.0" "seed4:12.469445" "seed2:12.469445"; do
  S=${SPEC%%:*}; C=${SPEC##*:}; TAG=trimdone0_minmax_k2_lr1e-5_s20k_$S; CT=$(echo $C | tr '.' 'p')
  $E scripts/eval_lerobot_act_runtime.py --ckpt $B/$TAG \
    --episodes 20 --seed0 5000 --horizon 300 --clip-norm-input $C \
    --out $CP/official_act_truth20_${TAG}_clipC${CT}.json
  $E scripts/b_gate_controlled_success.py $CP/official_act_truth20_${TAG}_clipC${CT}.json \
    --json-out $CP/gate_strict_${TAG}_clipC${CT}.json --quiet
done
# 改评测器后必做的回归：全键递归比对，只允许 rows[].elapsed_sec（墙钟）不同

# 14) 全量重判到当前门禁构建（§19）：只读后处理，旧 gate_strict_*.json 一字节不改
$E scripts/a_regate_gate_current.py --dir $O            # -> $O/regate_current/ + $O/regate_diff_current.json
$E scripts/a_regate_gate_current.py --dir $O/clipprobe  # 截断探针臂同样重判（composite_policy 标注不变）

# 15) 刷新两份汇总（§19）：arms_summary 会自动优先采用 regate_current/ 的当前构建裁定
$E scripts/summarize_lerobot_act_arms.py --dir $O --json-out $O/arms_summary.json
$E scripts/a_gate_threshold_sensitivity.py --dir $O --json-out $O/gate_threshold_sensitivity_A.json

# 16) residual 臂补门禁字段后重判（§20.1）：产物写新文件，09-24 留档不动
#     注意用 rlrobot venv（SB3 在 lerobot_eval 里没装）；这里的 RL 与上文 $R（数据集路径）无关
RL=/root/venvs/rlrobot/bin/python
$RL scripts/audit_residual_lift.py --ckpt runs/20260924_142702_sac_lift_residual_grasp_lift/model_final.zip \
  --episodes 20 --seed0 5000 --horizon 300 --residual-scale 0.25 --residual-phases grasp,lift \
  --out runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20_gatefields.json
$E scripts/b_gate_controlled_success.py \
  runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20_gatefields.json \
  --json-out runs/20260924_142702_sac_lift_residual_grasp_lift/gate_v121.json

# 17) 改评测器后必做的**恒等回归**（§21.2）：同 ckpt 重跑 + 全键递归比对
#     允许差异只有 rows[].elapsed_sec 与本次新增键；verdict=PASS 才算改完
$E scripts/eval_lerobot_act_runtime.py --ckpt $B/trimdone0_minmax_k2_lr1e-5_s20k_seed3 \
  --episodes 20 --seed0 5000 --horizon 300 --out /tmp/id_check.json
python3 scripts/a_eval_idempotence_check.py \
  --old $O/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed3.json \
  --new /tmp/id_check.json --out $O/evaluator_patch_regression_k2_seed3.json

# 18) blown 口径单一来源化核对（§21.3，监管 增补三 §12）：H1/H2/H3 三假设逐局判定
python3 scripts/a_blown_metric_reconcile.py          # -> $O/blown_metric_reconcile.json
#     「截断生效但真值逐位不变」的单局取证（§21.4，需 --log-actions 产物）
$E scripts/eval_lerobot_act_runtime.py --ckpt $B/trimdone0_minmax_k2_lr1e-5_s20k_seed0 \
  --episodes 1 --seed0 5011 --horizon 300 --log-actions --out $O/clampnochange/k2_seed0_ep5011_plain_logactions.json
$E scripts/eval_lerobot_act_runtime.py --ckpt $B/trimdone0_minmax_k2_lr1e-5_s20k_seed0 \
  --episodes 1 --seed0 5011 --horizon 300 --log-actions --clip-norm-input 5.0 \
  --out $O/clampnochange/k2_seed0_ep5011_clipC5p0_logactions.json
$E scripts/a_clamp_bound_no_divergence_case.py \
  --plain $O/clampnochange/k2_seed0_ep5011_plain_logactions.json \
  --clip  $O/clampnochange/k2_seed0_ep5011_clipC5p0_logactions.json \
  --out   $O/clampnochange/k2_seed0_ep5011_explained.json

# 19) [0.03,0.08] 带臂重测（§21.5）：写 reblown/ 子目录，留档不动
mkdir -p $O/reblown
$E scripts/eval_lerobot_act_runtime.py --ckpt $B/trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0 \
  --episodes 20 --seed0 5000 --horizon 300 \
  --out $O/reblown/official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json
python3 scripts/a_eval_idempotence_check.py \
  --old $O/official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json \
  --new $O/reblown/official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json \
  --out $O/reblown/reblown_vs_archived_stdfloor_seed0.json
python3 scripts/a_regate_gate_current.py --dir $O/reblown --out-dir $O/reblown/regate_current

# 20) 5 个盲臂补测（§21.6）：写 blindfix/ 子目录，留档不动；交集字段比对后才允许 superseded
mkdir -p $O/blindfix
for JOB in train24_lr1e-4_s20k train24_lr1e-5_actionminmax_s20k \
           train24_lr1e-5_actionminmax_s20k_seed1 train24_lr1e-5_actionminmax_s20k_seed2 train24_lr1e-5_s20k; do
  $E scripts/eval_lerobot_act_runtime.py --ckpt $B/$JOB --episodes 20 --seed0 5000 --horizon 300 \
    --out $O/blindfix/official_act_truth20_$JOB.json
done
python3 scripts/a_regate_gate_current.py --dir $O/blindfix --out-dir $O/blindfix/regate_current
python3 scripts/a_blindfix_compare.py --dir $O --sub blindfix --out $O/blindfix/blindfix_vs_archived.json

# 21) K=1 seed2-5（§21.7，监管 增补三 §9.A④）：训练 -> dz 审计 -> 闭环 -> 门禁 -> actlog
NORM='{"STATE":"MEAN_STD","VISUAL":"MEAN_STD","ENV":"MEAN_STD","ACTION":"MIN_MAX"}'
SRC=runs/infra/lerobot_act_lift_state_overfit/data/episode_0000.npz
for S in 2 3 4 5; do
  JOB=trimdone0_minmax_k1_lr1e-5_s20k_seed$S
  $P -m lerobot.scripts.lerobot_train \
    --dataset.repo_id=rl-robot/lift-act-train24-trimdone0 --dataset.root=$R/train24_trimdone0 \
    --policy.type=act --policy.chunk_size=1 --policy.n_action_steps=1 \
    --policy.device=cuda --policy.push_to_hub=false \
    --policy.normalization_mapping="$NORM" --policy.optimizer_lr=1e-5 \
    --output_dir=$R/$JOB --job_name=$JOB \
    --batch_size=8 --steps=20000 --log_freq=100 --eval_freq=-1 --save_freq=10000 \
    --num_workers=4 --seed=$S --wandb.enable=false
  $E scripts/audit_lerobot_act_lift_frames.py --src-episode $SRC --ckpt $B/$JOB \
    --out $O/lift_frames_dz_$JOB.json
  $E scripts/eval_lerobot_act_runtime.py --ckpt $B/$JOB --episodes 20 --seed0 5000 --horizon 300 \
    --out $O/official_act_truth20_$JOB.json
  $E scripts/b_gate_controlled_success.py $O/official_act_truth20_$JOB.json \
    --json-out $O/gate_strict_$JOB.json --quiet
  $E scripts/eval_lerobot_act_runtime.py --ckpt $B/$JOB --episodes 20 --seed0 5000 --horizon 300 \
    --log-actions --out $O/actlog/actlog_$JOB.json
done
# 回来后重跑 14)/15) 与 dz 归因，把新臂纳入单一构建的汇总
$E scripts/a_closed_loop_dz_diag.py --dir $O/actlog --json-out $O/closed_loop_dz_diag_A.json

# 22) A-1 唯一权威表（§21.10）：schema_version=2 —— validity_class / superseded_by /
#     blowup_threshold_source / 五套显式分母 / 四个带 scope 标签的合计（其一与监管增补五 §3 逐格对账）。
#     裁定 16：v1.3 全量重判后**重跑这一条命令**即可刷新数字列，结构性字段不变。
python3 scripts/summarize_lerobot_act_arms.py --dir runs/infra/lerobot_act_env_20260928 \
  --json-out runs/infra/lerobot_act_env_20260928/arms_summary.json

# 23) A-2 分岔定位（§22）：预登记冻结后才跑；两批各写独立 dz / 判定文件，首批留档不覆盖
E=/root/venvs/lerobot_eval/bin/python
O=runs/infra/lerobot_act_env_20260928
B=runs/infra/lerobot_act_lift_v30
mkdir -p $O/ckptseq
for ARM in trimdone0_minmax_k1_lr1e-5_s20k_seed0 trimdone0_minmax_k1_lr1e-5_s20k_seed4 \
           trimdone0_minmax_k2_lr1e-5_s20k_seed4 trimdone0_minmax_k2_lr1e-5_s20k_seed2; do
  for STEP in 010000 020000; do   # last -> 020000 是符号链接，每臂只有这 2 个互异 ckpt
    TAG=${ARM}__step${STEP}
    $E scripts/eval_lerobot_act_runtime.py --ckpt $B/$ARM/checkpoints/$STEP \
      --episodes 20 --seed0 5000 --horizon 300 --log-actions --out $O/ckptseq/actlog_$TAG.json
    $E scripts/b_gate_controlled_success.py $O/ckptseq/actlog_$TAG.json \
      --json-out $O/ckptseq/gate_$TAG.json --quiet
  done
done
# 扩围 8 臂只跑 010000（预登记 §7/§10.5 原文清单），dz 写**新文件**不覆盖首批
$E scripts/a_closed_loop_dz_diag.py --dir $O/ckptseq --pattern "actlog_*.json" \
  --json-out $O/ckptseq/dz_diag_ckptseq_all.json
python3 scripts/a_ckptseq_verdict.py --dir $O --dz dz_diag_ckptseq_all.json \
  --json-out $O/ckptseq/divergence_verdict_all.json
#   ↑ 只读判定器：R5 先行门槛（020000 vs 留档逐局对账）→ R1/R2/R3 分岔定位 → R4 超阈时间点剔除
#     → R7 三切点（0.85/0.90/0.95）敏感性 → Q1 晋级条件① / Q2 HIGH 集合重叠 → 样本外分离度

# 24) A-3 给 B 的裁定 14 回归算例（v1.3 **局部**结果，写独立子目录，禁入 48 臂表 —— 裁定 16）
mkdir -p $O/v13probe
for ARM in train24_lr1e-4_s20k train24_lr1e-5_s20k train24_lr1e-5_actionminmax_s20k \
           train24_lr1e-5_actionminmax_s20k_seed1 train24_lr1e-5_actionminmax_s20k_seed2; do
  $E scripts/b_gate_controlled_success.py $O/official_act_truth20_$ARM.json \
    --json-out $O/v13probe/gate_partial_$ARM.json --quiet    # 期望：裁定 14 后 unjudged，**不得**出 flick
  $E scripts/b_gate_controlled_success.py $O/blindfix/official_act_truth20_$ARM.json \
    --json-out $O/v13probe/gate_strict_$ARM.json --quiet     # 期望：11/3/2 个 insuff + seed2 ctrl=1（不误伤）
done
#   实测（v1.3 / build 4f20b3ec9130）：partial 侧仍出 flick 11/3/2、unjudged=0 ⇒ 裁定 14 **未落地**；
#   strict 侧 11/3/2 + seed2 ctrl=1 gate_pass=true ⇒ 无误伤；residual 词表侧 unjudged=20 ⇒ 裁定 8 **已修**。
#   明细与逐局 evidence 见 docs/a_handoff_to_b_gate_vocabulary_20260928.md

# 25) A-5：residual 训练脚本前瞻落盘 obs stats（裁定 9 的 ②③④）——200 步冒烟，只验机制不验能力
/root/venvs/rlrobot/bin/python scripts/train_residual_lift.py \
  --steps 200 --eval-freq 100 --horizon 20 --eval-episodes 1 --run-name a5_obsstats_smoke
#   → runs/<ts>_a5_obsstats_smoke/obs_stats.json：normalization="none"、
#     input_contract_status="not_applicable_unnormalized"、train 60 维逐维 absmax（211 obs）、
#     closed_loop_final 越界 1369/25200 = 0.054325 > 0.05 ⇒ bound_satisfied=false（机制生效）。
#   **不重跑 09-24 的 residual 臂**：它们没有这份证据 ⇒ 维持 INVALID / not_applicable_unnormalized。

# 26) A-2 的 gate_build 漂移处置：把 ckptseq/ 的 16 份 gate 统一到 v1.2.1 单一构建（§22.9 / 预登记 §13）
#     只重判、**不重跑评测**（16 份 actlog 一字节未动）；旧 gate 一律 mv 备份（禁 rm）
SNAP=$O/gate_v121_pinned
mkdir -p $SNAP/scripts $SNAP/docs
git archive 0137b33 scripts/b_gate_controlled_success.py docs/b_controlled_success_v1_20260928.md | tar -x -C $SNAP
#   ↑ 必须复刻 <root>/scripts + <root>/docs 相对布局：门禁用 _ROOT=Path(__file__).resolve().parents[1]
#     定位 GATE_SPEC_DOC，布局不同则 gate_spec_sha256 变。自报身份须为 v1.2.1/e4f5ec887788/494d5f5babf9。
mkdir -p $O/ckptseq/gate_build_drift_backup
for f in $O/ckptseq/gate_*.json; do mv "$f" $O/ckptseq/gate_build_drift_backup/; done
for A in $O/ckptseq/actlog_*__step*.json; do
  stem=$(basename "$A" .json); stem=${stem#actlog_}
  # 门禁 gate_pass=False 时 exit 1（FAIL 是正常裁定，不是脚本错误）⇒ 这段**不能**用 set -e
  $E $SNAP/scripts/b_gate_controlled_success.py "$A" --json-out "$O/ckptseq/gate_$stem.json" --quiet
done
python3 scripts/a_gate_build_drift_check.py --dir $O/ckptseq \
  --diff-backup $O/ckptseq/gate_build_drift_backup \
  --json-out $O/ckptseq/build_drift_remediate_diff.json
#   期望：SINGLE_BUILD=PASS、MATCHES_EXPECTED_v1.2.1=PASS、ALL_VERDICTS_IDENTICAL=PASS
#   （16 臂实体裁定全同，含 per_episode 逐局 verdict 320 局；14 份仅指纹变化，10 份只有表述/溯源差异）

# 27) 刷新两份 verdict 视图（权威 = divergence_verdict_all.json）
python3 scripts/a_ckptseq_verdict.py --dir $O --dz dz_diag_ckptseq_all.json \
  --json-out $O/ckptseq/divergence_verdict_all.json
#   期望：与处置前相比只有 29 处字段变化 = 14 gate_build + 14 gate_version + 1 generated_at（实体零变化）
# 干净的首批视图：全 symlink 影子目录，只放预登记 §4 的 8 个 tag（判定器逻辑零改动）
S=$O/ckptseq_batch1_pinned; mkdir -p $S/ckptseq
ln -sfn ../closed_loop_dz_diag_A.json $S/closed_loop_dz_diag_A.json; ln -sfn ../actlog $S/actlog
ln -sfn ../../ckptseq/dz_diag_ckptseq_batch1.json $S/ckptseq/dz_diag_ckptseq_batch1.json
for ARM in trimdone0_minmax_k1_lr1e-5_s20k_seed0 trimdone0_minmax_k1_lr1e-5_s20k_seed4 \
           trimdone0_minmax_k2_lr1e-5_s20k_seed4 trimdone0_minmax_k2_lr1e-5_s20k_seed2; do
  for STEP in 010000 020000; do T=${ARM}__step${STEP}
    ln -sfn ../../ckptseq/actlog_$T.json $S/ckptseq/actlog_$T.json
    ln -sfn ../../ckptseq/gate_$T.json   $S/ckptseq/gate_$T.json; done
done
python3 scripts/a_ckptseq_verdict.py --dir $S --dz dz_diag_ckptseq_batch1.json \
  --json-out $S/ckptseq/divergence_verdict_batch1_pinned.json
#   期望：K1=R2 / K2=R1 / R5 PASS(4/4, diffs 全 0) / R6 不一致 —— 与权威视图一致

# 28) 48 臂权威表回归（证明 A-1 未被 A-2 的处置扰动）
python3 scripts/summarize_lerobot_act_arms.py --dir $O --json-out /tmp/arms_summary_regression.json
#   期望：与留档 $O/arms_summary.json 逐字节相同（除 generated_at），48 臂口径不变。
#   **09-29 起本条的期望口径是 v1.5 / f19f61341cbe**（当时写下这条时是 v1.2.1）：本条验的是
#   「本脚本是 arms_summary.json 的唯一生产者、重跑可复现」，不是「表钉在某个 build 上」。
#   跑在 30–35 的迁移**之前**才会得到 v1.2.1；跑在之后就应得到 v1.5。

# 29) v1.4 交叉核验（§22.10；**不是**迁移，A-2 仍钉 v1.2.1）
X=$O/ckptseq/v14_crosscheck; mkdir -p $X
for A in $O/ckptseq/actlog_*__step*.json; do
  stem=$(basename "$A" .json); stem=${stem#actlog_}
  $E scripts/b_gate_controlled_success.py "$A" --json-out "$X/gate_$stem.json" --quiet   # 工作树门禁
done
python3 scripts/a_gate_build_drift_check.py --dir $X --diff-backup $O/ckptseq \
  --json-out $X/crosscheck_diff.json
#   期望：SINGLE_BUILD=PASS、MATCHES_EXPECTED_v1.4=PASS（默认期望值跟随权威表）、
#         ALL_VERDICTS_IDENTICAL=PASS、STOP_SIGNAL=0、LABEL_MIGRATION_ONLY=0
python3 scripts/a_gate_build_drift_check.py --pin-a2-prereg --dir $O/ckptseq \
  --diff-backup $O/ckptseq/gate_build_drift_backup \
  --json-out $O/ckptseq/build_drift_remediate_diff.json     # A-2 锚点视图，期望 v1.2.1 PASS

# ======================================================================================
# 30-34) 48 臂权威表**迁到 v1.5**（09-29 执行；裁定 27①「先修红绿灯再迁」+ 裁定 29 §2 选 (a)）
#   全部是**只读后处理**：重判只走门禁，actlog 一字节未动，不跑任何训练/评测。
#   权威口径固定写法 = `v1.5 / f19f61341cbe`（裁定 29：**不带 spec 值**，spec 轴是观测日志不是钉子）
# ======================================================================================

# 30) 迁移闸自检：证明判据**有牙**（31 档，fixture 全在内存，不写任何文件）
python3 scripts/a_migration_gate_preflight.py --selftest
#   期望：31/31。关键档位：S18 真条目形状（布尔键 + condN 证据散文）-> OPEN（裁定 27③ 补的缺口）；
#         S19 注入 v1.4 行为的裁定行 -> CLOSED(G2)（G2 实测的牙）；S24 布尔键 false 但散文写满 -> CLOSED(L5)；
#         S29 实测跑不起来 -> CLOSED(G2)（无证据不放行）；S22b 桶里塞 matches=null 的臂 -> WARN(B7b)；
#         S30 **live** 端到端实测（真册子、真产物）-> OPEN

# 31) 迁移前判「现在能不能迁」（CLOSED 时 exit 1，可以直接串在迁移命令前面）
python3 scripts/a_migration_gate_preflight.py
#   期望：MIGRATION_GATE=OPEN、blocking_fail=0、warn=0、total_checks=24
#   G2 = importlib 加载 B 的门禁本尊、对目标臂 plain 产物调 judge_file（json_out=None ⇒ 不写文件）
#   期望 G2 回显：ic_status=probe_exonerated、measurement_valid=True、probe_kind=clip_at_train_absmax、
#                band_checked=False、registered_clip_C=artifact_train_absmax=12.469445、cosign_build_matches=True

# 32) 钉死旧口径（**禁 rm**；复制不移动。regate_current/ 目录名不写死版本号 ⇒ 重判会原地覆盖它）
mkdir -p $O/regate_v121_pinned/{main,blindfix,reblown}
cp -a $O/regate_current/.           $O/regate_v121_pinned/main/
cp -a $O/blindfix/regate_current/.  $O/regate_v121_pinned/blindfix/
cp -a $O/reblown/regate_current/.   $O/regate_v121_pinned/reblown/
cp -a $O/regate_diff_current.json   $O/regate_v121_pinned/ 2>/dev/null || true
#   该目录**不在** summarize_lerobot_act_arms.py::load_gate_index 的扫描范围内 ⇒ 留档不污染现值表
#   （它只扫根目录 gate_*.json / flick_gate_*.json 与三个 regate_current/）

# 33) 全量重判到当前门禁构建（**三个目录都要跑**，否则表里会混 build ⇒ 违反禁跨 build 混引）
python3 scripts/a_regate_gate_current.py --dir $O
python3 scripts/a_regate_gate_current.py --dir $O/blindfix
python3 scripts/a_regate_gate_current.py --dir $O/reblown
#   期望：48 + 5 + 1 = **54 份全部 v1.5 / f19f61341cbe**；阈值常量一个没动（RISE_CAP=0.15、FINAL_RISE_MIN=0.04）

# 34) 重出 48 臂权威表 + 构建迁移回归断言（断言 FAIL ⇒ exit 2 且**不写** --json-out）
python3 scripts/summarize_lerobot_act_arms.py --dir $O \
  --json-out             $O/arms_summary.json \
  --regression-baseline  $O/attribution/arms_summary_v3.json \
  --regression-out       $O/attribution/migration_regression_v121_to_v15.json \
  --allow-build-change
#   期望：构建迁移回归断言 **PASS**，预期差异 201 处 / **非预期 0 处**
#   201 处全是判据构建的函数：gate_version×48、gate_build×48、gate_spec_sha256×48、
#     blowup_threshold_source×48、gate_reason×2、ic_status×2、validity_reason×2、
#     gate_pass×1、measurement_valid×1、probe_exoneration×1
#   **计数层与分母被列为「即使 --allow-build-change 也永远不许动」**（DR-008 验收判据 3 的可执行形式）
#   期望表值：single_build_only=true；免罪前 24/22/2、免罪后 **25/22/1**；
#     validity = valid 46 / VALID_probe_exonerated 1 / invalid 1（唯一 INVALID = _replan1）；
#     probe_kind 列 = clip 1 / reblown 1 / null 46（裁定 24⑤）；
#     48 臂合计 960 局 / raw 377 / 受控 135 / insuff 235 / flick 7 / over 0 / prov 0（与迁移前逐格相同）

# 35) 迁移后复核（A 侧 P0-P7 + B 侧 B0-B8 一起判；只核 A 侧会放过半迁移状态）
python3 scripts/a_migration_gate_preflight.py --mode postcheck
#   期望：POST_MIGRATION_CHECK=OPEN、blocking_fail=0、warn=0、total_checks=17
#   P7 = 按 probe_kind **分组**对账（裁定 24⑤）：A 的 VALID_probe_exonerated 只对应 clip 通道，
#        A 1 臂 / B 2 臂 / design_difference=1（**必然差 1，属设计差异不是缺陷**）

# 留档：$O/migration_gate/preflight_v15_migration_20260929.json
#       $O/migration_gate/postcheck_v15_migration_20260929.json
#       $O/migration_gate/selftest_v15_20260929.txt
#       $O/regate_v121_pinned/PINNED_WHY.md

# ======================================================================================
# 36-37) 裁定 30（DR-D29）：**分布层**引用闸 —— 双峰改述为「强间隙分离」
#   同样是**只读后处理**：join 已有 actlog 名单与已有权威表，不跑任何训练/评测。
#   立的一般规则：**计数层构建不变，分布层构建相关** ⇒ 分布类陈述一律带构建指纹 + 臂集。
# ======================================================================================

# 36) 重出 48 臂表，带上 meta.distribution_layer（裁定 30.4 的代码承载）
python3 scripts/summarize_lerobot_act_arms.py --dir $O \
  --json-out             $O/arms_summary.json \
  --regression-baseline  $O/attribution/arms_summary_v3.json \
  --regression-out       $O/attribution/dist_layer_regression_v15.json \
  --allow-build-change
#   期望：构建迁移回归断言仍 **PASS，预期差异 201 / 非预期 0** ⇒ 分布层块是**纯附加**，
#         计数层 / 分母 / 合计一格未动（与 34) 的迁移断言同值，两份报告并存、互不覆盖）
#   新增只读参数 --actlog-diag（默认在 --dir 下找 closed_loop_dz_diag_A.json；读不到就跳过该臂集，不阻断）
#   期望 meta.distribution_layer 回显三套臂集：official_all(48) / measurement_valid(47) / actlog_subset(21)
#     21 臂：低簇 0–3 = 15、高簇 14–20 = 5、空带 4–8 = 0、空带 10–13 = 0、4–9 = **1**、characterization=gap_separated
#     48 臂：直方图 {0:23,1:9,2:6,3:2,4:1,9:2,14:1,16:1,17:1,19:1,20:1}、4–9 = **3**、characterization=mixed
#     build_fingerprint 只锚 build 轴（gate_version/gate_build），spec 写 observation_only（裁定 29.1）

# 37) 分布层闸：先自检证明**有牙**，再判现场（CLOSED 时 exit 1）
python3 scripts/a_distribution_layer_check.py --selftest
python3 scripts/a_distribution_layer_check.py --json-out $O/distribution_layer/ruling30_check_20260929.json
#   期望：自检 **12/12**；现场 DISTRIBUTION_LAYER_CHECK=**OPEN**、blocking_fail=0、warn=0、total_checks=**10**
#   D2 = 21 臂 join 后 4–9 计数 == **1**（不是 0），且那一臂就是 裁定 10 的免罪臂本尊
#        （validity_class=VALID_probe_exonerated、probe_kind=clip_at_train_absmax）
#   D3 = 定性 gap_separated，空带 **4–8 与 10–13**；产物回显值必须 == 现场重算值
#   D4 = A 表 ↔ B 表 21 臂计数逐格相同（A `success_raw` ↔ B `raw_success`，**显式映射**）
#        且 A 表 build == B 表 build == live 门禁 sha256[:12]
#   D6 = **禁用写法扫描**（扫 docs/a_*.md + daily_report.md，**A 不自免**）：出现「4–9 = 0」「中间是空的」
#        必须在 ±8 行内带更正指针（裁定 30 / DR-D29 / 强间隙分离 / 4–8 与 10–13 …）
#   D8 = 分布层构建相关的双向证据：v1.2.1 历史表 n_artifacts=**44**、无效臂 **7**；v1.5 无效臂 **1**
#   非恒真：可红条件 =「21 臂 join 后 4–9 == 0」，现场实测 == 1；自检 S2/S3 让它变 0 ⇒ 必须红，
#           **S9** 同一句禁用写法但带指针 ⇒ D6 必须**放行**（证明 D6 不是恒假）
#   留档：$O/distribution_layer/ruling30_check_20260929.json
#         $O/attribution/README_BASELINE.md（为什么 arms_summary_v3.json 的 meta 必须停在 v1.2.1）

# ======================================================================================
# 38) A 线**新复现主张**的就绪闸（裁定 29.4 / 增补七 §19-A④ 的代码承载）
#   只读：探两个 venv 的解释器 + 读 C 的 manifest，不装任何东西、不写任何文件。
#   pin 全部照抄 docs/lerobot_env_reinstall_pin_20260929.md（B / DR-012）§2，**A 不自己定 pin**。
# ======================================================================================
python3 scripts/a_env_readiness_gate.py --selftest     # 期望 10/10（fixture 全在内存，不起子进程）
python3 scripts/a_env_readiness_gate.py \
  --json-out $O/env_readiness/a_env_readiness_20260929.json
#   期望（**0929 检修后的真实现场**）：A_NEW_REPRO_CLAIMS=**BLOCKED**、blocking_fail=**6**(E1–E6)、
#     warn=0、total_checks=7、**exit 1**；只有 E7（两份 lock 在位）PASS
#   E2 判 `lerobot.__version__ == 0.4.4`，**不是**只验 importable —— B §4 实测：离线候选源
#     `lerobot_0cf8648` 比 tag v0.4.4 **落后 488 commit**、pyproject 写 version=0.1.0，
#     从它装出来 `import lerobot` **照样成功** ⇒「只验 importable」是恒真判据（自检 S2 就是这一档）
#   E6 读 C 的 manifest：`reproduction_claims_blocked.blocked` 必须为 false 且 `env_fully_restored` 为 true
#   解除条件：`bash scripts/install_lerobot_act_env.sh` 重建 lerobot_act + lerobot_eval 两个 venv
#     （属**环境重建**，裁定 29.4 分工是 C 的 P0；**A 不代跑**，避免与 C 同时建同一份 venv）
#     ⇒ 本闸 E1–E6 变绿后，A 才可以声称新的训练 / 评测复现
```

## 不能声称的事

- 不能把 teacher replay 的 20/20 说成 learned ACT 成功（09-24 的纪律继续有效）。
- 单局 overfit 的对齐结果只覆盖训练 episode，不代表 test seeds 上的能力。
- 闭环评测是 robosuite 仿真真值，不是真机；`claim` 字段写的是 `closed_loop_sim_truth`。
- 本轮没有 residual、没有 guard/recovery、没有视觉、没有 PickPlace，也没有跑 harness 闭环 A/B；
  晋级条件（`rl_harness_supervision/supervisor_review_20260924.md`）没有因为本轮而自动满足。
- `runs/infra/lerobot_official_env/` 与 `lerobot_official_env_torch27/` 保留原样未改动，
  作为 09-24 那次尝试的证据；它们不是可用环境，不要再用。
- **不能裸引用「K=2 seed0 受控 9/20」**：未截断时 blown = 0.2120 > 0.05、闭环 |x| 峰 93.4，
  门禁判 `measurement_invalid`（§17.2）。允许的唯一写法是带复合 policy 标注：
  「seed0 受控 9/20；该数字在推理侧截断（C=12.469）与未截断下**相同**，能力主张不依赖截断，
  但两次测量都属复合 policy 口径」（§17.13）。同一 checkpoint 的 R=1 变体也 INVALID（blown 0.1692）。
- **不能说「K=2 解决了抬起」**：6 个训练 seed 里 5 个测量有效 = 2/0/17/19/1，均值 7.8/20、
  极差 0–95%、**双峰**（§17.9）。允许写的只有「均值 7.8/20、极差 0–19、分布双峰、未达可重复」。
- **不能说「K=1 达到 20/20」**：seed0 20/20 而 seed1 0/20，两 seed 都测量有效，
  是真实种子方差；单 seed 非零按纪律不得作为晋级证据（§17.8，§15 的候选资格已撤销）。
- **不能说「加了 std 下限就修好了官方线的 L1」**：四 seed 修复臂已**否证**——肇事维
  `env[3]/env[4]`（cube_quat 近常量维）的 std 一个字节都没改（floor 比 std 小 23 倍），
  对照组 seed4 从 19/20 退到 14/20，seed0 的 |x| 峰 93.4 → 94.7 没降（§17.4、§17.12）。
  也**不能反过来说「std 下限有害」**：4 seed、母体双峰 0–19，±5 局在种子噪声内。
- **不能说「官方 LeRobot 支持训练/推理一致截断」**：`normalize_processor.py` 全文无 clip/clamp，
  MEAN_STD 纯线性、MIN_MAX 不外 clip；要做必须自定义 processor，越出官方入口纪律（§17.5）。
- **引用输入契约数字必须说明口径**：per-dim 超界比例 16 臂全在 0.196–0.593（全部 > 0.05），
  全局阈值口径只有 2/40 臂超阈，因为阈值被 `state[34]` 单维主导（§17.7）。
  但截断探针显示：截到全局阈值后 per-dim oor 仍是 0.565 而**行为四位小数不变** →
  per-dim 越界虽普遍却**行为上无关**，A 线已**撤回**「建议门禁增设 per-dim 判据」的提法，
  per-dim `oor` 只保留为诊断字段（§17.13 末）。
- **不能把 L1 当成官方线的能力瓶颈**：blown_frac 与受控成功无关联
  （seed4 blown 0.0000 → 19/20；seed1 blown 0.0000 → 2/20），瓶颈仍是 §16 的 L2（§17.6）。
- **不能说「K=2 在 seed0 之外都失败」**：§15 当时只有 seed0/1/2 = 9/2/0；补到 6 seed 后是
  seed3 17/20、seed4 19/20（均测量有效），分布是双峰而不是「一个幸运 seed」（§17.9）。
- **不能说「学会了 teacher 的抬起动作」**：闭环里 dz ≥ 0.5 的饱和爆发帧平均每局 0–0.25 帧
  （teacher 是连续 7 帧），全部抬升来自 0.005 ≤ dz < 0.5 的持续小正命令积分（§16）。
- **不能引用不带门槛的受控成功数字**：门槛 0.040 → 0.045 时合计从 28/420 掉到 18/420（§14）。
  §14 里「只有 K=2 seed0 一臂在 0.030–0.050 全域不变」已失效——该臂现判 `measurement_invalid`
  （§17.2）。扫描已在 37 个 strict 臂上重跑：门槛全域不变且非零的臂变成 **K=2 seed3（恒 17/20）**
  与已 INVALID 的 seed0；seed4 = 19/19/19/19/18（§17.11）。引用 §14 的合计数（28/420）也已过期；
  §17.11 的 118/740 @0.040 **同样已过期**，现行是 **132/780 @0.040**（39 strict 臂、门禁 v1.2.1，§19）。
- **不能把开环 `done_dz` 相关当因果**：n=11、单 teacher episode、in-sample，Spearman 仅 +0.327（§16）。
  §18 已把闭环 `dz_tail` 扩到 16 个有效臂（Spearman +0.946），但相关不等于因果这条边界不变。
- **不能把 120 局数据的负结果推广成「数据无用」**：该臂未做 epoch 对齐（81 → 16 epoch，§13）。
- **不能把 v1.1 口径的「flick N」读成脱手**：门禁升 v1.2.1 后 44 臂的 `flick` 从 185 降到 **23**、
  `insufficient_lift` 从 30 升到 **208**；受控成功 132 → 132 一格未动（§19）。
  A 线的失败形态是「夹住了、抬到 3.5–4.5 cm 就停」，**不是**「抬起后开爪扔方块」。
- **不能说官方线存在 over_lift**：44 个臂 `over_lift` 合计 **0**（对照 B 自研线 clip3 的 12/20）。
  B 的「teacher dz 饱和 → 过冲」在官方线上没有对应现象，官方线是同一 dz 偏置的**另一侧**（不足）。
- **不能裸引用受控成功数字**：39 个 strict 臂里只有 **4 臂**在 ±0.005 带内门槛稳健
  （`k2 seed3` 恒 17/20、`k2 seed4` 19、`k2 seed5` 1、`k8 seed0` 1），21 臂敏感、12 臂恒 0。
  引用格式必须带门槛与敏感带（B 报告 §3 的写法），例如
  「2/20（`final_rise ≥ 0.040`，±0.005 敏感带 1–6/20，全部边界局卡在 C5）」。
- **不能把 residual 臂的 20/20 当 learned 能力**：它是 `clip(a_base + 0.25·a_residual, −1, 1)` 的
  **复合 policy**（门禁已标 `composite_policy=true`、4 项 exec 约束），且因 SAC 无归一化、
  缺 `norm_input_blown_frames_frac` 而判 `measurement_invalid`（§20.1）。
- **不能说「`dz_tail` 高导致受控成功」**：`dz_tail` 是闭环内测得的**中介量**，不是可外生设置的变量；
  §18 的 +0.874/+0.946 只支持「归因与预登记判据」，不支持因果，也不构成「调大 dz 就能成功」的修复方案。
- **不能引用旧构建的留档裁定与新数字直接比较**：`gate_strict_*.json` 停在 6 个不同 `gate_build`，
  现行数字一律以 `regate_current/` 为准 —— **09-29 起该目录已是 `v1.5 / f19f61341cbe`**
  （54 份：主目录 48 + `blindfix/` 5 + `reblown/` 1，`single_build_only=true`）；
  `v1.2.1 / e4f5ec887788` 的 54 份已钉死在 `regate_v121_pinned/`（含 `PINNED_WHY.md`），
  `v1.2.1` 与 `v1.4 / b9379fdb1089` 同时**降级为历史口径**（不作废、不得当现值引用）。
  旧文件保留作改判前证据（§19、复现命令 30–35）。
- **不能把 spec 轴当引用锚**（裁定 29 / DR-D28）：`GATE_BUILD = _sha12(门禁脚本自身)` 是运行时现算的
  **内容哈希** ⇒ 判据不可能在 build 不变时改变；`GATE_SPEC_SHA` 哈希的是**散文规格文档**，
  可以在判据一字未动时被编辑（D 实测 35 分钟内移动 4 次：`132fceb89f68` → `154b3636056f` →
  `a1a8f38e7893` → `c7fadabe8e3c`）。所以权威口径的固定写法是 **`v1.5 / f19f61341cbe`（不带 spec 值）**；
  A 侧工具一律只锚 build 轴（`a_gate_build_drift_check.py` 已把两轴拆开：`BUILD_AXIS_MATCHES_*` 判 PASS/FAIL、
  `SPEC_AXIS` 只回显 `observation_only`）。
- **不能把 A 表的 `VALID_probe_exonerated` 计数与 B 表的 `probe_exonerated` 计数直接相比**（裁定 24⑤）：
  两者**不是同一概念**，长期是 **1 对 2** —— A 的标签语义是「原判 invalid 被 裁定 10 探针救回」，
  **只**对应 `probe_kind=clip_at_train_absmax`；B 的 `ic_status=probe_exonerated` 含两条通道。
  stdfloor 走 `reblown_single_source`，在 A 表里维持 `valid`、但**另列一列**回显 `probe_kind`。
  两表「被豁免臂数」**必然差 1，属设计差异不是缺陷**；对账一律**按 `probe_kind` 分组比**
  （判据 = `a_migration_gate_preflight.py` 的 B8 + P7）。
- **不能把 `cosign_build_matches=null` 读成「待复签」**（裁定 25 护栏① 的三值语义）：
  `True` = 会签已锚在 live build；`False` = 会签锚在旧 build、待 D 复签换块（按 DR-008 决定 7 **不拒判**）；
  `null` = **该通道根本不要求 D 会签**（`reblown_single_source`；门禁只在 裁定 10 的 clip 通道里产出这个字段）。
  混为一谈会让桶永远清不空，实质等于把 裁定 13 的豁免偷偷降级（= 裁定 24① 判为「退步」的那件事）。
  详见 `docs/a_handoff_to_b_pending_bucket_tristate_20260929.md`。
- **不能引用不带 `probe_kind` 与 `cosign_build_matches` 的免罪臂数字**（裁定 27：会签锚在哪个 build 上是
  **可核事实**，必须随数字一起走）。A 表已把这两项落成结构化字段，不必靠散文：逐臂
  `arms[].probe_kind` / `arms[].probe_cosign_build_matches` / `arms[].probe_exoneration_citation`，
  汇总 `meta.cosign_provenance` / `meta.exoneration_reconciliation`。
- **§16 的「闭环抬起 100% 来自 bias」要改口径**：17 臂上 burst 平均贡献 0.0027 m（bias 0.0327 m），
  高分组占 13%（`k1 seed0` 有 0.0175 m 来自 burst）→ 写成「主体 87–100% 来自小正 dz 积分」（§18 结论 3）。
- **不能把「blown 数字不等」读成口径不单一来源**：§12 的这个诊断已被 §21.3 逐局否证——
  分母逐局全等、截断从未生效的 52 局上 `absmax`/`blown_frac` 逐位相等，0.0940 的差 **100% 来自 6 局轨迹分岔**。
  D 的「20 局 `max_rise` 逐位相同」是对的，但那 6 局 `max_rise` 全为 0.0，`phase_trace` 已从第 48–138 帧分岔。
  **教训：`max_rise` 是投影量，不能用它判轨迹同一性。**
- **不能用 `mean_blown_frames_frac` 反推「炸穿导致了失败」**：它度量输入越界程度，不是行为后果。
  已取证一例（§21.4，`k2 seed0 ep5011`）：48% 帧越界、输入从 93.4 截到 5.0、144 帧动作不同，
  闭环真值仍**逐位不变**（截断在 tick 156 才生效，抬起峰值在 tick 154）。
  因果必须靠截断探针的**逐臂行为差异**来证，不能靠 blown 比例。
- **不能引用 `k1 seed0 = 20/20` 当 K=1 族的能力**：补齐 6 seed 后是 **20/0/0/2/0/0，均值 3.67/20、极差 0~20**（§21.7）。
  按 B §4 的表述纪律，任何单臂数字都属挑 seed，只能报「族 × 口径」均值 + 摆幅 + n。
- **不能说 K=1 与 K=2 的「0 分」是同一种失败**：K=1 的 4 个 0/20 臂是 `raw=0`、`mean_max_rise≈1e-4 m` 的
  **整体塌缩**；K=2 的失败主要是 `raw>0` 但 `insufficient_lift`（抬到 3.5–4.5 cm 就停）。修错方向会白跑一轮。
- **不能跨口径比算力**：`(1,1,1)` 的推理次数是 `(4,4,4)` 的 4 倍，k1 的 3.67/20 与 k2 的 7.80/20 不可排序（B §5 同）。
- **不能宣布晋级条件第 1 条上调**：§8 收窄条件 4 条里，第 1 条（≥3 seed 受控 ≥ 半数）K=1 只有 1/6、K=2 只有 2/5，
  第 4 条（burst >50%）21 臂**无一达标**（最高 23.2%）→ 维持「部分满足」（§21.7）。
- **不能把「INVALID 7 → 2」读成留档数字被改了**：5 个盲臂的补测在**共有字段上逐位相同**（§21.6），
  改的只是「这份文件能不能进门禁判定」；留档原件一字节未动，补测产物在 `blindfix/` 子目录。
- **不能混用五套分母口径的「有效臂数」/「三分类」**：`gate_threshold_sensitivity_A.json` 按**主目录留档口径**
  是 **41/48 有效**（合并 `blindfix/` 是 46/48、裁定 10 免罪后 47/48）；三分类在**产物级 48 臂**上是
  **24/22/2**（免罪后 **25/22/1**）、在**互异实验 dedup 43 行**上是 **24/18/1**、在 **44 臂旧口径**上是 23/19/2。
  五套并列在 §21.10(1)，引用任何一个数都必须带口径名。
- **不能引用「受控 134 / `insufficient_lift` 219 / `flick` 23」**：这是 blindfix 合并前口径，**已作废**
  （16 局 `flick` 是门禁缺字段时走弱证据分支的产物，裁定 14）。权威合计 = **135 / 235 / 7**（全 48 产物 scope），
  可引用的 `flick` 只有 **2 局 / 920**；四个 scope 见 §21.10(3)，引用必须带 scope 名。
- **不能把 `VALID_probe_exonerated` 简写成 `valid`**，也不能不带 C 与探针路径引用免罪臂的数字（裁定 10 / §21.10(2)）。
- **不能把 INVALID 臂的失效模式标签当物理事实**：`k2 seed0_replan1` 的 4 局 `flick` 属测量无效产物，
  只能说「测量无效、能力未知」（裁定 12）。
- **不能跨族搬 blown 阈值**：A 按 ckpt 现算，train24 族 = 23.8450（与 B 的常量 23.85 一致），
  trimdone0 族 = **12.469445**。同一把 0.05 容差在不同族上不是同一把尺子，引用 blown 必须写阈值取自哪个 ckpt。
- **不能说「双峰、中间是空的」/「受控成功落在 4–9 的臂数 = 0」**（裁定 30 / DR-D29，2026-09-29 起禁用）。
  该主张在 **v1.2.1** 口径下成立（那时免罪臂 `k2 seed0`(9/20) 是 `NOT_CITABLE_measurement_invalid`、
  不在有效臂分布里），在 **v1.5 / `f19f61341cbe`** 下被**恰好 1 臂**证伪 —— 就是 裁定 10 的免罪臂本尊。
  唯一允许的写法是带**四限定**：「在 **21 个 actlog 臂**、**20k 快照**（`checkpoints/last`=020000）、
  构建 **`v1.5 / f19f61341cbe`** 下，受控成功呈**强间隙分离（gap-separated）**：低簇 0–3 共 **15** 臂、
  高簇 14–20 共 **5** 臂、中间带只有**孤立 1 臂 = 9/20**（`VALID_probe_exonerated`）；
  **空带是 4–8 与 10–13**」。**双峰结论本身不倒**，被推翻的只是「中间全空」这种写法。
  机器判据 = `scripts/a_distribution_layer_check.py`（D2/D3/D6）；详见
  `docs/a_bimodal_divergence_preregistration_20260928.md` §14 与 `docs/a_handoff_to_d_20260929.md` §3。
- **不能把「强间隙分离」搬到 48 臂全集上**：48 臂的定性是 `mixed`，不是 gap-separated ——
  `trimdone0_minmax_lr1e-5_s20k_seed0_replan1` 的受控 **4** 占住了 4–8 带（48 臂 4–9 区间 = **3** 臂）。
  分布层定性**只对写明的臂集成立**（`official_all` 48 / `measurement_valid` 47 / `actlog_subset` 21 三套并列在
  `arms_summary.json` 的 `meta.distribution_layer.arm_sets`），跨臂集挪用即为不可引用。
- **不能不带构建指纹做任何分布类陈述**（裁定 30.4）：直方图 / 区间计数 / 极差 / 族均值的 n 都是按
  `measurement_valid` 的**臂集**统计的，免罪或降级会改这个臂集（实测无效臂 **v1.2.1 = 7 → v1.5 = 1**）。
  与**计数层**区分开：逐局 verdict 计数（受控 135 / insuff 235 / flick 7 / over 0 / prov 0 / raw 377）
  **构建不变**（v1.4→v1.5 实测一格未动，裁定 28 ③）。
- **不能把 v1.2.1 的 `132/208/23/0/1/364` 与 v1.5 的 `135/235/7/0/0/377` 直接相减**（裁定 30.5）：
  v1.2.1 历史表是 `n_artifacts = **44**` 的**不同臂集**（多出的 4 臂是 blindfix / reblown 重测世代）。
  「计数层一格不动」**限定在 v1.4→v1.5（同为 48 臂）**；引历史口径必须同时报 `n_artifacts`。
- **不能把 `attribution/arms_summary_v3.json` 当现值表**：它是 **v1.2.1 / `e4f5ec887788`** 的**留档基线**
  （`migration_regression_v121_to_v15.json` 的 `baseline` 字段可核），meta 停在 v1.2.1 **是对的** ——
  刷成 v1.5 会把迁移断言的左操作数改成右操作数，使它退化成恒真判据（ADR-A-011，已提请 D 改判）。
  现值权威表 = `runs/infra/lerobot_act_env_20260928/arms_summary.json`（v1.5 / `f19f61341cbe`）。
  三个文件各是什么见 `attribution/README_BASELINE.md`。
- **不能在本仓环境就绪闸判 ALLOWED 之前声称任何新训练 / 评测复现**（裁定 29.4；
  判据 = `scripts/a_env_readiness_gate.py`，E1–E6）。0929 检修后的现场实测 = **BLOCKED**（E1–E6 全红）：
  `/root/venvs/` 下**只剩 `rlrobot`**，`lerobot_act` 与 `lerobot_eval` 两个 venv 都被抹掉；
  `lerobot` 在系统 `python3` 与 `rlrobot` 解释器里均 MISSING。缺口的准确表述**不是**
  「rlrobot 少一个 lerobot 包」（lerobot 按设计从不装在 rlrobot 里，两份 lock 均无它），
  而是「**A 的训练 / 评测环境整体需按 `scripts/install_lerobot_act_env.sh` 重建**」（B / DR-012 §1）。
  **允许**声称的仍是一切**只读后处理**结论（门禁裁定 / 48 臂汇总 / 分布层引用 / 登记册 / 账本视图自检）。
- **不能只验 `import lerobot` 成功就说环境好了**（B / DR-012 §4–§5.2）：离线候选源 `lerobot_0cf8648`
  的 HEAD 比 tag `v0.4.4` **落后 488 个 commit**、`pyproject.toml` 写 `version = "0.1.0"` ⇒ 从它装出来
  import 照样成功，而 48 臂权威表依赖的官方 ACT 入口是 **0.4.4** 的。必须验
  `lerobot.__version__ == "0.4.4"` + 官方入口能 import + `lerobot_train --help` 能跑 + 安装来源可追。
