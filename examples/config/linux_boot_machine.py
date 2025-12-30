import rbot
from rbot.machine import board, connector, linux


class RaspberryPi(connector.PyserialConnector, board.Board):

    serial_port = "/dev/ttyUSB0"


class LinuxRaspberryPi(board.Connector, board.LinuxBootLogin, linux.Bash):
    username = "roman"
    password = "ra4csn"


def register_machines(ctx):
    ctx.register_machine(RaspberryPi, rbot.role.Board)
    ctx.register_machine(LinuxRaspberryPi, rbot.role.BoardLinux)
