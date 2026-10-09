# 可复现性事故：robosuite pin 漂移导致几何与观测布局同时改变（B 线，2026-09-28）

状态：**已修复，已加防线，作废清单见 §5**。
`scripts/setup_env.sh` 末尾的可复现性门禁就是为这次事故加的，本文是它引用的说明书。

---

## 1. 一句话

`scripts/setup_env.sh` 里 `pip freeze --local` 的结果**直接覆写了 `requirements.txt`**
（人工 pin 的意图文件）。容器重建后 robosuite 装到 1.5.1，freeze 又把 pin 改写成 1.5.1，
于是「pin 文件」和「实装版本」互相确认、双双错误。1.5.1 与 1.5.2 在两个地方不兼容：
**物体尺寸随机化走的 RNG 不同**、**state obs 从 60 维变 53 维**。当天所有接触实验作废。

## 2. 三个缺陷，逐级放大

### 缺陷 1：pin 文件被生成物覆写（治理层）

`requirements.txt` 是「我们想要什么」，`pip freeze` 是「实际装了什么」。
两者写进同一个文件，pin 就会静默漂移，而且漂移之后文件看起来完全正常。

**修复**：freeze 改写 `requirements.lock.txt`，`requirements.txt` 恢复为人工 pin
（`robosuite==1.5.1` → `1.5.2`，见 `scripts/setup_env.sh:59-67`）。

### 缺陷 2：`PINNED_OBJECT_SEED` 在 1.5.1 下静默失效（环境层）

`harness/env_factory.py::pinned_object_rng` 的做法是 monkeypatch `np.random.default_rng`，
把 robosuite **构造期未播种**的物体尺寸随机化钉死。这条路在 1.5.2 上成立：

```
robosuite 1.5.2  utils/mjcf_utils.py:489   rng = np.random.default_rng()      ← patch 生效
robosuite 1.5.1  utils/mjcf_utils.py:500   np.random.uniform(...)             ← 走全局 RandomState，patch 完全无效
```

后果是**同一个进程内连建三次环境会得到三个不同的 cube**，而且没有任何报错。
这比跨进程不可复现更糟：它让「同进程配对比较」这个当时唯一还成立的保证也失效了。

**证据**：装回 1.5.2 后几何恢复，并与 09-24 的记录逐位相同
（`size=[0.0219796, 0.0210383, 0.021705]`、`mass=0.080293`、
`bottom_offset=[0,0,-0.021705]`、`horizontal_radius=[0.0304255]`）。
`scripts/b_selfcheck_reproducibility.py` 的 L0-a（进程内 3 次构造）与
L0-b（跨进程）现在都是单一 hash `752ff735ed145948`。

### 缺陷 3：门禁里有一个恒真断言（防线层，最该记住的一条）

`scripts/b_selfcheck_reproducibility.py` 原本有一项
「robosuite 版本与 requirements.txt pin 一致」，实现是 `record(..., True, ...)` ——
它只把「requirements.txt 应 pin 同一版本」当**提示文字**打印，从不真的去读那个文件。
所以缺陷 1 发生之后，自检**全绿**。

**门禁里存在恒真断言，比没有门禁更危险**：它提供了虚假的保证，让人不再手工核对。

**修复**：改成真读 `requirements.txt` 与 `requirements.lock.txt` 并与实装版本比对
（L0-f / L0-g），并新增 L0-h —— 扫 `runs/**/model_*.pt` 的 `obs_dim`，
自动产出与当前环境失配的 checkpoint 清单，不再靠人记住哪些作废。

## 3. 附带澄清：`OMP_NUM_THREADS` 敏感性是伪结论

事故期间观察到「结果随 `OMP_NUM_THREADS` 变化」，当时被当成需要钉死线程数的证据。
实际上那是缺陷 2 的症状：每次构造环境都换 cube，看起来就像线程数在影响结果。
1.5.2 下重测，开环探针在 `OMP=1/2/4` **完全一致**
（`runs/infra/b_reproducibility/selfcheck.json` 的「线程数敏感性」项）。

结论：**不需要**为了可复现性把线程数钉成 1（当然为了性能与确定性仍建议钉），
之前基于「线程敏感」做出的任何推断都要重新看。

## 4. state obs 维度随版本改变

| robosuite | Lift state obs 维度 |
|---|---|
| 1.5.1 | **53** |
| 1.5.2 | **60** |

所有 `obs_dim=53` 的 checkpoint 与当前环境**结构性失配**，加载即错，不是精度问题。
L0-h 会自动扫出来。obs 布局的逐维语义见
`docs/b_normalization_incident_20260928.md` §2（同一批实测）。

**L0-h 的判据必须按 history 折算**：checkpoint 的 `obs_dim = 单帧维度 × history`，
所以 `hist4` 臂的 `obs_dim` 是 `4×60=240`（1.5.2）或 `4×53=212`（1.5.1）。
直接拿 `obs_dim == 60` 比会把合法的 240 误判成失配——L0-h 首版就犯了这个错，
现已改为 `obs_dim == 60 × history`。

实测扫描结果（2026-09-28，全部 `runs/**/model_*.pt`）：**兼容 8 个，失配 4 个**

```
runs/infra/b_act_lift_mb_hist1_seed0/model_best.pt    obs_dim=53   history=1  单帧=53.0
runs/infra/b_act_lift_mb_hist1_seed0/model_final.pt   obs_dim=53   history=1  单帧=53.0
runs/infra/b_act_lift_mb_hist4_seed0/model_best.pt    obs_dim=212  history=4  单帧=53.0
runs/infra/b_act_lift_mb_hist4_seed0/model_final.pt   obs_dim=212  history=4  单帧=53.0
```

**注意 `runs/infra/act_lift_k4_state_hist4_seed0/`（obs_dim=240）结构上是兼容的**，
不在本事故的作废范围内。它的闭环评测仍然 `INVALID`，但原因是**归一化输入契约违例**
（`docs/b_normalization_incident_20260928.md` §9），不是版本漂移——两个作废理由必须分开写，
否则 A 会以为要重采数据，其实只需要按 §6.1 改归一化后重训。

## 5. 作废清单（两条独立理由，不得混写）

**理由 A：版本漂移（本节）**——只有下列 4 个 checkpoint 及其闭环产物：

- `runs/infra/b_act_lift_mb_hist1_seed0/`（obs_dim=53）
- `runs/infra/b_act_lift_mb_hist4_seed0/`（obs_dim=212 = 4×53）
- 所有在 1.5.1 下跑的闭环比较（含当时的 minibatch「10/20 成功」——那是**另一个 cube**
  上的结果，与 09-24 的 base 记录不可比；重训钉死几何后同一策略只有 3/20）

**理由 B：归一化输入契约违例**（见 `docs/b_normalization_incident_20260928.md` §9）
——范围大得多，包括 A 的 `act_lift_k4_state_*` 全部三个臂和 B 重训后的无截断评测。
这一条**不作废 checkpoint**，只作废「用它测出来的成功率」。

**不作废**：
- `runs/infra/b_env_rebuild/base_truth20.json` —— 1.5.2 下复现 scripted base
  **20/20、`mean_max_rise=0.076330`**，与 A 的 09-24 记录逐位相同，是本次修复有效的判据
- 全部离线探针（不碰 robosuite，输入从未越界）
- `runs/infra/act_lift_k4_state_hist4_seed0/` 的 checkpoint 本身（obs_dim=240 兼容）

## 6. 现在的强制协议

接触实验前后各跑一次：

```bash
source /root/venvs/rlrobot/bin/activate
OMP_NUM_THREADS=1 MUJOCO_GL=egl python3 scripts/b_selfcheck_reproducibility.py \
  --repeats 2 --omp-list 1,2,4 --json-out runs/infra/b_reproducibility/selfcheck.json
```

必须全过的项目：L0-a/b 进程内与跨进程几何钉死、L0-c 与 09-24 记录一致、
L0-d `obs_dim == 60`、L0-e raw obs 键集合一致、**L0-f 实装版本 == requirements.txt 的 pin**、
L0-g lock 与 pin 一致、**L0-h 既有 checkpoint 的 `obs_dim == 60 × history`**、
L1 reset 可复现、L2 前向可复现、L3 动力学可复现。

2026-09-28 实测：L0-a~L0-g 与 L1/L2/L3 **全部 PASS**
（`runs/infra/b_reproducibility/selfcheck_v11b.json`，10 项）；L0-h 报出上表 4 个失配
checkpoint，即预期行为（它的作用就是自动产出作废清单，不靠人记）。

任何一项不过就**先修再跑**。`scripts/setup_env.sh` 末尾已经会自动调它。

## 7. 遗留决策（需要用户拍板，B 不下放）

1. **是否 `git init`。** 仓库目前不是 git 仓库，「代码版本」这一栏在三线实验记录里
   事实上无法填写——这是监管 P0 的第一项，现在不满足。障碍是 90+ 个 `runs/` 目录、
   大产物、NAS 共享目录，需要先定 `.gitignore` 与 `runs/` 是否纳管。
2. **`work/decisions/` 写在哪。** v4 要求路线变更登记在 `work/decisions/`，
   但那个目录在只读的 `RL_Harness_v4_20260924/` 里。B 倾向在仓库根建镜像目录
   `work/decisions/`，待授权。本文与归一化事故文档目前先落在 `docs/`。
