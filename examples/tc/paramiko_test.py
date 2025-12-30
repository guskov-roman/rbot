import rbot


@rbot.testcase
def local_test():
    with rbot.ctx.request(rbot.role.BoardLinux) as lo:
        lo.exec("uname", "-a")
        lo.exec("cat", "/etc/os-release")
        lo.exec("ls", "/var/log")
