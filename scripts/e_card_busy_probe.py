"""E 的 `card_busy()` 修法验证探针（裁定 96.1-③ · **纯 CPU · 不上卡 · 不需窗口**）。

修的是什么（F 实测、D 已裁）：共用占卡判定的 **cmdline 网**（网③）两档都在做**字面量匹配**，
于是「只在文本里提到 GPU 关键字」的纯 CPU 进程会被判成占卡。F 的只读探针实测两起
（`runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json` = 74 ln `59fca05a6f68`）：
宽档命中 PID 214244（那是在**改文件**，cmdline 里带 `scripts/a2_…` 字面量）。后果具体：
A2 按裁定 94.9-1② 要在**起跑那一刻**实测三网 ⇒ 窗口被判 `contaminated`（D 不认数字）或被
起跑前拒绝逻辑挡下（`exit 3`）⇒ 白跑一轮，而裁定 95.2 的六步序列第 1–3 步全部要上卡。

修法（D 裁：窄档 = **真实执行形态 ∧ 关键字**，不是裸关键字；并排除 `pcpu≈0` 的闲置进程；
宽档同理）落在 `scripts/e_mainline_render_calib.py` 的 `classify_cmdline()` /
`other_line_gpu_intent()` / `card_busy()`；网①（`compute-apps`）与网②（`/dev/nvidia*` fd）
**源码一字未改**（本件用 ast 逐对象机器比对，见 `nets_untouched`）。

本探针的六条腿（裁定 93.8 要求**两向都装**，只装一向不许报绿 —— 缺陷类 ⑲）：
  R **重放腿**：把「历史上真实出现过的 cmdline」喂给纯函数 `classify_cmdline()`（F 实测的 3 条 +
    23:58 抢卡事故的假体形态 + A2 的延迟臂形态 + `torchrun` 裸启动器 + 冷启动 `env -i /bin/bash`）。
  L **活体腿**：真起进程（**诱饵**：纯 CPU、不导入 torch/mujoco、不开 `/dev/nvidia*`，并把这些
    自证进 `self_report`），在诱饵活着时同时用**旧版模块**与**新版模块**各测一次三网。
  D **新旧差分腿**：文本提及腿必须「旧判忙 ∧ 新不判忙」，真跑腿必须「旧判忙 ∧ 新判忙」
    ⇒ 证明修法**确实改了该改的**，也证明这套断言**不是恒真**（把修法退回去就会红）。
  N **网①②未改腿**：ast 取 7 个对象的源码字节，改前 / 改后逐一相等。
  I **接口未破腿**：`card_busy()` 的 8 个旧键全在（A2 的 `a2_egl_latency_remeasure.py` 按路径
    import 本模块、`e_selfcheck_gate_mutation.py` 会 monkeypatch 它 ⇒ 键名与"非空即计入"的读法不能变）。
  S **现场读数腿**：此刻的三网原文 + 全部候选的分类 + `loadavg` + `nr_throttled`。

**GPU 边界（本件自己也要守）**：只调用 detector 自身的**只读**三网（含 `nvidia-smi` 只读查询），
不起任何 GL/CUDA 上下文、不打开 `/dev/nvidia*`、不分配显存；诱饵自证 `nvidia_fds=[]` /
`nvidia_maps=[]`；探针起止各测一次 `utilization.gpu` / `memory.used` 与 `compute_procs`。

退出码：0 = 六腿全过（含两向）；3 = 任一腿断言失败（含只装一向）；5 = 有 `not_measured`；
2 = 拒绝覆写 / 用法错。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CALIB_REL = "scripts/e_mainline_render_calib.py"
RUN_REL = "runs/infra/e_card_busy_fix_20260930"
BEFORE_REL = f"{RUN_REL}/before_images/e_mainline_render_calib.py.before_96_1_3"
OUT_DIR = REPO / RUN_REL
FIXTURE_REL = "tmp/e_card_busy_probe/scripts/a2_probe_decoy.py"
CITATION_ALGO = "sha256[:12]"
RULING = "裁定 96.1-③（缺陷族：网在匹配「关于 GPU 的文本」，不是「GPU 占用」）"
LEGACY_CARD_BUSY_KEYS = ("busy", "strict", "compute_procs", "nvidia_fd_holders", "cmdline_hits",
                         "cmdline_hits_all_other_line", "excluded_own_pids", "detection_note")
NETS_MUST_BE_UNTOUCHED = ("gpu_snapshot", "other_compute_procs", "nvidia_fd_holders", "_cmdline",
                          "_own_tree", "GPU_INTENT_PATTERNS", "OTHER_LINE_SCRIPT_RE")
DECOY_LIFETIME_S = 2.5
DECOY_SETTLE_S = 0.45


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def ident(path: Path) -> dict:
    """身份三元组（裁定 92.3：`n_lines` = `wc -l` 口径 = 数换行符，不是 `splitlines`）。"""
    raw = path.read_bytes()
    return {"path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
            "sha256_12": hashlib.sha256(raw).hexdigest()[:12], "n_lines": raw.count(b"\n"),
            "n_bytes": len(raw), "citation_algo": CITATION_ALGO, "as_of": now()}


def cpu_ctx() -> dict:
    """每个数字都要带的机器读数（12 核配额：`cpu.cfs_quota_us`=1200000，`nproc`=112 是误导）。"""
    out: dict = {"as_of": now()}
    try:
        out["loadavg"] = Path("/proc/loadavg").read_text().split()[:3]
    except OSError:
        out["loadavg"] = None
    for src in ("/sys/fs/cgroup/cpu/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        try:
            txt = Path(src).read_text()
            for line in txt.splitlines():
                k, _, v = line.partition(" ")
                if k in ("nr_throttled", "throttled_time", "nr_periods"):
                    out[k] = int(v)
            out["cpu_stat_source"] = src
            break
        except (OSError, ValueError):
            continue
    out.setdefault("nr_throttled", None)
    try:
        out["cfs_quota_us"] = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip())
    except (OSError, ValueError):
        out["cfs_quota_us"] = None
    return out


def load_calib(path: Path, name: str):
    """按路径加载**任意文件名**的 calib 副本（前像的后缀不是 `.py`，故用 SourceFileLoader）。"""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


# ── R 腿：重放（纯函数，不起进程）─────────────────────────────────────────────────────
# `source` 一律写明这条 cmdline 是**哪儿来的**（实测件 / 事故记录 / 反漏检构造），
# 免得把"我编的"读成"线上真出现过的"。
REPLAY_LEGS = [
    {"id": "R1_f_measured_text_mention_pid214244",
     "source": "runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json → broad_band_hits[0].cmdline（F 实测 `text_mention_only`）",
     "argv": ["/bin/bash", "-c", "cd", "/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot",
              "&&", "python3", "-", "<<'PY'", "import", "pathlib",
              "r=pathlib.Path(\"scripts/a2_s4b_outcome_ledger_verify.py\");", "u=r.read_text()",
              "old", "=", "'''", "ok", "=", "a"],
     "cpu_ticks": 40, "proc_state": "R",
     "expect": {"classification": "text_mention_only", "counted_narrow": False, "counted_broad": False},
     "why": "在**改文件**（纯 CPU），只是 argv 里带了 `scripts/a2_…` 字面量；`python3` 后面跟的是 `-`，不构成执行形态"},
    {"id": "R2_f_measured_real_pid214254",
     "source": "同上 → broad_band_hits[1].cmdline（F 实测 `real_gpu_work`）",
     "argv": ["timeout", "1800", "/root/venvs/pi05_sim/bin/python",
              "scripts/a2_s4b_outcome_ledger_verify.py", "--out-dir",
              "runs/vla/a2_s4b_outcome_ledger_20260930_dbg7", "--real-frames", "30"],
     "cpu_ticks": 900, "proc_state": "R",
     "expect": {"classification": "real_gpu_work", "counted_narrow": False, "counted_broad": True},
     "why": "`timeout … python scripts/a2_….py` = 真实执行形态 ⇒ 宽档计入；但它不带窄档关键字（这一轮是 CPU 臂），窄档不计入"},
    {"id": "R3_f_measured_real_pid214257",
     "source": "同上 → broad_band_hits[2].cmdline（F 实测 `real_gpu_work`）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/a2_s4b_outcome_ledger_verify.py",
              "--out-dir", "runs/vla/a2_s4b_outcome_ledger_20260930_dbg7", "--real-frames", "30"],
     "cpu_ticks": 700, "proc_state": "R",
     "expect": {"classification": "real_gpu_work", "counted_narrow": False, "counted_broad": True},
     "why": "同 R2，无 `timeout` 前缀也必须命中（`^` 分支）"},
    {"id": "R4_a2_latency_arm_must_still_be_detected",
     "source": "裁定 85.0 记录的真实形态（`scripts/e_mainline_render_calib.py` 网③注释里的事故 cmdline）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/a2_egl_latency_remeasure.py",
              "--mode", "closed_loop", "--tag", "quiet_window_rep1"],
     "cpu_ticks": 5000, "proc_state": "R",
     "expect": {"classification": "real_gpu_work", "counted_narrow": True, "counted_broad": True},
     "why": "**反漏检主腿**：A2 真要上卡的延迟臂，收紧之后必须照旧命中（窄档 3 个关键字 + 宽档）"},
    {"id": "R5_2358_cotenant_proxy_form",
     "source": "23:58 抢卡事故的 E 侧假体（`decisions_20260929.md` 网③注释 + §E1 记录）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/e_mainline_render_calib.py",
              "--workers", "1,2,4,8"],
     "cpu_ticks": 3000, "proc_state": "R",
     "expect": {"classification": "no_keyword", "counted_narrow": False, "counted_broad": False},
     "why": "改前改后**都不**由网③命中（`scripts/e_` 不属「他线」、且无窄档关键字）；当时抓住它的是**网②**"
             "（它持 `/dev/nvidia2`+`/dev/nvidiactl` 而 compute-apps 为空）⇒ 正是网①②不许动的原因"},
    {"id": "R6_bare_torchrun_launcher",
     "source": "反漏检构造（六步序列第 2 步的 BC/SFT 可能用分布式启动器）",
     "argv": ["torchrun", "--nproc_per_node=1", "harness/train_bc.py"],
     "cpu_ticks": 800, "proc_state": "R",
     "expect": {"classification": "real_gpu_work", "counted_narrow": True, "counted_broad": False},
     "why": "argv0 **本身就是** GPU 启动器 ⇒ 即使没有 `scripts/<line>_*.py` 也算真实执行形态（`GPU_LAUNCHER_ARGV0` 反漏检腿）"},
    {"id": "R7_coldstart_recovery_entry",
     "source": "T-E-11 第 3 项的恢复入口（`docs/infra-gpu-render.md` §0.4 权威恢复块）",
     "argv": ["env", "-i", "/bin/bash",
              "/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/scripts/e_coldstart_gpu_render.sh"],
     "cpu_ticks": 120, "proc_state": "R",
     "expect": {"classification": "no_keyword", "counted_narrow": False, "counted_broad": False},
     "why": "改前改后一致（`/bin/bash` + `scripts/e_` 构成执行形态，但两档关键字都不命中）⇒ 无回归"},
    {"id": "R8_python_m_torch_distributed_run",
     "source": "反漏检构造（`-m` 形态的分布式启动器）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "-m", "torch.distributed.run",
              "--nproc_per_node=1", "harness/train_bc.py"],
     "cpu_ticks": 800, "proc_state": "R",
     "expect": {"classification": "no_keyword", "counted_narrow": False, "counted_broad": False,
                "registered_gap": True},
     "why": "**已登记的漏检缺口（改前改后同）**：`-m torch.distributed.run` 不含任何窄档关键字、"
            "也没有 `scripts/<line>_*.py` ⇒ 网③两版都不命中；真上卡后由网②（fd）/网①（compute-apps）抓住。"
            "修法建议见 `residual_risk_register`（**E 不自决扩范围**，报 D）"},
    {"id": "R9_f_injected_bad_form",
     "source": "F 的 93.8 对照探针注入串（同上件 `pattern_coverage_probe.injected_bad_form`）",
     "argv": ["/bin/bash", "-c", "cd", "/repo", "&&", "grep", "-n",
              "a2_egl_latency_remeasure", "harness/some_module.py"],
     "cpu_ticks": 30, "proc_state": "R",
     "expect": {"classification": "text_mention_only", "counted_narrow": False, "counted_broad": False},
     "why": "`grep` 一个关键字 ≠ 要上卡（这条同时是本件 `pattern_coverage_probe` 的注入坏形态）"},
    {"id": "R10_shell_really_launching_a_gpu_run",
     "source": "残留风险构造（过判方向，安全侧）",
     "argv": ["/bin/bash", "-c", "cd /repo && python scripts/a2_egl_latency_remeasure.py --mode closed_loop"],
     "cpu_ticks": 60, "proc_state": "R",
     "expect": {"classification": "real_gpu_work", "counted_narrow": True, "counted_broad": True},
     "why": "`bash -c` 里**真要启动**一条 GPU 跑 ⇒ 计入是对的；代价是同形的 `echo`/`cat` 纯文本也会被计入"
            "（cmdline-only 探测无法区分，已在 `residual_risk_register` 登记）"},
    {"id": "R11_idle_carrier_with_exec_form",
     "source": "闲置腿构造（`pcpu≈0` 排除）",
     "argv": ["/bin/sleep scripts/a2_probe_idle.py --mode closed_loop", "30"],
     "cpu_ticks": 0, "proc_state": "S",
     "expect": {"classification": "idle_text_mention", "counted_narrow": False, "counted_broad": False},
     "why": "执行形态与关键字都在，但自启动以来几乎没执行过指令 ⇒ 按裁定 96.1-③ 排除"},
    {"id": "R12_just_forked_real_run_must_not_be_idle_excluded",
     "source": "闲置腿的**反漏检**对照（刚 fork 出来的真跑）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/a2_egl_latency_remeasure.py",
              "--mode", "closed_loop"],
     "cpu_ticks": 6, "proc_state": "S",
     "expect": {"classification": "real_gpu_work", "counted_narrow": True, "counted_broad": True},
     "why": "6 tick（60 ms）> `IDLE_CPU_TICKS`=1 ⇒ 不被闲置排除；python 解释器启动自身就已超过这个阈值"
            "（活体腿 L1 实测这个裕度）"},
]


def legs_replay(calib) -> dict:
    rows, all_ok = [], True
    for leg in REPLAY_LEGS:
        got = calib.classify_cmdline(leg["argv"], cpu_ticks=leg["cpu_ticks"],
                                     proc_state=leg["proc_state"])
        exp = leg["expect"]
        checks = {k: (got.get(k) == v) for k, v in exp.items() if k != "registered_gap"}
        ok = all(checks.values())
        all_ok &= ok
        rows.append({"id": leg["id"], "source": leg["source"], "why": leg["why"],
                     "argv_head": " ".join(leg["argv"])[:160], "n_argv": len(leg["argv"]),
                     "cpu_ticks": leg["cpu_ticks"], "proc_state": leg["proc_state"],
                     "expected": {k: v for k, v in exp.items()}, "checks": checks, "ok": ok,
                     "got": {k: got[k] for k in ("classification", "exec_form", "exec_form_kind",
                                                 "counted_narrow", "counted_broad", "idle",
                                                 "gpu_intent_matched", "other_line_script_matched")},
                     "measurement_status": "measured", "cpu_ctx": cpu_ctx()})
    return {"leg": "R_replay_pure_function", "n_rows": len(rows), "n_ok": sum(r["ok"] for r in rows),
            "all_ok": all_ok, "rows": rows,
            "caliber": "纯函数重放：不起进程、不读 /proc，喂的是**真实记录过的** argv（R1–R3、R9 出自 F 的实测件）",
            "measurement_status": "measured" if rows else "not_measured"}


# ── 活体腿用的诱饵 ────────────────────────────────────────────────────────────────────
SPIN_THEN_SLEEP = (
    "import time\n"
    "t0 = time.time()\n"
    f"while time.time() - t0 < 0.25:\n"
    "    pass\n"
    f"time.sleep({DECOY_LIFETIME_S})\n")

FIXTURE_SRC = '''"""E 的裁定 96.1-③ 探针用的**纯 CPU 诱饵**（fixture）。

路径里带 `scripts/a2_` 只是为了让 `card_busy()` 的宽档能有一个**真实执行形态**的正腿可测；
它**不是 A2 的文件**、A2 不跑它、也不进任何 run 目录（在 `tmp/`，按设计不入库）。
它不导入 torch/mujoco/OpenGL、不打开 `/dev/nvidia*`、不建任何 GL/CUDA 上下文，并把这一点
自证进 `--self-report` 指定的 JSON（`nvidia_fds` / `nvidia_maps` / `imports` 必须为空）。
"""
import json
import os
import sys
import time


def main() -> int:
    argv = sys.argv[1:]
    sleep_s = float(argv[argv.index("--sleep") + 1]) if "--sleep" in argv else 2.5
    report = argv[argv.index("--self-report") + 1] if "--self-report" in argv else None
    t0 = time.time()
    while time.time() - t0 < 0.25:      # 烧 0.25 s CPU ⇒ 累计 tick 必须 > IDLE_CPU_TICKS
        pass
    fds = []
    try:
        for fd in os.listdir("/proc/self/fd"):
            try:
                target = os.readlink("/proc/self/fd/" + fd)
            except OSError:
                continue
            if "/dev/nvidia" in target:
                fds.append(target)
    except OSError:
        pass
    maps = []
    try:
        txt = open("/proc/self/maps", errors="ignore").read()
        maps = [k for k in ("libcuda.so", "libnvidia-ml.so", "libnvidia-eglcore",
                            "libnvidia-glcore", "libEGL_nvidia.so") if k in txt]
    except OSError:
        pass
    try:
        st = open("/proc/self/stat", errors="ignore").read().rsplit(")", 1)[-1].split()
        ticks, state = int(st[11]) + int(st[12]), st[0]
    except (OSError, IndexError, ValueError):
        ticks, state = -1, ""
    rec = {"pid": os.getpid(), "argv": sys.argv, "nvidia_fds": sorted(set(fds)),
           "nvidia_maps": maps, "cpu_ticks": ticks, "proc_state": state,
           "gpu_context_created": False,
           "imports": sorted(m for m in ("torch", "mujoco", "OpenGL") if m in sys.modules),
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())}
    if report:
        Path = __import__("pathlib").Path
        Path(report).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\\n")
    time.sleep(max(0.0, sleep_s - (time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def ensure_fixture() -> dict:
    """诱饵 fixture：不存在则写、存在则必须字节相同（拒绝静默改字，裁定 94.6-1 同族）。"""
    path = REPO / FIXTURE_REL
    if path.exists():
        raw = path.read_bytes()
        if raw.decode() != FIXTURE_SRC:
            return {"ok": False, "reason": "fixture 已在盘且字节不同（拒绝覆写）", **ident(path)}
        return {"ok": True, "created": False, **ident(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FIXTURE_SRC)
    return {"ok": True, "created": True, **ident(path)}


def eval_both_code() -> str:
    """差分腿的子进程源码：同一时刻用**旧版**与**新版**模块各测一次三网，按 pid 输出。"""
    return r'''
import importlib.machinery, importlib.util, json, sys


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


out = {}
for tag, path in (("new", sys.argv[1]), ("old", sys.argv[2])):
    mod = load(path, "calib_" + tag)
    rec = {}
    for strict in (False, True):
        b = mod.card_busy(strict=strict)
        cands = {}
        for h in b["cmdline_hits_all_other_line"]:
            cands[str(h["pid"])] = {
                "narrow_counted": bool(h.get("gpu_intent")),
                "broad_matched": bool(h.get("other_line_script")),
                "classification": h.get("classification"),
                "exec_form_kind": h.get("exec_form_kind"),
                "cpu_ticks": h.get("cpu_ticks"),
                "proc_state": h.get("proc_state"),
                "cmdline_head": (h.get("cmdline") or "")[:120],
            }
        rec["strict_%s" % strict] = {
            "busy": b["busy"], "n_compute": len(b["compute_procs"]),
            "n_fd_holders": len(b["nvidia_fd_holders"]),
            "fd_holder_pids": [h["pid"] for h in b["nvidia_fd_holders"]],
            # `cmdline_hit_pids` = **真正驱动 `busy` 的那一组**（不是候选全集）⇒ 差分腿按它断言，
            # 分窄档（strict=False）与含宽档（strict=True）两个口径，正是 A2 窗口判据的两种用法。
            "cmdline_hit_pids": [h["pid"] for h in b["cmdline_hits"]],
            "candidates": cands,
        }
    out[tag] = rec
print(json.dumps(out))
'''


def run_eval_both(new_path: Path, old_path: Path) -> dict:
    code = eval_both_code()
    p = subprocess.run([sys.executable, "-c", code, str(new_path), str(old_path)],
                       capture_output=True, text=True, timeout=120, cwd=str(REPO))
    if p.returncode != 0:
        return {"ok": False, "returncode": p.returncode, "stderr_tail": p.stderr[-2000:],
                "measurement_status": "not_measured"}
    try:
        return {"ok": True, "measurement_status": "measured", "eval": json.loads(p.stdout.strip())}
    except json.JSONDecodeError as exc:
        return {"ok": False, "reason": f"子进程输出不是合法 JSON：{exc}",
                "stdout_tail": p.stdout[-800:], "measurement_status": "not_measured"}


def live_legs(calib, new_path: Path, old_path: Path) -> dict:
    """L + D 腿：真起诱饵进程，在它活着时用旧/新两版各测一次。"""
    fixture = ensure_fixture()
    if not fixture["ok"]:
        return {"leg": "L_live_processes", "all_ok": False, "measurement_status": "not_measured",
                "fixture": fixture, "rows": []}
    fixture_path = REPO / FIXTURE_REL
    rows = []
    all_ok = True
    plans = [
        {"id": "L1_real_exec_form_decoy", "direction": "positive",
         "expect": {"old_narrow": True, "old_with_broad": True,
                    "new_narrow": True, "new_with_broad": True},
         "spawn": {"kind": "fixture",
                   "args": [sys.executable, str(fixture_path), "--mode", "closed_loop",
                            "--tag", "quiet_window_probe", "--sleep", str(DECOY_LIFETIME_S),
                            "--self-report", str(OUT_DIR / "decoy_self_report_L1.json")]},
         "why": "真实执行形态（解释器 + `scripts/a2_….py`）∧ 窄档关键字 ∧ 非闲置 ⇒ **必须判忙**（两向的正腿；"
                "旧版也必须判忙 ⇒ 修法没有把真跑漏掉）"},
        {"id": "L2_f_measured_text_mention", "direction": "negative",
         "expect": {"old_narrow": False, "old_with_broad": True,
                    "new_narrow": False, "new_with_broad": False},
         "spawn": {"kind": "spoof_argv0", "executable": sys.executable,
                   "argv0": ("/bin/bash -c cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot "
                             "&& python3 - <<'PY' import pathlib "
                             "r=pathlib.Path(\"scripts/a2_s4b_outcome_ledger_verify.py\"); u=r.read_text()"),
                   "rest": ["-c", SPIN_THEN_SLEEP]},
         "why": "F 实测的那一起（PID 214244 形态）：在改文件、不是在上卡 ⇒ 新版**必须不判忙**；"
                "旧版宽档会判忙（`old_with_broad=True`）⇒ 差分腿证明这不是恒真断言"},
        {"id": "L3_grep_keyword_text_mention", "direction": "negative",
         "expect": {"old_narrow": True, "old_with_broad": True,
                    "new_narrow": False, "new_with_broad": False},
         "spawn": {"kind": "spoof_argv0", "executable": sys.executable,
                   "argv0": ("grep -rn a2_egl_latency_remeasure --mode closed_loop quiet_window "
                             "torchrun harness/ scripts/a2_egl_latency_remeasure.py"),
                   "rest": ["-c", SPIN_THEN_SLEEP]},
         "why": "93.8 注入坏形态的活体版：满嘴 GPU 关键字的 `grep`（纯 CPU、且在烧 CPU ⇒ 排除它靠的是"
                "**执行形态**而不是闲置过滤）；旧版**窄档**就会判忙 ⇒ 这正是 A2 起跑那一刻会被误判的形态"},
        {"id": "L4_idle_carrier", "direction": "negative",
         "expect": {"old_narrow": True, "old_with_broad": True,
                    "new_narrow": False, "new_with_broad": False},
         "spawn": {"kind": "spoof_argv0", "executable": "/bin/sleep",
                   "argv0": "/bin/sleep scripts/a2_probe_idle.py --mode closed_loop",
                   "rest": ["20"]},
         "why": "执行形态与关键字都在，但累计 CPU ≈0 ⇒ 按 `pcpu≈0` 排除（**闲置腿**：隔离出闲置过滤这一条判据）"},
    ]
    for plan in plans:
        spawn = plan["spawn"]
        self_report = None
        try:
            if spawn["kind"] == "fixture":
                proc = subprocess.Popen(spawn["args"], cwd=str(REPO), stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, text=True)
            else:
                proc = subprocess.Popen([spawn["argv0"]] + spawn["rest"],
                                        executable=spawn["executable"], cwd=str(REPO),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            rows.append({"id": plan["id"], "ok": False, "measurement_status": "not_measured",
                         "reason": f"诱饵起不来：{type(exc).__name__}: {exc}"})
            all_ok = False
            continue
        time.sleep(DECOY_SETTLE_S)
        diff = run_eval_both(new_path, old_path)
        in_proc = calib.card_busy(strict=False)
        row = {"id": plan["id"], "direction": plan["direction"], "why": plan["why"],
               "decoy_pid": proc.pid, "expect": plan["expect"],
               "differential": diff, "in_proc_busy": in_proc["busy"],
               "in_proc_candidates": [
                   {"pid": h["pid"], "classification": h["classification"],
                    "counted_toward_busy": h["counted_toward_busy"], "cpu_ticks": h["cpu_ticks"],
                    "proc_state": h["proc_state"], "exec_form_kind": h["exec_form_kind"]}
                   for h in in_proc["cmdline_hits_all_other_line"]],
               "gpu_snapshot_during_leg": {
                   "compute_procs": in_proc["compute_procs"],
                   "n_fd_holders": len(in_proc["nvidia_fd_holders"])},
               "cpu_ctx": cpu_ctx(), "measurement_status": "measured" if diff.get("ok") else "not_measured"}
        if diff.get("ok"):
            ev = diff["eval"]
            key = str(proc.pid)
            got = {"new_narrow": ev["new"]["strict_False"], "new_with_broad": ev["new"]["strict_True"],
                   "old_narrow": ev["old"]["strict_False"], "old_with_broad": ev["old"]["strict_True"]}
            measured = {k: (proc.pid in v["cmdline_hit_pids"]) for k, v in got.items()}
            row["measured_drives_busy"] = measured
            row["candidate_record_new"] = got["new_narrow"]["candidates"].get(key)
            row["candidate_record_old"] = got["old_narrow"]["candidates"].get(key)
            row["busy_flags"] = {k: v["busy"] for k, v in got.items()}
            row["checks"] = {f"{k}_as_expected": (measured[k] == plan["expect"][k]) for k in measured}
            # 差分腿：负腿必须"旧判忙 ∧ 新不判忙"（含宽档口径），否则这套断言是恒真的（缺陷类 ⑲）
            row["checks"]["differential_is_not_vacuous"] = (
                measured["old_with_broad"] != measured["new_with_broad"]
                if plan["expect"]["old_with_broad"] != plan["expect"]["new_with_broad"] else True)
            row["ok"] = all(row["checks"].values())
        else:
            row["ok"] = False
        if spawn["kind"] == "fixture":
            try:
                proc.wait(timeout=30)
                row["decoy_exit_code"] = proc.returncode
                row["decoy_stderr_tail"] = (proc.stderr.read() or "")[-400:]
            except subprocess.TimeoutExpired:
                proc.kill()
                row["decoy_exit_code"] = None
            srp = OUT_DIR / "decoy_self_report_L1.json"
            if srp.exists():
                try:
                    self_report = json.loads(srp.read_text())
                except json.JSONDecodeError:
                    self_report = None
            row["decoy_self_report"] = self_report
            row["decoy_touched_gpu"] = (None if self_report is None else bool(
                self_report.get("nvidia_fds") or self_report.get("nvidia_maps")
                or self_report.get("imports") or self_report.get("gpu_context_created")))
            if self_report is not None:
                row["checks"]["decoy_touched_gpu_is_false"] = row["decoy_touched_gpu"] is False
                row["ok"] = all(row["checks"].values())
        else:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            row["decoy_exit_code"] = proc.returncode
        rows.append(row)
        all_ok &= bool(row["ok"])
    both = {"positive_leg_present": any(r["direction"] == "positive" and r.get("ok") for r in rows),
            "negative_leg_present": any(r["direction"] == "negative" and r.get("ok") for r in rows)}
    return {"leg": "L_live_processes_and_D_differential", "fixture": fixture,
            "decoy_lifetime_s": DECOY_LIFETIME_S, "decoy_settle_s": DECOY_SETTLE_S,
            "n_rows": len(rows), "n_ok": sum(bool(r.get("ok")) for r in rows),
            "all_ok": bool(all_ok and both["positive_leg_present"] and both["negative_leg_present"]),
            "both_directions": both, "rows": rows,
            "gpu_boundary": ("诱饵为纯 CPU：不导入 torch/mujoco/OpenGL、不打开 `/dev/nvidia*`、不建 GL/CUDA 上下文；"
                             "由 `decoy_self_report` 自证（`nvidia_fds`/`nvidia_maps`/`imports` 全空）。"
                             "本探针只调用 detector 自身的**只读**三网（含 `nvidia-smi` 只读查询）"),
            "measurement_status": "measured" if rows else "not_measured"}


def legs_nets_untouched(new_path: Path, old_path: Path) -> dict:
    """N 腿：网①②与词表/锚点的源码字节，改前改后必须逐一相等（机器比对，不是散文声明）。"""
    def objects(path: Path) -> dict:
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
        out = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in NETS_MUST_BE_UNTOUCHED:
                    out[node.name] = ast.get_source_segment(src, node) or ""
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if getattr(tgt, "id", "") in NETS_MUST_BE_UNTOUCHED:
                        out[tgt.id] = ast.get_source_segment(src, node) or ""
        return out
    new_o, old_o = objects(new_path), objects(old_path)
    rows, all_ok = [], True
    for name in NETS_MUST_BE_UNTOUCHED:
        n, o = new_o.get(name), old_o.get(name)
        present = n is not None and o is not None
        same = present and n == o
        all_ok &= same
        rows.append({"object": name, "present_in_both": present, "byte_identical": same,
                     "sha256_12_before": None if o is None else hashlib.sha256(o.encode()).hexdigest()[:12],
                     "sha256_12_after": None if n is None else hashlib.sha256(n.encode()).hexdigest()[:12],
                     "n_lines_before": None if o is None else o.count("\n") + 1,
                     "n_lines_after": None if n is None else n.count("\n") + 1,
                     "measurement_status": "measured" if present else "not_measured"})
    return {"leg": "N_nets_untouched", "objects": list(NETS_MUST_BE_UNTOUCHED),
            "n_rows": len(rows), "n_ok": sum(r["byte_identical"] for r in rows),
            "all_ok": all_ok, "rows": rows,
            "claim": "网①（`compute-apps`）与网②（`/dev/nvidia*` fd）+ 窄档词表 + 宽档正则 + "
                     "`_cmdline()`/`_own_tree()` 的源码字节**逐字未改**；本轮只改网③的判据",
            "measurement_status": "measured" if rows else "not_measured"}


def legs_interface(calib) -> dict:
    """I 腿：`card_busy()` 的旧键一个都不能少（A2 按路径 import 本模块、自检件会 monkeypatch 它）。"""
    b = calib.card_busy(strict=False)
    missing = [k for k in LEGACY_CARD_BUSY_KEYS if k not in b]
    added = sorted(set(b) - set(LEGACY_CARD_BUSY_KEYS))
    sig_ok = True
    try:
        import inspect
        params = list(inspect.signature(calib.card_busy).parameters)
        sig_ok = params == ["exclude_pids", "strict"]
    except (ImportError, TypeError, ValueError):
        sig_ok = False
    hits_shape_ok = all(
        {"pid", "gpu_intent", "other_line_script", "cmdline"} <= set(h)
        for h in b["cmdline_hits_all_other_line"])
    return {"leg": "I_interface_unbroken",
            "legacy_keys": list(LEGACY_CARD_BUSY_KEYS), "missing_keys": missing,
            "added_keys": added, "signature_params_ok": sig_ok,
            "hit_dict_legacy_keys_ok": hits_shape_ok,
            "all_ok": bool(not missing and sig_ok and hits_shape_ok),
            "consumers": ["scripts/a2_egl_latency_remeasure.py（按路径 importlib 加载本模块，复用 `card_busy()`）",
                          "scripts/e_selfcheck_gate_mutation.py（monkeypatch `calib.card_busy`，签名须为 "
                          "`(exclude_pids=None, strict=False)`）",
                          "scripts/e_mainline_render_calib.py 自身的批级让位闸与假体拒绝逻辑",
                          "scripts/b2_s1_generate_dataset.py（自带同口径副本 `card_busy_three_net`，"
                          "**B2 的 RR-B2-18 归 B2 同批修**，本件不改它）"],
            "measurement_status": "measured"}


def legs_in_situ(calib) -> dict:
    """S 腿：此刻的三网原文读数（与 F 的 `probe_card_busy_*` 同口径，可对照）。"""
    out, checks = {}, {}
    for strict in (False, True):
        b = calib.card_busy(strict=strict)
        tag = f"strict_{strict}"
        out[f"strict_{strict}"] = {
            "busy": b["busy"], "compute_procs": b["compute_procs"],
            "n_fd_holders": len(b["nvidia_fd_holders"]),
            "fd_holder_pids": [h["pid"] for h in b["nvidia_fd_holders"]],
            "cmdline_hit_pids": [h["pid"] for h in b["cmdline_hits"]],
            "text_mention_only_pids": [h["pid"] for h in b["cmdline_hits_text_mention_only"]],
            "candidates": [{"pid": h["pid"], "classification": h["classification"],
                            "counted_toward_busy": h["counted_toward_busy"],
                            "exec_form_kind": h["exec_form_kind"], "cpu_ticks": h["cpu_ticks"],
                            "proc_state": h["proc_state"],
                            "gpu_intent_matched": h["gpu_intent_matched"],
                            "other_line_script_matched": h["other_line_script_matched"],
                            "cmdline_head": (h.get("cmdline") or "")[:160]}
                           for h in b["cmdline_hits_all_other_line"]],
            "excluded_own_pids": b["excluded_own_pids"],
            "cmdline_net_caliber": b["cmdline_net_caliber"],
            "cpu_ctx": cpu_ctx(), "as_of": now()}
        cands = b["cmdline_hits_all_other_line"]
        hit_pids = {h["pid"] for h in b["cmdline_hits"]}
        tmo_pids = {h["pid"] for h in b["cmdline_hits_text_mention_only"]}
        # 读数腿也要有牙（否则 `all_ok` 是空转的）：以下四条都是**内部自洽**判据，不引入新口径。
        checks[f"{tag}_busy_consistent_with_its_own_inputs"] = (
            b["busy"] == bool(b["compute_procs"] or b["nvidia_fd_holders"] or b["cmdline_hits"]))
        checks[f"{tag}_all_candidates_classified"] = all(
            h["classification"] in ("no_keyword", "text_mention_only", "idle_text_mention",
                                    "real_gpu_work") and h["cpu_ticks"] is not None
            and h["proc_state"] for h in cands)
        checks[f"{tag}_counted_implies_exec_form_and_not_idle"] = all(
            (h["exec_form"] and not h["idle"]) for h in cands if h["counted_toward_busy"])
        checks[f"{tag}_text_mention_only_disjoint_from_hits"] = not (hit_pids & tmo_pids)
        checks[f"{tag}_every_candidate_in_exactly_one_bucket"] = (
            {h["pid"] for h in cands} == (hit_pids | tmo_pids))
    snap = calib.gpu_snapshot()
    net1_ok = snap.get("utilization_gpu") is not None and snap.get("memory_used_mib") is not None
    checks["net1_readings_present_else_not_measured"] = net1_ok
    try:
        n_proc = len([e for e in os.listdir("/proc") if e.isdigit()])
    except OSError:
        n_proc = None
    return {"leg": "S_in_situ_three_net", "n_proc_visible": n_proc,
            "net1_raw": {"utilization_gpu": snap.get("utilization_gpu"),
                         "memory_used_mib": snap.get("memory_used_mib"),
                         "compute_procs": snap.get("compute_procs"),
                         "measurement_status": "measured" if net1_ok else "not_measured",
                         "note": ("`compute_procs=[]` 只有在网①**真的测到**时才是"
                                  "「卡上空」的证据；测不到就是 `not_measured`，"
                                  "不得读成「没有」（红线 `absence_of_measurement_is_not_"
                                  "measurement_of_absence`）")},
            "checks": checks, "all_ok": bool(all(checks.values()) and net1_ok and n_proc),
            "scan_scope": "/proc（只读；无根文件系统扫描，裁定 94.9-2）",
            "no_root_filesystem_scans": True, "readings": out,
            "measurement_status": "measured" if (n_proc and net1_ok) else "not_measured"}


def gpu_state(calib, when: str) -> dict:
    snap = calib.gpu_snapshot()
    measured = snap.get("utilization_gpu") is not None and snap.get("memory_used_mib") is not None
    return {"when": when, "as_of": now(),
            "utilization_gpu": snap.get("utilization_gpu"),
            "memory_used_mib": snap.get("memory_used_mib"),
            "compute_procs": snap.get("compute_procs"),
            "measurement_status": "measured" if measured else "not_measured",
            "raw_keys": sorted(snap), "cpu_ctx": cpu_ctx()}


def build_idle_calibration(legs: dict, calib) -> dict:
    """闲置阈值的**定标实测**（不是拍脑袋的常数）：真跑诱饵 vs 闲置载体的累计 tick。

    `scripts/e_mainline_render_calib.py` 的 `IDLE_CPU_TICKS` 注释里指向本字段
    （裁定 89.7：散文引用的东西必须真有一个保存下来的产物与之相等）。
    """
    clk = int(os.sysconf("SC_CLK_TCK"))
    rows = {r["id"]: r for r in legs["L_D"].get("rows", [])}
    l1, l4 = rows.get("L1_real_exec_form_decoy"), rows.get("L4_idle_carrier")
    real_ticks = real_state = idle_ticks = idle_state = None
    if l1:
        sr = l1.get("decoy_self_report") or {}
        cand = l1.get("candidate_record_new") or {}
        real_ticks = sr.get("cpu_ticks", cand.get("cpu_ticks"))
        real_state = sr.get("proc_state") or cand.get("proc_state")
    if l4:
        cand = l4.get("candidate_record_new") or {}
        idle_ticks, idle_state = cand.get("cpu_ticks"), cand.get("proc_state")
    thr = calib.IDLE_CPU_TICKS
    checks = {
        "real_decoy_ticks_measured": isinstance(real_ticks, int) and real_ticks >= 0,
        "idle_carrier_ticks_measured": isinstance(idle_ticks, int) and idle_ticks >= 0,
        "real_decoy_above_threshold": isinstance(real_ticks, int) and real_ticks > thr,
        "idle_carrier_at_or_below_threshold": isinstance(idle_ticks, int) and idle_ticks <= thr,
        "idle_carrier_classified_idle": bool(l4 and (l4.get("candidate_record_new") or {}).get(
            "classification") == "idle_text_mention"),
        "real_decoy_not_classified_idle": bool(l1 and (l1.get("candidate_record_new") or {}).get(
            "classification") == "real_gpu_work"),
    }
    measured = checks["real_decoy_ticks_measured"] and checks["idle_carrier_ticks_measured"]
    return {
        "question": "`IDLE_CPU_TICKS` 这个阈值有没有实测依据？会不会把刚 fork 出来的真跑排掉？",
        "threshold_ticks": thr, "sc_clk_tck": clk,
        "threshold_seconds": round(thr / clk, 4) if clk else None,
        "idle_proc_states": list(calib.IDLE_PROC_STATES),
        "real_run_decoy": {"cpu_ticks": real_ticks, "proc_state": real_state,
                           "leg": "L1（活体：解释器 + `scripts/a2_….py`，烧 0.25 s CPU 后转 sleep）"},
        "idle_carrier": {"cpu_ticks": idle_ticks, "proc_state": idle_state,
                         "leg": "L4（活体：`/bin/sleep` 载体，argv 里带执行形态与关键字）"},
        "margin": {"real_over_threshold": (None if not isinstance(real_ticks, int) or not thr
                                           else round(real_ticks / max(thr, 1), 1)),
                   "reading": ("真跑诱饵的累计 tick 是阈值的这个倍数 ⇒ 阈值留了足够的下裕度；"
                               "python 解释器**启动自身**就已超过阈值，所以刚 fork 的真跑不会被误排")},
        "unreadable_proc_means_not_idle": ("`_proc_cpu()` 取不到读数 ⇒ 返回 `(-1, \"\")` ⇒ `idle=False`"
                                           "（宁可过判不可漏判，与网②的 `D` 态同理）"),
        "checks": checks, "all_ok": bool(all(checks.values())),
        "measurement_status": "measured" if measured else "not_measured", "as_of": now(),
    }


def build_verdict(args) -> dict:
    new_path = REPO / CALIB_REL
    old_path = REPO / BEFORE_REL
    for p in (new_path, old_path):
        if not p.exists():
            return {"verdict": "NOT_MEASURED", "reason": f"缺少 {p}", "exit_code": 5}
    calib = load_calib(new_path, "calib_new")
    gpu_before = gpu_state(calib, "before_probe")
    legs = {
        "R": legs_replay(calib),
        "L_D": live_legs(calib, new_path, old_path),
        "N": legs_nets_untouched(new_path, old_path),
        "I": legs_interface(calib),
        "S": legs_in_situ(calib),
    }
    gpu_after = gpu_state(calib, "after_probe")
    idle_calib = build_idle_calibration(legs, calib)
    statuses = [legs[k].get("measurement_status") for k in legs]
    n_not_measured = sum(1 for s in statuses if s != "measured") + (
        0 if idle_calib["measurement_status"] == "measured" else 1)
    oks = {k: bool(legs[k].get("all_ok")) for k in legs}
    oks["idle_calibration"] = bool(idle_calib["all_ok"])
    probe = build_pattern_coverage_probe(legs)
    all_ok = all(oks.values()) and probe["detected"] and probe["both_directions"]
    if n_not_measured:
        verdict, code = "NOT_MEASURED", 5
    elif all_ok:
        verdict, code = "PASS", 0
    else:
        verdict, code = "FAIL", 3
    return {
        "artifact": "e_card_busy_fix_verdict", "line": "E", "generated_at": now(),
        "generator": "scripts/e_card_busy_probe.py", "generator_identity": ident(Path(__file__)),
        "ruling": RULING,
        "orders": ["work/decisions/decisions_20260929.md §96.1-③（E 主责 · P0.5 · A2 第一次真上卡之前）",
                   "§96.5 停点：E 先修 96.1-③ ⇒ 再继续 T-E-11 / T-E-12 + 落 96.3 的白名单两件"],
        "defect_family": "网在匹配「关于 GPU 的**文本**」，不是「GPU **占用**」（同族：B2 的 RR-B2-18）",
        "evidence_that_it_is_real_not_inferred": {
            "f_probe_artifact": ident(REPO / "runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json"),
            "f_measured_false_positive_pid": 214244,
            "f_measured_true_positives_pids": [214254, 214257],
            "consequence": ("A2 按裁定 94.9-1② 在起跑那一刻测三网 ⇒ 窗口被判 `contaminated`（D 不认数字）"
                            "或被起跑前拒绝逻辑挡下（`exit 3`）⇒ 白跑一轮；六步序列第 1–3 步全部要上卡")},
        "target_identity": {"before": ident(old_path), "after": ident(new_path)},
        "fix_summary": {
            "narrow_band": "**真实执行形态**（`EXEC_FORM_RE`，逐字复用 F 的探针；或 argv0 本身是 GPU 启动器；"
                           "或 `python -m` 分布式启动器）**∧ 窄档关键字 ∧ 非闲置**",
            "wide_band": "同一个执行形态 / 非闲置门槛（裁定 96.1-③「宽档同理」）",
            "idle_criterion": f"累计 utime+stime ≤ {calib.IDLE_CPU_TICKS} tick 且状态 ∈ "
                              f"{list(calib.IDLE_PROC_STATES)}；取不到读数 ⇒ **不**判闲置（宁可过判）",
            "anti_false_negative_legs": ["R4 A2 延迟臂", "R6 裸 `torchrun`", "R12 刚 fork 的真跑",
                                         "L1 活体真跑诱饵"],
            "not_counted_but_still_registered": "`cmdline_hits_text_mention_only`（消费方可审计「为什么这一刻没判忙」）",
            "exec_form_re_reused_from": {"path": "scripts/f_probe_card_busy.py",
                                         **ident(REPO / "scripts/f_probe_card_busy.py"),
                                         "reuse_not_reimplemented": True,
                                         "boundary": "读别人的工具、写自己的文件（裁定 96.1-③ 明示可复用）"},
        },
        "legs": legs,
        "legs_all_ok": oks,
        "idle_threshold_calibration": idle_calib,
        "pattern_coverage_probe": probe,
        "gpu_free_discipline": {
            "declared": "本轮 E 一条都不上卡（裁定 95.8 / 96.5）；本探针纯 CPU、不需窗口",
            "gpu_state_before": gpu_before, "gpu_state_after": gpu_after,
            "no_gl_or_cuda_context_created": True,
            "no_dev_nvidia_opened_by_probe_or_decoys": True,
            "how_proven": ("诱饵自证件 `decoy_self_report_L1.json`（`nvidia_fds`/`nvidia_maps`/`imports` 全空）"
                           " + 探针起止两次 `nvidia-smi` 只读读数（`gpu_state_before/after`）"
                           " + 每条活体腿记录当时的 `compute_procs` 与 fd 持有者数"),
            "only_readonly_nvidia_smi_queries": True},
        "residual_risk_register": residual_risks(calib),
        "n_not_measured_legs": n_not_measured,
        "verdict": verdict, "exit_code": code,
        "cpu_ctx_final": cpu_ctx(),
    }


def build_pattern_coverage_probe(legs: dict) -> dict:
    """裁定 93.8：注入一个已知坏形态 ⇒ 必须被检出；**两向都装**（缺陷类 ⑲：只装一向不许报绿）。"""
    inj = "grep -rn a2_egl_latency_remeasure --mode closed_loop quiet_window torchrun harness/ scripts/a2_egl_latency_remeasure.py"
    r9 = next((r for r in legs["R"]["rows"] if r["id"] == "R9_f_injected_bad_form"), None)
    l3 = next((r for r in legs["L_D"].get("rows", []) if r["id"] == "L3_grep_keyword_text_mention"), None)
    l1 = next((r for r in legs["L_D"].get("rows", []) if r["id"] == "L1_real_exec_form_decoy"), None)
    r4 = next((r for r in legs["R"]["rows"] if r["id"] == "R4_a2_latency_arm_must_still_be_detected"), None)
    neg_ok = bool(r9 and r9["ok"] and l3 and l3.get("ok"))
    pos_ok = bool(r4 and r4["ok"] and l1 and l1.get("ok"))
    return {
        "injected_bad_form": inj,
        "detected": neg_ok,
        "detected_meaning": "注入的坏形态被正确归类为 `text_mention_only` 且**不**计入 busy（重放腿 R9 + 活体腿 L3 双证）",
        "positive_control": {"cmdline": " ".join(REPLAY_LEGS[3]["argv"]),
                             "leg": "R4 + L1", "ok": pos_ok,
                             "meaning": "真跑形态**必须**照旧判忙；没有这条正腿，「什么都不判忙」也能过负腿（那是恒绿）"},
        "negative_control": {"leg": "L2/L3/L4 的差分腿",
                             "ok": bool(l3 and l3.get("checks", {}).get("differential_is_not_vacuous")),
                             "meaning": "**旧版必须判忙、新版必须不判忙** ⇒ 断言不是恒真；把修法退回去这套探针会红"},
        "both_directions": bool(neg_ok and pos_ok),
        "measurement_status": "measured" if (r9 and l3 and l1 and r4) else "not_measured",
        "ruling": "裁定 93.8 `reference_auditor_must_prove_its_own_pattern_coverage` + 缺陷类 ⑲",
    }


def residual_risks(calib) -> list[dict]:
    """可推翻条件一律带 `checked_by` + `checked_when`（裁定 94.9-5 / 缺陷类 ⑳：预登记条件必须有消费方）。"""
    return [
        {"id": "RR1_stale_keyword_table",
         "risk": ("窄档词表 `GPU_INTENT_PATTERNS` 是**手工维护**的：六步序列（裁定 95.2）会引入新入口"
                  "（如 `a2_s3_bc_overfit*`），若它既不含现有 11 个关键字、又还没加载 CUDA 库，"
                  "则**预分配显存之前**的那段（`from_pretrained` 实测 60–185 s）网③会漏判"),
         "falsifiable_condition": ("A2 的任一条六步入口脚本，其 cmdline 不含 `GPU_INTENT_PATTERNS` 里任何一项，"
                                   "且在起跑后 60 s 内网③窄档为 0 命中（而网①②也为空）"),
         "checked_by": "A2（起跑那一刻的三网读数落进 `GPU_WINDOW.json`，裁定 94.9-1②）+ E（收到申报后一行补词表）",
         "checked_when": "A2 每次上卡起跑时（六步序列第 1 步第一次上卡即到期）",
         "proposed_fix_not_self_authorized": ("E **不自决扩范围**（裁定 96.1-③「同族一并修，不扩范围」）；"
                                              "两条候选报 D：① A2 申报窗口时把入口名加进词表（一行，E 的写入面）；"
                                              "② 采纳 `/proc/<pid>/maps` 里的 `libcuda.so`/`libnvidia-*` 作为"
                                              "**实测**信号补进窄档（非文本、不随脚本名漂移，但属新增判据 ⇒ 需 D 点头）"),
         "severity": "低—中（网①②在 CUDA init 后仍会命中；漏的只是预分配那段窗口）"},
        {"id": "RR2_bash_c_text_over_inclusive",
         "risk": ("`bash -c '…python scripts/a2_x.py --mode closed_loop…'` 与 `bash -c 'echo 同样这串文本'` "
                  "在 cmdline 上无法区分 ⇒ 后者会被**过判**为占卡（安全侧：宁可让路）"),
         "falsifiable_condition": "出现一次「纯文本 echo/cat 被判 busy 而 A2 因此被拒绝起跑或窗口被判 contaminated」",
         "checked_by": "F（每轮的 `f_probe_card_busy.py` 只读探针，已能分开这两类）",
         "checked_when": "每轮（F 的常设台账，裁定 96.3）",
         "severity": "低（R10 已登记为有意的过判方向）"},
        {"id": "RR3_idle_exclusion_margin",
         "risk": f"累计 CPU ≤ {calib.IDLE_CPU_TICKS} tick 且状态 ∈ {list(calib.IDLE_PROC_STATES)} 会被排除；理论上刚 fork 的真跑可能落在这个区间",
         "falsifiable_condition": "任一活体/真实跑在起跑后第一次采样时 `cpu_ticks` ≤ 阈值而被漏判",
         "checked_by": "本探针 L1（活体实测裕度：`idle_threshold_calibration`）+ A2 起跑时的三网读数",
         "checked_when": "本轮已测（见 `legs.L_D.rows[L1]`）；A2 每次上卡起跑时复测",
         "severity": f"低（阈值取 1 tick = 10 ms；python 解释器启动自身即超过它，实测裕度见产物）"},
        {"id": "RR4_b2_copy_diverges",
         "risk": ("B2 自带同口径副本 `card_busy_three_net`（`scripts/b2_s1_generate_dataset.py`），"
                  "本次只改了 E 的参考实现 ⇒ 两份定义漂移（裁定 46.4 的根因形态）"),
         "falsifiable_condition": "B2 的副本仍用裸关键字匹配，且 B2/A2 的窗口判据读的是副本",
         "checked_by": "B2（RR-B2-18 同批修，裁定 96.1-③ 明示归 B2）+ D（里程碑审查）",
         "checked_when": "commit-4 之前（B2 的同批修）",
         "severity": "中（A2 的起跑前拒绝逻辑若走 B2 的副本，则本次修法对 A2 不生效）"},
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="裁定 96.1-③ 的 `card_busy()` 修法验证探针（纯 CPU）")
    ap.add_argument("--out-name", default="CARD_BUSY_FIX_VERDICT.json")
    ap.add_argument("--allow-overwrite", action="store_true",
                    help="默认拒绝覆写（每次重跑请换 `--out-name`）")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / args.out_name
    if out_path.exists() and not args.allow_overwrite:
        print(json.dumps({"verdict": "REFUSED_OVERWRITE", "existing": ident(out_path),
                          "how_to_proceed": "换 --out-name（旧件字节必须原样保留）"},
                         ensure_ascii=False, indent=1))
        return 2
    verdict = build_verdict(args)
    out_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=1) + "\n")
    summary = {"verdict": verdict.get("verdict"), "exit_code": verdict.get("exit_code"),
               "legs_all_ok": verdict.get("legs_all_ok"),
               "pattern_coverage_probe": {k: verdict.get("pattern_coverage_probe", {}).get(k)
                                          for k in ("injected_bad_form", "detected", "both_directions")},
               "n_not_measured_legs": verdict.get("n_not_measured_legs"),
               "target_identity": verdict.get("target_identity"),
               "out": ident(out_path)}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return int(verdict.get("exit_code", 5))


if __name__ == "__main__":
    sys.exit(main())
