"""Compte les anomalies des trajets sans charger le fichier en mémoire."""

from __future__ import annotations

import argparse
import os
from collections import Counter
from pathlib import Path

from mobilis.trajets import convertir_trajets, dedoublonner_trajets, lire_trajets

_NOM_TRAJETS = "trajets_2026-08_2026-10.csv.gz"


def _chemin_par_defaut() -> Path | None:
    chemin = os.environ.get("MOBILIS_TRAJETS")
    if chemin:
        return Path(chemin)
    repertoire = os.environ.get("MOBILIS_DATA_DIR")
    if repertoire:
        return Path(repertoire) / _NOM_TRAJETS
    return None


def analyser_anomalies(chemin: Path) -> Counter[str]:
    """Retourne un compte d'anomalies en un seul parcours du fichier."""
    anomalies: Counter[str] = Counter()
    sans_doublons = dedoublonner_trajets(lire_trajets(chemin), anomalies)
    trajets = convertir_trajets(sans_doublons, anomalies)

    for trajet in trajets:
        if not str(trajet.get("station_depart", "") or "").strip():
            anomalies["station_depart_manquante"] += 1
        if not str(trajet.get("station_arrivee", "") or "").strip():
            anomalies["station_arrivee_manquante"] += 1

        distance = trajet.get("distance_m")
        try:
            distance_m = int(str(distance))
            if distance_m < 0:
                anomalies["distance_negative"] += 1
        except ValueError:
            anomalies["distance_absente_ou_invalide"] += 1

        type_velo = trajet.get("type_velo")
        if type_velo not in {"mecanique", "electrique"}:
            anomalies["type_velo_inconnu"] += 1

    return anomalies


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

    anomalies = analyser_anomalies(arguments.trajets)
    print("\n========== JOURNAL DES ANOMALIES ==========")
    for nom, nombre in anomalies.most_common():
        print(f"{nom} : {nombre:,}")
    print("\n========== TOTAL ==========")
    print(f"Anomalies comptabilisées : {sum(anomalies.values()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
