import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from test_facturation_regles import _moteur, _trajet

from mobilis.facturation import Abonnement, Facturation, resumer_par_mois


def test_r1_grille_tarifaire_avant_et_apres_2026_10_01() -> None:
    moteur = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), None)])
    avant = moteur.facturer_trajets(
        [
            _trajet(
                "R1-AVANT",
                "2026-09-15T10:00:00+02:00",
                "2026-09-15T11:01:00+02:00",
                subscriber="U1",
            )
        ]
    )[0]
    apres = moteur.facturer_trajets(
        [
            _trajet(
                "R1-APRES",
                "2026-10-15T10:00:00+02:00",
                "2026-10-15T11:01:00+02:00",
                subscriber="U1",
            )
        ]
    )[0]

    assert avant.montant == Decimal("2.00")
    assert apres.montant == Decimal("2.40")


def test_r6_plafond_journalier_sur_plusieurs_trajets() -> None:
    moteur = _moteur([Abonnement("U1", "annuel", date(2025, 1, 1), None)])
    trajets = [
        _trajet(
            f"R6-{i}", "2026-10-15T10:00:00+02:00", "2026-10-15T11:00:00+02:00", subscriber="U1"
        )
        for i in range(12)
    ]
    resultats = moteur.facturer_trajets(trajets)

    assert sum((r.montant for r in resultats), Decimal("0.00")) == Decimal("14.00")


def test_effet_nouvelle_grille_octobre_est_mesure_a_volume_constant() -> None:
    abonnement = Abonnement("U1", "annuel", date(2025, 1, 1), None)
    moteur = _moteur([abonnement])
    trajet = _trajet(
        "OCTOBRE",
        "2026-10-15T10:00:00+02:00",
        "2026-10-15T11:01:00+02:00",
        subscriber="U1",
    )
    reel = resumer_par_mois(moteur.iter_facturer_trajets([trajet]))
    ancien_tarif = moteur.avec_grille_precedente(date(2026, 10, 1))
    contrefactuel = resumer_par_mois(ancien_tarif.iter_facturer_trajets([trajet]))

    assert reel["2026-10"].recettes_par_formule["annuel"] == Decimal("2.40")
    assert contrefactuel["2026-10"].recettes_par_formule["annuel"] == Decimal("2.00")
    assert reel["2026-10"].total - contrefactuel["2026-10"].total == Decimal("0.40")


def test_import_abonnes_ignore_et_compte_les_lignes_abimees(tmp_path: Path) -> None:
    tarifs = {
        "grilles": [
            {
                "en_vigueur_du": "2025-01-01",
                "formules": {
                    "occasionnel": {
                        "minutes_incluses": 0,
                        "tranche_minutes": 15,
                        "prix_tranche": "0.60",
                        "supplement_electrique_tranche": "0.40",
                        "frais_deblocage": "1.00",
                        "plafond_jour": None,
                    }
                },
            }
        ],
        "seuil_non_restitution_heures": 24,
        "penalite_non_restitution": "150.00",
    }
    chemin_tarifs = tmp_path / "tarifs.json"
    chemin_tarifs.write_text(json.dumps(tarifs), encoding="utf-8")
    chemin_abonnes = tmp_path / "abonnes.jsonl"
    chemin_abonnes.write_text(
        '{"id":"U1","formule":"annuel","debut":"2025-01-01"}\n{"id":}\n',
        encoding="utf-8",
    )
    chemin_stations = tmp_path / "stations.csv"
    chemin_stations.write_text("Code station;Nom\nS1;Station 1\n", encoding="utf-8")

    moteur = Facturation.depuis_fichiers(chemin_tarifs, chemin_abonnes, chemin_stations)

    assert len(moteur.abonnements) == 1
    assert moteur.anomalies_import["abonnement_malforme"] == 1


def test_r7_montants_decimal_et_precision_centime() -> None:
    resultat = _moteur().facturer_trajets(
        [_trajet("R7", "2026-09-10T10:00:00+02:00", "2026-09-10T10:20:00+02:00")]
    )[0]

    assert isinstance(resultat.montant, Decimal)
    assert resultat.montant == Decimal("2.20")
    assert resultat.montant == resultat.montant.quantize(Decimal("0.01"))
