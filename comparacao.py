#!/usr/bin/env python3
"""
Comparação SAW × GBN × SR (Entrega 2) a partir de resultados/resumo_entrega2.csv.

Uso:
    .venv/bin/python comparacao.py [--resumo resultados/resumo_entrega2.csv]
                                   [--grupo grupo10] [--arquivo small] [--saida resultados]

Gera, na pasta de saída:
  tabela_comparativa.csv   formato do enunciado: uma linha por protocolo × janela e, para
                           Sem perda / 5% / 10%, throughput médio, retransmissões e tempo total
  tabela_comparativa.tex   a mesma tabela em LaTeX, para colar no Overleaf
  comparacao_segmentos_w<J>_loss<P>.png   GBN × SR com a mesma janela (--janela) e perda 5% e
                           10%: throughput e retransmissões acumuladas ao longo da transferência
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


def table_rows():
    """Linhas da tabela do enunciado: SAW 1, GBN 4/8/16, SR 4/8/16."""
    yield ("saw", 1)
    for proto in ("gbn", "sr"):
        for w in WINDOWS:
            yield (proto, w)


def write_tables(data, outdir):
    """Tabela no formato do enunciado: uma linha por protocolo × janela e, para cada
    cenário de perda (Sem perda / 5% / 10%), throughput médio, retransmissões e tempo total."""
    loss_tag = {0.0: "0", 0.05: "5", 0.10: "10"}
    cols = ["protocolo", "janela"]
    for loss in LOSSES:
        t = loss_tag[loss]
        cols += [f"throughput_kbps_{t}", f"retransmissoes_{t}", f"tempo_s_{t}"]

    rows = []
    for proto, w in table_rows():
        row = {"protocolo": NAMES[proto], "janela": w}
        for loss in LOSSES:
            r = data.get((proto, w, loss))
            t = loss_tag[loss]
            row[f"throughput_kbps_{t}"] = r["throughput_medido_kbps"] if r else "-"
            row[f"retransmissoes_{t}"] = r["retransmissoes"] if r else "-"
            row[f"tempo_s_{t}"] = r["tempo_total_s"] if r else "-"
        rows.append(row)

    csv_path = os.path.join(outdir, "tabela_comparativa.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    tex_path = os.path.join(outdir, "tabela_comparativa.tex")
    with open(tex_path, "w") as f:
        f.write("\\begin{tabular}{lr|rrr|rrr|rrr}\n\\hline\n")
        f.write(" & & \\multicolumn{3}{c|}{Sem perda} & \\multicolumn{3}{c|}{5\\% perda} "
                "& \\multicolumn{3}{c}{10\\% perda} \\\\\n")
        f.write("Protocolo & Janela" + " & Thr. (kbps) & Retx. & Tempo (s)" * 3 + " \\\\\n\\hline\n")
        for r in rows:
            f.write(f"{r['protocolo']} & {r['janela']} & "
                    + " & ".join(str(r[c]) for c in cols[2:]) + " \\\\\n")
        f.write("\\hline\n\\end{tabular}\n")

    # Também imprime no terminal, para conferir na hora
    print(f"{'':<10}" + "".join(f"{h:^27}" for h in ("Sem perda", "5% perda", "10% perda")))
    print(f"{'prot':<5}{'jan':>4} " + f"{'kbps':>10}{'retx':>7}{'tempo_s':>10}" * 3)
    for r in rows:
        print(f"{r['protocolo']:<5}{r['janela']:>4} "
              + "".join(f"{r[c]:>10}" if c.startswith(("throughput", "tempo")) else f"{r[c]:>7}"
                        for c in cols[2:]))
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


def segment_series(csv_path, k):
    """Lê o CSV por segmento e devolve as séries na ordem em que os DATA foram ACEITOS:
      xs   = nº de segmentos já recebidos (posição na transferência)
      thr  = throughput dos últimos k segmentos: bits recebidos / tempo que levaram (kbps)
      retx = retransmissões acumuladas até ali
    (O throughput_kbps de cada linha é muito ruidoso; a janela de k segmentos suaviza.)"""
    csv_path = csv_path.replace("\\", "/")      # resumos gravados no Windows
    with open(csv_path) as f:
        rows = sorted(csv.DictReader(f), key=lambda r: float(r["recv_time_ms"]))
    t = [0.0] + [float(r["recv_time_ms"]) for r in rows]
    bits = [0] + [int(r["size_bytes"]) * 8 for r in rows]
    for i in range(1, len(bits)):
        bits[i] += bits[i - 1]
    xs, thr, retx, acc = [], [], [], 0
    for i, r in enumerate(rows, start=1):
        j = max(0, i - k)
        xs.append(i)
        thr.append((bits[i] - bits[j]) / max(t[i] - t[j], 1e-3))   # bits/ms = kbps
        acc += int(r["retransmissions"])
        retx.append(acc)
    return xs, thr, retx


def plot_segments(data, outdir, w, loss, k=50):
    """GBN × SR com a MESMA janela e perda, ao longo da transferência.
    Em cima: throughput (média dos últimos k segmentos). Embaixo: retransmissões acumuladas."""
    runs = {p: data.get((p, w, loss)) for p in ("gbn", "sr")}
    if not all(runs.values()):
        return None
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    all_thr = []
    for proto, r in runs.items():
        xs, thr, retx = segment_series(r["csv"], k)
        all_thr += thr
        label = f"{NAMES[proto]}: {r['tempo_total_s']} s, {r['retransmissoes']} retransmissões"
        ax1.plot(xs, thr, lw=1.3, color=COLORS[proto], label=label)
        ax2.plot(xs, retx, lw=2, color=COLORS[proto], label=label)
    style(ax1, "", f"Throughput (kbps, últimos {k} segm.)",
          f"GBN × SR por segmento — janela {w}, perda simulada {loss * 100:g}%")
    # Rajadas raras (vários DATA chegando quase juntos) achatariam o resto do gráfico:
    # corta o eixo no percentil 99.
    ax1.set_ylim(0, 1.2 * sorted(all_thr)[int(0.99 * (len(all_thr) - 1))])
    style(ax2, "Segmentos recebidos (ordem de aceitação)", "Retransmissões acumuladas",
          "Retransmissões ao longo da transferência")
    fig.tight_layout()
    out = os.path.join(outdir, f"comparacao_segmentos_w{w}_loss{loss * 100:g}.png")
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
    outputs = [*write_tables(data, args.saida), plot_by_loss(data, args.saida, args.janela),
               plot_by_window(data, args.saida)]
    outputs += [plot_segments(data, args.saida, args.janela, loss) for loss in LOSSES[1:]]
    for path in outputs:
        if path:
            print(f"Gerado: {path}")


if __name__ == "__main__":
    main()
