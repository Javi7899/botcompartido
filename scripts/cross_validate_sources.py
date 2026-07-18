"""Cross-validación de fuentes contra referencias independientes (Fase 2).

Cierra la validación de nivel 1 del spec 2.1.6 de forma automática:
    python scripts/cross_validate_sources.py

- Opciones: OI por vencimiento e IV ATM de yfinance vs CBOE (JSON público).
- OHLCV: closes de yfinance vs API histórica pública de Nasdaq.
- VIX: último valor de FRED (VIXCLS) vs Yahoo (^VIX) en la misma fecha.
"""

import sys
from datetime import date, datetime, timedelta

from quantbot.data.crosscheck import (
    MIN_IV_COMPARISON_DTE,
    atm_iv,
    compare_atm_iv,
    compare_closes,
    compare_oi,
    fetch_cboe_options,
    fetch_nasdaq_closes,
    oi_by_expiration,
)
from quantbot.data.fred import fetch_series

OPTIONS_TICKERS = ("SPY", "AAPL", "NVDA")
CLOSE_TICKERS = ("AAPL", "KO", "JPM")
MAX_EXPIRATIONS = 3


def check_options(ticker: str) -> list[str]:
    import yfinance as yf

    spot, cboe_options = fetch_cboe_options(ticker)
    cboe_oi = oi_by_expiration(cboe_options)

    yf_ticker = yf.Ticker(ticker)
    yf_oi: dict[date, int] = {}
    for exp_str in yf_ticker.options[:MAX_EXPIRATIONS]:
        expiration = date.fromisoformat(exp_str)
        chain = yf_ticker.option_chain(exp_str)
        yf_oi[expiration] = int(
            chain.calls["openInterest"].fillna(0).sum()
            + chain.puts["openInterest"].fillna(0).sum()
        )

    # IV: primer vencimiento con >=14 días de vida; en los sub-semanales la
    # IV está dominada por el timing del snapshot y no es comparable.
    iv_exp: date | None = None
    yf_atm: float | None = None
    today = date.today()
    for exp_str in yf_ticker.options:
        expiration = date.fromisoformat(exp_str)
        if (expiration - today).days >= MIN_IV_COMPARISON_DTE:
            iv_exp = expiration
            chain = yf_ticker.option_chain(exp_str)
            near = chain.calls[
                (chain.calls["strike"] / spot - 1).abs() <= 0.05
            ]["impliedVolatility"]
            yf_atm = float(near.median()) if not near.empty else None
            break

    issues = compare_oi(ticker, yf_oi, cboe_oi)
    if iv_exp is not None:
        cboe_atm = atm_iv(cboe_options, spot, iv_exp)
        print(
            f"     {ticker} IV ATM ({iv_exp}): yfinance="
            f"{yf_atm if yf_atm is not None else float('nan'):.3f} vs "
            f"CBOE={cboe_atm if cboe_atm is not None else float('nan'):.3f}"
        )
        issues += compare_atm_iv(ticker, yf_atm, cboe_atm)
    for expiration in sorted(yf_oi):
        print(
            f"     {ticker} {expiration}: OI yfinance={yf_oi[expiration]:,} "
            f"vs CBOE={cboe_oi.get(expiration, 0):,}"
        )
    return issues


def check_closes(ticker: str) -> list[str]:
    import yfinance as yf

    df = yf.Ticker(ticker).history(
        period="3mo", interval="1d", auto_adjust=False
    )
    yf_closes = {ts.date(): float(row["Close"]) for ts, row in df.iterrows()}
    reference = fetch_nasdaq_closes(
        ticker, date.today() - timedelta(days=45), date.today()
    )
    return compare_closes(ticker, yf_closes, reference)


def check_vix() -> list[str]:
    import yfinance as yf

    fred_obs = {o.obs_date: o.value for o in fetch_series("VIXCLS")}
    df = yf.Ticker("^VIX").history(period="1mo", interval="1d")
    yahoo = {ts.date(): float(row["Close"]) for ts, row in df.iterrows()}
    shared = sorted(set(fred_obs) & set(yahoo))
    if not shared:
        return ["VIX: ninguna fecha compartida entre FRED y Yahoo"]
    last = shared[-1]
    deviation = abs(fred_obs[last] / yahoo[last] - 1)
    print(
        f"     VIX {last}: FRED={fred_obs[last]:.2f} vs "
        f"Yahoo={yahoo[last]:.2f}"
    )
    if deviation > 0.03:
        return [
            f"VIX {last}: FRED={fred_obs[last]:.2f} vs Yahoo="
            f"{yahoo[last]:.2f} (desviación {deviation:.1%})"
        ]
    return []


def main() -> int:
    failures: list[str] = []
    print("=" * 70)
    print(f"CROSS-VALIDACIÓN DE FUENTES — {datetime.now().isoformat(' ', 'seconds')}")
    print("=" * 70)

    print("\n--- Opciones: yfinance vs CBOE ---")
    for ticker in OPTIONS_TICKERS:
        try:
            issues = check_options(ticker)
            print(f"[{'OK' if not issues else 'FALLA'}] {ticker}")
            failures += issues
        except Exception as exc:  # noqa: BLE001 - informe: registra y sigue
            failures.append(f"Opciones {ticker}: {exc}")
            print(f"[FALLA] {ticker}: {exc}")

    print("\n--- Closes diarios: yfinance vs Nasdaq ---")
    for ticker in CLOSE_TICKERS:
        try:
            issues = check_closes(ticker)
            print(f"[{'OK' if not issues else 'FALLA'}] {ticker}")
            failures += issues
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Closes {ticker}: {exc}")
            print(f"[FALLA] {ticker}: {exc}")

    print("\n--- VIX: FRED vs Yahoo ---")
    try:
        issues = check_vix()
        print(f"[{'OK' if not issues else 'FALLA'}] VIXCLS")
        failures += issues
    except Exception as exc:  # noqa: BLE001
        failures.append(f"VIX: {exc}")
        print(f"[FALLA] VIX: {exc}")

    print("\n" + "=" * 70)
    if failures:
        print(f"RESULTADO: {len(failures)} problema(s)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULTADO: cross-validación superada en todas las fuentes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
