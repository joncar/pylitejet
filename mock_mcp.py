import logging

_LOGGER = logging.getLogger(__name__)


class MockMCP:
    def __init__(self):
        self._load_levels = {}
        self._switch_pressed = {}
        self._broadcast_receivers = []

    def _broadcast(self, line: str):
        b = line.encode("utf-8")
        _LOGGER.info(f"bcst MCP: {b}")
        for r in self._broadcast_receivers:
            r(b)

    def add_listener(self, r):
        self._broadcast_receivers.append(r)

    def set_load(self, number: int, level: int):
        self._load_levels[number] = level
        self._broadcast(f"^K{number:03d}{level:02d}\r")

    def set_switch(self, number: int, pressed: bool):
        if self._switch_pressed.get(number, False) == pressed:
            return
        self._switch_pressed[number] = pressed
        if pressed:
            event = "P"
        else:
            event = "R"
        self._broadcast(f"{event}{number:03d}\r")

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
        if command != "G" and command != "H":
            number = int(str[2:5])
        if command == "A":
            self.set_load(number, 99)
            command_length = 5
        elif command == "B":
            self.set_load(number, 0)
            command_length = 5
        elif command == "C" or command == "D":
            _LOGGER.warning("Scenes not supported")
        elif command == "E":
            level = int(str[5:7])
            rate = int(str[7:9])
            self.set_load(number, level)
            command_length = 9
        elif command == "F":
            response = f"{self._load_levels.get(number, 0):02d}\r"
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
            self.set_switch(number, True)
            command_length = 5
        elif command == "J":
            self.set_switch(number, False)
            command_length = 5
        elif command == "K":
            response = f"Switch #{number}\r"
            command_length = 5
        elif command == "L":
            response = f"Load #{number}\r"
            command_length = 5
        elif command == "M":
            response = f"Scene #{number}\r"
            command_length = 5
        if response:
            response = response.encode("utf-8")
            _LOGGER.info(f"from MCP: {response}")
        return command_length, response
