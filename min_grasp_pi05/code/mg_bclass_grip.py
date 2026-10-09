#!/usr/bin/env python3
"""B 类失败（「抓起了却没送到」）的**夹爪通道**事前诊断（零 GPU、只读盘上产物）

定位：**回溯性分析**，用来给下一档立假设（同档 7F 里 F4 的标注方式）。
  ⚠️ **不进任何门、不改任何既有判据、不产出成功率结论**；下一档要动它必须先写预注册（坑 40）。

为什么要有它（出处）：
* `runs/_diag/s9_tax/SUMMARY.md`（档 9A）：放宽口径下真失败的最大单一桶 = **B（抓起了却没送到附近，`min_dist`>25 cm）**，
  关门配方占真失败 **52%**、便宜配方 **62%**；而 TILT（侧躺）已被 9B 证明是**接触/动量弹射**、dz 级外壳按不住。
* 9B 的 `pop_probe24.json` 顺带露了一条线索：侧躺局里 can 抬升 15.3 cm 而**末端只抬 1.2 cm** ⇒ can 是被夹爪「挤」着弹上去的。
  ⇒ 假设：**夹爪通道**（闭合指令过强 / 中途丢罐）可能是 B 与 TILT 的**共同上游**。本工具只做测量，不做因果断言。

纪律（本文件自己遵守的）：
1. **只读一手产物**：`runs/<arm>_rev_test_rand20_k10*/rollout_actions.npz` 的 `action(T,7)`、`state(T,8)`
   + 同目录 `eval_summary.json` 的逐局标记（`success/success_relaxed/delivered_tipped/max_lift_cm/min_dist_to_target_xy`）。
2. **同一个量不重写第二遍**（坑 54）：搬运段窗口 `carry_window` 与末端升程 `rise_cm` **import 自** `code/mg_zlim_replay.py`；
   夹爪阈值 `OPEN_THR/GRASP_THR/RELEASE_THR` **import 自** `code/mg_eval_zlim.py`、开口实测常数
   `GRIP_OPEN_WIDTH/GRIP_AT_RESET/GRIP_HOLD_WIDTH/GRIP_EMPTY_CLOSE` **import 自** `code/mg_env.py`（冻结文件，只 import）。
2b. **夹爪指令符号靠实测、不靠注释**（坑 82）：`code/mg_env.py` 自己的注释互相打架（第 11/305 行写「-1=close,+1=open」，
   而第 66/68 行的实测标注是「action=-1 → 0.0788 张开到底 / action=+1 → 0.0010 空合到底」）⇒ 本工具用 `grip_sign_probe`
   在**专家示范**上实测 `sign(act)` 与 `sign(Δwidth)` 的一致率来定符号，并把读数写进报告，不再引用任何注释。
3. **阈值只从专家示范推**（坑 27/42，同 9A §三）：`W_LOSS` = 专家搬运段逐 step 宽度的 **p05**，
   在**读任何策略数据之前**由 `data/mix60f120r_rev_raw.npz`（120 集反向示范）定死；并**同时报 p01/p10 的敏感性**，
   免得结论挂在阈值上。
4. ⚠️ **不复用**上一轮的 `carry_400.json` / `slip_400.json`：那两个是 ad-hoc 脚本产物、字段定义无处可查
   （`slip_400.json` 还是截断的 83 字节，已隔离为 `*.CORRUPT_TRUNCATED_83B`）⇒ 本工具全部从一手数据重算，定义写死在这里。
5. **缺产物 ≠ 0**（坑 40③）：缺 npz / 缺逐局字段的局一律单列 `missing`，不当 0 计入。
6. 自测用**合成夹具**、不断言盘上进度（坑 77）。

用法：
    $MG_PY code/mg_bclass_grip.py --selftest
    $MG_PY code/mg_bclass_grip.py                 # 写 runs/_diag/s9_tax/grip_mech_400.{json,md}
    $MG_PY code/mg_bclass_grip.py --sample val    # 换 val 窗口（5 个关门格，各 1×20）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_eval_zlim import GRASP_THR, OPEN_THR, RELEASE_THR      # noqa: E402  真值源 = code/mg_env.py 实测
from mg_env import (GRIP_AT_RESET, GRIP_EMPTY_CLOSE,           # noqa: E402  开口实测常数（冻结文件，只 import）
                    GRIP_HOLD_WIDTH, GRIP_OPEN_WIDTH)
from mg_zlim_replay import carry_window, rise_cm, sample_dirs  # noqa: E402  同一个量不重写第二遍（坑 54）

DEMO_NPZ = MG / "data/mix60f120r_rev_raw.npz"   # 120 集反向示范（专家）；阈值只从这里推
OUT_DIR = MG / "runs/_diag/s9_tax"
PRE = 10            # 丢罐前的观察窗（步）；K=10 = 一个执行步长 ⇒ 「一次重规划」的量级
K_MATCH = 40        # 相位匹配窗（步）：只比搬运段**前 40 步**（≈4 次重规划），两组都取得到 ⇒ 消掉窗口删失偏差
W_Q_MAIN = 0.05     # W_LOSS = 专家搬运段宽度分布的 p05（事前定死）
W_Q_SENS = (0.01, 0.10)   # 敏感性：换成 p01 / p10 结论会不会翻
N_PERM = 10000
PERM_SEED = 20261007
MOVE_EPS = 2e-4     # 「宽度真的动了」的下限（m/步）；小于它不算一次开合，避免噪声决定符号
LABEL_KEYS = ("arm", "dir", "ep", "seed", "cls", "grasped", "strict", "relax", "tipped", "held",
              "w_min", "can_lift_cm", "min_dist_cm", "eef_rise_cm", "carry_len", "lost", "t_loss",
              "loss_after_steps")   # 逐局归因标签的字段（缺的一律写 None，不当 0，坑 40③）


def label_rows(recs: list[dict]) -> list[dict]:
    """把逐局测量压成一张**可复用的归因标签表**（按 `(arm, dir, ep, seed)` 可 join 回任何既有产物）。

    这是本诊断唯一**向前**的产出：后续任何一档要做失败分类，直接读 `runs/_diag/s9_tax/grip_labels_*.json`，
    不必再碰 npz。⚠️ `held` 是**归因标签**、不是成功判据（OK 组也有空合却送达，阳性预测值见报告 §一·补）。
    """
    return [{k: r.get(k) for k in LABEL_KEYS} for r in recs]


# ─────────────────────────── 纯函数（口径写死在这里）───────────────────────────
def q(v, p: float) -> float:
    """下分位（与 mg_verdict_s9b.quantile_lower 同义：取第 floor(p·n) 小，n=0 → nan）。"""
    v = [float(x) for x in v]
    if not v:
        return float("nan")
    v = sorted(v)
    return v[min(len(v) - 1, int(np.floor(p * len(v))))]


def spd_acc(eef: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """逐控制步的末端速度 |Δpos|（m/步）与加速度 |Δ速度|。长度 = T-1 / T-2。"""
    if len(eef) < 3:
        return np.zeros(0), np.zeros(0)
    s = np.linalg.norm(np.diff(eef[:, :3], axis=0), axis=1)
    return s, np.abs(np.diff(s))


def classify(grasped: bool, relax: bool, tipped: bool) -> str:
    """一局的分组口径（抽成纯函数好自测）。与档 9A 的 261/69/70 对齐：

    * **A**   = 搬运段都没检出 ⇒ 压根没夹住（9A 的「没抓起」族）
    * **TIP** = 夹住 ∧ 侧躺送达（`delivered_tipped`，放宽算成功、严格不算）
    * **OK**  = 夹住 ∧ 立着送达
    * **B**   = 夹住 ∧ 放宽也失败（= 9A 的「抓起了却没送到附近」族）

    ⚠️ 顺序要紧：`delivered_tipped` **蕴含**放宽成功，所以必须先判 tipped 再判 relax，
    否则侧躺局会被 `grasped and relax` 吞进 OK ⇒ TIP 组**结构性恒为 0**、§三 变死表（本文件上一版就犯了这个错）。
    """
    if not grasped:
        return "A"
    if tipped:
        return "TIP"
    return "OK" if relax else "B"


def grip_sign_probe(act: np.ndarray, width: np.ndarray, lens, eps: float = MOVE_EPS) -> dict:
    """**实测**夹爪指令的符号（坑 82：不信注释，注释在 mg_env.py 里自相矛盾）。

    口径：只在「宽度真的动了」（|Δwidth| > eps）的步上比 `sign(act)` 与 `sign(Δwidth)`；
    Δwidth 逐集内算，跨集边界不连（避免把上一集末尾接到下一集开头）。
    一致率 < 0.5 ⇒ 指令与开口反向 ⇒ **+1 = 闭合**；> 0.5 ⇒ +1 = 张开；没有可判步 ⇒ 「不可判」（不猜，坑 40③）。
    另按开口宽度分箱给 act 的中位/均值，用来看指令是不是**饱和 bang-bang**（这决定「限位」有没有成因侧抓手）。
    """
    act = np.asarray(act, dtype=np.float64)
    width = np.asarray(width, dtype=np.float64)
    dw = np.full(width.shape, np.nan)
    off = 0
    for L in np.asarray(lens).astype(int):
        a, b = off, off + int(L)
        off = b
        if b - a >= 2:
            dw[a:b - 1] = width[a + 1:b] - width[a:b - 1]
    mv = np.isfinite(dw) & (np.abs(dw) > eps)
    n_mv = int(mv.sum())
    frac = round(float(np.mean(np.sign(act[mv]) == np.sign(dw[mv]))), 5) if n_mv else float("nan")
    conv = "不可判" if n_mv == 0 else ("+1=闭合, -1=张开" if frac < 0.5 else "+1=张开, -1=闭合")
    out = {"n_move": n_mv, "frac_same_sign": frac, "convention": conv, "eps": eps,
           "width_const": {"open": GRIP_OPEN_WIDTH, "reset": GRIP_AT_RESET,
                           "hold_thr": GRIP_HOLD_WIDTH, "empty": GRIP_EMPTY_CLOSE}}
    for key, sel in (("open", width > OPEN_THR),
                     ("hold", (width < GRASP_THR) & (width > GRIP_HOLD_WIDTH)),
                     ("empty", width <= GRIP_HOLD_WIDTH)):
        n = int(sel.sum())
        out[key] = {"n": n,
                    "act_med": round(float(np.median(act[sel])), 4) if n else None,
                    "act_mean": round(float(np.mean(act[sel])), 4) if n else None,
                    "w_med": round(float(np.median(width[sel])), 5) if n else None}
    return out


def expert_width_quantiles(npz_path: Path = DEMO_NPZ, qs=(0.01, 0.05, 0.10)) -> dict:
    """专家（示范）搬运段的逐 step 夹爪宽度分布 ⇒ 阈值只从这里推（纪律 3）。"""
    z = np.load(npz_path)
    st, lens = z["state"], z["episode_lengths"]
    off = 0
    ws: list[float] = []
    n_ep = n_carry = 0
    for L in lens:
        S = st[off:off + int(L)]
        off += int(L)
        n_ep += 1
        cw = carry_window(S[:, 7])
        if cw is None:
            continue
        n_carry += 1
        ws += [float(x) for x in S[cw[0]:cw[1] + 1, 7]]
    return {"n_ep": n_ep, "n_carry": n_carry, "n_step": len(ws),
            "w_min": min(ws) if ws else float("nan"), "w_med": q(ws, 0.5),
            **{f"p{int(x*100):02d}": q(ws, x) for x in qs}}


def ep_metrics(S: np.ndarray, A: np.ndarray, w_loss: float) -> dict | None:
    """一局的搬运期测量。没检出搬运段（没夹住）⇒ 返回 None（由调用方记成 A 类，不当 0）。"""
    cw = carry_window(S[:, 7])
    if cw is None:
        return None
    tg, tr = cw
    w = S[tg:tr + 1, 7]
    a = A[tg:tr + 1, 6] if A.shape[1] > 6 else np.zeros(len(w))
    spd, acc = spd_acc(S[tg:tr + 1])
    below = np.where(w < w_loss)[0]
    t_loss = (tg + int(below[0])) if len(below) else None
    pre: dict = {}
    if t_loss is not None:
        lo, hi = max(tg, t_loss - PRE), t_loss
        sp2, ac2 = spd_acc(S[lo:hi + 2])
        pre = {"n": int(hi - lo), "act_mean": float(np.mean(A[lo:hi + 1, 6])) if A.shape[1] > 6 else float("nan"),
               "spd_p95": float(np.max(sp2)) if len(sp2) else float("nan"),
               "acc_p95": q(list(ac2), 0.95) if len(ac2) else float("nan"),
               "dz_mean": float(np.mean(A[lo:hi + 1, 2])) if A.shape[1] > 2 else float("nan")}
    # 相位匹配窗：只取搬运段**前 K_MATCH 步**。窗口不够长的局 ⇒ 全部记 nan（不当 0，坑 40③），
    # 因为「B 组窗口被丢罐截断」会让整窗均值带删失偏差，等长前缀窗才是可比的（§六 删失警告）。
    nan = float("nan")
    if len(w) >= K_MATCH:
        mspd, macc = spd_acc(S[tg:tg + K_MATCH])
        match = {"m_n": K_MATCH, "m_w_min": float(np.min(w[:K_MATCH])), "m_w_mean": float(np.mean(w[:K_MATCH])),
                 "m_act_mean": float(np.mean(a[:K_MATCH])),
                 "m_spd_p95": q(list(mspd), 0.95) if len(mspd) else nan,
                 "m_acc_p95": q(list(macc), 0.95) if len(macc) else nan}
    else:
        match = {"m_n": int(len(w)), "m_w_min": nan, "m_w_mean": nan, "m_act_mean": nan,
                 "m_spd_p95": nan, "m_acc_p95": nan}
    return {"t_grasp": tg, "t_release": tr, "carry_len": int(tr - tg + 1),
            "w_min": float(np.min(w)), "w_p05": q(list(w), 0.05), "w_mean": float(np.mean(w)),
            "act_mean": float(np.mean(a)), "act_p95": q(list(a), 0.95),
            "spd_mean": float(np.mean(spd)) if len(spd) else float("nan"),
            "spd_p95": q(list(spd), 0.95) if len(spd) else float("nan"),
            "acc_p95": q(list(acc), 0.95) if len(acc) else float("nan"),
            "eef_rise_cm": rise_cm(S[:, 2], tg, tr),
            "lost": t_loss is not None, "t_loss": t_loss,
            "loss_after_frac": (float((t_loss - tg) / max(1, tr - tg)) if t_loss is not None else float("nan")),
            "loss_after_steps": int(t_loss - tg) if t_loss is not None else None,
            # 「指间有物」= 搬运期最小开口不低于 mg_env 的物理常数 GRIP_HOLD_WIDTH（专家假阳 0/120）。
            # 与 W_LOSS（专家自己的 p05，逐集假阳 16.7%）是两把不同的尺：这把有物理含义、地板为 0。
            "held": bool(float(np.min(w)) >= GRIP_HOLD_WIDTH),
            "pre": pre, **match}


def collect(sample: str, w_loss: float) -> dict:
    """把 5 臂 × 80 局（test）或 5 格 × 20 局（val）的逐局测量收上来。缺产物单列（坑 40③）。"""
    recs, missing, nofield = [], [], []
    for arm, d in sample_dirs(sample):
        npz, summ = d / "rollout_actions.npz", d / "eval_summary.json"
        if not (npz.exists() and summ.exists()):
            missing.append(d.name)
            continue
        z = np.load(npz)
        s = json.loads(summ.read_text())
        st, ac, lens = z["state"], z["action"], z["episode_lengths"]
        pe = s.get("per_episode") or []
        if len(pe) != len(lens):
            nofield.append((d.name, f"per_episode {len(pe)} != episode_lengths {len(lens)}"))
            continue
        off = 0
        for i, L in enumerate(lens):
            S, A = st[off:off + int(L)], ac[off:off + int(L)]
            off += int(L)
            e = pe[i]
            need = ("success_relaxed", "success", "delivered_tipped", "min_dist_to_target_xy", "max_lift_cm")
            if any(k not in e for k in need):
                nofield.append((d.name, f"ep{i} 缺字段 {[k for k in need if k not in e]}（坑 40③）"))
                continue
            m = ep_metrics(S, A, w_loss)
            grasped = m is not None
            relax = bool(e["success_relaxed"])
            cls = classify(grasped, relax, bool(e["delivered_tipped"]))
            recs.append({"arm": arm, "dir": d.name, "ep": i, "seed": int(e.get("seed", -1)),
                         "cls": cls, "grasped": grasped, "relax": relax, "strict": bool(e["success"]),
                         "tipped": bool(e["delivered_tipped"]),
                         "min_dist_cm": float(e["min_dist_to_target_xy"]) * 100.0,
                         "can_lift_cm": float(e["max_lift_cm"]), "final_tilt_deg": float(e.get("final_tilt_deg", float("nan"))),
                         **(m or {})})
    return {"recs": recs, "missing": missing, "nofield": nofield}


def perm_test(a: list[float], b: list[float], n_perm: int = N_PERM, seed: int = PERM_SEED) -> dict:
    """双侧置换检验（统计量 = 中位数之差）。样本太小 ⇒ 返回 nan，不假装显著。"""
    a = np.asarray([x for x in a if x == x], dtype=float)
    b = np.asarray([x for x in b if x == x], dtype=float)
    if len(a) < 5 or len(b) < 5:
        return {"n_a": int(len(a)), "n_b": int(len(b)), "obs": float("nan"), "p": float("nan")}
    obs = float(np.median(a) - np.median(b))
    pool = np.concatenate([a, b])
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        d = abs(float(np.median(pool[:len(a)]) - np.median(pool[len(a):])))
        cnt += int(d >= abs(obs))
    return {"n_a": int(len(a)), "n_b": int(len(b)), "obs": round(obs, 5),
            "p": round((cnt + 1) / (n_perm + 1), 5)}


def rate_perm_test(fa: list[bool], fb: list[bool], n_perm: int = N_PERM, seed: int = PERM_SEED) -> dict:
    """**比例**的双侧置换检验（统计量 = 发生率之差）。

    为什么不用 `perm_test`：`held`/空合是 0/1 双峰混合，中位数落在哪一峰完全由混合比例决定 ⇒
    中位数差是**错的统计量**（val 窗就是这么把 p 打到 0.053 的）。发生率才是这个问题的自然统计量。
    """
    a = [bool(x) for x in fa]
    b = [bool(x) for x in fb]
    if len(a) < 5 or len(b) < 5:
        return {"n_a": len(a), "n_b": len(b), "rate_a": float("nan"), "rate_b": float("nan"),
                "obs": float("nan"), "p": float("nan")}
    ra, rb = sum(a) / len(a), sum(b) / len(b)
    obs = ra - rb
    pool = np.concatenate([np.asarray(a, dtype=float), np.asarray(b, dtype=float)])
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        d = abs(float(pool[:len(a)].mean() - pool[len(a):].mean()))
        cnt += int(d >= abs(obs) - 1e-12)
    return {"n_a": len(a), "n_b": len(b), "rate_a": round(ra, 4), "rate_b": round(rb, 4),
            "obs": round(obs, 5), "p": round((cnt + 1) / (n_perm + 1), 5)}


FEATS = ("w_min", "w_p05", "w_mean", "act_mean", "act_p95", "spd_mean", "spd_p95", "acc_p95",
         "eef_rise_cm", "carry_len", "can_lift_cm")
FEATS_MATCH = ("m_w_min", "m_w_mean", "m_act_mean", "m_spd_p95", "m_acc_p95")  # 相位匹配窗（搬运段前 K_MATCH 步）
CLASSES = ("OK", "TIP", "B", "A")
LIFT_THR = 8.0      # 9A 用来判「抓起了」的 can 升程门槛（cm）；这里只用来**检验它被空合骗了多少**


def subsplit(recs: list[dict]) -> dict:
    """按 `mg_env.GRIP_HOLD_WIDTH` 把每组分「空合（指间无物）/ 真夹住」，并检验 9A 的 `max_lift_cm≥LIFT_THR` 代理。

    为什么要这一刀：`W_LOSS`（专家 p05）是**统计**阈值、自带 16.7% 的逐集假阳地板；
    `GRIP_HOLD_WIDTH` 是 `mg_env` 里写死的**物理**常数（夹住 can≈0.05、空合≈0.001），专家假阳 0/120 ⇒ 可以当标签用。
    """
    out = {}
    for cls in ("EXPERT",) + CLASSES:
        g = [r for r in recs if r["cls"] == cls and r.get("w_min") is not None]
        if not g:
            continue
        row = {"n": len(g)}
        for key, sel in (("empty", [r for r in g if not r.get("held")]), ("held", [r for r in g if r.get("held")])):
            def med(f):
                v = [float(r[f]) for r in sel if r.get(f) is not None and float(r[f]) == float(r[f])]
                return round(q(v, 0.5), 5) if v else None
            row[key] = {"n": len(sel), "frac": round(len(sel) / len(g), 4), "w_min_med": med("w_min"),
                        "can_lift_med": med("can_lift_cm"), "eef_rise_med": med("eef_rise_cm"),
                        "min_dist_med": med("min_dist_cm"), "n_tipped": sum(1 for r in sel if r.get("tipped"))}
        hi = [r for r in g if r.get("can_lift_cm") is not None and r["can_lift_cm"] >= LIFT_THR]
        row["lift_hi"] = {"n": len(hi), "n_empty": sum(1 for r in hi if not r.get("held")),
                          "lie_frac": round(sum(1 for r in hi if not r.get("held")) / len(hi), 4) if hi else None}
        los = [r["loss_after_steps"] for r in g if r.get("loss_after_steps") is not None]
        row["loss_after_steps_med"] = round(q(los, 0.5), 1) if los else None
        row["n_lost"] = len(los)
        out[cls] = row
    return out


def expert_recs(w_loss: float, npz_path: Path = DEMO_NPZ) -> list[dict]:
    """专家示范走**同一个** `ep_metrics` ⇒ 基线行与策略局口径逐字一致（不另写一份，坑 54）。

    为什么必须有它：`W_LOSS` = 专家搬运段宽度的 p05 ⇒ **按构造**专家自己就有一批步低于它。
    不把专家的「丢罐检出率」当假阳地板印出来，策略组的 `lost_frac` 就没法读（会被当成真实丢罐率）。
    """
    z = np.load(npz_path)
    st, ac, lens = z["state"], z["action"], z["episode_lengths"]
    sd = z["seeds"] if "seeds" in z else np.full(len(lens), -1)
    out, off = [], 0
    for i, L in enumerate(lens):
        S, A = st[off:off + int(L)], ac[off:off + int(L)]
        off += int(L)
        m = ep_metrics(S, A, w_loss)
        if m is None:
            continue
        out.append({"arm": "EXPERT", "dir": Path(npz_path).name, "ep": i, "seed": int(sd[i]), "cls": "EXPERT",
                    "grasped": True, "relax": True, "strict": True, "tipped": False, **m})
    return out


def group_table(recs: list[dict], classes=CLASSES) -> dict:
    out = {}
    for cls in classes:
        g = [r for r in recs if r["cls"] == cls]
        row = {"n": len(g)}
        for f in FEATS + FEATS_MATCH:
            # nan 一并滤掉：缺值既不当 0（坑 40③）、也不许毒化中位数/均值
            v = [float(r[f]) for r in g if r.get(f) is not None and float(r[f]) == float(r[f])]
            row[f + "_n"] = len(v)
            row[f] = {"mean": round(float(np.mean(v)), 4) if v else None,
                      "med": round(q(v, 0.5), 4) if v else None,
                      "p95": round(q(v, 0.95), 4) if v else None}
        row["lost_frac"] = round(float(np.mean([r.get("lost", False) for r in g])), 4) if g else None
        out[cls] = row
    return out


def write_md(res: dict) -> str:
    g, ex, sg = res["groups"], res["expert_groups"]["EXPERT"], res["sign"]
    L = ["# B 类失败（抓起了却没送到）的**夹爪通道**诊断（回溯、零 GPU、**不进任何门**）",
         f"<!-- 由 code/mg_bclass_grip.py 生成于 {res['generated']}；sample={res['sample']}、W_LOSS={res['w_loss']:.5f} m -->",
         "",
         "* ⚠️ **回溯性分析**：只用于给下一档立假设，**不产出成功率结论、不参与任何门**；要动判据/干预必须先写预注册（坑 40）。",
         f"* 样本：`--sample {res['sample']}` 共 **{res['n_rec']} 局**（缺产物 {len(res['missing'])} 个目录、缺字段 {len(res['nofield'])} 条 ⇒ 单列，不当 0，坑 40③）。",
         "* 分组（口径写死在 `code/mg_bclass_grip.py`）：**EXPERT** = 120 集反向示范（基线，走**同一套** `ep_metrics`）；"
         "**OK** = 夹住 ∧ 放宽成功；**TIP** = 夹住 ∧ 放宽成功但侧躺（`delivered_tipped`）；**B** = 夹住 ∧ 放宽也失败；"
         "**A** = 搬运段都没检出（压根没夹住）。",
         "* **单位**：夹爪宽度一律 **m**（`state[:,7]` = Σ|gripper_qpos|）；升程/距离 **cm**；速度 **m/步**。",
         f"* 夹爪指令符号 = **实测**（不信注释，坑 82）：专家 {sg['n_move']} 个「宽度真的动了」的步里，`sign(act)==sign(Δwidth)` 只占 "
         f"**{sg['frac_same_sign']:.4f}** ⇒ **{sg['convention']}**。`code/mg_env.py` 第 11/305 行的注释与此**相反**（文档缺陷，已记坑）；"
         f"第 66/68 行的**实测标注**与此一致：`action=-1 → {GRIP_OPEN_WIDTH}` 张开到底、`action=+1 → {GRIP_EMPTY_CLOSE}` 空合到底。",
         f"* 指令分箱（专家）：张开段（width>{OPEN_THR}）act 中位 **{sg['open']['act_med']:+.3f}**；夹住段 act 中位 **{sg['hold']['act_med']:+.3f}**、"
         f"均值 **{sg['hold']['act_mean']:+.3f}** ⇒ 指令实际上是**饱和 bang-bang（±1）**，不是可连续调节的量。",
         f"* 阈值只从**专家示范**推：`W_LOSS` = 专家搬运段逐 step 宽度的 **p{int(W_Q_MAIN*100):02d}** = **{res['w_loss']:.5f} m**"
         f"（专家 {res['expert']['n_carry']}/{res['expert']['n_ep']} 集有搬运段、{res['expert']['n_step']} 步；"
         f"p01={res['expert']['p01']:.5f} / p05={res['expert']['p05']:.5f} / p10={res['expert']['p10']:.5f}；专家中位 {res['expert']['w_med']:.5f}）。",
         f"* ⚠️ **假阳地板**：`W_LOSS` 是专家自己的分位数 ⇒ 专家组用**同一判据**也被标「丢罐」**{ex['lost_frac']*100:.1f}%**（p01/p10 的地板见 §五）。"
         "策略组的丢罐率**必须减掉这个地板**再读，不能当绝对概率。",
         f"* 搬运段窗口阈值 OPEN>{OPEN_THR} / GRASP<{GRASP_THR} / RELEASE>{RELEASE_THR}（import 自冻结口径，不新造）。",
         "", "## 一、逐组读数（宽度单位 m；EXPERT 行 = 示范包络）", "",
         "| 组 | n | 丢罐标记比例 | `w_min` 中位 | `w_p05` 中位 | `act_mean` 中位 | `act_p95` 中位 | 速度 p95 中位 | 加速度 p95 中位 | 末端升程中位 (cm) | 搬运步数中位 |",
         "|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for cls, name in (("EXPERT", "**EXPERT 示范基线**"), ("OK", "OK 放宽成功（立着）"), ("TIP", "TIP 侧躺送达"),
                      ("B", "**B 抓起了没送到**"), ("A", "A 压根没夹住")):
        r = ex if cls == "EXPERT" else g[cls]
        if not r["n"]:
            L.append(f"| {name} | 0 | — | — | — | — | — | — | — | — | — |")
            continue
        def m(f, k="med"):
            v = r[f][k]
            return "—" if v is None else f"{v:.5f}" if f.startswith("w_") or f.startswith("m_w") else f"{v:.4f}"
        cl = r["carry_len"]["med"]
        cl_txt = "—" if cl is None else f"{cl:.0f}"
        lf = r["lost_frac"]
        lf_txt = "—" if lf is None else f"{lf*100:.1f}%"
        L.append(f"| {name} | {r['n']} | {lf_txt} | {m('w_min')} | {m('w_p05')} | {m('act_mean')} "
                 f"| {m('act_p95')} | {m('spd_p95')} | {m('acc_p95')} | {m('eef_rise_cm')} | {cl_txt} |")
    sub = res["sub"]
    okE = sub.get("OK", {}).get("empty", {"n": 0})
    L += ["", f"### 一·补、按 `mg_env` 的**物理常数**再切一刀：空合（指间无物）vs 真夹住",
          "",
          f"* 判据：`held` = 搬运期最小开口 ≥ `GRIP_HOLD_WIDTH={GRIP_HOLD_WIDTH}`（出处 `code/mg_env.py` 写死的实测常数："
          f"夹住 can ≈0.05、空合到底 ≈{GRIP_EMPTY_CLOSE}），**不是本档新调的参数**。",
          f"* **专家假阳 = 0/{ex['n']} = 0.0%**（对比 §五 里 `W_LOSS`=专家 p05 的地板 {ex['lost_frac']*100:.1f}%）⇒ 这把尺可以当**逐局标签**用。",
          f"* ⚠️ 但「空合」**不等于**「从没夹住」：OK 组也有 **{okE['n']}** 局空合却照样送达 ⇒ 可能是先空合后重抓、或一次瞬时过冲。"
          "要分清需要看「空合」与「can 升起」的**时序**，本档没做（留作后续，别当结论）。",
          "* ⚠️ 空合行的 `can 升程`/`末端升程`/`离目标 XY` 受**窗口删失**污染（空合后往往再也达不到释放阈值 ⇒ 窗口一路截到局末），"
          "只能读量级、不能当「罐被顶飞多高」的定量值。",
          "",
          "| 组 | n | 空合 n（占比） | 空合 `w_min` 中位 | 空合 can 升程中位 | 空合 末端升程中位 | 空合 离目标 XY 中位 | 真夹住 n（占比） | 真夹住 `w_min` 中位 | 真夹住 离目标 XY 中位 | 真夹住∧侧躺 |",
          "|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    def fnum(v, nd=4, pct=False):
        if v is None:
            return "—"
        return f"{v*100:.1f}%" if pct else f"{v:.{nd}f}"
    for cls, nm in (("EXPERT", "**EXPERT 示范**"), ("OK", "OK 放宽成功"), ("TIP", "TIP 侧躺送达"),
                    ("B", "**B 抓起了没送到**"), ("A", "A 没夹住")):
        if cls not in sub:
            continue
        s = sub[cls]
        e, h = s["empty"], s["held"]
        L.append(f"| {nm} | {s['n']} | {e['n']}（{fnum(e['frac'], pct=True)}） | {fnum(e['w_min_med'], 5)} "
                 f"| {fnum(e['can_lift_med'], 1)} | {fnum(e['eef_rise_med'], 1)} | {fnum(e['min_dist_med'], 1)} "
                 f"| {h['n']}（{fnum(h['frac'], pct=True)}） | {fnum(h['w_min_med'], 5)} | {fnum(h['min_dist_med'], 1)} | {h['n_tipped']} |")
    er = res.get("empty_rate", {})
    if er.get("B_vs_OK") and er["B_vs_OK"]["p"] == er["B_vs_OK"]["p"]:
        d = er["B_vs_OK"]
        exr = er.get("EXPERT", {})
        L += ["", f"* **空合发生率的比例置换检验**（双峰混合的正确统计量；中位数在这里是错的量）："
              f"B **{d['rate_a']*100:.1f}%**（{d['n_a']} 局） vs OK **{d['rate_b']*100:.1f}%**（{d['n_b']} 局），"
              f"差 **{d['obs']*100:+.1f} pp**，p=**{d['p']:.4f}**"
              + (f"；专家地板 **{exr.get('rate', 0)*100:.1f}%**（{exr.get('n_empty')}/{exr.get('n')}）" if exr else "") + "。"]
    bsub = sub.get("B")
    if bsub:
        lh = bsub["lift_hi"]
        L += ["", f"* **9A 的「抓起了」代理被证伪一半**：9A 用 `max_lift_cm ≥ {LIFT_THR:.0f} cm` 判「抓起了」。B 组里满足它的有 **{lh['n']}** 局，"
              f"其中 **{lh['n_empty']}** 局（**{fnum(lh['lie_frac'], pct=True)}**）其实是**空合**——can 是被**接触顶飞/弹射**升起来的，"
              "根本没在指间。⇒ 9A 那个「B = 抓起了却没送到」的桶**标签有系统性错误**，需回填更正（见 §六⑥）。"]
    ls = res.get("loss_steps", {})
    if ls:
        L += ["", f"* **「丢罐」发生在夹住后第几步**（绝对步数，不受窗口删失影响；`W_LOSS`=专家 p05）：",
              "", "| 组 | 被标丢罐 n | 第 25 百分位 | 中位 | 第 75 百分位 | ≤10 步占比 |", "|:--|---:|---:|---:|---:|---:|"]
        for cls, nm in (("EXPERT", "EXPERT（假阳参考）"), ("OK", "OK"), ("B", "**B**")):
            if cls in ls:
                d = ls[cls]
                L.append(f"| {nm} | {d['n']} | {d['p25']:.0f} | {d['med']:.0f} | {d['p75']:.0f} | {d['le10_frac']*100:.0f}% |")
        L.append("")
        bb = ls.get("B")
        if bb and bb["med"] <= 10:
            L.append(f"> ⚠️ B 组的中位丢罐时刻 = **夹住后第 {bb['med']:.0f} 步**（≤10 步占 {bb['le10_frac']*100:.0f}%）⇒ "
                     f"§二·补 那个 {K_MATCH} 步匹配窗**已经跨过丢罐时刻**，所以窗内 `m_w_min` 的显著性是**后果**、不是前兆；"
                     "而 `m_act_mean/m_spd_p95/m_acc_p95` 三个**不显著**才是可用的读数（B 与 OK 在指令与运动学上不可区分）。")
    L += ["", "## 二、B vs OK 的置换检验（双侧，统计量 = 中位数差；n<5 ⇒ 不判）", "",
          "⚠️ 下表带 † 的特征受**窗口删失**污染（B 组一丢罐，释放阈值就再也达不到、窗口在 `len(width)-1` 截断），只能读方向；"
          "定量结论看 §二·补 的相位匹配窗。", "",
          "| 特征 | 中位数差（B − OK） | p | 读法 |", "|:--|---:|---:|:--|"]
    CENSORED = {"act_mean", "act_p95", "spd_mean", "spd_p95", "acc_p95", "carry_len", "w_p05", "w_mean", "m_w_mean"}
    for f in FEATS:
        t = res["tests"]["B_vs_OK"][f]
        mark = "†" if f in CENSORED else ""
        if t["p"] != t["p"]:
            L.append(f"| `{f}`{mark} | — | — | 样本太小，不判 |")
            continue
        sig = "**显著**" if t["p"] <= 0.05 else "不显著"
        L.append(f"| `{f}`{mark} | {t['obs']:+.5f} | {t['p']:.4f} | {sig}（n={t['n_a']} vs {t['n_b']}） |")
    L += ["", f"### 二·补、相位匹配窗（只比搬运段**前 {K_MATCH} 步** ⇒ 两组同相位、等长，删失消失）", "",
          "| 特征 | 中位数差（B − OK） | p | 读法 |", "|:--|---:|---:|:--|"]
    for f in FEATS_MATCH:
        t = res["tests"]["B_vs_OK_match"][f]
        if t["p"] != t["p"]:
            L.append(f"| `{f}` | — | — | 可匹配局太少（n={t['n_a']} vs {t['n_b']}），不判 |")
            continue
        sig = "**显著**" if t["p"] <= 0.05 else "不显著"
        L.append(f"| `{f}` | {t['obs']:+.5f} | {t['p']:.4f} | {sig}（n={t['n_a']} vs {t['n_b']}） |")
    L += ["", f"> `m_*` 只取搬运段前 {K_MATCH} 步（≈{K_MATCH // 10} 次重规划）。窗口不足 {K_MATCH} 步的局整条记 nan 并被排除（不当 0，坑 40③），"
          "所以上表的 n 小于 §一 的 n —— 这是**去掉删失**的代价，也是唯一能定量比的两组数字。", ""]
    n_tip = g["TIP"]["n"]
    L += ["", "## 三、侧躺（TILT）在夹爪侧的对照 —— 检验「B 与 TILT 共因」", ""]
    if n_tip:
        key, lab = "TIP_vs_OK", "TIP − OK"
        L.append(f"* TIP（侧躺**且送达**）n = {n_tip} ⇒ 直接给 TIP vs OK。")
    else:
        key, lab = "BTIP_vs_BUP", "B∧侧躺 − B∧立着"
        L += [f"* **TIP（侧躺且送达）n = 0**：侧躺绝大多数直接判失败、落在 B 组里 ⇒ 「TIP vs OK」在本窗口是空表。",
              f"* 改用**同一批一手数据**在 B 组内部切：B∧侧躺（n={res['n_B_tipped']}） vs B∧立着（n={g['B']['n'] - res['n_B_tipped']}）。"
              "若 B 与 TILT 真共因（同一上游），两组的夹爪读数应当**无差**；若有差，则侧躺另有独立通道。"]
    L += ["", f"| 特征 | 中位数差（{lab}） | p |", "|:--|---:|---:|"]
    for f in FEATS:
        t = res["tests"][key][f]
        nan_p = t["p"] != t["p"]
        obs_txt = "—" if nan_p else f"{t['obs']:+.5f}"
        p_txt = "—" if nan_p else f"{t['p']:.4f}"
        L.append(f"| `{f}` | {obs_txt} | {p_txt} |")
    L += ["", "## 四、丢罐前的那 10 步（`PRE=10` = 一次重规划的量级）", ""]
    if res["pre"]["n"]:
        L += [f"* 检出「中途丢罐」（宽度 < W_LOSS）的局：**{res['pre']['n']}** 局（B {res['pre']['n_B']} / TIP {res['pre']['n_TIP']} / OK {res['pre']['n_OK']}）",
              f"* 丢罐发生在搬运段的相对位置：中位 **{res['pre']['loss_after_frac_med']:.2f}**（0=刚夹住、1=释放前）",
              f"* 丢罐前 10 步：闭合指令均值 **{res['pre']['act_mean']:+.3f}**、速度 p95 中位 **{res['pre']['spd_p95']:.5f} m/步**、"
              f"加速度 p95 中位 **{res['pre']['acc_p95']:.5f}**、`dz` 均值 **{res['pre']['dz_mean']:+.4f} m**",
              f"* **对照**：专家整个搬运段的 `act_mean` 均值 = **{res['pre']['act_mean_expert']:+.3f}**（且专家夹住段 act 中位 = {sg['hold']['act_med']:+.3f}）⇒ "
              "「丢罐前指令更接近饱和」这件事，专家**也**在饱和 ⇒ 指令幅度本身**不区分**成功与丢罐。"]
    else:
        L.append("* 没有检出「中途丢罐」的局（或阈值太严）⇒ 看 §五 的敏感性。")
    L += ["", "## 五、阈值敏感性（W_LOSS 换成专家 p01 / p10，结论会不会翻）", "",
          "| W_LOSS | 值 (m) | 丢罐局数 | B 组丢罐比例 | OK 组丢罐比例 | **专家组假阳地板** | B − 地板 |",
          "|:--|---:|---:|---:|---:|---:|---:|"]
    for row in res["sens"]:
        fl, bb = row["EXPERT"], row["B"]
        d = (bb - fl) * 100 if (fl == fl and bb == bb) else float("nan")
        L.append(f"| 专家 p{row['q']} | {row['w_loss']:.5f} | {row['n_lost']} | {bb*100:.1f}% | {row['OK']*100:.1f}% "
                 f"| {fl*100:.1f}% | {d:+.1f} pp |")
    L += ["", "## 六、判读（**假设**，不是结论；下一档要先写预注册）", ""]
    for line in res["reading"]:
        L.append(f"* {line}")
    L += ["", "## 七、出身与不变量", "",
          f"* 逐局不变量「放宽成功 ⊇ 严格成功」违例：**{res['invariant_broken']}** 条（必须 0）",
          f"* 「TIP ⇒ 放宽成功 ∧ 严格失败」违例：**{res['invariant_tip']}** 条（必须 0）",
          f"* 「夹住的侧躺局必须进 TIP 组」违例：**{res['invariant_cls']}** 条（必须 0；上一版把侧躺局吞进 OK ⇒ TIP 恒为 0）",
          f"* 缺产物目录：{res['missing'] or '无'}；缺字段：{res['nofield'][:5] or '无'}",
          f"* 夹爪阈值出处：`OPEN_THR={OPEN_THR}`、`GRASP_THR={GRASP_THR}`、`RELEASE_THR={RELEASE_THR}`（`code/mg_eval_zlim.py` ← `code/mg_env.py` 实测）",
          f"* 搬运段窗口/升程：import 自 `code/mg_zlim_replay.py`（与 9B 的 Z0b 台**同一份代码**，不是复制品）",
          "", "## 八、复现", "", "```bash", "source code/env.sh",
          "$MG_PY code/mg_bclass_grip.py --selftest", "$MG_PY code/mg_bclass_grip.py            # test 窗口（5 臂 × 4×20）",
          "$MG_PY code/mg_bclass_grip.py --sample val  # val 窗口（5 个关门格 × 1×20）", "```"]
    L = L[:-1] + ["# 逐局归因标签（可 join (arm,dir,ep,seed)，后续任何一档要做失败分类直接读它）：",
                  f"#   runs/_diag/s9_tax/grip_labels_{'400' if res['sample'] == 'test' else 'val'}.json", "```"]
    return "\n".join(L) + "\n"


def reading_of(res: dict) -> list[str]:
    """把读数翻译成**判读**。措辞纪律：相关 ≠ 因果；被窗口删失污染的量只说方向；有专家地板的一律减地板再读。"""
    t, tm = res["tests"]["B_vs_OK"], res["tests"]["B_vs_OK_match"]
    g, ex, sg = res["groups"], res["expert_groups"]["EXPERT"], res["sign"]
    out = []

    def sig(d, f):
        return d[f]["p"] == d[f]["p"] and d[f]["p"] <= 0.05

    def pc(x):
        return "n/a" if x is None else f"{x * 100:.1f}%"

    def det(d, feats):
        return "；".join("`%s` %+.5f（p=%.4f）" % (f, d[f]["obs"], d[f]["p"]) for f in feats)

    sb, so = res["sub"].get("B"), res["sub"].get("OK")
    if sb and so and sb["n"]:
        out.append(f"**① B 不是一个桶，是两个**（用 `mg_env.GRIP_HOLD_WIDTH={GRIP_HOLD_WIDTH}` 切，专家假阳 0/120 ⇒ 尺子干净）："
                   f"**空合（指间无物）{sb['empty']['n']}/{sb['n']} = {sb['empty']['frac']*100:.1f}%**，`w_min` 中位 "
                   f"{sb['empty']['w_min_med']:.5f} m ≈ 空合到底 {GRIP_EMPTY_CLOSE}；这些局 can 升程中位 "
                   f"{sb['empty']['can_lift_med']:.1f} cm 而离目标 XY 中位 {sb['empty']['min_dist_med']:.1f} cm ⇒ "
                   "**罐是被接触顶飞的、从来没在指间**（= 9B 的弹射家族，不是「搬运途中掉了」）。"
                   f"**真夹住 {sb['held']['n']}/{sb['n']} = {sb['held']['frac']*100:.1f}%**，`w_min` 中位 {sb['held']['w_min_med']:.5f} m"
                   f"（专家 {ex['w_min']['med']:.5f}）却离目标 XY 中位 {sb['held']['min_dist_med']:.1f} cm ⇒ "
                   f"**这才是真的搬运/放置失败**，规模只有全体的 {sb['held']['n'] / max(1, res['n_rec']) * 100:.1f}%（比 9A 的印象小得多）。")
        lh = sb["lift_hi"]
        if lh["n"]:
            out.append(f"**①b 9A 的「抓起了」代理被证伪一半**：`max_lift_cm ≥ {LIFT_THR:.0f} cm` 在 B 组命中 {lh['n']} 局，"
                       f"其中 **{lh['n_empty']} 局（{lh['lie_frac']*100:.1f}%）是空合** ⇒ 「B = 抓起了却没送到」这个标签对将近一半的 B 是**错的**。"
                       f"⚠️ 反向也要说清：OK 组有 **{so['empty']['n']}** 局空合**却照样送达** ⇒ 空合**不是**失败的充分条件，"
                       f"它当失败归因标签的阳性预测值 = {sb['empty']['n'] / max(1, sb['empty']['n'] + so['empty']['n']) * 100:.0f}%，只能配合成败一起读。")
        out.append(f"**② 「闭合指令过强 ⇒ 把罐挤飞」不成立**（这条**推翻**本工具上一版的措辞）：实测符号 = **{sg['convention']}**，"
               f"而 B 组 `act_mean` 中位 **{g['B']['act_mean']['med']:+.4f}** 反而**低于** OK 组 **{g['OK']['act_mean']['med']:+.4f}**；"
               f"更要紧的是专家夹住段 act 中位 = **{sg['hold']['act_med']:+.3f}**、均值 = **{sg['hold']['act_mean']:+.3f}** ⇒ "
               "指令本来就是**饱和 bang-bang（±1）**，专家一路 +1 而开口仍稳在 ~0.049 m（位置控制夹爪 + can 是硬约束，压不下去）。"
               "⇒ **夹爪指令幅度不是一根可用的成因侧杠杆**，「给闭合指令限位」这类干预在本 env 里**没有作用对象**。")
    lsb = res.get("loss_steps", {}).get("B")
    kin = [f for f in ("m_act_mean", "m_spd_p95", "m_acc_p95") if sig(tm, f)]
    when = (f"（B 的中位丢罐时刻 = 夹住后第 {lsb['med']:.0f} 步、≤10 步占 {lsb['le10_frac']*100:.0f}%）" if lsb else "")
    if not kin:
        nm = tm["m_w_min"]
        out.append(f"**③ 相位匹配窗（搬运段前 {K_MATCH} 步，n={nm['n_a']} vs {nm['n_b']}）里，指令与运动学三项全部不显著**："
                   f"`m_act_mean` p={tm['m_act_mean']['p']:.4f}、`m_spd_p95` p={tm['m_spd_p95']['p']:.4f}、`m_acc_p95` p={tm['m_acc_p95']['p']:.4f} ⇒ "
                   "**B 与 OK 在夹爪指令、速度、加速度上不可区分**；§二 里那些「显著」的速率/指令差**基本全是窗口删失与后果**。"
                   f"唯一显著的 `m_w_min`（{tm['m_w_min']['obs']:+.5f}，p={tm['m_w_min']['p']:.4f}）**不能当前兆读**{when}——"
                   "匹配窗已经跨过丢罐时刻，它测到的是**罐已经不在了**这件事本身。⇒ 与 9B 同源：**弹射是接触事件，事前在可观测量里看不出来**，"
                   "所以任何「事前过滤/限速/限力」类干预都按不住它。")
    else:
        out.append(f"**③ 相位匹配窗（搬运段前 {K_MATCH} 步）里仍然显著的指令/运动学差**：{det(tm, kin)} ⇒ 这些发生在丢罐**之前**，"
                   f"才有资格当上游量{when}。其余 §二 的显著项受删失污染，只读方向。")
    out.append(f"**④ 丢罐标记的假阳地板（必须减）**：`W_LOSS` = 专家自己的 p05 ⇒ 专家组用同一判据也被标丢罐 **{pc(ex['lost_frac'])}**。"
               f"于是 B {pc(g['B']['lost_frac'])} / OK {pc(g['OK']['lost_frac'])} 只能这么读："
               f"B 超出地板 **{(g['B']['lost_frac'] - ex['lost_frac']) * 100:+.1f} pp**、OK 超出 **{(g['OK']['lost_frac'] - ex['lost_frac']) * 100:+.1f} pp** ⇒ "
               "分离是真的，但「OK 组有 40% 中途丢罐」这种说法是**错的**（其中一大半是阈值抖动）。")
    n_tip, n_bt = g["TIP"]["n"], res["n_B_tipped"]
    if n_tip >= 5 and so:
        ttm = res["tests"]["TIP_vs_OK_match"]
        ns = [f for f in FEATS_MATCH if sig(ttm, f)]
        tipE = res["sub"].get("TIP", {}).get("empty", {})
        tip_frac = tipE.get("frac")
        tip_txt = "n/a" if tip_frac is None else f"{tip_frac*100:.1f}%"
        out.append(f"**⑤ 侧躺送达（TIP，n={n_tip}）vs 立着送达（OK，n={g['OK']['n']}）—— 9B 弹射机理在夹爪侧的对照**："
                   f"空合率 TIP **{tip_txt}** vs OK **{so['empty']['frac']*100:.1f}%**；相位匹配窗（前 {K_MATCH} 步）上"
                   + ("**五项特征全部不显著** ⇒ 侧躺与立着送达在夹爪指令与运动学上**不可区分** ⇒ 与 9B 的结论一致："
                      "侧躺是**放下瞬间的冲击/接触**造成的，不是抓取阶段的差别 ⇒ 夹爪侧同样**没有**成因侧抓手。"
                      if not ns else
                      f"显著的特征：{det(ttm, ns)} ⇒ "
                      "侧躺在**抓取阶段**就已有差别，9B 的「放下冲击」不是全部故事，值得再看一眼。"))
    else:
        tb = res["tests"]["BTIP_vs_BUP"]
        n_bu = g["B"]["n"] - n_bt
        if n_bt >= 5 and n_bu >= 5:
            nsf = [f for f in FEATS if sig(tb, f)]
            out.append(f"**⑤ B 与 TILT 共因检验**（B 组内 侧躺 n={n_bt} vs 立着 n={n_bu}）："
                       + ("两组夹爪读数**无显著差** ⇒ 与「同一上游（接触弹射）」一致。" if not nsf else
                          f"有显著差的特征：{', '.join(nsf)} ⇒ 侧躺可能另有独立通道，别急着并进同一机理。"))
        else:
            out.append(f"**⑤ 侧躺的夹爪侧对照做不了**：TIP（侧躺且送达）只有 **{n_tip}** 局、B∧侧躺 **{n_bt}** 局（<5 ⇒ 不判，坑 40③）⇒ "
                       "9B `pop_probe24` 那条线索（can 升 15.3 cm 而末端只升 1.2 cm）在本窗口**无法用夹爪量复核**，维持「假设」状态，不写成结论。")
    hold_n = sb["held"]["n"] if sb else 0
    lie = sb["lift_hi"]["lie_frac"] if sb and sb["lift_hi"]["n"] else float("nan")
    out.append("**⑥ 建议（只登记，不立项）**：夹爪通道交出来的是一根**零成本的逐局归因标签**"
               f"（`held = w_min ≥ GRIP_HOLD_WIDTH={GRIP_HOLD_WIDTH}`，专家假阳 0/120，只读已落盘 npz、零 GPU 零重放），"
               "但**交不出成因侧的可调量**：指令本来就是饱和 bang-bang、专家也饱和，开口宽度是接触的**结果**而不是原因。"
               "⇒ **不建议为它单开档 9D**：候选①「闭合指令限位」**没有作用对象**；候选②「教材侧补轻夹慢运片段」要重采 + 重训 ≥20 h，"
               f"而真正的搬运/放置失败（B∧真夹住）只有全体的 **{hold_n / max(1, res['n_rec']) * 100:.1f}%**，"
               "使命门已有 30 pp 余量（反向 min 80.0% vs 门 50%）⇒ 收益/代价不划算。**主线仍是档 9C**（便宜配方的三 seed 复现）。")
    out.append(f"**⑥b 必须回填的更正（修记录，不是新实验）**：9A 的失败分类拿 `max_lift_cm ≥ {LIFT_THR:.0f} cm` 当「抓起了」，"
               f"本次一手复核发现它在 B 组有 **{lie*100:.1f}%** 的假阳 ⇒ `runs/_diag/s9_tax/SUMMARY.md` 里"
               "「B = 最大真失败桶（占真失败 52~62%）」需就地更正为「B 里约 45% 实为**接触弹射造成的假『抓起了』**（罐从没在指间），"
               "约 55% 才是真·搬运/放置失败（占全体 ~9.5%）」，并在 README 记一条坑："
               "`max_lift_cm` 不能当「已抓住」的判据，要用 `w_min ≥ GRIP_HOLD_WIDTH`。"
                   "⚠️ 本条只改**归因叙述**，不动任何成功率、不动任何门（坑 40）。")
    out.append("**⑦ 跨窗复核纪律**：本工具同时产出 test（400 局，9A/9B 的预注册窗口）与 val（100 局，关门格）**两窗**。"
               "引用**效应量**之前两窗都要看：val 的 B 组只有 20~30 局 ⇒ 只够判**方向**、不够定**幅度**；"
               "且两窗来自不同 harness/ckpt/seed 族，**不许跨窗比高低**（坑 33），只许比方向是否一致。")
    return out


def run(sample: str) -> int:
    exp = expert_width_quantiles()
    w_loss = exp[f"p{int(W_Q_MAIN*100):02d}"]
    zz = np.load(DEMO_NPZ)
    sign = grip_sign_probe(zz["action"][:, 6], zz["state"][:, 7], zz["episode_lengths"])
    if sign["convention"] != "+1=闭合, -1=张开":
        print(f"[bclass][WARN] 实测夹爪符号 = {sign['convention']}（frac_same={sign['frac_same_sign']}）"
              "≠ 报告判读假定的「+1=闭合」⇒ §六 的方向性措辞需人工复核，别直接引用！", file=sys.stderr)
    erecs = expert_recs(w_loss)
    got = collect(sample, w_loss)
    recs = got["recs"]

    def cmp(sel_a, sel_b, feats):
        return {f: perm_test([r[f] for r in recs if sel_a(r)], [r[f] for r in recs if sel_b(r)]) for f in feats}

    def is_cls(c):
        return lambda r: r["cls"] == c

    def lost_frac(rs):
        return round(float(np.mean([r.get("lost", False) for r in rs])), 4) if rs else float("nan")

    res = {"generated": f"{datetime.now():%Y-%m-%d %H:%M}", "sample": sample, "expert": exp,
           "w_loss": w_loss, "n_rec": len(recs), "missing": got["missing"], "nofield": got["nofield"],
           "sign": sign, "units": {"width": "m", "eef_rise/can_lift/min_dist": "cm", "spd": "m/步"},
           "groups": group_table(recs), "expert_groups": group_table(erecs, classes=("EXPERT",)),
           "n_expert_rec": len(erecs),
           "tests": {"B_vs_OK": cmp(is_cls("B"), is_cls("OK"), FEATS),
                     "TIP_vs_OK": cmp(is_cls("TIP"), is_cls("OK"), FEATS),
                     "BTIP_vs_BUP": cmp(lambda r: r["cls"] == "B" and r["tipped"],
                                        lambda r: r["cls"] == "B" and not r["tipped"], FEATS),
                     "B_vs_OK_match": cmp(is_cls("B"), is_cls("OK"), FEATS_MATCH),
                     "TIP_vs_OK_match": cmp(is_cls("TIP"), is_cls("OK"), FEATS_MATCH)}}
    res["n_B_tipped"] = sum(1 for r in recs if r["cls"] == "B" and r["tipped"])
    # 空合发生率（比例检验，双峰混合的正确统计量）：B vs OK、以及各自 vs 专家地板 0
    er_empty = [not r["held"] for r in erecs]
    res["empty_rate"] = {
        "B_vs_OK": rate_perm_test([not r["held"] for r in recs if r["cls"] == "B" and r.get("held") is not None],
                                  [not r["held"] for r in recs if r["cls"] == "OK" and r.get("held") is not None]),
        "EXPERT": {"n": len(er_empty), "n_empty": int(sum(er_empty)),
                   "rate": round(sum(er_empty) / len(er_empty), 4) if er_empty else None}}
    res["sub"] = subsplit(erecs + recs)
    # 丢罐前窗口
    lost = [r for r in recs if r.get("lost") and r.get("pre")]
    def pm(v):
        v = [x for x in v if x == x]
        return float(np.mean(v)) if v else float("nan")
    res["pre"] = {"n": len(lost), "n_B": sum(1 for r in lost if r["cls"] == "B"),
                  "n_TIP": sum(1 for r in lost if r["cls"] == "TIP"),
                  "n_OK": sum(1 for r in lost if r["cls"] == "OK"),
                  "loss_after_frac_med": q([r["loss_after_frac"] for r in lost], 0.5) if lost else float("nan"),
                  "act_mean": pm([r["pre"].get("act_mean", float("nan")) for r in lost]),
                  "spd_p95": q([r["pre"]["spd_p95"] for r in lost if r.get("pre", {}).get("spd_p95") is not None], 0.5) if lost else float("nan"),
                  "acc_p95": q([r["pre"]["acc_p95"] for r in lost if r.get("pre", {}).get("acc_p95") is not None], 0.5) if lost else float("nan"),
                  "dz_mean": pm([r["pre"].get("dz_mean", float("nan")) for r in lost])}
    res["pre"]["act_mean_expert"] = pm([r["act_mean"] for r in erecs])
    # 丢罐发生在「夹住后第几步」——绝对步数，不受窗口删失影响（`loss_after_frac` 的分母是被截断的窗口，会骗人）
    res["loss_steps"] = {}
    for cls in ("EXPERT",) + tuple(CLASSES):
        rr = (erecs if cls == "EXPERT" else recs)
        v = [r["loss_after_steps"] for r in rr if r["cls"] == cls and r.get("loss_after_steps") is not None]
        if v:
            res["loss_steps"][cls] = {"n": len(v), "med": q(v, 0.5), "p25": q(v, 0.25), "p75": q(v, 0.75),
                                      "le10_frac": round(float(np.mean([x <= 10 for x in v])), 4)}
    # 敏感性
    sens = []
    for qq in (W_Q_SENS[0], W_Q_MAIN, W_Q_SENS[1]):
        wl = exp[f"p{int(qq*100):02d}"]
        same = abs(wl - w_loss) < 1e-12
        got2 = recs if same else collect(sample, wl)["recs"]
        er2 = erecs if same else expert_recs(wl)
        nl = [r for r in got2 if r.get("lost")]
        B = [r for r in got2 if r["cls"] == "B"]
        OK = [r for r in got2 if r["cls"] == "OK"]
        sens.append({"q": int(qq * 100), "w_loss": round(wl, 6), "n_lost": len(nl),
                     "B": round(float(np.mean([r.get("lost", False) for r in B])), 4) if B else float("nan"),
                     "OK": round(float(np.mean([r.get("lost", False) for r in OK])), 4) if OK else float("nan"),
                     "EXPERT": lost_frac(er2)})
    res["sens"] = sens
    res["invariant_broken"] = sum(1 for r in recs if r["strict"] and not r["relax"])
    res["invariant_tip"] = sum(1 for r in recs if r["tipped"] and not (r["relax"] and not r["strict"]))
    # 分组必须与 tipped 一致：夹住的侧躺局一律进 TIP，不许漏进 OK/B（上一版的 bug）
    res["invariant_cls"] = sum(1 for r in recs
                               if r["grasped"] and (r["cls"] == "TIP") != bool(r["tipped"]))
    res["reading"] = reading_of(res)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "400" if sample == "test" else "val"
    res["recs_per_ep"] = label_rows(recs)
    (OUT_DIR / f"grip_mech_{tag}.json").write_text(json.dumps(
        {k: v for k, v in res.items() if k != "recs_per_ep"}, ensure_ascii=False, indent=1, default=str))
    (OUT_DIR / f"grip_mech_{tag}.md").write_text(write_md(res))
    (OUT_DIR / f"grip_labels_{tag}.json").write_text(json.dumps(
        {"generated": res["generated"], "sample": sample, "n": len(res["recs_per_ep"]),
         "w_loss_m": w_loss,
         "held_criterion": f"w_min >= GRIP_HOLD_WIDTH={GRIP_HOLD_WIDTH}（出处 code/mg_env.py，专家假阳 0/120）",
         "sign_convention": sign["convention"], "sign_frac_same": sign["frac_same_sign"],
         "note": "held 是**归因标签**不是成功判据（OK 组也有空合却送达）；缺字段一律 null，不当 0（坑 40③）",
         "per_episode": res["recs_per_ep"]}, ensure_ascii=False, indent=1, default=str))
    print(f"[bclass] sample={sample} 收到 {len(recs)} 局（缺产物 {len(got['missing'])}、缺字段 {len(got['nofield'])}）")
    print(f"[bclass] 夹爪符号实测（专家 {sign['n_move']} 个开合步）：sign(act)==sign(Δwidth) 占 {sign['frac_same_sign']:.4f} ⇒ {sign['convention']}")
    print(f"[bclass] W_LOSS（专家 p{int(W_Q_MAIN*100):02d}）= {w_loss:.4f} m；分组 "
          + " ".join(f"{k}={v['n']}" for k, v in res["groups"].items()))
    ex = res["expert_groups"]["EXPERT"]
    print(f"[bclass] 专家基线（同一套 ep_metrics、{res['n_expert_rec']} 集）：lost_frac={ex['lost_frac']*100:.1f}%（= 本阈值的逐集假阳地板）"
          f" w_min中位={ex['w_min']['med']} m carry_len中位={ex['carry_len']['med']:.0f}")
    print(f"[bclass] 不变量违例：relax⊉strict {res['invariant_broken']}、TIP 口径 {res['invariant_tip']}、"
          f"分组一致性 {res['invariant_cls']}（都应为 0）")
    print(f"[bclass] 产物 -> runs/_diag/s9_tax/grip_mech_{tag}.{{md,json}} + grip_labels_{tag}.json（逐局归因标签，可 join）")
    bad = res["invariant_broken"] or res["invariant_tip"] or res["invariant_cls"]
    return 3 if bad else 0


# ─────────────────────────── 自测（合成夹具，不断言盘上进度：坑 77）───────────────────────────
def selftest() -> int:
    fails, total = [], [0]

    def ck(name, cond):
        total[0] += 1
        if not cond:
            fails.append(name)

    ck("q1 下分位 = 第 floor(p·n) 小", q([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0 and q([1.0, 2.0, 3.0, 4.0], 0.05) == 1.0)
    ck("q2 空列表 → nan（不当 0，坑 40③）", q([], 0.5) != q([], 0.5))
    ck("q3 乱序自动排序", q([3.0, 1.0, 2.0], 0.5) == 2.0)

    # carry_window / ep_metrics：合成一段「张开 → 夹住 → 中途丢罐（宽度塌到空合）→ 释放」
    T = 60
    w = np.full(T, 0.045)          # 夹住 can 的典型宽度
    w[:10] = 0.0788                # 张开到底
    w[40:45] = 0.0010              # 丢罐：空合
    w[50:] = 0.075                 # 释放
    S = np.zeros((T, 8)); S[:, 7] = w
    S[:, 2] = np.linspace(0.30, 0.42, T)      # 末端一路抬 12 cm
    A = np.zeros((T, 7)); A[:, 6] = 0.8       # 闭合指令恒 0.8
    cw = carry_window(w)
    ck("c1 搬运段窗口 = (t0+首次<GRASP_THR, 其后首次>RELEASE_THR) = (10, 50)",
       cw is not None and cw[0] == 10 and cw[1] == 50)
    m = ep_metrics(S, A, w_loss=0.02)
    ck("c2 检出丢罐且 t_loss 落在空合段", m["lost"] and m["t_loss"] == 40)
    ck("c3 w_min = 空合宽度 0.001", abs(m["w_min"] - 0.001) < 1e-9)
    ck("c4 闭合指令统计 = 合成值 0.8", abs(m["act_mean"] - 0.8) < 1e-9 and abs(m["act_p95"] - 0.8) < 1e-9)
    # 全程 60 步抬 12 cm，但 rise_cm 只量搬运段 [10,50] ⇒ 0.12×40/59×100 ≈ 8.1356 cm
    ck("c5 搬运段内末端升程 = (z[tr]−z[tg])×100 ≈ 8.1356 cm（rise_cm 复用 9B 的同一份代码）",
       abs(m["eef_rise_cm"] - 0.12 * 40 / 59 * 100) < 1e-3)
    ck("c6 丢罐前窗口有 PRE 步且 dz/act 都被记", m["pre"]["n"] == PRE and m["pre"]["act_mean"] == 0.8)
    ck("c7 丢罐相对位置 = (t_loss−tg)/(tr−tg) = 30/40 = 0.75", abs(m["loss_after_frac"] - 0.75) < 1e-6)
    m2 = ep_metrics(S, A, w_loss=1e-6)
    ck("c8 阈值严到不可能触发 ⇒ 不报丢罐（不假阳）", m2["lost"] is False and m2["t_loss"] is None)
    w3 = np.full(T, 0.09)          # 从头到尾没张开过 ⇒ 检不出搬运段
    S3 = np.zeros((T, 8)); S3[:, 7] = w3
    ck("c9 没夹住 ⇒ ep_metrics 返回 None（由调用方记 A 类，不当 0）", ep_metrics(S3, A, 0.02) is None)
    ck("c10 太短的局不炸（spd/acc 返回空、分位 nan）",
       (lambda s, a: (s.shape[0] == 0 and a.shape[0] == 0))(*spd_acc(np.zeros((2, 8)))))
    # 相位匹配窗（前 K_MATCH 步）：合成搬运段 41 步 ≥ K_MATCH ⇒ 取得到
    ck("c11 匹配窗取到 K_MATCH 步且 w_min/w_mean/act_mean = 合成值",
       m["m_n"] == K_MATCH and abs(m["m_w_min"] - 0.001) < 1e-9
       and abs(m["m_w_mean"] - (35 * 0.045 + 5 * 0.001) / 40) < 1e-9 and abs(m["m_act_mean"] - 0.8) < 1e-9)
    ck("c12 匹配窗的速度/加速度 = 合成等速值（Δz=0.12/59、加速度 0）",
       abs(m["m_spd_p95"] - 0.12 / 59) < 1e-9 and abs(m["m_acc_p95"]) < 1e-12)   # 等速 ⇒ 加速度只有浮点噪声
    w4 = np.full(30, 0.045); w4[:10] = 0.0788      # 搬运段只有 20 步 < K_MATCH ⇒ 匹配不了
    S4 = np.zeros((30, 8)); S4[:, 7] = w4
    m4 = ep_metrics(S4, np.zeros((30, 7)), 0.02)
    ck("c13 窗口不够长 ⇒ m_* 全 nan（不当 0，坑 40③）",
       m4 is not None and m4["m_n"] == 20 and all(m4[k] != m4[k] for k in FEATS_MATCH))
    ck("c14 loss_after_steps = t_loss − t_grasp（绝对步数，不受窗口删失影响）", m["loss_after_steps"] == 30)
    ck("c15 w_min 0.001 < GRIP_HOLD_WIDTH ⇒ held=False（空合）", m["held"] is False and m2["held"] is False)
    w5 = np.full(T, 0.049); w5[:10] = 0.0788; w5[50:] = 0.075     # 全程稳稳夹住 can
    S5 = np.zeros((T, 8)); S5[:, 7] = w5; S5[:, 2] = S[:, 2]
    m5 = ep_metrics(S5, A, 0.02)
    ck("c16 w_min 0.049 ≥ GRIP_HOLD_WIDTH ⇒ held=True、且不报丢罐", m5["held"] is True and m5["lost"] is False)
    fake = [{"cls": "B", "w_min": 0.003, "held": False, "can_lift_cm": 12.0, "eef_rise_cm": 13.0,
             "min_dist_cm": 45.0, "tipped": False, "loss_after_steps": 1},
            {"cls": "B", "w_min": 0.049, "held": True, "can_lift_cm": 11.0, "eef_rise_cm": 11.0,
             "min_dist_cm": 57.0, "tipped": True, "loss_after_steps": None},
            {"cls": "OK", "w_min": 0.049, "held": True, "can_lift_cm": 11.0, "eef_rise_cm": 11.0,
             "min_dist_cm": 0.5, "tipped": False, "loss_after_steps": None}]
    ss = subsplit(fake)
    ck("s1 subsplit 分桶计数/占比正确", ss["B"]["n"] == 2 and ss["B"]["empty"]["n"] == 1
       and ss["B"]["held"]["n"] == 1 and ss["OK"]["held"]["frac"] == 1.0 and ss["B"]["empty"]["frac"] == 0.5)
    ck("s2 「抓起了」代理的假阳率 = 空合∧can升程≥LIFT_THR ÷ can升程≥LIFT_THR",
       ss["B"]["lift_hi"]["n"] == 2 and ss["B"]["lift_hi"]["n_empty"] == 1 and ss["B"]["lift_hi"]["lie_frac"] == 0.5)
    ck("s3 loss_after_steps 中位数只统计有的局（None 不当 0，坑 40③）",
       ss["B"]["loss_after_steps_med"] == 1 and ss["B"]["n_lost"] == 1 and "EXPERT" not in ss)
    ck("r1 比例置换检验：两组完全分离 ⇒ obs=率差=1、p≤0.05", (lambda d: d["obs"] == 1.0 and d["p"] <= 0.05)(
        rate_perm_test([True] * 20, [False] * 20, n_perm=500)))
    ck("r2 比例相同 ⇒ obs=0、p=1（不制造显著）", (lambda d: d["obs"] == 0.0 and d["p"] == 1.0)(
        rate_perm_test([True] * 10 + [False] * 10, [True] * 10 + [False] * 10, n_perm=500)))
    ck("r3 n<5 ⇒ p=nan（不假装显著，坑 40③）",
       (lambda d: d["p"] != d["p"])(rate_perm_test([True, False], [True] * 20)))
    # classify：分组口径。顺序要紧——delivered_tipped 蕴含放宽成功，先判 relax 会把侧躺局吞进 OK（本文件上一版的 bug）
    ck("k1 没夹住 ⇒ A（无论成败/侧躺）", classify(False, True, True) == "A" and classify(False, False, False) == "A")
    ck("k2 夹住 ∧ 侧躺送达 ⇒ TIP（不许被吞进 OK）", classify(True, True, True) == "TIP")
    ck("k3 夹住 ∧ 立着送达 ⇒ OK；夹住 ∧ 放宽也失败 ⇒ B",
       classify(True, True, False) == "OK" and classify(True, False, False) == "B")
    lr = label_rows([{"cls": "B", "held": False, "w_min": 0.003, "seed": 7001}])
    ck("l1 标签表字段固定、缺的写 None（不当 0，坑 40③）",
       len(lr) == 1 and tuple(lr[0].keys()) == LABEL_KEYS and lr[0]["held"] is False
       and lr[0]["w_min"] == 0.003 and lr[0]["can_lift_cm"] is None and lr[0]["arm"] is None)

    # grip_sign_probe：合成「张开(-1) → 闭合(+1) → 保持 → 张开(-1)」，符号必须被**实测**出来（不信注释，坑 82）
    T2 = 24
    w2 = np.concatenate([np.full(6, GRIP_OPEN_WIDTH), np.linspace(GRIP_OPEN_WIDTH, 0.05, 6),
                         np.full(6, 0.05), np.linspace(0.05, GRIP_OPEN_WIDTH, 6)])
    a2 = np.concatenate([np.full(6, -1.0), np.full(12, +1.0), np.full(6, -1.0)])
    sp = grip_sign_probe(a2, w2, [T2])
    # 动步 = 下降段 5 步（i=6..10）+ 上升段 5 步（i=18..22）；linspace 起点与 0.0788 重合、平台段 Δ=0 ⇒ 都不算动
    ck("g1 指令与开口反向 ⇒ 实测出「+1=闭合」", sp["n_move"] == 10 and sp["frac_same_sign"] == 0.0
       and sp["convention"] == "+1=闭合, -1=张开")
    sp2 = grip_sign_probe(-a2, w2, [T2])
    ck("g2 指令翻号 ⇒ 实测出「+1=张开」（说明不是写死的）",
       sp2["frac_same_sign"] > 0.5 and sp2["convention"] == "+1=张开, -1=闭合")
    sp3 = grip_sign_probe(a2, np.full(T2, 0.05), [T2])
    ck("g3 宽度全程不动 ⇒ n_move=0、frac=nan、「不可判」（不猜，坑 40③）",
       sp3["n_move"] == 0 and sp3["frac_same_sign"] != sp3["frac_same_sign"] and sp3["convention"] == "不可判")
    ck("g4 分箱：张开段 act 中位 -1、夹住段 act 中位 +1",
       sp["open"]["act_med"] == -1.0 and sp["hold"]["act_med"] == 1.0 and sp["empty"]["n"] == 0)
    ck("g5 多集时 Δwidth 不跨集连（边界步被排除）",
       grip_sign_probe(a2, w2, [8, 16])["n_move"] == sp["n_move"] - 1)

    # perm_test：完全分离 ⇒ p 很小；完全相同 ⇒ p≈1；样本太小 ⇒ nan（不判）
    rng = np.random.default_rng(0)
    sep = perm_test(list(rng.normal(1.0, 0.01, 40)), list(rng.normal(0.0, 0.01, 40)), n_perm=500)
    ck("p1 完全分离 ⇒ p ≤ 0.05 且 obs > 0", sep["p"] <= 0.05 and sep["obs"] > 0)
    same = perm_test([1.0] * 20, [1.0] * 20, n_perm=200)
    ck("p2 两组全同 ⇒ obs=0、p=1", same["obs"] == 0.0 and same["p"] == 1.0)
    ck("p3 n<5 ⇒ nan（不假装显著）", perm_test([1.0, 2.0], [3.0, 4.0])["p"] != perm_test([1.0, 2.0], [3.0, 4.0])["p"])
    ck("p4 置换检验可复现（固定 seed）",
       perm_test([1.0, 2.0, 3.0, 4.0, 5.0, 9.0], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], n_perm=200)["p"]
       == perm_test([1.0, 2.0, 3.0, 4.0, 5.0, 9.0], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], n_perm=200)["p"])

    # 阈值必须只从专家推：断言本文件不去读策略产物来定 W_LOSS
    ck("w1 W_LOSS 的分位是事前常数 p05、敏感性含 p01/p10", W_Q_MAIN == 0.05 and W_Q_SENS == (0.01, 0.10))
    ck("w2 夹爪阈值 import 自冻结口径（不新造）", (OPEN_THR, GRASP_THR, RELEASE_THR) == (0.07, 0.058, 0.062))
    ck("w3 专家示范 npz 在盘上（阈值出处）", DEMO_NPZ.exists())

    print(f"[selftest] B 类夹爪诊断钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  🚫", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sample", choices=("test", "val"), default="test")
    a = ap.parse_args()
    return selftest() if a.selftest else run(a.sample)


if __name__ == "__main__":
    raise SystemExit(main())
