# -*- coding: utf-8 -*-
"""
arthouse_final.csv → arthouse_report.html

대외 공유용 산업 현황 페이지. 특정 작품 검토 내용은 담지 않는다.
손익분기는 고정 상수 대신 열람자가 MG·P&A·정산단가를 입력해 실시간 계산한다.
  BEP 관객 = (수입 MG + P&A) ÷ 실정산 부금단가
입력값은 브라우저 안에서만 쓰이고 페이지에 저장되지 않는다.
"""
import os
import csv
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "arthouse_final.csv")
OUT = os.path.join(BASE, "arthouse_report.html")

RERELEASE_GAP = 6
NDAY = 15

# 세그먼트에서 통째로 빼는 대상 (필터가 아니라 제외)
#  · 직배  : 글로벌 스튜디오 한국지사 배급작. 비직배 수입 시장을 보려는 목적이므로 제외.
#  · 청불 소규모: 청소년관람불가 + 개봉스크린 20개 미만.
#    성인물을 정확히 집어내는 규칙이 아니라 근사치다. 크로넨버그 '미래의 범죄들'(칸 경쟁,
#    16개관)처럼 성격이 다른 작품도 함께 빠진다. 되살릴 작품은 KEEP 에 제목을 넣는다.
ERO_SCREEN_MAX = 20
KEEP = set()

# 계산기 초기값 (열람자가 화면에서 바꿀 수 있다)
DEF_MG, DEF_PA, DEF_UNIT = 7500, 7000, 4200   # 만원, 만원, 원


def load():
    rows, n_major, n_ero = [], 0, 0
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        oy = int(r["개봉일"][:4])
        py = int(r["제작연도"]) if r["제작연도"].isdigit() else oy
        iv = lambda k: int(r[k]) if r.get(k) and r[k].strip() else 0
        fv = lambda k: float(r[k]) if r.get(k) and r[k].strip() else 0
        if r["영화명"] not in KEEP:
            if r["직배여부"] == "직배":
                n_major += 1
                continue
            if "청소년관람불가" in r["등급"] and iv("개봉스크린수") < ERO_SCREEN_MAX:
                n_ero += 1
                continue
        rows.append({
            "name": r["영화명"], "open": r["개봉일"],
            "nat": r["대표국적"], "gen": r["장르"], "dir": r["감독"], "dist": r["배급사"],
            "scr": iv("개봉스크린수"),
            "s0": iv("개봉일좌석수"), "r0": fv("개봉일좌석판매율"),
            "sw": iv("첫주말좌석수"), "rw": fv("첫주말좌석판매율"),
            "fw": iv("첫주관객"), "cum": iv("최종누적관객"),
            "mult": fv("배수"),
            "c": [iv(f"D{i}") for i in range(NDAY)],
            "re": (oy - py) >= RERELEASE_GAP,
        })
    rows.sort(key=lambda r: -r["cum"])
    print(f"  제외: 직배 {n_major}편, 청불·소규모 {n_ero}편")
    return rows


HTML = """<title>한국 아트하우스 외화 흥행 실적 · 2024–2026</title>
<style>
  :root{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --alert:#A8452F; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  @media (prefers-color-scheme:dark){:root{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --alert:#D4735A; --grid:#232B29; --shadow:none;
  }}
  :root[data-theme="dark"]{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --alert:#D4735A; --grid:#232B29; --shadow:none;
  }
  :root[data-theme="light"]{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --alert:#A8452F; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1400px;margin:0 auto;padding:44px 22px 90px;display:flex;flex-direction:column;gap:34px}
  header{display:flex;flex-direction:column;gap:9px;border-bottom:2px solid var(--ink);padding-bottom:18px}
  .eyebrow{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:700}
  h1{margin:0;font-size:clamp(25px,4vw,37px);font-weight:800;letter-spacing:-.022em;line-height:1.18;text-wrap:balance}
  .sub{color:var(--muted);font-size:13.5px;max-width:74ch;margin:0}
  .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px 17px;
    display:flex;flex-direction:column;gap:4px;box-shadow:var(--shadow)}
  .tile .k{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700}
  .tile .v{font-size:25px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
  .tile .n{font-size:12px;color:var(--muted)}
  section{display:flex;flex-direction:column;gap:13px}
  h2{margin:0;font-size:16.5px;font-weight:700;letter-spacing:-.01em}
  h2 .hint{font-weight:400;color:var(--muted);font-size:13px;margin-left:8px;letter-spacing:0}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:19px;box-shadow:var(--shadow)}

  /* 손익분기 계산기 */
  .calc{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:16px;align-items:end}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld label{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700}
  .fld input{padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--paper);
    color:var(--ink);font:inherit;font-size:15px;font-variant-numeric:tabular-nums;text-align:right;width:100%}
  .fld .u{font-size:11px;color:var(--muted)}
  .out{border-left:3px solid var(--accent);padding-left:15px;display:flex;flex-direction:column;gap:2px}
  .out .big{font-size:27px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums;line-height:1.15}
  .out .cap{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700}
  .out .sm{font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums}
  .out .sm b{color:var(--accent);font-size:14px}
  .formula{font-size:12px;color:var(--muted);border-top:1px solid var(--line);margin-top:15px;padding-top:11px}

  .dist{display:flex;flex-direction:column;gap:7px}
  .drow{display:grid;grid-template-columns:92px 1fr 96px;align-items:center;gap:11px;font-size:13px}
  .drow .lb{color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
  .bar{height:19px;background:var(--grid);border-radius:3px;overflow:hidden}
  .bar i{display:block;height:100%;background:var(--muted);border-radius:3px;transition:background .15s}
  .drow.ok .bar i{background:var(--accent)}
  .drow.ok .lb{color:var(--accent);font-weight:700}
  .drow .ct{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}
  .lg{font-size:12.5px;color:var(--muted);margin-top:10px;border-top:1px solid var(--line);padding-top:10px}
  .lg b{color:var(--accent)}

  .ctl{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
  input[type=search]{flex:1 1 250px;min-width:190px;padding:9px 13px;border:1px solid var(--line);
    border-radius:8px;background:var(--card);color:var(--ink);font:inherit;font-size:14px}
  input:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  button.tog{padding:9px 13px;border:1px solid var(--line);border-radius:8px;background:var(--card);
    color:var(--muted);font:inherit;font-size:13px;font-weight:600;cursor:pointer}
  button.tog[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--card)}
  .count{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto}

  .tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);box-shadow:var(--shadow)}
  table{border-collapse:collapse;width:100%;font-size:13px}
  th,td{padding:8px 11px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line);vertical-align:top}
  thead th{position:sticky;top:0;background:var(--card);z-index:2;font-size:11px;letter-spacing:.05em;
    color:var(--muted);font-weight:700;cursor:pointer;user-select:none;border-bottom:2px solid var(--line);
    white-space:nowrap}
  thead th:hover{color:var(--ink)} thead th.on{color:var(--accent)}
  thead th.on::after{content:attr(data-a);margin-left:4px}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tbody tr:hover{background:color-mix(in srgb,var(--accent) 7%,transparent)}
  tbody tr:last-child td{border-bottom:none}
  .nm{font-weight:600;white-space:normal;min-width:170px;max-width:230px}
  .meta{color:var(--muted);font-size:11.5px}
  td.dist{max-width:140px;white-space:normal;font-size:11.5px;color:var(--muted)}
  .cum{font-weight:700} .ok{color:var(--accent)} .no{color:var(--muted)}
  .pill{display:inline-block;padding:0 6px;border-radius:99px;font-size:10.5px;font-weight:700;
    border:1px solid currentColor;margin-left:5px;color:var(--muted)}
  .spark{display:block}
  tr.mark td{background:color-mix(in srgb,var(--accent) 11%,var(--card));border-top:2px solid var(--accent);
    border-bottom:2px solid var(--accent);font-weight:700;color:var(--accent);white-space:normal;font-size:12.5px}
  footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:15px}
  footer code{background:var(--grid);padding:1px 5px;border-radius:4px;font-size:11.5px}
  @media (max-width:640px){.wrap{padding:26px 13px 60px}.drow{grid-template-columns:74px 1fr 68px}}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">KOBIS 통합전산망 기반 · 2024–2026</div>
    <h1>한국 아트하우스 외화 흥행 실적</h1>
    <p class="sub">2024년 1월 ~ 2026년 4월 개봉, KOBIS에서 다양성영화 × 외국영화로 분류된 __N__편.
      직배(글로벌 스튜디오 한국지사 배급)와 청소년관람불가 중 개봉 20개관 미만은 제외해
      비직배 수입 시장만 남겼습니다. 재개봉·구작(개봉연도 − 제작연도 ≥ 6년)은 기본 숨김입니다.</p>
  </header>

  <div class="tiles">__TILES__</div>

  <section>
    <h2>손익분기 계산기<span class="hint">수입가와 마케팅비를 넣으면 필요 관객과 달성 확률이 나옵니다</span></h2>
    <div class="panel">
      <div class="calc">
        <div class="fld"><label for="mg">수입 MG</label>
          <input id="mg" type="number" min="0" step="100" value="__MG__" inputmode="numeric"><span class="u">만원</span></div>
        <div class="fld"><label for="pa">P&amp;A</label>
          <input id="pa" type="number" min="0" step="100" value="__PA__" inputmode="numeric"><span class="u">만원</span></div>
        <div class="fld"><label for="up">실정산 부금단가</label>
          <input id="up" type="number" min="1" step="100" value="__UNIT__" inputmode="numeric"><span class="u">원 / 관객 1명</span></div>
        <div class="out">
          <span class="cap">손익분기 관객</span>
          <span class="big" id="obep">–</span>
          <span class="sm" id="orate">–</span>
        </div>
      </div>
      <div class="formula">
        관객수 × 부금단가 − (수입 MG + P&amp;A) ≥ 0 &nbsp;→&nbsp; 손익분기 관객 = 총제작비 ÷ 부금단가.
        입력값은 이 브라우저에서만 계산에 쓰이며 페이지에 저장되지 않습니다.
      </div>
    </div>
  </section>

  <section>
    <h2>관객수 구간별 분포<span class="hint">손익분기를 넘는 구간이 초록으로 표시됩니다</span></h2>
    <div class="panel">
      <div class="dist" id="dist"></div>
      <div class="lg" id="distlg"></div>
    </div>
  </section>

  <section>
    <h2>전체 랭킹<span class="hint">열 제목을 눌러 정렬 · 막대는 개봉일부터 14일간 일별 관객</span></h2>
    <div class="ctl">
      <input type="search" id="q" placeholder="영화명 · 감독 · 국가 · 장르 · 배급사 검색" aria-label="검색">
      <button class="tog" id="tre" aria-pressed="false">재개봉 포함</button>
      <button class="tog" id="tbep" aria-pressed="false">손익분기 돌파만</button>
      <span class="count" id="ct"></span>
    </div>
    <div class="tw">
      <table>
        <thead><tr>
          <th class="num" data-k="rank">#</th>
          <th data-k="name">영화</th>
          <th data-k="open">개봉일</th>
          <th data-k="nat">국가</th>
          <th data-k="dist">배급사</th>
          <th class="num" data-k="scr">개봉<br>스크린</th>
          <th class="num" data-k="s0">개봉일<br>좌석수</th>
          <th class="num" data-k="r0">개봉일<br>판매율</th>
          <th class="num" data-k="sw">첫주말<br>좌석수</th>
          <th class="num" data-k="rw">첫주말<br>판매율</th>
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
    첫주 관객은 개봉일~D+6, 첫 주말은 개봉 후 처음 오는 금·토·일 구간입니다.
    좌석판매율은 해당 구간 관객수 ÷ 좌석수로 직접 계산했습니다.
    배수는 최종 누적 ÷ 첫주 관객으로, 값이 클수록 개봉 후 입소문으로 확산된 작품입니다.
    좌석 데이터가 제공되지 않는 일부 소규모 상영은 <code>–</code>로 표시했습니다.
  </footer>
</div>

<script>
const D=__DATA__;
const tb=document.getElementById('tb'), q=document.getElementById('q'), ct=document.getElementById('ct'),
      tre=document.getElementById('tre'), tbep=document.getElementById('tbep'),
      mg=document.getElementById('mg'), pa=document.getElementById('pa'), up=document.getElementById('up'),
      obep=document.getElementById('obep'), orate=document.getElementById('orate'),
      dist=document.getElementById('dist'), distlg=document.getElementById('distlg');
let sortK='rank', sortA=true, showRe=false, onlyBep=false, BEP=0;
const fmt=n=>n?Math.round(n).toLocaleString('ko-KR'):'–';
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const BUCKETS=[[200000,1e9,'20만+'],[100000,200000,'10만–20만'],[50000,100000,'5만–10만'],
  [30000,50000,'3만–5만'],[20000,30000,'2만–3만'],[10000,20000,'1만–2만'],
  [5000,10000,'5천–1만'],[1000,5000,'1천–5천'],[0,1000,'1천 미만']];

function calcBep(){
  const tot=(Number(mg.value)||0)*10000+(Number(pa.value)||0)*10000;
  const u=Number(up.value)||0;
  BEP = u>0 ? tot/u : 0;
  const base=D.filter(d=>!d.re);
  const k=base.filter(d=>d.cum>=BEP).length;
  obep.textContent = BEP>0 ? fmt(BEP)+'명' : '–';
  orate.innerHTML = BEP>0
    ? `총제작비 ${fmt(tot/10000)}만원 · 달성 <b>${k}편 / ${base.length}편 (${(100*k/base.length).toFixed(1)}%)</b>`
    : '부금단가를 입력하세요';
}

function drawDist(){
  const base=D.filter(d=>!d.re);
  const cnt=BUCKETS.map(([lo,hi,lb])=>[lb,base.filter(d=>d.cum>=lo&&d.cum<hi).length,lo]);
  const mx=Math.max(...cnt.map(x=>x[1]),1);
  dist.innerHTML=cnt.map(([lb,v,lo])=>
    `<div class="drow ${BEP>0&&lo>=BEP?'ok':''}"><span class="lb">${lb}</span>
     <span class="bar"><i style="width:${Math.max(2,Math.round(100*v/mx))}%"></i></span>
     <span class="ct">${v}편</span></div>`).join('');
  const med=[...base].sort((a,b)=>a.cum-b.cum)[Math.floor(base.length/2)];
  distlg.innerHTML=`중앙값 <b>${fmt(med.cum)}명</b> · 5천 명 미만 ${base.filter(d=>d.cum<5000).length}편`
    + (BEP>0?` · 손익분기 <b>${fmt(BEP)}명</b> 이상 구간이 초록입니다`:'');
}

function spark(c){
  const w=104,h=26,mx=Math.max(...c,1),n=c.length,bw=w/n;
  let b='';
  for(let i=0;i<n;i++){
    const bh=Math.max(1,Math.round(c[i]/mx*(h-3)));
    b+=`<rect x="${(i*bw).toFixed(1)}" y="${h-bh}" width="${(bw-1.1).toFixed(1)}" height="${bh}" rx="0.7"/>`;
  }
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"
    fill="currentColor" opacity=".72">${b}</svg>`;
}

function view(){
  let r=D.filter(d=>showRe||!d.re);
  if(onlyBep&&BEP>0) r=r.filter(d=>d.cum>=BEP);
  const s=q.value.trim().toLowerCase();
  if(s) r=r.filter(d=>(d.name+' '+d.dir+' '+d.nat+' '+d.gen+' '+d.dist).toLowerCase().includes(s));
  r.forEach((d,i)=>d.rank=i+1);
  const dir=sortA?1:-1;
  r.sort((a,b)=>{const x=a[sortK],y=b[sortK];
    return typeof x==='string'?x.localeCompare(y,'ko')*dir:(x-y)*dir;});
  return r;
}

function draw(){
  const r=view(); let html='', marked=false;
  const banded=(sortK==='cum'||sortK==='rank');
  const desc=(sortK==='cum'&&!sortA)||(sortK==='rank'&&sortA);
  for(const d of r){
    if(banded&&desc&&!marked&&BEP>0&&d.cum<BEP){
      html+=`<tr class="mark"><td colspan="14">손익분기 ${fmt(BEP)}명 — 아래로는 회수 미달</td></tr>`;
      marked=true;
    }
    const ok=BEP>0&&d.cum>=BEP;
    html+=`<tr>
      <td class="num meta">${d.rank}</td>
      <td class="nm">${esc(d.name)}${d.re?'<span class="pill">재개봉</span>':''}
        <div class="meta">${esc([d.dir,d.gen].filter(Boolean).join(' · '))||'&nbsp;'}</div></td>
      <td class="meta">${d.open}</td>
      <td class="meta">${esc(d.nat)||'–'}</td>
      <td class="dist">${esc(d.dist)||'–'}</td>
      <td class="num">${fmt(d.scr)}</td>
      <td class="num">${fmt(d.s0)}</td>
      <td class="num meta">${d.r0?d.r0.toFixed(1)+'%':'–'}</td>
      <td class="num">${fmt(d.sw)}</td>
      <td class="num meta">${d.rw?d.rw.toFixed(1)+'%':'–'}</td>
      <td>${spark(d.c)}</td>
      <td class="num">${fmt(d.fw)}</td>
      <td class="num cum ${ok?'ok':'no'}">${fmt(d.cum)}</td>
      <td class="num meta">${d.mult?d.mult.toFixed(1)+'×':'–'}</td>
    </tr>`;
  }
  tb.innerHTML=html;
  const nb=BEP>0?r.filter(d=>d.cum>=BEP).length:0;
  ct.textContent=`${r.length}편 표시`+(BEP>0?` · 손익분기 돌파 ${nb}편 (${r.length?(100*nb/r.length).toFixed(1):0}%)`:'');
}

function refresh(){ calcBep(); drawDist(); draw(); }

document.querySelectorAll('thead th').forEach(th=>{
  th.addEventListener('click',()=>{
    const k=th.dataset.k;
    if(sortK===k) sortA=!sortA;
    else{sortK=k; sortA=['rank','name','open','nat','dist'].includes(k);}
    document.querySelectorAll('thead th').forEach(o=>{o.classList.remove('on');o.removeAttribute('data-a');});
    th.classList.add('on'); th.setAttribute('data-a',sortA?'↑':'↓');
    draw();
  });
});
[mg,pa,up].forEach(el=>el.addEventListener('input',refresh));
q.addEventListener('input',draw);
tre.addEventListener('click',()=>{showRe=!showRe;tre.setAttribute('aria-pressed',showRe);
  tre.textContent=showRe?'재개봉 포함됨':'재개봉 포함';refresh();});
tbep.addEventListener('click',()=>{onlyBep=!onlyBep;tbep.setAttribute('aria-pressed',onlyBep);draw();});
refresh();
</script>
"""


def main():
    rows = load()
    live = [r for r in rows if not r["re"]]
    c = sorted(r["cum"] for r in live)
    n = len(c)
    ns = sum(1 for r in live if r["sw"])

    tiles = [
        ("분석 대상", f"{n}편", "비직배 신작 외화"),
        ("중앙값", f"{c[n//2]:,}", "절반이 이 아래"),
        ("상위 10%", f"{c[int(n*0.90)]:,}", "상위 25%는 " + f"{c[int(n*0.75)]:,}명"),
        ("5천 명 미만", f"{sum(1 for x in c if x < 5000)}편",
         f"전체의 {round(100*sum(1 for x in c if x<5000)/n)}%"),
        ("최고 기록", f"{c[-1]:,}", live[0]["name"]),
        ("좌석 데이터", f"{ns}편", f"{round(100*ns/n)}% 확보"),
    ]
    th = "".join(f'<div class="tile"><span class="k">{t[0]}</span>'
                 f'<span class="v">{t[1]}</span><span class="n">{t[2]}</span></div>' for t in tiles)

    keys = ("name", "open", "nat", "gen", "dir", "dist", "scr", "s0", "r0",
            "sw", "rw", "fw", "cum", "mult", "c", "re")
    data = [{k: r[k] for k in keys} for r in rows]
    html = (HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
                .replace("__TILES__", th).replace("__N__", str(n))
                .replace("__MG__", str(DEF_MG)).replace("__PA__", str(DEF_PA))
                .replace("__UNIT__", str(DEF_UNIT))
                .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d")))
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"완료: {OUT} (표시 {len(rows)}편 / 신작 {n}편 / 좌석 {ns}편)")


if __name__ == "__main__":
    main()
