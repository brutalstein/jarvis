"""Bounded subprocess helper, not an OS security sandbox."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from ..domain.contracts import Denied, UncertainOutcome

async def checked_process(program: str, args: list[str], *, cwd: Path, timeout: float = 90, output_limit: int = 2_000_000) -> str:
    """Trusted executable only. No shell; bounded pipe reads; scrub unrelated env secrets.

    This is NOT OS isolation. A malicious executable can still access the caller's files.
    Do not route arbitrary LLM-generated commands here.
    """
    if not cwd.is_dir() or timeout <= 0 or not 1024 <= output_limit <= 2_000_000:
        raise Denied('Invalid process boundary')
    if not Path(program).name or any('\x00' in a for a in args):
        raise Denied('Invalid subprocess parameters')
    safe_env = {k: v for k, v in os.environ.items() if k.upper() in {
        'PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG',
        'GOOGLE_API_KEY', 'GEMINI_API_KEY', 'APPDATA', 'LOCALAPPDATA'}}
    proc = await asyncio.create_subprocess_exec(program, *args, cwd=cwd, env=safe_env,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def bounded(stream: asyncio.StreamReader) -> bytes:
        result = bytearray()
        while chunk := await stream.read(65536):
            result.extend(chunk)
            if len(result) > output_limit:
                raise Denied('Provider output exceeds configured size limit')
        return bytes(result)

    stdout_task = asyncio.create_task(bounded(proc.stdout))
    stderr_task = asyncio.create_task(bounded(proc.stderr))
    try:
        _code, stdout, _stderr = await asyncio.wait_for(asyncio.gather(
            proc.wait(), stdout_task, stderr_task), timeout)
    except (TimeoutError, Denied, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            proc.kill()
        stdout_task.cancel()
        stderr_task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        await proc.wait()
        if isinstance(exc, TimeoutError):
            raise UncertainOutcome('Provider exceeded time budget; side effects unverified') from None
        raise
    if proc.returncode != 0:
        raise Denied(f'Provider failed with exit code {proc.returncode}; sensitive diagnostics suppressed')
    return stdout.decode('utf-8', errors='replace')
