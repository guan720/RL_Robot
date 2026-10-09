import pathlib,json,subprocess,hashlib,datetime,re
root=pathlib.Path(__file__).parent
out=root.parent.parent
pins=[]
for d in sorted(root.glob('*_git')):
 commit=subprocess.check_output(['git','-C',str(d),'log','-1','--format=%H%x09%cI%x09%s'],text=True,encoding='utf8').strip().split('\t')
 pins.append({'local':d.name,'commit':commit[0],'commit_date':commit[1],'subject':commit[2],'tree':str((d/'tree.txt').relative_to(out))})
 for p in [d/'text'/'LICENSE']:
  if p.exists():print(d.name,p.read_text(encoding='utf8').splitlines()[:4])
reads=[
('fluxdagger_git','src/dagger/launch/dagger.launch','launch nodes and configured topic inputs','1-100'),
('fluxdagger_git','src/dagger/config/default.yaml','topic and arm profiles; collector/reward defaults','24-51,95-145'),
('fluxdagger_git','src/dagger/scripts/dagger_controller_node.py','publish_global_state; _set_arms_subscribe_inference; _set_front_arms_subscribe_human; handle_human_mode; handle_inference_mode','165-190,333-387'),
('fluxdagger_git','src/dagger/scripts/arm_node.py','PiperArm construction; subscribe_cmd_callback','70-107,202-219'),
('fluxdagger_git','src/dagger/dagger/hardware/piper_arm.py','publish_master_joint; joint_slave_callback','200-245,314-386'),
('fluxdagger_git','src/dagger/scripts/dagger_collector_node.py','topic subscribers; _handle_finish_episode; _save_frame_from_synced; _pop_up_to; _build_action','115-165,398-448,598-751'),
('fluxdagger_git','src/dagger/dagger/collectors/sync_frame_collector.py','start_new_episode; set_human_mode; save_frame_from_synced; _save_data_parquet; record_raw_action_chunk; finish_episode interface','90-365,430-520'),
('fluxdagger_git','src/dagger_msgs/msg/GlobalState.msg','entire message','all'),
('fluxdagger_git','src/dagger_msgs/msg/EpisodeInfo.msg','entire message','all'),
('fluxdagger_git','src/dagger/scripts/qwen3_reward_node.py','_obs_callback; _run_inference; _publish_reward','117-163'),
('fluxdagger_git','tools/data_processing/parquet_to_mp4_npy.py','qpos/action export','162-175'),
('fluxvla_git','tools/arm_awbc/README.md','full training/data/weight contract','all'),
('fluxvla_git','fluxvla/weighters/arm_rabc.py','ArmRABCWeighter and ArmAWBCWeighter','all'),
('fluxvla_git','fluxvla/datasets/arm_dataset.py','_compute_interval_targets_from_progress; __getitem__ progress requirement','98-105,156-173; surrounding inspected via rg'),
('fluxvla_git','fluxvla/models/vlas/arm_reward_model.py','_build_success_targets; forward; predict_advantage loss/output relevant lines','198-304,312-378; relevant lines located/read via rg'),
('fluxvla_git','scripts/compute_arm_awbc_progress.py','_build_output_rows; _write_progress_parquet; main','80-180'),
('fluxvla_git','tools/arm_awbc/progress_reconstruction.py','extract_last_interval_delta; build_cumulative_progress; run_strided_episode_inference input','26-150'),
('fluxvla_git','fluxvla/transforms/attach_rabc_weight.py','_build_weighter; AttachRABCWeight.__call__','25-63'),
('fluxvla_git','fluxvla/models/vlas/pi05_flowmatching.py','PI05FlowMatching inherits PI0FlowMatching','18-68; inheritance inspection'),
('fluxvla_git','fluxvla/models/vlas/pi0_flowmatching.py','forward flow loss and weight handoff','649-765'),
('fluxvla_git','scripts/train.py','dataset/statistics/config/tokenizer export and runner invocation','431-493'),
('fluxvla_git','fluxvla/engines/runners/ddp_train_runner.py','save_checkpoint key branches','335-358,406-414,470-494'),
('fluxvla_git','fluxvla/engines/runners/serving/ros_server.py','build_ros_policy_from_config','749-821'),
('futurertc_real_git','README.md','full branch README','all'),
('futurertc_real_git','infer/cobot-magic-real/deploy_policy_local_ours_batch_test.py','interpolate_action_sequence_with_boundaries; clip_grippers; send_reset; query_server; AsyncChunkFetcher; run_one_episode','131-171,344-408,503-630; output saving via rg'),
('futurertc_real_git','infer/ours_pi05/deploy_protocol.py','executed_slice; committed_actions_from_slice; build_padded_motion; save_gap_log','all'),
('futurertc_real_git','infer/ours_pi05/models/corrector.py','Corrector.__init__; __call__; author dataset identity claim','all'),
('futurertc_real_git','infer/openpi/deploy_policy_server_ours_local.py','init artifact load; reset; infer_ours; handle_obs','175-205,230-312,331-375'),
('futurertc_real_git','train/ours_pi05/train_predictor.py','module training claim; main optimizer/MSE/export','1-34,115-177,188-215'),
('futurertc_real_git','train/ours_pi05/fast_loader.py','_fill_one and producer context','80-140'),
('futurertc_real_git','train/ours_pi05/collect_latents.py','data/model-space and norm stats acquisition contract','1-48'),
('futurertc_libero_git','README.md','phases; assets; prerequisites','108-134,182-202,229-248; context via rg'),
('futurertc_libero_git','predictor/train.py','policy loss switch; optimizer param scope; loss assembly','238-261,286-319; flags via rg'),
('futurertc_libero_git','predictor/policy_loss/pi05.py','OfflinePi05PolicyLoss.__init__ policy freeze','55-100'),
('futurertc_kinetix_git','README.md','full mechanism/asset/dependency overview only; code not fully audited','all')]
manifest=[]
for f in ['download_manifest.json','download_more.json','download_final.json']:
 data=json.loads((root/f).read_text(encoding='utf8'));manifest.extend(data)
for x in reads:
 pass
web=[
('https://github.com/FluxVLA/FluxVLA','opened current repository README; primary source discovery'),
('https://github.com/FluxVLA/FluxDAgger','opened README and file overview'),
('https://github.com/JianghaiSCU/FutureRTC','opened main README and branch links'),
('https://arxiv.org/html/2609.22840v1','read IV-C/IV-D plus independent evaluation and baselines paragraphs; primary paper, not code'),
('https://arxiv.org/html/2607.24008v1','opened paper; detailed new claims grounded in branch source'),
('https://huggingface.co/limxdynamics/FluxVLAEngine','opened official model card; model family asset links and third-party licenses'),
('https://huggingface.co/datasets/limxdynamics/FluxVLAData','opened official dataset card; Apache-2.0 label'),
('https://github.com/FluxVLA/FluxDAgger/issues','read issue listing; demo entry only, no independent reproduction evidence'),
('https://github.com/JianghaiSCU/FutureRTC/issues','read cached issue listing; release question not used to infer current code unavailable'),
('https://github.com/JianghaiSCU/FutureRTC/issues/1','opened cached primary community issue; no code absence inference'),
('https://huggingface.co/datasets/limxdynamics/FluxVLAData/blob/main/README.md','web inaccessible; recovered via dataset landing page'),
('https://huggingface.co/limxdynamics/FluxVLA/blob/main/README.md','web inaccessible/wrong provisional repo name; corrected from official GitHub link to FluxVLAEngine')]
record={
 'round':'S2','track':'RL source and assets','date':'2026-09-23','scope':'static research only; no third-party installation, training, tests or model download',
 'initial_read':['AGENTS.md','embodied-scientist/START_HERE.md','embodied-scientist/ROLE.md','embodied-scientist/state/status.json','06/00_任务契约与进度.md','06/research/S1/00_根审总结与S2入口.md','06/research/S1/rl_frontier.md','04/research/01_VLA_RL扩展调研.md','06/appendices/02_异步动作时间轴与学习目标.md relevant takeover passages'],
 'questions_before_code':['Do correction ownership and post-controller commands remain attributable through save and BC?','Is ARM advantage a TD value or reconstructed progress weight?','Which FutureRTC branches exist and which parameters/losses does realworld update?','Do committed prefixes, late results, reset and takeover satisfy continuous C/E/D?','Does ForceRFT autonomous-segment return match preserving valid predecessors and isolating broken current slots?'],
 'pins':pins,'main_future_ref':'67cb0b0e46cf66a800cfd4a78a5bcbcf3d360794',
 'actually_read':[dict(snapshot=d+'/text/'+p,path=p,functions=fn,lines=lines) for d,p,fn,lines in reads],
 'web_visits':[dict(url=u,result=v) for u,v in web],
 'source_downloads':manifest,
 'transport_failures':['GitHub API repos endpoint returned HTTP 403 rate limit for each of 3 projects; no branch API result claimed','git ls-remote inherited dead 127.0.0.1:7890 proxy; command-local -c http.proxy= -c https.proxy= succeeded; no global config changed','partial clones with filter=blob:none and no checkout yielded metadata/tree only; selected checkout attempts failed with network reset/promisor-object/read errors; claims use successful raw text snapshots','wrong provisional fluxvla/engines/losses.py returned 404; tree located engines/losses/rabc.py, latter raw timeout; no full reducer verification claimed'],
 'new_evidence':[{'id':'F1','kind':'code fact + static counterexample','claim':'Default human arm subscription changes topic but collector command subscribers stay on model topic; zeros on absent messages; mode read at save time; action smoothing occurs downstream'}, {'id':'F2','kind':'code fact','claim':'ARM loss is interval CE plus success focal supervision; actor is weighted flow MSE, not this chain providing online TD'}, {'id':'F3','kind':'static inference from code, not executed test','claim':'No-done and constant cumulative interval scores fall back to linspace(0,1), yielding false-positive progress weights'}, {'id':'R1','kind':'code fact','claim':'Realworld predictor optimized by MSE only; corrector returns last committed absolute target; policy fixed'}, {'id':'R2','kind':'code fact','claim':'LIBERO consistency branch exists and keeps policy frozen; do not generalize realworld comment speculation'}, {'id':'R3','kind':'code fact + proposed race test','claim':'Realworld client waits at handoff; stop does not cancel already submitted worker; reset only clears server z_init; no generation contract in read paths'}, {'id':'FR1','kind':'paper specification + project comparison','claim':'ForceRFT beta=0 at takeover optimizes autonomous segment surrogate; current project isolates broken macro slot, preserves valid preceding one-step record; both retain selection-bias limits'}],
 'not_claimed':['Complete repo audit','Executed third-party tests','Successful install or real robot reproduction','Full third-party license review','Training history of released predictor weights','ForceRFT code or weight availability conclusively absent','No other superior research candidate exists'],
 'decision':'Keep RAPolicy native-learning and RT-EXPO realtime preflight priorities; fix recorder/gateway data semantics first; Flux weighted BC and FutureRTC predictor are conditional components; ForceRFT supplies a distinct segment-objective comparison; composite frozen policy evaluation retains its algorithmic editor/predictor/Q.'
}
(out/'rl_code_log.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
p=out/'rl_code.md';s=p.read_text(encoding='utf8').replace('L138–149、203–216','L140–149、203–216').replace('L310–316、362–366','L292–299、341–346');p.write_text(s,encoding='utf8')
print('REPORT',p.stat().st_size,'LOG', (out/'rl_code_log.json').stat().st_size,'READ ENTRIES',len(reads),'DOWNLOAD ATTEMPTS',len(manifest),'SUCCESS',sum(x.get('status')=='ok' for x in manifest))
