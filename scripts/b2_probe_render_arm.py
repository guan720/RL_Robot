#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B2 · 渲染臂**端点复测**（裁定 88.5-1 的补偿控制 / d_handoff_to_b2 §20.4）。

## 它解决什么
`scripts/b2_s1_generate_dataset.py`（产出 formal-40 的那份字节 = `b6af48fc6d58`）只在**起点**
用 `gl_identity()` 实测过一次 `renderer_class`；终点没有独立复测 —— `:3624` 的 `nvidia_arm_now`
**复用同一个读数**。所以那份 manifest 里 `renderer_class` 只出现 1 次（机器 grep 计数 = 1），
而 D 的补偿控制要求"跑完立刻核 manifest 的**两个端点**"，并要三个字段落进产物：
`renderer_class_at_start` / `renderer_class_at_end` / `arm_stable`。

本件在 formal 跑完后**独立复测一次**，把三字段 + 判据 + **缺口披露**落成机器可读产物。

## 三条纪律（本件自己守，也自己留证）
1. **口径不另造**：`renderer_class` 用 `importlib` 复用生成器自己的 `gl_identity()`
   （同一个函数、同一把尺，否则"两端不一致"可能是尺不同而不是臂不同）；三网预检复用
   **E 的 `card_busy(strict=True)`**（裁定 85.0-2-1 / §19.5：不写第三份）。
2. **不静默、不塌缩**：运行内的终点读数**不存在**（那是缺口），本件把它写成
   `renderer_class_at_end_in_run = null` + 说明，**绝不**用起点值或本次复测值顶替
   （裁定 88.1-3 新红线 `absence_of_measurement_is_not_measurement_of_absence`）。
3. **报告器自己必须有牙**：`--tooth-software-arm` 用 D §19.2-4 的形态（`MUJOCO_GL=egl`
   **但不带前缀**）起一个子进程，断言本件会把它识别成**非** `nvidia_gpu`、并因此把
   `arm_stable` 判成 `false`。若它识别不出来（恒报 nvidia_gpu）⇒ `rc=3`，牙没咬，CI 不静默。

## rc
0 = 两端一致且都是 `nvidia_gpu`（`arm_stable=true`）；3 = 牙没咬 / 证据不可得（UNJUDGED）；
4 = 三网预检不清洁，拒绝起跑（不抢卡）；5 = 端点不一致或任一端不是 `nvidia_gpu`
（⇒ `environment_invalid=true`，裁定 88.5-1 的豁免作废）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
GENERATOR = ROOT / "scripts" / "b2_s1_generate_dataset.py"
E_CALIB = ROOT / "scripts" / "e_mainline_render_calib.py"
ACTIVATOR = "scripts/e_activate_gpu_render.sh"
LLVMPIPE_SLOWDOWN_REF = 12.64        # D §19.2 引用的实测倍数（osmesa/llvmpipe 臂 vs nvidia 臂）
WALL_OUTLIER_FACTOR = 2.0            # 换臂会造成阶跃；2× 中位数已远小于 12.64×，留足余量


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _sha12(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 22), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except OSError:
        return None


def _ident(p: Path) -> dict:
    """裁定 78.11：引用自己写入面内、可能仍在编辑的文件时，sha 必须在**落笔时刻重读**。"""
    try:
        st = p.stat()
        return {"path": str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),
                "sha256_12": _sha12(p), "n_lines": sum(1 for _ in open(p, "rb")),
                "bytes": st.st_size,
                "mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(
                    timespec="seconds")}
    except OSError as e:
        return {"path": str(p), "error": "%s: %s" % (type(e).__name__, e)}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def three_net(strict: bool = True) -> dict:
    """三网读数（复用 E 的实现，零抄写）。"""
    try:
        m = _load(E_CALIB, "e_calib_for_arm_probe")
        cb = m.card_busy(strict=strict)
    except Exception as e:                                      # noqa: BLE001
        return {"error": "%s: %s" % (type(e).__name__, e), "busy": None}
    try:
        smi = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu,temperature.gpu",
             "--format=csv,noheader"], capture_output=True, text=True, timeout=60)
        gpu = smi.stdout.strip()
    except Exception as e:                                      # noqa: BLE001
        gpu = "error: %s" % e
    try:
        apps = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv"], capture_output=True, text=True, timeout=60)
        apps_txt = apps.stdout.strip()
    except Exception as e:                                      # noqa: BLE001
        apps_txt = "error: %s" % e
    return {"three_net": cb, "nvidia_smi": gpu, "compute_apps_verbatim": apps_txt,
            "loadavg": list(os.getloadavg()), "ts": _now(),
            "caliber_source": "scripts/e_mainline_render_calib.py:card_busy(strict=%s)" % strict}


def activation_env() -> dict:
    keys = ("MUJOCO_GL", "PYOPENGL_PLATFORM", "LD_LIBRARY_PATH",
            "__EGL_VENDOR_LIBRARY_FILENAMES", "__EGL_VENDOR_LIBRARY_DIRS", "CUDA_VISIBLE_DEVICES")
    return {k: os.environ.get(k) for k in keys}


def gl_probe(generator_sha_expected: str | None = None) -> dict:
    """用**生成器自己的** `gl_identity()` 实测渲染臂（同一把尺）。"""
    out = {"method": "importlib 复用 scripts/b2_s1_generate_dataset.py:gl_identity()",
           "generator_identity": _ident(GENERATOR), "ts": _now()}
    gen_now = out["generator_identity"].get("sha256_12")
    out["generator_sha_matches_formal_batch"] = (
        None if generator_sha_expected is None else (gen_now == generator_sha_expected))
    try:
        g = _load(GENERATOR, "b2gen_for_arm_probe")
        out["gl_identity"] = g.gl_identity()
        out["renderer_class"] = (out["gl_identity"] or {}).get("renderer_class")
    except Exception as e:                                      # noqa: BLE001
        import traceback
        out.update({"error": "%s: %s" % (type(e).__name__, e),
                    "traceback": traceback.format_exc()[-1500:], "renderer_class": None})
    return out


def wall_evidence(manifest: dict) -> dict:
    ws = [float(e["wall_s"]) for e in (manifest.get("episodes") or []) if e.get("wall_s")]
    if not ws:
        return {"available": False, "note": "manifest 里没有 episodes[].wall_s ⇒ 这条证据不可得（写 null，不塌缩）"}
    med = statistics.median(ws)
    n_out = sum(1 for w in ws if w > WALL_OUTLIER_FACTOR * med)
    return {"available": True, "n_episodes": len(ws), "min_s": min(ws), "max_s": max(ws),
            "mean_s": round(sum(ws) / len(ws), 3), "median_s": round(med, 3),
            "max_over_median": round(max(ws) / med, 4),
            "outlier_criterion": "wall_s > %.1f × median" % WALL_OUTLIER_FACTOR,
            "n_episodes_exceeding_outlier_criterion": n_out,
            "llvmpipe_slowdown_reference_x": LLVMPIPE_SLOWDOWN_REF,
            "wall_if_switched_to_software_arm_s": round(med * LLVMPIPE_SLOWDOWN_REF, 1),
            "why_this_is_evidence": "换臂（nvidia → llvmpipe/osmesa）会让每集墙钟阶跃 ≈%.1f×；"
                                    "实测 max/median = %.4f ⇒ 40 集里**没有任何一集**出现换臂阶跃"
                                    % (LLVMPIPE_SLOWDOWN_REF, max(ws) / med)}


def late_render_evidence(manifest: dict) -> dict:
    er = manifest.get("episode_replay_comparison") or {}
    n_irr, n_slots = 0, 0
    for v in er.values():
        irr = (v or {}).get("image_repeat_render") or {}
        ps = irr.get("per_slot") or {}
        if isinstance(ps, dict) and ps:
            n_irr += 1
            n_slots += len(ps)
    g4 = {c["id"]: c.get("status") for c in ((manifest.get("gates") or {}).get("checks") or [])
          if str(c.get("id", "")).startswith(("G4b", "G4d"))}
    return {"n_episodes_in_replay_block": len(er),
            "n_episodes_with_late_render_measurements": n_irr,
            "n_slot_rows": n_slots, "g4b_g4d_status": g4,
            "why_this_is_evidence": "重放/连渲发生在**全部 40 集录制之后**（同一进程的运行末段）；"
                                    "它产出了非退化的逐槽像素测量 ⇒ 运行末段 GL 渲染路径是活的",
            "available": bool(n_irr)}


def build(manifest_path: Path, generator_sha_expected: str | None, tooth: bool) -> tuple[dict, int]:
    man_raw = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(man_raw)
    gli = manifest.get("gl_identity") or {}
    start_class = gli.get("renderer_class")
    pre = three_net(strict=True)

    doc = {
        "spec": "渲染臂端点复测（裁定 88.5-1 的补偿控制 / d_handoff_to_b2 §20.4 / §19.2）",
        "verdict_kind": "b2_render_arm_endpoint_probe",
        "generated_at": _now(), "generated_by": str(SCRIPT.relative_to(ROOT)),
        "script_identity": _ident(SCRIPT),
        "manifest": {"path": str(manifest_path), "sha256_12": _sha12(manifest_path),
                     "bytes": len(man_raw.encode("utf-8")),
                     "generated_at": manifest.get("generated_at"),
                     "generator_sha256_12": manifest.get("generator_sha256_12")},
        "caliber": {
            "renderer_class_source": "importlib 复用生成器的 gl_identity()（与起点同一函数）",
            "three_net_source": pre.get("caliber_source"),
            "activation_authority": 'eval "$(%s --print)"（裁定 70，不硬编码前缀目录名）' % ACTIVATOR,
            "why_same_caliber_matters": "两端若用不同的尺，'不一致'可能来自尺而不是臂 ⇒ 复用同一函数",
        },
        "activation_env": activation_env(),
        "gpu_preflight": pre,
        # ---- 起点（运行内实测，来自 manifest）----
        "renderer_class_at_start": start_class,
        "renderer_class_at_start_source": "demo_manifest.json:gl_identity.renderer_class（运行内实测）",
        "renderer_class_at_start_gl_strings": gli.get("gl_strings"),
        "renderer_class_at_start_method": gli.get("method"),
        # ---- 终点（运行内**没有**测 ⇒ null，不塌缩）----
        "renderer_class_at_end_in_run": None,
        "renderer_class_at_end_in_run_note":
            "**缺口如实登记**：产出这批的生成器（%s）在运行内**没有**终点复测 —— `:3624` 的 "
            "`nvidia_arm_now` 复用起点读数 ⇒ manifest 里 `renderer_class` 只出现 1 次。"
            "按裁定 88.1-3 的红线 `absence_of_measurement_is_not_measurement_of_absence`，"
            "这里写 null，**不用起点值或本次复测值顶替**。加项 1（硬 preflight + 收尾复测）"
            "落地后由生成器自己在运行内产出这个字段。" % (generator_sha_expected or "见 manifest"),
    }

    # ---- 终点（本次独立复测，运行结束后）----
    end = gl_probe(generator_sha_expected)
    doc["post_run_probe"] = end
    doc["renderer_class_at_end"] = end.get("renderer_class")
    doc["renderer_class_at_end_measurement_kind"] = "post_run_independent_probe_same_caliber"
    doc["renderer_class_at_end_caveat"] = (
        "这是**运行结束后**的独立复测（不是运行内连续监测）。它证明的是： EGL 前缀/vendor json "
        "在 formal 收尾之后仍然活着、且此刻的臂是它读到的那个值。运行中途是否换臂由下面两组"
        "**间接但机器算**的证据承载：`wall_time_evidence`（换臂会造成 ≈%.1f× 墙钟阶跃）与 "
        "`late_run_render_evidence`（运行末段的连渲真的产出了测量）。" % LLVMPIPE_SLOWDOWN_REF)
    try:
        gen_at = _dt.datetime.fromisoformat(manifest.get("generated_at"))
        doc["gap_s_since_run_end"] = round(
            (_dt.datetime.now().astimezone() - gen_at).total_seconds(), 1)
    except Exception:                                            # noqa: BLE001
        doc["gap_s_since_run_end"] = None
    doc["wall_time_evidence"] = wall_evidence(manifest)
    doc["late_run_render_evidence"] = late_render_evidence(manifest)

    # ---- arm_stable：四条判据逐条给实测值（不给"综合判断"这种黑箱）----
    we, lre = doc["wall_time_evidence"], doc["late_run_render_evidence"]
    crit = [
        {"id": "start_is_nvidia_gpu", "criterion": "renderer_class_at_start == 'nvidia_gpu'",
         "observed": start_class, "holds": start_class == "nvidia_gpu"},
        {"id": "end_is_nvidia_gpu", "criterion": "renderer_class_at_end == 'nvidia_gpu'（本次复测）",
         "observed": doc["renderer_class_at_end"], "holds": doc["renderer_class_at_end"] == "nvidia_gpu"},
        {"id": "no_wall_time_step_change",
         "criterion": "没有任何一集 wall_s > %.1f × median（换臂会造成 ≈%.1f× 阶跃）"
                      % (WALL_OUTLIER_FACTOR, LLVMPIPE_SLOWDOWN_REF),
         "observed": {"max_over_median": we.get("max_over_median"),
                      "n_exceeding": we.get("n_episodes_exceeding_outlier_criterion")},
         "holds": (we.get("available") is True
                   and we.get("n_episodes_exceeding_outlier_criterion") == 0)},
        {"id": "late_run_render_alive",
         "criterion": "运行末段的连渲对全部集都产出了逐槽测量（G4b/G4d 有行）",
         "observed": {"n_episodes_with_late_render_measurements":
                          lre.get("n_episodes_with_late_render_measurements"),
                      "n_episodes_in_replay_block": lre.get("n_episodes_in_replay_block"),
                      "g4b_g4d_status": lre.get("g4b_g4d_status")},
         "holds": (lre.get("available") is True
                   and lre.get("n_episodes_with_late_render_measurements")
                   == lre.get("n_episodes_in_replay_block")
                   and bool(lre.get("n_episodes_in_replay_block")))},
    ]
    doc["arm_stable_criterion"] = crit
    n_holds = sum(1 for c in crit if c["holds"])
    measurable = [c for c in crit if c["observed"] is not None]
    doc["arm_stable"] = bool(measurable) and n_holds == len(crit)
    doc["arm_stable_n_criteria"] = len(crit)
    doc["arm_stable_n_holds"] = n_holds
    doc["arm_stable_note"] = (
        "四条判据全成立 ⇒ `arm_stable=true`。**判据逐条带实测值**，不给"
        "「综合判断」这种黑箱（裁定 27.1：恒真的闸等于没有闸；牙见 `tooth_software_arm`）。"
        if doc["arm_stable"] else
        "有判据不成立或不可测 ⇒ `arm_stable=false`（不塌缩成 true）。")
    doc["endpoints_agree"] = (start_class == doc["renderer_class_at_end"])
    # D 的可推翻条件：任一端点不是 nvidia_gpu、或两端不一致 ⇒ 整批 environment_invalid
    doc["environment_invalid"] = bool(not doc["arm_stable"] or not doc["endpoints_agree"])
    doc["ruling_88_5_1_exemption_void"] = doc["environment_invalid"]
    doc["if_environment_invalid_then"] = (
        "不得通知 C2 重算、不得进 BC；加项 1（硬 preflight 拒绝 + 牙）立即升为**重跑前置**"
        if doc["environment_invalid"] else "N_A（本批两端一致且都是 nvidia_gpu）")

    rc = 0 if (doc["arm_stable"] and doc["endpoints_agree"]) else 5
    if end.get("error") or doc["renderer_class_at_end"] is None:
        rc = 3                      # 证据不可得 ⇒ UNJUDGED，不当作通过

    # ---- 牙：软件臂必须被识别出来（否则本件是恒报 nvidia_gpu 的报告器）----
    if tooth:
        doc["tooth_software_arm"] = run_tooth()
        if not doc["tooth_software_arm"].get("tooth_verified"):
            rc = 3 if rc == 0 else rc
    doc["post_run_readings_after_probe"] = three_net(strict=True)
    doc["rc"] = rc
    return doc, rc


def run_tooth() -> dict:
    """D §19.2-4 的形态：`MUJOCO_GL=egl` **但不带前缀** ⇒ 必须被识别成非 nvidia_gpu。

    这颗牙钉的是**报告器自己**：若 `gl_identity()` 在软件臂上也报 `nvidia_gpu`（或本件把
    "读不到"当成"没问题"），那 `arm_stable=true` 就是恒真的。子进程跑，不污染本进程的 GL 状态。
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("LD_LIBRARY_PATH", "__EGL_VENDOR_LIBRARY_FILENAMES",
                        "__EGL_VENDOR_LIBRARY_DIRS")}
    env["MUJOCO_GL"] = "egl"
    env["PYOPENGL_PLATFORM"] = "egl"
    out = {"tooth_id": "software_arm_must_be_identified",
           "form": "MUJOCO_GL=egl 且**不带** EGL 前缀（D §19.2-4 的牙形态）",
           "env_scrubbed": ["LD_LIBRARY_PATH", "__EGL_VENDOR_LIBRARY_FILENAMES",
                            "__EGL_VENDOR_LIBRARY_DIRS"],
           "command_verbatim": "%s %s --probe-only" % (sys.executable, SCRIPT)}
    try:
        p = subprocess.run([sys.executable, str(SCRIPT), "--probe-only"],
                           capture_output=True, text=True, env=env, timeout=300, cwd=str(ROOT))
        raw = p.stdout.strip()
        child = json.loads(raw[raw.index("{"):raw.rindex("}") + 1]) if "{" in raw else {}
    except Exception as e:                                      # noqa: BLE001
        out.update({"error": "%s: %s" % (type(e).__name__, e), "tooth_verified": False,
                    "note": "牙跑不起来 = 牙没咬，不得记成通过"})
        return out
    cls = child.get("renderer_class")
    out.update({"child_rc": p.returncode, "child_renderer_class": cls,
                "child_gl_renderer": ((child.get("gl_identity") or {}).get("gl_strings") or {}).get(
                    "GL_RENDERER"),
                "child_error": child.get("error"),
                "expected": "非 nvidia_gpu（mesa_cpu_software / unknown / unknown_error 都算识别出来）",
                "identified_as_not_nvidia": (cls is not None and cls != "nvidia_gpu"),
                "stderr_tail": (p.stderr or "")[-400:]})
    out["tooth_verified"] = bool(out["identified_as_not_nvidia"])
    out["consequence_if_blind"] = ("若这里报 nvidia_gpu，说明本件对软件臂是盲的 ⇒ `arm_stable` 恒真"
                                   "（缺陷类 ⑯ 空集平凡真 / ⑫ 探测器盲区）")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest",
                    default="runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--generator-sha-expected", default=None,
                    help="产出该批的生成器 sha256[:12]（裁定 78.11：登记复测时的生成器是否仍是那一份）")
    ap.add_argument("--no-tooth", action="store_true", help="不跑软件臂反向牙（默认跑）")
    ap.add_argument("--allow-cotenant", action="store_true",
                    help="三网不清洁也起跑（默认拒绝，rc=4；本件是诊断件，不抢卡）")
    ap.add_argument("--probe-only", action="store_true",
                    help="只把 gl_identity() 的结果打到 stdout（牙的子进程用）")
    a = ap.parse_args()

    if a.probe_only:
        print(json.dumps(gl_probe(None), ensure_ascii=False, indent=1, default=str))
        return 0

    mp = Path(a.manifest)
    mp = mp if mp.is_absolute() else (ROOT / mp)
    if not mp.exists():
        print(json.dumps({"error": "manifest 不存在", "path": str(mp)}, ensure_ascii=False))
        return 3
    pre = three_net(strict=True)
    if pre.get("three_net", {}).get("busy") and not a.allow_cotenant:
        ref = {"spec": "渲染臂复测**拒绝起跑**（三网不清洁）", "generated_at": _now(),
               "gpu_preflight": pre, "rc": 4}
        rp = mp.parent / ("refused_gpu_busy_%s.json" % _dt.datetime.now().strftime("%H%M%S"))
        rp.write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"refused": True, "reason": "三网读到卡上有活", "artifact": str(rp),
                          "gpu_preflight": pre}, ensure_ascii=False, indent=1))
        return 4

    doc, rc = build(mp, a.generator_sha_expected, not a.no_tooth)
    out = Path(a.out) if a.out else (mp.parent / "renderer_arm_endpoint_probe.json")
    out = out if out.is_absolute() else (ROOT / out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "artifact": str(out), "rc": rc,
        "renderer_class_at_start": doc["renderer_class_at_start"],
        "renderer_class_at_end": doc["renderer_class_at_end"],
        "renderer_class_at_end_in_run": doc["renderer_class_at_end_in_run"],
        "endpoints_agree": doc["endpoints_agree"],
        "arm_stable": doc["arm_stable"],
        "arm_stable_n_holds": "%d/%d" % (doc["arm_stable_n_holds"], doc["arm_stable_n_criteria"]),
        "criteria": [{"id": c["id"], "holds": c["holds"]} for c in doc["arm_stable_criterion"]],
        "environment_invalid": doc["environment_invalid"],
        "tooth_verified": (doc.get("tooth_software_arm") or {}).get("tooth_verified"),
        "tooth_child_renderer_class": (doc.get("tooth_software_arm") or {}).get(
            "child_renderer_class"),
        "gap_s_since_run_end": doc.get("gap_s_since_run_end"),
        "wall_max_over_median": (doc["wall_time_evidence"] or {}).get("max_over_median"),
    }, ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
