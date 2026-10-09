"""Offline, read-only package integrity checks. Does not execute source samples."""
from pathlib import Path
from urllib.parse import unquote
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(name):
    if re.match(r"^[A-Za-z]:", name) or Path(name).is_absolute():
        raise ValueError("absolute package path: " + name)
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("path escapes package: " + name)
    return path


def read(name):
    return json.loads(safe_path(name).read_text(encoding="utf-8-sig"))


def check(unsealed=False):
    errors, excluded_upstream_markdown, historical_snapshot_markdown, link_count = [], [], [], 0
    actual = {p.relative_to(ROOT).as_posix(): p for p in ROOT.rglob("*") if p.is_file()}
    checked_manifest = 0
    if not unsealed:
        manifest = read("MANIFEST.json")
        listed = set()
        for row in manifest["files"]:
            name = row["path"]
            if name in listed:
                errors.append("duplicate manifest entry: " + name)
            listed.add(name)
            p = safe_path(name)
            if not p.is_file() or p.stat().st_size != row["bytes"] or sha(p) != row["sha256"]:
                errors.append("package file missing or changed: " + name)
            checked_manifest += 1
        for name in set(actual) - listed - {"MANIFEST.json"}:
            if not name.startswith(("work/", "implementation/")):
                errors.append("unexpected package file: " + name)
    for name in actual:
        if any(x in {".git", "browser_profile", "chrome_profile", "profile", "User Data", "__pycache__"} for x in Path(name).parts):
            errors.append("unexpected local metadata/cache: " + name)

    originals = read("audit/source_files.json")
    for row in originals:
        p = safe_path(row["package"])
        if not p.is_file() or sha(p) != row["sha256"]:
            errors.append("source bytes changed: " + row["package"])

    maps = read("audit/review_snapshot_map.json")
    first, agents = None, set()
    round_counts = []
    for item in maps["rounds"]:
        source_manifest = read(item["manifest"])
        hashes = {x["path"]: x["sha256"] for x in source_manifest["files"]}
        if first is None:
            first = hashes
        if hashes != first:
            errors.append("review scientific inputs differ: " + item["round"])
        covered = {}
        for row in item["retained"]:
            if row["path"] in covered:
                errors.append("repeated mapped source: " + row["path"])
            covered[row["path"]] = row["sha256"]
            p = safe_path(row["package"])
            if not p.is_file() or sha(p) != row["sha256"]:
                errors.append("review content missing or changed: " + row["package"])
        for row in item["omitted"]:
            if ".git" not in Path(row["path"]).parts or row["path"] in covered:
                errors.append("invalid review omission: " + row["path"])
            covered[row["path"]] = row["sha256"]
        if covered != hashes:
            errors.append("incomplete review mapping: " + item["round"])
        rd = safe_path(item["manifest"]).parent
        decision = json.loads((rd / "decision.json").read_text(encoding="utf-8-sig"))
        if decision["root_verdict"] != "PASS" or decision.get("required_issues") or len(decision["reviews"]) != 3:
            errors.append("review decision not passed: " + item["round"])
        if not (rd / decision["root_report"]).is_file():
            errors.append("missing root review: " + item["round"])
        for report in decision["reviews"]:
            if report["agent"] in agents or report["verdict"] != "PASS" or not (rd / report["file"]).is_file():
                errors.append("invalid reviewer report: " + item["round"] + "/" + report["file"])
            agents.add(report["agent"])
        round_counts.append({"round": item["round"], "original_manifest": len(hashes),
                             "retained_verified": len(item["retained"]), "excluded_git_internals": len(item["omitted"])})
    if [r["round"] for r in round_counts] != ["R01", "R02", "R03", "R04", "R05"] or len(agents) != 15:
        errors.append("expected five rounds and fifteen distinct reviewers")

    latest = next((ROOT / "materials").glob("06_*"))
    history = json.loads((latest / "qa/historical_source_hashes.json").read_text(encoding="utf-8"))
    for name, expected in history.items():
        p = safe_path("materials/" + name)
        if not p.is_file() or sha(p) != expected:
            errors.append("historical identity mismatch: " + name)
    rendering = json.loads((latest / "qa/render_manifest.json").read_text(encoding="utf-8"))
    for fig in rendering["figures"]:
        for key in ("source", "svg"):
            if sha(latest / fig[key]) != fig[key + "_sha256"]:
                errors.append("figure identity mismatch: " + fig[key])
    visual = json.loads((latest / "qa/visual_review.json").read_text(encoding="utf-8"))
    for name, expected in visual["files"].items():
        if sha(latest / name) != expected:
            errors.append("visual review asset differs: " + name)
    preview = json.loads((latest / "qa/markdown_layout.json").read_text(encoding="utf-8"))
    if preview["source_sha256"] != sha(latest / "03_技术专家汇报.md"):
        errors.append("brief differs from original layout-reviewed file")

    # Upstream excerpts are not complete repositories. Their original internal links
    # remain untouched and are explicitly outside the authored-document link check.
    for name, p in actual.items():
        if p.suffix.lower() != ".md":
            continue
        parts = p.relative_to(ROOT).parts
        if "input" in parts and any(x.startswith("reviews") for x in parts):
            historical_snapshot_markdown.append(name)
            continue
        upstream = name.startswith("materials/") and (
            "evidence" in parts or any("code_snapshot" in x or "_source_" in x or "_snapshot_" in x or x.endswith("_evidence") for x in parts[:-1]))
        if upstream:
            excluded_upstream_markdown.append(name)
            continue
        body = p.read_text(encoding="utf-8-sig")
        if "\ufffd" in body:
            errors.append("encoding replacement character: " + name)
        body = re.sub(r"```.*?```", "", body, flags=re.S)
        for target in re.findall(r"!?\[[^\]\n]*\]\(([^\n)]+)\)", body):
            target = target.strip().strip("<>")
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0])
            link_count += 1
            if re.match(r"^[A-Za-z]:", target) or target.startswith(("/", "\\")):
                errors.append("nonportable document link: " + name + " -> " + target)
                continue
            dest = (p.parent / target).resolve()
            if not dest.is_relative_to(ROOT) or not dest.exists():
                errors.append("broken document link: " + name + " -> " + target)
    path_map = read("audit/legacy_path_map.json")
    for row in path_map["mapped_file_fields"]:
        if not safe_path(row["package_path"]).is_file():
            errors.append("legacy mapped file missing: " + row["package_path"])
    return {"ok": not errors, "sealed_manifest_checked": not unsealed,
            "manifest_files_checked": checked_manifest, "source_files_checked": len(originals),
            "authored_local_links_checked": link_count,
            "upstream_excerpt_markdown_excluded_from_link_check": excluded_upstream_markdown,
            "historical_snapshot_markdown_identity_only": historical_snapshot_markdown,
            "original_review_rounds": round_counts, "distinct_original_reviewers": len(agents),
            "scope": "delivery identity and links; not scientific correctness or robot validation",
            "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unsealed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--details", action="store_true", help="List archived link-check exclusions in full")
    args = parser.parse_args()
    try:
        result = check(args.unsealed)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        result = {"ok": False, "errors": [str(exc)]}
    if not args.details:
        for key in ("upstream_excerpt_markdown_excluded_from_link_check", "historical_snapshot_markdown_identity_only"):
            if key in result:
                result[key + "_count"] = len(result.pop(key))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
