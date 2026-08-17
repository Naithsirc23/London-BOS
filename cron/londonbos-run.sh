#!/bin/bash
# Wrapper para correr módulos London-BOS con el venv y el .env cargado.
# Uso: londonbos-run.sh <modulo>
#   modulo = armado | paper-mid | paper-end
cd /home/cris/GITHUBS/London-BOS || exit 1
# cargar .env si existe
if [ -f DATA/.env ]; then
  set -a
  . ./DATA/.env
  set +a
fi
export LONDONBOS_TG_CHAT=6091150597
. DATA/.venv/bin/activate
if [ "$1" = "armado" ]; then
  python DATA/armado.py --port 4001 --client 30
elif [ "$1" = "paper-mid" ]; then
  python DATA/paper_trade.py --hasta 04:30
elif [ "$1" = "paper-end" ]; then
  python DATA/paper_trade.py
else
  echo "Uso: londonbos-run.sh armado|paper-mid|paper-end"
  exit 1
fi
