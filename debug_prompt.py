import asyncio
from plesk_unified.server import mcp


async def run():
    p = await mcp.get_prompt("plesk-api-integration", {"api_operation": "test"})
    print(f"Type: {type(p)}")
    print(f"Content: {p}")


if __name__ == "__main__":
    asyncio.run(run())
