#!/usr/bin/env python3
"""
Gera os gráficos de throughput e RTT por segmento a partir do CSV do cliente.

Uso:
    .venv/bin/python graficos.py metrics_grupo01_saw_20261015_143022.csv
Gera: <nome_do_csv>.png
"""

import csv
import sys

import matplotlib.pyplot as plt


def main():
    if len(sys.argv) != 2:
        sys.exit("uso: python3 graficos.py <arquivo.csv>")
    path = sys.argv[1]

    seg, rtt, thr, retx, sizes = [], [], [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            seg.append(int(row["segment"]))
            sizes.append(int(row["size_bytes"]))
            rtt.append(float(row["rtt_ms"]))
            thr.append(float(row["throughput_kbps"]))
            retx.append(int(row["retransmissions"]))

    seg_size = max(sizes)  # bytes; o maior payload = segment_size (o último pode ser menor)
    avg_rtt = sum(rtt) / len(rtt)
    theoretical = seg_size * 8 / avg_rtt          # kbps
    # Média ponderada pelo tempo: total de bits / tempo total gasto nos segmentos.
    # (A média simples dos valores instantâneos esconderia o custo dos timeouts.)
    seg_times = [b * 8 / 1000 / t for b, t in zip(sizes, thr)]  # segundos por segmento
    avg_thr = sum(sizes) * 8 / 1000 / sum(seg_times)
    retx_segs = [s for s, r in zip(seg, retx) if r > 0]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    ax1.plot(seg, thr, lw=0.6, label="throughput instantâneo")
    ax1.axhline(avg_thr, color="tab:green", ls="--", label=f"média medida ({avg_thr:.1f} kbps)")
    ax1.axhline(theoretical, color="tab:red", ls=":", label=f"teórico máx. ({theoretical:.1f} kbps)")
    ax1.set_ylabel("Throughput (kbps)")
    ax1.set_title("Stop-and-Wait — throughput e RTT por segmento")
    ax1.legend(loc="lower right")
    ax1.grid(alpha=0.3)

    ax2.plot(seg, rtt, lw=0.6, color="tab:orange", label="RTT medido")
    ax2.axhline(avg_rtt, color="tab:gray", ls="--", label=f"RTT médio ({avg_rtt:.1f} ms)")
    for s in retx_segs:  # marca os segmentos que tiveram retransmissão
        ax2.axvline(s, color="tab:red", alpha=0.3, lw=0.8)
    ax2.set_xlabel("Segmento")
    ax2.set_ylabel("RTT (ms)")
    ax2.legend(loc="upper right")
    ax2.grid(alpha=0.3)

    out = path.rsplit(".", 1)[0] + ".png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Gráfico salvo em {out}")


if __name__ == "__main__":
    main()
