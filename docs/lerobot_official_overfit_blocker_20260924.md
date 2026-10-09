# Official LeRobot ACT overfit blocker

本轮严格基于 `runs/infra/lerobot_act_lift_state_overfit/official_probe/` 检查，未训练、未覆盖已有数据、未回退到自研 MLP ACT。

## 已确认

- `lerobot==0.4.4` 导入成功：

  ```text
  0.4.4
  .../official_probe/lerobot/__init__.py
  ```

- wheel 来源为 PyPI 镜像下载的 `lerobot-0.4.4-py3-none-any.whl`；当前环境 `torch==2.4.1+cu124` 满足其声明范围。
- 官方 ACT 代码入口存在：`lerobot.policies.act.configuration_act.ACTConfig`、`lerobot.policies.act.modeling_act.ACTPolicy`。
- `lerobot` wheel 的 console entry point 声明了 `lerobot-train = lerobot.scripts.lerobot_train:main`。

## 阻塞点

已建立独立环境：`runs/infra/lerobot_official_env/`。该环境使用 `--system-site-packages`，所有新增包仅写入此目录，不修改 `/root/venvs/rlrobot`。

1. 使用隔离 target 的 shell 入口：

   ```text
   /root/venvs/rlrobot/bin/lerobot-train: No such file or directory
   ```

   原因是 `pip install --target` 只把 wheel 内容和依赖目录放进 `official_probe/`，没有把 console script 安装到 `/root/venvs/rlrobot/bin`。

2. 独立环境中的等价模块入口目前仍在导入阶段失败。已补齐 `accelerate`、`typing_inspect`、`multiprocess`、`xxhash`、`pyserial`、`orderly-set`、`cachebox`、`gymnasium` 等依赖后，当前下一个阻塞为：

   ```text
   PYTHONPATH=.../official_probe /root/venvs/rlrobot/bin/python \
     -m lerobot.scripts.lerobot_train --help
   ```

   在解析训练入口前失败：

   ```text
   `ModuleNotFoundError: No module named 'diffusers'`
   ```

3. 当前独立环境仍复用了系统 `torch==2.4.1+cu124` 和 `torchvision==0.19.1+cu124`；`lerobot==0.4.4` 声明 `torchvision>=0.21.0,<0.26.0`。直接在独立环境升级 torch/torchvision 可能下载大型 CUDA 依赖，因此尚未执行。

## 未执行事项

- 没有把 interchange 数据伪装成官方 `LeRobotDataset` 对象；
- 没有启动官方 ACT overfit；
- 没有生成官方 ACT checkpoint、loss 或 action alignment 结果；
- 没有进行完整 train split 或 20 局 learned ACT 评测。

已有 `runs/infra/lerobot_act_lift_state_overfit/` 仍是兼容交换格式，teacher replay 结果仍只能称为 teacher replay。

## 下一步所需环境动作

建立独立虚拟环境，锁定 `lerobot==0.4.4`、兼容的 `torchvision`、`accelerate` 及其完整 wheel 依赖；然后在该环境中运行：

```bash
python -m lerobot.scripts.lerobot_train --help
```

只有该入口成功加载、官方 `LeRobotDataset` 能读取单个 train episode 后，才允许开始官方 ACT 单 episode overfit。
