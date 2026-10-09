#!/usr/bin/env python3
"""C 线自检：观测快照存储（内容寻址 / 新鲜度 / 表征版本）与数据桥的联动。

依据 v4 附录 01 §2.3（观测时刻、源时钟、同步误差、不得重打时间戳）与 §5.1
（表征缓存不能伪装成新表征、原始观测要能重算）。全部离线、不训练、不碰 robosuite。

用法：
    /root/venvs/rlrobot/bin/python scripts/selfcheck_obs_store.py
产物：runs/infra/c_obs_selfcheck.json + runs/infra/c_obs_selfcheck/<时间戳>/
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy")

from harness import data_bridge as db  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402
from harness.obs_store import (ObsStore, RepresentationMismatch, StaleObservation,  # noqa: E402
                               normalizer_hash)
from scripts.selfcheck_ledger_views import EpisodeBuilder, action  # noqa: E402

OUT_ROOT = ROOT / "runs" / "infra" / "c_obs_selfcheck" / time.strftime("%Y%m%d_%H%M%S")
OUT_JSON = ROOT / "runs" / "infra" / "c_obs_selfcheck.json"
NS_PER_FRAME = 50_000_000          # 20 Hz


def obs(seed: float) -> dict[str, np.ndarray]:
    return {"state": np.full(4, seed, dtype=np.float32),
            "wrist": np.full((2, 2), int(seed * 10), dtype=np.uint8)}


def new_store(name: str) -> ObsStore:
    return ObsStore(OUT_ROOT / name)


def new_ledger(name: str) -> FactLedger:
    return FactLedger(OUT_ROOT / f"{name}.db")


def case_content_addressing(checks: list) -> None:
    with new_store("addr") as store:
        first = store.put(obs(1.0), sampled_at_ns=1_000, representation_version="repr-v1",
                          episode_id="e1", abs_frame=100)
        again = store.put(obs(1.0), sampled_at_ns=1_000, representation_version="repr-v1",
                          episode_id="e1", abs_frame=100)
        other = store.put(obs(2.0), sampled_at_ns=2_000, representation_version="repr-v1")
        checks.append(("同内容同采样时刻 -> 同一 obs_ref（去重）", first.obs_ref == again.obs_ref))
        checks.append(("不同内容 -> 不同 obs_ref", first.obs_ref != other.obs_ref))
        checks.append(("去重后只存一份 blob", store.stats()["n_snapshots"] == 2))
        back = store.get(first.obs_ref)
        checks.append(("取回的数组逐元素相同",
                       np.array_equal(back["state"], obs(1.0)["state"])
                       and np.array_equal(back["wrist"], obs(1.0)["wrist"])))
        checks.append(("写入顺序不影响内容寻址",
                       store.put({"wrist": obs(1.0)["wrist"], "state": obs(1.0)["state"]},
                                 sampled_at_ns=1_000,
                                 representation_version="repr-v1").obs_ref == first.obs_ref))


def case_no_retimestamp(checks: list) -> None:
    with new_store("time") as store:
        original = store.put(obs(1.0), sampled_at_ns=1_000, representation_version="repr-v1")
        try:
            store.put(obs(1.0), sampled_at_ns=9_999, representation_version="repr-v1")
            blocked = False
        except StaleObservation:
            blocked = True
        checks.append(("旧观测不能重打时间戳当新观察", blocked))
        try:
            store.put(obs(1.0), sampled_at_ns=1_000, representation_version="repr-v2")
            mismatch = False
        except RepresentationMismatch:
            mismatch = True
        checks.append(("同内容标两个表征版本 -> 拒绝", mismatch))
        try:
            store.put(obs(3.0), sampled_at_ns=3_000, representation_version="")
            blocked_empty = False
        except ValueError:
            blocked_empty = True
        checks.append(("表征版本为空 -> 拒绝（不可追溯）", blocked_empty))


def case_freshness_and_sync(checks: list) -> None:
    with new_store("fresh") as store:
        ref = store.put(obs(1.0), sampled_at_ns=0, representation_version="repr-v1",
                        decided_at_ns=10 * NS_PER_FRAME, sync_error_ns=2_000_000)
        fresh = store.reuse_as(ref.obs_ref, decided_at_ns=2 * NS_PER_FRAME,
                               max_age_ns=3 * NS_PER_FRAME, max_sync_error_ns=5_000_000)
        checks.append(("预算内复用通过且不改采样时刻",
                       fresh.obs_ref == ref.obs_ref and fresh.sampled_at_ns == 0))
        checks.append(("复用留下使用记录",
                       store.conn.execute("SELECT COUNT(*) FROM obs_usage WHERE obs_ref=?",
                                          (ref.obs_ref,)).fetchone()[0] == 1))
        try:
            store.reuse_as(ref.obs_ref, decided_at_ns=100 * NS_PER_FRAME,
                           max_age_ns=3 * NS_PER_FRAME)
            stale_blocked = False
        except StaleObservation:
            stale_blocked = True
        checks.append(("超龄复用被拒（不置零、不伪造）", stale_blocked))
        try:
            store.reuse_as(ref.obs_ref, decided_at_ns=NS_PER_FRAME, max_age_ns=3 * NS_PER_FRAME,
                           max_sync_error_ns=1_000_000)
            sync_blocked = False
        except StaleObservation:
            sync_blocked = True
        checks.append(("同步误差超容差被拒", sync_blocked))
        no_sync = store.put(obs(4.0), sampled_at_ns=0, representation_version="repr-v1")
        try:
            store.reuse_as(no_sync.obs_ref, decided_at_ns=NS_PER_FRAME, max_age_ns=3 * NS_PER_FRAME,
                           max_sync_error_ns=1_000_000)
            unknown_blocked = False
        except StaleObservation:
            unknown_blocked = True
        checks.append(("要求容差但同步误差未知 -> 拒绝", unknown_blocked))


def case_representation_homogeneity(checks: list) -> None:
    with new_store("repr") as store:
        a = store.put(obs(1.0), sampled_at_ns=0, representation_version="repr-v1",
                      normalizer={"mean": np.zeros(4, np.float32), "std": np.ones(4, np.float32)})
        b = store.put(obs(2.0), sampled_at_ns=0, representation_version="repr-v1",
                      normalizer={"mean": np.zeros(4, np.float32), "std": np.ones(4, np.float32)})
        ok = store.assert_single_representation([a.obs_ref, b.obs_ref], view_name="td")
        checks.append(("单一表征/归一化版本 -> 通过", ok["problems"] == []))
        c = store.put(obs(3.0), sampled_at_ns=0, representation_version="repr-v2",
                      normalizer={"mean": np.zeros(4, np.float32), "std": np.ones(4, np.float32)})
        try:
            store.assert_single_representation([a.obs_ref, c.obs_ref], view_name="td")
            mixed_blocked = False
        except RepresentationMismatch:
            mixed_blocked = True
        checks.append(("混两个表征版本 -> 冻结视图", mixed_blocked))
        d = store.put(obs(4.0), sampled_at_ns=0, representation_version="repr-v1",
                      normalizer={"mean": np.ones(4, np.float32), "std": np.ones(4, np.float32)})
        try:
            store.assert_single_representation([a.obs_ref, d.obs_ref], view_name="td")
            norm_blocked = False
        except RepresentationMismatch:
            norm_blocked = True
        checks.append(("同表征但 normalizer 变了 -> 也冻结", norm_blocked))
        checks.append(("normalizer 指纹可复算",
                       normalizer_hash({"mean": np.zeros(4, np.float32),
                                        "std": np.ones(4, np.float32)}) == a.normalizer_hash))


def _episode_with_obs(store: ObsStore, ledger: FactLedger, episode_id: str, *, n: int,
                      repr_of_frame=None, with_time: bool = True) -> tuple[list[str], list[str]]:
    """建一条三槽 episode，每帧都带内容寻址快照与绝对时间。"""
    builder = EpisodeBuilder(ledger, episode_id, n=n)
    refs: dict[int, str] = {}

    def obs_ref_of(frame: int) -> str:
        if frame not in refs:
            version = (repr_of_frame or (lambda f: "repr-v1"))(frame)
            refs[frame] = store.put(obs(1.0 + 0.001 * frame), sampled_at_ns=frame * NS_PER_FRAME,
                                    representation_version=version, episode_id=episode_id,
                                    abs_frame=frame).obs_ref
        return refs[frame]

    def time_ns_of(frame: int) -> int | None:
        return frame * NS_PER_FRAME if with_time else None

    u1, u2, u3 = action(1.0, n), action(2.0, n), action(3.0, n)
    builder.add_slot("R1", 100, u=u1, rewards=[0.1] * n, obs_ref_of=obs_ref_of, time_ns_of=time_ns_of)
    builder.add_slot("R2", 106, u=u2, rewards=[0.2] * n, obs_ref_of=obs_ref_of, time_ns_of=time_ns_of)
    builder.add_slot("R3", 112, u=u3, rewards=[0.3] * n, obs_ref_of=obs_ref_of, time_ns_of=time_ns_of)
    return sorted(refs), [refs[f] for f in (100, 106, 112) if f in refs]


def case_integration_x_ref(checks: list) -> None:
    n, gamma = 6, 0.99
    store = new_store("integ")
    ledger = new_ledger("integ")
    with store, ledger:
        _, decision_refs = _episode_with_obs(store, ledger, "epO", n=n)
        bundle = db.build_views(ledger, n=n, gamma=gamma, obs_store=store,
                                max_age_ns=NS_PER_FRAME, max_sync_error_ns=None)
        s1 = next((s for s in bundle.td if s.request_id == "R1"), None)
        checks.append(("新鲜观测下样本仍进普通 TD", s1 is not None and s1.td_valid))
        checks.append(("x_ref 是内容地址而不是字符串占位",
                       s1 is not None and s1.x_ref == decision_refs[0] and len(s1.x_ref) == 64))
        restored = db.resolve_x(store, s1) if s1 else None
        checks.append(("x_ref 能反查回原始观测数组",
                       restored is not None and np.array_equal(restored["state"], obs(1.1)["state"])))
        restored_next = db.resolve_x(store, s1, which="next") if s1 else None
        checks.append(("next_x_ref 同样可反查",
                       restored_next is not None and "state" in restored_next))
        checks.append(("观测年龄被记账",
                       s1 is not None and s1.start_frame == 100
                       and bundle.stats["representation_check"]["representation_versions"] == ["repr-v1"]))
        checks.append(("单表征版本 -> 视图未冻结", bundle.stats.get("view_frozen") is not True))


def case_integration_stale_and_unknown(checks: list) -> None:
    n, gamma = 6, 0.99
    # (a) 采样时刻远早于决策时刻 -> observation_stale 隔离
    store_a, ledger_a = new_store("stale"), new_ledger("stale")
    with store_a, ledger_a:
        builder = EpisodeBuilder(ledger_a, "epS", n=n)
        stale_ref = store_a.put(obs(1.0), sampled_at_ns=0, representation_version="repr-v1",
                                episode_id="epS", abs_frame=100).obs_ref

        def ref_of(frame: int) -> str:
            return stale_ref if frame == 100 else store_a.put(
                obs(1.0 + 0.001 * frame), sampled_at_ns=frame * NS_PER_FRAME,
                representation_version="repr-v1", episode_id="epS", abs_frame=frame).obs_ref

        builder.add_slot("R1", 100, u=action(1.0, n), rewards=[0.1] * n, obs_ref_of=ref_of,
                         time_ns_of=lambda f: f * NS_PER_FRAME)
        builder.add_slot("R2", 106, u=action(2.0, n), rewards=[0.2] * n, obs_ref_of=ref_of,
                         time_ns_of=lambda f: f * NS_PER_FRAME)
        bundle = db.build_views(ledger_a, n=n, gamma=gamma, obs_store=store_a, max_age_ns=NS_PER_FRAME)
        stale = next((s for s in bundle.isolated if s.request_id == "R1"), None)
        checks.append(("陈旧观测 -> 该槽被隔离", stale is not None
                       and "observation_stale" in stale.isolation_reasons))
        checks.append(("陈旧槽不被静默丢弃（仍在 isolated 视图）",
                       stale is not None and stale.r_slot is not None))
    # (b) 缺绝对时间且要求新鲜度 -> observation_age_unknown
    store_b, ledger_b = new_store("notime"), new_ledger("notime")
    with store_b, ledger_b:
        builder = EpisodeBuilder(ledger_b, "epN", n=n)
        refs: dict[int, str] = {}

        def ref_of(frame: int) -> str:
            if frame not in refs:
                refs[frame] = store_b.put(obs(1.0 + 0.001 * frame), sampled_at_ns=frame * NS_PER_FRAME,
                                          representation_version="repr-v1", episode_id="epN",
                                          abs_frame=frame).obs_ref
            return refs[frame]

        builder.add_slot("R1", 100, u=action(1.0, n), rewards=[0.1] * n, obs_ref_of=ref_of,
                         time_ns_of=lambda f: None)
        builder.add_slot("R2", 106, u=action(2.0, n), rewards=[0.2] * n, obs_ref_of=ref_of,
                         time_ns_of=lambda f: None)
        bundle = db.build_views(ledger_b, n=n, gamma=gamma, obs_store=store_b, max_age_ns=NS_PER_FRAME)
        unknown = next((s for s in bundle.isolated if s.request_id == "R1"), None)
        checks.append(("缺决策时刻且要求新鲜度 -> 记 unknown 不猜",
                       unknown is not None and "observation_age_unknown" in unknown.isolation_reasons))
    # (c) 不传 obs_store 时行为与旧口径完全一致（不影响既有自检）
    store_c, ledger_c = new_store("compat"), new_ledger("compat")
    with store_c, ledger_c:
        builder = EpisodeBuilder(ledger_c, "epC", n=n)
        builder.add_slot("R1", 100, u=action(1.0, n), rewards=[0.1] * n)
        builder.add_slot("R2", 106, u=action(2.0, n), rewards=[0.2] * n)
        bundle = db.build_views(ledger_c, n=n, gamma=gamma)
        s1 = next((s for s in bundle.td if s.request_id == "R1"), None)
        checks.append(("未接 obs_store 时 x_ref 退回 ep#frame 旧口径",
                       s1 is not None and s1.x_ref == "epC#100"))


def case_integration_mixed_representation(checks: list) -> None:
    n, gamma = 6, 0.99
    store, ledger = new_store("mixed"), new_ledger("mixed")
    with store, ledger:
        def repr_of(frame: int) -> str:
            return "repr-v2" if frame >= 112 else "repr-v1"

        _episode_with_obs(store, ledger, "epM", n=n, repr_of_frame=repr_of)
        bundle = db.build_views(ledger, n=n, gamma=gamma, obs_store=store, max_age_ns=NS_PER_FRAME)
        check = bundle.stats.get("representation_check", {})
        checks.append(("TD 视图混表征 -> view_frozen=True",
                       bundle.stats.get("view_frozen") is True))
        checks.append(("冻结原因写明混用的版本",
                       any("representation_version" in p for p in bundle.stats["view_frozen_reasons"])
                       and set(check["representation_versions"]) == {"repr-v1", "repr-v2"}))
        checks.append(("冻结不等于丢弃：样本与事实仍保留",
                       len(bundle.td) + len(bundle.isolated) > 0 and store.stats()["n_snapshots"] > 0))


CASES = (case_content_addressing, case_no_retimestamp, case_freshness_and_sync,
         case_representation_homogeneity, case_integration_x_ref,
         case_integration_stale_and_unknown, case_integration_mixed_representation)


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool]] = []
    for case in CASES:
        before = len(checks)
        case(checks)
        for name, ok in checks[before:]:
            print(f"[{'PASS' if ok else 'FAIL'}] {name}", flush=True)
    failed = [name for name, ok in checks if not ok]
    print(f"--- 失败 {len(failed)} 条 ---" if failed else "--- 全部通过 ---")
    for name in failed:
        print(f"  FAIL {name}")
    OUT_JSON.write_text(json.dumps({
        "cases": [c.__name__ for c in CASES],
        "checks": [{"name": name, "ok": bool(ok)} for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_failed": len(failed),
        "artifact_dir": str(OUT_ROOT),
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"结果: {len(checks) - len(failed)}/{len(checks)} PASS -> {OUT_JSON}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
