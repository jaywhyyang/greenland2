# -*- coding: utf-8 -*-
"""
arthouse_final.csv → arthouse_report.html (내부 검토용 단일 파일 페이지)

주의: 개봉 여부를 저울질하는 내부 자료다.
      공개 대시보드(index.html / GitHub Pages)와 절대 섞지 않는다.
"""
import os
import csv
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "arthouse_final.csv")
OUT = os.path.join(BASE, "arthouse_report.html")

BEP = 30000
BAND = (23000, 33000)   # 로즈부시 유형 comp 클러스터
RERELEASE_GAP = 6
NDAY = 15

# 세그먼트에서 통째로 빼는 대상 (필터가 아니라 제외)
#  · 직배  : 글로벌 스튜디오 한국지사 배급작. 비직배 수입 시장을 보려는 목적이므로 제외.
#  · 성인에로: 청소년관람불가 + 개봉스크린 20개 미만.
#    주의 — 이 규칙은 '청불 소규모 개봉작'을 걸러내는 근사치이지 에로물을 정확히 집어내지 못한다.
#    실제로 크로넨버그 '미래의 범죄들'(칸 경쟁, 16개관)처럼 성격이 다른 작품도 함께 빠진다.
#    특정 작품을 되살리려면 KEEP 에 제목을 넣는다.
ERO_SCREEN_MAX = 20
KEEP = set()


def load():
    rows = []
    n_major = n_ero = 0
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        oy = int(r["개봉일"][:4])
        py = int(r["제작연도"]) if r["제작연도"].isdigit() else oy
        iv = lambda k: int(r[k]) if r.get(k) and r[k].strip() else 0
        if r["영화명"] not in KEEP:
            if r["직배여부"] == "직배":
                n_major += 1
                continue
            if "청소년관람불가" in r["등급"] and iv("개봉스크린수") < ERO_SCREEN_MAX:
                n_ero += 1
                continue
        rows.append({
            "name": r["영화명"], "open": r["개봉일"], "py": py,
            "nat": r["대표국적"], "gen": r["장르"], "dir": r["감독"],
            "dist": r["배급사"], "major": r["직배여부"], "grade": r["등급"],
            "scr": iv("개봉스크린수"),
            "fw": iv("첫주관객"), "w2": iv("2주누적"), "cum": iv("최종누적관객"),
            "seat": iv("14일좌석수"), "srate": float(r["평균좌석판매율"]) if r["평균좌석판매율"] else 0,
            "smiss": iv("좌석결손일"),
            "mult": float(r["배수"]) if r["배수"] else 0,
            "pers": iv("스크린당관객"),
            "c": [iv(f"D{i}") for i in range(NDAY)],
            "re": (oy - py) >= RERELEASE_GAP,
        })
    rows.sort(key=lambda r: -r["cum"])
    print(f"  제외: 직배 {n_major}편, 청불·소규모 {n_ero}편")
    return rows


HTML = """<title>신작 아트하우스 외화 실적 랭킹 · 2024–2026</title>
<style>
  :root{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --band:#A8452F; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  @media (prefers-color-scheme:dark){:root{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --band:#D4735A; --grid:#232B29; --shadow:none;
  }}
  :root[data-theme="dark"]{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --band:#D4735A; --grid:#232B29; --shadow:none;
  }
  :root[data-theme="light"]{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --band:#A8452F; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1340px;margin:0 auto;padding:44px 22px 90px;display:flex;flex-direction:column;gap:34px}
  header{display:flex;flex-direction:column;gap:9px;border-bottom:2px solid var(--ink);padding-bottom:18px}
  .eyebrow{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--band);font-weight:700}
  h1{margin:0;font-size:clamp(25px,4vw,37px);font-weight:800;letter-spacing:-.022em;line-height:1.18;text-wrap:balance}
  .sub{color:var(--muted);font-size:13.5px;max-width:70ch;margin:0}
  .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px 17px;
    display:flex;flex-direction:column;gap:4px;box-shadow:var(--shadow)}
  .tile .k{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700}
  .tile .v{font-size:25px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
  .tile .n{font-size:12px;color:var(--muted)}
  .tile.hero .v{color:var(--accent)} .tile.bad .v{color:var(--band)}
  section{display:flex;flex-direction:column;gap:13px}
  h2{margin:0;font-size:16.5px;font-weight:700;letter-spacing:-.01em}
  h2 .hint{font-weight:400;color:var(--muted);font-size:13px;margin-left:8px;letter-spacing:0}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:19px;box-shadow:var(--shadow)}
  .dist{display:flex;flex-direction:column;gap:7px}
  .drow{display:grid;grid-template-columns:92px 1fr 84px;align-items:center;gap:11px;font-size:13px}
  .drow .lb{color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
  .bar{height:19px;background:var(--grid);border-radius:3px;overflow:hidden}
  .bar i{display:block;height:100%;background:var(--muted);border-radius:3px}
  .drow.ok .bar i{background:var(--accent)} .drow.bd .bar i{background:var(--band)}
  .drow .ct{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}
  .drow.bd .lb,.drow.bd .ct{color:var(--band);font-weight:700}
  .lg{font-size:12.5px;color:var(--muted);display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;
    border-top:1px solid var(--line);padding-top:10px}
  .lg b{color:var(--band)} .lg .sw{color:var(--accent);font-weight:700}
  .ctl{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
  input[type=search]{flex:1 1 250px;min-width:190px;padding:9px 13px;border:1px solid var(--line);
    border-radius:8px;background:var(--card);color:var(--ink);font:inherit;font-size:14px}
  input[type=search]:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  button.tog{padding:9px 13px;border:1px solid var(--line);border-radius:8px;background:var(--card);
    color:var(--muted);font:inherit;font-size:13px;font-weight:600;cursor:pointer}
  button.tog[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--card)}
  .count{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto}
  .tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);box-shadow:var(--shadow)}
  table{border-collapse:collapse;width:100%;font-size:13px}
  th,td{padding:8px 11px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line)}
  thead th{position:sticky;top:0;background:var(--card);z-index:2;font-size:11px;letter-spacing:.05em;
    text-transform:uppercase;color:var(--muted);font-weight:700;cursor:pointer;user-select:none;
    border-bottom:2px solid var(--line)}
  thead th:hover{color:var(--ink)} thead th.on{color:var(--accent)}
  thead th.on::after{content:attr(data-a);margin-left:4px}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tbody tr:hover{background:color-mix(in srgb,var(--accent) 7%,transparent)}
  tbody tr:last-child td{border-bottom:none}
  .nm{font-weight:600;white-space:normal;min-width:180px;max-width:250px}
  .meta{color:var(--muted);font-size:11.5px}
  .cum{font-weight:700} .ok{color:var(--accent)} .no{color:var(--muted)}
  .pill{display:inline-block;padding:0 6px;border-radius:99px;font-size:10.5px;font-weight:700;
    border:1px solid currentColor;margin-left:5px;vertical-align:1px;color:var(--muted)}
  .pill.mj{color:var(--band)}
  td.dist{max-width:150px;overflow:hidden;text-overflow:ellipsis}
  .spark{display:block}
  tr.mark td{background:color-mix(in srgb,var(--band) 13%,var(--card));border-top:2px solid var(--band);
    border-bottom:2px solid var(--band);font-weight:700;color:var(--band);white-space:normal;font-size:12.5px}
  tr.mark span{font-weight:500;color:var(--muted);display:block;font-size:11.5px;margin-top:2px}
  footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:15px}
  footer code{background:var(--grid);padding:1px 5px;border-radius:4px;font-size:11.5px}
  @media (max-width:640px){.wrap{padding:26px 13px 60px}.drow{grid-template-columns:74px 1fr 60px}}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">KOBIS 데이터 분석 · 2024–2026</div>
    <h1>신작 아트하우스 외화 실적 랭킹</h1>
    <p class="sub">2024년 1월 ~ 2026년 4월 개봉, KOBIS에서 다양성영화 × 외국영화로 분류된 __N__편.
      최종 누적관객 내림차순. <b>직배(글로벌 스튜디오 한국지사 배급)</b>와 <b>청소년관람불가 중 개봉 20개관 미만</b>은 세그먼트에서 제외했고, 재개봉·구작(개봉연도 − 제작연도 ≥ 6년)은 기본 숨김입니다.</p>
  </header>

  <div class="tiles">__TILES__</div>

  <section>
    <h2>관객수 구간별 분포<span class="hint">BEP 3만 명 기준선과 로즈부시 예상 밴드</span></h2>
    <div class="panel">
      <div class="dist">__DIST__</div>
      <div class="lg">
        <span class="sw">■ BEP 3만 명 돌파 구간</span>
        <span><b>■ 로즈부시 프루닝 예상 밴드 (2.3만–3.3만)</b></span>
      </div>
    </div>
  </section>

  <section>
    <h2>전체 랭킹<span class="hint">열 제목을 눌러 정렬 · D+0~D+14 곡선은 각 행의 스파크라인</span></h2>
    <div class="ctl">
      <input type="search" id="q" placeholder="영화명 · 감독 · 국가 · 장르 검색" aria-label="검색">
      <button class="tog" id="tre" aria-pressed="false">재개봉 포함</button>
      <button class="tog" id="tbep" aria-pressed="false">BEP 돌파만</button>
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
          <th class="num" data-k="scr">개봉스크린</th>
          <th class="num" data-k="seat">14일 좌석수</th>
          <th class="num" data-k="srate">좌석판매율</th>
          <th data-k="rank">D+0 → D+14</th>
          <th class="num" data-k="fw">첫주</th>
          <th class="num" data-k="w2">2주누적</th>
          <th class="num" data-k="cum">최종누적</th>
          <th class="num" data-k="mult">배수</th>
        </tr></thead>
        <tbody id="tb"></tbody>
      </table>
    </div>
  </section>

  <footer>
    출처 KOBIS 영화관입장권통합전산망 · 수집 __DATE__ ·
    <code>kobis_arthouse_scan.py</code> → <code>kobis_arthouse_enrich.py</code> →
    <code>kobis_arthouse_daily.py</code> → <code>kobis_arthouse_merge.py</code><br>
    <b>좌석수 주의</b> — KOBIS 기간별 좌석 통계는 하루 50편만 제공하며 페이징·영화명 필터가 동작하지 않습니다.
    하루 좌석 240석 미만의 소형 상영은 집계에서 빠지므로, 좌석수가 비었거나 결손일이 많은 행은 과소집계입니다.
    배수는 최종누적÷첫주관객(입소문 계수)이며 값이 클수록 개봉 후 확산형입니다.
  </footer>
</div>

<script>
const D=__DATA__, BEP=__BEP__, BAND=__BAND__;
const tb=document.getElementById('tb'), q=document.getElementById('q'), ct=document.getElementById('ct'),
      tre=document.getElementById('tre'), tbep=document.getElementById('tbep');
let sortK='rank', sortA=true, showRe=false, onlyBep=false;
const fmt=n=>n?n.toLocaleString('ko-KR'):'–';
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

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
  if(onlyBep) r=r.filter(d=>d.cum>=BEP);
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
  for(const d of r){
    if(banded&&!marked){
      const desc=(sortK==='cum'&&!sortA)||(sortK==='rank'&&sortA);
      if(desc&&d.cum<BAND[1]){
        html+=`<tr class="mark"><td colspan="13">여기부터 로즈부시 프루닝 예상 구간 (2.3만–3.3만)
          <span>동일 유형 comp — 에밀리아 페레즈 33,103 · 퀴어 29,104 · 노스페라투 25,830 · 마리아 25,082 · 베이비걸 22,859</span></td></tr>`;
        marked=true;
      }
    }
    const ok=d.cum>=BEP;
    const seat=d.seat?fmt(d.seat)+(d.smiss>3?'<span class="pill">결손</span>':''):'–';
    html+=`<tr>
      <td class="num meta">${d.rank}</td>
      <td class="nm">${esc(d.name)}${d.re?'<span class="pill">재개봉</span>':''}
        <div class="meta">${esc([d.dir,d.gen].filter(Boolean).join(' · '))||'&nbsp;'}</div></td>
      <td class="meta">${d.open}</td>
      <td class="meta">${esc(d.nat)||'–'}</td>
      <td class="meta dist" title="${esc(d.dist)}">${esc(d.dist)||'–'}</td>
      <td class="num">${fmt(d.scr)}</td>
      <td class="num">${seat}</td>
      <td class="num meta">${d.srate?d.srate.toFixed(1)+'%':'–'}</td>
      <td>${spark(d.c)}</td>
      <td class="num">${fmt(d.fw)}</td>
      <td class="num">${fmt(d.w2)}</td>
      <td class="num cum ${ok?'ok':'no'}">${fmt(d.cum)}</td>
      <td class="num meta">${d.mult?d.mult.toFixed(1)+'×':'–'}</td>
    </tr>`;
  }
  tb.innerHTML=html;
  const nb=r.filter(d=>d.cum>=BEP).length;
  ct.textContent=`${r.length}편 표시 · BEP 돌파 ${nb}편 (${r.length?(100*nb/r.length).toFixed(1):0}%)`;
}

document.querySelectorAll('thead th').forEach(th=>{
  th.addEventListener('click',()=>{
    const k=th.dataset.k;
    if(sortK===k) sortA=!sortA;
    else{sortK=k; sortA=['rank','name','open','nat'].includes(k);}
    document.querySelectorAll('thead th').forEach(o=>{o.classList.remove('on');o.removeAttribute('data-a');});
    th.classList.add('on'); th.setAttribute('data-a',sortA?'↑':'↓');
    draw();
  });
});
q.addEventListener('input',draw);
tre.addEventListener('click',()=>{showRe=!showRe;tre.setAttribute('aria-pressed',showRe);
  tre.textContent=showRe?'재개봉 포함됨':'재개봉 포함';draw();});
tbep.addEventListener('click',()=>{onlyBep=!onlyBep;tbep.setAttribute('aria-pressed',onlyBep);draw();});

draw();
</script>
"""


def main():
    rows = load()
    live = [r for r in rows if not r["re"]]
    c = sorted(r["cum"] for r in live)
    n = len(c)
    nbep = sum(1 for x in c if x >= BEP)
    nseat = sum(1 for r in live if r["seat"])

    tiles = [
        ("분석 대상", f"{n}편", "재개봉 제외 신작"),
        ("중앙값", f"{c[n//2]:,}", "절반이 이 아래"),
        ("BEP 3만 돌파", f"{round(100*nbep/n,1)}%", f"{nbep}편 / {n}편", "hero"),
        ("5천 명 미만", f"{sum(1 for x in c if x < 5000)}편",
         f"전체의 {round(100*sum(1 for x in c if x<5000)/n)}%", "bad"),
        ("좌석 확보", f"{nseat}편", f"{round(100*nseat/n)}% · 소형작 결손"),
    ]
    th = "".join(f'<div class="tile {t[3] if len(t)>3 else ""}"><span class="k">{t[0]}</span>'
                 f'<span class="v">{t[1]}</span><span class="n">{t[2]}</span></div>' for t in tiles)

    buckets = [(200000, 10**9, "20만+"), (100000, 200000, "10만–20만"), (50000, 100000, "5만–10만"),
               (30000, 50000, "3만–5만"), (20000, 30000, "2만–3만"), (10000, 20000, "1만–2만"),
               (5000, 10000, "5천–1만"), (1000, 5000, "1천–5천"), (0, 1000, "1천 미만")]
    cnt = [(lb, sum(1 for r in live if lo <= r["cum"] < hi), lo) for lo, hi, lb in buckets]
    mx = max(x for _, x, _ in cnt) or 1
    dist = "".join(
        f'<div class="drow {"ok" if lo>=BEP else ("bd" if lo==20000 else "")}">'
        f'<span class="lb">{lb}</span><span class="bar"><i style="width:{max(2,round(100*v/mx))}%"></i></span>'
        f'<span class="ct">{v}편</span></div>' for lb, v, lo in cnt)

    keys = ("name", "open", "nat", "gen", "dir", "dist", "major", "scr", "seat",
            "srate", "smiss", "fw", "w2", "cum", "mult", "c", "re")
    data = [{k: r[k] for k in keys} for r in rows]
    html = (HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
                .replace("__TILES__", th).replace("__DIST__", dist)
                .replace("__N__", str(n)).replace("__BEP__", str(BEP))
                .replace("__BAND__", json.dumps(list(BAND)))
                .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d")))
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"완료: {OUT} (전체 {len(rows)}편 / 신작 {n}편 / 좌석확보 {nseat}편)")


if __name__ == "__main__":
    main()
