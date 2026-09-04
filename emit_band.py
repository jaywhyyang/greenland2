# -*- coding: utf-8 -*-
"""
메가박스 단독개봉 comp 분석 → megabox_solo_band.json (교환 파일)

■ 왜 있나
  인 더 그레이 트래커(../인더그레이/build_ig.py) 같은 소비처가 밴드 숫자를
  손으로 옮겨 적으면, comp가 갱신될 때(예: 워페어 종영) 반드시 드리프트한다.
  이 파일이 유일한 출처가 되고, 소비처는 읽기만 한다.

■ 무엇을 담나
  observed — comp 실측 통계만. 판단이 섞이지 않는다.
  scenario — 표시용 밴드. 가정(개봉일 좌석·좌석판매율)을 값과 함께 실어 보낸다.
  model    — 개봉일 관객 → 최종 로그회귀 계수. 개봉 후 소비처가 직접 재예측할 수 있다.
  pacing   — 개봉 N일차 누적 비중 중앙값. D3 40% 룰(즉시소진형 vs 롱런형) 판정용.

  scenario 는 판단이 들어간 값이므로 assumptions 를 반드시 함께 읽을 것.
"""
import csv
import io
import json
import math
import os
import statistics as st
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "megabox_solo_final.csv")
DAILY = os.path.join(BASE, "all_daily.csv")
OUT = os.path.join(BASE, "megabox_solo_band.json")
# 소비처 리포 안에도 사본을 둔다. 그래야 그 리포만 클론해도 밴드가 살아 있고,
# 인더그레이 세션이 그린랜드2 폴더 없이 단독으로 작업할 수 있다.
MIRRORS = [os.path.join(BASE, "..", "인더그레이", "megabox_solo_band.json")]

# 인 더 그레이 세그먼트 정의
SEG = "실사 외화"
MIN_SCREENS = 150          # 상업 규모 단독 편성
EXCLUDE_NATION = "일본"     # 배급사 의견(2026-08-27): 일본작 제외
# 개봉일 좌석 가정. scenario 전체가 이 값 위에 서 있으므로 바뀌면 반드시 갱신할 것.
# 2026-08-28: 배급사 전망이 4만석대로 내려와 45,000 으로 수정(직전 가정 50,000).
# 참고로 워페어 개봉일이 45,012석이었다 — 사실상 동일 조건이므로 워페어 최종이 곧 기준선이 된다.
ASSUMED_OPENING_SEATS = 45000
SELL_RATES = {"low": 0.066, "mid": 0.085, "high": 0.121}  # 크라임101 / 워킹맨·워페어 / 머티리얼리스트
PACING_MARKS = [1, 3, 7, 11, 14, 21, 28]


def _i(x):
    try:
        return int(str(x).strip() or 0)
    except ValueError:
        return 0


def load():
    rows = list(csv.DictReader(io.open(SRC, encoding="utf-8-sig")))
    for r in rows:
        for k in ("누적관객", "개봉일좌석수", "개봉일스크린수", "개봉일관객수", "메가최대일간스크린"):
            r[k] = _i(r[k])
    day = defaultdict(dict)
    for r in csv.DictReader(io.open(DAILY, encoding="utf-8-sig")):
        day[r["영화명"]][r["날짜"]] = r
    return rows, day


def logfit(pts):
    xs = [math.log(x) for x, _ in pts]
    ys = [math.log(y) for _, y in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    r2 = 1 - sum(e * e for e in res) / sum((y - my) ** 2 for y in ys)
    return a, b, r2, st.pstdev(res), n


def main():
    rows, day = load()
    new = [r for r in rows if r["구분"] == "신작"]
    fl = [r for r in new if r["세그먼트"] == SEG and r["대표국적"] != EXCLUDE_NATION]
    band_set = [r for r in fl if r["메가최대일간스크린"] >= MIN_SCREENS]
    if not band_set:
        raise SystemExit("세그먼트에 해당하는 comp 없음 — 정의를 확인할 것")

    aud = sorted(r["누적관객"] for r in band_set)
    a, b, r2, sd, n_fit = logfit([(r["개봉일관객수"], r["누적관객"]) for r in fl if r["개봉일관객수"] > 0])
    predict = lambda x: math.exp(a + b * math.log(x))

    # 소진 곡선 — 종영작만
    curves = []
    for r in band_set:
        if r["상영상태"] != "종영":
            continue
        d = day.get(r["영화명"], {})
        dl = sorted(x for x in d if r["단독런시작"] <= x <= r["단독런종료"]
                    and _i(d[x]["관객수"]) > 0 and x >= r["개봉일"])
        if not dl or not r["누적관객"]:
            continue
        cum, acc = [], 0
        for x in dl:
            acc += _i(d[x]["관객수"])
            cum.append(acc)
        curves.append([cum[min(k, len(cum)) - 1] / r["누적관객"] for k in PACING_MARKS])
    pacing = {("D%d" % k): round(st.median([c[i] for c in curves]), 3)
              for i, k in enumerate(PACING_MARKS)} if curves else {}

    live = [r["영화명"] for r in band_set if r["상영상태"] != "종영"]
    doc = {
        "schema": "megabox-solo-band/1",
        "generated_from": "build_megabox_solo.py → megabox_solo_final.csv",
        # 단독런종료는 주 단위라 미래 날짜가 될 수 있다. 실제 관측 마지막 날을 쓴다.
        "data_range": {"start": min(r["단독런시작"] for r in rows),
                       "end": max(d for f in day.values() for d in f)},
        "segment": {
            "label": "실사 외화 × 메가박스 {0}관 이상 (일본 제외)".format(MIN_SCREENS),
            "n": len(band_set),
            "min_screens": MIN_SCREENS, "exclude_nation": EXCLUDE_NATION,
        },
        "observed": {
            "max": aud[-1], "min": aud[0],
            "median": round(st.median(aud)),
            "p25": round(st.quantiles(aud, n=4, method="inclusive")[0]) if len(aud) > 3 else aud[0],
            "p75": round(st.quantiles(aud, n=4, method="inclusive")[2]) if len(aud) > 3 else aud[-1],
            "opening_seats_median": round(st.median([r["개봉일좌석수"] for r in band_set])),
            "opening_aud_median": round(st.median([r["개봉일관객수"] for r in band_set])),
            "sell_rate_median": round(st.median(
                [r["개봉일관객수"] / r["개봉일좌석수"] for r in band_set if r["개봉일좌석수"]]), 4),
        },
        "scenario": {
            "low": round(predict(ASSUMED_OPENING_SEATS * SELL_RATES["low"]), -2),
            "mid": round(predict(ASSUMED_OPENING_SEATS * SELL_RATES["mid"]), -2),
            "high": round(predict(ASSUMED_OPENING_SEATS * SELL_RATES["high"]), -2),
            "ceiling": aud[-1],
            "assumptions": {
                "opening_seats": ASSUMED_OPENING_SEATS,
                "sell_rates": SELL_RATES,
                "note": ("scenario 는 개봉일 좌석 {0:,}석 가정 위의 값이다. 편성이 이보다 좁으면 "
                         "한 단계 낮춰 읽을 것. ceiling 은 장르 무관 실사 외화 단독 최고 실측치이며, "
                         "액션·범죄로 좁히면 역대 최고는 21,014(워킹맨)이다."
                         ).format(ASSUMED_OPENING_SEATS),
            },
        },
        "model": {
            "form": "ln(final) = a + b * ln(opening_admissions)",
            "a": round(a, 4), "b": round(b, 4), "r2": round(r2, 3),
            "resid_sd": round(sd, 3), "n": n_fit,
            "interval_68": [round(math.exp(-sd), 3), round(math.exp(sd), 3)],
            "fit_on": "실사 외화 신작 단독개봉(일본 제외) 전체",
        },
        "pacing": {
            "desc": "개봉 N일차 누적 / 최종 (중앙값). D3가 0.40을 넘길 기세면 즉시소진형(2만대), 0.30 안팎이면 롱런형.",
            "median": pacing, "n": len(curves),
        },
        "comps": [{
            "title": r["영화명"], "open": r["개봉일"], "genre": r["장르"],
            "screens": r["메가최대일간스크린"], "opening_seats": r["개봉일좌석수"],
            "opening_aud": r["개봉일관객수"], "final": r["누적관객"], "status": r["상영상태"],
        } for r in sorted(band_set, key=lambda x: -x["누적관객"])],
        "caveats": ([("아직 상영 중이라 최종이 아닌 작품이 포함됨: " + ", ".join(live) +
                      ". 종영 후 재생성하면 밴드가 바뀐다.")] if live else []),
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("{0} 생성 — comp {1}편 / 시나리오 {2:,}–{3:,} (천장 {4:,})".format(
        os.path.basename(OUT), len(band_set),
        doc["scenario"]["low"], doc["scenario"]["high"], doc["scenario"]["ceiling"]))
    for m in MIRRORS:
        d = os.path.dirname(m)
        if not os.path.isdir(d):
            print("  · 사본 건너뜀(폴더 없음):", os.path.normpath(d))
            continue
        with io.open(m, "w", encoding="utf-8") as f:
            f.write(text)
        print("  · 사본 갱신:", os.path.normpath(m))
    if live:
        print("  주의: 상영중 포함 —", ", ".join(live))
    return OUT


if __name__ == "__main__":
    main()
