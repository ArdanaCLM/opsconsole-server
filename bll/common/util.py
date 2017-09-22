# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from dogpile.cache.api import CachedValue
import re
import logging
import threading
import time

from bll import api
from uuid import uuid4, uuid1
from pecan import conf

# the super-secret recipe for searching key-values pairs (i.e. key: value)
RE_KEYVALUE = re.compile(
    r'(\\?[\'"])(.*?)(\\?[\'"]):\s*(\\?[\'"])(.*?)(\\?[\'"])([:\s,}\]])')

context = threading.local()


def deepMerge(d1, d2, inconflict=lambda v1, v2: v2):
    '''
    merge d2 into d1. using inconflict function to
    resolve the leaf conflicts
    '''
    for k in d2:
        if k in d1:
            if isinstance(d1[k], dict) and isinstance(d2[k], dict):
                deepMerge(d1[k], d2[k], inconflict)
            elif d1[k] != d2[k]:
                d1[k] = inconflict(d1[k], d2[k])
        else:
            d1[k] = d2[k]
    return d1


def scrub_passwords(_val):

    if _val is None:
        return _val

    try:

        # We want to get a string value out of this object
        # strings are immutable so _val is never modified.
        if type(_val) in (str, unicode):
            out = _val
        else:
            out = str(_val)

        # convert u'blah' to "blah" since 'u' literals are not json-compatible
        # but also convert non-unicode strings, too
        out = re.sub("u?'(.*?)'([:\s,}\]])",
                     lambda match: '"%s"%s' %
                                   (match.group(1), match.group(2)), out)

        # Some Python-represented values may be None, but None is not a valid
        # value in json.  Let's convert that None to "None".  This isn't
        # necessary, but it makes it easier for unit-testing to take place
        out = re.sub(": None", ": \"None\"", out)

        # Search for key-value pairs where the key contains 'password/cert'
        # and "4-star" the values
        out = re.sub(RE_KEYVALUE,
                     lambda match: "%s%s%s: %s%s%s%s" %
                                   (match.group(1), match.group(2),
                                    match.group(3), match.group(4),
                                    '****', match.group(6), match.group(7))
                     if 'password' in match.group(2).lower() or
                        'cert' in match.group(2).lower()
                     else match.group(0),
                     out)

        # Search for key-value pairs where the key contains 'token'
        out = re.sub(RE_KEYVALUE,
                     lambda match: "%s%s%s: %s%s%s%s" %
                                   (match.group(1), match.group(2),
                                    match.group(3), match.group(4),
                                    "%s%s" % ('*' * (len(match.group(5)) - 4),
                                              match.group(5)
                                              [-(min(4,
                                                     len(match.group(5)))):]),
                                    match.group(6), match.group(7))
                     if 'token' in match.group(2).lower()
                     else match.group(0),
                     out)

        # we only need to return a string representation of the object
        # since this is only used for logging
        return out
    except Exception:
        # Not sure how we'd ever get here, but just in case we can't scrub
        # the passwords, we'll just print this useless message
        return "Could not properly scrub_passwords for passed in object"


def empty(value):
    if value is None:
        return True
    elif isinstance(value, str) and len(value) < 1:
        return True

    return False


def _get_app_env():
    return conf.get('env', 'stdcfg')


def is_stdcfg():
    """
    Determines whether the BLL is running in a stdcfg environment or legacy
    environment based on the presence of an entry in the config file that
    indicates this.

    WARNING

    It is preferable to avoid using this function in the BLL, as well as its 
    sibling is_legacy(), and instead rely in the presence of services to 
    dictate logic.
    """
    return _get_app_env() == "stdcfg"


def is_legacy():
    """
    WARNING

    See description of is_stdcfg above.
    """
    return _get_app_env() == "legacy"


def get_conf(key, default=None):
    """
    Traverse through the levels of the config file to obtain the specified
    key, safely handling any missing levels.  For example, if the key is
    "app.error", it will find the "error" entry in the "app" dictionary; if
    either the app dictionary or the error entry is missing, then the default
    will be returned.
    """
    return get_val(conf, key, default)


def get_val(dic, key, default=None):
    """
    Traverse through the levels of a dictionary to obtain the
    specified key, safely handling any missing levels.  For example, if the
    key is "app.error", it will find the "error" entry in the "app"
    dictionary; if either the app dictionary or the error entry is missing,
    then the default will be returned.
    """
    if not key:
        return default

    try:
        current = dic
        for attribute in key.split("."):
            current = current[attribute]
        return current

    except KeyError:
        return default


def setup_txn_logging():
    """
    Setup python logging to be able to include the txn id in messages, which
    will be kept in thread-local storage
    """

    LOG = logging.getLogger('bll')
    f = ContextFilter()
    LOG.addFilter(f)
    for handler in LOG.handlers:
        handler.addFilter(f)


class ContextFilter(logging.Filter):
    """
    This logging filter enables the transaction id to be included
    as a field in log messages
    """

    def filter(self, record):
        record.txn_id = getattr(context, 'txn_id', '')
        return True


def new_txn_id(txn_id=None):
    """
    Create a new txn id using an exiting transaction id.  The newly created txn
    id will contain a concatenation of the existing transaction id plus a new
    unique id, separated by a delimiter.

    The basic idea is that when a new call comes into the BLL, it has a
    transaction id that is often a uuid.  If the BLL first service needs to
    make another call to another BLL service, it is required that it have a new
    transaction id since transaction id's are used as unique identifiers for
    obtaining status of long-running processes, which must be unique or else
    it cannot properly correlate calls with responses.  Creating transaction
    ids for these subsequent calls that are derived from the original
    facilitate associating the calls together.
    :param txn_id:
    :return:
    """
    main_txn_id = txn_id

    # No txn_id passed, so look in the context
    if not main_txn_id:
        main_txn_id = getattr(context, 'txn_id', '')

    if main_txn_id:
        # If we have a txn_id, then create a sub-txn_id with a unique id.
        # This sub-txn does not have to be a full uuid -- instead, generate
        # a uuid1 whose first 8 characters are unique on this system,
        # and thus for this transaction (the 8 characters are generated by a
        # timestamp plus logic to avoid duplicates)
        return main_txn_id.split('.')[0] + "." + str(uuid1())[:8]

    else:
        return str(uuid4())


def get_service_tenant_name():
    return get_conf('keystone.service_tenant', 'service')


def response_to_string(resp, print_data=False):
    """
    Utility function for converting a response dictionary to a string.
    This function can be used to create a string representation of a
    BllResponse, which is a thin veneer over a dictionary, or just
    a bare dictionary (which is all that the app_controller has)

    :param resp:
    :return string:
    """

    # Print the DATA portion of the request with sorted keys
    if print_data:
        data = resp.get(api.DATA)

        if isinstance(data, dict):
            sorted_keys = sorted(data.keys())

            data_list = []
            for key in sorted_keys:
                data_list.append("%s:%s" % (key, str(data[key])))

            data_str = scrub_passwords("{%s}" % ",".join(data_list))
        else:
            data_str = scrub_passwords(data)
        data_str = "DATA:%s" % data_str
    else:
        data_str = ""

    result = ""
    if api.STATUS in resp:
        result += "STATUS:%s " % (resp[api.STATUS])

    if api.TXN_ID in resp:
        result += "TXN:%s " % (resp[api.TXN_ID])

    if api.DURATION in resp:
        result += "DURATION:%d " % (resp[api.DURATION])

    if api.PROGRESS in resp:
        result += "PROGRESS:%s " % (str(resp[api.PROGRESS]))

    return result + data_str


def start_cache_cleaner(cache, cache_expiration, thread_name="CacheCleaner"):
    """
    Create a thread to clean up the given dogpile cache.  Items whose age,
    in seconds, is older than cache_expiration, are removed from the cache.
    """
    def expire_cache():
        while True:
            current_time = time.time()
            for k, v in cache.items():
                if isinstance(v, CachedValue):
                    # Determines whether the cache has expired by comparing
                    # the elapsed time since the creation time (metadata["ct"])
                    # against the expiration time.
                    if current_time - v.metadata["ct"] > cache_expiration:
                        del cache[k]
            time.sleep(cache_expiration)

    t = threading.Thread(target=expire_cache, name=thread_name)
    t.daemon = True
    t.start()
