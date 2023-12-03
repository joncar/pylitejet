#!/usr/bin/env python3
import sys
import logging
import argparse
import serial
import asyncio
import pylitejet


async def cmd_none(args):
    print("Nothing to do. See -h.")


# Command: info
async def cmd_info(lj, args):
    print(f"Model: {lj.model_name}")
    print(f"Board Count: {lj.board_count}")
    print(f"Load Count: {sum(1 for _ in lj.loads())}")
    print(f"Button Count: {sum(1 for _ in lj.button_switches())}")
    print(f"Scene Count: {sum(1 for _ in lj.scenes())}")

# Command: list
async def cmd_list(lj, args):
    if args.loads:
        load_states = await lj.get_all_load_states()
        for number in lj.loads():
            level = await lj.get_load_level(number) if load_states[number] else 0
            if args.hide_off and level == 0:
                continue
            name = await lj.get_load_name(number)
            if level == 0:
                level_string = "off"
            elif level == 99:
                level_string = "on"
            else:
                level_string = "at " + str(level) + "%"
            print('Load {} is named "{}" and is {}'.format(number, name, level_string))
    if args.scenes:
        for number in lj.scenes():
            name = await lj.get_scene_name(number)
            print('Scene {} is named "{}"'.format(number, name))
    if args.buttons:
        switch_states = await lj.get_all_switch_states()
        for number in lj.button_switches():
            if args.hide_off and not switch_states[number]:
                continue
            name = await lj.get_switch_name(number)
            is_pressed = " and is pressed" if switch_states[number] else ""
            keypad_name = lj.get_switch_keypad_name(number)
            print('Switch {} is named "{}" ({}){}'.format(number, name, keypad_name, is_pressed))
    if args.all_switches:
        switch_states = await lj.get_all_switch_states()
        for number in lj.all_switches():
            if args.hide_off and not switch_states[number]:
                continue
            name = await lj.get_switch_name(number)
            is_pressed = " and is pressed" if switch_states[number] else ""
            keypad_name = lj.get_switch_keypad_name(number)
            print('(All) Switch {} is named "{}" ({}){}'.format(number, name, keypad_name, is_pressed))


# Command: load
async def cmd_load(lj, args):
    name = await lj.get_load_name(args.number)
    level = await lj.get_load_level(args.number)
    if level == 0:
        level_string = "off"
    elif level == 99:
        level_string = "on"
    else:
        level_string = "at " + str(level) + "%"
    print(f'Load {args.number} is named "{name}" and is {level_string}')


async def cmd_load_on(lj, args):
    await lj.activate_load(args.number)
    await cmd_load(lj, args)


async def cmd_load_off(lj, args):
    await lj.deactivate_load(args.number)
    await cmd_load(lj, args)


async def cmd_load_set(lj, args):
    await lj.activate_load_at(args.number, args.level, args.rate)
    await cmd_load(lj, args)


# Command: switch
async def cmd_scene(lj, args):
    name = await lj.get_scene_name(args.number)
    print('Scene {} is named "{}"'.format(args.number, name))


async def cmd_scene_on(lj, args):
    await lj.activate_scene(args.number)
    await cmd_scene(lj, args)


async def cmd_scene_off(lj, args):
    await lj.deactivate_scene(args.number)
    await cmd_scene(lj, args)


# Command: switch
async def cmd_switch(lj, args):
    name = await lj.get_switch_name(args.number)
    print('Switch {} is named "{}"'.format(args.number, name))


async def cmd_switch_press(lj, args):
    await lj.press_switch(args.number)
    await cmd_switch(lj, args)


async def cmd_switch_release(lj, args):
    await lj.release_switch(args.number)
    await cmd_switch(lj, args)


# Command: monitor
async def cmd_monitor(lj: pylitejet.LiteJet, args):
    def capture(func, name, number):
        return lambda *args: func(name, number, *args)

    def load_activated(name, number, level):
        print("Load {} ({}) activated to {}%.".format(name, number, level or "??"))

    def load_deactivated(name, number, level):
        print("Load {} ({}) deactivated.".format(name, number))

    def switch_pressed(name, number):
        print("Switch {} ({}) pressed.".format(name, number))

    def switch_released(name, number):
        print("Switch {} ({}) released.".format(name, number))

    def connected_changed(connected: bool, reason: str):
        print("Connected" if connected else f"Disconnected {reason}")

    lj.on_connected_changed(connected_changed)

    for number in lj.loads():
        name = await lj.get_load_name(number)
        lj.on_load_activated(number, capture(load_activated, name, number))
        lj.on_load_deactivated(number, capture(load_deactivated, name, number))
    for number in lj.all_switches():
        name = await lj.get_switch_name(number)
        lj.on_switch_pressed(number, capture(switch_pressed, name, number))
        lj.on_switch_released(number, capture(switch_released, name, number))

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input, "Press any key to stop monitoring...")


# Main


async def main():
    parser = argparse.ArgumentParser("Control a LiteJet lighting system.")
    parser.set_defaults(func=None)
    parser.add_argument("--path", required=True)
    parser.add_argument(
        "-v",
        "--verbose",
        help="Show debug logging, including data sent and received via serial port.",
        action="store_const",
        const=logging.DEBUG,
        default=logging.WARN,
    )
    subparsers = parser.add_subparsers()

    parser_info = subparsers.add_parser("info", help="Information about the board.")
    parser_info.set_defaults(func=cmd_info)

    parser_list = subparsers.add_parser("list", help="List available items.")
    parser_list.add_argument("-l", "--loads", action="store_true")
    parser_list.add_argument("-s", "--scenes", action="store_true")
    parser_list.add_argument("-b", "--buttons", action="store_true")
    parser_list.add_argument("--all_switches", action="store_true")
    parser_list.add_argument("--hide_off", action="store_true")
    parser_list.set_defaults(func=cmd_list)

    parser_load = subparsers.add_parser("load", help="Change load level.")
    parser_load.add_argument("number", type=int)
    subparser_load = parser_load.add_subparsers()
    parser_load_set = subparser_load.add_parser(
        "set", help="Set load to a specific level."
    )
    parser_load_set.add_argument("level", type=int)
    parser_load_set.add_argument("rate", type=int, default=0)
    parser_load_set.set_defaults(func=cmd_load_set)
    parser_load_on = subparser_load.add_parser(
        "on", help="Set load to its default level."
    )
    parser_load_on.set_defaults(func=cmd_load_on)
    parser_load_off = subparser_load.add_parser("off", help="Turn off a load.")
    parser_load_off.set_defaults(func=cmd_load_off)
    parser_load_get = subparser_load.add_parser("get", help="Get load information.")
    parser_load_get.set_defaults(func=cmd_load)

    parser_scene = subparsers.add_parser("scene", help="Change scene activation.")
    parser_scene.add_argument("number", type=int)
    subparser_scene = parser_scene.add_subparsers()
    parser_scene_on = subparser_scene.add_parser("on", help="Turn on a scene.")
    parser_scene_on.set_defaults(func=cmd_scene_on)
    parser_scene_off = subparser_scene.add_parser("off", help="Turn off a scene.")
    parser_scene_off.set_defaults(func=cmd_scene_off)
    parser_scene_get = subparser_scene.add_parser("get", help="Get scene information.")
    parser_scene_get.set_defaults(func=cmd_scene)

    parser_switch = subparsers.add_parser("switch", help="Change switch activation.")
    parser_switch.add_argument("number", type=int)
    subparser_switch = parser_switch.add_subparsers()
    parser_switch_on = subparser_switch.add_parser(
        "press", help="Simulate pressing a switch."
    )
    parser_switch_on.set_defaults(func=cmd_switch_press)
    parser_switch_off = subparser_switch.add_parser(
        "release", help="Simulate releasing a switch."
    )
    parser_switch_off.set_defaults(func=cmd_switch_release)
    parser_switch_get = subparser_switch.add_parser(
        "get", help="Get switch information."
    )
    parser_switch_get.set_defaults(func=cmd_switch)

    parser_monitor = subparsers.add_parser(
        "monitor", help="Monitor items for state changes."
    )
    parser_monitor.set_defaults(func=cmd_monitor)

    args = parser.parse_args()

    logging.basicConfig(level=args.verbose)

    serial.protocol_handler_packages.append("test_handlers")

    try:
        lj = await pylitejet.open(args.path)
    except pylitejet.LiteJetError as exc:
        print(f"Cannot connect: {exc}")
        return

    if args.func is not None:
        await args.func(lj, args)

    await lj.close()


asyncio.run(main())
