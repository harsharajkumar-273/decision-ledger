"""Entry point executed inside the sandbox: claim JSON on stdin, repo path as argv[1]."""
import json
import sys
from dataclasses import asdict

from .schema import Claim
from .verify import verify


def main() -> int:
    claim = Claim.from_dict(json.loads(sys.stdin.read()))
    ev = verify(claim, sys.argv[1], web=False)
    print(json.dumps([asdict(e) for e in ev]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
