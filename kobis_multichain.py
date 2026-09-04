# -*- coding: utf-8 -*-
"""
체인영화관별(멀티체인) 상영현황 전수 수집 → multichain_weekly.csv

■ 왜 이 소스인가
  KOBIS 「체인영화관별 상영현황」(findDailyMultichainList.do)은 영화 × 체인(CGV·롯데시네마·
  메가박스·씨네Q) × 구분(직영/위탁/계) 중첩표로 스크린수·상영횟수를 준다.
  → 특정 체인에만 편성된 작품(=단독개봉)을 실측으로 판별할 수 있는 유일한 공개 소스.
  배급사명이나 스크린수 지문 같은 프록시가 필요 없다.

■ 표 구조 (셀 개수로 행 종류를 구분해야 함 — rowspan 때문에 컬럼이 밀린다)
    10칸: [순위, 영화명, 체인명, 구분, 상영횟수, 체인전체상영횟수, 상영점유율,
           스크린수, 체인전체스크린수, 스크린점유율]  ← 새 영화의 첫 행
     8칸: [체인명, 구분, +6]   ← 같은 영화의 다음 체인
     7칸: [구분, +6]           ← 같은 체인의 위탁/계 행
  '계' 행만 취하면 체인별 합계가 된다.

■ dmlMode=excel 은 행 상한이 없다(화면 조회는 잘림). 1주 조회 시 ~12,000행.
수집한 주는 건너뛰므로 중단 후 재실행(resume) 가능.
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
OUT = os.path.join(BASE, "multichain_weekly.csv")
LOG = os.path.join(BASE, "multichain.log")
URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyMultichainList.do"

START = datetime.date(2023, 1, 2)          # 월요일
END = datetime.date.today()
DELAY = 1.0
REFRESH_WEEKS = 2      # 진행 중인 주 + 직전 주는 항상 다시 받는다(확정 지연 대비)
HEADER = ["주시작", "주종료", "영화명", "체인", "스크린수", "상영횟수"]


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _clean(x):
    t = re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").replace("&amp;", "&").replace("&#039;", "'")
    return re.sub(r"\s+", " ", t).strip()


def _num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def fetch_week(d0, d1):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]
    h = op.open(URL, timeout=90).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"\s+value="([^"]+)"', h)
    p = {"loadEnd": "0", "dmlMode": "excel",
         "startDate": d0.strftime("%Y-%m-%d"), "endDate": d1.strftime("%Y-%m-%d"),
         "sMovName": "", "sMovLang": "ko", "CSRFToken": (m.group(1) if m else "")}
    body = op.open(urllib.request.Request(URL, data=urllib.parse.urlencode(p).encode()),
                   timeout=300).read().decode("utf-8", "replace")
    out, cur, chain = [], None, None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        c = [_clean(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(c) == 10 and c[0].isdigit():
            cur, chain, rest = c[1], c[2], c[3:]
        elif len(c) == 8 and cur:
            chain, rest = c[0], c[1:]
        elif len(c) == 7 and cur:
            rest = c[:]
        else:
            continue
        if rest[0] == "계":
            out.append({"주시작": d0.strftime("%Y-%m-%d"), "주종료": d1.strftime("%Y-%m-%d"),
                        "영화명": cur, "체인": chain,
                        "스크린수": _num(rest[4]), "상영횟수": _num(rest[1])})
    return out


def main():
    if not os.path.exists(OUT):
        with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=HEADER).writeheader()
    with open(OUT, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("주시작")]
    done = {r["주시작"] for r in rows}
    # 진행 중인 주는 '수집 완료'가 아니다. 주 키만 보고 건너뛰면 그 주가 끝날 때까지
    # 영영 갱신되지 않는다(상영중 작품의 최신 수치가 통째로 누락된다).
    # → 최근 REFRESH_WEEKS 주는 항상 다시 받고, 기존 행을 교체한다.
    fresh = sorted(done)[-REFRESH_WEEKS:] if done else []
    if fresh:
        done -= set(fresh)
        kept = [r for r in rows if r["주시작"] not in fresh]
        with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            w.writeheader()
            w.writerows(kept)
        log("최근 {0}주 재수집: {1}".format(len(fresh), ", ".join(fresh)))
    d = START
    while d <= END:
        d1 = min(d + datetime.timedelta(days=6), END)
        key = d.strftime("%Y-%m-%d")
        if key in done:
            d = d1 + datetime.timedelta(days=1)
            continue
        try:
            rows = fetch_week(d, d1)
        except Exception as e:
            log(f"  !! {key} 실패: {e}")
            time.sleep(5)
            continue
        with open(OUT, "a", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=HEADER).writerows(rows)
        log(f"{key}~{d1:%m-%d} {len(rows)}행 ({len(set(r['영화명'] for r in rows))}편)")
        d = d1 + datetime.timedelta(days=1)
        time.sleep(DELAY)
    log("완료")


if __name__ == "__main__":
    main()
