import asyncio
from unittest.mock import MagicMock

m = MagicMock()


async def f():
    await m()
    print("Awaited successfully")


asyncio.run(f())
