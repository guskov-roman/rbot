#!/usr/bin/env python3
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

import logparser  # type: ignore
from rbot.log import Verbosity

"""Print all ["msg",cmd, ...] log events."""


def main() -> None:
    events = logparser.from_argv()
    for ev in events:
        if ev.type[0] == "tc" and ev.type[1] == "begin":
            print(f"[{ev.timestamp}][{ev.data["name"]}] started")
        elif ev.type[0] == "tc" and ev.type[1] == "end":
            print(f"[{ev.timestamp}][{ev.data["name"]}] end")
        elif ev.type[0] == "msg":
            print(
                f"[{ev.timestamp}][{Verbosity(int(ev.type[1])).name}]: {ev.data["text"]}"
            )
        elif ev.type[0] == "cmd":
            print(f"[{ev.timestamp}][COMMAND]: {ev.data["cmd"]}\n{ev.data["stdout"]}")


if __name__ == "__main__":
    main()
