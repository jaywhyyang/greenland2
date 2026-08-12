# -*- coding: utf-8 -*-
"""
vkobis_films.csv 상위 작품에 메타(장르·국적·영화구분) + 극장 누적 관객수 조인 → vkobis_enriched.csv.

- 소스: 상세 fragment(장르/국적/영화구분) + JSON `selectMovieAccumulateCnt.do`(극장관객수).
- 대상: lifetime_vod 상위 TOP_N (comp 후보 전부 포함). movie_id 있는 행만.
- resume 가능(이미 처리한 movie_id 스킵), 젠틀 딜레이.

selectMovieAccumulateCnt.do → {realIssuCnt=극장누적관객수, useCo=온라인누적, seatCnt=좌석수, totalCnt=합}
"""
import os
import re
import csv
import json
import time
import datetime

import requests
from bs4 import BeautifulSoup

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "vkobis_films.csv")
OUT = os.path.join(BASE, "vkobis_enriched.csv")
LOG = os.path.join(BASE, "vkobis_enrich.log")

DETAIL = "https://www.vkobis.or.kr/movie/selectMovieInfoDetailAjax.do"
ACCUM = "https://www.vkobis.or.kr/movie/selectMovieAccumulateCnt.do"
TOP_LIFETIME = 1500          # 생애 상위(역대 대형작: 장르/전환율 트렌드용)
RECENT_YEARS = {"2021", "2022", "2023", "2024", "2025", "2026"}  # 붕괴장 이후 시장
RECENT_MIN_VOD = 3000        # 최근작 중 유의미 볼륨 하한(그린랜드2급 소형 comp 포함)
DELAY = 0.4

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HDR = {"User-Agent": UA,
       "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
       "X-Requested-With": "XMLHttpRequest",
       "Referer": "https://www.vkobis.or.kr/"}

HEADER = ["movie_id", "title_ko", "title_en", "gubun", "genre", "nation",
          "theater_admissions", "online_cumulative", "seat_cnt",
          "lifetime_vod", "first_year_vod", "online_open", "theater_open"]


def _log(msg):
    line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_meta(html):
    """상세 fragment에서 영화구분/장르/국적 추출."""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    gubun = ""
    mg = re.search(r"(독립[·\-]?\s?예술영화|일반영화)", text)
    if mg:
        gubun = mg.group(1).replace(" ", "")
    genre = ""
    # 영화구분 다음 ~ runtime(분) 사이 = 장르
    gg = re.search(r"(?:독립[·\-]?\s?예술영화|일반영화)\s+([가-힣A-Za-z/,·\s]+?)\s+\d+\s*분", text)
    if gg:
        genre = gg.group(1).strip().replace(" ", "")
    nation = ""
    # 구조: ... [국내] <등급> <국적> (A.K.A <별칭>)? 코드 <숫자>
    # rating(관람가/관람불가/상영가/등급외) 앵커 뒤 토큰 = 국적
    nn = re.search(r"(?:관람가|관람불가|상영가|등급외)\s+([가-힣A-Za-z,·]+?)\s+(?:A\.K\.A|코드)", text)
    if not nn:  # 등급 표기가 특이한 경우: A.K.A/코드 직전 토큰
        nn = re.search(r"([가-힣A-Za-z,·]+?)\s+(?:A\.K\.A|코드)\s", text)
    if nn:
        nation = nn.group(1).strip()
    return gubun, genre, nation


def enrich_one(session, mid):
    html = session.post(DETAIL, data={"movieIdntfr": mid}, headers=HDR, timeout=30).text
    gubun, genre, nation = parse_meta(html)
    theater = online = seat = ""
    try:
        j = json.loads(session.post(ACCUM, data={"movieIdntfr": mid}, headers=HDR, timeout=30).text)
        rm = j.get("resultMap", {}) or {}
        theater = rm.get("realIssuCnt", "")
        online = rm.get("useCo", "")
        seat = rm.get("seatCnt", "")
    except Exception:
        pass
    return gubun, genre, nation, theater, online, seat


def _done_ids():
    if not os.path.exists(OUT):
        return set()
    with open(OUT, encoding="utf-8-sig") as f:
        return {r["movie_id"] for r in csv.DictReader(f) if r.get("movie_id")}


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        allf = [r for r in csv.DictReader(f) if r.get("movie_id", "").startswith("FS")]
    # 대상 = (생애 상위 TOP_LIFETIME) ∪ (최근 개봉 + 유의미 볼륨) — lifetime desc 순 유지
    top = allf[:TOP_LIFETIME]
    recent = [r for r in allf
              if (r.get("online_open", "")[:4] in RECENT_YEARS
                  or r.get("theater_open", "")[:4] in RECENT_YEARS)
              and int(r.get("lifetime_vod") or 0) >= RECENT_MIN_VOD]
    seen, films = set(), []
    for r in top + recent:
        mid = r["movie_id"]
        if mid not in seen:
            seen.add(mid)
            films.append(r)
    done = _done_ids()
    new_file = not os.path.exists(OUT)
    session = requests.Session()
    try:
        session.get("https://www.vkobis.or.kr/", headers={"User-Agent": UA}, timeout=20)
    except Exception:
        pass
    f = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=HEADER)
    if new_file:
        w.writeheader()
    _log(f"시작: 대상 {len(films)}편, 이미 {len(done)}편 완료")
    n = 0
    for r in films:
        mid = r["movie_id"]
        if mid in done:
            continue
        try:
            gubun, genre, nation, theater, online, seat = enrich_one(session, mid)
            w.writerow({
                "movie_id": mid, "title_ko": r["title_ko"], "title_en": r["title_en"],
                "gubun": gubun, "genre": genre, "nation": nation,
                "theater_admissions": theater, "online_cumulative": online, "seat_cnt": seat,
                "lifetime_vod": r["lifetime_vod"], "first_year_vod": r["first_year_vod"],
                "online_open": r["online_open"], "theater_open": r["theater_open"],
            })
            f.flush()
            n += 1
            if n % 50 == 0:
                _log(f"  진행 {n}편 (마지막 {r['title_ko']} / {nation} {genre} / 극장 {theater})")
        except Exception as e:
            _log(f"  실패 {mid} {r['title_ko']}: {str(e)[:60]}")
            time.sleep(2)
        time.sleep(DELAY)
    f.close()
    _log(f"완료: 신규 {n}편 → {os.path.basename(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
