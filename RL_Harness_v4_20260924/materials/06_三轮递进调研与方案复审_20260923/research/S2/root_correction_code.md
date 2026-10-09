# S2 根审：纠正 buffer 并不自动成为 TD buffer

2026-09-23，源码静态学习，未安装或执行第三方代码。第一轮已确认SDP有真机纠正研究，本轮改查数据与loss；目标是判断能否改进本项目Harness监督，不重复方法摘要。

## 1. 固定版本与阅读范围

通过GitHub API读取main与递归文件树，固定 `ZhaotingLi/Set_Supervised_DP@d973e38edb4cd742485b9b9bd283ce62d09f129c`。有限源文件缓存与SHA见 [manifest](evidence/root_sdp/manifest.json)。实际读到：

| 文件／函数 | 阅读范围 | 支持的结论 |
|---|---|---|
| `main-real-robot.py::train_interactive_learning_repetition` | 动作生成／真实step、纠正窗口、buffer调用和轨迹记录附近 | 在线收集正负纠正段；以人工反馈和键盘控制实验边界 |
| `Set_Supervised_diffusion_policy_image.py::TRAIN_Diffusion_with_Set_Supervised` | 919行起 | 入池主要是观测、偏好动作与非偏好动作；新纠正注入采样batch，后续继续重采 |
| 同文件 `compute_loss_Diffusion_Set_Supervised` | 781–977行 | 从desired set采样动作，再做加噪／去噪监督；可加视觉自编码器loss，没有本项目Bellman target |
| 同文件 `check_if_inside_desiredA` / `project_and_reflect_trajectory` | 82–181行及相关采样入口 | 正负差定义几何期望集合，不是环境可行域或碰撞检查 |
| `replay_buffer_setup.py` | 头部类型、HDF5字段与构造入口 | buffer支持观测、robot_action和teacher_action；格式存在不证明真实next-state对齐 |
| `feedback_window_buffer.py` | 类型及前110行 | 另一纠正窗口工具有独立数据结构；未证其用于上述真机入口，不将两条实现混同 |
| README／LICENSE | 相关使用段及全文许可 | 主仓MIT；有ROS1／Franka／外部镜像和实验文档依赖 |

[固定主入口](https://github.com/ZhaotingLi/Set_Supervised_DP/blob/d973e38edb4cd742485b9b9bd283ce62d09f129c/Files/src/main-real-robot.py)、[固定loss与训练函数](https://github.com/ZhaotingLi/Set_Supervised_DP/blob/d973e38edb4cd742485b9b9bd283ce62d09f129c/Files/src/agents/Set_Supervised_diffusion_policy_image.py)、[固定buffer装配](https://github.com/ZhaotingLi/Set_Supervised_DP/blob/d973e38edb4cd742485b9b9bd283ce62d09f129c/Files/src/agents/replay_buffer_setup.py)。低维policy文件与完整buffer文件下载TLS超时，未用失败访问推断它们不存在，也未声称读完这些文件。

## 2. 实际学习链与不适配处

纠正连续收集成Ta长度窗口，得到观测与正负动作段，训练器从持久buffer重采；期望集合中的合成动作作为去噪目标。这里“在线”“replay”指交互式模仿中的持续数据聚合，不等于off-policy TD。

真机入口向训练函数传递`next_obs`并带一处TODO，但所读SDP训练分支并不利用它构建Q目标，因此不能凭这个注释宣称SDP的TD有bug；真正结论是它不提供可直接照搬的本项目TD链。新纠正长期入buffer的思想可以吸收，环境转移仍须从本项目事实日志独立构建。

正负动作窗口也不能直接迁入固定队列协议：它来自连续人工反馈，部分动作可能依赖后续观察；本项目要核同状态、同goal、同C、同可用信息和同动作时段。动作被拒绝／发生接管并不自动证明它比替代动作差。由集合采样得到的动作没有真实后果，不进入真实TD。

## 3. 资产与采用决定

README给出仿真纠正HF数据和Space入口；本轮HF PickCan页面打开失败，未下载数据或核数据许可。另读外部Franka实验说明，确认仍需设备／相机／SpaceMouse等配置，文档含未补齐启动命令。主仓许可不覆盖所有镜像、驱动和数据的许可判断。[外部实验说明](https://github.com/ZhaotingLi/franka_docker/blob/fr3/docs/franka_exp_steps_to_follow.md)

**决定：保留为可信BC之后的纠正集合／偏好监督消融，不替换主要RL方法，不先于普通BC验证。** 其价值是避免把唯一纠正轨迹当唯一正确答案；局限是纠正质量、动作几何和时间一致性仍需验证。采用前须比较普通BC、集合监督与最终独立policy行为，不以集合内动作数量视为有效交互增加。

## 4. 移交S3的联合反例

1. 一个未执行提议被标负，替代动作成功：能否证明两者来自相同信息与起态？若不能，不构造强偏好对。
2. Harness用后续图像逐步纠正，却整段回填给旧观测：即使buffer永久保留，普通BC条件仍错误。
3. 合成动作接近纠正动作，却碰撞或夹爪时序错误：几何集合不提供物理保证。
4. 系统成功率提高而policy独立不提高：需要对纠正数据、有效TD与练习分布分别诊断，不只是增大BC权重。

相对S1的新增证据是固定源码中的buffer→集合采样→去噪loss链及真机采集窗口；本轮未声称新的真机结果或独立复现。
