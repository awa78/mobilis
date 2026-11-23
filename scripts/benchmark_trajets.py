import csv
import gzip
import tempfile
import time
import tracemalloc
from pathlib import Path

from mobilis.trajets import analyser_trajets, pipeline_trajets

SOURCE = Path("data/donnees/trajets_2026-08_2026-10.csv.gz")
FACTEUR = 100


def creer_fichier_x100(source: Path, destination: Path) -> int:
    """Crée un fichier gzip avec 100 répétitions et des IDs distincts."""
    nombre_lignes = 0

    with gzip.open(source, "rt", encoding="utf-8", newline="") as fichier_source:
        lecteur = csv.DictReader(fichier_source)
        champs = lecteur.fieldnames

        if champs is None:
            raise ValueError("Le fichier source ne contient pas d'en-tête.")

        with gzip.open(
            destination, "wt", encoding="utf-8", newline=""
        ) as fichier_destination:
            ecrivain = csv.DictWriter(fichier_destination, fieldnames=champs)
            ecrivain.writeheader()

            lignes = list(lecteur)

            for repetition in range(FACTEUR):
                for ligne_originale in lignes:
                    ligne = ligne_originale.copy()

                    identifiant = ligne.get("trajet_id", "")
                    if identifiant:
                        ligne["trajet_id"] = f"{identifiant}-x{repetition}"

                    ecrivain.writerow(ligne)
                    nombre_lignes += 1

    return nombre_lignes


def benchmark() -> None:
    with tempfile.NamedTemporaryFile(
        suffix=".csv.gz", delete=False
    ) as fichier_temporaire:
        chemin_temporaire = Path(fichier_temporaire.name)

    try:
        print("========== CRÉATION DU FICHIER 100× ==========")
        debut_creation = time.perf_counter()

        nombre_lignes = creer_fichier_x100(SOURCE, chemin_temporaire)

        temps_creation = time.perf_counter() - debut_creation

        print(f"Lignes générées : {nombre_lignes:,}")
        print(f"Temps de création : {temps_creation:.2f} secondes")
        print(f"Taille compressée : {chemin_temporaire.stat().st_size / 1024 / 1024:.2f} Mo")

        print("\n========== BENCHMARK PIPELINE ==========")
        tracemalloc.start()
        debut_analyse = time.perf_counter()

        statistiques = analyser_trajets(
            pipeline_trajets(chemin_temporaire)
        )

        temps_analyse = time.perf_counter() - debut_analyse
        memoire_actuelle, pic_memoire = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        print(f"Trajets analysés : {statistiques['total_trajets']:,}")
        print(f"Temps d'analyse : {temps_analyse:.2f} secondes")
        print(f"Mémoire actuelle : {memoire_actuelle / 1024 / 1024:.2f} Mo")
        print(f"Pic mémoire : {pic_memoire / 1024 / 1024:.2f} Mo")

    finally:
        chemin_temporaire.unlink(missing_ok=True)
        print("\nFichier temporaire supprimé.")


if __name__ == "__main__":
    benchmark()
