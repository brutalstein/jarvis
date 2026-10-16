"""Optional isolated one-shot Browser Use worker. Requires a separate OS sandbox.

Only run for tasks explicitly authorized by JARVIS action gateway. Do not expose a TCP port.
"""
import asyncio
import json
import os
import sys

async def execute(task: str):
    from browser_use import Agent, ChatBrowserUse
    agent = Agent(task=task, llm=ChatBrowserUse())
    history = await asyncio.wait_for(agent.run(max_steps=12), timeout=120)
    # AgentHistoryList.final_result is an official helper, not proof of target state.
    return {'reported_result': history.final_result(), 'verified': False}

async def main():
    request = json.loads(sys.stdin.read(20000))
    if not isinstance(request, dict) or not isinstance(request.get('task'), str):
        raise ValueError('Invalid bounded browser job')
    if not os.getenv('BROWSER_USE_API_KEY'):
        raise RuntimeError('BROWSER_USE_API_KEY not configured')
    result = await execute(request['task'])
    print(json.dumps(result))

if __name__ == '__main__':
    asyncio.run(main())
