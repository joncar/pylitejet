from serial.serialutil import *
import logging
import threading

_LOGGER = logging.getLogger(__name__)

class LJTestSerial(SerialBase):
    def open(self):
        self._read_buffer = bytes()
        self._read_ready = threading.Event()
        self._read_ready.clear()
        self._load_levels = {}
        self._switch_pressed = {}

    def close(self):
        pass

    def fromURL(self, url):
        _LOGGER.debug('url is %s', url)

    def read(self, size=1):
        _LOGGER.debug('read %d bytes', size)
        assert size == 1
        self._read_ready.wait()

        next_bytes = self._read_buffer[0:size]
        self._read_buffer = self._read_buffer[size:]
        if len(self._read_buffer) == 0:
            self._read_ready.clear()
        _LOGGER.debug('read satisfied with %s', next_bytes)
        return next_bytes

    def _set_load(self, number, level):
        self._load_level[number] = level
        self._respond('^K{0:03d}{1:02d}'.format(number, level))

    def _set_switch(self, number, pressed):
        if self._switch_pressed[number] == pressed:
            return
        self._switch_pressed[number] = pressed
        if pressed:
            event = 'P'
        else:
            event = 'R'
        self._respond('{0}{1:03d}'.format(event, number))

    def write(self, data):
        str = data.decode('utf-8')
        _LOGGER.debug('write %s', str)
        assert str[0] == '^'
        command = str[1]
        if command != 'G' and command != 'H':
            number = int(str[3:5])
        if command == 'A':
            self._set_load(number, 99)
        elif command == 'B':
            self._set_load(number, 0)
        elif command == 'C' or command == 'D':
            _LOGGER.warning('Scenes not supported')
        elif command == 'E':
            level = int(str[6:8])
            rate = int(str[8:10])
            self._set_load(number, level)
        elif command == 'F':
            self._respond('{0:02d}\r'.format(self._load_levels.get(number, 0)))
        elif command == 'G':
            _LOGGER.warning('Instant status not supported')
            self._respond('000000000000000000000000000000000000000000000000\r')
        elif command == 'H':
            _LOGGER.warning('Instant status not supported')
            self._respond('00000000000000000000000000000000000000 0000000000000000000000000000000000000000000000000000000000\r')
        elif command == 'I':
            self._set_switch(number, True)
        elif command == 'J':
            self._set_switch(number, False)
        elif command == 'K':
            self._respond('Switch #{}\r'.format(number))
        elif command == 'L':
            self._respond('Load #{}\r'.format(number))
        elif command == 'M':
            self._respond('Scene #{}\r'.format(number))
        return len(data)

    def _respond(self, str):
        _LOGGER.debug('response: %s', str)
        self._read_buffer = str.encode('utf-8')
        self._read_ready.set()

class Serial(LJTestSerial, io.RawIOBase):
    pass
