#!/usr/bin/env python3
"""C 线自检：裁定身份与有效性层（`registry/verdict_identity.py`，D 清单 P0-3 第一层）。

要钉住的不是「能解析 JSON」，而是四条会致命的性质：

1. **不作越级**：旧 `gate_build`、`measurement_valid=False`、缺身份的裁定，一律不得被标成
   `physical_fact`。照现状 ingest 会把已作废的数字当物理事实写进 append-only 账本。
2. **不重算判据**：所有数字都取自上游落盘值，本层只做绑定与分级（否则就是第二套判据）。
3. **只读上游**：扫 A/B 的产物目录不得改动其中任何文件（大小与 mtime 逐文件核对）。
4. **分级不是恒真**：变异自检把 `classify` 换成「一律 physical_fact」，上面的断言必须转红。

产物：`runs/infra/c_verdict_identity_inventory.json`（全量清单）+ `runs/infra/c_verdict_selfcheck.json`。
临时裁定写在 `runs/infra/c_verdict_selfcheck/<时间戳>/`，**不写** A/B 的目录、不写 `registry/`。

用法：/root/venvs/rlrobot/bin/python scripts/c_selfcheck_verdict_identity.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from registry import verdict_identity as vi  # noqa: E402

UPSTREAM_DIR = ROOT / "runs" / "infra" / "lerobot_act_env_20260928"
OUT_ROOT = ROOT / "runs" / "infra" / "c_verdict_selfcheck" / time.strftime("%Y%m%d_%H%M%S")
OUT_JSON = ROOT / "runs" / "infra" / "c_verdict_selfcheck.json"
OUT_INVENTORY = ROOT / "runs" / "infra" / "c_verdict_identity_inventory.json"
# 门禁构建的观测流水（append-only）：本轮就实测到 B 把判据从 v1.2.1 升到 v1.3，
# 63 条原判 physical_fact 的裁定当场全部降级为「待重判」。构建会在 C 脚下移动，
# 所以每次扫描都留一行「此刻当前构建是什么」，事后才能解释某份清单为什么是那个分布。
OUT_BUILD_LOG = ROOT / "runs" / "infra" / "c_gate_build_observed.jsonl"


def _dir_fingerprint(directory: Path) -> dict[str, tuple[int, int]]:
    """目录指纹：相对路径 → (size, mtime_ns)。用来证明「只读」不是嘴上说的。"""
    return {str(p.relative_to(directory)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def _write_verdict(path: Path, *, gate_build, measurement_valid=True, suspect=False,
                   controlled=3, denominator=20, arm="synthetic_arm",
                   ic_status="verified_ok") -> Path:
    """造一份**结构同形**的合成裁定（只用于分级测试，数字无物理意义）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{
        "file": f"runs/infra/c_verdict_selfcheck/eval_{arm}.json",
        "controller": "synthetic", "gate_version": "vSYN", "gate_build": gate_build,
        "gate_spec_sha256": "synthetic", "field_class": "strict", "missing_fields": [],
        "episodes_total": denominator, "raw_success": controlled, "gate_pass": controlled > 0,
        "gate_reason": "ok" if controlled > 0 else "no_controlled_success",
        "measurement_valid": measurement_valid,
        "terminal_semantics": {"suspect_truncation_labeled_as_failure": suspect},
        "input_contract": {"status": ic_status},
        "accounts": {"policy_independent": {"denominator": denominator, "controlled_success": controlled,
                                            "provisional_pass": 0, "over_lift": 0, "flick": 0,
                                            "insufficient_lift": 0},
                     "system_assisted": {"denominator": denominator, "controlled_success": controlled},
                     "autonomous_learning": {"denominator": 0, "controlled_success": None}},
    }]
    if gate_build is None:
        del payload[0]["gate_build"]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. 当前构建身份是 import 来的，不是硬编码的
# ---------------------------------------------------------------------------
def _import_gate_module():
    spec = importlib.util.spec_from_file_location("_gate_probe", vi.GATE_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stable_gate_snapshot(tries: int = 6, pause: float = 1.0) -> tuple[dict, Any, bool, list[str]]:
    """取一个**自洽**的当前构建快照：连续多次读到的内容指纹必须相同。

    为什么需要它：这一条核对要读上游门禁脚本好几次（算 sha、import 拿属性、再算 sha），
    而 `GATE_BUILD` 就是该脚本内容的指纹 —— B 正在改判据时（本轮 20 分钟内实测改了 3 次），
    几次读到的东西天然不同。那不是 C 读错，是上游在动；两者必须分开报告，
    否则自检会在别人正常工作时随机转红，久了就没人信它的红。
    """
    seen: list[str] = []
    for _ in range(tries):
        sha0 = vi.content_sha256(vi.GATE_MODULE_PATH)
        probe = _import_gate_module()
        cur = vi.current_gate_identity(refresh=True)
        sha1 = vi.content_sha256(vi.GATE_MODULE_PATH)
        seen.extend([sha0[:12], cur["module_sha256"][:12], sha1[:12]])
        if sha0 == sha1 == cur["module_sha256"]:
            return cur, probe, True, sorted(set(seen))
        time.sleep(pause)
    return cur, probe, False, sorted(set(seen))


def case_current_gate_identity_is_imported(checks: list) -> None:
    cur, probe, stable, seen = _stable_gate_snapshot()
    checks.append(("gate_version / gate_build / gate_spec_sha256 都非空（缺任一就无法判定新旧）",
                   bool(cur["gate_version"]) and bool(cur["gate_build"])
                   and bool(cur["gate_spec_sha256"])))
    # 「不硬编码」要查的是**代码里有没有自己定义一份门禁常量**，不是文档里能不能提到版本号：
    # docstring 写「一天内连升 v1.1 → v1.2.1」是叙述事实，把它判成违规会逼人删掉有用的记录。
    src_text = Path(vi.__file__).read_text(encoding="utf-8")
    own_constants = [ln for ln in src_text.splitlines()
                     if re.match(r"\s*(GATE_VERSION|GATE_BUILD|GATE_SPEC_SHA256|GATE_SPEC_SHA)\s*=",
                                 ln)]
    checks.append(("C 侧不自定义门禁常量（GATE_VERSION/BUILD/SPEC_SHA 只能 import 上游的）",
                   not own_constants))
    if stable:
        checks.append(("当前门禁身份来自 import：module_sha256 与实算一致",
                       cur["module_sha256"] == vi.content_sha256(vi.GATE_MODULE_PATH)))
        checks.append(("gate_build 就是门禁脚本自身内容的指纹（B 改判据 ⇒ C 自动跟随）",
                       cur["gate_build"] == cur["module_sha256"][:12]))
        checks.append(("读到的版本/构建/spec 指纹与上游模块属性逐项相同（不是 C 自己编的）",
                       cur["gate_version"] == probe.GATE_VERSION
                       and cur["gate_build"] == probe.GATE_BUILD
                       and cur["gate_spec_sha256"] == probe.GATE_SPEC_SHA))
    else:
        # 上游在核对期间被改写：这几条**没被验证**，如实记 SKIP，不算通过也不算失败。
        reason = f"上游门禁脚本在 {len(seen)} 次读取间被改写（指纹 {seen}）"
        for name in ("当前门禁身份来自 import：module_sha256 与实算一致",
                     "gate_build 就是门禁脚本自身内容的指纹（B 改判据 ⇒ C 自动跟随）",
                     "读到的版本/构建/spec 指纹与上游模块属性逐项相同（不是 C 自己编的）"):
            checks.append((f"{name} —— SKIP：{reason}", None))
        print(f"  SKIP：{reason}；本次快照按 {cur['gate_version']}/{cur['gate_build']} 继续",
              flush=True)


# ---------------------------------------------------------------------------
# 2. 真目录清单：分级不得越级
# ---------------------------------------------------------------------------
def case_real_dir_inventory(checks: list) -> None:
    # 只给**本次真的读了的**文件按指纹：上游目录此刻正被 A/B 并发写入（本轮实测到 B 在
    # 几分钟内连改两次门禁脚本、A 新建 ckptseq/），拿整个目录树比会把别人的正常写入
    # 算成 C 的锅。若这条失败，两种含义都要查：要么 C 写了上游，要么上游在扫描期间被改写
    # ⇒ 本份清单已不自洽，必须重跑。
    scanned = sorted(UPSTREAM_DIR.rglob("gate_*.json"))
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in scanned}
    inv = vi.scan_dir(UPSTREAM_DIR)
    after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
             for p in sorted(UPSTREAM_DIR.rglob("gate_*.json")) if str(p) in before}
    checks.append(("上游裁定全部可解析（parse_errors 为空）", inv["parse_errors"] == []))
    checks.append(("扫到裁定 > 0 条", inv["n_verdicts"] > 0))
    builds = inv["build_distribution"]
    checks.append((f"实证：同一目录里并存多个 gate_build（本次 {len(builds)} 个）", len(builds) > 1))
    recs = inv["records"]
    checks.append((f"每条记录的 usable_for 都在 {len(vi.USABLE_LEVELS)} 档枚举内",
                   all(r["usable_for"] in vi.USABLE_LEVELS for r in recs)))
    cur = inv["gate_current"]["gate_build"]
    facts = [r for r in recs if r["usable_for"] == vi.USABLE_PHYSICAL_FACT]
    checks.append(("physical_fact ⇒ 必出自当前构建 + measurement_valid is True + 不怀疑截断当失败",
                   all(str(r["gate_build"]) == str(cur) and r["measurement_valid"] is True
                       and r["suspect_truncation_as_failure"] is not True for r in facts)))
    checks.append(("反向不越级：非当前构建的裁定没有一条被标成 physical_fact",
                   all(r["usable_for"] != vi.USABLE_PHYSICAL_FACT
                       for r in recs if str(r["gate_build"]) != str(cur))))
    # 增补六 §8-C3 之后这条不再是无条件的：权威表已记免罪而门禁未承载的那批，
    # 落 `pending_impl_ruling_approved` 而不是 `invalid_measurement`（见 case_pending_impl_grade）。
    # 排除条件用**独立手写**的判据，不调 vi.is_pending_impl_exoneration —— 这一节的价值
    # 就在于它是第二条代码路径；调同一个函数等于自己核对自己。
    def _pending_expected(r: dict) -> bool:
        return (str(r["validity_class"]) == vi.AUTHORITY_EXONERATED
                and str(r["input_contract_status"]) != vi.GATE_EXONERATED)

    checks.append(("上游明确判 measurement_valid=False 且构建已知 ⇒ invalid_measurement"
                   "（例外：终局语义怀疑、权威表已会签免罪而门禁未承载 —— 后者按裁定 31.4 "
                   "收窄后或留本档、或转 stale_build_evidence，两者都不进 invalid_measurement）",
                   all(r["usable_for"] == vi.USABLE_INVALID_MEASUREMENT
                       for r in recs if r["measurement_valid"] is False
                       and r["measurement_validity_declared"] and r["gate_build"] not in (None, "")
                       and r["suspect_truncation_as_failure"] is not True
                       and not _pending_expected(r))))
    checks.append(("measurement_valid=False 但构建缺失 ⇒ 归 unidentified（身份先于有效性）",
                   all(r["usable_for"] == vi.USABLE_UNIDENTIFIED
                       for r in recs if r["measurement_valid"] is False
                       and r["gate_build"] in (None, ""))))
    checks.append(("有效性**未声明**（字段缺失）不等于 INVALID：不替上游下结论，且绝不当事实",
                   all(r["usable_for"] in (vi.USABLE_UNIDENTIFIED, vi.USABLE_NOT_A_VERDICT)
                       for r in recs if not r["measurement_validity_declared"])))
    checks.append(("聚合/敏感度报告标 not_a_verdict，且绝不当物理事实",
                   all(r["usable_for"] == vi.USABLE_NOT_A_VERDICT
                       for r in recs if not r["arm_verdict"])))

    # 分级必须**穷尽且可复算**：用独立重写的一遍规则逐条复算，与 classify 的结果对齐。
    # 两条独立代码路径互相核对（同 `manual_bc_loss` 的做法），比只断言"都在枚举内"强得多 ——
    # 后者对任何常量实现都成立。
    # 裁定 31.4：本档激活条件**收窄**（跨记录条件）。这里独立手写一遍承载集的判据
    # （不调 vi.regrade_pending_impl），两条代码路径对齐才算互核。
    carried_arms = {r["arm"] for r in recs
                    if str(r["gate_build"]) == str(cur)
                    and str(r["input_contract_status"]) == vi.GATE_EXONERATED}

    def expected_level(r: dict) -> str:
        if not r["arm_verdict"]:
            return vi.USABLE_NOT_A_VERDICT
        if r["gate_build"] in (None, ""):
            return vi.USABLE_UNIDENTIFIED
        if not r["measurement_validity_declared"]:
            return vi.USABLE_UNIDENTIFIED
        # 终局语义优先于免罪：裁定 10 的探针免罪只针对输入契约 / blown 那一维，
        # 覆盖不到「把截断标成失败」。这一行若被挪到 _pending_expected 之后，
        # 免罪就变成万能牌（case_pending_impl_grade 的变异会当场抓到）。
        if r["suspect_truncation_as_failure"] is True:
            return vi.USABLE_INVALID_MEASUREMENT
        if _pending_expected(r):
            # 该臂在当前构建下**已有**承载免罪的产物 ⇒ 这份只是旧构建留档，
            # 它的 violated 是探针的预期结果 / 锚点的设计使然 ⇒ 转 stale（裁定 31.4 判 (b)）。
            return (vi.USABLE_STALE_BUILD if r["arm"] in carried_arms
                    else vi.USABLE_PENDING_IMPL)
        if r["measurement_valid"] is not True:
            return vi.USABLE_INVALID_MEASUREMENT
        if str(r["gate_build"]) != str(cur):
            return vi.USABLE_STALE_BUILD
        return vi.USABLE_PHYSICAL_FACT

    disagree = [r["source_path"] for r in recs if expected_level(r) != r["usable_for"]]
    checks.append((f"分级穷尽：{len(recs)} 条记录用独立重写的规则复算，逐条一致", not disagree))
    if disagree:
        print(f"  分级不一致样本: {disagree[:5]}", flush=True)
    prov = inv["provenance_distribution"]
    checks.append(("来源分层覆盖全部记录（各层计数之和 == 裁定总数）",
                   sum(prov.values()) == inv["n_verdicts"] and bool(prov)))
    checks.append(("分层里能同时看到原始留档与重判产物（否则「裸 ingest 顶层」的风险看不出来）",
                   "<top-level>" in prov and any("regate_current" in k for k in prov)))
    top = inv["usable_for_by_provenance"].get("<top-level>", {})
    checks.append(("顶层留档裁定里存在不可当事实的记录（这一层存在的理由，实证）",
                   sum(v for k, v in top.items() if k != vi.USABLE_PHYSICAL_FACT) > 0))
    checks.append(("gate_build 缺失 ⇒ unidentified_build（连「旧」都说不清，不当事实）",
                   all(r["usable_for"] == vi.USABLE_UNIDENTIFIED
                       for r in recs if r["gate_build"] in (None, ""))))
    checks.append(("三套账与五档 bucket 的键名齐备（值可以是 None，键不许少）",
                   all(set(r["accounts"]) == set(vi.ACCOUNTS) and set(r["buckets"]) == set(vi.BUCKETS)
                       for r in recs)))
    # 只读证明：上游目录逐文件 size + mtime_ns 不变
    # 只读性用**两条**证据，一条与时间无关、一条是实测：
    #   (a) 结构证据：`verdict_identity.py` 全文不含任何写 API —— 这条不受上游并发写入影响；
    #   (b) 实测证据：本次读过的文件扫描前后 size/mtime 不变。上游正在被 A/B 改写时
    #       这条会假红，所以变动一律记 SKIP（未被验证）而不是 FAIL，并要求重跑。
    # 结构证据要用**精确**的模式：第一版把 `str.replace(` 也算成 `Path.replace(`（改名），
    # 于是身份层里一次正常的字符串处理就把这条判红了 —— 粗匹配的检查自己就是噪声源。
    lib_src = Path(vi.__file__).read_text(encoding="utf-8")
    write_patterns = (r"\.write_text\(", r"\.write_bytes\(", r"\.mkdir\(", r"\.unlink\(",
                      r"\.rename\(", r"\.touch\(", r"\.chmod\(", r"\bshutil\.",
                      r"\bos\.remove\b", r"\bos\.unlink\b", r"\bos\.rename\b",
                      r"\bos\.replace\b", r"\bPath\([^)]*\)\.replace\(")
    write_apis = [pat for pat in write_patterns if re.search(pat, lib_src)]
    open_modes = re.findall(r"open\([^)]*?,\s*[\"']([rwaxb+]+)[\"']", lib_src)
    checks.append(("结构证据：身份层源码里没有任何文件写 API（只 read_text / open(rb)）",
                   not write_apis and all("w" not in m and "a" not in m and "x" not in m
                                         for m in open_modes)))
    if write_apis:
        print(f"  写 API 命中: {write_apis}", flush=True)
    touched = sorted(k for k in before if before[k] != after.get(k))
    gone = sorted(k for k in before if k not in after)
    if not touched and not gone and len(after) == len(before):
        checks.append((f"实测证据：本次读过的 {len(before)} 份裁定扫描前后 size/mtime 全不变", True))
    else:
        checks.append((f"实测证据：本次读过的 {len(before)} 份裁定扫描前后 size/mtime 全不变"
                       f" —— SKIP：上游在扫描期间被改写（{[Path(x).name for x in touched[:3]]}"
                       f"{('；消失 ' + str(len(gone))) if gone else ''}）⇒ 无法用它证明只读，"
                       f"且本份清单可能不自洽，需重跑", None))
    OUT_INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    OUT_INVENTORY.write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checks.append(("清单落盘到 C 自己的产物路径，并带 invariant 声明",
                   OUT_INVENTORY.exists() and bool(json.loads(
                       OUT_INVENTORY.read_text(encoding="utf-8")).get("invariant"))))
    print(f"  实扫 {inv['n_files_scanned']} 文件 / {inv['n_verdicts']} 条裁定："
          f"builds={builds}", flush=True)
    with open(OUT_BUILD_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"observed_at": inv["generated_at"],
                             "gate_current": inv["gate_current"],
                             "usable_for_distribution": inv["usable_for_distribution"],
                             "n_verdicts": inv["n_verdicts"],
                             "by": "scripts/c_selfcheck_verdict_identity.py"},
                            ensure_ascii=False) + "\n")
    print(f"  当前门禁构建={inv['gate_current']['gate_version']}/"
          f"{inv['gate_current']['gate_build']}（观测流水 -> {OUT_BUILD_LOG.name}）", flush=True)
    print(f"  usable_for={inv['usable_for_distribution']} "
          f"measurement_valid={inv['measurement_valid_distribution']} "
          f"superseded={inv['n_superseded']} conflicting_arms={len(inv['arms_with_conflicting_builds'])}",
          flush=True)


# ---------------------------------------------------------------------------
# 3. 不重算判据 + 内容身份
# ---------------------------------------------------------------------------
def case_no_recomputation_and_content_identity(checks: list) -> None:
    inv = json.loads(OUT_INVENTORY.read_text(encoding="utf-8"))
    mismatch, sha_bad, eval_bad, n = [], [], [], 0
    # 一份裁定文件可能含**多臂**（如 gate_controlled_success_minmax_arms.json 是 5 臂 list），
    # 所以按文件分组、按出现顺序对齐记录与行；一律拿 rows[0] 比会把多臂文件误判成"数字不符"。
    by_source: dict[str, list[dict]] = {}
    for r in inv["records"]:
        by_source.setdefault(r["source_path"], []).append(r)
    for source, recs in by_source.items():
        payload = json.loads((ROOT / source).read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else [payload]
        if len(rows) != len(recs):
            mismatch.append(f"{source}: 行数 {len(rows)} != 记录数 {len(recs)}")
            continue
        for r, row in zip(recs, rows):
            n += 1
            accounts = row.get("accounts") or {}
            indep = accounts.get("policy_independent") or {}
            if any(r["buckets"][k] != indep.get(k) for k in vi.BUCKETS) \
                    or r["accounts"] != {name: accounts.get(name) for name in vi.ACCOUNTS} \
                    or r["measurement_valid"] != row.get("measurement_valid") \
                    or r["gate_pass"] != row.get("gate_pass") \
                    or r["gate_reason"] != row.get("gate_reason") \
                    or r["gate_build"] != row.get("gate_build") \
                    or r["gate_spec_sha256"] != row.get("gate_spec_sha256"):
                mismatch.append(f"{source}:{r['arm']}")
    for r in inv["records"]:
        src = ROOT / r["source_path"]
        if r["source_sha256"] != vi.content_sha256(src):
            sha_bad.append(r["source_path"])
        if r["eval_sha256"] and r["eval_file"] and (ROOT / r["eval_file"]).exists() \
                and r["eval_sha256"] != vi.content_sha256(ROOT / r["eval_file"]):
            eval_bad.append(r["source_path"])
    checks.append((f"不重算判据：{n} 条记录的数字与上游落盘值逐位相同", not mismatch))
    checks.append(("多臂裁定文件被逐臂拆开核对（对齐不是只比第一臂）",
                   any(len(v) > 1 for v in by_source.values())))
    if mismatch:
        print(f"  mismatch 样本: {mismatch[:5]}", flush=True)
    checks.append(("内容身份：source_sha256 与实算一致（runs/ 未纳管 git，产物只能靠内容指纹）", not sha_bad))
    checks.append(("被判决的评测文件也带 sha256，且与实算一致", not eval_bad))
    checks.append(("确实核到了评测文件（eval_sha256 非全空，否则上一条是空过）",
                   any(r["eval_sha256"] for r in inv["records"])))


# ---------------------------------------------------------------------------
# 4. 取代关系（superseded_by）
# ---------------------------------------------------------------------------
def case_supersession(checks: list) -> None:
    """取代关系用**合成夹具**验（非空过），真目录只做结构核对。

    为什么不在真目录上断言「必须有取代关系」：当前构建是 B 的门禁脚本内容指纹，B 一升级
    （本轮就实测到 v1.2.1 → v1.3），全部留档裁定立刻变旧、而重判产物还没生成，
    此时 `superseded` 合法地为空。把「>0」写成断言就等于埋一颗随上游升级爆炸的定时炸弹。
    """
    cur = vi.current_gate_identity()
    d = OUT_ROOT / "supersede"
    d.mkdir(parents=True, exist_ok=True)
    old_v = _write_verdict(d / "arm_old_build.json", gate_build="deadbeef0000", arm="arm_same")
    new_v = _write_verdict(d / "arm_current_build.json", gate_build=cur["gate_build"], arm="arm_same")
    other = _write_verdict(d / "arm_other_old.json", gate_build="deadbeef0000", arm="arm_other")
    syn = vi.inventory([old_v, new_v, other], current=cur, root=d)
    sup = syn["superseded"]
    checks.append(("合成夹具：同一臂的旧构建裁定被当前构建裁定取代（关系非空过）", len(sup) == 1))
    checks.append(("superseded_by 指向同臂的当前构建那份，且不是自己",
                   sup and sup[0]["superseded_path"] == str(old_v.relative_to(ROOT))
                   and sup[0]["superseded_by"] == str(new_v.relative_to(ROOT))))
    by_arm = {(r["source_path"], r["arm"]): r for r in syn["records"]}
    old_rec = by_arm[(str(old_v.relative_to(ROOT)), "eval_arm_same")]
    new_rec = by_arm[(str(new_v.relative_to(ROOT)), "eval_arm_same")]
    other_rec = by_arm[(str(other.relative_to(ROOT)), "eval_arm_other")]
    checks.append(("被取代者标 superseded=True 且降级为 stale_build_evidence",
                   old_rec["superseded"] and old_rec["superseded_by"] == new_rec["source_path"]
                   and old_rec["usable_for"] == vi.USABLE_STALE_BUILD))
    checks.append(("取代者自己不被标 superseded（当前构建不会被自己取代）",
                   not new_rec["superseded"] and new_rec["superseded_by"] is None))
    checks.append(("没有当前构建版本的臂：旧裁定只标 stale，superseded_by 保持 None（= 尚未重判）",
                   not other_rec["superseded"] and other_rec["superseded_by"] is None
                   and other_rec["usable_for"] == vi.USABLE_STALE_BUILD))

    inv = json.loads(OUT_INVENTORY.read_text(encoding="utf-8"))
    real_sup = inv["superseded"]
    paths = {(r["source_path"], r["arm"]): r for r in inv["records"]}
    cur_build = str(inv["gate_current"]["gate_build"])
    ok_target = ok_build = ok_flag = True
    for sp in real_sup:
        old_r = paths.get((sp["superseded_path"], sp["arm"]))
        new_r = next((r for r in inv["records"]
                      if r["source_path"] == sp["superseded_by"] and r["arm"] == sp["arm"]), None)
        if old_r is None or new_r is None:
            ok_target = False
            continue
        if str(new_r["gate_build"]) != cur_build or new_r["source_path"] == old_r["source_path"]:
            ok_target = False
        if str(old_r["gate_build"]) == cur_build:
            ok_build = False
        if not old_r["superseded"] or old_r["superseded_by"] != new_r["source_path"]:
            ok_flag = False
        if old_r["usable_for"] == vi.USABLE_PHYSICAL_FACT:
            ok_flag = False
    checks.append((f"真目录：{len(real_sup)} 条取代关系全部结构自洽（目标同臂/当前构建/非自身）",
                   ok_target))
    checks.append(("真目录：被取代者一定出自旧构建", ok_build))
    checks.append(("真目录：被取代者标 superseded=True 且不当物理事实", ok_flag))
    n_facts = inv["usable_for_distribution"].get(vi.USABLE_PHYSICAL_FACT, 0)
    print(f"  真目录取代关系 {len(real_sup)} 条；当前构建 {cur_build} 下 physical_fact={n_facts}"
          + ("（B 刚升级判据、重判产物尚未生成，属预期）" if n_facts == 0 else ""), flush=True)


# ---------------------------------------------------------------------------
# 5. 合成裁定：四档分级各自可达
# ---------------------------------------------------------------------------
def _synthetic_dir() -> Path:
    d = OUT_ROOT / "synthetic"
    cur = vi.current_gate_identity()["gate_build"]
    _write_verdict(d / "ok_current.json", gate_build=cur, arm="arm_ok")
    _write_verdict(d / "no_build.json", gate_build=None, arm="arm_nobuild")
    _write_verdict(d / "invalid.json", gate_build=cur, measurement_valid=False, arm="arm_invalid")
    _write_verdict(d / "suspect.json", gate_build=cur, suspect=True, arm="arm_suspect")
    _write_verdict(d / "stale.json", gate_build="deadbeef0000", arm="arm_stale")
    _write_verdict(d / "undeclared.json", gate_build=cur, arm="arm_undeclared")
    _strip_key(d / "undeclared.json", "measurement_valid")
    _write_aggregate(d / "aggregate.json", gate_build=cur, measurement_valid=None)
    # 第二份聚合报告**带** measurement_valid=True：这样「不辨聚合报告」的变异会把它抬成
    # physical_fact —— 凭空多出一个不存在的臂。真实的敏感度报告没有该字段，
    # 只靠那一份看不出危害（它只会掉到 unidentified_build）。
    _write_aggregate(d / "aggregate_valid.json", gate_build=cur, measurement_valid=True)
    return d


def _write_aggregate(path: Path, *, gate_build, measurement_valid) -> Path:
    """造一份「关于裁定的聚合报告」：有 arms/thresholds，没有 accounts。"""
    row = {"gate_version": "vSYN", "gate_build": gate_build, "gate_spec_sha256": "synthetic",
           "thresholds": {"controlled_success_min": 5}, "arms": [{"arm": "a1"}, {"arm": "a2"}]}
    if measurement_valid is not None:
        row["measurement_valid"] = measurement_valid
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([row], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def _strip_key(path: Path, key: str) -> None:
    """把某个键**整个删掉**（不是设成 None）：字段缺失与字段为假值是两种不同事实。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload:
        row.pop(key, None)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def case_synthetic_downgrades(checks: list) -> None:
    d = _synthetic_dir()
    got = {p.stem: vi.parse_verdict(p)[0].usable_for for p in sorted(d.glob("*.json"))}
    checks.append(("当前构建 + 测量有效 ⇒ physical_fact",
                   got["ok_current"] == vi.USABLE_PHYSICAL_FACT))
    checks.append(("缺 gate_build ⇒ unidentified_build（不当当前构建用）",
                   got["no_build"] == vi.USABLE_UNIDENTIFIED))
    checks.append(("当前构建但 measurement_valid=False ⇒ invalid_measurement（构建匹配不足以放行）",
                   got["invalid"] == vi.USABLE_INVALID_MEASUREMENT))
    checks.append(("怀疑把截断标成失败 ⇒ invalid_measurement",
                   got["suspect"] == vi.USABLE_INVALID_MEASUREMENT))
    checks.append(("旧构建 ⇒ stale_build_evidence", got["stale"] == vi.USABLE_STALE_BUILD))
    checks.append(("measurement_valid 字段被删 ⇒ unidentified_build（不猜成 False，也不放行）",
                   got["undeclared"] == vi.USABLE_UNIDENTIFIED))
    checks.append(("聚合报告（有 arms/thresholds、无 accounts）⇒ not_a_verdict",
                   got["aggregate"] == vi.USABLE_NOT_A_VERDICT))
    checks.append(("聚合报告即使自带 measurement_valid=True 也不当一次测量（不凭空造臂）",
                   got["aggregate_valid"] == vi.USABLE_NOT_A_VERDICT))
    checks.append(("八份合成裁定落在五个不同档（分级不是常量）", len(set(got.values())) == 5))


# ---------------------------------------------------------------------------
# 6. 变异自检：把 classify 改成「一律 physical_fact」，上面的断言必须转红
# ---------------------------------------------------------------------------
def case_mutation_classify_always_fact(checks: list) -> None:
    d = OUT_ROOT / "synthetic"
    if not d.is_dir():
        d = _synthetic_dir()
    real = vi.classify
    baseline = {p.stem: vi.parse_verdict(p)[0].usable_for for p in sorted(d.glob("*.json"))}
    try:
        vi.classify = lambda *a, **k: (vi.USABLE_PHYSICAL_FACT, ())   # 最省事的一种坏实现
        mutated = {p.stem: vi.parse_verdict(p)[0].usable_for for p in sorted(d.glob("*.json"))}
    finally:
        vi.classify = real
    restored = {p.stem: vi.parse_verdict(p)[0].usable_for for p in sorted(d.glob("*.json"))}
    checks.append(("变异确实改变了被测量（否则这条变异测试是空转）", mutated != baseline))
    checks.append(("变异下全部合成裁定塌成 physical_fact ⇒ 「不越级」断言会转红",
                   set(mutated.values()) == {vi.USABLE_PHYSICAL_FACT}))
    checks.append(("变异下连聚合报告都成了「一次测量」（凭空造出不存在的臂）",
                   mutated["aggregate"] == vi.USABLE_PHYSICAL_FACT))
    checks.append(("变异下 INVALID / 缺身份 / 旧构建全部越级（正是要拦的事故）",
                   mutated["invalid"] == vi.USABLE_PHYSICAL_FACT
                   and mutated["no_build"] == vi.USABLE_PHYSICAL_FACT
                   and mutated["stale"] == vi.USABLE_PHYSICAL_FACT))
    checks.append(("还原后分级恢复原状（monkey-patch 没有泄漏）", restored == baseline))

    # 第二种坏实现：只看 measurement_valid，忽略 gate_build（「测量有效就当事实」）
    try:
        vi.classify = lambda gb, mv, sp, cb, **kw: (
            (vi.USABLE_PHYSICAL_FACT, ()) if mv is True else (vi.USABLE_INVALID_MEASUREMENT, ()))
        mutated2 = {p.stem: vi.parse_verdict(p)[0].usable_for for p in sorted(d.glob("*.json"))}
    finally:
        vi.classify = real
    checks.append(("变异2（忽略 gate_build）会让旧构建裁定越级 ⇒ 构建核对非冗余",
                   mutated2["stale"] == vi.USABLE_PHYSICAL_FACT
                   and mutated2["ok_current"] == vi.USABLE_PHYSICAL_FACT))

    # 第三种坏实现：不区分聚合报告与逐臂裁定（is_arm_verdict 恒 True）
    real_is_arm = vi.is_arm_verdict
    try:
        vi.is_arm_verdict = lambda row: True
        mutated3 = {p.stem: vi.parse_verdict(p)[0].usable_for for p in sorted(d.glob("*.json"))}
    finally:
        vi.is_arm_verdict = real_is_arm
    checks.append(("变异3（不辨聚合报告）会把带 valid 的聚合报告抬成 physical_fact ⇒ 凭空造臂",
                   mutated3["aggregate_valid"] == vi.USABLE_PHYSICAL_FACT))
    checks.append(("变异3 下 aggregate 也丢了 not_a_verdict 身份 ⇒ 判别式非冗余",
                   mutated3["aggregate"] != vi.USABLE_NOT_A_VERDICT))
    checks.append(("变异3 确实改变了被测量（还原后 aggregate 回到 not_a_verdict）",
                   mutated3 != baseline))


# ---------------------------------------------------------------------------
# 7. 身份对内容敏感；分级只读字段不读文件名
# ---------------------------------------------------------------------------
def case_identity_is_content_addressed(checks: list) -> None:
    d = OUT_ROOT / "content"
    d.mkdir(parents=True, exist_ok=True)
    src = OUT_ROOT / "synthetic" / "stale.json"
    if not src.exists():
        _synthetic_dir()
    copy = d / "stale_copy.json"
    shutil.copyfile(src, copy)
    base = vi.parse_verdict(copy)[0]
    # 改一个与判据无关的字节（controller 名字）：身份必须变，分级不许变
    payload = json.loads(copy.read_text(encoding="utf-8"))
    payload[0]["controller"] = "synthetic_touched"
    copy.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    touched = vi.parse_verdict(copy)[0]
    checks.append(("改一个字节 ⇒ source_sha256 变（内容寻址，不是路径寻址）",
                   touched.source_sha256 != base.source_sha256))
    checks.append(("无关字段变动 ⇒ 分级不变（身份与有效性判定分离）",
                   touched.usable_for == base.usable_for == vi.USABLE_STALE_BUILD))
    # 把 gate_build 改成当前构建：分级必须跟着翻，证明它读的是文件内容而不是文件名
    payload[0]["gate_build"] = vi.current_gate_identity()["gate_build"]
    promoted = d / "stale_promoted.json"
    promoted.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    after = vi.parse_verdict(promoted)[0]
    checks.append(("把 gate_build 改成当前构建 ⇒ stale 翻成 physical_fact（分级读内容不读文件名）",
                   after.usable_for == vi.USABLE_PHYSICAL_FACT and after.is_current_build))


# ---------------------------------------------------------------------------
# 8. 写入边界
# ---------------------------------------------------------------------------
def case_write_scope(checks: list) -> None:
    written = {str(p.relative_to(ROOT)) for p in OUT_ROOT.rglob("*") if p.is_file()}
    checks.append(("合成裁定只写在 C 自己的临时目录里", bool(written) and all(
        p.startswith("runs/infra/c_verdict_selfcheck/") for p in written)))
    checks.append(("产物只有两份：自检结果 + 全量清单（都在 runs/infra/c_*）",
                   OUT_JSON.name.startswith("c_") and OUT_INVENTORY.name.startswith("c_")))
    registry_files = {p.name for p in (ROOT / "registry").glob("*.py")}
    checks.append(("没有往 registry/ 写发布物（本轮只做身份层，不做晋级）",
                   "verdict_identity.py" in registry_files
                   and not (ROOT / "registry" / "c_selfcheck_skill").exists()))



# ---------------------------------------------------------------------------
# 9. 三键与 A 的权威表：C 只绑定，不自己推导 validity
# ---------------------------------------------------------------------------
def case_upstream_authority_join(checks: list) -> None:
    """监管备忘 增补六：裁定身份必须含 `field_class` / `validity_class` /
    `blowup_threshold_source` 三键，且 `validity_class` 只能来自 A 的唯一权威表。"""
    inv = json.loads(OUT_INVENTORY.read_text(encoding="utf-8"))
    recs = inv["records"]
    summary = json.loads((UPSTREAM_DIR / "arms_summary.json").read_text(encoding="utf-8"))
    rows = {r["arm"]: r for r in summary["arms"]}
    checks.append(("清单带权威表身份（sha256 + 行数），validity 可回溯到具体一份表",
                   bool(inv["arm_summary"].get("sha256")) and inv["arm_summary"]["n_rows"] > 0))
    checks.append(("三键齐备：每条记录都有 field_class / validity_class / blowup_threshold_source 字段",
                   all({"field_class", "validity_class", "blowup_threshold_source"} <= set(r)
                       for r in recs)))
    checks.append(("validity_class 取值只在 A 定义的三值内，或如实为 None（未声明）",
                   all(r["validity_class"] in vi.VALIDITY_CLASSES or r["validity_class"] is None
                       for r in recs)))
    joined = [r for r in recs if r["validity_class"] is not None]
    absent = [r for r in recs if r["validity_class"] is None]
    checks.append((f"确实接上了权威表（{len(joined)}/{len(recs)} 条），否则本节是空过", len(joined) > 0))
    checks.append((f"没接上的 {len(absent)} 条一律标 absent_from_arms_summary，不自己推导 validity",
                   all(r["validity_source"] == "absent_from_arms_summary" for r in absent)))
    # 逐条与 A 的行核对：C 的值必须**等于**权威表的值（不是 C 重算的近似值）
    bad = []
    for r in joined:
        arm = r["arm"].replace("official_act_truth20_", "", 1)
        row = rows.get(arm) or rows.get(r["arm"])
        if row is None:
            bad.append(f"{r['arm']}: 权威表里没有")
            continue
        if r["validity_class"] != row.get("validity_class") \
                or r["labels_reportable"] != row.get("labels_reportable") \
                or r["blowup_threshold_source"] != row.get("blowup_threshold_source") \
                or r["upstream_superseded_by"] != row.get("superseded_by"):
            bad.append(r["arm"])
    checks.append(("逐条与 A 权威表相同：validity/labels/阈值来源/upstream superseded_by 全一致",
                   not bad))
    if bad:
        print(f"  不一致样本: {bad[:5]}", flush=True)
    # 裁定 14（DR-D09）：非 strict 不得输出失效模式标签
    # 裁定 14（DR-D09）要用 **A 权威表的** field_class 判：本文件自己的 field_class 属于
    # 这一份（可能是留档的 partial 原件），而 labels_reportable 是权威那一行的结论。
    # 第一版拿本地 field_class 去卡 A 的 labels_reportable，把「原件 partial + 重测 strict」
    # 这种正常情形判成了违规 —— 那恰恰是 A 的 superseded_by 设计要表达的。
    arm_nonstrict = [r for r in recs if r["arm_field_class"] not in (None, "strict")]
    checks.append(("裁定 14：A 权威表 field_class != strict 的行，labels_reportable 一律不为 True",
                   all(r["labels_reportable"] is not True for r in arm_nonstrict)))
    mismatch = [r for r in recs if r["arm_field_class"] is not None and r["field_class"] is not None
                and r["arm_field_class"] != r["field_class"]]
    checks.append((f"本地 field_class 与权威不一致的 {len(mismatch)} 条，一律不是 physical_fact"
                   "（非权威裁定不得冒充权威数字）",
                   all(r["usable_for"] != vi.USABLE_PHYSICAL_FACT for r in mismatch)))
    checks.append(("不一致的条数与清单里的 field_class_mismatch_count 相同（两处口径一致）",
                   len(mismatch) == inv["field_class_mismatch_count"]))
    if mismatch:
        print(f"  field_class 不一致（本地/权威）: "
              f"{[(r['arm'][:40], r['field_class'], r['arm_field_class']) for r in mismatch[:3]]}",
              flush=True)
    checks.append(("裁定 14 非空过：清单里确实存在 labels_reportable=False 的记录",
                   any(r["labels_reportable"] is False for r in recs)))
    checks.append(("C 不改上游数字：labels_reportable=False 的记录里，五档 bucket 仍原样保留",
                   all(isinstance(r["buckets"].get("flick"), int) or r["buckets"].get("flick") is None
                       for r in recs if r["labels_reportable"] is False)))
    # 两种 superseded 语义不许混：C 的是「判据构建取代」，A 的是「评测产物取代」
    checks.append(("C 的 superseded_by（判据构建）与 A 的 upstream_superseded_by（评测产物）分列两键",
                   all(("superseded_by" in r and "upstream_superseded_by" in r) for r in recs)
                   and any(r["upstream_superseded_by"] for r in recs)))

    # 变异：把 join 弄坏，上面两条必须转红
    real_lookup = vi._lookup_arm
    try:
        vi._lookup_arm = lambda *a, **k: None
        no_join = vi.parse_verdict(UPSTREAM_DIR / "regate_current"
                                   / sorted(x.name for x in (UPSTREAM_DIR / "regate_current")
                                            .glob("gate_*.json"))[0],
                                   arm_index=vi.load_arm_index(UPSTREAM_DIR))
        vi._lookup_arm = lambda *a, **k: {"validity_class": "valid", "labels_reportable": True,
                                         "blowup_threshold_source": None, "superseded_by": None}
        fake_join = vi.parse_verdict(UPSTREAM_DIR / "regate_current"
                                     / sorted(x.name for x in (UPSTREAM_DIR / "regate_current")
                                              .glob("gate_*.json"))[0],
                                     arm_index=vi.load_arm_index(UPSTREAM_DIR))
    finally:
        vi._lookup_arm = real_lookup
    checks.append(("变异4（join 恒失败）会让 validity 全部变 absent ⇒ join 断言非恒真",
                   all(r.validity_class is None and r.validity_source == "absent_from_arms_summary"
                       for r in no_join)))
    checks.append(("变异5（join 恒返回 valid）会与权威表不符 ⇒ 「逐条相同」断言非恒真",
                   any(r.validity_class == "valid" for r in fake_join)
                   and any((rows.get(r.arm.replace("official_act_truth20_", "", 1)) or {})
                           .get("blowup_threshold_source") is not None for r in fake_join)))


# ---------------------------------------------------------------------------
# 10. n 必须等于该臂的 n_action_steps（监管备忘 增补五 §9-C④）
# ---------------------------------------------------------------------------
def case_n_matches_arm_guard(checks: list) -> None:
    """真实帧路径的槽长 n 不许沿用规格算例的 6，也不许与臂的 `n_action_steps` 不一致。"""
    k2 = sorted(UPSTREAM_DIR.glob("official_act_truth20_*k2*.json"))
    k4 = sorted(p for p in UPSTREAM_DIR.glob("official_act_truth20_*.json") if "k2" not in p.name)
    checks.append(("真目录里能同时找到 K=2 与 K=4 两族臂（否则本守卫是空过）",
                   bool(k2) and bool(k4)))
    t2 = vi.read_arm_timing(k2[0])
    t4 = vi.read_arm_timing(k4[0])
    checks.append((f"K=2 族 n_action_steps={t2['n_action_steps']}、K=4 族={t4['n_action_steps']}（实测读取）",
                   int(t2["n_action_steps"]) == 2 and int(t4["n_action_steps"]) == 4))
    checks.append(("n 与该臂一致 ⇒ 放行（K=2 用 2、K=4 用 4）",
                   vi.assert_n_matches_arm(2, t2) == 2 and vi.assert_n_matches_arm(4, t4) == 4))
    for bad_n, timing, label in ((4, t2, "K=2 臂配 n=4"), (6, t2, "K=2 臂配规格算例 n=6"),
                                 (6, t4, "K=4 臂配规格算例 n=6"), (2, t4, "K=4 臂配 n=2")):
        try:
            vi.assert_n_matches_arm(bad_n, timing, arm=label)
            raised = "NO-RAISE"
        except ValueError as exc:
            raised = f"ValueError: {exc}"[:120]
        checks.append((f"{label} ⇒ 拒绝（不静默换算、不沿用规格 n）", raised.startswith("ValueError")))
    try:
        vi.assert_n_matches_arm(4, {"n_action_steps": None})
        missing = "NO-RAISE"
    except vi.VerdictIdentityError as exc:
        missing = f"VerdictIdentityError: {exc}"[:120]
    checks.append(("臂缺 n_action_steps ⇒ 直接拒（不许拿假设的 n 去解读真实臂）",
                   missing.startswith("VerdictIdentityError")))
    checks.append(("C 的真帧 smoke 用 n=4：与 K=4 族同尺度，且产物已标为假设值待实测升格",
                   int(t4["n_action_steps"]) == 4))


# ---------------------------------------------------------------------------
# 11. 增补六 §8-C3 / 裁定 17.7：「裁定已核可、实现待落地」自成一档
# ---------------------------------------------------------------------------
# 真值表逐格写死。每一格都对应监管备忘里一句明文要求，注释里标了出处，
# 免得后人把「哪一格该落哪一档」当成 C 自己的口味来改。
#   (文件名, gate_build, measurement_valid, suspect, input_contract.status,
#    权威表 validity_class, 期望档, 出处)
# 当前构建一律**运行时**取（B 正在升门禁：本轮实测 b9379fdb1089 → 9e57327af208 → f19f61341cbe），
# 所以规格里写 "CUR" 占位，由 _pending_specs() 换成实测值 —— 钉死指纹当场就过期。
_PENDING_SPECS_TAIL = (
    # 目标格：§8-C3 点名的那一个（真目录里的 `k2 seed0` 就是这个形态）
    ("authority_exo_gate_violated", "CUR", False, False, "violated",
     vi.AUTHORITY_EXONERATED, vi.USABLE_PENDING_IMPL, "增补六 §8-C3 / 裁定 17.7"),
    # 门禁已承载免罪（v1.5 落地后的形态）⇒ 不再需要过渡档，走正常分级
    ("authority_exo_gate_exonerated", "CUR", True, False, vi.GATE_EXONERATED,
     vi.AUTHORITY_EXONERATED, vi.USABLE_PHYSICAL_FACT, "裁定 26：实现承载后过渡档自动清空"),
    # 权威表不是免罪 ⇒ 门禁的 violated 照原判（C 不替 A 造免罪）
    ("authority_valid_gate_violated", "CUR", False, False, "violated",
     "valid", vi.USABLE_INVALID_MEASUREMENT, "§8-C3 只认「权威表已会签」这一个前提"),
    # 终局语义怀疑优先：裁定 10 的探针免罪覆盖不到「把截断标成失败」
    ("authority_exo_suspect", "CUR", False, True, "violated",
     vi.AUTHORITY_EXONERATED, vi.USABLE_INVALID_MEASUREMENT, "裁定 10 免罪范围（输入契约 / blown）"),
    # 身份缺失优先：连出自哪一版判据都说不清，无从谈「相对哪一版实现待落地」
    ("authority_exo_no_build", None, False, False, "violated",
     vi.AUTHORITY_EXONERATED, vi.USABLE_UNIDENTIFIED, "分级优先级：身份先于有效性"),
    # 旧构建 + 已会签 ⇒ 仍是过渡档，不是 stale_build_evidence
    ("authority_exo_stale_build", "deadbeef0000", False, False, "violated",
     vi.AUTHORITY_EXONERATED, vi.USABLE_PENDING_IMPL, "§8-C3：事实基础已核可，与构建新旧无关"),
)


def _pending_specs() -> tuple:
    """把 "CUR" 换成**运行时**取到的当前构建（不钉死指纹：B 一升门禁就过期）。"""
    cur = vi.current_gate_identity()["gate_build"]
    return tuple((name, cur if gb == "CUR" else gb, mv, sp, ic, vc, exp, src)
                 for name, gb, mv, sp, ic, vc, exp, src in _PENDING_SPECS_TAIL)


def _pending_arm_index(specs) -> dict:
    """合成的「权威表索引」：形状与 `load_arm_index()` 的产物相同，值由 specs 指定。

    只用于分级真值表（数字无物理意义）。真目录那一半的断言在
    `case_pending_impl_real_inventory` 里，读的是 A 的**真**权威表。
    """
    index = {}
    for name, _gb, _mv, _sp, _ic, vc, _exp, _src in specs:
        index[f"eval_{name}.json"] = {
            "arm": name, "file": f"eval_{name}.json", "validity_class": vc,
            "validity_reason": "synthetic_for_grade_truth_table", "labels_reportable": None,
            "blowup_threshold_source": None, "superseded_by": None, "field_class": "strict"}
    return {"available": True, "path": "synthetic/arms_summary.json", "sha256": "synthetic" * 8,
            "sha12": "synthetic", "index": index, "n_rows": len(index)}


def _pending_impl_dir() -> tuple[Path, dict, dict]:
    """造出这一档的真值表目录，返回 (目录, 合成权威表索引, {name: VerdictIdentity})。"""
    d = OUT_ROOT / "pending_impl"
    specs = _pending_specs()
    arm_index = _pending_arm_index(specs)
    got: dict[str, Any] = {}
    for name, gb, mv, sp, ic, _vc, _exp, _src in specs:
        path = _write_verdict(d / f"{name}.json", gate_build=gb, measurement_valid=mv,
                              suspect=sp, ic_status=ic, arm=name)
        got[name] = vi.parse_verdict(path, arm_index=arm_index)[0]
    # 两格不在 specs 里：它们需要**改结构**（删字段 / 换成聚合报告），不是改值
    undeclared = _write_verdict(d / "authority_exo_undeclared.json",
                                gate_build=vi.current_gate_identity()["gate_build"],
                                measurement_valid=False, ic_status="violated",
                                arm="authority_exo_undeclared")
    _strip_key(undeclared, "measurement_valid")
    arm_index["index"]["eval_authority_exo_undeclared.json"] = dict(
        arm_index["index"]["eval_authority_exo_gate_violated.json"],
        arm="authority_exo_undeclared", file="eval_authority_exo_undeclared.json")
    got["authority_exo_undeclared"] = vi.parse_verdict(undeclared, arm_index=arm_index)[0]

    aggregate = _write_aggregate(d / "authority_exo_aggregate.json",
                                 gate_build=vi.current_gate_identity()["gate_build"],
                                 measurement_valid=True)
    arm_index["index"]["authority_exo_aggregate"] = dict(
        arm_index["index"]["eval_authority_exo_gate_violated.json"],
        arm="authority_exo_aggregate", file="authority_exo_aggregate")
    got["authority_exo_aggregate"] = vi.parse_verdict(aggregate, arm_index=arm_index)[0]
    return d, arm_index, got


def case_pending_impl_grade(checks: list) -> None:
    """分级真值表：这一档的边界逐格钉死（合成裁定 + 合成权威表索引）。"""
    d, arm_index, got = _pending_impl_dir()
    specs = {name: (exp, src) for name, _gb, _mv, _sp, _ic, _vc, exp, src in _pending_specs()}
    for name, rec in sorted(got.items()):
        if name in specs:
            exp, src = specs[name]
            checks.append((f"真值表 {name} ⇒ {exp}（{src}）", rec.usable_for == exp))
        elif name == "authority_exo_undeclared":
            checks.append(("真值表 authority_exo_undeclared ⇒ unidentified_build"
                          "（有效性未声明时不替上游下结论，免罪也不接）",
                           rec.usable_for == vi.USABLE_UNIDENTIFIED))
        else:
            checks.append(("真值表 authority_exo_aggregate ⇒ not_a_verdict"
                          "（聚合报告不是一次测量，免罪抬不动它）",
                           rec.usable_for == vi.USABLE_NOT_A_VERDICT))
    checks.append((f"真值表 {len(got)} 格落在 {len(set(r.usable_for for r in got.values()))} 个不同档"
                   "（这一档不是常量、也没有吞掉别的档）",
                   len(set(r.usable_for for r in got.values())) >= 4))
    # 标签纪律（裁定 17.7）：只有这一档带过渡期标签，且理由里两层取值都要出现
    pend = [r for r in got.values() if r.usable_for == vi.USABLE_PENDING_IMPL]
    checks.append((f"命中这一档的 {len(pend)} 格全部带过渡期标签 {vi.PENDING_IMPL_LABEL}",
                   bool(pend) and all(r.pending_impl_label == vi.PENDING_IMPL_LABEL for r in pend)))
    checks.append(("其余档一律不带该标签（标签不是装饰，它与分级一一对应）",
                   all(r.pending_impl_label is None for r in got.values()
                       if r.usable_for != vi.USABLE_PENDING_IMPL)))
    checks.append(("理由里同时写出两层取值（权威表 validity_class 与门禁 input_contract.status）"
                   "⇒ 事后可追，不是「C 说它待落地」",
                   all(any(vi.AUTHORITY_EXONERATED in x for x in r.reasons)
                       and any("input_contract.status" in x for x in r.reasons) for r in pend)))
    checks.append((f"标签用 D 的原字 {vi.PENDING_IMPL_LABEL}，且已被 USABLE_LEVELS 收编",
                   vi.PENDING_IMPL_LABEL == "PENDING_IMPL_probe_exonerated"
                   and vi.USABLE_PENDING_IMPL in vi.USABLE_LEVELS
                   and len(vi.USABLE_LEVELS) == len(set(vi.USABLE_LEVELS))))

    # --- 纯函数真值表：同一批格子直接问 classify（不经文件），两条路径必须同答 ---
    cur = vi.current_gate_identity()["gate_build"]
    cells = (
        ("正向：权威免罪 + 门禁 violated", dict(
            gate_build=cur, measurement_valid=False, suspect_truncation=False, current_build=cur,
            validity_class=vi.AUTHORITY_EXONERATED, input_contract_status="violated"),
         vi.USABLE_PENDING_IMPL),
        ("门禁已承载免罪 ⇒ 让位给正常分级", dict(
            gate_build=cur, measurement_valid=True, suspect_truncation=False, current_build=cur,
            validity_class=vi.AUTHORITY_EXONERATED, input_contract_status=vi.GATE_EXONERATED),
         vi.USABLE_PHYSICAL_FACT),
        ("权威表是 invalid ⇒ 不接免罪", dict(
            gate_build=cur, measurement_valid=False, suspect_truncation=False, current_build=cur,
            validity_class="invalid", input_contract_status="violated"),
         vi.USABLE_INVALID_MEASUREMENT),
        ("权威表未声明（None）⇒ 不接免罪", dict(
            gate_build=cur, measurement_valid=False, suspect_truncation=False, current_build=cur,
            validity_class=None, input_contract_status="violated"),
         vi.USABLE_INVALID_MEASUREMENT),
        ("终局语义怀疑 ⇒ 免罪不得盖过", dict(
            gate_build=cur, measurement_valid=False, suspect_truncation=True, current_build=cur,
            validity_class=vi.AUTHORITY_EXONERATED, input_contract_status="violated"),
         vi.USABLE_INVALID_MEASUREMENT),
        ("gate_build 缺失 ⇒ 身份先于免罪", dict(
            gate_build=None, measurement_valid=False, suspect_truncation=False, current_build=cur,
            validity_class=vi.AUTHORITY_EXONERATED, input_contract_status="violated"),
         vi.USABLE_UNIDENTIFIED),
        ("聚合报告 ⇒ 不是裁定，先于免罪", dict(
            gate_build=cur, measurement_valid=True, suspect_truncation=False, current_build=cur,
            arm_verdict=False, validity_class=vi.AUTHORITY_EXONERATED,
            input_contract_status="violated"),
         vi.USABLE_NOT_A_VERDICT),
    )
    for label, kwargs, exp in cells:
        got_level = vi.classify(kwargs.pop("gate_build"), kwargs.pop("measurement_valid"),
                                kwargs.pop("suspect_truncation"), kwargs.pop("current_build"),
                                **kwargs)[0]
        checks.append((f"classify 纯函数：{label} ⇒ {exp}", got_level == exp))
    checks.append(("classify 的两个新参有缺省值（旧调用点不传也能跑，向后兼容）",
                   vi.classify(cur, True, False, cur)[0] == vi.USABLE_PHYSICAL_FACT))
    checks.append(("判据是独立函数（可被单测/被引用），不是埋在 classify 里的字面量",
                   vi.is_pending_impl_exoneration(vi.AUTHORITY_EXONERATED, "violated") is True
                   and vi.is_pending_impl_exoneration(vi.AUTHORITY_EXONERATED,
                                                      vi.GATE_EXONERATED) is False
                   and vi.is_pending_impl_exoneration("valid", "violated") is False))


def _classify_without_pending_branch(gate_build, measurement_valid, suspect_truncation,
                                     current_build, *, validity_declared=True,
                                     arm_verdict=True, **_ignored):
    """变异体：把 增补六 §8-C3 那一档**整个拿掉**，退回 9/28 的五档实现。"""
    if not arm_verdict:
        return vi.USABLE_NOT_A_VERDICT, ("聚合报告",)
    if gate_build in (None, "", "<unknown>"):
        return vi.USABLE_UNIDENTIFIED, ("gate_build 缺失",)
    if not validity_declared:
        return vi.USABLE_UNIDENTIFIED, ("有效性未声明",)
    reasons = []
    if measurement_valid is not True:
        reasons.append(f"measurement_valid={measurement_valid!r}")
    if suspect_truncation is True:
        reasons.append("terminal_semantics 怀疑截断当失败")
    if reasons:
        return vi.USABLE_INVALID_MEASUREMENT, tuple(reasons)
    if str(gate_build) != str(current_build):
        return vi.USABLE_STALE_BUILD, ("旧构建",)
    return vi.USABLE_PHYSICAL_FACT, ()


def case_pending_impl_real_inventory(checks: list) -> None:
    """真实清单上的这一档 + 裁定 31.4 的改判：可独立复算、改判不动可用性、方向限制有牙。"""
    inv = json.loads(OUT_INVENTORY.read_text(encoding="utf-8"))
    recs = inv["records"]
    cur = inv["gate_current"]["gate_build"]

    def _record_level_shape(r: dict) -> bool:
        """记录级形状（独立手写，不调 `vi.is_pending_impl_exoneration`）：第二条代码路径。"""
        return (r["arm_verdict"] and r["gate_build"] not in (None, "")
                and r["measurement_validity_declared"]
                and r["suspect_truncation_as_failure"] is not True
                and str(r["validity_class"]) == vi.AUTHORITY_EXONERATED
                and str(r["input_contract_status"]) != vi.GATE_EXONERATED)

    # 裁定 31.4 的收窄是**跨记录**条件，这里也独立手写一遍承载集（不调 vi.regrade_pending_impl）。
    carried_arms = {r["arm"] for r in recs
                    if str(r["gate_build"]) == str(cur)
                    and str(r["input_contract_status"]) == vi.GATE_EXONERATED}
    shape = [r for r in recs if _record_level_shape(r)]
    expected_pending = {r["source_path"] for r in shape if r["arm"] not in carried_arms}
    expected_regraded = {r["source_path"] for r in shape if r["arm"] in carried_arms}
    actual_pending = {r["source_path"] for r in recs if r["usable_for"] == vi.USABLE_PENDING_IMPL}
    regraded = [r for r in recs if r["regraded_from"] == vi.USABLE_PENDING_IMPL]
    actual_regraded = {r["source_path"] for r in regraded}

    checks.append((f"真清单：记录级形状命中 {len(shape)} 条，收窄后仍留本档 {len(actual_pending)} 条"
                   " —— 与独立手写判据复算逐条相同（分级穷尽且可复算）",
                   expected_pending == actual_pending))
    checks.append((f"裁定 31.4：被改判的 {len(actual_regraded)} 条与独立复算的 {len(expected_regraded)}"
                   " 条逐条相同（跨记录条件既没多改也没漏改）",
                   expected_regraded == actual_regraded))
    checks.append(("裁定 31.4：改判后每条都是 stale_build_evidence + 带 regraded_from + "
                   "provenance_kind 落在封闭集合内",
                   all(r["usable_for"] == vi.USABLE_STALE_BUILD
                       and r["regraded_from"] == vi.USABLE_PENDING_IMPL
                       and r["provenance_kind"] in vi.PROVENANCE_KINDS for r in regraded)))
    checks.append(("审计字段不是装饰：没被改判的记录一律不带 regraded_from",
                   all(r["regraded_from"] is None for r in recs
                       if r["source_path"] not in actual_regraded)))
    checks.append(("改判记录的理由里写明依据（裁定 31.4 + 跨记录事实 + 为什么不是 "
                   "invalid_measurement）⇒ 事后可追，不是「C 说它旧」",
                   all(any("31.4" in x for x in r["reasons"])
                       and any("当前构建" in x for x in r["reasons"])
                       and any("provenance_kind" in x for x in r["reasons"])
                       and any("作废" in x for x in r["reasons"]) for r in regraded)))
    checks.append(("过渡期标签与本档一一对应：留在本档的带标签，被改判的标签随之撤下",
                   all(r["pending_impl_label"] == vi.PENDING_IMPL_LABEL for r in recs
                       if r["usable_for"] == vi.USABLE_PENDING_IMPL)
                   and all(r["pending_impl_label"] is None for r in regraded)))

    # --- 改判**不得动可用性**（D 的验收 2）：两档都不能当现构建证据 ⇒ physical_fact 一条不变 ---
    def _fact_expected(r: dict) -> bool:
        return (r["arm_verdict"] and str(r["gate_build"]) == str(cur)
                and r["measurement_validity_declared"] and r["measurement_valid"] is True
                and r["suspect_truncation_as_failure"] is not True
                and not _record_level_shape(r))

    facts = {r["source_path"] for r in recs if r["usable_for"] == vi.USABLE_PHYSICAL_FACT}
    n_fact_expected = sum(1 for r in recs if _fact_expected(r))
    checks.append((f"改判不动可用性：physical_fact 实测 {len(facts)} 条 = 独立复算 "
                   f"{n_fact_expected} 条，且与改判集交集为空（改分级没顺手改可用性）",
                   len(facts) == n_fact_expected and not (facts & actual_regraded)))

    # --- provenance_kind：理由侧子标签（裁定 31.4 的 (b)+子标签）---
    stale = [r for r in recs if r["usable_for"] == vi.USABLE_STALE_BUILD]
    checks.append((f"理由侧子标签覆盖全部 {len(stale)} 条 stale 记录，取值只在封闭集合内",
                   bool(stale) and all(r["provenance_kind"] in vi.PROVENANCE_KINDS for r in stale)))
    checks.append(("非 stale 档一律不带子标签（可用性只看 usable_for，子标签不越档）",
                   all(r["provenance_kind"] is None for r in recs
                       if r["usable_for"] != vi.USABLE_STALE_BUILD)))
    probe_dir = [r for r in stale
                 if any(m in (r["provenance"] or "") + r["source_path"]
                        for m in vi.DELIBERATE_REJECTION_PROBE_DIRS)]
    accepted_paths = {r["source_path"] for r in probe_dir
                      if r["gate_pass"] is True
                      and str(r["input_contract_status"]) == vi.GATE_EXONERATED}
    checks.append((f"探针目录里 {len(probe_dir)} 条：被拒的落 deliberate_rejection_probe，"
                   f"被**接受**的正向对照（{len(accepted_paths)} 条）不得落这个子标签 —— "
                   "否则就是把「故意被接受」写成「故意被拒」（说谎的标签比没标签更坏）",
                   bool(probe_dir) and bool(accepted_paths)
                   and all(r["provenance_kind"] == vi.PROVENANCE_DELIBERATE_REJECTION_PROBE
                           for r in probe_dir if r["source_path"] not in accepted_paths)
                   and all(r["provenance_kind"] != vi.PROVENANCE_DELIBERATE_REJECTION_PROBE
                           for r in probe_dir if r["source_path"] in accepted_paths)))
    kinds: dict[str, int] = {}
    for r in regraded:
        kinds[r["provenance_kind"]] = kinds.get(r["provenance_kind"], 0) + 1
    if len(shape) == 5:
        checks.append(("裁定 31.4 验收 1（本轮实测形状）：5 条 = 4×deliberate_rejection_probe "
                       f"+ 1×frozen_prereg_anchor（实测 {kinds}）",
                       kinds == {vi.PROVENANCE_DELIBERATE_REJECTION_PROBE: 4,
                                 vi.PROVENANCE_FROZEN_PREREG_ANCHOR: 1}))
    else:
        checks.append((f"裁定 31.4 验收 1 的 4+1 形状 —— SKIP：记录级形状此刻是 {len(shape)} 条"
                       f"（上游产物已变），实测子标签分布 {kinds}；上面几条结构性断言仍照跑", None))

    dis = inv.get("exoneration_disagreement") or {}
    ruling = dis.get("pending_impl_ruling") or {}
    ev = ruling.get("evidence") or {}
    checks.append(("清单 invariant 明文写了这一档的口径、标签与收窄条件（不只活在代码里）",
                   vi.USABLE_PENDING_IMPL in inv["invariant"]
                   and vi.PENDING_IMPL_LABEL in inv["invariant"]
                   and "承载免罪" in inv["invariant"]))
    checks.append(("清单明写这一档是逐份裁定口径（否则旧产物的标签会被误读成「v1.5 还没落地」）",
                   bool(dis.get("scope_note")) and vi.GATE_EXONERATED in str(dis.get("scope_note"))))
    checks.append(("结项用的是**实测字段**而非叙述：清单里的证据与自检独立复算逐项一致",
                   ev.get("n_record_level_shape") == len(shape)
                   and ev.get("n_pending_impl") == len(actual_pending)
                   and ev.get("n_regraded_to_stale") == len(actual_regraded)
                   and ev.get("record_level_shape_all_at_historical_builds")
                   == (bool(shape) and all(str(r["gate_build"]) != str(cur) for r in shape))
                   and {x["source_path"] for x in (ev.get("regraded_records") or [])}
                   == actual_regraded
                   and ev.get("activation_rule") == vi.PENDING_IMPL_ACTIVATION_RULE))
    # --- 裁定 28（增补七 §13）：标注作废、全部撤下；但**机制**不作废 ---
    checks.append(("裁定 28：标签已作废这一事实进清单（label_retired + 作废依据 + 引用纪律）",
                   ruling.get("label_retired") is True and bool(ruling.get("retired_by"))
                   and "25/22/1" in str(ruling.get("citation_rule"))))
    checks.append(("裁定 28：作废的是**标注**不是机制 ⇒ 档名仍在枚举里、现状态一律转引 D 的裁定"
                   "并注明 C 未独立复核",
                   ruling.get("grade_mechanism_retired") is False
                   and vi.USABLE_PENDING_IMPL in vi.USABLE_LEVELS and vi.LABEL_RETIRED is True
                   and "C 未独立复核" in str(ruling.get("arm_current_status_source"))))
    checks.append(("裁定 31.4 已结项：清单里同时留「C 当初提请的原话」与「D 判的 (b)+子标签」"
                   "（append-only：判了也不删自己问过什么），且词汇表与代码里那份同一个",
                   bool(ruling.get("todo9_question_as_filed"))
                   and "(a)" in str(ruling["todo9_question_as_filed"])
                   and "31.4" in str(ruling.get("ruling"))
                   and tuple(ruling["implementation"]["provenance_kind_vocabulary"])
                   == vi.PROVENANCE_KINDS
                   and ruling["implementation"]["regraded_to"] == vi.USABLE_STALE_BUILD))
    checks.append(("清单指向非恒假反例的位置（机制的价值在它将来会咬人的那一刻）",
                   "case_pending_impl_not_always_false" in str(ruling.get("not_always_false"))))

    per_arm = dis.get("per_arm_current_build")
    cur_obs = [o for v in (per_arm or {}).values() for o in v]
    checks.append((f"清单给出记录级正向脱节臂在**当前构建 {dis.get('current_build')}** 下的产物观测"
                   "（C 不重跑门禁去造观测，空列表就如实空着）",
                   isinstance(per_arm, dict) and bool(per_arm)
                   and all(isinstance(v, list) for v in per_arm.values())
                   and all({"provenance", "gate_build", "is_current_build"} <= set(o)
                           for o in cur_obs)))
    if cur_obs:
        checks.append(("当前构建下已承载免罪的记录不再落这一档（实现落地 ⇒ 过渡档自动让位）",
                       all(o["usable_for"] != vi.USABLE_PENDING_IMPL for o in cur_obs
                           if o["input_contract_status"] == vi.GATE_EXONERATED)))
    else:
        checks.append(("当前构建下已承载免罪的记录不再落这一档 —— SKIP：当前构建 "
                       f"{dis.get('current_build')} 下没有这些臂的裁定产物 ⇒ 未被验证", None))

    if actual_pending:
        checks.append((f"非空过：真目录此刻确实有 {len(actual_pending)} 条留在本档", True))
    else:
        checks.append(("真目录此刻本档为空 —— SKIP：记录级形状那批全部因「该臂在当前构建下已有"
                       "承载免罪的产物」被改判（裁定 31.4 的预期结果）；**本档非恒假**的证据在 "
                       "case_pending_impl_not_always_false 的合成反例里（SKIP≠PASS，ADR-C-004）",
                       None))

    # --- 变异6：把这一档整个拿掉（退回五档实现），上面的断言必须转红 ---
    real_classify = vi.classify
    try:
        vi.classify = _classify_without_pending_branch
        mut = vi.scan_dir(UPSTREAM_DIR)
    finally:
        vi.classify = real_classify
    mut_level = {r["source_path"]: r["usable_for"] for r in mut["records"]}
    checks.append(("变异6 确实改变了真清单（否则这条变异是空转）",
                   mut["usable_for_distribution"] != inv["usable_for_distribution"]))
    mv_false_shape = {r["source_path"] for r in shape if r["measurement_valid"] is not True}
    buried = {sp for sp in mv_false_shape if mut_level.get(sp) == vi.USABLE_INVALID_MEASUREMENT}
    checks.append((f"变异6（拿掉本档）下记录级形状里 measurement_valid 非 True 的 "
                   f"{len(mv_false_shape)} 条全部被埋进 invalid_measurement ⇒ 改判到 stale 是"
                   "裁定 31.4 的**主动选择**，不是「反正都会掉进 stale」（§8-C3 要防的事故仍在）",
                   bool(mv_false_shape) and buried == mv_false_shape))
    checks.append(("变异6 下改判痕迹（regraded_from）全部消失 ⇒ 改判依附本档、不是独立装饰",
                   all(r["regraded_from"] is None for r in mut["records"])))
    restored = {r["source_path"]: r["usable_for"] for r in vi.scan_dir(UPSTREAM_DIR)["records"]}
    checks.append(("还原后真清单分级恢复原状（monkey-patch 没有泄漏）", restored == {
        r["source_path"]: r["usable_for"] for r in recs}))

    # --- 变异7：把判据放宽成「一律免罪」（免罪万能牌）⇒ 好裁定被这一档吞掉 ---
    d, arm_index, got = _pending_impl_dir()
    real_pred = vi.is_pending_impl_exoneration
    try:
        vi.is_pending_impl_exoneration = lambda vc, ic: True
        over = {name: vi.parse_verdict(d / f"{name}.json", arm_index=arm_index)[0].usable_for
                for name in got if (d / f"{name}.json").exists()}
    finally:
        vi.is_pending_impl_exoneration = real_pred
    checks.append(("变异7（免罪万能牌）会把当前构建的 physical_fact 吞成待落地 "
                   "⇒ 「只认正向」的限制有牙",
                   over.get("authority_exo_gate_exonerated") == vi.USABLE_PENDING_IMPL))
    checks.append(("变异7 下权威表未记免罪的裁定也被抬进这一档 ⇒ 权威表前提非冗余",
                   over.get("authority_valid_gate_violated") == vi.USABLE_PENDING_IMPL))
    checks.append(("变异7 下终局语义怀疑 / 身份缺失 / 聚合报告**仍然**不被免罪盖过"
                   "（三条优先级不依赖判据宽窄，是 classify 的顺序在管）",
                   over.get("authority_exo_suspect") == vi.USABLE_INVALID_MEASUREMENT
                   and over.get("authority_exo_no_build") == vi.USABLE_UNIDENTIFIED
                   and over.get("authority_exo_undeclared") == vi.USABLE_UNIDENTIFIED
                   and over.get("authority_exo_aggregate") == vi.USABLE_NOT_A_VERDICT))

    # --- 变异8：只认**反方向** ⇒ 门禁判对了的臂被误记成实现缺口（裁定 18 的 stdfloor 形态）---
    # 真清单的反向脱节此刻为空（裁定 31.3 之后只在现构建子集上比，两侧一致），所以这一条
    # 改用**合成臂**验：门禁 ic=probe_exonerated、权威表 validity_class=valid（裁定 18 说这是
    # 门禁对、权威表滞后）。原判 physical_fact；把方向翻过来就会变成 pending_impl。
    d8 = OUT_ROOT / "direction_mutant"
    _write_arms_summary(d8, [{"arm": "syn_gate_right_authority_lag", "validity_class": "valid",
                              "ic_status": "verified_ok"}],
                        note="变异8 用合成臂：数字与免罪声明均无物理意义（ADR-C-007）")
    art8 = _write_verdict(d8 / "gate_syn_gate_right_authority_lag.json", gate_build=cur,
                          measurement_valid=True, ic_status=vi.GATE_EXONERATED,
                          arm="syn_gate_right_authority_lag")
    idx8 = vi.load_arm_index(d8)
    base_level = vi.parse_verdict(art8, arm_index=idx8)[0].usable_for
    try:
        vi.is_pending_impl_exoneration = (
            lambda vc, ic: str(ic) == vi.GATE_EXONERATED and str(vc) != vi.AUTHORITY_EXONERATED)
        flipped = vi.parse_verdict(art8, arm_index=idx8)[0].usable_for
    finally:
        vi.is_pending_impl_exoneration = real_pred
    checks.append(("变异8（只认反方向）会把 裁定 18 那类「门禁判对了、权威表滞后」的臂记成实现缺口"
                   f"（{base_level} → {flipped}）⇒ 方向限制非冗余",
                   base_level == vi.USABLE_PHYSICAL_FACT
                   and flipped == vi.USABLE_PENDING_IMPL))


def _always_regrade(records, current):
    """变异9：把收窄条件当**恒真**（该臂「总有」承载产物）⇒ 本档永不触发（恒假）。"""
    out, regraded = [], []
    for r in records:
        if r.usable_for == vi.USABLE_PENDING_IMPL:
            out.append(vi._rebuild(r, usable_for=vi.USABLE_STALE_BUILD,
                                   provenance_kind=vi.PROVENANCE_ORDINARY_STALE,
                                   regraded_from=vi.USABLE_PENDING_IMPL,
                                   pending_impl_label=None,
                                   reasons=list(r.reasons) + ["MUTANT: 恒改判"]))
            regraded.append({"source_path": r.source_path, "arm": r.arm,
                             "provenance": r.provenance, "gate_build": r.gate_build,
                             "gate_version": r.gate_version,
                             "is_current_build": bool(r.is_current_build),
                             "source_sha256": r.source_sha256,
                             "regraded_from": vi.USABLE_PENDING_IMPL,
                             "regraded_to": vi.USABLE_STALE_BUILD,
                             "provenance_kind": vi.PROVENANCE_ORDINARY_STALE})
        else:
            out.append(r)
    return out, {"regraded": regraded, "n_regraded": len(regraded),
                 "carrying_arms_at_current_build": [],
                 "carrying_artifact_rule": "MUTANT", "activation_rule": "MUTANT: 恒改判"}


def _never_regrade(records, current):
    """变异10：**恒不改判**（收窄条件当恒假）⇒ 裁定 31.4 的 (b) 从未落地。"""
    return list(records), {"regraded": [], "n_regraded": 0,
                           "carrying_arms_at_current_build": [],
                           "carrying_artifact_rule": vi.CARRYING_ARTIFACT_RULE,
                           "activation_rule": "MUTANT: 恒不改判"}


def case_pending_impl_not_always_false(checks: list) -> None:
    """裁定 31.4 的附加要求：收窄之后本档**非恒假**（机制将来咬得动）。

    合成两个臂，唯一差别是「该臂在当前构建下有没有承载免罪的产物」：

    - **无**承载产物 ⇒ 必须**触发**本档（否则收窄就把这一档变成了恒假 = 没有这一档）；
    - **有**承载产物 ⇒ 必须**改判**成 stale + provenance_kind + regraded_from。

    再用两个变异体（恒改判 / 恒不改判）证明这两条都不是常量。合成产物写在
    `runs/infra/c_verdict_selfcheck/<ts>/`，**数字无物理意义**（ADR-C-007）。
    """
    d = OUT_ROOT / "regrade_not_always_false"
    cur = vi.current_gate_identity()
    _write_arms_summary(d, [
        {"arm": "syn_no_carrying", "validity_class": vi.AUTHORITY_EXONERATED,
         "ic_status": "violated", "gate_file": "gate_syn_no_carrying_hist.json"},
        {"arm": "syn_with_carrying", "validity_class": vi.AUTHORITY_EXONERATED,
         "ic_status": "violated", "gate_file": "gate_syn_with_carrying_hist.json"},
    ], note="裁定 31.4 非恒假反例：数字与免罪声明均无物理意义")
    for name in ("syn_no_carrying", "syn_with_carrying"):
        _write_verdict(d / f"gate_{name}_hist.json", gate_build="deadbeef0000",
                       measurement_valid=False, ic_status="violated", arm=name)
    _write_verdict(d / "gate_syn_with_carrying_cur.json", gate_build=cur["gate_build"],
                   measurement_valid=True, ic_status=vi.GATE_EXONERATED,
                   arm="syn_with_carrying")
    inv = vi.scan_dir(d)
    recs = {r["source_path"]: r for r in inv["records"]}

    def _level(suffix: str, source: dict | None = None) -> Any:
        src = source if source is not None else recs
        hits = [r for p, r in src.items() if p.endswith(suffix)]
        return hits[0]["usable_for"] if len(hits) == 1 else f"<{len(hits)} hits>"

    def _rec(suffix: str) -> dict:
        hits = [r for p, r in recs.items() if p.endswith(suffix)]
        assert len(hits) == 1, (suffix, len(hits))
        return hits[0]

    no_carry = _rec("gate_syn_no_carrying_hist.json")
    with_carry = _rec("gate_syn_with_carrying_hist.json")
    checks.append(("非恒假反例①：免罪条目已登记、该臂在当前构建下**无任何**承载产物 ⇒ 本档"
                   f"**必须触发**（实测 {no_carry['usable_for']}）",
                   no_carry["usable_for"] == vi.USABLE_PENDING_IMPL
                   and no_carry["pending_impl_label"] == vi.PENDING_IMPL_LABEL
                   and no_carry["regraded_from"] is None
                   and no_carry["provenance_kind"] is None))
    checks.append(("非恒假反例②：同形状但该臂在当前构建下**已有**承载产物 ⇒ 必须改判成 "
                   "stale_build_evidence + regraded_from + provenance_kind（实测 "
                   f"{with_carry['usable_for']} / {with_carry['provenance_kind']}）",
                   with_carry["usable_for"] == vi.USABLE_STALE_BUILD
                   and with_carry["regraded_from"] == vi.USABLE_PENDING_IMPL
                   and with_carry["provenance_kind"] in vi.PROVENANCE_KINDS
                   and with_carry["pending_impl_label"] is None))
    checks.append(("两个形状在同一份清单里同时出现（一个触发、一个改判）⇒ 收窄条件真的在判，"
                   "不是常量",
                   inv["usable_for_distribution"].get(vi.USABLE_PENDING_IMPL) == 1
                   and inv["regraded_from_pending_impl"]["n_regraded"] == 1))
    meta = json.loads((d / "arms_summary.json").read_text(encoding="utf-8"))["meta"]
    checks.append(("合成产物照 ADR-C-007 标明「数字无物理意义」，且只写在 C 自己的目录里",
                   meta["c_synthetic"]["physical_meaning"] is False
                   and bool(meta["c_synthetic"]["note"])
                   and all(p.startswith("runs/infra/c_verdict_selfcheck/") for p in recs)))

    real_regrade = vi.regrade_pending_impl
    try:
        vi.regrade_pending_impl = _always_regrade
        mut_always = {r["source_path"]: r for r in vi.scan_dir(d)["records"]}
        vi.regrade_pending_impl = _never_regrade
        mut_never = {r["source_path"]: r for r in vi.scan_dir(d)["records"]}
    finally:
        vi.regrade_pending_impl = real_regrade
    checks.append(("变异9（恒改判 = 收窄条件恒真）下反例① 不再触发本档 ⇒ 上面那条断言有牙，"
                   "「非恒假」不是嘴上说的",
                   _level("gate_syn_no_carrying_hist.json", mut_always)
                   != vi.USABLE_PENDING_IMPL))
    checks.append(("变异10（恒不改判）下反例② 仍停在 pending_impl ⇒ 改判那条断言同样有牙",
                   _level("gate_syn_with_carrying_hist.json", mut_never)
                   == vi.USABLE_PENDING_IMPL
                   and vi.scan_dir(d)["regraded_from_pending_impl"]["n_regraded"] == 1))
    checks.append(("还原后合成清单分级恢复原状（monkey-patch 没有泄漏）",
                   {r["source_path"]: r["usable_for"] for r in vi.scan_dir(d)["records"]}
                   == {p: r["usable_for"] for p, r in recs.items()}))


def case_reconciliation_current_build_only(checks: list) -> None:
    """裁定 31.3：免罪对账只在**两侧同为当前构建**的子集上做，不同构建改报不可比。

    三件事都要证明：① 真清单两侧为空**不是因为判据恒空**（确实逐臂比过了）；
    ② 历史侧转 `stale_side_not_comparable`，各自带两侧 build；③ 合成反例能让它**变红**。
    """
    inv = json.loads(OUT_INVENTORY.read_text(encoding="utf-8"))
    dis = inv["exoneration_disagreement"]
    cur = inv["gate_current"]["gate_build"]
    rows = json.loads((UPSTREAM_DIR / "arms_summary.json").read_text(encoding="utf-8"))["arms"]
    fwd = dis["authority_exonerated_gate_not"]
    rev = dis["gate_exonerated_authority_not"]
    live = dis["live_compared"]
    stale = dis[vi.STALE_SIDE_NOT_COMPARABLE]
    non_adj = dis["current_build_non_adjudicated"]

    checks.append(("裁定 31.3：对账口径写进清单本身（只在 is_current_build==true 子集上做，"
                   "不同构建报 stale_side_not_comparable）",
                   "is_current_build" in dis["scope"]
                   and vi.STALE_SIDE_NOT_COMPARABLE in dis["scope"]))
    checks.append((f"非空过：两侧同为当前构建的可比对账 {dis['n_live_compared']} 臂 = 权威表 "
                   f"{len(rows)} 行，且每臂**两侧都带构建**（authority.gate_build / "
                   "gate.is_current_build / gate.gate_build）",
                   dis["n_live_compared"] == len(rows) == len(live)
                   and all(e["comparable"] is True and e["gate"]["is_current_build"] is True
                           and str(e["gate"]["gate_build"]) == str(cur)
                           and str(e["authority"]["gate_build"]) == str(cur)
                           and e["matched_by"] for e in live)))
    checks.append(("本轮实测：现构建子集上两个方向**均为空**（k2 seed0 与 stdfloor 都已是 v1.5 "
                   "承载），且不是因为没比（live_all_agree=true）",
                   fwd == [] and rev == [] and dis["live_all_agree"] is True))
    checks.append((f"历史侧 {len(stale)} 条转 {vi.STALE_SIDE_NOT_COMPARABLE}：每条都带 "
                   "authority_build / gate_build / provenance / is_current_build=false，"
                   "且没有一条混进两个方向列表（可见但不报警）",
                   bool(stale)
                   and all(e["kind"] == vi.STALE_SIDE_NOT_COMPARABLE and e["comparable"] is False
                           and "authority_build" in e and "gate_build" in e
                           and e["gate"]["provenance"] and e["gate"]["is_current_build"] is False
                           and str(e["gate_build"]) != str(cur)
                           and e["why_not_comparable"] for e in stale)
                   and not ({e["arm"] for e in stale} & (set(fwd) | set(rev)))))
    checks.append(("不可比条目里能看到 D 现场点名的那一份：顶层 v1.0 时代产物（gate_build=None）"
                   "对 v1.5 权威表 ⇒ 明确写成不可比，不再冒充活矛盾",
                   any(e["gate"]["provenance"] == "<top-level>" and e["gate_build"] in (None, "None")
                       and str(e["authority_build"]) == str(cur) for e in stale)))
    checks.append(("现构建里**不是**权威表指定对账那一份的产物没有被静默丢掉：单列可见 + 写明排除理由",
                   all(e["gate"]["is_current_build"] is True and e["why_excluded"]
                       and e["authority"]["gate_file"] for e in non_adj)))
    checks.append(("权威表每一行都认得出对应的门禁产物（认不出会单列，不静默挑一份）",
                   dis["authority_row_without_counterpart"] == []))
    own = dis["historical_gate_artifact_ownership"]
    top_files = sorted(UPSTREAM_DIR.glob("gate_*.json"))
    checks.append((f"顶层历史 gate_*.json 的归属写明（实测 {own['n_files']} 份 = 目录里 "
                   f"{len(top_files)} 份；{own['n_at_current_build']} 份在当前构建；"
                   "owner / status / reading_rule 都在，且明写不参与现口径对账）",
                   own["n_files"] == len(top_files) and own["n_at_current_build"] == 0
                   and bool(own["owner"]) and bool(own["status"]) and bool(own["reading_rule"])
                   and own["participates_in_current_reconciliation"] is False))
    checks.append(("清单写明这字段怎么才能变红（否则「两侧为空」会被读成「闸恒空」）",
                   "红" in dis["red_condition"] or "非空" in dis["red_condition"]))

    # --- 合成反例：证明它**红得起来**（裁定 31.3 第 2 条 / 裁定 27.1「恒假的闸等于没有闸」）---
    d = OUT_ROOT / "reconcile_counterexample"
    cur_id = vi.current_gate_identity()
    _write_arms_summary(d, [
        {"arm": "syn_live_fwd", "validity_class": vi.AUTHORITY_EXONERATED,
         "ic_status": "violated", "gate_file": "gate_syn_live_fwd.json"},
        {"arm": "syn_live_rev", "validity_class": "valid", "ic_status": "verified_ok",
         "gate_file": "gate_syn_live_rev.json"},
        {"arm": "syn_stale_side", "validity_class": vi.AUTHORITY_EXONERATED,
         "ic_status": "violated", "gate_file": "gate_syn_stale_side.json"},
        {"arm": "syn_agree", "validity_class": "valid", "ic_status": "verified_ok",
         "gate_file": "gate_syn_agree.json"},
    ], note="裁定 31.3 非恒真反例：数字与免罪声明均无物理意义")
    # 两侧同为当前构建、authority 说免罪而 gate 说不免罪 ⇒ **必须**报出 disagreement
    _write_verdict(d / "gate_syn_live_fwd.json", gate_build=cur_id["gate_build"],
                   measurement_valid=True, ic_status="verified_ok", arm="syn_live_fwd")
    # 反方向（裁定 18 的形态）：gate 说免罪、authority 没记 ⇒ 也必须报，但**不改分级**
    _write_verdict(d / "gate_syn_live_rev.json", gate_build=cur_id["gate_build"],
                   measurement_valid=True, ic_status=vi.GATE_EXONERATED, arm="syn_live_rev")
    # 同一个形状、gate 侧换成旧构建 ⇒ 不得报 disagreement，只能报不可比
    _write_verdict(d / "gate_syn_stale_side.json", gate_build="deadbeef0000",
                   measurement_valid=False, ic_status="violated", arm="syn_stale_side")
    _write_verdict(d / "gate_syn_agree.json", gate_build=cur_id["gate_build"],
                   measurement_valid=True, ic_status="verified_ok", arm="syn_agree")
    syn = vi.scan_dir(d)
    sdis = syn["exoneration_disagreement"]
    syn_recs = {r["source_path"]: r for r in syn["records"]}
    checks.append(("合成反例①（两侧同为当前构建、authority 免罪而 gate 不免罪）⇒ 正向列表"
                   f"**真的红**（实测 {sdis['authority_exonerated_gate_not']}）；4 个合成臂里"
                   "只有 3 个两侧同为当前构建（第 4 个 gate 侧在旧构建 ⇒ 不参与活对账）",
                   sdis["authority_exonerated_gate_not"] == ["syn_live_fwd"]
                   and sdis["n_live_compared"] == 3
                   and sdis["live_all_agree"] is False))
    checks.append(("合成反例②（反方向：gate 免罪、authority 未记）⇒ 反向列表也红，且该臂分级"
                   "**没有**被改（裁定 18：只上报不裁定谁对）",
                   sdis["gate_exonerated_authority_not"] == ["syn_live_rev"]
                   and [r["usable_for"] for p, r in syn_recs.items()
                        if p.endswith("gate_syn_live_rev.json")] == [vi.USABLE_PHYSICAL_FACT]))
    checks.append(("合成反例③（同一形状、gate 侧换成旧构建）⇒ **不**报 disagreement，改报 "
                   f"{vi.STALE_SIDE_NOT_COMPARABLE} 并带两侧 build（构建过滤就是这两者的分界）",
                   "syn_stale_side" not in sdis["authority_exonerated_gate_not"]
                   and [e["arm"] for e in sdis[vi.STALE_SIDE_NOT_COMPARABLE]] == ["syn_stale_side"]
                   and sdis[vi.STALE_SIDE_NOT_COMPARABLE][0]["gate_build"] == "deadbeef0000"
                   and str(sdis[vi.STALE_SIDE_NOT_COMPARABLE][0]["authority_build"])
                   == str(cur_id["gate_build"])))
    checks.append(("合成对照臂（两侧一致）不出现在任何列表里 ⇒ 这字段也不是**恒报**的红",
                   all("syn_agree" not in (sdis[k] or []) for k in
                       ("authority_exonerated_gate_not", "gate_exonerated_authority_not"))
                   and not [e for e in sdis[vi.STALE_SIDE_NOT_COMPARABLE]
                            if e["arm"] == "syn_agree"]))
    checks.append(("合成反例里 authority 侧与 gate 侧都自带构建（两侧带 build 是裁定 31.3 的硬要求）",
                   all(e["authority"]["gate_build"] and e["gate"]["gate_build"] is not None
                       or e["gate"]["gate_build"] is None
                       for e in sdis["live_compared"] + sdis[vi.STALE_SIDE_NOT_COMPARABLE])))
    meta = json.loads((d / "arms_summary.json").read_text(encoding="utf-8"))["meta"]
    checks.append(("合成产物照 ADR-C-007 标明「数字无物理意义」，且只写在 C 自己的目录里",
                   meta["c_synthetic"]["physical_meaning"] is False
                   and all(p.startswith("runs/infra/c_verdict_selfcheck/") for p in syn_recs)))


def _write_arms_summary(directory: Path, rows: list[dict], *, note: str) -> Path:
    """造一份**结构同形**的合成权威表（只用于改判/对账测试；数字与免罪声明无物理意义）。

    只填对账真正读到的那几个键（`validity_class` / `ic_status` / `gate_build` / `gate_file` /
    `adjudicated_artifact`），其余留 None —— 合成表越像真表，越容易被人当真臂读，
    所以 `meta.c_synthetic.physical_meaning=false` 是硬性标记（ADR-C-007）。
    """
    directory.mkdir(parents=True, exist_ok=True)
    cur = vi.current_gate_identity()
    full = []
    for row in rows:
        base: dict[str, Any] = {
            "arm": row["arm"], "file": f"eval_{row['arm']}.json",
            "authoritative_eval_file": None,
            "validity_class": "valid", "validity_reason": "synthetic_for_selfcheck",
            "ic_status": "verified_ok", "probe_exoneration_status": None,
            "gate_build": cur["gate_build"], "gate_version": cur["gate_version"],
            "gate_spec_sha256": cur["gate_spec_sha256"],
            "gate_file": None, "adjudicated_artifact": None, "superseded_by": None,
            "labels_reportable": None, "blowup_threshold_source": None,
            "field_class": "strict", "measurement_valid": True, "gate_pass": True}
        base.update(row)
        full.append(base)
    payload = {"meta": {"schema_version": 3,
                        "generated_at": time.strftime("%Y-%m-%dT%H%M%S%z"),
                        "producer": "scripts/c_selfcheck_verdict_identity.py（合成，非 A 的权威表）",
                        "gate_version": [cur["gate_version"]], "gate_build": [cur["gate_build"]],
                        "c_synthetic": {"physical_meaning": False, "note": note}},
               "arms": full}
    path = directory / "arms_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


CASES = (case_current_gate_identity_is_imported, case_real_dir_inventory,
         case_no_recomputation_and_content_identity, case_supersession,
         case_synthetic_downgrades, case_mutation_classify_always_fact,
         case_identity_is_content_addressed, case_write_scope,
         case_upstream_authority_join, case_n_matches_arm_guard,
         case_pending_impl_grade, case_pending_impl_real_inventory,
         # 裁定 31.4 / 31.3 的附加要求：两个「判据不是常量」的证明（非恒假 / 非恒真）
         case_pending_impl_not_always_false, case_reconciliation_current_build_only)


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool]] = []
    for case in CASES:
        print(f"--- {case.__name__} ---", flush=True)
        before = len(checks)
        case(checks)
        for name, ok in checks[before:]:
            tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
            print(f"[{tag}] {name}", flush=True)
    failed = [name for name, ok in checks if ok is False]
    skipped = [name for name, ok in checks if ok is None]
    n_pass = len([1 for _, ok in checks if ok is True])
    print("--- 全部通过 ---" if not failed else f"--- 失败 {len(failed)} 条 ---")
    for name in failed:
        print(f"  FAIL {name}")
    if skipped:
        print(f"--- 另有 {len(skipped)} 条 SKIP（未被验证，不计入通过）---")
    inv = json.loads(OUT_INVENTORY.read_text(encoding="utf-8")) if OUT_INVENTORY.exists() else {}
    OUT_JSON.write_text(json.dumps({
        "cases": [c.__name__ for c in CASES],
        "checks": [{"name": name, "ok": (None if ok is None else bool(ok))}
                   for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_pass": n_pass,
        "n_failed": len(failed), "n_skipped": len(skipped), "skipped": skipped,
        "artifact_dir": str(OUT_ROOT), "inventory": str(OUT_INVENTORY),
        "upstream_dir": str(UPSTREAM_DIR.relative_to(ROOT)),
        "inventory_summary": {k: inv.get(k) for k in
                              ("n_files_scanned", "n_verdicts", "build_distribution",
                               "usable_for_distribution", "measurement_valid_distribution",
                               "n_superseded", "arms_with_conflicting_builds", "gate_current")},
        "impl_sha256": {rel: vi.content_sha256(ROOT / rel) for rel in
                        ("registry/verdict_identity.py", "scripts/c_selfcheck_verdict_identity.py")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"结果: {n_pass}/{len(checks)} PASS"
          + (f"（{len(skipped)} SKIP）" if skipped else "") + f" -> {OUT_JSON}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
