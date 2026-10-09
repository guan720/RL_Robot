#!/usr/bin/env python
"""最小抓取链路 · 关门检查点选择（只用 val，不看 test）。

为什么需要这个脚本，而不是「拿 last 关门」：
  2026-10-01 档 2 的门是用 `checkpoints/last`（=014400）评的，判反向 FAIL 32.5%。
  但双向扫描 `sweep_bidir/` 早就摆在那里：**正向 val 与反向 val 同时在 step 11000 达峰**
  （fwd 8/10、rev 5/10），之后一路掉（rev 13000 = 0/10，14000 = 2/10，last 亦然）。
  也就是说档 2 交的读数不是「模型能做到的水平」，而是「训练尾巴上最差的那一步」。
  这是**协议缺陷**，不是模型缺陷：BC 在小数据上过训会先升后降，用 last 关门等于
  把「选点」这件事偷偷交给了「训练什么时候停」。

本脚本做的事（刻意很笨，为的是可审计）：
  1. 把 sweep 里每个 step 的 val 成功数读出来，原样落盘（`ckpt_selection.json` 里的 `curve`）；
  2. **核对每一格的出身**：`eval_summary.json:policy_ckpt` 里的检查点格号必须等于目录名的 step
     （坑 42）。对不上 ⇒ 这一格**剔除并报出来**，绝不静默参与选点；
  3. 按**预先写死**的规则选一个 step：`argmax(fwd_val_n + rev_val_n)`，并列取**更早**的 step
     —— 更早 = 更少训练 = 更不容易过训；单方向任务传 `--direction` 只按那一支选；
  4. 把规则和「test 只能读一次」写进 json，免得后人换规则重选（那就是在 test 上挑点）。

⚠️ 纪律：选择只准看 val。选定之后 test 读数**只跑一次**；跑完再回来改规则重选 = 在 test 上
   挑检查点，等于把 test 变成第二个 val，门的意义就没了。

⚠️ 坑 42（2026-10-02 实测，本脚本旧版就是被它骗过）：`mg_sweep_*.sh` 对**终点格**用的是
   `checkpoints/last`，而 lerobot 的 `last` 软链**每次 save 都重指**。扫描在训练收工前跑到
   终点格时，`last -> 020000`，于是 `sweep_rev/step_22000_rev/` 里装的是 **020000 的权重**、
   读出的 10/20 被写进 `ckpt_selection.json` 当了 22000 的分。旧版 `read_sweep()` 只看目录名、
   不看 `policy_ckpt`，所以完全没察觉。上游 `wait_last_ckpt()` 已修（等 `readlink last == %06d`），
   本脚本再核一遍出身 = **第二道闸**：上游漏了也不会污染选点。

⚠️ 「缺读数」不等于 0 分（与坑 40③ 同源）：`--direction both` 时若某一格只有 fwd 没有 rev，
   旧版按 `fwd + 0` 记分 ⇒ 系统性把它压下去。现在这种**读数不全的格直接取消资格**并报出来，
   不参与 argmax。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_select_ckpt.py \
        --run runs/pi05_mix60f60r_s2 --sweep sweep_bidir --direction both'
    # 只看不落盘：--print-only    # 写到别的文件名（不动历史）：--out ckpt_selection_corrected.json
    $MG_PY code/mg_select_ckpt.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent

RULE = ("argmax over sweep steps of (fwd_val_n_success + rev_val_n_success); "
        "tie-break = earliest step (less training = less overfitting); "
        "points whose policy_ckpt does not match their own step number are REJECTED (trap 42); "
        "steps missing a required direction are INELIGIBLE, never scored as 0")

STEP_RE = re.compile(r"step_(\d+)_(fwd|rev)\Z")
CKPT_RE = re.compile(r"checkpoints/([^/]+)/")


def rel(p: Path) -> str:
    """相对 MG_ROOT 的路径；不在其下就原样给绝对路径（自测用临时目录时不至于崩）。"""
    try:
        return str(p.relative_to(MG_ROOT))
    except ValueError:
        return str(p)


def last_target(run: Path) -> str | None:
    """`run/checkpoints/last` 现在指向哪一格（坑 38：它会随每次 save 重指）。"""
    link = run / "checkpoints" / "last"
    try:
        if link.is_symlink():
            return Path(link.resolve()).name
        if link.is_dir():                      # 不是软链而是真目录 ⇒ 无从核对
            return None
    except OSError:
        return None
    return None


def classify(ckpt_field: str | None, step: int, last_now: str | None) -> tuple[str, str]:
    """核对一格 val 产物的出身。返回 (状态, 说明)，状态 ∈ {ok, mismatch, unverifiable}。

    * ok           ：`policy_ckpt` 明确指向 `checkpoints/{step:06d}/`，或指向 `last` 且
                     **此刻** `readlink last == {step:06d}`（训练已收工时才可信）。
    * mismatch     ：指向别的格号，或指向 `last` 而 `last` 现在指着别的格 ⇒ 这格读数不是这一步的权重。
    * unverifiable ：产物里没写 `policy_ckpt`，或写了 `last` 而 `last` 读不出来。
    """
    want = f"{step:06d}"
    if not ckpt_field:
        return "unverifiable", "产物里没有 policy_ckpt 字段，无法核对出身"
    m = CKPT_RE.search(str(ckpt_field))
    if not m:
        return "unverifiable", f"policy_ckpt 里没有 checkpoints/<格>：{ckpt_field}"
    got = m.group(1)
    if got == want:
        return "ok", f"policy_ckpt -> checkpoints/{got}（与目录名 step {step} 一致）"
    if got == "last":
        if last_now is None:
            return "unverifiable", ("policy_ckpt 记的是 checkpoints/last，而 run/checkpoints/last "
                                    "此刻读不出指向（坑 38：last 每次 save 都重指）")
        if last_now == want:
            return "ok", (f"policy_ckpt 记的是 last，此刻 readlink last == {want}（与 step {step} 一致；"
                          "仅在训练已收工后可信）")
        return "mismatch", (f"policy_ckpt 记的是 last，而 last 现在 -> {last_now} ≠ 期望 {want} "
                            f"⇒ 这格装的是 {last_now} 的权重（坑 38/42）")
    return "mismatch", f"policy_ckpt -> checkpoints/{got}，而目录名是 step {step}（期望 {want}）⇒ 出身不符"


def read_sweep(sweep_dir: Path, run: Path, include_unverifiable: bool = False):
    """读扫描产物并逐格核对出身。

    返回 (curve, rejected)。curve 只含**可参与选点**的格；rejected 是被剔除的，逐条带原因。
    """
    last_now = last_target(run)
    curve: dict[int, dict[str, dict]] = {}
    rejected: list[dict] = []
    for d in sorted(sweep_dir.glob("step_*")):
        m = STEP_RE.fullmatch(d.name)
        if not m:
            continue
        step, direction = int(m.group(1)), m.group(2)
        f = d / "eval_summary.json"
        rec = {"step": step, "direction": direction, "dir": rel(d)}
        if not f.exists():
            rec.update(status="missing", reason="没有 eval_summary.json（这一格没跑完）")
            rejected.append(rec)
            continue
        try:
            j = json.loads(f.read_text())
        except Exception as exc:                                   # noqa: BLE001
            rec.update(status="unreadable", reason=f"eval_summary.json 解析失败：{exc!r}")
            rejected.append(rec)
            continue
        status, why = classify(j.get("policy_ckpt"), step, last_now)
        rec.update(status=status, reason=why, ckpt_field=j.get("policy_ckpt"))
        if status == "mismatch" or (status == "unverifiable" and not include_unverifiable):
            rejected.append(rec)
            continue
        if "n_success" not in j or "episodes" not in j:
            rec.update(status="incomplete", reason="缺 n_success/episodes 字段")
            rejected.append(rec)
            continue
        curve.setdefault(step, {})[direction] = {
            "n_success": int(j["n_success"]),
            "episodes": int(j["episodes"]),
            "seed_base": int(j.get("seed", -1)),
            "dir": rel(d),
            "provenance": status,
            "provenance_note": why,
            "policy_ckpt": j.get("policy_ckpt"),
        }
        if j.get("pc_success_relaxed") is not None:
            curve[step][direction]["n_success_relaxed"] = int(j["n_success_relaxed"])
    return dict(sorted(curve.items())), rejected, last_now


def score_steps(curve, direction: str):
    """按预注册规则记分。读数不全的 step 取消资格（不当 0 分）。

    返回 (scores, ineligible)。
    """
    need = ("fwd", "rev") if direction == "both" else (direction,)
    scores: dict[int, int] = {}
    ineligible: list[dict] = []
    for step, dirs in curve.items():
        lack = [d for d in need if d not in dirs]
        if lack:
            ineligible.append({"step": step, "reason": f"缺方向读数 {','.join(lack)} ⇒ 取消资格（不当 0 分）"})
            continue
        scores[step] = sum(int(dirs[d]["n_success"]) for d in need)
    return scores, ineligible


def select(scores: dict[int, int]):
    """argmax，并列取最早。空字典返回 (None, None, [])。"""
    if not scores:
        return None, None, []
    best = max(scores.values())
    ties = sorted(s for s, v in scores.items() if v == best)
    return ties[0], best, ties


def build_report(run: Path, sweep_name: str, direction: str, include_unverifiable: bool):
    """把「读盘 + 核出身 + 记分 + 选点」做完，返回一个可落盘的 dict（不落盘）。"""
    sweep_dir = run / sweep_name
    curve, rejected, last_now = read_sweep(sweep_dir, run, include_unverifiable)
    scores, ineligible = score_steps(curve, direction)
    sel, best, ties = select(scores)
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run": str(run),
        "sweep": str(sweep_dir),
        "direction": direction,
        "rule": RULE,
        "include_unverifiable": bool(include_unverifiable),
        "curve": {str(k): v for k, v in curve.items()},
        "scores": {str(k): v for k, v in scores.items()},
        "provenance": {
            "last_target_now": last_now,
            "rejected": rejected,
            "ineligible": ineligible,
        },
        "selected_step": sel,
        "selected_score": best,
        "tied_steps": ties,
        "discipline": ("selection used val only; the test set must be read ONCE for this "
                       "checkpoint. Re-selecting after seeing test = tuning on test."),
    }
    if sel is not None:
        ckpt = run / "checkpoints" / f"{sel:06d}" / "pretrained_model"
        out["selected_ckpt"] = str(ckpt)
        out["ckpt_exists"] = ckpt.joinpath("model.safetensors").exists()
    else:
        out["selected_ckpt"] = None
        out["ckpt_exists"] = False
    return out


def print_report(out: dict, sweep_name: str) -> None:
    run = Path(out["run"])
    print(f"# 检查点选择（只看 val）  run={run.name}  sweep={sweep_name}  direction={out['direction']}")
    prov = out["provenance"]
    print(f"# run/checkpoints/last 此刻 -> {prov['last_target_now'] or '读不出'}（坑 38：每次 save 都重指）")
    print(f"{'step':>6} {'fwd val':>10} {'rev val':>10} {'和':>5}")
    curve = {int(k): v for k, v in out["curve"].items()}
    for step in sorted(set(list(curve) + [int(r["step"]) for r in prov["rejected"]])):
        dirs = curve.get(step, {})
        f, r = dirs.get("fwd"), dirs.get("rev")
        ft = f"{f['n_success']}/{f['episodes']}" if f else "-"
        rt = f"{r['n_success']}/{r['episodes']}" if r else "-"
        sc = out["scores"].get(str(step), "取消")
        print(f"{step:>6} {ft:>10} {rt:>10} {str(sc):>5}")
    if prov["rejected"]:
        print("\n[select] ⚠️ 剔除 %d 格（**不参与选点**，逐条给原因）：" % len(prov["rejected"]))
        for rec in prov["rejected"]:
            print("[select]   🚫 step %-6s %-3s [%s] %s"
                  % (rec["step"], rec["direction"], rec["status"], rec["reason"]))
    if prov["ineligible"]:
        print("[select] ⚠️ 读数不全 %d 格（不当 0 分，直接取消资格）：" % len(prov["ineligible"]))
        for rec in prov["ineligible"]:
            print("[select]   ⛔ step %-6s %s" % (rec["step"], rec["reason"]))
    print(f"\n[select] 规则：{out['rule']}")
    if out["selected_step"] is None:
        print("[select] 🚫 没有任何合格格 ⇒ 选不出点（别拿 last 冒充）")
        return
    print(f"[select] 并列最高分 {out['selected_score']} 的 step：{out['tied_steps']} "
          f"⇒ 取最早 = {out['selected_step']}")
    print(f"[select] 检查点：{out['selected_ckpt']}")
    print(f"[select] 存在={out['ckpt_exists']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="训练产物目录，如 runs/pi05_mix60f60r_s2")
    ap.add_argument("--sweep", default="sweep_bidir", help="run 下的扫描子目录名")
    ap.add_argument("--direction", choices=("fwd", "rev", "both"), default="both",
                    help="both = 双向和最大（档 2 口径）；单向任务只按那一支选")
    ap.add_argument("--print-only", action="store_true", help="只打印曲线，不落盘 selection")
    ap.add_argument("--out", default="ckpt_selection.json",
                    help="落盘文件名（在 --run 下）。要保留历史就换个名字，别覆盖")
    ap.add_argument("--include-unverifiable", action="store_true",
                    help="把「出身核不了」的格也算进来。**只用于取证**，选点/关门一律不许开")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.run:
        ap.error("--run 是必需的（除非 --selftest）")
    if args.include_unverifiable:
        print("[select] ⚠️⚠️ --include-unverifiable 已开：出身核不了的格会参与选点。"
              "这只用于取证，不许用于任何门。")

    run = Path(args.run)
    if not run.is_absolute():
        run = MG_ROOT / run
    sweep_dir = run / args.sweep
    if not sweep_dir.is_dir():
        print(f"[select] FATAL 扫描目录不存在：{sweep_dir}")
        return 3
    out = build_report(run, args.sweep, args.direction, args.include_unverifiable)
    print_report(out, args.sweep)
    if out["selected_step"] is None:
        return 4
    if args.print_only:
        return 0

    dst = run / args.out
    dst.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[select] 落盘 -> {dst}")
    return 0


# ── 自测：钉住「出身核对」「不当 0 分」「argmax 并列取最早」三件事 ────────────────
def selftest() -> int:
    import tempfile

    fails: list[str] = []
    n = 0

    def chk(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            fails.append(msg)

    # --- classify()：四种出身，逐个钉住 -------------------------------------
    chk(classify("/r/checkpoints/022000/pretrained_model", 22000, "022000") ==
        ("ok", "policy_ckpt -> checkpoints/022000（与目录名 step 22000 一致）"),
        "格号一致必须判 ok")
    st, why = classify("/r/checkpoints/last/pretrained_model", 22000, "020000")
    chk(st == "mismatch" and "020000" in why, "last 指着别的格必须判 mismatch，实得 %r %r" % (st, why))
    st, why = classify("/r/checkpoints/last/pretrained_model", 22000, "022000")
    chk(st == "ok" and "readlink" in why, "last 恰好指着本格应判 ok（带可信条件说明），实得 %r" % st)
    st, _ = classify("/r/checkpoints/last/pretrained_model", 22000, None)
    chk(st == "unverifiable", "last 读不出指向 ⇒ unverifiable，实得 %r" % st)
    st, _ = classify("/r/checkpoints/018000/pretrained_model", 22000, "022000")
    chk(st == "mismatch", "格号不符必须 mismatch，实得 %r" % st)
    st, _ = classify(None, 22000, "022000")
    chk(st == "unverifiable", "没写 policy_ckpt ⇒ unverifiable，实得 %r" % st)
    st, _ = classify("/some/where/else", 22000, "022000")
    chk(st == "unverifiable", "路径里没有 checkpoints/<格> ⇒ unverifiable，实得 %r" % st)
    chk(classify("/r/checkpoints/000100/pretrained_model", 100, None)[0] == "ok",
        "格号零填充必须按 %06d 比（step 100 -> 000100）")

    # --- 造一个假 run：好格 / 误标格(last 指别处) / 缺字段格 / 只有单向的格 -----
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run"
        (run / "checkpoints").mkdir(parents=True)
        # last -> 020000（复刻坑 38 当时的现场：终点格跑的时候 022000 还没 save）
        (run / "checkpoints" / "020000").mkdir()
        (run / "checkpoints" / "022000").mkdir()
        (run / "checkpoints" / "022000" / "pretrained_model").mkdir()
        (run / "checkpoints" / "022000" / "pretrained_model" / "model.safetensors").write_text("w")
        (run / "checkpoints" / "last").symlink_to(run / "checkpoints" / "020000")
        chk(last_target(run) == "020000", "last_target 应读出 020000，实得 %r" % last_target(run))

        sw = run / "sweep_rev"
        def put(name, step_ckpt, n, episodes=20, extra=None, drop_fields=False):
            d = sw / name
            d.mkdir(parents=True)
            j = {"episodes": episodes, "seed": 8000,
                 "policy_ckpt": f"{run}/checkpoints/{step_ckpt}/pretrained_model"}
            if not drop_fields:
                j["n_success"] = n
            if extra:
                j.update(extra)
            (d / "eval_summary.json").write_text(json.dumps(j))

        put("step_018000_rev", "018000", 9)                       # 好格
        put("step_020000_rev", "020000", 6)                        # 好格
        put("step_022000_rev", "last", 10)                         # 误标格：last -> 020000 ⇒ 剔除
        put("step_016000_rev", "016000", 99, drop_fields=True)     # 缺 n_success ⇒ 剔除
        (sw / "step_014000_rev").mkdir(parents=True)               # 没有 summary ⇒ 剔除
        (sw / "_trash_step_99999_rev").mkdir()                     # 不符合命名 ⇒ 忽略（不入 rejected）
        (sw / "step_012000_fwd").mkdir()
        (sw / "step_012000_fwd" / "eval_summary.json").write_text(json.dumps(
            {"episodes": 20, "seed": 3000, "n_success": 5,
             "policy_ckpt": f"{run}/checkpoints/012000/pretrained_model"}))

        curve, rejected, last_now = read_sweep(sw, run)
        chk(last_now == "020000", "read_sweep 要报出 last 的当前指向")
        chk(sorted(curve) == [12000, 18000, 20000], "合格格应是 12000(仅fwd)/18000/20000，实得 %r" % sorted(curve))
        chk(22000 not in curve, "误标的 22000 必须被剔除（坑 42 的核心）")
        rj = {(r["step"], r["direction"]): r["status"] for r in rejected}
        chk(rj.get((22000, "rev")) == "mismatch", "22000 应以 mismatch 被剔除，实得 %r" % rj.get((22000, "rev")))
        chk(rj.get((16000, "rev")) == "incomplete", "缺 n_success 的格应判 incomplete，实得 %r" % rj.get((16000, "rev")))
        chk(rj.get((14000, "rev")) == "missing", "没产物的格应判 missing，实得 %r" % rj.get((14000, "rev")))
        chk(99999 not in [r["step"] for r in rejected], "_trash_* 不该被当 step 收进来")
        chk(curve[18000]["rev"]["n_success"] == 9, "18000 的读数应原样保留")
        chk("provenance" in curve[18000]["rev"], "合格格也要留出身说明，方便审计")

        # 单向 rev：argmax 应是 18000（9 分），误标的 22000（10 分）不参与
        sc, inel = score_steps(curve, "rev")
        chk(sc == {18000: 9, 20000: 6}, "rev 记分应只剩 18000/20000，实得 %r" % sc)
        chk([i["step"] for i in inel] == [12000],
            "单向 rev 时 12000 只有 fwd ⇒ 应被取消资格，实得 %r" % inel)
        chk(select(sc) == (18000, 9, [18000]), "rev 选点应是 18000，实得 %r" % (select(sc),))

        # both：12000 只有 fwd、没有 rev ⇒ 取消资格，**不是** 5+0=5 分
        sc2, inel2 = score_steps(curve, "both")
        chk(12000 not in sc2, "读数不全的格不许进记分（坑 40③ 同源），实得 %r" % sc2)
        chk(any(i["step"] == 12000 for i in inel2), "12000 应出现在 ineligible 里")
        chk(sc2 == {}, "本例没有 fwd+rev 齐全的格 ⇒ both 应选不出点，实得 %r" % sc2)
        chk(select(sc2) == (None, None, []), "空记分要返回 (None, None, [])")

        # 并列取最早
        chk(select({5000: 8, 7000: 8, 9000: 3}) == (5000, 8, [5000, 7000]),
            "并列必须取更早的 step，实得 %r" % (select({5000: 8, 7000: 8, 9000: 3}),))

        # --include-unverifiable：把 last 读不出指向的格放回来
        (run / "checkpoints" / "last").unlink()
        (run / "checkpoints" / "last").mkdir()          # 真目录 ⇒ last 指向读不出
        chk(last_target(run) is None, "last 是真目录时应返回 None")
        c_strict, rej_strict, _ = read_sweep(sw, run, include_unverifiable=False)
        c_loose, rej_loose, _ = read_sweep(sw, run, include_unverifiable=True)
        chk(22000 not in c_strict, "last 读不出指向时，严格模式必须剔除 22000")
        chk(22000 in c_loose, "取证模式（--include-unverifiable）应把 22000 放回来")
        chk(len(rej_loose) < len(rej_strict), "取证模式剔除条数应更少")

        # 端到端：build_report 的字段齐不齐
        (run / "checkpoints" / "last").rmdir()
        (run / "checkpoints" / "last").symlink_to(run / "checkpoints" / "020000")
        rep = build_report(run, "sweep_rev", "rev", False)
        for k in ("generated_at", "run", "sweep", "direction", "rule", "curve", "scores",
                  "provenance", "selected_step", "selected_score", "tied_steps",
                  "selected_ckpt", "ckpt_exists", "discipline"):
            chk(k in rep, f"报告缺字段 {k}")
        chk(rep["selected_step"] == 18000 and rep["ckpt_exists"] is False,
            "18000 没建权重目录 ⇒ ckpt_exists 应为 False，实得 %r" % rep["ckpt_exists"])
        rep2 = build_report(run, "sweep_rev", "rev", False)
        chk(rep2["selected_step"] == 18000, "同盘重跑选点必须稳定")
        # rel() 在 MG_ROOT 外不崩
        chk(rel(Path("/tmp/definitely/not/under/mg")) == "/tmp/definitely/not/under/mg",
            "rel() 对 MG_ROOT 外的路径要原样返回")

    # --- 真实产物回归（只读，不改）：档 2e 的 sweep_rev ------------------------
    real = MG_ROOT / "runs" / "pi05_mix60f120r_s2e"
    if (real / "sweep_rev").is_dir():
        rep = build_report(real, "sweep_rev", "rev", False)
        chk(rep["provenance"]["rejected"] == [],
            "档 2e 的 sweep_rev 在阶段 E 修正后应无剔除格，实得 %r" % rep["provenance"]["rejected"])
        chk(rep["scores"].get("22000") == 7,
            "档 2e 真 022000 的 val 严格读数应是 7（阶段 E 补测），实得 %r" % rep["scores"].get("22000"))
        chk(rep["selected_step"] == 18000,
            "修正后 val argmax 应是 18000（9/20），实得 %r" % rep["selected_step"])
        stale = real / "ckpt_selection.json"
        if stale.is_file():
            old = json.loads(stale.read_text())
            chk(old.get("selected_step") == 22000 and old["curve"]["22000"]["rev"]["n_success"] == 10,
                "历史 ckpt_selection.json 应仍是误标版（22000/10 分）——它不许被覆盖")
    else:
        print("  (跳过真实产物回归：没有 runs/pi05_mix60f120r_s2e/sweep_rev)")

    print("选点工具钉子：%d 项检查，%d 项失败" % (n, len(fails)))
    for f in fails[:20]:
        if f:
            print("  FAIL " + f)
    real_fails = [f for f in fails if f]
    if real_fails:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
