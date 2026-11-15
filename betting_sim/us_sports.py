"""
미국 종목(NBA/NFL/NHL/MLB/NCAA농구) 과거 마감배당 분석.
출처: sportsbookreviewsonline.com 공개 아카이브 (단일 기준 라인).
- 머니라인(승패): 마감 ML을 소수배당으로 바꿔 '아무 선택 없이' 걸었을 때 ROI를 배당구간/홈원정별로
- 핸디캡(스프레드)·언오버: 가격이 없어서 표준 -110(소수 1.909) 가정
사용: python3 us_sports.py
"""
import glob, os, re, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
D = os.path.join(os.path.dirname(__file__), "data", "sbr")
STD = 1 + 100 / 110


def num(x):
    if isinstance(x, str):
        x = x.strip().lower()
        if x in ("pk", "pick", "p"): return 0.0
        try: return float(x)
        except ValueError: return np.nan
    return float(x) if pd.notna(x) else np.nan


def am2dec(a):
    a = num(a)
    if not np.isfinite(a) or abs(a) < 100: return np.nan
    return 1 + (a / 100 if a > 0 else 100 / -a)


def read(p):
    if p.endswith(".xlsx"):
        t = pd.read_excel(p)
    else:
        t = pd.read_html(p)[0]; t.columns = t.iloc[0]; t = t.iloc[1:]
    t.columns = [str(c).strip() for c in t.columns]
    return t.reset_index(drop=True)


def games(sport):
    pats = {"nba": "nba-odds-*", "nfl": "nfl-odds-*", "nhl": "nhl-odds-*", "mlb": "mlb-odds-*", "ncaab": "ncaa-basketball-*"}
    out = []
    for p in sorted(glob.glob(os.path.join(D, pats[sport]))):
        try:
            t = read(p)
        except Exception:
            continue
        if "VH" not in t: continue
        t = t[t["VH"].isin(["V", "H", "N"])].reset_index(drop=True)
        if len(t) % 2: t = t.iloc[:-1]
        v, h = t.iloc[0::2].reset_index(drop=True), t.iloc[1::2].reset_index(drop=True)
        g = pd.DataFrame({"season": os.path.basename(p), "vf": v["Final"].map(num), "hf": h["Final"].map(num),
                          "neutral": v["VH"].eq("N")})
        mlcol = "ML" if "ML" in t else "Close"
        g["vml"] = v[mlcol].map(am2dec); g["hml"] = h[mlcol].map(am2dec)
        if sport in ("nba", "nfl", "ncaab"):  # Close 열: 작은 값 = 스프레드(그 팀이 정배), 큰 값 = 토탈
            a, b = v["Close"].map(num).to_numpy(), h["Close"].map(num).to_numpy()
            vfav = a < b
            g["spread"] = np.where(vfav, a, b)         # 정배가 주는 점수
            g["total"] = np.where(vfav, b, a)
            g["fav_is_home"] = ~vfav
        out.append(g)
    return pd.concat(out, ignore_index=True).dropna(subset=["vf", "hf"])


def roi(ret):
    ret = np.asarray(ret, float); ret = ret[np.isfinite(ret)]
    if len(ret) < 200: return None
    r = ret - 1
    return len(r), r.mean() * 100, 1.96 * r.std() / np.sqrt(len(r)) * 100


def fmt(name, x):
    return f"  {name:24s} " + ("표본부족" if x is None else f"{x[0]:7,d}건  {x[1]:+6.2f}% (±{x[2]:.1f})")


def analyze(sport):
    g = games(sport)
    print(f"\n######## {sport.upper()}  경기 {len(g):,} ({g.season.iloc[0]} ~ {g.season.iloc[-1]})")
    m = g.dropna(subset=["vml", "hml"])
    m = m[m.vf != m.hf]
    over = (1 / m.vml + 1 / m.hml - 1).mean() * 100
    print(f" [머니라인] 평균 마진 {over:.1f}%")
    legs = pd.concat([
        pd.DataFrame({"odds": m.vml, "win": m.vf > m.hf, "side": "원정"}),
        pd.DataFrame({"odds": m.hml, "win": m.hf > m.vf, "side": "홈"})])
    legs["ret"] = np.where(legs.win, legs.odds, 0.0)
    for s in ["홈", "원정"]:
        print(fmt(s, roi(legs.loc[legs.side == s, "ret"])))
    bands = [1, 1.3, 1.5, 1.8, 2.2, 3, 5, 100]
    legs["band"] = pd.cut(legs.odds, bands)
    for b, x in legs.groupby("band", observed=True):
        print(fmt(f"배당 {b}", roi(x.ret)))
    if "spread" in g:
        s = g.dropna(subset=["spread"]); s = s[s.spread > 0]
        fav_m = np.where(s.fav_is_home, s.hf - s.vf, s.vf - s.hf) - s.spread
        res = pd.DataFrame({"fav": np.where(fav_m > 0, STD, np.where(fav_m == 0, 1, 0)),
                            "dog": np.where(fav_m < 0, STD, np.where(fav_m == 0, 1, 0)), "fh": s.fav_is_home.values})
        print(" [핸디캡 -110 가정]")
        print(fmt("정배(점수 주는 쪽)", roi(res.fav))); print(fmt("역배(점수 받는 쪽)", roi(res.dog)))
        print(fmt("홈 역배", roi(res.dog[~res.fh]))); print(fmt("원정 역배", roi(res.dog[res.fh])))
        tot = (s.vf + s.hf - s.total)[(s.total > s.spread * 3) & s.total.notna()]  # 토탈 없는 경기 제외
        print(fmt("오버", roi(np.where(tot > 0, STD, np.where(tot == 0, 1, 0)))))
        print(fmt("언더", roi(np.where(tot < 0, STD, np.where(tot == 0, 1, 0)))))


if __name__ == "__main__":
    for sp in ["nba", "nfl", "nhl", "mlb", "ncaab"]:
        try:
            analyze(sp)
        except Exception as e:
            print(sp, "오류:", e)
