"""Unit tests for ImpersonationDetectionService helpers."""

from datetime import datetime, timedelta, timezone

from src.services.impersonation_detection_service import (
    ImpersonationDetectionService,
)


def test_account_age_days_handles_timezone_aware_datetime():
    service = ImpersonationDetectionService()
    created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    now = datetime(2020, 1, 11, tzinfo=timezone.utc)

    assert service._calculate_account_age_days(created_at, now) == 10


def test_account_age_days_normalizes_naive_datetime():
    service = ImpersonationDetectionService()
    created_at = datetime(2020, 1, 1)  # naive
    now = datetime(2020, 1, 2, tzinfo=timezone.utc) + timedelta(hours=1)

    assert service._calculate_account_age_days(created_at, now) == 1
