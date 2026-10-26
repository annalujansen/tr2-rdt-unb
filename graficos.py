#!/usr/bin/env python3
"""
Gera os gráficos de throughput e RTT por segmento a partir do CSV do cliente.
Funciona para SAW, GBN e SR (lê o protocolo e a janela do próprio CSV) e também
com os CSVs da Entrega 1, que não têm a coluna simulated_loss.

Uso:
    .venv/bin/python graficos.py resultados/small_gbn_w4_loss0/metrics_grupo10_gbn_<data>.csv [--janela 100]
Gera: <nome_do_csv>.png

Além dos valores por segmento, desenha a média móvel (janela de N segmentos), que
mostra a tendência mesmo quando há milhares de pontos (medium/large).
Na faixa de baixo marca, separadamente, os segmentos com timeout e os com perda
simulada (a especificação pede para separar a perda simulada da perda natural).
"""

import argparse
import csv

import matplotlib.pyplot as plt

PROTOCOL_NAMES = {"saw": "Stop-and-Wait", "gbn": "Go-Back-N", "sr": "Selective Repeat"}


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

    seg, rtt, thr, retx, sizes, timeouts, sim_loss = [], [], [], [], [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            seg.append(int(row["segment"]))
            sizes.append(int(row["size_bytes"]))
            rtt.append(float(row["rtt_ms"]))
            thr.append(float(row["throughput_kbps"]))
            retx.append(int(row["retransmissions"]))
            timeouts.append(int(row["timeout_occurred"]))
            sim_loss.append(int(row.get("simulated_loss") or 0))   # não existe na Entrega 1
            protocol = row["protocol"]
            window = int(row["window_size"])

    seg_size = max(sizes)  # bytes; o maior payload = segment_size (o último pode ser menor)
    avg_rtt = sum(rtt) / len(rtt)
    # Sem perda, cabem `window` segmentos por RTT (window = 1 reduz à fórmula do SAW)
    theoretical = window * seg_size * 8 / avg_rtt          # kbps
    # Média ponderada pelo tempo: total de bits / tempo total gasto nos segmentos.
    # (A média simples dos valores instantâneos esconderia o custo dos timeouts.)
    seg_times = [b * 8 / 1000 / t for b, t in zip(sizes, thr)]  # segundos por segmento
    avg_thr = sum(sizes) * 8 / 1000 / sum(seg_times)
    timeout_segs = [s for s, t in zip(seg, timeouts) if t]
    sim_loss_segs = [s for s, l in zip(seg, sim_loss) if l]
    total_retx = sum(retx)

    # Média móvel do throughput também ponderada pelo tempo (bits da janela / tempo da janela)
    bits_ma = moving_average([b * 8 / 1000 for b in sizes], args.janela)
    time_ma = moving_average(seg_times, args.janela)
    thr_ma = [b / t for b, t in zip(bits_ma, time_ma)]
    rtt_ma = moving_average(rtt, args.janela)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 3, 1]})

    if window == 1:
        # No SAW chega um segmento por vez: o throughput de cada segmento faz sentido.
        ax1.plot(seg, thr, lw=0.5, alpha=0.35, color="tab:blue", label="throughput por segmento")
    # Com janela os DATA chegam em rajadas: o intervalo entre duas chegadas fica
    # minúsculo e o throughput "por segmento" vira só ruído (picos de dezenas de
    # milhares de kbps). Por isso, com janela, só a média móvel é desenhada.
    ax1.plot(seg, thr_ma, lw=1.8, color="tab:blue", label=f"média móvel ({args.janela} seg.)")
    ax1.axhline(avg_thr, color="tab:green", ls="--", label=f"média medida ({avg_thr:.1f} kbps)")
    ax1.axhline(theoretical, color="tab:red", ls=":", label=f"teórico máx. ({theoretical:.1f} kbps)")
    ax1.set_ylabel("Throughput (kbps)")
    ax1.set_ylim(bottom=0)
    name = PROTOCOL_NAMES.get(protocol, protocol.upper())
    janela = "" if protocol == "saw" else f", janela {window}"
    ax1.set_title(f"{name}{janela} — throughput e RTT por segmento ({len(seg)} segmentos)")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.plot(seg, rtt, lw=0.5, alpha=0.35, color="tab:orange", label="RTT por segmento")
    ax2.plot(seg, rtt_ma, lw=1.8, color="tab:orange", label=f"média móvel ({args.janela} seg.)")
    ax2.axhline(avg_rtt, color="tab:gray", ls="--", label=f"RTT médio ({avg_rtt:.1f} ms)")
    ax2.set_ylabel("RTT (ms)")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(alpha=0.3)

    # Faixa de eventos: uma linha para timeout, outra para perda simulada.
    # (No GBN quase todo segmento é retransmitido "de carona", então marcar
    # retransmissões cobriria o gráfico inteiro; o timeout é o evento que importa.)
    ax3.eventplot([timeout_segs, sim_loss_segs], lineoffsets=[1, 0], linelengths=0.7,
                  linewidths=0.6, colors=["tab:red", "tab:purple"])
    ax3.set_yticks([1, 0])
    ax3.set_yticklabels([f"timeout ({len(timeout_segs)})",
                         f"perda simulada ({len(sim_loss_segs)})"], fontsize=8)
    ax3.set_ylim(-0.6, 1.6)
    ax3.set_xlabel("Segmento")
    ax3.set_title(f"Eventos — {total_retx} retransmissões no total", fontsize=9, loc="left")
    ax3.grid(axis="x", alpha=0.3)

    out = path.rsplit(".", 1)[0] + ".png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Gráfico salvo em {out}")


if __name__ == "__main__":
    main()
