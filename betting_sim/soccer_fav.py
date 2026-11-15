"""
후보 3: 축구 강팀(bet365 배당 1.0~1.3) — 한 사이트(bet365)에서만 베팅.
필터:
  A. bet365 배당 > 시장평균 공정가 (Avg/BbAv 마진제거)
  B. bet365 배당 > Pinnacle 공정가 (동시점 PS)
  C. 홈 강팀 / 원정 강팀
  D. 상위 리그 / 하위 리그
결정은 경기 전 배당만. 학습 ~2020-06 / 검증 2020-07~.
"""
import glob, os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest as B

TOP = {"E0", "SP1", "I1", "D1", "F1"}


def load():
    fr = []
    for p in sorted(glob.glob(os.path.join(B.RAW, "*.csv"))):
        d = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip", low_memory=False)
        d.columns = [c.replace("ï»¿", "").strip() for c in d.columns]
        o = pd.DataFrame({"div": os.path.basename(p)[5:-4], "Date": d.get("Date"), "FTR": d.get("FTR")})
        for l in "HDA":
            o["b" + l] = pd.to_numeric(d.get("B365" + l), errors="coerce")
            o["a" + l] = pd.to_numeric(d["Avg" + l] if "Avg" + l in d else d.get("BbAv" + l), errors="coerce")
            o["p" + l] = pd.to_numeric(d.get("PS" + l), errors="coerce")
        fr.append(o)
    df = pd.concat(fr, ignore_index=True).dropna(subset=["FTR", "bH", "bD", "bA", "aH", "aD", "aA"])
    df["ts"] = pd.to_datetime(df.Date, dayfirst=True, errors="coerce", format="mixed")
    return df.dropna(subset=["ts"]).reset_index(drop=True)


def legs(df):
    b = df[["bH", "bD", "bA"]].to_numpy(); fa = B.devig(df[["aH", "aD", "aA"]].to_numpy())
    pp = df[["pH", "pD", "pA"]].to_numpy(); ok = np.isfinite(pp).all(1) & (pp > 1.01).all(1)
    fp = np.full_like(pp, np.nan); fp[ok] = B.devig(pp[ok])
    rows = []
    for j, l in enumerate("HDA"):
        m = (b[:, j] > 1.0) & (b[:, j] <= 1.3)
        rows.append(pd.DataFrame({"ts": df.ts[m], "div": df["div"][m], "side": l, "odds": b[m, j],
                                  "e_avg": b[m, j] * fa[m, j] - 1, "e_pin": b[m, j] * fp[m, j] - 1,
                                  "win": (df.FTR[m] == l).astype(int)}))
    return pd.concat(rows, ignore_index=True).sort_values("ts").reset_index(drop=True)


def line(name, x):
    if len(x) < 50:
        print(f"  {name:36s} {len(x):6,d}건 (표본부족)"); return
    r = x.win * x.odds - 1
    yrs = max((x.ts.max() - x.ts.min()).days / 365.25, 0.5)
    print(f"  {name:36s} {len(x):6,d}건 (연 {len(x)/yrs:4.0f}) 적중 {x.win.mean()*100:4.1f}% 평균배당 {x.odds.mean():.2f} "
          f"ROI {r.mean()*100:+5.2f}% (±{1.96*r.std()/np.sqrt(len(r))*100:.1f})")


if __name__ == "__main__":
    L = legs(load())
    for lab, x in [("학습 ~2020-06", L[L.ts < "2020-07-01"]), ("검증 2020-07~", L[L.ts >= "2020-07-01"])]:
        print(f"\n[{lab}] bet365 배당 1.0~1.3 강팀")
        line("전부", x)
        line("홈 강팀", x[x.side == "H"]); line("원정 강팀", x[x.side == "A"])
        line("5대 리그", x[x["div"].isin(TOP)]); line("그 외 리그", x[~x["div"].isin(TOP)])
        for t in [-0.01, 0.0, 0.01]:
            line(f"A. 시장평균 대비 엣지 > {t*100:+.0f}%", x[x.e_avg > t])
        for t in [-0.01, 0.0, 0.01]:
            line(f"B. Pinnacle 대비 엣지 > {t*100:+.0f}%", x[x.e_pin > t])
        line("A>0 & 홈", x[(x.e_avg > 0) & (x.side == "H")])
        line("하위 50%: 시장평균 대비 엣지 최저", x[x.e_avg < x.e_avg.median()])
