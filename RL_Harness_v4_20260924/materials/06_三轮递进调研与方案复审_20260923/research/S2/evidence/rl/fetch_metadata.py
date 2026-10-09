import json,urllib.request,pathlib,hashlib,concurrent.futures
root=pathlib.Path(__file__).parent
repos=['FluxVLA/FluxVLA','FluxVLA/FluxDAgger','JianghaiSCU/FutureRTC']
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'research-static-audit'})
 with urllib.request.urlopen(req,timeout=40) as r:return r.read()
def run(repo):
 d=root/repo.replace('/','__');d.mkdir(exist_ok=True)
 try:
  meta=json.loads(get('https://api.github.com/repos/'+repo));bs=json.loads(get('https://api.github.com/repos/'+repo+'/branches?per_page=100'))
  (d/'meta.json').write_text(json.dumps(meta,indent=2),encoding='utf8');(d/'branches.json').write_text(json.dumps(bs,indent=2),encoding='utf8')
  output=[]
  for b in bs:
   if repo!='JianghaiSCU/FutureRTC' and b['name']!=meta['default_branch']:continue
   sha=b['commit']['sha']; t=json.loads(get('https://api.github.com/repos/'+repo+'/git/trees/'+sha+'?recursive=1'))
   p=d/(b['name'].replace('/','__')+'__tree.json');p.write_text(json.dumps(t,indent=2),encoding='utf8')
   output.append({'branch':b['name'],'sha':sha,'files':len(t.get('tree',[])),'truncated':t.get('truncated')})
  print(json.dumps({'repo':repo,'branches':output},ensure_ascii=False))
 except Exception as e:print(repo,repr(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:list(ex.map(run,repos))
