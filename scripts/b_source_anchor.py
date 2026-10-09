#!/usr/bin/env python3
"""B 线：跨文件引用的**内容锚**工具（D→B 执行单 §5 / 裁定 27「文本锚点易失效」）。

为什么要这个：B 的脚本里有一批指向 A/C 源文件的**行号锚**（`train_act_lift.py:44` 这种）。
行号锚在别人改文件时静默失效，而且失效方向是**变成假证据**：引用还在、指向的代码已经不是那行了。
本仓已吃过两次：
  · 裁定 27.4：A 的 G2 因行号锚失效被判**假红**；
  · 0929：A 主动报出 B 的 4 处锚点移位（`docs/a_handoff_to_b_anchor_shift_20260929.md`），
    其中 `b_eval_act_lift_v1.py` 引的 `:44` 在 A 动手**之前**就已失效（HEAD 里那行本来在 `:36`）。

修法（D §5 要求）：把行号锚换成**内容锚** —— 记住被引代码的**规范化文本**，
需要行号时现场搜索并回显命中行号。规范化 = 去掉全部空白，所以对缩进/换行/空格风格不敏感，
只对**代码本身变了**敏感（那正是我们想知道的）。

约定：
  · `expect=None`  ⇒ 至少命中 1 处即 ok；
  · `expect=N`     ⇒ 必须恰好命中 N 处（0 也合法，用来断言「某段代码已被删掉」）；
  · 命中数不符 / 文件缺失 ⇒ **响亮地失败**，不静默降级成「锚点还在」。
    （同 `b_selfcheck_t17_mutation.py` 的 ANCHOR-MISS 口径。）

只读，不写任何文件。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """内容锚的规范化：去掉全部空白字符。

    去空白而不是折叠空白，因为本仓的源码风格里 `std = x.std(0) + 1e-6`（注释里的写法）
    与 `std=x.std(0)+1e-6`（实际代码，分号连写）必须能对上。
    """
    return _WS.sub("", text)


def find_lines(target, snippet, root=ROOT, expect=None) -> dict:
    """在 `target`（相对仓库根的路径）里按内容锚 `snippet` 搜索，回显命中行号。

    返回 dict：
      rel_path / snippet / snippet_normalized / n_hits / lines / status / expect / detail
    status ∈ {"ok", "not_found", "count_mismatch", "missing_file"}
    """
    rel = str(target)
    p = Path(target) if Path(target).is_absolute() else Path(root) / target
    want = normalize(snippet)
    out = {"rel_path": rel, "snippet": snippet, "snippet_normalized": want,
           "expect": expect, "n_hits": 0, "lines": [], "status": "ok", "detail": ""}
    if not p.exists():
        out["status"] = "missing_file"
        out["detail"] = "目标文件不存在：%s" % p
        return out
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = [i + 1 for i, ln in enumerate(lines) if want and want in normalize(ln)]
    out["n_hits"] = len(hits)
    out["lines"] = hits
    out["hit_texts"] = [lines[i - 1].strip()[:160] for i in hits]
    if not hits:
        # expect==0 时「一处都没命中」正是期望（断言某段代码已删除）
        out["status"] = "ok" if expect == 0 else "not_found"
        out["detail"] = ("规范化文本一处未命中（期望 0 处 ⇒ 这段代码确实已不在）"
                         if expect == 0 else
                         "内容锚未命中：被引代码已被改写或删除 ⇒ 引用它的结论必须重验")
    elif expect is not None and len(hits) != expect:
        out["status"] = "count_mismatch"
        out["detail"] = "命中 %d 处，期望 %d 处（多命中=锚不够独特，少命中=被引代码已变）" % (len(hits), expect)
    return out


def render(res: dict) -> str:
    """把 find_lines 的结果渲染成人类可读的锚点串（含命中行号）。"""
    if res["status"] == "missing_file":
        return "%s:?（内容锚 `%s` —— 目标文件缺失）" % (res["rel_path"], res["snippet"])
    if not res["lines"]:
        return "%s:无命中（内容锚 `%s`）" % (res["rel_path"], res["snippet"])
    loc = ",".join(str(x) for x in res["lines"])
    return "%s:%s（内容锚 `%s`）" % (res["rel_path"], loc, res["snippet"])


def owner_carries(owner, must_contain=(), must_not_contain=(), root=ROOT) -> dict:
    """断言**引用方**文件里确实带着内容锚、且不再带旧的行号锚。

    这条是防「锚点修完又被回退」的牙：只查引用方自己的文本，不查目标文件。
    must_not_contain 用来断言旧行号锚已清除（冻结文件除外，那种情况反过来放进 must_contain）。
    """
    p = Path(owner) if Path(owner).is_absolute() else Path(root) / owner
    res = {"owner": str(owner), "status": "ok", "missing": [], "still_present": [], "detail": ""}
    if not p.exists():
        res["status"] = "missing_file"
        res["detail"] = "引用方文件不存在：%s" % p
        return res
    text = p.read_text(encoding="utf-8", errors="replace")
    ntext = normalize(text)
    res["missing"] = [s for s in must_contain if normalize(s) not in ntext]
    res["still_present"] = [s for s in must_not_contain if normalize(s) in ntext]
    if res["missing"] or res["still_present"]:
        res["status"] = "anchor_regressed"
        res["detail"] = ("缺内容锚 %s；旧锚未清除 %s"
                         % (res["missing"] or "无", res["still_present"] or "无"))
    return res
