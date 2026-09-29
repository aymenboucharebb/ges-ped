# Vérification — ges-ped 1.2.0 PILOTE — 25/09/2026

- **79 tests automatisés réussis sur SQLite et les mêmes 79 sur PostgreSQL 16** : 0 échec, 0 erreur (RESULTATS_TESTS.txt).
- **Recette de bout en bout en HTTPS : 28/28 contrôles réussis.** Elle a été faite avec de vrais navigateurs Chromium, sans aucune exception de sécurité acceptée, sur une installation réalisée par `deploiement/installer-ges-ped.sh` : PostgreSQL privé, service applicatif, Caddy HTTPS, sauvegarde et compte administrateur. Les tests A à G de la demande pilote sont couverts.
- Sécurité vérifiée :
  - mots de passe temporaires uniques, jamais stockés en clair ;
  - changement obligatoire du mot de passe avant tout accès ;
  - jetons de session hachés, expiration après 2 h d’inactivité et 10 h au maximum ;
  - verrouillage après 5 échecs, pendant 15 minutes ;
  - cookies `__Host-`, `Secure`, `HttpOnly`, `SameSite=Strict`, protection CSRF ;
  - hôte et origine contrôlés ; HSTS, CSP et X-Frame-Options ;
  - accès par adresse IP refusé ;
  - PostgreSQL n’écoute qu’en local ;
  - droits appliqués par l’API : 16 tentatives de contournement par un enseignant, toutes refusées.
- Simultanéité : 5 comptes connectés travaillent en même temps sur la même base, sans écrasement. Deux modifications concurrentes d’une même fiche : la seconde est refusée.
- Semaine ENSF (dimanche → jeudi) et créneaux (08:00, 09:30, 11:00, pause, 13:30, 15:00) contrôlés à l’enregistrement.

Limite : le test a été fait avec un certificat d’une autorité de test ajoutée au navigateur, sur le nom de domaine de test `pilote.ges-ped.test`. Sur le serveur réel, Caddy obtient automatiquement un certificat Let’s Encrypt pour `pilote.ges-ped.hnsf.dz` dès que le DNS et les ports 80/443 sont en place.
