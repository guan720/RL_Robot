# skills/

阶段 3 放这里：把「一段能用的能力」封装成带版本的技能。

约定接口：

    skill(obs) -> action          # 或者 skill.run(env) -> result
    skill.meta -> {name, version, trained_on, eval_score, config_hash}

- 一个技能内部可以是规划（MoveIt 风格）、RL 策略、或大模型调用，对上层都一样。
- 技能**代码/规则**的变更和**策略参数**的变更要分开记账，
  否则永远说不清成功率提升来自哪一边（这是 RoboRSI 分析里强调过的一条）。

现有实现：

| 文件 | 技能 | 来源 |
| --- | --- | --- |
| `reach_skills.py` | `ReachPolicySkill` / `ProportionalReachSkill` / `RandomSkill` | SB3 权重 / 人写公式 / 随机 |
| `transport_skill.py` | `TransportPolicySkill` / `ProportionalTransportSkill` | 冻结 SB3 权重 / 人写公式 |
| `layered.py` | `PhaseSkill` / `ResidualSkill` | 分层 ACT/低层技能分发 / 有界 residual 组合 |

分层策略可实现 `act_with_context(obs, context)`，其中 context 由 harness 提供，包含
`phase`、步号、方向、目标和最近一帧环境 `info`。旧技能只实现 `act(obs)` 即可继续使用。

`transport_skill.py` 的纪律：**只读 import 另一条并行工作线的环境类，不修改它们**。
并发安全靠 `env_hash`（环境参数 + 扰动档位 + ckpt 内容 sha256）：那边改环境或换权重后，
旧分数会在 `registry.publish.decide()` 的环境一致性检查上被拒绝，不会污染版本线。
冒烟 / 发布入口：`scripts/smoke_transport_skill.py`（默认只冒烟，`--publish` 显式）。
