# -*- coding: utf-8 -*-
"""
kidsani_final.csv → kidsani_report.html

어린이 애니메이션(비직배 수입) 세그먼트 페이지.
아트하우스 페이지(build_arthouse_page.py)와 같은 디자인·계산 규칙을 쓰되,
이 세그먼트의 특징인 '주말 집중'이 눈에 보이도록 구성한다.
  · 일별 막대에서 금·토·일을 다른 색으로 칠한다
  · 주말 집중도(첫 주말 관객 ÷ 첫주 관객)를 지표로 노출한다
"""
import os
import csv
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "kidsani_final.csv")
ART = os.path.join(BASE, "arthouse_final.csv")
OUT = os.path.join(BASE, "kidsani_report.html")

NDAY = 15
DEF_MG, DEF_PA, DEF_UNIT = 0, 3000, 4200   # 만원, 만원, 원


def load():
    rows = []
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        if r["성적확정"] != "확정":
            continue          # 수집 종료일까지 상영 중이라 성적 미확정
        iv = lambda k: int(r[k]) if r.get(k) and r[k].strip() else 0
        fv = lambda k: float(r[k]) if r.get(k) and r[k].strip() else 0
        od = datetime.date(*map(int, r["개봉일"].split("-")))
        rows.append({
            "name": r["영화명"], "open": r["개봉일"], "wd": od.weekday(),
            "nat": r["대표국적"], "dir": r["감독"], "dist": r["배급사"],
            "scr": iv("개봉스크린수"),
            "s0": iv("개봉일좌석수"), "r0": fv("개봉일좌석판매율"),
            "sw": iv("첫주말좌석수"), "rw": fv("첫주말좌석판매율"),
            "wc": fv("주말집중도"),
            "fw": iv("첫주관객"), "cum": iv("최종누적관객"), "mult": fv("배수"),
            "c": [iv(f"D{i}") for i in range(NDAY)],
        })
    rows.sort(key=lambda r: -r["cum"])
    return rows


def art_stats():
    """비교용 아트하우스 요약 (같은 제외 규칙 적용)."""
    out = []
    for r in csv.DictReader(open(ART, encoding="utf-8-sig")):
        oy = int(r["개봉일"][:4])
        py = int(r["제작연도"]) if r["제작연도"].isdigit() else oy
        if oy - py >= 6 or r["직배여부"] == "직배":
            continue
        if "청소년관람불가" in r["등급"] and int(r["개봉스크린수"] or 0) < 20:
            continue
        out.append({"cum": int(r["최종누적관객"] or 0),
                    "r0": float(r["개봉일좌석판매율"] or 0),
                    "rw": float(r["첫주말좌석판매율"] or 0),
                    "mult": float(r["배수"] or 0)})
    return out


def med(v):
    v = sorted(x for x in v if x)
    return v[len(v) // 2] if v else 0


HTML = """<title>어린이 애니메이션 수입작 흥행 실적 · 2024–2026</title>
<style>
  :root{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --alert:#A8452F; --wknd:#C87B2E; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  @media (prefers-color-scheme:dark){:root{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --alert:#D4735A; --wknd:#E0A05A; --grid:#232B29; --shadow:none;
  }}
  :root[data-theme="dark"]{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --alert:#D4735A; --wknd:#E0A05A; --grid:#232B29; --shadow:none;
  }
  :root[data-theme="light"]{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --alert:#A8452F; --wknd:#C87B2E; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1320px;margin:0 auto;padding:44px 22px 90px;display:flex;flex-direction:column;gap:34px}
  header{display:flex;flex-direction:column;gap:9px;border-bottom:2px solid var(--ink);padding-bottom:18px}
  .eyebrow{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--wknd);font-weight:700}
  h1{margin:0;font-size:clamp(25px,4vw,37px);font-weight:800;letter-spacing:-.022em;line-height:1.18;text-wrap:balance}
  .sub{color:var(--muted);font-size:13.5px;max-width:74ch;margin:0}
  .sub a{color:var(--accent)}
  .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px 17px;
    display:flex;flex-direction:column;gap:4px;box-shadow:var(--shadow)}
  .tile .k{font-size:11px;letter-spacing:.09em;color:var(--muted);font-weight:700}
  .tile .v{font-size:25px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
  .tile .n{font-size:12px;color:var(--muted)}
  .tile.w .v{color:var(--wknd)}
  section{display:flex;flex-direction:column;gap:13px}
  h2{margin:0;font-size:16.5px;font-weight:700;letter-spacing:-.01em}
  h2 .hint{font-weight:400;color:var(--muted);font-size:13px;margin-left:8px}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:19px;box-shadow:var(--shadow)}

  .cmp{width:100%;border-collapse:collapse;font-size:13.5px}
  .cmp th,.cmp td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:right;
    font-variant-numeric:tabular-nums}
  .cmp th:first-child,.cmp td:first-child{text-align:left;font-weight:600}
  .cmp thead th{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700;
    border-bottom:2px solid var(--line)}
  .cmp tbody tr:last-child td{border-bottom:none}
  .cmp .k{color:var(--wknd);font-weight:700}
  .cmp .a{color:var(--muted)}

  .calc{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:16px;align-items:end}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld label{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700}
  .fld input{padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--paper);
    color:var(--ink);font:inherit;font-size:15px;font-variant-numeric:tabular-nums;text-align:right;width:100%}
  .fld .u{font-size:11px;color:var(--muted)}
  .out{border-left:3px solid var(--alert);padding-left:15px;display:flex;flex-direction:column;gap:2px}
  .out .big{font-size:27px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums;line-height:1.15}
  .out .cap{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700}
  .out .sm{font-size:12.5px;color:var(--muted)} .out .sm b{color:var(--alert);font-size:14px}
  .out.sim{border-left-color:var(--muted)}
  .out.sim.plus{border-left-color:var(--accent)} .out.sim.plus .big{color:var(--accent)}
  .out.sim.minus{border-left-color:var(--alert)} .out.sim.minus .big{color:var(--alert)}
  .outs{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:18px;
    margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
  .formula{font-size:12px;color:var(--muted);border-top:1px solid var(--line);margin-top:15px;padding-top:11px}

  .dist{display:flex;flex-direction:column;gap:7px}
  .drow{display:grid;grid-template-columns:88px 1fr 88px;align-items:center;gap:11px;font-size:13px}
  .drow .lb{color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
  .bar{height:19px;background:var(--grid);border-radius:3px;overflow:hidden}
  .bar i{display:block;height:100%;background:var(--muted);border-radius:3px}
  .drow.under .bar i{background:var(--alert)}
  .drow.under .lb{color:var(--alert);font-weight:700}
  .drow .ct{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}
  .thr{display:flex;align-items:center;gap:9px;margin:4px 0}
  .thr::before,.thr::after{content:"";flex:1;height:2px;background:var(--alert)}
  .thr span{font-size:11.5px;font-weight:700;color:var(--alert);white-space:nowrap;
    font-variant-numeric:tabular-nums}
  .lg{font-size:12.5px;color:var(--muted);margin-top:10px;border-top:1px solid var(--line);padding-top:10px}
  .lg b{color:var(--alert)}

  .ctl{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
  input[type=search]{flex:1 1 250px;min-width:190px;padding:9px 13px;border:1px solid var(--line);
    border-radius:8px;background:var(--card);color:var(--ink);font:inherit;font-size:14px}
  input:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  button.tog{padding:9px 13px;border:1px solid var(--line);border-radius:8px;background:var(--card);
    color:var(--muted);font:inherit;font-size:13px;font-weight:600;cursor:pointer}
  button.tog[aria-pressed="true"]{background:var(--wknd);border-color:var(--wknd);color:#fff}
  .count{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto}

  .tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);box-shadow:var(--shadow)}
  table.rk{border-collapse:collapse;width:100%;font-size:13px}
  .rk th,.rk td{padding:8px 11px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line);
    vertical-align:top}
  .rk thead th{position:sticky;top:0;background:var(--card);z-index:2;font-size:11px;letter-spacing:.05em;
    color:var(--muted);font-weight:700;cursor:pointer;user-select:none;border-bottom:2px solid var(--line)}
  .rk thead th:hover{color:var(--ink)} .rk thead th.on{color:var(--wknd)}
  .rk thead th.on::after{content:attr(data-a);margin-left:4px}
  .rk td.num,.rk th.num{text-align:right;font-variant-numeric:tabular-nums}
  .rk tbody tr:hover{background:color-mix(in srgb,var(--wknd) 8%,transparent)}
  .rk tbody tr:last-child td{border-bottom:none}
  .nm{font-weight:600;white-space:normal;min-width:180px;max-width:250px}
  .meta{color:var(--muted);font-size:11.5px}
  td.dstr{max-width:130px;white-space:normal;font-size:11.5px;color:var(--muted)}
  .cum{font-weight:700} .under{color:var(--alert)}
  .wc{color:var(--wknd);font-weight:700}
  .spark{display:block}
  tr.mark td{background:color-mix(in srgb,var(--alert) 10%,var(--card));border-top:2px solid var(--alert);
    border-bottom:2px solid var(--alert);font-weight:700;color:var(--alert);white-space:normal;font-size:13px}
  tr.mark span{display:block;font-weight:400;color:var(--muted);font-size:11.5px;margin-top:3px}
  footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:15px}
  footer code{background:var(--grid);padding:1px 5px;border-radius:4px;font-size:11.5px}
  @media (max-width:640px){.wrap{padding:26px 13px 60px}.drow{grid-template-columns:72px 1fr 62px}}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">KOBIS 통합전산망 기반 · 2024–2026</div>
    <h1>어린이 애니메이션 수입작 흥행 실적</h1>
    <p class="sub">2024년 1월 이후 개봉한 비직배 수입 어린이 애니메이션 __N__편.
      일본 애니(팬덤 극장판·대형 IP), 대형 배급사 경유 메이저 IP, 작가주의·성인 애니는 제외했습니다.
      같은 기준으로 정리한 <a href="arthouse.html">아트하우스 외화 실적</a>과 비교해 보실 수 있습니다.</p>
  </header>

  <div class="tiles">__TILES__</div>

  <section>
    <h2>주말에 몰린다는 통설<span class="hint">아트하우스와 나란히 놓고 본 결과</span></h2>
    <div class="panel">
      <table class="cmp">
        <thead><tr><th>지표</th><th>어린이 애니</th><th>아트하우스 외화</th><th>차이</th></tr></thead>
        <tbody>__CMP__</tbody>
      </table>
      <div class="formula">__CMPNOTE__</div>
    </div>
  </section>

  <section>
    <h2>얼마를 써야 본전인가<span class="hint">비용을 넣으면 그 돈조차 못 번 영화가 몇 편인지 나옵니다</span></h2>
    <div class="panel">
      <div class="calc">
        <div class="fld"><label for="pa">P&amp;A</label>
          <input id="pa" type="number" min="0" step="500" value="__PA__" inputmode="numeric">
          <span class="u">만원</span></div>
        <div class="fld"><label for="mg">수입 MG</label>
          <input id="mg" type="number" min="0" step="500" value="__MG__" inputmode="numeric">
          <span class="u">만원 · 0으로 두면 가장 보수적인 하한</span></div>
        <div class="fld"><label for="up">실정산 부금단가</label>
          <input id="up" type="number" min="1" step="100" value="__UNIT__" inputmode="numeric">
          <span class="u">원 / 관객 1명</span></div>
        <div class="fld"><label for="au">예상 관객수</label>
          <input id="au" type="number" min="0" step="1000" value="__AUD__" inputmode="numeric">
          <span class="u">명 · 이 성적일 때 손익</span></div>
      </div>
      <div class="outs">
        <div class="out">
          <span class="cap">이만큼은 들어야 본전</span>
          <span class="big" id="obep">–</span>
          <span class="sm" id="orate">–</span>
        </div>
        <div class="out sim" id="simbox">
          <span class="cap">그때 전체 손익</span>
          <span class="big" id="osim">–</span>
          <span class="sm" id="osimn">–</span>
        </div>
        <div class="out sim" id="relbox">
          <span class="cap">개봉 실익 · 개봉 안 하는 경우 대비</span>
          <span class="big" id="orel">–</span>
          <span class="sm" id="oreln">–</span>
        </div>
      </div>
      <div class="formula">
        수입가(MG)는 작품마다 천차만별이라 누가 남겼는지는 실제 계약을 봐야 압니다.
        하지만 P&amp;A는 극장 개봉을 하는 이상 최소한 들어가는 돈이 있습니다.
        그래서 이 페이지는 <b>영화를 공짜로 사왔다고 쳐도 그 P&amp;A조차 극장에서 못 번 영화</b>만 붉게 표시합니다.
        입력값은 이 브라우저에만 있고 저장되지 않습니다.        <br><br><b>개봉이 이득인지는 MG와 무관합니다.</b>
        개봉을 안 하면 손실은 수입 MG 그대로이고, 개봉하면 거기에 P&amp;A가 더해지고 부금이 들어옵니다.
        양쪽에서 MG가 상쇄되므로 <b>부금이 P&amp;A를 넘느냐</b>만 남습니다.
        그래서 개봉 분기점은 P&amp;A ÷ 부금단가이고, 수입가를 얼마에 샀든 이 선은 같습니다.
      </div>
    </div>
  </section>

  <section>
    <h2>관객수 구간별 분포<span class="hint">붉은 구간이 비용조차 못 번 영화들입니다</span></h2>
    <div class="panel">
      <div class="dist" id="dist"></div>
      <div class="lg" id="distlg"></div>
    </div>
  </section>

  <section>
    <h2>전체 랭킹<span class="hint">막대는 개봉일부터 14일간 일별 관객 · 주황이 금·토·일</span></h2>
    <div class="ctl">
      <input type="search" id="q" placeholder="영화명 · 국가 · 배급사 검색" aria-label="검색">
      <button class="tog" id="tbep" aria-pressed="false">못 번 영화만</button>
      <span class="count" id="ct"></span>
    </div>
    <div class="tw">
      <table class="rk">
        <thead><tr>
          <th class="num" data-k="rank">#</th>
          <th data-k="name">영화</th>
          <th data-k="open">개봉일</th>
          <th data-k="nat">국가</th>
          <th data-k="dist">배급사</th>
          <th class="num" data-k="scr">스크린</th>
          <th class="num" data-k="s0">개봉일<br>좌석수</th>
          <th class="num" data-k="rw">첫주말<br>판매율</th>
          <th class="num" data-k="wc">주말<br>집중도</th>
          <th data-k="rank">D+0 → D+14</th>
          <th class="num" data-k="fw">첫주<br>관객</th>
          <th class="num" data-k="cum">최종<br>누적</th>
          <th class="num" data-k="mult">배수</th>
        </tr></thead>
        <tbody id="tb"></tbody>
      </table>
    </div>
  </section>

  <footer>
    출처 영화진흥위원회 영화관입장권통합전산망(KOBIS) · 수집 __DATE__<br>
    주말 집중도는 첫 주말(개봉 후 처음 오는 금·토·일) 관객 ÷ 첫주(개봉일~D+6) 관객입니다.
    배수는 최종 누적 ÷ 첫주 관객으로, 값이 클수록 개봉 후 입소문으로 확산된 작품입니다.
    좌석판매율은 해당 구간 관객수 ÷ 좌석수로 직접 계산했습니다.
    최종 누적은 일별 관객 합산값이며, 수집 종료일까지 상영이 이어져 성적이 확정되지 않은 작품은 제외했습니다.
  </footer>
</div>

<script>
const D=__DATA__;
const tb=document.getElementById('tb'), q=document.getElementById('q'), ct=document.getElementById('ct'),
      tbep=document.getElementById('tbep'), mg=document.getElementById('mg'), pa=document.getElementById('pa'),
      up=document.getElementById('up'), obep=document.getElementById('obep'), orate=document.getElementById('orate'),
      au=document.getElementById('au'),
      osim=document.getElementById('osim'), osimn=document.getElementById('osimn'),
      simbox=document.getElementById('simbox'),
      orel=document.getElementById('orel'), oreln=document.getElementById('oreln'),
      relbox=document.getElementById('relbox'),
      dist=document.getElementById('dist'), distlg=document.getElementById('distlg');
let sortK='rank', sortA=true, onlyBep=false, BEP=0;
const fmt=n=>n?Math.round(n).toLocaleString('ko-KR'):'–';
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const BUCKETS=[[50000,1e9,'5만+'],[40000,50000,'4–5만'],[30000,40000,'3–4만'],[20000,30000,'2–3만'],
  [10000,20000,'1–2만'],[5000,10000,'5천–1만'],[0,5000,'5천 미만']];

function costPhrase(){
  const m=Number(mg.value)||0, p=Number(pa.value)||0;
  return m===0 ? `영화를 공짜로 사왔어도 P&A ${fmt(p)}만원`
               : `MG ${fmt(m)}만 + P&A ${fmt(p)}만 = ${fmt(m+p)}만원`;
}
function calcBep(){
  const tot=((Number(mg.value)||0)+(Number(pa.value)||0))*10000, u=Number(up.value)||0;
  BEP = u>0 ? tot/u : 0;
  const k=D.filter(d=>d.cum<BEP).length;
  obep.textContent = BEP>0 ? fmt(BEP)+'명' : '–';
  orate.innerHTML = BEP>0
    ? `${costPhrase()}은 못 벌었을 작품 <b>${k}편 / ${D.length}편 (${(100*k/D.length).toFixed(1)}%)</b>`
    : '부금단가를 입력하세요';
}
const compact=n=>n>=10000?String(+(n/10000).toFixed(1)).replace(/\\.0$/,'')+'만':fmt(n);


// 예상 관객수를 넣으면 그 지점의 손익을 계산한다.
//   부금 = 관객수 × 부금단가,  손익 = 부금 − (MG + P&A)
function simulate(base){
  const a=Number(au.value)||0, u=Number(up.value)||0;
  const tot=((Number(mg.value)||0)+(Number(pa.value)||0))*10000;
  const rev=a*u, pl=rev-tot;
  osim.textContent=(pl>=0?'+':'−')+fmt(Math.abs(pl)/10000)+'만원';
  simbox.classList.toggle('plus',pl>=0);
  simbox.classList.toggle('minus',pl<0);
  const better=base.filter(d=>d.cum>=a).length;
  const pct=base.length?100*better/base.length:0;
  osimn.innerHTML=`부금 ${fmt(rev/10000)}만원 · 이 성적을 넘긴 작품 `
    +`<b>${better}편 / ${base.length}편 (상위 ${pct.toFixed(0)}%)</b>`;

  // 개봉 여부 판단 — 개봉 안 하면 손실은 MG 그대로, 개봉하면 -MG-P&A+부금.
  // 양쪽에서 MG가 상쇄되므로 부금이 P&A 를 넘는지만 보면 된다(MG 무관).
  const paw=(Number(pa.value)||0)*10000;
  const relGain=rev-paw, relNeed=u>0?paw/u:0;
  orel.textContent=(relGain>=0?'+':'−')+fmt(Math.abs(relGain)/10000)+'만원';
  relbox.classList.toggle('plus',relGain>=0);
  relbox.classList.toggle('minus',relGain<0);
  oreln.innerHTML=`개봉 분기 <b>${fmt(relNeed)}명</b> · 이보다 적으면 `
    +`<b>개봉 안 하고 MG만 손실 보는 편이 이득</b>`;
}

function drawDist(){
  // 입력값이 구간 한가운데를 지나면 그 구간을 정확히 둘로 쪼갠다.
  // 그래야 기준선이 실제 위치에 그어지고, 아래쪽만 붉게 칠할 수 있다.
  let bs=BUCKETS.map(([lo,hi,lb])=>({lo,hi,lb}));
  if(BEP>0){
    const i=bs.findIndex(b=>b.lo<BEP&&BEP<b.hi);
    if(i>=0){
      const b=bs[i];
      bs.splice(i,1,
        {lo:BEP,hi:b.hi,lb:b.hi>=1e9?compact(BEP)+'+':compact(BEP)+'–'+compact(b.hi)},
        {lo:b.lo,hi:BEP,lb:compact(b.lo)+'–'+compact(BEP)});
    }
  }
  const cnt=bs.map(b=>D.filter(d=>d.cum>=b.lo&&d.cum<b.hi).length);
  const mx=Math.max(...cnt,1);
  dist.innerHTML=bs.map((b,i)=>{
    const line=(BEP>0&&i>0&&bs[i-1].lo>=BEP&&b.hi<=BEP)
      ? `<div class="thr"><span>${fmt(BEP)}명</span></div>` : '';
    return line+`<div class="drow ${BEP>0&&b.hi<=BEP?'under':''}"><span class="lb">${b.lb}</span>
     <span class="bar"><i style="width:${Math.max(2,Math.round(100*cnt[i]/mx))}%"></i></span>
     <span class="ct">${cnt[i]}편</span></div>`;
  }).join('');
  const m=[...D].sort((a,b)=>a.cum-b.cum)[Math.floor(D.length/2)];
  distlg.innerHTML=`중앙값 <b>${fmt(m.cum)}명</b> · 최고 ${fmt(D[0].cum)}명`
    +(BEP>0?` · <b>선 아래 = ${costPhrase()}도 극장에서 못 번 영화</b>`:'');
}
// 금·토·일 막대를 다른 색으로 칠해 주말 쏠림이 눈에 보이게 한다
function spark(c,wd){
  const w=104,h=26,mx=Math.max(...c,1),n=c.length,bw=w/n;
  let b='';
  for(let i=0;i<n;i++){
    const day=(wd+i)%7, wknd=day>=4;
    const bh=Math.max(1,Math.round(c[i]/mx*(h-3)));
    b+=`<rect x="${(i*bw).toFixed(1)}" y="${h-bh}" width="${(bw-1.1).toFixed(1)}" height="${bh}" rx="0.7"
        fill="${wknd?'var(--wknd)':'currentColor'}" opacity="${wknd?'.95':'.45'}"/>`;
  }
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">${b}</svg>`;
}
function view(){
  let r=D.slice();
  if(onlyBep&&BEP>0) r=r.filter(d=>d.cum<BEP);
  const s=q.value.trim().toLowerCase();
  if(s) r=r.filter(d=>(d.name+' '+d.nat+' '+d.dist+' '+d.dir).toLowerCase().includes(s));
  r.forEach((d,i)=>d.rank=i+1);
  const dir=sortA?1:-1;
  r.sort((a,b)=>{const x=a[sortK],y=b[sortK];
    return typeof x==='string'?x.localeCompare(y,'ko')*dir:(x-y)*dir;});
  return r;
}
function draw(){
  const r=view(); let html='', marked=false;
  const desc=(sortK==='cum'&&!sortA)||(sortK==='rank'&&sortA);
  for(const d of r){
    if(desc&&!marked&&BEP>0&&d.cum<BEP){
      html+=`<tr class="mark"><td colspan="13">여기 아래는 ${costPhrase()}조차 극장에서 못 번 영화들 — ${fmt(BEP)}명 미만
        <span>위쪽이라고 남는 장사였다는 뜻은 아닙니다. 실제 수입가를 알아야 알 수 있습니다.</span></td></tr>`;
      marked=true;
    }
    html+=`<tr>
      <td class="num meta">${d.rank}</td>
      <td class="nm">${esc(d.name)}<div class="meta">${esc(d.dir)||'&nbsp;'}</div></td>
      <td class="meta">${d.open}</td>
      <td class="meta">${esc(d.nat)||'–'}</td>
      <td class="dstr">${esc(d.dist)||'–'}</td>
      <td class="num">${fmt(d.scr)}</td>
      <td class="num">${fmt(d.s0)}</td>
      <td class="num meta">${d.rw?d.rw.toFixed(1)+'%':'–'}</td>
      <td class="num wc">${d.wc?d.wc.toFixed(0)+'%':'–'}</td>
      <td>${spark(d.c,d.wd)}</td>
      <td class="num">${fmt(d.fw)}</td>
      <td class="num cum ${BEP>0&&d.cum<BEP?'under':''}">${fmt(d.cum)}</td>
      <td class="num meta">${d.mult?d.mult.toFixed(2)+'×':'–'}</td>
    </tr>`;
  }
  tb.innerHTML=html;
  const nb=BEP>0?r.filter(d=>d.cum<BEP).length:0;
  ct.textContent=`${r.length}편 표시`+(BEP>0?` · 못 번 영화 ${nb}편 (${r.length?(100*nb/r.length).toFixed(1):0}%)`:'');
}
function refresh(){calcBep();simulate(D);drawDist();draw();}
document.querySelectorAll('.rk thead th').forEach(th=>{
  th.addEventListener('click',()=>{
    const k=th.dataset.k;
    if(sortK===k) sortA=!sortA; else{sortK=k; sortA=['rank','name','open','nat','dist'].includes(k);}
    document.querySelectorAll('.rk thead th').forEach(o=>{o.classList.remove('on');o.removeAttribute('data-a');});
    th.classList.add('on'); th.setAttribute('data-a',sortA?'↑':'↓');
    draw();
  });
});
[mg,pa,up,au].forEach(el=>el.addEventListener('input',refresh));
q.addEventListener('input',draw);
tbep.addEventListener('click',()=>{onlyBep=!onlyBep;tbep.setAttribute('aria-pressed',onlyBep);draw();});
refresh();
</script>
"""


def main():
    K = load()
    A = art_stats()
    n = len(K)
    kc = sorted(x["cum"] for x in K)
    ac = sorted(x["cum"] for x in A)
    UP = DEF_UNIT

    kwc = med([x["wc"] for x in K])
    k_r0, k_rw = med([x["r0"] for x in K]), med([x["rw"] for x in K])
    a_r0, a_rw = med([x["r0"] for x in A]), med([x["rw"] for x in A])
    k_m, a_m = med([x["mult"] for x in K]), med([x["mult"] for x in A])
    need = 3000 * 10000 / UP
    k_rec = 100 * sum(1 for v in kc if v >= need) / n
    a_rec = 100 * sum(1 for v in ac if v >= need) / len(ac)

    tiles = [
        ("분석 대상", f"{n}편", "성적 확정분"),
        ("중앙값", f"{kc[n//2]:,}", f"아트하우스 {ac[len(ac)//2]:,}명"),
        ("주말 집중도", f"{kwc:.0f}%", "첫주 관객 중 금·토·일", "w"),
        ("최고 기록", f"{kc[-1]:,}", K[0]["name"]),
        ("배수 중앙", f"{k_m:.2f}배", f"아트하우스 {a_m:.2f}배"),
        ("P&A 3천만 회수", f"{k_rec:.0f}%", f"아트하우스 {a_rec:.0f}%"),
    ]
    th = "".join(f'<div class="tile {t[3] if len(t)>3 else ""}"><span class="k">{t[0]}</span>'
                 f'<span class="v">{t[1]}</span><span class="n">{t[2]}</span></div>' for t in tiles)

    rows = [
        ("중앙 관객수", f"{kc[n//2]:,}명", f"{ac[len(ac)//2]:,}명", f"{kc[n//2]/ac[len(ac)//2]:.1f}배"),
        ("개봉일 좌석판매율", f"{k_r0:.1f}%", f"{a_r0:.1f}%", f"{k_r0-a_r0:+.1f}%p"),
        ("첫 주말 좌석판매율", f"{k_rw:.1f}%", f"{a_rw:.1f}%", f"{k_rw-a_rw:+.1f}%p"),
        ("개봉일 → 첫 주말 변화", f"{k_rw-k_r0:+.1f}%p", f"{a_rw-a_r0:+.1f}%p", "—"),
        ("배수 (최종÷첫주)", f"{k_m:.2f}배", f"{a_m:.2f}배", f"{k_m-a_m:+.2f}"),
        ("최고 기록", f"{kc[-1]:,}명", f"{ac[-1]:,}명", f"{ac[-1]/kc[-1]:.0f}배 차이"),
        ("P&A 3천만 회수율", f"{k_rec:.0f}%", f"{a_rec:.0f}%", f"{k_rec-a_rec:+.0f}%p"),
    ]
    cmp_html = "".join(
        f"<tr><td>{a}</td><td class='k'>{b}</td><td class='a'>{c}</td><td class='a'>{d}</td></tr>"
        for a, b, c, d in rows)

    note = (f"어린이 애니는 개봉일 판매율이 {k_r0:.1f}%로 아트하우스({a_r0:.1f}%)와 비슷하게 출발하지만, "
            f"첫 주말에 {k_rw:.1f}%까지 <b>오릅니다</b>. 아트하우스는 같은 구간에서 {a_rw:.1f}%로 <b>떨어집니다</b>. "
            f"주말에 채운다는 통설은 데이터로 확인됩니다. "
            f"다만 배수는 {k_m:.2f}배로 아트하우스({a_m:.2f}배)보다 낮고 최고 기록도 "
            f"{kc[-1]:,}명에 그칩니다. 첫 주말에 올 관객은 다 오지만 그 이상으로 번지지는 않는다는 뜻입니다. "
            f"바닥은 튼튼하고 천장은 낮은 구조입니다.")

    keys = ("name", "open", "wd", "nat", "dir", "dist", "scr", "s0", "r0",
            "sw", "rw", "wc", "fw", "cum", "mult", "c")
    data = [{k: r[k] for k in keys} for r in K]
    html = (HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
                .replace("__TILES__", th).replace("__CMP__", cmp_html).replace("__CMPNOTE__", note)
                .replace("__N__", str(n)).replace("__MG__", str(DEF_MG))
                .replace("__PA__", str(DEF_PA)).replace("__UNIT__", str(DEF_UNIT))
                .replace("__AUD__", str(kc[n//2]))
                .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d")))
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"완료: {OUT} ({n}편)")


if __name__ == "__main__":
    main()
