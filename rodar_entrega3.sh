#!/usr/bin/env bash
# Experimentos da Entrega 3 (RTT adaptativo). Uso:
#   ./rodar_entrega3.sh varredura   # α × β no SR-16, small, perdas 0/5/10 %, 2 repetições (~20 min)
#   ./rodar_entrega3.sh comparacao  # fixo × adaptativo, GBN-16 e SR-16, small, perdas 0/5/10 %, 2 repetições
# Variáveis de ambiente:
#   ALPHA, BETA  par usado em "comparacao" (escolha pelo resultado da varredura)
#   OUT          pasta de saída (padrão entregas/entrega3/dados); ex.: OUT=demo ./rodar_entrega3.sh varredura
# O arquivo large (com a captura do Wireshark) é rodado à mão, um protocolo por vez (ver README).
set -u
cd "$(dirname "$0")"
G=grupo10
OUT=${OUT:-entregas/entrega3/dados}
ALPHA=${ALPHA:-0.125}
BETA=${BETA:-0.25}

ping_servidor() {
  python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(b'PING',('137.131.178.229',8080)); s.recvfrom(2048)" \
    || { echo "servidor não respondeu ao PING"; exit 1; }
}

roda() {   # roda <outdir> <args...>
  local dir=$1; shift
  echo "=== $* ==="
  python3 cliente.py --group $G --seed 42 --outdir "$dir" "$@" | grep -E "Tempo total|Retransmiss|Throughput medido|Timeout \(|Checksum"
}

ping_servidor
case "${1:-}" in
  varredura)
    for rep in 1 2; do
      for l in 0 0.05 0.10; do
        for a in 0.0625 0.125 0.25 0.5; do
          for b in 0.125 0.25 0.5; do
            roda $OUT/varredura --file small --protocol sr --window 16 --loss $l \
                 --timeout-mode adaptive --alpha $a --beta $b
          done
        done
      done
    done ;;
  comparacao)
    for rep in 1 2; do
      for p in gbn sr; do
        for l in 0 0.05 0.10; do
          roda $OUT/comparacao --file small --protocol $p --window 16 --loss $l --timeout-mode fixed
          roda $OUT/comparacao --file small --protocol $p --window 16 --loss $l \
               --timeout-mode adaptive --alpha $ALPHA --beta $BETA
        done
      done
    done ;;
  *) echo "uso: $0 varredura|comparacao"; exit 2 ;;
esac
