#!/usr/bin/env python
"""最小抓取链路 · 档 2 反向任务的脚本专家（只打开一个开关，其余全部沿用正向专家）。

为什么不复制一份状态机：反向与正向的动作语义、相位序列、抓取/搬运/下放几何完全一致，
差别只有「起点在 bin2 象限、终点在 bin1 托盘」——而这两处都由 env 的 target_xy / bin_pos 提供
（见 mg_env_reverse.ReverseGraspEnv）。所以这里只继承 + 打开 CARRY_Z_LOCK，
避免两份状态机各自漂移（那才是真正会咬人的维护债）。

CARRY_Z_LOCK 的作用与实测依据见 mg_expert.ScriptedExpert 的类注释：反向搬运朝机器人方向收臂，
「目标 z = 当前 eef z」的写法会把稳态误差积分上去（实测 +0.155 m），can 在指间转到 75° 后侧躺落盘。
锁到绝对搬运高度后 eef z 不再漂，can 全程立着。正向默认不打开，行为逐比特不变。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_expert import ScriptedExpert  # noqa: E402


class ReverseScriptedExpert(ScriptedExpert):
    """反向示范源：与正向同一套状态机，仅把搬运高度从「跟随」改成「绝对锁定」。"""

    CARRY_Z_LOCK = True
