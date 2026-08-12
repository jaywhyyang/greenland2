# -*- coding: utf-8 -*-
"""forecast.json → vkobis_forecast.html (자립형 대시보드).
히어로(조건부 중앙+확률) · 배우 VOD프리미엄 랭킹 · 예측분포 · 시장하락 · 전환율 산점도 · 버틀러/근접 comp · 양극화.
인라인 SVG + 바닐라 JS(hover). 외부 의존성 없음(GitHub Pages 호환)."""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(BASE, "forecast.json"), encoding="utf-8"))


def money(n):
    return f"{int(round(n)):,}"


HTML = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>그린랜드2 온라인(TVOD) 이용건수 예측</title>
<style>
:root{--bg:#f7f8fa;--surface:#fff;--ink:#1a1d24;--muted:#5b6470;--faint:#8b95a3;
--line:#e3e7ec;--grid:#eef1f4;--g2:#2563eb;--g1:#f59e0b;--comp:#94a3b8;--market:#0d9488;--warn:#dc2626;}
@media(prefers-color-scheme:dark){:root{--bg:#0f1319;--surface:#171c24;--ink:#e8ecf1;--muted:#9aa4b2;--faint:#6b7482;
--line:#262d38;--grid:#1e242e;--g2:#60a5fa;--g1:#fbbf24;--comp:#64748b;--market:#2dd4bf;--warn:#f87171;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,'Noto Sans KR',sans-serif;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:23px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:14px;margin-bottom:22px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:22px;margin-bottom:18px}
.card h2{font-size:15px;margin:0 0 3px;letter-spacing:-.01em}
.card .desc{color:var(--muted);font-size:13px;margin:0 0 16px}
.hero{display:flex;flex-wrap:wrap;gap:26px;align-items:flex-end}
.bignum{font-size:46px;font-weight:750;letter-spacing:-.02em;line-height:1;color:var(--g2)}
.bignum small{font-size:15px;font-weight:600;color:var(--muted);margin-left:6px}
.rng{color:var(--muted);font-size:13px;margin-top:8px}
.scen{display:flex;flex:1;min-width:260px}
.scen div{flex:1;text-align:center;padding:9px 4px;border-radius:9px;margin:0 3px}
.scen .lbl{font-size:11px;color:var(--muted)} .scen .v{font-size:17px;font-weight:700;margin-top:2px}
.sc-lo{background:color-mix(in srgb,var(--comp) 16%,transparent)}
.sc-mid{background:color-mix(in srgb,var(--g2) 16%,transparent)}
.sc-hi{background:color-mix(in srgb,var(--g1) 16%,transparent)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:720px){.grid2{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:right;padding:7px 8px;border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left}
th{color:var(--faint);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
.tag{display:inline-block;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:600}
svg{display:block;width:100%;height:auto;overflow:visible}
.axl{fill:var(--faint);font-size:10px} .gl{stroke:var(--grid)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:12px;box-shadow:0 6px 20px rgba(0,0,0,.14);opacity:0;transition:opacity .1s;z-index:9;max-width:230px}
.tt b{color:var(--ink)} .tt span{color:var(--muted)}
.lgd{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:10px}
.lgd i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.note{font-size:12.5px;color:var(--muted);margin:6px 0}
.foot{color:var(--faint);font-size:11.5px;margin-top:20px;text-align:center}
b.mono{font-variant-numeric:tabular-nums}
.pill{display:inline-block;background:color-mix(in srgb,var(--g2) 15%,transparent);color:var(--g2);font-weight:700;padding:2px 9px;border-radius:20px;font-size:12px}
</style></head><body><div class="wrap">
<h1>그린랜드2 · 온라인(TVOD) 1년누적 이용건수 예측</h1>
<div class="sub">영진위 온라인상영관 통합전산망(vkobis) 전량(2012~26, 74,999행) · 지표=PPV(TVOD)·정액제 제외 · 회귀+배우프리미엄 조건부분포 · __GEN__</div>

<div class="card"><div class="hero">
  <div><div class="bignum">~__POINT__<small>건 (중앙값)</small></div>
    <div class="rng">80% 구간 __P10__ ~ __P90__ · 목표=온라인 개봉 후 1년 · 주연 <b>제라드 버틀러</b>(VOD 프리미엄 __RANK__위/__TOTAL__)</div></div>
  <div class="scen">
    <div class="sc-lo"><div class="lbl">보수 (25%)</div><div class="v">__SC_LO__</div></div>
    <div class="sc-mid"><div class="lbl">중앙 (50%)</div><div class="v">__SC_MID__</div></div>
    <div class="sc-hi"><div class="lbl">낙관 (90%)</div><div class="v">__SC_HI__</div></div>
  </div></div>
  <div class="note" style="margin-top:16px">장르만 보면 중앙 <b>__GENRE_ONLY__</b>이지만, 주연 <b>제라드 버틀러</b>는 외화 주연 __TOTAL__명 중 <b>VOD 프리미엄 1위(×__BMULT__)</b> — 그의 필모 전편이 시장·규모 모델을 초과. 이를 반영한 조건부 중앙이 <b style="color:var(--g2)">__POINT__</b>. 발레리나급(90k) 도달 확률 <b>__P90K__%</b>.</div>
</div>

<div class="grid2">
  <div class="card" style="margin-bottom:0">
    <h2>예측 분포 <span style="color:var(--faint);font-weight:400">(도달 확률)</span></h2>
    <div class="desc">조건부 로그정규 · 임계값 이상 나올 확률</div>
    <div id="dist"></div>
  </div>
  <div class="card" style="margin-bottom:0">
    <h2>앵커 · 시장 타이밍</h2>
    <table>
      <tr><th>구분</th><th>극장</th><th>온라인1년</th><th>R</th></tr>
      <tr><td><b style="color:var(--g1)">그린랜드1</b> <span class="axl">2020</span></td><td class="mono">326,130</td><td class="mono">266,688</td><td class="mono">0.82</td></tr>
      <tr><td><b style="color:var(--g2)">그린랜드2</b> <span class="axl">예측</span></td><td class="mono">55,446</td><td class="mono">~__POINT__</td><td class="mono">~__G2R__</td></tr>
    </table>
    <div class="note" style="margin-top:12px">개봉 시장에 민감: 늦어질수록 하방<br>
      <span id="timing"></span></div>
  </div>
</div>

<div class="card">
  <h2>배우별 VOD 프리미엄 <span style="color:var(--faint);font-weight:400">(장르로 못 잡는 스타 요인)</span></h2>
  <div class="desc">극장·시장 회귀 대비 초과배수(주연 3편+, shrinkage) · <b>VOD형 액션스타가 최상위, 극장형(크루즈·존슨)은 프리미엄 없음</b></div>
  <div id="stars"></div>
</div>

<div class="card">
  <h2>제라드 버틀러 필모 <span style="color:var(--faint);font-weight:400">(극장 무관 VOD 20만+ 바닥)</span></h2>
  <div class="desc">오른쪽 <b>×배수</b> = 극장·시장 모델 대비 실제 초과 · 헌터킬러(극장 57,032 ≈ 그린랜드2)가 VOD 213,845</div>
  <div style="overflow-x:auto"><table id="butler"><tr><th>작품</th><th>극장</th><th>온라인1년</th><th>R</th><th>개봉</th><th>모델대비</th></tr></table></div>
</div>

<div class="card">
  <h2>TVOD 시장 하락 지수 <span style="color:var(--faint);font-weight:400">(2020=100)</span></h2>
  <div class="desc">전체 온라인 이용건수 · 그린랜드1(2020)은 시장 높던 시기, 그린랜드2(예측)는 붕괴 후(~20)</div>
  <div id="mkt"></div>
  <div class="lgd"><span><i style="background:var(--market)"></i>연간 총 이용건수 지수</span><span><i style="background:var(--g1)"></i>1편</span><span><i style="background:var(--g2)"></i>2편(예측장)</span></div>
</div>

<div class="card">
  <h2>양극화 <span style="color:var(--faint);font-weight:400">(온라인 개봉연도별 분포)</span></h2>
  <div class="desc">중간대(2~10만) 편수 붕괴 + 집중도↑ · 단 극장과 달리 50만+ 대박도 소멸(SVOD 이탈)</div>
  <div id="polar"></div>
  <div class="lgd"><span><i style="background:var(--comp)"></i>중간대(2~10만)</span><span><i style="background:var(--g2)"></i>10만+</span><span><i style="background:var(--g1)"></i>50만+</span><span style="color:var(--faint)">— Top10% 집중도</span></span></div>
</div>

<div class="card">
  <h2>전환율 산점도 <span style="color:var(--faint);font-weight:400">(극장→온라인1년, 로그-로그)</span></h2>
  <div class="desc">외화 실사 액션 · 버틀러작(강조)이 곡선 위쪽에 몰림 · 그린랜드2 예측 위치 표시</div>
  <div id="scat"></div>
  <div class="lgd"><span><i style="background:var(--comp)"></i>comp</span><span><i style="background:var(--warn)"></i>버틀러작</span><span><i style="background:var(--g2)"></i>그린랜드2</span><span><i style="background:var(--g1)"></i>그린랜드1</span><span style="color:var(--faint)">— 멱법칙</span></span></div>
</div>

<div class="card"><h2>방법론 노트</h2>__NOTES__</div>
<div class="foot">데이터: vkobis 연간 전량 + 영화상세·인물 조인 · 자산: vkobis_scrape/analyze/enrich/people/forecast.py + build_vkobis_dashboard.py</div>
</div><div class="tt" id="tt"></div>
<script>
const D=__DATA__;const $=s=>document.querySelector(s);const tt=$('#tt');
const fmt=n=>Math.round(n).toLocaleString('ko-KR');
function showTT(h,e){tt.innerHTML=h;tt.style.opacity=1;let x=e.clientX+14,y=e.clientY+14;if(x+240>innerWidth)x=e.clientX-240;tt.style.left=x+'px';tt.style.top=y+'px';}
function hideTT(){tt.style.opacity=0;}

// 타이밍
$('#timing').innerHTML=Object.entries(D.timing).map(([k,v])=>`시장 idx ${k} → <b class="mono">${fmt(v)}</b>`).join(' &nbsp;·&nbsp; ');

// 예측 분포(P≥X 수평바)
(function(){
  const P=D.probs, keys=Object.keys(P).map(Number).sort((a,b)=>a-b);
  const W=440,rh=30,pad=8,lw=96,H=keys.length*rh+pad*2;
  let s=`<svg viewBox="0 0 ${W} ${H}">`;
  keys.forEach((k,i)=>{const y=pad+i*rh, pct=P[k], bw=(W-lw-70)*pct/100;
    const hl=(k==90000);
    s+=`<text class="axl" x="${lw-8}" y="${y+rh/2+4}" text-anchor="end" style="font-size:12px;fill:var(--ink)">≥ ${k>=1000?k/1000+'k':k}</text>`;
    s+=`<rect x="${lw}" y="${y+5}" width="${Math.max(2,bw)}" height="${rh-12}" rx="3" fill="${hl?'var(--g1)':'var(--g2)'}" opacity="${hl?1:.8}"/>`;
    s+=`<text x="${lw+bw+7}" y="${y+rh/2+4}" style="font-size:12px;font-weight:700;fill:var(--ink)">${pct}%${hl?' ← 발레리나급':''}</text>`;});
  $('#dist').innerHTML=s+'</svg>';
})();

// 배우 프리미엄 랭킹
(function(){
  const R=D.star.ranking.slice(0,14);const star=D.star.name;
  const W=920,rh=26,pad=10,lw=110,H=R.length*rh+pad*2+16;
  const mx=Math.max(...R.map(r=>r.mult));
  const X=v=>lw+(v/(mx*1.05))*(W-lw-70);
  let s=`<svg viewBox="0 0 ${W} ${H}">`;
  s+=`<line x1="${X(1)}" y1="${pad}" x2="${X(1)}" y2="${H-pad-16}" stroke="var(--faint)" stroke-dasharray="3 3"/><text class="axl" x="${X(1)}" y="${H-pad}" text-anchor="middle">×1 (프리미엄 없음)</text>`;
  R.forEach((r,i)=>{const y=pad+i*rh, isB=r.name===star, bw=X(r.mult)-lw;
    s+=`<text x="${lw-8}" y="${y+rh/2+4}" text-anchor="end" style="font-size:12px;fill:${isB?'var(--g2)':'var(--ink)'};font-weight:${isB?700:400}">${r.name}</text>`;
    s+=`<rect x="${lw}" y="${y+4}" width="${Math.max(2,bw)}" height="${rh-9}" rx="3" fill="${isB?'var(--g2)':'var(--comp)'}" data-n="${r.name}" data-m="${r.mult}" data-c="${r.n}"/>`;
    s+=`<text x="${lw+bw+6}" y="${y+rh/2+4}" style="font-size:11.5px;font-weight:${isB?700:600};fill:${isB?'var(--g2)':'var(--muted)'}">×${r.mult.toFixed(2)}${isB?' · 1위/'+D.star.total:''}</text>`;});
  $('#stars').innerHTML=s+'</svg>';
  $('#stars').querySelectorAll('rect[data-n]').forEach(c=>{c.onmousemove=e=>showTT(`<b>${c.dataset.n}</b><br><span>VOD 프리미엄 ×${(+c.dataset.m).toFixed(2)} (주연 ${c.dataset.c}편)</span>`,e);c.onmouseleave=hideTT;});
})();

// 버틀러 필모 표
(function(){
  const rows=D.butler_comps.map(r=>`<tr><td><b>${r.t}</b></td><td class="mono">${fmt(r.th)}</td><td class="mono">${fmt(r.fy)}</td>
    <td class="mono">${r.R.toFixed(2)}</td><td class="axl">${r.oo}</td>
    <td class="mono"><b class="tag" style="background:color-mix(in srgb,var(--g2) ${Math.min(30,r.mult*8)}%,transparent);color:var(--g2)">×${r.mult.toFixed(2)}</b></td></tr>`).join('');
  $('#butler').insertAdjacentHTML('beforeend',rows);
})();

// 시장 하락
(function(){
  const M=D.market_index.map(m=>({y:+m.year,idx:+m.idx_2020,total:+m.total_vod}));
  const W=920,H=240,pl=44,pr=16,pt=16,pb=28,ymax=Math.max(...M.map(m=>m.idx))*1.08;
  const xs=M.map(m=>m.y),X=y=>pl+(y-xs[0])/(xs[xs.length-1]-xs[0])*(W-pl-pr),Y=v=>H-pb-(v/ymax)*(H-pt-pb);
  let g='';[0,25,50,75,100,125].forEach(v=>{if(v<=ymax)g+=`<line class="gl" x1="${pl}" y1="${Y(v)}" x2="${W-pr}" y2="${Y(v)}"/><text class="axl" x="${pl-6}" y="${Y(v)+3}" text-anchor="end">${v}</text>`;});
  M.forEach(m=>{if(m.y%2===0||m.y===2026)g+=`<text class="axl" x="${X(m.y)}" y="${H-8}" text-anchor="middle">${m.y}</text>`;});
  const area='M'+M.map(m=>`${X(m.y)},${Y(m.idx)}`).join(' L')+` L${X(xs[xs.length-1])},${Y(0)} L${X(xs[0])},${Y(0)} Z`;
  const line='M'+M.map(m=>`${X(m.y)},${Y(m.idx)}`).join(' L');
  const css=v=>getComputedStyle(document.body).getPropertyValue(v).trim();
  const mk=(yr,idx,col)=>`<line x1="${X(yr)}" y1="${pt}" x2="${X(yr)}" y2="${H-pb}" stroke="${col}" stroke-dasharray="3 3" stroke-width="1.5"/><circle cx="${X(yr)}" cy="${Y(idx)}" r="4.5" fill="${col}"/>`;
  const dots=M.map(m=>`<circle cx="${X(m.y)}" cy="${Y(m.idx)}" r="9" fill="transparent" data-y="${m.y}" data-i="${m.idx}" data-t="${m.total}"/>`).join('');
  $('#mkt').innerHTML=`<svg viewBox="0 0 ${W} ${H}"><path d="${area}" fill="var(--market)" opacity=".14"/><path d="${line}" fill="none" stroke="var(--market)" stroke-width="2.2"/>${g}${mk(2020,M.find(m=>m.y==2020).idx,css('--g1'))}${mk(2026,20.6,css('--g2'))}${dots}
    <text class="axl" x="${X(2020)}" y="${pt-2}" text-anchor="middle" fill="var(--g1)">1편</text><text class="axl" x="${X(2026)}" y="${pt-2}" text-anchor="middle" fill="var(--g2)">2편~</text></svg>`;
  $('#mkt').querySelectorAll('circle[data-y]').forEach(c=>{c.onmousemove=e=>showTT(`<b>${c.dataset.y}년</b> 지수 <b>${(+c.dataset.i).toFixed(0)}</b><br><span>총 ${fmt(+c.dataset.t)}건</span>`,e);c.onmouseleave=hideTT;});
})();

// 양극화
(function(){
  const P=D.polarization;if(!P||!P.length)return;
  const W=920,H=240,pl=40,pr=44,pt=16,pb=28,maxC=Math.max(...P.map(p=>p.mid_20_100k)),bw=(W-pl-pr)/P.length;
  const Y=v=>H-pb-(v/(maxC*1.1))*(H-pt-pb),YR=v=>H-pb-(v/100)*(H-pt-pb);
  let g='';[0,50,100,150].forEach(v=>{if(v<=maxC*1.1)g+=`<line class="gl" x1="${pl}" y1="${Y(v)}" x2="${W-pr}" y2="${Y(v)}"/><text class="axl" x="${pl-6}" y="${Y(v)+3}" text-anchor="end">${v}</text>`;});
  [70,80,90].forEach(v=>g+=`<text class="axl" x="${W-pr+6}" y="${YR(v)+3}" fill="var(--faint)">${v}%</text>`);
  const cols=[['mid_20_100k','var(--comp)'],['over_100k','var(--g2)'],['over_500k','var(--g1)']];let bars='';
  P.forEach((p,i)=>{const x0=pl+i*bw,gw=bw*0.72/3;cols.forEach((c,j)=>{const h=H-pb-Y(p[c[0]]);
    bars+=`<rect x="${x0+bw*0.14+j*gw}" y="${Y(p[c[0]])}" width="${gw-1.5}" height="${Math.max(0,h)}" rx="1.5" fill="${c[1]}" data-y="${p.year}" data-m="${p.mid_20_100k}" data-h="${p.over_100k}" data-v="${p.over_500k}" data-s="${p.top10_share}"/>`;});
    if(i%2===0)g+=`<text class="axl" x="${x0+bw/2}" y="${H-8}" text-anchor="middle">${p.year}</text>`;});
  const line='M'+P.map((p,i)=>`${pl+i*bw+bw/2},${YR(p.top10_share)}`).join(' L');
  $('#polar').innerHTML=`<svg viewBox="0 0 ${W} ${H}">${g}${bars}<path d="${line}" fill="none" stroke="var(--faint)" stroke-width="1.8" stroke-dasharray="4 3"/></svg>`;
  $('#polar').querySelectorAll('rect').forEach(c=>{c.onmousemove=e=>showTT(`<b>${c.dataset.y}년</b><br><span>중간대 ${c.dataset.m}·10만+ ${c.dataset.h}·50만+ ${c.dataset.v}</span><br><span>Top10% ${c.dataset.s}%</span>`,e);c.onmouseleave=hideTT;});
})();

// 산점도
(function(){
  const W=920,H=380,pl=52,pr=18,pt=16,pb=34,L=Math.log10;
  const xmin=L(3000),xmax=L(6e6),ymin=L(300),ymax=L(3e5);
  const X=v=>pl+(L(v)-xmin)/(xmax-xmin)*(W-pl-pr),Y=v=>H-pb-(L(Math.max(300,v))-ymin)/(ymax-ymin)*(H-pt-pb);
  let g='';[1e4,1e5,1e6].forEach(v=>g+=`<line class="gl" x1="${X(v)}" y1="${pt}" x2="${X(v)}" y2="${H-pb}"/><text class="axl" x="${X(v)}" y="${H-10}" text-anchor="middle">극장 ${v>=1e6?v/1e6+'M':v/1e3+'k'}</text>`);
  [1e3,1e4,1e5].forEach(v=>g+=`<line class="gl" x1="${pl}" y1="${Y(v)}" x2="${W-pr}" y2="${Y(v)}"/><text class="axl" x="${pl-6}" y="${Y(v)+3}" text-anchor="end">${v/1e3}k</text>`);
  const curve='M'+D.model_curve.filter(p=>p[0]>=3000&&p[0]<=6e6).map(p=>`${X(p[0])},${Y(p[1])}`).join(' L');
  const dots=D.comps_scatter.map(p=>`<circle cx="${X(p.th)}" cy="${Y(p.fy)}" r="${p.butler?5:3.6}" fill="${p.butler?'var(--warn)':'var(--comp)'}" opacity="${p.butler?.95:.6}" data-t="${p.t}" data-th="${p.th}" data-fy="${p.fy}" data-r="${p.R}" data-o="${p.oo}" data-b="${p.butler?1:0}"/>`).join('');
  const pt2=D.point;
  const g2=`<circle cx="${X(55446)}" cy="${Y(pt2)}" r="8" fill="var(--g2)" stroke="var(--surface)" stroke-width="2"/><text class="axl" x="${X(55446)+11}" y="${Y(pt2)+4}" fill="var(--g2)" style="font-weight:700">그린랜드2 ~${(pt2/1e3).toFixed(0)}k</text>`;
  const g1=`<circle cx="${X(326130)}" cy="${Y(266688)}" r="7" fill="var(--g1)" stroke="var(--surface)" stroke-width="2"/><text class="axl" x="${X(326130)}" y="${Y(266688)-11}" text-anchor="middle" fill="var(--g1)" style="font-weight:700">그린랜드1</text>`;
  $('#scat').innerHTML=`<svg viewBox="0 0 ${W} ${H}">${g}<path d="${curve}" fill="none" stroke="var(--faint)" stroke-width="2" stroke-dasharray="5 4"/>${dots}${g1}${g2}</svg>`;
  $('#scat').querySelectorAll('circle[data-t]').forEach(c=>{c.onmousemove=e=>{c.setAttribute('r',c.dataset.b=='1'?7:5.5);showTT(`<b>${c.dataset.t}</b>${c.dataset.b=='1'?' <span style="color:var(--warn)">버틀러</span>':''}<br><span>극장 ${fmt(+c.dataset.th)} → 온라인 ${fmt(+c.dataset.fy)}</span><br><span>R=${c.dataset.r} · ${c.dataset.o}</span>`,e);};c.onmouseleave=e=>{c.setAttribute('r',c.dataset.b=='1'?5:3.6);hideTT();};});
})();
</script></body></html>"""


def main():
    d = DATA
    reps = {
        "__GEN__": d["generated"],
        "__POINT__": money(d["point"]), "__GENRE_ONLY__": money(d["genre_only"]),
        "__P10__": money(d["percentiles"]["10"]), "__P90__": money(d["percentiles"]["90"]),
        "__SC_LO__": money(d["scenarios"]["conservative"]), "__SC_MID__": money(d["scenarios"]["base"]),
        "__SC_HI__": money(d["scenarios"]["optimistic"]),
        "__RANK__": str(d["star"]["rank"]), "__TOTAL__": str(d["star"]["total"]),
        "__BMULT__": f'{d["star"]["mult"]:.2f}', "__P90K__": str(d["probs"]["90000"]),
        "__G2R__": f'{d["point"]/d["anchors"]["greenland2"]["theater"]:.2f}',
        "__NOTES__": "".join(f'<div class="note">• {n}</div>' for n in d["notes"]),
        "__DATA__": json.dumps(d, ensure_ascii=False),
    }
    html = HTML
    for k, v in reps.items():
        html = html.replace(k, v)
    out = os.path.join(BASE, "vkobis_forecast.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"=> {os.path.basename(out)} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
