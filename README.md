# Mobilis

Bibliotheque Python pour controler le referentiel des stations, analyser les trajets, calculer les factures et consulter l'etat du reseau Mobilis. Les donnees du kit restent hors du depot; les commandes prennent leurs chemins en options ou dans des variables d'environnement.

## Installation

Python 3.11 ou plus recent est requis.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Chemins des donnees

Les options de chaque commande peuvent etre remplacees par des variables. `MOBILIS_DATA_DIR` sert de valeur par defaut pour les fichiers portant leur nom standard.

| Fichier | Option | Variable |
|---|---|---|
| `stations.csv` | `--stations` | `MOBILIS_STATIONS` |
| `trajets_2026-08_2026-10.csv.gz` | `--trajets` | `MOBILIS_TRAJETS` |
| `tarifs.json` | `--tarifs` | `MOBILIS_TARIFS` |
| `abonnes.jsonl` | `--abonnes` | `MOBILIS_ABONNES` |

PowerShell:

```powershell
$env:MOBILIS_DATA_DIR = "C:\chemin\vers\mobilis-kit\donnees"
```

## Commandes

### Referentiel des stations

```powershell
mobilis stations --stations "C:\chemin\vers\donnees\stations.csv"
```

La commande normalise les statuts et produit un rapport d'anomalies sans s'arreter a la premiere ligne invalide.

### Frequentation et flux des trajets

```powershell
mobilis frequentation --trajets "C:\chemin\vers\donnees\trajets_2026-08_2026-10.csv.gz"
```

La lecture gzip, la conversion des dates, le dedoublonnage et les agregats sont traites en flux. Les dates sont converties en instants, puis classees en heure locale de Paris. Les stations sont classees selon leur flux net pour identifier celles qui se vident le matin et se remplissent le soir.

Pour generer le fichier de test 100 fois plus grand et mesurer le pic memoire du pipeline:

```powershell
python scripts/benchmark_trajets.py --trajets "C:\chemin\vers\donnees\trajets_2026-08_2026-10.csv.gz"
python scripts/anomalies_trajets.py --trajets "C:\chemin\vers\donnees\trajets_2026-08_2026-10.csv.gz"
```

### Facturation

```powershell
mobilis facturation `
  --trajets "C:\chemin\vers\donnees\trajets_2026-08_2026-10.csv.gz" `
  --tarifs "C:\chemin\vers\donnees\tarifs.json" `
  --abonnes "C:\chemin\vers\donnees\abonnes.jsonl" `
  --stations "C:\chemin\vers\donnees\stations.csv"
```

Le rapport donne les recettes mensuelles par formule. Pour mesurer l'effet de la nouvelle grille, il recalcule octobre avec les memes trajets et l'ancienne grille. Les montants utilisent `Decimal` et les regles R1 a R12 de la specification du kit.

### Etat du reseau en temps reel

Dans un terminal separe, demarrer le simulateur fourni avec le kit:

```powershell
python ..\mobilis-kit\mobilis-kit\outils\serveur_bornes.py
```

Puis demander une photo du reseau:

```powershell
mobilis etat --stations "C:\chemin\vers\donnees\stations.csv"
```

L'URL et la cle de l'API peuvent etre reglees avec `--api-url` et `--api-key`, ou `MOBILIS_API_URL` et `MOBILIS_API_KEY`. La strategie par defaut utilise au plus huit appels simultanes. Ajouter `--benchmark` pour comparer les strategies sequentielle, threads et asyncio.

## Choix de traitement des anomalies

Les donnees ne sont jamais modifiees a la main. Les anomalies, leurs nombres, decisions et justifications sont consignes dans [`docs/journal_anomalies.md`](docs/journal_anomalies.md). Les decisions de facturation sont detaillees selon R1 a R12; les resultats reproduits utilisent les fichiers bruts du kit.

## Verifications

```powershell
python -m pytest -q
python -m mypy --strict src\mobilis
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
```

GitHub Actions execute ces quatre controles sur Python 3.11 et 3.14 pour chaque push et pull request.
