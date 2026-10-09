import pathlib,subprocess,json,concurrent.futures,hashlib
root=pathlib.Path(__file__).parent
src=(root/'fetch_text.py').read_text(encoding='utf-8-sig');start=src.index('specs=');end=src.index('\njobs=')
ns={};exec(src[start:end],ns)
def run(item):
 d,(repo,match)=item;folder=root/d
 files=[p for p in (folder/'tree.txt').read_text(encoding='utf-8-sig').splitlines() if match(p)]
 r=subprocess.run(['git','-c','http.proxy=','-c','https.proxy=','-C',str(folder),'checkout','HEAD','--']+files,capture_output=True,text=True,encoding='utf8')
 print(d,len(files),r.returncode,r.stderr[-300:])
 sha=subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()
 return [{'repo':repo,'sha':sha,'path':p,'url':f'https://github.com/{repo}/blob/{sha}/{p}','local':d+'/'+p,'sha256':hashlib.sha256((folder/p).read_bytes()).hexdigest(),'bytes':(folder/p).stat().st_size} for p in files if (folder/p).exists()]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:rows=[r for a in ex.map(run,ns['specs'].items()) for r in a]
(root/'git_text_manifest.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf8')
