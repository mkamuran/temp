import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_TTL_SECONDS = 30 * 60
BATCH_SIZE = int(os.environ.get("YFINANCE_BATCH_SIZE", "80"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "80"))

_history_cache = {}

PERIOD_TRADING_DAYS = {
	"1mo": 21,
	"3mo": 63,
	"6mo": 126,
	"1y": 252,
	"3y": 756,
	"5y": 1260,
}


def load_markets():
	markets = {}

	for csv_file in DATA_DIR.glob("*.csv"):
		market = csv_file.stem
		df = pd.read_csv(csv_file, dtype=str).fillna("")
		markets[market] = df.to_dict("records")

	return markets


def get_symbols(market):
	markets = load_markets()
	if market not in markets:
		raise ValueError(f"unknown market: {market}")

	return markets[market]


def yahoo_url(ticker):
	return f"https://finance.yahoo.co.jp/quote/{ticker}"


def minkabu_url(ticker):
	code = ticker.replace(".T", "")
	return f"https://minkabu.jp/stock/{code}"


def _extract_symbol_frame(raw, ticker):
	if raw.empty:
		return pd.DataFrame()

	if isinstance(raw.columns, pd.MultiIndex):
		if ticker in raw.columns.get_level_values(0):
			return raw[ticker].copy()
		if ticker in raw.columns.get_level_values(1):
			return raw.xs(ticker, axis=1, level=1).copy()
		return pd.DataFrame()

	return raw.copy()


def _calendar_range(base_date, trading_days, anchor):
	if anchor == "left":
		start = base_date - timedelta(days=10)
		end = base_date + timedelta(days=trading_days * 2 + 10)
	elif anchor == "center":
		half = trading_days // 2
		start = base_date - timedelta(days=half * 2 + 10)
		end = base_date + timedelta(days=(trading_days - half) * 2 + 10)
	else:
		start = base_date - timedelta(days=trading_days * 2 + 10)
		end = base_date + timedelta(days=1)

	today = date.today()
	return start, min(end, today + timedelta(days=1))


def _slice_around_base(frame, base_date, trading_days, anchor):
	frame = frame.sort_index()
	frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()

	candidate_dates = frame.index[frame.index.date <= base_date]
	if candidate_dates.empty:
		return pd.DataFrame(), None

	base_session = candidate_dates[-1]
	base_pos = frame.index.get_loc(base_session)

	if anchor == "left":
		start_pos = base_pos
		end_pos = start_pos + trading_days
	elif anchor == "center":
		before = trading_days // 2
		start_pos = base_pos - before
		end_pos = start_pos + trading_days
	else:
		end_pos = base_pos + 1
		start_pos = end_pos - trading_days

	if start_pos < 0 or end_pos > len(frame):
		return pd.DataFrame(), str(base_session.date())

	return frame.iloc[start_pos:end_pos].copy(), str(base_session.date())


def _chunks(values, size):
	for index in range(0, len(values), size):
		yield values[index:index + size]


def _representative_symbols(symbols):
	if MAX_SYMBOLS <= 0 or len(symbols) <= MAX_SYMBOLS:
		return symbols

	total = len(symbols)
	return [symbols[int(index * total / MAX_SYMBOLS)] for index in range(MAX_SYMBOLS)]


def _download_batch(tickers, start_date, end_date):
	return yf.download(
		" ".join(tickers),
		start=start_date.isoformat(),
		end=end_date.isoformat(),
		interval="1d",
		group_by="ticker",
		auto_adjust=False,
		progress=False,
		threads=True,
	)


def fetch_histories(market, period, base_date, anchor):
	trading_days = PERIOD_TRADING_DAYS[period]
	cache_key = (market, period, str(base_date), anchor)
	now = time.time()

	if cache_key in _history_cache:
		expires_at, rows = _history_cache[cache_key]
		if expires_at > now:
			return rows

	symbols = _representative_symbols(get_symbols(market))
	tickers = [row["ticker"] for row in symbols]
	start_date, end_date = _calendar_range(base_date, trading_days, anchor)

	rows = []
	failed_batches = 0
	meta_by_ticker = {row["ticker"]: row for row in symbols}

	for batch in _chunks(tickers, BATCH_SIZE):
		try:
			raw = _download_batch(batch, start_date, end_date)
		except Exception:
			failed_batches += 1
			continue

		for ticker in batch:
			frame = _extract_symbol_frame(raw, ticker)
			if frame.empty or "Close" not in frame.columns:
				continue

			frame = frame[["Close", "Volume"]].dropna(subset=["Close"]).copy()
			if frame.empty:
				continue

			frame, resolved_base_date = _slice_around_base(frame, base_date, trading_days, anchor)
			if frame.empty:
				continue

			close = frame["Close"].astype(float)
			volume = frame["Volume"].fillna(0).astype(float)
			meta = meta_by_ticker[ticker]

			rows.append({
				"ticker": ticker,
				"name": meta.get("name", ticker),
				"sector": meta.get("sector", ""),
				"dates": [str(idx.date()) for idx in frame.index],
				"base_date": resolved_base_date,
				"close": close.tolist(),
				"avg_volume": float(volume.mean()),
				"latest_close": float(close.iloc[-1]),
				"yahoo_url": yahoo_url(ticker),
				"minkabu_url": minkabu_url(ticker),
			})

	if not rows and failed_batches:
		raise RuntimeError("failed to fetch market data")

	_history_cache[cache_key] = (now + CACHE_TTL_SECONDS, rows)
	return rows
