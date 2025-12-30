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

import contextlib
import re
import time
import typing

import rbot
from .. import shell, machine, channel
from ..shell.linux import special, util


class UefiStartupEvent(rbot.log.EventIO):
    def __init__(self, uefi: machine.Machine) -> None:
        self.uefi = uefi
        super().__init__(
            ["board", "uefi", uefi.name],
            rbot.log.c("UEFI").bold + f" ({uefi.name})",
            verbosity=rbot.log.Verbosity.QUIET,
        )

        self.verbosity = rbot.log.Verbosity.STDOUT
        self.prefix = "   <> "

    def close(self) -> None:
        setattr(self.uefi, "bootlog", self.getvalue())
        self.data["output"] = self.getvalue()
        super().close()


class UefiStartup(machine.Machine):
    _uefi_init_event: typing.Optional[rbot.log.EventIO] = None
    _timeout_start: typing.Optional[float] = None

    boot_timeout: typing.Optional[float] = None
    """
    Maximum time from power-on to UEFI shell.

    If rbot can't reach the UEFI shell during this time, an exception will be thrown.
    """

    def _uefi_startup_event(self) -> rbot.log.EventIO:
        if self._uefi_init_event is None:
            self._uefi_init_event = UefiStartupEvent(self)

            self._timeout_start = time.monotonic()

        return self._uefi_init_event


class UefiAutobootIntercept(machine.Initializer, UefiStartup):
    """
    Machine-initializer to intercept UEFI autobooting.

    The default settings for this class should work for most cases, but if a
    custom autoboot prompt was configured, or a special key sequence is
    necessary, you will have to adjust this here.

    **Example**:

    .. code-block:: python

        import re

        class MyUefi(
            board.Connector,
            board.UefiAutobootIntercept,
            board.UefiShell,
        ):
            autoboot_prompt = b"ESC (setup), F1 (shell), ENTER (boot)"
            autoboot_keys = b"\x1bOP" # F1 Code
    """

    autoboot_prompt: bytes = b"ESC (setup), F1 (shell), ENTER (boot)"

    """
    Autoboot prompt to wait for.
    """

    autoboot_keys: typing.Union[str, bytes] = b"\x1bOP"
    """
    Keys to press as soon as autoboot prompt is detected.
    """

    @contextlib.contextmanager
    def _init_machine(self) -> typing.Iterator:
        if self.autoboot_prompt is not None:
            with self.ch.with_stream(self._uefi_startup_event()):
                timeout = None
                if self.boot_timeout is not None:
                    assert self._timeout_start is not None
                    timeout = self.boot_timeout - (
                        time.monotonic() - self._timeout_start
                    )

                try:
                    self.ch.read_until_prompt(
                        prompt=self.autoboot_prompt, timeout=timeout
                    )
                except TimeoutError:
                    raise TimeoutError(
                        "Uefi autoboot prompt did not show up in time"
                    ) from None
                self.ch.send(self.autoboot_keys, _ignore_blacklist=True)
                self.ch.sendcontrol("[")
        yield None


_hush_find_unsafe = re.compile(r"[^\w@%+=:,./-]", re.ASCII).search


def _hush_quote(s: str) -> str:
    if not s:
        return '""'
    if _hush_find_unsafe(s) is None:
        return s

    # - Quote \ (inside quotes) as \\
    # - Quote single quotes using a \ (outside the original quotes).
    #
    # Example: $'\b is quoted as '$'\''\\b'
    s = s.replace("\\", "\\\\").replace("'", "'\\''")
    return "'" + s + "'"


ArgTypes = typing.Union[str, special.Special]


class UefiShell(shell.Shell, UefiStartup):
    """
    UEFI shell.

    The interface of this shell was designed to be close to the
    :ref:`Linux shell <linux-shells>` design.  This means that UEFI shells
    also provide

    - :py:meth:`uefi.escape() <rbot.machine.board.UefiShell.escape>` - Escape
      args for the UEFI shell.
    - :py:meth:`uefi.exec0() <rbot.machine.board.UefiShell.exec0>` - Run command
      and ensure it succeeded.
    - :py:meth:`uefi.exec() <rbot.machine.board.UefiShell.exec>` - Run command
      and return output and return code.
    - :py:meth:`uefi.test() <rbot.machine.board.UefiShell.test>` - Run command
      and return boolean whether it succeeded.
    - :py:meth:`uefienv() <rbot.machine.board.UefiShell.env>` - Get/Set
      environment variables.
    - :py:meth:`uefi.interactive() <rbot.machine.board.UefiShell.interactive>` -
      Start an interactive session for this machine.

    There is also the special :py:meth:`uefi.boot() <rbot.machine.board.UefiShell.boot>`
    which will boot a payload and return the machine's channel, for use in a
    machine for the booted payload.
    """

    prompt: typing.Union[str, bytes] = "Shell> \x1b[0m\x1b[37m\x1b[40m"
    """
    Prompt which was configured for UEFI.

    .. warning::
        ** Don't forget the ANSI colors codes for colorize the shell,
           if your prompt has one!**
    """

    bootlog: str
    """Transcript of console output during boot."""

    @contextlib.contextmanager
    def _init_shell(self) -> typing.Iterator:
        with self._uefi_startup_event() as ev, self.ch.with_stream(ev):
            self.ch.prompt = (
                self.prompt.encode("utf-8")
                if isinstance(self.prompt, str)
                else self.prompt
            )

            # Set a blacklist of control characters.  These characters are
            # known to mess up the state of the UEFI shell.  They are:
            self.ch._write_blacklist = [
                0x03,  # ETX  | End of Text / Interrupt
                0x04,  # EOT  | End of Transmission
                0x11,  # DC1  | Device Control One (XON)
                0x12,  # DC2  | Device Control Two
                0x13,  # DC3  | Device Control Three (XOFF)
                0x14,  # DC4  | Device Control Four
                0x15,  # NAK  | Negative Acknowledge
                0x16,  # SYN  | Synchronous Idle
                0x17,  # ETB  | End of Transmission Block
                0x1A,  # SUB  | Substitute / Suspend Process
                0x1C,  # FS   | File Separator
                0x7F,  # DEL  | Delete
            ]

            while True:
                if self.boot_timeout is not None:
                    assert self._timeout_start is not None
                    if (time.monotonic() - self._timeout_start) > self.boot_timeout:
                        raise TimeoutError("UEFI did not reach shell in time")
                try:
                    self.ch.read_until_prompt(timeout=0.5)
                    break
                except TimeoutError:
                    # self.ch.sendline()
                    self.ch.sendintr()
                    time.sleep(0.5)

        yield None

    def escape(self, *args: ArgTypes) -> str:
        """Escape a string so it can be used safely on the UEFI command-line."""
        string_args = []
        for arg in args:
            if isinstance(arg, str):
                # We can't use shlex.quote() here because UEFI's shell of
                # course has its own rules for quoting ...
                string_args.append(_hush_quote(arg))
            elif isinstance(arg, special.Special):
                string_args.append(arg._to_string(self))
            else:
                raise TypeError(f"{type(arg)!r} is not a supported argument type!")

        return " ".join(string_args)

    def exec(self, *args: ArgTypes) -> typing.Tuple[int, str]:
        """
        Run a command in UEFI.

        **Example**:

        .. code-block:: python

            retcode, output = uefi.exec("ver")
            assert retcode == 0

        :rtype: tuple(int, str)
        :returns: A tuple with the return code of the command and its console
            output.  The output will also contain a trailing newline in most
            cases.
        """
        cmd = self.escape(*args)

        override_prompt = None
        with rbot.log.command(self.name, cmd) as ev:
            self.ch.sendline(cmd, read_back=True)
            with self.ch.with_prompt(override_prompt):
                with self.ch.with_stream(ev, show_prompt=False):
                    out = self.ch.read_until_prompt(prompt=override_prompt)
            ev.data["stdout"] = util.strip_ansi_escapes(out).strip()

            self.ch.sendline("echo %lasterror%", read_back=True)
            retcode_str = util.strip_ansi_escapes(self.ch.read_until_prompt()).strip()
            try:
                retcode = int(retcode_str, 16)
            except ValueError:
                raise rbot.error.InvalidRetcodeError(self, retcode_str) from None

        return (retcode, out)

    def exec0(self, *args: ArgTypes) -> str:
        """
        Run a command and assert its return code to be 0.

        **Example**:

        .. code-block:: python

            output = uefi.exec0("ver")

            # This will raise an exception!
            uefi.exec0("false")

        :rtype: str
        :returns: The command's console output.  It will also contain a trailing
            newline in most cases.
        """
        retcode, out = self.exec(*args)
        if retcode != 0:
            raise rbot.error.CommandFailure(self, args, repr=self.escape(*args))
        return out

    def test(self, *args: ArgTypes) -> bool:
        """
        Run a command and return a boolean value whether it succeeded.

        **Example**:

        .. code-block:: python

            if uefi.test("echo"):
                rbot.log.message("Is correct")

        :rtype: bool
        :returns: Boolean representation of commands success.  ``True`` if
            return code was ``0``, ``False`` otherwise.
        """
        retcode, _ = self.exec(*args)
        return retcode == 0

    def env(self, var: str, value: typing.Optional[ArgTypes] = None) -> str:
        """
        Get or set an environment variable.

        **Example**:

        .. code-block:: python

            # Get the value of a var
            value = uefi.env("uefishellversion")

        :param str var: Environment variable name.
        :param str value: Optional value to set the variable to.
        :rtype: str
        :returns: Current (new) value of the environment variable.
        """
        if value is not None:
            self.exec0("setvar", var, str(f"={value}"))

        # Use `printenv var` instead of `echo "$var"` because some values would
        # otherwise result in broken expansion.
        output = self.exec0("echo", str(f"%{var}%"))
        # remove ansi escape sequence from string
        output = util.strip_ansi_escapes(output)
        # and trailing newline.
        return output.strip()

    def boot(self, *args: ArgTypes) -> channel.Channel:
        """
        Boot a payload from UEFI.

        This method will run the given command and expects it to start booting
        a payload.  ``uefi.boot()`` will then return the channel so a new machine
        can be built on top of it for the booted payload.

        **Example**:

        .. code-block:: python

            ch = uefi.boot("startup.nsh")

        :rtype: rbot.machine.channel.Channel
        """
        cmd = self.escape(*args)

        with rbot.log.command(self.name, cmd):
            self.ch.sendline(cmd, read_back=True)

        return self.ch.take()

    def interactive(self) -> None:
        """
        Start an interactive session on this machine.

        This method will connect rbot's stdio to the machine's channel so you
        can interactively run commands.  This method is used by the
        ``interactive`` testcase.
        """
        rbot.log.message(f"Entering interactive shell...")

        # It is important to send a space before the newline.  Otherwise UEFI
        # will reexecute the last command which we definitely do not want here.
        self.ch.sendline(" ")
        self.ch.attach_interactive(ctrld_exit=True)
        self.ch.sendline(" ")

        try:
            self.ch.read_until_prompt(timeout=0.5)
        except TimeoutError:
            raise rbot.error.MachineError(
                "Failed to reacquire UEFI after interactive session!"
            )

        rbot.log.message("Exiting interactive shell ...")
