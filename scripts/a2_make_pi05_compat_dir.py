#!/usr/bin/env python3
"""A2 / G2 —— 为 **lerobot 0.4.4** 造一个 π₀.₅ ckpt 的**兼容目录**（软链 + 过滤后的 processor JSON）。

## 为什么需要它（本轮实测）
`lerobot/pi05_base` 的 `policy_preprocessor.json` 里有 `relative_actions_processor`、
`policy_postprocessor.json` 里有 `absolute_actions_processor`，而这两个 registry 名在
**lerobot 0.4.4 里根本不存在**（实测 registry 全集 40 项，无此二者；0.4.4 源码树 grep 也只命中
无关的 `lerobot_train_tokenizer.py`）⇒ `make_pre_post_processors` 直接 ImportError。
ckpt 的 README 自己写的是 `pip install "lerobot[pi]@git+https://github.com/huggingface/lerobot.git"`
（**git main，不是 0.4.4**）⇒ 这批权重是**比 0.4.4 新**的 lerobot 存下来的。

## 为什么"删掉这两步"是**可证明的行为等价**，不是偷偷改口径
两步在 ckpt 里都是 `enabled: false`；lerobot main 的实现
（`src/lerobot/processor/relative_action_processor.py`，GitHub blob sha
`3405402904cf15ca18227b3a3fe006d7936f9d53`，本机已存 `tmp/a2_lerobot_main_ref/`）：
  - `RelativeActionsProcessorStep.__call__`：`if not self.enabled: return transition`（原样返回）
  - `AbsoluteActionsProcessorStep.__call__`：`if not self.enabled: return transition`（原样返回）
⇒ 二者对数据流是**恒等映射**，删掉不改变任何张量。

## 牙（防止这个 shim 日后变成"静默改口径"）
**只有同时满足「registry 里没有」+「config.enabled 明确为 false」的步骤才允许被删**；
任何其它缺失（例如某步存在但 enabled=true、或压根没有 enabled 字段）⇒ **非零退出、不产出目录**。
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import pathlib
import sys
from datetime import datetime

PRE = "policy_preprocessor.json"
POST = "policy_postprocessor.json"


RECYCLE = pathlib.Path("/workspace/mnt/sppro/yhzhang91/recycle_bin")


def recycle(target: pathlib.Path) -> None:
    """把要替换掉的旧文件 mv 到回收站（**不用 rm**，全局硬约束）。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    bucket = RECYCLE / f"a2_pi05_compat_dir_{stamp}"
    bucket.mkdir(parents=True, exist_ok=True)
    target.rename(bucket / target.name)


def installed_registry_names() -> list[str]:
    """已安装 lerobot 的 processor registry 全集。

    **registry 是惰性填充的**：`pi05_prepare_state_tokenizer_processor_step` 由
    `lerobot/policies/pi05/processor_pi05.py:48` 注册，只 import `lerobot.processor.pipeline`
    会漏掉它（本脚本第一版就踩了这个，结果守卫误报"缺失"）。所以先把真实加载路径上的
    模块 import 进来，再读 `_registry`。
    """
    import lerobot.processor  # noqa: F401
    import lerobot.policies.pi05.processor_pi05  # noqa: F401
    from lerobot.processor.pipeline import ProcessorStepRegistry

    names = sorted(str(k) for k in ProcessorStepRegistry._registry.keys())
    if not names:
        raise RuntimeError("processor registry 读到空集：枚举方式失效，停下。"
                           " 不许在空集上判定缺失，那会把所有步骤都判成可删")
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights-dir", required=True, help="原始 ckpt 目录（**只读**，本脚本不改它）")
    ap.add_argument("--out-dir", required=True, help="兼容目录（软链 + 过滤后的两个 JSON）")
    args = ap.parse_args()

    src = pathlib.Path(args.weights_dir).resolve()
    dst = pathlib.Path(args.out_dir).resolve()
    if not src.is_dir():
        print(f"源目录不存在: {src}", file=sys.stderr)
        return 2
    if dst == src or src in dst.parents:
        print("拒绝：out-dir 不能等于/位于 weights-dir 内部（不许污染原始 ckpt）", file=sys.stderr)
        return 2

    reg = installed_registry_names()
    dropped, kept, refused = [], [], []
    patched: dict[str, str] = {}

    for fname in (PRE, POST):
        raw = (src / fname).read_text()
        doc = json.loads(raw)
        new_steps = []
        for step in doc.get("steps", []):
            name = step.get("registry_name")
            if name in reg:
                kept.append({"file": fname, "registry_name": name})
                new_steps.append(step)
                continue
            cfg = step.get("config") or {}
            if "enabled" in cfg and cfg["enabled"] is False:
                dropped.append({"file": fname, "registry_name": name, "config": cfg,
                                "reason": "registry 里不存在，且 config.enabled 明确为 false（恒等映射）"})
                continue
            refused.append({"file": fname, "registry_name": name, "config": cfg,
                            "reason": "registry 里不存在，但**不是** enabled=false ⇒ 不许静默删"})
        if refused:
            print(json.dumps({"REFUSED": refused}, ensure_ascii=False, indent=1), file=sys.stderr)
            print("⇒ 兼容目录未产出。这条要报 D（可能需要升级 lerobot，那是断点变更）。", file=sys.stderr)
            return 3
        new_doc = dict(doc)
        new_doc["steps"] = new_steps
        # indent=2 与 ckpt 原文件一致 ⇒ 产出的 diff 里**只有被删的那两步**，没有排版噪声
        patched[fname] = json.dumps(new_doc, ensure_ascii=False, indent=2)

    dst.mkdir(parents=True, exist_ok=True)
    linked = []
    for entry in sorted(src.iterdir()):
        if entry.name in (PRE, POST) or entry.name.startswith("."):
            continue
        target = dst / entry.name
        if target.exists() or target.is_symlink():
            recycle(target)          # 全局硬约束：不用 rm，一律 mv 到回收站
        target.symlink_to(entry)
        linked.append({"name": entry.name, "bytes": entry.stat().st_size, "symlink_to": str(entry)})
    for fname, text in patched.items():
        target = dst / fname
        if target.exists() or target.is_symlink():
            recycle(target)
        target.write_text(text)

    diffs = {}
    for fname in (PRE, POST):
        a = (src / fname).read_text().splitlines(keepends=True)
        b = (dst / fname).read_text().splitlines(keepends=True)
        diffs[fname] = "".join(difflib.unified_diff(a, b, fromfile=f"orig/{fname}", tofile=f"compat/{fname}"))

    report = {
        "tool": "scripts/a2_make_pi05_compat_dir.py",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "morphology": "aloha_bimanual_14d",
        "src_weights_dir": str(src), "compat_dir": str(dst),
        "installed_lerobot_registry_steps": reg,
        "kept_steps": kept, "dropped_steps": dropped, "refused_steps": refused,
        "symlinks": linked,
        "diffs": diffs,
        "equivalence_argument": (
            "被删的两步在 ckpt 里都是 enabled=false；lerobot main 的实现在 enabled=false 时"
            "`return transition`（恒等），见 tmp/a2_lerobot_main_ref/relative_action_processor.py "
            "blob sha 3405402904cf15ca18227b3a3fe006d7936f9d53 的 :154 与 :213。"
            "⇒ 过滤后的管线与原管线**数据流等价**。"),
        "root_cause": (
            "ckpt 的 README 要求 lerobot git main；lerobot 0.4.4 的 processor registry 没有这两步。"
            "0.4.4 是 D 指定的冻结版本（与已验收的 lerobot_act/lerobot_eval 一致），"
            "升级 lerobot = 断点变更，须 D 登记 + 重过 B2 的闸 ⇒ 本轮**不升级**，用本兼容目录，并报 D 裁定。"),
    }
    out_json = dst.parent / f"compat_dir_report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (dst.parent / "compat_dir_diffs.patch").write_text(
        "".join(f"### {k}\n{v}\n" for k, v in diffs.items()))
    print(json.dumps({"dropped": dropped, "kept_n": len(kept), "linked_n": len(linked),
                      "compat_dir": str(dst), "report": str(out_json)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
