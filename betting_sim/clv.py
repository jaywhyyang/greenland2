"""
CLV(마감 배당 대비 가치) 기록 — 조회 전용 공개 API (Polymarket CLOB prices-history)

- 마감 확률 close_p = 경기 시작 시각(ko) 직전 마지막 시세(해당 결과 쪽 토큰)
- CLV = 우리가 산 배당 x close_p - 1   (+면 시장 마감가보다 싸게 산 것 = 장기적으로 이기는 신호)
- 스캔이 2시간마다라도 시세 이력을 거꾸로 조회하므로 정확한 시작 직전 가격을 얻는다.

  python3 clv.py          # 두 장부(paper_pm, paper_table) 전체 CLV 요약
"""
import json, subprocess, sys
import numpy as np, pandas as pd
import pm_trade as PM

CLOB = "https://clob.polymarket.com/prices-history"


def _curl(url):
    out = subprocess.run(["curl", "-s", "--compressed", "--max-time", "30", url], capture_output=True, text=True).stdout
    return json.loads(out)


def closing_prob(market_id, outcome_idx, ko):
    """ko(UTC naive 문자열) 직전 마지막 시세. 없으면 None."""
    m = PM.get(f"/markets/{market_id}")
    toks = json.loads(m.get("clobTokenIds") or "[]")
    if len(toks) <= int(outcome_idx): return None
    t1 = int(pd.Timestamp(ko).tz_localize("UTC").timestamp())
    h = _curl(f"{CLOB}?market={toks[int(outcome_idx)]}&startTs={t1 - 12 * 3600}&endTs={t1}&fidelity=1").get("history", [])
    h = [x for x in h if x["t"] <= t1]
    return float(h[-1]["p"]) if h else None


def fill(legs):
    """경기가 시작된 다리 중 close_p가 비어 있으면 채운다. 열: close_p, clv"""
    for c in ("close_p", "clv"):
        if c not in legs.columns: legs[c] = ""
    now = PM.now_utc()
    for i in legs.index:
        if legs.at[i, "close_p"] != "" or pd.to_datetime(legs.at[i, "ko"]) > now: continue
        try:
            p = closing_prob(legs.at[i, "market_id"], legs.at[i, "outcome_idx"], legs.at[i, "ko"])
        except Exception as e:
            print(f"  [CLV] 조회 오류 {legs.at[i, 'market_id']}: {e}"); continue
        if p and 0 < p < 1:
            legs.at[i, "close_p"] = f"{p:.4f}"
            legs.at[i, "clv"] = f"{float(legs.at[i, 'odds']) * p - 1:.4f}"
    return legs


def summary(legs, label):
    d = legs[legs.get("clv", pd.Series(dtype=str)).astype(str) != ""] if "clv" in legs else legs.iloc[0:0]
    if not len(d): print(f"  [CLV·{label}] 기록 없음"); return
    v = d.clv.astype(float)
    se = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else float("nan")
    print(f"  [CLV·{label}] 다리 {len(v)}개 · 평균 {v.mean()*100:+.2f}% (±{se*100:.2f}) · 마감가보다 싸게 산 비율 {(v > 0).mean()*100:.0f}%")


if __name__ == "__main__":
    for f, label in [("paper_pm/legs.csv", "기존 장부"), ("paper_table/legs.csv", "한 테이블")]:
        l = fill(pd.read_csv(f, dtype=str).fillna(""))
        if "--save" in sys.argv: l.to_csv(f, index=False)
        summary(l, label)
        for _, r in l[l.clv != ""].iterrows():
            print(f"     {r.ko[5:16]} {r.pick[:24]:24s} 산 배당 {float(r.odds):.3f} → 마감확률 {float(r.close_p):.3f} (마감배당 {1/float(r.close_p):.3f}) CLV {float(r.clv)*100:+.1f}% 결과 {r.win or '-'}")
