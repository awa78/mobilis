from datetime import date, datetime
from decimal import Decimal

from mobilis.facturation import Abonnement, Facturation, Grille, Tarif


def _tarif(minutes: int, tranche: int, prix: str, supplement: str, unlock: str, cap: str | None) -> Tarif:
    return Tarif(minutes, tranche, Decimal(prix), Decimal(supplement), Decimal(unlock), Decimal(cap) if cap else None)



def _moteur(abonnements: list[Abonnement] | None = None) -> Facturation:
    grille_2025 = Grille(date(2025, 1, 1), {
        "annuel": _tarif(30, 30, "1.00", "0.50", "0.00", "12.00"),
        "mensuel": _tarif(30, 30, "1.00", "0.50", "0.00", "15.00"),
        "solidaire": _tarif(45, 30, "0.50", "0.25", "0.00", "5.00"),
        "occasionnel": _tarif(0, 15, "0.60", "0.40", "1.00", None),
    })
    grille_2026 = Grille(date(2026, 10, 1), {
        "annuel": _tarif(30, 30, "1.20", "0.60", "0.00", "14.00"),
        "mensuel": _tarif(30, 30, "1.20", "0.60", "0.00", "18.00"),
        "solidaire": _tarif(45, 30, "0.50", "0.25", "0.00", "5.00"),
        "occasionnel": _tarif(0, 15, "0.75", "0.50", "1.20", None),
    })
    return Facturation(
        [grille_2025, grille_2026],
        abonnements or [],
        {"S1", "S2"},
        24,
        Decimal("150.00"),
    )


def _trajet(tid: str, start: str, end: str | None, *, subscriber: str | None = None,
            bike: str = "mechanical", from_station: str = "S1", to_station: str = "S2") -> dict[str, object]:
    return {
        "trajet_id": tid,
        "abonne_id": subscriber,
        "debut": datetime.fromisoformat(start),
        "fin": datetime.fromisoformat(end) if end else None,
        "type_velo": bike,
        "station_depart": from_station,
        "station_arrivee": to_station,
    }



def test_r2_abonnement_renouvele_choisit_periode_la_plus_recente() -> None:
    moteur = _moteur([
        Abonnement("U1", "annuel", date(2025, 1, 1), date(2026, 8, 31)),
        Abonnement("U1", "mensuel", date(2026, 9, 1), None),
    ])
    resultat = moteur.facturer_trajets([_trajet("R2", "2026-09-10T10:00:00+02:00", "2026-09-10T11:01:00+02:00", subscriber="U1")])[0]
    assert resultat.formule == "mensuel"
    assert resultat.montant == Decimal("2.00")



def test_r3_abonnement_expire_tarif_occasionnel() -> None:
    moteur = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), date(2026, 8, 31))])
    resultat = moteur.facturer_trajets([_trajet("R3", "2026-09-10T10:00:00+02:00", "2026-09-10T10:20:00+02:00", subscriber="U1")])[0]
    assert resultat.formule == "occasionnel"
    assert resultat.montant == Decimal("2.20")



def test_r3_identifiant_abonne_inconnu_est_signale() -> None:
    resultat = _moteur().facturer_trajets([_trajet("R3U", "2026-09-10T10:00:00+02:00", "2026-09-10T10:20:00+02:00", subscriber="ABSENT")])[0]
    assert resultat.formule == "occasionnel"
    assert any("inconnu" in anomalie.lower() for anomalie in resultat.anomalies)



def test_r4_tranche_entamee_une_seconde_apres_minutes_incluses() -> None:
    resultat = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), None)]).facturer_trajets([
        _trajet("R4", "2026-09-10T10:00:00+02:00", "2026-09-10T10:30:01+02:00", subscriber="U1")
    ])[0]
    assert resultat.montant == Decimal("1.00")



def test_r5_supplement_electrique_applique_sur_duree_totale() -> None:
    resultat = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), None)]).facturer_trajets([
        _trajet("R5", "2026-09-10T10:00:00+02:00", "2026-09-10T10:30:00+02:00", subscriber="U1", bike="electric")
    ])[0]
    assert resultat.montant == Decimal("0.50")



def test_r8_trajet_fantome_moins_de_deux_minutes_non_facture() -> None:
    resultat = _moteur().facturer_trajets([
        _trajet("R8", "2026-09-10T10:00:00+02:00", "2026-09-10T10:01:59+02:00", from_station="S1", to_station="S1")
    ])[0]
    assert resultat.montant == Decimal("0.00")
    assert "fantôme" in resultat.motif.lower() or "fantome" in resultat.motif.lower()



def test_r9_non_restitution_applique_penalite_forfaitaire() -> None:
    resultat = _moteur().facturer_trajets([
        _trajet("R9", "2026-09-10T10:00:00+02:00", None, to_station="")
    ])[0]
    assert resultat.montant == Decimal("150.00")



def test_r9_duree_superieure_au_seuil_applique_penalite() -> None:
    resultat = _moteur().facturer_trajets([
        _trajet("R9B", "2026-09-10T10:00:00+02:00", "2026-09-11T10:00:01+02:00")
    ])[0]
    assert resultat.montant == Decimal("150.00")



def test_r10_fin_anterieure_debut_non_facturee() -> None:
    resultat = _moteur().facturer_trajets([
        _trajet("R10", "2026-09-10T10:00:00+02:00", "2026-09-10T09:59:00+02:00")
    ])[0]
    assert resultat.montant == Decimal("0.00")
    assert "incohérent" in resultat.motif.lower() or "incoherent" in resultat.motif.lower()



def test_r11_doublon_facture_une_seule_fois() -> None:
    t = _trajet("R11", "2026-09-10T10:00:00+02:00", "2026-09-10T10:20:00+02:00")
    resultats = _moteur().facturer_trajets([t, t.copy()])
    assert resultats[0].montant > Decimal("0.00")
    assert resultats[1].montant == Decimal("0.00")
    assert "doublon" in resultats[1].motif.lower()



def test_r12_station_inconnue_signalee_trajet_facture() -> None:
    resultat = _moteur().facturer_trajets([
        _trajet("R12", "2026-09-10T10:00:00+02:00", "2026-09-10T10:20:00+02:00", from_station="UNKNOWN")
    ])[0]
    assert resultat.montant == Decimal("2.20")
    assert any("station inconnue" in anomalie.lower() for anomalie in resultat.anomalies)
