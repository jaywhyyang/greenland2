"""
'바카라형' 2폴더 백테스트.
매 경기일마다: 샘플사이트 배당(bet365 x (1-마진))이 1.35~1.55인 결과 중
Pinnacle 공정확률 기준 엣지가 가장 큰 2개(서로 다른 경기)를 묶어 1판으로 본다.
→ 그 '판'들의 시퀀스에 고정/파롤리/바벨 적용.

사용: python3 baccarat_parlay.py [--margin 0.02] [--lo 1.35] [--hi 1.55] [--minedge -1]
"""
import argparse
import numpy as np, pandas as pd
import backtest as B


def build_hands(df, margin, lo, hi, min_edge):
    venue = df[["B365H", "B365D", "B365A"]].to_numpy() * (1 - margin)
    fair = B.devig(df[["PSH", "PSD", "PSA"]].to_numpy())
    res = df["FTR"].to_numpy()
    rows = []
    for j, lab in enumerate("HDA"):
        m = (venue[:, j] >= lo) & (venue[:, j] <= hi)
        idx = np.where(m)[0]
        rows.append(pd.DataFrame({"i": idx, "day": df["ts"].dt.normalize().to_numpy()[idx],
                                  "odds": venue[idx, j], "p": fair[idx, j],
                                  "win": (res[idx] == lab).astype(int)}))
    legs = pd.concat(rows)
    legs["edge"] = legs["odds"] * legs["p"] - 1
    legs = legs[legs["edge"] > min_edge].sort_values(["day", "edge"], ascending=[True, False])
    legs = legs.drop_duplicates("i")  # 한 경기 한 결과
    top = legs.groupby("day").head(2)
    g = top.groupby("day")
    hands = pd.DataFrame({"n": g.size(), "odds": g["odds"].prod(), "p": g["p"].prod(),
                          "win": g["win"].min(), "edge1": g["edge"].mean()})
    hands = hands[hands["n"] == 2].reset_index()
    hands["ev"] = hands["odds"] * hands["p"] - 1
    return hands


def run(h, kind, base=0.02, steps=3, share=1.0):
    """kind: flat / paroli. share: 파롤리에 쓰는 자금 비율(바벨이면 0.1, 나머지는 고정 1%)."""
    o = h["odds"].to_numpy(); w = h["win"].to_numpy()
    pot = B.BUDGET * share; core = B.BUDGET - pot
    streak = 0; stake = 0; out = np.empty(len(h))
    for i in range(len(h)):
        if kind == "flat":
            s = base * pot
        else:
            if streak == 0:
                stake = base * pot
            s = min(stake, pot)
        sc = 0.01 * core
        if w[i]:
            pot += s * (o[i] - 1); core += sc * (o[i] - 1)
            if kind == "paroli":
                streak += 1; stake = s * o[i]
                if streak >= steps: streak = 0
        else:
            pot -= s; core -= sc; streak = 0
        out[i] = pot + core
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--lo", type=float, default=1.35)
    ap.add_argument("--hi", type=float, default=1.55)
    ap.add_argument("--minedge", type=float, default=-1.0)
    a = ap.parse_args()
    df = B.load()
    h = build_hands(df, a.margin, a.lo, a.hi, a.minedge)
    se = (h["win"] * h["odds"]).std() / np.sqrt(len(h))
    roi = (h["win"] * h["odds"] - 1).mean()
    print(f"추가마진 {a.margin*100:.0f}% | 배당 {a.lo}~{a.hi} | 판 수 {len(h):,} ({h['day'].min():%Y-%m}~{h['day'].max():%Y-%m})")
    print(f"평균 묶음배당 {h['odds'].mean():.2f} | 적중률 {h['win'].mean()*100:.1f}% (손익분기 {100/h['odds'].mean():.1f}%) "
          f"| 판당 ROI {roi*100:+.2f}% (±{1.96*se*100:.1f}%p) | 예상 EV {h['ev'].mean()*100:+.2f}%")
    for name, kw in [("고정 2%", dict(kind="flat")), ("파롤리 3단 2%", dict(kind="paroli")),
                     ("파롤리 2단 2%", dict(kind="paroli", steps=2)),
                     ("바벨 90/10 (파롤리 10% 기본5%)", dict(kind="paroli", base=0.05, share=0.1))]:
        x = run(h, **kw)
        peak = np.maximum.accumulate(np.r_[B.BUDGET, x]); mdd = ((np.r_[B.BUDGET, x] - peak) / peak).min()
        print(f"  {name:28s} 최종 {x[-1]/1e6:7.1f}백만 (x{x[-1]/B.BUDGET:.2f}) 최고 {x.max()/1e6:6.1f}백만 최대낙폭 {mdd*100:.0f}%")
