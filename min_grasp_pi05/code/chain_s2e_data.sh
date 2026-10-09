#!/usr/bin/env bash
# 档 2e · 数据侧准备（**无regret**：R1/R2/R3 三个分支都要它，所以在判定落盘后就发车，
#          不等我读完判定再动手 —— 那样会白等 45 分钟）。
#
# 干什么：重收一个 60 正向 + **120** 反向 的混合数据集 `data/mix60f120r`。
#   * rev:fwd = 2:1  ⇒ 这就是 R1（干扰确认）的处方「改数据配比」本身；
#   * 反向从 60 条加到 120 条、seed 覆盖翻一倍 ⇒ 这也是 R2（任务本身难）的处方「加反向数据」；
#   * R3 = 两个都要 ⇒ 还是它。
#
# 为什么"重收"比"复制一遍反向 episode"好：
#   复制能在**采样比例**上凑出 2:1，但反向的位姿多样性一点没变；而档 2c 的失败盘子
#   （A 类抓空 44%，见 runs/_diag/lift_profile.md）是**泛化**问题 —— TEST 7000..7019 是
#   没见过的随机位姿，专家上界 70% 而策略只有 37.5%。加真数据同时动了配比和多样性，
#   复制只动配比。
#
# 承重的三条护栏（任一不过 ⇒ 数据作废，不写 done 标记）：
#   G-A 集数必须真收满：mg_collect.py **收不满也不报错**（只在 0 条时才 fail），
#       所以必须由 MG_DATASET_CARD.json 反过来断言 forward=60 / reverse=120。
#   G-B 正向半边逐比特复现：--verify-forward-npz 已内建（不符则 rc=3）；这里只看 rc。
#       它保证新集的正向与档 1/档 3 的正向可比，不是"又换了一批数据"。
#   G-C 反向半边必须是旧 60 条的**严格超集**，且新 seed 不得撞留出窗口
#       （反向 TEST 7000..7019、G1 正向 TEST 2000..2019）。
#       不满足 ⇒ 「120 反向 vs 60 反向」的差里混进了"换数据"，比较作废。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
source "$MG/code/env.sh"; cd "$MG"

NAME="${NAME:-mix60f120r}"
FWD_N="${FWD_N:-60}"
REV_N="${REV_N:-120}"
OLD_FWD_NPZ="$MG/data/mix60f60r_raw.npz"
OLD_REV_NPZ="$MG/data/mix60f60r_rev_raw.npz"
NEW_FWD_NPZ="$MG/data/${NAME}_raw.npz"
NEW_REV_NPZ="$MG/data/${NAME}_rev_raw.npz"
CARD="$MG/data/$NAME/MG_DATASET_CARD.json"
INFO="$MG/data/$NAME/meta/info.json"
S2C_MARK="$MG/runs/pi05_rev60_s2c/s2c.done"
MARK="$MG/runs/s2e_data.done"
FAILMARK="$MG/runs/s2e_data.FAILED"
REPORT="$MG/runs/_diag/superset_${NAME}.md"
NEED_FREE_MIB="${NEED_FREE_MIB:-20000}"     # 只跑 EGL 渲染 + 物理，占不了多少显存；
NEED_DISK_GB="${NEED_DISK_GB:-40}"          # 但可以和档 2d 的评测并发
LOG="$MG/logs/collect_${NAME}.log"

[ -f "$MARK" ] && { echo "[s2e] 已完成（$MARK 存在），退出"; exit 0; }
fail () { echo "[s2e] FATAL $*" | tee -a "$FAILMARK"; date +"%Y-%m-%d %H:%M:%S $*" >> "$FAILMARK"; exit 1; }

# ── 0. 等档 2c 主链落地（绝不跟训练抢卡：实测并发把 1.36 s/步拖到 1.9 s/步）──────
for _ in $(seq 1 480); do [ -f "$S2C_MARK" ] && break; sleep 60; done
[ -f "$S2C_MARK" ] || fail "等了 8 h 还没见到 $S2C_MARK，先看 logs/chain_s2c.log"
echo "[s2e] 档 2c 主链已落地：$(cat "$S2C_MARK")  -> 开始收数据 $(date +%H:%M:%S)"

for _ in $(seq 1 120); do
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
  [ "${free:-0}" -ge "$NEED_FREE_MIB" ] && break
  echo "[s2e] 显存 free=${free}MiB < ${NEED_FREE_MIB}MiB，等 30 s ... $(date +%H:%M:%S)"; sleep 30
done

# ── 0b. 磁盘余量（数据集 ~6 GB；共享盘曾经 97% 满，别把别人的作业挤死）────────────
avail_gb=$(df -BG --output=avail "$MG" | tail -1 | tr -dc '0-9')
echo "[s2e] 磁盘余量 ${avail_gb} GB（门槛 ${NEED_DISK_GB} GB）"
[ "${avail_gb:-0}" -ge "$NEED_DISK_GB" ] || fail "磁盘只剩 ${avail_gb} GB，不够收 $NAME"

# ── 0c. 旧数据必须在（否则"超集"无从谈起）───────────────────────────────────────
for f in "$OLD_FWD_NPZ" "$OLD_REV_NPZ"; do [ -f "$f" ] || fail "缺旧 npz：$f"; done
echo "[s2e] 旧数据出处：$OLD_FWD_NPZ / $OLD_REV_NPZ"

# ── 1. 采集（参数与 mix60f60r 完全一致，只把反向目标从 60 提到 120）──────────────
# 复现性依据（mg_collect.py 头注释）：正向 noise_rng=default_rng(12345)、seed=1000+attempt；
# 反向 seed=5000+attempt；只保留成功局 ⇒ 同参数重跑走同一条确定性序列，
# 前 60 条反向应当与旧集逐比特相同，多出来的只是尾部新 seed（由 G-C 实测）。
CMD=("$MG_PY" code/mg_collect.py
  --mode mixed --episodes "$FWD_N" --reverse-episodes "$REV_N"
  --seed-mode random --seed-base 1000 --reverse-seed-base 5000
  --expert-noise 0.05 --img-size 224 --max-attempts-mult 3.0
  --name "$NAME" --overwrite
  --verify-forward-npz "$OLD_FWD_NPZ")
echo "[s2e] 命令：${CMD[*]}"
echo "[s2e] === 采集开始 $(date +%H:%M:%S)（预计 45–75 min；反向产出率约 0.645，120 条约需 186 次尝试）==="
"${CMD[@]}" > "$LOG" 2>&1
rc=$?
echo "[s2e] 采集退出 rc=$rc $(date +%H:%M:%S)"
tail -12 "$LOG"
[ "$rc" = "0" ] || fail "mg_collect.py 非 0 退出（rc=$rc）；rc=3 通常就是 G-B 正向没复现，看 $LOG"

# ── 2. 护栏 G-A：集数真收满了吗（mg_collect 收不满不报错，必须自己断言）──────────
[ -f "$CARD" ] || fail "没有 $CARD"
"$MG_PY" - "$CARD" "$FWD_N" "$REV_N" <<'PY'
import json, sys
card = json.load(open(sys.argv[1]))
want_f, want_r = int(sys.argv[2]), int(sys.argv[3])
pf, pr = card["phases"]["forward"], card["phases"]["reverse"]
print("[s2e][G-A] 出处 %s" % sys.argv[1])
print("[s2e][G-A] forward kept=%d/%d attempts=%d yield=%.3f"
      % (pf["kept"], pf["wanted"], pf["attempts"], pf["yield"]))
print("[s2e][G-A] reverse kept=%d/%d attempts=%d yield=%.3f seed_base=%d"
      % (pr["kept"], pr["wanted"], pr["attempts"], pr["yield"], pr["seed_base"]))
bad = []
if pf["kept"] != want_f:
    bad.append("正向只收到 %d，要 %d" % (pf["kept"], want_f))
if pr["kept"] != want_r:
    bad.append("反向只收到 %d，要 %d（产出率 %.3f；提高 --max-attempts-mult 再收）"
               % (pr["kept"], want_r, pr["yield"]))
if card.get("episodes_kept") != want_f + want_r:
    bad.append("episodes_kept=%s != %d" % (card.get("episodes_kept"), want_f + want_r))
if bad:
    print("[s2e][G-A] FAIL " + "；".join(bad)); sys.exit(11)
print("[s2e][G-A] OK  集数收满：%d 正向 + %d 反向 = %d 集 / %d 帧"
      % (pf["kept"], pr["kept"], card["episodes_kept"], card["frames"]))
PY
[ "$?" = "0" ] || fail "G-A 集数没收满（细节见上）"

# ── 3. 护栏 G-C：反向是旧 60 条的严格超集，且新 seed 避开留出窗口 ────────────────
[ -f "$NEW_REV_NPZ" ] || fail "没有 $NEW_REV_NPZ"
"$MG_PY" code/mg_check_superset.py \
    --old "$OLD_REV_NPZ" --new "$NEW_REV_NPZ" \
    --forbid-seed-range 7000:7019 --forbid-seed-range 2000:2019 \
    --report "$REPORT"
[ "$?" = "0" ] || fail "G-C 反向不是旧集的严格超集，或撞了留出 seed（详见 $REPORT）"

# 正向半边也过一遍同一把尺（应当"等长 + 逐比特相同"，mg_collect 的 G-B 已保证）
"$MG_PY" code/mg_check_superset.py --old "$OLD_FWD_NPZ" --new "$NEW_FWD_NPZ" \
    --forbid-seed-range 2000:2019 --forbid-seed-range 7000:7019 2>&1 | tail -8

# ── 4. 数据集自证：info.json 与 card 对得上（否则 lerobot 读出来的帧数会悄悄不同）──
[ -f "$INFO" ] || fail "没有 $INFO"
"$MG_PY" - "$INFO" "$CARD" "$FWD_N" "$REV_N" <<'PY'
import json, sys
info, card = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
want_eps = int(sys.argv[3]) + int(sys.argv[4])
print("[s2e][自证] 出处 %s vs %s" % (sys.argv[1], sys.argv[2]))
print("[s2e][自证] info.total_episodes=%d total_frames=%d total_tasks=%d | card.episodes_kept=%d frames=%d"
      % (info["total_episodes"], info["total_frames"], info.get("total_tasks", -1),
         card["episodes_kept"], card["frames"]))
bad = []
if info["total_episodes"] != want_eps:
    bad.append("info.total_episodes=%d != %d" % (info["total_episodes"], want_eps))
if info["total_frames"] != card["frames"]:
    bad.append("info.total_frames=%d != card.frames=%d" % (info["total_frames"], card["frames"]))
if info.get("total_tasks") != 2:
    bad.append("total_tasks=%s != 2（混合集必须是两个 task 字符串）" % info.get("total_tasks"))
if bad:
    print("[s2e][自证] FAIL " + "；".join(bad)); sys.exit(12)
print("[s2e][自证] OK  %d 集 / %d 帧 / 2 个 task" % (want_eps, info["total_frames"]))
PY
[ "$?" = "0" ] || fail "数据集自证不过（info.json 与 card 不一致）"

date +"%Y-%m-%d %H:%M:%S name=$NAME fwd=$FWD_N rev=$REV_N frames=$("$MG_PY" -c "import json;print(json.load(open('$CARD'))['frames'])")" > "$MARK"
echo "[s2e] done $(date +%H:%M:%S)  标记 -> $MARK"
echo "[s2e] 下一步：等 runs/S2C_VERDICT.md 出判定，再决定用这份数据训哪个配比（R1/R2/R3）"
