# R10 根审再次学习

本轮重新独立读 [RAPolicy 固定 replay buffer](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/replay_buffer.py) 的 add_realworld_demo_episode、remove_transition_ids、保存／恢复 demo state，以及 [LeRobot 固定 mixer](https://raw.githubusercontent.com/huggingface/lerobot/fbb811fca92504439792b97d216f0d00c2268382/src/lerobot/rl/data_sources/data_mixer.py) 的 sample／get_iterator。

前者在淘汰最快榜之外的成功轨迹时保留受保护接管项，逻辑索引删除也不同于删除原始自动保存文件。后者混合的是 transition，默认至少取一个 online 样本。两者不能证明纯建议能当真实后果，也不能代替自有事实日志、双向采样及完整恢复包。当前技术与研究文本已分别表达这些边界，无需修改科学输入。

本轮未安装运行。三份新独立报告完成后再给根审结论，不沿用上一轮 PASS 代替本轮判断。

本轮期间会话被中断；恢复时三名审查员均为 interrupted，报告尚未写出。已接续原三名审查员的本轮任务，没有另算一轮、复用旧轮通过或更改冻结输入。

根审已完整阅读三份独立报告，共 36 问。必要问题 0 项，三方 PASS；根复核 PASS。重点复核了真实请求与纯建议、终局监督、RAPolicy 的行为价值与独立策略能力、原生 hold 和连续队列的差别，以及长期工具调用下的观察与停止边界。

不采纳的可选编辑：§10 学习导航补 RAPolicy 链接。该节是非穷尽的原理阅读路径，正式候选优先级已在摘要、候选地图、§4.3／§9及实施门槛明确；现有报告可直接定位原文和固定源码，不影响选型或开发理解。测试产物索引、动态延迟消融等保留为实施阶段工作。没有修改九份科学输入，本轮与 R09 同版本，连续通过计数为 2。
