import asyncio
from dna.runtime.mcp_tools import build_headers_provider


def test_headers_provider_reads_the_auth_hook_at_call_time():
    box = {"bearer": "t1"}
    provider = build_headers_provider(lambda: {"Authorization": f"Bearer {box['bearer']}"})
    assert provider()["Authorization"] == "Bearer t1"
    box["bearer"] = "t2"  # short-lived: re-read each call, never cached stale
    assert provider()["Authorization"] == "Bearer t2"
