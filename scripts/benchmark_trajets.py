"""Génère un fichier 100× et mesure le pic mémoire du pipeline."""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import tempfile
import time
import tracemalloc
from collections import Counter
from pathlib import Path

from mobilis.trajets import analyser_trajets, pipeline_trajets

FACTEUR = 100
_NOM_TRAJETS = "trajets_2026-08_2026-10.csv.gz"


def creer_fichier_x100(source: Path, destination: Path) -> int:
    """Crée un fichier gzip 100× sans charger les lignes source en mémoire."""
    nombre_lignes = 0
    with gzip.open(source, "rt", encoding="utf-8", newline="") as premier_fichier:
        champs = csv.DictReader(premier_fichier).fieldnames
    if champs is None:
        raise ValueError("Le fichier source ne contient pas d'en-tête")

    with gzip.open(destination, "wt", encoding="utf-8", newline="") as fichier_destination:
        ecrivain = csv.DictWriter(fichier_destination, fieldnames=champs)
        ecrivain.writeheader()

        for repetition in range(FACTEUR):
            with gzip.open(source, "rt", encoding="utf-8", newline="") as fichier_source:
                lecteur = csv.DictReader(fichier_source)
                if lecteur.fieldnames != champs:
                    raise ValueError("L'en-tête du fichier source a changé")
                for ligne_originale in lecteur:
                    ligne = ligne_originale.copy()
                    identifiant = ligne.get("trajet_id", "")
                    if identifiant:
                        ligne["trajet_id"] = f"{identifiant}-x{repetition}"
                    ecrivain.writerow(ligne)
                    nombre_lignes += 1

    return nombre_lignes


def _chemin_par_defaut() -> Path | None:
    chemin = os.environ.get("MOBILIS_TRAJETS")
    if chemin:
        return Path(chemin)
    repertoire = os.environ.get("MOBILIS_DATA_DIR")
    if repertoire:
        return Path(repertoire) / _NOM_TRAJETS
    return None


def benchmark(source: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        print("========== CRÉATION DU FICHIER 100× ==========")
        creation_start = time.perf_counter()
        line_count = creer_fichier_x100(source, temporary_path)
        creation_seconds = time.perf_counter() - creation_start
        print(f"Lignes générées : {line_count:,}")
        print(f"Temps de création : {creation_seconds:.2f} secondes")
        print(f"Taille compressée : {temporary_path.stat().st_size / 1024 / 1024:.2f} Mo")

        anomalies: Counter[str] = Counter()
        print("\n========== BENCHMARK PIPELINE ==========")
        tracemalloc.start()
        analysis_start = time.perf_counter()
        statistics = analyser_trajets(
            pipeline_trajets(temporary_path, anomalies=anomalies), anomalies=anomalies
        )
        analysis_seconds = time.perf_counter() - analysis_start
        current_memory, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        print(f"Trajets uniques analysés : {statistics['total_trajets']:,}")
        print(f"Anomalies comptées : {sum(anomalies.values()):,}")
        print(f"Temps d'analyse : {analysis_seconds:.2f} secondes")
        print(f"Mémoire actuelle : {current_memory / 1024 / 1024:.2f} Mo")
        print(f"Pic mémoire Python : {peak_memory / 1024 / 1024:.2f} Mo")
    finally:
        tracemalloc.stop()
        temporary_path.unlink(missing_ok=True)
        print("\nFichier temporaire supprimé.")


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
    benchmark(arguments.trajets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
