#!/usr/bin/env python3
"""
Comparação SAW × GBN × SR (Entrega 2) a partir de resultados/resumo_entrega2.csv.

Uso:
    .venv/bin/python comparacao.py [--resumo resultados/resumo_entrega2.csv]
                                   [--grupo grupo10] [--arquivo small] [--saida resultados]

Gera, na pasta de saída:
  tabela_comparativa.csv   uma linha por cenário (protocolo, janela, perda)
  tabela_comparativa.tex   a mesma tabela em LaTeX, para colar no Overleaf
  comparacao_perda.png     SAW × GBN × SR conforme a perda (GBN e SR com a janela de --janela)
                           -> por que o GBN sofre mais que o SR com perda alta
  comparacao_janela.png    GBN e SR conforme a janela -> impacto do tamanho da janela

Se o mesmo cenário foi rodado mais de uma vez, usa a execução MAIS RECENTE.
Execuções com MD5 errado ou de outro grupo/arquivo são ignoradas.
Cenários que ainda não foram rodados aparecem como "-" na tabela e somem do gráfico.
"""

import argparse
import csv
import os

import matplotlib.pyplot as plt

PROTOCOLS = ["saw", "gbn", "sr"]
NAMES = {"saw": "SAW", "gbn": "GBN", "sr": "SR"}
# Cores fixas por protocolo (nunca mudam entre gráficos) + marcador diferente,
# para quem não distingue as cores ou imprime em preto e branco.
COLORS = {"saw": "#2a78d6", "gbn": "#eb6834", "sr": "#1baf7a"}
MARKERS = {"saw": "s", "gbn": "o", "sr": "^"}
WINDOWS = [4, 8, 16]
LOSSES = [0.0, 0.05, 0.10]


def load(path, grupo, arquivo):
    """Lê o resumo e devolve {(protocolo, janela, perda): linha mais recente}."""
    best = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["grupo"] != grupo or r["arquivo"] != arquivo or r["md5_ok"] != "1":
                continue
            key = (r["protocolo"], int(r["janela"]), round(float(r["perda_simulada"]), 2))
            if key not in best or r["data_hora"] > best[key]["data_hora"]:
                best[key] = r
    return best


def scenarios():
    """Ordem da tabela: SAW (janela 1), depois GBN e SR com 4, 8, 16; cada um com 0, 5, 10%."""
    for loss in LOSSES:
        yield ("saw", 1, loss)
    for proto in ("gbn", "sr"):
        for w in WINDOWS:
            for loss in LOSSES:
                yield (proto, w, loss)


def write_tables(data, outdir):
    cols = ["protocolo", "janela", "perda_pct", "tempo_total_s", "throughput_medido_kbps",
            "retransmissoes", "dados_descartados_simulados", "rtt_medio_ms", "eficiencia_pct"]
    rows = []
    for proto, w, loss in scenarios():
        r = data.get((proto, w, loss))
        rows.append({
            "protocolo": NAMES[proto], "janela": w, "perda_pct": f"{loss * 100:g}",
            **{c: (r[c] if r else "-") for c in cols[3:]},
        })

    csv_path = os.path.join(outdir, "tabela_comparativa.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    tex_path = os.path.join(outdir, "tabela_comparativa.tex")
    with open(tex_path, "w") as f:
        f.write("\\begin{tabular}{lrrrrrr}\n\\hline\n")
        f.write("Protocolo & Janela & Perda (\\%) & Tempo (s) & Throughput (kbps) "
                "& Retransm. & Descartes sim. \\\\\n\\hline\n")
        for r in rows:
            f.write(f"{r['protocolo']} & {r['janela']} & {r['perda_pct']} & {r['tempo_total_s']} "
                    f"& {r['throughput_medido_kbps']} & {r['retransmissoes']} "
                    f"& {r['dados_descartados_simulados']} \\\\\n")
        f.write("\\hline\n\\end{tabular}\n")

    # Também imprime no terminal, para conferir na hora
    print(f"{'prot':<5}{'jan':>4}{'perda':>7}{'tempo_s':>10}{'kbps':>10}{'retx':>7}{'descartes':>11}")
    for r in rows:
        print(f"{r['protocolo']:<5}{r['janela']:>4}{r['perda_pct'] + '%':>7}{r['tempo_total_s']:>10}"
              f"{r['throughput_medido_kbps']:>10}{r['retransmissoes']:>7}"
              f"{r['dados_descartados_simulados']:>11}")
    return csv_path, tex_path



def point(data, proto, w, loss, field):
    r = data.get((proto, 1 if proto == "saw" else w, loss))
    return float(r[field]) if r else None


def draw(ax, xs, ys, proto, label):
    """Uma linha por protocolo; pula cenários que ainda não foram rodados."""
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if pts:
        px, py = zip(*pts)
        ax.plot(px, py, lw=2, color=COLORS[proto], marker=MARKERS[proto], ms=8, label=label)


def style(ax, xlabel, ylabel, title):
    ax.set_title(title, fontsize=11, loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3, lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=9)


def plot_by_loss(data, outdir, w):
    """Esquerda: throughput × perda. Direita: retransmissões × perda.
    O tempo total fica só na tabela (é o inverso do throughput: o mesmo gráfico de ponta-cabeça)."""
    xs = [l * 100 for l in LOSSES]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for proto in PROTOCOLS:
        label = "SAW" if proto == "saw" else f"{NAMES[proto]} (janela {w})"
        draw(ax1, xs, [point(data, proto, w, l, "throughput_medido_kbps") for l in LOSSES], proto, label)
        draw(ax2, xs, [point(data, proto, w, l, "retransmissoes") for l in LOSSES], proto, label)
    style(ax1, "Perda simulada (%)", "Throughput médio (kbps)", "Throughput")
    style(ax2, "Perda simulada (%)", "Retransmissões", "Retransmissões")
    for ax in (ax1, ax2):
        ax.set_xticks(xs)
    fig.tight_layout()
    out = os.path.join(outdir, "comparacao_perda.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_by_window(data, outdir):
    """Esquerda: throughput × janela SEM perda (a janela multiplica a vazão).
    Direita: retransmissões × janela com 10% de perda (o GBN paga N por perda, o SR ~1)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for proto in ("gbn", "sr"):
        draw(ax1, WINDOWS, [point(data, proto, w, 0.0, "throughput_medido_kbps") for w in WINDOWS],
             proto, NAMES[proto])
        draw(ax2, WINDOWS, [point(data, proto, w, 0.10, "retransmissoes") for w in WINDOWS],
             proto, NAMES[proto])
    for ax, loss in ((ax1, 0.0), (ax2, 0.10)):
        saw = point(data, "saw", 1, loss, "throughput_medido_kbps" if ax is ax1 else "retransmissoes")
        if saw is not None:
            ax.axhline(saw, color=COLORS["saw"], ls="--", lw=1.5, label="SAW (janela 1)")
    style(ax1, "Tamanho da janela", "Throughput médio (kbps)", "Throughput sem perda")
    style(ax2, "Tamanho da janela", "Retransmissões", "Retransmissões com 10% de perda")
    for ax in (ax1, ax2):
        ax.set_xticks(WINDOWS)
    fig.tight_layout()
    out = os.path.join(outdir, "comparacao_janela.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser(description="Tabela e gráficos comparativos SAW × GBN × SR")
    ap.add_argument("--resumo", default=os.path.join("resultados", "resumo_entrega2.csv"))
    ap.add_argument("--grupo", default="grupo10")
    ap.add_argument("--arquivo", default="small", choices=["small", "medium", "large"])
    ap.add_argument("--saida", default="resultados", help="pasta onde salvar tabela e gráficos")
    ap.add_argument("--janela", type=int, default=16, choices=WINDOWS,
                    help="janela do GBN/SR no gráfico por perda (padrão 16, a da Dica 3)")
    args = ap.parse_args()

    data = load(args.resumo, args.grupo, args.arquivo)
    if not data:
        raise SystemExit(f"Nenhuma execução de {args.grupo}/{args.arquivo} com MD5 OK em {args.resumo}")
    os.makedirs(args.saida, exist_ok=True)

    total = len(list(scenarios()))
    print(f"{len(data)} de {total} cenários encontrados ({args.grupo}, {args.arquivo})\n")
    for path in (*write_tables(data, args.saida), plot_by_loss(data, args.saida, args.janela),
                 plot_by_window(data, args.saida)):
        print(f"Gerado: {path}")


if __name__ == "__main__":
    main()
