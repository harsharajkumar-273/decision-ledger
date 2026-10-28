"""Verification history and status transitions, stored separately from source files."""
from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from datetime import datetime, timezone


class ReportStore:
    def __init__(self, path=':memory:'):
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, at TEXT NOT NULL, payload TEXT NOT NULL)')
        self.connection.commit()

    def record(self, report, event_type='check', before=None):
        result = copy.deepcopy(report)
        result['event_id'] = uuid.uuid4().hex
        result['event_type'] = event_type
        result['recorded_at'] = datetime.now(timezone.utc).isoformat()
        old = {n['id']: n['status'] for n in (before or {}).get('nodes', [])}
        result['transitions'] = [{'id': n['id'], 'text': n['text'], 'owner': n.get('owner'),
                                  'before': old.get(n['id']), 'after': n['status']}
                                 for n in result['graph']['nodes'] if n['status'] != old.get(n['id'])]
        with self.connection:
            self.connection.execute('INSERT INTO reports VALUES (?, ?, ?)',
                                    (result['event_id'], result['recorded_at'], json.dumps(result)))
        return result

    def get(self, event_id):
        row = self.connection.execute('SELECT payload FROM reports WHERE id = ?', (event_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def latest(self):
        row = self.connection.execute('SELECT payload FROM reports ORDER BY rowid DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None

    def summaries(self, limit=30):
        rows = self.connection.execute('SELECT payload FROM reports ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
        summaries = []
        for row in rows:
            report = json.loads(row[0])
            counts = {}
            for n in report['graph']['nodes']:
                counts[n['status']] = counts.get(n['status'], 0) + 1
            summaries.append({k: report.get(k) for k in ('event_id', 'event_type', 'recorded_at', 'checked_at',
                                                        'trigger', 'commit', 'transitions', 'last_resolution')} |
                             {'counts': counts, 'checked': len(report.get('verdicts', [])) if report['event_type'] == 'check' else 0,
                              'mode': 'human' if report['event_type'] == 'resolution' else
                                      (report.get('execution') or {}).get('mode') if report['event_type'] == 'check' else None,
                              'changed_paths': [c['path'] for c in report.get('changes', [])] if report['event_type'] == 'check' else []})
        return summaries

    def close(self):
        self.connection.close()
