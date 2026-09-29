# Conception et traçabilité

## Décisions retenues

Projet neuf, indépendant de v0.3.1 : aucune lecture ou reprise de son code, aucune importation de ses données. La demande actuelle prévaut sur le cahier des charges de phase 1 pour inclure affectations, emploi du temps et suivi.

Application locale Python 3.12 standard + SQLite + interface HTML/CSS/JavaScript. Aucune bibliothèque téléchargée ou ressource Internet nécessaire à l’exécution. Le runtime Windows fourni provient du Python embarqué disponible dans l’environnement de développement ; sa licence est incluse. Le paquet a été exécuté sur le PC de préparation, pas sur un parc indépendant de machines Windows.

`schema.py` décrit les données éditables et les formulaires. `domain.py` porte validations et calculs. `database.py` gère SQLite, initialisation et historique. `server.py` fournit l’API HTTP locale et les contrôles d’accès. `excel.py` assure des échanges XLSX simples. `static` contient l’interface. Les transactions SQLite protègent les écritures et la restauration ; `links` impose les références par clés étrangères. Les fiches sont stockées par type et année avec JSON contrôlé, relations explicites, révision optimiste et journal avant/après. Ce schéma flexible requiert le service métier pour ses validations sémantiques.

Toutes les données de référence sont copiées par année. Les règles ont des versions immuables, une seule active par année. Les changements de coefficients d’activité déjà utilisés sont bloqués. Une nouvelle règle active recalcule les cibles de l’année encore ouverte ; les valeurs précédentes restent au journal. La clôture verrouille l’année.

Authentification par mot de passe haché PBKDF2-SHA256 (310 000 itérations), cookies HttpOnly/SameSite, protection CSRF et contrôle de l’hôte local. Aucun compte précréé dans la base livrée. Les rôles sont contrôlés côté serveur. La cible reste un poste local ; le serveur HTTP standard n’est pas un déploiement réseau de production.

## Benchmark ciblé consulté le 25/09/2026

| Repère | Idée retenue pour ENSF | Source primaire |
|---|---|---|
| PROGRES | Relier offres de formation, charges et suivi ; aucun couplage technique supposé | [Présentation officielle MESRS](https://www.mesrs.dz/fr/progres/), [Documentation et tutoriels universitaires](https://www.univ-biskra.dz/index.php/fr/58-rectorat/2011-progres) |
| Ellucian Student | Visibilité du programme et des données académiques dans un même espace | [Présentation officielle](https://www.ellucian.com/en-ae/products/student) |
| Ellucian / TimeEdit | Relier le programme aux ressources, aux charges et à la planification | [Timetabling and curriculum planning](https://www.ellucian.com/en-gb/blog/timetabling-and-curriculum-planning-uk-higher-ed) |
| TimeEdit | Séparer curriculum, workload, planning manuel, calendrier publié et reporting ; saisir des semaines explicites | [Catalogue produit](https://www.academy.timeedit.com/products), [Guides officiels](https://timeedit.com/guides-tutorials), [Correction de planification par semaines](https://www.academy.timeedit.com/product-updates/211585741) |

Usage institutionnel illustré par les témoignages de [Western Norway University of Applied Sciences et Frankfurt School](https://timeedit.com/platform/workload), de [Vrije Universiteit Amsterdam et University of Central Lancashire](https://timeedit.com/platform/curriculum), et par le [cas Ellucian de National Louis University](https://www.ellucian.com/customer-stories/boosting-efficiency-shedding-manual-tasks). Les chiffres commerciaux ne servent pas à classer les produits.

Il s’agit d’un benchmark documentaire ciblé, sans accès aux installations privées ni essai de leurs produits. Aucun classement exhaustif des « meilleurs » logiciels n’est revendiqué. Les idées ci-dessus sont adaptées au besoin ENSF ; aucune interface propriétaire n’est reproduite.

## Sources ENSF

Le dossier fourni est conservé séparément dans l’espace de travail. Le fichier `references/source.json` contient l’extraction intégrale des feuilles du classeur réglementaire, y compris sources, contrôles, anomalies et modèle de fiche vierge. Le classeur original est également inclus dans `references` pour consultation.

Initialisation : 156 matières/lignes sources, 283 activités dont Cours/TD/TP et activités PFE, 83 UE, 22 semestres/blocs, 10 niveaux/blocs, 25 sections/groupes, 2 cycles, 2 filières et 3 spécialités. Les 5 625 h réglementaires proviennent des lignes, sans groupes ; formation complémentaire et PFE sont distincts.

Décret n°24-103 : [JORADP n°18 du 13/03/2024, page 9](https://www.joradp.dz/FTP/jo-francais/2024/F2024018.pdf). Le texte consulté confirme 192 h annuelles de cours, 288 h de TD/TP et le minimum de 13 semaines. Les valeurs 96/48 h par semestre et 14 semaines sont les paramètres internes fournis par l’ENSF. Cette vérification ciblée n’est pas une certification de l’ensemble du droit applicable ni de l’absence de modifications ultérieures.

Les écarts des arrêtés sont conservés tels que décrits dans le classeur. Le système n’arbitre pas la valeur officielle. La validation administrative des anomalies, des règles internes, du calendrier et de la formation complémentaire reste nécessaire.

## Évolutions 1.1 (enseignants interdépartementaux et vœux)

- Identité enseignant : champ technique `person` stable d’une année à l’autre ; un compte utilisateur est lié à cette identité (index unique). Le département administratif n’intervient plus dans les droits ni dans les affectations.
- Département propriétaire d’un enseignement : département de la matière, sinon de sa filière. Les droits du chef, les rapports départementaux et le filtrage des données s’appuient sur ce seul critère.
- Filtrage des données côté serveur (`domain.visible`, `domain.scoped_summary`) pour l’amorçage, les exports et l’historique ; contrôles d’écriture par capacité (`domain.permission`), y compris pour un chef qui est aussi enseignant.
- Langue : supprimée de l’activité (valeur 1.0 conservée en observation), portée par l’affectation. Taux d’anglais par activité = moyenne sur ses publics des heures validées en anglais (bornées au volume), agrégé sur le volume réglementaire.
- Nouveaux objets : campagne de vœux (période, département facultatif, dates, statut) et vœu (priorité, langue souhaitée, décision, dates et auteur de décision, historique complet dans le journal).
- Migration n° 2 : ajout du lien compte-enseignant, identités, niveaux d’anglais par défaut ; copie SQLite de sécurité préalable.
