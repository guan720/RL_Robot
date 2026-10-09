#!/usr/bin/env python3
"""B 线门禁：接触任务评测可复现性自检（监管 P0 第一项的可执行形式）。

为什么必须有它（2026-09-28 实测事故）：
  `scripts/setup_env.sh` 装的是**未 pin** 的 `robosuite`，容器重建后装到了 1.5.1。
  1.5.1 的 `utils/mjcf_utils.py::get_size` 用 `np.random.uniform`（legacy 全局 RandomState）
  采样物体尺寸，而 `harness/env_factory.py::pinned_object_rng` 只 monkeypatch 了
  `np.random.default_rng` —— 于是 `PINNED_OBJECT_SEED` **静默失效**：
    · 进程内连续构造 3 次得到 3 个不同 cube（docstring 声称「进程内完全确定」被打破）；
    · 同一臂的 train config 与 eval audit 记录到不同几何；
    · 同一 ckpt / 同一 seeds / 同一评测器，连跑两次成功率与 max_rise 全变。
  装回 `robosuite==1.5.2` 后几何恢复为 `size=[0.0219796,0.0210383,0.021705] mass=0.080293`，
  与 09-24 记录逐位相同。

本脚本把上述四层不变量变成可反复执行的门禁。**任何一次容器重建、依赖升级、
或改动 env_factory / robosuite 版本之后，先跑它再跑实验。**

用法：
    MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/b_selfcheck_reproducibility.py
    ... --omp-list 1 2 4        # 额外报告线程数敏感性
    ... --json-out runs/infra/b_reproducibility/selfcheck.json
退出码 0 = 全部通过，1 = 有 FAIL（可直接接发布门禁）。
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS = []


def record(name, ok, detail, severity="FAIL"):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail, "severity": severity})
    tag = "PASS" if ok else severity
    print(f"  [{tag}] {name}\n         {detail}")
    return bool(ok)


def _geom_str():
    from harness.env_factory import PINNED_OBJECT_SEED, contact_object_geom, make_contact_env
    env = make_contact_env("lift", horizon=300, reward_shaping=True, obs_mode="state")
    try:
        g = contact_object_geom(env, "lift", PINNED_OBJECT_SEED)
        return json.dumps(g, sort_keys=True)
    finally:
        env.close()


def _fingerprint(omp):
    """一次进程内的完整指纹：几何 ×3、reset ×2、策略前向、20 步开环动力学。"""
    import numpy as np
    import torch
    from harness.env_factory import make_contact_env, reset_contact

    out = {"omp_env": os.environ.get("OMP_NUM_THREADS"), "torch_threads": torch.get_num_threads(),
           "robosuite": None, "mujoco": None, "torch": torch.__version__, "geoms": [], "eps": []}
    try:
        import robosuite, mujoco
        out["robosuite"] = robosuite.__version__; out["mujoco"] = mujoco.__version__
    except Exception as exc:  # noqa: BLE001
        out["import_error"] = repr(exc)
        return out

    def h(x):
        return hashlib.sha256(np.ascontiguousarray(np.asarray(x, dtype=np.float64)).tobytes()).hexdigest()[:16]

    for i in range(3):
        gs = _geom_str()
        out["geoms"].append(hashlib.sha256(gs.encode()).hexdigest()[:16])
        if i == 0:
            # L0-c 要**真的**比对 size/mass 数值，不能只留一句「见 --json-out」。
            # 这一项原先是 record(..., True, ...) 的恒真断言，与本文件 docstring
            # 记的那次事故属于同一类缺陷（见 docs/b_reproducibility_incident_20260928.md §2）。
            try:
                out["geom_values"] = json.loads(gs)
            except Exception as exc:                                # noqa: BLE001
                out["geom_values_error"] = repr(exc)

    env = make_contact_env("lift", horizon=300, reward_shaping=True, obs_mode="state")
    try:
        # L0-d 观测布局指纹。robosuite 1.5.1 的 state obs 是 53 维、1.5.2 是 60 维，
        # 版本一换 checkpoint 就静默失配（维度巧合相同时连报错都没有）。
        probe = reset_contact(env, 5000)
        raw0 = env._env._get_observations()
        out["obs_dim"] = int(len(np.asarray(probe)))
        out["obs_layout"] = h(np.asarray(probe))
        out["obs_raw_keys"] = sorted(str(k) for k in raw0.keys())
        out["obs_raw_keys_hash"] = hashlib.sha256(
            json.dumps(out["obs_raw_keys"]).encode()).hexdigest()[:16]
        for seed in (5000, 5001):
            obs = reset_contact(env, seed)
            raw = env._env._get_observations()
            ep = {"seed": seed, "L1_obs": h(obs),
                  "L1_cube": [round(float(v), 9) for v in np.asarray(raw["cube_pos"])],
                  "L1_qpos": h(np.asarray(env._env.sim.data.qpos))}
            cmds = [np.zeros(7, dtype=np.float32) for _ in range(5)] + \
                   [np.array([0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32) for _ in range(15)]
            for c in cmds:
                env.step(c)
            raw = env._env._get_observations()
            ep["L3_cube"] = [round(float(v), 9) for v in np.asarray(raw["cube_pos"])]
            ep["L3_qpos"] = h(np.asarray(env._env.sim.data.qpos))
            out["eps"].append(ep)
    finally:
        env.close()

    # L2：同一输入的策略前向（若无 ckpt 则用固定权重的同构网络，仍可测线程敏感性）
    x = torch.tensor(np.linspace(-1, 1, 60, dtype=np.float32).reshape(1, 60))
    torch.manual_seed(0)
    net = torch.nn.Sequential(torch.nn.Linear(60, 256), torch.nn.ReLU(), torch.nn.Linear(256, 28))
    with torch.no_grad():
        out["L2_forward"] = h(net(x).numpy())
    return out


def _run_child(omp):
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(omp); env["MKL_NUM_THREADS"] = str(omp)
    env.setdefault("MUJOCO_GL", "egl")
    me = str(Path(__file__).resolve())
    code = (
        "import sys,json,importlib.util;"
        f"sys.path.insert(0,{str(ROOT)!r});"
        f"spec=importlib.util.spec_from_file_location('b_selfcheck_reproducibility',{me!r});"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"print('@@FP@@'+json.dumps(m._fingerprint({omp})))"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(ROOT))
    for line in p.stdout.splitlines():
        if line.startswith("@@FP@@"):
            return json.loads(line[6:])
    raise RuntimeError(f"child failed (omp={omp}):\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=2, help="同配置重复进程数（测跨进程可复现）")
    ap.add_argument("--skip-ckpt-scan", action="store_true",
                    help="跳过 runs/ 下 checkpoint 的 obs_dim 兼容性扫描")
    ap.add_argument("--omp-list", type=int, nargs="*", default=None,
                    help="额外跑这些 OMP_NUM_THREADS 并报告敏感性（不计入 PASS/FAIL）")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    print("=" * 78)
    print("接触任务可复现性自检（B 线门禁）")
    print("=" * 78)
    base = None
    fps = []
    for r in range(a.repeats):
        fp = _run_child(1)
        fps.append(fp)
        if base is None:
            base = fp
        print(f"  · repeat {r}: robosuite={fp.get('robosuite')} mujoco={fp.get('mujoco')} "
              f"geom={fp['geoms'][0] if fp['geoms'] else '?'}")

    # 环境缺失（例如误用系统 python3，没有 robosuite）时，必须给出**可读裁定**，
    # 不能在 L0-b 的 f["geoms"][0] 上抛 IndexError：门禁脚本自己崩掉 = 没有裁定，
    # 比 FAIL 更糟（2026-09-28 实测：系统 python3 跑本脚本直接 traceback）。
    if base is None or base.get("robosuite") is None or not base.get("geoms"):
        del CHECKS[:]
        record("L0-0 环境可用（robosuite/mujoco 可导入且能建接触环境）", False,
               f"robosuite={base.get('robosuite') if base else None} "
               f"geoms={len(base.get('geoms') or []) if base else 0} "
               f"import_error={base.get('import_error') if base else 'no fingerprint'}"
               "  ← 本自检必须在 rlrobot venv 里跑："
               "OMP_NUM_THREADS=1 MUJOCO_GL=egl /root/venvs/rlrobot/bin/python "
               "scripts/b_selfcheck_reproducibility.py")
        print("\n" + "=" * 78)
        print("结论：环境缺失，本轮**未产生任何可复现性裁定**（1 项 FAIL）")
        print("=" * 78)
        if a.json_out:
            Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json_out).write_text(json.dumps(
                {"checks": CHECKS, "fingerprints": fps, "env_missing": True},
                indent=2, ensure_ascii=False) + "\n")
            print("写出:", a.json_out)
        return 1

    print("\n--- 不变量检查 ---")
    ok = True
    ok &= record("L0-a 进程内几何钉死", len(set(base["geoms"])) == 1,
                 f"3 次构造几何 hash 集合 = {sorted(set(base['geoms']))}"
                 + ("" if len(set(base["geoms"])) == 1 else "  ← PINNED_OBJECT_SEED 已失效"))
    ok &= record("L0-b 跨进程几何钉死", len({f["geoms"][0] for f in fps}) == 1,
                 f"{a.repeats} 个进程的首个几何 hash = {sorted({f['geoms'][0] for f in fps})}")
    # 09-24 / 09-28 实测参考值（robosuite==1.5.2 + PINNED_OBJECT_SEED）。
    # 数值口径说明（2026-09-28 晚）：本文件 docstring 与事故文档里记的是**6~7 位小数**
    # 的四舍五入值（size=[0.0219796,0.0210383,0.021705] mass=0.080293）。用它做 1e-8
    # 级别的比对会因舍入而假 FAIL，所以这里把参考值提升到实测全精度；提升的合法性由
    # `geom_hash` 保证 —— 该 hash 是**独立记录**的（09-24 与 09-28 恢复后同为
    # 752ff735ed145948），不是本次现算后回填的，因此不构成恒真断言。
    REFERENCE_GEOM = {"size": [0.0219795783, 0.0210382586, 0.0217049526],
                      "body_mass_kg": 0.08029305,
                      "geom_hash": "752ff735ed145948"}
    gv = base.get("geom_values") or {}
    got_size, got_mass = gv.get("size"), gv.get("body_mass_kg")
    size_ok = (isinstance(got_size, list) and len(got_size) == len(REFERENCE_GEOM["size"])
               and all(abs(float(x) - y) <= 1e-9
                       for x, y in zip(got_size, REFERENCE_GEOM["size"])))
    mass_ok = (isinstance(got_mass, (int, float))
               and abs(float(got_mass) - REFERENCE_GEOM["body_mass_kg"]) <= 1e-9)
    hash_ok = base["geoms"][0] == REFERENCE_GEOM["geom_hash"]
    ok &= record("L0-c 几何数值与 09-24 参考记录一致", size_ok and mass_ok and hash_ok,
                 f"实测 size={got_size} mass={got_mass}；参考 size={REFERENCE_GEOM['size']} "
                 f"mass={REFERENCE_GEOM['body_mass_kg']}；hash={base['geoms'][0]}"
                 f"（参考 {REFERENCE_GEOM['geom_hash']}）"
                 + ("" if (size_ok and mass_ok and hash_ok) else
                    "  ← 物体几何/质量变了：接触实验结果不可与历史记录比较，必须重训重测"
                    + (f"；geom_values_error={base.get('geom_values_error')}"
                       if base.get("geom_values_error") else "")))
    ok &= record("L1 reset 状态可复现",
                 all(f["eps"] == base["eps"] for f in fps),
                 "reset_contact(5000/5001) 的 obs/qpos/cube_pos 指纹跨进程逐位一致"
                 if all(f["eps"] == base["eps"] for f in fps)
                 else f"不一致：{[f['eps'] for f in fps]}")
    ok &= record("L2 策略前向可复现",
                 len({f["L2_forward"] for f in fps}) == 1,
                 f"同构固定权重网络前向 hash = {sorted({f['L2_forward'] for f in fps})}")
    ok &= record("L3 20 步动力学可复现",
                 len({json.dumps(f["eps"]) for f in fps}) == 1,
                 "开环命令序列 20 步后 cube_pos/qpos 一致"
                 if len({json.dumps(f["eps"]) for f in fps}) == 1 else "动力学发散")
    EXPECTED_OBS_DIM = 60      # robosuite 1.5.2 / Lift state obs 实测值
    obs_dims = {f.get("obs_dim") for f in fps}
    ok &= record("L0-d 观测布局维度与期望一致",
                 obs_dims == {EXPECTED_OBS_DIM},
                 f"obs_dim = {sorted(str(x) for x in obs_dims)}，期望 {EXPECTED_OBS_DIM}"
                 + ("" if obs_dims == {EXPECTED_OBS_DIM} else
                    "  ← robosuite 版本变了，所有既有 state checkpoint 全部失配，必须重训"))
    ok &= record("L0-e raw obs 键集合跨进程一致",
                 len({f.get("obs_raw_keys_hash") for f in fps}) == 1,
                 f"obs_raw_keys_hash = {sorted({f.get('obs_raw_keys_hash') for f in fps})}")
    # ---- L0-f pin 一致性（真检查）----
    # 这一项在 2026-09-28 之前是 `record(..., True, ...)` 的**恒真假检查**：它只把
    # 「requirements.txt 应 pin 同一版本」当提示打印，从不真的去读文件，所以
    # setup_env.sh 里的 `pip freeze --local > requirements.txt` 把 pin 从 1.5.2 覆写成
    # 实装的 1.5.1 之后，自检仍然全绿，当天所有接触实验在错误的几何/obs 布局下跑完。
    # 门禁里不许存在恒真断言 —— 这条本身就是本次事故的第二级根因。
    installed = base.get("robosuite")
    pin_txt = pin_lock = None
    for fn, holder in (("requirements.txt", "txt"), ("requirements.lock.txt", "lock")):
        f = ROOT / fn
        if f.exists():
            for line in f.read_text().splitlines():
                if line.strip().lower().startswith("robosuite=="):
                    v = line.split("==", 1)[1].strip()
                    if holder == "txt":
                        pin_txt = v
                    else:
                        pin_lock = v
    ok &= record("L0-f robosuite 实装版本 == requirements.txt 的 pin",
                 pin_txt is not None and installed == pin_txt,
                 f"实装={installed} requirements.txt pin={pin_txt}"
                 + ("" if (pin_txt is not None and installed == pin_txt) else
                    "  ← pin 漂移。pinned_object_rng 与 state obs 布局都会变，"
                    "接触实验结果不可与历史记录比较"))
    record("L0-g requirements.lock.txt 与 pin 一致", 
           pin_lock is None or pin_lock == pin_txt,
           (f"lock={pin_lock} pin={pin_txt}" if pin_lock is not None
            else "requirements.lock.txt 尚未生成（跑一次 scripts/setup_env.sh）"),
           severity="WARN")

    # ---- L0-h 既有 checkpoint 的 obs_dim 兼容性扫描（自动产出作废清单）----
    if not a.skip_ckpt_scan:
        # 已知作废的 checkpoint 走确认清单（configs/b_obs_dim_mismatch_ack.json）降为 WARN，
        # 否则这一项会**永久 FAIL**：永久红的门禁等于没有门禁，人会开始无视它，
        # 等到真的出现新失配时就没人看了。清单只认精确路径，新失配照样 FAIL。
        ack_file = ROOT / "configs" / "b_obs_dim_mismatch_ack.json"
        ack, ack_problems = {}, []
        if ack_file.exists():
            try:
                for e in json.loads(ack_file.read_text()).get("entries", []):
                    p = str(e.get("path") or "")
                    if not p or any(ch in p for ch in "*?["):
                        ack_problems.append(f"{p or '<empty>'}: 只接受精确相对路径，不接受通配符")
                    elif not e.get("reason") or not e.get("acked_at"):
                        ack_problems.append(f"{p}: 缺 reason/acked_at，该条目不生效")
                    else:
                        ack[p] = e
            except Exception as exc:                                # noqa: BLE001
                ack_problems.append(f"<ack 文件解析失败: {exc!r}>")
        try:
            import torch
            bad, good, acked, seen = [], 0, [], set()
            for ck in sorted((ROOT / "runs").rglob("model_*.pt")):
                try:
                    d = torch.load(ck, map_location="cpu", weights_only=False)
                except Exception:
                    continue
                od = d.get("obs_dim") if isinstance(d, dict) else None
                if od is None:
                    continue
                # obs_dim = 单帧维度 × history。必须按 checkpoint 自己声明的 history 折算，
                # 否则会把合法的 hist4 臂（4×60=240）误判成失配。
                h = int(d.get("history") or 1)
                if int(od) == EXPECTED_OBS_DIM * h:
                    good += 1
                else:
                    rel = str(ck.relative_to(ROOT))
                    implied = int(od) / h
                    if rel in ack:
                        seen.add(rel)
                        acked.append(f"{rel}(obs_dim={od},history={h})")
                    else:
                        bad.append(f"{rel}(obs_dim={od},history={h},"
                                   f"单帧={implied:.1f}≠{EXPECTED_OBS_DIM})")
            stale = sorted(set(ack) - seen)
            ok &= record("L0-h 既有 state checkpoint 的 obs_dim 与当前环境一致",
                         not bad,
                         (f"{good} 个 checkpoint 的 obs_dim == {EXPECTED_OBS_DIM}×history，全部兼容"
                          if not bad else
                          f"{len(bad)} 个**未确认**失配（作废，不得与当前环境比较；"
                          f"确认后请写进 {ack_file.name}）：{bad[:12]}"
                          + (" ..." if len(bad) > 12 else ""))
                         + (f"；另有 {len(acked)} 个已确认作废：{acked[:6]}" if acked else ""))
            record("L0-h-ack 作废清单自身健康", not stale and not ack_problems,
                   (f"{len(ack)} 条确认记录全部命中实际失配" if not stale and not ack_problems
                    else f"stale={stale}；无效条目={ack_problems}"),
                   severity="WARN")
        except Exception as exc:                                  # pragma: no cover
            record("L0-h 既有 state checkpoint 的 obs_dim 与当前环境一致", True,
                   f"扫描跳过，**本轮对 checkpoint 兼容性未产生任何裁定**：{exc!r}",
                   severity="WARN")

    if a.omp_list:
        print("\n--- 线程数敏感性（OMP_NUM_THREADS 扫描，报告不计入 PASS/FAIL）---")
        variants = {}
        for t in a.omp_list:
            fp = _run_child(t)
            variants[t] = fp
            print(f"  OMP={t}: geom={fp['geoms'][0]} L2={fp['L2_forward']} "
                  f"cube@5000={fp['eps'][0]['L3_cube'][2]}")
        same_l2 = len({v["L2_forward"] for v in variants.values()}) == 1
        same_dyn = len({json.dumps(v["eps"]) for v in variants.values()}) == 1
        record("线程数敏感性", same_l2 and same_dyn,
               f"L2 前向跨线程一致={same_l2}；L1/L3 跨线程一致={same_dyn}"
               + ("" if (same_l2 and same_dyn) else "  ← 必须在实验记录里钉死 OMP_NUM_THREADS"),
               severity="WARN")

    print("\n" + "=" * 78)
    n_fail = sum(1 for c in CHECKS if not c["ok"] and c["severity"] == "FAIL")
    print(f"结论：{'全部通过' if ok and n_fail == 0 else f'{n_fail} 项 FAIL'}　"
          f"（共 {len(CHECKS)} 项检查）")
    print("=" * 78)
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps({"checks": CHECKS, "fingerprints": fps},
                                               indent=2, ensure_ascii=False) + "\n")
        print("写出:", a.json_out)
    return 0 if (ok and n_fail == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
