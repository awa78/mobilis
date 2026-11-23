"""Tests des commandes disponibles avant l'intégration des cas 2 et 3."""

import csv
from datetime import UTC, date, datetime

from mobilis import (
    Station,
    StationComparison,
    StationFailure,
    StationReport,
    StationSnapshot,
    StationStatus,
    StrategyMeasurement,
)
from mobilis.cli import main
from mobilis.realtime import SnapshotReport


def _report() -> StationReport:
    station = Station(
        code="MB-0001",
        name="Place Centrale",
        municipality="Valmont",
        capacity=10,
        latitude=45.75,
        longitude=4.83,
        status=StationStatus.ACTIVE,
        commissioned_on=date(2024, 2, 1),
    )
    return StationReport(1, (station,), (), ())


def test_stations_command_prints_summary(tmp_path, capsys):
    source = tmp_path / "stations.csv"
    with source.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "Code station",
                "Nom",
                "Commune",
                "Capacité",
                "Latitude",
                "Longitude",
                "Statut",
                "Mise en service",
            ],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerow(
            {
                "Code station": "MB-0001",
                "Nom": "Place Centrale",
                "Commune": "Valmont",
                "Capacité": "10",
                "Latitude": "45,75",
                "Longitude": "4,83",
                "Statut": "En service",
                "Mise en service": "01/02/2024",
            }
        )

    assert main(["stations", "--stations", str(source)]) == 0
    output = capsys.readouterr().out
    assert "Lignes lues : 1" in output
    assert "Stations exploitables : 1" in output


def test_state_command_uses_api_and_shows_comparison(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, base_url, api_key):
            assert base_url == "http://api.test"
            assert api_key == "key"

        def list_station_codes(self):
            return ("MB-0001", "MB-0002")

        def snapshot_all(self, strategy, codes):
            assert strategy == "threads"
            assert codes == ("MB-0001", "MB-0002")
            return SnapshotReport(
                snapshots=(
                    StationSnapshot("MB-0001", 0, 0, 10, datetime(2026, 11, 23, tzinfo=UTC)),
                ),
                failures=(StationFailure("MB-0002", "offline", 504),),
            )

    monkeypatch.setattr("mobilis.cli.load_stations", lambda _: _report())
    monkeypatch.setattr("mobilis.cli.MobilisApiClient", FakeClient)
    monkeypatch.setattr(
        "mobilis.cli.compare_station_codes",
        lambda reference, api: StationComparison((), ("MB-0002",)),
    )

    assert (
        main(
            [
                "etat",
                "--stations",
                "stations.csv",
                "--api-url",
                "http://api.test",
                "--api-key",
                "key",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Photos reçues : 1" in output
    assert "Bornes injoignables : 1" in output
    assert "Stations sans vélo : MB-0001" in output
    assert "Inconnues du référentiel : MB-0002" in output


def test_state_benchmark_command_prints_measurements(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, base_url, api_key):
            pass

        def benchmark(self):
            return (
                StrategyMeasurement("sequential", 2.0, 1, 0),
                StrategyMeasurement("threads", 0.5, 1, 0),
                StrategyMeasurement("asyncio", 0.7, 1, 0),
            )

    monkeypatch.setattr("mobilis.cli.load_stations", lambda _: _report())
    monkeypatch.setattr("mobilis.cli.MobilisApiClient", FakeClient)

    assert main(["etat", "--stations", "stations.csv", "--benchmark"]) == 0
    output = capsys.readouterr().out
    assert "sequential : 2.00 s" in output
    assert "threads : 0.50 s" in output
    assert "asyncio : 0.70 s" in output
