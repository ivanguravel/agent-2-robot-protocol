#!/usr/bin/env python3
"""
CLI for controlling Unitree Go2 — real robot or Gazebo simulation.
Designed to be called by the Cursor agent (go2-control skill).

Usage:
    python3 go2_real/go2_cli.py walk --forward 0.9 --right 0.3
    python3 go2_real/go2_cli.py --sim walk --forward 0.9
    python3 go2_real/go2_cli.py rotate 90
    python3 go2_real/go2_cli.py stand
    python3 go2_real/go2_cli.py sit
    python3 go2_real/go2_cli.py stop
    python3 go2_real/go2_cli.py status

All commands output JSON to stdout. Exit code 0 = success, 1 = error.

Modes:
    (default)  — connect to real Go2 via unitree_sdk2_python
    --sim      — control simulated robot in Gazebo via docker exec
    --dry-run  — print planned action without any connection
"""

import argparse
import json
import os
import sys


def _output(data: dict, success: bool = True) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(0 if success else 1)


def _dry_run_result(command: str, params: dict) -> None:
    _output({
        "dry_run": True,
        "command": command,
        "params": params,
        "msg": "No robot connection — dry-run mode",
    })


def _get_client(args):
    """Return the appropriate client based on --sim or real mode."""
    if args.sim:
        from sim_client import SimClient
        client = SimClient()
        client.connect(container=args.container)
        return client
    else:
        from go2_client import Go2Client
        client = Go2Client()
        client.connect(interface=args.iface)
        return client


def cmd_walk(args):
    forward = args.forward or 0.0
    right = args.right or 0.0

    if forward == 0.0 and right == 0.0:
        _output({"status": "ok", "msg": "zero distance, nothing to do"})

    if args.dry_run:
        _dry_run_result("walk", {"forward_m": forward, "right_m": right})

    try:
        client = _get_client(args)
        result = client.move_distance(forward=forward, right=right)
        _output(result, success=(result.get("status") == "ok"))
    except Exception as e:
        _output({"status": "error", "msg": str(e)}, success=False)


def cmd_rotate(args):
    degrees = args.degrees

    if args.dry_run:
        _dry_run_result("rotate", {"degrees": degrees})

    try:
        client = _get_client(args)
        result = client.rotate(degrees)
        _output(result, success=(result.get("status") == "ok"))
    except Exception as e:
        _output({"status": "error", "msg": str(e)}, success=False)


def cmd_stand(args):
    if args.dry_run:
        _dry_run_result("stand", {})

    try:
        client = _get_client(args)
        result = client.stand()
        _output(result)
    except Exception as e:
        _output({"status": "error", "msg": str(e)}, success=False)


def cmd_sit(args):
    if args.dry_run:
        _dry_run_result("sit", {})

    try:
        client = _get_client(args)
        result = client.sit()
        _output(result)
    except Exception as e:
        _output({"status": "error", "msg": str(e)}, success=False)


def cmd_stop(args):
    if args.dry_run:
        _dry_run_result("stop", {})

    try:
        client = _get_client(args)
        result = client.stop()
        _output(result)
    except Exception as e:
        _output({"status": "error", "msg": str(e)}, success=False)


def cmd_status(args):
    if args.dry_run:
        _dry_run_result("status", {})

    try:
        client = _get_client(args)
        result = client.status()
        _output(result)
    except Exception as e:
        _output({"status": "error", "msg": str(e)}, success=False)


def main():
    parser = argparse.ArgumentParser(
        description="Unitree Go2 CLI — discrete movement commands (real robot or sim)"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--sim",
        action="store_true",
        default=os.environ.get("GO2_MODE", "").lower() == "sim",
        help="Control simulated robot in Gazebo via docker exec (or env GO2_MODE=sim)",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print planned action as JSON without connecting to robot",
    )
    parser.add_argument(
        "--container",
        default=os.environ.get("GO2_CONTAINER", "simulator-gui"),
        help="Docker container name for --sim mode (default: env GO2_CONTAINER or simulator-gui)",
    )
    parser.add_argument(
        "--iface",
        default=os.environ.get("GO2_IFACE", "eth0"),
        help="Network interface for real robot (default: env GO2_IFACE or eth0)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # walk
    p_walk = subparsers.add_parser("walk", help="Move forward/right by meters")
    p_walk.add_argument("--forward", type=float, default=0.0, help="Meters forward (negative = backward)")
    p_walk.add_argument("--right", type=float, default=0.0, help="Meters right (negative = left)")
    p_walk.set_defaults(func=cmd_walk)

    # rotate
    p_rotate = subparsers.add_parser("rotate", help="Rotate by degrees")
    p_rotate.add_argument("degrees", type=float, help="Degrees CCW (negative = CW)")
    p_rotate.set_defaults(func=cmd_rotate)

    # stand
    p_stand = subparsers.add_parser("stand", help="Stand up")
    p_stand.set_defaults(func=cmd_stand)

    # sit
    p_sit = subparsers.add_parser("sit", help="Sit down")
    p_sit.set_defaults(func=cmd_sit)

    # stop
    p_stop = subparsers.add_parser("stop", help="Emergency stop")
    p_stop.set_defaults(func=cmd_stop)

    # status
    p_status = subparsers.add_parser("status", help="Get robot telemetry")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
