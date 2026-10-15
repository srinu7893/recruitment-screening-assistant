"""Fail-closed, bounded INSTREAM scans against a private loopback sidecar."""
from datetime import datetime, timezone
import os
import socket
import struct
import time


def scan_upload(raw):
    mode = os.environ.get('SCREENING_SCAN_MODE', 'clamd' if os.environ.get('K_SERVICE') else 'off')
    if mode == 'off' and not os.environ.get('K_SERVICE'):
        return {'status': 'not_scanned'}
    if mode != 'clamd':
        raise ValueError('Cloud uploads require malware scanning')
    check_signatures()
    deadline = time.monotonic() + 30
    try:
        with socket.create_connection(('127.0.0.1', 3310), timeout=5) as connection:
            def send(value):
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                connection.sendall(value)
            send(b'zINSTREAM\0')
            for offset in range(0, len(raw), 65536):
                chunk = raw[offset:offset + 65536]
                send(struct.pack('!I', len(chunk)) + chunk)
            send(struct.pack('!I', 0))
            reply = b''
            while len(reply) < 4096:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                connection.settimeout(remaining)
                chunk = connection.recv(4096 - len(reply))
                if not chunk:
                    break
                reply += chunk
                if b'\0' in reply:
                    break
            if reply == b'stream: OK\0':
                return {'status': 'clean', 'engine': 'clamd'}
            if reply.endswith(b' FOUND\0'):
                raise ValueError('Upload blocked by malware scanner')
            raise ValueError('Malware scanner did not return a clean result')
    except OSError:
        raise ValueError('Malware scanner unavailable; upload blocked') from None


def check_signatures():
    """Reject stale/unknown databases even if a stale daemon still answers OK."""
    try:
        with socket.create_connection(('127.0.0.1', 3310), timeout=5) as connection:
            connection.sendall(b'zVERSION\0')
            reply = b''
            deadline = time.monotonic() + 5
            while len(reply) < 512 and b'\0' not in reply:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                connection.settimeout(remaining)
                chunk = connection.recv(512 - len(reply))
                if not chunk:
                    break
                reply += chunk
            if not reply.endswith(b'\0'):
                raise ValueError()
            stamp = reply[:-1].decode('ascii').split('/')[2]
            issued = datetime.strptime(stamp, '%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - issued).total_seconds()
            if not -300 <= age <= 72 * 3600:
                raise ValueError()
    except (OSError, ValueError, IndexError, UnicodeError):
        raise ValueError('Scanner signatures unavailable or older than 72 hours; upload blocked') from None
