"""The image copies an explicit list of Python files. A local module missing from that list
crashes the container on start (ModuleNotFoundError), so check every local import is copied."""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent


def local_imports(path, seen):
    for name in re.findall(r'^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)', path.read_text(encoding='utf-8'), re.M):
        module = BASE / f'{name}.py'
        if module.exists() and module.name not in seen:
            seen.add(module.name)
            local_imports(module, seen)
    return seen


class DockerfileTests(unittest.TestCase):
    def test_image_contains_every_local_module_the_server_imports(self):
        copied = set()
        for line in (BASE / 'Dockerfile').read_text(encoding='utf-8').splitlines():
            if line.startswith('COPY ') and line.rstrip().endswith('./'):
                copied.update(word for word in line.split()[1:-1] if word.endswith('.py'))
        needed = local_imports(BASE / 'server.py', {'server.py'}) | local_imports(BASE / 'manage.py', {'manage.py'})
        self.assertEqual(sorted(needed - copied), [], 'Add these files to the COPY line in ai-pc/Dockerfile')


if __name__ == '__main__':
    unittest.main()
