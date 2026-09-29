#!/usr/bin/env bash
# ges-ped — mise à jour de l'application sur le serveur (les données sont conservées).
#   sudo bash mettre-a-jour-ges-ped.sh [--instance pilote|production]
set -euo pipefail
INSTANCE=pilote
[ "${1:-}" = "--instance" ] && INSTANCE="$2"
[ "$(id -u)" = 0 ] || { echo "Lancez ce script avec sudo."; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"; APP=/opt/ges-ped-$INSTANCE; SERVICE=ges-ped-$INSTANCE; DB=gesped_$INSTANCE; BACKUP=/var/backups/ges-ped-$INSTANCE
[ -d "$APP" ] || { echo "Instance $INSTANCE introuvable : utilisez installer-ges-ped.sh."; exit 1; }
STAMP=$(date +%Y%m%d-%H%M%S)
echo "==> Sauvegarde de la base avant mise à jour"
su postgres -c "pg_dump -Fc $DB > $BACKUP/$DB-avant-maj-$STAMP.dump"
echo "==> Sauvegarde du programme actuel"
tar -czf "$BACKUP/programme-avant-maj-$STAMP.tgz" -C "$APP" .
echo "==> Installation des nouveaux fichiers"
cp -r "$SRC"/{server.py,database.py,domain.py,schema.py,excel.py,manage.py,static,references} "$APP"/
chmod -R a+rX "$APP"
systemctl restart $SERVICE
sleep 3
PORT=$(grep '^GESPED_PORT=' /etc/ges-ped/$INSTANCE.env | cut -d= -f2); HOST=$(grep '^GESPED_HOSTS=' /etc/ges-ped/$INSTANCE.env | cut -d= -f2)
if curl --noproxy "*" -fsS "http://127.0.0.1:$PORT/healthz" -H "Host: $HOST" >/dev/null; then echo "Mise à jour terminée : ges-ped fonctionne (migrations de la base appliquées automatiquement)."
else echo "ÉCHEC du démarrage. Retour arrière : tar -xzf $BACKUP/programme-avant-maj-$STAMP.tgz -C $APP && systemctl restart $SERVICE ; base : pg_restore --clean -d $DB $BACKUP/$DB-avant-maj-$STAMP.dump"; exit 1; fi
