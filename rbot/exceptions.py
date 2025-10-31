import typing
from typing import Any, Optional


class RbotException(Exception):
    """
    Base-class for all exceptions which are specific to uhtf.
    """


class ChannelException(RbotException):
    """
    Base-class for exceptions raised due to channel errors
    """


class ApiViolationException(RbotException, RuntimeError):
    """
    Base-class for all exceptions that are raised due to wrong use of rbot's API.
    """


class ChannelClosedException(ChannelException):
    """
    Error type for exceptions when a channel was closed unexpectedly.
    """


class ChannelBorrowedException(ApiViolationException):
    """
    Error type for exceptions when accessing a channel which is currently borrowed.
    """

    def __init__(self) -> None:
        super().__init__("channel is currently borrowed by another machine")


class ChannelTakenException(ApiViolationException):
    """
    Error type for exceptions when accessing a channel which was "taken".
    """

    def __init__(self) -> None:
        super().__init__(
            "channel was taken by another." + " it can no longer be accessed from here"
        )


class IllegalDataException(ApiViolationException):
    """
    Raised when attempting to write illegal data to a channel.

    Some channels cannot deal with all byte sequences.  For example, certain
    escape sequences will mess up the connection.  If an attempt is made to
    send such data, this exception is raised.  The exact set of illegal
    sequences depends on the specific machine configuration.
    """


class UnboundedPatternException(ApiViolationException, ValueError):
    """
    Raised when a regex pattern is used which does not have a bounded length.

    rbot requires the use of patterns with a bounded length to keep track of
    incoming data efficiently.  A bounded pattern is one which does not use any
    infinitely repeating expressions.
    """

    def __init__(self, pattern: bytes) -> None:
        self.pattern = pattern

        super().__init__(f"Regex expression {pattern!r} is not bounded")


class CommandFailureException(RbotException):
    """
    A command exited with non-zero exit code.
    """

    cmd: Any

    out: str

    def __init__(self, cmd: Any, *, out: Optional[str] = None) -> None:
        self.cmd = cmd
        if repr is not None:
            self.cmd_repr = out
        else:
            self.cmd_repr = self.cmd

        super().__init__(f"command failed: {self.cmd_repr}")


class InvalidRetcodeException(ChannelException):
    """
    While trying to fetch the return code of a command,
    unexpected output was received.
    """

    def __init__(
        self,
        retcode_str: str,
    ) -> None:
        self.retcode_str = retcode_str
        super().__init__(
            f"received string {retcode_str!r} instead of a return code integer"
        )


class DeathStringException(RbotException):
    __slots__ = "match"

    def __init__(self, match: typing.Union[bytes, typing.Match[bytes]] = b""):
        self.match = match

    def __repr__(self) -> str:
        return f"DeathStringException({self.match!r})"
