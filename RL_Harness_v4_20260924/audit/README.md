# 交付包审查与溯源入口

本包接手材料与依赖整理分别接受了独立审查，根审完整读取并复核，两项均通过、无剩余必要修订：

- [开发者与Codex接手审查](reader_review.md)：阅读顺序、实施阶段、模板、主版本及可选讨论边界。
- [依赖与版本审查](dependency_review.md)：来源原字节、引用闭包、五轮去重映射、缓存排除与校验器行为。

这两项是2026-09-24的交付整理检查，不替代或重计v4原有五轮科学设计审查。最新科学内容保持原字节，原审查报告位于`materials/06_…/reviews/`。

[来源文件表](source_files.json)、[五轮快照映射](review_snapshot_map.json)、[排除清单](packaging_omissions.json)与[旧绝对路径映射](legacy_path_map.json)用于追溯搬迁过程。原五轮每轮564项中，309项非Git内容保留并核验，255项Git内部元数据不分发。

交付根`MANIFEST.json`覆盖发布文件。使用`python -B tools/verify_package.py`从包根执行离线检查；加`--details`可展开上游摘录和历史快照的链接核验排除清单。校验器成功不等于算法、机器人或安全性能已验证。
