import tracemalloc
from pathlib import Path
from typing import cast

from mobilis.trajets import analyser_trajets, pipeline_trajets

CHEMIN = Path("data/donnees/trajets_2026-08_2026-10.csv.gz")


def main() -> None:
    tracemalloc.start()

    statistiques = analyser_trajets(pipeline_trajets(CHEMIN))

    total_trajets = cast(int, statistiques["total_trajets"])
    distance_totale = cast(int, statistiques["distance_totale_m"])
    departs = cast(dict[str, int], statistiques["departs_par_station"])
    arrivees = cast(dict[str, int], statistiques["arrivees_par_station"])
    profil_horaire = cast(dict[int, int], statistiques["profil_horaire"])
    stations_vides = cast(
        list[tuple[str, int]], statistiques["stations_vides_matin"]
    )
    stations_pleines = cast(
        list[tuple[str, int]], statistiques["stations_pleines_soir"]
    )

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("\n========== BILAN GLOBAL ==========")
    print(f"Nombre de trajets : {total_trajets:,}")
    print(f"Distance totale : {distance_totale:,} m")
    print(f"Distance totale : {distance_totale / 1000:,.2f} km")
    print(f"Mémoire actuelle : {current / 1024 / 1024:.2f} Mo")
    print(f"Pic mémoire : {peak / 1024 / 1024:.2f} Mo")

    print("\n========== TOP 10 DÉPARTS ==========")
    for station, nombre in sorted(
        departs.items(), key=lambda item: item[1], reverse=True
    )[:10]:
        print(f"{station} : {nombre:,}")

    print("\n========== TOP 10 ARRIVÉES ==========")
    for station, nombre in sorted(
        arrivees.items(), key=lambda item: item[1], reverse=True
    )[:10]:
        print(f"{station} : {nombre:,}")

    print("\n========== PROFIL HORAIRE ==========")
    for heure, nombre in sorted(profil_horaire.items()):
        print(f"{heure:02d}h : {nombre:,}")

    print("\n========== DÉPARTS MATIN ==========")
    for station, nombre in stations_vides[:10]:
        print(f"{station} : {nombre:,}")

    print("\n========== ARRIVÉES SOIR ==========")
    for station, nombre in stations_pleines[:10]:
        print(f"{station} : {nombre:,}")


if __name__ == "__main__":
    main()
