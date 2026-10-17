"""SQLite single-host durable store; conditional writes are serialized with IMMEDIATE transactions.

Do not use this as a multi-host distributed lease service. See docs/LIMITATIONS.md.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
import threading
import time
from typing import Iterator
from uuid import uuid4

from ..domain.contracts import Conflict, Denied, State, TaskSpec, TRANSITIONS

SCHEMA = '''
CREATE TABLE IF NOT EXISTS tasks(
 id TEXT PRIMARY KEY, objective TEXT NOT NULL, category TEXT NOT NULL, capability TEXT NOT NULL,
 risk TEXT NOT NULL, status TEXT NOT NULL, correlation_id TEXT NOT NULL,
 parent_id TEXT REFERENCES tasks(id), idempotency_key TEXT UNIQUE,
 provider TEXT, attempt INTEGER NOT NULL DEFAULT 0,
 lease_holder TEXT, lease_until REAL, result TEXT, evidence TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dependencies(task_id TEXT NOT NULL REFERENCES tasks(id), requires TEXT NOT NULL REFERENCES tasks(id), PRIMARY KEY(task_id, requires));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id), kind TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), action_digest TEXT NOT NULL,
 expires_at REAL NOT NULL, granted_at REAL, consumed_at REAL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actions(action_digest TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), status TEXT NOT NULL,
 outcome TEXT, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id,id);
'''

def utc() -> str:
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path: str = 'jarvis.sqlite3') -> None:
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA busy_timeout=5000')
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
            else:
                self.db.execute('COMMIT')

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def event(self, task_id: str, kind: str, data: dict | None = None) -> None:
        self.db.execute('INSERT INTO events(task_id,kind,data,at) VALUES(?,?,?,?)',
                        (task_id, kind, json.dumps(data or {}, sort_keys=True), utc()))

    def get(self, task_id: str) -> dict:
        with self.lock:
            row = self.db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            return dict(row)

    def history(self, task_id: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM events WHERE task_id=? ORDER BY id', (task_id,))]

    def _ensure_acyclic(self, task_id: str, dependencies: tuple[str, ...]) -> None:
        # New task cannot be depended on by any existing task; still protect against bad input.
        if task_id in dependencies:
            raise Denied('Self dependency')
        for dep in dependencies:
            if self.db.execute('SELECT 1 FROM tasks WHERE id=?', (dep,)).fetchone() is None:
                raise Denied(f'Unknown dependency: {dep}')

    def create(self, spec: TaskSpec) -> dict:
        spec.validate()
        task_id = str(uuid4())
        with self.tx():
            if spec.idempotency_key:
                existing = self.db.execute('SELECT id,objective,category,capability,risk,parent_id FROM tasks WHERE idempotency_key=?',
                                           (spec.idempotency_key,)).fetchone()
                if existing:
                    if (existing['objective'], existing['category'], existing['capability'], existing['risk']) != (
                            spec.objective, spec.category, spec.capability, spec.risk.value):
                        raise Conflict('Idempotency key reused for a different request')
                    old_deps = tuple(sorted(r['requires'] for r in self.db.execute(
                        'SELECT requires FROM dependencies WHERE task_id=?', (existing['id'],))))
                    if existing['parent_id'] != spec.parent_id or old_deps != tuple(sorted(spec.dependencies)):
                        raise Conflict('Idempotency key reused with different dependencies or parent')
                    return self.get(existing['id'])
            if spec.parent_id and not self.db.execute('SELECT 1 FROM tasks WHERE id=?', (spec.parent_id,)).fetchone():
                raise Denied('Unknown parent')
            self._ensure_acyclic(task_id, spec.dependencies)
            now = utc()
            self.db.execute('''INSERT INTO tasks(id,objective,category,capability,risk,status,correlation_id,parent_id,idempotency_key,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (task_id, spec.objective, spec.category, spec.capability,
               spec.risk.value, State.CREATED, str(uuid4()), spec.parent_id, spec.idempotency_key, now, now))
            for dep in spec.dependencies:
                self.db.execute('INSERT INTO dependencies(task_id,requires) VALUES(?,?)', (task_id, dep))
            self.event(task_id, 'task.created', {'dependencies': list(spec.dependencies)})
        return self.get(task_id)

    def claim_admission(self, task_id: str) -> bool:
        """Claim CREATED->VALIDATING atomically to prevent concurrent duplicate admits."""
        with self.tx():
            changed = self.db.execute(
                'UPDATE tasks SET status=?,updated_at=? WHERE id=? AND status=?',
                (State.VALIDATING, utc(), task_id, State.CREATED),
            )
            if changed.rowcount:
                self.event(task_id, 'state.changed',
                           {'from': State.CREATED, 'to': State.VALIDATING})
            return changed.rowcount == 1

    def transition(self, task_id: str, new: State, data: dict | None = None, *, owner: str | None = None) -> dict:
        with self.tx():
            task = self.get(task_id)
            old = State(task['status'])
            if new not in TRANSITIONS[old]:
                raise Conflict(f'Illegal transition {old} -> {new}')
            # A caller without a lease must never transition an actively owned task.
            if task['lease_holder'] is not None and task['lease_holder'] != owner:
                raise Conflict('Worker does not hold lease')
            if task['lease_holder'] is not None and (
                task['lease_until'] is None or task['lease_until'] <= time.time()
            ):
                raise Conflict('Worker lease expired; reconcile before mutation')
            if new == State.COMPLETED:
                evidence = data.get('evidence') if data else None
                if not data or data.get('verified') is not True or not isinstance(evidence, dict):
                    raise Denied('Completion requires verification evidence')
                digest = evidence.get('action_digest')
                if not isinstance(digest, str):
                    raise Denied('Completion requires an associated verified action')
                verification = self.db.execute(
                    'SELECT status,outcome FROM actions WHERE action_digest=? AND task_id=?',
                    (digest, task_id),
                ).fetchone()
                if not verification or verification['status'] != 'VERIFIED':
                    raise Denied('Action not verified for this task')
                if json.loads(verification['outcome']) != evidence:
                    raise Denied('Evidence does not match recorded verifier output')
            if old == State.RECOVERY_REQUIRED and new == State.READY:
                unresolved = self.db.execute('''SELECT 1 FROM actions
                    WHERE task_id=? AND status IN ('INTENT_RECORDED','RECOVERY_REQUIRED') LIMIT 1''',
                    (task_id,)).fetchone()
                if unresolved:
                    raise Denied('Unreconciled action: external effect must be investigated before retry')
            if new == State.READY:
                unmet = self.db.execute('''SELECT 1 FROM dependencies d JOIN tasks t ON t.id=d.requires
                                          WHERE d.task_id=? AND t.status!=? LIMIT 1''',
                                        (task_id, State.COMPLETED)).fetchone()
                if unmet:
                    raise Denied('Dependencies not complete')
            self.db.execute('UPDATE tasks SET status=?,updated_at=?,result=COALESCE(?,result),evidence=COALESCE(?,evidence) WHERE id=?',
                            (new, utc(), json.dumps(data['result']) if data and 'result' in data else None,
                             json.dumps(data['evidence']) if data and 'evidence' in data else None, task_id))
            self.event(task_id, 'state.changed', {'from': old, 'to': new, **(data or {})})
        return self.get(task_id)

    def lease(self, task_id: str, worker: str, now: float, seconds: float = 60) -> bool:
        if not worker or seconds <= 0:
            raise Denied('Invalid lease')
        with self.tx():
            row = self.db.execute('''UPDATE tasks SET lease_holder=?,lease_until=?,attempt=attempt+1
             WHERE id=? AND status=? AND (lease_holder IS NULL OR lease_until<?)''',
             (worker, now + seconds, task_id, State.READY, now))
            if row.rowcount:
                self.event(task_id, 'lease.acquired', {'holder': worker})
            return row.rowcount == 1

    def release(self, task_id: str, worker: str) -> None:
        with self.tx():
            row = self.db.execute('UPDATE tasks SET lease_holder=NULL,lease_until=NULL WHERE id=? AND lease_holder=?',
                                  (task_id, worker))
            if not row.rowcount:
                raise Conflict('Lease not owned')
            self.event(task_id, 'lease.released')

    def quarantine(self, task_id: str, reason: str, *, owner: str | None = None) -> None:
        """Privileged recovery transition: mark an externally ambiguous task non-runnable."""
        with self.tx():
            task = self.get(task_id)
            if task['lease_holder'] is not None and task['lease_holder'] != owner:
                raise Conflict('Recovery attempted by non-owner')
            if State(task['status']) in (State.COMPLETED, State.FAILED, State.CANCELLED, State.BLOCKED):
                raise Conflict('Terminal task cannot be quarantined')
            self.db.execute('UPDATE tasks SET status=?,updated_at=? WHERE id=?',
                            (State.RECOVERY_REQUIRED, utc(), task_id))
            self.event(task_id, 'recovery.required', {'reason': reason})

    def reconcile_interrupted(self) -> list[str]:
        """Quarantine both interrupted workers AND orphaned/uncertain action intentions."""
        with self.tx():
            rows = self.db.execute('''SELECT DISTINCT t.id FROM tasks t
                LEFT JOIN actions a ON a.task_id=t.id
                WHERE t.status IN (?,?,?,?)
                  OR (t.status=? AND t.lease_holder IS NOT NULL)
                  OR (a.status IN ('INTENT_RECORDED','RECOVERY_REQUIRED')
                      AND t.status NOT IN (?,?,?,?,?))''',
                (State.RUNNING, State.VERIFYING, State.VALIDATING,
                 State.PLANNING, State.READY,
                 State.COMPLETED, State.FAILED, State.CANCELLED,
                 State.BLOCKED, State.RECOVERY_REQUIRED)).fetchall()
            for row in rows:
                self.db.execute('UPDATE tasks SET status=?,lease_holder=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                                (State.RECOVERY_REQUIRED, utc(), row['id']))
                self.db.execute('''UPDATE actions SET status='RECOVERY_REQUIRED'
                    WHERE task_id=? AND status='INTENT_RECORDED' ''', (row['id'],))
                self.event(row['id'], 'recovery.required',
                           {'reason': 'interrupted worker or unresolved external action'})
            return [row['id'] for row in rows]
