#!/usr/bin/env python3
"""生成**自足**的持久 venv lock（监管备忘 裁定 32.3 第 1 条的 (甲) 方案）。

为什么需要它
------------
`requirements.lock.txt` 是 `pip freeze --local` 的产物，而 `rlrobot` venv 是用
`--system-site-packages` 建的 ⇒ 那 28 个 pin **不含**从 `/opt/conda` 继承的包
（torch / torchvision / scipy / pandas / pillow / h5py / opencv …）。
把这份 lock 装进一个**干净** venv，缺的恰恰是跑训练真正要用的那几个。

本脚本从「28 pin + 显式种子」出发，沿**已安装发行版的 metadata**做依赖闭包 BFS，
把闭包里每个包的**当前已装版本**钉死，产出一份能用 `--no-deps` 直接装进干净 venv 的
`requirements.persistent.lock.txt`（外加 `--json-out` 的溯源报告）。

口径（沿用 C 的 ADR-C-006 / D 裁定 32.2）
----------------------------------------
* **只跟依赖名字、不跟版本约束**：`robosuite 1.5.2` 声明 `mink==0.0.5`，而实际装成并跑通
  全量回归的是 `mink 1.2.0` ⇒ 闭包按**已装版本**钉，把不满足的约束记进 `known_conflicts`
  （解析器到不了某个组合 ≠ 那个组合不可用），**不**放宽 pin、**不**改判。
* **不碰仓里的 `requirements.lock.txt`**：那是门禁产物（28 pin），B 的
  `b_selfcheck_reproducibility.py`（L0-f/L0-g）与 C 的 `c_env_manifest.py::_parse_lock` 都读它。
  本脚本只**读**它，产物写另一个文件名。
* 缺包（metadata 里没有）记进 `gaps`，**必须显式处理**，不静默跳过。

用法（**必须用能同时看到 venv 与 base 的解释器**，即带 `--system-site-packages` 的那份 rlrobot）：
    /root/venvs/rlrobot/bin/python scripts/d_build_persistent_lock.py \
        --json-out runs/infra/d_persistent_env_20260929/persistent_lock_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from importlib import metadata as md
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_LOCK = ROOT / "requirements.lock.txt"
DEFAULT_OUT = ROOT / "requirements.persistent.lock.txt"

# 不在 28 pin 里、但跑训练/画图真正要用到的继承包（requirements-inherited.json 逐条对齐，
# 减去 jax/jaxlib：仓里执行的代码没有一处 import jax，只有 RL_Harness_v4 的**只读调研快照**
# 里有；而 conda 的 jax/tensorflow 正是 09-24 那串 ImportError 的污染源）。
SEEDS = ("torch", "torchvision", "scipy", "pandas", "pyarrow", "matplotlib", "pyyaml",
         "imageio", "pillow", "psutil", "rich", "pip", "setuptools")
# 等价性补钉：`robosuite/utils/camera_utils.py:12` **模块级** `import h5py`，而 h5py 不在
# robosuite 的 install_requires 里（只由 `robosuite/scripts/*` 与 demo_sampler_wrapper 用）。
# 今天它能用，是因为 base 里有 h5py 3.14.0；干净 venv 会缺 ⇒ 显式钉上，保持与已验证环境等价。
PARITY_SEEDS = ("h5py",)
EXCLUDES = ("jax", "jaxlib")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def parse_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry or entry.startswith("-"):
            continue
        if "==" in entry:
            name, version = entry.split("==", 1)
            pins[name.strip()] = version.split(";", 1)[0].strip()
        else:
            pins[entry.split(";", 1)[0].strip()] = ""
    return pins


def installed(name: str) -> str | None:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def requires(name: str) -> list[str]:
    try:
        return list(md.distribution(name).requires or [])
    except md.PackageNotFoundError:
        return []


def build_closure(seeds: list[str], excludes: set[str]) -> dict:
    """BFS：只跟名字，版本一律取**当前已装版本**。"""
    from packaging.markers import Marker
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    pinned: dict[str, str] = {}
    why: dict[str, list[str]] = {}
    conflicts: list[str] = []
    gaps: list[str] = []
    excluded_hits: dict[str, list[str]] = {}
    queue = list(dict.fromkeys(seeds))
    seen: set[str] = set()

    while queue:
        name = queue.pop(0)
        key = norm(name)
        if key in seen:
            continue
        seen.add(key)
        if key in excludes:
            continue
        version = installed(name)
        if version is None:
            gaps.append("%s（被 %s 需要，但当前解释器里没有它的 metadata）"
                        % (name, ",".join(why.get(key, ["seed"])) or "seed"))
            continue
        pinned[name] = version
        for raw in requires(name):
            try:
                req = Requirement(raw)
            except Exception:                                  # 解析不了的约束只记不看
                conflicts.append("%s -> 无法解析的约束 %r" % (name, raw))
                continue
            if req.marker is not None and not Marker(str(req.marker)).evaluate({"extra": ""}):
                continue                                       # extra / 平台不符 ⇒ 不跟
            child_key = norm(req.name)
            why.setdefault(child_key, []).append(name)
            if child_key in excludes:
                excluded_hits.setdefault(req.name, []).append(name)
                continue
            child_version = installed(req.name)
            if child_version is None:
                gaps.append("%s（被 %s 需要，但当前解释器里没有它的 metadata）" % (req.name, name))
                continue
            if req.specifier and not SpecifierSet(str(req.specifier)).contains(
                    Version(child_version), prereleases=True):
                conflicts.append("%s %s -> %s%s（实际装成 %s，按已装版本钉）"
                                 % (name, version, req.name, req.specifier, child_version))
            queue.append(req.name)
    return {"pinned": pinned, "why": why, "conflicts": sorted(set(conflicts)),
            "gaps": sorted(set(gaps)), "excluded_hits": excluded_hits}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--base-lock", default=str(BASE_LOCK))
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--seed", action="append", default=None,
                        help="追加种子包（可重复）；默认 = %s" % ",".join(SEEDS))
    parser.add_argument("--exclude", action="append", default=None,
                        help="排除包（可重复，含其依赖子树）；默认 = %s" % ",".join(EXCLUDES))
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args(argv)

    base_lock = Path(args.base_lock).resolve()
    if not base_lock.is_file():
        print("找不到 base lock：%s" % base_lock)
        return 2
    project_pins = parse_pins(base_lock)
    seeds = list(project_pins) + list(SEEDS) + list(PARITY_SEEDS) + list(args.seed or [])
    excludes = {norm(name) for name in (list(EXCLUDES) + list(args.exclude or []))}

    closure = build_closure(seeds, excludes)
    pinned = closure["pinned"]

    # 已装版本必须与 base lock 的 pin 一致（不一致就是环境漂移，不能生成）
    drift = [(name, want, pinned[name]) for name, want in project_pins.items()
             if name in pinned and pinned[name] != want]
    missing_from_closure = [name for name in project_pins if name not in pinned]
    if drift or missing_from_closure:
        print("拒绝生成：base lock 的 pin 与当前已装版本不一致")
        for name, want, got in drift:
            print("  DRIFT   %s lock=%s installed=%s" % (name, want, got))
        for name in missing_from_closure:
            print("  MISSING %s（lock 里有、当前解释器里没装）" % name)
        return 3
    if closure["gaps"]:
        print("拒绝生成：闭包里有缺口（缺的包必须显式处理，不能静默跳过）")
        for gap in closure["gaps"]:
            print("  GAP %s" % gap)
        return 4

    extra = {name: version for name, version in pinned.items() if name not in project_pins}
    lines = [
        "# generated_by=scripts/d_build_persistent_lock.py",
        "# generated_at=%s" % time.strftime("%FT%T%z"),
        "# generated_with=%s (%s)" % (sys.executable, sys.version.split()[0]),
        "# purpose=自足持久 venv 的 lock（监管备忘 裁定 32.3 第 1 条 (甲)）：base lock 的 %d pin + 依赖闭包 %d 包"
        % (len(project_pins), len(extra)),
        "# base_lock=%s sha256_12=%s" % (base_lock.name,
                                         hashlib.sha256(base_lock.read_bytes()).hexdigest()[:12]),
        "# install=codex-persist mkvenv rlrobot %s --clean --find-links https://mirrors.aliyun.com/pytorch-wheels/cu124/"
        % Path(args.out).name,
        "# verify=codex-persist venvcheck rlrobot --pin-file %s --import torch:torch --import mujoco ..."
        % Path(args.out).name,
        "# python=%s" % ".".join(map(str, sys.version_info[:3])),
        "# excluded=%s（仓里执行的代码不 import；conda 的 jax/tf 是 09-24 ImportError 的污染源）"
        % ",".join(sorted(excludes)),
        "# known_conflicts=%s" % ("; ".join(closure["conflicts"]) or "无"),
        "# note=本文件**不是**门禁产物；门禁读的是 requirements.lock.txt（28 pin，勿改）。",
        "",
        "# --- 项目 pin（与 %s 逐行一致） ---" % base_lock.name,
    ]
    lines += ["%s==%s" % (name, project_pins[name]) for name in sorted(project_pins, key=str.lower)]
    lines += ["", "# --- 依赖闭包新增（干净 venv 自足所需；原先靠 --system-site-packages 从 base 继承） ---"]
    lines += ["%s==%s" % (name, extra[name]) for name in sorted(extra, key=str.lower)]
    text = "\n".join(lines) + "\n"

    if args.dry_run:
        print(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
        print("已写 %s（%d pin = 项目 %d + 闭包 %d）"
              % (args.out, len(pinned), len(project_pins), len(extra)))

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps({
            "kind": "d_persistent_lock_report",
            "generated_at": time.strftime("%FT%T%z"),
            "generated_with": {"executable": sys.executable, "version": sys.version.split()[0],
                               "prefix": sys.prefix, "base_prefix": sys.base_prefix},
            "out": str(Path(args.out).resolve()),
            "base_lock": {"path": str(base_lock), "n_pins": len(project_pins),
                          "sha256_12": hashlib.sha256(base_lock.read_bytes()).hexdigest()[:12]},
            "seeds": seeds,
            "excludes": sorted(excludes),
            "excluded_hits": closure["excluded_hits"],
            "n_pins_total": len(pinned),
            "n_pins_closure_only": len(extra),
            "pins": {name: pinned[name] for name in sorted(pinned, key=str.lower)},
            "required_by": closure["why"],
            "known_conflicts": closure["conflicts"],
            "gaps": closure["gaps"],
            "doctrine": ("只跟依赖名字、版本取已装值；解析器到不了某个组合 ≠ 该组合不可用"
                         "（C 的 ADR-C-006 / D 裁定 32.2）"),
        }, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
        print("已写报告 %s" % args.json_out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
