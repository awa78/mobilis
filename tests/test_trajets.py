import csv
import gzip
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mobilis.trajets import (
    analyser_trajets,
    convertir_date,
    convertir_trajets,
    dedoublonner_trajets,
    filtrer_trajets,
    lire_trajets,
    pipeline_trajets,
)


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (
            "2026-08-01T00:04:23+02:00",
            datetime(2026, 7, 31, 22, 4, 23, tzinfo=UTC),
        ),
        (
            "2026-08-01T00:43:46Z",
            datetime(2026, 8, 1, 0, 43, 46, tzinfo=UTC),
        ),
        (
            "01/08/2026 00:42:17",
            datetime(2026, 7, 31, 22, 42, 17, tzinfo=UTC),
        ),
    ],
)
def test_convertir_date_formats_valides(
    valeur: str,
    attendu: datetime,
) -> None:
    assert convertir_date(valeur) == attendu


def test_convertir_date_valeur_vide() -> None:
    assert convertir_date("") is None


def test_convertir_trajets_compte_dates_manquantes_et_invalides() -> None:
    anomalies: Counter[str] = Counter()
    trajets = list(
        convertir_trajets(
            iter(
                [
                    {"trajet_id": "T1", "debut": "date incorrecte", "fin": ""},
                    {"trajet_id": "T2", "debut": "2026-08-01T08:00:00Z", "fin": ""},
                ]
            ),
            anomalies,
        )
    )
    assert len(trajets) == 2
    assert trajets[0]["debut"] is None
    assert anomalies["date_invalide:debut"] == 1
    assert anomalies["date_manquante:fin"] == 2


def test_lire_trajets_fichier_gzip(tmp_path: Path) -> None:
    chemin = tmp_path / "trajets.csv.gz"

    donnees = [
        {
            "trajet_id": "T001",
            "abonne_id": "A001",
            "velo_id": "V001",
            "type_velo": "mecanique",
            "station_depart": "MB-001",
            "debut": "2026-08-01T08:00:00+02:00",
            "station_arrivee": "MB-002",
            "fin": "2026-08-01T08:15:00+02:00",
            "distance_m": "2500",
        }
    ]

    with gzip.open(chemin, mode="wt", encoding="utf-8", newline="") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=donnees[0].keys())
        writer.writeheader()
        writer.writerows(donnees)

    trajets = list(lire_trajets(chemin))

    assert len(trajets) == 1
    assert trajets[0]["trajet_id"] == "T001"
    assert trajets[0]["station_depart"] == "MB-001"
    assert trajets[0]["distance_m"] == "2500"


def test_convertir_trajets_convertit_dates_et_conserve_champs() -> None:
    trajet = {
        "trajet_id": "T001",
        "abonne_id": "A001",
        "velo_id": "V001",
        "type_velo": "mecanique",
        "station_depart": "MB-001",
        "debut": "2026-08-01T08:00:00+02:00",
        "station_arrivee": "MB-002",
        "fin": "2026-08-01T08:15:00+02:00",
        "distance_m": "2500",
    }

    trajets_convertis = list(convertir_trajets(iter([trajet])))

    assert len(trajets_convertis) == 1
    assert trajets_convertis[0]["debut"] == datetime(2026, 8, 1, 6, 0, 0, tzinfo=UTC)
    assert trajets_convertis[0]["fin"] == datetime(2026, 8, 1, 6, 15, 0, tzinfo=UTC)
    assert trajets_convertis[0]["distance_m"] == "2500"
    assert trajets_convertis[0]["trajet_id"] == "T001"


def test_convertir_trajets_ne_modifie_pas_trajet_original() -> None:
    trajet = {
        "trajet_id": "T001",
        "debut": "2026-08-01T08:00:00+02:00",
        "fin": "2026-08-01T08:15:00+02:00",
    }

    list(convertir_trajets(iter([trajet])))

    assert isinstance(trajet["debut"], str)
    assert isinstance(trajet["fin"], str)


def test_dedoublonner_trajets() -> None:
    trajets = [
        {"trajet_id": "T001", "distance_m": "2500"},
        {"trajet_id": "T002", "distance_m": "1800"},
        {"trajet_id": "T001", "distance_m": "2500"},
        {"trajet_id": "T003", "distance_m": "3000"},
    ]

    resultat = list(dedoublonner_trajets(trajets))

    assert len(resultat) == 3
    assert [trajet["trajet_id"] for trajet in resultat] == [
        "T001",
        "T002",
        "T003",
    ]


def test_dedoublonner_trajets_conserve_trajets_sans_identifiant() -> None:
    trajets = [
        {"trajet_id": "", "distance_m": "1200"},
        {"trajet_id": "", "distance_m": "1400"},
    ]

    resultat = list(dedoublonner_trajets(trajets))

    assert len(resultat) == 2


def test_dedoublonner_compte_doublons_et_identifiants_absents() -> None:
    anomalies: Counter[str] = Counter()
    resultat = list(
        dedoublonner_trajets(
            [
                {"trajet_id": " T001 "},
                {"trajet_id": "T001"},
                {"trajet_id": ""},
            ],
            anomalies,
        )
    )
    assert len(resultat) == 2
    assert anomalies["trajet_id_duplique"] == 1
    assert anomalies["identifiant_absent"] == 1


def test_filtrer_trajets_distance_minimale() -> None:
    trajets = [
        {"trajet_id": "T001", "distance_m": "1000"},
        {"trajet_id": "T002", "distance_m": "2500"},
        {"trajet_id": "T003", "distance_m": "4000"},
    ]

    resultat = list(
        filtrer_trajets(
            trajets,
            lambda trajet: int(str(trajet["distance_m"])) >= 2500,
        )
    )

    assert len(resultat) == 2
    assert [trajet["trajet_id"] for trajet in resultat] == ["T002", "T003"]


def test_filtrer_trajets_resultat_vide() -> None:
    trajets = [
        {"trajet_id": "T001", "distance_m": "1000"},
        {"trajet_id": "T002", "distance_m": "1500"},
    ]

    resultat = list(
        filtrer_trajets(
            trajets,
            lambda trajet: int(str(trajet["distance_m"])) > 5000,
        )
    )

    assert resultat == []


def test_pipeline_trajets_complet(tmp_path: Path) -> None:
    chemin = tmp_path / "trajets.csv.gz"

    donnees = [
        {
            "trajet_id": "T001",
            "abonne_id": "A001",
            "velo_id": "V001",
            "type_velo": "mecanique",
            "station_depart": "MB-001",
            "debut": "2026-08-01T08:00:00+02:00",
            "station_arrivee": "MB-002",
            "fin": "2026-08-01T08:15:00+02:00",
            "distance_m": "2500",
        },
        {
            "trajet_id": "T001",
            "abonne_id": "A001",
            "velo_id": "V001",
            "type_velo": "mecanique",
            "station_depart": "MB-001",
            "debut": "2026-08-01T08:00:00+02:00",
            "station_arrivee": "MB-002",
            "fin": "2026-08-01T08:15:00+02:00",
            "distance_m": "2500",
        },
        {
            "trajet_id": "T002",
            "abonne_id": "A002",
            "velo_id": "V002",
            "type_velo": "electrique",
            "station_depart": "MB-003",
            "debut": "2026-08-01T09:00:00+02:00",
            "station_arrivee": "MB-004",
            "fin": "2026-08-01T09:30:00+02:00",
            "distance_m": "5000",
        },
    ]

    with gzip.open(chemin, "wt", encoding="utf-8", newline="") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=donnees[0].keys())
        writer.writeheader()
        writer.writerows(donnees)

    resultat = list(pipeline_trajets(chemin))

    assert len(resultat) == 2
    assert resultat[0]["trajet_id"] == "T001"
    assert resultat[1]["trajet_id"] == "T002"
    assert isinstance(resultat[0]["debut"], datetime)


def test_pipeline_trajets_avec_filtre(tmp_path: Path) -> None:
    chemin = tmp_path / "trajets.csv.gz"

    donnees = [
        {
            "trajet_id": "T001",
            "abonne_id": "A001",
            "velo_id": "V001",
            "type_velo": "mecanique",
            "station_depart": "MB-001",
            "debut": "2026-08-01T08:00:00+02:00",
            "station_arrivee": "MB-002",
            "fin": "2026-08-01T08:15:00+02:00",
            "distance_m": "1000",
        },
        {
            "trajet_id": "T002",
            "abonne_id": "A002",
            "velo_id": "V002",
            "type_velo": "electrique",
            "station_depart": "MB-003",
            "debut": "2026-08-01T09:00:00+02:00",
            "station_arrivee": "MB-004",
            "fin": "2026-08-01T09:30:00+02:00",
            "distance_m": "5000",
        },
    ]

    with gzip.open(chemin, "wt", encoding="utf-8", newline="") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=donnees[0].keys())
        writer.writeheader()
        writer.writerows(donnees)

    resultat = list(
        pipeline_trajets(
            chemin,
            lambda trajet: int(str(trajet["distance_m"])) >= 2500,
        )
    )

    assert len(resultat) == 1
    assert resultat[0]["trajet_id"] == "T002"


def test_pipeline_trajets_sans_filtre(tmp_path: Path) -> None:
    chemin = tmp_path / "trajets.csv.gz"

    donnees = [
        {
            "trajet_id": "T001",
            "abonne_id": "A001",
            "velo_id": "V001",
            "type_velo": "mecanique",
            "station_depart": "MB-001",
            "debut": "2026-08-01T08:00:00+02:00",
            "station_arrivee": "MB-002",
            "fin": "2026-08-01T08:15:00+02:00",
            "distance_m": "2500",
        },
    ]

    with gzip.open(chemin, "wt", encoding="utf-8", newline="") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=donnees[0].keys())
        writer.writeheader()
        writer.writerows(donnees)

    resultat = list(pipeline_trajets(chemin))

    assert len(resultat) == 1
    assert resultat[0]["trajet_id"] == "T001"


def test_analyser_trajets_statistiques_completes() -> None:
    trajets = [
        {
            "trajet_id": "T001",
            "station_depart": "S001",
            "station_arrivee": "S002",
            "debut": datetime(2026, 8, 3, 8, 0, tzinfo=ZoneInfo("Europe/Paris")),
            "fin": datetime(2026, 8, 3, 8, 30, tzinfo=ZoneInfo("Europe/Paris")),
            "distance_m": "2500",
        },
        {
            "trajet_id": "T002",
            "station_depart": "S001",
            "station_arrivee": "S003",
            "debut": datetime(2026, 8, 3, 18, 0, tzinfo=ZoneInfo("Europe/Paris")),
            "fin": datetime(2026, 8, 3, 18, 30, tzinfo=ZoneInfo("Europe/Paris")),
            "distance_m": "3500",
        },
        {
            "trajet_id": "T003",
            "station_depart": "S004",
            "station_arrivee": "S001",
            "debut": datetime(2026, 8, 8, 12, 0, tzinfo=ZoneInfo("Europe/Paris")),
            "fin": datetime(2026, 8, 8, 12, 30, tzinfo=ZoneInfo("Europe/Paris")),
            "distance_m": "1500",
        },
    ]

    resultat = analyser_trajets(trajets)

    assert resultat["total_trajets"] == 3
    assert resultat["distance_totale_m"] == 7500

    departs = resultat["departs_par_station"]
    arrivees = resultat["arrivees_par_station"]

    assert isinstance(departs, dict)
    assert isinstance(arrivees, dict)

    assert departs["S001"] == 2
    assert arrivees["S001"] == 1

    profil = resultat["profil_horaire"]
    assert isinstance(profil, dict)
    assert profil[8] == 1
    assert profil[18] == 1
    assert profil[12] == 1

    semaine = resultat["profil_semaine"]
    weekend = resultat["profil_week_end"]

    assert isinstance(semaine, dict)
    assert isinstance(weekend, dict)
    assert semaine[8] == 1
    assert weekend[12] == 1

    matin = resultat["departs_matin"]
    soir = resultat["arrivees_soir"]

    assert isinstance(matin, dict)
    assert isinstance(soir, dict)
    assert matin["S001"] == 1
    assert soir["S003"] == 1


def test_analyser_trajets_classe_les_stations_par_flux_net() -> None:
    paris = ZoneInfo("Europe/Paris")
    trajets = [
        {
            "station_depart": "A",
            "station_arrivee": "B",
            "debut": datetime(2026, 8, 3, 8, 0, tzinfo=paris),
            "distance_m": "1000",
        },
        {
            "station_depart": "C",
            "station_arrivee": "A",
            "debut": datetime(2026, 8, 3, 8, 30, tzinfo=paris),
            "distance_m": "1000",
        },
        {
            "station_depart": "D",
            "station_arrivee": "E",
            "debut": datetime(2026, 8, 3, 18, 0, tzinfo=paris),
            "distance_m": "1000",
        },
        {
            "station_depart": "E",
            "station_arrivee": "F",
            "debut": datetime(2026, 8, 3, 18, 30, tzinfo=paris),
            "distance_m": "1000",
        },
    ]
    resultat = analyser_trajets(trajets)
    assert resultat["stations_vides_matin"] == [("C", 1)]
    assert resultat["stations_pleines_soir"] == [("F", 1)]
