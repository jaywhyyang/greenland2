# -*- coding: utf-8 -*-
"""
greenland2_hourly.csv 를 읽어 자체 완결형 index.html(대시보드)을 생성한다.
- 데이터를 HTML 안에 JSON으로 박아넣어 더블클릭/어떤 호스팅에서도 작동
- 확장 통계카드 + 예매율/관객수 추이 + 시간당 증가분(이동평균·스파이크 강조) + 일자별 요약표
"""
import os
import csv
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "greenland2_hourly.csv")
OUT_PATH = os.path.join(BASE, "index.html")  # GitHub Pages가 자동 인식하는 이름

MA_WINDOW = 6          # 이동평균 윈도우(시간)
SPIKE_MULT = 2.0       # 스파이크 기준: 직전 평균의 N배
SPIKE_MIN_ABS = 100    # 스파이크 최소 절대 증가분(소소한 변화 무시)


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").strip()
    if s == "":
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def load_rows(csv_path):
    rows = []
    if not os.path.exists(csv_path):
        return rows
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for d in csv.DictReader(f):
            if d.get("수집시각"):
                rows.append(d)
    return rows


def build_series(rows):
    """시간순 시계열 + 시간당 증가분/이동평균/스파이크 플래그 계산."""
    pts = []
    movie = "그린랜드 2: 마이그레이션"
    prev = None
    for d in rows:
        name = d.get("영화명") or ""
        if name:
            movie = name
        t = d.get("수집시각", "")
        book = _num(d.get("예매관객수"))
        inc = (book - prev) if (book is not None and prev is not None) else None
        pts.append({
            "time": t,
            "label": t[5:16] if len(t) >= 16 else t,  # MM-DD HH:MM
            "date": t[:10],
            "rate": _num(d.get("예매율")),
            "book": book,
            "cumul": _num(d.get("누적관객수")),
            "rank": d.get("순위", ""),
            "open": d.get("개봉일", ""),
            "inc": inc,
        })
        if book is not None:
            prev = book

    incs = [p["inc"] for p in pts]
    for i, p in enumerate(pts):
        # 직전 MA_WINDOW개의 증가분 평균(현재 제외)
        window = [v for v in incs[max(0, i - MA_WINDOW):i] if v is not None]
        ma = sum(window) / len(window) if window else None
        p["ma"] = round(ma, 1) if ma is not None else None
        p["spike"] = bool(
            p["inc"] is not None and ma is not None and ma > 0
            and p["inc"] >= SPIKE_MULT * ma and p["inc"] >= SPIKE_MIN_ABS
        )
    return movie, pts


def fmt(n):
    return f"{n:,}" if isinstance(n, (int, float)) else "-"


def latest(pts):
    for p in reversed(pts):
        if p["book"] is not None:
            return p
    return {}


def build_cards(pts):
    last = latest(pts)
    incs = [p["inc"] for p in pts if p["inc"] is not None]
    avg_hr = round(sum(incs) / len(incs)) if incs else None
    # 오늘 증가분(같은 날짜 첫값 대비)
    today = last.get("date")
    today_books = [p["book"] for p in pts if p.get("date") == today and p["book"] is not None]
    today_gain = (today_books[-1] - today_books[0]) if len(today_books) >= 2 else None
    # 최고 증가 시점
    peak = max((p for p in pts if p["inc"] is not None), key=lambda x: x["inc"], default=None)

    cards = [
        ("현재 순위", f'{last.get("rank","-")}위'),
        ("예매율", f'{last.get("rate","-")}%' if last.get("rate") is not None else "-"),
        ("예매관객수", fmt(last.get("book"))),
        ("누적관객수", fmt(last.get("cumul"))),
        ("직전 1시간 증가", fmt(last.get("inc"))),
        ("오늘 증가", fmt(today_gain)),
        ("시간당 평균", fmt(avg_hr)),
        ("최고 증가", f'{fmt(peak["inc"])} ({peak["label"]})' if peak else "-"),
    ]
    html = ""
    for k, v in cards:
        html += f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>\n'
    return html


def build_daily_table(pts):
    by_date = {}
    for p in pts:
        if p["book"] is None:
            continue
        by_date.setdefault(p["date"], []).append(p)
    rows_html = ""
    for date in sorted(by_date):
        ps = by_date[date]
        books = [p["book"] for p in ps]
        gain = books[-1] - books[0] if len(books) >= 2 else 0
        incs = [(p["inc"], p["label"]) for p in ps if p["inc"] is not None]
        peak = max(incs, default=(None, "-"))
        rates = [p["rate"] for p in ps if p["rate"] is not None]
        avg_rate = round(sum(rates) / len(rates), 1) if rates else "-"
        rows_html += (
            f"<tr><td>{date}</td><td>{len(ps)}</td>"
            f"<td>{fmt(books[0])}</td><td>{fmt(books[-1])}</td>"
            f"<td class='gain'>+{fmt(gain)}</td>"
            f"<td>{fmt(peak[0])} <span class='muted'>({peak[1]})</span></td>"
            f"<td>{avg_rate}%</td></tr>\n"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='7' class='muted'>아직 데이터가 부족합니다</td></tr>"
    return rows_html


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>__MOVIE__ · KOBIS 실시간 예매 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif; margin:0;
         background:#0f1117; color:#e7e9ee; }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:#9aa0ab; font-size:13px; margin-bottom:24px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:28px; }
  .card { background:#1a1d27; border:1px solid #262a36; border-radius:12px; padding:16px; }
  .card .k { font-size:12px; color:#9aa0ab; }
  .card .v { font-size:22px; font-weight:700; margin-top:6px; }
  .panel { background:#1a1d27; border:1px solid #262a36; border-radius:12px; padding:18px; margin-bottom:20px; }
  .panel h2 { font-size:15px; margin:0 0 14px; color:#c7ccd6; }
  canvas { width:100% !important; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:9px 10px; text-align:right; border-bottom:1px solid #262a36; white-space:nowrap; }
  th:first-child,td:first-child { text-align:left; }
  th { color:#9aa0ab; font-weight:600; }
  .gain { color:#4ade80; font-weight:600; }
  .muted { color:#6b7280; }
  .foot { color:#6b7280; font-size:12px; margin-top:16px; text-align:center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>🎬 __MOVIE__</h1>
  <div class="sub">KOBIS 실시간 예매율 · 개봉일 __OPEN__ · 마지막 갱신 <b>__UPDATED__</b> · 10분마다 자동 새로고침</div>

  <div class="cards">
__CARDS__
  </div>

  <div class="panel"><h2>예매율 추이 (%)</h2><canvas id="c_rate" height="100"></canvas></div>
  <div class="panel"><h2>예매관객수 / 누적관객수 추이</h2><canvas id="c_aud" height="100"></canvas></div>
  <div class="panel"><h2>시간당 증가분 · 이동평균(보라선) · 스파이크(빨강)</h2><canvas id="c_hourly" height="100"></canvas></div>

  <div class="panel"><h2>📅 일자별 요약</h2>
    <table>
      <thead><tr><th>날짜</th><th>수집수</th><th>시작</th><th>종료</th><th>증가</th><th>최고 시간당</th><th>평균예매율</th></tr></thead>
      <tbody>
__DAILY__
      </tbody>
    </table>
  </div>

  <div class="foot">데이터 출처: 영화관입장권 통합전산망(KOBIS) · 자동 수집 · 총 __N__개 시점</div>
</div>

<script>
const PTS = __DATA_JSON__;
const labels = PTS.map(p => p.label);
const grid = { color:'#262a36' }, tick = { color:'#9aa0ab' };
const base = () => ({
  responsive:true, interaction:{ mode:'index', intersect:false },
  plugins:{ legend:{ labels:{ color:'#c7ccd6' } } },
  scales:{ x:{ grid, ticks:tick }, y:{ grid, ticks:tick } }
});

new Chart(c_rate, { type:'line',
  data:{ labels, datasets:[{ label:'예매율(%)', data:PTS.map(p=>p.rate),
    borderColor:'#6ea8fe', backgroundColor:'rgba(110,168,254,.15)', tension:.3, fill:true, spanGaps:true }] },
  options:base() });

new Chart(c_aud, { type:'line',
  data:{ labels, datasets:[
    { label:'예매관객수', data:PTS.map(p=>p.book), borderColor:'#4ade80', tension:.3, spanGaps:true, yAxisID:'y' },
    { label:'누적관객수', data:PTS.map(p=>p.cumul), borderColor:'#f59e0b', tension:.3, spanGaps:true, yAxisID:'y1' }
  ]},
  options:{ ...base(), scales:{ x:{ grid, ticks:tick },
    y:{ position:'left', grid, ticks:tick }, y1:{ position:'right', grid:{drawOnChartArea:false}, ticks:tick } } } });

new Chart(c_hourly, { type:'bar',
  data:{ labels, datasets:[
    { type:'bar', label:'시간당 증가분', data:PTS.map(p=>p.inc),
      backgroundColor:PTS.map(p=> p.spike ? '#ef4444' : '#a78bfa'), order:2 },
    { type:'line', label:`이동평균(${PTS.length?'최근'+6+'시간':''})`, data:PTS.map(p=>p.ma),
      borderColor:'#c084fc', borderDash:[5,4], pointRadius:0, tension:.3, spanGaps:true, order:1 }
  ]},
  options:base() });
</script>
</body>
</html>
"""


def generate(csv_path=CSV_PATH, out_path=OUT_PATH):
    rows = load_rows(csv_path)
    movie, pts = build_series(rows)
    last = latest(pts)
    data_json = json.dumps(
        [{"label": p["label"], "rate": p["rate"], "book": p["book"], "cumul": p["cumul"],
          "inc": p["inc"], "ma": p["ma"], "spike": p["spike"]} for p in pts],
        ensure_ascii=False,
    )
    html = (HTML
            .replace("__MOVIE__", movie)
            .replace("__OPEN__", last.get("open", "-") or "-")
            .replace("__UPDATED__", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__CARDS__", build_cards(pts))
            .replace("__DAILY__", build_daily_table(pts))
            .replace("__N__", str(len(pts)))
            .replace("__DATA_JSON__", data_json))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    print("생성:", generate())
