"""football-data.co.uk 공개 CSV(시즌별) 다운로드. 로그인 불필요, 요청 간 지연."""
import os, time, urllib.request, sys
DIVS = "E0 E1 E2 E3 EC SC0 SC1 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1".split()
SEASONS = [f"{y%100:02d}{(y+1)%100:02d}" for y in range(2012, 2026)]  # 1213 ~ 2526
OUT = os.path.join(os.path.dirname(__file__), "data", "raw")
for s in SEASONS:
    for d in DIVS:
        p = os.path.join(OUT, f"{s}_{d}.csv")
        if os.path.exists(p) and os.path.getsize(p) > 1000: continue
        url = f"https://www.football-data.co.uk/mmz4281/{s}/{d}.csv"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-sim/0.1"})
            data = urllib.request.urlopen(req, timeout=30).read()
            open(p, "wb").write(data); print(s, d, len(data))
        except Exception as e:
            print(s, d, "ERR", e, file=sys.stderr)
        time.sleep(0.4)
