#!/usr/bin/env python
"""超集对账：新收的数据集，前 N 条必须与旧数据集**逐比特相同**。

为什么这是承重墙，不是卫生检查：
  档 2c 之后如果要走「改配比 / 加反向数据」这条处方，最省钱的做法是重收一个
  60 正向 + 120 反向的数据集（mix60f120r），而不是从头设计新示范。这么做能成立的
  **唯一前提**是：新数据集的前 60 条反向示范 == 旧的 60 条，也就是新集是旧集的
  **严格超集**。只有这样，「120 反向模型 vs 60 反向模型」的差才能归因到
  *数据量/配比*；否则两次采集的物体位姿、噪声流、seed 顺序只要有一处漂移，
  差值里就混进了「换了一批数据」，比较直接作废（这是档 1 kcurve 作废过的同一类错）。

  mg_collect.py 的设计上它应该是超集：正向半边 noise_rng=default_rng(12345)、
  seed=seed_base+attempt，反向半边 seed=reverse_seed_base+attempt，且**只保留成功局**，
  所以同一参数重跑会走同一条确定性序列、多出来的只是尾部新 seed。
  但「设计上应该是」不等于「实测是」——本工具就是那把实测的尺。

口径：
  * 逐比特 = np.array_equal（float32 不做容差；有容差就等于承认漂移）。
  * 比对四样：seeds、episode_lengths、state、action 的前 sum(old_lengths) 帧。
  * 任何一项不符 => 退出码非 0，并打印**第一个**不符的位置（第几条 episode / 第几帧 /
    哪个通道 / 新旧值），便于直接定位是 seed 漂了还是噪声流漂了。
  * 出处必须打印（坑 30）：两个文件的路径、形状、dtype、seed 区间、帧数。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_check_superset.py \
        --old data/mix60f60r_rev_raw.npz --new data/mix60f120r_rev_raw.npz'
    bash -c 'source code/env.sh && $MG_PY code/mg_check_superset.py --selftest'
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG = Path(os.environ.get("MG_ROOT", str(HERE.parent)))
KEYS = ("seeds", "episode_lengths", "state", "action")


def _rel(p: Path) -> str:
    return str(p.relative_to(MG)) if str(p).startswith(str(MG)) else str(p)


def describe(p: Path) -> dict:
    d = dict(np.load(p))
    miss = [k for k in KEYS if k not in d]
    if miss:
        raise SystemExit("FATAL %s 缺键 %s（需要 %s）" % (_rel(p), miss, list(KEYS)))
    lens = d["episode_lengths"]
    info = {
        "path": p, "n_eps": int(len(lens)), "n_frames": int(lens.sum()),
        "seed_lo": int(d["seeds"].min()), "seed_hi": int(d["seeds"].max()),
        "state": d["state"].shape, "action": d["action"].shape,
        "dtypes": {k: str(d[k].dtype) for k in KEYS},
    }
    if d["state"].shape[0] != info["n_frames"]:
        raise SystemExit("FATAL %s 自相矛盾：episode_lengths 求和=%d 但 state 行数=%d"
                         % (_rel(p), info["n_frames"], d["state"].shape[0]))
    return info


def first_diff(a: np.ndarray, b: np.ndarray) -> str:
    """返回 a/b 第一个不同位置的描述（a 是旧、b 是新截断到同长度）。"""
    ne = np.nonzero(a != b)
    if len(ne) == 0 or len(ne[0]) == 0:
        return ""
    idx = tuple(int(x[0]) for x in ne)
    return "首个不符 位置%s 旧=%r 新=%r" % (idx, a[idx], b[idx])


def check(old: Path, new: Path, verbose: bool = True,
          forbid: tuple[tuple[int, int], ...] = ()) -> tuple[bool, list[str]]:
    oi, ni = describe(old), describe(new)
    L: list[str] = []
    L.append("旧 %s: %d 集 / %d 帧 / seed %d..%d / state %s %s"
             % (_rel(old), oi["n_eps"], oi["n_frames"], oi["seed_lo"], oi["seed_hi"],
                oi["state"], oi["dtypes"]["state"]))
    L.append("新 %s: %d 集 / %d 帧 / seed %d..%d / state %s %s"
             % (_rel(new), ni["n_eps"], ni["n_frames"], ni["seed_lo"], ni["seed_hi"],
                ni["state"], ni["dtypes"]["state"]))

    ok = True
    if ni["n_eps"] < oi["n_eps"]:
        L.append("FAIL 新集只有 %d 集 < 旧集 %d 集，不可能是超集" % (ni["n_eps"], oi["n_eps"]))
        return False, L
    if ni["n_frames"] < oi["n_frames"]:
        L.append("FAIL 新集帧数 %d < 旧集 %d" % (ni["n_frames"], oi["n_frames"]))
        ok = False

    o, n = dict(np.load(old)), dict(np.load(new))
    n_eps = oi["n_eps"]
    n_frames = oi["n_frames"]

    # 1) seeds / episode_lengths 前缀
    for key, m in (("seeds", n_eps), ("episode_lengths", n_eps)):
        a, b = o[key][:m], n[key][:m]
        if a.dtype != b.dtype:
            L.append("FAIL %s dtype 变了：%s -> %s（采集器换过？）" % (key, a.dtype, b.dtype))
            ok = False
        elif np.array_equal(a, b):
            L.append("ok   %s 前 %d 项逐比特相同" % (key, m))
        else:
            L.append("FAIL %s 前缀不同 -> %s" % (key, first_diff(a, b)))
            ok = False

    # 2) state / action 前 sum(old_lengths) 帧
    for key in ("state", "action"):
        a, b = o[key], n[key][:n_frames]
        if a.shape[1] != b.shape[1]:
            L.append("FAIL %s 通道数变了：%s -> %s" % (key, a.shape, b.shape))
            ok = False
            continue
        if a.dtype != b.dtype:
            L.append("FAIL %s dtype 变了：%s -> %s" % (key, a.dtype, b.dtype))
            ok = False
        if np.array_equal(a, b):
            L.append("ok   %s 前 %d 帧逐比特相同" % (key, n_frames))
        else:
            L.append("FAIL %s 前缀不同 -> %s" % (key, first_diff(a, b)))
            ok = False

    added_eps = ni["n_eps"] - oi["n_eps"]
    added_frames = ni["n_frames"] - oi["n_frames"]
    new_seeds = n["seeds"][n_eps:]
    if len(new_seeds):
        L.append("新增 %d 集 / %d 帧，新 seed 区间 %d..%d"
                 % (added_eps, added_frames, int(new_seeds.min()), int(new_seeds.max())))
        overlap = sorted(set(new_seeds.tolist()) & set(o["seeds"].tolist()))
        if overlap:
            L.append("FAIL 新增 seed 与旧 seed 重叠 %s（同一 seed 两个 task 会混淆）" % overlap[:10])
            ok = False
        else:
            L.append("ok   新增 seed 与旧 seed 无重叠")
    else:
        L.append("WARN 新集没有多出任何 episode（--reverse-episodes 没生效？）")
    # 3) 留出集碰撞：训练 seed 绝不能落进 TEST 窗口（否则门的读数被记忆污染）
    all_new_seeds = set(n["seeds"].tolist())
    for lo, hi in forbid:
        hit = sorted(s for s in all_new_seeds if lo <= s <= hi)
        if hit:
            L.append("FAIL 新集有 %d 个 seed 落进留出窗口 [%d,%d]：%s%s"
                     % (len(hit), lo, hi, hit[:10], " ..." if len(hit) > 10 else ""))
            ok = False
        else:
            L.append("ok   新集 %d 个 seed 全部避开留出窗口 [%d,%d]"
                     % (len(all_new_seeds), lo, hi))

    L.append("结论：%s" % ("**是严格超集** ✅" if ok else "**不是超集** ❌ 比较作废"))
    if verbose:
        print("\n".join(L))
    return ok, L


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True, help="旧 npz（如 data/mix60f60r_rev_raw.npz）")
    ap.add_argument("--new", required=True, help="新 npz（如 data/mix60f120r_rev_raw.npz）")
    ap.add_argument("--report", default="", help="把对账结果落盘到这个文件")
    ap.add_argument("--forbid-seed-range", action="append", default=[], metavar="LO:HI",
                    help="留出窗口（可重复）。新集任何 seed 落进去就判 FAIL，"
                         "例如 7000:7019 = 反向 TEST 的 20 个 seed")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    old = Path(a.old); new = Path(a.new)
    for p in (old, new):
        pp = p if p.is_absolute() else MG / p
        if not pp.is_file():
            print("FATAL 找不到 %s" % p, file=sys.stderr)
            return 2
    old = old if old.is_absolute() else MG / old
    new = new if new.is_absolute() else MG / new
    forbid = []
    for r in a.forbid_seed_range:
        try:
            lo, hi = r.split(":")
            forbid.append((int(lo), int(hi)))
        except ValueError:
            print("FATAL --forbid-seed-range 需要 LO:HI 形式，收到 %r" % r, file=sys.stderr)
            return 2
    ok, lines = check(old, new, forbid=tuple(forbid))
    if a.report:
        rp = Path(a.report)
        if not rp.is_absolute():
            rp = MG / rp
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text("# 超集对账\n\n```\n" + "\n".join(lines) + "\n```\n")
        print("[superset] 落盘 -> %s" % rp)
    return 0 if ok else 3


# ── selftest ──────────────────────────────────────────────────────────────────
def _mk(root: Path, name: str, lengths: list[int], seed0: int,
        bump_frame: int = -1, seed_gap: bool = False) -> Path:
    """造一个自洽的假 npz。

    state / action 必须走**各自独立**的 rng：否则 action 的内容会依赖 state 抽了多少行，
    于是「55 帧的文件」和「91 帧的文件」前缀天然不同 —— selftest 第一版就是这么假失败的。
    独立 rng 下，内容只由行号决定，前缀天然一致，才测得出真正的漂移。
    """
    n = int(sum(lengths))
    state = np.random.default_rng(7).standard_normal((n, 8)).astype(np.float32)
    action = np.random.default_rng(8).standard_normal((n, 7)).astype(np.float32)
    if bump_frame >= 0:
        state[bump_frame, 3] += 1e-6
    seeds = np.array([seed0 + i + (1 if (seed_gap and i > 2) else 0)
                      for i in range(len(lengths))], dtype=np.int64)
    lens = np.array(lengths, dtype=np.int32)
    p = root / name
    np.savez(p, state=state, action=action, episode_lengths=lens, seeds=seeds)
    return p if str(p).endswith(".npz") else Path(str(p) + ".npz")


def selftest() -> int:
    n_case = fails = 0

    def chk(name: str, cond: bool, detail: str = ""):
        nonlocal n_case, fails
        n_case += 1
        if cond:
            print("  ok   %s" % name)
        else:
            fails += 1
            print("  FAIL %s %s" % (name, detail))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base = [10, 12, 11, 9, 13]
        ext = base + [10, 14, 12]
        old = _mk(root, "old_raw.npz", base, 5000)
        new_exact = _mk(root, "new_raw.npz", ext, 5000)
        # 注意：_mk 用固定 rng 生成，同长度前缀的内容必然一致 => 这就是"超集"用例
        ok, lines = check(old, new_exact, verbose=False)
        chk("真超集判通过", ok, "\n".join(lines))
        chk("报告里写明新增集数", any("新增 3 集" in x for x in lines), "\n".join(lines))
        chk("报告里写明 seed 无重叠", any("无重叠" in x for x in lines))
        chk("报告打印出处（旧/新路径+帧数）", lines[0].startswith("旧 ") and lines[1].startswith("新 "))

        # 前缀里改一个 float => 必须 FAIL，且指出位置
        new_bump = _mk(root, "bump_raw.npz", ext, 5000, bump_frame=15)
        ok2, l2 = check(old, new_bump, verbose=False)
        chk("前缀漂 1e-6 也必须 FAIL（逐比特口径）", not ok2)
        chk("FAIL 指出首个不符位置", any("首个不符" in x for x in l2), "\n".join(l2))

        # episode_lengths 前缀不同 => FAIL（总帧数仍与 lengths 自洽，否则 describe 会先报错）
        drift = list(ext); drift[1] += 1
        new_len = _mk(root, "len_raw.npz", drift, 5000)
        ok3, l3 = check(old, new_len, verbose=False)
        chk("episode_lengths 漂移 FAIL", not ok3 and any("episode_lengths 前缀不同" in x for x in l3),
            "\n".join(l3))

        # seeds 前缀不同（第 3 条起 +1，模拟"跳过一个失败 seed"的顺序漂移）=> FAIL
        new_seed = _mk(root, "seed_raw.npz", ext, 5000, seed_gap=True)
        ok4, l4 = check(old, new_seed, verbose=False)
        chk("seeds 顺序漂移 FAIL", not ok4 and any("seeds 前缀不同" in x for x in l4), "\n".join(l4))

        # 新集更短 => 直接判不可能超集
        new_short = _mk(root, "short_raw.npz", base[:3], 5000)
        ok5, l5 = check(old, new_short, verbose=False)
        chk("新集更短 FAIL", not ok5 and any("不可能是超集" in x for x in l5))

        # 集数相同（没有新增）=> WARN 但不 FAIL
        new_same = _mk(root, "same_raw.npz", base, 5000)
        ok6, l6 = check(old, new_same, verbose=False)
        chk("等长时 WARN 不误判为 FAIL", ok6 and any("WARN" in x for x in l6), "\n".join(l6))

        # 缺键 => SystemExit
        bad = root / "bad_raw.npz"
        np.savez(bad, state=np.zeros((4, 8), np.float32),
                 action=np.zeros((4, 7), np.float32), episode_lengths=np.array([4], np.int32))
        try:
            describe(bad)
            chk("缺 seeds 键必须报错", False)
        except SystemExit as e:
            chk("缺 seeds 键必须报错", "缺键" in str(e), str(e))

        # 自相矛盾：lengths 求和 != state 行数
        inc = root / "inc_raw.npz"
        np.savez(inc, state=np.zeros((9, 8), np.float32), action=np.zeros((9, 7), np.float32),
                 episode_lengths=np.array([4, 4], np.int32), seeds=np.array([1, 2], np.int64))
        try:
            describe(inc)
            chk("帧数自相矛盾必须报错", False)
        except SystemExit as e:
            chk("帧数自相矛盾必须报错", "自相矛盾" in str(e), str(e))

        # 留出窗口碰撞
        leaky = _mk(root, "leak_raw.npz", ext, 7000)   # seed 7000.. 直接压在 TEST 窗口上
        okL, lL = check(old, leaky, verbose=False, forbid=((7000, 7019),))
        chk("训练 seed 撞 TEST 窗口 => FAIL", not okL and any("落进留出窗口" in x for x in lL),
            "\n".join(lL))
        okC, lC = check(old, new_exact, verbose=False, forbid=((7000, 7019), (2000, 2019)))
        chk("干净数据 => 两个窗口都报 ok", okC and sum("避开留出窗口" in x for x in lC) == 2,
            "\n".join(lC))
        okO, lO = check(old, new_exact, verbose=False)
        chk("不给 --forbid 时不做该项检查（向后兼容）",
            okO and not any("留出窗口" in x for x in lO))

        # 真实文件存在性（只读，不改动）
        real_old = MG / "data" / "mix60f60r_rev_raw.npz"
        if real_old.is_file():
            ri = describe(real_old)
            chk("真实反向 npz = 60 集/16032 帧（与 meta.json 对得上）",
                ri["n_eps"] == 60 and ri["n_frames"] == 16032, str(ri))
            chk("真实反向 seed 区间 5000..5092（坑32：非连续）",
                ri["seed_lo"] == 5000 and ri["seed_hi"] == 5092, str(ri))
            okR, lR = check(real_old, real_old, verbose=False,
                            forbid=((7000, 7019), (2000, 2019)))
            chk("现有反向训练数据确实避开 TEST 7000..7019 / G1 2000..2019",
                okR and not any("等长时" in x for x in lR), "\n".join(lR))
        else:
            print("  skip 真实 npz 不在（%s）" % real_old)

    print("\nselftest: %d/%d 通过" % (n_case - fails, n_case))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
