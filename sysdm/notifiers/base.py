from sysdm.utils import get_output


class Base:
    description = ""
    cmd = ""

    @staticmethod
    def get_status_string(n=1000):
        """ %i refers to unit name """
        return "systemctl --user status -l -n {} %i".format(n)

    def get_notifier_cmd(self, **kwargs):
        """ Use:
        - %i to refer to unit name,
        - %H to hostname
        - {home} to refer to the users home folder
        """
        raise NotImplementedError

    def get_exec_start(self, n=1000, **kwargs):
        cmd = self.get_status_string(n) + " | " + self.get_notifier_cmd(**kwargs)
        return "/bin/bash -c {}".format(repr(cmd))

    @property
    def on_failure_name(self):
        return "OnFailure={}@%i.service".format(self.description.lower().replace(" ", "-"))

    @property
    def user(self):
        return get_output("echo $USER")

    @property
    def home(self):
        return get_output("echo ~" + self.user)

    @property
    def on_failure_service(self, n=1000, **kwargs):
        kwargs["home"] = self.home
        kwargs["user"] = self.user
        kwargs["description"] = self.description
        kwargs["exec_start"] = self.get_exec_start(n, **kwargs)
        service = """
        [Unit]
        Description={description}

        [Service]
        Type=oneshot
        ExecStart={exec_start}
        """.format(
            **kwargs
        ).replace(
            "\n    ", "\n"
        )
        return service


class Yagmail:
    description = "Mail OnFailure"
    cmd = "yagmail"
    args = ["-s", "%i failed on %H" "-oauth2" "{home}/oauth2.json"]
