# -*- coding: utf-8 -*-
"""
비직배 상업 외화 세그먼트 수집 → commercial_final.csv

■ 세그먼트를 '여집합'으로 잡는 이유
  KOBIS 다양성영화 분류로 상업/예술을 가르면 틀린다. 실측으로 확인된 반례:
    · 서브스턴스(56만) 콘클라베(33만) 8번 출구(45만) → 다양성 분류인데 상업 흥행작
    · 너자 2(중국 역대 흥행 1위) → 다양성 분류
  그래서 분류 플래그로 새 경계를 긋지 않고, 이미 만든 세 세그먼트의 나머지로 정의한다.

    비직배 상업 외화 = 외국 × 비직배
                     − 아트하우스(다양성 명부 arthouse_foreign.csv)
                     − 어린이 애니(kidsani_final.csv)
                     − 일본 애니(팬덤 극장판·대형 IP)
                     − 재개봉·구작

  이러면 경계를 새로 정의할 필요가 없고, 세 페이지를 합치면 비직배 수입 시장이 빠짐없이 덮인다.
  서브스턴스·콘클라베처럼 다양성으로 잡힌 상업 성공작은 아트하우스에 그대로 둔다.
  결과(관객수)로 분류를 정하면 개봉 전 판단 도구로서 순환논리가 되기 때문이다.

■ 데이터 출처
  모집단·메타 : arthouse_meta.csv (엑셀 경로가 필터를 무시해 전 장르·전 국적이 들어 있다)
  일별·좌석   : arthouse_daily.csv
  최종 누적   : 일별 관객 합산. findPeriodBoxOfficeList 는 sMovName 을 무시하고
                해당 기간 상위 100편만 돌려주므로 소형작이 잡히지 않는다.
                합산값은 구간 안에서 종영한 작품에서 KOBIS 값과 오차 0.0%로 일치함을 확인했다.
  재개봉 판별 : rerelease_suspects.csv (제작연도가 옛날인데 최근 개봉한 외국영화)
"""
import os
import csv
import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(BASE, "arthouse_meta.csv")
DAY = os.path.join(BASE, "arthouse_daily.csv")
ARTLIST = os.path.join(BASE, "arthouse_foreign.csv")
KIDS = os.path.join(BASE, "kidsani_final.csv")
RERE = os.path.join(BASE, "rerelease_suspects.csv")
OUT = os.path.join(BASE, "commercial_final.csv")

FROM = "2024-01-01"
NDAY = 15
RERELEASE_GAP = 6

# 실질 극장 개봉만 남기기 위한 최소 규모.
# KOBIS 에는 상영관 1개·관객 한 자릿수로 등록만 된 건이 대량 있다.
# 실측: 정리 전 2,248편 중 2,020편이 청소년관람불가였고 그중 1,997편이 스크린 20개 미만이었다
# (중앙값 1명). 아트하우스와 같은 청불 규칙에 최소 편성 규모를 더해 걸러낸다.
ERO_SCREEN_MAX = 20
MIN_SCREEN = 30

MAJORS = ("월트디즈니", "디즈니", "워너브러더스", "소니픽쳐스",
          "유니버설픽쳐스", "이십세기폭스", "파라마운트")

# 국내 대기업 배급사가 붙은 건 대부분 글로벌 스튜디오 배급대행(아웃풋 딜)이라
# MG를 주고 사오는 수입작이 아니다. 실질 직배로 보고 함께 제외한다.
BIG_KR = ("롯데", "씨제이", "CJ", "넥스트엔터", "메가박스")

HEADER = (["순위", "영화명", "개봉일", "대표국적", "등급", "장르", "감독", "배급사",
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
    art = {r["영화명"] for r in csv.DictReader(open(ARTLIST, encoding="utf-8-sig"))}
    kids = {r["영화명"] for r in csv.DictReader(open(KIDS, encoding="utf-8-sig"))} \
        if os.path.exists(KIDS) else set()
    rere = {r["영화명"]: int(r["제작연도"]) for r in csv.DictReader(open(RERE, encoding="utf-8-sig"))
            if r["제작연도"].isdigit()} if os.path.exists(RERE) else {}

    daily = defaultdict(dict)
    for r in csv.DictReader(open(DAY, encoding="utf-8-sig")):
        d = pdate(r["날짜"])
        if d:
            daily[(r["영화명"], r["개봉일"])][d] = r
    EDGE = max(d for v in daily.values() for d in v)

    films, skip = [], defaultdict(int)
    for x in csv.DictReader(open(META, encoding="utf-8-sig")):
        nm = x["영화명"]
        if x["대표국적"] in ("한국", ""):
            skip["한국"] += 1; continue
        if x["개봉일"] < FROM:
            skip["기간외"] += 1; continue
        if any(k in x["배급사"] for k in MAJORS):
            skip["직배"] += 1; continue
        if any(k in x["배급사"] for k in BIG_KR):
            skip["대형배급대행"] += 1; continue
        if nm in art:
            skip["아트하우스"] += 1; continue
        if nm in kids:
            skip["어린이애니"] += 1; continue
        if x["대표국적"] == "일본" and "애니메이션" in x["장르"]:
            skip["일본애니"] += 1; continue
        py = rere.get(nm)
        if py and int(x["개봉일"][:4]) - py >= RERELEASE_GAP:
            skip["재개봉"] += 1; continue
        films.append(x)

    print("제외 내역:", dict(skip))
    print(f"대상 {len(films)}편")

    out = []
    for x in films:
        od = pdate(x["개봉일"])
        by = daily.get((x["영화명"], x["개봉일"]), {})
        if not by:
            continue
        cum = sum(int(r["관객수"] or 0) for r in by.values())
        if not cum:
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
        scr0 = int(by[od]["스크린수"] or 0) if od in by else 0

        out.append({
            "영화명": x["영화명"], "개봉일": x["개봉일"], "대표국적": x["대표국적"],
            "등급": x["등급"], "장르": x["장르"], "감독": x["감독"], "배급사": x["배급사"],
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
            # 수집 종료일까지 상영이 이어져도 개봉 4주가 지났으면 성적이 사실상 굳은 것으로 본다.
            # (마지막 며칠은 소수 상영관의 꼬리라 누적을 거의 움직이지 않는다)
            "성적확정": "확정" if (max(by) < EDGE or (EDGE - od).days >= 28) else "",
            **{f"D{j}": curve[j] for j in range(NDAY)},
        })

    kept = []
    for r in out:
        if "청소년관람불가" in r["등급"] and r["개봉스크린수"] < ERO_SCREEN_MAX:
            skip["청불소규모"] += 1
            continue
        if r["개봉스크린수"] < MIN_SCREEN:
            skip["소규모편성"] += 1
            continue
        kept.append(r)
    print(f"  본편 정리: {len(out)}편 → {len(kept)}편 "
          f"(청불소규모 {skip['청불소규모']}, 스크린 {MIN_SCREEN}개 미만 {skip['소규모편성']})")
    out = kept

    out.sort(key=lambda r: -r["최종누적관객"])
    for i, r in enumerate(out, 1):
        r["순위"] = i
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(out)
    fin = sum(1 for r in out if r["성적확정"] == "확정")
    print(f"\n완료: {len(out)}편 → {OUT} (성적 확정 {fin}편)")


if __name__ == "__main__":
    main()
