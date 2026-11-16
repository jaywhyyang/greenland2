"""
NFL 원정 역배 핸디캡(ATS) 세부 분석. 가격은 표준 -110(1.909) 가정.
- 각 경기: 개막/마감 스프레드(홈 기준), 결과
- 쪼개기: 받는 점수 크기, 핵심 숫자(3, 7), 라인 이동 방향, 학습(2007-14)/검증(2015-21)
"""
import glob, os, re, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from us_sports import pair_rows, num, read, D, STD


def load():
    out = []
    for p in sorted(glob.glob(os.path.join(D, "nfl-odds-*.html"))):
        yr = int(re.search(r"(\d{4})", os.path.basename(p)).group(1))
        t = read(p); t.columns = [str(c).strip() for c in t.columns]
        v, h = pair_rows(t)
        g = pd.DataFrame({"yr": yr, "neutral": v.VH.eq("N"), "vf": v.Final.map(num), "hf": h.Final.map(num)})
        for col in ["Open", "Close"]:
            a, b = v[col].map(num).to_numpy(), h[col].map(num).to_numpy()
            vfav = a < b
            sp = np.where(vfav, a, b)
            g[col.lower()] = np.where(vfav, -sp, sp)  # 원정팀이 받는 점수(+면 원정 역배, 원정이 정배면 음수)
            g[col.lower() + "_ok"] = np.minimum(a, b) < 30
        out.append(g)
    g = pd.concat(out, ignore_index=True).dropna()
    g = g[g.open_ok & g.close_ok & ~g.neutral]
    g["margin"] = g.vf - g.hf + g.close        # 원정이 점수 받은 후 마진
    g["ret"] = np.where(g.margin > 0, STD, np.where(g.margin == 0, 1.0, 0.0))
    g["move"] = g.close - g.open                # +면 원정 역배가 점수를 더 받게 됨(돈이 홈 정배로)
    return g


def show(name, x):
    r = x.ret - 1
    if len(r) < 40: print(f"  {name:34s} {len(r):4d}건  (표본부족)"); return
    w = (x.margin > 0).sum() / max((x.margin != 0).sum(), 1)
    print(f"  {name:34s} {len(r):4d}건  커버 {w*100:4.1f}%  ROI {r.mean()*100:+6.2f}% (±{1.96*r.std()/np.sqrt(len(r))*100:4.1f})")


if __name__ == "__main__":
    g = load()
    dogs = g[g.close > 0]
    print(f"NFL {len(g):,}경기 중 원정 역배 {len(dogs):,}경기 ({g.yr.min()}~{g.yr.max()}), 손익분기 커버율 52.4%\n")
    for lab, d in [("전체", dogs), ("학습 2007-14", dogs[dogs.yr <= 2014]), ("검증 2015-21", dogs[dogs.yr >= 2015])]:
        print(f"[{lab}]")
        show("원정 역배 전체", d)
        show("받는 점수 0.5~2.5", d[d.close <= 2.5])
        show("받는 점수 3 (핵심숫자)", d[d.close == 3])
        show("받는 점수 3.5~6.5", d[(d.close >= 3.5) & (d.close <= 6.5)])
        show("받는 점수 7 (핵심숫자)", d[d.close == 7])
        show("받는 점수 7.5 이상", d[d.close >= 7.5])
        show("라인이 역배 쪽으로 이동(점수 감소)", d[d.move < 0])
        show("라인 그대로", d[d.move == 0])
        show("라인이 정배 쪽으로 이동(점수 증가)", d[d.move > 0])
        print()
