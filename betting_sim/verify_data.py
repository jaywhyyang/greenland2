# 실행: betting_sim 폴더에서 python3 verify_data.py
# 모든 결과(H/D/A)에 1씩 걸면 기대 회수율 = 평균(1/overround)에 근사 → 실제 회수율과 비교
import glob, os, numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
R="data/raw"; rows=[]
for p in sorted(glob.glob(R+"/*.csv")):
    d=pd.read_csv(p,encoding="latin-1",on_bad_lines="skip",low_memory=False)
    d.columns=[c.replace("ï»¿","") for c in d.columns]
    if "B365H" not in d: continue
    o=d[["B365H","B365D","B365A"]].apply(pd.to_numeric,errors="coerce"); ok=o.notna().all(1)&d.FTR.isin(["H","D","A"])
    d,o=d[ok],o[ok]
    ov=(1/o).sum(1)
    ret=sum(np.where(d.FTR==l,o["B365"+l],0) for l in "HDA")/3
    rows.append(dict(f=os.path.basename(p),n=len(d),theory=(1/ov).mean(),actual=ret.mean(),bad=(ov<1).sum(),
                     dup=d.duplicated(["Date","HomeTeam","AwayTeam"]).sum()))
t=pd.DataFrame(rows)
print(f"유럽 {len(t)}개 파일, {t.n.sum():,}경기")
print(f"  이론 회수율(1/마진) {np.average(t.theory,weights=t.n)*100:.2f}%  vs  실제 회수율 {np.average(t.actual,weights=t.n)*100:.2f}%")
print(f"  마진<0(입력오류 의심) {t.bad.sum()}경기, 중복 {t.dup.sum()}경기")
t["season"]=t.f.str[:4]
g=t.groupby("season").apply(lambda x: pd.Series({"n":x.n.sum(),"이론":np.average(x.theory,weights=x.n)*100,"실제":np.average(x.actual,weights=x.n)*100}))
print(g.round(2).to_string())
