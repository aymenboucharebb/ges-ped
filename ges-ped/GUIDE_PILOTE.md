# ges-ped PILOTE — Guide du responsable

**Adresse du pilote :** https://pilote.ges-ped.hnsf.dz (active une fois le serveur installé, voir `deploiement/DEMANDE_ADMINISTRATEUR_RESEAU.md`)
**Version :** ges-ped 1.2.0 PILOTE
**Vos utilisateurs n’installent rien :** Chrome, Edge ou Firefox suffit.

## 1. Première connexion (vous)
1. Ouvrir le lien, puis saisir l’identifiant **admin** et le mot de passe temporaire remis par l’administrateur réseau.
2. Choisir votre mot de passe personnel (10 caractères minimum).
3. Si vous aviez déjà saisi des données dans la version locale : dans votre version locale, **Paramètres → Sauvegarde → Télécharger** ; puis sur le pilote, **Paramètres → Sauvegarde → Restaurer**.
4. **Structure → Départements** : créer les deux départements. **Structure → Filières** : indiquer le département de chaque filière.
5. **Enseignants** : une seule fiche par personne, rattachement administratif facultatif.
6. **Structure → Semestres** : indiquer le premier **dimanche** de chaque semestre. La semaine va du dimanche au jeudi, avec les créneaux 08:00–09:30, 09:30–11:00, 11:00–12:30, pause, 13:30–15:00 et 15:00–16:30.

## 2. Créer les comptes
**Paramètres → Comptes utilisateurs**
- **+ Compte chef de département** : choisir le département, saisir « Prénom Nom ». L’identifiant est proposé automatiquement (ex. `k.benali`) et reste modifiable. Si le chef enseigne aussi, associez-lui sa fiche enseignant.
- **Enseignants** : dans « Enseignants sans compte », cliquer sur **Créer le compte**. L’identifiant proposé suit la règle prénom + nom (`n.laouar`, `e.bensalah` ; en cas de doublon : `m.benali2`).
- Après la création, une fenêtre affiche **uniquement à ce moment-là** le texte à transmettre. Cliquer sur **Copier le texte**, puis le coller dans votre courriel ou message :

```
Lien : https://pilote.ges-ped.hnsf.dz
Identifiant : n.laouar
Mot de passe temporaire : K7m4P9s2
```

- Mot de passe oublié : **Nouveau mot de passe** sur la ligne du compte. Un nouveau mot de passe temporaire est généré, et l’ancien ne fonctionne plus.
- Départ d’un utilisateur : **Désactiver**.

## 3. Checklist des tests utilisateurs
| Test | Qui | À vérifier | ✓ |
|---|---|---|---|
| A | Chef dépt A | Lien ouvert dans un navigateur neuf, mot de passe temporaire accepté, changement obligatoire | ☐ |
| A | Chef dépt A | Arrivée sur « Tableau de bord — Mon département » (bon département) | ☐ |
| A | Chef dépt A | Vœux → Campagnes : créer la campagne et la passer en « Ouverte » | ☐ |
| A | Chef dépt A | Vœux → Traitement : accepter, refuser, commenter ; « Créer l’affectation » | ☐ |
| A | Chef dépt A | Affectations → « Nouvelle affectation manuelle » sans vœu | ☐ |
| A | Chef dépt A | Impossible de modifier un enseignement du département B | ☐ |
| B | Enseignant 1 | Reçoit seulement lien + identifiant + mot de passe, puis change son mot de passe | ☐ |
| B | Enseignant 1 | Mes vœux : choisit des activités et une langue | ☐ |
| B | Enseignant 1 | Voit uniquement ses affectations et son emploi du temps | ☐ |
| C | Enseignant 2 | Vœux dans les deux départements, affectations dans les deux | ☐ |
| C | Enseignant 2 | Une seule charge (Ma charge) et un seul emploi du temps pour les deux départements | ☐ |
| D | Enseignant 1 | Aucune donnée de l’enseignant 2 n’est visible, où qu’il cherche | ☐ |
| E | Tous (5) | Connexion en même temps et travail simultané, sans perte de données | ☐ |
| F | Chefs A et B | Même enseignant placé au même créneau dans les deux départements : refusé | ☐ |
| G | Vous | Rapports → Taux d’anglais et Enseignants en anglais : les valeurs sont cohérentes | ☐ |

Chaque utilisateur peut transmettre ses remarques avec le bouton **Signaler un problème**, en haut de l’écran. Vous les retrouvez dans **Paramètres → Retours pilotes**.

## 4. Passer du PILOTE à la PRODUCTION (après validation)
1. Demander l’enregistrement DNS `ges-ped.hnsf.dz` et, si possible, un serveur dédié.
2. Sur ce serveur : `sudo bash deploiement/installer-ges-ped.sh --instance production --domaine ges-ped.hnsf.dz --email …`. On obtient une base, un service et des sauvegardes distincts du pilote.
3. Choisir entre deux options :
   - repartir d’une base propre ;
   - reprendre les données validées du pilote : Paramètres → Sauvegarde sur le pilote, puis Restaurer sur la production.
4. Recréer les comptes réels, puis transmettre le nouveau lien.
5. Fermer le pilote une fois la production validée.
