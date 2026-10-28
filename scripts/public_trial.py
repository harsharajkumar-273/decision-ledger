"""Read-only static trial of FastAPI's template; not a maintainer/user study."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dledger.judge import rule_verdict
from dledger.schema import Claim
from dledger.verify import verify

p = argparse.ArgumentParser()
p.add_argument('repo', type=Path)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
commit = subprocess.run(['git', '-C', str(a.repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
results=[]
for value, label in [('postgresql','README technology declaration'), ('mongodb','synthetic negative control; not a project decision')]:
    c=Claim(value, f'Use {value} as the database', 'database', value,
            source=f'https://github.com/fastapi/full-stack-fastapi-template/tree/{commit}')
    ev=verify(c,a.repo)
    results.append({'claim_type':label,'value':value,'verdict':rule_verdict(c.id,ev)[0].value,
                    'evidence':[e.__dict__ for e in ev]})
a.out.write_text(json.dumps({'repository':'https://github.com/fastapi/full-stack-fastapi-template',
                            'commit':commit,'trial_at':datetime.now(timezone.utc).isoformat(),
                            'method':'read-only static configuration inspection',
                            'limitations':'No maintainer interviews or production access. Negative control is synthetic.',
                            'results':results},indent=2)+'\n')
print(json.dumps({'commit':commit,'results':[{k:r[k] for k in ('value','verdict')} for r in results]}))
