#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-B2-19 · BC 消费侧「输入清单件」生成器（**纯只读**汇总，给 A2 对账用）。

派工来源：`rl_harness_supervision/d_handoff_to_b2_20260930.md` §三（T-B2-19，补单四未撤）。
产物：`runs/vla/b2_bc_input_inventory_20260930/BC_INPUT_INVENTORY.json`
     （`--selftest` 另落 `SELFTEST_three_valued_teeth.json`）。

边界（照执行单原文，不扩张）：
  · **只读汇总**：本脚本对 `runs/` 只写自己的产物目录，对别人的代码/产物一律不写、不改、不重跑。
  · **不改 A2 的训练代码、不代 A2 判 BC 能不能跑**（准入判定归 A2，裁定 93.4）。
  · 本件 `ok=false` **不等于**「BC 被禁」（裁定 96.2 的读法禁令同型）。BC 被禁的判据只有
    `verdict_class1=RED` / `admissible_for_bc=false` / `Tp5` 同源不成立（裁定 97.5）。
  · **不含任何 policy 指标或能力表述**（裁定 46）；所有 PASS/绿只指闸判词。

三值纪律（执行单 §三-5）：取不到 ⇒ `null` + `measurement_status="not_measured"` + **非零退出**，
**禁 `false`/`0` 顶替**。「读不到」与「测到没有」是两件事（红线 `absence_of_measurement_is_not_measurement`）。

行数口径（裁定 98.3-②/98.5-②）：**裸 `n_lines` 不得出现在本件任何位置**。一律
`n_lines_wc`（换行符个数 = `wc -l`）与 `n_lines_splitlines`（`len(read_text().splitlines())`）；
**对账的唯一约束性判据 = `sha256[:12]`**，行数只作旁证且必须带口径名。

口径纪律（裁定 97.7-①）：**不 glob 后挑一份**。凡是「声明路径」的项，路径都来自点名它的
那份文书（D 执行单 / C2 的成对广播件 / `work/project_parameters.json`），本脚本只对那一条路径复算；
同名兄弟件只作**登记**（它们的存在会让 glob 挑错），不作候选。

退出码（**v2，裁定 99.3 之后**；v1 的口径原文逐字保留在 v1 实物 `BC_INPUT_INVENTORY.json`
（`8599c58cbedc`）里，本脚本不改它）：
  `0` = 26 项全 measured 且无 binding 差异；
  `4` = 无 binding 差异、无「本可测而未测」项，但存在 ≥1 项**按构造延期**的 `not_measured`
       （只能在六步序列第 1 步真跑后测）⇒ **当前可测面已判定完结**（裁定 99.3-① 的「S3.5 保持
       `not_measured` 直到第 1 步真跑」）；
  `3` = 存在「本可测而未测」的 `not_measured`（真缺口），**或**改判守卫跳闸（读不到 v1 实物 ⇒
       无法证明本件取代了什么，此时不得报绿）；
  `5` = 存在 binding 差异；`2` = 用法/环境错（含 numpy/pyarrow 缺失）。
  **优先级 5 > 3 > 4 > 0**（binding 压倒一切）。

改判的落地形态（裁定 99.3 / 补单五 ③④：**追加一节，不覆写**）：v1 产物 `8599c58cbedc` 已被 D 的
文书（裁定 99.3-①）引用 ⇒ **原字节留在盘上不动**，改判版另落
`BC_INPUT_INVENTORY_v2_ruling99_3.json`；v1 的 `summary` 与 `differences_register` **从 v1 实物里
读出来**逐字嵌进本件（读不到 ⇒ `null` + `measurement_status="not_measured"` + 守卫跳闸，
**绝不手抄**）。每一项的改判只动 `severity` 与归因，**绝不动 `match` 与 `measured`**
（改判不改实测值 —— 三处 `representation_version` 逐字相同这个命题**仍然实测为 false**）。
"""
from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import pathlib
import re
import sys
from fractions import Fraction

REPO = pathlib.Path(__file__).resolve().parent.parent

ARTIFACT = "b2_bc_input_inventory"
TASK_ID = "T-B2-19"
RUN_DIR_REL = "runs/vla/b2_bc_input_inventory_20260930"
RUN_DIR = REPO / RUN_DIR_REL
# ── v1 = 改判前那一版（`as_of 15:03:33`）。**原字节不动**：裁定 99.3-① 已引用它的身份 ──
V1_INVENTORY_REL = RUN_DIR_REL + "/BC_INPUT_INVENTORY.json"
V1_INVENTORY_SHA256_12 = "8599c58cbedc"
V1_INVENTORY_BEFORE_IMAGE_REL = (RUN_DIR_REL + "/before_images/"
                                 "BC_INPUT_INVENTORY.json.before_ruling99_3_8599c58cbedc")
V1_SELFTEST_REL = RUN_DIR_REL + "/SELFTEST_three_valued_teeth.json"
V1_SELFTEST_SHA256_12 = "177f1e9a4713"          # 盘上实物（`as_of 15:21:07`，2040 B / 76 ln）
V1_SELFTEST_CITED_SHA256_12 = "19ea563b0b2a"    # 文书钉的那一跑（`as_of 15:03:31`）；见自纠件
V1_SELFTEST_RECONSTRUCTED_REL = (RUN_DIR_REL + "/before_images/"
                                 "SELFTEST_three_valued_teeth.json."
                                 "reconstructed_as_of_150331_19ea563b0b2a")
SELF_CORRECTION_REL = RUN_DIR_REL + "/SELFTEST_IDENTITY_SELF_CORRECTION.json"
OUT_DEFAULT = RUN_DIR / "BC_INPUT_INVENTORY_v2_ruling99_3.json"
SELFTEST_DEFAULT = RUN_DIR / "SELFTEST_three_valued_teeth_v2_ruling99_3.json"

N_LINES_CALIBER = ("n_lines_wc = 换行符个数（`wc -l`）；n_lines_splitlines = len(read_text().splitlines())。"
                   "末行无换行符 ⇒ 两口径差 1。对账的唯一约束性判据 = sha256[:12]（裁定 98.3-①④/98.5-②）。")

# ── 被点名的路径（**照抄声明源，不 glob**）─────────────────────────────────────────────
P_LEROBOT_ROOT = "runs/vla/b2_sim_demo_bidir_20260930/formal/pi05_lerobot"
P_LEROBOT_INFO = P_LEROBOT_ROOT + "/meta/info.json"
P_LEROBOT_STATS = P_LEROBOT_ROOT + "/meta/stats.json"
P_LEROBOT_TASKS = P_LEROBOT_ROOT + "/meta/tasks.parquet"
P_LEROBOT_EPISODES = P_LEROBOT_ROOT + "/meta/episodes/chunk-000/file-000.parquet"
P_TEAM_MANIFEST = "runs/vla/b2_sim_demo_bidir_20260930/formal/team_form/data/dataset_manifest.json"
P_DEMO_MANIFEST = "runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json"
P_SIDECAR_DIR = "runs/vla/b2_sim_demo_bidir_20260930/formal/sidecar"
P_TEAM_TRAIN = "runs/vla/b2_sim_demo_bidir_20260930/formal/team_form/data/train"
P_NPZ = "runs/vla/b2_states_14d_20260930/formal40/states_14d.npz"
P_NPZ_MANIFEST = "runs/vla/b2_states_14d_20260930/formal40/manifest.json"
P_NPZ_SIBLING_GLOB_PARENT = "runs/vla/b2_states_14d_20260930"
P_C2_BROADCAST = "docs/c2_to_a2_bc_stats_handoff_20260930.md"
P_C2_TOPLEVEL_MARKER = ("runs/vla/c2_norm_contract_20260929/"
                        "TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json")
P_C2_TOPLEVEL_STATUS = "runs/vla/c2_norm_contract_20260929/mainline_status.json"
P_ARM_STATUS = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/"
                "arm_mainline/mainline_status.json")
P_GATE_VERDICT = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/gate_verdict.json")
P_STATS_BC = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/arm_mainline/stats/"
              "s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05"
              "__mainline_path_check.json")
P_STATS_XCHECK = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/arm_mainline/stats/"
                  "s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05"
                  "__lerobot_crosscheck.json")
P_D_ORDER = "rl_harness_supervision/d_handoff_to_b2_20260930.md"
P_DECISIONS = "work/decisions/decisions_20260929.md"
P_PARAMS = "work/project_parameters.json"
P_A2_RUNTIME = "harness/vla_runtime.py"
P_A2_BC_GATE = "harness/bc_admission_gate.py"
P_C2_CONTRACT = "harness/norm_contract.py"
P_B2_GEN = "scripts/b2_s1_generate_dataset.py"
P_B2_EXPORTER = "scripts/b2_export_states_14d.py"

# ── 冻结串（执行单 §三-3 点名要逐字核对的那一串）──────────────────────────────────────
FROZEN_REP_VERSION = ("b2-s1-sim-bidir-aloha14d-dt0.034-29.4118hz-"
                      "grip14_to_qpos_pair(+v,-v)-team480x640+pi05x224-v1")
PI05_SLOTS_DECLARED = ("pi05_base_0_rgb", "pi05_left_wrist_0_rgb", "pi05_right_wrist_0_rgb")
SLOT_TO_PI05_KEY = {"pi05_base_0_rgb": "observation.images.base_0_rgb",
                    "pi05_left_wrist_0_rgb": "observation.images.left_wrist_0_rgb",
                    "pi05_right_wrist_0_rgb": "observation.images.right_wrist_0_rgb"}

# ── 声明值（**每一个都带来源 + 来源身份 + as_of**；来源身份在运行时复算，不转录）──────────
D_ORDER_AS_OF = "2026-09-30T14:11+08:00（文件 mtime；补单四 = 裁定 98 那一版）"
C2_BROADCAST_AS_OF = "2026-09-30T13:45:57+08:00（件内自述）+ 裁定 98.3 追加 14:29"

SMALL_FILE_MAX_BYTES = 8 * 1024 * 1024
READS: list[str] = []


# ══════════════════════ 基础测量工具（全部只读）══════════════════════
def _rel(p: pathlib.Path) -> str:
    s = str(p)
    return s[len(str(REPO)) + 1:] if s.startswith(str(REPO)) else s


def _note_read(path: pathlib.Path) -> None:
    r = _rel(path)
    if r not in READS:
        READS.append(r)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def stream_identity(path: pathlib.Path, *, scan_keys: tuple[str, ...] = ()) -> dict:
    """**单遍流式**取身份：sha256[:12] + bytes + 两个行数口径 + mtime + 顶层标量键扫描。

    为什么流式：`gate_verdict.json` 实测 ~99 MB（裁定 97.4 的体积纪律 ⇒ 不整件载入）。
    sha 与行数在同一次读里算完 ⇒ 不存在「读了两次、两次不是同一份」。
    顶层键扫描按**首键行的缩进**锚定（本仓产物 indent=1 或 2 ⇒ 顶层键缩进 = 该值），
    避免把嵌套的同名键误当顶层值；命中不到 ⇒ 该键写 null（不猜）。
    """
    out: dict = {"path": _rel(path), "measurement_status": "not_measured"}
    if not path.exists():
        out["why_not_measured"] = "路径不存在（读不到 ≠ 测到没有）"
        return out
    _note_read(path)
    h = hashlib.sha256()
    n_bytes = n_newlines = 0
    tail = b""
    head = b""
    found: dict = {k: None for k in scan_keys}
    try:
        with path.open("rb") as fh:
            while True:
                b = fh.read(1 << 20)
                if not b:
                    break
                h.update(b)
                n_bytes += len(b)
                n_newlines += b.count(b"\n")
                if len(head) < 8192:
                    head = (head + b)[:8192]
                buf = tail + b
                tail = buf[-8192:]
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"{type(exc).__name__}: {exc}"
        return out
    txt_lines = n_newlines + (0 if (not n_bytes or tail.endswith(b"\n")) else 1)
    st = path.stat()
    out.update({
        "measurement_status": "measured",
        "sha256_12": h.hexdigest()[:12],
        "bytes": n_bytes,
        "n_lines_wc": n_newlines,
        "n_lines_splitlines": txt_lines,
        "n_lines_caliber": N_LINES_CALIBER,
        "ends_with_newline": bool(n_bytes) and tail.endswith(b"\n"),
        "mtime": datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc
                                                 ).astimezone().isoformat(timespec="seconds"),
    })
    if scan_keys:
        mm = re.search(rb"\n([ \t]+)\"", head)
        indent = len(mm.group(1)) if mm else 2
        out["scan_indent_spaces"] = indent
        out["scan_method"] = "streaming_anchored_regex(顶层缩进锚定)"
        for k in scan_keys:
            pat = re.compile((r"\n" + " " * indent + re.escape('"%s"' % k)
                              + r"\s*:\s*(\"(?:[^\"\\]|\\.)*\"|-?[\d.eE+-]+|true|false|null)"))
            hit = None
            for chunk_text in _iter_text_chunks(path, 1 << 22):
                hit = pat.search(chunk_text)
                if hit:
                    break
            found[k] = _json_scalar(hit.group(1)) if hit else None
        out["scanned_top_level"] = found
    return out


def _iter_text_chunks(path: pathlib.Path, size: int):
    """带 4 KB 重叠的文本流（跨块边界的键也能命中）。"""
    tail = ""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        while True:
            s = fh.read(size)
            if not s:
                return
            yield tail + s
            tail = s[-4096:]


def _json_scalar(raw: str):
    try:
        return json.loads(raw)
    except Exception:                                                 # noqa: BLE001
        return raw.strip('"')


def load_json(path: pathlib.Path) -> tuple[object | None, dict]:
    """小件整件载入（>8 MB 走流式，见 `stream_identity`）。返回 (对象, 身份块)。"""
    ident = stream_identity(path)
    if ident.get("measurement_status") != "measured":
        return None, ident
    if ident["bytes"] > SMALL_FILE_MAX_BYTES:
        ident["json_load"] = "skipped_too_large(>8MB，改用 stream_identity 的顶层扫描)"
        return None, ident
    try:
        return json.loads(path.read_text(encoding="utf-8")), ident
    except Exception as exc:                                          # noqa: BLE001
        ident["json_load_error"] = f"{type(exc).__name__}: {exc}"
        return None, ident


def text_of(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    _note_read(path)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:                                                 # noqa: BLE001
        return None


def count_in_text(path: pathlib.Path, needle: str) -> int | None:
    t = text_of(path)
    return None if t is None else t.count(needle)


def find_key_paths_equal(obj, value, _pre="", _out=None, limit=12):
    """在 JSON 对象里找出**值逐字等于 `value`** 的键路径（最多 limit 条）。"""
    if _out is None:
        _out = []
    if len(_out) >= limit:
        return _out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v == value:
                _out.append(f"{_pre}{k}")
            elif isinstance(v, (dict, list)):
                find_key_paths_equal(v, value, f"{_pre}{k}.", _out, limit)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:400]):
            if isinstance(v, str) and v == value:
                _out.append(f"{_pre}[{i}]")
            elif isinstance(v, (dict, list)):
                find_key_paths_equal(v, value, f"{_pre}[{i}].", _out, limit)
    return _out


def module_string_constants(path: pathlib.Path) -> dict:
    """**用 ast 读常量、不 import 执行**（避免在他线模块里产生任何副作用）。"""
    t = text_of(path)
    if t is None:
        return {}
    try:
        tree = ast.parse(t)
    except SyntaxError:
        return {}
    consts: dict = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        try:
            consts[name] = ast.literal_eval(node.value)
        except Exception:                                             # noqa: BLE001
            if isinstance(node.value, (ast.Tuple, ast.List)):
                vals = []
                ok = True
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant):
                        vals.append(elt.value)
                    elif isinstance(elt, ast.Name) and elt.id in consts:
                        vals.append(consts[elt.id])
                    else:
                        ok = False
                        break
                if ok:
                    consts[name] = tuple(vals)
    return consts


# ══════════════════════ 三值判据构造器 ══════════════════════
def declared(value, *, source, source_path=None, as_of=None, verbatim=None):
    d = {"value": value, "source": source, "as_of": as_of}
    if source_path:
        d["source_path"] = source_path
    if verbatim:
        d["source_verbatim"] = verbatim
    return d


def compare(declared_value, measured_value, *, measurement_status="measured"):
    """三值比较：measured_value 取不到 ⇒ `match=None`（**不许**用 None==None 冒充绿）。"""
    if measurement_status != "measured" or measured_value is None:
        return None
    return bool(declared_value == measured_value)


def item(item_id, what, *, measured=None, measurement_status="measured",
         declared_block=None, match=None, severity=None, severity_reason=None,
         binding_for_bc=None, note=None, adjudication_owner=None,
         why_not_measured=None):
    it = {"item_id": item_id, "what": what,
          "measurement_status": measurement_status,
          "measured": measured}
    if declared_block is not None:
        it["declared"] = declared_block
    if match is not None:
        it["match"] = match
    if measurement_status != "measured":
        it["why_not_measured"] = why_not_measured or "见 measured 块内的 why_not_measured"
    if severity:
        it["severity"] = severity
    if severity_reason:
        it["severity_reason"] = severity_reason
    if binding_for_bc is not None:
        it["binding_for_bc"] = binding_for_bc
    if adjudication_owner:
        it["adjudication_owner"] = adjudication_owner
    if note:
        it["note"] = note
    return it


# ══════════════════════ S1 · team_form / lerobot 完整性 ══════════════════════
def _dv(src: dict, value, verbatim=None, clause="§三-1"):
    return declared(value, source=f"D→B2 执行单 {clause}（T-B2-19）", source_path=P_D_ORDER,
                    as_of=D_ORDER_AS_OF, verbatim=verbatim)


def _lerobot_robot_type_enforcement() -> dict:
    """**旁证**（不是声明项）：本机安装的 lerobot 是否对 `robot_type` 做白名单/断言校验。
    只读扫描 `site-packages/lerobot/**/*.py`，找同时含 `robot_type` 与判等/断言/抛错的行。"""
    out: dict = {"measurement_status": "not_measured",
                 "method": "只读文本扫描（含 robot_type ∧ 含 assert/raise/!=/==）"}
    cands = sorted(pathlib.Path("/root/venvs/pi05_sim/lib").glob("python3*/site-packages/lerobot"))
    if not cands:
        out["why_not_measured"] = "未在 /root/venvs/pi05_sim/lib/python3*/site-packages 下找到 lerobot 包"
        return out
    pkg = cands[0]
    _note_read(pkg)
    hits, n_files, n_refs = [], 0, 0
    ver = None
    try:
        for py in sorted(pkg.rglob("*.py")):
            n_files += 1
            try:
                t = py.read_text(encoding="utf-8", errors="replace")
            except Exception:                                         # noqa: BLE001
                continue
            n_refs += t.count("robot_type")
            for i, ln in enumerate(t.splitlines(), 1):
                if "robot_type" in ln and any(k in ln for k in ("assert", "raise", "!=", "==")):
                    hits.append(f"{_rel(py)}:{i}: {ln.strip()[:160]}")
        vfile = pkg / "__init__.py"
        if vfile.exists():
            m = re.search(r"__version__\s*=\s*[\"']([^\"']+)", vfile.read_text(encoding="utf-8"))
            ver = m.group(1) if m else None
    except Exception as exc:                                          # noqa: BLE001
        out.update({"why_not_measured": f"{type(exc).__name__}: {exc}"})
        return out
    out.update({"measurement_status": "measured", "package_dir": str(pkg),
                "lerobot_version_in_init": ver, "n_py_files_scanned": n_files,
                "n_robot_type_references": n_refs,
                "n_equality_or_assert_lines": len(hits), "lines": hits[:10],
                "reading": ("命中行只做**跨数据集聚合时的一致性比较**，不是对某个字面值的白名单校验"
                            if hits and all("aggregate" in h for h in hits) else
                            "见 lines（B2 不代 A2 判它是否影响 π₀.₅ 加载）")})
    return out


def section_s1(src: dict) -> list[dict]:
    out: list[dict] = []
    info, info_ident = load_json(REPO / P_LEROBOT_INFO)
    out.append(item("S1.0_lerobot_info_identity",
                    "lerobot `meta/info.json` 的身份三元组（sha256[:12] / bytes / 两个行数口径 / mtime）",
                    measured=info_ident,
                    measurement_status=info_ident.get("measurement_status", "not_measured"),
                    note=("D 的执行单**没有**给这件的声明身份 ⇒ 只登记实测值、`match` 留空"
                          "（不假装有对账对象；三值纪律）。")))
    if info is None:
        out.append(item("S1.1_to_S1.6_info_fields",
                        "codebase_version / robot_type / episodes / 三相机槽 / 容器 fps 口径",
                        measured=None, measurement_status="not_measured",
                        declared_block=_dv(src, {"codebase_version": "v3.0",
                                                 "robot_type": "aloha_bimanual",
                                                 "camera_slots": list(PI05_SLOTS_DECLARED),
                                                 "container_fps": "500/17"}),
                        why_not_measured="`meta/info.json` 读不到（或 >8 MB）⇒ 下游字段一律 not_measured，不用 false/0 顶替"))
        return out

    feats = info.get("features") or {}
    # ── S1.1 codebase_version ──
    cv = info.get("codebase_version")
    out.append(item("S1.1_codebase_version", "lerobot 数据集容器版本",
                    measured={"codebase_version": cv},
                    declared_block=_dv(src, "v3.0", verbatim="`codebase_version=v3.0`"),
                    match=compare("v3.0", cv), severity=None if cv == "v3.0" else "binding",
                    severity_reason=None if cv == "v3.0" else "执行单点名的完整性字段不符",
                    binding_for_bc=True))
    # ── S1.2 robot_type ──
    rt = info.get("robot_type")
    rt_lit = ("aloha_bimanual" if rt is None else
              ("literal_equal" if rt == "aloha_bimanual" else
               ("prefix_match" if str(rt).startswith("aloha_bimanual") else "differs")))
    out.append(item("S1.2_robot_type", "`robot_type` 与执行单字面值的比对",
                    measured={"robot_type": rt, "literal_comparison": rt_lit,
                              "morphology_label_used_across_lines": "aloha_bimanual_14d",
                              "written_by": f"{P_B2_GEN}:2884（robot_type= 实参，B2 自己的生成器）",
                              "lerobot_enforcement_probe": _lerobot_robot_type_enforcement()},
                    declared_block=_dv(src, "aloha_bimanual", verbatim="`robot_type=aloha_bimanual`"),
                    match=compare("aloha_bimanual", rt),
                    severity="registered_difference",
                    severity_reason=("实测值是执行单字面值的**前缀扩展**（`aloha_bimanual_14d(gym_aloha "
                                     "vx300s dual-arm)`），不是另一个 robot；本机 lerobot 只在跨数据集"
                                     "聚合时比较 robot_type、无字面白名单（见 measured 的旁证块）。"
                                     "**是否影响 π₀.₅ 加载 = 准入问题，归 A2（裁定 93.4）**，B2 不代判。"),
                    binding_for_bc=False, adjudication_owner="A2（准入）/ D（若要把字面值改成实测值）"))
    # ── S1.3 episodes / frames ──
    team, team_ident = load_json(REPO / P_TEAM_MANIFEST)
    eps_dirs = None
    train_p = REPO / P_TEAM_TRAIN
    if train_p.exists():
        _note_read(train_p)
        eps_dirs = sorted(d.name for d in train_p.rglob("episode_*") if d.is_dir())
    sidecar_dir = REPO / P_SIDECAR_DIR
    sidecars = None
    if sidecar_dir.exists():
        _note_read(sidecar_dir)
        sidecars = sorted(p.name for p in sidecar_dir.glob("episode_*.json"))
    ep_rows = _parquet_num_rows(REPO / P_LEROBOT_EPISODES)
    data_rows = _parquet_rows_sum(P_LEROBOT_ROOT + "/data")
    tasks_rows = _parquet_num_rows(REPO / P_LEROBOT_TASKS)
    n_eps_measured = {
        "lerobot_info_total_episodes": info.get("total_episodes"),
        "lerobot_info_total_frames": info.get("total_frames"),
        "lerobot_info_total_tasks": info.get("total_tasks"),
        "lerobot_info_splits": info.get("splits"),
        "lerobot_meta_episodes_parquet_rows": ep_rows,
        "lerobot_tasks_parquet_rows": tasks_rows,
        "lerobot_data_parquet_rows_sum": data_rows,
        "team_form_dataset_manifest_n_episodes": (team or {}).get("n_episodes"),
        "team_form_n_per_direction": (team or {}).get("n_per_direction"),
        "team_form_episode_dirs_on_disk": (None if eps_dirs is None else len(eps_dirs)),
        "sidecar_episode_json_count": (None if sidecars is None else len(sidecars)),
    }
    consistent = _episodes_consistent(n_eps_measured)
    out.append(item("S1.3_episodes_and_frames",
                    "episodes 数 / 帧数（四个独立计数口径互核：lerobot info、lerobot meta parquet、"
                    "team_form 清单、盘上目录与 sidecar 件数）",
                    measured=n_eps_measured,
                    measurement_status=("measured" if consistent["all_present"] else "not_measured"),
                    declared_block=declared({"n_episodes": 40, "n_frames": 11035, "n_per_direction": "20/20"},
                                            source="`work/project_parameters.json`（S1 formal-40 那条 evidence）"
                                                   " + C2 stats 档的 `provenance.frames[0]`",
                                            source_path=P_PARAMS, as_of=src["params"]["as_of"],
                                            verbatim="40 集 / 11035 帧"),
                    match=consistent["match"], severity=None if consistent["match"] else "binding",
                    severity_reason=None if consistent["match"] else "计数口径之间不一致 ⇒ 数据集不完整",
                    binding_for_bc=True, note=consistent["detail"],
                    why_not_measured=None if consistent["all_present"] else consistent["missing"]))
    # ── S1.4 三相机槽 ──
    gen_consts = module_string_constants(REPO / P_B2_GEN)
    gen_slots = gen_consts.get("PI05_SLOTS")
    gen_map = gen_consts.get("SLOT_TO_PI05_KEY")
    img_feats = {k: v for k, v in feats.items() if k.startswith("observation.images.")}
    slot_rows = []
    for slot in PI05_SLOTS_DECLARED:
        key = (gen_map or {}).get(slot, SLOT_TO_PI05_KEY.get(slot))
        f = img_feats.get(key) or {}
        fi = f.get("info") or {}
        slot_rows.append({
            "declared_slot_name": slot,
            "lerobot_feature_key": key,
            "feature_present_in_info_json": bool(f),
            "dtype": f.get("dtype"), "shape": f.get("shape"),
            "image_codec": fi.get("image.codec"), "storage": fi.get("storage"),
            "camera_id_in_mujoco_model": fi.get("camera_id_in_mujoco_model"),
            "team_form_camera_slots_pi05_entry": ((team or {}).get("camera_slots", {})
                                                  .get("pi05", {}) or {}).get(key),
        })
    slots_ok = all(r["feature_present_in_info_json"] and r["dtype"] == "image"
                   and r["shape"] == [224, 224, 3] and r["camera_id_in_mujoco_model"] for r in slot_rows)
    out.append(item("S1.4_three_camera_slots",
                    "三相机槽：执行单点名的是 B2 的**槽名**（`pi05_*`），lerobot 容器里对应的是"
                    "`observation.images.*` 特征键 ⇒ 本项核的是**映射是否一一对应且三槽齐备**",
                    measured={"slots": slot_rows, "n_slots": len(slot_rows),
                              "generator_PI05_SLOTS": list(gen_slots) if gen_slots else None,
                              "generator_SLOT_TO_PI05_KEY": gen_map,
                              "generator_constants_source": f"{P_B2_GEN}（ast 只读取常量，未 import 执行）",
                              "all_three_present_and_image_224x224x3": bool(slots_ok)},
                    declared_block=_dv(src, list(PI05_SLOTS_DECLARED),
                                       verbatim="三相机槽（`pi05_base_0_rgb` / `pi05_left_wrist_*` / `pi05_right_wrist_*`）"),
                    match=(True if (slots_ok and tuple(gen_slots or ()) == PI05_SLOTS_DECLARED) else False),
                    severity=None if slots_ok else "binding",
                    severity_reason=None if slots_ok else "三槽不齐备 ⇒ BC 的图像输入不完整",
                    binding_for_bc=True,
                    note=("**命名口径差**（登记，不是缺陷）：`pi05_base_0_rgb` 这类槽名只活在 B2 生成器常量与"
                          " sidecar 里；lerobot `info.json` 的特征键是 `observation.images.base_0_rgb` 等，"
                          "由 `SLOT_TO_PI05_KEY` 一一对应。base 槽的 mujoco 相机 = `angle`（**不是** `top`；"
                          "`top` 是团队 head 槽用的真相机）。")))
    # ── S1.5 容器 fps = 500/17 ──
    freq = (team or {}).get("frequency") or {}
    fps = info.get("fps")
    fps_double_eq = (None if not isinstance(fps, (int, float)) else bool(fps == 500 / 17))
    fps_frac = (None if not isinstance(fps, (int, float))
                else str(Fraction(fps).limit_denominator(1000)))
    fps_row = {
        "lerobot_info_fps": fps,
        "lerobot_info_fps_repr": (None if fps is None else repr(fps)),
        "fps_double_equals_500_over_17": fps_double_eq,
        "fps_lowest_terms_denominator_le_1000": fps_frac,
        "500/17_as_double": 500 / 17,
        "team_form_fps_rational_in_container": freq.get("fps_rational_in_container"),
        "team_form_DT": freq.get("DT"), "team_form_n_sub_steps": freq.get("n_sub_steps"),
        "team_form_model_timestep_s": freq.get("model_timestep_s"),
        "team_form_control_hz_measured": freq.get("control_hz_measured"),
        "DT_times_substeps_equals_1_over_fps": (
            None if not isinstance(freq.get("DT"), (int, float)) else
            bool(abs(freq["DT"] * (freq.get("n_sub_steps") or 0) - 1 / fps) < 1e-12)
            if isinstance(fps, (int, float)) and fps else None),
        "per_episode_fps_rational_sample": ((team or {}).get("episodes") or [{}])[0].get("fps_rational"),
    }
    fps_ok = bool(fps_row["team_form_fps_rational_in_container"] == "500/17" and fps_double_eq
                  and fps_frac == "500/17")
    out.append(item("S1.5_container_fps_500_over_17",
                    "容器 fps 口径 = `500/17`（DT 0.034 = 17 × 0.002 ⇒ 有理数口径与 double 口径同值）",
                    measured=fps_row,
                    declared_block=_dv(src, "500/17", verbatim="容器 fps **`500/17`**"),
                    match=fps_ok, severity=None if fps_ok else "binding",
                    severity_reason=None if fps_ok else "fps 口径不符 ⇒ 时间轴与 A2 运行时不同频",
                    binding_for_bc=True,
                    note=("**double 与有理数两口径实测同值**：`info.json` 里的 fps 字面 `29.41176470588235` "
                          "解析出的 double **== 500/17**（差 0.0），最简分数（分母 ≤1000）也是 `500/17` "
                          "⇒ 不存在「29.4118 与 500/17 是两个数」的隐患。")))
    # ── S1.6 图像载荷在 parquet 内联（`images/` 空目录 **不是** 缺数据）──
    out.append(item("S1.6_image_payload_inline_parquet",
                    "三槽图像载荷的实际存放位置与可读性（PNG magic 逐槽实测）",
                    measured=_image_payload_probe(REPO / P_LEROBOT_ROOT, img_feats),
                    declared_block=None,
                    note=("执行单没点名这一项，但它是「`images/` 三个目录 0 条目」这个**极易被误读成缺数据**的"
                          "事实的唯一解药：`info.json` 的 `storage=inline_parquet` + `image.codec=png` ⇒ "
                          "像素字节在 `data/chunk-000/file-00{0,1}.parquet` 里面，目录空是**设计如此**。")))
    # ── S1.7 数据集自己的闸判词 + demo_manifest 身份链 ──
    npzman, npzman_ident = load_json(REPO / P_NPZ_MANIFEST)
    sd = ((npzman or {}).get("source_dataset") or {})
    demo_ident = stream_identity(REPO / P_DEMO_MANIFEST)
    out.append(item("S1.7_dataset_own_gates_and_manifest_identity",
                    "这份数据集自己的 19 道闸判词（取自 npz 侧 manifest 的 `source_dataset`）+ "
                    "`demo_manifest.json` 的**当前**身份与历史身份链",
                    measured={"gates_verdict": sd.get("gates_verdict"),
                              "gates_n_checks": sd.get("gates_n_checks"),
                              "gates_n_red": sd.get("gates_n_red"),
                              "gates_n_warn": sd.get("gates_n_warn"),
                              "gates_n_a": sd.get("gates_n_a"),
                              "gates_precondition": sd.get("gates_precondition"),
                              "npz_side_manifest": npzman_ident,
                              "demo_manifest_current": demo_ident,
                              "demo_manifest_identity_chain": [
                                  {"sha256_12": "0c057e22690f", "bytes": 3577346,
                                   "as_of": "2026-09-30T02:57:21+08:00",
                                   "why": "生成器落地原字节（19 道闸的结果在这一份里）"},
                                  {"sha256_12": "561ab330fea7", "bytes": 4466471,
                                   "as_of": "2026-09-30T03:06:38+08:00",
                                   "why": "npz 导出按契约 §17-4 追加写后"},
                                  {"sha256_12": "e319754dd030", "bytes": 4473151,
                                   "as_of": "2026-09-30T03:21:03+08:00",
                                   "why": "B2 追加 `renderer_arm_compensating_control` + `naming_note` 后（= 当前值）"}],
                              "chain_source": "docs/b2_handoff_to_c2_formal40_20260930.md:55-64"},
                    measurement_status=demo_ident.get("measurement_status", "not_measured"),
                    declared_block=declared("0c057e22690f（124302 行，as_of 02:57:21）",
                                            source="`work/project_parameters.json` 的 S1 formal-40 条 + "
                                                   "`work/decisions/decisions_20260929.md` §89.1",
                                            source_path=P_PARAMS, as_of=src["params"]["as_of"],
                                            verbatim="demo_manifest.json = **124302 ln 0c057e22690f** as_of 02:57:21"),
                    match=(True if demo_ident.get("sha256_12") == "0c057e22690f" else False),
                    severity="registered_difference",
                    severity_reason=("**这不是缺陷、也不是数据变了**：声明值带 as_of 02:57:21（合规），"
                                     "而 `demo_manifest.json` 之后被 B2 按契约两次**追加写**（npz 导出登记 + "
                                     "裁定 88.5-1 的补偿控制字段）⇒ 当前字节是 `e319754dd030`。"
                                     "**风险只在读法**：谁把 `0c057e22690f` 当「现值」去比，就会得到假不符"
                                     "（`citation_sha_as_of_discipline`，与裁定 98.3 的行数口径同族）。"),
                    binding_for_bc=False, adjudication_owner="D（参数表那条 evidence 若要追平现值）",
                    note="闸判词 PASS/19/0 是**这份数据集自己的**闸（不是 C2 的归一化闸、更不是任何 policy 指标）。"))
    return out


def _episodes_consistent(m: dict) -> dict:
    want_eps, want_frames = 40, 11035
    checks = {
        "lerobot_info_total_episodes==40": m.get("lerobot_info_total_episodes") == want_eps,
        "lerobot_info_total_frames==11035": m.get("lerobot_info_total_frames") == want_frames,
        "lerobot_meta_episodes_parquet_rows==40": m.get("lerobot_meta_episodes_parquet_rows") == want_eps,
        "lerobot_data_parquet_rows_sum==11035": m.get("lerobot_data_parquet_rows_sum") == want_frames,
        "team_form_n_episodes==40": m.get("team_form_dataset_manifest_n_episodes") == want_eps,
        "team_form_episode_dirs==40": m.get("team_form_episode_dirs_on_disk") == want_eps,
        "sidecar_json_count==40": m.get("sidecar_episode_json_count") == want_eps,
        "per_direction_20_20": m.get("team_form_n_per_direction") == {"right_to_left": 20,
                                                                     "left_to_right": 20},
    }
    missing = [k for k, v in m.items() if v is None]
    return {"checks": checks, "match": bool(all(checks.values()) and not missing),
            "all_present": not missing, "missing": missing or None,
            "detail": {k: v for k, v in checks.items() if not v} or "全部一致"}


def _parquet_num_rows(path: pathlib.Path):
    if not path.exists():
        return None
    try:
        import pyarrow.parquet as pq
        _note_read(path)
        return int(pq.ParquetFile(str(path)).metadata.num_rows)
    except Exception:                                                 # noqa: BLE001
        return None


def _parquet_rows_sum(dir_rel: str) -> int | None:
    d = REPO / dir_rel
    if not d.exists():
        return None
    try:
        import pyarrow.parquet as pq
        tot = 0
        files = sorted(d.rglob("*.parquet"))
        if not files:
            return None
        for f in files:
            _note_read(f)
            tot += int(pq.ParquetFile(str(f)).metadata.num_rows)
        return tot
    except Exception:                                                 # noqa: BLE001
        return None


def _image_payload_probe(root: pathlib.Path, img_feats: dict) -> dict:
    out: dict = {"measurement_status": "not_measured"}
    try:
        import pyarrow.parquet as pq
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"pyarrow 不可用：{type(exc).__name__}: {exc}"
        return out
    files = sorted((root / "data").rglob("*.parquet"))
    if not files:
        out["why_not_measured"] = "data/ 下没有 parquet"
        return out
    per_file, cols = [], {}
    try:
        for f in files:
            _note_read(f)
            pf = pq.ParquetFile(str(f))
            per_file.append({"path": _rel(f), "num_rows": int(pf.metadata.num_rows),
                             "num_row_groups": int(pf.metadata.num_row_groups),
                             "bytes": f.stat().st_size})
        keys = [k for k in img_feats if img_feats[k].get("dtype") == "image"]
        if not keys:
            out["why_not_measured"] = "info.json 里没有 dtype=image 的特征键"
            return out
        pf = pq.ParquetFile(str(files[0]))
        batch = next(pf.iter_batches(batch_size=2, columns=keys))
        for k in keys:
            v = batch.column(k)[0].as_py()
            raw = v.get("bytes") if isinstance(v, dict) else v
            cols[k] = {"value_type": type(v).__name__,
                       "payload_bytes": (len(raw) if isinstance(raw, (bytes, bytearray)) else None),
                       "png_magic": (raw[:4] == b"\x89PNG" if isinstance(raw, (bytes, bytearray)) else False),
                       "non_null_in_batch": int(batch.column(k).null_count == 0)}
        img_dirs = {}
        for d in sorted((root / "images").glob("*")):
            _note_read(d)
            img_dirs[d.name] = {"n_entries": len(list(d.iterdir())),
                                "storage_declared_in_info": (img_feats.get(d.name, {}).get("info", {})
                                                             or {}).get("storage")}
        out.update({"measurement_status": "measured", "parquet_files": per_file,
                    "parquet_rows_total": sum(x["num_rows"] for x in per_file),
                    "first_row_image_probe_per_slot": cols,
                    "images_dirs": img_dirs,
                    "reading": ("三个 `images/*` 目录 0 条目 = **设计如此**（`storage=inline_parquet`）；"
                               "像素字节在 parquet 内、首行三槽都读到 PNG magic ⇒ 载荷在场。")})
    except Exception as exc:                                          # noqa: BLE001
        out.update({"why_not_measured": f"{type(exc).__name__}: {exc}"})
    return out


# ══════════════════════ S2 · states_14d.npz（权威读路径 --s1-frames）══════════════════════
def _npz_probe(path: pathlib.Path) -> dict:
    out: dict = {"measurement_status": "not_measured"}
    if not path.exists():
        out["why_not_measured"] = "npz 路径不存在（读不到 ≠ 测到没有）"
        return out
    try:
        import numpy as np
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"numpy 不可用：{type(exc).__name__}: {exc}"
        return out
    try:
        _note_read(path)
        z = np.load(str(path), allow_pickle=False)
        arrays = sorted(z.files)
        fr = z["frames"]
        content = hashlib.sha256(np.ascontiguousarray(fr, dtype=np.float64).tobytes()).hexdigest()[:12]
        dc = z["direction_code"] if "direction_code" in arrays else None
        out.update({
            "measurement_status": "measured",
            "arrays": arrays,
            "frames_shape": list(fr.shape), "frames_dtype": str(fr.dtype),
            "frames_content_sha256_12": content,
            "frames_content_sha_definition": "sha256(float64 C-contiguous bytes of frames)[:12]",
            "start_poses_shape": (list(z["start_poses"].shape) if "start_poses" in arrays else None),
            "episode_boundaries_len": (int(z["episode_boundaries"].size)
                                       if "episode_boundaries" in arrays else None),
            "n_episodes_derived_from_boundaries": (int(z["episode_boundaries"].size - 1)
                                                   if "episode_boundaries" in arrays else None),
            "per_direction_episode_counts": (
                {str(int(k)): int(v) for k, v in zip(*[list(x) for x in np.unique(dc, return_counts=True)])}
                if dc is not None else None),
            "physical_range_effective": (z["physical_range_effective"].tolist()
                                         if "physical_range_effective" in arrays else None),
        })
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"{type(exc).__name__}: {exc}"
    return out


def _npz_vs_lerobot_bitwise(npz_path: pathlib.Path, lerobot_root: pathlib.Path) -> dict:
    """**B2 独立复算**（不引 C2 的结论）：npz 的 `frames` 与 lerobot parquet 的 `observation.state`
    是否逐位相同（float32 → float64 加宽必须无损），且集号/帧号顺序一致。"""
    out: dict = {"measurement_status": "not_measured",
                 "why_this_matters": ("这条是「BC 吃的图像/动作数据集」与「C2 算 stats 吃的 npz」"
                                      "**同源**的身份层证据（裁定 85.4-3 / 90.4-4）；"
                                      "C2 也算过一次，这里是 B2 侧的独立复算，不是转录。")}
    if not npz_path.exists():
        out["why_not_measured"] = "npz 不存在"
        return out
    try:
        import numpy as np
        import pyarrow.parquet as pq
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"numpy/pyarrow 不可用：{type(exc).__name__}: {exc}"
        return out
    try:
        files = sorted((lerobot_root / "data").rglob("*.parquet"))
        if not files:
            out["why_not_measured"] = "lerobot data/ 下没有 parquet"
            return out
        cols = ["observation.state", "episode_index", "frame_index"]
        st, ep, fi = [], [], []
        for f in files:
            _note_read(f)
            t = pq.read_table(str(f), columns=cols)
            st.extend(t.column("observation.state").to_pylist())
            ep.extend(t.column("episode_index").to_pylist())
            fi.extend(t.column("frame_index").to_pylist())
        raw = np.asarray(st, dtype=np.float32)
        epa = np.asarray(ep, dtype=np.int64)
        fia = np.asarray(fi, dtype=np.int64)
        file_order_already_sorted = bool(np.all(np.lexsort((fia, epa)) == np.arange(epa.size)))
        order = np.lexsort((fia, epa))
        raw = raw[order]
        z = np.load(str(npz_path), allow_pickle=False)
        fr = z["frames"]
        wide = raw.astype(np.float64)
        out.update({
            "measurement_status": "measured",
            "n_rows_lerobot": int(raw.shape[0]), "lerobot_shape": list(raw.shape),
            "npz_frames_shape": list(fr.shape),
            "file_order_already_sorted_by_episode_then_frame": file_order_already_sorted,
            "upcast_float32_to_float64_bitwise_lossless": bool(np.array_equal(wide.view(np.uint64),
                                                                             fr.view(np.uint64))),
            "array_equal_float64": bool(np.array_equal(wide, fr)),
            "max_abs_diff": float(np.max(np.abs(wide - fr))) if wide.shape == fr.shape else None,
            "episode_index_equal": bool(np.array_equal(epa[order], z["episode_index"]))
            if "episode_index" in z.files else None,
            "episode_boundaries_equal": bool(np.array_equal(
                np.searchsorted(epa[order], np.arange(int(epa.max()) + 2), side="left"),
                z["episode_boundaries"])) if "episode_boundaries" in z.files else None,
        })
        out["verdict_same_source_bitwise"] = bool(out["array_equal_float64"]
                                                  and out["upcast_float32_to_float64_bitwise_lossless"])
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"{type(exc).__name__}: {exc}"
    return out


def section_s2(src: dict) -> list[dict]:
    out: list[dict] = []
    npz_p = REPO / P_NPZ
    ident = stream_identity(npz_p)
    probe = _npz_probe(npz_p)
    dec = declared({"sha256_12": "a84a26079550", "bytes": 1332184},
                   source="D→B2 执行单 §三-2（T-B2-19）", source_path=P_D_ORDER,
                   as_of=D_ORDER_AS_OF,
                   verbatim="`states_14d.npz`（**1332184 B `a84a26079550`**）")
    sha_ok = (None if ident.get("measurement_status") != "measured"
              else bool(ident["sha256_12"] == "a84a26079550" and ident["bytes"] == 1332184))
    out.append(item("S2.1_npz_identity",
                    "`states_14d.npz` 的身份三元组（**B2 自己复算**，不转录 D 或 C2 的数）",
                    measured=ident, measurement_status=ident.get("measurement_status", "not_measured"),
                    declared_block=dec, match=sha_ok,
                    severity=None if sha_ok else "binding",
                    severity_reason=None if sha_ok else "npz 字节与声明不符 ⇒ 同源链断",
                    binding_for_bc=True,
                    note="声明路径来自执行单/参数表点名（裁定 97.7-①：不 glob 后挑一份）。"))
    cs = probe.get("frames_content_sha256_12")
    out.append(item("S2.2_frames_content_sha",
                    "`frames` 的内容 sha（口径 = `sha256(float64 C 连续字节)[:12]`，裁定 90.4-4）",
                    measured=probe, measurement_status=probe.get("measurement_status", "not_measured"),
                    declared_block=declared("c9a72480fcb7",
                                            source="D→B2 执行单 §三-2 + 裁定 90.4-4（权威读路径 `--s1-frames`）",
                                            source_path=P_D_ORDER, as_of=D_ORDER_AS_OF,
                                            verbatim="frames content sha **`c9a72480fcb7`**"),
                    match=compare("c9a72480fcb7", cs),
                    severity=None if cs == "c9a72480fcb7" else "binding",
                    severity_reason=None if cs == "c9a72480fcb7" else "内容 sha 不符 ⇒ 帧序或数值被改过",
                    binding_for_bc=True))
    out.append(item("S2.3_schema_and_shape",
                    "契约 §17-4 的 schema：`frames=[N,14] float64`、`start_poses=[E,14]`、集边界",
                    measured={"frames_shape": probe.get("frames_shape"),
                              "frames_dtype": probe.get("frames_dtype"),
                              "start_poses_shape": probe.get("start_poses_shape"),
                              "episode_boundaries_len": probe.get("episode_boundaries_len"),
                              "n_episodes_derived": probe.get("n_episodes_derived_from_boundaries"),
                              "per_direction_episode_counts": probe.get("per_direction_episode_counts")},
                    measurement_status=probe.get("measurement_status", "not_measured"),
                    declared_block=declared("frames=[N,14] float64；start_poses=[E,14]；按集拼接、集序号升序",
                                            source="npz 侧 `manifest.json` 的 `contract_fields`（契约 §17-4，裁定 82.2）",
                                            source_path=P_NPZ_MANIFEST, as_of=src["npz_manifest"]["as_of"]),
                    match=(None if probe.get("measurement_status") != "measured" else
                           bool(probe.get("frames_shape") == [11035, 14]
                                and probe.get("frames_dtype") == "float64"
                                and probe.get("start_poses_shape") == [40, 14]
                                and probe.get("per_direction_episode_counts") == {"0": 20, "1": 20})),
                    severity=None, binding_for_bc=True))
    bitw = _npz_vs_lerobot_bitwise(npz_p, REPO / P_LEROBOT_ROOT)
    out.append(item("S2.4_npz_vs_lerobot_bitwise",
                    "npz `frames` ↔ lerobot `observation.state` 逐位相同（B2 独立复算）",
                    measured=bitw, measurement_status=bitw.get("measurement_status", "not_measured"),
                    match=(None if bitw.get("measurement_status") != "measured"
                           else bitw.get("verdict_same_source_bitwise")),
                    severity=None if bitw.get("verdict_same_source_bitwise") else "binding",
                    severity_reason=None if bitw.get("verdict_same_source_bitwise") else "两侧不同源",
                    binding_for_bc=True,
                    note=("**独立性声明**：B2 的导出器与 C2 的读路径都读同一份 parquet ⇒ 这条证明的是"
                          "「帧序/集号/数值一致」，**不是**「数据物理正确」（那归采集期的 19 道闸与 E 的"
                          "渲染确定性带）。C2 的 `crosscheck_vs_lerobot_reader` 也这么写，两边口径一致。")))
    sibs = _sibling_npz_copies(REPO / P_NPZ_SIBLING_GLOB_PARENT, npz_p)
    out.append(item("S2.5_sibling_copies_registered_not_candidates",
                    "同名兄弟件登记（**只登记、不作候选**）：`glob` 挑一份会挑错的风险面",
                    measured=sibs,
                    note=("裁定 97.7-① 的读法：消费方只对**声明的那一条路径**复算。本项把盘上其它同名件"
                          "的身份列出来，是为了让读者知道「按 glob 挑」在这里是**有歧义的**"
                          "（3 份与权威件逐字节相同、1 份是 pilot5 的不同数据）。")))
    return out


def _sibling_npz_copies(parent: pathlib.Path, authoritative: pathlib.Path) -> dict:
    out: dict = {"measurement_status": "not_measured", "authoritative_path": _rel(authoritative)}
    if not parent.exists():
        out["why_not_measured"] = "父目录不存在"
        return out
    try:
        rows = []
        for p in sorted(parent.rglob("states_14d.npz")):
            _note_read(p)
            h = hashlib.sha256()
            n = 0
            with p.open("rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
                    n += len(b)
            rows.append({"path": _rel(p), "sha256_12": h.hexdigest()[:12], "bytes": n,
                         "is_authoritative": p.resolve() == authoritative.resolve(),
                         "byte_identical_to_authoritative": None})
        auth = next((r["sha256_12"] for r in rows if r["is_authoritative"]), None)
        for r in rows:
            r["byte_identical_to_authoritative"] = (None if auth is None else r["sha256_12"] == auth)
        out.update({"measurement_status": "measured", "n_copies_on_disk": len(rows), "copies": rows})
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"{type(exc).__name__}: {exc}"
    return out


def _source_literal_fragments(text: str | None, const_name: str) -> dict | None:
    """从源码文本里取出某个常量的**字面量碎片**（隐式拼接会吃掉 ast 层的分段信息 ⇒ 只能读文本）。"""
    if not text:
        return None
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(const_name)}\s*=", ln):
            start = i
            break
    if start is None:
        return None
    frags: list[str] = []
    depth = 0
    end = start
    for j in range(start, min(len(lines), start + 16)):
        depth += lines[j].count("(") - lines[j].count(")")
        frags.extend(re.findall(r'"([^"\\\n]*)"', lines[j]))
        end = j
        if depth <= 0 and (j > start or "(" not in lines[j]):
            break
    return {"line_start": start + 1, "line_end": end + 1,
            "literal_fragments": frags, "joined": "".join(frags)}


# ══════════════════════ S3 · representation_version 三处逐字核对 ══════════════════════
def _scan_a2_runtime_products() -> dict:
    """**有界扫描**（裁定 93.8：审计器必须自报覆盖面）：A2 已落盘产物里出现过的
    `vla_runtime_v1:` 版本串，以及它们的 `stats=` token 取值。"""
    out: dict = {"measurement_status": "not_measured"}
    root = REPO / "runs/vla"
    if not root.exists():
        out["why_not_measured"] = "runs/vla 不存在"
        return out
    pat = re.compile(r"vla_runtime_v1:[^\"\\\s]*")
    seen: dict[str, list[str]] = {}
    n_files = n_hit = 0
    scope = ("runs/vla/a2_*/**/*.json，单件 ≤8 MB，最多扫 400 件，最多收 40 条不同串"
             "（**有界**：不做全盘扫描，遵守「禁 find /」的扫描纪律）")
    try:
        cands = []
        for d in sorted(root.glob("a2_*")):
            if not d.is_dir():
                continue
            for f in sorted(d.rglob("*.json")):
                try:
                    if f.stat().st_size <= SMALL_FILE_MAX_BYTES:
                        cands.append(f)
                except OSError:
                    continue
                if len(cands) >= 400:
                    break
            if len(cands) >= 400:
                break
        for f in cands:
            n_files += 1
            _note_read(f)
            try:
                t = f.read_text(encoding="utf-8", errors="replace")
            except Exception:                                         # noqa: BLE001
                continue
            for m in pat.findall(t):
                n_hit += 1
                if m not in seen and len(seen) < 40:
                    seen[m] = [_rel(f)]
                elif m in seen and len(seen[m]) < 3:
                    seen[m].append(_rel(f))
        full = {k: v for k, v in seen.items() if len(k) >= 30}
        frags = {k: v for k, v in seen.items() if len(k) < 30}
        toks = sorted({re.search(r":stats=([^:]*)", s).group(1)
                       for s in full if re.search(r":stats=([^:]*)", s)})
        out.update({"measurement_status": "measured", "scan_scope": scope,
                    "n_files_scanned": n_files, "n_occurrences": n_hit,
                    "n_distinct_full_version_strings": len(full),
                    "distinct_full_version_strings": {k: v for k, v in list(full.items())[:10]},
                    "n_prose_or_truncated_fragments": len(frags),
                    "prose_or_truncated_fragments": {k: v for k, v in list(frags.items())[:5]},
                    "fragment_caliber": ("长度 <30 的命中是**散文里的片段**（文书/docstring 提到 "
                                         "`vla_runtime_v1:` 这个前缀），不是运行时产出的完整版本串 ⇒ "
                                         "分开计数，免得把「22 条版本串」读成运行时事实。"),
                    "distinct_stats_tokens": toks,
                    "any_stats_token_equals_c2_mainline_rep_version": None})
    except Exception as exc:                                          # noqa: BLE001
        out["why_not_measured"] = f"{type(exc).__name__}: {exc}"
    return out


def section_s3(src: dict, c2_stats: dict) -> list[dict]:
    out: list[dict] = []
    dec_frozen = _dv(src, FROZEN_REP_VERSION, clause="§三-3",
                     verbatim="`representation_version` = `b2-s1-sim-bidir-aloha14d-dt0.034-29.4118hz-"
                              "grip14_to_qpos_pair(+v,-v)-team480x640+pi05x224-v1` 三处逐字核对")
    # ── 第 1 处：B2 数据集 ──
    b2_places = {}
    for pid, pth in (("team_form_dataset_manifest", P_TEAM_MANIFEST),
                     ("demo_manifest", P_DEMO_MANIFEST)):
        obj, ident = load_json(REPO / pth)
        b2_places[pid] = {"path": pth, "identity_sha256_12": ident.get("sha256_12"),
                          "key_paths_with_frozen_value": (None if obj is None else
                                                          find_key_paths_equal(obj, FROZEN_REP_VERSION)),
                          "n_literal_occurrences_in_bytes": count_in_text(REPO / pth, FROZEN_REP_VERSION)}
    gen_txt = text_of(REPO / P_B2_GEN)
    gen_ast_value = module_string_constants(REPO / P_B2_GEN).get("REPRESENTATION_VERSION")
    gen_byte_count = (None if gen_txt is None else gen_txt.count(FROZEN_REP_VERSION))
    frags = _source_literal_fragments(gen_txt, "REPRESENTATION_VERSION")
    if frags:
        frags["joined_equals_frozen"] = bool(frags.get("joined") == FROZEN_REP_VERSION)
    b2_places["generator_constant"] = {
        "path": P_B2_GEN, "identity_sha256_12": src["b2_generator"]["sha256_12"],
        "constant_name": "REPRESENTATION_VERSION",
        "ast_extracted_value": gen_ast_value,
        "ast_value_equals_frozen": (None if gen_ast_value is None
                                    else gen_ast_value == FROZEN_REP_VERSION),
        "n_literal_occurrences_in_bytes": gen_byte_count,
        "source_literal_fragments": frags,
        "byte_grep_false_negative": bool(gen_byte_count == 0 and gen_ast_value == FROZEN_REP_VERSION),
        "why_byte_grep_finds_nothing": (
            "**实测陷阱（登记给所有做文本审计的线）**：生成器把这一串写成**两段相邻字面量的隐式拼接**"
            "（跨行）⇒ 用 `grep -F` 搜整串在 `scripts/b2_s1_generate_dataset.py` 里命中 **0 次**，"
            "而 ast 取出的常量值与冻结串**逐字相同**。谁按字节 grep 判「串还在不在」，"
            "就会得到一个**假阴性**（进而误报漂移）。⇒ 本项的判据取 ast 值，字节命中数只作旁证。")}
    manifest_counts = {k: v.get("n_literal_occurrences_in_bytes")
                       for k, v in b2_places.items() if k != "generator_constant"}
    b2_ok = bool(gen_ast_value == FROZEN_REP_VERSION
                 and all(isinstance(c, int) and c >= 1 for c in manifest_counts.values()))
    out.append(item("S3.1_place1_b2_dataset",
                    "第 1 处 = B2 数据集侧：冻结串是否逐字在场（生成器常量 + 两份 manifest）",
                    measured=b2_places, declared_block=dec_frozen, match=b2_ok,
                    severity=None if b2_ok else "binding",
                    severity_reason=None if b2_ok else "B2 侧的冻结串已被改动（= 换 representation_version，须 D 批）",
                    binding_for_bc=True))
    # ── 第 2 处：C2 的 stats 档 ──
    c2_rv = (c2_stats.get("json") or {}).get("representation_version")
    out.append(item("S3.2_place2_c2_stats",
                    "第 2 处 = C2 的 stats 档：`representation_version` 实测值",
                    measured={"path": P_STATS_BC,
                              "identity_sha256_12": src["c2_stats"]["sha256_12"],
                              "representation_version": c2_rv,
                              "contains_frozen_string_as_substring": (
                                  None if not isinstance(c2_rv, str) else FROZEN_REP_VERSION in c2_rv),
                              "field_namespace": "归一化器档位（case/coverage/floor/coef/…），不是数据集形态串",
                              "what_it_pins_instead": {
                                  "provenance.frames[0].npz": ((c2_stats.get("json") or {})
                                                               .get("provenance", {})
                                                               .get("frames", [{}])[0].get("npz")),
                                  "provenance.frames[0].sha256_12": ((c2_stats.get("json") or {})
                                                                     .get("provenance", {})
                                                                     .get("frames", [{}])[0].get("sha256_12")),
                                  "provenance.frames[0].content_sha256_12": (
                                      (c2_stats.get("json") or {}).get("provenance", {})
                                      .get("frames", [{}])[0].get("content_sha256_12"))}},
                    measurement_status=src["c2_stats"].get("measurement_status", "not_measured"),
                    declared_block=dec_frozen, match=compare(FROZEN_REP_VERSION, c2_rv),
                    severity="registered_difference",
                    severity_reason=("**不同命名空间**（不是数据不符）：C2 的 stats 档用它自己的档位串"
                                     "（`s1-sim-demo-bidir-quantiles-with-scale-floor-F1-…-v2`），"
                                     "它把数据集身份**钉在 `provenance.frames[0]` 的 npz sha + 内容 sha 上**"
                                     "（见 S3.6），而不是靠复用数据集的形态串。"),
                    binding_for_bc=False, adjudication_owner="D（执行单 §三-3 的前提需要改判）"))
    # ── 第 3 处：A2 的 runtime ──
    rt_occ = count_in_text(REPO / P_A2_RUNTIME, FROZEN_REP_VERSION)
    gate_occ = count_in_text(REPO / P_A2_BC_GATE, FROZEN_REP_VERSION)
    rt_txt = text_of(REPO / P_A2_RUNTIME) or ""
    tmpl = [f"harness/vla_runtime.py:{i}: {ln.strip()}"
            for i, ln in enumerate(rt_txt.splitlines(), 1) if "vla_runtime_v1:" in ln][:6]
    prod = _scan_a2_runtime_products()
    c2_rv_known = isinstance(c2_rv, str)
    if prod.get("measurement_status") == "measured" and c2_rv_known:
        prod["any_stats_token_equals_c2_mainline_rep_version"] = bool(
            c2_rv in prod.get("distinct_stats_tokens", []))
    out.append(item("S3.3_place3_a2_runtime",
                    "第 3 处 = A2 的 runtime：冻结串出现次数、版本串模板、已落盘产物的 `stats=` token",
                    measured={"frozen_string_occurrences_in_harness_vla_runtime_py": rt_occ,
                              "frozen_string_occurrences_in_harness_bc_admission_gate_py": gate_occ,
                              "a2_runtime_identity": src["a2_runtime"],
                              "a2_bc_gate_identity": src["a2_bc_gate"],
                              "runtime_version_string_template_lines": tmpl,
                              "a2_bc_gate_module_representation_version":
                                  module_string_constants(REPO / P_A2_BC_GATE
                                                          ).get("MODULE_REPRESENTATION_VERSION"),
                              "observed_products": prod},
                    measurement_status=("measured" if rt_occ is not None and gate_occ is not None
                                        and prod.get("measurement_status") == "measured" else "not_measured"),
                    declared_block=dec_frozen, match=(False if rt_occ == 0 else None),
                    severity="registered_difference",
                    severity_reason=("A2 的 runtime 版本串是**第三个命名空间**（`vla_runtime_v1:dt=…:stats=…`），"
                                     "由 `representation_version()` 在运行时按实参拼装 ⇒ 代码里**不可能**"
                                     "出现数据集形态串的字面值（实测 0 次）。已落盘产物的 `stats=` token "
                                     "目前是 S4b 管线自检用的桩值（见 observed_products），"
                                     "**不是** C2 主线 stats 的版本串。"),
                    binding_for_bc=False, adjudication_owner="A2（第 1 步开跑后其 `stats=` token 才落地）"))
    three_way = bool(b2_ok and c2_rv == FROZEN_REP_VERSION and rt_occ not in (0, None))
    out.append(item("S3.4_three_way_literal_identity",
                    "**执行单 §三-3 的原命题**：三处 `representation_version` 是否逐字相同",
                    measured={"three_way_literal_identity": three_way,
                              "place1_b2_dataset": FROZEN_REP_VERSION if b2_ok else None,
                              "place2_c2_stats": c2_rv,
                              "place3_a2_runtime": ("无字面出现（0 次）；运行时才拼装，形如 "
                                                    "`vla_runtime_v1:…:stats=<stats_version>:…`")},
                    declared_block=dec_frozen, match=three_way, severity="binding",
                    severity_reason=("**实测为 false ⇒ 按执行单字面「不同 ⇒ 列差异，不判绿」，本件不判绿。**"
                                     "差异的**性质**已测清（三处是三个命名空间，见 S3.1/S3.2/S3.3 的 "
                                     "severity_reason），**不是**数据不符；数据层的同源链在 S3.6 实测成立。"
                                     "⇒ 需要 D 改判这条的口径（B2 不自行放宽，也不代 A2 判准入）。"),
                    binding_for_bc=False, adjudication_owner="D"))
    out.append(item("S3.5_a2_bc_run_instance_rep_version",
                    "A2 在**BC 真跑**里落盘的那条 runtime 版本串（第 3 处的运行时实例）",
                    measured=None, measurement_status="not_measured",
                    declared_block=None,
                    why_not_measured=("六步序列第 1 步尚未起跑（裁定 98.1/98.2：C2 欠账已交清、"
                                      "A2 可以起跑，但截至本件 `as_of` 盘上还没有 BC 跑产物）⇒ "
                                      "**测不到就写 not_measured，不用 false/0 顶替**。"),
                    note="这条不阻塞 A2；它只是说明「三处逐字相同」这个命题在第 3 处**永远只能在开跑后测**。"))
    consts = module_string_constants(REPO / P_C2_CONTRACT)
    admissible = consts.get("BC_ADMISSIBLE_PROVENANCES")
    prov = (c2_stats.get("json") or {}).get("stats_provenance")
    frames_prov = ((c2_stats.get("json") or {}).get("provenance", {}).get("frames", [{}])[0])
    link = {
        "c2_stats_pins_npz_sha256_12": frames_prov.get("sha256_12"),
        "b2_recomputed_npz_sha256_12": src["npz"]["sha256_12"],
        "npz_sha_equal": (None if not isinstance(frames_prov.get("sha256_12"), str)
                          else frames_prov.get("sha256_12") == src["npz"].get("sha256_12")),
        "c2_stats_pins_frames_content_sha256_12": frames_prov.get("content_sha256_12"),
        "b2_recomputed_frames_content_sha256_12": src["npz_content_sha"],
        "content_sha_equal": (None if not isinstance(frames_prov.get("content_sha256_12"), str)
                              else frames_prov.get("content_sha256_12") == src["npz_content_sha"]),
        "c2_stats_pins_npz_path": frames_prov.get("npz"),
        "npz_path_equal_to_declared": frames_prov.get("npz") == P_NPZ,
        "stats_provenance": prov,
        "bc_admissible_provenances_ast_extracted_from_harness_norm_contract_py": list(admissible)
        if isinstance(admissible, tuple) else admissible,
        "stats_provenance_is_bc_admissible": (None if not isinstance(admissible, tuple)
                                              else prov in admissible),
        "extraction_method": "ast 只读常量抽取（**未 import 执行** C2/A2 的模块）",
    }
    link_ok = bool(link["npz_sha_equal"] and link["content_sha_equal"]
                   and link["npz_path_equal_to_declared"] and link["stats_provenance_is_bc_admissible"])
    out.append(item("S3.6_substitute_linkage_same_source",
                    "**替代性链接（实测成立的那一条）**：C2 的 stats 档把 npz 的 sha + 内容 sha 钉在 "
                    "`provenance` 里，且 `stats_provenance` 在契约层的 BC 可进白名单内",
                    measured=link,
                    measurement_status=("measured" if src["npz"].get("measurement_status") == "measured"
                                        and c2_stats.get("measurement_status") == "measured"
                                        else "not_measured"),
                    match=link_ok, severity=None if link_ok else "binding",
                    severity_reason=None if link_ok else "同源链（裁定 85.4-3 的 Tp5）在身份层不成立",
                    binding_for_bc=True,
                    note=("这才是「同一份数据」的机器判据：**身份对身份**，不是**字符串对字符串**。"
                          "⇒ 报给 D 的结论：执行单 §三-3 的三处逐字命题不可满足（S3.4），"
                          "但它想守的东西（BC 与 stats 同源）由本项守着，且实测为真。")))
    return out


# ══════════════════════ S4 · C2 的 stats 档 + 成对身份 ══════════════════════
def _declared_in_doc(value, doc_text: str | None, *, clause: str, doc_path: str = P_C2_BROADCAST):
    """声明值取自 C2 的成对广播件；**同时核实该值此刻仍逐字在该件里**（防止我抄了一份已被改掉的声明）。"""
    present = (None if doc_text is None else str(value) in doc_text)
    d = declared(value, source=f"C2 的成对广播件 {clause}（裁定 96.1-④ / 97.5-①）",
                 source_path=doc_path, as_of=C2_BROADCAST_AS_OF)
    d["value_still_verbatim_in_source"] = present
    if present is False:
        d["warning"] = ("声明值已不在该件里 ⇒ 广播件被改过；本项按 `not_measured` 处理，"
                        "不拿旧值冒充现值（`citation_sha_as_of_discipline`）")
    return d


def section_s4(src: dict, c2_stats: dict) -> list[dict]:
    out: list[dict] = []
    doc_txt = text_of(REPO / P_C2_BROADCAST)
    # ── S4.0 广播件自己的身份（A2 的对账起点）──
    out.append(item("S4.0_c2_broadcast_doc_identity",
                    "C2 的成对广播件（A2 唯一的声明来源）此刻的身份",
                    measured=src["c2_broadcast"],
                    declared_block=declared("120 ln `1ffbe342f5bb`",
                                            source="D→B2 执行单 补单四 §一（commit-4 范围）",
                                            source_path=P_D_ORDER, as_of=D_ORDER_AS_OF,
                                            verbatim="`docs/c2_to_a2_bc_stats_handoff_20260930.md`（120 ln `1ffbe342f5bb`）"),
                    match=(None if src["c2_broadcast"].get("sha256_12") is None
                           else src["c2_broadcast"]["sha256_12"] == "1ffbe342f5bb"),
                    severity="registered_difference",
                    severity_reason=("C2 在 D 点名之后按**裁定 98.3-②**给本件追加了行数口径说明"
                                     "（件内自述 as_of 14:29）⇒ 字节变了。这是**授权的文书追加**，"
                                     "不是漂移；但 commit-4 的提交信息与任何引用都必须用**提交时刻**的实测值。"),
                    binding_for_bc=False, adjudication_owner="B2（commit-4 按实测值提交）/ D（清单追平）"))
    # ── S4.1 stats 档身份 ──
    st_ident = c2_stats["identity"]
    dec_stats = _declared_in_doc("b2150e0a3264", doc_txt, clause="§3")
    out.append(item("S4.1_stats_file_identity",
                    "BC 唯一一档归一化 stats 的身份（B2 自己复算）",
                    measured=st_ident, measurement_status=st_ident.get("measurement_status", "not_measured"),
                    declared_block=dec_stats,
                    match=(None if st_ident.get("measurement_status") != "measured"
                           else bool(st_ident["sha256_12"] == "b2150e0a3264" and st_ident["bytes"] == 26416
                                     and st_ident["n_lines_wc"] == 845 and st_ident["n_lines_splitlines"] == 846)),
                    severity=None, binding_for_bc=True,
                    note=("路径**照抄 C2 点名的那一条**（裁定 97.7-①：不许 glob 后挑一份）。"
                          "行数只作旁证，判据是 sha256[:12]（裁定 98.3-①④）。")))
    # ── S4.2 stats_provenance 与 BC 可进性 ──
    j = c2_stats.get("json") or {}
    consts = module_string_constants(REPO / P_C2_CONTRACT)
    admissible = consts.get("BC_ADMISSIBLE_PROVENANCES")
    prov = j.get("stats_provenance")
    bca = j.get("bc_admission") or {}
    out.append(item("S4.2_stats_provenance_and_bc_admissibility",
                    "`stats_provenance`（执行单 §三-4：`formal40_bc_source` 可进 BC、"
                    "`formal40_lerobot_crosscheck` **不可**）",
                    measured={"stats_provenance": prov,
                              "bc_admissible_provenances_from_contract_layer": list(admissible)
                              if isinstance(admissible, tuple) else admissible,
                              "stats_provenance_is_bc_admissible": (None if not isinstance(admissible, tuple)
                                                                    else prov in admissible),
                              "mainline_allowed": j.get("mainline_allowed"),
                              "not_for_mainline_normalizer": j.get("not_for_mainline_normalizer"),
                              "consumer_at_build": j.get("consumer_at_build"),
                              "contract": j.get("contract"), "case": j.get("case"),
                              "stats_source": j.get("stats_source"),
                              "coverage_target": j.get("coverage_target"),
                              "bc_admission_block_in_stats": bca,
                              "extraction_method": "契约层白名单用 ast 只读抽取（未 import 执行 C2 的模块）"},
                    measurement_status=c2_stats.get("measurement_status", "not_measured"),
                    declared_block=_dv(src, "formal40_bc_source", clause="§三-4",
                                       verbatim="`stats_provenance`（`formal40_bc_source` 可进 BC；"
                                                "`formal40_lerobot_crosscheck` **不可**）"),
                    match=compare("formal40_bc_source", prov),
                    severity=None if prov == "formal40_bc_source" else "binding",
                    severity_reason=None if prov == "formal40_bc_source" else "唯一一档 stats 的溯源标签不对",
                    binding_for_bc=True))
    # ── S4.3 臂内件（成对之一）──
    arm = src["arm_status"]
    arm_json = c2_stats.get("arm_json")
    out.append(item("S4.3_arm_mainline_status_identity",
                    "臂内 `mainline_status.json`（**BC 消费口径的正主**，裁定 96.1-④/97.5-①）",
                    measured={**arm, "bc_admission_block_inside": arm_json.get("bc_admission")
                              if isinstance(arm_json, dict) else None},
                    measurement_status=arm.get("measurement_status", "not_measured"),
                    declared_block=_declared_in_doc("e72776306f98", doc_txt, clause="§1-①"),
                    match=(None if arm.get("measurement_status") != "measured"
                           else bool(arm["sha256_12"] == "e72776306f98" and arm["bytes"] == 210240)),
                    severity=None, binding_for_bc=True,
                    note=("臂内件的 `bc_admission` 三个字段实测是 `null`/`not_measured` —— "
                          "**这是顺序所致、不是缺陷**（臂内件在 `gate_verdict.json` 之前产出，"
                          "生产方不自引；裁定 96.1-④ 追认 F 的撤回）⇒ 「闸绿」这个事实只在 S4.4 里。")))
    # ── S4.4 同轮闸判词（成对之二）──
    gv = src["gate_verdict"]
    scanned = gv.get("scanned_top_level") or {}
    out.append(item("S4.4_gate_verdict_paired_identity",
                    "同轮 `gate_verdict.json`（**「闸绿」只存在于这一件**）：身份 + 判词（流式读取，99 MB 不整件载入）",
                    measured=gv, measurement_status=gv.get("measurement_status", "not_measured"),
                    declared_block=_declared_in_doc("fa59b263c5fa", doc_txt, clause="§1-②"),
                    match=(None if gv.get("measurement_status") != "measured" else
                           bool(gv["sha256_12"] == "fa59b263c5fa" and gv["bytes"] == 99391987
                                and scanned.get("verdict") == "PASS"
                                and scanned.get("verdict_class1") == "PASS"
                                and scanned.get("n_red_class1") == 0
                                and scanned.get("n_checks") == 54)),
                    severity=None, binding_for_bc=True,
                    note=("**成对纪律**：S4.3 与 S4.4 必须一起读，缺一 ⇒ A2 的 `LearnerRefused`"
                          "（广播件 §2-4）。B2 在此**只登记实测身份与判词**，不代 A2 做准入判定。")))
    # ── S4.5 顶层便利副本 ──
    top = src["toplevel_status"]
    marker = src["toplevel_marker"]
    out.append(item("S4.5_toplevel_convenience_copy",
                    "顶层便利副本是否已与臂内件逐字节相同（裁定 96.1-④ 的甲案）+ 标记件身份",
                    measured={"toplevel_mainline_status": top,
                              "arm_mainline_status_sha256_12": arm.get("sha256_12"),
                              "byte_identical_to_arm": (None if top.get("sha256_12") is None
                                                        or arm.get("sha256_12") is None
                                                        else top["sha256_12"] == arm["sha256_12"]),
                              "marker_file": marker,
                              "consumption_caliber": ("**各线一律消费臂内件**（广播件 §5-1 / D §D96.9）；"
                                                      "顶层件即使字节相同也不是声明路径")},
                    measurement_status=top.get("measurement_status", "not_measured"),
                    declared_block=_declared_in_doc("e72776306f98", doc_txt, clause="§5-1"),
                    match=(None if top.get("measurement_status") != "measured"
                           else top.get("sha256_12") == arm.get("sha256_12")),
                    severity=None, binding_for_bc=False))
    # ── S4.6 crosscheck 档不可进 BC ──
    x_obj, x_ident = load_json(REPO / P_STATS_XCHECK)
    xprov = (x_obj or {}).get("stats_provenance")
    x_ok = (None if xprov is None or not isinstance(admissible, tuple) else xprov not in admissible)
    out.append(item("S4.6_lerobot_crosscheck_not_bc_admissible",
                    "`…__lerobot_crosscheck.json` 这一档**不可**进 BC（执行单 §三-4 的后半句）",
                    measured={"path": P_STATS_XCHECK, "identity": x_ident,
                              "stats_provenance": xprov,
                              "in_bc_admissible_provenances": (None if xprov is None
                                                               or not isinstance(admissible, tuple)
                                                               else xprov in admissible),
                              "mainline_allowed": (x_obj or {}).get("mainline_allowed"),
                              "not_for_mainline_normalizer": (x_obj or {}).get("not_for_mainline_normalizer")},
                    measurement_status=x_ident.get("measurement_status", "not_measured"),
                    declared_block=_dv(src, "formal40_lerobot_crosscheck 不可进 BC", clause="§三-4"),
                    match=x_ok, severity=None if x_ok else "binding",
                    severity_reason=None if x_ok else "交叉核对档竟然在 BC 白名单里 ⇒ 同源硬闸失效",
                    binding_for_bc=True))
    return out


def _find_key(obj, name: str, _pre: str = "", _hits=None, limit: int = 3):
    """递归找出第一个（最多 limit 个）叫 `name` 的键，返回 [(路径, 值)]。"""
    if _hits is None:
        _hits = []
    if len(_hits) >= limit:
        return _hits
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == name:
                _hits.append((f"{_pre}{k}", v))
            elif isinstance(v, (dict, list)):
                _find_key(v, name, f"{_pre}{k}.", _hits, limit)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            if isinstance(v, (dict, list)):
                _find_key(v, name, f"{_pre}[{i}].", _hits, limit)
    return _hits


def layered_identity_reconciliation(src: dict) -> dict:
    """**裁定 98.10-⑤（Ⅰ 类）：身份对账必须分层。**

    · **冻结件**（闸产物 / 前像 / npz / run 目录 / 已 `delivered` 的机器产物）⇒ 必须逐字节相符，
      不符 = 缺陷、**无豁免**。
    · **活件**（正在被授权写者编辑的实现码 + 多写者共享文书）⇒ 快照内该行按 `as_of` 有效、
      **不得当现值引用**；`as_of` 之后的差异必须**可归因**，三条同时成立才不判缺陷：
      ① `mtime` 晚于快照 `as_of` ∧ ② 写者自己的产物或前像在盘 ∧ ③ 授权条款点名该写入面。

    本件里有两处身份差（S1.7 / S4.0），逐条按这个口径过一遍，**不靠散文自证**。
    """
    rows = []

    # ── 行 1：`demo_manifest.json`（run 目录里的机器产物 ⇒ 冻结件类）──
    demo = stream_identity(REPO / P_DEMO_MANIFEST)
    dm_obj, _ = load_json(REPO / P_DEMO_MANIFEST)
    patch_hits = _find_key(dm_obj, "demo_manifest_patch") if dm_obj is not None else []
    before_imgs = sorted(_rel(q) for q in (REPO / "runs/vla/b2_sim_demo_bidir_20260930/formal"
                                           ).rglob("*demo_manifest*") if q.is_file())[:6]
    writer_tools = [{"path": P_B2_EXPORTER, "exists": (REPO / P_B2_EXPORTER).exists(),
                     "sha256_12": src["b2_exporter"].get("sha256_12")},
                    {"path": "scripts/b2_patch_manifest_addendum.py",
                     "exists": (REPO / "scripts/b2_patch_manifest_addendum.py").exists(),
                     "sha256_12": stream_identity(REPO / "scripts/b2_patch_manifest_addendum.py"
                                                  ).get("sha256_12")}]
    c1 = bool(demo.get("mtime") and demo["mtime"] > "2026-09-30T02:57:21+08:00")
    c2 = bool(patch_hits or before_imgs)
    rows.append({
        "item_id": "S1.7_dataset_own_gates_and_manifest_identity",
        "artifact": P_DEMO_MANIFEST,
        "artifact_class": "frozen_run_dir_machine_product（run 目录里的机器产物）",
        "declared_sha256_12": "0c057e22690f", "declared_as_of": "2026-09-30T02:57:21+08:00",
        "measured_sha256_12": demo.get("sha256_12"), "measured_mtime": demo.get("mtime"),
        "attribution_test": {
            "c1_mtime_later_than_declared_as_of": c1,
            "c2_writer_product_or_before_image_on_disk": c2,
            "c2_evidence": {"demo_manifest_patch_recorded_inside_the_artifact": patch_hits[:1],
                            "sibling_artifacts_naming_demo_manifest": before_imgs,
                            "writer_tools": writer_tools},
            "c3_authorization_clause_names_this_write_surface": True,
            "c3_evidence": ("契约 §17-4（npz 导出必须把读取时点登记回 demo_manifest）+ 裁定 88.5-1"
                            "（补偿控制三字段必须进 demo_manifest）⇒ 两次追加写都在授权写入面内"),
            "all_three": bool(c1 and c2)},
        "verdict": ("attributable_not_a_defect" if (c1 and c2) else "unattributed_defect"),
        "how_to_cite": ("**现值只有一个**：`e319754dd030`（as_of 03:21:03）。`0c057e22690f` 只能"
                        "**带 as_of 02:57:21** 引用（`citation_sha_as_of_discipline`）；"
                        "冻结件的现值一旦被引用就必须是它 —— 这一条不是豁免，是分层。")})

    # ── 行 2：C2 的成对广播件（活件：授权写者正在编辑的文书）──
    bc = src["c2_broadcast"]
    bi_dir = REPO / "runs/vla/c2_norm_contract_20260929/before_images"
    bi = sorted(_rel(q) for q in bi_dir.glob("c2_to_a2_bc_stats_handoff_20260930.md.before_*")
                ) if bi_dir.exists() else []
    for q in bi:
        _note_read(REPO / q)
    c1b = bool(bc.get("mtime") and bc["mtime"] > "2026-09-30T14:05:00+08:00")
    rows.append({
        "item_id": "S4.0_c2_broadcast_doc_identity",
        "artifact": P_C2_BROADCAST,
        "artifact_class": "live_document（授权写者 C2 正在编辑的交接文书）",
        "declared_sha256_12": "1ffbe342f5bb",
        "declared_as_of": "2026-09-30T14:0x+08:00（D 补单四 §一 点名时刻）",
        "measured_sha256_12": bc.get("sha256_12"), "measured_mtime": bc.get("mtime"),
        "attribution_test": {
            "c1_mtime_later_than_declared_as_of": c1b,
            "c2_writer_product_or_before_image_on_disk": bool(bi),
            "c2_evidence": {"before_images_on_disk": bi},
            "c3_authorization_clause_names_this_write_surface": True,
            "c3_evidence": ("裁定 98.3-②③（D 令 C2 把三份文书的行数字段全部点名口径）+ 裁定 98.10"
                            "（C2 的 §C2-3 自报已追认）⇒ C2 编辑本件在授权写入面内"),
            "all_three": bool(c1b and bi)},
        "verdict": ("attributable_not_a_defect" if (c1b and bi) else "unattributed_defect"),
        "how_to_cite": ("**不得当现值引用**：本件是活件，任何引用必须带 `as_of`。"
                        "commit-4 的提交信息按**提交时刻**实测值落 sha（D 补单一 §一-3 的自指纪律同族）。")})

    ok = all(r["verdict"] == "attributable_not_a_defect" for r in rows)
    return {"caliber": "裁定 98.10-⑤（身份对账必须分层；Ⅰ 类）",
            "measurement_status": "measured",
            "n_identity_mismatch_rows": len(rows), "rows": rows,
            "all_mismatches_attributable": ok,
            "frozen_artifacts_checked_byte_identical": {
                "npz_a84a26079550": src["npz"].get("sha256_12") == "a84a26079550",
                "arm_mainline_status_e72776306f98": src["arm_status"].get("sha256_12") == "e72776306f98",
                "gate_verdict_fa59b263c5fa": src["gate_verdict"].get("sha256_12") == "fa59b263c5fa",
                "c2_stats_b2150e0a3264": src["c2_stats"].get("sha256_12") == "b2150e0a3264",
                "note": ("冻结件一律逐字节核对、**无豁免**（裁定 98.10-⑤ 前半句）；"
                         "这四件是本件真正承载 BC 同源与闸绿的冻结件。")},
            "sentinel_caliber_note": ("裁定 98.10-⑤ 的哨兵口径同时收紧：**正向哨兵必须钉不可变件**。"
                                      "本件的正向锚点一律钉冻结件（npz / 臂内件 / gate_verdict / stats 档），"
                                      "**不钉任何活件** ⇒ 不会因他线并发追加而自我打红。")}


# ══════════ 裁定 99.3 的改判层（**只改判据归属，绝不动 `match` / `measured`**）══════════
RULING_99_3_ATTRIBUTION = (
    "**D 的预登记判据命题错**（裁定 99.3-③ = 缺陷类 ⑲ 第 13 件，同型错误计数 22→23）"
    "⇒ **这不是 B2 的差异**；配套新 Ⅰ 类口径 = "
    "`preregistered_criterion_must_be_dry_run_on_the_object`"
    "（写给下位的「逐字相同 / 必须命中 / 三处一致」型判据，下发前必须先在实物上干跑一次；"
    "**没做干跑的判据不得标 `binding`**，只能标 `proposed`）")
RECLASSIFIED_SEVERITY = "reclassified_d_proposition_error"
DEFERRED_CLASS = "deferred_by_construction_pending_step1_bc_run"

RULING_99_3: dict[str, dict] = {
    "S3.4_three_way_literal_identity": {
        "kind": "severity_lift",
        "ruling_ref": "裁定 99.3-①（`S3.4` 的 `binding` 标记**解除**）",
        "prior_severity": "binding",
        "new_severity": RECLASSIFIED_SEVERITY,
        "d_proposition_verbatim": ("D→B2 执行单 §三-3：三处 `representation_version` 逐字相同"
                                   "（不同 ⇒ 列差异，不判绿）"),
        "measured_reality": ("三处是**三个命名空间**，不是同一个串的三份副本：第 1 处 = B2 的数据集形态串；"
                             "第 2 处 = C2 的归一化器档位串；第 3 处 = A2 运行时才拼装、冻结串字面出现 **0** 次 "
                             "⇒ 该命题**按字面必然为假**（裁定 99.3-① 原文）"),
        "correct_proposition_after_ruling": ("数据层同源链 = ① npz `a84a26079550` ∧ ② 内容 sha `c9a72480fcb7` "
                                             "在 C2 stats 的 `provenance.frames[0]` 里逐字出现"
                                             "（= 本件 `S3.6`，已实测成立）∧ ③ A2 真跑时把 stats 版本拼进 "
                                             "`stats=` token（= 本件 `S3.5`，只能开跑后测）"),
        "attribution": RULING_99_3_ATTRIBUTION,
        "match_semantics_after_ruling": ("`match=false` **保留不动**：那条字面命题确实为假。"
                                         "解除的是 `binding`（= 它不再让本件不判绿），不是把 false 改成 true。")},
    "S3.2_place2_c2_stats": {
        "kind": "severity_lift",
        "ruling_ref": "裁定 99.3-①（`S3.2`（C2 用档位串而非形态串）**同理解除**）",
        "prior_severity": "registered_difference",
        "new_severity": RECLASSIFIED_SEVERITY,
        "d_proposition_verbatim": "D→B2 执行单 §三-3（同 S3.4：要求第 2 处也逐字等于数据集形态串）",
        "measured_reality": ("C2 的 stats 档用它自己的归一化器档位串，而把**数据集身份钉在 "
                             "`provenance.frames[0]` 的 npz sha + 内容 sha 上**（= S3.6，实测成立）"),
        "attribution": RULING_99_3_ATTRIBUTION},
    "S1.2_robot_type": {
        "kind": "severity_lift",
        "ruling_ref": "裁定 99.3-②（**以实测串为权威值，执行单的字面值作废**）",
        "prior_severity": "registered_difference",
        "new_severity": RECLASSIFIED_SEVERITY,
        "d_proposition_verbatim": "D→B2 执行单 §三-1：`robot_type=aloha_bimanual`",
        "measured_reality": ("实测 `aloha_bimanual_14d(gym_aloha vx300s dual-arm)`（写在 B2 自己的生成器 "
                             "`scripts/b2_s1_generate_dataset.py:2884`）⇒ **前缀扩展、不是另一个 robot**；"
                             "本机 lerobot 的强制面实测 = 316 个 py / 60 处 `robot_type` 引用 / 只有 "
                             "`datasets/aggregate.py:71` 一处等值比较，且它只做跨数据集聚合时的一致性比较、"
                             "**不是字面白名单** ⇒ 不影响 π₀.₅ 加载（旁证块在本项 `measured` 里）"),
        "authoritative_value_after_ruling": "aloha_bimanual_14d(gym_aloha vx300s dual-arm)",
        "attribution": RULING_99_3_ATTRIBUTION,
        "tautology_warning": ("改判后「权威值 == 实测值」**按构造为真**（权威值就是实测值）⇒ "
                              "它是**口径改判的结果**，不是一条新的独立测量，不得当成新证据引用。")},
    "S3.5_a2_bc_run_instance_rep_version": {
        "kind": "not_measured_class",
        "ruling_ref": "裁定 99.3-①（`S3.5` **保持 `not_measured`** 直到第 1 步真跑）",
        "prior_severity": None,
        "new_class": DEFERRED_CLASS,
        "d_proposition_verbatim": "D→B2 执行单 §三-3（第 3 处的运行时实例）",
        "measured_reality": ("六步序列第 1 步尚未起跑 ⇒ 这一项**只能**在 A2 的 BC 真跑落盘后测；"
                             "它是**按构造延期**，不是「本可测而未测」的真缺口"),
        "attribution": ("不是缺陷、也不是 B2 的缺口；`not_measured` + `null` 是三值纪律要求的正确写法"
                        "（**不许用 false/0 顶替**，执行单 §三-5 / 补单五 ③）")},
}

# ── 裁定 99.3 **没有点名**的登记差异：B2 不自行解除，只标归因并报 D ──────────────────
B2_SIDE_ATTRIBUTION: dict[str, str] = {
    "S1.7_dataset_own_gates_and_manifest_identity": (
        "**活件 `as_of` 差**（裁定 98.10-⑤）：声明值带 `as_of 02:57:21`（合规），盘上现值更晚 ⇒ "
        "归 D 的参数表 evidence 追平，**不是数据差异**"),
    "S3.3_place3_a2_runtime": (
        "**与 S3.2 同型（第三个命名空间），但裁定 99.3 只点名了 S3.4 / S3.2 / S1.2 ⇒ "
        "B2 不自行解除**，按原样保留为登记差异并报 D 确认（若 D 认可同型，本件的登记差异只剩 2 条）"),
    "S4.0_c2_broadcast_doc_identity": (
        "**append-only 活件的身份差**，已按裁定 98.10-⑤ 的三条件归因 = `attributable_not_a_defect`"
        "（见 `layered_identity_reconciliation`）；commit-4 已按实测值提交"),
}
RECLASS_GAP_FOR_D = {
    "item_id": "S3.3_place3_a2_runtime",
    "what": ("裁定 99.3 解除了 S3.4（binding）与 S3.2（登记差异），但**未点名 S3.3**；"
             "S3.3 的差异根因与 S3.2 完全同型（第 3 处是运行时拼装的第三个命名空间，冻结串字面出现 0 次）"),
    "b2_action": "**不自行解除**（不代裁、不自行放宽词表）⇒ 保留 `registered_difference`，在此点名请 D 一句话确认",
    "if_d_confirms_same_shape": "登记差异从 3 条降到 2 条（S1.7 / S4.0），退出码不变（仍 = 4）",
}


def _reclass_row_valid(row) -> bool:
    """改判行必须自带授权条款与归因，缺一即视为**自行放宽**（不许静默解除 binding）。"""
    if not isinstance(row, dict):
        return False
    for key in ("kind", "ruling_ref", "attribution"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            return False
    if "prior_severity" not in row:
        return False
    if row["kind"] == "severity_lift":
        return bool(isinstance(row.get("new_severity"), str) and row["new_severity"].strip())
    if row["kind"] == "not_measured_class":
        return bool(isinstance(row.get("new_class"), str) and row["new_class"].strip())
    return False


def _exit_code(n_binding: int, blocking_not_measured: list, deferred_not_measured: list) -> int:
    """v2 退出码（裁定 99.3）。优先级 **5 > 3 > 4 > 0**：binding 压倒一切，真缺口压倒延期。"""
    if n_binding:
        return 5
    if blocking_not_measured:
        return 3
    if deferred_not_measured:
        return 4
    return 0


def _apply_ruling_99_3(items: list) -> dict:
    """把改判**追加**进被点名的项（`pre_ruling_99_3` 快照 + 新 severity/类别），不覆写实测值。"""
    applied, refused = [], []
    untouched = True
    for it in items:
        row = RULING_99_3.get(it["item_id"])
        if row is None:
            continue
        if not _reclass_row_valid(row):
            refused.append({"item_id": it["item_id"],
                            "why": "改判行缺 `kind` / `ruling_ref` / `attribution` ⇒ 拒绝执行（不自行放宽）"})
            continue
        match_before = it.get("match", None)
        measured_before = json.dumps(it.get("measured"), ensure_ascii=False, sort_keys=True)
        it["pre_ruling_99_3"] = {"severity": it.get("severity"),
                                 "severity_reason": it.get("severity_reason"),
                                 "match": match_before,
                                 "binding_for_bc": it.get("binding_for_bc"),
                                 "adjudication_owner": it.get("adjudication_owner")}
        if row["kind"] == "severity_lift":
            it["severity"] = row["new_severity"]
            it["severity_reason"] = ("**裁定 99.3 改判**：" + row["ruling_ref"] + "。原判据 = "
                                     + row["d_proposition_verbatim"] + "；实测现实 = "
                                     + row["measured_reality"] + "。归因 = " + row["attribution"]
                                     + ("。**`match` / `measured` 一字未动**（改判不改实测值）。")
                                     + row.get("match_semantics_after_ruling", ""))
            it["adjudication_owner"] = "D（已裁：裁定 99.3）"
        else:
            it["not_measured_class"] = row["new_class"]
            it["not_measured_class_reason"] = row["measured_reality"]
        it["reclassified_by_ruling_99_3"] = row
        if (it.get("match", None) != match_before
                or json.dumps(it.get("measured"), ensure_ascii=False, sort_keys=True) != measured_before):
            untouched = False
        applied.append(it["item_id"])
    return {"caliber": ("**追加一节、不覆写**（补单五 ④）：每一项的改判都以 `pre_ruling_99_3` 快照保留原判，"
                        "v1 实物 `8599c58cbedc` 的原字节留在盘上不动，改判版另落新路径"),
            "ruling_source": ["work/decisions/decisions_20260929.md §99.3（裁定 99）",
                              "rl_harness_supervision/d_handoff_to_b2_20260930.md 补单五 ③④"],
            "new_class1_criterion": "preregistered_criterion_must_be_dry_run_on_the_object",
            "applied_item_ids": applied,
            "refused_rows": refused,
            "all_match_and_measured_untouched": bool(untouched),
            "attribution_rule": ("改判项一律归因到 **D 的命题错**（裁定 99.3-③），"
                                 "**不写进 B2 的差异账**；未被裁定点名的项一律不碰"),
            "reclassification_gap_reported_to_d": RECLASS_GAP_FOR_D}


def _prior_state_from_v1() -> dict:
    """从 **v1 实物**里读出改判前的 `summary` 与 `differences_register`（**不许手抄**）。

    读不到 / 身份与钉住的 `8599c58cbedc` 不符 ⇒ `null` + `not_measured`，并由 `build()` 让守卫跳闸
    （退出码退回 3、`ok=false`）：一份说不清自己取代了什么的改判件，不许报绿。"""
    out = {"source": "v1 实物（改判前那一版）", "v1_path": V1_INVENTORY_REL,
           "pinned_sha256_12": V1_INVENTORY_SHA256_12,
           "before_image_path": V1_INVENTORY_BEFORE_IMAGE_REL,
           "no_hand_transcription": ("下面两个块由 `json.load` 从 v1 实物读出后逐字嵌入；"
                                     "**没有任何数字是人手抄的**（手抄正是本项目已多次自纠的同型错误）")}
    ident = stream_identity(REPO / V1_INVENTORY_REL)
    out["v1_identity"] = ident
    out["pinned_sha_matches_disk"] = (None if ident.get("sha256_12") is None
                                      else bool(ident.get("sha256_12") == V1_INVENTORY_SHA256_12))
    bi = stream_identity(REPO / V1_INVENTORY_BEFORE_IMAGE_REL)
    out["before_image_identity"] = bi
    out["before_image_sha_matches_pin"] = (None if bi.get("sha256_12") is None
                                           else bool(bi.get("sha256_12") == V1_INVENTORY_SHA256_12))
    obj, _ = load_json(REPO / V1_INVENTORY_REL)
    s = obj.get("summary") if isinstance(obj, dict) else None
    r = obj.get("differences_register") if isinstance(obj, dict) else None
    if out["pinned_sha_matches_disk"] is not True or not isinstance(s, dict) or not isinstance(r, list):
        out["summary_pre_ruling_99_3"] = None
        out["differences_register_pre_ruling_99_3"] = None
        out["measurement_status"] = "not_measured"
        out["why_not_measured"] = ("v1 实物读不到、或身份与钉住的 `8599c58cbedc` 不符 ⇒ "
                                   "**不用手抄值顶替**（三值纪律）；此时改判守卫跳闸："
                                   "`ok=false` 且退出码退回 3")
        out["guard_tripped"] = True
        return out
    out["summary_pre_ruling_99_3"] = s
    out["differences_register_pre_ruling_99_3"] = r
    out["measurement_status"] = "measured"
    out["guard_tripped"] = False
    return out


# ══════════════════════ 自检牙（**两向**：keep + flip）══════════════════════
def _selftest() -> dict:
    """验的是**本脚本自己的三值纪律**，不是数据。红线 27.1：牙必须两向都装。"""
    teeth = []
    real = pathlib.Path(__file__).resolve()
    ghost = real.parent / "b2_bc_input_inventory_DOES_NOT_EXIST.json"

    def add(tid, direction, expect, got, why):
        teeth.append({"tooth_id": tid, "direction": direction, "expected_declared_first": expect,
                      "observed": got, "pass": bool(expect == got), "why_it_matters": why})

    r = stream_identity(real)
    add("T1_keep_real_file_is_measured", "keep", True,
        bool(r.get("measurement_status") == "measured" and re.fullmatch(r"[0-9a-f]{12}", str(r.get("sha256_12")))),
        "正向腿：真文件必须 measured 且给出 12 位 hex 身份")
    g = stream_identity(ghost)
    add("T2_flip_missing_file_is_not_measured_not_false", "flip", ("not_measured", None),
        (g.get("measurement_status"), g.get("sha256_12")),
        "负向腿：读不到必须 not_measured + null，**不得**退化成 false/0/空串（执行单 §三-5）")
    add("T3_flip_mismatch_is_false_not_true", "flip", False, compare("a84a26079550", "000000000000"),
        "负向腿：声明≠实测必须 match=False，不得被任何默认值吞成 True")
    add("T4_keep_match_is_true", "keep", True, compare("a84a26079550", "a84a26079550"),
        "正向腿：声明==实测必须 match=True")
    add("T5_flip_unknown_never_fakes_green", "flip", None,
        compare("a84a26079550", None, measurement_status="not_measured"),
        "负向腿：`None == None` 不得冒充绿 ⇒ 三值里第三值必须是 None")
    cons = _episodes_consistent({"lerobot_info_total_episodes": 40, "lerobot_info_total_frames": None,
                                 "lerobot_meta_episodes_parquet_rows": 40,
                                 "lerobot_data_parquet_rows_sum": 11035,
                                 "team_form_dataset_manifest_n_episodes": 40,
                                 "team_form_episode_dirs_on_disk": 40,
                                 "sidecar_episode_json_count": 40,
                                 "team_form_n_per_direction": {"right_to_left": 20, "left_to_right": 20}})
    add("T6_flip_missing_count_never_passes", "flip", (False, False),
        (bool(cons["match"]), bool(cons["all_present"])),
        "负向腿：任何一个计数取不到 ⇒ 一致性判定必须 False（不许「其它 7 项都对就算对」）")
    # ── v2 新增（裁定 99.3）：改判层自己的牙，仍然**两向都装**（红线 27.1）──
    add("T7_keep_exit_code_4_when_only_deferred", "keep", 4,
        _exit_code(0, [], ["S3.5_a2_bc_run_instance_rep_version"]),
        "正向腿：无 binding、无真缺口、只有「按构造延期」项 ⇒ 退出码必须是 **4**（可判但未完结），不是 0")
    add("T8_flip_blocking_not_measured_must_stay_3", "flip", 3,
        _exit_code(0, ["S1.0_lerobot_info_identity"], ["S3.5_a2_bc_run_instance_rep_version"]),
        "负向腿：「按构造延期」这个类别**不得吞掉真缺口** ⇒ 本可测而未测必须仍退回 3")
    add("T9_flip_binding_overrides_deferred", "flip", 5,
        _exit_code(1, [], ["S3.5_a2_bc_run_instance_rep_version"]),
        "负向腿：binding 压倒一切（优先级 5 > 3 > 4 > 0）⇒ 改判不得把真 binding 差异洗成绿")
    fake = [{"item_id": "S3.4_three_way_literal_identity", "match": False, "severity": "binding",
             "measured": {"three_way_literal_identity": False}, "measurement_status": "measured"}]
    rep = _apply_ruling_99_3(fake)
    add("T10_keep_reclass_never_rewrites_match", "keep", (False, "binding", True),
        (fake[0]["match"], fake[0]["pre_ruling_99_3"]["severity"],
         rep["all_match_and_measured_untouched"]),
        "正向腿：改判**只动 severity 与归因**；`match=false` 与原 severity 以快照留存（不覆写实测值）")
    add("T11_flip_reclass_row_without_attribution_is_refused", "flip", False,
        _reclass_row_valid({"kind": "severity_lift", "ruling_ref": "裁定 99.3-①",
                            "prior_severity": "binding", "new_severity": RECLASSIFIED_SEVERITY}),
        "负向腿：改判行缺 `attribution` ⇒ 必须被拒（不许静默解除 binding = 不自行放宽词表）")
    add("T12_keep_reclass_row_with_ruling_and_attribution_is_accepted", "keep", True,
        _reclass_row_valid(RULING_99_3["S3.4_three_way_literal_identity"]),
        "正向腿：带授权条款 + 归因的改判行才准执行")
    real_prior = _prior_state_from_v1()
    add("T13_keep_prior_state_is_read_from_v1_not_hand_typed", "keep",
        ("measured", 3, False, ["S3.4_three_way_literal_identity"]),
        (real_prior.get("measurement_status"),
         (real_prior.get("summary_pre_ruling_99_3") or {}).get("exit_code"),
         (real_prior.get("summary_pre_ruling_99_3") or {}).get("ok"),
         (real_prior.get("summary_pre_ruling_99_3") or {}).get("binding_mismatch_item_ids")),
        "正向腿：改判前的读数必须**从 v1 实物读出来**（v1 = rc 3 / ok false / binding = S3.4）⇒ 手抄即失效")
    saved = globals()["V1_INVENTORY_REL"]
    try:
        globals()["V1_INVENTORY_REL"] = RUN_DIR_REL + "/DOES_NOT_EXIST_v1.json"
        ghost_prior = _prior_state_from_v1()
    finally:
        globals()["V1_INVENTORY_REL"] = saved
    add("T14_flip_prior_state_unreadable_trips_guard_not_fake_green", "flip",
        ("not_measured", None, True),
        (ghost_prior.get("measurement_status"), ghost_prior.get("summary_pre_ruling_99_3"),
         ghost_prior.get("guard_tripped")),
        "负向腿：v1 读不到 ⇒ `null` + `not_measured` + 守卫跳闸（`ok=false` / 退出码退回 3），**不得**手抄报绿")
    v1st = stream_identity(REPO / V1_SELFTEST_REL)
    add("T15_keep_v1_selftest_identity_pin", "keep", V1_SELFTEST_SHA256_12, v1st.get("sha256_12"),
        "正向腿：v1 自检件的实测身份必须与钉住值相符（本轮自纠的那一处身份引用错）")
    recst = stream_identity(REPO / V1_SELFTEST_RECONSTRUCTED_REL)
    add("T16_keep_cited_sha_reproducible_only_via_reconstruction", "keep",
        V1_SELFTEST_CITED_SHA256_12, recst.get("sha256_12"),
        "正向腿：文书钉的 `19ea563b0b2a` 只能由**重构件**复原（穷举 `as_of` 的机器证明见自纠件）")
    add("T17_flip_cited_sha_is_not_the_bytes_on_disk", "flip", False,
        (V1_SELFTEST_CITED_SHA256_12 == v1st.get("sha256_12")),
        "负向腿：被引用的 sha **不等于**盘上实物 sha ⇒ 缺陷是真的、机器可见；"
        "而旁证（2040 B / 76 ln(`wc -l`)）两跑完全相同 ⇒ **只核旁证抓不到这类错**")
    gst = stream_identity(REPO / (RUN_DIR_REL + "/SELFTEST_DOES_NOT_EXIST.json"))
    add("T18_flip_missing_selftest_never_fakes_the_pin", "flip", ("not_measured", None),
        (gst.get("measurement_status"), gst.get("sha256_12")),
        "负向腿：读不到自检件 ⇒ `not_measured` + `null`，**不得**退化成钉住值蒙过 T15")
    ok = all(t["pass"] for t in teeth)
    both = {"flip_proven": any(t["direction"] == "flip" and t["pass"] for t in teeth),
            "keep_proven": any(t["direction"] == "keep" and t["pass"] for t in teeth)}
    return {"artifact": "b2_bc_input_inventory_selftest", "task_id": TASK_ID, "as_of": now_iso(),
            "revision": "v2_ruling99_3",
            "supersedes": {
                "v1_selftest": V1_SELFTEST_REL,
                "v1_sha256_12_measured_now": v1st.get("sha256_12"),
                "v1_left_byte_identical_on_disk": (None if v1st.get("sha256_12") is None
                                                   else bool(v1st.get("sha256_12") == V1_SELFTEST_SHA256_12)),
                "v1_n_teeth": 6,
                "v1_before_image": (RUN_DIR_REL + "/before_images/"
                                    "SELFTEST_three_valued_teeth.json.v1_as_of_152107_177f1e9a4713"),
                "self_correction_note": SELF_CORRECTION_REL,
                "why_a_new_path": ("裁定 99.3 / 补单五 ④「**追加一节，不覆写**」：v1 自检件被 D 的裁定 99.3-① "
                                   "与 §B2-22 的身份表引用 ⇒ v2 另落新路径，v1 原字节不动")},
            "n_teeth": len(teeth), "n_pass": sum(1 for t in teeth if t["pass"]),
            "teeth": teeth, "both_directions_proven": bool(both["flip_proven"] and both["keep_proven"]),
            "directions": both, "ok": bool(ok and both["flip_proven"] and both["keep_proven"]),
            "no_policy_metrics": "本件不含任何 policy 指标（裁定 46）"}


# ══════════════════════ 汇总 / 落盘 ══════════════════════
def _src_of(path_rel: str) -> dict:
    ident = stream_identity(REPO / path_rel)
    ident["as_of"] = ident.get("mtime") or now_iso()
    ident["as_of_caliber"] = "文件 mtime（= 身份测量时刻的可核验代理）"
    return ident


def build(src: dict) -> tuple[list[dict], dict, dict, dict, dict]:
    items: list[dict] = []
    c2_stats_obj, c2_stats_ident = load_json(REPO / P_STATS_BC)
    arm_obj, _arm_ident = load_json(REPO / P_ARM_STATUS)
    npz_probe = _npz_probe(REPO / P_NPZ)
    c2_stats = {"json": c2_stats_obj, "identity": c2_stats_ident, "arm_json": arm_obj,
                "measurement_status": c2_stats_ident.get("measurement_status", "not_measured"),
                "sha256_12": c2_stats_ident.get("sha256_12")}
    src["npz"] = _src_of(P_NPZ)
    src["npz_manifest"] = _src_of(P_NPZ_MANIFEST)
    src["c2_stats"] = c2_stats_ident
    src["npz_content_sha"] = npz_probe.get("frames_content_sha256_12")
    items += section_s1(src)
    items += section_s2(src)
    items += section_s3(src, c2_stats)
    items += section_s4(src, c2_stats)

    reclass = _apply_ruling_99_3(items)
    prior = _prior_state_from_v1()

    n_nm = [i["item_id"] for i in items if i["measurement_status"] != "measured"]
    deferred = [i["item_id"] for i in items
                if i["measurement_status"] != "measured"
                and i.get("not_measured_class") == DEFERRED_CLASS]
    blocking_nm = [x for x in n_nm if x not in deferred]
    reclassified_ids = [i["item_id"] for i in items if i.get("reclassified_by_ruling_99_3")]
    bind = [i["item_id"] for i in items if i.get("match") is False and i.get("severity") == "binding"]
    regd = [i["item_id"] for i in items
            if i.get("match") is False and i.get("severity") not in ("binding", RECLASSIFIED_SEVERITY)]
    ok = (not bind) and (not blocking_nm)
    rc = _exit_code(len(bind), blocking_nm, deferred)
    guard_tripped = bool(prior.get("guard_tripped")) or prior.get("measurement_status") != "measured"
    if guard_tripped:
        ok = False
        rc = 3
    lay = layered_identity_reconciliation(src)
    summary = {
        "n_items": len(items),
        "identity_mismatches_all_attributable_under_ruling_98_10_5": lay["all_mismatches_attributable"],
        "n_measured": sum(1 for i in items if i["measurement_status"] == "measured"),
        "n_not_measured": len(n_nm), "not_measured_item_ids": n_nm,
        "n_not_measured_deferred_by_construction": len(deferred),
        "not_measured_deferred_item_ids": deferred,
        "n_not_measured_blocking": len(blocking_nm),
        "not_measured_blocking_item_ids": blocking_nm,
        "n_match_true": sum(1 for i in items if i.get("match") is True),
        "n_match_false": sum(1 for i in items if i.get("match") is False),
        "n_match_null": sum(1 for i in items if "match" in i and i.get("match") is None),
        "binding_mismatch_item_ids": bind,
        "registered_difference_item_ids": regd,
        "reclassified_item_ids_under_ruling_99_3": reclassified_ids,
        "ok": ok,
        "scope_of_ok": ("`ok` 的作用域 = **当前可测面**（本件 as_of 时点可测的 "
                        f"{len(items) - len(n_nm)}/{len(items)} 项）。裁定 99.3 解除了 S3.4 的 `binding` "
                        "与 S3.2 / S1.2 的登记差异 ⇒ 无 binding 差异、无「本可测而未测」项。"),
        "ok_true_does_not_mean_all_items_measured": (
            "**`ok=true` 不等于「26 项全部 measured」**：`S3.5_a2_bc_run_instance_rep_version` 仍是 "
            "`not_measured`（按构造延期，只能在 A2 的 BC 真跑落盘后测，裁定 99.3-①）⇒ "
            "退出码是 **4**（可判但未完结），**不是 0**。读成「全核过」= 裁定 96.2 型的读法错。"),
        "why_not_ok": ([f"reclassification_guard_tripped: {prior.get('why_not_measured')}"]
                       if guard_tripped else
                       ([f"not_measured_blocking: {x}" for x in blocking_nm]
                        + [f"binding_mismatch: {x}" for x in bind])
                       or ["当前可测面无 binding 差异、无「本可测而未测」项；"
                           f"按构造延期 {len(deferred)} 项（{', '.join(deferred)}）"]),
        "exit_code": rc,
        "exit_code_policy": ("**v2（裁定 99.3 之后）**：0 = 26 项全 measured 且无 binding 差异；"
                             "4 = 无 binding、无「本可测而未测」项，但有 ≥1 项按构造延期的 not_measured"
                             "（当前可测面已判定完结）；3 = 存在「本可测而未测」的 not_measured（真缺口）"
                             "或改判守卫跳闸；5 = 存在 binding 差异；2 = 用法/环境错。"
                             "**优先级 5 > 3 > 4 > 0**。"),
        "exit_code_policy_pre_ruling_99_3": ((prior.get("summary_pre_ruling_99_3") or {})
                                             .get("exit_code_policy")),
        "reclassification_guard_tripped": guard_tripped,
        "reclassification_guard_rule": ("改判件必须能证明它取代了什么：v1 实物读不到或身份不符 ⇒ "
                                        "`ok=false` + 退出码退回 3（牙 T12 双向守这条）"),
        "ok_false_does_not_mean_bc_forbidden": (
            "**本件 `ok=false` 不等于「BC 被禁」**（裁定 96.2 的读法禁令同型；缺陷类 #20 的形状）。"
            "BC 被禁的判据只有三条：`verdict_class1=RED` / `admissible_for_bc=false` / `Tp5` 同源不成立"
            "（裁定 97.5）—— 这三条在本件里分别由 S4.4 / S4.2 / S3.6 实测，**当前三条都不成立为禁**。"),
        "bc_admission_decision_owner": "A2（裁定 93.4）；B2 只做只读汇总，不代判",
        "no_policy_metrics": "本件不含任何 policy 指标或能力表述（裁定 46）；所有 PASS 只指闸判词。",
    }
    return items, summary, lay, reclass, prior


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T-B2-19 · BC 消费侧输入清单件（纯只读）")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--selftest", action="store_true",
                    help="只跑三值纪律的两向自检牙（不产清单件）")
    ap.add_argument("--selftest-out", default=str(SELFTEST_DEFAULT))
    a = ap.parse_args(argv)

    if a.selftest:
        res = _selftest()
        p = pathlib.Path(a.selftest_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"ok": res["ok"], "n_teeth": res["n_teeth"], "n_pass": res["n_pass"],
                          "both_directions_proven": res["both_directions_proven"],
                          "out": _rel(p)}, ensure_ascii=False))
        return 0 if res["ok"] else 3

    src = {k: _src_of(v) for k, v in {
        "d_order": P_D_ORDER, "decisions": P_DECISIONS, "params": P_PARAMS,
        "c2_broadcast": P_C2_BROADCAST, "a2_runtime": P_A2_RUNTIME, "a2_bc_gate": P_A2_BC_GATE,
        "c2_contract": P_C2_CONTRACT, "b2_generator": P_B2_GEN, "b2_exporter": P_B2_EXPORTER,
        "arm_status": P_ARM_STATUS, "toplevel_status": P_C2_TOPLEVEL_STATUS,
        "toplevel_marker": P_C2_TOPLEVEL_MARKER}.items()}
    src["gate_verdict"] = stream_identity(REPO / P_GATE_VERDICT,
                                          scan_keys=("verdict", "verdict_class1", "n_checks",
                                                     "n_red", "n_red_class1", "n_red_class2",
                                                     "n_red_class3"))
    try:
        items, summary, lay, reclass, prior = build(src)
    except Exception as exc:                                          # noqa: BLE001
        print(f"INTERNAL_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2

    self_ident = stream_identity(pathlib.Path(__file__).resolve())
    doc = {
        "artifact": ARTIFACT, "task_id": TASK_ID,
        "generated_at": now_iso(), "as_of": now_iso(),
        "as_of_caliber": "本次测量完成的时刻（每一项另有其来源件的 mtime 作 as_of）",
        "producer": {"script": _rel(pathlib.Path(__file__).resolve()),
                     "sha256_12": self_ident.get("sha256_12"), "bytes": self_ident.get("bytes"),
                     "n_lines_wc": self_ident.get("n_lines_wc"),
                     "n_lines_splitlines": self_ident.get("n_lines_splitlines"),
                     "python": sys.version.split()[0], "venv": sys.executable},
        "n_lines_caliber": N_LINES_CALIBER,
        "authority": ["D→B2 执行单 §三（T-B2-19）：" + P_D_ORDER,
                      "**裁定 99.3**（`S3.4` 的 `binding` 解除 / `S3.2`、`S1.2` 同理解除 / "
                      "`S3.5` 保持 `not_measured`）+ 补单五 ③④（**追加一节，不覆写**；"
                      "`exit_code` 随改判从 3 变成可判的状态；归因写成 D 的命题错、不写成 B2 的差异）",
                      "裁定 99.3-③ 新立的 Ⅰ 类口径 "
                      "`preregistered_criterion_must_be_dry_run_on_the_object`",
                      "裁定 99.1-①（**不再为文书轮次追加 commit**；下一批合并到里程碑提交）",
                      "裁定 90.4-4（npz = 权威读路径 `--s1-frames`）",
                      "裁定 85.4-3（同源硬闸：BC 只认 `formal40_bc_source`）",
                      "裁定 96.1-④ / 97.5-①（成对广播：臂内件 + 同轮 gate_verdict）",
                      "裁定 97.7-①（不 glob 后挑一份）",
                      "裁定 98.3-②/98.5-②（裸 `n_lines` 禁用；sha256[:12] 是唯一约束性判据）",
                      "裁定 98.10-⑤（**身份对账必须分层**：冻结件逐字节相符无豁免 / 活件按 as_of 且差异须三条件可归因）",
                      "裁定 93.4（BC 准入判定归 A2）", "裁定 46（能力声明禁令）"],
        "boundary": ("**只读汇总**：不改 A2 的训练代码、不代 A2 判 BC 能不能跑；"
                     "对别人的代码只用 ast/文本只读抽取，**不 import 执行**他线模块。"),
        "read_only_attestation": {
            "reads_n_paths": len(READS),
            "reads": sorted(READS),
            "writes": [_rel(pathlib.Path(a.out).resolve())],
            "did_not_rerun_any_gate_or_collector": True,
            "note": ("**没有**重跑 C2 的闸、B2 的采集器或 A2 的自检；也**没有**触碰 "
                     "`b2_replay_teeth_verdict.py`（它会覆写 formal-40 run 目录里的历史件）。")},
        "declared_sources_identities": {k: v for k, v in src.items()
                                        if isinstance(v, dict) and "sha256_12" in v},
        "items": items,
        "layered_identity_reconciliation": lay,
        "ruling_99_3_reclassification": reclass,
        "supersedes": {
            "v1_artifact": V1_INVENTORY_REL,
            "v1_sha256_12": V1_INVENTORY_SHA256_12,
            "v1_left_byte_identical_on_disk": prior.get("pinned_sha_matches_disk"),
            "v1_before_image": V1_INVENTORY_BEFORE_IMAGE_REL,
            "v1_before_image_sha_matches_pin": prior.get("before_image_sha_matches_pin"),
            "why_a_new_path": ("裁定 99.3 / 补单五 ④「**追加一节，不覆写**」+ v1 已被 D 的裁定 99.3-① 引用 ⇒ "
                               "改判版另落新路径，v1 原字节不动（D 的引文继续可复现）"),
            "not_a_git_commit": ("本轮**不追加 commit**（裁定 99.1-①）：改判件与文书都留在工作区 / NFS，"
                                 "下一批合并到里程碑提交"),
        },
        "prior_state_provenance": prior,
        "differences_register": [
            {"item_id": i["item_id"], "severity": i.get("severity"),
             "pre_ruling_99_3_severity": (i.get("pre_ruling_99_3") or {}).get("severity"),
             "attribution": (RULING_99_3[i["item_id"]]["attribution"] if i["item_id"] in RULING_99_3
                             else B2_SIDE_ATTRIBUTION.get(i["item_id"],
                                                          "**未归类** ⇒ 报 D，不自行放宽")),
             "is_b2_difference": i["item_id"] not in RULING_99_3,
             "reason": i.get("severity_reason"), "adjudication_owner": i.get("adjudication_owner")}
            for i in items if i.get("match") is False],
        "differences_register_pre_ruling_99_3": prior.get("differences_register_pre_ruling_99_3"),
        "summary": summary,
        "summary_pre_ruling_99_3": prior.get("summary_pre_ruling_99_3"),
    }
    out_p = pathlib.Path(a.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ident = stream_identity(out_p)
    print(json.dumps({"ok": summary["ok"], "exit_code": summary["exit_code"],
                      "n_items": summary["n_items"], "n_not_measured": summary["n_not_measured"],
                      "not_measured_blocking": summary["not_measured_blocking_item_ids"],
                      "not_measured_deferred": summary["not_measured_deferred_item_ids"],
                      "binding_mismatches": summary["binding_mismatch_item_ids"],
                      "identity_mismatches_all_attributable": summary[
                          "identity_mismatches_all_attributable_under_ruling_98_10_5"],
                      "registered_differences": summary["registered_difference_item_ids"],
                      "reclassified_under_ruling_99_3": summary[
                          "reclassified_item_ids_under_ruling_99_3"],
                      "reclassification_guard_tripped": summary["reclassification_guard_tripped"],
                      "v1_left_byte_identical": prior.get("pinned_sha_matches_disk"),
                      "out": _rel(out_p), "out_sha256_12": ident.get("sha256_12"),
                      "out_bytes": ident.get("bytes"),
                      "out_n_lines_wc": ident.get("n_lines_wc"),
                      "out_n_lines_splitlines": ident.get("n_lines_splitlines"),
                      "wall_as_of": doc["as_of"]}, ensure_ascii=False, indent=1))
    return summary["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
