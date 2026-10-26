"""
saw.py — Stop-and-Wait (janela = 1).

Mesma lógica da Entrega 1: REQ -> espera DATA(seq) -> ACK -> próximo REQ.
O envio, o recebimento (com perda simulada) e a contabilidade estão em comum.py.
Interface: run(sess) -> (payloads, rows)
"""
from comum import make_row, progress, recv_data, send_ack, send_req


def run(sess):
    payloads, rows = [], []

    for seq in range(sess["total_segments"]):
        payload = None
        while payload is None:
            t_sent = send_req(sess, seq)                 # (re)envia o REQ
            deadline = t_sent + sess["timeout_s"]

            # Espera o DATA certo até o timeout. DATA de outro seq (duplicata
            # atrasada de uma retransmissão anterior) é descartado.
            while payload is None:
                pkt = recv_data(sess, deadline)
                if pkt is None:
                    break                                # timeout -> reenvia o REQ
                got_seq, data, t_recv = pkt
                if got_seq == seq:
                    payload = data

        send_ack(sess, seq)
        payloads.append(payload)
        rows.append(make_row(sess, seq, payload, t_recv, window_size=1))
        progress(sess, seq + 1)

    return payloads, rows
