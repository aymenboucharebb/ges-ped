# ges-ped — Gestion pédagogique ENSF (version 1.2.0 PILOTE)

La version web pilote est décrite dans **GUIDE_PILOTE.md** (utilisateurs) et **deploiement/DEMANDE_ADMINISTRATEUR_RESEAU.md** (serveur). Le lanceur Windows local ci-dessous reste disponible pour des essais sur un seul PC.


Version 1.1.0 • 25 septembre 2026 — enseignants ENSF interdépartementaux, fiches de vœux, espaces personnels

## Installer ou mettre à jour (le plus simple)

1. Fermer la fenêtre noire d’ENSF si elle est ouverte.
2. Double-cliquer sur **Setup_ENSF_Gestion_Pedagogique_1.1.0.exe** et laisser le dossier proposé (`Documents\ENSF_Gestion_Pedagogique`). Si votre version 1.0 est dans un autre dossier, choisir ce dossier : le programme est remplacé, **vos données (`data`) sont conservées**.
3. Lancer **ENSF Gestion pédagogique** depuis le Bureau. Au premier démarrage, la base est mise à jour automatiquement ; une copie de sécurité est d’abord créée dans `data\sauvegardes\avant-migration-v1.1-….sqlite`.

Sans installateur : extraire le ZIP par-dessus l’ancien dossier (le ZIP ne contient pas de base de données, il n’écrase donc rien dans `data`).

## Nouveautés 1.1

- **Un enseignant = une seule fiche ENSF**, un seul compte, une seule charge, un seul emploi du temps, même s’il intervient dans plusieurs départements. Le département administratif est facultatif et sans effet sur les affectations. Les doublons (même nom, même matricule ou même courriel) sont refusés.
- **Le département d’un enseignement est celui de la matière** (filière, ou matière si un département spécifique lui est donné dans Programmes → Matières). Un chef affecte à ses matières n’importe quel enseignant ENSF ou vacataire.
- **Charge globale** : sous-charge, charge atteinte, dépassement, demi-charge et charge annuelle sont calculés sur le total ENSF, avec la ventilation par département.
- **Emploi du temps** : les conflits enseignant, groupe, section et salle sont contrôlés sur toute l’ENSF.
- **Langue** : le programme officiel reste en français ; la langue réellement utilisée est choisie dans chaque affectation. Fiche enseignant : niveau d’anglais (informatif), possibilité déclarée d’enseigner en anglais, observation.
- **Taux d’anglais** = heures réglementaires affectées en anglais (affectations validées) / volume réglementaire total × 100, sans multiplication par les groupes ; par semestre, niveau, spécialité, filière, département, cycle, année / ENSF.
- **Campagnes et fiches de vœux** (module Vœux), traitement des vœux par le chef du département de la matière avec aide à la décision, création de l’affectation depuis un vœu accepté, affectation manuelle toujours possible, écran « Activités restant à affecter », traçabilité complète.
- **Rôles** : Administrateur, Direction / DAP, Chef de département (lié à son département), Enseignant (lié à sa fiche), Consultation. Les droits sont appliqués par le serveur : un enseignant ne reçoit jamais les données d’un collègue.
- **Espace enseignant** : Accueil, Mes vœux, Mes affectations, Mon emploi du temps, Ma charge, Mon profil (niveau d’anglais, mot de passe). Un chef de département lié à sa propre fiche enseignant dispose aussi de cet espace.
- **Nouveaux rapports** : fiches de vœux individuelles, synthèse des vœux par département, matières sans candidat, activités à plusieurs candidats, vœux acceptés / refusés, affectations issues des vœux / manuelles / par département / par enseignant, charge globale annuelle, ventilation par département, enseignants en anglais.

## Mise en place de la version 1.1 (à faire une fois)

1. **Structure → Départements** : créer vos départements. **Structure → Filières** : indiquer le département responsable de chaque filière. Si une matière relève d’un autre département que sa filière, l’indiquer dans **Programmes → Matières**.
2. **Paramètres → Utilisateurs** : créer un compte « Chef de département » par département, puis un compte « Enseignant » par enseignant (choisir sa fiche). Un chef qui enseigne peut aussi être lié à sa fiche.
3. **Vœux → Campagnes de vœux** : créer la campagne (semestre 1 = S1, S3, S5… ; semestre 2 = S2, S4…), dates d’ouverture et limite, puis passer le statut à « Ouverte ».
4. Les enseignants déposent leurs vœux ; chaque chef les traite dans **Vœux → Traitement des vœux**, puis crée les affectations, ou affecte manuellement depuis **Affectations → Activités restant à affecter**.

## Démarrer sur Windows (version portable)

## Démarrer sur Windows

1. Extraire complètement le ZIP dans un dossier conservé sur le PC, par exemple `Documents\ENSF_Gestion_Pedagogique`. Ne pas lancer depuis la fenêtre du ZIP.
2. Double-cliquer sur **Lancer_ENSF.cmd**. Le navigateur s’ouvre sur `http://127.0.0.1:8765`.
3. Au premier lancement, choisir un nom de connexion et un mot de passe d’au moins 10 caractères pour votre compte administrateur.
4. Garder la fenêtre du lanceur ouverte pendant l’utilisation. La fermer pour arrêter l’application. Pour revenir à l’application sans la relancer, ouvrir l’adresse ci-dessus.

Windows 10/11 64 bits, navigateur Edge ou Chrome conseillé. Python est inclus dans `runtime` ; Internet et droits administrateur ne sont pas nécessaires. Le script facultatif `Installer_Raccourci.ps1` crée un raccourci sur le Bureau. Vous pouvez aussi créer vous-même un raccourci vers `Lancer_ENSF.cmd`.

## Ce que contient cette version

- Les dix modules : Tableau de bord, Structure, Programmes, Enseignants, Vœux, Affectations, Emploi du temps, Suivi, Rapports, Paramètres, et l’espace personnel enseignant.
- 156 matières / activités sources, déclinées en 283 activités ; cycles, niveaux, spécialités, sections et groupes de référence.
- Création, recherche, filtres, modification et archivage des référentiels ; suppression des éléments non utilisés.
- Affectations manuelles, partage entre enseignants, contrôle de volume par public, validation, duplication contrôlée.
- Charges affectée, planifiée et réalisée, coefficients Cours / TD / TP et règles annuelles ; décisions de demi-charge obligatoires.
- Planning manuel, semaines personnalisées, contrôles de conflit, capacité, type de salle et indisponibilités ; génération des séances datées.
- Suivi des séances, réalisé partiel, annulation, rattrapage lié à sa séance d’origine.
- Rapports à l’écran, exports XLSX et impression / PDF par le navigateur, dont fiche individuelle avec signatures.
- Imports XLSX avec aperçu et validation, sauvegarde et restauration, cinq rôles, historique des modifications, clôture et duplication annuelle.

**Aucun enseignant réel, aucune salle réelle, aucune affectation ni séance ne sont préchargés.** Les captures utilisent une base d’essai séparée et peuvent montrer un enseignant fictif.

## Premier parcours conseillé

1. **Structure** : créer vos départements, rattacher les filières ; renseigner les effectifs, les salles et le premier dimanche de chaque semestre. La semaine ENSF va du dimanche au jeudi ; créneaux : 08:00–09:30, 09:30–11:00, 11:00–12:30, pause, 13:30–15:00, 15:00–16:30 (modifiables dans une nouvelle version des règles de charge).
2. **Enseignants** : saisir une seule fiche par personne (grade, statut, décisions, niveau d’anglais). Le département administratif est facultatif.
3. **Vœux** : ouvrir une campagne ; les enseignants formulent leurs vœux ; le chef du département de la matière les traite.
4. **Affectations** : depuis un vœu accepté ou manuellement, choisir activité, enseignant, public, heures et langue réellement utilisée. Enregistrer en brouillon puis passer à « Validée ». Les brouillons réservent le volume mais ne comptent pas dans la charge validée.
5. **Emploi du temps** : placer les affectations validées. `toutes`, `1-14` et `1,3,5` sont acceptés pour les semaines. Un conflit ou un dépassement bloque l’enregistrement avec son motif.
6. **Valider et générer les séances** : cette action crée les dates. Les séries générées sont verrouillées ; les adaptations ultérieures s’effectuent dans **Suivi**.
7. **Suivi** : ouvrir la séance, renseigner son statut et ses heures réalisées. Pour un rattrapage, ouvrir une séance annulée / partielle / à reprogrammer puis choisir « Programmer un rattrapage ». Le statut « Rattrapée » s’affiche lorsque le volume restant a été réalisé par ses remplacements.
8. **Rapports** : sélectionner un état et ses filtres. Pour une fiche individuelle, choisir l’enseignant et la période 1 ou 2. « PDF / Imprimer » ouvre la boîte d’impression : choisir « Enregistrer au format PDF » et le format paysage.

## Points pédagogiques à confirmer

La source fournie est le classeur réglementaire, pas les PDF signés des arrêtés. Les trois anomalies sources sont reprises dans le tableau de bord et Paramètres → Sources et décisions :

- Gestion des forêts S3 : somme TP 135 h, total imprimé 120 h.
- Santé des forêts S5 : somme TP 75 h, total imprimé 105 h.
- Mémoire complémentaire : travail individuel 80 h, total imprimé 35 h.

Les codes `REG-xxx` identifient les lignes du classeur, pas des codes officiels de matière. Lorsqu’un code d’UE est absent, l’UE est regroupée par type au sein du semestre et ce manque est noté.

Les langues, départements, enseignants, salles, effectifs et dates ne sont pas fournis. Le taux d’anglais indique les heures encore inconnues et reste provisoire tant que toutes les langues ne sont pas renseignées. Il utilise uniquement les activités réglementaires, sans multiplier par groupes.

La formation complémentaire est isolée dans un niveau / des blocs « rattachement à préciser ». Ses périodes de charge sont des valeurs de préparation à confirmer avant affectation. Les PFE sont conservés séparément et leur affectation est bloquée tant qu’aucune équivalence justifiée n’est renseignée. Sorties, CDE et Incubateur sont saisis séparément dans « Sorties et missions » avec les heures Eq. cours explicitement reconnues et une décision / un PV ; aucune équivalence CDE / Incubateur n’est inventée. La valeur indicative des sorties reste paramétrée (8 h TP).

## Importer un annuaire ou un référentiel

Exporter d’abord le référentiel concerné en Excel pour obtenir ses en-têtes. Remplacer les lignes par vos données dans une copie. Garder les intitulés des colonnes ; pour les références, reprendre les libellés complets des listes exportées (ou leurs identifiants si disponibles). Les dates doivent être du texte `AAAA-MM-JJ`, les heures `HH:MM`, les nombres de vraies valeurs numériques. Coller les valeurs, pas des formules.

L’import ajoute des fiches, sans remplacer les existantes. Il lit la première feuille, jusqu’à 2 000 lignes, détecte les erreurs et refuse la validation si une erreur subsiste. Importer les parents avant leurs enfants (départements, filières, niveaux, semestres, UE, matières, activités). Les modifications de fiches existantes s’effectuent depuis leur formulaire. Affectations, séances et comptes ne sont pas importables par Excel.

## Sauvegarder et restaurer

Dans **Paramètres → Sauvegarde**, télécharger une sauvegarde JSON ENSF puis la copier sur une clé USB ou un disque externe. Faire cette opération après une session importante et avant clôture annuelle ou mise à jour.

Pour restaurer : choisir la sauvegarde, vérifier l’aperçu puis saisir votre mot de passe administrateur. Les données pédagogiques sont remplacées dans une transaction. Une sauvegarde de l’état précédent est automatiquement créée dans `data\sauvegardes`. Les comptes et mots de passe du PC sont conservés, le journal sauvegardé est réintégré.

Pour une copie complète avec les comptes : **arrêter l’application**, puis copier tout le dossier, en particulier `data\ensf.sqlite`. Conserver ce dossier à l’abri des accès non autorisés. La sauvegarde pédagogique JSON ne contient pas les comptes. Il n’y a pas de sauvegarde automatique sur un service distant.

## Années, historique et droits

Les données sont propres à l’année sélectionnée en haut de l’écran. Dupliquer une année copie les référentiels, l’annuaire et leurs liens, mais aucune affectation, indisponibilité, mission ou séance. Les dates de semestre sont effacées dans la copie. Vérifier les règles, décisions individuelles et rattachements avant utilisation ; réattribuer aux chefs de département leur département de la nouvelle année dans les comptes.

La clôture rend toute l’année consultable uniquement. Effectuer une sauvegarde avant de la confirmer. Une fiche utilisée dans une opération protège ses caractéristiques pédagogiques ; une observation reste modifiable. Créer une nouvelle fiche ou retirer les dépendances quand cela est autorisé. Les données d’une année clôturée ne changent pas lors des modifications d’une autre année.

Administrateur : tous les modules et l’administration. Direction / DAP : gestion pédagogique globale et validation du planning. Chef de département : campagnes, vœux, affectations, groupes, emploi du temps et rapports des matières de son département, avec tout enseignant ENSF ; il voit la charge globale et les créneaux occupés des enseignants mais pas le détail des enseignements des autres départements, et ne peut pas les modifier. Enseignant : uniquement ses vœux, affectations, emploi du temps, charge et profil. Consultation : lecture et exports. Ces droits sont appliqués par le serveur (données transmises, exports, historique).

## Tests de réception

Utiliser de préférence une copie du dossier pour les essais.

1. Créer un enseignant permanent et un enseignant à demi-charge avec décision.
2. Fixer le calendrier et les effectifs d’un semestre ; créer une salle adaptée.
3. Affecter le Cours d’une matière en anglais et le TP en français ; vérifier le taux d’anglais (Rapports → Taux d’anglais).
3 bis. Affecter un même enseignant dans deux départements ; vérifier sa charge globale et le conflit d’horaire entre départements.
3 ter. Ouvrir une campagne, déposer des vœux avec un compte enseignant dans deux départements, les traiter avec chaque chef, créer une affectation depuis un vœu.
4. Répartir une activité entre deux enseignants sur le même public ; tenter un dépassement.
5. Placer des séances sur quelques semaines ; tenter un conflit de salle puis d’enseignant.
6. Générer les séances, en réaliser une partiellement, en annuler une puis créer son rattrapage.
7. Contrôler les trois charges, exporter une fiche individuelle Excel/PDF et vérifier les signatures.
8. Télécharger une sauvegarde, modifier une fiche et restaurer ; vérifier le retour à l’état sauvegardé.
9. Dupliquer une année et vérifier l’absence d’affectations dans la nouvelle année ; clôturer l’année d’essai.

`Tester.cmd` exécute les tests automatisés sur des bases temporaires, sans modifier votre base.

## Limites de cette livraison

Il s’agit d’une version fonctionnelle d’évaluation à valider sur vos cas réels avant adoption administrative. Tant que l’application fonctionne en mode local, les comptes enseignants et chefs s’utilisent sur ce PC ; l’accès depuis les postes des enseignants nécessite le futur mode réseau. Interface française uniquement. Pas d’import direct PROGRES, de planification automatique, de signature électronique, ni de calcul d’heures supplémentaires payables. Le planning représente les séries, et le suivi leurs dates ; pas de glisser-déposer ni de gestion automatique des vacances. Les indisponibilités permettent de bloquer les dates concernées.

Le serveur écoute uniquement sur ce PC. Le passage en réseau nécessite un serveur applicatif de production, HTTPS, une politique d’accès et des essais de concurrence ; ne pas exposer ce lanceur sur Internet. Le code sépare interface, service métier et stockage pour faciliter cette évolution. L’installateur fourni n’est pas signé numériquement : Windows peut afficher « Windows a protégé votre ordinateur » ; cliquer sur « Informations complémentaires » puis « Exécuter quand même ».

## Mise à jour et dépannage

Avant mise à jour, arrêter l’application et copier le dossier. Remplacer les fichiers du programme en conservant `data` ; ne jamais écraser `data\ensf.sqlite` avec la base initiale d’une autre archive. Les évolutions de structure sont appliquées par migrations numérotées (1 : version 1.0 ; 2 : version 1.1), avec copie de sécurité automatique de la base avant migration.

Si le navigateur ne s’ouvre pas, saisir `http://127.0.0.1:8765`. Si le port est occupé, vérifier si une autre fenêtre ENSF fonctionne déjà. Ne pas lancer deux instances sur la même base. Si le mot de passe administrateur est perdu, il n’y a pas de porte dérobée : restaurer une copie complète connue du dossier ou faire intervenir votre support avec votre autorisation.
