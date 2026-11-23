"""Client concurrent pour l'API temps réel des bornes Mobilis."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import wraps
from threading import BoundedSemaphore
from time import sleep
from typing import ParamSpec, TypeVar, cast
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

P = ParamSpec("P")
R = TypeVar("R")
_RETRYABLE_STATUS = frozenset({429, 503, 504})
_MAX_CONCURRENCY = 8


class ApiError(RuntimeError):
    """Erreur de communication avec l'API des bornes."""


class ApiProtocolError(ApiError):
    """Réponse API absente, mal formée ou incohérente."""


@dataclass(frozen=True, slots=True)
class StationFailure:
    """Échec isolé lors de la récupération d'une station."""

    code: str
    message: str
    status_code: int | None = None


def retry_transient(
    *, max_attempts: int = 4, base_delay: float = 0.25
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Décorateur qui réessaie les réponses HTTP 429, 503 et 504.

    `Retry-After` est respecté pour 429. Les réponses 503/504 utilisent un
    délai exponentiel. Les autres erreurs HTTP sont renvoyées sans réessai.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts doit être supérieur ou égal à 1")
    if base_delay < 0:
        raise ValueError("base_delay ne peut pas être négatif")

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(max_attempts):
                try:
                    return function(*args, **kwargs)
                except HTTPError as error:
                    if error.code not in _RETRYABLE_STATUS or attempt == max_attempts - 1:
                        raise
                    delay = _retry_delay(error, base_delay, attempt)
                    sleep(delay)
            raise AssertionError("Boucle de réessai terminée sans résultat")

        return wrapped

    return decorate


def _retry_delay(error: HTTPError, base_delay: float, attempt: int) -> float:
    if error.code == 429 and error.headers is not None:
        retry_after = error.headers.get("Retry-After")
        if isinstance(retry_after, str):
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
    return float(base_delay * (2**attempt))


@dataclass(frozen=True, slots=True)
class StationSnapshot:
    """Photo d'occupation d'une station renvoyée par l'API."""

    code: str
    mechanical_bikes: int
    electric_bikes: int
    free_places: int
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Le code station ne peut pas être vide")
        if min(self.mechanical_bikes, self.electric_bikes, self.free_places) < 0:
            raise ValueError("Les nombres de vélos et de places doivent être positifs")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("L'horodatage doit inclure un fuseau horaire")


@dataclass(frozen=True, slots=True)
class StationComparison:
    """Différences de codes entre le référentiel et le réseau des bornes."""

    missing_from_api: tuple[str, ...]
    unknown_to_reference: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SnapshotReport:
    """Résultat partiel ou complet de la photographie du réseau."""

    snapshots: tuple[StationSnapshot, ...]
    failures: tuple[StationFailure, ...]


@dataclass(frozen=True, slots=True)
class StrategyMeasurement:
    """Durée mesurée pour photographier toutes les stations."""

    strategy: str
    elapsed_seconds: float
    stations_received: int
    stations_failed: int


def compare_station_codes(
    reference_codes: Iterable[str], api_codes: Iterable[str]
) -> StationComparison:
    """Compare les codes connus du référentiel et ceux publiés par les bornes."""
    reference = set(reference_codes)
    api = set(api_codes)
    return StationComparison(
        missing_from_api=tuple(sorted(reference - api)),
        unknown_to_reference=tuple(sorted(api - reference)),
    )


class MobilisApiClient:
    """Client standard-library avec pagination, réessais et concurrence bornée."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        api_key: str = "demo-mobilis-2026",
        *,
        timeout: float = 5.0,
        max_concurrency: int = _MAX_CONCURRENCY,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url doit commencer par http:// ou https://")
        if not api_key.strip():
            raise ValueError("La clé API ne peut pas être vide")
        if timeout <= 0:
            raise ValueError("timeout doit être strictement positif")
        if not 1 <= max_concurrency <= _MAX_CONCURRENCY:
            raise ValueError("max_concurrency doit être compris entre 1 et 8")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_concurrency = max_concurrency
        self._request_semaphore = BoundedSemaphore(_MAX_CONCURRENCY)

    @retry_transient()
    def _request_json(self, path: str) -> dict[str, object]:
        request = Request(
            self.base_url + path,
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
        )
        with self._request_semaphore, urlopen(request, timeout=self.timeout) as response:
            payload: object = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ApiProtocolError("La réponse JSON doit être un objet")
        return cast(dict[str, object], payload)

    def list_station_codes(self) -> tuple[str, ...]:
        """Lit toutes les pages de codes de stations publiées par l'API."""
        codes: list[str] = []
        page = 1
        seen_pages: set[int] = set()
        while page not in seen_pages:
            seen_pages.add(page)
            payload = self._request_json(f"/stations?page={page}")
            response_page = payload.get("page")
            raw_codes = payload.get("stations")
            next_page = payload.get("page_suivante")
            if (
                type(response_page) is not int
                or response_page != page
                or not isinstance(raw_codes, list)
            ):
                raise ApiProtocolError(f"Réponse invalide pour la page {page}")
            for raw_code in raw_codes:
                if not isinstance(raw_code, str) or not raw_code.strip():
                    raise ApiProtocolError(f"Code station invalide sur la page {page}")
                codes.append(raw_code)
            if next_page is None:
                return tuple(codes)
            if type(next_page) is not int or next_page <= page:
                raise ApiProtocolError(f"Page suivante invalide après la page {page}")
            page = next_page
        raise ApiProtocolError("Cycle détecté dans la pagination des stations")

    def get_station(self, code: str) -> StationSnapshot:
        """Récupère et valide la dernière photo de la station donnée."""
        if not code.strip():
            raise ValueError("Le code station ne peut pas être vide")
        payload = self._request_json(f"/stations/{quote(code, safe='')}")
        if payload.get("code") != code:
            raise ApiProtocolError(f"Le code retourné ne correspond pas à {code}")
        mechanical = _required_nonnegative_int(payload, "velos_mecaniques", code)
        electric = _required_nonnegative_int(payload, "velos_electriques", code)
        free_places = _required_nonnegative_int(payload, "places_libres", code)
        raw_timestamp = payload.get("horodatage")
        if not isinstance(raw_timestamp, str):
            raise ApiProtocolError(f"Horodatage manquant pour {code}")
        try:
            timestamp = datetime.fromisoformat(raw_timestamp)
        except ValueError as error:
            raise ApiProtocolError(f"Horodatage invalide pour {code}") from error
        try:
            return StationSnapshot(code, mechanical, electric, free_places, timestamp)
        except ValueError as error:
            raise ApiProtocolError(f"Photo de station invalide pour {code}: {error}") from error

    def snapshot_all(self, strategy: str = "threads") -> SnapshotReport:
        """Photographie toutes les stations sans perdre le lot en cas d'erreur isolée."""
        codes = self.list_station_codes()
        if strategy == "sequential":
            results = tuple(self._snapshot_one(code) for code in codes)
        elif strategy == "threads":
            with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
                results = tuple(executor.map(self._snapshot_one, codes))
        else:
            raise ValueError("strategy doit être 'sequential' ou 'threads'")
        return _make_snapshot_report(results)

    async def snapshot_all_async(self, codes: Iterable[str] | None = None) -> SnapshotReport:
        """Photographie les stations avec asyncio et un maximum de huit tâches."""
        selected_codes = (
            tuple(codes) if codes is not None else await asyncio.to_thread(self.list_station_codes)
        )
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def fetch(code: str) -> StationSnapshot | StationFailure:
            async with semaphore:
                return await asyncio.to_thread(self._snapshot_one, code)

        results = tuple(await asyncio.gather(*(fetch(code) for code in selected_codes)))
        return _make_snapshot_report(results)

    def benchmark(self) -> tuple[StrategyMeasurement, ...]:
        """Mesure séquentiel, threads et asyncio sur les mêmes codes de stations."""
        codes = self.list_station_codes()
        measurements: list[StrategyMeasurement] = []

        start = time.perf_counter()
        sequential_results = tuple(self._snapshot_one(code) for code in codes)
        sequential = _make_snapshot_report(sequential_results)
        measurements.append(
            StrategyMeasurement(
                "sequential",
                time.perf_counter() - start,
                len(sequential.snapshots),
                len(sequential.failures),
            )
        )

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            threaded_results = tuple(executor.map(self._snapshot_one, codes))
        threaded = _make_snapshot_report(threaded_results)
        measurements.append(
            StrategyMeasurement(
                "threads",
                time.perf_counter() - start,
                len(threaded.snapshots),
                len(threaded.failures),
            )
        )

        start = time.perf_counter()
        asynchronous = asyncio.run(self.snapshot_all_async(codes))
        measurements.append(
            StrategyMeasurement(
                "asyncio",
                time.perf_counter() - start,
                len(asynchronous.snapshots),
                len(asynchronous.failures),
            )
        )
        return tuple(measurements)

    def _snapshot_one(self, code: str) -> StationSnapshot | StationFailure:
        try:
            return self.get_station(code)
        except HTTPError as error:
            return StationFailure(code, str(error), error.code)
        except (OSError, ApiError) as error:
            return StationFailure(code, str(error))


def _required_nonnegative_int(payload: dict[str, object], field: str, code: str) -> int:
    value = payload.get(field)
    if type(value) is not int or value < 0:
        raise ApiProtocolError(f"Valeur invalide pour {field} à la station {code}")
    return value


def _make_snapshot_report(
    results: Iterable[StationSnapshot | StationFailure],
) -> SnapshotReport:
    snapshots: list[StationSnapshot] = []
    failures: list[StationFailure] = []
    for result in results:
        if isinstance(result, StationSnapshot):
            snapshots.append(result)
        else:
            failures.append(result)
    return SnapshotReport(tuple(snapshots), tuple(failures))
