import concurrent.futures, json, pathlib, urllib.request, datetime

ROOT=pathlib.Path(__file__).resolve().parent
REPOS=['pd-perry/expo-ft','sylvestf/WCM','manutdmoon/ZPRL','LiangSu8899/FlashRT','LAMDA-RL/VLA-MBPO','VLARLKit/VLARLKit']
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ResearchAudit/1.0','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=35) as r:return json.load(r)
def one(repo):
    try:
        meta=get('https://api.github.com/repos/'+repo)
        commit=get('https://api.github.com/repos/'+repo+'/commits/'+meta['default_branch'])
        sha=commit['sha'];tree=get('https://api.github.com/repos/'+repo+'/git/trees/'+sha+'?recursive=1')
        dest=ROOT/repo.replace('/','__');dest.mkdir(parents=True,exist_ok=True)
        (dest/'metadata.json').write_text(json.dumps({'fetched_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repository':meta,'commit':commit,'tree':tree},ensure_ascii=False,indent=2),encoding='utf-8')
        return {'repo':repo,'sha':sha,'date':commit['commit']['committer']['date'],'stars':meta['stargazers_count'],'forks':meta['forks_count'],'license':meta.get('license'),'paths':[v['path'] for v in tree['tree'] if v['type']=='blob']}
    except Exception as e:return {'repo':repo,'error':repr(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for r in pool.map(one,REPOS):print(json.dumps(r,ensure_ascii=False))
