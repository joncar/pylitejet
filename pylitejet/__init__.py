import logging
import serial
import threading
import asyncio
import queue

_LOGGER = logging.getLogger(__name__)

class AsyncSerialAdapter:
    def __init__(self, serial_instance: serial.Serial):
        self._serial = serial_instance
        self._loop = asyncio.get_running_loop()

        self._read_queue = queue.Queue()
        self._read_queue_event = asyncio.Event()
        self._write_queue = queue.Queue()
        self._open = True

        self._read_thread = threading.Thread(target=self._read_thread_impl, daemon=True)
        self._write_thread = threading.Thread(target=self._write_thread_impl, daemon=True)

        self._read_thread.start()
        self._write_thread.start()

    def _read_thread_impl(self):
        while self._open:
            line = self._serial.read_until(expected=b'\r')
            self._loop.call_soon_threadsafe(self._add_read, line)

    def _add_read(self, line: bytes):
        self._read_queue.put(line)
        self._read_queue_event.set()

    def _write_thread_impl(self):
        while self._open:
            line = self._write_queue.get()
            line = self._serial.write(line)

    async def read(self) -> bytes:
        while self._open:
            await self._read_queue_event.wait()
            if not self._read_queue.empty():
                return self._read_queue.get_nowait()
            else:
                self._read_queue_event.clear()
        raise Exception('Closed')

    async def write(self, data: bytes):
        self._write_queue.put(data)

    def close(self):
        pass

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
        self._open = False

    async def open(self, url: str):
        self._serial = serial.serial_for_url(
            url, baudrate=19200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE
        )
        self._adapter = AsyncSerialAdapter(self._serial)
        self._open = True
        self._reader_task = asyncio.create_task(self._reader_impl())

        # Auto detect which start symbol the MCP expects.
        self._start = '^'
        try:
            await self.get_all_load_states()
        except asyncio.exceptions.TimeoutError:
            self._start = '+'
        await self.get_all_load_states()

    async def _reader_impl(self):
        while self._open:
            line = await self._adapter.read()

            line = line[0:-1].decode('utf-8')

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
                self._recv_line = line[0:-1]
                self._recv_event.set()

    async def close(self):
        self._open = False
        self._adapter.close()
        self._serial.close()
        self._reader_task.cancel()

    async def _send(self, command: str):
        _LOGGER.debug('WantToSend "%s"', command)
        async with self._command_lock:
            _LOGGER.debug('Send "%s"', command)
            await self._adapter.write(bytes(f"{command}\n", 'utf-8'))

    async def _sendrecv(self, command: str):
        _LOGGER.debug('WantToSendRecv "%s"', command)
        async with self._command_lock:
            self._recv_event.clear()

            _LOGGER.debug('SendRecv(S) "%s"', command)
            await self._adapter.write(bytes(f"{command}\n", 'utf-8'))

            await asyncio.wait_for(self._recv_event.wait(), timeout=1)
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

    def _hex2bits(self, response, input_first, input_last, output_first):
        output = {}
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

    def on_load_activated(self, index: int, handler):
        self._add_event(f"N{index:03d}", handler)

    def on_load_deactivated(self, index: int, handler):
        self._add_event(f"F{index:03d}", handler)

    def on_switch_pressed(self, index: int, handler):
        self._add_event(f"P{index:03d}", handler)

    def on_switch_released(self, index: int, handler):
        self._add_event(f"R{index:03d}", handler)

    async def activate_load(self, index: int):
        await self._send(f"{self._start}A{index:03d}")

    async def deactivate_load(self, index: int):
        await self._send(f"{self._start}B{index:03d}")

    async def activate_scene(self, index: int):
        await self._send(f"{self._start}C{index:03d}")

    async def deactivate_scene(self, index: int):
        await self._send(f"{self._start}D{index:03d}")

    async def activate_load_at(self, index: int, level: int, rate_seconds: int):
        if index >= LiteJet.FIRST_LOAD_RELAY and index <= LiteJet.LAST_LOAD_RELAY:
            table = LiteJet.RELAY_RATE_SECONDS
        elif index >= LiteJet.FIRST_LOAD_LVRB and index <= LiteJet.LAST_LOAD_LVRB:
            table = LiteJet.LVRB_RATE_SECONDS
        else:
            table = LiteJet.FAN_RATE_SECONDS
        rate = self._seconds2rate(rate_seconds, table)
        await self._send(f"{self._start}E{index:03d}{level:02d}{rate:02d}")

    async def get_load_level(self, index: int) -> int:
        return int(await self._sendrecv(f"{self._start}F{index:03d}"))

    # ^G: Get instant on/off status of all loads on this board
    # ^H: Get instant on/off status of all switches on this board.

    async def get_all_load_states(self):
        response = await self._sendrecv(f"{self._start}G")
        return self._hex2bits(response, 0, 11, LiteJet.FIRST_LOAD)

    async def get_all_switch_states(self):
        response = await self._sendrecv(f"{self._start}H")
        return self._hex2bits(response, 0, 39, LiteJet.FIRST_SWITCH)

    async def press_switch(self, index: int):
        await self._send(f"{self._start}I{index:03d}")

    async def release_switch(self, index: int):
        await self._send(f"{self._start}J{index:03d}")

    async def get_switch_name(self, index: int):
        return (await self._sendrecv(f"{self._start}K{index:03d}")).strip()

    async def get_load_name(self, index: int):
        return (await self._sendrecv(f"{self._start}L{index:03d}")).strip()

    async def get_scene_name(self, index: int):
        return (await self._sendrecv(f"{self._start}M{index:03d}")).strip()

    def loads(self):
        return range(LiteJet.FIRST_LOAD, LiteJet.LAST_LOAD + 1)

    def button_switches(self):
        return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_BUTTON_SWITCH + 1)

    def all_switches(self):
        return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_SWITCH + 1)

    def scenes(self):
        return range(LiteJet.FIRST_SCENE, LiteJet.LAST_SCENE + 1)

async def open(url):
    lj = LiteJet()
    await lj.open(url)
    return lj