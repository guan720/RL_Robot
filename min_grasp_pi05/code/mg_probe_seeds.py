import sys
import numpy as np
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from mg_env import SingleArmGraspEnv

env = SingleArmGraspEnv(img_size=64)
raw_keys = None
rows = []
for s in (0, 1000, 1001, 1002, 2000, 2001):
    env.reset(seed=s)
    op = env.object_pos
    r = env._last_obs_raw
    eq = r.get("object0_quat")
    rows.append((s, op, eq, env.eef_pos, env.target_xy))
    if raw_keys is None:
        raw_keys = [k for k in r.keys() if "object" in k or "quat" in k]
print("obj-related raw keys:", raw_keys)
for s, op, eq, eef, txy in rows:
    print(f"seed={s:>5}  can={np.round(op,4)}  quat={None if eq is None else np.round(np.asarray(eq),3)}  eef={np.round(eef,4)}  target={np.round(txy,3)}")
ops = np.stack([r[1] for r in rows])
print("can xy spread over seeds: x range", round(float(np.ptp(ops[:,0])),4), " y range", round(float(np.ptp(ops[:,1])),4))
print("eef identical across seeds:", bool(np.allclose(np.stack([r[3] for r in rows]), np.stack([r[3] for r in rows])[0], atol=1e-6)))
env.close()
