"""Read-only retrieval of selected primary evidence; never executes upstream code."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parent / "evidence" / "rl_joint"
SOURCES = {
    "rapolicy_paper.html": "https://arxiv.org/html/2609.22888v1",
    "rt_expo_paper.html": "https://arxiv.org/html/2609.18207v1",
    "synthdemo_paper.html": "https://arxiv.org/html/2609.21650v1",
    "torl_paper.html": "https://arxiv.org/html/2606.09337v1",
    "force_paper.html": "https://arxiv.org/html/2609.22840v1",
    "future_paper.html": "https://arxiv.org/html/2607.24008v1",
    "rt_batch_processor.py": "https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/batch_processor.py",
    "rt_learner.py": "https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py",
    "ra_actor_loss.py": "https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_actor_loss.py",
    "ra_sac.py": "https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py",
    "ra_offline.py": "https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py",
}

def fetch(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchEvidence/1.0"})
        with urllib.request.urlopen(req, timeout=40) as response:
            data = response.read()
        (ROOT / name).write_bytes(data)
        return {"file": name, "url": url, "ok": True, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    except Exception as error:
        return {"file": name, "url": url, "ok": False, "error": str(error)}

if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        records = list(executor.map(fetch, SOURCES.items()))
    (ROOT / "manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(records, indent=2, ensure_ascii=False))
