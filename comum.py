#!/usr/bin/env python3
"""
comum.py — código compartilhado por SAW, GBN e SR (Entrega 2).  SEM classes.

O estado compartilhado (socket, contadores, timeout...) fica num DICIONÁRIO `sess`,
criado por new_session() e passado como 1º argumento para todas as funções:

    send_req(sess, seq)         recv_data(sess, deadline)        make_row(sess, ...)

Ler um valor:    sess["timeout_s"]          Mudar um valor:   sess["timeout_s"] = 0.3

Tudo o que NÃO depende do protocolo de janela fica aqui:
  * leitura dos pacotes RDT-UnB v1.0
  * handshake HELLO/OK e encerramento FIN/DONE
  * simulação de perda (descarta o DATA recebido com probabilidade P)
  * contabilidade por segmento (envios, retransmissões, perdas simuladas)
  * CSV por segmento, resumo e verificação de MD5

Cada protocolo (saw.py, gbn.py, sr.py) só decide QUANDO enviar REQ e O QUE fazer
com cada DATA recebido. No fim devolve (payloads, rows) e o cliente chama finish().
"""

import csv
import hashlib
import os
import random
import socket
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
DEFAULT_PORT = 8080
DEFAULT_SEGMENT_SIZE = 512
DEFAULT_TIMEOUT_MS = 500          # timeout FIXO (o adaptativo é a Entrega 3)
DEFAULT_MAX_RETRIES = 50
RECV_BUFFER = 65535

# Colunas do CSV por segmento: as da especificação + simulated_loss, sim_drops, recv_time_ms
SEGMENT_COLUMNS = [
    "segment", "timestamp", "size_bytes", "rtt_ms", "rtt_estimated_ms", "dev_rtt_ms", "timeout_ms",
    "throughput_kbps", "retransmissions", "timeout_occurred", "window_size", "protocol",
    "simulated_loss", "sim_drops", "recv_time_ms", "timeout_mode", "alpha", "beta",
]

# Colunas do resumo (uma linha por execução) -> base da tabela comparativa
SUMMARY_COLUMNS = [
    "data_hora", "grupo", "protocolo", "janela", "perda_simulada", "seed", "arquivo",
    "file_size", "segment_size", "total_segments", "tempo_total_s", "rtt_medio_ms",
    "throughput_teorico_kbps", "throughput_medido_kbps", "eficiencia_pct",
    "retransmissoes", "segmentos_com_timeout", "segmentos_com_perda_simulada",
    "dados_descartados_simulados", "md5", "md5_ok", "done_ok", "csv",
]

DELIVERY3_SUMMARY_COLUMNS = SUMMARY_COLUMNS[:-1] + [
    "timeout_mode", "alpha", "beta", "rtt_inicial_ms", "dev_rtt_final_ms", "csv",
]


# ---------------------------------------------------------------------------
# Pacotes RDT-UnB v1.0 (igual à Entrega 1)
# ---------------------------------------------------------------------------
def parse_fields(parts):
    """Converte ['seq=3', 'total=512'] em {'seq': '3', 'total': '512'}."""
    fields = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            fields[k] = v
    return fields


def parse_text_packet(data: bytes):
    """Pacotes de controle (OK, DONE, PONG) são texto puro: TIPO|k=v|k=v."""
    parts = data.decode("utf-8", errors="replace").strip().split("|")
    return parts[0], parse_fields(parts[1:])


def parse_data_packet(data: bytes):
    """
    DATA|seq=<n>|total=<bytes>|<payload_binário>
    Divide no máximo 3 vezes: o que vem depois do 3º '|' é payload intacto
    (o payload é binário e pode conter '|'). Retorna (seq, payload) ou None.
    """
    if not data.startswith(b"DATA|"):
        return None
    parts = data.split(b"|", 3)
    if len(parts) < 4:
        return None
    fields = parse_fields([p.decode("ascii", errors="replace") for p in parts[1:3]])
    try:
        seq = int(fields["seq"])
    except (KeyError, ValueError):
        return None
    return seq, parts[3]


def request_reply(sock, addr, message: bytes, expected_type: str, timeout_s, max_retries):
    """Envia `message` e espera resposta do tipo `expected_type`; retransmite no timeout.
    Usado só no HELLO/OK e no FIN/DONE (que NÃO sofrem perda simulada)."""
    for attempt in range(max_retries):
        sock.sendto(message, addr)
        deadline = time.perf_counter() + timeout_s
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, _ = sock.recvfrom(RECV_BUFFER)
            except socket.timeout:
                break
            if data.startswith(expected_type.encode() + b"|") or data == expected_type.encode():
                return parse_text_packet(data)
        print(f"  [timeout] sem {expected_type}, retransmitindo ({attempt + 1}/{max_retries})")
    raise RuntimeError(f"Servidor não respondeu {expected_type} após {max_retries} tentativas")


# ---------------------------------------------------------------------------
# Sessão = dicionário com o estado compartilhado
# ---------------------------------------------------------------------------
def new_session(args):
    # A seed fica no resumo: qualquer execução com perda simulada pode ser repetida.
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    return {
        "args": args,
        "protocol": args.protocol,
        "window": 1 if args.protocol == "saw" else args.window,
        "addr": (args.server, args.port),
        "timeout_s": args.timeout / 1000.0,     # Entrega 3: o protocolo pode mudar este valor
        "rtt_est_ms": None,                     # Entrega 3: RTT estimado pela EWMA (None = fixo)
        "dev_rtt_ms": None,
        "initial_rtt_ms": None,
        "timeout_at_send": {},
        "alpha": args.alpha,
        "beta": args.beta,
        "max_retries": args.max_retries,
        "sock": socket.socket(socket.AF_INET, socket.SOCK_DGRAM),   # UDP
        "loss": args.loss,                      # probabilidade de descartar cada DATA
        "seed": seed,
        "rng": random.Random(seed),             # gerador do sorteio de perda
        # contabilidade por segmento (chave = seq)
        "sends": {},                            # quantas vezes o REQ do seq foi enviado
        "last_send": {},                        # instante (perf_counter) do último REQ do seq
        "sim_drops": {},                        # quantos DATA do seq a simulação descartou
        "total_sim_drops": 0,
        # preenchidos no handshake()
        "file_size": None, "expected_md5": None, "total_segments": None, "segment_size": None,
        "t_start": None, "last_arrival": None,
    }


def handshake(sess):
    a = sess["args"]
    hello = f"HELLO|grupo={a.group}|segment_size={a.segment_size}|file={a.file}"
    print(f"-> {hello}")
    _, ok = request_reply(sess["sock"], sess["addr"], hello.encode(), "OK",
                          sess["timeout_s"], sess["max_retries"])
    print(f"<- OK {ok}")
    sess["file_size"] = int(ok["file_size"])
    sess["expected_md5"] = ok["checksum"]
    sess["total_segments"] = int(ok["total_segments"])
    sess["segment_size"] = int(ok["segment_size"])      # o servidor pode ajustar
    print(f"Protocolo={sess['protocol']}  janela={sess['window']}  "
          f"perda simulada={a.loss:.0%}  seed={sess['seed']}")
    print(f"Timeout={a.timeout_mode}  RTO inicial/fixo={a.timeout} ms" +
          (f"  alpha={a.alpha:g} beta={a.beta:g}" if a.timeout_mode == "adaptive" else ""))
    sess["t_start"] = sess["last_arrival"] = time.perf_counter()


# ---------------------------------------------------------------------------
# Primitivas que os protocolos usam
# ---------------------------------------------------------------------------
def send_req(sess, seq):
    """Envia REQ|seq e registra o envio. Devolve o instante do envio."""
    if sess["sends"].get(seq, 0) > sess["max_retries"]:
        raise RuntimeError(f"Segmento {seq}: excedeu {sess['max_retries']} retransmissões")
    now = time.perf_counter()
    sess["timeout_at_send"][seq] = sess["timeout_s"]
    sess["sock"].sendto(f"REQ|seq={seq}".encode(), sess["addr"])
    sess["sends"][seq] = sess["sends"].get(seq, 0) + 1
    sess["last_send"][seq] = now
    return now


def update_rtt_estimator(sess, sample_ms):
    """Atualiza SRTT/DevRTT e o RTO adaptativo. Chamado só para amostra Karn-válida."""
    if sess["protocol"] not in ("gbn", "sr") or sess["args"].timeout_mode != "adaptive":
        return
    if sess["rtt_est_ms"] is None:
        # Inicialização recomendada pelo TCP: SRTT=R e RTTVAR=R/2.
        sess["rtt_est_ms"] = sample_ms
        sess["dev_rtt_ms"] = sample_ms / 2.0
        sess["initial_rtt_ms"] = sample_ms
    else:
        old_estimate = sess["rtt_est_ms"]
        sess["dev_rtt_ms"] = ((1 - sess["beta"]) * sess["dev_rtt_ms"]
                               + sess["beta"] * abs(sample_ms - old_estimate))
        sess["rtt_est_ms"] = ((1 - sess["alpha"]) * old_estimate
                              + sess["alpha"] * sample_ms)
    # Limites operacionais evitam RTO zero ou espera ilimitada em caminhos ruins.
    sess["timeout_s"] = min(60.0, max(0.001,
        (sess["rtt_est_ms"] + 4 * sess["dev_rtt_ms"]) / 1000.0))


def send_ack(sess, seq):
    sess["sock"].sendto(f"ACK|seq={seq}".encode(), sess["addr"])


def retransmissions(sess, seq):
    """Retransmissões do segmento = envios do REQ menos o primeiro."""
    return max(0, sess["sends"].get(seq, 0) - 1)


def should_drop(sess):
    """Sorteio da perda simulada: True com probabilidade P (= --loss)."""
    return sess["loss"] > 0 and sess["rng"].random() < sess["loss"]


def recv_data(sess, deadline):
    """
    Espera um DATA até `deadline` (instante absoluto de perf_counter).
    Devolve (seq, payload, t_recv) ou None se estourou o prazo.
    É AQUI que a perda é simulada: o DATA chegou de verdade, mas com
    probabilidade P é descartado antes de qualquer processamento, como se a
    rede o tivesse perdido. Cada descarte é contado em sim_drops[seq].
    """
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return None
        sess["sock"].settimeout(remaining)
        try:
            data, _ = sess["sock"].recvfrom(RECV_BUFFER)
        except socket.timeout:
            return None
        parsed = parse_data_packet(data)
        if parsed is None:
            continue                            # não é DATA (ex.: OK/DONE atrasado)
        seq, payload = parsed
        t_recv = time.perf_counter()
        if should_drop(sess):
            sess["sim_drops"][seq] = sess["sim_drops"].get(seq, 0) + 1
            sess["total_sim_drops"] += 1
            continue                            # "perdido": segue esperando até o deadline
        return seq, payload, t_recv


def make_row(sess, seq, payload, t_recv, window_size, timeout_occurred=None):
    """
    Linha do CSV para o segmento `seq`, chamada quando o DATA é ACEITO.
      rtt_ms          = t_recv - instante do ÚLTIMO REQ deste seq
      throughput_kbps = bits do segmento / tempo desde a chegada aceita anterior.
          (Em janela deslizante o tempo "REQ -> DATA" de um segmento não mede a
          vazão, porque vários segmentos estão em voo ao mesmo tempo. Assim a
          soma dos intervalos = tempo total, e a média ponderada pelo tempo
          bate com file_size*8/tempo_total.)
      simulated_loss  = 1 se algum DATA deste seq foi descartado pela simulação
      sim_drops       = quantos DATA deste seq foram descartados
    """
    retx = retransmissions(sess, seq)
    rtt_ms = (t_recv - sess["last_send"][seq]) * 1000.0
    if retx == 0:
        update_rtt_estimator(sess, rtt_ms)  # Karn: ignora amostras ambíguas após retransmissão.
    drops = sess["sim_drops"].get(seq, 0)
    dt = max(t_recv - sess["last_arrival"], 1e-6)
    sess["last_arrival"] = t_recv
    if timeout_occurred is None:
        timeout_occurred = int(retx > 0)
    rtt_est = sess["rtt_est_ms"]
    return {
        "segment": seq,
        "timestamp": datetime.now().astimezone().isoformat(timespec="microseconds"),
        "size_bytes": len(payload),
        "rtt_ms": f"{(t_recv - sess['last_send'][seq]) * 1000.0:.3f}",
        "rtt_estimated_ms": "" if rtt_est is None else f"{rtt_est:.3f}",
        "dev_rtt_ms": "" if sess["dev_rtt_ms"] is None else f"{sess['dev_rtt_ms']:.3f}",
        "timeout_ms": f"{sess['timeout_at_send'][seq] * 1000.0:g}",
        "throughput_kbps": f"{(len(payload) * 8 / 1000.0) / dt:.3f}",
        "retransmissions": retx,
        "timeout_occurred": timeout_occurred,
        "window_size": window_size,
        "protocol": sess["protocol"],
        "simulated_loss": int(drops > 0),
        "sim_drops": drops,
        "recv_time_ms": f"{(t_recv - sess['t_start']) * 1000.0:.3f}",
        "timeout_mode": sess["args"].timeout_mode,
        "alpha": f"{sess['alpha']:g}" if sess["args"].timeout_mode == "adaptive" else "",
        "beta": f"{sess['beta']:g}" if sess["args"].timeout_mode == "adaptive" else "",
    }


def progress(sess, n_done):
    if (n_done - 1) % 100 == 0 or n_done == sess["total_segments"]:
        retx = sum(max(0, s - 1) for s in sess["sends"].values())
        print(f"  {n_done}/{sess['total_segments']} segmentos  retx={retx}  "
              f"descartes simulados={sess['total_sim_drops']}")


# ---------------------------------------------------------------------------
# Encerramento: MD5, FIN/DONE, arquivo, CSV e resumo
# ---------------------------------------------------------------------------
def finish(sess, payloads, rows):
    """Devolve True se o MD5 e o DONE estiverem OK."""
    elapsed = time.perf_counter() - sess["t_start"]
    a = sess["args"]
    total = sess["total_segments"]
    rows = sorted(rows, key=lambda r: r["segment"])
    missing = [i for i, p in enumerate(payloads) if p is None]
    if len(payloads) != total or missing or len(rows) != total:
        raise RuntimeError(f"Transferência incompleta (faltam segmentos {missing[:10]}...)")

    received = b"".join(payloads)[:sess["file_size"]]
    md5 = hashlib.md5(received).hexdigest()
    md5_ok = md5 == sess["expected_md5"]
    print(f"MD5 recebido: {md5}")
    print(f"MD5 esperado: {sess['expected_md5']}  -> {'OK' if md5_ok else 'DIFERENTE'}")

    _, done = request_reply(sess["sock"], sess["addr"], f"FIN|checksum={md5}".encode(), "DONE",
                            sess["timeout_s"], sess["max_retries"])
    print(f"<- DONE ok={done.get('ok')}")
    sess["sock"].close()

    # ----- arquivos de saída -----
    # O nome do CSV segue a especificação (metrics_<grupo>_<protocolo>_<timestamp>.csv).
    # Cada cenário (arquivo, protocolo, janela, perda) tem a sua pasta, então
    # nada é sobrescrito e dá para saber de qual execução é cada CSV.
    tag = f"{sess['protocol']}_w{sess['window']}_loss{a.loss * 100:g}"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rundir = os.path.join(a.outdir, f"{a.file}_{tag}")
    os.makedirs(rundir, exist_ok=True)
    out_file = os.path.join(rundir, f"recebido_{a.group}_{a.file}.bin")
    csv_name = os.path.join(rundir, f"metrics_{a.group}_{sess['protocol']}_{stamp}.csv")
    with open(out_file, "wb") as f:
        f.write(received)
    with open(csv_name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SEGMENT_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    # ----- métricas -----
    rtts = [float(r["rtt_ms"]) for r in rows]
    avg_rtt = sum(rtts) / len(rtts)
    total_retx = sum(r["retransmissions"] for r in rows)
    seg_timeouts = sum(r["timeout_occurred"] for r in rows)
    seg_simloss = sum(r["simulated_loss"] for r in rows)
    measured_kbps = sess["file_size"] * 8 / 1000.0 / elapsed
    # Limite teórico sem perda: W segmentos por RTT (W=1 reduz à fórmula do SAW)
    theoretical_kbps = sess["window"] * sess["segment_size"] * 8 / avg_rtt
    eff = 100 * measured_kbps / theoretical_kbps

    print("\n===== RESUMO =====")
    print(f"Arquivo salvo:          {out_file} ({sess['file_size']} bytes, {total} segmentos)")
    print(f"CSV:                    {csv_name}")
    print(f"Tempo total:            {elapsed:.2f} s")
    print(f"RTT médio:              {avg_rtt:.2f} ms (min {min(rtts):.2f}, max {max(rtts):.2f})")
    print(f"Retransmissões:         {total_retx}  (segmentos com timeout: {seg_timeouts})")
    print(f"DATA descartados (sim): {sess['total_sim_drops']}  (segmentos afetados: {seg_simloss})")
    print(f"Throughput medido:      {measured_kbps:.2f} kbps")
    print(f"Throughput teórico:     {theoretical_kbps:.2f} kbps  (janela*segment_size*8 / RTT médio)")
    print(f"Eficiência:             {eff:.1f}%")
    print(f"Checksum servidor:      {'OK' if done.get('ok') == '1' else 'FALHOU'}")

    summary = {
        "data_hora": datetime.now().astimezone().isoformat(timespec="seconds"),
        "grupo": a.group, "protocolo": sess["protocol"], "janela": sess["window"],
        "perda_simulada": a.loss, "seed": sess["seed"], "arquivo": a.file,
        "file_size": sess["file_size"], "segment_size": sess["segment_size"],
        "total_segments": total, "tempo_total_s": f"{elapsed:.2f}",
        "rtt_medio_ms": f"{avg_rtt:.2f}",
        "throughput_teorico_kbps": f"{theoretical_kbps:.2f}",
        "throughput_medido_kbps": f"{measured_kbps:.2f}",
        "eficiencia_pct": f"{eff:.1f}",
        "retransmissoes": total_retx, "segmentos_com_timeout": seg_timeouts,
        "segmentos_com_perda_simulada": seg_simloss,
        "dados_descartados_simulados": sess["total_sim_drops"],
        "md5": md5, "md5_ok": int(md5_ok), "done_ok": done.get("ok"), "csv": csv_name,
    }
    # Preserva o conjunto oficial da Entrega 2 e mantém os experimentos da Entrega 3 separados.
    if a.timeout_mode == "fixed":
        path = os.path.join(a.outdir, "resumo_entrega2.csv")
        write_header = not os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
            if write_header:
                w.writeheader()
            w.writerow(summary)
    path3 = os.path.join(a.outdir, "resumo_entrega3.csv")
    write_header = not os.path.exists(path3)
    summary3 = {k: v for k, v in summary.items() if k != "csv"}
    summary3.update({
        "timeout_mode": a.timeout_mode,
        "alpha": f"{a.alpha:g}" if a.timeout_mode == "adaptive" else "",
        "beta": f"{a.beta:g}" if a.timeout_mode == "adaptive" else "",
        "rtt_inicial_ms": "" if sess["initial_rtt_ms"] is None else f"{sess['initial_rtt_ms']:.3f}",
        "dev_rtt_final_ms": "" if sess["dev_rtt_ms"] is None else f"{sess['dev_rtt_ms']:.3f}",
        "csv": csv_name,
    })
    with open(path3, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DELIVERY3_SUMMARY_COLUMNS)
        if write_header:
            w.writeheader()
        w.writerow(summary3)

    return md5_ok and done.get("ok") == "1"
