"""
Tests for Phase 5: LinUCB bandit, features, pattern detector, and API endpoints.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from app.agent.features import FEATURE_DIM, build_feature_vector
from app.agent.learner import LinUCBModel, load_model, save_model


# ── Feature vector ─────────────────────────────────────────────────────────────

def _slot(hour: int, dow: int = 0) -> datetime:
    """Create a UTC-aware datetime for a given hour and day-of-week (Mon=0)."""
    # 2025-01-06 is a Monday; add dow days to shift day
    base = datetime(2025, 1, 6 + dow, hour, 0, tzinfo=timezone.utc)
    return base


def test_feature_vector_length():
    x = build_feature_vector("want", None, 60, _slot(9), {})
    assert len(x) == FEATURE_DIM


def test_feature_vector_bias():
    x = build_feature_vector("want", None, 60, _slot(9), {})
    assert x[-1] == 1.0  # bias term always 1


def test_feature_vector_priority_one_hot_need():
    x = build_feature_vector("need", None, 60, _slot(9), {})
    assert x[4] == 1.0  # need
    assert x[5] == 0.0  # want
    assert x[6] == 0.0  # like


def test_feature_vector_priority_one_hot_like():
    x = build_feature_vector("like", None, 60, _slot(9), {})
    assert x[4] == 0.0
    assert x[5] == 0.0
    assert x[6] == 1.0


def test_feature_vector_deadline_urgency_near():
    """A deadline 2 days away should yield high (positive) urgency signal."""
    near_deadline = date(2025, 1, 8)  # 2 days from slot date 2025-01-06
    x = build_feature_vector("want", near_deadline, 60, _slot(9), {})
    # tanh((2-7)/7) is negative (overdue-ish)
    assert x[7] < 0.0


def test_feature_vector_deadline_urgency_far():
    """A deadline 30 days away should yield neutral/positive urgency."""
    far_deadline = date(2025, 2, 5)  # ~30 days from 2025-01-06
    x = build_feature_vector("want", far_deadline, 60, _slot(9), {})
    assert x[7] > 0.0


def test_feature_vector_uses_patterns():
    """Historical completion rates from patterns should appear in features."""
    patterns = {
        "completion_by_hour": [0.9 if i == 9 else 0.3 for i in range(24)],
        "completion_by_dow": [0.8] * 7,
    }
    x = build_feature_vector("want", None, 60, _slot(9), patterns)
    assert x[8] == pytest.approx(0.9)  # hist_hour
    assert x[9] == pytest.approx(0.8)  # hist_dow


# ── LinUCBModel ────────────────────────────────────────────────────────────────

def test_model_fresh_score_returns_float():
    model = LinUCBModel()
    x = build_feature_vector("want", None, 60, _slot(9), {})
    score = model.score(x)
    assert isinstance(score, float)


def test_model_is_cold_initially():
    model = LinUCBModel()
    assert model.is_cold is True


def test_model_not_cold_after_updates():
    model = LinUCBModel()
    x = build_feature_vector("want", None, 60, _slot(9), {})
    for _ in range(5):
        model.update(x, 1.0)
    assert model.is_cold is False


def test_model_update_increases_n_updates():
    model = LinUCBModel()
    x = build_feature_vector("want", None, 60, _slot(9), {})
    model.update(x, 0.8)
    assert model.n_updates == 1


def test_model_positive_reward_raises_score():
    """After seeing positive rewards, the model should score similar slots higher."""
    model = LinUCBModel(alpha=0.0)  # no exploration; pure exploitation
    x = build_feature_vector("want", None, 60, _slot(9), {})
    score_before = model.score(x)

    for _ in range(10):
        model.update(x, 1.0)

    score_after = model.score(x)
    assert score_after > score_before


def test_model_negative_reward_lowers_score():
    """After negative rewards, the model should score similar slots lower."""
    model = LinUCBModel(alpha=0.0)
    x = build_feature_vector("want", None, 60, _slot(9), {})
    # Warm up with a few neutral updates first
    x_other = build_feature_vector("want", None, 60, _slot(14), {})
    for _ in range(3):
        model.update(x_other, 0.5)

    score_before = model.score(x)
    for _ in range(5):
        model.update(x, -0.5)
    score_after = model.score(x)
    assert score_after < score_before


def test_model_serialise_round_trip():
    model = LinUCBModel()
    x = build_feature_vector("want", None, 60, _slot(9), {})
    model.update(x, 1.0)

    d = model.to_dict()
    restored = LinUCBModel.from_dict(d)

    assert restored.n_updates == 1
    assert restored.score(x) == pytest.approx(model.score(x), abs=1e-9)


def test_load_model_fresh_when_no_bandit_in_prefs():
    model = load_model({})
    assert model.n_updates == 0
    assert model.is_cold


def test_load_model_restores_from_prefs():
    model = LinUCBModel()
    x = build_feature_vector("want", None, 60, _slot(9), {})
    for _ in range(6):
        model.update(x, 0.9)

    prefs = save_model(model, {})
    restored = load_model(prefs)
    assert restored.n_updates == 6
    assert not restored.is_cold


def test_save_model_preserves_other_prefs():
    model = LinUCBModel()
    prefs = {"wake_hour": 7, "patterns": {"data_points": 42}}
    updated = save_model(model, prefs)
    assert updated["wake_hour"] == 7
    assert updated["patterns"]["data_points"] == 42
    assert "bandit" in updated


# ── API integration tests ──────────────────────────────────────────────────────

async def test_insights_endpoint_empty(client, auth_headers):
    """GET /insights should return a valid response even with no activity data."""
    resp = await client.get("/api/v1/insights", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data_points" in data
    assert "bandit_updates" in data
    assert "model_warm" in data
    assert data["model_warm"] is False


async def test_rate_schedule_endpoint(client, auth_headers):
    """POST /schedules/{id}/rate should persist the rating."""
    # Create a schedule to rate
    schedule_resp = await client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={"period_start": "2025-03-01", "period_end": "2025-03-07"},
    )
    assert schedule_resp.status_code == 201
    schedule_id = schedule_resp.json()["id"]

    rate_resp = await client.post(
        f"/api/v1/schedules/{schedule_id}/rate",
        headers=auth_headers,
        json={"rating": 5, "feedback_text": "Great schedule!"},
    )
    assert rate_resp.status_code == 200
    data = rate_resp.json()
    assert data["user_rating"] == 5


async def test_rate_schedule_invalid_rating(client, auth_headers):
    """Ratings outside 1-5 should return 422."""
    schedule_resp = await client.post(
        "/api/v1/schedules",
        headers=auth_headers,
        json={"period_start": "2025-04-01", "period_end": "2025-04-07"},
    )
    schedule_id = schedule_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/schedules/{schedule_id}/rate",
        headers=auth_headers,
        json={"rating": 6},
    )
    assert resp.status_code == 422


async def test_generate_schedule_uses_bandit(client, auth_headers):
    """After warmup updates the generate endpoint should still work correctly."""
    # Create task
    await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Bandit test task",
            "priority": "want",
            "total_duration_minutes": 60,
            "min_block_minutes": 30,
            "max_block_minutes": 60,
        },
    )
    resp = await client.post(
        "/api/v1/schedules/generate",
        headers=auth_headers,
        json={"period_start": "2025-02-03", "period_end": "2025-02-03"},
    )
    assert resp.status_code == 201
    assert resp.json()["generated_by_agent"] is True
