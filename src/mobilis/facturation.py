"""Regles de calcul et rapports de facturation des trajets Mobilis."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
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
    """Arrondit au centime, avec les demi-centimes arrondis vers le haut."""
    return montant.quantize(CENTIME, rounding=ROUND_HALF_UP)


def lire_datetime(valeur: str | datetime | None) -> datetime | None:
    """Convertit une date ISO ou conserve un objet datetime deja normalise."""
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        return valeur
    return datetime.fromisoformat(valeur)


def date_locale(valeur: datetime) -> date:
    """Retourne le jour local Europe/Paris correspondant a un instant."""
    if valeur.tzinfo is None:
        valeur = valeur.replace(tzinfo=PARIS)
    return valeur.astimezone(PARIS).date()


def duree_minutes(debut: datetime, fin: datetime) -> Decimal:
    """Calcule l'ecart entre deux instants en minutes decimales exactes."""
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=PARIS)
    if fin.tzinfo is None:
        fin = fin.replace(tzinfo=PARIS)

    secondes = (fin.astimezone(UTC) - debut.astimezone(UTC)).total_seconds()

    return Decimal(str(secondes)) / Decimal(60)


def tranches_entamees(minutes: Decimal, taille: int) -> int:
    """Compte les tranches entamees, toute fraction comptant pour une tranche."""
    if minutes <= 0:
        return 0
    return int((minutes / Decimal(taille)).to_integral_value(rounding="ROUND_CEILING"))


@dataclass(frozen=True)
class Tarif:
    """Parametres d'une formule dans une grille tarifaire."""

    minutes_incluses: int
    tranche_minutes: int
    prix_tranche: Decimal
    supplement_electrique_tranche: Decimal
    frais_deblocage: Decimal
    plafond_jour: Decimal | None


@dataclass(frozen=True)
class Grille:
    """Grille tarifaire applicable a partir de sa date d'effet."""

    date_effet: date
    formules: dict[str, Tarif]


@dataclass(frozen=True)
class Abonnement:
    """Periode d'abonnement d'un usager a une formule."""

    abonne_id: str
    formule: str
    debut: date
    fin: date | None


@dataclass
class ResultatTrajet:
    """Montant facture et anomalies constatees pour un trajet."""

    trajet_id: str
    abonne_id: str | None
    formule: str
    date_locale: date | None
    montant: Decimal
    motif: str
    anomalies: list[str]


@dataclass(frozen=True)
class BilanMensuel:
    """Recettes du mois ventilees par formule."""

    """Recettes mensuelles, ventilées par formule tarifaire."""

    recettes_par_formule: dict[str, Decimal]
    total: Decimal


def resumer_par_mois(
    resultats: Iterable[ResultatTrajet],
) -> dict[str, BilanMensuel]:
    """Regroupe les montants par mois local et par formule tarifaire."""
    recettes: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for resultat in resultats:
        if resultat.date_locale is None or resultat.formule == "non_facture":
            continue
        mois = resultat.date_locale.strftime("%Y-%m")
        par_formule = recettes[mois]
        par_formule[resultat.formule] = par_formule.get(resultat.formule, ZERO) + resultat.montant

    bilans: dict[str, BilanMensuel] = {}
    for mois, par_formule in sorted(recettes.items()):
        ordonnees = dict(sorted(par_formule.items()))
        bilans[mois] = BilanMensuel(
            recettes_par_formule=ordonnees,
            total=sum(ordonnees.values(), ZERO),
        )
    return bilans


class PolitiqueTarifaire(Protocol):
    """Contrat commun aux strategies de calcul des tarifs."""

    def calculer(self, duree: Decimal, tarif: Tarif, electrique: bool) -> Decimal:
        """Retourne le prix d'usage et le supplement electrique eventuel."""
        ...


class PolitiqueStandard:
    """Applique les formules R4 et R5 de la specification."""

    def calculer(self, duree: Decimal, tarif: Tarif, electrique: bool) -> Decimal:
        """Calcule le montant avant application du plafond journalier."""
        usage = max(Decimal(0), duree - tarif.minutes_incluses)
        montant = tarif.frais_deblocage + (
            Decimal(tranches_entamees(usage, tarif.tranche_minutes)) * tarif.prix_tranche
        )

        if electrique:
            montant += (
                Decimal(tranches_entamees(duree, tarif.tranche_minutes))
                * tarif.supplement_electrique_tranche
            )

        return arrondir(montant)


class PolitiqueAlternative:
    """Implémentation alternative de la stratégie de tarification."""

    def calculer(self, duree: Decimal, tarif: Tarif, electrique: bool) -> Decimal:
        """Calcule le montant en additionnant les deux composantes tarifaires."""
        usage = max(Decimal(0), duree - tarif.minutes_incluses)
        tranches_usage = tranches_entamees(usage, tarif.tranche_minutes)

        montant = tarif.frais_deblocage + (tarif.prix_tranche * tranches_usage)

        if electrique:
            montant += tarif.supplement_electrique_tranche * (
                tranches_entamees(duree, tarif.tranche_minutes)
            )

        return arrondir(montant)


class Facturation:
    """Charge les regles et facture des trajets selon les regles R1 a R12."""

    def __init__(
        self,
        grilles: list[Grille],
        abonnements: list[Abonnement],
        stations: set[str],
        seuil_non_restitution_heures: int,
        penalite_non_restitution: Decimal,
        politique: PolitiqueTarifaire | None = None,
        anomalies_import: Counter[str] | None = None,
    ) -> None:
        """Initialise le moteur avec grilles, abonnements, stations et penalites."""
        self.grilles = sorted(grilles, key=lambda grille: grille.date_effet)
        self.abonnements = abonnements
        self.stations = stations
        self.seuil_non_restitution_heures = seuil_non_restitution_heures
        self.penalite_non_restitution = penalite_non_restitution
        self.politique = politique or PolitiqueStandard()
        self.anomalies_import = anomalies_import or Counter()

    @classmethod
    def depuis_fichiers(
        cls,
        chemin_tarifs: Path,
        chemin_abonnes: Path,
        chemin_stations: Path,
        politique: PolitiqueTarifaire | None = None,
    ) -> Facturation:
        """Charge les fichiers du kit et compte les lignes d'abonnement abimees."""
        with chemin_tarifs.open(encoding="utf-8") as fichier:
            donnees_tarifs = json.load(fichier)

        grilles: list[Grille] = []

        for grille_json in donnees_tarifs["grilles"]:
            formules = {
                nom: Tarif(
                    minutes_incluses=tarif["minutes_incluses"],
                    tranche_minutes=tarif["tranche_minutes"],
                    prix_tranche=Decimal(tarif["prix_tranche"]),
                    supplement_electrique_tranche=Decimal(tarif["supplement_electrique_tranche"]),
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
                    date_effet=date.fromisoformat(grille_json["en_vigueur_du"]),
                    formules=formules,
                )
            )

        abonnements: list[Abonnement] = []
        anomalies_import: Counter[str] = Counter()

        with chemin_abonnes.open(encoding="utf-8") as fichier:
            for numero_ligne, ligne in enumerate(fichier, start=1):
                if not ligne.strip():
                    continue
                try:
                    donnees = json.loads(ligne)
                    if not isinstance(donnees, dict):
                        raise TypeError("l'enregistrement n'est pas un objet JSON")
                    abonne_id = donnees.get("id")
                    formule = donnees.get("formule")
                    debut_brut = donnees.get("debut")
                    fin_brute = donnees.get("fin")
                    if not isinstance(abonne_id, str) or not abonne_id.strip():
                        raise ValueError("identifiant d'abonné manquant")
                    if not isinstance(formule, str) or not formule.strip():
                        raise ValueError("formule d'abonnement manquante")
                    if not isinstance(debut_brut, str) or not debut_brut.strip():
                        raise ValueError("identifiant, formule ou début manquant")
                    if fin_brute is not None and not isinstance(fin_brute, str):
                        raise ValueError("fin d'abonnement invalide")

                    abonnements.append(
                        Abonnement(
                            abonne_id=abonne_id.strip(),
                            formule=formule.strip(),
                            debut=date.fromisoformat(debut_brut),
                            fin=date.fromisoformat(fin_brute) if fin_brute else None,
                        )
                    )
                except (json.JSONDecodeError, TypeError, ValueError):
                    anomalies_import["abonnement_malforme"] += 1

        stations: set[str] = set()

        with chemin_stations.open(encoding="cp1252", newline="") as fichier:
            lecteur_stations = csv.DictReader(fichier, delimiter=";")
            for station_ligne in lecteur_stations:
                code_station = station_ligne.get("Code station", "")
                if code_station:
                    stations.add(code_station.strip())

        return cls(
            grilles=grilles,
            abonnements=abonnements,
            stations=stations,
            seuil_non_restitution_heures=donnees_tarifs["seuil_non_restitution_heures"],
            penalite_non_restitution=Decimal(donnees_tarifs["penalite_non_restitution"]),
            politique=politique,
            anomalies_import=anomalies_import,
        )

    def grille_pour_date(self, jour: date) -> Grille:
        """Selectionne la grille la plus recente applicable au jour local."""
        disponibles = [grille for grille in self.grilles if grille.date_effet <= jour]
        if not disponibles:
            raise ValueError(f"Aucune grille tarifaire pour le {jour}")
        return disponibles[-1]

    def avec_grille_precedente(self, date_effet: date) -> Facturation:
        """Construit le scénario contrefactuel avec l'ancienne grille à cette date."""
        grille_actuelle = self.grille_pour_date(date_effet)
        if grille_actuelle.date_effet != date_effet:
            raise ValueError(f"Aucune nouvelle grille en vigueur le {date_effet}")
        precedentes = [grille for grille in self.grilles if grille.date_effet < date_effet]
        if not precedentes:
            raise ValueError(f"Aucune grille précédente au {date_effet}")

        grilles = [grille for grille in self.grilles if grille.date_effet != date_effet]
        grilles.append(Grille(date_effet, precedentes[-1].formules))
        return Facturation(
            grilles,
            self.abonnements,
            self.stations,
            self.seuil_non_restitution_heures,
            self.penalite_non_restitution,
            self.politique,
            self.anomalies_import.copy(),
        )

    def abonnement_actif(self, abonne_id: str | None, jour: date) -> Abonnement | None:
        """Retourne la periode active la plus recente pour l'usager."""
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

    def _anomalies_stations(self, depart: str, arrivee: str) -> list[str]:
        return [
            f"station inconnue : {station}"
            for station in (depart, arrivee)
            if station and station not in self.stations
        ]

    def _resultat_penalite(
        self,
        trajet_id: str,
        abonne_id: str | None,
        jour: date,
        anomalies: list[str],
        motif_anomalie: str,
    ) -> ResultatTrajet:
        return ResultatTrajet(
            trajet_id,
            abonne_id,
            "occasionnel",
            jour,
            arrondir(self.penalite_non_restitution),
            "non-restitution",
            anomalies + [motif_anomalie],
        )

    def _resultat_non_restitution(
        self,
        trajet_id: str,
        abonne_id: str | None,
        jour: date,
        fin: datetime | None,
        arrivee: str,
        anomalies: list[str],
    ) -> ResultatTrajet | None:
        if fin is not None and arrivee:
            return None
        return self._resultat_penalite(
            trajet_id,
            abonne_id,
            jour,
            anomalies,
            "non-restitution",
        )

    def _resultat_duree_invalide(
        self,
        trajet_id: str,
        abonne_id: str | None,
        jour: date,
        minutes: Decimal,
        anomalies: list[str],
    ) -> ResultatTrajet | None:
        if minutes >= 0:
            return None
        return ResultatTrajet(
            trajet_id,
            abonne_id,
            "non_facture",
            jour,
            ZERO,
            "horodatage incohérent",
            anomalies + ["fin antérieure au début"],
        )

    def _resultat_trajet_fantome(
        self,
        trajet_id: str,
        abonne_id: str | None,
        jour: date,
        minutes: Decimal,
        depart: str,
        arrivee: str,
        anomalies: list[str],
    ) -> ResultatTrajet | None:
        if minutes >= 2 or depart != arrivee:
            return None
        return ResultatTrajet(
            trajet_id,
            abonne_id,
            "non_facture",
            jour,
            ZERO,
            "trajet fantôme",
            anomalies + ["trajet fantôme"],
        )

    def _resultat_duree_seuil(
        self,
        trajet_id: str,
        abonne_id: str | None,
        jour: date,
        minutes: Decimal,
        anomalies: list[str],
    ) -> ResultatTrajet | None:
        seuil = Decimal(self.seuil_non_restitution_heures * 60)
        if minutes <= seuil:
            return None
        return self._resultat_penalite(
            trajet_id,
            abonne_id,
            jour,
            anomalies,
            "durée supérieure au seuil",
        )

    def _calculer_facture_valide(
        self,
        trajet_id: str,
        abonne_id: str | None,
        jour: date,
        minutes: Decimal,
        type_velo: str,
        anomalies: list[str],
        cumuls: dict[tuple[str, date], Decimal],
    ) -> ResultatTrajet:
        abonnement = self.abonnement_actif(abonne_id, jour)
        formule = abonnement.formule if abonnement else "occasionnel"

        if abonne_id and not any(abonne.abonne_id == abonne_id for abonne in self.abonnements):
            anomalies.append(f"abonné inconnu : {abonne_id}")

        grille = self.grille_pour_date(jour)
        tarif = grille.formules.get(formule)
        if tarif is None:
            formule = "occasionnel"
            tarif = grille.formules["occasionnel"]

        electrique = "elect" in type_velo or "élect" in type_velo
        montant = self.politique.calculer(minutes, tarif, electrique)

        if abonnement and tarif.plafond_jour is not None:
            cle = (abonne_id or "", jour)
            restant = max(ZERO, tarif.plafond_jour - cumuls[cle])
            montant = min(montant, restant)
            cumuls[cle] += montant

        return ResultatTrajet(
            trajet_id,
            abonne_id,
            formule,
            jour,
            arrondir(montant),
            "facturé",
            anomalies,
        )

    def _facturer_un_trajet(
        self,
        trajet: Mapping[str, object],
        cumuls: dict[tuple[str, date], Decimal],
    ) -> ResultatTrajet:
        trajet_id = str(trajet.get("trajet_id", ""))
        debut = lire_datetime(trajet.get("debut"))  # type: ignore[arg-type]
        fin = lire_datetime(trajet.get("fin"))  # type: ignore[arg-type]
        abonne_id = str(trajet["abonne_id"]) if trajet.get("abonne_id") else None
        depart = str(trajet.get("station_depart") or "")
        arrivee = str(trajet.get("station_arrivee") or "")
        type_velo = str(trajet.get("type_velo") or "").lower()

        if debut is None:
            return ResultatTrajet(
                trajet_id,
                abonne_id,
                "non_facture",
                None,
                ZERO,
                "début manquant",
                ["début manquant ou invalide"],
            )

        jour = date_locale(debut)
        anomalies = self._anomalies_stations(depart, arrivee)

        penalite = self._resultat_non_restitution(
            trajet_id, abonne_id, jour, fin, arrivee, anomalies
        )
        if penalite is not None:
            return penalite

        assert fin is not None
        minutes = duree_minutes(debut, fin)  # fin validée ci-dessus
        duree_invalide = self._resultat_duree_invalide(
            trajet_id, abonne_id, jour, minutes, anomalies
        )
        if duree_invalide is not None:
            return duree_invalide

        fantome = self._resultat_trajet_fantome(
            trajet_id, abonne_id, jour, minutes, depart, arrivee, anomalies
        )
        if fantome is not None:
            return fantome

        penalite_seuil = self._resultat_duree_seuil(trajet_id, abonne_id, jour, minutes, anomalies)
        if penalite_seuil is not None:
            return penalite_seuil

        return self._calculer_facture_valide(
            trajet_id, abonne_id, jour, minutes, type_velo, anomalies, cumuls
        )

    def iter_facturer_trajets(
        self, trajets: Iterable[Mapping[str, object]]
    ) -> Iterator[ResultatTrajet]:
        """Facture les trajets en flux, en conservant les cumuls n?cessaires."""
        deja_vus: set[str] = set()
        cumuls: dict[tuple[str, date], Decimal] = defaultdict(lambda: ZERO)

        for trajet in trajets:
            trajet_id = str(trajet.get("trajet_id", ""))
            if trajet_id and trajet_id in deja_vus:
                yield ResultatTrajet(
                    trajet_id,
                    None,
                    "non_facture",
                    None,
                    ZERO,
                    "doublon",
                    ["trajet dupliqu?"],
                )
                continue

            if trajet_id:
                deja_vus.add(trajet_id)

            yield self._facturer_un_trajet(trajet, cumuls)

    def facturer_trajets(self, trajets: Iterable[Mapping[str, object]]) -> list[ResultatTrajet]:
        """Retourne les r?sultats sous forme de liste pour les appels ponctuels."""
        return list(self.iter_facturer_trajets(trajets))
