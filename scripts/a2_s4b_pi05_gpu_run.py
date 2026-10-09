#!/usr/bin/env python3
"""A2 / **T-A2-6** —— S4b 的 **GPU·EGL 权威臂**：四类判定接 `ledger`（独立于 `reward==4`）+ 同批三件。

## 判据（照抄，不重新解释）
`work/project_parameters.json:1047`（`vla_runtime_gap`）：
「**S4b**（等 C2 的 env）= 四类判定接 `ledger`，**独立于 `reward==4`**，不一致即红。」
派工原文 `rl_harness_supervision/d_handoff_to_a2_20260930.md` §一 + **裁定 94 补单**（§一 GPU 过渡协议、
§二 `prompt_bin_guard` 认可与 bin 常量口径、§三 身份口径更正、§四 BC 入口与正确性族 caveat）。

## 本臂与 CPU 臂的分工（口径**不得互搬**，裁定 46.4 / 53.6 / 71）
* `scripts/a2_s4b_outcome_ledger_verify.py` = **闸与变异体**（CPU-only，`MUJOCO_GL=osmesa`，15 闸 + 22 牙）。
* 本脚本 = **真实 π₀.₅（零 SFT）+ 真实 EGL 渲染**的权威臂，负责三件**只有在 GPU/EGL 下才测得到**的事：
  ① **运行时** prompt 的非法 `-1` token（`harness/prompt_bin_guard.PromptCapture` 旁路钩子抓的是
     **真正拼进 prompt 的那一条文本**，不是离线 stats）；
  ② `renderer_class` **三点**（起点/运行内/终点）—— osmesa 臂实测三点全 `null`
     （`runs/vla/a2_s4b_outcome_ledger_20260930_dbg7/s4b_verification.json`）⇒ **只有 EGL 臂**能给
     E 的 **C4 复验第三方证据**（`params:1412`：搭便车、不单开窗口）；若回 `nvidia_gpu`，即证明
     E 的前缀改动无害；
  ③ 主线 `n_replan=25` **同步闭环**的延迟/吞吐（每个数字成对带 `loadavg` 三点 + `nr_throttled`）。

## 本脚本**不做什么**（每一条都是已发生过的事故形状）
* **不重算判定**：四类结论只取自 C2 的 `harness/env_gym_aloha.py`（`judge_from_facts`），
  连 `cross_check()` / `ledger_label_kwargs()` 也是**直接调 C2 的方法对象**（自造 = 与 J1–J15 分叉）。
* **不重造探测器**：三网 = E 的 `card_busy()`（经 A2 自己的 `three_net_snapshot()` 归一）；
  policy 构造 / 动作适配 / 负载快照 = `scripts/a2_pi05_zeroshot_eval.py` 的 `build_policy()` /
  `adapt_action()` / `load_snapshot()`（G3 的**同一套**，⇒ 本臂与 G3 的 0/20 只差被声明的那几个变量）。
* **本件不另立 bin 常量口径**：`N_BINS=256` / `SAT_BIN_HIGH=255` / `ILLEGAL_BIN_LOW=-1` 与
  `harness/norm_contract.py:63/:93/:94` **同值**，由 `harness/prompt_bin_guard.py` 承载（裁定 94 补单-§二）。
  ⇒ 给 **C2 的指针**：离线牙（`Te1`/`Te2`，判归一化后的数组）在 `scripts/c2_gate_norm_contract.py`；
  运行时牙（判**真正拼进 prompt 的文本**）在 `harness/prompt_bin_guard.py`；两者**互补而非分叉**。
* **不声称能力**（裁定 46）：`capability_claim=false`、成功率栏 = `not_an_exit_criterion`。
  四类分布是**契约层**证据，不是 policy 指标；G3 的 zero-shot 0/20 已按「非能力结论」登记，
  本臂**不得**被引用成「模型不行」或「模型行」。
* **不声称实时闭环**（裁定 75.5）：`realtime_closed_loop_claim` 恒 `false`（`async_overlap=false`）。

## GPU 纪律（裁定 73 / 84.7 / 85.0-2 / 85.6-2 / 85.7 + 裁定 94 补单-§一，一条都不豁免）
1. **起跑前拒绝逻辑**（B2 的 `gpu_preflight()` 是参考实现）：起跑那一刻实测三网
   （compute-apps / `/dev/nvidia*` fd 持有者 / cmdline），外来 GPU 占用命中且未显式
   `--allow-cotenant` ⇒ **拒绝起跑 `exit 3`** + 落 `refused_gpu_busy_<ts>.json`。
   **「起跑前已实测 GPU 空载」这类写死字符串一律无效**（裁定 50.1/72）。
2. `GPU_WINDOW.json`：`start`/`end` + 三网原文 + `loadavg` **三点** + `nr_throttled`
   （cgroup **v1** 路径 `/sys/fs/cgroup/cpu/cpu.stat`；v2 路径本机不存在）+ 外来进程清单 +
   `contaminated` 判定（缺证据 ⇒ `unknown_not_collected`，**不许**写 `false`）。
3. 运行中**周期**采共租证据（裁定 76.3 红线 `cotenant_evidence_must_be_runtime`）——
   复用 `RuntimeCotenantSampler`（后台线程，**不在关键路径上**，开销自己记账）。
4. **先申报后上卡**：`--policy pi05` 必须给 `--declaration-line`（`daily_report.md` 里的申报行号），
   本脚本会**读回该行**核它确实提到 A2 与 GPU 窗口；核不过 ⇒ `exit 2`，不上卡。
5. 单卡优先权 **A2 > B2 > C2 > E**（裁定 85.7）。宽档 cmdline（他线**纯 CPU** 脚本）
   **只登记不拒绝**：A2 优先级最高，且把宽档当拒绝判据会重演 RR-B2-18 的「恒真 ⇒ 狼来了」。
   ⇒ `--refusal-strictness strict` 可把宽档也纳入拒绝（默认 `narrow`，选择本身落进产物）。
6. **不跑 `find /`**（新纪律 `no_root_filesystem_scans`）；本脚本只读显式给出的路径。

## 用法（**前台跑**；先激活 EGL 前缀）
    eval "$(bash scripts/e_activate_gpu_render.sh --print)"
    /root/venvs/pi05_sim/bin/python scripts/a2_s4b_pi05_gpu_run.py \
        --out-dir runs/vla/a2_s4b_pi05_gpu_20260930 \
        --directions right_to_left,left_to_right --n-episodes 3 \
        --declaration-line <daily_report.md 里的申报行号>

    # CPU 管路自检（**不占 GPU、不是权威臂**；口径标 `cpu_osmesa_plumbing_check`）：
    /root/venvs/pi05_sim/bin/python scripts/a2_s4b_pi05_gpu_run.py --policy hold \
        --mujoco-gl osmesa --directions right_to_left --n-episodes 1 --max-frames 60 \
        --out-dir runs/vla/a2_s4b_pi05_gpu_plumbing_20260930

退出码：`0` 完成且无阻塞红 · `1` 结构性失败/阻塞红 · `2` 用法或未申报 · `3` **起跑前拒绝（GPU 忙）**。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import time
import types
from datetime import datetime

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "4")

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np                                                     # noqa: E402

from harness import prompt_bin_guard as PBG                            # noqa: E402
from harness import vla_runtime as VR                                  # noqa: E402
from harness.ledger import FactLedger                                  # noqa: E402

# ══════════════════════════ 口径常量（都能被独立复核）══════════════════════════
CRITERION_VERBATIM = ("S4b（等 C2 的 env）= 四类判定接 ledger，独立于 reward==4，不一致即红。"
                      "（work/project_parameters.json:1047，不重新解释）")
HANDOFF = "rl_harness_supervision/d_handoff_to_a2_20260930.md"
DAILY_REPORT = "daily_report.md"
MORPHOLOGY = "aloha_bimanual_14d"
EXIT_OK, EXIT_BLOCKING_RED, EXIT_USAGE, EXIT_REFUSED_GPU_BUSY = 0, 1, 2, 3

# 任务文本按方向分列。**这是 A2 的口径选择，显式登记**：G3 只跑过 right_to_left 的那一句；
# 反向臂换文本是必须的（否则 prompt 与 goal_id 互相打脸），但 base ckpt 对两句的响应差异
# **未被测过** ⇒ 记 `task_text_caliber="a2_choice_not_validated_on_base_ckpt"`。
TASK_BY_DIRECTION = {
    "right_to_left": "Transfer the red cube from the right arm to the left arm.",
    "left_to_right": "Transfer the red cube from the left arm to the right arm.",
}
TASK_TEXT_SAME_AS_G3 = {"right_to_left": True, "left_to_right": False}

# 延迟权威带（裁定 94 补单 / §四：不变；本臂的数字要与它**同口径**才可并列）
AUTHORITATIVE_LATENCY_BAND = {
    "caliber": "synchronous_blocking_serial + MUJOCO_GL=egl + n_replan=25 + H=50 + A800-80GB",
    "rep4": {"budget_fraction": 0.8009, "ms_per_ctrl_step": 27.230,
             "source": "runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep4.json"},
    "rep5": {"budget_fraction": 0.7766, "ms_per_ctrl_step": 26.405,
             "source": "runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep5.json"},
    "rep1_rejected": {"budget_fraction": 1.3466, "status": "contaminated__not_adopted"},
    "all_episodes_within_per_step_budget": True,
    "note": ("rep4/rep5 的臂**没有**把 cotenant 采样器挂在关键路径上（其 episode 记录里无 "
             "`cotenant_sampling_ms_per_ctrl_step` 字段）⇒ 本臂默认 `--cotenant-interval-s 0`"
             "（关掉运行时采样器）以保持同口径；窗口级共租证据由后台线程承载，不占关键路径。"),
}

# 裁定 94.3/94.5 的代价：**必须写在脸上**（补单-§四-2）
CORRECTNESS_FAMILY_CAVEAT = {
    "statement": ("正确性族（held-out 口径）在 [0,3,5,7,10,12] 六维上是 `not_measured`；"
                  "偿清之前不得写「归一化器已通过正确性验证」。"),
    "dims_not_measured": [0, 3, 5, 7, 10, 12],
    "measurement_status": "not_measured",
    "red_line": "absence_of_measurement_is_not_measurement_of_absence",
    "ruling": "裁定 94.3 / 94.5；d_handoff_to_a2_20260930.md 补单-§四-2",
}
RULING_46 = ("裁定 46：能力声明禁令。本臂产物里出现的任何计数都**不是** policy 能力指标；"
             "`success_rate_column=\"not_an_exit_criterion\"`、`capability_claim=false`。")
BIN_CONSTANT_CALIBER_NOT_REESTABLISHED = {
    "statement": "本件不另立 bin 常量口径（裁定 94 补单-§二）。",
    "values": {"N_BINS": PBG.N_BINS, "SAT_BIN_HIGH": PBG.SAT_BIN_HIGH,
               "ILLEGAL_BIN_LOW": PBG.ILLEGAL_BIN_LOW, "MAX_STATE_DIM": PBG.MAX_STATE_DIM},
    "same_value_as": "harness/norm_contract.py:63/:93/:94（N_BINS=256 / SAT_BIN_HIGH=255 / SAT_BIN_LOW=-1）",
    "carrier": "harness/prompt_bin_guard.py（A2 自有；bin 常量与 C2 同值不另立）",
    "pointer_for_c2": {
        "offline_tooth": "scripts/c2_gate_norm_contract.py 的 Te1/Te2（判**归一化后的数组**）",
        "runtime_tooth": "harness/prompt_bin_guard.py 的 PromptCapture/audit_prompt_text"
                         "（判**真正拼进 prompt 的文本**）",
        "relation": "互补而非分叉（裁定 94 补单-§二）",
        "auditor_self_proof": "prompt_bin_guard.pattern_coverage_probe()（裁定 93.8：审计器须自证模式覆盖）",
    },
}


# ══════════════════════════ 小工具 ══════════════════════════
def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(p: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()[:12]
    except Exception:                                                  # noqa: BLE001
        return None


def sha256_big(p: pathlib.Path, chunk: int = 1 << 22) -> tuple[str | None, float, int | None]:
    """大文件 sha256（`model.safetensors` = 14.4 GB）。**自己复算**，不采信 receipt（裁定 83§7）。"""
    t0 = time.perf_counter()
    try:
        h = hashlib.sha256()
        n = 0
        with open(p, "rb") as fh:
            while True:
                b = fh.read(chunk)
                if not b:
                    break
                n += len(b)
                h.update(b)
        return h.hexdigest(), round(time.perf_counter() - t0, 2), n
    except Exception:                                                  # noqa: BLE001
        return None, round(time.perf_counter() - t0, 2), None


def jdefault(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    if isinstance(o, pathlib.Path):
        return str(o)
    if hasattr(o, "as_dict"):
        return o.as_dict()
    return str(o)


def write_json(path: pathlib.Path, obj) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2, default=jdefault)
    path.write_text(txt + "\n", encoding="utf-8")
    return {"path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
            "sha256_12": hashlib.sha256((txt + "\n").encode("utf-8")).hexdigest()[:12],
            "bytes": len((txt + "\n").encode("utf-8")),
            "n_lines_wc_l": (txt + "\n").count("\n")}


def load_module_by_path(name: str, relpath: str):
    """按**路径**加载（本仓既有口径，见 `a2_egl_latency_remeasure._load_eval_module`）。"""
    path = REPO / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ══════════════════════════ 复用件（**不重造**）══════════════════════════
def load_reuse() -> dict:
    """把要复用的四件按路径 import，并取**身份三元组**（裁定 64：只有路径的引用不可核验）。"""
    a2l = load_module_by_path("a2_egl_latency_remeasure", "scripts/a2_egl_latency_remeasure.py")
    zs = a2l._load_eval_module()
    calib = a2l._load_e_calib_module()
    am = a2l._load_amendments_module()
    ident = {
        "three_net_detector": a2l.module_identity(REPO / "scripts/e_mainline_render_calib.py",
                                                  "importlib（A2 不复制 E 的代码）"),
        "policy_builder_and_action_adapter": a2l.module_identity(
            REPO / "scripts/a2_pi05_zeroshot_eval.py", "a2_egl_latency_remeasure._load_eval_module()"),
        "latency_remeasure_helpers": a2l.module_identity(
            REPO / "scripts/a2_egl_latency_remeasure.py", "importlib.util.spec_from_file_location"),
        "cotenant_classifier": a2l.module_identity(
            REPO / "scripts/a2_artifact_amendments_20260929.py",
            "a2_egl_latency_remeasure._load_amendments_module()"),
        "prompt_bin_guard": a2l.module_identity(REPO / "harness/prompt_bin_guard.py", "import harness"),
        "vla_runtime": a2l.module_identity(REPO / "harness/vla_runtime.py", "import harness"),
        "this_script": a2l.module_identity(REPO / "scripts/a2_s4b_pi05_gpu_run.py", "__file__"),
        **VR.env_gym_aloha_identity(),
    }
    ident["env_gym_aloha_shim"] = a2l.module_identity(REPO / "envs/gym_aloha_shim.py",
                                                      "harness.env_gym_aloha 模块级 import")
    return {"a2l": a2l, "zs": zs, "calib": calib, "am": am, "identity": ident}


# ══════════════════════════ ① 申报核对（先申报后上卡）══════════════════════════
def check_declaration(line_no: int | None, *, required: bool) -> dict:
    """核 `daily_report.md` 里的 GPU 窗口申报行**确实存在且确实是 A2 的申报**。

    为什么要在代码里核：裁定 73 的申报制度若只靠自觉，就会退化成 B2 那次「manifest 里写着
    23:45 的陈旧断言、同文件的实测证据却打脸」。**读回原文**才算核过（裁定 50.1/72 同族）。
    """
    p = REPO / DAILY_REPORT
    doc: dict = {"artifact": "gpu_window_declaration_check", "report_path": DAILY_REPORT,
                 "report_exists": p.exists(), "report_sha256_12": sha12(p),
                 "declared_line_no": line_no, "required_for_this_arm": bool(required),
                 "measurement_status": "not_measured", "verdict": None, "found_text": None}
    if not p.exists():
        doc["why"] = f"读不到 {DAILY_REPORT} ⇒ not_measured（不是「没有申报」）"
        return doc
    n_lines = p.read_text(encoding="utf-8", errors="replace").count("\n")
    doc["report_lines_wc_l"] = n_lines
    if line_no is None:
        doc["why"] = ("未提供 `--declaration-line` ⇒ 申报事实 `not_measured`。"
                      + ("**本臂是上卡臂，先申报后上卡是硬纪律 ⇒ main() 会 exit 2**" if required
                         else "CPU 管路自检臂不上卡 ⇒ 不阻塞"))
        return doc
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if not (1 <= int(line_no) <= len(lines)):
        doc.update({"why": f"行号 {line_no} 越界（文件 {len(lines)} 行）", "verdict": "RED"})
        return doc
    text = lines[int(line_no) - 1]
    doc.update({"measurement_status": "measured", "found_text": text[:600],
                "line_mentions_a2": ("A2" in text),
                "line_mentions_gpu_window": (("GPU" in text) and (("申报" in text) or ("窗口" in text))),
                "line_mentions_three_net_or_loadavg": (("三网" in text) or ("loadavg" in text)
                                                       or ("nr_throttled" in text))})
    ok = bool(doc["line_mentions_a2"] and doc["line_mentions_gpu_window"])
    doc["verdict"] = "GREEN" if ok else "RED"
    if not ok:
        doc["why"] = "该行没有同时提到 A2 与 GPU 窗口 ⇒ 不认它为申报行（不许拿无关行充数）"
    return doc


# ══════════════════════════ ② GPU 窗口：拒绝逻辑 + 账本 ══════════════════════════
class GpuBusyRefusal(RuntimeError):
    """起跑前三网命中**外来 GPU 占用**且未显式 `--allow-cotenant` ⇒ 拒绝起跑（`exit 3`）。"""


class GpuWindow:
    """GPU 窗口的**起跑前拒绝 + 窗口账本 + 运行中周期采样**（裁定 73/76.3/84.7/85.0-2/85.6-2/85.7）。

    三条硬要求（裁定 94 补单-§一）逐条落地：
      ③ `GPU_WINDOW.json`：`start`/`end` + 三网原文 + `loadavg` 三点 + `nr_throttled`
         （cgroup **v1** `/sys/fs/cgroup/cpu/cpu.stat`）+ 外来进程清单 + `contaminated` 判定；
      ④ **起跑前拒绝逻辑**：`n_foreign_gpu_processes > 0` 且未显式 `--allow-cotenant` ⇒
         拒绝起跑 `exit 3` + 落 `refused_gpu_busy_<ts>.json`。判定来自**本进程起跑那一刻**的实测，
         写死的字符串一律无效（裁定 50.1/72）。

    **GL 上下文必须在硬闸之后才起**：`preflight()` 在 `open()` 之前、`open()` 在模型加载与
    env 构造之前 ⇒ 自己不会成为 fd 网的命中者（B2 `gpu_preflight()` 的同一条注意事项）。
    """

    def __init__(self, run_dir: pathlib.Path, *, reuse: dict, allow_cotenant: bool,
                 refusal_strictness: str, sampler_interval_s: float, arm_label: str,
                 declaration: dict, three_net_strict_for_sampler: bool = True):
        self.run_dir = run_dir
        self.a2l = reuse["a2l"]
        self.calib = reuse["calib"]
        self.am = reuse["am"]
        self.calib_identity = reuse["identity"]["three_net_detector"]
        self.allow_cotenant = bool(allow_cotenant)
        self.refusal_strictness = refusal_strictness
        self.arm_label = arm_label
        self.declaration = declaration
        self.sampler = self.a2l.RuntimeCotenantSampler(
            self.am, interval_s=float(sampler_interval_s), own_pid=os.getpid(),
            calib=self.calib, three_net_strict=three_net_strict_for_sampler)
        self.preflight_doc: dict | None = None
        self.start_readings: dict | None = None
        self.end_readings: dict | None = None
        self.started_at: str | None = None
        self.ended_at: str | None = None
        self.path = run_dir / "GPU_WINDOW.json"
        self._t0: float | None = None

    # ---- ④ 起跑前拒绝逻辑 ----
    def preflight(self) -> dict:
        snap = self.a2l.three_net_snapshot(self.calib, own_pid=os.getpid(), strict=True,
                                           with_memory=True)
        # 决策视图：默认 `narrow` ⇒ 宽档（他线**纯 CPU** 脚本）**只登记不拒绝**。
        # 理由：A2 优先级最高（裁定 85.7），且把宽档当拒绝判据会重演 RR-B2-18 的「恒真 ⇒ 狼来了」。
        # 原始 strict=True 快照**照样全量落盘**（不许因为不拒绝就把证据丢掉）。
        view = dict(snap)
        if self.refusal_strictness == "narrow":
            view["strict"] = False
        gate = self.a2l.three_net_yield_gate(view, detector_module=self.calib_identity)
        n_foreign_gpu = (int(snap.get("n_compute_apps") or 0) + int(snap.get("n_foreign_fd_holders") or 0))
        doc = {
            "artifact": "gpu_preflight_three_net",
            "ts": now_iso(), "own_pid": os.getpid(), "parent_pid": os.getppid(),
            "arm_label": self.arm_label,
            "measured_at_process_start": True,
            "hardcoded_string_forbidden": ("裁定 50.1/72：本块每个数字都来自**本次进程**起跑那一刻的 "
                                           "`nvidia-smi` + `/proc` 实测，没有任何写死的「已实测空载」字符串"),
            "three_net_raw": snap,
            "n_foreign_gpu_processes": n_foreign_gpu,
            "n_foreign_gpu_processes_definition": ("compute-apps 条数 + 持 `/dev/nvidia*` 的外来 PID 数"
                                                   "（两者都已剔除本进程树与 1 代子进程，如本脚本派生的 "
                                                   "`nvidia-smi`）"),
            "yield_gate": gate,
            "refusal_strictness": self.refusal_strictness,
            "refusal_strictness_rationale": (
                "narrow = 拒绝判据只看 compute-apps / fd 网 / cmdline **窄档**（明确 GPU 意图）+ "
                "`memory.used==0`；宽档（任何他线脚本，含纯 CPU）**登记不拒绝** —— A2 单卡优先权最高"
                "（裁定 85.7），且宽档当拒绝判据 = RR-B2-18 的「恒真 ⇒ 狼来了」。"
                "`--refusal-strictness strict` 可把宽档纳入拒绝。"),
            "wide_net_hits_registered_not_blocking": (snap.get("other_line_script_wide") or []),
            "allow_cotenant": self.allow_cotenant,
            "detector_reuse": "E 的 card_busy()（A2 不重造，裁定 85.0-2-①）",
            "detector_module": self.calib_identity,
            "priority_ruling": "裁定 85.7：A2 > B2 > C2 > E（关键路径感知；取代裁定 73 的 A2>C2>E>B2）",
        }
        refuse = bool(gate.get("refuse"))
        doc["refused"] = bool(refuse and not self.allow_cotenant)
        doc["override_applied"] = bool(refuse and self.allow_cotenant)
        if refuse and self.allow_cotenant:
            doc["override_note"] = ("`--allow-cotenant` 显式放行：闸判 refuse 但按调用方指令继续；"
                                    "**本窗口的延迟/吞吐数字自动标 `contaminated_candidate=true`**")
        self.preflight_doc = doc
        if doc["refused"]:
            ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
            rp = self.run_dir / f"refused_gpu_busy_{ts}.json"
            doc["refusal_artifact"] = write_json(rp, {
                "artifact": "refused_gpu_busy", "ts": doc["ts"], "exit_code": EXIT_REFUSED_GPU_BUSY,
                "reason": "起跑前三网命中外来 GPU 占用且未给 --allow-cotenant ⇒ 拒绝起跑（裁定 94 补单-§一-4）",
                "n_foreign_gpu_processes": n_foreign_gpu,
                "yield_gate_reasons": gate.get("reasons"),
                "three_net_raw": snap, "detector_module": self.calib_identity,
            })
            raise GpuBusyRefusal(
                f"GPU 忙 ⇒ 拒绝起跑（exit {EXIT_REFUSED_GPU_BUSY}）：n_foreign_gpu_processes="
                f"{n_foreign_gpu}；理由={gate.get('reasons')}；已落 {rp.name}")
        return doc

    # ---- 开窗 ----
    def open(self) -> dict:
        self._t0 = time.perf_counter()
        self.started_at = now_iso()
        self.start_readings = PBG.gpu_window_readings(extra={"phase": "at_start"})
        self.sampler.start()
        doc = self._doc(phase="open")
        write_json(self.path, doc)
        return doc

    def runtime_cotenant_sample(self) -> dict:
        """给 `ChunkedVlaRuntime(cotenant_sampler=…)` 的回调（**只在 `--cotenant-interval-s>0` 时挂**）。"""
        snap = self.a2l.three_net_snapshot(self.calib, own_pid=os.getpid(), strict=False,
                                           with_memory=True)
        la = os.getloadavg()
        return {"ts": now_iso(), "n_compute_apps": snap.get("n_compute_apps"),
                "n_foreign_fd_holders": snap.get("n_foreign_fd_holders"),
                "n_other_line_gpu_intent": snap.get("n_other_line_gpu_intent"),
                "memory_used_mib": snap.get("memory_used_mib"),
                "loadavg": f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}",
                "scan_overhead_s": snap.get("scan_overhead_s"),
                "collected_at_run_time": True,
                "attribution_strength": "inferred_from_pid_and_timeline"}

    # ---- 关窗 ----
    def close(self, *, renderer_at_end: dict | None = None, extra: dict | None = None) -> dict:
        samples = self.sampler.stop()
        self.ended_at = now_iso()
        self.end_readings = PBG.gpu_window_readings(extra={"phase": "at_end"})
        doc = self._doc(phase="closed", renderer_at_end=renderer_at_end, extra=extra)
        doc["in_run_cotenant_evidence"] = self.sampler.evidence()
        doc["in_run_cotenant_samples_n"] = len(samples)
        doc["in_run_cotenant_samples_first3"] = samples[:3]
        doc["in_run_cotenant_samples_last3"] = samples[-3:]
        write_json(self.path, doc)
        return doc

    def _doc(self, *, phase: str, renderer_at_end: dict | None = None,
             extra: dict | None = None) -> dict:
        s, e = self.start_readings or {}, self.end_readings or {}
        nr0, nr1 = s.get("nr_throttled"), e.get("nr_throttled")
        doc = {
            "artifact": "GPU_WINDOW",
            "line": "A2", "task": "T-A2-6 / S4b GPU·EGL 权威臂",
            "arm_label": self.arm_label,
            "phase": phase,
            "ruling": ("裁定 73（静默窗口制度）+ 84.7（缺窗口账本 ⇒ D 不认该窗口的延迟/吞吐数字）"
                       "+ 85.0-2-①/85.6-2（三网化）+ 85.7（A2 优先）+ 94 补单-§一（过渡协议）"),
            "registry_script_status": ("`scripts/gpu_window_ledger.py` 尚不存在 ⇒ 走过渡协议："
                                       "daily_report 申报 + 本文件 + 起跑前拒绝逻辑"),
            "start": {"ts": self.started_at, "readings": s},
            "end": {"ts": self.ended_at, "readings": e},
            "elapsed_s": (round(time.perf_counter() - self._t0, 2) if self._t0 else None),
            "loadavg_three_points": {"at_start": s.get("loadavg"), "at_end": e.get("loadavg"),
                                     "pairing_rule": ("裁定 46.4/53.6/85.7：任何吞吐/延迟数字必须成对引 "
                                                      "`loadavg`(3 点) + `nr_throttled`；cgroup 配额 "
                                                      f"{s.get('cgroup_quota_cores')} 核，`nproc=112` 是假象")},
            "nr_throttled": {"at_start": nr0, "at_end": nr1,
                             "delta": (None if (nr0 is None or nr1 is None) else int(nr1) - int(nr0)),
                             "cgroup_path": "/sys/fs/cgroup/cpu/cpu.stat",
                             "cgroup_version": "v1（v2 路径本机不存在，裁定 94 补单-§一-3）"},
            "three_net_at_start": (self.preflight_doc or {}).get("three_net_raw"),
            "preflight": self.preflight_doc,
            "declaration": self.declaration,
            "foreign_process_list": {
                "at_start": {"compute_apps": ((self.preflight_doc or {}).get("three_net_raw") or {}).get("compute_apps"),
                             "fd_holders": ((self.preflight_doc or {}).get("three_net_raw") or {}).get("foreign_fd_holders"),
                             "cmdline_narrow": ((self.preflight_doc or {}).get("three_net_raw") or {}).get("other_line_gpu_intent"),
                             "cmdline_wide_registered_only": ((self.preflight_doc or {}).get("three_net_raw") or {}).get("other_line_script_wide")},
                "definition": "「外来」= 非本进程树（含 1 代子进程）；归线按脚本前缀，只能是 inferred（裁定 76.1）",
            },
            "renderer_class_at_end": renderer_at_end,
            "contaminated": None,
        }
        if phase == "closed":
            ev = self.sampler.evidence()
            tn = ev.get("three_net") or {}
            las = [sm.get("loadavg_1m") for sm in self.sampler.samples
                   if isinstance(sm.get("loadavg_1m"), (int, float))]
            swing = (round(max(las) - min(las), 2) if len(las) >= 2 else None)
            override = bool((self.preflight_doc or {}).get("override_applied"))
            doc["contaminated"] = {
                "contaminated_three_net": tn.get("contaminated_three_net"),
                "contaminated_by_loadavg_swing_ge_5": (None if swing is None else bool(swing >= 5.0)),
                "loadavg_1m_swing": swing,
                "contaminated_overall": (None if tn.get("contaminated_three_net") is None else
                                         bool(tn.get("contaminated_three_net")
                                              or (swing is not None and swing >= 5.0)
                                              or override)),
                "contaminated_candidate_because_allow_cotenant": override,
                "reason": tn.get("reason"),
                "net_hit_counts": tn.get("net_hit_counts"),
                "n_periodic_samples": ev.get("n_periodic_samples"),
                "sampling_interval_s": ev.get("sampling_interval_s"),
                "sampler_overhead_s": ev.get("sampler_overhead_s"),
                "sampler_overhead_pct_of_window": ev.get("sampler_overhead_pct_of_window"),
                "nr_throttled_values_in_window": ev.get("nr_throttled_values"),
                "memory_used_mib_max": tn.get("memory_used_mib_max"),
                "attribution_strength": "inferred_from_pid_and_timeline",
                "caliber_note": ("宽档（他线纯 CPU 脚本）只喂 yield 闸、不喂污染定性 —— A2 的口径切分，"
                                 "D 可推翻（`three_net_contamination()` 的 docstring 里已登记）"),
            }
        if extra:
            doc.update(extra)
        return doc


# ══════════════════════════ ③ π₀.₅ → VlaChunkPolicy ══════════════════════════
class _Rows:
    """`ActionChunk.actions` 的最小容器：可 `__getitem__`、有 `.shape`（runtime 只用到这两件）。"""

    def __init__(self, rows):
        self.rows = rows
        self.shape = (len(rows), len(rows[0]) if rows else 0)

    def __getitem__(self, i):
        return self.rows[i]

    def __len__(self):
        return len(self.rows)


class Pi05ChunkPolicy:
    """π₀.₅ **base（零 SFT）** → `harness/vla_runtime.VlaChunkPolicy`。

    构造与动作适配一律**复用**既有实现（裁定 72 `self_artifact_reuse_discipline`）：
      * `build_policy()` / `adapt_action()` 来自 `scripts/a2_pi05_zeroshot_eval.py`（G3 的同一套）
        ⇒ 本臂与 G3 的 0/20 只差**被声明的那几个变量**（运行时 = `ChunkedVlaRuntime`、判定层 = C2 的
        `env_gym_aloha`、`n_replan=25` 而非 `n_action_steps=50` 的队列语义）；
      * prompt 文本由 `harness/prompt_bin_guard.PromptCapture` 的**旁路钩子**抓
        （`register_after_step_hook`，`lerobot/processor/pipeline.py:1264`）⇒ 抓的是**模型真正吃到的那一条**，
        不是自己再跑一遍 tokenizer 得到的**另一份**文本（那正是"离线绿、运行时红"的分叉形状）。

    `stats_version` **恒为 `NONE`**：π₀.₅ base 不携带 normalizer stats（裁定 44.1/49.2；
    `normalizer_processor.config.features={}` ⇒ pass-through）。⇒ runtime 的 `_guard_stats_version()`
    会**硬隔离**（`td_eligible=bc_eligible=False`）—— 这是**预期形态**，本臂如实登记，不掩盖。
    """

    def __init__(self, *, adapter, zs, weights_dir: str, tokenizer_dir: str, device: str,
                 task_text: str, n_replan: int, keep_last_n: int = 4096, weights_identity: dict | None = None):
        self.adapter = adapter
        self.zs = zs
        self.n_replan = int(n_replan)
        self.task_text = task_text
        self.device = device
        ns = types.SimpleNamespace(weights_dir=weights_dir, tokenizer_dir=tokenizer_dir, device=device)
        self.policy, self.preprocess, self.postprocess, self.cfg, self.load_info = zs.build_policy(ns)
        self.chunk_size = int(self.cfg.chunk_size)
        self.n_action_steps = int(self.cfg.n_action_steps)
        self.max_action_dim = int(self.cfg.max_action_dim)
        if self.chunk_size < 2 * self.n_replan:
            raise RuntimeError(f"H≥2n 不成立：chunk_size={self.chunk_size} < 2*n_replan={2 * self.n_replan}")
        self.runtime_to_pi05_keys = {v: k for k, v in VR.PI05_TO_RUNTIME_IMAGE_KEYS.items()}
        phys = adapter.jenv.physics
        self.lo = np.asarray(phys.model.actuator_ctrlrange[:, 0], dtype="float64")
        self.hi = np.asarray(phys.model.actuator_ctrlrange[:, 1], dtype="float64")
        self.clip_stats = {"n_values": 0, "n_clipped": 0, "max_clip_magnitude": 0.0, "raw_absmax": 0.0}
        self.capture = PBG.PromptCapture(self.preprocess, keep_last_n=int(keep_last_n)).attach()
        self.weights_identity = weights_identity or {}
        wsha = str(self.weights_identity.get("model_safetensors_sha256") or "unverified")[:12]
        self.policy_version = f"pi05_base_zero_sft@{wsha}"
        self.stats_version = VR.STATS_VERSION_ABSENT
        self.g = 0
        self.n_calls = 0
        self.inference_wall_s_total = 0.0

    def reset(self, seed: int) -> None:
        self.g = 0

    def select_chunk(self, obs) -> VR.ActionChunk:
        import torch
        g = self.g
        self.g += 1
        H, n = self.chunk_size, self.n_replan
        batch = {}
        for rt_key, arr in (obs.images or {}).items():
            pi_key = self.runtime_to_pi05_keys.get(rt_key, rt_key)
            batch[pi_key] = torch.from_numpy(np.asarray(arr, dtype="float32"))
        batch["observation.state"] = torch.from_numpy(np.asarray(obs.state, dtype="float32"))
        batch["task"] = self.task_text
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        b = self.preprocess(batch)
        with torch.inference_mode():
            raw = self.policy.predict_action_chunk(b)
        raw = self.postprocess(raw)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        wall = time.perf_counter() - t0
        self.n_calls += 1
        self.inference_wall_s_total += wall
        c = raw.detach().to("cpu").numpy()
        if c.ndim == 3:
            c = c[0]
        if c.shape[0] != H:
            raise RuntimeError(f"chunk 长度 {c.shape[0]} != H {H} ⇒ 队列语义与 runtime 的三槽不一致，停下报 D")
        rows = [self.zs.adapt_action(r, self.lo, self.hi, self.clip_stats).tolist() for r in c]
        return VR.ActionChunk(
            request_id="placeholder", chunk_index=-1, chunk_id=f"pi05-chunk-{g}", lease_generation=-1,
            epoch=0, actions=_Rows(rows), created_at_frame=-1, planned_frames=(-1, -1),
            slot_c=tuple(range(0, n)), slot_e=tuple(range(n, 2 * n)), slot_d=tuple(range(2 * n, H)),
            dt_s=self.adapter.dt_s, control_hz=self.adapter.control_hz, n_replan=n, chunk_size=H,
            inference_wall_s=wall, deadline_frame=-1, deadline_s=-1.0,
            policy_version=self.policy_version, stats_version=self.stats_version,
            shim_sha256_12=self.adapter.shim.shim_sha256_12(), representation_version="placeholder")

    def identity(self) -> dict:
        return {"kind": "pi05_base_zero_sft", "policy_version": self.policy_version,
                "stats_version": self.stats_version,
                "stats_version_note": ("π₀.₅ base 不携带 normalizer stats（裁定 44.1/49.2）⇒ 恒 `NONE`；"
                                       "runtime 会硬隔离 td/bc 资格，这是**预期形态**"),
                "chunk_size": self.chunk_size, "n_action_steps": self.n_action_steps,
                "max_action_dim": self.max_action_dim,
                "num_inference_steps": int(getattr(self.cfg, "num_inference_steps", -1) or -1),
                "device": self.device, "load_info": self.load_info,
                "weights_identity": self.weights_identity,
                "reused_build_policy_from": "scripts/a2_pi05_zeroshot_eval.py::build_policy",
                "reused_adapt_action_from": "scripts/a2_pi05_zeroshot_eval.py::adapt_action",
                "action_adaptation_status": ("assumed_from_convention（π₀.₅ base ckpt 不携带 embodiment "
                                             "槽位语义，`runs/vla/a2_pi05_contract_20260929/contract.json` "
                                             "的 q2/q3 = unknown）⇒ 32→14 的映射是**假设**，裁剪失真已实测登记"),
                "clip_stats": dict(self.clip_stats),
                "runtime_to_pi05_image_keys": dict(self.runtime_to_pi05_keys),
                "n_inference_calls": self.n_calls,
                "inference_wall_s_total": round(self.inference_wall_s_total, 3)}


# ══════════════════════════ ④ 单局 ══════════════════════════
HOLD_STATS_VERSION = "s4b_gpu_plumbing_check@not_a_claim"


def make_policy_factory(args, reuse, wident: dict):
    """策略工厂：**必须绑定当局的活适配器**（`HoldPolicy` 要读 `adapter.hold`，而 `hold` 只在
    `reset()` 之后才有值 ⇒ 拿一个已 close 的临时适配器去构造 = 运行时抛「hold 在 reset 之前被读取」）。

    π₀.₅ 只加载**一次**（~60 s），跨局复用同一个 policy 对象；`task_text` 按方向改写
    （`policy_version`/`stats_version` 不动 ⇒ 不会触发 runtime 的「episode 中途换版本」牙）。
    """
    zs = reuse["zs"]
    cache: dict = {}

    def factory(ad, direction: str):
        if args.policy == "pi05":
            p = cache.get("pi05")
            if p is None:
                p = Pi05ChunkPolicy(adapter=ad, zs=zs, weights_dir=args.weights_dir_resolved,
                                    tokenizer_dir=args.tokenizer_dir, device=args.device,
                                    task_text=args.task_by_direction[direction],
                                    n_replan=args.n_replan, weights_identity=wident)
                cache["pi05"] = p
                print(f"[model] loaded in {p.load_info.get('load_s')}s H={p.chunk_size} "
                      f"n_action_steps={p.n_action_steps} policy_version={p.policy_version}", flush=True)
            p.task_text = args.task_by_direction[direction]
            return p
        if "mod" not in cache:
            cache["mod"] = load_module_by_path("a2_s4b_outcome_ledger_verify",
                                               "scripts/a2_s4b_outcome_ledger_verify.py")
        return cache["mod"].HoldPolicy(ad, n_replan=args.n_replan, stats_version=HOLD_STATS_VERSION)

    factory.cache = cache
    return factory


def policy_identity_of(policy) -> dict:
    if hasattr(policy, "identity"):
        return policy.identity()
    return {"kind": "deterministic_hold", "policy_version": getattr(policy, "policy_version", None),
            "stats_version": getattr(policy, "stats_version", None),
            "chunk_size": getattr(policy, "chunk_size", None),
            "note": ("CPU 管路自检用；`stats_version` 是**测试输入**，不是任何真实 stats 的声明"),
            "reused_from": "scripts/a2_s4b_outcome_ledger_verify.py::HoldPolicy"}


def run_episode(*, ep_index: int, direction: str, seed: int, args, policy, ledger, window,
                reuse, out_dir: pathlib.Path) -> dict:
    zs = reuse["zs"]
    task_text = args.task_by_direction.get(direction) or TASK_BY_DIRECTION[direction]
    ad = VR.GymAlohaJudgedAdapter(direction=direction, image_size=args.image_size, render=True)
    if callable(policy):
        policy = policy(ad, direction)
    ep_id = f"s4b-gpu-{direction}-{ep_index:02d}"
    rt_kw: dict = dict(episode_id=ep_id, goal_id=ad.goal_id, epoch=0, n_replan=args.n_replan,
                       dt_s=ad.dt_s, late_policy="hold", prime_mode="hold", ledger=ledger,
                       shim_sha256_12=ad.jenv.timing.get("shim_sha256_12", "unspecified"),
                       async_overlap=False, max_episode_steps=ad.max_episode_steps)
    if args.cotenant_interval_s > 0:
        rt_kw["cotenant_sampler"] = window.runtime_cotenant_sample
        rt_kw["cotenant_sample_interval_s"] = args.cotenant_interval_s
    rt = VR.ChunkedVlaRuntime(policy, ad, **rt_kw)
    load_before = PBG.gpu_window_readings(extra={"phase": f"ep{ep_index}_before"})
    prompt_lo = len(policy.capture.prompts) if getattr(policy, "capture", None) else 0
    n_calls_before = getattr(policy, "n_calls", None)
    t0 = time.perf_counter()
    rt.reset(seed=seed)
    max_frames = min(int(args.max_frames or ad.max_episode_steps), int(ad.max_episode_steps))
    transitions: list[dict] = []
    prev_oc = "__none__"
    stop_reason = "frame_budget_exhausted"
    frames = 0
    while frames < max_frames:
        sr = rt.step()
        frames += 1
        oc = sr.info.get("outcome_class")
        if oc != prev_oc:
            transitions.append({"abs_frame": sr.abs_frame, "outcome_class": oc,
                                "env_reward": sr.info.get("env_reward"),
                                "geometric_success": sr.info.get("geometric_success"),
                                "env_is_success": sr.info.get("env_is_success"),
                                "hold_steps": sr.info.get("hold_steps")})
            prev_oc = oc
        if sr.terminated or sr.truncated:
            stop_reason = ("env_terminated(is_success==reward==4)" if sr.terminated
                           else "env_truncated(TimeLimit)")
            break
        if oc == "success" and args.stop_on_geometric_success:
            stop_reason = "geometric_success__mirrors_c2_env_done_semantics"
            break
    wall_s = time.perf_counter() - t0
    renderer_at_end = ad.measure_renderer_at_end()
    out = rt.finalize_from_env_judgment(ad, ledger=ledger)
    roundtrip = VR.s4b_outcome_from_ledger(ledger, episode_id=ep_id)
    load_after = PBG.gpu_window_readings(extra={"phase": f"ep{ep_index}_after"})
    nr0, nr1 = load_before.get("nr_throttled"), load_after.get("nr_throttled")

    # ---- 运行时 prompt 牙（同批第 1 件）----
    cap = getattr(policy, "capture", None)
    if cap is not None:
        prompt_slice = list(cap.prompts[prompt_lo:])
        prompt_audit = cap.audit(prompts=prompt_slice)
        prompt_audit["n_prompts_in_this_episode"] = len(prompt_slice)
        prompt_audit["prompt_index_range"] = [prompt_lo, len(cap.prompts)]
        # `aggregate_prompt_audit()` 只给并集与计数；`pad_vector` 的旁证（**pad 之后的长度**）
        # 要逐条取 ⇒ 这里再走一遍 `audit_prompt_text()`（同一实现，不另造口径）。
        per = [PBG.audit_prompt_text(p) for p in prompt_slice]
        dims = sorted({int(a["state_dim_after_pad"]) for a in per
                       if isinstance(a.get("state_dim_after_pad"), int)})
        tmins = [int(a["token_min"]) for a in per if isinstance(a.get("token_min"), int)]
        tmaxs = [int(a["token_max"]) for a in per if isinstance(a.get("token_max"), int)]
        sat_union: set[int] = set()
        for a in per:
            sat_union.update(int(i) for i in (a.get("saturated_bin_255_dims") or []))
        prompt_audit.update({
            "state_dim_after_pad_values": dims,
            "pad_dim_matches_max_state_dim_all": (
                None if not per else all(bool(a.get("pad_dim_matches_max_state_dim")) for a in per)),
            "expected_state_dim_after_pad": PBG.MAX_STATE_DIM,
            "token_min_over_prompts": min(tmins) if tmins else None,
            "token_max_over_prompts": max(tmaxs) if tmaxs else None,
            "n_saturated_bin_255_total": sum(int(a.get("n_saturated_bin_255") or 0) for a in per),
            "saturated_bin_255_dims_union": sorted(sat_union),
            "saturation_is_legal_note": ("bin 255 = `x ≥ 1` 的**合法**优雅饱和（`processor_pi05.py:77` "
                                         "的上侧），**不判红**；只逐维登记"),
            "per_prompt_audit_reused": "harness/prompt_bin_guard.audit_prompt_text（同一实现，不另造）",
        })
    else:
        prompt_audit = {"measurement_status": "not_measured", "verdict": None, "value": None,
                        "nonzero_exit_required": False, "n_prompts_in_this_episode": 0,
                        "state_dim_after_pad_values": [],
                        "why": ("本臂是 `--policy hold` 的 **CPU 管路自检**，不跑 π₀.₅ 推理 ⇒ 没有 prompt 可审。"
                                "`not_measured` ≠ 「审过且 0 命中」（三值纪律）"),
                        "arm_is_not_authoritative": True}

    timing = rt.timing_report()
    rec = {
        "episode_id": ep_id, "episode_index": ep_index, "direction": direction, "seed": seed,
        "goal_id": ad.goal_id, "task_text": task_text,
        "task_text_same_as_g3": TASK_TEXT_SAME_AS_DIRECTION.get(direction),
        "n_control_frames": frames, "max_frames_allowed": max_frames, "stop_reason": stop_reason,
        "wall_s": round(wall_s, 2),
        "outcome": out.as_dict(),
        "ledger_roundtrip": roundtrip,
        "renderer_class_three_points": ad.renderer_ledger.snapshot(),
        "renderer_measurement_mechanism": {
            "at_start": ad.start_renderer_measurement, "in_run": ad.in_run_renderer_measurement,
            "at_end": renderer_at_end,
            "rule": ("三点各自独立测（真实渲染后在**同一调用栈**读 `glGetString`）；读到 NULL 一律 "
                     "`not_measured_no_gl_context`，**不许**记成 measured、也**不许**拿起点顶替终点"),
        },
        "n_renders_in_run": ad.n_renders_in_run,
        "isolation_reasons": list(rt.isolation_reasons),
        "td_eligible": out.training_view.td_eligible, "bc_eligible": out.training_view.bc_eligible,
        "timing_report": timing,
        "load_pair": {"before": load_before, "after": load_after,
                      "nr_throttled_delta": (None if (nr0 is None or nr1 is None) else int(nr1) - int(nr0)),
                      "pairing_rule": "裁定 46.4/53.6/85.7：延迟/吞吐数字成对带 loadavg(3 点)+nr_throttled"},
        "prompt_audit": prompt_audit,
        "representation_version": rt.representation_version,
        "n_inference_calls_this_episode": (
            None if n_calls_before is None
            else (int(getattr(policy, "n_calls", 0)) - int(n_calls_before))),
        "n_chunk_requests_committed": timing["n_chunks_committed"],
        "outcome_transitions": transitions,
        "env_manifest": ad.manifest(),
        "policy_identity": policy_identity_of(policy),
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "gpu_stats": zs.gpu_stats(),
        "load_snapshot_reuse": {"before": zs.load_snapshot(), "note": "复用 G3 的 load_snapshot()，不另造"},
    }
    ad.close()
    return rec


TASK_TEXT_SAME_AS_DIRECTION = dict(TASK_TEXT_SAME_AS_G3)


# ══════════════════════════ ⑤ 发现（findings）与总判 ══════════════════════════
class Findings:
    """三值纪律 + 归因强度：每条发现都有 `verdict ∈ {GREEN,RED,not_measured}`、`blocking`、
    `attribution_strength`（**只能** `inferred`，裁定 76.1）。"""

    def __init__(self):
        self.items: list[dict] = []

    def add(self, fid: str, *, verdict: str, blocking: bool, subject: str, evidence=None,
            attribution: str = "inferred", ruling: str = "", why: str = ""):
        if verdict not in ("GREEN", "RED", "not_measured"):
            raise ValueError(f"verdict {verdict!r} 不在三值词表")
        if attribution != "inferred" and verdict == "RED":
            attribution = "inferred"          # 裁定 76.1：不得写 confirmed
        self.items.append({"id": fid, "verdict": verdict, "blocking": bool(blocking),
                           "red_subject": (subject if verdict == "RED" else None),
                           "attribution_strength": attribution, "ruling": ruling,
                           "why": why, "evidence": evidence})
        return self.items[-1]

    @property
    def blocking_red(self) -> list[dict]:
        return [x for x in self.items if x["verdict"] == "RED" and x["blocking"]]

    @property
    def non_blocking_red(self) -> list[dict]:
        return [x for x in self.items if x["verdict"] == "RED" and not x["blocking"]]

    def summary(self) -> dict:
        return {"n_findings": len(self.items),
                "n_green": sum(1 for x in self.items if x["verdict"] == "GREEN"),
                "n_red": sum(1 for x in self.items if x["verdict"] == "RED"),
                "n_not_measured": sum(1 for x in self.items if x["verdict"] == "not_measured"),
                "n_blocking_red": len(self.blocking_red),
                "n_non_blocking_red": len(self.non_blocking_red),
                "blocking_red_ids": [x["id"] for x in self.blocking_red],
                "non_blocking_red_ids": [x["id"] for x in self.non_blocking_red]}


# ══════════════════════════ ⑥ main ══════════════════════════
def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="A2 / T-A2-6：S4b 的 GPU·EGL 权威臂")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--policy", choices=["pi05", "hold"], default="pi05",
                    help="pi05=真实模型（需 GPU 窗口）；hold=CPU 管路自检（**不是权威臂**）")
    ap.add_argument("--weights-dir",
                    default="runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044")
    ap.add_argument("--tokenizer-dir",
                    default="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/"
                            "hf-cache/modelscope/google/paligemma-3b-pt-224")
    ap.add_argument("--weights-receipt",
                    default="runs/vla/a2_pi05_contract_20260929/ckpt_readonly_reverification.json")
    ap.add_argument("--skip-weights-rehash", action="store_true",
                    help="不复算 14.4 GB safetensors 的 sha256（⇒ 该身份记 not_measured）")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--directions", default="right_to_left,left_to_right")
    ap.add_argument("--n-episodes", type=int, default=3, help="**每个方向**的局数（速度优先 ⇒ 默认 3）")
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--n-replan", type=int, default=VR.MAINLINE_N_REPLAN)
    ap.add_argument("--max-frames", type=int, default=0, help="0 = 用 env 注册的 300（裁定 65-2）")
    ap.add_argument("--task-right-to-left", default=TASK_BY_DIRECTION["right_to_left"])
    ap.add_argument("--task-left-to-right", default=TASK_BY_DIRECTION["left_to_right"])
    ap.add_argument("--no-stop-on-geometric-success", dest="stop_on_geometric_success",
                    action="store_false", default=True)
    ap.add_argument("--mujoco-gl", default=None, help="默认沿用环境（EGL 前缀激活后应为 egl）")
    ap.add_argument("--cotenant-interval-s", type=float, default=0.0,
                    help=">0 才把三网采样挂到 runtime 关键路径（会改变延迟口径，见 AUTHORITATIVE_LATENCY_BAND.note）")
    ap.add_argument("--sampler-interval-s", type=float, default=2.0,
                    help="窗口级后台共租采样间隔（**不在**关键路径上）")
    ap.add_argument("--allow-cotenant", action="store_true",
                    help="显式放行起跑前的三网命中（⇒ 本窗口数字自动标 contaminated_candidate）")
    ap.add_argument("--refusal-strictness", choices=["narrow", "strict"], default="narrow")
    ap.add_argument("--declaration-line", type=int, default=None,
                    help="daily_report.md 里的 GPU 窗口申报行号（pi05 臂**必填**）")
    ap.add_argument("--skip-gpu-preflight", action="store_true",
                    help="**只**允许与 --policy hold 同用（CPU 管路自检不上卡）")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    args.task_by_direction = {"right_to_left": args.task_right_to_left,
                              "left_to_right": args.task_left_to_right}
    directions = [d.strip() for d in str(args.directions).split(",") if d.strip()]
    bad = [d for d in directions if d not in TASK_BY_DIRECTION]
    if bad:
        print(f"[usage] 未知 direction {bad}，可选 {sorted(TASK_BY_DIRECTION)}", file=sys.stderr)
        return EXIT_USAGE
    if args.policy == "pi05" and args.skip_gpu_preflight:
        print("[usage] --skip-gpu-preflight 只能与 --policy hold 同用（上卡臂必须过起跑前拒绝逻辑）",
              file=sys.stderr)
        return EXIT_USAGE
    if args.mujoco_gl:
        os.environ["MUJOCO_GL"] = args.mujoco_gl
    _w = pathlib.Path(args.weights_dir)
    args.weights_dir_resolved = str(_w if _w.is_absolute() else (REPO / _w))
    if args.policy == "pi05" and not pathlib.Path(args.weights_dir_resolved).exists():
        print(f"[usage] 权重目录不存在：{args.weights_dir_resolved}", file=sys.stderr)
        return EXIT_USAGE
    if args.policy == "pi05" and not pathlib.Path(args.tokenizer_dir).exists():
        print(f"[usage] tokenizer 目录不存在：{args.tokenizer_dir}", file=sys.stderr)
        return EXIT_USAGE

    out_dir = REPO / args.out_dir if not pathlib.Path(args.out_dir).is_absolute() else pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    authoritative = (args.policy == "pi05")
    arm_label = ("gpu_egl_authoritative" if authoritative else "cpu_osmesa_plumbing_check")

    reuse = load_reuse()
    a2l, zs, calib = reuse["a2l"], reuse["zs"], reuse["calib"]
    print(f"[reuse] 三网探测器={reuse['identity']['three_net_detector']['sha256_12']} "
          f"policy 构造={reuse['identity']['policy_builder_and_action_adapter']['sha256_12']} "
          f"判定层={reuse['identity']['judgment_module']['sha256_12']}", flush=True)

    # ---- ① 先申报后上卡 ----
    decl = check_declaration(args.declaration_line, required=authoritative)
    if authoritative and decl.get("verdict") != "GREEN":
        print(f"[refuse] 未核到 A2 的 GPU 窗口申报行（--declaration-line={args.declaration_line}）"
              f"⇒ 不上卡（exit {EXIT_USAGE}）。核到的事实：{json.dumps(decl, ensure_ascii=False)[:400]}",
              file=sys.stderr)
        write_json(out_dir / "refused_no_declaration.json", decl)
        return EXIT_USAGE

    # ---- ② 起跑前拒绝逻辑 + 开窗 ----
    window = GpuWindow(out_dir, reuse=reuse, allow_cotenant=args.allow_cotenant,
                       refusal_strictness=args.refusal_strictness,
                       sampler_interval_s=args.sampler_interval_s, arm_label=arm_label,
                       declaration=decl)
    if not args.skip_gpu_preflight:
        try:
            pf = window.preflight()
        except GpuBusyRefusal as exc:
            print(f"[refuse] {exc}", file=sys.stderr)
            return EXIT_REFUSED_GPU_BUSY
        print(f"[preflight] n_foreign_gpu_processes={pf['n_foreign_gpu_processes']} "
              f"gate_ok={pf['yield_gate']['ok']} memory_used_mib="
              f"{(pf['three_net_raw'] or {}).get('memory_used_mib')}", flush=True)
    else:
        window.preflight_doc = {"artifact": "gpu_preflight_three_net", "skipped": True,
                                "why": "--policy hold 的 CPU 管路自检臂**不上卡** ⇒ 不适用（not_applicable，"
                                       "不是「测过且空载」）", "measurement_status": "not_applicable_no_gpu_use"}
    window.open()

    findings = Findings()
    episodes: list[dict] = []
    ledger_path = out_dir / "ledger_s4b_gpu.sqlite"
    ledger = FactLedger(ledger_path)
    policy_identity: dict = {}
    exit_code = EXIT_OK
    try:
        # ---- ③ 权重身份（自己复算 + 与 G1 receipt 对账，裁定 83§7）----
        wident = weights_identity(pathlib.Path(args.weights_dir_resolved),
                                  REPO / args.weights_receipt, skip_rehash=args.skip_weights_rehash)
        factory = make_policy_factory(args, reuse, wident)
        # ---- ④ 逐方向、逐局 ----
        for di, direction in enumerate(directions):
            for k in range(int(args.n_episodes)):
                ep_index = di * 100 + k
                seed = int(args.seed0) + di * 1000 + k
                try:
                    rec = run_episode(ep_index=ep_index, direction=direction, seed=seed, args=args,
                                      policy=factory, ledger=ledger, window=window, reuse=reuse,
                                      out_dir=out_dir)
                except Exception as exc:                                 # noqa: BLE001
                    import traceback
                    tb = traceback.format_exc()
                    findings.add(f"episode_crash:{direction}:{ep_index}", verdict="RED", blocking=True,
                                 subject="episode_crash",
                                 evidence={"error": f"{type(exc).__name__}: {exc}", "traceback": tb[-3000:]},
                                 ruling="—", why="一局崩了 ⇒ 该臂不完整，不许当绿交付")
                    print(f"[ep {direction}#{ep_index}] CRASH {type(exc).__name__}: {exc}", flush=True)
                    continue
                episodes.append(rec)
                if not policy_identity:
                    policy_identity = rec.get("policy_identity") or {}
                write_json(out_dir / f"episode_{direction}_{ep_index:03d}.json", rec)
                o = rec["outcome"]
                print(f"[ep {direction}#{ep_index:03d}] seed={seed} frames={rec['n_control_frames']} "
                      f"stop={rec['stop_reason']} outcome={o['outcome_class']} "
                      f"reward4={o['reward4_success']} geom={o['geometric_success']} "
                      f"cross_check={o['cross_check_verdict']} s4b_red={o['red']} "
                      f"wall={rec['wall_s']}s "
                      f"ms/step={rec['timing_report']['wall_ms_per_ctrl_step']} "
                      f"budget_fraction={rec['timing_report']['budget_fraction']} "
                      f"renderer_end={rec['renderer_class_three_points']['at_end']}",
                      flush=True)
    except Exception as exc:                                             # noqa: BLE001
        import traceback
        findings.add("run_crash", verdict="RED", blocking=True, subject="run_crash",
                     evidence={"error": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc()[-4000:]},
                     why="整轮崩了 ⇒ 不许当绿交付")
        exit_code = EXIT_BLOCKING_RED
    finally:
        renderer_end = None
        if episodes:
            renderer_end = episodes[-1]["renderer_class_three_points"]["points"]["at_end"]
        win = window.close(renderer_at_end=renderer_end,
                           extra={"n_episodes_completed": len(episodes),
                                  "arm_label": arm_label})
        try:
            ledger_stats = ledger.stats()
        except Exception as exc:                                         # noqa: BLE001
            ledger_stats = {"error": f"{type(exc).__name__}: {exc}"}
        ledger.close()
        summary = build_summary(args=args, directions=directions, episodes=episodes, findings=findings,
                                reuse=reuse, window_doc=win, policy_identity=policy_identity,
                                ledger_path=ledger_path, ledger_stats=ledger_stats,
                                authoritative=authoritative, arm_label=arm_label, ts=ts,
                                decl=decl, out_dir=out_dir)
        exit_code = evaluate_findings(summary, findings, episodes, args, authoritative, exit_code,
                                      directions=directions)
        summary["exit_code"] = exit_code
        summary["overall_verdict"] = "RED" if exit_code != EXIT_OK else summary["overall_verdict"]
        ident = write_json(out_dir / "s4b_gpu_run.json", summary)
        summary_art = ident
        print(f"[done] overall={summary['overall_verdict']} exit={exit_code} "
              f"blocking_red={summary['findings_summary']['n_blocking_red']} "
              f"episodes={len(episodes)} artifact={ident['path']} {ident['sha256_12']}", flush=True)
    return exit_code


def weights_identity(wdir: pathlib.Path, receipt_path: pathlib.Path, *, skip_rehash: bool) -> dict:
    """权重身份：**自己复算** sha256 并与 G1 receipt 对账（裁定 83§7 / 94 补单-§三）。

    `model.safetensors` = 14.4 GB ⇒ 复算要 ~14 s（receipt 实测 1063 MB/s）。`--skip-weights-rehash`
    时该字段记 `not_measured`（**不写 receipt 的值冒充复算**）。
    """
    out: dict = {"weights_dir": str(wdir), "weights_dir_exists": wdir.exists(),
                 "receipt_path": str(receipt_path.relative_to(REPO)) if receipt_path.is_relative_to(REPO)
                 else str(receipt_path),
                 "receipt_sha256_12": sha12(receipt_path),
                 "config_json_sha256_12": sha12(wdir / "config.json"),
                 "policy_preprocessor_sha256_12": sha12(wdir / "policy_preprocessor.json"),
                 "policy_postprocessor_sha256_12": sha12(wdir / "policy_postprocessor.json")}
    declared = None
    try:
        rd = json.loads(receipt_path.read_text(encoding="utf-8"))
        for f in rd.get("files") or []:
            if f.get("path") == "model.safetensors":
                declared = {"actual_sha256": f.get("actual_sha256"), "actual_size": f.get("actual_size"),
                            "sha256_match_hf_lfs": f.get("sha256_match_hf_lfs"),
                            "sha256_match_modelscope": f.get("sha256_match_modelscope")}
        out["receipt_license"] = (rd.get("license") or {})
        out["receipt_verdict"] = rd.get("verdict")
    except Exception as exc:                                             # noqa: BLE001
        out["receipt_error"] = f"{type(exc).__name__}: {exc}"
    out["receipt_declared_model_safetensors"] = declared
    if skip_rehash:
        out.update({"model_safetensors_sha256": None, "recomputed": False,
                    "measurement_status": "not_measured",
                    "why": "--skip-weights-rehash ⇒ 不复算 14.4 GB；**不拿 receipt 的值冒充复算**"})
        return out
    st = wdir / "model.safetensors"
    sha, secs, nbytes = sha256_big(st)
    agree = (None if (sha is None or not declared) else bool(sha == declared.get("actual_sha256")))
    out.update({"model_safetensors_sha256": sha, "model_safetensors_bytes": nbytes,
                "recomputed": True, "recompute_seconds": secs,
                "measurement_status": "measured",
                "agrees_with_receipt": agree,
                "agreement_verdict": ("GREEN" if agree else ("not_measured" if agree is None else "RED")),
                "note": "复算值与 G1 receipt 声明值逐字对账；不一致 ⇒ RED（不许静默用其中一份）"})
    return out


def evaluate_findings(summary: dict, findings: Findings, episodes: list[dict], args,
                      authoritative: bool, exit_code: int, *, directions: list[str]) -> int:
    """把产物里的事实翻成 findings（**牙在这里**），再决定退出码。"""
    n_requested = len(directions) * int(args.n_episodes)
    if len(episodes) != n_requested:
        findings.add("incomplete_episodes", verdict="RED", blocking=True, subject="incomplete_episodes",
                     evidence={"requested": n_requested, "completed": len(episodes)},
                     why="局数不齐 ⇒ 该臂不完整（不许拿半份产物当全份）")
    if not episodes:
        findings.add("no_episodes", verdict="RED", blocking=True, subject="empty_set",
                     evidence={"n_episodes": 0}, ruling="裁定 88.3-1",
                     why="空集 ⇒ verdict=null + 非零退出（不许写 0、不许写 GREEN）")
        summary["overall_verdict"] = None
        return EXIT_BLOCKING_RED

    # ---- 四类判定接 ledger：round-trip 每局恰一条 episode_end + outcome_class 一致 ----
    bad_rt = []
    for r in episodes:
        rt = r["ledger_roundtrip"]
        oc = r["outcome"]["outcome_class"]
        ok = (rt.get("measurement_status") == "measured"
              and int(rt.get("n_episode_end_events") or 0) == 1
              and int(rt.get("n_outcome_labels") or 0) >= 1
              and oc in (rt.get("outcome_classes_observed") or []))
        if not ok:
            bad_rt.append({"episode_id": r["episode_id"], "outcome_class": oc,
                           "roundtrip_status": rt.get("measurement_status"),
                           "n_episode_end_events": rt.get("n_episode_end_events"),
                           "n_outcome_labels": rt.get("n_outcome_labels"),
                           "outcome_classes_observed": rt.get("outcome_classes_observed")})
    findings.add("ledger_roundtrip_four_classes", verdict=("GREEN" if not bad_rt else "RED"),
                 blocking=True, subject="ledger_roundtrip_mismatch", evidence={"mismatched": bad_rt},
                 ruling="params:1047", why="四类判定必须**真的**落进 ledger 并能读回，每局恰一条 episode_end")

    # ---- 独立于 reward==4：outcome_source 恒为几何；且有反向臂的 RED 见证 ----
    srcs = {r["outcome"]["outcome_source"] for r in episodes}
    findings.add("outcome_source_is_geometric_only",
                 verdict=("GREEN" if srcs == {VR.OUTCOME_SOURCE_GEOMETRIC} else "RED"), blocking=True,
                 subject="outcome_source_not_geometric", evidence={"observed": sorted(srcs),
                                                                   "forbidden_constant":
                                                                       VR.OUTCOME_SOURCE_REWARD4_FORBIDDEN},
                 ruling="params:1047",
                 why="四类结论只能来自 C2 的几何真值；`reward==4` 只作交叉核验的一侧")

    # ---- 不一致即红：反向臂必须出现 RED，且 red_subject = env_reward_direction_hardcoded ----
    rev = [r for r in episodes if r["direction"] == "left_to_right"]
    fwd = [r for r in episodes if r["direction"] == "right_to_left"]
    if rev:
        rev_red = [r for r in rev if r["outcome"]["red"]]
        subj = {r["outcome"].get("red_subject") for r in rev_red}
        findings.add("reverse_direction_expected_red_witnessed",
                     verdict=("GREEN" if rev_red else "RED"), blocking=False,
                     subject="reverse_arm_no_red_witness",
                     evidence={"n_reverse_episodes": len(rev), "n_red": len(rev_red),
                               "red_subjects": sorted(str(x) for x in subj),
                               "red_classes": sorted({str(r["outcome"].get("red_class")) for r in rev_red})},
                     ruling="裁定 54 / params:1047",
                     why=("env 的 reward==4 写死右→左 ⇒ 反向臂的几何真值与它**必然**不一致；"
                          "RED 照记不降级，归因写在 env 的判据上（不是 policy 能力、不是 A2 的运行时）"))
    else:
        findings.add("reverse_direction_expected_red_witnessed", verdict="not_measured", blocking=False,
                     subject=None, evidence={"n_reverse_episodes": 0},
                     why="本轮没跑反向臂 ⇒ 「不一致即红」的反向见证 not_measured（不是「没有不一致」）")
    # 正向臂若出现 RED ⇒ 阻塞（那不是预期形态）
    fwd_red = [r for r in fwd if r["outcome"]["red"]]
    findings.add("forward_direction_no_unexpected_red",
                 verdict=("GREEN" if not fwd_red else "RED"), blocking=True,
                 subject="forward_arm_unexpected_red",
                 evidence=[{"episode_id": r["episode_id"], "red_subject": r["outcome"].get("red_subject"),
                            "red_class": r["outcome"].get("red_class"),
                            "geometric_success": r["outcome"].get("geometric_success"),
                            "reward4_success": r["outcome"].get("reward4_success"),
                            "cross_check_verdict": r["outcome"].get("cross_check_verdict")}
                           for r in fwd_red],
                 ruling="裁定 54",
                 why="正向臂的不一致**不是**预期形态（可能是 flick/擦碰的伪成功）⇒ 阻塞，报 D")

    # ---- 视觉通道：不得静默退化 ----
    vis = [r for r in episodes if any("vision_channel_absent" in x for x in r["isolation_reasons"])]
    findings.add("vision_channels_present", verdict=("GREEN" if not vis else "RED"), blocking=True,
                 subject="vision_channel_absent",
                 evidence=[{"episode_id": r["episode_id"], "isolation_reasons": r["isolation_reasons"]}
                           for r in vis],
                 ruling="任务书：不许自行退化成状态输入小模型",
                 why="缺图像键 ⇒ 硬隔离；本臂是**视觉**臂，出现隔离就是臂失效")

    # ---- 同批第 1 件：运行时 prompt 牙 ----
    audits = [r["prompt_audit"] for r in episodes]
    n_prompts = sum(int(a.get("n_prompts_in_this_episode") or 0) for a in audits)
    illegal = [a for a in audits if (a.get("n_prompts_red") or 0) or a.get("verdict") == "RED"]
    probes = {((a.get("pattern_coverage_probe") or {}).get("auditor_self_verdict")) for a in audits}
    if not authoritative:
        findings.add("runtime_prompt_illegal_bin_tooth", verdict="not_measured", blocking=False,
                     subject=None, evidence={"n_prompts": n_prompts},
                     why="CPU 管路自检臂不跑 π₀.₅ ⇒ 运行时 prompt 牙 not_measured")
    elif n_prompts == 0:
        findings.add("runtime_prompt_illegal_bin_tooth", verdict="RED", blocking=True,
                     subject="prompt_capture_hook_did_not_fire",
                     evidence={"n_prompts": 0, "audits": [{k: a.get(k) for k in
                                                           ("hook_error", "tokenizer_step_seen",
                                                            "n_hook_captures", "step_class_hits")}
                                                          for a in audits]},
                     ruling="裁定 88.3-1（空集 ⇒ null + 非零退出）",
                     why="跑过推理却一条 prompt 都没抓到 ⇒ 牙**未测**，不许读成「0 命中」")
    else:
        findings.add("runtime_prompt_illegal_bin_tooth",
                     verdict=("RED" if illegal else "GREEN"), blocking=False,
                     subject="prompt_illegal_bin_minus1_at_runtime",
                     evidence={"n_prompts_audited": n_prompts, "n_prompts_with_illegal_bin": len(illegal),
                               "per_episode": [{
                                   "episode_id": r["episode_id"],
                                   "n_prompts": r["prompt_audit"].get("n_prompts_in_this_episode"),
                                   "n_prompts_red": r["prompt_audit"].get("n_prompts_red"),
                                   "verdict": r["prompt_audit"].get("verdict"),
                                   "illegal_bin_dims_union": r["prompt_audit"].get("illegal_bin_dims_union"),
                                   "n_illegal_bin_minus1": r["prompt_audit"].get("n_illegal_bin_minus1"),
                                   "red_classes": r["prompt_audit"].get("red_classes"),
                                   "token_min_over_prompts": r["prompt_audit"].get("token_min_over_prompts"),
                                   "token_max_over_prompts": r["prompt_audit"].get("token_max_over_prompts"),
                                   "n_saturated_bin_255_total":
                                       r["prompt_audit"].get("n_saturated_bin_255_total"),
                                   "state_dim_after_pad_values":
                                       r["prompt_audit"].get("state_dim_after_pad_values"),
                               } for r in episodes],
                               "auditor_self_verdicts": sorted(str(x) for x in probes)},
                     ruling="裁定 94 补单-§一-1（§23.2）",
                     attribution="inferred",
                     why=("**这是发现不是故障**：π₀.₅ base 的 `normalizer_processor.config.features={}` ⇒ "
                          "pass-through ⇒ 原始 rad 量纲的 state 直接进 `digitize`，`x < −1` 落 bin `-1` "
                          "（`processor_pi05.py:77` 的结构不对称：`x ≥ 1 → 255` 是合法饱和、"
                          "`x < −1 → −1` 是**非法 token 静默进 prompt**）。归因强度只能 inferred。"))
        findings.add("prompt_auditor_pattern_coverage_self_proof",
                     verdict=("GREEN" if probes == {"GREEN"} else "RED"), blocking=True,
                     subject="auditor_pattern_coverage_self_red",
                     evidence={"auditor_self_verdicts": sorted(str(x) for x in probes)},
                     ruling="裁定 93.8 / 93.5",
                     why="审计器必须自证模式覆盖：注入的坏形态抓不到 ⇒ 审计器自己红")

    # ---- 同批第 2 件：pad_vector 缺口 = not_measured ----
    pad_dims = sorted({int(v) for r in episodes
                       for v in (r["prompt_audit"].get("state_dim_after_pad_values") or [])}) \
        if authoritative else []
    pad = PBG.pad_vector_gap_registration(measured=False,
                                          evidence={"runtime_state_dim_after_pad": (pad_dims or None)})
    summary["pad_vector_gap_registration"] = pad
    findings.add("pad_vector_gap_registered_not_measured", verdict="not_measured", blocking=False,
                 subject=None,
                 evidence={"value": pad["value"], "safe": pad["safe"],
                           "runtime_state_dim_after_pad": pad_dims,
                           "must_not_be_written_as": pad["must_not_be_written_as"]},
                 ruling="裁定 94 补单-§一-2 / 88.3-1",
                 why="D 未测过这一维 ⇒ `not_measured`、`value=null`、`safe=null`；**不得假设安全**")

    # ---- 同批第 3 件：renderer_class 三点（EGL 臂才读得到）----
    rend = [r["renderer_class_three_points"] for r in episodes]
    gl = os.environ.get("MUJOCO_GL")
    end_classes = {(p.get("at_end"), p.get("at_end_measurement_kind")) for p in rend}
    all_null = all(c is None for c, _ in end_classes)
    summary["renderer_class_three_points_aggregate"] = {
        "mujoco_gl": gl, "per_episode": rend,
        "at_end_classes": sorted({str(c) for c, _ in end_classes}),
        "at_end_measurement_kinds": sorted({str(k) for _, k in end_classes}),
        "all_points_null": all_null,
        "backfill_from_at_start_forbidden": True,
        "c4_piggyback_evidence_for_e": [p.get("c4_piggyback_evidence_for_e") for p in rend],
        "c4_ruling": "params:1412 `c4_reverify_piggybacks_no_window`（搭本窗口的便车，不单开窗口）",
        "e_c4_third_party_evidence": (
            {"available": bool(not all_null), "renderer_class": sorted({str(c) for c, _ in end_classes}),
             "meaning": ("读到 `nvidia_gpu` ⇒ E 的自有前缀 EGL 改动无害（`params:1412` 的 C4 复验"
                         "第三方证据，搭本窗口的便车）")}
            if not all_null else
            {"available": False, "renderer_class": None,
             "meaning": ("EGL 臂也读不到 ⇒ E 的 C4 搭车证据**取不到**，如实登记 not_measured，"
                         "不拿 osmesa 臂的值顶替（跨后端不得互搬，裁定 46.4/53.6/71）")}),
    }
    findings.add("renderer_class_three_points",
                 verdict=("not_measured" if all_null else "GREEN"), blocking=False,
                 subject=("renderer_class_unreadable_in_this_arm" if all_null else None),
                 evidence={"mujoco_gl": gl, "at_end_classes": sorted({str(c) for c, _ in end_classes}),
                           "at_end_measurement_kinds": sorted({str(k) for _, k in end_classes})},
                 ruling="裁定 72 / 94 补单-§一-3",
                 why=("三点各自独立测；NULL 一律 not_measured_no_gl_context，不许记成 measured、"
                      "也不许拿起点顶替终点" if not all_null else
                      "本臂三点全 null ⇒ renderer_class 与 E 的 C4 证据都 not_measured"))

    # ---- 延迟/吞吐口径（成对带负载；与权威带**同口径**才可并列）----
    tm = [r["timing_report"] for r in episodes]
    ms = [t["wall_ms_per_ctrl_step"] for t in tm if isinstance(t.get("wall_ms_per_ctrl_step"), (int, float))]
    bf = [t["budget_fraction"] for t in tm if isinstance(t.get("budget_fraction"), (int, float))]
    comparable = (args.cotenant_interval_s <= 0 and authoritative
                  and int(args.n_replan) == VR.MAINLINE_N_REPLAN)
    summary["timing_authoritative_band_comparison"] = {
        "this_run": {"n_episodes": len(tm),
                     "wall_ms_per_ctrl_step_min": min(ms) if ms else None,
                     "wall_ms_per_ctrl_step_max": max(ms) if ms else None,
                     "budget_fraction_min": min(bf) if bf else None,
                     "budget_fraction_max": max(bf) if bf else None,
                     "all_episodes_within_per_step_budget": (None if not bf else bool(max(bf) <= 1.0)),
                     "overload_flags": [bool(t.get("overload_flag")) for t in tm],
                     "queue_never_drained": [bool(t.get("queue_never_drained")) for t in tm],
                     "caliber": (tm[0].get("caliber") if tm else None),
                     "mujoco_gl": gl,
                     "load_pair_per_episode": [r["load_pair"] for r in episodes]},
        "authoritative_band": AUTHORITATIVE_LATENCY_BAND,
        "caliber_comparable_to_band": bool(comparable),
        "comparability_reason": (
            "同口径：同步阻塞串行 + MUJOCO_GL=egl + n_replan=25 + H=50 + 运行时采样器**未**挂关键路径"
            if comparable else
            f"口径不同（authoritative={authoritative}、cotenant_interval_s={args.cotenant_interval_s}、"
            f"n_replan={args.n_replan}、MUJOCO_GL={gl}）⇒ **不得**与 rep4/rep5 的数值带并列"
            "（裁定 46.4/53.6/71）"),
        "realtime_closed_loop_claim": False,
        "allowed_wording": ("「主线 n_replan=25 同步闭环在预算内」（须带口径 + 负载对 + §15.6 caveat）"
                            if (comparable and bf and max(bf) <= 1.0) else
                            "本窗口不得写「同步闭环在预算内」"),
        "forbidden_wording": ["异步实时闭环", "跑通", "学会", "达标"],
    }
    if comparable and bf:
        findings.add("mainline_sync_loop_within_budget",
                     verdict=("GREEN" if max(bf) <= 1.0 else "RED"), blocking=False,
                     subject="budget_fraction_over_1",
                     evidence={"budget_fraction_max": max(bf), "wall_ms_max": max(ms) if ms else None,
                               "band_rep4": AUTHORITATIVE_LATENCY_BAND["rep4"],
                               "band_rep5": AUTHORITATIVE_LATENCY_BAND["rep5"]},
                     ruling="裁定 75.4（软约束，不判硬失败）/ 75.5",
                     why="`budget_fraction>1` 只置 overload_flag，不判硬失败；本条只登记事实")

    # ---- 裁定 46：能力声明禁令 ----
    summary["capability_claim"] = False
    summary["success_rate_column"] = "not_an_exit_criterion"
    summary["ruling_46"] = RULING_46
    summary["correctness_family_caveat"] = CORRECTNESS_FAMILY_CAVEAT
    findings.add("no_capability_claim", verdict="GREEN", blocking=True, subject=None,
                 evidence={"capability_claim": False,
                           "success_rate_column": "not_an_exit_criterion"},
                 ruling="裁定 46 / 46.6",
                 why="四类分布是契约层证据；G3 的 0/20 已按非能力结论登记，本臂不翻案")

    n_blk = len(findings.blocking_red)
    summary["findings_summary"] = findings.summary()
    summary["overall_verdict"] = ("RED" if (n_blk or exit_code != EXIT_OK) else "GREEN")
    return (EXIT_BLOCKING_RED if (n_blk or exit_code != EXIT_OK) else EXIT_OK)


def build_summary(*, args, directions, episodes, findings, reuse, window_doc, policy_identity,
                  ledger_path, ledger_stats, authoritative, arm_label, ts, decl, out_dir) -> dict:
    dist: dict = {}
    for r in episodes:
        d = dist.setdefault(r["direction"], {"n_episodes": 0, "outcome_class_hist": {},
                                             "cross_check_verdicts": {}, "s4b_red": 0,
                                             "red_subjects": {}, "red_classes": {}})
        d["n_episodes"] += 1
        oc = r["outcome"]["outcome_class"]
        d["outcome_class_hist"][oc] = d["outcome_class_hist"].get(oc, 0) + 1
        cv = str(r["outcome"].get("cross_check_verdict"))
        d["cross_check_verdicts"][cv] = d["cross_check_verdicts"].get(cv, 0) + 1
        if r["outcome"].get("red"):
            d["s4b_red"] += 1
            sj = str(r["outcome"].get("red_subject"))
            cl = str(r["outcome"].get("red_class"))
            d["red_subjects"][sj] = d["red_subjects"].get(sj, 0) + 1
            d["red_classes"][cl] = d["red_classes"].get(cl, 0) + 1
    empty = not episodes
    return {
        "artifact": "a2_s4b_pi05_gpu_run",
        "generated_at": now_iso(), "run_ts": ts,
        "generator": "scripts/a2_s4b_pi05_gpu_run.py",
        "generator_identity": reuse["identity"]["this_script"],
        "task": "T-A2-6 / S4b（GPU·EGL 权威臂）",
        "criterion_verbatim": CRITERION_VERBATIM,
        "handoff": HANDOFF,
        "arm_label": arm_label,
        "authoritative_gpu_arm": bool(authoritative),
        "caliber": {
            "mujoco_gl": os.environ.get("MUJOCO_GL"),
            "egl_vendor_library_filenames": os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
            "ld_library_path_head": (os.environ.get("LD_LIBRARY_PATH") or "").split(":")[:2],
            "pyopengl_platform": os.environ.get("PYOPENGL_PLATFORM"),
            "device": args.device, "policy_kind": args.policy,
            "directions": directions, "n_episodes_per_direction": int(args.n_episodes),
            "n_replan": int(args.n_replan), "chunk_size_H": VR.MAINLINE_CHUNK_SIZE,
            "dt_s": VR.MAINLINE_DT_S, "control_hz": VR.MAINLINE_CONTROL_HZ,
            "max_episode_steps": VR.MAINLINE_MAX_EPISODE_STEPS,
            "episode_horizon_s": VR.MAINLINE_EPISODE_HORIZON_S,
            "published_gym_aloha_caliber": VR.PUBLISHED_GYM_ALOHA_CALIBER,
            "timeout_isolation_scope": VR.TIMEOUT_ISOLATION_SCOPE,
            "timeout_ruling": VR.TIMEOUT_RULING,
            "morphology": MORPHOLOGY, "env_id": VR.ENV_ID,
            "image_size": int(args.image_size),
            "task_by_direction": dict(args.task_by_direction),
            "task_text_caliber": ("a2_choice_not_validated_on_base_ckpt（反向臂的任务文本是 A2 换的；"
                                  "base ckpt 对两句的响应差异**未被测过**）"),
            "not_comparable_with": ["CPU osmesa 臂（a2_s4b_outcome_ledger_verify.py）",
                                    "G3 的 n_action_steps=50 队列语义（a2_pi05_zeroshot_eval.py）"],
            "authority_note": ("本臂是 S4b 的**权威**臂（EGL + 真实 π₀.₅）；CPU 臂只承载闸与变异体"
                               "（口径不得互搬，裁定 46.4/53.6/71）") if authoritative else
                              ("**CPU 管路自检臂**：只证明接线通，不承载任何权威数字"
                               "（不是 GPU/EGL 口径，不得与权威带并列）"),
        },
        "reused_not_reimplemented": reuse["identity"],
        "bin_constant_caliber_not_reestablished": BIN_CONSTANT_CALIBER_NOT_REESTABLISHED,
        "judgment_layer": {
            "authority": VR.S4B_JUDGMENT_AUTHORITY, "module": VR.S4B_JUDGMENT_MODULE,
            "identity": reuse["identity"]["judgment_module"], "gate": reuse["identity"]["judgment_gate"],
            "handoff_declared_values": reuse["identity"]["handoff_declared_values_for_comparison"],
            "recomputed_by_a2": True,
            "not_reimplemented_here": ("四类结论、cross_check()、ledger_label_kwargs() 全部**直接调 C2 的"
                                       "方法对象**；本脚本没有任何判定阈值常量"),
        },
        "gpu_window": window_doc,
        "gpu_window_declaration": decl,
        "policy": policy_identity,
        "ledger": {"path": str(ledger_path.relative_to(REPO)) if ledger_path.is_relative_to(REPO)
                           else str(ledger_path),
                   "sha256_12": sha12(ledger_path), "stats": ledger_stats,
                   "admission_declared": VR.S4B_LEDGER_ADMISSION,
                   "api_used": ["append_label", "append_event", "append_frame", "labels()", "events()"],
                   "not_modified": "harness/ledger.py（冻结面，只 import）"},
        "episodes": [{k: v for k, v in r.items() if k not in ("env_manifest",)} for r in episodes],
        "episode_files": [f"episode_{r['direction']}_{r['episode_index']:03d}.json" for r in episodes],
        "env_manifest_last_episode": (episodes[-1]["env_manifest"] if episodes else None),
        "aggregate": {
            "n_episodes_requested": len(directions) * int(args.n_episodes),
            "n_episodes_completed": len(episodes),
            "outcome_class_distribution_by_direction": dist,
            "aggregate_verdict_if_empty": (None if not empty else "GREEN"),
            "empty_set_rule": ("空集 ⇒ `null` + 非零退出（裁定 88.3-1）；**不许**写 0、不许写 GREEN"
                               if empty else "非空"),
            "measurement_status": ("not_measured" if empty else "measured"),
        },
        "findings": findings.items,
        "findings_summary": findings.summary(),
        "overall_verdict": None,
        "three_value_discipline": {
            "vocabulary": ["GREEN(阳性)", "RED(阴性)", "not_measured"],
            "empty_set": "null + 非零退出",
            "reading_failure_is_not_measurement_of_absence": True,
            "red_line": "absence_of_measurement_is_not_measurement_of_absence",
        },
        "banned_words": ["跑通", "学会", "达标"],
        "python": sys.version.split()[0],
    }


if __name__ == "__main__":
    sys.exit(main())
