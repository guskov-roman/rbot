# rbot, Automation Tool
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

import typing
import shlex
import re
import shutil

import rbot.exceptions
from rbot.channel import channel


def wait_for_shell(ch: channel.Channel) -> None:
    timeout = 0.2
    while True:
        ch.sendline("echo RBOT\\LOGIN")
        try:
            ch.expect("RBOTLOGIN", timeout=timeout)
            break
        except TimeoutError:
            timeout = 3.0


def posix_fetch_return_code(ch: channel.Channel) -> int:
    ch.sendline("echo $?", read_back=True)
    retcode_str = ch.read_until_prompt()
    try:
        return int(retcode_str)
    except ValueError:
        raise rbot.exceptions.InvalidRetcodeException(retcode_str)


def shell_sanity_check(ch: channel.Channel) -> None:
    ch.sendline("echo RBOT-SANITY-CHECK", read_back=True)
    output = ch.read_until_prompt()
    if output != "RBOT-SANITY-CHECK\n":
        raise rbot.exceptions.ChannelException()


def Re(pat: typing.Union[str, bytes], flags: int = 0) -> typing.Pattern[bytes]:
    """
    A bounded regex pattern for use with rbot.

    When using various channel-methods you sometimes need a regex pattern.
    ``rbot.Re`` is a convenience tool to create such patterns.
    """
    pat_bytes = pat if isinstance(pat, bytes) else pat.encode("utf-8")
    return __import__("re").compile(pat_bytes, flags)


def escape(*args: typing.Union[str, bytes]) -> str:
    string_args = []
    for arg in args:
        if isinstance(arg, str):
            string_args.append(shlex.quote(arg))
        elif isinstance(arg, bytes):
            string_args.append(shlex.quote(arg.decode("utf-8", errors="replace")))
        else:
            raise TypeError(f"{type(arg)!r} is not a supported argument type!")

    return " ".join(string_args)


class PosixChannel(channel.Channel):

    name: typing.Union[str, None] = None

    def __init__(self, channel_io: channel.ChannelIO):
        super().__init__(channel_io)

    def exec(self, *args: typing.Union[str, bytes]) -> typing.Tuple[int, str]:
        cmd = escape(*args)

        self.sendline(cmd, read_back=True)
        out = self.read_until_prompt()
        retcode = posix_fetch_return_code(self)

        return (retcode, out)

    def exec0(self, *args: typing.Union[str, bytes]) -> str:
        retcode, out = self.exec(*args)
        if retcode != 0:
            raise rbot.exceptions.CommandFailureException(cmd=escape(*args), out=out)
        return out

    def interactive(self, prompt: typing.Optional[str] = None) -> None:
        # Generate the endstring instead of having it as a constant
        # so opening this files won't trigger an exit
        endstr = (
            "INTERACTIVE-END-"
            + hex(165_380_656_580_165_943_945_649_390_069_628_824_191)[2:]
        )

        termsize = shutil.get_terminal_size()
        self.sendline(escape("stty", "cols", str(termsize.columns)))
        self.sendline(escape("stty", "rows", str(termsize.lines)))

        # Outer shell which is used to detect the end of the interactive session
        self.sendline(f"bash --norc --noprofile")
        self.sendline(f"PS1={endstr}")
        self.read_until_prompt(prompt=endstr)

        # Inner shell which will be used by the user
        self.sendline("bash --norc --noprofile")
        self.sendline("set -o emacs")
        if prompt is None:
            new_prompt = escape(
                f"\\[\\033[36m\\]{self.name}: \\[\\033[32m\\]\\w\\[\\033[0m\\]> "
            )
        else:
            new_prompt = escape(
                f"\\[\\033[36m\\]{prompt}: \\[\\033[32m\\]\\w\\[\\033[0m\\]> "
            )

        self.sendline(f"PS1={new_prompt}")

        self.read_until_prompt(prompt=re.compile(b"> (\x1B\\[.{0,10})?"))
        self.sendline()
        print("Entering interactive shell ...")

        self.attach_interactive(end_magic=endstr)

        print("Exiting interactive shell ...")

        try:
            self.sendline("exit")
            try:
                self.read_until_prompt(timeout=0.5)
            except TimeoutError:
                # we might still be in the inner shell so let's try exiting again
                self.sendline("exit")
                self.read_until_prompt(timeout=0.5)
        except TimeoutError:
            raise Exception("Failed to reacquire shell after interactive session!")
