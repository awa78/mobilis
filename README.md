# Mobilis

Bibliothèque Python pour charger et analyser les données du réseau de vélos Mobilis. Le dépôt contient le code, pas les exports bruts du kit : donne leur chemin avec une option ou une variable d'environnement.

## Installation

Python 3.11 ou plus récent est nécessaire.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Commandes disponibles

### Vérifier le référentiel des stations

```powershell
mobilis stations --stations "C:\chemin\vers\donnees\stations.csv"
```

La commande signale les anomalies, le nombre de stations fiables et le nombre de stations exploitables. Le chemin peut aussi être fourni par `MOBILIS_STATIONS`, ou par `MOBILIS_DATA_DIR` si ce dossier contient `stations.csv`.

### Consulter l'état du réseau

Dans un autre terminal, lancer le simulateur fourni avec le kit :

```powershell
python ..\mobilis-kit\mobilis-kit\outils\serveur_bornes.py
```

Puis photographier les stations :

```powershell
mobilis etat --stations "C:\chemin\vers\donnees\stations.csv"
```

L'URL et la clé de l'API peuvent être réglées avec `--api-url` et `--api-key`, ou les variables `MOBILIS_API_URL` et `MOBILIS_API_KEY`. La stratégie par défaut utilise des threads, avec huit appels simultanés au maximum. Pour comparer les temps séquentiel, threads et asyncio, ajouter `--benchmark`.

## Vérifications de développement

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mypy --strict src\mobilis
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
```

Les tests de l'API utilisent des réponses simulées et ne lancent pas le serveur.
