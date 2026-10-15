"""Build code-only device ZIPs. Private company data is never read by this script."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

BASE = Path(__file__).resolve().parents[1]
PI_FILES = ['README.md', 'face.py', 'kiosk_config.py', 'kiosk_keyboard.py', 'kiosk_touch.py', 'kiosk_transport.py',
            'kiosk_vision.py', 'configure_kiosk.py', 'configure_display.py', 'test_configure_display.py', 'run_kiosk.sh', 'kiosk.env.example',
            'test_kiosk_transport.py', 'test_kiosk_keyboard.py', 'test_kiosk_controls.py', '1.png']
PC_FILES = ['README.md', 'server.py', 'requirements.txt', 'start.ps1', 'package.json',
            'package-lock.json', 'index.html', 'vite.config.js', 'test_server.py', 'import_history.py',
            'data/employees.example.json', 'Dockerfile', '.dockerignore', 'compose.yaml', '.env.example',
            'manage.py', 'test_manage.py', 'install-docker-ubuntu.sh', 'DOCKER-SSH.md']


def main():
    output = BASE / 'downloads'
    output.mkdir(exist_ok=True)
    if not (BASE/'ai-pc/dist/index.html').exists():
        raise SystemExit('Build React first: cd ai-pc, npm ci, npm run build')
    manifest = {}
    for folder, name, files, trees in [
        ('raspberry-pi', 'Smart-Attendance-Pi.zip', PI_FILES, []),
        ('ai-pc', 'Smart-Attendance-AI-PC.zip', PC_FILES, ['src', 'public', 'dist']),
    ]:
        paths = [BASE/folder/file for file in files]
        for tree in trees:
            paths.extend(sorted(p for p in (BASE/folder/tree).rglob('*') if p.is_file()))
        with ZipFile(output/name, 'w', ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, path.relative_to(BASE).as_posix())
        manifest[name] = {'sha256':hashlib.sha256((output/name).read_bytes()).hexdigest(), 'files':len(paths)}
    (output/'SHA256SUMS.txt').write_text(''.join(f"{value['sha256']}  {name}\n" for name,value in manifest.items()),encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
