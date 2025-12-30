import rbot


@rbot.testcase
def linux_test():
    with rbot.ctx.request(rbot.role.BoardLinux) as rpi:
        _, out = rpi.exec("uname", "-a")
        rbot.log.message(out)
        _, out = rpi.exec("cat", "/etc/os-release")
        rbot.log.message(out)
