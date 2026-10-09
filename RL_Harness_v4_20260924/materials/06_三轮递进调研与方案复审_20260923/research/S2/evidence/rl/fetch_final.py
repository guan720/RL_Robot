import pathlib,json,urllib.request,concurrent.futures,hashlib
r=pathlib.Path(__file__).parent
jobs=[('fluxvla_git','FluxVLA/FluxVLA','3fe5d10cf56ae33787baf58efaf12bfbce2393d0','fluxvla/engines/losses/rabc.py'),('futurertc_libero_git','JianghaiSCU/FutureRTC','57310be57b13cb2284d25c9ab7f636e9cf77fa90','launch/train_predictor_phase2_pl_pi05.sh'),('futurertc_libero_git','JianghaiSCU/FutureRTC','57310be57b13cb2284d25c9ab7f636e9cf77fa90','launch/train_predictor_phase2_pl_smolvla.sh')]
def f(j):
 d,repo,s,p=j;u=f'https://raw.githubusercontent.com/{repo}/{s}/{p}';rec=dict(url=u,path=p,sha=s,repo=repo)
 try:
  b=urllib.request.urlopen(u,timeout=20).read();o=r/d/'text'/p;o.parent.mkdir(parents=True,exist_ok=True);o.write_bytes(b);rec.update(status='ok',sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),local=str(o.relative_to(r)))
 except Exception as e:rec.update(status='failed',error=str(e))
 return rec
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:res=list(ex.map(f,jobs))
(r/'download_final.json').write_text(json.dumps(res,indent=2),encoding='utf8');print(res)
