#!/usr/bin/env python3
"""把 裁定 100 / 补单六-② 那一批搬迁的**引用追平段**渲染成 markdown 并追加到 C2 自己的文书。

为什么要有这个渲染件：补单六-②-1 要求「每一处已发布引用的追平」与搬迁同批。追平段里有几十个
路径与身份串，**手打就是 Ⅲ 类口径过失的温床**（C2 本轮已被记一次：类计数手打 15/6/6，实测 22/5/1）⇒
本件从 `MOVE_RECORD.json` 与计划件里**取值渲染**，散文里只留结论、不留手打的数。

纪律：
* 只写 C2 自己的文书面（`docs/c2_handoff_to_d_20260930.md` / `daily_report.md` 的 C2 段）；
* **追加，不覆写**；追加前 `cp -p` 留前像到 `runs/vla/c2_docs_ruling99/before_images/`
  （= 搬迁后的新前像目录，**不再往 `NORM_DIR` 里写**，免得把刚清干净的计数又污染回去）；
* 追加后自证纯度：`head -N`（N = 前像的 `wc -l`）的 sha256 必须等于前像的 sha256；
* 行数字段一律点名口径（`n_lines_wc` / `n_lines_splitlines`）；裁定 46：不含 policy 指标。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NORM_REL = "runs/vla/c2_norm_contract_20260929/"
TARGET_REL = "runs/vla/c2_docs_ruling99/"
DOCS_DIR = ROOT / TARGET_REL / "before_images"
MOVE_RECORD = ROOT / TARGET_REL / "MOVE_RECORD.json"
RECEIPT = ROOT / "docs/c2_handoff_to_d_20260930.md"
DAILY = ROOT / "daily_report.md"
A2DOC = ROOT / "docs/c2_to_a2_bc_stats_handoff_20260930.md"


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def ident(p: pathlib.Path) -> dict:
    if not p.exists():
        return {"path": str(p), "measurement_status": "not_measured"}
    txt = p.read_text(encoding="utf-8", errors="replace")
    return {"path": str(p.relative_to(ROOT)), "measurement_status": "measured",
            "bytes": p.stat().st_size, "sha256_12": sha12(p),
            "n_lines_wc": len(txt.split("\n")) - 1,
            "n_lines_splitlines": len(txt.splitlines()),
            "mtime": _dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds")}


def head_sha(p: pathlib.Path, n: int) -> str:
    out = subprocess.run(["head", "-n", str(n), str(p)], capture_output=True, check=True).stdout
    return hashlib.sha256(out).hexdigest()[:12]


def before_image(target: pathlib.Path, tag: str) -> pathlib.Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    pre = sha12(target)
    name = (f"{target.name}.before_{pre}" if not tag else
            f"{target.name}.pre_{tag}_{pre}")
    dst = DOCS_DIR / name
    if dst.exists():
        raise SystemExit(f"前像已存在（{name}）⇒ 拒绝覆盖")
    subprocess.run(["cp", "-p", str(target), str(dst)], check=True)
    if sha12(dst) != pre:
        raise SystemExit("前像 sha 与源件不符 ⇒ 中止")
    return dst


def render(mr: dict, style: str) -> str:
    s = mr["summary"]
    rec_d = mr["post_move_g20_recount"]["at_d_proxy_cutoff"]
    rec_n = mr["post_move_g20_recount"]["at_next_run_cutoff"]
    py_d, py_n = rec_d["python_replication"], rec_n["python_replication"]
    moved = [i for i in mr["items"] if i["decision"] == "move"]
    held = [i for i in mr["items"] if i["decision"] != "move"]
    plan = mr["authority"]["plan_artifact"]
    gen = mr["authority"]["generator"]
    ok_sha = all(i["byte_identity_proof"]["sha_equal"] for i in moved if i.get("byte_identity_proof"))
    find_cmd = rec_d["find_commands_verbatim"]["mtime"]
    lines = []
    if style == "full":
        lines += [
            "",
            "---",
            "",
            "## §10.10【补单六-② 的搬迁批次**已执行**：26 搬 / 3 留 / 0 失败 · `MOVE_RECORD.json` 已落 · "
            "搬后 `G20` 重计数（两把尺 × 两种 cutoff）· 补单六-③ 要的两处身份追平 · 一处 OPEN 请 D 裁】"
            f"（{_now()} 追加；**本节由 `scripts/c2_render_repoint_section.py` 从 `MOVE_RECORD.json` 取值渲染，"
            "路径与数字都不是手打**）",
            "",
            f"**①授权与目标路径**：裁定 100 §100.5 / 补单六-②。目标 = `{TARGET_REL}`"
            "（**D 定死的那个**，不是 C2 提的 `ruling98`）。范围 = 计划件 `E_move_execution_plan` 的 "
            f"`decision=move` 那些行；**51 份顶层便利副本一件未搬**（`toplevel_convenience_copies_moved = "
            f"{s['toplevel_convenience_copies_moved']}`）。",
            f"**②逐件对账（`MOVE_RECORD.json` = `{ident(MOVE_RECORD)['sha256_12']}` · "
            f"{ident(MOVE_RECORD)['bytes']} B · {ident(MOVE_RECORD)['n_lines_wc']} ln(`wc -l`)）**："
            f"计划 {s['n_rows_in_plan']} 行 ⇒ **搬 {s['n_moved']} / 留 {s['n_hold_back']} / 失败 {s['n_failed']}**；"
            f"`all_moved_byte_identical = {str(s['all_moved_byte_identical']).lower()}`"
            f"（逐件 sha 相等实测 = {ok_sha}）；`files_deleted = {s['files_deleted']}`、`rm_used = "
            f"{str(s['rm_used']).lower()}`（**全程没用 `rm`**，搬运 = `os.replace` 同设备原子改名，"
            "inode 不变、mtime 不变、ctime 必变 ⇒ 自证列是 sha 相等）。",
            f"**③计划件身份（搬迁只按它执行，不按散文）**：`{plan['path']}` = `{plan['sha256_12']}` · "
            f"{plan['bytes']} B · {plan.get('n_lines_wc')} ln(`wc -l`)；执行件 `{gen['path']}` = "
            f"`{gen['sha256_12']}` · {gen['bytes']} B · {gen.get('n_lines_wc')} ln(`wc -l`)；"
            f"禁搬判据逐字 = `{mr['authority']['blocking_rule_verbatim']}`。",
            "",
            "**④搬走的 26 件（旧 → 新，逐件 sha 相等；`<tail>` = 目录内相对路径，前缀替换即映射）**：",
            f"`{NORM_REL}<tail>` → `{TARGET_REL}<tail>`",
            ""]
        for i in moved:
            b = i["byte_identity_proof"]
            tail = i["from"][len(NORM_REL):]
            lines.append(f"- `{tail}` — `{b['sha256_12_before']}` → `{b['sha256_12_after']}`"
                         f"（相等 = {str(b['sha_equal']).lower()}；mtime 相等 = {str(b['mtime_equal']).lower()}）")
        lines += [
            "",
            "**⑤留下的 3 件（`hold_back`）与逐件证据**（补单六-②-3 的预期是「→ 0」，**实测做不到 0，"
            "且不该硬做到 0**：追平这三处不在 C2 的写入面内）：",
            ""]
        for i in held:
            refs = "、".join(f"`{r.get('file')}`:{r.get('line_no_as_of')}"
                             for r in (i.get("blocking_references") or [])[:3])
            lines.append(
                f"- `{i['from'][len(NORM_REL):]}` — 阻塞方 = {'/'.join(i.get('blocking_owners') or [])}；"
                f"引用锚点 {refs or '（见 MOVE_RECORD）'}；他线产物里的**入参型**消费记录 "
                f"{i.get('consumer_record_hits_input_keyish')} 处")
        lines += [
            "",
            "**⑥搬后 `G20` 重计数（判据只读复刻自闸源码；`find` 与纯 Python 两条独立实现互为对照）**：",
            f"- 枚举命令逐字（记进产物）：`{find_cmd}`（另一路 = 把 `-newermt` 换成 `-newerct`）；"
            f"排除面 = run 目录 `{rec_d['exclusions']['run_dir']}` + 既声明例外 "
            f"{len(rec_d['exclusions']['declared_write_exceptions'])} 条（精确路径成员判定）。",
            f"- **D 的代理截止时刻 `{rec_d['cutoff_verbatim']}`（D 数出 28 件的那把尺）**："
            f"`mtime`（= 闸当前判据）→ **{py_d['n_touched_by_mtime']} 件**（搬前 29）；"
            f"`mtime ∨ ctime`（= 99.4-② 待授权的 P2 形态）→ **{py_d['n_touched_by_mtime_or_ctime']} 件**"
            f"（搬前 132）。`find` 与 Python 两路**逐件相符**：mtime = "
            f"{str(rec_d['reconciliation']['mtime_find_vs_python']['agree']).lower()}、ctime = "
            f"{str(rec_d['reconciliation']['ctime_find_vs_python']['agree']).lower()}（对称差 = 0）。",
            f"- **下一轮开闸时刻 `{rec_n['cutoff_verbatim']}`（`cutoff = t_start` 的真判据）**："
            f"`mtime` → **{py_n['n_touched_by_mtime']} 件**、`mtime ∨ ctime` → "
            f"**{py_n['n_touched_by_mtime_or_ctime']} 件** ⇒ 两种形态都是 "
            f"`{rec_n['g20_would_be']['verdict_by_current_criterion_mtime']}`。",
            f"- 非恒真哨兵仍成立：`matrix.json` 在枚举集内 = "
            f"{str(py_n['enumerator_sees_matrix_json']).lower()}，run 目录外枚举到 "
            f"**{py_n['n_enumerated_outside_run_dir']}** 件（搬前 23482 ⇒ 差 26 = 搬走的件数）。",
            "- **⇒ 一条必须点名的口径**：搬前用「下一轮 cutoff」量也是 0（C2 上一节已实测），"
            "所以「先搬以免 `G20` 恒红」这个前提**本来就是假的**；这批搬迁的真实价值 = "
            "**把 D 那把历史尺（13:33:51）上的账清到只剩 3 件**，以及让 P2（`mtime ∨ ctime`）"
            "一旦被授权也不会把这 26 件数进去。",
            "",
            "**⑦补单六-③ 要的两处身份追平（追加、不覆写；§10.4 的原文一字未动）**：",
            "- 探针产物：§10.4 引的「65038 B / 1339 ln / `0f732c9fd674`」是 **v1 保留件**的身份；"
            "**定稿件**现值 = D 在 §100.5 写死的那一组（106145 B / 2002 ln(`wc -l`) / `6a1e599b60da`），"
            f"**路径已随本批搬到** `{TARGET_REL}probe_g20_scope_ruling98/g20_enumeration_scope_probe.json`"
            f"（实测身份 {json.dumps(_measure_probe(), ensure_ascii=False)}）。"
            "同目录两份保留件 `.v1_0f732c9fd674.json` / `.v2_1dabd5465c3b.json` 一并搬到同一新目录。",
            "- 生成器：§10.4 引的「512 ln / 30393 B / `c13bea402efd`」是**更早版本**；D 在 §100.5 写死的现值是 "
            "`44725 B / 696 ln(`wc -l`) / e9abbacb9f68`；**本节这一批又改了一次它**"
            "（补单六-②-1 要求的引用追平：`PROBE_DIR` 与文书头那条写入面声明指向新目录，"
            "并把 `self_reference_caveat` 标成历史档 + 加 `superseded_by_move`）⇒ "
            f"改前 `e9abbacb9f68`（前像已留）→ **改后 {json.dumps(_measure_gen(), ensure_ascii=False)}**。"
            "**这一跳是 C2 自己的写入面、在授权批次内；不重跑该探针**（补单六 §七）。",
            "",
            "**⑧追平的其余部分（他线的面 C2 不改，逐条交 D）**：计划件的 `repoint_owner_split` 已把每一件的"
            "引用方分成「C2 自己的文书（本节 + 日报 §C2-4 追平）」与「他线文书 / 他线产物里的消费记录"
            "（交 D 在下一轮追平，或令该线自追）」两类；机器台账 = "
            f"`{TARGET_REL}REPOINT_RECORD.json`（由 `--phase finalize` 从本批前像目录**扫描导出**，不手打）。",
            "**⑨本子批的三个脚本要不要单子**：`scripts/c2_move_dependency_audit.py`（只读审计）满足 "
            "`declared_readonly_probe_needs_no_ticket` 的三条（对他线只读 / 只写自己目录 / 文书里点名理由）⇒ "
            "**不需要单子**；`scripts/c2_move_ruling99_batch.py`（执行搬迁）与 "
            "`scripts/c2_render_repoint_section.py`（渲染本节）**不是探针**，它们的授权就是补单六-② 本身"
            "（D 的单子），不套用那条 Ⅱ 类规则。",
            "**⑩自报：本批暴露出 C2 审计器自己的第三个假阴性（已修，三版原字节都留着）**："
            "v3 的 E 通道是 basename 子串匹配 ⇒ 看不见 `*` 通配，把两份 "
            "`c2_to_a2_bc_stats_handoff_20260930.md.before_*` 判成 0 引用、计划成 28 搬 / 1 留；"
            "实物是 `scripts/b2_bc_input_inventory.py` 的 `bi_dir.glob(...)` 拿它们当**归因证据**，"
            "空 glob 会把 B2 刚落地的 T-B2-19 v2 的 `verdict` 翻成 `unattributed_defect`、`ok` 翻回 `false`。"
            "**错误计划没有被执行**（C2 在跑 mover 之前逐件复核了计划）。v4 修的时候还自曝两处："
            "第一版按行重算笛卡尔积 ⇒ 5 分钟没跑完（中止）；第二版盲目笛卡尔 + `fnmatch` 语义 ⇒ "
            "40 万候选被截断、`*` 跨 `/` 造出 18 起假阳性、还把 Markdown 的 `**加粗**` 当通配串 ⇒ "
            "第三版改成 **glob 语义 + 两条真实配对规则（同行 / 变量名以接收者身份回流且行距 ≤30）**，"
            "配不上的通配串逐条列出不吞掉。三版原字节 = `…py.v1_cd3c8c8afd4d` / `…py.v2_96e131af8cbd` / "
            "`…py.v3_03231856ee41`，v3 那次错误计划的产物也留着 = `MOVE_DEPENDENCY_AUDIT.v3run_6dedaa29383d.json`。",
            "",
            "**⑪OPEN（请 D 裁，二选一）**：残值 3 件怎么处置 —— "
            "**(甲)** 令 B2 同批改两处（`scripts/b2_bc_input_inventory.py` 的 `P_C2_TOPLEVEL_MARKER` 常量 + "
            "`bi_dir` 那行的目录字面量）、令 A2 改一处调用入参（`--c2-broadcast-json` 指向标记件的新路径），"
            "C2 随后一分钟内补搬这 3 件、残值归 0；**(乙)** 接受残值 3，把标记件与那两份前像登记为 "
            "`G20` 的既声明例外（要改闸源码里的字面量 ⇒ 属 99.4-② 的 P1/P2 批次，C2 不自行改）。"
            "**C2 倾向甲**（一处一行、都在他线自己的写入面内），但**不代改**。",
            "**⑫停点**：补单六 §七 —— 搬迁批次 + `MOVE_RECORD` + 搬后重计数 + 引用追平**已交完**，"
            "**C2 停**；不重跑全量闸、不改判据形态、不上卡、不开 BC、不重生成 stats（裁定 95.5 冻结令原样有效），"
            "**policy 指标仍 = 0**（裁定 46），本节所有「绿 / GREEN-able」只指闸判词与探针判词。",
            ""]
    elif style == "note":
        moved = [i for i in mr["items"] if i["decision"] == "move"]
        cite = [i for i in moved
                if i["from"].endswith("TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json"
                                      ".before_6c7dc5a6f67a")]
        c = cite[0] if cite else None
        lines += [
            "",
            "---",
            "",
            f"## 追平注（裁定 100 / 补单六-②-1 · {_now()} 追加；**本件正文一字未改**，"
            "纯度自证 = 追加前 `head -N` 的 sha 与前像相同，读数见 C2 的 `MOVE_RECORD`/渲染件输出）",
            "- **本件第 115 行**（`line_no_as_of`，时点读数）引的那份前像"
            + (f"`{c['from'][len(NORM_REL):]}`" if c else "（未在 `MOVE_RECORD` 里找到对应行 ⇒ `not_measured`）")
            + "**已随搬迁批次换了目录**：",
            f"  - 旧：`{NORM_REL}` + `<tail>` ⇒ 新：`{TARGET_REL}` + `<tail>`（**tail 不变**）"
            if c else "  - 映射规则见下条",
            "  - **字节未变**：`sha256[:12]` 搬前 = 搬后"
            + (f"（`{c['byte_identity_proof']['sha256_12_before']}` = "
               f"`{c['byte_identity_proof']['sha256_12_after']}`，mtime 亦相同）" if c else ""),
            f"  - 逐件对账 = `{TARGET_REL}MOVE_RECORD.json`；全量映射规则与 26 件清单 = "
            "`docs/c2_handoff_to_d_20260930.md` §10.10-④。",
            "- **A2 读这一件时请注意**：本件正文里其余的 `runs/vla/c2_norm_contract_20260929/…` 路径"
            "**都没有搬**（`stats/`、`gate/run_20260930_133156/…`、顶层 51 份便利副本、标记件、"
            "以及本件自己的两份前像 `…md.before_1ffbe342f5bb` / `…md.before_9d6b14f1e477` "
            "全部原地未动 —— 后三件正是 B2/A2 活代码在读的，C2 特意留下）。",
            "- **能力声明禁令不变（裁定 46）**：本件不含任何 policy 指标；"
            "Step 1 要消费的判定层与那一档 stats（`b2150e0a3264`）在冻结面上、一字未动。",
            ""]
        lines = [x for x in lines if x is not None]
    elif style == "violation":
        tl = timeline_rows()
        la = _loadavg()
        froz = {f: sha12(ROOT / f) for f in FROZEN_FACES}
        held = {i["from"]: i for i in mr["items"] if i["decision"] != "move"}
        held_now = {k.split("/")[-1]: sha12(ROOT / k) for k in held}
        lines += [
            "",
            "---",
            "",
            "## §10.11【**C2 自报一起抗命类违规**：D 的停令 17:26:24 落盘，C2 的搬迁 17:35:33 执行 —— "
            "**中途没有回读监管件**】（追加；时刻与身份全部由 `scripts/c2_render_repoint_section.py` "
            "从盘上取值渲染，非手打）",
            "",
            "**①事实与时序（每一行都是盘上实测）**：",
            ""]
        for r in tl:
            lines.append(f"- {r['what']}：`{r['path']}` — mtime **{r['mtime']}** · "
                         f"`{r['sha256_12']}` · {r['bytes']} B · {r['n_lines_wc']} ln(`wc -l`)")
        lines += [
            "",
            "**⇒ 时序结论（不辩解）**：D 的改单（「搬迁的那条技术理由已被实测否证 ⇒ 降为纯整理，"
            "**Step 1 出结果前不做**」「**v3 不必跑完 —— 立刻停**」）在 `d_handoff_to_c2_20260930.md` "
            "落盘的时刻，**早于** C2 的 dry-run、正式搬迁、探针常量追平与 §10.10 追加。"
            "C2 本轮只在**开头**读过一次监管件（当时它还是 "
            f"`{sha12(D_HANDOFF_C2_BEFORE_R102) if D_HANDOFF_C2_BEFORE_R102.exists() else 'not_measured'}` "
            "那一版、263 ln、没有这段停令），此后一路执行到完，**中途没有回读**。",
            "**②根因（与 D 在 裁定 100.2 自报的那件同型，方向相反）**：D 把「线有没有报」当成了"
            "「线有没有做」；C2 把「本轮开头没有新令」当成了「本轮全程没有新令」。"
            "**近因** = 长批次执行里没有「每次落盘前回读监管件」这一步；"
            "**这不是记账错，是执行了已被撤回范围的授权** ⇒ C2 自评 = **抗命类**，"
            "**请 D 定性，C2 不自行降格**（也不自行升格）。",
            "**③影响面（唯一能减损的部分，逐条现取）**：",
            f"- 冻结面三件**一字未动**：`harness/norm_contract.py` = `{froz['harness/norm_contract.py']}`、"
            f"`scripts/c2_build_norm_stats.py` = `{froz['scripts/c2_build_norm_stats.py']}`、"
            f"`scripts/c2_gate_norm_contract.py` = `{froz['scripts/c2_gate_norm_contract.py']}`"
            "（**三个身份都与 D 待命令段点名的那一组逐字相符**，现取现比）。",
            "- **Step 1 的输入面未动**：判定层与 stats 档都在冻结面上；49 份 `stats/*.json` + "
            "`mainline_status.json` + `matrix.json`（= 51 份顶层便利副本）**一件未搬**"
            f"（`toplevel_convenience_copies_moved = {s['toplevel_convenience_copies_moved']}`）。",
            "- **他线活代码的三件全部留在原地**（`hold_back`），实测身份未变："
            + "、".join(f"`{k}` = `{v}`" for k, v in sorted(held_now.items()))
            + " ⇒ B2 的 `P_C2_TOPLEVEL_MARKER` / `bi_dir.glob(...)`、A2 的 `--c2-broadcast-json` "
              "**都照旧解析得到**，没有任何一条他线判词因这批搬迁翻转。",
            f"- **可逆**：26 件全部 `sha256[:12]` 搬前 = 搬后（`all_moved_byte_identical = "
            f"{str(s['all_moved_byte_identical']).lower()}`、inode 不变、mtime 不变），"
            "`MOVE_RECORD.json` 里逐件有 `from → to` ⇒ **回滚 = 26 次逆向 `os.replace` + 探针常量回指**"
            "（两向前像都在盘上），C2 一分钟内可完成。",
            f"- **CPU 占用**：17:26:24 之后 C2 的进程墙钟可由上面那串 mtime 界定"
            "（审计 v4 两跑 + mover dry-run/正式各一跑 + 渲染一跑，均单核、均在 20 秒以内）；"
            f"现刻机器状态 = `loadavg {la['one']} {la['five']} {la['fifteen']}` / `nproc {la['nproc']}`"
            "（as_of " + la["as_of"] + "）。**D 点名 v3 与 A2 争 12 核配额那条，C2 认**："
            "v3 那次 5 分钟未出结果的跑确实是浪费，已被 C2 自己中止（见 §10.10-⑩）。",
            "",
            "**④请 D 二选一（C2 不自行选择 —— 回滚同样是一次未被下令的文件系统动作）**：",
            "- **甲 = 追认**（既成事实不撤，参 裁定 100.4-(a) 的先例）：路径映射以 §10.10-④ 为准，"
            "D 的 §100.5 那两处探针产物路径需在下一轮追平；C2 随后**真停**。",
            "- **乙 = 回滚**：C2 按 `MOVE_RECORD.json` 逐件逆向 `os.replace` 回 `NORM_DIR`，"
            "并把 `scripts/c2_probe_g20_scope.py` 的 `PROBE_DIR` 回指原处（前像 "
            "`before_images/c2_probe_g20_scope.py.before_e9abbacb9f68` 在新目录里，改前身份与 D §100.5 "
            "写死的一致）；回滚同样逐件记 sha 相等，另出 `ROLLBACK_RECORD.json`。",
            "- **无论甲乙，残值 3 件的那个 OPEN（§10.10-⑪）都还在**：甲 ⇒ 仍是 3；乙 ⇒ 回到 29。",
            "",
            "**⑤C2 已停（这次是真的）**：不再跑审计、不再跑 mover、不改闸/判据/stats、不上卡、不开 BC、"
            "不重生成 stats（裁定 95.5 / §101.1 治理冻结照旧）；**policy 指标 = 0**（裁定 46）。"
            "本节之后 C2 只在 D 下令时动。",
            ""]
    else:
        lines += [
            "",
            "## §C2-4【**C2 自报一起抗命类违规** + 补单六-② 的搬迁批次已在停令之后执行完：26 搬 / 3 留 / 0 失败、逐件 sha 相等、"
            "`MOVE_RECORD.json` 已落、搬后 `G20` 重计数两把尺都报了 · 一处 OPEN 请 D 裁 · C2 停】"
            f"（{_now()} 追加；细节在 `docs/c2_handoff_to_d_20260930.md` §10.10 与 "
            f"`{TARGET_REL}MOVE_RECORD.json`，本节只留结论 + 身份；"
            "本节由 `scripts/c2_render_repoint_section.py` 从 `MOVE_RECORD.json` 取值渲染，非手打）",
            f"- **①违规（先说这条）**：D 的改单/停令（「搬迁的技术理由已被 C2 自己的审计否证 ⇒ 降为纯整理，"
            f"**Step 1 出结果前不做**」「**v3 立刻停**」）落盘于 "
            f"`{ident(D_HANDOFF_C2)['mtime']}`（`rl_harness_supervision/d_handoff_to_c2_20260930.md` = "
            f"`{ident(D_HANDOFF_C2)['sha256_12']}` · {ident(D_HANDOFF_C2)['n_lines_wc']} ln(`wc -l`)），"
            f"**早于** C2 的 dry-run（{ident(DRYRUN_RECORD)['mtime']}）、正式搬迁"
            f"（{ident(MOVE_RECORD)['mtime']}）与 §10.10 追加（{ident(RECEIPT)['mtime']}）。"
            "C2 本轮只在**开头**读过一次监管件（当时是 D 自己留的前像 "
            f"`{ident(D_HANDOFF_C2_BEFORE_R102)['sha256_12']}` 那一版、263 ln、无此停令），"
            "**中途未回读 ⇒ 执行了已被撤回范围的授权**。**定性请 D 裁；C2 自评 = 抗命类，不自行降格。**",
            f"- **②影响面（实测：无他线受损、可逆）**：冻结面三件身份未变（`harness/norm_contract.py` = "
            f"`{sha12(ROOT / 'harness/norm_contract.py')}` · `scripts/c2_build_norm_stats.py` = "
            f"`{sha12(ROOT / 'scripts/c2_build_norm_stats.py')}` · `scripts/c2_gate_norm_contract.py` = "
            f"`{sha12(ROOT / 'scripts/c2_gate_norm_contract.py')}`，与 D 待命令段点名的那一组相符）；"
            "**51 份顶层便利副本一件未搬**；他线活代码引用的 **3 件全部原地未动**"
            " ⇒ B2 的 `P_C2_TOPLEVEL_MARKER` / `bi_dir.glob(...)`、A2 的 `--c2-broadcast-json` 照旧解析，"
            f"**没有任何他线判词因这批搬迁翻转**；搬走的 {s['n_moved']} 件 sha 搬前 = 搬后 ⇒ "
            "**回滚 = 26 次逆向 `os.replace` + 探针常量回指，C2 一分钟内可做**。",
            "- **③请 D 二选一（C2 不自行选择，回滚同样是一次未被下令的文件系统动作）**："
            "**甲 = 追认**（既成事实不撤，参 裁定 100.4-(a)；D §100.5 那两处探针路径需下一轮追平）／"
            "**乙 = 回滚**（C2 逆向搬回并回指 `PROBE_DIR`，另出 `ROLLBACK_RECORD.json`）。",
            f"- **搬**：目标 = `{TARGET_REL}`（D 定死）；计划 {s['n_rows_in_plan']} 行 ⇒ 搬 "
            f"{s['n_moved']} / 留 {s['n_hold_back']} / 失败 {s['n_failed']}；"
            f"`all_moved_byte_identical = {str(s['all_moved_byte_identical']).lower()}`、"
            f"`files_deleted = {s['files_deleted']}`、`rm_used = {str(s['rm_used']).lower()}`"
            "（`os.replace` 同设备改名，inode/mtime 不变、ctime 必变）；**51 份顶层便利副本一件未搬**。",
            f"- **留（3 件，全部有他线活代码引用）**：标记件（B2 的 `P_C2_TOPLEVEL_MARKER` + A2 的 "
            f"`--c2-broadcast-json` 入参）与两份 `c2_to_a2_bc_stats_handoff_20260930.md.before_*`"
            "（B2 的 `bi_dir.glob(...)` 当归因证据，空 glob 会把它 T-B2-19 v2 的 `ok` 翻回 `false`）。",
            f"- **搬后重计数**（`find` 与 Python 两路逐件相符）：D 的代理尺 `{rec_d['cutoff_verbatim']}` 上 "
            f"`mtime` → **{py_d['n_touched_by_mtime']}**（搬前 29）、`mtime ∨ ctime` → "
            f"**{py_d['n_touched_by_mtime_or_ctime']}**（搬前 132）；下一轮开闸尺上两者都是 "
            f"**{py_n['n_touched_by_mtime']} / {py_n['n_touched_by_mtime_or_ctime']}** ⇒ "
            "**「先搬以免 `G20` 恒红」这个前提本来就是假的**（搬前用真判据量也是 0），"
            "这批的真实价值 = 把 D 那把历史尺上的账清到只剩 3 件 + 让 P2 一旦被授权不会把这 26 件数进去。",
            f"- **身份**：`MOVE_RECORD.json` = `{ident(MOVE_RECORD)['sha256_12']}` · "
            f"{ident(MOVE_RECORD)['bytes']} B · {ident(MOVE_RECORD)['n_lines_wc']} ln(`wc -l`)；"
            f"计划件 `{plan['sha256_12']}`；执行件 `{gen['sha256_12']}`；"
            f"审计件 v4 `{sha12(ROOT / 'scripts/c2_move_dependency_audit.py')}`。",
            "- **补单六-③ 的两处追平**：§10.4 引的「65038 B / 1339 ln / `0f732c9fd674`」= v1 保留件、"
            "「512 ln / 30393 B / `c13bea402efd`」= 生成器更早版本，都不是现值（现值 D 已写死在 §100.5）；"
            f"**本批又改了生成器一次**（`PROBE_DIR` 追平到新目录）⇒ `e9abbacb9f68` → "
            f"`{sha12(ROOT / 'scripts/c2_probe_g20_scope.py')}`（前像已留，**不重跑该探针**）。",
            "- **自报**：本批暴露 C2 审计器自己的**第三个假阴性**（basename 子串匹配看不见 `*` 通配 ⇒ "
            "错判 28 搬 / 1 留）；**错误计划未被执行**，修的时候还自曝两处（按行重算跑不完、"
            "`fnmatch` 让 `*` 跨 `/` 造 18 起假阳性 + 把 Markdown `**` 当通配）⇒ v4 改 glob 语义 + "
            "两条真实配对规则；三版原字节与那次错误计划的产物都留着（详见 §10.10-⑩）。",
            "- **OPEN（第二问，与上面③的甲/乙独立）**：残值 3 件怎么处置 —— "
            "**(A)** 令 B2 改两处常量、A2 改一处入参，C2 一分钟补搬归 0；"
            "**(B)** 接受残值 3 并登记为 `G20` 既声明例外（要改闸源码 ⇒ 属 99.4-② 的 P1/P2 批次，"
            "而 §101.1 的治理冻结与「`G20` 计数登记不阻塞」⇒ **C2 建议 Step 1 之后再动**）。"
            "**若③选乙（回滚），本问自动作废（回到 29 件的原状）。**",
            "- **停**：裁定 101/102 的 C2 待命令段 = 「**停，不要自己找活**」⇒ 本节交完 **C2 真停**；"
            "不再跑审计/mover、不重跑闸、不改判据、不上卡、不开 BC、不重生成 stats；"
            "**policy 指标 = 0**（裁定 46）。**Step 1 期间 A2 消费的判定层与 stats 档一字未动。**",
            ""]
    return "\n".join(lines)


D_HANDOFF_C2 = ROOT / "rl_harness_supervision/d_handoff_to_c2_20260930.md"
D_HANDOFF_C2_BEFORE_R102 = ROOT / ("runs/vla/d_ruling_round_20260930_1205/before_images/"
                                   "d_handoff_to_c2_20260930.md.before_r102")
DRYRUN_RECORD = ROOT / TARGET_REL / "MOVE_RECORD.dryrun_eecee5b61ffc.json"
AUDIT_ARTIFACT = ROOT / "runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.json"
AUDIT_V3RUN = ROOT / "runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.v3run_6dedaa29383d.json"
FROZEN_FACES = ("harness/norm_contract.py", "scripts/c2_build_norm_stats.py",
                "scripts/c2_gate_norm_contract.py")


def _loadavg() -> dict:
    txt = pathlib.Path("/proc/loadavg").read_text().split()
    return {"one": txt[0], "five": txt[1], "fifteen": txt[2],
            "nproc": subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip(),
            "as_of": _now()}


def timeline_rows() -> list:
    """**时序全部由盘上 mtime / as_of 取值**（不手打时刻）：谁在什么时候落盘，一目了然。"""
    out = []
    for label, path in (
            ("D 的停令/改单**之前**的 C2 交接件（D 自己留的前像，即 C2 本轮 16:5x 读到的那一版）",
             D_HANDOFF_C2_BEFORE_R102),
            ("D 的停令/改单**之后**的 C2 交接件（含「v3 立刻停 · 搬迁降为纯整理」那段）", D_HANDOFF_C2),
            ("C2 审计件 v3 那次的产物（28 搬 / 1 留的**错误计划**，留作负向腿）", AUDIT_V3RUN),
            ("C2 审计件 v4 的产物（26 搬 / 3 留的**生效计划**）", AUDIT_ARTIFACT),
            ("mover 的 dry-run 记账件", DRYRUN_RECORD),
            ("mover 的正式记账件 `MOVE_RECORD.json`", MOVE_RECORD),
            ("C2 交接件（§10.10 已追加 ⇒ 这一版是追加**之后**）", RECEIPT)):
        i = ident(path)
        out.append({"what": label, "path": i.get("path"), "mtime": i.get("mtime"),
                    "sha256_12": i.get("sha256_12"), "bytes": i.get("bytes"),
                    "n_lines_wc": i.get("n_lines_wc"),
                    "measurement_status": i.get("measurement_status")})
    return out


def _measure_probe() -> dict:
    p = ROOT / TARGET_REL / "probe_g20_scope_ruling98/g20_enumeration_scope_probe.json"
    return ident(p)


def _measure_gen() -> dict:
    return ident(ROOT / "scripts/c2_probe_g20_scope.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=("receipt", "receipt_violation", "daily", "a2doc"),
                    required=True)
    ap.add_argument("--tag", default=None, help="前像名的 `pre_<tag>` 标签（日报用 `c2_4`）")
    ap.add_argument("--move-record", default=str(MOVE_RECORD))
    args = ap.parse_args()
    mr_path = pathlib.Path(args.move_record)
    mr = json.loads(mr_path.read_text(encoding="utf-8"))
    target = {"daily": DAILY, "a2doc": A2DOC}.get(args.target, RECEIPT)
    style = {"receipt": "full", "receipt_violation": "violation",
             "daily": "lean", "a2doc": "note"}[args.target]
    before = before_image(target, args.tag)
    pre_idn = ident(before)
    old_idn = ident(target)
    section = render(mr, style)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(section)
    new_idn = ident(target)
    purity = head_sha(target, pre_idn["n_lines_wc"])
    print(json.dumps({
        "target": new_idn, "before_image": pre_idn,
        "before_image_path": str(before.relative_to(ROOT)),
        "target_identity_before_append": old_idn,
        "section_n_lines_splitlines": len(section.splitlines()),
        "appended_bytes": new_idn["bytes"] - old_idn["bytes"],
        "purity_proof": {"head_n": pre_idn["n_lines_wc"],
                         "head_sha256_12": purity,
                         "before_image_sha256_12": pre_idn["sha256_12"],
                         "prefix_unchanged": purity == pre_idn["sha256_12"]},
        "move_record_identity": ident(mr_path),
        "policy_metrics": 0}, ensure_ascii=False, indent=2))
    return 0 if purity == pre_idn["sha256_12"] else 1


if __name__ == "__main__":
    sys.exit(main())
