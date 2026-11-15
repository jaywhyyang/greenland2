import sys; sys.path.insert(0,'.')
import numpy as np, backtest as B
df=B.load()
print("마진  기준  최대배당 | 건수  단위ROI(95%CI)   CLV")
for m in [0.0,0.01,0.02]:
  for thr in [0.01,0.03]:
    for mo in [2.5,6.0]:
      b=B.find_bets(df,m,thr,max_odds=mo)
      if len(b)<30: print(f"{m:.2f} {thr:.2f} {mo:4.1f} | {len(b):5d}"); continue
      r=b.win*b.odds-1; se=r.std()/np.sqrt(len(b))
      print(f"{m:.2f} {thr:.2f} {mo:4.1f} | {len(b):5d}  {r.mean()*100:+5.2f}% (±{1.96*se*100:4.1f})  {b.clv.mean()*100:+.2f}%")
