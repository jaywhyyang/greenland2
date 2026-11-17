"""
샘플사이트 #2: Polymarket 예측시장 모의투자 (조회 전용 공개 API, 계정·로그인·거래 없음).

  python3 pm_trade.py run     # settle → pick → status (하루 4회: KST 09/15/21/03)

- 시장   : Polymarket 승패(moneyline) 시장 — NBA/NHL/NFL/대학미식축구/축구 주요 리그
- 배당   : 해당 결과를 '매수'하는 가격(ask)의 역수 = 1/ask  (예: 0.775 → 1.29)
- 스캔   : (1) 8일 내 마감되는 '모든' 이벤트를 날짜로 전수 조회(마감=경기+7일인 리그 대응) + (2) 종목 태그 조회(테니스 등) → 합집합
- 다리   : 배당 1.01~1.90, 호가차 <= 6센트(거래량 무관, $1k 미만은 '저유동성' 표시), 시작 15분~24시간 전
- 판     : 거래량 많은 순으로 묶어 배당 1.9 이상(1~4폴더), 동시에 최대 2판(체인 A/B)
           (pm-v5부터 동시 최대 3판, 체인 A/B/C) → 체인이 정산되면 다음 스캔에서 다음 시간대 경기로 '이어가기'
- 자금   : paper_trade.py와 같은 5트랙(ATK 주력 / BOLD / F500 / P2 / 싱글), 트랙별 1,000만원
- 정산   : 시장 마감 후 결과가격(1/0)으로 즉시 확정. 50/50 또는 10일 경과 미확정은 무효(배당 1.0)
참고: 예측시장 가격은 마진이 거의 없는 '공정가'에 가까움. 엣지 기대보다 '매일 실전 기록' 목적.
"""
import json, os, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from paper_trade import TRACKS, stake_for, STEPS, START, GOAL, FLAT_S

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "paper_pm")
LEGS, STATE = os.path.join(DIR, "legs.csv"), os.path.join(DIR, "state.json")
API = "https://gamma-api.polymarket.com"
TAGS = ["nba", "nhl", "nfl", "cfb", "mlb", "epl", "la-liga", "serie-a", "bundesliga", "ligue-1", "ucl", "tennis", "esports", "mls", "kbl", "k-league", "j-league", "basketball", "soccer", "hockey"]
LO, HI, TARGET_ODDS, MAX_LEGS = 1.01, 1.90, 1.9, 4
MIN_VOL, MAX_SPREAD, AHEAD_MIN, AHEAD_H, VOID_DAYS = 0, 0.06, 15, 24, 10  # v3: 거래량 조건 없음, 호가차 4센트 이하만
LOWLIQ = 1_000  # 이 미만 거래량은 '저유동성' 표시
KST = ZoneInfo("Asia/Seoul")


def get(path):
    """공개 조회 API. 요청 간 1초 간격(서버 부담·제한 방지)."""
    time.sleep(1)
    out = subprocess.run(["curl", "-sS", "--compressed", "-m", "30", "-A", "research-sim/0.1", API + path],
                         capture_output=True, text=True)
    if out.returncode: raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


CHAINS = "ABC"  # pm-v5: 동시 진행 판 최대 3개


def load_state():
    if os.path.exists(STATE):
        st = json.load(open(STATE))
        for t in st["tracks"].values():
            for ch in CHAINS: t["chains"].setdefault(ch, [0, None])
        return st
    return {"tracks": {k: {"bank": START, "chains": {ch: [0, None] for ch in CHAINS}, "stopped": False} for k in TRACKS},
            "S": {"bank": START}, "version": "pm-v5"}


def load_legs():
    if not os.path.exists(LEGS) or os.path.getsize(LEGS) < 5: return pd.DataFrame()
    return pd.read_csv(LEGS, dtype=str).fillna("")


def save(st, legs):
    os.makedirs(DIR, exist_ok=True)
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    legs.to_csv(LEGS, index=False)


def candidates():
    now = now_utc(); rows = []; evs_all = []; seen = set()
    # 마감일 기준 8일을 12시간 조각으로 나눠 전수 조회(한 번에 크게 조회하면 서버 상한에 잘림)
    for k in range(16):
        a = (now + timedelta(hours=12 * k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        b = (now + timedelta(hours=12 * (k + 1))).strftime("%Y-%m-%dT%H:%M:%SZ")
        for off in range(0, 3000, 100):
            try:
                evs = get(f"/events?closed=false&end_date_min={a}&end_date_max={b}&limit=100&offset={off}")
            except Exception as e:
                print(f"  날짜조회 오류: {e}"); break
            if not isinstance(evs, list) or not evs: break
            evs_all += [("all", e) for e in evs]
            if len(evs) < 100: break
    for tag in TAGS:  # 마감일이 늦게 잡힌 경기 보완
        try:
            evs = get(f"/events?tag_slug={tag}&closed=false&limit=100")
        except Exception as e:
            print(f"  {tag} 조회 오류: {e}"); continue
        if isinstance(evs, list): evs_all += [(tag, e) for e in evs]
    print(f"  조회 이벤트 {len(evs_all):,}개")
    for tag, e in evs_all:
        tag = (e.get("seriesSlug") or e.get("slug", "")).split("-")[0] or tag
        if True:
            for m in e.get("markets", []):
                if m.get("sportsMarketType") != "moneyline" or m.get("closed") or not m.get("acceptingOrders"): continue
                if m["id"] in seen: continue
                seen.add(m["id"])
                try:
                    ko = pd.to_datetime(m.get("gameStartTime") or e.get("startTime"), utc=True).tz_localize(None)
                    outs = json.loads(m["outcomes"]); bid, ask = float(m["bestBid"]), float(m["bestAsk"])
                    vol, spr = float(m.get("volume") or 0), float(m.get("spread") or (ask - bid))
                except Exception:
                    continue
                if not (now + timedelta(minutes=AHEAD_MIN) < ko < now + timedelta(hours=AHEAD_H)): continue
                if vol < MIN_VOL or spr > MAX_SPREAD: continue
                # 결과별 매수가: 0번 결과 = ask, 1번 결과 = 1 - bid
                sides = [(0, ask), (1, 1 - bid)]
                if outs == ["Yes", "No"]: sides = [(0, ask)]  # 축구 'X 승리?' 시장은 Yes만
                for idx, price in sides:
                    if price <= 0: continue
                    odds = 1 / price
                    if LO <= odds <= HI:
                        pick = outs[idx] if outs != ["Yes", "No"] else m.get("question", "")[:60]
                        rows.append(dict(tag=tag, market_id=str(m["id"]), outcome_idx=idx, title=e.get("title", "")[:60],
                                         pick=pick, ko=ko, price=round(price, 4), odds=round(odds, 3), vol=round(vol)))
    c = pd.DataFrame(rows)
    if not len(c): return c
    return c.sort_values(["vol", "ko"], ascending=[False, True]).drop_duplicates("market_id").reset_index(drop=True)  # v4: 거래량 많은 경기 우선


def cmd_pick(st, legs):
    c = candidates()
    if len(legs) and len(c):
        c = c[~c.market_id.isin(set(legs.market_id))]
    print(f"[픽] 후보 다리 {len(c)}개 (Polymarket 전 종목 승패시장, 배당 1.01~1.90, 호가차 {MAX_SPREAD*100:.0f}센트 이하, {AHEAD_H}시간 내 시작)")
    if not len(c): print("  이번 스캔엔 조건에 맞는 경기가 없습니다."); return legs
    open_ch = set(legs.loc[legs.status.isin(["open", "leg_done"]) & (legs.combo != ""), "chain"]) if len(legs) else set()
    free = [ch for ch in CHAINS if ch not in open_ch]
    if not free: print(f"  체인 {'/'.join(CHAINS)} 모두 진행 중 → 결과 확정 후 다음 스캔에서 이어갑니다."); return legs
    pool = list(c.itertuples()); combos = []
    while pool and len(combos) < len(free):
        grp, odds = [], 1.0
        while pool and odds < TARGET_ODDS and len(grp) < MAX_LEGS:
            r = pool.pop(0); grp.append(r); odds *= r.odds
        if odds < TARGET_ODDS and combos: pool = grp + pool; break
        combos.append((grp, odds))
    exposure = {}
    if len(legs):
        op = legs[legs.status.isin(["open", "leg_done"]) & (legs.combo != "")].drop_duplicates("combo")
        exposure = {tr: pd.to_numeric(op[f"stake_{tr}"], errors="coerce").fillna(0).sum() for tr in TRACKS}
    bold_open = len(legs) > 0 and (legs.status.isin(["open", "leg_done"]) & ~legs.stake_BOLD.isin(["", "0"])).any()
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M"); rows = []
    for (grp, odds), ch in zip(combos, free):
        cid = f"PM{datetime.now(KST):%Y%m%d%H%M}-{ch}"
        stakes = {}
        for tr in TRACKS:
            stakes[tr] = stake_for(tr, st["tracks"][tr], ch, odds, bold_open, exposure.get(tr, 0.0))
            exposure[tr] = exposure.get(tr, 0.0) + stakes[tr]
        if stakes["BOLD"]: bold_open = True
        print(f"  [{cid}] {len(grp)}폴더 묶음배당 {odds:.2f}")
        for tr, s in stakes.items():
            stp = st["tracks"][tr]["chains"][ch][0] + 1 if TRACKS[tr]["kind"] == "paroli" else None
            print(f"     · {TRACKS[tr]['name']}: {s:,}원" + (f" (파롤리 {stp}단계)" if s and stp else ""))
        for r in grp:
            rows.append(dict(created_kst=stamp, tag=r.tag, market_id=r.market_id, outcome_idx=r.outcome_idx, title=r.title,
                             pick=r.pick, ko=str(r.ko), price=r.price, odds=f"{r.odds:.3f}", vol=r.vol, combo=cid, chain=ch,
                             combo_odds=f"{odds:.3f}", **{f"stake_{tr}": s for tr, s in stakes.items()},
                             stake_S=int(FLAT_S * st["S"]["bank"] // 1000 * 1000), status="open", win=""))
            kst = pd.Timestamp(r.ko).tz_localize("UTC").tz_convert(KST)
            liq = " ·저유동성" if r.vol < LOWLIQ else ""
            print(f"     {kst:%m-%d %H:%M}(KST) [{r.tag}] {r.title} → {r.pick} @{r.odds:.2f} (가격 {r.price:.3f}, 거래량 ${r.vol:,}{liq})")
    return pd.concat([legs, pd.DataFrame(rows).astype(str)], ignore_index=True)


def cmd_settle(st, legs):
    if not len(legs) or not (legs.status == "open").any():
        print("[정산] 대기 중인 베팅 없음"); return legs
    for i in legs[legs.status == "open"].index:
        try:
            m = get(f"/markets/{legs.at[i, 'market_id']}")
        except Exception as e:
            print(f"  {legs.at[i, 'market_id']} 조회 오류: {e}"); continue
        prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")] if m else []
        idx = int(legs.at[i, "outcome_idx"])
        ko = pd.to_datetime(legs.at[i, "ko"])
        if m.get("closed") and prices and max(prices) >= 0.99:
            w = prices[idx] >= 0.99
            legs.at[i, "win"] = "1" if w else "0"
        elif (m.get("closed") and prices and abs(prices[idx] - 0.5) < 0.01) or ko < now_utc() - timedelta(days=VOID_DAYS):
            legs.at[i, "win"] = "V"; print(f"  [무효] {legs.at[i, 'title']} → 배당 1.0 처리")
        else:
            continue
        s = float(legs.at[i, "stake_S"] or 0); o = float(legs.at[i, "odds"])
        if legs.at[i, "win"] == "1": st["S"]["bank"] += s * (o - 1)
        elif legs.at[i, "win"] == "0": st["S"]["bank"] -= s
        legs.at[i, "status"] = "leg_done"
    for cid in [x for x in legs.combo.unique() if x]:
        m = legs.combo == cid
        if legs.loc[m, "status"].isin(["won", "lost"]).any(): continue
        lw = legs.loc[m, "win"]
        if (lw == "0").any() or (lw != "").all():  # 한 다리라도 지면 즉시 실패 확정
            win = lw.isin(["1", "V"]).all() and (lw != "").all()
            odds = float(np.prod([float(o) for o, w in zip(legs.loc[m, "odds"], lw) if w == "1"] or [1.0]))
            ch = legs.loc[m, "chain"].iloc[0]; msg = []
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
    print("[현황·Polymarket] (각 트랙 시작 1,000만, 목표 1억)")
    for tr, cfg in TRACKS.items():
        t = st["tracks"][tr]
        print(f"  {cfg['name']:24s} {t['bank']:>13,.0f}원 (x{t['bank']/START:.2f})" + (" [1억 도달·중단]" if t["stopped"] else ""))
    print(f"  {'비교·싱글 1%':24s} {st['S']['bank']:>13,.0f}원 (x{st['S']['bank']/START:.2f})")
    if len(legs):
        cb = legs[legs.combo != ""].drop_duplicates("combo")
        w, l = (cb.status == "won").sum(), (cb.status == "lost").sum()
        lg = legs[legs.win.isin(["0", "1"])]
        print(f"  판 {w}승 {l}패 (진행 {len(cb)-w-l}) | 다리 적중 {int((lg.win=='1').sum())}/{len(lg)}")
        print("  체인 " + ", ".join(f"{ch}: {st['tracks']['ATK']['chains'][ch][0]}연승" for ch in CHAINS))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    st, legs = load_state(), load_legs()
    if cmd in ("settle", "run"): legs = cmd_settle(st, legs)
    if cmd in ("pick", "run"): legs = cmd_pick(st, legs)
    if cmd != "status": save(st, legs)
    cmd_status(st, legs)
