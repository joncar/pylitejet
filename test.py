#!/usr/bin/env python3
import sys
import logging
import argparse
import serial
from pylitejet import LiteJet


def cmd_none(args):
    print("Nothing to do. See -h.")


# Command: list
def cmd_list(args):
    if args.loads:
        load_states = lj.get_all_load_states()
        for number in lj.loads():
            level = lj.get_load_level(number) if load_states[number] else 0
            if args.hide_off and level == 0:
                continue
            name = lj.get_load_name(number)
            if level == 0:
                level_string = "off"
            elif level == 99:
                level_string = "on"
            else:
                level_string = "at " + str(level) + "%"
            print('Load {} is named "{}" and is {}'.format(number, name, level_string))
    if args.scenes:
        for number in lj.scenes():
            name = lj.get_scene_name(number)
            print('Scene {} is named "{}"'.format(number, name))
    if args.buttons:
        switch_states = lj.get_all_switch_states()
        for number in lj.button_switches():
            if args.hide_off and not switch_states[number]:
                continue
            name = lj.get_switch_name(number)
            is_pressed = " and is pressed" if switch_states[number] else ""
            print('Switch {} is named "{}"{}'.format(number, name, is_pressed))
    if args.all_switches:
        switch_states = lj.get_all_switch_states()
        for number in lj.all_switches():
            if args.hide_off and not switch_states[number]:
                continue
            name = lj.get_switch_name(number)
            is_pressed = " and is pressed" if switch_states[number] else ""
            print('(All) Switch {} is named "{}"{}'.format(number, name, is_pressed))


# Command: load
def cmd_load(args):
    name = lj.get_load_name(args.number)
    level = lj.get_load_level(args.number)
    if level == 0:
        level_string = "off"
    elif level == 99:
        level_string = "on"
    else:
        level_string = "at " + str(level) + "%"
    print('Load {} is named "{}" and is {}'.format(args.number, name, level_string))


def cmd_load_on(args):
    lj.activate_load(args.number)
    cmd_load(args)


def cmd_load_off(args):
    lj.deactivate_load(args.number)
    cmd_load(args)


def cmd_load_set(args):
    lj.activate_load_at(args.number, args.level, args.rate)
    cmd_load(args)


# Command: switch
def cmd_scene(args):
    name = lj.get_scene_name(args.number)
    print('Scene {} is named "{}"'.format(args.number, name))


def cmd_scene_on(args):
    lj.activate_scene(args.number)
    cmd_scene(args)


def cmd_scene_off(args):
    lj.deactivate_scene(args.number)
    cmd_scene(args)


# Command: switch
def cmd_switch(args):
    name = lj.get_switch_name(args.number)
    print('Switch {} is named "{}"'.format(args.number, name))


def cmd_switch_press(args):
    lj.press_switch(args.number)
    cmd_switch(args)


def cmd_switch_release(args):
    lj.release_switch(args.number)
    cmd_switch(args)


# Command: monitor
def cmd_monitor(args):
    def capture(func, name, number):
        return lambda: func(name, number)

    def load_activated(name, number):
        print("Load {} ({}) activated.".format(name, number))

    def load_deactivated(name, number):
        print("Load {} ({}) deactivated.".format(name, number))

    def switch_pressed(name, number):
        print("Switch {} ({}) pressed.".format(name, number))

    def switch_released(name, number):
        print("Switch {} ({}) released.".format(name, number))

    for number in lj.loads():
        name = lj.get_load_name(number)
        lj.on_load_activated(number, capture(load_activated, name, number))
        lj.on_load_deactivated(number, capture(load_deactivated, name, number))
    for number in lj.all_switches():
        name = lj.get_switch_name(number)
        lj.on_switch_pressed(number, capture(switch_pressed, name, number))
        lj.on_switch_released(number, capture(switch_released, name, number))
    input("Press any key to stop monitoring...")


# Main

parser = argparse.ArgumentParser("Control a LiteJet lighting system.")
parser.set_defaults(func=None)
parser.add_argument("--path", required=True)
parser.add_argument(
    "-v",
    "--verbose",
    help="Show debug logging, including data sent and received via serial port.",
    action="store_const",
    const=logging.INFO,
    default=logging.WARN,
)
subparsers = parser.add_subparsers()

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
parser_load_set = subparser_load.add_parser("set", help="Set load to a specific level.")
parser_load_set.add_argument("level", type=int)
parser_load_set.add_argument("rate", type=int, default=0)
parser_load_set.set_defaults(func=cmd_load_set)
parser_load_on = subparser_load.add_parser("on", help="Set load to its default level.")
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
parser_switch_get = subparser_switch.add_parser("get", help="Get switch information.")
parser_switch_get.set_defaults(func=cmd_switch)

parser_monitor = subparsers.add_parser(
    "monitor", help="Monitor items for state changes."
)
parser_monitor.set_defaults(func=cmd_monitor)

args = parser.parse_args()

logging.basicConfig(level=args.verbose)

serial.protocol_handler_packages.append("test_handlers")

lj = LiteJet(args.path)

if args.func is not None:
    args.func(args)

lj.close()
