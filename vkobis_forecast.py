# -*- coding: utf-8 -*-
"""
그린랜드2 온라인(TVOD) 1년누적 예측 — 회귀 + 배우/감독 프리미엄 조건부 분포.

모델: log(VOD_1yr) = a + b·log(극장) + c·log(시장지수)   (외화 실사 액션, 완전1년)
      + 배우 프리미엄(주연 잔차, shrinkage) → 로그정규 예측분포 → 확률/분위.
스타 요인이 장르보다 큼: 제라드 버틀러 = 외화 주연 VOD 프리미엄 1위(×2.7).

출력 forecast.json: 회귀계수·배우랭킹·조건부분포(중앙/확률/분위)·comps·시장지수·양극화.
"""
import os
import csv
import json
import math
import statistics as st
from math import log, exp, erf, sqrt
from collections import defaultdict
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
G2_TH = 55446                 # 그린랜드2 극장 누적 관객수(최종)
G2_STAR = "제라드 버틀러"       # 주연(1편과 동일)
G2_DIRECTOR = "릭 로먼 워"      # 감독(1편과 동일)
TARGET_MKT_IDX = 20.6          # 예측대상 시장(2026말~2027초 가정, 2020=100)
G1_TH, G1_VOD1Y, G1_LIFE = 326130, 266688, 281316
ACT = {"액션", "SF", "어드벤처", "스릴러", "전쟁"}
COND_SD = 0.62                 # 조건부 스프레드(버틀러 일관성 0.32 + 시장/개별 불확실성)


def I(v):
    try:
        return int(v or 0)
    except ValueError:
        return 0


def load():
    films = {r["movie_id"]: r for r in csv.DictReader(open(os.path.join(BASE, "vkobis_films.csv"), encoding="utf-8-sig"))}
    en = {e["movie_id"]: e for e in csv.DictReader(open(os.path.join(BASE, "vkobis_enriched.csv"), encoding="utf-8-sig"))}
    try:
        ppl = {p["movie_id"]: p for p in csv.DictReader(open(os.path.join(BASE, "vkobis_people.csv"), encoding="utf-8-sig"))}
    except FileNotFoundError:
        ppl = {}
    mkt = {m["year"]: float(m["idx_2020"]) for m in csv.DictReader(open(os.path.join(BASE, "market_index.csv"), encoding="utf-8-sig"))}
    rows = []
    for mid, e in en.items():
        f = films.get(mid)
        if not f:
            continue
        th, fy, oo = I(e["theater_admissions"]), I(f["first_year_vod"]), f["online_open"][:4]
        if th < 5000 or fy <= 0 or oo not in mkt or f["first_year_note"]:
            continue
        foreign = ("한국" not in e["nation"] and e["nation"] != "")
        p = ppl.get(mid, {})
        rows.append({"t": e["title_ko"], "nat": e["nation"], "g": e["genre"],
                     "th": th, "fy": fy, "mk": mkt[oo], "R": fy / th, "oo": f["online_open"][:7],
                     "foreign": foreign, "act": any(x in e["genre"] for x in ACT),
                     "ani": "애니메이션" in e["genre"],
                     "dir": p.get("director", ""), "leads": (p.get("leads", "") or "").split("|")})
    return rows, mkt


def regress(rows):
    X = np.array([[1, log(r["th"]), log(r["mk"])] for r in rows])
    Y = np.array([log(r["fy"]) for r in rows])
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    pred = X @ beta
    resid = Y - pred
    r2 = 1 - (resid ** 2).sum() / ((Y - Y.mean()) ** 2).sum()
    return beta, resid, float(st.pstdev(resid)), float(r2)


def norm_p(x, mu, sd):
    return 1 - 0.5 * (1 + erf((log(x) - mu) / sd / sqrt(2)))


def main():
    rows, mkt = load()
    # 액션 baseline 회귀
    act = [r for r in rows if r["foreign"] and r["act"] and not r["ani"]]
    beta, _, sd_act, r2 = regress(act)
    a, b, c = beta
    base_mu = a + b * log(G2_TH) + c * log(TARGET_MKT_IDX)

    # 배우 프리미엄: 외화 전체(일반화) 잔차 → 주연별 shrinkage
    fbeta, _, _, _ = regress([r for r in rows if r["foreign"]])
    fa, fb, fc = fbeta
    fres = {}
    for r in rows:
        if r["foreign"]:
            fres[r["t"]] = log(r["fy"]) - (fa + fb * log(r["th"]) + fc * log(r["mk"]))
    actR, dirR = defaultdict(list), defaultdict(list)
    for r in rows:
        if not r["foreign"]:
            continue
        rv = fres[r["t"]]
        for L in r["leads"]:
            if L:
                actR[L].append(rv)
        if r["dir"]:
            dirR[r["dir"]].append(rv)

    def shrink(v, k=3):
        n = len(v)
        return (sum(v) / n) * n / (n + k), n
    star_prem = {nm: shrink(v) for nm, v in actR.items() if len(v) >= 3}
    ranking = sorted(star_prem.items(), key=lambda x: -x[1][0])
    star_rank = [{"name": nm, "mult": round(exp(pr), 2), "n": n} for nm, (pr, n) in ranking[:15]]
    bpr, bn = star_prem.get(G2_STAR, (log(2.0), 0))
    b_mult = exp(bpr)
    b_rank = 1 + sum(1 for _, (p2, _) in star_prem.items() if p2 > bpr)
    dpr, dn = shrink(dirR.get(G2_DIRECTOR, [0.0]))

    # ── 예측분포: 버틀러 소형~중형작(극장<25만) 직접환산 (그린랜드2 규모·시장으로) ──
    #  이유: 버틀러 평균 프리미엄(×2.7)은 대형작까지 섞여 소형극장 구간을 과소평가.
    #  그린랜드2는 극장 55k 소형작이라, 버틀러의 소형작 실적을 규모·시장 보정해 직접 준거로 삼음.
    genre_only = exp(base_mu)
    analog = []
    for r in rows:
        if r["foreign"] and G2_STAR in r["leads"] and 0 < r["th"] < 250000:
            # 규모·시장 보정은 계수 민감 → 액션·외화 두 회귀 계수 평균으로 안정화
            e1 = r["fy"] * (G2_TH / r["th"]) ** b * (TARGET_MKT_IDX / r["mk"]) ** c
            e2 = r["fy"] * (G2_TH / r["th"]) ** fb * (TARGET_MKT_IDX / r["mk"]) ** fc
            analog.append({"t": r["t"], "th": r["th"], "fy": r["fy"], "est": round((e1 + e2) / 2, -2)})
    analog.sort(key=lambda x: x["est"])
    aest = [x["est"] for x in analog]
    median = st.median(aest)
    mu = log(median)
    sd = max(0.46, st.pstdev([log(e) for e in aest]))   # 버틀러 일관성 반영(넓지 않음)
    probs = {str(x): round(norm_p(x, mu, sd) * 100) for x in
             (40000, 50000, 60000, 72000, 90000, 130000)}
    pct = {str(q): round(exp(mu + z * sd), -2) for q, z in
           [(10, -1.2816), (25, -0.6745), (50, 0), (75, 0.6745), (90, 1.2816)]}

    # 시장 타이밍 민감도(환산 중앙을 시장으로 스케일)
    timing = {str(int(m)): round(median * (m / TARGET_MKT_IDX) ** c, -2) for m in (24.9, 20.6, 15.0)}

    # 버틀러 comp(디스플레이) + 근접 comp + 산점도
    butler = []
    for r in rows:
        if r["foreign"] and G2_STAR in r["leads"] and r["th"] >= 5000:
            g_pred = exp(a + b * log(r["th"]) + c * log(r["mk"]))
            butler.append({"t": r["t"], "th": r["th"], "fy": r["fy"], "R": round(r["R"], 2),
                           "oo": r["oo"], "mult": round(r["fy"] / g_pred, 2)})
    butler.sort(key=lambda x: -x["mult"])
    near = sorted([r for r in act if 30000 <= r["th"] <= 120000], key=lambda r: r["th"])
    near_view = [{"t": r["t"], "nat": r["nat"], "g": r["g"], "th": r["th"], "fy": r["fy"],
                  "R": round(r["R"], 2), "oo": r["oo"]} for r in near]
    scatter = [{"t": r["t"], "th": r["th"], "fy": r["fy"], "R": round(r["R"], 2), "oo": r["oo"],
                "butler": (G2_STAR in r["leads"])} for r in act]

    # 양극화
    filmrows = list(csv.DictReader(open(os.path.join(BASE, "vkobis_films.csv"), encoding="utf-8-sig")))
    yv = defaultdict(list)
    for r in filmrows:
        y = r["online_open"][:4]
        fy = I(r["first_year_vod"])
        if y.isdigit() and 2013 <= int(y) <= 2025 and fy > 0 and not r["first_year_note"]:
            yv[y].append(fy)
    polar = []
    for y in sorted(yv):
        v = sorted(yv[y], reverse=True)
        n = len(v)
        polar.append({"year": y, "films": n,
                      "top10_share": round(sum(v[:max(1, n // 10)]) / sum(v) * 100, 1),
                      "mid_20_100k": sum(1 for x in v if 20000 <= x < 100000),
                      "over_100k": sum(1 for x in v if x >= 100000),
                      "over_500k": sum(1 for x in v if x >= 500000)})

    market = list(csv.DictReader(open(os.path.join(BASE, "market_index.csv"), encoding="utf-8-sig")))

    out = {
        "generated": "2026-07-31",
        "anchors": {
            "greenland1": {"theater": G1_TH, "vod_1yr": G1_VOD1Y, "lifetime": G1_LIFE, "R": round(G1_VOD1Y / G1_TH, 2)},
            "greenland2": {"theater": G2_TH, "genre": "액션,SF", "nation": "영국",
                           "star": G2_STAR, "director": G2_DIRECTOR, "online_open": "미정(예측대상)"},
        },
        "model": {"formula": "log(VOD)=%.2f+%.3f·log(극장)+%.3f·log(시장)" % (a, b, c),
                  "b": round(b, 3), "c": round(c, 3), "n": len(act), "r2": round(r2, 3),
                  "method": "버틀러 소형~중형작 규모·시장 직접환산 중앙값", "cond_sd": round(sd, 2),
                  "target_mkt_idx": TARGET_MKT_IDX},
        "point": round(median, -2), "genre_only": round(genre_only, -2),
        "probs": probs, "percentiles": pct, "timing": timing, "analog": analog,
        "scenarios": {"conservative": pct["25"], "base": round(median, -2), "optimistic": pct["90"]},
        "star": {"name": G2_STAR, "mult": round(b_mult, 2), "n": bn, "rank": b_rank,
                 "total": len(star_prem), "ranking": star_rank,
                 "director": G2_DIRECTOR, "dir_mult": round(exp(dpr), 2), "dir_n": dn},
        "butler_comps": butler, "comps_near": near_view, "comps_scatter": scatter,
        "model_curve": [[th, round(exp(a + b * log(th) + c * log(TARGET_MKT_IDX)))]
                        for th in (5000, 10000, 20000, 50000, 100000, 300000, 1000000, 5000000)],
        "polarization": polar, "market_index": market,
        "notes": [
            "지표=PPV(TVOD) 이용건수, 정액제 제외. 목표=온라인 개봉 후 1년 누적. 예측대상 시장지수=%.0f(2020=100)." % TARGET_MKT_IDX,
            "핵심: 스타 요인이 장르보다 큼. 제라드 버틀러=외화 주연 %d명 중 VOD 프리미엄 1위(×%.2f). VOD형 액션스타(버틀러·니슨·스타뎀)가 최상위, 극장형(크루즈·존슨)은 프리미엄 없음." % (len(star_prem), b_mult),
            "예측법: 버틀러 소형~중형작(극장<25만)을 그린랜드2 규모·시장으로 직접환산한 중앙값 %s(장르-only %s의 ~3.6배). 버틀러 평균배수(×2.7)는 대형작까지 섞여 소형극장 구간을 과소평가하므로 사용 안함." % (format(round(median, -2), ","), format(round(genre_only, -2), ",")),
            "준거집단(최근 소형 외화액션)은 양극단: 중앙 ~21k지만 VOD스타면 70~90k(워킹맨 72k·쉘터 60k+·플레인 71k·블랙라이트 73k). 그린랜드2는 버틀러+프랜차이즈라 상위 프로필 → 워킹맨·쉘터 동급 이상(넘을 확률 %d%%).",
            "발레리나급(90k)=P %d%%. 발레리나는 극장 323k(그린랜드2의 6배)로 도달 — 그린랜드2는 소형극장이라 '버틀러 고전환' 경로.",
            "하방 리스크: 2편 극장(55k)이 1편(326k) 대비 83% 급감 = 프랜차이즈 냉각 신호. 스타작도 중위 착지 사례 있음(익스펜더블4 32k·레드원 13k). 개봉 늦어 시장 더 낮으면 하방.",
        ],
    }
    out["notes"][3] = out["notes"][3] % probs["72000"]
    out["notes"][4] = out["notes"][4] % probs["90000"]
    with open(os.path.join(BASE, "forecast.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("그린랜드2 중앙 %s (장르만 %s) | 버틀러 ×%.2f (%d위/%d) | 환산 n=%d sd=%.2f" %
          (format(round(median, -2), ","), format(round(genre_only, -2), ","), b_mult, b_rank, len(star_prem), len(analog), sd))
    print("P(≥90k)=%d%% P(≥72k워킹맨)=%d%% P(≥50k)=%d%%  분위 25/50/75/90 = %s/%s/%s/%s" %
          (probs["90000"], probs["72000"], probs["50000"],
           format(pct["25"], ","), format(pct["50"], ","), format(pct["75"], ","), format(pct["90"], ",")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
