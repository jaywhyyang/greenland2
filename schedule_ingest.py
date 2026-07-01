# -*- coding: utf-8 -*-
"""
배급 시간표 엑셀(그린랜드2 마이그레이션_시간표*.xlsx)에서 오늘 날짜 시트의
- 총 상영회차 / 총 좌석수
- 시간대별(오전 ~12:00 / 오후 12:01~17:00 / 저녁 17:01~) 회차 수
를 뽑아 schedule.json 저장 → 대시보드 '편성 반영 예상 스코어'에 사용.
(시간표는 수동 스냅샷; 0701~0705 등 여러 날짜 시트 포함)
"""
import os
import re
import glob
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE, "schedule.json")
SEARCH_DIRS = [os.path.join(os.path.expanduser("~"), "Downloads"),
               os.path.join(os.path.expanduser("~"), "OneDrive - 키노라이츠", "바탕 화면"),
               BASE]


def _find_file():
    cands = []
    for d in SEARCH_DIRS:
        cands += glob.glob(os.path.join(d, "*마이그레이션*시간표*.xls*"))
        cands += glob.glob(os.path.join(d, "*시간표*.xlsx"))
    return max(cands, key=os.path.getmtime) if cands else None


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def parse(path, date_str=None):
    import openpyxl
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    mmdd = date_str[5:7] + date_str[8:10]  # "0701"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = mmdd if mmdd in wb.sheetnames else next(
        (s for s in wb.sheetnames if re.fullmatch(r"\d{4}", s)), wb.sheetnames[0])
    ws = wb[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]

    bands = {"오전": 0, "오후": 0, "저녁": 0}
    total_seats = 0
    for r in rows:
        cells = [("" if c is None else c) for c in r]
        first = str(cells[0]).strip() if cells else ""
        # 시간대 비율표: 첫 셀이 오전/오후/저녁, 정수(>1)들의 합 = 그 시간대 회차수
        if first in bands:
            # 행에 계열사별 회차 + 총합 컬럼이 함께 있음 → 최댓값(=그 시간대 총 회차)만 사용
            ints = [n for c in cells[1:]
                    if (n := _num(c)) is not None and n > 1 and float(c) == int(float(c))]
            if ints:
                bands[first] = max(ints)
        # 총 좌석수: '계' 행의 큰 값
        if first == "계":
            for c in cells:
                n = _num(c)
                if n and n > 10000:
                    total_seats = max(total_seats, n)
    total_shows = sum(bands.values())
    return {"date": date_str, "sheet": sheet, "total_shows": total_shows,
            "total_seats": total_seats, "bands": bands}


def main():
    f = _find_file()
    if not f:
        print("시간표 파일 못 찾음")
        return 1
    data = parse(f)
    with open(OUT_JSON, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)
    print("시간표 파싱:", data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
