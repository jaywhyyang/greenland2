"""
한 테이블 모의투자 (v-table1, 2026-11-19~) — '난사' 대신 한 번에 한 판.

  python3 one_table.py run     # settle → (진행 중인 판이 없을 때만) pick → status

규칙
- 판은 동시에 하나뿐. 결과가 확정돼야 다음 판을 건다 (바카라 한 테이블).
- 픽: Polymarket 전수 스캔(pm_trade.candidates) 후보 다리(배당 1.30~1.55), 두 경기 모두 12시간 안에 시작,
      2폴더 묶음 배당 1.90~2.20 조합 1개.
      (table3~) 종목 무관 '기대값 점수' 최대 조합: 공정확률 = 시장합의(The Odds API) 우선, 없으면 Polymarket 중간가,
               거래량 $1k 미만 -1% 감점, 24시간 내 시작, 늦게 끝날수록 시간당 -0.05%
  ※ 축구(bet365 공개파일)는 결과가 2~4일 늦게 올라와 테이블이 멈추므로 메인에서 제외.
- 메인 베팅법: 1-2-4-4-4-4 (3단 파롤리 후 4단위 유지, 지면 처음으로), 단위 = 체인 시작 자금의 8%
- 비교 기록(같은 픽, 실제 결정에는 영향 없음):
    파롤리3 1-2-4(8%) / 1-2-4-8-8(8%) / 1-3-2-6(8%) / 고정 2%(연구용) / 고정 10%
- 각 베팅법 시작 1,000만원, 목표 3배(3,000만) 도달 시 그 베팅법은 원금 1,000만을 따로 떼어 놓고 이익만으로 계속.
조회 전용 공개 API만 사용. 계정·로그인·거래 없음.
"""
import json, os, sys
from datetime import datetime, timedelta
from itertools import combinations
import numpy as np, pandas as pd
import pm_trade as PM

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "paper_table")
LEGS, STATE = os.path.join(DIR, "legs.csv"), os.path.join(DIR, "state.json")
START, TARGET_X = 10_000_000, 3.0
ODDS_BAND, AIM, HORIZON_H = (1.90, 2.20), 2.00, 24
MAIN = "M1244"
SYSTEMS = {  # 이름: (표시명, 시퀀스, 끝에서 'reset' 또는 'stay', 단위 비율, 고정형 여부)
    "M1244":  ("메인 · 1-2-4-4-4-4", [1, 2, 4], "stay", 0.08, False),
    "P124":   ("비교 · 파롤리3 1-2-4", [1, 2, 4], "reset", 0.08, False),
    "P12488": ("비교 · 1-2-4-8-8", [1, 2, 4, 8], "stay", 0.08, False),
    "S1326":  ("비교 · 1-3-2-6", [1, 3, 2, 6], "reset", 0.08, False),
    "F2":     ("비교 · 고정 2%(연구용)", [1], "reset", 0.02, True),
    "F10":    ("비교 · 고정 10%", [1], "reset", 0.10, True),
}


def load_state():
    if os.path.exists(STATE): return json.load(open(STATE))
    return {"systems": {k: {"bank": START, "locked": 0, "unit": None, "idx": 0} for k in SYSTEMS}, "version": "table1"}


def load_legs():
    if not os.path.exists(LEGS) or os.path.getsize(LEGS) < 5: return pd.DataFrame()
    return pd.read_csv(LEGS, dtype=str).fillna("")


def save(st, legs):
    os.makedirs(DIR, exist_ok=True)
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    legs.to_csv(LEGS, index=False)


def stake(name, s):
    _, seq, mode, f, fixed = SYSTEMS[name]
    if s["bank"] <= 0: return 0
    if fixed: return int(f * s["bank"] // 1000 * 1000)
    if s["unit"] is None or s["idx"] == 0: s["unit"] = f * s["bank"]
    amt = s["unit"] * seq[min(s["idx"], len(seq) - 1)]
    return int(min(amt, s["bank"]) // 1000 * 1000)


LOWVOL, LOWVOL_PEN, TIME_PEN = 1_000, 0.01, 0.0005  # table3


def best_combo(c):
    """table3 — 종목 무관 '기대값 점수'로 가장 좋은 조합 1개.
    다리별 공정확률 추정: ① The Odds API 다수 업체 합의(fair_p) ② 없으면 Polymarket 중간가격(mid)
    다리 엣지 = 배당 x 공정확률 - 1 (거래량 $1k 미만이면 -1% 불확실성 감점)
    묶음 기대값 = (1+e1)(1+e2) - 1 - 0.05%x(마지막 경기까지 시간) → 최대값 선택. 묶음 1.90~2.20, 24시간 내."""
    import odds_ref as R
    now = PM.now_utc()
    c = c[c.ko < now + timedelta(hours=HORIZON_H)].sort_values("vol", ascending=False).head(120).reset_index(drop=True)
    c = R.match(c)
    c["p_hat"] = c.fair_p.where(c.fair_p.notna(), c["mid"].astype(float))
    c["src"] = np.where(c.fair_p.notna(), "시장합의", "PM중간가")
    c["edge"] = c.odds * c.p_hat - 1 - np.where(c.vol < LOWVOL, LOWVOL_PEN, 0)
    best = None
    for a, b in combinations(c.itertuples(), 2):
        if a.title == b.title: continue
        o = a.odds * b.odds
        if not (ODDS_BAND[0] <= o <= ODDS_BAND[1]): continue
        hours = max((max(a.ko, b.ko) - now).total_seconds() / 3600, 0)
        score = (1 + a.edge) * (1 + b.edge) - 1 - TIME_PEN * hours
        if best is None or score > best[0]: best = (score, [a, b], o)
    if not best: return None
    mode = "value" if all(r.src == "시장합의" for r in best[1]) else "ev"
    return sorted(best[1], key=lambda r: r.ko), best[2], mode


def cmd_pick(st, legs):
    if len(legs) and (legs.status == "open").any():
        print("[픽] 진행 중인 판이 있어 대기합니다 (한 테이블 규칙)."); return legs
    c = PM.candidates()
    if len(legs): c = c[~c.market_id.isin(set(legs.market_id))]
    b = best_combo(c) if len(c) else None
    if not b: print(f"[픽] {HORIZON_H}시간 안에 조건(묶음 1.90~2.20)에 맞는 조합이 없습니다."); return legs
    grp, odds, mode = b
    stakes = {k: stake(k, st["systems"][k]) for k in SYSTEMS}
    cid = f"T{datetime.now(PM.KST):%Y%m%d%H%M}"
    stamp = datetime.now(PM.KST).strftime("%Y-%m-%d %H:%M")
    m = st["systems"][MAIN]
    print(f"[픽] 선정 방식: 기대값 점수 최대 (공정확률: {'두 다리 모두 시장합의' if mode == 'value' else '시장합의/PM중간가 혼합'})")
    print(f"[픽] {cid} 2폴더 묶음배당 {odds:.2f} · 메인 {SYSTEMS[MAIN][0]} {m['idx']+1}번째 칸 · 가상베팅 {stakes[MAIN]:,}원")
    for r in grp:
        kst = pd.Timestamp(r.ko).tz_localize("UTC").tz_convert(PM.KST)
        ref = f" · {r.src} {r.p_hat*100:.1f}% → 엣지 {r.edge*100:+.1f}%"
        print(f"   {kst:%m-%d %H:%M}(KST) [{r.tag}] {r.title} → {r.pick} @{r.odds:.2f} (거래량 ${r.vol:,}{ref})")
    print("   비교: " + ", ".join(f"{SYSTEMS[k][0].split('· ')[1]} {v:,}" for k, v in stakes.items() if k != MAIN))
    rows = [dict(created_kst=stamp, combo=cid, combo_odds=f"{odds:.3f}", tag=r.tag, market_id=r.market_id,
                 outcome_idx=r.outcome_idx, title=r.title, pick=r.pick, ko=str(r.ko), odds=f"{r.odds:.3f}", vol=r.vol,
                 status="open", win="", pick_mode=mode, fair_p=f"{r.fair_p:.4f}" if r.fair_p == r.fair_p else "",
                 edge=f"{r.edge:.4f}" if r.edge == r.edge else "", ref=r.ref, p_hat=f"{r.p_hat:.4f}", p_src=r.src, **{f"stake_{k}": v for k, v in stakes.items()}) for r in grp]
    return pd.concat([legs, pd.DataFrame(rows).astype(str)], ignore_index=True)


def cmd_settle(st, legs):
    if not len(legs) or not (legs.status == "open").any():
        print("[정산] 대기 중인 판 없음"); return legs
    for i in legs[(legs.status == "open") & (legs.win == "")].index:
        try:
            m = PM.get(f"/markets/{legs.at[i, 'market_id']}")
        except Exception as e:
            print(f"  조회 오류: {e}"); continue
        prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        idx = int(legs.at[i, "outcome_idx"])
        proposed = str(m.get("umaResolutionStatus") or "").lower() in ("proposed", "resolved")  # 결과 제안됨(이의제기 대기) 포함
        if prices and ((m.get("closed") and max(prices) >= 0.99) or (proposed and max(prices) >= 0.995)):
            legs.at[i, "win"] = "1" if prices[idx] >= 0.99 else "0"
        elif (m.get("closed") and prices and abs(prices[idx] - 0.5) < 0.01) or \
                pd.to_datetime(legs.at[i, "ko"]) < PM.now_utc() - timedelta(days=PM.VOID_DAYS):
            legs.at[i, "win"] = "V"
    for cid in legs.loc[legs.status == "open", "combo"].unique():
        m = legs.combo == cid; lw = legs.loc[m, "win"]
        if not ((lw == "0").any() or (lw != "").all()): continue
        win = (lw != "0").all() and (lw != "").all()
        odds = float(np.prod([float(o) for o, w in zip(legs.loc[m, "odds"], lw) if w == "1"] or [1.0]))
        msg = []
        for k, (name, seq, mode, f, fixed) in SYSTEMS.items():
            s = st["systems"][k]; amt = float(legs.loc[m, f"stake_{k}"].iloc[0] or 0)
            pnl = amt * (odds - 1) if win else -amt
            s["bank"] += pnl
            if not fixed:
                if win:
                    nxt = s["idx"] + 1
                    s["idx"] = 0 if (mode == "reset" and nxt >= len(seq)) else min(nxt, len(seq) - 1 if mode == "stay" else nxt)
                else:
                    s["idx"] = 0
            if s["bank"] >= START * TARGET_X and s["locked"] == 0:  # 3배 도달 → 원금 분리
                s["bank"] -= START; s["locked"] = START; s["idx"] = 0
                print(f"  ★ {name}: 3배 도달! 원금 1,000만 분리 보관, 이익으로만 계속")
            msg.append(f"{k} {pnl:+,.0f}")
        legs.loc[m, "status"] = "won" if win else "lost"
        print(f"[정산] {cid} 묶음 {float(legs.loc[m,'combo_odds'].iloc[0]):.2f} {'적중' if win else '실패'} | " + ", ".join(msg))
    return legs


def cmd_status(st, legs):
    print(f"[현황·한 테이블] 각 베팅법 시작 1,000만 · 목표 3배(3,000만)")
    for k, (name, seq, mode, f, fixed) in SYSTEMS.items():
        s = st["systems"][k]; tot = s["bank"] + s["locked"]
        step = "" if fixed else f" · 다음 {s['idx']+1}번째 칸"
        print(f"  {name:22s} {tot:>13,.0f}원 (x{tot/START:.2f}){' [원금 분리됨]' if s['locked'] else ''}{step}")
    if len(legs):
        cb = legs.drop_duplicates("combo"); w, l = (cb.status == "won").sum(), (cb.status == "lost").sum()
        lg = legs[legs.win.isin(["0", "1"])]
        print(f"  판 {w}승 {l}패 (진행 {(cb.status=='open').sum()}) | 다리 적중 {int((lg.win=='1').sum())}/{len(lg)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    st, legs = load_state(), load_legs()
    if cmd in ("settle", "run"): legs = cmd_settle(st, legs)
    if cmd in ("pick", "run"): legs = cmd_pick(st, legs)
    if cmd != "status": save(st, legs)
    cmd_status(st, legs)
