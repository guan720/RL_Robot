"""Build static research manifest from locally saved text; never imports source files."""
import datetime, hashlib, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parent
retrieval=json.loads((ROOT/'retrieval_log.json').read_text('utf-8'))
def read(name): return json.loads((ROOT/name).read_text('utf-8'))
versions={}
for name in ['lerobot_main','lerobot_release','openpi_main','openpi_report_commit']:
    d=read(name+'.json'); versions[name]={'sha':d['sha'],'url':d['html_url'],'commit_time':d['commit']['committer']['date']}
for name in ['lerobot_pr4452','lerobot_pr4454','lerobot_pr4398','lerobot_pr4122','openpi_pr960']:
    d=read(name+'.json');versions[name]={k:d.get(k) for k in ['state','merged','merged_at','merge_commit_sha','html_url']}
    versions[name]['head_sha']=d['head']['sha'];versions[name]['base_sha']=d['base']['sha']
versions['gr00t_weights']={'repo':'nvidia/GR00T-N1.7-3B','revision':'2fc962b973bccdd5d8ce4f67cc63b264d6886495','pin_method':'HF tree commit link -> commit page; fixed revision LICENSE opened via web tool','first_license_commit_visible_short':'6949d5d'}
web_success=[
 'https://github.com/huggingface/lerobot/pull/4452',
 'https://github.com/huggingface/lerobot/pull/4454',
 'https://github.com/huggingface/lerobot/pull/4398',
 'https://github.com/Physical-Intelligence/openpi/pull/960',
 'https://github.com/Physical-Intelligence/openpi/issues/958',
 'https://huggingface.co/nvidia/GR00T-N1.7-3B/tree/main',
 'https://developer.nvidia.com/blog/develop-humanoid-robot-policies-end-to-end-with-nvidia-isaac-gr00t/',
 'https://github.com/huggingface/lerobot/pull/4452/files',
 'https://github.com/huggingface/lerobot/pull/4398/files',
 'https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/strategies/dagger.py',
 'https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/examples/convert_jax_model_to_pytorch.py',
 'https://huggingface.co/nvidia/GR00T-N1.7-3B/commit/2fc962b973bccdd5d8ce4f67cc63b264d6886495',
 'https://huggingface.co/nvidia/GR00T-N1.7-3B/blob/main/LICENSE',
 'https://huggingface.co/nvidia/GR00T-N1.7-3B/blob/2fc962b973bccdd5d8ce4f67cc63b264d6886495/LICENSE',
 'https://github.com/dexmal/dexbotic/blob/main/docs/RLinfAsRLBackend.md',
 'https://github.com/dexmal/dexbotic',
 'https://raw.githubusercontent.com/huggingface/lerobot/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/rollout/inference/rtc.py',
 'https://github.com/huggingface/lerobot/pull/4454/files',
 'https://github.com/Physical-Intelligence/openpi/blob/46fe49901bfee3b6d8c768a755e86699d5006b48/examples/convert_jax_model_to_pytorch.py',
 'https://raw.githubusercontent.com/Physical-Intelligence/openpi/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models_pytorch/gemma_pytorch.py'
]
web_failure=[
 'https://huggingface.co/api/models/nvidia/GR00T-N1.7-3B',
 'https://github.com/dexmal/dexbotic/commits/main/',
 'https://github.com/huggingface/lerobot/commits/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/rtc.py',
 'https://github.com/huggingface/lerobot/blame/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/rtc.py',
 'https://huggingface.co/nvidia/GR00T-N1.7-3B/blob/2fc962b973bccdd5d8ce4f67cc63b264d6886495/README.md',
 'https://api.github.com/repos/dexmal/dexbotic/branches/main'
]
artifact_rows=[]
for p in sorted(ROOT.iterdir()):
    if p.is_file(): artifact_rows.append({'path':'evidence/ecosystem/'+p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
log={
 'round':'S2','researcher_scope':'ecosystem source and release chain','access_date':'2026-09-23','built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'read_before_research':['session AGENTS.md','06/00 task contract','S1 root summary','S1/ecosystem_frontier.md','embodied-scientist START_HERE.md, ROLE.md, state/status.json, knowledge/INDEX.md read only'],
 'new_questions':['Which final LeRobot merged diffs are in v0.6.1 versus a fixed main?','Does open #4398 imply stale observations remain in current engine code?','Does LoRA training delta survive the current OpenPI converter and serving loader, together with stats/config/precision?','What precise artifact license applies to the GR00T weight revision?','Which residual failures change the joint S3 design for an independently capable policy?'],
 'versions':versions,
 'actual_web_searches':[{'query':'site.github.com/huggingface/lerobot "4398" "observation"','result':'No useful matching result; unrelated search hits not treated as evidence; direct official PR used.'},{'query':'site:github.com/Physical-Intelligence/openpi "960" "LoRA"','relevant_result':'https://github.com/Physical-Intelligence/openpi/issues/958','result':'Issue found; direct PR and fixed source opened. Other unrelated hits discarded.'}],
 'web_opened':[{'url':u,'status':'opened_body_or_code','channel':'web.run','date':'2026-09-23'} for u in web_success],
 'web_failed':[{'url':u,'status':'Internal Error / restricted URL as returned by web tool','channel':'web.run','date':'2026-09-23'} for u in web_failure],
 'bounded_downloads':retrieval,
 'other_failed_attempts':[{'command':'git ls-remote https://github.com/dexmal/dexbotic.git refs/heads/main','result':'failed: existing proxy 127.0.0.1:7890 unavailable'},{'command':'git -c http.proxy= -c https.proxy= ls-remote https://github.com/dexmal/dexbotic.git refs/heads/main','result':'failed: direct github.com:443 connection timeout; command-only config, no global config edits'},{'operation':'initial UTF-8 read through Windows PowerShell default encoding','result':'mojibake; reran Get-Content -Encoding UTF8 successfully'},{'operation':'initial jobs1 JSON standard-library parse','result':'PowerShell UTF-8 BOM; downloader parser changed to utf-8-sig, then succeeded'},{'operation':'initial Python stdin path containing Chinese','result':'PowerShell pipe encoding corrupted path; reran ASCII script from explicit evidence workdir'}],
 'read_functions':{
   'lerobot':['context._align_to_checkpoint_order','context._assert_state_matches_action_order','context.build_rollout_context','SyncInferenceEngine.get_action/reset','RTCInferenceEngine.reset/notify_observation/pause/resume/_rtc_loop/get_action','_normalize_prev_actions_length','_estimate_rtc_delay/_clamp_trained_rtc_delay/_trained_rtc_chunk_can_merge','ActionQueue.get_with_task/merge/clear/_check_and_resolve_delays','DAggerStrategy._apply_transition/_run_continuous/_run_corrections_only','RolloutStrategy._process_observation_and_notify/reset_control_state','strategies.core.send_next_action'],
   'openpi':['checkpoints.save_state/_split_params/load_norm_stats','converter.main/convert_pi0_checkpoint/slice_initial_orbax_checkpoint/slice_paligemma_state_dict/slice_gemma_state_dict','PR960 _has_lora/merge_lora_into_base/_merge_attn_vec_lora/_merge_einsum_lora/_merge_mlp_linear_lora','lora.Einsum.__call__/_make_lora_eqns','lora.FeedForward._dot','gemma.Attention.__call__','policy_config.create_trained_policy','BaseModelConfig.load_pytorch','Policy.infer','Normalize/Unnormalize','PI0Pytorch.__init__','PaliGemmaWithExpertModel.to_bfloat16_for_selected_params']},
 'static_findings':[{'id':'E2-01','claim':'Current LeRobot engine clears observation and rejects stale reset-epoch chunks although #4398 is open. Present by merge4454 snapshot; not introduced by #4454 diff.','type':'fixed source static evidence'},{'id':'E2-02','claim':'RTC consumed count measures queue dequeue, while driver dispatch follows interpolation and action processing.','type':'fixed source static semantics'},{'id':'E2-03','claim':'Current OpenPI converter is byte-identical to the #958 reported-version converter; no adapter merge and ignored strict=False load result.','type':'file hash plus source evidence; no checkpoint execution'},{'id':'E2-04','claim':'PR960 checks remaining LoRA unexpected keys only; normalizer copying and serving precision still need separate audit.','type':'fixed PR source and serving loader'},{'id':'E2-05','claim':'Fixed GR00T weight LICENSE includes noncommercial research/evaluation limitation and conflicts with model-card/blog statements.','type':'official fixed artifact document'}],
 'unresolved':['First introducing commit for LeRobot reset-epoch equivalent fix not identified.','Actual stateful policy reset concurrency untested.','No model checkpoint converted or numerically compared.','GR00T conflicting licensing statements not authoritatively reconciled.','Dexbotic source SHA not fixed because source API/git attempts failed; no new S2 code claim.'],
 'not_executed':['No upstream source execution','No package installation','No training','No simulation or robot experiment','No weight/dataset download','No third-party full reproduction','No UPDATE/goal','No writes outside assigned report/log/evidence paths'],
 'artifact_index':artifact_rows,
 'notes':['Search engine request URL not exposed; not invented.','Web and urllib have different access results; downloaded-source failures do not negate successful web reading.','External pages may be cached; claims use fixed content SHA and API state at access time.','S2 is research, not a passed independent review round.']
}
(ROOT.parent.parent/'ecosystem_code_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'downloads':len(retrieval),'download_success':sum(x.get('status')==200 for x in retrieval),'web_opened':len(web_success),'artifact_count':len(artifact_rows),'manifest':'ecosystem_code_log.json'},ensure_ascii=False))
