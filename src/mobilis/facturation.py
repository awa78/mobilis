
from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
CENTIME = Decimal("0.01")
ZERO = Decimal("0.00")


def arrondir(montant: Decimal) -> Decimal:
    return montant.quantize(CENTIME, rounding=ROUND_HALF_UP)


def lire_datetime(valeur: str | datetime | None) -> datetime | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        return valeur
    return datetime.fromisoformat(valeur)


def date_locale(valeur: datetime) -> date:
    if valeur.tzinfo is None:
        valeur = valeur.replace(tzinfo=PARIS)
    return valeur.astimezone(PARIS).date()


def duree_minutes(debut: datetime, fin: datetime) -> Decimal:
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=PARIS)
    if fin.tzinfo is None:
        fin = fin.replace(tzinfo=PARIS)

    secondes = (
        fin.astimezone(UTC) - debut.astimezone(UTC)
    ).total_seconds()
    
    return Decimal(str(secondes)) / Decimal(60)


def tranches_entamees(minutes: Decimal, taille: int) -> int:
    if minutes <= 0:
        return 0
    return int(
        (minutes / Decimal(taille)).to_integral_value(rounding="ROUND_CEILING")
    )


@dataclass(frozen=True)
class Tarif:
    minutes_incluses: int
    tranche_minutes: int
    prix_tranche: Decimal
    supplement_electrique_tranche: Decimal
    frais_deblocage: Decimal
    plafond_jour: Decimal | None


@dataclass(frozen=True)
class Grille:
    date_effet: date
    formules: dict[str, Tarif]


@dataclass(frozen=True)
class Abonnement:
    abonne_id: str
    formule: str
    debut: date
    fin: date | None


@dataclass
class ResultatTrajet:
    trajet_id: str
    abonne_id: str | None
    formule: str
    date_locale: date | None
    montant: Decimal
    motif: str
    anomalies: list[str]


class PolitiqueTarifaire(Protocol):
    def calculer(
        self, duree: Decimal, tarif: Tarif, electrique: bool
    ) -> Decimal: ...


class PolitiqueStandard:
    def calculer(
        self, duree: Decimal, tarif: Tarif, electrique: bool
    ) -> Decimal:
        usage = max(Decimal(0), duree - tarif.minutes_incluses)
        montant = tarif.frais_deblocage + (
            Decimal(tranches_entamees(usage, tarif.tranche_minutes))
            * tarif.prix_tranche
        )

        if electrique:
            montant += (
                Decimal(tranches_entamees(duree, tarif.tranche_minutes))
                * tarif.supplement_electrique_tranche
            )

        return arrondir(montant)


class PolitiqueAlternative:
    """Implémentation alternative de la stratégie de tarification."""

    def calculer(
        self, duree: Decimal, tarif: Tarif, electrique: bool
    ) -> Decimal:
        usage = max(Decimal(0), duree - tarif.minutes_incluses)
        tranches_usage = tranches_entamees(usage, tarif.tranche_minutes)

        montant = tarif.frais_deblocage + (
            tarif.prix_tranche * tranches_usage
        )

        if electrique:
            montant += tarif.supplement_electrique_tranche * (
                tranches_entamees(duree, tarif.tranche_minutes)
            )

        return arrondir(montant)


class Facturation:
    def __init__(
        self,
        grilles: list[Grille],
        abonnements: list[Abonnement],
        stations: set[str],
        seuil_non_restitution_heures: int,
        penalite_non_restitution: Decimal,
        politique: PolitiqueTarifaire | None = None,
    ) -> None:
        self.grilles = sorted(grilles, key=lambda grille: grille.date_effet)
        self.abonnements = abonnements
        self.stations = stations
        self.seuil_non_restitution_heures = seuil_non_restitution_heures
        self.penalite_non_restitution = penalite_non_restitution
        self.politique = politique or PolitiqueStandard()

    @classmethod
    def depuis_fichiers(
        cls,
        chemin_tarifs: Path,
        chemin_abonnes: Path,
        chemin_stations: Path,
        politique: PolitiqueTarifaire | None = None,
    ) -> Facturation:
        with chemin_tarifs.open(encoding="utf-8") as fichier:
            donnees_tarifs = json.load(fichier)

        grilles: list[Grille] = []

        for grille_json in donnees_tarifs["grilles"]:
            formules = {
                nom: Tarif(
                    minutes_incluses=tarif["minutes_incluses"],
                    tranche_minutes=tarif["tranche_minutes"],
                    prix_tranche=Decimal(tarif["prix_tranche"]),
                    supplement_electrique_tranche=Decimal(
                        tarif["supplement_electrique_tranche"]
                    ),
                    frais_deblocage=Decimal(tarif["frais_deblocage"]),
                    plafond_jour=(
                        Decimal(tarif["plafond_jour"])
                        if tarif["plafond_jour"] is not None
                        else None
                    ),
                )
                for nom, tarif in grille_json["formules"].items()
            }

            grilles.append(
                Grille(
                    date_effet=date.fromisoformat(
                        grille_json["en_vigueur_du"]
                    ),
                    formules=formules,
                )
            )

        abonnements: list[Abonnement] = []

        with chemin_abonnes.open(encoding="utf-8") as fichier:
            for ligne in fichier:
                if not ligne.strip():
                    continue
                donnees = json.loads(ligne)
                abonnements.append(
                    Abonnement(
                        abonne_id=donnees["id"],
                        formule=donnees["formule"],
                        debut=date.fromisoformat(donnees["debut"]),
                        fin=(
                            date.fromisoformat(donnees["fin"])
                            if donnees.get("fin")
                            else None
                        ),
                    )
                )

        stations: set[str] = set()

        with chemin_stations.open(
            encoding="utf-8-sig", newline=""
        ) as fichier:
            lecteur_stations = csv.DictReader(fichier, delimiter=";")
            for station_ligne in lecteur_stations:
                code_station = station_ligne.get("Code station", "")
                if code_station:
                    stations.add(code_station.strip())

        return cls(
            grilles=grilles,
            abonnements=abonnements,
            stations=stations,
            seuil_non_restitution_heures=donnees_tarifs[
                "seuil_non_restitution_heures"
            ],
            penalite_non_restitution=Decimal(
                donnees_tarifs["penalite_non_restitution"]
            ),
            politique=politique,
        )

    def grille_pour_date(self, jour: date) -> Grille:
        disponibles = [
            grille for grille in self.grilles
            if grille.date_effet <= jour
        ]
        if not disponibles:
            raise ValueError(f"Aucune grille tarifaire pour le {jour}")
        return disponibles[-1]

    def abonnement_actif(
        self, abonne_id: str | None, jour: date
    ) -> Abonnement | None:
        if not abonne_id:
            return None

        actifs = [
            abonnement
            for abonnement in self.abonnements
            if abonnement.abonne_id == abonne_id
            and abonnement.debut <= jour
            and (abonnement.fin is None or jour <= abonnement.fin)
        ]

        return max(actifs, key=lambda abonnement: abonnement.debut) if actifs else None

    def facturer_trajets(
        self, trajets: Iterable[dict[str, object]]
    ) -> list[ResultatTrajet]:
        resultats: list[ResultatTrajet] = []
        deja_vus: set[str] = set()
        cumuls: dict[tuple[str, date], Decimal] = defaultdict(lambda: ZERO)

        for trajet in trajets:
            trajet_id = str(trajet.get("trajet_id", ""))
            anomalies: list[str] = []

            if trajet_id and trajet_id in deja_vus:
                resultats.append(
                    ResultatTrajet(
                        trajet_id, None, "non_facture", None, ZERO,
                        "doublon", ["trajet dupliqué"]
                    )
                )
                continue

            if trajet_id:
                deja_vus.add(trajet_id)

            debut = lire_datetime(trajet.get("debut"))  # type: ignore[arg-type]
            fin = lire_datetime(trajet.get("fin"))  # type: ignore[arg-type]
            abonne_id = (
                str(trajet["abonne_id"])
                if trajet.get("abonne_id")
                else None
            )
            depart = str(trajet.get("station_depart") or "")
            arrivee = str(trajet.get("station_arrivee") or "")
            type_velo = str(trajet.get("type_velo") or "").lower()

            if debut is None:
                resultats.append(
                    ResultatTrajet(
                        trajet_id, abonne_id, "non_facture", None, ZERO,
                        "début manquant", ["début manquant ou invalide"]
                    )
                )
                continue

            jour = date_locale(debut)

            for station in (depart, arrivee):
                if station and station not in self.stations:
                    anomalies.append(f"station inconnue : {station}")

            # R9 : non-restitution
            if fin is None or not depart or not arrivee:
                resultats.append(
                    ResultatTrajet(
                        trajet_id, abonne_id, "occasionnel", jour,
                        arrondir(self.penalite_non_restitution),
                        "non-restitution", anomalies + ["non-restitution"]
                    )
                )
                continue

            minutes = duree_minutes(debut, fin)

            # R10 : fin antérieure au début
            if minutes < 0:
                resultats.append(
                    ResultatTrajet(
                        trajet_id, abonne_id, "non_facture", jour, ZERO,
                        "horodatage incohérent",
                        anomalies + ["fin antérieure au début"]
                    )
                )
                continue

            # R8 : trajet fantôme
            if minutes < 2 and depart == arrivee:
                resultats.append(
                    ResultatTrajet(
                        trajet_id, abonne_id, "non_facture", jour, ZERO,
                        "trajet fantôme", anomalies + ["trajet fantôme"]
                    )
                )
                continue

            # R9 : dépassement du seuil
            if minutes > Decimal(
                self.seuil_non_restitution_heures * 60
            ):
                resultats.append(
                    ResultatTrajet(
                        trajet_id, abonne_id, "occasionnel", jour,
                        arrondir(self.penalite_non_restitution),
                        "non-restitution",
                        anomalies + ["durée supérieure au seuil"]
                    )
                )
                continue

            abonnement = self.abonnement_actif(abonne_id, jour)
            formule = abonnement.formule if abonnement else "occasionnel"

            if abonne_id and not any(
                abonne.abonne_id == abonne_id
                for abonne in self.abonnements
            ):
                anomalies.append(
                    f"abonné inconnu : {abonne_id}"
                )

            grille = self.grille_pour_date(jour)
            tarif = grille.formules.get(formule)

            if tarif is None:
                formule = "occasionnel"
                tarif = grille.formules["occasionnel"]

            electrique = "elect" in type_velo or "élect" in type_velo
            montant = self.politique.calculer(minutes, tarif, electrique)

            # R6 : plafond journalier des abonnés
            if abonnement and tarif.plafond_jour is not None:
                cle = (abonne_id or "", jour)
                restant = max(
                    ZERO, tarif.plafond_jour - cumuls[cle]
                )
                montant = min(montant, restant)
                cumuls[cle] += montant

            resultats.append(
                ResultatTrajet(
                    trajet_id, abonne_id, formule, jour,
                    arrondir(montant), "facturé", anomalies
                )
            )

        return resultats
