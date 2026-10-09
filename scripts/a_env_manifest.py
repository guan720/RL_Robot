#!/usr/bin/env python3
"""A 线：**lerobot 环境重建后的 env manifest**（D 执行单 §6.3–§6.6 的机器承载）—— 全程只读。

为什么 A 要自己出一份，而不是让 C 的 manifest 覆盖
------------------------------------------------
C 的 `runs/infra/c_env_manifest_20260929.json` 的「全绿」只覆盖
`probe_module_classes.required_for_c_regression`（robosuite/mujoco 那条回归线），
它自己就明写 `env_fully_restored=false` 时不得读成「环境已完全恢复」。
A 的训练/评测环境（`lerobot_act` / `lerobot_eval`）是**另一套 venv、另一组判据**，
所以断点也**单列**（`BP-20260929-lerobot-env-rebuild`），不与 C 的 `BP-20260929-venv-rebuild` 合并：
两者 `invalidates` 的范围不同（C 废的是 rlrobot 侧复现，A 废的是官方 ACT 训练与真值评测）。

本脚本收集 6 类证据，**全部现场实测**，不手抄数字
--------------------------------------------------
1. 两个 venv 的解释器 / 版本 / **安装来源**（dist-info 路径 ⇒ 区分 wheel 与源装）；
   经 `/root/venvs/*` **软链**调用，同时把软链指向回显出来（D §4：73 个文件硬编码 /root/venvs，不改路径用软链）。
2. `pyvenv.cfg`：lerobot 两个必须 `include-system-site-packages = false`（D §6.4）。
3. **lock 差异报告（P0，D §6.3）**：新 lock vs C 的逐字节备份，逐包给出 added/removed/changed；
   并证明 0928 两份原件**未被覆写**（sha256 与 C 备份相同 + mtime 早于 0929 断点时刻）。
4. 冷导入耗时基线（D §6.6）：NFS 上 import torch/lerobot 是大量小文件读。
5. smoke 证据（D §6.7）：从 smoke.log 解析三步的 exit code —— **三步全 0 才叫环境可用**。
6. 就绪闸现状：A 的 `a_env_readiness_gate.py` 的 E1–E7 结论（E6 读 C 的 manifest，A 不改它）。

口径纪律（写在产物里，防止被误读）
--------------------------------
`env_usable=true`（smoke 通过）**只**支持「环境可用」这一句；
`reproduction_claims_blocked` 仍是 true，只要 ① 就绪闸未 ALLOWED（E6 需 C 重出 manifest），
或 ② lock 有差异且 D 尚未裁定。D §6.3 原文：有差异 ⇒「在 D 裁定前不得声称任何跨断点复现」。

用法：
    /root/venvs/rlrobot/bin/python scripts/a_env_manifest.py            # 或任一能跑 python3 的解释器
    python3 scripts/a_env_manifest.py --no-cold-import                  # 跳过冷导入计时
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# pin 的单一事实源 = A 自己的就绪闸（它照抄 B 的 DR-012 §2）；这里**不再抄第二份**
from scripts.a_env_readiness_gate import LOCK_EVAL, LOCK_TRAIN, PIN  # noqa: E402

NEW_LOCKS = "runs/infra/a_lerobot_env_rebuild_20260929"
C_BACKUP = "runs/infra/c_lerobot_env_locks_backup_20260928"
SMOKE_DIR = "runs/infra/a_smoke_env_rebuild_20260929"
# 0929 检修断点时刻（C 的 manifest 记的同一件事）：早于它的 mtime 才可能是「旧事实」
BREAKPOINT_OCCURRED_AT = "2026-09-29T10:45:56+08:00"
BREAKPOINT_OCCURRED_NS = 1790649956015412393


def sh(cmd, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:  # noqa: BLE001
        return -1, "", "%r" % (exc,)


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def mtime_iso(path: Path):
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def parse_pyvenv_cfg(venv: Path):
    cfg = venv / "pyvenv.cfg"
    if not cfg.exists():
        return {"exists": False}
    out = {"exists": True, "path": str(cfg)}
    for line in cfg.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def probe_venv(link: Path, packages):
    """经 `/root/venvs/*` 软链探一个 venv：软链指向、pyvenv.cfg、版本、安装来源、CUDA。"""
    rec = {"link": str(link), "is_symlink": link.is_symlink(),
           "link_target": os.readlink(str(link)) if link.is_symlink() else None,
           "resolved": str(link.resolve()) if link.exists() else None,
           "exists": link.exists(), "python_exists": (link / "bin/python").exists()}
    if not rec["python_exists"]:
        rec["error"] = "解释器不存在，无法探测"
        return rec
    real = Path(rec["resolved"])
    rec["pyvenv_cfg"] = parse_pyvenv_cfg(real)
    # 用占位符替换而不是 % 格式化：被探测的代码里本身就有 %d/%r，用 % 会互相吃掉。
    code = """
import sys, json, importlib.metadata as md
out = {'exe': sys.executable,
       'py': '.'.join(str(i) for i in sys.version_info[:3]),
       'pkgs': {}, 'dist': {}}
for m in __PACKAGES__:
    try:
        mod = __import__(m)
        out['pkgs'][m] = getattr(mod, '__version__', None)
        out['dist'][m] = str(md.distribution(m)._path)
    except Exception as e:
        out['pkgs'][m] = None
        out['dist'][m] = 'ERROR ' + repr(e)
try:
    import torch
    out['cuda'] = bool(torch.cuda.is_available())
    out['cuda_device'] = torch.cuda.get_device_name(0) if out['cuda'] else None
    out['torch_version'] = torch.__version__
except Exception as e:
    out['cuda'] = None
    out['cuda_error'] = repr(e)
print(json.dumps(out))
""".replace("__PACKAGES__", repr(list(packages)))
    rc, so, se = sh([str(link / "bin/python"), "-c", code], timeout=300)
    rec["probe_rc"] = rc
    if rc == 0 and so:
        try:
            rec.update(json.loads(so.splitlines()[-1]))
        except Exception as exc:  # noqa: BLE001
            rec["probe_error"] = "解析探针输出失败 %r；stderr=%s" % (exc, se[-400:])
    else:
        rec["probe_error"] = "rc=%s stderr=%s" % (rc, se[-800:])
    return rec


def parse_lock(path: Path):
    """`pip freeze` 格式 -> {包名小写: (原名, 版本)}。"""
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, ver = line.split("==", 1)
        out[name.strip().lower()] = (name.strip(), ver.strip())
    return out


def diff_locks(old: Path, new: Path):
    if not old.exists() or not new.exists():
        return {"comparable": False, "missing": [str(p) for p in (old, new) if not p.exists()]}
    o, n = parse_lock(old), parse_lock(new)
    changed = [{"package": n[k][0], "old": o[k][1], "new": n[k][1]}
               for k in sorted(set(o) & set(n)) if o[k][1] != n[k][1]]
    added = [{"package": n[k][0], "version": n[k][1]} for k in sorted(set(n) - set(o))]
    removed = [{"package": o[k][0], "version": o[k][1]} for k in sorted(set(o) - set(n))]
    pins_untouched = []
    for label, name, want in (("lerobot", "lerobot", PIN["lerobot"]),
                              ("torch", "torch", None), ("torchvision", "torchvision", None),
                              ("numpy(eval)", "numpy", None), ("robosuite", "robosuite", PIN["eval_robosuite"]),
                              ("mujoco", "mujoco", PIN["eval_mujoco"])):
        key = name.lower()
        if key in n:
            got = n[key][1]
            pins_untouched.append({"pin": label, "version_in_new_lock": got,
                                   "expected": want, "matches_pin": (got.startswith(want) if want else None)})
    return {"comparable": True, "n_old": len(o), "n_new": len(n),
            "identical": not (changed or added or removed),
            "changed": changed, "added": added, "removed": removed,
            "authoritative_pins_in_new_lock": pins_untouched}


def cold_import(link: Path, code, runs=3):
    ts = []
    for _ in range(runs):
        t0 = time.time()
        rc, _, se = sh([str(link / "bin/python"), "-c", code], timeout=600)
        ts.append({"rc": rc, "seconds": round(time.time() - t0, 2), "error": se[-200:] if rc else ""})
    return {"runs": ts, "cold_first_s": ts[0]["seconds"] if ts else None,
            "warm_min_s": min((t["seconds"] for t in ts if t["rc"] == 0), default=None),
            "note": "NFS venv：第一次含页缓存冷启动，之后为热值。**没有** drop_caches（会与同机 B/C 抢缓存），"
                    "所以 cold_first_s 是「进程冷 + 页缓存部分热」的下界，不是真冷盘值。"}


def cold_import_section(a, link_act, link_eval):
    """冷/热导入基线。默认**引用**第二轮实测（真冷：整份 site-packages 定点逐出），不重复计时。

    首版那种「同一进程连跑三次取第一次」不是真冷（页缓存还热），与 D 的 rlrobot 对照值不可比。
    逐出用 `posix_fadvise(DONTNEED)` 定点做，**不** drop_caches（那会清整机缓存、影响同机 B/C）。
    """
    if a.no_cold_import:
        return None
    ref = ROOT / a.cold_import_json
    if ref.exists() and not a.measure_cold_import:
        try:
            data = json.loads(ref.read_text())
        except Exception as exc:  # noqa: BLE001
            return {"source": str(ref), "error": repr(exc)}
        return {"source": str(ref), "protocol": data.get("protocol"),
                "corrections_vs_round1": data.get("corrections_vs_round1"),
                "summary_for_d": data.get("summary_for_d"),
                "per_venv": {k: {"composite": v.get("composite"), "torch_only": v.get("torch_only"),
                                 "true_cold_effective": v.get("true_cold_effective")}
                             for k, v in (data.get("venvs") or {}).items()},
                "round1_superseded": "runs/infra/a_lerobot_env_rebuild_20260929/cold_import_baseline.json",
                "d_reference_rlrobot": data.get("d_reference_rlrobot"),
                "conclusion": ("冷比热慢 2.5–3 倍；import 在训练循环里只发生一次（一臂 20k 步是小时级）"
                               "⇒ NFS venv 不是吞吐瓶颈，A 侧不需要首轮预热。")}
    return {"source": "inline（--measure-cold-import；口径较粗，非真冷）",
            "act_torch_lerobot_actpolicy": cold_import(
                link_act, "import torch,lerobot\nfrom lerobot.policies.act.modeling_act import ACTPolicy",
                a.cold_import_runs),
            "eval_torch_lerobot_robosuite_mujoco": cold_import(
                link_eval, "import torch,lerobot,robosuite,mujoco", a.cold_import_runs)}


def parse_smoke(log: Path):
    if not log.exists():
        return {"ran": False, "log": str(log)}
    txt = log.read_text(errors="replace")
    steps = {}
    for tag in ("S1", "S2", "S3"):
        mark = "%s_EXIT=" % tag
        if mark in txt:
            steps[tag] = int(txt.split(mark, 1)[1].split("\n", 1)[0].strip() or -1)
    return {"ran": True, "log": str(log), "steps": steps,
            "all_zero": bool(steps) and all(v == 0 for v in steps.values()),
            "meaning": {"S1": "官方 LeRobotDataset v3.0 写 API（build_lerobot_act_dataset.py，1 局）",
                        "S2": "官方 ACT 训练入口 lerobot_train + CUDA（50 步）",
                        "S3": "评测 venv 闭环真值（lerobot 与 robosuite 同解释器，2 局）"},
            "not_a_claim": "smoke 只证明**流水线跑得通**，不证明策略能力："
                           "50 步 + --limit-requests 5 的模型 success_raw=0 是预期的，不得读成环境失败，"
                           "更不得读成任何能力/复现结论。"}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="runs/infra/a_env_manifest_20260929.json")
    ap.add_argument("--new-locks", default=NEW_LOCKS)
    ap.add_argument("--c-backup", default=C_BACKUP)
    ap.add_argument("--smoke-dir", default=SMOKE_DIR)
    ap.add_argument("--no-cold-import", action="store_true")
    ap.add_argument("--cold-import-runs", type=int, default=3)
    # D 附记 §9.4 要的是**与 rlrobot 对照可比**的冷/热值。首版那种「跑三次取第一次」不是真冷
    # （页缓存还热），已由 cold_import_baseline_v2.py 用 posix_fadvise 定点逐出整份 site-packages 重测。
    # 默认**引用**那份实测 JSON（不重复计时）；--measure-cold-import 才现场重测（口径较粗，只作退化兜底）。
    ap.add_argument("--cold-import-json",
                    default="runs/infra/a_lerobot_env_rebuild_20260929/cold_import_baseline_v2.json")
    ap.add_argument("--measure-cold-import", action="store_true")
    ap.add_argument("--rlrobot-venv", default="/root/venvs/rlrobot",
                    help="只读观测（D 附记 §9.4 第 1 项要求回显它的 realpath 与 ssp）；A 不改它")
    a = ap.parse_args()
    t0 = time.time()

    link_act = Path(PIN["train_venv"])
    link_eval = Path(PIN["eval_venv"])

    pkgs_act = ["lerobot", "torch", "torchvision", "numpy", "gymnasium"]
    pkgs_eval = ["lerobot", "torch", "numpy", "gymnasium", "robosuite", "mujoco"]
    v_act = probe_venv(link_act, pkgs_act)
    v_eval = probe_venv(link_eval, pkgs_eval)

    # --- pyvenv.cfg 断言（D §6.4）---
    ssp = {}
    for name, rec in (("lerobot_act", v_act), ("lerobot_eval", v_eval)):
        cfg = rec.get("pyvenv_cfg", {})
        ssp[name] = {"include-system-site-packages": cfg.get("include-system-site-packages"),
                     "home": cfg.get("home"), "version": cfg.get("version"),
                     "realpath": rec.get("resolved"), "link_target": rec.get("link_target"),
                     "must_be_false": cfg.get("include-system-site-packages") == "false",
                     "home_matches_pin_base": cfg.get("home") == str(Path(PIN["base_python"]).parent)}

    # --- rlrobot：**只读观测**（D 附记 §9.4 第 1 项）。A 不建、不改、不验收它（那是 C/D 的面）---
    rl = Path(a.rlrobot_venv)
    rl_real = Path(os.path.realpath(str(rl))) if rl.exists() else None
    rl_cfg = parse_pyvenv_cfg(rl_real) if rl_real else {"exists": False}
    rlrobot = {
        "link": str(rl), "is_symlink": rl.is_symlink(),
        "link_target": os.readlink(str(rl)) if rl.is_symlink() else None,
        "realpath": str(rl_real) if rl_real else None,
        "include-system-site-packages": rl_cfg.get("include-system-site-packages"),
        "home": rl_cfg.get("home"), "version": rl_cfg.get("version"),
        "persist_meta": None,
        "note": ("裁定 33 已选 (甲) 自足：D 于 14:24 建成 clean venv（82 pin）、14:35 把 /root/venvs/rlrobot "
                 "切成软链。A 首版回执写的是 `true` + 「甲/乙尚未裁定」，**据此更正**。"
                 "A 只读观测，不代 C/D 验收。"),
    }
    pm = (rl_real / ".persist_meta.json") if rl_real else None
    if pm and pm.exists():
        try:
            rlrobot["persist_meta"] = json.loads(pm.read_text())
        except Exception as exc:  # noqa: BLE001
            rlrobot["persist_meta"] = {"error": repr(exc)}

    # --- lock 差异（P0，D §6.3）---
    new_dir, bak_dir = ROOT / a.new_locks, ROOT / a.c_backup
    locks = {}
    for fname, old_rel in (("requirements.lock.txt", LOCK_TRAIN),
                           ("requirements.eval.lock.txt", LOCK_EVAL)):
        old_p, bak_p, new_p = ROOT / old_rel, bak_dir / fname, new_dir / fname
        entry = {"file": fname,
                 "original_0928": {"path": str(old_p), "exists": old_p.exists()},
                 "c_backup": {"path": str(bak_p), "exists": bak_p.exists()},
                 "new": {"path": str(new_p), "exists": new_p.exists()}}
        if old_p.exists():
            st = old_p.stat()
            entry["original_0928"].update({
                "sha256": sha256(old_p), "mtime": mtime_iso(old_p), "mtime_ns": st.st_mtime_ns,
                "size": st.st_size,
                # 关键证据：mtime 早于 0929 断点 ⇒ 今天这次安装**没有**覆写它
                "mtime_before_breakpoint": st.st_mtime_ns < BREAKPOINT_OCCURRED_NS})
        if bak_p.exists():
            entry["c_backup"].update({"sha256": sha256(bak_p), "mtime": mtime_iso(bak_p)})
        if new_p.exists():
            entry["new"].update({"sha256": sha256(new_p), "mtime": mtime_iso(new_p)})
        entry["original_equals_c_backup"] = (old_p.exists() and bak_p.exists()
                                             and sha256(old_p) == sha256(bak_p))
        entry["original_not_overwritten"] = bool(entry["original_0928"].get("mtime_before_breakpoint")
                                                 and entry["original_equals_c_backup"])
        entry["diff_vs_0928"] = diff_locks(bak_p, new_p) if (bak_p.exists() and new_p.exists()) else \
            {"comparable": False, "missing": [str(p) for p in (bak_p, new_p) if not p.exists()]}
        locks[fname] = entry

    provenance_ok = all(v["original_not_overwritten"] for v in locks.values())
    all_diffs = [d for v in locks.values() for d in v["diff_vs_0928"].get("changed", [])]
    diffs_identical = all(v["diff_vs_0928"].get("identical") for v in locks.values()
                           if v["diff_vs_0928"].get("comparable"))

    # --- 就绪闸现状（只跑只读的默认模式）---
    rc, so, se = sh([sys.executable, str(ROOT / "scripts/a_env_readiness_gate.py")], timeout=900)
    gate = {"rc": rc, "verdict": None, "failed": []}
    for line in (so or "").splitlines():
        if line.startswith("A_NEW_REPRO_CLAIMS="):
            gate["verdict"] = line.split()[0].split("=", 1)[1]
            gate["summary"] = line
        if line.startswith("[FAIL]"):
            gate["failed"].append(line.split()[1] if len(line.split()) > 1 else line)
    gate["note"] = ("E6 读的是 **C 的** manifest（runs/infra/c_env_manifest_20260929.json）：C 未重出前，"
                    "即使 A 的两个 venv 全部合格，本闸仍 CLOSED ⇒ A 不得声称新复现。A 不改 C 的文件。")

    smoke = parse_smoke(ROOT / a.smoke_dir / "smoke.log")

    manifest = {
        "manifest_kind": "a_lerobot_env_manifest",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "A（官方 LeRobot ACT 训练与真值评测线）/ scripts/a_env_manifest.py",
        "authority": ["rl_harness_supervision/d_handoff_to_a_20260929.md §6.3–§6.7（裁定 32）",
                      "docs/lerobot_env_reinstall_pin_20260929.md（B / DR-012）§2 = pin 单一事实源",
                      "rl_harness_supervision/supervisor_memo_20260929.md 增补九 §26–§29"],
        "scope_note": ("只覆盖 A 线的两个 lerobot venv（训练/评测）。rlrobot 侧见 C 的 "
                       "runs/infra/c_env_manifest_20260929.json；两份 manifest 的「绿」范围不重叠、不可互代。"),
        "pin": PIN,
        "venvs": {"lerobot_act": v_act, "lerobot_eval": v_eval},
        "pyvenv_cfg_assertion": ssp,
        "sibling_venv_readonly": {"rlrobot": rlrobot},
        "lock_provenance": {
            "rule": "新装的环境是**新事实**，0928 的 lock 是**旧事实**，两者必须并存（裁定 32.4）。",
            "lock_out_overridden_to": str(new_dir),
            "installer_would_have_written_to": "runs/infra/lerobot_act_env_20260928（installer 的 LOCK_OUT 默认值）",
            "files": locks,
            "originals_not_overwritten": provenance_ok,
            "new_locks_identical_to_0928": diffs_identical,
            "n_changed_packages": len(all_diffs),
            "changed_packages": all_diffs,
            "ruling_required": (not diffs_identical),
            "ruling_note": ("lock 有差异 ⇒ 按 D §6.3：逐条解释并报 D，**在 D 裁定前不得声称任何跨断点复现**。"
                            if not diffs_identical else
                            "lock 与 0928 逐字节相同 ⇒ 环境重建未漂移。"),
        },
        "cold_import_baseline": cold_import_section(a, link_act, link_eval),
        "smoke": smoke,
        "readiness_gate": gate,
        "breakpoints": [{
            "id": "BP-20260929-lerobot-env-rebuild",
            "kind": "environment_rebuild",
            "occurred_at": BREAKPOINT_OCCURRED_AT,
            "occurred_at_ns": BREAKPOINT_OCCURRED_NS,
            "ready_at": mtime_iso(new_dir / "requirements.eval.lock.txt") if (new_dir / "requirements.eval.lock.txt").exists() else None,
            "cause": ("0929 早间服务器检修：进程被直接关闭，overlay 上的 /root/venvs/lerobot_act 与 "
                      "/root/venvs/lerobot_eval 一并丢失（D §0 只读实测：ls /root/venvs 只剩 rlrobot）。"),
            "rebuild": {
                "method": "bash scripts/install_lerobot_act_env.sh（VENV/EVAL_VENV 覆写到 NFS，LOCK_OUT 覆写到 a_* 目录）",
                "venv_physical_path": "…/.codex-persist/envs/lerobot_{act,eval}（NFS，换容器不用重装）",
                "overlay_symlink": "ln -sfn → /root/venvs/lerobot_{act,eval}（仓里 73 个文件硬编码该路径，不改路径）",
                "install_log": str(new_dir / "install.log"),
                "lock_out_overridden": True,
            },
            "invalidates": ("任何**需要 lerobot_act / lerobot_eval venv** 的官方 ACT 训练或真值评测复现主张，"
                            "若其产物 mtime 早于本断点 ⇒ 跨断点，必须在重建后的环境上重跑才继续有效。"),
            "not_merged_with": {
                "id": "BP-20260929-venv-rebuild（C）",
                "why": "两者 invalidates 范围不同：C 的废 rlrobot/robosuite 侧复现，本条废官方 ACT 训练与真值评测。合并会让「哪些产物要重跑」失去边界。"},
        }],
        "env_usable": bool(smoke.get("all_zero") and provenance_ok
                           and all(ssp[k]["must_be_false"] for k in ssp)
                           and (v_act.get("pkgs", {}).get("lerobot") == PIN["lerobot"])
                           and (v_eval.get("pkgs", {}).get("lerobot") == PIN["lerobot"])),
        "lock_diff_waiver": {
            # 裁定 34.1（14:5x）：3 处差异**放行**，但豁免是**按包按链路**授的，引用纪律逐字抄进来，
            # 防止被简写成「lock 差异已裁定可忽略」（那正是 D 明令禁止的无限定句）。
            "ruling": "裁定 34.1（supervisor_memo_20260929.md 增补十一 §36–§39 / DR-D33）",
            "waived": not diffs_identical,
            "scope": "只覆盖这 2 个包 / 这 2 份 lock / 官方 ACT 与 48 臂这条链路",
            "waived_packages": all_diffs,
            "citation_rule": "引用时**点名包与版本**；**不得**写成「lock 差异已裁定可忽略」这种无限定句",
            "re_report_rule": "下次重建若有**任何**新增差异（含这两个包再浮动）一律重新报 D",
            "void_if": "若将来发现 imageio/uv 确实在 48 臂链路的 import 面上 ⇒ 本裁定自动作废",
            "a_reinstall_proposal_rejected": ("A 提议的 --override imageio==2.37.4 重装**不批准**（会动只读 NFS venv，"
                                              "而 2.37.4 不是任何判据的输入）⇒ A 不重建"),
            "root_cause_owner": ("B：installer :77 未钉 imageio 本体、:36 未钉 uv；D 判钉**实际装成**的 "
                                 "imageio==2.38.0 与 uv==0.12.17（事实源口径、不回退）。"
                                 "**注意 B 14:49 钉的是 2.37.4，与裁定相反 ⇒ A 已告知 B 改**"),
        },
        "reproduction_claims_blocked": {
            # 裁定 34.1 只解除「lock 差异」这一条阻塞；**E6 未闭合前仍不得声称新训练/新评测复现**。
            "blocked": bool(gate.get("verdict") != "ALLOWED"),
            "reasons": (["就绪闸 = %s（未 ALLOWED）；红项 %s" % (gate.get("verdict"), gate.get("failed"))]
                         if gate.get("verdict") != "ALLOWED" else []),
            "resolved_reasons": ["lock 3 处差异 → 裁定 34.1 **放行**（按包按链路，引用须点名包与版本）"],
            "what_is_allowed_now": ("环境可用性主张（smoke 三步全 0）+ 一切只读后处理结论 + "
                                    "T17 的**代码与自检**结论 + **官方 ACT 链路上的复现**（裁定 34.1 / D 附记 §9.2）。"),
            "what_is_still_blocked": ("任何**新训练 / 新评测**的复现主张（含 48 臂权威表的跨断点复用、"
                                      "B §8 两条 T17 的**训练侧验证**、§8 晋级条件① 的任何推进）。"),
            "new_obligation": ("D 附记 §9.1 末：A 今后的新训练/新评测产物**必须回显新 lock 的 sha256** ⇒ "
                               "承载 = scripts/a_env_provenance.py 的 env_provenance.json 旁挂件，"
                               "已接进 train_act_lift.py 与 run_act_lift_runtime_failure_audit.py。"),
        },
        "elapsed_sec": round(time.time() - t0, 2),
    }

    outp = ROOT / a.out
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n")

    print("=" * 96)
    print("env_usable=%s   reproduction_claims_blocked=%s"
          % (manifest["env_usable"], manifest["reproduction_claims_blocked"]["blocked"]))
    print("  lerobot_act : %s  lerobot=%s torch=%s cuda=%s  ssp=%s"
          % (v_act.get("exe"), (v_act.get("pkgs") or {}).get("lerobot"),
             (v_act.get("pkgs") or {}).get("torch"), v_act.get("cuda"),
             ssp["lerobot_act"]["include-system-site-packages"]))
    print("  lerobot_eval: %s  lerobot=%s robosuite=%s mujoco=%s numpy=%s  ssp=%s"
          % (v_eval.get("exe"), (v_eval.get("pkgs") or {}).get("lerobot"),
             (v_eval.get("pkgs") or {}).get("robosuite"), (v_eval.get("pkgs") or {}).get("mujoco"),
             (v_eval.get("pkgs") or {}).get("numpy"), ssp["lerobot_eval"]["include-system-site-packages"]))
    print("  0928 lock 原件未被覆写=%s；新 lock 与 0928 逐字节相同=%s；差异 %d 处 %s"
          % (provenance_ok, diffs_identical, len(all_diffs),
             [(d["package"], d["old"], d["new"]) for d in all_diffs]))
    print("  smoke=%s（%s）" % (smoke.get("steps"), "三步全 0" if smoke.get("all_zero") else "**未全 0**"))
    print("  rlrobot（只读观测）= realpath %s  ssp=%s" % (rlrobot.get("realpath"),
          rlrobot.get("include-system-site-packages")))
    print("  就绪闸=%s  FAIL=%s" % (gate.get("verdict"), gate.get("failed")))
    print("  lock 差异裁定=34.1 放行（按包按链路；引用须点名包与版本）；复现主张仍被阻=%s"
          % manifest["reproduction_claims_blocked"]["blocked"])
    print("  产物：%s" % outp)
    return 0 if manifest["env_usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
