from datetime import date, datetime
from decimal import Decimal

from mobilis.facturation import (
    Abonnement,
    Facturation,
    Grille,
    Tarif,
)


def tarif(
    minutes_incluses: int,
    tranche: int,
    prix: str,
    electrique: str,
    deblocage: str,
    plafond: str | None,
) -> Tarif:
    return Tarif(
        minutes_incluses=minutes_incluses,
        tranche_minutes=tranche,
        prix_tranche=Decimal(prix),
        supplement_electrique_tranche=Decimal(electrique),
        frais_deblocage=Decimal(deblocage),
        plafond_jour=Decimal(plafond) if plafond else None,
    )


def creer_facturation() -> Facturation:
    ancienne_grille = Grille(
        date_effet=date(2025, 1, 1),
        formules={
            "annuel": tarif(30, 30, "1.00", "0.50", "0.00", "12.00"),
            "mensuel": tarif(30, 30, "1.00", "0.50", "0.00", "15.00"),
            "solidaire": tarif(45, 30, "0.50", "0.25", "0.00", "5.00"),
            "occasionnel": tarif(0, 15, "0.60", "0.40", "1.00", None),
        },
    )

    nouvelle_grille = Grille(
        date_effet=date(2026, 10, 1),
        formules={
            "annuel": tarif(30, 30, "1.20", "0.60", "0.00", "14.00"),
            "mensuel": tarif(30, 30, "1.20", "0.60", "0.00", "18.00"),
            "solidaire": tarif(45, 30, "0.50", "0.25", "0.00", "5.00"),
            "occasionnel": tarif(0, 15, "0.75", "0.50", "1.20", None),
        },
    )

    abonnements = [
        Abonnement("A1", "annuel", date(2024, 1, 1), None),
        Abonnement("M1", "mensuel", date(2024, 1, 1), None),
    ]

    return Facturation(
        grilles=[ancienne_grille, nouvelle_grille],
        abonnements=abonnements,
        stations={"MB-0001", "MB-0002"},
        seuil_non_restitution_heures=24,
        penalite_non_restitution=Decimal("150.00"),
    )


def trajet(
    identifiant: str,
    abonne: str | None,
    debut: str,
    fin: str,
    velo: str = "mechanical",
    depart: str = "MB-0001",
    arrivee: str = "MB-0002",
) -> dict[str, object]:
    return {
        "trajet_id": identifiant,
        "abonne_id": abonne,
        "debut": datetime.fromisoformat(debut),
        "fin": datetime.fromisoformat(fin),
        "type_velo": velo,
        "station_depart": depart,
        "station_arrivee": arrivee,
    }


def test_e1_annuel_mecanique_25_minutes() -> None:
    moteur = creer_facturation()
    resultat = moteur.facturer_trajets(
        [
            trajet(
                "E1",
                "A1",
                "2026-09-10T10:00:00+02:00",
                "2026-09-10T10:25:00+02:00",
            )
        ]
    )
    assert resultat[0].montant == Decimal("0.00")


def test_e2_annuel_electrique_25_minutes() -> None:
    moteur = creer_facturation()
    resultat = moteur.facturer_trajets(
        [
            trajet(
                "E2",
                "A1",
                "2026-09-10T10:00:00+02:00",
                "2026-09-10T10:25:00+02:00",
                "electric",
            )
        ]
    )
    assert resultat[0].montant == Decimal("0.50")


def test_e3_mensuel_mecanique_61_minutes() -> None:
    moteur = creer_facturation()
    resultat = moteur.facturer_trajets(
        [
            trajet(
                "E3",
                "M1",
                "2026-09-10T10:00:00+02:00",
                "2026-09-10T11:01:00+02:00",
            )
        ]
    )
    assert resultat[0].montant == Decimal("2.00")


def test_e4_occasionnel_electrique_20_minutes() -> None:
    moteur = creer_facturation()
    resultat = moteur.facturer_trajets(
        [
            trajet(
                "E4",
                None,
                "2026-10-05T10:00:00+02:00",
                "2026-10-05T10:20:00+02:00",
                "electric",
            )
        ]
    )
    assert resultat[0].montant == Decimal("3.70")


def test_e5_plafond_journalier_annuel() -> None:
    moteur = creer_facturation()
    resultat = moteur.facturer_trajets(
        [
            trajet(
                "E5-1",
                "A1",
                "2026-08-12T08:00:00+02:00",
                "2026-08-12T11:00:00+02:00",
            ),
            trajet(
                "E5-2",
                "A1",
                "2026-08-12T12:00:00+02:00",
                "2026-08-12T15:00:00+02:00",
            ),
            trajet(
                "E5-3",
                "A1",
                "2026-08-12T16:00:00+02:00",
                "2026-08-12T19:00:00+02:00",
            ),
        ]
    )
    assert sum(r.montant for r in resultat) == Decimal("12.00")


def test_e6_changement_heure_hiver() -> None:
    moteur = creer_facturation()
    resultat = moteur.facturer_trajets(
        [
            trajet(
                "E6",
                "A1",
                "2026-10-25T02:40:00+02:00",
                "2026-10-25T02:10:00+01:00",
            )
        ]
    )
    assert resultat[0].montant == Decimal("0.00")
