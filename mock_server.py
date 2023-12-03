import asyncio
import logging
import argparse
from mock_mcp import MockMCP, MockSystem

_LOGGER = logging.getLogger(__name__)


async def handle_client(reader, writer):
    _LOGGER.info("Client connected")
    loop = asyncio.get_running_loop()

    async def async_write(data):
        writer.write(data)
        await writer.drain()

    def handle_broadcast(data):
        asyncio.run_coroutine_threadsafe(async_write(data), loop)

    mcp.add_listener(handle_broadcast)

    while True:
        try:
            request = await reader.readuntil(separator=b"\n")
        except asyncio.exceptions.IncompleteReadError:
            break
        while len(request) > 0:
            length, response = mcp.handle_input(request)
            if response:
                await async_write(response)
            request = request[length:]
    writer.close()
    _LOGGER.info("Client disconnected")


async def run_server():
    port = 9999
    _LOGGER.info(f"Listening for connections on port {port}")
    server = await asyncio.start_server(handle_client, port=port)
    async with server:
        await server.serve_forever()


logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser("Emulate a LiteJet lighting system.")
parser.add_argument(
    "--litejet48",
    help="Emulate a LiteJet 48 (two LiteJet boards)",
    action="store_true"
)
args = parser.parse_args()

mcp = MockMCP(MockSystem.LITEJET_48 if args.litejet48 else MockSystem.LITEJET)

asyncio.run(run_server())
