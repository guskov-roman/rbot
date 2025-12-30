import rbot
from .connector import Connector
from .common import SubprocessConnector, ConsoleConnector, NullConnector
from .ssh import SSHConnector


try:
    from .paramiko import ParamikoConnector, ParamikoInitializer
except ImportError:
    raise rbot.error.RbotException(
        """\
The ParamikoConnector requires paramiko to be installed:
pip3 install paramiko
"""
    )

try:
    from .pyserial import PyserialConnector
except ImportError:
    raise rbot.error.RbotException(
        """\
The PyserialConnector requires pyserial to be installed:
pip3 install pyserial
"""
    )


__all__ = (
    "Connector",
    "SubprocessConnector",
    "ConsoleConnector",
    "ParamikoConnector",
    "ParamikoInitializer",
    "PyserialConnector",
    "SSHConnector",
    "NullConnector",
)
