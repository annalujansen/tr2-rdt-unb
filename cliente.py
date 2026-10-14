#!/usr/bin/env python3
"""
Cliente RDT-UnB v1.0 — Entrega 1: Stop-and-Wait (SAW)

Transferência confiável de arquivo sobre UDP. O servidor é "pull-based":
ele só manda um segmento (DATA) quando o cliente pede (REQ). A confiabilidade
(timeout, retransmissão, verificação de integridade) é toda feita aqui no cliente.

Uso:
    python3 cliente.py --server 137.131.178.229 --group grupo01 --file small
"""

import argparse
import csv
import hashlib
import os
import socket
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
DEFAULT_PORT = 8080
DEFAULT_SEGMENT_SIZE = 512       # bytes de payload por segmento (recomendado no enunciado)
DEFAULT_TIMEOUT_MS = 500         # timeout FIXO (o adaptativo é a Entrega 3)
DEFAULT_MAX_RETRIES = 50         # desiste depois de tantas tentativas para o mesmo pacote
RECV_BUFFER = 65535              # maior datagrama UDP possível; garante que nada é truncado
PROTOCOL = "saw"
WINDOW_SIZE = 1                  # Stop-and-Wait = janela de tamanho 1


# ---------------------------------------------------------------------------
# Montagem e interpretação dos pacotes do protocolo RDT-UnB v1.0
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

    O payload é BINÁRIO e pode conter o byte '|' ou qualquer outro. Por isso
    dividimos no máximo 3 vezes (maxsplit=3): tudo o que vem depois do 3º '|'
    é payload, intacto. Também NÃO decodificamos o payload como texto.
    Retorna (seq, payload) ou None se não for um DATA válido.
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


# ---------------------------------------------------------------------------
# Envio com timeout e retransmissão (usado no handshake e no FIN)
# ---------------------------------------------------------------------------
def request_reply(sock, addr, message: bytes, expected_type: str, timeout_s, max_retries):
    """
    Envia `message` e espera uma resposta cujo tipo seja `expected_type`.
    Se não chegar dentro do timeout, retransmite. Pacotes de outro tipo
    (ex.: um DATA atrasado) são ignorados.
    """
    for attempt in range(max_retries):
        sock.sendto(message, addr)
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break  # estourou o timeout -> retransmite
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
# Programa principal
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Cliente RDT-UnB — Stop-and-Wait")
    ap.add_argument("--server", default="137.131.178.229", help="IP do servidor")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="porta UDP do servidor")
    ap.add_argument("--group", required=True, help="ID do grupo (obrigatório), ex.: grupo01")
    ap.add_argument("--file", choices=["small", "medium", "large"], default="small")
    ap.add_argument("--segment-size", type=int, default=DEFAULT_SEGMENT_SIZE)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS, help="timeout fixo em ms")
    ap.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    args = ap.parse_args()  # sem --group o argparse aborta com erro: o cliente não roda

    addr = (args.server, args.port)
    timeout_s = args.timeout / 1000.0

    # Socket UDP (SOCK_DGRAM). Nada de TCP em lugar nenhum.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ---------------- 1) Handshake HELLO / OK ----------------
    hello = f"HELLO|grupo={args.group}|segment_size={args.segment_size}|file={args.file}"
    print(f"-> {hello}")
    ptype, ok = request_reply(sock, addr, hello.encode(), "OK", timeout_s, args.max_retries)
    print(f"<- OK {ok}")

    file_size = int(ok["file_size"])
    expected_md5 = ok["checksum"]
    total_segments = int(ok["total_segments"])
    segment_size = int(ok["segment_size"])  # o servidor pode ajustar o valor pedido

    # ---------------- 2) Loop Stop-and-Wait: REQ -> DATA -> ACK ----------------
    received = bytearray()   # o arquivo é montado aqui, em ordem
    rows = []                # uma linha do CSV por segmento
    total_retx = 0
    total_timeouts = 0
    t_start = time.monotonic()

    for seq in range(total_segments):
        req = f"REQ|seq={seq}".encode()
        retransmissions = 0
        timeout_occurred = 0
        t_first_req = time.monotonic()   # 1º envio deste segmento (p/ throughput)
        payload = None

        while payload is None:
            if retransmissions > args.max_retries:
                raise RuntimeError(f"Segmento {seq}: excedeu {args.max_retries} retransmissões")

            t_sent = time.monotonic()    # último envio do REQ (p/ RTT)
            sock.sendto(req, addr)
            deadline = t_sent + timeout_s

            # Espera o DATA certo até o timeout. Pacotes de outro seq (duplicatas
            # atrasadas de retransmissões anteriores) são descartados.
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    data, _ = sock.recvfrom(RECV_BUFFER)
                except socket.timeout:
                    break
                parsed = parse_data_packet(data)
                if parsed is not None and parsed[0] == seq:
                    payload = parsed[1]
                    t_recv = time.monotonic()
                    break

            if payload is None:
                # Timeout: o REQ ou o DATA se perdeu -> retransmite o REQ
                retransmissions += 1
                timeout_occurred = 1

        # Confirma o segmento. Em SAW o próximo REQ é enviado logo em seguida.
        sock.sendto(f"ACK|seq={seq}".encode(), addr)
        received += payload

        rtt_ms = (t_recv - t_sent) * 1000.0
        seg_time = t_recv - t_first_req          # inclui os timeouts deste segmento
        throughput_kbps = (len(payload) * 8 / 1000.0) / seg_time
        total_retx += retransmissions
        total_timeouts += timeout_occurred

        rows.append({
            "segment": seq,
            "timestamp": datetime.now().astimezone().isoformat(timespec="microseconds"),
            "size_bytes": len(payload),
            "rtt_ms": f"{rtt_ms:.3f}",
            "rtt_estimated_ms": "",              # EWMA só na Entrega 3
            "timeout_ms": args.timeout,
            "throughput_kbps": f"{throughput_kbps:.3f}",
            "retransmissions": retransmissions,
            "timeout_occurred": timeout_occurred,
            "window_size": WINDOW_SIZE,
            "protocol": PROTOCOL,
        })

        if seq % 100 == 0 or seq == total_segments - 1:
            print(f"  seg {seq + 1}/{total_segments}  rtt={rtt_ms:.1f}ms  retx={retransmissions}")

    elapsed = time.monotonic() - t_start

    # ---------------- 3) Verificação de integridade (MD5) ----------------
    received = bytes(received[:file_size])
    md5 = hashlib.md5(received).hexdigest()
    print(f"MD5 recebido: {md5}")
    print(f"MD5 esperado: {expected_md5}  -> {'OK' if md5 == expected_md5 else 'DIFERENTE'}")

    # ---------------- 4) Encerramento FIN / DONE ----------------
    _, done = request_reply(sock, addr, f"FIN|checksum={md5}".encode(), "DONE",
                            timeout_s, args.max_retries)
    print(f"<- DONE ok={done.get('ok')}")
    sock.close()

    # ---------------- 5) Salva arquivo e CSV ----------------
    out_file = f"recebido_{args.group}_{args.file}.bin"
    with open(out_file, "wb") as f:
        f.write(received)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_name = f"metrics_{args.group}_{PROTOCOL}_{stamp}.csv"
    with open(csv_name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---------------- 6) Resumo ----------------
    rtts = [float(r["rtt_ms"]) for r in rows]
    avg_rtt = sum(rtts) / len(rtts)
    measured_kbps = file_size * 8 / 1000.0 / elapsed
    theoretical_kbps = segment_size * 8 / avg_rtt   # bits/ms == kbps
    print("\n===== RESUMO =====")
    print(f"Arquivo salvo:          {out_file} ({file_size} bytes, {total_segments} segmentos)")
    print(f"CSV:                    {csv_name}")
    print(f"Tempo total:            {elapsed:.2f} s")
    print(f"RTT médio:              {avg_rtt:.2f} ms (min {min(rtts):.2f}, max {max(rtts):.2f})")
    print(f"Retransmissões:         {total_retx}  (segmentos com timeout: {total_timeouts})")
    print(f"Throughput medido:      {measured_kbps:.2f} kbps")
    print(f"Throughput teórico SAW: {theoretical_kbps:.2f} kbps  (segment_size*8 / RTT médio)")
    print(f"Eficiência:             {100 * measured_kbps / theoretical_kbps:.1f}%")
    print(f"Checksum servidor:      {'OK' if done.get('ok') == '1' else 'FALHOU'}")

    # Uma linha por execução em resumo.csv -> vira a tabela teórico x medido do relatório
    summary = {
        "data_hora": datetime.now().astimezone().isoformat(timespec="seconds"),
        "grupo": args.group,
        "arquivo": args.file,
        "file_size": file_size,
        "segment_size": segment_size,
        "total_segments": total_segments,
        "tempo_total_s": f"{elapsed:.2f}",
        "rtt_medio_ms": f"{avg_rtt:.2f}",
        "throughput_teorico_kbps": f"{theoretical_kbps:.2f}",
        "throughput_medido_kbps": f"{measured_kbps:.2f}",
        "eficiencia_pct": f"{100 * measured_kbps / theoretical_kbps:.1f}",
        "retransmissoes": total_retx,
        "md5": md5,
        "done_ok": done.get("ok"),
        "csv": csv_name,
    }
    write_header = not os.path.exists("resumo.csv")
    with open("resumo.csv", "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        if write_header:
            w.writeheader()
        w.writerow(summary)

    if md5 != expected_md5 or done.get("ok") != "1":
        sys.exit(1)


if __name__ == "__main__":
    main()
