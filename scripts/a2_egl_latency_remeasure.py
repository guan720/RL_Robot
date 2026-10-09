#!/usr/bin/env python3
"""A2 / 裁定 59-② —— **egl(GPU, prefix-only) 下重测 π₀.₅ 闭环延迟** + 旧口径的**机器化回溯标注**

## 为什么要有这个脚本（三件事，都不许靠嘴说）

1. **裁定 59-②**：G3 那轮的 `loop_fps≈10.39 / env_step_fps≈11.91 / 0.21× 实时`
   （`runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json`）是 **CPU 渲染口径**；
   GPU(EGL) 解锁后渲染不再是瓶颈 ⇒ **瓶颈应移到 π₀.₅ 推理（≈0.517 s/chunk）**，
   这才是主线要的数字。本脚本在 **主线口径**（shim `DT=0.034` ⇒ 29.4118 Hz，裁定 53/58.2）
   下重测，并同时给出 **`n_action_steps=50`（出厂）与 `=25`（满足 v4 `H≥2n`）** 两档，
   因为二者的**每控制步摊薄推理开销差一倍**（S4 草案 §2.4）。
2. **回溯标注**：G3 的产物里**只记了 `MUJOCO_GL="egl"` 这个环境变量，从未记过 `GL_RENDERER`**
   （`grep -rl GL_RENDERER runs/vla/a2_*` = 0 命中，21:4x 实测）⇒ D 说的"CPU 渲染口径"
   在 A2 产物侧一直是 **`declared_only`**。本脚本用 `--mode env_only` **不带 prefix** 复现
   同一组环境配置，把当时的渲染器身份**实测出来**（预期 mesa/llvmpipe = CPU），
   并配一条**反向牙**：若不带 prefix 也拿到 NVIDIA，则回溯标注**判无效**（`retro_label.valid=false`）。
3. **tied 检查落进 zero-shot 侧产物**（D §12.11-3 / memo 增补：不许让下一个复核的人
   再误判"0/20 = 权重没加载"）：本脚本在**加载模型的那一次**就地重算
   `alias/twin/same_storage_data_ptr/bitwise_equal_in_model`，机器携带、不是抄写。

## 硬约束（本脚本自己遵守，且把遵守情况写进产物）

- **裁定 60 / E 线**：GPU 渲染**只走 prefix-only**（`LD_LIBRARY_PATH` +
  `__EGL_VENDOR_LIBRARY_FILENAMES` 指向 NFS 前缀 `.codex-persist/egl-libs/590.48.01/`），
  **不做任何系统写入、不 `ldconfig`**；本脚本**只读**系统目录并把结果记进 `boundary_facts`
  （判据同 `scripts/e_egl_probe.py:73` 的 `boundary_guard`；**这一项**A2 仍不 import E 的文件，
  避免跨线耦合）。
  **【裁定 85.0-2-① 已推翻 A2 的"一概不 import E 文件"自律】**：占卡探测器**必须**复用 E 的
  `card_busy()` 三网口径、**不得重造**（E 的牙已验过：M2 双向 + fd 网 + cmdline 网 + 纯 `sleep`
  无误报 + 扫描开销 0.08 s）。⇒ 本文件现在 `import` E 的 `e_mainline_render_calib.py`，
  并把被 import 件的**身份三元组**（路径 / sha256-12 / 行数）落进产物
  （`three_net.detector_module`），使"复用的是哪一版、E 改了没有"可核 —— 跨线耦合从
  "不发生"改为"**发生但被版本钉住**"。
- **裁定 59-③**：**不开多进程渲染**；本脚本单进程串行。
- **裁定 58.3**：`max_episode_steps` **保持 300**，但产物必须带 `episode_horizon_s=10.2`，
  超时/时长**一律按秒**登记；**跨频率不得按步数并列**。
- **裁定 46**：本脚本**不采集任何成功率**（`success_metrics_collected=false`），
  因此**不构成能力主张**（`capability_claim=false`）；`policy_executed=true` 的正当理由 =
  **推理延迟本身是被测对象**。
- **裁定 83§5（A2 澄清项）**：`policy_executed` 取**读法 A**「策略前向推理的输出驱动了 `env.step()`」，
  **不**取读法 B「以产出任务结果为目的执行策略」（那归 `capability_claim`）。定义逐字写进产物
  的 `policy_executed_definition`（裁定 50.1），顶层值 = 各模式级值的 **OR**、臂跑完后重算，
  由 `gates.policy_executed_consistency` 看守（自检 M4a 是它的输入级变异体，M4b/M4c 是绿见证）。
- **裁定 46.4 / 53.6**：所有吞吐/延迟数字带**五元标注**与 `loadavg`+`nr_throttled`，
  并自带 `cross_transport_ban`（不得与 osmesa/Piper/50 Hz/其它 venv 的数字互搬）。

## 用法

    P=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist
    V=$P/envs/pi05_sim/bin/python
    # 0) 自检（CPU，含 4 个变异体）
    MUJOCO_GL=egl $V scripts/a2_egl_latency_remeasure.py --selftest --out-dir runs/vla/a2_egl_latency_20260929
    # 1) 回溯标注臂：**不带 prefix**（预期 mesa/llvmpipe = CPU），不需要 GPU 计算
    MUJOCO_GL=egl CUDA_VISIBLE_DEVICES="" $V scripts/a2_egl_latency_remeasure.py \
        --mode env_only --tag retro_label_no_prefix --expect-renderer mesa --steps 100
    # 2) 主线臂：prefix-only 激活（GPU）
    LD_LIBRARY_PATH=$P/egl-libs/590.48.01:/usr/local/nvidia/lib:/usr/local/nvidia/lib64 \
    __EGL_VENDOR_LIBRARY_FILENAMES=$P/egl-libs/590.48.01/10_nvidia.json \
    MUJOCO_GL=egl PYOPENGL_PLATFORM=egl \
    $V scripts/a2_egl_latency_remeasure.py --mode env_only --tag mainline_egl_gpu --expect-renderer nvidia
    # 3) 闭环延迟（GPU + 模型）
    …同上环境… $V scripts/a2_egl_latency_remeasure.py --mode closed_loop \
        --weights-dir runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044 \
        --tokenizer-dir $P/hf-cache/modelscope/google/paligemma-3b-pt-224 \
        --n-episodes 3 --n-action-steps 50,25 --expect-renderer nvidia
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import pathlib
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
PERSIST = REPO.parent / ".codex-persist"
EGL_PREFIX = PERSIST / "egl-libs" / "590.48.01"
EGL_VENDOR_JSON = EGL_PREFIX / "10_nvidia.json"
# 判据来源（只引不改）：scripts/e_egl_probe.py:73 boundary_guard / :95 prefix_env
FORBIDDEN_SYSTEM_PATHS = (
    "/usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0",
    "/usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0",
    "/usr/lib/x86_64-linux-gnu/libnvidia-glcore.so.590.48.01",
    "/usr/lib/x86_64-linux-gnu/libnvidia-eglcore.so.590.48.01",
    "/usr/share/glvnd/egl_vendor.d/10_nvidia.json",
)
SYSTEM_RENDER_LIB_RE = r"glcore|eglcore|glsi|gpucomp|EGL_nvidia|GLX_nvidia|glvkspirv|nvoptix"

TOY_XML = """
<mujoco><worldbody><light pos="0 0 2"/><camera name="c" pos="1 0 1" xyaxes="0 1 0 -1 0 1"/>
<body pos="0 0 0.3"><freejoint/><geom type="sphere" size="0.1" rgba="1 0 0 1"/></body>
</worldbody></mujoco>
"""

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────── 复用（不另写一套口径）──────────────────────────
def _load_shim():
    from envs import gym_aloha_shim as shim
    return shim


def _load_amendments_module():
    """复用 A2 自己的 cotenant 判据（裁定 73），**不复制一份**（复用自己早先的实现 = 裁定 72 的
    `self_artifact_reuse_discipline`：这里显式 import，而不是凭记忆重写）。"""
    path = REPO / "scripts" / "a2_artifact_amendments_20260929.py"
    spec = importlib.util.spec_from_file_location("a2_artifact_amendments", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_eval_module():
    """复用 G3 评测脚本的 **同一套** policy 构造 / 渲染 / 动作适配 / 负载采样函数，
    保证重测数字与 G3 数字**只差被声明的那几个变量**（渲染器、DT、n_action_steps）。"""
    path = REPO / "scripts" / "a2_pi05_zeroshot_eval.py"
    spec = importlib.util.spec_from_file_location("a2_pi05_zeroshot_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_e_calib_module():
    """**复用 E 的三网探测器口径，不重造一份**（裁定 85.0-2-① 明写「复用 E 的实现口径，不重造」）。

    为什么必须 import 而不是抄：`card_busy()` 的三网（compute-apps / `/proc/*/fd` / `/proc/*/cmdline`）
    连同它的**锚点细节**（`OTHER_LINE_SCRIPT_RE` 用负向后顾 `(?<!\\w)` 才能吃到空格前的 `scripts/`、
    `GPU_INTENT_PATTERNS` 的窄档词表、`_own_tree()` 排除自身与祖先）都是 E 在 23:58 抢卡事故后
    调出来并验过牙的。抄一份 = 两处定义漂移（裁定 46.4 的根因）⇒ 显式 import，并把被 import 件的
    **身份三元组**（路径 / sha256-12 / 行数）落进产物，使"复用的是哪一版"可核。
    """
    path = REPO / "scripts" / "e_mainline_render_calib.py"
    spec = importlib.util.spec_from_file_location("e_mainline_render_calib", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["e_mainline_render_calib"] = mod      # E 的模块内部有 `sys.path` 依赖的兄弟 import
    spec.loader.exec_module(mod)
    return mod


def module_identity(path: pathlib.Path, loaded_from: str) -> dict:
    """被复用件的身份三元组（裁定 64：只有路径的引用不可核验）。"""
    raw = path.read_bytes()
    text = raw.decode(errors="ignore")
    return {"path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
            "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
            # **口径 = `wc -l`**（数换行符），与本仓所有文书里的行数一致；
            # 早先写的 `count("\n") + 1` 对"以换行结尾"的文件会**多算 1 行**（实测 E 的件：
            # `wc -l` = 1162 而旧公式给 1163）⇒ 就地改正，并把口径写进字段名。
            "n_lines_wc_l": text.count("\n"),
            "bytes": len(raw), "loaded_from": loaded_from,
            "reuse_not_reimplemented": True}


# ── 裁定 85.0 新红线 `card_busy_detector_must_include_fd_and_cmdline_nets` ──────────────────
# 根因（D 查实、A2 认）：`nvidia-smi --query-compute-apps` **只列已分配显存的进程**，
# 对「EGL 图形上下文」「正在加载模型尚未分配显存的进程」是盲的。A2 的 rep4/rep5 正是用
# `--query-compute-apps` + `ps` 当占卡判据（本文件旧 `:135`），于是把 B2 的 EGL 图形负载
# （E 于 00:42:53 实测：持 `/dev/nvidia2`+`/dev/nvidiactl`、util/mem = 11% / 102 MiB，
# 而 compute-apps = **空**）判成了「卡空」⇒ 两窗的清洁认证被降级为
# `undetermined_detector_blind_to_egl`（裁定 85.0-2-②，**数值带不变、只有标签变**）。
THREE_NET_RULING = {
    "ruling": "裁定 85.0-2-①：新红线 `card_busy_detector_must_include_fd_and_cmdline_nets`",
    "nets": ["compute_apps", "proc_fd_dev_nvidia", "proc_cmdline_gpu_intent"],
    "net_meanings": {
        "compute_apps": "`nvidia-smi --query-compute-apps`（**只**看到已分配显存的 compute 进程）",
        "proc_fd_dev_nvidia": "扫 `/proc/*/fd` 找持 `/dev/nvidia*` 者（比 compute-apps **早一步**：打开设备即命中）",
        "proc_cmdline_gpu_intent": ("扫 `/proc/*/cmdline`：**窄档** `gpu_intent`（明确要上卡的入口/关键字）"
                                    "与**宽档** `other_line_script`（任何他线脚本 `scripts/{a,a2,b,b2,c,c2,d}_*`）"),
    },
    "blind_spot_it_closes": ("EGL 图形负载与「已起跑但尚未分配显存」的进程在 compute-apps 里是**空**的；"
                             "rep4/rep5 的降级（`undetermined_detector_blind_to_egl`）就是这个盲区造成的"),
    "implementation_reused_from": "scripts/e_mainline_render_calib.py 的 `card_busy()`（**A2 不重造**，见 `three_net.detector_module`）",
    "attribution_strength": "inferred_from_pid_and_timeline（裁定 76.1：PID 跨命名空间不可见 ⇒ **不得写 confirmed**）",
}


def _ppid_of(pid: int):
    try:
        stat = pathlib.Path(f"/proc/{pid}/stat").read_text(errors="ignore")
        return int(stat.rsplit(")", 1)[-1].split()[1])
    except (OSError, IndexError, ValueError):
        return None


def drop_own_descendants(hits: list, own_pid: int, depth: int = 1) -> list:
    """三网命中里剔掉 **A2 自己派生的瞬时子进程**。

    为什么必须有这一步：`nvidia-smi` 自己会短暂打开 `/dev/nvidiactl` ⇒ 若不剔，采样器
    派生的 `nvidia-smi` 会被 fd 网当成「别人」，造成**自致假阳**（闸恒忙 ⇒ 永远拒绝开跑，
    与 RR-B2-18 那个「`contaminated_by_cotenant` 恒真 ⇒ 狼来了」是同族缺陷）。
    E 的 `_own_tree()` 只覆盖**自身 + 祖先**，不覆盖子进程 ⇒ 这一段是 A2 侧必须补的。
    **如实登记覆盖深度**：只查 `depth` 代直系子进程（`nvidia-smi` 不派生孙进程 ⇒ 1 代足够）。
    """
    out = []
    for h in hits or []:
        pid = h.get("pid") if isinstance(h, dict) else None
        if pid == own_pid:
            continue
        if depth >= 1 and isinstance(pid, int) and _ppid_of(pid) == own_pid:
            continue
        out.append(h)
    return out


def three_net_snapshot(calib, own_pid: int | None = None, strict: bool = True,
                       with_memory: bool = True) -> dict:
    """取一次**三网**读数 + `memory.used`，归一成 A2 产物字段。

    三项读数就是裁定 85.7-2-① 要求的那三项：`compute-apps 条数 / fd 网外来 PID 列表 / memory.used MiB`。
    """
    own_pid = own_pid if own_pid is not None else os.getpid()
    t0 = time.perf_counter()
    busy = calib.card_busy(strict=strict)
    fd_holders = drop_own_descendants(busy.get("nvidia_fd_holders") or [], own_pid)
    cmd_hits = drop_own_descendants(busy.get("cmdline_hits") or [], own_pid)
    cmd_narrow = [h for h in cmd_hits if h.get("gpu_intent")]
    cmd_wide_only = [h for h in cmd_hits if not h.get("gpu_intent") and h.get("other_line_script")]
    compute = busy.get("compute_procs") or []
    snap = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "strict": bool(busy.get("strict")),
        "n_compute_apps": len(compute),
        "compute_apps": compute[:20],
        "n_foreign_fd_holders": len(fd_holders),
        "foreign_fd_holders": fd_holders[:20],
        "n_other_line_gpu_intent": len(cmd_narrow),
        "other_line_gpu_intent": cmd_narrow[:20],
        "n_other_line_script_wide": len(cmd_wide_only),
        "other_line_script_wide": cmd_wide_only[:20],
        "busy_per_detector": bool(busy.get("busy")),
        "excluded_own_pids": busy.get("excluded_own_pids"),
        "own_descendants_also_excluded": True,
        "own_descendant_depth_covered": 1,
        "detection_note": busy.get("detection_note"),
        "scan_overhead_s": None,
    }
    if with_memory:
        snap["memory_used_mib"] = nvidia_smi().get("memory_used_mib")
    snap["scan_overhead_s"] = round(time.perf_counter() - t0, 4)
    return snap


def three_net_yield_gate(snap: dict | None, *, declared_nets: list | None = None,
                         detector_module: dict | None = None) -> dict:
    """裁定 76.2 的 `per_batch_gpu_yield_gate` **升级三网**（裁定 85.0-2-①）。

    判红的三个独立理由（任一命中即拒绝开跑）：
      ① `n_compute_apps > 0`；② `n_foreign_fd_holders > 0`；③ 窄档 `n_other_line_gpu_intent > 0`
         或（`strict=True` 时）宽档 `n_other_line_script_wide > 0`。
    **缺证据时不许判绿**（与 `classify_cotenant` 同一条纪律）：`snap is None` ⇒ `ok=False`、
    `refuse=True`、理由 `no_three_net_evidence`。
    """
    nets = declared_nets if declared_nets is not None else list(THREE_NET_RULING["nets"])
    reasons: list[str] = []
    checks = {
        "detector_uses_three_nets": bool(set(nets) >= set(THREE_NET_RULING["nets"])),
        "detector_module_identity_recorded": bool(detector_module and detector_module.get("sha256_12")),
        "evidence_present": snap is not None,
    }
    if not checks["detector_uses_three_nets"]:
        reasons.append(f"探测器只用了 {nets}，缺 {sorted(set(THREE_NET_RULING['nets']) - set(nets))}"
                       "⇒ 违反红线 `card_busy_detector_must_include_fd_and_cmdline_nets`")
    if not checks["detector_module_identity_recorded"]:
        reasons.append("未记录被复用的 E 探测器身份三元组 ⇒ 无法核「复用的是哪一版」")
    if snap is None:
        reasons.append("no_three_net_evidence：没有三网读数 ⇒ **不许**判「卡空」")
        checks.update({"no_compute_app": False, "no_foreign_fd_holder": False,
                       "no_other_line_gpu_intent": False, "memory_used_mib_is_zero": False})
        return {"ok": False, "refuse": True, "checks": checks, "reasons": reasons,
                "n_red_teeth_reasons": len(reasons), "three_net": None,
                "ruling": THREE_NET_RULING["ruling"],
                "detector_nets_declared": nets, "detector_module": detector_module}
    checks["no_compute_app"] = int(snap.get("n_compute_apps") or 0) == 0
    checks["no_foreign_fd_holder"] = int(snap.get("n_foreign_fd_holders") or 0) == 0
    checks["no_other_line_gpu_intent"] = int(snap.get("n_other_line_gpu_intent") or 0) == 0
    checks["no_other_line_script_wide_when_strict"] = (
        int(snap.get("n_other_line_script_wide") or 0) == 0 if snap.get("strict") else True)
    mem = snap.get("memory_used_mib")
    checks["memory_used_mib_is_zero"] = (mem == 0) if isinstance(mem, int) else False
    if not checks["no_compute_app"]:
        reasons.append(f"compute-apps 网命中 {snap.get('n_compute_apps')} 条：{snap.get('compute_apps')}")
    if not checks["no_foreign_fd_holder"]:
        reasons.append(f"**fd 网**命中 {snap.get('n_foreign_fd_holders')} 个持 `/dev/nvidia*` 的外来 PID"
                       f"（compute-apps 对它们是盲的）：{[h.get('pid') for h in (snap.get('foreign_fd_holders') or [])]}")
    if not checks["no_other_line_gpu_intent"]:
        reasons.append(f"**cmdline 窄档**命中 {snap.get('n_other_line_gpu_intent')} 个他线 GPU 意图进程")
    if snap.get("strict") and not checks["no_other_line_script_wide_when_strict"]:
        reasons.append(f"**cmdline 宽档**（strict=True）命中 {snap.get('n_other_line_script_wide')} 个他线脚本")
    if not checks["memory_used_mib_is_zero"]:
        reasons.append(f"`memory.used = {mem} MiB ≠ 0（裁定 85.11 `unexplained_nonzero_reading_must_block_clean_claim`："
                       "**非零读数未被解释就不许声称卡空**）")
    ok = all(checks.values())
    return {"ok": ok, "refuse": not ok, "checks": checks, "reasons": reasons,
            "n_red_teeth_reasons": len(reasons),
            "three_net": {"n_compute_apps": snap.get("n_compute_apps"),
                          "n_foreign_fd_holders": snap.get("n_foreign_fd_holders"),
                          "n_other_line_gpu_intent": snap.get("n_other_line_gpu_intent"),
                          "n_other_line_script_wide": snap.get("n_other_line_script_wide"),
                          "memory_used_mib": mem},
            "ruling": THREE_NET_RULING["ruling"],
            "detector_nets_declared": nets, "detector_module": detector_module,
            "scan_overhead_s": snap.get("scan_overhead_s")}


def three_net_contamination(samples: list, snapshots: list | None = None) -> dict:
    """把三网证据汇成一个**只会更严、不会更松**的污染判据（裁定 73 + 85.0）。

    - **计入污染**：compute-apps 命中 ∪ fd 网外来持有者 ∪ cmdline **窄档** GPU 意图。
      （fd 网这一项正是 rep4/rep5 的盲区：compute-apps 空但 EGL 上下文持 `/dev/nvidia*`。）
    - **不自动计入污染、但如实登记**：cmdline **宽档**（任何他线脚本）。理由：一条**纯 CPU**
      的他线脚本不是 GPU 共租者；把宽档当污染判据会造成 RR-B2-18 那个「恒真 ⇒ 狼来了」缺陷。
      宽档只用于 **yield 闸**（拒绝开跑，`strict=True`），不用于事后污染定性。
      **这是 A2 对裁定 73 判据的口径切分，显式登记，D 可推翻。**
    - **缺证据不许输出 false**：一个样本都没有 ⇒ `unknown_not_collected`。
    """
    snaps = list(samples or []) + list(snapshots or [])
    if not snaps:
        return {"contaminated_three_net": "unknown_not_collected",
                "reason": "窗口内没有任何三网样本 ⇒ 既不能判 contaminated，也**不许**判 clean",
                "n_samples": 0}
    compute = [q for s in snaps for q in (s.get("compute_apps") or s.get("non_self_gpu_procs") or [])]
    fd = [q for s in snaps for q in (s.get("foreign_fd_holders") or [])]
    narrow = [q for s in snaps for q in (s.get("other_line_gpu_intent") or [])]
    wide = [q for s in snaps for q in (s.get("other_line_script_wide") or [])]
    mem = [s.get("memory_used_mib") for s in snaps if isinstance(s.get("memory_used_mib"), int)]
    hit = bool(compute or fd or narrow)
    why = []
    if compute:
        why.append(f"compute-apps 网命中 {len(compute)} 次")
    if fd:
        why.append(f"**fd 网**命中 {len(fd)} 次（外来 PID "
                   f"{sorted({h.get('pid') for h in fd if isinstance(h, dict)})[:8]}）")
    if narrow:
        why.append(f"cmdline 窄档命中 {len(narrow)} 次")
    return {
        "contaminated_three_net": bool(hit),
        "reason": ("；".join(why) if hit else "三网（compute-apps / fd / cmdline 窄档）在全窗口零命中"),
        "n_samples": len(snaps),
        "net_hit_counts": {"compute_apps": len(compute), "proc_fd": len(fd),
                           "cmdline_narrow": len(narrow), "cmdline_wide_registered_only": len(wide)},
        "wide_net_hits_do_not_auto_contaminate": True,
        "wide_net_split_rationale": ("宽档（任何他线脚本）只喂 yield 闸、不喂污染定性：纯 CPU 的他线脚本"
                                     "不是 GPU 共租者，把它当污染判据会重演 RR-B2-18 的「恒真 ⇒ 狼来了」"
                                     "（裁定 85.6-2）。**这是 A2 的口径切分，D 可推翻。**"),
        "memory_used_mib_max": max(mem) if mem else None,
        "memory_used_mib_values": sorted(set(mem)),
        "attribution_strength": "inferred_from_pid_and_timeline",
        "ruling": "裁定 73 + 85.0-2-①；缺证据不许 false（与 `classify_cotenant` 同一条纪律）",
    }


# ────────────── 运行时 cotenant 采样（裁定 76.3 红线 `cotenant_evidence_must_be_runtime`）──────────────
class RuntimeCotenantSampler:
    """**周期性**采共租证据的后台线程。

    为什么必须有它：本脚本原先只在臂的**前后各采一次** GPU 进程，却把字段写成
    `collected_at_run_time=True` —— 而它自己的 caveat 已经承认「窗口中途的瞬时并发无法回溯」。
    裁定 76.3 正是把这一点判为**纪律缺口**（红线级），要求「运行中周期采
    `--query-compute-apps` + `ps`，落 `cotenant_samples[]`」。本类就是那条裁定的机器承载。

    **裁定 85.0-2-① 的升级（本轮）**：`--query-compute-apps` + `ps` **不够**——它对 EGL 图形
    上下文与「已起跑但尚未分配显存」的进程是盲的（rep4/rep5 因此被降级为
    `undetermined_detector_blind_to_egl`）。⇒ 每个样本**额外**落一次 E 的 `card_busy()` 三网读数
    （compute-apps / `/proc/*/fd` 持 `/dev/nvidia*` 者 / cmdline 窄档+宽档）与 `memory.used`。

    设计约束：
    - 采样失败**不得**打断被测臂（每次采样都吞异常并记 `sampler_error`）；
    - **开销自己记账，不写死一个百分比**：每个样本现在是 `nvidia-smi`×2（`--query-compute-apps`
      与 `--query-gpu=memory.used`）+ E 的 `gpu_snapshot()`×1 + `/proc` 全扫×2 + `ps`×1。
      旧 docstring 那句「开销 <5%」是**一网时代**的估算，三网后已不成立 ⇒ 改为**实测并登记**
      （`sampler_overhead_s` / `sampler_overhead_pct_of_window` / `three_net.scan_overhead_s_max`），
      读者按实测值判断，A2 不预先声称一个好看的百分比；
    - **归因强度只能是 inferred**（裁定 76.1：容器内 `process_name` 为空、PID 跨命名空间不可见）。
    """

    def __init__(self, am_module, interval_s: float = 2.0, own_pid: int | None = None,
                 calib=None, three_net_strict: bool = True):
        self.am = am_module
        self.interval_s = float(interval_s)
        self.own_pid = own_pid if own_pid is not None else os.getpid()
        self.calib = calib                      # E 的 `e_mainline_render_calib`（三网探测器，不重造）
        self.three_net_strict = bool(three_net_strict)
        self.samples: list[dict] = []
        self.sampler_overhead_s = 0.0
        self.three_net_errors: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started_at: str | None = None
        self.stopped_at: str | None = None
        self._n_three_net_ok = 0

    def _one_sample(self) -> dict:
        t0 = time.perf_counter()
        out: dict = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                     "wall_s_since_start": round(time.perf_counter() - self._t_start, 3)}
        try:
            procs = self.am.gpu_procs()
            out["gpu_compute_procs"] = procs
            out["gpu_compute_proc_count"] = len(procs)
            out["non_self_gpu_procs"] = [q for q in procs if q.get("pid") != self.own_pid]
            out["non_self_gpu_proc_count"] = len(out["non_self_gpu_procs"])
        except Exception as exc:
            out["gpu_error"] = f"{type(exc).__name__}: {exc}"
        try:
            la = os.getloadavg()
            out["loadavg_1m"], out["loadavg_5m"], out["loadavg_15m"] = la[0], la[1], la[2]
        except Exception as exc:
            out["loadavg_error"] = f"{type(exc).__name__}: {exc}"
        try:
            stat = {}
            for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
                k, _, v = ln.partition(" ")
                stat[k] = int(v)
            out["nr_throttled"] = stat.get("nr_throttled")
        except Exception as exc:
            out["cpu_stat_error"] = f"{type(exc).__name__}: {exc}"
        try:
            r = subprocess.run(["ps", "-eo", "pid,etimes,pcpu,comm"], capture_output=True,
                               text=True, timeout=15)
            others = []
            for ln in (r.stdout or "").splitlines()[1:]:
                parts = ln.split()
                if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) != self.own_pid:
                    if any(t in parts[-1] for t in ("python", "mujoco", "render")):
                        others.append({"pid": int(parts[0]), "etimes_s": int(parts[1]),
                                       "pcpu": float(parts[2]), "comm": parts[-1]})
            out["other_cpu_procs"] = others[:20]
            out["other_cpu_proc_count"] = len(others)
        except Exception as exc:
            out["ps_error"] = f"{type(exc).__name__}: {exc}"
        # ── 裁定 85.0-2-①：三网读数（复用 E 的 `card_busy()`，不重造）──────────────────
        # 这一项正是 rep4/rep5 缺的证据：compute-apps 为空、但 EGL 上下文持 `/dev/nvidia*`。
        if self.calib is not None:
            try:
                snap = three_net_snapshot(self.calib, own_pid=self.own_pid,
                                          strict=self.three_net_strict, with_memory=True)
                for k in ("n_compute_apps", "n_foreign_fd_holders", "n_other_line_gpu_intent",
                          "n_other_line_script_wide", "foreign_fd_holders", "other_line_gpu_intent",
                          "other_line_script_wide", "memory_used_mib", "strict",
                          "scan_overhead_s", "own_descendant_depth_covered"):
                    out[k] = snap.get(k)
                out["three_net_busy"] = bool(snap.get("busy_per_detector"))
                self._n_three_net_ok += 1
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                out["three_net_error"] = msg
                self.three_net_errors.append(msg)
        else:
            # **缺证据不许静默判绿**：没有探测器 ⇒ 样本里必须留一个显式的"未采"标记，
            # 让下游的 `three_net_contamination()` 判 `unknown_not_collected` 而不是 false。
            out["three_net_error"] = "calib_module_not_provided"
            self.three_net_errors.append("calib_module_not_provided")
        out["collected_at_run_time"] = True
        out["attribution_strength"] = "inferred_from_pid_and_timeline"
        self.sampler_overhead_s += time.perf_counter() - t0
        return out

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.samples.append(self._one_sample())
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        self._t_start = time.perf_counter()
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.samples.append(self._one_sample())          # t=0 先采一发（臂起点）
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="a2-cotenant-sampler")
        self._thread.start()

    def stop(self) -> list[dict]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s + 5.0)
        self.samples.append(self._one_sample())          # 收尾再采一发（臂终点）
        self.stopped_at = datetime.now().astimezone().isoformat(timespec="seconds")
        return self.samples

    def evidence(self) -> dict:
        n = len(self.samples)
        foreign = [q for sm in self.samples for q in (sm.get("non_self_gpu_procs") or [])]
        las = [sm["loadavg_1m"] for sm in self.samples if isinstance(sm.get("loadavg_1m"), (int, float))]
        overheads = [sm["scan_overhead_s"] for sm in self.samples
                     if isinstance(sm.get("scan_overhead_s"), (int, float))]
        return {
            "n_periodic_samples": n,
            "sampling_interval_s": self.interval_s,
            "started_at": self.started_at, "stopped_at": self.stopped_at,
            "sampler_overhead_s": round(self.sampler_overhead_s, 3),
            "window_elapsed_s": round(self._elapsed(), 3),
            "sampler_overhead_pct_of_window": (
                round(self.sampler_overhead_s / max(1e-9, self._elapsed()) * 100, 3) if n else None),
            # ── 裁定 85.0-2-①：三网证据的窗口级汇总（**只会更严、不会更松**）──────────
            "three_net": dict(three_net_contamination(self.samples), **{
                "n_samples_with_three_net_reading": self._n_three_net_ok,
                "n_samples_missing_three_net_reading": n - self._n_three_net_ok,
                "three_net_errors": sorted(set(self.three_net_errors))[:8],
                "strict_mode": self.three_net_strict,
                "scan_overhead_s_max": max(overheads) if overheads else None,
                "scan_overhead_s_mean": (round(sum(overheads) / len(overheads), 4) if overheads else None),
                "detector_nets": list(THREE_NET_RULING["nets"]),
                "ruling": THREE_NET_RULING["ruling"],
                "blind_spot_it_closes": THREE_NET_RULING["blind_spot_it_closes"],
            }),
            "non_self_gpu_procs_observed": foreign[:20],
            "non_self_gpu_proc_seen_at_any_sample": bool(foreign),
            "loadavg_1m_min": min(las) if las else None, "loadavg_1m_max": max(las) if las else None,
            "nr_throttled_values": sorted({sm.get("nr_throttled") for sm in self.samples
                                           if sm.get("nr_throttled") is not None}),
            "attribution_strength": "inferred_from_pid_and_timeline",
            "attribution_note": ("裁定 76.1：容器内 `process_name` 为空、PID 跨命名空间不可见 "
                                 "⇒ 运行时采样保证**时刻**是真的，但把某个 PID 归到某条线仍只能是 inferred，"
                                 "**不得写 confirmed**"),
        }

    def _elapsed(self) -> float:
        return time.perf_counter() - getattr(self, "_t_start", time.perf_counter())


# ────────────────────────── 渲染器身份（五元标注里最容易缺的那一元）──────────
def classify_renderer(gl_strings: dict) -> str:
    r = (gl_strings.get("GL_RENDERER") or "").strip()
    v = (gl_strings.get("GL_VENDOR") or "").strip()
    if not r:
        return "unknown_no_gl_string"
    if "NVIDIA" in r.upper() or "NVIDIA" in v.upper():
        return "nvidia_gpu"
    if "llvmpipe" in r or "softpipe" in r or "Mesa" in v or "Mesa/X.org" in r:
        return "mesa_cpu_software"
    return "unknown_other"


def gl_identity_via_mujoco(height: int = 64, width: int = 64) -> dict:
    """独立的 `mujoco.Renderer` 取 GL 身份（方法同 `scripts/e_egl_probe.py:336`–`:370`：
    **必须在 renderer 还活着时取**，`close()` 之后 `glGetString` 返回 NULL）。"""
    out: dict = {"method": "mujoco.Renderer + OpenGL.GL.glGetString（renderer 存活期内）"}
    try:
        import mujoco
        import numpy as np
        out["mujoco_version"] = mujoco.__version__
        model = mujoco.MjModel.from_xml_string(TOY_XML)
        data = mujoco.MjData(model)
        rend = mujoco.Renderer(model, height=height, width=width)
        for _ in range(5):
            mujoco.mj_step(model, data)
        rend.update_scene(data, camera="c")
        img = np.asarray(rend.render())
        out["render_ok"] = True
        out["render_shape"] = list(img.shape)
        out["render_byte_mean"] = round(float(img.mean()), 4)
        try:
            from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
            strs = {}
            for name, const in (("GL_VENDOR", GL_VENDOR), ("GL_RENDERER", GL_RENDERER),
                                ("GL_VERSION", GL_VERSION)):
                s = glGetString(const)
                strs[name] = (s.decode() if isinstance(s, bytes) else str(s)) if s else None
            out["gl_strings"] = strs
        except Exception as exc:
            out["gl_strings"] = {}
            out["gl_strings_error"] = f"{type(exc).__name__}: {exc}"
        rend.close()
    except Exception as exc:
        out["render_ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"
        out.setdefault("gl_strings", {})
    out["renderer_class"] = classify_renderer(out.get("gl_strings", {}))
    return out


def resolve_identity(primary: dict, from_dm: dict | None) -> dict:
    """五元标注里的渲染器身份**必须非空**。两条取法：
    ① 独立 `mujoco.Renderer`（首选，与被测 env 解耦）；
    ② **被测 env 自己的** `physics.render` 之后取（更贴近实际渲染路径）。
    ①取不到就用②，但**必须登记来源**，绝不拿一条的结果冒充另一条。"""
    got_p = bool((primary.get("gl_strings") or {}).get("GL_RENDERER"))
    got_d = bool(((from_dm or {}).get("gl_strings") or {}).get("GL_RENDERER"))
    if got_p:
        src, strs, err = "mujoco.Renderer(独立探针)", primary.get("gl_strings"), None
    elif got_d:
        src, strs, err = "dm_control physics.render 之后（同进程上下文）", from_dm.get("gl_strings"), primary.get("error")
    else:
        src, strs, err = "none", {}, primary.get("error") or (from_dm or {}).get("error")
    return {"identity_source": src, "gl_strings": strs or {},
            "renderer_class": classify_renderer(strs or {}),
            "primary_probe_error": err,
            "primary_probe": primary, "dm_context_probe": from_dm,
            "both_probes_agree": (None if not (got_p and got_d)
                                  else classify_renderer(primary["gl_strings"]) == classify_renderer(from_dm["gl_strings"]))}


def gl_identity_after_dm_render(physics) -> dict:
    """在 **gym-aloha 自己的** `physics.render` 之后再取一次身份（同一进程/线程的上下文）。
    取不到就如实记 `None`，**不用上一条的结果冒充这一条**。"""
    try:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
        strs = {}
        for name, const in (("GL_VENDOR", GL_VENDOR), ("GL_RENDERER", GL_RENDERER),
                            ("GL_VERSION", GL_VERSION)):
            s = glGetString(const)
            strs[name] = (s.decode() if isinstance(s, bytes) else str(s)) if s else None
        return {"gl_strings": strs, "renderer_class": classify_renderer(strs),
                "note": "取自 dm_control physics.render 之后；NULL 表示该上下文已不 current（如实登记）"}
    except Exception as exc:
        return {"gl_strings": {}, "renderer_class": "unknown_no_gl_string",
                "error": f"{type(exc).__name__}: {exc}"}


# ────────────────────────── 边界与激活（裁定 60：只读，不写系统）──────────────
def boundary_facts() -> dict:
    present = [p for p in FORBIDDEN_SYSTEM_PATHS if os.path.exists(p)]
    hits = sorted(os.path.basename(p) for p in glob.glob("/usr/lib/x86_64-linux-gnu/lib*nvidia*")
                  if re.search(SYSTEM_RENDER_LIB_RE, p))
    icd_dir = "/usr/share/glvnd/egl_vendor.d"
    return {
        "criterion_source": "scripts/e_egl_probe.py:73 boundary_guard（A2 复写判据，不 import E 的文件）",
        "forbidden_system_paths_present": present,
        "system_render_lib_hits": hits,
        "egl_vendor_d_listing": sorted(os.listdir(icd_dir)) if os.path.isdir(icd_dir) else "(目录不存在)",
        "system_clean": (not present and not hits),
        "prefix_only_compliance": (not present and not hits),
        "egl_prefix_path": str(EGL_PREFIX),
        "egl_prefix_exists": EGL_PREFIX.is_dir(),
        "egl_prefix_vendor_json_exists": EGL_VENDOR_JSON.exists(),
        "note": "若 `system_clean=false`，则本进程的 GPU 渲染**无法归因于 prefix-only**，闸判红。",
    }


def activation_env_facts() -> dict:
    env = os.environ
    ldp = env.get("LD_LIBRARY_PATH") or ""
    vendor_file = env.get("__EGL_VENDOR_LIBRARY_FILENAMES")
    prefix_in_ldp = str(EGL_PREFIX) in ldp.split(":")
    return {
        "MUJOCO_GL": env.get("MUJOCO_GL"),
        "PYOPENGL_PLATFORM": env.get("PYOPENGL_PLATFORM"),
        "LD_LIBRARY_PATH": ldp or None,
        "__EGL_VENDOR_LIBRARY_FILENAMES": vendor_file,
        "__EGL_VENDOR_LIBRARY_DIRS": env.get("__EGL_VENDOR_LIBRARY_DIRS"),
        "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES"),
        "nvidia_prefix_active": bool(prefix_in_ldp or (vendor_file and str(EGL_PREFIX) in vendor_file)),
        "prefix_paths_verified": {
            "prefix_in_ld_library_path": prefix_in_ldp,
            "vendor_json_points_into_prefix": bool(vendor_file and str(EGL_PREFIX) in vendor_file),
            "vendor_json_exists": os.path.exists(vendor_file) if vendor_file else False,
        },
    }


def activation_consistency_gate(identity: dict, activation: dict, boundary: dict) -> dict:
    """**双向有牙**：
    - 声称 prefix 激活却是 mesa/CPU ⇒ 红（激活没生效，数字仍是 CPU 口径）；
    - 未声称 prefix 激活却拿到 NVIDIA ⇒ **回溯标注判无效**（说明系统里本来就有 NVIDIA EGL，
      G3 那轮的 CPU 口径推断不成立）⇒ 红；
    - 系统目录不干净 ⇒ 红（无法归因 prefix-only，裁定 60）。
    """
    cls = identity.get("renderer_class")
    active = bool(activation.get("nvidia_prefix_active"))
    reasons = []
    ok = True
    if cls == "unknown_no_gl_string" or cls == "unknown_other":
        ok = False
        reasons.append(f"GL 身份未取到或无法分类（renderer_class={cls}）⇒ 五元标注缺一元，判红")
    if active and cls == "mesa_cpu_software":
        ok = False
        reasons.append("声称 prefix-only 激活，但 GL_RENDERER 仍是 mesa/CPU ⇒ 激活未生效，本臂数字仍是 CPU 口径")
    if (not active) and cls == "nvidia_gpu":
        ok = False
        reasons.append("未激活 prefix 却拿到 NVIDIA EGL ⇒ 「G3 是 CPU 渲染口径」的回溯标注不成立，判无效")
    if not boundary.get("system_clean", False):
        ok = False
        reasons.append("系统目录存在 NVIDIA GL 库/ICD ⇒ 无法把 GPU 渲染归因于 prefix-only（裁定 60）")
    return {"ok": ok, "renderer_class": cls, "nvidia_prefix_active": active,
            "system_clean": boundary.get("system_clean"), "reasons": reasons}


def expect_renderer_gate(identity: dict, expect: str | None) -> dict:
    if not expect or expect == "auto":
        return {"ok": True, "expect": expect, "skipped": True}
    want = {"nvidia": "nvidia_gpu", "mesa": "mesa_cpu_software"}.get(expect, expect)
    got = identity.get("renderer_class")
    return {"ok": got == want, "expect": expect, "expected_class": want, "actual_class": got,
            "gl_strings": identity.get("gl_strings"),
            "note": "这条牙的用途：把「我以为在用 GPU」变成可失败的断言（不许静默退化成 CPU 口径）。"}


# ────────── `policy_executed` 的字段定义与一致性牙（裁定 50.1 + 裁定 83§5）──────────
POLICY_EXECUTED_DEFINITION = {
    "field": "policy_executed",
    "meaning_used_here": "reading_A_forward_pass_drove_env_step",
    "definition": ("**本产物中是否发生了「由策略权重驱动的前向推理，且其输出被用于 `env.step()`」**。"
                   "裁定 83§5 点出的两种读法里，A2 采**读法 A（「跑了推理」）**，因为它是可机器判的客观事实；"
                   "**读法 B（「以产出任务结果为目的执行策略」）不由本字段承载**，归 `capability_claim` / "
                   "`success_metrics_collected`。"),
    "two_readings_distinguished": {
        "reading_A_forward_pass_drove_env_step": {
            "carried_by": "policy_executed",
            "value_in_this_artifact_family": ("`closed_loop` 臂 = **true**（真权重前向 + 输出驱动 env.step）；"
                                              "`env_only` 臂与 `--selftest` = **false**"
                                              "（动作来自 `rng.uniform(...)`，无策略参与）"),
        },
        "reading_B_executed_to_produce_task_outcome": {
            "carried_by": "capability_claim / success_metrics_collected",
            "value_in_this_artifact_family": "**两者恒 false**（裁定 46：不采成功率 ⇒ 不构成能力主张）",
        },
    },
    "why_not_conflate": ("裁定 46 的红线是「不采成功率 ⇒ 不得声称能力」。若把 `policy_executed` 定义成读法 B，"
                         "则 `closed_loop` 臂写 true 就等于同时声称「在做任务、有结果」⇒ **放大**能力主张的误读面。"
                         "拆成两个字段后，`policy_executed=true` + `capability_claim=false` + "
                         "`success_metrics_collected=false` 是**自洽且不越界**的组合，也正是本臂的实态"
                         "（推理延迟是被测对象，裁定 59-②）。"),
    "scope_semantics": {
        "top_level": ("= 本次运行**所有模式级同名值的 OR**（等价于 `policy_executed_any_arm`）；"
                      "**不是**「整份产物都没跑策略」的意思。初值在 build 时为 `false`，"
                      "臂跑完后**必须重算**，并由 `gates.policy_executed_consistency` 看守。"),
        "per_mode": "`closed_loop.policy_executed` / `env_only.policy_executed` 各自如实、互不覆盖。",
    },
    "incident_that_made_this_necessary": {
        "artifact": "runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep1.json",
        "defect": ("顶层 `policy_executed=false` 而 `closed_loop.policy_executed=true`；"
                   "同一产物里 GPU 实测 14,990 MiB、`closed_loop.arms.*.t_infer_s` 在册 ⇒ **自相矛盾**"),
        "root_cause": "顶层字段在 build 期写死 `false`、臂跑完后从未重算（不是取值错误，是**缺一步重算**）",
        "spotted_by": "D（裁定 83§5，A2 澄清项）",
        "fix_witness": "自检变异体 M4a（喂入 rep1 同型缺陷 ⇒ 闸必须判红）+ 绿见证 M4b/M4c（裁定 83.2）",
    },
    "ruling": "裁定 50.1（字段定义必须写在产物里）+ 裁定 83§5（申报值与产物字段必须一致）",
}


# ── 裁定 84§4 的全线规则 `top_level_aggregate_must_declare_semantics`（A2 自己的产物先合规）──────
AGGREGATE_FIELD_SEMANTICS = {
    "_rule": ("裁定 84§4：**任何顶层汇总布尔/数值必须写明聚合语义（OR/AND/mean/worst/diff/count）**、"
              "**由一把闸或就地重算看守**、**不得留初值**。正例 = `policy_executed`（初值 false、"
              "臂跑完后按 OR 重算、`gates.policy_executed_consistency` 看守）；"
              "反例 = 裁定 84§3 里 D 自己撤回的「分量相加 33.13 ms > 同口径实测总量 26.28 ms」。"),
    "_sibling_rule": ("裁定 84§4 的另一条 `boolean_field_reading_must_be_declared` 由 "
                      "`policy_executed_definition` 承载（所采读法 / 未采读法归谁 / 为何不可合并）。"),
    "gates_all_ok": {"aggregate": "AND", "over": "gates[*].ok",
                     "recomputed": "所有闸算完之后就地 `all(g.get('ok') for g in gates.values())`，**不留初值**",
                     "guard": "无独立闸（它**就是**闸的汇总）；但 `gates` 里每条闸各自带 `ok` ⇒ 读者可逐条复核，汇总无法撒谎"},
    "policy_executed": {"aggregate": "OR", "over": "closed_loop.policy_executed ∪ env_only.policy_executed",
                        "guard": "gates.policy_executed_consistency（自检 M4a–M4d：1 红见证 + 2 绿见证 + 1 缺证据红）",
                        "definition_ref": "policy_executed_definition"},
    "nr_throttled_delta_total": {"aggregate": "diff",
                                 "over": "load_after.cpu_stat.nr_throttled − load_before.cpu_stat.nr_throttled",
                                 "pair_semantics_ref": "load_pair_semantics（臂起点 / 臂终点，不含 gates 汇总与写盘）",
                                 "note": "**吞吐/延迟数字必须与它成对出现**（裁定 46.4 / 75.4）"},
    "cotenant_evidence.non_a2_gpu_procs_in_window": {
        "aggregate": "OR",
        "over": "前后两点快照 gpu_compute_apps_before/after ∪ **全部周期样本** cotenant_samples[*].non_self_gpu_procs",
        "guard": "裁定 76.3：不得只用两点冒充运行时证据（rep1 正是靠周期样本才抓到窗内 t=61–137 s 的第二个进程）"},
    "cotenant_evidence.collected_at_run_time": {
        "aggregate": "count>0", "over": "periodic_sampling.n_periodic_samples",
        "note": "**真一个样本都没有时必须是 false**（裁定 76.3 之前这里是恒 true 的谎报）"},
    "cotenant_evidence.classification.contaminated": {
        "aggregate": "OR", "over": ["窗内存在非本线 GPU 进程", "loadavg_1m 漂移 ≥ +5"],
        "guard": "`classify_cotenant`（**缺证据时输出 unknown、不许输出 false**）",
        "attribution_strength": "`inferred_from_pid_and_timeline`，**不得写 confirmed**（裁定 76.1）"},
    "closed_loop.arms.*.all_episodes_within_per_step_budget": {
        "aggregate": "AND", "over": "episodes[*].within_per_step_budget（3 集/臂）",
        "note": "**不是均值达标、是每一集都达标**（裁定 84§1-1 特别点了这一点）；它是裁定 75.4 `overload_flag` 的承载字段"},
    "closed_loop.arms.*.mean_loop_fps": {
        "aggregate": "mean", "over": "episodes[*].loop_fps（3 集/臂）",
        "caveat": "裁定 82.5（渲染速率类；适用性按实测 `GL_RENDERER` 判）"},
    "closed_loop.arms.*.mean_wall_ms_per_ctrl_step / mean_budget_fraction / mean_inference_s_per_chunk / "
    "mean_amortized_inference_ms_per_ctrl_step / mean_inference_share_of_budget / mean_realtime_ratio": {
        "aggregate": "mean", "over": "episodes[*] 的同名字段（3 集/臂）",
        "note": ("均值**不得单独引用**（裁定 71-2）：必须与区间/极差并列，且带负载对与窗口判定。"
                 "`mean_realtime_ratio` = `control_timestep ÷ mean_wall_ms_per_ctrl_step`，"
                 "**同步串行环**口径（`async_overlap=false`）⇒ 按裁定 84§6 可写「同步闭环在预算内」、"
                 "**仍不得写任何异步重叠/线程并发/async 实时闭环**")},
    "closed_loop.arms.*.mean_env_step_fps": {"aggregate": "mean", "over": "episodes[*].env_step_fps",
                                             "caveat": "裁定 82.5（渲染速率类）"},
    "loadavg_before / loadavg_after": {"aggregate": "point_sample",
                                       "over": "`os.getloadavg()` 的 1/5/15 分钟三点，**臂起点与臂终点各一次**",
                                       "note": "不是均值、不是极值；窗口中途的漂移由 `periodic_sampling.loadavg_1m_min/max` 承载"},
    # ── 裁定 85.0-2-①（三网红线）新增的汇总字段，按裁定 84§4 逐个声明聚合语义 ──────────
    "per_batch_gpu_yield_gate.gate.ok": {
        "aggregate": "AND", "over": "`three_net_yield_gate.checks` 的 8 个布尔（三网各自零命中 + 三项声明齐全）",
        "guard": "gates.three_net_detector_85_0（自检 M5a–M5f：fd-_only 红 / 窄档红 / 缺证据红 / 一网退化红 / 2 绿见证）",
        "note": "**缺证据不许判绿**：`snap is None` ⇒ `ok=False, refuse=True`（与 `classify_cotenant` 同一条纪律）"},
    "cotenant_evidence.contaminated_final": {
        "aggregate": "OR（严格化）",
        "over": ["`classification.contaminated`（一网：compute-apps + loadavg 漂移 ≥5）",
                 "`classification_three_net.contaminated_three_net`（三网：compute-apps ∪ fd ∪ cmdline 窄档）"],
        "recomputed": "两条子判据都算完之后**就地重算**，初值 `None` 不得留下（裁定 84§4）",
        "guard": "gates.three_net_detector_85_0 的 `contaminated_final_is_recomputed` check",
        "monotonicity": "**只会更严、不会更松**：任一 True ⇒ True；无 True 但有 unknown ⇒ unknown；**永不由 unknown 降为 False**"},
    "cotenant_evidence.periodic_sampling.three_net.net_hit_counts": {
        "aggregate": "count（逐网分别计数，**不合并**）",
        "over": "全部周期样本 ∪ 臂起点/终点两次快照的对应网命中",
        "note": ("`cmdline_wide_registered_only` **只登记、不自动定性为污染**：一条纯 CPU 的他线脚本"
                 "不是 GPU 共租者，把宽档当污染判据会重演 RR-B2-18 的「恒真 ⇒ 狼来了」（裁定 85.6-2）。"
                 "宽档只喂 yield 闸（strict=True）。**这条切分是 A2 的口径判断，D 可推翻。**")},
    "cotenant_evidence.periodic_sampling.three_net.memory_used_mib_max": {
        "aggregate": "max", "over": "全部样本的 `memory_used_mib`（int 者）",
        "note": ("**非零读数未被解释就不许声称卡空**（裁定 85.11 `unexplained_nonzero_reading_must_block_clean_claim`）："
                 "rep5 起点那个 `102 MiB` 正是这条规则的诞生案例")},
    "cotenant_evidence.periodic_sampling.three_net.scan_overhead_s_mean / _max": {
        "aggregate": "mean / max", "over": "每样本 `card_busy()` + `nvidia-smi` 的实测耗时",
        "note": "**不预先声称一个百分比**（旧 docstring 那句「开销 <5%」是一网时代的估算，三网后已不成立）"},
}


def three_net_detector_gate(rep: dict) -> dict:
    """裁定 85.0-2-① 新红线 `card_busy_detector_must_include_fd_and_cmdline_nets` 的牙。

    这条闸守的不是"卡上有没有人"，而是"**用来判断卡上有没有人的那个探测器，是不是三网**"——
    即 rep4/rep5 被降级的那个根因。8 个 check：
      ① yield 闸声明的网 ⊇ 三网；② 被复用的 E 探测器身份三元组在册（含 sha256-12）；
      ③ 复用而非重造（`reuse_not_reimplemented=true`）；④ 每个周期样本都带三网读数**或**显式错误；
      ⑤ `contaminated_final` 已就地重算（不是初值 None）；⑥ `contaminated_final` 与两条子判据按 OR 相符；
      ⑦ 宽/窄档切分已声明（`wide_net_hits_do_not_auto_contaminate`）；⑧ 自致假阳防护已声明
      （`own_descendants_excluded`，否则采样器自己的 `nvidia-smi` 会被 fd 网当成"别人"⇒ 闸恒忙）。
    牙由自检 M5a–M5f 承载（裁定 83.1 `tooth_must_be_mutant_proven`）。
    """
    y = (rep.get("per_batch_gpu_yield_gate") or {})
    g = y.get("gate") or {}
    checks = dict(g.get("checks") or {})
    tn = rep.get("three_net") or {}
    ce = rep.get("cotenant_evidence") or {}
    ps = ce.get("periodic_sampling") or {}
    tn_ev = ps.get("three_net") or {}
    samples = ce.get("cotenant_samples") or []
    reasons: list[str] = []

    declared = y.get("detector_nets") or g.get("detector_nets_declared") or []
    out = {
        "gate_declares_three_nets": bool(set(declared) >= set(THREE_NET_RULING["nets"])),
        "detector_module_identity_recorded": bool((y.get("detector_module") or {}).get("sha256_12")),
        "detector_reused_not_reimplemented": bool((tn.get("detector_module") or {}).get("reuse_not_reimplemented")),
        "every_sample_has_three_net_or_explicit_error": bool(samples) and all(
            (sm.get("n_foreign_fd_holders") is not None) or sm.get("three_net_error") for sm in samples),
        "contaminated_final_is_recomputed": ("contaminated_final" in ce) and ce.get("contaminated_final") is not None,
        "wide_narrow_split_declared": bool(tn_ev.get("wide_net_hits_do_not_auto_contaminate")),
        "own_descendant_exclusion_declared": bool((tn.get("own_descendants_excluded") or {}).get("how")),
        "three_net_readings_present_at_batch_start": bool(
            (y.get("three_net_snapshot_at_batch_start") or {}).get("n_foreign_fd_holders") is not None),
    }
    # OR 一致性（就地重算，不看声明看数值）
    c1 = (ce.get("classification") or {}).get("contaminated")
    c2 = tn_ev.get("contaminated_three_net")
    cf = ce.get("contaminated_final")
    expect = (True if (c1 is True or c2 is True)
              else ("unknown_not_collected" if isinstance(c1, str) or isinstance(c2, str) else False))
    out["contaminated_final_matches_or_semantics"] = (cf == expect)
    for k, v in out.items():
        if not v:
            reasons.append(f"{k}=False")
    ok = all(out.values())
    return {"ok": ok, "checks": out, "reasons": reasons,
            "sub_checks_from_yield_gate": {k: v for k, v in checks.items()},
            "inputs": {"one_net_contaminated": c1, "three_net_contaminated": c2,
                       "contaminated_final": cf, "expected_by_or": expect,
                       "n_samples": len(samples),
                       "n_samples_with_three_net": tn_ev.get("n_samples_with_three_net_reading"),
                       "net_hit_counts": tn_ev.get("net_hit_counts"),
                       "memory_used_mib_max": tn_ev.get("memory_used_mib_max"),
                       "scan_overhead_s_mean": tn_ev.get("scan_overhead_s_mean")},
            "detector_module": y.get("detector_module"),
            "ruling": THREE_NET_RULING["ruling"],
            "unidirectional_by_design": False,
            "green_witness": ("自检 M5c（三网全空 ⇒ 闸判绿）与 M5f（宽档只喂 yield 闸、不自动定性污染 ⇒ 判绿）"
                              "是两个方向的绿见证（裁定 83.2 `green_witness_required`）"),
            "why": ("**这条闸守的是探测器本身，不是探测结果**：rep4/rep5 的数值带没变（0.7703–0.8009），"
                    "变的是「我们凭什么说窗是干净的」——一网半判据不足以支撑那句话（裁定 85.0-2-②）")}


def policy_executed_gate(rep: dict) -> dict:
    """裁定 83§5 的牙：顶层 `policy_executed` 必须与各模式级同名值按 **OR** 语义逐一相符。

    rep1 的真实缺陷正是这里：顶层写死 `false`、`closed_loop` 臂级 `true` ⇒ 读者按顶层判断"没跑策略"，
    而卡上 14,990 MiB、`t_infer_s` 在册。这条牙把「顶层与模式级同名不同值」变成**可失败的断言**，
    而不是靠人在文书里对齐（裁定 83.1 `tooth_must_be_mutant_proven`：自检 M4a 是它的输入级变异体）。
    """
    top = rep.get("policy_executed")
    per_mode = {}
    for key in ("closed_loop", "env_only"):
        rec = rep.get(key)
        if isinstance(rec, dict) and "policy_executed" in rec:
            per_mode[key] = bool(rec["policy_executed"])
    expected = any(per_mode.values())
    reasons = []
    if not per_mode:
        reasons.append("没有任何模式级 `policy_executed` 可核 ⇒ 顶层值无从验证（不许静默判绿）")
    if not isinstance(top, bool):
        reasons.append(f"顶层 `policy_executed` 不是 bool：{top!r}")
    elif top != expected:
        reasons.append(f"顶层 `policy_executed={top}` 与各模式 OR={expected} 不符（per_mode={per_mode}）")
    return {"ok": (not reasons), "top_level": top, "expected_by_or_semantics": expected,
            "per_mode": per_mode, "reasons": reasons,
            "definition_ref": "policy_executed_definition（裁定 50.1 / 83§5）",
            "unidirectional_by_design": False,
            "green_witness": "自检 M4b（closed_loop 全 true）/ M4c（env_only 全 false）⇒ 双向可判（裁定 83.2）",
            "why_it_matters": ("裁定 83§5：申报值与产物字段不一致 = 文书谎报。"
                               "闸装在**产物内部一致性**上，不装在「申报文书写对了没有」上——后者机器判不了。")}


# ────────────────────────── 频率 / 回合时长（裁定 53 / 58.3）──────────────────
def dt_gate(live: dict, applied: dict, dt: float) -> dict:
    reasons = []
    ok = True
    if not applied.get("applied"):
        ok = False
        reasons.append(f"shim 拒绝应用：{applied.get('why_not_applied')} / {applied.get('compute_n_steps_error')}")
    if not applied.get("both_names_patched"):
        ok = False
        reasons.append("只改了一处 DT 绑定（constants / env 必须同时改，裁定 57.4）")
    if abs(float(live.get("control_timestep_s", -1)) - dt) > 1e-12:
        ok = False
        reasons.append(f"活对象 control_timestep={live.get('control_timestep_s')} ≠ 请求 {dt}")
    if not live.get("in_qc_band_29_31"):
        ok = False
        reasons.append(f"实测 {live.get('control_hz')} Hz 不在 QC 带 [29,31]")
    if dt == 0.034 and not live.get("matches_mainline"):
        ok = False
        reasons.append("主线口径（0.034）未命中")
    return {"ok": ok, "live_timing": live, "shim_apply_record": applied, "requested_dt": dt,
            "reasons": reasons}


# ────────────────────────── tied 权重（D 点名要落进 zero-shot 侧产物）──────────
def tied_weight_live_check(policy) -> dict:
    """在**本次加载的模型对象**上重算 D 复核时差点误判的那条检查。
    键名与 `runs/vla/a2_pi05_contract_20260929/load_verification.json:tied_weight_checks` 对齐。"""
    import torch
    alias = "paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight"
    twin = "paligemma_with_expert.paligemma.lm_head.weight"
    out = {"alias_key_in_ckpt_metadata": alias, "stored_twin_key": twin,
           "recomputed_live": True, "source_of_key_names":
               "runs/vla/a2_pi05_contract_20260929/load_verification.json（safetensors __metadata__）",
           "key_prefix_rule_source": ("scripts/a2_verify_pi05_load.py:118-126 —— `policy.state_dict()` 的键带 "
                                      "**`model.` 前缀**，ckpt/`__metadata__` 的键不带 ⇒ 必须按同一规则解析"
                                      "（A2 第一版直接用裸键 ⇒ `keys_missing` 假红，见产物归档 run1）")}
    try:
        sd = dict(policy.state_dict())

        def resolve(k):
            if k in sd:
                return k
            alt = k[len("model."):] if k.startswith("model.") else "model." + k
            return alt if alt in sd else None

        ka, kt = resolve(alias), resolve(twin)
        out["alias_key_resolved_in_model"] = ka
        out["twin_key_resolved_in_model"] = kt
        a, t = (sd.get(ka) if ka else None), (sd.get(kt) if kt else None)
        out["alias_present_in_model"] = a is not None
        out["twin_present_in_model"] = t is not None
        if a is not None and t is not None:
            out["shape_alias"] = list(a.shape)
            out["shape_twin"] = list(t.shape)
            out["same_storage_data_ptr"] = bool(a.data_ptr() == t.data_ptr())
            out["bitwise_equal_in_model"] = bool(torch.equal(a.detach().cpu(), t.detach().cpu()))
            out["verdict"] = ("tie_ok" if out["same_storage_data_ptr"] and out["bitwise_equal_in_model"]
                              else "TIE_BROKEN")
        else:
            out["verdict"] = "keys_missing"
        link = REPO / "runs/vla/a2_pi05_zeroshot_20260929/weights_linkage.json"
        if link.exists():
            import hashlib as _h
            out["cross_link_to_zeroshot_side"] = {
                "path": str(link.relative_to(REPO)),
                "sha256_12": _h.sha256(link.read_bytes()).hexdigest()[:12],
                "written_at": "2026-09-29 20:1x（scripts/a2_post_g3_diagnostics.py 的 sec_weights）",
                "meaning": "D 的旧账「tied 检查抄进 zero-shot 产物」**当时已闭合**；本字段是**就地重算**的加强版，两者互为交叉引用",
            }
        else:
            out["cross_link_to_zeroshot_side"] = {"path": str(link), "exists": False}
        out["interpretation"] = ("ckpt 里 812 个张量键**没有** `embed_tokens`（tied 只存一份，别名在 `__metadata__`）"
                                 "⇒ `from_pretrained` 会把 tie 补上；**这条告警良性，不是 `0/20` 的原因**。"
                                 "（本字段的存在意义 = 让任何复核者不必再去翻另一份产物。）")
    except Exception as exc:
        out["verdict"] = "check_failed"
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ────────────────────────── 测量臂 ──────────────────────────────────────────
def run_env_only(args, shim, ev, identity_fn) -> dict:
    """不加载模型：只测 env stepping 与 A2 侧渲染（3 相机 224²）的吞吐。
    用途 = ①回溯标注臂（mesa/CPU）②主线臂（NVIDIA/GPU）；两臂**只差渲染器**，DT 相同。"""
    import numpy as np
    env, applied = shim.make_env(args.env_id, dt=args.dt,
                                 obs_type="pixels_agent_pos", render_mode="rgb_array")
    live = shim.read_live_timing(env)
    cam_map = {"observation.images.base_0_rgb": args.base_camera,
               "observation.images.left_wrist_0_rgb": "left_wrist",
               "observation.images.right_wrist_0_rgb": "right_wrist"}
    load0 = ev.load_snapshot()
    # 渲染-only 计时（A2 侧那 3 路 224²）
    obs, info = env.reset(seed=args.seed0)
    r_times = []
    for _ in range(args.render_reps):
        _, _, dt_r = ev.render_obs(env, args, cam_map)
        r_times.append(dt_r)
    # stepping 计时（含 gym-aloha 内部 3 路 480×640 渲染，因为 obs_type=pixels_agent_pos）
    rng = np.random.default_rng(args.seed0 + 777)
    t0 = time.perf_counter()
    n_steps_done = 0
    for _ in range(args.steps):
        a = rng.uniform(env.action_space.low, env.action_space.high).astype("float32")
        obs, reward, terminated, truncated, info = env.step(a)
        n_steps_done += 1
        if terminated or truncated:
            env.reset(seed=args.seed0)
    wall = time.perf_counter() - t0
    load1 = ev.load_snapshot()
    physics = env.unwrapped._env.physics
    ident2 = identity_fn(physics)
    hz = live.get("control_hz")
    rec = {
        "mode": "env_only",
        "policy_executed": False,
        "capability_claim": False,
        "n_steps": n_steps_done,
        "stepping_wall_s": round(wall, 3),
        "env_step_fps": round(n_steps_done / wall, 3) if wall > 0 else None,
        "render_only_3cam_224_fps": round(len(r_times) / sum(r_times), 3) if r_times and sum(r_times) > 0 else None,
        "render_only_3cam_224_s_mean": round(statistics.fmean(r_times), 5) if r_times else None,
        "render_only_3cam_224_s_max": round(max(r_times), 5) if r_times else None,
        "control_hz": hz,
        "realtime_ratio_of_stepping": (round((n_steps_done / hz) / wall, 4) if (wall > 0 and hz) else None),
        "load_before": load0, "load_after": load1,
        "nr_throttled_delta": (load1.get("cpu_stat", {}).get("nr_throttled", 0)
                                - load0.get("cpu_stat", {}).get("nr_throttled", 0)),
        "gl_identity_after_dm_render": ident2,
        "episode_horizon": shim.episode_horizon(dt=args.dt),
    }
    env.close()
    return rec, live, applied


def run_closed_loop(args, shim, ev, identity_fn) -> dict:
    """主线闭环延迟：π₀.₅ fp32 + shim DT + 动作队列。**不采集成功率**（裁定 46）。"""
    import numpy as np
    import torch

    env, applied = shim.make_env(args.env_id, dt=args.dt,
                                 obs_type="pixels_agent_pos", render_mode="rgb_array")
    live = shim.read_live_timing(env)
    cam_map = {"observation.images.base_0_rgb": args.base_camera,
               "observation.images.left_wrist_0_rgb": "left_wrist",
               "observation.images.right_wrist_0_rgb": "right_wrist"}
    policy, preprocess, postprocess, cfg, model_info = ev.build_policy(args)
    tied = tied_weight_live_check(policy)
    physics0 = env.unwrapped._env.physics
    lo = np.asarray(physics0.model.actuator_ctrlrange[:, 0], dtype="float64")
    hi = np.asarray(physics0.model.actuator_ctrlrange[:, 1], dtype="float64")
    clip_stats = {"n_values": 0, "n_clipped": 0, "max_clip_magnitude": 0.0, "raw_absmax": 0.0}
    ident2 = identity_fn(env.unwrapped._env.physics)

    n_act_list = [int(x) for x in str(args.n_action_steps).split(",") if x.strip()]
    chunk = int(cfg.chunk_size)
    bad = [n for n in n_act_list if n > chunk]
    if bad:
        raise SystemExit(f"--n-action-steps {bad} > chunk_size {chunk}（不可能，停下报错）")

    out_arms = {}
    for n_act in n_act_list:
        episodes = []
        load_arm0 = ev.load_snapshot()
        t_arm0 = time.perf_counter()
        for ep in range(args.n_episodes):
            seed = args.seed0 + ep
            ep_load0 = ev.load_snapshot()
            queue: list = []
            n_infer = 0
            t_infer = 0.0
            t_render = 0.0
            t_env = 0.0
            chunk_times = []
            steps = 0
            terminal_reason = "limit"
            t_ep0 = time.perf_counter()
            obs, info = env.reset(seed=seed)
            for step in range(args.max_steps):
                if not queue:
                    imgs, state, dt_r = ev.render_obs(env, args, cam_map)
                    t_render += dt_r
                    batch = {k: torch.from_numpy(v) for k, v in imgs.items()}
                    batch["observation.state"] = torch.from_numpy(state)
                    batch["task"] = args.task
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    t0 = time.perf_counter()
                    b = preprocess(batch)
                    with torch.inference_mode():
                        c = policy.predict_action_chunk(b)
                    c = postprocess(c)
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    dt_i = time.perf_counter() - t0
                    t_infer += dt_i
                    n_infer += 1
                    chunk_times.append(dt_i)
                    arr = c.detach().to("cpu").numpy()
                    if arr.ndim == 3:
                        arr = arr[0]
                    if arr.shape[0] != chunk:
                        raise RuntimeError(f"chunk 长度 {arr.shape[0]} != cfg.chunk_size {chunk}")
                    queue = list(arr[:n_act])   # 队列截断 = S4 草案 §2.4 的运行时语义
                a32 = queue.pop(0)
                action = ev.adapt_action(a32, lo, hi, clip_stats)
                t0 = time.perf_counter()
                obs, reward, terminated, truncated, info = env.step(action)
                t_env += time.perf_counter() - t0
                steps += 1
                if terminated or truncated:
                    terminal_reason = "terminated" if terminated else "truncated"
                    break
            wall = time.perf_counter() - t_ep0
            ep_load1 = ev.load_snapshot()
            hz = live.get("control_hz")
            horizon_s = shim.episode_horizon(dt=args.dt)
            rec = {
                "episode": ep, "seed": seed, "steps": steps,
                "terminal_reason": terminal_reason,
                "terminal_reason_units_note": "步数只作过程量；**时长一律按秒**登记（裁定 58.3）",
                "episode_wall_s": round(wall, 3),
                "episode_sim_seconds_covered": round(steps * args.dt, 4),
                "episode_horizon_s": horizon_s["simulated_seconds_at_shim_hz"],
                "n_inference_calls": n_infer,
                "t_infer_s": round(t_infer, 3),
                "t_render_s": round(t_render, 3),
                "t_env_step_s": round(t_env, 3),
                "t_other_s": round(max(0.0, wall - t_infer - t_render - t_env), 3),
                "loop_fps": round(steps / wall, 3) if wall > 0 else None,
                "env_step_fps": round(steps / t_env, 3) if t_env > 0 else None,
                "inference_s_per_chunk_mean": round(statistics.fmean(chunk_times), 4) if chunk_times else None,
                "inference_s_per_chunk_p50": round(statistics.median(chunk_times), 4) if chunk_times else None,
                "inference_s_per_chunk_max": round(max(chunk_times), 4) if chunk_times else None,
                "inference_s_per_chunk_first": round(chunk_times[0], 4) if chunk_times else None,
                "wall_ms_per_ctrl_step": round(wall / steps * 1000.0, 3) if steps else None,
                "per_step_budget_ms": shim.PER_STEP_BUDGET_MS,
                "budget_fraction": round((wall / steps * 1000.0) / shim.PER_STEP_BUDGET_MS, 4) if steps else None,
                "within_per_step_budget": bool(steps and (wall / steps * 1000.0) <= shim.PER_STEP_BUDGET_MS),
                "amortized_inference_ms_per_ctrl_step": round(t_infer / steps * 1000.0, 3) if steps else None,
                "inference_share_of_budget": round((t_infer / steps * 1000.0) / shim.PER_STEP_BUDGET_MS, 4) if steps else None,
                "chunk_coverage_s": round(n_act * args.dt, 4),
                "chunk_coverage_share_of_horizon": round(n_act * args.dt / horizon_s["simulated_seconds_at_shim_hz"], 4),
                "realtime_ratio": round((steps * args.dt) / wall, 4) if wall > 0 else None,
                "control_hz": hz,
                "gpu": ev.gpu_stats(),
                "load_before": ep_load0, "load_after": ep_load1,
                "nr_throttled_delta": (ep_load1.get("cpu_stat", {}).get("nr_throttled", 0)
                                       - ep_load0.get("cpu_stat", {}).get("nr_throttled", 0)),
            }
            episodes.append(rec)
            print(f"[ep {ep}] steps={steps} wall={wall:.2f}s loop_fps={rec['loop_fps']} "
                  f"infer/chunk={rec['inference_s_per_chunk_mean']}s "
                  f"wall_ms/step={rec['wall_ms_per_ctrl_step']} "
                  f"budget_frac={rec['budget_fraction']}", flush=True)
        arm_wall = time.perf_counter() - t_arm0
        load_arm1 = ev.load_snapshot()
        n_eps = max(1, len(episodes))
        out_arms[f"n_action_steps_{n_act}"] = {
            "n_action_steps": n_act,
            "chunk_size": chunk,
            "queue_truncated_from_chunk": chunk != n_act,
            "v4_H_ge_2n_satisfied": bool(chunk >= 2 * n_act),
            "v4_H_ge_2n_source": "RL_Harness_v4_20260924 附录一 :103（异步调度定义 H≥2n；见 S4 草案 §2.4）",
            "n_episodes": len(episodes),
            "episodes": episodes,
            "arm_wall_s": round(arm_wall, 2),
            "mean_loop_fps": round(statistics.fmean([e["loop_fps"] for e in episodes]), 3),
            "mean_env_step_fps": round(statistics.fmean([e["env_step_fps"] for e in episodes]), 3),
            "mean_wall_ms_per_ctrl_step": round(statistics.fmean([e["wall_ms_per_ctrl_step"] for e in episodes]), 3),
            "mean_budget_fraction": round(statistics.fmean([e["budget_fraction"] for e in episodes]), 4),
            "mean_inference_s_per_chunk": round(statistics.fmean([e["inference_s_per_chunk_mean"] for e in episodes]), 4),
            "mean_amortized_inference_ms_per_ctrl_step": round(
                statistics.fmean([e["amortized_inference_ms_per_ctrl_step"] for e in episodes]), 3),
            "mean_inference_share_of_budget": round(
                statistics.fmean([e["inference_share_of_budget"] for e in episodes]), 4),
            "mean_realtime_ratio": round(statistics.fmean([e["realtime_ratio"] for e in episodes]), 4),
            "all_episodes_within_per_step_budget": all(e["within_per_step_budget"] for e in episodes),
            "load_before": load_arm0, "load_after": load_arm1,
            "nr_throttled_delta": (load_arm1.get("cpu_stat", {}).get("nr_throttled", 0)
                                   - load_arm0.get("cpu_stat", {}).get("nr_throttled", 0)),
        }
    env.close()
    return {"arms": out_arms, "model": model_info, "tied_weight_check": tied,
            "clip_stats": clip_stats, "gl_identity_after_dm_render": ident2,
            "live_timing": live, "shim_apply_record": applied,
            "policy_executed": True,
            "policy_executed_justification": "**推理延迟本身是被测对象**（裁定 59-②）；本产物不采集成功率，故不构成能力主张（裁定 46）",
            "capability_claim": False,
            "success_metrics_collected": False}


# ────────────────────────── 自检（4 个变异体，都要被抓到）─────────────────────
def selftest(args) -> int:
    shim = _load_shim()
    cases = []

    # 被复用的 E 探测器的**真实**身份（自检里 M5 族喂的是合成读数，但"复用的是哪一版"必须是真的）。
    # 取不到就如实写 None ⇒ `three_net_detector.detector_module` 缺 sha，读者立刻知道自检没核到真件。
    try:
        _e_path = REPO / "scripts" / "e_mainline_render_calib.py"
        _selftest_detector_identity = module_identity(_e_path, "只读 sha/行数，未 import（自检不需要真探测器）")
        _selftest_detector_identity["has_card_busy"] = "def card_busy(" in _e_path.read_text(errors="ignore")
    except OSError as exc:
        _selftest_detector_identity = {"error": f"{type(exc).__name__}: {exc}", "sha256_12": None}

    def case(name, ok, detail):
        cases.append({"case": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print("[selftest] 变异体 M1：把 DT 设成 0.02（50 Hz）⇒ dt_gate 必须判红", flush=True)
    import gym_aloha  # noqa: F401
    applied_bad = shim.apply_dt(0.02)
    import gymnasium as gym
    env_bad = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    live_bad = shim.read_live_timing(env_bad)
    g_bad = dt_gate(live_bad, applied_bad, 0.034)
    env_bad.close()
    case("M1_dt_0.02_must_fail_gate", g_bad["ok"] is False,
         f"live control_hz={live_bad.get('control_hz')}，gate.ok={g_bad['ok']}，reasons={g_bad['reasons'][:2]}")

    print("[selftest] 变异体 M2：只改 constants.DT（半 patch）⇒ 活对象必须仍是 50 Hz", flush=True)
    import gym_aloha.constants as C
    import gym_aloha.env as E
    C.DT = 0.034
    env_half = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    live_half = shim.read_live_timing(env_half)
    env_half.close()
    case("M2_half_patch_silently_stays_50hz",
         abs(float(live_half.get("control_timestep_s", 0)) - 0.02) < 1e-12,
         f"只改 constants.DT ⇒ 活对象 control_timestep={live_half.get('control_timestep_s')}"
         f"（env.DT={getattr(E,'DT',None)}）—— 与 shim 的 patch_mechanism_proof 同结论")
    C.DT = 0.02

    print("[selftest] 变异体 M3：伪造 GL 身份 ⇒ activation_consistency_gate 必须双向判红", flush=True)
    bnd = boundary_facts()
    fake_nvidia = {"renderer_class": "nvidia_gpu", "gl_strings": {"GL_RENDERER": "NVIDIA A800-SXM4-80GB/PCIe/SSE2"}}
    fake_mesa = {"renderer_class": "mesa_cpu_software", "gl_strings": {"GL_RENDERER": "llvmpipe (LLVM 15.0.7, 256 bits)"}}
    act_off = {"nvidia_prefix_active": False}
    act_on = {"nvidia_prefix_active": True}
    g_a = activation_consistency_gate(fake_nvidia, act_off, bnd)
    g_b = activation_consistency_gate(fake_mesa, act_on, bnd)
    g_c = activation_consistency_gate({"renderer_class": "unknown_no_gl_string", "gl_strings": {}}, act_on, bnd)
    case("M3a_claim_gpu_without_prefix_must_fail", g_a["ok"] is False, g_a["reasons"][:1])
    case("M3b_claim_prefix_but_cpu_renderer_must_fail", g_b["ok"] is False, g_b["reasons"][:1])
    case("M3c_missing_gl_string_must_fail", g_c["ok"] is False, g_c["reasons"][:1])

    print("[selftest] 变异体 M4：伪造顶层 policy_executed（rep1 的同型缺陷）⇒ 一致性闸必须判红", flush=True)
    # 输入级变异体（裁定 83.1 `tooth_must_be_mutant_proven`）：把 rep1 的缺陷形态直接喂给闸，
    # 不靠 `red_when` 文案充当牙。
    g_m4a = policy_executed_gate({"policy_executed": False, "closed_loop": {"policy_executed": True}})
    case("M4a_toplevel_false_while_arm_true_must_fail", g_m4a["ok"] is False, g_m4a["reasons"][:1])
    # 绿见证（裁定 83.2 `green_witness_required`）：两个方向都要能判绿，否则这条牙是单向装饰品。
    g_m4b = policy_executed_gate({"policy_executed": True, "closed_loop": {"policy_executed": True}})
    case("M4b_toplevel_true_with_arm_true_must_pass", g_m4b["ok"] is True, f"per_mode={g_m4b['per_mode']}")
    g_m4c = policy_executed_gate({"policy_executed": False, "env_only": {"policy_executed": False}})
    case("M4c_env_only_all_false_must_pass", g_m4c["ok"] is True, f"per_mode={g_m4c['per_mode']}")
    # 缺证据时不许静默判绿（与 `classify_cotenant` 同一条纪律）
    g_m4d = policy_executed_gate({"policy_executed": False})
    case("M4d_no_mode_level_evidence_must_fail", g_m4d["ok"] is False, g_m4d["reasons"][:1])

    # ── 变异体 M5 族：裁定 85.0-2-① 三网红线的牙（`tooth_must_be_mutant_proven`，裁定 83.1）──────
    # 全部是**输入级/产物级**变异体，不是 `red_when` 文案。M5a 就是 rep4/rep5 的真实缺陷形态：
    # compute-apps **空**、但 fd 网看到有人持 `/dev/nvidia*`（EGL 图形上下文）。
    print("[selftest] 变异体 M5：三网探测器（裁定 85.0-2-①）—— fd 网/窄档/缺证据/一网退化 都必须判红", flush=True)
    _calib_id = {"path": "scripts/e_mainline_render_calib.py", "sha256_12": "deadbeefcafe",
                 "n_lines_wc_l": 1, "bytes": 1, "loaded_from": "selftest_synthetic",
                 "reuse_not_reimplemented": True}

    def _snap(**kw):
        base = {"strict": True, "n_compute_apps": 0, "compute_apps": [],
                "n_foreign_fd_holders": 0, "foreign_fd_holders": [],
                "n_other_line_gpu_intent": 0, "other_line_gpu_intent": [],
                "n_other_line_script_wide": 0, "other_line_script_wide": [],
                "memory_used_mib": 0, "scan_overhead_s": 0.05, "busy_per_detector": False}
        base.update(kw)
        return base

    # M5a：**fd-_only** 命中（rep4/rep5 的盲区本体）⇒ 必须拒绝开跑
    g_m5a = three_net_yield_gate(_snap(n_foreign_fd_holders=1,
                                       foreign_fd_holders=[{"pid": 235015,
                                                            "nvidia_devs": ["/dev/nvidia2", "/dev/nvidiactl"],
                                                            "cmdline": "python scripts/b2_s1_generate_dataset.py"}],
                                       memory_used_mib=102), detector_module=_calib_id)
    case("M5a_fd_only_hit_must_refuse", g_m5a["ok"] is False and g_m5a["refuse"] is True,
         f"compute-apps=0 而 fd 网=1（102 MiB）⇒ ok={g_m5a['ok']} reasons={g_m5a['reasons'][:2]}")
    # M5b：cmdline **窄档**命中（他线正要上卡、还没分配显存）⇒ 必须拒绝
    g_m5b = three_net_yield_gate(_snap(n_other_line_gpu_intent=1,
                                       other_line_gpu_intent=[{"pid": 999, "gpu_intent": ["gpu_intent:torchrun"]}]),
                                 detector_module=_calib_id)
    case("M5b_narrow_cmdline_intent_must_refuse", g_m5b["ok"] is False, g_m5b["reasons"][:1])
    # M5c：**绿见证**（裁定 83.2）——三网全空 + `memory.used=0` ⇒ 必须判绿（否则闸恒忙 = 狼来了）
    g_m5c = three_net_yield_gate(_snap(), detector_module=_calib_id)
    case("M5c_all_three_nets_empty_must_pass", g_m5c["ok"] is True and g_m5c["refuse"] is False,
         f"checks={ {k: v for k, v in g_m5c['checks'].items() if not v} or 'all_true'}")
    # M5d：缺证据（`snap=None`）⇒ **不许**判绿
    g_m5d = three_net_yield_gate(None, detector_module=_calib_id)
    case("M5d_no_evidence_must_refuse", g_m5d["ok"] is False and g_m5d["refuse"] is True, g_m5d["reasons"][:1])
    # M5e：**探测器退化成一网**（正是 rep4/rep5 的口径）⇒ 即使读数全空也必须判红
    g_m5e = three_net_yield_gate(_snap(), declared_nets=["compute_apps"], detector_module=_calib_id)
    case("M5e_one_net_detector_must_fail_even_if_clean", g_m5e["ok"] is False,
         f"reasons={g_m5e['reasons'][:1]}（读数全空也红 ⇒ 红的是**探测器**，不是探测结果）")
    # M5f：未记录被复用探测器的身份三元组 ⇒ 判红（"复用的是哪一版"必须可核）
    g_m5f = three_net_yield_gate(_snap(), detector_module=None)
    case("M5f_missing_detector_identity_must_fail", g_m5f["ok"] is False, g_m5f["reasons"][:1])
    # M5g：`memory.used` 非零且未解释 ⇒ 判红（裁定 85.11 `unexplained_nonzero_reading_must_block_clean_claim`；
    #      rep5 起点那个 102 MiB 就是这条规则的诞生案例）
    g_m5g = three_net_yield_gate(_snap(memory_used_mib=102), detector_module=_calib_id)
    case("M5g_unexplained_nonzero_memory_must_refuse", g_m5g["ok"] is False, g_m5g["reasons"][:1])
    # M5h：污染判据——**fd-_only** 证据必须把 `contaminated_three_net` 翻成 True（一网判据会漏）
    c_m5h = three_net_contamination([_snap(n_foreign_fd_holders=1,
                                           foreign_fd_holders=[{"pid": 235015, "nvidia_devs": ["/dev/nvidia2"]}])])
    c_m5h_one_net = {"contaminated": False}      # 一网视角：compute-apps 空 ⇒ 会说"干净"
    case("M5h_fd_only_must_contaminate", c_m5h["contaminated_three_net"] is True
         and c_m5h["net_hit_counts"]["compute_apps"] == 0,
         f"三网={c_m5h['contaminated_three_net']}（一网会说 {c_m5h_one_net['contaminated']}）"
         f" counts={c_m5h['net_hit_counts']}")
    # M5i：污染判据——**缺证据不许输出 false**
    c_m5i = three_net_contamination([])
    case("M5i_no_sample_must_be_unknown_not_false",
         c_m5i["contaminated_three_net"] == "unknown_not_collected", c_m5i["reason"][:1])
    # M5j：**绿见证 2**——宽档（纯 CPU 的他线脚本）只喂 yield 闸、**不**自动定性为污染
    c_m5j = three_net_contamination([_snap(n_other_line_script_wide=1,
                                           other_line_script_wide=[{"pid": 7, "other_line_script": ["other_line_script"],
                                                                     "cmdline": "python scripts/c2_gate_norm_contract.py"}])])
    g_m5j_yield = three_net_yield_gate(_snap(n_other_line_script_wide=1), detector_module=_calib_id)
    case("M5j_wide_net_refuses_but_does_not_auto_contaminate",
         c_m5j["contaminated_three_net"] is False and g_m5j_yield["ok"] is False,
         f"污染判据={c_m5j['contaminated_three_net']}（登记 wide={c_m5j['net_hit_counts']['cmdline_wide_registered_only']}）"
         f"、yield 闸 refuse={g_m5j_yield['refuse']} ⇒ 两条口径的切分如声明")
    # M5k：**产物级**变异体——把一份"rep4/rep5 同型"的旧产物（只有半网证据）喂给 `three_net_detector_gate`
    _old_shaped_rep = {
        "per_batch_gpu_yield_gate": {"checked_before_this_batch": True, "detector_nets": ["compute_apps"],
                                     "non_self_gpu_procs_at_batch_start": [], "refused_if_nonempty": True},
        "cotenant_evidence": {"collected_at_run_time": True,
                              "cotenant_samples": [{"ts": "x", "gpu_compute_procs": [], "non_self_gpu_procs": []}],
                              "periodic_sampling": {"n_periodic_samples": 1},
                              "classification": {"contaminated": False}},
    }
    g_m5k = three_net_detector_gate(_old_shaped_rep)
    case("M5k_old_half_net_artifact_must_fail_detector_gate", g_m5k["ok"] is False,
         f"red checks={sorted(k for k, v in g_m5k['checks'].items() if not v)}")
    # M5l：**绿见证 3**——三网齐全的新产物形状 ⇒ 判绿（证明 M5k 的红不是恒真）
    _new_shaped_rep = {
        "per_batch_gpu_yield_gate": {"detector_nets": list(THREE_NET_RULING["nets"]), "detector_module": _calib_id,
                                     "three_net_snapshot_at_batch_start": _snap(),
                                     "gate": three_net_yield_gate(_snap(), detector_module=_calib_id)},
        "three_net": {"detector_module": _calib_id,
                      "own_descendants_excluded": {"how": "drop_own_descendants()", "depth_covered": 1}},
        "cotenant_evidence": {
            "cotenant_samples": [dict(_snap(), non_self_gpu_procs=[], ts="x")],
            "periodic_sampling": {"three_net": three_net_contamination([_snap()])},
            "classification": {"contaminated": False}, "contaminated_final": False},
    }
    g_m5l = three_net_detector_gate(_new_shaped_rep)
    case("M5l_three_net_artifact_must_pass_detector_gate", g_m5l["ok"] is True,
         f"red checks={sorted(k for k, v in g_m5l['checks'].items() if not v) or 'none'}")
    # M5m：`contaminated_final` 留初值 None（裁定 84§4「不得留初值」）⇒ 判红
    _m5m = json.loads(json.dumps(_new_shaped_rep))
    _m5m["cotenant_evidence"]["contaminated_final"] = None
    g_m5m = three_net_detector_gate(_m5m)
    case("M5m_stale_initial_value_must_fail", g_m5m["ok"] is False
         and not g_m5m["checks"]["contaminated_final_is_recomputed"], g_m5m["reasons"][:1])
    # M5n：`contaminated_final` 与两条子判据的 OR 不符（偷偷放松）⇒ 判红
    _m5n = json.loads(json.dumps(_new_shaped_rep))
    _m5n["cotenant_evidence"]["periodic_sampling"]["three_net"] = three_net_contamination(
        [_snap(n_foreign_fd_holders=1, foreign_fd_holders=[{"pid": 1}])])
    g_m5n = three_net_detector_gate(_m5n)      # 三网=True 而 final 仍写 False
    case("M5n_or_semantics_violation_must_fail", g_m5n["ok"] is False
         and not g_m5n["checks"]["contaminated_final_matches_or_semantics"],
         f"三网={g_m5n['inputs']['three_net_contaminated']} final={g_m5n['inputs']['contaminated_final']}"
         f" expected={g_m5n['inputs']['expected_by_or']}")

    print("[selftest] 分类器不许把 unknown 静默当成 nvidia", flush=True)
    cls_cases = {
        "NVIDIA Corporation | NVIDIA A800-SXM4-80GB/PCIe/SSE2 | 4.6.0 NVIDIA 590.48.01": "nvidia_gpu",
        "llvmpipe (LLVM 15.0.7, 256 bits)": "mesa_cpu_software",
        "": "unknown_no_gl_string",
        "some future renderer": "unknown_other",
    }
    for s, want in cls_cases.items():
        got = classify_renderer({"GL_RENDERER": s, "GL_VENDOR": ""})
        case(f"classify[{s[:28] or '(empty)'}]", got == want, f"got={got} want={want}")

    n_ok = sum(1 for c in cases if c["ok"])
    payload = {"probe": "a2_egl_latency_selftest",
               "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "generator": "scripts/a2_egl_latency_remeasure.py --selftest",
               "generator_sha256_12": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()[:12],
               "n_cases": len(cases), "n_ok": n_ok, "all_ok": n_ok == len(cases),
               "gpu_used": False, "policy_executed": False,
               "capability_claim": False, "success_metrics_collected": False,
               "success_rate_column": "not_an_exit_criterion（裁定 65-6③）",
               "policy_executed_definition": POLICY_EXECUTED_DEFINITION, "cases": cases,
               "aggregate_field_semantics": AGGREGATE_FIELD_SEMANTICS,
               # ── 裁定 85.0-2-①：自检产物也要能核「复用的是 E 的哪一版探测器」──────────
               "three_net_detector": {
                   "ruling": THREE_NET_RULING,
                   "detector_module": _selftest_detector_identity,
                   "m5_family": {
                       "n_mutants": sum(1 for c in cases if c["case"].startswith("M5")),
                       "red_witnesses": ["M5a_fd_only_hit_must_refuse（**rep4/rep5 盲区本体**：compute-apps 空 + fd 网命中）",
                                          "M5b_narrow_cmdline_intent_must_refuse",
                                          "M5d_no_evidence_must_refuse",
                                          "M5e_one_net_detector_must_fail_even_if_clean（**读数全空也红 ⇒ 红的是探测器**）",
                                          "M5f_missing_detector_identity_must_fail",
                                          "M5g_unexplained_nonzero_memory_must_refuse（裁定 85.11）",
                                          "M5h_fd_only_must_contaminate", "M5i_no_sample_must_be_unknown_not_false",
                                          "M5k_old_half_net_artifact_must_fail_detector_gate（**产物级**：rep4/rep5 同型旧产物）",
                                          "M5m_stale_initial_value_must_fail（裁定 84§4 不得留初值）",
                                          "M5n_or_semantics_violation_must_fail"],
                       "green_witnesses": ["M5c_all_three_nets_empty_must_pass（否则闸恒忙 = 狼来了，裁定 85.6-2 同族）",
                                            "M5j_wide_net_refuses_but_does_not_auto_contaminate",
                                            "M5l_three_net_artifact_must_pass_detector_gate"],
                       "note": ("自检**不需要 GPU**（M5 族全部喂合成读数）⇒ `gpu_used=false`；"
                                "真卡上的活见证见 `yield_gate_three_net_live_witness.json`"),
                   },
               },
               "boundary_facts": bnd}
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "selftest.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"[written] {p}  ({n_ok}/{len(cases)})", flush=True)
    return 0 if n_ok == len(cases) else 1


# ────────────────────────── main ────────────────────────────────────────────
def nvidia_smi() -> dict:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
        line = (r.stdout or "").strip().splitlines()
        if not line:
            return {"error": (r.stderr or "empty").strip()[:200]}
        mem, util = [x.strip() for x in line[0].split(",")[:2]]
        return {"memory_used_mib": int(mem), "utilization_gpu_pct": int(util)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=["env_only", "closed_loop"], default="env_only")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--env-id", default="gym_aloha/AlohaTransferCube-v0")
    ap.add_argument("--dt", type=float, default=0.034)
    ap.add_argument("--steps", type=int, default=100, help="env_only 臂的 stepping 步数")
    ap.add_argument("--render-reps", type=int, default=20, help="env_only 臂的 3 相机 224² 渲染重复次数")
    ap.add_argument("--n-episodes", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=300, help="裁定 58.3：保持 300，不缩放")
    ap.add_argument("--n-action-steps", default="50,25", help="逗号分隔；50=出厂，25=满足 v4 H≥2n")
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--base-camera", default="angle")
    ap.add_argument("--task", default="Transfer the red cube from the right arm to the left arm.")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--weights-dir")
    ap.add_argument("--tokenizer-dir")
    ap.add_argument("--expect-renderer", choices=["nvidia", "mesa", "auto"], default="auto")
    ap.add_argument("--out-dir", default="runs/vla/a2_egl_latency_20260929")
    ap.add_argument("--cotenant-interval-s", type=float, default=2.0,
                    help="运行时 cotenant 周期采样间隔（裁定 76.3）")
    ap.add_argument("--quiet-window", default=None,
                    help="若本臂在申报过的静默窗口内跑，填 daily_report 的申报行号/时刻（裁定 73/76.4）")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args)
    if args.mode == "closed_loop" and not (args.weights_dir and args.tokenizer_dir):
        print("--mode closed_loop 需要 --weights-dir 与 --tokenizer-dir", file=sys.stderr)
        return 2

    shim = _load_shim()
    ev = _load_eval_module()

    am = _load_amendments_module()
    # ── 裁定 76.2 红线 `per_batch_gpu_yield_gate` **升级三网**（裁定 85.0-2-① 新红线
    #    `card_busy_detector_must_include_fd_and_cmdline_nets`）─────────────────────────
    # 旧口径 = `--query-compute-apps` + `ps`（一网半）。它对 EGL 图形上下文与「已起跑但尚未
    # 分配显存」的进程是盲的 ⇒ rep4/rep5 的清洁认证被降级为 `undetermined_detector_blind_to_egl`。
    # 修法**不是**A2 自己再写一套探测器，而是复用 E 已验过牙的 `card_busy()`（裁定 85.0-2-①
    # 明写「复用 E 的实现口径，不重造」），并把被复用件的身份三元组钉进产物。
    calib = _load_e_calib_module()
    calib_id = module_identity(REPO / "scripts" / "e_mainline_render_calib.py",
                               "importlib.util.spec_from_file_location（A2 不复制 E 的代码）")
    yield_snap = three_net_snapshot(calib, strict=True, with_memory=True)
    yield_gate = three_net_yield_gate(yield_snap, detector_module=calib_id)
    procs_before = am.gpu_procs()          # 保留：既有产物字段与 `classify_cotenant` 的输入形状不变
    foreign_before = [q for q in procs_before if q.get("pid") != os.getpid()]
    if yield_gate["refuse"]:
        print("[yield-gate] **三网判「卡忙」⇒ 拒绝开跑**（裁定 76.2 + 85.0-2-①）", flush=True)
        for r in yield_gate["reasons"]:
            print(f"  - {r}", flush=True)
        print(json.dumps({"per_batch_gpu_yield_gate": yield_gate,
                          "three_net_snapshot_at_batch_start": yield_snap,
                          "detector_module": calib_id,
                          "refused": True, "exit_code": 4,
                          "note": ("拒绝也是证据：本 JSON 就是「三网闸在真实场景下会红」的见证。"
                                   "**没有产生任何延迟数字**（臂未起跑）⇒ 不得被引用为测量结果")},
                         ensure_ascii=False, indent=1, default=str), flush=True)
        return 4
    # 裁定 76.3 红线 `cotenant_evidence_must_be_runtime`：运行中**周期**采样，不再只采前后两个时刻
    sampler = RuntimeCotenantSampler(am, interval_s=args.cotenant_interval_s,
                                     calib=calib, three_net_strict=True)
    sampler.start()
    ident_primary = gl_identity_via_mujoco()
    act = activation_env_facts()
    bnd = boundary_facts()
    rep = {
        "probe": "a2_egl_latency_remeasure",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_egl_latency_remeasure.py",
        "generator_sha256_12": __import__("hashlib").sha256(pathlib.Path(__file__).read_bytes()).hexdigest()[:12],
        "args": vars(args),
        "mode": args.mode,
        "tag": args.tag,
        "purpose": ("裁定 59-②：egl(GPU, prefix-only) 下重测 π₀.₅ 闭环延迟；"
                    "并用 `--mode env_only`（不带 prefix）把 G3 旧数字的渲染器口径**实测回溯标注**"),
        "morphology": "aloha_bimanual_14d",
        "env_id": args.env_id,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "venv": sys.executable,
        "versions": {},
        "backend_tuple_five": {
            "venv": sys.executable,
            "mujoco_gl_env": act["MUJOCO_GL"],
            "gl_renderer": None,
            "gl_vendor": None,
            "gl_version": None,
            "renderer_class": None,
            "identity_source": None,
            "_gl_fields_filled_after_measurement": True,
            "mujoco_version": ident_primary.get("mujoco_version"),
            "model_xml": "gym_aloha/assets/bimanual_viperx_transfer_cube.xml",
            "n_cameras_a2_side": 3,
            "resolution_a2_side": args.image_size,
            "control_dt": args.dt,
            "control_hz": round(1.0 / args.dt, 6),
            "note": "五元标注缺一不可；不得与 (osmesa, mujoco 3.9.0, Piper STL, 单臂) 或 G3 的 50 Hz 数字互搬",
        },
        "quiet_window": (args.quiet_window or "not_in_a_declared_quiet_window"),
        "quiet_window_rule": ("裁定 73/76.4：要成为**权威口径**的标定测量必须在申报过的静默窗口内做；"
                              "窗口外测的一律标 `contaminated_by_cotenant`，只可作趋势参考"),
        "per_batch_gpu_yield_gate": {
            "checked_before_this_batch": True,
            "detector_nets": list(THREE_NET_RULING["nets"]),
            "detector_nets_ruling": THREE_NET_RULING,
            "detector_module": calib_id,
            "strict": True,
            "non_self_gpu_procs_at_batch_start": foreign_before,   # 旧一网字段，保留供对账
            "three_net_snapshot_at_batch_start": yield_snap,
            "gate": yield_gate,
            "three_readings_required_by_85_7_2": {
                "n_compute_apps": yield_snap.get("n_compute_apps"),
                "n_foreign_fd_holders": yield_snap.get("n_foreign_fd_holders"),
                "memory_used_mib": yield_snap.get("memory_used_mib"),
            },
            "refused_if_any_net_hits": True,
            "ruling": ("裁定 76.2 红线：每个 GPU 批次开跑前都要重查，不允许只在任务级查一次；"
                       "**裁定 85.0-2-① 升级**：`--query-compute-apps` 单独不构成合法占卡判据，"
                       "必须三网并查（复用 E 的 `card_busy(strict=True)`，不重造）"),
            "upgrade_reason": ("rep4/rep5 用一网半判据把 B2 的 EGL 图形负载（E 00:42:53 实测：持 "
                               "`/dev/nvidia2`+`/dev/nvidiactl`、11% / 102 MiB，而 compute-apps **空**）"
                               "判成「卡空」⇒ 两窗清洁认证降级为 `undetermined_detector_blind_to_egl`"),
        },
        "three_net": {
            "ruling": THREE_NET_RULING,
            "detector_module": calib_id,
            "applies_to": ["per_batch_gpu_yield_gate（起跑前 + 每批前，strict=True）",
                           "cotenant_evidence.periodic_sampling.three_net（运行中每样本）"],
            "own_descendants_excluded": {
                "why": ("`nvidia-smi` 自己会短暂持 `/dev/nvidiactl` ⇒ 不剔会造成**自致假阳**"
                        "（闸恒忙、永远拒绝开跑），与 RR-B2-18 的「恒真 ⇒ 狼来了」同族（裁定 85.6-2）"),
                "how": "`drop_own_descendants()`：剔除 pid==own 或 ppid==own 的命中",
                "depth_covered": 1,
                "e_side_coverage": "E 的 `_own_tree()` 覆盖自身+祖先（8 代），**不覆盖子进程** ⇒ 这一段是 A2 侧必须补的",
            },
            "wide_net_split": THREE_NET_RULING["net_meanings"]["proc_cmdline_gpu_intent"],
        },
        "activation_env": act,
        "boundary_facts": bnd,
        "gl_identity_mujoco_renderer": ident_primary,
        "nvidia_smi_before": nvidia_smi(),
        "load_before": ev.load_snapshot(),
        # 裁定 83§5：这里只是**初值**。真值在臂跑完后按 OR 语义重算（见 `policy_executed_gate`），
        # 并由 `gates.policy_executed_consistency` 看守。rep1 的缺陷正是「初值从未被重算」。
        "policy_executed": False,
        "policy_executed_definition": POLICY_EXECUTED_DEFINITION,
        "capability_claim": False,
        "success_metrics_collected": False,
        "no_multiprocess_rendering": True,
        "cross_transport_ban": ("本产物的每个吞吐/延迟数字都绑定 `backend_tuple_five`；"
                                "跨 venv / 渲染后端 / mujoco 版本 / 模型 / 相机数 / 分辨率 / DT **不得互搬**"
                                "（裁定 46.4 / 53.6）。"),
    }
    import importlib.metadata as md
    for m in ("torch", "transformers", "lerobot", "gym-aloha", "mujoco", "numpy", "gymnasium", "PyOpenGL"):
        try:
            rep["versions"][m] = md.version(m)
        except Exception:
            rep["versions"][m] = None

    extra_gates: dict = {}
    retro_pending = False
    if args.mode == "env_only":
        rec, live, applied = run_env_only(args, shim, ev, gl_identity_after_dm_render)
        ident_dm = rec.get("gl_identity_after_dm_render")
        rep["env_only"] = rec
        rep["live_timing"] = live
        rep["shim_apply_record"] = applied
        extra_gates["dt_mainline"] = dt_gate(live, applied, args.dt) if args.dt == 0.034 else {
            "ok": True, "skipped": True, "reason": f"本臂请求 dt={args.dt}（非主线 0.034），主线闸不适用"}
        # 只有「未激活 prefix」的 env_only 臂才承担回溯标注；GPU 臂发这条闸 = 假红（run1 已踩，见归档）
        retro_pending = not act["nvidia_prefix_active"]
    else:
        rec = run_closed_loop(args, shim, ev, gl_identity_after_dm_render)
        ident_dm = rec.get("gl_identity_after_dm_render")
        rep["closed_loop"] = rec
        rep["live_timing"] = rec["live_timing"]
        rep["shim_apply_record"] = rec["shim_apply_record"]
        rep["tied_weight_check"] = rec["tied_weight_check"]
        extra_gates["dt_mainline"] = dt_gate(rec["live_timing"], rec["shim_apply_record"], args.dt)
        extra_gates["tied_weight"] = {"ok": rec["tied_weight_check"].get("verdict") == "tie_ok",
                                "detail": rec["tied_weight_check"].get("verdict"),
                                "why_it_matters": "D 复核 G3 时差点把 `0/20` 误判成「权重没加载」；这条就地重算，读者不必再翻别的产物"}
        extra_gates["chunk_length_matches_cfg"] = {
            "ok": all(a["chunk_size"] == rec["model"]["chunk_size"] for a in rec["arms"].values()),
            "detail": {k: v["chunk_size"] for k, v in rec["arms"].items()}}
        extra_gates["v4_H_ge_2n"] = {
            "ok": True, "informational": True,
            "detail": {k: {"n_action_steps": v["n_action_steps"], "chunk_size": v["chunk_size"],
                           "satisfied": v["v4_H_ge_2n_satisfied"]} for k, v in rec["arms"].items()},
            "note": "**出厂 n=50 违反 v4 `H≥2n`**（S4 草案 §2.4）⇒ 主线运行时必须用 n≤25；本脚本两档都测，供 S4 定档"}

    cotenant_samples = sampler.stop()
    procs_after = am.gpu_procs()
    # **顺序 bug 修复（A2 自纠 ⑦）**：`rep["load_after"]` / `nvidia_smi_after` / `nr_throttled_delta_total`
    # 原先写在**下面 ~70 行之后**（gates 汇总处），而下面的 cotenant 块**先读**它们
    # ⇒ `KeyError: 'load_after'`，任何模式都跑不完。这个 cotenant 块是上一轮新加的、
    # **加完从未端到端跑过**（既有 env_only 产物 21:59/22:16 里根本没有 `cotenant_evidence` 字段可证）。
    # 修法不是把读的那行挪下去，而是把**臂终点快照**放在真正"臂结束"的那一刻——
    # 它本来就该与 `load_before`（臂起点）成对，放在 gates 计算之后反而把报告耗时算进了窗口。
    rep["load_after"] = ev.load_snapshot()
    rep["nvidia_smi_after"] = nvidia_smi()
    rep["nr_throttled_delta_total"] = (rep["load_after"].get("cpu_stat", {}).get("nr_throttled", 0)
                                       - rep["load_before"].get("cpu_stat", {}).get("nr_throttled", 0))
    rep["load_pair_semantics"] = ("load_before = 臂起点、load_after = 臂终点（采样器 stop 之后立刻取）；"
                                  "两者之间不含 gates 汇总与写盘的耗时")
    my_pid = os.getpid()
    foreign = [q for q in (procs_before + procs_after) if q.get("pid") != my_pid]
    foreign_in_samples = [q for sm in cotenant_samples for q in (sm.get("non_self_gpu_procs") or [])]
    la_before = rep["load_before"].get("loadavg_1m")
    la_after = rep["load_after"].get("loadavg_1m")
    la_delta = (la_after - la_before) if isinstance(la_before, (int, float)) and isinstance(la_after, (int, float)) else None
    rep["cotenant_evidence"] = {
        # **如实**：只有真的存在周期样本时才敢说 True（裁定 76.3 前这里是恒 True 的谎报，
        # 因为当时只在臂的前后各采一次 —— 见本字段下方的 caveat 与 `periodic_sampling`）
        "collected_at_run_time": bool(cotenant_samples),
        "periodic_sampling": sampler.evidence(),
        "cotenant_samples": cotenant_samples,
        "ruling": "裁定 73（静默窗口制度）：每臂落 cotenant_evidence；窗内有非本线 GPU 进程或 loadavg_1m 高出 ≥5 ⇒ 自动标 contaminated",
        "own_pid": my_pid,
        "gpu_compute_apps_before": procs_before,
        "gpu_compute_apps_after": procs_after,
        "non_a2_gpu_procs_in_window": bool(foreign or foreign_in_samples),
        "foreign_procs": foreign,
        "foreign_procs_seen_by_periodic_sampler": foreign_in_samples[:20],
        "loadavg_1m_before": la_before, "loadavg_1m_after": la_after, "loadavg_1m_delta": la_delta,
        # 判据输入改成**周期样本 ∪ 前后两点**：原先只看 `procs_before/after` 是否为空列表，
        # 而"空列表"其实有两种含义 —— ①采到了、卡上确实没别人 ②压根没采。旧写法把①当成②，
        # 于是明明有 11 个运行时样本、结论却是 `unknown_not_collected`（自相矛盾）。
        # `classify_cotenant` 的那条牙（**没有证据时不许输出 false**）保持不变：真的一个样本都没有才传 None。
        "evidence_basis": {
            "n_periodic_samples": len(cotenant_samples),
            "point_snapshots_taken": 2,          # before + after，总是各取一次
            "point_snapshots_with_procs": int(bool(procs_before)) + int(bool(procs_after)),
            "collected_any": bool(cotenant_samples or procs_before or procs_after),
        },
        "classification": am.classify_cotenant(
            bool(foreign or [q for sm in cotenant_samples for q in (sm.get("non_self_gpu_procs") or [])])
            if (cotenant_samples or procs_before or procs_after) else None,
            la_delta),
        # ── 裁定 85.0-2-①：三网判据。**只会更严、不会更松**（与上面那条一网判据取 OR）──────
        # 为什么不直接改 `classify_cotenant` 的输入：它在 `scripts/a2_artifact_amendments_20260929.py`，
        # 是**被复用的既有件**（裁定 72 `self_artifact_reuse_discipline`），改它会连带改动它已经
        # 写进历史产物的判据语义。⇒ A2 的做法是**并列两条判据 + 一条 OR 汇总**，两条都留在产物里，
        # 读者能看见"一网说了什么、三网说了什么、最终取哪个"。
        "classification_three_net": three_net_contamination(
            cotenant_samples, [yield_snap, three_net_snapshot(calib, strict=True, with_memory=True)]),
        "contaminated_final": None,        # 初值；下面按 OR 就地重算（裁定 84§4 `不得留初值`）
        "caveat": ("`gpu_compute_apps_before/after` 这两个字段**只**证明臂起点与终点的 GPU 占用；"
                   "窗口中途的瞬时并发由 `cotenant_samples[]`（周期采样，裁定 76.3）承载，"
                   "**不得再用前后两点冒充运行时证据**。若要成为权威口径，仍须在申报过的静默窗口内跑（裁定 73）。"),
    }
    # `contaminated_final` = 一网判据 OR 三网判据（**任一为 True 即 True**；任一为 unknown 且另一个
    # 为 False ⇒ 结果 unknown，**不许**降级成 False）。就地重算，不留初值（裁定 84§4）。
    _c1 = rep["cotenant_evidence"]["classification"].get("contaminated")
    _c2 = rep["cotenant_evidence"]["classification_three_net"].get("contaminated_three_net")
    _vals = [_c1, _c2]
    rep["cotenant_evidence"]["contaminated_final"] = (
        True if any(v is True for v in _vals)
        else ("unknown_not_collected" if any(isinstance(v, str) for v in _vals) else False))
    rep["cotenant_evidence"]["contaminated_final_semantics"] = {
        "aggregate": "OR（严格化：任一 True ⇒ True；无 True 但有 unknown ⇒ unknown；**永不由 unknown 降为 False**）",
        "inputs": {"one_net_classify_cotenant": _c1, "three_net_contamination": _c2},
        "guard": "gates.three_net_detector_85_0（自检 M5a–M5f）",
        "ruling": "裁定 73 + 85.0-2-① + 84§4 `top_level_aggregate_must_declare_semantics`",
    }
    ident = resolve_identity(ident_primary, ident_dm)
    rep["gl_identity_resolved"] = ident
    # 裁定 82.5：渲染速率类数字的 caveat（适用性按**实测 renderer_class** 判，不按环境变量判 —— 裁定 71）
    _is_gpu = (ident.get("renderer_class") == "nvidia_gpu")
    rep["ruling_82_5_render_rate_caveat"] = {
        "text": ("egl/GPU 下 wrist 相机**不逐位可复现**，且 `raw_first` 臂渲染速率被抬高 "
                 "`inflation_pct=8.3%` ⇒ 渲染速率类数字带此 caveat；推理延迟类不受影响（不经 GL）"),
        "renderer_class_measured": ident.get("renderer_class"),
        "applies_to_this_arm": bool(_is_gpu),
        "why": ("**适用性按实测 `GL_RENDERER` 判，不按 `MUJOCO_GL` 环境变量判**（裁定 71：GL_RENDERER 才是事实）："
                "E 实测 **osmesa/mesa 路径下三相机全部逐位一致** ⇒ 只跑在 llvmpipe 上的臂不带这条 caveat"),
        "affected_fields_if_applicable": ["env_only.env_step_fps", "env_only.render_*",
                                        "closed_loop.arms.*.t_render_s", "closed_loop.arms.*.mean_loop_fps"],
        "unaffected_fields": ["closed_loop.arms.*.t_infer_s", "mean inference / chunk 延迟（推理不经 GL）"],
        "a2_exonerated_by": ("裁定 82.5：`gl_identity_via_mujoco()`（本文件 `:702`）在 `make_env` 之前 ⇒ `raw_first`、安全；"
                             "`gl_identity_after_dm_render`（`:195`）只调 `glGetString`、不建 Renderer ⇒ 亦安全 "
                             "⇒ **裁定 75/76 的延迟数字无需重判**"),
    }
    rep["gpu_used"] = bool(args.mode == "closed_loop" or ident.get("renderer_class") == "nvidia_gpu")
    # ── 裁定 83§5：顶层 `policy_executed` **臂跑完后重算**（OR 语义），并落一致性牙 ──────────
    # 修法不是把初值改对，而是补上「重算」这一步：模式级值才是事实来源，顶层只是它的 OR 汇总。
    rep["policy_executed"] = bool((rep.get("closed_loop") or {}).get("policy_executed", False)
                                  or (rep.get("env_only") or {}).get("policy_executed", False))
    extra_gates["policy_executed_consistency"] = policy_executed_gate(rep)
    # ── 裁定 85.0-2-①：探测器本身也要被闸看守（守的是"凭什么说窗干净"，不是"窗干不干净"）──
    extra_gates["three_net_detector_85_0"] = three_net_detector_gate(rep)
    rep["aggregate_field_semantics"] = AGGREGATE_FIELD_SEMANTICS
    btf = rep["backend_tuple_five"]
    strs = ident.get("gl_strings") or {}
    btf["gl_renderer"] = strs.get("GL_RENDERER")
    btf["gl_vendor"] = strs.get("GL_VENDOR")
    btf["gl_version"] = strs.get("GL_VERSION")
    btf["renderer_class"] = ident.get("renderer_class")
    btf["identity_source"] = ident.get("identity_source")
    gates = {
        "gl_identity_resolved": {"ok": bool(strs.get("GL_RENDERER")),
                                 "detail": {"renderer_class": ident.get("renderer_class"),
                                            "identity_source": ident.get("identity_source"),
                                            "both_probes_agree": ident.get("both_probes_agree")}},
        "activation_consistency": activation_consistency_gate(ident, act, bnd),
        "expect_renderer": expect_renderer_gate(ident, args.expect_renderer),
        "prefix_only_boundary": {"ok": bool(bnd["system_clean"] and bnd["egl_prefix_exists"]),
                                 "detail": bnd},
    }
    if retro_pending:
        eo = rep.get("env_only") or {}
        rep["retro_label"] = {
            "target": "runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json 的 timing 段（loop_fps 10.39 / env_step_fps 11.91）",
            "claim": "G3 那轮的 `MUJOCO_GL=egl` **只是环境变量**；当时系统内无 NVIDIA EGL ICD（E 线 21:0x 才解锁、且随后回滚），"
                     "⇒ 实际渲染器 = **mesa/llvmpipe（CPU）**，故 `loop_fps≈10.39` 是 CPU 渲染口径",
            "valid": bool(ident.get("renderer_class") == "mesa_cpu_software" and not act["nvidia_prefix_active"]
                          and bnd["system_clean"]),
            "evidence": [
                "① G3 产物**从未记录 `GL_RENDERER`**：`grep -rl GL_RENDERER runs/vla/a2_*` = 0 命中（21:4x 实测）⇒ D 的口径说法此前在 A2 产物侧是 `declared_only`",
                "② 本臂用**同一组环境配置**（MUJOCO_GL=egl、无 prefix、系统 ICD 只有 mesa）实测渲染器身份 = "
                f"{(ident.get('gl_strings') or {}).get('GL_RENDERER')}"
                f"（取法：{ident.get('identity_source')}）",
                "③ 系统目录当前干净（E 已回滚、D 独立复核）⇒ 19:2x 那次也不可能拿到 NVIDIA EGL",
                "④ E 线独立实测：解锁前 gym_aloha 480×640 = 7.91 steps/s（llvmpipe 档），与 G3 的 env_step_fps 11.91 同一量级",
                f"⑤ 本臂自测 env_step_fps = {eo.get('env_step_fps')}（DT=0.034/17 子步）vs G3 的 11.91（DT=0.02/10 子步）"
                "—— 同为 CPU 渲染档，差值方向与子步数一致（**不是同口径，不可直接相减**）",
            ],
            "limits": "这是**同配置复现**，不是对 19:24 那个进程的直接观测（当时没记 GL 身份，无法回溯取证）",
        }
        extra_gates["retro_label_valid"] = {
            "ok": bool(rep["retro_label"]["valid"]),
            "detail": {"renderer_class": ident.get("renderer_class"),
                       "nvidia_prefix_active": act["nvidia_prefix_active"],
                       "system_clean": bnd["system_clean"]},
            "note": "反向牙：若不带 prefix 也能拿到 NVIDIA，则本回溯标注必须判无效（自检 M3a 已验证该分支会红）"}
    gates.update(extra_gates)
    rep["gates"] = gates
    all_ok = all(g.get("ok") for g in gates.values())
    rep["gates_all_ok"] = all_ok
    # load_after / nvidia_smi_after / nr_throttled_delta_total 已在**臂终点**处写入（见上方自纠 ⑦）
    rep["gpu_deregister_note"] = ("本进程退出后由调用方复测 `nvidia-smi` 必须回到 0 MiB / 无进程（GPU 销账纪律）")

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"latency_{args.tag}.json"
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(f"[written] {p}", flush=True)
    print(json.dumps({"tag": args.tag, "mode": args.mode, "gates_all_ok": all_ok,
                      "renderer_class": ident.get("renderer_class"),
                      "gl_renderer": (ident.get("gl_strings") or {}).get("GL_RENDERER"),
                      "gates": {k: v.get("ok") for k, v in gates.items()},
                      "nr_throttled_delta": rep["nr_throttled_delta_total"],
                      "loadavg_before": [rep["load_before"].get(k) for k in ("loadavg_1m", "loadavg_5m", "loadavg_15m")],
                      "loadavg_after": [rep["load_after"].get(k) for k in ("loadavg_1m", "loadavg_5m", "loadavg_15m")],
                      "env_step_fps": (rep.get("env_only") or {}).get("env_step_fps"),
                      "mean_loop_fps_by_arm": {k: v.get("mean_loop_fps") for k, v in
                                               ((rep.get("closed_loop") or {}).get("arms") or {}).items()}},
                     ensure_ascii=False, indent=1), flush=True)
    return 0 if all_ok else 3


if __name__ == "__main__":
    sys.exit(main())
