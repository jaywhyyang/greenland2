"""sportsbookreviewsonline.com 과거 배당 아카이브(공개, robots 허용) 다운로드. 요청 간 1초."""
import os, re, time, urllib.request
OUT = os.path.join(os.path.dirname(__file__), "data", "sbr")
BASE = "https://www.sportsbookreviewsonline.com"
UA = {"User-Agent": "Mozilla/5.0 (research-sim)"}
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
for sport in ["nba", "nfl", "nhl", "mlb", "ncaabasketball", "ncaafootball"]:
    idx = get(f"{BASE}/scoresoddsarchives/{sport}/{sport}oddsarchives.htm").decode("utf-8", "ignore")
    links = sorted(set(re.findall(r'href="(/scoresoddsarchives/[a-z0-9-]*odds-[0-9-]+/?)"', idx)))
    links += sorted(set(re.findall(r'href="(/wp-content/uploads/[^"]+\.xlsx)"', idx)))
    for l in links:
        name = l.strip("/").split("/")[-1]
        p = os.path.join(OUT, name if name.endswith(".xlsx") else name + ".html")
        if os.path.exists(p): continue
        try:
            open(p, "wb").write(get(BASE + l)); print(name)
        except Exception as e:
            print(name, "ERR", e)
        time.sleep(1)
