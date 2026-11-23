
import csv
import gzip
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

T = TypeVar("T")

Trajet = dict[str, str | datetime | None]


def lire_trajets(chemin: Path) -> Iterator[dict[str, str]]:
    """Lit un fichier CSV gzip progressivement."""
    with gzip.open(chemin, mode="rt", encoding="utf-8", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        yield from lecteur


def convertir_date(valeur: str) -> datetime | None:
    """Convertit une date Mobilis en instant UTC."""
    if not valeur:
        return None

    try:
        date = datetime.fromisoformat(valeur)
    except ValueError:
        date = datetime.strptime(valeur, "%d/%m/%Y %H:%M:%S")

    if date.tzinfo is None:
        date = date.replace(tzinfo=ZoneInfo("Europe/Paris"))

    return date.astimezone(UTC)


def convertir_trajets(
    trajets: Iterator[dict[str, str]],
) -> Iterator[Trajet]:
    """Convertit les dates des trajets sans chargement global."""
    for trajet in trajets:
        trajet_converti: Trajet = dict(trajet)
        trajet_converti["debut"] = convertir_date(trajet["debut"])
        trajet_converti["fin"] = convertir_date(trajet["fin"])
        yield trajet_converti


def dedoublonner_trajets(
    trajets: Iterable[dict[str, T]],
) -> Iterator[dict[str, T]]:
    """Élimine les trajets déjà rencontrés grâce à trajet_id."""
    identifiants: set[str] = set()

    for trajet in trajets:
        identifiant = trajet.get("trajet_id")

        if not isinstance(identifiant, str) or not identifiant:
            yield trajet
            continue

        if identifiant not in identifiants:
            identifiants.add(identifiant)
            yield trajet


def filtrer_trajets(
    trajets: Iterable[dict[str, T]],
    predicate: Callable[[dict[str, T]], bool],
) -> Iterator[dict[str, T]]:
    """Filtre les trajets progressivement."""
    for trajet in trajets:
        if predicate(trajet):
            yield trajet


def pipeline_trajets(
    chemin: Path,
    predicate: Callable[[Trajet], bool] | None = None,
) -> Iterator[Trajet]:
    """Pipeline complet de traitement des trajets Mobilis."""
    trajets_bruts = lire_trajets(chemin)
    trajets_convertis = convertir_trajets(trajets_bruts)
    trajets_dedoublonnes = dedoublonner_trajets(trajets_convertis)

    if predicate is not None:
        trajets_final = filtrer_trajets(
            trajets_dedoublonnes,
            predicate,
        )
    else:
        trajets_final = trajets_dedoublonnes

    yield from trajets_final


def analyser_trajets(
    trajets: Iterable[Mapping[str, object]],
    heure_matin_debut: int = 6,
    heure_matin_fin: int = 10,
    heure_soir_debut: int = 16,
    heure_soir_fin: int = 20,
) -> dict[str, object]:
    """Analyse les trajets en un seul passage et produit des statistiques."""

    departs: Counter[str] = Counter()
    arrivees: Counter[str] = Counter()
    heures: Counter[int] = Counter()
    semaine: Counter[int] = Counter()
    week_end: Counter[int] = Counter()
    departs_matin: Counter[str] = Counter()
    arrivees_matin: Counter[str] = Counter()
    departs_soir: Counter[str] = Counter()
    arrivees_soir: Counter[str] = Counter()

    total_trajets = 0
    distance_totale = 0

    for trajet in trajets:
        total_trajets += 1

        station_depart = trajet.get("station_depart")
        station_arrivee = trajet.get("station_arrivee")
        debut = trajet.get("debut")
        distance = trajet.get("distance_m")

        if isinstance(station_depart, str) and station_depart:
            departs[station_depart] += 1

        if isinstance(station_arrivee, str) and station_arrivee:
            arrivees[station_arrivee] += 1

        if isinstance(debut, datetime):
            heure = debut.hour
            heures[heure] += 1

            if debut.weekday() < 5:
                semaine[heure] += 1
            else:
                week_end[heure] += 1

            if heure_matin_debut <= heure < heure_matin_fin:
                if isinstance(station_depart, str) and station_depart:
                    departs_matin[station_depart] += 1

                if isinstance(station_arrivee, str) and station_arrivee:
                    arrivees_matin[station_arrivee] += 1

            if heure_soir_debut <= heure < heure_soir_fin:
                if isinstance(station_depart, str) and station_depart:
                    departs_soir[station_depart] += 1

                if isinstance(station_arrivee, str) and station_arrivee:
                    arrivees_soir[station_arrivee] += 1

        if isinstance(distance, str):
            try:
                distance_totale += int(distance)
            except ValueError:
                pass

    stations = set(departs) | set(arrivees)

    bilan_stations = {
        station: {
            "departs": departs[station],
            "arrivees": arrivees[station],
            "balance": arrivees[station] - departs[station],
        }
        for station in stations
    }

    stations_vides_matin = sorted(
        departs_matin.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    stations_pleines_soir = sorted(
        arrivees_soir.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "total_trajets": total_trajets,
        "distance_totale_m": distance_totale,
        "departs_par_station": dict(departs),
        "arrivees_par_station": dict(arrivees),
        "bilan_stations": bilan_stations,
        "profil_horaire": dict(sorted(heures.items())),
        "profil_semaine": dict(sorted(semaine.items())),
        "profil_week_end": dict(sorted(week_end.items())),
        "departs_matin": dict(departs_matin),
        "arrivees_matin": dict(arrivees_matin),
        "departs_soir": dict(departs_soir),
        "arrivees_soir": dict(arrivees_soir),
        "stations_vides_matin": stations_vides_matin,
        "stations_pleines_soir": stations_pleines_soir,
    }