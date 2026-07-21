# -*- coding: utf-8 -*-
"""
어린이 애니메이션(비직배 수입) 세그먼트 수집 → kidsani_final.csv

세그먼트 정의 — 아트하우스 분석과 같은 틀을 쓰되 대상만 바꾼다.
  장르에 '애니메이션' 포함 × 외국영화 × 비직배
  × 일본 제외 (귀멸·블루록 등 팬덤 극장판과 도라에몽·짱구 등 대형 IP가 섞여
    '어린이 애니'로 묶이지 않는다. 국적으로 잘라내는 편이 정확하다)
  × 대형 배급사(롯데·CJ·NEW·메가박스) 경유작 제외 (메이저 IP는 규모가 달라 중앙값을 왜곡)
  × 작가주의·성인 애니 제외 (EXCLUDE 목록)
  × 2024-01-01 이후 개봉

메타·일별관객·좌석은 아트하우스 수집분(arthouse_meta / arthouse_daily / arthouse_seats)을
그대로 재사용한다. 엑셀 경로가 다양성·국적 필터를 무시한 덕에 전 장르가 이미 들어와 있다.
여기서 새로 받는 것은 '최종 누적관객'뿐이다.
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
META = os.path.join(BASE, "arthouse_meta.csv")
DAY = os.path.join(BASE, "arthouse_daily.csv")
OUT = os.path.join(BASE, "kidsani_final.csv")
PB = "https://www.kobis.or.kr/kobis/business/stat/boxs/findPeriodBoxOfficeList.do"

FROM = "2024-01-01"
DELAY = 0.6
NDAY = 15

MAJORS = ("월트디즈니", "디즈니", "워너브러더스", "소니픽쳐스",
          "유니버설픽쳐스", "이십세기폭스", "파라마운트")
BIG_KR = ("롯데", "씨제이", "넥스트엔터", "메가박스")

# 작가주의·성인 취향 애니 — 어린이 관객 대상이 아니라 세그먼트에서 뺀다
EXCLUDE = {
    "로봇 드림", "플로우", "달팽이의 회고록", "그들은 피아노 연주자를 쐈다",
    "아르코", "술타나의 꿈", "리틀 아멜리", "스퍼마게돈: 사정의 날",
    "너자 2", "월레스와 그로밋 더 클래식 컬렉션", "아웃 오브 네스트",
}

HEADER = (["순위", "영화명", "개봉일", "대표국적", "등급", "장르", "감독", "배급사",
           "개봉스크린수", "첫주관객", "첫주말관객", "2주누적", "최종누적관객",
           "배수", "주말집중도", "개봉일좌석수", "개봉일좌석판매율",
           "첫주말좌석수", "첫주말좌석판매율", "첫주말일수", "성적확정"]
          + [f"D{i}" for i in range(NDAY)])


def _clean(x):
    t = re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").replace("&#039;", "'").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def _num(s):
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else 0


def pdate(s):
    try:
        return datetime.date(*map(int, s.split("-")))
    except Exception:
        return None


def final_audience_unused(name, opendt, today):
    """[사용 안 함] 개봉일~오늘 구간 조회.

    이 엔드포인트는 sMovName 을 무시하고 그 기간의 상위 100편만 돌려준다.
    기간이 길수록 소형작은 순위에 밀려 아예 잡히지 않는다(51편 중 6편만 매칭).
    → 최종 누적은 arthouse_daily.csv 의 일별 관객을 합산해 구한다.
      검증: 수집 구간 안에서 종영한 5편이 KOBIS 값과 오차 0.0%로 일치했다.
    """
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", PB)]
    g = op.open(PB, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', g)
    data = urllib.parse.urlencode({
        "CSRFToken": m.group(1) if m else "", "loadEnd": "0", "searchType": "search",
        "sSearchFrom": opendt, "sSearchTo": today,
        "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": "",
        "sMovName": name, "sMovLang": "ko", "curPage": "1",
    }).encode()
    h = op.open(urllib.request.Request(PB, data=data), timeout=30).read().decode("utf-8", "replace")
    for mb in re.finditer(r"<tbody[^>]*>(.*?)</tbody>", h, re.S):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", mb.group(1), re.S):
            c = [_clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(c) >= 10 and c[1] == name:
                return _num(c[7]), _num(c[8])   # 누적관객수, 스크린수
        break
    return 0, 0


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")

    films = []
    for x in csv.DictReader(open(META, encoding="utf-8-sig")):
        if "애니메이션" not in x["장르"]:
            continue
        if x["대표국적"] in ("한국", "일본", ""):
            continue
        if x["개봉일"] < FROM:
            continue
        d = x["배급사"]
        if any(k in d for k in MAJORS) or any(k in d for k in BIG_KR):
            continue
        if x["영화명"] in EXCLUDE:
            continue
        films.append(x)
    films.sort(key=lambda x: x["개봉일"])
    print(f"대상 {len(films)}편")

    daily = defaultdict(dict)
    for r in csv.DictReader(open(DAY, encoding="utf-8-sig")):
        d = pdate(r["날짜"])
        if d:
            daily[(r["영화명"], r["개봉일"])][d] = r

    # 일별 데이터의 마지막 날짜. 여기까지 상영이 이어진 작품은 성적이 확정되지 않았다.
    EDGE = max(d for v in daily.values() for d in v)

    out = []
    for i, x in enumerate(films, 1):
        od = pdate(x["개봉일"])
        by = daily.get((x["영화명"], x["개봉일"]), {})
        cum = sum(int(r["관객수"] or 0) for r in by.values())
        scr = max([int(r["스크린수"] or 0) for r in by.values()] or [0])
        last = max(by) if by else None
        # 개봉 4주가 지났으면 수집 종료일까지 상영 중이어도 성적이 굳은 것으로 본다
        running = bool(last and last >= EDGE and (EDGE - od).days < 28)
        curve = [int(by[od + datetime.timedelta(days=j)]["관객수"] or 0)
                 if (od + datetime.timedelta(days=j)) in by else 0 for j in range(NDAY)]

        def seat(d):
            r = by.get(d)
            return int(r["좌석수"]) if r and r.get("좌석수") else 0

        def aud(d):
            r = by.get(d)
            return int(r["관객수"] or 0) if r else 0

        wk = []
        for j in range(NDAY):
            d = od + datetime.timedelta(days=j)
            if d.weekday() in (4, 5, 6):
                wk.append(d)
            elif wk:
                break
        ws, wa = sum(seat(d) for d in wk), sum(aud(d) for d in wk)
        s0, a0 = seat(od), aud(od)
        wk1 = sum(curve[:7])

        out.append({
            "영화명": x["영화명"], "개봉일": x["개봉일"], "대표국적": x["대표국적"],
            "등급": x["등급"], "장르": x["장르"], "감독": x["감독"], "배급사": x["배급사"],
            "개봉스크린수": scr, "첫주관객": wk1, "첫주말관객": wa,
            "성적확정": "" if running else "확정",
            "2주누적": sum(curve[:14]), "최종누적관객": cum,
            "배수": round(cum / wk1, 2) if wk1 else "",
            # 주말 집중도 = 첫 주말 관객 ÷ 첫주 관객. '주말에 꽉 찬다'는 통설의 핵심 지표
            "주말집중도": round(100 * wa / wk1, 1) if wk1 else "",
            "개봉일좌석수": s0 or "",
            "개봉일좌석판매율": round(100 * a0 / s0, 1) if s0 else "",
            "첫주말좌석수": ws or "",
            "첫주말좌석판매율": round(100 * wa / ws, 1) if ws else "",
            "첫주말일수": len(wk),
            **{f"D{j}": curve[j] for j in range(NDAY)},
        })


    out.sort(key=lambda r: -r["최종누적관객"])
    for i, r in enumerate(out, 1):
        r["순위"] = i
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(out)
    ok = sum(1 for r in out if r["최종누적관객"])
    print(f"\n완료: {len(out)}편 → {OUT} (누적관객 확보 {ok}편)")


if __name__ == "__main__":
    main()
