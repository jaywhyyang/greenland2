# -*- coding: utf-8 -*-
"""
greenland2_hourly.csv 를 읽어 자체 완결형 dashboard.html 을 생성한다.
- 데이터를 HTML 안에 JSON으로 박아넣으므로 더블클릭/어떤 호스팅에서도 그대로 작동
- Chart.js(CDN)로 예매율 / 예매관객수 / 누적관객수 / 시간당 증가분 그래프 표시
"""
import os
import csv
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "greenland2_hourly.csv")
OUT_PATH = os.path.join(BASE, "index.html")  # GitHub Pages가 자동 인식하는 이름


def _num(s):
    if s is None:
        return None
    s = s.replace(",", "").replace("%", "").strip()
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
        r = csv.DictReader(f)
        for d in r:
            if not d.get("수집시각"):
                continue
            rows.append(d)
    return rows


def build_series(rows):
    labels, rate, book, cumul, hourly = [], [], [], [], []
    prev_book = None
    movie_name = "그린랜드 2: 마이그레이션"
    for d in rows:
        t = d.get("수집시각", "")
        name = d.get("영화명") or ""
        if name:
            movie_name = name
        labels.append(t[5:16] if len(t) >= 16 else t)  # MM-DD HH:MM
        rate.append(_num(d.get("예매율")))
        b = _num(d.get("예매관객수"))
        book.append(b)
        cumul.append(_num(d.get("누적관객수")))
        # 시간당 증가분 (직전 예매관객수와의 차이)
        if b is not None and prev_book is not None:
            hourly.append(b - prev_book)
        else:
            hourly.append(None)
        if b is not None:
            prev_book = b
    return movie_name, labels, rate, book, cumul, hourly


def latest_summary(rows):
    for d in reversed(rows):
        if d.get("예매관객수"):
            return {
                "time": d.get("수집시각", ""),
                "rank": d.get("순위", "-"),
                "rate": d.get("예매율", "-"),
                "book": d.get("예매관객수", "-"),
                "cumul": d.get("누적관객수", "-"),
                "open": d.get("개봉일", "-"),
            }
    return {"time": "-", "rank": "-", "rate": "-", "book": "-", "cumul": "-", "open": "-"}


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{movie} · KOBIS 실시간 예매 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Malgun Gothic','Apple SD Gothic Neo',sans-serif; margin:0;
         background:#0f1117; color:#e7e9ee; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:#9aa0ab; font-size:13px; margin-bottom:24px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:28px; }}
  .card {{ background:#1a1d27; border:1px solid #262a36; border-radius:12px; padding:16px; }}
  .card .k {{ font-size:12px; color:#9aa0ab; }}
  .card .v {{ font-size:24px; font-weight:700; margin-top:6px; }}
  .panel {{ background:#1a1d27; border:1px solid #262a36; border-radius:12px; padding:18px; margin-bottom:20px; }}
  .panel h2 {{ font-size:15px; margin:0 0 14px; color:#c7ccd6; }}
  canvas {{ width:100% !important; }}
  .foot {{ color:#6b7280; font-size:12px; margin-top:16px; text-align:center; }}
  a {{ color:#6ea8fe; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🎬 {movie}</h1>
  <div class="sub">KOBIS 실시간 예매율 · 개봉일 {open} · 마지막 갱신 <b>{updated}</b></div>

  <div class="cards">
    <div class="card"><div class="k">현재 순위</div><div class="v">{rank}위</div></div>
    <div class="card"><div class="k">예매율</div><div class="v">{rate}</div></div>
    <div class="card"><div class="k">예매관객수</div><div class="v">{book}</div></div>
    <div class="card"><div class="k">누적관객수</div><div class="v">{cumul}</div></div>
  </div>

  <div class="panel"><h2>예매율 추이 (%)</h2><canvas id="c_rate" height="110"></canvas></div>
  <div class="panel"><h2>예매관객수 / 누적관객수 추이</h2><canvas id="c_aud" height="110"></canvas></div>
  <div class="panel"><h2>시간당 예매관객 증가분</h2><canvas id="c_hourly" height="110"></canvas></div>

  <div class="foot">데이터 출처: 영화관입장권 통합전산망(KOBIS) · 자동 수집 · 총 {n}개 시점</div>
</div>

<script>
const DATA = {data_json};
const grid = {{ color:'#262a36' }}, tick = {{ color:'#9aa0ab' }};
const baseOpts = sets => ({{
  responsive:true,
  interaction:{{ mode:'index', intersect:false }},
  plugins:{{ legend:{{ labels:{{ color:'#c7ccd6' }} }} }},
  scales:{{ x:{{ grid, ticks:tick }}, y:{{ grid, ticks:tick }} }}
}});
new Chart(c_rate, {{ type:'line',
  data:{{ labels:DATA.labels, datasets:[{{ label:'예매율(%)', data:DATA.rate,
    borderColor:'#6ea8fe', backgroundColor:'rgba(110,168,254,.15)', tension:.3, fill:true, spanGaps:true }}] }},
  options:baseOpts() }});
new Chart(c_aud, {{ type:'line',
  data:{{ labels:DATA.labels, datasets:[
    {{ label:'예매관객수', data:DATA.book, borderColor:'#4ade80', tension:.3, spanGaps:true, yAxisID:'y' }},
    {{ label:'누적관객수', data:DATA.cumul, borderColor:'#f59e0b', tension:.3, spanGaps:true, yAxisID:'y1' }}
  ] }},
  options:{{ ...baseOpts(), scales:{{ x:{{ grid, ticks:tick }},
    y:{{ position:'left', grid, ticks:tick }}, y1:{{ position:'right', grid:{{drawOnChartArea:false}}, ticks:tick }} }} }} }});
new Chart(c_hourly, {{ type:'bar',
  data:{{ labels:DATA.labels, datasets:[{{ label:'시간당 증가분', data:DATA.hourly, backgroundColor:'#a78bfa' }}] }},
  options:baseOpts() }});
</script>
</body>
</html>
"""


def generate(csv_path=CSV_PATH, out_path=OUT_PATH):
    rows = load_rows(csv_path)
    movie, labels, rate, book, cumul, hourly = build_series(rows)
    s = latest_summary(rows)
    data_json = json.dumps(
        {"labels": labels, "rate": rate, "book": book, "cumul": cumul, "hourly": hourly},
        ensure_ascii=False,
    )
    html = HTML.format(
        movie=movie, open=s["open"],
        updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        rank=s["rank"], rate=s["rate"], book=s["book"], cumul=s["cumul"],
        n=len(rows), data_json=data_json,
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    print("생성:", generate())
