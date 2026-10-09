"""C 线：ReleaseBundle / DeploymentManifest —— 整体边界发布与回滚身份。

补的是 v4 附录 01 §6（B5）的要求：发布包必须**绑定**共享 policy、Q/target 与优化器、
观测处理、normalizer、动作契约、执行调度配置、任务契约、Harness 程序、GPT 模型/提示/rubric、
奖励视图、回放索引与评测协议；**原始路径不能代替内容身份**，只换权重而不换匹配预处理
不算有效回滚。主方案另外规定：发布必须是同一 checkpoint 双向通过后**整体边界替换**，
禁止分方向各挑最优、禁止 chunk 中途热换权重。

与既有 `registry/publish.py` 的关系：那一层负责「技能版本 + 门禁判定」，写
`registry/<skill>/<version>/`；本层负责「一次部署的完整身份 + 原子换版」，写
`registry/<skill>/bundles/<bundle_id>/` 与 `registry/<skill>/deployment/`。
两者互不覆盖：本层不写 `current.json`（那是 `publish.load_current()` 的指针）。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "registry"
CONTRACT_VERSION = "v4-appendix01-B5"

# 附录 01 §6 列出的发布包必须绑定的组件。缺哪个都要显式声明豁免，不允许静默省略。
REQUIRED_ROLES = (
    "policy", "q", "q_target", "optimizer", "obs_pipeline", "normalizer",
    "action_contract", "schedule_config", "task_contract", "harness_programs",
    "gpt_rubric", "reward_view", "replay_index", "eval_protocol",
)
DEFAULT_DIRECTIONS = ("A_to_B", "B_to_A")
_CHUNK = 1 << 20


class BundleError(RuntimeError):
    """发布包本身的构造/校验错误。"""


class MissingComponent(BundleError):
    """缺少必须绑定的组件，且没有显式豁免。"""


class BidirectionalViolation(BundleError):
    """双向发布契约被破坏：分方向各挑最优、单向通过、或 checkpoint 身份不一致。"""


class MidChunkSwapRefused(BundleError):
    """未确认槽边界就想换权重：禁止 chunk 中途热换。"""


class ContaminatedBundle(BundleError):
    """该发布包已被污染记录暂停晋级。"""


class VerdictIdentityViolation(BundleError):
    """方向评测缺裁定身份、或身份与门禁现值不符 ⇒ **拒收**（与「双向同 checkpoint」红线同级）。

    判据不在这里（裁定 21 判据单一来源）：`usable_for` 词汇表与准入规则由
    `registry/verdict_identity.py` 拥有，本模块只执行它的结论。
    """


def content_sha256(path: str | Path) -> str:
    """文件内容身份（不是路径身份）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def inline_sha256(payload: Any) -> str:
    """内联配置的内容身份：规范化 JSON 后取 sha256。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ComponentRef:
    role: str
    kind: str                 # file | inline
    sha256: str
    version: str
    path: str | None = None
    inline: Any = None
    notes: str = ""

    def identity(self) -> dict[str, Any]:
        return {"role": self.role, "kind": self.kind, "sha256": self.sha256,
                "version": self.version, "path": self.path, "notes": self.notes}


def file_component(role: str, path: str | Path, *, version: str, notes: str = "") -> ComponentRef:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"{role} 组件不存在: {target}")
    return ComponentRef(role=role, kind="file", sha256=content_sha256(target), version=version,
                        path=str(target), notes=notes)


def inline_component(role: str, payload: Any, *, version: str, notes: str = "") -> ComponentRef:
    return ComponentRef(role=role, kind="inline", sha256=inline_sha256(payload), version=version,
                        inline=payload, notes=notes)


@dataclass(frozen=True)
class DirectionScore:
    """一个方向的独立评测结果。`checkpoint_sha256` 必须与发布包的 policy 组件一致。"""
    goal_id: str
    passed: bool
    checkpoint_sha256: str
    eval_protocol_sha256: str
    success_rate: float
    n_episodes: int
    success_rate_grasp_verified: float | None = None
    flick_frac: float | None = None
    controlled_success_rate: float | None = None
    source: str = ""
    notes: str = ""
    # --- 裁定身份（P1-5：增补五 §9-C③ / 裁定 29.1「引用锚在 build 轴」）---
    # 这些是**字段**，不是注释：缺了它们，读发布包的人就无从判断这个数字出自哪一版判据、
    # 还能不能当事实用。值由 `registry.verdict_identity.direction_identity()` 填，
    # 与 `artifact_identity()` **同源同义**（`gate_build` / `is_current_build` / `usable_for`
    # 三个字段不另写一套 —— D 派工单 P1-6 的硬要求）。
    gate_version: str | None = None
    gate_build: str | None = None
    gate_spec_sha256: str | None = None
    verdict_sha256: str | None = None
    measurement_valid: Any = None
    usable_for: str | None = None
    provenance_kind: str | None = None
    is_current_build: bool | None = None
    superseded_by: str | None = None
    regraded_from: str | None = None


@dataclass(frozen=True)
class ReleaseBundle:
    bundle_id: str
    contract_version: str
    components: tuple[ComponentRef, ...]
    directions: tuple[DirectionScore, ...]
    bidirectional_pass: bool
    waived_roles: tuple[str, ...]
    created_ns: int
    notes: str = ""
    contamination: tuple[dict[str, Any], ...] = field(default=())

    def component(self, role: str) -> ComponentRef:
        for item in self.components:
            if item.role == role:
                return item
        raise MissingComponent(f"发布包里没有 {role} 组件")

    def to_dict(self) -> dict[str, Any]:
        return {"bundle_id": self.bundle_id, "contract_version": self.contract_version,
                "components": [c.identity() for c in self.components],
                "component_inline": {c.role: c.inline for c in self.components if c.kind == "inline"},
                "directions": [asdict(d) for d in self.directions],
                "bidirectional_pass": self.bidirectional_pass, "waived_roles": list(self.waived_roles),
                "created_ns": self.created_ns, "notes": self.notes,
                "contamination": list(self.contamination)}


def _canonical_bundle_id(contract_version: str, components: Sequence[ComponentRef],
                         directions: Sequence[DirectionScore], notes: str) -> str:
    payload = {
        "contract_version": contract_version,
        "components": sorted((c.identity() for c in components), key=lambda d: d["role"]),
        "component_inline": {c.role: c.inline for c in components if c.kind == "inline"},
        "directions": sorted((asdict(d) for d in directions), key=lambda d: d["goal_id"]),
        "notes": notes,
    }
    return inline_sha256(payload)


def _physical_fact_token() -> str:
    """`usable_for` 词汇表的**单一来源**是 `registry/verdict_identity.py`（裁定 21）。

    这里 import 它而不是在本模块抄一份常量：抄一份就有了第二份口径，
    两边一旦漂移，「发布包只收 physical_fact」这句会变成一句看不出错的话。
    延迟 import：不让发布包模块在导入期就拉起裁定层（它又会去加载上游门禁模块）。
    """
    from registry.verdict_identity import USABLE_PHYSICAL_FACT
    return USABLE_PHYSICAL_FACT


def _require_verdict_identity(scores: Sequence["DirectionScore"], *,
                              gate_current: Mapping[str, Any] | str | None,
                              required: bool) -> None:
    """发布包的身份红线：**缺身份不许进包**，**构建不符必须拒收**（不是 warn）。

    `gate_current` 给了就逐方向比 `gate_build`；比的是**调用时的门禁现值**，
    不是当初解析裁定时存下的那份 —— 判据在脚下移动过就必须重新对表。
    **预先写明的后果**（D 派工单「与 B §5 的交点」）：B 的 v1.6 落地会升 `GATE_BUILD`，
    届时现存 48 条 `physical_fact` 会整批不符 ⇒ 本函数全部拒收。
    **那是正确行为，不是回归红点。**
    """
    token = _physical_fact_token()
    expect: str | None = None
    if gate_current is not None:
        expect = str(gate_current.get("gate_build") if isinstance(gate_current, Mapping)
                     else gate_current)
    gaps = [(d.goal_id, [n for n in ("gate_build", "verdict_sha256", "usable_for")
                         if not getattr(d, n, None)]) for d in scores]
    gaps = [(g, missing) for g, missing in gaps if missing]
    if required and gaps:
        raise VerdictIdentityViolation(
            f"以下方向缺裁定身份字段（缺身份不许进发布包，与「双向同 checkpoint」红线同级）: {gaps}。"
            f"身份请用 registry.verdict_identity.direction_identity(record) 填，不要手抄。")
    if required:
        wrong_grade = [(d.goal_id, d.usable_for) for d in scores if d.usable_for != token]
        if wrong_grade:
            raise VerdictIdentityViolation(
                f"以下方向的 usable_for 不是 {token!r} ⇒ 不得进发布包: {wrong_grade}。"
                f"留档/比对可以，当事实不行（词汇表见 registry/verdict_identity.py）。")
        not_current = [(d.goal_id, d.is_current_build, d.gate_build) for d in scores
                       if d.is_current_build is not True]
        if not_current:
            raise VerdictIdentityViolation(
                f"以下方向自称 is_current_build != True ⇒ 不得进发布包: {not_current}")
    if expect is not None:
        offenders = [(d.goal_id, d.gate_build) for d in scores
                     if str(d.gate_build or "") != expect]
        if offenders:
            raise VerdictIdentityViolation(
                f"以下方向的 gate_build 与门禁现值 {expect} 不符 ⇒ **拒收，不是 warn**"
                f"（裁定 29.1：引用锚在 build 轴）: {offenders}。"
                f"若门禁刚升版（例如 B 的 v1.6），正确动作是在新构建上重新出裁定，不是放宽本闸。")


def build_bundle(components: Iterable[ComponentRef], directions: Iterable[DirectionScore], *,
                 contract_version: str = CONTRACT_VERSION, notes: str = "",
                 required_roles: Sequence[str] = REQUIRED_ROLES,
                 waive_roles: Sequence[str] = (),
                 required_directions: Sequence[str] = DEFAULT_DIRECTIONS,
                 created_ns: int | None = None,
                 gate_current: Mapping[str, Any] | str | None = None,
                 require_verdict_identity: bool = True) -> ReleaseBundle:
    """组装并校验发布包。校验不过直接抛错，不产出半成品。

    `require_verdict_identity=True`（默认）⇒ 每个方向必须自带裁定身份且
    `usable_for == physical_fact`；`gate_current` 给了就再逐方向比 `gate_build`。
    两条都是**拒收**（抛 `VerdictIdentityViolation`），不是 warn。
    """
    items = tuple(components)
    scores = tuple(directions)
    roles = [c.role for c in items]
    if len(set(roles)) != len(roles):
        duplicates = sorted({r for r in roles if roles.count(r) > 1})
        raise BundleError(f"组件 role 重复: {duplicates}")
    unknown_waiver = [r for r in waive_roles if r not in required_roles]
    if unknown_waiver:
        raise BundleError(f"豁免了不在必需清单里的 role: {unknown_waiver}")
    missing = [r for r in required_roles if r not in roles and r not in waive_roles]
    if missing:
        raise MissingComponent(f"缺少必须绑定的组件 {missing}；确实没有就显式写进 waive_roles，"
                               f"豁免会记进 manifest")
    for item in items:
        if not item.sha256:
            raise BundleError(f"组件 {item.role} 没有内容身份（sha256 为空）")

    policy = next((c for c in items if c.role == "policy"), None)
    protocol = next((c for c in items if c.role == "eval_protocol"), None)
    covered = {d.goal_id for d in scores}
    absent = [g for g in required_directions if g not in covered]
    if absent:
        raise BidirectionalViolation(f"缺方向的独立评测: {absent}；单向通过不得发布")
    failed = [d.goal_id for d in scores if not d.passed]
    if failed:
        raise BidirectionalViolation(f"以下方向未通过独立评测: {failed}")
    if policy is not None:
        offenders = sorted({d.checkpoint_sha256 for d in scores if d.checkpoint_sha256 != policy.sha256})
        if offenders:
            raise BidirectionalViolation(
                f"分方向各挑最优：方向评测用的 checkpoint {offenders} 与发布包 policy "
                f"{policy.sha256[:12]} 不是同一份内容")
    if protocol is not None:
        offenders = sorted({d.eval_protocol_sha256 for d in scores
                            if d.eval_protocol_sha256 != protocol.sha256})
        if offenders:
            raise BidirectionalViolation(f"方向评测协议不一致: {offenders}")

    _require_verdict_identity(scores, gate_current=gate_current,
                              required=require_verdict_identity)

    return ReleaseBundle(
        bundle_id=_canonical_bundle_id(contract_version, items, scores, notes),
        contract_version=contract_version, components=items, directions=scores,
        bidirectional_pass=True, waived_roles=tuple(sorted(waive_roles)),
        created_ns=int(created_ns if created_ns is not None else time.time_ns()), notes=notes)


# ---------------- 持久化 / 原子换版 ----------------
def bundle_dir(skill_name: str, bundle_id: str, registry_root: str | Path = DEFAULT_REGISTRY) -> Path:
    return Path(registry_root) / skill_name / "bundles" / bundle_id


def deployment_dir(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> Path:
    return Path(registry_root) / skill_name / "deployment"


def write_bundle(bundle: ReleaseBundle, skill_name: str,
                 registry_root: str | Path = DEFAULT_REGISTRY) -> Path:
    """写 manifest。同 bundle_id 已存在且内容不同 -> 拒绝（append-only）。"""
    target = bundle_dir(skill_name, bundle.bundle_id, registry_root)
    manifest = target / "manifest.json"
    text = json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if manifest.exists():
        existing = json.loads(manifest.read_text(encoding="utf-8"))
        if existing.get("bundle_id") != bundle.bundle_id or \
                inline_sha256(existing) != inline_sha256(bundle.to_dict()):
            raise BundleError(f"bundle_id {bundle.bundle_id} 已存在且内容不同，拒绝覆盖")
        return target
    target.mkdir(parents=True, exist_ok=True)
    manifest.write_text(text, encoding="utf-8")
    return target


def load_bundle(skill_name: str, bundle_id: str,
                registry_root: str | Path = DEFAULT_REGISTRY) -> ReleaseBundle:
    manifest = bundle_dir(skill_name, bundle_id, registry_root) / "manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(f"发布包不存在: {manifest}")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    components = tuple(ComponentRef(role=c["role"], kind=c["kind"], sha256=c["sha256"],
                                    version=c["version"], path=c.get("path"),
                                    inline=raw.get("component_inline", {}).get(c["role"]),
                                    notes=c.get("notes", "")) for c in raw["components"])
    directions = tuple(DirectionScore(**d) for d in raw["directions"])
    return ReleaseBundle(bundle_id=raw["bundle_id"], contract_version=raw["contract_version"],
                         components=components, directions=directions,
                         bidirectional_pass=raw["bidirectional_pass"],
                         waived_roles=tuple(raw.get("waived_roles", ())),
                         created_ns=int(raw["created_ns"]), notes=raw.get("notes", ""),
                         contamination=tuple(raw.get("contamination", ())))


def verify_bundle(bundle: ReleaseBundle) -> dict[str, Any]:
    """按内容身份重新核对磁盘上的组件：抓「只换权重不换预处理」和路径漂移。"""
    mismatches, missing = [], []
    for item in bundle.components:
        if item.kind != "file":
            if inline_sha256(item.inline) != item.sha256:
                mismatches.append({"role": item.role, "reason": "inline content changed"})
            continue
        path = Path(item.path or "")
        if not path.exists():
            missing.append({"role": item.role, "path": item.path})
            continue
        actual = content_sha256(path)
        if actual != item.sha256:
            mismatches.append({"role": item.role, "path": item.path,
                               "expected": item.sha256, "actual": actual})
    return {"ok": not mismatches and not missing, "bundle_id": bundle.bundle_id,
            "mismatches": mismatches, "missing": missing}


def record_contamination(skill_name: str, bundle_id: str, *, reason: str,
                         affected_views: Sequence[str] = (), revoked_label_seqs: Sequence[int] = (),
                         registry_root: str | Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    """标签/评分被撤销后暂停该发布包晋级（附录 01 §污染追踪）。追加，不改历史。"""
    entry = {"bundle_id": bundle_id, "recorded_ns": time.time_ns(), "reason": reason,
             "affected_views": list(affected_views),
             "revoked_label_seqs": [int(s) for s in revoked_label_seqs]}
    deploy = deployment_dir(skill_name, registry_root)
    deploy.mkdir(parents=True, exist_ok=True)
    with open(deploy / "contamination.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    paused_path = deploy / "paused.json"
    paused = json.loads(paused_path.read_text(encoding="utf-8")) if paused_path.exists() else []
    if bundle_id not in paused:
        paused.append(bundle_id)
    _atomic_write_json(paused_path, paused)
    return entry


def paused_bundles(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> list[str]:
    path = deployment_dir(skill_name, registry_root) / "paused.json"
    return list(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else []


def load_active(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> dict[str, Any] | None:
    path = deployment_dir(skill_name, registry_root) / "current.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def activation_history(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> list[dict]:
    path = deployment_dir(skill_name, registry_root) / "history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _atomic_write_json(path: Path, payload: Any) -> None:
    """整体边界替换：先写临时文件再 `os.replace`，不留半份 manifest。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def activate_bundle(skill_name: str, bundle_id: str, *, slot_boundary_confirmed: bool,
                    registry_root: str | Path = DEFAULT_REGISTRY, reason: str = "",
                    kind: str = "promote", lease_generation: int | None = None,
                    verify: bool = True) -> dict[str, Any]:
    """把某个发布包整体切成现任。

    三条拒绝：未确认槽边界（禁止 chunk 中途热换）、内容身份核对不过、已被污染暂停。
    """
    if not slot_boundary_confirmed:
        raise MidChunkSwapRefused(
            "未确认已到固定交接点：禁止在 chunk 中途热换权重（附录 01 §6 / 主方案 §发布）")
    if bundle_id in paused_bundles(skill_name, registry_root):
        raise ContaminatedBundle(f"{bundle_id} 已被污染记录暂停晋级，先处置撤销与重训")
    bundle = load_bundle(skill_name, bundle_id, registry_root)
    if verify:
        result = verify_bundle(bundle)
        if not result["ok"]:
            raise BundleError(f"内容身份核对不过: {json.dumps(result, ensure_ascii=False)}")
    previous = load_active(skill_name, registry_root)
    generation = int((previous or {}).get("generation", 0)) + 1
    record = {"skill": skill_name, "bundle_id": bundle_id, "generation": generation,
              "kind": kind, "activated_ns": time.time_ns(), "reason": reason,
              "previous_bundle_id": (previous or {}).get("bundle_id"),
              "previous_generation": (previous or {}).get("generation"),
              "slot_boundary_confirmed": True, "lease_generation": lease_generation,
              "contract_version": bundle.contract_version,
              "directions": [asdict(d) for d in bundle.directions],
              "component_sha256": {c.role: c.sha256 for c in bundle.components},
              "waived_roles": list(bundle.waived_roles)}
    deploy = deployment_dir(skill_name, registry_root)
    deploy.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(deploy / "current.json", record)
    with open(deploy / "history.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def rollback(skill_name: str, *, to_bundle_id: str, slot_boundary_confirmed: bool,
             reason: str, registry_root: str | Path = DEFAULT_REGISTRY,
             lease_generation: int | None = None) -> dict[str, Any]:
    """回滚到某个历史发布包。回滚同样要过内容身份核对——路径不能代替内容。"""
    if not reason.strip():
        raise BundleError("回滚必须写原因，否则事后无法解释为什么退版本")
    return activate_bundle(skill_name, to_bundle_id, slot_boundary_confirmed=slot_boundary_confirmed,
                           registry_root=registry_root, reason=reason, kind="rollback",
                           lease_generation=lease_generation)


def bundle_ids(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> list[str]:
    root = Path(registry_root) / skill_name / "bundles"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "manifest.json").exists())


def deployment_manifest(skill_name: str, registry_root: str | Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    """当前部署身份（DeploymentManifest）：现任 bundle + 代次 + 历史长度 + 暂停清单。"""
    active = load_active(skill_name, registry_root)
    return {"skill": skill_name, "active": active,
            "generation": (active or {}).get("generation"),
            "n_activations": len(activation_history(skill_name, registry_root)),
            "paused": paused_bundles(skill_name, registry_root),
            "known_bundles": bundle_ids(skill_name, registry_root)}


def as_dict(obj: Any) -> Mapping[str, Any]:
    return obj.to_dict() if hasattr(obj, "to_dict") else asdict(obj)
