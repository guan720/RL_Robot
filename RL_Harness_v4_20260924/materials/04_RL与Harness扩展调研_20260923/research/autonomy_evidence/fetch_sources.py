import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import requests

ROOT = Path(__file__).resolve().parent
URLS = {
    'autoserl_repo': 'https://github.com/autoserl/AutoSERL',
    'hilrl_repo': 'https://github.com/nuomizai/HIL-RL',
    'uniintervene_site': 'https://denghaoyuan123.github.io/UniIntervene-project/',
    'autoserl_paper': 'https://arxiv.org/html/2607.01651v1',
    'silri_paper': 'https://arxiv.org/html/2512.24288v1',
    'gains_paper': 'https://arxiv.org/html/2608.15707v1',
    'uniintervene_paper': 'https://arxiv.org/html/2606.12372v1',
    'cronos_site': 'https://embodiedai-ntu.github.io/cronos/index.html',
    'playworld_site': 'https://robot-playworld.github.io/',
    'lwd_site': 'https://finch.agibot.com/research/lwd',
}

def fetch(item):
    name, url = item
    s = requests.Session()
    s.trust_env = False
    try:
        r = s.get(url, timeout=40)
        record = dict(name=name, url=url, status=r.status_code)
        if r.status_code == 200:
            (ROOT / (name + '.html')).write_bytes(r.content)
            record['sha256'] = hashlib.sha256(r.content).hexdigest()
            record['commit_candidates'] = sorted(set(re.findall(r'currentOid[\"\\:]+([0-9a-f]{40})', r.text)))
        else:
            record['error'] = r.text[:160]
        return record
    except Exception as e:
        return dict(name=name, url=url, error=str(e))

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(fetch, URLS.items()))
    (ROOT / 'source_manifest.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))
