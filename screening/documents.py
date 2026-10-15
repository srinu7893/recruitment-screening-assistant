"""Bounded file extraction in a separate process; originals are not retained."""
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory

from .scanning import scan_upload

MAX_FILE = 5 * 1024 * 1024


def extract_upload(filename, encoded):
    if not isinstance(filename, str) or len(filename) > 200:
        raise ValueError("Invalid filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt"):
        raise ValueError("Supported files: PDF, DOCX and UTF-8 TXT")
    if not isinstance(encoded, str) or len(encoded) > MAX_FILE * 4 // 3 + 4:
        raise ValueError("File exceeds 5 MB")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise ValueError("Invalid base64 file") from None
    if not raw or len(raw) > MAX_FILE:
        raise ValueError("Empty file or file exceeds 5 MB")
    if suffix == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ValueError("PDF signature does not match")
    if suffix == ".docx" and not raw.startswith(b"PK"):
        raise ValueError("DOCX signature does not match")
    scan = scan_upload(raw)
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("input" + suffix)
        path.write_bytes(raw)
        proc = subprocess.Popen([sys.executable, "-m", "screening.extract_worker", str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, _ = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise ValueError("Document extraction timed out") from None
    if proc.returncode or len(stdout) > 500_000:
        raise ValueError("Document could not be read within extraction limits")
    result = json.loads(stdout)
    if result.get("error"):
        raise ValueError(result["error"])
    result["malware_scan"] = scan
    if scan["status"] == "not_scanned":
        result.setdefault("warnings", []).append("Malware scanning disabled in this development environment.")
    return result
