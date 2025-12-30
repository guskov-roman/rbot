import rbot

from .channel import (
    BoundedPattern,
    Channel,
    ChannelBorrowedException,
    ChannelClosedException,
    ChannelIO,
    ChannelTakenException,
    DeathStringException,
)

from .subprocess import SubprocessChannel
from .null import NullChannel

try:
    from .paramiko import ParamikoChannel
except ImportError:  # pragma: no cover
    raise rbot.error.RbotException(
        """\
The ParamikoChannel requires paramiko to be installed:
pip3 install paramiko
"""
    )

try:
    from .pyserial import PyserialChannel
except ImportError:  # pragma: no cover
    raise rbot.error.RbotException(
        """\
The PyserialChannel requires pyserial to be installed:
pip3 install pyserial
"""
    )

__all__ = (
    "BoundedPattern",
    "Channel",
    "ChannelBorrowedException",
    "ChannelClosedException",
    "ChannelIO",
    "ChannelTakenException",
    "DeathStringException",
    "PyserialChannel",
    "ParamikoChannel",
    "SubprocessChannel",
    "NullChannel",
)
