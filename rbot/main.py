# rbot, System Development Automation Tool
# Copyright (C) 2025  Roman Guskov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import string
import sys
import os
import argparse
from typing import List, Optional, Sequence

import rbot
from rbot import loader


def get_version() -> str:
    try:
        from importlib import metadata  # type: ignore

        try:
            return metadata.version("rbot")  # type: ignore
        except metadata.PackageNotFoundError:  # type: ignore
            pass
    except ImportError:
        pass

    try:
        from rbot import _version  # type: ignore

        return _version.version  # type: ignore
    except ImportError:
        pass

    return "unknown"


def build_parser() -> argparse.ArgumentParser:

    parser = RbotArgumetParser(
        prog="rbot",
        description="Rbot Test and Development Automation Tool",
        fromfile_prefix_chars="@",
    )

    parser.add_argument(
        "-C",
        metavar="WORKDIR",
        dest="workdir",
        help="use WORKDIR as working directory instead of the current directory.",
    )

    parser.add_argument("-c", "--config", help="path to the boards config file")
    parser.add_argument("-tc", "--testcase", help="path to the file with testcases")
    parser.add_argument("-l", "--log", help="write a log to the specified file")
    parser.add_argument(
        "-verbose", dest="verbosity", default=0, type=int, help="set the verbosity"
    )
    parser.add_argument(
        "-nsf", "--no-stop", action="store_false", help="no stop if a testcase fail"
    )
    parser.add_argument(
        "-k",
        "--keep-alive",
        dest="keep_alive",
        action="store_true",
        default=False,
        help="keep machines alive for later tests to reacquire them",
    )
    parser.add_argument("--debug", action="store_true", help="enable debug mode")
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {get_version()}"
    )
    return parser


class RbotArgumetParser(argparse.ArgumentParser):
    def convert_arg_line_to_args(self, arg_line: str) -> List[str]:
        """
        Make it possible to use shell variables also in argumentsfiles.
        """
        try:
            arg_line_expanded = string.Template(arg_line).substitute(os.environ)
        except KeyError as e:
            raise rbot.error.RbotException(
                f"Could not find environment variable: {e.args[0]!r}"
            ) from None

        return [arg_line_expanded]


def main(argv: Optional[Sequence[str]] = None) -> None:  # noqa: C901
    """Rbot main entry point."""
    parser = build_parser()

    args = parser.parse_args(argv)

    if args.workdir:
        os.chdir(args.workdir)

    sys.path.insert(1, os.getcwd())

    import rbot

    rbot.log.rbot_start()

    if args.log:
        rbot.log.LOGFILE = open(args.log, "w")

    if args.verbosity:
        rbot.log.VERBOSITY = rbot.log.Verbosity(args.verbosity)

    if args.debug:
        rbot.log.VERBOSITY = rbot.log.Verbosity.CHANNEL

    rbot.ctx = rbot.Context(add_defaults=True, keep_alive=args.keep_alive)

    try:
        if args.config:
            loader.load_config(args.config, rbot.ctx)

        if args.testcase:
            loader.load_testcase(args.testcase, rbot.ctx)

        ret = rbot.ctx.run_test(args.no_stop)

    except Exception as e:
        import traceback

        trace = traceback.format_exc(limit=-6)
        rbot.log.exception(e.__class__.__name__, trace)
        rbot.log.rbot_end(False)
        sys.exit(1)
    except KeyboardInterrupt:
        rbot.log.exception("KeyboardInterrupt", "Test run manually aborted.")
        rbot.log.rbot_end(False)
        sys.exit(1)
    except SystemExit as e:
        rbot.log.exception("SystemExit triggered.", "")
        rbot.log.rbot_end(e.code in (None, 0))
    else:
        result = True if ret == 0 else False
        rbot.log.rbot_end(result)


if __name__ == "__main__":
    main(sys.argv)
