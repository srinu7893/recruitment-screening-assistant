"""Explicit public origin configuration; forwarded headers are not trusted."""
from urllib.parse import urlsplit
import re


def public_origin(value):
    if not value:
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
                or parts.path not in ('', '/') or parts.query or parts.fragment
                or parts.port not in (None, 443)
                or not re.fullmatch(r'[a-zA-Z0-9.-]+', parts.hostname)):
            raise ValueError()
    except ValueError:
        raise ValueError('SCREENING_PUBLIC_URL must be an HTTPS origin without a path or credentials') from None
    return 'https://' + parts.netloc.lower()


def allowed_request(authority, origin, port, external):
    origins = {f'127.0.0.1:{port}': f'http://127.0.0.1:{port}',
               f'localhost:{port}': f'http://localhost:{port}'}
    if external:
        origins[urlsplit(external).netloc] = external
    return authority in origins and (origin is None or origin == origins[authority])
