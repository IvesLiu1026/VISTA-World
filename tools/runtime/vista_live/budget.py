"""Durable reservation before any network call; ambiguous requests never retry."""
import hashlib
import json
import sqlite3
import time


class Budget:
    LIMITS = {'decision': 1000, 'plan': 60, 'tts': 30}
    RESERVES = {'decision': .0015, 'plan': .02, 'tts': .04}

    def __init__(self, path, cap=2.0):
        self.path, self.cap = str(path), cap
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, kind TEXT, hash TEXT, reserve REAL, status TEXT, result TEXT, at REAL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10, isolation_level='IMMEDIATE')

    def reserve(self, ident, kind, body):
        if kind not in self.LIMITS:
            raise ValueError('Unsupported provider operation')
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT hash,status,result FROM requests WHERE id=?', (ident,)).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError('Request ID reused for different input')
                if row[1] != 'complete':
                    raise RuntimeError('Prior request started/failed; resubmission refused')
                return json.loads(row[2])
            used = db.execute('SELECT COALESCE(SUM(reserve),0) FROM requests').fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM requests WHERE kind=?', (kind,)).fetchone()[0]
            if count >= self.LIMITS[kind] or used + self.RESERVES[kind] > self.cap + 1e-9:
                raise RuntimeError('Persistent model budget exhausted')
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',
                       (ident, kind, digest, self.RESERVES[kind], 'started', None, time.time()))
        return None

    def finish(self, ident, result, ok=True):
        with self.connect() as db:
            db.execute('UPDATE requests SET status=?,result=? WHERE id=?',
                       ('complete' if ok else 'failed', json.dumps(result), ident))

    def status(self):
        with self.connect() as db:
            counts = dict(db.execute('SELECT kind,COUNT(*) FROM requests GROUP BY kind'))
            reserve = db.execute('SELECT COALESCE(SUM(reserve),0) FROM requests').fetchone()[0]
        return {'counts': counts, 'limits': self.LIMITS, 'reserved_usd': round(reserve, 6),
                'cap_usd': self.cap, 'reserve_is_not_reported_spend': True}
