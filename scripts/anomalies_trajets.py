
from collections import Counter
from pathlib import Path

from mobilis.trajets import convertir_date, lire_trajets

CHEMIN = Path("data/donnees/trajets_2026-08_2026-10.csv.gz")


def analyser_anomalies() -> None:
    anomalies: Counter[str] = Counter()
    identifiants: set[str] = set()
    doublons = 0

    for trajet in lire_trajets(CHEMIN):
        trajet_id = trajet.get("trajet_id", "").strip()

        if not trajet.get("abonne_id", "").strip():
            anomalies["abonne_id manquant"] += 1

        if not trajet.get("fin", "").strip():
            anomalies["date de fin manquante"] += 1

        if not trajet.get("station_arrivee", "").strip():
            anomalies["station d'arrivee manquante"] += 1

        distance = trajet.get("distance_m", "").strip()

        try:
            valeur_distance = float(distance)
            if valeur_distance < 0:
                anomalies["distance negative"] += 1
        except ValueError:
            anomalies["distance absente ou invalide"] += 1

        if trajet_id:
            if trajet_id in identifiants:
                doublons += 1
            else:
                identifiants.add(trajet_id)

        if convertir_date(trajet.get("debut", "")) is None:
            anomalies["date de debut invalide"] += 1

        if trajet.get("fin", "").strip() and convertir_date(trajet["fin"]) is None:
            anomalies["date de fin invalide"] += 1

    anomalies["trajets avec identifiant duplique"] = doublons

    print("\n========== JOURNAL DES ANOMALIES ==========")
    for nom, nombre in anomalies.most_common():
        print(f"{nom} : {nombre:,}")

    print("\n========== TOTAL ==========")
    print(f"Anomalies comptabilisees : {sum(anomalies.values()):,}")


if __name__ == "__main__":
    analyser_anomalies()
