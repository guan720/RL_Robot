import pathlib,json,urllib.request,concurrent.futures,hashlib,subprocess
root=pathlib.Path(__file__).parent
specs={
'fluxdagger_git':('FluxVLA/FluxDAgger',lambda p:p.endswith(('.py','.msg','.yaml','.launch','.xml','.txt')) or p in ['LICENSE','README.md','docs/README.md']),
'fluxvla_git':('FluxVLA/FluxVLA',lambda p:p in ['LICENSE','README.md','docs/arm.md','tools/arm_awbc/README.md','requirements-base.txt','scripts/train.py','scripts/ros_inference_server.py','scripts/compute_arm_awbc_progress.py','scripts/infer_arm_progress.py','fluxvla/engines/runners/base_train_runner.py','fluxvla/engines/runners/ddp_train_runner.py','fluxvla/engines/runners/serving/serve.py','fluxvla/engines/runners/serving/ros_server.py','fluxvla/weighters/arm_rabc.py','fluxvla/models/vlas/arm_reward_model.py','fluxvla/datasets/arm_dataset.py','tools/arm_awbc/progress_reconstruction.py','configs/arm/arm_clip_aloha_example.py'] or ('pi05' in p and p.endswith('.py') and 'models/vlas' in p)),
'futurertc_real_git':('JianghaiSCU/FutureRTC',lambda p:p in ['LICENSE','README.md','infer/cobot-magic-real/README.md','infer/cobot-magic-real/deploy.sh','infer/cobot-magic-real/deploy_policy_local_ours_batch_test.py','infer/cobot-magic-real/control_arm_server.py','infer/cobot-magic-real/reset.py','infer/openpi/deploy_policy_server_ours_local.py'] or (p.startswith(('train/ours_pi05/','infer/ours_pi05/')) and p.endswith('.py') and '/tests/' not in p)),
'futurertc_libero_git':('JianghaiSCU/FutureRTC',lambda p:p in ['LICENSE','README.md','predictor/dataset.py','predictor/train.py','predictor/losses.py','predictor/collect_latents.py','predictor/policy_loss/pi05.py','corrector/train.py'] or ('eval' in p and p.endswith('.py'))),
'futurertc_kinetix_git':('JianghaiSCU/FutureRTC',lambda p:p in ['LICENSE','README.md','scripts/train_predictor.py','src/motion_prior_handoff/predictor.py','src/motion_prior_handoff/rtc_env.py'])}
jobs=[]
for d,(repo,match) in specs.items():
 sha=subprocess.check_output(['git','-C',str(root/d),'rev-parse','HEAD'],text=True).strip()
 for p in (root/d/'tree.txt').read_text(encoding='utf-8-sig').splitlines():
  if match(p):jobs.append((d,repo,sha,p))
def fetch(job):
 d,repo,sha,p=job;out=root/d/'text'/p;url=f'https://raw.githubusercontent.com/{repo}/{sha}/{p}'
 rec={'repo':repo,'sha':sha,'path':p,'url':url,'local':str(out.relative_to(root))}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'static-research-audit'})
  with urllib.request.urlopen(req,timeout=35) as r:b=r.read(2000000)
  out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b);rec.update(status='ok',bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:rec.update(status='failed',error=str(e))
 return rec
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:res=list(ex.map(fetch,jobs))
(root/'download_manifest.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'total':len(res),'ok':sum(r['status']=='ok' for r in res),'failures':[r for r in res if r['status']!='ok']},ensure_ascii=False))
