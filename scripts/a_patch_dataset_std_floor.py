#!/usr/bin/env python3
"""L1 数值炸穿修复：给 LeRobotDataset 的 `meta/stats.json` 里的 std 加**相对下限**，派生出新数据集。

为什么需要（监管备忘 2026-09-28 增补二 §1/§5.A②、`docs/b_normalization_incident_20260928.md`）：
LeRobot 官方 `processor/normalize_processor.py:335` 的 MEAN_STD 分支是 `denom = std + eps`
（`eps = 1e-8`，同文件 :94），**没有下限保护**。Lift 的 `observation.state` 里 `joint_pos_cos` 系
（dim 7/9/11）对关节角在 0 附近是二阶平坦的（cos θ ≈ 1 − θ²/2），teacher 数据里 std 低至
5.07e-04（trimdone0）/ 1.28e-03（未裁剪 train24）。闭环一旦偏离 teacher 轨迹，这几维被放大
10^1~10^4 倍喂进网络 → 首层激活炸穿 → 末层 tanh 饱和 → 策略退化成 ±1 抖动。
**开环指标看不到这件事**，所以它一直伪装成「能力不足」。

A 线自己的实证（`runs/infra/lerobot_act_env_20260928/gate_strict_trimdone0_minmax_k2_*`）：
K=2 trimdone0 六个训练 seed 里，seed0 的 `norm_input_blown_frames_frac = 0.2120`、
闭环 |x| 峰值 93.4，被门禁判 `measurement_invalid`；同配方 seed4 的 blown_frac = 0.0000、
受控成功 19/20。**同一配方下 L1 是否咬合是随训练 seed 变的**，这正是种子方差的机制之一。

为什么不是改用 MIN_MAX：MIN_MAX 分支只在 `denom == 0` 时才把分母换成 eps
（`normalize_processor.py:350-354`）。近常量维的 `max − min` 不为 0 但极小，同样被放大，
所以「STATE=MIN_MAX」不是修复（监管备忘 增补二 §0 已把「MIN_MAX 免疫 L1」的口头表述作废）。

修复公式（B §6.1 的相对下限，逐维、按该维自己的量级缩放，不是绝对常数）：
    absmax_j = max(|min_j|, |max_j|)                       # 该维原始数据的绝对幅度
    floor_j  = rel_floor * max(absmax_j, abs_floor)        # rel_floor 默认 1e-2
    std_j    = max(std_j, floor_j)
只抬 std、不动 mean/min/max：归一化中心不变，只把「近常量维的增益」压到 ≤ 1/rel_floor 倍。
副作用是这几维在训练分布内的归一化幅度从 ±20 压到 ±2 左右（即网络见到的输入范围变窄），
**训练与推理用的是同一份 stats**（LeRobot 把 stats 烘进 checkpoint 的
`policy_preprocessor_step_*_normalizer_processor.safetensors`），因此不存在 B 警告的
train/inference 截断不一致问题。

只 patch 走 MEAN_STD 的特征（默认 `observation.state` + `observation.environment_state`）。
`action` 在本项目所有臂里都是 MIN_MAX，patch 它的 std 对归一化没有影响，默认不动，
以保持「单变量」。

派生而不修改源：源数据集目录一个字节都不改，`--out` 是新目录（数据文件整树复制，
本项目的数据集只有 ~1 MB）。源目录仍被 09-28 早段的所有臂引用，改它会毁掉跨臂可比性。

用法（必须用装了 lerobot 的解释器）：
    /root/venvs/lerobot_act/bin/python scripts/a_patch_dataset_std_floor.py \
        --src runs/infra/lerobot_act_lift_v30/train24_trimdone0 \
        --out runs/infra/lerobot_act_lift_v30/train24_trimdone0_stdfloor

训练完核对烘进 checkpoint 的 stats 是否真的带上了下限：
    /root/venvs/lerobot_act/bin/python scripts/a_patch_dataset_std_floor.py \
        --check-ckpt runs/infra/lerobot_act_lift_v30/<job> \
        --expect-manifest runs/infra/lerobot_act_lift_v30/train24_trimdone0_stdfloor/std_floor_manifest.json
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

STATS_REL = "meta/stats.json"
MANIFEST_REL = "std_floor_manifest.json"
DEFAULT_FEATURES = ("observation.state", "observation.environment_state")


def _floor_for(std: np.ndarray, lo: np.ndarray, hi: np.ndarray,
               rel_floor: float, abs_floor: float) -> np.ndarray:
    absmax = np.maximum(np.abs(lo), np.abs(hi))
    return rel_floor * np.maximum(absmax, abs_floor)


def patch(src: Path, out: Path, features: tuple[str, ...], rel_floor: float,
          abs_floor: float, overwrite: bool) -> dict:
    if not (src / STATS_REL).exists():
        raise SystemExit(f"[错误] {src / STATS_REL} 不存在，源不是 v3.0 LeRobotDataset")
    if out.exists():
        if not overwrite:
            raise SystemExit(f"[错误] {out} 已存在（--overwrite 才覆盖；不会删除源）")
        shutil.move(str(out), str(out.parent / f".trash_{out.name}"))
    shutil.copytree(src, out)

    stats_path = out / STATS_REL
    stats = json.loads(stats_path.read_text())
    report: dict = {"src": str(src), "out": str(out), "stats_file": str(stats_path),
                    "rel_floor": rel_floor, "abs_floor": abs_floor, "features": {}}

    for feat in features:
        if feat not in stats:
            raise SystemExit(f"[错误] stats.json 里没有特征 {feat}（现有：{sorted(stats)}）")
        entry = stats[feat]
        std = np.asarray(entry["std"], dtype=np.float64)
        lo = np.asarray(entry["min"], dtype=np.float64)
        hi = np.asarray(entry["max"], dtype=np.float64)
        if not (std.shape == lo.shape == hi.shape):
            raise SystemExit(f"[错误] {feat} 的 std/min/max 维度不一致")
        floor = _floor_for(std, lo, hi, rel_floor, abs_floor)
        raised = std < floor
        new_std = np.maximum(std, floor)
        # 训练期归一化后的 |x| 上界：(max(|lo-mean|,|hi-mean|))/std，用来看增益被压掉多少
        mean = np.asarray(entry["mean"], dtype=np.float64)
        span = np.maximum(np.abs(lo - mean), np.abs(hi - mean))
        gain_old = np.where(std > 0, span / np.maximum(std, 1e-12), 0.0)
        gain_new = np.where(new_std > 0, span / np.maximum(new_std, 1e-12), 0.0)
        entry["std"] = [float(v) for v in new_std]
        report["features"][feat] = {
            "dim": int(std.size),
            "n_raised": int(raised.sum()),
            "raised_dims": [
                {"dim": int(j), "std_old": float(std[j]), "std_new": float(new_std[j]),
                 "absmax": float(max(abs(lo[j]), abs(hi[j]))),
                 "norm_absmax_old": float(gain_old[j]), "norm_absmax_new": float(gain_new[j]),
                 "gain_reduction_x": (float(gain_old[j] / gain_new[j]) if gain_new[j] > 0 else None)}
                for j in np.flatnonzero(raised)
            ],
            "min_std_old": float(std.min()), "min_std_new": float(new_std.min()),
            "max_norm_absmax_old": float(gain_old.max()), "max_norm_absmax_new": float(gain_new.max()),
        }
        stats_path.write_text(json.dumps(stats, indent=2))

    # 只 patch stats.json：训练读路径是 LeRobotDatasetMetadata.__init__ -> load_stats(root)
    # （lerobot/datasets/lerobot_dataset.py:169 -> utils.py:319 读 meta/stats.json）。
    # meta/episodes/*.parquet 里的逐 episode stats 不参与训练期归一化，保留原值以便追溯。
    report["episodes_parquet_patched"] = False
    report["episodes_parquet_note"] = (
        "训练期归一化只读 meta/stats.json（lerobot_dataset.py:169）；逐 episode stats 保留原值，"
        "作为「源数据集未被篡改」的证据。")
    report["expected_ckpt_std"] = {
        feat: [float(v) for v in np.asarray(stats[feat]["std"], dtype=np.float64)]
        for feat in features if feat in stats
    }
    (out / MANIFEST_REL).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def check_ckpt(ckpt: Path, expect_manifest: Path, tol: float) -> int:
    from safetensors.torch import load_file

    expect = json.loads(expect_manifest.read_text())["expected_ckpt_std"]
    cand = sorted(ckpt.glob("**/policy_preprocessor_step_*_normalizer_processor.safetensors"))
    if not cand:
        raise SystemExit(f"[错误] {ckpt} 下找不到 normalizer safetensors")
    got = load_file(cand[-1])
    bad = 0
    print(f"checkpoint normalizer: {cand[-1]}")
    for feat, want in expect.items():
        key = f"{feat}.std"
        if key not in got:
            print(f"  [缺失] {key} 不在 checkpoint 里"); bad += 1; continue
        arr = got[key].numpy().astype(np.float64)
        want_arr = np.asarray(want, dtype=np.float64)
        if arr.shape != want_arr.shape:
            print(f"  [维度不符] {key}: ckpt={arr.shape} expect={want_arr.shape}"); bad += 1; continue
        diff = np.abs(arr - want_arr)
        n_bad = int((diff > tol).sum())
        worst = int(diff.argmax())
        print(f"  {key}: dim={arr.size} min_std={arr.min():.6e} "
              f"不匹配={n_bad} 最大偏差={diff[worst]:.3e}@dim{worst}")
        bad += n_bad
    print("CKPT_STD_FLOOR_OK" if bad == 0 else f"CKPT_STD_FLOOR_MISMATCH n={bad}")
    return 0 if bad == 0 else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", help="源 v3.0 LeRobotDataset 根目录（只读，不会被修改）")
    ap.add_argument("--out", help="派生数据集根目录（新建）")
    ap.add_argument("--features", default=",".join(DEFAULT_FEATURES),
                    help="要加 std 下限的特征，逗号分隔（默认只含走 MEAN_STD 的两个 obs 特征）")
    ap.add_argument("--rel-floor", type=float, default=1e-2,
                    help="std 相对下限系数：floor = rel_floor * max(absmax, abs_floor)")
    ap.add_argument("--abs-floor", type=float, default=1e-3,
                    help="absmax 的绝对兜底，防止全零维把 floor 也压成 0")
    ap.add_argument("--overwrite", action="store_true",
                    help="--out 已存在时先挪到 .trash_<name> 再重建（不删除、不动源）")
    ap.add_argument("--check-ckpt", help="校验模式：checkpoint 目录")
    ap.add_argument("--expect-manifest", help="校验模式：派生数据集里的 std_floor_manifest.json")
    ap.add_argument("--tol", type=float, default=1e-6, help="校验模式的 std 绝对容差")
    args = ap.parse_args()

    if args.check_ckpt:
        if not args.expect_manifest:
            raise SystemExit("[错误] --check-ckpt 需要同时给 --expect-manifest")
        raise SystemExit(check_ckpt(Path(args.check_ckpt), Path(args.expect_manifest), args.tol))

    if not (args.src and args.out):
        raise SystemExit("[错误] 构建模式需要 --src 与 --out")
    feats = tuple(f.strip() for f in args.features.split(",") if f.strip())
    rep = patch(Path(args.src), Path(args.out), feats, args.rel_floor, args.abs_floor, args.overwrite)
    print(f"派生数据集: {rep['out']}")
    for feat, info in rep["features"].items():
        print(f"  {feat}: dim={info['dim']} 抬升={info['n_raised']} "
              f"min_std {info['min_std_old']:.3e} -> {info['min_std_new']:.3e} "
              f"训练期归一化 |x| 上界 {info['max_norm_absmax_old']:.2f} -> {info['max_norm_absmax_new']:.2f}")
        for d in info["raised_dims"]:
            print(f"      dim{d['dim']:>2d}: std {d['std_old']:.3e} -> {d['std_new']:.3e} "
                  f"(增益压缩 {d['gain_reduction_x']:.1f}x)" if d["gain_reduction_x"] else
                  f"      dim{d['dim']:>2d}: std {d['std_old']:.3e} -> {d['std_new']:.3e}")
    print(f"manifest: {Path(rep['out']) / MANIFEST_REL}")


if __name__ == "__main__":
    main()
