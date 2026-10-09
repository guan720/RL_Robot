# R09 根审再次学习

独立重新读取 [RPent 新固定提交 Toolkit](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/tools/toolkit.py) 的 execute_tool／readonly／cancel_active_and_wait，以及 [OpenETA 固定 registry](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py) 的 _invoke_tool_handler／取消结果／监听器错误分支。

RPent 的 active operation 门禁先于 readonly，取消请求等待 handler 结束；OpenETA 的 cancel 可放弃等待 daemon handler 的结果，不能证明设备已经停止。来源再次支持同一 Gateway、独立观测和实体回执的必要性；也支持两种骨架用同门槛比较，而非仅对新候选强调缺口。这里是指定文件与版本的静态事实，不推断整个仓库永久缺失这些能力。

根审检查新增候选摘要与 §8／§11、总报告和技术方案的优先级已同步，未新增科学改动。等待三份独立逐问报告后记录最终合并判断；未运行训练或真机。

## 合并结论

已完整阅读 RL、Harness、证据三份报告，各12问、均PASS、必要修订0。来源、机制和当前候选顺序相符。配置保留／替换清单、协议选型卡、实验登记表属于实施阶段对既有门槛的展开，当前不改变科学输入。主设计与队列参考的称呼已有明确条件和可推翻路径，不构成矛盾。

根审 **PASS，连续通过1轮**。本轮之后未修改九份科学文件。实测门槛继续有效，未将审查通过等同真机可靠性或净学习增益。
