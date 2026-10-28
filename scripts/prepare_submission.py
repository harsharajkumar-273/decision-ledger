"""Collect reproducible local checks; opt in to paid live model evaluations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='call configured models; consumes provider credits')
    args = parser.parse_args()
    output = ROOT / '.local' / 'submission-runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    steps = [('tests', [sys.executable, '-m', 'pytest', '-q']),
             ('readiness', [sys.executable, '-m', 'dledger.cli', 'doctor'])]
    # Invoke the installed entry point via main, since cli.py is a library module.
    def cli(*arguments):
        return [sys.executable, '-c', 'from dledger.cli import main; raise SystemExit(main())', *arguments]
    steps[1] = ('readiness', cli('doctor', '--out', str(output / 'readiness.json')))
    steps.append(('rules-benchmark', cli('benchmark', '--out', str(output / 'rules-benchmark.json'))))
    if args.live:
        steps.extend([('live-readiness', cli('doctor', '--live', '--out', str(output / 'live-readiness.json'))),
                      ('model-evaluations', cli('eval-models', '--task', 'all', '--out', str(output / 'models.json'))),
                      ('model-comparison', cli('benchmark', '--models', '--out', str(output / 'comparison.json')))])
    manifest = {'started_at': datetime.now(timezone.utc).isoformat(), 'live_requested': args.live, 'steps': []}
    failed = False
    for name, command in steps:
        print(f'Running {name}…', flush=True)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        # Doctor output contains only readiness booleans, env names and model IDs.
        (output / f'{name}.log').write_text(result.stdout + result.stderr)
        manifest['steps'].append({'name': name, 'exit_code': result.returncode})
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        if result.returncode:
            if name == 'readiness' and not args.live:
                print('Live model setup is incomplete. Continuing local checks.')
                continue
            failed = True
            print(f'{name} failed. Later steps were not run; inspect its log.')
            break
    print(f'Results: {output}')
    print('Live evaluations were not requested.' if not args.live else 'Review the saved metrics; a completed command is not proof of model quality.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
