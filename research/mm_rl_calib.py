"""Calibrated RL sweep — v4: reward-aligned trainer, PAIRED multi-seed eval, honest CIs.

v3 evaluated baseline then RL on DIFFERENT random draws (shared, advancing RNG) and reported single
point estimates. v4 fixes both: for each eval seed we run baseline and RL on the SAME market draws
(paired), then report mean delta +/- 95% CI across seeds. Training reward is now aligned to terminal
PnL (inv_penalty=0, gamma=1.0) so the learned policy optimizes exactly what we score.

Real-tape adverse selection ~2.6% of spread income => plausible informed_rate band ~0.03-0.08.
"""
import random
from mm_rl import train, evaluate, N_ACT

EVAL_SEEDS = [7, 42, 123, 999, 8675]
med_neutral = 1 * 3 + 1


def ci95(xs):
    xs = sorted(xs)
    n = len(xs)
    lo = xs[max(0, int(0.025 * n) - 1)]
    hi = xs[min(n - 1, int(0.975 * n))]
    return lo, hi


if __name__ == "__main__":
    import time
    t0 = time.time()
    print(f"{'informed':>9} {'baseline':>9} {'RL':>9} {'delta':>8} {'RL win-seeds':>13} {'verdict':>18}")
    for ir in (0.30, 0.15, 0.08, 0.03):
        Q = train(informed_rate=ir)                       # reward-aligned training at this regime
        rl_pol = lambda s: max(range(N_ACT), key=Q[s].__getitem__)
        bl_pol = lambda s: med_neutral
        b_means, r_means, deltas = [], [], []
        for sd in EVAL_SEEDS:
            bm, *_ = evaluate(bl_pol, n=6000, informed_rate=ir, seed=sd)   # SAME seed =>
            rm, *_ = evaluate(rl_pol, n=6000, informed_rate=ir, seed=sd)   # identical scenarios (paired)
            b_means.append(bm); r_means.append(rm); deltas.append(rm - bm)
        bmean = sum(b_means) / len(b_means)
        rmean = sum(r_means) / len(r_means)
        dmean = sum(deltas) / len(deltas)
        lo, hi = ci95(deltas)
        win_seeds = sum(1 for d in deltas if d > 0)
        beats = dmean > 0 and lo > 0                      # positive AND CI excludes 0
        prof = rmean > 0
        verdict = ("RL>baseline" if beats else "tie/rl-worse") + (" +profit" if prof else " -loss")
        print(f"{ir:>9.2f} {bmean:>9.3f} {rmean:>9.3f} {dmean:>+8.3f} {win_seeds:>10}/{len(EVAL_SEEDS)} {verdict:>18}")
    print(f"\n(paired eval: baseline & RL see identical draws per seed; delta CI over {len(EVAL_SEEDS)} seeds)")
    print(f"swept in {time.time()-t0:.0f}s")
