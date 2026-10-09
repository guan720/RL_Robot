# R02 后续学习与澄清

三名独立审查员共 43 个问答，均判设计级 PASS，未发现必要性阻断。主审仍采纳非阻断澄清，修改后重新开始连续计数，不用旧哈希的通过充抵最终三轮。

1. 02、07 统一首版初期冻结 VLA 表征，以及 C 中终局的取消激活行不做 actor Q 更新；保留采样分布变化与后续消融边界。
2. 02 收紧“旧计划后果”措辞：禁止伪称新动作物理执行，并不禁止队列 MDP 使用由 C 产生的当前槽回报。
3. 02 明确持续观察订阅 Gateway 只读遥测，不排队经过 RPent 活动工具锁；增加长工具未结束／卡死时的观察验收。主审重新读取固定 Toolkit 和 API loop，核对 `sequential=True` 及 readonly 限制。
4. 02 明确 Flywheel 原导出器单 task_language 限制、双向重载和主 RL 绕过成功导出；主审读取固定 export.py 对应逻辑。
5. 09 修正类名为 EpisodeWriter，并强调全部聚合不等于全部可以进入当前 n 步 BC。
6. 补查 [RoboRSI 固定 RL 入口](https://raw.githubusercontent.com/nssmd/RoboRSI/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py)，确认为具体 `run` 的 NotImplementedError，补直链并限定判断范围。
7. 补读 [Harness VLA v4](https://arxiv.org/html/2607.08448v4) 方法及局限和 [版本记录](https://arxiv.org/abs/2607.08448)：2026-09-02 最新稿仍冻结低层 VLA，联合奖励微调仍列为未来方向；明确不混用 v1/v4 的实验增益数字。

上述变更写入正式 02、07、09 后，下一轮重新冻结六份文档。原 R02 冻结输入与独立报告不修改。
