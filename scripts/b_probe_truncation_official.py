#!/usr/bin/env python3
"""B②：把归一化输入截断的**因果探针**移植到 A 的官方 LeRobot checkpoint 上。

监管指派：`rl_harness_supervision/supervisor_memo_20260928.md` 增补二 §5.B②
  「把截断因果探针移植到 A 的官方 checkpoint 上跑一次，判定 L1 是否在 A 臂上实际咬合
    （咬合强度决定重分类是形式还是实质）」。

为什么必须真跑而不能靠已有字段推断：A 的官方臂 `norm_input_blown_frames_frac` 全是 0，
按门禁的**全局**规则（`max|x| > 训练期全局上界 23.85`）它们干净得不能再干净；
但同一批产物的**逐维**越界率是 0.22~0.98（`norm_input_out_of_range_frames_frac`）。
两个口径差这么多，说明「L1 咬不咬」取决于你用哪把尺子 —— 只有真的把输入夹住再跑一遍，
才能知道夹住以后行为变不变。这是因果测量，不是相关性推断。

单变量纪律：两臂**同一 checkpoint、同一 seeds、同一 horizon、同一 replan、同一评测器版本**，
只差 `--clip-norm-input` 一个开关。为保证「同一评测器版本」，基线臂也**当场重跑**，
不直接引用 A 之前产出的 JSON（那份可能是旧版评测器跑的）。

三道防自欺的护栏（本仓已反复吃过亏，见 docs/b_reproducibility_incident_20260928.md）：
  1. checkpoint 权重 sha256 必须与参考产物记录的一致，否则权重变了、比较无意义 -> 拒绝启动；
  2. 重跑的基线臂必须**逐位复现**参考产物的 raw 与四类失效计数，否则基线不可复现，
     任何差异都不能归因给截断 -> 裁定降为 inconclusive；
  3. 咬合强度的阈值在**跑之前**写死在本文件顶部，并给出锚定依据，不允许事后挑阈值。

只读纪律：本脚本**不修改** A 的评测器，只以子进程调用它（先例：
`scripts/b_train_act_lift_fixed.py` 以 import 方式复用 A 的代码）。产物写在 `runs/infra/b_*`。

用法（必须用 lerobot venv 的解释器跑评测子进程，本脚本自身可用任一 python）：
    source /root/venvs/rlrobot/bin/activate
    python3 scripts/b_probe_truncation_official.py
    python3 scripts/b_probe_truncation_official.py --clip 3.0 --episodes 20
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "b_gate_controlled_success.py"
A_EVAL = "scripts/eval_lerobot_act_runtime.py"
DEFAULT_REF = ("runs/infra/lerobot_act_env_20260928/"
               "official_act_truth20_train24_lr1e-5_actionminmax_s20k_gatefields.json")
# 注意：`/root/venvs/lerobot_act` **没有 robosuite/mujoco**，跑不了闭环（本脚本第一次冒烟
# 就是用它，两臂都 ModuleNotFoundError，护栏 3 正确地把整次探测判为 FATAL 而不是给个空裁定）。
# `lerobot_eval` 才是同时具备 lerobot 0.4.4 + torch 2.6.0+cu124 + robosuite 1.5.2 的那个，
# 与 A 官方产物 `versions` 字段记录的逐项一致。
DEFAULT_VENV_PY = "/root/venvs/lerobot_eval/bin/python"

# ---- 预先登记的判定规则（跑之前写死；锚定依据见下）----
# 锚：`runs/infra/b_gate_sensitivity/report.json` 里**同一个臂**在门禁阈值 ±0.005 网格上
#     受控成功数就在 0→2 之间摆动。也就是说 ±2 局是「已知噪声带」，不是信号。
#     因此把「实质咬合」的门槛设在 3 局（15%/20 局）以上，低于它只算形式性。
BITE_SUBSTANTIVE_CTRL = 3      # |Δ受控成功| >= 3 局 -> 实质
BITE_SUBSTANTIVE_RAW = 5       # |Δraw| >= 5 局 -> 实质（raw 口径噪声更大，门槛相应放宽）
COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")


def load_gate():
    spec = importlib.util.spec_from_file_location("b_gate", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GateArgs:
    def __init__(self, gate):
        self.rise_cap = gate.RISE_CAP
        self.final_rise = gate.FINAL_RISE_MIN
        self.assist_off = False


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def counts(row):
    a = (row.get("accounts") or {}).get("policy_independent", {}) or {}
    return {k: a.get(k) for k in COUNT_KEYS}


def per_seed(row):
    """裁定行的逐局视图：{seed: (raw, verdict)}。用于**按 seed 交集**比对复现性。"""
    return {str(e.get("seed")): (bool(e.get("verdict") != "unjudged"), e.get("verdict"),
                                 e.get("max_rise"), e.get("final_rise"))
            for e in (row.get("per_episode") or [])}


def raw_by_seed(path):
    d = json.loads(Path(path).read_text())
    rows = d.get("rows") or d.get("per_episode") or []
    return {str(r.get("seed")): bool(r.get("success_raw", r.get("success", False))) for r in rows}


def env_fingerprint(venv_py: str) -> dict:
    """取评测子进程将要用的解释器的关键版本，供与 requirements pin / A 的产物记录比对。"""
    code = ("import importlib,json\n"
            "out={}\n"
            "for m in ('torch','lerobot','robosuite','mujoco'):\n"
            "    try: out[m]=getattr(importlib.import_module(m),'__version__','?')\n"
            "    except Exception: out[m]=None\n"
            "import torch; out['cuda_available']=bool(torch.cuda.is_available())\n"
            "print(json.dumps(out))\n")
    r = subprocess.run([venv_py, "-c", code], cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout or "")[-400:]}
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:                               # noqa: BLE001
                pass
    return {"error": "无法解析版本输出", "stdout_tail": r.stdout[-400:]}


def pinned_robosuite() -> str | None:
    try:
        for line in (ROOT / "requirements.txt").read_text().splitlines():
            s = line.strip()
            if s.lower().startswith("robosuite") and "==" in s:
                return s.split("==", 1)[1].strip()
    except Exception:                                       # noqa: BLE001
        pass
    return None


def run_arm(venv_py, ckpt, out, clip, episodes, seed0, horizon, replan, log):
    cmd = [venv_py, A_EVAL, "--ckpt", ckpt, "--out", str(out),
           "--episodes", str(episodes), "--seed0", str(seed0), "--horizon", str(horizon)]
    if replan:
        cmd += ["--replan-every", str(replan)]
    if clip is not None:
        cmd += ["--clip-norm-input", str(clip)]
    log.append(" ".join(cmd))
    print("  $ %s" % " ".join(cmd))
    t0 = time.time()
    env = {**os.environ, "OMP_NUM_THREADS": "1", "MUJOCO_GL": "egl"}
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env)
    dt = time.time() - t0
    logfile = Path(str(out) + ".log")
    logfile.write_text("CMD: %s\nRC: %d\nELAPSED: %.1fs\n\n--- stdout ---\n%s\n--- stderr ---\n%s"
                       % (" ".join(cmd), r.returncode, dt, r.stdout, r.stderr))
    print("    rc=%d  %.1fs  日志 %s" % (r.returncode, dt, logfile.name))
    if r.returncode != 0:
        print((r.stderr or r.stdout or "")[-1500:])
    return r.returncode == 0, dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-artifact", default=DEFAULT_REF,
                    help="A 的官方产物，用于取 checkpoint 与权重 sha256")
    ap.add_argument("--clip", type=float, default=3.0, help="截断幅度 C（与 B 线 clip 扫描同口径）")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--replan-every", type=int, default=None,
                    help="默认**继承参考产物**的 replan_every；跨口径比较没有意义，"
                         "实测 44 个官方臂横跨 8 种 (chunk,n_action,replan) 组合")
    ap.add_argument("--venv-python", default=DEFAULT_VENV_PY)
    ap.add_argument("--out-dir", default=str(ROOT / "runs/infra/b_truncprobe_official"))
    ap.add_argument("--skip-noclip", action="store_true",
                    help="已有同版本基线产物时复用（默认两臂都当场重跑）")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    gate = load_gate()
    gargs = GateArgs(gate)
    # 绝对化：产物路径要写进报告，相对路径会导致 relative_to(ROOT) 抛 ValueError
    # （第一次冒烟就崩在这里，两臂已经跑完却写不出报告）。
    out_dir = Path(a.out_dir)
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    log: list[str] = []

    print("=" * 100)
    print("B② 截断因果探针（A 的官方 LeRobot checkpoint）")
    print("门禁构建：gate_version=%s gate_build=%s spec_sha256=%s"
          % (gate.GATE_VERSION, gate.GATE_BUILD, gate.GATE_SPEC_SHA))
    print("预先登记的判定规则：|Δ受控|>=%d 或 |Δraw|>=%d -> substantive；"
          "1..%d 局 -> formal；0 局 -> no_bite"
          % (BITE_SUBSTANTIVE_CTRL, BITE_SUBSTANTIVE_RAW, BITE_SUBSTANTIVE_CTRL - 1))
    print("  锚定依据：同一臂在门禁阈值 ±0.005 网格上受控成功数已在 0→2 摆动，±2 属已知噪声带")
    print("=" * 100)

    ref = json.loads((ROOT / a.ref_artifact).read_text())
    # replan 口径必须与被比较的参考臂一致，否则护栏 2 的「逐位复现」根本无从谈起。
    replan = a.replan_every if a.replan_every is not None else ref.get("replan_every")
    print("\n参考臂口径：chunk=%s n_action_steps=%s replan_every=%s -> 本次沿用 replan=%s"
          % (ref.get("chunk_size"), ref.get("n_action_steps"), ref.get("replan_every"), replan))
    ck = ref.get("checkpoint") or {}
    ckpt_dir = ck.get("pretrained_model_dir")
    ref_sha = ck.get("model_safetensors_sha256")
    if not ckpt_dir:
        print("[FATAL] 参考产物没有 checkpoint.pretrained_model_dir，无法定位权重")
        return 2
    weights = Path(ckpt_dir) / "model.safetensors"

    # ---- 护栏 1：权重 sha256 必须与参考产物一致 ----
    print("\n[护栏 1] 权重一致性")
    if not weights.exists():
        print("  [FATAL] 权重文件不存在：%s" % weights)
        return 2
    got_sha = sha256_file(weights)
    sha_ok = (ref_sha is None) or (got_sha == ref_sha)
    print("  实测 sha256 = %s" % got_sha)
    print("  参考产物记录 = %s" % ref_sha)
    print("  -> %s" % ("一致，比较有效" if sha_ok else
                      "**不一致：权重已变，本次比较无意义，拒绝启动**"))
    if not sha_ok:
        return 2

    # ---- 护栏 3：评测环境的版本指纹 ----
    # 本仓发生过 requirements pin 从 robosuite==1.5.2 漂到 1.5.1、而自检恒真放行的事故
    # （docs/b_reproducibility_incident_20260928.md）。所以这里真比对，不是打印一下就算。
    print("\n[护栏 3] 评测环境版本指纹")
    fp = env_fingerprint(a.venv_python)
    print("  解释器：%s" % a.venv_python)
    print("  %s" % json.dumps(fp, ensure_ascii=False))
    if "error" in fp:
        print("  [FATAL] 取不到版本指纹，无法确认评测环境 —— 拒绝启动")
        return 2
    pin = pinned_robosuite()
    rs_ok = (pin is None) or (fp.get("robosuite") == pin)
    print("  robosuite 实装=%s  requirements.txt pin=%s -> %s"
          % (fp.get("robosuite"), pin, "一致" if rs_ok else "**不一致**"))
    ref_versions = ref.get("versions") or {}
    ver_match = {k: (fp.get(k) == ref_versions.get(k)) for k in ("torch", "lerobot")
                 if k in ref_versions}
    print("  与参考产物 versions 比对：%s" % json.dumps(ver_match, ensure_ascii=False))
    if not rs_ok or not fp.get("cuda_available") or (ver_match and not all(ver_match.values())):
        print("  [FATAL] 评测环境与 pin / 参考产物不一致，单变量前提不成立 —— 拒绝启动")
        return 2

    # ---- 跑两臂 ----
    p_noclip = out_dir / "official_noclip.json"
    p_clip = out_dir / ("official_clip%g.json" % a.clip)
    print("\n[基线臂] 截断关闭")
    if a.skip_noclip and p_noclip.exists():
        print("  复用已有产物 %s（--skip-noclip）" % p_noclip.name)
        ok_base, dt_base = True, 0.0
    else:
        ok_base, dt_base = run_arm(a.venv_python, ckpt_dir, p_noclip, None,
                                   a.episodes, a.seed0, a.horizon, replan, log)
    print("\n[探针臂] 截断 ±%g" % a.clip)
    ok_clip, dt_clip = run_arm(a.venv_python, ckpt_dir, p_clip, a.clip,
                               a.episodes, a.seed0, a.horizon, replan, log)
    if not (ok_base and ok_clip):
        print("\n[FATAL] 有臂跑失败，无法给出裁定（详见 .log）")
        return 2

    # ---- 护栏 2：基线臂必须复现参考产物（**按 seed 交集**比，不是比总数）----
    # 为什么不能比总数：冒烟时只跑 2 局，参考产物是 20 局，raw 2 vs 11 必然不等，
    # 于是护栏会把一次正常的冒烟判成「基线不可复现」。总数只在局数相同时才有意义；
    # 逐 seed 比对在任何局数下都成立，且能指出**哪一局**开始分叉。
    print("\n[护栏 2] 基线复现性（重跑的 noclip 臂 vs A 的参考产物，按 seed 交集）")
    base = gate.judge_file(p_noclip, gargs)
    clip = gate.judge_file(p_clip, gargs)
    ref_row = gate.judge_file(ROOT / a.ref_artifact, gargs)
    rb, rr = raw_by_seed(p_noclip), raw_by_seed(ROOT / a.ref_artifact)
    vb, vr = per_seed(base), per_seed(ref_row)
    common = sorted(set(rb) & set(rr))
    mism = []
    for s in common:
        if rb[s] != rr[s]:
            mism.append({"seed": s, "field": "success_raw", "rerun": rb[s], "ref": rr[s]})
        if vb.get(s, (None, None))[1] != vr.get(s, (None, None))[1]:
            mism.append({"seed": s, "field": "verdict",
                         "rerun": vb.get(s, (None, None))[1], "ref": vr.get(s, (None, None))[1]})
    repro_ok = bool(common) and not mism
    print("  比对 seed 数：%d（重跑 %d 局 ∩ 参考 %d 局）" % (len(common), len(rb), len(rr)))
    print("  raw       ：重跑=%s 参考=%s" % (base.get("raw_success"), ref_row.get("raw_success")))
    print("  四类计数  ：重跑=%s" % json.dumps(counts(base), ensure_ascii=False))
    print("             参考=%s" % json.dumps(counts(ref_row), ensure_ascii=False))
    if not common:
        print("  -> **seed 交集为空，无可比对象** -> 裁定降为 inconclusive")
    elif mism:
        for m in mism[:10]:
            print("     [MISMATCH] seed=%s %s：重跑=%s 参考=%s" % (m["seed"], m["field"], m["rerun"], m["ref"]))
        print("  -> **%d 处逐局不一致：基线不可复现，差异不能归因给截断** -> inconclusive" % len(mism))
    else:
        print("  -> %d 局逐位复现（raw 与裁定全同），差异可归因给截断这一个变量" % len(common))

    # ---- 比较 ----
    print("\n[比较] 单变量：--clip-norm-input %s" % ("关 vs ±%g" % a.clip))
    hdr = "%-26s %10s %10s %8s" % ("指标", "noclip", "clip%g" % a.clip, "Δ")
    print("  " + hdr)
    bc, cc = counts(base), counts(clip)
    metrics = [("raw_success", base.get("raw_success"), clip.get("raw_success")),
               ("受控成功", bc["controlled_success"], cc["controlled_success"]),
               ("insufficient_lift", bc["insufficient_lift"], cc["insufficient_lift"]),
               ("over_lift", bc["over_lift"], cc["over_lift"]),
               ("flick", bc["flick"], cc["flick"]),
               ("provisional_pass", bc["provisional_pass"], cc["provisional_pass"])]
    for name, v0, v1 in metrics:
        d = (v1 - v0) if isinstance(v0, int) and isinstance(v1, int) else None
        print("  %-26s %10s %10s %8s" % (name, v0, v1, ("+" if (d or 0) > 0 else "") + str(d)))

    ic0 = (base.get("input_contract") or {})
    ic1 = (clip.get("input_contract") or {})
    print("  %-26s %10s %10s" % ("输入契约 status", ic0.get("status"), ic1.get("status")))
    print("  %-26s %10s %10s" % ("mean blown frac", ic0.get("mean_blown_frames_frac"),
                                 ic1.get("mean_blown_frames_frac")))
    print("  %-26s %10s %10s" % ("closed-loop |x|max", ic0.get("closed_loop_norm_absmax"),
                                 ic1.get("closed_loop_norm_absmax")))
    print("  %-26s %10s %10s" % ("composite_policy", base.get("composite_policy"),
                                 clip.get("composite_policy")))
    print("  %-26s %10s %10s" % ("active_constraints", ",".join(base.get("active_constraints") or []),
                                 ",".join(clip.get("active_constraints") or [])))
    # 截断臂还应带 pre-clip 记账，否则「截断后 0% 越界」会把违例藏掉
    pre = [r.get("norm_input_preclip_blown_frames_frac") for r in
           (json.loads(p_clip.read_text()).get("rows") or [])
           if r.get("norm_input_preclip_blown_frames_frac") is not None]
    print("  %-26s %10s %10s" % ("pre-clip 越界帧占比(均)", "-",
                                 (round(sum(pre) / len(pre), 6) if pre else "缺字段")))
    if not pre:
        print("    [warn] 截断臂没有 norm_input_preclip_blown_frames_frac —— "
              "无法知道截断前有多少帧越界，「L1 不咬」与「L1 被截断藏住」不可区分")

    # ---- 裁定 ----
    d_ctrl = (cc["controlled_success"] or 0) - (bc["controlled_success"] or 0)
    d_raw = (clip.get("raw_success") or 0) - (base.get("raw_success") or 0)
    if not repro_ok:
        verdict = "inconclusive_baseline_not_reproduced"
        why = "基线臂未复现参考产物，差异不可归因"
    elif abs(d_ctrl) >= BITE_SUBSTANTIVE_CTRL or abs(d_raw) >= BITE_SUBSTANTIVE_RAW:
        verdict = "L1_bites_substantive"
        why = "|Δ受控|=%d 或 |Δraw|=%d 超过预先登记的实质门槛 -> 重分类是**实质**的" % (abs(d_ctrl), abs(d_raw))
    elif d_ctrl == 0 and d_raw == 0:
        verdict = "L1_no_bite"
        why = "截断开关不改变任何计数 -> 对这个臂，L1 重分类只是**形式**的"
    else:
        verdict = "L1_bites_formal"
        why = "|Δ受控|=%d、|Δraw|=%d 落在已知噪声带内 -> 重分类**形式为主**，但非零" % (abs(d_ctrl), abs(d_raw))

    # ---- 地板/天花板效应自检：Δ受控=0 有两种完全不同的含义 ----
    base_ctrl = bc["controlled_success"] or 0
    denom = base.get("episodes_total") or a.episodes
    room_down, room_up = base_ctrl, denom - base_ctrl
    if base_ctrl == 0:
        floor_note = ("**地板效应**：基线受控成功为 0/%d，「截断后仍是 0」无法区分"
                      "「L1 不咬」与「本来就没有可失去的」。此裁定对受控口径**只是弱证据**，"
                      "需在受控成功非零的臂上重跑才能定性。" % denom)
    elif base_ctrl >= denom:
        floor_note = ("**天花板效应**：基线受控成功 %d/%d 已满，改善无从观测，"
                      "只能观测退化。" % (base_ctrl, denom))
    else:
        floor_note = ("基线受控成功 %d/%d：可退化余量 %d 局、可改善余量 %d 局。%s"
                      % (base_ctrl, denom, room_down, room_up,
                         ("两个方向都有充分空间，Δ受控 可作强证据。"
                          if min(room_down, room_up) >= 3 else
                          "**改善方向余量不足 3 局**，「截断没带来改善」这一半结论偏弱；"
                          "「截断没造成退化」那一半仍成立（退化余量 %d 局）。" % room_down)))
    print("\n[观测空间自检] %s" % floor_note)
    report_floor = {"baseline_controlled": base_ctrl, "denominator": denom,
                    "room_to_degrade": room_down, "room_to_improve": room_up,
                    "effect": ("floor" if base_ctrl == 0 else
                               ("ceiling" if base_ctrl >= denom else "two_sided")),
                    "note": floor_note}

    print("\n" + "=" * 100)
    print("裁定：%s" % verdict)
    print("理由：%s" % why)
    print("=" * 100)

    report = {
        "probe": "truncation_causal_on_official_checkpoint",
        "gate_version": gate.GATE_VERSION, "gate_build": gate.GATE_BUILD,
        "gate_spec_sha256": gate.GATE_SPEC_SHA,
        "ref_artifact": a.ref_artifact,
        "checkpoint": {"pretrained_model_dir": ckpt_dir, "model_safetensors_sha256_recorded": ref_sha,
                       "model_safetensors_sha256_measured": got_sha, "sha_ok": sha_ok},
        "single_variable": {"varied": "clip_norm_input", "off": None, "on": a.clip,
                            "held_fixed": ["checkpoint", "episodes", "seed0", "horizon",
                                           "replan_every", "evaluator_version(同进程同代码)"]},
        "config": {"episodes": a.episodes, "seed0": a.seed0, "horizon": a.horizon,
                   "replan_every": replan, "venv_python": a.venv_python,
                   "ref_cadence": {"chunk_size": ref.get("chunk_size"),
                                   "n_action_steps": ref.get("n_action_steps"),
                                   "replan_every": ref.get("replan_every")}},
        "preregistered_rule": {"substantive_ctrl": BITE_SUBSTANTIVE_CTRL,
                               "substantive_raw": BITE_SUBSTANTIVE_RAW,
                               "anchor": "同一臂在门禁阈值 ±0.005 网格上受控成功数 0→2，±2 属已知噪声带"},
        "guards": {"weights_sha_ok": sha_ok, "baseline_reproduced": repro_ok,
                   "n_seeds_compared": len(common), "baseline_mismatches": mism},
        "env_fingerprint": {"venv_python": a.venv_python, "versions": fp,
                            "robosuite_pin": pin, "robosuite_matches_pin": rs_ok,
                            "matches_ref_artifact_versions": ver_match},
        "arms": {"noclip": {"file": str(p_noclip.relative_to(ROOT)), "summary": base,
                            "elapsed_sec": round(dt_base, 1)},
                 "clip": {"file": str(p_clip.relative_to(ROOT)), "summary": clip,
                          "elapsed_sec": round(dt_clip, 1)}},
        "delta": {"controlled_success": d_ctrl, "raw_success": d_raw,
                  "counts_noclip": bc, "counts_clip": cc},
        "preclip_blown_frames_frac_mean": (round(sum(pre) / len(pre), 6) if pre else None),
        "verdict": verdict, "verdict_reason": why,
        "observation_space": report_floor,
        "commands": log,
    }
    # summary 里 per_episode 太长，只留裁定级字段
    for k in ("noclip", "clip"):
        report["arms"][k]["summary"] = {
            f: report["arms"][k]["summary"].get(f) for f in
            ("file", "gate_version", "gate_build", "gate_spec_sha256", "gate_pass", "gate_reason",
             "measurement_valid", "input_contract", "composite_policy", "active_constraints",
             "constraint_sides", "raw_success", "accounts", "terminal_semantics", "field_class")}
    outp = Path(a.json_out) if a.json_out else out_dir / "probe_report.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print("写出:", outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
