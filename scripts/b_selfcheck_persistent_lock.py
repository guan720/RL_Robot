#!/usr/bin/env python3
"""B 线：`requirements.persistent.lock.txt` 的**身份登记 + 牙**（D→B 执行单 §3 / 验收 §8.3）。

## 身份（登记在 DR-013；本脚本的缺省期望值就是这张表）

| 项 | 值 |
|---|---|
| 文件 | `requirements.persistent.lock.txt`，**82 pin**，`sha256_12=69d61657f531` |
| 生成器 | `scripts/d_build_persistent_lock.py`（依赖闭包 BFS；pin 漂移 ⇒ exit 3、闭包 GAP ⇒ exit 4） |
| 生成报告 | `runs/infra/d_persistent_env_20260929/persistent_lock_report.json` |
| **不是**什么 | **不是门禁产物**、不参与 `GATE_BUILD`、**不被** `c_env_manifest.py::_parse_lock` 读取 |
| 与 28 pin lock 的关系 | 头部 `base_lock=requirements.lock.txt sha256_12=d1ea71b7b4e5`；前 28 pin 逐行沿用，其余是闭包新增 |
| 已知冲突 | `robosuite 1.5.2 -> mink==0.0.5`（实际装成 `1.2.0`，按裁定 32.2「lock 是事实源」记录不改） |
| 排除项 | `jax` / `jaxlib`（仓里执行的代码 0 处 import；conda 的 jax/tf 是 09-24 ImportError 的污染源） |
| 等价性补钉 | `h5py 3.14.0`（`robosuite/utils/camera_utils.py:12` 模块级 import，但不在 robosuite 的 install_requires 里） |
| owner | **生成器 = D**，**验收闸 = B（本脚本）**。0929 14:19 曾发生写权碰撞（B 14:16 建的 36 pin 版被 D 的生成器覆盖），处置 = B 不回抢（裁定 21 单一来源），改为登记 + 验收。 |

## 为什么不挂在 `b_selfcheck_reproducibility.py` 的 L0 系列里

D §3 建议「挂在 L0 系列，与 L0-f/L0-g 并列」。**B 没这么做，理由是 D 自己的另一条硬要求**：
§8.1 要求五套自检的通过数与 12:2x 基线**逐项相同**（可复现性 **12/12**）。
往 L0 加三条牙会把它变成 15/15 ⇒ 同一份执行单里，§3 的落地方式会推翻 §8.1 的判据。
所以做成**独立脚本**：L0 仍是 12/12（迁移不变性证明 `runs/infra/b_env_migration_invariance_20260929/`
可被 D 原样复核），persistent lock 有自己的闸和自己的 `--selftest`。
另一条支持理由：D §3 明确 persistent lock **不是门禁产物**，把它的检查塞进门禁前的 L0 系列，
反而会让「不是门禁产物」这句话在代码层面不成立。

## 牙（D §3 要求的三条，外加两条身份断言）

  K1 头部 `base_lock ... sha256_12=` == 仓里 `requirements.lock.txt` 的**实测** sha256 前 12 位
  K2 persistent 的 pin **⊇** 28 pin lock，且**交集逐格相同**（按 PEP 503 归一化名比对）
  K3 `torch` / `torchvision` 的 pin **必须带 `+cu124`**
  K4 persistent lock 的身份未变（sha256_12 与 pin 数）—— 登记册必须能注意到事实被换过
  K5 28 pin 门禁 lock 的身份未变（sha256_12 == d1ea71b7b4e5、28 pin 一行未动）
  K6 「**不是**门禁产物」由观测支撑（门禁本体 0 命中 + `_parse_lock(` 调用行 0 命中 + 头部自述在位）
     —— 裁定 37.4-3：判据产物里的散文必须由观测生成。**散文引用不算违规**
     （实测 `c_env_manifest.py:1117` 有一处 authority 出处说明，按「出现即违规」判就是假红）

**可红条件（裁定 27.1）**
  1. K1：改头部 sha 任意一位 / 换掉 `requirements.lock.txt` ⇒ RED；
  2. K2：从 persistent 里删掉任一 base pin ⇒ RED（⊇ 被破坏）；
     改任一**共有** pin 的版本 ⇒ RED（交集不逐格相同）；
  3. K3：去掉 `torch` 或 `torchvision` 的 `+cu124` ⇒ RED（重生成时被解析成 CPU 版就是这条）；
  4. K4/K5：对应文件的 sha256_12 或 pin 数变了 ⇒ RED（要改就用 `--expect-*` 显式重新登记，
     并在 DR-013 追加一条；**不许**就地放宽缺省值）；
  5. 任一文件缺失 / 一行 pin 都解析不出来 ⇒ RED（不当作「没有差异」）。

**不红条件（反向，防恒红 / 防假红）**
  · 发行名大小写不同（`ImageIO` vs `imageio`）、行序不同 ⇒ 仍 GREEN
    （PEP 503 归一化 + 无序比对；这正是 0929 B 在 `b_env_provenance_guard.py` G3 上
     撞过的假红：freeze 用发行名原样、lock 用归一化名 ⇒ 误报 8 个缺失）；
  · 只改**闭包新增**（非共有）pin 的版本 ⇒ K2 仍 GREEN（⊇ 只约束交集），但 K4 会 RED
    （身份 sha 变了）—— 这是分工，不是漏判；
  · `pip` / `setuptools` 不在 `pip freeze` 默认输出里，不参与 K2 比对（`FREEZE_EXEMPT`）。

用法：
    python3 scripts/b_selfcheck_persistent_lock.py
    python3 scripts/b_selfcheck_persistent_lock.py --selftest
    python3 scripts/b_selfcheck_persistent_lock.py --json-out runs/infra/b_persistent_lock/report.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSISTENT = ROOT / "requirements.persistent.lock.txt"
BASE = ROOT / "requirements.lock.txt"

# ---- 登记的身份（DR-013）；要改必须显式传 --expect-*，并在 DR-013 追加一条 ----
EXPECT_PERSISTENT_SHA12 = "69d61657f531"
EXPECT_PERSISTENT_PINS = 82
EXPECT_BASE_SHA12 = "d1ea71b7b4e5"
EXPECT_BASE_PINS = 28
# `pip freeze` 默认不列自身 ⇒ 这两条不参与「交集逐格相同」比对（否则是恒假的缺失报告）
FREEZE_EXEMPT = {"pip", "setuptools"}
CU_SUFFIX = "+cu124"
PLOCK_NAME = "requirements.persistent.lock.txt"
# K6 的观测对象：门禁本体（冻结）与 C 的 manifest 生成器。**只读**，不改它们。
GATE_SCRIPT = ROOT / "scripts/b_gate_controlled_success.py"
C_MANIFEST = ROOT / "scripts/c_env_manifest.py"
# 门禁本体里必须**一处不提** persistent lock（GATE_BUILD = sha12(门禁自身) ⇒ 提了就等于进了构建输入）
GATE_MUST_NOT_MENTION = PLOCK_NAME
# persistent lock 头部必须自带「不是门禁产物」的自述（自述缺失 ⇒ 登记与文件不同源）
HEADER_SELF_DESCRIBE = "不是**门禁产物"
_BASE_SHA_RE = re.compile(r"^#\s*base_lock=(?P<path>\S+)\s+sha256_12=(?P<sha>[0-9a-fA-F]{12})")


def norm_name(name: str) -> str:
    """PEP 503 归一化：小写 + 把 `-`/`_`/`.` 折叠成单个 `-`。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def parse_pins(path: Path) -> dict:
    """解析 lock → {归一化名: {"raw": 原始名, "version": 版本, "line": 行号}}。

    跳过 `#` 注释、`-` 选项行（`--find-links` 这类）与空行 ——
    与 C 的 `c_env_manifest.py::_parse_lock` 同口径。
    """
    out = {}
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" not in line:
            continue
        name, _, version = line.partition("==")
        name, version = name.strip(), version.strip()
        if not name:
            continue
        out[norm_name(name)] = {"raw": name, "version": version, "line": i}
    return out


def parse_base_lock_header(path: Path) -> dict:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _BASE_SHA_RE.match(raw.strip())
        if m:
            return {"found": True, "path": m.group("path"), "sha256_12": m.group("sha"),
                    "line": raw.strip()}
    return {"found": False, "path": None, "sha256_12": None, "line": None}


def observe_not_a_gate_product(persistent: Path, gate_script: Path, c_manifest: Path) -> dict:
    """把「persistent lock **不是**门禁产物」从**旁挂散文**变成**观测**。

    裁定 37.4-3 的一般规则：判据产物里的每一句散文，要么由观测生成，要么显式标注为历史说明。
    D §3 的「不是什么」那一栏原本是登记散文，这里改成三条可核观测：

      a) **门禁本体**（冻结，`GATE_BUILD = sha12(自身)`）源码里 `requirements.persistent.lock.txt`
         命中 **0** 处 ⇒ 它既不被门禁读取，也不进构建指纹的输入；
      b) **C 的 manifest 生成器**里，凡带 `_parse_lock(` 的行**都不得**出现该文件名
         ⇒ 「不被 `_parse_lock` 读取」是**语义**断言，不是天真 grep。
         为什么必须这样写：实测 `scripts/c_env_manifest.py:1117` 有一处
         `"authority": ("requirements.persistent.lock.txt 头部 `excluded=jax,jaxlib` + "`
         —— 那是**散文引用**（jax 排除项的出处），不是解析。按「出现即违规」判就会造一个假红
         （本仓今天第 8 起同型就在隔壁文件，B 不再造第 9 起）；
      c) persistent lock **自己的头部**带「不是门禁产物」的自述 ⇒ 登记与文件同源。
    """
    out = {"gate_script": str(gate_script), "c_manifest": str(c_manifest),
           "gate_mentions": [], "c_parse_lock_lines": [], "c_prose_mentions": [],
           "header_self_describe": False, "violations": []}
    if gate_script.exists():
        for i, ln in enumerate(gate_script.read_text(encoding="utf-8",
                                                      errors="replace").splitlines(), 1):
            if PLOCK_NAME in ln:
                out["gate_mentions"].append("%d: %s" % (i, ln.strip()[:120]))
    else:
        out["violations"].append("门禁本体不存在：%s" % gate_script)
    if c_manifest.exists():
        for i, ln in enumerate(c_manifest.read_text(encoding="utf-8",
                                                    errors="replace").splitlines(), 1):
            if PLOCK_NAME not in ln:
                continue
            if "_parse_lock(" in ln:
                out["c_parse_lock_lines"].append("%d: %s" % (i, ln.strip()[:160]))
            else:
                out["c_prose_mentions"].append("%d: %s" % (i, ln.strip()[:160]))
    else:
        out["violations"].append("C 的 manifest 生成器不存在：%s" % c_manifest)
    if persistent.exists():
        head = "\n".join(persistent.read_text(encoding="utf-8",
                                               errors="replace").splitlines()[:20])
        out["header_self_describe"] = HEADER_SELF_DESCRIBE in head
    if out["gate_mentions"]:
        out["violations"].append("门禁本体里出现 %d 处 %s（会进 GATE_BUILD 的输入）：%s"
                                 % (len(out["gate_mentions"]), PLOCK_NAME, out["gate_mentions"][:3]))
    if out["c_parse_lock_lines"]:
        out["violations"].append("C 的 `_parse_lock(` 调用行里出现 %s：%s"
                                 % (PLOCK_NAME, out["c_parse_lock_lines"][:3]))
    if not out["header_self_describe"]:
        out["violations"].append("persistent lock 头部前 20 行里没有「%s」的自述" % HEADER_SELF_DESCRIBE)
    out["ok"] = not out["violations"]
    return out


class Checker:
    def __init__(self):
        self.rows = []

    def ck(self, cid, ok, observed, required, note="", severity="FAIL"):
        self.rows.append({"id": cid, "ok": bool(ok), "severity": severity,
                          "observed": str(observed), "required": str(required), "note": str(note)})
        print("  [%s] %-4s %s" % ("PASS" if ok else severity, cid, note or required))
        if not ok and observed:
            print("         实测：%s" % str(observed)[:600])
        return bool(ok)

    @property
    def n_pass(self):
        return sum(1 for r in self.rows if r["ok"])

    @property
    def n_fail(self):
        return sum(1 for r in self.rows if not r["ok"] and r["severity"] == "FAIL")

    @property
    def n_warn(self):
        return sum(1 for r in self.rows if not r["ok"] and r["severity"] == "WARN")


def evaluate(persistent: Path, base: Path,
             expect_p_sha=EXPECT_PERSISTENT_SHA12, expect_p_pins=EXPECT_PERSISTENT_PINS,
             expect_b_sha=EXPECT_BASE_SHA12, expect_b_pins=EXPECT_BASE_PINS,
             gate_script: Path = GATE_SCRIPT, c_manifest: Path = C_MANIFEST) -> dict:
    ck = Checker()
    for p, what in ((persistent, "persistent lock"), (base, "28 pin 门禁 lock")):
        if not p.exists():
            ck.ck("K0", False, "缺失：%s" % p, "两份 lock 都必须存在",
                  "%s 不存在 ⇒ 不做任何「没有差异」的推定" % what)
    if ck.n_fail:
        return _finish(ck, persistent, base, {})

    p_sha, b_sha = sha12(persistent), sha12(base)
    pp, bp = parse_pins(persistent), parse_pins(base)
    ck.ck("K0", bool(pp) and bool(bp), "persistent=%d pin / base=%d pin" % (len(pp), len(bp)),
          "两份 lock 都至少解析出 1 条 pin（解析出 0 条 = 格式变了，不是「没有 pin」）")

    # ---- K1 头部 base_lock sha256_12 == 实测 ----
    hdr = parse_base_lock_header(persistent)
    ck.ck("K1", hdr["found"] and hdr["sha256_12"] == b_sha,
          "头部=%s 实测(requirements.lock.txt)=%s" % (hdr["sha256_12"], b_sha),
          "persistent 头部登记的 base_lock sha256_12 == 仓里 requirements.lock.txt 的实测值",
          "头部行：%s" % (hdr["line"] or "（没找到 `# base_lock=... sha256_12=` 这一行）"))

    # ---- K2 ⊇ 且交集逐格相同（PEP 503 归一化 + 无序）----
    comparable = {k for k in bp if k not in FREEZE_EXEMPT}
    missing = sorted(k for k in comparable if k not in pp)
    diff = sorted(k for k in comparable if k in pp and pp[k]["version"] != bp[k]["version"])
    ck.ck("K2", not missing and not diff,
          "缺 %d 个 %s；版本不同 %d 个 %s" % (
              len(missing), missing[:8], len(diff),
              [(k, bp[k]["version"], pp[k]["version"]) for k in diff][:8]),
          "persistent 的 pin ⊇ base 的 %d 个可比 pin，且交集**逐格相同**"
          "（归一化名比对；pip/setuptools 不参与）" % len(comparable))

    # ---- K3 torch / torchvision 必须带 +cu124 ----
    bad_cu = []
    for pkg in ("torch", "torchvision"):
        e = pp.get(pkg)
        if e is None:
            bad_cu.append("%s 不在 persistent lock 里" % pkg)
        elif CU_SUFFIX not in e["version"]:
            bad_cu.append("%s==%s（缺 %s）" % (pkg, e["version"], CU_SUFFIX))
    ck.ck("K3", not bad_cu,
          "; ".join(bad_cu) or "torch==%s torchvision==%s"
          % (pp["torch"]["version"], pp["torchvision"]["version"]),
          "torch / torchvision 的 pin 必须带 %s（重生成时被解析成 CPU 版就是这条在拦）" % CU_SUFFIX)

    # ---- K4 persistent 身份未变 ----
    ck.ck("K4", p_sha == expect_p_sha and len(pp) == expect_p_pins,
          "sha256_12=%s（登记 %s）pin 数=%d（登记 %d）" % (p_sha, expect_p_sha, len(pp), expect_p_pins),
          "persistent lock 的身份与 DR-013 登记一致",
          "变了就用 --expect-persistent-sha12/--expect-persistent-pins 显式重新登记，"
          "并在 work/decisions/decisions_20260928_B.md 的 DR-013 追加一条；不许就地放宽缺省值")

    # ---- K5 28 pin 门禁 lock 身份未变 ----
    ck.ck("K5", b_sha == expect_b_sha and len(bp) == expect_b_pins,
          "sha256_12=%s（登记 %s）pin 数=%d（登记 %d）" % (b_sha, expect_b_sha, len(bp), expect_b_pins),
          "28 pin 门禁 lock 一字节未动（D→B 执行单 §8.2）",
          "它是 0928 那批产物的溯源件；覆写它 = 把可核事实换成新事实（裁定 32.4）")

    # ---- K6「不是门禁产物」由**观测**生成（裁定 37.4-3），不是旁挂散文 ----
    ngp = observe_not_a_gate_product(persistent, gate_script, c_manifest)
    ck.ck("K6", ngp["ok"],
          "门禁本体命中 %d 处；C 的 `_parse_lock(` 行命中 %d 处；C 的散文引用 %d 处；头部自述=%s%s"
          % (len(ngp["gate_mentions"]), len(ngp["c_parse_lock_lines"]),
             len(ngp["c_prose_mentions"]), ngp["header_self_describe"],
             ("；违例：%s" % ngp["violations"][:2]) if ngp["violations"] else ""),
          "「不是门禁产物 / 不参与 GATE_BUILD / 不被 _parse_lock 读取」三条**由观测支撑**",
          "散文引用（如 C 的 authority 出处说明）**不算**违规；只有门禁本体命中、"
          "或 `_parse_lock(` 调用行命中、或头部自述缺失才红")

    extra = {"persistent_sha256_12": p_sha, "base_sha256_12": b_sha,
             "not_a_gate_product_observed": ngp,
             "persistent_pins": len(pp), "base_pins": len(bp),
             "closure_only_pins": sorted(k for k in pp if k not in bp),
             "n_closure_only": len([k for k in pp if k not in bp]),
             "base_lock_header": hdr,
             "not_comparable_freeze_excludes": sorted(FREEZE_EXEMPT)}
    return _finish(ck, persistent, base, extra)


def _finish(ck, persistent, base, extra) -> dict:
    ok = ck.n_fail == 0
    return {"spec": "requirements.persistent.lock.txt 身份登记 + 牙（D→B 执行单 §3 / 验收 §8.3）",
            "ok": ok, "persistent_lock": str(persistent), "base_lock": str(base),
            "summary": {"pass": ck.n_pass, "fail": ck.n_fail, "warn": ck.n_warn,
                        "total": len(ck.rows)},
            "checks": ck.rows, "identity": extra,
            # 由 K6 的观测生成（裁定 37.4-3）：不再是一句写死的登记散文
            "not_a_gate_product": (
                "观测成立：门禁本体 %s 里 `%s` 命中 %d 处、C 的 `_parse_lock(` 调用行命中 %d 处"
                "（另有 %d 处**散文引用**，不算违规）、文件头部自述「%s」= %s"
                % (Path((extra.get("not_a_gate_product_observed") or {}).get("gate_script", "?")).name,
                   PLOCK_NAME,
                   len((extra.get("not_a_gate_product_observed") or {}).get("gate_mentions") or []),
                   len((extra.get("not_a_gate_product_observed") or {}).get("c_parse_lock_lines") or []),
                   len((extra.get("not_a_gate_product_observed") or {}).get("c_prose_mentions") or []),
                   HEADER_SELF_DESCRIBE,
                   (extra.get("not_a_gate_product_observed") or {}).get("header_self_describe"))),
            "owner": "生成器 = D（scripts/d_build_persistent_lock.py）；验收闸 = B（本脚本）",
            "red_conditions": [
                "K1 头部 base_lock sha256_12 与实测不符 / 头部那行没了",
                "K2 persistent 缺任一 base pin，或共有 pin 版本不同",
                "K3 torch / torchvision 缺 +cu124",
                "K4/K5 sha256_12 或 pin 数与登记值不符（要改就显式传 --expect-* 并在 DR-013 追加）",
                "K0 文件缺失，或解析出 0 条 pin（不当作「没有差异」）",
                "K6 门禁本体里出现该文件名 / C 的 `_parse_lock(` 调用行里出现该文件名 / 头部自述缺失",
            ]}


# --------------------------------------------------------------------------
# --selftest：D §8.3 要求「三条牙各红一次」。全部在临时副本上做，**绝不碰真文件**。
# S6/S7 是**反向变异**（必须仍绿），防恒红也防 PEP 503 假红。
# --------------------------------------------------------------------------
def _fixture(src_p: Path, src_b: Path) -> tuple[Path, Path]:
    d = Path(tempfile.mkdtemp(prefix="b_plock_selftest_"))
    p, b = d / src_p.name, d / src_b.name
    shutil.copy2(src_p, p)
    shutil.copy2(src_b, b)
    return p, b


def _rewrite(path: Path, fn):
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(fn(lines)) + "\n", encoding="utf-8")


def selftest() -> int:
    """D §8.3 要求「三条牙各红一次」。全部在临时副本上做，**绝不碰真文件**。

    判定口径不是「有没有红」，而是「**指定条目**是否红/绿」：
      · S1–S5 必须让**对应那条**牙红（不是碰巧被 K4 带红就算过）；
      · S6/S7 是**反向变异**（大小写、行序）：K1/K2/K3 必须**仍绿**，
        同时用 `--expect-persistent-sha12` 的等价手段把 K4 **重新登记** ——
        因为字节确实变了，K4 红是它的职责，不是语义牙失效。
        （0929 B 在 `b_env_provenance_guard.py` G3 上撞过的假红正是这一类：
         发行名大小写不同被读成「缺失 8 个包」。）
      · S8 篡改 28 pin 门禁 lock ⇒ K1 与 K5 必须都红。
    """
    if not PERSISTENT.exists() or not BASE.exists():
        print("找不到 lock，无法 selftest：%s / %s" % (PERSISTENT, BASE))
        return 2

    def m_header_sha(p, b):
        _rewrite(p, lambda ls: [re.sub(r"(sha256_12=)[0-9a-f]{12}",
                                       lambda mm: mm.group(1) + ("0" * 12), ln)
                                for ln in ls])

    def m_drop_base_pin(p, b):
        victim = sorted(parse_pins(b))[0]
        raw = parse_pins(p)[victim]["raw"]
        _rewrite(p, lambda ls: [ln for ln in ls if not ln.startswith(raw + "==")])

    def m_change_shared_pin(p, b):
        victim = sorted(parse_pins(b))[0]
        raw = parse_pins(p)[victim]["raw"]
        _rewrite(p, lambda ls: [("%s==0.0.1" % raw if ln.startswith(raw + "==") else ln)
                                for ln in ls])

    def m_strip_cu(pkg):
        def f(p, b):
            _rewrite(p, lambda ls: [(ln.replace("+cu124", "") if ln.startswith(pkg + "==") else ln)
                                    for ln in ls])
        return f

    def m_case_only(p, b):
        # 反向：只改发行名大小写（imageio -> ImageIO），PEP 503 归一化后语义牙必须仍绿
        _rewrite(p, lambda ls: [("ImageIO==2.37.3" if ln.lower().startswith("imageio==") else ln)
                                for ln in ls])

    def m_reorder(p, b):
        # 反向：pin 行整体倒序（注释头保留），无序比对必须仍绿
        def f(ls):
            head = [ln for ln in ls if not ln.strip() or ln.startswith("#") or ln.startswith("-")]
            pins = [ln for ln in ls if ln.strip() and not ln.startswith("#")
                    and not ln.startswith("-")]
            return head + pins[::-1]
        _rewrite(p, f)

    def m_tamper_base(p, b):
        _rewrite(b, lambda ls: [(ln + "  " if ln.startswith("ale-py==") else ln) for ln in ls])

    # reregister=True ⇒ 把 K4/K5 的期望值改成变异后文件的实测值（只考察语义牙）
    def kw_gate_mentions(d):
        # K6-a 红：门禁本体里出现该文件名（= 它进了 GATE_BUILD 的输入）
        f = d / "fake_gate.py"
        f.write_text("PLOCK = \"requirements.persistent.lock.txt\"\n", encoding="utf-8")
        return {"gate_script": f}

    def kw_manifest_prose_only(d):
        # K6 反向：C 的文件里只有**散文引用**（不在 `_parse_lock(` 行上）⇒ **不得**判红
        f = d / "fake_manifest_prose.py"
        f.write_text("def _parse_lock(path):\n    pass\n"
                     "AUTHORITY = (\"requirements.persistent.lock.txt 头部 excluded=jax,jaxlib\")\n",
                     encoding="utf-8")
        return {"c_manifest": f}

    def kw_manifest_parses(d):
        # K6-b 红：`_parse_lock(` 的调用行里出现该文件名（= 真的被解析）
        f = d / "fake_manifest_parse.py"
        f.write_text("pins = _parse_lock(ROOT / \"requirements.persistent.lock.txt\")\n",
                     encoding="utf-8")
        return {"c_manifest": f}

    muts = [
        ("S0_unmutated", None, set(), {"K0", "K1", "K2", "K3", "K4", "K5", "K6"}, False,
         "正对照：原样七条全绿"),
        ("S1_base_sha_one_digit", m_header_sha, {"K1"}, None, False,
         "K1：头部 base_lock sha 改一位 ⇒ K1 必须红"),
        ("S2_drop_a_base_pin", m_drop_base_pin, {"K2"}, None, False,
         "K2：从 persistent 删掉一个 base pin ⇒ K2 必须红（⊇ 被破坏）"),
        ("S3_change_shared_pin", m_change_shared_pin, {"K2"}, None, False,
         "K2：改共有 pin 的版本 ⇒ K2 必须红（交集不逐格相同）"),
        ("S4_strip_torch_cu124", m_strip_cu("torch"), {"K3"}, None, False,
         "K3：torch 去掉 +cu124 ⇒ K3 必须红"),
        ("S5_strip_torchvision_cu124", m_strip_cu("torchvision"), {"K3"}, None, False,
         "K3：torchvision 去掉 +cu124 ⇒ K3 必须红"),
        ("S6_case_only_REVERSE", m_case_only, set(), {"K1", "K2", "K3"}, True,
         "**反向**：只改发行名大小写（imageio→ImageIO）⇒ 语义牙必须仍绿（PEP 503 归一化）"),
        ("S7_reorder_REVERSE", m_reorder, set(), {"K1", "K2", "K3"}, True,
         "**反向**：pin 行倒序 ⇒ 语义牙必须仍绿（无序比对）"),
        ("S8_tamper_base_lock", m_tamper_base, {"K1", "K5"}, None, False,
         "篡改 28 pin 门禁 lock ⇒ K1（头部对不上）与 K5（身份变了）都必须红"),
        # 注意条目形状：(mid, fn, must_red, must_green, reregister, why, kw_fn)
        # why 必须在第 6 位、extra_kw 在第 7 位（见下方 entry[:6] / entry[6] 解包）
        ("S9_gate_mentions_plock", None, {"K6"}, None, True,
         "K6：门禁本体里出现该文件名（= 进了 GATE_BUILD 输入）⇒ 必须红",
         kw_gate_mentions),
        ("S10_prose_only_REVERSE", None, set(), {"K1", "K2", "K3", "K6"}, True,
         "**反向**：C 的文件里只有**散文引用**（authority 出处说明）⇒ K6 必须仍绿"
         "（按「出现即违规」判就是假红，实测 c_env_manifest.py 的 AUTHORITY 行就是这种）",
         kw_manifest_prose_only),
        ("S11_manifest_parses_plock", None, {"K6"}, None, True,
         "K6：`_parse_lock(` 调用行里出现该文件名（= 真被解析）⇒ 必须红",
         kw_manifest_parses),
    ]
    print("=" * 112)
    print("%-32s %-22s %-22s %s" % ("变异", "必须红", "必须绿", "结论"))
    print("=" * 112)
    allok, results = True, []
    for entry in muts:
        # 形状牙：条目只允许 6 元 (…, why) 或 7 元 (…, why, kw_fn)；
        # 第 7 位必须是可调用对象。写错顺序会让 extra_kw 拿到字符串（历史 bug）。
        if len(entry) not in (6, 7):
            raise AssertionError("selftest 条目形状非法（长度 %d）：%r" % (len(entry), entry[0]))
        if len(entry) == 7 and not callable(entry[6]):
            raise AssertionError("selftest 条目第 7 位必须是 kw_fn 可调用对象，实为 %s：%r"
                                 % (type(entry[6]).__name__, entry[0]))
        mid, fn, must_red, must_green, reregister, why = entry[:6]
        extra_kw = entry[6] if len(entry) > 6 else None
        if not isinstance(why, str) or not why:
            raise AssertionError("selftest 条目第 6 位必须是 why 字符串：%r" % (entry[0],))
        p, b = _fixture(PERSISTENT, BASE)
        if fn is not None:
            fn(p, b)
        kw = {}
        if reregister:                      # 反向变异：把身份期望值重新登记到变异后的实测值
            kw = {"expect_p_sha": sha12(p), "expect_p_pins": len(parse_pins(p)),
                  "expect_b_sha": sha12(b), "expect_b_pins": len(parse_pins(b))}
        if extra_kw is not None:
            kw.update(extra_kw(p.parent))
        rep = _quiet(p, b, **kw)
        red = {r["id"] for r in rep["checks"] if not r["ok"]}
        green = {r["id"] for r in rep["checks"] if r["ok"]}
        bad_red = sorted(must_red - red)
        bad_green = sorted((must_green or set()) - green)
        status = "pass" if not bad_red and not bad_green else "FAIL"
        if status == "FAIL":
            allok = False
        results.append({"id": mid, "must_red": sorted(must_red), "must_green": sorted(must_green or []),
                        "reregistered_identity": reregister, "actual_red": sorted(red),
                        "status": status, "why": why,
                        "missed_red": bad_red, "unexpectedly_red": bad_green,
                        "fixture": str(p)})
        print("%-32s %-22s %-22s %-6s %s"
              % (mid, sorted(must_red) or "-", sorted(must_green or []) or "-", status, why))
        print("%-32s   实际红=%s%s" % ("", sorted(red) or "无",
                                       "" if status == "pass"
                                       else "  ← 漏红 %s / 不该红却红 %s" % (bad_red, bad_green)))
    print("=" * 112)
    n = sum(1 for r in results if r["status"] == "pass")
    print("selftest：%d/%d 符合预期 → 本闸%s有牙（teeth.non_vacuous=%s）"
          % (n, len(results), "" if allok else "**不**", allok and n == len(results)))
    return 0 if allok else 1


def _quiet(p, b, **kw):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return evaluate(p, b, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persistent-lock", default=str(PERSISTENT))
    ap.add_argument("--base-lock", default=str(BASE))
    ap.add_argument("--expect-persistent-sha12", default=EXPECT_PERSISTENT_SHA12)
    ap.add_argument("--expect-persistent-pins", type=int, default=EXPECT_PERSISTENT_PINS)
    ap.add_argument("--expect-base-sha12", default=EXPECT_BASE_SHA12)
    ap.add_argument("--expect-base-pins", type=int, default=EXPECT_BASE_PINS)
    ap.add_argument("--gate-script", default=str(GATE_SCRIPT),
                    help="K6 观测对象：门禁本体（只读）")
    ap.add_argument("--c-manifest", default=str(C_MANIFEST),
                    help="K6 观测对象：C 的 manifest 生成器（只读）")
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_persistent_lock/report.json"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rep = evaluate(Path(a.persistent_lock), Path(a.base_lock),
                   a.expect_persistent_sha12, a.expect_persistent_pins,
                   a.expect_base_sha12, a.expect_base_pins,
                   Path(a.gate_script), Path(a.c_manifest))
    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("=" * 108)
    print("persistent lock 登记：%d PASS / %d FAIL / %d WARN → %s"
          % (rep["summary"]["pass"], rep["summary"]["fail"], rep["summary"]["warn"],
             "成立" if rep["ok"] else "**不成立**"))
    idn = rep.get("identity") or {}
    if idn:
        print("身份：persistent sha256_12=%s / %d pin（其中闭包新增 %d）；base sha256_12=%s / %d pin"
              % (idn.get("persistent_sha256_12"), idn.get("persistent_pins"),
                 idn.get("n_closure_only"), idn.get("base_sha256_12"), idn.get("base_pins")))
    print("产物：%s" % outp)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
