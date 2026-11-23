"""Tests de lecture en flux et de conversion des dates Mobilis."""

import csv
import gzip
from collections import Counter
from datetime import UTC, datetime

import pytest

from mobilis.trajets import convertir_date, convertir_trajets, lire_trajets


def test_reads_compressed_csv_as_a_generator(tmp_path):
    source = tmp_path / "trajets.csv.gz"
    with gzip.open(source, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["trajet_id", "debut"])
        writer.writeheader()
        writer.writerow({"trajet_id": "T1", "debut": "2026-08-01T10:00:00+02:00"})

    rows = lire_trajets(source)

    assert iter(rows) is rows
    assert next(rows) == {"trajet_id": "T1", "debut": "2026-08-01T10:00:00+02:00"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "2026-08-01T10:00:00+02:00",
            datetime(2026, 8, 1, 8, tzinfo=UTC),
        ),
        (
            "2026-08-01T08:00:00Z",
            datetime(2026, 8, 1, 8, tzinfo=UTC),
        ),
        (
            "01/08/2026 10:00:00",
            datetime(2026, 8, 1, 8, tzinfo=UTC),
        ),
    ],
)
def test_converts_supported_date_formats_to_utc(raw, expected):
    assert convertir_date(raw) == expected


def test_empty_date_is_none():
    assert convertir_date("") is None
    assert convertir_date("   ") is None


def test_invalid_date_raises_a_clear_error():
    with pytest.raises(ValueError, match="Date de trajet invalide"):
        convertir_date("31/02/2026 10:00:00")


def test_conversion_counts_bad_date_and_continues():
    anomalies: Counter[str] = Counter()
    source = iter(
        [
            {"trajet_id": "T1", "debut": "bad date", "fin": ""},
            {"trajet_id": "T2", "debut": "2026-08-01T10:00:00Z", "fin": ""},
        ]
    )

    converted = list(convertir_trajets(source, anomalies))

    assert converted[0]["debut"] is None
    assert converted[1]["debut"] == datetime(2026, 8, 1, 10, tzinfo=UTC)
    assert anomalies == Counter({"date_invalide:debut": 1})
