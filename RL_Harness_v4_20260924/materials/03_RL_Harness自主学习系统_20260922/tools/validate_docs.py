"""Validate the document delivery only; this does not test any robotics software."""
from pathlib import Path
from collections import defaultdict
from urllib.parse import unquote
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT.parent
REQUIRED = [
    "README.md", "01_RL_Harness真机自主学习技术方案.md",
    "02_接口契约与开发验收.md", "03_调研覆盖与选型证据.md",
    "04_审查与修订记录.md", "06_异步动作时间轴与学习目标.md",
    "07_共享策略与异步RL联合选型证据.md", "08_三轮连续审查与修订记录.md",
    "09_RPent与Harness联合选型.md",
]
LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^\n)]+)\)")

def source_documents():
    return sorted([p for p in ROOT.glob("*.md") if p.name != "05_来源索引.md"]
                  + list((ROOT / "research").glob("*.md")))

errors = []
urls = defaultdict(set)
for path in source_documents():
    content = path.read_text(encoding="utf-8-sig")
    for match in LINK.finditer(content):
        target = match.group(1).strip().strip("<>")
        if target.startswith(("https://", "http://")):
            urls[target].add(path.relative_to(ROOT).as_posix())

lines = ["# 本轮原始来源索引", "", "由文档引用生成；历史研究日期为 2026-09-22，本次修订核验截至 2026-09-23。",
         "来源出现不代表全篇或全仓审计，具体核验范围见调研证据及专项报告。", "",
         f"收录 {len(urls)} 个去重后的引用 URL；固定版本、不同版本及页内锚点保留。", ""]
for i, (url, docs) in enumerate(sorted(urls.items()), 1):
    refs = "、".join(f"[{Path(p).name}]({p})" for p in sorted(docs))
    lines.extend([f"{i}. [原始来源]({url}) — {refs}", ""])
(ROOT / "05_来源索引.md").write_text("\n".join(lines), encoding="utf-8")

for name in REQUIRED:
    if not (ROOT / name).is_file():
        errors.append({"missing_required": name})

documents = source_documents() + [ROOT / "05_来源索引.md"]
entrypoints = [SESSION / "README.md"] + [
    SESSION / "02_自主RL调研_20260922" / n for n in
    ["README.md", "01_调研报告与选型建议.md", "09_参考动作约束改进与VLA替代基线.md",
     "12_低成功率策略的RL再评估与自主练习路线.md"]
]
local_count = 0
manifest = []
for path in documents + entrypoints:
    raw = path.read_bytes()
    content = raw.decode("utf-8-sig")
    if "\ufffd" in content:
        errors.append({"replacement_character": str(path.relative_to(SESSION))})
    if len(re.findall(r"^\s*```", content, flags=re.M)) % 2:
        errors.append({"unbalanced_code_fence": str(path.relative_to(SESSION))})
    for match in LINK.finditer(content):
        target = match.group(1).strip().strip("<>")
        if target.startswith(("https://", "http://", "#", "mailto:", "app:")):
            continue
        # Ordinary file targets in this delivery do not include quoted titles.
        target = unquote(target.split("#", 1)[0])
        if not target:
            continue
        local_count += 1
        resolved = (path.parent / target).resolve()
        # The check result is written at the end of this run.
        generated_result = ROOT / "evidence" / "文档检查结果.json"
        if not resolved.exists() and resolved != generated_result:
            errors.append({"broken_link": str(path.relative_to(SESSION)), "target": target})
    manifest.append({"path": path.relative_to(SESSION).as_posix(), "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest()})

result = {
    "date": "2026-09-23", "scope": "document integrity only; no algorithm or robot tests",
    "new_delivery_markdown_files": len(documents), "entrypoints_checked": len(entrypoints),
    "local_links_checked": local_count, "source_urls": len(urls),
    "errors": errors, "files": manifest,
}
(ROOT / "evidence").mkdir(exist_ok=True)
(ROOT / "evidence" / "文档检查结果.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "files"}, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
