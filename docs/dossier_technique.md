# Dossier technique Mobilis

## Page 1

 Mobilis
 Dossier technique du projet final
 Conception, anomalies, resultats et verifications
 Equipe: Awa Bouare et Hadile Issilame
 Version de travail - 24 novembre 2026
 Depot: github.com/awa78/mobilis
Les bilans personnels restent a completer et a valider par les deux membres.

## Page 2

Presentation et perimetre
Mobilis est une bibliotheque Python destinee a produire des resultats reproductibles a partir des exports du reseau de
velos. Le projet reunit cinq cas: referentiel des stations, frequentation en flux, facturation, etat temps reel et livraison
installable.
Le depot utilise une structure src/, un pyproject.toml, une interface de commande et une suite de tests. Les donnees
brutes du kit ne sont pas versionnees. Les resultats de ce dossier ont ete obtenus a partir des donnees synthetiques
fournies par l'enseignant.
equipe: Awa Bouare et Hadile Issilame. Le travail est organise en branches et en demandes de fusion relues. Ce dossier
decrit la conception, les controles, les chiffres mesures et les limites connues. Les bilans personnels seront completes et
valides par chaque membre.
 - Besoin: disposer d'un seul traitement fiable au lieu de scripts d'analyse divergents.
 - Langage et version minimale: Python 3.11.
 - Date des mesures presentees: 24 novembre 2026.

## Page 3

Besoins et criteres de reussite
Le projet transforme des questions operationnelles en traitements verifiables. Une station doit etre declaree exploitable
seulement si ses donnees essentielles sont coherentes. Le trafic doit pouvoir etre analyse sans charger le fichier complet
en memoire. Une facture doit suivre les regles commerciales et etre explicable. L'API des bornes doit repondre dans le
delai demande malgre sa lenteur.
Le livrable logiciel doit s'installer avec pip install -e .[dev], exposer les commandes mobilis, contenir au moins quinze
tests dont des exemples parametres et des mocks, et passer pytest, mypy strict et Ruff. Une integration continue doit
relancer ces controles. Le dossier technique doit rendre les decisions et les resultats reproductibles.
La qualite ne se resume pas au nombre de fonctionnalites: les erreurs de donnees doivent etre detectees, comptees et
traitees selon une decision ecrite. Les chiffres doivent pouvoir etre recalcules avec les fichiers du kit et une commande
documentee.
 - Cas 1: combien de stations sont exploitables et pourquoi les autres posent probleme?
 - Cas 2: quelles stations se vident et se remplissent; quel est le profil horaire par jour?
 - Cas 3: quelles recettes par mois et par formule; quel effet a la grille d'octobre?
 - Cas 4: la photo reseau est-elle complete en moins de 15 secondes et coherente avec le referentiel?
 - Cas 5: l'equipe peut-elle installer, tester et relancer les chiffres seule?

## Page 4

Architecture de la bibliotheque
Le paquet separe les domaines pour garder chaque traitement comprehensible. Le module stations valide et normalise
les lignes du CSV historique. Le module trajets lit le fichier compresse, convertit les dates, dedoublonne et agrege. Le
module facturation applique les grilles, les abonnements et les exceptions. Le client temps reel isole les appels HTTP, les
retries et la concurrence.
Les commandes de console orchestrent ces modules et affichent les rapports. Elles prennent les chemins de donnees en
options ou via les variables d'environnement. Les scripts d'anomalies et de benchmark restent utiles pour produire les
mesures du Cas 2.
Entree
Traitement
Sortie
stations.csv
Station immuable, Enum, validation
rapport d'anomalies et stations exploitables
trajets CSV gzip
lecture en flux, dates, SQLite, agregats
profils, flux nets, memoire mesuree
tarifs, abonnes, stations, trajets
Decimal, regles R1-R12, plafonds
factures et recettes mensuelles
API paginee
retry, threads ou asyncio, maximum 8
photo et comparaison au referentiel

## Page 5

Donnees et regles d'anomalies
Le kit contient un CSV de stations issu d'un ancien outil Windows, un fichier gzip de trajets d'environ 155 000 lignes, des
abonnements JSON Lines comprenant des enregistrements abemes, un JSON de tarifs et un simulateur HTTP. Le code
n'altere jamais ces fichiers a la main.
Chaque anomalie a un type, un nombre, une decision et une justification. Les doublons de trajets ne contribuent qu'une
fois. Une distance invalide n'empeche pas de compter un trajet pour le profil horaire. Une fin manquante laisse le depart
exploitable. En facturation, une arrivee absente suit la regle de penalite R9.
Les identifiants d'abonnes illisibles ne peuvent pas etre repares sans preuve. Le moteur ignore et compte les
enregistrements malformes; un trajet sans abonnement actif est tarife occasionnellement selon R3. Le journal des
anomalies conserve les nombres mesures et les decisions.
 - CSV stations: separateur point-virgule, encodage CP1252.
 - Dates des trajets: ISO avec fuseau, ISO Z et JJ/MM/AAAA HH:MM:SS.
 - Fuseau d'analyse et jour de facturation: Europe/Paris.
 - Les donnees du kit restent hors du depot Git.

## Page 6

Cas 1 - referentiel des stations
Le modele Station est une dataclass immuable. Le statut est une Enum normalisee pour absorber les differences de
casse, d'espaces, d'accents et de synonymes. Le chargeur lit le CSV historique en CP1252 et accumule un rapport au
lieu d'arreter la lecture a la premiere ligne incorrecte.
Les codes dupliques sont exclus du referentiel fiable parce que les lignes peuvent decrire des capacites, statuts ou dates
differents. Les stations incompletes restent visibles dans le rapport mais ne sont pas declarees exploitables. Le critere
d'exploitabilite exige un statut en service, une capacite positive connue et des coordonnees valides.
Sur 153 lignes de donnees, 147 stations restent dans le rapport apres exclusion des six lignes impliquees dans trois
doublons. Neuf anomalies sont signalees. Le resultat reproductible est de 138 stations exploitables.
Constat
Nombre
Decision
Codes dupliques
3 codes / 6 lignes
exclure les lignes ambigues
Capacite inconnue
2 lignes
conserver, non exploitable
Coordonnees absentes
1 ligne
conserver, non exploitable
Stations exploitables
138
statut actif, capacite et coordonnees valides

## Page 7

Cas 2 - pipeline en flux
Le pipeline compose la lecture gzip, la conversion des dates, le dedoublonnage, un filtre facultatif et l'agregation. Chaque
ligne est traitee sans charger tout le CSV en memoire. Les dates sans fuseau sont interpretees en heure locale de Paris;
les dates avec fuseau sont converties en instants UTC avant l'analyse locale.
Le dedoublonnage utilise un index SQLite temporaire sur disque avec un cache plafonne, plutet qu'un set Python
contenant chaque identifiant. Les compteurs d'agregation sont bornes par le nombre de stations et de creneaux horaires.
La generation du fichier de benchmark relit la source progressivement cent fois.
Les stations qui se vident le matin sont triees par departs moins arrivees dans la fenetre du matin. Les stations qui se
remplissent le soir sont triees par arrivees moins departs dans la fenetre du soir. Les profils semaine et week-end sont
calcules sur l'heure locale.
 - Les dates invalides sont comptees et deviennent None; le flux continue.
 - Les doublons sont retires avant l'agregation.
 - Le filtre est un predicat composable qui n'impose pas de liste intermediaire.
 - La memoire Python est relevee avec tracemalloc pendant l'analyse.

## Page 8

Cas 2 - resultats et anomalies
Sur le fichier du kit, le pipeline garde 155 011 trajets uniques et cumule 703 139 254 metres de distance valide. Le pic
Python mesure sur la source reelle est de 2,48 Mio.
Le benchmark 100x a genere 15 563 100 lignes dans un fichier temporaire compresse de 336,87 Mio. Le pipeline a traite
15 501 100 trajets uniques en 844,74 secondes. Le pic Python est reste a 3,01 Mio; la generation du fichier a pris 150,95
secondes.
Les anomalies sont comptees et traitees selon leur usage. Les doublons sont ignores; une distance invalide n'empeche
pas de compter les departs; les trajets sans fin ou station d'arrivee restent signales.
Mesure
Valeur
Trajets uniques - source
155 011
Trajets uniques - benchmark 100x
15 501 100
Pic Python - source / benchmark
2,48 / 3,01 Mio
Creation du fichier / analyse 100x
150,95 / 844,74 s
Anomalies - doublons
620
Distances invalides / fin manquante / arrivee absente
4 676 / 78 / 78
- L'index des identifiants est conserve dans un fichier SQLite temporaire avec cache plafonne.
- Le fichier de benchmark est supprime automatiquement a la fin.

## Page 9

Cas 3 - moteur de facturation
Le moteur represente les tarifs, grilles, abonnements et resultats par dataclasses. Un Protocol definit le contrat de
tarification et deux implementations appliquent la meme formule Decimal, ce qui rend le calcul remplaeable et testable.
Les montants ne passent jamais par float.
La date locale de depart choisit la grille R1 et l'abonnement actif R2. Les tranches entamees, supplements electriques,
plafonds journaliers et arrondis R4-R7 sont appliques en Decimal. Les cas particuliers R8-R12 couvrent les trajets
fantemes, non-restitutions, horodatages incoherents, doublons et stations inconnues.
Le chargeur ignore et compte les six lignes JSON malformees du fichier abonnes.jsonl. Il lit le CSV stations en CP1252.
Le fichier contient egalement trois lignes vides, qui ne sont pas considerees comme des abonnements. Les 5 254
enregistrements valides sont charges.
 - R8: trajet de moins de deux minutes avec retour a la station de depart - 0 EUR.
 - R9: arrivee sans station ou heure, ou duree au-dele du seuil - penalite forfaitaire hors plafond.
 - R10: fin anterieure au debut - non facture et signale.
 - R11: un seul montant par identifiant de trajet.
 - R12: station inconnue - trajet facture et anomalie signalee.

## Page 10

Cas 3 - exemples valides E1 a E6
Les six exemples de la direction commerciale sont couverts par des tests automatises. Les regles complementaires sont
couvertes par des tests des limites de tranches, des renouvellements, des plafonds, des dates incoherentes, des
doublons et des stations inconnues.
L'exemple E6 verifie le passage a l'heure d'hiver: les deux horodatages locaux semblent inverses, mais les instants
indiquent une duree reelle de trente minutes. Le moteur soustrait les instants UTC, puis determine le jour de facturation
en Europe/Paris.
Les deux politiques de tarification sont testees avec les memes entrees, afin de verifier qu'elles respectent le contrat et
rendent le meme montant defini par les regles.
Exemple
Situation
Montant attendu
E1
abonne annuel, mecanique, 25 min
0,00 EUR
E2
abonne annuel, electrique, 25 min
0,50 EUR
E3
abonne mensuel, mecanique, 61 min
2,00 EUR
E4
occasionnel electrique, 20 min en octobre
3,70 EUR
E5
trois trajets annuels de 3 h le meme jour
12,00 EUR total
E6
retour au changement d'heure d'hiver
0,00 EUR; 30 min

## Page 11

Cas 3 - recettes mensuelles et effet d'octobre
La commande facturation regroupe les montants par mois local et formule. Pour isoler l'effet de la grille entree en vigueur
le 1er octobre, elle recalcule les memes trajets, abonnements et evenements avec la grille precedente. La difference
mesure ainsi l'effet du tarif, sans le confondre avec une evolution du nombre de trajets.
Les montants suivants ont ete recalcules avec les fichiers du kit. Les trajets sans date de depart ne peuvent etre affectes
a un mois; les resultats non factures sont exclus des recettes. Les penalites R9 restent incluses dans les montants
factures.
Mois
Annuel
Mensuel
Occasionnel
Solidaire
Total
Aout
12 295,00
4 353,00
46 748,80
533,25
63 930,05
Septembre
18 025,50
6 459,00
68 334,00
852,00
93 670,50
Octobre
17 990,20
6 617,40
70 070,85
725,25
95 403,70
- Octobre avec l'ancienne grille: 79 031,25 EUR.
 - Octobre avec la nouvelle grille: 95 403,70 EUR.
 - Effet attribuable au changement de grille a trajets identiques: +16 372,45 EUR.

## Page 12

Cas 4 - etat temps reel
Le client API recupere les codes de station par pagination, puis demande les photos des bornes. Un decorateur
reutilisable applique les nouvelles tentatives pour les reponses 429, 503 et 504, en respectant Retry-After lorsqu'il est
fourni. Les echecs persistants sont retournes dans un rapport au lieu de faire echouer toute la photographie.
Les strategies sequentielle, threads et asyncio sont mesurees sur les memes codes. Pour les appels en parallele, le
nombre de requetes simultanees est limite a huit, comme demande par le simulateur. L'approche retenue par defaut est
threads, car elle a ete la plus rapide sur la mesure documentee.
La comparaison du referentiel et de l'API distingue les codes absents de l'API et les codes inconnus du referentiel. Le
rapport presente les stations vides, pleines et les bornes injoignables.
 - Retry sur 429, 503 et 504; delai Retry-After pris en compte.
 - Limite stricte: huit appels simultanes au maximum.
 - Tests HTTP simules: les tests ne lancent pas le serveur.
 - Le benchmark mesure les trois strategies avec les memes entrees.

## Page 13

Cas 4 - mesures de performance
La mesure a ete faite sur le simulateur fourni, en mode normal, avec 149 codes publies par l'API. Les temps indiques
pour les trois strategies couvrent la recuperation des photos et excluent la pagination, commune aux trois approches.
Les threads terminent en 10,08 secondes pour 146 photos reeues et trois echecs 504. L'approche asyncio termine en
12,77 secondes avec les memes resultats. Le mode sequentiel prend 63,17 secondes. Une mesure de bout en bout en
threads, pagination comprise, prend 11,67 secondes.
Les 3 bornes en echec sont hors ligne dans le simulateur. Les delais et indisponibilites sont aleatoires; ces resultats
decrivent une execution observee et ne sont pas une garantie pour toutes les executions.
Strategie
Temps photos
Photos reeues
echecs
Sequentielle
63,17 s
146
3
Threads, maximum 8
10,08 s
146
3
asyncio, maximum 8
12,77 s
146
3
Threads bout en bout
11,67 s
146
3

## Page 14

Livraison et commandes installables
Le paquet s'installe en mode editable avec une seule commande pip. La commande mobilis propose quatre
sous-commandes: stations, frequentation, facturation et etat. Elles couvrent les cinq cas du projet, certains rapports
partageant une meme commande. Les chemins peuvent etre donnes en options ou par variables d'environnement;
MOBILIS_DATA_DIR fournit les noms de fichiers par defaut.
Les fichiers du kit ne sont pas inclus dans le depot. Le README explique l'installation, le lancement des commandes et
le demarrage du simulateur API. Les docstrings decrivent les interfaces publiques et les decisions principales sont
documentees dans le journal d'anomalies.
Une workflow GitHub Actions execute pytest, mypy strict, Ruff lint et Ruff format sur Python 3.11 et 3.14 lors d'un push
ou d'une pull request. Le statut distant de la workflow devra etre confirme apres publication de la branche et creation de
la demande de fusion.
 - Installation: python -m pip install -e ".[dev]".
 - Donnees privees du cours: non versionnees.
 - Secrets de l'API: options ou variables d'environnement; aucune cle reelle n'est enregistree.

## Page 15

Qualite logicielle et strategie de tests
La suite couvre les validations de stations, le client API, les commandes, les generateurs de trajets et les regles de
facturation. Les tests incluent les six exemples commerciaux, plusieurs cas limites, le mock HTTP et les deux strategies
de tarification.
Les controles locaux realises sur la branche de travail passent: pytest, mypy --strict, ruff check et ruff format --check. Au
dernier releve, 75 tests passent; le nombre final sera celui du rapport de CI apres les derniers changements.
L'integration provisoire des deux contributions a ete realisee sans conflit et la suite reunie a passe 66 tests avant les
dernieres corrections. Les tests ne dependent pas du serveur API ni d'un acces reseau. Les controles automatiques
nouvellement configures devront etre observes sur GitHub une fois la branche publiee.
 - Typage strict sur les modules Python du paquet.
 - Formatage deterministe par Ruff.
 - Tests des regles de prix et des erreurs de donnees.
 - Mesures de memoire avec tracemalloc.

## Page 16

Reproduction des chiffres
Les commandes suivantes partent de la racine du depot, apres installation du paquet et extraction du kit voisin. Elles
reproduisent le rapport des stations, la frequentation et les anomalies, la facturation mensuelle et l'effet d'octobre, puis
l'etat temps reel.
Le dossier est une photographie du resultat de l'equipe. Les donnees synthetiques peuvent evoluer si le kit change; la
commande, le fichier source et les regles doivent donc etre conserves avec chaque nouvelle mesure.
 - Pour etat, demarrer d'abord outils/serveur_bornes.py dans un autre terminal.
 - Les commandes facturation et frequentation peuvent utiliser MOBILIS_DATA_DIR.
 python -m pip install -e ".[dev]"
mobilis stations --stations CHEMIN/stations.csv
mobilis frequentation --trajets CHEMIN/trajets_2026-08_2026-10.csv.gz
mobilis facturation --trajets CHEMIN/trajets_2026-08_2026-10.csv.gz --tarifs CHEMIN/tarifs.json --abonnes
CHEMIN/abonnes.jsonl --stations CHEMIN/stations.csv
python scripts/benchmark_trajets.py --trajets CHEMIN/trajets_2026-08_2026-10.csv.gz
pytest -q && mypy --strict src/mobilis && ruff check src tests scripts

## Page 17

Organisation Git et bilans individuels
L'historique distingue les apports. Hadile a créé la lecture et l'analyse initiales des trajets, puis le moteur de facturation et
des tests des règles. Awa a développé le référentiel des stations, l'état temps réel et les premières commandes; elle a
ensuite corrigé et documenté le pipeline des trajets et les rapports de facturation.
Les commits sont attribués à leurs auteurs et les branches de travail ont été intégrées dans awa/corrections-cas2-cas3.
Cette branche est publiée. Une demande de fusion avec relecture par un pair reste à créer : l'historique montre les
contributions, mais la relecture n'est pas encore prouvée.
Une proposition de bilan général et deux brouillons individuels sont présentés page 19. Ils s'appuient sur les corrections
et l'historique Git; chaque membre doit les relire, corriger les éléments personnels et confirmer qu'ils décrivent bien son
expérience.

## Page 18

Limites et suites proposees
Les abonnements malformés ne peuvent pas être reconstitués sans preuve. Ils sont comptés et ignorés; lorsqu'un
abonnement n'est pas retrouvé, le tarif occasionnel est appliqué selon R3.
tracemalloc mesure la mémoire Python suivie, pas la mémoire native du système ou de SQLite. Sur une entrée cent fois
plus grande, le pic suivi passe de 2,48 à 3,01 Mio. La mesure API est sous 15 secondes sur l'exécution décrite, mais trois
stations ont répondu en erreur.
Les bilans individuels sont maintenant proposés page 19 et doivent être validés par Awa et Hadile. Le statut de la CI
distante, la relecture de la demande de fusion et l'installation sur une machine propre restent à confirmer.
Suite
État
Benchmark 100x
Mesuré; pic Python 3,01 Mio
CI GitHub
À confirmer sur GitHub
Brouillons des bilans
À relire par chaque membre
Demande de fusion
À créer et faire relire

## Page 19

Bilan général et bilans individuels
Bilan général du projet
Le projet a transformé les cinq questions de Mobilis en une bibliothèque Python installable. Le travail sur les données a
révélé plusieurs difficultés concrètes : encodages anciens, formats de dates différents, trajets non triés ou en double,
champs incomplets et abonnements malformés. Les choix de traitement ont été documentés et couverts par des tests.
La facturation utilise Decimal et les règles du kit; l'analyse des trajets fonctionne en flux, et le client temps réel gère
pagination, limites de concurrence et erreurs temporaires.
La suite locale passe 75 tests, mypy strict et Ruff. Le benchmark 100x traite 15 501 100 trajets uniques avec un pic
tracemalloc de 3,01 Mio. La mesure de l'API est sous 15 secondes, mais inclut trois bornes en échec; le résultat ne
signifie donc pas que toutes les stations ont répondu. Les suites prioritaires sont la relecture par un pair, la vérification de
la CI distante, un essai d'installation sur une machine propre et la préparation de la soutenance.
Brouillon individuel - Awa (à relire et personnaliser)
Dans ce projet, j'ai contribué au référentiel des stations, au client de l'API temps réel et aux commandes. J'ai aussi
travaillé sur les corrections du pipeline de trajets et sur les résultats de facturation. Une difficulté importante a été de
traiter des données réelles imparfaites sans les modifier à la main : dates de formats différents, identifiants dupliqués et
champs manquants. J'ai appris à rendre les traitements plus robustes, à vérifier les choix par des tests et à mesurer la
mémoire sur un fichier beaucoup plus gros. Je suis particulièrement satisfaite que les anomalies et les limites soient
visibles dans les rapports. Pour améliorer ma contribution, je voudrais encore faire relire les changements et vérifier
l'installation et les commandes sur une machine propre.
Brouillon individuel - Hadile (à relire et personnaliser)
Dans ce projet, j'ai contribué à la lecture et à l'analyse des trajets, puis à la facturation et aux tests des règles tarifaires.
La difficulté a été de faire fonctionner ces traitements malgré les données incomplètes et les règles qui se combinent,
tout en gardant des résultats explicables. Ce travail m'a permis de pratiquer les générateurs pour lire les trajets en flux, la
séparation des politiques tarifaires et les tests de cas limites. Je retiens surtout l'importance de tester les règles avec des
exemples précis et de simplifier le code après une première version. Pour la suite, je voudrais participer à la relecture de
la demande de fusion et vérifier avec l'équipe que les choix et les chiffres du dossier sont faciles à reproduire.
Ces deux textes sont des propositions fondées sur l'historique Git et les problèmes traités. Awa et Hadile doivent corriger toute phrase
qui ne décrit pas leur expérience réelle avant le rendu.
