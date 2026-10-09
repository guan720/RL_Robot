"""统一的「你是不是忘了 activate venv」检查。

为什么需要这个？本机默认激活的是 conda base（`/opt/conda/bin/python`），
而本项目的依赖（py_trees / gymnasium / robosuite / stable-baselines3 / mujoco）
装在独立 venv `/root/venvs/rlrobot` 里。在 base 下直接跑脚本，
只会看到一行 `ModuleNotFoundError`，对新手很不友好。

这个模块用 importlib.util.find_spec **只探测不导入**，所以：
  - 不会提前把 torch 拉起来（`train_reach.py` 要在 import torch 之前设 OMP_NUM_THREADS）；
  - 探测本身几乎零开销。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

VENV_PYTHON = "/root/venvs/rlrobot/bin/python"
VENV_ACTIVATE = "/root/venvs/rlrobot/bin/activate"


def missing_modules(*names: str) -> list[str]:
    """返回当前解释器里找不到的模块名。"""
    missing = []
    for name in names:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, ModuleNotFoundError, ValueError):
            missing.append(name)
    return missing


def ensure_venv(*names: str) -> None:
    """缺依赖就直接退出，并告诉你怎么修。"""
    missing = missing_modules(*names)
    if not missing:
        return

    script = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "<script>.py"
    raise SystemExit(
        "\n" + "=" * 72 + "\n"
        "[环境不对] 当前 Python 里找不到这些依赖：" + ", ".join(missing) + "\n"
        + "=" * 72 + "\n"
        f"  你正在用的解释器 : {sys.executable}\n"
        f"  本项目应该用的   : {VENV_PYTHON}\n\n"
        "两种修法，任选一种：\n\n"
        f"  1) source {VENV_ACTIVATE}\n"
        f"     python scripts/{script} ...\n\n"
        f"  2) {VENV_PYTHON} scripts/{script} ...\n\n"
        "怎么判断自己在哪个环境：看终端提示符。\n"
        "  (base)    -> conda base，跑不了本项目\n"
        "  (rlrobot) -> 对了\n\n"
        "如果 venv 不存在或被清掉了（它在容器 overlay 上，重启会丢），重建：\n"
        "  bash scripts/setup_env.sh\n"
    )
