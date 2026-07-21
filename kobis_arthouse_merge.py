# -*- coding: utf-8 -*-
"""
영화별 1행 최종 데이터셋 → arthouse_final.csv

입력과 각각의 역할:
  arthouse_enriched.csv : 기준 명부. 2024-01-01~2026-04-30 개봉 다양성 외화 394편.
                          (HTML 조회 경로 산출물 — 이쪽은 다양성/국적 필터가 정상 작동한다)
                          개봉스크린수, 최종누적관객, 누적매출액, 제작연도 보유.
  arthouse_daily.csv    : 일별 관객수 + 좌석수 (엑셀 경로).
  arthouse_meta.csv     : 배급사·제작사·등급·장르·감독·배우 (엑셀 경로).

■ 반드시 알아야 할 함정
  엑셀 내보내기(searchType=excelDaily / dmlMode=excel)는 sMultiMovieYn·sRepNationCd 필터를
  응답 헤더 문구에만 반영하고 실제 행에는 적용하지 않는다.
  실측: 2024-01-01~07 조회 시 헤더는 '독립·예술영화 / 외국'인데 215행 중 70행이 한국영화.
  → 그래서 엑셀 산출물은 모집단으로 쓰지 않고, 기준 명부에 조인해 붙이는 용도로만 쓴다.

산출 항목: 메타 + 배급사/직배여부 + 좌석 + D+0~D+14 곡선 + 파생지표
"""
import os
import csv
import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ENR = os.path.join(BASE, "arthouse_enriched.csv")
DAY = os.path.join(BASE, "arthouse_daily.csv")
META = os.path.join(BASE, "arthouse_meta.csv")
OUT = os.path.join(BASE, "arthouse_final.csv")

NDAY = 15   # D+0 ~ D+14

# 직배사(글로벌 스튜디오 한국지사) 판별 — 이 문자열이 배급사명에 있으면 직배로 본다
MAJORS = ("월트디즈니", "디즈니", "워너브러더스", "워너브라더스", "소니픽쳐스",
          "유니버설픽쳐스", "이십세기폭스", "파라마운트", "넷플릭스")

HEADER = (["순위", "영화명", "개봉일", "제작연도", "대표국적", "국적", "장르", "감독",
           "배급사", "직배여부", "등급", "개봉스크린수",
           "첫주관객", "2주누적", "최종누적관객", "배수", "스크린당관객",
           "14일좌석수", "평균좌석판매율", "좌석결손일", "누적매출액"]
          + [f"D{i}" for i in range(NDAY)])


def pdate(s):
    try:
        return datetime.date(*map(int, s.split("-")))
    except Exception:
        return None


def main():
    # 일별 데이터: (영화명, 개봉일) → {날짜: row}
    daily = defaultdict(dict)
    if os.path.exists(DAY):
        for r in csv.DictReader(open(DAY, encoding="utf-8-sig")):
            d = pdate(r["날짜"])
            if d:
                daily[(r["영화명"], r["개봉일"])][d] = r

    meta = {}
    if os.path.exists(META):
        for r in csv.DictReader(open(META, encoding="utf-8-sig")):
            meta.setdefault((r["영화명"], r["개봉일"]), r)

    out = []
    for e in csv.DictReader(open(ENR, encoding="utf-8-sig")):
        od = pdate(e["개봉일"])
        if not od:
            continue
        key = (e["영화명"], e["개봉일"])
        by_date = daily.get(key, {})
        m = meta.get(key, {})

        curve, seats, rates, miss = [], 0, [], 0
        for i in range(NDAY):
            row = by_date.get(od + datetime.timedelta(days=i))
            if not row:
                curve.append(0)
                miss += 1
                continue
            curve.append(int(row["관객수"] or 0))
            if row.get("좌석수"):
                seats += int(row["좌석수"])
                try:
                    rates.append(float((row.get("좌석판매율") or "").rstrip("%")))
                except ValueError:
                    pass
            else:
                miss += 1

        wk1 = sum(curve[:7]) or int(e["첫주관객"] or 0)
        wk2 = sum(curve[:14])
        cum = int(e["최종누적관객"] or 0)
        scr = int(e["개봉스크린수"] or 0)
        dist = m.get("배급사", "")

        out.append({
            "영화명": e["영화명"], "개봉일": e["개봉일"], "제작연도": e["제작연도"],
            "대표국적": m.get("대표국적", "") or e.get("제작국가", ""),
            "국적": m.get("국적", ""), "장르": m.get("장르", "") or e.get("장르", ""),
            "감독": m.get("감독", "") or e.get("감독", ""),
            "배급사": dist,
            "직배여부": "직배" if any(k in dist for k in MAJORS) else ("비직배" if dist else ""),
            "등급": m.get("등급", ""),
            "개봉스크린수": scr, "첫주관객": wk1, "2주누적": wk2,
            "최종누적관객": cum, "누적매출액": int(e["누적매출액"] or 0),
            "배수": round(cum / wk1, 2) if wk1 else "",
            "스크린당관객": round(cum / scr) if scr else "",
            "14일좌석수": seats or "", "좌석결손일": miss,
            "평균좌석판매율": round(sum(rates) / len(rates), 1) if rates else "",
            **{f"D{i}": curve[i] for i in range(NDAY)},
        })

    out.sort(key=lambda r: -r["최종누적관객"])
    for i, r in enumerate(out, 1):
        r["순위"] = i
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(out)

    nc = sum(1 for r in out if r["D0"] or r["D1"])
    ns = sum(1 for r in out if r["14일좌석수"])
    nd = sum(1 for r in out if r["배급사"])
    print(f"완료: {len(out)}편 → {OUT}")
    print(f"  일별곡선 {nc}편 / 좌석 {ns}편 / 배급사 {nd}편")


if __name__ == "__main__":
    main()
