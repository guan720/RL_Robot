#!/usr/bin/env python3
"""B 线：定位 Lift 评测路径的不可复现来源（分层探针）。

背景（2026-09-28 实测）：同一 checkpoint、同一 pinned seeds、同一评测器，
仅改 OMP_NUM_THREADS 得到三个不同结果；固定 OMP=1 连跑两次仍不同。
这使「pinned seeds 5000-5019」协议产生的是**确定性错觉**，跨臂比较失去基础。

本探针把一次评测拆成四层，逐层比对两次运行是否 bitwise 相同：
  L0 环境构造      object_geom / 初始 qpos
  L1 reset         reset_contact(seed) 后的 obs 与 cube_pos
  L2 策略前向      同一 obs 下模型输出的 chunk
  L3 动力学        同一下发命令序列 20 步后的 cube_pos / qpos

判读：
  L1 就不同 -> reset/播种路径有未钉死的随机源（最可能是 robosuite inner.rng 或叶子 sampler）
  L1 同、L2 不同 -> torch CPU 归约顺序（线程数 / 非确定性 kernel）
  L1、L2 同、L3 不同 -> MuJoCo 接触求解的线程相关归约
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.env_factory import (PINNED_OBJECT_SEED, contact_object_geom,  # noqa: E402
                                 make_contact_env, reset_contact)
from scripts.train_act_lift import ChunkPolicy  # noqa: E402


def h(x):
    return hashlib.sha256(np.ascontiguousarray(np.asarray(x, dtype=np.float64)).tobytes()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="runs/infra/b_act_lift_mb_hist1_seed0/model_final.pt")
    ap.add_argument("--seeds", type=int, nargs="+", default=[5000, 5001, 5002])
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--repeats", type=int, default=2, help="同进程内重复建环境+评测的次数")
    ap.add_argument("--open-loop", action="store_true",
                    help="L3 用固定命令序列（不看观测），把动力学与策略解耦")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    hist_n = int(ck.get("history", 1))
    model = ChunkPolicy(int(ck["obs_dim"]), int(ck["chunk_length"]))
    model.load_state_dict(ck["model"]); model.eval()
    mean = np.asarray(ck["obs_mean"], np.float32); std = np.asarray(ck["obs_std"], np.float32)

    rec = {"omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
           "torch_get_num_threads": torch.get_num_threads(),
           "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
           "torch_version": torch.__version__, "repeats": a.repeats, "runs": []}

    for rep in range(a.repeats):
        env = make_contact_env("lift", horizon=300, reward_shaping=True, obs_mode="state")
        run = {"repeat": rep, "geom_hash": hashlib.sha256(json.dumps(contact_object_geom(env, "lift", PINNED_OBJECT_SEED), sort_keys=True).encode()).hexdigest()[:16], "episodes": []}
        for seed in a.seeds:
            obs = reset_contact(env, seed)
            raw = env._env._get_observations()
            ep = {"seed": seed,
                  "L1_obs_hash": h(obs), "L1_cube_pos": [round(float(v), 9) for v in np.asarray(raw["cube_pos"])],
                  "L1_qpos_hash": h(np.asarray(env._env.sim.data.qpos)),
                  "L2_first_chunk": None, "L3_cube_pos": None, "L3_qpos_hash": None}
            o = np.asarray(obs, dtype=np.float32)
            hist = [o.copy() for _ in range(hist_n)]
            with torch.no_grad():
                chunk = model(torch.tensor(((np.concatenate(hist) - mean) / std)[None]))[0].numpy()
            ep["L2_first_chunk"] = [round(float(v), 9) for v in chunk[0]]
            cmds = ([np.full(7, 0.0, dtype=np.float32) for _ in range(a.steps)] if a.open_loop
                    else [chunk[j % len(chunk)] for j in range(a.steps)])
            for c in cmds:
                obs, _, term, trunc, _ = env.step(np.asarray(c, dtype=np.float32))
                if term or trunc:
                    break
            raw = env._env._get_observations()
            ep["L3_cube_pos"] = [round(float(v), 9) for v in np.asarray(raw["cube_pos"])]
            ep["L3_qpos_hash"] = h(np.asarray(env._env.sim.data.qpos))
            run["episodes"].append(ep)
        env.close()
        rec["runs"].append(run)

    # 逐层比对
    verdict = {}
    r0, r1 = rec["runs"][0], rec["runs"][-1]
    verdict["L0_geom"] = (r0["geom_hash"] == r1["geom_hash"])
    for lay, key in (("L1_obs", "L1_obs_hash"), ("L1_qpos", "L1_qpos_hash"),
                     ("L2_chunk", "L2_first_chunk"), ("L3_cube", "L3_cube_pos"),
                     ("L3_qpos", "L3_qpos_hash")):
        ok = all(a_ [key] == b_[key] for a_, b_ in zip(r0["episodes"], r1["episodes"]))
        verdict[lay] = bool(ok)
    rec["verdict"] = verdict
    first_bad = next((k for k, v in verdict.items() if not v), None)
    rec["first_diverging_layer"] = first_bad
    rec["interpretation"] = {
        "L0_geom": "环境构造期物体几何未钉死",
        "L1_obs": "reset/播种路径有未钉死的随机源（robosuite inner.rng 或叶子 sampler）",
        "L1_qpos": "reset 后机器人初始 qpos 不可复现",
        "L2_chunk": "torch CPU 前向不可复现（线程数 / 非确定性归约）",
        "L3_cube": "MuJoCo 接触求解不可复现（同一命令序列给出不同物理）",
        "L3_qpos": "MuJoCo 步进不可复现",
    }.get(first_bad, "全部一致：本进程内可复现，需跨进程再测")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("omp_num_threads", "torch_get_num_threads",
                                          "verdict", "first_diverging_layer", "interpretation")},
                     indent=2, ensure_ascii=False))
    for run in rec["runs"]:
        print("  repeat %d: %s" % (run["repeat"], [(e["seed"], e["L1_cube_pos"][2], e["L3_cube_pos"][2])
                                                   for e in run["episodes"]]))


if __name__ == "__main__":
    main()
PYCMD
