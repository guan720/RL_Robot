# R01 修正与再学习

三个独立报告均 FAIL，未计入连续通过。旧输入未修改；R02 使用修正后完整输入。

| 问题簇 | 补充学习 | 修订位置 |
|---|---|---|
| 共享正反与目标缺失 | UVFA 原论文，ConRFT／EXPO 固定 Q 输入 | 01 §5、02 B4/B5、07 §5；goal 贯通，双向共同发布 |
| DAgger／BC 术语及资格 | DAgger、HIL-SERL replay／SAC、DIDA | 01 §6/9、02 B3/B4、07；Harness 命名，持久标签和物理转移分开 |
| GPT 主观察与缓存 | GPT-6 官方接口，ENPIRE 奖励固定源码 | 01 §6/7、02 B3；多图主观察，目标化缓存及迟到结果三分流 |
| chunk 异步定义不足 | SmoothRL、ARLI v2、Thinking While Moving | 06；C/E/D 与请求／提交／激活，队列增广 TD；不冒充原论文实现 |
| terminal 特判潜在偏差 | 独立构造随机终局反例，重读并发 Bellman | 撤回按未来终局挑前驱 target，统一实际请求定义；原结果未知不补造动作 |
| RPent 遗漏 | Harness VLA 论文，官方架构／Flywheel／真机文档及固定源码 | 09，01 §10.2、02 §1.3；提升首选骨架，列人工依赖和迁移缺口 |

主代理另做有限状态例子：显式枚举 48 组起始状态／承诺／新请求／时域，与队列 Bellman 递推比较，最大数值差约 5.6e-16。见 [结果](../../evidence/queue_bellman_example.json) 和 [脚本](../../tools/check_queue_bellman_example.py)。此项只校验给定玩具环境的数学定义，不验证机器人代码、模型收敛或 GPT。

RPent 固定 SHA `eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1`；根主代理另读双 Franka 固定指令代码、Flywheel 成功导出文档、operator verdict/reset 文档，确认不是可以直接去人的默认 RL 闭环。

R01 修正阶段中的讨论不是额外的通过轮次；真正的下一轮必须使用冻结 R02 输入并独立复审。
