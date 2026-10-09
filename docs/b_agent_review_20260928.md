# B 支线复核：A 的下一步实验计划是否成立（2026-09-28）

本文只读 A 的产物与文档，未修改 A 的任何脚本、checkpoint 或数据。
B 新增文件全部带 `b_` 前缀，产物写入 `runs/infra/b_*/`。

## 0. 一句话结论（2026-09-28 晚间第三次修订，见 §6 与 §7）

> **§7 追加的两条更正**：① clip 扫描的**受控**最优臂是 clip1.5（4/20），不是 raw 最优的
> clip3（raw 15/20 但受控仅 1/20）—— 以 `success_raw` 选臂会选错；
> ② `scripts/eval_lerobot_act_runtime.py` 的门禁字段**A 已补齐**，§5 交接面那条待办作废，
> 仍缺字段的只有 `eval_act_lift_truth.py` 与 `audit_residual_lift.py`。
> 给 A 的完整交接单见 `docs/b_handoff_to_a_20260928.md`。

**§2 的离线结论仍然成立，§0/§2.3/§2.4 的闭环数字已作废，「动作太暴烈、以小时计可解」
这个预判被证伪。**

原始判断（保留以便追溯）：A 对现状的梳理准确，但「learned ACT 0/20」不是 ACT / chunk /
观测信息的结论，而是 `scripts/train_act_lift.py` 训练循环只做了 **40 步梯度**造成的
欠拟合伪影；minibatch 之后 `success_grasp_verified` 从 0/20 升到 10/20，但全部是弹射。

**现在的结论**：那个 10/20 是在 robosuite 1.5.1（obs_dim=53、物体几何 pin 失效）下测的，
整条作废；重训钉死几何后同一策略只有 raw 3/20。更重要的是，闭环失败的主因**不是**
「动作太暴烈」——执行侧 slew cap 与 dz deadband 共 7 个臂受控成功**全部 0/20**。
真正的根因是 `(x-mean)/(std+1e-6)` 归一化对近常量维无下限保护，闭环里策略输入的
归一化幅度冲到 **20403**（训练上界 23.7），**94% 的帧**超出训练分布，
网络被炸穿后 tanh 饱和输出 ±1 抖动。把输入截到 ±3（同一 checkpoint、单变量），
raw success 3/20 → **15/20**，失效模式从「漏抓/弹射」整体转为「抓稳了但抬太高」。

详见 `docs/b_normalization_incident_20260928.md`（根因与因果证据）与
`docs/b_reproducibility_incident_20260928.md`（版本漂移与作废清单）。

## 1. 环境事实：`/root/venvs/rlrobot` 已随容器重建消失

- A 的计划默认 RL 环境仍在，只差 LeRobot 依赖。实际 `/root/venvs/` 整个目录不存在，
  base conda 里没有 robosuite / mujoco / SB3 / py_trees。
- `scripts/_venv.py` 的报错文案里已预告过这一点（「它在容器 overlay 上，重启会丢」）。
- B 已用 `bash scripts/setup_env.sh` 重建，`scripts/env_check.py` 全绿：
  渲染可用、RL 接口可用、robosuite 19 envs、torch 2.4.1+cu124 / CUDA True。
- **接线不变量复现通过**：`scripts/audit_lift_base_truth.py --episodes 20 --seed0 5000`
  → base-only `success_grasp_verified = 20/20`，`mean_max_rise = 0.07644`
  （A 记录 0.076330，差 0.14%）。证据：`runs/infra/b_env_rebuild/base_truth20.json`。
- **版本漂移（需登记）**：`setup_env.sh` 会用 `pip freeze --local` 覆写 `requirements.txt`，
  robosuite 由 pin 的 `1.5.2` 变成实装的 `1.5.1`。base-only 复现未受影响，
  但按监管 P0 必须在实验记录里写明。仓库当前**不是 git 仓库**，没有 commit 可锁。
  > **已修（2026-09-28 晚，见 §7.2）**：`setup_env.sh` 改为写 `requirements.lock.txt`，
  > 不再覆写 pin 文件；`requirements.txt` 已修回 `robosuite==1.5.2`；lock 已生成且与 pin 一致。
  > 「不是 git 仓库」这一条**仍未解决**，需用户决策（§7.4）。

### 1.1 A 报的 LeRobot 阻塞已由 A 自己解除（B 复核时点：14:52 起）

A 在 13:51 的汇报里把「官方 LeRobot ACT 环境没打通」列为当前卡点。B 复核时发现 A 已在 14:41–15:02 之间自行解除：

- `/root/venvs/lerobot_act/` 已建成，实测 `lerobot 0.4.4 | torch 2.6.0+cu124 | torchvision 0.21.0+cu124 | CUDA True`，
  满足 lerobot 声明的 `torchvision>=0.21,<0.26`；`ACTConfig` / `ACTPolicy` import OK。
  **A 计划第 1 条的两条门槛命令均已通过。**
- `scripts/install_lerobot_act_env.sh` 记录了真正的根因：09-24 那个 `--system-site-packages` 环境把
  `/opt/conda` 的 TensorFlow + jax 拖进 import 链，jax 与 numpy 版本对不上导致 transformers 惰性导入
  报成 `cannot import name 'AutoProcessor'/'PreTrainedModel'`——**看着像 transformers 装坏，其实是系统包污染**，
  与 torchvision 版本无关。另记录了 pip 走代理下大 wheel 只有 ~0.7 MB/s，而 curl/uv 有 ~40 MB/s，
  这才是 09-24 那个 571 MB cuDNN 下到 304 MB 中断的原因。
- 官方 v3.0 数据集已用官方 API 重建：`runs/infra/lerobot_act_lift_v30/{overfit_ep0,train24,val8,smoke_ep0}/`
  （`meta/stats.json` 由官方代码生成，不再手写）。
- 官方 ACT 单 episode overfit **正在跑**（`/tmp/lr_overfit.sh`，两臂 lr=1e-5 / 1e-4，
  `--policy.type=act --policy.chunk_size=4 --policy.n_action_steps=4 --steps=20000`，GPU 利用率 71%）。

因此本文 §3 对 A 计划第 1 条的裁决从「降级」修正为：**已由 A 自己执行完毕，无需重复启动**。
但 §2 的证据依然改变了它的意义——官方 ACT 现在是「与自研实现做平价校验」，
不是「rescue 一条已证明走不通的路线」。

> **归属勘误（2026-09-28 15:10，用户裁定）**：本节初稿把 LeRobot 全线误记为「C 线」。
> 正确归属是 **A = LeRobot 全线**（venv / 数据集 / 官方 ACT 训练与评测），
> **C = `harness/ledger.py` + `harness/data_bridge.py`**，
> **B = `scripts/b_*` + 门禁 + 验收规格 + 可复现性**。
> 本次勘误只涉及归属标签，**§2 的欠拟合翻案与 §4 的空转帧发现不受影响，继续有效**。

## 2. 推翻「learned ACT 0/20」的证据

### 2.1 训练循环只有 40 步梯度

`scripts/train_act_lift.py` 的训练体是

```python
for epoch in range(args.epochs):          # epochs 默认 40
    pred = model(tx)                      # tx = 全部 7128 个训练样本
    loss = ((pred - ty) ** 2).mean()
    opt.zero_grad(); loss.backward(); opt.step()
```

每个 epoch 只有一次全批量前向/反向/更新 → **整个训练只有 40 步 Adam(lr=3e-4)**。

B 用同一份已导出数据离线复现（`scripts/b_bc_underfit_probe.py`），A0 臂精确重现了 A 报告的数字：

| 臂 | 梯度步 | val MSE(全帧) | 与 A 记录对照 |
|---|---:|---:|---|
| A0 全批量（= A 的训练） | 40 | 0.025899 | A 记录 `best_val_mse = 0.0258990`，**逐位吻合** |
| A0 全批量 hist4 | 40 | 0.010780 | A 记录 `0.010779940…`，**逐位吻合** |
| A1 minibatch | 5600 | 0.006997 | — |

且 A0 的 train MSE(0.025383) ≈ val MSE(0.025899)：**是欠拟合，不是过拟合**。

### 2.2 欠拟合具体坏在哪一维

离线逐维分解（validation，task-relevant = phase ∉ {done, hold}）：

| 维度 | A0（40 步）R² | A1（5600 步）R² | A0 关键帧正确率 | A1 关键帧正确率 |
|---|---:|---:|---|---|
| dx | 0.771 | 0.980 | — | — |
| dy | **−0.367**（比常数还差） | 0.912 | — | — |
| dz | 0.572 | 0.420 | — | — |
| droll/dpitch/dyaw | teacher 恒 0，模型输出 rmse 3.4–3.7e-2 rad | 强制置 0 后 = 0 | — | — |
| grip | 0.318 | 0.997 | **teacher 开爪帧上符号正确率 30.9%** | **99.8%** |

最关键的一行：**A0 在「teacher 要求开爪」的 580 个帧上只有 30.9% 输出开爪**，
即接近阶段夹爪一直是闭合的 → 必然抓不到 → 与 A 观测到的「19/20 局 failure_phase=approach」完全一致。
换成 minibatch 后该指标升到 99.8%。

### 2.3 闭环 20 局真值评测（同一评测器、同一 pinned 题集）

B 新增 `scripts/b_train_act_lift_fixed.py`，**直接 import** A 的 `collect()` 与 `ChunkPolicy`，
数据、架构、归一化（含 `std+1e-6`）全部复用，唯一变量是优化调度。
checkpoint 字段与 baseline 一致，因此用 A 自己的 `scripts/eval_act_lift_truth.py` 评测。

| 口径 | A baseline hist1 | A baseline hist4 | **B minibatch hist1** | B minibatch hist4 | scripted base |
|---|---:|---:|---:|---:|---:|
| success_raw | 1/20 | 1/20 | **10/20** | 4/20 | 20/20 |
| grasp_verified | 3/20 | 3/20 | **12/20** | 6/20 | 20/20 |
| success_grasp_verified | 0/20 | 0/20 | **10/20** | 4/20 | 20/20 |
| mean_max_rise (m) | 0.0035 | 0.0024 | **0.2161** | 0.1307 | 0.0764 |
| failure_phase | approach 19 | approach 19 | approach 9 / descend 1 | approach 16 | — |
| **受控成功（过 flick 门禁）** | 0/20 | 0/20 | **0/20** | 0/20 | **20/20** |
| **flick_frac（成功局中）** | 1.00 | 1.00 | **1.00** | 1.00 | 0.00 |

产物：`runs/infra/b_act_lift_mb_hist{1,4}_seed0/{model_final.pt,config.json,audit_truth20.json}`、
`runs/infra/b_bc_retrain/{hist1_v2,hist4_v2,eval_mb_hist1}.log`、`runs/infra/b_bc_retrain/flick_gate.json`。

### 2.4 但 10/20 全是弹射，门禁仍未过

- 成功局的 `max_rise` 达 0.263–0.772 m（hist4 到 1.166/1.289 m）。方块初始 z≈0.83 m，
  Panda 工作空间不可能把它受控举到 2 m，只能是接触爆炸式弹射。
- 10 个成功局里 **9 局结束时 `phase_trace` 末元素是 `approach`**（方块已落回桌面、机械臂不在旁边），
  只有 seed 5002 结束在 `grasp`。base-only 20/20 结束在 `done` 且 `final_rise≈0.065`。
- 因此按监管 P0 口径，受控成功仍是 **0/20**。

### 2.5 评测器本身对 flick 是盲的（方法论缺陷）

`scripts/eval_act_lift_truth.py` 的逐局字段只有 `max_rise`，**缺 `final_rise` / `held` /
`phase_at_end` / `rise_at_success`**；而 `scripts/audit_lift_base_truth.py` 这些字段都有。
后果：任何 ACT 臂只要把方块弹起来就能刷高 `success_raw` 和 `mean_max_rise` 而不被发现。
A 的计划第 2 条（「Lift learned 能力重做，≥2 seed × 20 局」）如果沿用现有评测器，
存在把弹射当成能力达标的实际风险。

B 侧提供了不改评测脚本的事后门禁：`scripts/b_flick_check.py <audit_truth20.json> ...`
（判据：`max_rise ≤ 0.15` ∧ 局末 phase ∈ {hold,done,grasp} ∧ 若有 `final_rise` 则 ≥ 0.04）。
建议把 flick 字段直接补进 `eval_act_lift_truth.py`，让两条线共用一个门禁。

## 3. 对 A 计划五条的逐条裁决

| A 的计划 | 裁决 | 理由与修改 |
|---|---|---|
| 1. 建独立 venv 装齐 `lerobot==0.4.4` + 匹配 torch/torchvision，跑通两条门槛命令，再做官方 ACT overfit | **已由 A 自己完成，不要重复启动** | 见 §1.1：`/root/venvs/lerobot_act` 已建成、两条门槛命令已过、官方 v3.0 数据集已重建、overfit 两臂正在跑。B 的修正意见是**它的定位**：§2 证明自研 ACT 的 0/20 是训练循环伪影而非能力上限，所以官方 ACT 是平价校验，不是 rescue。overfit 通过后应按 `scripts/audit_lerobot_act_overfit.py` 的口径只声称「开环动作对齐」，闭环成功率必须另跑 20 局真值 + flick 门禁（§2.5） |
| 2. Lift learned 能力重做 + 四阶段 verifier | **提到第 1 位，但必须补 flick 口径** | 方向对。要加：① 先修训练循环（§2.1）；② 评测器补 `final_rise/held/phase_at_end/flick_frac`（§2.5）；③ 四阶段 verifier 之外再加「弹射 vs 受控」判据，否则 approach 失败率会被弹射掩盖 |
| 3. 先解释 from-scratch SAC 为何 0/20 | **保留，但优先级低于 2** | §2 给出的机制线索可直接迁移验证：SAC 训练曲线 reward 涨到 114.8 而 raw 0/5，是典型 shaped-reward exploit；且 teacher 数据里 82.5% 是空转帧（§4），任何用示范预填的臂都会被「什么都不做」主导 |
| 4. harness 独立贡献 A/B（P4） | **暂缓** | 监管 P4 本身就排在 P1–P3 之后；当前 policy 独立能力仍为 0（受控口径），A/B 没有可比较的对象 |
| 5. 五条晋级条件全满足才回 PickPlace / 视觉 / VLA / 真机 | **同意，维持** | 与 `rl_harness_supervision/supervisor_review_20260924.md` 一致 |

A 计划里**缺失**的一条：`work/decisions/` 变更记录。v4 指南要求「如需改变设计，先在
`work/decisions/` 记录问题、证据、选择、被推翻的假设」。本轮被推翻的假设是
「learned ACT 0/20 ⇒ chunk policy / 观测信息 / 分布偏移是主因」，应正式登记。
注意 `RL_Harness_v4_20260924/` 是只读的，`work/decisions/` 在其内部，需先确认写入许可。

## 4. 新发现的数据缺陷：82.5% 的训练帧是任务完成后的空转帧

`scripts/train_act_lift.py::collect()` 无论任务是否完成都跑满 `horizon=300`，
teacher 在 `done` 阶段输出全零动作。实测 train split 帧分布：

```
approach 262 | descend 219 | grasp 600 | lift 168 | hold 720 | done 5159   (共 7128)
→ done+hold 占 82.5%，dz 在 91.3% 的帧上恒为 0，droll/dpitch/dyaw 在 100% 的帧上恒为 0
```

后果：MSE 损失被「什么都不做」主导，而决定成败的 approach/descend/lift 只占约 7%。
这解释了 dz 为何是所有臂里最差的一维（R² 0.16–0.42，且带 **+0.11 ~ +0.22 的系统性正偏**，
即持续命令向上 → 正好产生弹射）。

B 的初步扫参（`runs/infra/b_bc_retrain/bc_underfit_probe_hist1_seed0.json`，统一 5600 步梯度预算）：

| 臂 | 训练帧 | dz R²(全帧 / task-relevant) | dz bias | grip R² |
|---|---:|---|---:|---:|
| A1 minibatch | 7128 | 0.158 / 0.420 | +0.111 | 0.998 |
| A2 +恒零维置 0 | 7128 | 0.158 / 0.420 | +0.111 | 0.998 |
| A3 丢弃 done 帧 | 1969 | −5.010 / 0.035 | +0.448 | 0.997 |
| A4 丢弃 + 相位加权 | 1969 | −4.899 / −0.050 | +0.467 | 0.996 |
| A5 全帧 + 相位加权 | 7128 | −0.612 / 0.261 | +0.203 | 0.998 |

结论：**naive 截断/加权在同步长预算下反而更差**（样本少 3.6 倍 → 同步数下多跑 3.6 倍 epoch → 过拟合）。
不能用一次实验下结论，需要「截断比例 × 梯度预算 × 加权上限」的小网格。
注意 `hold` 帧**不能**丢：丢掉后模型在抬起后会预测开爪（A3 全帧 grip bias −0.93），会主动扔方块。

## 5. 并行方案

v4 开发实施指南明确写「架构、数据和评估契约应先统一；确定接口后，**各模块可以并行开发**」，
且「没有GPU或硬件时仍可实现数据结构、mock驱动、队列事件回放和手算target检查」。
资源上不冲突：A800 80 GB 空闲、112 核、2 TB 内存；ACT 是小 MLP + robosuite CPU 步进，
B 侧账本/TD 是纯 Python。

### A 线（policy / ACT + LeRobot 全线，独占写权限）
- `scripts/train_act_lift.py`（修训练循环）、`scripts/eval_act_lift_truth.py`（补 flick 字段）、
  `envs/robosuite_lift.py`、`runs/infra/act_*`、`runs/infra/b_act_lift_mb_*` 的后续重训。
- 顺序建议：① 训练循环改 minibatch + 梯度预算 → ② 加连续性约束（v4 已定义
  `λ_cont·L_continuity`）或执行侧 slew limit，目标把 flick_frac 压到 0 → ③ 修 dz 正偏
  （逐维动作缩放 / 损失加权）→ ④ 空转帧配比的网格扫参 → ⑤ 受控成功稳定非零后，
  再评估是否需要官方 LeRobot 做平价校验。

其 LeRobot 支线已完成/在跑（B 不重复）：`scripts/install_lerobot_act_env.sh`、
`scripts/build_lerobot_act_dataset.py`、`scripts/audit_lerobot_act_overfit.py`、
`scripts/eval_lerobot_act_runtime.py`、官方 overfit 两臂。

### C 线（账本与训练视图，B 不重复）
- `harness/ledger.py`（append-only 事实账本，400 行）、`harness/data_bridge.py`
  （四种训练视图 + 队列增广 TD 语义，415 行）。接口 15:00 仍在变动。

### B 线（验收 / 门禁 / 可复现性，独占写权限）

C 线已经把账本和视图**写出来了，但 `grep -rn` 全仓库对 `harness.ledger` / `data_bridge`
是零引用——没有任何测试、没有任何调用方**。现有 `scripts/selfcheck_harness_contracts.py`
覆盖的是更早的 `harness/contracts.py::ReplayDriver` mock 层（6 例 PASS，
`runs/infra/harness_contract_replay.json`），**不覆盖新账本**。这正是 B 的切入点：

1. ~~**给 `ledger.py` + `data_bridge.py` 补验收测试**（最高优先）：新建
   `scripts/selfcheck_ledger_data_bridge.py`，把 v4 附录 02 §9 的六个手算例子逐条打在**新账本**上~~
   > **已被推翻（2026-09-28 晚）**：C 的账本接口仍在变动，对着移动靶写测试会两边都阻塞。
   > 改为 **B 出 implementation-agnostic 的黄金期望值规格、C 自证**：
   > 六算例已手算落地为 `docs/b_golden/async_td_golden_v1.json`（含 8 条跨例不变量），
   > 自校验 `scripts/b_selfcheck_golden_values.py` 47/47 通过。
   > `scripts/selfcheck_ledger_data_bridge.py` **暂缓**，等 C 宣布接口冻结。
2. **flick 门禁并入正式 gate**：`scripts/b_flick_check.py` 已可事后判定；
   推动 `eval_act_lift_truth.py` 补 `final_rise / held / phase_at_end / rise_at_success`
   （base 评测器已有这些字段，ACT 评测器没有，见 §2.5），让两条线共用一个口径。
3. **goal_id 贯通预检**：v4 硬约束要求 goal 真正进 actor/Q/target/replay，当前所有 Lift 实验
   都是单向、无 goal 条件。先做 T17 的 mock 版（同状态换 goal，验证 goal 真进计算图而非只查维度）。
4. **可复现性**：钉死 robosuite 版本；让 `setup_env.sh` 不再覆写 `requirements.txt`
   （改写 `requirements.lock.txt`）；venv 建到 NAS 持久路径或提供容器重建后的一键校验，
   避免 §1 那种「整条线因 `/root` 被清空而停摆 4 天」的情况重演。

### 写入边界（避免三线互踩，2026-09-28 用户裁定版）
| 线 | 独占写 | 只读 |
|---|---|---|
| A | LeRobot 全线：`scripts/*lerobot*`、`runs/infra/lerobot_*`、`/root/venvs/lerobot_act`；以及 `scripts/train_act_lift.py`、`scripts/eval_act_lift_truth.py`、`envs/robosuite_lift.py`、`runs/infra/act_*` | 其余全部 |
| C | `harness/ledger.py`、`harness/data_bridge.py` | 其余全部 |
| B | `scripts/b_*.py`、`runs/infra/b_*/`、`docs/b_*.md`、门禁与验收规格、可复现性硬化 | A/C 的实现文件 |

`scripts/selfcheck_ledger_data_bridge.py` **暂缓实现**：C 的账本接口仍在变动，
B 改为先交付 implementation-agnostic 的六算例黄金期望值表交 C 自证（见 §6 B-3）。

### 交接面（三线唯一的耦合点）
`data_bridge` 的输入契约：每局产出必须带
`request_id / chunk 起始绝对帧 / K / actual_activation_mask / 动作来源 / 策略版本 / phase /
grasp_verified / final_rise / held / terminal_kind`。

现状核对（2026-09-28）：
- `scripts/eval_act_lift_truth.py:38` 的 row 只有 `max_rise`，缺 `final_rise / held(局末) /
  phase_at_end / rise_at_success / terminal_kind`。
- ~~`scripts/eval_lerobot_act_runtime.py:187` 同样缺上述 5 个字段~~
  **已更正（2026-09-28 晚）：A 已补齐。** 该评测器现在每局输出
  `final_rise / held_at_end / terminal_kind`（`scripts/eval_lerobot_act_runtime.py:334-337`，
  字段契约在其 docstring `:23` 声明），已满足 v1.1 门禁的严格判定，**A 无需再改**。
  仍缺字段的只有两个：`scripts/eval_act_lift_truth.py:38` 与
  `scripts/audit_residual_lift.py`（residual 臂，当前 20 局 `provisional_pass` / FAIL）。
- `scripts/audit_lift_base_truth.py` 五个字段全有，是字段契约的参考实现。

字段契约与《受控成功判据 v1》见 `docs/b_controlled_success_v1_20260928.md`；
给 A 的补字段交接单见 **`docs/b_handoff_to_a_20260928.md`**（交接单 2；
原文误指「同文件 §4」，§4 讲的是空转帧配比，不是交接单）。约定好这张表后三线互不阻塞。


---

## 6. 2026-09-28 晚间追加：B-2 收尾与根因定位

§2 的离线欠拟合结论**不受本节影响，继续有效**（离线探针在 teacher 分布内评测，
输入从未越界，也不碰 robosuite）。本节推翻的是 §0/§2.3/§2.4 里的**闭环**数字，
以及「flick 可以用连续性约束解决」这个预判。

### 6.1 执行侧约束全线无效（负结果，有价值）

同一 checkpoint、同一 pinned 题集（seeds 5000–5019）、20 局：

| 约束 | raw success | 受控成功 |
|---|---|---|
| 无 | 3/20 | 0/20 |
| slew cap 0.5 / 0.25 / 0.1 | 4 / 6 / 8 | **0 / 0 / 0** |
| dz deadband 0.15 / 0.2 / 0.3 | 3 / 3 / 4 | **0 / 0 / 0** |

产物：`runs/infra/b_flick_sweep/`、`runs/infra/b_dzdeadband/`。
命令幅度不是瓶颈——因为命令本身已经是饱和的 ±1，问题在网络的**输入**。

### 6.2 排除了三种更像的解释

| 假设 | 检验 | 结果 |
|---|---|---|
| 欠拟合 | minibatch 40 → 5600 步 | `val_mse_all` 0.0259 → 0.0070，但 **dz 的 r² 反而 0.542 → 0.158**。不是欠拟合的形状 |
| 信息不足（部分可观测） | `lift` vs 非 `lift` 在**夹爪已闭合**子集上分类 | recall_lift = **1.000**（56/56），approx AUC = **0.996**。信息在观测里 |
| 样本配比 | 逐维 dz 损失权重 1 → 30；丢空转帧；hist 1 → 4 | dz r² 单调变差（+0.238 → −0.839）；丢空转帧 −5.01；hist4 −2.517 |

产物：`runs/infra/b_observability/identifiability_hist1_seed0.json`、
`runs/infra/b_bc_retrain/bc_underfit_probe_hist{1,4}_seed0.json`。

**这条对项目有直接意义**：用户之前问的「给出 ACT 用作预测的信息不足时，RL 训练往往
无法取得有效成果」——在当前 Lift + state obs 上，**不属于信息不足**。
`gripper_to_cube_pos` 在观测末 3 维，模式可辨识性 AUC 0.996。
卡点在数值/表征，不在可观测性。

### 6.3 修复后剩下的唯一缺陷：hold 段 dz 正偏 → 无界上升

输入截断到 ±3 后，逐帧取证（`runs/infra/b_normclip/clip3.json`，seed 5002）：

```
帧 0-17   dz=-1 正确下降        帧 18-27 正确高度闭爪，held=True
帧 27-299 held=True 持续 273 帧，方块全程在爪里，|dz|>0.9 的帧 = 0%（无饱和）
          held 期间 dz_cmd 均值 = +0.052 = 每控制步 +2.6mm
          rise +0.012(f30) → +0.060(f40) → +0.099(f60) → +0.128(f200) → +0.154(f299)
```

teacher 的 `LIFT_TARGET=0.05`，到 0.05 就该转入 `hold` 输出 dz=0；策略**没有停止条件**。
+0.052 的动作偏置在 260 帧上积分成 0.14m 过冲，与离线测到的 dz 正偏
（全帧 +0.111、done 帧 +0.143）量级一致。

成因不是 bug 而是**多峰目标 + 确定性回归**：teacher 的 `lift` 段 dz 恒为 +1（饱和），
`hold`/`done` 段恒为 0，两者的可观测差异只在 `cube_z` 绝对值
（hold 的触发条件是 `cube_z > z0 + 0.05`，而 z0 不在观测里）。
T2 测到 lift 的 precision 只有 0.30，边界确实薄；MSE 在歧义区输出条件均值，
lift 的 +1 把均值往上拉。**修复建议见归一化事故文档 §6，前两条在 A 线**
（std 加下限且训练时同样截断；把 teacher `lift` 段的动作饱和拆掉）。

### 6.4 门禁升到 v1.1

三处语义修正，全部有实测反例支撑（`docs/b_controlled_success_v1_20260928.md` §2.1–2.4、§7）：

1. **`phase_of()` 的 `grasp` 意思是「两指张开>1.2cm」，不是「夹住了」**——空爪（0.042）
   与夹着方块（0.022）拿同一个标签。v1 把它无条件当作局末夹持的证据，
   配合「C5 缺字段不判失败」会产生假阳性 PASS。
2. **`phase_trace` 是同名字段、两套不兼容语义**：`audit_lift_base_truth.py` 写的是
   6 元素状态机日志（含 `done`/`lift`），三个 ACT 评测器写的是 ≤300 元素逐帧
   `phase_of()`（词表只有 hold/grasp/descend/approach，**永不产出 done**）。
   v1 的 `phase_at_end or phase_trace[-1]` 兜底把两者混用了。
3. **过不了 `rise_cap` 的不都是 flick**：拆出 `over_lift`（方块全程在爪里、只是抬太高）
   与 `flick`（方块脱离夹爪）。两者指向完全不同的修复动作。
   v1 的「flick_frac = 100%」把「抓取其实成功」这一关键信息掩盖了。

后果：**residual 臂从「受控 20/20 PASS」降级为「20 局 `provisional_pass`，FAIL」**
（缺 `final_rise`/`held_at_end`；状态机的 `hold→done` 是纯计时转移，不复查抓取，
不能证明局末仍夹持）。按 §4 的交接单补 2 个字段即可恢复裁定——**这是 A 线两行代码的事**。

门禁自己现在有 4 条已知答案的回归（`docs/b_controlled_success_v1_20260928.md` §7）：
1 条防假阴性、2 条防假阳性、1 条防失效混类。

### 6.5 B-2 的裁定

**「消灭 flick 的单变量实验链」这个提法要改。** flick 不是独立缺陷，
它是输入契约违例的下游症状；输入修好之后剩下的主要是 `over_lift`，
而 `over_lift` 是训练侧 dz 正偏的确定性积分，执行侧掐不掉。

所以 B-2 的实际产出是**根因定位 + 一个 A 线可执行的修复清单**，不是「把 flick 压到 0」。
继续在推理侧调截断常数没有意义（C 非单调：1.0→2 局、1.5→8、3.0→15、4.0→7、5.0→9、10→2；
20 局里差 1~4 局在噪声内），那是优化一个 band-aid。

**下一步应该是 A 线按 §6.3 重训（std 下限 + 训练时同截断 + teacher lift 段去饱和），
B 线用 v1.1 门禁验收。** 在重训之前，任何闭环成功率数字都不可信。

---

## 7. 2026-09-28 晚间第三次修订：门禁自身硬化与 clip 结论更正

本节记录 B-1/B-3/B-4/B-5 落地后的状态，以及对前文两处结论的更正。
优先级仍是 B-1 → B-5，`selfcheck_ledger_data_bridge.py` 暂缓（见 §5 更正）。

### 7.1 B-5：T17 预检落地，并修掉「牙齿判定」自己的误报

`scripts/b_selfcheck_goal_conditioning_t17.py` 已交付：1 个参考实现 + 6 个故意写坏的实现。
结果 **T17 断言有牙**（`runs/infra/b_t17/t17_precheck.json`）：

| 实现 | 常规维度检查 | T17 | 说明 |
|---|---|---|---|
| REF_embedding | PASS | PASS | 参考实现 |
| B1_onehot_single_goal | **BLOCKED** | FAIL | 词表只有 `('lift',)`，「同状态换 goal」构造不出来 |
| B2_zero_gate | PASS | FAIL | 零门 → 前向恒 0，维度全对 |
| B3_detached_goal | PASS | FAIL | embedding 被 detach → 永远学不到 |
| B4_goal_not_wired | PASS | FAIL | concat 前丢成 0 |
| B5_goal_cols_masked | PASS | FAIL | goal 列被掩成 0，形状完全正确 |
| B6_asymmetric_wiring | PASS | FAIL | 只有 critic 吃了 goal（标量检查会漏掉） |

**误报修正**：初版把 B1 算进「常规检查会放行」的分母，而 B1 的常规检查其实是**报错**
（词表装不下第二个 goal，forward 抛 KeyError），不是放行 —— 于是 `test_has_teeth` 被判 False。
正确做法是把三类分开：`pass`（常规检查放行，只能靠 T17 抓）/ `fail`（常规检查自己报错）/
`blocked`（测试根本构造不出来，是比 fail 更强的信号）。分母只取 runnable，
blocked 走独立断言「必须被 T17 明确挡下，不得静默通过」。

**这个裁定本身也做了变异测试**（`scripts/b_selfcheck_t17_mutation.py`，6/6 通过）：
注入「参考实现其实是坏的」「存在 T17 放过的坏实现」「分母只剩 blocked 变体」「blocked 被静默放行」
四种缺陷，裁定都必须翻 False；另加未变异正对照与一个合法变化对照。
过程中发现并修掉一个**恒真断言**：`blocked_variants_cannot_silently_pass` 原先读的是与分类
同源的标志位（`v["t17_blocked"]`），永远为真 —— 与本仓已记录的
`b_selfcheck_reproducibility.py` 恒真「版本一致」检查属同一类缺陷，现已改为读独立证据。

### 7.2 B-4：可复现性门禁首次转全绿（12/12），并修掉三个门禁自身缺陷

`scripts/b_selfcheck_reproducibility.py`（`runs/infra/b_reproducibility/selfcheck.json`）：

| 缺陷 | 现象 | 修法 |
|---|---|---|
| 崩溃路径 | 误用系统 `python3`（无 robosuite）时抛 `IndexError` traceback，**没有裁定** | 新增 L0-0：环境缺失时输出可读 FAIL + 正确命令，退出码 1 |
| L0-c 恒真 | `record(..., True, ...)`，只把参考值打印出来从不比对 —— 与本次事故同类型 | 改成真比对 size/mass/geom_hash；参考值从 6~7 位小数提升到实测全精度，合法性由**独立记录**的 `geom_hash=752ff735ed145948` 保证（不是现算回填，故不构成恒真） |
| L0-h 永久红 | 4 个 53 维 checkpoint 会让它永远 FAIL；永久红的门禁等于没有门禁 | 新增作废确认清单 `configs/b_obs_dim_mismatch_ack.json`：只认精确路径、必须有 reason/acked_at，已确认的降为账内 WARN，**新失配照样 FAIL**；另有 L0-h-ack 检查清单自身是否 stale |

结果：L0-a/b/c、L1、L2、L3、L0-d/e/f/g/h、L0-h-ack **12/12 PASS**。
其中 L0-g 由「尚未生成」转 PASS（`requirements.lock.txt` 已生成，`lock=1.5.2 pin=1.5.2`）；
L0-h 报「8 个 checkpoint 兼容（含 A 的 hist4=240）+ 4 个已确认作废」。

**门禁构建指纹（新增）**：仓库不是 git repo，留档裁定无法回答「这是哪一版门禁判的」。
实测后果 —— `runs/infra/b_normclip/gate_v11.json` 里的 clip24 条目缺 `measurement_valid`/`gate_reason`，
是加入输入契约检查**之前**的 v1.1 构建产出的；用当前脚本重判会从 FAIL 翻成 **INVALID**。
因此每份裁定现在都带 `gate_build` / `gate_spec_sha256`（本脚本内容哈希，跨运行稳定），
汇总产物已用同一构建重判（`gate_all.json` 11 臂 + `gate_v12.json` 5 臂 + 敏感性 `report.json` 12 臂，
**指纹以产物内 `gate_build` 字段为准**，本文不写死哈希），
旧产物备份为 `runs/infra/b_normclip2/gate_all.prev_build.json`。

**本轮补上的根因修复**：产物之所以会停在三个不同构建上（`800e1d08a174` / `28290b9c1b25` /
`22a7d92bec0a`），不是「忘了跑门禁」，而是**没有统一的重生成入口** —— 三份产物各由一条手敲
命令产出。现已提供 `scripts/b_regate_all.py`：一键重判三组臂集合、覆盖前按
`*.build_<旧指纹>.json` 快照、逐臂输出新旧裁定 diff、最后自动跑规格 §7 回归，
diff 一个臂都没比上时**拒绝**宣称「无变化」（防空比对护栏）。
实测：`22a7d92bec0a → cd96d1cd94c0` 迁移 16 臂裁定差异 **0 处**（仅指纹变化），
留档见 `runs/infra/b_regate/report.json`。

规格 §7 那张「反例自检」表也一并变成可执行的：`scripts/b_selfcheck_gate_regression.py`
（5 用例 / 21 断言，夹具缺失按 FAIL 不按 skip，零断言时强制 `ok=False`）。
变异验证有牙：`--rise-cap 0.30` → 19/21 红；`--final-rise 0.08` → 19/21 红。

### 7.3 更正：clip 扫描的最优臂在受控口径下**不是** clip3

§6.5 用 raw success 论证「C 非单调、调截断没意义」。这个结论方向正确，但**选臂依据要改**：
raw 与受控的最优臂不是同一个（来源 `runs/infra/b_normclip2/gate_all.json`，同一 gate build；
下表数字为 v1.2 判据下的重判结果，与产物逐臂核对一致；当前构建 v1.2.1 只改
复合 policy 标注、**不改任何计数**，故下表数字仍成立，但选臂解读须加上 §8.3 的复合 policy 限制）。

| 臂 | raw | **受控** | over_lift | flick | insuff | gate |
|---|---|---|---|---|---|---|
| noclip | 3 | 0 | 2 | 1 | 0 | INVALID（输入契约违例） |
| clip1.0 | 2 | 1 | 1 | 0 | 0 | PASS |
| **clip1.5** | 8 | **4** | 2 | 2 | 0 | PASS |
| clip2.0 | 8 | 2 | 5 | 1 | 0 | PASS |
| clip3 | **15** | 1 | 12 | 1 | 1 | PASS |
| clip4.0 | 7 | 0 | 7 | 0 | 0 | FAIL |
| clip5 | 9 | 0 | 9 | 0 | 0 | FAIL |
| clip10 | 2 | 0 | 2 | 0 | 0 | FAIL |
| clip24 | 4 | 0 | 4 | 0 | 0 | INVALID（输入契约违例） |
| clip3+dzdb0.1 | 14 | 3 | 10 | 1 | 0 | PASS |
| clip3+dzdb0.2 | 14 | 1 | 12 | 1 | 0 | PASS |

与 v1.1 表的两处数字变化，都由 v1.2 拆出 `insufficient_lift`（insuff）引起：
clip3 的 flick 2→1（另一局其实是抬起不足），clip10 由「1 over_lift + 1 flick」改为「2 over_lift」。
**结论方向不变**，但任何引用这两格旧数字的下游文字都要跟着改。

三条：

1. **以 `success_raw` 选臂会选错**（clip3 raw 15 但受控只有 1；clip1.5 raw 8 而受控 4）。
   这本身就是 v1.1 门禁存在的最硬理由，也应写进任何后续实验的主指标定义。
2. clip3 的失效模式是 **over_lift 而非 flick**（12/20），与 §6.3 的 teacher dz 饱和诊断一致：
   修 `demo_scripted_lift_rs.py:99` 应当直接把 over_lift 转成受控成功。
3. dz 死区同样非单调（0.1 → 受控 3，0.2 → 受控 1），不得固化为超参。

### 7.4 仍待用户决策（B 不能自行决定）

1. **`work/decisions/` 写入位置**：v4 要求路线变更先登记，但该目录在只读交付包内。
   B 倾向在仓库根建镜像 `work/decisions/`。授权前，B 的工程扩展
   （连续性正则 / slew limit 等非 v4 既定 BC 阶段项）不落地。
2. **是否 `git init`**：监管 P0 第一项仍不满足。B 已用 `gate_build` 内容哈希做局部替代，
   但只覆盖门禁脚本，覆盖不了 A/C 的实现文件。需先定 `.gitignore` 与 90+ 个 `runs/` 目录是否纳管。

### 7.5 交接

- **给 A**：`docs/b_handoff_to_a_20260928.md`（交接单 1 归一化三项重训 / 交接单 2 补 2 个门禁字段 /
  交接单 3 T17 goal 贯通 A 侧 2 项阻塞，附 §7.3 的重判总表）。
- **给 C**：`docs/b_golden/async_td_golden_v1.json` + `docs/b_golden/README.md`（六算例黄金期望值，
  C 自证用）；T17 的 C 侧 3 项在 `runs/infra/b_t17/t17_precheck.json::to_wire_goal_for_real`
  （`harness/queue_td_learner.py:65,135` 阻塞）。

### 7.6 协变量漂移探针：三轮修度量后**退役 NN 代理**，并分离出两种机制

`runs/infra/b_covariate_shift/covariate_shift.json` 原先是首轮产物（`metric_note` 为 null、
rows 无 `raw_norm_*` 字段），而代码已改过 —— 「代码已修、产物未重跑」被误记成「产物有缺陷」。
这是与 §7.2 门禁构建指纹同源的陈旧产物问题，现已给探针也加上 `probe_build`（本轮 `a98dfce9b4e2`）。

度量修了三轮，结论是**这个代理量不该继续用**：

| 轮次 | 度量空间 | 结果 | 判定 |
|---|---|---|---|
| 1 | raw 归一化空间 | nn_median=1545 vs 标尺 4.5，OOD 99.3%，首次越界帧 2 | 被 dim 7/9/11 主导，伪影 |
| 2 | 剔除 std<1e-3 的维 | OOD 99.3%，首次越界帧 2.2，nn_median 238–620 | 改由 dim 28–38 主导，绝对下限太弱 |
| 3 | 相对下限 `std_eff=max(std, 1e-2·max\|x_train\|)` + **距离集中度自检** | 标尺集中度 0.469、闭环 0.640，**6/6 行退化** | 度量仍被少数维主导，OOD% 与首次越界帧**不得引用** |

第 3 轮新增的自检（`nn_stats` 返回前 3 维贡献的平方距离占比）是关键：它让探针**自己拒绝**
给出不可信的时序结论，而不是等人发现。`summary.ood_numbers_citable=false` 时脚本会直接打印
「不得引用」。需要说明的是，集中度 >0.5 有两种可能成因（度量伪影 **或** 真实的低维发散），
本探针无法区分二者 —— 这正是退役它的理由：一个无法自证有效性的代理量不该进入结论链。
若将来仍要量化流形距离，应改用正则化协方差的 Mahalanobis 距离或 PCA 白化，而不是逐维 std。

**唯一无条件可引用的是直接测量**（不经任何度量假设）：
平均 **93.3%** 的帧超出训练归一化上界，闭环 `|x|max = 19320`（训练上界 **23.7**）。

顺带得到一个对交接单 1 有直接影响的结论 ——  blown-up 的维分成**两种不同机制**：

| 机制 | 维 | teacher std | 闭环 \|x\| 峰值 | std 下限能修吗 |
|---|---|---|---|---|
| ① 平坦特征放大 | 9 `joint_pos_cos[2]`、11 `[4]`、7 `[0]`、38 `eef_quat[0]` | 9.7e-05 ~ 1.7e-03 | 19320 / 2125 / 1348 / 1138 | **能**（相对下限正好命中这 4 维，放大倍数降 6~103 倍） |
| ② 真实闭环发散 | 32 / 28 / 34 / 30 = `joint_acc[4/0/6/2]` | 3.8e-02 ~ 1.13（本就设定了 23.7 这个上界） | 1787 / 1314 / 1130 / 529 | **不能，也不该**——这是策略真的离开了数据分布 |

即：相对下限 `1e-2·max|x|` 只命中 4 维（60 维里的 7/9/11/38），
`joint_acc` 因为 std 本来就大而不被抬升。机制 ② 是 §6.3 那条 dz 正偏积分出
`eef_z` 从 0.83 漂到 1.44 的**下游后果**，只能靠 teacher 去饱和（§6.1(b)）
与训练时同截断（§6.1(a) 后半）来治，任何归一化改动都治不了它。
所以交接单 1 的三项修复里，**(b) 不是「成本最低的可选优化」，而是唯一针对机制 ② 的修复**。

---

## 8. 2026-09-28 深夜第四次修订：门禁 v1.2.1、一键重判、§7 可执行化、B② 探针

本轮四件事，全部在 B 的写入边界内（`scripts/b_*` / `docs/b_*` / `configs/b_*` / `runs/infra/b_*`）。

### 8.1 指纹漂移的根因修复：一键重判入口

上一轮遗留的待办是「重新盖章」。做的时候发现真正的问题不是忘了跑门禁，
而是**没有统一的重生成入口**：三份产物各由一条手敲命令产出，于是同时停在
`22a7d92bec0a` / `800e1d08a174` / `28290b9c1b25` 三个构建上，文档里引用的又是第四个值。

新增 `scripts/b_regate_all.py`：一键重判三组臂集合（`b_normclip` 5 臂、`normclip` 全 11 臂、
官方臂敏感性 12 臂），覆盖前按 `*.build_<旧指纹>.json` 快照，逐臂输出新旧裁定 diff，
最后自动跑规格 §7 回归。带一道**空比对护栏**：旧产物存在却一个臂都没匹配上时，
拒绝宣称「裁定无变化」并退出非零。

这道护栏不是空写的 —— 本轮就触发了两次真实缺陷：

| 缺陷 | 现象 | 修法 |
|---|---|---|
| 产物路径口径 | 用绝对路径调 `judge_file`，产物 `file` 字段变成 `/workspace/...`，与旧产物的 `runs/...` 全部失配 → diff 报「0 处变化」，实为**空话** | 统一 chdir 到仓库根 + 传相对路径；`relkey()` 归一化比对键；留档缺陷样本 `runs/infra/b_regate/defect_abs_paths_gate_all.json` |
| diff 摘要漏字段 | 摘要里没有 `composite_policy`，于是 v1.2.1 那次**唯一真正变化**的字段被漏报，diff 照样说「16 臂全部一致」 | 摘要补 `composite_policy` / `active_constraints` |

第二次尤其值得记：工具少报了一次我**故意做的**改动。如果当时直接引用那句「全部一致」，
v1.2.1 的效果就永远不会出现在任何产物里。

实测指纹迁移证据（对留档快照显式核验，不靠 diff 自述）：
`22a7d92bec0a → cd96d1cd94c0` 16 臂裁定差异 **0 处**；
`cd96d1cd94c0 → e4f5ec887788` 标注字段变化 **18 处**、判据字段（pass/四类计数/输入契约）变化 **0 处**。

### 8.2 规格 §7 反例自检变成可执行的

原来 §7 那张表要人肉重跑核对。现在是 `scripts/b_selfcheck_gate_regression.py`：
**8 用例 / 30 断言**，退出码即裁定。两道防恒真护栏：夹具缺失按 **FAIL** 不按 skip；
一条断言都没评上时强制 `ok=false`。

变异验证有牙（不是写完就绿）：

| 变异 | 期望 | 实测 |
|---|---|---|
| `--rise-cap 0.30` | 翻红 | 19/21，红 |
| `--final-rise 0.08` | 翻红 | 19/21，红 |
| `INPUT_CONSTRAINT_KEYS` 清空（退回 v1.2 行为） | 第 6、7 条红 | 红 |
| 白名单放宽到 `input_constraints` 全部键 | 第 8 条负对照红 | 红（`noclip` 被标成 composite，清单变 `[note, train_time_norm_absmax]`） |

顺带修掉规格里一处重复标题（`## 7. 反例自检（…）（…）`）。

### 8.3 门禁 v1.2.1：输入侧约束也计入 `composite_policy`（真实缺陷）

`composite_policy` 的用途是挡住一类具体的过度主张：某臂成绩是加了约束才拿到的，
描述对象是 `policy + 约束`，不是底模。v1.2 及之前只读 `execution_constraints`，
漏掉了「推理期对归一化输入截断」这一介入，而 B 自己的评测器正是把它写在
`input_constraints.clip_norm_input`（该文件注释里早就写明「改变的是复合 policy」——
意图有、实现漏了）。

后果是**不对称标注**：同一个介入，A 的评测器写 `execution_constraints.norm_input_clip`
会被标成复合，B 的写 `input_constraints` 就不会。实测 `runs/infra/b_normclip*/`
的 **9 个 clip 臂全部 `composite_policy=false`**，门禁那句 warn 一次都没打印过。

修正后 10/11 臂标为复合，并由此得到一条必须写进结论的话（详见
`docs/b_handoff_to_a_20260928.md` §4.1）：

> clip 扫描 11 臂里，10 个复合、剩下 1 个 `noclip` 是 INVALID。
> **既非复合、又测量有效的臂 = 0 个。**
> 所以这次扫描回答的是「加了输入截断后哪个幅度最好」，不是「base policy 有多好」；
> `clip1.5` 的「受控口径最优 4/20」是 `policy+截断` 的成绩，不得当底模能力引用。

实现上只按白名单 `INPUT_CONSTRAINT_KEYS` 取键（`input_constraints` 里混着
`train_time_norm_absmax` / `note` 等元数据，全量取非 None 会把元数据当约束 ——
上表第 4 行那条变异就是专门盯这个的）。新增输出字段 `input_constraints` / `constraint_sides`，
`active_constraints` 保持原有格式（加法变更，无下游代码消费者，已 grep 确认）。

### 8.4 B② 截断因果探针：L1 在 A 的官方臂上**不咬**（形式性重分类）

完整报告：`docs/b_truncation_probe_official_20260928.md`。工具
`scripts/b_probe_truncation_official.py`（子进程调 A 的评测器，不改它）。

单变量（只差 `--clip-norm-input 3.0`）+ 三道护栏全过：权重 sha256 逐字符相同、
基线臂 **20/20 局逐位复现** A 的参考产物、评测 venv 版本与 pin 及参考产物 `versions` 全一致。
判定规则**在跑之前**写死在脚本顶部，锚定「同一臂在阈值 ±0.005 网格上受控数已在 0→2 摆动」。

跑了两次，分别落在受控成功的两端 —— 因为第一次的基线受控是 0，`Δ受控=0`
分不清「L1 不咬」和「本来就没有可失去的」（脚本会自动标注这种**地板效应**）：

| 探针 | 臂 | 基线受控 | 截断后 | Δraw | 闭环 `max\|x\|` | 裁定 |
|---|---|---|---|---|---|---|
| PROBE-1 弱臂 | `train24_lr1e-5_actionminmax_s20k` | 0/20 | 0/20 | **−3** | 16.1 → 3.0 | `L1_bites_formal` |
| PROBE-2 强臂 | `trimdone0_minmax_k2_lr1e-5_s20k_seed4` | **19/20** | **19/20** | **0** | 9.3 → 3.0 | **`L1_no_bite`** |

PROBE-1 另有 `held_at_end` 20/20 → 17/20、`grasp_verified` 20/20 不变；
PROBE-2 的 raw / 受控 / 四类失效计数**全部零变化**，且基线第三次在全新进程里精确复现。
（PROBE-2 自动继承参考臂口径 `chunk=2/n_action=2/replan=2`，不用弱臂的 `replan=4` ——
44 个官方臂横跨 8 种口径，跨口径比较没有意义。）

四条要点：

1. 受控成功口径上咬合强度为 **0**，且 PROBE-2 不是地板效应（退化余量 19 局）
   → 增补二 §2 对 A 官方臂的重分类是**形式性**的。
2. 方向与假设**相反**：弱臂夹住输入后 raw −3、局末夹持 −3；强臂完全无感。
   两次都没有观察到任何改善 → 「L1 炸穿导致 `insufficient_lift`」不成立，成因仍指向 dz / 抬起高度。
3. 全局输入契约在 A 的臂上几乎从不触发（弱臂族 7/7 臂 `blown_frames_frac`=0.0000）。
   **L1 是 B 线的事故，不是 A 线的事故**（例外：`trimdone0_minmax_k2_lr1e-5_s20k_seed0`
   及其 `replan1` 判 `violated`，见 §8.6）。
4. **逐维越界与行为无关（新增）**：强臂逐维越界率 0.372，硬夹到 ±3 后成绩纹丝不动。
   这为 §8.5-1「暂不把逐维口径升级为 INVALID」提供了实证依据 —— 用它作废测量，
   作废掉的会是本项目目前最强的结果。

诚实边界：PROBE-2 基线 19/20，改善方向只剩 1 局余量，所以「截断没带来改善」这半句
在强臂上证据偏弱；站得住的是「截断没造成退化」。**「截断能否改善某个中等强度臂」本文没有回答。**

副产品：两个 `official_noclip.json` 是 B 侧目前**唯一**干净（非复合 ∧ `verified_ok`）
且已证明可逐局复现的 base policy 闭环基线，后续执行侧干预实验应以它们为对照，
而不是以 clip1.5 为对照。

### 8.5 量到但未定性的两个事实（提交 D 裁决，B 不自行改判据）

1. **全局 0% 越界 与 逐维 22~98% 越界 并存**（A 的 7 个官方臂）。门禁现在只强制全局口径，
   所以这批臂拿 `verified_ok`。23.85 是训练期所有维度的全局最大值，是很松的尺子。
   建议：先不改判据，改为并列输出两个口径的数值，攒够证据再议是否升级为 INVALID 条件。
2. **动作侧饱和率 0.93~1.00**（7 臂里 6 臂 >0.99，`Σclip_events/Σsteps`）。
   `[-1,1]` 是 robosuite 动作空间固有边界，不算额外约束，故 v1.2.1 的 `composite_policy`
   **不该**因此翻 true；但每帧都触发说明策略在持续命令越界动作（`max_preclip_abs_action≈1.19`）。
   建议作为 v1.2.2 的信息性字段 + warn，不改 `gate_pass`。

### 8.6 B③：44 个官方臂全量重判与重分类（本轮最大的一块新证据）

完整报告：`docs/b_official_arms_reclassification_20260928.md`。工具
`scripts/b_official_arms_reclassification.py`，产物 `runs/infra/b_official_arms/reclassification.json`。

动因：监管 增补二 §2 定了「blowup 字段已记录且 <0.05 + 过官方重判」才可作为率证据，
但仓库里**没有**任何一份覆盖全部官方臂、且带当前构建指纹的裁定产物 ——
A 目录下那 43 份 `gate_*.json` 横跨至少 5 个不同 `gate_build`，没有一份是现行的。
所以「哪些数字现在可以引用」此前无法机械回答。本轮把 44 份官方产物全部重判了。

| 结论 | 数字 |
|---|---|
| 可引用性三分类 | 可引用（须附敏感带）**22** / 测量有效但受控为 0 **15** / **测量无效 7** |
| 输入契约 | `verified_ok` 37、`unverified` 5、`violated` **2** |
| 有受控成功的臂 | 23 / 44，其中 **21 个阈值敏感** |
| 重规划口径 | **8 种** `(chunk, n_action, replan)` 组合，跨口径不可比 |
| 同族跨 seed 摆幅 | 最大 **20 局**（k1 族 seed0=20 / seed1=0） |

三条必须写进发布说明的重分类结论：

1. **改判 1 引用的那个臂测量无效。** `trimdone0_minmax_k2_lr1e-5_s20k_seed0`（及其 `replan1`）
   输入契约 `violated` → 它的 9/20 **不满足**增补二 §2 的生效条件，不得作为率证据引用。
2. **但仓库里已经有了过门禁的强结果**：同族 `seed4` = 受控 **19/20**（阈值稳定）、
   `seed3` = **17/20**（稳定）、`k1 seed0` = **20/20**（敏感带 20→19）。
   全部 `verified_ok`、非复合。这是本项目第一次有过门禁的高受控成功。
   配合 §8.4 的探针结论（L1 在强臂上零咬合），**回流点的三个条件已齐备**，
   B 建议 D 重议改判 1，但依据要换成 k2/k1 族。
3. **可引用的单位是「配置族 × 口径」，不是单个臂。** 族均值与最好单臂差 2.4 倍
   （`trimdone0_minmax_k2` 族均值 7.8/20 vs seed4 的 19/20）。
   任何「某臂 N/20」的单独引用都属挑 seed。

本轮工具自身也犯过一次同类错误并已修正：族均值第一版把「测量有效但受控为 0」的臂
排除在分母外，导致 k1 族报成 20.0/20（只算 seed0）；算上 seed1=0 才是真实的 10.0/20。
**排除零值臂会系统性高估** —— 这条已写进脚本注释与产物的 `citation_unit_note`。

**与 A 的独立重判交叉核验：44/44 臂零差异。** A 线同一时间用
`scripts/a_regate_gate_current.py` 把同样 44 臂重判到当前构建
（`runs/infra/lerobot_act_env_20260928/regate_current/` + `regate_diff_current.json`），
两条产物互不知情、各自生成，但都 `import` B 的 `judge_file` 而不重实现判据。
逐格比对（5 类失效计数 + `raw_success` + `measurement_valid` + `gate_pass`）：**0 处差异**，
`gate_build` / `spec_sha` / `rise_cap` / `final_rise_min` 全部相同。
这是本轮最干净的一条可复现性证据：同一判据同一构建，两条独立路径给出完全相同的裁定 ——
说明分歧只可能来自**构建漂移**，不可能来自实现分歧。

A 侧还量出了漂移的实际代价：44 臂里 **35 臂的失效模式计数在旧构建下是错的**
（`n_counts_changed=35`），而 `gate_pass` 一个都没翻（`n_verdict_changed=0`）。
即陈旧裁定不会让该红的臂变绿，但会让 **80% 的臂**报出错误的
`flick`/`over_lift`/`insufficient_lift` 分布 —— 而失效模式分布正是决定「下一步修哪个旋钮」的依据。
这比「指纹不一致」这种形式问题严重得多。

据此，§8.6 原来那个治理项（43 份历史裁定与现行裁定并存）**已由 A 自行解决**
（A 遵守了「不覆盖、不移动、不删除旧裁定」）。B 未触碰 A 的写入范围。
剩下只需 D 确认分工：逐臂现行裁定与新旧 diff 以 A 的 `regate_current/` 为准；
**可引用性判定与族 × 口径汇总以 B 的 `reclassification.json` 为准**（A 侧产物没有这两层）；
那 43 份旧 `gate_*.json` 一律视为历史留档，禁止再引用为现行裁定。
（另更正：旧构建数是 **6 个**而非 B 初稿写的「至少 5 个」，以 A 的 `n_old_builds` 枚举为准。）

### 8.7 待决策清单（更新 §7.4；前两项仍未决）

| # | 事项 | 归属 | 状态 |
|---|---|---|---|
| 1 | `work/decisions/` 写入位置（v4 要求路线变更登记，但该目录在只读交付包内） | 用户 | **未决**，B 的工程扩展（连续性正则 / slew limit）在此授权前不落地 |
| 2 | 是否 `git init`（监管 P0 第一项；`gate_build` 只覆盖门禁脚本，覆盖不了 A/C 的实现文件） | 用户 | **未决**，需先定 `.gitignore` 与 90+ 个 `runs/` 目录是否纳管 |
| 3 | C5=0.04 比 robosuite 等效阈（≈0.0085）严约 4.7 倍，保留还是按 `object_geom` 缩放 | D | 已提交，B 不自行改 |
| 4 | 逐维输入契约是否进门禁（§8.5-1） | D | **本轮新增** |
| 5 | 动作侧饱和率是否标注为 v1.2.2 warn（§8.5-2） | D | **本轮新增** |
| 6 | 改判 1 是否上调：依据须从 `trimdone0 k2 seed0`（已判测量无效）换成 k2/k1 族，且只能报族均值 + seed 摆幅（§8.6） | D | **本轮新增**，回流点三条件已齐备 |
| 7 | 现行裁定分工确认：逐臂裁定/新旧 diff 用 A 的 `regate_current/`，可引用性与族汇总用 B 的 `reclassification.json`（两者已交叉核验 44/44 零差异）；43 份旧 `gate_*.json`（跨 **6** 个构建）降为历史留档（§8.6） | D + A | **本轮新增**，数字无冲突，只需确认分工 |

---

## 9. 2026-09-28 深夜第五次修订：门禁 v1.3、版控落地、insuff 主靶量化、teacher 锚点预登记

本节是 D 派的 B-1…B-7 的执行结果。指纹：**门禁 v1.3 / `gate_build=4f20b3ec9130` /
`spec=c9303525112a`**；**git 首次提交 `0137b33ab1a490f590d97305fd0619de270b213a`（228 文件）**。

### 9.1 归属更正已落地（§1.1 标题与 §5 三线表）

用户指出的两处归属错误已改：A = **LeRobot 全线**（venv / 数据集 / 官方 ACT 训练与评测）、
C = `harness/ledger.py` + `harness/data_bridge.py`（+ 新增 `harness/queue_td_learner.py`）、
B = `scripts/b_*` + 门禁 + 验收规格 + 可复现性。**§2 的欠拟合翻案与 §4 的空转帧发现不受此更正影响，继续有效。**

同时更正 §5「B 线」段里一句已过期的话：

> ~~C 线已经把账本和视图写出来了，但 `grep -rn` 全仓库对 `harness.ledger` / `data_bridge` 是零引用——没有任何测试、没有任何调用方~~
> **已过期（2026-09-28 深夜）**：C 现在有 `scripts/c_selfcheck_golden_conformance.py`、
> `scripts/c_selfcheck_verdict_identity.py`、`scripts/c_run_all_selfchecks.sh`、
> `docs/c_golden_conformance_20260928.md`、`registry/verdict_identity.py`，并新增了
> `harness/queue_td_learner.py`（队列增广 TD 学习器）。「零引用零测试」的判断在当时成立，现在不成立。
> B 的黄金值规格已被 C 用于自证（对账通过），T17 的 C 侧 3 项已交接（`docs/b_handoff_to_c_20260928.md`）。

### 9.2 B-1：版控落地（监管 P0 第一项，此前事实上不满足）

- `.gitignore` 按 **DR-003**（`work/decisions/decisions_20260928_B.md`，8 条决定）重写：
  `runs/`（37 GB / 22596 文件）、`RL_Harness_v4_20260924/`、`registry/*/`、二进制/媒体/大产物全部排除；
  `work/` **纳管**（它是 DR-001 指定的唯一登记处，必须受版控才能追溯「谁在何时改口径」）。
- **单写者纪律**：只有 B 执行 git 写操作，A/C 只读 `git log` / `git status`。禁用命令清单（`git clean -fd`、
  `git reset --hard`、`git checkout -- .`、`git restore .` 等）写进 DR-003，与 AGENTS.md 禁 `rm` 同源。
- **带牙护栏**：pre-commit 体积闸 `scripts/b_git_size_guard.py`，拒绝新增 > 2 MB 的 tracked 文件
  （扩展名规则挡不住「大 JSON」，git 无法按体积忽略）。自检 7/7，另做了一次 3 MB 真实拒绝测试。
- 解锁：裁定 JSON 现在带 `git_commit`（门禁 v1.3 §2.15）。**缺 `git_commit` 的旧裁定不因此作废**
  —— 只有缺 `blown_metric_impl` 指纹才拒判（DR-006）。
- 附带事实：`/workspace/mnt/sppro/yhzhang91/.git` 是个**空目录**（不是 repo），无害，已记录。

### 9.3 B-2：门禁 v1.3（D 的裁定 1/2/3 + 监管 §12 分派）

| 裁定 | 落地 | 实测附带损伤 |
|---|---|---|
| 1 phase 词表矛盾 → `INVALID`（不再静默判 `flick`） | 行级 `unjudged` + 文件级 `INVALID`；规格 §2.9 | 48 臂官方集 **0 例**矛盾（`phase_vocab_mismatch_arms: []`） |
| 2 `not_applicable` 必须走**带牙**声明路径 | 规格 / 训练范围 / 闭环三项任一缺 → `INVALID`；§2.10 | — |
| 3 `probe_exonerated` 只接受带内 + sha256 可校验证据 | 带外一律 `out_of_band_refused`；`scope=arm` 要求 impl 已知（防连带洗白）；§2.11 | 实测免罪 **1** 臂，`in_disputed_band` 1 |
| §12 `blown_metric_impl` 指纹 | `KNOWN_BLOWN_IMPLS=("52eae25ee2d7",)` + 祖父登记簿 `configs/b_blown_impl_grandfathered.json`（**69 条**，cutoff `2026-09-28T21:27:24+08:00`，`scripts/b_blown_impl_registry.py --verify` **69/69**）；§2.12 | `missing_legacy_grandfathered` **38** / `known` **10** / `missing_blowup` **0** |

另加：`threshold_provenance` 回显（ADR-A-005 #4 / DR-D10，修掉「|x|>**0.0**」的打印缺陷）、
`git_commit` 戳、`measurement_invalid_reasons`、CLI 缺字段告警。规格 §2.13–§2.15。

**反例自检**：`scripts/b_selfcheck_gate_regression.py` **21 用例 / 85 断言全过**
（合成夹具在 `runs/infra/b_gate_regression/fixtures/`）；新增 `scripts/b_selfcheck_gate_mutation.py`
**5/5 变异全被抓到**（防「门禁自检定然是绿的」这一类恒真）。

### 9.4 B-3：`insufficient_lift` 是当前**主靶**，现已量化到「差多少」

此前只有计数，无法回答「该修策略还是该由 D 重定 C5」（ADR-A-005 #3）。v1.3 起每份产物带
`insuff_diagnostic`，重分类里池化：

**235 局 / 34 臂**，门槛 `C5 = 0.04`：

| 量 | 值 |
|---|---|
| `final_rise` 中位数 | **0.0236 m** |
| p10 / p90 | 0.01024 / 0.0367 |
| min / max | 0.0087 / 0.0399 |
| 与门槛的中位差 | **0.0164 m** |
| 最好一局只差 | **0.0001 m** |
| 落在门槛下方 0.005 m 内 | **41 局（17.4%）** |
| 落在门槛下方 0.010 m 内 | 75 局（31.9%） |

**C5 杠杆表**（改阈值能翻多少局，`insuff_pooled.c5_scenario_impact`）：

| C5 | 依据 | 翻成受控成功 | 占 235 局 |
|---|---|---|---|
| **0.04**（现行） | `0.92 ×` 方块全高 `0.04341` | 0 | 0% |
| 0.035 | 现行 −0.005（敏感带下沿） | 41 | 17.4% |
| 0.03 | `0.69 ×` 全高 | 75 | 31.9% |
| 0.0217 | `0.50 ×` 全高（半高） | 134 | 57.0% |
| 0.0085 | robosuite `_check_success` 换算到相对初始高度口径的等效阈（规格 §2.7 实测） | **235** | **100%** |

**这是当前最大的单一杠杆**：17.4% 的 insuff 局只差不到 5 mm。B 的立场不变 ——
`C5 = 0.04` 是几何锚，**改它属监管裁决范围，B 不自行改**；但 D 现在有了做这个裁决所需的全部数字。
注意 0.0085 那一行不是建议值，它只是说明「与环境自带成功阈对齐」会把 235 局全部翻过来，
即**现行门槛比环境严约 4.7 倍**这件事的量化后果。

### 9.5 B-5：48 臂 v1.3 重分类 + 历史归档，并修掉一个**分类缺陷造成的假信号**

- **48 臂重分类**（`runs/infra/b_official_arms/reclassification.json`，v1.3 / `4f20b3ec9130` / `git 0137b33`）：
  来源 official 42 / blindfix 5 / reblown 1；`ic_status` verified_ok **45** / violated **2** /
  probe_exonerated **1**；可引用三分类 **24 / 22 / 2**；`arms_with_controlled_success` **25**、
  `threshold_sensitive` **24**（δ=0.005）；`cadence_unresolved` **0**。
  族均值：`k1 = 3.667/20 (n=6)`、`k2 = 7.8/20 (n=5)`、`stdfloor = 7.75/20 (n=4)`
  （显示层 `%.1f` 把 7.75 印成 7.8，JSON 里是精确值）。
  顺带修掉一个**真实缺陷**：重复世代未去重（`dedup_generations`，实测 5 对），现已 `n_superseded=6`。
  v1.2.1 快照保留为 `reclassification.build_e4f5ec887788.json`，不覆盖。
- **历史归档**（`scripts/b_archive_historical_rulings.py` → `runs/infra/b_official_arms/historical_archive.json`）：
  63 份文件 / 114 条臂级记录，一律 `citable=false`（监管 改判 7：唯一可采信的是当前构建）。
- **修掉 B 自己报的「8 个孤臂」假信号**：首版把 8 条记录一律判 `C_orphan_no_counterpart`，
  看起来像 8 个漏判。逐条核查后是**分类缺陷**，补两条规则后真孤臂 = **0**：
  - **B2 `superseded_name_variant`（4 条 / 2 臂）**：`train24_lr1e-4_actionminmax_s20k`、
    `train24_lr1e-5_actionminmax_s40k` —— 当前权威里的同臂叫 `..._gatefields`（blindfix 补测改名）。
  - **D `probe_output_not_delivery_arm`（4 条）**：`clipprobe/regate_current/` 下的
    `*_clipC12p469445` / `*_clipC5p0` —— B 自己的 `--clip-norm-input` 探针产物，本来就不是交付臂。
  首版产物留档为 `historical_archive.v1_8falseOrphans.json`（不覆盖）。
  最终分布：`B_superseded_with_drift` **104** / `D` **4** / `B2` **4** / `A_superseded_no_drift` **2**，**真孤臂 0**。

### 9.6 B-4：teacher 去饱和**预登记**（DR-004，现在不动手）

正文 `docs/b_teacher_desaturation_prereg_20260928.md`，仪器 `scripts/b_teacher_dz_audit.py`。三条要点：

1. **`RISE_CAP = 0.15` 从来没有可复现规则**（源码只写「取约 2 倍」）。实测 `2 × 0.07633 = 0.15266`：
   `ceil_to_0.01` → **0.16 ≠ 0.15**，`round_to_0.05` → 0.15，`floor_to_0.01` → **0.15**。
   采纳 `floor_to_0.01(2 × mean_max_rise)`（cap 是上限，floor 是保守方向），并用判据 **A0**
   钉死「规则套旧数据必须精确复现任值 0.15」，防悄悄换锚。
   `FINAL_RISE_MIN = 0.04` **不是** teacher 锚（几何锚 `0.92 × 0.04341`），**不在重算范围**。
2. **去饱和是幅度修复，不是可辨识性修复**：T2 实测 `recall_lift = 1.000` 但 `precision_lift = 0.30`，
   `hold` 的触发条件 `cube_z > z0 + 0.05` 里的 `z0` 不在观测里 → 策略没有停止条件。
   把 `dz` 从 `+1` 降到 `+0.2` 只缩小条件均值幅度，不恢复停止条件。
3. **新增 B3 漂移有界性探针**（本次最重要的补充）：命令幅度缩 5× 后，「不停」的策略尾速从
   `1.9e-4` 降到约 `4e-5 m/step`，300 步内可能只漂 `0.05 → 0.06`，**稳稳落在 `RISE_CAP=0.15` 以内**
   → 现有 C3 会判 `controlled_success`。这不是门禁 bug，是判据对「有界」的定义不完整。
   B3 要求同一冻结 ckpt 跑 `--horizon 300` 与 `600`：`median[max_rise(600) − max_rise(300)] ≤ 0.010 m`
   且尾 100 步速率 `≤ 5e-5 m/step`。旧行为外推漂移 `≈ +0.06 m` → **FAIL 6×**，两边都有区分力。
   两个评测器（`scripts/eval_act_lift_truth.py:29`、`scripts/eval_lerobot_act_runtime.py:219`）**都已有 `--horizon`**，零代码改动可跑。

共 15 条判据（teacher 侧 T1–T5 / 锚点侧 A0–A5 / 闭环侧 B1–B4），`not_measured` 一律不算通过。
**已锁基线**（旧 teacher，`runs/infra/b_teacher_desat/baseline_teacher_dz.json`，sha256 前 16 位 `9288e63f6a5e1ca0`）：
`dz_lift_mean = 1.000`、`sat_frac = 1.000`、`dz_hold ≡ 0`、分离度 `1.000`；
帧级口径 24 集 × 300 = **7200 帧**（文档常引的 7128 是 chunk 级 24 × 297 口径，同一批数据，不是漂移）；
base-only `20/20`、`mean_max_rise 0.07633`、`mean_final_rise 0.06365`、过冲 `mean 0.01365 / max 0.0169`、
裕度 `min(final_rise) − 0.04 = 0.0220`。
**负控制已跑**（`negative_control_old_teacher.json`，`ab874f09c2cc25b0`）：用未修改的旧 teacher 跑 check
→ `verdict=FAIL`、退出码 1，FAIL 的恰好是 T1（`sat_frac=1.0`）、T2（`mean_dz_lift=1.0`）、
A4（`mean_max_rise=0.07633` 超出预测带 `[0.052,0.072]`）三条本次应当改变的判据，其余 PASS、
B1–B4 如实标 `not_measured` → 判据非恒真非恒假。

**排序**：DR-004 现在**不生效**。放行条件是 A 的双峰预登记出 R1/R2 结论 + D/用户放行 + A 线 in-flight 评测收尾
（依据 `docs/a_bimodal_divergence_preregistration_20260928.md` §9：双峰有答案前不做 L2 修复，
否则会连做两次重置并废掉 48 臂比较集）。B 同意该排序。

### 9.7 B-7：连续性正则 / slew limit **继续停车**（DR-005）

DR-001 解锁了 B 的工程扩展，现登记为继续停车，理由从「无登记入口」变成「**证据反转**」：

1. v4 的 `λ_cont L_continuity` 出现在 **RL 的 actor loss**（`01_开发技术方案.md:253`），**不是** BC/ACT 阶段既定项；
2. 实证负结果已在手：slew cap ∈ {0.5,0.25,0.1} + dz deadband ∈ {0.15,0.2,0.3} 共 7 臂，受控成功**全 0/20**；
3. **v1.3 重判后打的不是现在的靶**：权威 `flick = 7`（其中 5 局在 2 个 INVALID 臂上 → 可引用 **2 局 / 920 局**，
   DR-D09），而主失效模式是 `insufficient_lift`（**235 局**，§9.4）。连续性正则与 slew limit 打的是 `flick`/`over_lift`。

重启条件三选一并附产物：(a) teacher 去饱和后 `over_lift` 重新成为主失效模式；
(b) `flick` 可引用局数 > 20 且集中在同一配置族；(c) 进入 RL 阶段按 v4 原文实现 actor loss 的 `λ_cont`
（那是实现既定项，不属本条扩展）。

### 9.8 DR-006：补齐悬空的前向引用

DR-003 与 D 的 DR-D10 都前向引用了「DR-006『缺指纹才拒判』」，但该编号此前不存在。
现已补登记（`work/decisions/decisions_20260928_B.md` DR-006）：新产物缺 `blown_metric_impl` 指纹 → **拒判 `INVALID`**；
祖父条款只覆盖 cutoff 之前的历史臂（69 条，`--verify` 69/69），**不覆盖新产物**。

### 9.9 自检全绿（本次会话实测）

| 自检 | 结果 |
|---|---|
| `b_selfcheck_gate_regression.py` | **21 用例 / 85 断言**全过 |
| `b_selfcheck_gate_mutation.py` | **5/5** 变异被抓 |
| `b_selfcheck_golden_values.py` | **47/47** |
| `b_selfcheck_t17_mutation.py` | **6/6**（`test_has_teeth = true`，`non_vacuous = true`） |
| `b_selfcheck_reproducibility.py` | **12/12** |
| `b_git_size_guard.py` | **7/7** + 一次 3 MB 真实拒绝 |
| `b_blown_impl_registry.py --verify` | **69/69** |
| `b_teacher_dz_audit.py` 负控制 | 退出码 **1**（预期 FAIL，见 §9.6） |

### 9.10 交给 D 的决策队列

1. **C5 裁决（最高优先，数字已齐）**：235 局 insuff、中位差 0.0164 m、17.4% 只差 <5 mm。
   选项是「维持 0.04 并把它当作 A 的训练靶」还是「重定 C5」。B 的立场：0.04 是几何锚，
   **维持**，把 §9.4 的表当成 A 的靶（差 16 mm 不是阈值问题，是能力问题）；但 17.4% 那一段
   说明「阈值微调 0.005」能立刻改变 41 局的结论，所以**任何报率都必须附敏感带**（规格 §2.7 已要求）。
2. **DR-004 的放行时点**：是否与 A 的双峰判定串联（B 建议串联，理由见 §9.6）。
3. **被否决的替代方案，供 D 复审**：裁定 1（phase 词表矛盾）如果改成「自动接受裸 `done`」，
   当时那个 residual 臂会直接给到 **20/20** 受控成功。B 选择了 `INVALID` 而不是自动接受，
   因为「词表矛盾」意味着证据分支不可信，20/20 是**用不可信证据换来的好看数字**。
   若 D 认为该臂的证据其实充分，正确路径是按裁定 3 走**带内探针免罪**（sha256 可校验），而不是放宽词表。
4. **监管 §8.7 #3–#7 的开放升级项**仍未裁决（B 不自行决定）。

---

## 10. 2026-09-28 深夜第六次修订：门禁 v1.4 —— A 移交的裁定 14 落地 + DR-007 收窄

§9 写完后 A 移交了一份新缺陷（`docs/a_handoff_to_b_gate_vocabulary_20260928.md`，22:07），
属 B 的门禁范围，当轮处理完。新指纹：**v1.4 / `gate_build=b9379fdb1089` / `spec=132fceb89f68` / `git=3615c8e`**。

### 10.1 缺陷：证据不足被解析成「判成脱手弹射」

`held_at_end` 与 `final_rise` 双缺时，C4 落到 `HOLD_PHASES_STRICT={"hold"}` 拒绝 `end_phase="grasp"`
→ `c4=False` → 一路返回**最重的失效模式 `flick`**；字段齐时走 `HOLD_PHASES_WITH_EVIDENCE={"hold","grasp"}`
接受它 → 同一局其实是 `insufficient_lift`。**同一个 `"grasp"` 标签是否算 C4 证据，取决于一个不相关字段在不在。**
讽刺的是 v1.3 已经算出了 `field_class="partial"` 与 `phase_vocab_status="absent_field"`，只是没用这个信息。
影响面：5 臂 **16 局假 `flick`**，使可引用 `flick` 只剩 **2 局 / 920 局**（0.2%）——
这恰恰是 §9.7（B-7 停车）的依据数字，也就是说**停车结论此前建立在一个含假标签的统计上**，
现在标签修好了，停车结论的依据反而更干净（真 `flick` 确实只有 2 局）。

### 10.2 v1.4 的处置

标签（`flick` / `insufficient_lift` / `over_lift`）只在证据充分时输出，否则本局改判 `unjudged`
（`unjudged_reason="evidence_missing_label_critical"`）+ `measurement_valid=False` + `gate_reason` 点名缺失字段。
原标签**不销毁**，留在 `per_episode[].evidence.label_before_abstain`。
新增 4 个裁定字段，其中 `labels_reportable` 与 A 的 `summarize_lerobot_act_arms.py`（`schema_version=2`）**故意同名**。
`provisional_pass` 通道**不动**（v1.1 有意设计的「待补测」档）；`failure` 不动。
顺带推翻 v1.1 的一条设计注释（`field_blind` 单独走 FAIL 不走 INVALID）：关键字段缺失是「没测到」，
不是「策略失败」，判 FAIL 会把测量缺口说成能力结论。

### 10.3 DR-007：B 对字面裁定做了收窄，主动申报并请 D 复核

DR-D09 的字面口径是 `field_class != "strict"` 即弃权。**B 没有按字面实现**，改成只由
`LABEL_CRITICAL_FIELDS = (final_rise, held_at_end, phase_at_end)` 触发。理由可测：

1. 三个失效模式标签**不读** `terminal_kind`（它走规格 §2.4 终局语义那条独立弃权路径）；
2. **base-only 标定产物本身就缺 `terminal_kind`** —— 实测 `runs/infra/b_env_rebuild/base_truth20.json`
   与 `runs/act_chunk_replay_20260924_k4_base_truth20.json` 的覆盖率都是 **0/20**、`field_class` 都是 `partial`。
   按字面实现，门禁会把 `RISE_CAP=0.15` 的标定基准与 20/20 参考上界判成 `INVALID`，
   连带 DR-004 的 A0–A5 全部无法执行。这正是门禁 `:741` 注释早就警告过的自伤
   （「门禁把自己的标定基准作废了」）。

**收窄不是放宽，两个方向都有牙**（`b_selfcheck_gate_mutation.py`，7/7 全被抓）：
`M6` 清空 `LABEL_CRITICAL_FIELDS`（= 静默删掉裁定 14）→ 用例 22 红；
`M7` 把 `terminal_kind` 加进去（= 按字面实现）→ 用例 **1 与 24** 红。
`M7` 的作用是把收窄理由钉成**可执行证据**而不是注释：将来谁想按裁定原文改回来，这条会立刻红给他看。
若 D 否决收窄，前置条件是 A 给 `scripts/audit_lift_base_truth.py` 补 `terminal_kind` 并重跑标定。

### 10.4 实测：A 的 12 份算例逐条对齐，48 臂零附带损伤

- partial 5 臂 `n_labels_abstained = 11 / 3 / 2 / 0 / 0`，合计 **16 局**，与 DR-D09 独立复算一致；
  `seed2` 的 `provisional_pass=1` 保留；strict 5 臂维持 `insuff 11 / 3 / 2` 与 `ctrl=1`；
  residual 两臂（裁定 8）`unjudged=20` / `ctrl=20` 无回退。
- 逐臂 v1.3→v1.4 对比：`measurement_valid` **12/12 不变**、`controlled_success + provisional_pass` **12/12 不变**，
  唯一差异是那 16 局标签迁移 → **回归违例 0**。
- 48 臂官方集 48/48 全 `strict` → 重分类逐项与 v1.3 **完全一致**（§9.5 的每个数字都没变），
  `b_regate_all.py` 报「裁定变化 **0** 处」。**A 的 §21.10 权威表不需要重算，只需更新 `gate_build`。**

### 10.5 §4.4 建议的采纳方式（与 A 的做法有一处刻意不同）

A 建议把 12 份真产物直接进回归。B 改为**合成夹具**（`label_abstain_partial.json` /
`label_strict_reportable.json` / `label_terminal_kind_only.json`，三份是同一次物理评测的三种字段可得性）。
原因：`runs/` 不纳版控（DR-003 决定 1），把真产物当夹具会让回归在容器重建后**静默失效**
（夹具缺失虽已按 FAIL 处理，但那会让回归长期红着，红久了就没人看）。
A 的 13 份真产物作为**外部验证**已在 §10.4 逐条对齐；合成夹具作为**长期回归**。
规格 §7 现在 **24 用例 / 108 断言**全绿。

### 10.6 自检全绿（v1.4，本轮实测）

| 自检 | §9.9（v1.3） | **本轮（v1.4）** |
|---|---|---|
| `b_selfcheck_gate_regression.py` | 21 用例 / 85 断言 | **24 用例 / 108 断言** |
| `b_selfcheck_gate_mutation.py` | 5/5 | **7/7** |
| `b_selfcheck_golden_values.py` | 47/47 | **47/47** |
| `b_selfcheck_t17_mutation.py` | 6/6 | **6/6** |
| `b_selfcheck_reproducibility.py` | 12/12 | **12/12** |
| `b_selfcheck_goal_conditioning_t17.py` | `test_has_teeth=true` | **同** |
| `b_blown_impl_registry.py --verify` | 69/69 | **69/69**（0 漂移 / 0 缺失） |
| `b_git_size_guard.py --selftest` | 7/7 | **7/7** |
| `b_teacher_dz_audit.py` 负控制 | 退出码 1（预期 FAIL） | **同** |

### 10.7 决策队列增量（接 §9.10）

5. **DR-007 请 D 复核**：认可或否决 B 对裁定 14 的收窄。否决的前置条件是 A 补 `terminal_kind`
   到 `scripts/audit_lift_base_truth.py` 并重跑标定 —— 在补齐之前按字面实现会立刻作废
   `RISE_CAP` 标定基准与 DR-004 的全部锚点判据。
6. **`terminal_kind` 缺失是否应触发另一条（非标签类）降级**：B 倾向在裁定里 warn
   「终局语义自检不可用」但**不**判 INVALID，等 D 定。
