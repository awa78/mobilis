from datetime import date
from decimal import Decimal

from test_facturation_regles import _moteur, _trajet

from mobilis.facturation import Abonnement


def test_r1_grille_tarifaire_avant_et_apres_2026_10_01() -> None:
    moteur = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), None)])
    avant = moteur.facturer_trajets([
        _trajet("R1-AVANT", "2026-09-15T10:00:00+02:00", "2026-09-15T11:01:00+02:00", subscriber="U1")
    ])[0]
    apres = moteur.facturer_trajets([
        _trajet("R1-APRES", "2026-10-15T10:00:00+02:00", "2026-10-15T11:01:00+02:00", subscriber="U1")
    ])[0]

    assert avant.montant == Decimal("2.00")
    assert apres.montant == Decimal("2.40")


def test_r6_plafond_journalier_sur_plusieurs_trajets() -> None:
    moteur = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), None)])
    trajets = [
        _trajet(f"R6-{i}", "2026-10-15T10:00:00+02:00", "2026-10-15T11:00:00+02:00", subscriber="U1")
        for i in range(12)
    ]
    resultats = moteur.facturer_trajets(trajets)

    assert sum((r.montant for r in resultats), Decimal("0.00")) == Decimal("14.00")


def test_r7_montants_decimal_et_precision_centime() -> None:
    resultat = _moteur().facturer_trajets([
        _trajet("R7", "2026-09-10T10:00:00+02:00", "2026-09-10T10:20:00+02:00")
    ])[0]

    assert isinstance(resultat.montant, Decimal)
    assert resultat.montant == Decimal("2.20")
    assert resultat.montant == resultat.montant.quantize(Decimal("0.01"))
