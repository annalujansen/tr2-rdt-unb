#!/usr/bin/env python3
"""
Cliente RDT-UnB v1.0 — Entrega 2: SAW, GBN e SR com simulação de perda.

Uso:
    python3 cliente.py --group grupo10 --file small --protocol saw
    python3 cliente.py --group grupo10 --file small --protocol gbn --window 8 --loss 0.05
    python3 cliente.py --group grupo10 --file small --protocol sr  --window 16 --loss 0.10 --seed 42

Na DEMO: não use --loss (padrão 0 = sem simulação; só a perda natural da rede).
"""
import argparse
import importlib
import sys

from comum import (DEFAULT_MAX_RETRIES, DEFAULT_PORT, DEFAULT_SEGMENT_SIZE,
                   DEFAULT_TIMEOUT_MS, finish, handshake, new_session)


def parse_args():
    ap = argparse.ArgumentParser(description="Cliente RDT-UnB — SAW / GBN / SR")
    ap.add_argument("--server", default="137.131.178.229", help="IP do servidor")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--group", required=True, help="ID do grupo (obrigatório), ex.: grupo10")
    ap.add_argument("--file", choices=["small", "medium", "large"], default="small")
    ap.add_argument("--protocol", choices=["saw", "gbn", "sr"], default="saw")
    ap.add_argument("--window", type=int, default=None,
                    help="tamanho da janela (obrigatório em gbn/sr; saw usa sempre 1)")
    ap.add_argument("--loss", type=float, default=0.0,
                    help="probabilidade de descartar cada DATA recebido (0.05 = 5%%)")
    ap.add_argument("--seed", type=int, default=None, help="seed da simulação (repetibilidade)")
    ap.add_argument("--segment-size", type=int, default=DEFAULT_SEGMENT_SIZE)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS, help="timeout fixo em ms")
    ap.add_argument("--timeout-mode", choices=["fixed", "adaptive"], default="fixed",
                    help="modo do timeout; adaptive está disponível em GBN e SR")
    ap.add_argument("--alpha", type=float, default=0.125, help="peso do RTT medido na EWMA")
    ap.add_argument("--beta", type=float, default=0.25, help="peso do desvio na EWMA")
    ap.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    ap.add_argument("--outdir", default="resultados", help="pasta de saída (CSV, .bin, resumo)")
    args = ap.parse_args()

    if not 0.0 <= args.loss < 1.0:
        ap.error("--loss deve estar em [0, 1), ex.: 0.05")
    if args.protocol in ("gbn", "sr") and (args.window is None or args.window < 1):
        ap.error(f"--window é obrigatório para {args.protocol} (use 4, 8 ou 16)")
    if args.timeout_mode == "adaptive" and args.protocol not in ("gbn", "sr"):
        ap.error("--timeout-mode adaptive está disponível com --protocol gbn ou sr")
    if not 0 < args.alpha <= 1 or not 0 < args.beta <= 1:
        ap.error("--alpha e --beta devem estar no intervalo (0, 1]")
    return args


def main():
    args = parse_args()
    protocolo = importlib.import_module(args.protocol)   # saw.py, gbn.py ou sr.py
    sess = new_session(args)
    handshake(sess)
    payloads, rows = protocolo.run(sess)                 # cada protocolo devolve (payloads, rows)
    ok = finish(sess, payloads, rows)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
