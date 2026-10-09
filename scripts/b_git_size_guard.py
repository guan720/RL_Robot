#!/usr/bin/env python3
"""B 线：git 纳管体积闸 + 排除域守卫（DR-003 决定 7 的带牙实现）。

为什么光有 .gitignore 不够：
  - git **无法按体积**忽略文件，「大 JSON 产物」只能靠扩展名猜；
  - `.gitignore` 只挡未跟踪文件，`git add -f` 或规则写漏时照样进版本库；
  - DR-002 护栏 3 / DR-003 决定 1、5 要求 `runs/` 与只读交付包 `RL_Harness_v4_20260924/`
    永不被 git 改写 —— 这需要一条**主动拒绝**的规则，而不是被动忽略。

本脚本因此做三件事，任一不过即 exit 1（可直接当 pre-commit hook）：
  1. 体积闸：暂存区里新增/修改的文件 > SIZE_LIMIT_BYTES 且不在白名单 -> 拒绝；
  2. 排除域守卫：暂存区里出现 `runs/` 或 `RL_Harness_v4_20260924/` 下的路径 -> 拒绝；
  3. 白名单完整性：白名单里的路径必须真实存在且**逐个写明理由**，否则拒绝
     （防止把白名单当成一键放行的大口袋）。

用法：
  python scripts/b_git_size_guard.py                # 检查暂存区（hook 模式）
  python scripts/b_git_size_guard.py --install      # 写入 .git/hooks/pre-commit
  python scripts/b_git_size_guard.py --check-tracked # 扫全部已跟踪文件（体检/CI）
  python scripts/b_git_size_guard.py --selftest     # 变异自检：闸门必须真的有牙

AGENTS.md 纪律：本脚本**不删除任何文件**，只拒绝提交。清理一律 mv 到回收站。
"""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE_LIMIT_BYTES = 2 * 1024 * 1024          # 2 MB；实测当前 tracked 候选无 >1 MB 文件
WHITELIST_DOC = ROOT / "configs" / "b_git_size_whitelist.json"
FORBIDDEN_PREFIXES = ("runs/", "RL_Harness_v4_20260924/")
HOOK = ROOT / ".git" / "hooks" / "pre-commit"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _whitelist() -> dict:
    if not WHITELIST_DOC.exists():
        return {"entries": {}}
    return json.loads(WHITELIST_DOC.read_text(encoding="utf-8"))


def _fmt(n: int) -> str:
    return "%.2f MB" % (n / 1024 / 1024) if n >= 1024 * 1024 else "%.1f KB" % (n / 1024)


FORBIDDEN_WHY = {
    "runs/": "DR-003 决定 1：实验产物（37 GB），版本库只登记其 sha256/路径，不收载荷",
    "RL_Harness_v4_20260924/": "DR-003 决定 5 + DR-002 护栏 3：只读交付包，纳管即产生 git checkout 改写路径",
}


def check_paths(paths: list[str]) -> list[str]:
    """逐路径检查：体积闸 + 排除域守卫。返回错误列表（空 = 通过）。"""
    errs: list[str] = []
    wl = _whitelist().get("entries", {})
    for rel in paths:
        for pre, why in FORBIDDEN_WHY.items():
            if rel.startswith(pre):
                errs.append("[排除域] %s 落在 `%s` 下 —— %s" % (rel, pre.rstrip('/'), why))
        p = ROOT / rel
        if not p.exists():
            continue                                    # 删除类变更已被 --diff-filter 过滤
        sz = p.stat().st_size
        if sz > SIZE_LIMIT_BYTES:
            ent = wl.get(rel)
            if not ent:
                errs.append("[体积] %s = %s > 上限 %s —— 属实验产物，应放 runs/；"
                            "确需纳管则在 %s 里显式登记路径+理由+sha256"
                            % (rel, _fmt(sz), _fmt(SIZE_LIMIT_BYTES), WHITELIST_DOC.name))
            elif not str(ent.get("reason", "")).strip():
                errs.append("[体积] %s = %s 在白名单里但**没写理由** —— 白名单不是一键放行口袋"
                            % (rel, _fmt(sz)))
    return errs


def check_whitelist() -> list[str]:
    """白名单自身完整性：陈旧条目与空理由。与待提交路径无关，故独立成函数
    （否则全局错误会污染逐路径用例的判定，selftest M2 就是被它带偏的）。"""
    errs: list[str] = []
    for rel, ent in _whitelist().get("entries", {}).items():
        if not (ROOT / rel).exists():
            errs.append("[白名单] %s 已不存在，应从 %s 移除（陈旧放行条目）"
                        % (rel, WHITELIST_DOC.name))
        elif not str((ent or {}).get("reason", "")).strip():
            errs.append("[白名单] %s 缺 reason 字段" % rel)
    return errs


def check(paths: list[str], label: str) -> list[str]:
    """hook 入口 = 逐路径检查 + 白名单完整性。"""
    errs = check_paths(paths) + check_whitelist()
    if errs:
        print("%s：发现 %d 个问题" % (label, len(errs)))
        for e in errs:
            print("  ✗ " + e)
    else:
        print("%s：通过（%d 个路径，上限 %s，排除域 %s）"
              % (label, len(paths), _fmt(SIZE_LIMIT_BYTES), " / ".join(FORBIDDEN_WHY)))
    return errs


def staged_paths() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [ln for ln in out.splitlines() if ln.strip()]


def tracked_paths() -> list[str]:
    out = _git("ls-files")
    return [ln for ln in out.splitlines() if ln.strip()]


def install() -> int:
    if not HOOK.parent.exists():
        print("✗ 未找到 %s —— 先 git init" % HOOK.parent)
        return 1
    body = ("#!/bin/sh\n"
            "# 由 scripts/b_git_size_guard.py --install 写入（DR-003 决定 7）。手改请先登记。\n"
            "exec python3 \"%s\" || exit 1\n" % (ROOT / "scripts" / "b_git_size_guard.py"))
    HOOK.write_text(body, encoding="utf-8")
    HOOK.chmod(0o755)
    print("✓ 已写入 %s" % HOOK)
    return 0


def selftest() -> int:
    """变异自检：证明闸门真的有牙（会拒），而不是恒过。

    全部临时文件用完一律 mv 到回收站，绝不 rm（AGENTS.md 数据安全约束 1/2）。
    逐路径检查与白名单完整性分开断言，避免全局错误互相污染。
    """
    import time
    rb = Path("/workspace/mnt/sppro/yhzhang91/recycle_bin")
    rb.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    cases: list[tuple[str, bool]] = []
    made: list[Path] = []

    def case(name: str, errs: list[str], expect_errs: bool) -> None:
        got = len(errs) > 0
        ok = (got == expect_errs)
        cases.append((name, ok))
        print("    %-44s errs=%-2d expect_errs=%-5s -> %s"
              % (name, len(errs), expect_errs, "pass" if ok else "FAIL"))
        for e in errs[:2]:
            print("        ✗ " + e)

    big = ROOT / "configs" / ("_sizetest_%d.bin" % stamp)
    big.write_bytes(b"\0" * (SIZE_LIMIT_BYTES + 1024))
    made.append(big)
    wl_bak = WHITELIST_DOC.read_text(encoding="utf-8") if WHITELIST_DOC.exists() else None
    WHITELIST_DOC.parent.mkdir(parents=True, exist_ok=True)
    rel_big = str(big.relative_to(ROOT))
    WHITELIST_DOC.write_text(json.dumps({"entries": {
        "configs/_does_not_exist_%d.bin" % stamp: {"reason": "陈旧条目，应被查出"},
        rel_big: {"reason": ""},
    }}, ensure_ascii=False, indent=1), encoding="utf-8")
    made.append(WHITELIST_DOC)
    try:
        # --- 逐路径检查 ---
        case("M1 超上限且不在白名单 -> 拒",
             _with_whitelist({"entries": {}}, lambda: check_paths([rel_big])), True)
        case("M2 正常源码文件 -> 放行", check_paths(["scripts/b_git_size_guard.py"]), False)
        case("M3 runs/ 路径 -> 拒（文件不存在也拒）", check_paths(["runs/infra/whatever.json"]), True)
        case("M4 只读交付包路径 -> 拒", check_paths(["RL_Harness_v4_20260924/README.md"]), True)
        # --- 白名单完整性 ---
        case("M5 陈旧条目 -> 查出", check_whitelist(), True)
        case("M6 空白名单 -> 无错", _with_whitelist({"entries": {}}, check_whitelist), False)
        case("M7 白名单放行超限文件（有理由）-> 逐路径放行",
             _with_whitelist({"entries": {rel_big: {"reason": "selftest 显式放行"}}},
                             lambda: check_paths([rel_big])), False)
    finally:
        for f in made:
            if f.exists():
                f.rename(rb / ("%d_%s" % (stamp, f.name)))
        if wl_bak is not None:
            WHITELIST_DOC.write_text(wl_bak, encoding="utf-8")
        print("    临时文件已 mv 到回收站（前缀 %d_），白名单已还原" % stamp)
    bad = [n for n, ok in cases if not ok]
    print("  体积闸变异自检：%d/%d 通过%s"
          % (len(cases) - len(bad), len(cases), "" if not bad else " -> FAIL: " + str(bad)))
    return 0 if not bad else 1


def _with_whitelist(content: dict, fn):
    """临时替换白名单内容跑 fn，跑完还原（selftest 专用）。"""
    bak = WHITELIST_DOC.read_text(encoding="utf-8") if WHITELIST_DOC.exists() else None
    WHITELIST_DOC.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        return fn()
    finally:
        if bak is None:
            WHITELIST_DOC.rename(ROOT / "configs" / ("_wl_bak_%d.json" % int(time.time())))
        else:
            WHITELIST_DOC.write_text(bak, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="git 纳管体积闸 + 排除域守卫（DR-003）")
    ap.add_argument("--install", action="store_true", help="写入 .git/hooks/pre-commit")
    ap.add_argument("--check-tracked", action="store_true", help="扫全部已跟踪文件")
    ap.add_argument("--selftest", action="store_true", help="变异自检")
    ap.add_argument("--limit-mb", type=float, default=None, help="临时改上限（仅体检用）")
    a = ap.parse_args()
    global SIZE_LIMIT_BYTES
    if a.limit_mb:
        SIZE_LIMIT_BYTES = int(a.limit_mb * 1024 * 1024)
    if a.selftest:
        return selftest()
    if a.install:
        return install()
    paths = tracked_paths() if a.check_tracked else staged_paths()
    label = "已跟踪文件体检" if a.check_tracked else "暂存区检查"
    if not paths:
        print("%s：暂存区为空，无需检查" % label)
        return 0
    return 1 if check(paths, label) else 0


if __name__ == "__main__":
    sys.exit(main())
