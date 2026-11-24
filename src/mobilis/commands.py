"""Commandes de frequentation et de facturation Mobilis."""

from __future__ import annotations

import argparse
import os
import tracemalloc
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from mobilis.facturation import Facturation, resumer_par_mois
from mobilis.trajets import analyser_trajets, pipeline_trajets

NOM_TRAJETS = "trajets_2026-08_2026-10.csv.gz"


def _default_path(variable: str, filename: str) -> Path | None:
    explicit = os.environ.get(variable)
    if explicit:
        return Path(explicit)
    data_directory = os.environ.get("MOBILIS_DATA_DIR")
    if data_directory:
        return Path(data_directory) / filename
    return None


def _add_path(
    parser: argparse.ArgumentParser,
    option: str,
    variable: str,
    filename: str,
) -> None:
    parser.add_argument(
        option,
        type=Path,
        default=_default_path(variable, filename),
        help=f"chemin du fichier (ou {variable} / MOBILIS_DATA_DIR)",
    )


def add_report_commands(commands: Any) -> None:
    """Ajoute les sous-commandes de frequentation et de facturation."""
    frequentation = commands.add_parser("frequentation", help="analyse les trajets et les stations")
    _add_path(frequentation, "--trajets", "MOBILIS_TRAJETS", NOM_TRAJETS)

    facturation = commands.add_parser(
        "facturation", help="calcule les recettes mensuelles et l'effet du tarif d'octobre"
    )
    _add_path(facturation, "--trajets", "MOBILIS_TRAJETS", NOM_TRAJETS)
    _add_path(facturation, "--tarifs", "MOBILIS_TARIFS", "tarifs.json")
    _add_path(facturation, "--abonnes", "MOBILIS_ABONNES", "abonnes.jsonl")
    _add_path(facturation, "--stations", "MOBILIS_STATIONS", "stations.csv")


def _required_path(parser: argparse.ArgumentParser, value: Path | None, option: str) -> Path:
    if value is None:
        parser.error(f"indiquez {option} CHEMIN ou definissez MOBILIS_DATA_DIR")
    return value


def run_frequentation(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    trajet_path = _required_path(parser, args.trajets, "--trajets")
    anomalies: Counter[str] = Counter()
    tracemalloc.start()
    try:
        statistiques = analyser_trajets(
            pipeline_trajets(trajet_path, anomalies=anomalies), anomalies=anomalies
        )
        _, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    total = cast(int, statistiques["total_trajets"])
    distance = cast(int, statistiques["distance_totale_m"])
    profil_semaine = cast(dict[int, int], statistiques["profil_semaine"])
    profil_weekend = cast(dict[int, int], statistiques["profil_week_end"])
    stations_vides = cast(list[tuple[str, int]], statistiques["stations_vides_matin"])
    stations_pleines = cast(list[tuple[str, int]], statistiques["stations_pleines_soir"])

    print(f"Trajets uniques : {total:,}")
    print(f"Distance totale : {distance:,} m")
    print(f"Pic memoire Python : {peak_memory / 1024 / 1024:.2f} Mo")
    print(f"Anomalies comptees : {sum(anomalies.values()):,} {dict(anomalies)}")
    for title, profile in (
        ("Semaine", profil_semaine),
        ("Week-end", profil_weekend),
    ):
        print(f"\n{title} (heure locale de Paris) :")
        for hour, count in sorted(profile.items()):
            print(f"  {hour:02d} h : {count:,}")
    print("\nStations qui se vident le matin (flux net) :")
    for code, count in stations_vides[:10]:
        print(f"  {code} : +{count:,}")
    print("Stations qui se remplissent le soir (flux net) :")
    for code, count in stations_pleines[:10]:
        print(f"  {code} : +{count:,}")
    return 0


def run_facturation(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    trajet_path = _required_path(parser, args.trajets, "--trajets")
    tarifs_path = _required_path(parser, args.tarifs, "--tarifs")
    abonnes_path = _required_path(parser, args.abonnes, "--abonnes")
    stations_path = _required_path(parser, args.stations, "--stations")
    moteur = Facturation.depuis_fichiers(tarifs_path, abonnes_path, stations_path)

    anomalies_trajets: Counter[str] = Counter()
    bilans = resumer_par_mois(
        moteur.iter_facturer_trajets(pipeline_trajets(trajet_path, anomalies=anomalies_trajets))
    )
    for month, bilan in bilans.items():
        print(f"\n{month} - recettes : {bilan.total:,.2f} EUR")
        for formula, amount in bilan.recettes_par_formule.items():
            print(f"  {formula} : {amount:,.2f} EUR")

    october = "2026-10"
    if october in bilans:
        ancien_moteur = moteur.avec_grille_precedente(date(2026, 10, 1))
        ancien_bilan = resumer_par_mois(
            ancien_moteur.iter_facturer_trajets(pipeline_trajets(trajet_path))
        )[october]
        reel = bilans[october]
        print(
            f"\nEffet du tarif d'octobre sur les memes trajets : "
            f"{reel.total - ancien_bilan.total:+,.2f} EUR "
            f"(ancienne grille {ancien_bilan.total:,.2f}, nouvelle grille {reel.total:,.2f})"
        )
        formulas = set(reel.recettes_par_formule) | set(ancien_bilan.recettes_par_formule)
        for formula in sorted(formulas):
            difference = reel.recettes_par_formule.get(
                formula, Decimal("0.00")
            ) - ancien_bilan.recettes_par_formule.get(formula, Decimal("0.00"))
            print(f"  {formula} : {difference:+,.2f} EUR")

    print(f"\nLignes d'abonnement malformees : {dict(moteur.anomalies_import)}")
    print(f"Anomalies des trajets : {dict(anomalies_trajets)}")
    return 0
