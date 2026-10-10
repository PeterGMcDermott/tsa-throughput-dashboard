"""Parallel TSA PDF downloader using curl (works around httpx no_proxy parsing bug)."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tsa_throughput.source_manifest import load_installed_source_manifest, list_source_reports

BASE = Path.home() / "workspace" / "tsa-analysis"
OUT = BASE / "raw"
OUT.mkdir(parents=True, exist_ok=True)

LO, HI = "2023-10-01", "2026-09-30"
WORKERS = 6

# sanitize proxy env for children (keep proxy, drop bracketed IPv6 no_proxy entries)
env = dict(os.environ)
env["no_proxy"] = "localhost,127.0.0.1"
env["NO_PROXY"] = "localhost,127.0.0.1"

manifest = load_installed_source_manifest()
reports = [r for r in list_source_reports(manifest) if LO <= str(r.week_end) <= HI]
reports.sort(key=lambda r: str(r.week_end))
print(f"in-window reports: {len(reports)}", flush=True)


def fetch(url, dest):
    p = subprocess.run(
        ["curl", "-sL", "--max-time", "300", "--retry", "2", "--retry-delay", "3",
         "-o", str(dest), "-w", "%{http_code} %{size_download}", url],
        capture_output=True, text=True, env=env, timeout=330)
    return p.stdout.strip(), p.returncode


def is_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def one(r):
    dest = OUT / r.canonical_filename
    if dest.exists() and is_pdf(dest) and dest.stat().st_size > 100_000:
        return (r.canonical_id, "exists", dest.stat().st_size)
    urls = [r.source_url] + list(r.alternate_urls or [])
    for url in urls:
        if not url:
            continue
        try:
            info, rc = fetch(url, dest)
        except Exception as e:  # noqa: BLE001
            info = f"exc {e}"
            rc = 1
        if rc == 0 and dest.exists() and is_pdf(dest) and dest.stat().st_size > 100_000:
            return (r.canonical_id, "downloaded", dest.stat().st_size)
        if dest.exists():
            dest.unlink(missing_ok=True)
    return (r.canonical_id, f"FAILED last={info}", 0)


results = []
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for res in ex.map(one, reports):
        results.append(res)
        if len(results) % 20 == 0:
            print(f"  ...{len(results)}/{len(reports)} done", flush=True)

from collections import Counter
print(Counter(s for _, s, _ in results), flush=True)
failed = [cid for cid, s, _ in results if s.startswith("FAILED")]
print("failed:", len(failed), flush=True)
for cid in failed[:20]:
    print("  FAIL", cid, flush=True)

# tool-compatible runtime manifest for parse-all (week dates per file)
rt = {"reports": []}
for r in reports:
    dest = OUT / r.canonical_filename
    if dest.exists() and is_pdf(dest):
        rt["reports"].append({
            "canonical_id": r.canonical_id,
            "canonical_filename": r.canonical_filename,
            "week_start": str(r.week_start), "week_end": str(r.week_end),
            "source_url": r.source_url,
            "bytes": dest.stat().st_size,
        })
(OUT / "manifest.json").write_text(json.dumps(rt, indent=1))
print(f"manifest.json: {len(rt['reports'])} pdfs", flush=True)
total_mb = sum(f.stat().st_size for f in OUT.glob("*.pdf")) / 1e6
print(f"total size: {total_mb:.0f} MB", flush=True)
