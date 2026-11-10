#!/usr/bin/env python3
"""
Análise da Entrega 3 (RTT adaptativo).  Rodar com .venv/bin/python.

    rtt_adaptativo.py serie <csv> [--inicio 0 --fim 300]
        RTT medido × RTT estimado por segmento e timeout ao longo da transferência.
        Gera <csv>_rtt.png (ou <csv>_rtt_<inicio>-<fim>.png com zoom).

    rtt_adaptativo.py varredura [--resumo entregas/entrega3/dados/varredura/resumo_entrega3.csv]
        Tabela e mapas de calor da varredura α × β (média das repetições).

    rtt_adaptativo.py comparacao [--resumo entregas/entrega3/dados/comparacao/resumo_entrega3.csv]
        Tabela fixo × adaptativo (GBN-16 e SR-16, perdas 0/5/10 %).

    rtt_adaptativo.py final [--resumo entregas/entrega3/dados/large/resumo_entrega3.csv]
        Tabela integrada e gráfico de barras com o melhor cenário de cada protocolo (large).

"Retransmissões espúrias" (estimativa) = retransmissões - DATA descartados pela simulação.
No SR cada descarte exige exatamente 1 retransmissão; o que passa disso é timeout que
estourou com o DATA ainda a caminho (ou, raramente, perda natural da rede).

Lê o CSV/resumo gerado pelo cliente com --timeout-mode fixed|adaptive.
"""
import argparse
import csv
import os
from collections import defaultdict

import matplotlib.pyplot as plt

E3 = os.path.join("entregas", "entrega3", "dados")
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
COLORS = {"saw": BLUE, "gbn": ORANGE, "sr": AQUA}
NAMES = {"saw": "SAW", "gbn": "GBN", "sr": "SR"}
MODE = {"fixed": "fixo", "adaptive": "adaptativo"}     # valores de timeout_mode -> rótulo


def style(ax, xlabel, ylabel, title=None):
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    if title:
        ax.set_title(title, color=INK, loc="left", fontsize=11)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)


def read_summary(path):
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if r["md5_ok"] == "1" and r["done_ok"] == "1"]
    if not rows:
        raise SystemExit(f"Nenhuma execução válida em {path}")
    return rows


def mean(xs):
    return sum(xs) / len(xs)


def stats(rows):
    """Médias de um grupo de execuções do mesmo cenário."""
    f = lambda k: mean([float(r[k]) for r in rows])
    retx = f("retransmissoes")
    drops = f("dados_descartados_simulados")
    return {
        "n": len(rows), "tempo": f("tempo_total_s"), "kbps": f("throughput_medido_kbps"),
        "retx": retx, "drops": drops, "espurias": max(0.0, retx - drops),
        "timeouts": f("segmentos_com_timeout"), "rtt": f("rtt_medio_ms"),
        "to_medio": f("timeout_medio_ms"),
    }


def write_csv(path, header, lines):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(lines)
    print(f"-> {path}")


# ---------------------------------------------------------------------------
def cmd_serie(args):
    seg, rtt, est, to, used, tmo = [], [], [], [], [], []
    with open(args.csv) as f:
        for r in csv.DictReader(f):
            s = int(r["segment"])
            if s < args.inicio or (args.fim is not None and s > args.fim):
                continue
            seg.append(s)
            rtt.append(float(r["rtt_ms"]))
            est.append(float(r["rtt_estimated_ms"]) if r["rtt_estimated_ms"] else None)
            to.append(float(r["timeout_ms"]))
            # Karn: só segmentos sem retransmissão entram na EWMA
            used.append(r["retransmissions"] == "0")
            tmo.append(r["timeout_occurred"] == "1")
            proto, window = r["protocol"], r["window_size"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ok = [i for i, u in enumerate(used) if u]
    no = [i for i, u in enumerate(used) if not u]
    ax1.scatter([seg[i] for i in ok], [rtt[i] for i in ok], s=6, color="#b5b3ad",
                label="RTT medido (amostra usada)", zorder=2)
    ax1.scatter([seg[i] for i in no], [rtt[i] for i in no], s=10, marker="x", color=ORANGE,
                label="RTT medido de segmento retransmitido (ignorado — Karn)", zorder=3)
    ax1.plot(seg, est, lw=1.6, color=BLUE, label="RTT estimado (EWMA)", zorder=4)
    style(ax1, "", "RTT (ms)", "RTT medido × RTT estimado por segmento")
    ax1.legend(frameon=False, fontsize=8, loc="upper right")
    hi = sorted(rtt)[int(0.995 * (len(rtt) - 1))]
    ax1.set_ylim(0, hi * 1.25)

    ax2.plot(seg, to, lw=1.4, color=ORANGE, label="timeout vigente")
    ax2.plot(seg, est, lw=1.2, color=BLUE, label="RTT estimado")
    tx = [seg[i] for i, t in enumerate(tmo) if t]
    ax2.scatter(tx, [0] * len(tx), marker="|", s=80, color=INK, label=f"timeout ({len(tx)})",
                clip_on=False, zorder=5)
    style(ax2, "segmento", "ms", "Timeout ao longo da transferência (RTT_est + 4·DevRTT)")
    ax2.legend(frameon=False, fontsize=8, loc="upper right")
    ax2.set_ylim(0, max(to) * 1.1)
    fig.suptitle(f"{NAMES.get(proto, proto)}-{window} — {os.path.basename(args.csv)}",
                 color=INK2, fontsize=9, x=0.01, ha="left")
    fig.tight_layout()
    base = os.path.splitext(args.csv)[0]
    out = f"{base}_rtt.png" if args.fim is None and args.inicio == 0 else \
        f"{base}_rtt_{args.inicio}-{args.fim}.png"
    fig.savefig(out, dpi=150)
    print(f"-> {out}")


# ---------------------------------------------------------------------------
def cmd_varredura(args):
    rows = [r for r in read_summary(args.resumo) if r["timeout_mode"] == "adaptive"]
    if not rows:
        raise SystemExit(f"Nenhuma execução adaptativa em {args.resumo}")
    groups = defaultdict(list)
    for r in rows:
        groups[(float(r["perda_simulada"]), float(r["alpha"]), float(r["beta"]))].append(r)
    st = {k: stats(v) for k, v in groups.items()}
    losses = sorted({k[0] for k in st})
    alphas = sorted({k[1] for k in st})
    betas = sorted({k[2] for k in st})

    lines = []
    for k in sorted(st):
        s = st[k]
        lines.append([f"{k[0]:g}", f"{k[1]:g}", f"{k[2]:g}", s["n"], f"{s['tempo']:.2f}",
                      f"{s['kbps']:.1f}", f"{s['retx']:.0f}", f"{s['drops']:.0f}",
                      f"{s['espurias']:.0f}", f"{s['to_medio']:.1f}", f"{s['rtt']:.1f}"])
    outdir = os.path.dirname(args.resumo)
    write_csv(os.path.join(outdir, "tabela_varredura.csv"),
              ["perda", "alpha", "beta", "execucoes", "tempo_s", "throughput_kbps", "retx",
               "descartes_sim", "retx_espurias", "timeout_medio_ms", "rtt_medio_ms"], lines)

    print(f"\n{'perda':>5} {'α':>7} {'β':>6} {'kbps':>8} {'retx':>6} {'espúr.':>7} {'TO médio':>9}")
    for l in lines:
        print(f"{l[0]:>5} {l[1]:>7} {l[2]:>6} {l[5]:>8} {l[6]:>6} {l[8]:>7} {l[9]:>9}")

    # Mapas de calor: linhas = métrica, colunas = perda.  Uma escala por linha (um único matiz).
    metrics = [("kbps", "Throughput médio (kbps)", "Blues"),
               ("espurias", "Retransmissões espúrias", "Oranges"),
               ("to_medio", "Timeout médio (ms)", "Greys")]
    fig, axes = plt.subplots(len(metrics), len(losses),
                             figsize=(4 * len(losses), 3.3 * len(metrics)), squeeze=False)
    for i, (key, title, cmap) in enumerate(metrics):
        vals = [st[(l, a, b)][key] for l in losses for a in alphas for b in betas if (l, a, b) in st]
        vmin, vmax = min(vals), max(vals)
        for j, l in enumerate(losses):
            ax = axes[i][j]
            M = [[st.get((l, a, b), {}).get(key, float("nan")) for b in betas] for a in alphas]
            ax.imshow(M, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
            for ia in range(len(alphas)):
                for ib in range(len(betas)):
                    v = M[ia][ib]
                    dark = (v - vmin) / max(vmax - vmin, 1e-9) > 0.55
                    ax.text(ib, ia, f"{v:.0f}", ha="center", va="center", fontsize=9,
                            color="white" if dark else INK)
            ax.set_xticks(range(len(betas)), [f"{b:g}" for b in betas])
            ax.set_yticks(range(len(alphas)), [f"{a:g}" for a in alphas])
            ax.set_xlabel("β", color=INK2)
            ax.set_ylabel("α", color=INK2)
            ax.set_title(f"{title} — perda {l * 100:g} %", fontsize=9, color=INK, loc="left")
            ax.tick_params(colors=INK2, length=0)
            for s in ax.spines.values():
                s.set_visible(False)
    fig.suptitle("SR-16, small — varredura α × β (média das execuções)", color=INK, x=0.01,
                 ha="left")
    fig.tight_layout()
    out = os.path.join(outdir, "varredura_alfa_beta.png")
    fig.savefig(out, dpi=150)
    print(f"-> {out}")


# ---------------------------------------------------------------------------
def cmd_comparacao(args):
    rows = read_summary(args.resumo)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["protocolo"], int(r["janela"]), float(r["perda_simulada"]),
                MODE[r["timeout_mode"]])].append(r)
    st = {k: stats(v) for k, v in groups.items()}
    lines = []
    for k in sorted(st):
        s = st[k]
        lines.append([NAMES[k[0]], k[1], f"{k[2] * 100:g}", k[3], s["n"], f"{s['tempo']:.2f}",
                      f"{s['kbps']:.1f}", f"{s['retx']:.0f}", f"{s['drops']:.0f}",
                      f"{s['timeouts']:.0f}", f"{s['to_medio']:.1f}", f"{s['rtt']:.1f}"])
    outdir = os.path.dirname(args.resumo)
    header = ["protocolo", "janela", "perda_pct", "timeout", "execucoes", "tempo_s",
              "throughput_kbps", "retx", "descartes_sim", "seg_com_timeout", "timeout_medio_ms",
              "rtt_medio_ms"]
    write_csv(os.path.join(outdir, "tabela_fixo_vs_adaptativo.csv"), header, lines)
    for l in lines:
        print("  ".join(str(x) for x in l))

    # Barras agrupadas: throughput fixo × adaptativo por perda, um painel por protocolo
    protos = sorted({k[0] for k in st})
    losses = sorted({k[2] for k in st})
    fig, axes = plt.subplots(1, len(protos), figsize=(5.5 * len(protos), 4), sharey=True,
                             squeeze=False)
    for ax, p in zip(axes[0], protos):
        w = 0.38
        for d, (mode, color) in enumerate([("fixo", "#b5b3ad"), ("adaptativo", COLORS[p])]):
            xs = [i + (d - 0.5) * (w + 0.02) for i in range(len(losses))]
            ys = [st.get((p, 16, l, mode), {}).get("kbps", 0) for l in losses]
            bars = ax.bar(xs, ys, width=w, color=color, label=f"timeout {mode}")
            for b, y in zip(bars, ys):
                ax.text(b.get_x() + b.get_width() / 2, y, f"{y:.0f}", ha="center",
                        va="bottom", fontsize=8, color=INK2)
        ax.set_xticks(range(len(losses)), [f"{l * 100:g} %" for l in losses])
        style(ax, "perda simulada", "throughput médio (kbps)", f"{NAMES[p]}-16")
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    out = os.path.join(outdir, "fixo_vs_adaptativo.png")
    fig.savefig(out, dpi=150)
    print(f"-> {out}")


# ---------------------------------------------------------------------------
def cmd_final(args):
    rows = read_summary(args.resumo)
    latest = {}
    for r in rows:   # execução mais recente de cada (protocolo, janela, modo)
        latest[(r["protocolo"], int(r["janela"]), MODE[r["timeout_mode"]])] = r
    order = [("saw", 1, "fixo"), ("gbn", 16, "fixo"), ("gbn", 16, "adaptativo"),
             ("sr", 16, "fixo"), ("sr", 16, "adaptativo")]
    lines, labels, vals, colors = [], [], [], []
    for k in order:
        if k not in latest:
            continue
        r = latest[k]
        lines.append([NAMES[k[0]], k[1], k[2], r["throughput_medido_kbps"], r["retransmissoes"],
                      r["tempo_total_s"], r["rtt_medio_ms"], r["timeout_medio_ms"], r["md5"]])
        labels.append(f"{NAMES[k[0]]}-{k[1]}\n{k[2]}")
        vals.append(float(r["throughput_medido_kbps"]))
        colors.append(COLORS[k[0]])
    outdir = os.path.dirname(args.resumo)
    write_csv(os.path.join(outdir, "tabela_integrada.csv"),
              ["protocolo", "janela", "timeout", "throughput_kbps", "retransmissoes", "tempo_s",
               "rtt_medio_ms", "timeout_medio_ms", "md5"], lines)
    for l in lines:
        print("  ".join(str(x) for x in l))

    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(range(len(vals)), vals, color=colors, width=0.62)
    for i, (b, l) in enumerate(zip(bars, lines)):
        if l[2] == "fixo" and l[0] != "SAW":
            b.set_alpha(0.55)
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{vals[i]:.0f}", ha="center",
                va="bottom", fontsize=9, color=INK)
    ax.set_xticks(range(len(vals)), labels)
    style(ax, "", "throughput médio (kbps)", "Throughput médio — arquivo large, sem perda simulada")
    fig.tight_layout()
    out = os.path.join(outdir, "comparacao_final.png")
    fig.savefig(out, dpi=150)
    print(f"-> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serie")
    p.add_argument("csv")
    p.add_argument("--inicio", type=int, default=0)
    p.add_argument("--fim", type=int, default=None)
    p.set_defaults(fn=cmd_serie)
    for name, fn, sub_dir in [("varredura", cmd_varredura, "varredura"),
                              ("comparacao", cmd_comparacao, "comparacao"),
                              ("final", cmd_final, "large")]:
        p = sub.add_parser(name)
        p.add_argument("--resumo", default=os.path.join(E3, sub_dir, "resumo_entrega3.csv"))
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
