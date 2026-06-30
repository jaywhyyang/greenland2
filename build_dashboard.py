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
BOX_CSV = os.path.join(BASE, "greenland2_boxoffice.csv")  # 개봉 후 일별 박스오피스
COMP_CSV = os.path.join(BASE, "competitors_hourly.csv")   # 경쟁작 비교(TOP-N 스냅샷)
GKEY = "그린랜드 2"  # 그린랜드2 식별 키워드
OUT_PATH = os.path.join(BASE, "index.html")  # GitHub Pages가 자동 인식하는 이름

MA_WINDOW = 6          # 이동평균 윈도우(시간)
SPIKE_MULT = 2.0       # 스파이크 기준: 직전 평균의 N배
SPIKE_MIN_ABS = 100    # 스파이크 최소 절대 증가분(소소한 변화 무시)

# 히어로(상단 꾸미기) 정보 — 필요시 여기만 수정
POSTER = "poster.jpg"
TAGLINE = "최후의 희망을 향한 가족의 사투"
CAST = "제라드 버틀러 · 모레나 바카린"

# 프로모션 물량(예매관객수에 선반영됨) — 무료 6,750 + 2,000원 1,000 = 7,750
PROMO_FREE = 6750
PROMO_PAID = 1000
PROMO_TICKETS = PROMO_FREE + PROMO_PAID


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


GAP_HOURS = 1.5  # 이 간격을 넘으면 '수집 중단'으로 보고 시간당 증가분에서 제외


def build_series(rows):
    """시간순 시계열 + 시간당 증가분/이동평균/스파이크 플래그 계산.
    수집이 끊긴(>GAP_HOURS) 구간의 증가분은 1시간치가 아니므로 None 처리(왜곡 방지)."""
    pts = []
    movie = "그린랜드 2: 마이그레이션"
    prev = None
    prev_dt = None
    for d in rows:
        name = d.get("영화명") or ""
        if name:
            movie = name
        t = d.get("수집시각", "")
        book = _num(d.get("예매관객수"))
        try:
            dt = datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = None
        inc = None
        gap = False
        if book is not None and prev is not None and dt and prev_dt:
            elapsed = (dt - prev_dt).total_seconds() / 3600
            if elapsed > GAP_HOURS:
                gap = True       # 수집 중단(너무 김) → 증가분 제외
            elif elapsed < 0.5:
                inc = None       # 분 단위(너무 짧음) → 시간당 아님, 제외
            else:
                inc = book - prev
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
            "gap": gap,
        })
        if book is not None:
            prev = book
            prev_dt = dt

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

    organic = (last.get("book") - PROMO_TICKETS) if last.get("book") is not None else None
    cards = [
        ("현재 순위", f'{last.get("rank","-")}위'),
        ("예매율", f'{last.get("rate","-")}%' if last.get("rate") is not None else "-"),
        ("예매관객수", fmt(last.get("book"))),
        ("순수 예매 (프로모션 제외)", fmt(organic)),
        ("누적관객수", fmt(last.get("cumul"))),
        ("직전 1시간 증가", fmt(last.get("inc"))),
        ("오늘 증가", fmt(today_gain)),
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


def load_box():
    rows = []
    if not os.path.exists(BOX_CSV):
        return rows
    with open(BOX_CSV, encoding="utf-8-sig", newline="") as f:
        for d in csv.DictReader(f):
            if d.get("날짜"):
                rows.append(d)
    return rows


def build_box(rows):
    out = []
    for d in rows:
        t = d.get("날짜", "")
        out.append({
            "d": t[5:] if len(t) >= 10 else t,        # MM-DD
            "audi": _num(d.get("관객수")),
            "cum": _num(d.get("누적관객수")),
            "occ": _num(d.get("좌석점유율")),
            "seat": _num(d.get("좌석판매율")),
            "screens": _num(d.get("스크린수")),
            "shows": _num(d.get("상영횟수")),
            "sales": _num(d.get("매출액")),
        })
    return out


def box_section(has_data):
    if not has_data:
        return ('<div class="panel" style="text-align:center;color:#9aa0ab;padding:42px 18px">'
                '<div style="font-size:15px;color:#c7ccd6;margin-bottom:10px">🎟️ 개봉 후 실적 (박스오피스)</div>'
                '개봉일(2026-07-01)부터 <b>일일 관객수 · 누적관객수 · 좌석점유율 · 스크린수/상영횟수</b>가<br>'
                '이 자리에 자동으로 채워집니다.<br>'
                '<span style="font-size:12px">매일 오전 9시 전날 확정치 수집 · 현재는 개봉 전</span></div>')
    return (
        '  <div class="panel"><h2>🎟️ 일일 관객수</h2><div class="cbox"><canvas id="c_box_audi"></canvas></div></div>\n'
        '  <div class="panel"><h2>누적 관객수</h2><div class="cbox"><canvas id="c_box_cum"></canvas></div></div>\n'
        '  <div class="panel"><h2>좌석점유율 / 좌석판매율 (%)</h2><div class="cbox"><canvas id="c_box_seat"></canvas></div></div>\n'
        '  <div class="panel"><h2>스크린수 / 상영횟수</h2><div class="cbox"><canvas id="c_box_supply"></canvas></div></div>')


def load_competitors():
    rows = []
    if not os.path.exists(COMP_CSV):
        return rows
    with open(COMP_CSV, encoding="utf-8-sig", newline="") as f:
        for d in csv.DictReader(f):
            if d.get("수집시각") and d.get("영화명"):
                rows.append(d)
    return rows


def build_comp(rows):
    """경쟁작: 그린랜드2와 '같은 개봉일'인 영화만 비교.
    최신 스냅샷(예매관객수 정렬 top8) + 상위 6편 예매율 시계열."""
    empty = {"latest": [], "labels": [], "series": [], "open": ""}
    if not rows:
        return empty
    times = sorted({r["수집시각"] for r in rows})
    last = times[-1]
    snap_all = [r for r in rows if r["수집시각"] == last]
    # 그린랜드2 개봉일을 기준 날짜로 사용
    target = ""
    for r in snap_all:
        if GKEY in r["영화명"]:
            target = (r.get("개봉일") or "").strip()
            break
    if not target:
        target = "2026-07-01"

    def same(r):
        return (r.get("개봉일") or "").strip() == target

    snap = [r for r in snap_all if same(r)]
    snap.sort(key=lambda r: _num(r.get("예매관객수")) or 0, reverse=True)
    latest = [{"name": r["영화명"], "book": _num(r.get("예매관객수")),
               "rate": _num(r.get("예매율")), "g": GKEY in r["영화명"]}
              for r in snap[:8]]
    top_names = [x["name"] for x in latest[:6]]

    rate_by, book_by = {}, {}  # (name, time) -> 예매율 / 예매관객수 (같은 개봉일만)
    for r in rows:
        if same(r):
            rate_by[(r["영화명"], r["수집시각"])] = _num(r.get("예매율"))
            book_by[(r["영화명"], r["수집시각"])] = _num(r.get("예매관객수"))

    dts = []
    for t in times:
        try:
            dts.append(datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            dts.append(None)

    def inc_series(nm):
        """movie의 시간별 예매관객 증가분(시간당) 리스트 + 가장 최근 증가분 반환."""
        out = [None] * len(times)
        prev = prevd = None
        last = None
        for i, t in enumerate(times):
            bk = book_by.get((nm, t))
            d = dts[i]
            if bk is not None and prev is not None and d and prevd:
                gh = (d - prevd).total_seconds() / 3600
                if 0.5 <= gh <= 1.5:
                    out[i] = bk - prev
                    last = bk - prev
            if bk is not None:
                prev, prevd = bk, d
        return out, last

    series = []
    for nm in top_names:
        incs, _ = inc_series(nm)
        series.append({"name": nm, "g": GKEY in nm,
                       "rates": [rate_by.get((nm, t)) for t in times], "incs": incs})
    # 비교 표용: 각 영화의 '직전 1시간 증가' 부착
    for m in latest:
        _, m["inc"] = inc_series(m["name"])
    short = [t[5:16] for t in times]
    return {"latest": latest, "labels": short, "series": series, "open": target}


def comp_section(comp):
    if not comp["latest"]:
        return ('<div class="panel" style="text-align:center;color:#9aa0ab;padding:32px 18px">'
                '🥊 경쟁작 비교 — 매시간 동일 개봉작을 함께 수집합니다. 곧 표시됩니다.</div>')
    d = comp["open"] or "동일 개봉일"
    # 비교 표: 영화 / 예매관객수 / 직전 1시간 증가 / 예매율
    trs = ""
    for m in comp["latest"]:
        star = "★ " if m["g"] else ""
        cls = ' style="color:#4ade80;font-weight:700"' if m["g"] else ""
        inc = m.get("inc")
        inc_s = f"+{inc:,}" if isinstance(inc, (int, float)) else "-"
        rate = f'{m["rate"]}%' if m.get("rate") is not None else "-"
        trs += (f"<tr{cls}><td>{star}{m['name']}</td><td>{fmt(m['book'])}</td>"
                f"<td class='gain'>{inc_s}</td><td>{rate}</td></tr>")
    table = (f'  <div class="panel"><h2>🥊 {d} 동시 개봉작 비교</h2>'
             '<table><thead><tr><th>영화</th><th>예매관객수</th><th>직전 1시간 ↑</th><th>예매율</th></tr></thead>'
             f'<tbody>{trs}</tbody></table>'
             '<p style="color:#9aa0ab;font-size:12px;margin:10px 2px 0">“직전 1시간 ↑”는 수집 2시간 이상 쌓여야 채워집니다.</p></div>')
    charts = (
        f'  <div class="panel"><h2>동시 개봉작 · 예매관객수 (현재)</h2><div class="cbox tall"><canvas id="c_comp_bar"></canvas></div></div>\n'
        '  <div class="panel"><h2>예매율 추이 비교 (%)</h2><div class="cbox"><canvas id="c_comp_rate"></canvas></div></div>\n'
        '  <div class="panel"><h2>시간당 예매 증가 비교 (명/시간)</h2><div class="cbox"><canvas id="c_comp_inc"></canvas></div>\n'
        '    <p style="color:#9aa0ab;font-size:12px;margin:10px 2px 0">동시 개봉작별 시간당 예매관객 증가분. 그린랜드2는 굵은 초록선.</p></div>')
    return table + "\n" + charts


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>__MOVIE__ · KOBIS 실시간 예매 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif; margin:0;
         background:#0f1117; color:#e7e9ee; }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
  h1 { font-size:26px; margin:6px 0 6px; line-height:1.2; }
  /* 히어로 */
  .hero { position:relative; display:flex; gap:22px; align-items:flex-end; overflow:hidden;
          padding:26px; border-radius:16px; border:1px solid #3a2a1a; margin-bottom:12px;
          background:linear-gradient(135deg,#3a1c0e 0%,#1a1d27 65%); }
  .hero::before { content:''; position:absolute; inset:0; z-index:0;
          background:url('__POSTER__') center/cover no-repeat; filter:blur(34px) brightness(.35); opacity:.55; }
  .hero > * { position:relative; z-index:1; }
  .poster { width:132px; flex-shrink:0; border-radius:10px; box-shadow:0 10px 28px rgba(0,0,0,.55); }
  .tagline { color:#f4c89a; font-size:14px; font-style:italic; margin:0 0 8px; }
  .meta { color:#d4d8e0; font-size:13px; margin:0 0 12px; }
  .dday { display:inline-block; background:#ef4444; color:#fff; font-size:12px; font-weight:700;
          padding:4px 11px; border-radius:999px; }
  .sub { color:#9aa0ab; font-size:13px; margin-bottom:22px; }
  .status { display:inline-block; font-size:12px; padding:6px 12px; border-radius:999px; }
  @media (max-width:560px){ .hero{ flex-direction:column; align-items:center; text-align:center; } }
  .status.ok { background:#13241a; color:#4ade80; border:1px solid #1f3a2a; }
  .status.warn { background:#2a1416; color:#f87171; border:1px solid #4a1f23; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:28px; }
  .card { background:#1a1d27; border:1px solid #262a36; border-radius:12px; padding:16px; }
  .card .k { font-size:12px; color:#9aa0ab; }
  .card .v { font-size:22px; font-weight:700; margin-top:6px; }
  .panel { background:#1a1d27; border:1px solid #262a36; border-radius:12px; padding:18px; margin-bottom:20px; }
  .panel h2 { font-size:15px; margin:0 0 14px; color:#c7ccd6; }
  .cbox { position:relative; width:100%; height:380px; margin-top:8px; }
  .cbox.short { height:300px; }
  .cbox.tall { height:460px; }
  @media (max-width:560px){ .cbox{height:300px} .cbox.tall{height:380px} }
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
  <div class="hero">
    <img class="poster" src="__POSTER__" alt="__MOVIE__ 포스터" onerror="this.style.display='none'">
    <div class="hero-body">
      <span id="dday" class="dday"></span>
      <h1>🎬 __MOVIE__</h1>
      <p class="tagline">“__TAGLINE__”</p>
      <p class="meta">개봉 __OPEN__ · __CAST__</p>
      <div id="status" class="status"></div>
    </div>
  </div>
  <div class="sub">KOBIS 실시간 예매율 · 마지막 갱신 <b>__UPDATED__</b> · 10분마다 자동 새로고침</div>

  <div class="cards">
__CARDS__
  </div>

  <div style="border-top:1px solid #262a36;margin:8px 0 18px;padding-top:6px;color:#f4c89a;font-size:14px;font-weight:600">— 경쟁작 비교 —</div>
__COMP_SECTION__

  <div style="border-top:1px solid #262a36;margin:30px 0 18px;padding-top:6px;color:#6ea8fe;font-size:14px;font-weight:600">— 그린랜드2 예매 추이 —</div>
  <div class="panel"><h2>순위 변동 추이 (위로 갈수록 상위)</h2><div class="cbox short"><canvas id="c_rank"></canvas></div></div>
  <div class="panel"><h2>예매율 추이 (%)</h2><div class="cbox"><canvas id="c_rate"></canvas></div></div>
  <div class="panel"><h2>예매관객수 추이 (예매된 표 누적)</h2><div class="cbox"><canvas id="c_book"></canvas></div>
    <p style="color:#9aa0ab;font-size:12px;margin:10px 2px 0">회색 점선 = 프로모션 물량 7,750장(무료 6,750 + 2,000원 1,000). <b style="color:#4ade80">그 위쪽이 순수 예매분</b>입니다.</p></div>
  <div class="panel"><h2>누적관객수 추이 (실제 입장, 개봉 후 증가)</h2><div class="cbox"><canvas id="c_cumul"></canvas></div></div>
  <div class="panel"><h2>시간당 증가분 · 이동평균(보라선) · 스파이크(빨강)</h2><div class="cbox"><canvas id="c_hourly"></canvas></div>
    <p style="color:#9aa0ab;font-size:12px;margin:10px 2px 0">※ 수집이 1시간 넘게 끊긴 구간(PC 꺼짐/절전 등)은 1시간치가 아니므로 증가분에서 제외합니다. (누적 그래프엔 그대로 반영)</p></div>

  <div style="border-top:1px solid #262a36;margin:30px 0 18px;padding-top:6px;color:#f4c89a;font-size:14px;font-weight:600">— 개봉 후 실적 —</div>
__BOX_SECTION__

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
Chart.register(ChartDataLabels);
const labels = PTS.map(p => p.label);
const grid = { color:'#262a36' }, tick = { color:'#9aa0ab' };
const won = v => (v==null ? '' : Number(v).toLocaleString());
const lastIdx = key => { for(let i=PTS.length-1;i>=0;i--){ if(PTS[i][key]!=null) return i; } return -1; };
const showAllBars = PTS.length <= 36;   // 점이 너무 많으면 라벨 생략(가독성)

const base = () => ({
  responsive:true, maintainAspectRatio:false,
  interaction:{ mode:'index', intersect:false },
  layout:{ padding:{ top:22 } },
  plugins:{ legend:{ labels:{ color:'#c7ccd6' } }, datalabels:{ display:false } },
  scales:{ x:{ grid, ticks:tick }, y:{ grid, ticks:tick } }
});
// 선 그래프: 마지막(현재) 값만 라벨로 표시
const lastOnly = (key, color, suffix='') => ({
  display: ctx => ctx.dataIndex === lastIdx(key),
  align:'top', color, font:{ weight:'bold', size:13 },
  formatter: v => v==null ? '' : won(v)+suffix
});

// ===== 경쟁작 비교 =====
const COMP = __COMP_JSON__;
if (COMP.latest && COMP.latest.length) {
  // 현재 예매관객수 가로 막대 (그린랜드2 강조)
  new Chart(c_comp_bar, { type:'bar',
    data:{ labels: COMP.latest.map(m=>m.name.length>16?m.name.slice(0,15)+'…':m.name),
      datasets:[{ label:'예매관객수', data:COMP.latest.map(m=>m.book),
        backgroundColor: COMP.latest.map(m=> m.g ? '#4ade80' : '#3b4252'),
        borderColor: COMP.latest.map(m=> m.g ? '#4ade80' : '#4c566a'), borderWidth:1,
        datalabels:{ anchor:'end', align:'end', color:'#e7e9ee', font:{size:11,weight:'bold'}, formatter:won } }] },
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, layout:{padding:{right:46}},
      plugins:{ legend:{display:false}, datalabels:{} },
      scales:{ x:{ grid, ticks:tick, beginAtZero:true }, y:{ grid:{display:false}, ticks:{ color:'#c7ccd6' } } } } });

  // 예매율 추이 멀티라인 (그린랜드2 굵게)
  const palette = ['#f59e0b','#60a5fa','#f472b6','#a78bfa','#22d3ee','#fb7185'];
  let ci=0;
  const ds = COMP.series.map(s => {
    const color = s.g ? '#4ade80' : palette[(ci++)%palette.length];
    // 현재 예매율을 범례에 함께 표기 → 모든 영화 수치가 겹침 없이 보임
    let lastRate = null;
    for (let i=s.rates.length-1;i>=0;i--){ if(s.rates[i]!=null){ lastRate=s.rates[i]; break; } }
    const nm = s.name.length>12 ? s.name.slice(0,11)+'…' : s.name;
    const lbl = (s.g?'★ ':'') + nm + (lastRate!=null ? `  ${lastRate}%` : '');
    // 끝 % 라벨은 그린랜드2만(겹침/잘림 방지)
    return { label: lbl, data: s.rates,
      borderColor: color, backgroundColor: color, spanGaps:true, tension:.3,
      borderWidth: s.g?3:1.5, pointRadius: s.g?3:0,
      datalabels:{ display: ctx => s.g && ctx.dataIndex===s.rates.length-1, align:'right', clamp:true,
        color, font:{weight:'bold', size:12}, formatter:v=>v==null?'':v+'%' } };
  });
  new Chart(c_comp_rate, { type:'line',
    data:{ labels: COMP.labels, datasets: ds },
    options:{ ...base(), layout:{padding:{right:60, top:22}},
      plugins:{ legend:{ labels:{ color:'#c7ccd6', boxWidth:12 } }, datalabels:{} } } });

  // 시간당 예매 증가 비교 (동시 개봉작별)
  let ci2 = 0;
  const dsi = COMP.series.map(s => {
    const color = s.g ? '#4ade80' : palette[(ci2++)%palette.length];
    const nm = s.name.length>12 ? s.name.slice(0,11)+'…' : s.name;
    return { label: (s.g?'★ ':'') + nm, data: s.incs,
      borderColor: color, backgroundColor: color, spanGaps:true, tension:.3,
      borderWidth: s.g?3:1.5, pointRadius: s.g?3:2,
      datalabels:{ display: ctx => s.g && ctx.dataIndex===s.incs.length-1, align:'top', clamp:true,
        color, font:{weight:'bold', size:12}, formatter:v=>v==null?'':'+'+won(v) } };
  });
  new Chart(c_comp_inc, { type:'line',
    data:{ labels: COMP.labels, datasets: dsi },
    options:{ ...base(), layout:{padding:{right:50, top:22}},
      plugins:{ legend:{ labels:{ color:'#c7ccd6', boxWidth:12 } }, datalabels:{} } } });
}

// 개봉 D-day 뱃지
(function(){
  const el=document.getElementById('dday'); if(!el) return;
  const d=new Date("__OPEN__"+"T00:00:00");
  if(isNaN(d.getTime())){ el.style.display='none'; return; }
  const today=new Date(); today.setHours(0,0,0,0);
  const diff=Math.round((d-today)/86400000);
  el.textContent = diff>0 ? `개봉까지 D-${diff}` : (diff===0 ? '🎬 오늘 개봉!' : `개봉 ${-diff+1}일차`);
})();

// 수집 상태: 마지막 수집 시각 기준 신선도 표시 (75분 넘으면 경고)
const LAST = "__LASTTIME__";
(function(){
  const el = document.getElementById('status');
  if(!el) return;
  if(!LAST){ el.textContent='수집 데이터 없음'; el.className='status warn'; return; }
  const t = new Date(LAST.replace(' ','T'));
  const mins = Math.floor((Date.now() - t.getTime())/60000);
  let txt, cls;
  if(mins < 2){ txt='🟢 방금 수집됨'; cls='ok'; }
  else if(mins <= 75){ txt=`🟢 정상 · 마지막 수집 ${mins}분 전`; cls='ok'; }
  else { const h=Math.floor(mins/60), m=mins%60;
    txt=`⚠️ 수집 지연 · 마지막 수집 ${h>0?h+'시간 ':''}${m}분 전 (PC 꺼짐/절전 확인)`; cls='warn'; }
  el.textContent = txt; el.className = 'status '+cls;
})();

new Chart(c_rank, { type:'line',
  data:{ labels, datasets:[{ label:'순위', data:PTS.map(p=>p.rank),
    borderColor:'#f472b6', backgroundColor:'rgba(244,114,182,.12)', tension:.3, fill:false, spanGaps:true,
    datalabels:{ display: ctx=>ctx.dataIndex===lastIdx('rank'), align:'top', color:'#f472b6',
      font:{weight:'bold',size:13}, formatter:v=>v==null?'':v+'위' } }] },
  options:{ ...base(), scales:{ x:{ grid, ticks:tick },
    y:{ reverse:true, min:1, grid, ticks:{ color:'#9aa0ab', stepSize:1, precision:0 } } } } });

new Chart(c_rate, { type:'line',
  data:{ labels, datasets:[{ label:'예매율(%)', data:PTS.map(p=>p.rate),
    borderColor:'#6ea8fe', backgroundColor:'rgba(110,168,254,.15)', tension:.3, fill:true, spanGaps:true,
    datalabels:lastOnly('rate','#6ea8fe','%') }] },
  options:base() });

new Chart(c_book, { type:'line',
  data:{ labels, datasets:[
    { label:'예매관객수', data:PTS.map(p=>p.book),
      borderColor:'#4ade80', backgroundColor:'rgba(74,222,128,.12)', tension:.3, fill:true, spanGaps:true,
      datalabels:lastOnly('book','#4ade80') },
    { label:'프로모션 물량(7,750)', data:labels.map(()=>__PROMO__),
      borderColor:'#9aa0ab', borderDash:[6,4], borderWidth:1.5, pointRadius:0, fill:false,
      datalabels:{ display:false } }
  ]},
  options:base() });

new Chart(c_cumul, { type:'line',
  data:{ labels, datasets:[{ label:'누적관객수', data:PTS.map(p=>p.cumul),
    borderColor:'#f59e0b', backgroundColor:'rgba(245,158,11,.12)', tension:.3, fill:true, spanGaps:true,
    datalabels:lastOnly('cumul','#f59e0b') }] },
  options:base() });

new Chart(c_hourly, { type:'bar',
  data:{ labels, datasets:[
    { type:'bar', label:'시간당 증가분', data:PTS.map(p=>p.inc),
      backgroundColor:PTS.map(p=> p.spike ? '#ef4444' : '#a78bfa'), order:2,
      datalabels:{ display: ctx => showAllBars && ctx.dataset.data[ctx.dataIndex]!=null,
        anchor:'end', align:'end', color:'#e7e9ee', font:{ size:11, weight:'bold' }, formatter:won } },
    { type:'line', label:'이동평균(최근 6시간)', data:PTS.map(p=>p.ma),
      borderColor:'#c084fc', borderDash:[5,4], pointRadius:0, tension:.3, spanGaps:true, order:1,
      datalabels:{ display:false } }
  ]},
  options:{ ...base(), scales:{ x:{ grid, ticks:tick }, y:{ grid, ticks:tick, beginAtZero:true } } } });

// ===== 개봉 후 박스오피스 차트 (데이터 있을 때만) =====
const BOX = __BOX_JSON__;
if (BOX.length) {
  const bl = BOX.map(b=>b.d);
  const boxAll = BOX.length <= 36;
  const lastIdxB = key => { for(let i=BOX.length-1;i>=0;i--){ if(BOX[i][key]!=null) return i; } return -1; };
  const lastLabB = (key,color,suffix='') => ({ display:ctx=>ctx.dataIndex===lastIdxB(key),
    align:'top', color, font:{weight:'bold',size:13}, formatter:v=>v==null?'':won(v)+suffix });

  new Chart(c_box_audi, { type:'bar',
    data:{ labels:bl, datasets:[{ label:'일일 관객수', data:BOX.map(b=>b.audi), backgroundColor:'#22d3ee',
      datalabels:{ display:ctx=>boxAll&&ctx.dataset.data[ctx.dataIndex]!=null, anchor:'end', align:'end',
        color:'#e7e9ee', font:{size:10,weight:'bold'}, formatter:won } }] },
    options:{ ...base(), scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick,beginAtZero:true} } } });

  new Chart(c_box_cum, { type:'line',
    data:{ labels:bl, datasets:[{ label:'누적 관객수', data:BOX.map(b=>b.cum), borderColor:'#34d399',
      backgroundColor:'rgba(52,211,153,.12)', fill:true, tension:.3, spanGaps:true, datalabels:lastLabB('cum','#34d399') }] },
    options:base() });

  new Chart(c_box_seat, { type:'line',
    data:{ labels:bl, datasets:[
      { label:'좌석점유율', data:BOX.map(b=>b.occ), borderColor:'#fbbf24', tension:.3, spanGaps:true, datalabels:lastLabB('occ','#fbbf24','%') },
      { label:'좌석판매율', data:BOX.map(b=>b.seat), borderColor:'#60a5fa', tension:.3, spanGaps:true, datalabels:lastLabB('seat','#60a5fa','%') }
    ]},
    options:base() });

  new Chart(c_box_supply, { type:'line',
    data:{ labels:bl, datasets:[
      { label:'스크린수', data:BOX.map(b=>b.screens), borderColor:'#f472b6', tension:.3, spanGaps:true, datalabels:lastLabB('screens','#f472b6') },
      { label:'상영횟수', data:BOX.map(b=>b.shows), borderColor:'#a78bfa', tension:.3, spanGaps:true, datalabels:lastLabB('shows','#a78bfa') }
    ]},
    options:base() });
}
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
          "inc": p["inc"], "ma": p["ma"], "spike": p["spike"], "rank": _num(p["rank"])} for p in pts],
        ensure_ascii=False,
    )
    box = build_box(load_box())
    box_json = json.dumps(box, ensure_ascii=False)
    comp = build_comp(load_competitors())
    comp_json = json.dumps(comp, ensure_ascii=False)
    html = (HTML
            .replace("__MOVIE__", movie)
            .replace("__OPEN__", last.get("open", "-") or "-")
            .replace("__POSTER__", POSTER)
            .replace("__TAGLINE__", TAGLINE)
            .replace("__CAST__", CAST)
            .replace("__PROMO__", str(PROMO_TICKETS))
            .replace("__UPDATED__", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__LASTTIME__", last.get("time", "") or "")
            .replace("__CARDS__", build_cards(pts))
            .replace("__DAILY__", build_daily_table(pts))
            .replace("__N__", str(len(pts)))
            .replace("__BOX_SECTION__", box_section(bool(box)))
            .replace("__BOX_JSON__", box_json)
            .replace("__COMP_SECTION__", comp_section(comp))
            .replace("__COMP_JSON__", comp_json)
            .replace("__DATA_JSON__", data_json))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    print("생성:", generate())
