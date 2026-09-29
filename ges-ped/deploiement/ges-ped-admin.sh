#!/usr/bin/env bash
# Commandes d'administration ges-ped sur le serveur :
#   sudo bash ges-ped-admin.sh reset-password admin
#   sudo bash ges-ped-admin.sh users | check      [--instance production]
set -euo pipefail
INSTANCE=pilote; ARGS=()
while [ $# -gt 0 ]; do case "$1" in --instance) INSTANCE="$2"; shift 2;; *) ARGS+=("$1"); shift;; esac; done
[ "$(id -u)" = 0 ] || { echo "Lancez avec sudo."; exit 1; }
PY=/usr/bin/python3; [ -x /opt/ges-ped-venv/bin/python ] && PY=/opt/ges-ped-venv/bin/python
cd /opt/ges-ped-$INSTANCE && runuser -u gesped -- env $(grep -v '^#' /etc/ges-ped/$INSTANCE.env | xargs) "$PY" manage.py "${ARGS[@]}"
