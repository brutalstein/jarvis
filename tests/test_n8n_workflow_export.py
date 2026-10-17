"""Validate that the example n8n import cannot carry plaintext credentials."""
import json
from pathlib import Path


def test_n8n_workflow_export_contract():
    root = Path(__file__).resolve().parents[1]
    workflow = json.loads((root / 'examples' / 'n8n' / 'verified-echo.json').read_text())
    assert workflow['active'] is False
    assert len(workflow['nodes']) == 2
    assert workflow['nodes'][0]['type'] == 'n8n-nodes-base.manualTrigger'
    request = workflow['nodes'][1]
    assert request['type'] == 'n8n-nodes-base.httpRequest'
    params = request['parameters']
    assert params['method'] == 'POST'
    assert params['url'].endswith('/v1/integrations/n8n/echo')
    assert params['genericAuthType'] == 'httpHeaderAuth'
    assert 'credentials' not in request
    assert 'workflow_id: $workflow.id' in params['jsonBody']
    assert 'execution_id: $execution.id' in params['jsonBody']
    assert 'token' not in params['jsonBody'].lower()
