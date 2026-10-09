# RoboRSI 源码核对笔记（2026-09-22 实测）

源码位置：`../RoboRSI`（已从 `/tmp/roborsi_src` 备份到工作区，`/tmp` 是容器临时盘会丢）
上游：`https://github.com/nssmd/RoboRSI.git` · commit `9b644d2`（2026-09-21）

> 这一页只写**在仓库里核实过的事实**，以及它对我们路线的影响。官方宣传的数字与口径见 `../RoboRSI/README.md`。

## 1. 安装门槛（硬约束，直接影响环境规划）

| 项 | 实测值 | 影响 |
| --- | --- | --- |
| Python | `requires-python = ">=3.12"`（`pyproject.toml`） | base 是 3.11.9，**必须单独建 3.12 环境** |
| `[libero]` extra | `robosuite==1.4.0`、`gym==0.25.2`、`mujoco==3.3.0`、`bddl==1.0.1`、`numpy>=1.26,<2.3`、`transformers>=4.57,<6.0` | 与我们的 `rlrobot` 环境（robosuite 1.5.2 + gymnasium 1.2 + mujoco 3.13）**互斥**，不能装在一起 |
| 主依赖 | `lerobot[feetech,dynamixel,pi]`、`flexivrdk`、`record3d`、`litellm`、`mcp`、`openai>=2.8` | 体量很大；`lerobot` 会带一串机器人 SDK |
| 模型凭证 | `.env.example`：`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`、`ROBORSI_VLM_MODEL`、`ROBORSI_PERCEPTION_MODEL`、`ROBORSI_OPENAI_TRANSPORT=chat_completions\|responses` | **没有可用的 OpenAI 兼容端点就跑不了任何 agent 流程** |
| IK 服务 | `scripts/pyroki_ik_server.py`、`scripts/solve_ik.py`、`solve_trajopt.py` | 复现脚本会先起 PyRoKi 服务 |
| 一键复现 | `scripts/reproduce_libero_pro.sh`：建隔离环境 → 装 RoboRSI → clone LIBERO-PRO → 从 HF 拉 `zhouxueyang/LIBERO-Pro` 资产 → 配置 + 健康检查 → 起 IK 服务 → 跑 frozen code-on Pass-1 → 审计 journal（幂等、可续跑） | HF 不通，需要 `HF_ENDPOINT=https://hf-mirror.com` |
| 初始化 | `roborsi onboard` 生成 `~/.roborsi/config.json` 与 `~/.roborsi/workspace/{AGENTS.md,SOUL.md,TOOLS.md,USER.md,memory/MEMORY.md}`；`roborsi status` 自检；`roborsi web` 起 evolution dashboard `:8787` 与 Manager cockpit `:8795` | 上手第一步就是这三条命令 |

**结论：RoboRSI 需要一个独立的 py3.12 环境，且强依赖 LLM API。** 它不适合作为第一个跑通的项目，但很适合作为阶段 4 的上层。

## 2. 关键发现：RL 能力是内嵌的 LeRobot fork 提供的

`roborsi/learning/` 里只有 `auto_apply.py`、`base_skill_extractor.py`、`__init__.py` —— **没有 SAC/PPO/BC 训练器**。真正的训练栈在：

```
roborsi/embodied/engine/                    ← 内嵌的 LeRobot 分支
├─ src/lerobot/policies/                    act · diffusion · pi0 · pi05 · pi0_fast · sac
│                                           smolvla · tdmpc · vqbet · groot · sarm · rtc · wall_x · xvla
│   └─ sac/                                 configuration_sac.py · modeling_sac.py · processor_sac.py
│                                           · reward_model/          ← 奖励分类器
├─ src/lerobot/rl/                          buffer.py（ReplayBuffer）· gym_manipulator.py（make_robot_env）
└─ examples/tutorial/rl/
    ├─ hilserl_example.py                   SACPolicy + 双 ReplayBuffer(online/offline) + Classifier 奖励模型
    │                                       + SO100 follower/leader 遥操作；learner 与 actor 双进程用 mp.Queue 传 transition
    └─ reward_classifier_example.py         RewardClassifierConfig(model_name="microsoft/resnet-18")
                                            数据集 lerobot/example_hil_serl_dataset
```

三点实用结论：
1. **HIL-SERL 的参考实现已经在仓库里**，不用另找；它用的是 LeRobot 版 SAC，不是 stable-baselines3。
2. 示例里 `device = torch.device("mps")`（Mac 默认），在 Linux 上要改成 `"cuda"`。
3. 它默认绑 SO100（Feetech 舵机臂）。要换成 Genie G2，需要写 `make_robot_env` 的对应实现 + 奖励分类器的数据采集。
4. `roborsi/embodied/command/builder.py` 把「manifest + params」翻译成 `lerobot` / `lerobot-train` 的 CLI argv —— 也就是说**上层 harness 是通过调用 LeRobot CLI 来触发训练的**，这正是我们阶段 3 要仿的「训练触发器」形态。

## 3. 技能分层（`docs/skill-taxonomy.md`，官方就是中文写的）

```
skills/
├─ base/<robot>/<primitive>/     机器人原语（"肌肉"）：感知 / 运动 / 抓取 / 放置
├─ atomic/<task>/                单个可验证任务，四件套 + 两个复位相位
│   ├─ SKILL.md                    任务定义
│   ├─ zeroshot/                   VLM + base tools 直接做
│   ├─ train/                      数据集 + π₀ finetune
│   ├─ eval/                       held-out + 飞轮开关
│   ├─ reset_success/              ★ 成功后复位
│   └─ reset_failure/              ★ 失败救场
├─ long_horizon/<task>/          多 atomic 串联：plan / progress_judge / posttrain
└─ _lib/<lifecycle>/<name>/      通用工具盒，不面向用户
```

frontmatter 强约定：`kind`、`robot`、`parent`、`phase`、`domain` + 标准 `name/description/version/metadata`。

**对我们最有价值的一点**：`reset_success` / `reset_failure` 这两个相位，正好就是我们「正反向交替搬运 + 失败救场」的现成插槽。阶段 2 自写的双向环境，接口按这个 taxonomy 对齐，将来迁到 RoboRSI 几乎零成本。

## 4. 评测口径（`docs/EVALUATION.md`）——这套纪律值得直接抄

- 两种运行模式：`ROBORSI_RUN_MODE=evolve`（可写回能力）/ `eval`（冻结，不改变后续 run 能做什么）。
- `roborsi eval <atomic-task> --seeds 5 --seed-start 0 --backend libero --sim-task libero_object/0 --tool-budget 40`，Planner/Engineer/Reviewer 逐 seed 跑，**成功标签只由仿真器的 post-episode 判定给出**。
- 三个角色的模型可以分别 pin：`--planner-model / --engineer-model / --reviewer-model`。
- journal 是 append-only，`roborsi eval-audit` 独立重算分数。
- 失败被分成三类，**不混在一起**：任务失败 / `infra_count`（provider、backend、transport 等基础设施错误）/ `implementation_error_count`（代码缺陷）。
- 每次 run 落 `plan.md`、`summary.md`、`review.md`、工具调用轨迹、`trace.db`。
- README 明确写了：累计通过率是「跨版本至少成功过一次」，**不是** frozen-policy 分数，也不是固定方法的 Pass@k。

我们的 `eval/reach_eval.py` 现在只有「成功率 + 平均奖励」。按这套纪律，下一步应该补：
- `infra_count` / `implementation_error_count` 分离；
- append-only 的 run journal；
- 一个独立的 `audit` 脚本重算分数（防止训练脚本自己报高分）。

## 5. `docs/capx-pickplace-lessons.md`：纯视觉抓取的工程纪律（强烈建议精读）

背景是 CaP-X 在 LIBERO-PRO 上的复盘，同一 benchmark 的对照数字：
OpenVLA / π₀ = 0%，π₀.₅ ≈ 13%，**CaP-Agent0 = 18%（纯视觉、无训练）**，ASPIRE ≈ 72%。

它的核心论点：**18% 不是靠某个神仙抓取网络，而是靠「可靠定位 + 干净点云 + 多候选校验 + 受控执行」这一整套工程纪律。**

感知栈（按顺序）：
1. Molmo 精确指点（语言 → 图上一个点），**不让主 VLM 猜像素**（实测：主 VLM 猜像素判别正确物体 ≈ 1/7，SAM3 ≈ 4/7）；
2. SAM3 点提示分割，拿不到点就退回文本提示；
3. 多视角（`agentview` + `robot0_eye_in_hand`）都分割并**取交集**，天然滤掉「整桌」伪 mask；
4. DBSCAN 清点云噪声（`eps=0.005, min_samples=10`）。

抓取配方：多视角点云 → 清洗 → Contact-GraspNet 出 N 个 6-DoF 候选 + 分数 → **沿抓取轴 +0.12m 生成 pregrasp** → 取最高分 → 夹爪 yaw +90° 修正。

对我们的直接启示：**抓取失败的第一嫌疑是感知定位，不是 RL 策略**。所以阶段 2 的双向搬运先用仿真真值（物体位姿）做观测，把「感知」这个变量摘出去；等 RL 闭环跑通了，再单独引入视觉与定位误差，并做对照。

## 6. 官方 README 的结果表（口径注意）

| 指标 | 数字 | 口径 |
| --- | --- | --- |
| LIBERO 累计任务通过 | 95/120 | 跨版本累计覆盖；十轮 32/120 → 83/120 |
| LIBERO-PRO 累计 | 80/120 | 5 个自适应版本，43 → 80 |
| LIBERO-Plus 扰动实例 | 398/840（adaptive Pass@2） | 固定版本 261/840，+16.3 点 |
| Code-on / Code-off（匹配） | 174/600 vs 129/600 | 120 任务 × 5 布局，+7.5 点 |
| 效率面板（118 任务，中位数） | tokens −29.4% · VLM 调用 −27.2% · 墙钟 −17.0% | Code-on vs Code-off |
| RoboTwin 累计 | 36/50 | 三角色；单角色基线 9/50 |
| 纠正轨迹学习案例 | 1 个匹配任务成功 | 304 帧 → 2,432 样本 → 1,000 步微调 |

**读法**：Code-on/Code-off 与效率面板是匹配对照，最有说服力；累计类指标回答「迭代到现在曾经解决过多少任务」，不回答「冻结当前版本、换一批初始状态能稳定成功多少」。我们自己做实验时两种都要留。

## 7. 本机把 LLM 通路接通的实测记录（2026-09-23）

结论先行：**`roborsi eval` 的角色模型不读 `config.json` 的 `agents.defaults`，只认环境变量；
而 agent loop 的模型路由只有「OpenAI 兼容」和「Anthropic SDK」两条路。** 不知道这两点，
第一次跑 eval 必然死在 `ModuleNotFoundError: No module named 'anthropic'`（本机没装 anthropic）。

实测依据（代码位置）：

1. 角色模型解析顺序是环境变量，默认值硬编码成 anthropic：
   `roborsi/agents/planner.py:402`、`engineer.py:31`、`reviewer.py:620` 都是
   `ROBORSI_<ROLE>_MODEL or ROBORSI_VLM_MODEL or "anthropic/claude-opus-4-8"`。
   `config.json` 里的 `agents.defaults.model/provider` 只服务于交互式 manager / 冒烟脚本那条路。
2. 工具调用路由只有两条：`embodied/agent_loop/vlm_io.py::_call_vlm_tools` 里
   模型串以 `openai/ azure/ gpt- o3 o4` 开头走 OpenAI 兼容 Chat Completions，**其余一律走
   Anthropic SDK**（`_anthropic_call_with_tools`，第 489 行 `import anthropic`）。
3. 感知（喂图）同样只有两条：`_call_vlm_image_impl` 走 OpenAI 兼容或 Anthropic，
   且**必须是视觉模型**——把纯文本的 `qwen3.8-max` 喂图会 400。

因此本机的正确姿势是「拿 DashScope 的 OpenAI 兼容端点冒充 OpenAI」，包装器在
`../roborsi_runtime/bin/roborsi-dashscope`（与 `bin/roborsi` 同构，只多四个变量）：

```bash
ROBORSI_OPENAI_API_KEY=<dashscope key>          # 从 home/.roborsi/config.json 的 providers.dashscope 读
ROBORSI_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
ROBORSI_VLM_MODEL=openai/qwen3.8-max            # planner/engineer/reviewer 一起 fallback 到它
ROBORSI_PERCEPTION_MODEL=openai/qwen-vl-max     # 感知必须 VL 模型
```

已验证（2026-09-23，均走 compatible-mode）：

- `qwen3.8-max` 接受 `max_completion_tokens`、`tool_choice="auto"`，能正确返回 function call
  （`get_gripper_state({"include_distance": true})`）；
- `qwen-vl-max` / `qwen3-vl-plus` 能吃 base64 图片并答对颜色（注意：手搓的 1x1 PNG 会被
  DashScope 判「image format is illegal」，测试图要用真编码器生成）；
- SiliconFlow 的 key 返回 403「Model disabled」、讯飞的 URL 缺 `/chat/completions`，
  三个 endpoint 里只有 DashScope 可用（见 `REMOTE_ENDPOINTS.md`）。

跑通后的最小 eval（后台、nice 15、单线程，别和训练抢 CPU）：

```bash
cd ../roborsi_runtime
setsid nohup nice -n 15 env OMP_NUM_THREADS=1 bin/roborsi-dashscope eval libero_pick_place \
    --backend libero --sim-task libero_object/0 --seeds 1 --tool-budget 10 --json \
    > logs/eval_dashscope_$(date +%Y%m%d_%H%M%S).log 2>&1 < /dev/null & disown
```

产物在 `home/.roborsi/evals/manifests/*.json`；`--json` 的 stdout 不是纯 JSON，
解析前先定位第一个 `{`。

### 7.1 第三次 eval：**完整三角色闭环跑通**（2026-09-23 13:48→14:21，实测数据）

三次尝试的对照（同一个命令，只改模型路由）：

| 本地时间 | manifest | status | outcome | 墙钟 | 死因 |
| --- | --- | --- | --- | --- | --- |
| 11:27 | `…T032721Z-…-d930626a` | incomplete | implementation_error | 62s | `ModuleNotFoundError: anthropic`（角色模型默认 anthropic，见 §7） |
| 11:55 | `…T035542Z-…-c038d7c0` | incomplete | implementation_error | 599s | DashScope 400 `thinking_budget`（`vlm_io.py:694` 硬编码 `reasoning_effort="low"` 打到 `qwen-vl-max`） |
| 13:48 | `…T054857Z-…-44ef86a1` | **complete** | `budget_exceeded`（12 tool calls） | 1962s | 任务没成功，但 Planner→Engineer→Reviewer **走完了** |

成功那次的配置：`ROBORSI_VLM_MODEL=openai/qwen3.8-max`（三角色共用）+
`ROBORSI_PERCEPTION_MODEL=openai/qwen3-vl-plus`；task `libero_pick_place`
（指令 `pick the alphabet soup and place it in the basket`）、backend `libero`、
sim_task `libero_object/0`、`--seeds 1 --tool-budget 10 --json`、`run_mode=eval`、
`frozen=true`、commit `9b644d2`（`git_dirty=false`）。

**成本结构**（做预算时直接照抄这一张表）：

| 项 | 数值 | 占比 |
| --- | --- | --- |
| 总 token | 215,841 | — |
| Engineer | 202,829（56 次 VLM 调用，墙钟 1823s） | **94%** |
| Planner | 6,843（1 次，68s） | 3% |
| Reviewer | 6,169（1 次，48s） | 3% |
| 感知类工具耗时 | 1351.8s | **89%**（tool 总时 1520.7s） |
| 动作类工具耗时 | 168.9s | 11% |
| 恢复类工具耗时 | 0.0s | 本次没触发 |

结论：**贵的是感知调用**（`find_pixel` / `find_by_pointing` / `visual_pick_place` 单次
100~420s），不是 LLM 推理。要压成本先压感知次数与图片尺寸，换小模型收益有限。

**Reviewer 的诊断**（harness 上层最有价值的一环，全文在 workspace 的 `review.md`）：

- `verdict=continue`、`proposal=NO_PROPOSAL` —— eval 模式冻结能力集，**不产生技能修订，
  这是正确行为**（想看到 proposal 必须离开 eval 跑改进流程）。
- root cause：`visual_pick_place` 在离开源视野时脱手（hold lost）；随后 `grasp_object`
  复用了 step-1 的**过期像素** `[137,167]`，GraspGen 找不到可行抓取。
- next action：失败后必须重新 grounding，用新的 top-center 像素，放置前先跑
  `verify_holding_visual`。
- 最值得学的一条：step 8 已经拿到新像素 `[65,125]`，下一步却选了 `observe_orbit`
  而不是重试抓取 —— Reviewer 明确点出这个「拿到了信息没用上」的决策错误。
  这正是我们 `harness/diagnose.py` 想干的事，差别在于它用模型解释、我们用客观量 +
  固定失败标签（后者可复现、可回归，前者能提出**改法**）。

Engineer 的 12 步 trace（`summary.md` 原样，`ok=False` 的是 2/5/6/7）：

```
[0] look()                                  ok=True
[1] find_pixel(alphabet soup can, center)    ok=True
[2] visual_pick_place(source→basket)         ok=False   ← 脱手
[3] look()                                  ok=True
[4] find_by_pointing(…)                      ok=True
[5] find_by_detector(alphabet soup can)      ok=False
[6] find_by_pointing(alphabet soup)          ok=False
[7] grasp_object(pixel=[137,167])            ok=False   ← 复用过期像素
[8] ?({})                                    ok=None    ← 日志里工具名丢了（见坑 2）
[8] ?({})                                    ok=None
[8] find_pixel(top center of the can body)   ok=True    ← 拿到新像素 [65,125]
[9] observe_orbit(image_size=512)            ok=True    ← 没用它重试
```

产物路径：

- manifest：`home/.roborsi/evals/manifests/20260923T054857Z-libero_pick_place-44ef86a1.json`
- workspace：`home/.roborsi/workspaces/libero_pick_place-20260923-134858-e0d9cd/`
  （`plan.md` / `summary.md` / `review.md` / `rollout/libero_pick_place-0/` 里的
  `tick_*.jpg`、`orbit_*.png`、`grasp_identity_candidate.png`）
- 失败视频：`/root/roborsi_trial/RoboRSI/artifacts/evals/libero_pick_place-seed0-failure-20260923-142047.mp4`（48 KB）
- 运行日志：`logs/eval_dashscope_20260923_134856.log`

三个实测坑：

1. `plan.md` 的内容是 `(planner output empty)`：Planner 在这条路由下产出为空，
   但**不阻塞**流程，Engineer 直接从任务指令开工。所以「eval 失败」不能算到 Planner 头上；
   要拿到真正的任务拆解，得去查 `roborsi/agents/planner.py` 的 prompt/解析。
2. trace 里的 `[8] ?({}) → ok=None` 说明 summary 的工具名会丢。复现调用链时不能只信
   `summary.md`，要和日志里的 `[zeroshot] step=N → tool(…)` 行对齐。
3. `tool_calls=12 > tool_budget=10`：预算检查发生在调用**之后**，超出才收尾并记
   `budget_exceeded`。做成本核算按实际 `tool_calls`，不要按预算值。

RoboRSI 侧下一步：

1. `--tool-budget 20 --seeds 3` 重跑，看 `success_rate` 能不能 > 0（当前 0/1 只证明
   **闭环通了**，不证明能力）。
2. 查 Planner 空输出 —— 它决定「任务怎么拆」，是自进化的入口。
3. 想看到技能修订（`proposal != NO_PROPOSAL`）必须跑非 eval 的改进流程。
4. 与我们 harness 的对接点已经清楚：Reviewer ≈ `harness/diagnose.py`。可行的合流方式是
   **客观标签负责判定与采样，模型解释只负责提出候选改法**，而任何改法都要先过
   `docs/notes_stage3.md` §12 的探针门禁（量强度 → 覆盖率 → 小预算 A/B）才允许生效 ——
   这样「大模型改东西」就不会变成不可复现的 reward hacking。
