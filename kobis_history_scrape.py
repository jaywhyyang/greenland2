# -*- coding: utf-8 -*-
"""
KOBIS 일별 박스오피스 전량 수집 (2023-01-01 ~ 오늘) → history_boxoffice.csv.
영화별 1일차~종영 누적곡선 재구성용 대형 데이터셋. HTML 스크래핑(좌판/좌석 포함).
- 날짜별 박스오피스 + 좌석 페이지를 병합(개봉일+관객수 매칭)해 상위 ~50편 적재
- 이미 수집한 날짜는 건너뜀(resume 가능), 젠틀 딜레이로 차단 회피
- 백그라운드로 장시간 실행. 진행상황은 history_scrape.log 에 기록.
"""
import os
import csv
import time
import datetime
import kobis_boxoffice_daily as K

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "history_boxoffice.csv")
LOG = os.path.join(BASE, "history_scrape.log")
START = datetime.date(2023, 1, 1)
DELAY = 0.6  # 쿼리 사이 딜레이(초)
HEADER = ["날짜", "순위", "영화명", "개봉일", "관객수", "누적관객수",
          "매출액", "누적매출액", "스크린수", "상영횟수", "좌석수", "좌석판매율", "좌석점유율"]


def _log(msg):
    line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _done_dates():
    if not os.path.exists(OUT):
        return set()
    with open(OUT, encoding="utf-8-sig", newline="") as f:
        return {r["날짜"] for r in csv.DictReader(f) if r.get("날짜")}


def main():
    done = _done_dates()
    if not os.path.exists(OUT):
        with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=HEADER).writeheader()
    today = datetime.date.today()
    d = START
    total = (today - START).days
    n_ok = 0
    _log(f"시작: {START}~{today} ({total}일), 이미 {len(done)}일 완료")
    while d <= today:
        ds = d.strftime("%Y-%m-%d")
        if ds in done:
            d += datetime.timedelta(days=1)
            continue
        try:
            recs = K.collect_all(ds, top_n=50)
            rows = []
            for r in recs:
                rows.append({h: r.get(h, "") for h in HEADER})
            with open(OUT, "a", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=HEADER)
                w.writerows(rows)
            n_ok += 1
            if n_ok % 20 == 0:
                _log(f"진행 {ds}: 누적 {n_ok}일 수집(영화 {len(rows)}편)")
        except Exception as e:
            _log(f"실패 {ds}: {str(e)[:80]}")
            time.sleep(3)  # 실패 시 좀 더 쉼
        time.sleep(DELAY)
        d += datetime.timedelta(days=1)
    _log(f"완료: 총 {n_ok}일 신규 수집")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
