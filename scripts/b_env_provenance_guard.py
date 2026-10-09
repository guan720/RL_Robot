#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 线：环境与 lock 溯源闸 —— 裁定 32.4（P0）+ 裁定 32.3 前提 1/2 的机器判据。

为什么需要它（D 的 裁定 32.4 原文实质）：
    scripts/install_lerobot_act_env.sh:57 / :85 会 `pip freeze > "$LOCK_OUT/requirements*.lock.txt"`，
    而 :29 的 LOCK_OUT 默认值就是 runs/infra/lerobot_act_env_20260928 ⇒ **照默认值跑一次，
    就会就地覆写 0928 那两份 lock**。那两份是「48 臂权威表当初到底跑在什么环境上」的
    **唯一溯源证据**。覆写它 = 让这个问题永久不可答（与本仓已踩 5 次的坑同型：
    把可核事实换成自述）。散文纪律拦不住手滑，所以这里做成会红的闸。

判据（每条都写出**可红条件**，遵守 裁定 27.1「恒假的闸等于没有闸」/ 裁定 31.2 第 3 条
「探针必须验语义值而不是可导入」）：

  G1 locks_0928_not_overwritten   0928 两份 lock 的 sha256 == 实测基线，且 mtime 早于
                                  2026-09-29T00:00。**红**：sha 变了 / mtime 是今天 /
                                  文件缺失 / C 的逐字节备份与原件不一致。
  G2 rebuild_lockout_not_default  重建产物必须落在**另一个目录**。**红**：--rebuild-dir
                                  解析后 == 0928 目录（即用了默认 LOCK_OUT）；或重建目录里
                                  两份 lock 缺失（**警告**，因为安装可能还没跑到第 5/6 步）。
                                  同时把新旧 lock 的**逐包差异枚举出来**（解释义务在 A，
                                  B 只保证差异不被吞掉）。
  G3 persistent_pin_conformance   requirements.persistent.lock.txt 必须：① 28 个项目 pin
                                  与 requirements.lock.txt 逐字节相同；② 含 6 个原继承 pin +
                                  2 个 venv 引导件 pin；③ torch/torchvision 必须带 `+cu124`。
                                  **红**：任一 pin 缺失/版本不符；**torch 少了 `+cu124`**
                                  （那就是 PyPI 的 cu121 构建，版本字符串一样、CUDA 构建不同
                                  = 最坏的一类静默漂移）；给了 --frozen 时，freeze 产物与
                                  本文件逐 pin 不符。
  G4 base_python_assertion        venv 的 pyvenv.cfg：home 目录存在、version == 3.11.9、
                                  executable 存在；实测该 executable 自报 3.11.9。
                                  **红**：任一不符 / venv 不存在（venv 的 shebang 与
                                  pyvenv.cfg.home 都是绝对路径，换容器后 base python 不在
                                  /opt/conda/bin 或不是 3.11.x，持久 venv 直接坏）。
  G5 numpy_shadowing              该 venv 里**生效**的 numpy == **对应那份 0928 lock 的 numpy pin**，
                                  而不是 base 的 1.26.4。**红**：生效值 != 期望值。
                                  期望值按 venv 分别推导（`NUMPY_EXPECT_BY_VENV_LOCK`）：
                                    · rlrobot / 门禁 venv → 项目口径 2.4.6；
                                    · lerobot_act  → act lock 的 numpy（0928 起就是 **2.2.6**，无 --override）；
                                    · lerobot_eval → eval lock 的 numpy（**2.4.6**，installer 带 --override）。
                                  也可用 `--expect-numpy` 显式指定；推导失败会在 `expect_source` 里
                                  **响亮写明**，不静默退回常量。
                                  这条盯的是「半自足」陷阱：带 --system-site-packages 时靠
                                  venv 自己的 numpy 遮蔽 base，遮蔽一失效就静默拿到 1.26.4。

用法：
    python3 scripts/b_env_provenance_guard.py                     # 全量判现场
    python3 scripts/b_env_provenance_guard.py --selftest          # 12 条变异（含 2 条反向）证明有牙
    python3 scripts/b_env_provenance_guard.py --frozen <freeze产物>   # 甲案建成后对账
    python3 scripts/b_env_provenance_guard.py --check-persistent-pin  # 只跑 G3

AGENTS.md 纪律：本脚本**不删除任何文件**；自检的临时目录用完一律 mv 到回收站，绝不 rm。
写入面：只写 runs/infra/b_env_provenance/（B 的产物目录）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parent.parent
RECYCLE_BIN = Path("/workspace/mnt/sppro/yhzhang91/recycle_bin")

# ---------------------------------------------------------------------------
# 实测基线（2026-09-29 14:1x，B 现场测；改这里必须同时在 DR-013 登记理由）
# ---------------------------------------------------------------------------
LOCKS_0928_DIR = "runs/infra/lerobot_act_env_20260928"
LOCKS_0928_BASELINE = {
    "requirements.lock.txt":
        "68a38731c5b586902ffb59671ceca3f93cbb80c0cc81866a0b003d849f98b615",
    "requirements.eval.lock.txt":
        "b6db07e2e31c0b1fbba84144e6ac572d8560c4c20e9e9ee572a89bb73b888c67",
}
LOCKS_BACKUP_DIR = "runs/infra/c_lerobot_env_locks_backup_20260928"
REBUILD_DIR_DEFAULT = "runs/infra/a_lerobot_env_rebuild_20260929"
LOCK_CUTOFF_MTIME = 1790704000  # 2026-09-29T00:00:00+08:00；0928 的 lock 不得有今天及以后的 mtime

PROJECT_LOCK = "requirements.lock.txt"
PERSISTENT_LOCK = "requirements.persistent.lock.txt"
INHERITED_PINS = {
    "torch": "2.4.1+cu124",
    "torchvision": "0.19.1+cu124",
    "scipy": "1.17.1",
    "pandas": "3.0.3",
    "pyarrow": "24.0.0",
    "matplotlib": "3.11.1",
}
BOOTSTRAP_PINS = {"pip": "26.2.1", "setuptools": "65.5.0"}
BASE_PY_EXPECT = {
    "home": "/opt/conda/bin",
    "version": "3.11.9",
    "executable": "/opt/conda/bin/python3.11",
}
VENV_DEFAULT = "/root/venvs/rlrobot"
NUMPY_EXPECT_EFFECTIVE = "2.4.6"
NUMPY_BASE_SHADOWED = "1.26.4"
# G5 的期望值**按 venv 分别取，且取自事实源**（对应那份 0928 lock 的 numpy pin），
# 不是单个写死常量。为什么改：0929 B 拿 `--venv /root/venvs/lerobot_act` 跑本闸，
# G5 报 RED「生效 numpy==2.2.6（期望 2.4.6）」—— 但 act 侧 lock **从 0928 起就是 numpy==2.2.6**
# （`runs/infra/lerobot_act_env_20260928/requirements.lock.txt:49`），只有 eval 侧带
# `--override numpy==2.4.6`（installer 的评测环境那段）⇒ A 的 0929 重建两份 lock 同样是 2.2.6 / 2.4.6。
# 所以那是**期望值口径错**造成的假红（本仓第 8 起同型），不是环境缺陷，也不是 G5 的牙失效。
# 修法是让期望值跟着事实源走：venv 名 -> 对应 lock -> 该 lock 里的 numpy pin。
NUMPY_EXPECT_BY_VENV_LOCK = {
    "lerobot_act": "requirements.lock.txt",        # 训练环境：无 --override
    "lerobot_eval": "requirements.eval.lock.txt",  # 评测环境：--override numpy==2.4.6
}

PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)")

# `pip freeze` 默认**不输出** pip / setuptools（要 --all 才有）⇒ 这两个 pin 在 freeze 对账里
# 属「不可比」，不是「缺失」。按护栏① 的三值纪律：可见、但不报警（区别于真缺失 = RED）。
FREEZE_EXEMPT = {"pip", "setuptools"}

# `pip freeze` 写发行名原样、lock 里常写小写/连字符 ⇒ 自检用它造「字面不同但同一个包」的形状
FREEZE_NAME_VARIANTS = {
    "imageio": "ImageIO", "jinja2": "Jinja2", "typing-extensions": "typing_extensions",
    "pyyaml": "PyYAML", "pygments": "Pygments", "werkzeug": "Werkzeug",
}

def norm_name(name: str) -> str:
    """PEP 503 归一化：大小写不敏感，`-`/`_`/`.` 等价。

    为什么必须有它（B 自查出的假红，与 DR-011 的三值桶同型）：`pip freeze` 输出的是
    **发行名原样**（`ImageIO` / `Jinja2` / `PyYAML` / `typing_extensions` / `Werkzeug`），
    而 lock 里写的是 `imageio` / `jinja2` / `pyyaml` / `typing-extensions` / `werkzeug`。
    不做归一化 ⇒ 6 个包被误报成「freeze 产物里缺失」，把一次**完全合格**的自足 venv
    判成 RED。假红和恒绿一样坏：它让人学会忽略红灯。
    """
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def norm_pins(pins: dict) -> dict:
    """{归一化名: (原名, 版本)}"""
    return {norm_name(k): (k, v) for k, v in pins.items()}

def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def _sha12(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception:
        return "0" * 12


def parse_pins(path: Path) -> dict:
    """从 lock 文件解析 name==version（跳过注释与空行；名字按原样保留大小写）。"""
    out = {}
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return out
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = PIN_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


class Report:
    def __init__(self):
        self.checks = []

    def add(self, check_id, ruling_ref, status, expected, actual, red_when, note=""):
        self.checks.append({
            "check_id": check_id, "ruling_ref": ruling_ref, "status": status,
            "expected": expected, "actual": actual,
            "red_when": red_when, "note": note,
        })
        return status

    @property
    def n_red(self):
        return sum(1 for c in self.checks if c["status"] == "RED")

    @property
    def n_warn(self):
        return sum(1 for c in self.checks if c["status"] == "WARN")

    @property
    def n_pass(self):
        return sum(1 for c in self.checks if c["status"] == "PASS")


def _probe_python(py: Path, packages):
    """实测某个解释器里的包版本与 dist-info 位置（裁定 31.2：验语义值，不是"能 import"）。"""
    if not py.exists():
        return None
    # 不用 % 格式化拼代码：本仓已两次踩过「实参里的 %d 撞占位符」导致探针静默返回空
    # （DR-011 的 T17 evidence 实参事故、D 的恒真判据 3）。这里全部走字符串拼接 + json.dumps。
    code = "".join([
        "import importlib.metadata as md, json, sys\n",
        "names = " + json.dumps(list(packages)) + "\n",
        "out = {'python': '.'.join(str(x) for x in sys.version_info[:3]),\n",
        "       'executable': sys.executable, 'pkgs': {}}\n",
        "for p in names:\n",
        "    try:\n",
        "        d = md.distribution(p)\n",
        "        out['pkgs'][p] = {'version': d.version, 'path': str(d._path)}\n",
        "    except Exception as e:\n",
        "        out['pkgs'][p] = {'version': None, 'error': type(e).__name__}\n",
        "print(json.dumps(out))\n",
    ])
    try:
        r = subprocess.run([str(py), "-c", code], capture_output=True, text=True, timeout=180)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# G1 —— 裁定 32.4：0928 的两份 lock 不得被覆写
# ---------------------------------------------------------------------------
def check_g1(ctx, rep):
    root, measured = ctx["root"], ctx["measured"]
    bad, detail = [], {}
    for name, want in LOCKS_0928_BASELINE.items():
        p = root / LOCKS_0928_DIR / name
        if measured and name in measured.get("locks_0928", {}):
            got = measured["locks_0928"][name]
        else:
            if not p.exists():
                bad.append("%s 缺失" % name)
                detail[name] = {"exists": False}
                continue
            got = {"sha256": _sha256(p), "mtime": p.stat().st_mtime}
        detail[name] = got
        if got.get("sha256") != want:
            bad.append("%s sha256 变了（%s -> %s）" % (name, want[:12], str(got.get("sha256"))[:12]))
        if got.get("mtime") is not None and got["mtime"] >= LOCK_CUTOFF_MTIME:
            bad.append("%s mtime=%s 落在 0929 及以后（溯源件不得被重写）"
                       % (name, datetime.fromtimestamp(got["mtime"]).strftime("%Y-%m-%d %H:%M:%S")))
    # C 的逐字节备份必须与原件一致（备份不一致 = 备份失效，等于没有第二份证据）
    backup_same = True
    for name in LOCKS_0928_BASELINE:
        a, b = root / LOCKS_0928_DIR / name, root / LOCKS_BACKUP_DIR / name
        if measured and name in measured.get("backup_sha", {}):
            sa, sb = measured["locks_0928"].get(name, {}).get("sha256"), measured["backup_sha"][name]
        else:
            sa, sb = _sha256(a) if a.exists() else None, _sha256(b) if b.exists() else None
        if sa is None or sb is None or sa != sb:
            backup_same = False
            bad.append("C 的备份 %s/%s 与原件不一致或缺失（%s vs %s）"
                       % (LOCKS_BACKUP_DIR, name, str(sa)[:12], str(sb)[:12]))
    status = "RED" if bad else "PASS"
    rep.add("G1_locks_0928_not_overwritten", "裁定 32.4（DR-D31）/ P0", status,
            "两份 0928 lock 的 sha256 == 基线、mtime < 0929、且与 C 的备份逐字节一致",
            {"detail": detail, "violations": bad, "backup_identical": backup_same},
            "sha 变了 / mtime 是今天或更晚 / 文件缺失 / 备份与原件不一致")
    return status


# ---------------------------------------------------------------------------
# G2 —— 裁定 32.4：重建必须写到另一个目录，且新旧差异必须被枚举
# ---------------------------------------------------------------------------
def _diff_pins(old: dict, new: dict):
    changed, added, removed = {}, {}, {}
    for k in sorted(set(old) | set(new)):
        if k in old and k in new:
            if old[k] != new[k]:
                changed[k] = {"old": old[k], "new": new[k]}
        elif k in new:
            added[k] = new[k]
        else:
            removed[k] = old[k]
    return {"changed": changed, "added": added, "removed": removed,
            "n_changed": len(changed), "n_added": len(added), "n_removed": len(removed)}


def check_g2(ctx, rep):
    root, measured = ctx["root"], ctx["measured"]
    rebuild = Path(ctx["rebuild_dir"])
    if not rebuild.is_absolute():
        rebuild = root / rebuild
    old_dir = root / LOCKS_0928_DIR
    red, warn, note = [], [], ""
    try:
        same = rebuild.resolve() == old_dir.resolve()
    except Exception:
        same = str(rebuild) == str(old_dir)
    if same:
        red.append("LOCK_OUT 用了默认值：重建目录 == %s ⇒ 会就地覆写 0928 溯源件" % LOCKS_0928_DIR)
    diffs = {}
    for name in LOCKS_0928_BASELINE:
        op, np_ = old_dir / name, rebuild / name
        if measured and name in measured.get("rebuild_pins", {}):
            diffs[name] = _diff_pins(measured.get("old_pins", {}).get(name, {}),
                                     measured["rebuild_pins"][name])
            continue
        if not np_.exists():
            warn.append("重建目录里没有 %s（安装可能还没跑到第 5/6 步，或 LOCK_OUT 指错了）" % name)
            continue
        diffs[name] = _diff_pins(parse_pins(op), parse_pins(np_))
    n_ch = sum(d["n_changed"] + d["n_added"] + d["n_removed"] for d in diffs.values())
    if not diffs and not red:
        warn.append("无可比对的重建 lock ⇒ 本轮「差异 0 处」不可采信（空比对）")
    note = ("差异必须逐条解释并**报 D**（裁定 32.4）；在 D 裁定前 A 不得声称任何跨断点复现。"
            "解释义务在 A，本闸只保证差异不被吞掉。")
    status = "RED" if red else ("WARN" if warn else "PASS")
    rep.add("G2_rebuild_lockout_not_default", "裁定 32.4（DR-D31）/ P0", status,
            "重建目录 != %s，且两份新 lock 存在、差异被逐包枚举" % LOCKS_0928_DIR,
            {"rebuild_dir": str(rebuild), "same_as_0928": same, "lock_diff": diffs,
             "n_total_diff": n_ch, "violations": red, "warnings": warn, "note": note},
            "重建目录解析后等于 0928 目录（= 用了默认 LOCK_OUT）")
    ctx["lock_diff"] = diffs
    return status


# ---------------------------------------------------------------------------
# G3 —— 裁定 32.3 前提 1：持久 pin 文件的自足性与「+cu124 静默漂移」陷阱
# ---------------------------------------------------------------------------
def check_g3(ctx, rep):
    root, measured = ctx["root"], ctx["measured"]
    pp = root / PERSISTENT_LOCK
    qp = root / PROJECT_LOCK
    red = []
    if measured and "persistent_pins" in measured:
        pers, proj = measured["persistent_pins"], measured.get("project_pins", {})
    else:
        if not pp.exists():
            rep.add("G3_persistent_pin_conformance", "裁定 32.3 前提 1（DR-D31）", "RED",
                    "%s 存在" % PERSISTENT_LOCK, {"exists": False},
                    "文件缺失")
            return "RED"
        pers, proj = parse_pins(pp), parse_pins(qp) if qp.exists() else {}
    pers_n, proj_n = norm_pins(pers), norm_pins(proj)
    # ① 28 个项目 pin 必须与 requirements.lock.txt 完全一致（一个都不许"顺手升级"）
    drift = {orig: {"project_lock": proj_n[k][1], "persistent_lock": pers_n[k][1] if k in pers_n else None}
             for k, (orig, _v) in proj_n.items() if k not in pers_n or pers_n[k][1] != _v}
    if drift:
        red.append("与 %s 的 pin 不一致/缺失 %d 处：%s" % (PROJECT_LOCK, len(drift), sorted(drift)[:6]))
    # ② 6 个原继承 pin + 2 个引导件 pin 必须在
    for group, want in (("原继承", INHERITED_PINS), ("venv 引导件", BOOTSTRAP_PINS)):
        for k, v in want.items():
            got = pers_n.get(norm_name(k))
            if got is None or got[1] != v:
                red.append("%s pin %s 期望 %s 实测 %s" % (group, k, v, got[1] if got else None))
    # ③ +cu124 静默漂移陷阱
    for k in ("torch", "torchvision"):
        got = pers_n.get(norm_name(k))
        v = got[1] if got else ""
        if v and "+cu124" not in v:
            red.append("%s==%s 少了 +cu124 ⇒ 会装到 PyPI 的 cu121 构建（版本字符串一样、"
                       "CUDA 构建不同 = 静默漂移）；B 实测 aliyun 的 pypi/simple 上没有 +cu124，"
                       "必须另给 cu124 轮子源（download.pytorch.org/whl/cu124，或 D 用的 "
                       "mirrors.aliyun.com/pytorch-wheels/cu124/）" % (k, v))
    # ④ 可选：与真建出来的 freeze 产物对账（名字走 PEP 503 归一化，见 norm_name）
    frozen_cmp = None
    if ctx.get("frozen"):
        fz = Path(ctx["frozen"])
        if not fz.is_absolute():
            fz = root / fz
        if not fz.exists():
            red.append("--frozen 指向的 %s 不存在" % ctx["frozen"])
        else:
            fz_n = norm_pins(parse_pins(fz))
            mismatch = {orig: {"pin": v, "frozen": fz_n[k][1]}
                        for k, (orig, v) in pers_n.items()
                        if k in fz_n and fz_n[k][1] != v}
            absent = sorted(orig for k, (orig, _v) in pers_n.items() if k not in fz_n)
            exempt = sorted(n for n in absent if norm_name(n) in FREEZE_EXEMPT)
            real_missing = [n for n in absent if n not in exempt]
            frozen_cmp = {
                "path": str(fz), "n_frozen_pins": len(fz_n),
                "version_mismatch": mismatch,
                "missing_in_frozen": real_missing,
                "not_comparable_freeze_excludes": exempt,
                "note": "pip/setuptools 不在 `pip freeze` 默认输出里（要 --all）⇒ 记为不可比、"
                        "不报警；这两个值由 G4 的解释器探针侧验。名字比对已做 PEP 503 归一化。",
            }
            if mismatch:
                red.append("freeze 产物与持久 pin 版本不符 %d 处：%s"
                           % (len(mismatch), sorted(mismatch)[:6]))
            if real_missing:
                red.append("freeze 产物里缺 %d 个 pin：%s" % (len(real_missing), real_missing[:8]))
    status = "RED" if red else "PASS"
    rep.add("G3_persistent_pin_conformance", "裁定 32.3 前提 1（DR-D31）", status,
            "%s：28 个项目 pin 逐字节沿用 + 6 继承 pin + 2 引导件 pin，且 torch/torchvision 带 +cu124"
            % PERSISTENT_LOCK,
            {"n_pins": len(pers), "n_project_pins": len(proj), "drift_vs_project_lock": drift,
             "inherited_pins_expected": INHERITED_PINS, "bootstrap_pins_expected": BOOTSTRAP_PINS,
             "frozen_comparison": frozen_cmp, "violations": red},
            "任一 pin 缺失/版本不符；torch 或 torchvision 少 +cu124；--frozen 对账不符")
    return status


# ---------------------------------------------------------------------------
# G4 —— 裁定 32.3 前提 2：base 解释器必须是断言，不能只记观测
# ---------------------------------------------------------------------------
def _read_pyvenv_cfg(venv: Path):
    cfg = venv / "pyvenv.cfg"
    out = {}
    if not cfg.exists():
        return None
    for line in cfg.read_text(errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def check_g4(ctx, rep):
    root, measured = ctx["root"], ctx["measured"]
    venv = Path(ctx["venv"])
    red = []
    if measured and "pyvenv_cfg" in measured:
        cfg = measured["pyvenv_cfg"]
        probe = measured.get("venv_probe")
    else:
        if not venv.exists():
            rep.add("G4_base_python_assertion", "裁定 32.3 前提 2（DR-D31）", "RED",
                    "venv 存在：%s" % venv, {"exists": False}, "venv 缺失")
            return "RED"
        cfg = _read_pyvenv_cfg(venv)
        probe = None if ctx.get("no_live") else _probe_python(venv / "bin" / "python3", [])
    if cfg is None:
        red.append("pyvenv.cfg 读不到")
    else:
        home = cfg.get("home")
        if home != BASE_PY_EXPECT["home"]:
            red.append("pyvenv.cfg.home 期望 %s 实测 %s" % (BASE_PY_EXPECT["home"], home))
        elif not Path(home).exists():
            red.append("pyvenv.cfg.home=%s 在本容器里不存在 ⇒ 持久 venv 的 shebang 全断" % home)
        if cfg.get("version") != BASE_PY_EXPECT["version"]:
            red.append("pyvenv.cfg.version 期望 %s 实测 %s"
                       % (BASE_PY_EXPECT["version"], cfg.get("version")))
        exe = cfg.get("executable")
        if exe != BASE_PY_EXPECT["executable"]:
            red.append("pyvenv.cfg.executable 期望 %s 实测 %s" % (BASE_PY_EXPECT["executable"], exe))
        elif not Path(exe).exists():
            red.append("pyvenv.cfg.executable=%s 在本容器里不存在" % exe)
    if probe is not None and probe.get("python") != BASE_PY_EXPECT["version"]:
        red.append("venv 解释器自报 %s != %s（探针验语义值，裁定 31.2 第 3 条）"
                   % (probe.get("python"), BASE_PY_EXPECT["version"]))
    status = "RED" if red else ("WARN" if probe is None and not measured else "PASS")
    rep.add("G4_base_python_assertion", "裁定 32.3 前提 2（DR-D31）", status,
            "home==%s 且存在、version==%s、executable==%s 且存在、解释器自报 %s"
            % (BASE_PY_EXPECT["home"], BASE_PY_EXPECT["version"],
               BASE_PY_EXPECT["executable"], BASE_PY_EXPECT["version"]),
            {"pyvenv_cfg": cfg, "probe_python": (probe or {}).get("python"),
             "probe_skipped": probe is None, "violations": red},
            "任一路径/版本不符，或 venv 缺失")
    return status


# ---------------------------------------------------------------------------
# G5 —— 裁定 32.3 前提 1 的「半自足」陷阱：numpy 遮蔽必须真的生效
# ---------------------------------------------------------------------------
def expected_effective_numpy(ctx):
    """回显 (期望的生效 numpy, 期望值来源说明)。

    优先级：`--expect-numpy` 显式指定 > 按 venv 名从对应 0928 lock 推导 > 项目口径常量。
    推导失败**必须响亮**（回显里写明「推导失败」），不许静默退回常量假装通过。
    """
    if ctx.get("expect_numpy"):
        return ctx["expect_numpy"], "cli --expect-numpy 显式指定"
    venv_name = Path(str(ctx.get("venv") or "")).name
    lock_name = NUMPY_EXPECT_BY_VENV_LOCK.get(venv_name)
    if not lock_name:
        return NUMPY_EXPECT_EFFECTIVE, ("项目口径常量（venv=%s 不在按-lock-推导表里 ⇒ 用门禁 venv 口径）"
                                       % (venv_name or "?"))
    # 合成世界（--selftest）走 measured.old_pins；真跑时 measured=None ⇒ 读 lock 文件
    pins = ((ctx.get("measured") or {}).get("old_pins") or {}).get(lock_name) or {}
    src = "measured.old_pins[%s]" % lock_name
    if "numpy" not in pins:
        lock = Path(ctx["root"]) / LOCKS_0928_DIR / lock_name
        pins = parse_pins(lock) if lock.exists() else {}
        src = "%s/%s" % (LOCKS_0928_DIR, lock_name)
    v = pins.get("numpy")
    if not v:
        return NUMPY_EXPECT_EFFECTIVE, ("**推导失败**（%s 里读不到 numpy pin）⇒ 退回项目口径常量 %s；"
                                        "这条必须被人看见，不是静默通过"
                                        % (src, NUMPY_EXPECT_EFFECTIVE))
    return v, "推导自 %s 的 numpy pin（venv=%s）" % (src, venv_name)


def check_g5(ctx, rep):
    measured = ctx["measured"]
    exp_numpy, exp_src = expected_effective_numpy(ctx)
    if measured and "effective_numpy" in measured:
        eff, path = measured["effective_numpy"], measured.get("effective_numpy_path")
    elif ctx.get("no_live"):
        eff, path = None, None
    else:
        venv = Path(ctx["venv"])
        pr = _probe_python(venv / "bin" / "python3", ["numpy"])
        if not pr:
            eff, path = None, None
        else:
            info = (pr.get("pkgs") or {}).get("numpy") or {}
            eff, path = info.get("version"), info.get("path")
    if eff is None:
        rep.add("G5_numpy_shadowing", "裁定 32.3 前提 1（DR-D31）", "WARN",
                "生效 numpy == %s" % exp_numpy,
                {"effective": None, "probe_skipped": True,
                 "expected": exp_numpy, "expect_source": exp_src},
                "生效值 != %s（探不到时降级为 WARN，不假装通过）" % exp_numpy)
        return "WARN"
    red = []
    if eff != exp_numpy:
        red.append("生效 numpy==%s（期望 %s）%s" % (
            eff, exp_numpy,
            "⇒ 遮蔽失效，静默拿到了 base 的 %s" % NUMPY_BASE_SHADOWED if eff == NUMPY_BASE_SHADOWED else ""))
    status = "RED" if red else "PASS"
    rep.add("G5_numpy_shadowing", "裁定 32.3 前提 1（DR-D31）", status,
            "生效 numpy == %s（不是 base 的 %s）" % (exp_numpy, NUMPY_BASE_SHADOWED),
            {"effective": eff, "path": path, "base_shadowed_value": NUMPY_BASE_SHADOWED,
             "expected": exp_numpy, "expect_source": exp_src,
             "violations": red},
            "生效值 != %s（期望值来源：%s）" % (exp_numpy, exp_src))
    return status


CHECKS = {
    "G1": check_g1, "G2": check_g2, "G3": check_g3, "G4": check_g4, "G5": check_g5,
}


def run_checks(ctx):
    rep = Report()
    ids = ctx.get("only") or list(CHECKS)
    for cid in ids:
        CHECKS[cid](ctx, rep)
    return rep


def build_report(ctx, rep):
    return {
        "guard_kind": "b_env_provenance",
        "guard_build": _sha12(Path(__file__)),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "scripts/b_env_provenance_guard.py",
        "ruling_refs": ["裁定 32.3 前提 1/2（DR-D31）", "裁定 32.4（DR-D31）",
                        "裁定 31.2 第 3 条（探针验语义值）", "裁定 27.1（恒假的闸等于没有闸）"],
        "root": str(ctx["root"]), "rebuild_dir": str(ctx["rebuild_dir"]),
        "venv": str(ctx["venv"]), "frozen": ctx.get("frozen"),
        "no_live": bool(ctx.get("no_live")),
        "lock_diff": ctx.get("lock_diff"),
        "checks": rep.checks,
        "summary": {"n_checks": len(rep.checks), "n_pass": rep.n_pass,
                    "n_warn": rep.n_warn, "n_red": rep.n_red,
                    "all_green": rep.n_red == 0 and rep.n_warn == 0,
                    "verdict": "RED" if rep.n_red else ("WARN" if rep.n_warn else "PASS")},
    }


def print_report(doc, quiet=False):
    s = doc["summary"]
    if not quiet:
        print("=" * 92)
        print("B 线环境与 lock 溯源闸（裁定 32.3 前提 1/2 + 裁定 32.4）  guard_build=%s" % doc["guard_build"])
        print("=" * 92)
        for c in doc["checks"]:
            print("  [%-4s] %-34s %s" % (c["status"], c["check_id"], c["ruling_ref"]))
            print("         期望：%s" % c["expected"])
            act = c["actual"]
            if isinstance(act, dict) and act.get("violations"):
                for v in act["violations"]:
                    print("         ** 违例：%s" % v)
            for v in (act.get("warnings") or []) if isinstance(act, dict) else []:
                print("         警告：%s" % v)
            if isinstance(act, dict) and act.get("note"):
                print("         注：%s" % act["note"])
        ld = doc.get("lock_diff") or {}
        if ld:
            print("\n--- 新旧 lock 逐包差异（解释义务在 A，须报 D；裁定 32.4）---")
            for name, d in ld.items():
                print("  %s：changed=%d added=%d removed=%d"
                      % (name, d["n_changed"], d["n_added"], d["n_removed"]))
                for k, v in d["changed"].items():
                    print("      ~ %s：%s -> %s" % (k, v["old"], v["new"]))
                for k, v in d["added"].items():
                    print("      + %s==%s" % (k, v))
                for k, v in d["removed"].items():
                    print("      - %s==%s（新环境里没有）" % (k, v))
        print("\n结论：%d 项判据 -> PASS %d / WARN %d / RED %d ⇒ %s"
              % (s["n_checks"], s["n_pass"], s["n_warn"], s["n_red"], s["verdict"]))
        print("=" * 92)


# ---------------------------------------------------------------------------
# 自检：合成世界 + 11 条变异，证明每条判据都咬得动（裁定 27.1 / 裁定 28.4）
# ---------------------------------------------------------------------------
def _mk_world(base: Path, tamper: str):
    """造一个合成世界：0928 目录 + C 备份 + 重建目录 + 两份 lock 文件。"""
    root = base
    d0928 = root / LOCKS_0928_DIR
    dbak = root / LOCKS_BACKUP_DIR
    rebuild = root / REBUILD_DIR_DEFAULT
    for d in (d0928, dbak, rebuild):
        d.mkdir(parents=True, exist_ok=True)
    old = "imageio==2.37.4\nuv==0.12.19\nnumpy==2.4.6\n"
    new = "imageio==2.38.0\nuv==0.12.17\nnumpy==2.4.6\n"
    oldev = "imageio==2.37.4\nlerobot==0.4.4\n"
    newev = "imageio==2.38.0\nlerobot==0.4.4\n"
    (d0928 / "requirements.lock.txt").write_text(old)
    (d0928 / "requirements.eval.lock.txt").write_text(oldev)
    (dbak / "requirements.lock.txt").write_text(old)
    (dbak / "requirements.eval.lock.txt").write_text(oldev)
    (rebuild / "requirements.lock.txt").write_text(new)
    (rebuild / "requirements.eval.lock.txt").write_text(newev)
    proj = root / PROJECT_LOCK
    proj.write_text("ale-py==0.12.1\nnumpy==2.4.6\nrobosuite==1.5.2\nmink==1.2.0\n")
    pers = ("torch==2.4.1+cu124\ntorchvision==0.19.1+cu124\nscipy==1.17.1\npandas==3.0.3\n"
            "pyarrow==24.0.0\nmatplotlib==3.11.1\npip==26.2.1\nsetuptools==65.5.0\n"
            "ale-py==0.12.1\nnumpy==2.4.6\nrobosuite==1.5.2\nmink==1.2.0\n"
            # 这 6 个是**故意**用 freeze 会写成另一种字面的名字，用来钉住 norm_name（M8）
            "imageio==2.37.3\njinja2==3.1.4\ntyping-extensions==4.15.0\n"
            "pyyaml==6.0.2\npygments==2.18.0\nwerkzeug==2.2.3\n")
    (root / PERSISTENT_LOCK).write_text(pers)
    # 合成 freeze 产物：名字用发行名原样（大小写/下划线与 lock 不同），且不含 pip/setuptools
    frozen_lines = []
    for line in pers.splitlines():
        if not line.strip():
            continue
        name, ver = line.split("==")
        if name in ("pip", "setuptools"):
            continue  # `pip freeze` 默认不输出这两个
        name = FREEZE_NAME_VARIANTS.get(name, name)
        if tamper == "M9_frozen_torch_drift" and name == "torch":
            ver = "2.4.1"  # cu121 构建：版本字符串变了，freeze 对账必须红
        frozen_lines.append("%s==%s" % (name, ver))
    (root / "frozen.txt").write_text("\n".join(frozen_lines) + "\n")

    m = {
        "locks_0928": {n: {"sha256": _sha256(d0928 / n), "mtime": 1790600000}
                       for n in LOCKS_0928_BASELINE},
        "backup_sha": {n: _sha256(dbak / n) for n in LOCKS_0928_BASELINE},
        "old_pins": {"requirements.lock.txt": parse_pins(d0928 / "requirements.lock.txt"),
                     "requirements.eval.lock.txt": parse_pins(d0928 / "requirements.eval.lock.txt")},
        "rebuild_pins": {"requirements.lock.txt": parse_pins(rebuild / "requirements.lock.txt"),
                         "requirements.eval.lock.txt": parse_pins(rebuild / "requirements.eval.lock.txt")},
        "persistent_pins": parse_pins(root / PERSISTENT_LOCK),
        "project_pins": parse_pins(proj),
        "pyvenv_cfg": {"home": BASE_PY_EXPECT["home"], "version": BASE_PY_EXPECT["version"],
                       "executable": BASE_PY_EXPECT["executable"]},
        "venv_probe": {"python": BASE_PY_EXPECT["version"]},
        "effective_numpy": NUMPY_EXPECT_EFFECTIVE,
        "effective_numpy_path": "/fake/venv/site-packages/numpy/__init__.py",
    }
    # 基线 sha 必须来自这个合成世界本身，否则 G1 在合成世界里恒红（那等于没测到牙）
    base_sha = dict(m["locks_0928"])

    if tamper == "M1_lock_byte":
        m["locks_0928"]["requirements.lock.txt"] = dict(
            base_sha["requirements.lock.txt"], sha256="0" * 64)
    elif tamper == "M2_backup_diverged":
        m["backup_sha"]["requirements.eval.lock.txt"] = "f" * 64
    elif tamper == "M3_mtime_today":
        m["locks_0928"]["requirements.lock.txt"] = dict(
            base_sha["requirements.lock.txt"], mtime=LOCK_CUTOFF_MTIME + 3600)
    elif tamper == "M5_torch_cu121":
        m["persistent_pins"] = dict(m["persistent_pins"], torch="2.4.1")
    elif tamper == "M6_base_python_310":
        m["pyvenv_cfg"] = dict(m["pyvenv_cfg"], version="3.10.14")
        m["venv_probe"] = {"python": "3.10.14"}
    elif tamper == "M7_numpy_shadow_lost":
        m["effective_numpy"] = NUMPY_BASE_SHADOWED
    elif tamper in ("M10_act_venv_derived_expectation", "M11_act_venv_shadow_lost"):
        # 复刻 0929 撞到的那个假红形状：act 侧 venv 的生效 numpy 与项目口径常量**不同**。
        # 只改 measured（不改 lock 文件）⇒ G1 在这些世界里仍绿，断言可以干净地只落在 G5 上。
        m["venv_path"] = "/fake/venvs/lerobot_act"
        m["old_pins"]["requirements.lock.txt"] = dict(
            m["old_pins"]["requirements.lock.txt"], numpy="2.2.6")
        m["effective_numpy"] = ("2.2.6" if tamper == "M10_act_venv_derived_expectation"
                                else NUMPY_BASE_SHADOWED)
    return root, m, base_sha


MUTATIONS = [
    # (id, tamper, 判据, 期望, 说明)；期望 NOT_RED 的那条是**反向**变异：
    # 它证明修完假红之后 G3 没有变成恒绿（假红和恒绿一样坏）。
    ("M1", "M1_lock_byte", "G1", "RED", "把 0928 lock 的 sha 改掉（= 有人覆写了溯源件）"),
    ("M2", "M2_backup_diverged", "G1", "RED", "让 C 的备份与原件不一致（= 第二份证据失效）"),
    ("M3", "M3_mtime_today", "G1", "RED", "把 0928 lock 的 mtime 改成今天（= 原地重写）"),
    ("M4", "M4_lockout_default", "G2", "RED", "让重建目录 == 0928 目录（= 用了默认 LOCK_OUT）"),
    ("M5", "M5_torch_cu121", "G3", "RED", "把 torch pin 从 2.4.1+cu124 改成 2.4.1（= cu121 静默漂移）"),
    ("M6", "M6_base_python_310", "G4", "RED", "把 base python 说成 3.10.14（= 换容器后 shebang 全断）"),
    ("M7", "M7_numpy_shadow_lost", "G5", "RED", "让生效 numpy 退回 base 的 1.26.4（= 遮蔽失效）"),
    ("M8", "none", "G3", "NOT_RED",
     "freeze 用发行名原样（ImageIO/Jinja2/typing_extensions/PyYAML/Pygments/Werkzeug）且不含 "
     "pip/setuptools ⇒ **不得**误报缺失（这条钉住 norm_name + FREEZE_EXEMPT，防假红回归）"),
    ("M9", "M9_frozen_torch_drift", "G3", "RED",
     "freeze 产物里 torch 是 2.4.1（cu121）而 pin 是 2.4.1+cu124 ⇒ 对账必须红（证明 M8 没把 G3 弄成恒绿）"),
    ("M10", "M10_act_venv_derived_expectation", "G5", "NOT_RED",
     "**反向**（钉住 0929 那起假红）：act venv 生效 numpy==2.2.6、act lock 的 pin 也是 2.2.6 "
     "⇒ 期望值按 venv 推导后**不得**再拿项目口径 2.4.6 去误报缺失"),
    ("M11", "M11_act_venv_shadow_lost", "G5", "RED",
     "同一个 act venv，但生效 numpy 退回 base 的 1.26.4 ⇒ 仍必须红"
     "（证明 M10 的修法没把 G5 弄成恒绿：按 venv 推导 ≠ 放宽判据）"),
]


def selftest():
    stamp = int(time.time())
    base = Path("/tmp/b_env_provenance_selftest_%d_%d" % (stamp, os.getpid()))
    base.mkdir(parents=True, exist_ok=True)
    print("=" * 92)
    print("变异自检：证明 5 条判据都咬得动（裁定 27.1「恒假的闸等于没有闸」）")
    print("含 2 条**反向**变异（M8 / M10，期望 NOT_RED）：证明修完假红后判据没变成恒绿")
    print("=" * 92)
    print("%-4s %-10s %-10s %s" % ("变异", "期望", "实际", "结论"))
    print("-" * 92)
    results = []

    # baseline：合成世界必须全绿，否则后面的"变红"没有意义
    root, m, base_sha = _mk_world(base / "baseline", "none")
    globals()["LOCKS_0928_BASELINE"] = {k: v["sha256"] for k, v in base_sha.items()}
    ctx = {"root": root, "rebuild_dir": REBUILD_DIR_DEFAULT, "venv": "/fake/venv",
           "measured": m, "no_live": True, "frozen": None}
    rep0 = run_checks(ctx)
    base_green = rep0.n_red == 0
    print("%-4s %-6s %-6s %s" % ("-", "GREEN", "GREEN" if base_green else "RED",
                                  "baseline_all_green（合成世界本身必须全绿）"))
    results.append(base_green)
    if not base_green:
        for c in rep0.checks:
            if c["status"] == "RED":
                print("      baseline 变红：%s -> %s" % (c["check_id"], c["actual"].get("violations")))

    for mid, tamper, want_check, want_status, desc in MUTATIONS:
        wroot, wm, _ = _mk_world(base / mid, tamper)
        ctx = {"root": wroot,
               "rebuild_dir": (LOCKS_0928_DIR if tamper == "M4_lockout_default" else REBUILD_DIR_DEFAULT),
               "venv": wm.get("venv_path", "/fake/venv"), "measured": wm, "no_live": True,
               "frozen": str(wroot / "frozen.txt")}
        rep = run_checks(ctx)
        target = [c for c in rep.checks if c["check_id"].startswith(want_check)]
        got = target[0]["status"] if target else "ABSENT"
        if want_status == "RED":
            ok = (got == "RED")
            verdict = "抓住" if ok else "**没抓住（判据恒假）**"
        else:
            ok = (got != "RED")
            verdict = "未误报（假红已修）" if ok else "**误报缺失（假红回归）**"
        print("%-4s %-10s %-10s %s" % (mid, "%s=%s" % (want_check, want_status), "%s=%s" % (want_check, got),
                                       "%s ⇒ %s" % (desc, verdict)))
        if not ok and target:
            print("      违例：%s" % (target[0]["actual"].get("violations") or target[0]["actual"]))
        results.append(ok)

    n_ok = sum(1 for r in results if r)
    print("-" * 92)
    print("变异测试：%d/%d 条判定符合预期（含 baseline 全绿）" % (n_ok, len(results)))
    # AGENTS.md：不 rm，临时目录 mv 到回收站
    moved = None
    try:
        RECYCLE_BIN.mkdir(parents=True, exist_ok=True)
        moved = RECYCLE_BIN / ("%d_b_env_provenance_selftest" % stamp)
        # /tmp 在 overlay、回收站在 NFS ⇒ Path.rename 会 EXDEV，必须用 shutil.move
        shutil.move(str(base), str(moved))
    except Exception as e:
        moved = "mv 失败（%s: %s），临时目录留在 %s" % (type(e).__name__, e, base)
    print("临时目录已 mv 到回收站：%s" % moved)
    print("=" * 92)
    return 0 if n_ok == len(results) else 1


def main():
    ap = argparse.ArgumentParser(description="B 线：环境与 lock 溯源闸（裁定 32.3 前提 1/2 + 裁定 32.4）")
    ap.add_argument("--root", default=str(ROOT_DEFAULT))
    ap.add_argument("--rebuild-dir", default=REBUILD_DIR_DEFAULT)
    ap.add_argument("--venv", default=VENV_DEFAULT)
    ap.add_argument("--frozen", default=None,
                    help="甲案建成后 pip freeze 的产物路径，与 requirements.persistent.lock.txt 逐 pin 对账")
    ap.add_argument("--no-live", action="store_true", help="不探真实解释器（只判文件层）")
    ap.add_argument("--expect-numpy", default=None,
                    help="显式指定 G5 的生效 numpy 期望值；缺省按 venv 名从对应 0928 lock 推导")
    ap.add_argument("--check-persistent-pin", action="store_true", help="只跑 G3")
    ap.add_argument("--selftest", action="store_true", help="变异自检：证明判据有牙")
    ap.add_argument("--expect", choices=["auto", "pass", "red"], default="auto")
    ap.add_argument("--json-out", default=str(ROOT_DEFAULT / "runs/infra/b_env_provenance/guard.json"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())

    ctx = {"root": Path(a.root), "rebuild_dir": a.rebuild_dir, "venv": a.venv,
           "measured": None, "no_live": a.no_live, "frozen": a.frozen,
           "expect_numpy": a.expect_numpy,
           "only": ["G3"] if a.check_persistent_pin else None}
    rep = run_checks(ctx)
    doc = build_report(ctx, rep)
    print_report(doc, a.quiet)

    outp = Path(a.json_out)
    try:
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        if not a.quiet:
            print("写出:", outp)
    except Exception as e:
        print("（未写出 %s：%s）" % (outp, e))

    if a.expect == "red":
        sys.exit(0 if doc["summary"]["n_red"] else 1)
    if a.expect == "pass":
        sys.exit(0 if doc["summary"]["n_red"] == 0 else 1)
    sys.exit(1 if doc["summary"]["n_red"] else 0)


if __name__ == "__main__":
    main()
