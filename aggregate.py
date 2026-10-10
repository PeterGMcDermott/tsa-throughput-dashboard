"""Aggregate parsed daily TSA data -> monthly per-airport, YoY growth, rankings."""
import json
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
PROC = BASE / "processed"

def load_daily():
    frames = []
    for f in sorted(PROC.glob("daily_*.csv")):
        df = pd.read_csv(f, parse_dates=["throughput_date"])
        frames.append(df)
    daily = pd.concat(frames, ignore_index=True)
    # dedupe (overlapping weeks shouldn't exist, but be safe)
    daily = daily.groupby(["throughput_date", "airport_code"], as_index=False)["throughput_count"].sum()
    # continuity: PBI renamed to DJT in Mar 2026 (same physical airport)
    daily["airport_code"] = daily["airport_code"].replace({"DJT": "PBI"})
    daily = daily.groupby(["throughput_date", "airport_code"], as_index=False)["throughput_count"].sum()
    return daily

def main():
    daily = load_daily()
    print(f"daily rows: {len(daily)}, airports: {daily['airport_code'].nunique()}, "
          f"range: {daily['throughput_date'].min().date()}..{daily['throughput_date'].max().date()}")
    daily["ym"] = daily["throughput_date"].dt.to_period("M").astype(str)
    # keep only COMPLETE months (all days of month present)
    daily["dim"] = daily["throughput_date"].dt.days_in_month
    cov = daily.groupby("ym").agg(days=("throughput_date", "nunique"), dim=("dim", "first"))
    complete = cov[cov["days"] == cov["dim"]].index.tolist()
    print(f"complete months: {complete[0]}..{complete[-1]} ({len(complete)})")
    daily = daily[daily["ym"].isin(complete)]
    monthly = daily.groupby(["ym", "airport_code"], as_index=False)["throughput_count"].sum()
    monthly.to_csv(PROC / "monthly.csv", index=False)

    # pivot: rows=airport, cols=ym
    piv = monthly.pivot(index="airport_code", columns="ym", values="throughput_count").fillna(0)
    months = sorted(piv.columns)
    print(f"{len(months)} months: {months[0]}..{months[-1]}")

    # TTM windows: last full 12m vs prior 12m
    last12 = months[-12:]
    prev12 = months[-24:-12]
    print("TTM:", last12[0], "..", last12[-1], " vs ", prev12[0], "..", prev12[-1])
    ttm_now = piv[last12].sum(axis=1)
    ttm_prev = piv[prev12].sum(axis=1)
    # require decent coverage in both windows (>=10 months with data)
    cov_now = (piv[last12] > 0).sum(axis=1)
    cov_prev = (piv[prev12] > 0).sum(axis=1)

    res = pd.DataFrame({
        "ttm_now": ttm_now, "ttm_prev": ttm_prev,
        "cov_now": cov_now, "cov_prev": cov_prev,
    })
    res["abs_change"] = res["ttm_now"] - res["ttm_prev"]
    res["pct_change"] = res["abs_change"] / res["ttm_prev"].replace(0, pd.NA)
    res["avg_monthly_now"] = res["ttm_now"] / 12
    ok = res[(res["cov_now"] >= 10) & (res["cov_prev"] >= 10) & (res["ttm_prev"] > 120_000)]
    print(f"airports qualifying: {len(ok)}")

    rank = ok.sort_values("pct_change", ascending=False)
    print("\nTop 10 growers (% TTM YoY):")
    for code, r in rank.head(10).iterrows():
        print(f"  {code}: {r['pct_change']:+.1%}  ({r['ttm_prev']/1e6:.2f}M -> {r['ttm_now']/1e6:.2f}M)")
    print("\nTop 10 shrinkers (% TTM YoY):")
    for code, r in rank.tail(10).iloc[::-1].iterrows():
        print(f"  {code}: {r['pct_change']:+.1%}  ({r['ttm_prev']/1e6:.2f}M -> {r['ttm_now']/1e6:.2f}M)")
    print("\nTop 10 growers (absolute):")
    for code, r in ok.sort_values("abs_change", ascending=False).head(10).iterrows():
        print(f"  {code}: {r['abs_change']/1e6:+.2f}M  ({r['pct_change']:+.1%})")
    print("\nTop 10 shrinkers (absolute):")
    for code, r in ok.sort_values("abs_change").head(10).iterrows():
        print(f"  {code}: {r['abs_change']/1e6:+.2f}M  ({r['pct_change']:+.1%})")

    # national monthly totals + YoY
    nat = monthly.groupby("ym")["throughput_count"].sum()
    nat_yoy = nat.pct_change(12)
    print("\nNational monthly YoY (last 12m):")
    for ym in months[-12:]:
        print(f"  {ym}: {nat[ym]/1e6:.1f}M  YoY {nat_yoy[ym]:+.1%}")

    res.to_csv(PROC / "growth_ttm.csv")
    nat.to_csv(PROC / "national_monthly.csv", header=["throughput_count"])

if __name__ == "__main__":
    main()
