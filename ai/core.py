import aiohttp
from typing import Optional

_session: Optional[aiohttp.ClientSession] = None

def init_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=90),
            connector=aiohttp.TCPConnector(limit=100)
        )
    return _session

async def close_session():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None

def get_session():
    return init_session()
