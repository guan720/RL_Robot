#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B2 · `demo_manifest.json` 的**披露式追加写**（裁定 88.5-1 的三字段 + D §20.6-4 的命名行）。

## 为什么要有这个件（而不是手改 JSON）
D 的补偿控制要求 `renderer_class_at_start / renderer_class_at_end / arm_stable` **落进 manifest**，
而产出 formal-40 的那份生成器字节（`b6af48fc6d58`）在运行内**没有**终点复测 ⇒ 这三字段
只能事后追加。**事后改一份已落地的证据产物，风险是"篡改"**，所以本件把追加做成
可复核的三件事（口径照抄 `scripts/b2_export_states_14d.py:patch_demo_manifest`，它已被 D 收下的
契约 §17-4 回写用过一次）：
1. **前后身份全留证**：before/after 的 `sha256_12` + `bytes` + `mtime`，以及 `keys_added`。
2. **机器断言"只增不改"**：写完后重新读盘，逐键深比对 —— 原有键的值必须**逐个相等**，
   新增键必须**恰好等于** `keys_added`；不成立 ⇒ `rc=2` 并保留 before 影像。
3. **数据集本体穷举计数不变**：`pi05_lerobot / team_form / sidecar` 三个子树的
   `(文件数, 字节总数)` 进出一致 ⇒ 追加写没有顺手碰数据。
另外：追加前把原字节拷成 before 影像；**已存在的顶层键默认拒绝覆盖**（`rc=2`），
要覆盖必须显式 `--allow-overwrite`（覆盖 = 改证据，必须留痕且有理由）。

## 三字段的事实源（不手打数字）
`renderer_arm_compensating_control` 全部由 `--arm-probe` 指的那份产物**机器派生**
（`scripts/b2_probe_render_arm.py` 的输出），并把它自己的 sha256[:12] 一并登记 ⇒
下游可以从 manifest 一路追到端点复测的原始读数（含那条如实登记的缺口：
`renderer_class_at_end_in_run = null`，运行内没测）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
BODY_ROOTS = ("pi05_lerobot", "team_form", "sidecar")


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def mtime_iso(p: Path) -> str:
    return _dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def count_tree(root: Path) -> dict:
    n, b = 0, 0
    if root.exists():
        for q in root.rglob("*"):
            if q.is_file():
                n += 1
                b += q.stat().st_size
    return {"n_files": n, "bytes_total": b}


def compose_arm_addendum(probe: dict, probe_path: Path) -> dict:
    """从端点复测产物**机器派生**三字段（不手打、不转述）。"""
    crit = probe.get("arm_stable_criterion") or []
    return {
        # ---- D 要的三个字段（裁定 88.5-1 补偿控制）----
        "renderer_class_at_start": probe.get("renderer_class_at_start"),
        "renderer_class_at_end": probe.get("renderer_class_at_end"),
        "arm_stable": probe.get("arm_stable"),
        # ---- 判据与出处（让三字段可追到原始读数）----
        "ruling": "裁定 88.5-1（d_handoff_to_b2 §20.4）：加项 1（渲染臂硬拒绝）一次性有条件豁免 ⇒ "
                  "补偿控制 = 跑完立刻核两个端点，并把三字段落进 manifest",
        "arm_stable_criterion": [{"id": c.get("id"), "criterion": c.get("criterion"),
                                  "observed": c.get("observed"), "holds": c.get("holds")}
                                 for c in crit],
        "arm_stable_n_holds": "%d/%d" % (probe.get("arm_stable_n_holds"),
                                         probe.get("arm_stable_n_criteria")),
        "endpoints_agree": probe.get("endpoints_agree"),
        "environment_invalid": probe.get("environment_invalid"),
        "ruling_88_5_1_exemption_void": probe.get("ruling_88_5_1_exemption_void"),
        "renderer_class_at_end_measurement_kind": probe.get(
            "renderer_class_at_end_measurement_kind"),
        "renderer_class_at_end_in_run": probe.get("renderer_class_at_end_in_run"),
        "gap_s_since_run_end": probe.get("gap_s_since_run_end"),
        "gl_strings_at_start": probe.get("renderer_class_at_start_gl_strings"),
        "gl_strings_at_end": ((probe.get("post_run_probe") or {}).get("gl_identity") or {}).get(
            "gl_strings"),
        "wall_time_evidence": probe.get("wall_time_evidence"),
        "late_run_render_evidence": probe.get("late_run_render_evidence"),
        "tooth_software_arm": {"tooth_id": (probe.get("tooth_software_arm") or {}).get("tooth_id"),
                               "child_renderer_class": (probe.get("tooth_software_arm") or {}).get(
                                   "child_renderer_class"),
                               "child_gl_renderer": (probe.get("tooth_software_arm") or {}).get(
                                   "child_gl_renderer"),
                               "tooth_verified": (probe.get("tooth_software_arm") or {}).get(
                                   "tooth_verified"),
                               "what_it_proves": "端点复测**不是**恒报 nvidia_gpu 的报告器："
                                                 "同一把尺在不带 EGL 前缀的子进程里读到 llvmpipe",
                               "what_it_does_not_prove": "**硬拒绝仍欠**（加项 1）：本子进程 "
                                                 "`--probe-only` 的 rc 是 0，因为它只测不采。"
                                                 "「`MUJOCO_GL=egl` 不带前缀 ⇒ 采集必须 exit != 0」"
                                                 "要等加项 1 落进生成器才有。"},
        "source_artifact": {"path": str(probe_path), "sha256_12": sha12(probe_path),
                            "generated_at": probe.get("generated_at"),
                            "generated_by": probe.get("generated_by"),
                            "probe_script_identity": probe.get("script_identity")},
        "added_post_hoc": True,
        "added_at": _now(),
        "added_by": str(SCRIPT.relative_to(ROOT)),
        "why_added_post_hoc": "产出本批的生成器字节（见 `generator_sha256_12`）在运行内没有终点复测；"
                              "三字段是 D 的补偿控制要求的，只能事后追加 ⇒ 追加过程按本件的"
                              "「前后 sha + 只增不改断言 + 本体计数不变」三重披露执行",
    }


def compose_naming_addendum() -> dict:
    return {
        "pilot5": "**每方向 5 个 seed ⇒ 共 10 集**（不是 5 集）。目录名 `pilot5` 里的 5 指"
                  "**每方向的 seed 数**；内容 = 10 集 / 2746 帧。",
        "pilot5_dataset_dir": "runs/vla/b2_sim_demo_bidir_20260930/pilot（**目录名是 `pilot`**，"
                              "npz 侧目录才叫 `pilot5`：`runs/vla/b2_states_14d_20260930/pilot5`）",
        "formal": "**每方向 20 个 seed ⇒ 共 40 集**（seeds 2000…2019 × {forward, reverse}），"
                  "11035 帧；`pilot` 的 5 个 seed ⊂ `formal` 的 20 个。",
        "formal_dataset_dir": "runs/vla/b2_sim_demo_bidir_20260930/formal",
        "why_written": "D §20.6-4 / §19.3：目录名与内容不符已经让 D 在裁定 86 栽过一次"
                       "（把 `pilot5` 读成 5 集）⇒ 命名口径必须写在产物里，不靠读者推断。",
        "added_post_hoc": True, "added_at": _now(), "added_by": str(SCRIPT.relative_to(ROOT)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--arm-probe", default=None,
                    help="scripts/b2_probe_render_arm.py 的产物（⇒ 追加三字段）")
    ap.add_argument("--naming-note", action="store_true", help="追加 `naming_note`（D §20.6-4）")
    ap.add_argument("--allow-overwrite", action="store_true",
                    help="允许覆盖已存在的顶层键（默认拒绝：覆盖 = 改证据）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    mp = Path(a.manifest)
    mp = mp if mp.is_absolute() else (ROOT / mp)
    if not mp.exists():
        print(json.dumps({"error": "manifest 不存在", "path": str(mp)}, ensure_ascii=False))
        return 2

    addenda: dict = {}
    if a.arm_probe:
        pp = Path(a.arm_probe)
        pp = pp if pp.is_absolute() else (ROOT / pp)
        probe = json.loads(pp.read_text(encoding="utf-8"))
        addenda["renderer_arm_compensating_control"] = compose_arm_addendum(probe, pp)
    if a.naming_note:
        addenda["naming_note"] = compose_naming_addendum()
    if not addenda:
        print(json.dumps({"error": "没有任何要追加的内容（--arm-probe / --naming-note 都没给）"},
                         ensure_ascii=False))
        return 2

    before = json.loads(mp.read_text(encoding="utf-8"))
    conflict = [k for k in addenda if k in before and not a.allow_overwrite]
    if conflict:
        print(json.dumps({"error": "顶层键已存在，默认拒绝覆盖（覆盖 = 改证据）",
                          "conflicting_keys": conflict,
                          "hint": "确有理由请加 --allow-overwrite，并在日报里写明理由"},
                         ensure_ascii=False, indent=1))
        return 2

    # 追加内容先独立落盘一份（即使不接受就地追加，三字段也有机器可读的载体）
    standalone = mp.parent / "manifest_addendum_ruling_88_5.json"
    standalone.write_text(json.dumps(
        {"spec": "demo_manifest.json 的追加内容（独立载体；就地追加见同目录 manifest）",
         "generated_at": _now(), "generated_by": str(SCRIPT.relative_to(ROOT)),
         "target_manifest": str(mp), "target_manifest_sha256_12_before": sha12(mp),
         "addenda": addenda}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if a.dry_run:
        print(json.dumps({"dry_run": True, "keys_to_add": sorted(addenda),
                          "standalone_artifact": str(standalone),
                          "before_sha256_12": sha12(mp)}, ensure_ascii=False, indent=1))
        return 0

    before_sha, before_bytes, before_mtime = sha12(mp), mp.stat().st_size, mtime_iso(mp)
    img_dir = mp.parent / "overwrite_guard"
    img_dir.mkdir(parents=True, exist_ok=True)
    before_img = img_dir / ("demo_manifest.json.before_addendum_%s"
                            % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(mp, before_img)
    body_before = {r: count_tree(mp.parent / r) for r in BODY_ROOTS}

    merged = dict(before)
    merged.update(addenda)
    # indent=2：与**当前盘上形态**一致（上一次追加写 = 导出器的契约 §17-4 回写，用的就是 2）
    # ⇒ 本次追加只增字节、不把整份文件重新排版（byte churn 最小化，便于 diff 复核）
    mp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- 机器断言：只增不改 ----
    after = json.loads(mp.read_text(encoding="utf-8"))
    keys_added = sorted(set(after) - set(before))
    changed = [k for k in before if k in after and after[k] != before[k]]
    dropped = [k for k in before if k not in after]
    additive_only = (not changed and not dropped and keys_added == sorted(addenda))
    body_after = {r: count_tree(mp.parent / r) for r in BODY_ROOTS}
    body_unchanged = all(body_before[r] == body_after[r] for r in BODY_ROOTS)
    res = {
        "manifest": str(mp), "keys_added": keys_added,
        "before": {"sha256_12": before_sha, "bytes": before_bytes, "mtime": before_mtime},
        "after": {"sha256_12": sha12(mp), "bytes": mp.stat().st_size, "mtime": mtime_iso(mp)},
        "before_image": str(before_img),
        "standalone_artifact": str(standalone),
        "additive_only_assertion": {
            "ok": additive_only, "preexisting_keys_changed": changed,
            "preexisting_keys_dropped": dropped,
            "expected_keys_added": sorted(addenda), "actual_keys_added": keys_added,
            "method": "写完后重新读盘，逐键深比对（`after[k] != before[k]` 即算改）"},
        "dataset_body_untouched": {"checked_roots": list(BODY_ROOTS), "before": body_before,
                                   "after": body_after, "unchanged": body_unchanged},
        "three_fields": {k: addenda["renderer_arm_compensating_control"][k]
                         for k in ("renderer_class_at_start", "renderer_class_at_end",
                                    "arm_stable")} if "renderer_arm_compensating_control" in addenda else None,
        "rc": 0 if (additive_only and body_unchanged) else 2,
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return res["rc"]


if __name__ == "__main__":
    sys.exit(main())
