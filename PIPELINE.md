# TSA Throughput Analysis Pipeline

## Data source
TSA FOIA Reading Room weekly "Total Pax + KCM Pax" PDFs (MicroStrategy exports),
downloaded from the TSA FOIA reading room. 157 weekly PDFs covering
week ending 2023-10-07 through 2026-10-03 (throughput dates 2026-09-27..2026-10-03
added 2026-10-05; total throughput dates 2023-10-01..2026-10-03).

## Pipeline
1. `dl.py` / `download_window.py` — parallel download of the 156 PDFs into `raw/`
   (+ `manifest.json` with week_start/week_end per file).
2. `fast_parse.py` — PyMuPDF-based parser (~15 s/PDF, 2 workers):
   - Airport sections are delimited by FULL-width horizontal vector rules
     (x0≈107); checkpoint rows inside a section by partial rules (x0≈341).
   - The airport code/name merged cell is vertically CENTERED, so text-order
     parsing misattributes rows; the vector rules give exact sections.
   - Hour blocks detected by alphabetical airport-code resets (168 blocks/week).
   - (date, hour) from dense hour text markers assigned by y-range; dates walk
     23→00 wraps from manifest week_start (DST-safe).
   - Handles thousands separators ("1,109") and wrapped airport codes
     ('MD'+'W' for MDW in PDFs from week ending 2026-03-07, when TSA narrowed
     the code column).
   - Validated: 88/88 exact (date, airport) matches vs official `tsa-throughput`
     parser on 5 pages (2026), 42/42 on 3 pages (2023).
3. `run_all.py` — batch parse all PDFs → `processed/daily_<week_end>.csv`
   (throughput_date, airport_code, throughput_count).
4. `aggregate.py` — combine, keep complete calendar months only, monthly
   per-airport totals → `processed/monthly.csv`; TTM growth
   (2025-08..2026-07 vs 2024-08..2025-07) → `processed/growth_ttm.csv`;
   national monthly → `processed/national_monthly.csv`.
   - PBI→DJT continuity: Palm Beach International was renamed
     "President Donald J Trump International" (code DJT) in Mar 2026;
     merged to PBI for continuity.
5. `build_dashboard_data.py` — compact JSON for the dashboard artifact
   → `processed/dashboard_data.json`.

## Key data notes
- 36 complete months: 2023-10..2026-09. October 2026 partial (3 days, through 2026-10-03) excluded from monthly comparisons; shown as hatched partial bar in the dashboard.
- ~434 airports; TTM comparison requires ≥10 months of data in each window.
- YoY same-month/TTM comparisons control for seasonality.
- National TTM (2025-10..2026-09 vs 2024-10..2025-09): 876M → 879M (+0.3%). Busiest month: 2025-07 (82.6M). September 2026: 69.8M, flat YoY.
- Local headlines: processed/headlines.json holds a news scan (3-5 recent headlines each) for the top TTM movers plus the top 30 airports by volume, refreshed with each dashboard data rebuild and merged into dashboard_data.json under "headlines". Powers the dashboard's on-demand headline context for movers and the airport explorer.

## Environment quirks (see also ~/AGENTS.md material)
- Sandbox `no_proxy`/`NO_PROXY` contain bracketed IPv6 (`[::1]`) which crashes
  httpx; sanitize to `localhost,127.0.0.1` for Python HTTP work.
- `tsa-throughput` (official parser) OOMs on full PDFs here (pdfplumber, 4GB+);
  the PyMuPDF parser above is the fast path.
