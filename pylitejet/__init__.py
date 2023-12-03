import logging
import serial
import threading
import asyncio
import queue
from typing import Optional, Dict
from itertools import chain
from enum import Enum

_LOGGER = logging.getLogger(__name__)

class Model(Enum):
    UNKNOWN = 0
    LITEJET = 1
    LITEJET_48 = 2

    def __str__(self):
        if self is Model.LITEJET:
            return "LiteJet"
        if self is Model.LITEJET_48:
            return "LiteJet 48"
        return self.name

class LiteJetError(Exception):
    pass


class LiteJetTimeout(LiteJetError):
    pass


class AsyncSerialAdapter:
    def __init__(self, url: str):
        self._url = url
        self._loop = asyncio.get_running_loop()
        self._thread_lock = threading.Lock()
        self._serial = None
        self.connected_changed = None

    def _connected_changed(self, connected: bool, reason: str):
        asyncio.run_coroutine_threadsafe(
            self.connected_changed(connected, reason), self._loop
        )

    def _ensure_connection(self):
        with self._thread_lock:
            serial_instance = self._serial

            if serial_instance is not None and not serial_instance.is_open:
                serial_instance = self._serial = None
                self._loop.call_soon_threadsafe(self._connected_changed, False, None)

            if serial_instance is None:
                _LOGGER.debug("Connecting to %s", self._url)
                try:
                    serial_instance = serial.serial_for_url(
                        self._url,
                        baudrate=19200,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                    )
                except serial.SerialException as exc:
                    raise LiteJetError(str(exc)) from exc

                self._serial = serial_instance
                _LOGGER.debug("Connected to %s", self._url)
                self._loop.call_soon_threadsafe(self._connected_changed, True, None)

            return serial_instance

    async def read(self) -> bytes:
        return await self._loop.run_in_executor(None, self._read)

    def _read(self) -> bytes:
        serial_instance = self._ensure_connection()
        try:
            return self._serial.read_until(expected=b"\r")
        except serial.SerialException as exc:
            self._close(f"due to exception: {exc}")
            raise LiteJetError() from exc

    async def write(self, data: bytes):
        await self._loop.run_in_executor(None, self._write, data)

    def _write(self, data: bytes):
        serial_instance = self._ensure_connection()
        try:
            serial_instance.write(data)
        except serial.SerialException as exc:
            self._close(f"due to exception: {exc}")
            raise LiteJetError() from exc

    async def open(self):
        await self._loop.run_in_executor(None, self._open)

    def _open(self):
        self._ensure_connection()

    async def close(self, reason="by request"):
        await self._loop.run_in_executor(None, self._close, reason)

    def _close(self, reason):
        with self._thread_lock:
            if self._serial is not None:
                _LOGGER.info("Disconnecting %s", reason)
                self._serial.close()
                self._serial = None
                self._loop.call_soon_threadsafe(self._connected_changed, False, reason)

    @property
    def connected(self):
        return self._serial is not None


class LiteJet:
    FIRST_LOAD = 1
    LAST_LOAD = 40
    FIRST_LOAD_RELAY = 1
    LAST_LOAD_RELAY = 24
    FIRST_LOAD_FAN = 25
    LAST_LOAD_FAN = 28
    FIRST_LOAD_LVRB = 29
    LAST_LOAD_LVRB = 40
    FIRST_SCENE = 1
    LAST_SCENE = 41
    FIRST_SWITCH = 1
    LAST_BUTTON_SWITCH = 96
    LAST_SWITCH = 138
    KEYPAD_COUNT = 16
    RELAY_RATE_SECONDS = [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        9,
        11,
        13,
        16,
        19,
        23,
        28,
        34,
        41,
        49,
        60,
        75,
        90,
        110,
        140,
        175,
        210,
        250,
        300,
        380,
        450,
        550,
        675,
        800,
    ]
    FAN_RATE_SECONDS = [0]
    LVRB_RATE_SECONDS = [
        0,
        0.25,
        0.50,
        0.75,
        1.00,
        1.50,
        2.00,
        2.50,
        3,
        4,
        5,
        6,
        7,
        8,
        10,
        12,
        14,
        16,
        18,
        20,
        25,
        30,
        45,
        60,
        90,
        120,
        300,
        600,
        900,
        1200,
        1800,
        2700,
    ]

    _serial: serial.Serial
    _adapter: AsyncSerialAdapter
    _reader_task: asyncio.Task
    _start: str

    def __init__(self):
        self._events = {}
        self._command_lock = asyncio.Lock()
        self._recv_event = asyncio.Event()
        self._recv_line = None
        self._reader_active = False
        self._open = False
        self.connected = False
        self.board_count = 1
        self.model = Model.UNKNOWN

    @property
    def model_name(self):
        return str(self.model)

    async def open(self, url: str):
        self._adapter = AsyncSerialAdapter(url)
        self._adapter.connected_changed = self._connected_changed
        await self._adapter.open()
        try:
            self._reader_active = True
            self._reader_task = asyncio.create_task(self._reader_impl())

            # Auto detect which start symbol the MCP expects.
            self._start = "^"
            try:
                await self.get_all_load_states()
            except LiteJetTimeout:
                _LOGGER.info("No response to '^'. Trying '+'...")
                self._start = "+"
            try:
                await self.get_all_load_states()
            except LiteJetTimeout:
                raise LiteJetError(
                    "No response to '+' or '^' command. No LiteJet MCP connected?"
                )

            # Auto detect if this is a dual MCP.
            try:
                await self._sendrecv(f"{self._start}g")
                self.model = Model.LITEJET_48
                self.board_count = 2
            except LiteJetTimeout:
                self.model = Model.LITEJET

            self._open = True
            await self._connected_changed(True, None)
        except:
            await self._adapter.close()
            raise

    async def _reader_impl(self):
        while self._reader_active:
            try:
                line = await self._adapter.read()
            except:
                await asyncio.sleep(5)
                continue

            line = line[0:-1].decode("utf-8")

            _LOGGER.debug(f'Read "{line}" ({len(line)})')
            if len(line) == 4 and (line[0] == "P" or line[0] == "R"):
                self._notify_event(line)
            elif len(line) == 4 and (line[0] == "F" or line[0] == "N"):
                self._notify_event(line)
            elif len(line) == 7 and line[0] == "^" and line[1] == "K":
                new_level = line[5:7]
                _LOGGER.debug("Dim event: '" + line[2:5] + "' '" + new_level + "'")
                event_name = "F" if new_level == "00" else "N"
                self._notify_event(event_name + line[2:5], int(new_level))
            else:
                self._recv_line = line
                self._recv_event.set()

    async def close(self):
        self._open = False
        self._reader_active = False
        await self._adapter.close()
        self._reader_task.cancel()

    async def _send(self, command: str):
        _LOGGER.debug('WantToSend "%s"', command)
        async with self._command_lock:
            _LOGGER.debug('Send "%s"', command)
            await self._adapter.write(bytes(f"{command}\n", "utf-8"))

    async def _sendrecv(self, command: str):
        _LOGGER.debug('WantToSendRecv "%s"', command)
        async with self._command_lock:
            self._recv_event.clear()

            _LOGGER.debug('SendRecv(S) "%s"', command)
            await self._adapter.write(bytes(f"{command}\n", "utf-8"))

            _LOGGER.debug("SendRecv(W)")
            try:
                await asyncio.wait_for(self._recv_event.wait(), timeout=1)
            except asyncio.exceptions.TimeoutError as exc:
                raise LiteJetTimeout() from exc

            result = self._recv_line
            _LOGGER.debug('SendRecv(R) "%s"', result)
            return result

    def _add_event(self, event_name, handler):
        event_list = self._events.get(event_name, None)
        if event_list is None:
            event_list = []
            self._events[event_name] = event_list
        event_list.append(handler)

    def _notify_event(self, event_name, *args):
        _LOGGER.debug('Event "%s"', event_name)
        event_list = self._events.get(event_name, None)
        if event_list is not None:
            for handler in event_list:
                handler(*args)

    def unsubscribe(self, handler):
        for event_name, event_list in self._events.items():
            event_list[:] = [x for x in event_list if x != handler]

    def _hex2bits(self, response: str, input_first: int, input_last: int, output_first: int, output: Dict[int, bool]):
        output_number = output_first
        for digit in range(input_first, input_last, 2):
            digit_value = int(response[digit : digit + 2], 16)
            for bit in range(0, 8):
                bit_value = (digit_value & (1 << bit)) != 0
                output[output_number] = bit_value
                output_number += 1
        return output

    def _seconds2rate(self, seconds, table):
        for candidate_rate, candidate_seconds in enumerate(table):
            if seconds <= candidate_seconds:
                return candidate_rate
        return len(table) - 1

    async def _connected_changed(self, connected: bool, reason: str):
        if not self._open:
            connected = False
        if connected:
            try:
                await self.get_all_load_states()
            except:
                connected = False
                reason = "due to non-responsive MCP"
                await self._adapter.close(reason)
        if connected != self.connected:
            self.connected = connected
            self._notify_event("CONN", connected, reason)

    def on_connected_changed(self, handler):
        self._add_event("CONN", handler)

    def on_load_activated(self, index: int, handler):
        self._add_event(f"N{index:03d}", handler)

    def on_load_deactivated(self, index: int, handler):
        self._add_event(f"F{index:03d}", handler)

    def on_switch_pressed(self, index: int, handler):
        self._add_event(f"P{index:03d}", handler)

    def on_switch_released(self, index: int, handler):
        self._add_event(f"R{index:03d}", handler)

    def _command(self, command: str, index: Optional[int] = None, last_index: Optional[int] = None):
        # If index exceeds this MCP's range, send it to the other MCP.
        if index is not None and index > last_index:
            command = command.lower()
            index -= last_index

        if index is None:
            return f"{self._start}{command}"
        return f"{self._start}{command}{index:03d}"

    async def activate_load(self, index: int):
        await self._send(self._command("A", index, LiteJet.LAST_LOAD))

    async def deactivate_load(self, index: int):
        await self._send(self._command("B", index, LiteJet.LAST_LOAD))

    async def activate_scene(self, index: int):
        await self._send(self._command("C", index, LiteJet.LAST_SCENE))

    async def deactivate_scene(self, index: int):
        await self._send(self._command("D", index, LiteJet.LAST_SCENE))

    async def activate_load_at(self, index: int, level: int, rate_seconds: int):
        if index >= LiteJet.FIRST_LOAD_RELAY and index <= LiteJet.LAST_LOAD_RELAY:
            table = LiteJet.RELAY_RATE_SECONDS
        elif index >= LiteJet.FIRST_LOAD_LVRB and index <= LiteJet.LAST_LOAD_LVRB:
            table = LiteJet.LVRB_RATE_SECONDS
        else:
            table = LiteJet.FAN_RATE_SECONDS
        rate = self._seconds2rate(rate_seconds, table)
        command = self._command("E", index, LiteJet.LAST_LOAD)
        await self._send(f"{command}{level:02d}{rate:02d}")

    async def get_load_level(self, index: int) -> int:
        return int(await self._sendrecv(self._command("F", index, LiteJet.LAST_LOAD)))

    # ^G: Get instant on/off status of all loads on this board
    # ^H: Get instant on/off status of all switches on this board.

    async def get_all_load_states(self):
        bits = {}
        response = await self._sendrecv(self._command("G"))
        self._hex2bits(response, 0, 11, LiteJet.FIRST_LOAD, bits)
        if self.board_count > 1:
            response = await self._sendrecv(self._command("g"))
            self._hex2bits(response, 0, 11, LiteJet.LAST_LOAD + 1, bits)
        return bits

    async def get_all_switch_states(self):
        bits = {}
        response = await self._sendrecv(self._command("H"))
        self._hex2bits(response, 0, 39, LiteJet.FIRST_SWITCH, bits)
        if self.board_count > 1:
            response = await self._sendrecv(self._command("h"))
            self._hex2bits(response, 0, 39, LiteJet.LAST_SWITCH + 1, bits)
        return bits

    async def press_switch(self, index: int):
        await self._send(self._command("I", index, LiteJet.LAST_SWITCH))

    async def release_switch(self, index: int):
        await self._send(self._command("J", index, LiteJet.LAST_SWITCH))

    async def get_switch_name(self, index: int):
        return (await self._sendrecv(self._command("K", index, LiteJet.LAST_SWITCH))).strip()

    async def get_load_name(self, index: int):
        return (await self._sendrecv(self._command("L", index, LiteJet.LAST_LOAD))).strip()

    async def get_scene_name(self, index: int):
        return (await self._sendrecv(self._command("M", index, LiteJet.LAST_SCENE))).strip()

    def loads(self):
        return range(LiteJet.FIRST_LOAD, LiteJet.LAST_LOAD * self.board_count + 1)

    def button_switches(self):
        result = range(LiteJet.FIRST_SWITCH, LiteJet.LAST_BUTTON_SWITCH + 1)
        if self.board_count > 1:
            result = chain(result, range(LiteJet.LAST_SWITCH + 1, LiteJet.LAST_SWITCH + LiteJet.LAST_BUTTON_SWITCH + 1))
        return result

    def all_switches(self):
        return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_SWITCH * self.board_count + 1)

    def scenes(self):
        return range(LiteJet.FIRST_SCENE, LiteJet.LAST_SCENE + 1)

    def get_switch_keypad_number(self, index: int):
        for board in range(0, self.board_count):
            if index < LiteJet.FIRST_SWITCH:
                return None
            if index <= LiteJet.LAST_BUTTON_SWITCH:
                # Keypad #1 has switches 1-6, #2 has 7-12, ...
                return (board * LiteJet.KEYPAD_COUNT) + (int((index - 1) / 6) + 1)
            if index <= LiteJet.LAST_SWITCH:
                # Touch Panel Programmer
                return 0
            index -= LiteJet.LAST_SWITCH

    def get_switch_keypad_name(self, index: int):
        keypad_number = self.get_switch_keypad_number(index)
        if keypad_number == 0:
            return "Touch Panel Programmer"
        return f"Keypad #{keypad_number}"

async def open(url):
    lj = LiteJet()
    await lj.open(url)
    return lj
