#!/usr/bin/env python
"""E 线**牙齿变异体自证件**（红线 `tooth_must_be_mutant_proven`，裁定 54.4 / 85.6 / 86.6-3）。

本轮（2026-09-30 02:2x）E 新装了 4 处闸 / 判定档，每一处都必须**两边都验**：
会咬（`must_go_red`）+ 不乱咬（`must_stay_green`）。只验一边 = 恒红闸或恒绿闸，都不算有牙。

| 变异体 | 目标闸 | 期望 |
|---|---|---|
| `M1_all_reps_skipped` | `e_render_determinism.py` 第四道闸（**没测到不许报绿**） | **must_go_red**：`exit 4` + `measurement_status=not_measured_all_reps_skipped_by_yield_gate` + `all_bitwise_deterministic=null` |
| `M2_osmesa_measured` | 同上 | **must_stay_green**：`exit 0` + `measurement_status=measured`（证明它不是恒红闸） |
| `M3_sampling_window_empty` | `e_activate_selfcheck.py` 的 `invalid_measurement` 档 | **must_go_red**：`verdict=invalid_measurement` + `exit 2`（**≠1**：没测到 ≠ GPU 坏了） |
| `M4_osmesa_negative_control` | 同上（integrity 档不得乱咬） | **must_stay_green**：`verdict=pass` + `exit 0` + `measurement_integrity.ok=true` |
| `M5_broken_icd_coldstart` | P0 的 `silent_fallback_must_fail_loudly`（裁定 85.9-3-3） | **must_go_red**：冷启动 `exit≠0`，且自证件 `verdict=fail`（**不是** `invalid_measurement`） |

**为什么本件全程不触卡**（B2 的 formal 采集在卡上，E 排末位、不抢，裁定 85.7-2）：
* `M1` 把 `card_busy()` 打成 busy ⇒ 批级让位闸把每个 rep 都跳过 ⇒ **一个 GPU 子进程都不会起**；
* `M3` 把 `run_child()` 与 `egl_device_probe()` 打成桩 ⇒ 不枚举 EGL 设备、不建上下文；
* `M2`/`M4` 是 **osmesa（llvmpipe，纯 CPU）**臂；`M5` 用**沙箱坏 ICD** ⇒ EGL 枚举到 0 个设备（实测 `child_nvidia_fds=[]`）。
**需要真卡的那一腿**（P0 的 `baseline` 反向牙 = must_stay_green）不在本件里，另按裁定 85.7-2 申报窗口跑，见 `daily_report.md` §E12.5。

纪律：monkeypatch 只发生在**本进程内**（不往生产件里塞测试钩子）；不 `rm`；产物只落 `--out-dir`；
每个数值主张同批带 `loadavg` + `nr_throttled`（裁定 82 §3）。
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import e_gpu_egl_verify as ev   # noqa: E402
import e_egl_probe as ep        # noqa: E402

OUT_DIR_DEFAULT = REPO / "runs" / "infra" / ("e_egl_coldstart_" + time.strftime("%Y%m%d")) / "gate_mutation"
STAMP = time.strftime("%Y%m%d_%H%M%S")
# 负对照臂要用**带 mujoco+OpenGL 的 venv 解释器**，不能用跑本件的 `/opt/conda/bin/python3`（它没装 mujoco）。
# 选 rlrobot 是为了与 21:54 那三份历史自证件**同一解释器**（`selfcheck_{cpu,mesa_egl,egl_nvidia}_20260929_2154*.json`
# 的 `python` 字段都是它）⇒ 负对照的可比性不被换解释器破坏。
# 第一次跑 M4 就是踩了这个坑：`sys.executable` ⇒ `ModuleNotFoundError: No module named 'mujoco'` ⇒ 假红，
# 如实登记在 §E12.4（**闸没问题，是测试台的问题**）。
VENV_PY = "/root/venvs/rlrobot/bin/python"
E_OWN_CMDLINE_MARKERS = ("e_selfcheck_gate_mutation", "e_render_determinism", "e_activate_selfcheck",
                         "e_egl_coldstart", "e_coldstart_gpu_render")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def m1_all_reps_skipped(out: Path) -> dict:
    """第四道闸的正向牙：让位闸把 rep 全跳过 ⇒ 必须 exit 4 且不许报 `all_bitwise_deterministic=true`。"""
    import e_render_determinism as det
    det = importlib.reload(det)
    real_card_busy = det.calib.card_busy
    fake_busy = {"busy": True, "strict": True, "compute_procs": [],
                 "nvidia_fd_holders": [{"pid": -1, "nvidia_devs": ["/dev/nvidia_stub"],
                                        "cmdline": "M1 变异体桩：不是真进程，也没触卡"}],
                 "cmdline_hits": ["M1_stub"], "cmdline_hits_all_other_line": [],
                 "excluded_own_pids": [], "detection_note": "M1 monkeypatch（不打桩就得真占卡，故打桩）"}
    name = f"MUT_M1_all_reps_skipped_{STAMP}.json"
    det.calib.card_busy = lambda strict=False: dict(fake_busy)
    buf = io.StringIO()
    argv = sys.argv
    try:
        sys.argv = ["e_render_determinism.py", "--backends", "egl_nvidia", "--reps", "2",
                    "--out-dir", str(out), "--out-name", name]
        with contextlib.redirect_stdout(buf):
            rc = det.main()
    finally:
        sys.argv = argv
        det.calib.card_busy = real_card_busy
    art = out / name
    doc = _read_json(art) if art.exists() else {}
    v = doc.get("verdict") or {}
    obs = {"exit_code": rc, "measurement_status": doc.get("measurement_status"),
           "all_bitwise_deterministic": v.get("all_bitwise_deterministic"),
           "non_deterministic_backend_cam_pairs": v.get("non_deterministic_backend_cam_pairs"),
           "n_runs": len(doc.get("runs") or []),
           "n_skipped_by_yield_gate": sum(1 for r in (doc.get("runs") or [])
                                          if r.get("skipped_reason") == "gpu_yield_gate_card_busy"),
           "per_backend": doc.get("per_backend"), "not_a_pass_present": "not_a_pass" in v}
    checks = {"exit_code_is_4": rc == 4,
              "measurement_status_marks_not_measured": str(doc.get("measurement_status", "")).startswith("not_measured"),
              "all_bitwise_deterministic_is_null": v.get("all_bitwise_deterministic", True) is None,
              "not_a_pass_note_present": "not_a_pass" in v}
    return {"mutant": "M1_all_reps_skipped", "expectation": "must_go_red",
            "target_gate": "e_render_determinism.py 第四道闸（没测到不许报绿 / exit 4）",
            "artifact": str(art), "observed": obs, "checks": checks,
            "mutation_effective": all(checks.values()),
            "gpu_touched": False,
            "how_mutated": "进程内把 `calib.card_busy` 打成 busy ⇒ 让位闸跳过全部 rep（不真占卡）",
            "stdout_tail": buf.getvalue().strip().splitlines()[-3:]}


def m2_osmesa_measured(out: Path) -> dict:
    """第四道闸的反向牙（must_stay_green）：真测到了 ⇒ 必须 exit 0，不许被新闸误伤。"""
    name = f"MUT_M2_osmesa_measured_{STAMP}.json"
    p = subprocess.run([sys.executable, str(REPO / "scripts" / "e_render_determinism.py"),
                        "--backends", "osmesa", "--reps", "1",
                        "--out-dir", str(out), "--out-name", name],
                       capture_output=True, text=True, timeout=900)
    art = out / name
    doc = _read_json(art) if art.exists() else {}
    v = doc.get("verdict") or {}
    obs = {"exit_code": p.returncode, "measurement_status": doc.get("measurement_status"),
           "all_bitwise_deterministic": v.get("all_bitwise_deterministic"),
           "n_ok_runs": sum(1 for r in (doc.get("runs") or []) if r.get("ok")),
           "renderer_is_cpu": "osmesa/llvmpipe（纯 CPU，不触卡）"}
    checks = {"exit_code_is_0": p.returncode == 0,
              "measurement_status_is_measured": doc.get("measurement_status") == "measured",
              "all_bitwise_deterministic_not_null": v.get("all_bitwise_deterministic") is not None}
    return {"mutant": "M2_osmesa_measured", "expectation": "must_stay_green",
            "target_gate": "同上（证明它不是恒红闸）", "artifact": str(art),
            "observed": obs, "checks": checks, "mutation_effective": all(checks.values()),
            "gpu_touched": False, "how_mutated": "无变异：真跑一条 osmesa 臂（对照腿）",
            "stdout_tail": p.stdout.strip().splitlines()[-2:]}


def m3_sampling_window_empty(out: Path) -> dict:
    """`invalid_measurement` 档的正向牙：采样窗没覆盖子进程 ⇒ 必须判 exit 2，**不是** exit 1。"""
    os.environ["E_MODE"] = "egl_nvidia"
    os.environ["E_OUT_DIR"] = str(out)
    import e_activate_selfcheck as sc
    sc = importlib.reload(sc)
    stub_child = {"ok": True, "gl_strings": ["NVIDIA Corporation", "NVIDIA A800-SXM4-80GB/PCIe/SSE2",
                                             "4.6.0 NVIDIA 590.48.01"],
                  "renders": {"64": {"frames": 10, "seconds": 0.01, "fps": 1000.0, "image_mean": 75.0}},
                  "loaded_gl_libs": {"libEGL_nvidia.so.590.48.01": 6, "libnvidia-eglcore.so.590.48.01": 5},
                  "returncode": 0, "env_extra": {}, "child_nvidia_fds": [],
                  "gpu_sampling": {"smi_enabled": True, "n_smi_samples": 0, "n_fd_polls": 0,
                                   "child_lifetime_s": 0.4,
                                   "window_covered_child_lifetime": False,
                                   "fds_measured_not_assumed": False,
                                   "smi_measured_not_assumed": False}}
    real_run_child, real_probe = sc.ev.run_child, sc.ev.egl_device_probe
    sc.ev.run_child = lambda *a, **k: dict(stub_child)
    sc.ev.egl_device_probe = lambda *a, **k: {"devices": [{"index": 0, "vendor": "NVIDIA"}],
                                             "note": "M3 桩：不真枚举 EGL 设备 ⇒ 不触卡"}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = sc.main()
    finally:
        sc.ev.run_child, sc.ev.egl_device_probe = real_run_child, real_probe
    arts = sorted(out.glob("selfcheck_egl_nvidia_*.json"), key=lambda q: q.stat().st_mtime)
    doc = _read_json(arts[-1]) if arts else {}
    mi = doc.get("measurement_integrity") or {}
    obs = {"exit_code": rc, "verdict": doc.get("verdict"), "decide_ok": doc.get("decide_ok"),
           "measurement_integrity_ok": mi.get("ok"),
           "activation_criteria_failed": doc.get("activation_criteria_failed"),
           "artifact": str(arts[-1]) if arts else None}
    checks = {"exit_code_is_2_not_1": rc == 2,
              "verdict_is_invalid_measurement": doc.get("verdict") == "invalid_measurement",
              "integrity_flagged": mi.get("ok") is False,
              "m0_label_present": any(str(x).startswith("M0") for x in (doc.get("activation_criteria_failed") or []))}
    return {"mutant": "M3_sampling_window_empty", "expectation": "must_go_red",
            "target_gate": "e_activate_selfcheck.py 的 invalid_measurement 档（exit 2）",
            "artifact": str(arts[-1]) if arts else None, "observed": obs, "checks": checks,
            "mutation_effective": all(checks.values()), "gpu_touched": False,
            "how_mutated": "把 `run_child` 打成「采样窗为空」的桩 + 把 `egl_device_probe` 打桩（不枚举设备）",
            "stdout_tail": buf.getvalue().strip().splitlines()[-3:]}


def m4_osmesa_negative_control(out: Path) -> dict:
    """`invalid_measurement` 档的反向牙：真跑一条 osmesa 负对照 ⇒ 必须 `pass` / exit 0，integrity 不许乱咬。"""
    import e_render_determinism as det
    env = det.activation_env("osmesa")
    env.update({"E_MODE": "osmesa", "E_OUT_DIR": str(out)})
    p = subprocess.run([VENV_PY, str(REPO / "scripts" / "e_activate_selfcheck.py")],
                       capture_output=True, text=True, env=env, timeout=900)
    arts = sorted(out.glob("selfcheck_osmesa_*.json"), key=lambda q: q.stat().st_mtime)
    doc = _read_json(arts[-1]) if arts else {}
    mi = doc.get("measurement_integrity") or {}
    obs = {"exit_code": p.returncode, "verdict": doc.get("verdict"),
           "measurement_integrity_ok": mi.get("ok"),
           "gpu_sampling": (doc.get("render_probe") or {}).get("gpu_sampling"),
           "child_nvidia_fds": doc.get("child_nvidia_fds"),
           "probe_bench_seconds": doc.get("probe_bench_seconds"),
           "probe_frames_cap": doc.get("probe_frames_cap"),
           "artifact": str(arts[-1]) if arts else None}
    checks = {"exit_code_is_0": p.returncode == 0,
              "verdict_is_pass": doc.get("verdict") == "pass",
              "integrity_ok": mi.get("ok") is True,
              "fds_were_polled_even_without_gpu_sampling": bool(
                  ((doc.get("render_probe") or {}).get("gpu_sampling") or {}).get("n_fd_polls", 0) > 0),
              "no_nvidia_fd_in_cpu_arm": not doc.get("child_nvidia_fds")}
    return {"mutant": "M4_osmesa_negative_control", "expectation": "must_stay_green",
            "target_gate": "同上（integrity 档不得乱咬 + 负对照仍必须 pass）",
            "artifact": str(arts[-1]) if arts else None, "observed": obs, "checks": checks,
            "mutation_effective": all(checks.values()), "gpu_touched": False,
            "how_mutated": "无变异：真跑 osmesa 负对照（顺带证明 fd 轮询现在对 CPU 臂也生效 ⇒ N5 不再空洞）",
            "stdout_tail": p.stdout.strip().splitlines()[-3:]}


def m5_broken_icd_coldstart(out: Path) -> dict:
    """P0 的正向牙（裁定 85.9-3-3）：沙箱坏 ICD ⇒ 冷启动必须响亮失败，且必须是 `fail` 而不是 `invalid_measurement`。"""
    import e_egl_coldstart as cs
    cs = importlib.reload(cs)
    sub = out / "M5_coldstart_mutant"
    sub.mkdir(parents=True, exist_ok=True)
    tooth = cs.tooth_mutant(sub)
    arm = tooth.get("arm") or {}
    obs = {"coldstart_exit_code": arm.get("exit_code"), "selfcheck_verdict": arm.get("selfcheck_verdict"),
           "renderer_class": arm.get("renderer_class"), "render_probe_ok": arm.get("render_probe_ok"),
           "child_nvidia_fds": arm.get("child_nvidia_fds"),
           "failure_mechanism": tooth.get("failure_mechanism"),
           "assertions": {k: v.get("ok") for k, v in (tooth.get("assertions") or {}).items()}}
    checks = {"tooth_proven_4_legs": tooth.get("tooth_proven") is True,
              "coldstart_exit_nonzero": bool(arm.get("exit_code")),
              "verdict_is_fail_not_invalid_measurement": arm.get("selfcheck_verdict") == "fail",
              "no_silent_cpu_fallback": arm.get("render_probe_ok") is False,
              "gpu_untouched": not arm.get("child_nvidia_fds")}
    return {"mutant": "M5_broken_icd_coldstart", "expectation": "must_go_red",
            "target_gate": "P0 `silent_fallback_must_fail_loudly`（裁定 85.9-3-3）",
            "artifact": arm.get("selfcheck_artifact"), "observed": obs, "checks": checks,
            "mutation_effective": all(checks.values()), "gpu_touched": False,
            "how_mutated": "沙箱前缀里的 `10_nvidia.json` 指向不存在的库（真前缀一个字节不碰）",
            "sandbox": tooth.get("sandbox", {}).get("sandbox_prefix")}


MUTANTS = {"M1": m1_all_reps_skipped, "M2": m2_osmesa_measured, "M3": m3_sampling_window_empty,
           "M4": m4_osmesa_negative_control, "M5": m5_broken_icd_coldstart}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mutants", default=",".join(MUTANTS), help="逗号分隔：M1..M5")
    ap.add_argument("--out-dir", default=str(OUT_DIR_DEFAULT))
    ap.add_argument("--out-name", default=f"GATE_MUTATION_SELFTEST_{STAMP}.json")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / args.out_name
    if target.exists():
        print(json.dumps({"verdict": "REFUSE", "reason": f"目标已存在，拒绝覆写: {target}"}, ensure_ascii=False))
        return 3
    want = [m.strip().upper() for m in args.mutants.split(",") if m.strip()]
    unknown = [m for m in want if m not in MUTANTS]
    if unknown:
        print(json.dumps({"verdict": "REFUSE", "reason": f"未知变异体 {unknown}；可选 {sorted(MUTANTS)}"},
                         ensure_ascii=False))
        return 3
    doc = {"artifact": str(target), "agent": "E",
           "task": "牙齿变异体自证（红线 tooth_must_be_mutant_proven，裁定 54.4 / 85.6 / 86.6-3）",
           "generator": "scripts/e_selfcheck_gate_mutation.py",
           "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
           "boundary_guard_before": ep.boundary_guard(),
           "load_before": ev.cpu_stat(), "gpu_before": ev.nvidia_smi_sample(),
           "gpu_contact_claim": "本件全程不触卡（见文件头的逐条理由）", "mutants": {}}
    for m in want:
        doc["mutants"][m] = MUTANTS[m](out)
        print(f"[mut] {m} {doc['mutants'][m]['expectation']} ⇒ "
              f"{'EFFECTIVE' if doc['mutants'][m]['mutation_effective'] else 'NOT_EFFECTIVE'}", flush=True)
    eff = {m: r["mutation_effective"] for m, r in doc["mutants"].items()}
    reds = {m: r for m, r in doc["mutants"].items() if r["expectation"] == "must_go_red"}
    greens = {m: r for m, r in doc["mutants"].items() if r["expectation"] == "must_stay_green"}
    doc["verdict_set_crosscheck"] = ("GREEN" if all(eff.values()) and reds and greens else "RED")
    doc["two_sided_proof_present"] = bool(reds) and bool(greens)
    doc["all_mutants_effective"] = all(eff.values()) and bool(eff)
    doc["boundary_guard_after"] = ep.boundary_guard()
    doc["load_after"] = ev.cpu_stat()
    doc["gpu_after"] = ev.nvidia_smi_sample()
    # 「本件没触卡」不能靠「显存读数 == 0」来证明：**他线**（B2 的 formal 采集）在卡上时读数就不是 0。
    # 用 fd 网做**归因**：看持有 /dev/nvidia* 的进程里有没有本件起的那些（按 cmdline 认）。
    import e_mainline_render_calib as calib
    busy = calib.card_busy(strict=True)
    holders = busy.get("nvidia_fd_holders") or []
    ours = [h for h in holders if any(mk in (h.get("cmdline") or "") for mk in E_OWN_CMDLINE_MARKERS)]
    mb, ma = doc["gpu_before"].get("memory_used_mib"), doc["gpu_after"].get("memory_used_mib")
    doc["gpu_contact_assessment"] = {
        "memory_used_mib_before": mb, "memory_used_mib_after": ma,
        "delta_mib": (ma - mb) if isinstance(mb, int) and isinstance(ma, int) else None,
        "nvidia_fd_holders_at_end": holders,
        "e_own_processes_holding_nvidia_fd": ours,
        "e_touched_the_card": bool(ours),
        "other_line_on_card_during_run": bool(holders) and not bool(ours),
        "claim": ("本件起的子进程**一个 `/dev/nvidia*` fd 都没持有**（M1/M3 打桩、M2/M4 是 osmesa 纯 CPU、"
                  "M5 用沙箱坏 ICD ⇒ EGL 枚举到 0 个设备）。若 `other_line_on_card_during_run=true`，"
                  "那个显存读数是**他线**的，不是本件的（裁定 85.0-2-1 的 fd 网归因口径）。"),
    }
    doc["gpu_untouched_by_this_selftest"] = not bool(ours)
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(target), "crosscheck": doc["verdict_set_crosscheck"],
                      "effective": eff,
                      "loadavg": [doc["load_before"].get("loadavg"), doc["load_after"].get("loadavg")],
                      "nr_throttled": [doc["load_before"].get("nr_throttled"), doc["load_after"].get("nr_throttled")],
                      "gpu_mem_mib": [doc["gpu_before"].get("memory_used_mib"), doc["gpu_after"].get("memory_used_mib")]},
                     ensure_ascii=False, indent=1))
    return 0 if doc["verdict_set_crosscheck"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
