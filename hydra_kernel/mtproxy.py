"""MTProto proxy connection helpers, including native FakeTLS (``ee``) links.

Telethon implements regular and ``dd`` MTProto proxies, but deliberately
normalizes an ``ee`` secret to its first 16 bytes and does not perform the
FakeTLS record handshake.  A real ``t.me/proxy?...&secret=ee...`` endpoint
therefore returns TLS-looking bytes which a normal MTProto packet codec reads
as a bogus (often negative) packet length.

This module keeps the extra handshake small and dependency-free.  It uses
Telethon's existing randomized-intermediate MTProto codec after the FakeTLS
layer has been negotiated, and is imported lazily only for a live client.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional


_TLS_RECORD_VERSION = b"\x03\x03"
_TLS_APPLICATION_DATA = 0x17
_TLS_CHANGE_CIPHER_SPEC = 0x14
_TLS_ALERT = 0x15
_TLS_HANDSHAKE = 0x16
_CLIENT_HELLO_SIZE = 517
_MAX_TLS_RECORD = 16_384 + 2_048


class FakeTLSHandshakeError(ConnectionError):
    """The server did not complete the authenticated MTProxy FakeTLS hello."""


@dataclass(frozen=True)
class FakeTLSSecret:
    """Parsed ``ee`` secret: a 16-byte HMAC key and the SNI domain bytes."""

    key: bytes
    domain: bytes

    @classmethod
    def parse(cls, value: Any) -> "FakeTLSSecret":
        if isinstance(value, bytes):
            try:
                text = value.decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError("FakeTLS secret must be ASCII hex") from exc
        else:
            text = str(value or "")
        text = "".join(text.split())
        if not text.lower().startswith("ee"):
            raise ValueError("FakeTLS secret must start with 'ee'")
        try:
            raw = bytes.fromhex(text)
        except ValueError as exc:
            raise ValueError("FakeTLS secret is not valid hexadecimal") from exc
        if len(raw) <= 17 or raw[0] != 0xEE:
            raise ValueError("FakeTLS secret must contain a key and a domain")
        key, domain = raw[1:17], raw[17:]
        if len(key) != 16 or not domain or len(domain) > 255:
            raise ValueError("FakeTLS secret has an invalid key or SNI domain")
        return cls(key=key, domain=domain)


def is_fake_tls_secret(value: Any) -> bool:
    """Whether a proxy secret is the hexadecimal FakeTLS form used by t.me."""

    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return False
    return str(value or "").strip().lower().startswith("ee")


@dataclass(frozen=True)
class _ClientHello:
    packet: bytes
    client_random: bytes
    session_id: bytes


def _extension(kind: int, data: bytes) -> bytes:
    return kind.to_bytes(2, "big") + len(data).to_bytes(2, "big") + data


def _x25519_looking_public_key() -> bytes:
    """Create a valid-looking X25519 u-coordinate without a crypto package."""

    field = (1 << 255) - 19
    seed = secrets.randbelow(field)
    return ((seed * seed) % field).to_bytes(32, "little")


def _build_client_hello(secret: FakeTLSSecret, *, now: Optional[int] = None) -> _ClientHello:
    """Build Telegram's 517-byte Chrome-shaped FakeTLS ClientHello.

    The HMAC is calculated while the TLS random field is all zeroes.  Its last
    four bytes are then XORed with the current Unix time, as specified by the
    MTProxy FakeTLS authentication scheme.
    """

    session_id = os.urandom(32)
    key_share = _x25519_looking_public_key()
    domain = secret.domain

    server_name = b"\x00" + len(domain).to_bytes(2, "big") + domain
    sni = len(server_name).to_bytes(2, "big") + server_name
    key_share_data = b"\x00\x29\xba\xba\x00\x01\x00\x00\x1d\x00\x20" + key_share

    # TLS 1.3 ClientHello extensions, including GREASE and padding.  The
    # resulting first record is intentionally 517 bytes, matching Telegram's
    # official FakeTLS profile rather than a real TLS session.
    extensions = b"".join(
        (
            _extension(0x4A4A, b""),
            _extension(0x0000, sni),
            _extension(0x0017, b""),
            _extension(0xFF01, b"\x00"),
            _extension(0x000A, b"\x00\x08\xba\xba\x00\x1d\x00\x17\x00\x18"),
            _extension(0x000B, b"\x01\x00"),
            _extension(0x0023, b""),
            _extension(0x0010, b"\x00\x0c\x02h2\x08http/1.1"),
            _extension(0x0005, b"\x01\x00\x00\x00\x00"),
            _extension(
                0x000D,
                b"\x00\x10\x04\x03\x08\x04\x04\x01\x05\x03\x08\x05"
                b"\x05\x01\x08\x06\x06\x01",
            ),
            _extension(0x0012, b""),
            _extension(0x0033, key_share_data),
            _extension(0x002D, b"\x01\x01"),
            _extension(0x002B, b"\x0a\x9a\x9a\x03\x04\x03\x03\x03\x02\x03\x01"),
            _extension(0x001B, b"\x02\x00\x02"),
            _extension(0x1A1A, b"\x00"),
        )
    )
    cipher_suites = bytes.fromhex(
        "fafa130113021303c02bc02fc02cc030cca9cca8c013c014009c009d002f0035"
    )
    base = (
        b"\x16\x03\x01\x02\x00"  # TLS record: Handshake, TLS 1.0, 512 bytes
        b"\x01\x00\x01\xfc"      # ClientHello, 508-byte handshake payload
        b"\x03\x03"                # TLS 1.2 legacy version
        + (b"\x00" * 32)             # replaced with authenticated random below
        + b"\x20"
        + session_id
        + len(cipher_suites).to_bytes(2, "big")
        + cipher_suites
        + b"\x01\x00"              # one null compression method
        + b"\x00\x00"              # extension length filled below
        + extensions
        + b"\x00\x15\x00\x00"    # padding extension and its length
    )
    padding_length = _CLIENT_HELLO_SIZE - len(base)
    if padding_length < 0:
        raise ValueError("FakeTLS SNI domain is too long for the ClientHello profile")
    extensions += _extension(0x0015, b"\x00" * padding_length)

    packet = bytearray(
        b"\x16\x03\x01\x02\x00"
        b"\x01\x00\x01\xfc"
        b"\x03\x03"
        + (b"\x00" * 32)
        + b"\x20"
        + session_id
        + len(cipher_suites).to_bytes(2, "big")
        + cipher_suites
        + b"\x01\x00"
        + len(extensions).to_bytes(2, "big")
        + extensions
    )
    if len(packet) != _CLIENT_HELLO_SIZE or packet[3:5] != b"\x02\x00":
        raise AssertionError("invalid FakeTLS ClientHello layout")

    digest = hmac.new(secret.key, bytes(packet), hashlib.sha256).digest()
    timestamp = int(time.time() if now is None else now).to_bytes(4, "little", signed=False)
    client_random = digest[:28] + bytes(
        digest[28 + index] ^ timestamp[index] for index in range(4)
    )
    packet[11:43] = client_random
    return _ClientHello(bytes(packet), client_random, session_id)


async def _read_tls_record(reader: Any) -> tuple[int, bytes, bytes]:
    header = await reader.readexactly(5)
    if len(header) != 5:
        raise FakeTLSHandshakeError("FakeTLS server closed the TLS record header")
    record_type = header[0]
    version = header[1:3]
    size = int.from_bytes(header[3:5], "big")
    if version not in (b"\x03\x01", _TLS_RECORD_VERSION) or size > _MAX_TLS_RECORD:
        raise FakeTLSHandshakeError("FakeTLS server sent an invalid TLS record")
    payload = await reader.readexactly(size)
    return record_type, payload, header + payload


def _verify_server_hello(secret: FakeTLSSecret, hello: _ClientHello, transcript: bytes) -> None:
    # Telegram's welcome packet has a 122-byte ServerHello record, a one-byte
    # ChangeCipherSpec record, and a fake ApplicationData record.  These fixed
    # offsets bind the server response to our ClientHello without implementing
    # a real TLS cipher suite.
    if len(transcript) < 138 or not transcript.startswith(b"\x16\x03\x03"):
        raise FakeTLSHandshakeError("FakeTLS server hello is incomplete")
    if transcript[127:136] != b"\x14\x03\x03\x00\x01\x01\x17\x03\x03":
        raise FakeTLSHandshakeError("FakeTLS server hello has an unexpected record layout")
    if transcript[44:76] != hello.session_id:
        raise FakeTLSHandshakeError("FakeTLS server did not echo the session identifier")
    server_digest = transcript[11:43]
    authenticated = bytearray(transcript)
    authenticated[11:43] = b"\x00" * 32
    expected = hmac.new(
        secret.key, hello.client_random + bytes(authenticated), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(server_digest, expected):
        raise FakeTLSHandshakeError("FakeTLS server authentication failed")


async def perform_fake_tls_handshake(reader: Any, writer: Any, secret: FakeTLSSecret) -> _ClientHello:
    """Authenticate a FakeTLS endpoint and leave its later records untouched."""

    hello = _build_client_hello(secret)
    writer.write(hello.packet)
    await writer.drain()

    records = [await _read_tls_record(reader) for _ in range(3)]
    if [record[0] for record in records] != [
        _TLS_HANDSHAKE,
        _TLS_CHANGE_CIPHER_SPEC,
        _TLS_APPLICATION_DATA,
    ]:
        raise FakeTLSHandshakeError("FakeTLS server sent an unexpected handshake sequence")
    _verify_server_hello(secret, hello, b"".join(record[2] for record in records))
    return hello


class _FakeTLSStreamReader:
    """Present post-handshake TLS ApplicationData as a regular byte stream."""

    def __init__(self, upstream: Any):
        self._upstream = upstream
        self._buffer = bytearray()

    async def _next_application_data(self) -> bytes:
        while True:
            record_type, payload, _raw = await _read_tls_record(self._upstream)
            if record_type == _TLS_APPLICATION_DATA:
                return payload
            if record_type == _TLS_CHANGE_CIPHER_SPEC:
                continue
            if record_type == _TLS_ALERT:
                raise ConnectionError("FakeTLS proxy sent a TLS alert")
            raise ConnectionError("FakeTLS proxy sent an unexpected TLS record")

    async def readexactly(self, size: int) -> bytes:
        if size < 0:
            raise ValueError("readexactly size can not be less than zero")
        while len(self._buffer) < size:
            payload = await self._next_application_data()
            if not payload:
                continue
            self._buffer.extend(payload)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    async def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        if size < 0:
            if self._buffer:
                data = bytes(self._buffer)
                self._buffer.clear()
                return data
            return await self._next_application_data()
        return await self.readexactly(size)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._upstream, name)


class _FakeTLSStreamWriter:
    """Wrap MTProto's encrypted bytes in TLS ApplicationData records."""

    def __init__(self, upstream: Any):
        self._upstream = upstream

    def write(self, data: bytes) -> int:
        payload = bytes(data)
        for offset in range(0, len(payload), 16_384):
            part = payload[offset : offset + 16_384]
            self._upstream.write(
                bytes((_TLS_APPLICATION_DATA,)) + _TLS_RECORD_VERSION
                + len(part).to_bytes(2, "big") + part
            )
        return len(payload)

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    async def drain(self) -> Any:
        return await self._upstream.drain()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._upstream, name)


_fake_tls_connection_class: Any = None


def _get_fake_tls_connection_class() -> type:
    """Build a Telethon connection class lazily, so offline imports stay safe."""

    global _fake_tls_connection_class
    if _fake_tls_connection_class is not None:
        return _fake_tls_connection_class

    from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate

    class ConnectionTcpMTProxyFakeTLS(ConnectionTcpMTProxyRandomizedIntermediate):
        """Telethon randomized-intermediate MTProxy inside a FakeTLS record layer."""

        def __init__(self, ip, port, dc_id, *, loggers, proxy=None, local_addr=None):
            if not isinstance(proxy, (tuple, list)) or len(proxy) < 3:
                raise ValueError("FakeTLS MTProxy needs (host, port, secret)")
            self._hydra_fake_tls_secret = FakeTLSSecret.parse(proxy[2])
            super().__init__(ip, port, dc_id, loggers=loggers, proxy=proxy, local_addr=local_addr)
            # Telethon's TcpMTProxy constructor connects directly to the
            # proxy endpoint and historically drops ``local_addr`` there.
            self._local_addr = local_addr

        async def _connect(self, timeout=None, ssl=None):
            if self._local_addr is None:
                local_addr = None
            elif isinstance(self._local_addr, tuple) and len(self._local_addr) == 2:
                local_addr = self._local_addr
            elif isinstance(self._local_addr, str):
                local_addr = (self._local_addr, 0)
            else:
                raise ValueError("Unknown local address format")

            raw_reader, raw_writer = await asyncio.wait_for(
                asyncio.open_connection(self._ip, self._port, local_addr=local_addr), timeout
            )
            try:
                await perform_fake_tls_handshake(
                    raw_reader, raw_writer, self._hydra_fake_tls_secret
                )
            except BaseException:
                raw_writer.close()
                try:
                    await raw_writer.wait_closed()
                except Exception:  # noqa: BLE001 - original handshake error wins
                    pass
                raise

            self._reader = _FakeTLSStreamReader(raw_reader)
            self._writer = _FakeTLSStreamWriter(raw_writer)
            self._codec = self.packet_codec(self)
            self._init_conn()
            await self._writer.drain()

    ConnectionTcpMTProxyFakeTLS.__module__ = __name__
    _fake_tls_connection_class = ConnectionTcpMTProxyFakeTLS
    return _fake_tls_connection_class


def connection_class_for_secret(secret: Any) -> type:
    """Choose FakeTLS for ``ee`` links and Telethon's normal class otherwise."""

    if is_fake_tls_secret(secret):
        return _get_fake_tls_connection_class()
    from telethon import connection

    return connection.ConnectionTcpMTProxyRandomizedIntermediate


__all__ = [
    "FakeTLSHandshakeError",
    "FakeTLSSecret",
    "connection_class_for_secret",
    "is_fake_tls_secret",
    "perform_fake_tls_handshake",
]
