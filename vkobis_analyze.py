# -*- coding: utf-8 -*-
"""
vkobis_annual.csv 분석 1단계: 시장 하락 지수 + 고유작품 테이블(1년누적 재구성).

출력:
- market_index.csv : year, total_vod, films, cutoff_rank5000, idx_2020, idx_2018
- vkobis_films.csv : movie_id, title_ko, title_en, online_open, theater_open,
                     lifetime_vod, first_year_vod, first_year_note, peak_share, n_years
  * first_year_vod = 온라인 개봉월부터 12개월 이용건수 합(연 경계 넘어 재구성)
  * peak_share = 최대 월이 생애에서 차지하는 비중(프론트로딩 정도)

콘솔 한글 깨짐 방지: 결과는 CSV로, 요약은 ascii 위주.
"""
import os
import csv
import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "vkobis_annual.csv")
MONTHS = [f"m{m:02d}" for m in range(1, 13)]


def load():
    with open(SRC, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _int(v):
    try:
        return int(v or 0)
    except ValueError:
        return 0


def market_index(rows):
    total = defaultdict(int)
    films = defaultdict(int)
    cutoff = {}
    for r in rows:
        y = r["year"]
        total[y] += _int(r["year_total"])
        films[y] += 1
        cutoff[y] = _int(r["year_total"])  # 정렬 desc → 마지막(rank~5000) 값
    b20 = total.get("2020", 1) or 1
    b18 = total.get("2018", 1) or 1
    out = []
    for y in sorted(total):
        out.append({
            "year": y, "total_vod": total[y], "films": films[y],
            "cutoff_rank5000": cutoff[y],
            "idx_2020": round(total[y] / b20 * 100, 1),
            "idx_2018": round(total[y] / b18 * 100, 1),
        })
    with open(os.path.join(BASE, "market_index.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    return out


def build_films(rows):
    """movie_id 기준으로 연도들을 합쳐 생애/1년누적/프론트로딩 계산."""
    # movie_id -> {year -> {m01..m12}}, + meta
    by_id = defaultdict(lambda: {"months": {}, "meta": {}})
    for r in rows:
        mid = r["movie_id"] or (r["title_ko"] + "|" + r["theater_open"])
        y = int(r["year"])
        by_id[mid]["months"][y] = {m: _int(r[m]) for m in MONTHS}
        # 메타는 최신 행 기준(동일하지만 안전)
        by_id[mid]["meta"] = {
            "title_ko": r["title_ko"], "title_en": r["title_en"],
            "online_open": r["online_open"], "theater_open": r["theater_open"],
        }
    films = []
    for mid, d in by_id.items():
        meta = d["meta"]
        months = d["months"]
        # 생애 월별 시퀀스(연-월 정렬)
        seq = []  # (year, month_idx1..12, value)
        for y in sorted(months):
            for i, m in enumerate(MONTHS, start=1):
                seq.append((y, i, months[y][m]))
        lifetime = sum(v for _, _, v in seq)
        # 1년누적: 온라인 개봉월(없으면 첫 비영(非零)월)부터 12개월
        start = None
        oo = meta["online_open"]
        if oo and len(oo) >= 7:
            oy, om = int(oo[:4]), int(oo[5:7])
            start = (oy, om)
        if start is None:
            nz = [(y, i) for (y, i, v) in seq if v > 0]
            start = nz[0] if nz else None
        first_year = 0
        note = ""
        if start:
            sy, sm = start
            # 12개월 윈도우
            wanted = set()
            yy, mm = sy, sm
            for _ in range(12):
                wanted.add((yy, mm))
                mm += 1
                if mm > 12:
                    mm = 1
                    yy += 1
            first_year = sum(v for (y, i, v) in seq if (y, i) in wanted)
            # 데이터가 12개월 다 안 찼으면 표시
            last_data = max((y * 12 + i) for (y, i, v) in seq) if seq else 0
            need_last = sy * 12 + sm + 11
            if last_data < need_last:
                note = "partial(<12mo data)"
        peak = max((v for _, _, v in seq), default=0)
        peak_share = round(peak / lifetime, 3) if lifetime else 0
        films.append({
            "movie_id": mid,
            "title_ko": meta["title_ko"], "title_en": meta["title_en"],
            "online_open": oo, "theater_open": meta["theater_open"],
            "lifetime_vod": lifetime, "first_year_vod": first_year,
            "first_year_note": note, "peak_share": peak_share,
            "n_years": len(months),
        })
    films.sort(key=lambda r: r["lifetime_vod"], reverse=True)
    with open(os.path.join(BASE, "vkobis_films.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(films[0].keys()))
        w.writeheader()
        w.writerows(films)
    return films


def main():
    rows = load()
    mkt = market_index(rows)
    films = build_films(rows)
    # ascii 요약
    print("=== MARKET INDEX (2020=100) ===")
    for m in mkt:
        print(f"  {m['year']}: total={m['total_vod']:>12,}  idx2020={m['idx_2020']:>6}  "
              f"idx2018={m['idx_2018']:>6}  cutoff@5000={m['cutoff_rank5000']}")
    print(f"\nunique films: {len(films):,}")
    # 그린랜드 검증
    gr = [r for r in films if r["title_ko"] == "그린랜드" and r["theater_open"].startswith("2020")]
    if gr:
        g = gr[0]
        print(f"Greenland1: lifetime={g['lifetime_vod']:,}  first_year={g['first_year_vod']:,}  "
              f"peak_share={g['peak_share']}  note={g['first_year_note']}")
    print("\n=> market_index.csv, vkobis_films.csv written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
