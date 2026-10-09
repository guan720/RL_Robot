# LeRobot 官方环境修复记录

环境均位于 `runs/infra/`，没有修改 `/root/venvs/rlrobot`，没有修改已有数据和 checkpoint。

## 原隔离环境

路径：`runs/infra/lerobot_official_env/`

记录版本：

```text
Python 3.11.9
torch 2.4.1+cu124
torchvision 0.19.1+cu124
CUDA runtime 12.4
CUDA available True
lerobot 0.4.4
accelerate 1.15.0
datasets 5.0.1
draccus 0.11.6
```

已补入或确认的依赖包括 `diffusers`、`accelerate`、`mypy_extensions`、`multiprocess`、`xxhash`、`pyserial`、`gymnasium`、`orderly-set`、`cachebox`、`typing_inspect`、`transformers` 和 `tokenizers`。

## 版本冲突

`lerobot==0.4.4` 声明 `torchvision>=0.21.0,<0.26.0`，原隔离环境实际为 `0.19.1+cu124`。为避免覆盖已有 RL 环境，曾建立第二个目录 `runs/infra/lerobot_official_env_torch27/`，尝试锁定：

```text
torch==2.7.1
torchvision==0.22.1
cu126 wheels
```

该安装需要下载约 571MB 的 cuDNN wheel，下载至约 304MB 时因耗时过长停止；没有改变原环境，也没有产生可用的新 torch 环境。

## 当前入口验证结果

运行：

```bash
runs/infra/lerobot_official_env/bin/python \
  -m lerobot.scripts.lerobot_train --help
```

当前确切阻塞为：

```text
ImportError: cannot import name 'AutoProcessor' from 'transformers'
```

此前已依次修复 `accelerate`、`typing_inspect`、`multiprocess`、`serial`、`orderly_set`、`cachebox`、`gymnasium`、`diffusers` 等导入缺口。由于 transformers/torchvision 组合仍不满足官方完整依赖，尚未执行官方 Dataset 转换、ACTPolicy 加载或任何训练。

## 结论

当前没有可复现的官方 LeRobot ACT 训练环境。不存在官方 ACT checkpoint，也没有伪造 learned 结果。下一步应使用完整独立 venv，并一次性安装 LeRobot 0.4.4 的完整依赖和匹配的 torch/torchvision CUDA wheel；待以下两条都成功后再继续：

```bash
python -m lerobot.scripts.lerobot_train --help
python -c "from lerobot.policies.act.configuration_act import ACTConfig; from lerobot.policies.act.modeling_act import ACTPolicy"
```
