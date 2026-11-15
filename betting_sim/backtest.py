"""
1단계 백테스트: '가상 샘플 사이트'(bet365 배당 x (1-추가마진)) vs Pinnacle 공정확률.

- 결정 시점 정보만 사용: bet365(B365H/D/A)와 Pinnacle(PSH/D/A)은 football-data가 같은 시각에 수집한 배당.
- Pinnacle 마감배당(PSCH/D/A)은 결정에 쓰지 않고 CLV(마감 대비 가치) 평가에만 사용.
- 정산은 실제 경기결과(FTR).
- 한 경기당 엣지가 가장 큰 결과 하나만 베팅. 경기는 날짜/시간 순서대로 순차 처리.

사용: python3 backtest.py [--margin 0.02] [--thr 0.02] [--split 2020-07-01]
"""
import argparse, glob, os
import numpy as np
import pandas as pd

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
BUDGET = 10_000_000
TARGET = 100_000_000


def load():
    frames = []
    for p in sorted(glob.glob(os.path.join(RAW, "*.csv"))):
        try:
            df = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip")
        except Exception:
            continue
        need = ["Date", "FTR", "B365H", "B365D", "B365A", "PSH", "PSD", "PSA"]
        if not all(c in df.columns for c in need):
            continue
        keep = need + [c for c in ["Time", "Div", "HomeTeam", "AwayTeam", "PSCH", "PSCD", "PSCA"] if c in df.columns]
        frames.append(df[keep])
    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce", format="mixed")
    df["Time"] = df.get("Time", pd.Series(index=df.index)).fillna("15:00")
    df["ts"] = pd.to_datetime(df["Date"].dt.strftime("%Y-%m-%d") + " " + df["Time"].astype(str), errors="coerce")
    df = df.dropna(subset=["ts", "FTR", "B365H", "B365D", "B365A", "PSH", "PSD", "PSA"])
    for c in ["B365H", "B365D", "B365A", "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[(df[["B365H", "B365D", "B365A", "PSH", "PSD", "PSA"]] > 1.01).all(axis=1)]
    return df.sort_values("ts").reset_index(drop=True)


def devig(o):
    """곱셈(비례) 방식으로 마진 제거한 확률."""
    inv = 1.0 / o
    return inv / inv.sum(axis=1, keepdims=True)


def find_bets(df, margin, thr, max_odds=6.0):
    venue = df[["B365H", "B365D", "B365A"]].to_numpy() * (1 - margin)
    fair = devig(df[["PSH", "PSD", "PSA"]].to_numpy())
    edge = venue * fair - 1
    edge[venue > max_odds] = -1  # 너무 높은 배당 제외(모델 오차 큼)
    k = edge.argmax(axis=1)
    e = edge[np.arange(len(df)), k]
    sel = e > thr
    out = df.loc[sel, ["ts", "Div", "HomeTeam", "AwayTeam", "FTR"]].copy()
    out["pick"] = np.array(list("HDA"))[k[sel]]
    out["odds"] = venue[sel, k[sel]]
    out["p"] = fair[sel, k[sel]]
    out["edge"] = e[sel]
    out["win"] = (out["pick"] == out["FTR"]).astype(int)
    if "PSCH" in df.columns:
        close = df[["PSCH", "PSCD", "PSCA"]].to_numpy()
        ok = np.isfinite(close).all(axis=1) & (close > 1.01).all(axis=1)
        cf = np.full_like(close, np.nan)
        cf[ok] = devig(close[ok])
        out["clv"] = out["odds"].to_numpy() * cf[sel, k[sel]] - 1
    return out.reset_index(drop=True)


# ---------------- 베팅법 ----------------
def kelly_frac(p, o):
    return max(0.0, (p * o - 1) / (o - 1))


def simulate(bets, strat, cap=None, limit_after=None, limit_cap=None):
    """bets 순서대로 자금 변화. cap: 1회 최대 베팅액(원). limit_after: 누적이익이 이 값 넘으면 cap을 limit_cap으로(계정 제한)."""
    p = bets["p"].to_numpy(); o = bets["odds"].to_numpy(); w = bets["win"].to_numpy()
    n = len(bets)
    hist = np.empty(n)
    # 바벨: core(켈리) + pot(파롤리)
    core = BUDGET * strat.get("core_share", 1.0)
    pot = BUDGET - core
    streak = 0; cur_stake = None
    limited = False
    for i in range(n):
        bank = core + pot
        c = cap
        if limit_after is not None and (limited or bank - BUDGET > limit_after):
            limited = True; c = limit_cap
        # core
        s_core = 0.0
        if strat["core"] == "flat":
            s_core = strat["flat"] * core
        elif strat["core"] == "kelly":
            s_core = strat["kf"] * kelly_frac(p[i], o[i]) * core
        # paroli pot
        s_pot = 0.0
        if pot > 0 and strat.get("paroli_steps"):
            if streak == 0:
                cur_stake = strat["paroli_base"] * pot
            s_pot = min(cur_stake, pot)
        tot = s_core + s_pot
        if c is not None and tot > c:  # 한도 초과 시 비례 축소
            r = c / tot; s_core *= r; s_pot *= r
        if w[i]:
            core += s_core * (o[i] - 1); pot += s_pot * (o[i] - 1)
            if s_pot > 0:
                streak += 1; cur_stake = s_pot * o[i]
                if streak >= strat["paroli_steps"]:
                    streak = 0
        else:
            core -= s_core; pot -= s_pot
            streak = 0
        hist[i] = core + pot
    return hist


STRATS = {
    "고정 1%":          dict(core="flat", flat=0.01),
    "1/4 켈리":          dict(core="kelly", kf=0.25),
    "1/2 켈리":          dict(core="kelly", kf=0.5),
    "파롤리 3단(기본2%)": dict(core="none", core_share=0.0, paroli_steps=3, paroli_base=0.02),
    "바벨 90/10":        dict(core="kelly", kf=0.25, core_share=0.9, paroli_steps=3, paroli_base=0.05),
    "바벨 80/20":        dict(core="kelly", kf=0.25, core_share=0.8, paroli_steps=3, paroli_base=0.05),
}


def summarize(name, bets, hist):
    final = hist[-1] if len(hist) else BUDGET
    peak = np.maximum.accumulate(np.r_[BUDGET, hist])
    mdd = ((np.r_[BUDGET, hist] - peak) / peak).min()
    hit = np.argmax(hist >= TARGET) if (hist >= TARGET).any() else None
    yrs = (bets["ts"].iloc[-1] - bets["ts"].iloc[0]).days / 365.25 if len(bets) else 1
    cagr = (final / BUDGET) ** (1 / max(yrs, 0.1)) - 1 if final > 0 else -1
    when = bets["ts"].iloc[hit].strftime("%Y-%m") if hit is not None else "-"
    return dict(전략=name, 최종=f"{final/1e6:,.1f}백만", 배수=f"x{final/BUDGET:.2f}", 연복리=f"{cagr*100:+.1f}%",
                최대낙폭=f"{mdd*100:.0f}%", 목표도달=when)


def report(bets, label, cap=None, limit_after=None, limit_cap=None):
    print(f"\n=== {label}: 베팅 {len(bets):,}건 ({bets['ts'].min():%Y-%m} ~ {bets['ts'].max():%Y-%m}) ===")
    if not len(bets):
        return
    roi = (bets["win"] * bets["odds"] - 1).mean()
    se = (bets["win"] * bets["odds"]).std() / np.sqrt(len(bets))
    print(f"평균배당 {bets['odds'].mean():.2f} | 적중률 {bets['win'].mean()*100:.1f}% | 단위 ROI {roi*100:+.2f}% (±{1.96*se*100:.2f}%p, 95%) "
          f"| 예상엣지 {bets['edge'].mean()*100:+.2f}%"
          + (f" | 평균 CLV {bets['clv'].mean()*100:+.2f}%" if "clv" in bets else ""))
    rows = [summarize(n, bets, simulate(bets, s, cap, limit_after, limit_cap)) for n, s in STRATS.items()]
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--thr", type=float, default=0.02)
    ap.add_argument("--split", default="2020-07-01")
    a = ap.parse_args()
    df = load()
    print(f"경기 {len(df):,}건 로드 ({df['ts'].min():%Y-%m} ~ {df['ts'].max():%Y-%m}), 추가마진 {a.margin*100:.1f}%, 엣지기준 {a.thr*100:.1f}%")
    bets = find_bets(df, a.margin, a.thr)
    tr = bets[bets["ts"] < a.split]; te = bets[bets["ts"] >= a.split].reset_index(drop=True)
    report(tr.reset_index(drop=True), "학습구간")
    report(te, "검증구간(손대지 않은 데이터)")
    report(te, "검증구간 + 계정제한(1회 50만원, 이익 300만 넘으면 1회 5만원)", cap=500_000, limit_after=3_000_000, limit_cap=50_000)
