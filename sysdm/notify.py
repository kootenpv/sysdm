import sys
from cliche import cli
from typing import Optional, Union
import subprocess


def install_notifier_dependencies(name):
    dependencies = {
        "telegram": [("telegram", "python-telegram-bot")],
        "yagmail": [("yagmail", "yagmail")],
        "notify-send": [("notify", "notify-send")],
    }
    for name, pip_package in dependencies.get(name, []):
        try:
            __import__(name)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_package])


@cli
def notify(
    notifier,
    user: Optional[Union[str, int]] = None,
    to: Optional[Union[str, int]] = None,
    pw: Optional[str] = None,
    msg: Optional[str] = None,
):
    body = sys.stdin.read()[-2000:]
    if notifier == "telegram":
        import telegram

        bot = telegram.Bot(user)
        to = -int(to)
        bot.sendMessage(to, msg + "\n\n" + body)
    elif notifier == "yagmail":
        import yagmail

        yag = yagmail.SMTP(user, pw)
        yag.send(to=to, subject=msg, contents=body)
    elif notifier == "notify-send":
        from notify import notification

        notification(body, msg)
