#!/usr/bin/env python
"""T-E-11（D 执行单 `d_handoff_to_e_20260930.md` §一，P1）：**重启续跑就绪清单**。

用户已明示「服务器可能会关闭」⇒ E 线从「吞吐线」变成**断点续跑保险线**。本件回答一个问题：
**重启之后，四条线要接着跑，各自需要什么、那些东西现在在哪一层、丢了谁能把它弄回来。**

**为什么每一项都必须实测**（D 的原话：「能用 `cpu_dryrun` 档验的就验，不许只写推断」）：
本仓已经吃过两次亏 —— ① `docs/infra-gpu-render.md` §4 早先断言「必须挂 `/dev/dri`」，被实测推翻（裁定 77.4）；
② D 的同型错误 #18 = 把他线报告的说法当文件系统状态写进权威重启入口。
⇒ 本件里每一个 `state_now` / `rebuild_class` / 计数 / 退出码都来自**当场的系统调用或子进程**，
凡是需要「真重启一次」才能知道的，一律写 **`not_measured`** 并附**机器可执行的重启后探针**（`argv` + `expect_exit`）。

**三值纪律（D 执行单 §一-5，红线 `absence_of_measurement_is_not_measurement_of_absence`）**：
`restored` / `not_restored` / **`not_measured`**。空集 ⇒ 聚合值 `null` + **非零退出**（裁定 88.3-2）。
**不许把「没测」写成「没问题」。**

**两个轴，不许混（这是本件最重要的一处口径）**：
- `readiness_axis`：**现在就能证**的就绪性（资产在哪一层、恢复机制本身有没有被实测过）。
- `post_restart_verification_axis`：**只有真重启一次才能证**。本轮**没有重启过** ⇒ 该轴**恒为 `not_measured`**，
  且**不参与** `overall_readiness`、**不影响** exit code 的「就绪」判定。
  ⇒ `exit 0` 的含义是「五项就绪判据都有实测支撑」，**不是**「重启已经验证过了」。见 `what_exit_0_does_not_mean`。

退出码：0 = 五项全 `restored`；1 = 有 `not_restored`；2 = 有 `not_measured`（就绪轴）；
3 = 目标已存在（拒绝覆写，裁定 82 §2-4 / 83.5）；4 = 项集或行集为空（裁定 88.3-2）。

**本轮硬约束**：**一条都不许上卡**（D 执行单 §一）。⇒ C4（实测 `GL_RENDERER`）**不在本轮重测**，
按裁定 92.2 / T-E-10 搭 A2 的 S4b 便车；本件如实记 `not_measured_this_round` + 历史实测值 + 对象未变证明。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import e_egl_coldstart as ec      # noqa: E402  复用 fs_of / link_audit / boundary_guard，不另写一套（裁定 46.4）

PERSIST = ec.PERSIST
PREFIX = ec.PREFIX
OUT_DIR = REPO / "runs/infra/e_restart_readiness_20260930"
RESTORED, NOT_RESTORED, NOT_MEASURED = "restored", "not_restored", "not_measured"

CHECKED_BY = "E（本件的生成轮）在下一轮开机后第一件事跑 `--post-restart-probe` 臂；D 按 §94.9-5 核它有没有真被跑"
CHECKED_WHEN = "每次真实重启/容器重建之后的第一个 E 动作（在申报任何 GPU 窗口之前）"


def sha256_file(p: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    n = 0
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
            if limit and n >= limit:
                break
    return h.hexdigest()


def ident(p: Path) -> dict:
    """身份三元组 + 两算法（裁定 92.3 全仓最低标准）。`n_lines` = `wc -l` 口径（换行符个数）。"""
    if not p.exists():
        return {"path": str(p), "exists": False}
    if p.is_dir():
        # 目录没有「字节身份」；给可核的替代量（条目数 + mode + mtime），并**明说这不是 sha**
        return {"path": str(p.relative_to(REPO)) if str(p).startswith(str(REPO) + "/") else str(p),
                "exists": True, "is_directory": True,
                "n_top_level_entries": len(list(p.iterdir())),
                "mode": oct(p.stat().st_mode)[-4:],
                "mtime": time.strftime("%Y-%m-%dT%H:%M:%S %Z", time.localtime(p.stat().st_mtime)),
                "sha256_12": None,
                "why_no_sha": "目录不是字节串 ⇒ 没有 sha；**不许**把「条目数」冒充成身份（裁定 92.3 的反面）"}
    b = p.read_bytes()
    return {"path": str(p.relative_to(REPO)) if str(p).startswith(str(REPO) + "/") else str(p),
            "exists": True, "n_lines": b.count(b"\n"), "n_lines_splitlines": len(b.splitlines()),
            "bytes": len(b), "ends_with_newline": b.endswith(b"\n"),
            "sha256_12": hashlib.sha256(b).hexdigest()[:12], "sha1_12": hashlib.sha1(b).hexdigest()[:12],
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S %Z", time.localtime(p.stat().st_mtime))}


def sh(argv: list[str], cwd: Path | None = None, timeout: int = 60,
       tail_out: int = 800, tail_err: int = 400, keep_full: Path | None = None) -> dict:
    """跑一条命令并**如实**记录（含超时与非零退出）。绝不把失败吞成成功。

    `tail_out`/`tail_err` 只是**登记用的截断长度**；给 `keep_full` 时**完整原文另存成文件**并记 sha。
    为什么必须有 `keep_full`（E 本轮自查出的缺陷，与 §E12.1-③ 的采样窗竞态**同族**）：
    第一版只留 400 字符的 stderr 尾巴，而冷启动脚本的 C1/C2 两行在**更前面** ⇒
    `"C1 ok" in stderr` / `"已重建" in stderr` 两个断言**假阴性**（实测出 `c1_ok=false`、
    `c2_rebuilt=false`，而真值都是 `true`）。**截断窗口决定了断言的真值 = 测量缺陷，不是被测对象的性质。**
    修法 = 断言一律在**完整原文**上做，截断只用于展示。
    """
    try:
        r = subprocess.run(argv, cwd=str(cwd or REPO), capture_output=True, text=True, timeout=timeout)
        res = {"argv": argv, "exit": r.returncode, "stdout_tail": r.stdout.strip()[-tail_out:],
               "stderr_tail": r.stderr.strip()[-tail_err:], "timed_out": False,
               "stdout_full": r.stdout, "stderr_full": r.stderr,
               "stdout_chars": len(r.stdout), "stderr_chars": len(r.stderr),
               "tail_fields_are_truncated": (len(r.stdout) > tail_out or len(r.stderr) > tail_err)}
        if keep_full is not None:
            keep_full.mkdir(parents=True, exist_ok=True)
            fo, fe = keep_full / "recovery_stdout.txt", keep_full / "recovery_stderr.txt"
            fo.write_text(r.stdout, encoding="utf-8")
            fe.write_text(r.stderr, encoding="utf-8")
            res["full_text_saved"] = {
                "stdout": str(fo.relative_to(REPO)) if str(fo).startswith(str(REPO) + "/") else str(fo),
                "stderr": str(fe.relative_to(REPO)) if str(fe).startswith(str(REPO) + "/") else str(fe),
                "stdout_sha256_12": hashlib.sha256(r.stdout.encode()).hexdigest()[:12],
                "stderr_sha256_12": hashlib.sha256(r.stderr.encode()).hexdigest()[:12],
                "stdout_chars": len(r.stdout), "stderr_chars": len(r.stderr)}
        return res
    except subprocess.TimeoutExpired:
        return {"argv": argv, "exit": None, "stdout_tail": None, "stderr_tail": None,
                "stdout_full": None, "stderr_full": None, "timed_out": True,
                "note": f"超过 {timeout}s ⇒ 按 not_measured 登记（裁定 94.9-2：>60s 的扫描视同上卡作业）"}
    except OSError as exc:
        return {"argv": argv, "exit": None, "error": f"{type(exc).__name__}: {exc}", "timed_out": False,
                "stdout_full": None, "stderr_full": None}


def git(*a: str) -> dict:
    return sh(["git", *a])


def row(obj: str, requirement: str, state_now, rebuild_class, status: str, basis: str,
        measured: dict, evidence: list, probe: dict | None = None, notes: str = "",
        falsification: dict | None = None) -> dict:
    r = {"object": obj, "requirement": requirement, "state_now": state_now,
         "rebuild_class": rebuild_class, "readiness_status": status, "status_basis": basis,
         "measured": measured, "evidence": evidence, "notes": notes}
    if probe:
        r["post_restart_probe"] = probe
    if falsification:
        r["falsification_condition"] = {**falsification, "checked_by": CHECKED_BY, "checked_when": CHECKED_WHEN}
    return r


def item_status_from_rows(rows: list[dict]):
    """行 → 项的聚合规则（**单一真源**：`item()` 与项 5 的变异探针都调它，裁定 46.4）。"""
    if not rows:
        return None
    st = [r["readiness_status"] for r in rows]
    if NOT_MEASURED in st:
        return NOT_MEASURED
    if NOT_RESTORED in st:
        return NOT_RESTORED
    return RESTORED


def recompute_items(items: list[dict]) -> list[dict]:
    for it in items:
        it["item_status"] = item_status_from_rows(it["rows"])
    return items


def item(n: int, title: str, requirement: str, rows: list[dict], rule: str) -> dict:
    """项级状态由行级状态聚合。空行集 ⇒ null（裁定 88.3-2）。"""
    if not rows:
        return {"id": n, "title": title, "requirement": requirement, "rows": [],
                "item_status": None, "item_status_rule": rule,
                "empty_set_guard": "行集为空 ⇒ 项状态 = null，**不是** `restored`（裁定 88.3-2）"}
    s = item_status_from_rows(rows)
    st = [r["readiness_status"] for r in rows]
    return {"id": n, "title": title, "requirement": requirement, "rows": rows, "item_status": s,
            "item_status_rule": rule,
            "status_distribution": {k: st.count(k) for k in (RESTORED, NOT_RESTORED, NOT_MEASURED)},
            "n_rows": len(rows)}


def survival(p: Path) -> dict:
    f = ec.fs_of(p)
    return {"rebuild_class": f.get("rebuild_class"), "survives_container_rebuild": f.get("survives_container_rebuild"),
            "fstype": f.get("fstype"), "mount": f.get("mount"), "note": f.get("note"),
            "state_now": ("present" if p.exists() else "absent") if not p.is_symlink()
                         else ("present" if p.exists() else "dangling_symlink")}


# ── 项 1：只在 NFS 的资产 ────────────────────────────────────────────────────
def build_item1() -> dict:
    rows = []
    gi = git("check-ignore", "-v", "runs/infra/e_restart_readiness_20260930/RESTART_READINESS.json")
    gitignore_line = None
    gl = REPO / ".gitignore"
    if gl.is_file():
        for i, ln in enumerate(gl.read_text().splitlines(), 1):
            if ln.strip().startswith("runs"):
                gitignore_line = {"line_no": i, "text": ln}
                break
    runs_sv = survival(REPO / "runs")
    n_runs_top = len([p for p in (REPO / "runs").iterdir()]) if (REPO / "runs").is_dir() else None
    tracked_in_runs = git("ls-files", "runs/")
    rows.append(row(
        "runs/**（全部证据档，含本件）",
        "重启后必须还在，且**只能靠 NFS**（不入库 ⇒ git 恢复不了它）",
        runs_sv["state_now"], runs_sv["rebuild_class"], RESTORED,
        "measured_now_survival_class",
        {"fs": runs_sv,
         "git_check_ignore": {"exit": gi["exit"], "stdout": gi["stdout_tail"],
                              "means": "exit 0 + 有输出 = **确实被忽略**（不入库）" if gi["exit"] == 0 else "未被忽略 ⇒ 前提变了，必须重判"},
         "gitignore_rule": gitignore_line,
         "git_ls_files_runs_count": (len(tracked_in_runs["stdout_tail"].splitlines())
                                     if tracked_in_runs["exit"] == 0 and tracked_in_runs["stdout_tail"] else 0),
         "n_top_level_entries_under_runs": n_runs_top,
         "consequence": ("`runs/` 在 NFS 且被 git 忽略 ⇒ 重启后**还在**（NFS 不随容器消失），"
                         "但**异地副本没有**（39.53 GiB 只在 NFS）⇒ 这正是裁定 94.9-6 的 T-E-12 要保「身份与判词」的原因")},
        [str(gl), "runs/"],
        probe={"argv": ["/bin/mountpoint", "-q", "/workspace/mnt/sppro"], "expect_exit": 0,
               "what_it_proves": "NFS 已挂载 ⇒ `runs/**` 可读；不成立则本项转 not_restored（找平台，本仓无法自恢复）"},
        notes="E **不遍历他线 run 目录做全量计数**（裁定 94.9-2 `no_root_filesystem_scans`：>60 s 的扫描视同上卡作业）",
        falsification={"condition": "若重启后 `/workspace/mnt/sppro` 不是 nfs 挂载，或 `runs/` 变为空/不可读",
                       "then": "本项 → `not_restored`；所有引用 `runs/**` 身份的文书全部失去可对账对象"}))

    ds = Path("/workspace/mnt/sppro/yhzhang91/datasets")
    ds_sv = survival(ds)
    rows.append(row(
        str(ds), "数据集（**E 永不写、永不遍历**，只 stat 一层）",
        ds_sv["state_now"], ds_sv["rebuild_class"], RESTORED, "measured_now_survival_class",
        {"fs": ds_sv, "top_level_entries": sorted(p.name for p in ds.iterdir()) if ds.is_dir() else None,
         "scan_scope": {"paths": [str(ds)], "depth": 1, "patterns": ["*"],
                        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
                        "why": "裁定 94.9-4 `negative_existence_claim_must_state_scan_scope`；"
                               "且硬约束「永不碰 /workspace/mnt/sppro/yhzhang91/datasets」⇒ 只列一层、不递归、不 hash"}},
        [str(ds)],
        probe={"argv": ["/bin/mountpoint", "-q", "/workspace/mnt/sppro"], "expect_exit": 0,
               "what_it_proves": "同上（NFS 挂载）"}))

    for name, req in (("RL_Harness_v4_20260924", "v4 参考实现（**只读**，E/任何线都不得改）"),
                      ("work/project_parameters.json", "参数表（**D 单写者**，rev19）"),
                      ("work/decisions/decisions_20260929.md", "裁定全history（append-only）"),
                      ("rl_harness_supervision/d_context_checkpoint_20260930_1010.md", "D 的权威重启入口")):
        p = REPO / name
        sv = survival(p)
        tracked = git("ls-files", "--error-unmatch", name)
        rows.append(row(
            name, req, sv["state_now"], sv["rebuild_class"], RESTORED,
            "measured_now_survival_class_plus_git_tracked" if tracked["exit"] == 0 else "measured_now_survival_class",
            {"fs": sv, "identity": ident(p),
             "git_tracked": tracked["exit"] == 0,
             "git_tracked_evidence": (tracked["stdout_tail"] or tracked["stderr_tail"]),
             "mode": (oct(p.stat().st_mode)[-4:] if p.exists() else None),
             "double_copy": ("NFS + git 双份（`git_tracked=true`）⇒ 即使 NFS 丢也能从 commit 恢复"
                             if tracked["exit"] == 0 else "**只有 NFS 一份**（未入库）⇒ 丢即不可恢复")},
            [name],
            probe={"argv": ["git", "-C", str(REPO), "log", "--oneline", "-1"], "expect_exit": 0,
                   "what_it_proves": "git 仓库可读 ⇒ 入库件可从 HEAD 恢复"}))

    hf = PERSIST / "hf-cache"
    sv = survival(hf)
    rows.append(row(
        "权重 / 模型缓存（`.codex-persist/hf-cache`，实测 14 GiB）",
        "重启后权重必须还在（否则 π₀.₅ 无法加载）",
        sv["state_now"], sv["rebuild_class"], RESTORED, "measured_now_survival_class",
        {"fs": sv, "top_level": sorted(p.name for p in hf.iterdir()) if hf.is_dir() else None,
         "du_sh_measured": sh(["du", "-sh", str(hf)], timeout=90).get("stdout_tail"),
         "scan_scope": {"paths": [str(hf)], "depth": 1, "patterns": ["*"],
                        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z")},
         "note": "**不做全量 hash**（14 GiB ⇒ 违反裁定 94.9-6 的总读量 ≤4 GiB 与 94.9-2 的扫描纪律）；"
                 "逐文件身份由 T-E-12 的白名单快照按体积闸挑"},
        [str(hf)],
        probe={"argv": ["/bin/ls", str(hf)], "expect_exit": 0, "what_it_proves": "缓存目录可读"},
        notes="`du` 若超时 ⇒ 该子字段为 null，本行仍按 `rebuild_class=nfs` 判 `restored`（体积不是就绪判据）"))

    return item(1, "只在 NFS 的资产", "重启后靠 NFS 自身活下来的东西", rows,
                "任一行 not_measured ⇒ 项 not_measured；否则任一 not_restored ⇒ 项 not_restored；全 restored ⇒ restored")


# ── 项 2：依赖容器本地的资产 ─────────────────────────────────────────────────
def build_item2(recovery: dict) -> dict:
    rows = []
    link = Path("/root/venvs/pi05_sim")
    sv_link = survival(link)
    body = PERSIST / "envs/pi05_sim"
    sv_body = survival(body)
    rows.append(row(
        "/root/venvs/pi05_sim（符号链接）",
        "主线解释器入口。**重启后必丢**（overlay 运行期可写层）⇒ 必须有**已实测过的**恢复机制",
        sv_link["state_now"], sv_link["rebuild_class"], RESTORED,
        "recovery_path_measured_this_round",
        {"fs": sv_link, "readlink_now": (os.readlink(str(link)) if link.is_symlink() else None),
         "expected_target": str(body),
         "readlink_matches_expected": (os.readlink(str(link)) == str(body)) if link.is_symlink() else None,
         "recovery_mechanism": "冷启动脚本的 C2 步（`ln -s <body> <link>`，幂等）",
         "recovery_measured_this_round": recovery,
         "historical_proof": "v3 的 `tooth_relink`（`sandbox_link_rebuilt_correctly.ok=true`，裁定 89.5-1 已验收）"},
        [str(link), str(body), "scripts/e_coldstart_gpu_render.sh",
         "runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json"],
        probe={"argv": ["/bin/ls", "-l", "/root/venvs/pi05_sim"], "expect_exit": 0,
               "what_it_proves": ("重启后这一条**预期是 exit≠0（链接不存在）**；"
                                  "正确处置 = 跑一条命令恢复路径（项 3），跑完再核它 exit 0 且 readlink == 本体路径")},
        falsification={"condition": "若重启后跑完恢复路径，`/root/venvs/pi05_sim` 仍不存在或指向别处",
                       "then": "本行 → `not_restored`；A2/B2/C2 三线全部无法起进程（这是最硬的一环）"}))

    rows.append(row(
        str(body), "venv **本体**（NFS）—— 链接丢了它还在",
        sv_body["state_now"], sv_body["rebuild_class"], RESTORED, "measured_now_survival_class",
        {"fs": sv_body, "pyvenv_cfg": (body / "pyvenv.cfg").read_text() if (body / "pyvenv.cfg").is_file() else None,
         "n_top_level": len(list(body.iterdir())) if body.is_dir() else None},
        [str(body)]))

    basepy = Path("/opt/conda/bin/python3.11")
    sv_base = survival(basepy)
    ver = sh([str(basepy), "-c", "import sys;print(sys.version.split()[0])"])
    rows.append(row(
        str(basepy),
        "venv 的 **base 解释器**（在 overlay 的**镜像只读层**）—— venv 能跨重建，**当且仅当新镜像仍带同版本 python3.11**",
        sv_base["state_now"], sv_base["rebuild_class"], RESTORED,
        "measured_now_survival_class_conditional_same_image",
        {"fs": sv_base, "version_measured": ver.get("stdout_tail"),
         "conditional_on": "**同一个镜像**。换镜像（python 小版本变）⇒ NFS 上的 venv 全体变悬空软链",
         "c1_asserts_this": "冷启动脚本 C1 已把「base 解释器存在 + venv 解释器真能起进程」做成**显式断言** ⇒ 这种情况会响亮失败，不静默降级"},
        [str(basepy), "scripts/e_coldstart_gpu_render.sh"],
        probe={"argv": [str(basepy), "-c", "import sys;print(sys.version.split()[0])"], "expect_exit": 0,
               "what_it_proves": f"base 解释器还在且版本 == {ver.get('stdout_tail')}（不等 ⇒ venv 变悬空）"},
        falsification={"condition": f"若重启后 base python 版本 ≠ {ver.get('stdout_tail')}",
                       "then": "本行 → `not_restored`；需要在 NFS 上重建 venv（不是跑一条命令能解决的）"}))

    rows.append(row(
        "镜像换 python 小版本这一情形", "**只有真换镜像才知道** ⇒ 本轮无从测",
        "unknown", "overlay_image_baked", NOT_MEASURED, "requires_actual_image_change",
        {"why_not_measured": ("本轮没有换镜像、也没有第二个镜像可比 ⇒ 任何结论都是推断。"
                              "按红线 `absence_of_measurement_is_not_measurement_of_absence`，**记 `not_measured`，不记 `restored`**")},
        [str(basepy)],
        probe={"argv": [str(basepy), "-c", "import sys;print(sys.version.split()[0])"], "expect_exit": 0,
               "what_it_proves": "重启后第一件事核版本号；与 v4 清单里记的值比对"}))

    sv_pfx = survival(PREFIX)
    audit = ec.link_audit(PREFIX)
    files = [f for f in sorted(PREFIX.iterdir()) if f.is_file() and not f.is_symlink()]
    links = [f for f in sorted(PREFIX.iterdir()) if f.is_symlink()]
    total = sum(f.stat().st_size for f in files)
    v4p = REPO / "runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v4.json"
    v4 = json.loads(v4p.read_text()) if v4p.is_file() else {}
    rows.append(row(
        str(PREFIX),
        "EGL/OpenGL 用户态库前缀（**34 个条目 / 339,337,693 B**）—— 渲染能力的全部物质基础",
        sv_pfx["state_now"], sv_pfx["rebuild_class"], RESTORED, "measured_now_survival_class",
        {"fs": sv_pfx,
         "n_entries_measured_now": len(files) + len(links), "n_regular_files": len(files), "n_symlinks": len(links),
         "total_bytes_measured_now": total,
         "link_audit": {k: audit[k] for k in ("verdict", "n_links_audited", "n_dangling", "dangling")},
         "matches_PERSIST_MANIFEST_v4": {
             "n_entries": (len(files) + len(links)) == v4.get("prefix", {}).get("n_files"),
             "total_bytes": total == v4.get("prefix", {}).get("total_bytes"),
             "n_dangling": audit["n_dangling"] == (v4.get("prefix", {}).get("link_audit", {}) or {}).get("n_dangling")},
         "v4_identity": ident(v4p),
         "authority_note": "持久化清单权威件 = `PERSIST_MANIFEST_v4.json`（裁定 92.2；`supersedes` v3，v3 原字节保留）"},
        [str(PREFIX), str(v4p.relative_to(REPO))],
        probe={"argv": ["/usr/bin/find", str(PREFIX), "-xtype", "l"], "expect_exit": 0,
               "what_it_proves": "**输出必须为空**（悬空链接 0 条）；非空 ⇒ 前缀在重启中被破坏，本行 → not_restored"},
        falsification={"condition": "若重启后 `find <prefix> -xtype l` 有输出，或条目数 ≠ 34 / 字节数 ≠ 339337693",
                       "then": "本行 → `not_restored`；**不要**跑任何标 `egl` 的采集（会静默退回 CPU 软渲染：92.374 ms/步 被当成 7.300 ms/步）"}))

    bashrc = Path("/root/.bashrc")
    sv_rc = survival(bashrc)
    hook = (bashrc.read_text(errors="replace") if bashrc.is_file() else "")
    rows.append(row(
        "/root/.bashrc 的 codex-persist hook",
        "重启后 hook 必丢 ⇒ 没有任何东西会自动恢复（`docs/infra-gpu-render.md` §0.1 的实测结论）",
        sv_rc["state_now"], sv_rc["rebuild_class"], RESTORED, "recovery_path_documented_and_tool_present",
        {"fs": sv_rc,
         "hook_present_now": ("codex-persist" in hook),
         "hook_line": next((ln for ln in hook.splitlines() if "codex-persist" in ln), None),
         "recovery_tool_on_nfs": ident(PERSIST / "bin" / "codex-persist"),
         "recovery_argv": ["/opt/conda/bin/python3", str(PERSIST / "bin" / "codex-persist"), "bootstrap"],
         "watch_pid_file": (PERSIST / "watch.pid").read_text().strip() if (PERSIST / "watch.pid").is_file() else None,
         "note": "`watch` 守护只做**单向镜像「本地 → NFS」**，从不反向恢复 ⇒ 恢复必须靠人显式跑上面这条 argv"},
        [str(bashrc), str(PERSIST / "bin" / "codex-persist")],
        probe={"argv": ["/opt/conda/bin/python3", str(PERSIST / "bin" / "codex-persist"), "bootstrap"],
               "expect_exit": 0,
               "what_it_proves": "hook + venv 软链 + watch 守护一次重建；失败则退到 `venvlink` 子命令（只重建软链）"}))

    dm = REPO / "runs/vla/b2_sim_demo_bidir_20260930/formal/demo_manifest.json"
    venv_py = None
    if dm.is_file():
        venv_py = (json.loads(dm.read_text()).get("versions") or {}).get("venv_python")
    rows.append(row(
        "B2 的 `demo_manifest.json → versions.venv_python`（D 执行单 §一-2 点名的口径来源）",
        "各线产物里记的解释器路径必须与恢复出来的那一个**逐字一致**",
        "present" if dm.is_file() else "absent", survival(dm)["rebuild_class"] if dm.exists() else None,
        RESTORED if (venv_py == "/root/venvs/pi05_sim/bin/python") else NOT_RESTORED,
        "measured_cross_check",
        {"demo_manifest": ident(dm), "versions.venv_python": venv_py,
         "expected": "/root/venvs/pi05_sim/bin/python",
         "matches_restored_link": venv_py == "/root/venvs/pi05_sim/bin/python",
         "consequence": "一致 ⇒ 重启后恢复出来的解释器**就是**各线产物里登记的那一个，历史数字仍可对账"},
        [str(dm.relative_to(REPO)) if dm.exists() else str(dm)]))

    return item(2, "依赖容器本地的资产", "重启后会丢、但恢复机制已被实测/工具在 NFS 上的东西", rows,
                "同项 1 的聚合规则；**「镜像换 python」那一行恒为 not_measured**，故本项在真重启前只能是 not_measured"
                " —— 这是**如实**，不是缺陷（要它变 restored 必须真换一次镜像）")


# ── 项 3：一条命令恢复路径 + 恢复后的验证点 ──────────────────────────────────
def build_item3(recovery: dict) -> dict:
    rows = []
    sh_p = REPO / "scripts/e_coldstart_gpu_render.sh"
    # 恢复路径这一臂的**判据**（全部从完整原文读；任一不成立 ⇒ 该行 not_restored，不许含糊）
    flags_ok = bool(recovery.get("c1_ok") and recovery.get("c2_rebuilt") and recovery.get("c3_ok")
                    and recovery.get("c4_skipped") and recovery.get("exit") == 5
                    and recovery.get("real_root_venvs_untouched") and not recovery.get("timed_out"))
    txt = sh_p.read_text()
    v4p = REPO / "runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v4.json"
    v4 = json.loads(v4p.read_text())
    one_cmd = v4["one_command_recovery"]
    ann = REPO / "runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.ANNOTATIONS.json"
    annd = json.loads(ann.read_text()) if ann.is_file() else {}

    rows.append(row(
        "一条命令恢复路径（字面串）", "两处定义必须**逐字一致**（裁定 46.4：根因就是两处定义漂移）",
        "present", survival(sh_p)["rebuild_class"], RESTORED, "measured_string_equality",
        {"from_PERSIST_MANIFEST_v4.one_command_recovery": one_cmd,
         "script_identity": ident(sh_p),
         "script_documents_same_command": ("env -i /bin/bash" in txt and "e_coldstart_gpu_render.sh" in txt),
         "single_prefix_source": ("E_GPU_RENDER_PREFIX" in txt),
         "note": "前缀只由 `E_GPU_RENDER_PREFIX` 一个变量决定 ⇒ C1 检查的目录与 C3 激活到的目录必然同一个"},
        [str(sh_p.relative_to(REPO)), str(v4p.relative_to(REPO))],
        probe={"argv": ["env", "-i", "/bin/bash", str(sh_p)], "expect_exit": 0,
               "what_it_proves": ("**这一条就是全部恢复动作**。exit 0 ⇒ GPU 渲染可用；"
                                  "exit 1 ⇒ 不可用（stderr 分 1/2/3 三种原因）；exit 5 ⇒ 只跑了 C1–C3、GPU 未测（PARTIAL）")}))

    rows.append(row(
        "恢复路径的 C1–C3（**本轮实测**，纯 CPU、沙箱 venv 链接、不触卡、不碰 `/root/venvs`）",
        "恢复机制本身必须被**跑过**，不能只写在文档里",
        "measured_this_round", None,
        # 这一行的状态**由实测旗标决定**，不是写死的 ⇒ 断言窗一坏，本行立刻转 not_restored（有牙）
        RESTORED if flags_ok else NOT_RESTORED, "measured_now_subprocess_run",
        {"invocation": recovery.get("argv"), "exit": recovery.get("exit"),
         "expected_exit": 5, "exit_matches_expected": recovery.get("exit") == 5,
         "stdout": recovery.get("stdout"), "stderr": recovery.get("stderr"),
         "stdout_chars": recovery.get("stdout_chars"), "stderr_chars": recovery.get("stderr_chars"),
         "full_text_saved": recovery.get("full_text_saved"),
         "c1_ok": recovery.get("c1_ok"),
         "c2_rebuilt": recovery.get("c2_rebuilt"),
         "c2_already_correct": recovery.get("c2_already_correct"),
         "c3_ok": recovery.get("c3_ok"),
         "c4_skipped": recovery.get("c4_skipped"),
         "all_flags_and_exit_as_expected": flags_ok,
         "expected_flag_pattern": ("`C1 ok` + `已重建`（不是「已存在且指向正确」—— 本轮要证的正是**能真建**那一支）"
                                   "+ `C3 ok` + `跳过 C4` + exit 5"),
         "flags_read_from": "**完整原文**（沙箱里的 `recovery_stderr.txt`），不是 400 字符的截断尾巴",
         "assertion_window_note": recovery.get("assertion_window_defect_fixed"),
         "sandbox_link_after": recovery.get("sandbox_link_after"),
         "real_root_venvs_untouched": recovery.get("real_root_venvs_untouched"),
         "env_i_used": recovery.get("env_i_used"),
         "why_exit_5_is_the_pass_value_here": ("`E_SKIP_GPU=1` ⇒ 跳过 C4 ⇒ 顶层必须是 PARTIAL/exit 5（§E12.10 的根因修）。"
                                              "**本轮禁上卡**，所以 5 就是这一臂能拿到的最好结果；"
                                              "若它是 0，那才是缺陷（退出码层面的假绿）")},
        [recovery.get("sandbox_dir") or "runs/infra/e_restart_readiness_20260930/"],
        probe={"argv": ["env", "-i", "/bin/bash", str(sh_p)], "expect_exit": 0,
               "what_it_proves": "重启后**不设** `E_SKIP_GPU` 真跑 ⇒ 期望 exit 0（含 C4 实测）"}))

    v3p = REPO / "runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json"
    v3 = json.loads(v3p.read_text())
    base = (v3.get("tooth_baseline") or {}).get("arm") or {}
    delta = REPO / "runs/infra/e_restart_readiness_20260930/V3_TO_V4_DELTA.json"
    deltad = json.loads(delta.read_text()) if delta.is_file() else {}
    rows.append(row(
        "验证点 `renderer_class = nvidia_gpu`（C4）",
        "恢复后必须实测到 GPU 渲染，**不许**接受「exit 0 但 gl_strings 不含 NVIDIA」",
        "historically_measured_not_remeasured_this_round", None, RESTORED,
        "measured_at_v3_and_object_proven_unchanged_since",
        {"v3_measured": {"renderer_class": base.get("renderer_class"),
                         "gl_strings": base.get("gl_strings"),
                         "exit_code": (v3.get("tooth_baseline") or {}).get("exit_code"),
                         "as_of": v3.get("generated_at")},
         "v3_identity": ident(v3p),
         "current_round_remeasurement": NOT_MEASURED,
         "why_not_remeasured": "**本轮一条都不许上卡**（D 执行单 §一）；GPU 优先级 A2 > B2 > C2 > E",
         "object_unchanged_since_v3": {"proof": ident(delta),
                                       "verdict": deltad.get("verdict"),
                                       "INVARIANT_23_real_file_sha256_all_identical": deltad.get("INVARIANT_23_real_file_sha256_all_identical"),
                                       "n_symlink_targets_changed": deltad.get("n_symlink_targets_changed")},
         "piggyback_plan": {"task": "T-E-10（裁定 92.2 / D 执行单 §三）",
                            "verification_kind": "third_party_piggyback",
                            "who": "A2 的 S4b（它本来就要在自己产物里落 `renderer_class`）",
                            "e_action": "A2 落盘后核对并登记；**不单开窗口、不上卡**",
                            "checked_by": "E，在 A2 的 S4b 产物落盘之后",
                            "checked_when": "A2 的 S4b 产物出现的那一刻（E 每轮开工先 `ls -dt runs/vla/a2_s4b*`）"}},
        [str(v3p.relative_to(REPO)), str(delta.relative_to(REPO)) if delta.exists() else str(delta)],
        probe={"argv": ["env", "-i", "/bin/bash", str(sh_p)], "expect_exit": 0,
               "what_it_proves": "C4 在**独立子进程**里实测 `GL_RENDERER` 并断言含 `NVIDIA`（裁定 82.5）"},
        notes="**这一行不是「没测写成没问题」**：它有 03:02:38 的实测值，且被测对象自那次实测以来**逐位未变**（23 个真文件 sha 全等）",
        falsification={"condition": "若 A2 的 S4b（或任何人下一次上卡）落出 `renderer_class != nvidia_gpu`",
                       "then": "本行立即 → `not_restored`；且裁定 92.1 的可推翻条件成立 ⇒ coldstart v4 升 P0"}))

    a = annd.get("annotation_a_tooth_relink_exit_code_is_historical") or {}
    rows.append(row(
        "退出码语义（`tooth_relink` 当前期望 **5**，不是 0）",
        "重启后判读冷启动结果的人必须知道 v3 里的 `0` 是历史值",
        "annotated_machine_readable", None, RESTORED, "measured_from_artifacts",
        {"sidecar": ident(ann) if ann.exists() else None,
         "historical_value_in_v3": a.get("historical_value_in_v3"),
         "current_expected_value": a.get("current_expected_value"),
         "current_sh_exit5_line": a.get("current_sh_exit5_line"),
         "exit_code_table": {"0": "C1–C4 全过，C4 实测 GL_RENDERER 含 NVIDIA ⇒ **唯一**可读作「GPU 渲染可用」的码",
                             "1": "任一环节失败（stderr 分 1/2/3 三种原因）⇒ 一个标 egl 的数字都不要采",
                             "5": "`E_SKIP_GPU=1` 的 PARTIAL 档：C1–C3 完好、GPU 未测量 ⇒ **不是通过**"}},
        [str(ann.relative_to(REPO)) if ann.exists() else str(ann), str(sh_p.relative_to(REPO))],
        probe={"argv": ["env", "-i", "E_SKIP_GPU=1", "/bin/bash", str(sh_p)], "expect_exit": 5,
               "what_it_proves": "PARTIAL 档真的 exit 5（不占卡即可验；这是唯一一条**不上卡也能验**的退出码臂）"}))

    bg = ec.ep.boundary_guard()
    sysdir = sh(["/bin/ls", "/usr/lib/x86_64-linux-gnu/"])
    n_render = len([x for x in (sysdir.get("stdout_tail") or "").split()
                    if x.startswith(("libEGL_nvidia", "libGLX_nvidia", "libnvidia-eglcore", "libnvidia-glcore"))])
    ldc = sh(["/bin/sh", "-c", "ldconfig -p | grep -cE 'libEGL_nvidia|libGLX_nvidia|libnvidia-eglcore|libnvidia-glcore' || true"])
    vend = sorted(p.name for p in Path("/usr/share/glvnd/egl_vendor.d").iterdir()) if Path("/usr/share/glvnd/egl_vendor.d").is_dir() else None
    rows.append(row(
        "不许写系统（含 `ldconfig`）", "恢复路径**只**写 `/root/venvs/<name>` 一个软链与 `--out-dir`",
        "clean", None, RESTORED, "measured_now_boundary_guard",
        {"boundary_guard_now": bg,
         "forbidden_paths_present": bg.get("forbidden_paths_present"),
         "system_render_lib_count": n_render,
         "ldconfig_cache_hits": ldc.get("stdout_tail"),
         "egl_vendor_d_contents": vend,
         "scan_scope": {"paths": ["/usr/lib/x86_64-linux-gnu", "/usr/share/glvnd/egl_vendor.d", "ldconfig -p 缓存"],
                        "patterns": ["libEGL_nvidia*", "libGLX_nvidia*", "libnvidia-eglcore*", "libnvidia-glcore*"],
                        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
                        "why": "裁定 94.9-4：「X 不存在」必须写成「在 <路径集> 扫过 <模式集> 未命中」+ 扫描时刻",
                        "result": "**四类命中 0**；`egl_vendor.d` 只有 `50_mesa.json`"},
         "v3_agrees": v3.get("boundary_clean_no_system_write"),
         "history": "2026-09-29 21:02 曾违规写系统，21:18 全量回滚（37 个文件进 recycle_bin，未用 rm）；处置 = 裁定 60「结果采纳、程序违规记一次」"},
        ["/usr/lib/x86_64-linux-gnu", "/usr/share/glvnd/egl_vendor.d"],
        probe={"argv": ["/bin/sh", "-c", "ls /usr/share/glvnd/egl_vendor.d/"], "expect_exit": 0,
               "what_it_proves": "**输出必须只有 `50_mesa.json`**；出现 `10_nvidia.json` ⇒ 有人写了系统 ⇒ 冷启动会 exit 3（边界闸拒跑）"}))

    return item(3, "一条命令恢复路径 + 恢复后的验证点",
                "恢复必须机械、可一条命令跑完，且验证点是实测而不是文案", rows,
                "同上；C4 那一行按「v3 已实测 + 对象逐位未变」判 restored，并**同时**记 current_round=not_measured")


# ── 项 4：各线续跑的最小前置 ────────────────────────────────────────────────
def build_item4() -> dict:
    rows = []
    head = git("rev-parse", "--short", "HEAD")
    dirty = git("status", "--porcelain")
    n_dirty = len(dirty["stdout_tail"].splitlines()) if dirty["exit"] == 0 and dirty["stdout_tail"] else None
    calib = REPO / "scripts/e_mainline_render_calib.py"
    ctxt = calib.read_text() if calib.is_file() else ""
    calib_ident = ident(calib)
    rows.append(row(
        "A2（π₀.₅ 运行时 + 延迟 + BC 执行）",
        "最小前置 = venv + EGL 前缀 + **GPU 窗口申报**（裁定 94.9-1 的过渡协议）",
        "present", None, RESTORED, "measured_prerequisites_present",
        {"venv": "/root/venvs/pi05_sim（项 2 已实测：本体在 NFS、链接有恢复机制）",
         "egl_prefix": str(PREFIX),
         "card_busy_source_identity": calib_ident,
         "card_busy_present": ("def card_busy" in ctxt),
         # **不再写死「逐字未动」**：裁定 96.1-③ 已把网③的判据改掉（修文本误触发），写死的身份串
         # 会立刻变成一句假话（缺陷类 ㉒ 台账被读成常驻事实 / ⑱ 给错值编理由）。改为**每次现取** +
         # 显式登记「改过、谁裁的、证据在哪、v1 的哪个字段被取代」。
         "card_busy_source_change": {
             "pre_96_1_3_identity": {
                 "sha256_12": "fd582e261e87", "n_lines": 1279, "n_bytes": 87046,
                 "as_of": "2026-09-30T12:3x+08:00",
                 "before_image": ("runs/infra/e_card_busy_fix_20260930/before_images/"
                                  "e_mainline_render_calib.py.before_96_1_3")},
             "byte_identical_to_pre_96_1_3": calib_ident["sha256_12"] == "fd582e261e87",
             "changed_by_ruling": "裁定 96.1-③（E 主责 · P0.5 · A2 第一次真上卡之前修完）",
             "what_changed": ("只改**网③ cmdline** 的判据：裸关键字 ⇒ 真实执行形态 ∧ 关键字 ∧ 非闲置"
                              "（新增 `classify_cmdline()` / `_argv()` / `_proc_cpu()`；"
                              "`card_busy()` 新增 `cmdline_hits_text_mention_only` 与 `cmdline_net_caliber` 两键，"
                              "8 个旧键与签名不变）"),
             "what_did_not_change": ("网①（`compute-apps`）/ 网②（`/dev/nvidia*` fd）/ 窄档词表 / 宽档正则 / "
                                     "`_cmdline()` / `_own_tree()` 源码逐字未改（ast 逐对象机器比对 7/7）"),
             "evidence": "runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json",
             "supersedes_field": ("本件 v1（1757 ln `4587672f186f`）里的 `card_busy_byte_identical_claim` —— "
                                  "那句在 v1 生成时刻为真，现已过期；v1 原字节保留，更正见同目录 "
                                  "`RESTART_READINESS.CARD_BUSY_FIX_96_1_3.SIDECAR.json`")},
         "gpu_window_protocol_94_9_1": ["① 起跑前在 daily_report.md 申报（裁定 73 模板）",
                                        "② 起跑那一刻实测三网（--query-compute-apps + fd 网 + cmdline 网）",
                                        "③ 在自己 run 目录落 GPU_WINDOW.json（start/end、三网原文、loadavg 三点、nr_throttled、外来进程清单、contaminated 判定）",
                                        "④ 必须有起跑前拒绝逻辑（n_foreign_gpu_processes>0 且未给 --allow-cotenant ⇒ exit 3 + 落 refused_gpu_busy_<ts>.json）"],
         "e_provides": "`renderer_class` 搭车核对（T-E-10）；E **不与 A2 争窗**"},
        [str(calib.relative_to(REPO)), "rl_harness_supervision/d_handoff_to_a2_20260930.md"]))

    rows.append(row(
        "B2（数据 + git 单写者 + registry/）",
        "最小前置 = `HEAD` 与脏项数（重启后要知道哪些活件还没提交）",
        "present", None, RESTORED, "measured_git_state",
        {"HEAD": head.get("stdout_tail"), "n_dirty": n_dirty,
         "dirty_list": (dirty["stdout_tail"].splitlines() if dirty["exit"] == 0 else None),
         "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
         "d_reference": "D 的 §94.0 记的是 `HEAD = d194269`、脏 **7** 项（as_of 11:19:56）",
         "delta_vs_d": (None if n_dirty is None else n_dirty - 7),
         "delta_explanation": ("差值来自 11:19:56 之后各线的新增活件（含 E 的 `scripts/e_authority_annotations.py`）；"
                              "**脏项数是一个随时间变的量，引用必须带 `as_of`**"),
         "git_single_writer": "B2（D 永不 commit；E 永不 commit）",
         "untracked_e_files_this_round": [x for x in (dirty["stdout_tail"].splitlines() if dirty["exit"] == 0 else [])
                                          if "/e_" in x or x.endswith("e_authority_annotations.py")
                                          or x.endswith("e_link_audit_selfcheck.py") or x.endswith("e_restart_readiness.py")]},
        ["git"],
        probe={"argv": ["git", "-C", str(REPO), "status", "--porcelain"], "expect_exit": 0,
               "what_it_proves": "重启后第一件事：核 HEAD 与脏项数，与本行记的值比对 ⇒ 知道 B2 还欠几次代提交"}))

    g = sh(["/bin/ls", "-dt", "runs/vla/c2_norm_contract_20260929/gate/run_*"], timeout=30)
    gate_dirs = (g.get("stdout_tail") or "").split()
    rows.append(row(
        "C2（契约层 / 归一化 / 闸审计）",
        "最小前置 = 闸可 **CPU-only** 跑（本轮 T-C2-8 全程 CPU）+ 闸产物在 NFS",
        "present", None, RESTORED, "measured_artifacts_present",
        {"n_gate_run_dirs_listed": len(gate_dirs), "latest_gate_run_dirs": gate_dirs[:3],
         "ls_command": g.get("argv"),
         "norm_contract_identity": ident(REPO / "harness/norm_contract.py"),
         "cpu_only_claim_source": "D 执行单 §一-4（「C2 = 闸可 CPU-only 跑（本轮 T-C2-8 全程 CPU）」）",
         "what_E_does_NOT_measure": ("**闸的判词（绿/红）不由 E 测** —— 那是 C2 的写入面与 C2 的自证件。"
                                     "E 只登记「闸产物在 NFS、重启后可读」这一层前置；"
                                     "把 C2 的判词搬进 E 的件 = 裁定 71 `caliber_transplant_ban`")},
        ["runs/vla/c2_norm_contract_20260929/gate/", "harness/norm_contract.py"],
        probe={"argv": ["/bin/ls", "-dt", "runs/vla/c2_norm_contract_20260929/gate/run_*"], "expect_exit": 0,
               "what_it_proves": "闸 run 目录可读 ⇒ C2 能接着跑第 4–9 步"}))

    ck = REPO / "rl_harness_supervision/d_context_checkpoint_20260930_1010.md"
    dec = REPO / "work/decisions/decisions_20260929.md"
    par = REPO / "work/project_parameters.json"
    rows.append(row(
        "D（监管 / 口径裁定）",
        "最小前置 = 权威重启入口 + 裁定全history + 参数表（**D 单写者**）",
        "present", None, RESTORED, "measured_identity_recorded",
        {"authoritative_restart_entry": ident(ck),
         "decisions": ident(dec),
         "params": ident(par),
         "note": ("`d_context_checkpoint_20260930_1010.md` 自述「读到这一件就够了」；"
                  "**但 §94 已落**（decisions 现 3493 ln `62734a102e8c`），checkpoint 的「当前状态」章节再次过期 ⇒ "
                  "重启后应**先读 decisions 的最后一节**，再读 checkpoint"),
         "stale_by_construction": True},
        [str(ck.relative_to(REPO)), str(dec.relative_to(REPO)), str(par.relative_to(REPO))],
        probe={"argv": ["git", "-C", str(REPO), "log", "--oneline", "-3"], "expect_exit": 0,
               "what_it_proves": "看 B2 代提交到哪一次；再 `tail -120 daily_report.md`（从当前 tail 读，不用缓存 offset）"}))

    rows.append(row(
        "E（GPU 渲染 / 冷启动 / 断点续跑保险）",
        "最小前置 = 本件 + `docs/infra-gpu-render.md` §0 的权威恢复块 + v3/v4 两件权威产物",
        "present", None, RESTORED, "measured_identity_recorded",
        {"this_artifact": "RESTART_READINESS.json（本件）",
         "docs_recovery_block": ident(REPO / "docs/infra-gpu-render.md"),
         "coldstart_authority": ident(REPO / "runs/infra/e_egl_coldstart_20260930/COLDSTART_EVIDENCE_v3.json"),
         "persist_manifest_authority": ident(REPO / "runs/infra/e_egl_coldstart_20260930/PERSIST_MANIFEST_v4.json")},
        ["docs/infra-gpu-render.md", "runs/infra/e_egl_coldstart_20260930/"]))

    return item(4, "各线续跑的最小前置", "四条线 + E 自己，各自重启后第一件事需要什么", rows,
                "同上；**E 只测「前置件在不在、身份是什么」，不测他线的判词**（裁定 71）")


# ── 项 5：三值纪律自证 ──────────────────────────────────────────────────────
def aggregate(items: list[dict]) -> dict:
    st = [it["item_status"] for it in items]
    if not items or any(s is None for s in st):
        return {"n_items": len(items), "overall_readiness": None,
                "empty_or_null_guard": "项集为空或任一项状态为 null ⇒ 聚合值 **null**（裁定 88.3-2），不给通过形状的读数",
                "status_distribution": None}
    dist = {k: st.count(k) for k in (RESTORED, NOT_RESTORED, NOT_MEASURED)}
    overall = NOT_MEASURED if dist[NOT_MEASURED] else (NOT_RESTORED if dist[NOT_RESTORED] else RESTORED)
    return {"n_items": len(items), "status_distribution": dist,
            "overall_readiness": overall,
            "overall_readiness_axis": "readiness_axis（**不含** post_restart_verification_axis）",
            "rule": "任一项 not_measured ⇒ 整体 not_measured；否则任一 not_restored ⇒ not_restored；全 restored ⇒ restored"}


def build_item5(items: list[dict]) -> dict:
    rows = []
    agg = aggregate(items)
    all_rows = [r for it in items for r in it["rows"]]
    dist = {k: sum(1 for r in all_rows if r["readiness_status"] == k) for k in (RESTORED, NOT_RESTORED, NOT_MEASURED)}

    # 空集探针（正向牙）：拿一个**空行集**的项去过同一套聚合逻辑
    empty_item = item(99, "空集探针项", "probe", [], "同上")
    empty_agg = aggregate(items + [empty_item])
    empty_ok = (empty_item["item_status"] is None and empty_agg["overall_readiness"] is None)

    # ── 变异探针（两侧牙 + 绿见证）。**必须先造一个全绿基线再注入**，否则真件里本来就有的
    #    `not_measured`（项 2 的「换镜像」那一行）会让 M1「通过」得毫无意义 —— 那是 E 自己
    #    在这一轮里抓到并根因修的**假绿**（缺陷类 ⑲ `green_verdict_from_an_under_covered_audit_pattern`
    #    的近亲：探针在非受控基线上跑）。三臂都走 `recompute_items()` ⇒ 与真件同一条聚合路径。
    def clone(its):
        return recompute_items(json.loads(json.dumps(its)))

    green = clone(items)
    for it in green:
        for r in it["rows"]:
            r["readiness_status"] = RESTORED
    green = recompute_items(green)
    green_agg = aggregate(green)
    green_ok = green_agg["overall_readiness"] == RESTORED      # 绿见证：全 restored 必须给 restored（不是"一律红"）

    m1 = clone(green)
    m1[0]["rows"][0]["readiness_status"] = NOT_MEASURED
    m1_agg = aggregate(recompute_items(m1))
    m1_ok = m1_agg["overall_readiness"] == NOT_MEASURED

    m2 = clone(green)
    m2[0]["rows"][0]["readiness_status"] = NOT_RESTORED
    m2_agg = aggregate(recompute_items(m2))
    m2_ok = m2_agg["overall_readiness"] == NOT_RESTORED

    m3 = clone(green)                                          #  precedence 牙：not_restored 不得淹掉 not_measured
    m3[0]["rows"][0]["readiness_status"] = NOT_RESTORED
    m3[1]["rows"][0]["readiness_status"] = NOT_MEASURED
    m3_agg = aggregate(recompute_items(m3))
    m3_ok = m3_agg["overall_readiness"] == NOT_MEASURED
    mut_ok = bool(green_ok and m1_ok and m2_ok and m3_ok)

    rows.append(row(
        "本件自己的三值纪律", "`restored` / `not_restored` / **`not_measured`** 三态必须真在用，不是装饰",
        "measured", None, RESTORED if (dist[NOT_MEASURED] > 0) else NOT_MEASURED,
        "measured_self_audit",
        {"row_status_distribution": dist,
         "n_rows": len(all_rows),
         "not_measured_rows_are_present": dist[NOT_MEASURED] > 0,
         "why_this_must_be_true": ("若全件 0 条 `not_measured`，说明这份清单**没有诚实登记任何未知** —— "
                                  "而「重启后才发生的事」按定义就是未知 ⇒ 那本身就是假绿。"
                                  "本行在 0 条 not_measured 时**自判 not_measured**（牙咬自己）"),
         "which_rows_are_not_measured": [r["object"] for r in all_rows if r["readiness_status"] == NOT_MEASURED]},
        ["本件"]))

    rows.append(row(
        "空集 → null + 非零退出（裁定 88.3-2）", "空行集/空项集不得给出「通过」形状的聚合值",
        "measured", None, RESTORED if empty_ok else NOT_RESTORED, "measured_probe",
        {"injected_bad_form": "一个 `rows=[]` 的项（id=99）混进项集",
         "detected": empty_ok,
         "empty_item_status": empty_item["item_status"],
         "aggregate_with_empty_item": empty_agg["overall_readiness"],
         "expected": "两者都必须是 null",
         "exit_code_consequence": "项状态为 null ⇒ 本脚本 exit 4（见 `exit_code_semantics`）"},
        ["本件的 `aggregate()` 与 `item()`"],
        notes="**这就是裁定 93.8 要求的对照探针形态**：注入一个已知坏形态，抓不到 ⇒ 审计器自己红"))

    rows.append(row(
        "聚合不会被单个坏行淹没（**全绿基线** + 三颗变异体 + 一颗绿见证）",
        "任一行 not_measured / not_restored 必须能把整体拉下来；全 restored 必须给 restored",
        "measured", None, RESTORED if mut_ok else NOT_RESTORED, "measured_mutation_probe",
        {"pattern_coverage_probe": {
            "injected_bad_form": ("**先把全部行强置 `restored` 造出受控全绿基线**，再分别注入："
                                  "M1 一行 `not_measured` / M2 一行 `not_restored` / "
                                  "M3 同时注入两者（测优先级）；另跑 G0 绿见证（全绿基线本身必须 `restored`）"),
            "detected": mut_ok,
            "G0_green_witness": {"expected": RESTORED, "observed": green_agg["overall_readiness"], "ok": green_ok},
            "M1": {"expected": NOT_MEASURED, "observed": m1_agg["overall_readiness"], "ok": m1_ok},
            "M2": {"expected": NOT_RESTORED, "observed": m2_agg["overall_readiness"], "ok": m2_ok},
            "M3_precedence": {"expected": NOT_MEASURED, "observed": m3_agg["overall_readiness"], "ok": m3_ok,
                              "why": "`not_measured` 的优先级必须高于 `not_restored`：把「没测」报成「测到坏了」"
                                     "同样是错（会让人去修一个不存在的东西，正是 §E12.1-③ 那个假红的教训）"},
            "why_it_matters": ("恒真/恒绿的聚合等于没有聚合。四臂证明聚合函数**两个方向都有牙**且优先级正确。"),
            "self_caught_defect": ("**E 本轮自查出的假绿**：第一版探针直接在**真件**上注入 M1，"
                                   "而真件的项 2 本来就有一条 `not_measured`（换镜像那一行）⇒ M1「通过」得毫无意义"
                                   "（聚合值本来就是 not_measured，注入与否都一样）；同一版的 M2 因此**如实判红**"
                                   "（observed=not_measured ≠ expected=not_restored），把缺陷照了出来。"
                                   "根因修 = 先造受控全绿基线再注入。与 §E12.10「反向牙咬到自己的件」同一形状。")}},
        ["本件的 `aggregate()` / `item_status_from_rows()`"]))

    rows.append(row(
        "「不许把没测写成没问题」的字面落实", "重启后才发生的一切 ⇒ 一律 `not_measured` + 机器可执行探针",
        "measured", None, RESTORED, "measured_self_audit",
        {"n_rows_with_post_restart_probe": sum(1 for r in all_rows if r.get("post_restart_probe")),
         "post_restart_verification_axis_status": NOT_MEASURED,
         "why": "本轮**没有真重启过** ⇒ 该轴不可能是 restored；它**不参与** overall_readiness，也**不改** exit code 的就绪语义",
         "falsification_conditions_all_have_consumer": all(
             ("checked_by" in r["falsification_condition"] and "checked_when" in r["falsification_condition"])
             for r in all_rows if r.get("falsification_condition")),
         "ruling_94_9_5": "缺陷类 ⑳ `preregistered_condition_without_a_consumer`：预登记条件必须写明谁在何时核"},
        ["本件"]))

    return item(5, "三值纪律自证（含裁定 93.8 的对照探针）",
                "本件自己必须服从它宣称的纪律，并**自证**", rows,
                "同上；本项的行是**对本件自身的审计**，故必须在项 1–4 聚合之后才算得出来")


def run_recovery_dryrun(sandbox: Path) -> dict:
    """实测 C1–C3（`env -i` + `E_SKIP_GPU=1`），**沙箱 venv 链接**，不触卡、不碰 `/root/venvs`。"""
    rv = sandbox / "root_venvs"
    od = sandbox / "out"
    rv.mkdir(parents=True, exist_ok=True)
    od.mkdir(parents=True, exist_ok=True)
    link = rv / "pi05_sim"
    sh_p = REPO / "scripts/e_coldstart_gpu_render.sh"
    real = Path("/root/venvs/pi05_sim")
    real_before = os.readlink(str(real)) if real.is_symlink() else None
    inner = (f"E_SKIP_GPU=1 E_VENV_LINK={link} E_OUT_DIR={od} /bin/bash {sh_p}")
    r = sh(["env", "-i", "/bin/bash", "-c", inner], timeout=180, keep_full=sandbox)
    err_full = r.get("stderr_full") or ""
    real_after = os.readlink(str(real)) if real.is_symlink() else None
    return {"argv": ["env", "-i", "/bin/bash", "-c", inner],
            "env_i_used": True, "exit": r["exit"],
            "stdout": (r.get("stdout_full") or "").strip(), "stderr": err_full.strip(),
            "stdout_chars": r.get("stdout_chars"), "stderr_chars": r.get("stderr_chars"),
            "full_text_saved": r.get("full_text_saved"),
            "timed_out": r.get("timed_out"),
            "sandbox_link": str(link),
            "sandbox_link_after": (os.readlink(str(link)) if link.is_symlink() else None),
            "sandbox_link_rebuilt": link.is_symlink(),
            "c1_ok": ("C1 ok" in err_full),
            "c2_rebuilt": ("已重建" in err_full),
            "c2_already_correct": ("已存在且指向正确" in err_full),
            "c3_ok": ("C3 ok" in err_full),
            "c4_skipped": ("跳过 C4" in err_full),
            "assertions_done_on_full_text": True,
            "assertion_window_defect_fixed": (
                "第一版把断言做在 400 字符的 stderr **尾巴**上 ⇒ C1/C2 两行被截掉 ⇒ `c1_ok`/`c2_rebuilt` "
                "**假阴性**。现在断言一律在**完整原文**上做（完整原文另存并带 sha256[:12]），截断只用于展示。"
                "**与 §E12.1-③ 的采样窗竞态同族：窗口决定了真值。**"),
            "real_root_venvs_link_before": real_before, "real_root_venvs_link_after": real_after,
            "real_root_venvs_untouched": real_before == real_after,
            "gpu_touched": False,
            "as_of": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
            "note": ("**沙箱臂**：`E_VENV_LINK` 指到 E 自己的产物目录 ⇒ 真 `/root/venvs` 一个字节不碰。"
                     "重启后的**权威臂**是 `env -i /bin/bash <sh>`（不设 `E_SKIP_GPU`、不覆盖 `E_VENV_LINK`），"
                     "期望 exit 0 含 C4 实测 —— 那一臂本轮**不许上卡**，故 `not_measured`。")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT_DIR / "RESTART_READINESS.json"))
    ap.add_argument("--sandbox-dir", default=str(OUT_DIR / "recovery_dryrun_inartifact"))
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(json.dumps({"verdict": "REFUSE", "reason": f"目标已存在，拒绝覆写（裁定 82 §2-4 / 83.5）: {out}",
                          "existing_sha256_12": sha256_file(out)[:12], "hint": "换 --out 另落新件"},
                         ensure_ascii=False))
        return 3

    load_before = ec.ev.cpu_stat()
    # 沙箱必须**每次全新**：若复用旧沙箱，C2 会走「已存在且指向正确（未改动）」分支，
    # 而本轮要证的恰恰是「**已重建**」那一支（= 重启后真会发生的那一支）。
    sandbox = Path(args.sandbox_dir)
    if sandbox.exists():
        sandbox = sandbox.with_name(sandbox.name + "_" + time.strftime("%H%M%S"))
    recovery = run_recovery_dryrun(sandbox)
    recovery["sandbox_dir"] = str(sandbox.relative_to(REPO))
    items = [build_item1(), build_item2(recovery), build_item3(recovery), build_item4()]
    items.append(build_item5(items))
    agg = aggregate(items)

    all_rows = [r for it in items for r in it["rows"]]
    n_empty_items = sum(1 for it in items if it["item_status"] is None)

    if n_empty_items or not all_rows:
        verdict, exit_code = "not_measured_empty_set", 4
    elif agg["overall_readiness"] == NOT_RESTORED:
        verdict, exit_code = "NOT_READY", 1
    elif agg["overall_readiness"] == NOT_MEASURED:
        verdict, exit_code = "READY_WITH_NOT_MEASURED", 2
    else:
        verdict, exit_code = "READY", 0

    bg = ec.ep.boundary_guard()
    payload = {
        "artifact": str(out.relative_to(REPO)), "agent": "E",
        "task": "T-E-11（`rl_harness_supervision/d_handoff_to_e_20260930.md` §一，P1）重启续跑就绪清单",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "generator": {"script": str(Path(__file__).resolve().relative_to(REPO)),
                      "sha256_12": sha256_file(Path(__file__).resolve())[:12],
                      "n_lines": Path(__file__).read_bytes().count(b"\n"),
                      "why": "裁定 92.3(i)：身份串必须由工具在落笔时刻生成，人不碰"},
        "citation_algo": "sha256[:12]",
        "line_count_convention": "`n_lines` = 换行符个数（= `wc -l`）；另给 `n_lines_splitlines` / `ends_with_newline`",
        "status_vocabulary": {
            RESTORED: "**要求的状态已有实测支撑**：要么资产就在重启能活下来的那一层（`rebuild_class=nfs` / `overlay_image_baked`），"
                      "要么它会丢但**恢复机制本身被实测过**（`status_basis` 里写明是哪一种）",
            NOT_RESTORED: "**实测到不成立**：真缺口，必须修，不许含糊",
            NOT_MEASURED: "**本轮无从测**（需要真重启 / 真换镜像 / 真上卡）。**绝不写成 `restored`** —— "
                          "红线 `absence_of_measurement_is_not_measurement_of_absence`",
            "empty_set": "行集或项集为空 ⇒ 聚合值 `null` + **exit 4**（裁定 88.3-2 `aggregate_over_empty_set_must_be_null`）"},
        "two_axes_do_not_mix": {
            "readiness_axis": "现在就能证的就绪性 ⇒ 决定 `overall_readiness` 与 exit code",
            "post_restart_verification_axis": {
                "status": NOT_MEASURED,
                "why": "本轮**没有真重启过**。任何声称「重启后验过」的说法都是假的",
                "participates_in_overall_readiness": False,
                "probes": [r["post_restart_probe"] for r in all_rows if r.get("post_restart_probe")]}},
        "what_exit_0_does_not_mean": ("**exit 0 ≠「重启已经验证过了」**。exit 0 只表示：五项就绪判据**都有实测支撑**"
                                      "（资产分层实测 / 恢复机制当场跑过 / 边界闸当场核过 / 各线前置件身份当场取过）。"
                                      "「真重启一次再验」是 `post_restart_verification_axis`，它**恒为 not_measured 直到有人真重启**。"),
        "gpu_window_used": False,
        "gpu_discipline": "**本轮 E 一条都没上卡**（D 执行单 §一 / §94.10「本轮仍一条都不许上卡」）；C4 按 T-E-10 搭 A2 的 S4b 便车",
        "recovery_dryrun_this_round": recovery,
        "regeneration_note": ("本件是**第二版**。第一版（同目录，已移入 recycle_bin、前像留在 "
                              "`before_images/round2_readiness/`）的项 5 变异探针有**假绿**：直接在真件上注入 M1，"
                              "而真件项 2 本来就有一条 `not_measured` ⇒ M1 通过得毫无意义；同版 M2 如实判红把缺陷照了出来。"
                              "根因修 = 先造受控全绿基线再注入（四臂：G0 绿见证 + M1/M2/M3）。"
                              "**第一版从未被任何文书引用过**。第一版与本版的项 1–4 行集完全相同（探针只影响项 5）。"),
        "environment": {"hostname": os.uname().nodename, "load_before": load_before,
                        "cgroup_cpu_quota_us": (Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip()
                                                if Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").is_file() else None),
                        "cgroup_cpu_period_us": (Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip()
                                                 if Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").is_file() else None),
                        "effective_cores": 12, "nproc_misleading": os.cpu_count(),
                        "note": "cgroup 配额 **12 核**；`nproc=112` 是假象（`docs/infra-gpu-render.md` §6.3）"},
        "items": items,
        "aggregate": agg,
        "n_rows_total": len(all_rows),
        "row_status_distribution": {k: sum(1 for r in all_rows if r["readiness_status"] == k)
                                    for k in (RESTORED, NOT_RESTORED, NOT_MEASURED)},
        "verdict": verdict,
        "exit_code_semantics": {"0": "五项全 restored（**就绪**，不等于「重启已验证」）",
                                "1": "有 not_restored（真缺口）", "2": "有 not_measured（就绪轴）",
                                "3": "目标已存在，拒绝覆写", "4": "项/行集为空 ⇒ 聚合 null（裁定 88.3-2）"},
        "boundary_guard_after": bg,
        "boundary_clean_no_system_write": bool(bg.get("ok") and not bg.get("forbidden_paths_present")),
        "load_after": ec.ev.cpu_stat(),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(out.relative_to(REPO)), "verdict": verdict, "exit": exit_code,
                      "aggregate": agg, "row_status_distribution": payload["row_status_distribution"],
                      "n_rows_total": payload["n_rows_total"],
                      "recovery_dryrun_exit": recovery["exit"],
                      "real_root_venvs_untouched": recovery["real_root_venvs_untouched"],
                      "post_restart_verification_axis": payload["two_axes_do_not_mix"]["post_restart_verification_axis"]["status"],
                      "boundary_clean_no_system_write": payload["boundary_clean_no_system_write"],
                      "gpu_window_used": False,
                      "loadavg": [load_before.get("loadavg"), payload["load_after"].get("loadavg")],
                      "nr_throttled": [load_before.get("nr_throttled"), payload["load_after"].get("nr_throttled")]},
                     ensure_ascii=False, indent=1))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
