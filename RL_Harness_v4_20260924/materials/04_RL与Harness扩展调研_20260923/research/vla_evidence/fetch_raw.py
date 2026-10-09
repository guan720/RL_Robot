import concurrent.futures, datetime, hashlib, json, pathlib, urllib.request, re
ROOT=pathlib.Path(__file__).resolve().parent
TASKS={
'pd-perry/expo-ft':['README.md','LICENSE','expo_ft/agents/alg/realtime_expo_ft.py','expo_ft/agents/alg/expo_ft.py','expo_ft/utils/loop_utils.py','expo_ft/data/batch_processor.py','expo_ft/data/replay_buffer.py','train_pi_robo.py','train_pi_robo_async.py','configs/model/realtime_expo_ft_pi_config.py','configs/task/dynamic_pick.py','scripts/dynamic_pick/train_policy.sh'],
'sylvestf/WCM':['README.md','LICENSE'],
'LiangSu8899/FlashRT':['training/README.md','docs/rl_inference.md'],
}
def one(task):
    repo,path=task;url=f'https://raw.githubusercontent.com/{repo}/main/{path}'
    dest=ROOT/repo.replace('/','__')/path;dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        with urllib.request.urlopen(url,timeout=50) as r:data=r.read()
        dest.write_bytes(data)
        result={'repo':repo,'path':path,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'fetched_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    except Exception as e:result={'repo':repo,'path':path,'url':url,'error':repr(e)}
    return result
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as p:
    results=list(p.map(one,[(r,f) for r,fs in TASKS.items() for f in fs]))
(ROOT/'raw_manifest.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf8')
for r in results:print(json.dumps(r,ensure_ascii=False))
