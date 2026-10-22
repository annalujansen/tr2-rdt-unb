"""
sr.py — Selective Repeat (Vinícius).   Interface: run(sess) -> (payloads, rows)

Estado típico:  base, next_seq, payloads = [None] * sess["total_segments"] (buffer de fora de ordem)
Funções do comum.py (todas recebem `sess` como 1º argumento):
    send_req(sess, seq)         envia REQ e registra o envio; sess["last_send"][seq] = instante (timer por segmento)
    recv_data(sess, deadline)   -> (seq, payload, t_recv) | None (timeout). Já aplica a perda simulada.
    send_ack(sess, seq)         confirma
    make_row(sess, seq, payload, t_recv, sess["window"])   linha do CSV
    progress(sess, n_done)      log opcional
Devolva:  payloads, rows   (rows pode estar fora de ordem; finish() ordena)
"""
from comum import make_row, progress, recv_data, send_ack, send_req  # noqa: F401


def run(sess):
    raise NotImplementedError("SR: implementar (Vinícius)")
