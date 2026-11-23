"""Lecture en flux et conversion des dates de trajet Mobilis."""

from __future__ import annotations

import csv
import gzip
from collections.abc import Iterable, Iterator, MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def lire_trajets(chemin: str | Path) -> Iterator[dict[str, str]]:
    """Lit un CSV gzip en flux, sans charger toutes les lignes en mémoire."""
    with gzip.open(chemin, mode="rt", encoding="utf-8", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        yield from lecteur


def convertir_date(valeur: str) -> datetime | None:
    """Convertit les formats ISO et JJ/MM/AAAA des bornes en instant UTC.

    Une date ISO contenant déjà son décalage conserve cet instant. Une date
    sans fuseau est interprétée dans ``Europe/Paris``. Une valeur vide donne
    ``None`` ; une date non vide mais invalide lève ``ValueError``.
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
        try:
            paris = ZoneInfo("Europe/Paris")
        except ZoneInfoNotFoundError as error:
            raise RuntimeError(
                "La base IANA des fuseaux horaires est absente ; installez le paquet tzdata"
            ) from error
        instant = instant.replace(tzinfo=paris)

    return instant.astimezone(UTC)


def convertir_trajets(
    trajets: Iterable[dict[str, str]],
    anomalies: MutableMapping[str, int] | None = None,
) -> Iterator[dict[str, str | datetime | None]]:
    """Convertit progressivement les dates et compte les dates invalides.

    Les lignes dont une date est invalide sont conservées avec ``None`` pour
    cette date afin que le traitement du reste du fichier puisse continuer.
    Le compteur facultatif reçoit le nombre de valeurs invalides par champ.
    """
    for trajet in trajets:
        trajet_converti: dict[str, str | datetime | None] = {}
        for cle, valeur in trajet.items():
            trajet_converti[cle] = valeur

        for champ in ("debut", "fin"):
            valeur = trajet.get(champ, "")
            try:
                trajet_converti[champ] = convertir_date(valeur)
            except ValueError:
                trajet_converti[champ] = None
                if anomalies is not None:
                    cle_anomalie = f"date_invalide:{champ}"
                    anomalies[cle_anomalie] = anomalies.get(cle_anomalie, 0) + 1

        yield trajet_converti
