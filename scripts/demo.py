"""Create and migrate a disposable Git repo for the automatic-change demo.

python scripts/demo.py init /tmp/dledger-demo
python scripts/demo.py migrate /tmp/dledger-demo
The migration is intentionally incomplete: SQL-based reporting remains.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Decision Ledger Demo',
                           '-c', 'user.email=demo@example.invalid', *args], check=True, capture_output=True, text=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['init', 'migrate'])
    p.add_argument('repo', type=Path)
    args = p.parse_args()
    repo = args.repo.resolve()
    if args.action == 'init':
        if repo.exists() and any(repo.iterdir()):
            p.error('choose an empty demo directory')
        repo.mkdir(parents=True, exist_ok=True)
        (repo / 'requirements.txt').write_text('fastapi\npsycopg2-binary\npymongo\nsqlalchemy\nredis\ncelery\n')
        (repo / 'compose.yml').write_text('services:\n  db:\n    image: postgres:16\n  api:\n    environment:\n      DATABASE_URL: postgresql://db/app\n')
        (repo / 'reporting.sql').write_text('SELECT customer_id, SUM(amount) OVER (PARTITION BY customer_id) FROM invoices;\n')
        shutil.copy(ROOT / 'data/sample/graph.json', repo / 'ledger.json')
        git(repo, 'init')
        git(repo, 'add', 'compose.yml', 'requirements.txt', 'reporting.sql')
        git(repo, 'commit', '-m', 'Use Postgres for billing and SQL reporting')
    else:
        config = repo / 'compose.yml'
        if not (repo / '.git').is_dir() or not config.is_file():
            p.error('initialize the demo repository first')
        text = config.read_text()
        if 'postgres:16' not in text:
            p.error('demo is already migrated or its configuration was changed')
        config.write_text(text.replace('postgres:16', 'mongo:7').replace('postgresql://db/app', 'mongodb://db/app'))
        git(repo, 'add', 'compose.yml')
        git(repo, 'commit', '-m', 'Migrate billing datastore to MongoDB; reporting still needs review')
    print(json.dumps({'repo': str(repo), 'action': args.action, 'commit': git(repo, 'rev-parse', 'HEAD').stdout.strip()}))


if __name__ == '__main__':
    main()
