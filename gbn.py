"""
gbn.py — Go-Back-N (Anna).   Interface: run(sess) -> (payloads, rows)

Funções do comum.py (todas recebem `sess` como 1º argumento):
    send_req(sess, seq)         envia REQ e registra o envio (retransmissão = chamar de novo)
    recv_data(sess, deadline)   -> (seq, payload, t_recv) | None (timeout). Já aplica a perda simulada.
    send_ack(sess, seq)         confirma o segmento ao servidor
    make_row(sess, seq, payload, t_recv, window_size, timeout_occurred)   linha do CSV
    progress(sess, n_done)      log de progresso
Devolve: payloads (em ordem) e rows (uma linha do CSV por segmento)
"""
import time

from comum import make_row, progress, recv_data, send_ack, send_req


def run(sess):
    total = sess["total_segments"]
    N = sess["window"]
    # Como o GBN só aceita em ordem, os payloads chegam na ordem certa
    payloads, rows = [], []
    base, next_seq = 0, 0   # base = 1º segmento não recebido; next_seq = próximo sem REQ
    timer_start = None      # o ÚNICO temporizador do GBN (é o da base)
    timed_out = set()       # segmentos que estavam na base quando o timer estourou

    while base < total:
        # 1) Enche a janela: manda REQ até ter N pendentes (base .. base+N-1)
        while next_seq < base + N and next_seq < total:
            t = send_req(sess, next_seq)
            if next_seq == base:
                timer_start = t #inicia o temporizador da base
            next_seq += 1

        # 2) Espera algum DATA até o temporizador da base estourar.
        # No GBN há um temporizador: o da base. O prazo usa o RTO guardado
        # quando o REQ da base foi enviado (também após reiniciar o timer).
        pacote = recv_data(sess, timer_start + sess["timeout_at_send"][base])
        if pacote is None:
            # 3) Timeout da base: "volta N" -> reenvia a base e todos os seguintes,
            # mesmo os que talvez já tenham chegado (e foram descartados).
            timed_out.add(base)
            for s in range(base, next_seq):
                send_req(sess, s)
            timer_start = sess["last_send"][base]  # novo timer da base retransmitida
            continue

        seq, data, t_recv = pacote
        if seq != base:
            # DATA fora de ordem (seq > base) ou duplicata atrasada (seq < base):
            # o GBN não tem buffer, então descarta. Será pedido de novo no "volta N".
            continue

        # 4) Chegou o DATA da base: confirma, guarda e desliza a janela
        send_ack(sess, seq)
        payloads.append(data)
        # timeout_occurred explícito: só marca o segmento que estava na base no timeout,
        # não os que foram reenviados
        rows.append(make_row(sess, seq, data, t_recv, window_size=N,
                             timeout_occurred=int(seq in timed_out)))
        base += 1
        progress(sess, base)
        # Ainda há REQs em voo: o temporizador recomeça para a nova base.
        # Se a janela esvaziou, o passo 1 religa o temporizador no próximo envio.
        timer_start = t_recv

    return payloads, rows
