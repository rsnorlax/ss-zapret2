#!/usr/bin/env python3
"""Verify SOCKS5 UDP ASSOCIATE and remote DNS resolution without dependencies."""

from __future__ import annotations

import argparse
import secrets
import socket
import struct


def recv_exact(stream: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise RuntimeError("SOCKS5 connection closed unexpectedly")
        data.extend(chunk)
    return bytes(data)


def read_address(stream: socket.socket, atyp: int) -> str:
    if atyp == 1:
        return socket.inet_ntop(socket.AF_INET, recv_exact(stream, 4))
    if atyp == 4:
        return socket.inet_ntop(socket.AF_INET6, recv_exact(stream, 16))
    if atyp == 3:
        length = recv_exact(stream, 1)[0]
        return recv_exact(stream, length).decode("ascii")
    raise RuntimeError(f"SOCKS5 returned unsupported address type {atyp}")


def udp_payload(packet: bytes) -> bytes:
    if len(packet) < 4 or packet[:2] != b"\x00\x00":
        raise RuntimeError("invalid SOCKS5 UDP response header")
    if packet[2] != 0:
        raise RuntimeError("fragmented SOCKS5 UDP responses are not supported")

    atyp = packet[3]
    offset = 4
    if atyp == 1:
        offset += 4
    elif atyp == 4:
        offset += 16
    elif atyp == 3:
        if len(packet) <= offset:
            raise RuntimeError("truncated SOCKS5 UDP domain header")
        offset += 1 + packet[offset]
    else:
        raise RuntimeError(f"unsupported SOCKS5 UDP address type {atyp}")

    offset += 2
    if len(packet) < offset:
        raise RuntimeError("truncated SOCKS5 UDP response")
    return packet[offset:]


def dns_query(domain: str, query_id: int) -> bytes:
    labels = domain.rstrip(".").encode("idna").split(b".")
    if not labels or any(not label or len(label) > 63 for label in labels):
        raise ValueError("invalid DNS name")
    qname = b"".join(bytes((len(label),)) + label for label in labels) + b"\x00"
    return struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + qname + struct.pack("!HH", 1, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1081)
    parser.add_argument("--domain", default="example.com")
    parser.add_argument("--dns-server", default="one.one.one.one")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), args.timeout) as control:
        control.settimeout(args.timeout)
        control.sendall(b"\x05\x01\x00")
        if recv_exact(control, 2) != b"\x05\x00":
            raise RuntimeError("SOCKS5 server rejected no-authentication mode")

        control.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
        version, reply, reserved, atyp = recv_exact(control, 4)
        if (version, reply, reserved) != (5, 0, 0):
            raise RuntimeError(f"SOCKS5 UDP ASSOCIATE failed with reply {reply}")
        relay_host = read_address(control, atyp)
        relay_port = struct.unpack("!H", recv_exact(control, 2))[0]
        if relay_host in {"0.0.0.0", "::"}:
            relay_host = args.host

        query_id = secrets.randbelow(65536)
        query = dns_query(args.domain, query_id)
        encoded_dns_server = args.dns_server.rstrip(".").encode("idna")
        if not encoded_dns_server or len(encoded_dns_server) > 255:
            raise ValueError("invalid DNS server name")
        request = (
            b"\x00\x00\x00\x03"
            + bytes((len(encoded_dns_server),))
            + encoded_dns_server
            + struct.pack("!H", 53)
            + query
        )

        relay = socket.getaddrinfo(relay_host, relay_port, type=socket.SOCK_DGRAM)[0]
        with socket.socket(relay[0], socket.SOCK_DGRAM) as udp:
            udp.settimeout(args.timeout)
            udp.sendto(request, relay[4])
            response = udp_payload(udp.recv(65535))

    if len(response) < 12:
        raise RuntimeError("truncated DNS response")
    response_id, flags, _, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
    if response_id != query_id or not flags & 0x8000:
        raise RuntimeError("invalid DNS response")
    if flags & 0x000F:
        raise RuntimeError(f"DNS query failed with RCODE {flags & 0x000F}")
    if answers == 0:
        raise RuntimeError("DNS response contained no answers")

    print(f"PASS: SOCKS5 UDP relay resolved {args.domain} with {answers} answer(s)")


if __name__ == "__main__":
    main()
