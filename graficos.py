#!/usr/bin/env python3
"""
Gera os gráficos de throughput e RTT por segmento a partir do CSV do cliente.

Uso:
    .venv/bin/python graficos.py metrics_grupo01_saw_20261015_143022.csv [--janela 100]
Gera: <nome_do_csv>.png

Além dos valores por segmento, desenha a média móvel (janela de N segmentos), que
mostra a tendência mesmo quando há milhares de pontos (medium/large).
"""

import argparse
import csv

import matplotlib.pyplot as plt


def moving_average(values, window):
    """Média de cada bloco deslizante de `window` valores (centrada no segmento)."""
    half = window // 2
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    out = []
    for i in range(len(values)):
        lo, hi = max(0, i - half), min(len(values), i + half + 1)
        out.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return out


def main():
    ap = argparse.ArgumentParser(description="Gráficos de throughput e RTT por segmento")
    ap.add_argument("csv", help="CSV gerado pelo cliente")
    ap.add_argument("--janela", type=int, default=100, help="segmentos na média móvel (padrão 100)")
    args = ap.parse_args()
    path = args.csv

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

    # Média móvel do throughput também ponderada pelo tempo (bits da janela / tempo da janela)
    bits_ma = moving_average([b * 8 / 1000 for b in sizes], args.janela)
    time_ma = moving_average(seg_times, args.janela)
    thr_ma = [b / t for b, t in zip(bits_ma, time_ma)]
    rtt_ma = moving_average(rtt, args.janela)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    ax1.plot(seg, thr, lw=0.5, alpha=0.35, color="tab:blue", label="throughput por segmento")
    ax1.plot(seg, thr_ma, lw=1.8, color="tab:blue", label=f"média móvel ({args.janela} seg.)")
    ax1.axhline(avg_thr, color="tab:green", ls="--", label=f"média medida ({avg_thr:.1f} kbps)")
    ax1.axhline(theoretical, color="tab:red", ls=":", label=f"teórico máx. ({theoretical:.1f} kbps)")
    ax1.set_ylabel("Throughput (kbps)")
    ax1.set_title(f"Stop-and-Wait — throughput e RTT por segmento ({len(seg)} segmentos)")
    ax1.legend(loc="lower right", fontsize=8)
    ax1.grid(alpha=0.3)

    for s in retx_segs:  # marca os segmentos que tiveram retransmissão
        ax2.axvline(s, color="tab:red", alpha=0.2, lw=0.6)
    ax2.plot(seg, rtt, lw=0.5, alpha=0.35, color="tab:orange", label="RTT por segmento")
    ax2.plot(seg, rtt_ma, lw=1.8, color="tab:orange", label=f"média móvel ({args.janela} seg.)")
    ax2.axhline(avg_rtt, color="tab:gray", ls="--", label=f"RTT médio ({avg_rtt:.1f} ms)")
    ax2.plot([], [], color="tab:red", alpha=0.4, label="segmento com retransmissão")
    ax2.set_xlabel("Segmento")
    ax2.set_ylabel("RTT (ms)")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(alpha=0.3)

    out = path.rsplit(".", 1)[0] + ".png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Gráfico salvo em {out}")


if __name__ == "__main__":
    main()
