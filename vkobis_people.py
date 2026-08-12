# -*- coding: utf-8 -*-
"""
vkobis_enriched.csv 작품들의 감독·주연 수집 → vkobis_people.csv.
배우/감독별 VOD 프리미엄(장르로 못 잡는 요인) 모델링용.
selectMovieInfoPeopleDetailAjax.do: span.name=이름, span.role=[주연]/[조연]…, 감독은 role 없음(첫 name).
"""
import os
import csv
import time
import datetime
import requests
from bs4 import BeautifulSoup

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "vkobis_enriched.csv")
OUT = os.path.join(BASE, "vkobis_people.csv")
LOG = os.path.join(BASE, "vkobis_people.log")
EP = "https://www.vkobis.or.kr/movie/selectMovieInfoPeopleDetailAjax.do"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
       "X-Requested-With": "XMLHttpRequest",
       "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
HEADER = ["movie_id", "director", "leads"]


def _log(m):
    line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {m}"
    print(line)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    director = ""
    leads = []
    for a in soup.select("a"):
        nm = a.select_one("span.name")
        if not nm:
            continue
        name = nm.get_text(strip=True)
        role = a.select_one("span.role")
        if role and "주연" in role.get_text():
            leads.append(name)
        elif not role and not director:
            director = name          # 첫 role-없는 name = 감독
    return director, leads[:3]


def done_ids():
    if not os.path.exists(OUT):
        return set()
    return {r["movie_id"] for r in csv.DictReader(open(OUT, encoding="utf-8-sig"))}


def main():
    ids = [r["movie_id"] for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))
           if r["movie_id"].startswith("FS")]
    done = done_ids()
    new = not os.path.exists(OUT)
    s = requests.Session()
    s.get("https://www.vkobis.or.kr/", headers={"User-Agent": HDR["User-Agent"]}, timeout=20)
    f = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=HEADER)
    if new:
        w.writeheader()
    _log(f"시작: {len(ids)}편, 완료 {len(done)}")
    n = 0
    for mid in ids:
        if mid in done:
            continue
        try:
            html = s.post(EP, data={"movieIdntfr": mid}, headers=HDR, timeout=30).text
            d, leads = parse(html)
            w.writerow({"movie_id": mid, "director": d, "leads": "|".join(leads)})
            f.flush()
            n += 1
            if n % 100 == 0:
                _log(f"  {n}편 (마지막 {d} / {leads})")
        except Exception as e:
            _log(f"  실패 {mid}: {str(e)[:50]}")
            time.sleep(2)
        time.sleep(0.3)
    f.close()
    _log(f"완료: 신규 {n}편")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
