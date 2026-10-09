# policies/

阶段 2/3 放这里：策略网络的定义与训练入口。

- 目前第一个训练脚本是 `scripts/train_reach.py`（SAC + 手写 Reach），
  等环境换成 robosuite / Genie Sim 后，把训练逻辑挪到这里，`scripts/` 只留薄壳。
- 训练与评测必须解耦：评测统一走 `eval/`，不要在训练脚本里自报成绩。
