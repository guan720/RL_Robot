# R08 根审再次学习

本轮独立重读 RAPolicy 固定提交的 [Pick Banana 配置](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml)、[真实 chunk 执行](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/envs/realworld/realworld_env.py) 和 [transition 数学工具](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)。

配置中实际有 `fixed_chunk=True`、`chunk_aware_discount=True`，环境 override 指定 fixed chunk／inference hold／10Hz；首个 find 未匹配完整词后继续读取 hold 上下文，取得对应行，未将一次搜索未命中视为字段不存在。代码区分接管后真实 hold 与终止后吸收填充；后者不执行、时长 NaN，而 fixed chunk 的训练 mask 可为真。prepare 函数明确逐步 γ 与按块 γ 两种模式。

这再次支持“上游内部训练表示不能覆盖项目物理账本”和“不同协议先独立验收”的当前决定。冻结输入已限定论文条件、原版 hold 与新队列改造，未发现需根审先行修订的事实。没有运行框架或机器人。三份正式独立报告完成后再记录合并结论。

## 合并结论

已全文阅读三份正式报告：RL 24问、Harness 20问、证据22问，全部 PASS，必要修订均为零。根审重新阅读 VLA 专题开头，采纳两名审查员共同提出的可读性建议：旧摘要仅列完整头／RT-EXPO，与 §8／§11 的 RAPolicy 新优先级不同步。已将开头摘要与地图同步为完整头参考、原生 RAPolicy 优先预检、RT-EXPO 实时路线及 TD3＋BC 补充。没有新增候选或改变后文机制。

完整可续训 bundle 已在接口§6.1要求，原版评测导出不足的可选测试例不必重复改设计；分来源行为统计也属于既有验证的实施细化。其余待实测门槛继续保留。

根结论为 **NEEDS_REVISION（采纳可选摘要同步），连续计数归零**。不将审查员 PASS 改写成其发现必要错误；因为冻结科学文件变化，下一轮重新冻结。未开展实现或实测。
