"""Batch-parse all 148 TSA PDFs with the validated PyMuPDF parser (2 workers)."""
import csv
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fast_parse import parse_pdf

BASE = Path(__file__).parent
RAW = BASE / "raw"
PROC = BASE / "processed"
PROC.mkdir(exist_ok=True)
LOG = BASE / "logs" / "parse_all.log"


def parse_one(item):
    pdf_name, week_start, week_end = item
    t0 = time.time()
    try:
        daily, names, warnings, recs = parse_pdf(RAW / pdf_name, week_start)
        # write per-week daily CSV
        out = PROC / f"daily_{week_end}.csv"
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["throughput_date", "airport_code", "throughput_count"])
            w.writerows(sorted(daily))
        total = sum(c for _, _, c in daily)
        return (pdf_name, "OK", len(daily), len(names), total,
                round(time.time() - t0, 1), "")
    except Exception as e:
        return (pdf_name, "FAIL", 0, 0, 0, round(time.time() - t0, 1),
                traceback.format_exc(limit=3))


def main():
    manifest = json.loads((RAW / "manifest.json").read_text())["reports"]
    items = [(m["canonical_filename"], m["week_start"], m["week_end"]) for m in manifest]
    print(f"{len(items)} PDFs to parse", flush=True)
    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=2) as ex:
        for i, r in enumerate(ex.map(parse_one, items)):
            results.append(r)
            name, status, nrows, nair, total, dt, err = r
            msg = f"[{i+1}/{len(items)}] {name}: {status} rows={nrows} airports={nair} total={total} {dt}s"
            print(msg, flush=True)
            with open(LOG, "a") as f:
                f.write(msg + "\n")
                if err:
                    f.write(err + "\n")
    ok = sum(1 for r in results if r[1] == "OK")
    print(f"Done: {ok}/{len(results)} OK in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
