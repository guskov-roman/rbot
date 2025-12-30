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

import re
import typing
import time
import subprocess
from typing import Any

import rbot.error
from rbot import machine
from rbot.machine import channel
from rbot.machine.shell import linux

M = typing.TypeVar("M", bound="linux.LinuxShell")


def wait_for_shell(ch: channel.Channel) -> None:
    # Repeatedly sends `echo rbot''LOGIN\r`.  At some point, the shell
    # interprets this command and prints out `rbotLOGIN` because of the
    # quotation-marks being removed.  Once we detect this, this function
    # can return, knowing the shell is now running on the other end.
    #
    # Credit to Pavel for this idea!
    timeout = 0.2
    while True:
        ch.sendline("echo RBOT\\LOGIN")
        try:
            ch.expect("RBOTLOGIN", timeout=timeout)
            break
        except TimeoutError:
            # Increase the timeout after the first try because the remote might
            # just be a bit slow to get ready.  If we spam it too much, we will
            # actually slow down the shell initialization...
            timeout = 3.0


def posix_fetch_return_code(ch: channel.Channel, mach: M) -> int:
    ch.sendline("echo $?", read_back=True)
    retcode_str = ch.read_until_prompt()
    try:
        return int(retcode_str)
    except ValueError:
        raise rbot.error.InvalidRetcodeError(mach, retcode_str) from None


def posix_environment(
    mach: M, var: str, value: "typing.Union[str, linux.Path[M], None]" = None
) -> str:
    if value is not None:
        mach.exec0("export", linux.Raw(f"{mach.escape(var)}={mach.escape(value)}"))
        if isinstance(value, linux.Path):
            return value.at_host(mach)
        else:
            return value
    else:
        # Escape environment variable name, unless it is one of a few special names
        if var not in ["!", "$"]:
            var = mach.escape(var)
        # Add a space in front of the expanded environment variable to ensure
        # values like `-E` will not get picked up as parameters by echo.  This
        # space is then cut away again so calling tests don't notice this trick.
        return mach.exec0("echo", linux.Raw(f'" ${{{var}}}"'))[1:-1]


def shell_sanity_check(mach: M) -> None:
    mach.ch.sendline("echo rbot-SANITY-CHECK", read_back=True)
    output = mach.ch.read_until_prompt()
    if output != "rbot-SANITY-CHECK\n":
        raise rbot.error.UncleanShellError(mach)


def xmodem_upload(
    file: str, port: str, callback: typing.Optional[typing.Callable] = None
) -> int:
    cmd = f"sx {file} < {port} > {port}"
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True
    )
    total_size = None
    send_size = None
    if callable(callback):
        while True:
            line = proc.stderr.readline()  # type: ignore
            if "blocks" in line:
                total_size = int(line[line.find(",") + 1 : line.find("blocks")].strip())
            elif "Xmodem sectors/kbytes sent:" in line:
                str_process = line.split(":")[1].strip()
                send_size = int(str_process[: str_process.find("/")])
                callback(total_size, send_size)
            if proc.poll() is not None:
                break
            time.sleep(0.1)

    return proc.wait()


# 7-bit C1 ANSI sequences, see https://stackoverflow.com/a/14693789
_ANSI_ESCAPE = re.compile(
    r"""
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
""",
    re.VERBOSE,
)


def strip_ansi_escapes(s: str) -> str:
    """
    Strip all ANSI escape sequences from a string

    This helper can be used when programs have colored output and piping with
    ``| cat`` doesn't help (e.g. forced color as with ``--color=always``).

    .. versionadded:: 0.9.2
    """
    return _ANSI_ESCAPE.sub("", s)


CMD_CONTEXT = typing.Callable[
    ["RunCommandProxy"], typing.Generator[str, None, typing.Tuple[int, str]]
]


class RunCommandProxy(channel.Channel):
    """
    Proxy for interacting with a running command.

    A ``RunCommandProxy`` is created with a context-manager and
    :py:meth:`LinuxShell.run() <rbot.machine.linux.LinuxShell.run>`.

    **Example**:

    .. code-block:: python

        with lh.run("gdb", lh.workdir / "a.out") as gdb:
            gdb.sendline("target remote 127.0.0.1:3333")
            gdb.sendline("load")
            gdb.sendline("mon reset halt")

            gdb.sendline("quit")
            gbd.terminate0()

    A ``RunCommandProxy`` has all methods of a :py:class:`~rbot.machine.channel.Channel`
    for interacting with the remote.  Additionally, a few more methods exist
    which are necessary to end a command's invokation properly.  **You must
    always call one of them before leaving the context-manager!**  These methods are:
    """

    _write_blacklist: typing.List[int]
    _c: channel.ChannelIO
    _c2: channel.ChannelIO

    @staticmethod
    def _ctx(
        *,
        channel: channel.Channel,
        context: CMD_CONTEXT,
        host: "machine.Machine",
        args: Any,
    ) -> "typing.Iterator[RunCommandProxy]":
        """
        Helper function for LinuxShell.run() implementations.  See the comment
        near the CMD_CONTEXT definition in this file for more details.
        """
        with channel.borrow() as ch:
            proxy = RunCommandProxy(ch, context, host, args)

            try:
                yield proxy
            except Exception as e:
                proxy._cmd_context.throw(e.__class__, e)
            proxy._assert_end()

    def __new__(
        cls,
        chan: channel.Channel,
        cmd_context: CMD_CONTEXT,
        host: "machine.Machine",
        args: Any,
    ) -> "RunCommandProxy":
        chan.__class__ = cls
        return typing.cast(RunCommandProxy, chan)

    def __init__(
        self,
        chan: channel.Channel,
        cmd_context: CMD_CONTEXT,
        host: "machine.Machine",
        args: Any,
    ) -> None:
        self._proxy_alive = True
        self._cmd_context = cmd_context(self)
        self._cmd = next(self._cmd_context)
        self._c2 = self._c
        self._exc_host = host
        self._exc_args = args

    def terminate0(self) -> str:
        """
        Wait for the command to end **successfully**.

        Asserts that the command returned with retcode 0.  If it did not, an
        exception is raised.

        :returns: Remaining output of the command until completion.
        :rtype: str
        """
        retcode, output = self.terminate()
        if retcode != 0:
            raise rbot.error.CommandFailure(
                self._exc_host, self._exc_args, repr=self._cmd
            )
        return output

    def terminate(self) -> typing.Tuple[int, str]:
        """
        Wait for the command to end.

        :returns: A tuple of return code and remaining output.
        :rtype: tuple(int, str)
        """
        assert self._proxy_alive, "Attempting to terminate multiple times"

        self._c = self._c2
        try:
            next(self._cmd_context)
        except StopIteration as s:
            retval = typing.cast(typing.Tuple[int, str], s.args[0])
            assert isinstance(retval, tuple), "generator returned wrong type"
        else:
            raise RuntimeError("runctx generator didn't stop")

        self._proxy_alive = False
        self._c = CommandEndedChannel()

        return retval

    def _pre_terminate(self) -> None:
        """
        Mark the command as terminated.

        This is useful when a runctx detected that a command exited prematurely.
        """
        self._c = CommandEndedChannel()

    def _assert_end(self) -> None:
        """Ensure that this proxy was properly terminated."""
        if self._proxy_alive:
            raise RuntimeError(
                "A run-command proxy needs to be terminated before leaving its context!"
            )


class CommandEndedException(
    channel.DeathStringException, channel.ChannelTakenException
):
    """
    The command which was run (interactively) ended prematurely.

    This exception might be raised when reading from (or writing to) a
    :py:class:`~rbot.machine.linux.RunCommandProxy` and the remote command
    exited during the call.  You can catch the exception but after receiving
    it, no more interaction with the command is allowed except the final
    :py:meth:`~RunCommandProxy.terminate0` or
    :py:meth:`~RunCommandProxy.terminate`.

    **Example**:

    .. code-block:: python

        with lh.run("foo", "command") as foo:
            try:
                while True:
                    foo.read_until_prompt("$ ")
                    foo.sendline("echo some command")
            except linux.CommandEndedException:
                pass

            foo.terminate0()
    """

    def __str__(self) -> str:
        return "Interactive command ended while attempting to interact with it."


class CommandEndedChannel(channel.channel.ChannelTaken):
    exception = CommandEndedException
