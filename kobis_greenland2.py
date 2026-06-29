# -*- coding: utf-8 -*-
"""
KOBIS 실시간 예매율 - '그린랜드 2: 마이그레이션' 시간당 예매관객수 수집기
실행할 때마다 현재 스냅샷을 읽어 CSV에 한 줄씩 추가한다.
(KOBIS 실시간 페이지는 '조회 시점의 누적값'만 제공하므로,
 매 시간 실행해서 시계열로 쌓는 구조)
"""
import re
import csv
import sys
import os
import datetime
import urllib.request
import urllib.parse

URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findRealTicketList.do"
# 영화명에 이 문자열이 포함된 행을 찾는다
MOVIE_KEYWORD = "그린랜드 2"
# CSV 저장 위치 (스크립트와 같은 폴더)
OUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "greenland2_hourly.csv")

COLUMNS = ["순위", "영화명", "개봉일", "예매율", "예매매출액", "누적매출액", "예매관객수", "누적관객수"]


def fetch_html():
    data = urllib.parse.urlencode({
        "loadEnd": "0",
        "searchType": "real",
        "sNationType": "",
        "sWideareaCd": "",
        "sMmType": "",
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=data, method="POST", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": URL,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_movie(html, keyword):
    m = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not m:
        return None
    body = m.group(1)
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        if keyword not in row:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip() for t in tds]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 8:
            return cells[:8]
    return None


def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        html = fetch_html()
        cells = parse_movie(html, MOVIE_KEYWORD)
    except Exception as e:
        print("ERROR:", e)
        return 1

    if not cells:
        print(now, "- 영화를 찾지 못했습니다 (상영/예매 데이터 없음일 수 있음)")
        # 빈 행도 기록해 두면 추적에 도움됨
        cells = ["", "", "", "", "", "", "", ""]

    row = [now] + cells
    header = ["수집시각"] + COLUMNS

    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(header)
        w.writerow(row)

    print("OK:", now, "| 예매율:", cells[3], "| 예매관객수:", cells[6], "| 누적관객수:", cells[7])
    print("저장:", OUT_CSV)

    # 대시보드 HTML 갱신 (실패해도 수집 자체는 성공으로 둠)
    try:
        import build_dashboard
        out = build_dashboard.generate()
        print("대시보드:", out)
    except Exception as e:
        print("대시보드 생성 건너뜀:", e)

    # GitHub로 자동 publish (원격 'origin'이 연결돼 있을 때만)
    try:
        publish_to_github(now)
    except Exception as e:
        print("publish 건너뜀:", e)

    return 0


def publish_to_github(now):
    import subprocess
    repo = os.path.dirname(os.path.abspath(__file__))

    def git(*args, check=True):
        return subprocess.run(["git", "-C", repo, *args],
                              capture_output=True, text=True, encoding="utf-8")

    # 원격이 없으면 아무 것도 하지 않음
    remotes = git("remote").stdout.split()
    if "origin" not in remotes:
        print("publish 건너뜀: GitHub 원격(origin) 미연결")
        return

    git("add", "index.html", "greenland2_hourly.csv")
    # 변경사항 없으면 커밋 스킵
    diff = subprocess.run(["git", "-C", repo, "diff", "--cached", "--quiet"])
    if diff.returncode != 0:
        git("commit", "-m", f"data update {now}")
    push = git("push", "origin", "main")
    if push.returncode == 0:
        print("publish 완료: GitHub push OK")
    else:
        print("publish 실패:", (push.stderr or "").strip()[:200])


if __name__ == "__main__":
    sys.exit(main())
