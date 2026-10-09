#!/usr/bin/env python3
"""C 线：把「harness 兜底接管 + 迟到/被撤销的标签」接到**真实 robosuite Lift 帧**上。

## 为什么还要第二个 smoke

`scripts/c_contract_lift_smoke.py` 证明的是「顺利的一局能正确落成账本与四视图」。但 v4 的
硬约束几乎全都长在**不顺利**的路径上，而这些路径此前只在合成时间轴上验过
（`scripts/selfcheck_ledger_views.py`）：

- 附录 02 §6.2：抢占槽自身隔离；边界快照不可确认时连前驱一起隔离；删失比例必须报告。
- 附录 01 §5.1：`proposed_action / a_rl / driver_command / measured_state` 四种动作量分开存，
  **实测位移不得倒填成动作标签**。
- 附录 01 §5.4：纠正帧走 BC 视图，supervision_mask 用真实 valid_indices；影子建议只进候选池。
- 附录 02 §7：`unknown` 不是失败、不是零奖励；`pending` 不发布也不置零。

本脚本用同一局真实帧跑三条通道，把上面这些打在真数据上：

| 通道 | 注入 | 要回答的问题 |
|---|---|---|
| `clean` | 无 | 基线：无接管时删失为 0、TD 正常 |
| `takeover` | 帧 F 处 harness 兜底接管 | 抢占槽/前驱是否隔离、删失是否报告、纠正帧是否**只**进 BC 且监督目标取自 `driver_command` |
| `late_labels` | 两帧 `pending` + 一帧 final 事后撤销 | pending 是否进 pending 桶而非 TD/0 分；撤销是否让整槽退回 unknown |

接管帧的账本编码（详见 `replay_into_contract` 的 docstring）：`source="harness"`、
`lease_generation=1`、`a_rl=None`、命令落 `driver_command`、自带纠正 chunk 的
`chunk_id/chunk_index`（沿用 E 段 `[n,2n)` 布局），且**不发 `request_admitted`** ——
否则 `build_slots` 会把兜底动作当成学习器的决策槽混进普通 TD。

这不是 learned policy 结果，也不是能力主张：teacher 与兜底都还是脚本控制器，
验的是契约层在真实接触数据上的行为。

## 用法

    MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/c_contract_lift_takeover_smoke.py
    ... --seed 5000 --n 4 --takeover-offset 2

产物：`runs/infra/c_lift_takeover_smoke.json` + `runs/infra/c_lift_takeover_smoke/<时间戳>/`
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "robosuite", "gymnasium")

from harness import data_bridge as db  # noqa: E402
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402
from harness.obs_store import ObsStore  # noqa: E402
from scripts.c_contract_lift_smoke import (REPR_VERSION, STATE_DIM,  # noqa: E402
                                           replay_into_contract, teacher_rollout,
                                           unit_convention)

OUT_ROOT = ROOT / "runs" / "infra" / "c_lift_takeover_smoke"
OUT_JSON = ROOT / "runs" / "infra" / "c_lift_takeover_smoke.json"


def build_pass(name: str, work: Path, rollout: dict, *, n: int, gamma: float, episode_id: str,
               takeover_frame: int | None, pending_frames: tuple, revoke_frames: tuple,
               label_version: str = "env-reward-v1") -> dict:
    """写一份独立账本 + 观测快照，派生四视图，返回可断言的摘要。"""
    ledger = FactLedger(work / f"ledger_{name}.db")
    store = ObsStore(work / f"obs_{name}")
    with ledger, store:
        replay = replay_into_contract(rollout, ledger, store, episode_id=episode_id, n=n,
                                      takeover_frame=takeover_frame,
                                      pending_frames=pending_frames,
                                      revoke_frames=revoke_frames)
        bundle = db.build_views(ledger, n=n, gamma=gamma, obs_store=store,
                                max_age_ns=200_000_000, label_version=label_version)
        db.write_manifests(ledger, bundle, run_id=f"c-takeover-{name}", gamma=gamma, n=n,
                           label_version=label_version)
        # 导出四视图分片（learner 进程真正会读的东西），并立刻读回核内容身份。
        export_dir = work / f"views_{name}"
        db.export_views(bundle, export_dir, run_id=f"c-takeover-{name}", n=n, gamma=gamma,
                        label_version=label_version, obs_store=store,
                        unit_convention=unit_convention(gamma, n),
                        notes="真实帧 smoke：scripted teacher 重放 + 注入")
        loaded, export_manifest = db.load_views(export_dir)      # verify=True：sha 对不上会抛
        frames = ledger.frames(episode_id=episode_id)
        admitted = ledger.events(episode_id=episode_id, kinds=["request_admitted"])
        takeovers = ledger.events(episode_id=episode_id, kinds=["takeover"])

        def sample(rid: str, view: str = "td"):
            pool = {"td": bundle.td, "isolated": bundle.isolated, "pending": bundle.pending}[view]
            return next((s for s in pool if s.request_id == rid), None)

        bc_rows = []
        for s in bundle.bc:
            row = next((fr for fr in frames if int(fr["abs_frame"]) == s.start_frame), None)
            bc_rows.append({
                "start_frame": s.start_frame, "u": s.u, "bc_action_field": s.bc_action_field,
                "supervision_sum": sum(s.supervision_mask), "weight": s.supervision_weight,
                "ledger_a_rl": (row["a_rl"] if row else "no-frame"),
                "ledger_driver_command": (row["driver_command"] if row else None),
                "ledger_measured_state": (row["measured_state"] if row else None),
                "ledger_source": (row["source"] if row else None),
                "lease_generation": (int(row["lease_generation"]) if row else None),
            })
        return {"replay": replay, "stats": bundle.stats, "n_td": len(bundle.td),
                "n_bc": len(bundle.bc), "n_isolated": len(bundle.isolated),
                "n_pending": len(bundle.pending),
                "td_start_frames": sorted(s.start_frame for s in bundle.td),
                "td_request_ids": sorted(s.request_id for s in bundle.td),
                "isolated": {s.request_id: list(s.isolation_reasons) for s in bundle.isolated},
                "pending_ids": sorted(s.request_id for s in bundle.pending),
                "pending_r_slot": {s.request_id: s.r_slot for s in bundle.pending},
                "samples": {rid: {view: (sample(rid, view) is not None)
                                  for view in ("td", "isolated", "pending")}
                            for rid in sorted({s.request_id for s in bundle.td}
                                              | {s.request_id for s in bundle.isolated}
                                              | {s.request_id for s in bundle.pending})},
                "sample_detail": {rid: {"r_slot": (sample(rid) or sample(rid, "isolated")
                                                   or sample(rid, "pending")).r_slot,
                                        "bootstrap_valid": (sample(rid) or sample(rid, "isolated")
                                                            or sample(rid, "pending")).bootstrap_valid}
                                  for rid in sorted({s.request_id for s in bundle.td}
                                                    | {s.request_id for s in bundle.isolated}
                                                    | {s.request_id for s in bundle.pending})},
                "bc_rows": bc_rows,
                "admitted_starts": sorted(int(e["abs_frame"]) for e in admitted),
                "takeover_events": [{"request_id": e["request_id"], "abs_frame": e["abs_frame"],
                                     "lease_generation": e["lease_generation"],
                                     "payload": e["payload"]} for e in takeovers],
                "ledger_stats": ledger.stats(),
                "export": {"dir": str(export_dir),
                           "rows": {view: len(loaded[view]) for view in loaded},
                           "bc_action_fields": sorted({str(r["bc_action_field"])
                                                       for r in loaded["bc"]}),
                           "td_start_frames": sorted(int(r["start_frame"]) for r in loaded["td"]),
                           "representation_versions": export_manifest["representation_versions"],
                           "unit_convention": export_manifest.get("unit_convention"),
                           "sha_verified_on_load": True}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=5000)
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--horizon", type=int, default=300)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--takeover-slot", type=int, default=4, help="在第几个槽内接管")
    parser.add_argument("--takeover-offset", type=int, default=2, help="槽内第几帧接管（须 < n）")
    parser.add_argument("--out", default=str(OUT_JSON))
    args = parser.parse_args()
    if args.takeover_offset >= args.n:
        raise SystemExit(f"--takeover-offset 必须 < n（当前 {args.takeover_offset} >= {args.n}）")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    work = OUT_ROOT / stamp
    work.mkdir(parents=True, exist_ok=True)
    n, gamma = args.n, args.gamma

    env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    try:
        rollout = teacher_rollout(env, args.seed, args.horizon)
    finally:
        env.close()
    total = len(rollout["frames"])
    episode_id = f"lift_{args.seed}"
    takeover_frame = args.takeover_slot * n + args.takeover_offset
    if takeover_frame >= total - n:
        raise SystemExit(f"接管帧 {takeover_frame} 太靠后（本局 {total} 帧），换一个 --takeover-slot")
    rid_at_takeover = f"R{args.takeover_slot:03d}"
    rid_prev = f"R{args.takeover_slot - 1:03d}"
    # 迟到/撤销通道：pending 放在第 2 槽，撤销放在第 5 槽（都远离接管，便于归因）
    pending_frames = tuple(range(2 * n, 2 * n + 2))
    revoke_frames = (5 * n + 1,)

    passes = {
        "clean": build_pass("clean", work, rollout, n=n, gamma=gamma, episode_id=episode_id,
                            takeover_frame=None, pending_frames=(), revoke_frames=()),
        "takeover": build_pass("takeover", work, rollout, n=n, gamma=gamma, episode_id=episode_id,
                               takeover_frame=takeover_frame, pending_frames=(),
                               revoke_frames=()),
        "late_labels": build_pass("late_labels", work, rollout, n=n, gamma=gamma,
                                  episode_id=episode_id, takeover_frame=None,
                                  pending_frames=pending_frames, revoke_frames=revoke_frames),
    }
    clean, take, late = passes["clean"], passes["takeover"], passes["late_labels"]
    rid_pending = f"R{pending_frames[0] // n:03d}"
    rid_revoked = f"R{revoke_frames[0] // n:03d}"

    bc = take["bc_rows"]
    bc_field_ok = all(r["bc_action_field"] == "driver_command" for r in bc)
    bc_mask_ok = all(r["supervision_sum"] == 1 for r in bc)
    bc_value_ok = all(r["u"] is not None and r["ledger_driver_command"] is not None
                      and np.allclose(np.asarray(r["u"], dtype=float),
                                      np.asarray(r["ledger_driver_command"], dtype=float),
                                      atol=0.0, rtol=0.0) for r in bc)
    def _not_measured(row: dict) -> bool:
        """禁止把实测位移倒填成动作标签：BC 目标不得等于同长度的 measured_state 切片。"""
        if row["ledger_measured_state"] is None:
            return True
        u = np.asarray(row["u"], dtype=float).reshape(-1)
        ms = np.asarray(row["ledger_measured_state"], dtype=float).reshape(-1)
        if ms.shape[0] < u.shape[0]:
            return True                      # 维度都装不下，天然不可能相等
        return not np.array_equal(u, ms[:u.shape[0]])

    bc_not_measured = all(_not_measured(r) for r in bc)
    bc_a_rl_none = all(r["ledger_a_rl"] in (None, "None") for r in bc)
    harness_lease_ok = all(r["lease_generation"] == 1 for r in bc)

    # P0-2：这一份产物用的是哪一套 γ/n 约定、有没有定标（docs/c_golden_conformance_20260928.md §8）。
    # 真机路径的 γ=0.99 / n=4 至今是假设值，模板 timing 组仍是 null。
    report_uc = unit_convention(gamma, n)

    checks = {
        # --- 基线 ---
        "clean 通道无接管时删失为 0": clean["stats"]["censoring_ratio"] == 0.0,
        # clean 通道允许的唯一隔离来源是**重放尾槽 U 不完整**：本重放的 U 由 teacher 逐帧动作
        # 拼出，尾槽的 [t_k+n, t_k+2n) 超出录制范围。附录 02 §3.3 条件2 要求 U「完整入队」，
        # §4.3／§5.1 禁止把短缺的行重复或补零填成 n 行（那是伪造动作），所以只能隔离。
        # 真机上 U 是 t_k 一次前向的产物，不会短缺 —— 这暴露的是重放的采集缺口，不是策略缺陷。
        # 接管／租约／边界类隔离必须为 0，否则这条通道就不叫 clean。
        "clean 通道 TD 非空，且隔离只来自尾槽 U 不完整（无接管类隔离）": (
            clean["n_td"] > 0
            and set(clean["stats"]["isolation_reasons"]) <= {"u_incomplete", "terminal_u_incomplete"}
            and clean["stats"]["isolation_reasons"].get("terminal_u_incomplete", 0) == 1
            and clean["stats"]["isolation_reasons"].get("u_incomplete", 0) >= 1),
        "clean 通道脚本帧不进 BC（source 不在 bc_sources）": clean["n_bc"] == 0,
        # --- 接管 ---
        "接管事件挂在被抢占的 request 上并换代次": (
            len(take["takeover_events"]) == 1
            and take["takeover_events"][0]["request_id"] == rid_at_takeover
            and int(take["takeover_events"][0]["abs_frame"]) == takeover_frame
            and int(take["takeover_events"][0]["lease_generation"]) == 1),
        "被抢占槽退出普通 TD 且原因记 takeover_in_slot": (
            take["samples"].get(rid_at_takeover, {}).get("td") is not True
            and "takeover_in_slot" in take["isolated"].get(rid_at_takeover, [])),
        "被抢占槽同时暴露租约代次变化": (
            "lease_generation_changed" in take["isolated"].get(rid_at_takeover, [])),
        # 边界语义（附录 §6.2 / B 黄金值 E5-V1、E5-V2）：前驱要不要一起隔离，取决于**边界帧**
        # 上的快照能不能确认，而不是「下一窗口里有没有出现过别的命令」。
        #   --takeover-offset > 0：接管发生在下一槽内部，边界帧仍归属前驱的 U ⇒ 前驱这一步转移
        #     已经合法成立，必须**保留**。旧写法在这里断言前驱被 `c_next_not_equal_u` 隔离，
        #     那正是 E5-V1 点名的过度删失（白扔合法数据）；2026-09-28 按黄金值裁定改掉，
        #     推导见 docs/c_golden_conformance_20260928.md §2。
        #   --takeover-offset == 0：接管正好压在槽边界上、先后无法判断 ⇒ 前驱一并隔离（E5-V2）。
        "前驱槽按边界快照裁定（offset>0 保留 / offset==0 一并隔离）": (
            (take["samples"].get(rid_prev, {}).get("td") is True
             and rid_prev not in take["isolated"])
            if args.takeover_offset > 0 else
            ({"c_next_not_equal_u", "boundary_unverifiable_before_takeover"}
             & set(take["isolated"].get(rid_prev, []))) != set()),
        "被抢占槽同时暴露 §3.3-1（C 未全槽按学习动作边界执行）": (
            "c_not_executed" in take["isolated"].get(rid_at_takeover, [])),
        "删失比例被报告且 > 0": take["stats"]["censoring_ratio"] > 0.0,
        "接管后不再接纳新的策略请求": (
            max(take["admitted_starts"]) == args.takeover_slot * n),
        "接管帧数与账本一致": take["replay"]["n_harness_frames"] == total - takeover_frame,
        # --- 纠正帧 → BC ---
        "纠正帧全部进 BC 视图": take["n_bc"] == total - takeover_frame,
        "BC 监督目标取自 driver_command（不是 a_rl）": bool(bc) and bc_field_ok and bc_a_rl_none,
        "BC 的 u 与账本 driver_command 逐值相同": bc_value_ok,
        "BC 的 u 不是 measured_state（禁止实测位移倒填）": bc_not_measured,
        "BC supervision_mask 每帧恰好一位（落在 E 段）": bc_mask_ok,
        "纠正帧的租约代次记为 1": harness_lease_ok,
        "纠正帧一条都没混进普通 TD": all(f < takeover_frame for f in take["td_start_frames"]),
        # --- 迟到 / 撤销 ---
        "pending 槽进 pending 桶而不是 TD": (
            late["samples"].get(rid_pending, {}).get("pending") is True
            and late["samples"].get(rid_pending, {}).get("td") is not True),
        "pending 槽 r_slot 为 None（不置零、不发布）": (
            late["pending_r_slot"].get(rid_pending, "missing") is None),
        "撤销一帧 final 标签 -> 整槽退回 unknown 并退出 TD": (
            late["samples"].get(rid_revoked, {}).get("td") is not True
            and "reward_unknown" in late["isolated"].get(rid_revoked, [])
            and late["sample_detail"].get(rid_revoked, {}).get("r_slot") is None),
        "撤销条数进 stats": late["stats"].get("revoked_labels") == 1,
        "撤销/pending 不牵连同局其它槽": late["n_td"] > 0,
        "账本 append-only：撤销后原标签行仍在": (
            late["ledger_stats"]["revoked_labels"] == 1
            and late["ledger_stats"]["label_record"] >= total + 1),
        # --- 导出给 learner 的分片 ---
        "五视图分片可导出并按内容身份读回（行数与内存一致）": (
            take["export"]["sha_verified_on_load"]
            and take["export"]["rows"]["td"] == take["n_td"]
            and take["export"]["rows"]["bc"] == take["n_bc"]
            and take["export"]["rows"]["isolated"] == take["n_isolated"]
            and take["export"]["rows"]["pending"] == take["n_pending"]),
        "导出的 BC 分片标明监督目标来自 driver_command": (
            take["export"]["bc_action_fields"] == ["driver_command"]),
        "导出的 td 分片里没有接管之后的帧": (
            all(f < takeover_frame for f in take["export"]["td_start_frames"])),
        "导出的分片带表征版本，learner 可拒绝混版本批次": (
            take["export"]["representation_versions"] == [REPR_VERSION]),
        # --- P0-2：γ/n 的定标状态必须跟着分片走，且与模板 timing 一致 ---
        "产物把 γ/n 显式标为假设值，且定标状态与模板 timing 一致": (
            report_uc["status"] == "assumed"
            and report_uc["gamma_is_assumed"] and report_uc["n_is_assumed"]
            and not report_uc["template_timing"].get("all_filled")
            and abs(report_uc["gamma_slot"] - gamma ** n) < 1e-15),
        "三个通道的导出 manifest 都带同一套约定（learner 换进程也读得到 assumed）": (
            all(p["export"]["unit_convention"] is not None
                and p["export"]["unit_convention"]["status"] == "assumed"
                and int(p["export"]["unit_convention"]["n"]) == n
                and abs(float(p["export"]["unit_convention"]["gamma"]) - gamma) < 1e-15
                for p in passes.values())),
        # --- 前提 ---
        "teacher 本局真实抓取成功（否则只是协议 smoke）": bool(rollout["success"] and rollout["held"]),
    }
    report = {
        "task": "robosuite Lift", "controller": rollout["controller"], "seed": args.seed,
        "horizon": args.horizon, "steps": total, "n_assumed": n, "gamma": gamma,
        "gamma_assumed": gamma, "unit_convention": report_uc,
        "pinned_object_seed": PINNED_OBJECT_SEED, "representation_version": REPR_VERSION,
        "artifact_dir": str(work), "takeover_frame": takeover_frame,
        "takeover_slot_request": rid_at_takeover, "pending_frames": list(pending_frames),
        "revoke_frames": list(revoke_frames), "phases": rollout["phases"],
        "success": rollout["success"], "held": rollout["held"],
        "note": "scripted teacher + 脚本兜底的重放注入，验契约层行为；不是 learned policy 结果",
        "passes": passes,
        "checks": [{"name": k, "ok": bool(v)} for k, v in checks.items()],
    }
    report["pass"] = all(checks.values())
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    for name in ("clean", "takeover", "late_labels"):
        p = passes[name]
        print(f"{name}: td={p['n_td']} bc={p['n_bc']} isolated={p['n_isolated']} "
              f"pending={p['n_pending']} censoring={p['stats']['censoring_ratio']} "
              f"reasons={p['stats']['isolation_reasons']}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"结果: {'PASS' if report['pass'] else 'FAIL'} -> {out}")
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
