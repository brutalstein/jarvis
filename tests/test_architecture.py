"""Regression checks for canonical modules, one-way dependencies and compatibility."""
from __future__ import annotations

import ast
from pathlib import Path

from jarvis.adapters import N8N, OpenClaw, NotConfigured, checked_process, gemini_text
from jarvis.api import create_app
from jarvis.cli import main
from jarvis.contracts import Action, TaskSpec
from jarvis.engine import Engine
from jarvis.policy import ActionGate
from jarvis.routing import Router
from jarvis.storage import Store
from jarvis.application.engine import Engine as CoreEngine
from jarvis.application.policy import ActionGate as CoreGate
from jarvis.application.ports import TaskRepository
from jarvis.domain.contracts import Action as DomainAction, TaskSpec as DomainTaskSpec
from jarvis.domain.routing import Router as DomainRouter
from jarvis.entrypoints.cli import main as EntryMain
from jarvis.entrypoints.http import create_app as EntryApp
from jarvis.integrations.errors import NotConfigured as IntegrationError
from jarvis.integrations.gemini import gemini_text as GeminiAdapter
from jarvis.integrations.n8n import N8N as N8NAdapter
from jarvis.integrations.openclaw import OpenClaw as OpenClawAdapter
from jarvis.integrations.process import checked_process as ProcessAdapter
from jarvis.persistence.sqlite import Store as SQLiteStore


def test_backward_compatible_imports_share_exactly_one_implementation():
    pairs = (
        (N8N, N8NAdapter), (OpenClaw, OpenClawAdapter),
        (NotConfigured, IntegrationError), (checked_process, ProcessAdapter),
        (gemini_text, GeminiAdapter), (create_app, EntryApp), (main, EntryMain),
        (Action, DomainAction), (TaskSpec, DomainTaskSpec), (Engine, CoreEngine),
        (ActionGate, CoreGate), (Router, DomainRouter), (Store, SQLiteStore),
    )
    assert all(old is new for old, new in pairs)


ALLOWED = {
    'domain': {'domain'},
    'application': {'application', 'domain'},
    'persistence': {'persistence', 'domain'},
    'integrations': {'integrations', 'domain'},
    'entrypoints': {'entrypoints', 'application', 'domain', 'persistence', 'integrations'},
}


def test_dependency_direction_and_package_inventory():
    root = Path(__file__).resolve().parents[1] / 'jarvis'
    for package, allowed in ALLOWED.items():
        modules = list((root / package).glob('*.py'))
        assert modules, f'Missing core package {package}'
        for path in modules:
            parsed = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(parsed):
                if isinstance(node, ast.ImportFrom) and node.level >= 2:
                    top = (node.module or '').split('.')[0]
                    assert top in allowed, f'{package}/{path.name} imports forbidden {top}'
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith('jarvis.'):
                            top = alias.name.split('.')[1]
                            assert top in allowed, f'{package}/{path.name} imports forbidden {top}'


def test_legacy_facades_cannot_accumulate_duplicated_business_logic():
    root = Path(__file__).resolve().parents[1] / 'jarvis'
    for name in ('contracts', 'routing', 'policy', 'engine', 'storage', 'adapters', 'api', 'cli'):
        source = (root / (name + '.py')).read_text(encoding='utf-8')
        nodes = ast.parse(source).body
        assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       for node in nodes), f'Business code accidentally added to {name} facade'
        assert len(source.splitlines()) <= 20, f'{name} is no longer a thin facade'


def test_database_store_satisfies_business_repository_contract(tmp_path):
    storage = Store(str(tmp_path / 'port.db'))
    try:
        assert isinstance(storage, TaskRepository)
        task = Engine(storage).admit(TaskSpec('port-conformance'))
        assert task['status'] == 'READY'
    finally:
        storage.close()
