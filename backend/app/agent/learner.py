"""
LinUCB contextual bandit for slot scoring.

Uses a single shared linear model (not disjoint arms):
  A ∈ R^(d×d)  — design matrix (initialised to λI)
  b ∈ R^d       — reward vector

Score:  θ̂ᵀx + α√(xᵀA⁻¹x)    (exploitation + UCB exploration bonus)
Update: A ← A + xxᵀ,  b ← b + r·x

Model state is stored as plain Python lists so it round-trips through JSONB
without any numpy dependency.  For d=12 the matrix is 144 floats (~1 KB).
"""

from __future__ import annotations

import math
from typing import Any

from app.agent.features import FEATURE_DIM

DEFAULT_ALPHA: float = 0.5   # exploration–exploitation trade-off
DEFAULT_LAMBDA: float = 1.0  # regularisation (λI initialisation)
COLD_START_THRESHOLD: int = 5  # updates before we trust the model


class LinUCBModel:
    """Wraps the design matrix A and reward vector b."""

    def __init__(
        self,
        alpha: float = DEFAULT_ALPHA,
        d: int = FEATURE_DIM,
        lam: float = DEFAULT_LAMBDA,
    ) -> None:
        self.alpha = alpha
        self.d = d
        self.n_updates = 0
        self._A_flat: list[float] = _identity_flat(d, lam)
        self._b: list[float] = [0.0] * d

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "A": self._A_flat,
            "b": self._b,
            "alpha": self.alpha,
            "d": self.d,
            "n_updates": self.n_updates,
            "version": 1,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinUCBModel":
        m = cls.__new__(cls)
        m.d = data.get("d", FEATURE_DIM)
        m.alpha = data.get("alpha", DEFAULT_ALPHA)
        m.n_updates = data.get("n_updates", 0)
        m._A_flat = list(data["A"])
        m._b = list(data["b"])
        return m

    # ── Core algorithm ────────────────────────────────────────────────────────

    def score(self, x: list[float]) -> float:
        """UCB score for feature vector x.  Higher → prefer this slot."""
        A_inv = _invert_flat(self._A_flat, self.d)
        theta = _mat_vec(A_inv, self._b, self.d)
        mu = _dot(theta, x)
        sigma_sq = _quad_form(A_inv, x, self.d)
        return mu + self.alpha * math.sqrt(max(0.0, sigma_sq))

    def update(self, x: list[float], reward: float) -> None:
        """Online weight update after observing reward r for context x."""
        d = self.d
        for i in range(d):
            for j in range(d):
                self._A_flat[i * d + j] += x[i] * x[j]
        for i in range(d):
            self._b[i] += reward * x[i]
        self.n_updates += 1

    @property
    def is_cold(self) -> bool:
        """True if the model has not yet seen enough updates to be reliable."""
        return self.n_updates < COLD_START_THRESHOLD


# ── Model persistence helpers ─────────────────────────────────────────────────

def load_model(preferences: dict) -> LinUCBModel:
    """Load the bandit from user.preferences, or return a fresh model."""
    data = preferences.get("bandit")
    if data and isinstance(data, dict) and "A" in data and "b" in data:
        try:
            return LinUCBModel.from_dict(data)
        except Exception:
            pass
    return LinUCBModel()


def save_model(model: LinUCBModel, preferences: dict) -> dict:
    """Return an updated preferences dict with the serialised bandit model."""
    return {**preferences, "bandit": model.to_dict()}


# ── Pure-Python linear algebra (no numpy required) ────────────────────────────

def _identity_flat(d: int, scale: float = 1.0) -> list[float]:
    A = [0.0] * (d * d)
    for i in range(d):
        A[i * d + i] = scale
    return A


def _dot(a: list[float], b: list[float]) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def _mat_vec(A: list[float], v: list[float], d: int) -> list[float]:
    result = [0.0] * d
    for i in range(d):
        for j in range(d):
            result[i] += A[i * d + j] * v[j]
    return result


def _quad_form(A: list[float], x: list[float], d: int) -> float:
    """Compute xᵀ A x."""
    Ax = _mat_vec(A, x, d)
    return _dot(x, Ax)


def _invert_flat(A_flat: list[float], d: int) -> list[float]:
    """Gauss-Jordan inversion of a d×d row-major flat matrix."""
    # Build augmented matrix [A | I]
    aug: list[list[float]] = []
    for i in range(d):
        row = [A_flat[i * d + j] for j in range(d)] + [1.0 if i == j else 0.0 for j in range(d)]
        aug.append(row)

    for col in range(d):
        # Find the pivot row
        pivot = col
        for row in range(col + 1, d):
            if abs(aug[row][col]) > abs(aug[pivot][col]):
                pivot = row
        aug[col], aug[pivot] = aug[pivot], aug[col]

        denom = aug[col][col]
        if abs(denom) < 1e-12:
            continue  # near-singular column — leave as-is

        inv_denom = 1.0 / denom
        for j in range(2 * d):
            aug[col][j] *= inv_denom

        for row in range(d):
            if row != col:
                factor = aug[row][col]
                for j in range(2 * d):
                    aug[row][j] -= factor * aug[col][j]

    result = [0.0] * (d * d)
    for i in range(d):
        for j in range(d):
            result[i * d + j] = aug[i][d + j]
    return result
