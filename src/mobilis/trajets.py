import csv
import gzip
from collections.abc import Iterator
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path


def lire_trajets(chemin: Path) -> Iterator[dict[str, str]]:
    """Lit un fichier CSV de trajets compressé en gzip ligne par ligne."""
    with gzip.open(chemin, mode="rt", encoding="utf-8", newline="") as fichier:
        lecteur = csv.DictReader(fichier)

        for ligne in lecteur:
            yield ligne

def convertir_date(valeur: str) -> datetime | None:
    """Convertit une date Mobilis en instant UTC.

    Les dates sans fuseau horaire sont interprétées comme des heures locales
    Europe/Paris.
    """
    if not valeur:
        return None

    try:
        date = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        date = datetime.strptime(valeur, "%d/%m/%Y %H:%M:%S")

    if date.tzinfo is None:
        date = date.replace(tzinfo=ZoneInfo("Europe/Paris"))

    return date.astimezone(timezone.utc)

def convertir_trajets(
    trajets: Iterator[dict[str, str]],
) -> Iterator[dict[str, str | datetime | None]]:
    """Convertit progressivement les dates des trajets."""
    for trajet in trajets:
        trajet_converti = trajet.copy()

        trajet_converti["debut"] = convertir_date(trajet["debut"])
        trajet_converti["fin"] = convertir_date(trajet["fin"])

        yield trajet_converti