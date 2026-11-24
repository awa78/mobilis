"""Tests des commandes disponibles avant l'intégration des cas 2 et 3."""

import csv
import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

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


def test_facturation_command_reproduces_monthly_revenue(tmp_path: Path, capsys) -> None:
    tarifs = {
        "grilles": [
            {
                "en_vigueur_du": "2025-01-01",
                "formules": {
                    "occasionnel": {
                        "minutes_incluses": 0,
                        "tranche_minutes": 15,
                        "prix_tranche": "0.60",
                        "supplement_electrique_tranche": "0.40",
                        "frais_deblocage": "1.00",
                        "plafond_jour": None,
                    }
                },
            }
        ],
        "seuil_non_restitution_heures": 24,
        "penalite_non_restitution": "150.00",
    }
    tarifs_path = tmp_path / "tarifs.json"
    tarifs_path.write_text(json.dumps(tarifs), encoding="utf-8")
    abonnes_path = tmp_path / "abonnes.jsonl"
    abonnes_path.write_text("", encoding="utf-8")
    stations_path = tmp_path / "stations.csv"
    stations_path.write_text("Code station;Nom\nS1;Station 1\nS2;Station 2\n", encoding="cp1252")
    trajets_path = tmp_path / "trajets.csv.gz"
    with gzip.open(trajets_path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "trajet_id",
                "abonne_id",
                "velo_id",
                "type_velo",
                "station_depart",
                "debut",
                "station_arrivee",
                "fin",
                "distance_m",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "trajet_id": "T1",
                "abonne_id": "",
                "velo_id": "V1",
                "type_velo": "mecanique",
                "station_depart": "S1",
                "debut": "2026-09-10T10:00:00+02:00",
                "station_arrivee": "S2",
                "fin": "2026-09-10T10:20:00+02:00",
                "distance_m": "1000",
            }
        )

    assert main(["frequentation", "--trajets", str(trajets_path)]) == 0
    assert "Trajets uniques : 1" in capsys.readouterr().out

    assert (
        main(
            [
                "facturation",
                "--trajets",
                str(trajets_path),
                "--tarifs",
                str(tarifs_path),
                "--abonnes",
                str(abonnes_path),
                "--stations",
                str(stations_path),
            ]
        )
        == 0
    )
    assert "2026-09 - recettes : 2.20 EUR" in capsys.readouterr().out
