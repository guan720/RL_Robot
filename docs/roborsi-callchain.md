# RoboRSI 源码级调用链笔记

> 目的：不装、不跑，先把"一轮执行如何变成下一轮能力"这条链看懂。
> 依据：本地只读 clone `/tmp/roborsi_src`，commit `9b644d2`（2026-09-21）。
> 重新获取：`git clone --depth 1 https://github.com/nssmd/RoboRSI.git /tmp/roborsi_src`
> （`/tmp` 可能被清，别把它当长期资产；本文所有结论都标了文件行号，可复核。）

## 0. 一句话定位与成熟度

RoboRSI = **LLM 多智能体 + 三层技能树 + 代码级自进化的 harness**。
它进化的是**技能代码/工作流**，不是神经网络权重（RL 只是其中一个很小的可选技能）。

| 项目 | 事实 |
| --- | --- |
| 仓库 | `nssmd/RoboRSI`，穹彻智能 Noematrix Lab 出品 |
| 建仓 / 最近提交 | 2026-08-29 / 2026-09-21（不到一个月，迭代很快） |
| 版本 / 状态 | `version 0.1.0`，`Development Status :: 3 - Alpha`，77 star |
| License | `LICENSE` 是 Apache-2.0，但 `pyproject.toml` 写 MIT（不一致，引用前注意） |
| Python | `requires-python >= 3.12`（本机 base 是 3.11，要新建环境） |
| 主战场 | LIBERO 120 任务 / LIBERO-PRO / LIBERO-Plus / RoboTwin |

## 1. 角色链：一轮执行发生了什么

```
用户指令 → Manager(任务队列) → Planner(plan.md) → Engineer(工具循环执行)
                                                      ↓ 可见轨迹 + journal
                                        Reviewer(根因定位 + 修订提案)
                                                      ↓
                             no-regression gate（真仿真器任务上验证）→ git commit
```

对应源码入口（`roborsi/agents/`）：`manager/`、`planner.py`、`engineer.py`、`reviewer.py`、
`lh_executor.py`（long-horizon 执行）、`compound_proposal.py`（修订提案）、
`proposal_safety.py`（提案安全审查）、`plan_archive.py`（历史 plan 归档）、
`gt_firewall.py`（**防止 ground-truth 泄漏给 agent**）、`html_review.py`（把 review 渲染成 HTML）。

关键工程细节：`roborsi/embodied/agent_loop/rollout.py:614` 的 `_dispatch_with_timeout`
用 `ThreadPoolExecutor` 给每个工具调用套 300s 墙钟上限，并在注释里记录了一次失败尝试——
2026-06-15 想用 `SIGALRM` 做超时，结果更糟（C 扩展持有 GIL 时信号投递不进去，
cuRobo 卡死变成 30 分钟不可恢复的冻结），已回滚。
**同一段注释还写明：MuJoCo 的 EGL 上下文是线程亲和的，所以 LIBERO 工具必须在环境所属线程上执行。**

产物与审计：每次运行写 `plan.md` / `summary.md` / `review.md`，工具调用与耗时进 `trace.db`
（`roborsi/store/trace_db.py`），campaign manifest 落在 `~/.roborsi/evals/manifests/`，
journal 是 append-only，`roborsi eval-audit`（`roborsi/evaluation/audit.py`）可独立重算分数。

## 2. 三层技能树（它最核心的约定）

```
long_horizon/<task>/    任务族：用户指令 → 有序的原子步骤
atomic/<task>/          原子任务：范围清晰、结果可验证；稳定路径会固化成代码
base/<robot>/<prim>/    基础原语：感知 / 运动 / 抓取 / 放置，既被 atomic 调用，也直接作为 VLM tool 暴露
```

- 每个技能 = 一个文件夹：`SKILL.md`（给 VLM 看的接口说明 + YAML frontmatter 参数表）+ `policy.py`（实现）。
- **双形态**：`policy.run(env, **params)` 给上层代码调；同时是 VLM 的工具（zeroshot 阶段被 VLM 直接调）。
- base 原语已实现约 70 个，按机器人分子目录（`base/<prim>/libero/`、`base/<prim>/robotwin/`）。
  值得抄的命名：`move_to_pose` / `move_ee_delta` / `move_to_pixel` / `unproject_pixel` /
  `grasp_top_down` / `grasp_obb` / `grasp_rim` / `place_on_surface` / `place_obb` /
  `is_holding` / `verify_holding_visual` / `verify_pick_complete` / `is_reachable` /
  `recover_joint_posture` / `probe_ik_workspace` / `preview_move_to_pose` /
  `execute_previewed_move` / `recall_past_success` / `register_skill` / `read_task_wiki` /
  `visual_diff` / `zoom_in` / `observe_orbit`。
  注意 `verify_*` 和 `recover_*` 是独立原语 —— **"验证是否真的抓住了"和"恢复"被当成一等能力**，
  这正是我们阶段 2/3 最容易漏掉的部分。
- 技能库分层目录：`skills/_lib/{collection,dataset,evaluation,human_review,judging,library,minting,orchestrate,rl,solidified,training}`。
- `long_horizon/` 里已有 `clean_table_bicoord`、`collect_pens_bicoord`、`match_blocks_bicoord`。
  ⚠️ 这里的 `bicoord` 是 **BiCoord-Bench 双臂协同**（embodiment `aloha-agilex`），
  **不是**我们想做的"正反向交替搬运"，别混淆。

## 3. LIBERO 后端实现细节（当作"动作接口语义"的现成教材）

`roborsi/embodied/sim/libero/adapter.py`：

| 位置 | 事实 | 为什么重要 |
| --- | --- | --- |
| `:663` | 环境用 `OffScreenRenderEnv(controller="JOINT_POSITION", ignore_done=True, use_object_obs=True, camera_heights/widths=256, camera_depths=True)` | 分辨率默认 256，可用 `ROBORSI_LIBERO_RES` 改；注释说明原生 512 会让离屏 `MjrContext` 报 "framebuffer not complete" |
| `:663` 注释 | 选 `JOINT_POSITION`（Jacobian-IK servo）而不用 OSC，因为"OSC wedged at joint limits" | 控制器选择是被坑出来的，不是随便定的 |
| `:255` | `step()` 收 7 维动作 `(dx,dy,dz,droll,dpitch,dyaw,gripper)` | 名义上是 OSC_POSE 语义，实际直接喂给 JOINT_POSITION 控制器 |
| `:574` | `_NOOP_ACTION = [0.0]*7 + [-1.0]`（保持关节、夹爪张开） | reset 后 settle 用的空动作 |
| `reset()` | 每个 episode 都要重设 `output_max=±0.35`、`kp=300`、`kd=2*sqrt(300)`，因为 `env.reset()` 会重建 controller | 典型的"仿真器状态会在你以为不变的地方被重置" |
| `:32` `:349` | 成功只由 `env.check_success()` 判定，且**在 agent 工具循环结束后只判一次** | 不让 agent 自己说成功 |
| `:212` | `_bind_gl_context()`：把离屏 GL 上下文绑回调用线程 | 呼应 rollout 里的线程亲和注释 |
| `:338` | 只有 `check_success()` 为真的 episode 才存 mp4 进 demo 库（"demo library should hold WINS"） | 数据质量控制 |
| `_visible_raw_obs()` | 在 adapter 边界把 object 相关的 obs key 全部删掉 | 仿真里保留 object observable（LIBERO-PRO 0.1 建模需要），但**不让 agent 看到** → 防 ground-truth 泄漏 |

渲染配置在 `roborsi/embodied/sim/libero/runtime.py:150`：`configure_headless_rendering()`
把 `MUJOCO_GL` 默认设成 `egl`，并且只有 `find_library("EGL_nvidia")` 成功时才写
`~/egl-vendor/10_nvidia.json`。本机没有 `libEGL_nvidia.so.0`，所以它不会写 ICD，
最后落到 Mesa 的 llvmpipe 软渲染 —— **能跑，但不会告诉你它没用 GPU**（详见 `docs/infra-gpu-render.md`）。

## 4. 评测口径（这部分设计非常值得我们照抄）

`docs/EVALUATION.md` + `roborsi/evaluation/`：

- 两种运行模式显式分开：`evolve`（可回写持久能力）vs `eval`（冻结，不改变后续运行）。
- `roborsi eval <atomic-task> --backend libero --sim-task libero_object/0 --seeds 5 --seed-start 0 --tool-budget 40`，
  三个角色的模型可以各自 pin（`--planner-model / --engineer-model / --reviewer-model`）。
- **成功率只在"拿到仿真器最终裁决"的 seed 上计算**；provider/backend/transport 等错误单独计为
  `infra_count`，代码缺陷计为 `implementation_error_count`，**都不并入任务失败**。
  分类逻辑在 `roborsi/evaluation/atomic.py:24`：异常类型白名单 + 消息关键词
  （`"egl"`、`"cuda out of memory"`、`"rate limit"`、`"timeout"`、`"http 5xx"`…）。
- README 的指标自己标了口径：`95/120`、`80/120` 是**跨版本累计覆盖**（任务只要有一次通过就算），
  明确写了 "they are not frozen-policy scores or fixed-method Pass@k"。
  其它口径：LIBERO-Plus `398/840` adaptive Pass@2（固定版本 261/840）；
  code-on vs code-off `174/600 vs 129/600`（120 任务 × 5 布局）；
  效率面板 tokens −29.4% / VLM 调用 −27.2% / 墙钟 −17.0%；RoboTwin `36/50`（单角色基线 9/50）。

## 5. 它的"学习"到底有多少（对我们目标的现实评估）

- `roborsi/embodied/engine/` 是**内嵌的一份 LeRobot**（不是 pip 依赖），带
  `examples/tutorial/act/`、`examples/tutorial/diffusion/`、`examples/training/train_policy.py`、
  `src/lerobot/policies/sac/`、`src/lerobot/rl/learner.py`、`examples/tutorial/rl/hilserl_example.py`。
- 技能层只有两个学习入口：
  - `_lib/training/pi0_finetune`：包装 `lerobot-train`，在 RoboRSI 自建数据集上微调 π₀ / π₀.₅
    （默认 `steps=20000`、`batch_size=8`、`lr=2.5e-5`、`device=cuda`）。
  - `_lib/rl/pi0_posttrain`：唯一的 RL 技能。参数 `backend=robotwin`（默认！）、`rollouts=1000`、
    `updates=200`、`reward ∈ {success_predicate, progress_score(VLM 打分), dense_shape}`。
    它的 SKILL.md 自己写了 "When NOT to use：finetune 成功率还没测之前别上 RL；
    RL 后训练很慢，不要花 GPU-weeks 从 30% 的 finetune 里再榨 5%"。
- README 成果表里与 RL 相关的只有**一行**：`304 帧纠正轨迹 → 2432 样本 → 1000 步微调`，
  且标注为 "1 matched task success"。
  ⚠️ 这正是 ROADMAP 里提醒的那类数字："一条轨迹切成 2432 个样本" ≠ "2432 次独立交互"。

**结论**：如果目标是"机械臂强化自学习"，RoboRSI 提供的是**上层编排 + 代码级自进化 + 评测纪律**的参考实现，
RL 部分是薄的、且默认绑在 RoboTwin（本机跑不了）上。它值得读、值得抄设计，但不适合当 RL 入门主线。

## 6. 如果要在本机试跑（最小代价路径）

前置事实：官方 `scripts/reproduce_libero_pro.sh:13` 写明需要
`Linux + git + python3.12+ + an NVIDIA/CUDA stack for the LIBERO renderer + OPENAI_API_KEY`。

```bash
# 1) 新建 py3.12 环境（base 是 3.11，装不上）
conda create -n roborsi python=3.12 -y && conda activate roborsi
# 2) 只装 LIBERO 后端（别装 dev/web/wecom 等一堆 extra）
pip install -e "/tmp/roborsi_src[libero]"      # 会拉 mujoco==3.3.0 robosuite==1.4.0 gym==0.25.2 bddl==1.0.1
# 3) LIBERO-PRO 代码与资产（HF 必须走镜像）
git clone --depth 1 https://github.com/Zxy-MLlab/LIBERO-PRO.git
export HF_ENDPOINT=https://hf-mirror.com
hf download zhouxueyang/LIBERO-Pro --repo-type dataset --local-dir ./LIBERO-PRO-assets
# 4) 配置 + 体检（doctor 会做 reset 冒烟）
roborsi onboard && roborsi status
roborsi libero configure --root ./LIBERO-PRO --bddldir ./LIBERO-PRO-assets/bddl_files --initdir ./LIBERO-PRO-assets/init_files
MUJOCO_GL=osmesa roborsi libero doctor --backend libero --task libero_object/0 --reset
# 5) 单任务冻结评测（先别碰 reproduce_libero_pro.sh 的完整 campaign）
MUJOCO_GL=osmesa roborsi eval libero_pick_place --backend libero --sim-task libero_object/0 --seeds 2 --tool-budget 20
```

已知会卡住的点：
1. **必须有 OpenAI 兼容的 Responses 端点**（`OPENAI_API_KEY`）；三个角色都要调模型，成本和排障都在这。
2. **PyRoKi IK/轨迹服务**：官方脚本会单独建 `.venv-pyroki` 装 `git+https://github.com/chungmin99/pyroki.git`
   并以 ZMQ 服务方式常驻（`scripts/pyroki_ik_server.py`）。手动装的话这一步要自己起。
3. `gym==0.25.2` + python 3.12 的组合容易出编译/兼容问题，装不动就先固定 `mujoco==3.3.0`。
4. 渲染按 §3 的说明只能是 CPU 软渲染，256px + depth 每帧约几十毫秒量级，`--seeds` 和 `--tool-budget` 要压小。
5. RoboTwin 后端直接放弃（SAPIEN + Vulkan + cuRobo，见 `docs/sim-robotwin.md`）。

## 7. 值得我们阶段 3 直接照抄的设计

1. **成功判定权只属于环境**：`env.check_success()`，agent 不能自证成功；long-horizon 那边甚至用
   "全新 VLM 子进程看图判定、不给任何 sim 特权状态"（`collect_pens_bicoord/SKILL.md`）。
2. **infra 错误与能力缺陷分开记账**，成功率只在拿到最终裁决的 seed 上算 → 我们的 `eval/reach_eval.py`
   以后也该把"环境崩了/超时"和"策略没学会"分开统计。
3. **累计覆盖 与 冻结版本单次成功率 两个指标都留**，防止用累计覆盖掩盖旧任务退化。
4. **每次能力变更 = 一次 git commit + 一道 no-regression gate**（在真仿真任务上验证才允许提交）。
5. **append-only journal + 独立 audit 重算**，让分数可复核而不是信一次输出。
6. **ground-truth 防火墙**：仿真里可以有特权信息，但在 adapter 边界删掉，避免 agent/策略"作弊"。
7. **`verify_*` / `recover_*` 作为一等原语**，而不是散落在任务代码里的 if。

## 8. 它没解决的（也就是我们的研究空间）

- **正反向交替 / reset-free**：它的 `bicoord` 是双臂协同，不是"正向搬完自动创造反向初始条件"。
  谁负责复位、两个方向都失败时怎么办，RoboRSI 里没有答案。
- **人类接管 → LLM 接管**：它有 `human_review` 技能目录和 `recover_joint_posture` 原语，
  但接管触发条件、控制权交接、接管动作质量、接管数据如何回流训练，都没有闭环。
- **VLM 评分的校准**：它用 VLM 判成功（long-horizon）也承认要防 reward hacking，
  但没有"VLM 判定 vs 仿真真值"的误判率统计流程 —— 这是我们该补的实验。
