"""Run on the Raspberry Pi: interactive connection setup, or --check."""
import argparse
import getpass
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from kiosk_config import load_config, validate_config

BASE = Path(__file__).resolve().parent


def check_connection(url, token):
    request = urllib.request.Request(url + '/api/employees', headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code in (401, 403):
            raise ValueError('Connection refused: use an active Raspberry Pi kiosk token from System settings.') from None
        raise ValueError(f'The attendance service returned HTTP {code}.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('Cannot reach the AI PC. Check its address, service, network/firewall and HTTPS certificate trust.') from None
    except (ValueError, UnicodeError):
        raise ValueError('The address did not return attendance employee data.') from None
    if not isinstance(data, dict) or not isinstance(data.get('employees'), list):
        raise ValueError('The address did not return attendance employee data.')
    if data.get('connection_scope') != 'kiosk':
        raise ValueError('Use a Raspberry Pi kiosk token and restart the AI PC with the latest server.py.')
    return len(data['employees'])


def save_config(directory, url, token):
    url, token = validate_config(url, token)
    directory = Path(directory)
    fd, temporary = tempfile.mkstemp(prefix='.kiosk-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as file:
            file.write(f'ATTENDANCE_API_URL={url}\nATTENDANCE_DEVICE_TOKEN={token}\n')
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, directory / 'kiosk.env')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check saved configuration without starting the camera or recording attendance')
    args = parser.parse_args()
    try:
        if args.check:
            url, token = load_config(BASE)
        else:
            print('On the AI PC, open System settings → Add connection → Raspberry Pi attendance kiosk.')
            url = input('AI PC service address (including http:// or https:// and port): ')
            token = getpass.getpass('Kiosk connection token (hidden): ')
            url, token = validate_config(url, token)
        count = check_connection(url, token)
        if not args.check:
            save_config(BASE, url, token)
            print('Connection saved in kiosk.env. Start with bash run_kiosk.sh or python3 face.py.')
        print(f'Connected successfully. {count} active employees available. No attendance was recorded.')
        return 0
    except (ValueError, OSError) as exc:
        print(f'Connection setup: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
