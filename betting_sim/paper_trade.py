"""
bet365 단일 사이트 모의투자 (가상 예산 1,000만원, 실제 돈/계정 없음).

  python3 paper_trade.py run      # settle → pick → status (매일 1회)
  python3 paper_trade.py pick | settle | status

규칙 (RESULTS.md 후보 3: 하위리그 홈 강팀, 2012~2026 백테스트 +1.3% ±1.7, 확정 아님)
  다리   : bet365 홈승 배당 1.01~1.30, 5대 리그(E0 SP1 I1 D1 F1) 제외, 킥오프 30분~36시간 전
  트랙 P : 다리를 킥오프 순으로 묶어 배당 1.9 이상(최대 4다리) '바카라 한 판' → 하루 최대 2판
           판마다 파롤리 3단 체인(A/B), 기본 = 자금의 2%. 자금 1억 도달 시 신규 베팅 중단(익절).
  트랙 S : 같은 다리를 싱글 고정 1%로 (비교용)
데이터: football-data.co.uk fixtures.csv(bet365 배당) / 시즌 결과 CSV. 로그인 불필요.
"""
import io, json, os, sys, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "paper")
LEGS, STATE = os.path.join(DIR, "legs.csv"), os.path.join(DIR, "state.json")
TOP5 = {"E0", "SP1", "I1", "D1", "F1"}
LO, HI, TARGET_ODDS, MAX_LEGS, MAX_COMBOS = 1.01, 1.30, 1.9, 4, 2
BASE_P, STEPS, FLAT_S = 0.02, 3, 0.01
UK, KST = ZoneInfo("Europe/London"), ZoneInfo("Asia/Seoul")
SEASON = "2627"
START, GOAL = 10_000_000, 100_000_000


def get_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-sim/0.1"})
    raw = urllib.request.urlopen(req, timeout=40).read()
    df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    return df


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"P": {"bank": START, "chains": {"A": [0, None], "B": [0, None]}, "stopped": False},
            "S": {"bank": START}, "log": []}


def load_legs():
    return pd.read_csv(LEGS, dtype=str) if os.path.exists(LEGS) else pd.DataFrame()


def save(st, legs):
    os.makedirs(DIR, exist_ok=True)
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    legs.to_csv(LEGS, index=False)


def cmd_pick(st, legs):
    now = datetime.now(UK).replace(tzinfo=None)
    fx = get_csv("https://www.football-data.co.uk/fixtures.csv")
    fx = fx.dropna(subset=["Date", "HomeTeam", "AwayTeam", "B365H"])
    fx["ko"] = pd.to_datetime(fx["Date"] + " " + fx["Time"].fillna("15:00"), dayfirst=True, errors="coerce")
    fx["B365H"] = pd.to_numeric(fx["B365H"], errors="coerce")
    c = fx[(fx.ko > now + timedelta(minutes=30)) & (fx.ko < now + timedelta(hours=36)) &
           (fx.B365H >= LO) & (fx.B365H <= HI) & ~fx.Div.isin(TOP5)].sort_values("ko")
    key = lambda d: d["Div"].astype(str) + "|" + d["HomeTeam"].astype(str) + "|" + d["ko"].astype(str)
    if len(legs):
        c = c[~key(c).isin(set(legs["Div"] + "|" + legs["home"] + "|" + legs["ko"]))]
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"[픽] 후보 다리 {len(c)}개 (bet365 홈 1.01~1.30, 5대리그 제외, 36시간 내 킥오프)")
    if not len(c):
        print("  오늘은 조건에 맞는 경기가 없어 베팅하지 않습니다."); return legs
    rows, open_ch = [], set(legs.loc[legs.status == "open", "chain"].dropna()) if len(legs) else set()
    free = [ch for ch in "AB" if ch not in open_ch]
    pool = list(c.itertuples())
    combos = []
    while pool and len(combos) < min(MAX_COMBOS, len(free)) and not st["P"]["stopped"]:
        grp, odds = [], 1.0
        while pool and odds < TARGET_ODDS and len(grp) < MAX_LEGS:
            r = pool.pop(0); grp.append(r); odds *= r.B365H
        if odds < TARGET_ODDS and combos:  # 남은 다리로 1.9 못 채우면 버림(첫 판은 미달이어도 진행)
            pool = grp + pool; break
        combos.append((grp, odds))
    used = set()
    for (grp, odds), ch in zip(combos, free):
        streak, stake = st["P"]["chains"][ch]
        stake = stake if streak > 0 and stake else BASE_P * st["P"]["bank"]
        stake = int(min(stake, st["P"]["bank"]) // 1000 * 1000)
        cid = f"{datetime.now(KST):%Y%m%d}-{ch}"
        print(f"  [{cid}] 체인{ch} 파롤리 {streak+1}단계 · {len(grp)}폴더 묶음배당 {odds:.2f} · 가상베팅 {stake:,}원")
        for r in grp:
            used.add(r.Index)
            rows.append(dict(created_kst=stamp, Div=r.Div, ko=str(r.ko), home=r.HomeTeam, away=r.AwayTeam,
                             odds=f"{r.B365H:.2f}", combo=cid, chain=ch, combo_odds=f"{odds:.3f}", stake_p=stake,
                             stake_s=int(FLAT_S * st["S"]["bank"] // 1000 * 1000), status="open", ftr="", win=""))
            print(f"     {r.ko:%m-%d %H:%M}(英) {r.Div:4s} {r.HomeTeam} vs {r.AwayTeam} → 홈승 @{r.B365H:.2f}")
    for r in pool:  # 묶음에 안 들어간 다리는 싱글 트랙만
        if r.Index in used: continue
        rows.append(dict(created_kst=stamp, Div=r.Div, ko=str(r.ko), home=r.HomeTeam, away=r.AwayTeam,
                         odds=f"{r.B365H:.2f}", combo="", chain="", combo_odds="", stake_p=0,
                         stake_s=int(FLAT_S * st["S"]["bank"] // 1000 * 1000), status="open", ftr="", win=""))
        print(f"     (싱글만) {r.ko:%m-%d %H:%M}(英) {r.Div:4s} {r.HomeTeam} vs {r.AwayTeam} @{r.B365H:.2f}")
    if st["P"]["stopped"]:
        print("  트랙P는 목표 1억 도달로 중단 상태(싱글만 기록)")
    return pd.concat([legs, pd.DataFrame(rows).astype(str)], ignore_index=True)


def cmd_settle(st, legs):
    if not len(legs) or not (legs.status == "open").any():
        print("[정산] 대기 중인 베팅 없음"); return legs
    res = {}
    for d in legs.loc[legs.status == "open", "Div"].unique():
        try:
            r = get_csv(f"https://www.football-data.co.uk/mmz4281/{SEASON}/{d}.csv").dropna(subset=["FTR"])
            for x in r.itertuples():
                res[(d, str(pd.to_datetime(x.Date, dayfirst=True).date()), x.HomeTeam, x.AwayTeam)] = x.FTR
        except Exception as e:
            print(f"  {d} 결과파일 오류: {e}")
    op = legs.status == "open"
    for i in legs[op].index:
        k = (legs.at[i, "Div"], str(pd.to_datetime(legs.at[i, "ko"]).date()), legs.at[i, "home"], legs.at[i, "away"])
        if k in res:
            legs.at[i, "ftr"] = res[k]; legs.at[i, "win"] = "1" if res[k] == "H" else "0"
            w = res[k] == "H"; s = float(legs.at[i, "stake_s"]); o = float(legs.at[i, "odds"])
            st["S"]["bank"] += s * (o - 1) if w else -s
            legs.at[i, "status"] = "done" if not legs.at[i, "combo"] else "leg_done"
    for cid in legs.loc[legs.combo.ne("") & legs.combo.notna(), "combo"].unique():
        m = legs.combo == cid
        if (legs.loc[m, "status"] == "won").any() or (legs.loc[m, "status"] == "lost").any(): continue
        if (legs.loc[m, "status"] == "open").any():
            if (legs.loc[m, "win"] == "0").any(): pass  # 이미 진 다리 있어도 전체 확정 후 처리
            continue
        win = (legs.loc[m, "win"] == "1").all()
        stake, odds = float(legs.loc[m, "stake_p"].iloc[0]), float(legs.loc[m, "combo_odds"].iloc[0])
        ch = legs.loc[m, "chain"].iloc[0]
        pnl = stake * (odds - 1) if win else -stake
        st["P"]["bank"] += pnl
        c = st["P"]["chains"][ch]
        if win:
            c[0] += 1; c[1] = stake * odds
            if c[0] >= STEPS: c[0], c[1] = 0, None
        else:
            c[0], c[1] = 0, None
        legs.loc[m, "status"] = "won" if win else "lost"
        if st["P"]["bank"] >= GOAL: st["P"]["stopped"] = True
        print(f"[정산] {cid} {'적중' if win else '실패'} {pnl:+,.0f}원 → 트랙P {st['P']['bank']:,.0f}원")
    return legs


def cmd_status(st, legs):
    p, s = st["P"]["bank"], st["S"]["bank"]
    print(f"[현황] 트랙P(파롤리 묶음) {p:,.0f}원 (x{p/START:.2f}, 목표 1억) | 트랙S(싱글 1%) {s:,.0f}원 (x{s/START:.2f})")
    if len(legs):
        cb = legs[legs.combo.notna() & legs.combo.ne("")].drop_duplicates("combo")
        w, l = (cb.status == "won").sum(), (cb.status == "lost").sum()
        lg = legs[legs.win.isin(["0", "1"])]
        print(f"  묶음 {w}승 {l}패 (진행 {len(cb)-w-l}) | 다리 적중 {int((lg.win=='1').sum())}/{len(lg)}")
        print("  체인 " + ", ".join(f"{k}: {v[0]}연승" for k, v in st["P"]["chains"].items()))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    st, legs = load_state(), load_legs()
    if len(legs): legs = legs.fillna("")
    if cmd in ("settle", "run"): legs = cmd_settle(st, legs)
    if cmd in ("pick", "run"): legs = cmd_pick(st, legs)
    if cmd != "status": save(st, legs)
    cmd_status(st, legs)
