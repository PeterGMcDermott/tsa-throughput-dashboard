"""Build compact JSON payload for the dashboard artifact."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from fast_parse import parse_pdf

BASE = Path(__file__).parent
PROC = BASE / "processed"


def main():
    monthly = pd.read_csv(PROC / "monthly.csv")
    months = sorted(monthly["ym"].unique())
    print(f"{len(months)} months: {months[0]}..{months[-1]}")

    # airport names from the most recent PDF
    latest = sorted((BASE / "raw").glob("tsa-throughput-week-ending-*.pdf"))[-1]
    print("names from:", latest.name)
    _, names, _, _ = parse_pdf(latest, "2026-09-27")

    piv = monthly.pivot(index="airport_code", columns="ym", values="throughput_count")
    # PBI was renamed DJT in Mar 2026; monthly data uses PBI (merged).
    # Carry the DJT name over so PBI is labeled.
    if "DJT" in names and "PBI" not in names:
        names["PBI"] = names["DJT"]
    airports = {}
    for code in piv.index:
        nm, city, st = names.get(code, ("", "", ""))
        vals = [None if pd.isna(v) else int(v) for v in piv.loc[code, months].tolist()]
        airports[code] = {"n": nm, "c": city, "s": st, "m": vals}

    national = monthly.groupby("ym")["throughput_count"].sum()
    payload = {
        "months": months,
        "airports": airports,
        "national": [int(national[m]) for m in months],
        "meta": {
            "coverage_start": months[0], "coverage_end": months[-1],
            "n_airports": len(airports),
            "source": "TSA FOIA Reading Room weekly passenger throughput PDFs",
        },
    }
    out = PROC / "dashboard_data.json"
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB), {len(airports)} airports")


if __name__ == "__main__":
    main()
