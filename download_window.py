"""Download in-window TSA throughput PDFs from the installed manifest."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tsa_throughput.source_manifest import load_installed_source_manifest, list_source_reports
from tsa_throughput.download import download_missing_reports
from tsa_throughput.storage import LocalStorage

OUT = Path.home() / "workspace" / "tsa-analysis" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

LO, HI = "2023-10-01", "2026-09-30"

manifest = load_installed_source_manifest()
reports = [r for r in list_source_reports(manifest)
           if LO <= str(r.week_end) <= HI]
reports.sort(key=lambda r: str(r.week_end))
print(f"in-window reports: {len(reports)}", flush=True)
print(f"range: {reports[0].week_start} -> {reports[-1].week_end}", flush=True)

storage = LocalStorage(OUT)
results = download_missing_reports(
    reports, storage=storage, manifest_path=OUT / "manifest.json",
)
from collections import Counter
print(Counter(r.status for r in results), flush=True)
# save filtered list for later stages
(OUT / "in_window.json").write_text(json.dumps(
    [{"canonical_id": r.canonical_id, "week_start": str(r.week_start),
      "week_end": str(r.week_end), "canonical_filename": r.canonical_filename}
     for r in reports], indent=1))
print("wrote in_window.json", flush=True)
