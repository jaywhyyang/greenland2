"""
bet365 단일 사이트 모의투자 (가상 예산 트랙별 1,000만원, 실제 돈/계정 없음).

  python3 paper_trade.py run      # settle → pick → status (매일 1회)
  python3 paper_trade.py pick | settle | status

픽 규칙 v2 (화이트리스트: segments.py가 고른 '바카라보다 나았던' 리그x결과x배당대 구간)
  다리 : bet365 배당 1.01~1.90(적중확률 50%+ 쪽만), 화이트리스트 구간, 킥오프 30분~36시간 전
         유럽(fixtures.csv) + 유럽 외(new_league_fixtures.csv)
  판   : 다리를 킥오프 순으로 묶어 배당 1.9 이상(최소 1, 최대 4폴더) '바카라 한 판' → 하루 최대 2판(체인 A/B)
  주의 : 학습구간 선정 → 검증구간 -4.5% (선정 안 된 구간 -4.3%와 차이 없음). 실전 기록으로 재확인 목적.

통합 장부(2026-11-18~): 자금 상태는 paper_pm/state.json 하나를 Polymarket과 공유. 축구 판은 체인 D/E.
자금운용 v3 — 같은 판에 트랙별로 동시에 가상 베팅 (staking_lab.py 비교 근거)
  ATK  주력  : 바닥 없음, 기본 = 현재 자금의 10%, 파롤리 3단, 1억 도달 시 중단
  BOLD 그림자: 대담한 베팅(Dubins & Savage 1965) — 1억까지 필요한 만큼 한 판에 (체인 A만, 한 번에 1판)
  F500 그림자: 바닥 500만 보호(CPPI, Black & Perold 1992), 기본 = (자금-500만)의 10%, 파롤리 3단
  P2   그림자: 이전 방식, 기본 = 자금의 2%, 파롤리 3단
  S    비교  : 묶음 없이 다리마다 싱글 자금 1%
데이터: football-data.co.uk 공개 CSV. 로그인 불필요.
"""
import io, json, os, sys, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "paper")
LEGS = os.path.join(DIR, "legs.csv")
STATE = os.path.join(HERE, "paper_pm", "state.json")  # 통합 장부: Polymarket과 같은 자금(트랙)을 공유
PM_LEGS = os.path.join(HERE, "paper_pm", "legs.csv")
SOCCER_CHAINS = "DE"  # 축구 판은 체인 D/E (Polymarket은 A/B/C)
WL = json.load(open(os.path.join(HERE, "paper", "whitelist.json")))["segments"]
WLSET = {(d["lg"], d["side"], d["band"]) for d in WL}
WORLD = {"Japan": "JPN", "USA": "USA", "Brazil": "BRA", "Argentina": "ARG", "Mexico": "MEX", "China": "CHN",
         "Norway": "NOR", "Sweden": "SWE", "Denmark": "DNK", "Finland": "FIN", "Ireland": "IRL", "Austria": "AUT",
         "Switzerland": "SWZ", "Poland": "POL", "Romania": "ROU", "Russia": "RUS"}
BANDS = [(1.01, 1.3), (1.3, 1.5), (1.5, 1.8), (1.8, 2.2)]
LO, HI, TARGET_ODDS, MAX_LEGS, MAX_COMBOS = 1.01, 1.90, 1.9, 4, 2
STEPS, FLAT_S, VOID_DAYS = 3, 0.01, 10
UK, KST = ZoneInfo("Europe/London"), ZoneInfo("Asia/Seoul")
SEASON = "2627"
START, GOAL = 10_000_000, 100_000_000
# 트랙: kind = paroli(base 비율, floor) / bold
TRACKS = {
    "ATK":  dict(name="주력·전액공격 파롤리(자금10%)", kind="paroli", base=0.10, floor=0),
    "BOLD": dict(name="그림자·대담한 베팅", kind="bold"),
    "F500": dict(name="그림자·바닥500만 보호", kind="paroli", base=0.10, floor=5_000_000),
    "P2":   dict(name="그림자·이전방식(자금2%)", kind="paroli", base=0.02, floor=0),
}


def get_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-sim/0.1"})
    raw = urllib.request.urlopen(req, timeout=40).read()
    df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    return df


def load_state():
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if "tracks" not in st:
        st = {"tracks": {k: {"bank": START, "chains": {}, "stopped": False} for k in TRACKS}, "S": {"bank": START}}
    for t in st["tracks"].values():
        for ch in "ABC" + SOCCER_CHAINS: t["chains"].setdefault(ch, [0, None])
    return st


def open_exposure():
    """통합 장부: 축구·Polymarket 양쪽의 미정산 판 베팅액 합계(트랙별)."""
    exp = {tr: 0.0 for tr in TRACKS}
    for p in (LEGS, PM_LEGS):
        if not os.path.exists(p) or os.path.getsize(p) < 5: continue
        l = pd.read_csv(p, dtype=str).fillna("")
        if "stake_ATK" not in l: continue
        op = l[l.status.isin(["open", "leg_done"]) & (l.combo != "")].drop_duplicates("combo")
        for tr in TRACKS:
            exp[tr] += pd.to_numeric(op.get(f"stake_{tr}"), errors="coerce").fillna(0).sum()
    return exp


def load_legs():
    if not os.path.exists(LEGS) or os.path.getsize(LEGS) < 5: return pd.DataFrame()
    return pd.read_csv(LEGS, dtype=str).fillna("")


def save(st, legs):
    os.makedirs(DIR, exist_ok=True)
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    legs.to_csv(LEGS, index=False)


SIDES = {"H": "홈승", "D": "무", "A": "원정승"}


def band(o):
    for lo, hi in BANDS:
        if lo <= o <= hi: return f"{lo}-{hi}"
    return None


def candidates(now):
    out = []
    for src, url in [("euro", "https://www.football-data.co.uk/fixtures.csv"),
                     ("world", "https://www.football-data.co.uk/new_league_fixtures.csv")]:
        try:
            fx = get_csv(url)
        except Exception as e:
            print(f"  {src} 예정경기 오류: {e}"); continue
        if src == "euro":
            fx = fx.rename(columns={"HomeTeam": "home", "AwayTeam": "away"}); fx["lg"] = fx["Div"]
        else:
            fx = fx.rename(columns={"Home": "home", "Away": "away"})
            fx["lg"] = fx["Country"].str.strip() + "|" + fx["League"].str.strip()
        fx["ko"] = pd.to_datetime(fx["Date"] + " " + fx["Time"].fillna("15:00"), dayfirst=True, errors="coerce")
        for l in "HDA":
            o = pd.to_numeric(fx.get("B365" + l), errors="coerce")
            out.append(pd.DataFrame({"src": src, "lg": fx.lg, "ko": fx.ko, "home": fx.home, "away": fx.away, "side": l, "odds": o}))
    c = pd.concat(out, ignore_index=True).dropna()
    c = c[(c.ko > now + timedelta(minutes=30)) & (c.ko < now + timedelta(hours=36)) & c.odds.between(LO, HI)]
    c = c[[(lg, sd, band(o)) in WLSET for lg, sd, o in zip(c.lg, c.side, c.odds)]] if len(c) else c
    if not len(c):  # 후보 0건이면 빈 표(열 유지) 반환 — 빈 표 정렬 시 KeyError 방지
        return pd.DataFrame(columns=["src", "lg", "ko", "home", "away", "side", "odds"])
    return c.sort_values("ko").drop_duplicates(["lg", "home", "ko"]).reset_index(drop=True)


def stake_for(tr, t, chain, odds, bold_open, exposure=0.0):
    """트랙 t의 이번 판 베팅액. exposure = 이 트랙의 미정산 베팅 합계(동시 노출이 자금/바닥을 넘지 않게)."""
    cfg = TRACKS[tr]
    if t["stopped"]: return 0
    bank = t["bank"] - exposure
    if cfg["kind"] == "bold":
        if chain != "A" or bold_open: return 0
        s = (GOAL - bank) / (odds - 1)
        return int(min(s, bank) // 1000 * 1000)
    room = max(bank - cfg["floor"], 0)
    if room <= 0: return 0
    streak, nxt = t["chains"][chain]
    s = nxt if streak > 0 and nxt else cfg["base"] * room
    return int(min(s, room) // 1000 * 1000)


def cmd_pick(st, legs):
    now = datetime.now(UK).replace(tzinfo=None)
    c = candidates(now)
    if len(legs):
        c = c[~(c["lg"] + "|" + c["home"] + "|" + c["ko"].astype(str)).isin(set(legs["lg"] + "|" + legs["home"] + "|" + legs["ko"]))]
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"[픽] 후보 다리 {len(c)}개 (bet365 1.01~1.90, 화이트리스트 {len(WLSET)}개 구간, 36시간 내 킥오프)")
    if not len(c):
        print("  오늘은 조건에 맞는 경기가 없어 베팅하지 않습니다."); return legs
    open_ch = set(legs.loc[legs.status == "open", "chain"]) - {""} if len(legs) else set()
    bold_open = False  # 대담한 베팅은 한 번에 1판만
    if len(legs) and "stake_BOLD" in legs:
        bold_open = ((legs.status == "open") & ~legs.stake_BOLD.isin(["", "0"])).any()
    free = [ch for ch in SOCCER_CHAINS if ch not in open_ch]
    pool = list(c.itertuples()); combos = []
    while pool and len(combos) < min(MAX_COMBOS, len(free)):
        grp, odds = [], 1.0
        while pool and odds < TARGET_ODDS and len(grp) < MAX_LEGS:
            r = pool.pop(0); grp.append(r); odds *= r.odds
        if odds < TARGET_ODDS and combos:
            pool = grp + pool; break
        combos.append((grp, odds))
    rows, used = [], set()
    exposure = open_exposure()  # 통합 장부 전체 미정산 노출
    for (grp, odds), ch in zip(combos, free):
        cid = f"{datetime.now(KST):%Y%m%d}-{ch}"
        stakes = {}
        for tr in TRACKS:
            stakes[tr] = stake_for(tr, st["tracks"][tr], ch, odds, bold_open, exposure.get(tr, 0.0))
            exposure[tr] = exposure.get(tr, 0.0) + stakes[tr]
        if stakes["BOLD"]: bold_open = True
        print(f"  [{cid}] {len(grp)}폴더 묶음배당 {odds:.2f}")
        for tr, s in stakes.items():
            t = st["tracks"][tr]; stp = t["chains"][ch][0] + 1 if TRACKS[tr]["kind"] == "paroli" else "-"
            print(f"     · {TRACKS[tr]['name']}: {s:,}원" + (f" (파롤리 {stp}단계)" if s and stp != "-" else ""))
        for r in grp:
            used.add(r.Index)
            rows.append(dict(created_kst=stamp, src=r.src, lg=r.lg, side=r.side, ko=str(r.ko), home=r.home, away=r.away,
                             odds=f"{r.odds:.2f}", combo=cid, chain=ch, combo_odds=f"{odds:.3f}",
                             **{f"stake_{tr}": s for tr, s in stakes.items()},
                             stake_S=int(FLAT_S * st["S"]["bank"] // 1000 * 1000), status="open", ftr="", win=""))
            print(f"     {r.ko:%m-%d %H:%M}(英) {r.lg} {r.home} vs {r.away} → {SIDES[r.side]} @{r.odds:.2f}")
    for r in pool:
        if r.Index in used: continue
        rows.append(dict(created_kst=stamp, src=r.src, lg=r.lg, side=r.side, ko=str(r.ko), home=r.home, away=r.away,
                         odds=f"{r.odds:.2f}", combo="", chain="", combo_odds="", **{f"stake_{tr}": 0 for tr in TRACKS},
                         stake_S=int(FLAT_S * st["S"]["bank"] // 1000 * 1000), status="open", ftr="", win=""))
        print(f"     (싱글만) {r.ko:%m-%d %H:%M}(英) {r.lg} {r.home} vs {r.away} → {SIDES[r.side]} @{r.odds:.2f}")
    return pd.concat([legs, pd.DataFrame(rows).astype(str)], ignore_index=True)


def cmd_settle(st, legs):
    if not len(legs) or not (legs.status == "open").any():
        print("[정산] 대기 중인 베팅 없음"); return legs
    res = {}
    for lg in legs.loc[legs.status == "open", "lg"].unique():
        world = "|" in lg
        url = (f"https://www.football-data.co.uk/new/{WORLD.get(lg.split('|')[0], 'XXX')}.csv" if world
               else f"https://www.football-data.co.uk/mmz4281/{SEASON}/{lg}.csv")
        try:
            r = get_csv(url)
            if world:
                r = r[(r.Country.str.strip() + "|" + r.League.str.strip()) == lg].rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "Res": "FTR"})
            for x in r.dropna(subset=["FTR"]).itertuples():
                res[(lg, str(pd.to_datetime(x.Date, dayfirst=True).date()), x.HomeTeam, x.AwayTeam)] = x.FTR
        except Exception as e:
            print(f"  {lg} 결과파일 오류: {e}")
    for i in legs[legs.status == "open"].index:
        k = (legs.at[i, "lg"], str(pd.to_datetime(legs.at[i, "ko"]).date()), legs.at[i, "home"], legs.at[i, "away"])
        if k in res:
            w = res[k] == legs.at[i, "side"]
            legs.at[i, "ftr"] = res[k]; legs.at[i, "win"] = "1" if w else "0"
            s = float(legs.at[i, "stake_S"] or 0); o = float(legs.at[i, "odds"])
            st["S"]["bank"] += s * (o - 1) if w else -s
            legs.at[i, "status"] = "leg_done" if legs.at[i, "combo"] else "done"
        elif pd.to_datetime(legs.at[i, "ko"]) < datetime.now(UK).replace(tzinfo=None) - timedelta(days=VOID_DAYS):
            legs.at[i, "win"] = "V"; legs.at[i, "ftr"] = "VOID"  # 연기·취소·이름불일치: 적중특례(배당 1.0) 처리
            legs.at[i, "status"] = "leg_done" if legs.at[i, "combo"] else "done"
            print(f"  [무효] {legs.at[i, 'home']} vs {legs.at[i, 'away']} ({legs.at[i, 'ko']}) {VOID_DAYS}일 경과 결과 없음 → 배당 1.0 처리")
    for cid in [x for x in legs.combo.unique() if x]:
        m = legs.combo == cid
        if legs.loc[m, "status"].isin(["won", "lost"]).any() or (legs.loc[m, "status"] == "open").any(): continue
        lw = legs.loc[m, "win"]
        win = lw.isin(["1", "V"]).all()
        odds = float(np.prod([float(o) for o, w in zip(legs.loc[m, "odds"], lw) if w != "V"] or [1.0]))  # 무효 다리 제외 재계산
        ch = legs.loc[m, "chain"].iloc[0]
        msg = []
        for tr in TRACKS:
            s = float(legs.loc[m, f"stake_{tr}"].iloc[0] or 0); t = st["tracks"][tr]
            if s <= 0: continue
            pnl = s * (odds - 1) if win else -s
            t["bank"] += pnl
            if TRACKS[tr]["kind"] == "paroli":
                c = t["chains"][ch]
                if win:
                    c[0] += 1; c[1] = s * odds
                    if c[0] >= STEPS: c[0], c[1] = 0, None
                else:
                    c[0], c[1] = 0, None
            if t["bank"] >= GOAL: t["stopped"] = True
            msg.append(f"{tr} {pnl:+,.0f}")
        legs.loc[m, "status"] = "won" if win else "lost"
        print(f"[정산] {cid} 묶음 {odds:.2f} {'적중' if win else '실패'} | " + ", ".join(msg))
    return legs


def cmd_status(st, legs):
    print("[현황·통합 장부(축구+Polymarket)] (각 트랙 시작 1,000만, 목표 1억)")
    for tr, cfg in TRACKS.items():
        t = st["tracks"][tr]
        print(f"  {cfg['name']:24s} {t['bank']:>13,.0f}원 (x{t['bank']/START:.2f})" + (" [1억 도달·중단]" if t["stopped"] else ""))
    print(f"  {'비교·싱글 1%':24s} {st['S']['bank']:>13,.0f}원 (x{st['S']['bank']/START:.2f})")
    if len(legs):
        cb = legs[legs.combo != ""].drop_duplicates("combo")
        w, l = (cb.status == "won").sum(), (cb.status == "lost").sum()
        lg = legs[legs.win.isin(["0", "1"])]
        print(f"  판 {w}승 {l}패 (진행 {len(cb)-w-l}) | 다리 적중 {int((lg.win=='1').sum())}/{len(lg)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    st, legs = load_state(), load_legs()
    if cmd in ("settle", "run"): legs = cmd_settle(st, legs)
    if cmd in ("pick", "run"): legs = cmd_pick(st, legs)
    if cmd != "status": save(st, legs)
    cmd_status(st, legs)
