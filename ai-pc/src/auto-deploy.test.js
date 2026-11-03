import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, delimiter, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const bash = process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : '/bin/bash';
const script = fileURLToPath(new URL('../../tools/auto-deploy.sh', import.meta.url));
for (const outcome of ['healthy', 'build-failure', 'unhealthy']) test(`deployment ${outcome} preserves configuration and handles the previous image`, { skip: !existsSync(bash) || !existsSync(script), timeout: 60000 }, () => {
  const dir = mkdtempSync(join(tmpdir(), 'digital-deploy-')), bin = join(dir, 'bin'); mkdirSync(bin);
  const shellPath = value => value.replaceAll('\\', '/');
  const log = join(dir, 'calls.log'), state = join(dir, 'state');
  function executable(name, body) { writeFileSync(join(bin, name), '#!/usr/bin/env bash\n'+body+'\n', { mode: 0o755 }); }
  executable('flock', 'exit 0'); executable('sleep', 'exit 0'); executable('seq', "printf '1\\n2\\n'"); executable('git', 'echo tested-commit');
  executable('docker', `echo "$*" >> "$DEPLOY_TEST_LOG"
case "$1" in
  inspect)
    if [[ "$*" == *'.Image'* ]]; then echo sha256:previous-image
    elif [[ "$DEPLOY_TEST_OUTCOME" == unhealthy ]]; then echo unhealthy
    else echo healthy; fi
    ;;
  compose)
    if [[ "$*" == *' build '* ]] && [[ "$DEPLOY_TEST_OUTCOME" == build-failure ]]; then exit 1; fi
    if [[ "$*" == *' ps -q '* ]]; then if test -f "$DEPLOY_TEST_STATE"; then echo new-container; else echo old-container; fi; fi
    if [[ "$*" == *' up '* ]]; then touch "$DEPLOY_TEST_STATE"; fi
    ;;
esac`);
  writeFileSync(join(dir, 'compose.yaml'), 'services: {}\n');
  writeFileSync(join(dir, 'compose.shift-link.yaml'), 'networks: {}\n');
  writeFileSync(join(dir, 'compose.override.yaml'), 'services: {}\n');
  writeFileSync(join(dir, '.env.docker'), 'PRIVATE_SETTING=preserved\n');
  try {
    const result = spawnSync(bash, ['--noprofile', '--norc', '-c', 'mock_bin="$DEPLOY_TEST_BIN"; if command -v cygpath >/dev/null; then mock_bin="$(cygpath -u "$mock_bin")"; fi; export PATH="$mock_bin:$PATH"; exec bash "$@"', 'deploy-test', shellPath(script), shellPath(dir), 'checksheet', '.env.docker'], {
      encoding: 'utf8', timeout: 55000, env: { ...process.env, PATH: bin + delimiter + process.env.PATH, HOME: shellPath(dir), DEPLOY_TEST_BIN: shellPath(bin), DEPLOY_TEST_LOG: shellPath(log), DEPLOY_TEST_STATE: shellPath(state), DEPLOY_TEST_OUTCOME: outcome }
    });
    assert.equal(result.error, undefined);
    assert.equal(result.status, outcome === 'healthy' ? 0 : 1, result.stderr);
    const calls = readFileSync(log, 'utf8');
    assert.match(calls, /compose.override.yaml/); assert.match(calls, /compose.shift-link.yaml/);
    assert.match(calls, / build --build-arg APP_BUILD_REVISION=tested-commit checksheet/);
    assert.doesNotMatch(calls, / up [^\n]*--build-arg/);
    assert.doesNotMatch(calls, /down|prune|--volumes/);
    assert.equal(readFileSync(join(dir, '.env.docker'), 'utf8'), 'PRIVATE_SETTING=preserved\n');
    if (outcome === 'unhealthy') assert.match(calls, /image tag sha256:previous-image production-digital-rollback:checksheet/);
    else assert.doesNotMatch(calls, /image tag/);
    if (outcome === 'build-failure') assert.doesNotMatch(calls, / up /);
  } finally { assert.ok(resolve(dir).startsWith(resolve(tmpdir()) + sep)); rmSync(dir, { recursive: true, force: true }); }
});
