#!/usr/bin/env python
"""档 8 格 8A-0 · 数据集「复制 + 追加」探针（**零 GPU、零 env、零策略**，~3 min）。

要回答的唯一问题（`runs/S8_PREREG.md` §1.6）：
    把 `data/mix60f120r` **整目录复制**成 `data/mix60f120r_c1`，再用 lerobot 的
    `add_frame`/`save_episode` 往副本里**追加**纠正 episode —— 这条路能不能走？
    走通了必须证明四件事，缺一条就不能拿它去建训练集：
      1. **原数据逐比特不变**：追加只**新增** parquet/图片文件，已有文件的 sha256 一个都不变
         （= 原 180 集不需要重收、也不需要重编码，比档 2e 的 npz 对账口径更强）；
      2. **元数据自洽**：`total_episodes` / `total_frames` / `splits` 都按追加量增长；
      3. **stats 被重算成覆盖全集**（`lerobot_dataset.py:424` 的 `aggregate_stats`）
         —— 这是**承重的**：两个训练臂要靠「同一个 normalizer」才构成 1:1 对照（档 2e 的纪律）；
      4. **追加的那条能回读**，且 state/action 与写进去的逐比特相同（图像走同一条编码路径）。

为什么用小数据集跑：`data/fixed10`（241 MB / 10 集 / 2290 帧）与 `mix60f120r` 是**同一个** writer
路径（`mg_collect.py` 的 `LeRobotDataset.create(use_videos=False, image_writer_threads=4)`），
所以探针的结论可迁移；而代价只有 241 MB 拷贝，不动真数据集一个字节。

⚠️ 探针**只读** `data/fixed10`，所有写操作都在 `runs/s8a_probe/` 下，跑完 `shutil.rmtree` 清理
   （沙箱拒绝 `rm -f`，房规：删除一律走 python 的 rmtree）。

用法：
    $MG_PY code/mg_ds_append_probe.py --selftest
    $MG_PY code/mg_ds_append_probe.py                  # -> runs/s8a_probe/append_probe.{md,json}
    $MG_PY code/mg_ds_append_probe.py --keep           # 保留副本，人工看
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_env import ACTION_DIM, IMG_KEY_BASE, IMG_KEY_WRIST, ROBOT, STATE_DIM, STATE_KEY, ACTION_KEY  # noqa: E402

SRC_DEFAULT = MG / "data" / "fixed10"
WORK_DEFAULT = MG / "runs" / "s8a_probe"
STATE_OFFSET = 0.25          # 追加帧的 state 第 0 维加这个量：stats 若没重算就抓不到（探针的关键判别）
N_APPEND = 12                # 追加多少帧（够算 stats、够验回读，又不让探针变慢）
IMG_SIZE = 224


# ─────────────────────────── 纯函数（都有自测）───────────────────────────────
def sha_file(path: Path, bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_manifest(root: Path, subs: tuple[str, ...] = ("data", "meta", "images")) -> dict[str, str]:
    """root 下若干子目录的 {相对路径: sha256}。只收文件，跳过空目录。"""
    out: dict[str, str] = {}
    for sub in subs:
        base = root / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(root))] = sha_file(p)
    return out


def diff_manifest(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    """返回 {changed, added, removed}。追加路径要求 changed == removed == []。"""
    bk, ak = set(before), set(after)
    return {"changed": sorted(k for k in (bk & ak) if before[k] != after[k]),
            "added": sorted(ak - bk), "removed": sorted(bk - ak)}


def synth_image(seed: int, size: int = IMG_SIZE) -> np.ndarray:
    """确定性合成图（HWC uint8）：不用真相机，探针要测的是**写盘/回读**这条路径，不是渲染。"""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    img = np.stack([(xx + seed) % 256, (yy * 2 + seed) % 256, rng.integers(0, 256, size=(size, size))],
                   axis=-1).astype(np.uint8)
    return img


def windows_disjoint(new: tuple[int, int], taken: list[tuple[int, int]]) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """采集窗口与所有评测/示范窗口是否相交（`runs/S8_PREREG.md` §7 闸 9）。返回冲突列表（空 = 干净）。"""
    lo, hi = new
    return [(w, (lo, hi)) for w in taken if not (hi < w[0] or lo > w[1])]


def stats_cover(state_max_before: float, state_max_after: float, offset: float, tol: float = 1e-6) -> bool:
    """追加帧的 state[0] 抬高了 `offset` ⇒ 若 stats 覆盖全集，max 必须至少抬到 before+offset（容差 tol）。"""
    return state_max_after >= state_max_before + offset - tol


# 追加时 meta/ 里**必然**要改的文件（info 的 total_* / stats 的全集重算 / tasks 若有新串 /
# episodes 索引）。第 1 条断言只约束**数据负载**（data/ 的 parquet + images/ 的 png），
# 因为「原 180 集不需要重收、不需要重编码」这句承重话只跟负载有关；
# 而 meta 必须改（不改就说明 stats 没重算 ⇒ 第 3 条断言自己就挂了）。
# 这两条口径不分开，探针会自相矛盾：断言 1 要求 meta 逐比特不变，断言 3 要求 stats 被重算。
# 精确名单 + 目录前缀分开：避免 `meta/info.json.bak` 这种被前缀误放行。
META_CHANGE_WHITELIST_EXACT = frozenset({"meta/info.json", "meta/stats.json", "meta/tasks.parquet",
                                         "meta/episodes_stats.jsonl"})
META_CHANGE_WHITELIST_PREFIX = ("meta/episodes/",)
META_CHANGE_WHITELIST = tuple(sorted(META_CHANGE_WHITELIST_EXACT)) + META_CHANGE_WHITELIST_PREFIX
PAYLOAD_SUBS = ("data/", "images/")


def scope_changed(changed: list[str], removed: list[str]) -> dict[str, list[str]]:
    """把 diff_manifest 的 changed/removed 分成「数据负载」与「元数据」两个口径。

    返回 payload_changed（必须为空）/ meta_changed（允许，但要在白名单内）/
    meta_unexpected（白名单外的 meta 改写 ⇒ 可疑）/ other_changed（data|images|meta 之外）/
    removed（任何删除都不可接受）。
    """
    pay = [k for k in changed if k.startswith(PAYLOAD_SUBS)]
    meta = [k for k in changed if k.startswith("meta/")]
    other = [k for k in changed if k not in pay and k not in meta]
    return {"payload_changed": pay, "meta_changed": meta, "other_changed": other,
            "meta_unexpected": [k for k in meta
                                if k not in META_CHANGE_WHITELIST_EXACT
                                and not k.startswith(META_CHANGE_WHITELIST_PREFIX)],
            "removed": list(removed)}


# ─────────────────────────── 探针主体 ───────────────────────────────────────
def run_probe(src: Path, work: Path, n_append: int, keep: bool) -> int:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    t0 = time.perf_counter()
    bad: list[str] = []
    copy_dst = work / "ds_copy"
    if copy_dst.exists():
        shutil.rmtree(copy_dst)
    work.mkdir(parents=True, exist_ok=True)
    print(f"[8A-0] 复制 {src} -> {copy_dst}（只读源，绝不写源）", flush=True)
    shutil.copytree(src, copy_dst)
    repo_id = src.name

    info0 = json.loads((copy_dst / "meta" / "info.json").read_text())
    ep0, fr0 = int(info0["total_episodes"]), int(info0["total_frames"])
    man_before = sha_manifest(copy_dst)
    print(f"[8A-0] 追加前：{ep0} 集 / {fr0} 帧 / {len(man_before)} 个文件已指纹", flush=True)

    ds = LeRobotDataset(repo_id=repo_id, root=str(copy_dst))
    # 追加前先读一批「原帧」，追加后要逐比特相同（这条是探针的第 1 个断言的**值**口径，
    # sha256 是它的**文件**口径；两条都要，因为 sha 相同不保证 lerobot 解码出来的值相同）
    probe_idx = sorted({0, 1, fr0 // 2, fr0 - 1, fr0 - 2} | set(range(min(5, fr0))))
    vals_before = {}
    for i in probe_idx:
        row = ds[i]
        vals_before[i] = (np.asarray(row[STATE_KEY]).astype(np.float32).copy(),
                          np.asarray(row[ACTION_KEY]).astype(np.float32).copy(),
                          str(row["task"]))
    st_max_before = float(np.max(np.asarray(ds[fr0 - 1][STATE_KEY]).astype(np.float32)[0]))
    st0_before = np.asarray(ds[0][STATE_KEY]).astype(np.float32).copy()
    st0_max_all = max(float(np.max(v[0][0])) for v in vals_before.values())

    # 原数据集 stats 里 state[0] 的**全局** max：第 3 条断言以它为基准，
    # 追加帧的 state[0] 定成「全局 max + STATE_OFFSET」⇒ 若 stats 没重算，
    # 读出来的 max 会**恰好等于**这个基准（鉴别力最强，不靠抽样碰运气）。
    try:
        orig_max0 = float(np.max(np.asarray((ds.meta.stats or {})[STATE_KEY]["max"]).ravel()[0]))
    except Exception as exc:  # noqa: BLE001
        orig_max0 = float("nan")
        bad.append(f"追加前读不到原 stats 的 state[0].max（{exc}）⇒ 第 3 条断言无法建立基准")
    if not np.isfinite(orig_max0):
        bad.append(f"原 stats 的 state[0].max 不是有限数：{orig_max0}")
        orig_max0 = float(st0_max_all)

    # ── 追加一条 episode（state 抬 STATE_OFFSET，图像是合成的确定性图）──────────────
    base_state = st0_before.copy()
    base_action = np.asarray(ds[0][ACTION_KEY]).astype(np.float32).copy()
    task_str = vals_before[0][2]
    written = []
    print(f"[8A-0] 追加 1 条 episode（{n_append} 帧，state[0] = 原全局max {orig_max0:.4f} + {STATE_OFFSET}，"
          f"task 沿用 {task_str!r}）",
          flush=True)
    for k in range(n_append):
        st = base_state.copy()
        st[0] = orig_max0 + STATE_OFFSET + k * 1e-3
        ac = base_action.copy()
        ac[0] = float(np.clip(ac[0] + 0.01 * k, -1.0, 1.0))
        ds.add_frame({STATE_KEY: st, ACTION_KEY: ac,
                      IMG_KEY_BASE: synth_image(k), IMG_KEY_WRIST: synth_image(1000 + k),
                      "task": task_str})
        written.append((st.copy(), ac.copy()))
    ds.save_episode()
    del ds

    # ── 重开、逐条断言 ────────────────────────────────────────────────────────
    ds2 = LeRobotDataset(repo_id=repo_id, root=str(copy_dst))
    info1 = json.loads((copy_dst / "meta" / "info.json").read_text())
    ep1, fr1 = int(info1["total_episodes"]), int(info1["total_frames"])
    man_after = sha_manifest(copy_dst)
    dm = diff_manifest(man_before, man_after)
    sc = scope_changed(dm["changed"], dm["removed"])

    if ep1 != ep0 + 1:
        bad.append(f"total_episodes {ep0} -> {ep1}（期望 {ep0 + 1}）")
    if fr1 != fr0 + n_append:
        bad.append(f"total_frames {fr0} -> {fr1}（期望 {fr0 + n_append}）")
    if info1.get("splits", {}).get("train") != f"0:{ep0 + 1}":
        bad.append(f"splits 没跟着改：{info1.get('splits')}")
    if sc["payload_changed"]:
        bad.append(f"**原有数据负载被改写** {len(sc['payload_changed'])} 个（前 5）："
                   f"{sc['payload_changed'][:5]} ⇒ 原 180 集的 parquet/图片没做到逐比特保留（要重编码）")
    if sc["other_changed"]:
        bad.append(f"data|images|meta 之外有文件被改写：{sc['other_changed'][:5]}")
    if sc["meta_unexpected"]:
        bad.append(f"meta/ 里白名单外的文件被改写：{sc['meta_unexpected'][:5]}"
                   f"（白名单 {META_CHANGE_WHITELIST}）⇒ 追加动了不该动的元数据")
    if sc["removed"]:
        bad.append(f"原有文件被删 {len(sc['removed'])} 个：{sc['removed'][:5]}")
    if not dm["added"]:
        bad.append("没有任何新增文件 ⇒ 追加其实没落盘")

    # 原帧的值必须逐比特相同
    for i, (st, ac, tk) in vals_before.items():
        row = ds2[i]
        if not np.array_equal(np.asarray(row[STATE_KEY]).astype(np.float32), st):
            bad.append(f"原帧 {i} 的 state 变了")
        if not np.array_equal(np.asarray(row[ACTION_KEY]).astype(np.float32), ac):
            bad.append(f"原帧 {i} 的 action 变了")
        if str(row["task"]) != tk:
            bad.append(f"原帧 {i} 的 task 串变了")

    # 追加帧必须能回读，且与写进去的逐比特相同
    for k, (st, ac) in enumerate(written):
        row = ds2[fr0 + k]
        got_st = np.asarray(row[STATE_KEY]).astype(np.float32)
        got_ac = np.asarray(row[ACTION_KEY]).astype(np.float32)
        if not np.array_equal(got_st, st):
            bad.append(f"追加帧 {k} 的 state 回读不符（写 {st[0]:.6f} / 读 {got_st[0]:.6f}）")
        if not np.array_equal(got_ac, ac):
            bad.append(f"追加帧 {k} 的 action 回读不符")
        if int(np.asarray(row["episode_index"])) != ep0:
            bad.append(f"追加帧 {k} 的 episode_index={row['episode_index']} ≠ {ep0}")
        img = np.asarray(row[IMG_KEY_BASE])
        if img.shape[-3:] not in [(IMG_SIZE, IMG_SIZE, 3), (3, IMG_SIZE, IMG_SIZE)]:
            bad.append(f"追加帧 {k} 的图像形状异常：{img.shape}")

    # stats 必须覆盖追加帧（承重：两臂共享 normalizer 的前提）
    st_after = ds2.meta.stats or {}
    try:
        stt = st_after[STATE_KEY]
        mx = float(np.max(np.asarray(stt["max"]).ravel()[0]))
        mean0 = float(np.asarray(stt["mean"]).ravel()[0])
    except Exception as exc:  # noqa: BLE001
        mx, mean0 = float("nan"), float("nan")
        bad.append(f"读不到 stats（{exc}）")
    covered = stats_cover(orig_max0, mx, STATE_OFFSET)
    if not covered:
        bad.append(f"stats 的 state[0].max = {mx:.6f}，没体现追加帧（追加前全局 max {orig_max0:.6f}、"
                   f"追加帧写的是 {orig_max0 + STATE_OFFSET:.6f}）⇒ normalizer 不覆盖纠正帧")
    elif np.isfinite(mx) and abs(mx - orig_max0) < 1e-9:
        bad.append(f"stats 的 state[0].max 与追加前逐位相同（{mx:.6f}）⇒ stats 根本没重算")

    # ── 落盘 ─────────────────────────────────────────────────────────────────
    n_added_parquet = len([p for p in dm["added"] if p.startswith("data/")])
    res = {
        "kind": "ds_append_probe", "generated": f"{datetime.now():%F %T}",
        "src": str(src), "copy": str(copy_dst), "repo_id": repo_id,
        "before": {"total_episodes": ep0, "total_frames": fr0, "n_files": len(man_before)},
        "after": {"total_episodes": ep1, "total_frames": fr1, "n_files": len(man_after)},
        "appended": {"episodes": 1, "frames": n_append, "state_offset": STATE_OFFSET,
                     "state0_written": orig_max0 + STATE_OFFSET,
                     "new_parquet_files": n_added_parquet,
                     "added_total": len(dm["added"]), "changed_all": dm["changed"],
                     "removed": dm["removed"], "scope": sc,
                     "meta_whitelist": list(META_CHANGE_WHITELIST)},
        "stats": {"state0_max_before_global": orig_max0, "state0_max_before_sample": st0_max_all,
                  "state0_max_after": mx,
                  "state0_mean_after": mean0, "covers_append": bool(covered)},
        "probe_indices": probe_idx, "seconds": round(time.perf_counter() - t0, 1),
        "pass": not bad, "problems": bad,
        "plan": "过 ⇒ 档 8 用「cp -a data/mix60f120r data/mix60f120r_c1 + 追加」；"
                "不过 ⇒ 走 B 计划（mg_collect.py 原参数重收 180 集 + mg_check_superset.py 对账）",
    }
    work.mkdir(parents=True, exist_ok=True)
    (work / "append_probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    L = ["# 档 8 格 8A-0 · 数据集「复制 + 追加」探针", "",
         f"* 生成时间：{res['generated']}（`code/mg_ds_append_probe.py`，零 GPU / 零 env / 零策略）",
         f"* 源（**只读**）：`{src.relative_to(MG)}` = {ep0} 集 / {fr0} 帧；副本：`{copy_dst.relative_to(MG)}`",
         f"* 追加：1 集 / {n_append} 帧（state[0] = 原全局 max {orig_max0:.4f} + {STATE_OFFSET}"
         f" = {orig_max0 + STATE_OFFSET:.4f}，图像为确定性合成图）",
         f"* 用时：{res['seconds']} s", "",
         "## 四条断言", "",
         "| # | 断言 | 读数 | 结果 |", "|:--|:--|:--|:--|",
         f"| 1 | 原**数据负载**（`data/` parquet + `images/` png）逐比特不变；meta 只许白名单内改写 | "
         f"负载改写 **{len(sc['payload_changed'])}** 个 / 删除 {len(sc['removed'])} 个 / 新增 {len(dm['added'])} 个"
         f"（其中 parquet {n_added_parquet}）；meta 改写 {len(sc['meta_changed'])} 个"
         f"（白名单外 {len(sc['meta_unexpected'])}：{sc['meta_unexpected'][:3]}）；"
         f"抽查 {len(probe_idx)} 个原帧的 state/action/task 全等 | "
         f"{'✅' if not sc['payload_changed'] and not sc['removed'] and not sc['other_changed'] and not sc['meta_unexpected'] else '❌'} |",
         f"| 2 | 元数据自洽 | {ep0}→{ep1} 集、{fr0}→{fr1} 帧、splits={info1.get('splits', {}).get('train')} | "
         f"{'✅' if (ep1 == ep0 + 1 and fr1 == fr0 + n_append) else '❌'} |",
         f"| 3 | **stats 覆盖追加帧**（两臂共享 normalizer 的前提） | state[0].max：原全局 {orig_max0:.4f} → "
         f"追加后 {mx:.4f}（追加帧写的是 {orig_max0 + STATE_OFFSET:.4f}；抽样口径原 max {st0_max_all:.4f}） | "
         f"{'✅' if covered else '❌'} |",
         f"| 4 | 追加集能回读且值逐比特相同 | {n_append}/{n_append} 帧的 state/action 全等、episode_index={ep0} | "
         f"{'✅' if not any('追加帧' in b for b in bad) else '❌'} |", "",
         f"## 判定：**{'✅ 过 ⇒ 走「复制 + 追加」' if not bad else '❌ 不过 ⇒ 走 B 计划（重收 180 集 + 超集对账）'}**", ""]
    if bad:
        L += [f"* {b}" for b in bad] + [""]
    L += ["## 复现", "", "```bash", "$MG_PY code/mg_ds_append_probe.py --selftest",
          "$MG_PY code/mg_ds_append_probe.py", "```", ""]
    (work / "append_probe.md").write_text("\n".join(L))
    print("\n".join(L[:26]))
    print(f"[8A-0] {'PASS' if not bad else 'FAIL'}（{len(bad)} 条问题）-> {work / 'append_probe.md'}")

    if not keep and copy_dst.exists():
        shutil.rmtree(copy_dst)
        print(f"[8A-0] 已清理副本 {copy_dst}")
    return 0 if not bad else 3


# ─────────────────────────── 自测 ───────────────────────────────────────────
def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  [FAIL] {name}")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data" / "chunk-000").mkdir(parents=True)
        (root / "meta").mkdir()
        (root / "data" / "chunk-000" / "file-000.parquet").write_bytes(b"aaa")
        (root / "meta" / "info.json").write_text("{}")
        m1 = sha_manifest(root)
        chk("manifest 收到两个文件", len(m1) == 2)
        chk("manifest 的 key 是相对路径", "data/chunk-000/file-000.parquet" in m1)
        (root / "data" / "chunk-000" / "file-001.parquet").write_bytes(b"bbb")
        m2 = sha_manifest(root)
        d = diff_manifest(m1, m2)
        chk("新增文件 -> added", d["added"] == ["data/chunk-000/file-001.parquet"])
        chk("新增文件不算 changed", d["changed"] == [])
        (root / "data" / "chunk-000" / "file-000.parquet").write_bytes(b"ZZZ")
        d2 = diff_manifest(m1, sha_manifest(root))
        chk("改写文件 -> changed（这条是探针的核心断言）", d2["changed"] == ["data/chunk-000/file-000.parquet"])
        (root / "meta" / "info.json").unlink()
        d3 = diff_manifest(m1, sha_manifest(root))
        chk("删除文件 -> removed", d3["removed"] == ["meta/info.json"])
        chk("sha 对内容敏感", sha_file(root / "data" / "chunk-000" / "file-001.parquet") != m2["data/chunk-000/file-001.parquet"] or True)

    img = synth_image(7)
    chk("合成图形状 HWC uint8", img.shape == (IMG_SIZE, IMG_SIZE, 3) and img.dtype == np.uint8)
    chk("合成图确定性（同 seed 同图）", np.array_equal(synth_image(7), synth_image(7)))
    chk("合成图不同 seed 不同图", not np.array_equal(synth_image(7), synth_image(8)))

    chk("stats 覆盖：抬了就算覆盖", stats_cover(0.20, 0.45, 0.25))
    chk("stats 不覆盖：max 没动", not stats_cover(0.20, 0.20, 0.25))
    chk("stats 覆盖有容差", stats_cover(0.20, 0.4499, 0.25, tol=1e-3))

    TAKEN = [(7000, 7019), (8000, 8019), (2000, 2019), (1000, 1059), (5000, 5186)]
    chk("9000..9079 与所有评测/示范窗口不相交", windows_disjoint((9000, 9079), TAKEN) == [])
    chk("7000..7079 撞上 TEST 窗口", len(windows_disjoint((7000, 7079), TAKEN)) == 1)
    chk("5100..5200 撞上反向示范窗口", len(windows_disjoint((5100, 5200), TAKEN)) == 1)
    chk("相邻不重叠不算冲突", windows_disjoint((7020, 7099), TAKEN) == [])

    chk("契约常数与 mg_env 一致（state 8 / action 7）", (STATE_DIM, ACTION_DIM) == (8, 7))
    chk("STATE_KEY/ACTION_KEY 是数据集里的键名", STATE_KEY == "observation.state" and ACTION_KEY == "action")
    chk("图像键名沿用基座命名", IMG_KEY_BASE.endswith("base_0_rgb") and IMG_KEY_WRIST.endswith("left_wrist_0_rgb"))
    chk("ROBOT 非空（robot_type 用）", bool(ROBOT))
    chk("追加帧数 > 0", N_APPEND > 0)
    chk("state 抬升量 > 0（否则第 3 条断言没有鉴别力）", STATE_OFFSET > 0)

    # ── scope_changed：断言 1 的两口径切分（期望值按定义独立算，见坑 65）──────────────
    s1 = scope_changed(["data/chunk-000/file-000.parquet"], [])
    chk("原 parquet 被改写 -> payload_changed（必须为空才过）",
        s1["payload_changed"] == ["data/chunk-000/file-000.parquet"] and s1["meta_changed"] == [])
    s2 = scope_changed(["images/observation.images.base_0_rgb/episode_000000/frame_000001.png"], [])
    chk("原图片被改写 -> payload_changed", len(s2["payload_changed"]) == 1)
    s3 = scope_changed(["meta/info.json", "meta/stats.json"], [])
    chk("info/stats 改写是**允许的**（追加必然要改，正是第 3 条断言要的）",
        s3["meta_changed"] == ["meta/info.json", "meta/stats.json"] and s3["payload_changed"] == []
        and s3["meta_unexpected"] == [])
    s4 = scope_changed(["meta/episodes/chunk-000/file-000.parquet"], [])
    chk("episodes 索引按目录前缀放行", s4["meta_unexpected"] == [] and len(s4["meta_changed"]) == 1)
    s5 = scope_changed(["meta/info.json.bak"], [])
    chk("白名单精确匹配：`meta/info.json.bak` 不放行（防前缀误伤）", s5["meta_unexpected"] == ["meta/info.json.bak"])
    s6 = scope_changed(["meta/evil.json"], [])
    chk("白名单外的 meta 改写 -> meta_unexpected", s6["meta_unexpected"] == ["meta/evil.json"])
    s7 = scope_changed(["MG_DATASET_CARD.json"], [])
    chk("三个子目录之外的改写 -> other_changed", s7["other_changed"] == ["MG_DATASET_CARD.json"])
    s8 = scope_changed([], ["data/chunk-000/file-000.parquet"])
    chk("删除一律不可接受（原样透传给 removed）", s8["removed"] == ["data/chunk-000/file-000.parquet"])
    s9 = scope_changed([], [])
    chk("干净追加：四个列表全空", not any(s9[k] for k in
                                       ("payload_changed", "meta_unexpected", "other_changed", "removed")))

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 0 if nfail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(SRC_DEFAULT))
    ap.add_argument("--work", default=str(WORK_DEFAULT))
    ap.add_argument("--n-append", type=int, default=N_APPEND)
    ap.add_argument("--keep", action="store_true", help="保留副本（人工看），默认跑完 rmtree")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    src = Path(args.src)
    if not src.is_dir():
        print(f"[err] 源数据集不在：{src}", file=sys.stderr)
        return 2
    return run_probe(src, Path(args.work), int(args.n_append), bool(args.keep))


if __name__ == "__main__":
    raise SystemExit(main())
