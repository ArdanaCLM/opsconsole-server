# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC


def _(msg):
    """
    Define _ to just return its arg.  Using this will flag strings that call
    it for translation.  The strings are actually localized in service.py
    before being returned to the UI
    """
    return msg


class BllException(Exception):
    """
    This class and its derived classes should define an ``overview`` member
    that contains a string describing an overview of the type of error.
    """
    overview = _("An unknown exception occurred")


class InvalidBllRequestException(BllException):
    overview = _("Invalid request")


class BllAuthenticationFailedException(BllException):
    overview = _("Authentication Failed to Backend Identity")
