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

## Cas 2 - trajets

Comptages obtenus avec `scripts/anomalies_trajets.py --trajets CHEMIN_TRAJETS` sur le fichier du kit. Le fichier source contient 155 631 lignes de trajets. Le pipeline garde 155 011 trajets uniques.

| Type | Nombre | Decision | Justification |
|---|---:|---|---|
| Identifiants de trajet dupliques | 620 | Garder la premiere occurrence et ignorer les suivantes | Le meme trajet ne doit contribuer qu'une fois aux profils et aux agregats. |
| Distance absente ou invalide | 4 676 | Garder le trajet et ne pas ajouter sa distance au total | La distance n'est pas necessaire pour compter les departs, les arrivees ou la frequentation horaire. |
| Heure de fin manquante | 78 | Garder le trajet; l'heure de debut reste utilisable pour les profils | Une fin manquante n'empeche pas d'analyser le depart. |
| Station d'arrivee manquante | 78 | Garder le trajet et le signaler | Il reste utile pour compter les departs; la facturation applique la regle de non-restitution. |

Le rapport compte 5 452 anomalies sur les lignes uniques et les doublons. Les profils horaires et les flux sont calcules en heure locale de Paris. Les stations qui se vident ou se remplissent sont classees par flux net.

## Cas 3 - abonnements et facturation

Le fichier `abonnes.jsonl` contient 5 263 lignes physiques, dont 3 lignes vides ignorees, 5 254 abonnements valides et 6 enregistrements JSON malformes. Les six lignes invalides sont ignorees et comptees sous `abonnement_malforme`; les trajets dont l'abonnement ne peut pas etre retrouve utilisent le tarif occasionnel, conformement a R3.

Le fichier stations du kit est decode en CP1252. La facturation des trajets incomplets applique la penalite R9 quand l'heure ou la station d'arrivee manque. Les trajets de moins de deux minutes avec retour a la station de depart sont exclus de la facturation selon R8. Les trajets aux horodatages incoherents sont non factures selon R10.

### Resultats reproductibles sur les donnees du kit

Commande: `mobilis facturation --trajets CHEMIN_TRAJETS --tarifs CHEMIN_TARIFS --abonnes CHEMIN_ABONNES --stations CHEMIN_STATIONS`.

| Mois 2026 | Annuel | Mensuel | Occasionnel | Solidaire | Total |
|---|---:|---:|---:|---:|---:|
| Aout | 12 295,00 EUR | 4 353,00 EUR | 46 748,80 EUR | 533,25 EUR | 63 930,05 EUR |
| Septembre | 18 025,50 EUR | 6 459,00 EUR | 68 334,00 EUR | 852,00 EUR | 93 670,50 EUR |
| Octobre | 17 990,20 EUR | 6 617,40 EUR | 70 070,85 EUR | 725,25 EUR | 95 403,70 EUR |

Pour isoler l'effet de la nouvelle grille, octobre a ete recalcule sur les memes trajets, avec les abonnements et les regles identiques, en remplacant uniquement la grille d'octobre par celle de septembre. L'ancienne grille aurait produit 79 031,25 EUR; la nouvelle produit 95 403,70 EUR, soit un effet de +16 372,45 EUR. Cette comparaison neutralise la variation du nombre et du type de trajets entre septembre et octobre.
## Cas 2 - mesure sur le fichier 100 fois plus gros

Le script scripts/benchmark_trajets.py --trajets CHEMIN_TRAJETS a genere 15 563 100 lignes dans un fichier gzip temporaire de 336,87 Mio. Le pipeline a analyse 15 501 100 trajets uniques.

| Etape | Temps | Pic memoire Python |
|---|---:|---:|
| Generation du fichier 100x | 150,95 s | hors mesure pipeline |
| Analyse des trajets 100x | 844,74 s | 3,01 Mio |

Le fichier temporaire est supprime a la fin du benchmark. La memoire Python suivie passe de 2,48 Mio sur la source a 3,01 Mio sur une entree cent fois plus grande. L'index des identifiants est stocke sur disque SQLite temporaire avec cache plafonne; la memoire reste quasi constante par rapport au nombre de lignes.
