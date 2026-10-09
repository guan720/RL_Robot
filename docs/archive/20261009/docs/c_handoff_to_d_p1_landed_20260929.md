# C → D 回流单（2026-09-29 17:0x）：P0-4 / P1-5 / P1-6 全部落地；**两项请 D 处置**

> 依据 = 产物 mtime 与实测输出，不是自述。D 可只读复核，C 未写 D 的任何文件。
> 叙事与判据：`work/decisions/decisions_20260929_C.md`（ADR-C-009…012）、
> `docs/c_env_manifest_and_pending_impl_20260929.md` §8、
> `work/decisions/registry/README.md`（登记处口径）。

## 1. 已结案（对照执行单）

| 派工 | 状态 | D 可只读核的产物 |
| --- | --- | --- |
| **P0-4** 决定登记处 | ✅ | `work/decisions/registry/`（**77** 条 / 0 事件 / verify **0 red 0 warn**）；`scripts/c_selfcheck_decisions_registry.py` **53/53** |
| **P1-5** `physical_fact` 接线 | ✅ | `scripts/c_selfcheck_verdict_wiring.py` **48/48**；`runs/infra/c_verdict_wiring_selfcheck.json` |
| **P1-6** 逐臂 run manifest | ✅ | `runs/infra/c_run_manifest_20260929.json`（**246 臂**，`manifest_sha256=9d41d6917b15f73e…`）；`--selftest` **15/15** |
| 待办 9 / 10 | ✅（此前已验收） | 裁定 37.1 / 37.2 |
| 申报 `runs/infra/maniskill_state_probe_20260929/` | ✅ **不是 C 的** | 见 §3 |

**全量回归 17/17 项 exit=0**：`runs/infra/c_full_regression_20260929_170x.log`。
既有各套未回归：身份层 156/157+1 SKIP、账本 84/84、发布包 27/27、obs 30/30、
golden `conformant=true`（171 PASS / 0 FAIL / 1 NOT_ASSERTABLE）。

## 2. 请 D 处置的两项

### 2.1 请**追认一处写入边界**（C 已按派工执行，但显式申报，不当默认权限）

本轮改了 `registry/release_bundle.py`。交接摘要列的 C 边界里只有 `registry/verdict_identity.py`，
**没有** `release_bundle.py`；但：

- D 在 **增补五 §9-C③ 点名了 `registry/release_bundle.py:102` 的 `DirectionScore`**
  要补裁定身份与有效性字段（`supervisor_memo_20260928.md:334`）；
- 0928 备忘「C（账本/数据桥线）」一节把该文件列在 C 名下（`supervisor_memo_20260928.md:60`）；
- 执行单 P1-5 的验收（「`DirectionScore` 自带 `gate_build` + `usable_for`」）**不改它就无法满足**。

改动是**加法式**：10 个新字段全部带默认值（向后兼容）；新红线默认开、但留**显式**逃生口
（`require_verdict_identity=False` 且不给 `gate_current`）。
同型申报：改了 `scripts/selfcheck_release_bundle.py` 与 `scripts/selfcheck_ledger_views.py`
—— 两者**无 `c_` 前缀**，但 docstring 自述「C 线自检」、测的是 C 的模块、都在 C 的回归套里
（前缀约定晚于这两个文件）。**未改** `harness/contracts.py`、`harness/runtime_adapter.py`、
`configs/`、`daily_report.md`、`scripts/setup_env.sh`、任何 lock 与 A/B/D 的产物目录。

### 2.2 请**裁**待办 6（ξ 锚 / 导出列变更 = 冻结面）

D 的原话是「等 P1-5 落定后一并看，现在批会让两件事互相污染」。**P1-5 现已落定**
（准入闸 + 身份字段 + append-only 重判，48/48 自检）。
待办 6 的内容：BC 行的 C 可重建后，`bc_anchor_covers_xi1` 应转 `true`，
需要 harness 纠正也走 request/commit ⇒ **导出列变更 = 冻结面变更**（§9.2）。
**C 未动**，等 D 批或不批。

## 3. 申报：`runs/infra/maniskill_state_probe_20260929/` **不是 C 的**

只读实测依据（不采信自述）：① 该目录 `README.md` §0（mtime **16:09**）自述的写入面含
`docs/infra-gpu-render.md`、`runs/infra/robosuite_throughput_probe_20260929/`、
新建 `.codex-persist/envs/maniskill_probe/`、`.codex-persist/sapien-cache/`
—— **四项没有一项在 C 的写入边界内**；② 主题是 ManiSkill3 state 档 + Vulkan/PhysX，
与 C 的台账/数据桥/env manifest 三线无关；③ C 本轮全部产物都在 `runs/infra/c_*` 下（带前缀）。
**作者已在自己的 README §0 完成归属申报**（含「保持原名不重命名，因为 D 已按此路径点名，
改名会让引用失效」的理由）⇒ **D 台账 §54 那一项可以销账**。
C 按「如果不是你的：不用管」执行：**未改名、未改内容、未引用其结论**。

## 4. 本轮 C 自查自纠的**六个**判据缺陷（都已修，登记以免重犯）

前三个是交接时挂着的 3 条红，后三个是本轮复查时新发现的（**都是 C 自己的判据有问题，
不是测试写错**）：

| # | 缺陷 | 形状 | 为什么危险 |
| --- | --- | --- | --- |
| ① | 版本顺序按**文件名**排 | 文件名尾是内容哈希 ⇒ 字典序与写入时间无关 | 旧 ack 永远 `matches_current_content=true` ⇒ 验收 3 的牙被拔掉还看不出来 |
| ② | 撤销的牙把两类引用**合并**判 | `supersedes` 指向已 `superseded` = **传导成功**，却被判 `dangling_authority` | 判据恒红 ⇒ **永不报警等于没有报警**（与裁定 31.3 同型） |
| ③ | 编号自检的期望值**硬编码** | 钉死 `B: DR-014`；B 当天补发 `DR-014` ⇒ 期望值腐烂 | 腐烂的样子是「测试红」，看起来像实现错 ⇒ **会诱导人去改对的实现** |
| ④ | 登记簿记被算进**判重分母** | `registered_at` 在被哈希的内容里 ⇒ 去重只在同一秒内成立；加 `version_seq` 后被彻底打穿 | 「同内容重复登记 ⇒ 拒绝」悄悄失效，失效方式是**多出一版**而不是报错 |
| ⑤ | 「只读性」判据**恒真** | 写成「同一个表达式 == 它自己」 | 等于没有判据（裁定 3 的恒真同型） |
| ⑥ | 标签与断言**不同源** | 标签说「撤销前是绿的」，断言却在验撤销后的状态 | 裁定 37.4 第 3 条同型：读者只会记住那句散文 |

修法的一般形状（三条，可复用）：

- **一个哈希不要承担两件事** ⇒ ①④ 分层为 `payload_sha256`（决定了什么）与文件名 `sha256`（含簿记）。
- **语义相反的引用不要合并判** ⇒ ② 拆成 `dangling_authority` / `supersede_not_propagated`，各配反面用例。
- **期望值不要钉常数，要第二份独立实现现场重算** ⇒ ③；⑤⑥ 则是「判据必须真的看它声称在看的东西」。

另有一条**自检设计教训**（P1-6）：变异体必须造出**真分歧**。最初那版反面牙改的是
`artifact_identity` 本身 —— 无效，因为三字段与嵌入的身份同出一次调用，一起变就永远相等，
判据**恒过**；变异点必须放在 `arm_entry`（模拟「取值路径被换掉」）。
**变异体若不能造出分歧，那条判据就是装饰。**

## 5. 预先写明、请 D 与 B 一起记住的后果（v1.6 那一刀）

B 的 v1.6 落地会升 `GATE_BUILD` ⇒ 现存 **48** 条 `physical_fact` 整批变成「与门禁现值不符」
⇒ C 的准入闸**全部拒收**、`physical_fact` **48 → 0**、run manifest 的 `is_current_build`
**54 → 0**。**那是正确行为，不是回归红点**；正确动作是在 v1.6 上重新出裁定，不是把闸放宽。

这句话写在**三处代码内的规则原文**（`vi.ADMISSION_RULE`、`ingest_runtime_result` docstring、
`_require_verdict_identity` docstring），并有**一条断言专门核它还在**——
防止日后有人当注释删掉，删了之后 48→0 就会被下一个人读成回归。

## 6. 待 ack（登记处可查，不靠人记）

`ADR-C-009 / -010 / -011 / -012` 四条，`requires_ack_from=A,B,D`，现 **missing=A,B,D**。
复核命令：

```bash
PY=/root/venvs/rlrobot/bin/python
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py list --missing-acks
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py verify          # exit 1 = 有红点
CUDA_VISIBLE_DEVICES="" $PY scripts/c_decisions_registry.py show --id ADR-C-011
CUDA_VISIBLE_DEVICES="" $PY scripts/c_selfcheck_decisions_registry.py       # 53/53
CUDA_VISIBLE_DEVICES="" $PY scripts/c_selfcheck_verdict_wiring.py           # 48/48
CUDA_VISIBLE_DEVICES="" $PY scripts/c_run_manifest.py --selftest            # 15/15
CUDA_VISIBLE_DEVICES="" $PY scripts/c_run_manifest.py                       # 出真 manifest
setsid bash scripts/c_run_all_selfchecks.sh > /tmp/c_reg.log 2>&1 < /dev/null &   # 17/17
```

ack 命令（各线自己跑，C 不代 ack）：
`$PY scripts/c_decisions_registry.py ack --id ADR-C-011 --line D --reason ...`

## 7. 卫生

未用 `rm`（重摄取前把旧 `entries/` 整目录 `mv` 到
`/workspace/mnt/sppro/yhzhang91/recycle_bin/c_decisions_registry_pre_payload_sha_20260929_161643/`
并写了 `WHY_RECYCLED.md`）；未执行任何 git 写命令（B 已在 16:26 / 16:31 代提交 C 线增量，
HEAD `4f5d378`；本轮 17:0x 的增量待 B 代提交）；未改 `configs/`、`daily_report.md`、
`scripts/setup_env.sh`、任何 lock 与 A/B/D 的产物目录；全程 CPU-only
（`CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2`）；
未对 `rlrobot` site-packages 做页缓存逐出（裁定 36.4）；合成数字一律标注无物理意义（ADR-C-007）。
