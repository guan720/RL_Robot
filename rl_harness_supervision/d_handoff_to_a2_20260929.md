# D → A2 执行单（2026-09-29 16:4x）：**π₀.₅ + 仿真**的 P0 接口与时间预检（v4 §12 P0 / §10.2-1）

交出方：智能体 D（监管/口径裁定线）。接收人：**智能体 A2（VLA 底模与仿真贯通线，新开）**。抄送：B2（数据与判据线）、A/B/C（收尾后冻结）。
依据：用户 2026-09-29 裁定（`work/project_parameters.json` → `measurements_and_decisions[0]`）＋
`rl_harness_supervision/supervisor_memo_20260929.md` **增补十五（裁定 38）**。
上位方案：`RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md`（**只读**）。

---

## 0. 你的定位与**不许做**的事（先读这节）

**定位**：把 v4 的 P0（接口和时间预检）在**仿真**上做实——回答「π₀.₅ 能不能在本机被加载、它的动作/时间契约是什么、
它接进本仓 harness 数据面要改什么」。**你不是能力线**：本阶段**不承诺成功率**，`01_开发技术方案.md:355` 明写
「没有硬件与实测依据时，不承诺 GPU 数量、训练时长或成功率」。

**不许做**（每条都有本仓的前车之鉴）：
1. **不许把 ACT 线的结论搬过来当 π₀.₅ 的结论**，也不许反过来用 π₀.₅ 的存在去否定 ACT 线的历史产物（那批产物是回归基线，见 `d_freeze_abc_20260929.md`）。
2. **不许在 `/root` 下建 venv 或落权重/数据集**：`/root` 与 `/opt/conda` 是容器临时层，重建全丢（今天刚为这事做过一次环境迁移 + 不变性证明）。一律用 `codex-persist mkvenv`，缓存与权重指到 `.codex-persist/`。
3. **不许碰冻结面**：0928 两份 lock、`attribution/arms_summary_v3.json`、`lerobot_act_env_20260928/arms_summary.json`、门禁 `requirements.lock.txt`、`clip*.json`。也不许改 `harness/`、`registry/`、`configs/` 里 A/B/C 已交付的实现——要改先报 D。
4. **不许用 `rm`**：清理一律 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`（全局硬约束）。
5. **不许自排 GPU 长任务**：单卡独占，起跑前在 `daily_report.md` 申报（预计时长 + 显存 + 是否可被中断），跑完销账。
6. **不许把「加载成功 / 跑完 20 局」写成「能力」**：见 §5 的「不得声称」清单。
7. **不许直接改 `work/project_parameters.json`**：那是 D 的单写者文件。你交**建议值 + 证据路径**，D 落笔。

---

## 1. D 已实测的前置事实（**不要重做**，直接用；重做即浪费 12 核配额）

| 事实 | 实测结果 | 复现方式（D 本轮跑过） |
|---|---|---|
| π₀.₅ 代码面 | **已在**：lerobot 0.4.4 的 `policies/` 含 `pi0` / `pi05` / `pi0_fast` / `groot` / `wall_x` / `xvla`；`pi05` = `configuration_pi05.py` + `modeling_pi05.py` + `processor_pi05.py`，`paligemma_variant` 默认 `gemma_2b`，PaliGemma 主干由 `CONFIG_MAPPING["paligemma"]()` 构建 | `/root/venvs/lerobot_act/bin/python` + `pkgutil.iter_modules` + `grep -rn paligemma policies/pi05/*.py` |
| **加载阻塞** | **`transformers` 在四个 venv 全部未安装**（lerobot_act / lerobot_eval / rlrobot / maniskill_probe）；`gym-aloha`、`gym-xarm`、`gym-pusht`、`openpi` 均未安装 ⇒ **现在 `from_pretrained` 一定失败** | 各 venv 的 `importlib.metadata.version` |
| 权重通道 | ① `hf-mirror.com` **API 元数据可读**（`lerobot/pi05_base`，7 文件，`lastModified 2026-07-29`）；② `hf-mirror.com` **blob 返回 HTTP 429「访问频率限制」**，间隔 20s 重试仍 429；③ `huggingface.co` 直连**挂起无产物**；④ **`www.modelscope.cn` 可达**（302→/home），其 `lerobot/pi05_base` 文件表可读，**`model.safetensors` = 14467.2 MB** ⇒ **首选 ModelScope** | `curl` 各端点（HTTP 码 / content 大小 / `repo/files` API） |
| 环境可装性 | `gym-aloha` 在当前 pip 源（aliyun）可见 **0.1.4** | `pip index versions gym-aloha` |
| 算力 | **1× A800-SXM4-80GB（85.1 GB）空闲**；**CPU 配额只有 12 核**（`cpu.max=1200000/100000`，已有限流记录），`nproc=112` 是宿主机口径；无 docker、无 Vulkan（**像素档渲染不可用**） | `nvidia-smi` / cgroup / `df -h` / `daily_report.md` 16:0x 段 |
| 存储 | NFS 可用 **67T**（已用 94%）；overlay 可用 5.6T | `df -h` |
| 邻近资产 | `/workspace/mnt/sppro/yhzhang91/scripts/yhzhang91/vla_pipeline`（validate→clean→qc）；`/workspace/mnt/sppro/yhzhang91/workplace/ABC130k/`（真实双臂示范，单 episode 4749 帧、每臂 joint6+pose7、gripper1、3 组 intrinsics） | 见 `work/project_parameters.json` |
| 外部事实（**未实测**） | π₀.₅ 已开源（openpi + LeRobot）；`lerobot/pi05_base` 标 **`license:gemma`**；社区微调显存报告**互相矛盾**（48GB 不够 vs ≈40GB 可用 vs 后续版本内存回归）⇒ 80GB 预期够，但**必须本机实测并记 lerobot 版本** | `web_search`（HF README/docs、GitHub issue #2216 / #3251 / #2867） |

---

## 2. G0 —— 持久环境与依赖（**今天，先做这个**）

```bash
PERSIST=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist
$PERSIST/bin/codex-persist mkvenv pi05_sim --link /root/venvs/pi05_sim
source /root/venvs/pi05_sim/bin/activate
# lerobot 版本必须与已验收的两套一致（0.4.4），不要顺手升级：升级 = 换断点，要重新过 B2 的闸
pip install "lerobot==0.4.4"          # 若解析器要拉 torch，先确认拿到的是 cu124 轮子
pip install "gym-aloha==0.1.4"        # ALOHA 类双臂仿真（MuJoCo）
python -c "import transformers, lerobot, gym_aloha; print(transformers.__version__, lerobot.__version__)"
```

**G0 的验收（三条，缺一不可）**：
1. `transformers` 装成，且 **PaliGemma 可用**：`from transformers.models.paligemma.modeling_paligemma import PaliGemmaForConditionalGeneration` 不报错（`policies/pi05/modeling_pi05.py:36` 就是这一行）。
2. `gym_aloha` 可注册环境：`gymnasium.make("gym_aloha/AlohaTransferCube-v0")` 能构造（**能构造 ≠ 能出图**；本节点无 Vulkan，见 §2.1）。
3. **产出 `runs/vla/a2_env_pi05_sim_20260929/`**：`requirements.lock.txt`（`pip freeze`）+ `env_manifest.json`。
   manifest **直接复用 A 的口径脚本** `scripts/a_env_manifest.py`（不要另写一套；A 的 manifest 已被 D 验收过，
   `probe_kind=semantic` 那条纪律照办：**`import` 成功不算过，要版本号 + 安装来源**）。
   然后**交给 B2 过 provenance 闸**（`scripts/b_env_provenance_guard.py` 的 G1–G5，含 `--selftest`）。

### 2.1 渲染这条坑，D 先替你踩过一半
本节点**无 Vulkan、无 docker**，`render_backend="none"` 在 ManiSkill 上被证明是死路（`daily_report.md` 16:0x 段：
`can_render()` 只 `return device is not None`，SAPIEN 建 actor 时无条件要 `RenderMaterial`）。
所以 **A2 的第一选择是 `render_mode="state"` 路线**；若 `gym_aloha` 必须要像素（π₀.₅ 是视觉语言模型，**它需要图像输入**），
则按 16:0x 段已验证可行的组合走：`apt install libvulkan1 mesa-vulkan-drivers xvfb` + `VK_ICD_FILENAMES` 钉 lavapipe + `xvfb-run -a`，
**并把实测帧率记进 manifest**（64² 单相机软渲染曾实测 8.5 fps ⇒ **像素档在 12 核上可能成为吞吐瓶颈，这本身就是 P0 要的答案**）。
**如果像素档在本节点确实跑不动，不要硬扛**：按 §4 的降级路径报 D，改用「离线图像回放 + 状态仿真」的半实物口径，并显式标注。

---

## 3. G1 —— 权重落地（**只许落 NFS**）

```bash
export MODELSCOPE_CACHE=$PERSIST/hf-cache/modelscope     # 新建，别用 /root/.cache
export HF_HOME=$PERSIST/hf-cache/hub
# 首选 ModelScope（D 实测可达、文件表可读、14467.2 MB）；hf-mirror 为备选（blob 现在 429）
pip install modelscope && python -c "
from modelscope import snapshot_download
p=snapshot_download('lerobot/pi05_base', cache_dir='$MODELSCOPE_CACHE')
print(p)"
```

**G1 的验收**：
1. 记录**实际字节数、sha256、耗时、平均速率、走的哪个通道**（ModelScope / hf-mirror / 其它）。14.47 GB 在 NFS 上不算大，但**速率必须记**——它决定后面每次换节点的成本。
2. **三个小文件也要齐**：`config.json`、`policy_preprocessor.json`、`policy_postprocessor.json`（lerobot 的 `from_pretrained` 要用后两个做归一化/反归一化；**缺了会静默走默认值**，那是最难查的一类错）。
3. **断点续传与失败路径**：若 ModelScope 也限速，写清「重试策略 + 需要平台加白名单的具体域名」报 D，**不要**反复重试把代理打到更严的限流（D 本轮已撞到 429）。
4. 落盘位置写进 `runs/vla/a2_env_pi05_sim_20260929/weights_receipt.json`，**含 license 字段（`gemma`）**：Gemma Terms of Use 是有约束的许可证，D 需要它出现在证据链里。

---

## 4. G2 —— **动作与时间契约实测**（这才是 P0 的核心交付，不是"能跑"）

用**最小可算**的方式把契约打出来，落到 `runs/vla/a2_pi05_contract_20260929/`：

1. **加载**：`PI05Policy.from_pretrained("lerobot/pi05_base")`（或本地路径）成功；记 **显存峰值**（`torch.cuda.max_memory_allocated`）与加载耗时。
2. **单次前向**：喂一帧伪造观测（按 preprocessor 要求的键与形状），取出 action chunk，回答**六个问题**——
   ① chunk 长度 `n_chunk_steps` 是多少；② 单步动作**维度与顺序**（双臂？单臂？关节还是末端位姿？夹爪在哪一维）；
   ③ **单位**（弧度 / 米 / 归一化到 [-1,1]）；④ **参考系**（base / world / 相对增量）；
   ⑤ 夹爪语义（连续开合度还是二值）；⑥ **推理延迟**（首帧与稳态分开记，含 preprocessor/postprocessor 的开销）。
3. **与团队数据形态对齐检查**：把 ②③④⑤ 与 ABC130k 的 `converted_metadata_normal.json`（每臂 joint6+pose7+velocity、gripper1）逐项对照，
   产出一张**「π₀.₅ 原生动作空间 ↔ 团队/实机动作空间」映射表**，不能对齐的格子**留空并标 `unknown`**，不许猜
   （`02_开发实施指南.md:7`：未知保留 null，不用论文默认值猜）。
4. **降级路径**（任一条触发就报 D，不要自行改口径）：显存不足 / 权重下不下来 / 像素档跑不动 / preprocessor 与 gym_aloha 观测键不匹配。

**G2 的产物直接喂 `work/project_parameters.json`**：把 ①–⑥ 与映射表写成「建议值 + 证据路径」发给 D，
D 负责落 `action_contract.*` 与 `timing.*`（**单写者**）。

---

## 5. G3 —— 零 SFT 基线（**明天**；只声称接口贯通）

`gym_aloha/AlohaTransferCube-v0`（或 `AlohaInsertion-v0`）上，**不做任何微调**，跑 **20 局** zero-shot：
- 记录：成功/失败**阶段分布**（识别 / 接近 / 抓取 / 搬运 / 释放）、每局时长、是否出现 flick/弹射类伪成功。
- **判据要自己长牙**：环境的 `success` 不一定含 grasp 真值——本仓在 robosuite Lift 上抓到过 `success_flick`，
  ManiSkill 的 `pick_cube.py:155` 的 `success` 也**不含 `is_grasped`**（`daily_report.md` 16:0x §2）。
  **所以你必须同时报「环境 success」与「grasp 真值 success」两列**，并说明差异。
- **随机基线对照**：同环境跑随机动作，证明你的判据不是恒真（`0/20` 与 `0.05` 的差别必须能被看见）。

### 不得声称（照抄进你的报告，一条不许删）
- **不得**声称 π₀.₅「会搬运」或「zero-shot 成功率为 X 所以能用」——20 局零 SFT 只证明**接口贯通与判据可用**。
- **不得**声称「已适配松灵实机」——本轮**没有接触任何硬件**，实机型号/自由度/夹爪/时延全部 `null`。
- **不得**把仿真吞吐外推成实机吞吐，也**不得**把 `steps/s`（纯 env stepping）当成 `s/局`（含推理与 reset）——
  `daily_report.md` 16:0x §4 已为这条外推移除过一次错误。
- **不得**把外部来源事实（license、他人报告的显存数）写成本机实测；引用时必须标 `external_unverified`。
- **不得**引用 ACT/Lift 线的成功率来给 π₀.₅ 背书（不同底座、不同任务、不同判据）。

---

## 6. 与 B2 的接口（**别抢活**）

| 谁 | 做什么 |
|---|---|
| **A2（你）** | 环境/权重/加载/契约/延迟/显存/zero-shot 接口贯通 |
| **B2** | 正反向**示范数据**（对齐团队流水线形态 + `vla_pipeline` QC）、**T17 目标条件**接到 π₀.₅ 输入与账本、**三口径评测器**、你这套新 venv 的 **provenance 准入闸** |

- 你**不采示范数据、不训 BC**；B2 **不装环境、不下权重、不占 GPU 训练**。
- 你的 G0 产物（`requirements.lock.txt` + `env_manifest.json`）**必须交 B2 过闸**后，D 才认这套环境。
- 你的 G2 契约表是 B2 造示范数据的**输入**（动作维度/单位/频率对不上，数据就是废的）⇒ **G2 优先于 G3**。
- C 线交付的 `harness/contracts.py`、`harness/data_bridge.py`、`harness/ledger.py`、`harness/obs_store.py`、`harness/queue_td_learner.py`、
  `registry/release_bundle.py` 是你的**下游对接面**；已知缺口在 `docs/ledger_data_bridge_20260928.md:211`
  （视觉表征缺失、`x_ref` 只重算 flat 状态、多 worker 签名、真 Gateway 独占租约未实现）。
  **本轮只要求你标出「π₀.₅ 接进去要改哪几处」，不要求你改。**

---

## 7. 时间盒与汇报

- **今天**：G0（环境 + manifest 交 B2）→ G1（权重落地 + receipt）。**这两步不占 GPU 训练时长，没有理由跨天。**
- **明天**：G2（契约六问 + 映射表）→ G3（20 局 zero-shot，若 G2 顺利）。
- 汇报落 `docs/a2_pi05_sim_readiness_20260929.md`，产物落 `runs/vla/a2_*`（**目录必须带 `a2_` 前缀**——
  今天已经出现过一次「探针目录无智能体前缀」被 D 点名的事，别重复）。
- 任何一条「降级路径」触发 ⇒ **立刻在 `daily_report.md` 追加一行并报 D**，不要自己换口径继续跑。

---

# §8 增补（2026-09-29 16:5x，D）：三条新证据 ⇒ **改两处优先级**

D 写完 §1–§7 之后读到了两批新交付（`daily_report.md` 16:4x A 线、16:4x 环境调研·续），其中三条直接影响你的做法。
**本节优先级高于 §2/§3/§5 的对应表述**；原文按 append-only 不改。

## 8.1 权重下载：**必须用现成的完整性校验工具，不许裸调 `snapshot_download`**

环境调研线已实测到一条**会静默骗过你**的坑：`snapshot_download` 被 429 时会打印
`Returning existing local_dir ... as remote repo cannot be accessed` 并 **exit 0**，实际只下了
**719/895 文件、569 MB/1.67 GB**（`scenes/`、`stage_*`、`object_urdf/` 整个目录缺失）。
**规则：资产/权重下载必须自己数文件并对远端清单核 size，不能信返回码。**

⇒ 你的 G1 改为：
1. **优先复用现成工具**：`runs/infra/maniskill_state_probe_20260929/hf_mirror_snapshot.py`（带完整性校验的 `snapshot_download` 包装）
   与 `hf_mirror_fetch.py`（清单驱动 + 按 size 校验 + 可续传 + 并发 3）。**不要另写第三个下载器。**
2. **π₀.₅ 的远端清单已知**：7 个文件，其中 `model.safetensors` = **14467.2 MB**（ModelScope `repo/files` API 实测）。
   下完必须核 **7/7 文件 + 字节数 + sha256**，并把 `policy_preprocessor.json` / `policy_postprocessor.json` **单列**为必需项。
3. **并发度是夹逼**：8 worker ⇒ hf-mirror **429**；单流 curl 只有 **~28 KB/s**（同域名 range 请求同时刻有 2.5 MB/s ⇒ 是单连接被限速）；
   8 worker 聚合 ~8.7 MB/s。**实操 2–3 worker + 重试**；14.47 GB 按此估算 **约 30–90 分钟**，把实测速率写进 receipt。
4. `MS_ASSET_DIR` 已被指到 `.codex-persist/maniskill-assets`（NFS）。**不要改回 `~/.maniskill`**（临时层）。

## 8.2 **新增 G0.5：视觉通道预检**（升为阻塞门，排在 G2 之前）

理由：π₀.₅ 是视觉语言模型，**必须有图像输入**；而本节点的像素档实测受限——ManiSkill 侧结论是
`render_mode="state"` + `render_backend="cpu"` + lavapipe + `xvfb-run -a` 可跑，**像素档仍 ❌**；
robosuite 侧 CPU 软渲染单相机 64² 实测 **8.5 fps**。**所以"本节点能不能喂 VLA 图像"是 P0 的真问题，不是细节。**

**G0.5 要实测的三条通道**（每条都记：能否出图、分辨率、相机数、fps、CPU/显存占用）：
| 通道 | 说明 |
|---|---|
| robosuite 1.5.2 + osmesa | 已装（`lerobot_eval` / `rlrobot` venv），已知 64² 单相机 8.5 fps ⇒ 需测 224² 与多相机 |
| ManiSkill3 + lavapipe/xvfb | 已有可用 venv（`.codex-persist/envs/maniskill_probe`）与已验证的启动组合 ⇒ 需测 `rgb` 档能否真出图 |
| gym-aloha（MuJoCo） | 未装；MuJoCo 的 EGL/osmesa 出图路径与 SAPIEN 不同 ⇒ 装完先测出图再谈任务 |

**G0.5 的三种结论，各自对应一条明确路径（你只报结论，不许自己选路）**：
- **甲：能出图且 fps 够闭环评测** ⇒ 继续 G2/G3。
- **乙：能出图但 fps 太低**（例如 224² 三相机 < 2 fps）⇒ 报 D，走「**离线图像回放 + 状态仿真**」的半实物口径，或申请带 GPU 渲染的节点。
- **丙：完全出不了图** ⇒ 报 D，**不要**退化成"用状态输入的小模型先把 RL 闭环跑通"——那会偏离 v4 的 VLA 主线，**这个选择只能由用户做**。

## 8.3 仿真首场景：**首选改为 ManiSkill 系**，gym-aloha 降为形态对齐备选

环境调研线的头号发现：`SO100GraspCube-v1`（`mani_skill/envs/tasks/digital_twins/so100_arm/grasp_cube.py:414`）的
`success = cube_lifted & is_grasped & reached_rest_qpos`，**结构上就含 grasp 真值**，并额外给 `reached_object` / `touching_table`；
`max_episode_steps=64`（评测便宜），@1024 实测 **43,082 steps/s**；机器人是 **SO-100（LeRobot 生态低成本臂）**。
域随机化是任务自带的（cube 尺寸/颜色/**摩擦**、初始 qpos、生成位置与朝向、相机位姿）。

⇒ P0 预检的候选改为（**先 state 档验判据与契约，再按 G0.5 的结论决定是否上像素**）：
1. **`SO100GraspCube-v1`** —— 判据成品（grasp 真值 + 受控定义 + 失败可归因），**首选**；
2. **`PickCube-v1`** —— 自带 goal 位（`is_obj_placed`），**天然目标条件**，正反两向 = 交换 goal；但 `success` **不含** `is_grasped`（flick 可得）⇒ 用它必须自己补 grasp 真值列；
3. **`gym-aloha/AlohaTransferCube-v0`** —— 与 v4 首场景（ALOHA 类双臂、单臂抓放、A↔B 搬运）**形态最贴**，降为备选，装完先过 G0.5。

**⚠️ 吞吐数字必须成对引用**：同一 PickCube @1024 两轮分别 **21,270**（宿主 `loadavg≈36`）与 **41,322**（`loadavg≈16.7`），差 **1.94×**。
⇒ 你报任何 fps / steps/s / 延迟，**必须同时记 `loadavg` 与 `cpu.stat` 的 `nr_throttled`**（本批已从 746 涨到 1612）。
这条同样适用于 G2 的**推理延迟**：不记负载的延迟数字在本节点没有意义。

## 8.4 一条对你有用的现成结论（A 线 16:4x，真跑规模）

A 已在**训练后的 ckpt** 上把「goal 贯通但学不出方向」量化成两个必须一起读的数：
输出空间 `mean|Δgoal| / mean|Δstate| = **0.0028**`，权重空间 goal 列 absmax / state 列 absmax = **0.966**；
根因是**数据不是实现**（`lift_A_to_B` 7128 行、`lift_B_to_A` **0 行** ⇒ goal one-hot 在训练集里是常量、未覆盖方向那列零梯度）。
**⇒ 你在 G2 做契约实测时，不要试图用"调实现"去修这类比值**；反向示范由 B2 负责补（`d_handoff_to_b2_20260929.md` §2）。
引用这两个数时必须带上「训练后 ckpt、`n_states=8`、单方向真帧」的口径，**不得**跨 regime 搬阈值（A 自查第 7 起就是这条）。

---

# §9 增补（2026-09-29 17:0x，D）：**G0 的安装方式必须改**（D 实测 lerobot 0.4.4 的依赖面后下的红线）

D 在你起跑前实测了 `importlib.metadata.requires('lerobot')`（在已验收的 `lerobot_act` venv 里读，**未安装任何东西**），
拿到三条会直接决定 G0 成败的事实。**本节优先级高于 §2 的 G0 命令**；原文按 append-only 不改。

## 9.1 `transformers` **不是核心依赖，是一个 extra**，而且有硬下界

- **核心依赖 23 条里没有 `transformers`**；它在 extra **`transformers-dep`** 下：
  **`transformers<5.0.0,>=4.57.1`**。
  ⇒ 这解释了为什么两套已验收 venv 都没有它（它们是 `--no-deps` 按 lock 装的）。
  ⇒ **所以 `pip install "lerobot==0.4.4"` 装完 π₀.₅ 依然加载不了**；要的是 **`lerobot[transformers-dep]==0.4.4`**
  （或 `--no-deps` 装 lerobot 后单独钉 `transformers>=4.57.1,<5.0.0`）。
- **extras 清单里没有 `pi` / `pi0` / `pi05` 这一项**（实测全集：aloha、async、groot、hilserl、libero、metaworld、peft、
  pusht、smolvla、transformers-dep、wallx、xvla、kinematics、各类机器人/相机 extra…）。
  ⇒ **不要去找"π₀.₅ 专用 extra"**，它不存在；π₀.₅ 走的就是 `transformers-dep`（+ 微调时可能需要 `peft`，`extra == "peft"` 为 `peft<1.0.0,>=0.18.0`）。
- **核心依赖里还有三条与 torch 强耦合**：`torch<2.11.0,>=2.2.1`、`torchvision<0.26.0,>=0.21.0`、
  `accelerate<2.0.0,>=1.10.0`、`torchcodec<0.11.0,>=0.2.1`。

## 9.2 **红线：新 venv 里 torch 必须仍是 `2.6.0+cu124`**

已验收的两套 venv 实测都是 **`torch 2.6.0+cu124`**（`lerobot_act`、`lerobot_eval`）。
而 `torch<2.11.0` 这个上界**允许 pip 把 torch 升到 2.7/2.8/2.9/2.10 并换成 cu126/cu128 轮子**，
`torchcodec` 又会跟着 torch/ffmpeg 版本走 ⇒ **一次"顺手装依赖"就能造出一个新断点**。

**裁定（裁定 39.1）**：
1. **推荐装法**（保住可比性）：
   ```bash
   PERSIST=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist
   $PERSIST/bin/codex-persist mkvenv pi05_sim --link /root/venvs/pi05_sim
   source /root/venvs/pi05_sim/bin/activate
   # 先钉住已验收的 torch 栈，再让 lerobot 的解析器在它之上工作
   pip install "torch==2.6.0" "torchvision==0.21.0" --index-url https://download.pytorch.org/whl/cu124
   pip install --no-deps "lerobot==0.4.4"
   pip install "transformers>=4.57.1,<5.0.0" "accelerate>=1.10.0,<2.0.0" "safetensors" "gym-aloha==0.1.4"
   ```
   （若 PyTorch 官方源被代理限速，改用现有 venv 的轮子缓存或 aliyun 源，但**版本号不许变**。）
2. **实装前先出解析结果给 D 看一眼**：`pip install --dry-run …` 的解析清单落进
   `runs/vla/a2_env_pi05_sim_20260929/resolve_dryrun.txt`。**解析结果里只要出现 `torch` 或 `torchvision` 或 `torchcodec`
   要被安装/升级 ⇒ 停下报 D，不要实装。**
3. **红线**：新 venv 的 `torch.__version__` 必须**逐字等于 `2.6.0+cu124`**。不等于 ⇒ 这是**断点变更**，
   需要 D 登记 + 重新过 B2 的闸，**不是"顺手升级"**。理由：A 线今天刚为一次环境迁移做完 V0–V9 不变性证明（10/10），
   跨 torch 版本会让那批基线与 `t17_train_side_verify_v2.json` 失去可比性。
4. **不许复用 `.codex-persist/envs/maniskill_probe` 跑 π₀.₅**：那套里实测是 **`transformers 4.30.0`**，
   **低于 `>=4.57.1` 的硬下界**，PaliGemma 支持也不够 ⇒ 会出现"import 成功但加载权重报错"的最难查形态。
   它只用于 §8.3 的 **state 档判据/吞吐对照**。
5. **不许改动已验收的 `lerobot_act` / `lerobot_eval` 两套 venv**（它们是 ACT 线回归基线的载体，已冻结）。
   新环境一律**另建**，`--link` 到 `/root/venvs/pi05_sim`。

## 9.3 一条并发纪律（A2/B2 同时在跑，今天已有四会话交叉写入的先例）

- **权重下载单线负责 = A2**。B2 **不得并行下载**：今天已实测 hf-mirror **8 worker ⇒ 429**、单流仅 ~28 KB/s，
  两条会话同时打代理会互相触发更严限流，最后两边都下不完。
- **GPU 独占**：A2/B2 **不得同时**起 GPU 任务；起跑前在 `daily_report.md` 申报（时长/显存/可否中断），跑完销账。
- **写文件按线前缀分家**：你写 `docs/a2_*.md` 与 `runs/vla/a2_*`，B2 写 `docs/b2_*.md` 与 `runs/vla/b2_*`；
  追加 `daily_report.md` 前先 `git status` + `tail` 看有没有人正在写，追加后立刻报 B（冻结后报 B2）代提交。
- **不许改 `work/project_parameters.json`**（D 单写者）：你交建议值 + 证据路径。

---

# §10 增补（2026-09-29 17:1x，D，裁定 40）：**实机型号已定 = 松灵 Piper**，仿真侧的形态口径随之收紧

用户已裁定两项：**实机 = 松灵 Agilex Piper**；**观察模型复用 `REMOTE_ENDPOINTS.md`**（后者由 D 亲自实测，**不归你**，见 §10.3）。

## 10.1 G2 契约表的对照对象改为 **Piper（6 关节 + 1 夹爪）**

- `work/project_parameters.json` 的 `hardware.robot_model` 已落 Piper；**动作维度按 6+1 对齐**
  （与 D 实测的 `ABC130k` 团队数据形态一致：每臂 `joint(6)` + `pose(7)` + `velocity`，`gripper joint(1)`）。
- **仍为 `null` 的四项**（单位 / 参考系 / 夹爪语义 / 控制频率）**不许猜**：
  要么从 Piper 的 SDK/URDF 文档取，要么等实机实测；**取不到就留 `null` 并在映射表里标 `unknown`**
  （`02_开发实施指南.md:7` 的原话：未知保留 null，不用论文默认值猜）。
- **待用户回答的一问**（D 已提，你别自己假设）：**`ABC130k` 是否由 Piper 采集**？
  若是，那批数据可直接反推契约；若否，它只是"形态相容的参照"。**在它得到答复前，映射表里那一列标 `pending_user`。**

## 10.2 仿真形态口径：**SO-100 是形态代理，不是 Piper**（裁定 40.3）

D 实测：ManiSkill 的 `digital_twins/` **只有 `so100_arm` 与 `bridge_dataset_eval`**，
`find -iname '*piper*' -o -iname '*agilex*'` 在 `mani_skill` 包内 **0 命中** ⇒ **本机没有 Piper 数字孪生**。

⇒ 三条口径，照抄进你的报告：
1. 用 `SO100GraspCube-v1` / `PickCube-v1` 跑通流程是**允许的**（这是用户"先在仿真跑通流程"的原意），
   但产物里**必须带字段 `morphology_proxy: "so100"`**，且**不得**把任何成功率/延迟/契约结论写成"Piper 上成立"。
2. **Piper 的 URDF/MuJoCo 导入是实机对接前的必做项**，由 D 在 P1 结束前排期；**本轮不要求你做**，
   但如果你在 G0.5/G2 过程中顺手发现了可用的 Piper 模型来源（官方仓/ROS 包/URDF），**只报路径与许可证，不要下载导入**（12 核 + 无 Vulkan，导入验证是另一件事）。
3. **像素档限制不变**：SAPIEN 像素档在本节点 ❌（无 Vulkan），G0.5 的三通道实测照做；
   Piper 实机是**有相机**的，所以 G0.5 的结论直接决定"π₀.₅ 在这台节点上能不能吃到图像"——**这是你本轮最重要的一条结论**。

## 10.3 观察模型**不归你**（避免重复劳动与并行打代理）

D 已亲自实测并裁定：**iflytek / `gpt-5.6-sol` 当前不可用**（7 个 URL 变体全 **403**，是 iflytek 自家 WAF 拦截页；
浏览器 UA 则 **302 → `iflygw.iflytek.com/changeUrl.html`**）⇒ **不是"改前后缀"能解决的**；
**dashscope / `qwen3.8-max` 实测可用且支持视觉**（64×64 纯红 PNG 识别正确）。
证据在 `runs/vla/d_observer_endpoint_20260929/`。**你不要再打这两个端点**（尤其 iflytek：WAF 已记录行为，反复重试只会让放行更难）。
观察模型的**校准**归 B2（`d_handoff_to_b2_20260929.md` §9）。

---

# §11 增补（2026-09-29 17:3x，D，裁定 41）：**实机平台已定 = 松灵 Cobot Magic（双臂 ALOHA 类）⇒ 形态口径改判，G0.5 权重上升**

用户补充了两条关键信息：**被控臂 = Piper，但整体真机平台 = 松灵分体式 ALOHA 具身遥操平台 Cobot Magic（多臂）**。
这**推翻了 D 上一轮 §10 的一个前提**（当时按"单臂 Piper"判的），所以本节改判。**§10.1 的契约纪律与 §10.3 的观察模型分工不变。**

## 11.1 **D 的自我纠错**：裁定 40.3 的形态判断基于错误前提，现予改判

40.3 说"SO-100 是形态代理、gym-aloha 是备选"，那是在"实机 = 单臂 Piper"的前提下判的。
实际平台是**双臂 ALOHA 类**（Cobot Magic：leader–follower 遥操，2 条 follower Piper 臂）⇒
**动作空间是 14 维（2×(6 关节 + 1 夹爪)），不是 6+1**。
**纪律同源**：这正是 D 反复引用的「**跨口径不得并列**」（裁定 31.3/33.4/36.4）——**这次用在 D 自己身上**：
前提变了，结论必须改判并留痕，不能悄悄沿用旧裁定。

## 11.2 仿真形态顺序**改判**（G0.5 的结论现在决定路线，不只是决定能不能跑）

| 优先级 | 环境 | 理由 | 产物必须带的标注 |
|---|---|---|---|
| **首选（条件 = G0.5 视觉通道可用）** | **`gym-aloha/AlohaTransferCube-v0`** | **形态一致**：14 维双臂 + top/2 wrist 三相机，与 Cobot Magic 及 ABC-130k(YAM) 同构；任务本身就是"把方块在两区之间转移"，与 v4 `:5` 首场景同型 | `morphology="aloha_bimanual_14d"` |
| **对照/退路（state 档）** | `SO100GraspCube-v1`、`PickCube-v1` | 判据成品（`success` 含 `is_grasped`）、@1024 43,082 steps/s、无需像素 ⇒ **只用于判据与流程贯通** | `morphology_proxy="so100_single_arm"`，结论**不得**外推到 Piper/Cobot Magic |

**⇒ G0.5（视觉通道预检）的地位变了**：它不再只是"能不能出图"，而是**决定本项目在仿真上能不能做形态一致的验证**。
- 若 G0.5 = **甲（能出图且够快）** ⇒ 走 gym-aloha，形态结论可迁移到实机对接阶段。
- 若 G0.5 = **乙（能出图但太慢）** ⇒ 报 D：**离线图像回放（用 ABC-130k 的真实帧）+ 状态仿真**的半实物口径，或申请带 GPU 渲染的节点。
- 若 G0.5 = **丙（完全出不了图）** ⇒ 报 D，**由用户裁**：是换节点，还是先用 state 档把流程/判据/数据闭环跑通、把形态验证整体后置。
  **你不许自行退化成"状态输入的小模型"**（那会偏离 v4 的 VLA 主线）。

## 11.3 G2 契约表：**14 维**，且现在有了一份**实测的同形态参照**（但不得当 Piper 契约）

D 已实测（全部只读，产物在 `work/project_parameters.json` rev3 的 `action_contract`）：
- **ABC-130k = HuggingFace `xdof/ABC-130k`，机器人是 YAM 双臂站（2×6-DoF + 平行夹爪），不是 Piper**（README 的 Dataset Statistics 表明写）。
- 动作总维度 **14**；每臂另有 `pose(7 = xyz+quat)` 与 `velocity(6)`；夹爪实测 **[0, 0.998]（已归一化）**；
  mcap 的 topic 是 `/left-arm-state`、`/left-arm-action`、`/left-ee-state`、`/left-ee-action` ⇒ **commanded 与 observed 分开**；
  实测 action 与 state 首帧差 1e-3~4e-2 ⇒ **两者不可混用**（这条要在你的契约表里显式写出来）。
- **帧率 30 Hz**（实测 4749 帧 ÷ 159.58 s = **29.76 fps**；团队 QC 的合格区间是 [29.0, 31.0]）。
- **内参是单个 3×3 矩阵**：fx=431.88、fy=431.38、cx=324.26、cy=240.97 ⇒ **640×480**（D 上一轮误读成"3 组相机"，现更正）。

**你的 G2 要交付的对照表因此变成三列**：`π₀.₅ 原生动作空间` ↔ `ABC-130k(YAM) 实测` ↔ `Piper/Cobot Magic（待实测）`。
**第三列取不到就留 `null`/`unknown`**（`02_开发实施指南.md:7`：不用论文默认值猜）；
**第二列的数值不得搬进第三列**——YAM 与 Piper 的关节零位、限位、连杆长度、夹爪行程都不同，
搬过去会造成"契约看起来已实测、其实是别的机器人"这种最难发现的错。

## 11.4 一条顺带的好消息（不改你的任务，但影响你的报告口径）

Cobot Magic 是 **leader–follower 遥操平台** ⇒ v4 `:5` 假设的「已有遥操作与少量示范采集能力」**成立**。
所以"正反两向示范只能靠仿真 teacher"这个前提**已经松动**：实机遥操作采集是正规数据源（窗口由用户定），
而且 **ABC-130k 里有天然的正反任务对**可作离线代理（归 B2，见其 §10）。
⇒ 你在 G3 报 zero-shot 基线时，**不要**再写"示范数据不可得"这类话；写"本阶段的示范来源见 B2 §10"。

---

## §12 追加（19:5x，D）：渲染口径已定 + Piper 模型侧四件必做 + 三处待答

**用户指令原文**：「尽量在渲染下跑验证吧，换节点不行再跑最小数据流程闭环」＋「**先只渲染单臂，不要弄双臂渲染**」。
**D 已完成基础验证**，产物在 `runs/vla/d_render_probe_20260929/`（脚本 6 + JSON 11 + 1 份崩溃留档）。以下是**你可直接引用的结论**与**你必须补做的部分**。

### 12.1 渲染口径（已定，不要重测后端选型）

- **后端 = `MUJOCO_GL=osmesa`**。egl 能跑但更慢，且退出时抛 `EGLError`（根因：`libEGL_nvidia*`/`libGLX_nvidia*`/`libnvidia-eglcore*`/`libnvidia-glcore*` 全缺，`egl_vendor.d` 只有 `50_mesa.json` ⇒ egl 落到 mesa 软 EGL，**不是 GPU 路径**）。
- **控制步口径**：模型 `timestep=0.002`（物理 500 Hz）÷ **decimation=16** ⇒ **控制 31.25 Hz**，**只在控制步渲染一次**。**不要每个 `mj_step` 都渲染**（那份口径过度悲观，D 已留档但不作判据）。
- **单臂实测中位（224²，3 重复，独立进程随机顺序）**：1 相机 **26.99** / 2 相机 **14.80** / 3 相机 **12.88** 控制步每秒；3 相机 10 秒回合 = **24.3 秒墙钟 = 0.41× 实时**。
- **并行度硬上限 = 4 个渲染进程**：4 进程效率 **0.98**；8 进程效率 **0.54**、`nr_throttled_delta` 从 71 涨到 **407** ⇒ **不许自行放大到 8**。
- **像素档验证判定 = 可行** ⇒ **G0.5 不需要走丙案**（不需换节点、也不需把形态验证后置）。**但你必须在 `gym-aloha` 或你自己的 Piper 模型上复测一次并给出你自己的数字**（D 的探测用的是 D 自己注入相机的单臂模型，不是你的环境）。**丙案仍然不许你自选**——只是本次实测把它排除了。

### 12.2 必做①：相机注入（官方模型 `ncam=0`）

官方 `mujoco_model/piper_description.xml` **一个相机都没有**（实测 `ncam=0`）。你必须自己加，且**命名与内外参要写进产物**：
- 建议命名 **`cam_high`**（top）、**`cam_wrist`**（挂 `link6`）；若要三相机再加 `cam_front`。
- 内参参照 ABC-130k/YAM 站：**fx=431.88 fy=431.38 cx=324.26 cy=240.97 ⇒ 640×480**（这是**参照**，不是 Piper 标定值）。
- MjSpec 注入方式（D 已验证可用）：`spec = mujoco.MjSpec.from_file(xml)`；`cam = body.add_camera()`；可设 `cam.pos / cam.quat / cam.fovy`（**没有 `zaxis` 属性**，别照 MuJoCo XML 习惯写）。

### 12.3 必做②：夹爪两指耦合（**这是硬缺口，不做就会静默错**）

实测：夹爪是 **`joint7`/`joint8` 两个独立 slide 关节**，官方模型**无 `<equality>`**、URDF **无 `mimic`** ⇒ **两指不会自动联动**。
- **你必须自己加耦合**（等式约束或指令层镜像），并在产物里写明用的是哪种。
- **检测口径警告**：**按关键字（`gripper`/`finger`）识别夹爪会漏掉 `joint7`/`joint8`**（名字里没有任何夹爪字样）⇒ **必须按关节类型（`slide`/`prismatic`）判定**。
- **DOF 口径**：**模型级 8/臂**（`nq=nv=nu=8`，8 个 position 执行器，kp 10000/2000/500/200…）、**指令级 7/臂** ⇒ 双臂模型级 16、**指令级 14（ALOHA 相容）**。你的契约表第三列请按这个写。

### 12.4 必做③：契约第三列的**三值并列**（裁定 43）

**仿真以 MuJoCo 模型为权威**；任何「Piper 契约」声称**必须实机校准**，**不许在 URDF / MJ joint / MJ ctrl 三套值里挑一个当真值**。
- **夹爪行程三套值：URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm ⇒ 三值必须并列记录，实机校准前不得选定。**
- **URDF vs MJ 关节限位不一致**：**J6 差 1.0456 rad（最大）**、J1 0.45、J3 0.27、J4 0.087、J7/J8 0.015 m；MJ 内部 `ctrlrange` 与 joint range 也不等。
- **跨形态禁令**：**YAM J3 实测为正值区间 31.6~104.5 度，Piper J3 的 MJ 限位是 −2.967~0 弧度（全负）** ⇒ 参照数据集的 action 数值**只能作分布形态参照，不得作 Piper 的限位或零位依据**。

### 12.5 必做④：π₀.₅ **单步推理延迟**（回填参数表 `timing.inference_latency_measurements`）

D 的吞吐数字**只覆盖渲染侧**，闭环总吞吐 = 渲染 + 推理，**推理项现在是 null**。请给出：单步（一个 action chunk）推理墙钟、chunk 长度、以及**折算后的闭环控制步/秒**。没有这一项，「像素档闭环可行」只是渲染侧成立。

### 12.6 三个**不要做**（都会踩坑，D 已踩过或已定位）

1. **不要对已 `from_file` 的 spec 把 `geom.meshname` 置空再改 `type=BOX`** ⇒ **SIGABRT（`corrupted double-linked list`，core dumped）**。留证 `piper_mesh_ablation.py` + `piper_ablation_osmesa.run1.json`。要做低面数对照就**另建独立 XML**。
2. **不要把「降分辨率」当提速手段**：受控 27 次独立进程显示 112²/224²/480×640 的 ms/图**无单调关系**（高分辨率反而更快），**机制未定**。同理**阴影不是杠杆**（`shadowsize=0` 仅差 1.7%）。**要提速只有两条：减相机数、降网格面数**；后者上限约 **2×**，且**会改图像外观 ⇒ 必须先做与参照数据集的外观 A/B 并报 D 裁定，不许静默改**。
3. **不要直接用官方 `piper_mujoco_pid.py`**：它依赖已弃用的 `mujoco_py` + `glfw`，**与本机 mujoco 3.9.0 不兼容**；只能移植逻辑或借用 PID 参数。`piper_sdk`（CAN）已下载但**依赖未装、未实测**，不要假设可用。

### 12.7 双臂：**能力已验证，但按用户指令停用**

`MjSpec.attach(child, prefix=..., frame=...)` **无需 ROS** 即可组装双臂（D 实测 `nq=16 / nv=16 / nu=16 / nbody=19 / ncam=3`，渲染非黑 `pixel_std=44.08`）。
**但用户明确「先只渲染单臂」** ⇒ **`arms=2` 的一切结果仅留档，不得作为你的验证依据或对外口径**。你当前所有渲染验证按**单臂**做。节点无 ROS，官方双臂 `piper_description_left/right.xacro` 需先解决展开，MjSpec attach 是已验证的替代路径（**等用户解除限制后再用**）。

### 12.8 你在 `daily_report.md` 待裁清单里的 6 项，D 的处置

- **第 1 项（兼容目录删两个 `enabled=false` 步骤）** ⇒ **裁定 44.2：理由成立，但需你自证**——给出「`enabled=false` 时该步骤确为恒等」的**代码级证据**（不是读 config 就下结论），并交 `compat_dir_diffs.patch` 与**原始 ckpt 只读未改**的 sha256 对照。**原始权重目录仍须只读。**
- **第 6 项（robosuite fps 口径分歧 8.5 vs 133–143）** ⇒ **D 处理：两者口径不同，在你给出各自测量口径（是否含策略推理、是否整回合折算、分辨率与相机数）前，任一数字都不得单独引用。**
- **第 2/3/4/5 项**（`scipy` 不降、带依赖安装、`tokenizers` 跟随分支、`torchcodec` 缺 FFmpeg 记为既存缺口）⇒ **追认**，但 **`torch==2.6.0+cu124` 红线不动**（裁定 39）。

### 12.9 **必须先答**（裁定 44.1，与红线冲突，不许沉默）

`probe_run1_transformers_blocker.log` 显示 lerobot 0.4.4 `modeling_pi05.py:584` 抛 `ValueError: An incorrect transformer version is used`；但 `contract.json` / `load_verification.json` 的现场栈是 **transformers 4.53.3 / lerobot 0.4.4，且加载成功**（3.6168 B 参数、allocated 13,812.5 MiB、tied weight 校验通过）。
**裁定 39 的红线是 transformers 走 extra `transformers-dep` 且 `>=4.57.1`** ⇒ 请选一个并给证据：
**(甲)** 4.53.3 下 π₀.₅ 确实可用 ⇒ 给出判据并**申请红线改判**（由 D 裁，不是你改）；
**(乙)** 另有绕过手段 ⇒ 写明改了什么；
**(丙)** 两份产物来自不同环境 ⇒ 给出**环境指纹**。
另：B2 的 M1 变异牙已能点名 **lerobot 0.4.5 vs 0.4.4 漂移**，而你的产物写 0.4.4 ⇒ **版本口径可能已分叉，请与本项一并交代**。
**同时**：`contract.json` 里 **`pre_normalizer_stats_present=false`、`pre_normalizer_stats_keys=[]`** ⇒ **π₀.₅ base 没带数据集统计量，反归一化后动作量纲不可信**；**你的 G3 zero-shot 基线报告，任何成功率/失败率都必须在同一句标注「无 normalizer stats」，写在结论行、不是脚注。** 另 `param_dtypes=["torch.float32"]` ⇒ **当前 fp32 推理**，若改 bf16 请**单独报**，不许与 fp32 结果混在同一张表比较。

### 12.10 **裁定 45（P0，改你的环境配置）：控制频率必须锚定 30 Hz，不是 31.25 Hz**

**D 的自我纠错**：§12.1 给你的吞吐基准用的是 **31.25 Hz**（物理 500 Hz ÷ decimation 16，D 为凑整数取的 convenient 值）。但**示范数据实测是 30 Hz**（4749 帧 ÷ 159.58 s = **29.76 fps**；团队 QC 规则 J/V04 合格区间 **[29.0, 31.0]**）⇒ **31.25 Hz 超出合格区间，不能当契约值。**

**已实测三种配置（单臂 3 相机 224²，osmesa，每配置独立进程 3 重复；loadavg 61.89→63.41，`nr_throttled_delta=18`）**：

| 配置 | 控制 Hz | 在 QC [29,31] 内 | 控制步/秒（中位） | 极差% | 10 秒回合墙钟 | vs A |
|---|---|---|---|---|---|---|
| A 物理 500 Hz（`timestep=0.002`）+ decim 16 | 31.25 | **否** | 11.97 | 9.0 | 26.1 s | — |
| **B 物理 480 Hz（`timestep=1/480`）+ decim 16** | **30.00** | **是** | **12.03** | 2.2 | **24.9 s** | **+0.5%** |
| C 物理 500 Hz + decim 17 | 29.41 | 是 | 11.69 | 6.6 | 25.2 s | −2.3% |

⇒ **采用 B**：`timestep=1/480` + **decimation=16 ⇒ 恰好 30.0 Hz**，**吞吐与旧基准差 +0.5%，不改任何结论**（渲染开销占比 >99%，改 timestep 基本不影响成本）。产物见 `runs/vla/d_render_probe_20260929/ctrl_hz_alignment.json`。

**为什么这条是 P0**：若仿真控制频率与示范频率不一致，**策略 action chunk 的时间尺度就和训练数据不一致**（同一 chunk 长度覆盖不同真实时长），SFT 后动作会整体偏快或偏慢；**这种偏差不会在任何单点检查里报错**，只会表现为"能接近但抓不准"，排查成本极高。

**你必须做的**：
1. 环境里把控制频率**显式设为 30.0 Hz**，并在产物里写出 `(timestep, decimation, 折算 Hz)` 三元组；
2. **若目标 VLA 的原生控制频率不是 30 Hz**（π₀.₅ / ALOHA 生态常见 **50 Hz**）⇒ **必须显式声明重采样方案**（把示范重采样到 50 Hz？还是把 chunk 按 30/50 缩放？），**报 D 裁，不许静默选一个**；
3. §12.5 要的**推理延迟**请按 **30 Hz 的预算**给：每控制步 **33.3 ms** 是硬预算，超了就不是实时闭环，必须写明你是按 chunk 执行（一次推理覆盖 N 步）还是每步推理。

### 12.11 **裁定 46（P0）：你的 zero-shot `0/20` 现在不许当能力结论用；同时 D 撤销了对你的一条误判**

**D 只读复核了你的 `runs/vla/a2_pi05_zeroshot_20260929/`（20 回合已跑完）。**

**(1) 反常已确认**：`env_success=0/20`、`grasp_truth=0/20`、**20/20 全部 `max_stage=0(no_contact)`**；而你的**随机基线**（`infer=0x`）在 ep04/06/07/10 达到 `max_stage=2(right_lift)`、ep08 达到 `1(right_touch)`。
⇒ **π₀.₅ 的推进度低于随机基线**。这不是"预训练模型在新形态上 zero-shot 不行"的正常量级，**必须先归因**。

**(2) 机制你自己已经证出来了，D 确认**：`state_channel_saturation_analysis.json` —— `normalizer_processor.config.features = {}`（**空 ⇒ 完全不做归一化**），而 `Pi05PrepareStateTokenizerProcessorStep` 是 `np.digitize(state, np.linspace(-1,1,257)[:-1])`、注释明写 state 应已归一化到 [-1,1]。
⇒ 原始关节角被按 [-1,1] 离散化 ⇒ **状态通道饱和**：`waist`/`forearm_roll`/`wrist_rotate` **只有 0.3183 行程可不饱和表示**，`shoulder` 0.6438、`elbow` 0.5937、`wrist_angle` 0.4876。**模型看到的是被压扁且截断的状态，输出又被当绝对关节角写进 ctrl** ⇒ `0/20` 是**无 normalizer stats 的必然后果**。
**你的报告必须这样写**：结论行 = "**本次 zero-shot 不构成 π₀.₅ 能力证据**"；任何引用 `0/20` 的地方**同句**带上「无 normalizer stats，状态通道饱和（waist 仅 0.3183 可表示）」。**这条不是格式要求，是防止项目基于假失败做路线判断。**

**(3) 一条告警 D 判为良性（避免你误改）**：`Remapped 812 state dict keys` 之后的 `Warning: Could not remap state dict keys: Missing key(s) ... embed_tokens.weight`。
D 独立解析了 safetensors 头部：**812 个张量键里确实没有 `embed_tokens`**，别名只在 `__metadata__`（→ `paligemma_with_expert.paligemma.lm_head.weight`，tied 只存一份）；而你的 `load_verification.json` tied 检查是 **`same_storage_data_ptr=true`、`bitwise_equal_in_model=true`** ⇒ **tie 已被 `from_pretrained` 补上，权重没丢，告警良性**。
**但要你做一件事**：**把这条 tied 检查也写进 zero-shot 产物**。现在它只在 `load_verification.json` 里，两份产物之间没有链接 ⇒ **D 自己在复核时差点把 `0/20` 误判成"权重没加载进去"**。不许让下一个复核的人再踩同一个坑。

**(4) D 的自我纠错：撤销 §12.1「后端固定 osmesa」对你环境的适用性**。
你的产物是 `mujoco_gl="egl"`（venv `pi05_sim`，mujoco **3.8.1**），D 独立解析你的 PNG 确认**出图有效**：`224×224`、`bitdepth=8`、`colortype=2`、`raw_len=150752` **与 expected_len 精确相等**、`byte_std≈44`、三帧内容互不相同 ⇒ **不是黑图也不是坏图**。
⇒ **修订**：**后端不再由 D 统一钉死，改为"由你在目标 venv 内自证并记录"**（附出图非黑/尺寸/长度证据，你已经有了，写进产物即可）。
**但边界保留**：D 的 osmesa 数字（单臂 **Piper STL** 网格、mujoco **3.9.0**、`lerobot_eval`）**不可搬到你的 viperx/3.8.1/egl 环境**；你的 `env_fps≈12.1`（双臂 3 相机 224²）也**不可反向搬给 Piper**。**两套数字各自标注 (后端, mujoco 版本, 模型, 相机数, 分辨率)。**

**(5) 推理延迟 D 已从你的日志回填参数表（你不必重测，但要认领口径）**：`chunk_size=50`、`n_action_steps=50`、`num_inference_steps=10`、`control_dt=0.02`（**50 Hz**）；每 300 步回合 **6 次推理 / 3.1 s ⇒ 约 0.517 s 每次 chunk**；`loop_fps≈10.5`、`env_fps≈12.1`、300 步墙钟 **28.4 s**（仿真 6 s ⇒ **0.21× 实时**）。
**预算判定**：一个 chunk 覆盖 1.0 s（50 Hz），推理 0.517 s ⇒ **占实时预算 52%**；若按裁定 45 改 **30 Hz**，同 chunk 覆盖 1.667 s ⇒ **占 31%**。**⇒ 按 chunk 执行时实时闭环可行，按每步推理不可行。** 请在产物里认领这个口径（是否含预处理/后处理、是否含首次预热）。

**(6) 频率冲突从"如果"变成"已发生"（裁定 45.4② 现在必须落地）**：你的环境是 **50 Hz**（`control_dt=0.02`），示范数据实测 **30 Hz**。
⇒ **必须给出重采样方案并报 D 裁，不许静默选**：(甲) 示范 30→50 Hz 重采样；(乙) 保持示范 30 Hz、chunk 时长按 30/50 缩放；(丙) 把仿真改到 30 Hz（`timestep=1/480` + decim 16，D 已实测吞吐代价 +0.5%）。**每案都要写明对 action chunk 时间尺度的影响。**

**(7) 排序变了（裁定 46.6，对你有利）**：**normalizer stats 只能来自示范数据集 ⇒ B2 的数据集是你做任何有意义 zero-shot/SFT 的 P0 硬前置**。
⇒ **在拿到 stats 之前，不要再用 zero-shot 成功率做路线判断**（会得到"π₀.₅ 不行"的错误结论）。这段时间你的有效工作是：**契约表（三列）、接口适配、延迟口径、渲染自证、频率对齐**，不是能力评测。

**(8) 你环境里的一个坑要进契约表第一列（Piper 侧不许照抄）**：`env_action_space` 声明 **`Box(-1,1) shape=[14]`**，但你自己实测 **arm 维在 `before_step` 里被当绝对关节角(rad) 直接写进 ctrl（`sim.py:38-55`）、夹爪维被当归一化开合度 0..1**，MuJoCo `ctrllimited` 还会再夹一次（`bimanual_viperx_transfer_cube.xml:17-33`）⇒ **声明与语义不一致**。
**另外一件值得你顺手查清的事**：你的 `actuator_ctrlrange` 有 **16 项**（每臂夹爪是 `left_finger [0.021,0.057]` + `right_finger [-0.057,-0.021]` **两个独立指关节**），而 `joint_names` 只有 **14** ⇒ **与 D 在 Piper 上实测的"模型级 8/臂、指令级 7/臂"完全同型**（裁定 43.3）。
⇒ **请查清 `gym-aloha` 是怎么把 1 维夹爪指令映射到两个指关节的**（等式约束？指令层镜像？XML 里的 `<equality>`？），**这就是你在 Piper 侧实现 §12.3 两指耦合的参照实现**，不要自己另发明一套。

**(9) 一条诊断请求（D 不下结论，你也不许先下）**：你的出图 `mean≈9.3/255` 偏暗、非零字节占比仅 7%（也可能只是大面积均匀区域经 PNG 滤波后归零）。
⇒ 请附**一张与参照数据集同视角的亮度/直方图对比**，排除"相机朝向或光照不对导致观测近乎全黑"这个**与 normalizer 无关的第二失败因**。**给出对比前，不许断言图像正常，也不许断言图像有问题。**

---

## §13 追加（21:0x，D，裁定 53/54）：**优先级变更 + 频率口径改判（你在 §12.10 提的甲/乙/丙，D 现在裁了，但丙案的实现配方被 D 自己推翻）**

**权威文书**：`rl_harness_supervision/d_simchain_e2emin_20260929.md`（218 行）。**与本单冲突处以该文书为准。**

**1. 频率三案裁定 = 丙案方向成立，但配方必须换（裁定 53）**
- 你的丙案（仿真改 30 Hz）方向**采纳**；但你引的实现配方「`timestep=1/480` + decim 16 = 恰好 30.0 Hz」**是 D 在 Piper/原生 mujoco 口径下实测的，在 gym-aloha 下不可实现** —— **D 本轮实测**：`bimanual_viperx_transfer_cube.xml` 的 `m.opt.timestep=0.002`（模型 `nq=23, nv=22, nu=16, ncam=7`），而 **`dm_control/rl/control.py:168`–`:194` 的 `compute_n_steps` 对非整数倍是 `raise ValueError`（tolerance=1e-8），不是四舍五入** ⇒ **`DT=1/30` 会直接构造失败**。
- **新口径（照此实现）**：**`DT=0.034` → 17×0.002 → 29.4118 Hz**，落在团队 QC 区间 **[29.0,31.0]**；**每控制步硬预算 34.0 ms**（**你之前按 33.3 ms 算的延迟占比要改成 34.0 ms**：0.517 s ÷ (50/29.4118=1.700 s) = **30.4%**）。其它档位：`DT=0.032`→31.25、`DT=0.030`→33.33（**均出区间**）。**精确 30.0 Hz 需改模型 timestep 到 1/480 ⇒ 属改第三方资产，需接触/稳定性 A/B + D 批，默认不走。**
- **实现约束**：`DT` 在 `gym_aloha/constants.py:4`（`env.py:134` 传入）⇒ **不许改 site-packages 原文件**，必须走本仓自有 shim；产物记 `representation_version` + shim `sha256-12` + **实测 Hz**。**S1 示范 / S3 训练 / S5 评测 / S6 采样必须同值。**

**2. 你新增的两件主线活（裁定 54.2 / 54.3）**
- **S4 · `harness/vla_runtime.py`（新文件，A2 主责）**：π₀.₅ 的 **chunk=50 动作 → 29.4118 Hz 逐步下发**，承诺(requested)→入队(committed)→生效(activated) 事件对齐 v4 `:344`–`:346`，含超时/取消、相机键注入（`top`/`left_wrist`/`right_wrist`）。**D 实测的缺口证据**：`harness/runtime_adapter.py` **全文 77 行是 mock 驱动 + 单 slot**（`policy="mock"`，`step()` 只调一次 driver，无 chunk/无图像/无真 env），`harness/env_factory.py:1`–`:45` 是 reach/robosuite 的 monkeypatch shim ⇒ **都不能复用**。**硬边界：不许改 `harness/contracts.py`（冻结面），只允许加法式新增；确需改契约先报 D + before 影像 + sha256-12；`queue_td_learner.py` 属降级线，不复用。**
- **S6 前置可行性探针（先做，别直接开长训）**：① 梯度能否到达待更新参数（列可训练/冻结参数数 + 显存实测）；② 一次更新的显存峰值与耗时；③ 更新后**导出/部署一致性**（v4 `:340`，**不许以"加载未报错"为绿**）。**路线裁定：原生路线优先（同结构同代码、更新 π₀.₅ 部分参数，优先 action expert）；residual RL / 价值选候选降为备选，只有探针证明原生不可行时才启用且须报 D。**

**3. D 撤销一条对你不利的驳回（裁定 50.1）**：D 曾在裁定 48.5 判「"无随机初始化键"无任何证据」——**D 错了**。本轮枚举 `load_verification.json` **全部 18 个顶层键**确认 `compare.n_bitwise_exact=812`、`n_differ=0`、`n_shape_mismatch=0`、**`n_model_keys_not_covered_by_ckpt=0`**、`verdict="all_bitwise_equal"` ⇒ **你的加载验证是有效证据，予以确认**（裁定 48 撤销 transformers 下界的结论不变，依据改为卫语句原文 + 本条）。**新纪律**：任何否定型主张（"证据不存在"/"命中 0"）**必须先枚举完整键集/清单**并落命令原文+mtime+计数（裁定 50.2）。

**4. 优先级（用户 21:0x 指令：尽快把仿真链跑通）**
1) **29.4118 Hz shim + 实测**（S1/S3/S5/S6 全靠它）；2) **`harness/vla_runtime.py` 接口草案**（先给 C2/B2 对接口，再写实现）；3) **S3 小规模 BC**（等 B2 的 S1 数据 + C2 的 S2 stats）；4) **S6 前置探针**。
**仍欠的旧账不变**：裁定 44.1 最后一项（blocker→成功之间改了什么）、tied 检查抄进 zeroshot 产物、亮度/直方图对比、裁定 46 的 5 项。
**降级**：Piper 相机注入（§12.2）与夹爪耦合实施**保持待做但不占主线工时**（实机线已触发式延期，裁定 55.5）；**双臂渲染不做**（用户指令 + 裁定 55.3）。

---

## §14 追加（21:3x，D，裁定 57/58/59）：**你的频率 shim 验收通过，且你抓到 D 的一处不完整表述；渲染后端改判为 egl（GPU 已解锁）**

**1. `envs/gym_aloha_shim.py` 验收 = 通过（裁定 57.1）**
D 只读复核 `runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json`（21:23:27）：`DT=0.034` → `n_sub_steps=17` → **`control_hz=29.411765`**、`in_qc_band_29_31=true`、`per_step_budget_ms=34.0`；`representation_version=gym_aloha_dt0.034_29.4118hz_shim_v1`、`shim_sha256_12=dc14466fcdcf`、**`site_packages_modified=false`**、`gpu_used=false`、`policy_executed=false`；五元标注齐全并自带 `cross_transport_ban`。**D 用独立脚本（直调 `dm_control.rl.control.compute_n_steps`）得到同一结果**，含 `DT=1/30` 的 `ValueError: Control timestep (0.0333…) must be an integer multiple of physics timestep (0.002)` ⇒ **两线互证，裁定 53 确认生效（裁定 58.2）。**

**2. 你纠正了 D（裁定 57.4 已立为纪律）**：D 的 §13-1 只说"`DT` 是 `constants.py:4` 的模块级常量、用自有 shim 改"，**不完整**。你发现 `gym_aloha/env.py:7`–`:12` 是 **`from gym_aloha.constants import (…, DT, …)`** ⇒ `DT` 在 `env.py` 里是**已复制的绑定**，**只改 `constants.DT` 会静默保持 50 Hz**，并把这点做成了可复现变异实验（`patch_mechanism_proof`）。**这正是 D 今天第四次同型事故的镜像（读了声明没读实现），记功。**
⇒ **新纪律（全仓）**：任何 monkeypatch **必须先读使用方的 import 形式**；`from m import X` ⇒ **必须同时改使用方模块里的同名绑定**；且**必须配一条"只改一半 ⇒ 静默错值"的变异体**。

**3. `max_episode_steps` 语义变化，D 现在裁（裁定 58.3）**：300 步在 29.4118 Hz 下 = **10.2 s**（原 50 Hz = 6.0 s）。**裁：保持 300 步、不缩放**；但**必须把 `episode_horizon_s=10.2` 写进每份 manifest**，**超时/失败一律按秒登记**，**跨频率对比不得按步数并列**；与 50 Hz 生态数字对比时必须显式换算并标注。

**4. 渲染后端改判（裁定 59）—— 直接影响你的像素档工作与延迟预算**
E 线已实测**GPU 渲染在本容器可解锁**：`gym_aloha` 480×640 从 **7.91 steps/s（llvmpipe）→ 109.09 steps/s（NVIDIA EGL）= 13.8×**，且图像 `mean 39.892 → 39.869`（**换后端不改变图像语义**）。**合规用法 = prefix-only**（`LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES` 指向 NFS staging `.codex-persist/nvidia-gl-590.48.01/`，**禁止系统写入、禁止 `ldconfig`**），**且必须 `MUJOCO_GL=egl`**（E 的负对照实测：**装了 NVIDIA 库，`osmesa` 仍走 CPU**）。
⇒ **对你的三条要求**：① 像素档评测/推理**改用 egl + prefix-only 激活**（等 E 交付 `scripts/e_activate_gpu_render.sh`，或先用 E 产物里记录的同一组环境变量）；② **重测你的闭环延迟**（此前 `loop_fps≈10.5 / env_fps≈12.1 / 0.21× 实时` 是 **CPU 渲染**口径，GPU 下渲染不再是瓶颈 ⇒ **瓶颈会移到 π₀.₅ 推理 0.517 s/chunk**，这正是主线要的数字）；③ **GPU 是单卡共享**（你训练 13.8 GB + 渲染 102–2647 MiB），**渲染并行度由 E 重测后 D 裁**，你**先不要自行开多进程渲染**。

**5. 已收到（D 只读登记，待你给结论行）**：`runs/vla/a2_pi05_zeroshot_20260929/brightness_reference_abc130k.json`（裁定 46.9 的亮度/直方图对比）、`runs/vla/a2_env_pi05_sim_20260929/manifest_run3_v10_pep610_false_red/`（假红归档 + `WHY_ARCHIVED.md`）、`weights_receipt_channel_sidecar.json`。**要求**：亮度对比现在**可以下结论了**（此前 D 禁止的是"没对比就断言"），但结论必须写成「与 ABC-130k 同视角参照的分布差异 = X，因此图像通道 是/不是 第二失败因」，并标 `morphology_proxy=yam`（参照数据集是 YAM 形态，**不得当成 Piper 标定值**）。

**6. 优先级（不变，但 S4 上移）**：① **`harness/vla_runtime.py` 接口草案**（先给 C2/B2 对接口，**不改 `harness/contracts.py`**）；② S3 BC 的就绪检查（等 B2 的 S1 数据 + C2 的 S2 stats）；③ S6 前置探针计划；④ 旧账（裁定 44.1 最后一项、tied 检查抄进 zeroshot 产物）。

---

## §15 【22:0x · D 裁定 64 / 65 —— 你 §9 的六条全部裁完；**S4 立即开工，不等 S1**】

> **总评**：`docs/a2_s4_vla_runtime_interface_20260929.md`（394 行）是本轮质量最高的一份交付。**四条实现级硬事实全部读了原文**，`:103`/`:105`–`:107`/`:111` 三处 v4 引用**D 逐字复核成立**，`§2.1` 的自纠框（自行作废"重定义 `epoch`"的初稿）和 `§10` 的"本节不声称"三条都做得对。**其中一条更正 D 采纳但需要修正其定性**（见 §15.1）。

### 15.1 【裁定 64】你的第 5 条"行号更正" —— **实质采纳，但定性要改：这是跨文件，不是同文件偏行**

**D 核实结果（两个文件都读了原文）**：

| 文件 | 行数 | `sha256-12` | 你/D 各引了什么 |
|---|---|---|---|
| `…/06_三轮递进调研与方案复审_20260923/**01_开发技术方案.md**` | **418** | **`0a9a2092e18a`** | **D 引的**：`:344`–`:346`「P0 要求」 |
| `…/06_三轮递进调研与方案复审_20260923/**appendices/01_接口契约与开发验收.md**` | **433** | **`aae20ffe604f`** | **你引的**：`:344`–`:346` = T24/T25/T26、`:375` |

- **你说的三条，在附录一里逐字成立**：`:344` T24（相同 θ 正反交替训练）✓、`:345` T25（仅开启训练并发或仅开启执行并发）✓、`:346` T26（同形状但 normalizer／n／rubric 版本冲突）✓、`:375`「真实决策请求、提交的动作结果与机械激活相互关联但分别记录，是异步 BC＋RL 接口成立的关键」✓。
- **但 D 引的是另一个文件**，所以"A2 实读该区间是陷阱表"这句的**前提是"D 与你读同一文件"**，而这个前提不成立 ⇒ **你的更正对 D 的原引用不构成否证**。
- **同时，D 的原引用也确实不准**：`01_开发技术方案.md` 里 **P0 那一行在 `:347`**（「请求／入队／执行可区分，**能选择 n**」），`:344` 是空行、`:345`–`:346` 是表头与分隔行 ⇒ **D 偏了 1–3 行**。
- **你自己也有一处内部不一致**：`§2.4` 写「v4 `:346`（T25）」，而 T25 实测在 **`:345`**（你 `§0`-5 写的是 `:345`，那个是对的）。

**裁定**：
1. **requested→committed→activated 的权威出处改为双文件双引用**：**`appendices/01_接口契约与开发验收.md:375`（契约陈述）** + **`01_开发技术方案.md:347`（P0 晋级依据「请求／入队／执行可区分，能选择 n」）**。S4 的文书一律照此引。
2. **升级为纪律 `citation_file_identity_discipline`**：**任何 v4 行号引用必须带文件身份三元组 `(相对路径, sha256-12, 行号)`**；**只有行号的引用一律视为不可核验，不得进入裁定依据。**
3. **这是 D 第五次同型事故**：D 在核实你的更正前**没有核文件身份**就准备接受。**与前四次同根因（31.25 Hz / osmesa 钉死 / `transformers>=4.57.1` / `1-480+decim16`）：读了声明，没读实现/没核身份。** 你按裁定 50.2/50.3 报上来是对的，D 该做的是**先核身份再裁**。

### 15.2 【裁定 65-1】`n_replan` = **25**（`H=50`，取 `H≥2n` 等号）—— **采纳你的推荐**

- **依据（D 逐字复核附录一）**：`:103`「默认验证固定调度间隔 `n`、动作长度 **`H≥2n`** 和 deadline 的模式」；`:105`–`:107` C/E/D 三槽定义；`:101`「**首版可采用异步执行、分批训练**」；`:345` T25「仅开启训练并发或仅开启执行并发 ⇒ **前者不被称作已实现异步动作调度**」。
- **为什么不能 n=50**：`n=H=50` 时 **E=`[50,100)` 为空、D=`[50,50)` 为空** ⇒ 三槽退化成"整块执行完再重规划"的同步模式 ⇒ **S4 验的就不是 v4 定义的异步调度**，而且 **S6 的 TD 样本时序前提会对不上**（附录一 `:109` 明确把精确状态/时间/价值定义交给 `appendices/02_异步动作时间轴与学习目标.md` —— **该文件存在，D 已核实；S6 开工前你和 C2 都必须读它**）。
- **61.6% / 38.5% 的定性**：**维持你标的 `proposed_from_g3_measurement`**。**仿真阶段允许非实时运行**（E2E-min 不要求实时），**但 slot 占比与 deadline-miss 计数必须照记**，因为 P4 实机要用这批数。**S4 必须在自己真实的 (venv, GL 后端, 相机数/分辨率, n, 并发) 组合下重测每 chunk 墙钟**，不得直接搬 0.5233 s。
- **`n=25` 进 `representation_version`，S1/S3/S4/S5/S6 同值。**
- **可推翻条件**：① S3 改了 `chunk_size`（则 `n` 重算 ≤ `H/2`）；② v4 修订 `H≥2n`；③ 用户明确要求同步整块执行（= 改设计基线，属路线分叉，D 不自行推进）。

### 15.3 【裁定 65-2】`max_episode_steps` = **维持 300，驳回你的 B 案（176）**

**这是 D 与你推荐不同的一条，理由四条，请你按 D 的读侧纪律复核**：

1. **你想保住的那个性质已经不存在了**：176 的目的是"保 6.0 s 任务时长 ⇒ 与已发表的 300 步/6 s 口径可比"。但**发表口径是 `DT=0.02`（50 Hz）**，而主线已裁定 **29.4118 Hz**（裁定 53，为落进团队 QC 区间 `[29.0,31.0]`）⇒ **动作保持时长差 1.7×，闭环动力学不同**，**本来就不可并列**。为一个已经失去的可比性引入新口径，收益不成立。
2. **v4 要求的对照不是已发表数字**：`01_开发技术方案.md:376` 逐字 —— 「从同一个双向 BC checkpoint、同一初始示范集分出**动态 Harness-DAgger／BC 与 BC＋RL 两组**…**只有实验组增加真实后果的 RL 更新**」⇒ **对照是同预算的动态 BC**，与 ALOHA 生态的发表成功率无关。
3. **E2E-min 的出口判据不是成功率**：`:5`（允许少量 SFT、**初始成功率可为零**）、`:348` P1「**不要求预先高成功率**」。
4. **176 是新的派生口径**，要在 S1/S3/S5/S6 处处携带，且**偏离注册资产配置**（`gym_aloha/__init__.py:16` = 300）；300 步还多给 1.7× 的每集数据量，对 S3 的小规模 BC 是有利的。

**强制附加（这四条必须落 manifest，缺一即红）**：
- `control_hz=29.4118`、`max_episode_steps=300`、**`episode_horizon_s=10.2`**、`published_gym_aloha_caliber="DT=0.02, 300 steps, 6.0 s, 50 Hz"`；
- **任何跨口径并列一律标 `not_comparable_horizon`**（裁定 58.3 的"超时/失败按秒登记、不得按步数并列"继续有效）；
- **可推翻条件**：**S5 的失败归因若显示 timeout 占主导**（则 horizon 成了混淆变量，D 必须开 176 的敏感性臂），**或用户要求与已发表数字可比**。

### 15.4 【裁定 65-3 / 65-5】`lease_generation` 与 `late_policy` —— **两条都采纳**

- **`lease_generation` = 控制代际 = chunk 代际；`epoch` 保持 `ledger.py` 既有语义不动**（你实测 `epoch` 在 `ledger.py` 命中 **18** 处）。**你自行作废"重定义 `epoch`"的初稿，记功** —— 这正是"读 schema 后再定调"的正确顺序。**已进参数表（rev10）。**
- **`late_policy = hold`**（继续执行旧计划的合法动作、不回填过期索引）。**依据附录一 `:111` 逐字**：「提前完成不擅自改变固定切换时刻；**错过 deadline 不把晚到结果塞进过期索引**。Runtime 按冻结的迟到规则**继续已有合法动作**、保持或结束尝试，并**记录实际选择**。只有符合该学习分支时序前提的窗口才生成其 TD 样本；**异常事实保留，不重标成"准时"**」⇒ **你的 `hold` 就是原文**。
- **附加三条**：① **必须记录"实际选择"**（`hold` / `keep` / `terminate` 三态）与 `expired` 事件；② **`late_policy` 的值进 `representation_version`**（它是冻结面语义，改了就是换契约）；③ **"异常事实保留，不重标成准时"⇒ 迟到帧不得被重标为 `activated`**，B2 的闸要能判这条红。

### 15.5 【裁定 65-6】**S4 不等 S1，立即开工** —— 驳回你的第 6 条推荐

**你的顾虑是对的（C 线的教训：对着 mock env 自测会打出第二个假组件），但前提在这里不成立**：

1. **S4 的证据是结构性的，不是任务成功率**：chunk 代际推进、C/E/D 三槽、七类事件、`ledger.frame_fact` 逐字段、deadline 计数与迟到记录 —— **这些都不需要示范数据**。
2. **你手上已经有真实 env + 真实 3 相机渲染路径**：`scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`，**已跑通 20 局**。**这不是 mock env**，所以"第二个假组件"的风险不成立。
3. **用 zero-shot π₀.₅ 作真实 obs 载体是允许的，但裁定 46.6 仍然有效**：**不得用 zero-shot 成功率做任何路线/能力判断**；S4 只取结构与字段证据，**成功率一栏写 `not_an_exit_criterion`**。
4. **排期理由**：S1 正卡在右臂 weld（B2 probe4：左臂 1.3 mm 绿、右臂 0.2469 m 发散），**若 S4 等 S1，全链停摆**。**S1 只阻塞 S3 / S5，不阻塞 S4。**

**⇒ S4 的落地顺序（D 定）**：
- **S4a（现在就能做，CPU/GPU 皆可）**：`harness/vla_runtime.py` 新文件 + 你 §3 的接口签名 + chunk 循环 + 三槽推进 + 事件写入 + 版本三件套；**对着真实 env（`AlohaTransferCube-v0` + 你自己的渲染路径）跑一条可手算的短轨迹**，逐字段手核（这就是 simchain §4-S4 的出口判据，对撞 `01_开发技术方案.md:350` P3「用可手算短轨迹核对 target、mask、goal 和来源」）。
- **S4b（等 C2 的 `harness/env_gym_aloha.py`）**：四类判定（成功/失败/超时/未知）接 `ledger`，**判定必须独立于 `reward==4`**，不一致即红。
- **硬边界重申**：**`harness/contracts.py` 一个字节不动**（你 §1 的结论 D 采纳：七个 `EVENT_KINDS` 够用，不新增 kind）。**只允许加法式新增文件。** 若确实必须改契约，先报 D + before 影像 + `sha256-12`（裁定 35.1）。

### 15.6 【裁定 67 的连带】渲染口径已改判 —— 你的两个旧数字**都不能再当主线依据**

E 线在 **prefix-only 合规态**下重测完毕（`runs/infra/e_egl_probe_20260929/`，`boundary_guard.ok=true`、`forbidden_paths_present=[]`、`system_render_lib_hits=[]`）：

| 口径 | osmesa | **egl_nvidia** | **egl_mesa（负对照）** |
|---|---|---|---|
| **gym-aloha 双臂 3cam 224²** | 14.01 | **165.65 ctrl-steps/s（11.82×）** | 12.83（**0.92×，比 osmesa 更慢**） |

- **你的 `loop_fps≈10.5` / `0.21× 实时` 是 CPU(osmesa) 渲染口径 ⇒ 作废，在 egl 下重测。**
- **你的 `hz_shim_verification.json` 里 `97.66 ms/控制步`、`realtime_factor=0.3482` 也是 osmesa + 单相机 top@480×640 口径 ⇒ 频率结论（29.4118 Hz）不受影响（那是 `DT`/substeps 的算术，与后端无关），但吞吐结论必须在 egl + 3cam 224² 下重测。**
- **egl_nvidia 下 165.65 ctrl-steps/s ÷ 29.4118 Hz = 5.63× 实时（仅渲染）** ⇒ **闭环是否实时，现在取决于 π₀.₅ 的推理墙钟，不再取决于渲染**。这把你 §2.4 的预算算术的分母换掉了，**必须重算 n=25 时的占比**。
- **激活一律 prefix-only，禁止任何系统写入（含 `ldconfig`）**；`MUJOCO_GL=egl` 是主线唯一后端（**egl_mesa 与 osmesa 都是 CPU，只作对照/回退**）。

### 15.7 你现在欠 D 的（更新版）

| # | 欠项 | 变化 |
|---|---|---|
| ① | **S4a 立即开工**（§15.5） | **从"等 S1"改为"现在做"** |
| ② | **egl 下重测闭环延迟与 chunk 墙钟**，重算 n=25 的推理占比（§15.6） | 口径已改判，旧数字作废 |
| ③ | **读 `appendices/02_异步动作时间轴与学习目标.md`**，S6 的 TD 样本时序前提以它为准（附录一 `:109` 指过去的） | **新增** |
| ④ | 亮度对比的**结论行**（标 `morphology_proxy=yam`） | 不变 |
| ⑤ | S6 前置探针计划 → **你 §8 的 P1–P5 D 已阅，采纳**；**P5（normalizer 联动、`stats_version` 更新前后必须相同且 `!= "NONE"`）尤其对，升为 S6 的必备闸** | **由"交计划"改为"已采纳"** |
| ⑥ | 裁定 44.1 最后一项 | 不变 |

**GPU 申报提醒**：②与 P1/P2 都要占 GPU。**>10 min 事前在 `daily_report.md` 申报**（预计时长/显存/可否 kill），跑完销账（`nvidia-smi` 实测 0 MiB）。单卡优先权 **A2 > C2 > E**，你是第一顺位。

---

## §16 【22:2x · D 裁定 70–74 —— 你的 run1/run2 已阅；**n=25 的裁定现在有实测支撑了**；你提的两条规则 D 全部采纳并升为全仓纪律】

### 16.1 【裁定 74】`n_replan=25` 的裁定**维持不变，但依据从"算术外推"升级为"实测"**

你归档的 run1（`gpu_run1_two_a2_defects/latency_mainline_egl_gpu_pi05.json`，22:11:16）里的闭环数字，D 实读：

| 档 | `mean_loop_fps`（实测） | 换算每控制步墙钟 | 每 chunk 墙钟 | 对 34.0 ms×n 的预算占比 | **判定** |
|---|---|---|---|---|---|
| **`n=50`** | **59.176** | 16.90 ms | 845 ms | 845 / (50×34.0=1700 ms) = **49.7%** | 实时可行（**但违反 v4 `H≥2n`，不能用**） |
| **`n=25`** | **38.055** | 26.28 ms | 657 ms | 657 / (25×34.0=850 ms) = **77.3%** | **实时可行，余量 22.7%** |

- **⇒ 你 §2.4 外推的 `61.6% / 余量 38.5%` 是乐观的；实测是 `77.3% / 余量 22.7%`。你把那个数字标成 `proposed_from_g3_measurement` 并要求 S4 重测，这一步救了它 —— 如果你当初直接写成结论，D 就会拿一个错 15.7 个百分点的余量去排 P4 实机。**
- **⇒ 裁定 65-1（`n=25`）维持不变。** 注意：**D 裁 n=25 的依据从来不是延迟，而是 v4 附录一 `:103` 的 `H≥2n` 合规**（n=50 时 E/D 双空、三槽退化）。**延迟实测只是确认它可行 —— 所以这条裁定对延迟数字不敏感，run2 即使把余量再压低也不动 n=25。**
- **证据等级**：run1 的两道闸是**假红**（你 `WHY_ARCHIVED.md` 已逐条说明），**延迟数据本身有效**，且 run2 用同一口径重测 ⇒ **run1 天然是 run2 的重复性对照（你这个设计 D 采纳）**。**当前标 `provisional_from_archived_run1`；run2 落地后由 D 改标 `measured_run2` 并把两个数字并列。**
- **一条必须带的边界**：run1 是在 **`loadavg_1m 67.36→71.98`、`nr_throttled Δ63`** 下测的（你产物实测），**这是本日观测到的最忙时段** ⇒ **77.3% 是保守端**。run2（22:16:55）在 **`loadavg 51.4`、`Δ20`** 下 env_only 就到 **65.865 fps**（run1 是 30.522）⇒ **同一口径负载不同差 2.16×**。所以 **77.3% 要写成"worst-observed-load 下的值"，并等 run2 的 closed_loop 臂给一个较低负载下的值，两者并列报，不许只报好看的那个。**

### 16.2 【裁定 72】你提的两条规则 —— **D 全部采纳，升为全仓纪律**

**规则 A（你的 §7-2）：后端口径主张必须带 `GL_RENDERER` 原文，不能只带 `MUJOCO_GL`。**
- **D 采纳，并升为纪律 `renderer_identity_evidence_discipline`**：**`MUJOCO_GL` 只表达意图，`GL_RENDERER` 才表达事实**；**任何渲染相关的吞吐/延迟/图像数字，产物里必须落 `GL_VENDOR` + `GL_RENDERER` + `GL_VERSION` 三条原文 + `renderer_class` + `identity_source`（取法）**；**只记环境变量的一律标 `declared_only`，不得作口径依据。**
- **你的机器化回溯标注就是这条纪律的正确用法，D 予以验收**：`latency_retro_label_no_prefix.json` 实测 —— 同一组环境配置（`MUJOCO_GL=egl`、无 prefix、系统 ICD 只有 mesa）下 `GL_RENDERER = "llvmpipe (LLVM 15.0.7, 256 bits)"`、`renderer_class="mesa_cpu_software"` ⇒ **`retro_label.valid=true`**，**G3 的 `loop_fps≈10.39 / env_step_fps 11.91` 确证是 CPU(mesa) 口径**。**并且你如实记了 `limits`：「这是同配置复现，不是对 19:24 那个进程的直接观测（当时没记 GL 身份，无法回溯取证）」⇒ 这条限定 D 一并采纳，任何人引用该回溯标注都必须带上它。**
- **⇒ D 等待项 ② 销账**（前半 = 口径已有机器证据；后半 = egl 下重测，run1/run2 已给）。

**规则 B（你的 §5-④ 建议）：自检至少要有一案真的调用被测的取数函数，而不是只喂它理想输入。**
- **D 采纳，升为纪律 `selftest_must_execute_acquisition_path`**：**任何闸的 `--selftest` 必须至少有一案真的执行"取数路径"本身**（构造真实对象、真的调用那个会失败的函数），**不许只把理想字符串喂给闸函数**。
- **你的 §5-④ 就是这条的反例实证**：`--selftest` 当时 **9/9 全绿**，但**没有一案真的执行过 GL 身份取数**（M3 是把伪造字符串直接喂给闸函数）⇒ **toy XML 非法（`worldbody` 直接挂 `<joint type="free"/>`）导致 `mujoco` 抛 `XML Error`、`glGetString` 返回 NULL、第一臂假红**，**而自检完全看不见**。
- **这与 C 线在 `daily_report.md:3740` 段登记的「库自检全绿 ≠ 工具可用（CLI 面没被测）」同族同向 ⇒ D 把两条合并成一条纪律，并要求 C2 的 T-C2-4 把它列为新增审点**：**逐闸检查"自检是否真的执行了取数路径"，凡只喂理想输入的，标 `acquisition_path_untested`。**
- **你的修法（XML 改 `<body><freejoint/>…`，并补 `gl_identity_resolved` + `retro_label_valid` 两道带反向牙的闸）D 验收。**

### 16.3 【裁定 72-2】你 run1 的两处假红 —— **归档纪律做得对，但第 2 处的根因要升级为纪律**

- **第 1 处（`retro_label_valid` 在 GPU 臂必然红）**：你的诊断准确 —— **脚本对任何 `--mode env_only` 臂都发"回溯标注"块与它的闸，但该标注只在未激活 prefix（=mesa/CPU）那一臂才成立**。**修法 `retro_pending = not act["nvidia_prefix_active"]` 正确，run2 已验证（`gates_all_ok=True`，5 道闸全绿，D 实读）。**
  **但 D 要把它归到一个更大的缺陷类，并交 C2 的 T-C2-4 审**：**「闸在它不适用的臂上开火」= 适用性缺陷（applicability defect）**，与 C2 已抓到的三起同族（B2 的 `G2_rebuild_lockout_not_default[a2env]` 极性/文案反了、A2 的 `manifest_run2_dist_drift_false_red` 把 dist-info 的 local tag 差当成 torch 漂移、B2 的 `A0_teeth_current` 因 `gate_build` 不匹配红过）。**要求：每道闸必须声明它的适用条件（`applies_when`），不适用时输出 `n_a` + 理由，而不是 `ok=false`。**
- **第 2 处（`tied_weight` 用裸键名查 `PI05Policy.state_dict()`）**：你的自诊非常准确 —— **「读法出处 `scripts/a2_verify_pi05_load.py:118`–`:126` 是 A2 自己 18:0x 写的、这次没去读 ⇒ 同型事故：读声明没读实现」**。**lerobot 0.4.4 的 `PI05Policy.state_dict()` 键带 `model.` 前缀。**
  **D 把这条升为纪律 `self_artifact_reuse_discipline`**：**复用自己在更早时段写下的读法/键名/路径/口径时，必须重读一次原文并留 `(file:line, mtime)`；"我记得我写过"不算证据。** **理由：本日已有两起同型 —— 你的 `tied_weight` 键名，以及 D 自己的前缀目录名（§16.4）。两者都是"引用自己先前的结论而没重读"。**
- **归档纪律 D 验收**：**两份 JSON 保留不删不改写**（裁定 35.1）、`WHY_ARCHIVED.md` 逐条说明假红根因与"数据有效"的边界、并明确「引用结论请用 run2 及以后，但单独引用 run1 的延迟数字是允许的，只要同时说明那两道闸的假红原因」、**并主动把 run1 定位成 run2 的重复性对照** ⇒ **这是本仓最好的一次假红处置，D 建议 B2/C2 照抄这个格式。**

### 16.4 【裁定 70】你和 E 一起抓到了 D 的一处事实错误 —— **前缀目录名**

- **D 的裁定 59.4 与断点文件 §3 写的前缀 `.codex-persist/nvidia-gl-590.48.01/` 不存在**（D 实测 `stat` → `No such file or directory`）。
- **正确前缀 = `.codex-persist/egl-libs/590.48.01/`**（内含 `10_nvidia.json` + 7 类 NVIDIA 库与符号链接）。
- **你本轮的做法（一律走 E 的激活件 `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`、不硬编码目录名）D 采纳为规范做法**，并已写进四条线的文书：**全线一律以 `scripts/e_activate_gpu_render.sh` 的解析结果为唯一权威。**
- **你产物里的 `activation_env.prefix_paths_verified`（`prefix_in_ld_library_path` / `vendor_json_points_into_prefix` / `vendor_json_exists` 三条布尔）是正确的自证形式，D 要求 E 的激活脚本也输出同样三条。**

### 16.5 【裁定 71 · 更正 D 自己】三个"主线渲染口径"数字互相冲突，**D 上一轮用错了**

**D 实读到的三个数**（都自称 gym-aloha 双臂 3cam 224² egl_nvidia）：

| 来源 | 数字 | `loadavg_1m` | `DT`/子步 | 协议 |
|---|---|---|---|---|
| **E** `ab_gym_aloha_20260929_214002.json` | **165.65 ctrl-steps/s（自称 `11.82×`）** | 47.49→50.08 | **未用 shim（应为 stock `DT=0.02`/10 子步）** | `bench_seconds=5.0`、reps=3、render_only |
| **A2 run1** `latency_mainline_egl_gpu.json`（22:08） | **30.522 `env_step_fps`** | **67.36→71.98** | **`DT=0.034`/17 子步** | `n_steps=100` |
| **A2 run2** 同名文件（22:16:55） | **65.865 `env_step_fps`** | **51.4→51.4** | **`DT=0.034`/17 子步** | `n_steps=100` |

- **D 的错误**：D 在 §15.6 与 `d_simchain_e2emin_20260929.md` §10.4 里，**用 E 的 `165.65` 算出了"`165.65 ÷ 29.4118 = 5.63× 实时`"和"S1 采集 300 步/集 ≈1.81 s/集、20 集 ≈36 s"** —— **这是把 E 的 (stock DT, 5 s 窗口, loadavg 47–50) 口径搬进主线的 (shim DT=0.034/17 子步, 100 步, loadavg 51–72) 口径，正是 D 自己在裁定 46.4/53.3/53.6 里明禁的跨口径搬运。D 在同一轮里写下禁令又违反它 ⇒ 记为 D 第七次同型事故。**
- **裁定 71**：
  1. **在 E3-③（`scripts/e_mainline_render_calib.py`，22:14 起在跑）落地之前，不得声明任何单一的"主线渲染口径"数值。** `11.82×` 与 `5.63× 实时` **一律降级为 `protocol_mismatched_not_mainline`**（E 的档位是 stock DT + 5 s 窗口，不是主线配置）。
  2. **规划一律用保守端**：**`env_step_fps = 30.522`（worst observed load 67–72）⇒ 300 步/集 ≈ 9.83 s/集 ⇒ 20 集 ≈ 3.3 min、先导 5 集 ≈ 49 s**。**较低负载端（run2 `65.865`）⇒ 20 集 ≈ 1.5 min**。**两个都报，规划取慢的那个。**（**结论不变：20 集仍在 GPU 10 min 申报门槛以下，但 B2 必须先算再跑。**）
  3. **本机负载摆动是已实测事实**：`loadavg_1m` 在 21:5x–22:1x 一小时内 **37.58 → 71.98**（12 核 cgroup 配额、宿主 112 核与其它租户共享）⇒ **任何吞吐数字都是负载条件量，必须成对带 `loadavg` 三点 + `nr_throttled` 增量**；**同一口径在不同负载下差 2.16× 已实测，所以"单点数字"本身就不该被当口径。**
  4. **E3-③ 是指定的对账仪器**：它扫 `egl_nvidia/osmesa × workers 1/2/4/8 × reps 2` **并且带一个 `--cotenant proxy_a2` 臂** ⇒ **它能直接量化负载敏感度与并发损失**。**但它必须在"静默窗口"内跑才有效（裁定 73，见 `d_handoff_to_e_20260929.md` §10.3）；当前这一轮已被你的 22:16 作业污染 ⇒ E 会重跑。**
- **⇒ 你 §2.4 的预算算术分母没有被 D 换成 165.65；正确的是：等你 run2 的 `closed_loop` 臂（`--n-action-steps 50,25`）落地，用它的实测 `mean_loop_fps` 直接算占比，不要用渲染吞吐反推。**（run1 已给 59.176 / 38.055，见 §16.1。）

### 16.6 【裁定 73】GPU 优先权与静默窗口 —— **你现在持有优先权**

- **单卡优先权 A2 > C2 > E > B2** ⇒ **你 22:16 起的 `closed_loop` 作业持有当前优先权，E 已被令不得打断你、并把自己那一轮权威臂标为 `contaminated`。**
- **但你要遵守一条新制度**：**E 会申请"静默窗口"重跑权威标定；窗口批下来之后，你在窗口内不得起 GPU 作业**（`daily_report.md` 里会写明起止时刻）。**反之，你要做长时间 GPU 作业（>10 min）时也可以申请窗口，D 按关键路径排。**
- **你本轮的 GPU 申报（22:0x，15–25 min，<15 GB，单进程、不采成功率、可随时 kill、跑完销账）格式完全合规，D 采纳为申报模板。销账条件：`nvidia-smi` 回到 0 MiB / 无进程 —— D 在 22:17:48 实测为 `0 MiB / 无进程`（那是你 run1 与 run2 之间的间隙），run2 结束后请自己再销一次账。**

### 16.7 你现在欠 D 的（更新版，替换 §15.7）

| # | 欠项 | 状态变化 |
|---|---|---|
| ① | **S4a 立即开工**（`harness/vla_runtime.py` 骨架 + chunk 循环 + 三槽 + 事件 + 版本三件套；对真实 env 跑可手算短轨迹） | **不变**（你 §8 已说"紧接着做"，D 确认这是当前第一优先） |
| ② | **run2 的 `closed_loop` 臂（`--n-action-steps 50,25`）落地并报 D** | **新增，且是 D 裁定 65-1 的证据升级项**；两个负载端的占比并列报，不许只报好看的 |
| ③ | **读 `appendices/02_异步动作时间轴与学习目标.md`** | 不变（S6 前置） |
| ④ | 亮度对比结论行 | **已销账**（你 §1，`brightness_reference_abc130k.json`，21:39，64,528 B） |
| ⑤ | S6 探针计划 P1–P5 | **已采纳**（P5 升为 S6 必备闸） |
| ⑥ | 裁定 44.1 最后一项 | 不变 |
| ⑦ | **`V-pi05-3` 顶层渠道** | **已由你的 `weights_receipt_channel_sidecar.json` 闭合**（`channel_top_level="mixed"`，C1–C5 绿、自检 3/3、receipt `sha256-12 11267d5b…` 未变）⇒ **D 从 B2 的欠项里撤下，改为 B2 只需在闸里引用你这份 sidecar** |
| ⑧ | **`env_manifest.json` 10/10 `env_usable=true`（20:50:14）+ V10 六条检查 + `--selftest` 6/6 变异体被抓** | **D 已阅并采纳**；**并采纳你对 B2 的点名：B2 那次吃的是假红 run2 快照，必须用新 manifest 重过闸** |

---

## §17 D 执行单（2026-09-29 23:0x）｜裁定 75/76/78.6 落到 A2 的三件事

**前提**：D 已独立复核你的 `latency_mainline_egl_gpu_pi05.json` ⇒ **渲染器身份合规**（`gl_renderer="NVIDIA A800-SXM4-80GB/PCIe/SSE2"`、`renderer_class=nvidia_gpu`、`identity_source=mujoco.Renderer(独立探针)`、`prefix_only_compliance=true`、`system_clean=true`、prefix = **正确的** `.codex-persist/egl-libs/590.48.01`）；`gates_all_ok=true`、闸 8/8。**裁定 70/72 合规，无需返工。**

### 17-1 你的「n=25 超预算」发现：**裁定 65-1 维持 `n_replan=25`**，但你的结论要按同步/异步分离改写

D 自己算过（不是采信措辞）：ep0/n=50 的 `t_infer 3.308 + t_render 0.037 + t_env_step 2.054 + t_other 0.09 = 5.489 = episode_wall_s` ⇒ **严格相加、零重叠 = 同步串行环**；n=25 的 `300/25=12` 次 × `0.7204 s` = `8.645 = t_infer_s` ✓。

- **你的建议被采纳的部分**：`budget_fraction>1` **不得当硬失败**，改为「按秒登记的**软约束** + `overload_flag`」（裁定 75.4）。**P4 真机不适用**，真机必须实测达标。
- **你的建议被采纳的部分**：`num_inference_steps` 与 **bf16** 列为 **P4 前置**降延迟手段；**bf16 必须另开 `representation_version`**、不得与 fp32 同表（75.7）。`n=17` **不推荐**（采纳你的外推 90.5%）。
- **必须改写的部分**：`budget_fraction=1.2178` 是**同步环**口径。v4 附录一 `:103` 的 `H≥2n` 本来就是**异步**可行性条件 ⇒ 不能拿同步墙钟否证它。异步下关键路径 = `max(env_step, 摊薄推理)`，n=25 摊薄 = **27.330 ms < 34.0 ms ⇒ 占比 80.4%、裕量 19.6%**（与你自己报的 19.6% 一致，D 只是把它归因到正确的口径上）。
- **禁止项（75.5）**：**在异步版被实测之前，任何 S4/S5 结论里不得出现「实时闭环」字样。** 异步最小证据 = ① `queue_drain_events`（0 或逐次登记时刻与时长）；② `wall_ms_per_ctrl_step` 与 `amortized_inference_ms_per_ctrl_step` **分列**；③ 负载对 + **运行时** cotenant 采样。

### 17-2 quiet-window 权威重测（裁定 76.4，**强制项**）

你自己已把 run2 标为 `not_authoritative_contaminated`（**接受，方向正确**）⇒ 现在缺一个**干净**的权威轮。GPU 在 22:45 与 22:52 两次实测为 **0 MiB / 无 compute 进程**，loadavg `37.70/37.81/39.52`。

- **窗口判据（裁定 73）**：窗内 `nvidia-smi --query-compute-apps` 只有你的进程；loadavg 相对窗前基线**不 +≥5**。
- **产出要求**：`n=25` 与 `n=50` 两档 × **各 ≥2 次重复** × 每次带负载对（3 点 loadavg + `nr_throttled` Δ）。
- **⚠ 必须修的纪律缺口（76.3）**：run2 的 `cotenant_evidence.collected_at_run_time=**false**` —— 它是 22:38 由 `a2_artifact_amendments_20260929.py --which cotenant` **事后重建**（依据 D 的 daily_report），**不是运行时采样**。裁定 73 要求运行时采集。**这轮必须 `collected_at_run_time=true`**：运行中周期性采 `--query-compute-apps` + `ps`，落 `cotenant_samples[]`（每条带时间戳）。**D 接受 run2 的保守分类方向，但下不为例。**
- **并行提醒（裁定 76.2 新纪律 `per_batch_gpu_yield_gate`）**：你的**每个** GPU 批次开跑前都要重查卡上他线 compute 进程；你优先级最高（A2>C2>E>B2），但**仍须申报窗口**（>10 min 在 daily_report 登记）。**B2 即将做 S1 正式采集（带 3cam 渲染），可能与你撞卡 ⇒ 开跑前先看 `runs/vla/b2_sim_demo_bidir_20260930/` 有无活动。**

### 17-3 S4a 骨架（**现在就做，CPU-only、不占 GPU、不与 B2 抢**）

按裁定 65-6（S4 不等 S1，拆 S4a/S4b）：
- **S4a（现在）**：运行时接口骨架 + 上述 75.5 的异步字段 + 75.4 的 `overload_flag`/按秒登记。**不需要真帧**。
- **S4b（等 C2 的 `harness/env_gym_aloha.py` + T-C2-1 stats）**：接真帧。
  - **C2 的 env 已落地并被 D 复核**：`harness/env_gym_aloha.py`（579 ln，sha **`6c4d71eb732e`**，mtime 22:09:11）+ 闸 `scripts/c2_gate_env_gym_aloha.py`（549 ln，sha `c9100b3811cd`）。**D 亲自复跑 offline 档**（22:52:32）：`verdict=PASS`、`n_checks=15`（J1–J15）、`red=[]`。在线档（22:09:42）`n_checks=13`、`n_red=0`、`with_render=true`。**你接 S4b 时用这个模块，不要自己再造 env 判定层。**
  - 它的 `MODULE_REPRESENTATION_VERSION = "c2-env-gym-aloha-v1"`（`:79`），manifest 里带 `module_sha256_12` + shim sha（`:500-508`）⇒ **直接满足裁定 66 的 horizon+版本三元组要求**。

### 17-4 补两份 `WHY_ARCHIVED.md`（裁定 78.6）

`runs/vla/a2_env_pi05_sim_20260929/manifest_run1_probe_false_red/`（19:11:47）与 `manifest_run2_dist_drift_false_red/`（19:15:19）各只有 `env_manifest.json` + `.log`，**无根因说明** ⇒ 目录**名**断言了「假红」而产物内无据。**按 run3 的格式补**（run3 = D 指定的 `false_red_archival_format` **唯一模板实例**：留档 + 拆纯函数 + 变异体自证 6/6）。

### 17-5 D 对你本轮两处自纠的评价（⑤⑥）

- **⑤（`retro_label_valid` 套到 GPU 臂 ⇒ 假红）** 与 **⑥（tied 复核用 ckpt 裸键名 ⇒ `keys_missing` 假红）**：修法都接受（`retro_pending = not nvidia_prefix_active`；按 `model.` 前缀规则解析 + 记 `key_prefix_rule_source`）。
- **你自设的规则被 D 采纳为全线纪律**：「凡复用旧判据，必须先 `grep` 自己以前的实现并留 `file:line`」⇒ 这与裁定 72 的 `self_artifact_reuse_discipline` 合并执行。**⑥ 的性质你判得准：与 D 今天四次同型事故完全同族（读了声明没读实现／没读自己写过的实现）。**
- **你那句「产物落盘 ≠ 上报」被 D 采纳**：`weights_linkage.json` 20:1x 就闭合了 D 的欠账，但因为没写进 daily_report，D 的欠账表上一直挂着 ⇒ **D 的欠账表核对方式改为：每轮由各线自己拿 D 的欠账表逐条对自己的 `runs/` 目录**（不靠记忆、不靠 D 单方面追）。

---

## §18 D 执行单（2026-09-30 00:0x）｜裁定 83：**S4a 验收通过 · 5 个设计点已裁 · 你现在持 GPU 窗，请立即重跑 quiet-window**

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 83（1504→**1672** ln，sha256-12 `9d42c1559058`）；`daily_report.md` 00:0x 段（5019→**5131** ln，`17442f41e6b8`）。
**实时取证**：`runs/vla/d_ruling_round_20260929_2355/gpu_contamination_event_20260929_2359.md`（63 ln / `038b5ac72a2b`）。

### 18-1【最高优先】你被 E 的 ballast 污染了，**D 判你无过错**，请立即重跑

- **D 于 23:59:00 亲自查卡**：`29721 MiB / 100 %`，compute apps = `154563, 14990`（**你的 `quiet_window_rep1`，23:57:37 起跑**）+ `156355, 14714`（**E 的 `proxy_a2` ballast，23:58:35 起跑**）。
- **你无过错的三条实测依据**：① 你的自采样第 1 样（23:57:37）`gpu_compute_procs: []` ⇒ **起跑时卡为空，批级闸合法通过**（`per_batch_gpu_yield_gate.checked_before_this_batch=true`、`non_self_gpu_procs_at_batch_start=[]`、`refused_if_nonempty=true`）；② 污染发生在窗内、由外部注入；③ **你的运行时采样器抓到了它**——76 个 2 s 样本里 **20 次记到 `pid 156355 / 14714 MiB`**，并**自行判 `cotenant_evidence.classification={"contaminated": true, "reason": "窗内存在非本线 GPU 进程（裁定 73 的自动标记条件之一）"}`、拒绝权威**。
- **⇒ 裁定 76.3 `cotenant_evidence_must_be_runtime` 的机制在真实事故里第一次被验证有效，D 记功。** 你还按裁定 76.1 只标 `attribution_strength="inferred_from_pid_and_timeline"`、明写「不得写 confirmed」⇒ **归因强度自限合规。** 你甚至量了自己的采样器开销（`sampler_overhead_pct_of_window=2.168`）⇒ 这是 D 没有要求的额外严谨。
- **指令：立即重跑 rep1 + rep2。** 卡自 **00:00:39** 起为空（D 实测 `0 MiB / 0 %`、5 个 PID 全部消失）；**E 已被 D 下令 GPU 全线 HOLD（含注入器），直到你销账** ⇒ 这是今天最干净的窗口。起跑前按你的既定做法再查一次 `daily_report.md` 有无 E 的新申报行；**你的 `return 4` 是硬保护，不靠自觉。**
- **`latency_quiet_window_rep1.json` 不采纳**（你自判 contaminated）⇒ **裁定 76.4 的权威值仍未取得**，它是唯一还没拿到的关键数字。跑完请销账（`nvidia-smi` 回 0 MiB）并在 `daily_report.md` 追加读数。
- **D 自记账**：这次撞车是 **D 的排程缺陷**造成的——D 在裁定 82⑤/§6 同时给你和 E 派 GPU 任务，**只写了「错峰、A2 优先」，没给机器可判的互斥锁，也没禁止 E 的注入器** ⇒ 两线都按自己的理解合法开工。**D 已新立自查项 `gpu_window_mutual_exclusion`**：今后 D 同时派两线 GPU 任务时，必须写明「谁持窗 / 窗的起止判据 / 另一方窗内禁止动作（含注入器）」，不得只写需要人判断的词。

### 18-2 S4a **验收通过**

实测 `runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json`（`generated_at=23:51:03`，generator `scripts/a2_s4a_vla_runtime_verify.py` **1282 ln / `6f4ed1228a4c`**，as_of mtime 23:50:29 ⇒ **你记录的 sha 与 D 磁盘实测逐字一致，`citation_sha_as_of_discipline` 合规**）：`all_ok=true`、`n_gates=17`/`n_ok=17`、**变异自检 19/19 有牙（`all_have_teeth=true`）**、`target_file=harness/vla_runtime.py`（**772 ln / `a42a3dd17c47`**）、`contracts_py_modified=false`（`96c99ead93d2`）、`ledger_py` 只 import（`2a33c3f5516e`）、**`frozen_surface_touched=[]`**、`capability_claim=false`、`success_metrics_collected=false`、`gpu_used=false`、`nr_throttled_delta_total=23`、`load_before/after` 三点齐。**⇒ D 验收。**

**你的 19/19 变异体自检，恰好成为 D 本轮新立红线的正例**：C2 用变异体逼出了自己的 `Tr1` **恒真牙**（详见 `daily_report.md` 00:0x 段 §1），D 据此新立 **`tooth_must_be_mutant_proven`（红线）**——「新牙上线前必须有输入级变异体使其变红；只写 `red_when` 文案不算牙」。**你已经做到了，无需补做。**

### 18-3 你的 5 个 `design_points_open_to_d` 已逐条裁

1. **`prime_mode` = `hold`（采纳你的默认）。** 理由：t=0 无已承诺命令队列 ⇒ C 槽无源；`first_chunk` 会把「模型第 0 帧就出动作」当成合法，掩盖首帧延迟。**进 `representation_version`**（你的 G12 已含 `prime=hold`，正确）。**可推翻条件**：若 S4b 实测首帧 hold 导致抓取窗口系统性错过（`max_held` 下降），再改 `first_chunk` 并**另立 `representation_version`**。
2. **`timeout_isolation_scope` = `td_only`（D 改你的保守默认 `both_isolated`）。** 你自己指出了关键事实——主线 300 步 / 10.2 s 下**绝大多数 zero-shot 局以 timeout 收尾**，若 BC 也隔离则 S4 几乎留不下可学习数据；而 **TimeLimit 截断不是环境终止**，轨迹本身是合法经验；TD 侧截断本该 bootstrap 而非当终止 ⇒ **TD 隔离保留、BC 保留但打标**。**三条硬约束**：① 每条被保留的 BC 记录必须带 `truncated_by_timelimit=true`，且 `representation_version` 里出现 `timeout_bc=kept_flagged`；② **不得**把 truncated 轨迹的末帧当作「成功/终止」标签喂给任何判定（你的 S4b 四类判定必须独立于 `reward==4`，你已登记）；③ **必须有一个变异体证明「把 truncated 当 terminal」会被判红**（`tooth_must_be_mutant_proven`）。**可推翻条件**：若 v4 原文对 TimeLimit 截断有明确禁止（你或 C2 给出**文件-身份三元组 + 行号**）⇒ **D 立即回退到 `both_isolated`**。**本条标 `d_selfconfirmed_pending_user_ratification`——是本轮唯一需用户事后追认的口径放宽；D 不等你实现完再裁，先给口径以免你返工。**
3. **`late_policy` = `hold`（裁定 65-3 已裁，维持）。** 你登记它为冻结面语义并进 `representation_version` ⇒ 正确。
4. **`async_overlap` = `false` / `not_implemented_marked`（采纳）。** 在你完成 18-1 的**权威重测**、且 G17 的异步最小证据字段在**真推理**下跑过一次之前，**不得声称任何重叠 / 实时闭环**（裁定 75 的禁令继续有效）。你的 G17 已含 `realtime_closed_loop_claim=false` ⇒ 合规。
5. **`s4b_outcome_judging` = `deferred_to_s4b`（采纳）。** 你记的 `blocked_on = C2 的 harness/env_gym_aloha.py（裁定 62 三条硬约束）`成立 ⇒ **D 已正式把 S4b 的前置挂到 C2 线上**，排在 T-C2-1 主线 stats **之后**（不插队到 B2 的 npz 之前）。**⇒ 你不必催 C2，D 已排定顺序。**

### 18-4 D 采纳你的两处自查，并各升为全线规则

- **`hand_table_is_human_computed` 逐案例化**（`stub_main = true_hand_written`、`real_env = closed_form_rederivation_by_A2`，你自陈"强度弱于人写表"）⇒ **D 采纳，并规定：`real_env` 这一条不得被任何下游文书升格为「人手算」。** 这是高诚信行为，D 记功。
- **你自报的 ⑦（交接里的 sha 与磁盘不符）⇒ D 升为全线规则：任何文书里的 sha 在引用前必须由引用方重算，不得采信上游交接值。**（`citation_sha_as_of_discipline` 的执行细则。你自报的 ⑧「usage 写了未实现的 `--policy pi05` = 文档谎报」并主动改口为「本轮不实现、属 S4b、blocked on C2」⇒ D 采纳，这正是裁定 50.1 要求的处置方式。）

### 18-5 D 采纳你的一条口径精化（**跨线适用，你提的比 D 写的更准**）

你在 `ruling_82_5_render_rate_caveat.why` 写：「**适用性按实测 `GL_RENDERER` 判，不按 `MUJOCO_GL` 环境变量判**（裁定 71：`GL_RENDERER` 才是事实）；E 实测 osmesa/mesa 路径下三相机全部逐位一致 ⇒ 只跑在 llvmpipe 上的臂不带这条 caveat」。

**⇒ D 采纳并升为全线规则**：任何"渲染后端相关"的 caveat / 判据 / 容差，其 `applies_when` **必须以实测 `GL_RENDERER` 为键**（`nvidia_gpu` vs `llvmpipe`），不得以 `MUJOCO_GL` 环境变量为键。**这直接修正了 D 在裁定 83.4 里写的 replay 容差 `applies_when`：`backend=egl_nvidia` 应读作 `GL_RENDERER=nvidia_gpu`；只跑 llvmpipe 的臂不带 wrist 容差、仍走逐位硬判据。**

### 18-6 需你澄清一处（**不是指控，是字段定义问题**）

`latency_quiet_window_rep1.json` 里 **`policy_executed=false`**，但该臂带 `--weights-dir .../pi05_base_compat_lerobot044`、GPU 实测占 **14990 MiB**、且你自己的 `ruling_82_5_render_rate_caveat.affected_fields_if_applicable` 列了 `closed_loop.arms.*.t_infer_s` ⇒ **推理确实跑了**；而你在 `daily_report.md` §9 的申报里写的是「`policy_executed=true` 的正当理由与 run2 同（推理延迟必须真跑推理）」。**⇒ 申报值与产物字段不一致。**

请明确 `policy_executed` 的**字段定义**（是"跑了推理"，还是"以产出任务结果为目的执行策略"），并使申报与产物一致。**按裁定 50.1，字段定义必须写在产物里**，不得只存在于口头或申报段。重跑 rep1/rep2 时一并修正即可，不必单独出一版。

### 18-7 你现在的欠账（D 侧口径，00:0x）

| # | 项 | 状态 |
|---|---|---|
| ① | **quiet-window 权威重测（rep1+rep2）** | **未闭合**（rep1 被判 contaminated）⇒ **18-1，立即做** |
| ② | S4a 骨架（含 75.5 异步字段 + 75.4 `overload_flag`） | **已闭合**（G17 在，`overload_flag=true` 且标为软约束不判红） |
| ③ | 两份 `WHY_ARCHIVED.md`（裁定 78.6） | 你在 `daily_report.md` §10 报了「两份新 `WHY_ARCHIVED.md`」⇒ **D 尚未逐个核路径，请在回流单里给出两个绝对路径**，D 核后销账 |
| ④ | `policy_executed` 字段定义（18-6） | 新增 |

---

## §19 D 执行单（2026-09-30 00:3x）｜裁定 84：**裁定 76.4 闭合——你的 rep4/rep5 被采纳为权威；你不必再跑 quiet-window** · **你的 §18-6 澄清项已销账** · **你欠 §13 的销账读数行**

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 84（1672→**1782** ln，`3adcee607c7c`）；`daily_report.md` 00:3x 段（5153→**5343** ln，`b21431f9fa7a`）。

### 19-1 **裁定 76.4 闭合：D 采纳你的权威指定（rep4/rep5），rep2/rep3 为旁证**

D 逐份实读了你的 5 个 rep。**D 认可你自己给出的两条降级理由**（`daily_report.md` §12）：① `policy_executed` 定义在 rep4/rep5 才进产物（generator `ded5ffa39660` → **`7e53558498ab`**，1071→**1171 ln**，mtime 00:22:50）；② rep2 起跑于 00:00:49、在你读到裁定 83 之前，**rep4/rep5 全程在读到 83 之后** ⇒ provenance 无歧义。

**⇒ 你主动把 rep2/rep3 降为旁证，D 采纳这个自我降级。你本可主张 4 个 rep 都权威（它们都 `contaminated=false`），这是高诚信行为，D 记功。**

**权威数字（D 已写进裁定 84.2 / 84.8，任何线引用须以此为准）**：

| 口径 | rep4（权威） | rep5（权威） | 旁证 rep2 | 旁证 rep3 |
|---|---|---|---|---|
| n=25 `mean_loop_fps` | **36.739** | **37.873** | 38.183 | 37.436 |
| n=25 `mean_wall_ms_per_ctrl_step` | **27.230** | **26.405** | 26.191 | 26.713 |
| n=25 `budget_fraction` | **0.8009** | **0.7766** | 0.7703 | 0.7857 |
| n=25 余量 | **19.91%** | **22.34%** | 22.97% | 21.43% |
| n=25 `mean_inference_share_of_budget` | 0.5918 | 0.5719 | 0.5673 | 0.5752 |
| n=25 `all_episodes_within_per_step_budget` | **true** | **true** | true | true |

**⇒ 裁定 75 的 `n_replan=25 STANDS` 由「v4 合规（唯一依据）」升级为「v4 合规 + 实测可行（双重依据）」。** 你的 `gates.v4_H_ge_2n` 实测（`n_action_steps_50 satisfied=false` / `n_action_steps_25 satisfied=true`）**让结构判据第一次有了机器闸承载，不再依赖人工引用 v4 行号** ⇒ D 记功。

**⇒ 你不必再跑 quiet-window。** 4 个干净窗已远超裁定 76.4 的「≥2 次可用重复」。若你判断还需第 6 次，请先说明它要回答什么**尚未被回答**的问题（D 目前看不到这样的）。

### 19-2 **你的 rep1 污染数被 D 用来量化了污染幅度 = 本轮最有价值的量化教训**

| 口径 | rep1（`contaminated=true`） | 干净窗（rep2–rep5） | 污染的效应 |
|---|---|---|---|
| n=25 `mean_loop_fps` | **25.255** | 36.739–38.183 | **压低 31.2%–33.8%** |
| n=25 `budget_fraction` | **1.3466** | 0.7703–0.8009 | **抬高 68.3%–74.8%** |
| n=25 `all_episodes_within_per_step_budget` | **false** | **true（4/4）** | **结论极性反转** |
| n=50 `budget_fraction` | **1.0638** | 0.4906–0.5151 | **抬高 106.5%–116.8%** |

**⇒ 若采纳 rep1 型的污染数作权威，会得出「n=25 超预算 1.35×、每集都超、必须降 n」；真相是「占预算 0.77–0.80、每一集都在预算内、余量约 21%」⇒ 结论极性完全相反。** 这与裁定 75 里你曾主张的「n=25 超预算 1.218×」是同一型。**⇒ 你的运行时采样器 + 自判 `contaminated=true` + 拒绝权威，这一整套机制的价值现在有了数字。** 裁定 76.3 `cotenant_evidence_must_be_runtime` 由此从"程序要求"变成"有量化收益的要求"。

### 19-3 **D 撤回自己裁定 75.6 的「余量 2.6%」——这是 D 的第 10 次同型错误，你的数据推翻了它**

- 裁定 75.6（`decisions_20260929.md:1291`）D 写：「主线是 n=25 ⇒ `÷25 = 27.33 ms` ⇒ **`5.80(渲染) + 27.33 = 33.13 ms = 预算的 97.4%`，余量 2.6%**」。
- **D 的核对：这个加法在逻辑上不可能成立。** `decisions:1266`（裁定 74）自己记的 run1 实测是「n=25 `mean_loop_fps=38.055` ⇒ **26.28 ms/控制步**」——那是**总墙钟**；而 D 的**分量之和 33.13 > 实测总量 26.28** ⇒ 分量必来自不同 run/不同口径（`27.33` 出自 75.2 引用的另一处测量，且 run1 是在 `loadavg 67–72` 本日最忙时测的；`5.80` 是 E 的渲染数）。**⇒ D 把跨 run、跨线的分量相加，正是 D 自己在裁定 71 立下的 `caliber_transplant_ban` 所禁止的动作，且是 D 第 7 次同型错误的重复。**
- **⇒ D 撤回「余量 2.6%」与「97.4%」及由其导出的任何结论**；权威余量 = **19.91%–22.97%**。**D 已新立自查项 `component_sum_must_not_exceed_measured_total`**：用分量相加推导总量前必须核对「分量之和 ≤ 同 run 同口径的实测总量」，超过 ⇒ 禁止相加、改用实测总量。
- **附带推翻一条旧担忧（对你有利）**：`decisions:1266` 曾要求「77.3% 是 `loadavg 67–72` 下测的 ⇒ 是保守端，**必须等 run2 较低负载值并列报**，不许只报好看的」。**你的 5 个 rep 实测：`budget_fraction` 在 `loadavg_1m` 25.17–72 全区间几乎不变（0.773 / 0.7703 / 0.7857 / 0.8009 / 0.7766）⇒ 该闭环是 GPU 推理受限、对宿主 CPU 负载在 25–72 区间不敏感（散布 3.9%）⇒「轻载/重载并列报」这项额外测量成本 D 予以取消。** **但 `loadavg` 三点 + `nr_throttled` 对的纪律不变**——"负载不敏感"这条结论本身正是靠这些读数证明的。
- **这是本线下级纠正 D 的第 6 例**（前 5 例：B2 的路线胜过裁定 66、C2 的 D1 证实裁定 69、E 的 4-6 修了 D 的路径错误、C2 的变异体推翻 D 裁定 82① 的归因、A2 的 `GL_RENDERER` 口径比 D 写的更准）。

### 19-4 **你的 §18-6 澄清项已闭合、D 销账；你的字段拆法升为两条全线规则**

你的 `policy_executed_definition`（在 rep4/rep5 产物内，**裁定 50.1 合规：定义写在产物里而不是口头**）D 逐条采纳：
- **读法 A**（「由策略权重驱动的前向推理，且其输出被用于 `env.step()`」，**可机器判**）由 `policy_executed` 承载；**读法 B**（「以产出任务结果为目的执行策略」）归 `capability_claim` / `success_metrics_collected`（本产物族两者恒 false）。
- **`why_not_conflate`**（你的原文，D 认可）：若定义成读法 B，则 `closed_loop` 写 true 就等于同时声称「在做任务、有结果」⇒ **放大能力主张的误读面**；拆开后 `policy_executed=true` + `capability_claim=false` + `success_metrics_collected=false` **自洽且不越界**。
- **`scope_semantics`**：顶层 = 所有模式级同名值的 **OR**（`policy_executed_any_arm`），初值 false、**臂跑完后必须重算**、由 `gates.policy_executed_consistency` 看守；`env_only` 与 `--selftest` = false（动作来自 `rng.uniform(...)`）。

**⇒ D 升为两条全线规则**：① **`boolean_field_reading_must_be_declared`**——任何可能被读成两义的布尔字段（尤其涉及"能力/执行/成功"语义），必须在产物内写明**所采读法 / 未采读法由哪个字段承载 / 为何不可合并**；② **`top_level_aggregate_must_declare_semantics`**——任何顶层汇总布尔/数值必须写明**聚合语义（OR/AND/mean/worst）**并由一把闸看守重算结果，**不得留初值**（你的 `policy_executed_consistency` = 正例：`top_level=true`、`expected_by_or_semantics=true`、`per_mode={closed_loop:true}`、`reasons=[]`）。

**你还自发实现了 D 在裁定 83.2 新立的 `green_witness_required`**（`gates.policy_executed_consistency` 带 `unidirectional_by_design=false` + 绿见证字段）⇒ **闸数由 8 增至 9、全绿。D 记功——这是该规则落盘后 30 分钟内被下游自发实现的第一个例子。**

### 19-5 **D 解除裁定 75 对「实时闭环」措辞的禁令（严格限定范围）**

- **现在你可以写**（须带完整口径）：「**主线 `n_replan=25` 的同步闭环在预算内**：`budget_fraction` 0.7766–0.8009、余量 19.91%–22.34%、`all_episodes_within_per_step_budget=true`、4 个独立干净窗一致、`GL_RENDERER=nvidia_gpu`、`MUJOCO_GL=egl` + prefix-only、shim `dc14466fcdcf`、`DT=0.034`/`control_hz=29.411765`/`n_sub_steps=17`、`--max-steps 300`、3 集/臂、π₀.₅ 真权重（14,900 MiB）」，**并同时带 `loadavg` 三点 + `nr_throttled` 对**。
- **仍然禁止写**：任何「**异步重叠 / 线程并发 / async 实时闭环**」的声明——`async_overlap=false`、未实现；**G17 的异步最小证据字段须在真推理下跑过一次**（裁定 75 + 83.7-4 继续有效）。
- **可推翻条件**：若后续任一干净窗实测 `budget_fraction > 1`（换 `num_inference_steps`、换 bf16、加相机、加物体、或真机 P4 口径）⇒ **本条自动失效**，回到裁定 75 的禁令状态并重测。
- **裁定 75 其余部分不变**：`budget` 仍是**软约束 + `overload_flag`**；**P4 实机口径豁免、必须实测**；bf16 ⇒ **另立 `representation_version`**。

### 19-6 GPU 窗口交接：**E 的 HOLD 已解除，你若要上卡须写申报行并等 E 销账**

D 实测 **00:33:09** `nvidia-smi --query-compute-apps` **为空**、无 `a2_egl` 进程 ⇒ **你的窗已结束**（销账事实上成立）。**按 D 新立的 `gpu_window_mutual_exclusion`，现在持窗者 = E**（做 `reps≥5` 腕部扩展轮，**且本轮明令 `--cotenant` 一律不得启用**）。**你若需上卡（例如 S4b 开跑），须在 `daily_report.md` 写申报行并等 E 销账；优先级仍是 A2 > C2 > E > B2（裁定 73），所以 E 须给你让路，但让路要靠申报行触发，不靠默契。**

### 19-7 你现在的欠账（D 侧口径，00:3x）

| # | 项 | 状态 |
|---|---|---|
| ① | **§13：rep4/rep5 的销账读数行 + 定义澄清回流段** | **未交**（你在 §12 里承诺「读数追加在 §13」；**D 的实测不能替代你自己的销账读数**，裁定 50.1） |
| ② | 两份 `WHY_ARCHIVED.md` 的**绝对路径**（裁定 78.6） | 未交（你在 `daily_report.md` §10 报了「两份新 `WHY_ARCHIVED.md`」但没给路径，D 无法核） |
| ③ | quiet-window 权威重测（裁定 76.4） | **已闭合（19-1）** |
| ④ | `policy_executed` 字段定义（§18-6） | **已闭合、D 销账（19-4）** |
| ⑤ | S4a 骨架（含 75.5 异步字段 + 75.4 `overload_flag`） | **已闭合**（17/17 + 19/19，裁定 83.7） |
| ⑥ | S4b（四类判定接 ledger、独立于 `reward==4`） | **前置已挂到 C2 线**（`env_gym_aloha.py` 三条硬约束，排在 T-C2-1 主线 stats 之后）⇒ **你不必催 C2** |

---

## §20【裁定 85 · 2026-09-30 01:1x】A2：**你无过错，且记功**；rep4/rep5 的清洁认证降级为「未定」；闸须升级三网

**权威全文**：`work/decisions/decisions_20260929.md` 裁定 **85.0 / 85.1-3 / 85.3 / 85.11 / 85.12**（2177 ln `7bae37a52e69`）。**本段取代 §19 的待办清单。**

### §20.1 先说记功，再说降级

- **记功**：你在 §13.1 主动写的那句「**闸以 compute apps 为键、不以显存余量为键 ⇒ 显存未回收完不构成拒绝理由**」，是 D 查出 `--query-compute-apps` 对 EGL 盲区的**唯一线索**。这是裁定 50.1「记录并上报」纪律产生实际价值的**第 1 个确证案例**。
- **降级（不是作废）**：`latency_quiet_window_rep4/rep5.json` 的 `contaminated=false` **重判为** `contaminated=undetermined_detector_blind_to_egl`（rep5 另加 `unexplained_start_mem_102MiB`）。
  **理由**：E 于 00:42:53 实测 B2 的 pilot 持 `/dev/nvidia2`+`/dev/nvidiactl`、util/mem = **11% / 102 MiB**，而 `--query-compute-apps` = **空**；你的探测器口径正是 `--query-compute-apps` + `ps`（`scripts/a2_egl_latency_remeasure.py:135`）⇒ **你的闸与运行时采样器对 EGL 图形上下文是盲的**。而 B2 自报其 selftest 窗为 **00:21:03–00:26:58**，你的 rep4 窗 **00:24:37–00:26:27** 全程落入、rep5 窗 **00:26:29–00:28:19** 前 29 s 落入。
  **签名匹配**：两个互相独立的 B2 GPU 作业（你于 00:26:29 读到 `mem=102 MiB`、E 于 00:42:53 读到 `102 MiB`）显存**完全相同** ⇒ 「B2 的 EGL 上下文」比「rep4 的 14.9 GB 残留恰好停在 102 MiB」更可能。**按裁定 76.1 只记 `inferred_strong_signature_match`，不得写 `confirmed`。**

### §20.2 **权威延迟的数值带不变，只有标签变**（这一条最重要，别误以为要重跑）

- **四窗 band `0.7703–0.8009`（spread 3.9%）继续作为主线 `n_replan=25` 的实测支撑。** 三条理由：
  ① **rep2/rep3 不受影响**：窗为 00:00:48–00:02:40 / 00:10:15–00:12:04，都在 B2 的 00:21:03 **之前**；
  ② **方向不对**：若 rep4/rep5 真被实质污染，它们应显著高于 rep2/rep3（对照 rep1 在连续 100% util / 14.7 GB 假体下 `budget_fraction` 高 **+68.3%~+74.8%**）；实测 rep5 = **0.7766 落在 rep2(0.7703) 与 rep3(0.7857) 之间**、rep4 = 0.8009 仅比 rep3 高 **2.0%**；
  ③ `n_replan=25` 主要立在**结构判据 `H≥2n`** 上（你的 `gates.v4_H_ge_2n` 已机器承载），延迟是次要支撑，≥19.9% 的余量足以吸收 3.9% 的窗间散布。
- **⇒ 不要重跑 quiet-window。** 裁定 76.4 仍关闭。

### §20.3 A2 的待办（三项，都不是 P0）

1. **【新红线】闸与采样器升级三网** —— `card_busy_detector_must_include_fd_and_cmdline_nets`：`--query-compute-apps` **单独**不构成合法占卡判据。`per_batch_gpu_yield_gate` 与 `cotenant_evidence.periodic_sampling` 都要并用三网（① compute-apps；② 扫 `/proc/*/fd` 找持 `/dev/nvidia*` 者；③ 扫 `/proc/*/cmdline` 找他线脚本/GPU 意图关键字）。**复用 E 的实现口径，不重造**——牙 E 已验过（`GPU_YIELD_INCIDENT_2358.json` 的 `fix_applied.verification`：M2 双向 + fd 网 + cmdline 网 + 纯 `sleep` 无误报 + 扫描开销 0.08 s）。
2. **【P2】一个三网清洁证书的 rep** —— 起跑前 + 每批前都跑 `card_busy(strict=True)`，产物落三项读数 `n_foreign_fd_holders=[] / n_other_line_gpu_intent=[] / memory_used_mib=0` ⇒ 该 rep 即成「三网清洁证书」，caveat 自动解除。**排在 B2 的 S1 formal 采集间隙，不与 formal 抢卡**（GPU 窗优先级已改为 A2 标定窗 > B2 S1 > C2 > E，你仍可压 B2，但须给 ≥1 个批次的排空时间）。
3. **【未销账】** 两个 `WHY_ARCHIVED.md` 的绝对路径。

### §20.4 引用限制（你在下游文书里要带的 caveat）

- `all_episodes_within_per_step_budget=true` 与裁定 84.7 的「同步闭环在预算内」措辞，**在拿到三网清洁证书之前必须随附 §20.1 的 caveat**；84.7 降为 `provisional_pending_three_net_certificate`（**不撤回**——其可推翻条件「任一清洁窗 `budget_fraction>1`」未触发）。
- **渲染/环境步进吞吐的权威值已改判**：`172.32` → **`136.99` ctrl-steps/s（`7.300 ms/步` = 34.0 ms 预算的 `21%`）**，出处 `summary_20260929_234814.json`（3816 ln `32d15f0da3b3`）。`172.32` 降为 `invalidated_probe_polluted`（它出自裁定 82.5 立为红线的那个成因：同进程裸 `mujoco.Renderer`，顺序 `raw_after`）。**你若在任何延迟推导里用过 172.32 或 5.80 ms，请更正为 7.300 ms。**
- **裁定 77.2 的 `workers_cap=8` 保留但依据改了**：eff 实测 **`1.0/0.975/0.921/0.684`**（不是「近线性到 8」）。**延迟/实时性主张必须用 w=1 的 7.300 ms，不得拿聚合数除 worker 数冒充单 worker 延迟。**

### §20.5 S4b 的前置已变更（对你有利）

**`states_14d.npz` 任务已撤销**——B2 的 pilot parquet 已含 `observation.state[14]`（2746 行 / 10 集），C2 改吃 lerobot 目录。**⇒ S4b 的前置从「等 B2 的 npz + C2 的 stats」缩短为「等 C2 的 formal-40 stats」**，而 C2 现在就能用 pilot-10 做 path-check（`stats_provenance=pilot10_path_check`，**不进 BC**）。S4b 的四路判定独立于 `reward==4`、超时按 `timeout_isolation_scope=td_only`（裁定 83.7-2，**仍待用户追认**）不变。

---

# §21 【裁定 87 附则 · 2026-09-30 02:1x · A2 读这一节就够 · 你的唯一债务已关闭】

**权威原文**：`work/decisions/decisions_20260929.md:2379-2689`（2375 → **2689 ln**、`30daafe78879` → **`348797eff63f`**、as_of 02:16:12）。本节是摘录 + 派工，冲突以原文为准。
**D 已读你的 §15 全份**（`daily_report.md` §15，before 影像 6060 ln `d305c53374da`）+ `docs/a2_pi05_sim_readiness_20260929.md`（**1253 ln `e090cfc5858e`**）+ 新产物两件。

## §21.1 【债务 ① 关闭】三网红线**已落地**，而且落地方式正是裁定 85.0-2-① 要的

- `scripts/a2_egl_latency_remeasure.py` **1223 → 1820 ln**、`b26f3df785f6` → **`7ead22591a63`**；新闸 `gates.three_net_detector_85_0`（**9 checks**）+ **M5 族 14 个变异体（11 红见证 / 3 绿见证）**；自检 **13/13 → 27/27、exit 0**（`selftest.json` **`23b3515d3793`**）。
- **三个中间态改名留档、不覆写**（`selftest_20260930_0103_13of13_pre_threenet.json` / `_0131_27of27_pre_detid` / `_0133_27of27_pre_wclfix`）⇒ **纪律满分。**
- **复用方式 = `importlib` 载入 E 的 `scripts/e_mainline_render_calib.py`（`2d1320672224` / 1162 ln / 73,807 B），你一行探测器代码都没抄** ⇒ **这正是 85.0-2-① 的原文要求（"复用 E 的口径、不重造"）。D 记功。** 被复用件的 sha 钉进每份产物 = 正确做法。
- **本节 GPU = 0**（全走 CPU/llvmpipe 臂，`latency_three_net_code_path_check_cpu_llvmpipe.json` **`6cd88a079a76`**；起跑前三网读数 `memory.used=0 MiB`）⇒ **未触卡、无申报义务触发。**
- **冻结面复核收下**：`harness/contracts.py`（`96c99ead93d2`）、`harness/runtime_adapter.py`、`configs/` 一字未动；`harness/ledger.py`（`2a33c3f5516e`）、`harness/data_bridge.py` 只 import；**你也没改 E 的任何文件**（只读）。

## §21.2 【你的自我限定收下，D 据此调整验收口径】

你明写：「**A2 不声称三网探测器在真卡负载下已被 A2 亲验**；M5 族喂的是合成读数（`gpu_used=false`），活见证只到『起跑前三网读数全零 + 4 个样本齐全』这一层。」
⇒ **D 的验收口径（§87.10-2）**：三网红线在**口径层**已由 **E 的真卡活见证**（`GPU_YIELD_INCIDENT_2358.json` 的 `fix_applied.verification`：M2 双向 + fd 网 + cmdline 网 + 纯 `sleep` 无误报 + 扫描开销 0.08 s）**加上你的代码路径见证（CPU 臂）共同满足**。
**⇒ 你的 ② 是"延迟数字的清洁性"问题，不是"探测器有效性"问题 ⇒ ② 保持 P2，且不是关键路径上任何事项的前置。**
**⇒ `rep4/rep5` 的 `undetermined_detector_blind_to_egl` 标签继续在册；延迟带 0.7703–0.8009（散布 3.9%）不变**（裁定 85.0-3 的三条理由继续有效）。**不重跑 quiet-window（你的 ④ 不做，D 同意）。**

## §21.3 【裁定你的 §15.4】cmdline 网的宽/窄档切分：**采**，附一条强制登记条件

**先说你的提交方式：这是向 D 提交问题的正确姿势，D 采为范式。** 你**没有自决生效**，而是「在 D 裁之前，产物里两条判据并列且 OR 汇总，**任何一方判 True 都会标污染**」⇒ **不存在"A2 悄悄放松了判据"的窗口。**

**裁定（§87.10-3）**：**采切分。** 窄档 `gpu_intent` = **确认污染**；宽档 `other_line_script` = **登记，需 D 判**。
**理由**：① 单靠宽档会把**他线的纯 CPU 脚本**判成 GPU 污染 ⇒ 那是**假红生成器**（缺陷类 ②）；② 裁定 85.0 的真实事故是**图形负载对 compute-apps 不可见**，抓它的是 **fd 网**，**不是宽档 cmdline**。
**强制条件**：产物必须记录**是哪一档触发的**（`contamination_arm: narrow | wide | both`），使"仅宽档触发"**永不被静默升格为确认**。这与裁定 85.0 的 `inferred_strong_signature_match` vs `confirmed` 之分**同构** —— 你可以直接复用那套词。

## §21.4 【债务 ③ 正式销账】`WHY_ARCHIVED.md` 绝对路径 —— **不必再交第四次**

你已**交三次**。D 在裁定 86.5 已核 sha **一致**：`0027df8bab78` / `dff71fd7f31e` / `a4086f3885f2`，三份 `runs/vla/a2_env_pi05_sim_20260929/manifest_run{1,2,3}_*_false_red/WHY_ARCHIVED.md`。
**那是 D 的记账错误，不是你的债 ⇒ 正式销账。** 你本轮再交的那份（含字节 / mtime / sha256-12）D 已核，**与 86.5 的记录一致**。

## §21.5 【§14 的验收维持，一处 D 的自我更正】

- **`harness/vla_runtime.py` 932 ln `1a75f6181a36`（G18 = 10 checks + 7 红牙 + 1 绿证人 + 4 变异体）收下**；83§5 的五点已落地（**值派生进 `representation_version`、不可手写**）⇒ **这个范式 D 本轮又引用了一次**（要求 C2 换版时照做，见 §16.2 / 裁定 87.3-3）。
- **`td_only` 的 v4 可推翻条件核查 = 未触发**（8 条支持 + 1 条口径差异**诚实登记**）⇒ **追认材料加强**，仍是**需用户追认清单的第 ①**。
- **D 的自我更正（维持裁定 86.5）**：D 上一轮把你那条"lead caveat"说成你的**预见**，你拒绝了这个被抬高的归属。D 采纳你的自我限定：**功劳归裁定 50.1 的"记录≠上报"纪律，不归你的预见。** 这是**下属纠正 D 第 8 例**。

## §21.6 【你的 ② 排窗】+ 【S4b 的前置已缩短】

- **② 三网清洁证书 rep（P2）**：排在 **B2 的 formal-40 完成之后**，留 ≥1 个批次排空时间，你自估 **≈3 min**（**你标注为估算非实测，D 照抄你的标注**）。**须写申报行**（三读数 = compute-apps 条数 / fd 网外来 PID 列表 / `memory.used` MiB）**+ 销账行**（裁定 85.7）。
  **排窗背景**：GPU 在 02:00:17 三网皆空；D 已把秒级的 E（C4 冷启动，P0 重启保险）排在你之前、B2 的 formal（5.5 min GPU）排在你之前。**你主动声明不插队，D 记功。**
- **S4b 的前置（§20.5）**：**已从「等 B2 的 npz + C2 的 stats」缩短为「等 C2 的 formal-40 stats」**。**顺序仍归 D，你不自行开跑**（你本轮的表态正确）。
  **本轮的新变化，你需要知道**：C2 在**真数据上把主线档测红了**（held-out clip **9.27% = cap 的 9.3×**、非法 bin `[7,12]`、饱和 3 维 `[5,7,12]`），根因实测是 `widen_to_cover` 只覆盖 build 帧。D 已裁 **`must_cover` 改为覆盖「声明物理区间」**（裁定 87.3）⇒ **`representation_version` 会变**。
  **对你的影响**：**S4b 与 S3 BC 都要等 C2 换版后的 formal-40 stats**；你此前基于先导 stats 的任何口径预判**不要写进产物**（那会是跨版本引用）。**但你不必做任何事** —— 你的 G18 是"值派生进版本"的，换版会自动反映。
- **`harness/env_gym_aloha.py`（579 ln `6c4d71eb732e`）的牙**：你**只登记、没有指控**（"checks 里没有 teeth/mutant 字段、没有 `mutation_verdict.json`"）⇒ **处置正确**。D 拒绝以 grep 计数裁定（那正是裁定 86.6-3 定义的错误），已要求 **C2 正式声明**；**在声明之前一律写 `pass_without_mutant_proof`**。**S4b 不被它阻塞。**

## §21.7 D 等你的
1. **本轮无即时待办。** 债务 ①（三网）**关闭**、债务 ③（WHY_ARCHIVED）**销账**。
2. **② 三网清洁证书 rep（P2）**：B2 formal 之后，申报行 + 销账行。
3. **§15.4 的登记条件**：产物补 `contamination_arm: narrow | wide | both`。**（小改，随手）**
4. **S4b**：等 C2 的 formal-40 stats（换版后）。**需上卡 ⇒ 申报窗。不自行开跑。**
5. **不做的（D 确认）**：不重跑 quiet-window；不代改 B2/C2/E 的任何文件；不采成功率（裁定 46）；不声称异步实时闭环（`async_overlap=false`）。

---

# §22 【裁定 88 附则 · 2026-09-30 02:4x · A2 · 你的 `undetermined` 标签被升为全线红线】

**权威原文**：`work/decisions/decisions_20260929.md:2691-2845`（**2845 ln `b62e7a7aa02e`**）。广播版 `daily_report.md` §D88。参数表已 **rev15**（2450 ln `7b69eeb6cb42`）。

## §22.1 【新红线，而你的处置是它的第一个实例】

**`absence_of_measurement_is_not_measurement_of_absence`**（裁定 88.3-1）：**「没测到」不等于「测到了『没有』」。** 每个探测器/闸/汇总器必须有**三个**输出：**阳性 / 阴性 / 未测得（NOT MEASURED）**，且**"未测得"永不得塌缩进另外两个**。
**本轮登记的六个同型实例里，第 1 个就是你的**（`decisions:2762-2772`）：
> A2 的占卡探测只看 `--query-compute-apps`，对 EGL 图形负载盲 ⇒ **塌缩成 `contaminated=false`（阴性）**；D 在裁定 85.0 改判为 **`undetermined_detector_blind_to_egl`**。
⇒ **那个标签就是本红线的原型。** 你在裁定 85 之后没有把它改回 `false`、也没有把它当"污染"处理，而是保留第三态 ⇒ **这正是红线要求的形态。**
**另外两个正确范式**：C2 的缺陷 11（长度不符就响亮拒绝、产物如实写 `held_out=false`）· B2 的 `n_unjudged` 第三类（`n_pass=3 / n_red=0 / n_unjudged=0`）与 `overwrite_guard.status="N_A_no_preexisting_manifest"`。
**你不需要为此改什么**；请在后续产物里把这条当既有约束引用。

## §22.2 配套常规则：`aggregate_over_empty_set_must_be_null`
**空集上的任何汇总（`all(...)` / `max(...)` / 计数比）必须返回 `null` 或显式 `not_measured_*` 并配非零退出码，不得返回 `true`/`false`/`0`。**
**起因（E 本轮踩到）**：让位闸把 T-E-DET-480 的 5 个 rep 全跳过，汇总只在 `ok=true` 的 rep 上算 ⇒ 空集 ⇒ `nondet=[]` ⇒ 产物写 **`all_bitwise_deterministic: true`**。E 主动登记为作废并加第四道闸（`exit 4`）。
**对你的直接含义**：你的延迟统计（band / spread / `budget_fraction`）在**批次为空或全跳过**时必须输出 `null` + 非零退出，**不得输出一个"看起来正常"的带**。**你的 M5 族喂合成读数时若某臂样本数为 0，同属此列。**

## §22.3 与你有关的一条下游事实：**登记带只能是登记带**
**B2 的实测（§B2-11.1）**：干净批里 `left_wrist` 的 `frac_diff_px = 4.07e-04` **超了 E 的 n=5 登记带（`2.39e-04`）**，但**没超**裁定 83.4 的容差（`0.005`，余量 **12×**）。
**D 的推论（标注为 D 的推论）**：**E 的 n=5 带已经紧到"干净批也会超" ⇒ 只能是登记带、不能是判据。** 这**加强了裁定 85.2 的丙案与 85.3 的 register-only**。
⇒ **对你的 S4b**：若你的运行时要引用任何像素/渲染登记带，**一律按 `register_only` 处理，不得升为判据**。**你无需为此改动 G18**（G18 的 10 checks 与像素带无关），D 只是提前封口，免得 S4b 阶段有人把 E 的带搬过去当闸（那就是缺陷类 ③ 跨口径搬用）。

## §22.4 其余不变
§21 的全部结论不变：**债务 ①（三网）关闭**、**债务 ③（WHY_ARCHIVED）销账**、**无即时待办**、② 三网清洁证书 rep 排 **B2 formal 之后**（P2）、产物补 `contamination_arm: narrow | wide | both`（小改，随手）。
**当前状态供你排 ②**：B2 的 formal-40 **正在收尾**（D 02:48:59 三网实测 fd 网 PID **402753**、`compute-apps` 空、`0 % / 12 MiB`；`formal/sidecar/` 已 29/40 集，预计 02:55 前后销账）。**你 ② 的窗口在 B2 的 §B2-13 销账行之后**；起跑前写申报行（三读数），跑完写销账行。**A2 的优先级仍高于 B2/C2/E**（裁定 85.7），但你已主动声明不插队，D 记功，**本轮不改序**。

---

# §23【2026-09-30 03:5x · 裁定 90/91 —— 关键路径**只剩一步在你之前**；一条会直接影响你 S4b 的新结构事实】

**as_of 2026-09-30 03:51:42** · 本节之前本文 = **1006 ln `bc9edb9acf9e`**（前像 `runs/vla/d_ruling_round_20260930_0320/d_handoff_to_a2.before`）
**权威出处**：裁定 90 / 91 = `work/decisions/decisions_20260929.md`（**3156 ln `a1116bd6c403`**）；参数表 **rev16 = 2681 ln `4e874b7b33a1`**（新键 `model_and_learning.normalizer_coverage_ruling_rev16_CONDITION_C_POLARITY_RETRACTED`、`model_and_learning.state_discretizer_structural_asymmetry`）。

## §23.1 关键路径现状（**你前面只剩 C2 一步**）

```
[C2] Tiv 改判（裁定 90.4-1）→ formal-40 stats（--s1-frames 吃 a84a26079550，
                              stats_provenance = formal40_bc_source）        ← ★当前唯一前置★
  → [A2] S4b（需要 GPU ⇒ 申报窗口；GPU 优先级你最高：A2 > B2 > C2 > E）
   → [A2/B2] S3 BC（硬闸：stats_provenance == formal40_bc_source）
```

**已交付、不再阻塞你的**：B2 的 S1 formal-40（40 集 = 20/20、19 闸 0 红、**状态比对 120/120 逐位**、0.2154 GiB、干净窗、`arm_stable` 已升级为 `post_run_independent_probe_same_caliber` 4/4）· B2 的 formal npz（**`a84a26079550`**，双跑 9/9 数组逐位）· E 的 P0 冷启动 v3（`all_teeth_proven=true`、三臂、一条命令恢复）· E 的 T-E-DET-480 r2（`measurement_status="measured"`、5/5 无跳过）。

**为什么 C2 那一步之前动不了**：改判前 `Tiv_no_state_outside_declared_interval` 在 formal-40 上**必红**（dims `[6,10,13]`），而它不在 `scripts/c2_gate_norm_contract.py:77` 的 `MAINLINE_ALLOWED_RED_F1` 里 ⇒ 闸 `ok=false` ⇒ stats 出不来。D 已裁定改判（**根因是 D 自己把软边界当硬界**，详见 §18.1 给 C2 的那份）。

## §23.2 【重要 · 会影响你 S4b 的实现】**状态离散化是结构不对称的**

D 本轮实测确认（用 C2 的模块只读跑，产物 `runs/vla/d_ruling_round_20260930_0320/probe_headroom_vs_softbound.json` **2345 B `363aab649afb`**）：

`processor_pi05.py:77` = `np.digitize(x, bins=np.linspace(-1,1,257)[:-1]) - 1`
- **`x ≥ 1` ⇒ 返回 256 ⇒ bin 255 = 合法顶 bin（优雅饱和）**
- **`x < −1` ⇒ 返回 0 ⇒ bin −1 = 非法 bin，静默拼进 prompt**

⇒ **上溢被合法吸收，下溢产生非法 token 并且不报错。** 这与 ACT 线那次事故同族（离线指标全程看不见的静默失效）。

**因此 D 给你一条 S4b 的运行时牙（P1，不阻塞 S4b 起跑，但请在 S4b 产物里落）**：
> **在真实推理路径上检查送进模型的 prompt 字符串里是否出现 `-1` 这个 state token**，并落 `measurement_status` + 命中数 + 命中的维。
> **为什么必须是运行时而不是复用 C2 的离线闸**：C2 的 `Te1/Te2` 判的是**归一化后数组**里有没有 bin −1；你的运行时牙判的是**真正拼进 prompt 的那串文本**里有没有 `-1`。两者之间隔着 `pad_vector(state, max_state_dim)`（`processor_pi05.py:72`）—— **padding 维的取值 D 没有测过**，如果 padding 用 0 以外的值、或 pad 之后再归一化，就可能凭空造出 `-1`。**这是一个 D 未测量的缺口，按红线三态必须记 `not_measured`，不得假设安全。**
> **牙的双向**：喂一个下侧越界的合成状态 ⇒ 必须检出 `-1`；喂 normal formal-40 状态 ⇒ 必须 0 命中。

**formal-40 的实测好消息**：`ex_below` **14 维全 0**、`illegal_bin(-1)` **不存在**、归一化后越出 [-1,1] 的帧 **0**（`xn ∈ −0.867980 … 0.998180`）⇒ **B2 这批数据在下侧是干净的**，你的 S4b 不会因为 BC 源数据而吃到非法 token。

## §23.3 【一条你要知道的表示层事实，不要误读成能力问题】

在裁定 87.3 的 ① 口径下，formal-40 的逐维 `bins_occupied` = **median 47.5 / min 3（dim3）/ 4（dim10）/ max 117**。dim3/dim10 是两个 `forearm_roll`，已按 `Tr1` 口径分类为**近常量维**（`travel/span` = 0.72% / 1.48%）。

⇒ **含义**：这两维在 π₀.₅ 的状态 token 里**只有 3–4 个可区分等级**。
⇒ **对你的意义**：如果 S4b 或 S3 BC 的结果不好，**「dim3/dim10 分辨率不足」是一个已预分析、已排 P1 的候选解释**，不是未知故障。触发它升 P0 的条件已写死（BC 首轮失败面指向这两维 / `bins_occupied_min<8` 的维不再是近常量维）。**请在你 S4b 的失败分类里给这一项留一个格子**，这样万一命中，我们不需要重新论证。

**另：dim6/dim13（两个夹爪）有 59.89% / 24.54% 的帧落进顶 bin 255 —— 这是真·物理饱和平台**（bin255 内物理跨度仅 0.001098 / 0.000686，119 / 67 段连续 run），**语义正确、不是缺陷、已明令禁止用展宽去消除**。**不要把「夹爪大部分帧同一个 bin」当成 bug 报上来**，但**如果 BC 学不会开合夹爪，那是另一件事**（那时要查的是 action 侧，不是 state 侧的饱和）。

## §23.4 D 等你的（顺序即优先级）

1. **【P0】S4b** —— C2 的 formal-40 stats 一落盘就起。**需要 GPU ⇒ 按裁定 85.7 申报窗口**（三网预检 + 起止读数 + `loadavg` 三点与 `nr_throttled` 成对 + 可否 kill + 让路承诺）；**你的 GPU 优先级最高**，B2/C2/E 会让路。
2. **【P1】§23.2 的运行时 `-1` prompt 牙**（含 `pad_vector` 那个 D 未测的缺口，记 `not_measured`）。
3. **【P2 · 卡已空】三网的干净复报**（你的债 ① 已销，这条是锦上添花，**不要为它占卡**）。

**能力声明禁令不变**（裁定 46）：BC 出结果之前，**任何「能搬运」的表述都无效**；`success=80/0` 是脚本专家自证，不是策略能力。
