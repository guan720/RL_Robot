#!/usr/bin/env bash
# 链路看门狗：每 TICK 秒把「每条自动化链的状态」写成一行心跳，专门用来抓**静默死亡**。
#
# 为什么要有它（README 坑 22(e)）：
#   2026-10-01 01:36，档 2 的关门评测链 chain_s2_eval.sh 被一个同名残留进程骗过 pgrep，
#   提前醒来 -> 找不到检查点 -> FATAL 自杀。训练照跑 6.6 小时，**门没人收**，
#   日志里只有一行 FATAL，凌晨无人盯，02:05 复查进程表才发现。
#   「起过」不等于「还在等」；所以这里按**链 -> 完成产物**清单对账：
#     RUNNING = 进程还在；DONE = 产物已落盘（进程退出是正常的）；
#     MISSING = 进程没了 **且** 产物也没有 => 静默死亡，写进 logs/ALERTS.log 报警。
#   判完成的证据一律是磁盘产物，不是进程状态翻转（同坑 22(e) 的房规）。
#
# 注意：本脚本**绝不**把 `job_name=...` 之类的训练 pattern 写进命令行或子进程，
#       否则会自伤等待方（README 坑 22(b)）——训练进度改从 meta/train.log 读。
set -uo pipefail
MG="/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05"
cd "$MG"
# 上限 66.7 h（MAX_TICKS=400 × TICK=600 s）：**2026-10-05 20:5x 为档 8D 重启**（清单加 s8d 一条）。
#   8D = 两个新 seed 串行 ≈ 2×(8.4 h 训练 + 1.2 h 扫描 + ~1 h 评测) ≈ **19~20 h** ⇒ ETA ~2026-10-06 15:30~16:30；
#   本次重启后的 66.7 h 窗覆盖到 2026-10-08 下午 ⇒ 不会在 D4 关门前先瞎掉。
#   （历史）上一次盯的是档 7F/7G + 档 8A/8C（2026-10-04 发车），已于 2026-10-05 20:03 全部 DONE 后自行收工。
#   档 8 全链最多 ~43 h（8A/8B 采集 3~5 h + 8C 10 h + 条件 8C-ctl 10 h + 条件 8D 20 h），
#   它等 s7f.done（~23:15）才开工 ⇒ 最迟 2026-10-06 晚间收；本次重启后的 66.7 h 窗覆盖到
#   2026-10-07 下午 ⇒ 不会在任何一段扫描/关门前先瞎掉。
#   7F 最长分支 ≈12.7 h（F1+F2 回溯 1.2 h + F3 归因 2.5 h + F4 lr 对照 8.5 h）⇒ 最迟 ~23:20 收；
#   7G 是**条件发车**（等 s7f.done + `7G_TRIGGER=YES`），三发 bs8/18000 步串行 ≈22.4 h
#   ⇒ 最早 ~10-05 13:00 收，最迟（7F 走 F4 分支再触发不了 7G）根本不发车。
#   66.7 h 的窗覆盖到 2026-10-07 05:20 ⇒ 不会在任何一段扫描/关门前先瞎掉
#   （坑 22(e) 的原始事故正是「看门狗先死、门没人收」这个形状）。
#   历史：这一行原来写的是档 7C 的 ETA（2026-10-05 16:30）；7C 已按预注册正确跳过（runs/s7c.SKIPPED）。
TICK="${TICK:-600}"
MAX_TICKS="${MAX_TICKS:-400}"                 # 400×600 s = 66.7 h 上限
LOG="$MG/logs/chain_watchdog.log"
ALERT="$MG/logs/ALERTS.log"
RUN_S2="$MG/runs/pi05_mix60f60r_s2"

# 清单：进程 pattern（转义点，避免坑 22(a) 子串误匹配）| 完成产物 | 短键 | 人类可读名
# 短键必须是纯 ASCII：中文过 `cut -c` 会按字节截断成乱码（第一版就是这么花的）。
#
# 已摘除的一条：`chain_s1_kcurve_tail.sh`（补 6500/7000/7200 三个 K=10 val 点）。
#   它存在的唯一目的是「若档 1 不达标，用来在『继续训练』和『数据翻倍』两条预案之间选一条」
#   （见该脚本自己的头注释）。档 1 已关门通过（未见 20 局 K=10 = 16/20 = 80%，门 50%），
#   预案问题**已经不存在**，这三个点只会白占 GPU（档 2 训练是当前唯一长杆），
#   还可能被后人误读成「档 1 当初数据不够」。02:16 于睡眠中 kill，零产出零损失。
MANIFEST=(
  'code/chain_s1_k\.sh|runs/s1_k1_test_rand20/eval_summary.json|s1k|档1 K 扫描(定版门+K25+K1)'
  'code/chain_s1_confirm\.sh|runs/s1_gate_test_rand20_k10_rep3/eval_summary.json|s1confirm|档1 主门复跑(rep2/rep3)'
  'code/chain_s2_train\.sh|runs/pi05_mix60f60r_s2/checkpoints/014400/pretrained_model/model.safetensors|s2train|档2 训练(14400步)'
  'code/mg_sweep_bidir\.sh|runs/pi05_mix60f60r_s2/sweep_bidir/step_14000_rev/eval_summary.json|s2sweep|档2 双向检查点扫描'
  'code/chain_s2_eval\.sh|runs/s2_gate_rev_test_rand20_k50/eval_summary.json|s2gate|档2 关门评测(7组)'
  'code/chain_s2_confirm\.sh|runs/s2_gate_rev_test_rand20_k10_rep2/eval_summary.json|s2confirm|档2 TEST两组复跑(定噪声)'
  'code/chain_s2b\.sh|runs/s2_crossinstr/crossinstr_summary.json|s2b|档2b 交叉指令探针(fr/rf各20局)'
  'code/chain_s2_verdict\.sh|runs/S2_VERDICT.md|s2verdict|档2 判定落盘(S2_VERDICT.md)'
  'code/chain_s3\.sh|runs/pi05_rand60_s3_seed3000_test_rand20_k50/eval_summary.json|s3|档3 三训练seed(2000/3000)'
  # 档 2 修正关门：关门检查点从 last(014400) 换成 val 选出的 011000，重读 TEST。
  # 完成证据是 s2fix.done（链末尾才写），不是某一格 eval_summary —— 中间任何一格挂了都不算完成。
  'code/chain_s2fix\.sh|runs/pi05_mix60f60r_s2/s2fix.done|s2fix|档2 修正关门(val选点011000,rev×3+fwd×2+ctrl×2)'
  'code/chain_s2c_jointbase\.sh|runs/pi05_mix60f60r_s2/jointbase.done|s2cjb|档2c 联合基线补读(反向TEST 到 80 局)'
  'code/chain_s2c\.sh|runs/pi05_rev60_s2c/s2c.done|s2c|档2c 反向单任务消融(7600步+门+护栏)'
  'code/chain_s3_confirm\.sh|runs/s3_confirm.done|s3confirm|档3 复跑(seed2000/3000 各补到 60 局)'
  # 档 2c 判定**之后**的补读：G2 加功效(40 局真训练 seed 5062..5071，坑 32) + A 类抓空几何定位
  # (H1 横向/H2 深度/H3 时机；A 类占失败 44%、是最大的盘子)。这条链自己会等 s2c.done，
  # 所以在 s2c 完成前它一直是 RUN 而不是 MISSING —— 完成证据是链末尾才写的 s2d_diag.done。
  'code/chain_s2d_diag\.sh|runs/s2d_diag.done|s2d|档2c 判定后补读(G2 加功效 + A 类抓空几何定位)'
  # 档 2e 数据侧：重收 60 正向 + **120** 反向 -> data/mix60f120r。这是 R1/R2/R3 **三个分支都要**
  # 的无regret 动作（2:1 配比 = R1 的处方本身；反向数据翻倍 = R2 的处方），所以判定一落盘就发车。
  # 它自己会等 s2c.done，完成证据是链末尾才写的 s2e_data.done；失败会另写 s2e_data.FAILED，
  # 届时本清单报 MISSING + 报警（这正是我们要的：收数据静默失败 = 白等一小时）。
  'code/chain_s2e_data\.sh|runs/s2e_data.done|s2edata|档2e 数据(60正向+120反向, 严格超集对账)'
  # 档 2e 训练+关门：等 s2e_data.done **和** s2c.done，且要求档 2c 的判定「可用」
  #（护栏作废 / 判定悬空 / 出现「反而更差」这种矛盾结果，一律 exit 6 停下来等人看）才自动发车。
  # 10 h 的 GPU 不能押在一个作废的消融上。完成证据是链末尾才写的 s2e.done。
  'code/chain_s2e_train\.sh|runs/pi05_mix60f120r_s2e/s2e.done|s2etrain|档2e 训练+关门(2:1配比,反向TEST 4读80局)'
  # 档 2f 放宽口径复判（用户 2026-10-02 授权：送到目标区为首要条件，侧躺算送到但打标）。
  # 完成证据是链末尾才写的 s2f_relax.done；阶段 A 的严格口径逐局回归不过闸就写 s2f_relax.FAILED，
  # 届时本清单报 MISSING + 报警（判据被改坏 = 后面所有放宽读数都不可信，必须人来）。
  'code/chain_s2f_relax\.sh|runs/s2f_relax.done|s2f|档2f 放宽口径复判(上界回归+档2c/档2 各4x20+补真22000)'
  # 档 3r 反向 seed 稳健性：反向至今只有一个训练 seed（1000），过门可能是 seed 运气。
  # 自己等 s2e.done，且 S2E_VERDICT 若是 P3（处方=停止加数据）或护栏作废就 exit 6 停下来等人。
  # 18 h GPU 的长杆，完成证据是链末尾才写的 s3r.done。
  'code/chain_s3r_seed\.sh|runs/s3r.done|s3r|档3r 反向 seed 稳健性(2000/3000 各 22000 步 + 4x20)'
  # 档 4r 反向 K 曲线：正向档 4 已量过 K=1≈K=10≫K=25≈K=50，反向只在 K=10 上读过数。
  'code/chain_s4r_kcurve\.sh|runs/s4r.done|s4r|档4r 反向 K 曲线(K=25/50/1 各 20 局)'
  # 档 5 Harness 接管：G0a(外壳等价) -> G0b 3×20(观察模式) -> 正式 3×20(接管打开) -> 判定。
  # 与档 3r seed 3000 训练**并发**（34+10 < 80 GB），实时性门不在本链判（产物 timing_isolated=false）。
  # 完成证据是链末尾才写的 s5.done；判定落在 runs/S5_VERDICT.md。
  'code/chain_s5_harness\.sh|runs/s5.done|s5|档5 Harness 接管(G0a/G0b/正式3x20/判定)'
  # 档 5 实时性门（≤50 ms/step）的**隔离**读数：自己等 s5.done + s3r.done + GPU compute 进程表为空。
  # 完成证据 s5_timing.done，判定落在 runs/S5_TIMING.md。它长时间处于「等」是正常的，不是 MISSING。
  'code/chain_s5_timing\.sh|runs/s5_timing.done|s5t|档5 实时性隔离读数(<=50ms/step 门)'
  # 档 3r FAIL 处方第 1 步：seed 2000 的 val 曲线（11 格 × 20 局）+ 与档 2e(seed 1000) 的 epoch 对齐对表。
  # 自己等 S3R_VERDICT.md + s3r.done + s5_timing.done（不和隔离实时性读数抢 GPU）。
  # 完成证据 s3r_sweep_seed2000.done，对表落在 runs/_diag/epoch_curve_s3r_seed2000.md。
  'code/chain_s3r_sweep_seed2000\.sh|runs/s3r_sweep_seed2000.done|s3rsweep|档3r处方 seed2000 val曲线(11格x20局)'
  # 档 3r 处方第 2 步：seed3000 的 11 格 val 曲线 + 与 seed1000/seed2000 的两份 epoch 对齐对表。
  #   要答的是「好 seed 是不是全程都好」⇒ 决定能不能用便宜的早期 val 探针筛坏 seed。
  'code/chain_s3r_sweep_seed3000\.sh|runs/s3r_sweep_seed3000.done|s3rsweep3k|档3r处方第2步 seed3000 val曲线+两份对表'
  # 档 6 格 6A：三 seed 各 4 rep x 20 局的机理分桶（复用 mg_diag_miss.py，零 GPU）。
  'code/chain_s6_geom_a\.sh|runs/s6_geom_a.done|s6a|档6A 三seed机理分桶(240局,零GPU)'
  # 档 7A：batch / gradient-checkpointing 的代价探针（s/step + 峰值显存 + 等 epoch 投影）。
  #   在决定烧 3x7h 训大 batch 之前先把代价量出来（坑 53/57 的房规）。
  'code/chain_s7_probe\.sh|runs/s7_probe.done|s7a|档7A batch/grad-ckpt 代价探针(5配置)'
  # 档 7B 主实验：10 条发车闸 -> 7A-2 梯度噪声探针 -> 机理闸(MECH_NO 就写 s7b.HELD 停下,不烧 7h)
  #   -> bs32/5500 步等 epoch 训练(seed2000) -> last 软链核对 -> 11 格 val 扫描 -> TEST 4x20 + 正向护栏
  #   -> 配对符号检验(M1) -> 判定 runs/S7_VERDICT.md。完成证据是链末尾才写的 s7b.done；
  #   若写了 s7b.HELD / s7b.FAILED，本清单会报 MISSING + 报警（这正是我们要的：都需要人来看）。
  'code/chain_s7b\.sh|runs/s7b.done|s7b|档7B bs32等epoch(seed2000)+11格扫描+TEST关门+判定'
  # 档 7C **条件发车**：等 s7b.done + 预注册闸（S7_VERDICT.md 的命中行必须是 M1∧M2∧M3 全过）
  #   才发 seed 1000/3000 两发（同配方 bs32/5500步/lr2e-4），各自 11 格 val 扫描 + TEST 4×20 + 正向护栏，
  #   收尾出 6 条曲线总览（batch8×3 + bs32×3）与 runs/S7C_VERDICT.md（C1~C3，门是 C2：最差 seed ≥50%）。
  #   闸不过 ⇒ 写 runs/s7c.SKIPPED（预注册的合法终态，下面的 SKIPPED 兜底会把它当 DONE，不报警）。
  'code/chain_s7c\.sh|runs/s7c.done|s7c|档7C 条件发车(bs32 seed1000/3000)+扫描+TEST+S7C_VERDICT'
  # 档 7F：7B「不采信」之后的归因 + epoch 预算回溯诊断（预注册 runs/S7F_PREREG.md）。
  #   F1/F2 = 三个 batch8 seed 的 018000（epoch 3.102）在 TEST 上（零训练）-> 早期触发读数；
  #   F3 = bs8/5500 步（与 7B 同更新数，只排除 H-B）-> runs/S7F_DIAG.md（含机器可读行 7G_TRIGGER=）；
  #   仅当 TRIGGER=NO 才续跑 F4（bs32/5500/lr1e-4，与 7B 唯一差 lr）+ 11 格扫描 + 诊断重跑。
  #   完成证据是链末尾才写的 s7f.done；写了 s7f.FAILED 就报 MISSING + 报警（判定工具 rc=3 也算失败）。
  'code/chain_s7f\.sh|runs/s7f.done|s7f|档7F 归因(F1/F2回溯+F3步数对照)+epoch预算诊断S7F_DIAG'
  # 档 7G **条件发车**：等 s7f.done + S7F_DIAG.md 的 `7G_TRIGGER=YES` 才发；
  #   新 seed 4000/5000/6000、bs8、18000 步（=3.102 ep，闸里现算对账）、save_freq 2000（9 格）；
  #   每 seed：9 格 val 扫描 + TEST 反向 4×20 + 正向护栏 20 -> runs/S7G_VERDICT.md（G1 主门=最差 seed ≥50%）。
  #   不触发 ⇒ 写 runs/s7g.SKIPPED（预注册合法终态，上面的 SKIPPED 兜底当 DONE，不报警）。
  'code/chain_s7g\.sh|runs/s7g.done|s7g|档7G 缩短epoch前瞻验证(新seed4000/5000/6000)'
  # 档 8A/8B：纠正数据采集 + 建合并集（预注册 runs/S8_PREREG.md，等 s7f.done 才开工）。
  #   三种终态：s8a.done（A1/A2/A3 三门全过 + B1/B2/B3 对账全过）；
  #   s8a.HELD（产出率/质量不够 ⇒ 预注册分支「停下等人」，下面的 HELD 分支报**一次**警，不每 tick 刷）；
  #   s8a.FAILED（链本身出错 ⇒ 走 MISSING + 每 tick 报警，这是真警）。
  'code/chain_s8a\.sh|runs/s8a.done|s8a|档8A/8B 纠正数据采集(80局标定+>=7000帧)+建合并集mix60f120r_c1'
  # 档 8C：主实验（mix60f120r_c1 **全集** / bs8 / 22000 步 / lr1e-4 / seed2000）+ 11 格 val 扫描
  #   + TEST 关门（反向 4×20 seed7000.. + 正向 1×20 seed2000..）-> runs/S8_VERDICT.md
  #   （D1 主门 ≥40/80=50%、D2 正向护栏掉幅 ≤15pp）；D1∧D2 过才**条件发车** 8C-ctl（D3 配对归因）。
  #   8A 暂缓 ⇒ 本链写 runs/s8c.SKIPPED（合法终态，SKIPPED 兜底当 DONE，不报警）。
  'code/chain_s8c\.sh|runs/s8c.done|s8c|档8C 纠正数据主实验(22000步)+TEST关门+S8_VERDICT(+条件8C-ctl)'
  # 档 8D **条件发车**（2026-10-05 20:45 已发车，PID=SID=334638）：闸读 runs/s8c.done 的
  #   S8_D1=PASS∧S8_D2=PASS + runs/S8_VERDICT.md 的 ^S8_D3=PASS ⇒ 新 seed **4000/5000**、
  #   **同一份纠正集** mix60f120r_c1 全集，配方与 8C 逐项相同（bs8/22000 步/lr1e-4/save_freq2000）；
  #   每 seed：11 格反向 val 扫描（与 8C 同数据集同 stats ⇒ 干净配对）+ TEST 反向 4×20 + 正向 1×20（副读数、不是门）
  #   -> 重出 runs/S8_VERDICT.md，主读 **D4 = min(seed2000,4000,5000) 反向 TEST 放宽 ≥ 40/80**。
  #   完成证据是链末尾才写的 s8d.done；写了 s8d.FAILED 报 MISSING + 报警（链**不自动降门、不自动重跑**）。
  'code/chain_s8d\.sh|runs/s8d.done|s8d|档8D 新seed4000/5000(同纠正集)+11格扫描+TEST关门+D4'
  # 档 8D 的**机理旁读**（零 GPU、**不是门**）：两个实例（seed4000 / seed5000）各等自己那臂的 11 格 val 扫描齐
  #   后跑重放台，对照臂 = **8C**（同数据集 ⇒ 同 normalizer，唯一差 = 训练 seed ⇒ 干净 1:1）；
  #   产物 runs/_diag/s8_mech_d{4000,5000}/COMPARE.md + MECH.done。
  #   ⚠️ 清单只能挂一条：两个实例的 cmdline 相同（env 前缀不进 cmdline）⇒ pattern 命中任一即 RUN，
  #   完成产物挂**后收工的那个**（seed5000，它的 val 扫描晚 ~9 h）；所以「4000 死、5000 活」会显示 RUN
  #   （可接受：这条不是门，读数缺失只影响机理解释，不影响 D4）。
  'code/chain_s8mech\.sh|runs/_diag/s8_mech_d5000/MECH.done|s8mechd|档8D 机理旁读(重放台/零GPU/不是门,seed4000+5000)'
  # 档 7H：便宜配方（bs32 / lr1e-4 / 5500 步 = 3.791 ep）在 **3 个新训练 seed**（11000/12000/13000）上的前瞻验证
  #   （预注册 runs/S7H_PREREG.md 2026-10-05 21:04 落盘；21:12 setsid 发车 PID=SID=346154）。
  #   **等 runs/s8d.done 才开工**（不抢卡）⇒ 在那之前一直显示 RUN；上游写 s8d.FAILED ⇒ 本链写 runs/s7h.SKIPPED
  #   （预注册 §7 的合法终态，SKIPPED 兜底当 DONE，不报警）。主门 H1 = 三 seed 反向 TEST 放宽 min ≥ 40/80。
  'code/chain_s7h\.sh|runs/s7h.done|s7h|档7H 便宜配方bs32/lr1e-4/5500步×3新seed(等s8d.done)'
  # 档 8D 的**独立出身核对**旁链（零 GPU、**不是门**、不改 S8_VERDICT.md 一个字）：等 s8d.done 后跑
  #   code/mg_prov_s8d.py（自测 19/19、正对照 = 已知good 的 8C 臂全对、三条负对照全被抓）⇒ runs/s8d_prov.md
  #   + runs/s8d_prov.done（含 PROV_RC=0 可采信 / 3 🚫不采信）。上游 s8d.FAILED ⇒ 写 s8d_prov.SKIPPED（合法终态）。
  #   为什么要它：mg_verdict_s8.py 的 prov() 只覆盖 8C/8C-ctl ⇒ D4 的输入出身原本只靠 chain_s8d.sh 自己核。
  'code/chain_s8d_prov\.sh|runs/s8d_prov.done|s8dprov|档8D 独立出身核对(零GPU/不是门,PROV_RC)'
)

train_progress () {   # 从 tqdm 行取「当前步/总步 + 剩余时间」，不碰进程表
  # 扫**所有** runs/*_meta/train.log，取最近改动的那一份：写死单一 run 的话，
  # 档 2 训练结束后这一格就永远是 n/a，档 2c 跑了 4 小时也看不见进度（20:55 实测吃到）。
  # 用 mtime 挑「当前这一发」，比在清单里再维护一份 run 名省事，也不会指错。
  local f=""
  f=$(ls -1t "$MG"/runs/*_meta/train.log 2>/dev/null | head -1)
  [ -n "$f" ] && [ -f "$f" ] || { echo "n/a"; return; }
  local prog
  # tqdm 形如 `379/7600 [11:36<2:50:08, 1.83s/step]`；总步数不写死，跟着当前 run 走
  prog=$(tr '\r' '\n' < "$f" | grep -oE "[0-9]+/[0-9]+ \[[0-9:]+<[0-9:]+" | tail -1)
  [ -n "$prog" ] && { echo "$(basename "$(dirname "$f")" | sed 's/_meta$//'):${prog}"; return; }
  echo "n/a"
}

# tick 编号接着日志已有的行数走：本脚本会被反复重启（改清单就得 kill 再启，README 坑 22(d)），
# 每次都从 tick=1 开始会让日志里出现一串重复编号，看不出心跳有没有断过。
t0=$(wc -l < "$LOG" 2>/dev/null || echo 0)
ndone=0
for ((t = t0 + 1; t <= t0 + MAX_TICKS; t++)); do
  ts=$(date '+%F %H:%M:%S')
  line="[$ts] tick=$t"
  miss=""
  hold=""
  ndone=0
  for entry in "${MANIFEST[@]}"; do
    pat="${entry%%|*}"; rest="${entry#*|}"
    art="$MG/${rest%%|*}"; rest2="${rest#*|}"; key="${rest2%%|*}"; name="${rest2#*|}"
    # 「条件发车」链可以合法地决定**不发车**（写 <同名>.SKIPPED）：那也是终态，不是静默死亡。
    #   不认它的话，一次预注册分支的不发车会换来几十小时的假警（每 tick 一条），
    #   把真警淹掉 —— 报警文件的价值在于「响就必须有人看」。
    if [ -f "$art" ] || [ -f "${art%.done}.SKIPPED" ]; then st="DONE"; ndone=$((ndone + 1))
    elif [ -f "${art%.done}.HELD" ]; then
      # HELD = 预注册分支「停下等人决定」，**不是**静默死亡：预注册 §3 明确要求「+ 看门狗报警」，
      #   所以不能当 DONE 静默吃掉；但也不能每 600 s 刷一条（那正是 SKIPPED 兜底要解决的假警淹没）。
      #   折中：靠 ALERTS.log 里有没有这一条去重 ⇒ **只报一次**，之后每 tick 只在心跳行标 HELD。
      st="HELD"
      grep -q "!!! HELD  ${name}" "$ALERT" 2>/dev/null \
        || hold="$hold\n[$ts] !!! HELD  ${name}  预注册分支：停下等人（$(head -c 220 "${art%.done}.HELD" 2>/dev/null)）"
    elif pgrep -f "$pat" > /dev/null 2>&1; then st="RUN"
    else st="MISSING"; miss="$miss\n[$ts] !!! MISSING  ${name}  (pattern=${pat}  期望产物=${rest%%|*})"; fi
    line="$line  ${key}=${st}"
  done
  # 上下文：训练进度、扫描已收检查点数、显存、正在跑的评测数
  sw=$(wc -l < "$RUN_S2/sweep_bidir/.done" 2>/dev/null || echo 0)
  # `pgrep -c` 在**零命中**时照样打印 "0"，但退出码是 1 ⇒ `|| echo 0` 会再补一个 0，
  # 于是 neval 变成 "0\n0"，把整行心跳撑成两行（02:59 实测吃到）。用 `|| true` 吃掉退出码即可。
  neval=$(pgrep -cf "code/mg_eval\.py" 2>/dev/null || true); neval="${neval:-0}"
  gpu=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader 2>/dev/null | head -1)
  line="$line | train=$(train_progress) sweep_done=${sw}/14 evals_running=${neval} gpu=${gpu}"
  echo -e "$line" >> "$LOG"
  [ -n "$miss" ] && echo -e "$miss" >> "$ALERT"
  [ -n "$hold" ] && echo -e "$hold" >> "$ALERT"
  [ "$ndone" -eq "${#MANIFEST[@]}" ] && { echo "[$ts] 全部链已完成，看门狗收工" >> "$LOG"; exit 0; }
  sleep "$TICK"
done
