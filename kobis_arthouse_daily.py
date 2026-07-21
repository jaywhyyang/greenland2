# -*- coding: utf-8 -*-
"""
다양성 외화 일별 관객 + 좌석 전수 수집 (엑셀 내보내기 경로)
  → arthouse_daily.csv  (날짜 × 영화 단위: 관객수, 좌석수, 좌석판매율)
  → arthouse_meta.csv   (영화 단위: 배급사·제작사·등급·장르·감독·배우·국적)

■ 왜 엑셀 경로인가 (실측으로 확인)
  화면 조회(HTML 표)에는 상한이 있다:
    · 일별 박스오피스/좌석 페이지는 10행 고정, 페이징 불가
    · 기간별 좌석 페이지는 하루 50편 고정 — 페이징·정렬·영화명 필터 전부 무시
  반면 엑셀 내보내기는 상한이 없다:
    · 기간별 박스오피스 + searchType=excelDaily
        → 날짜를 열로 펼친 일별 관객수. 단 조회기간 1주 이하만 허용.
        → 배급사/제작사/등급/장르/감독/배우/국적까지 함께 제공(직배 판별용).
    · 기간별 좌석 + dmlMode=excel
        → 그 기간 좌석 집계. 실측 2025-02-13 하루 조회 시 80편 전량 반환
          (같은 날 화면 조회는 50편에서 잘림, 최소 59석짜리까지 포함됨).
        → 일자별 좌석이 필요하므로 하루 단위로 조회한다.

두 산출물 모두 이미 수집한 구간은 건너뛰므로 중단 후 재실행(resume) 가능.
"""
import os
import re
import csv
import time
import datetime
import urllib.request
import urllib.parse
import http.cookiejar
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DAY = os.path.join(BASE, "arthouse_daily.csv")
OUT_META = os.path.join(BASE, "arthouse_meta.csv")
LOG = os.path.join(BASE, "arthouse_daily.log")

PB = "https://www.kobis.or.kr/kobis/business/stat/boxs/findPeriodBoxOfficeList.do"
PS = "https://www.kobis.or.kr/kobis/business/stat/boxs/findPeriodSeatTicketList.do"

START = datetime.date(2024, 1, 1)
END = datetime.date.today()
DELAY = 0.7

DAY_HEADER = ["날짜", "영화명", "개봉일", "관객수", "스크린수", "상영횟수",
              "좌석수", "좌석판매율", "좌석점유율"]
SEAT_CACHE = os.path.join(BASE, "arthouse_seats.csv")
META_HEADER = ["영화명", "개봉일", "대표국적", "국적", "제작사", "배급사", "등급", "장르", "감독", "배우"]


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _clean(x):
    t = re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").replace("&#039;", "'").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def _num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def _download(url, payload):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", url)]
    g = op.open(url, timeout=60).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    payload = dict(payload, CSRFToken=(m.group(1) if m else ""))
    r = op.open(urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode()), timeout=180)
    return r.read().decode("utf-8", "replace")


def _table(html):
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c = [_clean(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if c:
            out.append(c)
    return out


def box_week(d0, d1):
    """일별엑셀: 날짜가 열로 펼쳐진 관객수 + 메타데이터. 반환 (일별행들, 메타행들)."""
    html = _download(PB, {
        "loadEnd": "0", "searchType": "excelDaily",
        "sSearchFrom": d0.strftime("%Y-%m-%d"), "sSearchTo": d1.strftime("%Y-%m-%d"),
        "sMultiMovieYn": "Y", "sRepNationCd": "F", "sWideAreaCd": "",
        "sMovName": "", "sMovLang": "ko",
    })
    rows = _table(html)
    hi = next((i for i, c in enumerate(rows) if c and c[0] == "순위"), None)
    if hi is None:
        return [], []
    # 헤더는 날짜 1칸(colspan=6)으로 보이지만 데이터 행은 날짜당 6칸이다.
    # 앞 11칸이 메타(순위~배우), 이후 날짜별 6칸이 순서대로
    #   매출액 / 누적매출액 / 관객수 / 누적관객수 / 스크린수 / 상영횟수
    # 마지막 합계 2칸은 버린다. 이 구조를 무시하고 헤더 인덱스를 그대로 쓰면
    # 관객수 자리에서 매출액을 읽게 되므로 반드시 오프셋으로 접근한다.
    META_N, BLK = 11, 6
    dates = [h for h in rows[hi] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", h)]
    daily, metas = [], []
    for c in rows[hi + 1:]:
        if not c or not c[0].isdigit() or len(c) < META_N + BLK:
            continue
        name, opendt = c[1], c[2]
        metas.append({"영화명": name, "개봉일": opendt, "대표국적": c[3], "국적": c[4],
                      "제작사": c[5], "배급사": c[6], "등급": c[7], "장르": c[8],
                      "감독": c[9], "배우": c[10]})
        for i, ds in enumerate(dates):
            b = META_N + i * BLK
            if b + 5 >= len(c):
                break
            aud = _num(c[b + 2])
            if aud:
                daily.append({"날짜": ds, "영화명": name, "개봉일": opendt, "관객수": aud,
                              "스크린수": _num(c[b + 4]), "상영횟수": _num(c[b + 5])})
    return daily, metas


def seat_day(d):
    """하루 좌석 엑셀. 영화명 → (좌석수, 좌석판매율, 좌석점유율). 상한 없음."""
    ds = d.strftime("%Y-%m-%d")
    html = _download(PS, {
        "loadEnd": "0", "dmlMode": "excel", "searchType": "search",
        "startDate": ds, "endDate": ds,
        "repNationCd": "F", "wideareaCd": "", "sMovName": "", "sMovLang": "ko",
    })
    rows = _table(html)
    hi = next((i for i, c in enumerate(rows) if c and c[0] == "순위"), None)
    if hi is None:
        return {}
    out = {}
    for c in rows[hi + 1:]:
        if not c or not c[0].isdigit() or len(c) < 6:
            continue
        out[c[1]] = (_num(c[5]), c[3], c[4])
    return out


def _done(path, key):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r[key] for r in csv.DictReader(f) if r.get(key)}


def main():
    for p, h in ((OUT_DAY, DAY_HEADER), (OUT_META, META_HEADER)):
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=h).writeheader()

    done_dates = _done(OUT_DAY, "날짜")
    done_meta = _done(OUT_META, "영화명")

    # 1) 주 단위로 일별 관객 + 메타 수집
    log(f"[1/2] 일별 관객·메타 수집 {START}~{END}")
    d = START
    while d <= END:
        d1 = min(d + datetime.timedelta(days=6), END)
        span = [d + datetime.timedelta(days=i) for i in range((d1 - d).days + 1)]
        if all(x.strftime("%Y-%m-%d") in done_dates for x in span):
            d = d1 + datetime.timedelta(days=1)
            continue
        try:
            daily, metas = box_week(d, d1)
        except Exception as e:
            log(f"  !! {d} 박스오피스 실패: {e}")
            time.sleep(4)
            continue
        seen = {}
        for m in metas:
            if m["영화명"] not in done_meta and m["영화명"] not in seen:
                seen[m["영화명"]] = m
        with open(OUT_DAY, "a", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=DAY_HEADER).writerows(
                [dict.fromkeys(DAY_HEADER, "") | r for r in daily])
        if seen:
            with open(OUT_META, "a", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=META_HEADER).writerows(seen.values())
            done_meta |= set(seen)
        done_dates |= {x.strftime("%Y-%m-%d") for x in span}
        log(f"  {d}~{d1}: 관객행 {len(daily)}, 신규영화 {len(seen)} (누적 {len(done_meta)}편)")
        d = d1 + datetime.timedelta(days=1)
        time.sleep(DELAY)

    # 2) 좌석 채워넣기 — 이전 실행분 캐시(arthouse_seats.csv)를 먼저 쓰고 없는 날만 조회
    log("[2/2] 좌석 채우기")
    rows = list(csv.DictReader(open(OUT_DAY, encoding="utf-8-sig")))
    seatmap = defaultdict(dict)
    if os.path.exists(SEAT_CACHE):
        for r in csv.DictReader(open(SEAT_CACHE, encoding="utf-8-sig")):
            seatmap[r["날짜"]][r["영화명"]] = (r["좌석수"], r["좌석판매율"], r["좌석점유율"])
        log(f"  캐시에서 {sum(len(v) for v in seatmap.values())}건 복원 ({len(seatmap)}일)")

    todo = sorted({r["날짜"] for r in rows if not r["좌석수"]} - set(seatmap))
    log(f"  추가 조회 필요 {len(todo)}일")
    for i, ds in enumerate(todo, 1):
        try:
            seatmap[ds] = seat_day(datetime.date(*map(int, ds.split("-"))))
        except Exception as e:
            log(f"  !! {ds} 좌석 실패: {e}")
            seatmap[ds] = {}
        if i % 25 == 0:
            log(f"  좌석 {i}/{len(todo)}")
        time.sleep(DELAY)

    # 새로 받은 날짜분을 캐시에 반영
    with open(SEAT_CACHE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["날짜", "영화명", "좌석수", "좌석판매율", "좌석점유율"])
        w.writeheader()
        for ds, mv in sorted(seatmap.items()):
            for nm, s in mv.items():
                w.writerow({"날짜": ds, "영화명": nm, "좌석수": s[0],
                            "좌석판매율": s[1], "좌석점유율": s[2]})

    n_hit = 0
    for r in rows:
        if r["좌석수"]:
            continue
        s = seatmap.get(r["날짜"], {}).get(r["영화명"])
        if s:
            r["좌석수"], r["좌석판매율"], r["좌석점유율"] = s[0], s[1], s[2]
            n_hit += 1
    with open(OUT_DAY, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DAY_HEADER)
        w.writeheader()
        w.writerows(rows)

    miss = sum(1 for r in rows if not r["좌석수"])
    log(f"완료 → {OUT_DAY} ({len(rows)}행, 좌석 채움 {n_hit}, 여전히 결손 {miss})")
    log(f"완료 → {OUT_META} ({len(done_meta)}편)")


if __name__ == "__main__":
    main()
