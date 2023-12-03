This project provides a pure Python3 library for interfacing with the LiteJet lighting system.

## Setup
1. You will need the LiteJet programming software from the [Dragon Technologies](https://www.dragontechinc.com/) Programming page.
2. Your LiteJet MCP should be configured for 19.2 K baud.
   1. For firmware versions 5.00 and higher, this setting is configured using the LiteJet software's Settings screen.
   2. For firmware versions 4.90 and lower, this setting is configured by setting DIP Switch 4 to OFF. Press the RESET button after changing this.
2. In the LiteJet software's Settings screen configure it to send "Third Party Carriage Return".
3. In the LiteJet software's Lights screen configure each load to announce changes. This is the "Load RS232" checkbox on each load's middle panel.
4. Connect the LiteJet's RS232-2 port to your computer.

If you have LiteJet 48 then the RS232-2 port is used to connect the two boards together. So you will need to configure RS232-1 for third party mode by setting DIP Switch 8 to ON and DIP Switch 3 to OFF. Press the RESET button after changing this. (To change RS232-1 back to programming mode, set DIP Switch 8 to OFF.)

## Test

1. List all buttons and loads: `python3 ./test.py --path /dev/serial0 list -l -b`
2. Monitor button presses and load changes: `python3 ./test.py --path /dev/serial0 monitor`
3. Control a load: `python3 ./test.py --path /dev/serial0 load 1 on`

## Sample

```python
import asyncio
import pylitejet

async def main():
    try:
        lj = await pylitejet.open("/dev/serial0")
    except pylitejet.LiteJetError as exc:
        print(f"Cannot connect: {exc}")
        return

    await lj.activate_load(1) # on

    await lj.deactivate_load(1) # off

    await lj.activate_load_at(1, 50, 8) # 50% over 8 seconds

    await lj.close()

asyncio.run(main())
```
