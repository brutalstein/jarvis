"""Operator CLI. Does not implicitly accept high-risk actions."""
from __future__ import annotations
import argparse
import json
import os
import secrets
from .contracts import Risk, TaskSpec
from .engine import Engine
from .policy import Principal
from .storage import Store


def main() -> None:
    p = argparse.ArgumentParser(prog='jarvis')
    p.add_argument('--db', default=os.getenv('JARVIS_DB', 'jarvis.sqlite3'))
    sub = p.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create')
    create.add_argument('objective')
    create.add_argument('--risk', choices=[r.value for r in Risk], default='LOW')
    create.add_argument('--key')
    for cmd in ('get', 'events', 'run-echo', 'approve-request', 'cancel'):
        child = sub.add_parser(cmd)
        child.add_argument('id')
        if cmd == 'run-echo':
            child.add_argument('--approval-id')
    grant = sub.add_parser('approve-grant')
    grant.add_argument('approval_id')
    grant.add_argument('--confirm', required=True)
    sub.add_parser('serve')
    sub.add_parser('new-token')
    args = p.parse_args()
    if args.command == 'new-token':
        print(secrets.token_urlsafe(36))
        return
    if args.command == 'serve':
        from .api import serve
        serve()
        return
    store = Store(args.db)
    engine = Engine(store)
    principal = Principal('local-operator', frozenset({'model.text'}))
    try:
        if args.command == 'approve-grant':
            result = {'granted': engine.gate.grant_approval(args.approval_id, human_confirmation=args.confirm)}
        elif args.command == 'create':
            result = engine.admit(TaskSpec(objective=args.objective, risk=Risk(args.risk), idempotency_key=args.key))
        elif args.command == 'get':
            result = store.get(args.id)
        elif args.command == 'events':
            result = store.history(args.id)
        elif args.command == 'approve-request':
            result = {'approval_id': engine.request_approval(args.id, principal), 'granted': False}
        elif args.command == 'run-echo':
            result = engine.run_echo(args.id, principal, approval_id=args.approval_id).__dict__
        elif args.command == 'cancel':
            result = engine.cancel(args.id)
        else:
            raise AssertionError('Unexpected command')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == '__main__':
    main()
