"""
바카라 베팅법 비교 — 목표: '시드 5배'(1,000만 → 5,000만), 올인 금지
조건: 판 배당 2.0(묶음 2.0 근처), 최대 600판, 판당 기대값 EV 시나리오별, 경로 20,000개
단위 U = 체인(시퀀스) 시작 시점 자금 x f  (f = 2~15% 그리드)  → 자금이 늘면 단위도 커짐
이론 상한(최적 정지 정리): EV=0이면 어떤 방법도 P(5배) <= 1/5 = 20%

시퀀스형(이기면 다음 칸, 지면 처음으로):
  파롤리3 1-2-4 / 파롤리4 1-2-4-8 / 파롤리5 1-2-4-8-16 (완주하면 처음으로)
  1-2-4-8-8-8 (8에서 고정 유지, 사용자 제안)
  1-3-2-6 (고전 바카라 시스템)
  역피보나치 1-1-2-3-5-8-13-21 (21에서 유지)
  역 달랑베르(+1 이기면, -1 지면)
  (비교용) 마틴게일 1-2-4-8-16-32: 지면 2배, 이기면 처음으로 — 음의 진행
"""
import numpy as np

S, TARGET, N, R = 1.0, 5.0, 600, 20000
RUIN = 0.02  # 시드의 2% 미만이면 파산 처리

SEQ = {
    "파롤리3 (1-2-4)":        ([1, 2, 4], "reset"),
    "파롤리4 (1-2-4-8)":      ([1, 2, 4, 8], "reset"),
    "파롤리5 (1-2-4-8-16)":   ([1, 2, 4, 8, 16], "reset"),
    "1-2-4-8-8-8 (8 고정)":   ([1, 2, 4, 8], "stay"),
    "1-3-2-6":               ([1, 3, 2, 6], "reset"),
    "역피보나치 (~21 유지)":   ([1, 1, 2, 3, 5, 8, 13, 21], "stay"),
}


def sim(ev, kind, f, seed=1):
    rng = np.random.default_rng(seed)
    p = (1 + ev) / 2.0
    B = np.full(R, S); U = f * B; idx = np.zeros(R, int); lvl = np.ones(R)
    done = np.zeros(R, bool); hit = np.zeros(R, bool); maxfrac = np.zeros(R)
    for _ in range(N):
        live = ~done
        if kind in SEQ:
            seq = np.array(SEQ[kind][0], float)
            s = U * seq[idx]
        elif kind == "역 달랑베르 (+1/-1)":
            s = U * lvl
        elif kind == "마틴게일 (비교용, 음의 진행)":
            seq = np.array([1, 2, 4, 8, 16, 32], float)
            s = U * seq[idx]
        s = np.where(live, np.minimum(s, B), 0)
        maxfrac = np.maximum(maxfrac, np.where(B > 0, s / np.maximum(B, 1e-12), 0))
        w = rng.random(R) < p
        B = B + np.where(w, s, -s)
        # 상태 전이
        if kind in SEQ:
            seq_len = len(SEQ[kind][0]); mode = SEQ[kind][1]
            nxt = idx + 1
            if mode == "reset":
                reset = (~w) | (nxt >= seq_len)
                idx = np.where(reset, 0, nxt)
            else:
                reset = ~w
                idx = np.where(reset, 0, np.minimum(nxt, seq_len - 1))
            U = np.where(reset, f * B, U)
        elif kind == "역 달랑베르 (+1/-1)":
            lvl = np.where(w, lvl + 1, np.maximum(lvl - 1, 1))
            U = np.where(lvl == 1, f * B, U)
        elif kind == "마틴게일 (비교용, 음의 진행)":
            nxt = idx + 1
            reset = w | (nxt >= 6)
            idx = np.where(reset, 0, nxt)
            U = np.where(reset, f * B, U)
        newly = live & ((B >= TARGET) | (B < RUIN))
        hit |= live & (B >= TARGET)
        done |= newly
    return hit.mean(), (B < 0.1).mean(), np.median(B), np.median(maxfrac)


if __name__ == "__main__":
    kinds = list(SEQ) + ["역 달랑베르 (+1/-1)", "마틴게일 (비교용, 음의 진행)"]
    grid = [0.02, 0.03, 0.05, 0.08, 0.10, 0.15]
    for ev in [0.0, -0.02]:
        print(f"\n=== 판당 기대값 {ev*100:+.0f}% · 목표 5배 · 최대 600판 (EV=0 이론 상한 20%) ===")
        print(f"  {'베팅법':26s} {'최적 단위':>7s} {'5배 확률':>8s} {'90%+ 손실':>9s} {'자금 중앙값':>9s} {'최대 1회 베팅(자금 대비, 중앙)':>20s}")
        for k in kinds:
            best = max(((f, *sim(ev, k, f)) for f in grid), key=lambda x: x[1])
            f, h, z, m, mx = best
            print(f"  {k:26s} {f*100:6.0f}% {h*100:7.1f}% {z*100:8.1f}% {m:8.2f}배 {mx*100:16.0f}%")
