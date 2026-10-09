import json, pathlib, urllib.request, concurrent.futures, datetime
ROOT=pathlib.Path(__file__).parent
REPOS=['RLinf/RPent','NVlabs/VoLoAgent','OpenRAL/openral','showlab/Show-Harness','RoboClaw-Robotics/RoboClaw','InternRobotics/REAL','dimensionalOS/dimos','HorizonRobotics/HoloAgent','menloresearch/robotic-autonomy','NVlabs/ENPIRE','air-embodied-brain/Zetta-Embodiment','nssmd/RoboRSI']
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'research-audit','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=40) as r: return r.read()
def process(repo):
    d=ROOT/repo.replace('/','__'); d.mkdir(parents=True,exist_ok=True)
    out={'repo':repo,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        meta=json.loads(get('https://api.github.com/repos/'+repo)); out['metadata']={k:meta.get(k) for k in ['full_name','description','default_branch','created_at','pushed_at','stargazers_count','forks_count','open_issues_count','license','archived','size']}
        commit=json.loads(get('https://api.github.com/repos/'+repo+'/commits/'+meta['default_branch'])); sha=commit['sha']; out['sha']=sha; out['commit']=commit['commit']
        tree=json.loads(get('https://api.github.com/repos/'+repo+'/git/trees/'+sha+'?recursive=1')); (d/'tree.json').write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8')
        paths=[t['path'] for t in tree.get('tree',[]) if t['type']=='blob']; (d/'paths.txt').write_text('\n'.join(paths),encoding='utf-8')
        for p in ['README.md','LICENSE','pyproject.toml']:
            if p in paths:
                try:(d/p).write_bytes(get('https://raw.githubusercontent.com/'+repo+'/'+sha+'/'+p))
                except Exception as e:out.setdefault('file_errors',{})[p]=str(e)
    except Exception as e:out['error']=str(e)
    (d/'meta.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); return out
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex: results=list(ex.map(process,REPOS))
    (ROOT/'repo_snapshot.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'repo':r['repo'],'sha':r.get('sha'),'error':r.get('error'),'meta':r.get('metadata')} for r in results],ensure_ascii=False,indent=2))
