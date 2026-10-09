#!/usr/bin/env python
"""固定脚本/PD base controller 的 Lift 基线，使用与 residual 相同的 pinned 题集。"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from envs.robosuite_lift import RobosuiteLift
from harness.env_factory import PINNED_OBJECT_SEED, pinned_object_rng, reset_contact
from scripts.train_pickplace_sac import _state_obs, _new_controller

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--horizon", type=int, default=300); ap.add_argument("--seed-base", type=int, default=5000)
    args = ap.parse_args()
    with pinned_object_rng(PINNED_OBJECT_SEED):
        env = RobosuiteLift(obs_mode="state", horizon=args.horizon, reward_shaping=True)
    rows=[]
    for i in range(args.episodes):
        obs = reset_contact(env, args.seed_base+i); ctrl = _new_controller(env, "lift")
        succ=False
        for t in range(args.horizon):
            obs, r, term, trunc, info = env.step(ctrl(_state_obs(env)))
            succ = succ or bool(info.get("success", False))
            if term or trunc: break
        rows.append({"seed":args.seed_base+i,"success":succ,"tasks_done":int(env.tasks_done),"steps":t+1,"phases":ctrl.log})
    env.close(); n=sum(int(x["success"]) for x in rows)
    out=ROOT/"runs"/f"{datetime.now():%Y%m%d_%H%M%S}_lift_base"; out.mkdir(parents=True,exist_ok=True)
    result={"controller":"scripted_lift_base","episodes":args.episodes,"success":n,"success_rate":n/args.episodes,"tasks_done":sum(x["tasks_done"] for x in rows),"per_episode":rows}
    (out/"result.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)); print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__ == "__main__": main()
