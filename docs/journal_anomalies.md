# Journal des anomalies

Les constats viennent du CSV brut fourni dans le kit. Le fichier source n'a pas été modifié. Le chargeur utilise `cp1252` et le séparateur `;`.

## Référentiel des stations

| Type | Nombre | Décision appliquée | Justification |
|---|---:|---|---|
| Codes dupliqués | 3 codes / 6 lignes concernées | Exclure les six lignes du référentiel fiable et signaler chaque ligne | Les versions ont des capacités, statuts ou dates différents ; on ne peut pas choisir arbitrairement laquelle représente la station actuelle. |
| Capacité absente (`NC`) | 2 lignes | Garder la station dans le rapport avec une capacité inconnue ; ne pas la compter comme exploitable | Sans capacité connue, les analyses d'offre ne sont pas fiables. |
| Coordonnées absentes | 1 ligne | Garder la station dans le rapport ; ne pas la compter comme exploitable | La localisation est nécessaire pour les analyses géographiques et la comparaison avec l'état des bornes. |
| Variantes de statut | 153 valeurs normalisées ; aucun statut inconnu | Convertir casse, espaces, accents et `_` en valeurs de l'Enum ; `HS` devient « hors service » | Les variantes représentent les mêmes statuts métier. Les stations fermées et hors service restent au référentiel, mais ne sont pas exploitables. |
| Formats de date | 2 formats reconnus | Lire `JJ/MM/AAAA` et `AAAA-MM-JJ` | Les deux formats présents sont valides et deviennent des objets `date`. |

### Résultat reproductible

- Lignes de données lues : **153**.
- Codes dupliqués : **3** (`MB-0033`, `MB-0068`, `MB-0104`), soit **6 lignes** exclues.
- Stations gardées dans le rapport : **147**.
- Anomalies signalées : **9** (6 lignes de doublons, 2 capacités inconnues, 1 station sans coordonnées).
- Stations exploitables : **138**.

Une station est considérée exploitable si son statut normalisé est « en service », sa capacité est connue et positive, et ses coordonnées sont présentes et dans les limites géographiques. La date de mise en service n'est pas un critère d'exploitabilité.
