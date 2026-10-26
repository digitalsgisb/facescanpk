"""Shared kiosk configuration; reading kiosk.env never executes shell commands."""
import os
from pathlib import Path
from urllib.parse import urlsplit

KIOSK_USER_AGENT = 'SugiharaAttendance-Kiosk/1.0'


def load_config(directory, environ=None):
    values = {}
    path = Path(directory) / 'kiosk.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            key = key.strip()
            if separator and key in ('ATTENDANCE_API_URL', 'ATTENDANCE_DEVICE_TOKEN'):
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values[key] = value
    env = os.environ if environ is None else environ
    for key in ('ATTENDANCE_API_URL', 'ATTENDANCE_DEVICE_TOKEN'):
        if key in env:
            values[key] = env[key]
    return validate_config(values.get('ATTENDANCE_API_URL', ''), values.get('ATTENDANCE_DEVICE_TOKEN', ''))


def validate_config(url, token):
    url, token = url.strip().rstrip('/'), token.strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError('Enter a valid AI PC service address, including its port.') from None
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.hostname in ('0.0.0.0', '::'):
        raise ValueError('Set ATTENDANCE_API_URL to the AI PC address, for example http://192.168.1.100:8765.')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or any(c.isspace() for c in url):
        raise ValueError('Use the service base address without a login, query, fragment or spaces.')
    if not token or token.startswith('replace-with-') or any(c.isspace() for c in token):
        raise ValueError('Set ATTENDANCE_DEVICE_TOKEN to a kiosk token from System settings → Add connection.')
    return url, token
