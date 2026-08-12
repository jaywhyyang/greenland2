# -*- coding: utf-8 -*-
"""
vkobis(영진위 온라인상영관 통합전산망) TVOD 이용건수 전량 수집 → vkobis_annual.csv.

- 연간 전체 랭킹을 연도별로 1요청씩(최대 ~수천 행) 긁어 월별 이용건수까지 적재.
- 지표 = PPV(TVOD) 이용건수, 정액제(SVOD 구독) 제외. → 그린랜드1의 281,316과 동일 기준.
- 소급: 2012년부터 올해까지. 로그인 불필요. 응답은 HTML 테이블 → BeautifulSoup 파싱.
- movieIdntfr(예 FS20204008)도 함께 저장 → 이후 극장관객수/장르/국적 조인 키로 사용.

컬럼 매핑(연간 뷰): td0=순위, td1=영화명(+movieIdntfr), td2=개봉일(온라인/극장),
                    td3..td14=1~12월 이용건수, td15=연간합계.
진행상황은 vkobis_scrape.log 에 기록.
"""
import os
import re
import csv
import time
import datetime

import requests
from bs4 import BeautifulSoup

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "vkobis_annual.csv")
LOG = os.path.join(BASE, "vkobis_scrape.log")

URL = "https://www.vkobis.or.kr/boxoffice/selectBoxofficeList.do"
SM_ANNUAL = "5006040000"          # 연간 이용순위
START_YEAR = 2012                  # 연도 datepicker 최소값
LAST_INDEX = 5000                  # 한 요청당 최대 순위(롱테일 전부)
DELAY = 1.0                        # 연도 간 딜레이(초)

MONTHS = [f"m{m:02d}" for m in range(1, 13)]
HEADER = (["year", "rank", "movie_id", "title_ko", "title_en",
           "online_open", "theater_open"] + MONTHS + ["year_total"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.vkobis.or.kr/boxoffice/selectBoxofficeDayList.do",
}


def _log(msg):
    line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _num(s):
    """'63,067' -> 63067, '-'/'' -> 0"""
    s = (s or "").replace(",", "").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else 0


def _dates(cell_text):
    """'2020.11.03 (2020.09.29)' -> ('2020-11-03', '2020-09-29')"""
    ds = re.findall(r"(\d{4})\.(\d{2})\.(\d{2})", cell_text or "")
    def fmt(t):
        return f"{t[0]}-{t[1]}-{t[2]}"
    online = fmt(ds[0]) if len(ds) >= 1 else ""
    theater = fmt(ds[1]) if len(ds) >= 2 else ""
    return online, theater


def fetch_year(session, year):
    body = {
        "smSeCd": SM_ANNUAL,
        "searchCondition": "",
        "searchStartDate": f"{year}0101",
        "firstIndex": 1,
        "lastIndex": LAST_INDEX,
    }
    r = session.post(URL, data=body, headers=HEADERS, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.select_one("#boxList table") or soup.select_one(".tbl_boxoffice")
    rows = []
    if not table:
        return rows
    body_el = table.find("tbody") or table
    for tr in body_el.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 16:
            continue  # '조회된 영화 없음.' 등 스킵
        txt = [td.get_text(" ", strip=True) for td in tds]
        rank = _num(re.match(r"\s*(\d+)", txt[0]).group(1)) if re.match(r"\s*(\d+)", txt[0]) else 0
        # movie id
        mid = ""
        a = tds[1].find("a", href=True)
        if a:
            m = re.search(r"fn_comMovieDetail\('([^']+)'\)", a["href"])
            if m:
                mid = m.group(1)
        # 국문/영문 제목
        ko = tds[1].select_one("span.dotdot:not(.eng)")
        en = tds[1].select_one("span.eng")
        title_ko = ko.get_text(strip=True) if ko else ""
        title_en = en.get_text(strip=True) if en else ""
        online, theater = _dates(txt[2])
        months = [_num(txt[3 + i]) for i in range(12)]
        year_total = _num(txt[15]) if len(txt) > 15 else sum(months)
        rec = {
            "year": year, "rank": rank, "movie_id": mid,
            "title_ko": title_ko, "title_en": title_en,
            "online_open": online, "theater_open": theater,
            "year_total": year_total,
        }
        for i, mk in enumerate(MONTHS):
            rec[mk] = months[i]
        rows.append(rec)
    return rows


def main():
    session = requests.Session()
    # 세션 쿠키 확보(첫 GET)
    try:
        session.get("https://www.vkobis.or.kr/boxoffice/selectBoxofficeDayList.do",
                    headers={"User-Agent": HEADERS["User-Agent"]}, timeout=30)
    except Exception as e:
        _log(f"세션 초기화 경고: {str(e)[:60]}")

    this_year = datetime.date.today().year
    years = list(range(START_YEAR, this_year + 1))
    _log(f"시작: {years[0]}~{years[-1]} ({len(years)}개 연도)")

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        grand = 0
        for y in years:
            try:
                rows = fetch_year(session, y)
                w.writerows(rows)
                f.flush()
                grand += len(rows)
                _log(f"  {y}: {len(rows)}행 (누적 {grand})")
            except Exception as e:
                _log(f"  {y}: 실패 {str(e)[:80]}")
                time.sleep(3)
            time.sleep(DELAY)
    _log(f"완료: 총 {grand}행 → {os.path.basename(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
