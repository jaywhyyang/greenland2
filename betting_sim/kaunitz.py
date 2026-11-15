"""
Kaunitz et al.(2017) 'Beating the bookies with their own numbers' 방식 재현.
- 공정확률 = 여러 업체 평균배당(Avg / BbAv) 마진 제거
- 베팅 = 여러 업체 중 최고배당(Max / BbMx)이 공정가보다 thr 이상 높을 때만 '단일' 베팅
- 결정은 사전 배당(Max/Avg)만 사용, Pinnacle 마감배당은 CLV 평가에만 사용
- 학습(~2020-06) / 검증(2020-07~) 분리

사용: python3 kaunitz.py
"""
import glob, os
import numpy as np, pandas as pd
import backtest as B

COLS = {"max": ("MaxH", "MaxD", "MaxA", "BbMxH", "BbMxD", "BbMxA"),
        "avg": ("AvgH", "AvgD", "AvgA", "BbAvH", "BbAvD", "BbAvA")}


def load():
    fr = []
    for p in sorted(glob.glob(os.path.join(B.RAW, "*.csv"))):
        try:
            d = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip", low_memory=False)
        except Exception:
            continue
        d.columns = [c.replace("ï»¿", "").strip() for c in d.columns]
        out = pd.DataFrame({"Div": d.get("Div"), "Date": d.get("Date"), "Time": d.get("Time"), "FTR": d.get("FTR"),
                            "HomeTeam": d.get("HomeTeam"), "AwayTeam": d.get("AwayTeam")})
        for k, (n1, n2, n3, o1, o2, o3) in COLS.items():
            for lab, a, b in zip("HDA", (n1, n2, n3), (o1, o2, o3)):
                out[f"{k}{lab}"] = pd.to_numeric(d[a] if a in d else d.get(b), errors="coerce")
        for lab in "HDA":
            out[f"psc{lab}"] = pd.to_numeric(d.get(f"PSC{lab}"), errors="coerce")
        fr.append(out)
    df = pd.concat(fr, ignore_index=True)
    df["ts"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"].fillna("15:00").astype(str),
                              dayfirst=True, errors="coerce", format="mixed")
    oc = [f"{k}{l}" for k in ("max", "avg") for l in "HDA"]
    df = df.dropna(subset=["ts", "FTR"] + oc)
    df = df[(df[oc] > 1.01).all(axis=1)]
    return df.sort_values("ts").reset_index(drop=True)


def bets(df, thr, lo=1.0, hi=6.0):
    mx = df[["maxH", "maxD", "maxA"]].to_numpy()
    fair = B.devig(df[["avgH", "avgD", "avgA"]].to_numpy())
    edge = mx * fair - 1
    edge[(mx < lo) | (mx > hi)] = -9
    k = edge.argmax(1); e = edge[np.arange(len(df)), k]; s = e > thr
    o = df.loc[s, ["ts", "Div", "HomeTeam", "AwayTeam", "FTR"]].copy()
    o["pick"] = np.array(list("HDA"))[k[s]]; o["odds"] = mx[s, k[s]]; o["p"] = fair[s, k[s]]; o["edge"] = e[s]
    o["win"] = (o["pick"] == o["FTR"]).astype(int)
    pc = df[["pscH", "pscD", "pscA"]].to_numpy()
    ok = np.isfinite(pc).all(1) & (pc > 1.01).all(1)
    cf = np.full_like(pc, np.nan); cf[ok] = B.devig(pc[ok])
    o["clv"] = o["odds"].to_numpy() * cf[s, k[s]] - 1
    return o.reset_index(drop=True)


def line(b):
    r = b["win"] * b["odds"] - 1; se = r.std() / np.sqrt(len(b))
    return (f"{len(b):6,d}건 | 평균배당 {b['odds'].mean():.2f} | 적중 {b['win'].mean()*100:4.1f}% | "
            f"ROI {r.mean()*100:+5.2f}% (±{1.96*se*100:4.1f}) | CLV {b['clv'].mean()*100:+.2f}%")


if __name__ == "__main__":
    df = load()
    print(f"경기 {len(df):,} ({df['ts'].min():%Y-%m}~{df['ts'].max():%Y-%m})\n")
    print("[엣지 기준 x 배당구간 스캔]  학습(~2020-06) / 검증(2020-07~)")
    for lo, hi in [(1.0, 6.0), (1.8, 2.2)]:
        for thr in [0.0, 0.02, 0.04, 0.06]:
            b = bets(df, thr, lo, hi)
            tr, te = b[b.ts < "2020-07-01"], b[b.ts >= "2020-07-01"]
            print(f" 배당 {lo}~{hi} 엣지>{thr*100:.0f}%")
            print("   학습 " + line(tr)); print("   검증 " + line(te))
    for lo, hi, thr in [(1.0, 6.0, 0.04), (1.8, 2.2, 0.02)]:
        te = bets(df, thr, lo, hi); te = te[te.ts >= "2020-07-01"].reset_index(drop=True)
        B.report(te, f"검증구간 자금운용: 배당 {lo}~{hi}, 엣지>{thr*100:.0f}%")
