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
        out[date] = {"chains": chains, "theaters": mem.get(date, {}).get("theaters") or [], "total": total}
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


def member_daycompare(snaps):
    """오늘 vs 어제 동시간대 관객 증가 비교 + 동시간 대비 예측(마감 관객).
    이전 날짜가 현재 시각을 커버하면 예측 활성화(오늘 저녁부터/내일부터)."""
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

    def incs(v):
        v = sorted(v); out = {}; prev = None
        for m, a in v:
            if prev is not None and a - prev >= 0:
                out[m // 30 * 30] = out.get(m // 30 * 30, 0) + (a - prev)
            prev = a
        return out

    ti, yi = incs(days[today]), incs(days[yest])
    buckets = sorted(set(ti) | set(yi))
    labels = [f"{b // 60:02d}:{b % 60:02d}" for b in buckets]
    tv, yv = sorted(days[today]), sorted(days[yest])
    now_m, now_a = tv[-1]
    pred = None
    if yv[0][0] <= now_m <= yv[-1][0]:
        ya = _interp(yv, now_m)
        yfinal = yv[-1][1]
        if ya and ya > 0:
            ratio = now_a / ya
            pred = {"ratio": round(ratio, 3), "pred": int(round(yfinal * ratio)),
                    "now": now_a, "yestNow": int(round(ya)), "yestFinal": yfinal, "yest": yest}
    return {"labels": labels, "today": [ti.get(b) for b in buckets],
            "yest": [yi.get(b) for b in buckets], "todayDate": today, "yestDate": yest, "pred": pred}


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


def _member_peak(snaps):
    """오늘 스냅샷의 구간(관객수 증가) → 시간대별 실관람 증가. 마지막 날짜 기준."""
    if not snaps:
        return []
    today = max(s.get("수집시각", "")[:10] for s in snaps)
    ts = sorted((s for s in snaps if s.get("수집시각", "")[:10] == today),
                key=lambda s: s.get("수집시각", ""))
    out, prev = [], None
    for s in ts:
        a = _num(s.get("관객수"))
        t = s.get("수집시각", "")[11:16]
        if prev is not None and a is not None and a - prev >= 0:
            out.append([t, a - prev])
        if a is not None:
            prev = a
    return out


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
        eod_banner(snaps) + "\n"
        + daycmp_banner(snaps) + "\n"
        f'  <div class="sub" style="margin-top:4px">회원통계 기준 · {updated} · '
        '이 관객수엔 오늘 밤 예매분까지 포함 — 여기서 더 늘면 현매(현장)/막판 당일예매</div>\n'
        f'  <div class="cards">{cards_html}</div>\n'
        '  <div class="panel"><h2>오늘 관객수 추이 (예매·발권 포함)</h2><div class="cbox"><canvas id="c_mem_aud"></canvas></div>'
        '<p class="hint">30분마다의 "오늘 확정 관객(예매+발권)". 오르는 기울기 = <b>현매·당일예매가 붙는 속도</b>. (실제 관람 완료 수 아님)</p></div>\n'
        '  <div class="panel"><h2>시간대별 관객 증가 (오늘, 구간별)</h2><div class="cbox"><canvas id="c_mem_peak"></canvas></div>'
        '<p class="hint">각 구간의 확정 관객 <b>증가분</b> = 그 시간대에 예매·발권이 얼마나 붙었나. 막대 높은 구간 = 수요 피크.</p></div>\n'
        '  <div class="panel"><h2 id="daycmpTitle">📊 시간대별 증가 · 오늘 vs 어제 (동시간대)</h2><div class="cbox"><canvas id="c_mem_daycmp"></canvas></div>'
        '<p class="hint">같은 시각끼리 <b>구간 증가분</b>을 비교. 오늘 막대가 어제 선보다 높으면 <b style="color:#4ade80">그 시간대는 어제보다 빠른 페이스</b>. '
        '(어제가 그 시각을 커버하는 구간만 겹쳐 보임 — 저녁부터 채워짐)</p></div>\n'
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
        '<b style="color:#3b82f6">롯데</b>). 관객÷상영관 = 지점 효율.</p></div>')


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

  <div style="border-top:1px solid #262a36;margin:30px 0 10px;padding-top:6px;color:#f4c89a;font-size:14px;font-weight:600">— 경쟁작 비교 —</div>
  <div class="secdesc">같은 날(7/1) 개봉작 중 우리 위치. 규모(예매수)보다 <b>상대적 기세(예매율·순위)</b>로 판단.</div>
__COMP_SECTION__

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
  new Chart(c_mem_daycmp, {
    data:{ labels: dc.labels, datasets:[
      { type:'bar', label:`오늘 ${dc.todayDate?.slice(5)||''}`, data: dc.today, backgroundColor:'#22d3ee',
        datalabels:{display:false} },
      { type:'line', label:`어제 ${dc.yestDate?.slice(5)||''}`, data: dc.yest, borderColor:'#f59e0b',
        backgroundColor:'#f59e0b', pointRadius:3, tension:.3, spanGaps:true, datalabels:{display:false} } ] },
    options:{ ...base(), plugins:{ ...base().plugins, legend:{display:true, labels:{color:'#c7ccd6'}} },
      scales:{ x:{grid,ticks:tick}, y:{grid,ticks:tick,beginAtZero:true} } } });
}
if (MEM.aud && MEM.aud.length) {
  new Chart(c_mem_aud, { type:'line',
    data:{ labels:MEM.labels, datasets:[{ label:'오늘 관객수(예매포함)', data:MEM.aud,
      borderColor:'#4ade80', backgroundColor:'rgba(74,222,128,.12)', fill:true, tension:.3, spanGaps:true,
      datalabels:{ display:ctx=>ctx.dataIndex===MEM.aud.length-1, align:'top', color:'#4ade80', font:{weight:'bold',size:13}, formatter:won } }] },
    options:base() });
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
            .replace("__FORECAST__", secured_banner(pts, m_snaps))
            .replace("__CARDS__", build_cards(pts))
            .replace("__DAILY__", build_daily_table(pts))
            .replace("__N__", str(len(pts)))
            .replace("__BOX_SECTION__", box_leaderboard(comp.get("open", "")))
            .replace("__BOX_JSON__", box_json)
            .replace("__COMP_SECTION__", comp_section(comp))
            .replace("__COMP_JSON__", comp_json)
            .replace("__MEMBER_SECTION__", member_section(m_snaps, m_detail, m_pred, m_sched))
            .replace("__MEMBER_JSON__", member_json)
            .replace("__MEMBYDATE__", json.dumps(build_membydate(), ensure_ascii=False))
            .replace("__DATA_JSON__", data_json))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    print("생성:", generate())
