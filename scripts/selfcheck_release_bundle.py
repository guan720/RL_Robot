#!/usr/bin/env python3
"""C 线自检：ReleaseBundle / DeploymentManifest 的发布契约。

对应 v4 附录 01 §6（B5）与主方案的发布红线：内容身份而非路径身份、必须绑定全部组件、
同一 checkpoint 双向通过后整体边界替换、禁止分方向各挑最优、禁止 chunk 中途热换权重、
回滚要有身份、污染可暂停晋级。

全部写入临时 registry_root（`runs/infra/c_release_selfcheck/<时间戳>/registry`），
**不碰** `registry/` 里已发布的技能，也不调用 `registry/publish.py` 的写路径。

用法：/root/venvs/rlrobot/bin/python scripts/selfcheck_release_bundle.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from registry import release_bundle as rb  # noqa: E402

OUT_ROOT = ROOT / "runs" / "infra" / "c_release_selfcheck" / time.strftime("%Y%m%d_%H%M%S")
OUT_JSON = ROOT / "runs" / "infra" / "c_release_selfcheck.json"
SKILL = "c_selfcheck_skill"
# P1-5 的 fixture 身份：合成值、**无物理意义**（ADR-C-007）。本自检不把它与上游真门禁对表。
FIXTURE_IDENTITY = {"gate_version": "vFIX", "gate_build": "fixture00000",
                    "gate_spec_sha256": "fixture-spec-sha", "verdict_sha256": "fixture-verdict-sha",
                    "measurement_valid": True, "usable_for": "physical_fact",
                    "provenance_kind": None, "is_current_build": True,
                    "superseded_by": None, "regraded_from": None}


class Fixture:
    """一组可控内容的组件文件 + 临时 registry。"""

    def __init__(self, name: str):
        self.root = OUT_ROOT / name
        self.assets = self.root / "assets"
        self.registry = self.root / "registry"
        self.assets.mkdir(parents=True, exist_ok=True)
        self.registry.mkdir(parents=True, exist_ok=True)

    def write(self, role: str, text: str) -> Path:
        path = self.assets / f"{role}.bin"
        path.write_text(text, encoding="utf-8")
        return path

    def components(self, *, policy_text: str = "policy-bytes", omit: tuple[str, ...] = (),
                   protocol_text: str = "protocol-bytes") -> list[rb.ComponentRef]:
        out = []
        for role in rb.REQUIRED_ROLES:
            if role in omit:
                continue
            text = policy_text if role == "policy" else (
                protocol_text if role == "eval_protocol" else f"{role}-bytes")
            if role in ("schedule_config", "task_contract"):
                out.append(rb.inline_component(role, {"n": 6, "role": role}, version="v1"))
            else:
                out.append(rb.file_component(role, self.write(role, text), version="v1"))
        return out

    def directions(self, *, checkpoint_sha: str, protocol_sha: str, both: bool = True,
                   passed: bool = True, goals: tuple[str, ...] = rb.DEFAULT_DIRECTIONS,
                   flick: float | None = 0.0,
                   identity: dict | None = None) -> list[rb.DirectionScore]:
        # P1-5：`build_bundle` 现在默认要求裁定身份（`require_verdict_identity=True`）。
        # fixture 给一份**合法**身份（physical_fact + 现构建），让既有各 case 继续测它们本来
        # 要测的东西（内容身份 / 双向红线 / 组件绑定），而不是全体撞在新红线上。
        # `identity=None` ⇒ 用这份合法默认；传 dict ⇒ 整体替换，用来造「缺身份 / 档位不对 /
        # 构建不符」的反例。构建号是**合成值、无物理意义**（ADR-C-007），且本自检不把它与
        # 上游真门禁对表（保持 hermetic：不依赖 B 的判据模块）。
        ident = dict(FIXTURE_IDENTITY)
        if identity is not None:
            ident = dict(identity)
        rows = []
        for goal in (goals if both else goals[:1]):
            rows.append(rb.DirectionScore(goal_id=goal, passed=passed,
                                          checkpoint_sha256=checkpoint_sha,
                                          eval_protocol_sha256=protocol_sha,
                                          success_rate=0.8, n_episodes=20,
                                          success_rate_grasp_verified=0.75, flick_frac=flick,
                                          controlled_success_rate=0.75,
                                          source=f"runs/infra/{goal}/audit_truth20.json",
                                          **ident))
        return rows


def build_ok(fixture: Fixture, **kwargs) -> rb.ReleaseBundle:
    components = fixture.components(**{k: v for k, v in kwargs.items()
                                       if k in ("policy_text", "omit", "protocol_text")})
    policy = next(c for c in components if c.role == "policy")
    protocol = next(c for c in components if c.role == "eval_protocol")
    directions = fixture.directions(checkpoint_sha=policy.sha256, protocol_sha=protocol.sha256,
                                    **{k: v for k, v in kwargs.items()
                                       if k in ("both", "passed", "goals", "flick", "identity")})
    return rb.build_bundle(components, directions, notes=kwargs.get("notes", "selfcheck"),
                           waive_roles=kwargs.get("waive_roles", ()), created_ns=1_700_000_000,
                           gate_current=kwargs.get("gate_current"),
                           require_verdict_identity=kwargs.get("require_verdict_identity", True))


def case_content_identity(checks: list) -> None:
    fixture = Fixture("identity")
    first = rb.file_component("policy", fixture.write("a", "same-bytes"), version="v1")
    second = rb.file_component("policy", fixture.write("b", "same-bytes"), version="v1")
    checks.append(("同内容不同路径 -> 同一内容身份", first.sha256 == second.sha256))
    changed = rb.file_component("policy", fixture.write("a", "other-bytes"), version="v1")
    checks.append(("内容变了 -> 身份变（路径没变也一样）", changed.sha256 != first.sha256))
    inline = rb.inline_component("schedule_config", {"n": 6}, version="v1")
    inline_same = rb.inline_component("schedule_config", {"n": 6}, version="v1")
    inline_diff = rb.inline_component("schedule_config", {"n": 7}, version="v1")
    checks.append(("内联配置也按内容寻址", inline.sha256 == inline_same.sha256
                   and inline.sha256 != inline_diff.sha256))


def case_component_binding(checks: list) -> None:
    fixture = Fixture("binding")
    try:
        build_ok(fixture, omit=("normalizer",))
        blocked = False
    except rb.MissingComponent:
        blocked = True
    checks.append(("缺 normalizer -> 拒绝发布（只换权重不算有效回滚）", blocked))
    bundle = build_ok(fixture, omit=("gpt_rubric", "replay_index"),
                      waive_roles=("gpt_rubric", "replay_index"))
    checks.append(("显式豁免可用且记进 manifest",
                   bundle.waived_roles == ("gpt_rubric", "replay_index")))
    try:
        build_ok(fixture, omit=("reward_view",), waive_roles=("reward_view", "not_a_required_role"))
        blocked_unknown = False
    except rb.BundleError:
        blocked_unknown = True
    checks.append(("豁免不在必需清单里的 role -> 拒绝（不许拿豁免绕过校验）", blocked_unknown))
    components = fixture.components()
    components.append(rb.inline_component("policy", {"dup": True}, version="v1"))
    try:
        rb.build_bundle(components, fixture.directions(checkpoint_sha="x", protocol_sha="y"),
                        created_ns=1)
        blocked_dup = False
    except rb.BundleError:
        blocked_dup = True
    checks.append(("同一 role 出现两次 -> 拒绝", blocked_dup))


def case_bidirectional(checks: list) -> None:
    fixture = Fixture("bidir")
    bundle = build_ok(fixture)
    checks.append(("双向都通过 -> 允许发布", bundle.bidirectional_pass is True))
    again = build_ok(fixture)
    checks.append(("bundle_id 可复算（确定性身份）", again.bundle_id == bundle.bundle_id))
    try:
        build_ok(fixture, both=False)
        blocked_single = False
    except rb.BidirectionalViolation:
        blocked_single = True
    checks.append(("只有单向评测 -> 拒绝发布", blocked_single))
    try:
        build_ok(fixture, passed=False)
        blocked_failed = False
    except rb.BidirectionalViolation:
        blocked_failed = True
    checks.append(("某方向未通过 -> 拒绝发布", blocked_failed))
    components = fixture.components()
    policy = next(c for c in components if c.role == "policy")
    protocol = next(c for c in components if c.role == "eval_protocol")
    mixed = fixture.directions(checkpoint_sha=policy.sha256, protocol_sha=protocol.sha256)
    mixed[1] = rb.DirectionScore(goal_id=mixed[1].goal_id, passed=True,
                                 checkpoint_sha256="f" * 64,
                                 eval_protocol_sha256=protocol.sha256,
                                 success_rate=0.99, n_episodes=20, source="cherry-pick")
    try:
        rb.build_bundle(components, mixed, created_ns=1)
        blocked_cherry = False
    except rb.BidirectionalViolation:
        blocked_cherry = True
    checks.append(("分方向各挑最优（checkpoint 不同份）-> 拒绝", blocked_cherry))
    mixed_protocol = fixture.directions(checkpoint_sha=policy.sha256, protocol_sha="a" * 64)
    try:
        rb.build_bundle(components, mixed_protocol, created_ns=1)
        blocked_protocol = False
    except rb.BidirectionalViolation:
        blocked_protocol = True
    checks.append(("两方向评测协议不一致 -> 拒绝", blocked_protocol))


def case_persistence_and_activation(checks: list) -> None:
    fixture = Fixture("activate")
    bundle = build_ok(fixture, notes="first")
    rb.write_bundle(bundle, SKILL, fixture.registry)
    rb.write_bundle(bundle, SKILL, fixture.registry)          # 幂等重写
    loaded = rb.load_bundle(SKILL, bundle.bundle_id, fixture.registry)
    checks.append(("manifest 可回读且身份一致", loaded.bundle_id == bundle.bundle_id
                   and loaded.component("policy").sha256 == bundle.component("policy").sha256))
    try:
        rb.activate_bundle(SKILL, bundle.bundle_id, slot_boundary_confirmed=False,
                           registry_root=fixture.registry)
        blocked = False
    except rb.MidChunkSwapRefused:
        blocked = True
    checks.append(("未确认槽边界 -> 拒绝热换权重", blocked))
    record = rb.activate_bundle(SKILL, bundle.bundle_id, slot_boundary_confirmed=True,
                                registry_root=fixture.registry, reason="首次晋级",
                                lease_generation=7)
    checks.append(("激活后 generation=1 且无前任",
                   record["generation"] == 1 and record["previous_bundle_id"] is None))
    checks.append(("激活记录带 lease 代次与槽边界确认",
                   record["lease_generation"] == 7 and record["slot_boundary_confirmed"] is True))
    other = build_ok(fixture, notes="second")
    rb.write_bundle(other, SKILL, fixture.registry)
    record2 = rb.activate_bundle(SKILL, other.bundle_id, slot_boundary_confirmed=True,
                                 registry_root=fixture.registry, reason="换版")
    checks.append(("再次激活 generation 递增并记前任",
                   record2["generation"] == 2 and record2["previous_bundle_id"] == bundle.bundle_id))
    # 磁盘上的 policy 被偷偷换掉 -> 内容身份核对不过，拒绝激活。
    policy_path = Path(other.component("policy").path)
    policy_path.write_text("tampered-weights", encoding="utf-8")
    verify = rb.verify_bundle(rb.load_bundle(SKILL, other.bundle_id, fixture.registry))
    checks.append(("verify_bundle 抓到内容漂移", verify["ok"] is False
                   and verify["mismatches"][0]["role"] == "policy"))
    try:
        rb.activate_bundle(SKILL, other.bundle_id, slot_boundary_confirmed=True,
                           registry_root=fixture.registry, reason="再换一次")
        blocked_tamper = False
    except rb.BundleError:
        blocked_tamper = True
    checks.append(("内容身份核对不过 -> 拒绝激活", blocked_tamper))


def case_rollback_and_contamination(checks: list) -> None:
    fixture = Fixture("rollback")
    first = build_ok(fixture, notes="v1")
    second = build_ok(fixture, notes="v2")
    for bundle in (first, second):
        rb.write_bundle(bundle, SKILL, fixture.registry)
    rb.activate_bundle(SKILL, first.bundle_id, slot_boundary_confirmed=True,
                       registry_root=fixture.registry, reason="首发")
    rb.activate_bundle(SKILL, second.bundle_id, slot_boundary_confirmed=True,
                       registry_root=fixture.registry, reason="晋级")
    try:
        rb.rollback(SKILL, to_bundle_id=first.bundle_id, slot_boundary_confirmed=True,
                    reason="   ", registry_root=fixture.registry)
        blocked_reason = False
    except rb.BundleError:
        blocked_reason = True
    checks.append(("回滚必须写原因", blocked_reason))
    record = rb.rollback(SKILL, to_bundle_id=first.bundle_id, slot_boundary_confirmed=True,
                         reason="双向成绩退化", registry_root=fixture.registry)
    active = rb.load_active(SKILL, fixture.registry)
    checks.append(("回滚后现任指向旧包且代次递增",
                   record["kind"] == "rollback" and active["bundle_id"] == first.bundle_id
                   and record["generation"] == 3))
    history = rb.activation_history(SKILL, fixture.registry)
    checks.append(("激活历史 append-only 可追溯",
                   len(history) == 3 and [h["kind"] for h in history] ==
                   ["promote", "promote", "rollback"]))
    rb.record_contamination(SKILL, first.bundle_id, reason="reward rubric v1 误判被撤销",
                            affected_views=["c-selfcheck:td"], revoked_label_seqs=[1234],
                            registry_root=fixture.registry)
    try:
        rb.activate_bundle(SKILL, first.bundle_id, slot_boundary_confirmed=True,
                           registry_root=fixture.registry, reason="想再切回去")
        blocked_pause = False
    except rb.ContaminatedBundle:
        blocked_pause = True
    checks.append(("污染记录后暂停晋级", blocked_pause))
    manifest = rb.deployment_manifest(SKILL, fixture.registry)
    checks.append(("DeploymentManifest 汇总现任/代次/暂停清单",
                   manifest["generation"] == 3 and manifest["paused"] == [first.bundle_id]
                   and manifest["n_activations"] == 3
                   and set(manifest["known_bundles"]) == {first.bundle_id, second.bundle_id}))
    log = (rb.deployment_dir(SKILL, fixture.registry) / "contamination.jsonl").read_text()
    checks.append(("污染记录写明受影响视图与撤销标签",
                   "c-selfcheck:td" in log and "1234" in log))


def case_real_registry_untouched(checks: list) -> None:
    real = ROOT / "registry"
    before = {p.name for p in real.iterdir()}
    checks.append(("自检没有往真实 registry 写东西",
                   not (real / SKILL).exists() and "bundles" not in before))


CASES = (case_content_identity, case_component_binding, case_bidirectional,
         case_persistence_and_activation, case_rollback_and_contamination,
         case_real_registry_untouched)


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
