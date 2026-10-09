# VLA 方向交叉审查：自主性与可复现边界

审查日期：2026-09-22。输入为 `root_candidates.json` 和 `real_rl_candidates.json`；只读他人文件，本报告不代替原候选证据清单。重点重新打开了 ENPIRE、PLD runtime、AutoSERL 当前代码、DSRL 原论文与真机采集程序；另检查 FARL、UniIntervene 与两个 benchmark 的类别边界。未运行机器人控制或训练，未把静态检查表述为实机复现。

总体上，现有表格已经抓住关键边界，没有发现需要把 ENPIRE、AutoSERL、DSRL 的技术路线整体推翻的问题。筛选时必须保留以下限定，不能在压缩主报告时删除。

## 1. ENPIRE：99% 的单位应补为“每子任务最多 8 次上下文重试”

**小幅但有意义的修正。** 官网“Learned Manipulation Policy”明确写 99% 为 pass@8，并说明在一次长时程 rollout 内，**每个 subtask** 最多获得 8 次基于前次失败的上下文重试。当前 JSON 写“同一 rollout 内最多 8 次”可能被理解为整段长任务共享八次预算，建议补上“每个子任务”。论文 §3 同样说明固定八次重试，前次失败可影响下次行动；这不是单次执行成功率，也不是相互独立的八次 best-of-N 采样。不能用独立采样公式从该数字反推 pass@1。[官方项目，pass@8 定义](https://research.nvidia.com/labs/gear/enpire/)，[论文 §3](https://arxiv.org/html/2606.19980v1#S3)

**现有自主性分期正确。** 第一阶段由人验收安全边界、成功判定与复位接口，论文明确有少量成功/失败演示用于奖励开发；第二阶段才使用固定接口自动开展实验与策略改进。因而适合作为可与 RoboRSI 对接的外层实验 harness 候选，却不能写成任意新任务交给机器人即可无人开始。99% 也没有直接证明设备维护、不可逆耗材补给或所有新失败均已自动处理。[论文 §2.1](https://arxiv.org/html/2606.19980v1#S2.SS1)

## 2. PLD：原论文未公开完整栈，不等于当前没有公开实现

**现有 root JSON 已正确，合并其他材料时需维持一致。** NVlabs/ENPIRE 的 PLD runtime README 明确包含从 `minimal_policy@81988f0` 迁移的真实 actor/learner，并给出 `enpire rl learner/actor --task pin_insertion` 命令。它保存了 JAX 0.6.1、TensorFlow 2.18 等隔离依赖组合。这足以否定笼统的“PLD 完全无代码”。[官方相关 runtime README](https://raw.githubusercontent.com/NVlabs/ENPIRE/main/enpire/policy/pld/runtime/README.md)

建议统一措辞：“PLD 原论文/原项目未见完整独立发布；后续官方相关 ENPIRE 仓库提供迁移真机实现，任务数据、权重与工位配置需另行准备，尚未由本调研复现。”README 要求设置外部 `RL_DATA_PATH`，目录不自带数据与模型权重。迁移代码存在不等于全部原实验均可一键复现，也不能把 ENPIRE 的完整外层自动化能力归给 PLD 算法本身。[同上，运行与资产要求](https://raw.githubusercontent.com/NVlabs/ENPIRE/main/enpire/policy/pld/runtime/README.md)

## 3. AutoSERL：少接管成立，免值守尚不成立；奖励替换要改两层

**现有保守评级合适，新增一条影响工程接入的发现。** `plug_insert/config.py` 的真实环境使用 `SpacemouseActionRewardClassifierWrapper`。其 `step` 将奖励设为左键状态。更关键的是，外层 `auto_intervention_wrapper.step` 也重新读取 SpaceMouse，并再次执行 `rew = self.left`；因此未来接入 Robometer 等自动奖励时，单纯替换内层 wrapper 仍会被外层人工奖励覆盖。应该单独审查完整 wrapper 链。[任务配置](https://raw.githubusercontent.com/autoserl/AutoSERL/main/examples/experiments/plug_insert/config.py)，[两层 wrapper 实现](https://raw.githubusercontent.com/autoserl/AutoSERL/main/serl_robot_infra/franka_env/envs/wrappers.py)

人工复位的措辞也应具体：普通回合有机器人自动退回动作，不能说“每轮所有复位均人工”；但 F1 触发的异常重新抓取分支会等待终端输入，并要求人把物体放回夹取位置，因此没有消除现场异常处理。配置还含作者绝对演示文件路径、手工恢复索引 35/47 与距离阈值，当前 `RANDOM_RESET=False`。[复位与重抓取代码](https://raw.githubusercontent.com/autoserl/AutoSERL/main/examples/experiments/plug_insert/wrapper.py)，[配置](https://raw.githubusercontent.com/autoserl/AutoSERL/main/examples/experiments/plug_insert/config.py)

**当前发布代码有可定位的静态故障风险。** 直接请求当前 raw 文件得到的约 477 行：恢复切片的上界表达式为 `self.intervened_slide_idx_buffer[self.intervened_slide_idx] + 1`；约 554 行把该字典值初始化为列表，其他分支向列表追加索引。若进入此恢复分支且值仍为列表，Python 的 list + int 会抛出 TypeError。故障是路径条件性的，不宜夸大为全部训练均无法运行；但这是实际需要先审计的发布质量缺口。[恢复 wrapper 原始源码](https://raw.githubusercontent.com/autoserl/AutoSERL/main/serl_robot_infra/franka_env/envs/wrappers.py)

代码来源说明：web 的 raw 页面索引返回与直接 HTTP 请求不一致，`find recover_point` 曾未找到但直接请求能够看到该类；以上恢复分支定位以直接下载的当前源码为准，行号仅作辅助，复核应搜索变量名。未执行该代码。当前 JSON 的“静态错误风险，未实机执行”措辞准确，不能改成“完整无人训练代码已验证可用”。

## 4. DSRL：更新小模型噪声策略，基础 VLA/扩散模型冻结

**现有 JSON 算法分类正确。** 论文明确通过改变生成初始噪声分布调整动作，只需去噪前向调用，无需更新基础模型权重。学习的是噪声空间 actor/critic；它不是 VLA 全参数/LoRA 微调，也不是物理动作上的显式残差。基础模型仍需推理，所以节省反向训练显存不等于消除 VLA 推理延迟。还应保留“接口必须允许注入噪声”；普通只返回动作的黑盒 API 不一定够用。[原论文摘要与 §4](https://arxiv.org/html/2506.15799v2)

其 π0 真机采集程序把学习器生成的噪声交给 `agent_dp.infer(..., noise=...)`，同时包含人工 1/0 标注和“复位后继续”提示及调试停点。故当前评价“轻量 RL 更新候选，需要外接奖励和复位闭环”成立，不宜因论文使用 autonomous adaptation 就划为免值守完整方案。[真实采集程序](https://raw.githubusercontent.com/nakamotoo/dsrl_pi0/main/examples/train_utils_real.py)

## 5. 其余 root 候选：关键类别边界检查

|项目|检查结果|筛选时应保留的限定|
|---|---|---|
|FARL|官方页确认线上固定 recovery 与世界模型，仅 PPO 更新 task policy；Code 仍标 coming soon|73.1% 是需干预失败减少，不是人工总工时减少；提供人工移动障碍的视频任务也不能理解成所有现场劳动消失。[官网](https://failure-aware-rl.github.io/)|
|UniIntervene|当前 `run.py` 开头明确是 Fold Towel 离线训练，不启动真机或 online RL|公开离线训练环节不能等同完整在线恢复栈；57.4% 人工动作步数相对减少，不应写成干预事件或值守工时减少。此次独立核了代码发布边界，数字分母沿用原候选论文审查。[当前入口](https://raw.githubusercontent.com/Denghaoyuan123/UniIntervene/main/run.py)|
|CRONOS|官方页明确是 simulation benchmark、受限复位预算、Code coming soon|不是“零复位”算法，更不是真机持续学习实验；WidowX 是仿真本体描述。[官网](https://embodiedai-ntu.github.io/cronos/index.html)|
|REVERSAL-BENCH|原始 arXiv 页面已重新打开|保留评测协议/研究基准分类，不列为可以替代真机 learner 的部署方案；此次未对 8 设置/5 引擎逐项复算。[论文页](https://arxiv.org/abs/2609.17745)|

SERL/HIL-SERL、ResFiT、RLT、DayDreamer、TD-MPC2 与 FLaRe 的现有条目均已区分训练/部署、人工环节和基座更新方式，本轮未对所有原始数字重复审计。特别是 FLaRe 的真机部署不能被主表压缩为真机在线 RL；ResFiT 与 RLT 不能因基础模型冻结被混同为 DSRL 噪声策略。

## 6. 自有 VLA 文件同步修正

另收到 real_rl_stacks 交叉审查后，已独立重新打开 Robometer policy-learning 的 LICENSE，确认 **MIT，Copyright 2026 Robometer**。已修改本人拥有的 `vla_candidates.json` 与 `vla_self_learning.md`：奖励主仓 LICENSE 404 的缺口只适用于 `robometer/robometer`，不能笼统延伸到 `robometer-policy-learning`。主报告汇总应使用更新文件。[已核许可证](https://raw.githubusercontent.com/robometer/robometer-policy-learning/main/LICENSE)

本轮没有修改科学家知识库或其他代理的候选文件。筛选建议仍为：外层自动实验环境优先审核 ENPIRE；基础 VLA 已可用时比较 DSRL 等轻量 learner；AutoSERL 作为少接管模块需要先修复发布问题并补齐自动奖励/异常复位；自动奖励组件不能独自证明物理闭环无人化。
