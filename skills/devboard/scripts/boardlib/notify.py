"""Desktop notice for the person when an agent hands them something (`ask`, or an assignment to user).

Fire and forget: a notice never blocks or breaks a write. Settings:
  DEVBOARD_NOTIFY=0         turn notices off (the tests do this)
  DEVBOARD_NOTIFY_CMD="..." run this shell command instead of the system notice; it gets the text in
                            DEVBOARD_NOTIFY_TITLE and DEVBOARD_NOTIFY_BODY (phone push, chat webhook, ...)
Default: a Windows toast (PowerShell), macOS Notification Center (osascript) or notify-send on Linux.
"""
import os
import shutil
import subprocess
import sys

OFF = ("0", "off", "false", "no")

# Text travels in environment variables, never inside the script, so a card title cannot inject code.
WIN_TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
    "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$x = $t.GetElementsByTagName('text');"
    "$x.Item(0).AppendChild($t.CreateTextNode($env:DEVBOARD_NOTIFY_TITLE)) > $null;"
    "$x.Item(1).AppendChild($t.CreateTextNode($env:DEVBOARD_NOTIFY_BODY)) > $null;"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
)
MAC_SCRIPT = ('display notification (system attribute "DEVBOARD_NOTIFY_BODY") '
              'with title (system attribute "DEVBOARD_NOTIFY_TITLE")')


def command():
    """(argv or shell string, shell?) for this machine, or None when there is no way to notify."""
    custom = os.environ.get("DEVBOARD_NOTIFY_CMD")
    if custom:
        return custom, True
    if sys.platform == "win32" and shutil.which("powershell"):
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", WIN_TOAST], False
    if sys.platform == "darwin" and shutil.which("osascript"):
        return ["osascript", "-e", MAC_SCRIPT], False
    if shutil.which("notify-send"):
        return ["sh", "-c", 'notify-send "$DEVBOARD_NOTIFY_TITLE" "$DEVBOARD_NOTIFY_BODY"'], False
    return None


def user(title, body):
    if os.environ.get("DEVBOARD_NOTIFY", "1").strip().lower() in OFF:
        return False
    cmd = command()
    if cmd is None:
        return False
    env = dict(os.environ, DEVBOARD_NOTIFY_TITLE=f"devboard · {title}"[:120], DEVBOARD_NOTIFY_BODY=str(body)[:300])
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        subprocess.Popen(cmd[0], shell=cmd[1], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError:
        return False
    return True
