#!/usr/bin/env python3
"""T-E-EGL-COLDSTART 产物目录的逐文件 MANIFEST 生成器（裁定 85.9-3 / 87.1-4 / 89.5-1）。

为什么不复用 `e_mainline_render_calib.write_manifest()`：那个函数的**表头字段是标定轮专用的**
（`task_order` 指向 §8.3、`activation_artifact` 指激活件、`notes` 是标定轮的口径），
套到冷启动目录会把三件不相干的口径写进表头 = 裁定 71 `caliber_transplant_ban` 的同型动作。
**枚举算法与最长前缀匹配规则照抄它**（不另造一套语义），只换 DESC 表与表头。

两条内建纪律（都是本仓已有事故换来的）：
1. **原地重写前自动留前像**（`before_images/MANIFEST.json.before<ts>`）—— 防止重演
   `OVERWRITE_EVENT_20260929_2345.md`（裁定 83.5）。
2. **有任何文件落到 `(未登记)` ⇒ exit 3**（清单有洞就不是清单）。空目录 ⇒ exit 4
   （裁定 88.3-2 `aggregate_over_empty_set_must_be_null`：不许在空集上给出"通过"形状的产物）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO / "runs/infra/e_egl_coldstart_20260930"

DESC = {
    "COLDSTART_EVIDENCE_v3.json": (
        "**权威件（当前唯一可引用的冷启动证据）**：五阶段 `manifest,chain,relink,mutant,baseline` 全跑，"
        "`delivery_status=COLDSTART_VERIFIED`、`all_teeth_proven=true`、`stages_skipped=[]`、"
        "`c4_gl_renderer_measured=true`、`failed_teeth=[]`、`boundary_clean_no_system_write=true`、**exit 0**。"
        "C4 实测 `GL_RENDERER=NVIDIA A800-SXM4-80GB/PCIe/SSE2`、`GL_VERSION=4.6.0 NVIDIA 590.48.01`、"
        "`renderer_class=nvidia_gpu`。反向牙 `tooth_baseline` 的 8 条判据**全过**，其中 v2 假红的三条占用旁证腿"
        "（L5 `util_max=76%`/`mem_max=142 MiB`、L5b `child_nvidia_fds=[/dev/nvidia2,/dev/nvidiactl]`、S2）**全部转绿** "
        "⇒ 证明 §E12.1-③ 的定性正确（那是采样窗竞态，不是 GPU 不可用），根因修有效。裁定 89.5-1 已验收、P0 关闭",
        "冷启动交付（**权威**；`docs/infra-gpu-render.md` §0.3 指向本件）"),
    "COLDSTART_EVIDENCE_v2.json": (
        "**历史件，禁止当权威引用**：同五阶段，但 `baseline` 臂是**假红**（`tooth_proven=false`）—— "
        "根因 = `e_gpu_egl_verify.py` 旧采样逻辑「先 `sleep(1.0)` 再看 `proc.poll()`」，而该次渲染子进程 `wall_s=1.001` "
        "就退了 ⇒ 采样窗为空 ⇒「没采到」被读成「没有 fd / 整机没占用」。**原字节按 append-only 保留**"
        "（它是「反向牙咬到自己件」这一事实的唯一实证，也是竞态定位到行号的依据）",
        "历史取证（**禁止当权威**；替代件 = `_v3`）"),
    "COLDSTART_EVIDENCE.json": (
        "**v1 历史件，禁止当权威引用**：`fs_of()` 还没区分「镜像只读层」与「运行期可写层」⇒ "
        "`survives_container_rebuild` 标得不够准（E 自曝，D 裁定 87.1-3 采信并要求 v2 另落新名）。"
        "**原字节保留不动**",
        "历史取证（**禁止当权威**；替代件 = `_v3`）"),
    "PERSIST_MANIFEST_v3.json": (
        "**权威持久化清单**：NFS 前缀 34 个 `.so` 的逐文件 sha + 每条路径的 `rebuild_class` 分层"
        "（`nfs` / `overlay_image_baked` / `overlay_runtime_upper`）⇒ 重启后「什么会活下来、什么会死」的机器可读答案。"
        "v2 → v3 的差别只在生成时刻与同批负载读数（前缀字节未变）",
        "冷启动交付（**权威**；②③④ 三项证据之一）"),
    "PERSIST_MANIFEST_v2.json": ("**历史件**（v2 那轮的持久化清单，D 的 checkpoint §19.0-2 曾引用其 sha）；"
                                 "原字节保留", "历史取证（替代件 = `_v3`）"),
    "COLDSTART_EVIDENCE_relinktooth_": (
        "**`exit 5` 修法的验证件（只跑 `relink` 一个阶段，纯 CPU、未触卡）**：`tooth_relink` 的断言从 `exit_zero` 改为 "
        "**`exit_partial_5`（精确等值、不是放宽）**后实测 `tooth_proven=true`、三条断言全 `ok`、"
        "`boundary_clean_no_system_write=true`、`c4_gl_renderer_measured=false`（**如实标「没测」**）。"
        "顶层 `delivery_status=PARTIAL` / `all_teeth_proven=PARTIAL` / **exit 5** —— 因为只跑了一个阶段，"
        "这正是裁定 87.1-2「部分交付不得携带整体交付的布尔」的**正确行为**，不是缺陷。"
        "**它不取代 v3**：v3 仍是唯一权威件（五阶段全跑、`COLDSTART_VERIFIED`）",
        "牙证明（exit 5 修法；**不得**当冷启动交付引用）"),
    "PERSIST_MANIFEST_relinktooth_": (
        "上件的伴随持久化清单（同一轮 `relink`-only 运行产生）。**权威清单仍是 `PERSIST_MANIFEST_v3.json`**",
        "牙证明伴随件（**不得**当权威清单引用）"),
    "PERSIST_MANIFEST.json": ("**v1 历史件**（`fs_of()` 未分层的那一版）；原字节保留",
                             "历史取证（替代件 = `_v3`）"),
    "gate_mutation/GATE_MUTATION_SELFTEST_": (
        "**两侧牙的独立自证件（`scripts/e_selfcheck_gate_mutation.py`）**：M1–M5 五个变异体、"
        "`verdict_set_crosscheck=GREEN`、`two_sided_proof_present=true`、**全程不触卡**（纯 CPU 沙箱）。"
        "M1 = 全 rep 跳过必须红（咬 `e_render_determinism.py` 的第四道闸）、M2 = osmesa 真测量必须绿、"
        "M5 = 冷启动 mutant 臂必须红。**这是「闸有牙」的证明，不是测量件**",
        "牙证明（**不得**当冷启动或确定性数据引用）"),
    "gate_mutation/MUT_M1_all_reps_skipped_": (
        "**M1 变异体产物**：把 5 个 rep 全造成为 `skipped` ⇒ 闸必须判 `not_measured_*` + `exit 4`（不得给平凡真）",
        "牙证明（负向）"),
    "gate_mutation/MUT_M2_osmesa_measured_": (
        "**M2 变异体产物（`must_stay_green` 臂）**：真有测量时闸必须仍绿 ⇒ 证明第四道闸不是「一律红」",
        "牙证明（正向）"),
    "gate_mutation/M5_coldstart_mutant/": (
        "**M5 的沙箱工作区**：坏 ICD 副本 + 其子进程 stdout/stderr/自证件。**真前缀一个字节未碰**",
        "牙证明（沙箱）"),
    "gate_mutation/selfcheck_egl_nvidia_": (
        "变异体自检过程中跑出的自证件（`scripts/e_activate_selfcheck.py` 的产物）；"
        "**属于牙证明链，不是主线取证**",
        "牙证明（明细）"),
    "gate_mutation/selfcheck_osmesa_": ("同上（osmesa 臂，纯 CPU）", "牙证明（明细）"),
    "baseline_real_prefix/": (
        "**真前缀臂（= 反向牙 `must_stay_green`）的逐次原始输出**：冷启动子进程的 stdout（`COLDSTART_OK …`）、"
        "stderr（C1–C4 四步的逐步文案）、以及 C4 那份独立子进程自证件。"
        "`*_021854.json` = v2 那轮（假红，采样窗为空）；`*_030234.json` = v3 那轮（8 条判据全过）"
        "⇒ **两份并排留档，正是「竞态」这个定性的可核证据**",
        "取证明细（权威臂的原始输出）"),
    "mutant_broken_icd/": (
        "**坏 ICD 臂（= 正向牙，裁定 85.9-3-3：静默回退必须响亮失败）的逐次原始输出**：沙箱副本里把 "
        "`10_nvidia.json` 指向不存在的库 ⇒ 实测冷启动 exit 1、`verdict=fail`、`render_probe.ok=false`"
        "（mujoco 在 `MUJOCO_GL=egl` 下**直接抛 ImportError，没有静默退回 osmesa**）、`child_nvidia_fds=[]`。"
        "`*_021853.json` = v2 轮、`*_030233.json` = v3 轮",
        "取证明细（正向牙；**不触卡**）"),
    "sandbox_prefix/": ("**沙箱坏 ICD 本体**（`10_nvidia.json` 指向不存在的库）。真前缀不在本目录、未被改动",
                       "牙用沙箱（禁止当真实前缀引用）"),
    "sandbox_prefix/": ("**沙箱坏 ICD 本体**：唯一真文件是 `10_nvidia.json`（385 B，指向一个**不存在**的库路径）；"
                       "其余 33 个 `lib*.so*` 都是**指回真实 NFS 前缀的符号链接**（沙箱只改 ICD、不复制 339 MB 的库）。"
                       "**真前缀 `/…/.codex-persist/egl-libs/590.48.01` 一个字节未碰**"
                       "（每件产物的 `boundary_guard_*` 均 `system_render_lib_hits=[]` 为证）",
                       "牙用沙箱（禁止当真实前缀引用）"),
    "relink/": ("**`relink` 阶段的沙箱工作目录，本轮为空目录**。这是**实测事实、不是遗漏**："
               "`tooth_relink` 的证据**不落在这里**，而在 `COLDSTART_EVIDENCE*.json` 的 `tooth_relink` 字段里"
               "（`gate=venv_symlink_auto_rebuild`、`state_before`、`exit_code`、C2 的 stderr 原文）。"
               "**两臂见证**：v1 的 C2 输出 `**已重建** …/sandbox_root_venvs/pi05_sim -> …/envs/pi05_sim`"
               "（`state_before` = 「不存在」）；v2/v3 的 C2 输出 `已存在且指向正确（未改动）`"
               "（`state_before` = 真 venv 本体路径）⇒ **既能真建、也幂等不破坏正确链接**",
               "牙用沙箱（空目录 = 实测事实；证据在 EVIDENCE 件的 `tooth_relink`）"),
    "sandbox_root_venvs/": ("**relink 牙的沙箱 `/root/venvs` 副本**（在沙箱里真删真建，**不动本机 `/root`**）。"
                           "内含一个符号链接 `pi05_sim -> /…/.codex-persist/envs/pi05_sim`（= C2 重建出来的那一环）",
                           "牙用沙箱（禁止当真实 venv 引用）"),
    "cpu_dryrun/": ("**上卡前的 CPU 预演（第 1 轮）**：只跑 `manifest,chain,relink,mutant` 四个纯 CPU 阶段，"
                   "确认脚本形状与 mutant 臂不触卡（`child_nvidia_fds=[]`）⇒ 把上卡时间压到 ≈1 s。"
                   "**不是交付件**", "预演（禁止当交付引用）"),
    "cpu_dryrun2/": ("**上卡前的 CPU 预演（第 2 轮）**：同上，用于验「强化后的 mutant 牙（4 条腿）」与 "
                    "`--manifest-name` 拒绝覆写闸。**不是交付件**", "预演（禁止当交付引用）"),
    "before_images/": ("**本目录 MANIFEST 原地重写前自动留的字节前像**（裁定 83.5 / `OVERWRITE_EVENT_20260929_2345.md`）",
                      "前像（可复原重写前的字节）"),
    "MANIFEST.json": ("本清单", "索引"),
}


def describe(rel: str, name: str) -> tuple[str, str]:
    best, desc, scope = -1, "(未登记)", "unlisted_引用前须核对"
    for prefix, (d, sc) in DESC.items():
        if rel.startswith(prefix) or name.startswith(prefix) or name == prefix:
            if len(prefix) > best:
                best, desc, scope = len(prefix), d, sc
    return desc, scope


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--no-before-image", action="store_true",
                    help="**默认会留前像**；本旗标只用于目录里确实还没有 MANIFEST.json 的首次生成（此时无前像可留）")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"out_dir 不存在: {out_dir}"}, ensure_ascii=False))
        return 2
    target = out_dir / "MANIFEST.json"
    before_path = None
    if target.exists():
        if args.no_before_image:
            print(json.dumps({"ok": False, "error": "MANIFEST.json 已存在，拒绝原地重写而不留前像（裁定 83.5）；"
                                                    "去掉 --no-before-image"}, ensure_ascii=False))
            return 3
        bdir = out_dir / "before_images"
        bdir.mkdir(parents=True, exist_ok=True)
        before_path = bdir / f"MANIFEST.json.before{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(target, before_path)

    rows: dict[str, dict] = {}
    n_symlink, n_empty_dir, hashed_bytes = 0, 0, 0
    # **`followlinks=False` 是硬要求**：本目录的沙箱前缀里有 33 个指回真实 NFS 前缀（339 MB）的符号链接，
    # 跟随它们会把**目录外的文件**登记成本轮产物（= 清单说谎），并且每次重生成多读 ~1 GB。
    for root, dirs, files in os.walk(out_dir, followlinks=False):
        root_p = Path(root)
        for name in sorted(files):
            f = root_p / name
            rel = f.relative_to(out_dir).as_posix()
            if before_path is not None and os.path.abspath(f) == os.path.abspath(before_path):
                continue  # 本轮刚留的前像不自我引用；下一轮重生成时会正常登记
            desc, scope = describe(rel, name)
            lst = f.lstat()
            base = {"mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(lst.st_mtime)),
                    "desc": desc, "scope": scope}
            if f.is_symlink():
                tgt = os.readlink(f)
                base.update({"kind": "symlink", "link_target": tgt,
                             "link_target_exists": os.path.exists(f),
                             "bytes": None, "sha256_12": None,
                             "why_no_sha": ("符号链接的身份 = 它的目标路径，不是目标内容；"
                                            "对目标内容取 sha 会把**目录外**的文件冒充成本轮产物")})
                n_symlink += 1
            else:
                h = hashlib.sha256()
                with open(f, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                hashed_bytes += lst.st_size
                with open(f, "rb") as fh:
                    n_lines = sum(1 for _ in fh)
                base.update({"kind": "file", "bytes": lst.st_size, "n_lines": n_lines,
                             "sha256_12": h.hexdigest()[:12]})
            rows[rel] = base
        for d in sorted(dirs):
            dp = root_p / d
            rel_d = dp.relative_to(out_dir).as_posix()
            if dp.is_symlink():
                # **指向目录的符号链接也要登记**（`sandbox_root_venvs/pi05_sim` 正是 `tooth_relink` 的产物），
                # 但**不进去**（它的内容属于目标目录，不是本轮产物）。
                desc, scope = describe(rel_d, d)
                lst = dp.lstat()
                rows[rel_d] = {
                    "kind": "symlink_to_dir", "link_target": os.readlink(dp),
                    "link_target_exists": os.path.exists(dp),
                    "bytes": None, "sha256_12": None,
                    "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(lst.st_mtime)),
                    "desc": desc, "scope": scope,
                    "why_not_descended": "内容属于目标目录（真实 venv 本体），不是本轮产物；跟随它 = 清单说谎",
                }
                n_symlink += 1
                continue
            rel = rel_d + "/"
            if any(os.scandir(dp)):
                continue  # 非空目录由它自己的内容登记
            desc, scope = describe(rel, d + "/")
            rows[rel] = {"kind": "empty_dir", "bytes": 0, "sha256_12": None,
                         "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(dp.lstat().st_mtime)),
                         "desc": desc, "scope": scope,
                         "note": "空目录也登记 —— 否则「逐文件用途」对它是静默的（缺陷类 ⑩ 的同型）"}
            n_empty_dir += 1

    unlisted = sorted(k for k, v in rows.items() if v["scope"].startswith("unlisted"))
    if not rows:
        print(json.dumps({"ok": False, "error": "目录为空 ⇒ 不生成清单（裁定 88.3-2：空集上不许给出通过形状的产物）",
                          "n_files": None, "out_dir": str(out_dir)}, ensure_ascii=False))
        return 4

    man = {
        "manifest": str(target),
        "agent": "E",
        "task": "T-E-EGL-COLDSTART（P0 冷启动重启保险）：① 一条命令 ② 持久化清单 ③ 牙 ④ 重启后什么会活下来",
        "task_order": ("裁定 85.9-3（P0 指派）→ 87.1（部分验收 + 四条后续）→ 88.5-3（重跑 baseline）→ "
                       "**89.5-1（完整交付、P0 关闭）**；执行单 `rl_harness_supervision/d_handoff_to_e_20260929.md`"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "generator": {"file": "scripts/e_coldstart_manifest.py",
                      "sha256_12": (hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12])},
        "authoritative_version": {
            "evidence": "COLDSTART_EVIDENCE_v3.json", "persist_manifest": "PERSIST_MANIFEST_v3.json",
            "delivery_status": "COLDSTART_VERIFIED", "exit_code": 0,
            "why_not_v1_v2": ("v1 的 `fs_of()` 未区分镜像只读层/运行期可写层；v2 的 `baseline` 臂是采样窗竞态造成的**假红**。"
                              "两者原字节保留、仅作历史"),
        },
        "one_command_recovery": ("env -i /bin/bash "
                                 f"{REPO}/scripts/e_coldstart_gpu_render.sh"),
        "boundary": ("prefix-only：**零系统写入**（不 `ldconfig`、不写 `/usr/share`、不 apt/dpkg、"
                     "不改 `NVIDIA_DRIVER_CAPABILITIES`）；渲染库全在 NFS 前缀 "
                     "`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01`。"
                     "每件产物的 `boundary_guard_before`/`boundary_guard_after` 均 `ok=true`、"
                     "`forbidden_paths_present=[]`、`system_render_lib_hits=[]`；"
                     "`/usr/share/glvnd/egl_vendor.d` 跑前跑后都只有 `50_mesa.json`"),
        "authoritative_criterion": ("**`exit code`**（裁定 89.5-1 / §89.8：checkpoint §19.0-3 的临时判据"
                                    "「看 GL_RENDERER 不看 exit code」已按其自身可推翻条件退役）。"
                                    "防自相矛盾的硬规则见 `docs/infra-gpu-render.md` §0.3 末行"),
        "load": "每件产物同批带 `loadavg` + `nr_throttled`（cgroup `cpu.stat`）；GPU 用量按裁定 85.7 申报/销账",
        "notes": {
            "regeneration": ("MANIFEST.json 是**可重生成件**（每次 `--manifest-only` 语义原地重写）。"
                             "**重写前本脚本自动留前像到 `before_images/`**，无需人工 `cp -p`（裁定 83.5）"),
            "self_sha_caveat": ("本清单**无法登记自己的最终 sha**：`rows` 在写盘前采集，"
                                "所以 `files['MANIFEST.json'].sha256_12` 恒为**上一版**的字节身份。"
                                "按 `citation_sha_as_of_discipline`，引用本清单的 sha 一律**由引用方重算**，不得采信该行"),
            "no_unlisted_gate": ("**有任何文件落到 `(未登记)` ⇒ exit 3、不写盘**：清单有洞就不是清单。"
                                 "本轮 `n_unlisted` 见下"),
        },
        "n_files": len(rows),
        "n_unlisted": len(unlisted),
        "unlisted_files": unlisted,
        "enumeration": {
            "followlinks": False,
            "n_rows": len(rows), "n_real_files": len(rows) - n_symlink - n_empty_dir,
            "n_symlinks": n_symlink, "n_empty_dirs": n_empty_dir,
            "hashed_bytes": hashed_bytes,
            "why_not_rglob": ("`Path.rglob('*')` + `is_file()` **会跟随符号链接** ⇒ 本目录 3 个沙箱前缀里的 "
                              "33×3 个指回真实 NFS 前缀的 `.so` 会被当成产物登记（实测上一版就是这样：170 行、"
                              "其中 99 行是目录外的库、读盘 ~1 GB）。改用 `os.walk(followlinks=False)` 后 "
                              "只登记**本目录自己的字节**，符号链接按链接登记"),
        },
        "before_image": str(before_path) if before_path else None,
        "files": rows,
    }
    if unlisted:
        print(json.dumps({"ok": False, "error": "清单有洞：以下文件无用途登记 ⇒ 拒绝写盘",
                          "n_unlisted": len(unlisted), "unlisted_files": unlisted}, ensure_ascii=False))
        return 3
    target.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "manifest": str(target), "n_files": len(rows), "n_unlisted": 0,
                      "before_image": str(before_path) if before_path else None,
                      "sha256_12": hashlib.sha256(target.read_bytes()).hexdigest()[:12],
                      "n_lines": sum(1 for _ in open(target, encoding="utf-8"))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
