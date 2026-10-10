"""Build the partial-month payload for the newest incomplete calendar month.

Mirrors the payload format previously added by hand for September 2026:
{
  "label": "2026-10*",
  "coverage": "2026-10-01 to 2026-10-03 (3 of 31 days)",
  "national_2026": <throughput over the partial dates>,
  "national_2025": <same calendar dates one year earlier>,
  "airports": {code: [pax_2026, pax_2025]}
}
DJT is merged into PBI (Palm Beach rename, Mar 2026) for continuity.
Injects the payload as dashboard_data.json["partial_month"], replacing any
legacy partial_<month>_<year> key.
"""
import calendar
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).parent
PROC = BASE / "processed"


def load_daily():
    recs = defaultdict(int)  # (date_str, code) -> count
    for f in PROC.glob("daily_*.csv"):
        with open(f) as fh:
            for row in csv.DictReader(fh):
                code = row["airport_code"]
                if code == "DJT":
                    code = "PBI"
                recs[(row["throughput_date"], code)] += int(row["throughput_count"])
    return recs


def main():
    recs = load_daily()
    dates = sorted({d for d, _ in recs})
    last = date.fromisoformat(dates[-1])
    ym = last.strftime("%Y-%m")
    dim = calendar.monthrange(last.year, last.month)[1]
    mdates = sorted(d for d in dates if d.startswith(ym))
    if len(mdates) == dim:
        print(f"{ym} is complete ({dim} days); no partial payload needed")
        return
    ndays = len(mdates)
    prev = date(last.year - 1, last.month, 1)
    pdates = [str(prev + timedelta(days=i)) for i in range(ndays)]

    airports = defaultdict(lambda: [0, 0])
    for d in mdates:
        for code in {c for (dd, c) in recs if dd == d}:
            airports[code][0] += recs[(d, code)]
    for d in pdates:
        for code in {c for (dd, c) in recs if dd == d}:
            airports[code][1] += recs[(d, code)]

    payload = {
        "label": f"{ym}*",
        "coverage": f"{mdates[0]} to {mdates[-1]} ({ndays} of {dim} days)",
        "national_2026": sum(v[0] for v in airports.values()),
        "national_2025": sum(v[1] for v in airports.values()),
        "airports": {code: vals for code, vals in sorted(airports.items())},
    }

    out = PROC / "dashboard_data.json"
    d = json.loads(out.read_text())
    for k in [k for k in d if k.startswith("partial_")]:
        del d[k]
    d["partial_month"] = payload
    out.write_text(json.dumps(d, separators=(",", ":")))
    print(f"partial_month: {payload['label']} {payload['coverage']}, "
          f"national {payload['national_2026']:,} vs prior-year {payload['national_2025']:,}, "
          f"{len(payload['airports'])} airports")


if __name__ == "__main__":
    main()
