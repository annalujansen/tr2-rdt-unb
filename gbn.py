"""
gbn.py — Go-Back-N (Anna).   Interface: run(sess) -> (payloads, rows)

Estado típico:  base, next_seq, payloads = [None] * sess["total_segments"]
Funções do comum.py (todas recebem `sess` como 1º argumento):
    send_req(sess, seq)         envia REQ e registra o envio (retransmissão = chamar de novo)
    recv_data(sess, deadline)   -> (seq, payload, t_recv) | None (timeout). Já aplica a perda simulada.
    send_ack(sess, seq)         confirma
    make_row(sess, seq, payload, t_recv, sess["window"])   linha do CSV
    progress(sess, n_done)      log opcional
Valores úteis: sess["window"], sess["timeout_s"], sess["last_send"][seq], sess["total_segments"]
Devolva:  payloads, rows
"""
from comum import make_row, progress, recv_data, send_ack, send_req  # noqa: F401


def run(sess):
    raise NotImplementedError("GBN: implementar (Anna)")
