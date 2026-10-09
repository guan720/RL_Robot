# R07 根审再次学习

独立重新打开 LeRobot 固定提交下的 [算法接口](https://raw.githubusercontent.com/huggingface/lerobot/fbb811fca92504439792b97d216f0d00c2268382/src/lerobot/rl/algorithms/base.py) 与 [online/offline mixer](https://raw.githubusercontent.com/huggingface/lerobot/fbb811fca92504439792b97d216f0d00c2268382/src/lerobot/rl/data_sources/data_mixer.py)，继续审核训练运行时与方法分离的决定。

`update` 接收 trainer 所有的 batch iterator，`configure_data_iterator` 允许专门采样；这为独立纠正标签支路留出扩展点，但默认 mixer 仅混 transition。代码至少取一个 online 样本，不能将 ratio=0 当作纯离线启动。基类权重／状态接口也须由具体算法实现，不能因接口存在就宣称发布正确。平台专题§3/§10、技术T36已经要求验证采样、目标和发布，并未承诺原版开箱满足本项目。

冻结时 R07 与已通过 R06 的九份输入一致。三份正式报告已逐项读完，均为 PASS、12问。随后根审主动继续核查证据审查的 RAPolicy 线索，确认了改变候选资格的新证据，因此最终没有计入连续通过。

## 新证据与最终合并判断

根审实际重读 [RAPolicy 论文方法／实验](https://arxiv.org/html/2609.22888v1)、[官方仓库](https://github.com/flyfaerss/RAPolicy)、固定提交的 [value-backup 开关](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b104/rlinf/algorithms/awac_bootstrap.py)、[actor／critic worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b104/rlinf/workers/actor/fsdp_sac_policy_worker.py)、[异步 worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b104/rlinf/workers/actor/async_fsdp_sac_policy_worker.py)、[离线 latent](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py) 和 [launcher](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b104/examples/embodiment/run_rapolicy.sh)。

另外启动两项有界补核，分别独立查 [公开资产](rapolicy_asset_check.md) 与 [联合适配](rapolicy_joint_fit.md)，根审全文阅读。项目页工具失败后，经官方网页的实际读取和仓库核验确认有训练代码；固定完整 SHA、权重／数据未公开、infer hold、尾部吸收填充、真实 demo 的离线 latent 模式均有明确边界。

原生弱起点真机与共享任务证据，使其应优先于仅有对应仿真配方的原生 TD3＋BC 进入预检。既不将它判为整个框架最优，也不因缺少连续执行直接丢弃。主技术新增 §10.4／T39，研究报告和 VLA 专项补机制及代码；06 明确它不是现成队列实现。纯建议仍无 TD，真实无噪声示范的监督模式与 Q/V 资格分开。

RL 审查提及的投影措辞已在本次重开修订时一并澄清：解释器位于 learner 接口前与投影属于环境内部是两种不同合法边界，和既有02§2.1一致。

**最终 NEEDS_REVISION，连续计数归零。** 原三份正式报告没有被改判；这是根审接受实质新增候选与可选澄清后的主动版本修订。两份补核不冒充正式整轮审查。下一轮必须重新冻结；没有运行训练、设备或集成代码。
