import logging
import serial
import serial.threaded
import threading

_LOGGER = logging.getLogger(__name__)


class LiteJetReader(serial.threaded.LineReader):
    TERMINATOR = b"\r"

    def __init__(self):
        super(LiteJetReader, self).__init__()
        self._recv_event = threading.Event()

    def notify_event(self, event):
        pass

    def connection_made(self, transport):
        super(LiteJetReader, self).connection_made(transport)

    def connection_lost(self, exc):
        pass

    def handle_line(self, line):
        _LOGGER.debug('Read "%s"', line)
        if len(line) == 4 and (line[0] == "P" or line[0] == "R"):
            self.notify_event(line)
            return
        if len(line) == 4 and (line[0] == "F" or line[0] == "N"):
            self.notify_event(line)
            return
        if len(line) == 7 and line[0] == "^" and line[1] == "K":
            _LOGGER.debug("Dim event: '" + line[2:5] + "' '" + line[5:7] + "'")
            event_name = "F" if line[5:7] == "00" else "N"
            self.notify_event(event_name + line[2:5])
            return
        self._lastline = line
        self._recv_event.set()

    def get_response(self):
        self._recv_event.wait()
        self._recv_event.clear()
        return self._lastline


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

    def __init__(self, url):
        self._serial = serial.serial_for_url(
            url, baudrate=19200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE
        )
        self._events = {}
        self._command_lock = threading.Lock()
        self._thread = serial.threaded.ReaderThread(self._serial, LiteJetReader)
        self._thread.start()
        transport, self._protocol = self._thread.connect()
        self._protocol.notify_event = self._notify_event

    def close(self):
        self._thread.close()

    def _send(self, command):
        _LOGGER.debug('WantToSend "%s"', command)
        with self._command_lock:
            _LOGGER.debug('Send "%s"', command)
            self._protocol.write_line(command)

    def _sendrecv(self, command):
        _LOGGER.debug('WantToSendRecv "%s"', command)
        with self._command_lock:
            _LOGGER.debug('SendRecv(S) "%s"', command)
            self._protocol.write_line(command)
            result = self._protocol.get_response()
            _LOGGER.debug('SendRecv(R) "%s"', result)
            return result

    def _add_event(self, event_name, handler):
        event_list = self._events.get(event_name, None)
        if event_list == None:
            event_list = []
            self._events[event_name] = event_list
        event_list.append(handler)

    def _notify_event(self, event_name):
        _LOGGER.debug('Event "%s"', event_name)
        event_list = self._events.get(event_name, None)
        if event_list is not None:
            for handler in event_list:
                handler()

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

    def on_load_activated(self, index, handler):
        self._add_event("N{0:03d}".format(index), handler)

    def on_load_deactivated(self, index, handler):
        self._add_event("F{0:03d}".format(index), handler)

    def on_switch_pressed(self, index, handler):
        self._add_event("P{0:03d}".format(index), handler)

    def on_switch_released(self, index, handler):
        self._add_event("R{0:03d}".format(index), handler)

    def activate_load(self, index):
        self._send("^A{0:03d}".format(index))

    def deactivate_load(self, index):
        self._send("^B{0:03d}".format(index))

    def activate_scene(self, index):
        self._send("^C{0:03d}".format(index))

    def deactivate_scene(self, index):
        self._send("^D{0:03d}".format(index))

    def activate_load_at(self, index, level, rate_seconds):
        if index >= LiteJet.FIRST_LOAD_RELAY and index <= LiteJet.LAST_LOAD_RELAY:
            table = LiteJet.RELAY_RATE_SECONDS
        elif index >= LiteJet.FIRST_LOAD_LVRB and index <= LiteJet.LAST_LOAD_LVRB:
            table = LiteJet.LVRB_RATE_SECONDS
        else:
            table = LiteJet.FAN_RATE_SECONDS
        rate = self._seconds2rate(rate_seconds, table)
        self._send("^E{0:03d}{1:02d}{2:02d}".format(index, level, rate))

    def get_load_level(self, index):
        return int(self._sendrecv("^F{0:03d}".format(index)))

    # ^G: Get instant on/off status of all loads on this board
    # ^H: Get instant on/off status of all switches on this board.

    def get_all_load_states(self):
        response = self._sendrecv("^G")
        return self._hex2bits(response, 0, 11, LiteJet.FIRST_LOAD)

    def get_all_switch_states(self):
        response = self._sendrecv("^H")
        return self._hex2bits(response, 0, 39, LiteJet.FIRST_SWITCH)

    def press_switch(self, index):
        self._send("^I{0:03d}".format(index))

    def release_switch(self, index):
        self._send("^J{0:03d}".format(index))

    def get_switch_name(self, index):
        return self._sendrecv("^K{0:03d}".format(index)).strip()

    def get_load_name(self, index):
        return self._sendrecv("^L{0:03d}".format(index)).strip()

    def get_scene_name(self, index):
        return self._sendrecv("^M{0:03d}".format(index)).strip()

    def loads(self):
        return range(LiteJet.FIRST_LOAD, LiteJet.LAST_LOAD + 1)

    def button_switches(self):
        return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_BUTTON_SWITCH + 1)

    def all_switches(self):
        return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_SWITCH + 1)

    def scenes(self):
        return range(LiteJet.FIRST_SCENE, LiteJet.LAST_SCENE + 1)
