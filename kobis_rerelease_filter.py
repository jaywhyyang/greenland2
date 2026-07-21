# -*- coding: utf-8 -*-
"""
재개봉·구작 판별용 보조 수집기 → rerelease_suspects.csv

배경: arthouse_foreign.csv 의 '신작'은 개봉일 >= 2024-01-01 로만 걸러져 있다.
그런데 리마스터·재개봉이 새 영화코드 + 새 개봉일로 등록되는 사례가 있어
(예: 경멸 1963년작이 2024~2026 개봉일로 등재) 신작 분포를 위로 왜곡한다.

해법: KOBIS 영화정보 검색은 제작연도(sPrdtYearS/E)와 개봉연도(sOpenYearS/E)를
      각각 범위로 필터할 수 있다. '제작연도는 옛날인데 개봉연도는 최근'인 외국영화를
      전량 뽑아 두고, 분석 단계에서 제목 기준으로 제외한다.
"""
import os
import re
import csv
import time
import urllib.request
import urllib.parse
import http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "rerelease_suspects.csv")
URL = "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieList.do"

PRDT_TO = "2022"      # 제작연도 상한: 개봉 2024 기준 2년 이상 묵은 작품을 구작으로 본다
OPEN_FROM, OPEN_TO = "2024", "2026"
DELAY = 0.7


def _clean(cell):
    t = re.sub(r"<[^>]+>", "", cell).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def fetch_page(page):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", URL)]
    g = op.open(URL, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    data = urllib.parse.urlencode({
        "CSRFToken": m.group(1) if m else "", "sMovName": "", "sMovLang": "ko",
        "curPage": str(page), "searchType": "search",
        "sPrdtYearS": "1900", "sPrdtYearE": PRDT_TO,
        "sOpenYearS": OPEN_FROM, "sOpenYearE": OPEN_TO,
        "sRepNationStr": "외국",
    }).encode()
    h = op.open(urllib.request.Request(URL, data=data), timeout=30).read().decode("utf-8", "replace")
    out = []
    for mb in re.finditer(r"<tbody[^>]*>(.*?)</tbody>", h, re.S):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", mb.group(1), re.S):
            c = [_clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(c) >= 4 and c[0]:
                out.append({"영화명": c[0], "영화코드": c[2], "제작연도": c[3],
                            "제작국가": c[4] if len(c) > 4 else ""})
        break
    return out


def main():
    seen, page = {}, 1
    while True:
        try:
            rows = fetch_page(page)
        except Exception as e:
            print(f"  !! page {page} 실패: {e}")
            time.sleep(3)
            continue
        if not rows:
            break
        for r in rows:
            seen.setdefault(r["영화명"], r)
        print(f"  page {page}: {len(rows)}편 (누적 {len(seen)})")
        page += 1
        time.sleep(DELAY)

    with open(OUT, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=["영화명", "영화코드", "제작연도", "제작국가"])
        w.writeheader()
        w.writerows(seen.values())
    print(f"\n완료: 구작-최근개봉 {len(seen)}편 → {OUT}")


if __name__ == "__main__":
    main()
