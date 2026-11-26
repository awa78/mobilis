# Mobilis — règles de facturation des trajets

*Document de la direction commerciale, version du 15 septembre 2026. Les tarifs chiffrés sont dans `donnees/tarifs.json`.*

## 1. Quelle grille, quelle formule ?

- **R1 — Grille.** On applique la grille en vigueur à la **date locale (Europe/Paris) de début** du trajet. Une nouvelle grille entre en vigueur le 1er octobre 2026.
- **R2 — Formule.** On prend l'abonnement **actif** à la date locale de début : `debut ≤ date ≤ fin` (une `fin` vide signifie « en cours »). Un abonné peut avoir **plusieurs lignes** dans `abonnes.jsonl` : chaque ligne est une période d'abonnement (changement de formule, renouvellement).
- **R3 — Pas d'abonnement actif.** Trajet sans `abonne_id`, abonnement expiré ou identifiant introuvable : tarif **occasionnel**. Les identifiants introuvables sont signalés au service client.

## 2. Prix d'un trajet

La **durée** est l'écart entre les **instants** de début et de fin (attention aux fuseaux horaires et aux changements d'heure). Une tranche est due **dès qu'elle est entamée**, même d'une seconde.

- **R4 — Usage.** `usage = max(0, durée − minutes_incluses)` ; prix = `frais_deblocage + tranches entamées de l'usage × prix_tranche`.
- **R5 — Vélo électrique.** Supplément = `tranches entamées de la durée totale × supplement_electrique_tranche` (minutes incluses comprises).
- **R6 — Plafond journalier.** Pour un abonné, la somme des prix (R4 + R5) de ses trajets **facturés à une formule d'abonnement** et commencés le même jour local est plafonnée à `plafond_jour`. Pas de plafond pour le tarif occasionnel.
- **R7 — Arrondi.** Montants en euros, calculés en décimal exact (jamais en `float`), arrondis au centime au plus proche, la moitié vers le haut.

## 3. Cas particuliers

- **R8 — Trajet fantôme.** Durée de moins de 2 minutes **et** retour à la station de départ : rien n'est facturé (vélo raccroché aussitôt, souvent défectueux). À compter à part pour la maintenance.
- **R9 — Non-restitution.** Pas de station ou d'heure d'arrivée, ou durée supérieure à `seuil_non_restitution_heures` : pénalité forfaitaire `penalite_non_restitution`, **à la place** du prix d'usage, hors plafond.
- **R10 — Horodatage incohérent.** Fin antérieure au début : non facturé, transmis à l'équipe technique.
- **R11 — Doublons.** Les bornes renvoient parfois un trajet déjà transmis : un même `trajet_id` n'est facturé qu'une fois.
- **R12 — Station inconnue.** Un trajet vers ou depuis une station absente du référentiel est facturé normalement et signalé.

## 4. Exemples validés par la direction

| # | Situation | Montant |
|---|---|---|
| E1 | Abonné annuel, vélo mécanique, 25 min, le 10/09/2026 | 0,00 € |
| E2 | Abonné annuel, vélo électrique, 25 min, le 10/09/2026 | 0,50 € |
| E3 | Abonné mensuel, vélo mécanique, 61 min, le 10/09/2026 | 2,00 € |
| E4 | Sans abonnement, vélo électrique, 20 min, le 05/10/2026 | 3,70 € |
| E5 | Abonné annuel, trois trajets mécaniques de 3 h le 12/08/2026 | 12,00 € au total |
| E6 | Abonné annuel, vélo mécanique, départ `2026-10-25T02:40:00+02:00`, arrivée `2026-10-25T02:10:00+01:00` | 0,00 € (durée : 30 min) |

Vos tests automatisés doivent au minimum couvrir ces six exemples.
