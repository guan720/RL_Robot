"""Research-only bounded text retrieval. Does not import or run downloaded code."""
import concurrent.futures, datetime, hashlib, json, pathlib, sys, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent
def get_one(item):
    name, url = item
    record = {'name': name, 'url': url, 'accessed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'StaticSourceResearch/1.0', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=35) as response:
            data = response.read(8_000_001)
            if len(data) > 8_000_000:
                raise ValueError('bounded text size exceeded')
            data.decode('utf-8')
            record.update(status=response.status, final_url=response.url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        (ROOT / name).write_bytes(data)
    except Exception as error:
        record['error'] = repr(error)
    return record
def main():
    jobs = json.loads((ROOT / sys.argv[1]).read_text(encoding='utf-8-sig'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        records = list(pool.map(get_one, jobs))
    log = ROOT / 'retrieval_log.json'
    prior = json.loads(log.read_text(encoding='utf-8')) if log.exists() else []
    log.write_text(json.dumps(prior + records, ensure_ascii=False, indent=2), encoding='utf-8')
    for record in records:
        print(json.dumps(record, ensure_ascii=False))
if __name__ == '__main__':
    main()
