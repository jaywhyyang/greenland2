# -*- coding: utf-8 -*-
"""
신작 아트하우스 외화 부수정보 보강 → arthouse_enriched.csv

입력: arthouse_foreign.csv (kobis_arthouse_scan.py 산출물, 영화별 최종 누적)
보강 항목:
  - 첫주 관객 / 개봉 스크린수 / 첫주 상영횟수  ← 기간별 박스오피스를 개봉일~+6일로 조회
  - 제작연도 / 제작국가 / 장르 / 감독          ← 영화정보 검색
  - 파생: 최종/첫주 배수(입소문 계수), 스크린당 관객

주의:
  - 기간별 박스오피스에 '좌석수'는 없다(일별 좌석 페이지에만 존재). 대신 상영횟수로 규모를 본다.
  - 제작연도는 재개봉 판별용. 개봉연도-제작연도 갭 6년 이상은 재개봉으로 본다(민감도 분석 결과).
"""
import os
import re
import csv
import time
import datetime
import urllib.request
import urllib.parse
import http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "arthouse_foreign.csv")
OUT = os.path.join(BASE, "arthouse_enriched.csv")
BOX = "https://www.kobis.or.kr/kobis/business/stat/boxs/findPeriodBoxOfficeList.do"
INFO = "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieList.do"

NEW_FROM = datetime.date(2024, 1, 1)
NEW_TO = datetime.date(2026, 4, 30)   # 개봉 3개월 경과분만 (성적 확정)
DELAY = 0.5
HEADER = ["순위", "영화명", "개봉일", "제작연도", "제작국가", "장르", "감독",
          "개봉스크린수", "첫주관객", "첫주상영횟수", "최종누적관객", "누적매출액",
          "배수", "스크린당관객"]


def _clean(cell):
    t = re.sub(r"<[^>]+>", "", cell).replace("&nbsp;", " ").replace("&#039;", "'")
    return re.sub(r"\s+", " ", t).strip()


def _num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def _open(url):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", url)]
    g = op.open(url, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    return op, (m.group(1) if m else "")


def _rows(op, url, payload, min_cells):
    h = op.open(urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode()),
                timeout=30).read().decode("utf-8", "replace")
    out = []
    for mb in re.finditer(r"<tbody[^>]*>(.*?)</tbody>", h, re.S):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", mb.group(1), re.S):
            c = [_clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(c) >= min_cells and c[0]:
                out.append(c)
        break
    return out


def first_week(name, opendt):
    """개봉일~+6일 구간의 관객수/스크린수/상영횟수. 해당 구간 '관객수' 컬럼이 곧 첫주 성적."""
    d1 = (opendt + datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    op, tok = _open(BOX)
    rows = _rows(op, BOX, {
        "CSRFToken": tok, "loadEnd": "0", "searchType": "search",
        "sSearchFrom": opendt.strftime("%Y-%m-%d"), "sSearchTo": d1,
        "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": "",
        "sMovName": name, "sMovLang": "ko", "curPage": "1",
    }, 10)
    for c in rows:
        if c[1] == name:
            return _num(c[6]), _num(c[8]), _num(c[9])
    return 0, 0, 0


def meta(name):
    """영화정보 검색 → (제작연도, 제작국가, 장르, 감독). 동명이작은 첫 매치를 쓴다."""
    op, tok = _open(INFO)
    rows = _rows(op, INFO, {
        "CSRFToken": tok, "sMovName": name, "sMovLang": "ko",
        "curPage": "1", "searchType": "search",
    }, 4)
    for c in rows:
        if c[0] == name:
            return (c[3], c[4] if len(c) > 4 else "",
                    c[6] if len(c) > 6 else "", c[8] if len(c) > 8 else "")
    return "", "", "", ""


def main():
    src = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    films = []
    for r in src:
        try:
            dt = datetime.date(*map(int, r["개봉일"].split("-")))
        except Exception:
            continue
        if NEW_FROM <= dt <= NEW_TO:
            films.append((r["영화명"], dt, int(r["누적관객수"]), int(r["누적매출액"])))
    films.sort(key=lambda x: -x[2])
    print(f"대상 {len(films)}편 보강 시작")

    recs = []
    for i, (name, dt, cum, sales) in enumerate(films, 1):
        try:
            fw, scr, shows = first_week(name, dt)
        except Exception as e:
            print(f"  !! {name} 첫주 실패: {e}")
            fw, scr, shows = 0, 0, 0
        time.sleep(DELAY)
        try:
            py, nat, gen, dire = meta(name)
        except Exception as e:
            print(f"  !! {name} 메타 실패: {e}")
            py, nat, gen, dire = "", "", "", ""
        time.sleep(DELAY)
        recs.append({
            "영화명": name, "개봉일": dt.strftime("%Y-%m-%d"), "제작연도": py,
            "제작국가": nat, "장르": gen, "감독": dire,
            "개봉스크린수": scr, "첫주관객": fw, "첫주상영횟수": shows,
            "최종누적관객": cum, "누적매출액": sales,
            "배수": round(cum / fw, 2) if fw else "",
            "스크린당관객": round(cum / scr) if scr else "",
        })
        if i % 25 == 0:
            print(f"  {i}/{len(films)} …")

    recs.sort(key=lambda r: -r["최종누적관객"])
    for i, r in enumerate(recs, 1):
        r["순위"] = i
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=HEADER)
        w.writeheader()
        w.writerows(recs)
    print(f"\n완료: {len(recs)}편 → {OUT}")


if __name__ == "__main__":
    main()
