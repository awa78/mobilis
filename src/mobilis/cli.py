"""Commandes de diagnostic des stations Mobilis."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from mobilis.commands import add_report_commands, run_facturation, run_frequentation
from mobilis.realtime import ApiError, MobilisApiClient, compare_station_codes
from mobilis.stations import StationReport, load_stations


def _default_stations_path() -> Path | None:
    explicit_path = os.environ.get("MOBILIS_STATIONS")
    if explicit_path:
        return Path(explicit_path)
    data_directory = os.environ.get("MOBILIS_DATA_DIR")
    if data_directory:
        return Path(data_directory) / "stations.csv"
    return None


def _add_station_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stations",
        type=Path,
        default=_default_stations_path(),
        help="chemin du CSV (ou variable MOBILIS_STATIONS / MOBILIS_DATA_DIR)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mobilis", description="Outils d'analyse Mobilis")
    commands = parser.add_subparsers(dest="command", required=True)

    stations_parser = commands.add_parser("stations", help="valide le référentiel des stations")
    _add_station_path_argument(stations_parser)

    state_parser = commands.add_parser("etat", help="photographie le réseau en temps réel")
    _add_station_path_argument(state_parser)
    state_parser.add_argument(
        "--api-url",
        default=os.environ.get("MOBILIS_API_URL", "http://127.0.0.1:8765"),
        help="URL du simulateur ou de l'API (défaut : MOBILIS_API_URL)",
    )
    state_parser.add_argument(
        "--api-key",
        default=os.environ.get("MOBILIS_API_KEY", "demo-mobilis-2026"),
        help="clé d'API (défaut : MOBILIS_API_KEY)",
    )
    state_parser.add_argument(
        "--strategy",
        choices=("threads", "sequential"),
        default="threads",
        help="méthode de photographie (défaut : threads)",
    )
    state_parser.add_argument(
        "--benchmark",
        action="store_true",
        help="mesure séquentiel, threads et asyncio sur toutes les stations",
    )
    add_report_commands(commands)
    return parser


def _require_stations_path(parser: argparse.ArgumentParser, value: Path | None) -> Path:
    if value is None:
        parser.error(
            "indiquez --stations CHEMIN, ou définissez MOBILIS_STATIONS / MOBILIS_DATA_DIR"
        )
    return value


def _print_station_report(report: StationReport) -> None:
    print(f"Lignes lues : {report.rows_read}")
    print(f"Stations fiables : {len(report.stations)}")
    print(f"Stations exploitables : {len(report.exploitable_stations)}")
    print(f"Codes dupliqués : {len(report.duplicate_codes)}")
    print(f"Anomalies signalées : {len(report.anomalies)}")
    for anomaly in report.anomalies:
        code = anomaly.code or "code manquant"
        value = f" (valeur : {anomaly.value})" if anomaly.value else ""
        print(
            f"  ligne {anomaly.line_number} — {code} — {anomaly.field} : {anomaly.message}{value}"
        )


def _run_stations(parser: argparse.ArgumentParser, station_path: Path | None) -> int:
    report = load_stations(_require_stations_path(parser, station_path))
    _print_station_report(report)
    return 0


def _run_state(
    parser: argparse.ArgumentParser,
    station_path: Path | None,
    api_url: str,
    api_key: str,
    strategy: str,
    benchmark: bool,
) -> int:
    report = load_stations(_require_stations_path(parser, station_path))
    client = MobilisApiClient(base_url=api_url, api_key=api_key)

    if benchmark:
        print("Comparaison des stratégies (la pagination commune est hors chronométrage) :")
        for result in client.benchmark():
            print(
                f"{result.strategy} : {result.elapsed_seconds:.2f} s, "
                f"{result.stations_received} photos, {result.stations_failed} échecs"
            )
        return 0

    api_codes = client.list_station_codes()
    snapshot_report = client.snapshot_all(strategy=strategy, codes=api_codes)
    comparison = compare_station_codes(report.codes_seen, api_codes)
    empty_stations = [
        snapshot.code
        for snapshot in snapshot_report.snapshots
        if snapshot.mechanical_bikes + snapshot.electric_bikes == 0
    ]
    full_stations = [
        snapshot.code for snapshot in snapshot_report.snapshots if snapshot.free_places == 0
    ]

    print(f"Codes dans le référentiel : {len(report.codes_seen)}")
    print(f"Codes dans l'API : {len(api_codes)}")
    print(f"Photos reçues : {len(snapshot_report.snapshots)}")
    print(f"Bornes injoignables : {len(snapshot_report.failures)}")
    print(f"Stations sans vélo : {', '.join(empty_stations) or 'aucune'}")
    print(f"Stations pleines : {', '.join(full_stations) or 'aucune'}")
    print(f"Absentes de l'API : {', '.join(comparison.missing_from_api) or 'aucune'}")
    print(f"Inconnues du référentiel : {', '.join(comparison.unknown_to_reference) or 'aucune'}")
    if snapshot_report.failures:
        print("Échecs détaillés :")
        for failure in snapshot_report.failures:
            status = f"HTTP {failure.status_code}" if failure.status_code else "réseau"
            print(f"  {failure.code} — {status} — {failure.message}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Exécute une sous-commande et renvoie son code de sortie."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "stations":
            return _run_stations(parser, args.stations)
        if args.command == "etat":
            return _run_state(
                parser,
                args.stations,
                args.api_url,
                args.api_key,
                args.strategy,
                args.benchmark,
            )
        if args.command == "frequentation":
            return run_frequentation(parser, args)
        if args.command == "facturation":
            return run_facturation(parser, args)
    except (ApiError, OSError, ValueError) as error:
        print(f"Erreur Mobilis : {error}", file=sys.stderr)
        return 1
    parser.error(f"sous-commande inconnue : {args.command}")
    return 2


def console_main() -> None:
    """Point d'entrée utilisé par la commande installée ``mobilis``."""
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
