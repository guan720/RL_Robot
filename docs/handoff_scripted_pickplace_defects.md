# 交接单 · `PickPlaceStateMachine` 的 28% 失败缺口 = 一个几何常量

> 2026-09-24 · 由 harness/探针侧出具，**只读**对方文件（`scripts/demo_scripted_pickplace.py`
> 一个字节都没改）。所有数字都是本机实测，产物路径附在每条证据后面。
> 背景：`docs/notes_stage3.md` §12.11-R.4（手写参照臂上限 0.719 的解剖）。

## 0. 一句话

PickPlace 手写参照臂 0.719（23/32）的那 9 个失败局，**根因只有一个**：
`CARRY_HEIGHT = 0.16` 让搬运时 can 的**底部**（≈0.863~0.882）低于目标篮 `bin2` 的**墙顶 z=0.9000**
2~3.7 cm ⇒ 每次越过近侧墙板都要靠搬运途中的摆动/超调碰运气才能过去；撞墙之后有三种不同后果，
于是在探针里表现为三类标签（D1/D2/D3）。
运行时把这一个常量抬到 **0.22**，同一批 seed 从 **23/32 → 32/32 = 1.000**，
而且中位步数从 189 降到 **160**（比基线的成功局还快）。

## 1. 证据链（每条都可复算）

**① 几何：墙顶比搬运高度高。** 直接读 sim 的 geom（`bin2` body 下的 box）：

| 量 | 实测值 | 来源 |
| --- | --- | --- |
| 近侧墙板 | `xpos=[0.1, 0.03, 0.85]`、`size=[0.21, 0.01, 0.05]` ⇒ **墙顶 z = 0.9000** | `inner.sim.model/data`，body `bin2` |
| carry 门限 | `eef_z >= bin2_z + CARRY_HEIGHT - 0.02 = 0.8 + 0.16 - 0.02 = **0.9400**` | 对方 carry 段第二条分支 |
| 搬运时 can 中心 | ≈ 0.923~0.936（can 吊在 eef 下 0.015~0.017） | seed 1010 trace，step 74~121 |
| ⇒ can **底部** | 0.863~0.882（mesh AABB 半高 0.0407）/ 0.863~0.876（`bottom_offset=-0.06`） | `object_geom` 审计 |
| **间隙** | **−0.037 ~ −0.018 m（低于墙顶）** | 相减 |

**② 步级 trace：can 是在越过那面墙时滑脱的**（seed 1010，`--horizon 800`）：

| step | 相位 | `width` | `action[6]` | `_check_grasp` | `d_eef_can` | can 位置 |
| --- | --- | --- | --- | --- | --- | --- |
| 58 | lift | 0.0249 | +1（闭合） | **True** | 0.0150 | (0.138, −0.332, 0.861) |
| 101 | carry | **0.0409**（全开） | +1（闭合） | True | 0.0228 | (0.197, −0.028, 0.931) |
| 121 | carry | **0.0409** | +1 | True | 0.0274 | (0.203, −0.012, 0.936) |
| 141 | carry | 0.0016（空合） | +1 | **False** | 0.1230 | **(0.2035, 0.0251, 0.9247)** |
| 800 | carry | 0.0009 | +1 | False | **0.9977** | (0.2035, 0.0251, 0.9247) 一动不动 |

夹爪在**仍下发闭合指令**时张开到 0.0409 ⇒ can 被挤出去；它最终停在 `y=0.0251`，
而那面墙的中心就在 `y=0.03`（厚 0.02，跨 y∈[0.02,0.04]）⇒ **can 卡在了近侧墙板上**。

**③ 为什么没有恢复：两个独立的设计问题叠在一起。**
- 掉罐检测是 `can[2] < can_z0 + 0.02`（carry 段第一条分支）。can 卡在墙上时
  `rise = +0.0647` ⇒ **永远不触发**。
- carry 的水平指令是 `target = eef + (target_xy − can_xy)`，这是**开环偏移**
  （"往目标方向偏移一段"），不是"去 can 那里"。can 一丢，`(target_xy − can_xy)` 变成恒定矢量
  ⇒ 末端以最大速度（`action[:3]` 饱和）沿 +y 一路跑出去：实测末端终位 `(−0.4635, 0.7671, 0.9323)`，
  离 can **1.0 m**，而 step 200 之后对篮子的**净推进 = 0.0000**。

**④ 四个 D1 局把 can 丢在同一处 ⇒ 系统性碰撞，不是随机失手。**

| seed | `min_dist_target` | can 终位 | step200 后净推进 | 终局 `_check_grasp` |
| --- | --- | --- | --- | --- |
| 1010 | 0.3765 | (0.2035, 0.0251, 0.9247) | 0.0 | False |
| 1012 | 0.3753 | (0.2042, 0.0264, 0.9248) | 0.0 | False |
| 1018 | 0.3772 | (0.2037, 0.0247, 0.9248) | 0.0 | False |
| 1023 | 0.3764 | (0.2037, 0.0257, 0.9248) | 0.0 | False |

**⑤ A/B 验证：只改这一个常量。** 同一批 32 seed、同一 pinned can（`mass=0.01599621 kg`）、
同一出题（叶子播种，跨进程逐位可复现）、`horizon=400`：

| 条件 | `CARRY_HEIGHT` | carry 门限 `eef_z` | 成功 | 步数 min/中位/max |
| --- | --- | --- | --- | --- |
| C 基线 | 0.16 | 0.9400 | **23/32 = 0.719** | 141 / 189 / 400 |
| D 修复 | **0.22** | 1.0000 | **32/32 = 1.000** | 142 / **160** / 195 |

基线那 9 个失败局在 D 条件下**逐个转成功**，且都在 142~166 步内完成、`regrasp` 次数为 0：
1009(145) 1010(165) 1012(158) 1013(151) 1015(142) 1016(151) 1018(165) 1021(159) 1023(166)。
基线 C 的 23/32=0.719 与 `probe_contact_ceiling.py` 的 0.719 **逐题一致**
⇒ 取证脚本与天花板探针口径相同，两边的 seed 可以直接对照。

**口径时点（重要）**：C 与 D 两跑都在 2026-09-24 09:56~09:59 完成，**晚于**对方对
`envs/robosuite_pickplace.py` 的 09:51 修改 ⇒ 两个条件用的是同一份环境代码，A/B 内部有效。
另外 C 的逐 seed `success`/`steps`/`spawn_xy` 与 01:04 那次天花板探针运行（改环境之前）
**32 局全部一致、0 处差异** ⇒ 那次环境修改没有改变本实验涉及的物理路径，
0.719 这个基线数字在两个时点都成立。

## 2. 三类标签 ↔ 一个根因

| 代码 | 现象（探针标签） | 步级判据 | seed | 与根因的关系 |
| --- | --- | --- | --- | --- |
| **D1** `carry_no_progress` | `lift_no_carry`，`min_bin_dist` 在 400→800 步之间**逐位不动** | carry 步数 ~730、水平分支占比 0.52~0.64（**进得去**水平分支）、净推进 0.0、终局 `_check_grasp`=False | 1010 / 1012 / 1018 / 1023 | 撞墙后 can **卡在墙顶**（rise +0.065）⇒ 掉罐检测看不见 ⇒ 开环指令把末端甩出工作空间 |
| **D2** `regrasp_loop` | `lift_no_carry`，相位日志 `carry>regrasp1>approach>…` 循环 | `regrasp1` 发生在 step 76~88、当时 `rise≈0.002~0.003`（can 已落回桌面） | 1009 / 1013 / 1015 / 1016 | 同一根因，但 can **落回桌面** ⇒ 掉罐检测这次触发了 ⇒ 重抓后仍按同一高度搬 ⇒ 再撞，循环烧完预算（1009 在 `horizon=800` 下第二次尝试成功，713 步） |
| **D3** `release_drag` | `in_bin_no_success`：can 真进过篮（21 步）却没判成功 | step 123 先 `regrasp1`（can 落在 (0.208, 0.141, 0.852)，已在篮的 y 范围内）；终局 `_check_grasp`=**True**、`rise=+0.258`、末端 z=1.14 | 1021 | 撞墙掉罐 → 重抓 → 第二次搬进篮但**没真正松手**，`retreat` 把 can 拖着升高 ⇒ 判据第二半（末端离 can > 4.23 cm）永远不满足 |

注意 D3 里"释放不彻底"是**下游**后果：`--carry-height 0.22` 之后 seed 1021 在 159 步正常成功，
说明它并不是一个独立的释放段 bug（不过 §3 第 3 条那个闭环校验仍然值得加，见下）。

## 3. 建议改法（按性价比排序，都在对方文件里）

1. **`CARRY_HEIGHT` 抬到 ≥ 0.20**（实测 0.22 给 32/32）。
   几何下界可以算出来：can 底要清过墙顶 0.90 ⇒
   用 mesh AABB 半高 0.0407 算 `CARRY_HEIGHT ≥ 0.178`；
   用 robosuite 的 `bottom_offset = 0.06` 算 `≥ 0.197`。取 0.22 留 ~2 cm 余量给摆动。
   工作空间够：基线里末端最高实测到 `eef_z = 1.068`（门限 0.94 + 0.128），所以门限 1.00 可达。
2. **掉罐检测改用抓持真值/夹爪宽度，不要用 can 高度。** 现在的 `can[2] < can_z0 + 0.02`
   对"can 卡在墙上"（rise +0.065）和"can 被拖着走"都是瞎的。可用
   `width < 0.012`（空合，对方 grasp 段已经在用这个阈值）或 `env._check_grasp(...)`
   （每步调用会把每局从 4 s 拖到 15 s，建议只在 carry/place 段每 N 步问一次）。
3. **carry 的水平指令改成对 can 闭环**，例如 `target = can + [0, 0, hold] + 朝 target_xy 的分量`，
   或者干脆先"回到 can 正上方"再搬。这样即使丢了 can，也会自动退回 `approach` 重抓，
   而不是把末端以最大速度甩出工作空间（实测甩到离 can 1.0 m、离目标 0.377 m 原地打转 660 步）。
   顺带给 `regrasp` 加个次数上限 + 失败后停手，避免 D2 那种无限循环烧完预算。
4. **`release` 段加一个"can 真的离手了吗"的校验**（`_check_grasp` 为假、或 can 高度不再跟末端走），
   没离手就别 `retreat`。D3 的直接表现就是这个（末端抬到 z=1.14、can 被拖到 rise +0.258）。

## 4. 对上层（harness / 门禁）的影响

- **ceiling 规则不再拦**：`frontier_verdict` 的 `ceiling` 规则要求手写上限 ≥ 0.9；
  0.719 → 1.000 之后这一条通过，剩下的只有 `band`（策略侧 0.00 贴地）⇒
  **接触 A/B 的唯一阻塞项变成"策略侧要先把学习信号修出来"**，与 §12.11-R.3 的诊断一致。
- **`min_gain` 该按 1.0 天花板定**，不是按 0.72（§0 第 19 条已按此更正）。
- **PickPlace 在顶端也是饱和的**（和 Lift 一样）⇒ 难度旋钮仍然得挂在别处
  （下降高度 / 夹爪提前量 / 初始 yaw / 接触参数 / 出生范围），"任务本身难"这条路走不通。
- **不影响四臂 0% 的诊断**：那四个 SAC 臂 `ever_above_bin = 0`、`held ≤ 3/32`，
  它们根本没走到搬运段 ⇒ 参照臂修好**不会**让它们的成功率变非零。别把这两件事混起来。
- ⚠️ **如果这个控制器被用来采示范**：`CARRY_HEIGHT` +6 cm 会改变示范的动作分布
  （搬运段的末端高度与 z 方向动作），已采的示范池与新控制器不一致 ⇒ 改完后建议**重采**，
  否则 BC/示范预填学的是旧高度的轨迹。

## 5. 复现命令（两条，串行，各 ~1.5 min）

```bash
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot
SEEDS=$(python3 -c "print(','.join(str(1000+i) for i in range(32)))")

# C) 基线：应得 23/32 = 0.719（与 probe_contact_ceiling 的手写臂逐题一致）
MUJOCO_GL=egl OMP_NUM_THREADS=1 /root/venvs/rlrobot/bin/python -u \
  scripts/probe_scripted_defect_repro.py --seeds $SEEDS --horizon 400 --trace-every 200 \
  --out runs/infra/ceiling32_carry016_h400.json

# D) 只覆盖 CARRY_HEIGHT：应得 32/32 = 1.000
MUJOCO_GL=egl OMP_NUM_THREADS=1 /root/venvs/rlrobot/bin/python -u \
  scripts/probe_scripted_defect_repro.py --seeds $SEEDS --horizon 400 --trace-every 200 \
  --carry-height 0.22 --out runs/infra/ceiling32_carry022_h400.json
```

`--carry-height` 是**运行时 monkeypatch**（只在本进程覆盖对方模块常量，用于验证因果），
不改任何对方文件。要看单局的步级 trace，加 `--seeds 1010 --horizon 800 --trace-every 1`。

产物：
- `runs/infra/ceiling32_carry016_h400.json` / `ceiling32_carry022_h400.json`（32 seed × 两条件）
- `runs/infra/defect_repro_pickplace_base.json` / `defect_repro_pickplace_carry022.json`
  （9 个失败局 + 2 个对照，`horizon=800`，含逐步 trace）
- `runs/infra/probe_pickplace_scripted_h800.json`（horizon 敏感性：0.719 → 0.750）
- 取证脚本：`scripts/probe_scripted_defect_repro.py`（口径与 `probe_contact_ceiling.py` 一致：
  同一 pinned 物体、同一叶子播种出题、同一套 `_check_grasp` / `place_truth_fn` 真值）
