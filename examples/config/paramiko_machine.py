import rbot

from rbot.machine import connector, shell


class SSHLocalHost(
    connector.ParamikoConnector, connector.ParamikoInitializer, shell.Bash
):
    hostname = "localhost"
    username = "roman"


def register_machines(ctx):
    ctx.register_machine(SSHLocalHost, rbot.role.BoardLinux)
