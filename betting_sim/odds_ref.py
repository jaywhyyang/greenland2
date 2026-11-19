"""
The Odds API 기준배당(공정확률) — 키: 환경변수 ODDS_API_KEY (요청 URL 파라미터로만 사용, 저장·출력 안 함)

- /events (무료)로 경기 목록, /odds (종목당 1크레딧, regions=eu, h2h)로 25개 내외 업체 배당
- 공정확률 = 업체별 마진 제거(비례) 후 중앙값. Pinnacle 있으면 별도 기록
- 크레딧 절약: 종목별 4시간 캐시, 하루 사용 상한 DAILY_BUDGET (무료 500/월 기준 하루 15)
- match(): Polymarket 후보 다리(팀명·시작시각)를 기준배당 경기와 매칭 → fair_p, pin_p
"""
import json, os, re, time, unicodedata, urllib.request
from datetime import datetime, timedelta, timezone
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "odds_cache")
API = "https://api.the-odds-api.com/v4/sports"
DAILY_BUDGET, TTL_H = 15, 4
SPORTS = ["basketball_nba", "icehockey_nhl", "americanfootball_nfl", "americanfootball_ncaaf", "basketball_ncaab",
          "basketball_euroleague", "tennis_atp_finals", "soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a",
          "soccer_germany_bundesliga", "soccer_france_ligue_one", "soccer_uefa_champs_league", "soccer_uefa_europa_league",
          "soccer_korea_kleague1", "soccer_japan_j_league", "soccer_efl_champ", "soccer_netherlands_eredivisie",
          "soccer_portugal_primeira_liga", "soccer_turkey_super_league", "soccer_usa_mls", "soccer_brazil_campeonato",
          "icehockey_ahl", "icehockey_liiga", "icehockey_sweden_hockey_league", "basketball_nbl", "aussierules_afl"]
STOP = {"fc", "cf", "sc", "ac", "afc", "the", "club", "de", "cd", "fk", "sk", "if", "bk", "united", "city", "will", "win",
        "on", "vs", "women", "w", "and", "of", "st", "real", "sporting", "atletico", "athletic", "1", "2", "ii"}


def key():
    return os.environ.get("ODDS_API_KEY", "")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-sim/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()), int(r.headers.get("x-requests-last") or 0)


def _budget():
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "budget.json"); today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    b = json.load(open(p)) if os.path.exists(p) else {}
    return p, today, b.get(today, 0)


def _spend(n):
    p, today, used = _budget()
    b = json.load(open(p)) if os.path.exists(p) else {}
    b[today] = used + n; json.dump(b, open(p, "w"))


def toks(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return {t for t in re.split(r"[^a-z0-9]+", s) if len(t) > 1 and t not in STOP}


def events(sport):
    if not key(): return []
    try:
        d, _ = _get(f"{API}/{sport}/events?apiKey={key()}")
        return d if isinstance(d, list) else []
    except Exception:
        return []


def odds(sport):
    """캐시 우선. 없거나 오래되면 1크레딧 써서 조회(하루 상한 내)."""
    if not key(): return []
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{sport}.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < TTL_H * 3600:
        return json.load(open(p))
    _, _, used = _budget()
    if used >= DAILY_BUDGET:
        return json.load(open(p)) if os.path.exists(p) else []
    try:
        d, cost = _get(f"{API}/{sport}/odds?apiKey={key()}&regions=eu&markets=h2h&oddsFormat=decimal")
    except Exception:
        return json.load(open(p)) if os.path.exists(p) else []
    _spend(cost or 1); json.dump(d, open(p, "w"))
    return d


def fair_probs(ev, n_out=None):
    """경기 하나 → {결과명: (공정확률 중앙값, pinnacle확률 또는 None)}.
    n_out=2: 연장 포함 승패(2지선다) 배당만, 3: 무승부 포함 3지선다만 사용(하키 등 섞임 방지)."""
    per = {}; pin = {}
    for b in ev.get("bookmakers", []):
        for mk in b.get("markets", []):
            if mk.get("key") != "h2h": continue
            oc = [(o["name"], float(o["price"])) for o in mk["outcomes"] if float(o["price"]) > 1.0]
            if len(oc) < 2 or (n_out and len(oc) != n_out): continue
            inv = np.array([1 / p for _, p in oc]); fp = inv / inv.sum()
            for (n, _), f in zip(oc, fp):
                per.setdefault(n, []).append(f)
                if b["key"] == "pinnacle": pin[n] = f
    return {n: (float(np.median(v)), pin.get(n)) for n, v in per.items()}


def match(legs, max_sports=4):
    """legs: DataFrame(pick, title, ko[UTC naive]) → fair_p, pin_p, ref_event 열 추가.
    무료 /events로 먼저 매칭 후, 매칭이 많은 종목부터 max_sports개만 /odds 조회."""
    import pandas as pd
    legs = legs.copy(); legs["fair_p"] = np.nan; legs["pin_p"] = np.nan; legs["ref"] = ""
    if not key() or not len(legs): return legs
    hits = {}
    for sp in SPORTS:
        for e in events(sp):
            t0 = pd.to_datetime(e["commence_time"], utc=True).tz_localize(None)
            for i, r in legs.iterrows():
                if abs((pd.Timestamp(r.ko) - t0).total_seconds()) > 3 * 3600: continue
                pt = toks(r.pick); tt = toks(r.title)
                h, a = toks(e["home_team"]), toks(e["away_team"])
                # 고른 쪽 이름이 통째로 일치(한쪽이 다른 쪽에 포함)해야 함 — 'Alexander' 같은 이름 하나만 겹치는 오매칭 방지
                ok = lambda s: bool(pt) and bool(s) and (pt <= s or s <= pt)
                side, opp = (e["home_team"], a) if ok(h) else (e["away_team"], h) if ok(a) else (None, set())
                # 상대 팀명도 제목에 있어야 함(제목이 잘린 경우만 예외)
                if side and ((opp & tt) or len(str(r.title)) >= 58):
                    hits.setdefault(sp, []).append((i, e["id"], side))
    order = sorted(hits, key=lambda s: -len(hits[s]))[:max_sports]
    for sp in order:
        evs = {e["id"]: e for e in odds(sp)}
        for i, eid, side in hits[sp]:
            if eid in evs:
                yes_no = str(legs.at[i, "pick"]).lower().startswith("will")  # 축구 'X 승리?' = 3지선다
                fp = fair_probs(evs[eid], 3 if yes_no else 2).get(side)
                if fp:
                    legs.at[i, "fair_p"] = fp[0]; legs.at[i, "pin_p"] = fp[1] if fp[1] else np.nan
                    legs.at[i, "ref"] = f"{sp}:{eid}"
    return legs
