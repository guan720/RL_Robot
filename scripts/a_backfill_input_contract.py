#!/usr/bin/env python3
"""给「缺 `norm_input_blown_frames_frac` 字段」的历史闭环产物回填输入契约，并重新过门禁。

为什么需要（监管备忘 2026-09-28 增补二 §3）：任何闭环评测产物必须带
`norm_input_blown_frames_frac`，超 `INPUT_BLOWUP_TOL=0.05` 判 INVALID；**缺字段同样应判 INVALID**
（B 门禁待加该项，当前只判「有字段且超阈」）。所以缺字段的臂现在处在一个尴尬状态：
门禁写着 `measurement_valid=true`，但按增补二的口径它其实是「输入契约未验证」。

做法：**不手抄命令**。每份评测产物自己都记录了 `checkpoint / replan_every / episodes / seed0 /
horizon`，本脚本直接从产物里读出这些字段反推同参命令。评测器已验证跨进程逐位确定性
（`docs/lerobot_act_env_setup_20260928.md` §17），因此重跑只会在原产物上**新增字段**、
所有既有数字必须逐项不变——脚本会把原产物 `cp` 到 `pre_input_contract/` 留档供事后核对
（只复制、不移动、不删除）。

同一份评测产物可能被多个门禁产物引用（历史上存在重复裁定），因此按评测文件去重，
重评一次后把**所有**引用它的门禁产物都重跑一遍。

用法：
    python3 scripts/a_backfill_input_contract.py --dry-run     # 只打印将要执行什么
    python3 scripts/a_backfill_input_contract.py --emit /tmp/x.sh   # 写成 shell 链再后台跑
"""
from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path

OUT_DIR = "runs/infra/lerobot_act_env_20260928"
EVAL_PY = "/root/venvs/lerobot_eval/bin/python"


def gate_says_measured(gate: dict) -> bool:
    return bool((gate.get("input_contract") or {}).get("measured"))


def load_gate(path: Path) -> dict:
    g = json.loads(path.read_text())
    return g[0] if isinstance(g, list) else g


def collect(out_dir: Path) -> tuple[dict[str, list[Path]], list[str]]:
    """返回 {评测文件: [引用它的门禁文件]}（只含缺字段的）与跳过原因列表。"""
    need: dict[str, list[Path]] = collections.defaultdict(list)
    skipped: list[str] = []
    for gf in sorted(out_dir.glob("gate_strict_*.json")):
        gate = load_gate(gf)
        if gate_says_measured(gate):
            continue
        ef = gate.get("file")
        if not ef:
            skipped.append(f"{gf.name}: 门禁产物里没有 file 字段")
            continue
        if not Path(ef).exists():
            skipped.append(f"{gf.name}: 评测产物 {ef} 不存在")
            continue
        need[ef].append(gf)
    return need, skipped


def eval_command(eval_file: Path) -> tuple[str, str] | None:
    """从评测产物元数据反推同参 eval 命令；返回 (命令, 说明) 或 None。"""
    e = json.loads(eval_file.read_text())
    ckpt = e.get("checkpoint")
    if not ckpt:
        return None
    if isinstance(ckpt, str):
        ckpt_path: str | None = ckpt
    else:
        # 评测器写的是 pretrained_model_dir（精确到 step 目录），直接喂给 --ckpt 最稳：
        # 传 run 目录会被 resolve_pretrained_dir 解析成 checkpoints/last，未必是同一个 step。
        ckpt_path = (ckpt.get("pretrained_model_dir") or ckpt.get("path") or ckpt.get("dir"))
    if not ckpt_path or not Path(str(ckpt_path)).exists():
        return None
    parts = [EVAL_PY, "scripts/eval_lerobot_act_runtime.py", "--ckpt", str(ckpt_path),
             "--episodes", str(e.get("episodes", 20)), "--seed0", str(e.get("seed0", 5000)),
             "--horizon", str(e.get("horizon", 300))]
    r = e.get("replan_every")
    note = f"R={r}"
    if r and int(r) > 0:
        parts += ["--replan-every", str(int(r))]
    if e.get("log_actions"):
        parts += ["--log-actions"]
        note += " +log-actions"
    parts += ["--out", str(eval_file)]
    return " ".join(parts), note


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--emit", help="把命令写成 shell 脚本（供 setsid nohup 后台跑）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    need, skipped = collect(out_dir)
    lines: list[str] = []
    unresolved: list[str] = []
    for ef, gates in sorted(need.items()):
        got = eval_command(Path(ef))
        if got is None:
            unresolved.append(ef)
            continue
        cmd, note = got
        lines.append(f"# {Path(ef).name}  ({note})  被 {len(gates)} 个门禁产物引用")
        lines.append(f'cp -n "{ef}" "{out_dir}/pre_input_contract/{Path(ef).name}"')
        lines.append(cmd)
        lines.append(f'echo "REEVAL_{Path(ef).stem}_EXIT=$?"')
        for gf in gates:
            lines.append(f"{EVAL_PY} scripts/b_gate_controlled_success.py {ef} "
                         f"--json-out {gf} --quiet")
            lines.append(f'echo "REGATE_{gf.stem}_EXIT=$?"')

    header = [
        "set -x",
        "cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot",
        f"mkdir -p {out_dir}/pre_input_contract",
        "# 由 scripts/a_backfill_input_contract.py 生成：按产物自带的 checkpoint/replan_every 反推同参命令。",
        "# 重评只加字段，既有数字必须逐项不变（跨进程确定性已验证）。原产物 cp 留档，不 mv、不 rm。",
    ]
    body = header + lines + ['echo "BACKFILL_INPUT_CONTRACT_ALL_DONE"']
    text = "\n".join(body) + "\n"

    print(f"缺字段的评测产物: {len(need)} 份（被 {sum(len(v) for v in need.values())} 个门禁产物引用）")
    for s in skipped:
        print("  [跳过]", s)
    for u in unresolved:
        print("  [无法反推命令，checkpoint 字段缺失或路径不存在]", u)
    if args.emit and not args.dry_run:
        Path(args.emit).write_text(text)
        os.chmod(args.emit, 0o755)
        print(f"已写出: {args.emit}（{len(lines)} 行命令）")
    else:
        print(text)


if __name__ == "__main__":
    main()
