#!/usr/bin/env python3
"""A2 / G0 验收 3 —— `pi05_sim` 持久 venv 的 env manifest（**复用 A 线口径，不另写一套**）。

D §2 G0 验收 3 原文：manifest **直接复用 A 的口径脚本** `scripts/a_env_manifest.py`，
`probe_kind=semantic` 那条纪律照办：**`import` 成功不算过，要版本号 + 安装来源**。
A 的脚本硬绑 `lerobot_act`/`lerobot_eval` 与 A 线断点（`NEW_LOCKS`/`SMOKE_DIR`/就绪闸 E1–E7），
直接跑会拿 A 的口径套 A2 的环境 ⇒ 这里 **import A 的 `probe_venv` / `parse_pyvenv_cfg` / `sha256` 复用口径**，
只换被探对象与断言集合。probe_kind 仍是 semantic（子进程真 import + 读 dist-info 路径）。

断言集合（A2 专属，每条都能红）：
  V1  `/root/venvs/pi05_sim` 是软链且指向 NFS 持久盘（§0-2：不许在 /root 下建 venv）
  V2  `pyvenv.cfg` 的 `include-system-site-packages = false`（与两套已验收 venv 同构）
  V3  **红线**：`torch.__version__` 逐字 == `2.6.0+cu124`（D §9.2-3）
  V4  `torchvision` == `0.21.0+cu124`、`torchcodec` == `0.10.0`（与 `lerobot_act` 逐项一致）
  V5  `transformers` 满足 π₀.₅ 的真实要求：**必须有 `transformers.models.siglip.check`**
      （D §9.1 的 `>=4.57.1` 是 `transformers-dep` 的下界，π₀.₅ 走的是 `pi` extra 的补丁分支，见 §9.1 更正）
  V6  `PaliGemmaForConditionalGeneration` 与 `PI05Policy` 可导入（G0 验收 1）
  V7  `gym_aloha` 可注册且 `AlohaTransferCube-v0` 的 spec 存在（G0 验收 2 的可构造部分）
  V8  `lerobot` == 0.4.4（与已验收两套一致；升级 = 换断点）
  V9  lock 文件存在且 pin 数与实装包数一致（防止 lock 是空的却报绿）
  V10 **裁定 48 的新红线**：transformers 的**身份 = git commit**（不是版本区间）。
      判据三条同时成立才算绿：① `direct_url.json` 的 `vcs_info.commit_id` 与 lock 里
      `transformers @ git+…@<commit>` 的 commit **逐字相同**；② 卫语句
      `siglip.check.check_whether_transformers_replace_is_installed_correctly()` **严格返回 True**
      （V5 的 `is not False` 是弱判据：探针异常时它给 None 也会绿 ⇒ 弱牙，V10 补强）；
      ③ 运行时 `transformers.__version__` ∈ {4.53.2, 4.53.3}（= 卫语句自己那行判据的取值域，
      读实现原文得来，不是声明值）。另附 `ruling_48_6_blocker_to_success` 段，
      把「blocker→成功之间改了什么、何时改」做成**机器承载**（mtime + 安装日志原文行）。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from a_env_manifest import parse_pyvenv_cfg, probe_venv, sha256  # noqa: E402  复用 A 线口径

REPO = pathlib.Path(__file__).resolve().parent.parent
PERSIST = pathlib.Path("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist")
VENV_LINK = pathlib.Path("/root/venvs/pi05_sim")

PACKAGES = ["torch", "torchvision", "torchcodec", "transformers", "lerobot", "accelerate",
            "safetensors", "gymnasium", "gym_aloha", "mujoco", "numpy", "scipy", "huggingface_hub",
            "tokenizers", "datasets", "diffusers", "dm_control", "cv2", "imageio", "robosuite"]

DIST_NAME = {"cv2": "opencv-python-headless"}


def dist_name(mod: str) -> str:
    return DIST_NAME.get(mod, mod.replace("_", "-"))


def probe_dist(link: pathlib.Path, packages):
    """逐包探「**发行版本**（dist-info，pin 的权威口径）」与「**能否 import**」，两者分开记。

    为什么不能只用 A 线 `probe_venv` 的 `pkgs[m] = getattr(mod, "__version__", None)`：
    本轮实测到两类**假红**——
      ① `gym_aloha` / `dm_control` **压根不暴露 `__version__`** ⇒ 装好了也读成 None；
      ② `torchcodec` 装了（dist-info 在）但 **import 失败**（缺 FFmpeg：`Could not load libtorchcodec`）
         ⇒ 这是真的环境缺口，但它是**可导入性**问题，不是**版本漂移**问题，两者必须分开报。
    把两者混成一个 None，会让 V4（版本红线）假红、还会让基线比对**双向失明**
    （两边都 None ⇒ 相等 ⇒ 漂移检查恒过）。
    """
    code = """
import json, importlib, importlib.metadata as md
out = {}
for m in __PACKAGES__:
    rec = {}
    try:
        mod = importlib.import_module(m)
        rec["import_ok"] = True
        rec["import_version"] = getattr(mod, "__version__", None)
        rec["import_file"] = getattr(mod, "__file__", None)
    except Exception as e:
        rec["import_ok"] = False
        rec["import_error"] = repr(e)[:240]
    dn = __DISTNAMES__[m]
    rec["dist_name"] = dn
    try:
        rec["dist_version"] = md.version(dn)
    except Exception as e:
        rec["dist_version"] = None
        rec["dist_error"] = repr(e)[:160]
    out[m] = rec
print(json.dumps(out))
""".replace("__PACKAGES__", repr(list(packages))).replace(
        "__DISTNAMES__", repr({m: dist_name(m) for m in packages}))
    import subprocess
    r = subprocess.run([str(link / "bin/python"), "-c", code], capture_output=True, text=True, timeout=600)
    if r.returncode == 0 and r.stdout.strip():
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as exc:  # noqa: BLE001
            return {"_parse_error": repr(exc), "_stderr_tail": r.stderr[-800:]}
    return {"_probe_rc": r.returncode, "_stderr_tail": r.stderr[-1500:]}


PINNED = {
    "torch.__version__": "2.6.0+cu124",
    "torchvision": "0.21.0+cu124",
    "torchcodec": "0.10.0",
    "lerobot": "0.4.4",
}


def _mtime_iso(path: pathlib.Path):
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def _lock_transformers_line(lock_path: pathlib.Path):
    """从 lock 里取出 `transformers` 那一行**原文**，并解析出 commit（若有）。"""
    if not lock_path.is_file():
        return {"path": str(lock_path), "exists": False}
    for ln in lock_path.read_text().splitlines():
        t = ln.strip()
        if t.startswith("transformers @") or t.startswith("transformers@") or t.startswith("transformers=="):
            commit = None
            m = re.search(r"git\+[^@\s]+@([0-9a-f]{7,40})", t)
            if m:
                commit = m.group(1)
            return {"path": str(lock_path), "exists": True, "line": t, "line_no":
                    lock_path.read_text().splitlines().index(ln) + 1,
                    "kind": "git_commit" if commit else "pypi_version", "commit": commit}
    return {"path": str(lock_path), "exists": True, "line": None}


def ruling_48_6_evidence(lock_after: pathlib.Path) -> dict:
    """裁定 48.6 只剩的那一条：**blocker 与成功之间改了什么、何时改的**，做成机器承载。

    证据全部来自**已落盘的文件**（mtime + 安装日志原文行），不靠记忆或转述：
      before  = `requirements.lock.stage2c_before_pi_extra.txt`（STAGE 2c 后、`pi` extra 前）
      blocker = `probe_run1_transformers_blocker.log`（G2 run1 的 ValueError 现场）
      change  = `stage3_install.log`（装 lerobot `pi` extra 的那次，含 `- 4.57.6 / + 4.53.3(git@commit)`）
      after   = `requirements.lock.txt`（当前 lock，第 111 行带 commit）
      success = `probe.log`（G2 run3 的加载成功现场）
    """
    env_dir = REPO / "runs/vla/a2_env_pi05_sim_20260929"
    con_dir = REPO / "runs/vla/a2_pi05_contract_20260929"
    before_lock = env_dir / "requirements.lock.stage2c_before_pi_extra.txt"
    stage3 = env_dir / "stage3_install.log"
    blocker = con_dir / "probe_run1_transformers_blocker.log"
    success = con_dir / "probe.log"

    rec: dict = {
        "ruling": "48.6（裁定 44.1 的甲/乙/丙三案作废后，A2 只剩这一条要答）",
        "question": "blocker 与成功之间改了什么、何时改的；并确认已写入 lock 与 env_manifest.json",
        "timeline": {
            "1_before_pi_extra_lock": {"path": str(before_lock), "mtime": _mtime_iso(before_lock),
                                       "transformers": _lock_transformers_line(before_lock)},
            "2_blocker_observed": {"path": str(blocker), "mtime": _mtime_iso(blocker)},
            "3_change_install_log": {"path": str(stage3), "mtime": _mtime_iso(stage3)},
            "4_after_lock_current": {"path": str(lock_after), "mtime": _mtime_iso(lock_after),
                                     "transformers": _lock_transformers_line(lock_after)},
            "5_success_observed": {"path": str(success), "mtime": _mtime_iso(success)},
        },
    }

    # blocker 现场原文（只取含关键字的行，避免把整段 traceback 抄进来）
    if blocker.is_file():
        txt = blocker.read_text(errors="replace").splitlines()
        rec["blocker_log_key_lines"] = [ln.strip()[:240] for ln in txt
                                        if re.search(r"ValueError|incorrect transformer|ImportError|siglip|check", ln)][:8]
    # 安装日志原文：start_utc + transformers/tokenizers 的 -/+ 行 + Building 行
    if stage3.is_file():
        txt = stage3.read_text(errors="replace").splitlines()
        keys = []
        for ln in txt:
            t = ln.strip()
            if re.match(r"(start_utc=|PRE transformers|\s*[+-] (transformers|tokenizers)==|Building transformers|Resolved \d+ packages)", t) \
               or re.search(r"^[+-] (transformers|tokenizers)==", t):
                keys.append(t[:240])
        rec["install_log_key_lines"] = keys[:14]
        m = re.search(r"start_utc=(\S+)", stage3.read_text(errors="replace"))
        rec["install_started_utc"] = m.group(1) if m else None

    b = rec["timeline"]["1_before_pi_extra_lock"]["transformers"]
    a = rec["timeline"]["4_after_lock_current"]["transformers"]
    rec["what_changed"] = {
        "action": "安装 lerobot 0.4.4 的 `pi` extra（STAGE 3），由它把 PyPI 的 transformers 换成 "
                  "带 `transformers/models/siglip/check.py` 的 **git 构建**",
        "transformers_before": b.get("line"),
        "transformers_after": a.get("line"),
        "commit_after": a.get("commit"),
        "mechanism": ("卫语句 `modeling_pi05.py:576`–`:584` 是 `from transformers.models.siglip import check` "
                      "→ `check_whether_transformers_replace_is_installed_correctly()`；PyPI 构建**没有** "
                      "`check.py` ⇒ 走 `ImportError` 分支抛同一个 `ValueError`（= blocker 现场）；"
                      "git 构建有 `check.py` 且其判据是 `__version__ == 4.53.2 or 4.53.3` ⇒ 返回 True（= 成功现场）。"),
        "also_changed": "tokenizers 0.22.2 → 0.21.4（同一次 `pi` extra 解析带的，见 install_log_key_lines）",
    }
    rec["written_to_lock"] = {
        "verdict": bool(a.get("commit")) and a.get("kind") == "git_commit",
        "evidence": f"{pathlib.Path(lock_after).name}:{a.get('line_no')}",
        "note": "D 已在裁定 48 里独立确认过（「A2 的 lock 记对了」）；这里再自证一次，口径 = 行号 + 原文。",
    }
    rec["written_to_env_manifest"] = {
        "verdict_field": "assertions.V10_transformers_identity_is_git_commit_per_ruling_48",
        "note": ("裁定 48.6 要求的「写入 env_manifest.json」由 **V10** 承载：`direct_url.json.commit_id` "
                 "与 lock commit 逐字比对 + 卫语句严格 True。此前 19:1x 那版 manifest **只有 V5**"
                 "（弱判据，只查 `check` 模块在不在），**不含 commit 身份** ⇒ 本次补齐。"),
    }
    return rec


V10_COMMIT_DOMAIN = ("4.53.2", "4.53.3")


def eval_v10(direct_url, lock_commit, guard_ret, runtime_version):
    """裁定 48 红线的**纯判据**（拆出来是为了能被变异自检打，而不是只在真环境上跑一次）。

    `direct_url` = PEP 610 的 `direct_url.json` 内容（**注册表/wheel 安装时该文件根本不存在** ⇒ 传 None）。
    注意 PEP 610 的 `url` 字段是**裸 VCS URL**（`https://…/transformers.git`），
    **不带** pip/lock 里的 `git+` 前缀 ⇒ 判「是不是 VCS 构建」的权威信号是
    `vcs_info.vcs == "git"`（而不是 `url.startswith("git+")`；本轮第一版就是踩了这个坑，见日报自纠）。
    """
    du = direct_url or {}
    vcs = du.get("vcs_info") or {}
    dist_commit = vcs.get("commit_id")
    checks = {
        "c1_direct_url_commit_present": bool(dist_commit),
        "c2_lock_commit_present": bool(lock_commit),
        "c3_commits_bitwise_identical": bool(dist_commit) and bool(lock_commit) and dist_commit == lock_commit,
        "c4_guard_clause_returns_strictly_true": guard_ret is True,
        "c5_runtime_version_in_guard_domain": runtime_version in V10_COMMIT_DOMAIN,
        "c6_is_vcs_build_not_registry_wheel": vcs.get("vcs") == "git" and "archive_info" not in du,
    }
    return checks, all(checks.values())


def v5_predicate(siglip_module_present, guard_ret):
    """V5 的原判据（**弱牙**，逐字照抄 main() 里那行，用来在自检里对比 V10 强在哪）。"""
    return bool(siglip_module_present) and guard_ret is not False


REAL_COMMIT = "dcddb970176382c0fcf4521b0c0e6fc15894dfe0"
REAL_DIRECT_URL = {"url": "https://github.com/huggingface/transformers.git",
                   "vcs_info": {"vcs": "git", "commit_id": REAL_COMMIT,
                                "requested_revision": "fix/lerobot_openpi"}}


def v10_selftest():
    """**变异自检**：V10 必须在 6 个变异体上全红，否则它是恒真闸（B2 `mutation_verdict.json` 同族口径）。

    M1 就是**本轮真实发生过的 blocker 状态**（`transformers==4.57.6` 从 PyPI 装 ⇒ 压根没有
    `direct_url.json`）⇒ 这条不是假想变异，是历史复现。
    M5（探针异常 ⇒ guard 返回 None）**V5 会放过、V10 必须抓** ⇒ 用来证明 V10 严格强于 V5。
    """
    cases = [
        ("B0_real_observed", REAL_DIRECT_URL, REAL_COMMIT, True, "4.53.3", True),
        ("M1_registry_install_no_direct_url(=真实 blocker 4.57.6)", None, None, False, "4.57.6", False),
        ("M2_wheel_archive_info_shape", {"url": "file:///w/transformers-4.53.3-py3-none-any.whl",
                                         "archive_info": {"hashes": {"sha256": "0" * 64}}}, REAL_COMMIT, True, "4.53.3", False),
        ("M3_commit_mismatch", {"url": REAL_DIRECT_URL["url"],
                                "vcs_info": {"vcs": "git", "commit_id": "a" * 40}}, REAL_COMMIT, True, "4.53.3", False),
        ("M4_guard_returns_false", REAL_DIRECT_URL, REAL_COMMIT, False, "4.57.6", False),
        ("M5_guard_probe_exception_none", REAL_DIRECT_URL, REAL_COMMIT, None, "4.53.3", False),
        ("M6_version_outside_guard_domain", REAL_DIRECT_URL, REAL_COMMIT, True, "4.57.1", False),
    ]
    rows, n_caught, n_expected = [], 0, 0
    for name, du, lc, gr, rv, expect_green in cases:
        checks, got = eval_v10(du, lc, gr, rv)
        v5 = v5_predicate(True, gr)
        ok = (got == expect_green)
        if name != "B0_real_observed":
            n_expected += 1
            n_caught += int(not got)
        rows.append({"case": name, "expect_green": expect_green, "v10_green": got,
                     "verdict": "ok" if ok else "MISMATCH",
                     "failed_checks": sorted(k for k, v in checks.items() if not v),
                     "v5_would_say_green": v5,
                     "v10_strictly_stronger_here": (v5 and not got)})
    return {"probe": "v10_mutation_selftest",
            "mutations_expected_to_be_caught": n_expected,
            "mutations_caught": n_caught,
            "all_cases_verdict_ok": all(r["verdict"] == "ok" for r in rows),
            "baseline_green": rows[0]["v10_green"],
            "cases": rows,
            "v5_weak_tooth_demonstrated_by": [r["case"] for r in rows if r["v10_strictly_stronger_here"]]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv-link", default=str(VENV_LINK))
    ap.add_argument("--lock", default=str(REPO / "runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt"))
    ap.add_argument("--baseline-venv", default="/root/venvs/lerobot_act",
                    help="已验收基线 venv，用来逐项比对（只读，不装不改）")
    ap.add_argument("--out", default=str(REPO / "runs/vla/a2_env_pi05_sim_20260929/env_manifest.json"))
    ap.add_argument("--no-cold-import", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑 V10 的变异自检（纯函数，不探环境），6 个变异体必须全红")
    args = ap.parse_args()

    if args.selftest:
        st = v10_selftest()
        print(json.dumps(st, ensure_ascii=False, indent=1))
        return 0 if (st["all_cases_verdict_ok"] and st["baseline_green"]
                     and st["mutations_caught"] == st["mutations_expected_to_be_caught"]) else 1

    link = pathlib.Path(args.venv_link)
    man: dict = {
        "manifest": "a2_env_manifest",
        "line": "A2（VLA 底模与仿真贯通）",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_env_manifest.py",
        "probe_kind": "semantic",
        "probe_kind_meaning": ("子进程真 import 后读 __version__ 与 dist-info 路径（= 安装来源），"
                               "并回显软链指向与 pyvenv.cfg；**import 成功不算过**（A 线口径）"),
        "kou_jing_reused_from": "scripts/a_env_manifest.py 的 probe_venv / parse_pyvenv_cfg / sha256（未另写）",
        "loadavg": list(os.getloadavg()),
    }

    # ---------- V1/V2 ----------
    man["venv"] = probe_venv(link, PACKAGES)
    resolved = man["venv"].get("resolved") or ""
    v1 = link.is_symlink() and resolved.startswith(str(PERSIST))
    cfg = man["venv"].get("pyvenv_cfg") or {}
    v2 = str(cfg.get("include-system-site-packages", "")).lower() == "false"
    man["venv"]["base_python_home"] = cfg.get("home")

    pkgs = man["venv"].get("pkgs") or {}
    man["dist_probe"] = probe_dist(link, PACKAGES)
    dp = man["dist_probe"]
    dver = {k: (v or {}).get("dist_version") for k, v in dp.items() if isinstance(v, dict)}
    man["dist_versions"] = dver
    torch_v = man["venv"].get("torch_version")
    v3 = torch_v == PINNED["torch.__version__"]
    # 版本红线按**发行版本**判（pin 的口径），可导入性另记 known_gaps
    v4 = (dver.get("torchvision") == PINNED["torchvision"] and dver.get("torchcodec") == PINNED["torchcodec"])
    v8 = dver.get("lerobot") == PINNED["lerobot"]
    man["known_gaps"] = {
        m: {"import_ok": dp[m].get("import_ok"), "import_error": dp[m].get("import_error"),
            "dist_version": dp[m].get("dist_version")}
        for m in dp if isinstance(dp.get(m), dict) and not dp[m].get("import_ok") and dp[m].get("dist_version")
    }
    man["known_gaps_note"] = ("装了但 import 不了的包。**不是**版本漂移（版本红线仍按 dist-info 判），"
                              "但要报出来：`torchcodec` 缺 FFmpeg ⇒ lerobot 的**视频**数据集解码不可用；"
                              "本轮 G2/G3 走仿真渲染，不解码视频，所以不阻塞。基线 venv 是否同状况见 "
                              "baseline_comparison.known_gaps_baseline。")

    # ---------- V5/V6/V7：π₀.₅ 专属语义断言（单独子进程，避免污染上面的探测）----------
    sem_code = r"""
import json
out = {}
try:
    from transformers.models.siglip import check as _c
    out["siglip_check_module_present"] = True
    out["siglip_check_file"] = getattr(_c, "__file__", None)
    try:
        out["transformers_replace_installed_correctly"] = bool(
            _c.check_whether_transformers_replace_is_installed_correctly())
    except Exception as e:
        out["transformers_replace_installed_correctly"] = None
        out["transformers_replace_error"] = repr(e)[:200]
except Exception as e:
    out["siglip_check_module_present"] = False
    out["siglip_check_error"] = repr(e)[:200]
try:
    import transformers
    out["transformers_version"] = transformers.__version__
    out["transformers_file"] = transformers.__file__
except Exception as e:
    out["transformers_version"] = None; out["transformers_error"] = repr(e)[:200]
try:
    from transformers.models.paligemma.modeling_paligemma import PaliGemmaForConditionalGeneration
    out["paligemma_import_ok"] = True
except Exception as e:
    out["paligemma_import_ok"] = False; out["paligemma_import_error"] = repr(e)[:300]
try:
    from lerobot.policies.pi05.modeling_pi05 import PI05Policy
    from lerobot.policies.pi05.configuration_pi05 import PI05Config
    out["pi05_policy_import_ok"] = True
    c = PI05Config()
    out["pi05_config_defaults"] = {
        "chunk_size": c.chunk_size, "n_action_steps": c.n_action_steps, "n_obs_steps": c.n_obs_steps,
        "max_action_dim": c.max_action_dim, "max_state_dim": c.max_state_dim,
        "num_inference_steps": c.num_inference_steps, "image_resolution": list(c.image_resolution),
        "paligemma_variant": c.paligemma_variant, "action_expert_variant": c.action_expert_variant,
        "tokenizer_max_length": c.tokenizer_max_length,
    }
except Exception as e:
    out["pi05_policy_import_ok"] = False; out["pi05_import_error"] = repr(e)[:300]
try:
    import gymnasium as gym, gym_aloha  # noqa: F401
    spec = gym.spec("gym_aloha/AlohaTransferCube-v0")
    out["gym_aloha_spec_ok"] = True
    out["gym_aloha_spec"] = {"id": spec.id, "entry_point": spec.entry_point,
                             "max_episode_steps": spec.max_episode_steps, "kwargs": spec.kwargs}
except Exception as e:
    out["gym_aloha_spec_ok"] = False; out["gym_aloha_error"] = repr(e)[:300]
try:
    import torch
    out["torch_version"] = torch.__version__
    out["cuda_available"] = bool(torch.cuda.is_available())
    out["cuda_device"] = torch.cuda.get_device_name(0) if out["cuda_available"] else None
except Exception as e:
    out["torch_error"] = repr(e)[:200]
try:
    import importlib.metadata as _md, pathlib as _pl, json as _json
    _d = _md.distribution("transformers")
    _di = getattr(_d, "_path", None)
    out["transformers_dist_info_dir"] = str(_di) if _di else None
    if _di:
        _du = _pl.Path(_di) / "direct_url.json"
        out["transformers_direct_url"] = _json.loads(_du.read_text()) if _du.is_file() else None
        _ins = _pl.Path(_di) / "INSTALLER"
        out["transformers_installer"] = _ins.read_text().strip() if _ins.is_file() else None
except Exception as e:
    out["transformers_dist_info_error"] = repr(e)[:200]
try:
    import inspect as _inspect
    from transformers.models.siglip import check as _c2
    out["siglip_check_guard_source"] = _inspect.getsource(
        _c2.check_whether_transformers_replace_is_installed_correctly)
except Exception as e:
    out["siglip_check_guard_source_error"] = repr(e)[:200]
print(json.dumps(out))
"""
    t0 = time.perf_counter()
    import subprocess
    r = subprocess.run([str(link / "bin/python"), "-c", sem_code], capture_output=True, text=True, timeout=900)
    sem = {}
    if r.returncode == 0 and r.stdout.strip():
        try:
            sem = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as exc:  # noqa: BLE001
            sem = {"parse_error": repr(exc), "stderr_tail": r.stderr[-800:]}
    else:
        sem = {"probe_rc": r.returncode, "stderr_tail": r.stderr[-1500:]}
    sem["probe_wall_s"] = round(time.perf_counter() - t0, 1)
    man["semantic_probe"] = sem
    v5 = bool(sem.get("siglip_check_module_present")) and sem.get("transformers_replace_installed_correctly") is not False
    v6 = bool(sem.get("paligemma_import_ok")) and bool(sem.get("pi05_policy_import_ok"))
    v7 = bool(sem.get("gym_aloha_spec_ok"))

    # ---------- V9：lock ----------
    lock = pathlib.Path(args.lock)
    lock_rec: dict = {"path": str(lock), "exists": lock.is_file()}
    if lock.is_file():
        lines = [ln for ln in lock.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        lock_rec["n_pins"] = len(lines)
        lock_rec["sha256"] = sha256(lock)
        lock_rec["mtime"] = datetime.fromtimestamp(lock.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        names = {ln.split("==")[0].split(">=")[0].split("@")[0].strip().lower().replace("_", "-")
                 for ln in lines}
        # import 名 -> 发行名 的别名（`import cv2` 的发行名是 opencv-python-headless）
        alias = {"cv2": "opencv-python-headless", "sklearn": "scikit-learn", "yaml": "pyyaml"}
        # **只算真装了的**：probe_venv 对缺失包写的是 None，若按 key 全算进来，
        # 没装的 robosuite/cv2 会被判成「lock 缺条目」⇒ 假红（同 G0.5 那次探针 bug 的教训）。
        installed = {dist_name(k).lower() for k, v in dver.items() if v}
        lock_rec["import_name_alias"] = alias
        lock_rec["probed_packages_present"] = sorted(installed)
        lock_rec["probed_packages_missing_from_lock"] = sorted(p for p in installed if p and p not in names)
        lock_rec["probed_packages_absent_from_venv"] = sorted(
            dist_name(k).lower() for k, v in dver.items() if not v)
    man["lock"] = lock_rec
    v9 = bool(lock_rec.get("exists")) and lock_rec.get("n_pins", 0) > 50 \
        and not lock_rec.get("probed_packages_missing_from_lock")

    # ---------- V10：裁定 48 的 transformers 身份红线（git commit，不是版本区间）----------
    du = sem.get("transformers_direct_url") or {}
    vcs = du.get("vcs_info") or {}
    dist_commit = vcs.get("commit_id")
    lock_tf = _lock_transformers_line(lock)
    lock_commit = lock_tf.get("commit")
    guard_ret = sem.get("transformers_replace_installed_correctly")
    rt_ver = sem.get("transformers_version")
    v10_checks, v10 = eval_v10(sem.get("transformers_direct_url"), lock_commit, guard_ret, rt_ver)
    man["transformers_identity_ruling_48"] = {
        "ruling": "裁定 48：撤销裁定 39 的 `transformers >= 4.57.1` 下界；身份改判为 **git commit**",
        "red_line": "transformers 身份 = git commit（branch `fix/lerobot_openpi`）；`torch==2.6.0+cu124` 红线不动",
        "checks": v10_checks,
        "direct_url": du,
        "installer": sem.get("transformers_installer"),
        "dist_info_dir": sem.get("transformers_dist_info_dir"),
        "lock_line": lock_tf,
        "guard_clause_return": guard_ret,
        "guard_clause_source": sem.get("siglip_check_guard_source"),
        "guard_clause_call_site": ("lerobot/policies/pi05/modeling_pi05.py:576–:584 "
                                   "（`from transformers.models.siglip import check` → "
                                   "`check_whether_transformers_replace_is_installed_correctly()`；"
                                   "`ImportError` 也抛同一个 `ValueError`）"),
        "evidence_class": "implementation_read（读了卫语句与 `check.py` 的实现原文；**不是** `declared_only`）",
        "why_version_range_is_wrong": ("`check.py` 的判据是**等值**（`== 4.53.2 or == 4.53.3`），不是区间 ⇒ "
                                       "任何 `>=4.57.1` 的下界与它**互斥**；字面执行裁定 39 会把 π₀.₅ 加载搞坏。"),
        "v5_is_a_weak_tooth": ("V5 只要求 `siglip_check_module_present` 且 guard `is not False` ⇒ "
                               "探针异常给出 `None` 时 V5 仍绿。V10 用 `is True` + commit 逐字比对补强。"),
        "mutation_selftest": v10_selftest(),
        "pep610_note": ("`direct_url.json` 的 `url` 是**裸 VCS URL**（无 `git+` 前缀）⇒ "
                        "判 VCS 构建用 `vcs_info.vcs == 'git'`；注册表/wheel 安装**不生成该文件**"
                        "（本 venv 124 个 dist-info 里只有 transformers 有），"
                        "所以「没有 direct_url.json」本身就是 PyPI 构建的证据 = 本轮 blocker 的真实状态。"),
    }
    man["ruling_48_6_blocker_to_success"] = ruling_48_6_evidence(lock)

    # ---------- 与已验收基线逐项比对 ----------
    base = probe_venv(pathlib.Path(args.baseline_venv), PACKAGES) if args.baseline_venv else {}
    base_dp = probe_dist(pathlib.Path(args.baseline_venv), PACKAGES) if args.baseline_venv else {}
    bp = {k: (v or {}).get("dist_version") for k, v in base_dp.items() if isinstance(v, dict)}
    diff = {}
    for k in sorted(set(dver) | set(bp)):
        a, b = dver.get(k), bp.get(k)
        if a != b:
            diff[k] = {"pi05_sim": a, "lerobot_act_baseline": b}
    man["baseline_comparison"] = {
        "baseline_venv": args.baseline_venv,
        "baseline_read_only": True,
        "baseline_torch_version": base.get("torch_version"),
        "version_source": "dist-info（importlib.metadata），不是 module.__version__；理由见 probe_dist 的 docstring",
        "known_gaps_baseline": {
            m: {"import_ok": base_dp[m].get("import_ok"), "import_error": base_dp[m].get("import_error"),
                "dist_version": base_dp[m].get("dist_version")}
            for m in base_dp if isinstance(base_dp.get(m), dict)
            and not base_dp[m].get("import_ok") and base_dp[m].get("dist_version")
        },
        # 只算**两边都真有版本**的：两边都是 None（都没装）不算 identical，那是双向失明
        "identical_packages": sorted(k for k in set(dver) & set(bp) if dver.get(k) and dver.get(k) == bp.get(k)),
        "differing_packages": diff,
        "note": ("差异里 `transformers` / `tokenizers` / `gym-aloha` / `mujoco` / `dm-control` / `scipy` 是"
                 "**A2 有意引入**的（π₀.₅ 需要）；`torch` / `torchvision` / `torchcodec` / `lerobot` / "
                 "`numpy` / `safetensors` / `huggingface-hub` 若出现在差异里就是**断点变更**，必须报 D。"),
    }
    FROZEN = ("torch", "torchvision", "torchcodec", "lerobot")
    base_pkgs = base.get("pkgs") or {}
    # 冻结栈的**逐字**版本：运行时（module.__version__）与发行（dist-info）两个口径都记，
    # 因为本轮实测到它们会**不一致**（见下面 dist_metadata_difference）。
    man["frozen_stack_versions"] = {
        k: {"pi05_sim_runtime": pkgs.get(k), "baseline_runtime": base_pkgs.get(k),
            "pi05_sim_dist": dver.get(k), "baseline_dist": bp.get(k)}
        for k in FROZEN}

    def _effective(k, side):
        """运行时版本优先（D §9.2-3 的红线原文就是 `torch.__version__`）；读不到才退回 dist 版本。"""
        v = man["frozen_stack_versions"][k][f"{side}_runtime"]
        return v if v else man["frozen_stack_versions"][k][f"{side}_dist"]

    # **漂移按运行时版本判**，理由（本轮实测）：基线 `lerobot_act` 的 torch dist-info 写 `2.6.0`、
    # 本 venv 写 `2.6.0+cu124`，而两者 `torch.__version__` **都是** `2.6.0+cu124`
    # ⇒ local-version 后缀随**安装源**（download.pytorch.org vs aliyun 镜像）而变，
    # 那是**元数据口径差**，不是断点变更。按 dist 判会把红线判成假红（本轮第一版就红了）。
    frozen = [k for k in FROZEN if _effective(k, "pi05_sim") != _effective(k, "baseline")]
    man["frozen_stack_dist_metadata_difference"] = {
        k: {"pi05_sim_dist": dver.get(k), "baseline_dist": bp.get(k),
            "runtime_identical": _effective(k, "pi05_sim") == _effective(k, "baseline")}
        for k in FROZEN if dver.get(k) != bp.get(k)}
    man["frozen_stack_rule"] = ("drift 判据 = 运行时版本（module.__version__）逐字比对；"
                                "dist-info 的 local-version 后缀差异单列在 "
                                "frozen_stack_dist_metadata_difference，不计入 drift。")
    man["baseline_comparison"]["frozen_stack_drift"] = frozen

    # ---------- 冷导入耗时（NFS venv 是否拖慢）----------
    if not args.no_cold_import:
        cold = {}
        for mod in ("torch", "transformers", "lerobot"):
            code = f"import time;t=time.perf_counter();import {mod};print('%.2f' % (time.perf_counter()-t))"
            rr = subprocess.run([str(link / "bin/python"), "-c", code], capture_output=True, text=True, timeout=600)
            try:
                cold[mod] = float(rr.stdout.strip().splitlines()[-1])
            except Exception:
                cold[mod] = None
        man["cold_import_s"] = cold

    assertions = {
        "V1_venv_is_symlink_to_NFS_persist": v1,
        "V2_include_system_site_packages_false": v2,
        "V3_torch_version_redline_2_6_0_cu124": v3,
        "V4_torchvision_torchcodec_match_baseline": v4,
        "V5_transformers_has_siglip_check_for_pi05": v5,
        "V6_paligemma_and_pi05policy_importable": v6,
        "V7_gym_aloha_spec_registrable": v7,
        "V8_lerobot_pinned_0_4_4": v8,
        "V9_lock_present_and_covers_probed_packages": v9,
        "V10_transformers_identity_is_git_commit_per_ruling_48": v10,
    }
    man["assertions"] = assertions
    man["assertions_pass"] = f"{sum(1 for v in assertions.values() if v)}/{len(assertions)}"
    man["env_usable"] = all(assertions.values()) and not frozen
    man["verdict"] = {
        "env_usable": man["env_usable"],
        "frozen_stack_drift": frozen,
        "claim_scope": ("env_usable=true **只**支持『pi05_sim 环境可用、π₀.₅ 代码面与依赖就绪』这一句；"
                        "**不**支持任何能力/成功率主张（D §0-6、§5『不得声称』清单）。"),
        "blocked_if": ("V5/V10 红 ⇒ π₀.₅ 无法 from_pretrained（V10 是裁定 48 的强判据：commit 逐字 + 卫语句严格 True）；"
                       "V3/V4 红或 frozen_stack_drift 非空 ⇒ 断点变更，需 D 登记 + 重过 B2 闸"),
        "transformers_commit": (man.get("transformers_identity_ruling_48", {}).get("direct_url", {})
                                .get("vcs_info", {}) or {}).get("commit_id"),
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(man, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"assertions": assertions, "pass": man["assertions_pass"],
                      "frozen_stack_drift": frozen, "env_usable": man["env_usable"],
                      "torch": man["venv"].get("torch_version"),
                      "transformers": sem.get("transformers_version"),
                      "transformers_commit": (du.get("vcs_info") or {}).get("commit_id"),
                      "lock_commit": lock_commit, "guard_returns": guard_ret,
                      "differing_vs_baseline": sorted(diff)}, ensure_ascii=False, indent=1))
    print(f"[written] {out}")
    return 0 if man["env_usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
