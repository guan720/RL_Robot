#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · T-C2-1 归一化契约层的**闸**：牙的极性 + 变异体自证（裁定 49.1 / 51① / 68 / 78 / 79）。

## 它判什么（每条都有"哪把牙咬的"，不接受"总体绿"）
1. **基线三臂**（真跑 `scripts/c2_build_norm_stats.py`，产物落本闸自己的 run 目录）：
   基线 / `--no-widen` / `--floor-coef-scale 0`。
2. **极性**：基线必须绿（16 个非 stress 行全 PASS）；stress 8 行 + YAM 必红行必须红；
   `--no-widen` 必须由 **Tc**（起态覆盖）咬红；`--floor-coef-scale 0` 必须由 **Tr1**（近常量维无下限）
   咬红；两者咬的牙**必须不同**（否则说明有一把牙在替另一把挡枪，极性不可分辨）。
3. **落盘 = 被判**：每行 `roundtrip.match` 必须为真（从 stats 文件读回复算，verdict 一致）。
4. **输入级变异体**（进程内，直接调 `harness/norm_contract.evaluate_contract`）：
   清空 stats ⇒ **Ts** 红；`features={}` ⇒ **Ta** 红；单维缩放错 ⇒ 至少一把牙红**且点名到那一维**；
   主线臂 + F2 下限 ⇒ **Tr3** 红（诊断臂则必须 `N_A`，裁定 72-2 审点①③）。
5. **文件级变异体**（`mutant_construction_isolation`，裁定 79/78.1）：每个变异体在**独立新目录**构造，
   目录已存在 ⇒ **响亮拒绝**（不改名、不复用）；并**自证被 import 的就是变异副本**
   （子进程写回**活对象**属性 `nc.__file__` + `nc.__c2_mutant_id__`，不是读文件比对）。
   - `M1_non_raising`：去掉 `raise` ⇒ 契约层算出红却不抛 ⇒ 必须被 `Tconsistency_raise_matches_verdict` 抓住；
   - `M2_near_constant_always_empty`：`near_constant_dims` 恒返回 [] ⇒ `--floor-coef-scale 0` 时 **Tr1 必须失声**
     （失声 = 本闸的 G8 会红 = 变异体被抓；这正是"恒真的闸等于没有闸"的具体形态）；
   - `M3_payload_recompute_identity`：`stats_payload` 重新算 IDENTITY 的 center/gain ⇒ **round-trip 必须失配**；
   - `M4_collector_inline_qpos_formula`：把采集器的 qpos 映射改回内联 `state_dim + 2` ⇒ 勘误件 **Tp1 必须红**。
6. **写入面**：本闸只准写自己的 run 目录（跑完后逐文件枚举 `runs/vla/c2_norm_contract_20260929/`
   里 mtime 晚于开闸时刻、且不在 run 目录内的文件 ⇒ 有就必须红）。

## 纪律
每个数字带 `loadavg` + `nr_throttled`（分母 = cgroup 12 核）；否定主张要**全枚举**；
引用带 `(path, sha256-12, line)`；**不写「跑通/学会/达标」**；不 `rm`（本闸只新建，不删不改他人产物）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import norm_contract as nc      # noqa: E402
# 生成器模块**只为读口径清单**而 import（裁定 92.6 自查项族：常量各写一份必然漂移）。
# 漂移不靠自觉防：`pred_G41` 里有一条 clause 机器核 `EXPECT_CALIBERS == B.CALIBER_NAMES`。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import c2_build_norm_stats as B               # noqa: E402

PY = sys.executable
NORM_DIR = ROOT / "runs/vla/c2_norm_contract_20260929"
GATE_ROOT = NORM_DIR / "gate"
BUILD = "scripts/c2_build_norm_stats.py"
FIXPR = "scripts/c2_fix_physical_range.py"
ENV_ARMS = ("random", "sweep", "hold")
A2_START = "runs/vla/a2_pi05_zeroshot_20260929/approach_baseline.json"
YAM_STATS = "runs/vla/b2_abc130k_pairs_20260929/normalizer_stats.json"
PR_JSON = "physical_range_correction/physical_range.json"

MUST_RED_ROW_COUNT = 1        # YAM
STRESS_ROW_COUNT = 8
NORMAL_ROW_COUNT = 16
HOLD_ROW_COUNT = 8

# ---- 主线臂（裁定 90.4-4）：**权威接口 = npz + `--s1-frames`**；`--s1-lerobot` = 交叉核对臂 ----
# WHY 换档（裁定 86.0 撤回 85.4-2、86.1 末条、90.4-4）：修前这里指向 pilot-10 的 lerobot 目录，
# 并把 lerobot 读路径当主线；D 亲测两条读路径逐位等价后裁定 npz 为权威、lerobot 降为交叉核对臂
# （标签必须是 `formal40_lerobot_crosscheck`，结构上进不了 BC）。
FORMAL40_NPZ = "runs/vla/b2_states_14d_20260930/formal40/states_14d.npz"
FORMAL40_DIR = "runs/vla/b2_sim_demo_bidir_20260930/formal"
# 已退役（pilot 期常量 `PILOT10_DIR` / `B2_PILOT_NPZ` 已删）：pilot-10 的产物仍在盘上、仍是
# 裁定 83/84 文书引用的基线，但**不再是闸的输入档**（裁定 87.3-3：先导档 `not_for_bc`）。
MAINLINE_ROW_COUNT = 8        # 2 case × 2 family × 2 coef（权威 npz 臂）
CROSSCHECK_ROW_COUNT = 8      # 同批数据的 lerobot 交叉核对臂
BC_ARM_ROW_COUNT = 8          # 交叉核对臂的标签 + 消费方声明为 bc ⇒ 牙 Tp5 必须红
BASELINE_ROW_COUNT = 25       # 基线三臂（random/sweep/hold = 8+8+8）+ YAM 必红 1
MAINLINE_ARM_TOTAL_ROWS = 49  # 25（基线三臂 + YAM）+ 8 权威 npz + 8 交叉核对 + 8 BC 准入必红
TP4 = "Tp4_stats_provenance_declared"
TP5 = "Tp5_bc_admission_requires_formal40_bc_source"
# 裁定 93.2 / 93.4 新增的四颗牙（G52–G55 的判据对象；id 与 `harness/norm_contract.py` 同源）
TZ_ID = "Tz_denom_strictly_positive"
TRES_ID = "Tres_per_dim_resolution_floor"
TRESW_ID = "Tresw_near_constant_low_resolution_is_warned"
TBCAD_ID = "Tbcad_admission_requires_green_gate"
PILOT10_LABEL = "pilot10_path_check"       # 仍作"不可进 BC 的标签"之一用于进程内探针（G38）
FORMAL40_LABEL = "formal40_bc_source"      # **BC 档标签只由 npz 权威臂产**（裁定 90.4-4）
CROSSCHECK_LABEL = "formal40_lerobot_crosscheck"
# WHY 删除 `MAINLINE_ALLOWED_RED_F1` / `MAINLINE_ALLOWED_RED_F2`（裁定 35.1：不留尸体、写清理由）：
#   这两个常量在修前的闸里就已经是**死代码**（全文件仅这两行出现，无任何谓词引用），而 D 在
#   §D90.1 正是把「`Tiv` 不在 `MAINLINE_ALLOWED_RED_F1` 里」当作阻塞 BC 的理由之一 ⇒ 一个**没人读**
#   的常量被当成判据引用，是"声明与实现分叉"的教科书形态（裁定 88 `redline_provenance_discipline` 同族）。
#   现行口径：主线臂**允许红的牙由生成器逐行从测量派生**（`derive_allowed_red_from_measurement`），
#   闸只核「红是否逐条被授权事实解释」（`pred_G27` 的 `unexplained_red_teeth == []`），
#   **不再**在闸侧维护第二份白名单（两份白名单必然漂移，这正是本仓反复实测到的缺陷类 ⑨/⑮）。


def sha12(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def load_pair() -> dict:
    la = " ".join(Path("/proc/loadavg").read_text().split()[:3]) if Path("/proc/loadavg").exists() else "unavailable"
    nt = None
    for cand in ("/sys/fs/cgroup/cpu,cpuacct/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        p = Path(cand)
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("nr_throttled"):
                    nt = int(line.split()[1])
            break
    return {"loadavg": la, "nr_throttled": nt, "cgroup_quota_cores": 12}


class Gate:
    """最小公共 check schema（裁定 78.2）：`id / ok / status / required / observed / red_when`。

    裁定 **97.3-1/2** 起每条 check 另带 `triage_class`（用户三分类：1 = 控制与数据正确性、
    2 = 实验解释风险、3 = 文档与管理完整性；**默认 = 1**，取值**只**从
    `TRIAGE_CLASS_RUN_LEVEL_META` 这一张表来 ⇒ 单一真源），并另出一个 **`verdict_class1`**
    （= 当且仅当 class-1 的 blocking 红为 0 时 `PASS`）。**顶层 `verdict` 的语义与极性一字不改**：
    class-2/3 的红照样让 `verdict = RED`、照样登记、照样必须在 S5 前清零；变的只是
    「BC 准入 AND 哪一个判词」（裁定 97.3-3 ⇒ `verdict_class1`）与「顶层 RED 是否单独构成
    停训理由」（裁定 97.5 ⇒ 不构成）。
    """

    def __init__(self):
        self.checks: list[dict] = []

    def add(self, cid, name, ok, required, observed, red_when, kind="measured", note=None,
            applies_when=True, blocking=True, mutant_that_proves_it=None, ruling_ref=None,
            triage_class=None):
        status = "N_A" if not applies_when else ("PASS" if ok else ("RED" if blocking else "WARN"))
        tc = (int(triage_class) if triage_class is not None
              else int(TRIAGE_CLASS_RUN_LEVEL_META.get(cid, 1)))
        self.checks.append({"id": cid, "name": name, "ok": bool(ok), "status": status,
                            "required": required, "red_when": red_when, "observed": observed,
                            "kind": kind, "note": note, "blocking": bool(blocking),
                            "applies_when": bool(applies_when),
                            "triage_class": tc,
                            "mutant_that_proves_it": mutant_that_proves_it, "ruling_ref": ruling_ref})
        return status

    @property
    def n_red(self):
        return sum(1 for c in self.checks if c["status"] == "RED")

    @property
    def n_red_class1(self):
        """class-1（控制与数据正确性）的 **blocking** 红数。`status=="RED"` 已蕴含
        `blocking=True`（非阻塞的失败在 `add()` 里落 `WARN`）⇒ 不必再筛一次 `blocking`。"""
        return sum(1 for c in self.checks
                   if c["status"] == "RED" and c.get("triage_class") == 1)

    @property
    def red_by_class(self):
        return {k: [c["id"] for c in self.checks
                    if c["status"] == "RED" and c.get("triage_class") == k] for k in (1, 2, 3)}

    @property
    def verdict_class1(self):
        """裁定 97.3-2：**当且仅当 class-1 的 blocking 红为 0 时 `PASS`**。
        这是 BC 准入要 AND 的那一个判词（97.3-3），也是「BC 被禁」的唯一闸侧判据（97.5）。"""
        return "PASS" if self.n_red_class1 == 0 else "RED"

    @property
    def n_warn(self):
        return sum(1 for c in self.checks if c["status"] == "WARN")

    @property
    def n_unjudged(self):
        return sum(1 for c in self.checks if c["status"] == "UNJUDGED")

    @property
    def ok(self):
        return self.n_red == 0 and self.n_unjudged == 0


def run_py(script_rel: Path, args: list[str], cwd: Path, env_extra: dict | None = None,
           timeout: int = 900) -> dict:
    cmd = [PY, str(script_rel), *[str(a) for a in args]]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MUJOCO_GL": os.environ.get("MUJOCO_GL", "osmesa"),
           "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2", **(env_extra or {})}
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(cwd), timeout=timeout)
        exit_code, out, err = proc.returncode, proc.stdout, proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code, out, err, timed_out = 124, exc.stdout or "", (exc.stderr or "") + "\n[TIMEOUT]", True
    return {"cmd": [str(c) for c in cmd], "cwd": str(cwd), "exit": exit_code, "timed_out": timed_out,
            "elapsed_s": round(time.time() - t0, 3), "stdout_tail": out[-1500:], "stderr_tail": err[-1500:],
            "load_pair": load_pair()}


def build_args(out_dir: Path, extra: list[str], root: Path | None = None) -> list[str]:
    """输入路径**必须经调用方的 ROOT**：build 脚本对每个输入做 `relative_to(ROOT)`，
    变异体副本的 ROOT 是它自己的目录 ⇒ 传真仓绝对路径会抛 ValueError（首跑实测到过）。
    变异体目录里有 `runs -> 真 runs/` 的符号链接，所以经它寻址既是同一个文件、又在 ROOT 之内。"""
    r = ROOT if root is None else Path(root)
    nd = r / "runs/vla/c2_norm_contract_20260929"
    a = ["--emit-yam", "--out-dir", str(out_dir),
         "--env-frames", str(nd / "env_states_random/env_states.npz"),
         "--env-frames-2", str(nd / "env_states_sweep/env_states.npz"),
         "--env-frames-hold", str(nd / "env_states_hold/env_states.npz"),
         "--physical-range-json", str(nd / PR_JSON),
         "--yam-stats", str(r / YAM_STATS)]
    return a + extra


def rows_by(matrix: dict, *, tag=None, must_red=None):
    out = []
    for i, r in enumerate(matrix.get("rows", [])):
        if tag is not None and r.get("tag") != tag:
            continue
        if must_red is not None and bool(r.get("is_must_red_branch")) != must_red:
            continue
        out.append((i, r))
    return out


def teeth_ids(row: dict) -> set[str]:
    return {t["id"] for t in (row.get("teeth") or [])}


def red_ids(row: dict) -> set[str]:
    return {x.split(" ")[0] for x in (row.get("red") or [])}


def tooth_status_of(payload: dict, tid: str) -> str:
    """从**结构化 payload** 取某颗牙的 `status`（不去反解红的字符串）。缺席 ⇒ `"ABSENT"`。

    WHY 不用 `str(exc).split("；")`：牙与牙之间的分隔符是 `RED_MESSAGE_SEPARATOR = "\\n"`，而**单颗牙
    自己的** `required`/`observed` 文案内部本来就含中文分号 ⇒ 反解出来的是碎片。本轮设计探针实测到过
    （`runs/vla/c2_norm_contract_20260929/probe_design_ruling94_95/design_probe.json` 里 G52 那行的
    `red` 集合含 `'**逐维**判，永不'`、`'denom_raw_d'`、`'口径'` 这类片段）⇒ 判据必须读结构化字段
    （裁定 78.2 的最小公共 check schema 就是为了这个）。
    """
    return next((t.get("status") for t in ((payload or {}).get("teeth") or [])
                 if t.get("id") == tid), "ABSENT")


def tooth_field_of(payload: dict, tid: str, key: str):
    """取某颗牙 `extra` 里的一个字段（`tooth()` 把 `extra` **平铺**进牙记录，不是嵌套子字典）。"""
    return next((t.get(key) for t in ((payload or {}).get("teeth") or [])
                 if t.get("id") == tid), None)


# --------- matrix 级谓词：闸用**它**判定，同一份也拿去套变异体产物（不许各写一份） ---------
# 裁定 83.2 `tooth_must_be_mutant_proven` 的落地形式：一条 check "非恒真" 的证据 =
# 存在一个变异体，使**同一个谓词函数**在真仓产物上为 True、在变异体产物上为 False（实测，不是文案）。
SCHEMA_NEED = {"id", "ok", "status", "required", "observed", "red_when"}
# 裁定 87.3-1 的 ① 加了 `Tcov`；裁定 90.4-1 把 `Tiv_no_state_outside_declared_interval`（越界即红）
# 换成四把牙（测量 / 窗口逃逸硬红 / 下侧覆盖不足硬红 / 越界只 warning）⇒ 15 → 20 把。
# 旧 id **不得**再出现（名字承诺一条已撤回的极性 = 规则 `gate_name_must_match_gate_semantics` 违例），
# 由 `pred_G39` 机器核。
EXPECT_TEETH = sorted(["Ta_features_non_empty", "Tb_scale_floor_effective", "Tc_start_pose_coverage",
                       "Tcov_declared_interval_covered",
                       "Td1_clip_build_frames", "Td2_clip_heldout", "Te1_no_illegal_bin_build",
                       "Te2_no_illegal_bin_heldout", "Tr1_near_constant_has_floor",
                       "Tr2_stats_source_allowed", "Tr3_near_constant_floor_material",
                       "Ts_stats_arrays_present", "Tsat_saturation_dims_zero", "Tw_ctrlrange_coverage",
                       "Tiv_out_of_declared_interval_is_measured",
                       "Tesc_no_covered_window_escape",
                       "Tlo_no_downside_coverage_deficit",
                       "Tovr_out_of_interval_overflow_is_warned",
                       # 裁定 93.1/93.2/93.4 新增的四颗（20 → 24 把）：`Tz` = 除零族绝对硬红、
                       # `Tres` = 逐维分辨率下限（全量口径、D 定标）、`Tresw` = 近常量维 <8 的 WARN 登记、
                       # `Tbcad` = BC 准入必须 AND 闸 verdict。转 WARN 的 `Tb`/`Tr3` **仍在册**
                       # （裁定 93.1-3：登记不许缩水 ⇒ id 集合不许因转 WARN 而缩小）。
                       "Tz_denom_strictly_positive", "Tres_per_dim_resolution_floor",
                       "Tresw_near_constant_low_resolution_is_warned",
                       "Tbcad_admission_requires_green_gate",
                       TP4, TP5])
# 裁定 90.4-1 撤回极性的那把牙：id 一旦 reappearance ⇒ 名字与实际判据不符（G39 判红）。
WITHDRAWN_TOOTH_IDS = ["Tiv_no_state_outside_declared_interval"]
# 四把新牙的**期望语义**（名 ↔ 实；G39/G42 的判据来源，与 `harness/norm_contract.py` 的实现同源核对）
IV_TEETH = ("Tiv_out_of_declared_interval_is_measured", "Tesc_no_covered_window_escape",
            "Tlo_no_downside_coverage_deficit", "Tovr_out_of_interval_overflow_is_warned")
IV_EXPECT_STATUS_MAINLINE = {"Tiv_out_of_declared_interval_is_measured": "PASS",
                             "Tesc_no_covered_window_escape": "PASS",
                             "Tlo_no_downside_coverage_deficit": "PASS",
                             "Tovr_out_of_interval_overflow_is_warned": "WARN"}
IV_EXPECT_BLOCKING = {"Tiv_out_of_declared_interval_is_measured": True,
                      "Tesc_no_covered_window_escape": True,
                      "Tlo_no_downside_coverage_deficit": True,
                      "Tovr_out_of_interval_overflow_is_warned": False}
# 主线臂的牙集合**与基线相同**：`nc.evaluate_contract` 的 `tooth()` 对不适用的臂也 append
# 一条 `status=N_A` 的记录（裁定 72-2 审点①③ 要求的形态）⇒ Tp5 的 **id** 在每一行都在，
# 区别只在 `applies_when` / `status`。所以"Tp5 只在 BC 臂生效"这条要用 **status != N_A** 判，
# 不能用"id 是否出现"判（首轮冒烟实测踩过：按 id 判 ⇒ 基线并集差一个 Tp5、G21 假红）。
EXPECT_TEETH_MAINLINE = sorted(set(EXPECT_TEETH))

# ---- 裁定 93.1 / 93.2 的**极性台账**（G27 / G58 的判据来源；与 `harness/norm_contract.py` 同源核对）----
# 93.1（E4 = 甲）转 WARN 的两颗：阈值状态 = `registered_measurement_not_a_judgment` ⇒ `blocking=False`。
RULING_93_1_WARN_TEETH = ("Tb_scale_floor_effective", "Tr3_near_constant_floor_material")
# 93.2 换上去的两颗硬红（绝对硬红 / 逐维分辨率下限）：在真实数据上必须**绿**，在各自变异体上必须红。
RULING_93_2_HARD_TEETH = ("Tz_denom_strictly_positive", "Tres_per_dim_resolution_floor")
# 93.2 明令**不许跟着降级**的八颗（D 的验收：会 diff 前后牙清单，`missed=[]`/`extra=[]`）。
PROTECTED_TEETH_93_2 = ("Tr1_near_constant_has_floor", "Te1_no_illegal_bin_build",
                        "Te2_no_illegal_bin_heldout", "Tesc_no_covered_window_escape",
                        "Td1_clip_build_frames", "Td2_clip_heldout",
                        "Tp5_bc_admission_requires_formal40_bc_source",
                        "Tsat_saturation_dims_zero")
# 93.4 新增的 BC 准入 AND 闸（blocking）与 93.2 的 WARN 登记牙（**非** blocking）。
RULING_93_4_BC_GATE_TOOTH = "Tbcad_admission_requires_green_gate"
RULING_93_2_WARN_TOOTH = "Tresw_near_constant_low_resolution_is_warned"
# ⚠ 例外必须**显式登记**、不许写成"全都 blocking=True"（那是一句假话，会被真产物判红）：
#   `env_holdphase` / `env_randomphase` 两个**诊断档**臂上，held-out 家族三颗牙（Te2/Td2/Tsat）
#   本来就是 `blocking=False`（`force_blocking=False`：拿非部署分布的帧判红 = 极性错，裁定 51①
#   对 ctrlrange 覆盖率的处置同族）。实测：本轮 arm_mainline 与**上一轮权威跑** run_20260930_073852
#   的这两个臂读数**逐格相同** ⇒ 这是 93.1 之前就有的授权行为，不是本轮引入的放宽。
NON_BLOCKING_EXCEPTION_ARMS = ("env_holdphase", "env_randomphase")
NON_BLOCKING_EXCEPTION_TEETH = ("Te2_no_illegal_bin_heldout", "Td2_clip_heldout",
                                "Tsat_saturation_dims_zero")
# 裁定 93.1-3「**登记不许缩水**」：转 WARN 之后每行仍必须落的逐维读数字段（D 点名的 6 个 + 94.3 的 2 个）。
# 它们分散在三处（`summary` / `summary_all` / `near_constant`），本表把"在哪"写死 ⇒ G57 可逐条枚举。
NO_SHRINK_REQUIRED_FIELDS = {
    "summary": ("bins_occupied_per_dim", "dims_below_min_bins", "dims_floor_binding",
                "n_dims_floor_binding"),
    "summary_all": ("bins_occupied_per_dim", "dims_below_min_bins", "dims_floor_binding",
                    "n_dims_floor_binding"),
    "near_constant": ("materiality_ratio_min", "floor_min_on_marked"),
}
NO_SHRINK_ROW_FIELDS = ("bins_occupied_per_dim_resolution_caliber",
                        "heldout_bins_occupied_per_dim", "correctness_blind_dims",
                        "correctness_blind_dims_status")


def _normal_rows(mx):
    return [(i, r) for i, r in rows_by(mx)
            if not r.get("is_must_red_branch") and not r.get("is_stress_branch")]


def _stress_rows(mx):
    return [(i, r) for i, r in rows_by(mx) if r.get("is_stress_branch")]


def _mustred_rows(mx):
    return [(i, r) for i, r in rows_by(mx) if r.get("is_must_red_branch")]


def pred_G1(mx):
    return mx.get("verdict") == "PASS"


def pred_G2(mx):
    normal = _normal_rows(mx)
    return len(normal) == NORMAL_ROW_COUNT and all(r["verdict"] == "PASS" for _, r in normal)


def pred_G3(mx):
    stress = _stress_rows(mx)
    return (len(stress) == STRESS_ROW_COUNT and all(r["verdict"] == "RED" for _, r in stress)
            and all({"Td2_clip_heldout", "Te2_no_illegal_bin_heldout"} <= red_ids(r) for _, r in stress))


def pred_G4(mx):
    mustred = _mustred_rows(mx)
    return (bool(mustred) and len(mustred) == MUST_RED_ROW_COUNT
            and mustred[0][1]["verdict"] == "RED"
            and "Tr2_stats_source_allowed" in red_ids(mustred[0][1]))


def pred_G5(mx):
    rows = mx.get("rows", [])
    return (len(rows) > 0
            and all((r.get("roundtrip") or {}).get("match") for r in rows)
            and sum(1 for r in rows if (r.get("roundtrip") or {}).get("match")) == len(rows))


def pred_G6(mx):
    all_teeth = [t for _, r in rows_by(mx) for t in (r.get("teeth") or [])]
    missing = sorted({t.get("id", "<no-id>") for t in all_teeth if not SCHEMA_NEED <= set(t)})
    tr3_diag = [t["status"] for _, r in rows_by(mx) if not r.get("is_must_red_branch")
                for t in (r.get("teeth") or []) if t["id"] == "Tr3_near_constant_floor_material"]
    return (not missing) and all(s == "N_A" for s in tr3_diag) and len(all_teeth) > 0


def pred_G21(mx):
    cons = [i for i, r in rows_by(mx) if "Tconsistency_raise_matches_verdict" in red_ids(r)]
    union = sorted({tt["id"] for _, r in rows_by(mx) for tt in (r.get("teeth") or [])})
    # 裁定 90.4-1 撤回极性的旧 id 不得复活：名字承诺一条不再判的约束 = 名实不符
    withdrawn = [t for t in WITHDRAWN_TOOTH_IDS if t in union]
    return (not cons) and union == EXPECT_TEETH and not withdrawn


# G24 的三类分层（裁定 83.2 `tooth_must_be_mutant_proven` 的落地口径）：
#  A 类（**默认**，不在这两个集合里就是 A 类）= 必须有**实测翻转**台账：同一个谓词函数在真仓产物上
#     为 True、在某变异体产物上为 False。没有台账记录 ⇒ G24 红。
#  B 类 SELF_EVIDENT_FLIP = 该 check 的判据**本身**就是"变异体让某把牙失声/留痕"的实测记录
#     （它绿 = 已经实测到翻转；它红 = 翻转没发生）。再要一个"让它红的变异体"是同义反复。
#  C 类 DECLARED_PROOF_EXCEPTION = 元判据 / 执行前提 / **主动拒绝构造**行为型变异体。
#     理由必须写进该 check 的 note，不装成已证（G20 是这一类的范例）。
SELF_EVIDENT_FLIP = frozenset([
    "G7_no_widen_bites_Tc", "G8_floor_off_bites_Tr1", "G16_M1_non_raising_caught",
    "G17_M2_near_constant_empty_caught", "G18_M3_payload_divergence_caught",
    "G19_M4_collector_regression_caught", "G22_M5_schema_drop_caught", "G23_M6_tr3_false_red_caught",
    # G48：判据**就是**"三颗牙各自被哪个变异体翻"的实测台账（missed/extra/all_caught）⇒ 再要一个
    #   "让 G48 红的变异体"是同义反复（与 G16–G23 同族）。
    "G48_ruling_90_4_1_three_teeth_ledger",
    # G51：判据 = 每个变异体锚点在**真仓文件里恰好出现 1 次** + 一个"故意不存在的对照锚点必须 0 次"
    #   的枚举器自检（与 G20 的枚举器自检同族）。它的非恒真性本轮已被**真实检出**证明：
    #   M1/M5/M13 三个锚点因实现改名/重构而漂移（count=0），G51 正是为拦这类漂移而立。
    "G51_mutant_anchors_match_exactly_once"])
DECLARED_PROOF_EXCEPTION = frozenset([
    "G0_arms_executed", "G20_write_scope", "G24_every_check_mutant_proven",
    "G25_inprocess_teeth_mutant_proven", "G26_payload_teeth_mutant_proven"])
# 裁定 **97.3-1/4**：`triage_class` 的**唯一**取值来源（`Gate.add()` 只读这张表，默认 1）。
#   1 = 控制与数据正确性 · 2 = 实验解释风险 · 3 = 文档与管理完整性。
# 只显式标 **run 级元牙**（判的是本轮跑的台账 / 引用 / 写入面，**一个字节都不碰训练数据**）；
# 其余 44 条一律走默认 1 —— D 明令「不要给 54 条逐条写理由」（那就是 Ⅲ 类扩张）。
# ⚠ 单一真源、不接受第二份清单（本轮实测到的失效形态就是"两份清单漂移"：`INPROC_FLIP_PLAN`
#   改了、探针副本循环没加 M6 ⇒ `G25`/`G24` 双红，见 97.2 红一的根因登记）。
#   漏改 id 的失效方向是**安全**的：回落到默认 1 ⇒ 只可能更严（更可能挡 BC），不会更松。
TRIAGE_CLASS_RUN_LEVEL_META = {
    # 执行前提：三臂没跑完 ⇒ 一个字节证据都没有 ⇒ **必须**挡 BC（显式标 1，不是漏标）。
    "G0_arms_executed": 1,
    "G20_write_scope": 3,                          # 裁定 97.3-4，D 定：写入面记账 = Ⅲ 类
    "G24_every_check_mutant_proven": 2,            # 裁定 97.3-4，D 定：台账完备性 = Ⅱ 类
    "G25_inprocess_teeth_mutant_proven": 2,        # 裁定 97.3-4，D 定
    "G26_payload_teeth_mutant_proven": 2,          # 与 G24/G25 同族（翻转台账完备性）
    "G48_ruling_90_4_1_three_teeth_ledger": 2,     # 与 G24 同族（三颗牙各自的翻转台账）
    "G51_mutant_anchors_match_exactly_once": 2,    # 锚点漂移 ⇒ 变异体改的不是它声称的那一行 = 解释风险
    "G42_tooth_name_matches_semantics": 2,         # 名实不符 ⇒ 读者会以为有一条并不存在的保证（⑲ 族）
    "G46_tooth_name_citation_integrity": 3,        # 牙名引用完整性（悬空引用）= 文档与管理完整性
    "G57_no_shrink_registration_ruling_93_1_3": 3,  # 裁定 93.1-3「登记不许缩水」= 登记完整性
}
# 裁定 **97.2 红二**：`G20_write_scope` 的**既声明例外**清单（D 的处置原文 = 「在 G20 的既声明
#   例外清单里登记这一条路径 + 裁定号 + `as_of`；**不得移动或删除该文件**」）。
# 为什么不删/不移：它是 D 下令的更正证据、已被文书引用 ⇒ 移动会造成新的悬空引用
#   （D 同型错误 #21 的形状）。为什么这条例外不违反 Ⅲ 类冻结扩张：**给既有牙加一条声明例外，
#   不是新增牙**（97.2 红二原文）。
# ⚠ 例外只吃掉**路径命中**的那一个文件，且命中情况必须写进 `observed`（不许静默吞）。
G20_DECLARED_WRITE_EXCEPTIONS = {
    "runs/vla/c2_norm_contract_20260929/probe_monotonicity_20260930/"
    "ADDENDUM_ruling_94_6_1_wording_correction.json": {
        "ruling_ref": "裁定 94.6-1（措辞更正附录，D 下令落盘）/ 裁定 97.2 红二（登记为既声明例外）",
        "as_of": "2026-09-30T12:55:07+08:00",
        "triage_class": 3,
        "reason": ("12:5x 那轮全量闸跑（run_20260930_125352）进行**中**落了这份附录 ⇒ 被 G20 逮住。"
                   "它是 run 目录外的写入、但**一个字节都不碰训练数据**（Ⅲ 类记账）；"
                   "文件本身必须留在原地（已被 D 的文书引用）。"),
        "must_not_move_or_delete": True},
}
# 进程内 check 的翻转计划：**每条 check 由哪个变异体翻**是实测分工，不是一句"M1 全能"。
# 实测（00:5x，run_20260930_010545）：M1 只翻 G12/G13/G14；G10/G11 在 M1 下**仍为 True**，
# 因为 `Ts` 走 norm_contract.py:424-430 的独立提前抛 ⇒ 需要 M9 才翻得动。
# ⚠ `G14` 已从 M1 的分工里**移出**（裁定 93.1-1 之后 Tr3 不再产红 ⇒ M1「算出红也不抛」
#   在这条探针上无从翻转；实测台账会显示 baseline=True / M1 副本=True ⇒ 记不到翻转，
#   G24 会以"缺实测翻转台账"判红）。改由 **M6** 承担（它把 blocking/applies_when 一起装回去）。
INPROC_FLIP_PLAN = {"M1_non_raising": ["G12_empty_features_bites_Ta",
                                       "G13_single_dim_scale_error_named"],
                    "M6_tr3_always_blocking": ["G14_Tr3_registers_warn_on_mainline_only"],
                    "M9_missing_detection_vacuous": ["G10_clear_stats_bites_Ts",
                                                     "G11_missing_keys_bites_Ts"]}
INPROC_FLIP_PLAN["M11_provenance_label_vacuous"] = ["G37_missing_provenance_bites_Tp4"]
INPROC_FLIP_PLAN["M10_bc_admission_gate_vacuous"] = ["G38_bc_admission_tooth_polarity"]
INPROC_FLIP_PLAN["M19_arm_prefix_mislabel"] = ["G36_stats_file_arm_identity"]
# 裁定 90.4-1 的极性构造族（G43/G44/G45/G49/G50）与名实审计（G46）：分工同样是**实测**出来的，
# 不是一句"M20 全能"。WHY 这五条走进程内探针而不走文件级 matrix 比对：它们判的是**构造**（合成帧 +
# 固定种子），构造在 `inprocess_probes()` 里跑，变异体副本里跑的是同一份代码 ⇒ 极性翻转可直接归因到
# 被改的那一行。G46 例外（它读源码文件），但探针副本的 ROOT = 变异体目录 ⇒ 读到的就是变异后的源码。
INPROC_FLIP_PLAN["M20_headroom_consumption_zeroed"] = ["G44_polarity_side_asymmetry_escape_vs_deficit",
                                                       "G49_polarity_table_matches_ruling_90_4_1"]
INPROC_FLIP_PLAN["M22_widen_headroom_zeroed"] = ["G45_small_overflow_is_warned_never_red"]
INPROC_FLIP_PLAN["M23_tiv_always_true"] = ["G43_iv_is_measured_tracks_recompute",
                                           "G49_polarity_table_matches_ruling_90_4_1"]
INPROC_FLIP_PLAN["M27_tesc_id_renamed_at_call_site"] = ["G46_tooth_name_citation_integrity"]
INPROC_FLIP_PLAN["M21_coverage_target_ignored"] = ["G50_build_only_coverage_makes_te2_red"]
# 裁定 93.2 / 93.4 的四颗新牙：分工同样是**实测**出来的（设计探针先跑，见 4g-2 的注释）。
# WHY 走进程内而不是文件级 matrix 比对：这四颗牙在 formal-40 真数据上**全绿**（49/49 行），
#   文件级变异体在真数据上翻不动它们 ⇒ 只有构造能分辨"恒绿"与"有牙"（同 G43/G44/G45/G50 的理由）。
INPROC_FLIP_PLAN["M34_tz_denom_zero_tolerated"] = ["G52_Tz_denom_zero_bites"]
INPROC_FLIP_PLAN["M35_tres_resolution_floor_vacuous"] = [
    "G53_Tres_resolution_floor_bites_at_threshold"]
INPROC_FLIP_PLAN["M36_tresw_warn_vacuous"] = [
    "G54_Tresw_warn_and_Tres_hard_red_are_distinguishable"]
INPROC_FLIP_PLAN["M37_tbcad_gate_verdict_ignored"] = ["G55_Tbcad_admission_requires_green_gate"]
INPROC_M1_IDS = sorted(i for v in INPROC_FLIP_PLAN.values() for i in v)
# M3（落盘侧重算 center/gain）应当把这一条翻 False
INPROC_M3_IDS = ["G15_identity_payload_covers_start_pose"]

# --------- 主线臂（--s1-lerobot）的谓词：与基线臂分开，因为基线三臂**不含**主线行 ---------
def _arm_rows(mx, arm):
    return [(i, r) for i, r in rows_by(mx) if r.get("arm") == arm]


def pred_G27(mx):
    """**权威 npz 臂**（裁定 90.4-4 + 93.1/93.2）：8 行、**全绿**、全矩阵无一处不可解释的红；
    牙集合与 Tp5 归属正确；标签必须是 BC 档 `formal40_bc_source` 且 `admissible_for_bc=true`。

    ⚠ **本谓词的极性在裁定 93.1 处翻了**（原名 `G27_mainline_red_fully_explained`，已改名 =
    红线 `gate_name_must_match_gate_semantics`：名字不许继续承诺一条不再判的约束）。
    修前主线 8 行**全红**（`Tb` 分辨率代价 8/8 + F2 行 `Tr3` 下限不实质 4/8），判的是"红得可解释"。
    93.1 把这两颗**阈值状态 = `registered_measurement_not_a_judgment`** 的牙转成 WARN
    （`blocking=False`）⇒ 主线 8 行**应当全绿**；换上去的硬红是 93.2 的 `Tz`（除零族、绝对硬红）
    与 `Tres`（逐维分辨率下限、全量口径、D 定标），两颗在 formal-40 **真实数据**上都必须绿
    （D 的验收条款：真实数据绿 + 各自变异体红）。
    ⇒ 判的是三件事：① 该绿的地方绿；② 93.1 转 WARN 的两颗牙没有偷偷变回 RED（= 未经 D 裁定就
    撤回 93.1）；③ **全矩阵**（含必红臂）没有一处 `unexplained_red_teeth`。
    **仍不判"主线档可以进 BC"**：BC 准入 = `Tbcad`（AND 闸 verdict）+ A2 侧自己复算 sha 对账。
    """
    ml = _arm_rows(mx, "s1_mainline_path_check")
    mf = mx.get("mainline_finding") or {}
    union = sorted({t["id"] for _, r in rows_by(mx) for t in (r.get("teeth") or [])})
    # Tp5 **生效**的行（不是"id 出现"的行 —— 不适用的臂也 append 一条 N_A）
    tp5_rows = sorted(i for i, r in rows_by(mx)
                      if any(t["id"] == TP5 and t.get("applies_when") and t.get("status") != "N_A"
                             for t in (r.get("teeth") or [])))
    bc_idx = sorted(i for i, _ in _arm_rows(mx, "s1_bc_admission_mustred"))
    hard_not_green = sorted({t["id"] for _, r in ml for t in (r.get("teeth") or [])
                             if t["id"] in RULING_93_2_HARD_TEETH and t.get("status") != "PASS"})
    downgraded_back_to_red = sorted({t["id"] for _, r in ml for t in (r.get("teeth") or [])
                                     if t["id"] in RULING_93_1_WARN_TEETH
                                     and t.get("status") == "RED"})
    unexplained_anywhere = sorted({i for i, r in rows_by(mx) if (r.get("unexplained_red_teeth") or [])})
    return (len(ml) == MAINLINE_ROW_COUNT
            and all(r["verdict"] == "PASS" for _, r in ml)
            and all(not (r.get("red_ids") or []) for _, r in ml)
            and not hard_not_green
            and not downgraded_back_to_red
            and not unexplained_anywhere
            and mf.get("all_red_explained") is True
            and mf.get("n_mainline_rows_red") == 0
            and not (mf.get("tr3_red_on_f1_rows_must_be_empty") or [])
            and not [1 for _, r in ml if "Tconsistency_raise_matches_verdict" in red_ids(r)]
            and union == EXPECT_TEETH_MAINLINE
            and tp5_rows == bc_idx
            # 裁定 90.4-4：BC 档标签**只**由 npz 权威臂产
            and all(r.get("stats_provenance") == FORMAL40_LABEL for _, r in ml)
            and all((r.get("bc_admission") or {}).get("admissible_for_bc") is True for _, r in ml)
            and mf.get("stats_provenance") == FORMAL40_LABEL
            and (mf.get("reader_role") or "").startswith("authority"))


def pred_G28(mx):
    """BC 准入必红臂（裁定 85.4-3 点名的牙）：8 行全红、每行都由 **Tp5** 咬、标签与消费方对得上。

    裁定 90.4-4 之后本臂吃的是**交叉核对臂的标签** `formal40_lerobot_crosscheck`（不是 pilot 标签）：
    它证明的是"结构上进不了 BC 的那条读路径，其 stats 喂给 BC 配置必红"，与数据批次无关。"""
    bc = _arm_rows(mx, "s1_bc_admission_mustred")
    return (len(bc) == BC_ARM_ROW_COUNT
            and all(r["verdict"] == "RED" for _, r in bc)
            and all(TP5 in red_ids(r) for _, r in bc)
            and all(r.get("bc_admission_tooth_fired") for _, r in bc)
            and all(r.get("stats_provenance") == CROSSCHECK_LABEL for _, r in bc)
            and all(r.get("consumer") == nc.CONSUMER_BC for _, r in bc)
            and all((r.get("bc_admission") or {}).get("admissible_for_bc") is False for _, r in bc))


def pred_G30(mx):
    """**一行一文件**：不许两行 claim 同一个 stats 文件，且行内两处 sha 与 files[] 三方一致。

    这条是本轮实测到的真缺陷的回归闸：修前 41 行只有 25 个不同 `stats_file`，
    `env_derived_diagnostic__quantiles..._0.05.json` 被 3 行同时 claim、磁盘上只剩最后写的 hold 相那份
    ⇒ 16 行的 `roundtrip.sha256_12` 指向已不存在的文件状态（缺陷类 ⑨ 引用过期）。
    """
    rws = [r for r in mx.get("rows", []) if r.get("stats_file")]
    names = [r["stats_file"] for r in rws]
    files = {(f.get("path") or "").split("/")[-1]: f for f in (mx.get("files") or [])}
    if not rws or len(names) != len(set(names)):
        return False
    if set(names) != set(files):
        return False
    for r in rws:
        if not r.get("stats_file_sha256_12"):
            return False
        if r["stats_file_sha256_12"] != (r.get("roundtrip") or {}).get("sha256_12"):
            return False
        if files[r["stats_file"]].get("sha256_12") != r["stats_file_sha256_12"]:
            return False
    return True


# --------- 裁定 90.4-1 / 90.4-3 / 90.4-4 的谓词 + 名实相符元闸（裁定 87.2-1） ---------
EXPECT_CALIBERS = ("heldout", "build", "all")     # 与 `B.CALIBER_NAMES` 机器互核（见 pred_G41）
# 测量完整性：闸**自己**从 conformance 块重算，不采信生成器的 `measurement_complete` 布尔值
COMPLETENESS_PER_DIM_FIELDS = ("excess_above", "excess_below", "n_frames_out_per_dim",
                              "n_frames_above_per_dim", "n_frames_below_per_dim")


def _teeth_map(row: dict) -> dict:
    return {t["id"]: t for t in (row.get("teeth") or [])}


def _recompute_measurement_complete(conf: dict) -> dict:
    """闸侧重算「越界测量是否完整」（三态）。判据与契约层同形，但**独立实现**。"""
    if not conf:
        return {"complete": None, "why": "无 conformance 块（未测 ≠ 测到不完整）"}
    status = conf.get("measurement_status")
    if status != "measured":
        return {"complete": False, "why": f"measurement_status={status!r}（三态：不是 measured）"}
    nd = conf.get("n_dims")
    bad_len, nonfinite, missing = [], [], []
    for f in COMPLETENESS_PER_DIM_FIELDS:
        v = conf.get(f)
        if v is None:
            missing.append(f)
            continue
        if not isinstance(v, (list, tuple)) or (nd is not None and len(v) != nd):
            bad_len.append(f)
            continue
        try:
            if not all(np.isfinite(np.asarray(v, dtype=np.float64))):
                nonfinite.append(f)
        except (TypeError, ValueError):
            nonfinite.append(f)
    for f in ("headroom_consumption_max", "window_escape", "dims_out"):
        if conf.get(f) is None:
            missing.append(f)
    complete = not (missing or bad_len or nonfinite)
    return {"complete": bool(complete), "missing": missing, "bad_length": bad_len,
            "nonfinite": nonfinite,
            "agrees_with_self_report": (None if conf.get("measurement_complete") is None
                                        else bool(conf.get("measurement_complete") == complete))}


# 行级"一致性"红标签：它**不是牙**，由生成器 `eval_verdict` 在"契约层算出红却没抛异常"时拼进 `red[]`
# （= 恒绿闸的形态）。与 `ROW_TAG_IDS` 同族，但只有一处产出点 ⇒ 单列，便于审计规则 7 点名。
CONSISTENCY_TAG = "Tconsistency_raise_matches_verdict"


def name_semantics_audit(mx: dict) -> dict:
    """元闸 `gate_name_must_match_gate_semantics`（裁定 87.2-1 / 90.4-1 牙③）的**结构侧**。

    规则：牙名承诺了什么，闸就机器核它确实判了那个 —— 不采信生成器/契约层的自报布尔值。
    五条可机器核的名 → 实映射：
      1. `*_is_measured` ⇒ `ok` 必须等于**闸侧重算**的测量完整性；且越界量本身不得让它红；
      2. `*_is_warned`   ⇒ `blocking` 必须 False，且 status 永不为 RED；
      3. `T*_no_*`（断言"没有 X"）⇒ **主线行**上 `blocking` 必须 True（名字承诺的硬约束不许变软）；
         非主线行允许**声明式降级**，但降级理由必须写在牙自己身上（`blocking_reason` 非空）——
         本轮实测：诊断档 16 处 `blocking=False` 全部带理由（"诊断档的 held-out 牙降为 warning"），
         属合法降级，不是名实不符；把它们判红 = 闸自己在造 假红（裁定 72-2 审点③）。
      4. `*_heldout`     ⇒ 该行必须真的吃了 held-out 帧；**没有留出集的行**（本轮实测 9 行：
         8 行 hold 相 + 1 行 YAM 必红臂）牙名承诺的对象不存在 ⇒ 牙与行都必须**显式披露**
         `eval_scope`，且牙级 scope == 行级 scope == 行级旗标（三者互相锁死，缺一即红）；
      5. 撤回极性的旧 id ⇒ 不得出现（名字承诺一条已撤回的约束）；
      6. 行级 `expected_red_teeth`（设计意图声明）⇒ 每个 id 必须①真实存在于本行牙集合、
         ②在本行确实是红的。**这条来自本轮实测到的真缺陷**：生成器的行级 `expected_red_teeth`
         赋值行曾写 `["Td_clip_ratio_cap"]`（一个盘上从未存在过的 id），无消费方 ⇒ 静默错。（引用改成**名字锚点**：兄弟文件的绝对行号会被任何一次编辑静默推走，本轮实测到两起）
      7. 行级 `red_ids` 的每个 token 必须是**已知对象**：本行的牙 id ∪ `ROW_TAG_IDS` ∪ `CONSISTENCY_TAG`。
         **这条来自本轮实测到的真缺陷（幻影红标签）**：牙的 `required` 文案里合法地含中文分号
         （`Tesc` 的 required 写了"…不是调参项；裁定 90.6-1 明令不得放宽"），而红信息曾以 `"；"`
         拼接、下游再 `split("；")` ⇒ 切出一个**根本不是牙**的 token（原型跑里主线 8 行各多一个
         `裁定`），污染 `red_ids` 与 `unexplained_red_teeth`（闸会报一条现场找不到对应牙的"无法解释的红"）。
         根因已修在两处（`nc.RED_MESSAGE_SEPARATOR` 改 `"\n"` + 生成器改读结构化 `payload["red"]`）；
         **本规则是第二道**：无论分隔符将来怎么改、无论谁从字符串反解，token 落不进已知对象集合就红。
         它当时是**潜伏**缺陷（真数据上 `Tesc` 不红 ⇒ 不触发），会在裁定 90.6-2 那个 regime 首次出现窗口
         逃逸时正好响 ⇒ 属于"改闸前必须先看卫语句原文"这条纪律要挡的形态。
    """
    viol: list[dict] = []
    n_teeth = 0
    measured_agree = 0
    n_downgrade_accepted = 0
    n_heldout_disclosed = 0
    n_expected_red_checked = 0
    n_red_ids_checked = 0
    for i, r in rows_by(mx):
        tt = _teeth_map(r)
        conf = r.get("declared_interval_conformance") or {}
        rc = _recompute_measurement_complete(conf) if conf else None
        row_flag = r.get("eval_frames_are_held_out")
        row_scope = r.get("eval_scope")
        # (4a) 行级旗标与行级 scope 必须自洽（两处都是生成器写的 ⇒ 互核，不信任何一处）
        if row_scope is not None and (row_flag is True) != (row_scope == nc.EVAL_SCOPE_HELD_OUT):
            viol.append({"row": i, "tooth": None, "rule": "4a_row_flag_vs_row_scope_inconsistent",
                         "eval_frames_are_held_out": row_flag, "eval_scope": row_scope})
        exp_red = r.get("expected_red_teeth")
        if exp_red is not None:
            n_expected_red_checked += 1
            absent = [x for x in exp_red if x not in tt]
            not_red = [x for x in exp_red if x in tt and tt[x].get("status") != "RED"]
            if absent:
                viol.append({"row": i, "tooth": absent, "rule": "6_expected_red_teeth_id_absent",
                             "expected_red_teeth": exp_red, "row_tooth_ids": sorted(tt)})
            if not_red:
                viol.append({"row": i, "tooth": not_red, "rule": "6_expected_red_teeth_not_red",
                             "statuses": {x: tt[x].get("status") for x in not_red}})
        rid = r.get("red_ids")
        if rid is not None:                       # 三态：字段不存在 ⇒ 不判（不假装判过）
            n_red_ids_checked += 1
            known = set(tt) | set(ROW_TAG_IDS) | {CONSISTENCY_TAG}
            phantom = [x for x in rid if x not in known]
            if phantom:
                viol.append({"row": i, "tooth": phantom,
                             "rule": "7_red_ids_token_is_not_a_known_object",
                             "red_ids": list(rid), "known_ids_sample": sorted(known)[:12],
                             "n_known": len(known)})
        for tid, t in tt.items():
            n_teeth += 1
            applies = bool(t.get("applies_when"))
            if tid in WITHDRAWN_TOOTH_IDS:
                viol.append({"row": i, "tooth": tid, "rule": "5_withdrawn_id_reappeared",
                             "observed": t.get("status")})
            if tid.endswith("_is_measured") and applies:
                ok_recomputed = (None if rc is None else rc["complete"])
                if ok_recomputed is not None:
                    measured_agree += 1
                    if bool(t.get("ok")) is not bool(ok_recomputed):
                        viol.append({"row": i, "tooth": tid, "rule": "1_is_measured_ok_mismatch",
                                     "tooth_ok": t.get("ok"), "gate_recomputed": ok_recomputed,
                                     "recompute_detail": rc})
                # 越界量本身不得让它红：measurement 完整 + 有越界维 ⇒ 不得 RED
                if (rc or {}).get("complete") and (conf.get("dims_out") or []) \
                        and t.get("status") == "RED":
                    viol.append({"row": i, "tooth": tid, "rule": "1_red_on_magnitude_not_measurement",
                                 "dims_out": conf.get("dims_out")})
            if tid.endswith("_is_warned") and applies:
                if bool(t.get("blocking")) is not False:
                    viol.append({"row": i, "tooth": tid, "rule": "2_is_warned_must_not_block",
                                 "blocking": t.get("blocking")})
                if t.get("status") == "RED":
                    viol.append({"row": i, "tooth": tid, "rule": "2_is_warned_must_never_be_red",
                                 "status": t.get("status")})
            if re.match(r"^T[a-z0-9]+_no_", tid) and applies:
                if bool(t.get("blocking")) is not True:
                    declared_downgrade = (not bool(r.get("mainline"))
                                          and bool((t.get("blocking_reason") or "").strip()))
                    if declared_downgrade:
                        n_downgrade_accepted += 1
                    else:
                        viol.append({"row": i, "tooth": tid, "rule": "3_no_assertion_must_block",
                                     "blocking": t.get("blocking"),
                                     "mainline": r.get("mainline"),
                                     "blocking_reason": t.get("blocking_reason")})
            if tid.endswith("_heldout"):
                t_scope = t.get("eval_scope")
                # (4b) 牙级 scope 必须与行级 scope 一致（牙不许比行乐观）
                if row_scope is not None and t_scope != row_scope:
                    viol.append({"row": i, "tooth": tid, "rule": "4b_tooth_scope_differs_from_row",
                                 "tooth_eval_scope": t_scope, "row_eval_scope": row_scope})
                if row_flag is True:
                    if t_scope != nc.EVAL_SCOPE_HELD_OUT:
                        viol.append({"row": i, "tooth": tid,
                                     "rule": "4_heldout_name_without_heldout_frames",
                                     "tooth_eval_scope": t_scope})
                else:
                    # 没有留出集 ⇒ 必须显式披露（牙级 note + 行级 scope 都在），否则牙名在撒谎
                    if (t_scope is None or t_scope == nc.EVAL_SCOPE_HELD_OUT
                            or not (t.get("eval_scope_note") or "").strip()
                            or t_scope not in nc.KNOWN_EVAL_SCOPES):
                        viol.append({"row": i, "tooth": tid,
                                     "rule": "4_heldout_name_without_heldout_frames",
                                     "eval_frames_are_held_out": row_flag,
                                     "tooth_eval_scope": t_scope,
                                     "tooth_eval_scope_note": t.get("eval_scope_note"),
                                     "n_eval_frames": r.get("n_eval_frames"),
                                     "n_build_frames": r.get("n_build_frames")})
                    else:
                        n_heldout_disclosed += 1
    parity = set(SCHEMA_NEED) == set(nc.SCHEMA_REQUIRED_KEYS)
    return {"n_rows": len(mx.get("rows") or []), "n_teeth_audited": n_teeth,
            "n_measurement_clauses_recomputed": measured_agree,
            "n_declared_downgrades_accepted": n_downgrade_accepted,
            "n_heldout_teeth_disclosed_no_split": n_heldout_disclosed,
            "n_rows_with_expected_red_teeth": n_expected_red_checked,
            "n_rows_with_red_ids_audited": n_red_ids_checked,
            "schema_key_parity": bool(parity),
            "schema_key_parity_detail": {"gate_SCHEMA_NEED": sorted(SCHEMA_NEED),
                                         "contract_SCHEMA_REQUIRED_KEYS":
                                             sorted(nc.SCHEMA_REQUIRED_KEYS)},
            "violations": viol, "n_violations": len(viol), "ok": bool(not viol and parity),
            "rules": ["1_is_measured_ok_mismatch", "1_red_on_magnitude_not_measurement",
                      "2_is_warned_must_not_block", "2_is_warned_must_never_be_red",
                      "3_no_assertion_must_block", "4_heldout_name_without_heldout_frames",
                      "4a_row_flag_vs_row_scope_inconsistent", "4b_tooth_scope_differs_from_row",
                      "5_withdrawn_id_reappeared", "6_expected_red_teeth_id_absent",
                      "6_expected_red_teeth_not_red",
                      "7_red_ids_token_is_not_a_known_object", "schema_key_parity"],
            "authority": "裁定 87.2-1（规则原文）+ 90.4-1 牙③ + 缺陷类 ⑮（牙的名与实不符）"}


# 行级"红标签"id：它们**不是牙**（不出现在 `teeth[]` 里），而是生成器在检测到不一致时拼进
# `red[]` 的标签。健康跑里它们**不出现** ⇒ 无法从产物派生（这正是必须显式登记的原因）。
# 作为补偿（防止这份常量自己漂移成遮羞布）：每一项都必须在生成器源码里**真的被当红标签用**
# （同一行里出现 `red = list(red)` 或 `"tooth_id"`），只在散文里提到不算 ⇒ 漂移时本审计自己红。
ROW_TAG_IDS = ("Trt_payload_roundtrip", "Trt_bc_admission_stale")
# 裁定 93.6 起产物里多了一类 **run 级牙**：它不属于任何一行（`rows[*].teeth` 里没有它），
# 而是挂在 `matrix["run_level_teeth"]` 上。引用完整性审计（G46）的 live 集合必须包含它们，
# 否则契约层里那句 `tid = "Txr_..."` 会被自己的审计判成"悬空引用"（本轮首跑实测到过）。
# 与 `ROW_TAG_IDS` 同族：常量 + 产物派生**两路都算**，任何一路缺席都不至于假红。
RUN_LEVEL_TOOTH_IDS = ("Txr_crosscheck_freshness_is_registered",)
ROW_TAG_ANCHOR_PATTERNS = ("red = list(red)", '"tooth_id"')
# 牙 id 的词法：`T` + 1–4 个小写字母 + 可选 1 位数字 + `_` + 其余。
# ⚠ 修前这里是 `\bT(?:[a-z]{1,4})_[A-Za-z0-9_]+`，它**匹配不到带数字的 id**
#   （`Td2_clip_heldout` / `Te2_no_illegal_bin_heldout` / `Tp5_…`：`[a-z]{1,4}` 后紧跟的是数字
#   而不是 `_`）⇒ 本轮实测：这些 id 的悬空引用一条都抓不到，而它们正是本轮真缺陷的所在
#   （生成器 `expected_red_teeth` 写了不存在的 `Td_clip_ratio_cap`，恰好**不带数字**才被抓到）。
TOOTH_ID_RE = re.compile(r"\bT[a-z]{1,4}[0-9]?_[A-Za-z0-9_]+")
HISTORY_MARKERS = ("修前", "撤回", "已被", "旧 id", "was ", "withdrawn", "before_", "改名",
                   "不存在", "从未存在", "已修")
HISTORY_MARKER_WINDOW = 2      # 标记词允许出现在引用行的 ±2 行内（散文里"引用 + 说明"常跨行）
CITATION_SRCS = ("harness/norm_contract.py", "scripts/c2_build_norm_stats.py",
                 "scripts/c2_gate_norm_contract.py")
CORRECTION_JSON_REL = "physical_range_correction/correction.json"


def tooth_name_citation_audit(root: Path | None = None, mx: dict | None = None) -> dict:
    """源码里**引用到的牙 id** 必须真实存在（或显式带历史标记词）。

    WHY：本轮 C2 自查 + 本审计实测共命中 **5 处真缺陷** ——
    ①② `harness/norm_contract.py` 的 `coverage_must_cover` / `widen_to_cover` 散文引了
    `Tlo_no_state_below_declared_interval` / `Tovr_upside_overflow_is_warned`（改名时漏改引用）；
    ③ 生成器 `expected_red_teeth` 写了 `Td_clip_ratio_cap`（一个从未存在过的 id，且**无消费方**
    ⇒ 静默错）；④⑤ 本闸自己的散文里写了缩写 id（`Tiv_is_measured` 一类）—— 缩写读起来像真 id，
    而盘上没有那个对象。这正是规则 `gate_name_must_match_gate_semantics` 与裁定 92.3
    （散文身份可核）的形态：引用一个盘上没有的对象，读者无法核，而它读起来像是有据的。

    live 集合的三个来源（**都不是**本函数的自觉声明）：
      a. `EXPECT_TEETH` —— 由 `pred_G21` 与产物里的实际牙集合**逐条相等**锁死；
      b. 产物派生 —— 传进来的 matrix 里实际出现的牙 id 与红标签；
      c. `ROW_TAG_IDS` —— 见上（带源码锚点自证）。
    另：`WITHDRAWN_TOOTH_IDS` 在源码里**允许出现**（它们的存在就是为了登记"这条极性已撤回"），
    但作为**产出的牙**由 `name_semantics_audit` 规则 5 判红。
    """
    root = root or ROOT
    live = (set(EXPECT_TEETH) | set(WITHDRAWN_TOOTH_IDS) | set(ROW_TAG_IDS)
            | set(RUN_LEVEL_TOOTH_IDS))
    produced_teeth: set[str] = set()
    produced_tags: set[str] = set()
    # 裁定 93.6 起产物里多了一类**run 级牙**（`matrix["run_level_teeth"]`，目前只有
    # `Txr_crosscheck_freshness_is_registered`）：它不属于任何一行 ⇒ 不在 `rows[*].teeth` 里。
    # 不把它算进 live 集合，本审计就会把自己新加的牙判成"悬空引用"（本轮首跑实测到过：
    # `dangling={"Txr_crosscheck_freshness_is_registered": [["harness/norm_contract.py", 538]]}`）。
    produced_run_level: set[str] = set()
    if mx:
        for t in (mx.get("run_level_teeth") or []):
            if t.get("id"):
                produced_run_level.add(str(t["id"]))
    live |= produced_run_level
    if mx:
        for _, r in rows_by(mx):
            for t in (r.get("teeth") or []):
                if t.get("id"):
                    produced_teeth.add(str(t["id"]))
            for tag in (r.get("red_ids") or []):
                produced_tags.add(str(tag))
    live |= produced_teeth | produced_tags
    cjp = NORM_DIR / CORRECTION_JSON_REL
    correction_ids: set[str] = set()
    if cjp.is_file():
        try:
            cj = json.loads(cjp.read_text(encoding="utf-8"))
            correction_ids = {str(t.get("id")) for t in (cj.get("teeth") or []) if t.get("id")}
        except (OSError, ValueError):
            correction_ids = set()
    live |= correction_ids

    # ROW_TAG_IDS 的源码锚点自证（常量漂移 ⇒ 本审计自己红）
    bsrc = (root / BUILD).read_text(encoding="utf-8") if (root / BUILD).is_file() else ""
    blines = bsrc.splitlines()
    anchor: dict[str, dict] = {}
    for tid in ROW_TAG_IDS:
        hits = [n for n, ln in enumerate(blines, start=1)
                if tid in ln and any(pat in ln for pat in ROW_TAG_ANCHOR_PATTERNS)]
        anchor[tid] = {"anchored": bool(hits), "anchor_lines": hits[:4],
                       "n_mentions_in_builder": sum(1 for ln in blines if tid in ln)}
    anchor_ok = all(v["anchored"] for v in anchor.values())

    cited: dict[str, list] = {}
    n_citations = 0
    n_files = 0
    for relp in CITATION_SRCS:
        fp = root / relp
        if not fp.is_file():
            continue
        n_files += 1
        lines = fp.read_text(encoding="utf-8").splitlines()
        for ln_no, line in enumerate(lines, start=1):
            for m in TOOTH_ID_RE.finditer(line):
                tok = m.group(0)
                n_citations += 1
                if tok in live:
                    continue
                lo = max(0, ln_no - 1 - HISTORY_MARKER_WINDOW)
                hi = min(len(lines), ln_no + HISTORY_MARKER_WINDOW)
                marker_hits = [{"line": k + 1, "marker": h}
                               for k in range(lo, hi) for h in HISTORY_MARKERS if h in lines[k]]
                cited.setdefault(tok, []).append(
                    {"file": relp, "line": ln_no,
                     "has_history_marker": bool(marker_hits),
                     "history_marker_hits": marker_hits[:4],
                     "text": line.strip()[:160]})
    dangling = {k: v for k, v in cited.items() if any(not c["has_history_marker"] for c in v)}
    return {"n_source_files_scanned": n_files, "n_citations": n_citations,
            "live_tooth_ids": sorted(live),
            "live_id_sources": {"expect_teeth": len(EXPECT_TEETH),
                                "run_level_tooth_ids_const": len(RUN_LEVEL_TOOTH_IDS),
                                "run_level_teeth_in_matrix": sorted(produced_run_level),
                                "withdrawn": len(WITHDRAWN_TOOTH_IDS),
                                "row_tag_ids": len(ROW_TAG_IDS),
                                "produced_teeth_in_matrix": len(produced_teeth),
                                "produced_red_tags_in_matrix": len(produced_tags),
                                "correction_json_teeth": sorted(correction_ids),
                                "matrix_provided": mx is not None},
            "row_tag_id_anchors": anchor, "row_tag_anchor_ok": bool(anchor_ok),
            "id_regex": TOOTH_ID_RE.pattern,
            "regex_covers_digit_ids": bool(TOOTH_ID_RE.search("Td2_clip_heldout")),
            "cited_non_live_ids": {k: v for k, v in sorted(cited.items())},
            "dangling_citations": dangling,
            "n_dangling": len(dangling),
            "ok": bool(not dangling and anchor_ok and n_citations > 0 and n_files == len(CITATION_SRCS)),
            "rule": ("引用到的牙 id ∈ live 集合（EXPECT_TEETH ∪ 产物实际出现 ∪ ROW_TAG_IDS ∪ "
                     "RUN_LEVEL_TOOTH_IDS ∪ 勘误件牙 ∪ 已撤回 id），**或**该引用在 ±"
                     f"{HISTORY_MARKER_WINDOW} 行内带历史标记词（{list(HISTORY_MARKERS)}）"
                     "⇒ 历史引用合法、悬空引用红；ROW_TAG_IDS 必须有源码锚点"),
            "authority": "裁定 92.3（散文身份可核）+ 87.2-1（名实相符）+ 缺陷类 ⑮ + 92.6（间接量自查）"}


def pred_G39(mx):
    """裁定 90.4-1 的极性在**真数据**上落地：四把牙的状态与 blocking 逐条对上，旧 id 不复活。"""
    arms = ("s1_mainline_path_check", "s1_lerobot_crosscheck")
    rows = [(i, r) for i, r in rows_by(mx) if r.get("arm") in arms]
    if len(rows) != MAINLINE_ROW_COUNT + CROSSCHECK_ROW_COUNT:
        return False
    for _, r in rows:
        tt = _teeth_map(r)
        conf = r.get("declared_interval_conformance") or {}
        if conf.get("measurement_status") != "measured":
            return False
        # `Tovr` 的期望状态**由数据决定**：有越界维 ⇒ 必须 WARN；一个都没有 ⇒ PASS。
        # 写死 WARN 会把"下一批数据没有越界"误判成失败（裁定 87.7：数值不可搬）。
        exp = dict(IV_EXPECT_STATUS_MAINLINE)
        exp["Tovr_out_of_interval_overflow_is_warned"] = ("WARN" if (conf.get("dims_out") or []) else "PASS")
        for tid in IV_TEETH:
            t = tt.get(tid)
            if t is None or t.get("status") != exp[tid]:
                return False
            if bool(t.get("blocking")) is not IV_EXPECT_BLOCKING[tid]:
                return False
        if any(t in tt for t in WITHDRAWN_TOOTH_IDS):
            return False
        # 硬红的两把牙判据值必须**已测**且当前不成立（formal-40 的实测形态）
        if conf.get("window_escape") is not False:
            return False
        if conf.get("headroom_consumption_max") is None:
            return False
        if not (float(conf["headroom_consumption_max"]) < nc.WINDOW_ESCAPE_RATIO):
            return False
        if (conf.get("dims_downside_deficit") or []) or (conf.get("dims_window_escape") or []):
            return False
    return True


def pred_G40(mx):
    """裁定 90.4-4：npz = 权威（BC 档标签），lerobot = 交叉核对臂（结构上进不了 BC）。"""
    ml = _arm_rows(mx, "s1_mainline_path_check")
    cc = _arm_rows(mx, "s1_lerobot_crosscheck")
    bc = _arm_rows(mx, "s1_bc_admission_mustred")
    cs = mx.get("crosscheck_status") or {}
    ra = mx.get("reader_authority_ruling_90_4_4") or {}
    ms = mx.get("mainline_status") or {}
    comp = cs.get("ruling_90_4_4_compliance") or {}
    return (len(ml) == MAINLINE_ROW_COUNT and len(cc) == CROSSCHECK_ROW_COUNT
            and len(bc) == BC_ARM_ROW_COUNT
            and all(r.get("stats_provenance") == FORMAL40_LABEL for _, r in ml)
            and all(r.get("stats_provenance") == CROSSCHECK_LABEL for _, r in cc)
            and all(r.get("stats_provenance") == CROSSCHECK_LABEL for _, r in bc)
            and all((r.get("bc_admission") or {}).get("admissible_for_bc") is True for _, r in ml)
            and all((r.get("bc_admission") or {}).get("admissible_for_bc") is False
                    for _, r in (cc + bc))
            and CROSSCHECK_LABEL in nc.KNOWN_STATS_PROVENANCES
            and CROSSCHECK_LABEL not in nc.BC_ADMISSIBLE_PROVENANCES
            and FORMAL40_LABEL in nc.BC_ADMISSIBLE_PROVENANCES
            and comp.get("ok") is True and comp.get("must_be_false") is True
            and ra.get("authority_ran_this_run") is True
            and ra.get("crosscheck_ran_this_run") is True
            and ra.get("bc_label_only_from_authority") is True
            and ms.get("status") == "built_from_npz_authority_interface"
            and ms.get("stats_provenance") == FORMAL40_LABEL)


def pred_G41(mx):
    """裁定 90.4-3 的触发判据必须**逐口径 × 逐行**落盘；口径分叉 ⇒ `triggered` 必须是 null。

    WHY 这条是 P0 级：修前生成器只报 held-out 单口径的 `triggered=true`，而 D 在 90.2 #16 / §18.6
    引的是全量口径（该口径下**不**触发）⇒ 一个假 P0 升级项会被 D 当成"已触发的裁定"执行。
    """
    mf = mx.get("mainline_finding") or {}
    cb = mf.get("condition_b_resolution") or {}
    tg = cb.get("ruling_90_4_3_trigger") or {}
    cals = tg.get("calibers") or {}
    ms = mx.get("mainline_status") or {}
    if not cals or tuple(sorted(cals)) != tuple(sorted(EXPECT_CALIBERS)):
        return False
    if tuple(B.CALIBER_NAMES) != EXPECT_CALIBERS:      # 两处清单漂移 ⇒ 红（不靠自觉）
        return False
    measured = [c for c in EXPECT_CALIBERS
                if (cals.get(c) or {}).get("measurement_status") == "measured"]
    if len(measured) != len(EXPECT_CALIBERS):
        return False                                    # 有口径没测 ⇒ 不得当成"没触发"
    trigs = {cals[c]["triggered"] for c in measured}
    dependent = (len(trigs) > 1)
    per_row_ok = all(cals[c].get("n_rows") == MAINLINE_ROW_COUNT
                     and len(cals[c].get("bins_occupied_per_dim_per_row") or []) == MAINLINE_ROW_COUNT
                     and len(cals[c].get("dims_below_min_bins_per_row") or []) == MAINLINE_ROW_COUNT
                     for c in measured)
    r0 = cb.get("row0_representativeness") or {}
    trig_ok = ((tg.get("triggered") is None and tg.get("governing_caliber") == "OPEN_question_to_d")
               if dependent else
               (tg.get("triggered") in (True, False) and tg.get("caliber_dependent") is False))
    return (per_row_ok
            and tg.get("caliber_dependent") is dependent
            and trig_ok
            and len(r0.get("row_ids") or []) == MAINLINE_ROW_COUNT
            and r0.get("near_constant_dims_identical_across_rows") is not None
            and r0.get("declared_interval_conformance_identical_across_rows") is not None
            and set(r0.get("trigger_row0_only_vs_all_rows") or {}) == set(EXPECT_CALIBERS)
            and "condition_b_resolution_first_row" not in mf
            and "condition_b_resolution_first_row" not in ms
            and ms.get("condition_b_resolution") is not None
            and bool(ms.get("ruling_90_4_3_trigger_caliber"))
            and (tg.get("corroborating_probe") or {}).get("measurement_status") in ("measured",
                                                                                   "not_measured"))


def pred_G42(mx):
    """元闸（结构侧）：每把牙的**名字承诺**与**实际判据**相符（`name_semantics_audit`）。"""
    a = name_semantics_audit(mx)
    return bool(a["ok"]) and a["n_teeth_audited"] > 0 and a["n_measurement_clauses_recomputed"] > 0


def pred_G57(mx):
    """**登记不许缩水**（裁定 93.1-3）：`Tb`/`Tr3` 转 WARN 之后，逐维读数字段一个都不许少。

    WHY 需要这条谓词：93.1 把两颗牙从 RED 降成 WARN，最常见的"顺手"回归是**连登记一起删**
    （牙不红了 ⇒ 有人觉得逐维读数没用了）。D 明令：转 WARN 后每行仍必须落
    `bins_occupied_per_dim`（14 维逐维）等 6 个字段，并给了变异体口径 =「删掉
    `bins_occupied_per_dim` 任一维 ⇒ 必须红」。本谓词就是那条牙的闸侧实现（M39 = 截掉一维）。
    判据只在**主线 8 行**上判（诊断档行的 `summary_all` 合法地为 None，见 `summary_calibers`）。
    """
    ml = _arm_rows(mx, "s1_mainline_path_check")
    if len(ml) != MAINLINE_ROW_COUNT:
        return False
    missing, short = [], []
    for i, r in ml:
        # ⚠ `n_dims` **只从 `summary` 取**：`near_constant` 块里也有一个叫 `n_dims` 的键，但它是
        #   **近常量维的个数**（本轮实测 = 2），不是动作维数（14）。修前用 `b.get("n_dims", n_dims)`
        #   逐块覆盖 ⇒ 最后一块把它写成 2 ⇒ 逐维数组长度 14 != 2 ⇒ 本谓词在**真产物**上恒 False
        #   （= C2 自己写出的假红；裁定 92.6「取上一个/取典型值」同族，已由 dry-run 实测拦下）。
        n_dims = ((r.get("summary") or {}).get("n_dims")
                  if isinstance(r.get("summary"), dict) else None)
        for blk, fields in NO_SHRINK_REQUIRED_FIELDS.items():
            b = r.get(blk)
            if not isinstance(b, dict):
                missing.append(f"row{i}:{blk}")
                continue
            for f in fields:
                if f not in b:
                    missing.append(f"row{i}:{blk}.{f}")
        for f in NO_SHRINK_ROW_FIELDS:
            if f not in r:
                missing.append(f"row{i}:{f}")
        # 逐维数组的**长度**必须等于维数：截掉一维（M39 的形态）长度就对不上
        for path in (("summary", "bins_occupied_per_dim"), ("summary_all", "bins_occupied_per_dim")):
            arr = ((r.get(path[0]) or {}).get(path[1]))
            if arr is not None and n_dims is not None and len(arr) != int(n_dims):
                short.append(f"row{i}:{path[0]}.{path[1]} len={len(arr)} != n_dims={n_dims}")
        rc = r.get("bins_occupied_per_dim_resolution_caliber")
        ho = r.get("heldout_bins_occupied_per_dim")
        if rc is not None and n_dims is not None and len(rc) != int(n_dims):
            short.append(f"row{i}:resolution_caliber len={len(rc)} != n_dims={n_dims}")
        if r.get("correctness_blind_dims_status") == "measured":
            if ho is None or (n_dims is not None and len(ho) != int(n_dims)):
                short.append(f"row{i}:heldout_bins len={None if ho is None else len(ho)} "
                             f"!= n_dims={n_dims}（status=measured 却给不出逐维读数）")
            if r.get("correctness_blind_dims") is None:
                missing.append(f"row{i}:correctness_blind_dims（measured 却缺席）")
    # ② 裁定 94.3 的**不许硬编码**：盲点维必须能从逐维读数**复算**出来。
    #   WHY 这一条：D 的原话是「必须由逐维实测算出、不许硬编码 6」。只登记一个 `[0,3,5,7,10,12]`
    #   是没法机器分辨"算出来的"还是"抄上去的"⇒ 这里用**同一份逐维数组 + 同一个阈值**在闸侧复算，
    #   两者不等 ⇒ 红。换数据集/换切分后盲点维会变，抄死的那份就会在这里露出来。
    fnd = (mx.get("mainline_finding") or {}).get("heldout_per_dim_blindness_ruling_94_3") or {}
    if fnd.get("measurement_status") == "measured":
        pats = fnd.get("heldout_bins_occupied_per_dim_distinct") or []
        thr = fnd.get("blind_dim_threshold")
        if not pats or thr is None:
            missing.append("heldout_per_dim_blindness_ruling_94_3（measured 却缺逐维数组或阈值）")
        else:
            recomputed = sorted({int(d) for p in pats for d in range(len(p)) if int(p[d]) < int(thr)})
            registered = sorted(int(x) for x in (fnd.get("correctness_blind_dims_union") or []))
            if recomputed != registered:
                short.append(f"blind_dims_not_recomputable(registered={registered} "
                             f"recomputed_from_per_dim={recomputed} threshold={thr})")
    return not missing and not short


def pred_G58(mx):
    """**93.1 的极性没被偷偷撤回、93.2 明令保护的八颗牙一颗都没被放宽**（机器核，不靠 diff 散文）。

    D 的验收条款：`Tr1`/`Te1`/`Te2`/`Tesc`/`Td1`/`Td2`/`Tp5`/`Tsat` **一颗都没被放宽**
    （D 会 diff 前后牙清单）。本谓词把那条验收变成每轮实测：
      ① `Tb`/`Tr3` 在**每一行**都是 `blocking=False`（93.1 落地；变回 True = 未经 D 裁定就撤回）；
      ② `Tz`/`Tres`/`Tbcad` 在每一行都是 `blocking=True`（93.2/93.4 的硬红不许降软）；
      ③ `Tresw` 在每一行都是 `blocking=False`（它是 WARN 登记牙，升成硬红 = 把 Ⅱ 类当 Ⅰ 类，
         正是 D 自己记的同型错误 #20）；
      ④ 受保护的八颗在每一行都是 `blocking=True`，**唯一例外**已显式登记在
         `NON_BLOCKING_EXCEPTION_ARMS`/`_TEETH`（诊断档的 held-out 家族，93.1 之前就存在，
         与上一轮权威跑 run_20260930_073852 逐格相同）。
    本谓词对**基线臂矩阵**也成立（⇒ 进 `MATRIX_PREDS`，由 M6 在 baseline 面上翻它）。
    """
    bad = []
    for i, r in rows_by(mx):
        arm = r.get("arm")
        for t in (r.get("teeth") or []):
            tid, blk = t.get("id"), bool(t.get("blocking"))
            if tid in RULING_93_1_WARN_TEETH and blk:
                bad.append(f"row{i}:{tid} blocking=True（93.1 被撤回）")
            elif tid in RULING_93_2_HARD_TEETH and not blk:
                bad.append(f"row{i}:{tid} blocking=False（93.2 的硬红被降软）")
            elif tid == RULING_93_4_BC_GATE_TOOTH and not blk:
                bad.append(f"row{i}:{tid} blocking=False（93.4 的 AND 闸被降软）")
            elif tid == RULING_93_2_WARN_TOOTH and blk:
                bad.append(f"row{i}:{tid} blocking=True（WARN 登记牙被升成硬红）")
            elif tid in PROTECTED_TEETH_93_2 and not blk:
                if not (arm in NON_BLOCKING_EXCEPTION_ARMS
                        and tid in NON_BLOCKING_EXCEPTION_TEETH):
                    bad.append(f"row{i}:{tid} blocking=False（受保护的牙被放宽，arm={arm}）")
    seen = {t.get("id") for _, r in rows_by(mx) for t in (r.get("teeth") or [])}
    return (not bad) and bool(seen) and all(x in seen for x in RULING_93_1_WARN_TEETH)


MATRIX_PREDS_MAINLINE = {"G27_mainline_rows_green_no_unexplained_red": pred_G27,
                         "G28_bc_admission_arm_red_via_Tp5": pred_G28,
                         "G30_one_stats_file_per_row": pred_G30,
                         "G39_polarity_ruling_90_4_1_on_real_data": pred_G39,
                         "G40_reader_authority_ruling_90_4_4": pred_G40,
                         "G41_trigger_caliber_split_ruling_90_4_3": pred_G41,
                         "G42_tooth_name_matches_semantics": pred_G42,
                         # 裁定 93.1-3 的「登记不许缩水」+ 93.1/93.2 的极性保护（主线面上也判一遍）
                         "G57_no_shrink_registration_ruling_93_1_3": pred_G57,
                         "G58_ruling_93_polarity_not_relaxed": pred_G58}


# --------- 闸侧**独立复算**（不采信生成器的自报；G29/G31 的判据来源） ---------
def reader_evidence_recheck(mx: dict, root: Path) -> dict:
    """把 **交叉核对臂**（`crosscheck_reader_evidence`，parquet 侧）的每一项**自己重算一遍**再比。

    为什么必须重算而不是读生成器的布尔值：生成器自报"我按集分组、组内升序、上转无损、与 npz 逐位相同"，
    若闸只读这些字段，那 M12/M14/M15 那类"生成器自己算错或谎报"的形态就抓不到
    （= 缺陷类 ⑦「自检未执行完整路径」的同族）。这里用**闸自己的代码**重算，与生成器无共享实现。

    裁定 90.4-4 之后本函数读的证据块换名（`mainline_reader_evidence` 现在属**npz 权威臂**，
    其复算见 `npz_authority_recheck`），且行过滤换成 `s1_lerobot_crosscheck`。
    """
    ev = mx.get("crosscheck_reader_evidence") or {}
    out = {"present": bool(ev), "clauses": {}, "recorded": {}, "recomputed": {}}
    if not ev:
        out["why"] = "matrix 无 crosscheck_reader_evidence（交叉核对臂没跑）"
        out["ok"] = False
        return out
    import pyarrow as pa
    import pyarrow.parquet as pq
    ds = root / ev["dataset_dir"]
    lr = ds / "pi05_lerobot" if (ds / "pi05_lerobot" / "data").is_dir() else ds
    files = sorted((lr / "data").glob("chunk-*/*.parquet"))
    if not files:
        out["why"] = f"{lr}/data/chunk-*/*.parquet 不存在 ⇒ 无法复算"
        out["ok"] = False
        return out
    t = pa.concat_tables([pq.read_table(f, columns=["observation.state", "episode_index",
                                                    "frame_index", "index", "task_index"]) for f in files])
    col = t.column("observation.state").combine_chunks()
    s32 = col.values.to_numpy(zero_copy_only=False).reshape(
        len(col), int(col.type.list_size)).astype(np.float32, copy=False)
    s64 = s32.astype(np.float64)
    d = t.to_pydict()
    ep = np.asarray(d["episode_index"], dtype=np.int64)
    fi = np.asarray(d["frame_index"], dtype=np.int64)
    order = np.lexsort((fi, ep))
    frames = s64[order]
    ep_s, fi_s = ep[order], fi[order]
    uniq = sorted(set(int(e) for e in ep.tolist()))
    contig = all(bool(np.all(fi_s[ep_s == e] == np.arange(int((ep_s == e).sum())))) for e in uniq)
    rc = {
        "n_frames": int(frames.shape[0]), "n_episodes": len(uniq), "state_dim": int(col.type.list_size),
        "parquet_storage_dtype": str(col.type.value_type),
        # dtype 口径标签由**闸自己**从 parquet 的存储 dtype 推（不读生成器的字符串）：
        # pyarrow 的 `float` 就是 float32 ⇒ 计算走 float64 就必然是"上转"，标签只能是这一个值。
        "state_dtype_source": ("float32_parquet_upcast_to_float64"
                               if str(col.type.value_type) == "float"
                               else f"<unexpected_storage_dtype:{col.type.value_type}>"),
        "upcast_bitwise_lossless": bool(np.all(s64.astype(np.float32).view(np.uint32)
                                               == s32.view(np.uint32))),
        "raw_order_already_grouped_sorted": bool(np.array_equal(order, np.arange(order.size))),
        "frame_index_contiguous_per_episode": bool(contig),
        "index_column_is_global_arange": bool(np.all(np.asarray(d["index"], dtype=np.int64)
                                                     == np.arange(len(d["index"])))),
        "stray_parquet_outside_chunk_glob": sorted(str(x.relative_to(root)) for x in
                                                   set((lr / "data").rglob("*.parquet")) - set(files)),
        "parquet_sha256_12": [sha12(f) for f in files],
        "demo_manifest_sha256_12": (sha12(ds / "demo_manifest.json")
                                    if (ds / "demo_manifest.json").exists() else None),
    }
    # held-out 划分：闸自己按"每方向最后一整集"重算（方向用 task_index 的分区，独立于 manifest）
    ti_s = np.asarray(d["task_index"], dtype=np.int64)[order]
    ep_dir = {e: sorted(set(int(x) for x in ti_s[ep_s == e].tolist()))[0] for e in uniq}
    hold = sorted(max(e for e, c in ep_dir.items() if c == code)
                  for code in sorted(set(ep_dir.values()))
                  if sum(1 for c in ep_dir.values() if c == code) >= 2)
    m = np.isin(ep_s, hold)
    rc["held_out_episodes"] = hold
    rc["n_build_frames"] = int((~m).sum())
    rc["n_eval_frames"] = int(m.sum())
    npz_p = root / FORMAL40_NPZ
    if npz_p.exists():
        z = np.load(npz_p, allow_pickle=False)
        nb = np.asarray(z["frames"], dtype=np.float64)
        rc["npz_frames_bitwise_equal"] = bool(nb.shape == frames.shape
                                              and np.all(nb.view(np.uint64) == frames.view(np.uint64)))
        ne = np.asarray(z["episode_index"], dtype=np.int64)
        rc["npz_episode_index_identical"] = bool(ne.shape == ep_s.shape and np.array_equal(ne, ep_s))
    rec_g = ev.get("grouping") or {}
    rec_h = ev.get("heldout_split") or {}
    # 行级计数：`mainline_reader_evidence.heldout_split` 与 matrix 的**行**必须说同一件事。
    # 为什么必须三方比（证据块 / 行 / 闸侧复算）：M15 那类"假装切过"的变异体只改**返回的数组**，
    # 证据块里的 n_build/n_eval 仍由真 mask 算出 ⇒ 只比"证据块 vs 闸"看不出问题，
    # 必须把**行**（= 契约层实际吃到的帧数）也拉进来比。
    ml_rows = [r for r in mx.get("rows", []) if r.get("arm") == "s1_lerobot_crosscheck"]
    row_nb = sorted({int(r.get("n_build_frames") or -1) for r in ml_rows}) if ml_rows else []
    row_ne = sorted({int(r.get("n_eval_frames") or -1) for r in ml_rows}) if ml_rows else []
    row_ho = sorted({bool(r.get("eval_frames_are_held_out")) for r in ml_rows}) if ml_rows else []
    pairs = [
        ("n_frames", ev.get("n_frames"), rc["n_frames"]),
        ("n_episodes", ev.get("n_episodes"), rc["n_episodes"]),
        ("state_dim", ev.get("state_dim"), rc["state_dim"]),
        ("parquet_storage_dtype", ev.get("parquet_storage_dtype"), rc["parquet_storage_dtype"]),
        ("upcast_bitwise_lossless", ev.get("upcast_bitwise_lossless"), rc["upcast_bitwise_lossless"]),
        ("raw_order_already_grouped_sorted", rec_g.get("raw_order_already_grouped_sorted"),
         rc["raw_order_already_grouped_sorted"]),
        ("frame_index_contiguous_per_episode", rec_g.get("frame_index_contiguous_per_episode"),
         rc["frame_index_contiguous_per_episode"]),
        ("index_column_is_global_arange", rec_g.get("index_column_is_global_arange"),
         rc["index_column_is_global_arange"]),
        ("stray_parquet_outside_chunk_glob", ev.get("stray_parquet_outside_chunk_glob"),
         rc["stray_parquet_outside_chunk_glob"]),
        ("parquet_sha256_12", [f.get("sha256_12") for f in (ev.get("parquet_files") or [])],
         rc["parquet_sha256_12"]),
        ("demo_manifest_sha256_12", ev.get("demo_manifest_sha256_12"), rc["demo_manifest_sha256_12"]),
        ("held_out_episodes", rec_h.get("held_out_episodes"), rc["held_out_episodes"]),
        ("n_build_frames", rec_h.get("n_build_frames"), rc["n_build_frames"]),
        ("n_eval_frames", rec_h.get("n_eval_frames"), rc["n_eval_frames"]),
        ("npz_frames_bitwise_equal", ((ev.get("crosscheck_vs_b2_npz") or {}).get("frames") or {})
         .get("bitwise_equal"), rc.get("npz_frames_bitwise_equal")),
        ("npz_episode_index_identical",
         ((ev.get("crosscheck_vs_b2_npz") or {}).get("episode_index") or {}).get("identical"),
         rc.get("npz_episode_index_identical")),
        ("state_dtype_source", (ev.get("dtype_declaration") or {}).get("state_dtype_source"),
         rc["state_dtype_source"]),
        # 三方一致：证据块 vs 行（内部一致） + 行 vs 闸侧复算（外部一致）
        ("heldout_n_build_block_vs_rows", rec_h.get("n_build_frames"),
         (row_nb[0] if len(row_nb) == 1 else None)),
        ("heldout_n_eval_block_vs_rows", rec_h.get("n_eval_frames"),
         (row_ne[0] if len(row_ne) == 1 else None)),
        ("heldout_rows_agree_among_themselves", True, (len(row_nb) == 1 and len(row_ne) == 1)),
        ("heldout_rows_claim_held_out", row_ho, ([True] if row_ho == [True] else None)),
        ("heldout_n_build_rows_vs_gate", (row_nb[0] if len(row_nb) == 1 else None),
         rc["n_build_frames"]),
        ("heldout_n_eval_rows_vs_gate", (row_ne[0] if len(row_ne) == 1 else None),
         rc["n_eval_frames"]),
    ]
    for name, a, b in pairs:
        if b is None:
            continue                      # 闸侧算不出（例：npz 不在）⇒ 不判，不假装判过
        out["clauses"][name] = bool(a == b)
        out["recorded"][name] = a
        out["recomputed"][name] = b
    out["n_clauses"] = len(out["clauses"])
    out["failed"] = sorted(k for k, v in out["clauses"].items() if not v)
    out["agreement_ok"] = bool(out["clauses"]) and not out["failed"]
    # 期望值本身也要对（防"两边一起错"）：这几项必须是这个值，不是"相等就行"
    out["expected_values_ok"] = bool(
        rc["upcast_bitwise_lossless"] is True and rc["raw_order_already_grouped_sorted"] is True
        and rc["frame_index_contiguous_per_episode"] is True and rc["state_dim"] == 14
        and rc["n_episodes"] > 0 and rc["n_frames"] > rc["n_eval_frames"] > 0
        and rc["state_dtype_source"] == "float32_parquet_upcast_to_float64"
        and not rc["stray_parquet_outside_chunk_glob"]
        and rc.get("npz_frames_bitwise_equal", True) is True)
    out["ok"] = bool(out["agreement_ok"] and out["expected_values_ok"])
    return out


def npz_authority_recheck(mx: dict, root: Path) -> dict:
    """**权威接口**（npz + `--s1-frames`，裁定 90.4-4）的闸侧独立复算。

    为什么要单独一条（不复用 `reader_evidence_recheck`）：那条判的是 parquet 侧的分组/排序/dtype；
    权威臂的证据块是另一套字段（npz sha、frames content sha、shape/dtype、逐方向集数、与交叉核对臂
    的逐位相等）。**权威臂必须有闸自己的复算**，否则"BC 吃的是哪一份数据"这句话就只有生成器自报。

    复算全部用闸自己的代码（`np.load` + 自己的 lexsort + 自己的 sha 定义），与生成器无共享实现；
    content sha 的定义**照抄产物里写的那一句**（`sha256(float64 C-contiguous bytes)[:12]`），
    因为定义不同就会假红 —— 定义本身也在产物里被登记，可核。
    """
    ev = mx.get("mainline_reader_evidence") or {}
    out = {"present": bool(ev), "clauses": {}, "recorded": {}, "recomputed": {}}
    if not ev:
        out["why"] = "matrix 无 mainline_reader_evidence（权威 npz 臂没跑）"
        out["ok"] = False
        return out
    npz_p = root / (ev.get("npz") or FORMAL40_NPZ)
    if not npz_p.is_file():
        out["why"] = f"npz 不在盘上：{npz_p}"
        out["ok"] = False
        return out
    z = np.load(npz_p, allow_pickle=False)
    fr = np.asarray(z["frames"], dtype=np.float64)
    epi = (np.asarray(z["episode_index"], dtype=np.int64) if "episode_index" in z.files else None)
    content_sha = hashlib.sha256(np.ascontiguousarray(fr).tobytes()).hexdigest()[:12]
    rc = {
        "npz_arrays": sorted(z.files),
        "npz_sha256_12": sha12(npz_p),
        "npz_bytes": npz_p.stat().st_size,
        "frames_shape": list(fr.shape),
        "frames_dtype": str(fr.dtype),
        "frames_content_sha256_12": content_sha,
        "n_frames": int(fr.shape[0]),
        "n_episodes": (len(set(int(e) for e in epi.tolist())) if epi is not None else None),
        "upcast_bitwise_lossless": bool(np.array_equal(fr.astype(np.float32).astype(np.float64), fr)),
        "state_dim": int(fr.shape[1]),
    }
    # held-out 划分：闸自己按"每方向最后一整集"重算。方向码取自 parquet 的 task_index
    # （独立于 npz 与 manifest）；parquet 不在位 ⇒ 该子句**不判**（三态，不假装判过）。
    ho = {"held_out_episodes": None, "n_build_frames": None, "n_eval_frames": None}
    ds = root / ((mx.get("crosscheck_reader_evidence") or {}).get("dataset_dir") or FORMAL40_DIR)
    lr = ds / "pi05_lerobot" if (ds / "pi05_lerobot" / "data").is_dir() else ds
    files = sorted((lr / "data").glob("chunk-*/*.parquet")) if lr.is_dir() else []
    if files and epi is not None:
        import pyarrow as pa
        import pyarrow.parquet as pq
        t = pa.concat_tables([pq.read_table(f, columns=["episode_index", "frame_index",
                                                        "task_index"]) for f in files])
        d = t.to_pydict()
        ep = np.asarray(d["episode_index"], dtype=np.int64)
        fi = np.asarray(d["frame_index"], dtype=np.int64)
        ti = np.asarray(d["task_index"], dtype=np.int64)
        order = np.lexsort((fi, ep))
        ep_s, ti_s = ep[order], ti[order]
        uniq = sorted(set(int(e) for e in ep.tolist()))
        ep_dir = {e: sorted(set(int(x) for x in ti_s[ep_s == e].tolist()))[0] for e in uniq}
        hold = sorted(max(e for e, c in ep_dir.items() if c == code)
                      for code in sorted(set(ep_dir.values()))
                      if sum(1 for c in ep_dir.values() if c == code) >= 2)
        m = np.isin(epi, hold)
        ho = {"held_out_episodes": hold, "n_build_frames": int((~m).sum()), "n_eval_frames": int(m.sum())}
        rc["parquet_frames_bitwise_equal_to_npz"] = None   # 由 reader_evidence_recheck 判（避免两处实现）
    rc.update(ho)
    rec_h = ev.get("heldout_split") or {}
    ml_rows = [r for r in mx.get("rows", []) if r.get("arm") == "s1_mainline_path_check"]
    row_nb = sorted({int(r.get("n_build_frames") or -1) for r in ml_rows}) if ml_rows else []
    row_ne = sorted({int(r.get("n_eval_frames") or -1) for r in ml_rows}) if ml_rows else []
    row_na = sorted({int(r.get("n_all_frames") or -1) for r in ml_rows
                     if r.get("n_all_frames") is not None}) if ml_rows else []
    pairs = [
        ("npz_sha256_12", ev.get("npz_sha256_12"), rc["npz_sha256_12"]),
        ("npz_bytes", ev.get("npz_bytes"), rc["npz_bytes"]),
        ("npz_arrays", ev.get("npz_arrays"), rc["npz_arrays"]),
        ("frames_shape", ev.get("frames_shape"), rc["frames_shape"]),
        ("frames_dtype", ev.get("frames_dtype"), rc["frames_dtype"]),
        ("frames_content_sha256_12", ev.get("frames_content_sha256_12"), rc["frames_content_sha256_12"]),
        ("n_frames", ev.get("n_frames"), rc["n_frames"]),
        ("n_episodes", ev.get("n_episodes"), rc["n_episodes"]),
        ("upcast_bitwise_lossless", ev.get("upcast_bitwise_lossless"), rc["upcast_bitwise_lossless"]),
        ("held_out_episodes", rec_h.get("held_out_episodes"), rc["held_out_episodes"]),
        ("n_build_frames", rec_h.get("n_build_frames"), rc["n_build_frames"]),
        ("n_eval_frames", rec_h.get("n_eval_frames"), rc["n_eval_frames"]),
        # 三方一致：证据块 vs **行**（契约层实际吃到的帧数）vs 闸侧复算
        ("rows_n_build_agree", (row_nb[0] if len(row_nb) == 1 else None), rc["n_build_frames"]),
        ("rows_n_eval_agree", (row_ne[0] if len(row_ne) == 1 else None), rc["n_eval_frames"]),
        ("rows_n_all_agree", (row_na[0] if len(row_na) == 1 else None), rc["n_frames"]),
        ("crosscheck_arm_bitwise_equal_flag", ev.get("crosscheck_arm_frames_bitwise_equal"), True),
    ]
    for name, a, b in pairs:
        if b is None or a is None:
            continue                      # 闸侧算不出（例：parquet 不在）⇒ 不判，不假装判过
        out["clauses"][name] = bool(a == b)
        out["recorded"][name] = a
        out["recomputed"][name] = b
    out["n_clauses"] = len(out["clauses"])
    out["failed"] = sorted(k for k, v in out["clauses"].items() if not v)
    out["agreement_ok"] = bool(out["clauses"]) and not out["failed"]
    # 期望值本身也要对（防"两边一起错"）：不许写死数据集数字（裁定 87.7 数值不可搬），
    # 只核**内部自洽**与结构性质。
    out["expected_values_ok"] = bool(
        rc["upcast_bitwise_lossless"] is True
        and rc["state_dim"] == 14
        and rc["n_frames"] == int(rc["frames_shape"][0])
        and (rc["n_episodes"] or 0) > 0
        and (rc["held_out_episodes"] is None
             or (rc["n_build_frames"] + rc["n_eval_frames"] == rc["n_frames"]
                 and rc["n_eval_frames"] > 0))
        and len(rc["npz_sha256_12"]) == 12 and len(rc["frames_content_sha256_12"]) == 12
        and rc["frames_content_sha256_12"] != rc["npz_sha256_12"])   # 两个 sha 是不同对象，不得混用
    out["ok"] = bool(out["agreement_ok"] and out["expected_values_ok"])
    out["recomputed_full"] = rc
    return out


def mainline_status_recheck(mx: dict, root: Path) -> dict:
    """`mainline_status` 的自报状态 vs 磁盘现状（裁定 85.4-2-5：status 必须是**可执行态**）。"""
    ms = mx.get("mainline_status") or {}
    ev = mx.get("mainline_reader_evidence") or {}
    out = {"clauses": {}, "recorded": {}, "recomputed": {}}
    if not ms:
        out["why"] = "matrix 无 mainline_status"
        out["ok"] = False
        return out
    # 裁定 90.4-4：主线状态文件现在描述的是 **npz 权威臂**；parquet 侧的时刻只作交叉核对。
    npz_p = root / (ev.get("npz") or FORMAL40_NPZ)
    cc_ev = mx.get("crosscheck_reader_evidence") or {}
    ds = root / (cc_ev.get("dataset_dir") or FORMAL40_DIR)
    lr = ds / "pi05_lerobot" if (ds / "pi05_lerobot" / "data").is_dir() else ds
    files = sorted((lr / "data").glob("chunk-*/*.parquet")) if lr.is_dir() else []
    def _ts(x):
        try:
            return _dt.datetime.fromisoformat(str(x)).timestamp()
        except Exception:                                     # noqa: BLE001
            return None
    mt_parquet = max((f.stat().st_mtime for f in files), default=None)
    mt_npz = (npz_p.stat().st_mtime if npz_p.is_file() else None)
    mt = max([x for x in (mt_parquet, mt_npz) if x is not None], default=None)
    ck = _ts(ms.get("checked_at"))
    dm = ds / "demo_manifest.json"
    out["clauses"] = {
        # 裁定 90.4-4：可执行态的名字换了（权威接口 = npz）；旧名 `built_from_lerobot` 已作废
        "status_is_executable": ms.get("status") == "built_from_npz_authority_interface",
        "checked_path_present": bool(ms.get("checked_path")) and (root / str(ms.get("checked_path"))).exists(),
        "checked_path_is_the_npz_authority": (str(ms.get("checked_path") or "").endswith("states_14d.npz")
                                              and (root / str(ms.get("checked_path"))) == npz_p),
        "checked_at_not_older_than_data": bool(ck is not None and mt is not None and ck >= mt),
        "npz_sha_matches_disk": (bool(npz_p.is_file()) and ms.get("checked_path_sha256_12") == sha12(npz_p)),
        "npz_manifest_sha_matches_disk": ((ms.get("npz_manifest_sha256_12") is None)
                                          or (not (npz_p.parent / "manifest.json").exists())
                                          or ms.get("npz_manifest_sha256_12")
                                          == sha12(npz_p.parent / "manifest.json")),
        "demo_manifest_sha_matches_disk": ((not dm.exists())
                                           or ms.get("demo_manifest_sha256_12") is None
                                           or (ms.get("demo_manifest_sha256_12") == sha12(dm))),
        # 权威臂的标签**必须**是 BC 档，且**必须**可进 BC（与交叉核对臂相反 —— 两者弄反就是 90.4-4 要挡的形态）
        "provenance_is_formal40_bc_source": ms.get("stats_provenance") == FORMAL40_LABEL,
        "not_for_bc_is_false": ms.get("not_for_bc") is False,
        "bc_admission_admits": (ms.get("bc_admission") or {}).get("admissible_for_bc") is True,
        # 改名后的键必须真的在（本轮实测到过：改名后旧键留下、值静默变 null）
        "no_stale_renamed_keys": ("condition_b_resolution_first_row" not in ms),
        "condition_b_resolution_present": ms.get("condition_b_resolution") is not None,
        "trigger_caliber_block_present": bool(ms.get("ruling_90_4_3_trigger_caliber")),
    }
    out["recorded"] = {"status": ms.get("status"), "checked_path": ms.get("checked_path"),
                       "checked_at": ms.get("checked_at"),
                       "checked_path_sha256_12": ms.get("checked_path_sha256_12"),
                       "npz_manifest_sha256_12": ms.get("npz_manifest_sha256_12"),
                       "demo_manifest_sha256_12": ms.get("demo_manifest_sha256_12"),
                       "stats_provenance": ms.get("stats_provenance"), "not_for_bc": ms.get("not_for_bc"),
                       "bc_admission": ms.get("bc_admission")}
    out["recomputed"] = {"parquet_mtime_max": mt_parquet, "npz_mtime": mt_npz, "checked_at_ts": ck,
                         "npz_sha256_12": (sha12(npz_p) if npz_p.is_file() else None),
                         "npz_manifest_sha256_12": (sha12(npz_p.parent / "manifest.json")
                                                    if (npz_p.parent / "manifest.json").exists() else None),
                         "parquet_sha256_12": [sha12(f) for f in files],
                         "demo_manifest_sha256_12": (sha12(dm) if dm.exists() else None),
                         "n_parquet_files": len(files)}
    out["failed"] = sorted(k for k, v in out["clauses"].items() if not v)
    out["ok"] = not out["failed"]
    return out


MATRIX_PREDS = {"G1_baseline_verdict_pass": pred_G1,
                "G2_normal_rows_all_pass": pred_G2,
                "G3_stress_rows_all_red": pred_G3,
                "G4_must_red_row_red_with_source_tooth": pred_G4,
                "G5_roundtrip_all_match": pred_G5,
                "G6_schema_and_applies_when": pred_G6,
                "G21_baseline_invariants": pred_G21,
                "G30_one_stats_file_per_row": pred_G30,
                # 93.1/93.2 的极性保护在**基线臂**上也必须成立（⇒ M6 能在 baseline 面上翻它）
                "G58_ruling_93_polarity_not_relaxed": pred_G58}


# ---------------- 文件级变异体：独立目录 + 活对象自证 ----------------
MUTATIONS = {
    # ⚠ 锚点**已随实现改名而更新**（本轮实测到的锚点漂移）：`"；".join(red)` 在契约层把分隔符
    #   抽成 `RED_MESSAGE_SEPARATOR` 之后失配（count=0）⇒ `build_mutant` 拒绝构造 ⇒ M1 全族
    #   （G16/G25 + 4 条进程内探针）会静默变成"未执行"。这类漂移由 G51 在**跑变异体之前**统一拦。
    "M1_non_raising": [("harness/norm_contract.py",
                        '''    if red:
        raise NormContractViolation(RED_MESSAGE_SEPARATOR.join(red), payload=payload)
    return payload''',
                        '''    return payload   # __c2_mutant__ M1：算出红也不抛（恒绿闸的形态）''')],
    "M2_near_constant_always_empty": [("harness/norm_contract.py",
                                       "    return sorted(int(i) for i in np.nonzero(span / rng <= rel_tol)[0])",
                                       "    return []   # __c2_mutant__ M2：恒空 ⇒ Tr1 恒绿")],
    "M3_payload_recompute_identity": [("harness/norm_contract.py",
                                       '''        arr["center"] = center.tolist()
        arr["gain"] = (2.0 / denom).tolist()''',
                                       '''        arr["center"] = np.asarray(stats["median"], dtype=np.float64).tolist()   # __c2_mutant__ M3
        arr["gain"] = (2.0 / np.maximum(np.asarray(stats["span_q99_q01"], dtype=np.float64),
                                        np.asarray(floors, dtype=np.float64))).tolist()''')],
    "M5_schema_field_dropped": [("harness/norm_contract.py",
                                 '''               "required": required, "red_when": required, "observed": observed,''',
                                 '''               "required": required, "observed": observed,   # __c2_mutant__ M5：删掉 red_when''')],
    # ⚠ 锚点已随裁定 **93.1-1** 重指：Tr3 那一行修前是 `blocking=bool(mainline)`，
    #   93.1-1 把它改成 `blocking=False`（红 → WARN）⇒ 原文本 count=0（G51 会报）。
    #   变异体的**语义不变**：把 `blocking`/`applies_when` 一起装回"恒 blocking + 恒适用"，
    #   于是诊断臂上 Tr3 出 RED 而不是 N_A（= 裁定 72-2 的假红形态），且主线臂上 Tr3 由 WARN
    #   变回 RED（= 未经 D 裁定就撤回 93.1）⇒ 两个面都能被 G14/G23/G58 看见。
    "M6_tr3_always_blocking": [("harness/norm_contract.py",
                                "          blocking=False, applies_when=bool(mainline),",
                                "          blocking=True, applies_when=True,   # __c2_mutant__ M6：不适用也 blocking ⇒ 诊断臂假红")],
    # M7/M8（本轮新增，2026-09-30 00:5x）：目的是给 **G4 / G3** 也造出"实测翻转"证据。
    # 之前这两条 check 只写了 `mutant_that_proves_it="M1_non_raising"`，而 M1 只去掉 raise、
    # 行级 red 集合并不变 ⇒ 按裁定 83.2 它们其实**没有被任何变异体证明过**（= 可能是恒真的）。
    "M7_stats_source_gate_vacuous": [("harness/norm_contract.py",
                                      "    src_ok = (source in MAINLINE_ALLOWED_SOURCES) if mainline else True",
                                      "    src_ok = True   # __c2_mutant__ M7：源分级失效 ⇒ YAM 必红行的 Tr2 不再咬")],
    "M8_heldout_teeth_vacuous": [("harness/norm_contract.py",
                                  '          worst["clip_ratio"] <= th.clip_ratio_cap,',
                                  "          True,   # __c2_mutant__ M8a：Td2 恒真（held-out clip 牙被拔）"),
                                 ("harness/norm_contract.py",
                                  '    tooth("Te2_no_illegal_bin_heldout", "held-out 帧无非法 bin -1", not illegal,',
                                  '    tooth("Te2_no_illegal_bin_heldout", "held-out 帧无非法 bin -1", True,   # __c2_mutant__ M8b')],
    # M9（本轮新增）：`Ts` 有**自己**的提前抛路径（norm_contract.py:424-430），所以 M1（只删末尾
    # `if red: raise`）**翻不动** G10/G11 —— 这是 00:5x 实测出来的，不是推测。要证 G10/G11 非恒真，
    # 必须拔"缺失检测"本身。
    "M9_missing_detection_vacuous": [("harness/norm_contract.py",
                                      "    missing = [k for k in need_keys if k not in stats or np.asarray(stats[k]).size == 0]",
                                      "    missing = []   # __c2_mutant__ M9：缺失/空数组检测失效 ⇒ Ts 不再点名（静默 IDENTITY 形态）")],
    # M10（本轮新增，裁定 85.4-3 的牙）：把 BC 准入判定拔成恒真 ⇒ 喂 pilot10 的 stats 给 BC 也不再红。
    # 这是"同源硬闸恒真"的形态：闸还在、字段还在、就是永远放行。
    "M10_bc_admission_gate_vacuous": [("harness/norm_contract.py",
                                       '          adm["admissible_for_bc"],',
                                       "          True,   # __c2_mutant__ M10：BC 准入恒放行 ⇒ Tp5 不再咬")],
    # M11（本轮新增）：把"标签必须属于已知集合"拔成恒真 ⇒ 缺标签/非法标签也放行。
    # ⚠ 检测面**不在 matrix**：生成器现在每行都显式传标签 ⇒ M11 不改变任何行的判定；
    #   它的痕迹只能在**进程内探针**里看到（G37：不传 stats_provenance ⇒ 必须红）。
    #   这与"M1 翻不动 G10/G11"是同族教训：翻转分工必须实测，不能想当然。
    # ⚠⚠ 本变异体**必须同时拔两处**（02:43 全量跑实测到的缺陷，G25/G24 因此红）：
    #   Tp4 的校验在 `norm_contract.py` 里有**两个**实现点 —— ①`tooth(...)` 的 ok 实参，
    #   ②紧随其后的**提前抛卫语句**（`early_raise=Tp4`）。首版只拔了①，而 G37 的判据里
    #   含 `early_raise == Tp4` 这一子句 ⇒ ②仍在抛 ⇒ 谓词在变异体副本里**仍为 True**
    #   （run_20260930_024312 实测：`in_mutant_copy.G37=true`、`ok=false`）。
    #   教训与 M9 同族：**一个判据有几个实现点，变异体就得拔几个**，只拔一个 = 假翻转台账。
    "M11_provenance_label_vacuous": [("harness/norm_contract.py",
                                      "          (prov in KNOWN_STATS_PROVENANCES) and consumer_known,",
                                      "          True,   # __c2_mutant__ M11：标签校验恒真 ⇒ Tp4 不再咬"),
                                     ("harness/norm_contract.py",
                                      "    if prov not in KNOWN_STATS_PROVENANCES or not consumer_known:",
                                      "    if False:   # __c2_mutant__ M11：提前抛卫语句失效 ⇒ early_raise 不再等于 Tp4")],
    # M12（本轮新增）：把 `--s1-lerobot` 的分组排序键写反（主/次键对调）⇒ 帧序被打乱。
    # 为什么"取消排序"不行：pilot-10 的 parquet **本来就已经**按集分组、集内升序
    # （实测 `raw_order_already_grouped_sorted=true`）⇒ no-op 变异体观察不到任何东西。
    # 必须**主动打乱**才有可检测痕迹：帧序错 ⇒ 与 B2 npz 的逐位互核失配（G30）、
    # 且 `raw_order_already_grouped_sorted` 变 False（G35）。
    "M12_lerobot_grouping_broken": [("scripts/c2_build_norm_stats.py",
                                     "    order = np.lexsort((fi, ep))                     # 主键 episode_index，次键 frame_index",
                                     "    order = np.lexsort((ep, fi))   # __c2_mutant__ M12：主/次键对调 ⇒ 帧序被打乱")],
    # M13：把主线档"允许红的牙"清单缩小（去掉 Tsat）⇒ 真实的 Tsat 红立刻变成"无法解释的红"。
    # 意义：证明 G27 判的**不是**"有没有红"，而是"红是否被逐条解释"。
    # M13：缩小"允许红的牙"⇒ 真红变成**无法解释**的红（G27 的对象）。
    # ⚠ 锚点已随重构更新：修前指向生成器里的手写常量 `_HELDOUT_FAMILY`，而裁定 87.3-2 之后允许清单
    #   改为**由测量派生**（`derive_allowed_red_from_measurement` + `TOOTH_AUTHORIZED_BY_FACT`），
    #   `_HELDOUT_FAMILY` 已从生成器里消失（本轮实测 count=0）。现锚点 = 把 `Tb` 从授权表里摘掉：
    #   `Tb` 在 formal-40 主线 8 行上**确实红**（授权事实 C），摘掉授权 ⇒ `unexplained_red_teeth`
    #   非空 ⇒ `pred_G27` 翻 False。语义与 M13 原意（缩小清单 ⇒ 真红无法解释）一致。
    # ⚠ 锚点已随裁定 **93.1** 重指（第二类锚点漂移：文本仍可能唯一命中，但语义已过期）。
    #   修前锚点是 `"Tb_scale_floor_effective": ("C",),`；93.1 之后 `Tb` 转 WARN、结构上进不了
    #   `red_ids`，C2 已把它从授权表里**故意摘掉**（留绊线）⇒ 原锚点 count=0。
    #   改指 `Tp5`（BC 必红臂 8/8 行确实红，且授权事实 E 是唯一授权来源）：摘掉它 ⇒
    #   那 8 行的红立刻变成 `unexplained_red_teeth` ⇒ `pred_G27` 的"全 matrix 无无法解释的红"
    #   子句翻 False。语义与 M13 原意（缩小授权清单 ⇒ 真红无法解释）一致。
    "M13_allowed_red_set_shrunk": [("scripts/c2_build_norm_stats.py",
                                    '    "Tp5_bc_admission_requires_formal40_bc_source": ("E",),',
                                    '    # __c2_mutant__ M13：把 Tp5 从授权表摘掉 ⇒ BC 必红臂的真红变成无法解释的红')],
    # M14：dtype 口径**谎报**（把 float32 上转写成 parquet 原生 float64）⇒ G29 的独立复算必须抓到。
    "M14_dtype_misdeclared": [("scripts/c2_build_norm_stats.py",
                               '    "state_dtype_source": "float32_parquet_upcast_to_float64",',
                               '    "state_dtype_source": "float64_parquet_native",   # __c2_mutant__ M14：dtype 口径谎报')],
    # M15：**假装切过** held-out（build == eval == 全部帧，却仍报 held_out=True）。
    # 这是 C2 本轮 01:5x 真踩过的缺陷形态（帧级切 ⇒ 相邻近重复帧同时进 build 与 eval）。
    "M15_fake_heldout_split": [("scripts/c2_build_norm_stats.py",
                               '''    return (frames[~mask], frames[mask],
            {"held_out": True, "rule": "按集切：每个方向的最后一整集留出作 eval",''',
                               '''    return (frames, frames,   # __c2_mutant__ M15：假装切过（eval 就是 build）
            {"held_out": True, "rule": "按集切：每个方向的最后一整集留出作 eval",''')],
    # M16：把臂标识从文件名里抹掉 ⇒ 三臂重新互相覆写（本轮实测到过的真缺陷）。
    "M16_arm_suffix_removed": [("scripts/c2_build_norm_stats.py",
                                '            name = f"{source}__{case}__{fam_name}_{coef}{file_suffix}.json"',
                                '            name = f"{source}__{case}__{fam_name}_{coef}.json"   # __c2_mutant__ M16：臂标识被抹掉')],
    # M18：`checked_at` 写死成一个过去时刻 ⇒ "落笔时刻真去看过那个路径"这条纪律失效（G31 的对象）。
    # 对应本轮真踩过的缺陷：01:3x C2 写"等 B2"时数据其实已落地 25 min。
    # ⚠ **锚点已重指（本轮实测到的第二类锚点漂移：文本仍唯一命中，但语义已过期）**。
    #   修前锚点指的是 `crosscheck_status`（parquet 侧）那一块；裁定 90.4-4 之后 G31 读的是
    #   **npz 权威臂**的 `mainline_status`（`status="built_from_npz_authority_interface"`）⇒
    #   实测：M18 副本产出的 `mainline_status.checked_at = 2026-09-30T06:56:03+08:00`（**根本没被冻结**），
    #   `mainline_status_recheck` 13 条 clause 全 True、`failed=[]` ⇒ M18 跑了却翻不动任何 check。
    #   **检出方式**：翻转台账里 25 个 plans 变异体只有 M18 一条翻转都没有（G31 因此缺台账被 G24 判红）。
    #   ⇒ 教训：`G51`（锚点唯一）只能拦"文本失配"，拦不住"文本还在、指向的对象已换"；
    #     **语义漂移的唯一可靠检出面是翻转台账**（每个变异体至少翻一条 check）。
    #   **顺带查出的一处沉默缺口（不由本变异体覆盖，显式登记不许沉默）**：
    #     `crosscheck_status.checked_at`（生成器 `crosscheck_status = {` 块内那处；**引用不写绝对行号**，本轮实测该号被一次 +19 行的编辑推走 19 行）
    #     （`crosscheck_status` 只被 `pred_G40` 读 `ruling_90_4_4_compliance` 一项）⇒ 交叉核对臂的
    #     "落笔时刻真去看过"这条纪律目前**没有牙**。C2 不自行扩权补牙（交叉核对臂不是 BC 输入），
    #     已写进交接件的"待触发"清单，请 D 记一句以免成为沉默缺口。
    "M18_checked_at_frozen": [("scripts/c2_build_norm_stats.py",
                               '''            "checked_path": rel(s1),
            "checked_at": now_iso(),''',
                               '''            "checked_path": rel(s1),
            "checked_at": "2026-09-29T00:00:00+08:00",   # __c2_mutant__ M18：状态时刻写死''')],
    # M19：hold 臂的 representation_version 前缀写成别的臂 ⇒ 文件名/内容与臂不符（G36 的对象）。
    "M19_arm_prefix_mislabel": [("scripts/c2_build_norm_stats.py",
                                 '                   "env-derived-holdphase", mainline=False, eval_frames=None, tag="-holdphase",',
                                 '                   "env-derived-diagnostic", mainline=False, eval_frames=None, tag="-holdphase",   # __c2_mutant__ M19：臂前缀错标')],
    "M4_collector_inline_qpos_formula": [("scripts/c2_collect_env_states.py",
                                          '''    if state_dim in GRIPPER_STATE_DIMS:
        return GRIPPER_QPOS_IDX[state_dim]
    idx = state_dim if state_dim < 6 else state_dim - 1
    q = ARM_QPOS_IDX[idx]
    assert q == (state_dim if state_dim < 6 else state_dim + 1), (
        f"ARM_QPOS_IDX 与 tasks/sim.py:61-69 的映射不一致：state_dim={state_dim} → qpos={q}")
    return q''',
                                          '''    if state_dim in GRIPPER_STATE_DIMS:
        return GRIPPER_QPOS_IDX[state_dim]
    return state_dim if state_dim < 6 else state_dim + 2   # __c2_mutant__ M4：内联公式，绕开声明映射''')],
    # ── 本轮新增（裁定 90.4-1 的双向牙 + 90.4-3/90.4-4 的口径牙 + 名实审计牙）──────────────
    # M20：**测量说谎**（头寸消耗比恒 0）⇒ `Tesc` 失声。与 M32 成一对（一个把消耗比压成 0、
    #   一个把它推过 1.0）⇒ 证明 `Tesc` 的判据**真的读了那个量**，而不是恒绿/恒红。
    "M20_headroom_consumption_zeroed": [("harness/norm_contract.py",
                                         "    ratio = np.where(headroom > 0, exc / headroom, np.inf)",
                                         "    ratio = np.zeros_like(exc)   # __c2_mutant__ M20：消耗比谎报为 0")],
    # M21：覆盖目标失效（裁定 90.4-1 **牙②** 的实现）：`coverage_must_cover` 忽略 target ⇒
    #   覆盖集退回"起态 + build 帧"（= 修前 `build_only` 口径）⇒ held-out 帧不再被保护。
    #   D 的牙② 要求：这必须让 `Te2_no_illegal_bin_heldout` 红（实测见 G50）。
    "M21_coverage_target_ignored": [("harness/norm_contract.py",
                                     "    if target == COVERAGE_TARGET_DECLARED_INTERVAL:",
                                     "    if False:   # __c2_mutant__ M21：忽略 target ⇒ 覆盖集退回 build 帧")],
    # M22：展宽不留头寸 ⇒ **小幅**下侧越界（物理合法、本该被头寸吸收）变成"覆盖不足"硬红。
    #   它咬的是 G45：等于把裁定 90.4-1 刚撤回的极性从下侧装回去（假红）。
    "M22_widen_headroom_zeroed": [("harness/norm_contract.py",
                                   "    delta = headroom_bins * BIN_WIDTH * span / 2.0",
                                   "    delta = np.zeros_like(span)   # __c2_mutant__ M22：展宽不留头寸")],
    # M23：`Tiv` 恒真（裁定 90.4-1 **牙③**）：牙被拔掉、名字还在 ⇒ 必须由元闸
    #   `gate_name_must_match_gate_semantics` 抓到（实现 = G43 的 `nan_in_eval` 构造 + 同一份审计）。
    "M23_tiv_always_true": [("harness/norm_contract.py",
                             '''             bool(iv_conf.get("measurement_status") == "measured"
                  and iv_conf.get("measurement_complete") is True),''',
                             "             True,   # __c2_mutant__ M23：Tiv 恒真（名字还承诺『已被测量』）")],
    # M24/M25：裁定 90.4-3 的**口径分叉**牙。修前生成器只报单口径 ⇒ D 在 90.2 #16 引的全量口径
    #   读数无从核对。M24 把三个口径塌成一个；M25 把逐行聚合截成只有首行（= 用首行代表全臂，
    #   与 D 第 16 号同型错误"用中位数守逐维"同族）。两者都必须让 G41 翻 False。
    "M24_caliber_summary_key_collapsed": [("scripts/c2_build_norm_stats.py",
                                           '    SUMKEY = {"heldout": "summary", "build": "summary_build", "all": "summary_all"}',
                                           '    SUMKEY = {"heldout": "summary"}   # __c2_mutant__ M24：只留一个口径')],
    "M25_caliber_per_row_truncated": [("scripts/c2_build_norm_stats.py",
                                       "            per_dim_by_caliber[cname] = [[int(x) for x in v] for v in vals]",
                                       "            per_dim_by_caliber[cname] = [[int(x) for x in v] for v in vals[:1]]   # __c2_mutant__ M25：只聚合首行")],
    # M26：交叉核对臂**冒充**权威档（裁定 90.4-4 点名要挡的形态：两个读取器产同一个标签
    #   ⇒ 无法回答"BC 到底吃了哪一份"）⇒ G40 必须翻 False。
    "M26_crosscheck_arm_claims_bc_label": [("scripts/c2_build_norm_stats.py",
                                            "            return (nc.STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK,",
                                            "            return (nc.STATS_PROVENANCE_FORMAL40_BC,   # __c2_mutant__ M26：交叉核对臂冒充权威档")],
    # M27：只改**产出点**的牙 id 字面量（所有引用处不动）⇒ 源码里的引用变成悬空 ⇒ G46 必须翻。
    #   这正是本轮实测到的 5 处真缺陷的形态（改名时漏改引用）。
    "M27_tesc_id_renamed_at_call_site": [("harness/norm_contract.py",
                                          '    iv_tooth("Tesc_no_covered_window_escape",',
                                          '    iv_tooth("Tesc_no_covered_window_escape_M27",')],
    # M28：把本轮**真缺陷原样装回去**（生成器曾写一个从未存在过的牙 id 进 `expected_red_teeth`，
    #   而该字段无任何消费方 ⇒ 静默错）⇒ 名实审计规则 6 必须抓到。用真缺陷当变异体是最强的证明形式。
    "M28_expected_red_teeth_absent_id": [("scripts/c2_build_norm_stats.py",
                                          '            r["expected_red_teeth"] = ["Td2_clip_heldout", "Te2_no_illegal_bin_heldout"]',
                                          '            r["expected_red_teeth"] = ["Td_clip_ratio_cap"]   # __c2_mutant__ M28（该 id 从未存在）')],
    # M29：把主线行的 `Te2`（名字承诺"无非法 bin"的硬约束）降为不 blocking ⇒ 审计规则 3 必须抓到。
    "M29_te2_downgraded_on_mainline": [("harness/norm_contract.py",
                                        '          "processor_pi05.py:77 + :81-84", blocking=hard,',
                                        '          "processor_pi05.py:77 + :81-84", blocking=False,')],
    # M30：无论有没有留出集都自称 held-out ⇒ 牙级 scope 与行级 scope 分叉，审计规则 4/4b 必须抓到。
    "M30_eval_scope_always_held_out": [("harness/norm_contract.py",
                                        "    eval_scope = eval_scope_of(eval_frames)",
                                        "    eval_scope = EVAL_SCOPE_HELD_OUT   # __c2_mutant__ M30")],
    # M31：**权威臂**（npz）的证据谎报集数 ⇒ G47 的闸侧独立复算必须抓到（M14 是 parquet 侧的同族）。
    "M31_npz_episode_count_misdeclared": [("scripts/c2_build_norm_stats.py",
                                           '            "n_frames": int(fr.shape[0]), "n_episodes": n_eps_npz,',
                                           '            "n_frames": int(fr.shape[0]), "n_episodes": (n_eps_npz or 0) + 1,   # __c2_mutant__ M31')],
    # M32：裁定 90.4-1 **牙①**：把头寸减半 ⇒ formal-40 实测头寸消耗比 0.7652 翻倍越过 1.0
    #   ⇒ `Tesc` 必须红，且这条红**不得**被 allowed 清单吸收（G39/G27 必须翻 False）。
    #   处置口径（裁定 90.6-1）：不许放宽 1.0，只能升 `headroom_bins` 并新建 representation_version。
    #   ⚠ **必须同时拔掉生成器 :50 的卫语句**（本轮实测：只改常量 ⇒ 生成器在 import 期就
    #   `AssertionError: D 的文书按 1 bin 头寸引用本档读数…` 退出、连 matrix 都不产）。
    #   这条实测**本身就是卫语句有效的证据**（它挡住了"改头寸却沿用 representation_version 读数"
    #   的形态），已按裁定 85.5 的口径登记进 G48 的 `guard_fired_first_attempt` 字段。
    "M32_headroom_bins_halved": [("harness/norm_contract.py",
                                  "HEADROOM_BINS_DEFAULT = 1.0",
                                  "HEADROOM_BINS_DEFAULT = 0.5   # __c2_mutant__ M32：头寸减半"),
                                 ("scripts/c2_build_norm_stats.py",
                                  'assert HEADROOM_BINS == 1.0, "D 的文书按 1 bin 头寸引用本档读数；改这个值 = 换 representation_version"',
                                  'assert True, "D 的文书按 1 bin 头寸引用本档读数"   # __c2_mutant__ M32：卫语句一并拔掉')],
    # M33：**幻影红标签**（本轮实测到的潜伏缺陷，三锚点缺一不可）。
    #   形态：红信息用 `"；"` 拼接（锚点 1）+ 某把**真数据上确实红**的牙其 `required` 文案里含 `"；"`
    #   （锚点 2 注入）+ 生成器从字符串反解而不是读结构化 `payload["red"]`（锚点 3）
    #   ⇒ `split("；")` 切出一个**根本不是牙**的 token，污染 `red_ids` 与 `unexplained_red_teeth`
    #   ⇒ 名实审计**规则 7** 必须抓到（`pred_G42` 翻 False）。
    #   WHY 三个锚点：单改分隔符**不够** —— 每条红信息本身以 `Tid ` 开头，join 出来的 `"；"` 恰好落在
    #   token 边界上 ⇒ 反解仍得到正确 id；只有当 `"；"` 出现在**一条红信息内部**时才切出幻影。
    #   而真数据上唯一含 `"；"` 的红文案属 `Tesc`（"…不是调参项；裁定 90.6-1 明令不得放宽"），
    #   它在 formal-40 上**不红**（`headroom_consumption_max=0.7652411`）⇒ 该缺陷当时是**潜伏**的，
    #   会在裁定 90.6-2 那个 regime 首次出现窗口逃逸时正好响。
    # ⚠ 锚点 2 已随裁定 **93.1** 重指：修前选的是 `Tb`（当时主线 8/8 行确实红）；93.1 把 `Tb`
    #   转成 WARN 之后它**结构上进不了 `red`** ⇒ 注入分隔符也切不出幻影（变异体跑了却翻不动
    #   任何 check = M18 同型的"沉默失效"）。改指 `Tp5`：BC 准入必红臂 8/8 行确实红，
    #   且它的 `required` 文案是 93.1 之后主线 matrix 里**唯一**还在产红的牙 ⇒ 潜伏重新变成可测。
    #   检出方式：不是 G51（锚点文本仍唯一命中），而是"哪个变异体翻不动 check"的台账自查。
    "M33_phantom_red_tag_from_separator": [
        ("harness/norm_contract.py",
         'RED_MESSAGE_SEPARATOR = "\\n"',
         'RED_MESSAGE_SEPARATOR = "；"   # __c2_mutant__ M33-1：分隔符退回中文分号'),
        ("harness/norm_contract.py",
         '          f"stats_provenance ∈ {list(BC_ADMISSIBLE_PROVENANCES)}",',
         '          f"stats_provenance ∈ {list(BC_ADMISSIBLE_PROVENANCES)}；",   # __c2_mutant__ M33-2：在真数据上确实红的牙（Tp5）文案里注入分隔符'),
        ("scripts/c2_build_norm_stats.py",
         '        rl = pl.get("red")\n',
         '        rl = None   # __c2_mutant__ M33-3：忽略结构化 payload，退回字符串反解\n')],
    # ── 本轮新增（裁定 93.1-3 / 93.2 / 93.4）：四颗新牙各配一个"让它失声"的变异体，
    #   加一个"登记缩水"的变异体。锚点均已 `grep -Fc` 实测**恰好命中 1 次**（G51 会再拦一遍）。
    # M34：`Tz` 的判据整条抹掉 ⇒ 除零族（ACT 线 `(x-mean)/(std+1e-6)` 的形态）不再被看见。
    #   翻转面 = 进程内探针 G52（构造一维 `q99==q01` 且 `floor=0`）。
    "M34_tz_denom_zero_tolerated": [("harness/norm_contract.py",
                                    "          (not z_used_bad) and (not z_raw_bad) and (not z_floor_bad),",
                                    "          True,   # __c2_mutant__ M34：除零/非有限分母一律放过 ⇒ Tz 恒真")],
    # M35：`Tres` 的判据整条抹掉 ⇒ 逐维分辨率下限失声（93.2 补丁② 变成文案）。
    #   翻转面 = 进程内探针 G53（把某一非近常量维压到 3 个离散电平 ⇒ bins=3 < 8）。
    "M35_tres_resolution_floor_vacuous": [("harness/norm_contract.py",
                                           "          not (res_below_main or res_below_nc),",
                                           "          True,   # __c2_mutant__ M35：分辨率下限不判 ⇒ Tres 恒真")],
    # M36：`Tresw` 失声 ⇒ 近常量维 <8 的 WARN 登记消失（= 裁定 93.1-3「登记缩水」的牙级形态）。
    #   翻转面 = 进程内探针 G54（近常量维 3 个离散电平 ⇒ 本应 WARN）。
    "M36_tresw_warn_vacuous": [("harness/norm_contract.py",
                                "          not res_warn_nc,",
                                "          True,   # __c2_mutant__ M36：近常量维低分辨率不再登记 ⇒ Tresw 恒真")],
    # M37：`Tbcad` 的 AND 抹掉 ⇒ "准入只看标签、对闸 verdict 盲"（裁定 93.4 修前的形态）复活。
    #   翻转面 = 进程内探针 G55（`admissible_for_bc=true` + `gate_verdict_class1="RED"` ⇒ 本应红）。
    #   ⚠ 裁定 97.3-3 之后被抹掉的是 **class-1 判词**那一项（`gate_verdict_class1_green`）；
    #   变异体 id 不改名（它字面仍成立："闸 verdict 证据不参与准入"），改名的代价是要同步
    #   `INPROC_FLIP_PLAN` / 探针副本循环 / `MUTATIONS` / G51 锚点四处清单 —— 本轮实测到的
    #   （原句写的是 `MUTANT_SPECS`，**本文件里没有这个名字**，实物叫 `MUTATIONS`；补单四 §三-2 同批更正）
    #   失效形态恰恰是"多份清单漂移"（M6，见 97.2 红一根因），故此处**刻意只改锚点、不改 id**。
    "M37_tbcad_gate_verdict_ignored": [("harness/norm_contract.py",
                                        '          (not adm_gate["admissible_for_bc"]) or (adm_gate["gate_verdict_class1_green"] is True),',
                                        "          True,   # __c2_mutant__ M37：闸 verdict 不参与准入 ⇒ Tbcad 恒真")],
    # M39：`summarize()` 的逐维数组**截掉最后一维** ⇒ 裁定 93.1-3 的「登记不许缩水」被违反
    #   （D 给的变异体口径原文：删掉 `bins_occupied_per_dim` 任一维 ⇒ 必须红）。
    #   翻转面 = 矩阵谓词 G57（逐维数组长度 != `n_dims`）。**必须是 mainline 臂**：
    #   G57 只在主线 8 行上判（诊断档行的 `summary_all` 合法地为 None）。
    "M39_bins_per_dim_truncated": [("scripts/c2_build_norm_stats.py",
                                   '            "bins_occupied_per_dim": [int(x) for x in bins],',
                                   '            "bins_occupied_per_dim": [int(x) for x in bins][:-1],'
                                   '   # __c2_mutant__ M39：逐维登记缩水一维（裁定 93.1-3 禁止的形态）')],
}

# 裁定 **97.3-3** + 补单四 §二-E17-②③：变异体 id 是**不透明的台账键**，语义一律由本表的字段承载。
#   ⚠ 口径（D 立，对全线生效）：**任何审计器不得从变异体 id 的字符串推断语义**，一律读
#     `MUTANT_SEMANTICS[<id>]`；本表**只登记「id 字面已不足以描述现行语义」的变异体**（今天是 `M37`），
#     未登记者的语义以 `MUTATIONS` 的 (file, old, new) 三元组为准（那里就是它的实现）。
#   ⚠ **本表不接受第二份结构信息**：`flips` 派生自 `INPROC_FLIP_PLAN`，`target_file` /
#     `erased_source_line` / `mutant_replacement_line` 派生自 `MUTATIONS` —— 「两份清单漂移」正是
#     裁定 97.2 红一的根因（见 `INPROC_FLIP_PLAN` 上方那条 ⚠）。键不在两个真源里 ⇒ **拒绝开闸**（不猜、不静默）。
#   ⚠ 这是**登记字段**，不是判据：`n_checks` 不变、极性与「适用条件」字段一个字节没动（补单四 §二-E17-④）。
MUTANT_SEMANTICS: dict = {
    "M37_tbcad_gate_verdict_ignored": {
        "semantics": ("把 `Tbcad_admission_requires_green_gate` 的 ok 行**整行**换成 `True` ⇒ 准入对闸判词变盲、"
                      "该谓词恒真。被抹掉的判据里，**裁定 97.3-3 之后关键是 "
                      "`adm_gate[「gate_verdict_class1_green」] is True` 这一项**（此前只有顶层 `gate_verdict_green`）"
                      "⇒ id 字面「闸 verdict 不参与准入」**仍成立**（class-1 判词就是闸 verdict 的那一项），"
                      "但**只读 id 会漏掉「抹掉的是 class-1 那一项、不是顶层 verdict」这个事实** —— 这正是 E17 的实害。"),
        "ruling_ref": "裁定 97.3-3 + 补单四 §二-E17-②（id 保留、语义必须落**机器可读**字段）",
        "id_is_opaque_key": True,
        "id_renamed": False,
        "why_id_not_renamed": ("改名要同步四处清单（`INPROC_FLIP_PLAN` / 探针副本循环 / `MUTATIONS` / G51 锚点），"
                               "而历史台账已有此键 ⇒ 改名会造悬空引用（D 同型错误 #21 的形状）。"),
        "as_of": "2026-09-30T14:56:27+08:00",
    },
}
for _c2_mid, _c2_sem in MUTANT_SEMANTICS.items():
    if _c2_mid not in INPROC_FLIP_PLAN or _c2_mid not in MUTATIONS:
        raise SystemExit(
            f"`MUTANT_SEMANTICS` 的键 {_c2_mid} 不在 `INPROC_FLIP_PLAN`/`MUTATIONS` 里 ⇒ 登记漂移，"
            "拒绝开闸（裁定 97.2 红一同族的防线；不猜、不静默、不回落）")
    _c2_spec = MUTATIONS[_c2_mid]
    _c2_sem["flips"] = list(INPROC_FLIP_PLAN[_c2_mid])        # 单一真源，不手打
    _c2_sem["n_mutation_targets"] = len(_c2_spec)
    _c2_sem["target_file"] = _c2_spec[0][0]
    _c2_sem["erased_source_line"] = _c2_spec[0][1].strip()
    _c2_sem["mutant_replacement_line"] = _c2_spec[0][2].strip()

IDENTITY_HOOK = '''
# __c2_mutant_identity_hook__（由 c2_gate_norm_contract.py 注入；只在变异体副本里存在）
import os as _c2os, json as _c2json
_c2p = _c2os.environ.get("C2_MUTANT_IDENTITY_OUT")
if _c2p:
    with open(_c2p, "w", encoding="utf-8") as _c2f:
        _c2json.dump({"nc_file": nc.__file__,
                      "nc_mutant_id": getattr(nc, "__c2_mutant_id__", None),
                      "nc_sha256_12": __import__("hashlib").sha256(
                          open(nc.__file__, "rb").read()).hexdigest()[:12],
                      "entry_script": __file__, "pid": _c2os.getpid()}, _c2f, ensure_ascii=False)
'''


def build_mutant(run_dir: Path, mid: str) -> dict:
    """在 `run_dir/mutants/<mid>/` 构造变异体。**目录已存在 ⇒ 拒绝**（不改名、不复用）。"""
    mut = run_dir / "mutants" / mid
    if mut.exists():
        return {"ok": False, "mutant_id": mid, "dir": str(mut),
                "why": "目录已存在 ⇒ 拒绝构造（裁定 78.1 `mutant_construction_isolation`：改名复用会让"
                       "子进程 import 到未变异的旧副本 = 假绿）"}
    (mut / "scripts").mkdir(parents=True)
    for d in ("harness", "envs"):
        shutil.copytree(ROOT / d, mut / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in (BUILD, FIXPR, "scripts/c2_collect_env_states.py"):
        shutil.copy2(ROOT / f, mut / f)
    (mut / "runs").symlink_to(NORM_DIR.parent.parent, target_is_directory=True)   # → 真 runs/（只读用途）
    applied = []
    for rel, old, new in MUTATIONS[mid]:
        fp = mut / rel
        txt = fp.read_text(encoding="utf-8")
        n = txt.count(old)
        if n != 1:
            return {"ok": False, "mutant_id": mid, "dir": str(mut),
                    "why": f"锚点在 {rel} 出现 {n} 次（要求恰好 1 次）⇒ 变异体无效，拒绝当作已构造"}
        fp.write_text(txt.replace(old, new, 1), encoding="utf-8")
        applied.append({"file": rel, "sha256_12_after": sha12(fp)})
    # 变异标记（活对象属性，供子进程回读自证）
    ncp = mut / "harness/norm_contract.py"
    ncp.write_text(ncp.read_text(encoding="utf-8") + f'\n__c2_mutant_id__ = "{mid}"\n', encoding="utf-8")
    bp = mut / BUILD
    bsrc = bp.read_text(encoding="utf-8")
    anchor = "from harness import norm_contract as nc      # noqa: E402"
    if anchor not in bsrc:
        return {"ok": False, "mutant_id": mid, "dir": str(mut), "why": "identity hook 锚点缺失"}
    bp.write_text(bsrc.replace(anchor, anchor + IDENTITY_HOOK, 1), encoding="utf-8")
    return {"ok": True, "mutant_id": mid, "dir": str(mut), "applied": applied,
            "harness_norm_contract_sha256_12": sha12(ncp),
            "collector_sha256_12": (sha12(mut / "scripts/c2_collect_env_states.py")
                                    if mid.startswith("M4") else None)}


def read_identity(mut: Path) -> dict:
    ip = mut / "identity.json"
    if not ip.exists():
        return {"present": False, "why": "子进程没写 identity.json（hook 未执行？）"}
    d = json.loads(ip.read_text(encoding="utf-8"))
    d["present"] = True
    d["nc_file_inside_mutant_dir"] = str(Path(d["nc_file"]).resolve()).startswith(str(mut.resolve()))
    return d


# --------- 裁定 90.4-1 的**极性构造**（进程内；只调契约层，不读任何数据集） ---------
# WHY 放进闸里、而不是只留 `runs/.../probe_ruling90_4_polarity/probe.py`：那份探针是**一次性**只读
# 产物，跑完就与契约层脱钩（它记录的 contract sha 本轮已经过期过一次）。红线
# `tooth_must_be_mutant_proven` 要求"哪条 check 会被哪个变异体搞红"是**实测**的 ⇒ 极性判据必须能在
# **变异体副本里用同一份代码重跑**（`--probe-inprocess`），一次性探针在结构上做不到这件事。
# 构造与 `probe_ruling90_4_polarity/probe.py` 的 `mk()`/`EXPECT` **同源**（同一组 kind、同一个 rng 种子、
# 同一个声明区间），只是搬进了闸 ⇒ 两边读数可以互核，而闸这一份是**活的**（跟着变异体跑）。
POLARITY_ND = 4
POLARITY_SEED = 20260930
POLARITY_IV = ((-1.0, -2.0, 0.0, -0.5), (1.0, 2.0, 0.1, 0.5))   # dim2 = 近常量维（跨度 0.1）
POLARITY_PHYSICAL_RANGE = (2.0, 4.0, 0.1, 1.0)
TIV = "Tiv_out_of_declared_interval_is_measured"
TESC = "Tesc_no_covered_window_escape"
TLO = "Tlo_no_downside_coverage_deficit"
TOVR = "Tovr_out_of_interval_overflow_is_warned"
POLARITY_TEETH = (TIV, TESC, TLO, TOVR)
# 期望表 = 裁定 90.4-1 的四条极性的**逐构造**展开。每一行都必须能在产物里找到对应实测
# （`runs/vla/c2_norm_contract_20260929/probe_ruling90_4_polarity/verdict.json` 的 `rows[].expected`）。
POLARITY_EXPECT = {
    # 数据全在声明区间内 ⇒ 四把牙全绿（`Tovr` 无越界可登记 ⇒ PASS 而不是 WARN）
    "inside":         {TIV: "PASS", TESC: "PASS", TLO: "PASS", TOVR: "PASS"},
    # 上侧小幅越界（< 1 bin 头寸）⇒ 只 warning，**永不**因越界本身出红（90.4-1 第一条）
    "upside_small":   {TIV: "PASS", TESC: "PASS", TLO: "PASS", TOVR: "WARN"},
    # 下侧小幅越界但被头寸吸收 ⇒ 同样只 warning（下侧"越界"≠下侧"覆盖不足"）
    "downside_small": {TIV: "PASS", TESC: "PASS", TLO: "PASS", TOVR: "WARN"},
    # 下侧越出远超头寸 ⇒ 覆盖不足 = 正确性缺陷 = 硬红；`Tesc` 也红（它不分侧）
    "downside_escape": {TIV: "PASS", TESC: "RED", TLO: "RED", TOVR: "WARN"},
    # 上侧越出远超头寸 ⇒ 窗口逃逸红，但**下侧覆盖不足必须绿**（90.4-1 的分侧不对称）
    "escape":         {TIV: "PASS", TESC: "RED", TLO: "PASS", TOVR: "WARN"},
    # 评估帧里有 NaN ⇒ 越界**测量不完整** ⇒ `*_is_measured` 必须红（牙名承诺的就是"已测"）。
    # 这颗构造是 90.4-1 牙③（把 `Tiv` 改成恒真的变异体必须被元闸抓到）的**唯一**可测入口：
    # 真数据上测量是完整的，恒真变异体在真数据上与正确实现**读数相同** ⇒ 抓不到。
    "nan_in_eval":    {TIV: "RED", TESC: "PASS", TLO: "PASS", TOVR: "PASS"},
    # 不给声明区间 ⇒ 四把牙全 N_A（三态：没测 ≠ 测到没有；红线 88.3-1）
    "no_interval":    {TIV: "N_A", TESC: "N_A", TLO: "N_A", TOVR: "N_A"},
    # **held-out 帧**下侧越出声明区间 0.005（< 该维 1 bin 头寸 0.015625），而 build 帧全在区间内。
    # 这颗构造是裁定 90.4-1 **牙②**／90.4-2（"① 的正确性收益是实测的"）的**可测入口**：
    #   ① 档（覆盖声明区间 + 头寸）吸收它 ⇒ `Te2` 绿；
    #   `build_only` 档（覆盖集 = 起态 + build 帧）吸收不了 ⇒ held-out 帧归一化 < -1 ⇒
    #   `processor_pi05.py:77` 的 digitize 给出 **bin -1** ⇒ `Te2_no_illegal_bin_heldout` 必须红。
    # WHY 需要它（本轮实测）：在 **formal-40 真数据**上把覆盖目标退回 build_only（变异体 M21），
    #   咬到的是 `Tcov_declared_interval_covered`（主线 8/8 行），`Te2` **没有**红 ——
    #   因为 formal-40 的 held-out 帧（每方向最后一整集）恰好都落在 build 帧的范围内。
    #   ⇒ 牙② 在真数据上由 `Tcov` 承担、在"held-out 帧越过声明下界"这个**它真正要防的形态**上
    #   由本构造承担。两者都已实测（见 G48 的台账与 G50）。
    "heldout_below_lo": {TIV: "PASS", TESC: "PASS", TLO: "PASS", TOVR: "WARN"},
}
POLARITY_KINDS = tuple(POLARITY_EXPECT)


def polarity_frames(kind: str) -> tuple[np.ndarray, np.ndarray | None]:
    """返回 `(build_frames, eval_frames)`。构造是**确定的**（固定种子），不读盘、不依赖数据集。"""
    rng = np.random.default_rng(POLARITY_SEED)
    n = POLARITY_ND
    fr = np.zeros((400, n))
    fr[:, 0] = np.linspace(-0.9, 0.9, 400)
    fr[:, 1] = np.linspace(-1.9, 1.9, 400)
    fr[:, 2] = 0.05 + 1e-4 * rng.standard_normal(400)      # 近常量维（跨度 0.1 的声明区间里几乎不动）
    fr[:, 3] = np.linspace(-0.4, 0.4, 400)
    if kind == "upside_small":            # 上侧越出 1e-4（远小于 1 bin 头寸）
        fr[:, 0] = np.linspace(-0.9, 1.0 + 1e-4, 400)
    if kind == "downside_small":          # 下侧越出 1e-3（被头寸吸收）
        fr[:, 1] = np.linspace(-2.0 - 1e-3, 1.9, 400)
    if kind == "downside_escape":         # 下侧越出 0.5（= 头寸的数十倍）
        fr[:, 1] = np.linspace(-2.0 - 0.5, 1.9, 400)
    if kind == "escape":                  # 上侧越出 0.5
        fr[:, 0] = np.linspace(-0.9, 1.0 + 0.5, 400)
    build, ev = fr[:300], fr[300:].copy()
    if kind == "heldout_below_lo":
        # build 帧保持全在声明区间内；**只让 held-out 帧**下侧越出 0.005（< 1 bin 头寸 0.015625）
        ev[:, 1] = np.linspace(-2.005, 1.9, ev.shape[0])
    return build, ev


def red_tags_of(payload: dict | None, exc: BaseException) -> list[str]:
    """红标签的**权威**口径 = 结构化的 `payload["red"]`；缺则回落到分隔符切分。

    与生成器侧 `scripts/c2_build_norm_stats.py:eval_verdict` **同一条口径**（那边是 5 元组、这边只要标签）：
    两处都必须走 `payload["red"]`，因为牙的 `required`/`observed` 文案里合法地含中文分号
    （`Tesc` 的 required 写了"…不是调参项；裁定 90.6-1 明令不得放宽"）⇒ 用 `"；"` 拼串再
    `split("；")` 会切出**幻影红标签**。分隔符本身已由 `nc.RED_MESSAGE_SEPARATOR` 从 `"；"` 改成
    `"\n"`，回落分支只在"提前抛的卫语句没给结构化 payload"时才会走到（三态：不假装没红）。
    """
    pl = payload or getattr(exc, "payload", None) or {}
    rl = pl.get("red")
    if rl is None:
        rl = str(exc).split(nc.RED_MESSAGE_SEPARATOR)
    return [str(x) for x in rl]


def polarity_run(kind: str, coverage_target: str | None = None) -> dict:
    """跑一个构造，返回四把牙的状态 + 越界测量块 + payload（供 `name_semantics_audit` 复用）。

    数据流**与生成器同形**（本轮实测校正过）：stats 与覆盖集都只吃 **build** 帧，held-out 帧只用于
    评估（生成器 `run_source()` → `build_case()` 就是这么调 `coverage_must_cover(frames=frames)` 的）。
    修前本函数把 build ∪ eval 全喂给 stats/覆盖集 ⇒ held-out 帧的越界被自己的覆盖集吸收，
    "held-out 帧不受保护"这个形态在构造里**做不出来**（= 牙② 无从验证）。
    `coverage_target=None` ⇒ 用 ①（`declared_interval`）；显式给 `build_only` ⇒ 对照臂。
    """
    target = coverage_target or nc.COVERAGE_TARGET_DECLARED_INTERVAL
    iv = ([np.asarray(POLARITY_IV[0], dtype=np.float64),
           np.asarray(POLARITY_IV[1], dtype=np.float64)] if kind != "no_interval" else None)
    build, ev = polarity_frames(kind)
    if kind == "nan_in_eval":
        # 只污染**评估帧**，stats 仍由干净帧建。这是实测出来的必要顺序（不是设计偏好）：
        # 把 NaN 注入 build 帧 ⇒ `nc.build_stats` 产出非有限 q01/q99 ⇒
        # `Ts_stats_arrays_present` 的**提前抛**先响，payload 里根本没有四把 IV 牙
        # （首跑实测：statuses 全 `ABSENT`）⇒ 牙③ 的构造失去判别力。
        ev = ev.copy()
        ev[7, 1] = np.nan
    try:
        st = nc.build_stats(build)
        cov = (nc.coverage_must_cover(target=target, frames=build,
                                      start_pose=build[0], physical_interval=iv)
               if iv is not None else None)
        if cov is not None:
            w = nc.widen_to_cover(st, cov["must_cover"], cover_cap=cov["cover_cap"])
            st = {**st, "q01": w["q01"], "q99": w["q99"]}
        res = nc.evaluate_contract(
            case=nc.CASE_QUANTILES_FLOOR, stats=st, frames=build, start_pose=build[0],
            source=nc.SOURCE_S1_DEMO, features={"observation.state": {"shape": (POLARITY_ND,)}},
            physical_range=np.asarray(POLARITY_PHYSICAL_RANGE, dtype=np.float64), mainline=True,
            eval_frames=ev, physical_interval=iv,
            stats_provenance=nc.STATS_PROVENANCE_FORMAL40_BC, consumer=nc.CONSUMER_PATH_CHECK,
            coverage_target=target)
        raised = None
    except nc.NormContractViolation as exc:
        res = getattr(exc, "payload", None) or {}
        raised = [x.split(" ")[0] for x in red_tags_of(res, exc)]
    except Exception as exc:      # 变异体副本里可能崩（例：M21 让覆盖集构造改形）
        return {"kind": kind, "coverage_target": target,
                "crash": f"{type(exc).__name__}: {exc}"[:300], "teeth": {}, "all_statuses": {},
                "statuses": {t: "CRASH" for t in POLARITY_TEETH}, "match": False, "payload": None}
    teeth = {t["id"]: t for t in (res.get("teeth") or [])}
    statuses = {t: (teeth[t]["status"] if t in teeth else "ABSENT") for t in POLARITY_TEETH}
    exp = POLARITY_EXPECT[kind]
    return {"kind": kind, "coverage_target": target, "crash": None, "raised": raised,
            "all_statuses": {i: t["status"] for i, t in teeth.items()},
            "verdict": res.get("verdict"),
            "teeth": {t: {"status": statuses[t],
                          "ok": (teeth[t].get("ok") if t in teeth else None),
                          "blocking": (teeth[t].get("blocking") if t in teeth else None)}
                      for t in POLARITY_TEETH},
            "statuses": statuses, "expected": exp, "match": bool(statuses == exp),
            "conformance": {k: (res.get("declared_interval_conformance") or {}).get(k) for k in
                            ("measurement_status", "measurement_complete",
                             "measurement_nonfinite_fields", "dims_out", "window_escape",
                             "headroom_consumption_max", "dims_window_escape",
                             "dims_downside_deficit", "upside_overflow", "downside_deficit")},
            "payload": res}


def polarity_table() -> dict:
    return {k: polarity_run(k) for k in POLARITY_KINDS}


def polarity_rows_as_matrix(table: dict) -> dict:
    """把构造的 payload 拼成 `name_semantics_audit` 能吃的**同形**结构。

    WHY：牙③（裁定 90.4-1）要求"把 `Tiv` 改成恒真的变异体必须被元闸
    `gate_name_must_match_gate_semantics` 抓到"。那颗元闸的实现只有一份
    （`name_semantics_audit`），它在真产物上抓不到恒真变异体 —— 真数据的测量是**完整**的，
    恒真与正确实现读数相同。所以把**构造**也喂给同一份审计（含 `nan_in_eval` 这个测量不完整的
    构造）⇒ 元闸就在它有判别力的输入上跑，而且审计代码没有第二份（不会漂移）。
    """
    rows = []
    for kind in POLARITY_KINDS:
        ent = table.get(kind) or {}
        pl = ent.get("payload")
        # `raised` = `polarity_run` 已经按 `.split(" ")[0]` 取过 token 的红标签列表（与生成器
        # `red_ids` 同一口径）⇒ 审计规则 7 在构造矩阵上同样生效（幻影标签的原始检出面就是这里）。
        rid = ent.get("raised")
        if not pl:
            rows.append({"arm": f"polarity_construct_{kind}", "mainline": True,
                         "eval_frames_are_held_out": None, "eval_scope": None, "teeth": [],
                         "declared_interval_conformance": None, "red_ids": rid,
                         "construct_crashed": ent.get("crash")})
            continue
        rows.append({"arm": f"polarity_construct_{kind}", "mainline": bool(pl.get("mainline")),
                     "eval_frames_are_held_out": pl.get("eval_frames_are_held_out"),
                     "eval_scope": pl.get("eval_scope"),
                     "n_eval_frames": pl.get("n_eval_frames"),
                     "n_build_frames": pl.get("n_build_frames"),
                     "red_ids": rid,
                     "teeth": pl.get("teeth") or [],
                     "declared_interval_conformance": pl.get("declared_interval_conformance")})
    return {"rows": rows, "artifact": "polarity_constructs_as_matrix_rows"}


def inprocess_probes(base_dir: Path) -> dict:
    """进程内输入级变异体（直接调 `harness.norm_contract.evaluate_contract`）。

    抽成函数的理由（裁定 83.2 `tooth_must_be_mutant_proven`）：**同一份谓词代码**既用于真仓基线，
    也用于在变异体副本里重跑（`--probe-inprocess`）⇒ "哪条 check 会被哪个变异体搞红"是**实测**的，
    不是文书里写死的；谓词只有一份，不会漂移。
    """
    g = Gate()
    # ⚠ 本轮修的**标注缺陷**（不是新需求）：三个 env 臂过去共用同一文件名 ⇒ 互相覆写，
    # 磁盘上留的是 hold 相那份，而这里按无后缀名取档 ⇒ 变量名叫 st_file、内容其实是 hold 相
    # （结论侥幸自洽，因为 `call()` 默认也用 hold 帧；但**标注是错的**，且 matrix 里 16 行的
    # `roundtrip.sha256_12` 指向已被覆写的文件状态 = 缺陷类 ⑨ 引用过期）。
    # 生成器侧已根治（每臂独立文件名 + 每行落 `stats_file_sha256_12`）；这里显式点名 hold 相档，
    # 并**断言文件内容的 representation_version 就是本探针以为的那一臂**（防同类错标再次静默发生）。
    st_file = (base_dir / "stats/env_derived_diagnostic__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__holdphase.json")
    id_file = (base_dir / "stats/env_derived_diagnostic__identity_with_explicit_scale__F1_physical_range_fraction_0.05__holdphase.json")
    hold_file = st_file
    EXPECT_ARM_PREFIX = "env-derived-holdphase"
    prj = json.loads((NORM_DIR / PR_JSON).read_text(encoding="utf-8"))
    prange = np.asarray(prj["physical_range_effective"], dtype=np.float64)
    interval = [np.asarray(prj["physical_interval"]["lo"], dtype=np.float64),
                np.asarray(prj["physical_interval"]["hi"], dtype=np.float64)]
    z = np.load(NORM_DIR / "env_states_hold/env_states.npz")
    hold_frames = np.asarray(z["frames"], dtype=np.float64)
    a2 = json.loads((ROOT / A2_START).read_text(encoding="utf-8"))
    start_pose = np.asarray(a2["hold_action_14d"], dtype=np.float64)
    features = {"observation.state": {"type": "state", "shape": (14,)}}

    def call(stats, *, case=nc.CASE_QUANTILES_FLOOR, source=nc.SOURCE_ENV_DERIVED, mainline=False,
             frames=hold_frames, feat=None, force_blocking=False, prov="__auto__", consumer=None,
             # 裁定 93.2/93.4 的四个新入参（G52–G55 要用）：分辨率口径与 BC 准入的闸证据
             all_frames=None, gate_verdict=None, gate_run_dir=None, gate_verdict_sha256_12=None,
             # 裁定 97.3-3：BC 准入 AND 的是 `verdict_class1` ⇒ 构造必须能分别喂两个判词
             gate_verdict_class1=None):
        # `prov="__auto__"` = 按 source 自动填一个**合法**标签：探针要验的是 Ta/Td/Tr3，
        # 不是 Tp4；若不填，Tp4 的提前抛会让 red 集合里只剩 Tp4（首轮冒烟实测到过），
        # 那几条探针就全部假红。要验"缺标签必须红"的是 G37，它显式传 `prov=None`。
        _prov = prov
        if _prov == "__auto__":
            _prov = (PILOT10_LABEL if source == nc.SOURCE_S1_DEMO
                     else nc.STATS_PROVENANCE_ENV_DIAGNOSTIC)
        try:
            res = nc.evaluate_contract(case=case, stats=stats, frames=frames, start_pose=start_pose,
                                       source=source, features=(features if feat is None else feat),
                                       physical_range=prange, mainline=mainline,
                                       force_blocking=force_blocking, physical_interval=interval,
                                       stats_provenance=_prov, consumer=consumer,
                                       all_frames=all_frames, gate_verdict=gate_verdict,
                                       gate_run_dir=gate_run_dir,
                                       gate_verdict_sha256_12=gate_verdict_sha256_12,
                                       gate_verdict_class1=gate_verdict_class1)
            return "PASS", set(), res
        except nc.NormContractViolation as exc:
            pl = getattr(exc, "payload", None) or {}
            return "RED", {x.split(" ")[0] for x in str(exc).split("；")}, pl
        except Exception as exc:      # 变异体副本里会出现（例：M9 让缺键检测失效 ⇒ KeyError / numpy 广播错）
            # 记成 "CRASH" 而**不是** PASS/RED：G10/G11 要求的是"点名到 Ts 的 RED"，崩溃不满足 ⇒ 谓词为 False。
            # 这正是 `Ts` 提前抛（harness/norm_contract.py:424-430）要防的形态：红的理由变成 traceback。
            return "CRASH", set(), {"crash": f"{type(exc).__name__}: {exc}"[:400]}

    st_payload = json.loads(st_file.read_text(encoding="utf-8"))
    base_stats = nc.roundtrip_from_payload(st_payload)
    # 臂身份自证：文件**内容**里的 representation_version 前缀 == 本探针以为的那一臂
    arm_prefix_ok = str(st_payload.get("representation_version", "")).startswith(EXPECT_ARM_PREFIX)
    g.add("G36_stats_file_arm_identity",
          f"进程内探针吃的 stats 文件确实是它以为的那一臂（`{EXPECT_ARM_PREFIX}`）",
          arm_prefix_ok and st_payload.get("stats_provenance") in nc.KNOWN_STATS_PROVENANCES,
          f"representation_version 以 {EXPECT_ARM_PREFIX} 开头，且 stats_provenance ∈ 已知集合",
          (f"representation_version={st_payload.get('representation_version')} "
           f"stats_provenance={st_payload.get('stats_provenance')} file={st_file.name}"),
          ("文件名与内容口径不符 ⇒ 探针判的是别的臂（本轮实测到过的缺陷：三臂共用文件名互相覆写，"
           "磁盘上留 hold 相、名字看不出来）"),
          kind="measured",
          mutant_that_proves_it=("读的是**文件内容**而非文件名 ⇒ 错标即红；本轮已用真缺陷实测过一次"
                                 "（修前该文件内容是 hold 相、名字无臂标识）"),
          ruling_ref="裁定 85.4-2（口径必须显式）/ 缺陷类 ⑨")

    # 4a 清空 stats（两种形态：数组置空 / 键删掉）
    empty_stats = {**base_stats, "q01": np.zeros(0), "q99": np.zeros(0)}
    v, ids, _pl = call(empty_stats)
    g.add("G10_clear_stats_bites_Ts", "清空 stats（数组长度 0）⇒ **Ts** 必须红，且提前抛（不崩在 numpy 广播上）",
             v == "RED" and "Ts_stats_arrays_present" in ids,
             "verdict=RED 且 Ts ∈ red", f"verdict={v} red={sorted(ids)}",
             "清空 stats 不红 ⇒ 会静默走 `normalize_processor.py:305-307` 的 IDENTITY 默认（A2 实测该状态存在）",
             mutant_that_proves_it="M1_non_raising（在 M1 副本内用**同一份谓词**重跑 ⇒ 翻 False；见 G25）")
    nokey = {k: v2 for k, v2 in base_stats.items() if k not in ("q01", "q99")}
    v2, ids2, _ = call(nokey)
    g.add("G11_missing_keys_bites_Ts", "删掉 q01/q99 两个键 ⇒ Ts 必须红（缺键也要点名）",
             v2 == "RED" and "Ts_stats_arrays_present" in ids2,
             "verdict=RED 且 Ts ∈ red", f"verdict={v2} red={sorted(ids2)}",
             "缺键不红 ⇒ `modeling_pi05.py:995-998` 那类「缺键静默返回随机权重」的同族风险没人守",
             mutant_that_proves_it="M1_non_raising（在 M1 副本内用**同一份谓词**重跑 ⇒ 翻 False；见 G25）")

    # 4b features 清空（A2 实测的现场状态）
    v3, ids3, _ = call(base_stats, feat={})
    g.add("G12_empty_features_bites_Ta", "`features={}` ⇒ **Ta** 必须红（A2 实测 `config.features={}`）",
             v3 == "RED" and "Ta_features_non_empty" in ids3,
             "verdict=RED 且 Ta ∈ red", f"verdict={v3} red={sorted(ids3)}",
             "features 空而不红 ⇒ 处理器静默 IDENTITY，整条归一化等于没做",
             mutant_that_proves_it="M1_non_raising（在 M1 副本内用**同一份谓词**重跑 ⇒ 翻 False；见 G25）")

    # 4c 单维缩放错（把 dim5 的窗口压到 1/5）⇒ 必须红且**点名到 dim 5**
    one = {k: (np.array(v4, dtype=np.float64).copy() if isinstance(v4, np.ndarray) else v4)
           for k, v4 in base_stats.items()}
    q01, q99 = one["q01"], one["q99"]
    mid5 = (q01[5] + q99[5]) / 2.0
    q99[5] = mid5 + (q99[5] - mid5) * 0.2
    q01[5] = mid5 - (mid5 - q01[5]) * 0.2
    one["q01"], one["q99"] = q01, q99
    one["span_q99_q01"] = q99 - q01
    one["denom_raw"] = q99 - q01
    one["denom_effective"] = q99 - q01
    v4, ids4, pl4 = call(one, frames=np.asarray(np.load(NORM_DIR / "env_states_random/env_states.npz")["frames"], dtype=np.float64))
    named5 = any("5" in (t.get("observed") or "") for t in (pl4.get("teeth") or []) if t["id"] in ids4)
    g.add("G13_single_dim_scale_error_named", "单维（dim5）缩放错 ⇒ 必须红，且**在 observed 里点名到该维**",
             v4 == "RED" and bool(ids4 & {"Td1_clip_build_frames", "Tsat_saturation_dims_zero",
                                           "Tc_start_pose_coverage", "Te1_no_illegal_bin_build"}) and named5,
             "verdict=RED 且至少一把尺度类牙红，且 observed 含 dim 5",
             f"verdict={v4} red={sorted(ids4)} named_dim5={named5}",
             "红但不点名 ⇒ 现场无法定位是哪一维（裁定 51① 要求点名到维）",
             mutant_that_proves_it="M1_non_raising（在 M1 副本内用**同一份谓词**重跑 ⇒ 翻 False；见 G25）")

    # 4d Tr3：主线臂 + F2 下限（近常量维下限实质无效）⇒ 必须红；诊断臂 ⇒ 必须 N_A
    fam2 = nc.floor_family("F2_noise_scale_multiple", 2.0)
    mad = np.asarray(base_stats.get("noise_mad_step", np.full(14, np.nan)), dtype=np.float64)
    if not np.all(np.isfinite(mad)):
        zh = nc.build_stats(hold_frames)
        mad = np.asarray(zh["noise_mad_step"], dtype=np.float64)
    f2_floors = fam2.floors(physical_range=prange, noise=mad)
    f2_stats = {**base_stats, "floor": f2_floors,
                "denom_effective": np.maximum(np.asarray(base_stats["denom_raw"], dtype=np.float64), f2_floors)}
    v5, ids5, pl5 = call(f2_stats, source=nc.SOURCE_S1_DEMO, mainline=True)
    tr3_status_main = next((t["status"] for t in (pl5.get("teeth") or [])
                            if t["id"] == "Tr3_near_constant_floor_material"), None)
    v6, ids6, pl6 = call(f2_stats, source=nc.SOURCE_ENV_DERIVED, mainline=False)
    tr3_status_diag = next((t["status"] for t in (pl6.get("teeth") or [])
                            if t["id"] == "Tr3_near_constant_floor_material"), None)
    # ⚠ 本 check **改名 + 改判据**（裁定 93.1-1）。旧 id = `G14_Tr3_bites_on_mainline_only`、
    #   旧判据 = `v5 == "RED" and Tr3 ∈ ids5 and 诊断臂 N_A`。93.1-1 把 Tr3 的 `blocking` 改成
    #   `False` 之后，"主线臂上 Tr3 红"这个期望**由 D 的裁定作废** ⇒ 继续按旧判据判就会把
    #   "正确落地了 93.1" 判成失败（假红）。新判据守的是**同一件事的现行极性**：
    #   主线臂上 Tr3 必须**登记为 WARN 且不进 red**、诊断臂必须 N_A。
    #   "近常量维的下限必须实质有效"这件事并没有失去守卫：`Tr1`（blocking=True，裁定 93.2 明令
    #   不降级）+ `Tz`（近常量维 `floor_d > 0`，绝对硬红）两颗牙仍在，见 G52/G58。
    tr3_blocking_main = next((t.get("blocking") for t in (pl5.get("teeth") or [])
                              if t["id"] == "Tr3_near_constant_floor_material"), None)
    g.add("G14_Tr3_registers_warn_on_mainline_only",
             ("主线臂 + F2 下限 ⇒ **Tr3 = WARN、blocking=False、且不进 red**（裁定 93.1-1）；"
              "同一份 stats 在诊断臂 ⇒ **Tr3 = N_A**（裁定 72-2）"),
             (tr3_status_main == "WARN" and tr3_blocking_main is False
              and "Tr3_near_constant_floor_material" not in ids5
              and tr3_status_diag == "N_A"),
             "主线：Tr3 status == WARN 且 blocking == false 且 Tr3 ∉ red；诊断：Tr3 status == N_A",
             # ⚠ 标签里的 `Tr3_blocking=` 修前被引用审计（G46）当成**牙 id 引用**判为 dangling
             #   （`TOOTH_ID_RE = \bT[a-z]{1,4}[0-9]?_[A-Za-z0-9_]+` 正是牙 id 的形态）⇒ 用中文
             #   「的」断开，语义不变。**不改审计器**（放宽审计器 = 缺陷类 ⑲ 的形态）。
             (f"主线 verdict={v5} Tr3={tr3_status_main} Tr3 的 blocking={tr3_blocking_main} "
              f"red={sorted(ids5)}；诊断 Tr3={tr3_status_diag}"),
             ("主线仍出 RED ⇒ 裁定 93.1-1 没落地（未经定标的下限还在阻塞主线，E4 的实质缺陷仍在）；"
              "主线连 WARN 都不出 ⇒ 登记被悄悄删了（违反裁定 93.1-3「登记不许缩水」）；"
              "诊断臂出红/出 WARN ⇒ 假红（裁定 72-2 审点①③）"),
             mutant_that_proves_it=("M6_tr3_always_blocking（把 `blocking=False, "
                                    "applies_when=bool(mainline)` 装回 `blocking=True, "
                                    "applies_when=True` ⇒ 在本副本内用**同一份谓词**重跑，"
                                    "主线由 WARN 变 RED、诊断由 N_A 变 RED ⇒ 翻 False；见 G25）"),
             ruling_ref="裁定 93.1-1 / 49.1 / 72-2")

    # 4e IDENTITY 档：落盘的 center/gain 必须真能覆盖起态（直接拿文件里的数复算）
    idp = json.loads(id_file.read_text(encoding="utf-8")) if id_file.exists() else {}
    if idp:
        arrs = idp["arrays"]
        ctr = np.asarray(arrs["center"], dtype=np.float64)
        gan = np.asarray(arrs["gain"], dtype=np.float64)
        sn = (start_pose - ctr) * gan
        oob = [int(i) for i in np.nonzero((sn >= 1.0) | (sn < -1.0))[0]]
        g.add("G15_identity_payload_covers_start_pose",
                 "**从 IDENTITY 档落盘文件**取 center/gain 复算，起态越界维数 = 0",
                 len(oob) == 0, "越界维=[]",
                 f"越界维={oob} abs_max={float(np.abs(sn).max()):.6f}（起态 max|state|={float(np.abs(start_pose).max()):.4f}）",
                 "文件里的 center/gain 覆盖不住起态 ⇒ 交付物与判定不一致（M3 变异体的目标形态）",
                 mutant_that_proves_it=("M3_payload_recompute_identity（在 M3 副本内用**同一份谓词**"
                                        "重跑 ⇒ 翻 False；见 G26）"))
    else:
        g.add("G15_identity_payload_covers_start_pose", "从 IDENTITY 档落盘文件复算起态覆盖",
                 False, "identity stats 文件存在", f"缺文件：{id_file.name}", "缺交付物 ⇒ 无法判定", applies_when=False)
    # 4f 溯源标签缺失 ⇒ **Tp4 必须红且提前抛**（不许崩在下游算术上）
    v7, ids7, pl7 = call(base_stats, prov=None)           # 显式不传 ⇒ 验 Tp4
    g.add("G37_missing_provenance_bites_Tp4",
          "不传 `stats_provenance` ⇒ **Tp4** 必须红，且红的形式是点名（不是 traceback）",
          v7 == "RED" and TP4 in ids7 and (pl7 or {}).get("early_raise") == TP4,
          f"verdict=RED 且 {TP4} ∈ red 且 early_raise == {TP4}",
          f"verdict={v7} red={sorted(ids7)} early_raise={(pl7 or {}).get('early_raise')} "
          f"crash={(pl7 or {}).get('crash')}",
          ("缺标签不红 ⇒ 下游可以拿一份**身份不明**的 stats 去配 BC（裁定 85.4-3 的同源硬闸就少了入口检查）；"
           "崩在 numpy 上 ⇒ 红的理由变成 traceback，现场无法定位"),
          mutant_that_proves_it="M11_provenance_label_vacuous（在本变异体副本内用**同一份谓词**重跑 ⇒ 翻 False）",
          ruling_ref="裁定 85.4-2/85.4-3")

    # 4g BC 准入极性（三向：必红 / 绿证人 / 不适用）—— 裁定 85.4-3 点名要的那条牙
    v8, ids8, pl8 = call(base_stats, prov=PILOT10_LABEL, consumer=nc.CONSUMER_BC)
    t5_bc = next((t["status"] for t in (pl8.get("teeth") or []) if t["id"] == TP5), None)
    v9, ids9, pl9 = call(base_stats, prov=FORMAL40_LABEL, consumer=nc.CONSUMER_BC)
    t5_ok = next((t["status"] for t in (pl9.get("teeth") or []) if t["id"] == TP5), None)
    v10, ids10, pl10 = call(base_stats, prov=PILOT10_LABEL, consumer=nc.CONSUMER_PATH_CHECK)
    t5_na = next((t["status"] for t in (pl10.get("teeth") or []) if t["id"] == TP5), None)
    g.add("G38_bc_admission_tooth_polarity",
          "BC 准入牙 **Tp5** 的三向极性：pilot10+bc ⇒ RED；formal40+bc ⇒ PASS；pilot10+path_check ⇒ N_A",
          (TP5 in ids8 and t5_bc == "RED") and (TP5 not in ids9 and t5_ok == "PASS") and (t5_na == "N_A"),
          f"pilot10+bc：{TP5}=RED；formal40+bc：{TP5}=PASS（绿证人）；pilot10+path_check：{TP5}=N_A",
          f"pilot10+bc ⇒ Tp5={t5_bc} red={sorted(ids8)}；formal40+bc ⇒ Tp5={t5_ok}；"
          f"pilot10+path_check ⇒ Tp5={t5_na}",
          ("pilot10 喂 BC 不红 ⇒ 裁定 85.4-3 的同源硬闸恒真（= 没有闸）；formal40 也红 ⇒ 恒红"
           "（合法输入被挡，下游只能绕闸）；path_check 出红 ⇒ 极性错（裁定 72-2 审点①③）"),
          mutant_that_proves_it="M10_bc_admission_gate_vacuous（在本变异体副本内用**同一份谓词**重跑 ⇒ 翻 False）",
          ruling_ref="裁定 85.4-3")

    # 4h) 裁定 90.4-1 的**极性**（构造级）—— 与变异体副本里跑的是同一份代码（`--probe-inprocess`）
    # 4g-2) 裁定 93.2 / 93.4 四颗新牙的**双向构造**（G52–G55）
    # WHY 必须走构造、不能只判真数据：这四颗牙在 formal-40 **真实数据上全绿**（本轮实测
    #   `arm_mainline` 49/49 行 `Tz`=PASS、`Tres`=PASS）⇒ 在真数据上"恒绿"与"根本没判"读数相同
    #   （裁定 27.1）。牙的证据因此是三件：① 真数据绿（矩阵谓词 G27/G57）② 构造红（本节）
    #   ③ **同一份谓词**在 M34–M37 副本内由 True 翻 False（G25 的实测台账）。
    # 设计依据（先跑设计探针、再写进闸；不拿 ~2 min 的整轮闸跑当调试器）：
    #   `runs/vla/c2_norm_contract_20260929/probe_design_ruling94_95/design_probe.json`
    #   实测结论：`Tz` 两向 RED/PASS；`Tres` 在 **7 个 bin ⇒ RED、8 个 bin ⇒ PASS**（阈值边界
    #   本身被夹住，不是"压得够狠才红"）；`Tresw` 3 电平 ⇒ WARN 而 `Tres` PASS、1 电平 ⇒ `Tres` RED
    #   （两颗牙的分工可分辨）；`Tbcad` PASS/RED/not_measured⇒RED/path_check⇒N_A 四向齐。
    ncd_probe = nc.near_constant_dims(base_stats)
    d_probe = next(int(x) for x in range(len(prange)) if int(x) not in set(int(y) for y in ncd_probe))
    q01_d, q99_d = float(base_stats["q01"][d_probe]), float(base_stats["q99"][d_probe])

    def squeezed(n_levels: int, *, stats=None) -> np.ndarray:
        """把 `d_probe` 那一维压成 `n_levels` 个离散电平（都在 [q01, q99] 内），其余维保持真帧。

        WHY 电平都落在 [q01,q99] 内：要造的是"**分辨率**不足"，不是"越界"。若电平跑到分位距外，
        红的可能变成 clip 家族（Td1/Td2）⇒ 归因就不干净了（对照实验只许一个变量）。
        """
        f = hold_frames.copy()
        if n_levels <= 1:
            f[:, d_probe] = (q01_d + q99_d) / 2.0
        else:
            lev = np.linspace(q01_d, q99_d, n_levels)
            f[:, d_probe] = lev[np.arange(f.shape[0]) % n_levels]
        return f

    def zero_denom_dim(stats: dict, d: int) -> dict:
        """D 在裁定 93.2 给的字面构造：一维 `q99 == q01` 且 `floor = 0`（除零族的形态）。"""
        z = {k: (np.array(v, dtype=np.float64).copy() if isinstance(v, np.ndarray) else v)
             for k, v in stats.items()}
        z["q99"][d] = z["q01"][d]
        for key in ("span_q99_q01", "denom_raw", "denom_effective", "floor"):
            if key in z:
                z[key][d] = 0.0
        return z

    # ---- G52：`Tz_denom_strictly_positive`（裁定 93.2 补丁①，绝对硬红、无定标空间）----
    vz_m, _idsz_m, plz_m = call(zero_denom_dim(base_stats, d_probe))
    vz_b, _idsz_b, plz_b = call(base_stats)
    tz_mut, tz_base = tooth_status_of(plz_m, TZ_ID), tooth_status_of(plz_b, TZ_ID)
    tz_eps = tooth_field_of(plz_m, TZ_ID, "dims_relying_on_eps_fallback") or []
    tz_flr = tooth_field_of(plz_m, TZ_ID, "near_constant_dims_floor_nonpositive") or []
    g.add("G52_Tz_denom_zero_bites",
          f"**{TZ_ID} 双向**：构造一维 `q99==q01` 且 `floor=0`（D 的字面构造，dim={d_probe}）⇒ "
          f"{TZ_ID}=RED 且**点名到维**；真实 stats ⇒ PASS",
          (tz_mut == "RED" and tz_base == "PASS" and d_probe in tz_eps and d_probe in tz_flr),
          f"构造 ⇒ {TZ_ID}=RED（`dims_relying_on_eps_fallback` 与 "
          f"`near_constant_dims_floor_nonpositive` 都含 dim {d_probe}）；真实 ⇒ PASS",
          (f"dim={d_probe}（运行时从 `near_constant_dims` 之外挑的**非近常量维**，不硬编码）"
           f" 构造 verdict={vz_m} {TZ_ID}={tz_mut} eps_fallback={tz_eps} floor_nonpositive={tz_flr}"
           f"｜真实 verdict={vz_b} {TZ_ID}={tz_base}"
           f"｜crash={(plz_m or {}).get('crash')!r}"),
          ("除零族不红 ⇒ ACT 线 `(x-mean)/(std+1e-6)` 那个失效形态（`normalize_processor.py:371-374` "
           "的 eps 兜底）会静默通过；真实数据也红 ⇒ 恒红闸（裁定 27.1）"),
          kind="measured",
          note=("构造里 `denom_effective[d]=0` 会让**别的**牙也红（实测 `Tres`=RED、`Tresw`=WARN、"
                "`Ts`=RED）⇒ 本 check **只判 `Tz` 的状态与它的点名维**，不判构造的整体 verdict"
                "（与 G50 的口径一致：合成构造的用途是极性，不是『这份 stats 可以进 BC』）。"),
          mutant_that_proves_it=f"M34_tz_denom_zero_tolerated（在本变异体副本内用**同一份谓词**重跑 ⇒ 翻 False）",
          ruling_ref="裁定 93.2 补丁① / 83.2")

    # ---- G53：`Tres_per_dim_resolution_floor`（裁定 93.2 补丁②，阈值边界被夹住）----
    vt7, _idst7, plt7 = call(base_stats, frames=squeezed(7))
    vt8, _idst8, plt8 = call(base_stats, frames=squeezed(8))
    tr7, tr8 = tooth_status_of(plt7, TRES_ID), tooth_status_of(plt8, TRES_ID)
    below7 = tooth_field_of(plt7, TRES_ID, "dims_below_non_near_constant_floor") or []
    below8 = tooth_field_of(plt8, TRES_ID, "dims_below_non_near_constant_floor") or []
    bins7 = tooth_field_of(plt7, TRES_ID, "bins_occupied_per_dim_resolution_caliber")
    g.add("G53_Tres_resolution_floor_bites_at_threshold",
          f"**{TRES_ID} 双向且**夹住阈值**：把非近常量维 dim={d_probe} 压到 **7** 个离散电平 ⇒ RED "
          f"且点名该维；压到 **8** 个 ⇒ PASS（8 = `d_calibrated_from_formal40_all_caliber` 的阈值本身）",
          (tr7 == "RED" and d_probe in below7 and tr8 == "PASS" and not below8
           and (bins7 is None or int(bins7[d_probe]) == 7)),
          (f"7 个电平 ⇒ {TRES_ID}=RED、`dims_below_non_near_constant_floor` 含 dim {d_probe}；"
          f"8 个电平 ⇒ PASS、该清单为空（⇒ 阈值 8 是被**夹住**的，不是「压得够狠才红」）"),
          (f"dim={d_probe} 7电平：verdict={vt7} {TRES_ID}={tr7} below={below7} bins={bins7}"
           f"｜8电平：verdict={vt8} {TRES_ID}={tr8} below={below8} "
           f"bins={tooth_field_of(plt8, TRES_ID, 'bins_occupied_per_dim_resolution_caliber')}"
           f"｜口径={tooth_field_of(plt7, TRES_ID, 'resolution_caliber')}"),
          ("分辨率下限不红 ⇒ 一维只占 3 个 bin（归一化后几乎不携带可分辨信息）也能进 BC；"
           "7 个也红 ⇒ 阈值被偷偷改小了（D 定的 8 不许动）；8 个也红 ⇒ 恒红闸"),
          kind="measured",
          note=("两个构造的**唯一变量**是该维的离散电平数（其余 13 维用真帧、stats 同一份）⇒ 对照成立。"
                "真实 formal-40 全量口径的绿由矩阵谓词 G27 判（本轮实测 49/49 行 PASS，"
                "非近常量维最小 22 = 2.75× 余量）。"),
          mutant_that_proves_it=f"M35_tres_resolution_floor_vacuous（在本变异体副本内用**同一份谓词**重跑 ⇒ 翻 False）",
          ruling_ref="裁定 93.2 补丁② / 94.2 / 83.2")

    # ---- G54：`Tresw` 与 `Tres` 的**分工**（WARN 登记 vs 硬红）----
    wstats = {k: (np.array(v, dtype=np.float64).copy() if isinstance(v, np.ndarray) else v)
              for k, v in base_stats.items()}
    wstats["denom_raw"][d_probe] = 1e-9      # 把 dim=d_probe 变成**近常量维**（floor 仍 > 0 ⇒ Tz/Tr1 不红）
    vw3, _idsw3, plw3 = call(wstats, frames=squeezed(3))
    vw1, _idsw1, plw1 = call(wstats, frames=squeezed(1))
    w3_res, w3_resw = tooth_status_of(plw3, TRES_ID), tooth_status_of(plw3, TRESW_ID)
    w1_res, w1_resw = tooth_status_of(plw1, TRES_ID), tooth_status_of(plw1, TRESW_ID)
    w3_warn = tooth_field_of(plw3, TRESW_ID, "dims_near_constant_below_warn_threshold") or []
    w1_below = tooth_field_of(plw1, TRES_ID, "dims_below_near_constant_floor") or []
    g.add("G54_Tresw_warn_and_Tres_hard_red_are_distinguishable",
          f"**{TRESW_ID} 与 {TRES_ID} 的分工可分辨**：把 dim={d_probe} 变成近常量维后 —— "
          f"3 个电平 ⇒ `Tresw`=**WARN** 且 `Tres`=PASS（2 ≤ 3 < 8）；1 个电平 ⇒ `Tres`=**RED**"
          "（< 2 = 该维不携带任何可分辨信息）且 `Tresw` 仍 WARN；两向 `Tz` 都保持 PASS",
          (w3_resw == "WARN" and w3_res == "PASS" and d_probe in w3_warn
           and w1_res == "RED" and d_probe in w1_below and w1_resw == "WARN"
           and tooth_status_of(plw3, TZ_ID) == "PASS" and tooth_status_of(plw1, TZ_ID) == "PASS"),
          ("3 电平 ⇒ Tresw=WARN、Tres=PASS；1 电平 ⇒ Tres=RED（`dims_below_near_constant_floor` "
           f"含 dim {d_probe}）、Tresw=WARN；两向 Tz=PASS（⇒ 红的是分辨率、不是分母）"),
          (f"dim={d_probe}（`denom_raw` 置 1e-9 造近常量维，`floor` 不动）"
           f"｜3电平：verdict={vw3} Tres={w3_res} Tresw={w3_resw} warn_dims={w3_warn} "
           f"Tz={tooth_status_of(plw3, TZ_ID)}"
           f"｜1电平：verdict={vw1} Tres={w1_res} Tresw={w1_resw} below_nc={w1_below} "
           f"Tz={tooth_status_of(plw1, TZ_ID)}"
           f"｜nc_used={tooth_field_of(plw3, TRES_ID, 'near_constant_dims_used')}"),
          ("两颗牙同红同绿 ⇒ 93.2 的「近常量维 <2 硬红 / <8 只 WARN」这个分层只是文案；"
           "`Tresw` 恒不出 WARN ⇒ 裁定 90.4-3 的 P1 分辨率债**登记缩水**（93.1-3 禁止的形态）"),
          kind="measured",
          mutant_that_proves_it=f"M36_tresw_warn_vacuous（在本变异体副本内用**同一份谓词**重跑 ⇒ 翻 False）",
          ruling_ref="裁定 93.2 / 90.4-3 / 83.2")

    # ---- G55：`Tbcad_admission_requires_green_gate`（裁定 93.4：准入必须 AND 闸 verdict；
    #      裁定 **97.3-3**：AND 的对象收窄为 `verdict_class1`）----
    # ⚠ 三个入参值是**构造**、不指任何真实产物（裁定 92.6：不许把"上一次取到的东西"当成
    #   "这一次真正要指的东西"）⇒ 字符串里就写明它是构造，避免被下游当成真实 run 的身份引用。
    CONSTRUCT_RUN_DIR = "CONSTRUCTED_not_a_real_run_dir（G55 的极性构造，不指任何真实产物）"
    CONSTRUCT_SHA12 = "000000000000"
    bc_kw = dict(source=nc.SOURCE_S1_DEMO, prov=FORMAL40_LABEL, consumer=nc.CONSUMER_BC,
                 gate_run_dir=CONSTRUCT_RUN_DIR, gate_verdict_sha256_12=CONSTRUCT_SHA12)
    # 裁定 97.3-3 ⇒ 极性构造从**四格**扩到**五格**。第 3 格（顶层 `RED` ∧ class-1 `PASS`
    #   ⇒ 本牙必须 PASS）是**新语义的唯一证明**：少了它，「AND 的是 class1 而不是顶层 verdict」
    #   这句话在码层无从分辨（缺陷类 ⑲ 的形状：报了绿、而绿来自判据根本没被行使）。
    # 第 4 格守三值纪律：顶层给 `PASS` 但**不给** class-1 ⇒ 必须红（不许拿顶层顶替、不静默当绿）。
    vb1, _idsb1, plb1 = call(base_stats, gate_verdict=nc.GATE_VERDICT_PASS,
                             gate_verdict_class1=nc.GATE_VERDICT_PASS, **bc_kw)
    vb2, _idsb2, plb2 = call(base_stats, gate_verdict="RED", gate_verdict_class1="RED", **bc_kw)
    vb3, _idsb3, plb3 = call(base_stats, gate_verdict="RED",
                             gate_verdict_class1=nc.GATE_VERDICT_PASS, **bc_kw)
    vb4, _idsb4, plb4 = call(base_stats, gate_verdict=nc.GATE_VERDICT_PASS,
                             gate_verdict_class1=None, **bc_kw)
    vb5, _idsb5, plb5 = call(base_stats, source=nc.SOURCE_S1_DEMO, prov=FORMAL40_LABEL,
                             consumer=nc.CONSUMER_PATH_CHECK, gate_verdict="RED",
                             gate_verdict_class1="RED",
                             gate_run_dir=CONSTRUCT_RUN_DIR, gate_verdict_sha256_12=CONSTRUCT_SHA12)
    tb = [tooth_status_of(p, TBCAD_ID) for p in (plb1, plb2, plb3, plb4, plb5)]
    adm = [(p.get("bc_admission_with_gate") or {}) for p in (plb1, plb2, plb3, plb4, plb5)]
    g.add("G55_Tbcad_admission_requires_green_gate",
          f"**{TBCAD_ID} 五向**：`admissible_for_bc=true` 时 —— class-1 `PASS` ⇒ PASS；"
          "class-1 `RED` ⇒ **RED**；**顶层 `RED` 而 class-1 `PASS` ⇒ PASS**（裁定 97.3-3 的收窄："
          "Ⅱ/Ⅲ 类 run 级元牙的红不再单独禁 BC）；**不给 class-1 证据**（`not_measured`）⇒ **RED**"
          "（不静默当绿、不拿顶层顶替）；`consumer=path_check` ⇒ N_A（不适用不出红，裁定 72-2）",
          (tb == ["PASS", "RED", "PASS", "RED", "N_A"]
           and adm[3].get("gate_verdict_class1_measurement_status") == "not_measured"
           and adm[0].get("gate_verdict_class1_measurement_status") == "measured"
           and adm[2].get("gate_verdict_class1_green") is True
           and adm[2].get("gate_verdict_green") is False
           and all(a.get("admissible_for_bc") is True for a in adm[:4])),
          ("PASS/RED/(顶层RED∧class1 PASS)⇒PASS/not_measured⇒RED/path_check⇒N_A 五向逐格相符；"
           "四个 bc 构造的 `admissible_for_bc` 都是 true（⇒ 红的那两格归因于**闸 class-1 判词**，"
           "不是标签）；第 3 格另证 `gate_verdict_green=False` 而本牙 PASS ⇒ AND 的确实是 class-1"),
          (f"statuses={tb} "
           f"class1_ms={[a.get('gate_verdict_class1_measurement_status') for a in adm]} "
           f"class1_green={[a.get('gate_verdict_class1_green') for a in adm]} "
           f"toplevel_green={[a.get('gate_verdict_green') for a in adm]} "
           f"admissible={[a.get('admissible_for_bc') for a in adm]} "
           f"verdicts={[vb1, vb2, vb3, vb4, vb5]} "
           f"gate_verdict_sha256_12={CONSTRUCT_SHA12}（构造值，非真实产物身份）"),
          ("`bc_admission()` 修前只看标签（对数据质量盲）⇒ 外部分析③「准入闸与质量闸脱钩（AND 不在码里）」"
           "就是这个形态；裁定 97.3-3 之前 AND 的是**顶层** `verdict` ⇒ 一颗 Ⅲ 类记账红"
           "（`G20_write_scope`，12:5x 那轮**实测到过**）就能把 BC 挡死，而它一个字节都不碰训练数据；"
           "不给 class-1 证据也算通过 ⇒ 红线 `absence_of_measurement_is_not_measurement_of_absence`；"
           "path_check 也出红 ⇒ 极性错（通路验证档不是 BC 输入）"),
          kind="measured",
          note=("本 check 判的是**契约层的 AND 是否在码里**。真实产物侧：主线 8 行的 `consumer` 是 "
                "`path_check` ⇒ `Tbcad` 合法地 N_A；BC 必红臂 8 行 `admissible_for_bc=false` ⇒ 第一子句"
                "就满足（PASS）。**两者都没有真正行使 AND** ⇒ 这一格只能由本构造证明，"
               "已如实登记（不是「矩阵里绿了就算证过」）。"
               "裁定 97.3-3 之后的**分工**：第 1/2/5 格守 93.4 的原语义（AND 在码里、极性正确）；"
               "第 3 格守**收窄**（顶层 RED 不再单独禁 BC，97.5 明禁把它当停训理由）；"
               "第 4 格守**三值纪律**（缺 class-1 证据 ⇒ 红，不许拿顶层 `verdict` 顶替）。"),
          mutant_that_proves_it=f"M37_tbcad_gate_verdict_ignored（在本变异体副本内用**同一份谓词**重跑 ⇒ 翻 False）",
          ruling_ref="裁定 93.4（E2）/ 97.3-3 / 97.5 / 83.2")

    ptab = polarity_table()
    pmx = polarity_rows_as_matrix(ptab)
    paudit = name_semantics_audit(pmx)
    pst = {k: v["statuses"] for k, v in ptab.items()}
    pcrash = sorted(k for k, v in ptab.items() if v.get("crash"))
    rc_nan = _recompute_measurement_complete(
        ((ptab.get("nan_in_eval") or {}).get("payload") or {}).get("declared_interval_conformance") or {})
    g.add("G43_iv_is_measured_tracks_recompute",
          f"`{TIV}` 的 ok **跟着闸侧独立重算走**：测量不完整（评估帧含 NaN）⇒ 必须红；"
          "完整 ⇒ 必须绿；且构造矩阵过**同一份**名实审计（裁定 90.4-1 牙③ 的可测入口）",
          (pst.get("nan_in_eval", {}).get(TIV) == "RED" and rc_nan.get("complete") is False
           and pst.get("inside", {}).get(TIV) == "PASS" and bool(paudit["ok"])
           and paudit["n_measurement_clauses_recomputed"] >= len(POLARITY_KINDS) - 1
           and not pcrash),
          (f"nan_in_eval ⇒ {TIV}=RED 且闸侧重算 complete=False；inside ⇒ PASS；"
           f"构造矩阵 name_semantics_audit.ok=True（{len(POLARITY_KINDS)} 个构造、0 崩溃）"),
          (f"nan_in_eval={pst.get('nan_in_eval', {}).get(TIV)} 闸侧重算={rc_nan.get('complete')} "
           f"nonfinite={rc_nan.get('nonfinite')} inside={pst.get('inside', {}).get(TIV)} "
           f"audit_ok={paudit['ok']} audit_viol={paudit['n_violations']} "
           f"meas_clauses={paudit['n_measurement_clauses_recomputed']} crash={pcrash} "
           f"violations={json.dumps(paudit['violations'][:3], ensure_ascii=False)[:400]}"),
          ("恒真的 `*_is_measured` ⇒ 「越界量已被测量」这句话没有牙：下游会拿一份**含 NaN 的**"
           "越界测量去论证『没有越界』（红线 `absence_of_measurement_is_not_measurement_of_absence`）。"
           "真数据上测量是完整的 ⇒ 恒真变异体在真数据上与正确实现读数相同，**只有**这个构造能分辨"),
          kind="measured",
          note=("牙③ 的实现口径：元闸 `gate_name_must_match_gate_semantics` 只有**一份**代码"
                "（`name_semantics_audit`），这里把极性构造拼成同形的 rows 喂给它"
                "（`polarity_rows_as_matrix`）⇒ 不是第二套判据。审计规则 1 就是"
                "`*_is_measured` 的 ok 必须等于闸侧重算的完整性"),
          mutant_that_proves_it=("M23_tiv_always_true（在本变异体副本内用同一份谓词重跑 ⇒ 翻 False）"),
          ruling_ref="裁定 90.4-1 牙③ / 88.3-1")
    g.add("G44_polarity_side_asymmetry_escape_vs_deficit",
          f"**分侧不对称**（裁定 90.4-1 第 4 条）：上侧逃逸 ⇒ `{TESC}`=RED 且 `{TLO}`=PASS；"
          f"下侧逃逸 ⇒ 两把都 RED（两把牙极性可分辨，不是同一把牙的两个名字）",
          (pst.get("escape", {}).get(TESC) == "RED" and pst.get("escape", {}).get(TLO) == "PASS"
           and pst.get("downside_escape", {}).get(TESC) == "RED"
           and pst.get("downside_escape", {}).get(TLO) == "RED"),
          ("escape：Tesc=RED、Tlo=PASS；downside_escape：Tesc=RED、Tlo=RED"
           "（⇒ Tlo 在两个构造上取值不同 = 它真的在判下侧）"),
          (f"escape={pst.get('escape')} downside_escape={pst.get('downside_escape')} "
           f"hcmax={[(k, (ptab[k].get('conformance') or {}).get('headroom_consumption_max')) for k in ('escape','downside_escape')]}"),
          ("两侧同红 ⇒ 分侧分治只是文案（`processor_pi05.py:77` 的结构不对称没人守）；"
           "两侧同绿 ⇒ 覆盖集跟着数据涨（= 裁定 87.3-2 条件 c 的赦免令形态）"),
          kind="measured",
          mutant_that_proves_it=("M21_coverage_target_ignored（覆盖集退回 build 帧 ⇒ 逃逸/覆盖不足都消失）"
                                 " / M20_headroom_consumption_zeroed（消耗比谎报为 0 ⇒ Tesc 失声）"),
          ruling_ref="裁定 90.4-1 第 4 条 / 90.3")
    g.add("G45_small_overflow_is_warned_never_red",
          "**小幅**越出声明区间（任一侧，均 < 1 bin 头寸）⇒ 四把牙一把都不许红，"
          f"且 `{TOVR}` 必须出 WARN 并带量级（裁定 90.4-1 第一条：永不因越界本身出红）",
          (all(pst.get(k, {}).get(t) not in ("RED", "ABSENT", "CRASH")
               for k in ("upside_small", "downside_small") for t in POLARITY_TEETH)
           and pst.get("upside_small", {}).get(TOVR) == "WARN"
           and pst.get("downside_small", {}).get(TOVR) == "WARN"
           and bool((ptab.get("upside_small", {}).get("conformance") or {}).get("dims_out"))
           and bool((ptab.get("downside_small", {}).get("conformance") or {}).get("dims_out"))),
          ("两个构造都：无 RED、Tovr=WARN；**且 `dims_out` 非空**（确实有越界可登记 ⇒ 本 check 非恒真）"),
          (f"upside_small={pst.get('upside_small')} dims_out={(ptab.get('upside_small', {}).get('conformance') or {}).get('dims_out')} "
           f"downside_small={pst.get('downside_small')} dims_out={(ptab.get('downside_small', {}).get('conformance') or {}).get('dims_out')}"),
          ("小幅越界就红 ⇒ 把裁定 90.4-1 刚撤回的极性又装回去（`jnt_range` 是软边界，裁定 90.2 #15）；"
           "不 WARN ⇒ 分辨率/饱和事实被静默吞掉（下游看不到量级）"),
          kind="measured",
          mutant_that_proves_it=("M22_widen_headroom_zeroed（展宽不留头寸 ⇒ 下侧小幅越界变成覆盖不足 ⇒ Tlo 红）"),
          ruling_ref="裁定 90.4-1 第 1 条 / 90.2 #15")
    g.add("G49_polarity_table_matches_ruling_90_4_1",
          f"**全表**：{len(POLARITY_EXPECT)} 个构造 × 4 把牙的状态逐格等于裁定 90.4-1 的期望表"
          "（期望表与一次性探针 `probe_ruling90_4_polarity/verdict.json` 同源）",
          (len(ptab) == len(POLARITY_EXPECT) and not pcrash
           and all(v.get("match") for v in ptab.values())),
          "每个构造 `statuses == POLARITY_EXPECT[kind]`，且 0 个构造崩溃",
          json.dumps({k: {"statuses": v["statuses"], "expected": v["expected"], "match": v["match"],
                          "crash": v.get("crash")} for k, v in ptab.items()},
                     ensure_ascii=False, sort_keys=True)[:1600],
          ("任何一格不符 ⇒ 契约层的极性与裁定原文不一致（本轮 D 的第 15/16/17 号同型错误正是"
           "极性写反造成的硬阻塞）；崩溃 ⇒ 判据变成 traceback，现场无法定位"),
          kind="measured",
          mutant_that_proves_it=("M20/M21/M23（各翻若干格；逐格归因见 G43/G44/G45）"),
          ruling_ref="裁定 90.4-1")

    # 4h-2) 裁定 90.4-1 **牙②** 的双臂对照：同一构造、同一批 held-out 帧，**只换覆盖目标**。
    # WHY 必须做成对照而不是单臂断言（本轮实测到的判据缺陷）：在 formal-40 **真数据**上把覆盖目标
    #   退回 `build_only`（变异体 M21），咬到的是 `Tcov_declared_interval_covered`（主线 8/8 行），
    #   `Te2` **没有**红 —— 因为 formal-40 的 held-out 帧（每方向最后一整集）恰好都落在 build 帧范围内。
    #   ⇒ 只判真数据无法证明牙② 有牙；必须补一个"held-out 帧真的越过声明下界"的构造，
    #   并且**唯一变量是覆盖目标**（否则对照不成立，只是两次不同的测量）。
    TE2 = "Te2_no_illegal_bin_heldout"
    TCOV = "Tcov_declared_interval_covered"
    ph = polarity_run("heldout_below_lo")                                       # ① 档（declared_interval）
    pb = polarity_run("heldout_below_lo", coverage_target=nc.COVERAGE_TARGET_BUILD_ONLY)
    a_st, b_st = (ph.get("all_statuses") or {}), (pb.get("all_statuses") or {})
    _fb1, _fe1 = polarity_frames("heldout_below_lo")
    _fb2, _fe2 = polarity_frames("heldout_below_lo")
    frames_identical = bool(np.array_equal(_fb1, _fb2) and np.array_equal(_fe1, _fe2))
    arm_iv = {TE2: a_st.get(TE2), TCOV: a_st.get(TCOV), "verdict": ph.get("verdict")}
    arm_bo = {TE2: b_st.get(TE2), TCOV: b_st.get(TCOV), "verdict": pb.get("verdict")}
    g.add("G50_build_only_coverage_makes_te2_red",
          f"**牙② 双臂对照**：held-out 帧下侧越出声明区间（< 1 bin 头寸）时 —— ① 档 ⇒ `{TE2}`=PASS "
          f"且 `{TCOV}`=PASS；`build_only` 档 ⇒ `{TE2}`=**RED**；两臂的 build/held-out 帧**逐位相同**"
          "（⇒ 唯一变量是覆盖目标，对照成立）",
          (a_st.get(TE2) == "PASS" and a_st.get(TCOV) == "PASS" and b_st.get(TE2) == "RED"
           and not ph.get("crash") and not pb.get("crash") and frames_identical),
          f"① 档：{TE2}=PASS、{TCOV}=PASS；build_only 档：{TE2}=RED；两臂帧逐位相同=True；0 崩溃",
          ("arm_declared_interval=" + json.dumps(arm_iv, ensure_ascii=False, sort_keys=True)
           + " arm_build_only=" + json.dumps(arm_bo, ensure_ascii=False, sort_keys=True)
           + f" frames_identical={frames_identical}"
           + f" crash_iv={ph.get('crash')!r} crash_bo={pb.get('crash')!r}"
           + " build_only_raised="
           + json.dumps([x.split(" ")[0] for x in (pb.get("raised") or [])], ensure_ascii=False)),
          ("① 档也红 ⇒ 覆盖策略没有正确性收益（裁定 90.4-2 的实测依据被推翻，① 该回退）；"
           "build_only 档不红 ⇒ `Te2` 恒真，牙② 只是文案（裁定 83.2）；"
           "两臂帧不同 ⇒ 差异可能来自数据而不是覆盖目标，对照无效"),
          kind="measured",
          note=("两臂的整体 `verdict` 都是 RED，红的**不是** `Te2` 而是构造自带的 "
                "`Tb_scale_floor_effective`（近常量维在合成数据上 bin 占用不足）⇒ 本 check 只判 "
                "`Te2`/`Tcov` 两把牙的状态，不判构造的整体 verdict。这是显式登记，不是回避："
                "合成构造的用途是**极性**，不是「这份 stats 可以进 BC」。"),
          mutant_that_proves_it=("M21_coverage_target_ignored（`coverage_must_cover` 忽略 target ⇒ "
                                 "① 档也退回 build 帧 ⇒ 两臂读数相同 ⇒ 本 check 翻 False；"
                                 "猴子补丁预演已实测 arm① 的 Te2 PASS→RED）"),
          ruling_ref="裁定 90.4-1 牙② / 90.4-2")

    # 4i) 牙 id 引用完整性（源码里引用的 id 必须真实存在；G46）
    audit_mx = None
    mxp = base_dir / "matrix.json"
    if mxp.is_file():
        try:
            audit_mx = json.loads(mxp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            audit_mx = None
    ca = tooth_name_citation_audit(ROOT, mx=audit_mx)
    g.add("G46_tooth_name_citation_integrity",
          f"源码里引用的每个牙 id 都**真实存在**（{ca['n_citations']} 处引用 / "
          f"{ca['n_source_files_scanned']} 个文件），历史引用必须带标记词",
          bool(ca["ok"]) and audit_mx is not None,
          ("悬空引用 = 0；`ROW_TAG_IDS` 每一项在生成器源码里有红标签锚点；"
           "live 集合来自 EXPECT_TEETH ∪ 产物实际出现 ∪ 勘误件牙 ∪ 已撤回 id"),
          (f"matrix_in_place={audit_mx is not None} ok={ca['ok']} n_dangling={ca['n_dangling']} "
           f"n_citations={ca['n_citations']} files={ca['n_source_files_scanned']}/3 "
           f"anchor_ok={ca['row_tag_anchor_ok']} digit_ids_covered={ca['regex_covers_digit_ids']} "
           f"dangling={json.dumps({k: [(x['file'], x['line']) for x in v] for k, v in ca['dangling_citations'].items()}, ensure_ascii=False)[:600]}"),
          ("引用一个盘上没有的对象 ⇒ 读者无法核，而它读起来像是有据的（裁定 92.3 的形态）。"
           "本轮实测到 5 处真缺陷：契约层散文 2 处改名漏改、生成器 `expected_red_teeth` 写了"
           "从未存在的 id、本闸散文 2 处缩写 id"),
          kind="measured",
          note=("审计口径本身也带自证：`regex_covers_digit_ids` 必须是 True —— 修前正则"
                "`\bT(?:[a-z]{1,4})_…` **匹配不到带数字的 id**（`Td2_…`/`Te2_…`/`Tp5_…`），"
                "而本轮真缺陷恰好只有一个不带数字的 id 被抓到 ⇒ 正则的覆盖面本身必须被登记"),
          mutant_that_proves_it=("M27_tesc_id_renamed_at_call_site（只改产出点的 id 字面量 ⇒ "
                                 "源码里的引用变成悬空）"),
          ruling_ref="裁定 92.3 / 87.2-1 / 92.6")

    return {"checks": g.checks,
            "predicates": {c["id"]: bool(c["ok"]) for c in g.checks},
            "identity": {"nc_file": nc.__file__,
                         "nc_mutant_id": getattr(nc, "__c2_mutant_id__", None),
                         "nc_sha256_12": sha12(Path(nc.__file__)),
                         "gate_sha256_12": sha12(Path(__file__).resolve()),
                         "base_dir": str(base_dir)}}


# --------- 裁定 90.4-1 三颗双向牙的**翻转台账**（G48 的判据来源） ---------
# WHY 抽成模块级函数（本轮实测到的代价）：这段最初内联在 `main()` 里，一个 `KeyError`
# （`checks_flipped` 只写进了 `bite_evidence` 子字典、却在 observed 串里按顶层键取）在**全部 24 个
# 文件级变异体跑完之后**才炸 ⇒ 整轮 ~6 min 白跑，而 `--skip-file-mutants` 的冒烟跑走的是 N_A 分支、
# **根本碰不到这段**。抽出来之后可以用合成台账直接单测三种形态（全咬到 / 少一颗 / 咬到但证据面不对）。
T1_ID = "Tesc_no_covered_window_escape"
T2_ID = "Te2_no_illegal_bin_heldout"
T3_ID = "Tiv_out_of_declared_interval_is_measured"
TCOV_ID = "Tcov_declared_interval_covered"
TEETH_90_4_1 = (
    {"tooth": "牙①（把头寸消耗推过 1.0 的变异体必须红）",
     "mutant": "M32_headroom_bins_halved", "bite_tooth_id": T1_ID,
     "bite_surface": "real_data_matrix",
     "checks": ["G39_polarity_ruling_90_4_1_on_real_data"]},
    {"tooth": "牙②（把下侧覆盖缩回 build_only 的变异体必须让 Te2 红）",
     "mutant": "M21_coverage_target_ignored", "bite_tooth_id": T2_ID,
     "bite_surface": "polarity_construct",
     "checks": ["G50_build_only_coverage_makes_te2_red"]},
    {"tooth": "牙③（把测量牙改成恒真的变异体必须被元闸抓到）",
     "mutant": "M23_tiv_always_true", "bite_tooth_id": T3_ID,
     "bite_surface": "polarity_construct",
     "checks": ["G43_iv_is_measured_tracks_recompute",
                "G49_polarity_table_matches_ruling_90_4_1"]},
)


def ruling_90_4_1_teeth_ledger(proof_ledger: list, by_id: dict, probe_runs: dict) -> dict:
    """逐颗牙算「哪条 check 被哪个变异体翻了 + 咬到的牙 id 在哪个面上被看见」。

    返回 `ok / missed / extra / all_caught / ledger / observed / tooth2_divergence /
    guard_fired_first_attempt`。`ok` **只认本轮翻转台账**；两条披露项随产物落盘但不进 `ok`
    （红线 `redline_provenance_discipline`：历史/声明值不得作 blocking）。
    """
    # WHY 单列一条：D 在 90.4-1 明写"双向牙（三颗，缺一不可）"且"牙必须报 missed/extra/all_caught"。
    # 三颗牙的证据**落在不同面**上（牙① 在真数据 matrix、牙②/③ 在极性构造），若只报一句"三颗都有"
    # 就没法核 ⇒ 这里逐颗记"哪条 check 被哪个变异体翻"+"咬到的牙 id 在哪个面上被看见"。
    T1_ID, T2_ID, T3_ID = ("Tesc_no_covered_window_escape", "Te2_no_illegal_bin_heldout",
                           "Tiv_out_of_declared_interval_is_measured")
    TCOV_ID = "Tcov_declared_interval_covered"
    TEETH_90_4_1 = (
        {"tooth": "牙①（把头寸消耗推过 1.0 的变异体必须红）",
         "mutant": "M32_headroom_bins_halved", "bite_tooth_id": T1_ID,
         "bite_surface": "real_data_matrix",
         "checks": ["G39_polarity_ruling_90_4_1_on_real_data"]},
        {"tooth": "牙②（把下侧覆盖缩回 build_only 的变异体必须让 Te2 红）",
         "mutant": "M21_coverage_target_ignored", "bite_tooth_id": T2_ID,
         "bite_surface": "polarity_construct",
         "checks": ["G50_build_only_coverage_makes_te2_red"]},
        {"tooth": "牙③（把测量牙改成恒真的变异体必须被元闸抓到）",
         "mutant": "M23_tiv_always_true", "bite_tooth_id": T3_ID,
         "bite_surface": "polarity_construct",
         "checks": ["G43_iv_is_measured_tracks_recompute",
                    "G49_polarity_table_matches_ruling_90_4_1"]},
    )
    flips = {(e["check_id"], e["mutant"]) for e in proof_ledger if e["flip_measured"]}

    def red_scopes(mid: str) -> dict:
        """一个变异体的红牙集合，**两个口径都给**（本轮实测到的口径陷阱）。

        ⚠ WHY 不能只用 `red_teeth_counts`（= 全 matrix 并集）：主线 matrix 是 **49 行的超集**
          （25 行基线三臂 + YAM，再加 8+8+8 主线三臂），而 stress / YAM 行上的
          `Td1/Td2/Te1/Te2/Tsat/Tr2/Tc` 红来自**源不匹配**（与本轮要判的覆盖目标/头寸无关）
          ⇒ 用并集报「牙② 在真数据上咬到了什么」会把「主线 8 行里 `Te2` 命中 **0** 行」
          读成「`Te2` 在，咬到了」。这正是缺陷类 ⑰（聚合量掩盖逐维/逐臂失效）
          在**报告口径**上的同型形态 —— C2 在自己的新代码里先犯了一次，同一轮改判。
        """
        rec = by_id.get(mid) or {}
        rows = ((rec.get("matrix") or {}).get("rows") or [])
        ml = [r for r in rows if r.get("arm") == "s1_mainline_path_check"]
        return {"whole_matrix_union": rec.get("red_teeth_counts") or [],
                "mainline_rows": ml,
                "mainline_union": sorted({t for r in ml for t in (r.get("red_ids") or [])})}

    ledger_90_4_1 = []
    for spec in TEETH_90_4_1:
        mid = spec["mutant"]
        flipped = sorted(c for c in spec["checks"] if (c, mid) in flips)
        rec_m, pr_m = by_id.get(mid) or {}, probe_runs.get(mid) or {}
        sc = red_scopes(mid)
        rtc = sc["mainline_union"]              # 判据口径 = **主线臂**（WHY 见 `red_scopes`）
        n_hit = sum(1 for r in sc["mainline_rows"]
                    if spec["bite_tooth_id"] in (r.get("red_ids") or []))
        bite = {"surface": spec["bite_surface"], "bite_tooth_id": spec["bite_tooth_id"],
                "in_real_data_red_teeth": ((spec["bite_tooth_id"] in rtc) if rtc else None),
                "real_data_scope": "s1_mainline_path_check（主线臂；**不是**全 matrix 并集）",
                "real_data_mainline_rows_hit": (n_hit if sc["mainline_rows"] else None),
                "real_data_mainline_rows_n": (len(sc["mainline_rows"]) or None),
                "real_data_red_teeth": rtc[:14],
                "real_data_whole_matrix_union_NOT_the_scope": sc["whole_matrix_union"][:16],
                "mutant_identity_self_proof_ok": (rec_m.get("identity_self_proof_ok")
                                                  if rec_m else pr_m.get("identity_self_proof_ok")),
                "probe_ok": pr_m.get("ok"),
                "checks_flipped": flipped}
        # 牙① 的咬合证据在**真数据**上（`Tesc` 必须出现在 M32 的红牙集合里）；
        # 牙②/③ 的咬合证据在**构造**上 —— 由被翻的那条 check 自己的断言承担
        #   （G50 判 Te2 PASS→RED；G43 判 nan_in_eval 的 Tiv=RED）⇒ 翻转记录即咬合证据。
        bite["ok"] = (bool(rtc) and spec["bite_tooth_id"] in rtc) \
            if spec["bite_surface"] == "real_data_matrix" else bool(flipped)
        ledger_90_4_1.append({**spec, "caught": (len(flipped) == len(spec["checks"])),
                              "bite_evidence": bite})
    missed = [e["tooth"] for e in ledger_90_4_1 if not (e["caught"] and e["bite_evidence"]["ok"])]
    declared_pairs = {(c, e["mutant"]) for e in TEETH_90_4_1 for c in e["checks"]}
    ledger_check_ids = {c for e in TEETH_90_4_1 for c in e["checks"]}
    extra = sorted({f"{e['check_id']}<-{e['mutant']}" for e in proof_ledger
                    if e["flip_measured"] and e["check_id"] in ledger_check_ids
                    and (e["check_id"], e["mutant"]) not in declared_pairs})
    all_caught = (not missed)
    # 牙② 在**真数据**上的落点与 D 的字面判据不同（本轮实测）⇒ 显式披露，不含在 `caught` 里、
    # 也**不**由 C2 改写 D 的判据文字（升级项，见交接件）。
    m21_sc = red_scopes("M21_coverage_target_ignored")
    m21_ml = m21_sc["mainline_rows"]
    m21_te2_rows = sum(1 for r in m21_ml if T2_ID in (r.get("red_ids") or []))
    m21_tcov_rows = sum(1 for r in m21_ml if TCOV_ID in (r.get("red_ids") or []))
    tooth2_divergence = {
        "d_literal_text": "裁定 90.4-1 牙②：把下侧覆盖缩回 `build_only` 的变异体必须让 "
                          "`Te2_no_illegal_bin_heldout` 红",
        "measured_on_formal40": {
            "scope": "s1_mainline_path_check（主线臂）—— **判据口径**",
            "n_mainline_rows": len(m21_ml),
            f"{T2_ID}_rows_hit": m21_te2_rows,
            f"{TCOV_ID}_rows_hit": m21_tcov_rows,
            "mainline_red_ids_union": m21_sc["mainline_union"],
            "whole_matrix_union_NOT_the_scope": m21_sc["whole_matrix_union"],
            "why_both_calibers_are_shown": (
                "全 matrix 并集里 `Te2` **在**（stress / YAM 行因**源不匹配**而红，与覆盖目标无关）⇒ "
                "只报并集会把「主线 8 行里 `Te2` 命中 0 行」读成「咬到了」。本轮实测：并集含 "
                f"`{T2_ID}`，而主线口径下 `{T2_ID}` 命中 {m21_te2_rows} 行、`{TCOV_ID}` 命中 "
                f"{m21_tcov_rows} 行。**这是缺陷类 ⑰（聚合量掩盖逐臂失效）在报告口径上的同型形态**，"
                "C2 在自己的新代码里先犯了一次（首版 `tooth2_divergence` 就是并集口径），同一轮改判"),
        },
        "why": ("formal-40 的 held-out 帧（每方向最后一整集）恰好都落在 build 帧范围内 ⇒ 覆盖集退回 "
                "build 帧**不会**产出非法 bin；它咬到的是「覆盖集不再覆盖声明区间」这把牙"
                f"（`{TCOV_ID}`），主线 8/8 行"),
        "where_the_literal_form_is_proven": (
            "G50 的 `heldout_below_lo` 构造：held-out 帧下侧越出声明区间 0.005（< 该维 1 bin 头寸 "
            "0.015625），① 档 Te2=PASS、build_only 档 Te2=RED，两臂 build/held-out 帧**逐位相同** "
            "⇒ 唯一变量是覆盖目标"),
        "status": "escalated_to_d（C2 不改 D 的判据文字，只报落点差异）",
    }
    m32_guard = {
        "field": "guard_fired_first_attempt",
        "value": True,
        "provenance": "historical_artifact_on_disk（本轮**未**重跑那次单锚点尝试）",
        "evidence_path": ("runs/vla/c2_norm_contract_20260929/gate/proto_teeth_20260930_0545/"
                          "mutants/M32_headroom_bins_halved/"),
        "evidence": ("该副本里 `harness/norm_contract.py:68` 已是 `HEADROOM_BINS_DEFAULT = 0.5`（锚点 1 "
                     "已改）而 `scripts/c2_build_norm_stats.py:61` 的卫语句 "
                     "`assert HEADROOM_BINS == 1.0` **仍在位**，且该目录下**没有 `out/`** ⇒ 生成器在 "
                     "import 期即 AssertionError 退出、连 matrix 都不产。"),
        "meaning": ("卫语句挡住了「改头寸却沿用 representation_version 读数」的形态 ⇒ M32 必须是"
                    "**双锚点**变异体（连卫语句一起拔），这条要求本身就来自这次实测"),
        "counts_toward_ok": False,
        "why_not_in_ok": ("G48 的 `ok` 只认**本轮**翻转台账；把一个 run 目录外的历史 proto 件写进判据 "
                          "= 让本 check 依赖它管不到的文件（同 G20 的写入面纪律）"),
    }
    observed = ("missed=" + json.dumps(missed, ensure_ascii=False)
                + " all_caught=" + json.dumps(all_caught)
                + " extra=" + json.dumps(extra, ensure_ascii=False)
                + " ledger=" + json.dumps(
                    [{"tooth": e["tooth"], "mutant": e["mutant"], "caught": e["caught"],
                      "checks_flipped": e["bite_evidence"]["checks_flipped"],
                      "bite_ok": e["bite_evidence"]["ok"],
                      "bite_surface": e["bite_evidence"]["surface"],
                      "in_real_data_red_teeth": e["bite_evidence"]["in_real_data_red_teeth"],
                      "identity_ok": e["bite_evidence"]["mutant_identity_self_proof_ok"]}
                     for e in ledger_90_4_1], ensure_ascii=False)
                + " tooth2_divergence=" + json.dumps(tooth2_divergence["measured_on_formal40"],
                                                     ensure_ascii=False))
    return {"ok": bool(all_caught and len(ledger_90_4_1) == len(TEETH_90_4_1)),
            "missed": missed, "extra": extra, "all_caught": all_caught,
            "ledger": ledger_90_4_1, "observed": observed,
            "tooth2_divergence": tooth2_divergence,
            "guard_fired_first_attempt": m32_guard}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate-root", default=str(GATE_ROOT))
    ap.add_argument("--skip-file-mutants", action="store_true", help="只跑基线三臂 + 进程内变异体")
    ap.add_argument("--probe-inprocess", metavar="OUT_JSON",
                    help="**探针模式**：只跑 `inprocess_probes()`，把每条 check 的谓词真值落盘后退出。"
                         "用于在变异体副本内重跑**同一份谓词代码**（裁定 83.2）。不建 run 目录、不写别处。")
    ap.add_argument("--probe-run-dir", metavar="DIR",
                    help="配合 --probe-inprocess：其下的 `stats/` 为输入（真仓档 = `<run>/arm_baseline`）")
    ap.add_argument("--rerun-reason", default=None, metavar="TEXT",
                    help="裁定 97.4：每次重跑全量闸**前**必须写一句理由（原样落进产物 `rerun_reason`）。"
                         "不给 ⇒ 产物里记 `not_declared`（三值纪律：不猜、不静默当已声明）。")
    args = ap.parse_args()

    if args.probe_inprocess:
        if not args.probe_run_dir:
            raise SystemExit("--probe-inprocess 需要 --probe-run-dir（否则不知道读哪一份 stats）")
        bd = Path(args.probe_run_dir)
        if not bd.is_absolute():
            bd = (Path.cwd() / bd).resolve()
        if not (bd / "stats").is_dir():
            raise SystemExit(f"探针输入目录缺 stats/：{bd}")
        pr = inprocess_probes(bd)
        doc = {"artifact": "c2_inprocess_teeth_probe", "generated_at": now_iso(),
               "predicates": pr["predicates"], "identity": pr["identity"],
               "observed": {c["id"]: c["observed"] for c in pr["checks"]},
               "statuses": {c["id"]: c["status"] for c in pr["checks"]},
               "load_pair": load_pair()}
        op = Path(args.probe_inprocess)
        if not op.is_absolute():
            op = (Path.cwd() / op).resolve()
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"probe_out": str(op), "predicates": pr["predicates"],
                          "nc_mutant_id": pr["identity"]["nc_mutant_id"],
                          "nc_file": pr["identity"]["nc_file"],
                          "nc_sha256_12": pr["identity"]["nc_sha256_12"]}, ensure_ascii=False, indent=2))
        return 0

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.gate_root) / f"run_{ts}"
    if run_dir.exists():
        raise SystemExit(f"拒绝开工：run 目录已存在 {run_dir}（不复用、不改名）")
    run_dir.mkdir(parents=True)
    t_start = time.time()
    gate = Gate()
    evid = {"gate": str((Path(__file__).resolve()).relative_to(ROOT)), "gate_sha256_12": sha12(Path(__file__).resolve()),
            "contract_module": {"path": "harness/norm_contract.py", "sha256_12": sha12(ROOT / "harness/norm_contract.py"),
                                "lines": len((ROOT / "harness/norm_contract.py").read_text().splitlines())},
            "builder": {"path": BUILD, "sha256_12": sha12(ROOT / BUILD)},
            "physical_range_correction": {"path": f"{NORM_DIR.relative_to(ROOT)}/{PR_JSON}",
                                          "sha256_12": sha12(NORM_DIR / PR_JSON)},
            "started_at": now_iso(), "run_dir": str(run_dir.relative_to(ROOT))}

    # ---------- 1) 基线三臂（真跑） ----------
    arms = {}
    # 权威档在位 = npz **与** formal lerobot 目录都在（前者是权威接口，后者是交叉核对臂）。
    # 只在 npz 在位时也跑（生成器会把交叉核对臂登记为未测），但**两者都在**才等于裁定 90.4-4 的双臂形态。
    formal_npz_present = (ROOT / FORMAL40_NPZ).is_file()
    formal_dir_present = (ROOT / FORMAL40_DIR / "pi05_lerobot" / "data").is_dir()
    pilot_present = formal_npz_present          # 变量名保留：下面所有"主线臂是否执行"的判据都读它
    MAINLINE_EXTRA = ["--s1-frames", FORMAL40_NPZ] + (
        ["--s1-lerobot", FORMAL40_DIR] if formal_dir_present else [])
    arm_specs = [("baseline", []), ("no_widen", ["--no-widen"]), ("floor_off", ["--floor-coef-scale", "0"])]
    if pilot_present:
        arm_specs.append(("mainline", MAINLINE_EXTRA))
    for name, extra in arm_specs:
        od = run_dir / f"arm_{name}"
        rr = run_py(ROOT / BUILD, build_args(od, extra), cwd=ROOT)
        mj = od / "matrix.json"
        arms[name] = {"run": rr, "matrix": (json.loads(mj.read_text(encoding="utf-8")) if mj.exists() else None),
                      "matrix_path": str(mj.relative_to(ROOT)) if mj.exists() else None,
                      "matrix_sha256_12": sha12(mj) if mj.exists() else None}
    base = arms["baseline"]["matrix"]
    mx_main = (arms.get("mainline") or {}).get("matrix")

    gate.add("G0_arms_executed", "三臂都以 exit=0 执行完并产出 matrix.json",
             all(a["run"]["exit"] == 0 and a["matrix"] is not None for a in arms.values()),
             "3/3 exit=0 且 matrix.json 存在",
             "; ".join(f"{k}: exit={v['run']['exit']} matrix={'yes' if v['matrix'] else 'NO'}"
                       f" elapsed={v['run']['elapsed_s']}s" for k, v in arms.items()),
             "任一臂非 0 退出或没产物 ⇒ 后面的极性判定都无意义",
             kind="execution_precondition",
             note=("数值条件见各臂 run.load_pair（loadavg + nr_throttled）。本 check 是**执行前提**、"
                   "不是判定牙：失效形态 = 任一臂非 0 退出或无 matrix.json，此时本闸立即收口写 "
                   "verdict=RED（见 baseline 缺失分支）⇒ 非恒真"),
             mutant_that_proves_it="n_a_execution_precondition（失效即整闸提前 RED）")
    if base is None:
        (run_dir / "gate_verdict.json").write_text(json.dumps(
            {"verdict": "RED", "reason": "baseline 臂没产出 matrix.json", "evidence": evid,
             "checks": gate.checks, "arms": {k: v["run"] for k, v in arms.items()}},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"verdict": "RED", "reason": "baseline arm failed"}, ensure_ascii=False))
        return 1

    normal = [(i, r) for i, r in rows_by(base) if not r.get("is_must_red_branch") and not r.get("is_stress_branch")]
    stress = [(i, r) for i, r in rows_by(base) if r.get("is_stress_branch")]
    mustred = [(i, r) for i, r in rows_by(base) if r.get("is_must_red_branch")]
    hold = [(i, r) for i, r in rows_by(base, tag="-holdphase")]

    # ---------- 2) 基线极性 ----------
    gate.add("G1_baseline_verdict_pass", "基线 matrix 顶层 verdict = PASS",
             pred_G1(base), "verdict == PASS", f"verdict={base.get('verdict')}",
             "基线不绿 ⇒ 契约层自己就不自洽", mutant_that_proves_it="M1_non_raising / M3_payload_recompute_identity")
    gate.add("G2_normal_rows_all_pass", f"{NORMAL_ROW_COUNT} 个非 stress/非必红行全 PASS（全枚举）",
             pred_G2(base),
             f"n_rows={NORMAL_ROW_COUNT} 且逐个 verdict==PASS",
             f"n_rows={len(normal)} 非 PASS 行={[(i, r['verdict'], sorted(red_ids(r))) for i, r in normal if r['verdict'] != 'PASS']}",
             "有非 stress 行红 ⇒ 要么牙极性错，要么实现有缺陷",
             mutant_that_proves_it="M1_non_raising（会让本该红的行也变绿？不 —— 它让红行不抛，被一致性牙抓）")
    gate.add("G3_stress_rows_all_red", f"{STRESS_ROW_COUNT} 个跨策略 stress 行全 RED，且由 Td2/Te2 咬",
             pred_G3(base),
             "8/8 RED 且 red ⊇ {Td2_clip_heldout, Te2_no_illegal_bin_heldout}",
             f"n={len(stress)} 非 RED={[(i, r['verdict']) for i, r in stress if r['verdict'] != 'RED']} "
             f"咬合情况={[(i, sorted(red_ids(r))) for i, r in stress][:2]}",
             "stress 行不红 ⇒ held-out 那两把牙是恒真的（等于没有牙）",
             mutant_that_proves_it="M1_non_raising")
    gate.add("G4_must_red_row_red_with_source_tooth", "YAM 必红行 RED 且含 Tr2（stats 源禁用）",
             pred_G4(base),
             "1/1 RED 且 Tr2 ∈ red",
             (f"n={len(mustred)} verdict={mustred[0][1]['verdict'] if mustred else None} "
              f"red={sorted(red_ids(mustred[0][1])) if mustred else None}"),
             "YAM 行不红 ⇒ 主线禁用项可以被静默搬用（裁定 43.4/52/61 失效）",
             mutant_that_proves_it="M1_non_raising")
    rt_bad = [(i, (r.get("roundtrip") or {}).get("verdict_from_file")) for i, r in rows_by(base)
              if not (r.get("roundtrip") or {}).get("match")]
    gate.add("G5_roundtrip_all_match", "**落盘 stats 文件复算** 与内存判定逐行一致（25/25）",
             pred_G5(base),
             "每一行 roundtrip.match == true",
             f"n_rows={len(base['rows'])} 失配行={rt_bad}",
             "失配 ⇒ 闸判的不是交付物（本轮实测到过：IDENTITY 档 center/gain 被落盘侧重算）",
             mutant_that_proves_it="M3_payload_recompute_identity")
    schema_need = {"id", "ok", "status", "required", "observed", "red_when"}
    all_teeth = [t for _, r in rows_by(base) for t in (r.get("teeth") or [])]
    missing_fields = sorted({t.get("id", "<no-id>") for t in all_teeth if not schema_need <= set(t)})
    tr3_diag = [t["status"] for _, r in rows_by(base) if not r.get("is_must_red_branch")
                for t in (r.get("teeth") or []) if t["id"] == "Tr3_near_constant_floor_material"]
    gate.add("G6_schema_and_applies_when", "逐牙字段符合最小公共 schema，且 Tr3 在诊断臂出 N_A（不出红）",
             pred_G6(base),
             "每牙含 id/ok/status/required/observed/red_when；诊断臂 Tr3 全 N_A",
             f"n_teeth={len(all_teeth)} 缺字段牙={missing_fields} Tr3 诊断臂状态集合={sorted(set(tr3_diag))}",
             "字段缺 ⇒ 汇总器无法统一读；Tr3 在不适用的臂上出红 ⇒ 假红（裁定 72-2 审点①③）",
             mutant_that_proves_it="M5_schema_field_dropped / M6_tr3_always_blocking（实测翻转见 G24 台账）",
             ruling_ref="裁定 78.2 / 72-2")

    cons_base = [(i, sorted(red_ids(r))) for i, r in rows_by(base)
                 if "Tconsistency_raise_matches_verdict" in red_ids(r)]
    teeth_union = sorted({tt["id"] for _, r in rows_by(base) for tt in (r.get("teeth") or [])})
    expect_teeth = sorted(["Ta_features_non_empty", "Tb_scale_floor_effective", "Tc_start_pose_coverage",
                           "Tcov_declared_interval_covered",
                           "Td1_clip_build_frames", "Td2_clip_heldout", "Te1_no_illegal_bin_build",
                           "Te2_no_illegal_bin_heldout", "Tr1_near_constant_has_floor",
                           "Tr2_stats_source_allowed", "Tr3_near_constant_floor_material",
                           "Ts_stats_arrays_present", "Tsat_saturation_dims_zero", "Tw_ctrlrange_coverage",
                           "Tiv_out_of_declared_interval_is_measured",
                           "Tesc_no_covered_window_escape",
                           "Tlo_no_downside_coverage_deficit",
                           "Tovr_out_of_interval_overflow_is_warned",
                           "Tz_denom_strictly_positive", "Tres_per_dim_resolution_floor",
                           "Tresw_near_constant_low_resolution_is_warned",
                           "Tbcad_admission_requires_green_gate",
                           TP4, TP5])
    assert expect_teeth == EXPECT_TEETH, "main 内的牙清单与模块级 EXPECT_TEETH 漂移了（谓词必须只有一份）"
    gate.add("G21_baseline_invariants",
             f"基线不变式：一致性牙 0 次命中，且 {len(EXPECT_TEETH)} 把牙一把不少（全枚举，不抽样）",
             pred_G21(base),
             ("Tconsistency 命中 0 行；牙集合 == "
              f"{len(EXPECT_TEETH)} 把（全枚举，直接从 EXPECT_TEETH 渲染 ⇒ 文案不可能与常量漂移）："
              f"{', '.join(EXPECT_TEETH)}）；**旧 id "
              f"{WITHDRAWN_TOOTH_IDS} 不得出现**（裁定 90.4-1 撤回其极性）"),
             f"Tconsistency 命中行={cons_base}；实测牙集合 n={len(teeth_union)} 差集="
             f"{sorted(set(expect_teeth) ^ set(teeth_union))}",
             "少一把牙 ⇒ 判据被悄悄删了；一致性牙出现 ⇒ 契约层算出红却没抛（M1 的形态）",
             mutant_that_proves_it="M1_non_raising", ruling_ref="裁定 27.1（恒真的闸等于没有闸）")
    _g58_base, _g58_main = pred_G58(base), (None if mx_main is None else pred_G58(mx_main))
    gate.add("G58_ruling_93_polarity_not_relaxed",
             "**裁定 93.1 的极性没被偷偷撤回、93.2 明令保护的八颗牙一颗都没被放宽**（机器核，"
             "不靠人 diff 散文）：`Tb`/`Tr3` 全行 `blocking=False`；`Tz`/`Tres`/`Tbcad` 全行 "
             "`blocking=True`；`Tresw` 全行 `blocking=False`；受保护八颗全行 `blocking=True`"
             "（唯一例外 = 诊断档两臂的 held-out 家族三颗，已显式登记且与上一轮权威跑逐格相同）",
             bool(_g58_base) and _g58_main is not False,
             ("基线臂矩阵与主线臂矩阵**都**满足上述四条极性；例外只允许 "
              f"{list(NON_BLOCKING_EXCEPTION_ARMS)} × {list(NON_BLOCKING_EXCEPTION_TEETH)}"),
             (f"pred_G58(baseline)={_g58_base} pred_G58(mainline)={_g58_main} "
              f"受保护八颗={list(PROTECTED_TEETH_93_2)} 93.1转WARN={list(RULING_93_1_WARN_TEETH)} "
              f"93.2硬红={list(RULING_93_2_HARD_TEETH)} 例外臂={list(NON_BLOCKING_EXCEPTION_ARMS)}"),
             ("受保护的牙被降软 ⇒ 「这不是放宽」这句话变成假话（D 的验收条款：`Tr1`/`Te1`/`Te2`/"
              "`Tesc`/`Td1`/`Td2`/`Tp5`/`Tsat` 一颗都没被放宽）；`Tb`/`Tr3` 变回 blocking ⇒ "
              "未经 D 裁定就撤回 93.1；`Tresw` 变 blocking ⇒ 把 Ⅱ 类登记当 Ⅰ 类阻塞"
              "（= D 自己记的同型错误 #20 的形态）"),
             kind="measured",
             note=("例外为什么合法：`env_holdphase`/`env_randomphase` 是**诊断档**（非部署分布），"
                   "held-out 家族在那两臂上本来就 `force_blocking=False`（裁定 51① 对 ctrlrange "
                   "覆盖率的处置同族：拿非部署分布的帧判红 = 极性错）。实测本跑与上一轮权威跑 "
                   "`run_20260930_073852` 在这两臂的 `blocking` 读数**逐格相同** ⇒ 不是本轮引入的放宽。"),
             mutant_that_proves_it=("M6_tr3_always_blocking（把 `blocking=True, applies_when=True` "
                                    "装回去 ⇒ 基线臂矩阵上本谓词翻 False；实测台账见 proof_ledger）"),
             ruling_ref="裁定 93.1 / 93.2 / 95.1-8（已修好的检查一个都不撤）")

    # ---------- 3) 两个输入级变异臂的极性 ----------
    nw, fo = arms["no_widen"]["matrix"], arms["floor_off"]["matrix"]
    nw_tc = [(i, sorted(red_ids(r))) for i, r in rows_by(nw) if "Tc_start_pose_coverage" in red_ids(r)] if nw else []
    gate.add("G7_no_widen_bites_Tc", "`--no-widen` 必须由 **Tc（起态覆盖）** 咬红，且覆盖全部 25 行",
             bool(nw) and nw.get("verdict") == "RED" and len(nw_tc) == len(nw["rows"]),
             f"verdict=RED 且 {len(nw['rows']) if nw else 0}/{len(nw['rows']) if nw else 0} 行含 Tc",
             f"verdict={nw.get('verdict') if nw else None} 含 Tc 的行数={len(nw_tc)}",
             "去掉 widen 而不红 ⇒ 起态覆盖那把牙没牙（π₀.₅ 会拿到 bin -1，A2 已实测该现象）",
             mutant_that_proves_it="本臂自身即变异体（输入级）")
    fo_tr1 = [(i, sorted(red_ids(r))) for i, r in rows_by(fo, tag="-holdphase") if "Tr1_near_constant_has_floor" in red_ids(r)] if fo else []
    gate.add("G8_floor_off_bites_Tr1", "`--floor-coef-scale 0` 必须由 **Tr1（近常量维无下限）** 咬红全部 hold 行",
             bool(fo) and fo.get("verdict") == "RED" and len(fo_tr1) == HOLD_ROW_COUNT,
             f"verdict=RED 且 {HOLD_ROW_COUNT}/{HOLD_ROW_COUNT} 个 hold 行含 Tr1",
             f"verdict={fo.get('verdict') if fo else None} 含 Tr1 的 hold 行数={len(fo_tr1)}",
             ("关掉下限而不红 ⇒ Tr1 恒真。**本日实测过这个缺陷两次**："
              "① 近常量判据读 widen 后的 span（被覆盖头寸抹平）；② 标记阈值 1e-3 低于数据最小值 1.648e-3"),
             mutant_that_proves_it="M2_near_constant_always_empty")
    nw_ids = {x for _, r in rows_by(nw or {"rows": []}) for x in red_ids(r)}
    fo_ids = {x for _, r in rows_by(fo or {"rows": []}) for x in red_ids(r)}
    gate.add("G9_two_mutations_distinguishable", "两个输入级变异体咬的牙**不同**（极性可分辨）",
             bool(nw) and bool(fo) and ("Tc_start_pose_coverage" in nw_ids) and ("Tr1_near_constant_has_floor" in fo_ids)
             and nw_ids != fo_ids,
             "Tc ∈ no_widen 的牙集合、Tr1 ∈ floor_off 的牙集合，且两集合不同",
             f"no_widen={sorted(nw_ids)} floor_off={sorted(fo_ids)}",
             "两个变异体咬同一把牙 ⇒ 无法区分是哪一处失效（= 判据不可诊断）",
             mutant_that_proves_it=("M2_near_constant_always_empty（**clause 级实测**：本 check 的必要子句 "
                                    "`Tr1 ∈ floor_off 红牙集合` 在 M2 产物上由 True 翻 False；M2 只跑 "
                                    "floor_off 臂 ⇒ 不套整条谓词，见 G24 台账 form=necessary_clause）"))

    # ---------- 4) 进程内输入级变异体（谓词代码在 `inprocess_probes()`，与变异体副本里
    #            跑的是**同一份**；见 `--probe-inprocess`） ----------
    inproc_root = inprocess_probes(run_dir / "arm_baseline")
    for _c in inproc_root["checks"]:
        gate.checks.append(_c)

    # ---------- 4b) 主线臂（`--s1-lerobot`）：裁定 85.4-2 的三项用途 + 85.4-3 的同源硬闸 ----------
    rev = mst = npz_rec = None
    rev_ok = mst_ok = npz_ok = False
    NA_MAINLINE = (("G27_mainline_rows_green_no_unexplained_red",
                    "主线通路验证档 8 行全绿、93.2 的两颗硬红在真数据上绿、全矩阵无不可解释的红"),
                   ("G28_bc_admission_arm_red_via_Tp5", "BC 准入必红臂 8 行全由 Tp5 咬红"),
                   ("G29_reader_evidence_reproduced_by_gate", "闸侧独立复算主线读取器的每一项证据"),
                   ("G31_mainline_status_fresh_and_executable", "mainline_status 与磁盘现状一致且为可执行态"),
                   ("G39_polarity_ruling_90_4_1_on_real_data", "裁定 90.4-1 的四把牙极性在真数据上成立"),
                   ("G40_reader_authority_ruling_90_4_4", "裁定 90.4-4 的权威/交叉核对分工成立"),
                   ("G41_trigger_caliber_split_ruling_90_4_3", "裁定 90.4-3 的触发判据逐口径×逐行落盘"),
                   ("G42_tooth_name_matches_semantics", "元闸：牙名承诺与实际判据相符（结构侧）"),
                   ("G57_no_shrink_registration_ruling_93_1_3",
                    "裁定 93.1-3 登记不许缩水 + 94.3 的盲点维可由逐维读数复算"),
                   ("G47_npz_authority_reproduced_by_gate", "闸侧独立复算 npz 权威臂的每一项证据"))
    if mx_main is None:
        for cid, nm in NA_MAINLINE:
            gate.add(cid, nm, False, "主线臂执行完并产出 matrix.json",
                     f"主线臂未执行（pilot 数据在位={pilot_present}）⇒ 不声称已验",
                     "未执行 ⇒ 不得声称主线档已验证", applies_when=False,
                     mutant_that_proves_it="n_a_not_executed（pilot 数据不在位）")
    else:
        rev = reader_evidence_recheck(mx_main, ROOT)
        mst = mainline_status_recheck(mx_main, ROOT)
        npz_rec = npz_authority_recheck(mx_main, ROOT)
        rev_ok, mst_ok = bool(rev.get("ok")), bool(mst.get("ok"))
        npz_ok = bool(npz_rec.get("ok"))
        mf = mx_main.get("mainline_finding") or {}
        gate.add("G27_mainline_rows_green_no_unexplained_red",
                 f"主线通路验证档：{MAINLINE_ROW_COUNT} 行**全绿**、93.2 的两颗硬红（`Tz`/`Tres`）"
                 f"在真实数据上绿、93.1 转 WARN 的两颗牙没有变回 RED、**全矩阵**无一处不可解释的红、"
                 f"牙集合 == {len(EXPECT_TEETH_MAINLINE)} 把且 Tp5 只在 BC 臂生效",
                 pred_G27(mx_main),
                 (f"n={MAINLINE_ROW_COUNT} 全 PASS 且每行 red_ids=[]；`Tz`/`Tres` 全 PASS；"
                  f"`Tb`/`Tr3` 无 RED；全矩阵每行 unexplained_red_teeth=[]；"
                  f"mainline_finding.all_red_explained=true 且 n_mainline_rows_red=0；"
                  f"牙集合==EXPECT_TEETH_MAINLINE；Tp5 生效行 == BC 臂行"),
                 (f"n_mainline_rows={mf.get('n_mainline_rows')} 红={mf.get('n_mainline_rows_red')} "
                  f"绿={mf.get('n_mainline_rows_pass')} "
                  f"all_red_explained={mf.get('all_red_explained')} "
                  f"unexplained(全矩阵)={sorted({i for i, r in rows_by(mx_main) if (r.get('unexplained_red_teeth') or [])})} "
                  f"F1行Tr3红={mf.get('tr3_red_on_f1_rows_must_be_empty')} "
                  f"warn_counts={mf.get('warn_tooth_counts')} pred={pred_G27(mx_main)}"),
                 ("主线行不绿 ⇒ 要么 93.1 的转 WARN 没落地/被撤回，要么 93.2 的硬红在真数据上咬到了"
                  "东西（**必须停手报 D**，不得改阈值放行）；出现无法解释的红 ⇒ allowed 清单被放宽成了"
                  "遮羞布；F1 行 Tr3 红 ⇒ 下限实质性判据在真数据上失效"),
                 kind="measured",
                 note=("⚠ **本 check 的极性在裁定 93.1 处翻了**，原名 "
                       "`G27_mainline_red_fully_explained`（判『8 行全红且红得可解释』）。93.1 把 `Tb`"
                       "（阈值状态 `registered_measurement_not_a_judgment`）与 F2 行的 `Tr3` 转成 WARN "
                       "⇒ 主线 8 行**应当全绿**；换上去的硬红是 `Tz`（除零族）与 `Tres`（逐维分辨率下限、"
                       "全量口径、D 定标）。改名 = 红线 `gate_name_must_match_gate_semantics`（名字不许"
                       "继续承诺一条不再判的约束）。**仍不判『主线档可以进 BC』**：BC 准入 = `Tbcad`"
                       "（AND 闸 verdict）+ A2 侧自己复算 `gate_verdict_sha256_12` 对账。"
                       "Tr3 按 family 分开的事实不变：F1 绿（实质性比 2.5/1.0）、F2 是 WARN"
                       "（实测 2.7e-4/1.4e-4，小约 4 个数量级 —— 判据未放宽，只改阻塞性）。"),
                 mutant_that_proves_it=("M13_allowed_red_set_shrunk（把 Tp5 从授权表摘掉 ⇒ BC 必红臂的"
                                        "真红变成无法解释的红 ⇒ 本谓词的**全矩阵**子句翻 False）"),
                 ruling_ref="裁定 85.4-3 / 93.1 / 93.2")
        _blind = mf.get("heldout_per_dim_blindness_ruling_94_3") or {}
        gate.add("G57_no_shrink_registration_ruling_93_1_3",
                 "**登记不许缩水**（裁定 93.1-3）：`Tb`/`Tr3` 转 WARN 之后，主线 8 行仍必须逐条落 "
                 "D 点名的 6 个逐维读数字段 + 94.3 的 2 个登记字段，且逐维数组长度 == `n_dims`；"
                 "**盲点维必须能由逐维读数复算**（不许硬编码）",
                 pred_G57(mx_main),
                 ("每行 `summary`/`summary_all` 的 `bins_occupied_per_dim`、`dims_below_min_bins`、"
                  "`dims_floor_binding`、`n_dims_floor_binding` + `near_constant` 的 "
                  "`materiality_ratio_min`、`floor_min_on_marked` 全在场；行级 "
                  "`bins_occupied_per_dim_resolution_caliber` / `heldout_bins_occupied_per_dim` / "
                  "`correctness_blind_dims` / `_status` 全在场；逐维数组长度 == n_dims；"
                  "闸侧用**同一份逐维数组 + 同一阈值**复算出的盲点维 == 登记的并集"),
                 (f"pred={pred_G57(mx_main)} 必落字段表="
                  + json.dumps(NO_SHRINK_REQUIRED_FIELDS, ensure_ascii=False, sort_keys=True)
                  + f" 行级={list(NO_SHRINK_ROW_FIELDS)}"
                  + f" blindness_status={_blind.get('measurement_status')}"
                  + f" n_dims={_blind.get('n_dims')}"
                  + f" distinct_patterns={_blind.get('n_distinct_heldout_patterns')}"
                  + f" heldout_per_dim={_blind.get('heldout_bins_occupied_per_dim_distinct')}"
                  + f" blind_union(登记)={_blind.get('correctness_blind_dims_union')}"
                  + f" threshold={_blind.get('blind_dim_threshold')}"),
                 ("转 WARN 之后顺手把逐维登记删掉 ⇒ 「登记不许缩水」变成文案；盲点维写死一个 "
                  "`[0,3,5,7,10,12]` ⇒ 换数据集/换切分后它会继续谎报（裁定 94.3 明令不许硬编码 6）"),
                 kind="measured",
                 note=("裁定 **95.1-1** 把 94.3 的那颗牙（`Theldout_per_dim_blindness_is_registered`）"
                       "与它的双向变异体**推迟到 S5 前**（Ⅱ 类登记不阻塞，BC 不等它）⇒ 本轮只落"
                       "**两个字段**，本 check 只判「字段在不在、逐维长度对不对、盲点维能不能复算」，"
                       "**不判**正确性族在盲点维上是否 `not_measured`（那是推迟的那颗牙的事）。"
                       "本轮实测：held-out 逐维占用 `[3,97,106,2,38,3,35,4,111,108,5,46,5,36]`"
                       "（与 D 的独立复算**逐位相同**）、盲点维并集 `[0,3,5,7,10,12]`、"
                       "两个 case 族的 dim10 分别是 4 / 5（都 < 8 ⇒ 并集稳定为 6 维）。"),
                 mutant_that_proves_it=("M39_bins_per_dim_truncated（把 `summarize()` 的逐维数组截掉"
                                        "最后一维 ⇒ 长度 != n_dims ⇒ 本谓词翻 False）"),
                 ruling_ref="裁定 93.1-3 / 94.3 / 95.1-1")
        bc = _arm_rows(mx_main, "s1_bc_admission_mustred")
        gate.add("G28_bc_admission_arm_red_via_Tp5",
                 f"BC 准入必红臂：{BC_ARM_ROW_COUNT} 行**全部**由 Tp5 咬红（裁定 85.4-3 点名的那条牙）",
                 pred_G28(mx_main),
                 (f"n={BC_ARM_ROW_COUNT} 全 RED，每行 {TP5} ∈ red_ids，"
                  f"且 stats_provenance={PILOT10_LABEL} / consumer=bc / admissible_for_bc=false"),
                 (f"n={len(bc)} 全红={all(r['verdict'] == 'RED' for _, r in bc)} "
                  f"Tp5命中行={sum(1 for _, r in bc if TP5 in red_ids(r))} "
                  f"pred={pred_G28(mx_main)}"),
                 ("喂 pilot10 的 stats 给 BC 配置而不红 ⇒ 同源硬闸恒真（= 没有闸），"
                  "BC 会拿 pilot 的 q01/q99 去归一化 formal 的训练数据 —— 正是 ACT 线那次事故的形态"),
                 kind="measured", mutant_that_proves_it="M10_bc_admission_gate_vacuous",
                 ruling_ref="裁定 85.4-3")
        gate.add("G29_reader_evidence_reproduced_by_gate",
                 f"主线读取器的每一项证据都能被**闸侧独立复算**并与生成器自报一致（{rev.get('n_clauses')} 条 clause）",
                 rev_ok,
                 "全部 clause recorded == recomputed，且期望值本身正确（不许『两边一起错』）",
                 (f"n_clauses={rev.get('n_clauses')} failed={rev.get('failed')} "
                  f"agreement_ok={rev.get('agreement_ok')} expected_values_ok={rev.get('expected_values_ok')} "
                  f"why={rev.get('why')}"),
                 ("生成器自报而闸不复算 ⇒ M12（分组键写反）/ M14（dtype 谎报）/ M15（假装切过 held-out）"
                  "都抓不到；这三者都会让 stats 静默偏掉而 q01/q99 看不出来"),
                 kind="measured",
                 note=("复算用**闸自己的代码**（pyarrow 直读 + 自己的 lexsort + 自己的按集划分），"
                       "与生成器无共享实现。逐位互核的**独立性限制**已写进产物："
                       "B2 的导出器也读同一份 parquet ⇒ 它证明的是帧序/分组一致，不是数据正确性；"
                       "数据正确性的证据在 B2 的 demo_manifest.gates（16/16）与 expert_selfverify（80/80），"
                       "C2 只引用不重证"),
                 mutant_that_proves_it=("M12_lerobot_grouping_broken / M14_dtype_misdeclared / "
                                        "M15_fake_heldout_split（各翻一条 clause，见翻转台账 form=necessary_clause）"),
                 ruling_ref="裁定 85.4-2")
        gate.add("G30_one_stats_file_per_row",
                 "**一行一文件**：没有两行 claim 同一个 stats 文件，且行内两处 sha 与 files[] 三方一致",
                 pred_G30(base) and (mx_main is None or pred_G30(mx_main)),
                 "基线臂与主线臂都满足：distinct(stats_file) == n_rows_with_stats_file，"
                 "且 stats_file_sha256_12 == roundtrip.sha256_12 == files[].sha256_12",
                 (f"基线 pred={pred_G30(base)}（n_rows={len([r for r in base.get('rows', []) if r.get('stats_file')])}）"
                  + (f"；主线 pred={pred_G30(mx_main)}"
                     f"（n_rows={len([r for r in mx_main.get('rows', []) if r.get('stats_file')])}）"
                     if mx_main is not None else "；主线臂未执行")),
                 ("两行共用一个文件 ⇒ 后写的覆写先写的，磁盘上只剩最后一份，"
                  "而行里的 roundtrip.sha256_12 指向**已不存在的文件状态**（缺陷类 ⑨ 引用过期）"),
                 kind="measured",
                 note=("**本轮实测到过的真缺陷**（不是假想）：修前 41 行只有 25 个不同 stats_file，"
                       "`env_derived_diagnostic__quantiles..._0.05.json` 被 3 行同时 claim，"
                       "三行 roundtrip sha 分别 dd88b3260f2d / 98a4da4e2b83 / dcd975b29a70，"
                       "磁盘实际 = dcd975b29a70（hold 相）。8 个名不符实的孤儿文件已移入 "
                       "`/workspace/mnt/sppro/yhzhang91/recycle_bin/c2_orphan_stats_20260930_021x/`"
                       "（附 WHY_RECYCLED.md），根因修在生成器（每臂独立文件名 + 每行落 sha）"),
                 mutant_that_proves_it="M16_arm_suffix_removed（抹掉臂标识 ⇒ 覆写复现）",
                 ruling_ref="裁定 68 / 35.1")
        gate.add("G31_mainline_status_fresh_and_executable",
                 "`mainline_status` 是可执行态且与磁盘现状一致（status / checked_path / 时刻 / 三处 sha / 标签 / BC 拒绝）",
                 mst_ok,
                 "8 条 clause 全 True（含 `checked_at >= parquet mtime`、`parquet_sha 与磁盘一致`）",
                 (f"failed={mst.get('failed')} recorded={json.dumps(mst.get('recorded'), ensure_ascii=False)[:300]} "
                  f"recomputed={json.dumps(mst.get('recomputed'), ensure_ascii=False, default=str)[:300]}"),
                 ("状态文件说『等数据』而数据已落地 ⇒ 关键路径被一份过期状态挡住（本轮真踩过："
                  "01:3x 写 waiting 时 npz 已落地 25 min；D 在裁定 85.4-2-5 点名要重生成）"),
                 kind="measured", mutant_that_proves_it="M18_checked_at_frozen（把 checked_at 写死成过去时刻）",
                 ruling_ref="裁定 85.4-2-5")
        gate.add("G39_polarity_ruling_90_4_1_on_real_data",
                 f"**真数据**上的裁定 90.4-1 极性：主线 {MAINLINE_ROW_COUNT} 行逐行核 —— 四把牙状态等于"
                 "期望表（`Tovr` 的期望**由数据决定**：有越界维⇒WARN、无⇒PASS）、blocking 极性正确、"
                 "已撤回的旧 id 不复活、且硬红的两把牙判据值**已测**（`window_escape=False`、"
                 "`headroom_consumption_max` 非空且 < 1.0、下侧不足维与逃逸维均空）",
                 pred_G39(mx_main),
                 (f"n={MAINLINE_ROW_COUNT} 行逐行符合 `IV_EXPECT_STATUS_MAINLINE`（Tovr 按数据取期望）；"
                  f"0 个已撤回 id；每行 measurement_status=measured"),
                 (f"pred={pred_G39(mx_main)} "
                  f"hcmax={[(r.get('declared_interval_conformance') or {}).get('headroom_consumption_max') for _, r in _arm_rows(mx_main, 's1_mainline_path_check')][:2]} "
                  f"dims_out={[(r.get('declared_interval_conformance') or {}).get('dims_out') for _, r in _arm_rows(mx_main, 's1_mainline_path_check')][:2]} "
                  f"withdrawn_present={sorted({t['id'] for _, r in rows_by(mx_main) for t in (r.get('teeth') or []) if t['id'] in WITHDRAWN_TOOTH_IDS})}"),
                 ("极性写反 = D 本轮第 15/16/17 号同型错误的形态，会造成硬阻塞或假绿；"
                  "`Tovr` 期望写死 WARN ⇒ 换一批没有越界的数据就假红（裁定 87.7 数值不可搬）"),
                 kind="measured",
                 mutant_that_proves_it=("M32_headroom_bins_halved（头寸减半 ⇒ 消耗比翻倍越过 1.0 ⇒ "
                                        "`Tesc` 在主线 8/8 行红 ⇒ 本 check 翻 False）"),
                 ruling_ref="裁定 90.4-1")
        gate.add("G40_reader_authority_ruling_90_4_4",
                 f"裁定 90.4-4 的**读取器分工**：权威 npz 臂 {MAINLINE_ROW_COUNT} 行标签必须是 "
                 f"`{FORMAL40_LABEL}` 且 `admissible_for_bc=true`；交叉核对臂 {CROSSCHECK_ROW_COUNT} 行与 "
                 f"BC 必红臂 {BC_ARM_ROW_COUNT} 行标签必须是 `{CROSSCHECK_LABEL}` 且 `admissible_for_bc=false`；"
                 "且交叉核对标签**结构上**不在 `BC_ADMISSIBLE_PROVENANCES` 里",
                 pred_G40(mx_main),
                 ("三臂标签与准入旗标逐个相符；`reader_authority_ruling_90_4_4` 三个自证旗标为 True；"
                  "`mainline_status.status == built_from_npz_authority_interface`"),
                 (f"pred={pred_G40(mx_main)} "
                  f"ml_labels={sorted({r.get('stats_provenance') for _, r in _arm_rows(mx_main, 's1_mainline_path_check')})} "
                  f"cc_labels={sorted({r.get('stats_provenance') for _, r in _arm_rows(mx_main, 's1_lerobot_crosscheck')})} "
                  f"bc_admissible_ml={sorted({(r.get('bc_admission') or {}).get('admissible_for_bc') for _, r in _arm_rows(mx_main, 's1_mainline_path_check')})} "
                  f"crosscheck_in_bc_admissible={CROSSCHECK_LABEL in nc.BC_ADMISSIBLE_PROVENANCES}"),
                 ("两个读取器产同一个 provenance 标签 ⇒ 无法回答『BC 到底吃了哪一份』（裁定 90.4-4 定性为"
                  "**权威性冲突**）；交叉核对档进了 BC 白名单 ⇒ 同源硬闸在结构上失效"),
                 kind="measured",
                 mutant_that_proves_it=("M26_crosscheck_arm_claims_bc_label（交叉核对臂冒充权威档标签）"),
                 ruling_ref="裁定 90.4-4 / 86.0")
        gate.add("G41_trigger_caliber_split_ruling_90_4_3",
                 "裁定 90.4-3 的触发判据必须**逐口径 × 逐行**落盘（held-out / build / all 三口径都在，"
                 "每口径 8 行逐维读数齐），且口径分叉时 `triggered` 必须是 `null` + "
                 "`governing_caliber=OPEN_question_to_d`（不得替 D 选口径）",
                 pred_G41(mx_main),
                 (f"三口径齐且均 measured；每口径 n_rows=={MAINLINE_ROW_COUNT} 且逐维列表等长；"
                  "分叉 ⇒ triggered=null；`condition_b_resolution` 同时在 mainline_finding 与 mainline_status 里"),
                 (f"pred={pred_G41(mx_main)} "
                  f"caliber_dependent={((mx_main.get('mainline_finding') or {}).get('condition_b_resolution') or {}).get('ruling_90_4_3_trigger', {}).get('caliber_dependent')} "
                  f"triggered={((mx_main.get('mainline_finding') or {}).get('condition_b_resolution') or {}).get('ruling_90_4_3_trigger', {}).get('triggered')} "
                  f"governing={((mx_main.get('mainline_finding') or {}).get('condition_b_resolution') or {}).get('ruling_90_4_3_trigger', {}).get('governing_caliber')}"),
                 ("单口径布尔值会把 held-out 子集读数当成全量结论 ⇒ 一个**假 P0 升级项**被 D 当成已触发的"
                  "裁定执行（修前生成器正是这样，而 D 在 90.2 #16 引的是全量口径）"),
                 kind="measured",
                 mutant_that_proves_it=("M24_caliber_summary_key_collapsed（三口径塌成一个）/ "
                                        "M25_caliber_per_row_truncated（逐行聚合只留首行）"),
                 ruling_ref="裁定 90.4-3 / 90.2 #16")
        # G42 的分臂子句（见下面 note 里的「判据分臂」）：基线臂的「规则 1 不适用」必须是**实测**的，
        # 不能只写一句"不适用"（否则就是把 N_A 当遮羞布）。
        a_main = name_semantics_audit(mx_main)
        a_base = name_semantics_audit(base)
        base_meas_rows = [(i, r) for i, r in rows_by(base)
                          if (r.get("declared_interval_conformance") or {}).get("measurement_status") == "measured"]
        base_meas_rows_n = len(base_meas_rows)
        base_meas_complete_all = all(
            (_recompute_measurement_complete(r["declared_interval_conformance"]) or {}).get("complete") is True
            for _, r in base_meas_rows)
        base_tiv = [(t.get("applies_when"), t.get("status"))
                    for _, r in rows_by(base) for t in (r.get("teeth") or [])
                    if t["id"] == "Tiv_out_of_declared_interval_is_measured"]
        base_tiv_n = len(base_tiv)
        base_tiv_all_na = bool(base_tiv) and all(a is False and st == "N_A" for a, st in base_tiv)
        gate.add("G42_tooth_name_matches_semantics",
                 "**元闸**（结构侧）：每把牙的名字承诺与实际判据相符 —— 名实审计在**基线臂与主线臂两份真产物**"
                 "上都 0 违规，且 schema 键集合与契约层逐字相等",
                 (pred_G42(mx_main) and bool(a_base["ok"]) and a_base["n_teeth_audited"] > 0
                  and base_tiv_all_na and base_meas_rows_n > 0 and base_meas_complete_all),
                 ("**主线臂**：7 条规则 + schema 键 parity 全过、`n_teeth_audited > 0`、"
                  "**且规则 1 有可重算子句**（`n_measurement_clauses_recomputed > 0`）。"
                  "**基线臂**：审计 ok + `n_teeth_audited > 0`；规则 1 的可重算子句在基线臂上"
                  "**不适用**，但该「不适用」必须是**实测**的三件事：① 有 `measurement_status=measured` "
                  "的行（测量块确实在）② 这些行的越界块经闸侧重算 `complete=True`（测量确实完整）"
                  "③ 基线臂每行的 `Tiv` 都 `applies_when=False` 且状态 `N_A`（牙确实是不适用，不是失声）"),
                 (f"mainline: pred={pred_G42(mx_main)} viol={a_main['n_violations']} "
                  f"teeth={a_main['n_teeth_audited']} meas_clauses={a_main['n_measurement_clauses_recomputed']} "
                  f"red_ids_rows={a_main['n_rows_with_red_ids_audited']} parity={a_main['schema_key_parity']}；"
                  f"baseline: audit_ok={a_base['ok']} viol={a_base['n_violations']} "
                  f"teeth={a_base['n_teeth_audited']} "
                  f"meas_clauses={a_base['n_measurement_clauses_recomputed']}（规则 1 在本臂不适用） "
                  f"red_ids_rows={a_base['n_rows_with_red_ids_audited']} "
                  f"downgrades_accepted={a_base['n_declared_downgrades_accepted']}；"
                  f"base_meas_rows={base_meas_rows_n} base_meas_complete_all={base_meas_complete_all} "
                  f"base_tiv_n={base_tiv_n} base_tiv_all_na={base_tiv_all_na}；"
                  f"violations_sample="
                  f"{json.dumps((a_main['violations'] + a_base['violations'])[:2], ensure_ascii=False)[:400]}"),
                 ("牙名承诺一条它其实没判的约束 ⇒ 读者按名字推理会得到错误结论（缺陷类 ⑮）；"
                  "本轮实测到的三种真形态：`*_is_measured` 恒真、`expected_red_teeth` 写不存在的 id、"
                  "`red_ids` 里出现**幻影标签**"),
                 kind="measured",
                 note=("构造矩阵也喂**同一份**审计（`polarity_rows_as_matrix`，见 G43）⇒ 审计代码没有第二份。"
                      "规则 7（幻影红标签）的非恒真性本轮已实测：注入一个 `裁定` token 到主线 8 行的 "
                      "`red_ids` ⇒ 8 条违规、`pred_G42` 翻 False。"
                      " ⚠ **判据分臂**（本轮实测到的**假红**，与 D 第 15/16 号同型错误同族 = 用一个臂的"
                      "性质去判另一个臂）：修前本 check 写的是 `pred_G42(mx_main) and pred_G42(base)`，"
                      "而 `pred_G42` 里含一条 `n_measurement_clauses_recomputed > 0`。基线三臂**全是诊断档行**"
                      "（`mainline=False`）⇒ `Tiv_…is_measured` 的 `applies_when=False`、状态 `N_A`"
                      "（裁定 72-2 审点①③：不适用的臂必须出 N_A 而不是红）⇒ 规则 1 在基线臂上"
                      "**没有可重算的对象**：实测 `n_measurement_clauses_recomputed=0`，而 `n_violations=0`、"
                      "`ok=True`。把它判红 = 闸自己造假红。修后该子句只在主线臂判，基线臂改判上面那三条"
                      "**实测**的「不适用」证据（测量块在、测量完整、牙确实是 N_A）。"),
                 mutant_that_proves_it=("M28_expected_red_teeth_absent_id（规则 6）/ "
                                        "M29_te2_downgraded_on_mainline（规则 3）/ "
                                        "M30_eval_scope_always_held_out（规则 4/4b）/ "
                                        "M33_phantom_red_tag_from_separator（规则 7）"),
                 ruling_ref="裁定 87.2-1 / 90.4-1 牙③ / 92.6")
        gate.add("G47_npz_authority_reproduced_by_gate",
                 f"**权威接口**（npz + `--s1-frames`）的每一项证据都被闸侧独立复算并与生成器自报一致"
                 f"（{npz_rec.get('n_clauses')} 条 clause：npz sha/字节/数组名、frames shape/dtype/content sha、"
                 "帧数集数、上转无损、held-out 划分、与行级帧数三方一致、交叉核对臂逐位相等旗标）",
                 npz_ok,
                 "全部 clause recorded == recomputed，且期望值本身自洽（不许『两边一起错』）",
                 (f"n_clauses={npz_rec.get('n_clauses')} failed={npz_rec.get('failed')} "
                  f"agreement_ok={npz_rec.get('agreement_ok')} "
                  f"expected_values_ok={npz_rec.get('expected_values_ok')} why={npz_rec.get('why')} "
                  f"recomputed_sha={(npz_rec.get('recomputed_full') or {}).get('npz_sha256_12')} "
                  f"content_sha={(npz_rec.get('recomputed_full') or {}).get('frames_content_sha256_12')} "
                  f"n_frames={(npz_rec.get('recomputed_full') or {}).get('n_frames')} "
                  f"n_episodes={(npz_rec.get('recomputed_full') or {}).get('n_episodes')}"),
                 ("权威臂没有闸自己的复算 ⇒ 『BC 吃的是哪一份数据』只有生成器自报；"
                  "集数/帧数谎报会让 held-out 划分静默偏移，而 q01/q99 看不出来"),
                 kind="measured",
                 note=("复算全部用闸自己的代码（`np.load` + 自己的 lexsort + 自己的 sha 定义），与生成器无共享"
                      "实现；content sha 的定义**照抄产物里写的那一句**（定义不同就会假红，定义本身也在产物里"
                      "登记 ⇒ 可核）。`parquet_frames_bitwise_equal_to_npz` 一维**不在本 check 判**，"
                      "由 G29 判（避免同一件事两处实现）。"),
                 mutant_that_proves_it="M31_npz_episode_count_misdeclared（权威臂谎报集数 ⇒ clause `n_episodes` 翻）",
                 ruling_ref="裁定 90.4-4 / 86.1")

    # ---------- 5) 文件级变异体 ----------
    mutant_evidence = []
    probe_runs: dict = {}
    proof_ledger: list = []

    def add_proof(check_id, mutant, form, baseline_val, mutant_val, evidence):
        """翻转台账：`flip_measured` 只在 **真仓 True 且变异体 False** 时为真（单向不算）。"""
        proof_ledger.append({"check_id": check_id, "mutant": mutant, "form": form,
                             "baseline_true": bool(baseline_val), "mutant_false": (not bool(mutant_val)),
                             "flip_measured": bool(baseline_val) and not bool(mutant_val),
                             "evidence": evidence})

    # ---------- 5a-pre) 变异体**锚点自检**（在跑任何变异体之前） ----------
    # WHY 单列一条 check：`build_mutant` 对锚点失配是**拒绝构造**（ok=False）而不是假绿 —— 这个设计是对的，
    # 但后果是"该变异体没跑"被记成 `why_not_run`，而**它要证明的那几条 check 会缺翻转台账**，读者得顺着
    # 台账倒推才知道根因是锚点漂移。本轮实测到 **3 起**（M1 / M5 / M13，全因实现改名或重构导致 count=0）：
    #   · M1 = 契约层把红信息分隔符抽成 `RED_MESSAGE_SEPARATOR`（我上一轮自己改的）⇒ 锚点里的
    #     `"；".join(red)` 失配；M1 一漂移，G16 / G25 / G26 与 6 条进程内探针一起失声。
    #   · M5 = `tooth()` 的 `rec` 字典缩进变了。
    #   · M13 = 生成器把手写常量 `_HELDOUT_FAMILY` 重构成测量派生的 `TOOTH_AUTHORIZED_BY_FACT`。
    # ⇒ 把根因变成一条**点名**的 check，而不是让它以"某条 check 缺台账"的形式间接出现。
    # 非恒真性用**枚举器自检**证（与 G20 同族）：另扫一个故意不存在的对照锚点，它必须在每个被扫文件里
    # 出现 0 次；若对照锚点也"匹配到 1 次"，说明计数机器坏了 ⇒ 本 check 自己红。
    ANCHOR_CONTROL_PROBE = "__c2_anchor_control_probe_that_must_not_exist__"
    anchor_scan = []
    for mid, anchors in sorted(MUTATIONS.items()):
        for rel, old, _new in anchors:
            fp = ROOT / rel
            txt = fp.read_text(encoding="utf-8") if fp.is_file() else None
            anchor_scan.append({"mutant": mid, "file": rel, "file_exists": txt is not None,
                                "count": (txt.count(old) if txt is not None else None),
                                "control_count": (txt.count(ANCHOR_CONTROL_PROBE)
                                                  if txt is not None else None)})
    anchor_bad = [a for a in anchor_scan if a["count"] != 1]
    anchor_control_ok = bool(anchor_scan) and all(a["control_count"] == 0 for a in anchor_scan)
    gate.add("G51_mutant_anchors_match_exactly_once",
             f"**每个变异体锚点在真仓文件里恰好出现 1 次**（{len(MUTATIONS)} 个变异体 / "
             f"{len(anchor_scan)} 个锚点），且对照锚点（故意不存在）在每个被扫文件里出现 **0** 次",
             (not anchor_bad) and anchor_control_ok,
             "count != 1 的锚点数 = 0（0 次 = 漂移，>1 次 = 锚点不唯一、变异体会改错地方）；"
             "对照锚点 count 全 0（枚举器自检）",
             (f"n_mutants={len(MUTATIONS)} n_anchors={len(anchor_scan)} "
              f"n_bad={len(anchor_bad)} bad={json.dumps(anchor_bad[:6], ensure_ascii=False)} "
              f"control_ok={anchor_control_ok} "
              f"control_counts={sorted({a['control_count'] for a in anchor_scan})} "
              f"files_scanned={sorted({a['file'] for a in anchor_scan})}"),
             ("锚点漂移 ⇒ 变异体**根本没被构造**，而它要证明的 check 会以『缺翻转台账』的形式红，"
              "根因被埋在台账里；锚点不唯一 ⇒ `replace(...,1)` 只改第一处，变异体语义与登记不符（假证）"),
             kind="measured",
             note=("本轮真实检出记录（= 本 check 的非恒真证据）：M1 / M5 / M13 三个锚点 count=0，"
                   "根因分别是分隔符抽常量、`tooth()` 缩进变化、allowed 清单由常量改为测量派生。"
                   "三处锚点已随实现更新，并在 `MUTATIONS` 各自的注释里写明改锚点的理由。"
                   "**纪律**：改契约层/生成器的任何一行之前，先 `grep` 一遍 `MUTATIONS` 里有没有锚点落在它上面"
                   "（本轮的三起全是 C2 自己改实现时没做这一步）。"),
             mutant_that_proves_it=("anchor_drift_observed_this_round（M1/M5/M13 三起真实检出，count=0，"
                                    "见 note）+ control_probe_enumerator_self_check"),
             ruling_ref="裁定 83.2 / 78.1")

    if not args.skip_file_mutants:
        plans = [("M1_non_raising", ["--emit-yam"], "baseline"),
                 ("M2_near_constant_always_empty", ["--emit-yam", "--floor-coef-scale", "0"], "floor_off"),
                 ("M3_payload_recompute_identity", ["--emit-yam"], "baseline"),
                 ("M5_schema_field_dropped", ["--emit-yam"], "baseline"),
                 ("M6_tr3_always_blocking", ["--emit-yam"], "baseline"),
                 ("M7_stats_source_gate_vacuous", ["--emit-yam"], "baseline"),
                 ("M8_heldout_teeth_vacuous", ["--emit-yam"], "baseline"),
                 ("M16_arm_suffix_removed", ["--emit-yam"], "baseline"),
                 ("M19_arm_prefix_mislabel", ["--emit-yam"], "baseline")]
        # ⚠ M28/M30 原本挂在 baseline 臂，**这是错的**（本轮实测）：它们咬的是名实审计
        #   （规则 6 / 规则 4），而承载该审计的 check `G42` 只登记在 `MATRIX_PREDS_MAINLINE` 里 ——
        #   基线臂的翻转台账用 `MATRIX_PREDS`（不含 G42）⇒ 这两个变异体**跑了也记不到翻转**，
        #   G42 会因"缺实测翻转台账"被 G24 判红。
        #   而且不能把 G42 加进 `MATRIX_PREDS` 了事：`pred_G42` 含一条
        #   `n_measurement_clauses_recomputed > 0`，而基线三臂全是诊断档行（`Tiv` 合法地 N_A）
        #   ⇒ `pred_G42(基线 matrix)` 在**真仓**就是 False，进不了"真仓 True ⇒ 变异体 False"的台账形式。
        #   正解 = 让这两个变异体走 mainline 臂：主线 matrix 是 **49 行的超集**
        #   （25 行基线三臂 + YAM，再加 8+8+8 主线三臂）⇒ stress 行的 `expected_red_teeth`（M28）
        #   与 env 诊断行的 `eval_scope`（M30）都照样出现在里面，`pred_G42` 能翻。
        if pilot_present:
            plans += [(m, ["--emit-yam", *MAINLINE_EXTRA], "mainline") for m in
                      ("M10_bc_admission_gate_vacuous", "M12_lerobot_grouping_broken",
                       "M13_allowed_red_set_shrunk", "M14_dtype_misdeclared",
                       "M15_fake_heldout_split", "M18_checked_at_frozen",
                       # ── 本轮新增（裁定 90.4-1 三颗牙 + 90.4-3/90.4-4 口径牙 + 名实审计规则 3/7）──
                       # M21/M32 = 牙② / 牙①；M24/M25 = 90.4-3 的口径分叉；M26 = 90.4-4 的读取器冒充；
                       # M29 = 审计规则 3（主线行硬约束不许降软）；M31 = 权威臂证据谎报；
                       # M33 = 审计规则 7（幻影红标签）。
                       # WHY 这几个必须是 mainline 臂：它们咬的对象只在主线行上存在
                       #   （M32 要 `Tesc` 在真数据上红、M33 要 **`Tp5`** 在真数据上红（锚点已随 93.1
                       #    从 `Tb` 重指：`Tb` 转 WARN 之后结构上进不了 `red`，见 M33 上方注释）、
                       #    M26/M31 要 npz 权威臂、
                       #    M24/M25 要三口径逐行读数、M29 要 `blocking=hard` 为真的行）。
                       "M21_coverage_target_ignored", "M24_caliber_summary_key_collapsed",
                       "M25_caliber_per_row_truncated", "M26_crosscheck_arm_claims_bc_label",
                       "M28_expected_red_teeth_absent_id", "M29_te2_downgraded_on_mainline",
                       "M30_eval_scope_always_held_out", "M31_npz_episode_count_misdeclared",
                       "M32_headroom_bins_halved", "M33_phantom_red_tag_from_separator",
                       # ── 本轮新增（裁定 93.1-3）：登记缩水的变异体。WHY mainline 臂：
                       #   G57 只在主线 8 行上判（诊断档行的 `summary_all` 合法地为 None）。
                       "M39_bins_per_dim_truncated")]
        for mid, extra, _kind in plans:
            built = build_mutant(run_dir, mid)
            rec = {"mutant_id": mid, "construction": built, "arm_kind": _kind,
                   "mutant_root": str(Path(built["dir"]) if built.get("ok") else run_dir),
                   "matrix": None}
            if not built["ok"]:
                rec["caught"] = False
                rec["why_not_run"] = built["why"]
                mutant_evidence.append(rec)
                continue
            mut = Path(built["dir"])
            od = mut / "out"
            idout = mut / "identity.json"
            rr = run_py(mut / BUILD, build_args(od, extra, root=mut), cwd=mut,
                        env_extra={"C2_MUTANT_IDENTITY_OUT": str(idout)})
            ident = read_identity(mut)
            mj = od / "matrix.json"
            mx = json.loads(mj.read_text(encoding="utf-8")) if mj.exists() else None
            rec["matrix"] = mx
            rec["run"] = rr
            rec["identity"] = ident
            rec["identity_self_proof_ok"] = bool(ident.get("present") and ident.get("nc_mutant_id") == mid
                                                 and ident.get("nc_file_inside_mutant_dir"))
            if mx:
                rec["matrix_verdict"] = mx.get("verdict")
                rec["red_teeth_counts"] = sorted({x.split(" ")[0] for r in mx["rows"] for x in (r.get("red") or [])})
                rec["roundtrip_mismatch_rows"] = [i for i, r in enumerate(mx["rows"])
                                                  if not (r.get("roundtrip") or {}).get("match")]
                rec["tr1_rows_in_floor_off"] = [i for i, r in enumerate(mx["rows"])
                                                if "Tr1_near_constant_has_floor" in red_ids(r)]
                rec["consistency_tooth_rows"] = [i for i, r in enumerate(mx["rows"])
                                                 if "Tconsistency_raise_matches_verdict" in red_ids(r)]
                rec["n_rows_pass"] = sum(1 for r in mx["rows"] if r["verdict"] == "PASS")
                _need = {"id", "ok", "status", "required", "observed", "red_when"}
                rec["teeth_missing_schema_fields"] = sorted(
                    {tt.get("id", "<no-id>") for r in mx["rows"] for tt in (r.get("teeth") or [])
                     if not _need <= set(tt)})
                rec["tr3_statuses_on_diagnostic_rows"] = sorted(
                    {tt["status"] for r in mx["rows"] if not r.get("is_must_red_branch")
                     for tt in (r.get("teeth") or []) if tt["id"] == "Tr3_near_constant_floor_material"})
                rec["has_Tr1_in_red"] = "Tr1_near_constant_has_floor" in {
                    x for r in mx["rows"] for x in red_ids(r)}
                # **用闸自己的谓词函数**套变异体产物 ⇒ "哪些 check 被这个变异体搞红"是实测出来的，
                # 不是文书里写的（裁定 83.2）。只有与基线**同臂**（arm_kind=="baseline"）才逐条可比。
                _pd = MATRIX_PREDS if _kind == "baseline" else MATRIX_PREDS_MAINLINE
                rec["matrix_predicates"] = {cid: bool(fn(mx)) for cid, fn in _pd.items()}
            mutant_evidence.append(rec)

        # M4：采集器映射改回内联公式 ⇒ 勘误件的 Tp1 必须红
        mid = "M4_collector_inline_qpos_formula"
        built = build_mutant(run_dir, mid)
        rec = {"mutant_id": mid, "construction": built}
        if built["ok"]:
            mut = Path(built["dir"])
            od = mut / "out_pr"
            od.mkdir(parents=True, exist_ok=True)
            # 经变异体根的相对 glob（它自己有 runs 符号链接）⇒ 产物里登记的路径也在 ROOT 之内
            rr = run_py(mut / FIXPR, ["--out-dir", str(od),
                                      "--env-states-glob", "runs/vla/c2_norm_contract_20260929/"
                                                           "env_states_*/env_states.npz"],
                        cwd=mut)
            cj = od / "correction.json"
            cd = json.loads(cj.read_text(encoding="utf-8")) if cj.exists() else None
            rec["run"] = rr
            if cd:
                rec["correction_verdict"] = cd.get("verdict")
                rec["teeth"] = [(t["id"], t["status"]) for t in cd.get("teeth", [])]
                rec["collector_sha_in_artifact"] = next(
                    (c.get("sha256_12") for c in cd.get("citations", [])
                     if c.get("path") == "scripts/c2_collect_env_states.py"), None)
                rec["identity_self_proof_ok"] = (rec["collector_sha_in_artifact"] == built.get("collector_sha256_12"))
        mutant_evidence.append(rec)

        by_id = {m["mutant_id"]: m for m in mutant_evidence}
        m1 = by_id.get("M1_non_raising", {})
        # 判据设计事实（本轮实测）：matrix 的**顶层 verdict 是极性归一化的**（"该红的行红了"就 PASS），
        # 所以它**不能**当"变异体是否被抓"的判据。M1 的可检测痕迹 = 一致性牙
        # `Tconsistency_raise_matches_verdict` 出现在**本该红的那几行**（8 stress + 1 YAM 必红）。
        expect_rows = sorted([i for i, _ in stress] + [i for i, _ in mustred])
        got_rows = sorted(m1.get("consistency_tooth_rows") or [])
        gate.add("G16_M1_non_raising_caught",
                 "M1（去掉 raise）⇒ 一致性牙必须在**本该红的每一行**留下痕迹（不许静默变绿）",
                 bool(m1.get("identity_self_proof_ok")) and got_rows == expect_rows,
                 f"identity 自证成立 且 Tconsistency 命中行集合 == 本该红的行集合 {expect_rows}",
                 (f"identity_ok={m1.get('identity_self_proof_ok')} 命中={got_rows} "
                  f"matrix_verdict={m1.get('matrix_verdict')}（顶层 verdict 极性归一化，不作判据） "
                  f"n_rows_pass={m1.get('n_rows_pass')}"),
                 "去掉 raise 而一致性牙不响 ⇒ **假绿**（假红会被人发现，假绿不会）",
                 mutant_that_proves_it="M1_non_raising", ruling_ref="裁定 78.1 / 27.1",
                 note=("M1 之下顶层 verdict 仍是 PASS：不是闸漏了，而是 `eval_verdict` 的一致性牙把"
                       "「算出红但没抛」重新判成红 ⇒ 行级极性恢复。**教训：判变异体是否被抓要看牙的痕迹，"
                       "不能看顶层聚合值**（同裁定 72-2 审点③：聚合器会掩盖细节）"))
        m2 = by_id.get("M2_near_constant_always_empty", {})
        gate.add("G17_M2_near_constant_empty_caught", "M2（近常量恒空）⇒ floor_off 臂的 Tr1 必须**失声**（被 G8 抓）",
                 bool(m2.get("identity_self_proof_ok")) and m2.get("matrix_verdict") is not None
                 and not m2.get("tr1_rows_in_floor_off"),
                 "identity 自证成立 且 变异体跑出的 floor_off 臂里 Tr1 一行都不红（= 牙失声 = G8 会红）",
                 (f"identity_ok={m2.get('identity_self_proof_ok')} verdict={m2.get('matrix_verdict')} "
                  f"tr1_rows={m2.get('tr1_rows_in_floor_off')}"),
                 "Tr1 在变异体下仍红 ⇒ 说明 G8 判的不是 Tr1（判据错位）",
                 mutant_that_proves_it="M2_near_constant_always_empty")
        m3 = by_id.get("M3_payload_recompute_identity", {})
        gate.add("G18_M3_payload_divergence_caught", "M3（落盘重算 center/gain）⇒ round-trip 必须失配并被记红",
                 bool(m3.get("identity_self_proof_ok")) and m3.get("matrix_verdict") == "RED"
                 and bool(m3.get("roundtrip_mismatch_rows")),
                 "identity 自证成立 且 mutant matrix verdict=RED 且 有 round-trip 失配行",
                 (f"identity_ok={m3.get('identity_self_proof_ok')} verdict={m3.get('matrix_verdict')} "
                  f"mismatch_rows={(m3.get('roundtrip_mismatch_rows') or [])[:6]}"),
                 "落盘与判定分叉而闸不红 ⇒ 交付物可以和被验的东西不是同一份（附录 02:274）",
                 mutant_that_proves_it="M3_payload_recompute_identity")
        m4 = by_id.get("M4_collector_inline_qpos_formula", {})
        gate.add("G19_M4_collector_regression_caught", "M4（采集器改回内联 qpos 公式）⇒ 勘误件 **Tp1 必须红**",
                 m4.get("correction_verdict") == "RED"
                 and any(t[0] == "Tp1_declared_mapping_equals_implemented" and t[1] == "RED"
                         for t in (m4.get("teeth") or []))
                 and bool(m4.get("identity_self_proof_ok")),
                 "correction verdict=RED 且 Tp1=RED，且产物里引用的采集器 sha == 变异副本 sha",
                 (f"verdict={m4.get('correction_verdict')} teeth={m4.get('teeth')} "
                  f"sha_self_proof={m4.get('identity_self_proof_ok')}"),
                 "映射退回缺陷形态而勘误件不红 ⇒ 右臂 F1 分母会再错 175×（dim12）",
                 mutant_that_proves_it="M4_collector_inline_qpos_formula")
        m5 = by_id.get("M5_schema_field_dropped", {})
        gate.add("G22_M5_schema_drop_caught", "M5（删掉牙的 `red_when` 字段）⇒ G6 的 schema 判据必须能看见",
                 bool(m5.get("identity_self_proof_ok")) and bool(m5.get("teeth_missing_schema_fields")),
                 "identity 自证成立 且 变异体产物里存在缺字段的牙（= G6 在真基线上会红的同一判据）",
                 (f"identity_ok={m5.get('identity_self_proof_ok')} "
                  f"缺字段牙={(m5.get('teeth_missing_schema_fields') or [])[:4]}"),
                 "删字段而 G6 看不见 ⇒ schema 判据恒真（汇总器静默少读一列，裁定 78.2 失效）",
                 mutant_that_proves_it="M5_schema_field_dropped", ruling_ref="裁定 78.2")
        m6 = by_id.get("M6_tr3_always_blocking", {})
        gate.add("G23_M6_tr3_false_red_caught", "M6（Tr3 在不适用的臂上也 blocking）⇒ 诊断臂必须不再出 N_A",
                 bool(m6.get("identity_self_proof_ok"))
                 and bool(m6.get("tr3_statuses_on_diagnostic_rows"))
                 and "N_A" not in (m6.get("tr3_statuses_on_diagnostic_rows") or []),
                 "identity 自证成立 且 变异体下诊断臂 Tr3 状态集合不含 N_A（= G6 的 applies_when 判据会红）",
                 (f"identity_ok={m6.get('identity_self_proof_ok')} "
                  f"诊断臂 Tr3 状态={m6.get('tr3_statuses_on_diagnostic_rows')}"),
                 "不适用的臂上不出红 ⇒ `applies_when` 只是装饰（裁定 72-2 审点①③ 失效）",
                 mutant_that_proves_it="M6_tr3_always_blocking", ruling_ref="裁定 72-2")

        # ---- 5b) 在 M1 / M3 副本内**重跑同一份进程内谓词**（裁定 83.2：G10–G15 非恒真的实测证据） ----
        # 做法：把本闸文件**逐字节复制**进变异体目录再跑 `--probe-inprocess`。副本的 ROOT = 变异体目录
        # ⇒ `from harness import norm_contract` 必然 import 到变异副本；探针把**活对象**的
        # `nc.__file__` / `nc.__c2_mutant_id__` / sha 写回产物 ⇒ 不是"读文件比对"式的自证。
        grel = Path(__file__).resolve().relative_to(ROOT)
        # ⚠⚠ 裁定 **97.2 红一**的**根因修法**（不是"把 M6 补进第二份清单"了事）：本循环的目标清单
        #   **从 `INPROC_FLIP_PLAN` 派生**，不再手写第二份。
        # 根因（D 认定为"三字段全 null = 未实测"，具体成因由 C2 定并写进产物）：12:5x 那轮
        #   （`run_20260930_125352`）G25/G24 双红，是因为裁定 93.1-1 之后 `G14` 的翻转分工从 M1
        #   改挂 **M6**（M1「算出红也不抛」翻不动一条已经不再产红的牙），`INPROC_FLIP_PLAN` 改了、
        #   而这里那份**手写清单没加 M6** ⇒ M6 的探针根本没跑 ⇒ 台账里 `identity_ok` /
        #   `nc_mutant_id` / `in_mutant_copy` 三个身份字段全 `null`（不是 False，是"没测"）
        #   ⇒ G25 判红、G24 因"G14 无翻转台账"连带判红。
        # 为什么必须派生而不是补一行：只要还存在第二份清单，同一个失效就会在**下一个**新变异体上
        #   重演（缺陷类 ⑲ 同族：判据的识别面比对象空间窄）。派生之后**登记即被探针覆盖**，
        #   两份清单无从漂移。
        # 例外只有两处，且**差的只是 bdir**（它们的变异体目录由文件级 plans 产出，不在基线臂下）：
        probe_bdir_override = {
            "M19_arm_prefix_mislabel": run_dir / "mutants" / "M19_arm_prefix_mislabel" / "out",
            "M3_payload_recompute_identity":
                run_dir / "mutants" / "M3_payload_recompute_identity" / "out"}
        # `M3_payload_recompute_identity` 不在 `INPROC_FLIP_PLAN` 里（它的翻转面是 G26 的落盘复算，
        #   走 `INPROC_M3_IDS`）⇒ 显式追加，且**只此一项**追加（就写在下面这一行，不再散落到别处）。
        probe_targets = [(mid, probe_bdir_override.get(mid, run_dir / "arm_baseline"))
                         for mid in (*INPROC_FLIP_PLAN, "M3_payload_recompute_identity")]
        # bdir 的口径（原手写清单里的注释，保留不丢）：极性构造族（G43/G44/G45/G49/G50）、名实审计
        #   （G46）与裁定 93.2/93.4 四颗新牙的变异体（M34–M37）都用**真仓基线臂**，因为这些 check
        #   判的是构造/源码、不读主线 stats ⇒ 它们**不进 plans**（不必各跑一次完整生成器）；
        #   M21 例外：它在 plans 里（G39/G48 要它的真数据 matrix），但探针仍读基线臂。
        for pmid, bdir in probe_targets:
            pmut = run_dir / "mutants" / pmid
            gcopy, pout = pmut / grel, pmut / "inprocess_probe.json"
            rp = {"mutant_id": pmid, "base_dir": str(bdir), "probe_out": str(pout)}
            if not (pmut / "harness" / "norm_contract.py").exists():
                b_extra = build_mutant(run_dir, pmid)      # M9 不在 plans 里（不跑 builder，只跑探针）
                rp["construction"] = b_extra
            if not (pmut / "harness" / "norm_contract.py").exists() or not (bdir / "stats").is_dir():
                rp.update({"ok": False, "why": "变异体副本或 stats 输入目录缺失 ⇒ 拒绝声称已证"})
                probe_runs[pmid] = rp
                continue
            shutil.copy2(Path(__file__).resolve(), gcopy)
            rr = run_py(gcopy, ["--probe-inprocess", str(pout), "--probe-run-dir", str(bdir)], cwd=pmut)
            pj = json.loads(pout.read_text(encoding="utf-8")) if pout.exists() else None
            ident = (pj or {}).get("identity") or {}
            inside = str(Path(ident.get("nc_file") or "").resolve()).startswith(str(pmut.resolve()))
            rp.update({"ok": bool(pj), "run": rr, "predicates": (pj or {}).get("predicates") or {},
                       "identity": ident,
                       "identity_self_proof_ok": bool(ident.get("nc_mutant_id") == pmid and inside),
                       "gate_copy_sha256_12": (sha12(gcopy) if gcopy.exists() else None),
                       "gate_copy_identical_to_real": (sha12(gcopy) == sha12(Path(__file__).resolve())
                                                       if gcopy.exists() else False)})
            probe_runs[pmid] = rp

        # ---- 5c) 翻转台账：把"哪个变异体让哪条 check 红"变成**实测记录**（不是登记文案） ----
        base_preds = {cid: bool(fn(base)) for cid, fn in MATRIX_PREDS.items()}
        base_preds_ml = ({cid: bool(fn(mx_main)) for cid, fn in MATRIX_PREDS_MAINLINE.items()}
                         if mx_main else {})
        for m in mutant_evidence:
            mp = m.get("matrix_predicates")
            kind = m.get("arm_kind")
            if not mp or kind not in ("baseline", "mainline"):
                continue      # M2 只跑 floor_off 臂 ⇒ 不与基线逐条比（按 clause 另记，见下）
            bp = base_preds if kind == "baseline" else base_preds_ml
            for cid, val in mp.items():
                if bp.get(cid) and not val:
                    add_proof(cid, m["mutant_id"], "matrix_predicate", True, False,
                              f"同一个 `pred_{cid.split('_')[0]}` 函数：真仓 {kind} 臂 matrix=True，"
                              f"{m['mutant_id']} 的 matrix=False")
        # G29 / G31 的判据是"闸侧独立复算 vs 生成器自报"的**逐条 clause**；
        # 变异体只改其中一条 ⇒ 按 `necessary_clause` 记翻转（与 G9/M2 同一形式）。
        for m in mutant_evidence:
            if m.get("arm_kind") != "mainline" or not m.get("matrix"):
                continue
            mid = m["mutant_id"]
            if mid in ("M12_lerobot_grouping_broken", "M14_dtype_misdeclared", "M15_fake_heldout_split"):
                mr = reader_evidence_recheck(m["matrix"], Path(m["mutant_root"]))
                for cl in (mr.get("failed") or []):
                    if rev_ok and cl in (rev.get("clauses") or {}):
                        add_proof("G29_reader_evidence_reproduced_by_gate", mid, "necessary_clause",
                                  True, False,
                                  f"clause `{cl}`：真仓 recorded==recomputed（True），{mid} 产物上 "
                                  f"recorded={mr.get('recorded', {}).get(cl)!r} != "
                                  f"recomputed={mr.get('recomputed', {}).get(cl)!r}")
                        break
            if mid == "M31_npz_episode_count_misdeclared":
                nr = npz_authority_recheck(m["matrix"], Path(m["mutant_root"]))
                for cl in (nr.get("failed") or []):
                    if npz_ok and cl in (npz_rec.get("clauses") or {}):
                        add_proof("G47_npz_authority_reproduced_by_gate", mid, "necessary_clause",
                                  True, False,
                                  f"clause `{cl}`：真仓 recorded==recomputed（True），{mid} 产物上 "
                                  f"recorded={nr.get('recorded', {}).get(cl)!r} != "
                                  f"recomputed={nr.get('recomputed', {}).get(cl)!r}")
                        break
            if mid == "M18_checked_at_frozen":
                mm = mainline_status_recheck(m["matrix"], Path(m["mutant_root"]))
                for cl in (mm.get("failed") or []):
                    if mst_ok and cl in (mst.get("clauses") or {}):
                        add_proof("G31_mainline_status_fresh_and_executable", mid, "necessary_clause",
                                  True, False,
                                  f"clause `{cl}`：真仓=True，{mid} 产物上=False"
                                  f"（recorded={mm.get('recorded', {}).get(cl)!r}）")
                        break
        m2fo = by_id.get("M2_near_constant_always_empty", {})
        if ("Tr1_near_constant_has_floor" in fo_ids) and not m2fo.get("has_Tr1_in_red", True):
            add_proof("G9_two_mutations_distinguishable", "M2_near_constant_always_empty",
                      "necessary_clause", True, False,
                      "G9 的必要子句 `Tr1 ∈ floor_off 红牙集合`：真仓 floor_off 臂=True，M2 产物=False")
        for pmid, ids in ([*INPROC_FLIP_PLAN.items(),
                           ("M3_payload_recompute_identity", INPROC_M3_IDS)]):
            pr = probe_runs.get(pmid) or {}
            mpred = pr.get("predicates") or {}
            for cid in ids:
                if (pr.get("identity_self_proof_ok") and inproc_root["predicates"].get(cid) is True
                        and mpred.get(cid) is False):
                    add_proof(cid, pmid, "inprocess_predicate_in_mutant_copy", True, False,
                              f"`inprocess_probes()` 同一份代码：真仓={inproc_root['predicates'].get(cid)}，"
                              f"{pmid} 副本内={mpred.get(cid)}（探针 identity 自证 ok）")

        flip_tbl, flip_ok = {}, True
        for pmid, ids in INPROC_FLIP_PLAN.items():
            pr = probe_runs.get(pmid) or {}
            mpred = pr.get("predicates") or {}
            per_ok = (bool(pr.get("ok")) and bool(pr.get("identity_self_proof_ok"))
                      and bool(pr.get("gate_copy_identical_to_real"))
                      and all(inproc_root["predicates"].get(i) is True for i in ids)
                      and all(mpred.get(i) is False for i in ids))
            flip_ok = flip_ok and per_ok
            flip_tbl[pmid] = {"expected_flip": ids, "ok": per_ok,
                              "identity_ok": pr.get("identity_self_proof_ok"),
                              "nc_mutant_id": (pr.get("identity") or {}).get("nc_mutant_id"),
                              "baseline": {i: inproc_root["predicates"].get(i) for i in ids},
                              "in_mutant_copy": {i: mpred.get(i) for i in ids}}
        gate.add("G25_inprocess_teeth_mutant_proven",
                 f"`INPROC_FLIP_PLAN` 登记的**每一条** check（本轮 {len(INPROC_M1_IDS) + len(INPROC_FLIP_PLAN)} 项分工）"
                 "都在其登记的变异体副本内、用**同一份谓词代码**重跑后由 True 翻 False",
                 flip_ok,
                 ("M1 翻 G12/G13；**M6** 翻 G14（裁定 93.1-1 之后 Tr3 在主线臂不再产红 ⇒ M1「算出红也不抛」"
                  "翻不动它，分工改挂 M6 —— 12:5x 那轮漏挂正是本 check 判红的原因，见 note）；"
                  "**M9** 翻 G10/G11（`Ts` 走 norm_contract.py:424-430 的独立提前抛，"
                  "M1 翻不动它 —— 00:5x 实测）；每个副本都要 identity 自证 + 闸副本与真闸同 sha"),
                 json.dumps(flip_tbl, ensure_ascii=False, sort_keys=True),
                 "翻不动 ⇒ 这几条 check 恒真（裁定 83.2：只写 `red_when` 文案不算有牙）",
                 kind="measured",
                 note=("分工是**实测出来的**：00:5x 那一跑（run_20260930_010545）M1 下 G10/G11 仍为 True，"
                       "⇒ 原登记「M1 证明 G10/G11」是**声明值、不成立**，已改判为 M9 并新增该变异体。"
                       "这条正是「登记文案 ≠ 有牙」的现场例子。"
                       "｜**裁定 97.2 红一的根因（D 令 C2 定并写进产物）**：12:5x 那轮"
                       "（`run_20260930_125352`）本 check 判红，唯一 `ok=false` 的是 "
                       "`M6_tr3_always_blocking`，其 `identity_ok` / `nc_mutant_id` / `in_mutant_copy` "
                       "**三个身份字段全 null**。根因**不是**锚点缺失（同轮 `G51` PASS）、**也不是**"
                       "元牙与新码不同步（`G14` 已随 93.1 的极性改判更名并绿），而是："
                       "`INPROC_FLIP_PLAN` 把 `G14` 的分工从 M1 改挂 M6 之后，**探针副本循环那份"
                       "手写清单没有同步加 M6** ⇒ M6 的探针**根本没跑**（三个候选根因里 D 登记为 "
                       "`not_measured` 的那一项 = 「该变异体未进入本轮 `mutants/` 的调用清单」）。"
                       "**修法 = 根因修**：探针目标清单已改为**从 `INPROC_FLIP_PLAN` 派生**"
                       "（单写者，见该循环上方注释），并已静态核对派生结果与原手写清单**集合相等**"
                       "（16 项、无重复）⇒ 同类漂移在结构上不再可能。"
                       "**实测验证**：`run_20260930_125721` 里 M6 的三字段已非 null"
                       "（`identity_ok=true`、`nc_mutant_id=M6_tr3_always_blocking`、"
                       "`in_mutant_copy.G14=false`）、`G14` 的台账 `flip_measured=true`、"
                       "本 check 与 `G24` 双双转 PASS（**判据一字未改**，照裁定 97.2 的明令："
                       "修前向、不修判据）。"),
                 mutant_that_proves_it="元判据：本 check 的判据**就是**各变异体造成的翻转记录（绿 = 已实测到翻转）",
                 ruling_ref="裁定 83.2 / 97.2-红一")
        m3p = probe_runs.get("M3_payload_recompute_identity") or {}
        b3 = {i: inproc_root["predicates"].get(i) for i in INPROC_M3_IDS}
        m3t = {i: (m3p.get("predicates") or {}).get(i) for i in INPROC_M3_IDS}
        gate.add("G26_payload_teeth_mutant_proven",
                 "G15（落盘 center/gain 必须覆盖起态）**在 M3 副本内用同一份谓词重跑**后由 True 翻 False",
                 bool(m3p.get("ok")) and bool(m3p.get("identity_self_proof_ok"))
                 and bool(m3p.get("gate_copy_identical_to_real"))
                 and all(b3[i] is True for i in INPROC_M3_IDS)
                 and all(m3t[i] is False for i in INPROC_M3_IDS),
                 "真仓=True；M3 副本（读 M3 自己落盘的 IDENTITY stats）=False；identity 自证 ok",
                 f"identity_ok={m3p.get('identity_self_proof_ok')} "
                 f"nc_mutant_id={(m3p.get('identity') or {}).get('nc_mutant_id')} 真仓={b3} M3={m3t}",
                 "翻不动 ⇒ G15 恒真 ⇒ 「落盘 = 被判」这条纪律没有牙（M3 正是本轮实测到过的缺陷形态）",
                 mutant_that_proves_it="元判据：本 check 的判据**就是** M3 造成的翻转记录（绿 = 已实测到翻转）",
                 ruling_ref="裁定 83.2")

        # ---- 5d) 裁定 90.4-1 的**三颗双向牙**逐颗有实测翻转（裁定 85.5 口径：missed/extra/all_caught） ----
        # 判据计算已抽成模块级 `ruling_90_4_1_teeth_ledger()`（WHY 见该函数上方注释：内联版本的一个
        # KeyError 在 24 个变异体全跑完之后才炸，而冒烟跑走 N_A 分支碰不到它）。
        led = ruling_90_4_1_teeth_ledger(proof_ledger, by_id, probe_runs)
        gate.add("G48_ruling_90_4_1_three_teeth_ledger",
                 "**裁定 90.4-1 的三颗双向牙逐颗有实测翻转**，并按裁定 85.5 口径报 "
                 "`missed / extra / all_caught`（牙① M32→G39 在真数据；牙② M21→G50 在构造；"
                 "牙③ M23→G43+G49 在构造）",
                 led["ok"],
                 ("missed == []（每颗牙登记的 check 全部有 `flip_measured=True` 台账，"
                  "且咬合证据在其声明的面上可见）"),
                 led["observed"],
                 ("任一颗牙没有实测翻转 ⇒ 它是文案而不是牙（裁定 83.2）；三颗牙的**分工**若只写在一句话里，"
                  "读者无法核哪颗牙在哪个面上被看见 ⇒ 这正是 D 要 missed/extra/all_caught 的原因"),
                 kind="measured",
                 note=("两条**不由本 check 判但必须随产物落盘**的披露：① 牙② 在真数据上咬的是 "
                       f"`{TCOV_ID}` 而不是 `{T2_ID}`（held-out 帧恰好都在 build 范围内），字面形态由 G50 "
                       "的构造承担 ⇒ 见 `tooth2_divergence`，已升级给 D；② M32 的卫语句首次触发是"
                       "**历史**实测（`guard_fired_first_attempt`，`counts_toward_ok=False`）。"),
                 mutant_that_proves_it="元判据：本 check 的判据**就是**三颗牙的翻转台账（绿 = 三颗都已实测到翻转）",
                 ruling_ref="裁定 90.4-1 / 85.5")
        # 随产物落盘（不进 `ok`，但必须可核）
        gate.checks[-1]["ledger_90_4_1"] = led["ledger"]
        gate.checks[-1]["tooth2_divergence"] = led["tooth2_divergence"]
        gate.checks[-1]["guard_fired_first_attempt"] = led["guard_fired_first_attempt"]
    else:
        # ⚠ 本清单**只列由文件级变异体产出的 check**。G29/G31 曾在列（首版），
        #   但它们在 §4b 的主线臂分支里**无条件产出**（有主线臂 ⇒ 真判；无 ⇒ 走 NA_MAINLINE）
        #   ⇒ 冒烟跑里同一个 id 出现两条记录（一条 PASS/N_A、一条"未执行"N_A）。
        #   这是**重复条目缺陷**，不是极性缺陷，但会让 `n_checks` 与"每条 check 一条记录"的
        #   口径失配（G24 的"check 数"分母被污染）⇒ 已移除（02:43 全量跑后修）。
        for cid in ("G16_M1_non_raising_caught", "G17_M2_near_constant_empty_caught",
                    "G18_M3_payload_divergence_caught", "G19_M4_collector_regression_caught",
                    "G22_M5_schema_drop_caught", "G23_M6_tr3_false_red_caught",
                    "G25_inprocess_teeth_mutant_proven", "G26_payload_teeth_mutant_proven",
                    "G48_ruling_90_4_1_three_teeth_ledger"):
            gate.add(cid, "文件级变异体", False, "跑文件级变异体", "--skip-file-mutants ⇒ 未执行",
                     "未执行 ⇒ 不得声称牙有自证", applies_when=False,
                     mutant_that_proves_it="n_a_not_executed（--skip-file-mutants）")

    # ---------- 6) 写入面自查（不许写别人的目录） ----------
    cutoff = t_start
    touched = []
    for p in NORM_DIR.rglob("*"):
        if p.is_file() and not str(p).startswith(str(run_dir)):
            try:
                if p.stat().st_mtime >= cutoff:
                    touched.append(str(p.relative_to(ROOT)))
            except OSError:
                pass
    enumerated = [p for p in NORM_DIR.rglob("*") if p.is_file() and not str(p).startswith(str(run_dir))]
    enumerator_sees_known = (NORM_DIR / "matrix.json") in enumerated
    # 裁定 **97.2 红二**：既声明例外（Ⅲ 类记账，不得阻塞 BC）。命中情况**必须**写进 observed，
    #   不许静默吞掉；未声明的写入照样红。
    touched_declared = [t for t in touched if t in G20_DECLARED_WRITE_EXCEPTIONS]
    touched_undeclared = [t for t in touched if t not in G20_DECLARED_WRITE_EXCEPTIONS]
    gate.add("G20_write_scope", "本闸只写自己的 run 目录（`c2_norm_contract_20260929/` 下其它文件零改动）",
             (not touched_undeclared) and enumerator_sees_known and len(enumerated) > 0,
             "开闸后 run 目录外 0 个**未声明例外**的文件被写；**且枚举器自检看得到已知文件**"
             "（否则枚举为空 = 恒真）",
             (f"run 目录外被写文件数={len(touched)}（未声明={len(touched_undeclared)} "
              f"例={touched_undeclared[:6]}；已声明例外命中={len(touched_declared)} "
              f"例={touched_declared[:3]}）；枚举器自检："
              f"run 目录外枚举到 {len(enumerated)} 个文件、看到 matrix.json={enumerator_sees_known}"),
             "写了别处 ⇒ 覆写事故（裁定 68/79 的形态）；枚举为空 ⇒ 本 check 恒真", kind="measured",
             note=("枚举方式：`NORM_DIR.rglob('*')` **全枚举** + mtime ≥ 开闸时刻（不是抽样）。"
                   "**行为型变异体（故意往 run 目录外写文件）C2 主动不造**：它会污染共享 `runs/`，"
                   "与本 check 要守的纪律自相矛盾 ⇒ 改以枚举器自检证明非恒真，并把这条取舍显式登记，"
                   "不装成已证（`tooth_must_be_mutant_proven` 的例外必须点名）。"
                   "｜**既声明例外清单（裁定 97.2 红二，D 的处置原文 = 登记路径 + 裁定号 + `as_of`，"
                   "且不得移动或删除该文件）**："
                   + json.dumps(G20_DECLARED_WRITE_EXCEPTIONS, ensure_ascii=False, sort_keys=True)
                   + "。为什么这条例外不违反 Ⅲ 类冻结扩张：**给既有牙加一条声明例外，不是新增牙**"
                     "（97.2 红二原文）；为什么它不影响 BC：本 check 的 `triage_class=3`"
                     "（97.3-4，D 定）⇒ 它的红**本来就不该**单独禁 BC，而它的判据**一字未松**"
                     "（未声明的写入照样红）。"),
             mutant_that_proves_it="enumerator_self_check（行为型变异体已声明拒绝构造，理由见 note）")

    active = [c for c in gate.checks if c["status"] != "N_A"]
    no_proof = [c["id"] for c in active if not c.get("mutant_that_proves_it")]
    proven = sorted({e["check_id"] for e in proof_ledger if e["flip_measured"]})
    a_class = [c["id"] for c in active
               if c["id"] not in SELF_EVIDENT_FLIP and c["id"] not in DECLARED_PROOF_EXCEPTION]
    need_measured = [cid for cid in a_class if cid not in proven]
    n_a_ids = [c["id"] for c in gate.checks if c["status"] == "N_A"]
    gate.add("G24_every_check_mutant_proven",
             "**每条 check 都被证明非恒真**：有登记，且 A 类必须有**实测翻转**台账"
             "（红线 `tooth_must_be_mutant_proven`）",
             (not no_proof) and (not need_measured),
             "缺登记数 = 0；A 类（非 B/C 类）缺实测翻转台账数 = 0",
             f"check 数={len(gate.checks)}（N_A={n_a_ids}）；缺登记={no_proof}；"
             f"A 类 {len(a_class)} 条，其中无翻转台账={need_measured}；"
             f"台账内 flip_measured=True 的 check {len(proven)} 条={proven}",
             ("缺登记或缺实测翻转 ⇒ 按裁定 83.2 它可能是恒真的（等于没有闸）。**本 check 只认台账，"
              "不认登记文案**：登记了变异体、但台账里没有 `flip_measured=True` 记录，一样红"),
             kind="measured",
             note=("三类分层：A 类 = 默认（须有实测翻转台账）；B 类 SELF_EVIDENT_FLIP = "
                   f"{sorted(SELF_EVIDENT_FLIP)}（判据本身即翻转记录，绿 = 已实测到翻转）；"
                   f"C 类 DECLARED_PROOF_EXCEPTION = {sorted(DECLARED_PROOF_EXCEPTION)}"
                   "（元判据 / 执行前提 / 主动拒绝构造行为型变异体，理由写在各自 note 里）。"
                   "翻转台账的三种 form：`matrix_predicate`（用同一个 `pred_GX` 套变异体 matrix）、"
                   "`inprocess_predicate_in_mutant_copy`（把本闸复制进变异体目录跑 `--probe-inprocess`）、"
                   "`necessary_clause`（变异体只跑单臂时，只比该 check 的必要子句）。"
                   "N_A 的 check 不参与本判据（未执行 ⇒ 既不声称已证、也不假装它有牙）"),
             mutant_that_proves_it="本 check 自身即元判据（缺登记或缺翻转台账就红）", ruling_ref="裁定 83.2")

    verdict = "PASS" if gate.ok else "RED"
    # 裁定 **97.3-2**：另出 `verdict_class1`（= 当且仅当 class-1 的 blocking 红为 0 时 PASS），
    #   与顶层 `verdict` **并存**。顶层 `verdict` 的语义与极性**一字未改**（class-2/3 的红照样让它
    #   RED、照样登记、照样必须在 S5 前清零）；变的只有"BC 准入 AND 哪一个判词"（97.3-3）与
    #   "顶层 RED 是否单独构成停训理由"（97.5 ⇒ 不构成）。
    verdict_class1 = gate.verdict_class1
    red_by_class = gate.red_by_class
    n_per_class = {str(k): sum(1 for c in gate.checks if c.get("triage_class") == k)
                   for k in (1, 2, 3)}
    rerun_text = args.rerun_reason.strip() if isinstance(args.rerun_reason, str) else ""
    doc = {"artifact": "c2_norm_contract_gate", "generated_at": now_iso(), "verdict": verdict,
           "verdict_class1": verdict_class1,
           "n_red_class1": gate.n_red_class1,
           "n_red_class2": len(red_by_class[2]), "n_red_class3": len(red_by_class[3]),
           "red_by_triage_class": red_by_class,
           "bc_blocking_caliber": ("裁定 97.5：BC 被禁 = `verdict_class1=RED` 或 "
                                   "`admissible_for_bc=false` 或 `Tp5` 同源不成立；"
                                   "顶层 `verdict=RED` 本身**不再**等于 BC 被禁，任何线（含 D）"
                                   "不得再拿它当停训理由"),
           "triage_class_authority": {
               "ruling_ref": "裁定 97.3-1/2/4（用户三分类在 check 上的落地）",
               "classes": {"1": "控制与数据正确性（**默认**）", "2": "实验解释风险",
                           "3": "文档与管理完整性"},
               "n_checks_per_class": n_per_class,
               "explicitly_marked_run_level_meta": dict(sorted(TRIAGE_CLASS_RUN_LEVEL_META.items())),
               "d_fixed_marks_ruling_97_3_4": {"G20_write_scope": 3,
                                               "G24_every_check_mutant_proven": 2,
                                               "G25_inprocess_teeth_mutant_proven": 2},
               "single_source_of_truth": ("取值**只**来自 `TRIAGE_CLASS_RUN_LEVEL_META` 一张表"
                                          "（`Gate.add()` 不接受第二份清单）；漏标 id 的失效方向是"
                                          "**安全**的 —— 回落默认 1 ⇒ 只可能更严，不会更松"),
               "semantics": ("`verdict_class1 = PASS` 当且仅当 class-1 的 blocking 红为 0；"
                             "顶层 `verdict` 的语义与极性一字未改")},
           "rerun_reason": ({"status": "declared", "text": rerun_text, "authority": "裁定 97.4"}
                            if rerun_text else
                            {"status": "not_declared", "text": None, "authority": "裁定 97.4",
                             "why": ("调用方未给 `--rerun-reason` ⇒ 不猜、不静默当已声明"
                                     "（裁定 97.4 要求每次重跑全量闸前写一句理由；闸产物每轮 ~95 MB，"
                                     "而 `runs/` 已 39.53 GiB 且被 `.gitignore:12` 排除）")}),
           "ok": gate.ok, "n_checks": len(gate.checks), "n_red": gate.n_red, "n_warn": gate.n_warn,
           "n_unjudged": gate.n_unjudged, "n_n_a": sum(1 for c in gate.checks if c["status"] == "N_A"),
           "schema": "d_minimal_common_check_schema_v1（裁定 78.2）",
           "checks": gate.checks, "arms": {k: {"run": v["run"], "matrix_path": v["matrix_path"],
                                               "matrix_sha256_12": v["matrix_sha256_12"],
                                               "matrix_verdict": (v["matrix"] or {}).get("verdict")}
                                           for k, v in arms.items()},
           "file_mutants": mutant_evidence, "inprocess_probes": probe_runs,
           "proof_ledger": proof_ledger, "evidence": evid,
           "load_pair_at_end": load_pair(),
           "polarity_table_note": ("每条 check 带 `mutant_that_proves_it`：没有变异体能让它红的 check = 恒真 check，"
                                   "按裁定 27.1 等于没有闸")}
    (run_dir / "gate_verdict.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": verdict, "n_checks": len(gate.checks), "n_red": gate.n_red,
                      "n_warn": gate.n_warn, "n_n_a": doc["n_n_a"],
                      "verdict_class1": verdict_class1, "n_red_class1": gate.n_red_class1,
                      "n_red_class2": len(red_by_class[2]), "n_red_class3": len(red_by_class[3]),
                      "red": [c["id"] for c in gate.checks if c["status"] == "RED"],
                      "red_class1": red_by_class[1], "red_class2": red_by_class[2],
                      "red_class3": red_by_class[3],
                      "warn": [c["id"] for c in gate.checks if c["status"] == "WARN"],
                      "n_a": [c["id"] for c in gate.checks if c["status"] == "N_A"],
                      "rerun_reason_status": doc["rerun_reason"]["status"],
                      "exit_code_follows": ("顶层 `verdict`（裁定 97.3-2：其语义与极性未改）；"
                                            "BC 是否被禁看 `verdict_class1`，不看本 exit code"),
                      "run_dir": str(run_dir.relative_to(ROOT)),
                      "load_pair": doc["load_pair_at_end"]}, ensure_ascii=False, indent=2))
    return 0 if gate.ok else 1


if __name__ == "__main__":
    sys.exit(main())
