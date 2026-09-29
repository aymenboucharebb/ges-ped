# ges-ped PILOTE — demande à l’administrateur réseau / DNS de l’ENSF

Objet : mise en ligne du site pilote de gestion pédagogique **ges-ped**, à l’adresse **https://pilote.ges-ped.hnsf.dz**.

## 1. Un serveur pour le pilote
- Une machine Linux **Ubuntu Server 24.04 LTS** (22.04 accepté) : physique, virtuelle ou VPS.
- Minimum : 2 processeurs, 4 Go de mémoire, 40 Go de disque.
- Un accès administrateur (sudo) pour lancer l’installation, qui dure environ 5 minutes.
- Cette machine est réservée au pilote. La production aura plus tard sa propre instance : `https://ges-ped.hnsf.dz`.

## 2. Le nom de domaine
Créer dans la zone DNS **hnsf.dz** l’enregistrement :

| Nom | Type | Valeur |
|---|---|---|
| `pilote.ges-ped` | A | adresse IP **publique** du serveur pilote |

Si la zone contient un enregistrement CAA, il doit autoriser `letsencrypt.org`.

## 3. Ouvertures réseau
- Entrant, depuis Internet vers le serveur : **TCP 80 et 443**. Le port 80 sert uniquement à l’obtention et au renouvellement automatiques du certificat, puis à la redirection vers HTTPS.
- Sortant : HTTPS vers Internet, pour les mises à jour Ubuntu et Let’s Encrypt.
- **Aucun autre port.** La base PostgreSQL reste interne au serveur : elle n’écoute que sur 127.0.0.1 et n’est jamais exposée.

## 4. Installation (une commande, sur le serveur)
Copier le dossier `ges-ped` sur le serveur, puis lancer :

```
sudo bash deploiement/installer-ges-ped.sh --domaine pilote.ges-ped.hnsf.dz --email ADRESSE_EMAIL_INFORMATIQUE
```

Le script installe PostgreSQL, Caddy (serveur HTTPS) et l’application, puis :
- crée la base privée ;
- obtient automatiquement un certificat valide (Let’s Encrypt, renouvelé tout seul) ;
- programme une sauvegarde quotidienne (02:30, 30 jours conservés) ;
- affiche l’identifiant **admin** et son mot de passe temporaire. Merci de transmettre ce mot de passe au responsable fonctionnel.

**Si le serveur ne peut pas être joignable depuis Internet** (intranet uniquement), fournir un certificat pour `pilote.ges-ped.hnsf.dz` délivré par une autorité reconnue par les navigateurs, puis ajouter `--certificat fichier.pem --cle fichier.key` à la commande. Un certificat « maison » non reconnu provoquerait un avertissement dans les navigateurs, ce qu’il faut éviter.

## 5. Exploitation courante
- État du service : `systemctl status ges-ped-pilote` ; journal : `journalctl -u ges-ped-pilote -f`.
- Sauvegardes : `/var/backups/ges-ped-pilote/`. Les copier régulièrement hors du serveur.
- Mise à jour de l’application : `sudo bash deploiement/mettre-a-jour-ges-ped.sh`. La base est sauvegardée automatiquement avant la mise à jour.
- Mot de passe administrateur perdu : `sudo bash deploiement/ges-ped-admin.sh reset-password admin` (un nouveau mot de passe temporaire s’affiche).
- Diagnostic : `sudo bash deploiement/ges-ped-admin.sh check`.
