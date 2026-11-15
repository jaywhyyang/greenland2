"""
유럽 외/기타 축구 16개 리그 (football-data 'new' 파일: 일본, 미국, 브라질, 아르헨, 멕시코, 중국, 북유럽, 동유럽 등).
마감배당만 제공(B365C, PSC, MaxC, AvgC, BFEC) → 킥오프 직전 베팅 가정.
"""
import glob, os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest as B

D = os.path.join(os.path.dirname(__file__), "data", "new")


def load():
    fr = []
    for p in sorted(glob.glob(os.path.join(D, "*.csv"))):
        d = pd.read_csv(p, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
        d = d.loc[:, ~d.columns.str.startswith("Unnamed")]
        d["ts"] = pd.to_datetime(d.Date, dayfirst=True, errors="coerce", format="mixed")
        fr.append(d)
    df = pd.concat(fr, ignore_index=True)
    cols = [f"{k}C{l}" for k in ("Avg", "Max") for l in "HDA"]
    for c in cols + ["PSCH", "PSCD", "PSCA", "B365CH", "B365CD", "B365CA"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Res", "ts"] + cols)
    return df[(df[cols] > 1.01).all(1)].reset_index(drop=True)


def stat(name, odds, win, ts=None):
    odds, win = np.asarray(odds), np.asarray(win)
    if len(odds) < 100:
        print(f"  {name:34s} {len(odds):6,d}건 (표본부족)"); return
    r = win * odds - 1
    print(f"  {name:34s} {len(r):6,d}건  적중 {win.mean()*100:4.1f}%  ROI {r.mean()*100:+6.2f}% (±{1.96*r.std()/np.sqrt(len(r))*100:.1f})")


if __name__ == "__main__":
    df = load()
    print(f"{df.Country.nunique()}개국 {len(df):,}경기 ({df.ts.min():%Y}~{df.ts.max():%Y})")
    b = df[["AvgCH", "AvgCD", "AvgCA"]].to_numpy(); res = df.Res.to_numpy()  # 업체 평균 마감배당(bet365는 2025~만 있음)
    W = np.c_[res == "H", res == "D", res == "A"].astype(int)
    print("\n[1] 업체평균 마감배당에 조건 없이: 결과별")
    for j, l in enumerate(["홈", "무", "원정"]):
        stat(l, b[:, j], W[:, j])
    print("\n[2] 업체평균 배당구간별 (홈/무/원정 합산)")
    allo, allw = b.ravel(), W.ravel()
    for lo, hi in [(1, 1.3), (1.3, 1.5), (1.5, 1.8), (1.8, 2.2), (2.2, 3), (3, 5), (5, 10), (10, 999)]:
        m = (allo > lo) & (allo <= hi); stat(f"{lo}~{hi}", allo[m], allw[m])
    print("\n[3] 리그별: 홈 강팀(업체평균 1.0~1.3)")
    for c, x in df.groupby("Country"):
        m = x.AvgCH <= 1.3
        stat(c, x.AvgCH[m], (x.Res[m] == "H").astype(int))
    m = df.AvgCH <= 1.3
    stat("전체 홈 강팀 1.0~1.3", df.AvgCH[m], (df.Res[m] == "H").astype(int))
    print("\n[4] 가치 필터 (학습 ~2019 / 검증 2020~)")
    fa = B.devig(df[["AvgCH", "AvgCD", "AvgCA"]].to_numpy())
    mx = df[["MaxCH", "MaxCD", "MaxCA"]].to_numpy()
    pc = df[["PSCH", "PSCD", "PSCA"]].to_numpy(); ok = np.isfinite(pc).all(1) & (pc > 1.01).all(1)
    fp = np.full_like(pc, np.nan); fp[ok] = B.devig(pc[ok])
    for lab, per in [("학습", df.ts.dt.year <= 2019), ("검증", df.ts.dt.year >= 2020)]:
        per = per.to_numpy()[:, None].repeat(3, 1)
        for name, odds, fair, lo, hi in [("Kaunitz 최고배당 vs 평균, 1.8~2.2", mx, fa, 1.8, 2.2),
                                         ("Kaunitz 최고배당 vs 평균, 전체", mx, fa, 1.0, 10),
                                         ("최고배당 vs Pinnacle 공정가, 1.8~2.2", mx, fp, 1.8, 2.2)]:
            e = odds * fair - 1
            m = per & (e > 0) & (odds >= lo) & (odds <= hi)
            stat(f"{lab} {name}", odds[m], W[m])
