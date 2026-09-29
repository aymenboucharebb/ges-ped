#!/usr/bin/env bash
# ges-ped — installation serveur (Ubuntu 24.04 LTS recommandé, 22.04 accepté).
# Une seule commande, à lancer en root sur le serveur :
#   sudo bash installer-ges-ped.sh --domaine pilote.ges-ped.ensf.dz --email informatique@ensf.dz
# Options :
#   --instance pilote|production   (défaut : pilote — base, service et dossiers séparés)
#   --certificat FICHIER --cle FICHIER   certificat fourni par l'ENSF (sinon Let's Encrypt automatique)
#   --admin IDENTIFIANT            (défaut : admin)
set -euo pipefail
INSTANCE=pilote; DOMAINE=""; EMAIL=""; CERT=""; KEY=""; ADMIN=admin
while [ $# -gt 0 ]; do
  case "$1" in
    --domaine) DOMAINE="$2"; shift 2;;
    --email) EMAIL="$2"; shift 2;;
    --instance) INSTANCE="$2"; shift 2;;
    --certificat) CERT="$2"; shift 2;;
    --cle) KEY="$2"; shift 2;;
    --admin) ADMIN="$2"; shift 2;;
    *) echo "Option inconnue : $1"; exit 2;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "Lancez ce script avec sudo."; exit 1; }
[ -n "$DOMAINE" ] || { echo "Indiquez --domaine (ex. pilote.ges-ped.ensf.dz)."; exit 1; }
[[ "$INSTANCE" =~ ^(pilote|production)$ ]] || { echo "--instance : pilote ou production"; exit 1; }
[ -n "$EMAIL" ] || [ -n "$CERT" ] || { echo "Indiquez --email (compte Let's Encrypt) ou --certificat/--cle."; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/ges-ped-$INSTANCE; DATA=/var/lib/ges-ped-$INSTANCE; BACKUP=/var/backups/ges-ped-$INSTANCE; ETC=/etc/ges-ped; ENVF=$ETC/$INSTANCE.env
SERVICE=ges-ped-$INSTANCE; DB=gesped_$INSTANCE; PORT=$([ "$INSTANCE" = pilote ] && echo 8765 || echo 8766)
EDITION=$([ "$INSTANCE" = pilote ] && echo PILOTE || echo "")
log(){ echo -e "\n==> $*"; }

log "1/8 Paquets système (PostgreSQL, Caddy, Python)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql python3 python3-venv curl ca-certificates debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
CADDY_POLICY=$(apt-cache policy caddy 2>/dev/null || true)
if ! grep -q 'Candidate: [0-9]' <<<"$CADDY_POLICY"; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
fi
apt-get install -y -qq caddy >/dev/null
PY=/usr/bin/python3
if ! apt-get install -y -qq python3-psycopg >/dev/null 2>&1 || ! $PY -c 'import psycopg' 2>/dev/null; then
  $PY -m venv /opt/ges-ped-venv && /opt/ges-ped-venv/bin/pip install -q 'psycopg[binary]>=3.1' && PY=/opt/ges-ped-venv/bin/python
fi

log "2/8 Application ($APP)"
id gesped >/dev/null 2>&1 || useradd --system --home /nonexistent --shell /usr/sbin/nologin gesped
mkdir -p "$APP" "$DATA/sauvegardes" "$ETC" "$BACKUP"
cp -r "$SRC"/{server.py,database.py,domain.py,schema.py,excel.py,manage.py,static,references} "$APP"/
chown -R root:root "$APP"; chmod -R a+rX "$APP"; chown -R gesped:gesped "$DATA"; chmod 750 "$DATA"; chown postgres:postgres "$BACKUP"; chmod 750 "$BACKUP"

log "3/8 Base PostgreSQL privée ($DB, accessible uniquement depuis ce serveur)"
if [ ! -f "$ENVF" ]; then
  DBPASS=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
  [ "$(su postgres -c "psql -qtAc \"SELECT 1 FROM pg_roles WHERE rolname='$DB'\"")" = 1 ] || su postgres -c "psql -qc \"CREATE ROLE $DB LOGIN PASSWORD '$DBPASS'\""
  su postgres -c "psql -qc \"ALTER ROLE $DB PASSWORD '$DBPASS'\""
  [ "$(su postgres -c "psql -qtAc \"SELECT 1 FROM pg_database WHERE datname='$DB'\"")" = 1 ] || su postgres -c "createdb -O $DB $DB"
  umask 077
  cat > "$ENVF" <<EOF
GESPED_DATABASE_URL=postgresql://$DB:$DBPASS@127.0.0.1:5432/$DB
GESPED_PUBLIC_URL=https://$DOMAINE
GESPED_HOSTS=$DOMAINE
GESPED_EDITION=$EDITION
GESPED_TRUST_PROXY=1
GESPED_SECURE_COOKIE=1
GESPED_ALLOW_SETUP=0
GESPED_BIND=127.0.0.1
GESPED_PORT=$PORT
GESPED_DATA_DIR=$DATA
GESPED_IDLE_MINUTES=120
EOF
  umask 022
else
  sed -i "s|^GESPED_PUBLIC_URL=.*|GESPED_PUBLIC_URL=https://$DOMAINE|;s|^GESPED_HOSTS=.*|GESPED_HOSTS=$DOMAINE|" "$ENVF"
fi
chown root:gesped "$ENVF"; chmod 640 "$ENVF"
# PostgreSQL n'écoute que localement (configuration Ubuntu par défaut) : on le vérifie.
PGCONF=$(su postgres -c "psql -qtAc 'SHOW config_file'")
grep -Eq "^[[:space:]]*listen_addresses[[:space:]]*=[[:space:]]*'\*'" "$PGCONF" && echo "ATTENTION : PostgreSQL écoute sur toutes les interfaces ($PGCONF). Recommandé : listen_addresses = 'localhost'."

log "4/8 Service $SERVICE"
cat > /etc/systemd/system/$SERVICE.service <<EOF
[Unit]
Description=ges-ped ($INSTANCE) — Gestion pédagogique ENSF
After=network.target postgresql.service
Requires=postgresql.service
[Service]
User=gesped
Group=gesped
EnvironmentFile=$ENVF
WorkingDirectory=$APP
ExecStart=$PY $APP/server.py --no-browser
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA
[Install]
WantedBy=multi-user.target
EOF
asgesped(){ ( cd "$APP" && runuser -u gesped -- env $(grep -v '^#' "$ENVF" | xargs) "$PY" "$@" ); }
asgesped manage.py init
systemctl daemon-reload; systemctl enable --now $SERVICE >/dev/null; systemctl restart $SERVICE

log "5/8 HTTPS (Caddy) pour https://$DOMAINE"
mkdir -p /etc/caddy/sites
grep -q 'import sites/\*' /etc/caddy/Caddyfile 2>/dev/null || cat > /etc/caddy/Caddyfile <<EOF
{
	${EMAIL:+email $EMAIL}
}
import sites/*
EOF
TLS=""
if [ -n "$CERT" ]; then install -m 640 -o root -g caddy "$CERT" $ETC/$INSTANCE-cert.pem; install -m 640 -o root -g caddy "$KEY" $ETC/$INSTANCE-key.pem; TLS="tls $ETC/$INSTANCE-cert.pem $ETC/$INSTANCE-key.pem"; fi
cat > /etc/caddy/sites/$INSTANCE.caddy <<EOF
$DOMAINE {
	$TLS
	encode gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		-Server
	}
	reverse_proxy 127.0.0.1:$PORT
}
EOF
caddy fmt --overwrite /etc/caddy/Caddyfile 2>/dev/null || true
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || { echo "Configuration HTTPS invalide :"; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; exit 1; }
systemctl enable --now caddy >/dev/null; systemctl reload caddy || systemctl restart caddy
if command -v ufw >/dev/null && [[ "$(ufw status 2>/dev/null)" == *"Status: active"* ]]; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi

log "6/8 Sauvegarde automatique quotidienne (02:30, 30 jours conservés, $BACKUP)"
cat > /etc/cron.d/$SERVICE-sauvegarde <<EOF
30 2 * * * postgres pg_dump -Fc $DB > $BACKUP/$DB-\$(date +\%Y\%m\%d).dump && find $BACKUP -name '$DB-*.dump' -mtime +30 -delete
EOF
chmod 644 /etc/cron.d/$SERVICE-sauvegarde
su postgres -c "pg_dump -Fc $DB > $BACKUP/$DB-installation.dump" && echo "Première sauvegarde : $BACKUP/$DB-installation.dump"

log "7/8 Compte administrateur"
ADMINOUT=$(asgesped manage.py create-admin "$ADMIN" || true)
echo "$ADMINOUT"

log "8/8 Vérification"
sleep 2
curl --noproxy "*" -fsS "http://127.0.0.1:$PORT/healthz" -H "Host: $DOMAINE" >/dev/null && echo "Application : OK" || echo "Application : ÉCHEC (journalctl -u $SERVICE)"
if curl --noproxy "*" -fsS --max-time 20 "https://$DOMAINE/healthz" >/dev/null 2>&1; then echo "HTTPS public : OK (certificat valide)"; else echo "HTTPS public : pas encore joignable. Vérifiez le DNS de $DOMAINE et l'ouverture des ports 80/443 ; Caddy obtiendra le certificat automatiquement dès que ce sera le cas."; fi
echo
echo "================================================================"
echo " ges-ped $INSTANCE installé"
echo " Lien à transmettre : https://$DOMAINE"
echo " Administration : identifiant « $ADMIN » (mot de passe temporaire ci-dessus)"
echo " Commandes utiles : systemctl status $SERVICE | journalctl -u $SERVICE -f"
echo "================================================================"
