"""Phase A4: validate the ETF-proxy carry against direct calendar-spread carry.

The headline strategy uses an ETF-vs-futures spread as a PROXY for curve
carry. The "real" carry signal is (P_far - P_near) / P_near using actual
futures contracts on the same commodity at two different expiries.

yfinance preserves only currently-active contracts (the 2026-2027 CL
expiries are available; older ones return 404), so we can build a direct
calendar-spread carry going back to ~2018 -- the window where the
longest-dated currently-active contract had been listed for some time.

For WTI specifically: pull every available CL contract, identify on each
date the contract whose expiry is closest to t + 180 days, compute
direct_carry = (P_that_contract - CL=F) / CL=F * (365 / days_to_far).

Then compare to the ETF-proxy carry (USO underperformance vs CL=F over
the same trailing window). High correlation -> proxy is validated. Low
correlation -> the proxy is capturing something different and the
headline interpretation needs caveats.

    uv run python scripts/run_calendar_carry_validation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from statarb.backtest import Backtester
from statarb.costs import LinearCostModel
from statarb.data import PriceData, mask_known_anomalies
from statarb.evaluation import bootstrap_sharpe, evaluate

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
CSV_PATH = REPO_ROOT / "reports" / "09_calendar_carry_validation.csv"

# WTI contracts currently in yfinance (verified by an earlier probe).
# Each contract has data starting roughly when it began trading.
WTI_CONTRACTS = [
    "CLN26.NYM", "CLQ26.NYM", "CLU26.NYM", "CLV26.NYM", "CLX26.NYM", "CLZ26.NYM",
    "CLF27.NYM", "CLG27.NYM", "CLH27.NYM", "CLJ27.NYM", "CLK27.NYM", "CLM27.NYM",
    "CLN27.NYM", "CLQ27.NYM", "CLU27.NYM", "CLV27.NYM", "CLX27.NYM", "CLZ27.NYM",
]

# CME month-code -> calendar month
MONTH_CODE = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}


def contract_expiry(ticker: str) -> pd.Timestamp:
    """Approximate WTI contract expiry: 20th of the month preceding delivery.

    Real CL expiry is the 3rd business day before the 25th of the month
    PRIOR to delivery. We use the 20th of the prior month as a sufficient
    approximation for picking "which contract is closest to t+180d."
    """
    # ticker like "CLZ26.NYM" -> month code 'Z' (Dec), year 26 -> 2026
    body = ticker.split(".")[0]  # "CLZ26"
    month_code = body[2]
    year_two = int(body[3:5])
    delivery_year = 2000 + year_two
    delivery_month = MONTH_CODE[month_code]
    # Expiry ~= 20th of month preceding delivery
    if delivery_month == 1:
        exp_month, exp_year = 12, delivery_year - 1
    else:
        exp_month, exp_year = delivery_month - 1, delivery_year
    return pd.Timestamp(year=exp_year, month=exp_month, day=20)


def fetch_contracts(tickers: list[str]) -> pd.DataFrame:
    """Fetch each contract's adjusted close, return wide DataFrame."""
    import yfinance as yf
    cols = {}
    for t in tickers:
        df = yf.download(t, period="max", auto_adjust=False, progress=False, repair=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            print(f"  WARN: empty data for {t}")
            continue
        cols[t] = df["Adj Close"]
    return pd.concat(cols, axis=1).sort_index()


def build_far_series(
    contracts: pd.DataFrame,
    *,
    target_offset_days: int = 180,
) -> tuple[pd.Series, pd.Series]:
    """For each date t, pick the contract whose expiry is closest to
    t + target_offset_days. Return (far_price_series, days_to_far_series).
    """
    expiries = {t: contract_expiry(t) for t in contracts.columns}
    far_price = pd.Series(index=contracts.index, dtype=float)
    far_days = pd.Series(index=contracts.index, dtype=float)
    for date in contracts.index:
        target = date + pd.Timedelta(days=target_offset_days)
        # Pick contract whose expiry is closest to `target`, among those with
        # valid (non-NaN) price at `date` and expiry strictly after `date`.
        best_ticker = None
        best_diff = pd.Timedelta(days=365 * 100)  # 100 years as sentinel
        for t, exp in expiries.items():
            if exp <= date:
                continue
            price = contracts.loc[date, t]
            if pd.isna(price):
                continue
            diff = abs(exp - target)
            if diff < best_diff:
                best_diff = diff
                best_ticker = t
        if best_ticker is not None:
            far_price.loc[date] = contracts.loc[date, best_ticker]
            far_days.loc[date] = (expiries[best_ticker] - date).days
    return far_price.dropna(), far_days.dropna()


def main() -> int:
    print("=" * 76)
    print("PHASE A4 -- WTI calendar-spread carry vs ETF-proxy carry")
    print("=" * 76)

    # --- Step 1: fetch contracts + cached front-month + ETF ---
    print("\nFetching individual WTI contracts...")
    contracts = fetch_contracts(WTI_CONTRACTS)
    print(f"  {len(contracts.columns)} contracts loaded; "
          f"span {contracts.index.min().date()} -> {contracts.index.max().date()}")

    pd_raw = PriceData.load()
    adj_clean = mask_known_anomalies(pd_raw.adj_close())
    front = adj_clean["CL=F"]
    uso = adj_clean["USO"]

    # --- Step 2: build the rolling 6-month-out far series ---
    print("\nBuilding 6-month-out rolling far-contract series...")
    far_price, far_days = build_far_series(contracts, target_offset_days=180)
    far_price.name = "P_far_6mo"
    far_days.name = "days_to_far"
    print(f"  far series spans {far_price.index.min().date()} -> {far_price.index.max().date()}, "
          f"{len(far_price)} obs; days-to-far median = {far_days.median():.0f}")

    # --- Step 3: build the direct calendar-spread carry ---
    # Align with front
    common = far_price.index.intersection(front.dropna().index)
    front_aligned = front.loc[common]
    far_aligned = far_price.loc[common]
    days_aligned = far_days.loc[common]
    # Annualized carry, signed to match the project's "high = bullish" convention:
    # Backwardation (far < near) -> POSITIVE direct_carry (long earns roll-up yield).
    # Contango (far > near) -> NEGATIVE direct_carry (long pays roll-down cost).
    # Equivalently: -(P_far - P_near) / P_near.  This matches the ETF-proxy
    # where contango -> negative spread.
    direct_carry = -(far_aligned / front_aligned - 1.0) * (365.0 / days_aligned)
    direct_carry = direct_carry.replace([np.inf, -np.inf], np.nan).dropna()
    direct_carry.name = "direct_carry_6mo"

    print(f"\nDirect calendar-spread carry over {direct_carry.index.min().date()} -> "
          f"{direct_carry.index.max().date()} ({len(direct_carry)} obs):")
    print(f"  mean = {direct_carry.mean():+.4f}  ({direct_carry.mean()*100:+.2f}% annualized)")
    print(f"  median = {direct_carry.median():+.4f}")
    print(f"  std = {direct_carry.std(ddof=1):.4f}")
    # Backwardation = positive carry. Contango = negative carry.
    pct_back = (direct_carry > 0).mean() * 100
    pct_con = (direct_carry < 0).mean() * 100
    print(f"  Backwardation (carry>0): {pct_back:.1f}% of days")
    print(f"  Contango      (carry<0): {pct_con:.1f}% of days")

    # --- Step 4: ETF-proxy carry (USO underperformance vs CL=F over trailing 21d) ---
    print("\nETF-proxy carry (USO 21d return - CL=F 21d return):")
    etf_carry = (uso / uso.shift(21) - 1.0) - (front / front.shift(21) - 1.0)
    etf_carry.name = "etf_proxy_carry_21d"
    etf_carry = etf_carry.dropna()
    print(f"  mean = {etf_carry.mean():+.4f}  ({etf_carry.mean()*100:+.2f}% per 21d window)")
    print(f"  median = {etf_carry.median():+.4f}")

    # --- Step 5: comparison ---
    joined = pd.concat([direct_carry, etf_carry], axis=1).dropna()
    print(f"\nOverlap window (ALL): {joined.index.min().date()} -> "
          f"{joined.index.max().date()} ({len(joined)} obs)")

    # FULL-WINDOW comparison -- caveat: far-leg TTM ranges widely
    corr = joined.corr().iloc[0, 1]
    print(f"  Pearson correlation (all TTMs): {corr:+.3f}")
    print("  WARNING: this mixes long-dated and short-dated calendar spreads,")
    print("  because yfinance only preserved currently-active (2026+) contracts.")

    # RESTRICTED comparison: only days where the far leg is ~3-9 months out
    # (a real "calendar carry" timeframe). Outside this range we're capturing
    # something different from textbook curve carry.
    tight_mask = (days_aligned.reindex(joined.index) >= 90) & (days_aligned.reindex(joined.index) <= 270)
    joined_tight = joined.loc[tight_mask].dropna()
    if len(joined_tight) >= 30:
        corr_tight = joined_tight.corr().iloc[0, 1]
        spearman_tight = joined_tight.corr(method="spearman").iloc[0, 1]
        print("\n  RESTRICTED to days where far leg TTM in [90, 270] days:")
        print(f"    {len(joined_tight)} obs, "
              f"{joined_tight.index.min().date()} -> {joined_tight.index.max().date()}")
        print(f"    Pearson correlation: {corr_tight:+.3f}")
        print(f"    Spearman correlation: {spearman_tight:+.3f}")
        sign_agree_t = (np.sign(joined_tight.iloc[:, 0]) == np.sign(joined_tight.iloc[:, 1])).mean() * 100
        print(f"    Sign agreement: {sign_agree_t:.1f}% of days")
    else:
        print(f"\n  RESTRICTED comparison: only {len(joined_tight)} days qualify -- too few to report.")

    # Spearman (rank)
    spearman = joined.corr(method="spearman").iloc[0, 1]
    print(f"  Spearman correlation: {spearman:+.3f}")

    # Sign agreement
    direct_sign = np.sign(joined["direct_carry_6mo"])
    proxy_sign = np.sign(joined["etf_proxy_carry_21d"])
    sign_agree = (direct_sign == proxy_sign).mean() * 100
    print(f"  Sign agreement: {sign_agree:.1f}% of days")

    # --- Step 6: standalone Sharpe of each as a WTI-only signal ---
    # Since both are scalar signals for one asset, we can only do a
    # time-series (long if positive, short if negative) backtest.
    print("\nWTI-only time-series backtest (long when carry > 0, short when < 0):")
    pd_view = PriceData(adj_clean)
    bt = Backtester(pd_view, LinearCostModel(bps_per_side=10))

    # Align the trade-able window to where both signals exist
    test_idx = joined.index.intersection(adj_clean.index)
    for name, carry_series in [("direct_carry_6mo", direct_carry), ("etf_proxy_carry", etf_carry)]:
        sig = carry_series.reindex(test_idx)
        # Trade: weight = sign of carry (long if positive, short if negative)
        weights = pd.DataFrame(0.0, index=test_idx, columns=["CL=F"])
        weights["CL=F"] = np.sign(sig).fillna(0.0)
        res = bt.run(weights)
        rep = evaluate(res)
        boot = bootstrap_sharpe(res.net_returns, n_resamples=5000, block_length=20, rng_seed=0)
        print(f"  {name:>22}: Sharpe={rep.sharpe:+.3f}  CAGR={rep.cagr:+.2%}  "
              f"MaxDD={rep.max_drawdown:.2%}  CI=[{boot.ci_low:+.2f},{boot.ci_high:+.2f}]")

    # --- Step 7: save artifacts ---
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({
        "direct_carry_6mo": joined["direct_carry_6mo"],
        "etf_proxy_carry_21d": joined["etf_proxy_carry_21d"],
        "days_to_far": days_aligned.reindex(joined.index),
    })
    out.to_csv(CSV_PATH)
    print(f"\nsaved {CSV_PATH}")

    # Time-series chart
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(joined.index, joined["direct_carry_6mo"] * 100,
                 color="#1f4e79", linewidth=1.2, label="direct (CLnear-CLfar, ann)")
    axes[0].axhline(0, color="black", linewidth=0.5)
    axes[0].set_ylabel("annualized carry (%)")
    axes[0].set_title("Direct calendar-spread carry (WTI 6-month rolling)")
    axes[0].grid(alpha=0.3)
    axes[0].legend(loc="best", frameon=False)
    axes[1].plot(joined.index, joined["etf_proxy_carry_21d"] * 100,
                 color="#7b241c", linewidth=1.2, label="ETF-proxy (USO-CL=F 21d)")
    axes[1].axhline(0, color="black", linewidth=0.5)
    axes[1].set_ylabel("21-day spread (%)")
    axes[1].set_title("ETF-proxy carry (USO 21d return - CL=F 21d return)")
    axes[1].grid(alpha=0.3)
    axes[1].legend(loc="best", frameon=False)
    fig.suptitle(f"WTI carry: direct vs ETF-proxy  (Pearson {corr:+.2f}, sign-agree {sign_agree:.0f}%)")
    fig.tight_layout()
    out_chart = CHARTS_DIR / "09_calendar_carry_vs_proxy.png"
    fig.savefig(out_chart, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"saved chart: {out_chart}")

    # Scatter plot
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(joined["direct_carry_6mo"], joined["etf_proxy_carry_21d"],
               s=4, alpha=0.4, color="#1f4e79")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=0.5)
    ax.set_xlabel("direct calendar-spread carry (annualized)")
    ax.set_ylabel("ETF-proxy carry (21d spread)")
    ax.set_title(f"Direct vs proxy carry  (Pearson {corr:+.2f})")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "09_carry_scatter.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"saved chart: {CHARTS_DIR / '09_carry_scatter.png'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
