import logging
import serial
import threading

_LOGGER = logging.getLogger(__name__)

class LiteJetThread(threading.Thread):

   def __init__(self, serial, notify_event):
      threading.Thread.__init__(self, name='LiteJetThread', daemon=True)
      self._serial = serial
      self._lastline = None
      self._recv_event = threading.Event()
      self._notify_event = notify_event

   def run(self):
      while True:
         line = self._readline()
         if len(line)==4 and (line[0]=='P' or line[0]=='R'):
            self._notify_event(line)
            continue
         if len(line)==4 and (line[0]=='F' or line[0]=='N'):
            self._notify_event(line)
            continue
         self._lastline = line
         self._recv_event.set()

   def _readline(self):
      output = ''
      while True:
         byte = self._serial.read(size=1)
         if (byte[0] == 0x0d):
            break
         output += byte.decode('utf-8')
      return output

   def get_response(self):
      self._recv_event.wait()
      self._recv_event.clear()
      return self._lastline

class LiteJet:
   FIRST_LOAD = 1
   LAST_LOAD = 40
   FIRST_SCENE = 1
   LAST_SCENE = 41
   FIRST_SWITCH = 1
   LAST_BUTTON_SWITCH = 96
   LAST_SWITCH = 138

   def __init__(self, url):
      self._serial = serial.serial_for_url(url, baudrate=19200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE)
      self._events = {}
      self._thread = LiteJetThread(self._serial, self._notify_event)
      self._thread.start()
      self._command_lock = threading.Lock()

   def _send(self, command):
      with self._command_lock:
         _LOGGER.info('Send "%s"', command)
         self._serial.write(command.encode('utf-8'))

   def _sendrecv(self, command):
      with self._command_lock:
         _LOGGER.info('Send "%s"', command)
         self._serial.write(command.encode('utf-8'))
         result = self._thread.get_response()
         _LOGGER.info('Recv "%s"', result)
         return result

   def _add_event(self, event_name, handler):
      event_list = self._events.get(event_name, None)
      if event_list == None:
         event_list = []
         self._events[event_name] = event_list
      event_list.append(handler)

   def _notify_event(self, event_name):
      _LOGGER.info('Event "%s"', event_name)
      event_list = self._events.get(event_name, None)
      if event_list is not None:
         for handler in event_list:
            handler()

   def _hex2bits(self, response, input_first, input_last, output_first):
      output = {}
      output_number = output_first
      for digit in range(input_first, input_last, 2):
         digit_value = int(response[digit:digit+2], 16)
         for bit in range(0, 8):
            bit_value = (digit_value & (1 << bit)) != 0
            output[output_number] = bit_value
            output_number += 1
      return output
 
   def on_load_activated(self, index, handler):
      self._add_event('N{0:03d}'.format(index), handler)

   def on_load_deactivated(self, index, handler):
      self._add_event('F{0:03d}'.format(index), handler)

   def on_switch_pressed(self, index, handler):
      self._add_event('P{0:03d}'.format(index), handler)

   def on_switch_released(self, index, handler):
      self._add_event('R{0:03d}'.format(index), handler)

   def activate_load(self, index):
      self._send('^A{0:03d}'.format(index))

   def deactivate_load(self, index):
      self._send('^B{0:03d}'.format(index))

   def activate_scene(self, index):
      self._send('^C{0:03d}'.format(index))

   def deactivate_scene(self, index):
      self._send('^D{0:03d}'.format(index))

   def activate_load_at(self, index, level, rate):
      self._send('^E{0:03d}{1:02d}{2:02d}'.format(index, level, rate))

   def get_load_level(self, index):
      return int(self._sendrecv('^F{0:03d}'.format(index)))

   # ^G: Get instant on/off status of all loads on this board
   # ^H: Get instant on/off status of all switches on this board.

   def get_all_load_states(self):
      response = self._sendrecv('^G')
      return self._hex2bits(response, 0, 11, LiteJet.FIRST_LOAD)

   def get_all_switch_states(self):
      response = self._sendrecv('^H')
      return self._hex2bits(response, 0, 39, LiteJet.FIRST_SWITCH)

   def press_switch(self, index):
      self._send('^I{0:03d}'.format(index))

   def release_switch(self, index):
      self._send('^J{0:03d}'.format(index))

   def get_switch_name(self, index):
      return self._sendrecv('^K{0:03d}'.format(index)).strip()

   def get_load_name(self, index):
      return self._sendrecv('^L{0:03d}'.format(index)).strip()

   def get_scene_name(self, index):
      return self._sendrecv('^M{0:03d}'.format(index)).strip()

   def loads(self):
      return range(LiteJet.FIRST_LOAD, LiteJet.LAST_LOAD+1)

   def button_switches(self):
      return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_BUTTON_SWITCH+1)

   def all_switches(self):
      return range(LiteJet.FIRST_SWITCH, LiteJet.LAST_SWITCH+1)

   def scenes(self):
      return range(LiteJet.FIRST_SCENE, LiteJet.LAST_SCENE+1)

