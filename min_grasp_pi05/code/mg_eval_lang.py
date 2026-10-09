#!/usr/bin/env python
"""档 11 · 语言泛化外壳：把冻结评测入口的**指令串**换成同义改写句。**不修改任何冻结文件**。

为什么要外壳而不是改 `mg_eval.py`：`mg_eval.py` / `mg_env*.py` 是冻结文件（坑 22 家族）——判据、出身字段、
产物格式都由它一处出。本文件只改**一个模块级字符串常量**，其余原样交给 `mg_eval.main()`
（照 9B `mg_eval_zlim.py` 的已验证模式：新文件 + patch + 透传 argv）。

patch 目标（两条路径都在 `code/mg_eval.py:138-144`，本文件的自测**逐行钉住**这个写法）：
  * `--task-mode forward` ⇒ `task_str = TASK`，而 `TASK` 是 mg_eval **模块级** import 的名字
    ⇒ patch `mg_eval.TASK`（改 `mg_env.TASK` 没用：mg_eval 已经把值绑进自己的命名空间了）。
  * `--task-mode reverse` ⇒ `from mg_env_reverse import TASK_REVERSE` 是 main() 里的**延迟 import**
    ⇒ patch `mg_env_reverse.TASK_REVERSE` 就会被 main() 取到。

⚠️ 静默失败的最大风险 = **patch 没生效**（跑的还是原话）⇒ 那会让 L1 假过、L3 假阴。所以：
  1. patch 后**立刻回读**模块属性核对；
  2. sidecar 落 `orig_task` / `patched_task` / `module_attr` / `post_patch_readback`；
  3. `eval_summary.json` 的 `task` 字段由 mg_eval 自己写 ⇒ 判定工具（L4）拿它与 sidecar **逐字对账**。

用法（其余参数原样透传给 mg_eval.py）：
    $MG_PY code/mg_eval_lang.py --instruction "Remove the can from the bin and place it onto the tray." \
        --ckpt <run>/checkpoints/022000/pretrained_model --episodes 20 --seed-mode random --seed 7000 \
        --n-action-steps 10 --task-mode reverse --demo-npz data/mix60f120r_rev_raw.npz --out runs/s11_xxx
    $MG_PY code/mg_eval_lang.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# 两句原话的**期望值**：真值从冻结源码里读（`read_task_consts`），这里只是自测用的对账锚。
EXPECT_FWD = "Pick up the can and place it into the bin."
EXPECT_REV = "Take the can out of the bin and put it back into the tray."

# ── 本档的**单一真源**：指令集 / 三臂 / 目录命名 / 20 读清单 ─────────────────────────
# 为什么放这里而不是各写一份：链（`chain_s11.sh`）要按它发车、判定工具（`mg_verdict_s11.py`）要按它读盘，
# 两边各写一遍就一定会走样（走样的形状 = 链跑了 A 目录、判定去读 B 目录 ⇒ 永远 UNKNOWN 且看起来像「数据没出」）。
# 指令串与 `runs/S11_PREREG.md` §2.2 **逐字一致**（预注册 2026-10-07 20:04 落盘，早于任何读数）。
INSTR = {
    "R1": "Take the can out of the bin and put it back on the tray.",
    "R2": "Remove the can from the bin and place it onto the tray.",
    "R3": "Pick the can up out of the bin and return it to the tray.",
    "RN": "Stack the blocks into a tall tower.",
    "F1": "Pick up the can and put it into the bin.",
    "F2": "Grab the can and drop it into the basket.",
    "F3": "Move the can from the table into the bin.",
    "FN": "Stack the blocks into a tall tower.",
}
CODE_ORDER = ("R1", "R2", "R3", "RN", "F1", "F2", "F3", "FN")
ARMS = ("s8c_seed2000", "s8d_seed4000", "s8d_seed5000")   # = 档 8 的 D4 / 档 10 的三臂（同数据集 ⇒ 臂间可比）
NEG_ARM = "s8c_seed2000"          # 负对照只 1 臂（预注册 §2.3：定性足够，省下 4 读的 GPU）
DST = "mix60f120r_c1"
CK_STEP = 22000
K_EVAL = 10                       # 工作点；本档**不**碰 K=50（那是档 10）
EPS = 20
SCENES = {"rev": {"task_mode": "reverse", "seed0": 7000, "npz": "mix60f120r_rev_raw.npz"},
          "fwd": {"task_mode": "forward", "seed0": 2000, "npz": "mix60f120r_raw.npz"}}


def scene_of(code: str) -> str:
    return "rev" if code.startswith("R") else "fwd"


def out_name(arm: str, code: str) -> str:
    return f"s11_{arm}_{scene_of(code)}_{code}_rand20_k{K_EVAL}"


def plan_reads() -> list:
    """20 读清单（预注册 §2.3）：反向 3 句×3 臂 + 负对照 1 臂 = 10；正向同 = 10。"""
    reads = []
    for code in CODE_ORDER:
        sc = SCENES[scene_of(code)]
        arms = (NEG_ARM,) if code.endswith("N") else ARMS
        for arm in arms:
            run = f"pi05_{DST}_{arm}"
            reads.append({
                "code": code, "scene": scene_of(code), "arm": arm, "run": run,
                "instruction": INSTR[code], "out": out_name(arm, code),
                "task_mode": sc["task_mode"], "seed0": sc["seed0"], "npz": sc["npz"],
                "episodes": EPS, "k": K_EVAL,
                "ckpt": str(MG_ROOT / "runs" / run / "checkpoints" / f"{CK_STEP:06d}" / "pretrained_model"),
            })
    return reads


PLAN_FIELDS = ("code", "scene", "arm", "out", "task_mode", "seed0", "npz", "episodes", "k", "ckpt", "instruction")


def print_plan() -> int:
    """TSV 打印 20 读清单（instruction 放最后一列 ⇒ 含空格也安全）；`chain_s11.sh` 直接 read 它发车。"""
    print("\t".join(PLAN_FIELDS))
    for r in plan_reads():
        print("\t".join(str(r[f]) for f in PLAN_FIELDS))
    return 0


def code_sha16() -> str:
    return hashlib.sha256((HERE / "mg_eval_lang.py").read_bytes()).hexdigest()[:16]


def read_task_consts() -> dict:
    """从冻结源码里**读**出两句原话（不 import ⇒ 不拖进 robosuite/torch，自测才能秒级跑完）。

    读不到就**抛错**：说明冻结文件的写法变了，本外壳的 patch 目标可能已经失效 ——
    这种情况必须响，绝不允许静默退回某个硬编码字符串（那会跑成「原话」还看不出来）。
    """
    src_env = (HERE / "mg_env.py").read_text()
    src_rev = (HERE / "mg_env_reverse.py").read_text()
    m_f = re.search(r'^TASK\s*=\s*"([^"]+)"\s*$', src_env, re.M)
    m_r = re.search(r'^TASK_REVERSE\s*=\s*"([^"]+)"\s*$', src_rev, re.M)
    if not m_f or not m_r:
        raise RuntimeError(
            f"读不到原话常数（mg_env.TASK={bool(m_f)} / mg_env_reverse.TASK_REVERSE={bool(m_r)}）"
            " ⇒ 冻结文件写法变了，patch 目标不可信，拒绝发车")
    return {"forward": m_f.group(1), "reverse": m_r.group(1)}


def detect_mode(rest: list) -> str:
    """从透传 argv 里读 `--task-mode`（缺省 = forward，与 mg_eval 的 argparse 缺省一致）。"""
    for i, a in enumerate(rest):
        if a == "--task-mode" and i + 1 < len(rest):
            return str(rest[i + 1])
        if a.startswith("--task-mode="):
            return a.split("=", 1)[1]
    return "forward"


def detect_out(rest: list) -> str:
    for i, a in enumerate(rest):
        if a == "--out" and i + 1 < len(rest):
            return str(rest[i + 1])
        if a.startswith("--out="):
            return a.split("=", 1)[1]
    return ""


def plan_patch(task_mode: str, instruction: str) -> dict:
    """给出 patch 计划（**先算后打**，便于自测与出身核对）。"""
    consts = read_task_consts()
    if task_mode == "reverse":
        mod, attr, orig = "mg_env_reverse", "TASK_REVERSE", consts["reverse"]
    elif task_mode == "forward":
        # 正向的原话定义在 mg_env，但**要 patch 的是 mg_eval 命名空间里的绑定**（见文件头）
        mod, attr, orig = "mg_eval", "TASK", consts["forward"]
    else:
        raise ValueError(f"task_mode 只能是 forward/reverse，收到 {task_mode!r}")
    return {"task_mode": task_mode, "module": mod, "attr": attr,
            "orig_task": orig, "patched_task": instruction}


def validate_instruction(plan: dict) -> list:
    """指令合法性（返回问题清单，空 = 合法）。跑前挡掉三类白跑：空串、与原话相同、非字符串。"""
    bad = []
    ins = plan["patched_task"]
    if not isinstance(ins, str):
        bad.append(f"指令不是字符串：{type(ins).__name__}")
        return bad
    if not ins.strip():
        bad.append("指令是空串/全空白 ⇒ mg_eval 会把空 task 喂给策略，读数没有意义")
    if ins == plan["orig_task"]:
        bad.append("指令与该场景的原话**逐字相同** ⇒ 这一格是重复的参照读数，不是改写句（白跑 GPU）")
    if ins != ins.strip():
        bad.append("指令首尾有空白 ⇒ 与 sidecar/summary 的逐字对账会差一个空格")
    return bad


def apply_patch(plan: dict):
    """打 patch 并**回读核对**；返回 (mg_eval 模块, readback 值)。回读不符 ⇒ 抛错（不许静默跑原话）。"""
    import mg_eval
    if plan["module"] == "mg_eval":
        setattr(mg_eval, plan["attr"], plan["patched_task"])
        back = getattr(mg_eval, plan["attr"])
    else:
        import mg_env_reverse
        setattr(mg_env_reverse, plan["attr"], plan["patched_task"])
        back = getattr(mg_env_reverse, plan["attr"])
    if back != plan["patched_task"]:
        raise RuntimeError(f"patch 回读不符：{plan['module']}.{plan['attr']} = {back!r} ≠ {plan['patched_task']!r}")
    return mg_eval, back


def write_sidecar(path: Path, sc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sc, ensure_ascii=False, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instruction", required=True, help="要喂给策略的指令串（同义改写句 / 负对照句）")
    ap.add_argument("--sidecar-out", default="", help="sidecar 落盘路径（默认 <mg_eval 的 --out>/lang_sidecar.json）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--print-plan", action="store_true", help="TSV 打印 20 读清单（链按它发车，判定按它读盘）")
    args, rest = ap.parse_known_args()
    if args.selftest:
        return selftest()
    if args.print_plan:
        return print_plan()

    mode = detect_mode(rest)
    plan = plan_patch(mode, args.instruction)
    bad = validate_instruction(plan)
    if bad:
        for b in bad:
            print(f"[lang] FATAL {b}", file=sys.stderr)
        return 4
    out = detect_out(rest)
    sc_path = Path(args.sidecar_out) if args.sidecar_out else (Path(out) / "lang_sidecar.json" if out else Path("/tmp/lang_sidecar.json"))
    sc = {"tool": "mg_eval_lang.py", "tool_sha256_16": code_sha16(), "started": f"{datetime.now():%F %T}",
          "module_attr": f"{plan['module']}.{plan['attr']}", "task_mode": mode,
          "orig_task": plan["orig_task"], "patched_task": plan["patched_task"],
          "argv_passthrough": list(rest), "sidecar_path": str(sc_path)}

    mev, back = apply_patch(plan)
    sc["post_patch_readback"] = back
    print(f"[lang] patch {plan['module']}.{plan['attr']}: {plan['orig_task']!r} -> {back!r}", flush=True)
    print(f"[lang] 透传给 mg_eval：{' '.join(rest)}", flush=True)

    sys.argv = ["mg_eval.py"] + list(rest)
    rc = mev.main()                      # 冻结入口原样跑：判据/出身字段/npz 全是它一处出
    sc["mg_eval_rc"] = int(rc)
    sc["finished"] = f"{datetime.now():%F %T}"
    summ = Path(out) / "eval_summary.json" if out else None
    if summ and summ.exists():
        try:
            sc["summary_task_field"] = json.loads(summ.read_text()).get("task")
        except Exception as exc:                              # 读不动也要留痕，不静默
            sc["summary_task_field_error"] = str(exc)
    write_sidecar(sc_path, sc)
    print(f"[lang] sidecar -> {sc_path}（mg_eval rc={rc}）", flush=True)
    return int(rc)


# ── 自测：patch 机制必须在**不碰 GPU、不 import 重依赖**的前提下被测到 ──────────────────
def selftest() -> int:
    fails: list = []
    total = [0]

    def ck(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    # A. 原话常数从冻结源码读得到，且与预注册 §2.2 的参照句逐字相同
    try:
        c = read_task_consts()
        ck("A1 mg_env.TASK 读到且 == 预注册的 F0", c["forward"] == EXPECT_FWD)
        ck("A2 mg_env_reverse.TASK_REVERSE 读到且 == 预注册的 R0", c["reverse"] == EXPECT_REV)
    except Exception as exc:
        ck(f"A0 read_task_consts 不该抛（{exc}）", False)
        c = {"forward": EXPECT_FWD, "reverse": EXPECT_REV}

    # B. 冻结入口的写法钉子：patch 目标若被改写，这里必须响（不然外壳会静默跑原话）
    src = (HERE / "mg_eval.py").read_text()
    ck("B1 mg_eval 正向仍用模块级 `task_str = TASK`", re.search(r"^\s+task_str = TASK$", src, re.M) is not None)
    ck("B2 mg_eval 反向仍是 main() 里的**延迟** import（⇒ patch mg_env_reverse 有效）",
       src.index("from mg_env_reverse import TASK_REVERSE") > src.index("def main()"))
    ck("B3 mg_eval 反向用 `task_str = TASK_REVERSE`", "task_str = TASK_REVERSE" in src)
    ck("B4 mg_eval 把 task 写进 eval_summary（L4 对账的依据）", '"task": task_str' in src)

    # C. detect_mode / detect_out
    ck("C1 缺省 = forward（与 mg_eval 的 argparse 缺省一致）", detect_mode(["--ckpt", "x"]) == "forward")
    ck("C2 空格分隔", detect_mode(["--task-mode", "reverse", "--episodes", "20"]) == "reverse")
    ck("C3 等号写法", detect_mode(["--task-mode=reverse"]) == "reverse")
    ck("C4 后面的值不会被误当 mode", detect_mode(["--episodes", "20", "--task-mode", "forward"]) == "forward")
    ck("C5 --out 空格分隔", detect_out(["--out", "/x/runs/y"]) == "/x/runs/y")
    ck("C6 --out 等号写法", detect_out(["--out=/x/y"]) == "/x/y")
    ck("C7 没有 --out ⇒ 空串（不编路径）", detect_out(["--ckpt", "x"]) == "")

    # D. plan_patch：正向 patch mg_eval.TASK、反向 patch mg_env_reverse.TASK_REVERSE
    pf = plan_patch("forward", "Pick up the can and put it into the bin.")
    ck("D1 正向 patch 目标 = mg_eval.TASK（不是 mg_env.TASK）", (pf["module"], pf["attr"]) == ("mg_eval", "TASK"))
    ck("D2 正向 orig = F0 原话", pf["orig_task"] == EXPECT_FWD)
    pr = plan_patch("reverse", "Remove the can from the bin and place it onto the tray.")
    ck("D3 反向 patch 目标 = mg_env_reverse.TASK_REVERSE", (pr["module"], pr["attr"]) == ("mg_env_reverse", "TASK_REVERSE"))
    ck("D4 反向 orig = R0 原话", pr["orig_task"] == EXPECT_REV)
    try:
        plan_patch("sideways", "x"); ck("D5 非法 task_mode 必须抛", False)
    except ValueError:
        ck("D5 非法 task_mode 必须抛", True)

    # E. validate_instruction：挡掉三类白跑
    ck("E1 合法改写句 ⇒ 无问题", validate_instruction(pr) == [])
    ck("E2 空串 ⇒ 挡下", any("空串" in b for b in validate_instruction(plan_patch("reverse", "   "))))
    ck("E3 与原话逐字相同 ⇒ 挡下（那是重复参照，不是改写）",
       any("逐字相同" in b for b in validate_instruction(plan_patch("reverse", EXPECT_REV))))
    ck("E4 首尾空白 ⇒ 挡下（会毁掉逐字对账）",
       any("首尾有空白" in b for b in validate_instruction(plan_patch("reverse", " " + EXPECT_REV + "x "))))
    ck("E5 非字符串 ⇒ 挡下且不炸", any("不是字符串" in b for b in validate_instruction(plan_patch("reverse", 123))))

    # F. apply_patch 的机制（用假模块，不 import torch/robosuite）
    class _FakeMod:
        TASK = EXPECT_FWD
    fake = _FakeMod()
    real_set = plan_patch("forward", "Move the can from the table into the bin.")
    setattr(fake, real_set["attr"], real_set["patched_task"])
    ck("F1 setattr 后回读 == 改写句", getattr(fake, real_set["attr"]) == real_set["patched_task"])
    ck("F2 回读 != 原话（证明真的换了）", getattr(fake, real_set["attr"]) != real_set["orig_task"])
    ck("F3 code_sha16 是 16 位十六进制", len(code_sha16()) == 16 and all(ch in "0123456789abcdef" for ch in code_sha16()))

    # G. sidecar 落盘（写临时目录，不碰 runs/）
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sub" / "lang_sidecar.json"
        write_sidecar(p, {"orig_task": EXPECT_REV, "patched_task": pr["patched_task"], "mg_eval_rc": 0})
        j = json.loads(p.read_text())
        ck("G1 sidecar 建父目录并写成功", p.exists())
        ck("G2 sidecar 保留 orig/patched 两个字段（L4 靠它证明 patch 生效）",
            j["orig_task"] == EXPECT_REV and j["patched_task"] == pr["patched_task"] and j["orig_task"] != j["patched_task"])
        ck("G3 中文/引号不被转义成乱码（ensure_ascii=False）", "can" in p.read_text())

    # H. 单一真源：指令集 / 三臂 / 20 读清单 / 目录命名
    ck("H1 每场景 3 句改写 + 1 句负对照 = 8 个代号",
       len([c for c in CODE_ORDER if c.startswith("R")]) == 4 and len([c for c in CODE_ORDER if c.startswith("F")]) == 4)
    ck("H2 8 个代号里 7 句互不相同（两个场景共用同一句负对照）", len(set(INSTR.values())) == 7)
    ck("H3 没有一句与该场景原话逐字相同（否则是重复参照不是改写）",
       EXPECT_REV not in [v for k, v in INSTR.items() if scene_of(k) == "rev"]
       and EXPECT_FWD not in [v for k, v in INSTR.items() if scene_of(k) == "fwd"])
    ck("H4 每句都过 validate_instruction",
       all(validate_instruction(plan_patch(SCENES[scene_of(c)]["task_mode"], v)) == [] for c, v in INSTR.items()))
    pl = plan_reads()
    ck("H5 清单 = 20 读（预注册 §2.3 的账）", len(pl) == 20)
    ck("H6 反向 10 读 / 正向 10 读", len([r for r in pl if r["scene"] == "rev"]) == 10
       and len([r for r in pl if r["scene"] == "fwd"]) == 10)
    ck("H7 改写句 3 臂、负对照只 1 臂", len([r for r in pl if r["code"] == "R2"]) == 3
       and len([r for r in pl if r["code"] == "RN"]) == 1 and [r for r in pl if r["code"] == "RN"][0]["arm"] == NEG_ARM)
    ck("H8 合计 400 局", sum(r["episodes"] for r in pl) == 400)
    ck("H9 目录名互不相同（撞名会互相覆盖产物）", len({r["out"] for r in pl}) == 20)
    ck("H10 目录名含场景与代号（人眼能认）", all(f"_{r['scene']}_{r['code']}_" in r["out"] for r in pl))
    ck("H11 目录名不与档 10（k50）或关门读数（k10 无前缀）撞",
       all(r["out"].startswith("s11_") and "_k10" in r["out"] for r in pl))
    ck("H12 反向 seed0=7000 / 正向 seed0=2000（与关门读数同一批 ⇒ 可配对）",
       all(r["seed0"] == (7000 if r["scene"] == "rev" else 2000) for r in pl))
    ck("H13 K=10、每读 20 局", all(r["k"] == K_EVAL and r["episodes"] == EPS for r in pl))
    ck("H14 ckpt 全是 022000 数字格且在本臂 run 里（坑 38/42/63）",
       all(r["ckpt"].endswith(f"checkpoints/{CK_STEP:06d}/pretrained_model") and f"/{r['run']}/" in r["ckpt"] for r in pl))
    ck("H15 三臂都是 mix60f120r_c1（同数据集才许比高低，坑 33）", all(f"pi05_{DST}_" in r["run"] for r in pl))
    ck("H16 npz：反向用 _rev_raw、正向用 _raw（与关门读数同源）",
       all(r["npz"] == ("mix60f120r_rev_raw.npz" if r["scene"] == "rev" else "mix60f120r_raw.npz") for r in pl))
    ck("H17 TSV 表头 = 11 列且 instruction 在最后一列（含空格也安全）",
       PLAN_FIELDS[-1] == "instruction" and len(PLAN_FIELDS) == 11)
    ck("H18 TSV 每行 11 列、指令里不含制表符",
       all(len([str(r[f]) for f in PLAN_FIELDS]) == 11 and "\t" not in r["instruction"] for r in pl))

    print(f"[selftest] mg_eval_lang：{total[0] - len(fails)}/{total[0]} 通过" + ("" if not fails else f"，失败：{fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if "--print-plan" in sys.argv:
        raise SystemExit(print_plan())
    raise SystemExit(main())
