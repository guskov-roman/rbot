import rbot


@rbot.testcase
def local_test():
    with rbot.ctx.request(rbot.role.LocalHost) as lo:
        lo.exec("uname", "-a")
        lo.exec("cat", "/etc/os-release")
