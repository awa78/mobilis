"""Lecture en flux, normalisation et agrégation des trajets Mobilis."""

from __future__ import annotations

import csv
import gzip
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

T = TypeVar("T")
Trajet = dict[str, str | datetime | None]
_ZONE_PARIS = "Europe/Paris"


def lire_trajets(chemin: str | Path) -> Iterator[dict[str, str]]:
    """Lit un fichier CSV gzip progressivement, une ligne à la fois."""
    with gzip.open(chemin, mode="rt", encoding="utf-8", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        yield from lecteur


def _fuseau_paris() -> ZoneInfo:
    try:
        return ZoneInfo(_ZONE_PARIS)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            "Base des fuseaux absente ; installez les dépendances du projet, dont tzdata"
        ) from error


def convertir_date(valeur: str) -> datetime | None:
    """Convertit une date ISO ou JJ/MM/AAAA en instant UTC.

    Les dates sans fuseau sont interprétées en heure locale Europe/Paris.
    Une valeur vide donne ``None``. Une date non vide invalide lève ``ValueError``.
    """
    if not valeur.strip():
        return None

    try:
        instant = datetime.fromisoformat(valeur)
    except ValueError:
        try:
            instant = datetime.strptime(valeur, "%d/%m/%Y %H:%M:%S")
        except ValueError as error:
            raise ValueError(f"Date de trajet invalide : {valeur!r}") from error

    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=_fuseau_paris())
    return instant.astimezone(UTC)


def convertir_trajets(
    trajets: Iterable[dict[str, str]],
    anomalies: MutableMapping[str, int] | None = None,
) -> Iterator[Trajet]:
    """Convertit progressivement les dates et compte les valeurs invalides.

    Une date non vide mais invalide devient ``None`` dans la ligne normalisée,
    et son champ est incrémenté dans le compteur fourni. Le fichier continue.
    """
    for trajet in trajets:
        trajet_converti: Trajet = dict(trajet)
        for champ in ("debut", "fin"):
            valeur = trajet.get(champ, "")
            if not valeur.strip():
                trajet_converti[champ] = None
                if anomalies is not None:
                    cle = f"date_manquante:{champ}"
                    anomalies[cle] = anomalies.get(cle, 0) + 1
                continue
            try:
                trajet_converti[champ] = convertir_date(valeur)
            except ValueError:
                trajet_converti[champ] = None
                if anomalies is not None:
                    cle = f"date_invalide:{champ}"
                    anomalies[cle] = anomalies.get(cle, 0) + 1
        yield trajet_converti


def dedoublonner_trajets(
    trajets: Iterable[dict[str, T]],
    anomalies: MutableMapping[str, int] | None = None,
) -> Iterator[dict[str, T]]:
    """Élimine les trajets répétés avec un index SQLite temporaire sur disque.

    L'index évite de conserver les 155 000 identifiants (ou davantage) dans un
    set Python. Sa mémoire cache est plafonnée ; les lignes restent en flux.
    """
    with tempfile.TemporaryDirectory(prefix="mobilis-dedup-") as temporary_directory:
        database = Path(temporary_directory) / "identifiants.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("PRAGMA cache_size=-4096")
            connection.execute("CREATE TABLE identifiants (valeur TEXT PRIMARY KEY)")
            connection.execute("BEGIN")

            for nombre, trajet in enumerate(trajets, start=1):
                identifiant = trajet.get("trajet_id")
                if not isinstance(identifiant, str) or not identifiant.strip():
                    if anomalies is not None:
                        anomalies["identifiant_absent"] = anomalies.get("identifiant_absent", 0) + 1
                    yield trajet
                    continue

                normalized_id = identifiant.strip()
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO identifiants(valeur) VALUES (?)",
                    (normalized_id,),
                )
                if cursor.rowcount == 1:
                    yield trajet
                elif anomalies is not None:
                    anomalies["trajet_id_duplique"] = anomalies.get("trajet_id_duplique", 0) + 1

                if nombre % 10_000 == 0:
                    connection.commit()
                    connection.execute("BEGIN")

            connection.commit()
        finally:
            connection.close()


def filtrer_trajets(
    trajets: Iterable[dict[str, T]],
    predicate: Callable[[dict[str, T]], bool],
) -> Iterator[dict[str, T]]:
    """Filtre les trajets progressivement à l'aide d'un prédicat."""
    for trajet in trajets:
        if predicate(trajet):
            yield trajet


def pipeline_trajets(
    chemin: str | Path,
    predicate: Callable[[Trajet], bool] | None = None,
    anomalies: MutableMapping[str, int] | None = None,
) -> Iterator[Trajet]:
    """Compose lecture gzip, conversion, dédoublonnage et filtre optionnel."""
    trajets_convertis = convertir_trajets(lire_trajets(chemin), anomalies)
    trajets_uniques = dedoublonner_trajets(trajets_convertis, anomalies)
    if predicate is None:
        yield from trajets_uniques
    else:
        yield from filtrer_trajets(trajets_uniques, predicate)


def analyser_trajets(
    trajets: Iterable[Mapping[str, object]],
    heure_matin_debut: int = 6,
    heure_matin_fin: int = 10,
    heure_soir_debut: int = 16,
    heure_soir_fin: int = 20,
    anomalies: MutableMapping[str, int] | None = None,
) -> dict[str, object]:
    """Agrège les trajets en un passage, avec les heures locales de Paris.

    Les stations du matin sont classées par sorties nettes (vidage). Celles du
    soir sont classées par entrées nettes (remplissage).
    """
    if not (0 <= heure_matin_debut < heure_matin_fin <= 24):
        raise ValueError("Fenêtre du matin invalide")
    if not (0 <= heure_soir_debut < heure_soir_fin <= 24):
        raise ValueError("Fenêtre du soir invalide")

    fuseau = _fuseau_paris()
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
            debut_local = (
                debut.replace(tzinfo=fuseau) if debut.tzinfo is None else debut.astimezone(fuseau)
            )
            heure = debut_local.hour
            heures[heure] += 1
            if debut_local.weekday() < 5:
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
                if anomalies is not None:
                    anomalies["distance_invalide"] = anomalies.get("distance_invalide", 0) + 1
        elif isinstance(distance, int):
            distance_totale += distance

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
        (
            (station, departs_matin[station] - arrivees_matin[station])
            for station in set(departs_matin) | set(arrivees_matin)
            if departs_matin[station] > arrivees_matin[station]
        ),
        key=lambda item: (-item[1], item[0]),
    )
    stations_pleines_soir = sorted(
        (
            (station, arrivees_soir[station] - departs_soir[station])
            for station in set(departs_soir) | set(arrivees_soir)
            if arrivees_soir[station] > departs_soir[station]
        ),
        key=lambda item: (-item[1], item[0]),
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
