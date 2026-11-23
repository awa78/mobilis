"""Lecture et validation du référentiel des stations Mobilis."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import cast


class StationStatus(str, Enum):
    """Statut normalisé d'une station."""

    ACTIVE = "en_service"
    OUT_OF_SERVICE = "hors_service"
    CLOSED = "fermee"
    UNKNOWN = "inconnu"


@dataclass(frozen=True, slots=True)
class Station:
    """Station normalisée. Les données indisponibles sont représentées par ``None``."""

    code: str
    name: str
    municipality: str
    capacity: int | None
    latitude: float | None
    longitude: float | None
    status: StationStatus
    commissioned_on: date | None

    def __post_init__(self) -> None:
        """Vérifie les invariants structurels de la station."""
        if not self.code.strip():
            raise ValueError("Le code station ne peut pas être vide")
        if not self.name.strip():
            raise ValueError("Le nom de la station ne peut pas être vide")
        if not self.municipality.strip():
            raise ValueError("La commune ne peut pas être vide")
        if self.capacity is not None and self.capacity <= 0:
            raise ValueError("La capacité doit être strictement positive")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude et longitude doivent être présentes ensemble")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("La latitude doit être comprise entre -90 et 90")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("La longitude doit être comprise entre -180 et 180")

    @property
    def is_exploitable(self) -> bool:
        """Indique si la station est active et assez renseignée pour l'analyse."""
        return (
            self.status is StationStatus.ACTIVE
            and self.capacity is not None
            and self.latitude is not None
            and self.longitude is not None
        )


@dataclass(frozen=True, slots=True)
class StationAnomaly:
    """Anomalie relevée dans une ligne du CSV, avec sa ligne source."""

    line_number: int
    code: str | None
    field: str
    value: str
    message: str


@dataclass(frozen=True, slots=True)
class StationReport:
    """Stations lisibles et anomalies rencontrées pendant le chargement."""

    rows_read: int
    stations: tuple[Station, ...]
    anomalies: tuple[StationAnomaly, ...]
    duplicate_codes: tuple[str, ...]

    @property
    def exploitable_stations(self) -> tuple[Station, ...]:
        """Renvoie les stations actives disposant d'une capacité et de coordonnées."""
        return tuple(station for station in self.stations if station.is_exploitable)

    @property
    def codes_seen(self) -> tuple[str, ...]:
        """Tous les codes non vides du source, y compris les codes ambigus."""
        codes = {station.code for station in self.stations} | set(self.duplicate_codes)
        return tuple(sorted(codes))


class StationFileError(ValueError):
    """Erreur de structure du fichier empêchant toute lecture des stations."""


_REQUIRED_COLUMNS = (
    "Code station",
    "Nom",
    "Commune",
    "Capacité",
    "Latitude",
    "Longitude",
    "Statut",
    "Mise en service",
)


def _cell(row: dict[str, str | list[str] | None], column: str) -> str:
    value = row.get(column)
    return value.strip() if isinstance(value, str) else ""


def _parse_decimal(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_date(value: str) -> date | None:
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _parse_status(value: str) -> StationStatus:
    normalized = value.strip().casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "en_service": StationStatus.ACTIVE,
        "hors_service": StationStatus.OUT_OF_SERVICE,
        "hs": StationStatus.OUT_OF_SERVICE,
        "fermee": StationStatus.CLOSED,
        "fermée": StationStatus.CLOSED,
    }
    return aliases.get(normalized, StationStatus.UNKNOWN)


def load_stations(path: str | Path) -> StationReport:
    """Charge le CSV cp1252 et accumule les anomalies sans interrompre l'analyse.

    Les codes apparaissant plusieurs fois sont ambigus : toutes leurs lignes sont
    signalées et retirées du référentiel fiable. Les stations incomplètes restent
    dans le rapport, mais ne sont pas comptées comme exploitables.
    """
    source = Path(path)
    with source.open(encoding="cp1252", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise StationFileError("Le fichier des stations est vide")
        missing_columns = [column for column in _REQUIRED_COLUMNS if column not in fieldnames]
        if missing_columns:
            raise StationFileError("Colonnes absentes : " + ", ".join(missing_columns))

        raw_rows: list[tuple[int, dict[str, str | list[str] | None]]] = []
        duplicate_lines: dict[str, list[int]] = {}
        first_line_by_code: dict[str, int] = {}
        for row in reader:
            line_number = reader.line_num
            typed_row = cast(dict[str, str | list[str] | None], row)
            raw_rows.append((line_number, typed_row))
            source_code = _cell(typed_row, "Code station")
            if source_code:
                if source_code in first_line_by_code:
                    duplicate_lines.setdefault(
                        source_code, [first_line_by_code[source_code]]
                    ).append(line_number)
                else:
                    first_line_by_code[source_code] = line_number

    anomalies: list[StationAnomaly] = []
    parsed_stations: list[Station] = []
    duplicate_codes = tuple(sorted(duplicate_lines))
    duplicate_set = set(duplicate_codes)

    for duplicate_code, line_numbers in duplicate_lines.items():
        for line_number in line_numbers:
            anomalies.append(
                StationAnomaly(
                    line_number=line_number,
                    code=duplicate_code,
                    field="Code station",
                    value=duplicate_code,
                    message=(
                        f"Code dupliqué (lignes {', '.join(map(str, line_numbers))}); "
                        "toutes les lignes sont exclues du référentiel fiable"
                    ),
                )
            )

    for line_number, row in raw_rows:
        code = _cell(row, "Code station") or None
        name = _cell(row, "Nom")
        municipality = _cell(row, "Commune")
        row_is_usable = True

        for column, value in (("Code station", code), ("Nom", name), ("Commune", municipality)):
            if not value:
                anomalies.append(
                    StationAnomaly(line_number, code, column, "", "Champ obligatoire manquant")
                )
                row_is_usable = False

        capacity_text = _cell(row, "Capacité")
        try:
            capacity = int(capacity_text)
            if capacity <= 0:
                raise ValueError
        except ValueError:
            capacity = None
            anomalies.append(
                StationAnomaly(
                    line_number, code, "Capacité", capacity_text, "Capacité inconnue ou invalide"
                )
            )

        latitude_text = _cell(row, "Latitude")
        longitude_text = _cell(row, "Longitude")
        latitude = _parse_decimal(latitude_text)
        longitude = _parse_decimal(longitude_text)
        if not latitude_text and not longitude_text:
            anomalies.append(
                StationAnomaly(
                    line_number, code, "Coordonnées", "", "Latitude et longitude manquantes"
                )
            )
        elif latitude is None or longitude is None:
            anomalies.append(
                StationAnomaly(
                    line_number,
                    code,
                    "Coordonnées",
                    f"{latitude_text};{longitude_text}",
                    "Coordonnées incomplètes ou non numériques",
                )
            )
            latitude = longitude = None
        elif not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            anomalies.append(
                StationAnomaly(
                    line_number,
                    code,
                    "Coordonnées",
                    f"{latitude_text};{longitude_text}",
                    "Coordonnées hors limites géographiques",
                )
            )
            latitude = longitude = None

        raw_status = _cell(row, "Statut")
        status = _parse_status(raw_status)
        if status is StationStatus.UNKNOWN:
            anomalies.append(
                StationAnomaly(line_number, code, "Statut", raw_status, "Statut non reconnu")
            )

        date_text = _cell(row, "Mise en service")
        commissioned_on = _parse_date(date_text)
        if commissioned_on is None:
            anomalies.append(
                StationAnomaly(
                    line_number,
                    code,
                    "Mise en service",
                    date_text,
                    "Date invalide (formats acceptés : JJ/MM/AAAA ou AAAA-MM-JJ)",
                )
            )

        if row_is_usable and code is not None and code not in duplicate_set:
            parsed_stations.append(
                Station(
                    code=code,
                    name=name,
                    municipality=municipality,
                    capacity=capacity,
                    latitude=latitude,
                    longitude=longitude,
                    status=status,
                    commissioned_on=commissioned_on,
                )
            )

    return StationReport(
        rows_read=len(raw_rows),
        stations=tuple(parsed_stations),
        anomalies=tuple(sorted(anomalies, key=lambda item: (item.line_number, item.field))),
        duplicate_codes=duplicate_codes,
    )
