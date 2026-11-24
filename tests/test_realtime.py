"""Tests du client HTTP Mobilis, avec API simulée et sans serveur externe."""

import asyncio
import threading
import time
from datetime import UTC, datetime
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from mobilis import (
    ApiProtocolError,
    MobilisApiClient,
    StationSnapshot,
    compare_station_codes,
    retry_transient,
)


def _snapshot_payload(code: str = "MB-0001") -> dict[str, object]:
    return {
        "code": code,
        "velos_mecaniques": 3,
        "velos_electriques": 2,
        "places_libres": 10,
        "horodatage": "2026-11-23T10:00:00+00:00",
    }


def test_client_rejects_more_than_eight_concurrent_requests():
    with pytest.raises(ValueError, match="1 et 8"):
        MobilisApiClient(max_concurrency=9)


def test_retry_decorator_retries_transient_http_error(monkeypatch):
    attempts = 0
    delays: list[float] = []

    @retry_transient(max_attempts=3, base_delay=0.1)
    def request() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise HTTPError("http://test", 503, "temporary", Message(), None)
        return "ok"

    monkeypatch.setattr("mobilis.realtime.sleep", delays.append)

    assert request() == "ok"
    assert attempts == 3
    assert delays == [0.1, 0.2]


def test_retry_respects_retry_after_header(monkeypatch):
    attempts = 0
    delays: list[float] = []
    headers = Message()
    headers["Retry-After"] = "1.5"

    @retry_transient(max_attempts=2)
    def request() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPError("http://test", 429, "limited", headers, None)
        return "ok"

    monkeypatch.setattr("mobilis.realtime.sleep", delays.append)

    assert request() == "ok"
    assert delays == [1.5]


def test_retry_does_not_retry_non_transient_http_error(monkeypatch):
    attempts = 0

    @retry_transient(max_attempts=3)
    def request() -> str:
        nonlocal attempts
        attempts += 1
        raise HTTPError("http://test", 401, "unauthorized", Message(), None)

    monkeypatch.setattr("mobilis.realtime.sleep", lambda _: pytest.fail("unexpected retry"))

    with pytest.raises(HTTPError) as error:
        request()
    assert error.value.code == 401
    assert attempts == 1


def test_retry_returns_last_transient_error(monkeypatch):
    attempts = 0

    @retry_transient(max_attempts=2, base_delay=0)
    def request() -> str:
        nonlocal attempts
        attempts += 1
        raise HTTPError("http://test", 504, "gateway timeout", Message(), None)

    monkeypatch.setattr("mobilis.realtime.sleep", lambda _: None)

    with pytest.raises(HTTPError) as error:
        request()
    assert error.value.code == 504
    assert attempts == 2


def test_request_sends_api_key_and_decodes_json():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b'{"page": 1}'

    with patch("mobilis.realtime.urlopen", return_value=FakeResponse()) as mocked_urlopen:
        result = MobilisApiClient(api_key="test-key")._request_json("/stations?page=1")

    assert result == {"page": 1}
    request = mocked_urlopen.call_args.args[0]
    assert request.get_header("X-api-key") == "test-key"


def test_rejects_non_object_json_response():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b"[]"

    with (
        patch("mobilis.realtime.urlopen", return_value=FakeResponse()),
        pytest.raises(ApiProtocolError, match="objet"),
    ):
        MobilisApiClient()._request_json("/stations?page=1")


def test_reads_paginated_station_codes(monkeypatch):
    client = MobilisApiClient()
    payloads = {
        "/stations?page=1": {"page": 1, "stations": ["MB-0001"], "page_suivante": 2},
        "/stations?page=2": {"page": 2, "stations": ["MB-0002"], "page_suivante": None},
    }
    monkeypatch.setattr(client, "_request_json", lambda path: payloads[path])

    assert client.list_station_codes() == ("MB-0001", "MB-0002")


def test_detects_invalid_pagination(monkeypatch):
    client = MobilisApiClient()
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda _: {"page": 1, "stations": [], "page_suivante": 1},
    )

    with pytest.raises(ApiProtocolError, match="Page suivante invalide"):
        client.list_station_codes()


def test_parses_snapshot_and_requires_timezone(monkeypatch):
    client = MobilisApiClient()
    monkeypatch.setattr(client, "_request_json", lambda _: _snapshot_payload())

    snapshot = client.get_station("MB-0001")

    assert snapshot == StationSnapshot("MB-0001", 3, 2, 10, datetime(2026, 11, 23, 10, tzinfo=UTC))


def test_rejects_negative_counts_in_api_response(monkeypatch):
    client = MobilisApiClient()
    payload = _snapshot_payload()
    payload["velos_mecaniques"] = -1
    monkeypatch.setattr(client, "_request_json", lambda _: payload)

    with pytest.raises(ApiProtocolError, match="velos_mecaniques"):
        client.get_station("MB-0001")


def test_comparison_reports_codes_present_on_only_one_side():
    comparison = compare_station_codes(["MB-1", "MB-2"], ["MB-2", "MB-3"])

    assert comparison.missing_from_api == ("MB-1",)
    assert comparison.unknown_to_reference == ("MB-3",)


def test_async_snapshot_never_exceeds_configured_concurrency(monkeypatch):
    client = MobilisApiClient(max_concurrency=2)
    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def fake_get_station(code: str) -> StationSnapshot:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return StationSnapshot(code, 1, 0, 5, datetime.now(UTC))

    monkeypatch.setattr(client, "get_station", fake_get_station)
    codes = [f"MB-{number:04d}" for number in range(10)]

    report = asyncio.run(client.snapshot_all_async(codes))

    assert len(report.snapshots) == 10
    assert report.failures == ()
    assert maximum_active == 2


def test_snapshot_keeps_successes_when_one_station_is_unavailable(monkeypatch):
    client = MobilisApiClient()
    monkeypatch.setattr(client, "list_station_codes", lambda: ("MB-0001", "MB-0002"))

    def fake_get_station(code: str) -> StationSnapshot:
        if code == "MB-0002":
            raise HTTPError("http://test", 504, "offline", Message(), None)
        return StationSnapshot(code, 1, 0, 5, datetime.now(UTC))

    monkeypatch.setattr(client, "get_station", fake_get_station)

    report = client.snapshot_all(strategy="sequential")

    assert [snapshot.code for snapshot in report.snapshots] == ["MB-0001"]
    assert [(failure.code, failure.status_code) for failure in report.failures] == [
        ("MB-0002", 504)
    ]


def test_benchmark_reports_all_three_strategies(monkeypatch):
    client = MobilisApiClient(max_concurrency=2)
    monkeypatch.setattr(client, "list_station_codes", lambda: ("MB-0001", "MB-0002"))
    monkeypatch.setattr(
        client,
        "get_station",
        lambda code: StationSnapshot(code, 1, 0, 5, datetime.now(UTC)),
    )

    results = client.benchmark()

    assert [result.strategy for result in results] == ["sequential", "threads", "asyncio"]
    assert [result.stations_received for result in results] == [2, 2, 2]
    assert [result.stations_failed for result in results] == [0, 0, 0]
    assert all(result.elapsed_seconds >= 0 for result in results)
