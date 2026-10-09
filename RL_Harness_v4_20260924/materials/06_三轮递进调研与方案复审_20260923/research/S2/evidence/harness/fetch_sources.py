"""Standard-library text-only research fetcher; does not execute fetched code."""
import concurrent.futures, datetime, hashlib, json, pathlib, sys, urllib.request
BASE = pathlib.Path(__file__).resolve().parent
LOG = BASE / 'fetch_manifest.jsonl'
def fetch(item):
    url, rel = item
    row = dict(url=url, local=rel, accessed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'S2-static-research','Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(12_000_001)
            if len(data)>12_000_000: raise ValueError('text download size ceiling exceeded')
            row.update(status=r.status, final_url=r.url)
        data.decode('utf-8')
        out=BASE / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as e:
        row.update(error=str(e))
    return row
def run(items):
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows=list(pool.map(fetch,items))
    with LOG.open('a',encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    for r in rows: print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':
    run(json.loads(sys.stdin.read()))
