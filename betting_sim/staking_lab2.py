"""
자금운용 정밀 비교 v2 — 실제 운영 조건 반영
- 판 배당 2.0(묶음 1.90~2.20의 중심), 판당 기대값 EV 시나리오별
- 600판(하루 약 5판 x 4개월), 시작 1,000만 → 목표 1억(도달 시 중단), 2만회 몬테카를로
- 핵심 정리(최적 정지 정리): 공정한 게임(EV=0)에서는 어떤 베팅법을 써도
  P(1억 도달) <= 시작/목표 = 10%. EV<0이면 더 낮다. 베팅법은 기대값을 못 바꾸고 '분포 모양'만 바꾼다.
"""
import numpy as np
rng = np.random.default_rng(11)
S, G, N, R, O = 1e7, 1e8, 600, 20000, 2.0

def run(ev, kind):
    p = (1 + ev) / O
    B = np.full(R, S); peak = B.copy(); st = np.zeros(R); nxt = np.zeros(R)
    done = np.zeros(R, bool); hit = np.zeros(R, bool); t_end = np.full(R, N)
    for i in range(N):
        live = ~done & (B > 10_000)
        if kind == "연구용 고정 2%":          s = 0.02 * B
        elif kind == "고정비율 10%":         s = 0.10 * B
        elif kind == "파롤리3 기본10% (현행)": s = np.where(st > 0, nxt, 0.10 * B)
        elif kind == "파롤리3 기본5%":       s = np.where(st > 0, nxt, 0.05 * B)
        elif kind == "파롤리4 기본6%":       s = np.where(st > 0, nxt, 0.0625 * B)
        elif kind == "대담한 베팅":          s = (G - B) / (O - 1)
        elif kind == "바닥500만+파롤리3":     s = np.where(st > 0, nxt, 0.10 * np.maximum(B - 5e6, 0))
        elif kind == "최고점50% 잠금+파롤리3": s = np.where(st > 0, nxt, 0.10 * np.maximum(B - 0.5 * peak, 0))
        s = np.where(live, np.minimum(s, B), 0)
        w = rng.random(R) < p
        B = B + np.where(w, s * (O - 1), -s); peak = np.maximum(peak, B)
        if "파롤리" in kind:
            k = 4 if "파롤리4" in kind else 3
            st = np.where(w & (s > 0), st + 1, 0); nxt = np.where(w, s * O, 0); r = st >= k; st[r] = 0
        newhit = live & (B >= G); hit |= newhit
        ended = live & ((B >= G) | (B <= 10_000)); t_end[ended & ~done] = i + 1; done |= ended
    return hit.mean(), (B < 1e6).mean(), np.median(B), np.median(t_end)

K = ["연구용 고정 2%", "고정비율 10%", "파롤리3 기본10% (현행)", "파롤리3 기본5%", "파롤리4 기본6%",
     "바닥500만+파롤리3", "최고점50% 잠금+파롤리3", "대담한 베팅"]
for ev in [0.0, -0.03, 0.03]:
    print(f"\n=== 판당 기대값 {ev*100:+.0f}% · 배당 2.0 · 최대 600판 (이론 상한: EV=0이면 1억 확률 ≤10%) ===")
    print(f"  {'전략':22s} {'1억 도달':>8s} {'100만 미만':>10s} {'자금 중앙값':>10s} {'끝날 때까지 판수(중앙)':>18s}")
    for k in K:
        h, z, m, t = run(ev, k)
        print(f"  {k:22s} {h*100:7.1f}% {z*100:9.1f}% {m/1e6:8.1f}백만 {t:14.0f}판")
