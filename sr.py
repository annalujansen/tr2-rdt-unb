"""
sr.py — Selective Repeat.   Interface: run(sess) -> (payloads, rows)

Ideia: o cliente mantém uma janela [base, base+N). Para cada segmento da janela
há um REQ enviado e um temporizador PRÓPRIO (sess["last_send"][seq] + timeout).
  * DATA dentro da janela e ainda não recebido -> ACK individual, guarda no buffer
    (mesmo fora de ordem) e gera a linha do CSV.
  * Timeout de um segmento -> reenvia o REQ SÓ daquele segmento (diferente do GBN).
  * A janela desliza (base avança) sobre os segmentos consecutivos já recebidos.
"""
import time

from comum import make_row, progress, recv_data, send_ack, send_req


def run(sess):
    total = sess["total_segments"]
    N = sess["window"]
    timeout = sess["timeout_s"]

    payloads = [None] * total      # buffer de recebidos (inclui os fora de ordem)
    received = [False] * total
    rows = []
    base, next_seq = 0, 0          # base = menor seq não recebido; next_seq = próximo sem REQ
    n_done = 0

    while base < total:
        # 1) Enche a janela: REQ para base .. base+N-1
        while next_seq < base + N and next_seq < total:
            send_req(sess, next_seq)
            next_seq += 1

        # 2) Pendentes = enviados na janela e ainda sem DATA. O próximo timeout
        #    é o do pendente com envio mais antigo (timer individual por segmento).
        pending = [s for s in range(base, next_seq) if not received[s]]
        deadline = min(sess["last_send"][s] for s in pending) + sess["timeout_s"]

        pkt = recv_data(sess, deadline)

        if pkt is None:
            # 3) Timeout: reenvia SOMENTE os segmentos cujo timer estourou.
            #    (recv_data já devolve None só quando o deadline passou)
            now = time.perf_counter()
            for s in pending:
                if now - sess["last_send"][s] >= sess["timeout_s"]:
                    send_req(sess, s)
            continue

        seq, data, t_recv = pkt

        # 4) Só aceita DATA da janela atual que ainda não foi recebido.
        #    Fora da janela / duplicata (retransmissão atrasada) é descartado.
        if not (base <= seq < next_seq) or received[seq]:
            continue

        send_ack(sess, seq)                    # ACK individual
        payloads[seq] = data
        received[seq] = True
        rows.append(make_row(sess, seq, data, t_recv, window_size=N))
        n_done += 1
        progress(sess, n_done)

        # 5) Desliza a janela sobre os segmentos consecutivos já recebidos
        while base < total and received[base]:
            base += 1

    return payloads, rows