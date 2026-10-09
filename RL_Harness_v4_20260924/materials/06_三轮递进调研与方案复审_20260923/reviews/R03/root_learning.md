# R03 根审再学习与裁决依据

状态：三份独立报告已完整读取，根审裁决PASS；相同科学输入连续通过3轮。

## 学习对象与核对

1. 实际读取 [Spot Lease Service](https://dev.bostondynamics.com/docs/concepts/lease_service.html) 的资源、代次与序列机制。它区分命令所有权与只读传感服务，并支持资源层级；本项目仅借鉴原则，不能将这一厂商已实现机制当作通用Gateway已经具备的功能。再次核对ROS2取消状态：控制权交接仍须取得实体反馈。
2. 读取冻结 [LeRobot RTC引擎](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/rtc.py) 的生命周期、reset、`_rtc_loop`及动作返回路径。该版本已有reset epoch与合并时检查，不应重复断言功能缺失；但pause清Event不等待当前计算，processor reset仍需要本项目的读写屏障约束。源码静态观察不等于已复现竞态。
3. 读取同提交 `action_queue.py` 的 `get_with_task` 与clear：计数增加发生在出队，任务来源随动作返回，仍不证明设备生效。开发§11、接口T40/T44分别要求事件分层和在途处理器屏障。
4. 完整读取冻结 [OpenPI policy_config.py](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/policies/policy_config.py) 的模型／normalizer加载与变换链。模型参数、配置、归一化和服务精度共同决定动作；本项目部署一致性检查不能只验证权重文件存在。

以上源码均从研究中保留的固定文本静态阅读，未导入或执行第三方程序。根审对应检查了开发§11、接口§6.1–6.4与T40–45、汇报§2.3–2.5和§3.3：晚到回执不复权，软件回滚不撤销物理行为，标签撤销追踪到模型后继版本。暂未发现需要改变科学内容的遗漏；最终判断等待本轮三个独立报告。

## 三份报告复核后的裁决

根审完整读取RL10问、Harness9问、证据10问，并针对unknown跨任务问题再次实际阅读Phy固定`task.py`的状态集合、`start_action`及`reconcile_nonterminal`。同任务去重和工具终账不能被推成实体所有权释放，现稿的全局资源闭包、对账和历史补证不复权已补足这一设计边界。

再核对两个容易误导实现的判断：已有LeRobot epoch修复不代表processor并发reset已由该检查解决；部分flow标签不只是最终loss乘mask，还要验证未知位置对输入／token的影响。开发和附录明确列为待实现验收，专家文档没有以“已有框架支持”抹去这些条件。H1/H2/H3以及C可直接验收、D可选的流程在两文及六图中相符。

必要修订0项。三名审查者没有把未做实验当作已通过，也没有用历史轮次替代来源阅读；根审同意01与03共同PASS。科学内容和图示保持原哈希，没有采纳需要重置连续计数的改动。剩余工位能力和样本有效性风险继续由既定预检及实验回答。
