import logging
from enum import Enum

_LOGGER = logging.getLogger(__name__)

class MockSystem(Enum):
    LITEJET = 1
    LITEJET_48 = 2

class MockMCP:
    def __init__(self, system: MockSystem = MockSystem.LITEJET):
        self._system = system
        self._load_levels = {}
        self._switch_pressed = {}
        self._broadcast_receivers = []
        self._other = None
        self._prefix = ""

        if system == MockSystem.LITEJET_48:
            self._prefix = "Alpha "
            self._other = MockMCP(MockSystem.LITEJET)
            self._other._prefix = "Bravo "
            self._other._other = self

    def _broadcast(self, line: str):
        b = line.encode("utf-8")
        _LOGGER.info(f"bcst MCP: {b}")
        for r in self._broadcast_receivers:
            r(b)

    def _broadcast_other(self, line: str):
        if self._other:
            self._other._broadcast(line)

    def add_listener(self, r):
        self._broadcast_receivers.append(r)

    def set_load(self, number: int, level: int):
        self._load_levels[number] = level
        self._broadcast(f"^K{number:03d}{level:02d}\r")
        self._broadcast_other(f"^K{number+40:03d}{level:02d}\r")

    def set_switch(self, number: int, pressed: bool):
        if self._switch_pressed.get(number, False) == pressed:
            return
        self._switch_pressed[number] = pressed
        if pressed:
            event = "P"
        else:
            event = "R"
        self._broadcast(f"{event}{number:03d}\r")

    def get_load(self, number: int):
        return self._load_levels.get(number, 0)

    def get_switch_name(self, number: int):
        return f"{self._prefix}Switch #{number}"

    def get_load_name(self, number: int):
        return f"{self._prefix}Load #{number}"

    def get_scene_name(self, number: int):
        return f"{self._prefix}Scene #{number}"

    def handle_input(self, data: bytes):
        _LOGGER.info(f"  to MCP: {data}")
        str = data.decode("utf-8")

        # Skip until a command start marker
        start_index = 0
        while start_index < len(str) and str[start_index] != "+":
            start_index += 1
        if start_index != 0:
            _LOGGER.debug(f"Skipped {start_index} bytes")
            return start_index, None

        command = str[1]
        response = None
        mcp = self
        if command.islower() and self._other:
            mcp = self._other
            command = command.upper()
        if command in "ABCDEFIJKLM":
            number = int(str[2:5])
        if command == "A":
            mcp.set_load(number, 99)
            command_length = 5
        elif command == "B":
            mcp.set_load(number, 0)
            command_length = 5
        elif command == "C" or command == "D":
            _LOGGER.warning("Scenes not supported")
        elif command == "E":
            level = int(str[5:7])
            rate = int(str[7:9])
            mcp.set_load(number, level)
            command_length = 9
        elif command == "F":
            response = f"{mcp.get_load(number):02d}\r"
            command_length = 5
        elif command == "G":
            _LOGGER.warning("Instant status not supported")
            response = "000000000000000000000000000000000000000000000000\r"
            command_length = 2
        elif command == "H":
            _LOGGER.warning("Instant status not supported")
            response = "00000000000000000000000000000000000000 0000000000000000000000000000000000000000000000000000000000\r"
            command_length = 2
        elif command == "I":
            mcp.set_switch(number, True)
            command_length = 5
        elif command == "J":
            mcp.set_switch(number, False)
            command_length = 5
        elif command == "K":
            response = f"{mcp.get_switch_name(number)}\r"
            command_length = 5
        elif command == "L":
            response = f"{mcp.get_load_name(number)}\r"
            command_length = 5
        elif command == "M":
            response = f"{mcp.get_scene_name(number)}\r"
            command_length = 5
        else:
            _LOGGER.warning(f"Unknown command '{command}'")
            command_length = 2
        if response:
            response = response.encode("utf-8")
            _LOGGER.info(f"from MCP: {response}")
        return command_length, response
