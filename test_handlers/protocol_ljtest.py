from serial.serialutil import *
import logging
import threading
from mock_mcp import MockMCP

_LOGGER = logging.getLogger(__name__)


class Serial(SerialBase):
    def open(self):
        self._read_buffer = bytes()
        self._read_ready = threading.Event()
        self._read_ready.clear()
        self._mcp = MockMCP()
        self._mcp.add_listner(self._broadcast)
        self.is_open = True

    def close(self):
        self.is_open = False

    def from_url(self, url):
        _LOGGER.error("url is %s", url)

    @property
    def in_waiting(self):
        return len(self._read_buffer)

    @property
    def out_waiting(self):
        return 0

    def cancel_read(self):
        self._read_buffer = bytes()
        self._read_ready.set()

    def read(self, size=1):
        self._read_ready.wait()

        next_bytes = self._read_buffer[0:size]
        self._read_buffer = self._read_buffer[size:]
        if len(self._read_buffer) == 0:
            self._read_ready.clear()
        return next_bytes

    def _reconfigure_port(self):
        pass

    def write(self, data):
        length, response = self._mcp.handle_input(data)
        if response:
            self._respond(response)
        return length

    def _respond(self, b: bytes):
        self._read_buffer += b
        self._read_ready.set()
