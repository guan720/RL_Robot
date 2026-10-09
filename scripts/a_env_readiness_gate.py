#!/usr/bin/env python3
"""A 线：**新复现主张的就绪闸**（裁定 29.4 / 增补七 §19-A④ 的代码承载）—— 全程只读。

为什么需要它
------------
裁定 29.4 给 A 的是一条**行为约束**：「`lerobot` 未装好前不要声称任何新训练 / 评测复现」。
本仓已经立过纪律（裁定 29 附带登记）：**任何裁定落盘前必须回答「哪一行代码执行它」**；
答不出的只能落 `PENDING_IMPL`。一条只写在备忘里的行为约束，等于靠人记住 ——
而 0929 检修刚好证明了「人记住」不可靠（四线对话历史连同 venv 一起被清掉）。
本脚本把这条约束变成**机器判**：CLOSED 时 A 不得声称任何新复现，且脚本会打印
「此刻允许声称什么 / 不允许声称什么」。

权威 pin 来源
------------
`docs/lerobot_env_reinstall_pin_20260929.md`（B 线，DR-012）§2 的表，摘自
`scripts/install_lerobot_act_env.sh` 与两份 lock。**A 不自己定 pin**，只把它变成断言。

判据为什么不能只验「importable」（B §5.2 的实测反例）
----------------------------------------------------
D 在裁定 29.4 里提的离线候选源 `/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot`，
B 实测其 HEAD 比 tag `v0.4.4` **落后 488 个 commit**，且该 HEAD 的 `pyproject.toml` 写
`version = "0.1.0"` ⇒ **从它装出来的包 `import lerobot` 照样成功**，而 48 臂权威表依赖的
官方 ACT 入口（`lerobot.scripts.lerobot_train`、`normalize_processor.py` 的行为）是 **0.4.4** 的。
⇒ 「只验 importable」是**恒真判据**。本闸的 E2 判 `lerobot.__version__ == "0.4.4"`，
E3 判官方入口真能 import + `--help` 真能跑，E5 判**安装来源**（wheel 还是源装、源装必须回显 commit）。

模式
----
  默认          真探两个 venv 的解释器 + 读 C 的 manifest，判 E1–E7。CLOSED ⇒ exit 1。
  --selftest    变异自检（fixture 全在内存，**不写任何文件、不起任何子进程**），
                证明判据有牙：装成 0.1.0 必须被 E2 抓住、只验 importable 的形态必须红。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---- 权威 pin（照抄 B 的 DR-012 §2 表；A 不自己定 pin）--------------------
PIN = {
    "lerobot": "0.4.4",
    "torch": "2.6.0",
    "torchvision": "0.21.0",
    "train_numpy": "2.2.6",
    "train_gymnasium": "1.3.0",
    "eval_numpy": "2.4.6",
    "eval_gymnasium": "1.2.3",
    "eval_mujoco": "3.9.0",
    "eval_robosuite": "1.5.2",
    "base_python": "/opt/conda/bin/python3.11",
    "train_venv": "/root/venvs/lerobot_act",
    "eval_venv": "/root/venvs/lerobot_eval",
    "v044_commit": "8fff0fde7c79f23a93d845d1a50e985de01f8b8a",
    "source_doc": "docs/lerobot_env_reinstall_pin_20260929.md（B / DR-012）§2",
}
C_MANIFEST = "runs/infra/c_env_manifest_20260929.json"
LOCK_TRAIN = "runs/infra/lerobot_act_env_20260928/requirements.lock.txt"
LOCK_EVAL = "runs/infra/lerobot_act_env_20260928/requirements.eval.lock.txt"
# B §4 的实测反例：这个 checkout 装出来会自报 0.1.0（比 v0.4.4 落后 488 commit）
KNOWN_BAD_SOURCE_VERSION = "0.1.0"


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, cid, name, ok, observed, required, *, blocking=True, note=""):
        self.rows.append({"id": cid, "name": name, "pass": bool(ok), "blocking": blocking,
                          "observed": observed, "required": required, "note": note})
        return bool(ok)

    @property
    def open(self) -> bool:
        return all(r["pass"] for r in self.rows if r["blocking"])

    def n_fail_blocking(self) -> int:
        return sum(1 for r in self.rows if r["blocking"] and not r["pass"])

    def n_warn(self) -> int:
        return sum(1 for r in self.rows if not r["blocking"] and not r["pass"])


def _probe(py: str, code: str, timeout: int = 120) -> dict:
    """在**指定解释器**里跑一段代码，回显 stdout / 错误。只读，不写任何文件。"""
    if not Path(py).exists():
        return {"ok": False, "error": f"interpreter_missing: {py}", "stdout": None}
    try:
        p = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "stdout": None}
    if p.returncode != 0:
        return {"ok": False, "error": (p.stderr or "").strip().splitlines()[-1:] or ["nonzero_exit"],
                "stdout": p.stdout.strip() or None, "returncode": p.returncode}
    return {"ok": True, "stdout": p.stdout.strip(), "error": None}


_VER_CODE = """
import json, importlib.util, importlib.metadata as md
out = {}
for name in %s:
    spec = None
    try:
        spec = importlib.util.find_spec(name)
    except Exception as exc:
        spec = None
        out[name] = {"importable": False, "version": None, "error": type(exc).__name__}
        continue
    if spec is None:
        out[name] = {"importable": False, "version": None, "error": "ModuleNotFoundError"}
        continue
    try:
        ver = md.version(name)
    except Exception:
        try:
            m = __import__(name)
            ver = getattr(m, "__version__", "?")
        except Exception as exc:
            ver = None
            out[name] = {"importable": False, "version": None, "error": type(exc).__name__}
            continue
    out[name] = {"importable": True, "version": ver}
print(json.dumps(out))
"""


def collect_state(args) -> dict:
    train_py = f"{PIN['train_venv']}/bin/python"
    eval_py = f"{PIN['eval_venv']}/bin/python"
    st = {
        "train_python_exists": Path(train_py).exists(),
        "eval_python_exists": Path(eval_py).exists(),
        "train_versions": _probe(train_py, _VER_CODE % repr(["lerobot", "torch", "torchvision",
                                                             "numpy", "gymnasium"])) if args.probe else {},
        "eval_versions": _probe(eval_py, _VER_CODE % repr(["lerobot", "robosuite", "mujoco",
                                                           "numpy", "gymnasium"])) if args.probe else {},
        "act_entrypoints": _probe(train_py, "from lerobot.policies.act.configuration_act import ACTConfig;"
                                            "from lerobot.policies.act.modeling_act import ACTPolicy;"
                                            "print('OK')") if args.probe else {},
        "train_help": _probe(train_py, "import runpy,sys;sys.argv=['lerobot_train','--help'];"
                                      "runpy.run_module('lerobot.scripts.lerobot_train',"
                                      "run_name='__main__')", timeout=180) if args.probe else {},
        "install_source": _probe(train_py, """
import json, importlib.metadata as md
d = md.distribution('lerobot')
info = {'installer': None, 'direct_url': None}
try:
    info['installer'] = d.read_text('INSTALLER')
except Exception:
    pass
try:
    info['direct_url'] = d.read_text('direct_url.json')
except Exception:
    pass
try:
    info['location'] = str(d._path)
except Exception:
    pass
print(json.dumps(info))
""") if args.probe else {},
    }
    man_path = Path(args.c_manifest)
    if not man_path.is_absolute():
        man_path = ROOT / args.c_manifest
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        man = {}
    st["manifest"] = man
    st["manifest_path"] = str(man_path)
    st["locks"] = {n: (ROOT / p).is_file() for n, p in (("train", LOCK_TRAIN), ("eval", LOCK_EVAL))}
    return st


def _ver(probe: dict, pkg: str) -> str | None:
    if not probe.get("ok"):
        return None
    try:
        blob = json.loads(probe.get("stdout") or "{}")
    except json.JSONDecodeError:
        return None
    return (blob.get(pkg) or {}).get("version")


def _importable(probe: dict, pkg: str) -> bool:
    if not probe.get("ok"):
        return False
    try:
        blob = json.loads(probe.get("stdout") or "{}")
    except json.JSONDecodeError:
        return False
    return bool((blob.get(pkg) or {}).get("importable"))


def run_checks(st: dict) -> Checks:
    ck = Checks()
    tv, ev = st.get("train_versions") or {}, st.get("eval_versions") or {}
    lr_ver = _ver(tv, "lerobot")

    # ---- E1：训练 venv 解释器存在（pin 路径，不是 rlrobot）----
    ck.add("E1", "训练 venv 解释器存在（/root/venvs/lerobot_act/bin/python）",
           bool(st.get("train_python_exists")),
           {"train_python_exists": st.get("train_python_exists")},
           {"train_python_exists": True},
           note="B §1：lerobot 按设计**从不**装在 rlrobot 里（两份 lock 均无 lerobot）。"
                "缺口不是「rlrobot 少一个包」，而是「A 的训练/评测环境整体需按 installer 重建」。")

    # ---- E2：lerobot 版本 == pin（**不是**只验 importable）----
    ck.add("E2", f"lerobot.__version__ == {PIN['lerobot']}（只验 importable 是恒真判据）",
           lr_ver == PIN["lerobot"],
           {"importable": _importable(tv, "lerobot"), "version": lr_ver,
            "known_bad_source_version": KNOWN_BAD_SOURCE_VERSION,
            "probe_error": tv.get("error")},
           {"version": PIN["lerobot"]},
           note="B §4 的实测反例：离线候选 checkout `lerobot_0cf8648` 比 tag v0.4.4 **落后 488 commit**、"
                f"pyproject 写 version=0.1.0 ⇒ 从它装出来 `import lerobot` **照样成功**。"
                "只验 importable 会把它放过去，而 48 臂权威表依赖的官方 ACT 入口是 0.4.4 的。")

    # ---- E3：官方 ACT 入口真能 import + train --help 真能跑 ----
    ck.add("E3", "官方 ACT 入口可用（ACTConfig / ACTPolicy import + lerobot_train --help）",
           bool((st.get("act_entrypoints") or {}).get("ok"))
           and bool((st.get("train_help") or {}).get("ok")),
           {"entrypoints_ok": (st.get("act_entrypoints") or {}).get("ok"),
            "entrypoints_error": (st.get("act_entrypoints") or {}).get("error"),
            "train_help_ok": (st.get("train_help") or {}).get("ok"),
            "train_help_error": (st.get("train_help") or {}).get("error")},
           {"entrypoints_ok": True, "train_help_ok": True},
           note="版本对不等于入口在（源装场景下 `__version__` 来自 importlib.metadata，"
                "与真实 API 可能脱节）。这条判的是 48 臂表实际依赖的那两个入口。")

    # ---- E4：评测 venv（lerobot + robosuite 同解释器）----
    e4_terms = {
        "eval_python_exists": bool(st.get("eval_python_exists")),
        "robosuite_pin": _ver(ev, "robosuite") == PIN["eval_robosuite"],
        "numpy_pin": _ver(ev, "numpy") == PIN["eval_numpy"],
        "mujoco_present": _importable(ev, "mujoco"),
        "lerobot_present": _importable(ev, "lerobot"),
    }
    ck.add("E4", f"评测 venv 齐备（robosuite {PIN['eval_robosuite']} / numpy {PIN['eval_numpy']} / mujoco / lerobot）",
           all(e4_terms.values()),
           {"terms": e4_terms,
            "observed": {"robosuite": _ver(ev, "robosuite"), "numpy": _ver(ev, "numpy"),
                         "mujoco": _ver(ev, "mujoco"), "lerobot": _ver(ev, "lerobot"),
                         "probe_error": ev.get("error")}},
           {"terms": {k: True for k in e4_terms}},
           note="闭环真值评测要 lerobot 与 robosuite **同解释器**。评测环境那条 `numpy==2.4.6` 的 "
                "`--override` 是**已声明的例外**（robosuite→mink 的陈旧 pin），不是 pin 漂移（B §2）。")

    # ---- E5：安装来源可核（wheel / 源装 + commit）----
    src_raw = (st.get("install_source") or {}).get("stdout")
    try:
        src = json.loads(src_raw or "{}")
    except json.JSONDecodeError:
        src = {}
    installer = (src.get("installer") or "").strip()
    direct_url = src.get("direct_url")
    location = src.get("location") or ""
    is_wheel = installer.lower().startswith(("uv", "pip", "wheel")) and not direct_url
    source_install = bool(direct_url) or "site-packages" not in location
    ck.add("E5", "安装来源可核（wheel 还是源装；源装必须能追到 commit）",
           bool(installer) and (is_wheel or PIN["v044_commit"][:7] in json.dumps(src)),
           {"installer": installer or None, "direct_url": direct_url, "location": location or None,
            "classified_as": ("wheel" if is_wheel else ("source" if source_install else "unknown"))},
           {"installer": "非空", "if_source": f"commit 可追（v0.4.4 = {PIN['v044_commit']}）"},
           note="B §5.3 要求回显安装来源。源装而不回显 commit ⇒ 无法排除「装的是落后 488 commit 的那份」。")

    # ---- E6：C 的 manifest 不再声明 A 线被阻 ----
    man = st.get("manifest") or {}
    blocked = (man.get("reproduction_claims_blocked") or {})
    pm_lr = ((man.get("probe_modules") or {}).get("lerobot") or {})
    e6_terms = {
        "manifest_readable": bool(man),
        "probe_modules_has_lerobot": "lerobot" in (man.get("probe_modules") or {}),
        "probe_version_matches_pin": pm_lr.get("version") == PIN["lerobot"],
        "reproduction_claims_unblocked": blocked.get("blocked") is False,
        "env_fully_restored": man.get("env_fully_restored") is True,
    }
    # 裁定 36.4 的同源规则（D §9.7-5 的 P2）：note 曾是与实测**相反**的静态散文
    # （硬写「现值 importable=false ⇒ 本条应当红」，而这一跑 E6=PASS ⇒ 日志里 PASS 与「应当红」并存）。
    # 判据本身没问题（五个 term 都读真值、有变异期望），改的只是旁挂散文：**由观测生成**。
    e6_verdict = ("绿" if all(e6_terms.values()) else "红")
    e6_note = (
        "裁定 29.4 要求 C（P0）把 lerobot 加进 probe_modules。"
        f"**现测（与本行 terms 同源，manifest generated_at={man.get('generated_at')}）**："
        f"probe_modules.lerobot.version={pm_lr.get('version')!r}、"
        f"reproduction_claims_blocked.blocked={blocked.get('blocked')!r}、"
        f"env_fully_restored={man.get('env_fully_restored')!r} ⇒ 本条={e6_verdict}。"
        "manifest 的「全绿」只覆盖 `required_for_c_regression`，`env_fully_restored=false` 时"
        "不得读成「环境已完全恢复」。"
        "**历史说明（12:14–15:30 期间，已过期，勿当现值引用）**：C 的 12:14 manifest 记 "
        "`importable=false`，本条当时为红、是 A 线唯一红项；C 重探后转绿"
        "（D 只读复核见 `rl_harness_supervision/d_handoff_to_a_20260929.md` §9.7）。"
        "引用本条结论请引 `terms` 的取值，不要引旁挂散文。")
    ck.add("E6", "C 的 env manifest 已把 lerobot 探通、且不再声明 A 线被阻",
           all(e6_terms.values()),
           {"terms": e6_terms, "probe_modules.lerobot": pm_lr,
            "reproduction_claims_blocked": blocked.get("blocked"),
            "env_fully_restored": man.get("env_fully_restored"),
            "manifest": st.get("manifest_path"),
            "manifest_generated_at": man.get("generated_at")},
           {"terms": {k: True for k in e6_terms}},
           note=e6_note)

    # ---- E7（非 blocking）：两份 lock 在位 ----
    ck.add("E7", "train / eval 两份 lock 在位（重装后要比对）",
           all(st.get("locks", {}).values()), st.get("locks"),
           {"train": True, "eval": True}, blocking=False,
           note=f"pin 的事实源。A 不自己定 pin，只照 B 的 DR-012 §2 表断言（{PIN['source_doc']}）。")

    return ck


def report(ck: Checks, gate_open: bool) -> None:
    for r in ck.rows:
        tag = "PASS" if r["pass"] else ("FAIL" if r["blocking"] else "WARN")
        print(f"[{tag}] {r['id']:<4} {r['name']}")
        if not r["pass"]:
            print(f"           observed = {json.dumps(r['observed'], ensure_ascii=False)[:700]}")
            print(f"           required = {json.dumps(r['required'], ensure_ascii=False)[:300]}")
        if r["note"]:
            print(f"           note     = {r['note']}")
    print()
    print(f"A_NEW_REPRO_CLAIMS={'ALLOWED' if gate_open else 'BLOCKED'}  "
          f"blocking_fail={ck.n_fail_blocking()}  warn={ck.n_warn()}  total_checks={len(ck.rows)}")
    if gate_open:
        print("  ⇒ A 可以声称新的训练 / 评测复现（仍须按纪律带构建指纹与口径名）。")
    else:
        print("  此刻**允许**声称：一切**只读后处理**结论 —— 门禁裁定 / 48 臂汇总 / 分布层引用 /")
        print("                       登记册 / 账本视图自检（裁定 29.4 已解封；依据是机制性的：")
        print("                       构建哈希未变 + 被裁定产物未改写 + 现场重判计数与留档逐格相同）。")
        print("  此刻**不得**声称：任何需要跑训练 / 评测的**新复现**（含 B §8 那两条要动训练侧代码的 T17 待办）。")
        print("  解除条件：bash scripts/install_lerobot_act_env.sh 重建两个 venv 并通过本闸 E1–E6。")


# --------------------------------------------------------------------------
# 变异自检：fixture 全在内存，不起子进程、不写文件。
# --------------------------------------------------------------------------
def _blob(**kw) -> dict:
    return {"ok": True, "stdout": json.dumps(kw), "error": None}


def _fixture(**over) -> dict:
    st = {
        "train_python_exists": True, "eval_python_exists": True,
        "train_versions": _blob(lerobot={"importable": True, "version": PIN["lerobot"]},
                                torch={"importable": True, "version": PIN["torch"]},
                                torchvision={"importable": True, "version": PIN["torchvision"]},
                                numpy={"importable": True, "version": PIN["train_numpy"]},
                                gymnasium={"importable": True, "version": PIN["train_gymnasium"]}),
        "eval_versions": _blob(lerobot={"importable": True, "version": PIN["lerobot"]},
                               robosuite={"importable": True, "version": PIN["eval_robosuite"]},
                               mujoco={"importable": True, "version": PIN["eval_mujoco"]},
                               numpy={"importable": True, "version": PIN["eval_numpy"]},
                               gymnasium={"importable": True, "version": PIN["eval_gymnasium"]}),
        "act_entrypoints": {"ok": True, "stdout": "OK", "error": None},
        "train_help": {"ok": True, "stdout": "usage: ...", "error": None},
        "install_source": {"ok": True, "stdout": json.dumps(
            {"installer": "uv\n", "direct_url": None, "location": "/x/site-packages/lerobot-0.4.4.dist-info"}),
            "error": None},
        "manifest": {"probe_modules": {"lerobot": {"importable": True, "version": PIN["lerobot"]}},
                     "reproduction_claims_blocked": {"blocked": False},
                     "env_fully_restored": True},
        "manifest_path": "<fixture>", "locks": {"train": True, "eval": True},
    }
    st.update(over)
    return st


_MISSING = {"ok": False, "stdout": None, "error": "interpreter_missing"}


def selftest() -> int:
    cases = [
        ("S1 合规 fixture（两个 venv 都按 pin 装好）-> ALLOWED",
         _fixture(), (), True),
        ("S2 从落后 488 commit 的源装成 0.1.0（import 照样成功）-> CLOSED(E2)",
         _fixture(train_versions=_blob(
             lerobot={"importable": True, "version": KNOWN_BAD_SOURCE_VERSION},
             torch={"importable": True, "version": PIN["torch"]},
             torchvision={"importable": True, "version": PIN["torchvision"]},
             numpy={"importable": True, "version": PIN["train_numpy"]},
             gymnasium={"importable": True, "version": PIN["train_gymnasium"]})),
         ("E2",), False),
        # fixture 必须**自洽**：lerobot 全缺时，入口探针与来源探针也必然失败。
        # 首版只覆盖了版本 blob、留着 act_entrypoints ok=True，是 fixture 自相矛盾（不是判据缺口）；
        # E3 的牙由 S5 单独证明。
        ("S3 lerobot 完全 MISSING -> CLOSED(E2,E3,E4,E5)",
         _fixture(train_versions=_blob(), eval_versions=_blob(),
                  act_entrypoints={"ok": False, "stdout": None,
                                   "error": "ModuleNotFoundError: No module named 'lerobot'"},
                  train_help={"ok": False, "stdout": None, "error": "No module named lerobot"},
                  install_source={"ok": False, "stdout": None, "error": "PackageNotFoundError"}),
         ("E2", "E3", "E4", "E5"), False),
        ("S4 训练 venv 不存在（0929 检修的真实现场）-> CLOSED(E1,E2,E3)",
         _fixture(train_python_exists=False, train_versions=_MISSING,
                  act_entrypoints=_MISSING, train_help=_MISSING, install_source=_MISSING),
         ("E1", "E2", "E3"), False),
        ("S5 版本对但官方入口 import 不了 -> CLOSED(E3)【E3 有牙】",
         _fixture(act_entrypoints={"ok": False, "stdout": None, "error": "ImportError: ACTPolicy"}),
         ("E3",), False),
        ("S6 评测 venv 的 numpy 装成 2.2.6（train 的值）-> CLOSED(E4)",
         _fixture(eval_versions=_blob(
             lerobot={"importable": True, "version": PIN["lerobot"]},
             robosuite={"importable": True, "version": PIN["eval_robosuite"]},
             mujoco={"importable": True, "version": PIN["eval_mujoco"]},
             numpy={"importable": True, "version": PIN["train_numpy"]},
             gymnasium={"importable": True, "version": PIN["eval_gymnasium"]})),
         ("E4",), False),
        ("S7 源装但不回显 commit -> CLOSED(E5)",
         _fixture(install_source={"ok": True, "stdout": json.dumps(
             {"installer": "pip\n", "direct_url": {"url": "file:///tmp/lerobot_0cf8648"},
              "location": "/x/lerobot.egg-link"}), "error": None}),
         ("E5",), False),
        ("S8 C 的 manifest 仍声明 A 被阻（12:14–15:30 的**历史**状态）-> CLOSED(E6)",
         _fixture(manifest={"probe_modules": {"lerobot": {"importable": False, "version": None}},
                            "reproduction_claims_blocked": {"blocked": True},
                            "env_fully_restored": False}),
         ("E6",), False),
        ("S9 manifest 不可读 -> CLOSED(E6)【无证据不放行】",
         _fixture(manifest={}), ("E6",), False),
        ("S10 lock 缺失 -> 仅 WARN(E7)，其余仍 ALLOWED",
         _fixture(locks={"train": False, "eval": True}), (), True),
    ]
    n_pass = 0
    print(f"{'变异自检':<56}{'期望':<24}结果")
    print("-" * 100)
    for name, st, expect_closed, expect_open in cases:
        ck = run_checks(st)
        got = tuple(r["id"] for r in ck.rows if not r["pass"] and r["blocking"])
        if expect_open:
            ok = ck.open and (not expect_closed or all(c in
                  tuple(r["id"] for r in ck.rows if not r["pass"]) for c in expect_closed))
            want = "ALLOWED"
        else:
            ok = (not ck.open) and all(c in got for c in expect_closed)
            want = "CLOSED(" + ",".join(expect_closed) + ")"
        gots = "ALLOWED" if ck.open else "CLOSED(" + ",".join(got) + ")"
        print(f"    {name:<52}{want:<24}-> {'pass' if ok else 'FAIL'}   gate={gots}")
        n_pass += 1 if ok else 0
    print(f"\n  环境就绪闸自检：{n_pass}/{len(cases)} 通过")
    return 0 if n_pass == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--c-manifest", default=C_MANIFEST)
    ap.add_argument("--no-probe", dest="probe", action="store_false",
                    help="不起子进程探 venv（只读 manifest / lock；用于快速判 A 线是否被阻）")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    st = collect_state(args)
    ck = run_checks(st)
    report(ck, ck.open)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "check": "a_env_readiness_gate",
            "ruling": "裁定 29.4 / 增补七 §19-A④（A 侧行为约束的代码承载）",
            "pin_source": PIN["source_doc"],
            "pin": PIN,
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "read_only": True, "probed": bool(args.probe),
            "verdict": "ALLOWED" if ck.open else "BLOCKED",
            "blocking_fail": [r["id"] for r in ck.rows if r["blocking"] and not r["pass"]],
            "warn": [r["id"] for r in ck.rows if not r["blocking"] and not r["pass"]],
            "n_checks": len(ck.rows), "rows": ck.rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  留档 -> {args.json_out}")
    return 0 if ck.open else 1


if __name__ == "__main__":
    sys.exit(main())
