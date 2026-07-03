# -*- coding: utf-8 -*-
"""
노바엔터 '경쟁작 상영회차비교' 엑셀 파서.
파일은 기준일(예 7/2) vs 대상일(예 7/4) 두 날짜의 배급사별 총좌석수/총상영회차/총스크린수를
영화별로 비교. Downloads/바탕화면에서 최신 '경쟁작 상영회차비교*' 파일을 찾아 파싱 →
nova_competitors.json (대시보드 '경쟁작 편성 비교' 패널용).
"""
import os
import re
import glob
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "nova_competitors.json")
SEARCH = [os.path.join(os.path.expanduser("~"), "Downloads"),
          os.path.join(os.path.expanduser("~"), "OneDrive - 키노라이츠", "바탕 화면"), BASE]


def _find():
    cands = []
    for d in SEARCH:
        cands += glob.glob(os.path.join(d, "*경쟁작*상영회차*.xls*"))
    return max(cands, key=os.path.getmtime) if cands else None


def _clean_name(s):
    # "토이 스토리 5\n(월트디즈니)" → "토이 스토리 5"
    return str(s).split("\n")[0].strip()


def _metric_of(label):
    if "좌석" in label:
        return "seats"
    if "회차" in label:
        return "shows"
    if "스크린" in label or "상영관" in label:
        return "screens"
    return None


def _dates(rows):
    """헤더에서 'M/D일' 두 날짜를 순서대로."""
    yr = datetime.date.today().year
    for r in rows:
        found = []
        for c in r:
            m = re.match(r"\s*(\d{1,2})/(\d{1,2})", str(c or ""))
            if m:
                iso = f"{yr}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
                if iso not in found:
                    found.append(iso)
        if len(found) >= 2:
            return found[:2]
    return None


def parse(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    films = {}          # name -> {seats:[b,t], shows:.., screens:..}
    baseline = target = None
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        valrow = next((r for r in rows if r and isinstance(r[0], str) and r[0].strip().startswith("총")), None)
        if not valrow:
            continue
        metric = _metric_of(valrow[0])
        if not metric:
            continue
        dts = _dates(rows)
        if dts and not baseline:
            baseline, target = dts
        # 영화명: 상단 블록(row 2~13)의 문자열 셀 순서
        names = []
        for r in rows[2:14]:
            for c in r[1:]:
                if c and isinstance(c, str) and len(_clean_name(c)) > 1 and not re.match(r"\s*\d", str(c)):
                    names.append(_clean_name(c))
        vals = [v for v in valrow[1:] if isinstance(v, (int, float))]
        pairs = [(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]
        for nm, pr in zip(names, pairs):
            films.setdefault(nm, {})[metric] = [pr[0], pr[1]]
    out = {"baseline": baseline, "target": target,
           "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "films": [{"name": nm, **v} for nm, v in films.items() if v.get("seats")]}
    return out


def main():
    f = _find()
    if not f:
        print("노바 파일 못 찾음")
        return 1
    data = parse(f)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"노바 파싱: {data['baseline']}→{data['target']} · 영화 {len(data['films'])}편 · {os.path.basename(f)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
