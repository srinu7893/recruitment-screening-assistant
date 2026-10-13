"""Linux parser worker. No network fetches or Office macro execution."""
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


def extract(path):
    warnings = []
    pages = []
    if path.suffix == ".txt":
        pages = [path.read_text(encoding="utf-8-sig")]
    elif path.suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(x.file_size for x in entries) > 20_000_000:
                raise ValueError("DOCX expanded contents exceed limits")
            if any(x.flag_bits & 1 or "vbaproject" in x.filename.lower() for x in entries):
                raise ValueError("Encrypted or macro-bearing documents are not supported")
            raw = archive.read("word/document.xml")
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError("DOCX entities are not supported")
            root = ET.fromstring(raw)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            pages = ["\n".join("".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p"))]
            warnings.append("DOCX headers, footers and embedded images are not extracted.")
    else:
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")
        if not 1 <= len(reader.pages) <= 20:
            raise ValueError("PDF must contain 1 to 20 pages")
        for number, page in enumerate(reader.pages, 1):
            content = page.extract_text() or ""
            if len(content.strip()) < 20:
                renderer = shutil.which("pdftoppm", path="/usr/bin:/bin") or shutil.which("pdftoppm")
                ocr = shutil.which("tesseract", path="/usr/bin:/bin") or shutil.which("tesseract")
                if not renderer or not ocr:
                    raise ValueError("Scanned PDF needs Poppler and Tesseract installed")
                prefix = str(path.parent / f"page-{number}")
                subprocess.run([renderer, "-f", str(number), "-l", str(number), "-singlefile",
                                "-scale-to", "1800", "-png", str(path), prefix],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                content = subprocess.run([ocr, prefix + ".png", "stdout", "-l", "eng"],
                                         check=True, capture_output=True, timeout=15).stdout.decode("utf-8")
                warnings.append(f"Page {number}: OCR used; verify extracted text.")
            pages.append(content)
    content = "\n\n".join(pages).strip()
    if not content or len(content) > 50_000:
        raise ValueError("Extracted text is empty or exceeds 50,000 characters")
    return {"text": content, "pages": len(pages), "warnings": warnings}


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_FSIZE, (30 * 1024 * 1024,) * 2)
    try:
        result = extract(Path(sys.argv[1]))
    except ValueError as exc:
        result = {"error": str(exc)[:200]}
    except Exception:
        result = {"error": "Unreadable or unsupported document"}
    print(json.dumps(result))
