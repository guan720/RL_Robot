# 固定参考动作约束、ConRFT 与 FRS 补核

2026-09-22。VLA-only，弱任务策略，可少量示范及接管；不涉及 ACT。本文件只读原始资料，未运行训练。

## 区分三种约束

1. RLT：输出动作向基础 VLA reference 靠近。它是软正则，不能直接解释为硬动作上限；其利弊取决于 reference 质量与权重。原作对已有技能先验的消融显示 BC 有价值，不能只去掉全部 BC 就宣称改进。
2. ConRFT：BC 目标来自示范／混合回放动作，同时用 Q 改进。约束对象可以随新增示范、纠正和有效经验演化，不是永远回到一个冻结的 VLA 输出；但仍会受数据质量和分布限制。
3. HiL-ResRL：基础动作加缩放残差，论文明确限制幅度以保留局部修正。即便不写固定 reference 的 L2，也没有完全解除基础行为限制。

来源：[RLT](https://arxiv.org/html/2604.23073v1)、[ConRFT](https://arxiv.org/html/2502.05450v2)、[HiL-ResRL](https://arxiv.org/html/2606.22860v1)。

## ConRFT / HIL-ConRFT：成熟 VLA 路线的重要参考

中科院自动化所、国科大团队，RSS 2025 正式发表；官方仓库 Apache-2.0，明确基于 HIL-SERL 环境，主要提供 Octo 与 Franka。它是已有“VLA＋HIL”方案，不需要把两者兼容性完全当未知。[RSS](https://roboticsconference.org/2025/program/papers/19/)、[代码](https://github.com/cccedric/conrft)

原论文算法 1 随机初始化 consistency 动作头与 critic，用 20–30 条任务示范进行离线 BC＋校准 Q 学习，再进入人类接管在线学习。在线 BC 用示范与在线 replay 的真实动作；接管数据进入 demo buffer；逐步降低 BC 权重、提高 Q 权重。不是无约束策略，也不是无示范起步。

尤其需要纠正“直接更新 VLA”的含混用语：论文 §VI-B 明确视觉编码器和 transformer backbone 冻结，在线训练 consistency 动作头。不是全量更新原始 VLA，也不是直接微调 π0.5 原 flow action expert。论文还报告 Kosmos-2/PaliGemma 表征的试验，但公开主要工程入口仍为 Octo；π0.5 接口与双臂需适配。[机制、损失、限制](https://arxiv.org/html/2502.05450v2)

8 项真机实验，作者报告平均 96.3%，每任务最终 20 次评估；不能据此保证松灵任务成功率。官方仓库本次网页 371 stars / 25 forks，仅反映关注度。尚未核实数量明确且同协议的独立跨机构复现，不声称它比 HIL-SERL 更经广泛验证。

## FRS：2026 年值得保留的新方向

Flow Reversal Steering，arXiv 2026-06-11；Stanford / UC Berkeley，作者包括 Chelsea Finn、Sergey Levine。它将人类或 VLM 提供的合理动作经 flow 反演为噪声，用于引导冻结 π0.5 的动作生成；DSBC 学这些噪声，随后可做 RL。它不强迫靠近原 VLA 默认采样出的错误动作，但仍依赖基础 flow 所承载的行为先验。[论文](https://arxiv.org/html/2606.13675v1)、[项目](https://flow-reversal-steering.github.io/)

真实 DROID/Franka：6 任务的 DSBC 各用 10 条成功人工引导轨迹；另用 20 条普通遥操作训练离线 DSBC。**真机也有 RL**：挂毛巾任务从基础 5%，到 DSBC 50%，再到 RL 80%。附录 F 的真机 RL 是两轮各 10 次 rollout 后的批次 policy gradient，不是 LIBERO 中那套完整 SAC 实验。各评估 20 次，不能把 5% 视为精确已知概率，也不能把单任务效果推广为任意弱先验。

低成功率较广的 RL 对照主要在 LIBERO；先验技能在 DROID 数据中已有，只是在新情境下难以被调用。故该结果支持“弱默认行为可以借人类提示启动”，不证明“基础模型完全没有相关技能也能少样本学会”。

项目页本次仍写 Code (Coming soon)，未核实作者完整仓库。检索到的第三方 THyanNK/FRS 明确有 scaffold 与接口待接，不能冒充原作代码或独立性能复现。综上列为研究备选，不把 PI0.5 真机结果与完整开源成熟度混同。

## HiL-ResRL：没有解决当前的核心限制

2026-06-22 预印本，有 π0.5 真机实验，但动作是基础策略加 λ 倍残差，λ∈[0,1] 被明确用于限制覆盖基础动作的程度。它适合局部修正，不能只因含 HIL 且较新就认为优于 HIL-SERL 或适合无可用行为先验。本文原始页面未给可核查的完整训练仓库入口；本轮不提升为首选。[论文 §III-C](https://arxiv.org/html/2606.22860v1)

## 可验证的改进方向

保留 VLA 表征/token 和完整动作输出头；分开可靠人类动作 BC 与固定 VLA reference BC。原版作为对照，另试低 reference 权重／零 reference 权重但保留人类动作监督。不要同时取消所有约束；不要将初期失真的 Q 当作可靠动态门控。若不再使用 reference，准确命名为“VLA 表征驱动的离策略动作学习”，不继续声称完整复现标准 RLT。

这种做法保留 HIL-SERL 成熟的数据采集和接管机制，改变的是模型接口和学习约束；它仍需少量示范、可靠奖励、动作接口与恢复流程，并不能自动保证少人化。
