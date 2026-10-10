# TSA Airport Throughput Dashboard

Three years of TSA checkpoint screening data, broken down per airport. I got curious about which airports are actually growing and which are shrinking, and the TSA publishes weekly passenger counts, so I built this.

Live dashboard: https://muse.ai/s/tsa-airport-throughput-dashboard-oxq6ixd35ivky

## What is here

`index.html` is the dashboard itself, a single self-contained file. Open it in a browser and it works.

The `*.py` files are the pipeline that built it: download 157 weekly TSA PDFs, parse them into per-airport daily counts, aggregate to monthly, and generate the dashboard data. Details are in `PIPELINE.md`.

The raw TSA PDFs are not in this repo. Run `dl.py` to fetch them yourself, they are public.
