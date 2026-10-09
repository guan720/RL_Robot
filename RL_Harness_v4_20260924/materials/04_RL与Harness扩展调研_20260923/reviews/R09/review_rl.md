# R09 独立审查：RL 与异步执行

日期：2026-09-23。结论：**PASS**。正式问题 **12 项，12 项通过；必要修订 0 项**。仅通过文稿逻辑，非实现或真机验证。

已只读加载指定科学家入口、科研 SKILL/RESEARCH。未读其他审查或继承PASS；未UPDATE/goal、写库、安装训练或操作真机。

初始枚举：共享 θ 与目标；弱起点及动作覆盖；建议和真实 TD；队列一槽因果；提前终局；抢占删失；梯度及部分监督；RAPolicy 的 V、latent、hold／反馈；RT-EXPO 时间协议；算法 fork 与平台。合并为下列12问。

定位缩写：M=03/01 技术方案；I=03/02 接口契约；A=03/06 异步附录；E=03/README；R=04/01 深度报告；V=04/research/01 VLA；U=04/research/02 自主复位；H=04/research/03 Harness；P=04/research/04 平台。03、04 指 input 内两个对应目录。九份文件均枚举；算法时序细读，其余按接口选读。

## 独立来源学习

本轮实际打开3篇原文及以下固定源码：

- S1：[RAPolicy v1 §III–IV](https://arxiv.org/html/2609.22888v1)。核Q/V、latent、条件回归和实验条件。
- S2：[RT-EXPO v1 §IV、附录 VII-E.3](https://arxiv.org/html/2609.18207v1)。核慢候选／快编辑及延迟条件。
- S3：[SmoothRL v1 §3.1–3.3](https://arxiv.org/html/2608.29768v1)。核C/E/D、2n回报与E梯度。
- S4：[RAPolicy 固定 worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)。选读 critic、likelihood、actor评分及数据保留，核V备份／done／噪声。
- S5：[固定 chunk 工具](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)、[离线 latent](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)。选读 prepare_chunk_transition、resample_offline_latent，核固定块、折扣及离线噪声。
- S6：[固定 RT 学习器](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)。选读三种update及候选选择，核更新路径和折扣。
- S7：[RAPolicy 固定任务配置](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml)、[README](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md)。沿launcher读继承配置，核v2_awac、固定块、hold和资产缺口。

仅静态选读，非全库审核。urllib曾连接重置，浏览工具成功读取。

## 12 项审查问题与判定

**1. 换目标是否保留同一θ、区分学习问题？**
反例：物体在 B，正向成功后把正向 Q bootstrap 到反向起态，或分别挑双向最佳模型冒充共享。
定位：M§5（L91 起）、I§5.2/5.5、E 首段；依据：目标条件 Bellman 定义，S1只支持共享可行性。
**PASS。** goal 贯穿 actor/Q/target/reward/replay，换向切 episode、清队列，同 checkpoint 双向发布。正迁移／覆盖待测。

**2. 零成功是否被误当无启动信息也能学会？**
反例：全零奖励、无可信纠正、动作支持又缺少闭爪；不断采失败并不会产生正确抓取监督。
定位：M§2、§10.2、V§11.1、U§7；依据：S1 的十示范弱起点实验及其人工接管条件。
**PASS。** 文稿区分零成功与零信息；保留同预算动态 BC 对照和动作覆盖预检，允许原生头胜出。未由完整头自由度推出更省样本。

**3. 建议、已提交未激活、终局请求是否区分？**
反例：Harness 建议 B，机器人执行 A，却给 B 配 A 的后继；另一极端是将真实入队 U 一律删作“未执行”。
定位：A§2.2–2.3、§4.2、§5.1；I§5.1/5.4；依据：实际干预的因果转移定义。
**PASS。** 普通TD需请求、提交及next queue；建议只作监督。真终局例外保留事前请求的原在途计算，不能事后补 admission 或新算 U。请求证据待验收。

**4. 旧C产生奖励是否错配U？**
反例：t=100、n=6，回报取100–105，却将 next state 写112；或改取106–111奖励仍用106状态。
定位：A§2.3、§3、§9例1；依据：队列增广推导，S3 用作不同目标的参照。
**PASS。** X_next.C=U 已是本轮动作的环境后果，物理收益在后续链传播；R_n 与 γ^n、t+n 对齐。文稿明确不冒称 SmoothRL 原版2n目标。A§2.4未冒称完全Markov。

**5. 提前终局是否丢奖或选择性回填？**
反例：下槽第三步得1，将前驱临时改成长回报，未成功前驱仍用无条件 bootstrap，会产生选择偏差。
定位：A§5、§9例3；I§5.3/T11；依据：Bellman终局边界。
**PASS。** 原请求 U 配 R_L 的 critic terminal 行，无后继队列；前驱仍统一一步递推。取消激活行不作 actor-Q 更新的存活加权偏差已明示，不能再当遗漏；事件／返回时间已分开。

**6. 后续抢占是否篡改前驱转移？**
反例：106边界 U 已提交，108抢占；把100起转移的 next queue 倒填为抢占动作，或将108强制标真终止。
定位：A§3.3、§6–7、§9例5；I§5.3、T07/T12；依据：因果时间边界。
**PASS。** 准确的106边界允许保留前驱；106起受破坏槽隔离，边界本身不明才扩大隔离。文本承认删失并不消除接管选择偏差，要求报告数据密度和保留独立尝试；

**7. Q梯度与BC部分标签是否混用mask？**
反例：当前网络重预测 C 后得到价值梯度；D 从未入队却被奖；缺失动作先进入 flow 加噪／attention，最后乘 loss mask。
定位：A§4、§9例2；I§5.4/T13–14；依据：S3 的动作梯度边界。
**PASS。** 真实 C 固定，Q 动作路径仅经 E；参数共享可间接改变其他输出已说明。BC 独立判质量与监督粒度，未知 token 处理未验证就不进入分支。投影／平滑也要求进入明确动作边界，不能静默改写。

**8. RAPolicy的V是否被误称当前policy价值／梯度？**
反例：replay 中 Harness 能救回状态，V 很高，便宣称当前 actor 已会救回；或沿用 -Q(X,π(X)) 代替原生目标。
定位：V§11.1/11.3–4、M§10.4、R§4.3；依据：S1、S4。
**PASS。** 文稿正确描述 expectile V 备份及优势加权回归，明确没有新动作的 Q 梯度，不混入队列参考 loss。辅助行为覆盖与当前策略可达性不同，须用关闭辅助的双向评估；这已是明确门槛。

**9. latent缺失与真实后果是否混同？**
反例：无原始噪声的真遥操被全部拒出 Q；纯影子建议随机配 z 后被当真实 TD。
定位：M§10.4（L295）、V§11.3、I T39；依据：S4 likelihood 分支、S5 离线重采样。
**PASS。** 在线保留 rollout z；离线 actor 监督模式另定，真实示范 TD 资格按后果与协议独立判断。重采样是条件 log-density 的期望，不是专家噪声反演。版本兼容待实测。

**10. RAPolicy的hold／填充／反馈能直接接连续队列吗？**
反例：把终局尾部补齐的 hold 当实际执行，或把看到新图后逐步纠正的十步轨迹倒填为旧状态一次生成 U。
定位：V§11.3、A§4.3/§11、H§5.3；依据：S5 固定块检查、S7 hold 配置。
**PASS。** 已区分训练并发与C/E/D；终局填充只是张量约定，真实有效区间另记。队列版 Q/V/actor、E 监督、latent、终局／接管尚待独立定义，禁止提前混 replay；

**11. RT-EXPO是否被误当相同时间／信息／梯度协议？**
反例：快编辑读取 t+d 图像，却在本项目写成仅依据 t 的 U；将额外100ms sleep与 d步旧帧相加；用97%证明本机 deadline。
定位：V§4.3–4.6、A§11、R§4.2、M§10.2；依据：S2、S6。
**PASS。** 原生 RTC-BC 与有界编辑-Q 分离，较新观测、执行窗及 filtered backup 单列；两种延迟实验分开。候选覆盖、共享 goal 和纠正入口须改造，信息／预算匹配后才能比較；公开实时代码确已纳入竞争。

**12. 方法fork、平台、本体适配是否被混排？**
反例：RAPolicy 仍 import rlinf，便与上游 HEAD 混装；确定性队列 actor 为满足 SAC worker 填假 logπ；因缺 AgileX 即排除算法。
定位：P§1/10/13、M§10.1/10.4、I T36/T39及§9.1、R§8–9；依据：S7 的包命名、入口和发布范围，接口一致性推导。
**PASS。** fork 与运行时分别锁定；平台默认 target 需替换，I末段已明确确定性目标不继承熵备份。通用 schema、单 Gateway 优先，品牌只计移植成本。未冒称已集成。

## 必要、待测、可选

**必要修订：无。待测：**双向独立增益、纠正质量、连续队列改造、尾延迟／TD密度、终局／抢占偏差，均已有实施门槛。**可选：**将三协议整理为信息时刻／动作域／回报窗／折扣／latent／终止的开发选型卡，不阻断本轮。
