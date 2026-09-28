"""Adaptive conformal inference.

Split conformal assumes exchangeability between calibration and serving data. This archive
violates that twice over (a +24% material shock in 2026, a -25% insulation-labour reprice in
2025Q4), which is exactly why static calibration over-covers on some buckets and under-covers
on others.

ACI (Gibbs & Candes 2021) fixes it by treating the miscoverage level as a control variable
updated from realised coverage:

    alpha_{t+1} = alpha_t + gamma * (alpha_target - miscoverage_t)

Long-run coverage converges to 1 - alpha_target under ARBITRARY distribution shift, with no
exchangeability assumption. DtACI (Gibbs & Candes 2022) removes the need to pick gamma by
running several in parallel and aggregating them with exponential weights on pinball loss.

Both are implemented in BATCH form: one update per month, since quotes arrive in monthly cohorts.
"""
import numpy as np


def conformal_q(scores, alpha):
    """Finite-sample corrected conformal quantile of the nonconformity scores."""
    scores = np.asarray(scores, float)
    scores = scores[np.isfinite(scores)]
    n = len(scores)
    if n == 0:
        return np.inf
    if n < 10:
        return float(np.quantile(scores, np.clip(1 - alpha, 0, 1)))
    lvl = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(scores, np.clip(lvl, 0, 1)))


def pinball(scores, q, alpha):
    """Pinball loss of predicting quantile q at level (1-alpha) for observed scores."""
    s = np.asarray(scores, float)
    d = s - q
    return float(np.mean(np.where(d > 0, (1 - alpha) * d, -alpha * d)))


class ACI:
    """Single-gamma adaptive conformal inference, batch updates."""

    def __init__(self, alpha_target=0.20, gamma=0.03, lo=1e-3, hi=0.60):
        self.a_t = float(alpha_target)
        self.target = float(alpha_target)
        self.gamma = float(gamma)
        self.lo, self.hi = lo, hi
        self.history = []

    def alpha(self):
        return float(np.clip(self.a_t, self.lo, self.hi))

    def update(self, covered):
        """covered: boolean array for the batch just served."""
        covered = np.asarray(covered, bool)
        if covered.size == 0:
            return
        miscov = 1.0 - covered.mean()
        self.a_t = self.a_t + self.gamma * (self.target - miscov)
        self.a_t = float(np.clip(self.a_t, self.lo, self.hi))
        self.history.append((miscov, self.a_t))


class DtACI:
    """Multi-gamma ACI with exponentially weighted aggregation (no gamma to tune)."""

    def __init__(self, alpha_target=0.20, gammas=(0.005, 0.02, 0.06, 0.16),
                 eta=2.0, sigma=0.02, lo=1e-3, hi=0.60):
        self.target = float(alpha_target)
        self.gammas = np.array(gammas, float)
        self.a = np.full(len(gammas), float(alpha_target))
        self.w = np.ones(len(gammas)) / len(gammas)
        self.eta, self.sigma = eta, sigma
        self.lo, self.hi = lo, hi
        self.history = []

    def alpha(self):
        a = float(np.clip(np.sum(self.w * self.a) / np.sum(self.w), self.lo, self.hi))
        return a

    def update(self, covered, scores=None, q_used=None):
        covered = np.asarray(covered, bool)
        if covered.size == 0:
            return
        miscov = 1.0 - covered.mean()
        # expert-wise loss: pinball of each expert's own quantile level
        if scores is not None and q_used is not None:
            losses = np.array([pinball(scores, q_used, ai) for ai in self.a])
        else:
            losses = np.abs(self.a - miscov)
        losses = losses / (np.max(losses) + 1e-12)
        self.w = self.w * np.exp(-self.eta * losses)
        self.w = (1 - self.sigma) * self.w / np.sum(self.w) + self.sigma / len(self.w)
        self.a = np.clip(self.a + self.gammas * (self.target - miscov), self.lo, self.hi)
        self.history.append((miscov, self.alpha()))


def scaled_mondrian_q(scores_cal, groups_cal, groups_te, alpha, shrink=40.0, min_n=12):
    """Grade-conditional width WITHOUT fragmenting the calibration set.

    One global quantile sets the shape; each group gets a multiplicative SCALE estimated from
    its median absolute score, shrunk toward 1 by n/(n+k). With ~700 calibration rows a separate
    quantile per grade is hopeless, but a single shrunk scale per grade is estimable.
    """
    s = np.asarray(scores_cal, float)
    gq = conformal_q(s, alpha)
    med_all = float(np.median(s)) if len(s) else 1.0
    if med_all <= 0:
        med_all = 1e-6
    scale = {}
    for g in np.unique(groups_cal):
        sel = groups_cal == g
        n = int(sel.sum())
        if n < min_n:
            scale[g] = 1.0
            continue
        raw = float(np.median(s[sel])) / med_all
        lam = n / (n + shrink)
        scale[g] = lam * raw + (1 - lam) * 1.0
    return gq * np.array([scale.get(g, 1.0) for g in groups_te])
