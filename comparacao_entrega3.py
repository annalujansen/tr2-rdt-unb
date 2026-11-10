#!/usr/bin/env python3
"""Compara execuções SR com RTO fixo e adaptativo registradas em resumo_entrega3.csv."""
import argparse
import csv
import os

import matplotlib.pyplot as plt


def load(path, grupo, arquivo, protocolo):
    fixed, adaptive = {}, {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if (row["grupo"] != grupo or row["arquivo"] != arquivo
                    or row["protocolo"] != protocolo or row["md5_ok"] != "1"):
                continue
            common = (row["grupo"], row["arquivo"], row["protocolo"], row["janela"],
                      row["perda_simulada"], row["seed"])
            key = common if row["timeout_mode"] == "fixed" else common + (row["alpha"], row["beta"])
            dest = fixed if row["timeout_mode"] == "fixed" else adaptive
            if key not in dest or row["data_hora"] > dest[key]["data_hora"]:
                dest[key] = row
    return fixed, adaptive


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resumo", default=os.path.join("resultados", "resumo_entrega3.csv"))
    ap.add_argument("--grupo", default="grupo10")
    ap.add_argument("--arquivo", default="small", choices=["small", "medium", "large"])
    ap.add_argument("--protocolo", default="sr", choices=["gbn", "sr"])
    ap.add_argument("--saida", default="resultados")
    args = ap.parse_args()
    fixed, adaptive = load(args.resumo, args.grupo, args.arquivo, args.protocolo)

    fields = ["arquivo", "janela", "perda_pct", "seed", "alpha", "beta",
              "retransmissoes_fixo", "tempo_fixo_s", "throughput_fixo_kbps",
              "retransmissoes_adaptativo", "tempo_adaptativo_s", "throughput_adaptativo_kbps",
              "delta_retransmissoes", "delta_tempo_pct", "delta_throughput_pct",
              "md5_fixo", "md5_adaptativo"]
    rows = []
    for key, a in adaptive.items():
        f = fixed.get(key[:6])
        if not f:
            continue
        t_fixed, t_adapt = float(f["tempo_total_s"]), float(a["tempo_total_s"])
        thr_fixed = float(f["throughput_medido_kbps"])
        thr_adapt = float(a["throughput_medido_kbps"])
        rows.append({
            "arquivo": args.arquivo, "janela": key[3], "perda_pct": 100 * float(key[4]),
            "seed": key[5], "alpha": a["alpha"], "beta": a["beta"],
            "retransmissoes_fixo": f["retransmissoes"], "tempo_fixo_s": f["tempo_total_s"],
            "throughput_fixo_kbps": f["throughput_medido_kbps"],
            "retransmissoes_adaptativo": a["retransmissoes"],
            "tempo_adaptativo_s": a["tempo_total_s"],
            "throughput_adaptativo_kbps": a["throughput_medido_kbps"],
            "delta_retransmissoes": int(a["retransmissoes"]) - int(f["retransmissoes"]),
            "delta_tempo_pct": f"{100 * (t_adapt / t_fixed - 1):.2f}",
            "delta_throughput_pct": f"{100 * (thr_adapt / thr_fixed - 1):.2f}",
            "md5_fixo": f["md5"], "md5_adaptativo": a["md5"],
        })

    if not rows:
        raise SystemExit("Nenhum par fixo/adaptativo encontrado. Rode os cenários pareados primeiro.")
    os.makedirs(args.saida, exist_ok=True)
    table = os.path.join(args.saida, "comparacao_entrega3.csv")
    with open(table, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (float(r["perda_pct"]), r["alpha"], r["beta"])))

    # Gráfico agrupado por perda e configuração; deixa explícito qual alpha/beta foi usado.
    labels = [f"{r['perda_pct']:g}%\nα={r['alpha']}, β={r['beta']}" for r in rows]
    x = list(range(len(rows)))
    width = 0.38
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(max(9, len(rows) * 1.1), 7), sharex=True)
    ax1.bar([i - width / 2 for i in x], [float(r["throughput_fixo_kbps"]) for r in rows],
            width, label="RTO fixo", color="#2a78d6")
    ax1.bar([i + width / 2 for i in x], [float(r["throughput_adaptativo_kbps"]) for r in rows],
            width, label="RTO adaptativo", color="#eb6834")
    ax1.set_ylabel("Throughput (kbps)")
    ax1.legend(frameon=False)
    ax1.grid(axis="y", alpha=0.25)
    ax2.bar([i - width / 2 for i in x], [int(r["retransmissoes_fixo"]) for r in rows],
            width, label="RTO fixo", color="#2a78d6")
    ax2.bar([i + width / 2 for i in x], [int(r["retransmissoes_adaptativo"]) for r in rows],
            width, label="RTO adaptativo", color="#eb6834")
    ax2.set_ylabel("Retransmissões")
    ax2.set_xticks(x, labels)
    ax2.grid(axis="y", alpha=0.25)
    fig.suptitle(f"{args.protocolo.upper()} — timeout fixo vs adaptativo ({args.arquivo}, janela {rows[0]['janela']})")
    fig.tight_layout()
    plot = os.path.join(args.saida, "comparacao_entrega3.png")
    fig.savefig(plot, dpi=150)
    plt.close(fig)
    print(f"Tabela: {table}\nGráfico: {plot}\nPares comparados: {len(rows)}")


if __name__ == "__main__":
    main()
