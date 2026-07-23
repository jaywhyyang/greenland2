# -*- coding: utf-8 -*-
"""
한국영화 두 세그먼트 수집
  → korean_final.csv     (2024-2026 개봉 한국 국적 영화 전체)
  → krindie_final.csv    (그중 KOBIS '다양성영화' 분류 = 독립영화)

정의 (홈초이스 최수현 리더 요청, 2026-07 확정):
  · 한국영화 전체 : 2024-01-01 이후 개봉, 대표국적 한국
  · 독립영화      : 위 중 KOBIS 다양성영화 분류.
    (원래 기준은 '총제작비 20억 미만'이나 KOBIS에 총제작비가 없어 다양성 분류로 대체 합의)

데이터 출처는 외화 세그먼트와 동일:
  모집단·메타 : arthouse_meta.csv (엑셀 경로가 필터를 무시해 한국영화도 다 들어 있다)
  일별·좌석   : arthouse_daily.csv
  최종 누적   : 일별 관객 합산
  다양성 여부 : kr_diversity.csv (한국 × 다양성 명부, kobis_krdiv_scan.py 산출)

소규모 등록 건 정리: 외화와 동일하게 청불 소규모(스크린<20)만 뺀다.
한국영화 전체는 대작부터 소품까지 다 봐야 의미가 있으므로 스크린 하한은 두지 않는다.
"""
import os
import csv
import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(BASE, "arthouse_meta.csv")
DAY = os.path.join(BASE, "arthouse_daily.csv")
DIV = os.path.join(BASE, "kr_diversity.csv")
RERE = os.path.join(BASE, "rerelease_suspects.csv")
OUT_ALL = os.path.join(BASE, "korean_final.csv")
OUT_INDIE = os.path.join(BASE, "krindie_final.csv")

FROM = "2024-01-01"
NDAY = 15
ERO_SCREEN_MAX = 20

HEADER = (["순위", "영화명", "개봉일", "등급", "장르", "감독", "배급사", "다양성",
           "개봉스크린수", "최대스크린수", "첫주관객", "첫주말관객", "2주누적",
           "최종누적관객", "배수", "주말집중도",
           "개봉일좌석수", "개봉일좌석판매율", "첫주말좌석수", "첫주말좌석판매율", "성적확정"]
          + [f"D{i}" for i in range(NDAY)])


def pdate(s):
    try:
        return datetime.date(*map(int, s.split("-")))
    except Exception:
        return None


def main():
    div = {r["영화명"] for r in csv.DictReader(open(DIV, encoding="utf-8-sig"))} \
        if os.path.exists(DIV) else set()

    daily = defaultdict(dict)
    for r in csv.DictReader(open(DAY, encoding="utf-8-sig")):
        d = pdate(r["날짜"])
        if d:
            daily[(r["영화명"], r["개봉일"])][d] = r
    EDGE = max(d for v in daily.values() for d in v)

    rows = []
    for x in csv.DictReader(open(META, encoding="utf-8-sig")):
        if x["대표국적"] != "한국" or x["개봉일"] < FROM:
            continue
        od = pdate(x["개봉일"])
        by = daily.get((x["영화명"], x["개봉일"]), {})
        if not by:
            continue
        cum = sum(int(r["관객수"] or 0) for r in by.values())
        if not cum:
            continue
        scr0 = int(by[od]["스크린수"] or 0) if od in by else 0
        if "청소년관람불가" in x["등급"] and scr0 < ERO_SCREEN_MAX:
            continue

        curve = [int(by[od + datetime.timedelta(days=j)]["관객수"] or 0)
                 if (od + datetime.timedelta(days=j)) in by else 0 for j in range(NDAY)]
        seat = lambda d: int(by[d]["좌석수"]) if d in by and by[d].get("좌석수") else 0
        aud = lambda d: int(by[d]["관객수"] or 0) if d in by else 0

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

        rows.append({
            "영화명": x["영화명"], "개봉일": x["개봉일"], "등급": x["등급"],
            "장르": x["장르"], "감독": x["감독"], "배급사": x["배급사"],
            "다양성": "Y" if x["영화명"] in div else "",
            "개봉스크린수": scr0,
            "최대스크린수": max([int(r["스크린수"] or 0) for r in by.values()] or [0]),
            "첫주관객": wk1, "첫주말관객": wa, "2주누적": sum(curve[:14]),
            "최종누적관객": cum,
            "배수": round(cum / wk1, 2) if wk1 else "",
            "주말집중도": round(100 * wa / wk1, 1) if wk1 else "",
            "개봉일좌석수": s0 or "",
            "개봉일좌석판매율": round(100 * a0 / s0, 1) if s0 else "",
            "첫주말좌석수": ws or "",
            "첫주말좌석판매율": round(100 * wa / ws, 1) if ws else "",
            "성적확정": "확정" if (max(by) < EDGE or (EDGE - od).days >= 28) else "",
            **{f"D{j}": curve[j] for j in range(NDAY)},
        })

    def write(path, data):
        data = sorted(data, key=lambda r: -r["최종누적관객"])
        for i, r in enumerate(data, 1):
            r["순위"] = i
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            w.writeheader()
            w.writerows(data)
        return len(data)

    n_all = write(OUT_ALL, rows)
    indie = [r for r in rows if r["다양성"] == "Y"]
    n_indie = write(OUT_INDIE, indie)
    print(f"한국영화 전체 {n_all}편 → {OUT_ALL}")
    print(f"  그중 독립(다양성) {n_indie}편 → {OUT_INDIE}")


if __name__ == "__main__":
    main()
