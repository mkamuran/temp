from datetime import date, datetime
import traceback

from flask import Blueprint, jsonify, render_template, request

from app.market_data import MAX_SYMBOLS, fetch_histories, load_markets
from app.similarity import TARGET_POINTS, prepare_series, similarity_score


bp = Blueprint("main", __name__)

PERIODS = {
	"1mo": "1ヶ月",
	"3mo": "3ヶ月",
	"6mo": "6ヶ月",
	"1y": "1年",
	"3y": "3年",
	"5y": "5年",
}

ANCHORS = {
	"right": "基準日を右端",
	"center": "基準日を中央",
	"left": "基準日を左端",
}


@bp.get("/")
def index():
	markets = load_markets()
	return render_template(
		"index.html",
		markets=markets,
		periods=PERIODS,
		anchors=ANCHORS,
		default_market="nikkei225",
		default_anchor="right",
		today=date.today().isoformat(),
	)


@bp.get("/api/health")
def health():
	return jsonify({
		"ok": True,
		"max_symbols": MAX_SYMBOLS,
	})


@bp.post("/api/search")
def search():
	payload = request.get_json(silent=True) or {}

	market = payload.get("market", "nikkei225")
	period = payload.get("period", "6mo")
	anchor = payload.get("anchor", "right")
	base_date_text = payload.get("base_date", date.today().isoformat())
	points = payload.get("points", [])
	try:
		top_n = int(payload.get("top_n", 10))
	except ValueError:
		return jsonify({"error": "表示件数の指定が不正です。"}), 400
	min_avg_volume = payload.get("min_avg_volume")

	if period not in PERIODS:
		return jsonify({"error": "期間の指定が不正です。"}), 400

	if anchor not in ANCHORS:
		return jsonify({"error": "基準日の位置指定が不正です。"}), 400

	try:
		base_date = datetime.strptime(base_date_text, "%Y-%m-%d").date()
	except ValueError:
		return jsonify({"error": "基準日の形式が不正です。"}), 400

	if base_date > date.today():
		return jsonify({"error": "未来の基準日は指定できません。"}), 400

	if not isinstance(points, list) or len(points) < 8:
		return jsonify({"error": "線をもう少し長く描いてください。"}), 400

	top_n = max(3, min(top_n, 30))

	try:
		min_avg_volume = float(min_avg_volume) if min_avg_volume not in [None, ""] else None
	except ValueError:
		return jsonify({"error": "出来高フィルターは数値で入力してください。"}), 400

	draw_series = prepare_series(points, TARGET_POINTS)

	try:
		histories = fetch_histories(market, period, base_date, anchor)
	except Exception:
		traceback.print_exc()
		return jsonify({
			"error": "株価データの取得中にエラーが発生しました。時間をおいて再検索してください。",
		}), 502

	results = []
	for item in histories:
		if min_avg_volume is not None and item["avg_volume"] < min_avg_volume:
			continue

		price_series = prepare_series(item["close"], TARGET_POINTS)
		if not price_series:
			continue

		score = similarity_score(draw_series, price_series)
		results.append({
			"ticker": item["ticker"],
			"name": item["name"],
			"sector": item["sector"],
			"score": round(score, 1),
			"avg_volume": round(item["avg_volume"]),
			"latest_close": round(item["latest_close"], 2),
			"base_date": item["base_date"],
			"yahoo_url": item["yahoo_url"],
			"minkabu_url": item["minkabu_url"],
			"draw_series": draw_series,
			"price_series": price_series,
		})

	results.sort(key=lambda row: row["score"], reverse=True)

	return jsonify({
		"results": results[:top_n],
		"searched": len(histories),
		"matched": len(results),
		"period": period,
		"anchor": anchor,
		"base_date": base_date.isoformat(),
	})
