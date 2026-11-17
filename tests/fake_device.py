"""A fake Tuya LAN device for end-to-end tests of code that drives devices through TinyTuya.

It is a real TCP server on 127.0.0.1 speaking protocol 3.1, 3.3, 3.4 or 3.5 well enough for an
unmodified ``tinytuya.Device`` to query and control it. Framing and crypto reuse TinyTuya's own
``pack_message`` / ``unpack_message`` / ``AESCipher``, so the wire format cannot drift from the
client's::

    with FakeTuyaDevice(DEV_ID, LOCAL_KEY, version="3.4", dps={"1": False}) as fake:
        dev = tinytuya.Device(DEV_ID, "127.0.0.1", LOCAL_KEY, version=3.4, port=fake.port)
        dev.set_value(1, True)
        assert fake.dps["1"] is True and len(fake.received) == 1

A client with the wrong local key is treated the way TinyTuya's scanner describes real devices:
3.4/3.5 drop the connection during the handshake (TinyTuya reports Err 914), 3.3 answers with an
error text encrypted under the real key, which the client cannot read (Err 904), and 3.1 only
rejects CONTROL because everything else is plaintext.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import os
import socket
import struct
import threading
import time
from collections.abc import Callable
from hashlib import md5, sha256
from typing import Any

import tinytuya

VERSIONS = ("3.1", "3.3", "3.4", "3.5")


def _str_keys(dps: dict[Any, Any]) -> dict[str, Any]:
    return {str(dp): value for dp, value in dps.items()}


class _Client:
    """One TCP connection to the fake."""

    def __init__(self, sock: socket.socket, key: bytes, ready: bool) -> None:
        self.sock = sock
        self.reader = sock.makefile("rb")
        self.key = key  # the local key, until a 3.4/3.5 handshake replaces it with the session key
        self.ready = ready  # False while a 3.4/3.5 connection has not completed its handshake
        self.nonces = (b"", b"")  # (client, device) handshake nonces
        self.seqno = 0  # 3.5 only: the device numbers its own frames
        self.send_lock = threading.Lock()  # replies and pushes are sent from different threads


class FakeTuyaDevice:
    """A Tuya device (a gateway with sub-devices when ``cids`` is given) listening on 127.0.0.1.

    ``dps`` and ``cids[cid]`` hold the current datapoints and ``received`` the decoded JSON of
    every CONTROL / CONTROL_NEW command, exactly as sent; tests may read and modify all three.
    ``port`` is assigned by the OS on the first start() and kept if the fake is restarted.
    ``ack_code`` is the return code with which commands are acknowledged: TuyaOpen's device code
    sends 1, which a little-endian device puts on the wire as 01 00 00 00, read as 16777216.
    """

    def __init__(
        self,
        dev_id: str,
        local_key: str,
        version: str = "3.3",
        dps: dict[str, Any] | None = None,
        cids: dict[str, dict[str, Any]] | None = None,
        ack_code: int = 0,
    ) -> None:
        if str(version) not in VERSIONS:
            raise ValueError(f"unsupported version {version!r}, expected one of {VERSIONS}")
        if len(local_key) != 16:
            raise ValueError("local_key must be 16 characters")
        self.dev_id = dev_id
        self.version = str(version)
        self.port = 0
        self.dps = _str_keys(dps or {})
        self.cids = {cid: _str_keys(child) for cid, child in (cids or {}).items()}
        self.received: list[dict[str, Any]] = []
        self.connections = 0  # accepted so far
        self.ack_code = ack_code
        self._key = local_key.encode("latin1")
        self._negotiates = self.version in ("3.4", "3.5")  # connections start with a handshake
        is_35 = self.version == "3.5"
        self._prefix = tinytuya.PREFIX_6699_VALUE if is_35 else tinytuya.PREFIX_55AA_VALUE
        self._lock = threading.Lock()  # guards _clients and _pushes
        self._clients: dict[_Client, threading.Thread] = {}
        self._pushes = 0
        self._listener: socket.socket | None = None
        self._acceptor: threading.Thread | None = None

    def __enter__(self) -> FakeTuyaDevice:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def start(self) -> None:
        """Bind 127.0.0.1 and serve in daemon threads until stop()."""
        if self._listener is not None:
            raise RuntimeError("already started")
        listener = self._listener = socket.create_server(("127.0.0.1", self.port))
        self.port = listener.getsockname()[1]
        self._acceptor = self._spawn(self._accept_loop, listener)

    def stop(self) -> None:
        """Stop listening, drop every client and wait for all server threads to exit."""
        listener, self._listener = self._listener, None
        if listener is None or self._acceptor is None:
            return
        # Closing a socket does not reliably interrupt an accept() blocked in another thread,
        # but a connection does: the loop then notices that it has been stopped.
        socket.create_connection(("127.0.0.1", self.port)).close()
        self._acceptor.join()
        listener.close()
        with self._lock:
            clients = list(self._clients.items())
        for client, thread in clients:
            with contextlib.suppress(OSError):
                client.sock.shutdown(socket.SHUT_RDWR)  # wakes the client's thread out of its read
            thread.join()

    def push(self, dps: dict[str, Any], cid: str | None = None) -> None:
        """Change datapoints as a physical button press would: update the state and send an
        unsolicited STATUS to every client connected right now. ``cid`` selects a sub-device."""
        changed = _str_keys(dps)
        (self.dps if cid is None else self.cids[cid]).update(changed)
        self._broadcast(changed, cid)

    # --- connections ---

    def _spawn(self, target: Callable[..., None], *args: Any) -> threading.Thread:
        name = f"fake-tuya-{self.port}"
        thread = threading.Thread(target=target, args=args, name=name, daemon=True)
        thread.start()
        return thread

    def _accept_loop(self, listener: socket.socket) -> None:
        while True:
            sock, _ = listener.accept()
            if self._listener is not listener:  # stop() was called; this is its wake-up connection
                sock.close()
                return
            # An ack followed by a STATUS is two small writes; do not let Nagle delay the second.
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client = _Client(sock, self._key, ready=not self._negotiates)
            self.connections += 1
            with self._lock:  # held so that the thread cannot unregister before it is registered
                self._clients[client] = self._spawn(self._serve, client)

    def _serve(self, client: _Client) -> None:
        try:
            while (msg := self._read(client)) is not None and self._handle(client, msg):
                pass
        except OSError:
            pass  # the client went away while we were replying
        finally:
            client.reader.close()
            client.sock.close()
            with self._lock:
                del self._clients[client]

    def _read(self, client: _Client) -> tinytuya.TuyaMessage | None:
        """Next frame from the client; None on EOF or on anything that is not one of our version."""
        try:
            # 18 bytes hold either header (55AA: 16, 6699: 18); no valid frame is shorter than 24.
            data = client.reader.read(18)
            header = tinytuya.parse_header(data)
            if header.prefix != self._prefix or header.total_length < len(data):
                return None
            data += client.reader.read(header.total_length - len(data))
            key = self._frame_key(client)
            return tinytuya.unpack_message(data, hmac_key=key, header=header, no_retcode=True)
        except (tinytuya.DecodeError, OSError):
            return None

    # --- protocol ---

    def _handle(self, client: _Client, msg: tinytuya.TuyaMessage) -> bool:
        """Answer one request. False drops the connection, which is what a 3.4/3.5 device does with
        a frame it cannot authenticate (wrong local key or protocol version)."""
        if not msg.crc_good:
            return False
        cmd, seqno = msg.cmd, msg.seqno
        try:
            body = self._plaintext(client, msg)
            if not client.ready:
                return self._handshake(client, msg, body)
            request = json.loads(body)
            if not isinstance(request, dict):
                raise ValueError("not a JSON object")
        except (ValueError, TypeError):
            # Padding, UTF-8 or JSON error. Frames are not authenticated before 3.4, so this is how
            # a wrong local key shows up there. Devices answer with an error text (3.3: encrypted).
            self._send(client, cmd, seqno, b"data format error", retcode=1)
            return True

        # 3.4/3.5 CONTROL_NEW nests dps and cid under "data".
        inner = request["data"] if isinstance(request.get("data"), dict) else request
        cid = inner.get("cid", request.get("cid"))
        dps = self.dps if cid is None else self.cids.get(cid)  # None: no such sub-device
        control = cmd in (tinytuya.CONTROL, tinytuya.CONTROL_NEW)
        if control:
            self.received.append(request)
        if dps is not None and cmd in (tinytuya.DP_QUERY, tinytuya.DP_QUERY_NEW):
            self._send(client, cmd, seqno, self._report(dps, cid))
            return True
        touched: dict[str, Any] = {}
        if dps is not None and control:
            touched = _str_keys(inner.get("dps") or {})
            dps.update(touched)
        elif dps is not None and cmd == tinytuya.UPDATEDPS:
            wanted = {str(dp) for dp in request.get("dpId") or []}
            touched = {dp: value for dp, value in dict(dps).items() if dp in wanted}
        # A bare ack is all that HEART_BEAT and anything we cannot serve get. After CONTROL and
        # UPDATEDPS a device then reports the datapoints concerned in a STATUS to all its clients.
        self._send(client, cmd, seqno, retcode=self.ack_code if control else 0)
        self._broadcast(touched, cid)
        return True

    def _handshake(self, client: _Client, msg: tinytuya.TuyaMessage, body: bytes) -> bool:
        """3.4/3.5 session key negotiation, device side. Both peers prove they hold the local key by
        returning an HMAC of the other's nonce, then switch to a key derived from both nonces."""
        if msg.cmd == tinytuya.SESS_KEY_NEG_START and len(body) == 16:
            client.nonces = (body, os.urandom(16))
            proof = hmac.new(self._key, body, sha256).digest()
            self._send(client, tinytuya.SESS_KEY_NEG_RESP, msg.seqno, client.nonces[1] + proof)
            return True
        client_nonce, device_nonce = client.nonces
        expected = hmac.new(self._key, device_nonce, sha256).digest()
        finish = msg.cmd == tinytuya.SESS_KEY_NEG_FINISH and bool(device_nonce)
        if not finish or not hmac.compare_digest(body, expected):
            return False
        xored = bytes(a ^ b for a, b in zip(client_nonce, device_nonce, strict=False))
        cipher = tinytuya.AESCipher(self._key)
        if self.version == "3.4":
            client.key = cipher.encrypt(xored, use_base64=False, pad=False)
        else:  # 3.5: AES-GCM with the client nonce as IV; the key is the ciphertext after the IV
            iv = client_nonce[:12]
            client.key = cipher.encrypt(xored, use_base64=False, pad=False, iv=iv)[12:28]
        client.ready = True
        return True

    def _frame_key(self, client: _Client) -> bytes | None:
        """Key of the frame integrity check: none up to 3.3 (CRC32), then HMAC (3.4), GCM (3.5)."""
        return client.key if self._negotiates else None

    def _plaintext(self, client: _Client, msg: tinytuya.TuyaMessage) -> bytes:
        """Payload of a client frame, decrypted and without the 15-byte version header that TinyTuya
        puts on every command not in NO_PROTOCOL_HEADER_CMDS."""
        cipher = tinytuya.AESCipher(client.key)
        payload: bytes = msg.payload
        if self.version == "3.1":  # only CONTROL is encrypted: "3.1" + MD5 slice (16) + base64
            if msg.cmd != tinytuya.CONTROL:
                return payload
            return cipher.decrypt(payload[19:], decode_text=False)
        skip = 0 if msg.cmd in tinytuya.NO_PROTOCOL_HEADER_CMDS else 15
        if self.version == "3.3":  # header in clear, then AES-ECB under the local key
            return cipher.decrypt(payload[skip:], use_base64=False, decode_text=False)
        if self.version == "3.4":  # header inside AES-ECB under the session key
            return cipher.decrypt(payload, use_base64=False, decode_text=False)[skip:]
        return payload[skip:]  # 3.5: the whole frame is AES-GCM, unpack_message() decrypted it

    def _report(self, dps: dict[str, Any], cid: str | None) -> bytes:
        """Status JSON as devices send it: flat up to 3.3, wrapped in "data" on 3.4/3.5."""
        inner: dict[str, Any] = {"dps": dict(dps)}  # a copy: the test may change dps meanwhile
        if cid is not None:
            inner["cid"] = cid
        if self._negotiates:
            report = {"protocol": 4, "t": int(time.time()), "data": inner}
        else:
            report = {"devId": self.dev_id, **inner}
        return json.dumps(report, separators=(",", ":")).encode()

    def _broadcast(self, dps: dict[str, Any], cid: str | None) -> None:
        """Send a STATUS push for these datapoints to every client that can decrypt it."""
        if not dps:
            return
        with self._lock:
            self._pushes += 1
            clients = [client for client in self._clients if client.ready]
            # Where commands carry the version plus 12 zero bytes, a STATUS carries the version plus
            # a crc (0 on the LAN), a sequence number and a source id (1 for the device itself).
            header = self.version.encode() + struct.pack(">3I", 0, self._pushes, 1)
        for client in clients:
            with contextlib.suppress(OSError):  # that client has just disconnected
                self._send(client, tinytuya.STATUS, 0, self._report(dps, cid), header=header)

    def _send(
        self,
        client: _Client,
        cmd: int,
        seqno: int,
        body: bytes = b"",
        retcode: int = 0,
        header: bytes = b"",
    ) -> None:
        """Encrypt ``body`` (empty: a bare ack) the way our version does, frame it and send it.
        ``header`` is the version header of a STATUS; other replies have none."""
        cipher = tinytuya.AESCipher(client.key)
        if body and header and self.version == "3.1":  # the only thing a 3.1 device encrypts
            body = cipher.encrypt(body)  # base64, wrapped exactly like a 3.1 CONTROL
            signature = md5(b"data=" + body + b"||lpv=3.1||" + client.key).hexdigest()[8:24]
            body = b"3.1" + signature.encode() + body
        elif body and self.version == "3.3":
            body = header + cipher.encrypt(body, use_base64=False)
        elif body and self.version == "3.4":
            body = cipher.encrypt(header + body, use_base64=False)
        elif body and self.version == "3.5":
            body = header + body
        with client.send_lock:
            iv = None
            if self.version == "3.5":  # 6699: pack_message() puts the retcode into the ciphertext
                client.seqno += 1  # and the device numbers its frames itself
                seqno, iv = client.seqno, True  # True: a fresh random IV
            else:  # 55AA: pack_message() leaves the retcode to us; replies echo the request's seqno
                body = struct.pack(tinytuya.MESSAGE_RETCODE_FMT, retcode) + body
            msg = tinytuya.TuyaMessage(seqno, cmd, retcode, body, 0, True, self._prefix, iv)
            client.sock.sendall(tinytuya.pack_message(msg, hmac_key=self._frame_key(client)))
