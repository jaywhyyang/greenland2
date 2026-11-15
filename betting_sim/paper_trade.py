"""
바카라형 2폴더 모의투자 (가상 예산 1,000만원, 실제 돈/계정 없음).

  python3 paper_trade.py pick     # 예정경기에서 오늘~내일 조합 1~2개 선정, 장부 기록
  python3 paper_trade.py settle   # 결과 나온 조합 정산
  python3 paper_trade.py status   # 현재 자금/성적

샘플사이트 배당 = bet365 배당 x (1 - MARGIN)  (실제 사설사이트 대용)
공정확률     = Betfair 거래소(BFE*) 배당 마진 제거 (football-data에서 Pinnacle은 2025/26 시즌 중 중단)
조합         = 샘플사이트 배당 1.35~1.55 다리 중 엣지 상위 순으로 2개씩 → 하루 최대 2조합
베팅법       = 조합마다 독립 파롤리 3단 체인(A/B), 기본 단위 = 자금의 2%
데이터       = football-data.co.uk 공개 CSV (로그인 불필요)
"""
import io, json, os, sys, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "paper", "ledger.csv")
STATE = os.path.join(HERE, "paper", "state.json")
MARGIN, LO, HI = 0.02, 1.35, 1.55
BASE, STEPS, MAX_COMBOS = 0.02, 3, 2
UK = ZoneInfo("Europe/London"); KST = ZoneInfo("Asia/Seoul")
SEASON = "2627"


def get_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-sim/0.1"})
    raw = urllib.request.urlopen(req, timeout=30).read()
    df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", on_bad_lines="skip")
    df.columns = [c.strip().lstrip("﻿").lstrip("ï»¿") for c in df.columns]
    return df


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"bankroll": 10_000_000, "start": 10_000_000, "target": 100_000_000,
            "chains": {"A": {"streak": 0, "stake": None}, "B": {"streak": 0, "stake": None}}}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w"), ensure_ascii=False, indent=1)


def load_ledger():
    if os.path.exists(LEDGER):
        return pd.read_csv(LEDGER, dtype={"combo_id": str})
    return pd.DataFrame()


def devig(o):
    inv = 1.0 / o
    return inv / inv.sum(axis=1, keepdims=True)


def candidate_legs(fx, now_uk):
    fx = fx.dropna(subset=["Date", "HomeTeam", "AwayTeam", "B365H", "B365D", "B365A"]).copy()
    fx["ko"] = pd.to_datetime(fx["Date"] + " " + fx["Time"].fillna("15:00"), dayfirst=True, errors="coerce")
    fx = fx[fx["ko"] > now_uk.replace(tzinfo=None) + timedelta(minutes=30)]
    legs = []
    for _, r in fx.iterrows():
        for ref in ("BFE",):  # PP*는 Pinnacle이 아님(2026/27부터 PS* 사라짐) → Betfair 거래소 사용
            ro = [r.get(f"{ref}{x}") for x in "HDA"]
            if all(pd.notna(v) and float(v) > 1.01 for v in ro):
                break
        else:
            continue
        fair = devig(np.array([ro], dtype=float))[0]
        for j, lab in enumerate("HDA"):
            o = float(r[f"B365{lab}"]) * (1 - MARGIN)
            if LO <= o <= HI:
                legs.append(dict(div=r["Div"], ko=r["ko"], home=r["HomeTeam"], away=r["AwayTeam"], pick=lab,
                                 odds=round(o, 3), p=round(fair[j], 4), ref=ref, edge=round(o * fair[j] - 1, 4)))
    return pd.DataFrame(legs)


def cmd_pick():
    now = datetime.now(UK)
    st = load_state(); led = load_ledger()
    used = set()
    if len(led):
        used = set(led["home"] + "|" + led["ko"].astype(str))
    legs = candidate_legs(get_csv("https://www.football-data.co.uk/fixtures.csv"), now)
    if not len(legs):
        print("후보 다리 없음 (예정 경기에 1.35~1.55 배당 없음)"); return
    legs = legs[~(legs["home"] + "|" + legs["ko"].astype(str)).isin(used)]
    # 오늘~내일(영국시간) 킥오프만, 엣지 내림차순, 한 경기 한 다리
    legs = legs[legs["ko"].dt.date <= (now + timedelta(days=1)).date()]
    legs = legs.sort_values("edge", ascending=False).drop_duplicates(["home", "ko"])
    open_chains = set(led.loc[led["status"] == "open", "chain"]) if len(led) else set()
    new = []
    for k, chain in enumerate([c for c in "AB" if c not in open_chains][:MAX_COMBOS]):
        pair = legs.iloc[2 * k:2 * k + 2]
        if len(pair) < 2:
            break
        ch = st["chains"][chain]
        stake = ch["stake"] if ch["streak"] > 0 and ch["stake"] else BASE * st["bankroll"]
        stake = int(min(stake, st["bankroll"]) // 1000 * 1000)
        cid = f"{now:%Y%m%d}-{chain}"
        tot_odds = float(np.prod(pair["odds"]))
        for _, l in pair.iterrows():
            new.append(dict(combo_id=cid, chain=chain, created_kst=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                            stake=stake, combo_odds=round(tot_odds, 3), status="open", **l.to_dict(),
                            ftr="", leg_win="", payout=""))
        print(f"[{cid}] 체인{chain} 파롤리 {ch['streak']+1}단계 | 묶음배당 {tot_odds:.2f} | 가상 베팅 {stake:,}원")
        for _, l in pair.iterrows():
            print(f"   {l['ko']:%m-%d %H:%M}(英) {l['div']} {l['home']} vs {l['away']} → {l['pick']} @{l['odds']:.2f} "
                  f"(공정확률 {l['p']*100:.1f}%, 엣지 {l['edge']*100:+.1f}%)")
    if not new:
        print("새 조합 없음 (진행 중 체인 정산 대기 또는 후보 부족)"); return
    led = pd.concat([led, pd.DataFrame(new)], ignore_index=True)
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    led.to_csv(LEDGER, index=False)


def cmd_settle():
    led = load_ledger(); st = load_state()
    if not len(led) or not (led["status"] == "open").any():
        print("정산할 조합 없음"); return
    res = {}
    for d in led.loc[led["status"] == "open", "div"].unique():
        try:
            r = get_csv(f"https://www.football-data.co.uk/mmz4281/{SEASON}/{d}.csv")
            r["d"] = pd.to_datetime(r["Date"], dayfirst=True, errors="coerce").dt.date
            for _, x in r.dropna(subset=["FTR"]).iterrows():
                res[(str(x["d"]), x["HomeTeam"], x["AwayTeam"])] = x["FTR"]
        except Exception as e:
            print(d, "결과 파일 오류:", e)
    for cid in led.loc[led["status"] == "open", "combo_id"].unique():
        m = led["combo_id"] == cid
        ftrs = [res.get((str(pd.to_datetime(r["ko"]).date()), r["home"], r["away"])) for _, r in led[m].iterrows()]
        if any(f is None for f in ftrs):
            continue
        led.loc[m, "ftr"] = ftrs
        led.loc[m, "leg_win"] = [int(f == p) for f, p in zip(ftrs, led.loc[m, "pick"])]
        row = led[m].iloc[0]; win = all(f == p for f, p in zip(ftrs, led.loc[m, "pick"]))
        stake, odds = float(row["stake"]), float(row["combo_odds"])
        pnl = stake * (odds - 1) if win else -stake
        st["bankroll"] += pnl
        ch = st["chains"][row["chain"]]
        if win:
            ch["streak"] += 1; ch["stake"] = stake * odds
            if ch["streak"] >= STEPS:
                ch["streak"], ch["stake"] = 0, None
        else:
            ch["streak"], ch["stake"] = 0, None
        led.loc[m, "status"] = "won" if win else "lost"
        led.loc[m, "payout"] = round(pnl)
        print(f"[{cid}] {'적중' if win else '실패'} {pnl:+,.0f}원 → 자금 {st['bankroll']:,.0f}원")
    led.to_csv(LEDGER, index=False); save_state(st)


def cmd_status():
    st = load_state(); led = load_ledger()
    print(f"자금 {st['bankroll']:,.0f}원 (시작 {st['start']:,} → 목표 {st['target']:,}, 진행 x{st['bankroll']/st['start']:.2f})")
    if len(led):
        c = led.drop_duplicates("combo_id")
        done = c[c["status"] != "open"]
        if len(done):
            print(f"정산 {len(done)}판: 적중 {(done['status']=='won').sum()} / 실패 {(done['status']=='lost').sum()} "
                  f"| 평균 묶음배당 {done['combo_odds'].mean():.2f} | 손익 {pd.to_numeric(done['payout']).sum():+,.0f}원")
        print(f"진행 중 {(c['status']=='open').sum()}판")
    for k, v in st["chains"].items():
        print(f"  체인{k}: 파롤리 {v['streak']}연승 중")


if __name__ == "__main__":
    {"pick": cmd_pick, "settle": cmd_settle, "status": cmd_status}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
