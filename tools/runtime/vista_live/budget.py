"""Durable reservation before any network call; ambiguous requests never retry."""
import hashlib
import json
import math
import sqlite3
import time


class Budget:
    LIMITS = {'decision': 1000, 'plan': 60, 'tts': 30}
    RESERVES = {'decision': .0015, 'plan': .02, 'tts': .04}

    def __init__(self, path, cap=None, limits=None):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS allowance (id INTEGER PRIMARY KEY CHECK(id=1), cap REAL, limits TEXT)')
            agreed = db.execute('SELECT cap,limits FROM allowance WHERE id=1').fetchone()
            self.cap = cap if cap is not None else agreed[0] if agreed else 2.0
            self.LIMITS = dict(limits if limits is not None else json.loads(agreed[1]) if agreed else self.LIMITS)
            if (set(self.LIMITS) != {'decision', 'plan', 'tts'} or
                    any(type(n) is not int or n < 1 for n in self.LIMITS.values()) or
                    not math.isfinite(self.cap) or self.cap <= 0):
                raise ValueError('Invalid explicit budget')
            if agreed and (agreed[0] != self.cap or json.loads(agreed[1]) != self.LIMITS):
                raise ValueError('Existing task allowance cannot change on restart')
            db.execute('INSERT OR IGNORE INTO allowance VALUES (1,?,?)', (self.cap, json.dumps(self.LIMITS, sort_keys=True)))
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, kind TEXT, hash TEXT, reserve REAL, status TEXT, result TEXT, at REAL)')
            if 'reported_cost' not in {row[1] for row in db.execute('PRAGMA table_info(requests)')}:
                db.execute('ALTER TABLE requests ADD COLUMN reported_cost REAL')
            # Preserve every request/count/reservation. Reconcile only completed
            # responses with an actual provider-reported charge; unknown TTS and
            # failed/ambiguous calls retain their entire conservative reservation.
            for ident, result in db.execute("SELECT id,result FROM requests WHERE status='complete' AND reported_cost IS NULL").fetchall():
                cost = self.reported_cost(json.loads(result))
                if cost is not None:
                    db.execute('UPDATE requests SET reported_cost=? WHERE id=?', (cost, ident))

    @staticmethod
    def reported_cost(result):
        value = (result.get('usage') or {}).get('cost')
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None

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
            used = db.execute('SELECT COALESCE(SUM(COALESCE(reported_cost,reserve)),0) FROM requests').fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM requests WHERE kind=?', (kind,)).fetchone()[0]
            if count >= self.LIMITS[kind] or used + self.RESERVES[kind] > self.cap + 1e-9:
                raise RuntimeError('Persistent model budget exhausted')
            db.execute('INSERT INTO requests (id,kind,hash,reserve,status,result,at) VALUES (?,?,?,?,?,?,?)',
                       (ident, kind, digest, self.RESERVES[kind], 'started', None, time.time()))
        return None

    def finish(self, ident, result, ok=True):
        with self.connect() as db:
            db.execute('UPDATE requests SET status=?,result=?,reported_cost=? WHERE id=?',
                       ('complete' if ok else 'failed', json.dumps(result), self.reported_cost(result) if ok else None, ident))

    def status(self):
        with self.connect() as db:
            counts = dict(db.execute('SELECT kind,COUNT(*) FROM requests GROUP BY kind'))
            reserve = db.execute('SELECT COALESCE(SUM(reserve),0) FROM requests WHERE reported_cost IS NULL').fetchone()[0]
            reported = db.execute('SELECT COALESCE(SUM(reported_cost),0) FROM requests').fetchone()[0]
        return {'counts': counts, 'limits': self.LIMITS, 'reserved_usd': round(reserve, 6),
                'reported_spend_usd': round(reported, 6), 'committed_usd': round(reserve + reported, 6),
                'cap_usd': self.cap, 'reserve_is_not_reported_spend': True}
