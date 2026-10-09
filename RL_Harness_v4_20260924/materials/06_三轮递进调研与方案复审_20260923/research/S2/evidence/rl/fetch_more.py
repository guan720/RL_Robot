import pathlib,urllib.request,concurrent.futures,json,hashlib
root=pathlib.Path(__file__).parent
jobs=[('fluxvla_git','FluxVLA/FluxVLA','3fe5d10cf56ae33787baf58efaf12bfbce2393d0',p) for p in ['fluxvla/models/vlas/pi0_flowmatching.py','fluxvla/engines/losses.py','fluxvla/transforms/attach_rabc_weight.py','fluxvla/engines/runners/base_inference_runner.py','docs/arm.md','tools/arm_awbc/progress_reconstruction.py','configs/arm/arm_clip_aloha_example.py']]
def get(j):
 d,r,s,p=j;u=f'https://raw.githubusercontent.com/{r}/{s}/{p}';rec={'url':u,'path':p,'repo':r,'sha':s}
 try:
  b=urllib.request.urlopen(u,timeout=20).read();o=root/d/'text'/p;o.parent.mkdir(parents=True,exist_ok=True);o.write_bytes(b);rec.update(status='ok',sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),local=str(o.relative_to(root)))
 except Exception as e:rec.update(status='failed',error=str(e))
 return rec
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:out=list(ex.map(get,jobs))
(root/'download_more.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(out)
