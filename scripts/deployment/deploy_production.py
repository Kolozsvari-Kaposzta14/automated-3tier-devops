"""First production deployment only; reuse reviewed staging primitives."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path.home() / '.local/share/automated-3tier-deploy'
BIN = ROOT / 'bin'
PROJECT = 'automated-3tier-production'
PG = 'postgres@sha256:f2f98726820d0342055351c6e9d36e705f5bfffb3dd53ff556325114b08afb6d'
PG_ID = 'sha256:' + PG.split(':')[1]
PINS = {
    'deploy_release.py': '1a3d37584a555a3864732a4ca5ecce039f7834001d560863aa6cf9ce16db311a',
    'verify_production_approval.py': 'fe6311ba9589f7aac2cee89865e562a3d1111f3d42510d054a29149d0a450b70',
    'validate_release.py': '43c27775b9a9b4b20c6d4036c8f3af1122f258f10a32b4c22e4dfcb7a493029f',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def trusted_imports():
    # Verify dependencies before importing executable local code.
    for name, digest in PINS.items():
        path = BIN / name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600, 'Unsafe trusted file')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                'Trusted dependency checksum mismatch')
    sys.path.insert(0, str(BIN))
    import deploy_release as shared
    import verify_production_approval as approval
    shared.verify_trusted_files()
    return shared, approval


def credentials(shared):
    # Never print credential values. Require independent staging password.
    path = shared.CONFIG_ROOT / 'production.env'
    shared.verify_private_file(path)
    shared.verify_staging_credentials(shared.CONFIG_ROOT / 'staging.env')
    def parse(file):
        pairs = [line.split('=', 1) for line in file.read_text().splitlines()]
        require(len(pairs) == 4 and all(len(p) == 2 for p in pairs), 'Invalid credentials')
        return dict(pairs)
    values = parse(path)
    require(set(values) == {'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'HTTP_PORT'}, 'Unexpected credentials keys')
    require(values['POSTGRES_DB'] == 'taskmanager' and values['POSTGRES_USER'] == 'taskapp'
            and values['HTTP_PORT'] == '8081', 'Invalid production configuration')
    require(re.fullmatch(r'[A-Za-z0-9_-]{43}', values['POSTGRES_PASSWORD']) is not None, 'Invalid password format')
    require(values['POSTGRES_PASSWORD'] != parse(shared.CONFIG_ROOT / 'staging.env')['POSTGRES_PASSWORD'], 'Shared database password')
    return path


def consume(state_dir, authorization):
    # O_EXCL makes consumption atomic even if another process ignores the lock.
    run_id = authorization['approval_run_id']
    require(re.fullmatch(r'[1-9][0-9]{0,19}', run_id) is not None, 'Invalid run ID')
    require(time.time() < authorization['expires_at_epoch'], 'Approval expired')
    marker = state_dir / f'production-authorization-consumed-{run_id}.json'
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(authorization, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    # Persist directory entry before allowing any deployment mutation.
    fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    shared, approval = trusted_imports()
    env_file = credentials(shared)
    state_dir = ROOT / 'state'
    with (state_dir / 'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='production-check-', dir=ROOT) as temp:
            temp = Path(temp)
            snapshot = temp / 'release-manifest.json'
            with args.manifest.open('rb') as stream:
                raw = stream.read(65537)
            require(len(raw) <= 65536, 'Manifest too large')
            snapshot.write_bytes(raw)
            local = approval.verify_local_acceptance(snapshot)
            manifest = local['manifest']
            env = shared.compose_environment(manifest)
            def docker(*args, capture=True, timeout=120):
                return shared.run_command(['/usr/bin/docker', *args], env=env, capture=capture, timeout=timeout)
            # First deployment only: never overwrite existing production resources.
            for command in [('ps', '-aq'), ('volume', 'ls', '-q'), ('network', 'ls', '-q')]:
                require(not docker(*command, '--filter', f'label=com.docker.compose.project={PROJECT}').strip(), 'Existing production resources; stop for review')
            require(not (state_dir / 'production.json').exists(), 'Production state already exists')
            # Pin the exact PostgreSQL digest tested in staging using a private override.
            db = json.loads(docker('inspect', 'automated-3tier-staging-db-1'))[0]
            require(db['Image'] == PG_ID and db['State']['Health']['Status'] == 'healthy', 'Staging database image or health changed')
            require(json.loads(docker('image', 'inspect', PG))[0]['Id'] == PG_ID, 'Pinned PostgreSQL image unavailable')
            override = temp / 'postgres-pin.json'
            override.write_text(json.dumps({'services': {'db': {'image': PG}}}))
            compose = ['compose', '--project-name', PROJECT, '--project-directory', str(ROOT), '--env-file', str(env_file), '-f', str(shared.COMPOSE), '-f', str(override)]
            docker(*compose, 'config', '--quiet')
            shared.run_command([sys.executable, '-B', str(BIN / 'verify_github_release.py'), str(snapshot)])
            shared.verify_aws_identity()
            shared.verify_ecr_images(manifest)
            authorization = approval.verify_production_approval(snapshot, args.run_id)
            if not args.execute:
                print('PRECHECK PASSED: no deployment or approval consumption')
                return
            with open('/dev/tty', 'r') as tty:
                print('Type DEPLOY-PRODUCTION ' + manifest['release_tag'], flush=True)
                require(tty.readline().strip() == 'DEPLOY-PRODUCTION ' + manifest['release_tag'], 'Confirmation rejected')
            # Reverify after interactive confirmation, then consume before pulling.
            authorization = approval.verify_production_approval(snapshot, args.run_id)
            consume(state_dir, authorization)
            print('PASS: Authorization consumed; failures require a new approval and resource review')
            with tempfile.TemporaryDirectory(prefix='docker-auth-', dir=ROOT) as auth:
                env['DOCKER_CONFIG'] = auth
                try:
                    shared.run_command(['/usr/bin/docker', 'login', '--username', 'AWS', '--password-stdin', shared.REGISTRY], env=env, input_data=shared.aws_command('ecr', 'get-login-password'), capture=True)
                    docker(*compose, 'pull', 'backend', 'frontend', 'nginx', capture=False, timeout=600)
                    docker(*compose, 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '120', capture=False, timeout=240)
                finally:
                    try:
                        docker('logout', shared.REGISTRY, timeout=30)
                    except Exception:
                        print('WARNING: Temporary Docker config will be removed')
                    env.pop('DOCKER_CONFIG', None)
            # Verify actual running image IDs against the digest references.
            for service, reference in {'db': PG, **{k: v['reference'] for k, v in manifest['images'].items()}}.items():
                actual = json.loads(docker('inspect', f'{PROJECT}-{service}-1'))[0]
                expected = json.loads(docker('image', 'inspect', reference))[0]['Id']
                require(actual['Image'] == expected and actual['State']['Running'], 'Production runtime image mismatch')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), approval.RejectRedirects())
            for _ in range(30):
                try:
                    with opener.open('http://127.0.0.1:8081/api/health', timeout=5) as response:
                        require(response.status == 200 and json.loads(response.read(65536)) == {'status': 'ok'}, 'API not ready')
                    with opener.open('http://127.0.0.1:8081/', timeout=5) as response:
                        require(response.status == 200, 'Frontend not ready')
                    break
                except (OSError, ValueError, RuntimeError):
                    time.sleep(2)
            else:
                raise RuntimeError('Production readiness timeout')
            record = {'environment': 'production', 'release': manifest, 'authorization': authorization, 'postgres_image': PG, 'readiness': 'passed', 'integration_tests': 'pending', 'deployed_at_epoch': int(time.time())}
            fd, name = tempfile.mkstemp(prefix='production-', dir=state_dir)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(record, stream, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, state_dir / 'production.json')
            finally:
                Path(name).unlink(missing_ok=True)
            print('PRODUCTION DEPLOYED: independent runtime verification still required')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL: Production controller stopped (' + type(error).__name__ + ')', file=sys.stderr)
        if isinstance(error, RuntimeError) or type(error).__name__ == 'VerificationError':
            print(str(error), file=sys.stderr)
        sys.exit(1)
