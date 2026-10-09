# RL-Harness v4 监管审查记录（2026-09-24）

## 当前裁决

项目科学设计基线可继续使用，但工程状态只能标记为“设计交付，P0 未开始”。`implementation/` 只有说明文件，`work/` 只有说明文件；目前没有可审查的 adapter、runtime、事件回放、训练入口、模型产物或真机证据。因此不得宣称“框架已搭建”“RL 已跑通”或“真机闭环已完成”。

`tools/verify_package.py` 当前返回 `ok=false`。输出显示大量 `unexpected package file`，并有历史上游摘录的 broken/nonportable link。这是交付包身份/清单问题，不是机器人算法通过证据。实现智能体不得绕过它，也不得把修复清单校验当作 P0 学习闭环完成；应单独登记为包装修复任务。

## 对两个智能体的分工闸门

### 智能体 A：P0 接口与时间契约

先交付以下文件，再允许接入真实训练或机器人：

1. `work/project_parameters.json`：设备、模型、GPU、动作频率、相机/标定、任务 A↔B 起态；未知项保留 `null`，禁止猜填。
2. `work/p0_asset_and_interface.md`：唯一 Gateway、动作单位/坐标/夹爪语义、停止和保持回执、模型与依赖版本。
3. `implementation/` 中的 mock adapter、固定槽 runtime 和事件日志 schema。
4. 可回放的最小事件样例：request、accepted、committed、physically activated、cancel、terminal、handover。
5. 手算与自动断言：C/E/D 区间、goal/epoch 隔离、迟到结果拒绝、取消不等于物理停止、终局不伪造后继动作。

P0 的通过条件是“请求、入队、物理生效可区分且可回放”，不是 SDK 能发出一条动作。任何把 chunk 数组直接切片当 E、把建议补成 TD、或用回复时间替代物理时间的实现必须退回。

### 智能体 B：Harness、数据视图与 learner 骨架

依赖 A 的事件契约，但可用 mock 并行开发。先交付：

1. `work/harness_calibration.md`：双向、失败、遮挡、未知留出集；评分误报/漏报/未知和纠正退出规则。
2. `work/training_view_spec.md`：逐事件事实视图、BC 资格、TD 资格、撤销/重标版本；不执行建议不得伪造 TD。
3. 一个短轨迹回放器，逐项核对 reward、terminal、goal、queue target、BC mask 和 actor 仅对 E 求梯度。
4. 动态 BC 对照和 BC+RL 的最小训练入口；先用合成/回放数据证明 loss 与 target，再谈真机。
5. 双向独立评估脚本：关闭 Harness 临场动作改写，固定同一 checkpoint、调度和成功判据。

不得先堆 GPT 调用、程序生成或稠密奖励。Harness 能救场不等于 policy 学会；未执行建议只能进入监督候选池，不能借用别的动作后果训练 Q。

## 监管红线

- P0 未通过前禁止长时间真机训练、扩大自主窗口或比较算法性能。
- 不得把旧文档的五轮审查 PASS、论文分数或上游仓库 README 当成本项目实现证据。
- 不得把 EGO/CTC 讨论（`materials/07_...`）并入主线首版；它是可选监督扩展，必须在基础 BC/RL 闭环后单独消融。
- 正反任务必须共享明确的 `goal_id`；同一物理状态的 A→B 与 B→A 不能只换语言而让 Q 看不到目标。
- 每次实验必须写明：实现 commit、输入配置、运行环境、数据切分、试次数、失败/未知分母和证据路径。

## 晋级顺序

只有 A 的 P0 回放和 B 的短轨迹语义检查均通过，才进入 P1 共享 BC 冷启动；P1 通过后才校准 GPT Harness（P2）；P3 语义贯通后才做最小真机闭环和 H1。H1 必须与持续动态 BC 使用相同纠正、示范、交互预算；没有相对增益就停在诊断阶段，不扩大到 P5/P6。

## 下次监管检查点

两名智能体下次汇报必须各自提供：变更文件清单、可运行命令、回放输出、未解决风险、证据状态（未实施/已实现未验证/回放通过/真机通过）。只报“代码已写”“接口已通”“模型能推理”不构成通过。
