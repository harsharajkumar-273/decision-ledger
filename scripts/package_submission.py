"""Build a source archive with local credentials, environments and state excluded."""
from hashlib import sha256
from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {'.git', '.venv', '.local', '__pycache__', '.pytest_cache', 'node_modules', '.aws', '.codex', '.agents'}


def main():
    output = ROOT / '.local' / 'release'
    output.mkdir(parents=True, exist_ok=True)
    secrets = []
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                if any(s in key.upper() for s in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')) and len(value.strip()) >= 12:
                    secrets.append(value.strip().strip('\"\''))
    files = []
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS or part.endswith('.egg-info') for part in rel.parts):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if path.name == '.DS_Store' or path.name.startswith('.env') and path.name != '.env.example':
            continue
        if path.suffix in ('.pyc', '.pyo', '.sqlite3', '.sqlite', '.db') or '.history.sqlite3' in path.name:
            continue
        data = path.read_bytes()
        if any(secret.encode() in data or secret[-32:].encode() in data for secret in secrets):
            raise SystemExit(f'Packaging stopped: configured secret found in {rel}')
        files.append((rel, data))
    archive = output / 'decision-ledger-source.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for rel, data in files:
            bundle.writestr('decision-ledger/' + rel.as_posix(), data)
    digest = sha256(archive.read_bytes()).hexdigest()
    (output / 'decision-ledger-source.zip.sha256').write_text(digest + '  decision-ledger-source.zip\n')
    (output / 'package-manifest.json').write_text(json.dumps({'file_count': len(files), 'sha256': digest,
        'files': [rel.as_posix() for rel, _ in files], 'configured_secret_scan_passed': True}, indent=2))
    print(f'Created {archive} ({len(files)} files). Configured-secret scan passed.')


if __name__ == '__main__':
    main()
