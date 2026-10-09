#!/usr/bin/env python3
"""A 线：**产物 → 环境**的溯源旁挂件（D 附记 §9.1 末的硬义务）。

D 的原话：「**你今后的新训练/新评测产物必须回显新 lock 的 sha256**，否则『这条结论跑在哪个环境上』又会不可答。」
这正是 0929 检修暴露的那个洞：48 臂权威表当初跑在什么环境上，唯一答案就是
`runs/infra/lerobot_act_env_20260928/requirements{,.eval}.lock.txt` 那两份 `pip freeze`。
产物自己不回显环境指纹 ⇒ 环境一换，「这条结论还能不能算复现」就变成考古题。

为什么用**旁挂 sidecar** 而不是往 `config.json` / ckpt 里加键
------------------------------------------------------------
加键会改动**既有产物的 schema**：`train_act_lift.py` 的缺省路径必须与改动前逐项相同
（0924 的 ckpt 要能 `strict=True` 加载、`config.json` 的键集不能变），这是 A 侧 T17 改动的硬前提
（证据见 `scripts/a_selfcheck_goal_conditioning_t17.py` 的 G5/G6）。
所以这里**只在输出目录里多写一个文件** `env_provenance.json`：既有文件一字节不动，
下游谁都不受影响，而溯源信息在产物目录里就地可查。

**非致命**：溯源写不出来（例如 lock 文件不在）**不得**让训练/评测失败 ——
但必须**大声**打印，因为「静默没有溯源」正是本模块要治的病。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 新环境（0929 重建）的 lock = 「这条结论跑在什么环境上」的答案；
# 0928 那两份是**旧事实**（48 臂权威表的溯源），并存、不覆盖（裁定 32.4）。
NEW_LOCKS = ROOT / "runs/infra/a_lerobot_env_rebuild_20260929"
OLD_LOCKS = ROOT / "runs/infra/lerobot_act_env_20260928"
LOCK_FILES = ("requirements.lock.txt", "requirements.eval.lock.txt")
SIDECAR_NAME = "env_provenance.json"
BREAKPOINT_ID = "BP-20260929-lerobot-env-rebuild"
# 裁定 34.1 的放行是**按包按链路**授的，引用必须点名包与版本，不得写成「lock 差异已裁定可忽略」
LOCK_DIFF_WAIVER = {
    "ruling": "裁定 34.1（2026-09-29 14:5x，supervisor_memo_20260929.md 增补十一 / DR-D33）",
    "scope": "只覆盖这 2 个包 / 这 2 份 lock / 官方 ACT 与 48 臂这条链路",
    "waived_packages": [{"package": "ImageIO", "old": "2.37.4", "new": "2.38.0", "in_locks": ["act", "eval"]},
                        {"package": "uv", "old": "0.12.19", "new": "0.12.17", "in_locks": ["act"]}],
    "citation_rule": "引用时**点名包与版本**；**不得**写成「lock 差异已裁定可忽略」这种无限定句",
    "re_report_rule": "下次重建若有**任何**新增差异（含这两个包再浮动）一律重新报 D",
    "void_if": "若将来发现 imageio/uv 确实在 48 臂链路的 import 面上 ⇒ 本裁定自动作废",
}

# 裁定 37.3（DR-D36 / memo 增补十四）：裁定 34.1 的豁免**边界收窄一句**。
# C 的运行时实测（每模块一个子进程 + 回显 sys.modules 前缀键，**覆盖传递依赖**）：
# 本仓 ACT / 48 臂链路的 8 个脚本全部 `hit=[]` ⇒ 豁免继续有效；
# 但上游 `lerobot.scripts.lerobot_train` 的 import 闭包里**确有 imageio**（18 个子模块）
# ⇒ **用上游入口实跑的训练/评测不在豁免内**，且**今后真跑必须回显 imageio 生效版本**。
IMAGEIO_WAIVER_BOUNDARY = {
    "ruling": "裁定 37.3（2026-09-29 15:3x，supervisor_memo_20260929.md 增补十四 / DR-D36）",
    "waiver_covers": "本仓 ACT / 48 臂链路的 8 个脚本（C 运行时实测 hit=[]，覆盖传递依赖）",
    "waiver_does_not_cover": ("上游 lerobot.scripts.lerobot_train 的 import 闭包"
                              "（C 实测含 imageio，18 个子模块）⇒ 用它实跑不在豁免内"),
    "obligation": ("用上游入口实跑时本旁挂件必须回显 imageio 生效版本；引用结论时**必须带这条边界**，"
                   "否则另证 imageio 不材料 / 重新报 D"),
    "runtime_evidence_rule": ("「某包不在某链路的 import 面上」这类主张今后必须给**运行时**证据"
                              "（静态 grep 扫不到传递依赖）；现成工具 "
                              "`scripts/c_env_manifest.py --measure-import-surface`（只读调用，产物写自己的目录）"),
    "a_smoke_not_retroactive": "A 的环境 smoke S2 用过上游 lerobot_train，但 smoke **不是能力主张** ⇒ 不需追溯（裁定 37.3）",
}


def _waived_pkg(name: str) -> dict:
    """从 `LOCK_DIFF_WAIVER` 取某个包的旧/新值 —— **不另写一份常数**（裁定 36.4：并列两个陈述前先确认同源）。"""
    for pkg in LOCK_DIFF_WAIVER.get("waived_packages") or []:
        if str(pkg.get("package", "")).lower() == name.lower():
            return pkg
    return {}


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def lock_fingerprint() -> dict:
    """两份新 lock 的 sha256（+ 0928 旧 lock 的 sha256 作对照，证明「新旧并存、没覆盖」）。"""
    new, old = {}, {}
    for name in LOCK_FILES:
        new[name] = {"sha256": sha256(NEW_LOCKS / name), "path": str(NEW_LOCKS / name)}
        old[name] = {"sha256": sha256(OLD_LOCKS / name), "path": str(OLD_LOCKS / name)}
    return {"new_env_20260929": new, "original_0928_untouched": old,
            "new_locks_present": all(v["sha256"] for v in new.values()),
            "old_locks_present": all(v["sha256"] for v in old.values())}


def interpreter_facts() -> dict:
    """当前解释器的**语义值**（不是 importable）+ venv 的 realpath（经软链时要能追到 NFS 真实路径）。"""
    exe = Path(sys.executable)
    facts = {"executable": str(exe), "venv_as_invoked": None, "venv_realpath": None,
             "python_binary_realpath": None, "python": "%d.%d.%d" % sys.version_info[:3],
             "packages": {}}
    try:
        # **不能**用 `exe.resolve().parents[1]`：venv 的 `bin/python` 本身是指向 base 解释器的软链
        # （→ /opt/conda/bin/python3.11），resolve 会一路解到 base，parents[1] 就变成 `/opt/conda`
        # —— 那正是首版的 bug（实测写出 `venv_realpath=/opt/conda`，把 A 的 venv 说成了 conda）。
        # 正确做法：先按**未解析**路径取 venv 根（上两级），再对**目录**做 realpath。
        facts["venv_as_invoked"] = str(exe.parents[1])
        facts["venv_realpath"] = os.path.realpath(str(exe.parents[1]))
        facts["python_binary_realpath"] = os.path.realpath(str(exe))   # = base 解释器，与 pyvenv.cfg 的 executable 同源
    except Exception:  # noqa: BLE001
        pass
    # imageio 在列是**裁定 37.3 的硬要求**（真跑须回显其生效版本），不是顺手加的
    for mod, dist in (("torch", "torch"), ("lerobot", "lerobot"),
                      ("robosuite", "robosuite"), ("mujoco", "mujoco"), ("numpy", "numpy"),
                      ("imageio", "ImageIO")):
        try:
            m = __import__(mod)
            facts["packages"][mod] = getattr(m, "__version__", None)
        except Exception:  # noqa: BLE001
            facts["packages"][mod] = None
        del dist
    try:
        import torch
        facts["cuda_available"] = bool(torch.cuda.is_available())
        facts["cuda_device"] = torch.cuda.get_device_name(0) if facts["cuda_available"] else None
    except Exception:  # noqa: BLE001
        facts["cuda_available"] = None
    return facts


def gate_status() -> dict:
    """就绪闸现值：`BLOCKED` 时产物仍可写，但**不得**被引用为复现主张（裁定 29.4 / 34.1）。"""
    try:
        r = subprocess.run([sys.executable, str(ROOT / "scripts/a_env_readiness_gate.py")],
                           capture_output=True, text=True, timeout=900)
        out = {"rc": r.returncode, "verdict": None, "failed": []}
        for line in (r.stdout or "").splitlines():
            if line.startswith("A_NEW_REPRO_CLAIMS="):
                out["verdict"] = line.split()[0].split("=", 1)[1]
            elif line.startswith("[FAIL]"):
                parts = line.split()
                out["failed"].append(parts[1] if len(parts) > 1 else line)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"rc": None, "verdict": None, "failed": [], "error": repr(exc)}


def build(kind: str, artifact: str | None = None, extra: dict | None = None) -> dict:
    doc = {
        "sidecar_kind": "a_env_provenance",
        "run_kind": kind,
        "artifact": artifact,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "container_id": os.environ.get("HOSTNAME"),
        "breakpoint": {"id": BREAKPOINT_ID,
                       "occurred_at": "2026-09-29T10:45:56+08:00",
                       "rule": "本产物若 mtime 早于断点而被称为「可复现」，必须在重建后的环境上重跑"},
        "lock": lock_fingerprint(),
        "lock_diff_waiver": LOCK_DIFF_WAIVER,
        "interpreter": interpreter_facts(),
        "readiness_gate": gate_status(),
        "claim_discipline": {
            "allowed_if_gate_blocked": ["环境可用性结论", "只读后处理结论", "官方 ACT 链路上的复现（裁定 34.1）"],
            "forbidden_if_gate_blocked": ["任何**新训练 / 新评测**的复现主张",
                                          "48 臂权威表的跨断点复用", "§8 晋级条件① 的推进"],
        },
        "extra": extra or {},
    }
    img_w = _waived_pkg("ImageIO")
    img_eff = (doc["interpreter"].get("packages") or {}).get("imageio")
    doc["imageio"] = {
        "effective_version": img_eff,
        "old_lock_0928": img_w.get("old"),
        "new_lock_0929": img_w.get("new"),
        "matches_new_lock": (img_eff == img_w.get("new")) if img_eff else None,
        "note": ("生效版本 == 新 lock 的值 ⇒ 裁定 34.1 的放行按**实际跑的版本**成立；"
                 "不等于 ⇒ 这条产物跑在**未申报的环境**上，引用前必须报 D。"
                 "null = 该解释器里 imageio 不可导入（如实回显，不猜）。"),
        "waiver_boundary": IMAGEIO_WAIVER_BOUNDARY,
    }
    return doc


def write_sidecar(out_dir, kind: str, artifact: str | None = None, extra: dict | None = None) -> Path | None:
    """在 `out_dir` 里写 `env_provenance.json`。**非致命**：失败只打印，不抛。"""
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        payload = build(kind, artifact, extra)
        p = d / SIDECAR_NAME
        p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
        lk = payload["lock"]
        if not lk["new_locks_present"]:
            print("[env_provenance][WARN] 新 lock 缺失 ⇒ 本产物的环境指纹不完整：%s" % lk["new_env_20260929"],
                  file=sys.stderr)
        gate = payload["readiness_gate"].get("verdict")
        print("[env_provenance] 写出 %s（gate=%s，new_lock_sha12=%s）"
              % (p, gate, (lk["new_env_20260929"]["requirements.lock.txt"]["sha256"] or "")[:12]))
        return p
    except Exception as exc:  # noqa: BLE001
        print("[env_provenance][WARN] 溯源旁挂件写失败（**不致命**，但这意味着本产物缺环境指纹）：%r" % (exc,),
              file=sys.stderr)
        return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--kind", default="manual")
    ap.add_argument("--artifact", default=None)
    a = ap.parse_args()
    got = write_sidecar(a.out_dir, a.kind, a.artifact)
    sys.exit(0 if got else 1)
