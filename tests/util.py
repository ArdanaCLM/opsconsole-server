# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from contextlib import contextmanager
from bll import api
from bll.api import auth_token
from bll.api.auth_token import verify_https
from bll.api.request import BllRequest
from bll.common import job_status
from keystoneclient.v3 import client as ksclient3
from bll.plugins.service import SvcBase
from stubs.common.dict_job_status import DictStatus
from keystoneclient.v2_0 import client as ksc
import logging
import os
import mock
import pymysql.cursors
import random
import socket
import unittest

from pecan import testing
import pecan

detected = None


def functional(requires=None):
    """
    This function is used as a decorator to indicate that the given tests
    are "functional", which is to say, that they generally depend on some
    additional services to be running in the environment which are not
    automatically started by the test.

    :param requires: comma-separated list of items that must appear in the
                     environment variable named "functional".  For legacy
                     reasons, if "functional" consists solely of the string
                     "1", "true", or "all", then it will be considered that
                     all requirements are met
    """
    missing = _functional_lacking(requires)
    return unittest.skipUnless(len(missing) == 0,
                               "Functional test requires %s" %
                               (",".join(missing)))


def _functional_lacking(requires=None):
    """
    Returns a set of items that are lacking in order to execute a functional
    test that requires the indicated items.  Returns an empty set if all
    necessary items are present.
    """
    functional_env = os.environ.get('functional', '')

    needs = {x.strip() for x in requires.split(",")}

    if functional_env in ('all', 'true', '1'):
        has = needs
    else:
        has = {x.strip() for x in functional_env.split(",")}

    global detected
    if 'auto' in has:

        if detected is None:
            detected = set()

            if _has_mysql():
                detected.add('mysql')

            services = []
            try:
                auth_ref = get_auth_ref_from_env()
                services = ksc.Client(auth_ref=auth_ref,
                                      verify=verify_https()).services.list()
            except:
                pass

            # Add both the name and type as being detected, in case
            # some tests indicate the need for the name (e.g. monasca)
            # while others indicate the need for the type (e.g. volume)
            for s in services:
                detected.add(s.type)
                detected.add(s.name)

            print("Autodetected:", ",".join(sorted(detected)))

        has |= detected

    missing = needs.difference(has)
    return missing


def _has_mysql():

    # Retrieve a database connection based on the config
    try:
        loadConfigFile()
        config = pecan.conf.db.to_dict()
        config['cursorclass'] = pymysql.cursors.DictCursor
        pymysql.connect(**config)
        return True
    except:
        return False


def _is_port_in_use(address, port):
    s = socket.socket()
    try:
        s.connect((address, port))
        return True
    except socket.error:
        return False


def getConfigFile():

    test_config = os.path.realpath(
        os.path.join(os.path.dirname(__file__), '../tests/config.py'))

    if os.getenv("BLL_CONF_OVERRIDE"):
        config_file = os.getenv("BLL_CONF_OVERRIDE")
    elif os.path.isfile(test_config):
        config_file = test_config
    elif os.path.isfile('/etc/opsconsole-server/config.py'):
        config_file = '/etc/opsconsole-server/config.py'
    else:
        config_file = '/etc/opsconsole-server/opsconsole-server.conf'

    return config_file


loaded_config = False


def loadConfigFile():
    global loaded_config
    if loaded_config:
        return

    loaded_config = True
    pecan.conf.update(
        pecan.configuration.conf_from_file(getConfigFile()))

    # Use the logging configuration in the config file
    if 'logging' in pecan.conf:
        logging.config.dictConfig(pecan.conf['logging'])
    else:
        logging.basicConfig(level=logging.WARN)


class TestCase(unittest.TestCase):

    @classmethod
    def load_test_app(cls):
        cls.app = testing.load_test_app(getConfigFile())

    @classmethod
    def setUpClass(cls):
        loadConfigFile()

        # Determine whether the job status functions should run with mysql
        # or a test double (DictStatus).  It is basically equivalent to
        # determining whether 'mysql' is in the functional environment
        # variable, except that it also takes into account the new 'auto'
        # option.
        if _functional_lacking('mysql'):
            # Inject a mock, since mysql is not available
            job_status._get_status_obj = mock.Mock(return_value=DictStatus())


def randomword(length=12):
    """
    Generate a string of random alphanumeric characters
    """
    valid_chars = \
        'abcdefghijklmnopqrstuvyxwzABCDEFGHIJKLMNOPQRSTUVYXWZ012345689'
    return ''.join(random.choice(valid_chars) for i in range(length))


def randomidentifier(length=12):
    """
    Generate a random identifier, which is an alpha character followed by
    alphanumeric characters
    """
    valid_firsts = 'abcdefghijklmnopqrstuvyxwzABCDEFGHIJKLMNOPQRSTUVYXWZ'
    return ''.join((random.choice(valid_firsts), randomword(length - 1)))


def randomhex(length=32):
    """
    Generate a random hex string
    """
    valid_chars = 'abcdef0123456789'
    return ''.join(random.choice(valid_chars) for i in range(length))


def randomurl():
    """
    Generate a random url value
    """
    return "http://%s/%s" % (randomword(), randomword())


def randomdict():

    # build a complicated, nested dictionary
    my_dict = {}
    my_dict[randomidentifier()] = randomword()

    nested_dict = {}
    nested_dict[randomidentifier()] = randomword()
    my_dict['dict'] = nested_dict

    nested_array = []
    nested_array.append(randomword())
    nested_array.append(randomword(500))
    nested_array.append(random.random())
    nested_array.append(random.randint(0, 1000))
    my_dict['array'] = nested_array

    return my_dict


def randomip():
    return '%d.%d.%d.%d' % (random.randint(1, 255),
                            random.randint(0, 255),
                            random.randint(0, 255),
                            random.randint(0, 255))


def test_spawn_service(target, operation=None, action=None, token=None,
                       data=None):
    """
    Variant of spawn_service intended for testing -- the keystone token will be
    faked if not passed
    """
    payload = {}
    if operation:
        payload[api.OPERATION] = operation
    if data:
        payload.update(data)

    req = {
        api.TARGET: target,
        api.ACTION: action or "GET",
        api.AUTH_TOKEN: token or get_mock_token(),
        api.DATA: payload
    }
    return SvcBase.spawn_service(BllRequest(req))


def get_mock_token():
    return randomhex()


@contextmanager
def log_level(level, name):
    """
    Enable modifying logging level in a context manager
    """
    logger = logging.getLogger(name)
    old_level = logger.getEffectiveLevel()
    logger.setLevel(level)
    try:
        yield logger
    finally:
        logger.setLevel(old_level)


def get_auth_ref_from_env():
    """
    Obtains keystone token using the provided configuration
    """
    username = os.getenv('OS_USERNAME')
    password = os.getenv('OS_PASSWORD')
    if username is None or password is None:
        raise Exception("OS_USERNAME and OS_PASSWORD env vars must be set")

    return auth_token.login(username, password)


def get_token_from_env():
    return get_auth_ref_from_env().auth_token


ksclient = None


def create_user(project_roles={}, domain_roles={}):
    # Creates a keystone user with the specified roles.  Project_roles
    # and domain_roles are dictionaries with the key(s) being the name of the
    # project (or domain), and the value(s) being the name of the role
    #

    global ksclient
    if ksclient is None:

        # The OS_USERNAME and OS_PASSWORD should be for a keystone admin,
        # a user with the admin role in the default domain, since it is being
        # used to create new users.
        # Need a v3 URL for performing domain operations
        ksclient = ksclient3.Client(auth_url=auth_token.get_auth_url('v3'),
                                    username=os.getenv('OS_USERNAME'),
                                    password=os.getenv('OS_PASSWORD'),
                                    domain_name='default',
                                    verify=verify_https())

    username = "test_" + randomidentifier()
    password = randomidentifier()

    if not project_roles or 'admin' in project_roles:
        project_name = 'admin'
    else:
        # Just pick a project
        project_name = project_roles.keys()[0]

    domains = {d.name: d for d in ksclient.domains.list()}
    projects = {p.name: p for p in ksclient.projects.list()}
    roles = {r.name: r for r in ksclient.roles.list()}

    user = ksclient.users.create(name=username,
                                 password=password,
                                 default_project=projects[project_name])

    for project, role in project_roles.iteritems():
        ksclient.roles.grant(role=roles[role],
                             user=user,
                             project=projects[project])

    for domain, role in domain_roles.iteritems():
        ksclient.roles.grant(role=roles[role],
                             user=user,
                             domain=domains[domain])

    # Return the new user and generated password
    return user, password


def delete_user(user):
    global ksclient
    if ksclient is not None and user is not None:
        ksclient.users.delete(user)
