#!/usr/bin/env python
"""档 9B · 搬运期「末端高度保持」外壳（零训练干预）。**不修改任何冻结文件**。

为什么要外壳而不是改 `mg_eval.py`：`mg_eval.py` / `mg_env*.py` 是冻结文件（坑 22 家族），判据、出身字段、
产物格式都由它一处出。本文件只把 `env.step` 包一层（类级 patch；`ReverseGraspEnv.step` 内部 `super().step()`
⇒ 只 patch 父类就够，两次 patch 会被幂等标志挡住），其余原样交给 `mg_eval.main()`。

两种模式（`--mode`）：
  * `ceilpred`（**本档用的 v2**）：搬运期「末端高度保持」= **终点预测式节流**：
    `dz_allow = (cap - rise - safety·inflight) / (safety·k)`，`dz = clip(min(dz_policy, dz_allow), -1, 1)`；
    `inflight` = 已下发但还没兑现的升程（脉冲响应 b 的尾项 × 最近 3 步**实际下发**的 dz）。
    物理含义：不是「越界了才刹车」，而是「**照现在的命令，末端最终会升到哪**」≤ cap ⇒ 到天花板时速度已≈0。
    只用本体感觉（`eef_z` + 夹爪宽度 + 自己下发过的 dz）⇒ **可部署**。常数出处见 `B_CARRY` 注释。
  * `ceilhold`（**v1；Z0b 判为按不住，留档复现**）：越界才 `dz = -min(1, KP*err_cm)`。
    Z0b 实测 **0/12**（15.22~21.30 cm 只压到 13.38~14.67，门 ≤ 13.15）⇒ 反应式控制在速度级指令上必然过冲。
    为什么不是「把 dz 置 0」：`OSC_POSE` 的 dz 是速度/阻抗级指令，置 0 后末端仍滑行 **中位 3.77 / p90 5.87 cm**
    （400 局 npz 实测，`runs/_diag/s9_tax/coast_400.json`）⇒ 被动限位与「搬运需要 ~11.5 cm 升程」几何不相容。
    出处：`runs/S9_PREREG.md` 增补 1（v1）+ 增补 3（v2）。
  * `zlim`（**已证伪，只为复现留档**）：can 抬升超 cap 就把 `dz>0` 置 0。冒烟实测：夹了 24 次，can 仍升到 18.52 cm
    （`runs/_diag/s9b_smoke/cap_on`）⇒ 不要用它做任何门。

三条硬契约（自测钉住）：
  1. **cap<=0（off）⇒ 逐维恒等**：`n_clamped_total == 0` ∧ `max_abs_dz_delta == 0.0`（Z0 保真门要的就是这条）。
  2. **npz 语义不变**：就地改传进来的动作数组 ⇒ `rollout_actions.npz` 记的仍是**实际下发**的动作；
     改前的 `dz` 记进 sidecar 供审计。
  3. **只改 `dz` 一维**，其余 6 维逐位不动。

用法：`--mode ceilpred --cap-cm 12.15` + 原样透传 `mg_eval.py` 的全部参数。
产物：`<out>/eval_summary.json`（mg_eval 出）+ `<out>/zlim_sidecar.json`（本文件出）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

DZ = 2                 # ACTION_NAMES = [dx, dy, dz, droll, dpitch, dyaw, gripper]
ACTION_DIM_EXPECT = 7
# 夹爪阈值：全部来自 code/mg_env.py 已钉住的实测常数（GRIP_OPEN_WIDTH=0.0788 / GRIP_AT_RESET=0.0417 /
# 夹住 can≈0.05 / GRIP_EMPTY_CLOSE=0.0010），不是本档新调的参数。
OPEN_THR = 0.07        # 「张开过」——越过复位开口 0.0417，才算进入抓取流程
GRASP_THR = 0.058      # 张开之后首次合到它以下 = 抓到（can 直径 5 cm）
RELEASE_THR = 0.062    # 之后重新张过它 = 释放，搬运段结束
DZ_MAX = 1.0           # 动作各维的饱和幅值（mg_env 的 action space = [-1,1]）

# ── v2（`ceilpred`）的动力学常数。**全部来自已落盘的 400 局 TEST npz**（`code/mg_s9b_gain.py` 量，
#    产物 `runs/_diag/s9_tax/dz_gain_400.json`）：搬运段 76230 步上最小二乘拟合
#    `Δeef_z[t](cm) = Σ_j b_j·dz[t-j]`，R²=0.739、残差 σ=0.153 cm；lag 扫描 L=2/4/6 的 k=1.278/1.311/1.325
#    ⇒ 常数对 lag 选择不敏感。`SAFETY = max(上升保真比 1.138, 1/制动保真比 0.680) = 1.470`（**公式定，不调参**）。
B_CARRY = (0.4093, 0.6105, 0.1768, 0.1015)   # cm / 单位 dz
K_CARRY = 1.2981                             # ≈ Σb：单位 dz 脉冲的总升程 = 节流尺度
SAFETY = 1.4702


def code_sha16() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()[:16]


class CarryCeiling:
    """搬运期末端高度保持器（P 控制，只压 dz 一维）。纯逻辑、不碰 env ⇒ 可被 CPU 重放台复用。"""

    mode = "ceilhold"

    def __init__(self, cap_cm: float, kp: float = 0.5):
        self.cap_cm = float(cap_cm)
        self.kp = float(kp)
        self.enabled = self.cap_cm > 0.0
        self.reset()

    def reset(self) -> None:
        self.opened = False
        self.anchor = None            # 抓取时刻的 eef_z
        self.t_grasp = -1
        self.released = False
        self.n_held = 0
        self.max_rise_cm = 0.0
        self.max_err_cm = 0.0
        self.dz_min = 0.0             # 施加过的最负 dz
        self.dz_replaced_sum = 0.0    # Σ|dz_raw - dz_exec|（审计：改动总量）
        self.steps = 0

    def snapshot(self) -> dict:
        return {"anchor_eef_z": self.anchor, "t_grasp": self.t_grasp, "released": self.released,
                "n_held": self.n_held, "max_rise_cm": self.max_rise_cm, "max_err_cm": self.max_err_cm,
                "dz_min": self.dz_min, "dz_replaced_sum": self.dz_replaced_sum, "steps": self.steps}

    def apply(self, action: np.ndarray, eef_z: float) -> bool:
        """就地改 action[DZ]；返回本步是否施加了限位。宽度用于相位机，eef_z 用于高度。"""
        self.steps += 1
        if not self.enabled:
            return False
        return self._apply(action, float(eef_z))

    def phase(self, width: float) -> None:
        """推进相位机（用**动作前**的夹爪宽度，即上一步观测 = 本体感觉可得）。"""
        if self.released:
            return
        if not self.opened:
            if width > OPEN_THR:
                self.opened = True
            return
        if self.anchor is None:
            if width < GRASP_THR:
                self._pending_grasp = True
            return
        if width > RELEASE_THR:
            self.released = True

    def arm(self, eef_z: float, t: int) -> None:
        """在相位机判定「本步刚抓到」时锚定 eef_z。"""
        self.anchor = float(eef_z)
        self.t_grasp = int(t)

    def _apply(self, action: np.ndarray, eef_z: float) -> bool:
        if self.anchor is None or self.released:
            return False
        rise_cm = (eef_z - self.anchor) * 100.0
        if rise_cm > self.max_rise_cm:
            self.max_rise_cm = rise_cm
        err = rise_cm - self.cap_cm
        if err > self.max_err_cm:
            self.max_err_cm = err
        if err <= 0.0:
            return False
        raw = float(action[DZ])
        new = -min(1.0, self.kp * err)
        if new < raw:                      # 只允许比策略更保守（更负），绝不替策略往上抬
            action[DZ] = np.dtype(action.dtype).type(new)
            self.n_held += 1
            self.dz_replaced_sum += abs(raw - new)
            if new < self.dz_min:
                self.dz_min = new
            return True
        return False


class CarryPredict:
    """搬运期「末端高度保持」v2 = 终点预测式节流（只压 dz 一维；本体感觉 + 自己下发过的 dz）。

    为什么不是 v1 的「越界才反向 P」：`dz` 是速度级指令、响应有滞后（b1 > b0，峰值在**下一步**），
    带着上升速度撞天花板必然过冲（Z0b 实测 v1 平均过冲 +1.6 cm、最多 +2.5 cm）。v2 改成
    「预测本步命令的最终落点」：`rise + safety·(b0·dz + inflight) ≤ cap` ⇒ 解出允许的最大 dz。
    """

    mode = "ceilpred"

    def __init__(self, cap_cm: float, b=B_CARRY, safety: float = SAFETY):
        self.cap_cm = float(cap_cm)
        self.b = tuple(float(x) for x in b)
        if len(self.b) < 2:
            raise ValueError(f"b 至少 2 项（要有尾项才算得出 inflight），收到 {self.b}")
        self.safety = float(safety)
        self.k = float(sum(self.b))
        self.k_eff = self.k * self.safety
        self.enabled = self.cap_cm > 0.0
        self.reset()

    def reset(self) -> None:
        self.opened = False
        self.anchor = None
        self.t_grasp = -1
        self.released = False
        self.n_held = 0
        self.max_rise_cm = 0.0
        self.max_err_cm = 0.0
        self.dz_min = 0.0
        self.dz_replaced_sum = 0.0
        self.steps = 0
        self.hist = [0.0] * (len(self.b) - 1)     # 最近实际下发的 dz：[t-1, t-2, t-3]
        self.dz_allow_last = None

    def snapshot(self) -> dict:
        return {"anchor_eef_z": self.anchor, "t_grasp": self.t_grasp, "released": self.released,
                "n_held": self.n_held, "max_rise_cm": self.max_rise_cm, "max_err_cm": self.max_err_cm,
                "dz_min": self.dz_min, "dz_replaced_sum": self.dz_replaced_sum, "steps": self.steps,
                "dz_allow_last": self.dz_allow_last}

    # 相位机与 CarryCeiling 逐字同形（wrap_class 一套逻辑喂三种限位器）
    def phase(self, width: float) -> None:
        if self.released:
            return
        if not self.opened:
            if width > OPEN_THR:
                self.opened = True
            return
        if self.anchor is None:
            return
        if width > RELEASE_THR:
            self.released = True

    def arm(self, eef_z: float, t: int) -> None:
        self.anchor = float(eef_z)
        self.t_grasp = int(t)

    def apply(self, action: np.ndarray, eef_z: float) -> bool:
        self.steps += 1
        hit = self._apply(action, float(eef_z)) if self.enabled else False
        self.hist = [float(action[DZ])] + self.hist[:len(self.hist) - 1]   # 记**实际下发**的 dz
        return hit

    def inflight_cm(self) -> float:
        return self.safety * sum(self.b[j + 1] * self.hist[j] for j in range(len(self.hist)))

    def dz_allow(self, rise_cm: float) -> float:
        return max(-DZ_MAX, min(DZ_MAX, (self.cap_cm - rise_cm - self.inflight_cm()) / self.k_eff))

    def _apply(self, action: np.ndarray, eef_z: float) -> bool:
        if self.anchor is None or self.released:
            return False
        rise_cm = (eef_z - self.anchor) * 100.0
        if rise_cm > self.max_rise_cm:
            self.max_rise_cm = rise_cm
        err = rise_cm - self.cap_cm
        if err > self.max_err_cm:
            self.max_err_cm = err
        allow = self.dz_allow(rise_cm)
        self.dz_allow_last = allow
        raw = float(action[DZ])
        if allow >= raw:                      # 只允许比策略更保守（更小），绝不替策略往上抬
            return False
        action[DZ] = np.dtype(action.dtype).type(allow)
        self.n_held += 1
        self.dz_replaced_sum += abs(raw - allow)
        if allow < self.dz_min:
            self.dz_min = allow
        return True


class CanLiftClamp:
    """（已证伪）can 抬升超 cap ⇒ 把 dz>0 置 0。保留只为复现 `runs/S9_PREREG.md` 增补 1 ①。"""

    mode = "zlim"

    def __init__(self, cap_cm: float):
        self.cap_cm = float(cap_cm)
        self.enabled = self.cap_cm > 0.0
        self.reset()

    def reset(self) -> None:
        self.z0 = None
        self.opened = False          # 与 CarryCeiling 同形，wrap_class 才能一套逻辑喂两种限位器
        self.n_held = 0
        self.max_rise_cm = 0.0
        self.max_err_cm = 0.0
        self.dz_min = 0.0
        self.dz_replaced_sum = 0.0
        self.steps = 0
        self.anchor = None
        self.t_grasp = -1
        self.released = False

    def snapshot(self) -> dict:
        return {"z0": self.z0, "n_held": self.n_held, "max_lift_pre_cm": self.max_rise_cm,
                "dz_min": self.dz_min, "dz_replaced_sum": self.dz_replaced_sum, "steps": self.steps}

    def phase(self, width: float) -> None:
        return None

    def arm(self, eef_z: float, t: int) -> None:
        return None

    def apply(self, action: np.ndarray, can_z: float) -> bool:
        self.steps += 1
        if not self.enabled:
            return False
        if self.z0 is None:
            self.z0 = float(can_z)
        lift_cm = (float(can_z) - self.z0) * 100.0
        if lift_cm > self.max_rise_cm:
            self.max_rise_cm = lift_cm
        if lift_cm >= self.cap_cm and float(action[DZ]) > 0.0:
            raw = float(action[DZ])
            action[DZ] = np.dtype(action.dtype).type(0.0)
            self.n_held += 1
            self.dz_replaced_sum += raw
            self.max_err_cm = max(self.max_err_cm, lift_cm - self.cap_cm)
            return True
        return False


def make_sidecar(mode: str, cap_cm: float, kp: float, b=B_CARRY, safety: float = SAFETY) -> dict:
    sc = {"tool": "mg_eval_zlim.py", "tool_sha256_16": code_sha16(), "mode": mode,
          "cap_cm": float(cap_cm), "kp": (float(kp) if mode == "ceilhold" else None),
          "disabled": bool(cap_cm <= 0.0),
          "phase_thresholds": {"open": OPEN_THR, "grasp": GRASP_THR, "release": RELEASE_THR},
          "n_steps_total": 0, "n_clamped_total": 0, "max_abs_dz_delta": 0.0, "dz_replaced_sum": 0.0,
          "n_grasped_ep": 0, "invariant_no_clamp_when_off": False,
          "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ep": []}
    if mode == "ceilpred":      # 审计：v2 的控制律常数必须跟着读数一起落盘（否则事后无法复现）
        sc["b_carry"] = [float(x) for x in b]
        sc["k_carry"] = float(sum(b))
        sc["safety"] = float(safety)
        sc["k_eff"] = float(sum(b)) * float(safety)
        sc["law"] = "dz = clip(min(dz_policy, (cap - rise - safety*inflight)/(safety*k)), -1, 1)"
        sc["const_source"] = "code/mg_s9b_gain.py -> runs/_diag/s9_tax/dz_gain_400.json（400 局 TEST npz，76230 搬运步）"
    return sc


def wrap_class(cls, filt, sc: dict):
    """把限位器装到 env 类上（类级 patch）。幂等：子类继承到标志就不会被二次包裹。"""
    if getattr(cls, "_mg_zlim_wrapped", False):
        return cls
    orig_step, orig_reset = cls.step, cls.reset

    def reset(self, *a, **kw):
        # 上一局的限位器状态必须在 filt.reset() **之前**定格，否则逐局审计（Z4 要用的
        # 「本局搬运期最大升程」）会被最后一局覆盖。曾踩：main() 收尾时把**最终**快照写给每一局。
        if sc["ep"] and sc["ep"][-1].get("filter") is None:
            sc["ep"][-1]["filter"] = filt.snapshot()
        obs = orig_reset(self, *a, **kw)
        filt.reset()
        sc["ep"].append({"z0_can": None, "t": 0})
        return obs

    def step(self, action):
        if not isinstance(action, np.ndarray):
            raise TypeError(f"[zlim] 动作必须是 np.ndarray（就地改才符合 npz 语义），收到 {type(action).__name__}")
        if action.shape[0] != ACTION_DIM_EXPECT:
            raise ValueError(f"[zlim] 动作必须 {ACTION_DIM_EXPECT} 维，收到 {action.shape}")
        eps = sc["ep"]
        if eps:
            cur = eps[-1]
            cur["t"] += 1
            sc["n_steps_total"] += 1
            if cur["z0_can"] is None:
                cur["z0_can"] = float(self.object_pos[2])     # 反向任务在 super().reset() 之后才挪 can ⇒ 第一步取
            if filt.enabled and not action.flags.writeable:
                raise ValueError("[zlim] 动作数组只读 ⇒ 无法就地限位；拒绝静默降级（否则 npz 记的不是实际下发的动作）")
            width = float(self.gripper_width)
            eef_z = float(self.eef_pos[2])
            was_unanchored = getattr(filt, "anchor", None) is None
            filt.phase(width)
            if was_unanchored and filt.opened and not filt.released and width < GRASP_THR:
                filt.arm(eef_z, cur["t"])
                sc["n_grasped_ep"] += 1
                cur["anchor_eef_z"] = float(eef_z)
                cur["t_grasp"] = cur["t"]
            raw_dz = float(action[DZ])
            hit = filt.apply(action, eef_z if filt.mode in ("ceilhold", "ceilpred") else float(self.object_pos[2]))
            if hit:
                sc["n_clamped_total"] += 1
                d = abs(raw_dz - float(action[DZ]))
                sc["max_abs_dz_delta"] = max(sc["max_abs_dz_delta"], d)
                sc["dz_replaced_sum"] += d
            cur["n_clamped"] = filt.n_held
            cur["max_rise_cm"] = filt.max_rise_cm
        return orig_step(self, action)

    def _finish_ep(self, *a, **kw):        # 占位：保留 orig 的其它方法不动
        raise NotImplementedError

    cls.reset = reset
    cls.step = step
    cls._mg_zlim_wrapped = True
    return cls


def build_filter(mode: str, cap_cm: float, kp: float = 0.5, b=B_CARRY, safety: float = SAFETY):
    """mode → 限位器实例（单一出口：install 与自测的 `_mk` 都走这里，避免两处选择不一致）。"""
    if mode == "ceilpred":
        return CarryPredict(cap_cm, b=b, safety=safety)
    if mode == "ceilhold":
        return CarryCeiling(cap_cm, kp)
    if mode == "zlim":
        return CanLiftClamp(cap_cm)
    raise ValueError(f"未知 mode={mode}（可选 ceilpred / ceilhold / zlim）")


def install(mode: str, cap_cm: float, kp: float, sc: dict, b=B_CARRY, safety: float = SAFETY):
    filt = build_filter(mode, cap_cm, kp, b, safety)
    sc["mode"] = filt.mode
    import mg_env
    wrap_class(mg_env.SingleArmGraspEnv, filt, sc)
    sc["patched_classes"] = ["mg_env.SingleArmGraspEnv"]
    import mg_env_reverse
    if not getattr(mg_env_reverse.ReverseGraspEnv, "_mg_zlim_wrapped", False):
        wrap_class(mg_env_reverse.ReverseGraspEnv, filt, sc)
        sc["patched_classes"].append("mg_env_reverse.ReverseGraspEnv")
    sc["note_patch"] = ("ReverseGraspEnv.step/reset 内部调用 super() ⇒ patch 父类即生效；"
                        "子类若继承到 _mg_zlim_wrapped 标志则不会被二次包裹（幂等，自测 idem1 钉住）")
    return filt


def finalize_sidecar(sc: dict, filt) -> int:
    """收尾：给还没定格的局补限位器快照。正常只有**最后一局**（其后没有 reset 来定格）。

    返回补了几局；>1 说明中途有局没走 reset（审计异常，写进 sidecar 供事后查）。
    """
    snap = filt.snapshot() if hasattr(filt, "snapshot") else None
    n = 0
    for e in sc["ep"]:
        if e.get("filter") is None:
            e["filter"] = snap
            n += 1
    sc["filter_tail_filled"] = n
    return n


def peek_out_dir(rest: list[str]) -> str:
    for i, a in enumerate(rest):
        if a == "--out" and i + 1 < len(rest):
            return rest[i + 1]
        if a.startswith("--out="):
            return a.split("=", 1)[1]
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("ceilpred", "ceilhold", "zlim"), default="ceilpred",
                    help="ceilpred=终点预测式节流（本档 v2）；ceilhold=越界反向 P（v1，Z0b 判为按不住）；"
                         "zlim=已证伪的 can 抬升被动限位（只为复现留档）")
    ap.add_argument("--cap-cm", type=float, default=0.0, help="搬运期末端升程上限（cm）。0 = 关闭（对照条件，逐维恒等）")
    ap.add_argument("--kp", type=float, default=0.5, help="ceilhold(v1) 的比例增益（每 cm 越界给多少 dz，饱和到 -1）")
    ap.add_argument("--b", default="", help="ceilpred(v2) 的脉冲响应 b0,b1,b2,b3（默认用 mg_s9b_gain 量出的 B_CARRY）")
    ap.add_argument("--safety", type=float, default=SAFETY, help="ceilpred(v2) 的安全系数（默认 = max(f_pos,1/f_brk)）")
    ap.add_argument("--sidecar-out", default="", help="sidecar 落盘路径（默认 <mg_eval 的 --out>/zlim_sidecar.json）")
    args, rest = ap.parse_known_args()

    b = tuple(float(x) for x in args.b.split(",")) if args.b.strip() else B_CARRY
    sc = make_sidecar(args.mode, args.cap_cm, args.kp, b, args.safety)
    sc["argv_passthrough"] = list(rest)
    out_dir = peek_out_dir(rest)
    filt = install(args.mode, args.cap_cm, args.kp, sc, b, args.safety)
    extra = (f" kp={args.kp}" if args.mode == "ceilhold" else
             f" k_eff={filt.k_eff:.4f} safety={args.safety}" if args.mode == "ceilpred" else "")
    print(f"[zlim] mode={args.mode} cap={args.cap_cm:.2f} cm{extra}（{'关闭' if args.cap_cm <= 0 else '启用'}） "
          f"patched={sc['patched_classes']} sha={sc['tool_sha256_16']}")

    import mg_eval
    sys.argv = ["mg_eval.py"] + list(rest)
    rc = mg_eval.main()

    sc["finished"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sc["mg_eval_rc"] = int(rc)
    sc["n_ep"] = len(sc["ep"])
    finalize_sidecar(sc, filt)
    sc["invariant_no_clamp_when_off"] = bool(sc["disabled"] and sc["n_clamped_total"] == 0
                                             and sc["max_abs_dz_delta"] == 0.0)
    side = Path(args.sidecar_out) if args.sidecar_out else (Path(out_dir) / "zlim_sidecar.json" if out_dir else None)
    if side is not None:
        if not side.is_absolute():
            side = MG_ROOT / side
        side.parent.mkdir(parents=True, exist_ok=True)
        side.write_text(json.dumps(sc, ensure_ascii=False, indent=1, default=float))
        print(f"[zlim] sidecar -> {side}  n_clamped={sc['n_clamped_total']} "
              f"max|Δdz|={sc['max_abs_dz_delta']:.4f} steps={sc['n_steps_total']} eps={sc['n_ep']}")
    else:
        print("[zlim] ⚠️ 没有 --out，也没给 --sidecar-out ⇒ sidecar 未落盘（审计断链）")
    return rc


# ───────────────────────── 自测（零 GPU、合成对照，坑 77）─────────────────────────
class _FakeEnv:
    def __init__(self, z0: float = 0.80, eef0: float = 0.95):
        self._z = z0
        self._eef = eef0
        self._w = 0.0417
        self.stepped: list[np.ndarray] = []

    @property
    def object_pos(self) -> np.ndarray:
        return np.array([0.0, 0.0, self._z], dtype=np.float64)

    @property
    def eef_pos(self) -> np.ndarray:
        return np.array([0.0, 0.0, self._eef], dtype=np.float64)

    @property
    def gripper_width(self) -> float:
        return self._w

    def reset(self, seed=None):
        self._z, self._eef, self._w = 0.80, 0.95, 0.0417
        return {"obs": seed}

    def step(self, action):
        self.stepped.append(np.array(action, copy=True))
        self._eef += float(action[DZ]) * 0.01      # dz>0 = 上升（与 OSC 同号）
        self._z += float(action[DZ]) * 0.01
        return {}, 0.0, False, False, {}


def _act(dz: float = 0.5, dtype=np.float32) -> np.ndarray:
    return np.array([0.1, -0.2, dz, 0.3, -0.4, 0.05, 0.9], dtype=dtype)


def _mk(cap: float, mode: str = "ceilhold", kp: float = 0.5, b=B_CARRY, safety: float = SAFETY):
    """合成对照：真逻辑（三种限位器 + wrap_class）+ 假物理（_FakeEnv）。"""
    sc = make_sidecar(mode, cap, kp, b, safety)
    filt = build_filter(mode, cap, kp, b, safety)
    cls = wrap_class(type("E", (_FakeEnv,), {}), filt, sc)
    return cls(), filt, sc


def selftest() -> int:
    fails: list[str] = []
    total = [0]

    def ck(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    # ── A. CarryCeiling 纯逻辑（不经过 env）──
    f = CarryCeiling(12.15, kp=0.5)
    a = _act(0.8)
    f.phase(0.0417); ck("A1 复位开口不触发 opened", f.opened is False and f.apply(a, 0.95) is False)
    f.phase(0.079); ck("A2 张开 >0.07 ⇒ opened", f.opened is True)
    f.phase(0.079)
    a = _act(0.8); f.phase(0.050); f.arm(0.95, 10)
    ck("A3 合到 <0.058 ⇒ 锚定 eef_z", f.anchor == 0.95 and f.t_grasp == 10)
    ck("A4 升程 0 ⇒ 不干预", f.apply(a, 0.95) is False and a[DZ] == np.float32(0.8))
    ck("A5 升程 = cap（12.15cm）⇒ 边界不干预（err=0）", f.apply(_act(0.8), 0.95 + 0.1215) is False)
    a6 = _act(0.8)
    hit = f.apply(a6, 0.95 + 0.1315)      # 升程 13.15 ⇒ err = 1.0 cm ⇒ dz = -0.5
    ck("A6 越界 1 cm ⇒ dz = -KP*err = -0.5", hit and abs(float(a6[DZ]) + 0.5) < 1e-6)
    a7 = _act(0.8)
    f.apply(a7, 0.95 + 0.1315 + 0.05)     # err = 6 cm ⇒ 饱和 -1
    ck("A7 越界 6 cm ⇒ dz 饱和到 -1", abs(float(a7[DZ]) + 1.0) < 1e-6)
    a8 = _act(-0.9)
    f.apply(a8, 0.95 + 0.1315)            # err=1 ⇒ 想给 -0.5，但策略自己已在 -0.9（更保守）
    ck("A8 只允许更保守：策略已 -0.9 ⇒ 不改成 -0.5", abs(float(a8[DZ]) + 0.9) < 1e-6)
    ck("A9 其余 6 维逐位不动", all(a6[i] == _act(0.8)[i] for i in (0, 1, 3, 4, 5, 6)))
    ck("A10 dtype 不变", a6.dtype == np.float32)
    f.phase(0.079)
    ck("A11 张过 0.062 ⇒ 释放，之后不再干预", f.released is True and f.apply(_act(0.8), 1.5) is False)
    ck("A12 max_rise_cm 跟踪到最大升程", abs(f.max_rise_cm - 18.15) < 1e-6)
    ck("A13 n_held 计数正确", f.n_held == 2)

    f0 = CarryCeiling(0.0)
    a0 = _act(0.8)
    f0.phase(0.079); f0.arm(0.95, 1); 
    ck("B1 cap=0 ⇒ enabled False 且 apply 恒不改", f0.enabled is False and f0.apply(a0, 2.0) is False
       and a0[DZ] == np.float32(0.8))

    # ── B. 经过 env 包装（含相位机与 sidecar）──
    e, filt, sc = _mk(0.0)
    e.reset(seed=1)
    sent = []
    for dz in (0.9, 0.5, -0.3, 0.0, 1.0):
        aa = _act(dz); sent.append(aa.copy()); e.step(aa)
    ck("C1 off：动作逐维恒等", all(np.array_equal(x, y) for x, y in zip(sent, e.stepped)))
    ck("C2 off：n_clamped_total == 0", sc["n_clamped_total"] == 0)
    ck("C3 off：max_abs_dz_delta == 0.0", sc["max_abs_dz_delta"] == 0.0)
    ck("C4 off：disabled 标志", sc["disabled"] is True)
    ck("C5 off：步数照常计数", sc["n_steps_total"] == 5)

    e2, filt2, sc2 = _mk(2.0)      # cap = 2 cm，FakeEnv 每 dz=1.0 升 0.01 m = 1 cm
    e2.reset(seed=2)
    e2._w = 0.079; e2.step(_act(0.0))          # opened
    e2._w = 0.050; e2.step(_act(1.0))          # 抓到 ⇒ 锚定；本步升 1 cm
    ck("D1 抓取被识别并锚定", filt2.anchor is not None and sc2["n_grasped_ep"] >= 0)
    e2._w = 0.050; e2.step(_act(1.0))          # 升程 1→2 cm（边界内）
    ck("D2 未越界不干预", sc2["n_clamped_total"] == 0)
    e2._w = 0.050; e2.step(_act(1.0))          # 升程 2→3：本步起点 = 2 cm（err=0）仍不干预
    e2._w = 0.050; e2.step(_act(1.0))          # 起点 3 cm ⇒ err=1 ⇒ dz=-0.5，末端开始下降
    ck("D3 越界后主动命令下降（dz<0）", sc2["n_clamped_total"] >= 1 and filt2.dz_min < 0)
    ck("D4 sidecar 记了改动量", sc2["max_abs_dz_delta"] > 0 and sc2["dz_replaced_sum"] > 0)
    e2._w = 0.079; e2.step(_act(1.0))          # 释放
    n_before = sc2["n_clamped_total"]
    e2._w = 0.079; e2.step(_act(1.0))
    ck("D5 释放后不再干预", sc2["n_clamped_total"] == n_before)

    # 未 reset 就 step ⇒ 直通不炸
    e3, _f3, sc3 = _mk(2.0)
    a3 = _act(1.0)
    e3.step(a3)
    ck("E1 未 reset 直通、不改动作", float(a3[DZ]) == 1.0 and sc3["n_clamped_total"] == 0)

    # 契约违背必须响
    e4, _f4, _s4 = _mk(2.0)
    e4.reset(seed=4)
    try:
        e4.step([0.0] * 7); ck("F1 非 ndarray 必须抛", False)
    except TypeError:
        ck("F1 非 ndarray 必须抛", True)
    try:
        e4.step(np.zeros(6, dtype=np.float32)); ck("F2 维度错必须抛", False)
    except ValueError:
        ck("F2 维度错必须抛", True)
    ro = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32); ro.setflags(write=False)
    e4._w = 0.079; e4.step(_act(0.0)); e4._w = 0.050; e4.step(_act(0.0)); e4._eef = 1.20
    try:
        e4.step(ro); ck("F3 只读数组必须抛（不许静默不限位）", False)
    except ValueError:
        ck("F3 只读数组必须抛（不许静默不限位）", True)

    # 幂等：重复 wrap 不叠加
    e5, filt5, sc5 = _mk(2.0)
    wrap_class(type(e5), filt5, sc5)
    e5.reset(seed=5); e5._w = 0.079; e5.step(_act(0.0)); e5._w = 0.050; e5.step(_act(1.0))
    e5._eef = 1.20
    e5.step(_act(1.0))
    ck("G1 重复 wrap 只夹一次", sc5["n_clamped_total"] == 1)

    # 多局：锚点每局重置
    e6, filt6, sc6 = _mk(2.0)
    e6.reset(seed=6); e6._w = 0.079; e6.step(_act(0.0)); e6._w = 0.050; e6.step(_act(1.0)); e6._eef = 1.20
    e6.step(_act(1.0))
    n1 = sc6["n_clamped_total"]
    e6.reset(seed=7); e6._w = 0.050; e6.step(_act(1.0))
    ck("H1 新一局锚点重置 ⇒ 不误夹", sc6["n_clamped_total"] == n1 and len(sc6["ep"]) == 2)

    # ── 逐局快照必须在 reset 时定格（Z4 的受控量读它，不能被最后一局覆盖）──
    e9, filt9, sc9 = _mk(2.0)
    e9.reset(seed=11); e9._w = 0.079; e9.step(_act(0.0)); e9._w = 0.050; e9.step(_act(1.0))
    e9._eef = 1.20; e9.step(_act(1.0))                 # 第 1 局：升程 25 cm ⇒ 被夹
    r1 = filt9.max_rise_cm
    e9.reset(seed=12)                                  # 第 2 局：完全不越界
    e9._w = 0.079; e9.step(_act(0.0)); e9._w = 0.050; e9.step(_act(0.0))
    ck("K1 第 1 局的快照在 reset 时定格（不被第 2 局覆盖）",
       len(sc9["ep"]) == 2 and sc9["ep"][0]["filter"] is not None
       and abs(sc9["ep"][0]["filter"]["max_rise_cm"] - r1) < 1e-9 and r1 > 20.0)
    ck("K2 收尾只补最后一局（filter_tail_filled == 1）", finalize_sidecar(sc9, filt9) == 1
       and sc9["filter_tail_filled"] == 1)
    ck("K3 两局快照不相同（旧实现会把最终快照复制给每一局）",
       sc9["ep"][0]["filter"]["max_rise_cm"] != sc9["ep"][1]["filter"]["max_rise_cm"]
       and sc9["ep"][1]["filter"]["max_rise_cm"] == 0.0)
    ck("K4 重复收尾幂等（不会把已定格的局改掉）", finalize_sidecar(sc9, filt9) == 0
       and abs(sc9["ep"][0]["filter"]["max_rise_cm"] - r1) < 1e-9)

    # ── v2（ceilpred · 终点预测式节流）：本档 GPU 段用的就是它 ──
    p0 = CarryPredict(0.0)
    ck("N1 cap=0 ⇒ 关闭且恒等（Z0 保真门要的就是这条）", p0.enabled is False and p0.apply(_act(0.8), 2.0) is False)
    p = CarryPredict(12.15)
    ck("N2 常数自洽：K_CARRY≈Σb、safety≥1、k_eff=safety·k、b 四项",
       abs(K_CARRY - sum(B_CARRY)) < 1e-3 and SAFETY >= 1.0
       and abs(p.k_eff - p.k * p.safety) < 1e-9 and len(B_CARRY) == 4)
    p.phase(0.079); p.arm(0.95, 5)
    aN3 = _act(0.8)
    ck("N3 headroom 大（rise=0）⇒ dz_allow 饱和到 +1 ⇒ 恒等放行", p.apply(aN3, 0.95) is False
       and aN3[DZ] == np.float32(0.8) and p.dz_allow_last == DZ_MAX)
    p2 = CarryPredict(12.15); p2.phase(0.079); p2.arm(0.95, 5); p2.hist = [1.0, 1.0, 1.0]
    aN4 = _act(1.0)
    hit4 = p2.apply(aN4, 0.95 + 0.115)          # rise=11.5、在飞的升程 1.31 ⇒ 预测终点已超 cap
    ck("N4 接近天花板 ⇒ 提前节流（dz 被压小）", hit4 and float(aN4[DZ]) < 1.0)
    p3 = CarryPredict(12.15); p3.phase(0.079); p3.arm(0.95, 5)
    aN5 = _act(1.0)
    hit5 = p3.apply(aN5, 0.95 + 0.1415)          # 越界 2 cm
    ck("N5 越界 ⇒ dz 变负（主动制动，饱和到 -1）", hit5 and abs(float(aN5[DZ]) + 1.0) < 1e-6)
    aN6 = _act(-1.0); p3.apply(aN6, 0.95 + 0.1415)
    ck("N6 只允许更保守：策略已 -1 ⇒ 不改（绝不替策略往上抬）", abs(float(aN6[DZ]) + 1.0) < 1e-6)
    aN7 = _act(1.0); p3.apply(aN7, 0.95 + 0.1415)
    ck("N7 其余 6 维逐位不动 ∧ dtype 不变",
       all(aN7[i] == _act(1.0)[i] for i in (0, 1, 3, 4, 5, 6)) and aN7.dtype == np.float32)
    ck("N8 hist 记的是**实际下发**的 dz（下一步 inflight 用它，不用策略原值）",
       abs(p3.hist[0] - float(aN7[DZ])) < 1e-6)
    p3.phase(0.079)
    ck("N9 释放后不再干预", p3.released is True and p3.apply(_act(1.0), 2.0) is False)

    # 闭环（假物理 1 cm/单位dz、无滞后）：一路命令 dz=+1，终点必须贴着 cap 且**不过冲**
    e10, filt10, sc10 = _mk(12.15, mode="ceilpred")
    e10.reset(seed=21); e10._w = 0.079; e10.step(_act(1.0))
    for _ in range(40):
        e10._w = 0.050; e10.step(_act(1.0))
    ck("N10 闭环不过冲：max_rise ≤ cap（v1 在同一台上过冲 +1.6 cm）", filt10.max_rise_cm <= 12.15 + 1e-6)
    ck("N11 闭环也不过度节流：停在 cap 的 1 cm 之内", filt10.max_rise_cm >= 12.15 - 1.0)
    ck("N12 sidecar 记了 v2 的控制律常数（事后能复现）",
       sc10["mode"] == "ceilpred" and abs(sc10["k_eff"] - K_CARRY * SAFETY) < 1e-3
       and len(sc10["b_carry"]) == 4 and sc10["n_clamped_total"] > 0)
    ck("N13 build_filter 单一出口：三种 mode 各得其所",
       (build_filter("ceilpred", 5.0).mode, build_filter("ceilhold", 5.0).mode,
        build_filter("zlim", 5.0).mode) == ("ceilpred", "ceilhold", "zlim"))
    try:
        build_filter("nope", 5.0); ck("N14 未知 mode 必须抛（不许静默降级）", False)
    except ValueError:
        ck("N14 未知 mode 必须抛（不许静默降级）", True)

    # zlim（已证伪）模式仍能跑，且 cap=0 恒等
    e7, filt7, sc7 = _mk(0.0, mode="zlim")
    e7.reset(seed=8); a7 = _act(1.0); e7.step(a7)
    ck("I1 zlim off 恒等", float(a7[DZ]) == 1.0 and sc7["n_clamped_total"] == 0 and sc7["mode"] == "zlim")
    e8, filt8, sc8 = _mk(1.0, mode="zlim")
    e8.reset(seed=9); e8.step(_act(0.0))        # 第一步锚定 z0_can（反向任务在 super().reset() 之后才挪 can）
    e8._z = 0.82                                # can 抬到 +2 cm ≥ cap 1 cm
    a8 = _act(1.0); e8.step(a8)
    ck("I2 zlim 仍按 can 抬升夹 dz>0", float(a8[DZ]) == 0.0 and sc8["n_clamped_total"] == 1)
    ck("I3 z0_can 在第一步锚定（不是 reset 时）", abs(sc8["ep"][0]["z0_can"] - 0.80) < 1e-9)

    ck("J1 sha16 是 16 位十六进制", len(sc["tool_sha256_16"]) == 16
       and all(c in "0123456789abcdef" for c in sc["tool_sha256_16"]))
    ck("J2 peek_out_dir 认两种写法", peek_out_dir(["--out", "/a/b"]) == "/a/b"
       and peek_out_dir(["--out=/c/d"]) == "/c/d" and peek_out_dir(["--episodes", "20"]) == "")
    ck("J3 相位阈值来自 env 实测常数", (OPEN_THR, GRASP_THR, RELEASE_THR) == (0.07, 0.058, 0.062))

    print(f"限位外壳钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for x in fails:
        print("  🚫", x)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(main())
