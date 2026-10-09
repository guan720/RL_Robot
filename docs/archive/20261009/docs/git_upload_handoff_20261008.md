# 2026-10-08 组织仓库上传交接

- 用户本次明确要求上传到 `https://code.iflytek.com/xhzhang52/RL_Robot.git`，覆盖旧文书中暂缓外部推送的决定。
- 原项目已有 `master` 与未提交修改。原历史包含明文 API key，因此发布当前代码快照，不上传原历史；原项目的历史、索引和代码保持原状，仅新增本交接件。
- 上传副本：`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot_iflytek_upload_20261008`，分支 `master`，remote `origin` 为上述地址。
- 副本纳入已有跟踪文件及当前新增源码、配置、文档，包括 `min_grasp_pi05/code`；排除训练产物、权重、数据、临时文件和源码备份。副本 `REMOTE_ENDPOINTS.md` 的 key 替换为占位符；原文件不改。旧 key 是否已轮换未经验证。
- 副本设置 `user.name=xhzhang52`、`user.email=xhzhang52@iflytek.com`。全局设置失败：`/root/.gitconfig` 所在文件系统只读。
- 当前阻塞：本容器无法连接目标服务。`git ls-remote` 报 `Couldn't connect to server`；目标域名解析失败，配置的 HTTPS proxy TCP 连接报 `Operation not permitted`。远端是否为空、认证是否可用尚未验证，不能据此宣称上传成功。
- 准备与清单保存在副本 `.git/upload-record/`，不纳入提交。恢复可访问目标服务的环境后，从上传副本执行 `git push -u origin master`，再核对 `git ls-remote origin refs/heads/master` 与本地 `git rev-parse HEAD` 一致。
- 禁止从原项目直接推送旧历史；遇到远端已有提交时先取回并比较，禁止直接 force push。

## 后续变更：GitHub 目标

- 用户改用 `https://github.com/guan720/RL_Robot.git`；上传副本的 `origin` 已改为该地址，原仓库未设置 remote。
- 当前待推送提交仍为 `84fd72ea56b4f23046c5836d6ff327fce8bb7290`，`master`，641 个脱敏源码/配置/文档文件。
- `git ls-remote` 和实际 `git push -u origin master` 均失败：`Couldn't connect to server`；额外测试关闭代理后报 `Could not resolve host: github.com`。上传未完成，认证与远端现有内容尚未验证。
- 记录在上传副本 `.git/upload-record/github_push_result_20261008.json`。网络恢复后从该副本执行 `git push -u origin master`；不要从原仓库推送含明文 key 的旧历史。
