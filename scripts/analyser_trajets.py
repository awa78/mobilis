"""Affiche les statistiques de fréquentation à partir d'un flux de trajets."""

from __future__ import annotations

import argparse
import os
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import cast

from mobilis.trajets import analyser_trajets, pipeline_trajets

_NOM_TRAJETS = "trajets_2026-08_2026-10.csv.gz"


def _chemin_par_defaut() -> Path | None:
    chemin = os.environ.get("MOBILIS_TRAJETS")
    if chemin:
        return Path(chemin)
    repertoire = os.environ.get("MOBILIS_DATA_DIR")
    if repertoire:
        return Path(repertoire) / _NOM_TRAJETS
    return None


def analyser(chemin: Path) -> None:
    anomalies: Counter[str] = Counter()
    tracemalloc.start()
    statistiques = analyser_trajets(
        pipeline_trajets(chemin, anomalies=anomalies), anomalies=anomalies
    )
    memoire_actuelle, pic_memoire = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_trajets = cast(int, statistiques["total_trajets"])
    distance_totale = cast(int, statistiques["distance_totale_m"])
    departs = cast(dict[str, int], statistiques["departs_par_station"])
    arrivees = cast(dict[str, int], statistiques["arrivees_par_station"])
    profil_horaire = cast(dict[int, int], statistiques["profil_horaire"])
    profil_semaine = cast(dict[int, int], statistiques["profil_semaine"])
    profil_week_end = cast(dict[int, int], statistiques["profil_week_end"])
    stations_vides = cast(list[tuple[str, int]], statistiques["stations_vides_matin"])
    stations_pleines = cast(list[tuple[str, int]], statistiques["stations_pleines_soir"])

    print("\n========== BILAN GLOBAL ==========")
    print(f"Nombre de trajets uniques : {total_trajets:,}")
    print(f"Distance totale : {distance_totale:,} m ({distance_totale / 1000:,.2f} km)")
    print(f"Anomalies comptées : {sum(anomalies.values()):,} — {dict(anomalies)}")
    print(f"Mémoire actuelle : {memoire_actuelle / 1024 / 1024:.2f} Mo")
    print(f"Pic mémoire Python : {pic_memoire / 1024 / 1024:.2f} Mo")

    for titre, compteurs in (
        ("TOP 10 DÉPARTS", departs),
        ("TOP 10 ARRIVÉES", arrivees),
    ):
        print(f"\n========== {titre} ==========")
        for station, nombre in sorted(compteurs.items(), key=lambda item: (-item[1], item[0]))[:10]:
            print(f"{station} : {nombre:,}")

    for titre, profil in (
        ("PROFIL HORAIRE", profil_horaire),
        ("PROFIL SEMAINE", profil_semaine),
        ("PROFIL WEEK-END", profil_week_end),
    ):
        print(f"\n========== {titre} ==========")
        for heure, nombre in sorted(profil.items()):
            print(f"{heure:02d}h : {nombre:,}")

    print("\n========== STATIONS QUI SE VIDENT LE MATIN ==========")
    for station, sorties_nettes in stations_vides[:10]:
        print(f"{station} : +{sorties_nettes:,} départs nets")

    print("\n========== STATIONS QUI SE REMPLISSENT LE SOIR ==========")
    for station, arrivees_nettes in stations_pleines[:10]:
        print(f"{station} : +{arrivees_nettes:,} arrivées nettes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trajets",
        type=Path,
        default=_chemin_par_defaut(),
        help="chemin du CSV gzip (ou MOBILIS_TRAJETS / MOBILIS_DATA_DIR)",
    )
    arguments = parser.parse_args()
    if arguments.trajets is None:
        parser.error("indiquez --trajets CHEMIN ou définissez MOBILIS_TRAJETS")
    analyser(arguments.trajets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
