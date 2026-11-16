"""
'바카라(-1.06%)보다 나은 구간' 자동 선정 + 검증.
구간 = 리그 x 결과(홈/무/원정) x 배당대(1.01~1.3, 1.3~1.5, 1.5~1.8, 1.8~2.2)
- 유럽 20리그: bet365 경기전 배당(B365H/D/A)
- 유럽 외 16리그: bet365 마감배당은 2025~만 있어 업체평균 마감(AvgC) 사용 → bet365 대비 보정(아래 GAP)
선정: 학습(~2020-06)에서 ROI > -1.06% 이고 n>=MIN_N → 검증(2020-07~)에서 합산 성적 확인
최종 화이트리스트(전체기간 기준 재선정)는 paper/whitelist.json 으로 저장 → paper_trade.py가 사용
"""
import glob, json, os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest as B

BACCARAT = -0.0106
MIN_N = 80
BANDS = [(1.01, 1.3), (1.3, 1.5), (1.5, 1.8), (1.8, 2.2)]
HERE = os.path.dirname(os.path.abspath(__file__))


def euro_legs():
    fr = []
    for p in sorted(glob.glob(os.path.join(B.RAW, "*.csv"))):
        d = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip", low_memory=False)
        d.columns = [c.replace("ï»¿", "").strip() for c in d.columns]
        div = os.path.basename(p)[5:-4]
        ts = pd.to_datetime(d.get("Date"), dayfirst=True, errors="coerce", format="mixed")
        for l in "HDA":
            fr.append(pd.DataFrame({"lg": div, "ts": ts, "side": l, "odds": pd.to_numeric(d.get("B365" + l), errors="coerce"),
                                    "win": (d.get("FTR") == l).astype(int), "ok": d.get("FTR").notna()}))
    x = pd.concat(fr); return x[x.ok & x.odds.notna() & x.ts.notna()].drop(columns="ok")


def world_legs():
    fr = []
    for p in sorted(glob.glob(os.path.join(HERE, "data", "new", "*.csv"))):
        d = pd.read_csv(p, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
        ts = pd.to_datetime(d.Date, dayfirst=True, errors="coerce", format="mixed")
        lg = d.Country.str.strip() + "|" + d.League.str.strip()
        for l in "HDA":
            fr.append(pd.DataFrame({"lg": lg, "ts": ts, "side": l, "odds": pd.to_numeric(d.get("AvgC" + l), errors="coerce"),
                                    "b365": pd.to_numeric(d.get("B365C" + l), errors="coerce"),
                                    "win": (d.Res == l).astype(int), "ok": d.Res.notna()}))
    x = pd.concat(fr); return x[x.ok & x.odds.notna() & x.ts.notna()].drop(columns="ok")


def band(o):
    for lo, hi in BANDS:
        if lo <= o <= hi: return f"{lo}-{hi}"
    return None


def seg_table(x):
    x = x.copy(); x["band"] = x.odds.map(band); x = x.dropna(subset=["band"])
    x["r"] = x.win * x.odds - 1
    t = x.groupby(["lg", "side", "band"]).r.agg(["size", "mean", "std"]).reset_index()
    return x, t


if __name__ == "__main__":
    E = euro_legs(); W = world_legs()
    # bet365가 업체평균보다 얼마나 짠지(2025~ 겹치는 구간) → 유럽 외 리그 보정
    ov = W.dropna(subset=["b365"]); ov = ov[ov.odds.between(1.01, 2.2)]
    GAP = (ov.b365 / ov.odds).mean() - 1
    print(f"유럽 외 리그: bet365 마감배당 / 업체평균 = {1+GAP:.4f} (bet365가 평균 대비 {GAP*100:+.2f}%)")
    W["odds"] = W.odds * (1 + GAP)
    ALL = pd.concat([E, W.drop(columns="b365")], ignore_index=True)
    tr, te = ALL[ALL.ts < "2020-07-01"], ALL[ALL.ts >= "2020-07-01"]
    trx, trt = seg_table(tr); tex, tet = seg_table(te)
    sel = trt[(trt["size"] >= MIN_N) & (trt["mean"] > BACCARAT)][["lg", "side", "band"]]
    print(f"\n학습구간 구간 {len(trt):,}개 중 n>={MIN_N} & ROI>{BACCARAT*100:.2f}%: {len(sel)}개 선정")
    m = tex.merge(sel, on=["lg", "side", "band"])
    rest = tex.merge(sel, on=["lg", "side", "band"], how="left", indicator=True)
    rest = rest[rest._merge == "left_only"]
    def show(name, r):
        print(f"  {name:28s} {len(r):7,d}건  ROI {r.mean()*100:+6.2f}% (±{1.96*r.std()/np.sqrt(len(r))*100:.2f})")
    print("[검증구간 2020-07~ 성적]")
    show("선정된 구간 합산", m.r); show("선정 안 된 나머지", rest.r); show("바카라 뱅커", pd.Series([BACCARAT]))
    for b_ in [f"{lo}-{hi}" for lo, hi in BANDS]:
        show(f"  선정구간 중 배당 {b_}", m[m.band == b_].r)
    # 최종 화이트리스트: 전체기간, 더 엄격히(n>=150, ROI>-1.06%, 그리고 검증구간도 >-1.06% 또는 검증표본<30)
    ax, at = seg_table(ALL)
    te_t = tet.set_index(["lg", "side", "band"])
    wl = []
    for row in at[(at["size"] >= 150) & (at["mean"] > BACCARAT)].itertuples():
        k = (row.lg, row.side, row.band)
        tem = te_t["mean"].get(k, np.nan); ten = te_t["size"].get(k, 0)
        if ten >= 30 and tem <= BACCARAT: continue
        wl.append(dict(lg=row.lg, side=row.side, band=row.band, n=int(row.size), roi=round(row.mean, 4),
                       test_n=int(ten), test_roi=None if np.isnan(tem) else round(tem, 4)))
    wl.sort(key=lambda d: -d["roi"])
    os.makedirs(os.path.join(HERE, "paper"), exist_ok=True)
    json.dump({"baccarat": BACCARAT, "world_gap": GAP, "segments": wl}, open(os.path.join(HERE, "paper", "whitelist.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"\n최종 화이트리스트 {len(wl)}개 구간 (전체기간 n>=150, ROI>바카라, 검증구간에서 무너지지 않은 것)")
    for d in wl:
        print(f"  {d['lg']:28s} {d['side']} {d['band']:9s} n={d['n']:5d} ROI {d['roi']*100:+5.1f}%  검증 n={d['test_n']} "
              + ("-" if d['test_roi'] is None else f"{d['test_roi']*100:+.1f}%"))
