#!/usr/bin/env bash
# 档 5 护栏 G1 · 专家动作流回归（房规：改完 mg_expert.py 必须过这条，否则档 5 全部作废）
#
# 为什么这条是唯一可信的回归锚（坑 39③）：策略评测是**随机**的（flow-matching 采样没钉种子，
# n=20 的 1σ ≈ 11 pp），拿它做回归只会看到噪声。mg_ceiling.py 把噪声流钉死成 default_rng(12345)，
# 同参数重跑 = 逐比特相同的轨迹，所以「专家上界」是本项目唯一可复现的锚。
#
# 判据（逐局逐比特，不看聚合率）：
#   * 每局 success / success_step / steps / max_lift_cm / min_dist_to_target_cm /
#     success_relaxed / success_step_relaxed / delivered_tipped / final_tilt_deg 全部相同；
#   * 聚合 严格 14/20 ∧ 放宽 20/20 必须与 runs/s2f_ceiling_rev_test20_n05 一致。
#   code_sha256_16 **允许不同**（本次就是给 mg_expert.py 加了 resume()，文件哈希必然变）；
#   这条护栏查的正是「文件变了但行为没变」。
set -euo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
cd "$MG"
source code/env.sh
REF="$MG/runs/s2f_ceiling_rev_test20_n05"
# 输出目录可用 G1_NEW 覆盖（档 5.1 起用 runs/s5_1_g1_*，免得覆盖档 5 判定里引用的那份证据；坑 40）。
# ⚠️ 本脚本「有产物就跳过」⇒ **改完 mg_expert.py 必须换一个 G1_NEW**，否则拿到的是旧代码的产物、PASS 是假的。
NEW="${G1_NEW:-$MG/runs/s5_g1_ceiling_rev_test20_n05}"
[ -f "$REF/ceiling_summary.json" ] || { echo "[G1] 参考锚不存在：$REF"; exit 1; }
echo "[G1] 被测 mg_expert.py sha16=$(sha256sum "$MG/code/mg_expert.py" | cut -c1-16)  输出=$NEW"
echo "[G1] 参考锚 sha16=$(python3 -c "import json;print(json.load(open('$REF/ceiling_summary.json'))['code_sha256_16']['mg_expert.py'])" 2>/dev/null || echo '?')"

if [ ! -f "$NEW/ceiling_summary.json" ]; then
  echo "[G1] === 重跑专家上界（reverse 20 局 seed7000 noise0.05）=== $(date +%H:%M:%S)"
  "$MG_PY" code/mg_ceiling.py --task-mode reverse --episodes 20 --seed-mode random --seed 7000 \
      --noise 0.05 --out "$NEW" 2>&1 | grep -E "^  ep|专家上界|放宽口径|Error|Traceback" || true
fi
[ -f "$NEW/ceiling_summary.json" ] || { echo "[G1] 新上界没落盘"; exit 1; }

"$MG_PY" - "$NEW/ceiling_summary.json" "$REF/ceiling_summary.json" <<'PY'
import json, sys
new, ref = (json.load(open(p)) for p in sys.argv[1:3])
print(f"[G1] 出处 新={sys.argv[1]}")
print(f"[G1]      参考={sys.argv[2]}")
FIELDS = ("seed","success","success_step","steps","max_lift_cm","min_dist_to_target_cm",
          "success_relaxed","success_step_relaxed","delivered_tipped","ever_in_target_box",
          "final_tilt_deg","regrasp","slip")
assert len(new["per_episode"]) == len(ref["per_episode"]), "局数不同"
bad = []
for a, b in zip(new["per_episode"], ref["per_episode"]):
    diff = {k: (a.get(k), b.get(k)) for k in FIELDS if a.get(k) != b.get(k)}
    if diff:
        bad.append((a.get("ep"), diff))
n_s, n_r = new["n_success"], new["n_success_relaxed"]
r_s, r_r = ref["n_success"], ref["n_success_relaxed"]
print(f"[G1] 严格 {n_s}/{new['episodes']} (参考 {r_s})   放宽 {n_r}/{new['episodes']} (参考 {r_r})")
print(f"[G1] 新 mg_expert.py sha16={new['code_sha256_16']['mg_expert.py']}  "
      f"参考={ref['code_sha256_16']['mg_expert.py']}（允许不同：本次是纯增量加 resume()）")
if bad:
    for ep, d in bad:
        print(f"[G1][FAIL] ep{ep} 逐局不一致：{d}")
    raise SystemExit(f"[G1] FAIL：{len(bad)} 局动作流变了 ⇒ resume() 不是纯增量，档 5 作废")
assert (n_s, n_r) == (r_s, r_r), f"[G1] FAIL：聚合口径变了 {(n_s,n_r)} vs {(r_s,r_r)}"
assert (n_s, n_r) == (14, 20), f"[G1] FAIL：与文档记载的锚 严格14/20 放宽20/20 不符：{(n_s,n_r)}"
print("[G1] PASS：20 局逐局逐比特复现，严格 14/20 ∧ 放宽 20/20 ⇒ resume() 是纯增量")
PY
echo "[G1] done $(date +%H:%M:%S)"
