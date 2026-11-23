"""Tests du chargement et de la validation du référentiel des stations."""

import csv
from datetime import date

import pytest

from mobilis import Station, StationFileError, StationStatus, load_stations

FIELDS = [
    "Code station",
    "Nom",
    "Commune",
    "Capacité",
    "Latitude",
    "Longitude",
    "Statut",
    "Mise en service",
]


def _row(
    code: str = "MB-0001",
    capacity: str = "20",
    latitude: str = "45,75",
    longitude: str = "4,83",
    status: str = "En service",
    commissioned: str = "01/02/2024",
) -> dict[str, str]:
    return {
        "Code station": code,
        "Nom": "Place Centrale",
        "Commune": "Valmont",
        "Capacité": capacity,
        "Latitude": latitude,
        "Longitude": longitude,
        "Statut": status,
        "Mise en service": commissioned,
    }


def _write_csv(path, rows: list[dict[str, str]], fields: list[str] = FIELDS) -> None:
    with path.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def test_loads_valid_station_and_normalizes_status(tmp_path):
    source = tmp_path / "stations.csv"
    _write_csv(source, [_row(status=" EN SERVICE ")])

    report = load_stations(source)

    assert report.rows_read == 1
    assert len(report.stations) == 1
    station = report.stations[0]
    assert station.status is StationStatus.ACTIVE
    assert station.latitude == 45.75
    assert station.longitude == 4.83
    assert station.commissioned_on == date(2024, 2, 1)
    assert report.exploitable_stations == (station,)
    assert report.anomalies == ()


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("en_service", StationStatus.ACTIVE),
        ("Hors service", StationStatus.OUT_OF_SERVICE),
        ("HS", StationStatus.OUT_OF_SERVICE),
        ("FERMEE", StationStatus.CLOSED),
        ("Fermée", StationStatus.CLOSED),
    ],
)
def test_normalizes_known_statuses(tmp_path, raw_status, expected):
    source = tmp_path / "stations.csv"
    _write_csv(source, [_row(status=raw_status)])

    report = load_stations(source)

    assert report.stations[0].status is expected
    assert not report.anomalies


def test_accepts_iso_service_date(tmp_path):
    source = tmp_path / "stations.csv"
    _write_csv(source, [_row(commissioned="2024-02-01")])

    assert load_stations(source).stations[0].commissioned_on == date(2024, 2, 1)


def test_collects_unknown_capacity_and_missing_coordinates(tmp_path):
    source = tmp_path / "stations.csv"
    _write_csv(source, [_row(capacity="NC", latitude="", longitude="")])

    report = load_stations(source)

    assert len(report.stations) == 1
    assert report.stations[0].capacity is None
    assert report.stations[0].latitude is None
    assert report.stations[0].longitude is None
    assert {anomaly.field for anomaly in report.anomalies} == {"Capacité", "Coordonnées"}
    assert report.exploitable_stations == ()


def test_reports_unknown_status_but_keeps_station(tmp_path):
    source = tmp_path / "stations.csv"
    _write_csv(source, [_row(status="bientot ouverte")])

    report = load_stations(source)

    assert report.stations[0].status is StationStatus.UNKNOWN
    assert [(item.field, item.value) for item in report.anomalies] == [
        ("Statut", "bientot ouverte")
    ]


def test_excludes_every_row_with_duplicate_code(tmp_path):
    source = tmp_path / "stations.csv"
    _write_csv(source, [_row(), _row(capacity="30")])

    report = load_stations(source)

    assert report.rows_read == 2
    assert report.stations == ()
    assert report.duplicate_codes == ("MB-0001",)
    assert len([item for item in report.anomalies if item.field == "Code station"]) == 2


def test_rejects_invalid_station_values():
    with pytest.raises(ValueError, match="latitude"):
        Station(
            code="MB-0001",
            name="Station",
            municipality="Valmont",
            capacity=20,
            latitude=91,
            longitude=4,
            status=StationStatus.ACTIVE,
            commissioned_on=None,
        )


def test_rejects_file_without_required_columns(tmp_path):
    source = tmp_path / "stations.csv"
    _write_csv(source, [], fields=["Code station", "Nom"])

    with pytest.raises(StationFileError, match="Colonnes absentes"):
        load_stations(source)
