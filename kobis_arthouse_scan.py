# -*- coding: utf-8 -*-
"""
KOBIS 다양성(예술)영화 × 외국영화 세그먼트 전수 수집 → arthouse_foreign.csv

배경: 신작 아트하우스 외화의 국내 실적 분포를 확인해 개봉 여부를 판단하기 위한 데이터셋.

핵심 주의사항 (실측으로 확인된 KOBIS 동작):
- '관객수' 컬럼은 조회 기간 내 실적만 담는다. 기간 경계를 걸친 영화는 과소집계된다.
  (예: 서브스턴스 2024-12-11 개봉 → 2025년 조회 시 405,591. 실제 누적은 561,934)
- '누적관객수' 컬럼은 기간 시작일과 무관하게 '기간 종료일 기준 전체 누적'이다.
  (예: 위플래쉬 2015년 개봉작이 2025년 조회에서도 1,731,938로 표시)
  → 따라서 누적관객수를 쓰되, 월별로 훑어 영화별 최댓값을 취하면 최종 누적이 확정된다.
- 조회 기간에 상영 중이던 영화만 목록에 나온다. 그래서 월 단위로 쪼개 전 구간을 훑는다.
- 재개봉작이 다양성영화로 함께 잡힌다. 개봉일 기준 필터는 분석 단계에서 수행한다.
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
OUT = os.path.join(BASE, "arthouse_foreign.csv")
URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findPeriodBoxOfficeList.do"

START = datetime.date(2024, 1, 1)
DELAY = 0.8  # 요청 사이 딜레이(초) — 차단 회피
HEADER = ["영화명", "개봉일", "누적관객수", "누적매출액", "스크린수", "상영횟수", "관측월"]


def _clean(cell):
    t = re.sub(r"<[^>]+>", "", cell).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def _num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def _fetch_page(date_from, date_to, page, multi="Y", nation="F"):
    """기간별 박스오피스 한 페이지(최대 100편) 조회. 행별 셀 리스트 반환."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", URL)]
    g = op.open(URL, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    token = m.group(1) if m else ""
    data = urllib.parse.urlencode({
        "CSRFToken": token, "loadEnd": "0", "searchType": "search",
        "sSearchFrom": date_from, "sSearchTo": date_to,
        "sMultiMovieYn": multi,      # Y=다양성영화, N=상업영화, ''=전체
        "sRepNationCd": nation,      # F=외국영화, K=한국영화, ''=전체
        "sWideAreaCd": "", "sMovName": "", "sMovLang": "ko",
        "curPage": str(page),
    }).encode()
    h = op.open(urllib.request.Request(URL, data=data), timeout=30).read().decode("utf-8", "replace")
    for mb in re.finditer(r"<tbody[^>]*>(.*?)</tbody>", h, re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", mb.group(1), re.S)
        if len(rows) > 2:
            out = []
            for row in rows:
                cells = [_clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                if len(cells) >= 10 and cells[1]:
                    out.append(cells)
            return out
    return []


def fetch(date_from, date_to, multi="Y", nation="F"):
    """페이지당 100편 상한이 있어, 빈 페이지가 나올 때까지 순회해 전량을 모은다."""
    all_rows, page = [], 1
    while True:
        rows = _fetch_page(date_from, date_to, page, multi, nation)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break
        page += 1
        time.sleep(DELAY)
    return all_rows


def month_ranges(start, end):
    d = datetime.date(start.year, start.month, 1)
    while d <= end:
        nxt = datetime.date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
        yield d.strftime("%Y-%m-%d"), (min(nxt - datetime.timedelta(days=1), end)).strftime("%Y-%m-%d")
        d = nxt


def main():
    today = datetime.date.today()
    best = {}   # 영화명 → 최종 레코드(누적관객수 최댓값 기준)
    capped = []

    for f, t in month_ranges(START, today):
        try:
            rows = fetch(f, t)
        except Exception as e:
            print(f"  !! {f} 실패: {e}")
            time.sleep(3)
            continue
        for c in rows:
            # 0=순위 1=영화명 2=개봉일 3=매출액 4=점유율 5=누적매출 6=관객수 7=누적관객 8=스크린 9=상영횟수
            name, opendt, cum = c[1], c[2], _num(c[7])
            prev = best.get(name)
            if prev is None or cum > prev["_cum"]:
                best[name] = {"영화명": name, "개봉일": opendt, "누적관객수": cum,
                              "누적매출액": _num(c[5]), "스크린수": _num(c[8]),
                              "상영횟수": _num(c[9]), "관측월": f[:7], "_cum": cum}
        print(f"  {f[:7]}: {len(rows):3d}편 (누적 {len(best)}편)")
        time.sleep(DELAY)

    recs = sorted(best.values(), key=lambda r: -r["_cum"])
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=HEADER)
        w.writeheader()
        for r in recs:
            w.writerow({k: r[k] for k in HEADER})

    print(f"\n완료: {len(recs)}편 → {OUT}")
    if capped:
        print(f"!! 100편 상한에 닿은 월(누락 가능): {', '.join(capped)}")


if __name__ == "__main__":
    main()
