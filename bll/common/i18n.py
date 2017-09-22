# (c) Copyright 2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import gettext
import os


def get_(language):
    """
    Returns the function for localizing text for the given language, which
    is normally assigned to the function name ``_``.  Typical usage::

        _ = get_('en')
        print _("localizable string")

    :param language:
    :return:
    """
    locale_dir = os.path.realpath(os.path.join(
        os.path.dirname(__file__), '..', 'locale'))
    translator = gettext.translation(domain='messages',
                                     localedir=locale_dir,
                                     fallback=True,
                                     languages=[language])
    return translator.ugettext
