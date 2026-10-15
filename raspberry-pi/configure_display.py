"""Pin the kiosk to a Wayfire output without replacing desktop/touch settings."""
import argparse
import configparser
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


def pin_window(text, output, default_text=''):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', output):
        raise ValueError('Use a connector name such as DSI-1.')
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.read_string(text)
    # Validate first, then edit individual lines to retain comments and mappings.
    updates = {'window-rules': {'attendance_output':
        f'on created if title is "Smart Attendance Kiosk" then start_on_output "{output}"'}}
    plugins = config.get('core', 'plugins', fallback=None)
    if plugins is None:
        defaults = configparser.ConfigParser(interpolation=None)
        defaults.read_string(default_text)
        plugins = defaults.get('core', 'plugins', fallback=None)
    # Unknown inherited defaults are left inherited, never replaced with guesses.
    if plugins is not None and 'window-rules' not in plugins.split():
        updates['core'] = {'plugins': plugins + ' window-rules'}
    lines = text.splitlines(keepends=True)
    for section, entries in updates.items():
        start = next((i for i, line in enumerate(lines)
                      if line.strip() == f'[{section}]'), None)
        if start is None:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.extend(['\n', f'[{section}]\n'])
            start = len(lines) - 1
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].lstrip().startswith('[')), len(lines))
        for key, value in entries.items():
            index = next((i for i in range(start + 1, end)
                          if re.match(rf'\s*{re.escape(key)}\s*=', lines[i])), None)
            if index is None:
                if lines and not lines[end - 1].endswith('\n'):
                    lines[end - 1] += '\n'
                lines.insert(end, f'{key} = {value}\n')
                end += 1
            else:
                lines[index] = f'{key} = {value}\n'
    result = ''.join(lines)
    config.read_string(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='DSI-1')
    parser.add_argument('--config', type=Path, default=Path(os.environ.get(
        'WAYFIRE_CONFIG_FILE', str(Path.home()/'.config/wayfire.ini'))))
    parser.add_argument('--apply', action='store_true', help='Back up and save; otherwise preview only.')
    args = parser.parse_args()
    try:
        original = args.config.read_text(encoding='utf-8')
        # Raspberry Pi OS uses defaults.ini (plural).
        defaults = next((path for path in (Path('/etc/wayfire/defaults.ini'),
                                           Path('/etc/wayfire/default.ini')) if path.exists()), None)
        default_text = defaults.read_text(encoding='utf-8') if defaults else ''
        updated = pin_window(original, args.output, default_text)
        settings = configparser.ConfigParser(interpolation=None)
        settings.read_string(default_text)
        settings.read_string(original)
        if not settings.has_option('core', 'plugins'):
            print('Plugin defaults unavailable: leaving plugin settings untouched. '
                  'The rule requires the window-rules plugin to be enabled in Wayfire.')
        if updated == original:
            print('The kiosk output rule is already configured.')
            return
        if not args.apply:
            print(f'Preview: pin Smart Attendance Kiosk to {args.output} in {args.config}.')
            print('Existing touch mappings and other settings are preserved. Use --apply to save.')
            return
        backup = args.config.with_name(args.config.name + '.attendance-' +
                                       datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
        shutil.copy2(args.config, backup)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.config.parent,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
        try:
            shutil.copymode(args.config, temporary)
            temporary.replace(args.config)
        finally:
            temporary.unlink(missing_ok=True)
        print(f'Saved kiosk output rule for {args.output}. Backup: {backup}')
        print('Restart the kiosk and verify its physical screen. Older Wayfire builds may ignore this rule.')
    except (OSError, ValueError, configparser.Error) as exc:
        raise SystemExit(f'Display setup: {exc}') from None


if __name__ == '__main__':
    main()
