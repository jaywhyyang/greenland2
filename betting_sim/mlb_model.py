"""
MLB 엣지 탐색 (2010~2021, sportsbookreviewsonline 공개 아카이브).
- 시장확률: 마감 머니라인 마진 제거
- 피처(전부 경기 전 정보만, 누설 없음):
    p_ra   : 선발투수의 직전 등판들 평균 실점(팀 실점 기준, 시즌 누적, 최소 3등판) 홈-원정 차
    t_rd   : 팀 직전 20경기 평균 득실차 홈-원정 차
    move   : 개막→마감 라인 이동(홈 시장확률 변화)
- 학습 2010~2016 로지스틱 회귀(시장 로짓 + 피처) → 검증 2017~2021에서
  모델확률 x 마감배당 - 1 > 기준 일 때만 베팅
"""
import glob, os, re, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from us_sports import pair_rows, num, am2dec, D

def load():
    rows = []
    for p in sorted(glob.glob(os.path.join(D, "mlb-odds-*.xlsx"))):
        yr = int(re.search(r"(\d{4})", os.path.basename(p)).group(1))
        t = pd.read_excel(p); t.columns = [str(c).strip() for c in t.columns]
        v, h = pair_rows(t)
        md = v["Date"].astype(int)
        g = pd.DataFrame({"yr": yr, "date": pd.to_datetime(dict(year=yr, month=md // 100, day=md % 100), errors="coerce"),
                          "vt": v["Team"], "ht": h["Team"], "vp": v["Pitcher"].astype(str), "hp": h["Pitcher"].astype(str),
                          "vf": v["Final"].map(num), "hf": h["Final"].map(num),
                          "vo": v["Open"].map(am2dec), "ho": h["Open"].map(am2dec),
                          "vc": v["Close"].map(am2dec), "hc": h["Close"].map(am2dec)})
        rows.append(g)
    g = pd.concat(rows, ignore_index=True).dropna(subset=["date", "vf", "hf", "vc", "hc"])
    g = g[g.vf != g.hf].sort_values("date", kind="stable").reset_index(drop=True)
    g["gid"] = np.arange(len(g))
    return g


def features(g):
    # 시장확률
    ih, iv = 1 / g.hc, 1 / g.vc
    g["pm"] = ih / (ih + iv)
    oh, ov = 1 / g.ho, 1 / g.vo
    g["pm_open"] = oh / (oh + ov)
    g["move"] = g.pm - g.pm_open
    # 팀/투수별 긴 형식
    long = pd.concat([
        pd.DataFrame({"gid": g.gid, "yr": g.yr, "team": g.ht, "pit": g.hp, "rf": g.hf, "ra": g.vf, "home": 1}),
        pd.DataFrame({"gid": g.gid, "yr": g.yr, "team": g.vt, "pit": g.vp, "rf": g.vf, "ra": g.hf, "home": 0})]).sort_values("gid")
    long["rd"] = long.rf - long.ra
    long["t_rd"] = long.groupby(["yr", "team"])["rd"].transform(lambda s: s.shift().rolling(20, min_periods=10).mean())
    grp = long.groupby(["yr", "pit"])["ra"]
    long["p_n"] = grp.cumcount()
    long["p_ra"] = grp.transform(lambda s: s.shift().expanding().mean())
    long.loc[long.p_n < 3, "p_ra"] = np.nan
    H = long[long.home == 1].set_index("gid"); V = long[long.home == 0].set_index("gid")
    g["t_rd"] = (H.t_rd - V.t_rd).reindex(g.gid).values
    g["p_ra"] = (V.p_ra - H.p_ra).reindex(g.gid).values   # +면 홈 선발이 더 좋음(원정 선발 실점이 더 많음)
    g["y"] = (g.hf > g.vf).astype(int)
    return g


def fit_logit(X, y, l2=1.0, it=50):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):  # 뉴턴법
        p = 1 / (1 + np.exp(-X @ w)); W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + l2 * np.eye(len(w)); H[0, 0] -= l2
        w -= np.linalg.solve(H, X.T @ (p - y) + l2 * np.r_[0, w[1:]])
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ w)))


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6); return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


if __name__ == "__main__":
    g = features(load()).dropna(subset=["pm", "move", "t_rd", "p_ra"]).reset_index(drop=True)
    g["lm"] = np.log(g.pm / (1 - g.pm))
    tr, te = g[g.yr <= 2016], g[g.yr >= 2017].reset_index(drop=True)
    print(f"경기: 학습 {len(tr):,} (2010-16) / 검증 {len(te):,} (2017-21)")
    sets = {"시장만": ["lm"], "시장+선발투수": ["lm", "p_ra"], "시장+팀폼": ["lm", "t_rd"],
            "시장+라인이동": ["lm", "move"], "전부": ["lm", "p_ra", "t_rd", "move"]}
    print("\n[정보 추가 효과] 검증구간 로그손실 (낮을수록 좋음)")
    best = None
    for name, cols in sets.items():
        mu, sd = tr[cols].mean(), tr[cols].std()
        w = fit_logit(((tr[cols] - mu) / sd).values, tr.y.values)
        pt = predict(w, ((te[cols] - mu) / sd).values)
        coef = ", ".join(f"{c}={x:+.3f}" for c, x in zip(cols, w[1:]))
        print(f"  {name:12s} {logloss(pt, te.y.values):.5f}   계수: {coef}")
        te[name] = pt
    print(f"  (시장 그대로)  {logloss(te.pm.values, te.y.values):.5f}")

    print("\n[베팅 시뮬레이션] 검증 2017-21, 모델확률 기준 엣지 > 기준 일 때 해당 팀 마감배당에 싱글")
    for name in ["시장+선발투수", "시장+라인이동", "전부"]:
        for lo, hi in [(1.0, 10.0), (1.3, 1.6), (1.8, 2.2)]:
            for thr in [0.02, 0.04]:
                eh = te[name] * te.hc - 1; ev = (1 - te[name]) * te.vc - 1
                pick_h = eh >= ev; e = np.where(pick_h, eh, ev); o = np.where(pick_h, te.hc, te.vc)
                win = np.where(pick_h, te.y == 1, te.y == 0)
                s = (e > thr) & (o >= lo) & (o <= hi)
                if s.sum() < 50: continue
                r = np.where(win[s], o[s], 0) - 1
                print(f"  {name:12s} 배당 {lo}~{hi:<4} 엣지>{thr*100:.0f}%  {s.sum():5d}건  적중 {win[s].mean()*100:4.1f}%  "
                      f"ROI {r.mean()*100:+5.2f}% (±{1.96*r.std()/np.sqrt(len(r))*100:.1f})")
