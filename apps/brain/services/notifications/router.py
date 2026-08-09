from services.notifications import pushover


def transport_name():
    return "pushover"


def configured(channel="normal"):
    return pushover.configured(channel)


def publish(**notification):
    return pushover.publish(**notification)
