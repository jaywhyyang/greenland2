# -*- coding: utf-8 -*-
"""
메가박스 단독개봉 comp 라이브러리 생성 → megabox_solo_final.csv

입력
  multichain_weekly.csv  (kobis_multichain.py)  — 영화 × 주 × 체인 스크린수
  all_daily.csv / all_meta.csv (kobis_all_daily.py) — 일별 관객·스크린·좌석 + 메타

■ 단독 판정 (프록시 금지, 실측만)
  '오리지널 런' 구간에서 CGV 스크린합 == 0 and 롯데시네마 == 0 and 메가박스 > 0.
  씨네Q는 허용한다 — 단독작에도 곁다리로 붙어서(첫 번째 키스 19관, 워페어 14관)
  배제하면 진짜 단독작이 탈락한다.

■ 왜 '오리지널 런'인가 (이거 안 하면 틀린다)
  전 기간 합계로 보면 **1년 뒤 타 체인 재상영·기획전에 오염**된다.
  진격의 거인 완결편(2025-03 개봉, 개봉~종영 완전 메가박스 단독, 949,711명)은
  2026-03 재상영 때 CGV 39·97·41관이 붙었다는 이유로 탈락했었다. 전수 재판정 시 104편이 복구됐다.
  → 주간 시계열을 gap(1주 이상 공백) 기준으로 잘라 연속 런으로 나누고,
     신작은 개봉일이 속한 런, 재개봉·구작은 메가 스크린이 최대인 런으로 앵커한다.
     관객수도 그 런 구간으로 잘라야 재상영분이 안 섞인다.

■ 재개봉작 개봉일
  KOBIS 개봉일은 원작 개봉일이라 재개봉일이 아니다(러브레터 1999-11-20).
  런 안에서 스크린이 피크의 30%에 처음 도달한 날을 재개봉일로 실측한다(사전상영 잡음 제거).
"""
import csv
import io
import os
import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
MC = os.path.join(BASE, "multichain_weekly.csv")
DAILY = os.path.join(BASE, "all_daily.csv")
META = os.path.join(BASE, "all_meta.csv")
OUT = os.path.join(BASE, "megabox_solo_final.csv")

MIN_SCREENS = 50      # 메가 최대주간 스크린 하한 — 1~2관 기획전·잔여상영 제거
PEAK_FRAC = 0.30      # 재개봉일 판정: 런 피크 스크린 대비 비율

FIELDS = ["영화명", "개봉일", "원개봉일", "구분", "세그먼트", "상영상태", "누적관객",
          "개봉일좌석수", "개봉일스크린수", "개봉일관객수", "메가최대일간스크린", "평균스크린",
          "스크린당좌석", "상영주수", "단독런시작", "단독런종료", "장르", "대표국적", "배급사"]


def _int(x):
    try:
        return int(str(x).strip() or 0)
    except ValueError:
        return 0


def load():
    wk = defaultdict(dict)
    for r in csv.DictReader(io.open(MC, encoding="utf-8-sig")):
        wk[r["영화명"]].setdefault(r["주시작"], {})[r["체인"]] = _int(r["스크린수"])
    meta = {r["영화명"]: r for r in csv.DictReader(io.open(META, encoding="utf-8-sig"))}
    day = defaultdict(dict)
    for r in csv.DictReader(io.open(DAILY, encoding="utf-8-sig")):
        day[r["영화명"]][r["날짜"]] = r
    return wk, meta, day


def runs(weeks):
    """주간 시계열을 1주 이상 공백 기준으로 잘라 연속 런 리스트로."""
    ws = sorted(w for w, d in weeks.items() if sum(d.values()) > 0)
    out, cur = [], []
    for w in ws:
        d = datetime.date.fromisoformat(w)
        if cur and (d - datetime.date.fromisoformat(cur[-1])).days > 7:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def main():
    wk, meta, day = load()
    last_week = max(w for f in wk.values() for w in f)
    rows = []
    for n, weeks in wk.items():
        m = meta.get(n)
        if not m:
            continue
        op = (m.get("개봉일") or "")[:10]
        rs = runs(weeks)
        if not rs:
            continue
        if op >= "2023-01-01":
            run = next((r for r in rs if r[-1] >= op), rs[0])
            kind = "신작"
        else:
            run = max(rs, key=lambda r: max(weeks[w].get("메가박스", 0) for w in r))
            kind = "재개봉/구작"

        tot = defaultdict(int)
        for w in run:
            for k, v in weeks[w].items():
                tot[k] += v
        if not (tot["CGV"] == 0 and tot["롯데시네마"] == 0 and tot["메가박스"] > 0):
            continue
        mx = max(weeks[w].get("메가박스", 0) for w in run)
        if mx < MIN_SCREENS:
            continue

        w0 = run[0]
        w1 = (datetime.date.fromisoformat(run[-1]) + datetime.timedelta(days=6)).isoformat()
        dates = sorted(d for d in day[n] if w0 <= d <= w1)
        if not dates:
            continue
        sel = [day[n][d] for d in dates]
        dscr = {d: _int(day[n][d]["스크린수"]) for d in dates}
        peak = max(dscr.values()) or 1
        if kind == "신작" and op in day[n]:
            eff = op
        else:
            eff = next((d for d in dates if dscr[d] >= peak * PEAK_FRAC), dates[0])
        o = day[n].get(eff, {})
        scr = [v for v in dscr.values() if v]
        g = m.get("장르", "")
        seg = ("애니메이션" if "애니메이션" in g
               else "공연·실황" if ("공연" in g or "뮤지컬" in g)
               else "실사 한국" if m.get("대표국적") == "한국" else "실사 외화")
        rows.append({
            "영화명": n, "개봉일": eff, "원개봉일": m.get("개봉일", ""), "구분": kind, "세그먼트": seg,
            "상영상태": "상영중(잠정)" if run[-1] >= last_week else "종영",
            "누적관객": sum(_int(x["관객수"]) for x in sel),
            "개봉일좌석수": _int(o.get("좌석수")), "개봉일스크린수": _int(o.get("스크린수")),
            "개봉일관객수": _int(o.get("관객수")),
            "메가최대일간스크린": mx,
            "평균스크린": round(sum(scr) / max(len(scr), 1), 1),
            "스크린당좌석": round(sum(_int(x["좌석수"]) for x in sel) / max(sum(scr), 1)),
            "상영주수": len(run), "단독런시작": w0, "단독런종료": w1,
            "장르": g, "대표국적": m.get("대표국적", ""), "배급사": m.get("배급사", ""),
        })

    rows.sort(key=lambda x: -x["누적관객"])
    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    new = [r for r in rows if r["구분"] == "신작"]
    miss = [r for r in rows if r["개봉일좌석수"] == 0]
    print("{0} → {1}편 (신작 {2} / 재개봉·구작 {3})".format(os.path.basename(OUT), len(rows), len(new), len(rows) - len(new)))
    print("  개봉일 좌석 결손: {0}편 {1}".format(len(miss), [r["영화명"][:20] for r in miss]))
    print("  상영중(잠정): {0}".format([r["영화명"][:20] for r in rows if r["상영상태"].startswith("상영중")]))

    # 소비처(인 더 그레이 트래커 등)가 읽는 교환 파일을 함께 갱신한다.
    # 이걸 빼먹으면 소비처가 옛 밴드를 계속 표시하므로 여기서 같이 돌린다.
    try:
        import emit_band
        emit_band.main()
    except Exception as e:
        print("  !! 교환 파일(megabox_solo_band.json) 생성 실패:", e)


if __name__ == "__main__":
    main()
