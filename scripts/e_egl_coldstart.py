#!/usr/bin/env python
"""T-E-EGL-COLDSTART（裁定 85.9-3，P0）的**取证件**：②③④ 三项。

① 一条命令的冷启动自检 = `scripts/e_coldstart_gpu_render.sh`（本脚本不重复实现，只**验证**它）。
② `PERSIST_MANIFEST.json`：逐个 `.so` 的 sha256 + 字节数、vendor ICD 内容、venv 符号链接的源与目标、
   **机器可执行形式**的恢复步骤（`recovery_steps[*].argv`，不是散文）。
③ 静默回退必须响亮失败（**核心牙**）：在**沙箱副本**里把 `10_nvidia.json` 指向不存在的库
   （**不碰真前缀**）⇒ 激活后实测 `renderer_class` **必须 ≠ `nvidia_gpu`** 且自检 **exit ≠ 0**。
④ `.codex-persist` 恢复链路核实：NFS 归属、`watch` 守护进程语义（**它镜像什么、多久一次、重启后谁拉起它**）。

为什么 ③ 是核心（D 的原话，E 认）：若 EGL 失效时 mujoco **静默回退到 osmesa**，所有标着 `egl` 的数字
其实都是 osmesa 的数字，而 **92.374 ms/步（= 2.72× 预算）会被当成 7.300 ms/步** ⇒ 整条实时性结论被静默推翻。
裁定 83 §5 规定了「以实测 `GL_RENDERER` 为键」，**但没规定失败要响亮** ⇒ 本件补上。

纪律：不写系统目录、不 `ldconfig`、不 `apt/dpkg`、不 `rm`（沙箱建在 E 自己的产物目录里）。
每个数值主张同批带 `loadavg` + `nr_throttled`（裁定 82 §3）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import e_egl_probe as ep        # noqa: E402  复用边界闸，不另写一套（裁定 46.4）
import e_gpu_egl_verify as ev   # noqa: E402  复用 cpu_stat / lib_matrix / driver_version

PERSIST = Path("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist")
PREFIX = PERSIST / "egl-libs" / "590.48.01"
COLDSTART_SH = REPO / "scripts" / "e_coldstart_gpu_render.sh"
ACTIVATE_SH = REPO / "scripts" / "e_activate_gpu_render.sh"
VENV_LINK_DIR = Path("/root/venvs")
OUT_DIR = REPO / "runs" / "infra" / ("e_egl_coldstart_" + time.strftime("%Y%m%d"))

# 裁定 85.9-3-1 要写进 docs/infra-gpu-render.md 顶部的那**一条命令**（逐字，含 env -i）。
ONE_COMMAND = f"env -i /bin/bash {COLDSTART_SH}"


def sha256_file(p: Path, bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def fs_of(path: Path) -> dict:
    """这条路径归哪个文件系统，以及它**能不能跨容器重建活下来**。

    三档，不能只写"是不是 NFS"（那样会把两种性质完全不同的 overlay 内容混成一类）：
      `nfs`                    ⇒ 活（在 NFS 上）
      `overlay_image_baked`    ⇒ **条件活**：内容在镜像只读层，重建后**只要镜像不换就还在**
      `overlay_runtime_upper`  ⇒ 死：运行期写进 overlay 可写层的东西，重建后必然消失
    判据用 mtime 对比容器起点（`/proc/1` 的启动时刻，与 codex-persist 的容器指纹同源）：
    早于容器起点 = 镜像自带；晚于 = 运行期写的。
    """
    p = str(path)
    best = None
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            f = line.split()
            if len(f) < 3:
                continue
            mnt, fstype = f[1], f[2]
            if p == mnt or p.startswith(mnt.rstrip("/") + "/"):
                if best is None or len(mnt) > len(best["mount"]):
                    best = {"mount": mnt, "fstype": fstype, "device": f[0]}
    except OSError as exc:
        return {"path": p, "error": f"{type(exc).__name__}: {exc}"}
    row = {"path": p, **(best or {"mount": None, "fstype": "unknown", "device": None})}
    fstype = row["fstype"]
    if fstype == "nfs":
        row["rebuild_class"] = "nfs"
        row["survives_container_rebuild"] = True
        return row
    if fstype != "overlay":
        row["rebuild_class"] = f"other_{fstype}"
        row["survives_container_rebuild"] = None      # 不猜，如实标未定
        return row
    # overlay：分清「镜像只读层」与「运行期可写层」
    boot = None
    try:
        boot = Path("/proc/1").stat().st_mtime
    except OSError:
        pass
    mtimes = []
    for cand in (path, Path(p.rstrip("/")) if p.endswith("/") else path):
        try:
            mtimes.append(cand.lstat().st_mtime)
            break
        except OSError:
            continue
    mt = mtimes[0] if mtimes else None
    row["mtime"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mt)) if mt else None
    row["container_start"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(boot)) if boot else None
    if mt is None or boot is None:
        row["rebuild_class"] = "overlay_unknown_layer"
        row["survives_container_rebuild"] = None
    elif mt < boot:
        row["rebuild_class"] = "overlay_image_baked"
        row["survives_container_rebuild"] = "conditional_same_image"
        row["note"] = "镜像只读层：**换镜像（如 python 小版本变）就没了**，同镜像重建则还在"
    else:
        row["rebuild_class"] = "overlay_runtime_upper"
        row["survives_container_rebuild"] = False
        row["note"] = "运行期写进 overlay 可写层 ⇒ 容器重建后必然消失"
    return row


def link_row(link: Path) -> dict:
    row = {"link": str(link), "exists": link.exists(), "is_symlink": link.is_symlink()}
    if link.is_symlink():
        row["target"] = os.readlink(str(link))
        row["target_resolved"] = str(Path(os.readlink(str(link))))
        row["target_exists"] = link.exists()          # 悬空软链 ⇒ False
        row["link_fs"] = fs_of(link)                  # 软链**自己**在哪层（这才是重启会丢的那一环）
        row["target_fs"] = fs_of(Path(row["target"]))  # 本体在哪层
    return row


# ── ② PERSIST_MANIFEST.json ────────────────────────────────────────────────
def link_audit(prefix: Path) -> dict:
    """裁定 92.2-③：把「悬空符号链接」从**推断**变成**实测的后果字段**。

    为什么需要它（D 的原话，E 认）：v3 如实记了 `target="/NVIDIA-Linux/…"` 与 `sha256: null`，
    却**没有 `link_target_exists` / `dangling`** ⇒「记了事实、没记事实的后果」，与裁定 88.3-1 同族。
    这里两个字段都来自**一次真实的 stat 系统调用**（`Path.exists()` 跟随符号链接），
    **不是**从 `target` 字符串的形状（是否以 `/` 开头）推出来的 —— 绝对路径的链接也可以指向存在的目标。

    三值纪律（裁定 88.3-2 `aggregate_over_empty_set_must_be_null`）：被审计的集合 = 前缀里的**符号链接**。
    一条符号链接都没有 ⇒ 这个审计是在**空集**上做的 ⇒ `verdict="not_measured"` + 聚合值 `None`，
    **不许给出「0 条悬空」这种"通过"形状的读数**（那正是红线 `absence_of_measurement…` 要挡的东西）。
    """
    row: dict = {"prefix": str(prefix), "prefix_exists": prefix.is_dir(),
                 "measurement": ("每条 `link_target_exists` = `Path.exists()`（跟随符号链接的真实 stat）；"
                                 "`dangling = not link_target_exists`。**无推断、无字符串形状判断。**"),
                 "rulings": ["92.2-③ PERSIST_MANIFEST 加 link_target_exists / dangling 两个实测字段",
                             "88.3-1 absence_of_measurement_is_not_measurement_of_absence",
                             "88.3-2 aggregate_over_empty_set_must_be_null"]}
    if not prefix.is_dir():
        row.update({"verdict": "not_measured", "reason": "前缀目录不存在 ⇒ 无从审计（**不是**「0 条悬空」）",
                    "n_links_audited": None, "n_dangling": None, "dangling": None, "links": None})
        return row
    links = []
    for lnk in sorted(p for p in prefix.iterdir() if p.is_symlink()):
        raw = os.readlink(str(lnk))
        exists = lnk.exists()                      # ← 实测点（跟随链接）
        links.append({"name": lnk.name, "target": raw,
                      "target_is_absolute": raw.startswith("/"),
                      "target_resolved": str(Path(raw) if raw.startswith("/") else (lnk.parent / raw)),
                      "link_target_exists": exists,
                      "dangling": not exists})
    if not links:
        row.update({"verdict": "not_measured",
                    "reason": "前缀里一条符号链接都没有 ⇒ 审计集为空 ⇒ 聚合值必须是 null（裁定 88.3-2）",
                    "n_links_audited": 0, "n_dangling": None, "dangling": None, "links": []})
        return row
    n_dangling = sum(1 for x in links if x["dangling"])
    row.update({"verdict": "measured", "n_links_audited": len(links), "n_dangling": n_dangling,
                "dangling": sorted(x["name"] for x in links if x["dangling"]), "links": links,
                "empty_set_note": (
                    f"`dangling: []` 是**在 {len(links)} 条非空审计集上测出来的空结果**，不是「没测」；"
                    "审计集为空时本函数返回 `verdict=not_measured` + 聚合值 `null`")})
    return row


PROTECTED_MANIFEST_KEYS = ("prefix", "libs", "vendor_icd", "venvs", "venv_link_registry",
                           "recovery_steps", "boundary_guard", "load", "generated_at", "task",
                           "purpose", "one_command_recovery")


def build_manifest(artifact_name: str = "PERSIST_MANIFEST.json", extra: dict | None = None) -> dict:
    audit = link_audit(PREFIX)                     # 单一真源：逐条链接的实测值只算一次（裁定 46.4）
    audit_by_name = {x["name"]: x for x in (audit.get("links") or [])}
    libs, total = [], 0
    for f in sorted(PREFIX.iterdir()):
        if f.is_symlink():
            a = audit_by_name.get(f.name) or {}
            libs.append({"name": f.name, "kind": "symlink",
                         "target": a.get("target", os.readlink(str(f))),
                         "target_is_absolute": a.get("target_is_absolute"),
                         "target_resolved": a.get("target_resolved"),
                         "link_target_exists": a.get("link_target_exists"),   # 实测（裁定 92.2-③）
                         "dangling": a.get("dangling"),                       # 实测的**后果**
                         "sha256": None, "bytes": None})
            continue
        if not f.is_file():
            continue
        b = f.stat().st_size
        total += b
        row = {"name": f.name, "kind": "file", "bytes": b,
               "link_target_exists": None,   # N/A：不是符号链接（保持 schema 一致，消费方可直接 filter dangling）
               "dangling": False,            # 实测：它是**存在的真文件**
               "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))}
        if f.suffix in (".json",) or b <= 4096:
            row["content"] = f.read_text(errors="replace")     # ICD 这类小文本直接内联
            row["sha256"] = hashlib.sha256(row["content"].encode()).hexdigest()
        else:
            row["sha256"] = sha256_file(f)
        libs.append(row)

    icd = PREFIX / "10_nvidia.json"
    icd_parsed = None
    if icd.is_file():
        try:
            icd_parsed = json.loads(icd.read_text())
        except json.JSONDecodeError as exc:
            icd_parsed = {"parse_error": str(exc)}
    icd_lib = ((icd_parsed or {}).get("ICD") or {}).get("library_path")

    venvs = {}
    for name in sorted(p.name for p in PERSIST.joinpath("envs").iterdir() if p.is_dir()):
        body = PERSIST / "envs" / name
        row = {"body": str(body), "body_fs": fs_of(body),
               "pyvenv_cfg": (body / "pyvenv.cfg").read_text() if (body / "pyvenv.cfg").is_file() else None,
               "links": [link_row(VENV_LINK_DIR / name)]}
        # **D 没点名的那一环**：NFS 上的 venv 只是壳，它的解释器是指向**镜像层**的软链。
        binpy = body / "bin" / "python3.11"
        row["base_interpreter"] = link_row(binpy) if binpy.is_symlink() else {"path": str(binpy), "is_symlink": False}
        cfg = row["pyvenv_cfg"] or ""
        home = re.search(r"^home\s*=\s*(.+)$", cfg, re.M)
        row["pyvenv_home"] = home.group(1).strip() if home else None
        if row["pyvenv_home"]:
            row["pyvenv_home_fs"] = fs_of(Path(row["pyvenv_home"]))
        venvs[name] = row

    man = {
        "artifact": artifact_name,
        "task": "T-E-EGL-COLDSTART ②（裁定 85.9-3-2）",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "purpose": ("重启后的恢复必须是**机械的**、不依赖任何人的记忆。本件给出：库本体的逐文件 sha256、"
                    "vendor ICD 的原文、venv 软链的源与目标及其**各自所在的文件系统层**、"
                    "以及机器可执行的恢复步骤（argv 形式）。"),
        "one_command_recovery": ONE_COMMAND,
        "prefix": {"path": str(PREFIX), "fs": fs_of(PREFIX), "n_files": len(libs), "total_bytes": total,
                   "n_symlinks": sum(1 for x in libs if x["kind"] == "symlink"),
                   "n_regular_files": sum(1 for x in libs if x["kind"] == "file"),
                   "link_audit": audit},
        "vendor_icd": {"path": str(icd), "exists": icd.is_file(), "parsed": icd_parsed,
                       "library_path": icd_lib,
                       "library_path_exists": bool(icd_lib and Path(icd_lib).exists()),
                       "library_path_is_absolute": bool(icd_lib and str(icd_lib).startswith("/"))},
        "libs": libs,
        "venvs": venvs,
        "venv_link_registry": {"path": str(PERSIST / "envs" / "symlinks.json"),
                               "content": json.loads((PERSIST / "envs" / "symlinks.json").read_text())
                               if (PERSIST / "envs" / "symlinks.json").is_file() else None},
        "recovery_steps": [
            {"n": 1, "why": "确认 NFS 已挂载（库本体与 venv 本体都在上面；这一步不成立后面全不成立）",
             "argv": ["/bin/mountpoint", "-q", "/workspace/mnt/sppro"],
             "expect_exit": 0, "on_fail": "NFS 未挂载 ⇒ 找平台，本仓无法自恢复"},
            {"n": 2, "why": "重建 ~/.bashrc hook + 重放 venv 软链 + 起 watch 守护（容器重建后唯一入口）",
             "argv": ["/opt/conda/bin/python3", str(PERSIST / "bin" / "codex-persist"), "bootstrap"],
             "expect_exit": 0, "on_fail": "改跑第 3 步（只重建 venv 软链，不碰 ~/.codex）"},
            {"n": 3, "why": "只重放 venv 软链（`/root/venvs/*` 在临时层，重启后必丢）",
             "argv": ["/opt/conda/bin/python3", str(PERSIST / "bin" / "codex-persist"), "venvlink"],
             "expect_exit": 0, "on_fail": "手动 ln -s <persist>/envs/pi05_sim /root/venvs/pi05_sim"},
            {"n": 4, "why": "**一条命令完成 EGL 冷启动自检 + 自恢复**（C1 链路 / C2 软链 / C3 激活 / C4 实测断言）",
             "argv": shlex.split(ONE_COMMAND), "expect_exit": 0,
             "on_fail": "exit≠0 ⇒ **不要采集任何标 egl 的数字**（可能已静默退回 CPU 软渲染）"},
            {"n": 5, "why": "每个新 shell 里激活（环境变量是进程级的，重启/新 shell 必然为空）",
             "argv": ["/bin/bash", "-c", f'eval "$(/bin/bash {ACTIVATE_SH} --print)"'],
             "expect_exit": 0, "on_fail": "同第 4 步"},
        ],
        "boundary_guard": ep.boundary_guard(),
        "load": ev.cpu_stat(),
    }
    # 裁定 92.2 要求的**编务字段**（`supersedes` / `what_changed` / …）从外部 JSON 合并进来，
    # 而**实测字段一律不许被外部值覆盖**（`PROTECTED_MANIFEST_KEYS`）⇒ 测量永远是权威的那一半。
    if extra:
        clash = sorted(k for k in extra if k in PROTECTED_MANIFEST_KEYS)
        if clash:
            raise ValueError(f"--manifest-extra-json 不得覆盖实测字段: {clash}")
        man["extra_fields_provenance"] = {
            "merged_keys": sorted(extra), "protected_keys_refused": sorted(PROTECTED_MANIFEST_KEYS),
            "why": "编务字段（裁定要求的口径声明）可由外部件合并；**实测字段不可**，否则清单会变成自我背书"}
        man.update(extra)
    return man


# ── ③ 沙箱变异：ICD 指向不存在的库 ⇒ 必须响亮失败 ──────────────────────────
def build_sandbox(out: Path) -> dict:
    """在 E 自己的产物目录里造一个**沙箱前缀**：真库用软链指过去（不复制 331 MB），
    只有 `10_nvidia.json` 是坏的（library_path 指向一个不存在的文件）。**真前缀一个字节都不碰。**"""
    sb = out / "sandbox_prefix"
    sb.mkdir(parents=True, exist_ok=True)
    linked = 0
    for f in sorted(PREFIX.iterdir()):
        dst = sb / f.name
        if dst.is_symlink() or dst.exists():
            continue
        if f.name == "10_nvidia.json":
            continue                                   # 这一个要写坏版本
        dst.symlink_to(f if not f.is_symlink() else (PREFIX / os.readlink(str(f))))
        linked += 1
    missing = sb / "libEGL_nvidia_DOES_NOT_EXIST.so.0"
    broken = {"file_format_version": "1.0.0",
              "ICD": {"library_path": str(missing)},
              "_e_sandbox_note": ("裁定 85.9-3-3 的牙：library_path 指向一个**不存在**的库。"
                                  "真前缀未被触碰（本目录全是软链 + 这一个坏 json）。")}
    (sb / "10_nvidia.json").write_text(json.dumps(broken, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sandbox_prefix": str(sb), "n_symlinked_libs": linked,
            "broken_icd": str(sb / "10_nvidia.json"),
            "broken_library_path": str(missing),
            "broken_library_path_exists": missing.exists(),
            "real_prefix_untouched": {"path": str(PREFIX),
                                      "icd_sha256": sha256_file(PREFIX / "10_nvidia.json"),
                                      "boundary_guard": ep.boundary_guard()}}


def classify(gl_strings) -> str:
    """与 A2 的 `classify_renderer` 同口径（裁定 83 §5：以**实测 GL_RENDERER** 为键）。"""
    if isinstance(gl_strings, list):
        joined = " | ".join(str(s) for s in gl_strings)
        r = v = joined
    else:
        r = (gl_strings or {}).get("GL_RENDERER") or ""
        v = (gl_strings or {}).get("GL_VENDOR") or ""
    if not r:
        return "unknown_no_gl_string"
    if "NVIDIA" in r.upper() or "NVIDIA" in v.upper():
        return "nvidia_gpu"
    if "llvmpipe" in r or "softpipe" in r or "Mesa" in v or "Mesa/X.org" in r:
        return "mesa_cpu_software"
    return "unknown_other"


def run_coldstart(env_extra: dict, label: str, out: Path) -> dict:
    env = {"PATH": "/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
           "HOME": "/root", "LC_ALL": "C"}
    env.update({k: v for k, v in env_extra.items() if v is not None})
    t0 = time.perf_counter()
    p = subprocess.run(["/bin/bash", str(COLDSTART_SH)], capture_output=True, text=True,
                       env=env, timeout=900)
    row = {"label": label, "env_i_equivalent": True, "env": env,
           "exit_code": p.returncode, "wall_s": round(time.perf_counter() - t0, 2),
           "stderr_tail": p.stderr.strip().splitlines()[-14:],
           "stdout_tail": p.stdout.strip().splitlines()[-6:]}
    # 从自证件产物里取**实测**的 GL 身份（不靠 stdout 文案）
    arts = sorted(out.glob("selfcheck_*.json"), key=lambda q: q.stat().st_mtime)
    if arts:
        rep = json.loads(arts[-1].read_text())
        gls = rep.get("gl_strings") or []
        row["selfcheck_artifact"] = str(arts[-1])
        row["gl_strings"] = gls
        row["renderer_class"] = classify(gls)
        row["selfcheck_verdict"] = rep.get("verdict")
        row["child_nvidia_fds"] = rep.get("child_nvidia_fds")
        # 失败**机制**（不只记「失败了」，要记「被哪一层拦住的」）。这是把牙从「空洞成立」变成
        # 「有据成立」的关键：`renderer_class != nvidia_gpu` 在 `gl_strings` 为空时是**平凡真**，
        # 真正承重的证据是下面这几项（自证件自己的判据表 + 渲染子进程的原始报错）。
        row["selfcheck_decide_ok"] = rep.get("decide_ok")
        row["selfcheck_criteria_passed"] = rep.get("criteria_passed")
        row["selfcheck_criteria_failed"] = rep.get("criteria_failed")
        row["selfcheck_activation_criteria_failed"] = rep.get("activation_criteria_failed")
        rp = rep.get("render_probe") or {}
        row["render_probe_ok"] = rp.get("ok")
        row["render_probe_error"] = rp.get("error")
        row["egl_device_probe"] = rep.get("egl_device_probe")
        loaded = rp.get("loaded_gl_libs") or {}
        row["nvidia_gl_libs_loaded_in_child"] = sorted(k for k in loaded if "nvidia" in k.lower())
    else:
        row["renderer_class"] = "unknown_no_artifact"
        row["selfcheck_artifact"] = None
    row["load"] = ev.cpu_stat()
    return row


def tooth_mutant(out: Path) -> dict:
    """③ 的牙：坏 ICD ⇒ 必须**响亮失败**。**四条腿**，全对上才算有牙：
    ① `renderer_class != nvidia_gpu`；② 冷启动 `exit_code != 0`；
    ③ 自证件自己判 `verdict == "fail"`（`decide_ok is False`）——**非空洞腿**；
    ④ **没有静默回退**：渲染子进程要么直接报错、要么即使出了图也绝不被判成成功——**非空洞腿**。
    ①在 `gl_strings` 为空时是**平凡真**（空洞腿），承重的其实是③④ ⇒ 这一点如实写进产物，
    不假装四条腿等强（裁定 85.9-3-3 要的是「静默回退必须响亮失败」，那就得证明是哪一层响的）。"""
    sb = build_sandbox(out)
    mut_out = out / "mutant_broken_icd"
    mut_out.mkdir(parents=True, exist_ok=True)
    arm = run_coldstart({"E_GPU_RENDER_PREFIX": sb["sandbox_prefix"],
                         "E_OUT_DIR": str(mut_out),
                         "E_VENV_LINK": "/root/venvs/pi05_sim"},
                        "mutant_broken_icd", mut_out)
    rc_ok = arm["renderer_class"] != "nvidia_gpu"
    exit_ok = arm["exit_code"] != 0
    verdict_ok = arm.get("selfcheck_verdict") == "fail" and arm.get("selfcheck_decide_ok") is False
    # ④「没有静默回退」的机器判据：渲染子进程**没有**成功出图（`render_probe_ok is False`），
    # 或者即使出了图（例如 glvnd 退到 mesa）也**没有**被自证件判成通过（`verdict_ok` 仍为真）。
    # 两者任一成立 ⇒ 不存在「悄悄用 llvmpipe 出图、却被当成 egl/GPU 数字」的通道。
    silent_ok = (arm.get("render_probe_ok") is False) or verdict_ok
    rerr = arm.get("render_probe_error") or ""
    if arm.get("render_probe_ok") is False and "EGL" in rerr:
        mechanism = ("mujoco 在 `MUJOCO_GL=egl` 下**直接抛错**（EGL 设备显示初始化失败），"
                     "**没有**静默退回 osmesa/llvmpipe ⇒ 第一层就是响的")
    elif arm.get("renderer_class") == "mesa_cpu_software":
        mechanism = ("glvnd 退到了 mesa（llvmpipe），但**自证件按实测 GL_RENDERER 判 fail**"
                     "（裁定 83 §5 以实测为键）⇒ 第二层拦住，仍然响")
    else:
        mechanism = "见 `arm.render_probe_error` 与 `arm.selfcheck_criteria_failed`（本脚本不预设结论）"
    return {
        "gate": "silent_fallback_must_fail_loudly",
        "ruling": "85.9-3-3",
        "sandbox": sb,
        "arm": arm,
        "assertions": {
            "renderer_class_not_nvidia_gpu": {
                "ok": rc_ok, "observed": arm["renderer_class"],
                "leg_strength": ("vacuous_true_when_no_gl_string"
                                 if arm["renderer_class"].startswith("unknown_") else "substantive"),
                "note": ("`gl_strings` 为空 ⇒ 本腿平凡真；不作为承重证据（如实登记，不冒充）"
                         if arm["renderer_class"].startswith("unknown_") else
                         "实测到了 GL 串且不是 NVIDIA ⇒ 本腿承重")},
            "coldstart_exit_nonzero": {"ok": exit_ok, "observed": arm["exit_code"],
                                       "leg_strength": "substantive"},
            "selfcheck_verdict_fail": {"ok": verdict_ok,
                                       "observed": {"verdict": arm.get("selfcheck_verdict"),
                                                    "decide_ok": arm.get("selfcheck_decide_ok"),
                                                    "n_criteria_failed": len(arm.get("selfcheck_criteria_failed") or []),
                                                    "n_activation_criteria_failed": len(arm.get("selfcheck_activation_criteria_failed") or [])},
                                       "leg_strength": "substantive"},
            "no_silent_fallback_to_cpu_renderer": {"ok": silent_ok,
                                                   "observed": {"render_probe_ok": arm.get("render_probe_ok"),
                                                                "render_probe_error_head": rerr[:220],
                                                                "nvidia_gl_libs_loaded_in_child": arm.get("nvidia_gl_libs_loaded_in_child"),
                                                                "egl_device_probe": arm.get("egl_device_probe")},
                                                   "leg_strength": "substantive"},
        },
        "tooth_proven": bool(rc_ok and exit_ok and verdict_ok and silent_ok),
        "failure_mechanism": {"which_layer_fired": mechanism,
                              "load_bearing_legs": ["selfcheck_verdict_fail",
                                                    "no_silent_fallback_to_cpu_renderer",
                                                    "coldstart_exit_nonzero"],
                              "vacuous_leg_if_any": ("renderer_class_not_nvidia_gpu"
                                                     if arm["renderer_class"].startswith("unknown_") else None)},
        "why_this_is_the_core_tooth": (
            "若 EGL 失效时 mujoco 静默回退 osmesa，则所有标 `egl` 的数字其实都是 osmesa 的数字："
            "92.374 ms/步（2.72× 预算）会被当成 7.300 ms/步 ⇒ 整条实时性结论被静默推翻。"
            "本闸要求**响亮失败**：既不许判成 nvidia_gpu，也不许 exit 0，"
            "还必须有**非空洞**的一层（自证件判 fail + 渲染子进程没有静默出图）证明它是真响的。"),
        "load": ev.cpu_stat(),
    }


def tooth_baseline(out: Path) -> dict:
    """③ 的反向牙（must_stay_green）：真前缀 ⇒ 必须 `nvidia_gpu` 且 exit 0。
    只有正向牙没有反向牙 = 恒红闸（裁定 83.2 的 `Tc` 同族），所以两边都要。"""
    base_out = out / "baseline_real_prefix"
    base_out.mkdir(parents=True, exist_ok=True)
    arm = run_coldstart({"E_OUT_DIR": str(base_out)}, "baseline_real_prefix", base_out)
    rc_ok = arm["renderer_class"] == "nvidia_gpu"
    exit_ok = arm["exit_code"] == 0
    return {"gate": "coldstart_baseline_must_pass", "arm": arm,
            "assertions": {"renderer_class_is_nvidia_gpu": {"ok": rc_ok, "observed": arm["renderer_class"]},
                           "coldstart_exit_zero": {"ok": exit_ok, "observed": arm["exit_code"]}},
            "tooth_proven": bool(rc_ok and exit_ok), "load": ev.cpu_stat()}


def tooth_relink(out: Path) -> dict:
    """② 的牙：把 venv 软链**指到沙箱路径**（不碰 `/root/venvs/pi05_sim`，B2 正在用它）⇒
    C2 必须重建出正确的软链，且 C1–C3 通过。证明「重启后软链丢失」这一环真的被自动补上。"""
    fake_root = out / "sandbox_root_venvs"
    fake_root.mkdir(parents=True, exist_ok=True)
    link = fake_root / "pi05_sim"
    before = str(link) + " 不存在" if not link.exists() else os.readlink(str(link))
    env = {"E_VENV_LINK": str(link), "E_SKIP_GPU": "1", "E_OUT_DIR": str(out / "relink")}
    p = subprocess.run(["/bin/bash", str(COLDSTART_SH)], capture_output=True, text=True,
                       env={"PATH": "/opt/conda/bin:/usr/bin:/bin", "HOME": "/root", **env}, timeout=300)
    made = link.is_symlink() and os.readlink(str(link)) == str(PERSIST / "envs" / "pi05_sim")
    real_intact = (VENV_LINK_DIR / "pi05_sim").is_symlink() and \
        os.readlink(str(VENV_LINK_DIR / "pi05_sim")) == str(PERSIST / "envs" / "pi05_sim")
    return {"gate": "venv_symlink_auto_rebuild", "ruling": "85.9-3-1/②",
            "sandbox_link": str(link), "state_before": before,
            "exit_code": p.returncode,
            "stderr_tail": p.stderr.strip().splitlines()[-10:],
            "assertions": {
                "sandbox_link_rebuilt_correctly": {"ok": made,
                                                   "observed": os.readlink(str(link)) if link.is_symlink() else None},
                # **期望 5，不是 0**：本牙用 `E_SKIP_GPU=1` 跑（只验 C1–C3、不占卡），而冷启动脚本
                # 现在把这一档报成 **exit 5 = PARTIAL**（"没测 GPU"必须在退出码这一维也看得见）。
                # 断言仍是**精确等值**，不是放宽：改前期望 0、改后期望 5，牙的强度不变。
                "exit_partial_5": {"ok": p.returncode == 5, "observed": p.returncode,
                                   "expected": 5,
                                   "why_not_zero": ("0 会被读作「GPU 渲染可用」，而本臂**根本没测 GPU**"
                                                    "（裁定 87.1-2 partial_delivery_must_not_carry_a_whole_delivery_boolean）")},
                "real_link_untouched": {"ok": real_intact,
                                        "observed": os.readlink(str(VENV_LINK_DIR / "pi05_sim"))},
            },
            "tooth_proven": bool(made and p.returncode == 5 and real_intact),
            "load": ev.cpu_stat()}


# ── ④ .codex-persist 恢复链路核实 ─────────────────────────────────────────
def chain_verify() -> dict:
    pidfile = PERSIST / "watch.pid"
    pid = None
    if pidfile.is_file():
        try:
            pid = int(pidfile.read_text().strip())
        except ValueError:
            pid = None
    alive, cmdline, elapsed = False, None, None
    if pid and Path(f"/proc/{pid}").is_dir():
        alive = True
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace").replace("\0", " ").strip()
            elapsed = int(time.time() - Path(f"/proc/{pid}").stat().st_mtime)
        except OSError:
            pass
    log = PERSIST / "codex-persist.log"
    log_tail = log.read_text(errors="replace").strip().splitlines()[-8:] if log.is_file() else []
    return {
        "item": "T-E-EGL-COLDSTART ④（裁定 85.9-3-4）",
        "persist_root": {"path": str(PERSIST), "fs": fs_of(PERSIST)},
        "subdirs_on_nfs": {n: fs_of(PERSIST / n)["fstype"] for n in
                           ("egl-libs", "envs", "bin", "backup") if (PERSIST / n).exists()},
        "overlay_paths_that_die_on_rebuild": {
            p: fs_of(Path(p)) for p in ("/root", "/root/venvs", "/root/.bashrc", "/opt/conda", "/usr/share/glvnd/egl_vendor.d")
        },
        "watch_daemon": {
            "pidfile": str(pidfile), "pid": pid, "alive": alive, "cmdline": cmdline,
            "elapsed_s": elapsed, "elapsed_human": (f"{elapsed//3600}:{(elapsed%3600)//60:02d}" if elapsed else None),
            "log_tail": log_tail,
            "semantics": {
                "what_it_mirrors": "**只单向镜像 `~/.codex` → NFS `backup/`**（`cmd_watch` 循环里只调 `cmd_snapshot`）",
                "interval": "120 s（`watch 120`；`cmd_watch` 内部下限 `max(15, interval)`）",
                "does_it_restore": "**不**。`watch` 从不写回本地；恢复只发生在 `cmd_restore()`，"
                                   "由 `bootstrap` 或 `.bashrc` hook 调的 `cmd_auto()` 触发",
                "does_it_touch_egl_or_venv": "**`watch` 不碰**；`cmd_auto`/`cmd_bootstrap` 会调 `cmd_venvlink(None, [])` "
                                             "重放 `/root/venvs/*` 软链（登记表 = `envs/symlinks.json`，在 NFS 上）",
                "who_restarts_it_after_reboot": "**没有人自动拉起**。拉起它的是 `~/.bashrc` 里的 hook（`codex-persist auto`），"
                                                "而 `~/.bashrc` 本身在 overlay 临时层（`install_bashrc_hook` 自己就打印了这句警告）"
                                                "⇒ **容器重建后 hook 也没了，必须人工跑一次 `bootstrap`**。",
            },
        },
        "conclusion": (
            "**重启后没有任何自动恢复路径**：`~/.bashrc` hook 与 `/root/venvs/*` 软链同在 overlay 层，一起消失；"
            "`watch` 守护进程随容器一起死，且它本来也只做「本地 → NFS」的单向镜像、从不恢复。"
            "⇒ **裁定 85.9-3-4 的那个「若」成立**：`scripts/e_coldstart_gpu_render.sh` 的那一条手动命令是**唯一保障**，"
            "已按要求写进 `docs/infra-gpu-render.md` 顶部。"),
        "unbreakable_prerequisite": (
            "**但有一条 D 没点名的前提**：NFS 上的 venv 只是**壳**——`envs/pi05_sim/bin/python3.11` 是软链，"
            "指向 `/opt/conda/bin/python3.11`（`pyvenv.cfg` 的 `home=/opt/conda/bin`），而 `/opt/conda` 在 **overlay 层**。"
            "⇒ venv 能跨重启**当且仅当新镜像仍带同版本的 `/opt/conda/bin/python3.11`**。镜像换 python 小版本 ⇒ "
            "NFS 上的 venv 全体变悬空软链，`e_activate_gpu_render.sh` 再对也没用。"
            "冷启动自检的 C1 已把这条做成**显式断言**（base 解释器存在 + venv 解释器真能起进程），"
            "所以这种情况会**响亮失败**而不是静默降级。"),
        "load": ev.cpu_stat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stages", default="manifest,chain,relink",
                    help="逗号分隔：manifest / chain / relink / mutant / baseline（mutant+baseline 需 GPU 窗口）")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--out-name", default="COLDSTART_EVIDENCE.json")
    ap.add_argument("--manifest-name", default="PERSIST_MANIFEST.json",
                    help="② 的清单文件名。**同样受拒绝覆写闸保护**：v1 的那一份已被引用"
                         "（sha256-12 5d84871a3dd6），重跑必须换新名，不得原地覆盖（裁定 82 §2-4 / 83.5）。")
    ap.add_argument("--manifest-extra-json", default=None,
                    help="一个 JSON 物件路径，其键值合并进 PERSIST_MANIFEST 的**顶层**（裁定 92.2 的编务字段："
                         "`supersedes` / `superseded_by` / `what_changed` / `coldstart_evidence_authority_still` …）。"
                         "**不得含实测字段名**（prefix/libs/vendor_icd/… ⇒ 直接 refuse），测量永远权威。")
    args = ap.parse_args()
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / args.out_name
    if target.exists():
        print(json.dumps({"verdict": "REFUSE", "reason": f"目标已存在，拒绝覆写（append-only，裁定 82 §2-4 / 83.5）: {target}",
                          "hint": "换 --out-name 另落新件"}, ensure_ascii=False))
        return 3
    manifest_target = out / args.manifest_name
    if "manifest" in stages and manifest_target.exists():
        print(json.dumps({"verdict": "REFUSE",
                          "reason": f"{manifest_target.name} 已存在，拒绝覆写（append-only，裁定 82 §2-4 / 83.5）",
                          "existing_sha256_12": sha256_file(manifest_target)[:12],
                          "hint": "换 --manifest-name 另落新件；旧件是被引用过的字节，不许原地重生成"},
                         ensure_ascii=False))
        return 3

    payload = {"artifact": str(target), "agent": "E",
               "task": "T-E-EGL-COLDSTART（裁定 85.9-3，P0）",
               "one_command_recovery": ONE_COMMAND,
               "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
               "hostname": os.uname().nodename, "stages": stages,
               "boundary_guard_before": ep.boundary_guard(),
               "load_before": ev.cpu_stat()}
    if "manifest" in stages:
        extra = None
        if args.manifest_extra_json:
            extra_path = Path(args.manifest_extra_json)
            if not extra_path.is_file():
                print(json.dumps({"verdict": "REFUSE", "reason": f"--manifest-extra-json 不是可读文件: {extra_path}"},
                                 ensure_ascii=False))
                return 3
            extra = json.loads(extra_path.read_text(encoding="utf-8"))
            if not isinstance(extra, dict):
                print(json.dumps({"verdict": "REFUSE",
                                  "reason": "--manifest-extra-json 的顶层必须是 JSON 物件（键值对）"},
                                 ensure_ascii=False))
                return 3
            clash = sorted(k for k in extra if k in PROTECTED_MANIFEST_KEYS)
            if clash:
                print(json.dumps({"verdict": "REFUSE", "refused_keys": clash,
                                  "reason": "编务增补件**不得覆盖实测字段**（否则清单会变成自我背书，裁定 92.2-③ 的反面）",
                                  "protected_keys": sorted(PROTECTED_MANIFEST_KEYS)}, ensure_ascii=False))
                return 3
        man = build_manifest(artifact_name=args.manifest_name, extra=extra)
        manifest_target.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
        payload["persist_manifest"] = {"path": str(manifest_target),
                                       "sha256_12": sha256_file(manifest_target)[:12],
                                       "n_libs": man["prefix"]["n_files"],
                                       "total_bytes": man["prefix"]["total_bytes"],
                                       "n_symlinks": man["prefix"]["n_symlinks"],
                                       "link_audit_verdict": man["prefix"]["link_audit"]["verdict"],
                                       "n_dangling": man["prefix"]["link_audit"]["n_dangling"],
                                       "dangling_names": man["prefix"]["link_audit"]["dangling"],
                                       "icd_library_path_exists": man["vendor_icd"]["library_path_exists"]}
    if "chain" in stages:
        payload["chain_verify"] = chain_verify()
    if "relink" in stages:
        payload["tooth_relink"] = tooth_relink(out)
    if "mutant" in stages:
        payload["tooth_mutant"] = tooth_mutant(out)
    if "baseline" in stages:
        payload["tooth_baseline"] = tooth_baseline(out)

    teeth = {k: v.get("tooth_proven") for k, v in payload.items() if k.startswith("tooth_")}
    payload["teeth_summary"] = teeth
    # ── 裁定 87.1-2 `partial_delivery_must_not_carry_a_whole_delivery_boolean` ──────────
    # 顶层布尔的**量程必须与实际执行过的阶段一致**：v1 只跑了 manifest/chain/relink（不含 C4），
    # 却写着 `all_teeth_proven=true` ⇒ 下游（含 D）读顶层布尔就会把「部分交付」当成「全交付」。
    # D 明写：「诚实登记不能替代字段量程正确」（E 在 stderr 里写明了"不构成交付"，D 记功，但字段仍须改）。
    # ⇒ 三态（红线 88.3-1 `absence_of_measurement_is_not_measurement_of_absence`）：
    #    `COLDSTART_VERIFIED` = 五项全跑且全牙咬住；`PARTIAL` = 有阶段没跑（**枚举出被跳过的阶段名**）；
    #    `FAILED_*` = 五项全跑但有牙没咬住（**枚举出没咬住的牙**）。
    REQUIRED = ["manifest", "chain", "relink", "mutant", "baseline"]
    stage_key = {"manifest": "persist_manifest", "chain": "chain_verify", "relink": "tooth_relink",
                 "mutant": "tooth_mutant", "baseline": "tooth_baseline"}
    stages_executed = [s for s in REQUIRED if s in stages and stage_key[s] in payload]
    stages_skipped = [s for s in REQUIRED if s not in stages_executed]
    c4_measured = bool(payload.get("tooth_baseline", {}).get("arm", {}).get("gl_strings"))
    failed_teeth = sorted(k for k, v in teeth.items() if v is not True)
    if stages_skipped:
        delivery_status = "PARTIAL"
        all_teeth = "PARTIAL"          # D 明令：在全交付之前，这个字段必须写 PARTIAL，不得写 true
    elif failed_teeth:
        delivery_status = "FAILED_" + "_".join(t.replace("tooth_", "") for t in failed_teeth)
        all_teeth = False
    else:
        delivery_status = "COLDSTART_VERIFIED"
        all_teeth = True
    payload["delivery_status"] = delivery_status
    payload["stages_executed"] = stages_executed
    payload["stages_skipped"] = stages_skipped
    payload["c4_gl_renderer_measured"] = c4_measured
    payload["failed_teeth"] = failed_teeth
    payload["all_teeth_proven"] = all_teeth
    payload["delivery_status_semantics"] = {
        "COLDSTART_VERIFIED": "五项（①一条命令+C4 实测 / ② PERSIST_MANIFEST / ③ 双向牙 / ④ 恢复链路核实）全部执行且全部牙咬住",
        "PARTIAL": "**有阶段没跑**；被跳过的阶段名在 `stages_skipped` 里枚举。此时 `all_teeth_proven` 写字符串 "
                   "`\"PARTIAL\"` 而不是布尔（裁定 87.1-2 / 87.1-4-3）",
        "FAILED_*": "五项全跑但有牙没咬住；没咬住的牙在 `failed_teeth` 里枚举。"
                    "**注意区分**：若失败原因是采样窗为空，自证件会判 `invalid_measurement`（exit 2）"
                    "而不是 `fail`（exit 1）—— 那是「没测到」，不是「测到坏了」（红线 88.3-1）",
        "rulings": ["87.1-2 partial_delivery_must_not_carry_a_whole_delivery_boolean",
                    "87.1-4-3 顶层改 COLDSTART_VERIFIED + stages_executed/stages_skipped",
                    "88.3-1 absence_of_measurement_is_not_measurement_of_absence",
                    "88.3-2 aggregate_over_empty_set_must_be_null"],
    }
    payload["boundary_guard_after"] = ep.boundary_guard()
    payload["load_after"] = ev.cpu_stat()
    payload["boundary_clean_no_system_write"] = (
        payload["boundary_guard_after"]["ok"] and not payload["boundary_guard_after"]["forbidden_paths_present"])
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(target), "stages": stages,
                      "delivery_status": delivery_status,
                      "stages_executed": stages_executed, "stages_skipped": stages_skipped,
                      "c4_gl_renderer_measured": c4_measured, "teeth": teeth,
                      "all_teeth_proven": payload["all_teeth_proven"],
                      "boundary_ok": payload["boundary_clean_no_system_write"],
                      "loadavg": [payload["load_before"].get("loadavg"), payload["load_after"].get("loadavg")],
                      "nr_throttled": [payload["load_before"].get("nr_throttled"), payload["load_after"].get("nr_throttled")]},
                     ensure_ascii=False, indent=1))
    return 0 if delivery_status == "COLDSTART_VERIFIED" else (1 if delivery_status.startswith("FAILED") else 5)


if __name__ == "__main__":
    raise SystemExit(main())
