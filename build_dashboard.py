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
BOXC_CSV = os.path.join(BASE, "boxoffice_competitors.csv")  # 동시개봉작 경쟁력 리더보드
COMP_CSV = os.path.join(BASE, "competitors_hourly.csv")   # 경쟁작 비교(TOP-N 스냅샷)
MEMBER_SNAP = os.path.join(BASE, "member_snapshots.csv")  # 회원통계 실관람 스냅샷
MEMBER_DETAIL = os.path.join(BASE, "member_detail.json")  # 회원통계 극장/지역/회차 상세
SCHED_JSON = os.path.join(BASE, "schedule.json")          # 배급 편성(시간대별 회차/좌석)
MEMBER_HIST = os.path.join(BASE, "member_detail_history.json")  # 날짜별 상세 이력
SCHED_HIST = os.path.join(BASE, "schedule_history.json")        # 날짜별 편성 이력
EVENTS_JSON = os.path.join(BASE, "events.json")                 # 확정 마케팅/프로모 이벤트


def _load_json(path):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def build_membydate():
    """날짜별 {체인표(편성+관객+판매율), 극장TOP} 구조 → 날짜 선택용."""
    mem = _load_json(MEMBER_HIST)
    sch = _load_json(SCHED_HIST)
    out = {}
    for date in sorted(mem):  # 실관람(회원통계) 있는 날짜만
        aud_by = {c[0]: c[3] for c in (mem.get(date, {}).get("chains") or [])}
        sc = (sch.get(date) or {}).get("chains") or {}
        chains = []
        for name in sorted(sc, key=lambda n: sc[n].get("좌석") or 0, reverse=True):
            info = sc[name]
            seat = info.get("좌석") or 0
            aud = aud_by.get(name, 0)
            sell = round(aud / seat * 100, 1) if seat else None
            chains.append([name, info.get("상영관"), info.get("회차"), seat, aud, sell])
        # 합계 (편성 총계 = 시간표 그랜드토탈, 관객 = 회원 전 체인 합)
        sd = sch.get(date) or {}
        tot_seat = sd.get("total_seats") or sum(c[3] or 0 for c in chains)
        tot_aud = sum((c[3] for c in (mem.get(date, {}).get("chains") or [])))  # member aud
        total = {
            "screens": sd.get("total_screens") or sum((c[1] or 0) for c in chains),
            "shows": sd.get("total_shows") or sum((c[2] or 0) for c in chains),
            "seats": tot_seat,
            "aud": tot_aud,
            "sell": round(tot_aud / tot_seat * 100, 1) if tot_seat else None,
        }
        sd_full = sch.get(date) or {}
        out[date] = {"chains": chains, "theaters": mem.get(date, {}).get("theaters") or [],
                     "total": total, "hourly": sd_full.get("hourly") or {},
                     "regions": sd_full.get("regions") or []}
    return out
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
            elif elapsed < 0.25:
                inc = None       # 거의 중복(너무 짧음) → 제외
            else:
                inc = round((book - prev) / elapsed)  # 시간당 환산(30분 간격도 1시간 기준으로)
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


ACTIVE_H0, ACTIVE_H1 = 9, 22  # 시간당 평균을 낼 활동시간대(09~22시)


def _win_avg(pairs):
    """(datetime, book) 목록에서 09~22시 구간만 골라 시간당 평균 증가 = (끝-시작)/경과시간."""
    w = [(dt, b) for dt, b in pairs
         if dt is not None and b is not None
         and ACTIVE_H0 <= dt.hour + dt.minute / 60.0 <= ACTIVE_H1]
    if len(w) < 2:
        return None
    h = (w[-1][0] - w[0][0]).total_seconds() / 3600
    return round((w[-1][1] - w[0][1]) / h) if h > 0 else None


def _pairs_of_day(pts, day):
    out = []
    for p in pts:
        if p.get("date") != day or p["book"] is None:
            continue
        try:
            out.append((datetime.datetime.strptime(p["time"], "%Y-%m-%d %H:%M:%S"), p["book"]))
        except ValueError:
            pass
    return out


def build_cards(pts):
    last = latest(pts)
    incs = [p["inc"] for p in pts if p["inc"] is not None]
    avg_hr = round(sum(incs) / len(incs)) if incs else None
    # 오늘 증가분 + 시간당 평균(09~22시 활동시간 기준)
    today = last.get("date")
    today_pts = [p for p in pts if p.get("date") == today and p["book"] is not None]
    today_gain = (today_pts[-1]["book"] - today_pts[0]["book"]) if len(today_pts) >= 2 else None
    today_avg = _win_avg(_pairs_of_day(pts, today))
    # 최고 증가 시점
    peak = max((p for p in pts if p["inc"] is not None), key=lambda x: x["inc"], default=None)

    # 프로모(7/1 상영분)는 개봉일에만 예매관객수에 섞여있음 → 개봉일에만 '순수예매' 표시
    promo_on = bool(last.get("date") and last.get("open") and last["date"] <= last["open"])
    organic = (last.get("book") - PROMO_TICKETS) if last.get("book") is not None else None
    cards = [
        ("현재 순위", f'{last.get("rank","-")}위'),
        ("예매율", f'{last.get("rate","-")}%' if last.get("rate") is not None else "-"),
        ("예매관객수", fmt(last.get("book"))),
    ]
    if promo_on:
        cards.append(("순수 예매 (프로모션 제외)", fmt(organic)))
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


# 시간대별 예매 강도(상대 가중치): 낮 저조, 저녁(18~21) 피크
HOUR_PROFILE = {0:0.10,1:0.05,2:0.03,3:0.03,4:0.03,5:0.05,6:0.10,7:0.20,8:0.35,
                9:0.45,10:0.55,11:0.65,12:0.70,13:0.70,14:0.80,15:0.95,16:1.10,
                17:1.30,18:1.70,19:2.00,20:2.00,21:1.60,22:1.10,23:0.60}


def forecast_eod(pts):
    """현재 페이스 + 시간대 프로파일로 오늘 23:59 예매관객수 추정."""
    import math
    valid = [p for p in pts if p["book"] is not None]
    incs = [p["inc"] for p in pts if p["inc"] is not None]
    if not valid or not incs:
        return None
    last = valid[-1]
    try:
        cur_dt = datetime.datetime.strptime(last["time"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    cur = last["book"]
    r = sum(incs[-2:]) / len(incs[-2:])      # 최근 시간당 환산 페이스(최근 2개 평균)
    if r <= 0:
        r = max(incs[-1], 1)
    cur_h = cur_dt.hour + cur_dt.minute / 60.0
    if cur_h >= 23.98:
        return {"cur": cur, "pred": cur, "low": cur, "high": cur, "r": round(r), "done": True}
    pintens = HOUR_PROFILE.get(cur_dt.hour, 0.5) or 0.5
    unit = r / pintens                        # 프로파일을 현재 관측 페이스에 맞춤
    total = 0.0
    h = cur_h
    while h < 24:
        nxt = math.floor(h) + 1
        frac = min(nxt, 24) - h
        total += HOUR_PROFILE.get(int(h) % 24, 0.4) * frac
        h = nxt
    add = unit * total
    return {"cur": cur, "pred": round(cur + add),
            "low": round(cur + add * 0.8), "high": round(cur + add * 1.2),
            "r": round(r), "done": False}


def forecast_banner(fc):
    if not fc:
        return ('<div class="forecast"><div class="lbl">🔮 오늘 자정(23:59) 예상 예매관객수</div>'
                '<div class="sub2">데이터 수집 중 — 곧 예측이 표시됩니다.</div></div>')

    def r100(n):
        return int(round(n / 100.0) * 100)
    pred = r100(fc["pred"]); pure = pred - PROMO_TICKETS
    if fc.get("done"):
        head = f'마감 근접 · 현재 {fc["cur"]:,}명'
        rng = ""
    else:
        head = f'약 {pred:,}명 <span style="font-size:15px;color:#c7ccd6">(순수 ~{pure:,})</span>'
        rng = f'현재 {fc["cur"]:,} · 최근 +{fc["r"]:,}/h · 예상범위 {r100(fc["low"]):,}~{r100(fc["high"]):,}'
    return ('<div class="forecast">'
            '<div class="lbl">🔮 오늘 자정(23:59) 예상 예매관객수 · 30분마다 자동 갱신</div>'
            f'<div class="big">{head}</div>'
            f'<div class="sub2">{rng}</div></div>')


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


def box_leaderboard(open_date):
    """동시개봉작(같은 개봉일) 최신일 좌석판매율·회당관객 리더보드."""
    ph = ('<div class="panel" style="text-align:center;color:#9aa0ab;padding:32px 18px">'
          '🏆 동시개봉작 좌석판매율 리더보드 — 개봉 후(7/2 아침~) KOBIS 확정 집계가 나오면 표시됩니다.</div>')
    if not os.path.exists(BOXC_CSV):
        return ph
    with open(BOXC_CSV, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("날짜")]
    if not rows:
        return ph
    last = max(r["날짜"] for r in rows)
    day = [r for r in rows if r["날짜"] == last]
    # 그린랜드2와 같은 개봉일만 (없으면 전체)
    same = [r for r in day if (r.get("개봉일") or "").strip() == open_date] or day
    def sell(r):
        return _num(r.get("좌석판매율")) or -1
    same.sort(key=sell, reverse=True)
    trs = ""
    for r in same[:10]:
        g = GKEY in (r.get("영화명") or "")
        cls = ' style="color:#4ade80;font-weight:700"' if g else ""
        aud = _num(r.get("관객수")); shows = _num(r.get("상영횟수"))
        per = round(aud / shows) if aud and shows else None
        trs += (f"<tr{cls}><td>{'★ ' if g else ''}{r.get('영화명','')}</td>"
                f"<td>{r.get('좌석판매율') or '-'}</td><td>{fmt(per)}</td>"
                f"<td>{fmt(aud)}</td><td>{fmt(_num(r.get('스크린수')))}</td>"
                f"<td>{fmt(_num(r.get('누적관객수')))}</td></tr>")
    return (f'  <div class="panel"><h2>🏆 {last} 동시개봉작 경쟁력 (좌석판매율 순)</h2>'
            '<table><thead><tr><th>영화</th><th>좌석판매율</th><th>회당관객</th>'
            '<th>관객수</th><th>스크린</th><th>누적관객</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>'
            '<p style="color:#9aa0ab;font-size:12px;margin:10px 2px 0">좌석판매율=관객÷좌석(깔린 좌석이 얼마나 팔렸나=순수 수요강도), 회당관객=관객÷상영횟수. 개봉 후 경쟁력의 핵심 지표.</p></div>')


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
                if 0.25 <= gh <= 1.5:
                    out[i] = round((bk - prev) / gh)  # 시간당 환산
                    last = out[i]
            if bk is not None:
                prev, prevd = bk, d
        return out, last

    series = []
    for nm in top_names:
        incs, _ = inc_series(nm)
        series.append({"name": nm, "g": GKEY in nm,
                       "rates": [rate_by.get((nm, t)) for t in times], "incs": incs})
    # 비교 표용: '가장 최근 1시간 증가' + '오늘 시간당 평균'(오늘 증가 ÷ 경과시간) 부착
    def avg_today(nm):  # 09~22시 활동시간 시간당 평균
        return _win_avg([(dts[i], book_by.get((nm, t))) for i, t in enumerate(times)])
    for m in latest:
        incs_m, _ = inc_series(m["name"])
        m["inc"] = incs_m[-1] if incs_m else None
        m["avg"] = avg_today(m["name"])

    # 시간별 '증가량 순위' 계산 (그 시각 증가분이 큰 순 = 1위), 플롯 대상(series) 내에서
    n_t = len(times)
    for s in series:
        s["incRank"] = [None] * n_t
    for i in range(n_t):
        vals = [(j, series[j]["incs"][i]) for j in range(len(series))
                if series[j]["incs"][i] is not None]
        vals.sort(key=lambda x: x[1], reverse=True)
        for rank, (j, _) in enumerate(vals, start=1):
            series[j]["incRank"][i] = rank

    short = [t[5:16] for t in times]
    return {"latest": latest, "labels": short, "series": series, "open": target}


def comp_section(comp):
    if not comp["latest"]:
        return ('<div class="panel" style="text-align:center;color:#9aa0ab;padding:32px 18px">'
                '🥊 경쟁작 비교 — 매시간 동일 개봉작을 함께 수집합니다. 곧 표시됩니다.</div>')
    d = comp["open"] or "동일 개봉일"
    # 비교 표: 직전 1시간 증가량 내림차순 (증가분 없는 영화는 뒤로)
    def _ik(m):
        v = m.get("inc")
        return v if isinstance(v, (int, float)) else float("-inf")
    trs = ""
    for m in sorted(comp["latest"], key=_ik, reverse=True):
        star = "★ " if m["g"] else ""
        cls = ' style="color:#4ade80;font-weight:700"' if m["g"] else ""
        inc = m.get("inc")
        if isinstance(inc, (int, float)):
            inc_s = f"+{inc:,}" if inc >= 0 else f"{inc:,}"
        else:
            inc_s = "-"
        avg = m.get("avg")
        avg_s = f"{avg:,}/h" if isinstance(avg, (int, float)) else "-"
        rate = f'{m["rate"]}%' if m.get("rate") is not None else "-"
        trs += (f"<tr{cls}><td>{star}{m['name']}</td><td>{fmt(m['book'])}</td>"
                f"<td class='gain'>{inc_s}</td><td>{avg_s}</td><td>{rate}</td></tr>")
    table = (f'  <div class="panel"><h2>🥊 {d} 동시 개봉작 비교</h2>'
             '<table><thead><tr><th>영화</th><th>예매관객수</th><th>직전 1시간 ↑</th><th>시간당 평균(09~22)</th><th>예매율</th></tr></thead>'
             f'<tbody>{trs}</tbody></table>'
             '<p style="color:#9aa0ab;font-size:12px;margin:10px 2px 0">“직전 1시간 ↑”는 수집 2시간 이상 쌓여야 채워집니다. · '
             '“시간당 평균”은 경쟁작 공통 수집구간(오늘 시작분~) 기준이라, 위 그린랜드2 카드(자체 10시~ 집계)와 값이 다를 수 있어요.</p></div>')
    charts = (
        '  <div class="panel"><h2>예매율 추이 비교 (%)</h2><div class="cbox"><canvas id="c_comp_rate"></canvas></div>'
        '<p class="hint">동시 개봉작들의 예매율(=미래 수요 점유율) 흐름. 그린랜드2(굵은 초록)가 경쟁작 대비 올라가면 상대적 기세 ↑. 개봉 후 절대 증감은 상영소화로 출렁여 노이즈라 뺐고, 상대지표인 예매율/순위만 남겼어요.</p></div>')
    return table + "\n" + charts


def load_member():
    snaps = []
    if os.path.exists(MEMBER_SNAP):
        with open(MEMBER_SNAP, encoding="utf-8-sig", newline="") as f:
            snaps = [r for r in csv.DictReader(f) if r.get("수집시각")]
    detail = None
    if os.path.exists(MEMBER_DETAIL):
        try:
            detail = json.load(open(MEMBER_DETAIL, encoding="utf-8"))
        except Exception:
            detail = None
    return snaps, detail


def load_schedule():
    """오늘 편성을 반환. schedule.json은 낡을 수 있어 SCHED_HIST[오늘]을 우선 사용하고,
    date/bands(오전·오후·저녁)를 today 기준으로 합성해 모든 소비처가 항상 당일 기준이 되게 한다.
    오늘이 이력에 없으면(예: 아직 미수집) schedule.json으로 폴백."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    hist = _load_json(SCHED_HIST)
    e = hist.get(today) if isinstance(hist, dict) else None
    if e and e.get("total_seats"):
        hourly = e.get("hourly") or {}
        def band_sum(lo, hi):
            s = 0
            for k, v in hourly.items():
                try:
                    h = int(k)
                except (TypeError, ValueError):
                    continue
                if lo <= h < hi:
                    s += v or 0
            return s
        # 오전 6~11 / 오후 12~16 / 저녁 17~23(+심야 0~5는 저녁으로 합산)
        bands = {"오전": band_sum(6, 12), "오후": band_sum(12, 17),
                 "저녁": band_sum(17, 24) + band_sum(0, 6)}
        return {"date": today, "total_shows": e.get("total_shows"),
                "total_seats": e.get("total_seats"), "total_screens": e.get("total_screens"),
                "bands": bands, "chains": e.get("chains", {}),
                "hourly": hourly, "regions": e.get("regions", [])}
    if os.path.exists(SCHED_JSON):
        try:
            return json.load(open(SCHED_JSON, encoding="utf-8"))
        except Exception:
            return None
    return None


def predict_final(member_last, sched):
    """편성(시간대별 회차/좌석) + 현재 실관람 좌석소진율로 오늘 최종 실관람 추정."""
    if not member_last or not sched or not sched.get("total_seats"):
        return None
    b = sched.get("bands", {})
    tot_shows = sched.get("total_shows") or 0
    if tot_shows <= 0:
        return None
    # 관객수 측정 시점(엑셀 내린 시각) 기준으로 경과 회차 계산 (같은 날짜일 때만)
    ts = member_last.get("수집시각", "")
    if sched.get("date") and ts[:10] and sched["date"] != ts[:10]:
        return None
    try:
        dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        h = dt.hour + dt.minute / 60.0
    except ValueError:
        h = datetime.datetime.now().hour + 0.0

    def frac(band):
        if band == "오전":  # ~12:00 (상영 6시부터로 가정)
            return 1.0 if h >= 12 else max(0.0, (h - 6) / 6)
        if band == "오후":  # 12:01~17:00
            return 1.0 if h >= 17 else (0.0 if h < 12 else (h - 12) / 5)
        return 0.0 if h < 17 else min(1.0, (h - 17) / 7)  # 저녁 17:01~24:00

    elapsed_shows = sum(b.get(k, 0) * frac(k) for k in ("오전", "오후", "저녁"))
    if elapsed_shows <= 0:
        return None
    elapsed_seats = sched["total_seats"] * (elapsed_shows / tot_shows)
    if elapsed_seats < 500:
        return None
    aud = (_num(member_last.get("관객수")) or 0) + (_num(member_last.get("무료관객수")) or 0)
    occ = aud / elapsed_seats
    pred = aud + (sched["total_seats"] - elapsed_seats) * occ
    return {"pred": int(round(pred)), "aud": aud, "occ": occ,
            "elapsed": elapsed_shows / tot_shows, "seats": sched["total_seats"]}


def predict_banner(pred, sched):
    if not pred:
        return ""
    def r100(n):
        return int(round(n / 100.0) * 100)
    b = sched.get("bands", {})
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#3a2a0e 0%,#1a1d27 70%);border-color:#5a4a1a">'
            '<div class="lbl">🎯 편성 반영 오늘 예상 최종관객 (실관람)</div>'
            f'<div class="big" style="color:#f4c89a">약 {r100(pred["pred"]):,}명</div>'
            f'<div class="sub2">현재 실관람 {pred["aud"]:,} · 좌석소진율 {pred["occ"]*100:.1f}% · '
            f'편성 오전{b.get("오전",0)}/오후{b.get("오후",0)}/저녁{b.get("저녁",0)}회, 총 {pred["seats"]:,}석 반영 · '
            f'남은 편성이 현재 소진율만큼 찬다고 가정한 추정치</div></div>')


_REGION_POS = {
    "서울특별시": (126, 86, "서울"), "인천광역시": (92, 96, "인천"),
    "경기도": (150, 114, "경기"), "강원도": (216, 80, "강원"),
    "충청북도": (178, 146, "충북"), "세종특별자치시": (138, 158, "세종"),
    "대전광역시": (158, 176, "대전"), "충청남도": (104, 160, "충남"),
    "경상북도": (218, 150, "경북"), "대구광역시": (208, 182, "대구"),
    "울산광역시": (252, 198, "울산"), "부산광역시": (238, 220, "부산"),
    "경상남도": (192, 212, "경남"), "전라북도": (132, 196, "전북"),
    "광주광역시": (106, 232, "광주"), "전라남도": (122, 252, "전남"),
    "제주도": (110, 316, "제주"),
}


def region_map(regions):
    if not regions:
        return ""
    audmax = max((r[1] for r in regions), default=1) or 1

    def color(a):
        t = (a / audmax) ** 0.6
        c0, c1 = (0x33, 0x41, 0x55), (0xef, 0x44, 0x44)  # 적음(슬레이트)→많음(빨강)
        return "#%02x%02x%02x" % tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))

    body = ""
    for name, aud, seat, occ in regions:
        if name not in _REGION_POS:
            continue
        x, y, lbl = _REGION_POS[name]
        rad = 8 + (aud / audmax) ** 0.5 * 24
        body += (f'<circle cx="{x}" cy="{y}" r="{rad:.1f}" fill="{color(aud)}" fill-opacity="0.82" '
                 f'stroke="#0f1117" stroke-width="1"><title>{name} · 관객 {aud:,}</title></circle>'
                 f'<text x="{x}" y="{y-1}" text-anchor="middle" font-size="9" fill="#fff" font-weight="bold">{lbl}</text>'
                 f'<text x="{x}" y="{y+9}" text-anchor="middle" font-size="8" fill="#e7e9ee">{aud:,}</text>')
    svg = (f'<svg viewBox="0 0 300 340" style="width:100%;max-width:440px;display:block;margin:6px auto">{body}</svg>')
    return ('<div class="panel"><h2>🗺️ 지역별 관객 규모 지도</h2>' + svg +
            '<p class="hint">원 크기·색 = 관객수(<b style="color:#ef4444">빨강=많음</b>). 어디에서 많이 보는지 분포. '
            '(지역별 정확한 좌석점유율은 지역 좌석 데이터가 없어 생략 — 대체로 인구 규모를 따라갑니다.)</p></div>')


def secured_banner(pts, snaps):
    """기확보 관객. 주의: 누적관객수는 '오늘 예매분'을 이미 포함하므로 실시간예매와 단순 합산하면
    오늘분이 중복됨. 누적(오늘까지 확보)을 기준으로, 실시간예매 중 오늘과 겹치지 않는
    미래날짜분(≈ 실시간예매 − 오늘관객수)만 추가로 표기."""
    book = _num(latest(pts).get("book")) if pts else None       # 실시간 예매(오늘남은+미래)
    cumul = _num(snaps[-1].get("누적관객수")) if snaps else None  # 누적(과거실관람+오늘 예매포함)
    today = _num(snaps[-1].get("관객수")) if snaps else None      # 오늘(예매+발권)
    if not cumul:
        return ""
    future_extra = max(0, (book or 0) - (today or 0))  # 미래날짜 추가 예매(오늘과 중복 제외) 근사
    est = cumul + future_extra
    extra_txt = (f' + 미래날짜 예매 ≈ {future_extra:,}' if future_extra else '')
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#2a1e3a 0%,#1a1d27 70%);border-color:#4a3a5a">'
            '<div class="lbl">🎯 기확보 관객 (관람 + 예매, 오늘까지)</div>'
            f'<div class="big" style="color:#c084fc">{cumul:,}명'
            + (f' <span style="font-size:15px;color:#c7ccd6">(미래날짜까지 ≈ {est:,})</span>' if future_extra else '') + '</div>'
            f'<div class="sub2">누적관객수 {cumul:,} = 과거 실관람 + <b>오늘 예매·발권 포함</b>'
            f'{extra_txt}. '
            f'실시간 예매 {book:,}은 향후 상영분(오늘 남은+미래)인데 <b>오늘분은 누적에 이미 포함</b>돼 단순 합산 안 함.</div></div>'
            if book else
            '  <div class="forecast" style="background:linear-gradient(135deg,#2a1e3a 0%,#1a1d27 70%);border-color:#4a3a5a">'
            '<div class="lbl">🎯 기확보 관객 (관람 + 예매, 오늘까지)</div>'
            f'<div class="big" style="color:#c084fc">{cumul:,}명</div>'
            '<div class="sub2">누적관객수 = 과거 실관람 + 오늘 예매·발권 포함</div></div>')


def _hourly_norm(day_pts):
    """[(분, 관객)] → 정시(:00)로 선형보간한 {시:관객}과 시간당 증가 {시:그 시간대 증가}.
    수집이 잦거나 불규칙해도 08:00·09:00·10:00… 정시 값으로 후보정 → 요일 비교가 깔끔.
    관측 범위 안의 정시만 계산(범위 밖은 외삽 안 함)."""
    pts = sorted(day_pts)
    if len(pts) < 2:
        return {}, {}
    lo, hi = pts[0][0], pts[-1][0]
    hours = [h for h in range(24) if lo <= h * 60 <= hi]
    vals = {h: _interp(pts, h * 60) for h in hours}
    incs = {h: vals[h + 1] - vals[h] for h in hours if (h + 1) in vals}  # h시 = h:00→(h+1):00
    return vals, incs


def _incs_to(day_pts, now_m):
    """정시 경계 + 현재 진행시각(now_m)까지 시간당 증가 {시작시:증가}.
    마지막 시간대는 now_m까지 부분값(진행중) → '다음 정시 필요'로 인한 1시간 지연 제거. 외삽 안 함."""
    pts = sorted(day_pts)
    if len(pts) < 2:
        return {}
    lo, hi = pts[0][0], pts[-1][0]
    now_m = min(now_m, hi)
    bounds = [h * 60 for h in range(24) if lo <= h * 60 <= now_m]
    if not bounds:
        return {}
    if bounds[-1] < now_m:
        bounds.append(now_m)  # 진행 중인 현재 시각
    return {bounds[i - 1] // 60: _interp(pts, bounds[i]) - _interp(pts, bounds[i - 1])
            for i in range(1, len(bounds))}


def member_daycompare(snaps):
    """오늘 vs 어제 동시간대(정시) 관객 증가 비교 + 동시간 대비 예측(마감 관객).
    수집값을 정시로 후보정해서 요일끼리 딱 맞게 비교."""
    from collections import defaultdict
    days = defaultdict(list)
    for s in snaps:
        ts = s.get("수집시각", "")
        a = _num(s.get("관객수"))
        if len(ts) >= 16 and a is not None:
            days[ts[:10]].append((int(ts[11:13]) * 60 + int(ts[14:16]), a))
    if len(days) < 2:
        return None
    dts = sorted(days)
    today, yest = dts[-1], dts[-2]
    tv, yv = sorted(days[today]), sorted(days[yest])
    now_m, now_a = tv[-1]
    ti = _incs_to(days[today], now_m)   # 오늘: 진행 중 시각까지
    yi = _incs_to(days[yest], now_m)    # 어제: 같은 시각까지(동일 경계) → 공정 비교
    hours = sorted(set(ti) | set(yi))
    labels = [f"{h:02d}시" for h in hours]
    pred = None
    if yv[0][0] <= now_m <= yv[-1][0]:
        ya = _interp(yv, now_m)
        yfinal = yv[-1][1]
        if ya and ya > 0:
            ratio = now_a / ya
            pred = {"ratio": round(ratio, 3), "pred": int(round(yfinal * ratio)),
                    "now": now_a, "yestNow": int(round(ya)), "yestFinal": yfinal, "yest": yest}
    return {"labels": labels,
            "today": [int(round(ti[h])) if h in ti else None for h in hours],
            "yest": [int(round(yi[h])) if h in yi else None for h in hours],
            "todayDate": today, "yestDate": yest, "pred": pred}


def daycmp_banner(snaps):
    dc = member_daycompare(snaps)
    if not dc or not dc.get("pred"):
        return ""
    p = dc["pred"]
    pct = (p["ratio"] - 1) * 100
    updown = f'▲{pct:.0f}%' if pct >= 0 else f'▼{abs(pct):.0f}%'
    color = "#4ade80" if pct >= 0 else "#f87171"
    est = int(round(p["pred"] / 100.0) * 100)
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#1e3320 0%,#1a1d27 70%);border-color:#2f5a3a">'
            f'<div class="lbl">📊 어제 동시간 대비 · 오늘 예상 마감 ({p["yest"]} 패턴 기준)</div>'
            f'<div class="big" style="color:{color}">약 {est:,}명 <span style="font-size:15px">({updown})</span></div>'
            f'<div class="sub2">지금 {p["now"]:,} vs 어제 이 시각 {p["yestNow"]:,} = <b>{p["ratio"]:.2f}배</b> · '
            f'어제 최종 {p["yestFinal"]:,} × {p["ratio"]:.2f} = 예상 {est:,}. (관객수엔 예매 포함)</div></div>')


def _remaining_seats(sched, now_m):
    """시간표(hourly)로 현재시각 이후 아직 시작 안 한 회차의 좌석 합.
    sched = 해당 날짜 편성(hourly/total_seats/total_shows). 낡음 방지 위해 SCHED_HIST에서 조회."""
    if not sched:
        return None
    hourly = sched.get("hourly") or {}
    tot_shows = sched.get("total_shows") or 0
    tot_seats = sched.get("total_seats") or 0
    if not hourly or tot_shows <= 0 or tot_seats <= 0:
        return None
    now_h = now_m / 60.0
    remain_shows = sum(v for h, v in hourly.items() if int(h) >= now_h)
    return tot_seats * remain_shows / tot_shows


# 개봉 N일차 종료 시점의 '누적 관객 ÷ 최종 총관객' 통상 비율(중형 한국영화 앞쏠림). 매일 좁혀짐.
LIFETIME_FRAC = {1: 0.11, 2: 0.20, 3: 0.29, 4: 0.42, 5: 0.52, 6: 0.58, 7: 0.63}


AI_COMMENT = os.path.join(BASE, "ai_comment.json")


def _ai_cmt(field):
    """ai_comment.json의 섹션별 코멘트(weekend/decomp 등)를 패널에 붙일 div로."""
    d = _load_json(AI_COMMENT)
    if not d or not d.get(field):
        return ""
    return ('<div class="secdesc" style="border-left:3px solid #4a3a6a;padding-left:10px;'
            f'color:#e7e9ee;margin-top:6px">💬 {str(d[field]).replace(chr(10), "<br>")}'
            f' <span class="muted" style="font-size:11px">({d.get("updated","")})</span></div>')


def ai_comment_banner():
    """30분마다 갱신되는 서술형 코멘트(ai_comment.json). 폰에서 읽는 '의견'."""
    d = _load_json(AI_COMMENT)
    if not d or not d.get("text"):
        return ""
    txt = str(d["text"]).replace("\n", "<br>")
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#241a33 0%,#1a1d27 70%);border-color:#4a3a6a">'
            f'<div class="lbl">💬 코멘트 · {d.get("updated","")}</div>'
            f'<div style="font-size:14px;line-height:1.65;margin-top:6px;color:#e7e9ee">{txt}</div></div>')


def status_summary(snaps, sched):
    """폰에서 읽는 자동 '현황 한줄 요약' — 코멘트를 대시보드에 박아 넣음."""
    dc = member_daycompare(snaps)
    f = top_forecast(snaps, sched)
    if not f:
        return ""
    now = f["now"]
    est = int(round(f["est"] / 100.0) * 100)
    pred = (dc or {}).get("pred")
    ratio = pred["ratio"] if pred else None
    yfinal = pred["yestFinal"] if pred else None
    # 최근 완료 시간대 페이스(오늘 vs 어제)
    pace = ""
    if dc and dc.get("labels"):
        L, tA, yA = dc["labels"], dc["today"], dc["yest"]
        for i in range(len(L) - 1, -1, -1):
            if tA[i] is not None and yA[i] is not None and i + 1 < len(L):
                # 진행중(마지막) 제외, 직전 완료시간대
                pass
        comp = [(L[i], tA[i], yA[i]) for i in range(len(L))
                if tA[i] is not None and yA[i] is not None]
        if len(comp) >= 2:
            lab, t_, y_ = comp[-2]  # 마지막은 진행중 → 그 앞(완료된 것)
            pace = (f'{lab} 증가 {t_} vs 전일 {y_} — '
                    + ('<b style="color:#4ade80">전일보다 빠름(수요 살아있음)</b>' if t_ >= y_
                       else '<b style="color:#f4c89a">전일보다 느림</b>'))
    # 판정 문구
    if yfinal:
        rr = est / yfinal
        verdict = ("<b style='color:#4ade80'>전일 수준 유지</b>" if rr >= 0.95 else
                   "<b style='color:#f4c89a'>전일보다 소폭 낮음</b>" if rr >= 0.83 else
                   "<b style='color:#f87171'>전일 대비 부진</b>")
        vs = f'예상 마감 <b>~{est:,}</b> (전일 {int(yfinal):,}, {verdict})'
    else:
        vs = f'예상 마감 <b>~{est:,}</b>'
    rtxt = f' · 전일 동시각의 <b>{ratio:.2f}배</b>' if ratio else ""
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#10261f 0%,#1a1d27 70%);border-color:#2f5a4a">'
            f'<div class="lbl">📱 현황 한줄 요약 (자동)</div>'
            f'<div style="font-size:16px;font-weight:700;margin-top:4px;color:#e7e9ee">현재 {int(now):,}명{rtxt} · {vs}</div>'
            + (f'<div class="sub2">{pace}</div>' if pace else "") + '</div>')


def load_events():
    d = _load_json(EVENTS_JSON)
    return d.get("events", []) if isinstance(d, dict) else []


def future_event_boost(settled_date):
    """미정산 누적일(settled_date) 이후 예정된 이벤트만 집계.
    반환: (정량 부양 관객수 합, 미래 이벤트 목록). 아직 누적에 안 잡힌 것만 더함(중복 방지)."""
    evs = [e for e in load_events()
           if e.get("date") and (not settled_date or e["date"] > settled_date)]
    evs.sort(key=lambda e: e["date"])
    tickets = sum(int(e.get("tickets") or 0) for e in evs)
    return tickets, evs


def lifetime_forecast(cumul, completed_days):
    """개봉 최종 총관객 = 누적 ÷ (그 시점까지 통상 누적비율). 매우 이른 추정, 매일 정밀화.
    범위 = 비율 불확실성(레그=긴 꼬리→상단 / 페이드=이미 많이 소진→하단)."""
    f = LIFETIME_FRAC.get(completed_days)
    if not cumul or not f:
        return None
    r = lambda v: int(round(v / 1000.0) * 1000)
    return {"cumul": int(cumul), "days": completed_days, "frac": f,
            "mid": r(cumul / f), "low": r(cumul / (f * 1.3)), "high": r(cumul / (f * 0.8))}


def lifetime_banner(cumul, completed_days, settled_date=None):
    lf = lifetime_forecast(cumul, completed_days)
    if not lf:
        return ""
    boost, evs = future_event_boost(settled_date)
    # 유기적 전망 + 알려진 이벤트 정량 부양분(중복 방지: 미정산 미래 이벤트만)
    lo, mid, hi = lf["low"] + boost, lf["mid"] + boost, lf["high"] + boost
    evline = ""
    if evs:
        items = []
        for e in evs:
            tk = int(e.get("tickets") or 0)
            tag = f'+{tk/10000:.1f}만' if tk else '정성 부양'
            items.append(f'{e["date"][5:]} {e.get("label","")}({tag})')
        base = (f'유기적 ~{lf["mid"]/10000:.1f}만'
                + (f' + 확정 프로모 {boost:,}명 → <b style="color:#c084fc">조정 ~{mid/10000:.1f}만</b>' if boost else ''))
        evline = (f'<div class="sub2" style="margin-top:6px;color:#c7ccd6">📌 반영 이벤트: '
                  + ' · '.join(items) + f'<br>{base} '
                  + ('(0원 티켓은 상당수 증분 가정, 일부 견인효과 포함)' if boost else '') + '</div>')
    d = _load_json(AI_COMMENT)
    cmt = ""
    if d and d.get("lifetime"):
        cmt = (f'<div class="sub2" style="margin-top:8px;line-height:1.6;color:#e7e9ee">'
               f'{str(d["lifetime"]).replace(chr(10), "<br>")}</div>')
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#2a1e3a 0%,#1a1d27 70%);border-color:#4a2f5a">'
            '<div class="lbl">🎬 개봉 최종 총관객 예상 (전체 스코어) · <b style="color:#c084fc">매우 이른 추정</b></div>'
            f'<div class="big" style="color:#c084fc">약 {lo/10000:.0f}만~{hi/10000:.0f}만명 <span style="font-size:14px;color:#9aa0ab">(중앙 ~{mid/10000:.1f}만)</span></div>'
            f'<div class="sub2">누적 {lf["cumul"]:,}명({lf["days"]}일차 종료 기준) ÷ 통상 누적비율 {lf["frac"]*100:.0f}%. '
            '주말·2주차 실적 쌓이면 매일 좁혀짐.</div>' + evline + cmt + '</div>')


def _hoi_factor(today, yest, now_m):
    """오늘 남은 회차 vs 전일 남은 회차 → 잔여 증가분 편성 보정계수(선제적).
    회차가 전일보다 적으면 잔여 증가분을 미리 깎음. 단 저 fill이라 완전 비례는 아니어서
    √ 댐핑(회차 반토막→계수 0.71). 회차 0이면 잔여도 0."""
    sh = _load_json(SCHED_HIST)
    th = (sh.get(today) or {}).get("hourly") or {}
    yh = (sh.get(yest) or {}).get("hourly") or {}
    if not th or not yh:
        return 1.0
    now_h = now_m / 60.0
    trem = sum(v for h, v in th.items() if int(h) >= now_h)
    yrem = sum(v for h, v in yh.items() if int(h) >= now_h)
    if yrem <= 0:
        return 1.0
    return max(0.15, min(1.2, (trem / yrem) ** 0.5))


def top_forecast(snaps, sched=None):
    """오늘 최종 관객 예상(맨 위 히어로). 신뢰도 3단:
    ① 어제 동시간 보정(daycmp) + ② 당일 곡선(predict_eod_curve) → 되면 평균(정밀)
    ③ 둘 다 안되면 당일 추세 슬로프로 마감 시각(23:30)까지 외삽(잠정).
    + 남은 회차 편성 보정(오늘 남은회차 vs 전일) + '현재 + 남은좌석' 물리 상한 캡."""
    from collections import defaultdict
    days = defaultdict(list)
    for s in snaps:
        ts = s.get("수집시각", "")
        a = _num(s.get("관객수"))
        if len(ts) >= 16 and a is not None:
            days[ts[:10]].append((int(ts[11:13]) * 60 + int(ts[14:16]), a))
    if not days:
        return None
    dts = sorted(days)
    today = dts[-1]
    yest = dts[-2] if len(dts) >= 2 else None
    tv = sorted(days[today])
    now_m, now_a = tv[-1]

    # 오늘 편성은 SCHED_HIST에서(schedule.json은 낡을 수 있음). 남은 회차 좌석 × 현실 최대판매율로 상한.
    # 저 fill이면 남은 좌석이 넉넉해 상한이 안 걸림(수요를 따라감). 편성이 정말 얇을 때만 제한.
    today_sched = _load_json(SCHED_HIST).get(today) if today else None
    remain = _remaining_seats(today_sched, now_m)
    MAX_FILL = 0.6  # 남은 회차가 도달 가능한 현실적 최대 좌석판매율
    cap = (now_a + remain * MAX_FILL) if remain is not None else None
    hoi = _hoi_factor(today, yest, now_m) if yest else None  # 참고용(남은 회차 오늘/전일 비)

    def fin(v):  # 물리적 용량 상한만 적용(일괄 할인 없음 → 실제 수요를 따라감)
        return min(v, cap) if cap is not None else v

    dc = member_daycompare(snaps)
    ratio_est = dc["pred"]["pred"] if dc and dc.get("pred") else None
    cv = predict_eod_curve(snaps)
    curve_est = cv["pred"] if cv else None
    ests = [(e, lbl) for e, lbl in ((ratio_est, "어제 동시간 보정"), (curve_est, "당일 곡선 보정")) if e]

    END = 23 * 60 + 30  # 마감 기준 시각(관객수 확정이 대체로 이 무렵)
    base = {"now": now_a, "cap": (int(round(cap)) if cap is not None else None),
            "remain": (int(round(remain)) if remain is not None else None),
            "hoi": round(hoi, 2)}
    if ests:
        vals = [e for e, _ in ests]
        est = sum(vals) / len(vals)
        return {**base, "est": fin(est), "low": fin(min(vals)), "high": fin(max(vals)),
                "method": " + ".join(l for _, l in ests), "conf": "정밀",
                "capped": fin(est) < est, "detail": [(l, e) for e, l in ests]}
    # 잠정: 최근 구간 기울기로 마감까지 외삽
    if now_m >= END or len(tv) < 3:
        return {**base, "est": now_a, "low": now_a, "high": now_a,
                "method": "현재 확정치", "conf": "floor", "capped": False}
    recent = tv[-6:]
    span = recent[-1][0] - recent[0][0]
    slope = (recent[-1][1] - recent[0][1]) / span if span > 0 else 0
    # 저녁엔 예매·발권 속도가 둔화(어제 저녁 관측) → 남은 증가분에 감속계수 0.7
    raw = now_a + max(0, slope) * (END - now_m) * 0.7
    est = fin(raw)
    return {**base, "est": est, "low": fin(raw * 0.85), "high": fin(raw * 1.15),
            "method": "당일 추세 외삽", "conf": "잠정", "capped": est < raw}


def top_forecast_banner(snaps, sched=None):
    f = top_forecast(snaps, sched)
    if not f:
        return ""
    r = lambda v: int(round(v / 100.0) * 100)
    est, lo, hi = r(f["est"]), r(f["low"]), r(f["high"])
    capnote = ""
    if f.get("remain") is not None:
        capnote = f' · 남은 좌석 여유 {int(f["remain"]*0.6):,}석'
        if f.get("capped"):
            capnote += ' <b style="color:#fbbf24">← 편성 좌석 상한 적용(예측 제한)</b>'
        else:
            capnote += ' <span class="muted">(좌석 넉넉 → 수요 따라감)</span>'
    hoi = f.get("hoi")
    if hoi is not None and hoi < 0.92:
        capnote += (' · <span style="color:#9aa0ab">🎬 오늘 남은 회차가 전일보다 적음 — '
                    '단 좌석 여유 커서 예측은 실제 수요를 따라감(회차 적어도 꽉 차면 예측 오름)</span>')
    # 편성 기반 참고치: 오늘 좌석 × (직전 완료일 판매율, 요일 보정)
    schedref = ""
    if sched and sched.get("total_seats") and sched.get("date"):
        fb = _fill_baseline(sched["date"])
        if fb:
            wf = fb["fill"] / DOW_FILL[fb["dow"]][1]
            dw = _dow(sched["date"])
            ref = int(round(sched["total_seats"] * wf * DOW_FILL[dw][1] / 100.0) * 100)
            schedref = (f'<div style="font-size:11px;color:#c7ccd6;margin-top:4px">📐 편성 기반 참고: '
                        f'좌석 {sched["total_seats"]:,} × 판매율 {wf*DOW_FILL[dw][1]*100:.1f}% ≈ '
                        f'<b>{ref:,}명</b> (직전 {fb["date"][5:]} {fb["fill"]*100:.1f}% 기준). '
                        f'오늘 헤드라인은 실시간 누적이 더 정확해 그 값을 사용.</div>')
    if f["conf"] == "floor":
        return ('  <div class="forecast" style="background:linear-gradient(135deg,#2a2410 0%,#1a1d27 70%);border-color:#5a4a2f">'
                '<div class="lbl">🎯 오늘 최종 관객 예상</div>'
                f'<div class="big" style="color:#fbbf24">확정 {f["now"]:,}명</div>'
                '<div class="sub2">마감 시각이라 추가 예측 없음 · 오늘 확정 관객수.</div></div>')
    if f["conf"] == "정밀":
        dt = " · ".join(f"{l} {r(e):,}" for l, e in f["detail"])
        band = f"{lo:,}~{hi:,}명 범위" if lo != hi else ""
        return ('  <div class="forecast" style="background:linear-gradient(135deg,#10261a 0%,#1a1d27 65%);border-color:#2f5a42">'
                '<div class="lbl">🎯 오늘 최종 관객 예상 · 어제 추이 보정 (정밀)</div>'
                f'<div class="big" style="color:#4ade80">약 {est:,}명</div>'
                f'<div class="sub2">현재 확정 {f["now"]:,} → {dt}. {band}{capnote} '
                '(관객수엔 예매·발권 포함 — 여기에 남은 현매/당일예매가 더해진 최종 추정)</div>'
                + schedref + '</div>')
    # 잠정
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#1e2a3a 0%,#1a1d27 70%);border-color:#2f4a5a">'
            '<div class="lbl">🎯 오늘 최종 관객 예상 · 당일 추세 (잠정)</div>'
            f'<div class="big" style="color:#60a5fa">약 {est:,}명 <span style="font-size:14px;color:#9aa0ab">({lo:,}~{hi:,})</span></div>'
            f'<div class="sub2">현재 확정 {f["now"]:,} → 지금 증가 속도를 밤(23:30)까지 이어 붙인 <b>잠정치</b>{capnote}. '
            '<b style="color:#7dd3fc">어제 동시간 데이터가 겹치는 저녁부터 "정밀 예측"으로 자동 승급</b>. (관객수엔 예매 포함)</div>'
            + schedref + '</div>')


def _member_peak(snaps):
    """오늘 시간대별 관객 증가(정시 후보정). h시 = h:00→(h+1):00 증가분. 마지막 날짜 기준."""
    if not snaps:
        return []
    today = max(s.get("수집시각", "")[:10] for s in snaps)
    pts = sorted((int(s["수집시각"][11:13]) * 60 + int(s["수집시각"][14:16]), _num(s.get("관객수")))
                 for s in snaps if s.get("수집시각", "")[:10] == today and _num(s.get("관객수")) is not None)
    if len(pts) < 2:
        return []
    incs = _incs_to(pts, pts[-1][0])  # 진행 중 시간대까지 포함(지연 제거)
    return [[f"{h:02d}시", int(round(incs[h]))] for h in sorted(incs)]


def _interp(curve, x):
    """(x,y) 정렬 리스트에서 x 위치 선형보간."""
    if not curve:
        return None
    if x <= curve[0][0]:
        return curve[0][1]
    if x >= curve[-1][0]:
        return curve[-1][1]
    for i in range(1, len(curve)):
        x0, y0 = curve[i - 1]
        x1, y1 = curve[i]
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y0
    return curve[-1][1]


def predict_eod_curve(snaps):
    """당일 누적 곡선(이전 완료일들의 시간대별 도달률)으로 오늘 마감 관객 추정.
    이전 완료일(저녁 21시 이후 데이터 있는 날)이 최소 1개 있어야 작동 → 7/2부터 자동 켜짐."""
    from collections import defaultdict
    days = defaultdict(list)
    for s in snaps:
        ts = s.get("수집시각", "")
        a = _num(s.get("관객수"))
        if len(ts) >= 16 and a is not None:
            days[ts[:10]].append((int(ts[11:13]) * 60 + int(ts[14:16]), a))
    if not days:
        return None
    today = max(days)
    # '온전한 하루' = 아침(<=10시)부터 저녁(>=21시)까지 커버된 이전 날만 곡선에 사용
    prior = {d: v for d, v in days.items()
             if d < today and min(m for m, _ in v) <= 10 * 60 and max(m for m, _ in v) >= 21 * 60}
    if not prior:
        return None
    frac_pts = defaultdict(list)
    for d, v in prior.items():
        v = sorted(v)
        final = v[-1][1]
        if final > 0:
            for m, a in v:
                frac_pts[m // 30 * 30].append(a / final)
    curve = sorted((mb, sum(fs) / len(fs)) for mb, fs in frac_pts.items())
    tv = sorted(days[today])
    now_m, now_a = tv[-1]
    # 곡선 범위(아침 시작~) 안일 때만 예측. 곡선 시작 전 시각은 외삽 금지.
    if not curve or now_m < curve[0][0] or not now_a:
        return None
    frac = _interp(curve, now_m)
    if not frac or frac < 0.15:
        return None
    frac = min(frac, 1.0)
    return {"pred": int(round(now_a / frac)), "now": now_a, "frac": frac, "ndays": len(prior)}


def eod_banner(snaps):
    fc = predict_eod_curve(snaps)
    if not fc:
        return ""
    p = int(round(fc["pred"] / 100.0) * 100)
    tag = " (잠정, 1일 곡선)" if fc["ndays"] < 2 else f" (최근 {fc['ndays']}일 곡선)"
    return ('  <div class="forecast" style="background:linear-gradient(135deg,#1e2a3a 0%,#1a1d27 70%);border-color:#2f4a5a">'
            '<div class="lbl">🔮 오늘 예상 최종 관객 · 당일 곡선 기반' + tag + '</div>'
            f'<div class="big" style="color:#60a5fa">약 {p:,}명</div>'
            f'<div class="sub2">현재 확정 {fc["now"]:,} · 오늘 진행률 {fc["frac"]*100:.0f}% (이 시간대엔 보통 최종의 {fc["frac"]*100:.0f}%까지 참)</div></div>')


FUTURE_ADV = os.path.join(BASE, "future_advance_log.json")
CAP_LOG = os.path.join(BASE, "schedule_capacity_log.json")
DOW_NAME = ["월", "화", "수", "목", "금", "토", "일"]
# 요일별 좌석판매율 배수(평일 월~목=1.0 기준). 첫 주말 실적 나오면 자동 보정.
DOW_FILL = {0: (0.85, 1.0, 1.1), 1: (0.85, 1.0, 1.1), 2: (0.9, 1.0, 1.1),
            3: (0.9, 1.0, 1.1), 4: (1.0, 1.15, 1.35), 5: (1.25, 1.55, 1.9),
            6: (1.1, 1.4, 1.7)}
# 주말 최종 좌석(개방 완료 가정) ≈ 평일 대비 — 주말 좌석은 임박해 열려 지금 과소
WEEKEND_CAP = {4: 0.95, 5: 1.05, 6: 0.95}


def _dow(date_str):
    y, m, d = map(int, date_str.split("-"))
    return datetime.date(y, m, d).weekday()


def _fill_baseline(current_day):
    """직전 완료일의 좌석판매율(수요 강도) — 예측 앵커. 박스오피스 확정치 사용."""
    box = load_box()
    comp = {r["날짜"]: r for r in box if r.get("날짜") and r["날짜"] < current_day
            and _num(r.get("좌석판매율"))}
    if not comp:
        return None
    d = max(comp)
    return {"date": d, "dow": _dow(d), "fill": _num(comp[d]["좌석판매율"]) / 100.0,
            "aud": _num(comp[d].get("관객수"))}


def weekend_scenario(current_day):
    """향후 날짜 예상 = 편성 좌석 × 좌석판매율(요일 보정). 편성(좌석)이 스케일,
    판매율(과거 실적)이 수요강도. 선예매는 하한. 주말 좌석은 개방 진행중이라 상향 여지."""
    sched_hist = _load_json(SCHED_HIST)
    adv = _load_json(FUTURE_ADV)
    fb = _fill_baseline(current_day)
    if not fb or not sched_hist:
        return ""
    weekday_fill = fb["fill"] / DOW_FILL[fb["dow"]][1]  # 평일 환산 판매율
    wk_ref = (sched_hist.get(current_day) or {}).get("total_seats") or max(
        (v.get("total_seats") or 0) for v in sched_hist.values())

    fut = [d for d in sorted(sched_hist) if d > current_day]
    if not fut:
        return ""
    r = lambda v: int(round(v / 100.0) * 100)
    cards = []
    for d in fut[:4]:
        dw = _dow(d)
        seats_now = (sched_hist.get(d) or {}).get("total_seats") or 0
        # 주말은 좌석 개방 진행중 → 최종좌석을 평일 규모로 투영(하한은 현재 좌석)
        seats_proj = max(seats_now, int(wk_ref * WEEKEND_CAP.get(dw, 1.0))) if dw >= 4 else seats_now
        flo, fmid, fhi = DOW_FILL[dw]
        low = seats_now * weekday_fill * flo          # 보수: 현재 개방 좌석
        mid = seats_proj * weekday_fill * fmid        # 좌석 평일수준 개방 가정
        high = seats_proj * weekday_fill * fhi
        a_latest = adv[d][max(adv[d])].get("aud") if adv.get(d) else None
        if a_latest:
            low = max(low, a_latest)                   # 선예매 하한
            mid = max(mid, a_latest)
        opennote = ""
        under = dw in (5, 6) and wk_ref and seats_now < 0.75 * wk_ref
        if under:
            opennote = (f' · <b style="color:#7dd3fc">🔓 개방 진행중</b>'
                        f'(현재 {seats_now:,}석=평일 {seats_now/wk_ref*100:.0f}%, 최종 ~{seats_proj:,} 가정)')
        wend = dw >= 4
        adv_txt = f'선예매 {a_latest:,}' if a_latest else '선예매 -'
        cards.append(
            f'<div class="card" style="border-color:{"#3a4a2f" if wend else "#262a36"}">'
            f'<div class="k">{d[5:]} ({DOW_NAME[dw]}){" ⭐주말" if wend else ""}</div>'
            f'<div class="v" style="font-size:19px;color:{"#4ade80" if wend else "#e7e9ee"}">약 {r(mid):,}명</div>'
            f'<div style="font-size:11px;color:#9aa0ab;margin-top:4px">범위 {r(low):,}~{r(high):,} · {adv_txt}</div>'
            f'<div style="font-size:11px;color:#c7ccd6;margin-top:2px">좌석 {seats_now:,}{opennote}</div></div>')
    note = (f'<b>편성 좌석 × 좌석판매율</b> 방식. 판매율 기준 = 직전 완료일 '
            f'<b>{fb["date"][5:]}({DOW_NAME[fb["dow"]]}) {fb["fill"]*100:.1f}%</b>'
            f'(관객 {fb["aud"]:,}÷좌석), 평일환산 {weekday_fill*100:.1f}%에 요일 판매율배수(금×1.15·토×1.55·일×1.4)를 곱함. '
            '<b style="color:#f4c89a">최종 = 좌석(스케일) × 판매율(수요)</b> — 편성이 중심, 과거 실적이 판매율을 보정. '
            '<b style="color:#7dd3fc">주말 좌석은 임박해 열려 지금 과소</b>라 최종좌석을 평일수준으로 투영(범위 하단=현재좌석·상단=평일좌석). '
            '선예매는 하한. 완료일·주말 실적 쌓이면 판매율·좌석투영 자동 정밀화.')
    return ('  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#4ade80;font-size:14px;font-weight:600">— 🔮 향후·주말 예상 (편성 좌석 × 판매율) —</div>\n'
            f'  <div class="cards">{"".join(cards)}</div>\n'
            f'  <div class="secdesc" style="margin-top:2px">{note}</div>\n  ' + _ai_cmt("weekend"))


def defense_calculator(comp_rows):
    """예매율 방어 계산기: 0원 티켓 N장 추정.
    예매율 순위 ≡ 예매관객수 순위 → 경쟁작 넘는 N = 예매관객 gap.
    절대 예매율 s% 목표 → N=(s·G−b)/(1−s). (전국 실시간 기준·근사)"""
    if not comp_rows:
        return ""
    times = sorted({r["수집시각"] for r in comp_rows})
    last = times[-1]
    snap = [r for r in comp_rows if r["수집시각"] == last]
    for r in snap:
        r["_b"] = _num(r.get("예매관객수"))
        r["_r"] = _num(r.get("예매율"))
    snap = [r for r in snap if r["_b"] is not None]
    snap.sort(key=lambda r: r["_b"], reverse=True)
    us = next((r for r in snap if GKEY in r.get("영화명", "")), None)
    if not us or not us["_b"]:
        return ""
    b = us["_b"]
    r_us = us["_r"] or 0
    G = b / (r_us / 100) if r_us else sum(x["_b"] for x in snap)
    rank = snap.index(us) + 1
    # 우리보다 위(넘을 대상) — 예매관객 가까운 순 4편
    above = sorted((r for r in snap if r["_b"] > b), key=lambda r: r["_b"])[:4]
    rows_html = ""
    for r in above:
        n = int(r["_b"] - b)
        rows_html += (f'<tr><td style="text-align:left">{r.get("영화명","")[:16]}</td>'
                      f'<td>{r["_r"]:.1f}%</td><td>{int(r["_b"]):,}</td>'
                      f'<td class="gain"><b>+{n:,}장</b></td></tr>')
    # 절대 예매율 목표
    thr_html = ""
    base_pct = int(r_us) + 1
    for s_pct in range(base_pct, base_pct + 4):
        s = s_pct / 100.0
        N = (s * G - b) / (1 - s)
        if N > 0:
            thr_html += (f'<tr><td style="text-align:left">예매율 {s_pct}%</td>'
                         f'<td>-</td><td>-</td><td class="gain"><b>+{int(round(N/10)*10):,}장</b></td></tr>')
    return (
        '  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#f4c89a;font-size:14px;font-weight:600">— 🎯 예매율 방어 계산기 (0원 티켓 N장) —</div>\n'
        f'  <div class="secdesc">현재 <b>예매율 {r_us:.1f}% · 전국 {rank}위 · 예매관객 {int(b):,}</b> (전체 예매 ~{int(round(G/1000)):,}천). '
        '예매율 순위 = 예매관객수 순위라, 경쟁작 넘는 데 필요한 0원 티켓 = <b>예매관객 차이</b>.</div>\n'
        '  <div class="panel"><table><thead><tr><th>목표</th><th>예매율</th><th>예매관객</th><th>필요 N(지금)</th></tr></thead><tbody>'
        + rows_html + '<tr><td colspan="4" style="border-top:2px solid #3b4252;padding-top:8px;color:#9aa0ab;font-size:12px">▼ 절대 예매율 목표(극장 기준선)</td></tr>'
        + thr_html + '</tbody></table>'
        '<p class="hint">⚠️ <b>전국 실시간 근사치</b>예요. ①실시간 총 예매관객은 날짜가 섞이고 오후엔 당일소진으로 빠짐 → 2주차 방어는 '
        '<b>"그 날 상영분 예매율"</b>이 진짜 타깃(경쟁작 날짜별 예매 스크랩 필요). ②각 앱(CGV·롯데·메가) 순위는 체인별이라 별도 확인 권장. '
        '③경쟁작도 늘어나니 <b>여유 20~30%</b> 얹기. ④0원→노출→<b>유기 예매 전환</b>은 소규모 실험으로 측정해야 확정(가설 검증).</p></div>')


NOVA_JSON = os.path.join(BASE, "nova_competitors.json")


def nova_section():
    """노바 경쟁작 편성 비교(좌석/스크린/회차, 기준일→대상일). 우리 위치·점유율·증감."""
    d = _load_json(NOVA_JSON)
    if not d or not d.get("films"):
        return ""
    b, t = d.get("baseline", ""), d.get("target", "")
    dw = lambda s: DOW_NAME[_dow(s)] if s else ""
    films = sorted(d["films"], key=lambda f: -(f.get("seats") or [0, 0])[1])
    tot_t = sum((f.get("seats") or [0, 0])[1] for f in films) or 1
    rows = ""
    us_rank = None
    for i, f in enumerate(films):
        s = f.get("seats") or [0, 0]; sc = f.get("screens") or [0, 0]; sh = f.get("shows") or [0, 0]
        chg = (s[1] / s[0] - 1) * 100 if s[0] else 0
        share = s[1] / tot_t * 100
        us = GKEY in f["name"]
        if us:
            us_rank = i + 1
        col = "#4ade80" if chg >= 0 else "#f87171"
        rows += (f'<tr style="{"background:#12261a" if us else ""}">'
                 f'<td style="text-align:left">{i+1}. {"★ " if us else ""}{f["name"][:15]}</td>'
                 f'<td>{s[1]:,}</td><td style="color:{col}">{chg:+.0f}%</td><td>{share:.1f}%</td>'
                 f'<td class="muted">{sc[1]}</td><td class="muted">{sh[1]}</td></tr>')
    # 인사이트: 우리 vs 도라에몽(가족영화 벤치마크)
    def chg_of(key):
        for f in films:
            if key in f["name"]:
                s = f.get("seats") or [0, 0]
                return (s[1] / s[0] - 1) * 100 if s[0] else 0
        return None
    us_chg, dora = chg_of(GKEY), chg_of("도라에몽")
    note = (f'<b>{b[5:]}({dw(b)}) → {t[5:]}({dw(t)})</b> 배급사별 편성 변화. 열 = 대상일 좌석·증감·점유율·스크린·회차. '
            f'우리 <b style="color:{"#4ade80" if (us_chg or 0)>=0 else "#f87171"}">좌석 {us_chg:+.0f}%</b>(전국 {us_rank}위). ' if us_chg is not None else "")
    if us_chg is not None and dora is not None:
        note += (f'<b style="color:#f4c89a">참고:</b> 같은 가족영화 <b>도라에몽 {dora:+.0f}%</b>(주말 증편) vs 우리 {us_chg:+.0f}% — '
                 '스크린은 유지되고 좌석·회차만 깎였으면 <b>회차 추가 요청</b>이 현실적 레버.')
    return ('  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#f59e0b;font-size:14px;font-weight:600">— 🎬 경쟁작 편성 비교 (노바 자료) —</div>\n'
            f'  <div class="secdesc">{note}</div>\n'
            '  <div class="panel"><table><thead><tr><th>순위·영화</th><th>좌석(대상일)</th><th>증감</th><th>점유율</th><th>스크린</th><th>회차</th></tr></thead><tbody>'
            + rows + '</tbody></table>'
            f'<p class="hint">노바엔터 제공 · {d.get("updated","")} 기준. 매일 파일 넣으면 갱신. '
            '탑작(토이·눈동자)이 주말에 +50%↑ 늘며 미드작 물량을 흡수 — 우리가 축소되면 여기서 바로 보임.</p></div>')


def theater_ranking(top_n=20):
    """MEMBER_HIST 일자별 극장 top50를 누적 → 극장별 누적 관객·회차·출현일수 랭킹.
    회원 상위 극장 기준이라 하위 극장은 일부 누락될 수 있으나 상위권은 안정적."""
    mh = _load_json(MEMBER_HIST)
    if not mh:
        return None
    agg = {}
    for dt in sorted(mh):
        for row in (mh[dt].get("theaters") or []):
            if not row:
                continue
            nm = str(row[0]).strip()
            aud = _num(row[1]) or 0
            shows = (_num(row[2]) if len(row) > 2 else 0) or 0
            a = agg.setdefault(nm, {"aud": 0, "shows": 0, "days": 0, "last": 0})
            a["aud"] += aud
            a["shows"] += shows
            a["days"] += 1
            a["last"] = aud
    ranked = sorted(agg.items(), key=lambda x: -x[1]["aud"])
    return ranked[:top_n], len(agg)


def _chain_color(nm):
    if "CGV" in nm:
        return "#e11d48", "CGV"
    if "롯데" in nm:
        return "#f59e0b", "롯데"
    if "메가" in nm:
        return "#6366f1", "메가"
    return "#9aa0ab", "기타"


def theater_ranking_section():
    r = theater_ranking()
    if not r:
        return ""
    ranked, total = r
    rows = ""
    for i, (nm, v) in enumerate(ranked):
        col, ch = _chain_color(nm)
        per = v["aud"] / v["shows"] if v["shows"] else 0
        rows += (f'<tr><td style="text-align:left"><span style="color:{col};font-weight:700">{i+1}</span> '
                 f'<span style="color:{col};font-size:10px">●</span> {nm[:16]}</td>'
                 f'<td><b>{int(v["aud"]):,}</b></td><td class="muted">{int(v["shows"]):,}</td>'
                 f'<td>{per:.1f}</td><td class="muted">{v["days"]}일</td></tr>')
    return ('  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#34d399;font-size:14px;font-weight:600">— 🏆 극장별 누적 관객 순위 (회원 기준) —</div>\n'
            '  <div class="secdesc">개봉일부터 <b>일자별 회원 관객을 극장별로 누적</b>한 순위입니다. 단일 시점 스냅샷의 노이즈를 제거해 <b>실제로 잘 드는 지점</b>을 보여줘요. '
            '<b>회당</b>=누적관객÷누적회차(높을수록 회차를 꽉 채우는 지점). 편성 협상·프로모 지점 선정의 근거로 쓰세요.</div>\n'
            '  <div class="panel"><table><thead><tr><th>순위·극장</th><th>누적 관객</th><th>누적 회차</th><th>회당</th><th>집계</th></tr></thead><tbody>'
            + rows + '</tbody></table>'
            f'<p class="hint">회원 통계 상위 극장 기준(일자별 top50 누적, 전체 {total}개 극장). '
            '회원 관객은 전체의 일부라 절대치보다 <b>상대 순위</b>로 보세요. 매 갱신마다 누적됩니다.</p></div>')


def build_decomp():
    """신규 예매 수요 분해: 회원 오늘관객 증분(A=신규, 소진無) vs 실시간예매관객 순증(dP=신규−소진).
    A가 강한데 dP가 하락 = 소진이 큰데 신규가 계속 유입(좋은 신호). 경쟁작은 순증(net)만."""
    from collections import defaultdict
    snaps, _ = load_member()
    days = defaultdict(list)
    for s in snaps:
        ts = s.get("수집시각", ""); a = _num(s.get("관객수"))
        if len(ts) >= 16 and a is not None:
            days[ts[:10]].append((int(ts[11:13]) * 60 + int(ts[14:16]), a))
    memA = {d: _hourly_norm(v)[1] for d, v in days.items()}  # {date:{hour:증분}}

    def hourly_P(path, movie_key=None):
        out = defaultdict(dict)
        if not os.path.exists(path):
            return out
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                ts = r.get("수집시각", "")
                if len(ts) < 16 or ts[14:16] != "00":
                    continue
                if movie_key and movie_key not in r.get("영화명", ""):
                    continue
                p = _num(r.get("예매관객수"))
                if p is not None:
                    out[ts[:10]][int(ts[11:13])] = p
        return out

    rtP = hourly_P(os.path.join(BASE, "greenland2_hourly.csv"))

    def dP(d):
        h = rtP.get(d, {})
        return {k: h[k + 1] - h[k] for k in h if (k + 1) in h}

    dates = sorted(set(memA) | set(rtP))
    today = dates[-1] if dates else None
    yest = dates[-2] if len(dates) >= 2 else None

    def series(d):
        if not d:
            return None
        A = memA.get(d, {}); dp = dP(d)
        hrs = sorted(set(A) | set(dp))
        return {"labels": [f"{h:02d}시" for h in hrs],
                "A": [int(round(A[h])) if h in A else None for h in hrs],
                "dP": [int(round(dp[h])) if h in dp else None for h in hrs]}

    # 경쟁작 시간당 순증(net, 오늘) — 상위 6편
    comp = defaultdict(dict)
    cp = os.path.join(BASE, "competitors_hourly.csv")
    if os.path.exists(cp):
        with open(cp, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                ts = r.get("수집시각", "")
                if len(ts) >= 16 and ts[14:16] == "00" and ts[:10] == today:
                    p = _num(r.get("예매관객수"))
                    if p is not None:
                        comp[r.get("영화명", "")][int(ts[11:13])] = p
    compnet = []
    for nm, h in comp.items():
        dp = {k: h[k + 1] - h[k] for k in h if (k + 1) in h}
        if dp:
            hrs = sorted(dp)
            compnet.append({"name": nm, "g": GKEY in nm,
                            "labels": [f"{x:02d}시" for x in hrs],
                            "net": [int(round(dp[x])) for x in hrs],
                            "last": dp[max(hrs)]})
    compnet.sort(key=lambda x: (not x["g"], -x["last"]))
    return {"today": series(today), "todayDate": today,
            "yest": series(yest), "yestDate": yest, "comp": compnet[:6]}


def manual_defense(detail):
    """수동 입력 체인별 예매율 방어 계산기(인터랙티브).
    한 체인 안에서 N = 우리예매관객 × (모아나율/우리율 − 1). 앱에서 본 예매율 입력."""
    anchor = {"CGV": 0, "롯데시네마": 0, "메가박스": 0}
    for c in (detail or {}).get("chains", []):
        if c and c[0] in anchor and len(c) >= 4:
            anchor[c[0]] = _num(c[3]) or 0
    rows = [("CGV", "cgv", anchor["CGV"]), ("롯데시네마", "lot", anchor["롯데시네마"]),
            ("메가박스", "meg", anchor["메가박스"])]
    tr = ""
    for name, k, tk in rows:
        tr += (f'<tr><td style="text-align:left">{name}</td>'
               f'<td><input id="d_{k}_t" type="number" value="{int(tk)}" style="width:72px" oninput="defCalc()"></td>'
               f'<td><input id="d_{k}_u" type="number" step="0.1" placeholder="%" style="width:60px" oninput="defCalc()"></td>'
               f'<td><input id="d_{k}_m" type="number" step="0.1" placeholder="%" style="width:60px" oninput="defCalc()"></td>'
               f'<td id="d_{k}_n" class="gain">-</td><td id="d_{k}_nm" class="gain">-</td></tr>')
    js = """<script>
function defCalc(){
  var keys=['cgv','lot','meg'], sum=0, summ=0;
  keys.forEach(function(k){
    var t=parseFloat(document.getElementById('d_'+k+'_t').value)||0;
    var u=parseFloat(document.getElementById('d_'+k+'_u').value)||0;
    var m=parseFloat(document.getElementById('d_'+k+'_m').value)||0;
    var n=0; if(u>0 && m>u){ n=t*(m/u-1); }
    var nm=Math.ceil(n*1.2/10)*10; n=Math.ceil(n/10)*10;
    document.getElementById('d_'+k+'_n').textContent = n>0? '+'+n.toLocaleString()+'장':'-';
    document.getElementById('d_'+k+'_nm').textContent = n>0? '+'+nm.toLocaleString()+'장':'-';
    sum+=n; summ+=nm;
  });
  document.getElementById('d_sum').textContent = sum>0? '+'+sum.toLocaleString()+'장':'-';
  document.getElementById('d_summ').textContent = summ>0? '+'+summ.toLocaleString()+'장':'-';
}
</script>"""
    return (
        '  <div class="panel"><h2>🎯 예매율 방어 계산기 · 수동 입력 (체인별)</h2>'
        '<p class="hint" style="margin-top:0">각 앱(CGV·롯데·메가)에서 <b>우리 예매율</b>과 <b>모아나(넘을 대상) 예매율</b>을 보고 입력하세요. '
        '예매관객(장)은 회원통계 기준 자동 채움(수정 가능). <b>N = 우리예매관객 × (모아나율 ÷ 우리율 − 1)</b> — 그 체인에서 모아나를 넘는 데 필요한 0원 티켓.</p>'
        '<table><thead><tr><th>체인</th><th>우리 예매관객(장)</th><th>우리 예매율%</th><th>모아나 예매율%</th><th>필요 N</th><th>+마진20%</th></tr></thead><tbody>'
        + tr +
        '<tr style="border-top:2px solid #3b4252;font-weight:700"><td>합계</td><td>-</td><td>-</td><td>-</td>'
        '<td id="d_sum" class="gain">-</td><td id="d_summ" class="gain">-</td></tr>'
        '</tbody></table>'
        '<p class="hint">⚠️ 예매관객 앵커는 회원통계 <b>실관람 기준</b>이라 실제 <b>선예매 장수</b>와 다를 수 있어요(수정 입력 권장). '
        '모아나가 압도적이면 N이 커져 비현실적 → 그땐 <b>모아나 대신 우리 바로 위 홀드오버 예매율</b>을 넣어 "관 지키는 최소 N"을 보세요. '
        '경쟁작도 늘어나니 <b>+마진20%</b> 열을 실제 목표로.</p>' + js + '</div>')


def member_section(snaps, detail, pred=None, sched=None):
    if not snaps:
        return ('<div class="panel" style="text-align:center;color:#9aa0ab;padding:32px 18px">'
                '🎟️ 오늘 관객 현황(회원통계) — 회원통계 엑셀을 넣으면 표시됩니다.</div>')
    last = snaps[-1]
    aud = _num(last.get("관객수")); shows = _num(last.get("상영횟수"))
    free = _num(last.get("무료관객수")) or 0
    per = round(aud / shows) if aud and shows else None
    tot_seats = (sched or {}).get("total_seats") if sched else None
    occ_total = (f"{(aud + free) / tot_seats * 100:.1f}%"
                 if aud and tot_seats else "-")
    cards = [
        ("오늘 관객수 (예매·발권 포함)", fmt(aud)),
        ("전체 좌석판매율", occ_total),
        ("누적관객수", fmt(_num(last.get("누적관객수")))),
        ("회당 관객수", fmt(per)),
        ("스크린수", fmt(_num(last.get("스크린수")))),
    ]
    cards_html = "".join(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in cards)
    updated = (detail or {}).get("updated", last.get("수집시각", ""))
    return (
        f'  <div class="sub" style="margin-top:4px">회원통계 기준 · {updated} · '
        '이 관객수엔 오늘 밤 예매분까지 포함 — 여기서 더 늘면 현매(현장)/막판 당일예매</div>\n'
        f'  <div class="cards">{cards_html}</div>\n'
        '  <div class="panel"><h2>오늘 관객수 추이 (예매·발권 포함)</h2><div class="cbox"><canvas id="c_mem_aud"></canvas></div>'
        '<p class="hint">30분마다의 "오늘 확정 관객(예매+발권)". 오르는 기울기 = <b>현매·당일예매가 붙는 속도</b>. (실제 관람 완료 수 아님)</p></div>\n'
        '  <div class="panel"><h2>시간대별 관객 증가 (오늘, 정시 기준)</h2><div class="cbox"><canvas id="c_mem_peak"></canvas></div>'
        '<p class="hint">정시 후보정 — <b>"09시" = 09:00→10:00에 붙은 관객</b>(예매·발권). 수집이 잦아도 정시 값으로 맞춰 비교가 깔끔. <b>마지막 막대는 진행 중(정시→현재)</b>이라 시간 지나며 채워짐. 막대 높은 시간대 = 수요 피크.</p></div>\n'
        '  <div class="panel"><h2 id="daycmpTitle">📊 시간대별 증가 · 오늘 vs 어제 (동시간대)</h2><div class="cbox"><canvas id="c_mem_daycmp"></canvas></div>'
        '<p class="hint">정시 기준 <b>시간당 증가</b>를 요일끼리 비교(예 "10시"=10:00→11:00). 오늘 막대가 어제보다 높으면 <b style="color:#4ade80">그 시간대는 어제보다 빠른 페이스</b>. '
        '(오늘 수집된 시각까지만, 어제는 하루 전체)</p></div>\n'
        # 날짜 선택 (체인/극장은 날짜별)
        '  <div style="margin:14px 2px 8px;color:#c7ccd6;font-size:13px">📅 날짜 선택: '
        '<select id="dateSel" style="background:#1a1d27;color:#e7e9ee;border:1px solid #3b4252;border-radius:6px;padding:5px 10px;font-size:13px"></select>'
        ' <span class="muted" style="font-size:12px">(체인별·극장별은 선택한 날짜 기준)</span></div>\n'
        '  <div class="panel"><h2 id="chainTitle">🎦 체인별 편성·성적</h2><div id="chainBox"></div>'
        '<p class="hint">좌석수=정원×상영횟수(편성 총 좌석). 좌석판매율=관객÷좌석수. '
        '<b style="color:#4ade80">▲</b>/<b style="color:#f87171">▼</b> = 전날 대비 증감(상영관·상영횟수·좌석). '
        '<b>적게 깔고 판매율 높으면 = 스크린 더 요청 근거</b>, 많이 깔고 낮으면 = 조정 대상.</p></div>\n'
        '  <div class="panel"><h2 id="theaterTitle">🏢 극장(지점)별 관객 TOP50</h2>'
        '<div class="cbox xtall"><canvas id="c_theater"></canvas></div><div id="theaterBox"></div>'
        '<p class="hint">색 = 체인(<b style="color:#ef4444">CGV</b> · <b style="color:#a855f7">메가</b> · '
        '<b style="color:#3b82f6">롯데</b>). 관객÷상영관 = 지점 효율.</p></div>\n'
        '  <div class="panel"><h2 id="hourlyTitle">🕒 시간대별 편성 (회차) · 오늘 vs 어제</h2><div class="cbox short"><canvas id="c_hourly"></canvas></div>'
        '<p class="hint">선택 날짜의 <b>상영 회차 분포</b>(시간표, 전 극장 합) — <b style="color:#22d3ee">오늘</b> 막대 vs <b style="color:#f59e0b">어제</b> 선. '
        '<b>관객 추이가 좋아 보여도 그 시간대 회차가 어제보다 적으면 착시</b>일 수 있어요. 회차가 어제와 같은데 관객 증가가 높으면 = 진짜 수요 강세.</p></div>')


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
  .forecast { background:linear-gradient(135deg,#1e3a2a 0%,#1a1d27 70%); border:1px solid #2f5a42;
              border-radius:14px; padding:16px 20px; margin-bottom:16px; }
  .forecast .lbl { font-size:12px; color:#9aa0ab; }
  .forecast .big { font-size:27px; font-weight:800; color:#4ade80; margin-top:4px; }
  .forecast .sub2 { font-size:12px; color:#c7ccd6; margin-top:6px; }
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
  .cbox.xtall { height:900px; }
  @media (max-width:560px){ .cbox{height:300px} .cbox.tall{height:380px} .cbox.xtall{height:760px} }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:9px 10px; text-align:right; border-bottom:1px solid #262a36; white-space:nowrap; }
  th:first-child,td:first-child { text-align:left; }
  th { color:#9aa0ab; font-weight:600; }
  .gain { color:#4ade80; font-weight:600; }
  .muted { color:#6b7280; }
  .foot { color:#6b7280; font-size:12px; margin-top:16px; text-align:center; }
  .hint { color:#9aa0ab; font-size:12px; margin:10px 2px 0; line-height:1.5; }
  .secdesc { color:#c7ccd6; font-size:12.5px; margin:0 2px 16px; line-height:1.5; }
</style>
</head>
<body>
<div class="wrap">
__FORECAST__
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

  <div style="border-top:1px solid #262a36;margin:8px 0 10px;padding-top:6px;color:#4ade80;font-size:14px;font-weight:600">— 오늘 관객 현황 (회원통계) —</div>
  <div class="secdesc"><b>여기 "관객수"는 오늘 상영분에 대해 현재까지 예매·발권된 관객 총합</b>이에요 (= 이미 본 관객 + 오늘 남은 회차 예매분 + 현장발권). <b style="color:#f4c89a">"지금까지 실제로 본 사람 수"가 아니라 "오늘 최종 관객의 현재 확정분"</b>에 가깝습니다. 이게 늘면(특히 예매 안 줄었는데) = 현장·당일 신규 수요.</div>
__MEMBER_SECTION__

__WEEKEND__

  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#f4c89a;font-size:14px;font-weight:600">— 경쟁작 비교 —</div>
  <div class="secdesc">같은 날(7/1) 개봉작 중 우리 위치. 규모(예매수)보다 <b>상대적 기세(예매율·순위)</b>로 판단.</div>
__COMP_SECTION__

__NOVA__

__THEATERS__

__DEFENSE__

  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#22d3ee;font-size:14px;font-weight:600">— 🔬 신규 예매 수요 분해 (소진 제거) —</div>
  <div class="secdesc">실시간 예매관객수는 <b>(신규 유입 − 상영 소진)</b>이라, 하락해도 신규가 강할 수 있어요. <b style="color:#4ade80">회원 오늘관객 증분(소진 안 됨)</b>으로 순수 신규 수요를 분리해서 봅니다.</div>
__DECOMP_CMT__
  <div class="panel"><h2 id="decompTitle">우리: 신규 수요 vs 실시간 순증 (정시)</h2><div class="cbox"><canvas id="c_decomp"></canvas></div>
    <p class="hint"><b style="color:#4ade80">초록 막대=신규 수요(A)</b>(회원 오늘관객 증분, 소진無) · <b style="color:#f59e0b">주황 선=실시간 예매 순증(dP)</b>(신규−소진) · <b style="color:#9aa0ab">회색 점선=어제 신규</b>. '
    '<b>A는 높은데 dP가 낮으면 = 소진이 큰데 신규가 계속 유입(좋음).</b> A까지 꺼지면 진짜 수요 하락.</p></div>
  <div class="panel"><h2>경쟁작 시간당 순증 (net · 소진 포함)</h2><div class="cbox short"><canvas id="c_compnet"></canvas></div>
    <p class="hint">경쟁작은 회원데이터가 없어 <b>순증(net)만</b> 보여요(신규·소진 분리 불가). ★=우리. 우리 net이 마이너스여도 위 신규(A)는 살아있을 수 있음 — net끼리만 동일 비교.</p></div>

  <div style="border-top:1px solid #262a36;margin:30px 0 18px;padding-top:6px;color:#6ea8fe;font-size:14px;font-weight:600">— 우리 영화 예매(미래 수요) 추이 —</div>
  <div class="secdesc">앞으로의 예약 상황. 실제 관객은 위 '오늘 관객 현황' 섹션, 여기는 <b>앞으로 얼마나 예약됐나(미래 수요)</b>를 봅니다.</div>
  <div class="panel"><h2>순위 변동 추이 (위=상위)</h2><div class="cbox short"><canvas id="c_rank"></canvas></div>
    <p class="hint">전체 예매 순위. 순위 유지·상승이면 경쟁작 대비 위치 양호.</p></div>
  <div class="panel"><h2>예매율 추이 (%)</h2><div class="cbox"><canvas id="c_rate"></canvas></div>
    <p class="hint">전체 예매 중 우리 비중. 절대 예매수보다 <b>기세</b>를 보기 좋아요.</p></div>
  <div class="panel"><h2>예매관객수 추이 (앞으로의 예약)</h2><div class="cbox"><canvas id="c_book"></canvas></div>
    <p class="hint">개봉일엔 회색 점선(프로모 7,750장) 위쪽이 순수 예매분. <b>개봉 다음날부터는 프로모(7/1 상영분)가 빠져나가 회색선은 사라지고</b>, 이 수치는 앞으로 예약된 미래 수요를 뜻해요.</p></div>

  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#f4c89a;font-size:14px;font-weight:600">— 개봉 후 경쟁력 (좌석판매율) —</div>
  <div class="secdesc"><b>좌석판매율 = 관객 ÷ 좌석</b> — 스크린을 많이 깔았든 적게 깔았든 "깔린 좌석이 얼마나 팔렸나". 공급량과 무관한 순수 수요강도라, 개봉작 진짜 경쟁력 지표. (좌석점유율=전체 대비 점유 share와는 다른 개념. KOBIS 확정 집계, 7/2~)</div>
__BOX_SECTION__

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

// ===== 오늘 관객 현황 (회원통계) =====
const MEM = __MEMBER_JSON__;
const chainColor = nm => nm.includes('CGV') ? '#ef4444' : nm.includes('메가박스') ? '#a855f7' : nm.includes('롯데') ? '#3b82f6' : '#9aa0ab';

// ===== 날짜별 체인/극장 (선택) =====
const MEMBYDATE = __MEMBYDATE__;
let theaterChart = null;
function drawTheater(theaters){
  if (theaterChart) theaterChart.destroy();
  theaterChart = new Chart(c_theater, { type:'bar',
    data:{ labels: theaters.map(t=>t[0].length>18?t[0].slice(0,17)+'…':t[0]),
      datasets:[{ label:'관객수', data: theaters.map(t=>t[1]), backgroundColor: theaters.map(t=>chainColor(t[0])),
        datalabels:{ anchor:'end', align:'end', color:'#e7e9ee', font:{size:9,weight:'bold'}, formatter:won } }] },
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, layout:{padding:{right:44}},
      plugins:{ legend:{display:false}, datalabels:{} },
      scales:{ x:{ grid, ticks:tick, beginAtZero:true }, y:{ grid:{display:false}, ticks:{ color:'#c7ccd6', font:{size:10}, autoSkip:false } } } } });
}
const dlt = (cur, prev) => {
  if (prev==null || cur==null) return '';
  const x = cur - prev;
  if (x===0) return ' <span style="color:#6b7280;font-size:11px">-</span>';
  return ` <span style="color:${x>0?'#4ade80':'#f87171'};font-size:11px">${x>0?'▲':'▼'}${won(Math.abs(x))}</span>`;
};
function renderMemberDate(date){
  const d = MEMBYDATE[date]; if(!d) return;
  const dts = Object.keys(MEMBYDATE).sort();
  const prev = dts.indexOf(date)>0 ? MEMBYDATE[dts[dts.indexOf(date)-1]] : null;
  const pByChain = {}; if(prev) prev.chains.forEach(c=>pByChain[c[0]]=c);
  let ct = '<table><thead><tr><th>체인</th><th>상영관</th><th>상영횟수</th><th>좌석수</th><th>관객수</th><th>좌석판매율</th></tr></thead><tbody>';
  d.chains.forEach(c => { const p = pByChain[c[0]];
    ct += `<tr><td>${c[0]}</td><td>${won(c[1])}${dlt(c[1],p?p[1]:null)}</td><td>${won(c[2])}${dlt(c[2],p?p[2]:null)}</td>`
        + `<td>${won(c[3])}${dlt(c[3],p?p[3]:null)}</td><td>${won(c[4])}</td><td class="gain">${c[5]!=null?c[5]+'%':'-'}</td></tr>`; });
  if (d.total) { const t=d.total, pt=prev?prev.total:null;
    ct += `<tr style="border-top:2px solid #3b4252;font-weight:700"><td>합계</td><td>${won(t.screens)}${dlt(t.screens,pt?pt.screens:null)}</td>`
        + `<td>${won(t.shows)}${dlt(t.shows,pt?pt.shows:null)}</td><td>${won(t.seats)}${dlt(t.seats,pt?pt.seats:null)}</td>`
        + `<td>${won(t.aud)}</td><td class="gain">${t.sell!=null?t.sell+'%':'-'}</td></tr>`; }
  ct += '</tbody></table>';
  document.getElementById('chainBox').innerHTML = ct;
  const pTh = {}; if(prev) prev.theaters.forEach(t=>pTh[t[0]]=t[1]);
  let tt = '<table><thead><tr><th>순위</th><th>극장</th><th>상영관</th><th>관객수</th></tr></thead><tbody>';
  d.theaters.forEach((t,i) => { const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${chainColor(t[0])};margin-right:7px"></span>`;
    tt += `<tr><td>${i+1}</td><td style="text-align:left">${dot}${t[0]}</td><td>${won(t[2])}</td><td>${won(t[1])}${dlt(t[1], (t[0] in pTh)?pTh[t[0]]:null)}</td></tr>`; });
  tt += '</tbody></table>';
  document.getElementById('theaterBox').innerHTML = tt;
  const dtl = document.getElementById('theaterTitle'); if(dtl) dtl.textContent = '🏢 극장(지점)별 관객 TOP50 · '+date;
  const dtc = document.getElementById('chainTitle'); if(dtc) dtc.textContent = '🎦 체인별 편성·성적 · '+date;
  drawTheater(d.theaters);
  drawHourly(d.hourly, prev?prev.hourly:null, date, prev?dts[dts.indexOf(date)-1]:null);
}
let hourlyChart=null;
function drawHourly(hourly, prevHourly, date, prevDate){
  const el=document.getElementById('c_hourly'); if(!el) return;
  const t=document.getElementById('hourlyTitle'); if(t) t.textContent=`🕒 시간대별 편성 (회차) · 오늘(${date?.slice(5)}) vs 어제(${prevDate?prevDate.slice(5):'-'})`;
  const hrs=Array.from(new Set([...Object.keys(hourly||{}),...Object.keys(prevHourly||{})].map(Number))).sort((a,b)=>a-b);
  if(hourlyChart) hourlyChart.destroy();
  if(!hrs.length){ return; }
  const ds=[{ type:'bar', label:'오늘 회차', data:hrs.map(h=>(hourly||{})[h]??null),
      backgroundColor:hrs.map(h=>h>=17?'#f59e0b':h>=12?'#22d3ee':'#60a5fa'),
      datalabels:{ anchor:'end',align:'end',color:'#e7e9ee',font:{size:8,weight:'bold'},formatter:won } }];
  if(prevHourly&&Object.keys(prevHourly).length) ds.push({ type:'line', label:'어제 회차', data:hrs.map(h=>prevHourly[h]??null),
      borderColor:'#9aa0ab', borderDash:[4,3], pointRadius:2, tension:.3, spanGaps:true, datalabels:{display:false} });
  hourlyChart=new Chart(el,{ data:{ labels:hrs.map(h=>h+'시'), datasets:ds },
    options:{ ...base(), plugins:{...base().plugins, legend:{display:true,labels:{color:'#c7ccd6'}}}, scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick,beginAtZero:true} } } });
}
(function(){
  const sel = document.getElementById('dateSel'); if(!sel) return;
  const dates = Object.keys(MEMBYDATE).sort();
  if(!dates.length){ sel.parentElement.style.display='none'; return; }
  dates.forEach(dt => { const o=document.createElement('option'); o.value=dt; o.textContent=dt; sel.appendChild(o); });
  sel.value = dates[dates.length-1];
  sel.addEventListener('change', () => renderMemberDate(sel.value));
  renderMemberDate(sel.value);
})();

if (MEM.peak && MEM.peak.length) {
  new Chart(c_mem_peak, { type:'bar',
    data:{ labels: MEM.peak.map(p=>p[0]), datasets:[{ label:'구간 관객 증가', data: MEM.peak.map(p=>p[1]),
      backgroundColor:'#22d3ee',
      datalabels:{ display: MEM.peak.length<=24, anchor:'end', align:'end', color:'#e7e9ee', font:{size:10,weight:'bold'}, formatter:won } }] },
    options:{ ...base(), scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick,beginAtZero:true} } } });
}
if (MEM.daycmp && MEM.daycmp.labels && MEM.daycmp.labels.length) {
  const dc = MEM.daycmp;
  const tt = document.getElementById('daycmpTitle');
  if (tt) tt.textContent = `📊 시간대별 증가 · 오늘(${dc.todayDate?.slice(5)}) vs 어제(${dc.yestDate?.slice(5)}) 동시간대`;
  // 두 날짜가 같은 시각에 모두 값이 있는 구간만 비교(겹치는 시간대만) → 사과 대 사과
  const ov = dc.labels.map((l,i)=>({l, t:dc.today[i], y:dc.yest[i]}))
                      .filter(o => o.t!=null && o.y!=null);
  const panel = document.getElementById('c_mem_daycmp').closest('.cbox');
  if (ov.length) {
    new Chart(c_mem_daycmp, {
      data:{ labels: ov.map(o=>o.l), datasets:[
        { type:'bar', label:`오늘 ${dc.todayDate?.slice(5)||''}`, data: ov.map(o=>o.t), backgroundColor:'#22d3ee',
          datalabels:{display:false} },
        { type:'bar', label:`어제 ${dc.yestDate?.slice(5)||''}`, data: ov.map(o=>o.y), backgroundColor:'#f59e0b',
          datalabels:{display:false} } ] },
      options:{ ...base(), plugins:{ ...base().plugins, legend:{display:true, labels:{color:'#c7ccd6'}} },
        scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick,beginAtZero:true} } } });
  } else if (panel) {
    panel.style.height='auto';
    panel.innerHTML = '<div style="color:#9aa0ab;font-size:13px;padding:26px 14px;text-align:center;line-height:1.6">'
      + '아직 <b>어제와 겹치는 시간대</b>가 없어요.<br>'
      + `오늘 수집: <b>${dc.today.filter(x=>x!=null).length?dc.labels.find((l,i)=>dc.today[i]!=null)+'~':'-'}</b> · `
      + `어제 수집: <b>${dc.yest.filter(x=>x!=null).length?dc.labels.filter((l,i)=>dc.yest[i]!=null)[0]+'~':'-'}</b><br>`
      + '오늘이 어제 수집 시간대(저녁)에 도달하면 겹치는 구간부터 자동으로 나란히 표시됩니다.</div>';
  }
}
if (MEM.aud && MEM.aud.length) {
  new Chart(c_mem_aud, { type:'line',
    data:{ labels:MEM.labels, datasets:[{ label:'오늘 관객수(예매포함)', data:MEM.aud,
      borderColor:'#4ade80', backgroundColor:'rgba(74,222,128,.12)', fill:true, tension:.3, spanGaps:true,
      datalabels:{ display:ctx=>ctx.dataIndex===MEM.aud.length-1, align:'top', color:'#4ade80', font:{weight:'bold',size:13}, formatter:won } }] },
    options:base() });
}
// ===== 신규 예매 수요 분해 =====
const DECOMP = __DECOMP_JSON__;
if (DECOMP && DECOMP.today && DECOMP.today.labels.length) {
  const t = DECOMP.today;
  const dt = document.getElementById('decompTitle');
  if (dt) dt.textContent = `우리: 신규 수요 vs 실시간 순증 · 오늘(${DECOMP.todayDate?.slice(5)})`;
  // 어제 신규(A)를 오늘 라벨(시각)에 맞춰 정렬
  let yA = [];
  if (DECOMP.yest) { const map={}; DECOMP.yest.labels.forEach((l,i)=>map[l]=DECOMP.yest.A[i]); yA = t.labels.map(l=>map[l]??null); }
  new Chart(c_decomp, { data:{ labels:t.labels, datasets:[
    { type:'bar', label:'신규 수요(A·소진無)', data:t.A, backgroundColor:'#4ade80', order:3, datalabels:{display:false} },
    { type:'line', label:'실시간 예매 순증(dP)', data:t.dP, borderColor:'#f59e0b', backgroundColor:'#f59e0b', tension:.3, pointRadius:2, spanGaps:true, order:1, datalabels:{display:false} },
    { type:'line', label:'어제 신규', data:yA, borderColor:'#9aa0ab', borderDash:[5,4], pointRadius:0, tension:.3, spanGaps:true, order:2, datalabels:{display:false} } ] },
    options:{ ...base(), plugins:{ ...base().plugins, legend:{display:true, labels:{color:'#c7ccd6'}} },
      scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick} } } });
}
if (DECOMP && DECOMP.comp && DECOMP.comp.length) {
  const pal = ['#f59e0b','#60a5fa','#f472b6','#a78bfa','#fb7185','#22d3ee'];
  let ci=0;
  const ds = DECOMP.comp.map(c => {
    const nm = c.name.length>10 ? c.name.slice(0,9)+'…' : c.name;
    return { label:(c.g?'★ ':'')+nm, data:c.net, borderColor: c.g?'#4ade80':pal[(ci++)%pal.length],
      borderWidth:c.g?3:1.5, pointRadius:0, tension:.3, spanGaps:true, datalabels:{display:false} };
  });
  // 라벨은 가장 긴 시리즈 기준
  const lab = DECOMP.comp.reduce((a,c)=>c.labels.length>a.length?c.labels:a, []);
  new Chart(c_compnet, { type:'line', data:{ labels:lab, datasets:ds },
    options:{ ...base(), plugins:{ ...base().plugins, legend:{display:true, labels:{color:'#c7ccd6',font:{size:10}}} },
      scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick} } } });
}
// ===== 경쟁작 비교 =====
const COMP = __COMP_JSON__;
if (COMP.latest && COMP.latest.length) {
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

const bookDs = [
  { label:'예매관객수', data:PTS.map(p=>p.book),
    borderColor:'#4ade80', backgroundColor:'rgba(74,222,128,.12)', tension:.3, fill:true, spanGaps:true,
    datalabels:lastOnly('book','#4ade80') }
];
if (__PROMO_ON__) bookDs.push(
  { label:'프로모션 물량(7,750)', data:labels.map(()=>__PROMO__),
    borderColor:'#9aa0ab', borderDash:[6,4], borderWidth:1.5, pointRadius:0, fill:false,
    datalabels:{ display:false } });
new Chart(c_book, { type:'line', data:{ labels, datasets:bookDs }, options:base() });
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
    m_snaps, m_detail = load_member()
    m_sched = load_schedule()
    m_pred = predict_final(m_snaps[-1] if m_snaps else None, m_sched)
    member_json = json.dumps({
        "labels": [s["수집시각"][5:16] for s in m_snaps],
        "aud": [_num(s.get("관객수")) for s in m_snaps],
        "slots": (m_detail or {}).get("slots", []),
        "regions": (m_detail or {}).get("regions", []),
        "theaters": (m_detail or {}).get("theaters", []),
        "peak": _member_peak(m_snaps),
        "daycmp": member_daycompare(m_snaps),
    }, ensure_ascii=False)
    fc_html = forecast_banner(forecast_eod(pts))
    # 개봉 최종 총관객(전체 스코어) — 누적(실시간, 전일까지 확정) + 경과일수
    cumul_life = _num((latest(pts) or {}).get("cumul"))
    try:
        completed_days = (datetime.date.fromisoformat(last.get("date")) -
                          datetime.date.fromisoformat(last.get("open"))).days
    except Exception:
        completed_days = None
    html = (HTML
            .replace("__MOVIE__", movie)
            .replace("__OPEN__", last.get("open", "-") or "-")
            .replace("__POSTER__", POSTER)
            .replace("__TAGLINE__", TAGLINE)
            .replace("__CAST__", CAST)
            .replace("__PROMO__", str(PROMO_TICKETS))
            .replace("__PROMO_ON__", "true" if (last.get("date") and last.get("open") and last["date"] <= last["open"]) else "false")
            .replace("__UPDATED__", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__LASTTIME__", last.get("time", "") or "")
            .replace("__FORECAST__", ai_comment_banner() + "\n"
                     + lifetime_banner(cumul_life, completed_days, last.get("date")) + "\n"
                     + top_forecast_banner(m_snaps, m_sched) + "\n" + secured_banner(pts, m_snaps))
            .replace("__CARDS__", build_cards(pts))
            .replace("__N__", str(len(pts)))
            .replace("__BOX_SECTION__", box_leaderboard(comp.get("open", "")))
            .replace("__BOX_JSON__", box_json)
            .replace("__COMP_SECTION__", comp_section(comp))
            .replace("__DEFENSE__", manual_defense(m_detail) + "\n" + defense_calculator(load_competitors()))
            .replace("__DECOMP_JSON__", json.dumps(build_decomp(), ensure_ascii=False))
            .replace("__NOVA__", nova_section())
            .replace("__THEATERS__", theater_ranking_section())
            .replace("__DECOMP_CMT__", _ai_cmt("decomp"))
            .replace("__COMP_JSON__", comp_json)
            .replace("__MEMBER_SECTION__", member_section(m_snaps, m_detail, m_pred, m_sched))
            .replace("__WEEKEND__", weekend_scenario(
                max((s["수집시각"][:10] for s in m_snaps),
                    default=datetime.datetime.now().strftime("%Y-%m-%d"))))
            .replace("__MEMBER_JSON__", member_json)
            .replace("__MEMBYDATE__", json.dumps(build_membydate(), ensure_ascii=False))
            .replace("__DATA_JSON__", data_json))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    print("생성:", generate())
