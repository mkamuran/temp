const canvas = document.querySelector("#drawCanvas");
const ctx = canvas.getContext("2d");
const searchButton = document.querySelector("#searchButton");
const clearButton = document.querySelector("#clearButton");
const statusEl = document.querySelector("#status");
const summaryEl = document.querySelector("#summary");
const resultsEl = document.querySelector("#results");

let drawing = false;
let rawPoints = [];

function anchorRatio() {
	const value = document.querySelector("#anchor").value;
	if (value === "left") {
		return 0;
	}
	if (value === "center") {
		return 0.5;
	}
	return 1;
}

function drawGuide() {
	const { width, height } = canvas;
	ctx.clearRect(0, 0, width, height);
	ctx.fillStyle = "#f8fbff";
	ctx.fillRect(0, 0, width, height);
	ctx.strokeStyle = "#d9e2ef";
	ctx.lineWidth = 1;

	for (let i = 1; i < 5; i += 1) {
		const y = height * i / 5;
		ctx.beginPath();
		ctx.moveTo(0, y);
		ctx.lineTo(width, y);
		ctx.stroke();
	}

	for (let i = 1; i < 8; i += 1) {
		const x = width * i / 8;
		ctx.beginPath();
		ctx.moveTo(x, 0);
		ctx.lineTo(x, height);
		ctx.stroke();
	}

	const baseX = Math.max(2, Math.min(width - 2, width * anchorRatio()));
	ctx.strokeStyle = "#f59e0b";
	ctx.lineWidth = 3;
	ctx.beginPath();
	ctx.moveTo(baseX, 0);
	ctx.lineTo(baseX, height);
	ctx.stroke();

	ctx.fillStyle = "#8a98aa";
	ctx.font = "16px Arial";
	ctx.fillText("ここに自由に線を描いてください", 24, 34);
	ctx.fillStyle = "#b45309";
	ctx.fillText("基準日", Math.min(width - 64, baseX + 8), 62);
}

function drawUserLine() {
	drawGuide();
	if (rawPoints.length < 2) {
		return;
	}

	ctx.strokeStyle = "#2563eb";
	ctx.lineWidth = 5;
	ctx.lineJoin = "round";
	ctx.lineCap = "round";
	ctx.beginPath();
	rawPoints.forEach((point, index) => {
		if (index === 0) {
			ctx.moveTo(point.x, point.y);
		} else {
			ctx.lineTo(point.x, point.y);
		}
	});
	ctx.stroke();
}

function pointerPoint(event) {
	const rect = canvas.getBoundingClientRect();
	const scaleX = canvas.width / rect.width;
	const scaleY = canvas.height / rect.height;
	return {
		x: (event.clientX - rect.left) * scaleX,
		y: (event.clientY - rect.top) * scaleY,
	};
}

function startDrawing(event) {
	drawing = true;
	rawPoints = [pointerPoint(event)];
	canvas.setPointerCapture(event.pointerId);
	drawUserLine();
}

function moveDrawing(event) {
	if (!drawing) {
		return;
	}

	const point = pointerPoint(event);
	const last = rawPoints[rawPoints.length - 1];
	const distance = Math.hypot(point.x - last.x, point.y - last.y);

	if (distance > 4) {
		rawPoints.push(point);
		drawUserLine();
	}
}

function stopDrawing() {
	drawing = false;
	statusEl.textContent = rawPoints.length >= 8 ? "検索できます。" : "線をもう少し長く描いてください。";
}

function normalizedDrawPoints() {
	if (rawPoints.length < 2) {
		return [];
	}

	const sorted = [...rawPoints].sort((a, b) => a.x - b.x);
	return sorted.map((point) => 1 - point.y / canvas.height);
}

function clearCanvas() {
	rawPoints = [];
	drawGuide();
	statusEl.textContent = "線を描いてから検索してください。";
	summaryEl.textContent = "";
	resultsEl.className = "results-empty";
	resultsEl.textContent = "まだ検索していません。";
}

function drawOverlay(canvasEl, drawSeries, priceSeries, anchor) {
	const chart = canvasEl.getContext("2d");
	const width = canvasEl.width;
	const height = canvasEl.height;
	const pad = 18;
	const plotW = width - pad * 2;
	const plotH = height - pad * 2;

	chart.clearRect(0, 0, width, height);
	chart.fillStyle = "#ffffff";
	chart.fillRect(0, 0, width, height);
	chart.strokeStyle = "#eef2f7";
	chart.lineWidth = 1;

	for (let i = 1; i < 4; i += 1) {
		const y = pad + plotH * i / 4;
		chart.beginPath();
		chart.moveTo(pad, y);
		chart.lineTo(width - pad, y);
		chart.stroke();
	}

	const ratio = anchor === "left" ? 0 : anchor === "center" ? 0.5 : 1;
	const baseX = pad + ratio * plotW;
	chart.strokeStyle = "#f59e0b";
	chart.lineWidth = 2;
	chart.beginPath();
	chart.moveTo(baseX, pad);
	chart.lineTo(baseX, height - pad);
	chart.stroke();

	function plot(series, color, lineWidth) {
		chart.strokeStyle = color;
		chart.lineWidth = lineWidth;
		chart.lineJoin = "round";
		chart.lineCap = "round";
		chart.beginPath();
		series.forEach((value, index) => {
			const x = pad + index / (series.length - 1) * plotW;
			const y = pad + (1 - value) * plotH;
			if (index === 0) {
				chart.moveTo(x, y);
			} else {
				chart.lineTo(x, y);
			}
		});
		chart.stroke();
	}

	plot(drawSeries, "#2563eb", 3);
	plot(priceSeries, "#dc2626", 3);
}

function renderResults(results) {
	if (results.length === 0) {
		resultsEl.className = "results-empty";
		resultsEl.textContent = "条件に合う銘柄がありませんでした。出来高フィルターを下げてください。";
		return;
	}

	resultsEl.className = "result-list";
	resultsEl.innerHTML = results.map((item, index) => `
		<article class="result-card">
			<div>
				<div class="result-rank">
					<span class="rank-badge">${index + 1}</span>
					<span class="score">${item.score}%</span>
				</div>
				<h3>${item.ticker} ${item.name}</h3>
				<p class="meta">
					業種: ${item.sector || "-"}<br>
					基準日: ${item.base_date}<br>
					直近終値: ${item.latest_close.toLocaleString("ja-JP")} 円<br>
					平均出来高: ${item.avg_volume.toLocaleString("ja-JP")}
				</p>
				<div class="links">
					<a href="${item.yahoo_url}" target="_blank" rel="noreferrer">Yahoo株価</a>
					<a href="${item.minkabu_url}" target="_blank" rel="noreferrer">みんかぶ</a>
				</div>
			</div>
			<div>
				<canvas class="result-chart" width="700" height="220" data-index="${index}"></canvas>
				<div class="legend">
					<span>描いた線</span>
					<span class="price">株価</span>
					<span class="base">基準日</span>
				</div>
			</div>
		</article>
	`).join("");

	document.querySelectorAll(".result-chart").forEach((chart) => {
		const item = results[Number(chart.dataset.index)];
		drawOverlay(chart, item.draw_series, item.price_series, document.querySelector("#anchor").value);
	});
}

async function searchSimilarStocks() {
	const points = normalizedDrawPoints();
	if (points.length < 8) {
		statusEl.textContent = "線をもう少し長く描いてください。";
		return;
	}

	searchButton.disabled = true;
	statusEl.textContent = "日経225の株価を取得して比較しています。初回は少し時間がかかります。";
	summaryEl.textContent = "";

	const payload = {
		points,
		market: document.querySelector("#market").value,
		period: document.querySelector("#period").value,
		base_date: document.querySelector("#baseDate").value,
		anchor: document.querySelector("#anchor").value,
		top_n: Number(document.querySelector("#topN").value),
		min_avg_volume: document.querySelector("#minAvgVolume").value,
	};

	try {
		const response = await fetch("/api/search", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(payload),
		});
		const responseText = await response.text();
		let data;

		try {
			data = JSON.parse(responseText);
		} catch {
			throw new Error("検索APIがJSONではない応答を返しました。RenderでWeb Serviceとして起動できているか確認してください。");
		}

		if (!response.ok) {
			throw new Error(data.error || "検索に失敗しました。");
		}

		renderResults(data.results);
		statusEl.textContent = "検索完了。";
		summaryEl.textContent = `${data.base_date} 基準 / ${data.searched}銘柄を確認、条件一致 ${data.matched}銘柄`;
	} catch (error) {
		statusEl.textContent = error.message;
	} finally {
		searchButton.disabled = false;
	}
}

canvas.addEventListener("pointerdown", startDrawing);
canvas.addEventListener("pointermove", moveDrawing);
canvas.addEventListener("pointerup", stopDrawing);
canvas.addEventListener("pointercancel", stopDrawing);
clearButton.addEventListener("click", clearCanvas);
searchButton.addEventListener("click", searchSimilarStocks);
document.querySelector("#anchor").addEventListener("change", drawUserLine);

drawGuide();
