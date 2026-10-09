#!/usr/bin/env python3
"""C 线：环境 manifest + 「0929 检修导致 venv 重建」断点登记（增补六 §0.2 第 2 条）。

为什么要有这一份产物：D 的裁定把检修影响面分成两类 —— 只读后处理类结论**不因检修失效**
（依据是机制性的：`GATE_BUILD` 是脚本内容哈希，被裁产物未被改写），而任何需要
`rlrobot` venv 的**评测/训练复现**主张**必须重验**。要执行这条裁定，就得能回答
「某条复现主张跨没跨过 0929 这个断点」—— 而这需要一个**带时间戳的环境快照**当参照物。
口径沿用 `docs/lerobot_official_env_manifest_20260924.md`：环境路径 + 记录版本 +
版本冲突 + 入口验证结果，四块都要有，缺一块将来就没法判断。

三条纪律（与本仓其他 C 线脚本一致）：
1. **只报实测，不外推**：每一项都注明是「本脚本现场测的」还是「读某个产物的落盘值」。
   测不到就写 `null` + 原因，不填一个看起来合理的值。
2. **不碰 GPU 上下文**：A 在用卡训练，本脚本只读 `nvidia-smi` 的查询接口，
   不创建 CUDA / EGL 上下文（`gl_context_probe.attempted=false` 并写明原因）。
3. **不写别人的目录**：产物只落 `runs/infra/c_env_manifest_*.json`。

用法：
    /root/venvs/rlrobot/bin/python scripts/c_env_manifest.py            # 出 manifest
    /root/venvs/rlrobot/bin/python scripts/c_env_manifest.py --check    # 顺带做 lock 一致性闸
    PY=python3 python3 scripts/c_env_manifest.py --venv /opt/conda      # 给别的环境出快照

`--check` 的判据（有牙，不是恒真）：`requirements.lock.txt` 里每一个 pin 都必须在**当前解释器**
下装成**完全相同的版本**、且 `required_for_c_regression` 那批模块全部可 import；
任一不满足就 exit 3。本轮实测 28/28 全中 ⇒ exit 0（反证见 `docs/c_env_manifest_and_pending_impl_20260929.md` §4.4）。

**「全绿」的边界（裁定 29.4，增补七 §17）**：本脚本探到的 `blocking_for_reproduction`
（`lerobot`）缺失时，`--check` 仍然 PASS —— 因为它闸的是 C 的只读回归所需依赖，
而 lerobot 阻的是 **A 线的新训练/新评测**。为避免「manifest 全绿」被误读成「环境已完全恢复」，
manifest 顶层单列 `env_fully_restored` 与 `reproduction_claims_blocked`，`--check` 每次都会把
未恢复的部分喊出来。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import site
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_VENV = Path("/root/venvs/rlrobot")
DEFAULT_LOCK = ROOT / "requirements.lock.txt"
DEFAULT_OUT = ROOT / "runs" / "infra" / "c_env_manifest_20260929.json"
REBUILD_DIR = ROOT / "runs" / "infra" / "c_env_rebuild_20260929"
# 不在 lock 里、但 C 的脚本要用到的包：lock 是 `pip freeze --local`，
# venv 建时带了 --system-site-packages，这批从 base 继承 ⇒ 必须单独记，
# 否则「lock 全中」会给出一个假的安心（真正跑训练的那几个恰恰不在 lock 里）。
INHERITED_PACKAGES = ("torch", "torchvision", "scipy", "pandas", "pyarrow", "matplotlib",
                      "pip", "setuptools")
# C 的全量回归需要的模块（缺一个就有脚本以 ImportError 收场）。
PROBE_MODULES = ("numpy", "torch", "pandas", "pyarrow", "robosuite", "gymnasium",
                 "py_trees", "mujoco", "stable_baselines3", "mink", "scipy", "numba", "pytest")
# 裁定 29.4（增补七 §17）：lerobot **不在** `requirements.lock.txt` 里、也不属于 rlrobot 这个
# venv（项目口径是另建两个 venv，见 `docs/lerobot_act_env_setup_20260928.md`），但它缺失就
# 阻住 A 线的一切新训练/新评测 ⇒ 必须探、必须报，且**不得**让「manifest 全绿」被读成
# 「环境已完全恢复」。它单列一类，不进 `--check` 的 required 闸（否则 C 自己的回归永远红）。
BLOCKING_PROBE_MODULES = ("lerobot",)
ALL_PROBE_MODULES = PROBE_MODULES + BLOCKING_PROBE_MODULES
# 项目口径里的 lerobot 环境（`docs/lerobot_act_env_setup_20260928.md` 表：两个 venv 分开建，
# 因为闭环真值评测必须在**同一个解释器**里既能 import lerobot 又能 import robosuite）。
PERSISTENT_ENV_ROOT = Path(
    "/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs")
# 裁定 31.2 / DR-012：探针探**那两个 venv**（不是往 rlrobot 里探 lerobot —— 那里按设计
# 从来就没有它，探到 MISSING 是设计如此，不得记成缺口）。候选路径含持久目录：
# 裁定 32.3 之后 venv 建在 NFS 上，`/root/venvs/` 下只是符号链接；A 用 installer 的
# `VENV=` / `EVAL_VENV=` 覆写路径，C 的探针靠 candidates + 环境变量覆写跟着指过去。
LEROBOT_ENVS = (
    {"name": "lerobot_act", "path": "/root/venvs/lerobot_act",
     "candidates": ("/root/venvs/lerobot_act", str(PERSISTENT_ENV_ROOT / "lerobot_act")),
     "env_override": "C_PROBE_VENV_LEROBOT_ACT",
     "role": "官方 ACT 训练 / 离线审计",
     "system_site_packages_expected": False,
     "expected": "python 3.11.9, torch 2.6.0+cu124, torchvision 0.21.0+cu124, lerobot 0.4.4, "
                 "numpy 2.2.6, gymnasium 1.3.0, CUDA 12.4"},
    {"name": "lerobot_eval", "path": "/root/venvs/lerobot_eval",
     "candidates": ("/root/venvs/lerobot_eval", str(PERSISTENT_ENV_ROOT / "lerobot_eval")),
     "env_override": "C_PROBE_VENV_LEROBOT_EVAL",
     "role": "闭环真值评测（lerobot + robosuite 同解释器）",
     "system_site_packages_expected": False,
     "expected": "同上 + numpy 2.4.6, gymnasium 1.2.3, mujoco 3.9.0, robosuite 1.5.2, py_trees 2.6.0"},
)
LEROBOT_LOCK_DIR = ROOT / "runs" / "infra" / "lerobot_act_env_20260928"
LEROBOT_LOCK_BACKUP = ROOT / "runs" / "infra" / "c_lerobot_env_locks_backup_20260928"
LEROBOT_INSTALLER = ROOT / "scripts" / "install_lerobot_act_env.sh"
LEROBOT_PIN_DOC = ROOT / "docs" / "lerobot_env_reinstall_pin_20260929.md"
A_REBUILD_DIR = ROOT / "runs" / "infra" / "a_lerobot_env_rebuild_20260929"
INHERITED_BASELINE = REBUILD_DIR / "inherited_baseline.json"
VENV_MODE_DECLARATION = REBUILD_DIR / "venv_mode_declaration.json"
# C 12:14 那份 manifest（lerobot 重建之前）：rlrobot 重建窗口的**稳定证据**来源。
ARCHIVED_MANIFEST_PRE_REBUILD = ROOT / "runs" / "infra" / "c_env_manifest_20260929_pre_lerobot_rebuild.json"
# 语义断言要验的包。期望值一律**解析**自 0928 的两份 lock —— 那是「48 臂权威表当初跑在什么
# 环境上」的唯一溯源证据（裁定 32.4），也是重建后必须对得上的分母；写死在 C 的文件里
# 就等于复制了第二份 pin（裁定 21：判据单一来源）。
LEROBOT_SEMANTIC_PINS = ("lerobot", "torch", "torchvision", "numpy", "gymnasium")
LEROBOT_EVAL_EXTRA_PINS = ("mujoco", "robosuite", "numba", "opencv-python", "py_trees")
# 裁定 29.4 点名的盘上候选源（**他人副本/缓存**，不得当本项目的 pin）。
# --- 裁定 33.4（增补十 §33）C-F2：判据的每一个输入都必须与**被描述的对象**同源 ---
# 上一版把 `runs/infra/c_env_rebuild_20260929/rebuild2.log` 的 mtime 当 ready_at，而那是
# **上一个**（overlay）venv 的 ready 时刻；`--venv` 指到 D 新建的持久 venv 之后 created_at 变了、
# ready_at 没跟着变 ⇒ 窗口倒过来、断点分类自测 6 格里 5 格不符。修法不是把自测关掉，而是把
# 窗口证据与 venv 绑死：见 `_venv_window`（优先级：调用方显式给 > 该 venv 自己的
# `.persist_meta.json` > 与被描述 venv **身份对得上**的历史 manifest > 该 venv 自己的文件系统痕迹）。
PERSIST_META_NAME = ".persist_meta.json"
# 窗口不可得时允许调用方显式给（D 在 C-F2 的裁定里点名了这种给法）。
WINDOW_OVERRIDE_ENV = ("C_ENV_MANIFEST_OCCURRED_AT", "C_ENV_MANIFEST_READY_AT")

# --- 裁定 33.2 / 增补十 §34-C③：`inherited_packages` 的语义按 venv 类型分别解释 ---
# clean（自足）venv 里那 8 个包是**本地包**，不是「从 base 继承」；而 jax/jaxlib/tensorflow
# 在 clean venv 里**不可导入是设计意图**（persistent lock 头部 `excluded=jax,jaxlib`；
# conda 的 jax/tf 是 09-24 那串 ImportError 的污染源）。所以这批要**断言**，不只是观测。
EXCLUDED_BY_DESIGN = ("jax", "jaxlib", "tensorflow")

# --- 裁定 34.1（增补十一 §36）的**可红条件**：imageio / uv 若出现在 48 臂链路的 import 面，
# 那条「3 处 lock 差异放行」的裁定自动作废 ⇒ 必须实测，不能靠叙述。
RULING_34_1_PACKAGES = ("imageio", "uv")
RULING_34_1_VOID_IF_IN = ("任一 ACT 脚本", "summarize_lerobot_act_arms.py")
ACT_CHAIN_SCRIPTS = (
    "scripts/train_act_lift.py", "scripts/eval_act_lift_truth.py",
    "scripts/summarize_lerobot_act_arms.py", "scripts/_lerobot_act.py",
    "scripts/eval_lerobot_act_runtime.py", "scripts/audit_lerobot_act_overfit.py",
    "scripts/build_lerobot_act_dataset.py", "scripts/run_act_lift_runtime_failure_audit.py",
)
# 上游官方入口（**不在**本仓 48 臂链路上：`build_lerobot_act_dataset.py` 的 docstring 明写官方
# lerobot_train 读不了本仓的导出格式；installer 只用它的 `--help` 当安装闸）。单独测、单独报，
# 不与 ACT 链路混算 —— 混算就是裁定 31.3 / 33.4 那类跨对象混算。
UPSTREAM_REFERENCE_ENTRY = "lerobot.scripts.lerobot_train"
IMPORT_SURFACE_ARTIFACT = ROOT / "runs" / "infra" / "c_ruling_34_1_import_surface_20260929.json"

# 解释器指纹里的**易变字段**：`at` 是打指纹的时刻，两次打必然不同。把它算进「身份变了」
# 会让快照自洽判据**恒红**（本轮 14:52 实测就是：changed_fields=['at'] ⇒ env_fully_restored
# 永远 false）。恒红的判据等于没有判据（裁定 27.1 同型），所以显式排除，并把排除项写进产物。
FINGERPRINT_VOLATILE_FIELDS = ("at",)

LEROBOT_CANDIDATE_SOURCES = (
    "/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot",
    "/workspace/mnt/sppro/sqzhang26/gaoyuxuan/lerobot",
    "/workspace/mnt/sppro/clzhang25/LIBERO/lerobot",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _iso_ns(ns: int | None) -> str | None:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).astimezone().isoformat(
        timespec="seconds") if ns else None


def _sha12(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception:                                          # noqa: BLE001
        return None


def _file_evidence(path: Path) -> dict[str, Any]:
    """一份证据产物的可核对身份：路径 + sha256(12) + size + mtime。"""
    try:
        st = path.stat()
    except OSError as exc:
        return {"path": str(path), "exists": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "exists": True, "sha256_12": _sha12(path), "size": st.st_size,
            "mtime": _iso_ns(st.st_mtime_ns), "mtime_ns": st.st_mtime_ns}


def _parse_lock(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" in line:
            name, version = line.split("==", 1)
            pins[name.strip()] = version.strip()
        else:
            pins[line] = "<unpinned>"
    return pins


def _installed_version(name: str) -> str | None:
    """**本进程**解释器里的版本。只在「被描述的解释器 == 本进程」时才允许当观测值用。"""
    try:
        return metadata.version(name)
    except Exception:                                          # noqa: BLE001
        return None


def _same_environment(python: str) -> bool:
    """`python` 是否就是**本进程所在的**那个环境（决定能不能走本进程快路径）。

    不能比 `realpath(python)`：venv 的 `bin/python` 一律是指向 base 的符号链接，
    三个 venv 的 realpath 全是 `/opt/conda/bin/python3.11`（15:0x 实测），比它会把
    lerobot_act 判成 rlrobot ⇒ 数字是 A 的、标签是 B 的。正确做法是比**venv 前缀**：
    `<venv>/bin/python` 的 parent.parent 就是这个 venv。
    """
    try:
        prefix_from_arg = os.path.realpath(str(Path(python).absolute().parent.parent))
    except OSError:
        return False
    return (prefix_from_arg == os.path.realpath(sys.prefix)
            and os.path.realpath(python) == os.path.realpath(sys.executable))


_DIST_SNAPSHOT_CACHE: dict[str, dict[str, Any]] = {}


def _dist_snapshot(python: str, names: Sequence[str]) -> dict[str, Any]:
    """在 `python` **那个解释器**里一次性取回所有发行版的版本与位置（子进程，只读）。

    为什么要子进程：裁定 33.4 的一般规则是「判据的每一个输入都必须与被描述的对象同源」。
    上一版用 `importlib.metadata` 在**本进程**里查版本，于是 `--venv` 指到别的 venv 时，
    报出来的却是**本脚本自己那个解释器**的版本（14:5x 实测：`--venv lerobot_act` 时
    「8 个包」回显 torch 2.4.1+cu124，那是 rlrobot 的值，lerobot_act 里其实是 2.6.0+cu124）——
    标签说 A、数字是 B，比没有数字更坏。现在一律去被描述的解释器里取，并回显 `measured_in`。
    """
    key = f"{python}\u0000{','.join(sorted(names))}"
    cached = _DIST_SNAPSHOT_CACHE.get(key)
    if cached is not None:
        return cached
    if _same_environment(python):
        # 快路径：被描述的解释器就是本进程 ⇒ 在本进程里取即是同源（省一次子进程）。
        dists: dict[str, Any] = {}
        prefix = os.path.realpath(sys.prefix)
        for name in names:
            row: dict[str, Any] = {"present": False, "version": None, "dist_info": None,
                                   "venv_local": None, "inherited_from_base": None, "error": None}
            try:
                dist = metadata.distribution(name)
                path = str(dist._path)
                inside = os.path.realpath(path).startswith(prefix + os.sep)
                row.update({"present": True, "version": dist.version, "dist_info": path,
                            "venv_local": inside, "inherited_from_base": not inside})
            except Exception as exc:                           # noqa: BLE001
                row["error"] = f"{type(exc).__name__}: {exc}"
            dists[name] = row
        snap = {"dists": dists, "sys_prefix": sys.prefix, "sys_base_prefix": sys.base_prefix,
                "executable": sys.executable, "realpath_executable": os.path.realpath(sys.executable),
                "version": sys.version.split()[0], "available": True, "python": python,
                "is_this_process": True, "path_kind": "in_process_fast_path",
                "measured_at": _now_iso()}
        _DIST_SNAPSHOT_CACHE[key] = snap
        return snap
    code = (
        "import json,os,sys\n"
        "from importlib import metadata\n"
        "out={}\n"
        "for name in NAMES:\n"
        "    row={'present': False, 'version': None, 'dist_info': None,\n"
        "         'venv_local': None, 'inherited_from_base': None, 'error': None}\n"
        "    try:\n"
        "        dist=metadata.distribution(name)\n"
        "        path=str(dist._path)\n"
        "        inside=os.path.realpath(path).startswith(os.path.realpath(sys.prefix)+os.sep)\n"
        "        row.update({'present': True, 'version': dist.version, 'dist_info': path,\n"
        "                    'venv_local': inside, 'inherited_from_base': not inside})\n"
        "    except Exception as exc:\n"
        "        row['error']=f'{type(exc).__name__}: {exc}'\n"
        "    out[name]=row\n"
        "print(json.dumps({'dists': out, 'sys_prefix': sys.prefix,\n"
        "                  'sys_base_prefix': sys.base_prefix,\n"
        "                  'executable': sys.executable,\n"
        "                  'realpath_executable': os.path.realpath(sys.executable),\n"
        "                  'version': sys.version.split()[0]}))\n"
    ).replace("NAMES", repr(list(names)))
    try:
        proc = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=300)
    except Exception as exc:                                   # noqa: BLE001
        snap = {"available": False, "python": python, "path_kind": "subprocess",
                "error": f"{type(exc).__name__}: {exc}", "dists": {}}
        _DIST_SNAPSHOT_CACHE[key] = snap
        return snap
    payload = None
    for line in (proc.stdout or "").strip().splitlines()[::-1]:
        try:
            payload = json.loads(line)
            break
        except Exception:                                      # noqa: BLE001
            continue
    if payload is None:
        snap = {"available": False, "python": python, "rc": proc.returncode,
                "error": ((proc.stderr or "").strip().splitlines() or ["no json on stdout"])[-1][:300],
                "dists": {}}
        _DIST_SNAPSHOT_CACHE[key] = snap
        return snap
    payload.update({"available": True, "python": python, "path_kind": "subprocess",
                    "is_this_process": os.path.realpath(payload.get("executable") or "")
                    == os.path.realpath(sys.executable),
                    "measured_at": _now_iso()})
    _DIST_SNAPSHOT_CACHE[key] = payload
    return payload


def _dist_rows(python: str, names: Sequence[str]) -> dict[str, dict[str, Any]]:
    return dict(_dist_snapshot(python, names).get("dists") or {})


def _probe_import(module: str, interpreter: str) -> dict[str, Any]:
    """在**子进程**里 import：一个坏依赖不该把整份 manifest 带走。"""
    code = (f"import importlib,sys;m=importlib.import_module({module!r});"
            "print(getattr(m,'__version__','?'))")
    try:
        proc = subprocess.run([interpreter, "-c", code], capture_output=True, text=True, timeout=180)
    except Exception as exc:                                   # noqa: BLE001
        return {"importable": False, "version": None,
                "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode == 0:
        return {"importable": True, "version": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "?"}
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return {"importable": False, "version": None, "error": tail[-1][:200] if tail else "unknown"}


def _installer_pins(path: Path) -> dict[str, Any]:
    """从 `install_lerobot_act_env.sh` 里**解析**出 pin 缺省值（不抄写：脚本一改就跟着变）。"""
    if not path.exists():
        return {"available": False, "reason": f"脚本不存在: {path}"}
    text = path.read_text(encoding="utf-8")
    pins = {}
    for var in ("VENV", "BASE_PY", "INDEX", "TORCH", "TORCHVISION", "LEROBOT", "EVAL_VENV", "LOCK_OUT"):
        # `\$` 必须转义：正则里裸 `$` 是行尾锚，第一版就这么写，结果一个 pin 都没解析出来
        # （manifest 里 `pin.values` 是空 dict —— 空值比错值更难发现，故登记）。
        m = re.search(rf'^{var}="\${{{var}:-([^}}]*)}}"', text, flags=re.MULTILINE)
        if m:
            pins[var] = m.group(1)
    pins["_parsed_from"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    pins["_sha256_12"] = _sha12(path)
    return pins


def _git_head(path: Path) -> dict[str, Any]:
    """实测一个目录的 git commit（读不到就如实说读不到，不猜）。"""
    if not path.is_dir():
        return {"exists": False}
    try:
        proc = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30)
    except Exception as exc:                                   # noqa: BLE001
        return {"exists": True, "git": None, "reason": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        lines = [x.strip() for x in (proc.stderr or "").strip().splitlines() if x.strip()]
        # 取 `fatal:` 那行，不是最后一行：git 在用法提示之前才给出真正的原因
        # （第一版取了最后一行，报出来的是 `git <command> [<revision>...]` 这种无用提示）。
        fatal = next((x for x in lines if x.startswith("fatal:")), None)
        return {"exists": True, "git": None,
                "reason": (fatal or (lines[-1] if lines else "not a git repository"))[:160]}
    return {"exists": True, "git": proc.stdout.strip()}


def _lock_pins_lerobot(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("lerobot=="):
            return line.strip()
    return None


def _nvidia_smi() -> dict[str, Any]:
    """只读查询（不建 CUDA 上下文）。没有 nvidia-smi 就如实记 null。"""
    query = "index,name,memory.used,memory.total,utilization.gpu,driver_version"
    try:
        proc = subprocess.run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=60)
    except Exception as exc:                                   # noqa: BLE001
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"available": False, "reason": (proc.stderr or "").strip()[:200]}
    gpus = []
    for line in proc.stdout.strip().splitlines():
        fields = [f.strip() for f in line.split(",")]
        if len(fields) == 6:
            gpus.append(dict(zip(("index", "name", "memory_used", "memory_total",
                                  "utilization_gpu", "driver_version"), fields)))
    return {"available": True, "gpus": gpus}


def _position_vs_breakpoint(mtime_ns: int | None, occurred_ns: int | None,
                            ready_ns: int | None) -> str | None:
    """产物相对断点窗口的位置：before / during_rebuild / after（不可判 ⇒ None）。

    抽成纯函数是为了能**自测**：本轮 8 份 C 自检产物全部落在断点之后，
    `before` 与 `during_rebuild` 两支在真数据上是空过的 —— 空过的规则等于没有规则。
    """
    if mtime_ns is None or occurred_ns is None or ready_ns is None:
        return None
    if mtime_ns < occurred_ns:
        return "before"
    if mtime_ns < ready_ns:
        return "during_rebuild"
    return "after"


def _breakpoint_classifier_selftest(occurred_ns: int | None, ready_ns: int | None) -> dict[str, Any]:
    """用**合成的有序窗口**逐支验证分类规则（含边界），如实记录 expected/got。

    为什么不拿真窗口自测：真窗口可能不可得、甚至**倒过来**（rlrobot 迁到 NFS 之后
    `bin/python` 的 ctime 就成了迁移时刻，见 `_rebuild_window`）。用真窗口自测会让
    「规则自测」因为**数据**问题转红，读的人分不清是规则错还是观测错 —— 两件事必须分开报：
    规则用合成窗口自测，真窗口的一致性单独报 `window_consistent`。
    """
    syn_occurred = 1_700_000_000_000_000_000
    syn_ready = syn_occurred + 700_000_000_000        # 700 秒的重建窗口
    cells = (
        ("断点前 1 秒", syn_occurred - 1_000_000_000, "before"),
        ("断点起点（含）", syn_occurred, "during_rebuild"),
        ("重建窗口正中", (syn_occurred + syn_ready) // 2, "during_rebuild"),
        ("ready 前 1 秒", syn_ready - 1_000_000_000, "during_rebuild"),
        ("ready 时刻（含）", syn_ready, "after"),
        ("断点后 1 小时", syn_ready + 3_600_000_000_000, "after"),
    )
    rows = [{"label": label, "expected": exp,
             "got": _position_vs_breakpoint(ts, syn_occurred, syn_ready)}
            for label, ts, exp in cells]
    real_consistent = bool(occurred_ns is not None and ready_ns is not None
                           and occurred_ns <= ready_ns)
    return {"ran": True, "rows": rows, "all_match": all(r["got"] == r["expected"] for r in rows),
            "window": {"kind": "synthetic", "occurred_ns": syn_occurred, "ready_ns": syn_ready,
                       "why_synthetic": "真窗口可能不可得或倒过来 ⇒ 规则自测与数据一致性分开报"},
            "real_window": {"occurred_ns": occurred_ns, "ready_ns": ready_ns,
                            "consistent": real_consistent,
                            "usable_for_attribution": real_consistent},
            "note": ("边界口径：occurred_at 与 ready_at 两端都算「窗口内/后」的起点（>=），"
                     "即 ready 时刻当刻产出的东西算 after —— 重建日志落盘即环境可用。")}


def _selfcheck_artifacts(windows: dict[str, tuple[int | None, int | None]],
                         governing: str) -> list[dict[str, Any]]:
    """把 C 自己的自检产物按「跑在哪个窗口前/中/后」分类（只读落盘值，不重跑）。

    这一栏是断点登记的**用途**所在：跨没跨过 0929 断点，靠的是产物 mtime 与 venv 创建时刻
    的先后，而不是靠人记。`ran_after_breakpoint=null` 表示没有可比窗口（窗口不可得或倒置）。

    本轮有**三条**断点、各自描述**不同的 venv**，所以归属按窗口分别给（`positions_by_window`），
    顶层的 `position_vs_breakpoint` 只取 `governing` 那一个窗口 —— 也就是**被描述的这个 venv**
    自己的窗口（裁定 33.4 C-F2：不同对象的时刻不得混用）。
    """
    # 各脚本的「过没过」写的键名不统一（`pass` / `conformant`），这里按优先级取第一个存在的，
    # 并把**取的是哪个键**一并记下 —— 否则读 manifest 的人会以为口径是统一的。
    pass_keys = ("pass", "conformant", "all_pass", "ok")
    out = []
    for path in sorted((ROOT / "runs" / "infra").glob("c_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                      # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        pass_key = next((k for k in pass_keys if k in payload), None)
        if pass_key is None:
            continue          # 不是自检结果（如 inventory / manifest 本身）
        st = path.stat()
        positions = {label: _position_vs_breakpoint(st.st_mtime_ns, occ, rdy)
                     for label, (occ, rdy) in windows.items()}
        position = positions.get(governing)
        out.append({
            "positions_by_window": positions,
            "artifact": str(path.relative_to(ROOT)), "sha256_12": _sha12(path),
            "mtime": _iso_ns(st.st_mtime_ns),
            "pass_key": pass_key, "pass": payload.get(pass_key),
            "n_checks": payload.get("n_checks"), "n_pass": payload.get("n_pass"),
            "n_failed": payload.get("n_failed"), "n_skipped": payload.get("n_skipped"),
            "counts": payload.get("counts"),
            "position_vs_breakpoint": position,
            "ran_after_breakpoint": (None if position is None else position == "after"),
        })
    return out


def _version_vs_pin(module_version: Any, dist_version: Any, expect: str | None,
                    *, strict_self_report: bool = False) -> dict[str, Any]:
    """版本号断言（裁定 31.2：验**语义值**，不验可导入）。

    两处细节必须分清，否则会犯两种方向相反的错：

    - `importlib.metadata` 的版本才是 pip/uv freeze 记进 lock 的那个（**权威**比对对象）；
    - 模块自报的 `__version__` 可能带 PEP 440 的 local segment（torch 自报 `2.6.0+cu124`，
      lock 里是 `2.6.0`）。只比字符串会把「装对了」报成 mismatch（**假红**，裁定 27.4 同型）；
      但只比 dist 版本又会放过「dist-info 写着 0.4.4、模块自报 0.1.0」这种形状 ⇒
      **两个都比**，除 local segment 之外的差异一律算不符。
    - `strict_self_report=True`（lerobot 用）：连 local segment 也不容 —— D 的要求字面就是
      `lerobot.__version__ == "0.4.4"`（源装成 0.1.0 时 import 照样成功，这是恒真判据的解药）。
    """
    out: dict[str, Any] = {"expected": expect, "module_version": module_version,
                           "dist_version": dist_version,
                           "strict_self_report": strict_self_report}
    if not expect:
        return {**out, "matches": None, "rule": "没有 pin 可比 ⇒ version_unverified"}
    dist_ok = dist_version == expect
    if module_version is None:
        mod_ok: bool | None = None
    elif module_version == expect:
        mod_ok = True
    elif strict_self_report:
        mod_ok = False
    else:
        mod_ok = str(module_version).startswith(expect + "+")
    out["dist_matches"] = bool(dist_ok)
    out["module_matches"] = mod_ok
    out["module_differs_only_by_local_segment"] = bool(
        mod_ok and module_version != expect and not strict_self_report)
    out["matches"] = bool(dist_ok) and mod_ok is not False
    out["rule"] = ("dist 版本必须等于 pin；模块自报版本必须等于 pin，或只差 PEP 440 的 "
                   "local segment（如 +cu124）" + ("；本包 strict：自报值必须逐字相等"
                                                  if strict_self_report else ""))
    return out


def _load_venv_mode_declaration() -> dict[str, Any]:
    """读 C 落盘的 venv 模式声明（裁定 32.3 第 1 条：选了甲还是乙**必须落盘写明**）。"""
    if not VENV_MODE_DECLARATION.exists():
        return {"available": False, "path": str(VENV_MODE_DECLARATION),
                "reason": "声明文件不存在 ⇒ pyvenv 的 site-packages 断言无从比起（不当通过读）"}
    doc = json.loads(VENV_MODE_DECLARATION.read_text(encoding="utf-8"))
    return {"available": True, "path": str(VENV_MODE_DECLARATION.relative_to(ROOT)),
            "sha256_12": _sha12(VENV_MODE_DECLARATION), "declared": doc.get("declared") or {},
            "authority": doc.get("authority"), "reading_rule": doc.get("reading_rule")}


def _interpreter_fingerprint(venv: Path) -> dict[str, Any]:
    """解释器身份的指纹：用来发现「manifest 跑到一半，脚下的 venv 被换了」。

    本轮**真的发生过**：14:21 C 的 manifest 正在跑，A 把 `/root/venvs/rlrobot` 换成了指向
    NFS 持久 venv 的符号链接（模式也从 --system-site-packages=true 变成 false）⇒
    同一份 manifest 里前半段是旧 venv 的观测、后半段是新 venv 的。那种快照**不自洽**，
    必须自己说出来（同 `c_selfcheck_verdict_identity.py::_stable_gate_snapshot` 对
    「B 正在改门禁脚本」的处理）。
    """
    cfg_path = venv / "pyvenv.cfg"
    python_path = venv / "bin" / "python"
    try:
        ctime_ns = os.lstat(python_path).st_ctime_ns
    except OSError:
        ctime_ns = None
    return {"sys_prefix": sys.prefix, "sys_base_prefix": sys.base_prefix,
            "realpath_executable": os.path.realpath(sys.executable),
            "venv_realpath": os.path.realpath(str(venv)),
            "venv_is_symlink": venv.is_symlink(),
            "pyvenv_cfg_sha256_12": _sha12(cfg_path),
            "bin_python_ctime_ns": ctime_ns,
            "at": _now_iso()}


def _parse_iso_to_ns(value: Any) -> int | None:
    """把各种写法的 ISO 时刻解析成 ns（解析不出就 None，不猜）。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    parsers = (datetime.fromisoformat,
               lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z"),
               lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%S"),
               lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S"))
    for parse in parsers:
        try:
            moment = parse(text)
        except Exception:                                      # noqa: BLE001
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone(timedelta(hours=8)))   # 本项目一律 +08:00
        return int(moment.timestamp() * 1_000_000_000)
    return None


def _parse_pyvenv_cfg(venv: Path) -> dict[str, str]:
    cfg_path = venv / "pyvenv.cfg"
    fields: dict[str, str] = {}
    if cfg_path.exists():
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key.strip()] = value.strip()
    return fields


def _venv_identity(venv: Path) -> dict[str, Any]:
    """「被描述的这个 venv」的身份。窗口证据必须先与它对上号才允许使用（裁定 33.4 C-F2）。"""
    cfg_path = venv / "pyvenv.cfg"
    meta_path = venv / PERSIST_META_NAME
    fields = _parse_pyvenv_cfg(venv)
    return {"path": str(venv), "realpath": os.path.realpath(str(venv)),
            "is_symlink": venv.is_symlink(),
            "venv_type": ("clean" if fields.get("include-system-site-packages") == "false"
                          else ("system_site" if fields.get("include-system-site-packages") == "true"
                                else "unknown")),
            "include_system_site_packages": fields.get("include-system-site-packages"),
            "pyvenv_cfg": _file_evidence(cfg_path),
            "pyvenv_cfg_fields": fields,
            "persist_meta": _file_evidence(meta_path) if meta_path.exists() else None,
            "on_persistent_nfs": os.path.realpath(str(venv)).startswith(str(PERSISTENT_ENV_ROOT)),
            "observed_at": _now_iso()}


def _venv_self_evidence(venv: Path) -> dict[str, Any]:
    """venv **自己**的文件系统痕迹（没有 `.persist_meta.json` 时的同源回退）。

    同源是构造上保证的（读的全是这个 venv 目录里的文件），但**精度低**：`pyvenv.cfg` 的 mtime
    是建档时刻，`site-packages/*.dist-info` 的最大 mtime 是「最后一次往这个 venv 里写包」的时刻 ——
    任何后续 pip 操作都会把 ready 推后。所以它只能当回退值，且必须把精度局限写进产物。
    """
    cfg_path = venv / "pyvenv.cfg"
    created_ns = None
    try:
        created_ns = cfg_path.stat().st_mtime_ns
    except OSError:
        created_ns = None
    latest_ns, latest_name, n_dist = None, None, 0
    for dist in sorted(venv.glob("lib/python*/site-packages/*.dist-info")):
        try:
            stamp = dist.stat().st_mtime_ns
        except OSError:
            continue
        n_dist += 1
        if latest_ns is None or stamp > latest_ns:
            latest_ns, latest_name = stamp, dist.name
    return {"created_ns": created_ns, "created_at": _iso_ns(created_ns),
            "created_from": "pyvenv.cfg 的 mtime（建档时刻）" if created_ns else None,
            "ready_ns": latest_ns, "ready_at": _iso_ns(latest_ns),
            "ready_from": (f"site-packages 里最晚的 dist-info（{latest_name}，共 {n_dist} 个）"
                           if latest_ns else None),
            "n_dist_info": n_dist,
            "precision_caveat": ("文件系统痕迹：同源但精度低 —— 之后任何一次 pip install 都会把 "
                                 "ready 推后，而 created 只在 pyvenv.cfg 被改写时才变。"
                                 "有 `.persist_meta.json` 时优先用它（那是建档时写死的）。")}


def _venv_window(venv: Path, *, override_occurred: str | None = None,
                 override_ready: str | None = None,
                 archived_manifest: Path | None = None) -> dict[str, Any]:
    """`[occurred, ready]` 窗口，**与被描述的那个 venv 同源**（裁定 33.4 C-F2 的修法）。

    证据优先级（越靠前越硬）：
    ① 调用方显式给（`--occurred-at` / `--ready-at`，或同名环境变量）；
    ② 这个 venv 自己的 `.persist_meta.json`：`created_at` + `elapsed_s` ⇒ ready（建档时写死，
       与被描述对象同源是构造上成立的）；
    ③ 历史 manifest —— **仅当**它描述的 venv 与本次同一个（realpath 相同且 pyvenv.cfg 逐字段相同）；
       身份对不上就**拒绝**使用，并写明它描述的是哪一个（这正是 C-F2 的成因）；
    ④ 这个 venv 自己的文件系统痕迹（`_venv_self_evidence`，精度低但同源）。
    全都拿不到 ⇒ occurred/ready 记 null + 原因，**不填一个看起来合理的值**。
    """
    identity = _venv_identity(venv)
    self_evidence = _venv_self_evidence(venv)
    venv_python = venv / "bin" / "python"
    try:
        observed_ctime_ns = os.lstat(venv_python).st_ctime_ns
    except OSError:
        observed_ctime_ns = None

    occurred_ns = ready_ns = None
    kind, sources, rejected = None, [], []

    ov_occ = override_occurred or os.environ.get(WINDOW_OVERRIDE_ENV[0])
    ov_rdy = override_ready or os.environ.get(WINDOW_OVERRIDE_ENV[1])
    if ov_occ or ov_rdy:
        kind = "caller_provided"
        occurred_ns = _parse_iso_to_ns(ov_occ) if ov_occ else self_evidence["created_ns"]
        ready_ns = _parse_iso_to_ns(ov_rdy) if ov_rdy else self_evidence["ready_ns"]
        sources.append(f"调用方显式给定（occurred={ov_occ!r}, ready={ov_rdy!r}）；"
                       "未给的一侧回退到该 venv 自己的文件系统痕迹")
    meta_path = venv / PERSIST_META_NAME
    if occurred_ns is None and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            created = _parse_iso_to_ns(meta.get("created_at"))
            elapsed = meta.get("elapsed_s")
            if created is not None:
                occurred_ns = created
                kind = kind or "persist_meta"
                sources.append(f"{PERSIST_META_NAME}.created_at={meta.get('created_at')}"
                               f"（sha256_12={_sha12(meta_path)}，n_pins={meta.get('n_pins')}，"
                               f"installer={meta.get('installer')}，clean={meta.get('clean')}）")
            if created is not None and isinstance(elapsed, (int, float)):
                ready_ns = created + int(elapsed * 1_000_000_000)
                sources.append(f"{PERSIST_META_NAME}.elapsed_s={elapsed} ⇒ ready = created + elapsed")
        except Exception as exc:                               # noqa: BLE001
            rejected.append(f"{PERSIST_META_NAME} 读不出（{type(exc).__name__}: {exc}）")
    if occurred_ns is None and archived_manifest is not None and archived_manifest.exists():
        try:
            archived = json.loads(archived_manifest.read_text(encoding="utf-8"))
            a_venv = archived.get("venv") or {}
            a_real = a_venv.get("realpath") or os.path.realpath(str(a_venv.get("path") or ""))
            same_path = bool(a_real) and a_real == identity["realpath"]
            same_cfg = bool(a_venv.get("pyvenv_cfg")) and a_venv.get("pyvenv_cfg") == identity[
                "pyvenv_cfg_fields"]
            if same_path and same_cfg:
                occurred_ns = a_venv.get("created_at_ns")
                ready_ns = a_venv.get("ready_at_ns") or ready_ns
                kind = kind or "archived_manifest_identity_matched"
                sources.append(f"{archived_manifest.name}（身份核对通过：realpath 与 pyvenv.cfg "
                               f"逐字段相同；sha256_12={_sha12(archived_manifest)}）")
            else:
                rejected.append(
                    f"{archived_manifest.name} **不用于本次窗口**：它描述的是另一个 venv"
                    f"（realpath={a_real or '未回显'}、include-system-site-packages="
                    f"{(a_venv.get('pyvenv_cfg') or {}).get('include-system-site-packages')}、"
                    f"created_at={a_venv.get('created_at')}），而被描述的是 "
                    f"{identity['realpath']}（{identity['venv_type']}）。"
                    "拿它当 ready_at 就是 C-F2 那个跨 venv 混算。")
        except Exception as exc:                               # noqa: BLE001
            rejected.append(f"{archived_manifest.name} 读不出（{type(exc).__name__}）")
    if occurred_ns is None and self_evidence["created_ns"] is not None:
        occurred_ns = self_evidence["created_ns"]
        kind = kind or "venv_self_evidence"
        sources.append(self_evidence["created_from"])
    if ready_ns is None and self_evidence["ready_ns"] is not None:
        ready_ns = self_evidence["ready_ns"]
        kind = kind or "venv_self_evidence"
        sources.append(self_evidence["ready_from"])

    consistent = (occurred_ns is not None and ready_ns is not None and occurred_ns <= ready_ns)
    return {"occurred_ns": occurred_ns, "ready_ns": ready_ns,
            "occurred_at": _iso_ns(occurred_ns), "ready_at": _iso_ns(ready_ns),
            "source_kind": kind, "source": sources, "rejected_sources": rejected,
            "subject_venv": {"realpath": identity["realpath"], "path": identity["path"],
                             "venv_type": identity["venv_type"],
                             "pyvenv_cfg_sha256_12": identity["pyvenv_cfg"].get("sha256_12"),
                             "persist_meta_sha256_12": (identity["persist_meta"] or {}).get("sha256_12")},
            "same_source": bool(kind is not None and kind != "unavailable"),
            "same_source_rule": ("裁定 33.4（C-F2）：判据的每一个输入都必须与被描述的对象同源。"
                                 "窗口证据只接受 ①调用方显式给 ②该 venv 自己的 .persist_meta.json "
                                 "③身份核对通过的历史 manifest ④该 venv 自己的文件系统痕迹；"
                                 "身份对不上的一律拒绝并写明它描述的是哪个 venv。"),
            "window_consistent": bool(consistent),
            "venv_self_evidence": self_evidence,
            "observed_bin_python_ctime_ns": observed_ctime_ns,
            "observed_bin_python_ctime": _iso_ns(observed_ctime_ns),
            "observed_ctime_unused_because": (
                "bin/python 的 ctime 在符号链接场景下记的是**迁移/建链**时刻，不是重建时刻；"
                "用它当 occurred_at 会得到倒过来的窗口。照实回显，但不参与窗口。"),
            "if_unavailable": ("occurred/ready 任一为 null 或窗口倒置 ⇒ 该 venv 的 "
                               "position_vs_breakpoint 一律记 null，不得当成 before/after 读。")}


def _historical_window(archived_manifest: Path, rebuild_log: Path,
                       described: dict[str, Any]) -> dict[str, Any]:
    """**上一个**（overlay）rlrobot venv 的重建窗口 —— 只用于 BP-20260929-venv-rebuild 那条断点。

    这条断点描述的对象是「检修把 overlay venv 抹掉后 C 在 10:45–10:57 重建的那份」，
    那份 venv 现在已 `mv` 进回收站（`recycle_bin/rlrobot_overlay_20260929_143331`）。
    所以窗口取自它自己的证据（C 当时那份 manifest + 它自己的重建日志），并显式写明
    **它描述的不是本次 `--venv` 指的那个 venv**（除非身份核对恰好相同）。
    """
    occurred_ns = ready_ns = None
    subject: dict[str, Any] = {"realpath": None, "path": None, "venv_type": "system_site（当时）"}
    sources: list[str] = []
    if archived_manifest.exists():
        try:
            archived = json.loads(archived_manifest.read_text(encoding="utf-8"))
            a_venv = archived.get("venv") or {}
            occurred_ns = a_venv.get("created_at_ns")
            ready_ns = a_venv.get("ready_at_ns")
            subject = {"realpath": a_venv.get("realpath"), "path": a_venv.get("path"),
                       "venv_type": ("system_site" if (a_venv.get("pyvenv_cfg") or {}).get(
                           "include-system-site-packages") == "true" else "unknown"),
                       "created_at": a_venv.get("created_at"), "ready_at": a_venv.get("ready_at")}
            sources.append(f"{archived_manifest.name}（C 12:14 归档，sha256_12={_sha12(archived_manifest)}；"
                           "当时实测 created/ready）")
        except Exception as exc:                               # noqa: BLE001
            sources.append(f"{archived_manifest.name} 读不出（{type(exc).__name__}）")
    if rebuild_log.exists():
        ready_ns = ready_ns or rebuild_log.stat().st_mtime_ns
        sources.append(f"{rebuild_log.relative_to(ROOT)} 的 mtime（那次重建的日志落盘 = ready）")
    applies = bool(subject.get("realpath")) and subject.get("realpath") == described.get("realpath")
    return {"occurred_ns": occurred_ns, "ready_ns": ready_ns,
            "occurred_at": _iso_ns(occurred_ns), "ready_at": _iso_ns(ready_ns),
            "source_kind": "archived_manifest_of_that_venv", "source": sources,
            "subject_venv": subject,
            "applies_to_described_venv": applies,
            "not_the_described_venv_because": (
                None if applies else
                f"本次 --venv 描述的是 {described.get('realpath')}（{described.get('venv_type')}）；"
                "本窗口描述的是 overlay 上那份已被 mv 进回收站的 venv。两者**不得混用**"
                "（裁定 33.4 C-F2）。overlay 那份的重建仍是一条真实断点，只是它的窗口"
                "不用于本次 `--venv` 的 before/during/after 归属。"),
            "window_consistent": bool(occurred_ns is not None and ready_ns is not None
                                      and occurred_ns <= ready_ns),
            "old_env_kept_at": "/workspace/mnt/sppro/yhzhang91/recycle_bin/rlrobot_overlay_20260929_143331"}


WINDOW_SELFTEST_DIR = ROOT / "runs" / "infra" / "c_env_manifest_selftest"


def _venv_window_selftest(tmp_root: Path | None = None) -> dict[str, Any]:
    """窗口判据的**合成**自测：证明它既能取对同源证据，也**能拒绝**跨 venv 的证据。

    三个合成 venv（写在 C 自己的目录下，数字无物理意义，ADR-C-007）：
    ① 有 `.persist_meta.json` ⇒ 必须走 persist_meta，且 ready = created + elapsed_s；
    ② 没有 meta、只有 pyvenv.cfg + dist-info ⇒ 必须回退到 venv_self_evidence 且窗口不倒置；
    ③ 有一份**描述别的 venv** 的历史 manifest ⇒ 必须出现在 `rejected_sources` 里、
       且窗口值**不等于**那份 manifest 里的值（这一支就是 C-F2 的反例证明）。
    再加一支：④ meta 里 elapsed_s 为负 ⇒ 窗口倒置 ⇒ `window_consistent=false`（判据能红）。
    """
    root = Path(tmp_root or WINDOW_SELFTEST_DIR)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    def _mk(name: str, *, cfg: str, meta: str | None = None,
            dist_mtime: int | None = None) -> Path:
        d = root / name
        (d / "bin").mkdir(parents=True, exist_ok=True)
        (d / "pyvenv.cfg").write_text(cfg, encoding="utf-8")
        (d / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        sp = d / "lib" / "python3.11" / "site-packages" / "fake-1.0.dist-info"
        sp.mkdir(parents=True, exist_ok=True)
        (sp / "METADATA").write_text("Name: fake\nVersion: 1.0\n", encoding="utf-8")
        if dist_mtime is not None:
            os.utime(sp.parent, ns=(dist_mtime, dist_mtime))
            os.utime(d / "pyvenv.cfg", ns=(dist_mtime - 600_000_000_000,
                                            dist_mtime - 600_000_000_000_000))
        if meta is not None:
            (d / PERSIST_META_NAME).write_text(meta, encoding="utf-8")
        return d

    cfg = ("home = /opt/conda/bin\ninclude-system-site-packages = false\nversion = 3.11.9\n"
           "executable = /opt/conda/bin/python3.11\ncommand = fake\n")
    v1 = _mk("synthetic_persist", cfg=cfg, meta=json.dumps(
        {"created_at": "2026-09-29T14:24:52+0800", "elapsed_s": 223.8, "n_pins": 82}))
    w1 = _venv_window(v1)
    rows.append({"case": "① .persist_meta.json 存在 ⇒ 走 persist_meta，ready = created + elapsed",
                 "expected": {"source_kind": "persist_meta", "window_consistent": True,
                              "occurred_at": "2026-09-29T14:24:52+08:00",
                              "ready_at": "2026-09-29T14:28:35+08:00"},
                 "got": {k: w1[k] for k in ("source_kind", "window_consistent",
                                            "occurred_at", "ready_at")}})

    v2 = _mk("synthetic_no_meta", cfg=cfg, dist_mtime=1_790_660_000_000_000_000)
    w2 = _venv_window(v2)
    rows.append({"case": "② 没有 meta ⇒ 回退到 venv 自己的文件系统痕迹，窗口不倒置",
                 "expected": {"source_kind": "venv_self_evidence", "same_source": True,
                              "window_consistent": True},
                 "got": {k: w2[k] for k in ("source_kind", "same_source", "window_consistent")}})

    other_manifest = root / "archived_describing_another_venv.json"
    other_manifest.write_text(json.dumps({
        "venv": {"path": "/root/venvs/rlrobot", "realpath": "/some/other/venv",
                 "created_at": "2026-09-29T10:45:56+08:00",
                 "created_at_ns": 1_790_649_956_000_000_000,
                 "ready_at": "2026-09-29T10:57:19+08:00",
                 "ready_at_ns": 1_790_650_639_000_000_000,
                 "pyvenv_cfg": {"home": "/opt/conda/bin",
                                "include-system-site-packages": "true",
                                "version": "3.11.9"}}}, ensure_ascii=False), encoding="utf-8")
    w3 = _venv_window(v2, archived_manifest=other_manifest)
    rejected = bool(w3["rejected_sources"])
    not_adopted = w3["occurred_ns"] != 1_790_649_956_000_000_000
    rows.append({"case": "③ 历史 manifest 描述的是**别的** venv ⇒ 必须拒绝（C-F2 的反例证明）",
                 "expected": {"rejected": True, "adopted_other_venv_window": False},
                 "got": {"rejected": rejected, "adopted_other_venv_window": not not_adopted,
                         "rejected_sources_head": (w3["rejected_sources"] or [None])[0]}})

    v4 = _mk("synthetic_inverted", cfg=cfg, meta=json.dumps(
        {"created_at": "2026-09-29T14:24:52+0800", "elapsed_s": -100.0}))
    w4 = _venv_window(v4)
    rows.append({"case": "④ elapsed_s 为负 ⇒ 窗口倒置 ⇒ 判据必须红（window_consistent=false）",
                 "expected": {"window_consistent": False},
                 "got": {"window_consistent": w4["window_consistent"],
                         "occurred_at": w4["occurred_at"], "ready_at": w4["ready_at"]}})

    for row in rows:
        exp, got = row["expected"], row["got"]
        row["match"] = all(got.get(k) == v for k, v in exp.items())
    return {"ran": True, "rows": rows, "all_match": all(r["match"] for r in rows),
            "synthetic_root": str(root.relative_to(ROOT)) if root.is_relative_to(ROOT) else str(root),
            "c_synthetic": {"physical_meaning": False,
                            "note": "合成 venv 与合成时刻，数字无物理意义（ADR-C-007）；"
                                    "只用于证明窗口判据的四个分支各自能红/能绿。"},
            "teeth": ("③ 与 ④ 是**反向**用例：③ 证明跨 venv 的证据会被拒（不是恒接受），"
                      "④ 证明倒置窗口会被判红（不是恒绿）。")}


def _fingerprint_diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """两次指纹的差异，**排除易变字段**（`at` 是打指纹的时刻，两次必然不同）。

    不排除就是恒红：本轮 14:52 实测 `changed_fields=['at']` ⇒ `env_fully_restored` 永远 false，
    而恒红的判据等于没有判据（裁定 27.1 同型）。排除项写进产物，不藏在代码里。
    """
    return sorted(k for k in set(before) | set(after)
                  if k not in FINGERPRINT_VOLATILE_FIELDS and before.get(k) != after.get(k))


def _snapshot_consistency_selftest() -> dict[str, Any]:
    """快照自洽判据的**双向**自测：既不能恒红（只改时间戳不算换环境），也不能恒绿（改身份必须红）。"""
    base = {"sys_prefix": "/root/venvs/rlrobot", "sys_base_prefix": "/opt/conda",
            "realpath_executable": "/opt/conda/bin/python3.11",
            "venv_realpath": "/x/.codex-persist/envs/rlrobot", "venv_is_symlink": True,
            "pyvenv_cfg_sha256_12": "4bcf8f6c23fc", "bin_python_ctime_ns": 1790662868000000000,
            "at": "2026-09-29T14:52:55+08:00"}
    only_clock_moved = dict(base, at="2026-09-29T15:10:00+08:00")
    venv_swapped = dict(base, venv_realpath="/x/.codex-persist/envs/rlrobot_NEW",
                        pyvenv_cfg_sha256_12="deadbeef0000",
                        at="2026-09-29T15:10:00+08:00")
    mode_flipped = dict(base, sys_prefix="/other/venv", at="2026-09-29T15:10:00+08:00")
    cases = (
        ("完全相同", base, dict(base), []),
        ("只有打指纹的时刻变了（易变字段）", base, only_clock_moved, []),
        ("脚下的 venv 被换成另一份（14:21 真发生过）", base, venv_swapped,
         ["pyvenv_cfg_sha256_12", "venv_realpath"]),
        ("sys.prefix 变了（模式从 system-site 翻成 clean 会带出这一项）", base, mode_flipped,
         ["sys_prefix"]),
    )
    rows = [{"label": label, "expected_changed": exp, "got_changed": _fingerprint_diff(b, a),
             "expected_consistent": not exp}
            for label, b, a, exp in cases]
    for row in rows:
        row["match"] = row["got_changed"] == row["expected_changed"]
    return {"ran": True, "rows": rows, "all_match": all(r["match"] for r in rows),
            "volatile_fields_excluded": list(FINGERPRINT_VOLATILE_FIELDS),
            "teeth": ("两个方向都有牙：① 只改 `at` ⇒ 判**自洽**（否则本条恒红，14:52 的实测缺陷）；"
                      "② 改 venv_realpath / pyvenv_cfg_sha / sys_prefix ⇒ 判**不自洽**（否则恒绿）。"),
            "note": "合成指纹，数字无物理意义（ADR-C-007）；结构与 `_interpreter_fingerprint` 一致。",
            "c_synthetic": {"physical_meaning": False}}


def _static_import_surface(paths: Sequence[str], names: Sequence[str]) -> dict[str, Any]:
    """AST 静态扫：这些脚本里有没有 import 目标包（**含函数内 import**，不只顶层）。"""
    import ast                                                 # noqa: PLC0415
    wanted = set(names)
    rows: dict[str, Any] = {}
    for rel in paths:
        path = ROOT / rel
        if not path.exists():
            rows[rel] = {"exists": False, "hits": [], "note": "文件不存在（如实报，不静默跳过）"}
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            rows[rel] = {"exists": True, "parse_error": str(exc), "hits": []}
            continue
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                hits += [{"line": node.lineno, "stmt": f"import {alias.name}"}
                         for alias in node.names if alias.name.split(".")[0] in wanted]
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in wanted:
                    hits.append({"line": node.lineno, "stmt": f"from {node.module} import ..."})
        rows[rel] = {"exists": True, "sha256_12": _sha12(path), "hits": hits}
    return {"method": "ast.walk（覆盖模块级与函数级 import）", "packages": list(names),
            "files": rows,
            "any_hit": any(r["hits"] for r in rows.values()),
            "scope_note": ("只扫**本仓脚本的直接 import 面**。传递依赖（本仓脚本 import 的第三方包"
                           "又 import 了 imageio）不在静态扫描里 —— 那部分由 dynamic 实测覆盖"
                           "（见 `dynamic`，来源是落盘产物，不是叙述）。")}


def _measure_import_surface(python: str, modules: Sequence[str], *, out_path: Path) -> dict[str, Any]:
    """动态实测：在指定解释器里逐个 import，看目标包**是否被拉进 `sys.modules`**（含传递依赖）。

    产物落盘后由 `_ruling_34_1` 只读引用（manifest 里不重跑：跑一次要起 9 个子进程）。

    **口径禁令（裁定 36.4，增补十三 §47）**：本探针**不得**为了「测冷导入」去逐出页缓存
    （`posix_fadvise(DONTNEED)` / `drop_caches`）—— B 与 C 此刻正在用同一个解释器跑判据，
    逐出会拖慢它们并污染耗时类观测。本探针只判「有没有被 import」，**不测耗时**，
    所以既不需要也不允许逐出。冷导入基线由 A 按自己的口径测（只逐出 A 自己的 venv）。
    """
    code_template = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import importlib\n"
        "err = None\n"
        "try:\n"
        "    importlib.import_module(MOD)\n"
        "except Exception as exc:\n"
        "    err = f'{type(exc).__name__}: {exc}'\n"
        "print(json.dumps({'import_error': err,\n"
        "                  'loaded': {p: [k for k in sys.modules if k.split('.')[0] == p]\n"
        "                             for p in PKGS}}))\n")
    rows: dict[str, Any] = {}
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", MUJOCO_GL="egl", OMP_NUM_THREADS="2")
    for mod in modules:
        code = code_template.replace("MOD", repr(mod)).replace(
            "PKGS", repr(list(RULING_34_1_PACKAGES)))
        try:
            proc = subprocess.run([python, "-c", code], capture_output=True, text=True,
                                  timeout=600, cwd=str(ROOT), env=env)
        except Exception as exc:                               # noqa: BLE001
            rows[mod] = {"probed": False, "error": f"{type(exc).__name__}: {exc}"}
            continue
        payload = None
        for line in (proc.stdout or "").strip().splitlines()[::-1]:
            try:
                payload = json.loads(line)
                break
            except Exception:                                  # noqa: BLE001
                continue
        if payload is None:
            rows[mod] = {"probed": False, "rc": proc.returncode,
                         "error": (proc.stderr or "").strip().splitlines()[-1:] or "no json on stdout"}
            continue
        loaded = {p: sorted(v) for p, v in (payload.get("loaded") or {}).items() if v}
        rows[mod] = {"probed": True, "rc": proc.returncode,
                     "import_error": payload.get("import_error"),
                     "loaded": loaded,
                     "hit": sorted(loaded)}
    payload = {
        "kind": "c_ruling_34_1_import_surface",
        "measurement_kind": "real",
        "measured_at": _now_iso(),
        "measured_by": "scripts/c_env_manifest.py --measure-import-surface（C 线，只读实测）",
        "interpreter": {"path": python, "realpath": os.path.realpath(python)},
        "method": ("每个模块一个子进程：import 之后回显 `sys.modules` 里以 imageio / uv 开头的键。"
                   "覆盖**传递依赖**（静态 AST 扫不到那一层）。"),
        "packages": list(RULING_34_1_PACKAGES),
        "act_chain": {m: r for m, r in rows.items() if m != UPSTREAM_REFERENCE_ENTRY},
        "upstream_reference": {m: r for m, r in rows.items() if m == UPSTREAM_REFERENCE_ENTRY},
        "why_upstream_separate": ("`lerobot.scripts.lerobot_train` 是**上游官方入口**，不在本仓 48 臂"
                                  "链路上（`scripts/build_lerobot_act_dataset.py` 的 docstring 明写"
                                  "官方 lerobot_train 读不了本仓导出格式；installer 只用它的 `--help` "
                                  "当安装闸）。它与 ACT 链路**分开报**，不参与裁定 34.1 的可红条件判定"
                                  "（混算就是裁定 31.3 / 33.4 那类跨对象混算）。"),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _ruling_34_1(static_scan: dict[str, Any], dynamic: dict[str, Any] | None,
                 lock_diffs: dict[str, Any]) -> dict[str, Any]:
    """裁定 34.1（增补十一 §36）：3 处 lock 差异**放行**，但豁免是按包按链路授的，且有可红条件。

    C 的角色：只**实测**那条可红条件（imageio / uv 在不在 48 臂链路的 import 面），
    不解释、不改判。实测为否 ⇒ 裁定有效、差异不再阻 A 线；实测为真 ⇒ 裁定自动作废、
    差异回到阻塞项（本函数把这两种结果都写成机器可读的 `blocked`）。
    """
    act_rows = (dynamic or {}).get("act_chain") or {}
    dynamic_hits = sorted({p for row in act_rows.values() for p in (row.get("hit") or [])})
    static_hits = sorted({h["stmt"].split()[1].split(".")[0]
                          for row in static_scan["files"].values() for h in row["hits"]})
    triggered = bool(static_scan["any_hit"] or dynamic_hits)
    differing = sorted(name for name, diff in lock_diffs.items()
                       if diff.get("comparable") and not diff.get("identical"))
    return {
        "ruling": "裁定 34.1（增补十一 §36）+ 裁定 37.3 的边界收窄（增补十四 §52）",
        "boundary_narrowed_by_37_3": ("裁定 34.1 覆盖的是**本仓 48 臂 / ACT 链路**；凡是用上游 "
                                      "`lerobot.scripts.lerobot_train` **实跑**的训练（含 A 的 smoke S2 "
                                      "「官方 ACT 训练 + CUDA 50 步」这类）**不在豁免范围内**："
                                      "那条链路上 imageio 2.37.4→2.38.0 要么另证不材料，要么重新报 D。"
                                      "**引用 裁定 34.1 时必须带上这条边界**（按包按链路，不按次）。"),
        "boundary_evidence": ("本 manifest 的 `void_condition_measured.dynamic.upstream_reference_"
                              "excluded` 实测到上游入口的 import 闭包里确有 imageio（18 个子模块），"
                              "而本仓 8 个 ACT 链路脚本全部 `hit=[]` ⇒ 两边分开报，不混算。"),
        "ruling_summary": ("3 处 lock 差异（ImageIO 2.37.4→2.38.0 ×2、uv 0.12.19→0.12.17 ×1）"
                           "**不构成**跨断点复现的障碍；但豁免是**按包按链路**授的，不是按次授的。"),
        "void_condition": ("若 imageio 或 uv **确实**出现在 48 臂链路（任一 ACT 脚本或 "
                           "summarize_lerobot_act_arms.py 的 import 面）⇒ 裁定自动作废，"
                           "3 处差异重新变成阻塞项，A 的相关产物要按新环境重跑。"),
        "void_condition_measured": {
            "static": {"any_hit": static_scan["any_hit"], "hits": static_hits,
                       "n_files": len(static_scan["files"]),
                       "files": sorted(static_scan["files"])},
            "dynamic": {
                "available": dynamic is not None,
                "artifact": (_file_evidence(IMPORT_SURFACE_ARTIFACT) if dynamic else None),
                "interpreter": (dynamic or {}).get("interpreter"),
                "measured_at": (dynamic or {}).get("measured_at"),
                "hits": dynamic_hits,
                "per_module": {m: {"hit": r.get("hit"), "import_error": r.get("import_error")}
                               for m, r in act_rows.items()},
                "upstream_reference_excluded": (dynamic or {}).get("upstream_reference"),
                "how_to_remeasure": ("CUDA_VISIBLE_DEVICES=\"\" MUJOCO_GL=egl "
                                     "<lerobot_eval>/bin/python scripts/c_env_manifest.py "
                                     "--measure-import-surface"),
            },
            "triggered": triggered,
            "not_measured_note": (None if dynamic is not None else
                                  "动态那一层**没测**（产物不在）⇒ 只有静态结论，"
                                  "不足以支撑「裁定有效」；先跑 --measure-import-surface。"),
        },
        "adjudicated_differences": [
            {"lock": name, "differences": lock_diffs[name]["differences"],
             "explained_by": "A（docs/a_env_rebuild_acceptance_20260929.md §3.2）",
             "ruled_by": "D（裁定 34.1）",
             "exemption_scope": "按包按链路：只豁免 imageio / uv 这两个包在 48 臂链路上的差异",
             "new_artifacts_must_echo": ("新训练/新评测的产物必须回显**新 lock 的 sha256**"
                                         "（裁定 34.1 第 5 条）")}
            for name in differing],
        "blocked": bool(triggered),
        "blocked_reason": (
            "可红条件**已触发**：imageio/uv 出现在 ACT 链路 import 面 ⇒ 裁定 34.1 自动作废，"
            "3 处差异回到阻塞项。" if triggered else
            "可红条件实测**未触发**（静态 0 命中 + 动态 sys.modules 0 命中）⇒ 裁定 34.1 有效，"
            "3 处差异不再阻 A 线；但豁免按包按链路，且新产物必须回显新 lock 的 sha256。"),
        "c_role": "C 只实测可红条件，不解释、不改判（解释权归 A，裁定权归 D）。",
    }


def _excluded_by_design_probe(interpreter: str, *, venv_clean: bool) -> dict[str, Any]:
    """clean（自足）venv 里 `jax` / `jaxlib` / `tensorflow` **必须不可导入**（增补十 §34-C③）。

    这是设计意图（persistent lock 头部 `excluded=jax,jaxlib`；conda 的 jax/tf 是 09-24 那串
    ImportError 的污染源），不是缺口。所以判据是**反向**的：在 clean venv 里探到可导入
    ⇒ 说明 base 泄漏进来了（自足性不成立）⇒ 红。system-site venv 里可导入是预期，不判红。
    """
    rows = {name: _probe_import(name, interpreter) for name in EXCLUDED_BY_DESIGN}
    importable = sorted(n for n, r in rows.items() if r.get("importable"))
    if venv_clean:
        status = "ok" if not importable else "base_leak"
        expectation = "clean venv ⇒ 三者都**不可**导入（可导入 = base 泄漏 = 自足性不成立）"
    else:
        status = "ok"
        expectation = "system-site venv ⇒ 可导入是预期（从 base 继承），不判红"
    return {"packages": rows, "importable": importable, "venv_clean": venv_clean,
            "expectation": expectation, "status": status,
            "failed": importable if venv_clean else [],
            "authority": ("requirements.persistent.lock.txt 头部 `excluded=jax,jaxlib` + "
                          "D 的 verification.json（`import jax / import tensorflow 均 "
                          "ModuleNotFoundError（这是设计意图）`）+ 增补十 §34-C③"),
            "teeth": ("判据是反向的：clean venv 里探到 jax 可导入 ⇒ status=base_leak ⇒ "
                      "env_fully_restored=false。恒绿的写法（「不可导入就算过」而不看 venv 类型）"
                      "会在 system-site venv 上误报，恒红的写法会在 clean venv 上永远红。")}

def _resolve_venv(spec: dict[str, Any]) -> dict[str, Any]:
    """把一个环境规格解析成**此刻真实存在的**解释器路径（找不到就如实说找不到）。

    候选按顺序试：① 环境变量覆写（A 用 installer 的 `VENV=` / `EVAL_VENV=` 覆写到持久目录，
    C 的探针必须能跟着指过去，否则装好了也探不到）；② `candidates` 里的路径
    （`/root/venvs/*` 与 `.codex-persist/envs/*` —— 裁定 32.3 之后 venv 建在 NFS 上，
    `/root/venvs/` 下只是符号链接）。
    """
    override = os.environ.get(spec["env_override"]) if spec.get("env_override") else None
    candidates = ([override] if override else []) + list(spec.get("candidates") or [spec["path"]])
    resolved, resolved_from = None, None
    for idx, cand in enumerate(candidates):
        if cand and Path(cand).is_dir():
            resolved = Path(cand)
            resolved_from = (f"env:{spec['env_override']}" if override and idx == 0
                             else f"candidate[{idx}]")
            break
    path = resolved if resolved is not None else Path(candidates[0])
    python = path / "bin" / "python"
    real = os.path.realpath(str(path))
    return {"role": spec.get("role"), "requested": spec["path"], "candidates": candidates,
            "resolved_from": resolved_from, "path": str(path), "exists": path.is_dir(),
            "python": str(python), "python_exists": python.exists(),
            "is_symlink": path.is_symlink(), "realpath": real,
            "on_persistent_nfs": real.startswith(str(PERSISTENT_ENV_ROOT)),
            # 整个 venv 不在 ⇒ 是**解释器**缺失，不是「某个模块没装」。
            # 这两个状态混在一起，就会把「A 被阻」读成「B 没建好环境」（裁定 31.2 第 1 条）。
            "status": "ok" if python.exists() else "interpreter_missing",
            "observed_at": _now_iso()}


def _semantic_probe(python: str, pins: dict[str, str], *,
                    strict_self_report: Sequence[str] = ("lerobot",)) -> dict[str, Any]:
    """「装了没」类探针一律验**语义值**，不验可导入（裁定 31.2 / DR-012 判据纪律）。

    `import lerobot` 成功是**恒真判据**：lerobot 的 `__version__.py` 就是
    `importlib.metadata.version("lerobot")`，从落后 488 个 commit 的 checkout 源装成 0.1.0 时
    import 照样成功（B 只读实测，见 pin 文档 §4）。所以这里断言版本号 + 回显安装来源，
    子进程只**回显实测值**，判定放在父进程（可被 `--check` 引用、可单测）。
    """
    if not Path(python).exists():
        return {"ran": False, "status": "interpreter_missing", "modules": {},
                "reason": (f"解释器不存在：{python}。**不是** module_missing —— 整个 venv 不在，"
                           "所以缺口的准确表述是「环境需要按 installer 重建」，"
                           "不是「rlrobot 里少一个包」（裁定 31.2 / DR-012）。")}
    code = (
        "import importlib, importlib.metadata as md, json, pathlib, sys\n"
        "want = json.loads(sys.argv[1])\n"
        "out = {'python_version': sys.version.split()[0], 'executable': sys.executable,\n"
        "       'prefix': sys.prefix, 'base_prefix': sys.base_prefix,\n"
        "       'is_venv': sys.prefix != sys.base_prefix, 'modules': {}}\n"
        "for name in want:\n"
        "    row = {}\n"
        "    try:\n"
        "        mod = importlib.import_module(name)\n"
        "        row['importable'] = True\n"
        "        row['module_version'] = getattr(mod, '__version__', None)\n"
        "        row['module_file'] = getattr(mod, '__file__', None)\n"
        "    except Exception as exc:\n"
        "        row['importable'] = False\n"
        "        row['import_error'] = (type(exc).__name__ + ': ' + str(exc))[:300]\n"
        "    try:\n"
        "        dist = md.distribution(name)\n"
        "        row['dist_version'] = dist.version\n"
        "        dpath = pathlib.Path(str(dist._path))\n"
        "        row['dist_info'] = str(dpath)\n"
        "        du = dpath / 'direct_url.json'\n"
        "        row['direct_url'] = json.loads(du.read_text()) if du.exists() else None\n"
        "        inst = dpath / 'INSTALLER'\n"
        "        row['installer'] = inst.read_text().strip() if inst.exists() else None\n"
        "        whl = dpath / 'WHEEL'\n"
        "        row['wheel'] = ([x.strip() for x in whl.read_text().splitlines() if x.strip()]\n"
        "                        if whl.exists() else None)\n"
        "    except Exception as exc:\n"
        "        row['dist_present'] = False\n"
        "        row['dist_error'] = (type(exc).__name__ + ': ' + str(exc))[:200]\n"
        "    out['modules'][name] = row\n"
        "print(json.dumps(out))\n")
    try:
        proc = subprocess.run([python, "-c", code, json.dumps(sorted(pins))],
                              capture_output=True, text=True, timeout=600)
    except Exception as exc:                                   # noqa: BLE001
        return {"ran": False, "status": "probe_error", "modules": {},
                "reason": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return {"ran": False, "status": "probe_error", "modules": {},
                "reason": tail[-1][:300] if tail else "unknown"}
    try:
        raw = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:                                   # noqa: BLE001
        return {"ran": False, "status": "probe_error", "modules": {},
                "reason": f"探针输出不是 JSON（{type(exc).__name__}）"}
    modules: dict[str, Any] = {}
    for name, row in (raw.get("modules") or {}).items():
        expect = pins.get(name)
        check = _version_vs_pin(row.get("module_version"), row.get("dist_version"), expect,
                                strict_self_report=name in strict_self_report)
        observed = row.get("module_version") or row.get("dist_version")
        if not row.get("importable") and not row.get("dist_version"):
            status = "module_missing"
        elif not expect:
            status = "version_unverified"
        elif check["matches"]:
            status = "ok"
        else:
            status = "version_mismatch"
        modules[name] = {**row, "expected_version": expect, "observed_version": observed,
                         "version_check": check,
                         "version_matches_pin": check["matches"],
                         "install_source": _install_source(row), "status": status}
    bad = sorted(n for n, m in modules.items() if m["status"] != "ok")
    headline = modules.get("lerobot") or {}
    return {"ran": True, "python_version": raw.get("python_version"),
            "executable": raw.get("executable"), "prefix": raw.get("prefix"),
            "is_venv": raw.get("is_venv"), "modules": modules,
            "status": "ok" if not bad else "not_ok",
            "not_ok": bad,
            "lerobot_version": headline.get("observed_version"),
            "lerobot_version_matches_pin": headline.get("version_matches_pin"),
            "lerobot_self_report_equals_pin": ((headline.get("module_version") is not None)
                                               and headline.get("module_version")
                                               == headline.get("expected_version")),
            "lerobot_assertion": ("裁定 31.2 第 2 条①：断言 `lerobot.__version__ == pin`"
                                  "（strict：不容 local segment），并回显 dist 版本与安装来源；"
                                  "`import lerobot` 成功**不算**通过。"),
            "red_condition": ("任一包 status != ok 即红：`module_missing`（没装）／"
                              "**`version_mismatch`（装了但版本不符 pin —— 这一档才是重点，"
                              "因为 import 照样成功，只验可导入的探针会放它过去）**／"
                              "`version_unverified`（没有 pin 可比）。"
                              "红 ⇒ env_fully_restored=false 并点名到包。")}


def _install_source(row: dict[str, Any]) -> dict[str, Any]:
    """回显**安装来源**（裁定 31.2 第 2 条②）：PyPI/镜像 wheel 还是源装（+ commit）。

    判据是 dist-info 里的实测文件，不是猜：`direct_url.json` 只在「本地目录 / VCS / editable」
    安装时才写；从索引装 wheel 时它不存在，`INSTALLER` 给出安装器（pip / uv），
    `WHEEL` 给出 tag。源装还会带 `vcs_info.commit_id` —— 那正是能区分
    「0.4.4 的 wheel」与「落后 488 个 commit 的 checkout」的东西。
    """
    direct = row.get("direct_url")
    if isinstance(direct, dict):
        vcs = direct.get("vcs_info") or {}
        dir_info = direct.get("dir_info") or {}
        return {"kind": "vcs_source" if vcs else "local_source_dir",
                "url": direct.get("url"), "commit": vcs.get("commit_id"),
                "vcs": vcs.get("vcs"), "editable": dir_info.get("editable"),
                "installer": row.get("installer"),
                "derived_by": "dist-info/direct_url.json 存在 ⇒ 不是从索引装的 wheel"}
    wheel = row.get("wheel") or []
    tag = next((x.split(":", 1)[1].strip() for x in wheel if x.startswith("Tag:")), None)
    return {"kind": "index_wheel", "installer": row.get("installer"), "wheel_tag": tag,
            "dist_info": row.get("dist_info"), "commit": None,
            "derived_by": ("没有 direct_url.json（pip/uv 只在本地目录或 VCS 安装时写它）+ "
                           f"INSTALLER={row.get('installer')!r} + WHEEL Tag={tag!r} ⇒ "
                           "从索引装的 wheel；索引地址见 `lerobot.pin.values.INDEX`")}


def _pin_authority() -> dict[str, Any]:
    """lerobot 的权威 pin：**三个独立来源**互校（不复制判据，也不让 C 的文件成为 pin 的源）。

    ① B 的 pin 文档（DR-012，唯一权威）；② installer 的缺省值（B 的写入边界，解析不抄写）；
    ③ 0928 的 lock（48 臂权威表当初跑的环境）。三者不一致 ⇒ 报出来，不静默挑一个。
    """
    installer = _installer_pins(LEROBOT_INSTALLER)
    doc_value, doc_sha = None, _sha12(LEROBOT_PIN_DOC)
    if LEROBOT_PIN_DOC.exists():
        found = re.findall(r"lerobot==([0-9][0-9A-Za-z.\-+]*)",
                           LEROBOT_PIN_DOC.read_text(encoding="utf-8"))
        doc_value = sorted(set(found))[0] if found else None
    lock_act = _expected_pins(LEROBOT_LOCK_DIR / "requirements.lock.txt", ("lerobot",))
    values = {"pin_doc": doc_value, "installer_default": installer.get("LEROBOT"),
              "lock_0928": lock_act.get("lerobot")}
    agree = len({v for v in values.values() if v}) == 1 and all(values.values())
    return {"expected_lerobot": values["pin_doc"] or values["installer_default"],
            "sources": values, "all_agree": bool(agree),
            "pin_doc": (str(LEROBOT_PIN_DOC.relative_to(ROOT)) if LEROBOT_PIN_DOC.exists() else None),
            "pin_doc_sha256_12": doc_sha,
            "authority": "DR-012 / B 的 docs/lerobot_env_reinstall_pin_20260929.md（照抄，不顺手升级）",
            "index": installer.get("INDEX"), "torch": installer.get("TORCH"),
            "torchvision": installer.get("TORCHVISION"), "base_py": installer.get("BASE_PY"),
            "note": ("三个来源不一致 ⇒ `all_agree=false`，此时探针的期望值取 pin 文档，"
                     "并把不一致本身报出来（不静默挑一个）。")}


def _expected_pins(lock_path: Path, names: Sequence[str]) -> dict[str, str]:
    """从一份 lock 里**解析**出要断言的 pin（写死在 C 的文件里就等于复制了第二份判据）。"""
    pins = _parse_lock(lock_path) if lock_path.exists() else {}
    return {n: pins[n] for n in names if n in pins}


def _pyvenv_assertions(path: Path, *, base_py: str | None,
                       expect_system_site_packages: bool | None,
                       expect_source: str = "") -> dict[str, Any]:
    """裁定 32.3 第 2 条：base 解释器路径与版本必须**断言**，不能只记观测值。

    venv 的 shebang 与 `pyvenv.cfg.home` 都是**绝对路径** ⇒ 换容器后若 base python 不在
    `/opt/conda/bin` 或不是 3.11.x，持久 venv 直接坏掉（而它看起来「还在」）。
    """
    cfg_path = path / "pyvenv.cfg"
    cfg: dict[str, str] = {}
    if cfg_path.exists():
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip()
    expected_minor = None
    if base_py:
        m = re.search(r"python(\d+\.\d+)$", str(base_py))
        expected_minor = m.group(1) if m else None
    home = Path(cfg["home"]) if cfg.get("home") else None
    exe = Path(cfg["executable"]) if cfg.get("executable") else None
    ssp = cfg.get("include-system-site-packages")
    rows = [
        ("pyvenv.cfg 存在", cfg_path.exists(), str(cfg_path)),
        ("home 目录存在（换容器后 base python 不在这里 ⇒ 持久 venv 直接坏掉）",
         bool(home and home.is_dir()), cfg.get("home")),
        ("executable 存在", bool(exe and exe.exists()), cfg.get("executable")),
        (f"version 的 major.minor == BASE_PY 的 {expected_minor}（从 installer 解析，不写死）",
         (None if not expected_minor else str(cfg.get("version", "")).startswith(expected_minor)),
         cfg.get("version")),
    ]
    if expect_system_site_packages is not None:
        rows.append(("include-system-site-packages 与**落盘声明**一致"
                     f"（期望 {str(expect_system_site_packages).lower()}"
                     f"{('，来源 ' + expect_source) if expect_source else ''}）",
                     ssp == str(expect_system_site_packages).lower(), ssp))
    return {"cfg": cfg, "expected_minor": expected_minor,
            "expected_system_site_packages": expect_system_site_packages,
            "expected_source": expect_source, "rows": rows,
            "all_pass": all(bool(ok) for _name, ok, _got in rows),
            "failed": [name for name, ok, _got in rows if not ok],
            "note": ("裁定 32.3 第 2 条：这些是**断言**不是观测 —— 任一不过 ⇒ "
                     "env_fully_restored=false 并点名。")}


def _inherited_assertion(interpreter: str, *, declared_mode: str | None = None,
                         venv_type: str | None = None, applies: bool = True,
                         described_realpath: str | None = None) -> dict[str, Any]:
    """裁定 32.3 第 1 条：这批包从**观测**改成**断言**（基线见 `inherited_baseline.json`）。

    14:2x 起 rlrobot 迁到 NFS 且改成**自足**模式（不带 --system-site-packages），
    这批包不再是「继承来的」而是**装在 venv 里**的。所以逐包回显 dist-info 的位置
    （`venv_local` / `inherited_from_base`，实测），并按声明的模式断言位置对不对 ——
    模式换了却沿用旧标签，就是裁定 12 点名的那类「标签说谎」。
    """
    rows_snapshot = _dist_rows(interpreter, INHERITED_PACKAGES)
    locations = {name: {k: v for k, v in (rows_snapshot.get(name) or {}).items() if k != "error"}
                 or {"present": False} for name in INHERITED_PACKAGES}
    versions = {name: (rows_snapshot.get(name) or {}).get("version") for name in INHERITED_PACKAGES}
    measured_in = {"interpreter": interpreter,
                   "sys_prefix": _dist_snapshot(interpreter, INHERITED_PACKAGES).get("sys_prefix"),
                   "realpath_executable": _dist_snapshot(
                       interpreter, INHERITED_PACKAGES).get("realpath_executable"),
                   "is_this_process": _dist_snapshot(
                       interpreter, INHERITED_PACKAGES).get("is_this_process"),
                   "rule": ("裁定 33.4 一般规则：版本与位置都在**被描述的解释器**里取（子进程实测），"
                            "不用本进程的 importlib.metadata —— 否则 `--venv` 指到别处时，"
                            "标签说的是那个 venv、数字却是本脚本自己的解释器。")}
    if not applies:
        # 基线描述的是 rlrobot；被描述的是别的 venv ⇒ **不适用**（观测照记，判定不做）。
        subject = None
        if INHERITED_BASELINE.exists():
            try:
                subject = (json.loads(INHERITED_BASELINE.read_text(encoding="utf-8"))
                           .get("interpreter"))
            except Exception:                                  # noqa: BLE001
                subject = None
        return {"asserted": False, "status": "not_applicable",
                "reason": (f"inherited_baseline.json 的 interpreter 是 rlrobot"
                           f"（{subject}），被描述的是 {described_realpath} ⇒ "
                           "拿它当分母就是跨对象混算（裁定 33.4）。观测值照实回显，不做判定。"),
                "declared_mode": declared_mode, "venv_type": venv_type,
                "versions": versions, "locations": locations, "measured_in": measured_in,
                "failed": [], "rows": [{"package": n, "observed": versions[n],
                                        "venv_local": (locations.get(n) or {}).get("venv_local")}
                                       for n in INHERITED_PACKAGES]}
    if not INHERITED_BASELINE.exists():
        return {"asserted": False, "status": "baseline_absent",
                "reason": f"基线文件不存在：{INHERITED_BASELINE}（断言无从比起 ⇒ 不当通过读）",
                "versions": versions, "locations": locations, "measured_in": measured_in,
                "venv_type": venv_type}
    baseline = json.loads(INHERITED_BASELINE.read_text(encoding="utf-8"))
    expected = baseline.get("packages") or {}
    rows, bad, mode_bad = [], [], []
    for name in INHERITED_PACKAGES:
        got = versions[name]
        want = expected.get(name)
        ok = (got == want) if want else None
        loc = locations[name]
        rows.append({"package": name, "baseline": want, "installed": got,
                     "venv_local": loc.get("venv_local"),
                     "inherited_from_base": loc.get("inherited_from_base"),
                     "dist_info": loc.get("dist_info"),
                     "status": ("match" if ok else ("mismatch" if want else "no_baseline"))})
        if not ok:
            bad.append(name)
        if declared_mode == "self_sufficient" and loc.get("present") and not loc.get("venv_local"):
            mode_bad.append(f"{name}（声明自足，实测却来自 base）")
        if declared_mode == "inherit_base" and loc.get("present") and loc.get("venv_local"):
            mode_bad.append(f"{name}（声明继承 base，实测却装在 venv 里）")
    return {"asserted": True, "status": "ok" if not (bad or mode_bad) else "not_ok",
            "declared_mode": declared_mode, "venv_type": venv_type,
            "version_mismatch": bad, "mode_mismatch": mode_bad,
            "locations": locations, "measured_in": measured_in,
            "baseline": _file_evidence(INHERITED_BASELINE),
            "baseline_authority": baseline.get("authority"),
            "baseline_cross_check": baseline.get("cross_check"),
            "interpreter": interpreter, "rows": rows, "failed": bad + mode_bad,
            "versions": versions,
            "note": baseline.get("why"),
            "reading_rule": baseline.get("reading_rule")}


def _lock_diff(old: Path, new: Path) -> dict[str, Any]:
    """两份 lock 的逐行差异（裁定 32.4：差异必须逐条解释并报 D；C 只**实测**，不解释、不裁定）。"""
    if not old.exists() or not new.exists():
        return {"comparable": False,
                "reason": f"缺文件：old={old.exists()} new={new.exists()}"}
    old_pins, new_pins = _parse_lock(old), _parse_lock(new)
    changed = sorted(k for k in set(old_pins) | set(new_pins)
                     if old_pins.get(k) != new_pins.get(k))
    return {"comparable": True,
            "old": _file_evidence(old), "new": _file_evidence(new),
            "identical": not changed,
            "n_differences": len(changed),
            "differences": [{"package": p, "old": old_pins.get(p), "new": new_pins.get(p)}
                            for p in changed],
            "who_explains": "A（裁定 32.4：差异必须逐条解释 —— 哪个包、从什么变到什么、为什么）",
            "who_rules": "D（在 D 裁定之前，A 不得声称任何跨断点的复现）"}



def build_manifest(*, venv: Path, lock: Path, interpreter: str,
                   occurred_at: str | None = None, ready_at: str | None = None,
                   import_surface: dict[str, Any] | None = None,
                   lock_is_default: bool = False) -> dict[str, Any]:
    pyvenv_cfg = venv / "pyvenv.cfg"
    cfg = _parse_pyvenv_cfg(venv)
    venv_python = venv / "bin" / "python"
    venv_identity = _venv_identity(venv)
    # 裁定 33.4（C-F2）：窗口证据必须与**被描述的这个 venv**同源。上一版把 overlay 那份 venv 的
    # ready 时刻（rebuild2.log 的 mtime）喂给了持久 venv 的 created_at ⇒ 窗口倒过来、
    # 断点分类自测 5/6 格不符。现在按 `_venv_window` 的优先级取，并回显被拒绝的证据是谁的。
    window = _venv_window(venv, override_occurred=occurred_at, override_ready=ready_at,
                          archived_manifest=ARCHIVED_MANIFEST_PRE_REBUILD)
    venv_created_ns = window["occurred_ns"]
    venv_ready_ns = window["ready_ns"]
    # 那条**历史**断点（overlay venv 被检修抹掉后 C 在 10:45–10:57 重建）用的是它自己的窗口。
    overlay_window = _historical_window(ARCHIVED_MANIFEST_PRE_REBUILD, REBUILD_DIR / "rebuild2.log",
                                        venv_identity)
    mode_decl = _load_venv_mode_declaration()
    # 裁定 33.4 的同源纪律同样适用于**基线**：`inherited_baseline.json` 描述的是 rlrobot
    # （文件里写死了 `interpreter: /root/venvs/rlrobot/bin/python`）。拿它去断言 lerobot_act
    # 就是又一次跨对象混算（torch 2.6.0+cu124 会被判成「版本不符」的假红）。
    baseline_subject = None
    if INHERITED_BASELINE.exists():
        try:
            baseline_subject = (json.loads(INHERITED_BASELINE.read_text(encoding="utf-8"))
                                .get("interpreter"))
        except Exception:                                      # noqa: BLE001
            baseline_subject = None
    baseline_applies = (venv.name == "rlrobot" or
                        (baseline_subject or "").startswith(str(venv).rstrip("/") + "/"))
    # 同理，默认的 `requirements.lock.txt` 是 **rlrobot** 的门禁产物（28 pin，B 的闸与 C 的
    # `_parse_lock` 都读它）。被描述的 venv 不是 rlrobot 而调用方又没换 lock ⇒ 这条闸
    # **不适用**（拿 rlrobot 的分母去判 lerobot_act，mismatch 是口径不匹配，不是环境缺陷）。
    lock_applies = (not lock_is_default) or venv.name == "rlrobot"
    fp_before = _interpreter_fingerprint(venv)
    # 注意：本函数里曾有**三处**都叫 `pins`（lock 的 pin / lerobot 的语义 pin / installer 的
    # 缺省 pin），后两处会遮蔽第一处 ⇒ `lock.n_pins` 实测回显成 10 而不是 28（14:5x 抓到）。
    # 现在三者分别叫 lock_pins / env_pins / installer_pins，名字不再复用。
    lock_pins = _parse_lock(lock) if lock.exists() else {}
    installed_rows = _dist_rows(interpreter, sorted(lock_pins))
    conformance = []
    for name, pinned in sorted(lock_pins.items(), key=lambda kv: kv[0].lower()):
        installed = (installed_rows.get(name) or {}).get("version")
        conformance.append({
            "package": name, "pinned": pinned, "installed": installed,
            "status": ("missing" if installed is None
                       else ("match" if installed == pinned else "mismatch")),
        })
    status_counts: dict[str, int] = {}
    for row in conformance:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    # --- 探针按**解释器**分组（裁定 31.2 第 1 条）：rlrobot 的 13 项保持 + 两个 lerobot venv ---
    pin_authority = _pin_authority()
    declared = mode_decl.get("declared") or {}
    rlrobot_mode = ((declared.get(venv.name) or {}).get("mode")
                    or (declared.get("rlrobot") or {}).get("mode"))
    inherited_assert = _inherited_assertion(interpreter, declared_mode=rlrobot_mode,
                                            venv_type=venv_identity["venv_type"],
                                            applies=baseline_applies,
                                            described_realpath=venv_identity["realpath"])
    base_py = pin_authority.get("base_py")
    rlrobot_modules = {name: _probe_import(name, interpreter) for name in ALL_PROBE_MODULES}
    rlrobot_group = {
        "role": "C 的只读回归 + robosuite/mujoco 依赖的自检（在被描述的解释器里探）",
        "group_key_is_historical": (venv.name != "rlrobot"),
        "group_key_note": ("键名 `rlrobot` 是 12:14 那版的口径（当时只有 rlrobot 一个分组）。"
                           "本组实际探的是 `probed_in` 那个解释器；被描述的 venv 不是 rlrobot 时，"
                           "这组的 required 判据**不适用**（见 env_fully_restored_conditions）。"
                           if venv.name != "rlrobot" else None),
        "probed_in": interpreter,
        "requested": str(venv), "path": str(venv), "exists": venv.is_dir(),
        "python": interpreter, "python_exists": bool(Path(interpreter).exists()),
        "resolved_from": "--venv / --interpreter 参数",
        "status": "ok" if Path(interpreter).exists() else "interpreter_missing",
        "modules": rlrobot_modules,
        "required_modules": list(PROBE_MODULES),
        "missing_required": [n for n in PROBE_MODULES if not rlrobot_modules[n]["importable"]],
        "probe_kind": "importable（这一组是 C 自己回归的依赖闸，语义值断言见 lerobot 两组）",
        "lerobot_missing_here_is_by_design": not rlrobot_modules["lerobot"]["importable"],
        "design_note": ("`lerobot` 在这个解释器里 MISSING 是**设计如此**（它从不装在 rlrobot 里："
                        "requirements.lock.txt 28 包无它，pin 文档 §1 明写两个独立 venv）⇒ "
                        "**不计入缺口**、不进 required 闸。把这条写清，「A 被阻」才不会被读成"
                        "「B 没建好环境」。lerobot 由下面两个分组在**各自的解释器**里验。"),
        "mode_declared": rlrobot_mode,
        "pyvenv": _pyvenv_assertions(
            venv, base_py=base_py,
            expect_system_site_packages=(
                None if rlrobot_mode is None
                else rlrobot_mode != "self_sufficient"),
            expect_source=f"runs/infra/{REBUILD_DIR.name}/venv_mode_declaration.json"),
    }
    lerobot_groups: dict[str, Any] = {}
    for spec in LEROBOT_ENVS:
        resolved = _resolve_venv(spec)
        is_eval = spec["name"] == "lerobot_eval"
        lock_path = LEROBOT_LOCK_DIR / ("requirements.eval.lock.txt" if is_eval
                                        else "requirements.lock.txt")
        names = LEROBOT_SEMANTIC_PINS + (LEROBOT_EVAL_EXTRA_PINS if is_eval else ())
        env_pins = _expected_pins(lock_path, names)
        if pin_authority.get("expected_lerobot"):
            env_pins["lerobot"] = pin_authority["expected_lerobot"]
        probe = _semantic_probe(resolved["python"], env_pins)
        if not resolved["python_exists"]:
            status = "interpreter_missing"
        elif probe.get("status") == "ok":
            status = "ok"
        else:
            status = probe.get("status") or "probe_error"
        lerobot_groups[spec["name"]] = {
            "role": spec["role"], "expected": spec["expected"],
            "requested": resolved["requested"], "candidates": resolved["candidates"],
            "resolved_from": resolved["resolved_from"], "path": resolved["path"],
            "exists": resolved["exists"], "python": resolved["python"],
            "python_exists": resolved["python_exists"], "is_symlink": resolved["is_symlink"],
            "realpath": resolved["realpath"],
            "on_persistent_nfs": resolved["on_persistent_nfs"],
            "observed_at": resolved["observed_at"], "status": status,
            "pins": {"values": env_pins,
                     "parsed_from": str(lock_path.relative_to(ROOT)) if lock_path.exists() else None,
                     "parsed_from_sha256_12": _sha12(lock_path),
                     "lerobot_pin_authority": pin_authority},
            "semantic_probe": probe,
            "lerobot_version": probe.get("lerobot_version"),
            "lerobot_version_matches_pin": probe.get("lerobot_version_matches_pin"),
            "lerobot_install_source": (probe.get("modules", {}).get("lerobot") or {}).get(
                "install_source"),
            "mode_declared": (declared.get(spec["name"]) or {}).get("mode"),
            "pyvenv": _pyvenv_assertions(
                Path(resolved["path"]), base_py=base_py,
                expect_system_site_packages=(
                    (declared.get(spec["name"]) or {}).get("include_system_site_packages")
                    if (declared.get(spec["name"]) or {}).get("include_system_site_packages")
                    is not None else spec["system_site_packages_expected"]),
                expect_source=(mode_decl.get("path") or "LEROBOT_ENVS 规格")),
            "red_condition": (f"① 解释器不存在 ⇒ status=interpreter_missing（不是 module_missing）；"
                              f"② lerobot.__version__ != {env_pins.get('lerobot')!r} ⇒ "
                              "version_mismatch（**import 成功也算红**）；③ 其余语义 pin 任一不符 ⇒ "
                              "version_mismatch；④ pyvenv 断言任一不过 ⇒ 红。任一红 ⇒ "
                              "env_fully_restored=false 并点名。"),
        }
    probe_groups = {"rlrobot": rlrobot_group, **lerobot_groups}

    # --- 裁定 33.4（C-F1）：blocking 探针按**解释器分工**判定，rlrobot 里的 lerobot 是
    # `not_applicable`（设计如此），不是 `missing`。上一版把它记成 blocking 缺失，
    # 于是**每次**都给一个假红、还顺带把 A 线的复现主张全阻。
    lerobot_rows = {name: g for name, g in lerobot_groups.items()}
    act_group = lerobot_rows.get("lerobot_act") or {}
    eval_group = lerobot_rows.get("lerobot_eval") or {}
    act_version = act_group.get("lerobot_version")
    eval_version = eval_group.get("lerobot_version")
    versions_agree = (act_version is not None and act_version == eval_version)
    blocking_by_interpreter = {
        "rlrobot": {module: {"status": "not_applicable",
                             "reason": ("lerobot 从不装在 rlrobot 里（`requirements.lock.txt` 28 pin "
                                        "无它，pin 文档 §1 明写两个独立 venv）⇒ 这里探不到是"
                                        "**设计如此**，不计入缺口、不进 required 闸、不阻 A 线。"),
                             "observed": rlrobot_modules.get(module)}
                    for module in BLOCKING_PROBE_MODULES},
        "lerobot_act": {module: {"status": ("ok" if act_group.get("semantic_probe", {}).get("status") == "ok"
                                            else "blocking"),
                                 "version": act_version,
                                 "expected": (act_group.get("pins", {}).get("values", {}) or {}).get(module),
                                 "install_source": act_group.get("lerobot_install_source"),
                                 "not_ok": act_group.get("semantic_probe", {}).get("not_ok")}
                        for module in BLOCKING_PROBE_MODULES},
        "lerobot_eval": {module: {"status": ("ok" if eval_group.get("semantic_probe", {}).get("status") == "ok"
                                             else "blocking"),
                                  "version": eval_version,
                                  "expected": (eval_group.get("pins", {}).get("values", {}) or {}).get(module),
                                  "install_source": eval_group.get("lerobot_install_source"),
                                  "not_ok": eval_group.get("semantic_probe", {}).get("not_ok")}
                         for module in BLOCKING_PROBE_MODULES},
    }
    # 扁平视图（对外口径）：13 个 required 模块取**本解释器**的实测行；`lerobot` 那一行取
    # **各自解释器**的语义探针结果（act 为主、eval 并列回显），并写明它在 rlrobot 里 not_applicable。
    probe_flat: dict[str, Any] = {
        name: {**row, "probed_in": "rlrobot（本脚本运行的解释器）",
               "probe_kind": "importable"}
        for name, row in rlrobot_modules.items() if name not in BLOCKING_PROBE_MODULES}
    for module in BLOCKING_PROBE_MODULES:
        probe_flat[module] = {
            "importable": bool(act_group.get("python_exists")) and act_version is not None,
            "version": act_version,
            "error": None if act_version is not None else (
                act_group.get("semantic_probe", {}).get("reason") or "解释器缺失"),
            "probe_kind": "semantic（版本号 + 安装来源；`import` 成功不算过，裁定 31.2）",
            "probed_in": "lerobot_act（官方 ACT 训练/离线审计的解释器）",
            "also_probed_in": {"lerobot_eval": {"version": eval_version,
                                               "status": eval_group.get("status"),
                                               "install_source": eval_group.get("lerobot_install_source")}},
            "both_interpreters_agree": versions_agree,
            "not_applicable_in": {"rlrobot": blocking_by_interpreter["rlrobot"][module]["reason"]},
            "install_source": act_group.get("lerobot_install_source"),
            "matches_pin": act_group.get("lerobot_version_matches_pin"),
            "status": ("ok" if versions_agree and act_group.get("lerobot_version_matches_pin")
                       and eval_group.get("lerobot_version_matches_pin") else "not_ok"),
        }

    # clean（自足）venv 里 jax/jaxlib/tensorflow **不可导入是设计意图**（增补十 §34-C③）
    excluded_by_design = _excluded_by_design_probe(
        interpreter, venv_clean=venv_identity["venv_type"] == "clean")

    manifest: dict[str, Any] = {
        "manifest_kind": "c_env_manifest",
        "generated_at": _now_iso(),
        "generated_by": "scripts/c_env_manifest.py",
        "doc_convention": "docs/lerobot_official_env_manifest_20260924.md（环境路径/记录版本/版本冲突/入口验证）",
        "scope_note": ("只描述**本脚本运行时所用的这个解释器**；不描述其他环境，也不外推到"
                       "「所有 C 线产物都是在这个环境里跑出来的」—— 那要看 verification 一栏的 mtime。"),
        "interpreter": {
            "argv0": sys.argv[0],
            "sys_executable": sys.executable,
            "realpath": os.path.realpath(sys.executable),
            "version": sys.version.split()[0],
            "version_full": sys.version.replace("\n", " "),
            "requested_venv": str(venv),
            # venv 用 --system-site-packages 建、bin/python 又是符号链接 ⇒ realpath 会指回
            # base 解释器。判「在不在这个 venv 里」要看 sys.prefix，不是 realpath。
            "sys_prefix": sys.prefix, "sys_base_prefix": sys.base_prefix,
            "is_venv": sys.prefix != sys.base_prefix,
            "site_packages": [str(x) for x in site.getsitepackages()],
            "runs_inside_requested_venv": (
                os.path.realpath(sys.prefix) == os.path.realpath(str(venv)) if venv else False),
            "cwd": os.getcwd(),
        },
        "platform": {"platform": platform.platform(), "machine": platform.machine(),
                     "python_implementation": platform.python_implementation()},
        "venv": {
            "path": str(venv), "exists": venv.is_dir(),
            "python_exists": venv_python.exists(),
            "created_at": _iso_ns(venv_created_ns), "created_at_ns": venv_created_ns,
            "ready_at": _iso_ns(venv_ready_ns), "ready_at_ns": venv_ready_ns,
            "window": window,
            "is_symlink": venv.is_symlink(),
            "realpath": os.path.realpath(str(venv)),
            "on_persistent_nfs": os.path.realpath(str(venv)).startswith(str(PERSISTENT_ENV_ROOT)),
            "pyvenv_cfg": cfg,
            "venv_type": venv_identity["venv_type"],
            "identity": venv_identity,
            "mode_declaration": {"available": mode_decl["available"],
                                 "path": mode_decl.get("path"),
                                 "sha256_12": mode_decl.get("sha256_12"),
                                 "declared_for_this_venv": (mode_decl.get("declared") or {}).get(
                                     venv.name)},
            "note": ("created_at / ready_at 是**这个 venv 自己的**窗口，证据来源见 `window."
                     "source_kind` 与 `window.source`（裁定 33.4 C-F2：判据的每个输入都必须与"
                     "被描述的对象同源）。身份对不上的历史证据一律列在 `window.rejected_sources` "
                     "里，不用。窗口不可得 ⇒ 记 null，不填一个看起来合理的值。"),
            "expression_discipline": ("引用本解释器时必须回显 `realpath` + venv 类型"
                                      "（clean / system-site）+ 是否经软链（增补十 §34 全员条）。"
                                      f"本行：{venv_identity['realpath']} / "
                                      f"{venv_identity['venv_type']} / symlink="
                                      f"{venv_identity['is_symlink']}。"),
        },
        "lock": {
            "path": str(lock.relative_to(ROOT)) if lock.is_relative_to(ROOT) else str(lock),
            "exists": lock.exists(), "sha256_12": _sha12(lock) if lock.exists() else None,
            "n_pins": len(lock_pins),
            "kind": "pip freeze --local（不含从 base 继承的包）",
        },
        "lock_conformance": {
            "lock_applies_to_this_venv": lock_applies,
            "lock_subject": ("rlrobot（默认 lock 是它的门禁产物）" if lock_is_default
                             else "由 --lock 指定"),
            "not_applicable_reason": (None if lock_applies else
                                      "默认 lock 描述的是 rlrobot，被描述的是另一个 venv ⇒ "
                                      "mismatch 是口径不匹配，不是环境缺陷（同源纪律，裁定 33.4）"),
            "measured_in": {"interpreter": interpreter,
                            "sys_prefix": _dist_snapshot(
                                interpreter, sorted(lock_pins)).get("sys_prefix"),
                            "is_this_process": _dist_snapshot(
                                interpreter, sorted(lock_pins)).get("is_this_process"),
                            "rule": "版本在**被描述的解释器**里取（裁定 33.4 同源纪律）"},
            "counts": status_counts,
            "all_pinned_match": bool(lock_pins) and status_counts.get("mismatch", 0) == 0
            and status_counts.get("missing", 0) == 0,
            "rows": conformance,
        },
        "inherited_packages": {
            # 增补十 §34-C③：这个名字是**历史名**（0928 那版 venv 带 --system-site-packages，
            # 这 8 个包确实是从 base 继承的）。14:2x 起 rlrobot 是 clean（自足）venv，
            # 同样这 8 个包**装在 venv 里**，语义完全不同 ⇒ 键名保留（下游在读），
            # 但语义**按 venv 类型分别解释**，且逐包回显实测位置。
            "name_is_historical": ("`inherited_packages` 是 0928 那版（--system-site-packages）留下"
                                   "的键名；下游脚本在读它，所以键名不改，语义按下面的 "
                                   "`interpretation_for_this_venv` 读。"),
            "venv_type": venv_identity["venv_type"],
            "include_system_site_packages": venv_identity["include_system_site_packages"],
            "semantics_by_venv_type": {
                "system_site": ("这 8 个包**不在 lock 里**、来自 base 镜像 ⇒ 「继承包」。"
                                "base 镜像一换它们会静默变版本，而 venv 内的 pip freeze 看不到 ⇒ "
                                "必须单独断言（裁定 32.3 第 1 条乙）。"),
                "clean": ("这 8 个包是**venv 内的本地包**（persistent lock 的 82 pin 闭包里就有它们），"
                          "不依赖 base 镜像 ⇒ 「继承」这个词在这里是**错的读法**；断言随之变成两条："
                          "① 版本仍等于基线（基线是两个独立来源交叉核过的）② 位置必须 "
                          "`venv_local=true`（若实测 `inherited_from_base=true`，说明这个「clean」"
                          "venv 其实还在吃 base ⇒ 自足性不成立，红）。"),
            },
            "interpretation_for_this_venv": (
                "clean（自足）⇒ 下面 8 个是**本地包**，不是继承包；`inherited_from_base=true` "
                "的任何一行都是红。" if venv_identity["venv_type"] == "clean" else
                "system-site ⇒ 下面 8 个来自 base 镜像，是**继承包**；`venv_local=true` 的任何一行"
                "都与声明的模式不符（红）。" if venv_identity["venv_type"] == "system_site" else
                "venv 类型判不出（pyvenv.cfg 缺 include-system-site-packages）⇒ 只报观测，不做模式断言。"),
            "baseline_applies_to_this_venv": baseline_applies,
            "baseline_subject_interpreter": baseline_subject,
            "baseline_same_source_rule": ("基线描述的是 rlrobot；被描述的 venv 不是它 ⇒ 断言"
                                          "**不适用**（不当失败读，也不当通过读）。否则 torch "
                                          "2.6.0+cu124（lerobot_act）会被判成「与基线 2.4.1+cu124 "
                                          "不符」的假红 —— 与 C-F2 同一类跨对象混算。"),
            "versions": inherited_assert.get("versions")
            or {name: (_dist_rows(interpreter, INHERITED_PACKAGES).get(name) or {}).get("version")
                for name in INHERITED_PACKAGES},
            "locations": inherited_assert.get("locations")
            or _dist_rows(interpreter, INHERITED_PACKAGES),
            "measured_in": inherited_assert.get("measured_in"),
            # 裁定 32.3 第 1 条（乙）：从**观测**升成**断言** —— 版本或来源不符即
            # env_fully_restored=false 并点名。
            "assertion": inherited_assert,
            "excluded_by_design": excluded_by_design,
        },
        # 裁定 31.2 第 1 条：探针按**解释器**分组（rlrobot / lerobot_act / lerobot_eval）。
        # 三个分组的判据不同：rlrobot 是「C 自己回归所需的依赖能不能 import」，
        # 两个 lerobot 分组是「**语义值**对不对」（版本号 + 安装来源），因为
        # `import lerobot` 成功是恒真判据（源装成 0.1.0 也 import 得到）。
        # 分组视图放 `probe_modules_by_interpreter`；`probe_modules` 保持**扁平**（module → row）：
        # 那是 12:14 那版对外的口径，A 的就绪闸 E6 直接读 `probe_modules.lerobot.version`，
        # 换 schema 会让下游读到空 dict 而**假红**（本轮 14:47 实测就是这样）。
        "probe_modules": probe_flat,
        "probe_modules_by_interpreter": probe_groups,
        "probe_module_classes": {
            "required_for_c_regression": list(PROBE_MODULES),
            "blocking_for_reproduction": list(BLOCKING_PROBE_MODULES),
            "grouped_by_interpreter": list(probe_groups),
            "blocking_by_interpreter": blocking_by_interpreter,
            "division_of_labour": ("裁定 33.4（C-F1）：`blocking_for_reproduction` 的判定**按解释器"
                                   "分工** —— `lerobot` 在 rlrobot 里是 `not_applicable`（设计如此），"
                                   "在 lerobot_act / lerobot_eval 里才是 blocking。把三态写清，"
                                   "「A 被阻」才不会被读成「B 没建好环境」，也不会每次给一个假红。"),
            "note": ("两类分开：required 缺失 ⇒ `--check` 直接 exit 3；blocking 缺失 ⇒ 只声明"
                     "「复现主张被阻」，不阻 C 自己的只读回归（裁定 29.4 的解封/仍阻分层）。"),
        },
        "gpu": {
            "nvidia_smi": _nvidia_smi(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "mujoco_gl": os.environ.get("MUJOCO_GL"),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
            "context_probe": {
                "attempted": False,
                # 裁定 29.4 附带更正 2：原句写「A 线正在用 GPU 训练」是**过期推测**，
                # 与同一份 manifest 里 nvidia-smi 实测的 0 MiB / 0 % 自相矛盾。
                # manifest 里的每一句都必须是可核事实 ⇒ 改成「不探测 + 指向实测值」。
                "reason": ("本次不探测（不创建 CUDA/EGL 上下文）；GPU 此刻的占用以同一份 "
                           "manifest 里 `gpu.nvidia_smi` 的实测 `memory_used` / `utilization_gpu` "
                           "为准。渲染可用性由需要它的自检各自实测。"),
                "ruling": "裁定 29.4 附带更正 2（增补七 §17）：manifest 里不得夹推测。",
            },
        },
        "lerobot": {},          # 下面填（裁定 29.4 的 P0 要求）
        "known_conflicts": [{
            "id": "mink-numpy-resolution",
            "summary": ("`scripts/setup_env.sh` 的范围 pin（numpy>=2）与 robosuite 1.5.2 → mink==0.0.5 → "
                        "numpy<2.0.0 冲突；pip 26.2.1 的解析器会回溯到 mink 0.0.5 并判 ResolutionImpossible。"),
            "resolution": ("按 `requirements.lock.txt` 精确复现 + `--no-deps` 跳过解析：lock 是 9/28 "
                           "**实际装成并跑通**的 freeze（mink 1.2.0 + numpy 2.4.6 + robosuite 1.5.2 共存），"
                           "解析器到不了这个组合不代表它不可用。"),
            "evidence": [_file_evidence(REBUILD_DIR / "rebuild.sh"),
                         _file_evidence(REBUILD_DIR / "rebuild.log"),
                         _file_evidence(REBUILD_DIR / "rebuild2.log"),
                         _file_evidence(REBUILD_DIR / "requirements.lock.candidate.txt")],
            "not_changed_by_c": ("仓库根 `requirements.lock.txt` 与 `scripts/setup_env.sh` 一字节未改"
                                 "（后者不在 C 的写入边界）；候选清单只写进 C 自己的目录。"),
        }],
        "breakpoints": [],       # 下面填
        "verification": {},      # 下面填
    }

    installer_pins = _installer_pins(LEROBOT_INSTALLER)
    envs = []
    for spec in LEROBOT_ENVS:
        group = lerobot_groups[spec["name"]]
        envs.append({"name": spec["name"], "path": group["requested"], "role": spec["role"],
                     "exists": group["exists"], "python_exists": group["python_exists"],
                     "resolved_path": group["path"], "is_symlink": group["is_symlink"],
                     "realpath": group["realpath"],
                     "on_persistent_nfs": group["on_persistent_nfs"],
                     "status": group["status"],
                     "lerobot_version": group["lerobot_version"],
                     "lerobot_version_matches_pin": group["lerobot_version_matches_pin"],
                     "observed_at": group["observed_at"]})
    # 裁定 32.1（增补九 §26）：安装是**执行**动作 ⇒ 归 A；B 出权威 pin；C 只出探针。
    # 下面全是 C 对 A 重建产物的**只读实测**（不解释、不裁定：解释权归 A，裁定权归 D）。
    install_log = A_REBUILD_DIR / "install.log"
    install_started = A_REBUILD_DIR / "install_started_at.txt"
    started_at = (install_started.read_text(encoding="utf-8").strip()
                  if install_started.exists() else None)
    lock_diffs = {
        "requirements.lock.txt": _lock_diff(LEROBOT_LOCK_DIR / "requirements.lock.txt",
                                            A_REBUILD_DIR / "requirements.lock.txt"),
        "requirements.eval.lock.txt": _lock_diff(LEROBOT_LOCK_DIR / "requirements.eval.lock.txt",
                                                 A_REBUILD_DIR / "requirements.eval.lock.txt"),
    }
    locks_0928_intact = {
        name: {"identical_to_c_backup": (
            _sha12(LEROBOT_LOCK_DIR / name) == _sha12(LEROBOT_LOCK_BACKUP / name)),
            "original": _file_evidence(LEROBOT_LOCK_DIR / name),
            "c_backup": _file_evidence(LEROBOT_LOCK_BACKUP / name)}
        for name in ("requirements.lock.txt", "requirements.eval.lock.txt")}
    manifest["lerobot"] = {
        "ruling": ("裁定 29.4（增补七 §17）+ 裁定 31.2（增补八 §22）+ 裁定 32.1（增补九 §26）："
                   "两个 lerobot venv 不在或版本不符 ⇒ **A 线的一切新训练/新评测仍被阻**；"
                   "安装归 A、权威 pin 归 B（DR-012）、**C 只出探针，不装环境**。"),
        "gap_statement": ("缺口的准确表述是「`lerobot_act` / `lerobot_eval` 两个 venv 整体被抹掉」，"
                          "**不是**「rlrobot 里少一个 lerobot 包」—— lerobot 按设计从不装在 "
                          "rlrobot 里（pin 文档 §1）。探针因此按解释器分组，"
                          "在 rlrobot 里探到 lerobot MISSING 记 `by_design`、不记缺口。"),
        "installed_in_this_interpreter": rlrobot_modules.get("lerobot"),
        "installed_in_this_interpreter_note": ("这一项**不是**缺口判据（见 gap_statement）；"
                                              "留它只为回显「rlrobot 里确实没有 lerobot」这个事实。"),
        "project_envs": envs,
        "probes_by_interpreter": {name: lerobot_groups[name] for name in lerobot_groups},
        "probe_rule": ("裁定 31.2 第 2 条 / DR-012 判据纪律：**「装了没」类探针一律验语义值，"
                       "不验可导入** —— `import lerobot` 是恒真判据（lerobot 的 `__version__.py` "
                       "就是 `importlib.metadata.version(\"lerobot\")`，源装成 0.1.0 时 import "
                       "照样成功）。所以每个分组都断言 ①`lerobot.__version__ == pin` "
                       "②回显安装来源（index wheel / 源装 + commit）③写出可红条件。"),
        "rebuild_by_a": {
            "executor": "A（裁定 32.1 改判；B 不再执行安装）",
            "method": "bash scripts/install_lerobot_act_env.sh（VENV/EVAL_VENV/LOCK_OUT 用环境变量覆写）",
            "started_at": started_at,
            "log": _file_evidence(install_log),
            "ready_at": _iso_ns(install_log.stat().st_mtime_ns) if install_log.exists() else None,
            "new_locks": [_file_evidence(A_REBUILD_DIR / n) for n in
                          ("requirements.lock.txt", "requirements.eval.lock.txt")],
            "lock_out_redirected_to": (str(A_REBUILD_DIR.relative_to(ROOT))
                                       if A_REBUILD_DIR.is_dir() else None),
            "lock_diff_vs_0928": lock_diffs,
            "locks_0928_not_overwritten": locks_0928_intact,
            "ruling_32_4": ("裁定 32.4：0928 的两份 lock 是「48 臂权威表当初跑在什么环境上」的"
                            "**唯一溯源证据**，不得被 installer 就地覆写。C 只读实测："
                            "两份原件与 C 的逐字节备份是否仍相同（见上），以及新 lock 与旧 lock 的"
                            "逐包差异。**差异的解释权归 A、裁定权归 D**，C 不代解释。"),
        },
        "persistence": {
            "root": str(PERSISTENT_ENV_ROOT),
            "symlinked_from": [e["path"] for e in envs if e["is_symlink"]],
            "on_persistent_nfs": {e["name"]: e["on_persistent_nfs"] for e in envs},
            "ruling": ("裁定 32.3 第 3 条：NFS 上的 venv 建成后按**只读**对待 —— 两个容器同时"
                       "对着同一份 venv 跑 pip install 会写坏它；要改就整份重建到新目录再原子"
                       "切换（本项目禁 rm）。另：NFS 上 import torch/lerobot 是大量小文件读，"
                       "冷导入耗时基线由 A 装完实测记录（不在 C 的探针里代跑）。"),
        },
        "pin": {
            "declared_by": installer_pins.get("_parsed_from"),
            "installer_sha256_12": installer_pins.get("_sha256_12"),
            "values": {k: v for k, v in installer_pins.items() if not k.startswith("_")},
            "authority": pin_authority,
            "locks_on_disk": [_file_evidence(LEROBOT_LOCK_DIR / "requirements.lock.txt"),
                              _file_evidence(LEROBOT_LOCK_DIR / "requirements.eval.lock.txt")],
            "lock_pins_lerobot": {
                "requirements.lock.txt": _lock_pins_lerobot(LEROBOT_LOCK_DIR / "requirements.lock.txt"),
                "requirements.eval.lock.txt": _lock_pins_lerobot(
                    LEROBOT_LOCK_DIR / "requirements.eval.lock.txt")},
            "lock_backup_by_c": [_file_evidence(LEROBOT_LOCK_BACKUP / "requirements.lock.txt"),
                                 _file_evidence(LEROBOT_LOCK_BACKUP / "requirements.eval.lock.txt")],
            "backup_reason": ("`install_lerobot_act_env.sh` 的 [5/7]、[7/7] 步会 `pip freeze >` "
                              "**就地覆盖**这两份 lock（0928 环境的唯一证据）。C 已先把它们"
                              "逐字节复制到 `runs/infra/c_lerobot_env_locks_backup_20260928/`"
                              "（sha256 见上，与原件一致）；A 本次重装按裁定 32.4 用 `LOCK_OUT=` "
                              "指到了新目录（实测见 rebuild_by_a.locks_0928_not_overwritten）。"),
            "source_kind": ("pin 是 **PyPI 版本号**（`lerobot==0.4.4`，走 `INDEX` 镜像），"
                            "不是 git commit ⇒ 下面那些带 commit 的盘上副本都不是本项目的 pin。"),
        },
        "candidate_sources_on_disk": [
            {"path": c, **_git_head(Path(c))} for c in LEROBOT_CANDIDATE_SOURCES],
        "candidate_sources_rule": ("裁定 29.4 + 裁定 31.2 更正：这三份是**他人副本/缓存**，不得当"
                                   "本项目的 pin。D 上午指的 `lerobot_0cf8648` 尤其不能用 —— B 只读"
                                   "实测其 HEAD 落后 tag v0.4.4 **488 个 commit**、自报 "
                                   "`version = \"0.1.0\"`（pin 文档 §4）。「目录名带 commit」不是 pin。"
                                   "C 只回显实测到的 commit，**不推断**它们与 PyPI 0.4.4 是否同源。"),
        "observation_log": [
            {"at": "2026-09-29T12:0x+08:00", "by": "C（上一轮 manifest）",
             "state": ("/root/venvs/ 下只有 rlrobot；lerobot_act 与 lerobot_eval 两个环境也已不在"
                       "（与 rlrobot 同在 /root overlay 上，被 0929 检修同批清掉）"),
             "evidence": "runs/infra/c_env_manifest_20260929.json 的上一版（lerobot.project_envs）"},
            {"at": _now_iso(), "by": "C（本次 manifest，只读实测）",
             "state": {e["name"]: {"status": e["status"], "path": e["resolved_path"],
                                   "symlink": e["is_symlink"], "nfs": e["on_persistent_nfs"],
                                   "lerobot_version": e["lerobot_version"],
                                   "matches_pin": e["lerobot_version_matches_pin"]}
                       for e in envs},
             "note": "本条是**实测**（探针子进程回显），不是叙述；上一条留档不改写（append-only）。"},
        ],
    }

    # --- env_fully_restored：逐条列出判据（可核事实，不含推测；裁定 29.4 / 32.3）---
    conditions: list[dict[str, Any]] = []

    def _cond(name: str, ok: Any, detail: Any) -> None:
        conditions.append({"condition": name, "pass": bool(ok), "detail": detail})

    if lock_applies:
        _cond(f"{venv.name}：--lock 给的每个 pin 都装成完全相同的版本",
              manifest["lock_conformance"]["all_pinned_match"],
              manifest["lock_conformance"]["counts"])
    else:
        conditions.append({
            "condition": f"{venv.name}：--lock 给的每个 pin 都装成完全相同的版本",
            "pass": True, "not_applicable": True,
            "detail": {"reason": (f"默认 lock（{lock.name}）是 **rlrobot** 的门禁产物（28 pin）；"
                                  f"被描述的是 {venv_identity['realpath']} ⇒ 口径不匹配，"
                                  "本条不适用（不当失败读，也不当通过读）。要判这个 venv 请用 "
                                  "--lock 指到它自己的 lock，例如 "
                                  "runs/infra/a_lerobot_env_rebuild_20260929/requirements.lock.txt。"),
                       "observed_counts": manifest["lock_conformance"]["counts"]}})
    if baseline_applies:
        _cond(f"{venv.name}：required_for_c_regression 的模块全部可 import（在 --interpreter 里探）",
              not rlrobot_group["missing_required"], rlrobot_group["missing_required"])
    else:
        conditions.append({
            "condition": f"{venv.name}：required_for_c_regression 的模块全部可 import",
            "pass": True, "not_applicable": True,
            "detail": {"reason": ("这 13 项是 **C 的只读回归**在 rlrobot 里所需依赖（robosuite / "
                                  "stable_baselines3 / py_trees …）；被描述的 venv 不是 rlrobot ⇒ "
                                  "不适用。这个 venv 该探什么由它自己的语义 pin 决定"
                                  "（见 probe_modules_by_interpreter 的两个 lerobot 分组）。"),
                       "observed_missing": rlrobot_group["missing_required"]}})
    if baseline_applies:
        _cond(f"{venv.name}：{INHERITED_PACKAGES[0]} 等 8 个包逐包等于基线，且位置与声明的 venv 模式"
              f"相符（当前 {venv_identity['venv_type']}；裁定 32.3 乙 / 增补十 §34-C③）",
              inherited_assert.get("status") == "ok",
              {"status": inherited_assert.get("status"), "failed": inherited_assert.get("failed"),
               "version_mismatch": inherited_assert.get("version_mismatch"),
               "mode_mismatch": inherited_assert.get("mode_mismatch"),
               "reason": inherited_assert.get("reason")})
    else:
        conditions.append({
            "condition": f"{venv.name}：8 个包逐包等于 inherited_baseline（裁定 32.3 乙）",
            "pass": True, "not_applicable": True,
            "detail": {"reason": ("基线描述的是 rlrobot（interpreter="
                                  f"{baseline_subject}），被描述的是 {venv_identity['realpath']} ⇒ "
                                  "**不适用**，不当失败也不当通过读（同源纪律，裁定 33.4）。"),
                       "baseline": _file_evidence(INHERITED_BASELINE)}})
    _cond(f"{venv.name}：pyvenv.cfg 的 home / executable / 版本断言全过（裁定 32.3 第 2 条）",
          rlrobot_group["pyvenv"]["all_pass"], rlrobot_group["pyvenv"]["failed"])
    if venv_identity["venv_type"] == "clean" and baseline_applies:
        _cond(f"{venv.name}：clean venv 里 jax / jaxlib / tensorflow **不可**导入（设计意图；"
              "可导入 = base 泄漏 = 自足性不成立）",
              excluded_by_design.get("status") == "ok",
              {"status": excluded_by_design.get("status"),
               "importable": excluded_by_design.get("importable"),
               "expectation": excluded_by_design.get("expectation")})
    _cond("窗口与被描述的 venv 同源、且不倒置（裁定 33.4 C-F2）",
          window["same_source"] and window["window_consistent"],
          {"source_kind": window["source_kind"], "occurred_at": window["occurred_at"],
           "ready_at": window["ready_at"], "subject": window["subject_venv"],
           "rejected_sources": window["rejected_sources"]})
    for spec in LEROBOT_ENVS:
        group = lerobot_groups[spec["name"]]
        _cond(f"{spec['name']}：解释器存在（缺失 ⇒ interpreter_missing，不是 module_missing）",
              group["python_exists"], group["python"])
        _cond(f"{spec['name']}：语义探针全过（lerobot.__version__ == pin 等，import 成功不算过）",
              group["semantic_probe"].get("status") == "ok",
              {"status": group["semantic_probe"].get("status"),
               "not_ok": group["semantic_probe"].get("not_ok"),
               "lerobot_version": group["lerobot_version"],
               "expected": group["pins"]["values"].get("lerobot"),
               "reason": group["semantic_probe"].get("reason")})
        _cond(f"{spec['name']}：pyvenv.cfg 断言全过（含不带 --system-site-packages，裁定 32.3）",
              group["pyvenv"]["all_pass"], group["pyvenv"]["failed"])
    _cond("lerobot 的权威 pin 三个来源一致（pin 文档 / installer 缺省 / 0928 lock）",
          pin_authority["all_agree"], pin_authority["sources"])
    manifest["env_fully_restored_conditions"] = conditions
    manifest["env_fully_restored"] = all(c["pass"] for c in conditions)
    na = [c["condition"] for c in conditions if c.get("not_applicable")]
    manifest["env_fully_restored_not_applicable"] = na
    manifest["env_fully_restored_reason"] = (
        ("全部**适用**条件通过" + (f"；{len(na)} 条对被描述的 venv 不适用（{na}）—— "
                                  "不当通过读，见各条 detail.reason" if na else ""))
        if manifest["env_fully_restored"]
        else "未通过：" + "; ".join(f"{c['condition']}（detail={c['detail']}）"
                                    for c in conditions if not c["pass"]))
    differing_locks = [name for name, diff in lock_diffs.items()
                       if diff.get("comparable") and not diff.get("identical")]
    static_surface = _static_import_surface(ACT_CHAIN_SCRIPTS, RULING_34_1_PACKAGES)
    ruling_34_1 = _ruling_34_1(static_surface, import_surface, lock_diffs)
    manifest["ruling_34_1_lock_diff_adjudication"] = ruling_34_1
    manifest["reproduction_claims_blocked"] = {
        "blocked": (not manifest["env_fully_restored"]) or ruling_34_1["blocked"],
        "what_is_blocked": ("A 线的一切**新训练 / 新评测复现**主张（裁定 29.4）；"
                            "只读后处理与 robosuite/mujoco 依赖的自检**不在**被阻之列。"),
        "missing": [f"{name}: {g['status']}" + (f"（{g['semantic_probe'].get('not_ok')}）"
                                                if g["semantic_probe"].get("not_ok") else "")
                    for name, g in lerobot_groups.items() if g["status"] != "ok"]
        + [f"env_fully_restored 条件未过：{c['condition']}"
           for c in conditions if not c["pass"]],
        "adjudicated_rulings": ruling_34_1["adjudicated_differences"],
        "adjudication": {
            "ruling": ruling_34_1["ruling"],
            "summary": ruling_34_1["ruling_summary"],
            "void_condition": ruling_34_1["void_condition"],
            "void_condition_triggered": ruling_34_1["void_condition_measured"]["triggered"],
            "static_evidence": ruling_34_1["void_condition_measured"]["static"],
            "dynamic_evidence": ruling_34_1["void_condition_measured"]["dynamic"],
            "consequence": ruling_34_1["blocked_reason"],
            "history": ("裁定 32.4 时这 3 处差异是**待裁定**（A 解释 / D 裁定）⇒ 当时 blocked=true；"
                        "裁定 34.1（增补十一 §36）已放行，但豁免按包按链路、且带可红条件 ⇒ "
                        "本栏从「待裁定」改成「已裁定 + 可红条件实测」。C 只实测，不改判。"),
        },
        "pending_rulings": [],
        "why_env_restored_is_not_enough": ("`env_fully_restored=true` 只说明「按 pin 装对了」；"
                                           "**跨断点的复现主张**还要看 裁定 32.4：重建 lock 与 0928 "
                                           "lock 的差异必须 A 逐条解释、D 裁定，否则「48 臂跑在什么"
                                           "环境上」与「现在这个环境」不是同一个事实。两个判据分开报，"
                                           "谁也别冒充谁。"),
        "reading_rule": ("**本 manifest 的「全绿」只覆盖 `probe_module_classes."
                         "required_for_c_regression`**；`env_fully_restored=false` 时，"
                         "不得读成「环境已完全恢复」。"),
    }

    manifest["breakpoints"] = [{
        "id": "BP-20260929-venv-rebuild",
        "kind": "environment_rebuild",
        # 裁定 33.4（C-F2）：这条断点描述的是 **overlay 上那份被检修抹掉、C 在 10:45–10:57 重建的**
        # rlrobot venv，所以窗口取它自己的证据（C 12:14 归档的 manifest + 它自己的重建日志），
        # **不是**本次 `--venv` 指的那个 venv 的窗口。两者混用就是 C-F2。
        "occurred_at": overlay_window["occurred_at"],
        "occurred_at_ns": overlay_window["occurred_ns"],
        "ready_at": overlay_window["ready_at"], "ready_at_ns": overlay_window["ready_ns"],
        "window": overlay_window,
        "window_subject": overlay_window["subject_venv"],
        "applies_to_described_venv": overlay_window["applies_to_described_venv"],
        "cause": ("0929 早间服务器检修：进程被直接关闭，overlay 上的 `/root/venvs/rlrobot` "
                  "与 `~/.codex/sessions/2026-09-28/`（四线对话历史）一并丢失。"),
        "authority": "监管备忘 增补六 §0.2 第 2 条（`rl_harness_supervision/supervisor_memo_20260929.md`）",
        "rebuild": {
            "method": "python3 -m venv --system-site-packages + pip install --no-deps -r requirements.lock.txt",
            "finished_at": "2026-09-29T10:57:19+08:00（rebuild2.log 末行 rc=0）",
            "lock_candidate_sha12": _sha12(REBUILD_DIR / "requirements.lock.candidate.txt"),
            "candidate_equals_repo_lock": (
                (REBUILD_DIR / "requirements.lock.candidate.txt").exists() and lock.exists()
                and (REBUILD_DIR / "requirements.lock.candidate.txt").read_text(encoding="utf-8").strip()
                == lock.read_text(encoding="utf-8").strip()),
        },
        "invalidates": ("任何**需要 rlrobot venv** 的评测/训练复现主张，若其产物 mtime 早于本断点 ⇒ "
                        "跨断点，必须在重建后的环境上重跑才继续有效。"),
        "does_not_invalidate": ("只读后处理类结论（门禁裁定、48 臂汇总、登记册、账本/视图自检）—— "
                               "增补六 §0.2 第 1 条：`GATE_BUILD` 是脚本内容哈希、被裁产物未被改写。"
                               "**不得**写「检修后所有结论都要重验」。"),
        "scope_environments": {
            "lost": ["/root/venvs/rlrobot", "/root/venvs/lerobot_act", "/root/venvs/lerobot_eval"],
            "rebuilt": [{"path": "/root/venvs/rlrobot", "window": "10:45:56–10:57:19",
                         "lock": "requirements.lock.txt（28 pin 全中）"}],
            "still_missing": [e["path"] for e in envs if not e["python_exists"]],
            "see_also": "BP-20260929-lerobot-envs-wiped（同批被清，但 invalidates 范围不同）",
            "note": ("三个环境同在 `/root` overlay 上、同批被清。C 只重建了自己写入边界内需要的 "
                     "rlrobot；lerobot 两个环境的安装按 裁定 32.1 归 **A**（B 出权威 pin、"
                     "C 只出探针，C 不代装）。"),
        },
        "partial_release": {
            "ruling": "裁定 29.4（增补七 §17）：断点**部分解除**",
            "unblocked": ("只读后处理（门禁 / 48 臂汇总 / 登记册 / 账本视图自检）"
                          "**以及** robosuite/mujoco 依赖的自检 —— 旁证：C 全量回归 13/13 全绿、"
                          "golden `171 PASS / 0 FAIL / 1 NOT_ASSERTABLE`。"),
            "still_blocked": ("A 线的一切新训练 / 新评测 —— 判据是 `lerobot` 一栏两个分组的"
                              "**实测状态**（interpreter_missing / version_mismatch 都算仍阻），"
                              "不是这句话本身；本字段只是指路。"),
        },
        "irrecoverable_part": ("对话历史（`~/.codex/sessions/`）与 venv 同在 overlay 上：venv 可由 lock 复现，"
                              "对话历史**不可复现**，只能靠盘上产物重建（本轮 C 的上下文即如此重建）。"),
        "evidence": [_file_evidence(p) for p in
                     (REBUILD_DIR / "rebuild.sh", REBUILD_DIR / "rebuild.log",
                      REBUILD_DIR / "rebuild2.log", ARCHIVED_MANIFEST_PRE_REBUILD)],
        "evidence_note": ("证据一律取**那条断点自己的**产物：重建脚本/日志 + C 12:14 归档的 "
                          "manifest（当时实测的 created/ready 与 pyvenv.cfg 原文）。本次 `--venv` "
                          "的 pyvenv.cfg **不当本条的证据**（它描述的是另一个 venv）。"),
        "crossing_rule": ("判定某条主张跨没跨过断点：取其产物 mtime 与本断点的窗口比 —— "
                          "mtime < occurred_at_ns ⇒ before（旧环境的产物，跨了断点）；"
                          "落在窗口内 ⇒ during_rebuild（半装好的环境，同样不可当复现证据）；"
                          "mtime >= ready_at_ns ⇒ after。"
                          "verification.selfcheck_artifacts 已按此规则给出 position_vs_breakpoint。"),
    }]

    # A 侧的落盘证据（只读引用，不重跑）：门槛验证（就绪闸 E3）与冷导入基线。
    a_gate_artifact = A_REBUILD_DIR / "a_env_readiness_after_rebuild.json"
    a_cold_artifact = A_REBUILD_DIR / "cold_import_baseline_v2.json"
    if not a_cold_artifact.exists():
        a_cold_artifact = A_REBUILD_DIR / "cold_import_baseline.json"
    a_evidence: dict[str, Any] = {"entrypoints": None, "entrypoints_pass": None,
                                  "cold_baseline": None, "cold_baseline_present": None}
    if a_gate_artifact.exists():
        try:
            gate_rows = {r.get("id"): r for r in
                         (json.loads(a_gate_artifact.read_text(encoding="utf-8")).get("rows") or [])}
            e3 = gate_rows.get("E3") or {}
            a_evidence["entrypoints"] = {
                "source": _file_evidence(a_gate_artifact), "check_id": "E3",
                "name": e3.get("name"), "pass": e3.get("pass"),
                "observed": e3.get("observed"), "read_at": _now_iso()}
            a_evidence["entrypoints_pass"] = (True if e3.get("pass") is True
                                              else (False if e3.get("pass") is False else None))
        except Exception as exc:                               # noqa: BLE001
            a_evidence["entrypoints"] = {"source": _file_evidence(a_gate_artifact),
                                         "read_error": f"{type(exc).__name__}: {exc}"}
    if a_cold_artifact.exists():
        try:
            cold = json.loads(a_cold_artifact.read_text(encoding="utf-8"))
            per_venv = cold.get("venvs") or {}
            a_evidence["cold_baseline"] = {
                "source": _file_evidence(a_cold_artifact),
                "protocol": cold.get("protocol"),
                "venvs": {name: {"composite": (row.get("composite") or {}),
                                 "true_cold_effective": row.get("true_cold_effective")}
                          for name, row in per_venv.items()},
                "covers_both_lerobot_venvs": all(n in per_venv for n in
                                                 ("lerobot_act", "lerobot_eval")),
                "read_at": _now_iso()}
            a_evidence["cold_baseline_present"] = bool(
                a_evidence["cold_baseline"]["covers_both_lerobot_venvs"])
        except Exception as exc:                               # noqa: BLE001
            a_evidence["cold_baseline"] = {"source": _file_evidence(a_cold_artifact),
                                           "read_error": f"{type(exc).__name__}: {exc}"}

    # --- 第二个断点：lerobot 的两个 venv（与 BP-20260929-venv-rebuild **并列、不合并**：
    # 裁定 31.2 第 3 条明写它们的 invalidates 范围不同 —— 那条废的是 robosuite 侧复现，
    # 这条废的是**官方 ACT 训练与真值评测**）---
    release_conditions = [
        {"condition": "两个解释器都在（不是 module_missing，是 interpreter 层面）",
         "owner": "C 探针实测",
         "met": all(g["python_exists"] for g in lerobot_groups.values()),
         "detail": {n: g["status"] for n, g in lerobot_groups.items()}},
        {"condition": "lerobot.__version__ == 权威 pin（在**各自**解释器里验，import 成功不算过）",
         "owner": "C 探针实测",
         "met": all(g["semantic_probe"].get("status") == "ok" for g in lerobot_groups.values()),
         "detail": {n: {"version": g["lerobot_version"],
                        "matches_pin": g["lerobot_version_matches_pin"],
                        "install_source": (g["lerobot_install_source"] or {}).get("kind"),
                        "not_ok": g["semantic_probe"].get("not_ok")}
                    for n, g in lerobot_groups.items()}},
        {"condition": "venv 不带 --system-site-packages + base 解释器断言全过（裁定 32.3 第 2 条）",
         "owner": "C 探针实测",
         "met": all(g["pyvenv"]["all_pass"] for g in lerobot_groups.values()),
         "detail": {n: g["pyvenv"]["failed"] for n, g in lerobot_groups.items()}},
        {"condition": "A 的门槛验证：ACTConfig/ACTPolicy 可 import + `python -m "
                      "lerobot.scripts.lerobot_train --help` 通过（pin 文档 §3）",
         "owner": "A（C 不代跑：那是训练入口验证，属执行侧）",
         "met": a_evidence["entrypoints_pass"],
         "detail": a_evidence["entrypoints"],
         "how_c_knows": ("只读 A 的**落盘产物**（就绪闸 E3），不重跑；产物身份见 evidence "
                         "的 sha256_12 与 mtime。产物不在 ⇒ met=null（null ≠ true，ADR-C-004）。")},
        {"condition": "重建 lock 与 0928 lock 的差异逐条解释 + D 裁定（裁定 32.4 → 裁定 34.1）",
         "owner": "A 解释 / D 裁定",
         "met": (False if ruling_34_1["blocked"] else True),
         "detail": {"ruling": ruling_34_1["ruling"],
                    "adjudicated": [d["differences"] for d in
                                    ruling_34_1["adjudicated_differences"]],
                    "void_condition_triggered":
                        ruling_34_1["void_condition_measured"]["triggered"],
                    "exemption_scope": "按包按链路（imageio / uv，48 臂链路）",
                    "identical": not differing_locks},
         "how_c_knows": ("裁定 34.1 已放行这 3 处差异，但豁免带**可红条件**；C 实测该条件"
                         "（静态 AST + 动态 sys.modules）⇒ 触发则本条转 false、差异回到阻塞项。")},
        {"condition": "NFS venv 的冷导入耗时基线记录一次（裁定 32.3 第 3 条）",
         "owner": "A",
         "met": a_evidence["cold_baseline_present"],
         "detail": a_evidence["cold_baseline"],
         "how_c_knows": ("C 的探针**不代跑**（探一次冷导入会污染 A 的基线测量：逐出页缓存是"
                         "全局副作用）；只读 A 的落盘产物并回显其身份。")},
    ]
    manifest["breakpoints"].append({
        "id": "BP-20260929-lerobot-envs-wiped",
        "kind": "environment_rebuild",
        "scope_environments": [{"name": e["name"], "path": e["path"],
                                "resolved_path": e["resolved_path"], "status": e["status"]}
                               for e in envs],
        "occurred_at": None,
        "occurred_at_reason": ("丢失时刻**不可测**：两个 venv 在 overlay 上被清，没留下任何可取 "
                               "mtime 的产物。只给下界，不填一个看起来合理的值（裁定 29.4 附带"
                               "更正 2：manifest 里不得夹推测）。"),
        "occurred_at_lower_bound": ("2026-09-29T12:0x+08:00：C 上一份 manifest 实测 "
                                    "`/root/venvs/` 只有 rlrobot（见 lerobot.observation_log[0]）"),
        "rebuild_started_at": started_at,
        "ready_at": _iso_ns(install_log.stat().st_mtime_ns) if install_log.exists() else None,
        "cause": ("0929 早间服务器检修：进程被直接关闭，`/root/venvs/lerobot_act` 与 "
                  "`/root/venvs/lerobot_eval` 与 rlrobot 同在 overlay 上、同批丢失。"),
        "authority": ("监管备忘 增补六 §0.2 第 2 条 + 裁定 29.4 + 裁定 31.2（增补八 §22）+ "
                      "裁定 32.1（增补九 §26：安装责任改判给 A）"),
        "invalidates": ("**官方 ACT 训练与真值评测**的一切复现主张：依赖这两个 venv 的训练/评测"
                        "产物（含 48 臂权威表所依据的那批评测），mtime 早于本断点 ⇒ 跨断点，"
                        "必须在重建后的环境上重跑才继续有效。"),
        "does_not_invalidate": ("只读后处理类结论（门禁裁定、48 臂汇总的**数值**、登记册、"
                                "账本/视图自检）—— 依据是机制性的：`GATE_BUILD` 是脚本内容哈希、"
                                "被裁产物未被改写；且 0928 的两份 lock 未被覆写（实测见 "
                                "`lerobot.rebuild_by_a.locks_0928_not_overwritten`）。"
                                "**不得**写「检修后所有结论都要重验」。"),
        "differs_from_bp_20260929_venv_rebuild": (
            "BP-20260929-venv-rebuild 废的是 **rlrobot / robosuite 侧**的复现（B、C 的自检环境）；"
            "本条废的是 **lerobot 侧**的官方 ACT 训练与真值评测（A 的执行环境）。"
            "两条**并列不合并**（裁定 31.2 第 3 条）：合并之后「哪一类主张要重跑」就分不清了。"),
        "rebuild": {
            "executor": "A（裁定 32.1 改判：安装是执行动作，归训练/评测责任线）",
            "pin_authority": "B（DR-012 / docs/lerobot_env_reinstall_pin_20260929.md）",
            "probe_only": "C（本 manifest 的 probe_modules.lerobot_act / lerobot_eval 两组）",
            "method": ("bash scripts/install_lerobot_act_env.sh，VENV / EVAL_VENV / LOCK_OUT "
                       "用环境变量覆写到持久目录（A 不改 B 的脚本，裁定 32.2 第 1 条）"),
            "target": str(PERSISTENT_ENV_ROOT),
            "log": _file_evidence(install_log),
        },
        "release_conditions": release_conditions,
        "released": all(c["met"] is True for c in release_conditions),
        "released_note": ("`released` 只在**所有**条件为 True 时才是 true；owner 是 A/D 的条件"
                          "C 测不到，如实记 null（null ≠ true，ADR-C-004：SKIP/未知不当通过读）。"),
        "evidence": [_file_evidence(x) for x in
                     (install_log, install_started,
                      A_REBUILD_DIR / "requirements.lock.txt",
                      A_REBUILD_DIR / "requirements.eval.lock.txt",
                      LEROBOT_LOCK_BACKUP / "requirements.lock.txt",
                      LEROBOT_LOCK_BACKUP / "requirements.eval.lock.txt")],
        "crossing_rule": ("判定某条主张跨没跨过本断点：取其产物 mtime 与 rebuild 窗口比 —— "
                          "mtime < rebuild_started_at ⇒ before（旧环境的产物，跨了断点）；"
                          "落在 [rebuild_started_at, ready_at] 内 ⇒ during_rebuild（半装好的环境，"
                          "同样不可当复现证据）；mtime >= ready_at ⇒ after。"
                          "occurred_at 不可测 ⇒ 这里用 A 的重建窗口作参照，不用检修时刻。"),
    })

    # --- 第三个断点：rlrobot 迁到 NFS 持久层并接上 /root/venvs（裁定 33.3 / 增补十 §32）---
    # D 已把条目内容写在 `verification.json.breakpoint` 里、并写明 `owner_of_registration = C`
    # （env manifest 的断点清单在 C 的写入边界）。C 的做法：**只读引用** D 的条目原文（带 sha），
    # 再补 C 侧的实测字段；不改写 D 的措辞，也不把 D 的 `invalidates = 无` 换成 C 自己的判断。
    symlinks_json = PERSISTENT_ENV_ROOT / "symlinks.json"
    persistent_rlrobot = PERSISTENT_ENV_ROOT / venv.name
    d_verification_json = ROOT / "runs" / "infra" / "d_persistent_env_20260929" / "verification.json"
    d_entry: dict[str, Any] = {}
    d_entry_error = None
    if d_verification_json.exists():
        try:
            d_entry = (json.loads(d_verification_json.read_text(encoding="utf-8"))
                       .get("breakpoint") or {})
        except Exception as exc:                               # noqa: BLE001
            d_entry_error = f"{type(exc).__name__}: {exc}"
    else:
        d_entry_error = f"文件不存在：{d_verification_json}"
    meta_path = venv / PERSIST_META_NAME
    build_window = {"occurred_at": window["occurred_at"], "ready_at": window["ready_at"],
                    "source_kind": window["source_kind"], "source": window["source"],
                    "subject_venv": window["subject_venv"],
                    "same_source": window["same_source"],
                    "window_consistent": window["window_consistent"]}
    switch_ns = (symlinks_json.stat().st_mtime_ns if symlinks_json.exists() else None)
    manifest["breakpoints"].append({
        "id": "BP-20260929-rlrobot-persistent",
        "kind": "environment_relocation",
        "c_earlier_id": ("BP-20260929-venv-persistence-migration（C 14:49 那版 manifest 里用的名字）。"
                         "D 在 裁定 33.3 登记时定名 `BP-20260929-rlrobot-persistent` ⇒ 以 D 的 id 为准；"
                         "旧名保留在这一行以便检索，不另立第四条断点。"),
        "registered_by": "C（owner_of_registration，见 D 的 breakpoint 条目）",
        "registered_from": {"file": _file_evidence(d_verification_json),
                            "read_only": True,
                            "error": d_entry_error,
                            "rule": ("D 的条目原文照录（下面的 at / what_changed / invalidates / "
                                     "provenance_delta / old_env_kept_at / relation 全部来自它），"
                                     "C 只追加 `c_measured` 与窗口字段；不改写 D 的措辞。")},
        "at": d_entry.get("at"),
        "occurred_at": _iso_ns(switch_ns),
        "occurred_at_ns": switch_ns,
        "occurred_at_source": (f"{symlinks_json.name} 的 mtime（软链登记时刻 = 切换生效时刻）"
                               if switch_ns else "symlinks.json 不在 ⇒ 切换时刻不可测，记 null"),
        "ready_at": _iso_ns(switch_ns), "ready_at_ns": switch_ns,
        "ready_at_note": ("切换是原子的（mv 旧 venv 进回收站 + 建软链），没有「半装好」的窗口 ⇒ "
                          "occurred_at == ready_at。venv **本体**的建成窗口另见 `build_window`。"),
        "build_window": build_window,
        "what_changed": d_entry.get("what_changed"),
        "cause": ("裁定 32.3 的持久化方向落地：`/root/venvs/*` 全部改成指向 "
                  f"`{PERSISTENT_ENV_ROOT}` 的符号链接（venv 与 `~/.codex/sessions/` 同在 overlay，"
                  "每次检修都被清 ⇒ 建在 NFS 上换容器不用重装）。"),
        "authority": ("裁定 32.3（增补九 §28）+ 裁定 33.2（自足清单是 82 pin 闭包，不是 8 个）+ "
                      "裁定 33.3（增补十 §32：已迁成、断点定名、invalidates=无）+ "
                      "裁定 34.2（增补十一 §37：14:35 切成软链，B/A 的文档需追认）"),
        "invalidates": d_entry.get("invalidates"),
        "provenance_delta": d_entry.get("provenance_delta"),
        "old_env_kept_at": d_entry.get("old_env_kept_at"),
        "relation": d_entry.get("relation"),
        "does_not_invalidate": ("D 的 `invalidates = 无` 已含此意，C 只把它翻译成 C 侧产物的读法："
                                "只读后处理类结论（门禁裁定、48 臂汇总数值、登记册、账本/视图自检）"
                                "不因本断点失效；依据是机制性的（GATE_BUILD 是脚本内容哈希、"
                                "被裁产物未被改写）+ D 实测的 28 pin 逐格相同 / env_check 同值 / "
                                "B 的 12 项自检全过。"),
        "differs_from_other_breakpoints": (
            "BP-20260929-venv-rebuild = 检修把 overlay venv 抹掉后 C 在 10:45–10:57 **重建**；"
            "BP-20260929-lerobot-envs-wiped = lerobot 两个 venv 被抹掉后由 A 重建；"
            "本条 = rlrobot **迁到 NFS 持久层**（模式从 system-site 变 clean、路径变软链）。"
            "三条并列不合并：invalidates 的范围各不相同，合并之后「哪一类主张要重跑」就分不清。"),
        "c_measured": {
            "venvs_now_symlinks": {e["name"]: {"path": e["path"], "is_symlink": e["is_symlink"],
                                               "realpath": e["realpath"],
                                               "on_persistent_nfs": e["on_persistent_nfs"]}
                                   for e in envs},
            "rlrobot": {"path": str(venv), "is_symlink": venv.is_symlink(),
                        "realpath": os.path.realpath(str(venv)),
                        "venv_type": venv_identity["venv_type"],
                        "persistent_dir_exists": persistent_rlrobot.is_dir(),
                        "persist_meta": _file_evidence(meta_path) if meta_path.exists() else None,
                        "mode_before": "inherit_base（--system-site-packages=true，见 C 12:14 manifest）",
                        "mode_after": rlrobot_mode,
                        "mode_evidence": (declared.get(venv.name) or declared.get("rlrobot") or {})},
            "symlinks_json": _file_evidence(symlinks_json),
            "package_versions_unchanged": {
                "assertion": inherited_assert.get("status"),
                "failed": inherited_assert.get("failed"),
                "note": ("实测：8 个原「继承包」的版本与 inherited_baseline 逐项一致 ⇒ 迁移"
                         "**没有**带来版本漂移（这一条是实测，不是推断）。位置从 base 变成 "
                         "venv 内（`inherited_packages.locations[*].venv_local`）。")},
            "excluded_by_design": excluded_by_design,
            "lock_conformance": manifest["lock_conformance"]["counts"],
        },
        "persistence_risks": ("裁定 32.3 第 3 条：NFS 上的 venv 建成后按**只读**对待 —— "
                              "两个容器同时对着同一份 venv 跑 pip install 会写坏它；要改就整份"
                              "重建到新目录再原子切换（本项目禁 rm）。冷导入耗时基线："
                              "rlrobot 侧 D 已交（冷 torch 14.51s / 热 1.64s），lerobot 两侧见 "
                              "`lerobot.rebuild_by_a` 引用的 A 产物。"),
        "evidence": [_file_evidence(x) for x in
                     (symlinks_json, d_verification_json, ARCHIVED_MANIFEST_PRE_REBUILD,
                      persistent_rlrobot / "pyvenv.cfg", meta_path, VENV_MODE_DECLARATION,
                      INHERITED_BASELINE)],
    })

    try:
        from registry import verdict_identity as vi          # noqa: PLC0415
        gate = vi.current_gate_identity(refresh=True)
        gate_info = {k: gate.get(k) for k in ("gate_version", "gate_build", "module_sha256")}
    except Exception as exc:                                 # noqa: BLE001
        gate_info = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    fp_after = _interpreter_fingerprint(venv)
    # 裁定 33.4 同型缺陷（C 自查）：上一版把 `at`（打指纹的时刻）也算进「身份变了」⇒
    # 两次打指纹必然不同 ⇒ 本条**恒红**、env_fully_restored 永远 false。恒红的判据等于没有判据。
    changed = _fingerprint_diff(fp_before, fp_after)
    manifest["snapshot_consistency"] = {
        "consistent": not changed,
        "changed_fields": changed,
        "volatile_fields_excluded": list(FINGERPRINT_VOLATILE_FIELDS),
        "why_excluded": ("`at` 是打指纹的时刻，两次必然不同；算进差异会让本条恒红"
                         "（14:52 实测 changed_fields=['at']）。排除项显式回显，不藏在代码里。"),
        "selftest": "verification.snapshot_consistency_selftest（双向：只改 at ⇒ 自洽；改身份字段 ⇒ 不自洽）",
        "before": fp_before, "after": fp_after,
        "why_it_matters": ("manifest 跑到一半脚下的 venv 被换（本轮 14:21 实测发生过：A 把 "
                           "/root/venvs/rlrobot 换成指向 NFS 持久 venv 的符号链接、模式从 "
                           "--system-site-packages=true 变 false）⇒ 同一份快照前半段与后半段"
                           "不是同一个环境。不自洽 ⇒ env_fully_restored 一律记 false 并要求重跑，"
                           "不得把混着两个环境的观测当结论（同 verdict 自检对「B 正在改门禁脚本」"
                           "的处理：记 SKIP，不算通过也不算失败）。"),
    }
    if changed:
        conditions.append({
            "condition": "快照自洽：manifest 生成期间解释器身份未被改写",
            "pass": False, "detail": {"changed_fields": changed,
                                      "before": fp_before, "after": fp_after}})
        manifest["env_fully_restored"] = False
        manifest["env_fully_restored_reason"] = (
            "未通过：快照不自洽（生成期间解释器身份变了：" + ", ".join(changed)
            + "）⇒ 重跑一次 c_env_manifest.py 再读；本次所有 env 断言都不作数。")
    # 窗口倒过来（occurred > ready）⇒ 不做 before/during/after 归属，一律记 null
    governing_label = f"described_venv（{venv_identity['realpath']}）"
    attribution_windows: dict[str, tuple[int | None, int | None]] = {
        governing_label: ((venv_created_ns, venv_ready_ns) if window["window_consistent"]
                          else (None, None))}
    for bp in manifest["breakpoints"]:
        occ, rdy = bp.get("occurred_at_ns"), bp.get("ready_at_ns")
        if occ is not None and rdy is not None and occ <= rdy:
            attribution_windows[bp["id"]] = (occ, rdy)
    artifacts = _selfcheck_artifacts(attribution_windows, governing_label)
    manifest["verification"] = {
        "gate_current_at_manifest_time": gate_info,
        "gate_note": ("记这一项是为了把「环境快照」与「判据构建」绑在一起：将来看到某份 manifest，"
                      "就能知道它是在哪一版门禁下出的（构建在 C 脚下移动过 3 次：b9379fdb1089 → "
                      "9e57327af208 → f19f61341cbe）。"),
        "selfcheck_artifacts": artifacts,
        "breakpoint_classifier_selftest": _breakpoint_classifier_selftest(venv_created_ns,
                                                                        venv_ready_ns),
        "attribution_windows": {label: {"occurred_at": _iso_ns(occ), "ready_at": _iso_ns(rdy),
                                        "usable": occ is not None and rdy is not None}
                                for label, (occ, rdy) in attribution_windows.items()},
        "attribution_governing_window": governing_label,
        "selfcheck_summary": {
            "n_artifacts": len(artifacts),
            "n_pass": sum(1 for a in artifacts if a["pass"] is True),
            "n_not_pass": sum(1 for a in artifacts if a["pass"] is not True),
            "n_after_breakpoint": sum(1 for a in artifacts
                                      if a["position_vs_breakpoint"] == "after"),
            "n_during_rebuild": sum(1 for a in artifacts
                                    if a["position_vs_breakpoint"] == "during_rebuild"),
            "n_before_breakpoint": sum(1 for a in artifacts
                                       if a["position_vs_breakpoint"] == "before"),
            "counts_by_window": {
                label: {pos: sum(1 for a in artifacts
                                 if (a.get("positions_by_window") or {}).get(label) == pos)
                        for pos in ("before", "during_rebuild", "after", None)}
                for label in attribution_windows},
            "note": ("只读各产物自己写的 pass/n_checks，不重跑、不改判；顶层三个 n_* 计数按 "
                     "`attribution_governing_window`（= 被描述的这个 venv 自己的窗口）算，"
                     "其余窗口的归属见 `counts_by_window` 与每份产物的 `positions_by_window`。"
                     "position 为 before / during_rebuild 的那些**跨了断点**，按 §0.2 第 2 条"
                     "须在新环境上重跑才算复现。"),
        },
        "snapshot_consistency_selftest": _snapshot_consistency_selftest(),
        "venv_window_selftest": _venv_window_selftest(),
        "entry_check": {
            "cmd": f"{interpreter} -c \"import robosuite; print(robosuite.__version__)\"",
            "expected": "1.5.2（改判 3 的可复现性前提：robosuite 1.5.2 + harness/env_factory.py 的物体 pin）",
            "result": manifest["probe_modules"].get("robosuite"),
        },
    }
    return manifest


# 覆写前要留档的字段（D 附记 2 §2：「我改了什么、改前是什么」必须自带证据，不靠 mtime 猜）。
PREVIOUS_MANIFEST_WATCHED_KEYS = (
    "generated_at", "env_fully_restored", "env_fully_restored_reason",
    "reproduction_claims_blocked.blocked", "reproduction_claims_blocked.missing",
    "reproduction_claims_blocked.adjudication.void_condition_triggered",
    "probe_modules.lerobot.importable", "probe_modules.lerobot.version",
    "probe_modules.lerobot.probed_in", "probe_modules.lerobot.status",
    "probe_modules.lerobot.both_interpreters_agree",
    "probe_modules_by_interpreter.rlrobot.missing_required",
    "probe_modules_by_interpreter.rlrobot.lerobot_missing_here_is_by_design",
    "venv.created_at", "venv.ready_at", "venv.window.source_kind",
    "venv.window.same_source", "venv.window.window_consistent",
    "venv.realpath", "venv.venv_type",
    "lock_conformance.counts", "lock_conformance.all_pinned_match",
    "inherited_packages.assertion.status", "inherited_packages.excluded_by_design.status",
    "snapshot_consistency.consistent",
    "breakpoints",
    "verification.breakpoint_classifier_selftest.all_match",
    "verification.snapshot_consistency_selftest.all_match",
    "verification.venv_window_selftest.all_match",
    "verification.gate_current_at_manifest_time",
    "verification.selfcheck_summary",
)


def _dig(payload: Any, dotted: str) -> Any:
    node = payload
    for part in dotted.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def _archive_previous(out: Path) -> dict[str, Any]:
    """覆写自己的产物之前先 `copy2` 留档（D 附记 2 §2 的硬纪律，自下一次起生效）。

    理由与 裁定 35.1 同源：**「修完就绿」和「判据本来就不会红」在覆写之后长得一模一样**，
    只有留档能区分。留档落在 C 自己的目录里（`runs/infra/c_env_rebuild_20260929/`），
    不改产物路径本身 —— A 的 E6 读的仍是 `runs/infra/c_env_manifest_20260929.json`。
    """
    if not out.exists():
        return {"existed": False, "reason": "首次写这个路径，无可留档"}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = REBUILD_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = archive_dir / f"{out.stem}.pre_{stamp}{out.suffix}"
    shutil.copy2(out, archived)
    try:
        previous = json.loads(out.read_text(encoding="utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        previous = {"_unreadable": f"{type(exc).__name__}: {exc}"}
    return {"existed": True, "path": str(out), "archived_to": str(archived),
            "sha256": _sha12(out), "sha256_full": hashlib.sha256(
                out.read_bytes()).hexdigest() if out.exists() else None,
            "generated_at": previous.get("generated_at"),
            "previous": previous,
            "rule": ("覆写自己的产物前 copy2 留档（D 附记 2 §2）；`previous` 内嵌旧内容，"
                     "于是 `changed_fields` 的 before 值可核，不必去翻留档文件。")}


def _changed_fields(previous_entry: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """与上一版的逐字段差异（只挑 D 点名的那些 + 断点清单），before/after 都回显。"""
    previous = (previous_entry or {}).get("previous") or {}
    if not previous:
        return {"comparable": False,
                "reason": "没有上一版（首次写这个路径）⇒ 无从比较，不填一个看起来合理的值"}
    rows = {}
    for key in PREVIOUS_MANIFEST_WATCHED_KEYS:
        before, after = _dig(previous, key), _dig(manifest, key)
        if before != after:
            rows[key] = {"before": before, "after": after}
    return {"comparable": True, "n_watched": len(PREVIOUS_MANIFEST_WATCHED_KEYS),
            "n_changed": len(rows), "changed": rows,
            "previous_generated_at": previous.get("generated_at"),
            "previous_sha256_12": (previous_entry or {}).get("sha256"),
            "note": ("只列**被watched 的**字段（判据面），不是全文 diff：全文里 generated_at / "
                     "observed_at / mtime 每次都变，混进来会把真变化埋掉。")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", default=str(DEFAULT_VENV), help="被描述的环境（默认 /root/venvs/rlrobot）")
    ap.add_argument("--lock", default=str(DEFAULT_LOCK), help="pin 清单（默认仓库根 requirements.lock.txt）")
    ap.add_argument("--interpreter", default=sys.executable, help="探测 import 用哪个解释器（默认当前）")
    ap.add_argument("--json-out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true",
                    help="lock 一致性闸：有 mismatch/missing 就 exit 3（默认只报不闸）")
    ap.add_argument("--occurred-at", default=None,
                    help="显式给定被描述 venv 的重建起点（ISO 时刻）。裁定 33.4 C-F2：窗口证据必须"
                         "与被描述的 venv 同源；该 venv 没有 .persist_meta.json 时可用本参数显式给。")
    ap.add_argument("--ready-at", default=None,
                    help="显式给定被描述 venv 的可用时刻（ISO 时刻），同上。")
    ap.add_argument("--measure-import-surface", action="store_true",
                    help="动态实测裁定 34.1 的可红条件（imageio/uv 在不在 ACT 链路 import 面），"
                         f"产物写 {IMPORT_SURFACE_ARTIFACT.relative_to(ROOT)}；"
                         "manifest 生成时只**读**这份产物，不重跑（要起 8 个子进程）。")
    ap.add_argument("--surface-python", default=None,
                    help="--measure-import-surface 用哪个解释器（默认解析 lerobot_eval）")
    args = ap.parse_args()

    venv_path = Path(args.venv)
    interpreter = args.interpreter
    interpreter_switched = None
    if args.interpreter == sys.executable:
        candidate = venv_path / "bin" / "python"
        if candidate.exists() and not _same_environment(str(candidate)):
            # 裁定 33.4 同源纪律：`--venv` 指到别的 venv 时，探针必须跟着指过去，
            # 否则「标签是 A、数字是 B」。显式给了 --interpreter 就不动。
            interpreter = str(candidate)
            interpreter_switched = (f"--interpreter 未显式给 ⇒ 跟随 --venv 用它自己的解释器"
                                    f"（{interpreter}）；本脚本进程仍是 {sys.executable}")
    lock_is_default = (Path(args.lock).resolve() == DEFAULT_LOCK.resolve())

    started = time.time()
    import_surface = None
    if args.measure_import_surface:
        surface_python = args.surface_python or _resolve_venv(LEROBOT_ENVS[1])["python"]
        modules = [Path(rel).stem for rel in ACT_CHAIN_SCRIPTS]
        modules = [f"scripts.{Path(rel).stem}" for rel in ACT_CHAIN_SCRIPTS]
        modules.append(UPSTREAM_REFERENCE_ENTRY)
        print(f"动态实测 import 面（{len(modules)} 个模块，解释器 {surface_python}）…", flush=True)
        import_surface = _measure_import_surface(surface_python, modules,
                                                 out_path=IMPORT_SURFACE_ARTIFACT)
        print(f"-> {IMPORT_SURFACE_ARTIFACT}")
    elif IMPORT_SURFACE_ARTIFACT.exists():
        try:
            import_surface = json.loads(IMPORT_SURFACE_ARTIFACT.read_text(encoding="utf-8"))
        except Exception as exc:                               # noqa: BLE001
            print(f"!! {IMPORT_SURFACE_ARTIFACT.name} 读不出（{type(exc).__name__}）⇒ "
                  "裁定 34.1 的可红条件只有静态一半证据")
    manifest = build_manifest(venv=venv_path, lock=Path(args.lock),
                              interpreter=interpreter,
                              occurred_at=args.occurred_at, ready_at=args.ready_at,
                              import_surface=import_surface, lock_is_default=lock_is_default)
    manifest["elapsed_sec"] = round(time.time() - started, 2)

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest["previous_manifest"] = _archive_previous(out)
    manifest["changed_fields"] = _changed_fields(manifest["previous_manifest"], manifest)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    conf = manifest["lock_conformance"]
    baseline_applies_out = manifest["inherited_packages"]["baseline_applies_to_this_venv"]
    groups = manifest["probe_modules_by_interpreter"]
    required = set(manifest["probe_module_classes"]["required_for_c_regression"])
    rlrobot = groups["rlrobot"]
    bad_probes = rlrobot["missing_required"]
    lerobot_groups_out = {n: g for n, g in groups.items() if n != "rlrobot"}
    mismatched = {n: (g["semantic_probe"].get("not_ok") or [])
                  for n, g in lerobot_groups_out.items()
                  if any(m["status"] == "version_mismatch"
                         for m in (g["semantic_probe"].get("modules") or {}).values())}
    arts = manifest["verification"]["selfcheck_summary"]
    print(f"解释器      : {manifest['interpreter']['sys_executable']} -> realpath "
          f"{manifest['interpreter']['realpath']} ({manifest['interpreter']['version']})")
    if interpreter_switched:
        print(f"探针解释器  : {interpreter_switched}")
    print(f"lock        : {manifest['lock']['path']}（{manifest['lock']['n_pins']} pin）"
          f" 适用于本 venv={conf['lock_applies_to_this_venv']}")
    print(f"venv        : {manifest['venv']['path']} exists={manifest['venv']['exists']} "
          f"created_at={manifest['venv']['created_at']} ready_at={manifest['venv']['ready_at']}")
    print(f"sys.prefix  : {manifest['interpreter']['sys_prefix']} "
          f"(is_venv={manifest['interpreter']['is_venv']}, "
          f"inside_requested={manifest['interpreter']['runs_inside_requested_venv']})")
    print(f"lock 一致性 : {conf['counts']} all_pinned_match={conf['all_pinned_match']}")
    win = manifest["venv"]["window"]
    print(f"venv 身份   : {manifest['venv']['realpath']} 类型={manifest['venv']['venv_type']}"
          f" 软链={manifest['venv']['is_symlink']} NFS={manifest['venv']['on_persistent_nfs']}")
    print(f"窗口同源    : source_kind={win['source_kind']} same_source={win['same_source']} "
          f"consistent={win['window_consistent']}"
          + (f"；拒绝的证据 {len(win['rejected_sources'])} 条" if win["rejected_sources"] else ""))
    inh = manifest["inherited_packages"]
    print(f"8 个包      : {inh['versions']}（{inh['venv_type']} ⇒ "
          f"{'venv 内本地包' if inh['venv_type'] == 'clean' else 'base 继承包'}）")
    print(f"设计性排除  : {inh['excluded_by_design']['status']} "
          f"可导入={inh['excluded_by_design']['importable']}（clean venv 里应为空）")
    print(f"8 包断言    : {inh['assertion'].get('status')}"
          + (f"（不符 {inh['assertion'].get('failed')}）" if inh["assertion"].get("failed") else "")
          + (f"（{inh['assertion'].get('reason')}）" if inh["assertion"].get("reason") else ""))
    flat = manifest["probe_modules"]
    print(f"探针分组    : {list(groups)}（裁定 31.2：按解释器分组，lerobot 不在 rlrobot 里探）")
    print(f"扁平视图    : probe_modules 共 {len(flat)} 行"
          f"（对外口径，A 的 E6 在读）；lerobot={flat['lerobot']['version']} "
          f"probed_in={flat['lerobot']['probed_in']} 两解释器一致="
          f"{flat['lerobot']['both_interpreters_agree']}")
    own_label = "rlrobot" if baseline_applies_out else f"{manifest['venv']['path'].split('/')[-1]}*"
    print(f"  {own_label:10s}: required {len(required) - len(bad_probes)}/{len(required)} OK"
          + ("" if baseline_applies_out else "（这 13 项对本 venv **不适用**，只是观测）")
          + (f"，失败 {bad_probes}" if bad_probes else "")
          + f"；lerobot 在此 = {'not_applicable' if rlrobot['lerobot_missing_here_is_by_design'] else 'present'}"
                "（裁定 33.4 C-F1：设计如此，不算缺口、不阻 A 线）"
          + f"；pyvenv 断言 {'过' if rlrobot['pyvenv']['all_pass'] else rlrobot['pyvenv']['failed']}")
    for name, group in lerobot_groups_out.items():
        probe = group["semantic_probe"]
        src = (group["lerobot_install_source"] or {})
        print(f"  {name:12s}: status={group['status']} path={group['path']}"
              f"{'（-> NFS 持久）' if group['on_persistent_nfs'] else ''}"
              f" lerobot={group['lerobot_version']}"
              f" pin={group['pins']['values'].get('lerobot')}"
              f" 相符={group['lerobot_version_matches_pin']}"
              f" 来源={src.get('kind')}/{src.get('installer')}"
              + (f" 不符项 {probe.get('not_ok')}" if probe.get("not_ok") else "")
              + (f" pyvenv 断言未过 {group['pyvenv']['failed']}"
                 if not group["pyvenv"]["all_pass"] else ""))
    print(f"环境是否完全恢复: {manifest['env_fully_restored']}"
          f"（复现主张被阻={manifest['reproduction_claims_blocked']['blocked']}）")
    for cond in manifest["env_fully_restored_conditions"]:
        if not cond["pass"]:
            print(f"  未过条件  : {cond['condition']} -> {cond['detail']}")
    adj = manifest["reproduction_claims_blocked"]["adjudication"]
    print(f"裁定 34.1   : 可红条件触发={adj['void_condition_triggered']}"
          f"（静态命中 {adj['static_evidence']['hits']} / 动态命中 {adj['dynamic_evidence']['hits']}"
          f"，动态实测={'有' if adj['dynamic_evidence']['available'] else '无'}）"
          f" ⇒ {'差异回到阻塞项' if adj['void_condition_triggered'] else '差异已放行（按包按链路）'}")
    for item in manifest["reproduction_claims_blocked"]["pending_rulings"]:
        print(f"  待裁定    : {item['what']}（{item['who_explains']} 解释 / {item['who_rules']} 裁定）"
              f" -> {item['diff']}")
    for key in ("venv_window_selftest", "snapshot_consistency_selftest"):
        tst = manifest["verification"][key]
        print(f"{key}: ran={tst.get('ran')} all_match={tst.get('all_match')} "
              f"（{len(tst.get('rows') or [])} 格）")
    st = manifest["verification"]["breakpoint_classifier_selftest"]
    print(f"断点分类自测: ran={st.get('ran')} all_match={st.get('all_match')} "
          f"（{len(st.get('rows') or [])} 格；真数据里 before/during 可能为空过，故自测）")
    print(f"自检产物    : {arts['n_artifacts']} 份（pass {arts['n_pass']} / not-pass {arts['n_not_pass']}）"
          f"；断点后 {arts['n_after_breakpoint']}、重建窗口内 {arts['n_during_rebuild']}、"
          f"断点前 {arts['n_before_breakpoint']}")
    print(f"门禁构建    : {manifest['verification']['gate_current_at_manifest_time']}")
    for bp in manifest["breakpoints"]:
        extra = ""
        if "released" in bp:
            unmet = [c["condition"] for c in bp["release_conditions"] if c["met"] is not True]
            extra = f" released={bp['released']}" + (f"（未满足/测不到 {len(unmet)} 条）" if unmet else "")
        if "applies_to_described_venv" in bp:
            extra += f" 描述本次 venv={bp['applies_to_described_venv']}"
        print(f"断点        : {bp['id']} occurred_at={bp.get('occurred_at')} "
              f"ready_at={bp.get('ready_at')}{extra}")
        if bp.get("invalidates"):
            print(f"              invalidates: {str(bp['invalidates'])[:150]}")
    print(f"-> {out}")

    if args.check:
        if not conf["lock_applies_to_this_venv"]:
            print(f"!! lock 一致性闸**不适用**（--lock 是 rlrobot 的门禁产物，被描述的是 "
                  f"{manifest['venv']['realpath']}）⇒ 本次不判 mismatch；观测值照实记在 "
                  "lock_conformance.rows 里。")
        elif not conf["all_pinned_match"]:
            print("!! lock 一致性闸未过（exit=3）：", flush=True)
            for row in conf["rows"]:
                if row["status"] != "match":
                    print(f"   {row['status']:9s} {row['package']} pinned={row['pinned']} "
                          f"installed={row['installed']}")
            raise SystemExit(3)
        if bad_probes and baseline_applies_out:
            print(f"!! lock 一致但 required import 探测有失败（exit=3）：{bad_probes}")
            raise SystemExit(3)
        if bad_probes and not baseline_applies_out:
            print(f"   required 探测有失败但**不适用于本 venv**（这 13 项是 C 在 rlrobot 里的回归"
                  f"依赖）：{bad_probes}")
        selftest = manifest["verification"]["breakpoint_classifier_selftest"]
        if selftest.get("ran") and not selftest.get("all_match"):
            print("!! 断点分类规则自测未过（exit=3）：",
                  [r for r in selftest["rows"] if r["got"] != r["expected"]])
            raise SystemExit(3)
        win_selftest = manifest["verification"]["venv_window_selftest"]
        if win_selftest.get("ran") and not win_selftest.get("all_match"):
            print("!! 窗口判据自测未过（exit=3）：",
                  [r for r in win_selftest["rows"] if not r["match"]])
            raise SystemExit(3)
        snap_selftest = manifest["verification"]["snapshot_consistency_selftest"]
        if snap_selftest.get("ran") and not snap_selftest.get("all_match"):
            # 双向自测：恒红（只改 at 就判不自洽）与恒绿（改身份也不判）都算未过。
            print("!! 快照自洽判据自测未过（exit=3）：",
                  [r for r in snap_selftest["rows"] if not r["match"]])
            raise SystemExit(3)
        if win["same_source"] and not win["window_consistent"]:
            # 同源证据却给出倒置窗口 ⇒ 真矛盾（不是「测不到」），必须红。
            print(f"!! 窗口倒置（exit=3）：occurred_at={win['occurred_at']} > "
                  f"ready_at={win['ready_at']}，source_kind={win['source_kind']}")
            raise SystemExit(3)
        if not win["same_source"]:
            print("!! 窗口**不可得**（没有与被描述 venv 同源的证据）⇒ before/during/after 归属一律记 "
                  "null；不是失败，但不得当成 after 读。可用 --occurred-at/--ready-at 显式给。")
        if mismatched:
            # 「装了但装错版本」比「没装」更坏：import 照样成功，只验可导入的探针会放它过去
            # （裁定 31.2 / DR-012：`import lerobot` 是恒真判据）。所以单给一个 exit code，
            # 与「C 自己回归所需依赖缺失」（exit 3）区分开。
            print("!! lerobot 语义探针版本不符（exit=4）：装了但装错，比没装更坏")
            for name, bad in mismatched.items():
                for mod in bad:
                    row = lerobot_groups_out[name]["semantic_probe"]["modules"][mod]
                    print(f"   {name}: {mod} expected={row['expected_version']} "
                          f"observed={row['observed_version']} source="
                          f"{(row['install_source'] or {}).get('kind')}")
            raise SystemExit(4)
        print(f"lock 一致性闸：PASS（{conf['counts'].get('match', 0)}/{manifest['lock']['n_pins']} "
              f"pin 全中"
              + (f"，required {len(required)} 项 import 探测全 OK）" if baseline_applies_out
                 else "；required 那 13 项对本 venv 不适用）"))
        if not manifest["env_fully_restored"]:
            # 闸过 ≠ 环境全恢复：这条必须每次都喊出来（裁定 29.4 的核心风险就是
            # 「manifest 全绿」被读成「环境已完全恢复」）。
            print("!! 但 env_fully_restored=false：见上面「未过条件」逐条 ⇒ "
                  "**A 线的一切新训练/新评测复现主张仍被阻**（裁定 29.4 / 31.2）。"
                  "本闸只覆盖 C 的只读回归所需依赖。")
        elif manifest["reproduction_claims_blocked"]["blocked"]:
            print("!! env_fully_restored=true 但复现主张仍被阻：重建 lock 与 0928 lock 有差异，"
                  "待 A 解释、D 裁定（裁定 32.4）。**环境装对了 ≠ 跨断点的复现主张解封**。")


if __name__ == "__main__":
    main()
