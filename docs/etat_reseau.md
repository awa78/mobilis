# État du réseau en temps réel

Le client est dans `src/mobilis/realtime.py`. Il récupère les codes par pagination, interroge ensuite les bornes en parallèle, respecte la limite de huit requêtes, et réessaie les réponses HTTP 429, 503 et 504. Une station qui reste injoignable est inscrite dans `SnapshotReport.failures`; elle ne fait pas échouer la photo complète.

## Mesure sur le simulateur fourni

Mesure effectuée en mode normal, avec le simulateur sur le port 8766 et 149 codes dans l'API :

| Stratégie | Temps de récupération des photos | Photos reçues | Échecs |
|---|---:|---:|---:|
| Séquentielle | 63,17 s | 146 | 3 |
| Threads (8 maximum) | 10,08 s | 146 | 3 |
| asyncio (8 tâches maximum) | 12,77 s | 146 | 3 |

Le chronométrage des trois stratégies utilise les mêmes codes et exclut la pagination, qui est commune aux trois modes. Une mesure bout en bout de `snapshot_all("threads")`, pagination comprise, a pris **11,67 s** : 146 photos reçues et 3 échecs 504. Les 3 erreurs correspondent à des bornes hors ligne dans le simulateur. Les délais et stations hors ligne sont aléatoires ; ces mesures sont un relevé reproductible de cette exécution, pas une garantie de temps pour toutes les exécutions.

Les threads sont retenus pour la commande de photographie : ils ont été plus rapides que l'approche asyncio lors de cette mesure et satisfont le seuil de 15 secondes sur cette exécution.

## Comparaison des codes

Le CSV contient 150 codes distincts, en comptant les codes ambigus présents en double. L'API en publie 149.

- Référentiel absent de l'API : `MB-0013`, `MB-0047`, `MB-0105`.
- Présents dans l'API mais absents du référentiel : `MB-0151`, `MB-0152`.

## Reproduire les mesures

Depuis la racine du dépôt, lancer le simulateur fourni dans un terminal séparé :

```powershell
python ..\mobilis-kit\mobilis-kit\outils\serveur_bornes.py --port 8766
```

Puis lancer la comparaison en Python :

```powershell
python -c "from mobilis import MobilisApiClient; print(MobilisApiClient(base_url='http://127.0.0.1:8766').benchmark())"
```

Le mode threads de la bibliothèque borne la concurrence à huit appels. L'API reste accessible uniquement sur la machine locale et les tests automatisés la remplacent par des réponses simulées.
